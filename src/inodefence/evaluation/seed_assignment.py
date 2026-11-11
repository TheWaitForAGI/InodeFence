"""Which registered seeds each host runs, when one registration runs on two hosts.

The assignment is a frozen input next to the preregistration: one JSON file, the same bytes on
every host, its sha256 recorded with every cell. Rules fixed here:

* **Unit is the seed.** A seed belongs to exactly one host, so every target and arm of that seed
  runs on the same host and the seed-block permutation test keeps its blocks. The launcher derives
  cells from the seeds, so a seed cannot be split by construction; the merge tool checks it again.
  The one exception is ``replicate-v1`` (below), which is for host qualification, never for EXP.
* **Seeds come from the registration, in its order.** The union of the hosts' seeds is the whole
  registered list or its first ``n`` seeds (a holdout run decided at GO). Each host's list keeps the
  registered order.
* **Inputs are infrastructure values only.** The rate split takes per-host throughput ``r_h``; no
  oracle value, arm or outcome enters it.
* **No reassignment.** A host that stops keeps its seeds; moving them is a people decision outside
  this file.
* **The registration names the rule** (``seed_assignment_rule``). ``alternate-v1`` (train) is fixed
  at freeze, so its sha256 is registered too. ``rh-proportional-v1`` (holdout) is made at GO from
  the GO decision file's ``r_h``, so it has no registered sha256. ``replicate-v1`` gives every
  participating host every seed (host qualification: the same cells on each host, compared, never
  pooled); its sha256 is registered. Either way the launcher and the merge tool regenerate the file
  from the rule and accept only the same bytes (``rule_problems``).
* **Participants.** ``participants`` names the hosts that take part (one or both). A host left out
  gets no seed, so the launcher refuses to run it. A file without the field is the two-host file
  (both hosts take part) and keeps its exact earlier bytes.

``split_by_rate`` gives HOST1 the first ``round_half_down(n * r_1 / (r_1 + r_2))`` seeds and HOST2
the rest, in exact rational arithmetic, so every host and Python version computes the same split.
With one participant that host gets all ``n`` seeds and its ``r_h`` is only recorded.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

SCHEMA = "inodefence-seed-assignment-v1"
RULE_RH_PROPORTIONAL = "rh-proportional-v1"
RULE_ALTERNATE = "alternate-v1"
RULE_REPLICATE = "replicate-v1"
RULES = (RULE_ALTERNATE, RULE_RH_PROPORTIONAL, RULE_REPLICATE)
HOST_IDS = ("HOST1", "HOST2")


class SeedAssignmentError(ValueError):
    """The assignment file is malformed or does not fit the registration."""


@dataclass(frozen=True, slots=True)
class SeedAssignment:
    """A validated assignment and the sha256 of its exact bytes."""

    hosts: Mapping[str, tuple[int, ...]]
    sha256: str
    rule: str
    path: Path | None = None
    data: bytes = b""
    participants: tuple[str, ...] = HOST_IDS

    @property
    def replicated(self) -> bool:
        return self.rule == RULE_REPLICATE

    def seeds_for(self, host_id: str) -> tuple[int, ...]:
        if host_id not in self.hosts:
            raise SeedAssignmentError(
                f"host {host_id!r} is not in the assignment ({', '.join(self.hosts)})"
            )
        return self.hosts[host_id]

    def host_of(self) -> dict[int, str]:
        if self.replicated:
            raise SeedAssignmentError("replicate-v1 gives each seed to every participant")
        return {seed: host for host, seeds in self.hosts.items() for seed in seeds}

    def all_seeds(self) -> tuple[int, ...]:
        if self.replicated:
            return self.hosts[self.participants[0]]
        return tuple(seed for seeds in self.hosts.values() for seed in seeds)

    def record(self, host_id: str | None = None) -> dict[str, Any]:
        """What the launcher and index keep: sha256, rule and the per-host seeds."""
        record: dict[str, Any] = {
            "sha256": self.sha256,
            "rule": self.rule,
            "hosts": {host: list(seeds) for host, seeds in self.hosts.items()},
        }
        if self.participants != HOST_IDS:
            record["participants"] = list(self.participants)
        if self.path is not None:
            record["file"] = self.path.name
        if host_id is not None:
            record["host_id"] = host_id
        return record


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SeedAssignmentError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _participants(value: object) -> tuple[str, ...]:
    """The participating hosts, in HOST_IDS order; absent means both."""
    if value is None:
        return HOST_IDS
    if (
        not isinstance(value, list)
        or not value
        or len(set(value)) != len(value)
        or not set(value) <= set(HOST_IDS)
        or list(value) != [host for host in HOST_IDS if host in value]
    ):
        raise SeedAssignmentError(f"participants must be a non-empty ordered subset of {HOST_IDS}")
    return tuple(value)


def parse_seed_assignment(
    data: bytes, registered_seeds: Sequence[int], *, path: Path | None = None
) -> SeedAssignment:
    """Validate ``data`` against the registered seed order. Every problem refuses the file."""
    try:
        document = json.loads(data, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise SeedAssignmentError(f"assignment is not JSON: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise SeedAssignmentError(f"assignment schema must be {SCHEMA!r}")
    rule = document.get("rule")
    if rule not in RULES:
        raise SeedAssignmentError(f"assignment rule must be one of {RULES}, got {rule!r}")
    participants = _participants(document.get("participants"))
    hosts = document.get("hosts")
    if not isinstance(hosts, dict) or set(hosts) != set(HOST_IDS):
        raise SeedAssignmentError(f"assignment hosts must be exactly {HOST_IDS}")
    position = {seed: index for index, seed in enumerate(registered_seeds)}
    seen: dict[int, str] = {}
    parsed: dict[str, tuple[int, ...]] = {}
    for host in HOST_IDS:
        seeds = hosts[host]
        if not isinstance(seeds, list) or not all(type(s) is int for s in seeds):
            raise SeedAssignmentError(f"{host}: seeds must be a list of integers")
        if host not in participants and seeds:
            raise SeedAssignmentError(f"{host} does not take part but is assigned seeds")
        for seed in seeds:
            if seed not in position:
                raise SeedAssignmentError(f"{host}: seed {seed} is not registered")
            if seed in seen and rule != RULE_REPLICATE:
                raise SeedAssignmentError(f"seed {seed} is assigned to {seen[seed]} and {host}")
            seen.setdefault(seed, host)
        if [position[s] for s in seeds] != sorted(position[s] for s in seeds):
            raise SeedAssignmentError(f"{host}: seeds must keep the registered order")
        parsed[host] = tuple(seeds)
    union = sorted(seen, key=position.__getitem__)
    if union != list(registered_seeds[: len(union)]) or not union:
        raise SeedAssignmentError(
            "assigned seeds must be the registered seeds or their first n, without gaps"
        )
    if rule == RULE_REPLICATE and any(parsed[host] != tuple(union) for host in participants):
        raise SeedAssignmentError("replicate-v1 gives every participant the same seeds")
    declared_n = document.get("n")
    if declared_n is not None and declared_n != len(union):
        raise SeedAssignmentError(f"assignment declares n={declared_n} but assigns {len(union)}")
    return SeedAssignment(
        parsed, hashlib.sha256(data).hexdigest(), str(rule), path, data, participants
    )


def load_seed_assignment(path: Path, registered_seeds: Sequence[int]) -> SeedAssignment:
    return parse_seed_assignment(path.read_bytes(), registered_seeds, path=path)


def _round_half_down(value: Fraction) -> int:
    floor = math.floor(value)
    return floor if value - floor <= Fraction(1, 2) else floor + 1


def _rate(text: str) -> Fraction:
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError) as error:
        raise SeedAssignmentError(f"rate {text!r} is not a decimal number") from error
    if value <= 0:
        raise SeedAssignmentError(f"rate {text!r} must be positive; no assignment without it")
    return value


def _document(
    rule: str, n: int, hosts: Mapping[str, list[int]], participants: Sequence[str] | None
) -> dict[str, Any]:
    """Assignment document; ``participants`` only when given, so two-host bytes stay as before."""
    document: dict[str, Any] = {"schema": SCHEMA, "rule": rule, "n": n, "hosts": dict(hosts)}
    if participants is not None:
        document["participants"] = list(_participants(list(participants)))
    return document


def split_by_rate(
    registered_seeds: Sequence[int],
    n: int,
    rates: Mapping[str, str],
    participants: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The ``rh-proportional-v1`` document: HOST1 the front ``round_half_down(n·r1/Σr)``.

    ``rates`` are decimal strings exactly as recorded (``r_h`` in exec/h); they go into the file
    so the split can be recomputed from it. With ``participants`` the rates are needed for exactly
    those hosts; one participant gets all ``n`` seeds.
    """
    members = HOST_IDS if participants is None else _participants(list(participants))
    if set(rates) != set(members):
        raise SeedAssignmentError(f"rates are needed for exactly {members}")
    if not 1 <= n <= len(registered_seeds):
        raise SeedAssignmentError(f"n={n} must be between 1 and {len(registered_seeds)}")
    values = {host: _rate(rates[host]) for host in members}
    seeds = list(registered_seeds[:n])
    if len(members) == 1:
        hosts = {host: (seeds if host in members else []) for host in HOST_IDS}
    else:
        first = _round_half_down(n * values["HOST1"] / (values["HOST1"] + values["HOST2"]))
        hosts = {"HOST1": seeds[:first], "HOST2": seeds[first:]}
    document = _document(RULE_RH_PROPORTIONAL, n, hosts, participants)
    document["rates_exec_per_hour"] = {host: rates[host] for host in members}
    return document


