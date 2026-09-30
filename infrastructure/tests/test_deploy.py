import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

spec = importlib.util.spec_from_file_location(
    "deploy", Path(__file__).resolve().parents[1] / "scripts" / "deploy.py"
)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def aws_client(service):
    return boto3.client(
        service,
        region_name="ap-southeast-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def test_register_revision_preserves_roles_secrets_and_commands():
    ecs = aws_client("ecs")
    role = "arn:aws:iam::123456789012:role/test-role"
    definition = {
        "family": "backend",
        "revision": 1,
        "status": "ACTIVE",
        "taskDefinitionArn": "arn:aws:ecs:ap-southeast-2:123456789012:task-definition/backend:1",
        "networkMode": "awsvpc",
        "executionRoleArn": role,
        "taskRoleArn": role,
        "requiresCompatibilities": ["FARGATE"],
        "cpu": "256",
        "memory": "512",
        "containerDefinitions": [
            {
                "name": "backend",
                "image": "old",
                "command": ["uvicorn", "app.main:app"],
                "secrets": [{"name": "DATABASE_URL", "valueFrom": "database-secret-arn"}],
                "environment": [
                    {"name": "S3_KEY_PREFIX", "value": "attachments"},
                    {"name": "RELEASE_VERSION", "value": "old"},
                ],
            }
        ],
    }
    payload = {
        key: value
        for key, value in definition.items()
        if key not in {"revision", "status", "taskDefinitionArn"}
    }
    payload = json.loads(json.dumps(payload))
    payload["containerDefinitions"][0]["image"] = "repository@sha256:digest"
    payload["containerDefinitions"][0]["environment"][-1]["value"] = "a" * 40
    with Stubber(ecs) as stub:
        stub.add_response(
            "describe_task_definition",
            {"taskDefinition": definition},
            {"taskDefinition": "backend"},
        )
        stub.add_response(
            "register_task_definition",
            {"taskDefinition": {"taskDefinitionArn": "new"}},
            payload,
        )
        assert (
            deploy.register_image(ecs, "backend", "backend", "repository@sha256:digest", "a" * 40)
            == "new"
        )
        stub.assert_no_pending_responses()


def test_schedule_revision_preserves_disabled_state_and_optional_settings():
    scheduler = aws_client("scheduler")
    schedule = {
        "Name": "cleanup",
        "GroupName": "default",
        "State": "DISABLED",
        "ScheduleExpression": "rate(30 minutes)",
        "ScheduleExpressionTimezone": "UTC",
        "Description": "Reviewed cleanup",
        "ActionAfterCompletion": "NONE",
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": {
            "Arn": "arn:aws:ecs:ap-southeast-2:123456789012:cluster/test",
            "RoleArn": "arn:aws:iam::123456789012:role/scheduler",
            "EcsParameters": {"TaskDefinitionArn": "old", "LaunchType": "FARGATE"},
            "RetryPolicy": {"MaximumRetryAttempts": 2},
        },
    }
    updated = json.loads(json.dumps(schedule))
    updated["Target"]["EcsParameters"]["TaskDefinitionArn"] = "new"
    with Stubber(scheduler) as stub:
        stub.add_response("get_schedule", schedule, {"Name": "cleanup", "GroupName": "default"})
        stub.add_response(
            "update_schedule",
            {
                "ScheduleArn": (
                    "arn:aws:scheduler:ap-southeast-2:123456789012:schedule/default/cleanup"
                )
            },
            updated,
        )
        original = deploy.update_schedule_revision(scheduler, "cleanup", "new")
        assert original == schedule
        stub.assert_no_pending_responses()


def test_immutable_image_retry_reuses_existing_digest_without_build(monkeypatch):
    ecr = Mock()
    ecr.describe_images.return_value = {"imageDetails": [{"imageDigest": "sha256:existing"}]}
    process = Mock()
    monkeypatch.setattr(deploy.subprocess, "run", process)
    image = deploy.image_for_commit(
        ecr, "123.dkr.ecr.ap-southeast-2.amazonaws.com/backend", "a" * 40, "backend"
    )
    assert image.endswith("@sha256:existing")
    process.assert_not_called()


def test_ecr_permission_error_does_not_trigger_a_build(monkeypatch):
    ecr = Mock()
    ecr.describe_images.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException"}}, "DescribeImages"
    )
    process = Mock()
    monkeypatch.setattr(deploy.subprocess, "run", process)
    with pytest.raises(ClientError):
        deploy.image_for_commit(ecr, "registry/backend", "a" * 40, "backend")
    process.assert_not_called()


def test_ecs_circuit_breaker_rollback_is_not_reported_as_success():
    ecs = Mock()
    ecs.describe_services.return_value = {
        "services": [
            {
                "status": "ACTIVE",
                "runningCount": 1,
                "deployments": [
                    {
                        "status": "PRIMARY",
                        "taskDefinition": "old",
                        "rolloutState": "COMPLETED",
                    }
                ],
            }
        ]
    }
    with pytest.raises(RuntimeError, match="requested revision"):
        deploy.wait_for_revision(ecs, "cluster", "backend", "new", 1)


