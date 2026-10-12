# Transition mutation scheduler v1

## Status

- Stable mutation operator identity and inspectable attempts: **IMPLEMENTED**, **TESTED**
- Legacy uniform dispatch RNG compatibility: **TESTED**
- Transition-adaptive bounded integer scheduler: **IMPLEMENTED**, **TESTED**
- Native node-tar transition campaign: **NOT_RUN** because entry completion observation is not qualified
- Search-effectiveness claim: **NOT_RUN**, **HYPOTHESIS**

This document defines operator selection and outcome evidence. It contains no
target version, CVE identifier, known proof-of-concept bytes or exploit recipe.

## Stable operator vocabulary

`MutationOperatorId` fixes the existing eight slots in this order:

1. `add_entry`
2. `remove_entry`
3. `duplicate_entry`
4. `reorder_entries`
5. `mutate_path`
6. `add_hardlink`
7. `add_symlink`
8. `mutate_link_target`

`MutationAttempt` records the selected ID, mutation policy, parent case ID,
child case and whether the child differs from the parent. An inapplicable
operator is one recorded attempt with `applied=False`; it is not retried.

The existing `mutate()` and `mutate_with_policy()` APIs remain compatibility
wrappers. Their uniform dispatch still calls `rng.choice()` with the original
function table and derives the stable ID afterward. This preserves the previous
stdlib `random.Random` draw and custom test-double behavior. Explicit scheduler
dispatch uses the same ordered operator slots and then calls `apply_operator()`.
A3 reorder slots still consume the operator's draws and discard its result.

## Schedulers

`UniformMutationScheduler` gives every slot integer weight 1 and never changes
weights after an outcome. P0 and P1 use this scheduler.

`TransitionAdaptiveScheduler` starts every slot at integer weight 1, caps every
weight at 8 and selects with one caller-owned `rng.randrange(sum(weights))` draw
over the stable cumulative order. After the child has been observed:

- one or more new `TransitionFeedbackKey` values give reward 1;
- no new transition key gives reward 0;
- reward increments only the selected slot, capped at 8;
- new violation fingerprints are recorded as diagnostics and do not affect weight.

The reward is deliberately binary per attempt. The number of new keys cannot
amplify one execution's reward. Transition novelty is not a vulnerability result.

## Evidence

Every mutation step records `MutationSchedulerEvidence` containing the selected
operator, weights before selection, selected weight, new transition keys, new
violation fingerprints, integer reward, weights after update, parent case ID and
child case ID. The evidence makes deterministic replay and per-operator yield
metrics possible without inspecting mutable scheduler state.

## Causal policies

| Policy | Retention | Scheduler |
| --- | --- | --- |
| P0 `final-state-v3-or-violation-v1-uniform-mutation-v1` | final state or violation novelty | uniform |
| P1 `transition-v1-or-violation-v1-uniform-mutation-v1` | transition or violation novelty | uniform |
| P2 `transition-v1-or-violation-v1-adaptive-mutation-v1` | same as P1 | transition reward, bounded adaptive weights |

P1 versus P0 isolates the retention feedback variable. P2 versus P1 isolates
the operator scheduler variable. These are executable infrastructure policies,
not evidence that either hypothesis is true.

## Qualification boundary

The scheduler consumes generic normalized transition keys only. It imports no
node-tar adapter and does not infer a reward from raw inode numbers, target
versions or oracle verdicts. The in-memory campaign still requires a caller-owned
`TransitionRunResult` producer because native node-tar entry completion is
`NOT_IMPLEMENTED`; no formal benchmark is made ready by this component.