def split_alternate(
    registered_seeds: Sequence[int], participants: Sequence[str] | None = None
) -> dict[str, Any]:
    """Registered order, alternating over the participants: no measured input."""
    seeds = list(registered_seeds)
    members = HOST_IDS if participants is None else _participants(list(participants))
    hosts = {
        host: seeds[members.index(host) :: len(members)] if host in members else []
        for host in HOST_IDS
    }
    return _document(RULE_ALTERNATE, len(seeds), hosts, participants)


def split_replicate(
    registered_seeds: Sequence[int], participants: Sequence[str] | None = None
) -> dict[str, Any]:
    """Every participant gets every registered seed (host qualification only, never pooled)."""
    seeds = list(registered_seeds)
    members = HOST_IDS if participants is None else _participants(list(participants))
    hosts = {host: (list(seeds) if host in members else []) for host in HOST_IDS}
    return _document(RULE_REPLICATE, len(seeds), hosts, participants)


def assignment_bytes(document: Mapping[str, Any]) -> bytes:
    """Canonical bytes, so the same inputs give the same sha256 on every host."""
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _declared_participants(data: bytes) -> Sequence[str] | None:
    """The file's own ``participants`` (None when absent); regeneration uses the same value."""
    try:
        document = json.loads(data)
    except json.JSONDecodeError:
        return None
    value = document.get("participants") if isinstance(document, dict) else None
    return value if isinstance(value, list) else None


