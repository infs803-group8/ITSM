"""API-01 platform response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthChecks(BaseModel):
    database: Literal["ok"]


class HealthData(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    timestamp: datetime
    checks: HealthChecks


class HealthResponse(BaseModel):
    data: HealthData
