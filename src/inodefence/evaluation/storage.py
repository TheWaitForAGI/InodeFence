"""Checksummed canonical records with atomic no-overwrite file publication."""

import os
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

from inodefence.model import canonical_json

from .encoding import decode, json_bytes, object_fields, read_json
from .verify import VerificationError, _digest, _read_file


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_bytes(path: Path, content: bytes) -> str:
    """Publish a fully synced file by atomic hardlink, never overwrite evidence.

    Requires Linux and a trusted parent on one filesystem. Errors before link
    leave no destination; errors after link (including parent fsync) may leave
    the complete destination and propagate. A hard interruption can leave a
    temporary file. The final name never refers to a partly written file.
    """
    if sys.platform != "linux":
        raise NotImplementedError("evidence publication requires Linux")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".record-", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if _read_file(temporary) != content:
            raise OSError("staged evidence differs from encoded record")
        os.link(temporary, path, follow_symlinks=False)
        sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink()
    return sha256(content).hexdigest()


def write_record(path: Path, value: object) -> str:
    payload = canonical_json(value).encode("ascii")
    record = {
        "format": "inodefence-evaluation-record",
        "schema_version": 1,
        "payload": read_json(payload),
        "payload_sha256": sha256(payload).hexdigest(),
    }
    return publish_bytes(path, json_bytes(record) + b"\n")


def read_record[T](path: Path, kind: type[T], *, expected_sha256: str | None = None) -> T:
    """Verify checksum/schema/canonical bytes before decoding caller-selected type."""
    try:
        content = _read_file(path)
        if expected_sha256 is not None and sha256(content).hexdigest() != _digest(expected_sha256):
            raise ValueError("record checksum mismatch")
        record = object_fields(
            read_json(content), {"format", "schema_version", "payload", "payload_sha256"}
        )
        if (
            record["format"] != "inodefence-evaluation-record"
            or type(record["schema_version"]) is not int
            or record["schema_version"] != 1
            or content != json_bytes(record) + b"\n"
        ):
            raise ValueError("unsupported/noncanonical record schema")
        payload = json_bytes(record["payload"])
        if sha256(payload).hexdigest() != _digest(record["payload_sha256"]):
            raise ValueError("payload checksum mismatch")
        envelope = object_fields(record["payload"], {"model", "schema_version", "value"})
        if (
            envelope["model"] != kind.__name__
            or type(envelope["schema_version"]) is not int
            or envelope["schema_version"] != getattr(kind, "serialization_schema", 1)
        ):
            raise ValueError("unsupported model/schema")
        value = decode(kind, envelope["value"])
        if canonical_json(value).encode("ascii") != payload:
            raise ValueError("noncanonical payload")
        return value
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise VerificationError(f"invalid evaluation record: {error}") from error
