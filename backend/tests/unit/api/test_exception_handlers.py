"""Unit tests for app.api.exception_handlers._classify_validation_error
(C034 fix, filed under C035's stack since it was caught while starting
C035).

Imports app.api.exception_handlers, which imports fastapi at module
level -- fastapi is confirmed absent from this sandbox (see the module
docstring on _classify_validation_error), so syntax-checked only
(py_compile), not executed.
"""

from app.api.exception_handlers import _classify_validation_error

CLOSE_PATH = "/tickets/501/close"
OTHER_PATH = "/tickets/501/resolve"


def missing_field_error(field: str) -> dict:
    return {"type": "missing", "loc": ("body", field), "msg": "Field required"}


def literal_error(field: str) -> dict:
    return {
        "type": "literal_error",
        "loc": ("body", field),
        "msg": "Input should be True",
    }


def test_a_missing_acknowledge_on_close_maps_to_the_specific_code():
    status_code, code, message = _classify_validation_error(
        [missing_field_error("acknowledge")], path=CLOSE_PATH
    )
    assert status_code == 422
    assert code == "CLOSE_ACKNOWLEDGEMENT_REQUIRED"
    assert "acknowledge" in message.lower() or "close" in message.lower()


def test_a_false_acknowledge_on_close_maps_to_the_specific_code():
    """``Literal[True]`` rejects ``false`` as a literal_error, not a
    bool_type/bool_parsing error -- pydantic v2 already knows it parsed a
    valid bool, it just isn't the one literal value allowed.
    """
    status_code, code, message = _classify_validation_error(
        [literal_error("acknowledge")], path=CLOSE_PATH
    )
    assert code == "CLOSE_ACKNOWLEDGEMENT_REQUIRED"
    assert status_code == 422


def test_a_non_bool_acknowledge_on_close_also_maps_to_the_specific_code():
    error = {
        "type": "bool_type",
        "loc": ("body", "acknowledge"),
        "msg": "Input should be a valid boolean",
    }
    status_code, code, message = _classify_validation_error([error], path=CLOSE_PATH)
    assert code == "CLOSE_ACKNOWLEDGEMENT_REQUIRED"


def test_other_close_validation_errors_are_not_reclassified():
    """A structural error on some other field of the same request (e.g.
    ``reason`` too long) must NOT be swallowed into
    CLOSE_ACKNOWLEDGEMENT_REQUIRED -- only errors actually on
    ``acknowledge`` trigger the specific code (C034.02's own wording:
    "其他结构错误用既定 Validation Error，不把所有 422 都映射成关闭确认错误")."""
    error = {
        "type": "string_too_long",
        "loc": ("body", "reason"),
        "msg": "String should have at most 1000 characters",
    }
    status_code, code, message = _classify_validation_error([error], path=CLOSE_PATH)
    assert code == "VALIDATION_ERROR"
    assert status_code == 422


def test_an_acknowledge_shaped_error_on_a_different_endpoint_is_not_reclassified():
    """Path-scoped defensively: the same error shape on a hypothetical
    future endpoint that is not /close must fall through to the generic
    VALIDATION_ERROR rather than silently borrowing Close's error code.
    """
    status_code, code, message = _classify_validation_error(
        [missing_field_error("acknowledge")], path=OTHER_PATH
    )
    assert code == "VALIDATION_ERROR"


def test_a_request_with_no_errors_falls_back_to_generic_validation_error():
    status_code, code, message = _classify_validation_error([], path=CLOSE_PATH)
    assert (status_code, code) == (422, "VALIDATION_ERROR")


def test_the_two_pre_existing_attachment_branches_are_unaffected():
    """Regression guard for the refactor that pulled this function out of
    the inline handler body -- behaviour for the two branches C034's fix
    did not touch must be exactly what it was before.
    """
    size_error = {"type": "less_than_equal", "loc": ("body", "size_bytes"), "msg": "..."}
    assert _classify_validation_error([size_error], path="/attachments/upload-sessions") == (
        413,
        "ATTACHMENT_TOO_LARGE",
        "The attachment exceeds the 10 MiB limit.",
    )

    content_type_error = {"type": "enum", "loc": ("body", "content_type"), "msg": "..."}
    status_code, code, _message = _classify_validation_error(
        [content_type_error], path="/attachments/upload-sessions"
    )
    assert (status_code, code) == (422, "UNSUPPORTED_ATTACHMENT_TYPE")
