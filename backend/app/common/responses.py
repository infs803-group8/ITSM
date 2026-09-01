"""Common API response model."""

from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    data: T
