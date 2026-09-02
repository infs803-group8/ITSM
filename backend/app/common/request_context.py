"""Authenticated request identity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    user_id: int
    role: str
    vendor_org_id: int | None = None
