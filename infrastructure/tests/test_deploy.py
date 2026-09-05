import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

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
