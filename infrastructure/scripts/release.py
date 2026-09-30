"""Manual GitHub Actions releases into the existing, shared ECR repository."""

import argparse
import json
import os
import re
from functools import partial
from pathlib import Path
from urllib.request import urlopen

import boto3
import deploy

CONFIG = Path(__file__).resolve().parents[1] / "environments" / "production.json"


def source_commit(component, tag):
    match = re.fullmatch(rf"{component}-([0-9a-f]{{40}})-[A-Za-z0-9_.-]+", tag)
    if not match or len(tag) > 128:
        raise ValueError(f"Use a {component}-<40-character SHA>-<version> image tag")
    return match[1]


def prepare(component, operation, image_tag, config, environ):
    if environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("Run the release workflow from main")
    if operation == "deploy-existing":
        commit = source_commit(component, image_tag)
    else:
        if image_tag:
            raise ValueError("image_tag must be empty when building a new image")
        commit = environ["GITHUB_SHA"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid source commit")
        run, attempt = environ["GITHUB_RUN_ID"], environ["GITHUB_RUN_ATTEMPT"]
        if not run.isdigit() or not attempt.isdigit():
            raise ValueError("Invalid GitHub run identity")
        image_tag = f"{component}-{commit}-{run}-{attempt}"
    repository = config["services"][component]["repository"]
    return {
        "image_tag": image_tag,
        "source_sha": commit,
        "repository": repository,
        "region": config["region"],
        "account_id": config["account_id"],
    }


def resolve_image(ecr, repository_url, component, tag):
    commit = source_commit(component, tag)
    _, name = repository_url.split("/", 1)
    repository = ecr.describe_repositories(repositoryNames=[name])["repositories"][0]
    if repository["repositoryUri"] != repository_url:
        raise RuntimeError("ECR repository does not match the release configuration")
    if repository["imageTagMutability"] != "IMMUTABLE":
        raise RuntimeError("Release tags require an immutable ECR repository")
    detail = ecr.describe_images(repositoryName=name, imageIds=[{"imageTag": tag}])["imageDetails"][
        0
    ]
    digest = detail["imageDigest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Invalid ECR image digest")
    return f"{repository_url}@{digest}", commit


def write_summary(values):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            for name, value in values.items():
                output.write(f"- **{name}**: `{value}`\n")
    print(json.dumps(values), flush=True)


def release(session, config, component, tag, deploy_requested):
    ecs, ecr = session.client("ecs"), session.client("ecr")
    service_config = config["services"][component]
    image, commit = resolve_image(ecr, service_config["repository"], component, tag)
    summary = {"Component": component, "Source commit": commit, "Image tag": tag, "Image": image}
    if not deploy_requested:
        write_summary({**summary, "Result": "Built and pushed; ECS unchanged"})
        return

    cluster, name = config["cluster"], service_config["name"]
    current = deploy.read_service(ecs, cluster, name)
    if len(current.get("deployments", [])) != 1 or any(
        d.get("rolloutState") != "COMPLETED" for d in current.get("deployments", [])
    ):
        raise RuntimeError("Another ECS deployment is active; retry after it completes")
    # Clone the service's actual revision, never an unused latest family revision.
    revision = deploy.register_image(ecs, current["taskDefinition"], component, image, commit)
    write_summary(
        {**summary, "Previous task": current["taskDefinition"], "Requested task": revision}
    )
    after_rollback = None
    if component == "frontend":
        after_rollback = partial(
            deploy.invalidate_frontend,
            session.client("cloudfront"),
            config["cloudfront_distribution_id"],
            f"{commit}-rollback",
        )

    previous = deploy.deploy_service(ecs, cluster, name, revision, after_rollback=after_rollback)
    restored_schedules = []
    scheduler = session.client("scheduler")
    try:
        if component == "backend":
            deploy.check_health(config["base_url"], commit)
            for job in config.get("jobs", {}).values():
                if "schedule" not in job:
                    continue
                schedule = scheduler.get_schedule(Name=job["schedule"], GroupName="default")
                old = deploy.request_fields(scheduler, "UpdateSchedule", schedule)
                job_revision = deploy.register_image(
                    ecs,
                    schedule["Target"]["EcsParameters"]["TaskDefinitionArn"],
                    job["container"],
                    image,
                    commit,
                )
                # Record before mutation so a lost response can still be rolled back.
                restored_schedules.append(old)
                payload = deploy.request_fields(scheduler, "UpdateSchedule", schedule)
                payload["Target"]["EcsParameters"]["TaskDefinitionArn"] = job_revision
                scheduler.update_schedule(**payload)
        else:
            deploy.invalidate_frontend(
                session.client("cloudfront"), config["cloudfront_distribution_id"], commit
            )
            with urlopen(config["base_url"], timeout=30) as response:
                if response.status != 200 or "text/html" not in response.headers.get(
                    "Content-Type", ""
                ):
                    raise RuntimeError("Frontend smoke check failed")
        # A stable service can mean AWS rolled back. Verify the exact requested revision.
        deploy.wait_for_revision(ecs, cluster, name, revision, max(previous["desiredCount"], 1))
    except Exception as release_error:
        errors = [release_error]
        for old in reversed(restored_schedules):
            try:
                scheduler.update_schedule(**old)
            except Exception as error:
                errors.append(error)
        try:
            deploy.rollback_service(ecs, cluster, previous, after_rollback=after_rollback)
        except Exception as error:
            errors.append(error)
        write_summary(
            {
                "Result": "Release failed; rollback attempted",
                "Previous task": previous["taskDefinition"],
            }
        )
        if len(errors) > 1:
            raise ExceptionGroup("Release and rollback errors", errors) from release_error
        raise
    write_summary({"Result": "Deployed and verified", "Service": name, "Active task": revision})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "verify", "deploy"])
    parser.add_argument("--component", required=True, choices=["frontend", "backend"])
    parser.add_argument(
        "--operation",
        choices=["build-only", "build-and-deploy", "deploy-existing"],
        default="build-only",
    )
    parser.add_argument("--image-tag", default="")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.command == "prepare":
        values = prepare(args.component, args.operation, args.image_tag, config, os.environ)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            for name, value in values.items():
                output.write(f"{name}={value}\n")
        return
    session = boto3.Session(region_name=config["region"])
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != config["account_id"]:
        raise RuntimeError("Unexpected AWS account")
    release(session, config, args.component, args.image_tag, args.command == "deploy")


if __name__ == "__main__":
    main()
