import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("manual_release", SCRIPTS / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

SHA = "a" * 40
REPO = "256329410824.dkr.ecr.ap-southeast-2.amazonaws.com/shared"
CONFIG = {
    "region": "ap-southeast-2",
    "account_id": "256329410824",
    "cluster": "cluster",
    "base_url": "https://example.invalid",
    "cloudfront_distribution_id": "distribution",
    "services": {
        component: {"name": component, "repository": REPO} for component in ("frontend", "backend")
    },
    "jobs": {
        "cleanup": {"container": "attachment-cleanup", "schedule": "cleanup"},
        "sla": {"container": "sla-monitor", "schedule": "sla"},
    },
}


def env(attempt="1"):
    return {
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": SHA,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": attempt,
    }


def test_shared_repository_tags_do_not_collide_between_components_or_retries():
    tags = {
        release.prepare(c, "build-only", "", CONFIG, env(a))["image_tag"]
        for c in ("frontend", "backend")
        for a in ("1", "2")
    }
    assert len(tags) == 4


@pytest.mark.parametrize(
    "tag",
    [
        f"backend-{SHA}-123-1",
        "frontend-latest",
        f"frontend-{SHA}-x\nmalicious=value",
        f"frontend-{SHA}-$(id)",
    ],
)
def test_rejects_wrong_component_and_unsafe_existing_tags(tag):
    with pytest.raises(ValueError):
        release.prepare("frontend", "deploy-existing", tag, CONFIG, env())


def test_existing_image_uses_original_commit_not_workflow_commit():
    old = "b" * 40
    values = release.prepare("frontend", "deploy-existing", f"frontend-{old}-opt1", CONFIG, env())
    assert values["source_sha"] == old


def test_rejects_non_main_and_ignored_build_tag():
    with pytest.raises(ValueError, match="main"):
        release.prepare(
            "frontend", "build-only", "", CONFIG, {**env(), "GITHUB_REF": "refs/heads/dev"}
        )
    with pytest.raises(ValueError, match="empty"):
        release.prepare("frontend", "build-only", "existing", CONFIG, env())


def test_image_resolution_requires_immutable_correct_repository():
    ecr = Mock()
    ecr.describe_repositories.return_value = {
        "repositories": [{"repositoryUri": REPO, "imageTagMutability": "IMMUTABLE"}]
    }
    ecr.describe_images.return_value = {"imageDetails": [{"imageDigest": "sha256:" + "c" * 64}]}
    image, commit = release.resolve_image(ecr, REPO, "frontend", f"frontend-{SHA}-123-1")
    assert image == REPO + "@sha256:" + "c" * 64
    assert commit == SHA
    ecr.describe_repositories.return_value["repositories"][0]["imageTagMutability"] = "MUTABLE"
    with pytest.raises(RuntimeError, match="immutable"):
        release.resolve_image(ecr, REPO, "frontend", f"frontend-{SHA}-123-1")


@pytest.fixture
def context(monkeypatch):
    clients = {name: Mock() for name in ("ecs", "ecr", "cloudfront", "scheduler")}
    session = Mock()
    session.client.side_effect = clients.__getitem__
    monkeypatch.setattr(release, "resolve_image", Mock(return_value=(REPO + "@sha256:new", SHA)))
    previous = {
        "serviceName": "backend",
        "taskDefinition": "current:7",
        "desiredCount": 1,
        "deployments": [{"rolloutState": "COMPLETED"}],
    }
    monkeypatch.setattr(release.deploy, "read_service", Mock(return_value=previous))
    monkeypatch.setattr(release.deploy, "register_image", Mock(return_value="new:8"))
    monkeypatch.setattr(release.deploy, "deploy_service", Mock(return_value=previous))
    monkeypatch.setattr(release.deploy, "wait_for_revision", Mock())
    monkeypatch.setattr(release.deploy, "check_health", Mock())
    monkeypatch.setattr(release.deploy, "rollback_service", Mock())
    monkeypatch.setattr(release.deploy, "invalidate_frontend", Mock())
    monkeypatch.setattr(
        release.deploy,
        "request_fields",
        lambda client, operation, value: json.loads(json.dumps(value)),
    )
    return session, clients, previous


def test_build_only_does_not_update_services_or_schedules(context):
    session, clients, _ = context
    release.release(session, CONFIG, "frontend", f"frontend-{SHA}-123-1", False)
    release.deploy.read_service.assert_not_called()
    release.deploy.deploy_service.assert_not_called()
    clients["scheduler"].update_schedule.assert_not_called()


def test_frontend_uses_current_revision_and_never_updates_backend_jobs(context, monkeypatch):
    session, clients, _ = context
    response = MagicMock()
    response.__enter__.return_value.status = 200
    response.__enter__.return_value.headers = {"Content-Type": "text/html"}
    monkeypatch.setattr(release, "urlopen", Mock(return_value=response))
    release.release(session, CONFIG, "frontend", f"frontend-{SHA}-123-1", True)
    assert release.deploy.register_image.call_args.args[1:3] == ("current:7", "frontend")
    assert release.deploy.deploy_service.call_args.args[2] == "frontend"
    clients["scheduler"].update_schedule.assert_not_called()
    release.deploy.wait_for_revision.assert_called_once()


def test_rejects_external_deployment_in_progress(context):
    session, _, previous = context
    previous["deployments"][0]["rolloutState"] = "IN_PROGRESS"
    with pytest.raises(RuntimeError, match="Another ECS deployment"):
        release.release(session, CONFIG, "backend", f"backend-{SHA}-123-1", True)
    release.deploy.register_image.assert_not_called()


def test_backend_schedule_failure_restores_original_schedules_and_service(context):
    session, clients, previous = context
    scheduler = clients["scheduler"]
    originals = [
        {
            "Name": name,
            "State": "DISABLED",
            "Target": {
                "RoleArn": "scheduler-role",
                "EcsParameters": {"TaskDefinitionArn": f"{name}:3"},
            },
        }
        for name in ("cleanup", "sla")
    ]
    scheduler.get_schedule.side_effect = originals
    scheduler.update_schedule.side_effect = [None, RuntimeError("lost response"), None, None]
    with pytest.raises(RuntimeError, match="lost response"):
        release.release(session, CONFIG, "backend", f"backend-{SHA}-123-1", True)
    calls = scheduler.update_schedule.call_args_list
    assert calls[0].kwargs["State"] == "DISABLED"
    assert calls[2].kwargs == originals[1]
    assert calls[3].kwargs == originals[0]
    release.deploy.rollback_service.assert_called_once_with(
        clients["ecs"], "cluster", previous, after_rollback=None
    )


def test_frontend_smoke_failure_rolls_back_and_refreshes_cache(context, monkeypatch):
    session, clients, _ = context
    monkeypatch.setattr(release, "urlopen", Mock(side_effect=OSError("unreachable")))
    with pytest.raises(OSError):
        release.release(session, CONFIG, "frontend", f"frontend-{SHA}-123-1", True)
    callback = release.deploy.rollback_service.call_args.kwargs["after_rollback"]
    callback()
    assert release.deploy.invalidate_frontend.call_args.args == (
        clients["cloudfront"],
        "distribution",
        f"{SHA}-rollback",
    )


def test_original_local_deployer_namespaces_shared_repository_tags(monkeypatch):
    ecr = Mock()
    ecr.describe_images.return_value = {"imageDetails": [{"imageDigest": "sha256:existing"}]}
    process = Mock()
    monkeypatch.setattr(release.deploy.subprocess, "run", process)
    for component in ("frontend", "backend"):
        release.deploy.image_for_commit(ecr, REPO, SHA, component)
        assert ecr.describe_images.call_args.kwargs["imageIds"] == [
            {"imageTag": f"{component}-{SHA}"}
        ]
    process.assert_not_called()
