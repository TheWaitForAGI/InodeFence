"""Which registered seeds each host runs, when one registration runs on two hosts.

The assignment is a frozen input next to the preregistration: one JSON file, the same bytes on
every host, its sha256 recorded with every cell. Rules fixed here:

* **Unit is the seed.** A seed belongs to exactly one host, so every target and arm of that seed
  runs on the same host and the seed-block permutation test keeps its blocks. The launcher derives
  cells from the seeds, so a seed cannot be split by construction; the merge tool checks it again.
* **Seeds come from the registration, in its order.** The union of the hosts' seeds is the whole
  registered list or its first ``n`` seeds (a holdout run decided at GO). Each host's list keeps the
  registered order.
* **Inputs are infrastructure values only.** The rate split takes per-host throughput ``r_h``; no
  oracle value, arm or outcome enters it.
* **No reassignment.** A host that stops keeps its seeds; moving them is a people decision outside
  this file.
* **The registration names the rule** (``seed_assignment_rule``). ``alternate-v1`` (train) is fixed
  at freeze, so its sha256 is registered too. ``rh-proportional-v1`` (holdout) is made at GO from
  the GO decision file's ``r_h``, so it has no registered sha256. Either way the launcher and the
  merge tool regenerate the file from the rule and accept only the same bytes
  (``rule_problems``).

``split_by_rate`` gives HOST1 the first ``round_half_down(n * r_1 / (r_1 + r_2))`` seeds and HOST2
the rest, in exact rational arithmetic, so every host and Python version computes the same split.
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
RULES = (RULE_ALTERNATE, RULE_RH_PROPORTIONAL)
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

    def seeds_for(self, host_id: str) -> tuple[int, ...]:
        if host_id not in self.hosts:
            raise SeedAssignmentError(
                f"host {host_id!r} is not in the assignment ({', '.join(self.hosts)})"
            )
        return self.hosts[host_id]

    def host_of(self) -> dict[int, str]:
        return {seed: host for host, seeds in self.hosts.items() for seed in seeds}

    def all_seeds(self) -> tuple[int, ...]:
        return tuple(seed for seeds in self.hosts.values() for seed in seeds)

    def record(self, host_id: str | None = None) -> dict[str, Any]:
        """What the launcher and index keep: sha256, rule and the per-host seeds."""
        record: dict[str, Any] = {
            "sha256": self.sha256,
            "rule": self.rule,
            "hosts": {host: list(seeds) for host, seeds in self.hosts.items()},
        }
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
        for seed in seeds:
            if seed not in position:
                raise SeedAssignmentError(f"{host}: seed {seed} is not registered")
            if seed in seen:
                raise SeedAssignmentError(f"seed {seed} is assigned to {seen[seed]} and {host}")
            seen[seed] = host
        if [position[s] for s in seeds] != sorted(position[s] for s in seeds):
            raise SeedAssignmentError(f"{host}: seeds must keep the registered order")
        parsed[host] = tuple(seeds)
    union = sorted(seen, key=position.__getitem__)
    if union != list(registered_seeds[: len(union)]) or not union:
        raise SeedAssignmentError(
            "assigned seeds must be the registered seeds or their first n, without gaps"
        )
    declared_n = document.get("n")
    if declared_n is not None and declared_n != len(union):
        raise SeedAssignmentError(f"assignment declares n={declared_n} but assigns {len(union)}")
    return SeedAssignment(parsed, hashlib.sha256(data).hexdigest(), str(rule), path, data)


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


def split_by_rate(
    registered_seeds: Sequence[int], n: int, rates: Mapping[str, str]
) -> dict[str, Any]:
    """The ``rh-proportional-v1`` document: HOST1 the front ``round_half_down(n·r1/Σr)``.

    ``rates`` are decimal strings exactly as recorded (``r_h`` in exec/h); they go into the file
    so the split can be recomputed from it.
    """
    if set(rates) != set(HOST_IDS):
        raise SeedAssignmentError(f"rates are needed for exactly {HOST_IDS}")
    if not 1 <= n <= len(registered_seeds):
        raise SeedAssignmentError(f"n={n} must be between 1 and {len(registered_seeds)}")
    r1, r2 = (_rate(rates[host]) for host in HOST_IDS)
    first = _round_half_down(n * r1 / (r1 + r2))
    seeds = list(registered_seeds[:n])
    return {
        "schema": SCHEMA,
        "rule": RULE_RH_PROPORTIONAL,
        "n": n,
        "rates_exec_per_hour": {host: rates[host] for host in HOST_IDS},
        "hosts": {"HOST1": seeds[:first], "HOST2": seeds[first:]},
    }


def split_alternate(registered_seeds: Sequence[int]) -> dict[str, Any]:
    """Registered order, alternating HOST1, HOST2: equal counts with no measured input."""
    seeds = list(registered_seeds)
    return {
        "schema": SCHEMA,
        "rule": RULE_ALTERNATE,
        "n": len(seeds),
        "hosts": {"HOST1": seeds[0::2], "HOST2": seeds[1::2]},
    }


def assignment_bytes(document: Mapping[str, Any]) -> bytes:
    """Canonical bytes, so the same inputs give the same sha256 on every host."""
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def rule_problems(
    data: bytes,
    *,
    rule: str,
    registered_seeds: Sequence[int],
    registered_sha256: str | None,
    go_decision: Mapping[str, Any] | None,
) -> list[str]:
    """Why ``data`` is not the assignment the registered rule gives; empty when it is.

    ``alternate-v1``: the bytes regenerated from the registered seeds, and the registered sha256.
    ``rh-proportional-v1``: the bytes regenerated from the GO decision file's
    ``rates_exec_per_hour`` over every registered seed; a missing file or rate refuses. If the GO
    decision file records ``seed_assignment_sha256``, it must name these bytes.
    """
    digest = hashlib.sha256(data).hexdigest()
    if rule == RULE_ALTERNATE:
        problems = []
        if data != assignment_bytes(split_alternate(registered_seeds)):
            problems.append("assignment is not the alternate-v1 split of the registered seeds")
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
    rates = go_decision.get("rates_exec_per_hour")
    if not isinstance(rates, Mapping) or not all(
        isinstance(rates.get(host), str) for host in HOST_IDS
    ):
        return ["GO decision file has no r_h for both hosts: GO not computed, no assignment"]
    try:
        expected = assignment_bytes(
            split_by_rate(registered_seeds, len(registered_seeds), dict(rates))
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
