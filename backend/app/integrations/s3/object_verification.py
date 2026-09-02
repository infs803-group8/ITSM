"""S3 object verification values and storage exceptions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    content_type: str


class ObjectNotReadyError(Exception):
    """The expected S3 key is not visible yet."""


class ObjectStorageError(Exception):
    """S3 failed for a reason that should not be exposed to the caller."""
