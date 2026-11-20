"""Turn the :mod:`inodefence.app` records into JSON-ready values, recomputing nothing.

One rule, applied recursively: an :class:`~enum.Enum` becomes its value, a
:class:`~pathlib.Path` its string, a dataclass a dict of its fields, a mapping a dict, a
tuple/list a list, and ``None``/``bool``/``int``/``float``/``str`` pass through. ``None`` is never
turned into ``0`` or ``""`` -- "unknown" stays distinct from "zero" everywhere (the read model's
contract). Only declared dataclass *fields* are emitted; computed ``@property`` values are added
explicitly by the route that wants them, never inferred here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


def to_jsonable(obj: Any) -> Any:
    """A JSON-serialisable copy of ``obj`` (see the module docstring for the rules)."""
    if obj is None or isinstance(obj, bool | int | float | str):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Mapping):
        return {str(key): to_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [to_jsonable(value) for value in obj]
    return str(obj)


__all__ = ["to_jsonable"]
