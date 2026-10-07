from pathlib import Path

import yaml

from app.main import app


def test_api_12_to_20_routes_use_frozen_paths_and_operation_ids():
    operations = {
        (method.upper(), path): operation.get("operationId")
        for path, path_item in app.openapi()["paths"].items()
        for method, operation in path_item.items()
        if method.lower() in {"get", "post", "patch"}
    }
    assert operations[("GET", "/api/v1/reference-data")] == "api12ReferenceData"
    assert operations[("GET", "/api/v1/users/assignees")] == "api13ListAssignees"
    assert operations[("GET", "/api/v1/vendors")] == "api14ListVendors"
    assert operations[("POST", "/api/v1/tickets")] == "api15CreateTicket"
    assert operations[("GET", "/api/v1/tickets")] == "api16ListTickets"
    assert operations[("GET", "/api/v1/tickets/{id}")] == "api17GetTicket"
    assert operations[("GET", "/api/v1/tickets/{id}/vendor-requests")] == (
        "api33ListVendorRequestHistory"
    )
    assert operations[("PATCH", "/api/v1/tickets/{id}")] == "api18UpdateTicket"
    assert operations[("GET", "/api/v1/tickets/{id}/comments")] == "api19ListComments"
    assert operations[("POST", "/api/v1/tickets/{id}/comments")] == "api20CreateComment"


def test_member_b_write_models_forbid_additional_fields():
    schemas = app.openapi()["components"]["schemas"]
    for name in ("TicketCreateRequest", "TicketUpdateRequest", "CommentCreateRequest"):
        assert schemas[name]["additionalProperties"] is False


def test_api_33_checked_in_contract_has_history_schema_and_example():
    contract_path = Path(__file__).resolve().parents[3] / "backend" / "contracts" / "openapi.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    operation = contract["paths"]["/tickets/{id}/vendor-requests"]["get"]

    assert operation["operationId"] == "api33ListVendorRequestHistory"
    assert operation["x-api-id"] == "API-33"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/VendorRequestHistoryResponse"
    }
    example = contract["components"]["examples"]["API33Success"]["value"]["data"]
    assert example[0]["response"]["message"]
    assert example[1]["status"] == "CANCELLED"
    assert example[1]["response"] is None

