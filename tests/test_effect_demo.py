from scripts.run_effect_demo import synthetic_demo_json

from inodefence.feedback import EffectSearchPolicy
from inodefence.mutator import MutationPolicy


def test_synthetic_demo_json_is_byte_identical_for_same_seed() -> None:
    first = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)
    second = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)

    assert first == second
