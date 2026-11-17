"""Exploration policies outside ``EffectSearchPolicy`` (#511, W4 2026-11-18; exploratory only).

An exploration policy is selected by ``EffectCampaignConfig.exploration_policy`` (default
``None``: nothing here runs and every existing campaign is byte-identical). It is a separate id
type on purpose: ``EffectSearchPolicy`` lives in a no-touch file and is not extended again (W4
ruling 7, D062 stays a one-time exception). Consequences, accepted by W4:

* the shared launchers (``scripts/run_effect_demo.py`` and the scripts that call it) cannot select
  it -- their ``--policy`` choices are ``EffectSearchPolicy`` values -- so it runs only where a
  caller builds the config itself (tests, synthetic producer); a real-target path needs a
  decision on the shared launcher (Jiwoong, memo #511 section 7.1);
* registered readers that key on ``search_policy`` alone (``rds_report``) cannot tell it apart;
  the G1 v2 gate reads the pair (``search_policy``, ``exploration_policy``).

``pre-violation-signal-v1-novelty-applied-split-v1``:

W4 (2026-11-18), the asymmetry with the registered S-u: the retention of this exploration
policy does not look at protected-object information; the registered S-u retention uses effect
keys that include the protected/external flag. This is a different retention rule, not "S-u
plus signals"; S-u is computed here for the recorded channel only.

* Retention: the seeds (base corpus) plus every executed case that shows a pre-violation signal
  (:mod:`inodefence.feedback.pre_violation`) not seen before in the campaign. Nothing else: no
  effect key (the effect signature reads the protected list), no violation fingerprint, no
  oracle verdict. So no feedback decision of this policy depends on the protected list or on
  sentinel names (W4 line; property-tested).
* Parent selection: uniform over the retained cases, in admission order.
* The step's recorded ``feedback`` (``EffectSearchDecision``) is the S-u diagnostic channel,
  computed by an S-u state kept for the record only -- the same channel every R/D/S arm records,
  so the records stay comparable. It decides nothing here; the policy's own admission is the
  ``exploration`` record (``signal_retained``).
* Scheduler: :class:`inodefence.effect_scheduler.PreViolationNoveltyScheduler` (binary reward on
  a new signal, credit split evenly over the applied operators of the execution).

It claims nothing about search performance: an arm comparison needs a preregistered experiment
(W4 ruling 8), and the product default is unchanged.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from inodefence.feedback.effect_search import (
    EffectSearchDecision,
    EffectSearchPolicy,
    EffectSearchState,
    EffectSearchStats,
)
from inodefence.feedback.pre_violation import PreViolationSignal, pre_violation_signals
from inodefence.model import ArchiveCase, EffectRunResult


class ExplorationPolicyId(StrEnum):
    PRE_VIOLATION_SIGNAL_NOVELTY = "pre-violation-signal-v1-novelty-applied-split-v1"


#: The ``search_policy`` a campaign must declare with each exploration policy: the recorded
#: diagnostic channel (``feedback``) and the arm label it extends.
EXPLORATION_BASE_SEARCH_POLICY: Mapping[ExplorationPolicyId, EffectSearchPolicy] = MappingProxyType(
    {
        ExplorationPolicyId.PRE_VIOLATION_SIGNAL_NOVELTY: (
            EffectSearchPolicy.S_U_STATE_RETENTION_UNIFORM
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ExplorationObservation:
    """What the exploration state decided for one executed case."""

    signals: tuple[PreViolationSignal, ...]
    new_signals: tuple[PreViolationSignal, ...]
    signal_retained: bool


class ExplorationSearchState:
    """Retention and parent selection of an exploration policy (see the module docstring)."""

    def __init__(self, initial_cases: Sequence[ArchiveCase], policy: ExplorationPolicyId) -> None:
        if not isinstance(policy, ExplorationPolicyId):
            raise ValueError("policy must be an ExplorationPolicyId")
        cases = tuple(initial_cases)
        self._record = EffectSearchState(cases, EXPLORATION_BASE_SEARCH_POLICY[policy])
        self._initial_cases = cases
        self._policy = policy
        self._signals: set[PreViolationSignal] = set()
        self._retained: list[ArchiveCase] = []
        self._retained_ids: set[str] = set()
        self._observations = 0
        self._last: ExplorationObservation | None = None

    @property
    def policy(self) -> ExplorationPolicyId:
        return self._policy

    @property
    def last(self) -> ExplorationObservation:
        if self._last is None:
            raise ValueError("no case has been considered yet")
        return self._last

    def consider(self, result: EffectRunResult) -> EffectSearchDecision:
        """Record the S-u diagnostic decision; admit by seed or new pre-violation signal."""
        decision = self._record.consider(result)
        is_seed = self._observations < len(self._initial_cases)
        self._observations += 1
        signals = pre_violation_signals(result.trace)
        new = tuple(signal for signal in signals if signal not in self._signals)
        self._signals.update(signals)
        case = result.base_result.case
        admit = (is_seed or bool(new)) and case.case_id not in self._retained_ids
        if admit:
            self._retained.append(case)
            self._retained_ids.add(case.case_id)
        self._last = ExplorationObservation(signals, new, admit and not is_seed)
        return decision

    def select_case(self, rng: random.Random) -> ArchiveCase:
        if self._observations < len(self._initial_cases):
            raise ValueError("parent selection requires a completed seed phase")
        if not self._retained:
            raise ValueError("cannot select a case from an empty corpus")
        return rng.choice(self._retained)

    @property
    def retained_case_ids(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self._retained)

    @property
    def unique_signals(self) -> int:
        return len(self._signals)

    @property
    def stats(self) -> EffectSearchStats:
        """The recorded channel's statistics, with this policy's retained-case count."""
        recorded = self._record.stats
        return EffectSearchStats(
            recorded.observations,
            recorded.feedback_eligible_observations,
            recorded.observation_failures,
            recorded.interesting_observations,
            len(self._retained),
            recorded.unique_full_states,
            recorded.unique_effect_keys,
            recorded.unique_violation_fingerprints,
        )
