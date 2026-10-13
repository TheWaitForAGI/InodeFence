"""No-overwrite raw export for one completed native v2 effect observation."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from inodefence.effect_pipeline import NativeEffectRun
from inodefence.model import EffectRunResult

from .failure import ArtifactReference
from .storage import publish_bytes, sync_directory, write_record
from .verify import _digest


@dataclass(frozen=True, slots=True)
class NativeEffectEvidenceManifest:
    """Completion marker for immutable raw producer and typed result bytes."""

    serialization_schema: ClassVar[int] = 1

    raw_stream: ArtifactReference
    result: ArtifactReference
    case_id: str
    raw_stream_sha256: str
    producer_source_sha256: str
    trace_schema: int = 2
    result_schema: int = EffectRunResult.serialization_schema
    classification: str = "raw-native-effect-observation-v2"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.raw_stream, ArtifactReference)
            or self.raw_stream.name != "raw-stream.json"
            or not isinstance(self.result, ArtifactReference)
            or self.result.name != "result.json"
        ):
            raise ValueError("native effect manifest artifact names are fixed")
        for value in (self.case_id, self.raw_stream_sha256, self.producer_source_sha256):
            _digest(value)
        if self.trace_schema != 2 or self.result_schema != EffectRunResult.serialization_schema:
            raise ValueError("unsupported native effect evidence schema")
        if self.classification != "raw-native-effect-observation-v2":
            raise ValueError("unsupported native effect evidence classification")


def export_native_effect_run(run: NativeEffectRun, directory: Path) -> str:
    """Publish exact raw bytes and derived typed evidence, then the manifest."""
    if not isinstance(run, NativeEffectRun):
        raise ValueError("native effect export requires a NativeEffectRun")
    raw_digest = sha256(run.raw_stream).hexdigest()
    trace = run.result.trace
    if trace.provenance.raw_stream_sha256 != raw_digest:
        raise ValueError("typed trace raw-stream binding differs from producer bytes")
    sources = trace.provenance.sources
    if len(sources) != 1:
        raise ValueError("native node-tar trace requires one producer source")
    directory.mkdir()
    sync_directory(directory.parent)
    raw_file_digest = publish_bytes(directory / "raw-stream.json", run.raw_stream)
    result_digest = write_record(directory / "result.json", run.result)
    manifest = NativeEffectEvidenceManifest(
        ArtifactReference("raw-stream.json", raw_file_digest),
        ArtifactReference("result.json", result_digest),
        run.result.base_result.case.case_id,
        raw_digest,
        sources[0].source_sha256,
    )
    return write_record(directory / "manifest.json", manifest)
