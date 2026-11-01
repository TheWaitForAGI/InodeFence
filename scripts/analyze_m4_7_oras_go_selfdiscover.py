"""M4.7 oras-go self-discovery right-censored roll-up (A3 state-aware vs A1 random).

Reads native oras-go self-discovery evidence JSONs (``oras_go_campaign_schema`` 1, as
written by ``oras_go_effect_campaign.oras_go_effect_campaign_report``), groups them by arm,
and produces the per-arm right-censored roll-up via ``evaluation.right_censored`` -- the same
Wilson engine the M3.3 control and M4.5 decompress roll-ups use. It is additive: it imports
the shared engine, modifies no existing module, and re-derives none of the runtime lane's
determination.

Honest framing, fixed before running (evaluation-protocol-v1 / audit EN-008):

* ``hit`` = ``discovered_violation`` = any step with ``contract_violated`` true (the generic
  C0/C1/C2 oracle fired on the before/after snapshots; oracle logic unchanged).
  ``first_hit_executions`` is the 1-based index of that first step.
* ``by_contract`` splits the registered any-contract hit into C0 (path-boundary, the baseline
  contract, explicitly NOT InodeFence's novelty) vs C1 (object identity) and C2 (external
  effect) -- the identity/effect targets that carry the novelty. A C0 path escape is not an
  identity/effect discovery. The preregistered oras-go HIT is generic C1/C2.
* ``complete`` = ``observations == eligible_observations == execution_budget``: the campaign
  filled its budget and every step produced an eligible observation. A fail-closed abort stub
  (``{"aborted": {...}}`` with no config/steps) is infrastructure-incomplete, excluded from
  the hit denominator, and reported separately -- never a within-budget no-hit and never
  silently growing the denominator (evaluation-protocol-v1).
* A3 (state-aware identity) composes mutation targets from observed snapshot names
  (``outside``, ``sentinel.txt``) -- so it is NOT blind; this is disclosed. A1 (random) has no
  observation tokens and is the floor. No target path/identifier/answer seed and no proximity
  reward is hardcoded in the mutation vocabulary or the oracle (D005/D006).
* oras-go is a compiled 3rd-party extractor: link calls cannot be interposed, so the feedback
  channel is a POST-EXTRACTION state SET frame (``inodefence-boundary-attempt-v1``). It is
  narrower than decompress's fs-wrap set and node-tar's ordered per-op channel -- cleanly
  refused attempts are NOT observed. Disclosed.
* self-discovery (this right-censored result) != generality (oracle/adapter reuse) !=
  effectiveness (rate superiority). This reports no effectiveness ranking; the A3-vs-A1
  contrast is a mechanism tally over a small sample, not a rate claim.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from inodefence.evaluation.right_censored import (
    SeedOutcome,
    right_censored_summary,
)

_SCHEMA = 1

# Known arm policy strings -> stable arm label. An unknown policy falls back to its own string
# so the roll-up still groups it; it never silently merges two arms.
_ARM_LABELS = {
    "uniform-generic-m1-state-aware-escape-hardlink-v1": "A3-state-aware",
    "uniform-generic-v1": "A1-random",
}

_STATE_AWARE_ARMS = frozenset({"A3-state-aware"})

# RUN_ID token (from the evidence filename) -> arm label, used when an abort stub carries no
# config. The filename is the authoritative source of seed+arm for a stub.
_RUN_ID_ARM = {"sa": "A3-state-aware", "a1": "A1-random"}
_RUN_ID_RE = re.compile(r"-m4sd-oras-(sa|a1)-s(\d+)\.json$")


@dataclass(frozen=True, slots=True)
class Campaign:
    """One native oras-go self-discovery campaign, as recorded in its evidence JSON."""

    path: str
    seed: int
    budget: int
    policy: str
    arm: str
    producer: str
    observations: int
    eligible_observations: int
    retained_cases: int
    unique_attempt_keys: int
    unique_violation_fingerprints: int
    unique_full_states: int
    terminations: dict[str, int]
    discovered_violation: bool
    first_hit_index_one_based: int | None
    contract_counts: dict[str, int] = field(default_factory=dict)
    contract_first_hit: dict[str, int | None] = field(default_factory=dict)
    frames_observed: int = 0
    aborted: bool = False
    abort_reason: str | None = None

    @property
    def complete(self) -> bool:
        """A complete campaign ran its full budget with every observation eligible.

        A fail-closed infrastructure abort (``aborted``) is never complete: the backend writes a
        stub with no steps, so it is infrastructure-incomplete and excluded from the hit
        denominator (reported separately), per evaluation-protocol-v1.
        """
        if self.aborted:
            return False
        return self.eligible_observations == self.budget and self.observations == self.budget

    def seed_outcome(self) -> SeedOutcome:
        """Registered hit = discovered_violation (ANY contract C0/C1/C2)."""
        hit = self.discovered_violation and self.complete
        return SeedOutcome(
            seed=self.seed,
            budget=self.budget,
            complete=self.complete,
            hit=hit,
            first_hit_executions=self.first_hit_index_one_based if hit else None,
        )

    def contract_outcome(self, contract: str) -> SeedOutcome:
        """Per-contract hit = a step whose oracle flagged exactly this contract (C0/C1/C2)."""
        hit = self.complete and self.contract_counts.get(contract, 0) > 0
        return SeedOutcome(
            seed=self.seed,
            budget=self.budget,
            complete=self.complete,
            hit=hit,
            first_hit_executions=self.contract_first_hit.get(contract) if hit else None,
        )


def _arm_for(policy: str) -> str:
    return _ARM_LABELS.get(policy, policy)


def _parse_run_id(path: str | Path) -> tuple[str, int] | None:
    """Return (arm_label, seed) parsed from an ``...-m4sd-oras-<arm>-s<seed>.json`` name."""
    match = _RUN_ID_RE.search(Path(path).name)
    if match is None:
        return None
    return _RUN_ID_ARM[match.group(1)], int(match.group(2))


def load_campaign(path: str | Path, *, aborted_budget: int = 200) -> Campaign:
    """Parse one evidence JSON into a ``Campaign``; raise on an unexpected schema.

    A fail-closed abort stub (``{"aborted": {...}}`` with no config/steps) is returned as an
    ``aborted`` Campaign whose seed/arm come from the ``-m4sd-oras-<arm>-s<seed>`` filename,
    since the stub carries neither. ``aborted_budget`` is the registered budget used to record
    the censored entry label (it is excluded from the hit denominator regardless).
    """
    data = json.loads(Path(path).read_text())
    if data.get("oras_go_campaign_schema") != _SCHEMA:
        raise ValueError(f"{path}: not oras_go_campaign_schema {_SCHEMA}")

    if "aborted" in data or "config" not in data:
        run = _parse_run_id(path)
        if run is None:
            raise ValueError(f"{path}: aborted stub with no config and unparseable RUN_ID")
        arm, seed = run
        reason = ""
        if isinstance(data.get("aborted"), dict):
            reason = str(data["aborted"].get("reason", ""))
        return Campaign(
            path=str(path),
            seed=seed,
            budget=aborted_budget,
            policy="",
            arm=arm,
            producer=str(data.get("producer", "")),
            observations=0,
            eligible_observations=0,
            retained_cases=0,
            unique_attempt_keys=0,
            unique_violation_fingerprints=0,
            unique_full_states=0,
            terminations={},
            discovered_violation=False,
            first_hit_index_one_based=None,
            aborted=True,
            abort_reason=reason,
        )

    config = data["config"]
    stats = data["final_stats"]
    steps = data["steps"]
    terminations: dict[str, int] = {}
    first_hit: int | None = None
    frames_observed = 0
    contract_counts: dict[str, int] = {"C0": 0, "C1": 0, "C2": 0}
    contract_first_hit: dict[str, int | None] = {"C0": None, "C1": None, "C2": None}
    for step in steps:
        term = step.get("termination")
        if term is not None:
            terminations[term] = terminations.get(term, 0) + 1
        if step.get("frame_observed"):
            frames_observed += 1
        one_based = int(step["index"]) + 1
        if first_hit is None and step.get("contract_violated"):
            first_hit = one_based
        oracle = step.get("oracle", {})
        for contract in ("C0", "C1", "C2"):
            if oracle.get(contract):
                contract_counts[contract] += 1
                if contract_first_hit[contract] is None:
                    contract_first_hit[contract] = one_based
    budget = int(config["execution_budget"])
    policy = str(config["mutation_policy"])
    seed = int(config["random_seed"])
    run = _parse_run_id(path)
    if run is not None and run[1] != seed:
        raise ValueError(f"{path}: filename seed {run[1]} != config seed {seed}")
    return Campaign(
        path=str(path),
        seed=seed,
        budget=budget,
        policy=policy,
        arm=_arm_for(policy),
        producer=str(data.get("producer", "")),
        observations=int(stats["observations"]),
        eligible_observations=int(stats["eligible_observations"]),
        retained_cases=int(stats["retained_cases"]),
        unique_attempt_keys=int(stats["unique_attempt_keys"]),
        unique_violation_fingerprints=int(stats["unique_violation_fingerprints"]),
        unique_full_states=int(stats["unique_full_states"]),
        terminations=terminations,
        discovered_violation=bool(data["discovered_violation"]),
        first_hit_index_one_based=first_hit,
        contract_counts=contract_counts,
        contract_first_hit=contract_first_hit,
        frames_observed=frames_observed,
    )


def _mechanism_tally(campaigns: Sequence[Campaign]) -> dict:
    """Per-arm mechanism aggregate (NOT a rate; a tally of search behavior, EN-008)."""
    by_seed = {c.seed: c for c in campaigns}
    return {
        "campaigns": len(campaigns),
        "seeds": sorted(by_seed),
        "eligible_observations_total": sum(c.eligible_observations for c in campaigns),
        "frames_observed_total": sum(c.frames_observed for c in campaigns),
        "unique_attempt_keys_total": sum(c.unique_attempt_keys for c in campaigns),
        "unique_attempt_keys_by_seed": {c.seed: c.unique_attempt_keys for c in campaigns},
        "unique_violation_fingerprints_total": sum(
            c.unique_violation_fingerprints for c in campaigns
        ),
        "retained_cases_by_seed": {c.seed: c.retained_cases for c in campaigns},
        "terminations_total": _sum_terminations(campaigns),
        "note": "mechanism tally over a small sample; not a rate or effectiveness claim (EN-008)",
    }


def _sum_terminations(campaigns: Sequence[Campaign]) -> dict[str, int]:
    total: dict[str, int] = {}
    for campaign in campaigns:
        for term, count in campaign.terminations.items():
            total[term] = total.get(term, 0) + count
    return total


def roll_up(campaigns: Sequence[Campaign]) -> dict:
    """Group campaigns by arm and roll each up with the shared right-censored engine."""
    arms: dict[str, list[Campaign]] = {}
    for campaign in campaigns:
        arms.setdefault(campaign.arm, []).append(campaign)

    arm_reports: dict[str, dict] = {}
    for arm, arm_campaigns in sorted(arms.items()):
        outcomes = [c.seed_outcome() for c in arm_campaigns]
        summary = right_censored_summary(outcomes)
        by_contract = {
            contract: right_censored_summary([c.contract_outcome(contract) for c in arm_campaigns])
            for contract in ("C0", "C1", "C2")
        }
        aborted = [c for c in arm_campaigns if c.aborted]
        non_aborted = [c for c in arm_campaigns if not c.aborted]
        arm_reports[arm] = {
            "is_state_aware_not_blind": arm in _STATE_AWARE_ARMS,
            "right_censored_any_contract": summary,
            "right_censored": summary,
            "by_contract": by_contract,
            "mechanism": _mechanism_tally(non_aborted),
            "fail_closed_aborts": {
                "count": len(aborted),
                "seeds": sorted(c.seed for c in aborted),
                "reasons": sorted({c.abort_reason or "" for c in aborted}),
                "note": (
                    "infrastructure-incomplete (observation-integrity STOP), excluded from the "
                    "complete-campaign denominator and reported separately (evaluation-protocol-v1)"
                ),
            },
        }

    return {
        "schema_version": 1,
        "classification": "m4-7-oras-go-self-discovery-right-censored",
        "target": "oras-go@v2.6.1 AFFECTED",
        "architecture": "arm64",
        "extractor_channel": (
            "oras-go is a compiled 3rd-party extractor: link calls cannot be interposed, so "
            "the feedback channel is a POST-EXTRACTION state SET frame "
            "(inodefence-boundary-attempt-v1) -- narrower than decompress's fs-wrap set and "
            "node-tar's ordered per-op channel; cleanly refused attempts are NOT observed "
            "(disclosed)"
        ),
        "hit_definition": (
            "registered hit = discovered_violation == any step contract_violated (generic "
            "C0/C1/C2 on before/after; oracle logic unchanged). Preregistered HIT = generic C1/C2"
        ),
        "contract_semantics": (
            "by_contract splits the registered any-contract hit: C0 = path-boundary confinement "
            "(the baseline contract, explicitly NOT InodeFence's novelty); C1 = object-identity "
            "confinement and C2 = external-effect noninterference (the identity/effect targets "
            "that carry the novelty). A C0 path escape is not an identity/effect discovery."
        ),
        "complete_definition": (
            "observations == eligible_observations == execution_budget (budget filled and every "
            "step an eligible observation); otherwise infrastructure-incomplete and excluded"
        ),
        "seeds": sorted({c.seed for c in campaigns}),
        "arms": arm_reports,
        "arm_contrast_note": (
            "A3-vs-A1 is a mechanism contrast over a small sample (1 seed/arm), not a rate or "
            "superiority claim; generality != self-discovery != effectiveness (EN-008)"
        ),
    }


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# M4.7 oras-go self-discovery — right-censored roll-up")
    lines.append("")
    lines.append(f"- target: {report['target']}")
    lines.append(f"- architecture: {report['architecture']}")
    lines.append(f"- channel: {report['extractor_channel']}")
    lines.append(f"- hit: {report['hit_definition']}")
    lines.append(f"- complete: {report['complete_definition']}")
    lines.append(f"- seeds: {report['seeds']}")
    lines.append("")
    for arm, arm_report in report["arms"].items():
        rc = arm_report["right_censored"]
        mech = arm_report["mechanism"]
        prop = rc["observed_proportion"]
        ci = prop["wilson_95_ci"]
        ci_text = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci[0] is not None else "[n/a]"
        lines.append(
            f"## {arm}"
            + (
                "  (state-aware, NOT blind — disclosed)"
                if arm_report["is_state_aware_not_blind"]
                else ""
            )
        )
        lines.append(
            f"- complete campaigns: {rc['number_complete_campaigns']} "
            f"(incomplete excluded: {rc['number_incomplete_excluded']} "
            f"{rc['incomplete_seeds']})"
        )
        lines.append(
            f"- any-contract hits (registered): {rc['number_observed_target']} / "
            f"{prop['denominator']}  Wilson95 {ci_text}"
        )
        for contract, label in (
            ("C0", "C0 path-boundary (baseline)"),
            ("C1", "C1 object-identity (novel)"),
            ("C2", "C2 external-effect (novel)"),
        ):
            crc = arm_report["by_contract"][contract]
            cprop = crc["observed_proportion"]
            cci = cprop["wilson_95_ci"]
            cci_text = f"[{cci[0]:.3f}, {cci[1]:.3f}]" if cci[0] is not None else "[n/a]"
            fh = crc["first_hit_executions_observed_only"]["values"]
            lines.append(
                f"  - {label}: {crc['number_observed_target']} / {cprop['denominator']} "
                f"Wilson95 {cci_text}" + (f"  first-hit {fh}" if fh else "")
            )
        lines.append(f"- right-censored (no-hit within budget): {rc['number_right_censored']}")
        aborts = arm_report["fail_closed_aborts"]
        lines.append(
            f"- fail-closed aborts (excluded from denominator): {aborts['count']} {aborts['seeds']}"
        )
        lines.append(
            f"- mechanism (not a rate): frames_observed {mech['frames_observed_total']}, "
            f"attempt_keys total {mech['unique_attempt_keys_total']} by_seed "
            f"{mech['unique_attempt_keys_by_seed']}; violation_fingerprints "
            f"{mech['unique_violation_fingerprints_total']}; "
            f"terminations {mech['terminations_total']}"
        )
        lines.append("")
    lines.append(f"> {report['arm_contrast_note']}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="+", help="evidence JSON paths (globs pre-expanded)")
    parser.add_argument("--json-out", type=Path, default=None, help="write roll-up JSON here")
    parser.add_argument("--md-out", type=Path, default=None, help="write markdown readout here")
    args = parser.parse_args(argv)

    campaigns = [load_campaign(path) for path in args.evidence]
    report = roll_up(campaigns)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out:
        args.json_out.write_text(text + "\n")
    markdown = render_markdown(report)
    if args.md_out:
        args.md_out.write_text(markdown)
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
