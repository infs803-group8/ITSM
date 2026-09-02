from pathlib import Path
from uuid import UUID

import yaml
from openapi_spec_validator import validate

from app.main import app

EXPECTED = {
    "/api/v1/health": "api01Health",
    "/api/v1/tickets/{id}/attachments/presign": "api02CreateAttachmentUpload",
    "/api/v1/tickets/{id}/attachments/complete": "api03CompleteAttachmentUpload",
    "/api/v1/tickets/{id}/attachments": "api04ListAttachments",
    "/api/v1/tickets/{id}/attachments/{attachment_id}/download": (
        "api05GetAttachmentDownload"
    ),
    "/api/v1/dashboard/summary": "api06DashboardSummary",
    "/api/v1/dashboard/overdue-tickets": "api07OverdueTickets",
}


def test_checked_in_openapi_contract_is_valid():
    contract_path = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.yaml"
    with contract_path.open(encoding="utf-8") as source:
        validate(yaml.safe_load(source))


def test_member_a_runtime_routes_match_frozen_operation_ids():
    paths = app.openapi()["paths"]
    actual = {
        path: operation["operationId"]
        for path, methods in paths.items()
        for operation in methods.values()
        if isinstance(operation, dict)
        and operation.get("operationId") in EXPECTED.values()
    }
    assert actual == EXPECTED


def test_invalid_request_id_uses_error_envelope(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "not-a-uuid"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert UUID(response.headers["X-Request-ID"])
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_attachment_route_requires_authentication_before_storage(client):
    response = client.get("/api/v1/tickets/1/attachments")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["X-Request-ID"]
