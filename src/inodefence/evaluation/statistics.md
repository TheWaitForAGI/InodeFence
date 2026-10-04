# Statistical summary helpers

`python -m inodefence.evaluation.statistics EXPORT... --protocol-version VERSION`
verifies every raw export and requires dataset compatibility before pooling.
Seed variation requires `--allow-seed-variation`. Different targets/runtime
profiles must be selected as explicit compatible strata first. The dataset report
and manifest SHA-256 values bind every aggregate to input evidence. Corrupt,
unknown-source, duplicate or incompatible runs raise rather than being excluded.

The JSON records process success proportion by verified execution count and
any-contract observation proportion by valid completed run count. Both include
their numerator/denominator. These are distinct metrics, neither a rediscovery
classification. No-hit runs stay in the observation denominator and are
right-censored at their recorded execution budgets. First-hit median, quartiles,
IQR and min/max use only observed runs, one-based execution counts and inclusive
linear quantiles at position `(n-1)*p`. No-hit indices are never invented; no
uncensored full-population median or survival estimate is asserted. Empty input
is an explicit template with null proportions and distribution values.

Completed-only exports cannot describe aborted attempts: invalid run count is
null, not an inferred zero. `--repetitions DIRECTORY` verifies the plan, terminal
records, completed exports and failure ledgers. Every slot must be resolved before
aggregation. FAILED/INVALID slots are reported separately and excluded from the
valid observation denominator; interrupted reservations remain invalid metadata,
not evidence of how many target executions occurred. A failure-only plan has no
valid observations and null proportions. `--plan-sha256` optionally anchors plan
integrity. `--format markdown` renders counts and censoring semantics for people.
Raw experiment observations, target qualification and paper claims remain separate.
