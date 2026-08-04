"""
Response objects for the thin Clerk HTTP client.

Clerk API responses are plain JSON, but the call sites in this package were
written against the official SDK's pydantic models and reach into them with
``getattr``. ``getattr`` on a plain dict returns the default, so decoding
straight to dicts would make call sites such as
``getattr(email_obj, "email_address", None)`` silently return ``None`` instead
of failing loudly.

``ClerkObject`` bridges that gap: it is both attribute-accessible and a real
``Mapping``, and it converts nested values on access. Supporting both shapes
keeps the existing helpers working unchanged, including ``_get_value`` and
``_plain_data`` in ``server_api``, which branch on ``isinstance(value, Mapping)``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

__all__ = ["ClerkObject", "clerk_value", "to_plain_data"]


def clerk_value(value: Any) -> Any:
    """Wrap mappings as :class:`ClerkObject` and recurse through sequences.

    Scalars, strings, and bytes are returned unchanged.
    """
    if isinstance(value, ClerkObject):
        return value
    if isinstance(value, Mapping):
        return ClerkObject(value)
    if isinstance(value, list | tuple):
        return [clerk_value(item) for item in value]
    return value


def to_plain_data(value: Any) -> Any:
    """Convert a :class:`ClerkObject` tree back into plain dicts and lists."""
    if isinstance(value, Mapping):
        return {key: to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_plain_data(item) for item in value]
    return value


class ClerkObject(Mapping):
    """An attribute- and mapping-accessible view over a Clerk JSON object.

    Both access styles read the same underlying data::

        user.email_addresses[0].email_address
        user["email_addresses"][0]["email_address"]

    Nested mappings and lists are converted on access rather than up front, so
    decoding a large list response does not walk every branch of every item.

    Note that real attributes win over data keys. A response field named
    ``get``, ``keys``, ``items``, or ``values`` is reachable only through
    subscripting, because ``__getattr__`` is consulted only after normal
    attribute lookup fails and those names resolve to ``Mapping`` methods.
    Clerk does not currently return fields with those names.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        object.__setattr__(self, "_data", dict(data or {}))

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails, so this never
        # shadows Mapping's own methods.
        try:
            raw = self._data[name]
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__!s} has no attribute {name!r}"
            ) from None
        return clerk_value(raw)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            f"{type(self).__name__!s} is read-only; cannot set {name!r}"
        )

    def __delattr__(self, name: str) -> None:
        raise AttributeError(
            f"{type(self).__name__!s} is read-only; cannot delete {name!r}"
        )

    def __getitem__(self, key: str) -> Any:
        return clerk_value(self._data[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __dir__(self) -> list[str]:
        return sorted({*super().__dir__(), *self._data})

    def to_dict(self) -> dict[str, Any]:
        """Return a deep copy of the underlying data as plain Python values."""
        return to_plain_data(self)

    # ``server_api._plain_data`` prefers ``model_dump`` when it is callable,
    # which keeps this object interchangeable with the SDK's pydantic models.
    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Mirror the SDK's pydantic ``model_dump`` for drop-in compatibility."""
        exclude_none = kwargs.get("exclude_none", False)
        data = self.to_dict()
        if exclude_none:
            data = _drop_none(data)
        return data

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._data!r})"


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_none(item) for key, item in value.items() if item is not None
        }
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value
