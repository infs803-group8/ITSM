"""Unit tests for app.domains.workflow.error_mapping (C024+).

Pure -- imports only app.core.errors.ApplicationError, no SQLAlchemy -- so
actually executed via this project's pytest-shim convention.
"""

from app.domains.workflow.error_mapping import error_for_denial


def test_known_denial_codes_map_to_the_documented_public_error_and_status():
    cases = [
        ("ROLE_NOT_PERMITTED", "DATA_SCOPE_DENIED", 403),
        ("NOT_TICKET_ASSIGNEE", "DATA_SCOPE_DENIED", 403),
        ("NOT_TICKET_REQUESTER", "DATA_SCOPE_DENIED", 403),
        ("VENDOR_ORG_MISMATCH", "DATA_SCOPE_DENIED", 403),
        ("TARGET_ASSIGNEE_NOT_ELIGIBLE", "ASSIGNEE_NOT_ELIGIBLE", 422),
        ("INVALID_STATUS_TRANSITION", "INVALID_STATUS_TRANSITION", 409),
        ("TICKET_CLOSED", "TICKET_CLOSED", 409),
        ("VENDOR_REQUEST_ALREADY_ACTIVE", "ACTIVE_VENDOR_REQUEST_EXISTS", 409),
        ("NO_ACTIVE_VENDOR_REQUEST", "NO_ACTIVE_VENDOR_REQUEST", 409),
    ]
    for denial_code, expected_error, expected_status in cases:
        error = error_for_denial(denial_code, "some message")
        assert error.code == expected_error
        assert error.status_code == expected_status
        assert error.message == "some message"


def test_unknown_denial_code_falls_back_to_generic_422():
    error = error_for_denial("SOMETHING_NEW", "explain")
    assert error.code == "INVALID_REQUEST"
    assert error.status_code == 422
    assert error.message == "explain"


def test_missing_message_gets_a_generic_fallback_message():
    error = error_for_denial("TICKET_CLOSED", None)
    assert error.message == "The request could not be completed."
