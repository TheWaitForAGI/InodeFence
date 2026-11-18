"""Refuse product-CLI runs on reserved or sealed target versions (#520 D3).

Two kinds of entries:

* **reserved** (``inodefence.v2_reservations``, tracked in the repository): v2 holdout candidate
  ranges. Every clone enforces them; there is no host setup step to forget.
  Pre-releases at either end of a range count as inside (fail-closed).
* **sealed** (per host, ``lock_path()``): the target versions of a registered run that is still
  sealed. Written when the run starts, removed when its unseal record is merged.

``sealed_conflict`` is the one check the CLI calls. **Order is a hard requirement:** call it after
the driver has resolved the version (``latest`` becomes an exact version; that step uses the
network but extracts nothing) and before any preparation. Preparation without a committed lock
file performs a benign extraction with that version as its readiness check, so it counts as a
run; call again with ``mode="prepare"`` before it.

Default is refuse. Overrides:

=========  =========================  ===========================================
kind       mode                       allowed with override
=========  =========================  ===========================================
reserved   explore, replay            never
reserved   verify, prepare            ``reason`` and ``ledger_ref`` both given
sealed     any                        ``reason`` given
=========  =========================  ===========================================

Every allowed override appends one line to ``overrides_path()`` (no results in it). The check does
not verify the "at most 5 fixed inputs per version" rule or that the ledger row exists (the
ledger is on Drive); it records ``inputs`` so the #520 D2 audit and the ledger review can.

Coverage: this guards product-CLI use only. ``make regression``, ``make target-run``,
``run_exp0``, ``run_effect_demo`` and the protected node-tar launcher do not go through it.

Standard library only; imports no engine or driver code.
"""

from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from inodefence import v2_reservations

SCHEMA = "inodefence-sealed-lineage/1"
MODES = ("explore", "verify", "replay", "prepare")
QUALIFICATION_MODES = ("verify", "prepare")
LEDGER_REF = re.compile(r"^[^#\s]+#\S+$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?$"
)


class LockError(Exception):
    """A lock or reservation that cannot be read. Never treated as a pass."""


def lock_path() -> Path:
    """Per-host sealed-run lock.

    ``INODEFENCE_SEALED_LOCK`` if set, else ``~/.inodefence/sealed-lineage.json``.
    """
    env = os.environ.get("INODEFENCE_SEALED_LOCK")
    return Path(env) if env else Path.home() / ".inodefence" / "sealed-lineage.json"


def overrides_path() -> Path:
    """Append-only audit of allowed overrides, next to the lock."""
    return lock_path().with_name("sealed-overrides.jsonl")


# ---- versions ----


def parse_version(text: str) -> tuple:
    """SemVer precedence key; raises ValueError for anything else (``latest``, ``7.x``, '')."""
    m = _SEMVER.match(text.strip())
    if not m:
        raise ValueError(f"not an exact SemVer version: {text!r}")
    core = tuple(int(m.group(i)) for i in (1, 2, 3))
    if m.group(4) is None:
        return (*core, 1, ())  # a release sorts after all of its pre-releases
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in m.group(4).split("."))
    return (*core, 0, ids)


# ---- entries ----


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str  # "reserved" | "sealed"
    target: str
    source: str
    min: tuple | None = None
    below: tuple | None = None
    versions: tuple[str, ...] = ()

    def covers(self, version: tuple) -> bool:
        if self.kind == "reserved":
            assert self.min is not None and self.below is not None
            # Lower bound on the base triple, so pre-releases of ``min`` (7.0.0-rc.1) are inside;
            # upper bound in full SemVer order, so 7.4.4-rc.1 is inside too. This also puts
            # pre-releases of ``below`` (5.1.0-rc.1) inside: it errs toward refusing (W4 PASS).
            return version[:3] >= self.min[:3] and version < self.below
        return any(parse_version(v) == version for v in self.versions)


@dataclass(frozen=True)
class Lock:
    entries: tuple[Entry, ...]


def reserved_entries() -> tuple[Entry, ...]:
    """The tracked reservation rows as entries; LockError if any row is unusable."""
    try:
        doc, sha = v2_reservations.RESERVED_SOURCE
        rows = v2_reservations.RESERVED
    except (AttributeError, ValueError, TypeError) as exc:
        raise LockError(f"v2_reservations is broken: {exc}") from exc
    out = []
    for row in rows:
        try:
            rid, target, lo, hi = row
            lo_v, hi_v = parse_version(lo), parse_version(hi)
        except (ValueError, TypeError) as exc:
            raise LockError(f"v2_reservations row {row!r}: {exc}") from exc
        if not lo_v < hi_v:
            raise LockError(f"v2_reservations row {rid}: min {lo} is not below {hi}")
        out.append(Entry(rid, "reserved", target, f"{doc} sha256 {sha[:8]}", min=lo_v, below=hi_v))
    return tuple(out)


