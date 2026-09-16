"""Application-wide contract-shaped exception responses."""

import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.request_id import error_payload
from app.core.errors import ApplicationError

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", uuid4()))


def _classify_validation_error(errors: list[dict], *, path: str) -> tuple[int, str, str]:
    """Map a FastAPI/pydantic ``RequestValidationError``'s ``.errors()``
    list to this API's own contract-shaped (status, ErrorCode, message)
    triple, instead of always falling back to the generic
    ``VALIDATION_ERROR``.

    Pulled out of ``validation_error_handler`` as its own plain function
    (C035-fix) purely so it can be unit-tested directly -- with no
    ``Request``/``RequestValidationError``/FastAPI app object needed --
    rather than only through an HTTP-level contract test. Behaviour is
    unchanged from the inline version this replaces.
    """
    size_too_large = any(
        error.get("type") == "less_than_equal" and error.get("loc", ())[-1:] == ("size_bytes",)
        for error in errors
    )
    unsupported_content_type = any(
        error.get("type") == "enum" and error.get("loc", ())[-1:] == ("content_type",)
        for error in errors
    )
    missing_or_false_close_acknowledgement = path.endswith("/close") and any(
        error.get("loc", ())[-1:] == ("acknowledge",)
        and error.get("type") in {"missing", "literal_error", "bool_parsing", "bool_type"}
        for error in errors
    )
    if size_too_large:
        return 413, "ATTACHMENT_TOO_LARGE", "The attachment exceeds the 10 MiB limit."
    if unsupported_content_type:
        return 422, "UNSUPPORTED_ATTACHMENT_TYPE", "The attachment content type is not supported."
    if missing_or_false_close_acknowledgement:
        # C034.02 / Q07: a missing or false ``acknowledge`` on
        # POST /tickets/{id}/close must surface as this specific code,
        # not be swallowed by the generic VALIDATION_ERROR fallback --
        # same precedent as the two attachment-specific branches above.
        # Path-scoped (unlike those two) purely as an extra safety
        # margin, since "acknowledge" is currently unique to
        # CloseRequest but a future schema could reuse the field name.
        return (
            422,
            "CLOSE_ACKNOWLEDGEMENT_REQUIRED",
            "Acknowledgement is required to close this ticket.",
        )
    return 422, "VALIDATION_ERROR", "The request did not pass validation."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(_request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(_request),
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = exc.errors()
        status_code, code, message = _classify_validation_error(errors, path=request.url.path)
        fields = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "Invalid value."),
            }
            for error in errors
        ]
        return JSONResponse(
            status_code=status_code,
            content=error_payload(
                code=code,
                message=message,
                request_id=_request_id(request),
                details={"fields": fields},
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        error_details = {
            401: ("AUTHENTICATION_REQUIRED", "Authentication is required."),
            403: ("DATA_SCOPE_DENIED", "Permission is denied."),
            404: ("RESOURCE_NOT_FOUND", "The requested resource was not found."),
        }
        code, message = error_details.get(
            exc.status_code,
            ("INVALID_REQUEST", "The request could not be completed."),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=code,
                message=message,
                request_id=_request_id(request),
            ),
            headers=exc.headers,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.exception("Database operation failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content=error_payload(
                code="SERVICE_UNAVAILABLE",
                message="A required service is temporarily unavailable.",
                request_id=_request_id(request),
            ),
        )
