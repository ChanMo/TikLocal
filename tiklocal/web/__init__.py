"""Web route registration and shared request parsing."""

from flask import request


def read_int_arg(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = request.args.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value

