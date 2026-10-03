"""Versioned, deterministic evidence encoding, independent of Python hash seeds."""

import base64
import json
from dataclasses import asdict, is_dataclass

SCHEMA_VERSION = 1


def _encode_bytes(value: object) -> dict[str, str]:
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    raise TypeError(f"Unsupported evidence value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Encode a model dataclass, retaining bytes losslessly and tuple order.

    This is an evidence/export boundary, not a persistence system or deserializer.
    Raw observations contain run-specific metadata; only normalized signatures
    and logical cases are intended as cross-run keys.
    """
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("canonical_json requires a model dataclass instance")
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "model": type(value).__name__, "value": asdict(value)},
        default=_encode_bytes,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
