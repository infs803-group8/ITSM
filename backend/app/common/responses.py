"""Common API success and error models."""

from typing import Any

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    data: T


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any]
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
