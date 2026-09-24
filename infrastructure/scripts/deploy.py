"""Deploy immutable images to Terraform-created ECS services.

Uses locally configured AWS credentials.
Configuration is the JSON value of ``terraform output -json deployment_config``.
No infrastructure is provisioned by this command. Bootstrap is a separate action.
"""

import argparse
import base64
import copy
import json
import os
import re
import subprocess
import time
from functools import partial
from pathlib import Path
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[2]


def request_fields(client, operation, values):
    """Remove response-only fields before sending a describe result back to AWS."""
    allowed = client.meta.service_model.operation_model(operation).input_shape.members
    return {key: copy.deepcopy(value) for key, value in values.items() if key in allowed}


def image_for_commit(ecr, repository_url, commit, component):
    registry, repository = repository_url.split("/", 1)
    try:
        detail = ecr.describe_images(repositoryName=repository, imageIds=[{"imageTag": commit}])[
            "imageDetails"
        ][0]
    except ClientError as error:
        if error.response["Error"]["Code"] != "ImageNotFoundException":
            raise
        authorization = ecr.get_authorization_token()["authorizationData"][0]
        user, password = (
            base64.b64decode(authorization["authorizationToken"]).decode().split(":", 1)
        )
        subprocess.run(
            ["docker", "login", "--username", user, "--password-stdin", registry],
            input=password,
            text=True,
            check=True,
        )
        tagged = f"{repository_url}:{commit}"
        command = ["docker", "build", "--platform", "linux/amd64", "-t", tagged]
        if component == "frontend":
            command.extend(["--build-arg", "VITE_API_BASE_URL=/api/v1"])
        subprocess.run([*command, str(ROOT / component)], check=True)
        subprocess.run(["docker", "push", tagged], check=True)
        detail = ecr.describe_images(repositoryName=repository, imageIds=[{"imageTag": commit}])[
            "imageDetails"
        ][0]
    return f"{repository_url}@{detail['imageDigest']}"


def register_image(ecs, family, container_name, image, commit):
    definition = ecs.describe_task_definition(taskDefinition=family)["taskDefinition"]
    payload = request_fields(ecs, "RegisterTaskDefinition", definition)
    matching = [c for c in payload["containerDefinitions"] if c["name"] == container_name]
    if len(matching) != 1:
        raise RuntimeError(f"Expected one {container_name} container in {family}")
    matching[0]["image"] = image
    if container_name == "backend":
        environment = [
            e for e in matching[0].get("environment", []) if e["name"] != "RELEASE_VERSION"
        ]
        matching[0]["environment"] = [
            *environment,
            {"name": "RELEASE_VERSION", "value": commit},
        ]
    return ecs.register_task_definition(**payload)["taskDefinition"]["taskDefinitionArn"]


def read_service(ecs, cluster, name):
    response = ecs.describe_services(cluster=cluster, services=[name])
    if response.get("failures") or len(response.get("services", [])) != 1:
        raise RuntimeError(f"ECS service unavailable: {name}")
    service = response["services"][0]
    if service["status"] != "ACTIVE":
        raise RuntimeError(f"ECS service is not active: {name}")
    return service


def wait_for_revision(ecs, cluster, name, revision, desired):
    ecs.get_waiter("services_stable").wait(
        cluster=cluster, services=[name], WaiterConfig={"Delay": 15, "MaxAttempts": 60}
    )
    service = read_service(ecs, cluster, name)
    primary = next(d for d in service["deployments"] if d["status"] == "PRIMARY")
    if (
        primary["taskDefinition"] != revision
        or primary.get("rolloutState") != "COMPLETED"
        or service["runningCount"] < desired
    ):
        raise RuntimeError(f"ECS did not activate requested revision for {name}")


def deploy_service(ecs, cluster, name, revision, *, after_rollback=None):
    previous = read_service(ecs, cluster, name)
    desired = max(previous["desiredCount"], 1)
    try:
        ecs.update_service(
            cluster=cluster, service=name, taskDefinition=revision, desiredCount=desired
        )
        wait_for_revision(ecs, cluster, name, revision, desired)
    except Exception as release_error:
        try:
            rollback_service(ecs, cluster, previous, after_rollback=after_rollback)
        except Exception as rollback_error:
            raise ExceptionGroup(
                "Deployment and rollback failed", [release_error, rollback_error]
            ) from release_error
        raise
    return previous


def rollback_service(ecs, cluster, previous, *, after_rollback=None):
    name = previous["serviceName"]
    print(f"Rolling back {name} to {previous['taskDefinition']}", flush=True)
    ecs.update_service(
        cluster=cluster,
        service=name,
        taskDefinition=previous["taskDefinition"],
        desiredCount=previous["desiredCount"],
    )
    ecs.get_waiter("services_stable").wait(cluster=cluster, services=[name])
    if after_rollback is not None:
        after_rollback()


def invalidate_frontend(cloudfront, distribution_id, reference):
    invalidation = cloudfront.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": f"{reference}-{time.time_ns()}",
        },
    )
    cloudfront.get_waiter("invalidation_completed").wait(
        DistributionId=distribution_id,
        Id=invalidation["Invalidation"]["Id"],
    )


