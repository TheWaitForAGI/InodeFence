"""Synthetic-only bounded capture prototype; no target hooks or execution API.

Callers supply typed v2 evidence and explicit continuation tokens. This checks
bookkeeping and v3 reader compatibility, not the truth of native dependencies.
The operation count is bounded; strings/object evidence are caller-owned, so this
is not a constant-byte-memory native producer. Export has the reader's byte cap.
"""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import NoReturn

from inodefence.evaluation.rebinding_evidence import (
    MAX_RAW_BYTES,
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    reconstruct_rebinding_evidence,
)
from inodefence.model import (
    ArchiveEntryReference,
    EffectEventTrace,
    EvidenceSourceIdentity,
    FilesystemEffectEvent,
    OperationOutcome,
    canonical_json,
)


@dataclass(frozen=True)
class CaptureTerminal:
    pending: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]
    invalid: bool
    target_succeeded: bool

    @property
    def complete(self) -> bool:
        return not self.pending and not self.failures and not self.invalid and self.target_succeeded


class SyntheticRebindingCapture:
    """Track interleaved operations without using timestamps as dependency proof."""

    def __init__(self, max_operations: int = 64) -> None:
        if type(max_operations) is not int or not 1 <= max_operations <= 256:
            raise ValueError("max_operations must be an integer in 1..256")
        self._bound = max_operations
        self._started: dict[str, tuple[ArchiveEntryReference, int]] = {}
        self._completed: dict[str, FilesystemEffectEvent] = {}
        self._continuations: dict[str, tuple[str, str]] = {}
        self._failures: list[tuple[str, str]] = []
        self._last_sequence = -1
        self._invalid = False
        self._terminal: CaptureTerminal | None = None

    def _reject(self, message: str) -> NoReturn:
        self._invalid = True
        raise ValueError(message)

    def _advance(self, sequence: int) -> None:
        if self._terminal is not None:
            raise ValueError("capture is closed")
        if self._invalid:
            raise ValueError("capture is invalid")
        if type(sequence) is not int or sequence <= self._last_sequence:
            self._reject("duplicate or reversed observation sequence")
        # Other v2 lifecycle records may occupy sequence gaps. The v2 reader,
        # not this operation-only ledger, must establish transport completeness.
        self._last_sequence = sequence

    def begin(
        self,
        correlation: str,
        entry: ArchiveEntryReference,
        sequence: int,
        *,
        predecessor: str | None = None,
        token: str | None = None,
    ) -> None:
        self._advance(sequence)
        if (
            not isinstance(correlation, str)
            or not correlation
            or not isinstance(entry, ArchiveEntryReference)
        ):
            self._reject("operation requires correlation and typed entry")
        if correlation in self._started:
            self._reject("duplicate operation start")
        if len(self._started) >= self._bound:
            self._reject("operation bound exceeded")
        if (predecessor is None) != (token is None):
            self._reject("continuation requires predecessor and token")
        if predecessor is not None:
            event = self._completed.get(predecessor)
            if (
                event is None
                or event.entry != entry
                or event.outcome != OperationOutcome.SUCCEEDED
                or not isinstance(token, str)
                or not token
                or len(token) > 256
            ):
                self._reject("continuation requires successful same-entry predecessor and token")
            if any(
                previous == predecessor or previous_token == token
                for previous, previous_token in self._continuations.values()
            ):
                self._reject("continuation already consumed")
            self._continuations[correlation] = (predecessor, token)
        self._started[correlation] = (entry, sequence)

    def complete(self, event: FilesystemEffectEvent, *, error_code: str | None = None) -> None:
        self._advance(event.completion_sequence)
        if event.correlation_id in self._completed:
            self._reject("duplicate operation completion")
        if self._started.get(event.correlation_id) != (event.entry, event.start_sequence):
            self._reject("completion has no matching start/entry")
        failed = event.outcome != OperationOutcome.SUCCEEDED
        if (error_code is not None and (not isinstance(error_code, str) or not error_code)) or (
            failed != bool(error_code)
        ):
            self._reject("failure requires error code; success cannot carry error")
        self._completed[event.correlation_id] = event
        if error_code is not None:
            self._failures.append((event.correlation_id, error_code))

    def finish(self, *, target_succeeded: bool) -> CaptureTerminal:
        if self._terminal is not None:
            raise ValueError("capture is closed")
        if type(target_succeeded) is not bool:
            self._reject("target outcome must be Boolean")
        self._terminal = CaptureTerminal(
            tuple(key for key in self._started if key not in self._completed),
            tuple(self._failures),
            self._invalid,
            target_succeeded,
        )
        return self._terminal

    def envelope(self, trace: EffectEventTrace, source: EvidenceSourceIdentity) -> bytes:
        """Serialize then independently check synthetic endpoints against v2 evidence.

        The returned digest must later be frozen by an external manifest owner.
        Computing it here is an integrity check, not native provenance validation.
        """
        if self._terminal is None or not self._terminal.complete:
            raise ValueError("only closed complete successful capture can export")
        by_id = {event.correlation_id: event for event in trace.effect_events}
        if set(self._completed) != set(by_id):
            raise ValueError("captured operation set differs from v2 trace")
        if any(by_id.get(key) != event for key, event in self._completed.items()):
            raise ValueError("captured operation differs from v2 trace")
        records: list[dict[str, object]] = []
        for index, (successor, (predecessor, token)) in enumerate(self._continuations.items()):
            removal, creation = self._completed[predecessor], self._completed[successor]
            dependency_id = f"synthetic-dependency-{index}"
            records.extend(
                (
                    _endpoint(removal, "removal", dependency_id),
                    _endpoint(creation, "creation", dependency_id),
                    {
                        "record_type": "operation_dependency",
                        "record_id": dependency_id,
                        "dependency_id": dependency_id,
                        "predecessor_correlation_id": predecessor,
                        "successor_correlation_id": successor,
                        "predecessor_completion_sequence": removal.completion_sequence,
                        "successor_start_sequence": creation.start_sequence,
                        "kind": "producer_branch_continuation",
                        "evidence_token": token,
                    },
                )
            )
        value = {
            "format": PROTOCOL_ID,
            "schema_version": 3,
            "protocol_version": PROTOCOL_VERSION,
            "source": {
                "source_id": source.source_id,
                "mechanism": source.mechanism,
                "version": source.version,
                "source_sha256": source.source_sha256,
            },
            "v2_raw_stream_sha256": trace.provenance.raw_stream_sha256,
            "records": records,
            "terminal": {
                "record_count": len(records),
                "records_sha256": sha256(_json(records)).hexdigest(),
                "complete": True,
            },
        }
        raw = _json(value) + b"\n"
        if len(raw) > MAX_RAW_BYTES:
            raise ValueError("v3 envelope exceeds reader byte bound")
        reconstruct_rebinding_evidence(raw, sha256(raw).hexdigest(), trace, source)
        return raw


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _endpoint(event: FilesystemEffectEvent, role: str, dependency_id: str) -> dict[str, object]:
    # Explicit wire projection: canonical model JSON is not the v3 envelope schema.
    value = json.loads(canonical_json(event))["value"]
    return {
        "record_type": "operation_endpoint",
        "record_id": f"{dependency_id}-{role}",
        "dependency_id": dependency_id,
        "role": role,
        "entry": {
            "ordinal": event.entry.entry_index,
            "path": event.entry.path,
            "type": event.entry.entry_type.value,
            "link_target": event.entry.link_target,
        },
        **{
            field: value[field]
            for field in (
                "association",
                "effect_class",
                "evidence_strength",
                "affected_paths",
                "operation",
                "start_sequence",
                "completion_sequence",
                "start_observation",
                "completion_observation",
                "outcome",
                "object_evidence",
                "correlation_id",
            )
        },
        "v2_source_id": event.source_id,
        "v2_raw_record_id": event.raw_evidence.record_id,
    }
