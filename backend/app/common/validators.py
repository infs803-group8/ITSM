"""Reusable validation helpers."""


def require_non_blank(value: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError("value must not be blank")
    return result
