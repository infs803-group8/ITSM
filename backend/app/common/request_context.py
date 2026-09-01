"""Authenticated request identity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    user_id: int
    role: str