def rollout_response(state="IN_PROGRESS", running=1, pending=0):
    return {
        "services": [
            {
                "status": "ACTIVE",
                "runningCount": running,
                "desiredCount": 1,
                "pendingCount": pending,
                "deployments": [
                    {
                        "status": "PRIMARY",
                        "taskDefinition": "new",
                        "rolloutState": state,
                        "rolloutStateReason": "test rollout status",
                    }
                ],
            }
        ]
    }


def test_waiter_can_be_stable_before_rollout_completes(monkeypatch):
    # Exercise the real botocore waiter: one deployment and matching task counts
    # satisfy services_stable even while rolloutState remains IN_PROGRESS.
    ecs = aws_client("ecs")
    sleep = Mock()
    monkeypatch.setattr(deploy.time, "sleep", sleep)
    with Stubber(ecs) as stub:
        for state in ["IN_PROGRESS", "IN_PROGRESS", "COMPLETED"]:
            stub.add_response(
                "describe_services",
                rollout_response(state),
                {"cluster": "cluster", "services": ["backend"]},
            )
        deploy.wait_for_revision(ecs, "cluster", "backend", "new", 1)
        stub.assert_no_pending_responses()
    sleep.assert_called_once()


def test_rollout_failure_after_stability_reports_reason():
    ecs = Mock()
    ecs.describe_services.return_value = rollout_response("FAILED")
    with pytest.raises(RuntimeError, match="FAILED.*test rollout status"):
        deploy.wait_for_revision(ecs, "cluster", "backend", "new", 1)


def test_rollout_confirmation_timeout_is_bounded_and_diagnostic(monkeypatch):
    ecs = Mock()
    ecs.describe_services.return_value = rollout_response()
    monkeypatch.setattr(deploy.time, "monotonic", Mock(side_effect=[0, 901]))
    sleep = Mock()
    monkeypatch.setattr(deploy.time, "sleep", sleep)
    with pytest.raises(RuntimeError, match="Timed out.*IN_PROGRESS"):
        deploy.wait_for_revision(ecs, "cluster", "backend", "new", 1)
    sleep.assert_not_called()


def test_rollout_completion_still_requires_stable_task_counts(monkeypatch):
    ecs = Mock()
    ecs.describe_services.side_effect = [
        rollout_response("COMPLETED", running=0, pending=1),
        rollout_response("COMPLETED"),
    ]
    sleep = Mock()
    monkeypatch.setattr(deploy.time, "sleep", sleep)
    deploy.wait_for_revision(ecs, "cluster", "backend", "new", 1)
    sleep.assert_called_once()


def test_service_failure_restores_previous_revision_and_count(monkeypatch):
    ecs = Mock()
    previous = {
        "status": "ACTIVE",
        "serviceName": "backend",
        "taskDefinition": "old",
        "desiredCount": 0,
    }
    ecs.describe_services.return_value = {"services": [previous]}
    monkeypatch.setattr(deploy, "wait_for_revision", Mock(side_effect=RuntimeError("failed")))
    with pytest.raises(RuntimeError, match="failed"):
        deploy.deploy_service(ecs, "cluster", "backend", "new")
    assert ecs.update_service.call_args_list[-1].kwargs == {
        "cluster": "cluster",
        "service": "backend",
        "taskDefinition": "old",
        "desiredCount": 0,
    }


def test_deploy_reports_both_original_and_rollback_failures(monkeypatch):
    ecs = Mock()
    ecs.describe_services.return_value = {
        "services": [
            {
                "status": "ACTIVE",
                "serviceName": "backend",
                "taskDefinition": "old",
                "desiredCount": 1,
            }
        ]
    }
    monkeypatch.setattr(
        deploy, "wait_for_revision", Mock(side_effect=RuntimeError("deploy failed"))
    )
    monkeypatch.setattr(
        deploy, "rollback_service", Mock(side_effect=RuntimeError("rollback failed"))
    )
    with pytest.raises(ExceptionGroup) as raised:
        deploy.deploy_service(ecs, "cluster", "backend", "new")
    assert [str(error) for error in raised.value.exceptions] == [
        "deploy failed",
        "rollback failed",
    ]


@pytest.mark.parametrize(
    "response",
    [
        {"status": "ok"},
        {
            "data": {
                "status": "ok",
                "checks": {"database": "failed"},
                "version": "current",
            }
        },
        {"data": {"status": "ok", "checks": {"database": "ok"}, "version": "old"}},
    ],
)
def test_health_rejects_wrong_envelope_database_or_version(monkeypatch, response):
    monkeypatch.setattr(
        deploy, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(response).encode())
    )
    with pytest.raises((KeyError, RuntimeError)):
        deploy.check_health("https://review.invalid", "current", attempts=1)


def test_health_accepts_current_contract(monkeypatch):
    response = {"data": {"status": "ok", "checks": {"database": "ok"}, "version": "current"}}
    monkeypatch.setattr(
        deploy, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(response).encode())
    )
    deploy.check_health("https://review.invalid", "current", attempts=1)


