"""Correlation ID middleware required by the public API contract."""

from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response


def error_payload(
    *,
    code: str,
    message: str,
    request_id: str,
    details: dict | None = None,
) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }


async def add_request_id(request: Request, call_next) -> Response:
    supplied = request.headers.get("X-Request-ID")
    try:
        request_id = str(UUID(supplied)) if supplied else str(uuid4())
    except ValueError:
        request_id = str(uuid4())
        response = JSONResponse(
            status_code=422,
            content=error_payload(
                code="VALIDATION_ERROR",
                message="X-Request-ID must be a valid UUID.",
                request_id=request_id,
                details={"field": "X-Request-ID"},
            ),
        )
        response.headers["X-Request-ID"] = request_id
        return response

    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