def check_health(base_url, commit=None, *, attempts=12):
    for attempt in range(attempts):
        try:
            with urlopen(f"{base_url.rstrip('/')}/api/v1/health", timeout=30) as response:
                data = json.load(response)["data"]
            if data["status"] != "ok" or data["checks"]["database"] != "ok":
                raise RuntimeError("Backend/database health check failed")
            if commit is not None and data["version"] != commit:
                raise RuntimeError("Health endpoint is serving a different release")
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(5)


def update_schedule_revision(scheduler, name, revision):
    schedule = scheduler.get_schedule(Name=name, GroupName="default")
    payload = request_fields(scheduler, "UpdateSchedule", schedule)
    payload["Target"]["EcsParameters"]["TaskDefinitionArn"] = revision
    # Preserve state, timezone, role, retry policy, DLQ and all optional settings.
    scheduler.update_schedule(**payload)
    return request_fields(scheduler, "UpdateSchedule", schedule)


def run_bootstrap(ecs, config, revision):
    response = ecs.run_task(
        cluster=config["cluster"],
        taskDefinition=revision,
        launchType="FARGATE",
        networkConfiguration=config["job_network"],
        count=1,
        platformVersion="1.4.0",
    )
    if response.get("failures") or len(response.get("tasks", [])) != 1:
        raise RuntimeError("Database bootstrap task could not start")
    task = response["tasks"][0]["taskArn"]
    print(f"Bootstrap task: {task}", flush=True)
    ecs.get_waiter("tasks_stopped").wait(
        cluster=config["cluster"],
        tasks=[task],
        WaiterConfig={"Delay": 6, "MaxAttempts": 100},
    )
    result = ecs.describe_tasks(cluster=config["cluster"], tasks=[task])["tasks"][0]
    containers = result.get("containers", [])
    if not containers or any(c.get("exitCode") != 0 for c in containers):
        raise RuntimeError(f"Bootstrap failed; inspect CloudWatch logs for {task}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=os.getenv("DEPLOY_CONFIG_PATH"), required=False)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--component",
        choices=["all", "backend", "frontend", "bootstrap"],
        default="all",
    )
    args = parser.parse_args()
    if not args.config or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("--config and a full lowercase 40-character --commit SHA are required")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (
        actual != args.commit
        or subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        ).strip()
    ):
        parser.error("Deploy from a clean checkout of the requested commit")
    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    session = boto3.Session(region_name=config["region"])
    ecs, ecr = session.client("ecs"), session.client("ecr")
    scheduler = session.client("scheduler")
    components = ["backend", "frontend"] if args.component == "all" else [args.component]
    if args.component == "bootstrap":
        backend = config["services"]["backend"]
        image = image_for_commit(ecr, backend["repository"], args.commit, "backend")
        job = config["jobs"]["database-bootstrap"]
        revision = register_image(ecs, job["family"], job["container"], image, args.commit)
        run_bootstrap(ecs, config, revision)
        return
    previous_services = []
    previous_schedules = []
    backend_image = None
    try:
        for component in components:
            service = config["services"][component]
            image = image_for_commit(ecr, service["repository"], args.commit, component)
            revision = register_image(ecs, service["family"], component, image, args.commit)
            after_rollback = None
            if component == "frontend":
                after_rollback = partial(
                    invalidate_frontend,
                    session.client("cloudfront"),
                    config["cloudfront_distribution_id"],
                    f"{args.commit}-rollback",
                )
            previous = deploy_service(
                ecs,
                config["cluster"],
                service["name"],
                revision,
                after_rollback=after_rollback,
            )
            previous_services.append((previous, after_rollback))
            print(f"{component}: {image} -> {revision}", flush=True)
            if component == "backend":
                backend_image = image
                check_health(config["base_url"], args.commit)
        if "frontend" in components:
            invalidate_frontend(
                session.client("cloudfront"), config["cloudfront_distribution_id"], args.commit
            )
            with urlopen(config["base_url"], timeout=30) as response:
                if response.status != 200 or "text/html" not in response.headers.get(
                    "Content-Type", ""
                ):
                    raise RuntimeError("Frontend smoke check failed")
        if backend_image:
            for job in config["jobs"].values():
                if "schedule" in job:
                    revision = register_image(
                        ecs, job["family"], job["container"], backend_image, args.commit
                    )
                    previous_schedules.append(
                        update_schedule_revision(scheduler, job["schedule"], revision)
                    )
    except Exception as release_error:
        errors = [release_error]
        for previous in reversed(previous_schedules):
            try:
                scheduler.update_schedule(**previous)
            except Exception as error:
                errors.append(error)
        for previous, after_rollback in reversed(previous_services):
            try:
                rollback_service(ecs, config["cluster"], previous, after_rollback=after_rollback)
            except Exception as error:
                errors.append(error)
        if len(errors) > 1:
            raise ExceptionGroup("Release failed with rollback errors", errors) from release_error
        raise
    print("Deployment and smoke checks passed.", flush=True)


if __name__ == "__main__":
    main()