def rule_problems(
    data: bytes,
    *,
    rule: str,
    registered_seeds: Sequence[int],
    registered_sha256: str | None,
    go_decision: Mapping[str, Any] | None,
) -> list[str]:
    """Why ``data`` is not the assignment the registered rule gives; empty when it is.

    ``alternate-v1`` and ``replicate-v1``: the bytes regenerated from the registered seeds (and the
    file's participants), and the registered sha256 pins them. ``rh-proportional-v1``: the bytes
    regenerated from the GO decision file's ``rates_exec_per_hour`` (and its ``participants``) over
    every registered seed; a missing file or rate refuses. If the GO decision file records
    ``seed_assignment_sha256``, it must name these bytes.
    """
    digest = hashlib.sha256(data).hexdigest()
    if rule in (RULE_ALTERNATE, RULE_REPLICATE):
        split = split_alternate if rule == RULE_ALTERNATE else split_replicate
        problems = []
        try:
            expected = assignment_bytes(split(registered_seeds, _declared_participants(data)))
        except SeedAssignmentError as error:
            return [f"assignment participants unusable: {error}"]
        if data != expected:
            problems.append(f"assignment is not the {rule} split of the registered seeds")
        if registered_sha256 != digest:
            problems.append(
                f"assignment sha256 {digest} != registered seed_assignment_sha256 "
                f"{registered_sha256}"
            )
        return problems
    if rule != RULE_RH_PROPORTIONAL:
        return [f"unknown seed_assignment_rule {rule!r}"]
    if go_decision is None:
        return ["rh-proportional-v1 needs the GO decision file (--go-decision)"]
    participants = go_decision.get("participants")
    members = HOST_IDS if participants is None else tuple(participants)
    rates = go_decision.get("rates_exec_per_hour")
    if not isinstance(rates, Mapping) or not all(
        isinstance(rates.get(host), str) for host in members
    ):
        return ["GO decision file has no r_h for every participant: GO not computed, no assignment"]
    try:
        expected = assignment_bytes(
            split_by_rate(
                registered_seeds,
                len(registered_seeds),
                {host: rates[host] for host in members},
                participants,
            )
        )
    except SeedAssignmentError as error:
        return [f"GO decision r_h unusable: {error}"]
    problems = []
    if data != expected:
        problems.append("assignment is not the rh-proportional-v1 split of the GO decision r_h")
    recorded = go_decision.get("seed_assignment_sha256")
    if recorded is not None and recorded != digest:
        problems.append(f"GO decision names assignment {recorded}, not {digest}")
    return problems