@pytest.mark.parametrize(
    "containers", [[], [{"exitCode": 1}], [{"reason": "CannotPullContainerError"}]]
)
def test_bootstrap_missing_or_failed_container_is_a_release_failure(containers):
    ecs = Mock()
    ecs.run_task.return_value = {"tasks": [{"taskArn": "task"}]}
    ecs.describe_tasks.return_value = {"tasks": [{"containers": containers}]}
    with pytest.raises(RuntimeError, match="Bootstrap failed"):
        deploy.run_bootstrap(ecs, {"cluster": "cluster", "job_network": {}}, "revision")


@pytest.mark.parametrize("failure", ["scheduler", "frontend_rollout", "rollback_cache"])
def test_release_rollback_refreshes_restored_frontend_cache(monkeypatch, tmp_path, failure):
    commit = "a" * 40
    config = {
        "region": "ap-southeast-2",
        "cluster": "cluster",
        "base_url": "https://review.invalid",
        "cloudfront_distribution_id": "distribution",
        "services": {
            component: {"name": component, "family": component, "repository": component}
            for component in ["backend", "frontend"]
        },
        "jobs": {"cleanup": {"family": "cleanup", "container": "backend", "schedule": "job"}},
    }
    config_path = tmp_path / "deployment.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["deploy.py", "--config", str(config_path), "--commit", commit]
    )
    monkeypatch.setattr(deploy.subprocess, "check_output", Mock(side_effect=[commit, ""]))
    clients = {service: Mock() for service in ["ecs", "ecr", "scheduler", "cloudfront"]}
    session = Mock()
    session.client.side_effect = clients.__getitem__
    monkeypatch.setattr(deploy.boto3, "Session", Mock(return_value=session))
    monkeypatch.setattr(deploy, "image_for_commit", Mock(return_value="repository@sha256:new"))
    monkeypatch.setattr(deploy, "register_image", Mock(return_value="new"))
    monkeypatch.setattr(deploy, "check_health", Mock())
    monkeypatch.setattr(
        deploy, "update_schedule_revision", Mock(side_effect=RuntimeError("schedule failed"))
    )
    html = MagicMock()
    html.__enter__.return_value.status = 200
    html.__enter__.return_value.headers = {"Content-Type": "text/html"}
    monkeypatch.setattr(deploy, "urlopen", Mock(return_value=html))
    ecs, cloudfront = clients["ecs"], clients["cloudfront"]
    ecs.describe_services.side_effect = [
        {
            "services": [
                {
                    "status": "ACTIVE",
                    "serviceName": name,
                    "taskDefinition": "old",
                    "desiredCount": 1,
                }
            ]
        }
        for name in ["backend", "frontend"]
    ]
    events = []
    ecs.update_service.side_effect = lambda **kw: events.append(
        f"update:{kw['service']}:{kw['taskDefinition']}"
    )
    ecs.get_waiter.return_value.wait.side_effect = lambda **kw: events.append(
        f"restored:{kw['services'][0]}"
    )

    def wait_for_revision(ecs, cluster, name, revision, desired):
        if failure == "frontend_rollout" and name == "frontend":
            raise RuntimeError("frontend rollout failed")

    monkeypatch.setattr(deploy, "wait_for_revision", wait_for_revision)

    def create_invalidation(**kwargs):
        assert kwargs["DistributionId"] == "distribution"
        assert kwargs["InvalidationBatch"]["Paths"] == {"Quantity": 1, "Items": ["/*"]}
        reference = kwargs["InvalidationBatch"]["CallerReference"]
        phase = "rollback" if reference.startswith(f"{commit}-rollback-") else "release"
        events.append(f"invalidate:{phase}")
        return {"Invalidation": {"Id": phase}}

    def wait_for_invalidation(**kwargs):
        assert kwargs["DistributionId"] == "distribution"
        events.append(f"cache_ready:{kwargs['Id']}")
        if failure == "rollback_cache" and kwargs["Id"] == "rollback":
            raise RuntimeError("rollback cache failed")

    cloudfront.create_invalidation.side_effect = create_invalidation
    cloudfront.get_waiter.return_value.wait.side_effect = wait_for_invalidation
    if failure == "rollback_cache":
        with pytest.raises(ExceptionGroup) as raised:
            deploy.main()
        assert [str(error) for error in raised.value.exceptions] == [
            "schedule failed",
            "rollback cache failed",
        ]
    else:
        expected_error = (
            "frontend rollout failed" if failure == "frontend_rollout" else "schedule failed"
        )
        with pytest.raises(RuntimeError, match=expected_error):
            deploy.main()
    expected = ["update:backend:new", "update:frontend:new"]
    if failure != "frontend_rollout":
        expected.extend(["invalidate:release", "cache_ready:release"])
    expected.extend(
        [
            "update:frontend:old",
            "restored:frontend",
            "invalidate:rollback",
            "cache_ready:rollback",
            "update:backend:old",
            "restored:backend",
        ]
    )
    assert events == expected
    assert all(
        call.args == ("invalidation_completed",) for call in cloudfront.get_waiter.call_args_list
    )
