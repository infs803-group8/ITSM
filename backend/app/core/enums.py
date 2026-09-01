"""Shared API enums."""

from enum import StrEnum


class UserRole(StrEnum):
    END_USER = "END_USER"
    SERVICE_DESK = "SERVICE_DESK"
    TIER_2 = "TIER_2"
    VENDOR = "VENDOR"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
