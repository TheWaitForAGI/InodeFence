"""P0-5 effect loop demo: seed -> producer -> oracle -> feedback -> next mutation.

Only the synthetic producer runs here; its results are fixtures, not node-tar
evidence. Native runs belong inside the controller (container_host effect-demo).
"""

import argparse
import sys
from pathlib import Path

from inodefence.effect_campaign import EffectCampaignConfig, run_effect_campaign
from inodefence.effect_demo import effect_campaign_report, render_effect_campaign_report
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus

NATIVE_UNAVAILABLE = (
    "native producer is not runnable from this entrypoint: "
    "실제 실행은 controller 안에서 container_host effect-demo 모드로 (다음 PR)"
)


def synthetic_demo_json(seed: int, budget: int, policy: EffectSearchPolicy) -> str:
    config = EffectCampaignConfig(random_seed=seed, execution_budget=budget, search_policy=policy)
    result = run_effect_campaign(minimal_seed_corpus(), synthetic_effect_result, config)
    return render_effect_campaign_report(effect_campaign_report(result, "synthetic"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", choices=("synthetic", "native"), default="synthetic")
    parser.add_argument(
        "--policy",
        choices=tuple(policy.value for policy in EffectSearchPolicy),
        default=EffectSearchPolicy.P2_EFFECT_ADAPTIVE.value,
    )
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args(argv)
    if args.producer == "native":
        print(NATIVE_UNAVAILABLE, file=sys.stderr)
        return 2
    text = synthetic_demo_json(args.seed, args.budget, EffectSearchPolicy(args.policy))
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="ascii")
        print(f"producer=synthetic steps={args.budget} report={args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
