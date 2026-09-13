"""Translate state_machine.py's internal denial codes into the public API's
ErrorCode + HTTP status (needed by every write-path handler from C024 on,
so it lives once here rather than being redefined per endpoint).

state_machine.py's denial-code vocabulary (C016) was written to be
self-consistent for its own pure-logic tests, and two of its strings do
not literally match docs/api/openapi.yaml's ``ErrorCode`` enum:
``TARGET_ASSIGNEE_NOT_ELIGIBLE`` (public: ``ASSIGNEE_NOT_ELIGIBLE``) and
``VENDOR_REQUEST_ALREADY_ACTIVE`` (public: ``ACTIVE_VENDOR_REQUEST_EXISTS``).
Rather than editing state_machine.py -- already the base of the whole C16
through C23 branch stack, so a change there would force rebasing every
descendant branch -- this module is the single translation point every
write-path service imports.
"""

from app.core.errors import ApplicationError

# denial_code -> (public ErrorCode, HTTP status)
_DENIAL_TO_ERROR: dict[str, tuple[str, int]] = {
    "ROLE_NOT_PERMITTED": ("DATA_SCOPE_DENIED", 403),
    "NOT_TICKET_ASSIGNEE": ("DATA_SCOPE_DENIED", 403),
    "NOT_TICKET_REQUESTER": ("DATA_SCOPE_DENIED", 403),
    "VENDOR_ORG_MISMATCH": ("DATA_SCOPE_DENIED", 403),
    "TARGET_ASSIGNEE_NOT_ELIGIBLE": ("ASSIGNEE_NOT_ELIGIBLE", 422),
    "INVALID_STATUS_TRANSITION": ("INVALID_STATUS_TRANSITION", 409),
    "TICKET_CLOSED": ("TICKET_CLOSED", 409),
    "VENDOR_REQUEST_ALREADY_ACTIVE": ("ACTIVE_VENDOR_REQUEST_EXISTS", 409),
    "NO_ACTIVE_VENDOR_REQUEST": ("NO_ACTIVE_VENDOR_REQUEST", 409),
}


def error_for_denial(denial_code: str | None, denial_message: str | None) -> ApplicationError:
    """Build the ``ApplicationError`` a router should raise for a denied
    ``state_machine.TransitionResult``. An unrecognised code (should never
    happen for a code this module doesn't yet know about -- a future
    action handler introducing a new denial code without registering it
    here is a bug to fix in this table, not to paper over silently) falls
    back to a generic 422 rather than crashing the request.
    """
    error_code, status_code = _DENIAL_TO_ERROR.get(denial_code or "", ("INVALID_REQUEST", 422))
    return ApplicationError(error_code, denial_message or "The request could not be completed.", status_code)
