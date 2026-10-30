"""M4.5 decompress self-discovery right-censored roll-up (A3 state-aware vs A1 random).

Reads native decompress self-discovery evidence JSONs (``decompress_campaign_schema``
1, as written by ``decompress_effect_campaign.build_report``), groups them by arm, and
produces the per-arm right-censored roll-up via ``evaluation.right_censored`` -- the same
Wilson engine the M3.3 control roll-up uses. It is additive: it imports the shared engine,
modifies no existing module, and re-derives none of the runtime lane's determination.

Honest framing, fixed before running (evaluation-protocol-v1 / audit EN-008):

* ``hit`` = ``discovered_violation`` = any step with ``contract_violated`` true (the
  generic C0/C1/C2 oracle fired on the before/after snapshots; oracle logic unchanged).
  ``first_hit_executions`` is the 1-based index of that first step.
* ``complete`` = ``eligible_observations == execution_budget``: every step produced an
  eligible SUCCESS/REJECTED observation. A campaign with any ineligible observation is
  infrastructure-incomplete, excluded from the hit denominator, and reported separately
  (it is not a within-budget no-hit; it never silently grows the denominator).
* A3 (state-aware identity) composes mutation targets from observed snapshot names
  (``outside``, ``sentinel.txt``) -- so it is NOT blind; this is disclosed. A1 (random)
  has no observation tokens and is the floor. No target path/identifier/answer seed and
  no proximity reward is hardcoded in the mutation vocabulary or the oracle.
* arch = x86_64 on this host; the mac control runs arm64. Cross-arch byte-identity for
  decompress is NOT claimed -- arch is disclosed as a variable.
* self-discovery (this right-censored result) != generality (oracle/adapter reuse) !=
  effectiveness (rate superiority). This reports no effectiveness ranking; the A3-vs-A1
  contrast is a mechanism tally over a small sample, not a rate claim.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from inodefence.evaluation.right_censored import (
    SeedOutcome,
    right_censored_summary,
)

_SCHEMA = 1
_ELIGIBLE_TERMINATIONS = ("success", "rejected")

# Known arm policy strings -> stable arm label. An unknown policy falls back to its own
# string so the roll-up still groups it; it never silently merges two arms.
_ARM_LABELS = {
    "uniform-generic-m1-state-aware-escape-hardlink-v1": "A3-state-aware",
    "uniform-generic-m1-state-aware-escape-hardlink-blind-v1": "A3-blind",
    "uniform-generic-v1": "A1-random",
}

_STATE_AWARE_ARMS = frozenset({"A3-state-aware"})


@dataclass(frozen=True, slots=True)
class Campaign:
    """One native decompress self-discovery campaign, as recorded in its evidence JSON."""

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

    @property
    def complete(self) -> bool:
        """A complete campaign ran its full budget with every observation eligible."""
        return self.eligible_observations == self.budget and self.observations == self.budget

    def seed_outcome(self) -> SeedOutcome:
        hit = self.discovered_violation and self.complete
        return SeedOutcome(
            seed=self.seed,
            budget=self.budget,
            complete=self.complete,
            hit=hit,
            first_hit_executions=self.first_hit_index_one_based if hit else None,
        )


def _arm_for(policy: str) -> str:
    return _ARM_LABELS.get(policy, policy)


def load_campaign(path: str | Path) -> Campaign:
    """Parse one evidence JSON into a ``Campaign``; raise on an unexpected schema."""
    data = json.loads(Path(path).read_text())
    if data.get("decompress_campaign_schema") != _SCHEMA:
        raise ValueError(f"{path}: not decompress_campaign_schema {_SCHEMA}")
    config = data["config"]
    stats = data["final_stats"]
    steps = data["steps"]
    terminations: dict[str, int] = {}
    first_hit: int | None = None
    for step in steps:
        term = step.get("termination")
        if term is not None:
            terminations[term] = terminations.get(term, 0) + 1
        if first_hit is None and step.get("contract_violated"):
            # 1-based execution index of the first contract violation.
            first_hit = int(step["index"]) + 1
    budget = int(config["execution_budget"])
    policy = str(config["mutation_policy"])
    return Campaign(
        path=str(path),
        seed=int(config["random_seed"]),
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
    )


def _mechanism_tally(campaigns: Sequence[Campaign]) -> dict:
    """Per-arm mechanism aggregate (NOT a rate; a tally of search behavior, EN-008)."""
    by_seed = {c.seed: c for c in campaigns}
    return {
        "campaigns": len(campaigns),
        "seeds": sorted(by_seed),
        "eligible_observations_total": sum(c.eligible_observations for c in campaigns),
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
            total[term] = total.get(term, 0) + 1 * count
    return total


def roll_up(campaigns: Sequence[Campaign], *, external_seed_sets: dict | None = None) -> dict:
    """Group campaigns by arm and roll each up with the shared right-censored engine."""
    arms: dict[str, list[Campaign]] = {}
    for campaign in campaigns:
        arms.setdefault(campaign.arm, []).append(campaign)

    arm_reports: dict[str, dict] = {}
    for arm, arm_campaigns in sorted(arms.items()):
        outcomes = [c.seed_outcome() for c in arm_campaigns]
        summary = right_censored_summary(outcomes)
        arm_reports[arm] = {
            "is_state_aware_not_blind": arm in _STATE_AWARE_ARMS,
            "right_censored": summary,
            "mechanism": _mechanism_tally(arm_campaigns),
        }

    win_seeds = sorted({c.seed for c in campaigns})
    report = {
        "schema_version": 1,
        "classification": "m4-5-decompress-self-discovery-right-censored",
        "target": "decompress@4.2.1 AFFECTED",
        "architecture": "x86_64",
        "arch_disclosure": (
            "x86_64 (this host); the paired mac control runs arm64. decompress cross-arch "
            "byte-identity is NOT claimed -- arch is a disclosed variable."
        ),
        "hit_definition": (
            "discovered_violation == any step contract_violated (generic C0/C1/C2 on "
            "before/after; oracle logic unchanged)"
        ),
        "complete_definition": (
            "eligible_observations == execution_budget (every step an eligible "
            "SUCCESS/REJECTED observation); otherwise infrastructure-incomplete and excluded"
        ),
        "windows_host_seeds": win_seeds,
        "arms": arm_reports,
        "arm_contrast_note": (
            "A3-vs-A1 is a mechanism contrast over a small sample, not a rate or "
            "superiority claim; generality != self-discovery != effectiveness (EN-008)"
        ),
    }
    if external_seed_sets is not None:
        report["combined_denominator"] = _combined_denominator(win_seeds, external_seed_sets)
    return report


def _combined_denominator(win_seeds: Sequence[int], external_seed_sets: dict) -> dict:
    """Record the win + mac seed sets and assert zero overlap for the final combined roll-up.

    This does NOT fabricate the mac arm's numbers; it only states the union denominator and
    checks disjointness so whoever finally sums both hosts can do so without double-counting.
    """
    win = set(win_seeds)
    overlaps = {name: sorted(win.intersection(seeds)) for name, seeds in external_seed_sets.items()}
    any_overlap = any(overlaps.values())
    all_external = sorted({s for seeds in external_seed_sets.values() for s in seeds})
    return {
        "windows_seeds": sorted(win),
        "external_seed_sets": {k: sorted(v) for k, v in external_seed_sets.items()},
        "overlap_with_external": overlaps,
        "disjoint": not any_overlap,
        "combined_seed_count": len(win | set(all_external)) if not any_overlap else None,
        "note": (
            "final M4.5 judgment unions mac (arm64) and windows (x86_64) seeds; this only "
            "states the denominator and checks overlap -- it does not sum the mac numbers"
        ),
    }


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# M4.5 decompress self-discovery — right-censored roll-up")
    lines.append("")
    lines.append(f"- target: {report['target']}")
    lines.append(f"- architecture: {report['architecture']}")
    lines.append(f"- hit: {report['hit_definition']}")
    lines.append(f"- complete: {report['complete_definition']}")
    lines.append(
        f"- windows host seeds ({len(report['windows_host_seeds'])}): "
        f"{report['windows_host_seeds']}"
    )
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
            f"- clean exact hits: {rc['number_observed_target']} / "
            f"{prop['denominator']}  Wilson95 {ci_text}"
        )
        lines.append(f"- right-censored (no-hit within budget): {rc['number_right_censored']}")
        if rc["first_hit_executions_observed_only"]["values"]:
            lines.append(
                f"- first-hit executions (observed only): "
                f"{rc['first_hit_executions_observed_only']['values']}"
            )
        lines.append(
            f"- mechanism (not a rate): attempt_keys total "
            f"{mech['unique_attempt_keys_total']} by_seed "
            f"{mech['unique_attempt_keys_by_seed']}; terminations "
            f"{mech['terminations_total']}"
        )
        lines.append("")
    lines.append(f"> {report['arm_contrast_note']}")
    if "combined_denominator" in report:
        cd = report["combined_denominator"]
        lines.append("")
        lines.append("## combined denominator (mac + windows)")
        lines.append(f"- disjoint: {cd['disjoint']}  overlap: {cd['overlap_with_external']}")
        lines.append(f"- combined seed count: {cd['combined_seed_count']}")
        lines.append(f"- {cd['note']}")
    return "\n".join(lines) + "\n"


def _parse_external(value: str | None) -> dict | None:
    if not value:
        return None
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise ValueError("--external-seed-sets must be a JSON object of name -> [seeds]")
    return {str(k): [int(s) for s in v] for k, v in raw.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="+", help="evidence JSON paths (globs pre-expanded)")
    parser.add_argument("--json-out", type=Path, default=None, help="write roll-up JSON here")
    parser.add_argument("--md-out", type=Path, default=None, help="write markdown readout here")
    parser.add_argument(
        "--external-seed-sets",
        default=None,
        help="JSON object of name -> [seeds] (e.g. the mac reserved set) for the combined "
        "denominator overlap check; does NOT sum the external arm's numbers",
    )
    args = parser.parse_args(argv)

    campaigns = [load_campaign(path) for path in args.evidence]
    report = roll_up(campaigns, external_seed_sets=_parse_external(args.external_seed_sets))
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
