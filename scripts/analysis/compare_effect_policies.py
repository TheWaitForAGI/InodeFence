"""Compare mutation selection of two search policies on the synthetic effect loop (P0-4).

Both campaigns share seed, budget, mutation policy and seed corpus; only the
search policy differs. The default pair P1_EFFECT_RETENTION vs P2_EFFECT_ADAPTIVE
shares corpus admission, so a divergence isolates the adaptive scheduler weights.
Results come from the synthetic producer, not node-tar.
"""

import argparse
import sys
from pathlib import Path

from scripts.run_effect_demo import synthetic_demo_report

from inodefence.effect_demo import compare_effect_campaign_reports, render_effect_campaign_report
from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy


def synthetic_policy_comparison(
    seed: int,
    budget: int,
    mutation_policy: MutationPolicy,
    left: EffectSearchPolicy,
    right: EffectSearchPolicy,
) -> dict[str, object]:
    return compare_effect_campaign_reports(
        synthetic_demo_report(seed, budget, left, mutation_policy),
        synthetic_demo_report(seed, budget, right, mutation_policy),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    policies = tuple(policy.name for policy in EffectSearchPolicy)
    parser.add_argument("--left", choices=policies, default="P1_EFFECT_RETENTION")
    parser.add_argument("--right", choices=policies, default="P2_EFFECT_ADAPTIVE")
    parser.add_argument(
        "--mutation-policy",
        choices=tuple(policy.value for policy in MutationPolicy),
        default=MutationPolicy.M1.value,
    )
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)
    comparison = synthetic_policy_comparison(
        args.seed,
        args.budget,
        MutationPolicy(args.mutation_policy),
        EffectSearchPolicy[args.left],
        EffectSearchPolicy[args.right],
    )
    text = render_effect_campaign_report(comparison)
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="ascii")
        print(f"policy comparison: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
