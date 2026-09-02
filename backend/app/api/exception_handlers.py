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
        size_too_large = any(
            error.get("type") == "less_than_equal"
            and error.get("loc", ())[-1:] == ("size_bytes",)
            for error in errors
        )
        unsupported_content_type = any(
            error.get("type") == "enum"
            and error.get("loc", ())[-1:] == ("content_type",)
            for error in errors
        )
        if size_too_large:
            status_code, code, message = (
                413,
                "ATTACHMENT_TOO_LARGE",
                "The attachment exceeds the 10 MiB limit.",
            )
        elif unsupported_content_type:
            status_code, code, message = (
                422,
                "UNSUPPORTED_ATTACHMENT_TYPE",
                "The attachment content type is not supported.",
            )
        else:
            status_code, code, message = (
                422,
                "VALIDATION_ERROR",
                "The request did not pass validation.",
            )
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
