"""Application-wide exception responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import ApplicationError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(_request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