def load_lock(path: Path | None = None) -> Lock | None:
    """Sealed-run entries of this host. Missing file → None; malformed → LockError."""
    path = path or lock_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LockError(f"{path}: unreadable sealed-lineage lock: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise LockError(f"{path}: schema is not {SCHEMA}")
    entries = []
    for raw in data.get("entries", []):
        try:
            versions = tuple(raw["versions"])
            for v in versions:
                parse_version(v)
            src = raw.get("source") or {}
            entries.append(
                Entry(
                    str(raw["id"]),
                    "sealed",
                    str(raw["target"]),
                    f"{src.get('doc', '?')} sha256 {str(src.get('sha256', ''))[:8]}",
                    versions=versions,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LockError(f"{path}: bad entry {raw!r}: {exc}") from exc
    return Lock(tuple(entries))


# ---- the check ----


@dataclass(frozen=True)
class Override:
    reason: str
    ledger_ref: str = ""  # "<ledger file>#<row key>"; required for reserved verify/prepare
    inputs: int | None = None  # fixed inputs in this run; prepare always counts as 1


@dataclass(frozen=True)
class Conflict:
    entry_id: str
    kind: str
    target: str
    version: str
    source: str
    message: str


def _refuse(entry: Entry, target: str, version: str, why: str) -> Conflict:
    label = "v2 예약 버전" if entry.kind == "reserved" else "봉인 중인 등록 실행의 버전"
    return Conflict(
        entry.id,
        entry.kind,
        target,
        version,
        entry.source,
        f"{target} {version}은(는) {label}이다({entry.id}, {entry.source}). {why}",
    )


def _allowed(entry: Entry, mode: str, override: Override | None) -> str | None:
    """None if allowed, else the reason for refusing."""
    if entry.kind == "reserved":
        if mode not in QUALIFICATION_MODES:
            return "예약 버전의 탐색·재실행은 허용하지 않는다. 고정 입력 점검은 verify로 한다."
        if override is None:
            return "고정 입력 점검이면 --sealed-override와 --ledger-ref를 준다."
        if not override.reason.strip() or not LEDGER_REF.match(override.ledger_ref):
            return (
                "--sealed-override 사유와 '<원장 파일>#<행 키>' 형식의 "
                "--ledger-ref가 모두 필요하다."
            )
        return None
    if override is None or not override.reason.strip():
        return "봉인 중 실행이 꼭 필요하면 --sealed-override에 사유를 준다(기록됨)."
    return None


def _audit(entry: Entry, target: str, version: str, mode: str, override: Override) -> None:
    path = overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    readiness = mode == "prepare"
    line = {
        "time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": socket.gethostname(),
        "target": target,
        "version": version,
        "mode": mode,
        "entry_id": entry.id,
        "kind": entry.kind,
        "reason": override.reason,
        "ledger_ref": override.ledger_ref,
        "inputs": 1 if readiness else override.inputs,
        "kind_of_input": "readiness" if readiness else "fixed",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def sealed_conflict(
    target: str,
    resolved_version: str,
    *,
    mode: str,
    override: Override | None = None,
    lock: Lock | None = None,
) -> Conflict | None:
    """None = go ahead; Conflict = refuse (exit 3 in the CLI). LockError propagates."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}: {mode!r}")
    if lock is None:
        lock = load_lock()
    entries = [e for e in reserved_entries() + (lock.entries if lock else ()) if e.target == target]
    if not entries:
        return None
    try:
        version = parse_version(resolved_version)
    except ValueError:
        unknown = Entry(entries[0].id, entries[0].kind, target, entries[0].source)
        return _refuse(unknown, target, resolved_version, "정확한 버전으로 읽을 수 없어 거부한다.")
    hits = [e for e in entries if e.covers(version)]
    for entry in hits:  # every covering entry must allow it before anything is recorded
        why = _allowed(entry, mode, override)
        if why is not None:
            return _refuse(entry, target, resolved_version, why)
    for entry in hits:
        assert override is not None
        _audit(entry, target, resolved_version, mode, override)
    return None
