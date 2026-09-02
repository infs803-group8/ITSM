"""UTC time provider."""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Treat MySQL DATETIME values as UTC and return an aware value."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def as_mysql_utc(value: datetime) -> datetime:
    """Convert an aware timestamp to the naive UTC representation stored by MySQL."""
    return value.astimezone(UTC).replace(tzinfo=None)
