from scripts.run_effect_demo import synthetic_demo_json

from inodefence.feedback import EffectSearchPolicy


def test_synthetic_demo_json_is_byte_identical_for_same_seed() -> None:
    first = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE)
    second = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE)

    assert first == second
