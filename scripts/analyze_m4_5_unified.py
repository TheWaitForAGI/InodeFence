"""M4.5 decompress self-discovery UNIFIED right-censored roll-up (mac arm64 + windows x86_64).

The two M4.5 hosts ran disjoint seed sets of the same pre-registered large-budget
(1500) decompress self-discovery campaign: windows x86_64 ran ``{500..509}`` and mac
arm64 ran ``{11, 85, 163, 211, 307, 401}``. The windows per-contract roll-up is already
published in the repo (``m4-5-decompress-selfdiscover-win-v1.json``); its raw is
windows-host-local and not in the repo. The mac raw is on this host. This script assembles
the final M4.5 judgment: it pools both hosts into one right-censored by_contract (C0/C1/C2)
roll-up through the SAME ``evaluation.right_censored`` Wilson engine, after confirming the
seed sets are disjoint.

It is additive: it imports the shared Wilson engine and the reviewed per-campaign loader
from ``analyze_m4_5_selfdiscover``; it modifies no existing module and re-derives none of
the runtime lane's determination. For the windows side -- whose raw is absent here -- it
reconstructs per-seed ``SeedOutcome`` facts from the published windows roll-up and then
ASSERTS the reconstruction reproduces that roll-up's own numbers, so the union never trusts
an untracked transcription.

Honest framing, fixed before running (evaluation-protocol-v1 / audit EN-008):

* ``hit`` (by contract) = a complete campaign with >=1 step whose generic oracle flagged
  exactly that contract (C0/C1/C2; oracle logic unchanged). C0 = path-boundary confinement
  (the baseline contract, explicitly NOT InodeFence's novelty); C1 = object-identity and
  C2 = external-effect noninterference (the identity/effect targets that carry the novelty).
* ``complete`` = the campaign filled its budget with every step an eligible observation; a
  fail-closed infrastructure abort is infrastructure-incomplete, excluded from the hit
  denominator, and reported separately (never a within-budget no-hit).
* A no-hit complete campaign is right-censored at its budget (``> N``), never imputed.
* self-discovery (this right-censored result: the loop runs on a 2nd extractor and reaches
  a boundary violation without a hardcoded PoC/target) != generality (oracle/adapter reuse)
  != effectiveness (rate superiority). No effectiveness ranking is reported; the A3-vs-A1
  split and the mechanism tallies are search behavior over a small sample, not a rate claim.
* arch is a DISCLOSED variable: the union treats mac arm64 and windows x86_64 as two
  independent repetitions of the same pre-registered protocol. decompress cross-arch
  byte-identity is NOT claimed.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections.abc import Sequence
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _p in (_REPO / "src", _REPO):
    if str(_p) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(_p))

from scripts.analyze_m4_5_selfdiscover import (  # noqa: E402
    Campaign,
    load_campaign,
    roll_up,
)

from inodefence.evaluation.right_censored import (  # noqa: E402
    SeedOutcome,
    right_censored_summary,
)

_CONTRACTS = ("C0", "C1", "C2")
_ARMS = ("A1-random", "A3-state-aware")
_REGISTERED_BUDGET = 1500

# A fail-closed abort stub carries no config/steps, so its seed+arm come from the filename.
# The base loader only recognizes the windows ``-m45-`` token; the mac host writes ``-m4p-``.
_STUB_RUN_ID_RE = re.compile(r"-(?:m45|m4p)-(sa|a1)-s(\d+)\.json$")
_STUB_ARM = {"sa": "A3-state-aware", "a1": "A1-random"}


def load_campaign_any(path: str | Path, *, aborted_budget: int = _REGISTERED_BUDGET) -> Campaign:
    """Load a campaign, tolerating the mac ``-m4p-`` abort-stub filename.

    Non-stub evidence is delegated to the reviewed ``load_campaign`` (seed/arm from config).
    An abort stub (no config/steps) is built here with seed/arm from the general filename
    regex, mirroring the base loader's stub construction, so mac stubs do not crash it.
    """
    data = json.loads(Path(path).read_text())
    if data.get("decompress_campaign_schema") != 1:
        raise ValueError(f"{path}: not decompress_campaign_schema 1")
    if "aborted" not in data and "config" in data:
        return load_campaign(path)
    match = _STUB_RUN_ID_RE.search(Path(path).name)
    if match is None:
        raise ValueError(f"{path}: abort stub with no config and unparseable RUN_ID")
    arm, seed = _STUB_ARM[match.group(1)], int(match.group(2))
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


def reconstruct_windows_outcomes(win: dict, arm: str, contract: str) -> list[SeedOutcome]:
    """Rebuild one arm/contract's per-seed ``SeedOutcome`` list from the published win roll-up.

    The windows raw is not on this host, so the union is built from the repo roll-up. For an
    arm/contract the roll-up gives the complete count, the censored (no-hit) seeds, the
    observed first-hit values and the arm's abort seeds -- enough to rebuild each seed's
    outcome exactly. ``assert_matches_windows`` then checks the rebuild reproduces the
    roll-up's own numbers, so a silent transcription error cannot slip into the union.
    """
    block = win["arms"][arm]["by_contract"][contract]
    all_seeds = set(win["windows_host_seeds"])
    aborts = sorted(win["arms"][arm]["fail_closed_aborts"]["seeds"])
    complete_seeds = sorted(all_seeds - set(aborts))
    censored_seeds = sorted(entry["seed"] for entry in block["censored"])
    budget = block["censored"][0]["budget"] if block["censored"] else _REGISTERED_BUDGET
    hit_seeds = [seed for seed in complete_seeds if seed not in set(censored_seeds)]
    first_hits = [int(v) for v in block["first_hit_executions_observed_only"]["values"]]
    if len(hit_seeds) != len(first_hits):
        raise ValueError(
            f"win {arm}/{contract}: {len(hit_seeds)} hit seeds vs {len(first_hits)} first-hits"
        )
    outcomes: list[SeedOutcome] = []
    for seed in aborts:
        outcomes.append(
            SeedOutcome(
                seed=seed, budget=budget, complete=False, hit=False, first_hit_executions=None
            )
        )
    for seed in censored_seeds:
        outcomes.append(
            SeedOutcome(
                seed=seed, budget=budget, complete=True, hit=False, first_hit_executions=None
            )
        )
    for seed, first_hit in zip(hit_seeds, first_hits, strict=True):
        outcomes.append(
            SeedOutcome(
                seed=seed, budget=budget, complete=True, hit=True, first_hit_executions=first_hit
            )
        )
    return outcomes


def assert_matches_windows(
    win: dict, arm: str, contract: str, rebuilt: Sequence[SeedOutcome]
) -> None:
    """Fail loudly unless the reconstructed outcomes reproduce the published win numbers."""
    block = win["arms"][arm]["by_contract"][contract]
    summary = right_censored_summary(rebuilt)
    checks = {
        "number_complete_campaigns": block["number_complete_campaigns"],
        "number_observed_target": block["number_observed_target"],
        "number_right_censored": block["number_right_censored"],
        "number_incomplete_excluded": block["number_incomplete_excluded"],
    }
    for key, expected in checks.items():
        if summary[key] != expected:
            raise ValueError(
                f"win {arm}/{contract}: rebuilt {key}={summary[key]} != published {expected}"
            )
    want = block["observed_proportion"]["wilson_95_ci"]
    got = summary["observed_proportion"]["wilson_95_ci"]
    for a, b in zip(want, got, strict=True):
        if a is None or b is None:
            if a is not b:
                raise ValueError(f"win {arm}/{contract}: wilson None mismatch {want} vs {got}")
        elif abs(a - b) > 1e-9:
            raise ValueError(f"win {arm}/{contract}: wilson {got} != published {want}")


def _compact(summary: dict) -> dict:
    """A small per-host/unified view of one right-censored summary."""
    prop = summary["observed_proportion"]
    return {
        "hits": summary["number_observed_target"],
        "complete": summary["number_complete_campaigns"],
        "incomplete_excluded": summary["number_incomplete_excluded"],
        "wilson_95_ci": prop["wilson_95_ci"],
        "right_censored_seeds": [entry["seed"] for entry in summary["censored"]],
        "first_hit_executions_observed_only": summary["first_hit_executions_observed_only"][
            "values"
        ],
    }


def unify(mac_campaigns: Sequence[Campaign], win: dict, *, mac_raw_pointer: str) -> dict:
    """Assemble the unified mac+windows by_contract right-censored verdict."""
    mac_by_arm: dict[str, list[Campaign]] = {}
    for campaign in mac_campaigns:
        mac_by_arm.setdefault(campaign.arm, []).append(campaign)

    mac_seeds = sorted({c.seed for c in mac_campaigns})
    win_seeds = sorted(win["windows_host_seeds"])
    overlap = sorted(set(mac_seeds) & set(win_seeds))

    unified_by_arm: dict[str, dict] = {}
    pooled_novelty: dict[str, list[SeedOutcome]] = {contract: [] for contract in ("C1", "C2")}
    for arm in _ARMS:
        arm_campaigns = mac_by_arm.get(arm, [])
        by_contract: dict[str, dict] = {}
        host_views: dict[str, dict] = {"mac": {}, "windows": {}}
        for contract in _CONTRACTS:
            mac_outcomes = [c.contract_outcome(contract) for c in arm_campaigns]
            win_outcomes = reconstruct_windows_outcomes(win, arm, contract)
            assert_matches_windows(win, arm, contract, win_outcomes)
            host_views["mac"][contract] = _compact(right_censored_summary(mac_outcomes))
            host_views["windows"][contract] = _compact(right_censored_summary(win_outcomes))
            pooled = right_censored_summary([*mac_outcomes, *win_outcomes])
            by_contract[contract] = pooled
            if contract in pooled_novelty:
                pooled_novelty[contract].extend([*mac_outcomes, *win_outcomes])
        mac_aborts = sorted(c.seed for c in arm_campaigns if c.aborted)
        win_aborts = sorted(win["arms"][arm]["fail_closed_aborts"]["seeds"])
        unified_by_arm[arm] = {
            "is_state_aware_not_blind": arm == "A3-state-aware",
            "hosts": host_views,
            "by_contract": by_contract,
            "fail_closed_aborts": {
                "mac_seeds": mac_aborts,
                "windows_seeds": win_aborts,
                "combined_count": len(mac_aborts) + len(win_aborts),
                "note": (
                    "infrastructure-incomplete (observation-integrity STOP), excluded from the "
                    "complete-campaign denominator and reported separately (evaluation-protocol-v1)"
                ),
            },
        }

    novelty_overall: dict[str, object] = {
        contract: right_censored_summary(outcomes) for contract, outcomes in pooled_novelty.items()
    }
    novelty_overall["note"] = (
        "pools BOTH arms (A1+A3) for the identity/effect novelty targets; legitimate here only "
        "because the pooled result is a 0-hit negative and no arm or effectiveness claim is made "
        "(EN-008). It is the single honest-negative headline for C1/C2 across all powered "
        "complete campaigns on both architectures."
    )

    return {
        "schema_version": 1,
        "classification": "m4-5-decompress-self-discovery-unified-right-censored",
        "target": "decompress@4.2.1 AFFECTED",
        "hit_definition": (
            "per-contract hit = a complete campaign with >=1 step whose generic oracle flagged "
            "that contract (C0/C1/C2 on before/after; oracle logic unchanged)"
        ),
        "contract_semantics": (
            "C0 = path-boundary confinement (baseline, explicitly NOT InodeFence's novelty); "
            "C1 = object-identity confinement and C2 = external-effect noninterference (the "
            "identity/effect novelty targets). A C0 path escape is not an identity/effect "
            "discovery."
        ),
        "complete_definition": (
            "observations == eligible_observations == execution_budget; otherwise "
            "infrastructure-incomplete and excluded from the denominator (reported separately)"
        ),
        "arch_disclosure": (
            "mac arm64 + windows x86_64 pooled as two independent repetitions of one "
            "pre-registered protocol; decompress cross-arch byte-identity is NOT claimed -- arch "
            "is a disclosed variable"
        ),
        "hosts": {
            "mac": {
                "architecture": "arm64",
                "seeds": mac_seeds,
                "raw_pointer": mac_raw_pointer,
                "roll_up": roll_up(list(mac_campaigns)),
            },
            "windows": {
                "architecture": "x86_64",
                "seeds": win_seeds,
                "raw_pointer": "windows-host-local (not in repo); see rollup_source",
                "rollup_source": "experiments/summaries/m4-5-decompress-selfdiscover-win-v1.json",
            },
        },
        "combined_denominator": {
            "mac_seeds": mac_seeds,
            "windows_seeds": win_seeds,
            "overlap": overlap,
            "disjoint": not overlap,
            "combined_seed_count": len(set(mac_seeds) | set(win_seeds)) if not overlap else None,
            "note": "final M4.5 judgment unions mac (arm64) and windows (x86_64) disjoint seeds",
        },
        "unified_by_arm": unified_by_arm,
        "unified_novelty_overall": novelty_overall,
        "arm_contrast_note": (
            "A3-vs-A1 is a mechanism contrast over a small sample, not a rate or superiority "
            "claim; generality != self-discovery != effectiveness (EN-008)"
        ),
    }


def render_markdown(report: dict) -> str:
    """A plain readout of the unified roll-up for verification (not the curated summary)."""
    lines: list[str] = [
        "# M4.5 decompress self-discovery — UNIFIED (mac arm64 + windows x86_64)",
        "",
    ]
    cd = report["combined_denominator"]
    lines.append(
        f"- disjoint seeds: {cd['disjoint']}  overlap={cd['overlap']}  "
        f"combined={cd['combined_seed_count']}"
    )
    lines.append(f"- mac seeds {cd['mac_seeds']} | windows seeds {cd['windows_seeds']}")
    lines.append("")
    for arm, block in report["unified_by_arm"].items():
        tag = "  (state-aware, NOT blind — disclosed)" if block["is_state_aware_not_blind"] else ""
        lines.append(f"## {arm}{tag}")
        for contract, label in (
            ("C0", "C0 path-boundary (baseline)"),
            ("C1", "C1 object-identity (novel)"),
            ("C2", "C2 external-effect (novel)"),
        ):
            mac = block["hosts"]["mac"][contract]
            win = block["hosts"]["windows"][contract]
            uni = block["by_contract"][contract]
            prop = uni["observed_proportion"]
            ci = prop["wilson_95_ci"]
            ci_text = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci[0] is not None else "[n/a]"
            lines.append(
                f"  - {label}: mac {mac['hits']}/{mac['complete']} + "
                f"win {win['hits']}/{win['complete']} = "
                f"**{prop['numerator']}/{prop['denominator']}** Wilson95 {ci_text}"
            )
        ab = block["fail_closed_aborts"]
        lines.append(
            f"  - aborts (excluded): mac {ab['mac_seeds']} + win {ab['windows_seeds']} "
            f"= {ab['combined_count']}"
        )
        lines.append("")
    overall = report["unified_novelty_overall"]
    for contract in ("C1", "C2"):
        prop = overall[contract]["observed_proportion"]
        ci = prop["wilson_95_ci"]
        ci_text = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci[0] is not None else "[n/a]"
        lines.append(
            f"- novelty overall (both arms pooled) {contract}: "
            f"{prop['numerator']}/{prop['denominator']} Wilson95 {ci_text}"
        )
    lines.append("")
    lines.append(f"> {report['arm_contrast_note']}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mac-glob",
        default=str(Path.home() / "inodefence-evidence/m4-powered-20261030/*m4p-*.json"),
        help="glob for the mac M4.5 raw evidence JSONs",
    )
    parser.add_argument(
        "--windows-rollup",
        type=Path,
        default=_REPO / "experiments/summaries/m4-5-decompress-selfdiscover-win-v1.json",
        help="published windows roll-up JSON (repo)",
    )
    parser.add_argument(
        "--json-out", type=Path, default=None, help="write unified roll-up JSON here"
    )
    args = parser.parse_args(argv)

    mac_paths = sorted(glob.glob(args.mac_glob))
    if not mac_paths:
        raise SystemExit(f"no mac evidence matched {args.mac_glob!r}")
    mac_campaigns = [load_campaign_any(path) for path in mac_paths]
    win = json.loads(Path(args.windows_rollup).read_text())
    report = unify(mac_campaigns, win, mac_raw_pointer=args.mac_glob)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
