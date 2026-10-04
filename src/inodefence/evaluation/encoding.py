"""Strict decoding of the existing canonical model representation."""

import base64
import json
import math
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints, overload


def json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def _object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def read_json(content: bytes) -> object:
    return json.loads(content, object_pairs_hook=_object, parse_constant=_constant)


def object_fields(value: object, names: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"expected exact fields: {sorted(names)}")
    return value


@overload
def decode[T](kind: type[T], value: object) -> T: ...


@overload
def decode(kind: object, value: object) -> Any: ...


def decode(kind: Any, value: object) -> Any:
    """Only caller-selected model types can be instantiated, never JSON class names.

    Reject unknown/missing fields, bool-as-int, invalid enums and noncanonical
    base64. Constructors retain their existing validation responsibility.
    """
    origin, args = get_origin(kind), get_args(kind)
    if origin in (types.UnionType, Union):
        for option in args:
            try:
                return decode(option, value)
            except (ValueError, TypeError):
                pass
        raise ValueError("value matches no permitted union member")
    if origin is tuple:
        if not isinstance(value, list) or len(args) != 2 or args[1] is not Ellipsis:
            raise ValueError("expected a homogeneous tuple encoded as array")
        return tuple(decode(args[0], item) for item in value)
    if kind is bytes:
        encoded = object_fields(value, {"encoding", "data"})
        if encoded["encoding"] != "base64" or not isinstance(encoded["data"], str):
            raise ValueError("expected base64 bytes")
        data = base64.b64decode(encoded["data"], validate=True)
        if base64.b64encode(data).decode("ascii") != encoded["data"]:
            raise ValueError("noncanonical base64")
        return data
    if isinstance(kind, type) and issubclass(kind, Enum):
        if not isinstance(value, str):
            raise ValueError("expected enum text")
        return kind(value)
    if isinstance(kind, type) and is_dataclass(kind):
        record = object_fields(value, {field.name for field in fields(kind)})
        hints = get_type_hints(kind)
        return kind(**{key: decode(hints[key], item) for key, item in record.items()})
    if kind is float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("expected finite numeric value")
        return value
    if kind in (str, int, bool, type(None)) and type(value) is kind:
        return value
    raise ValueError(f"invalid value for {kind}")
