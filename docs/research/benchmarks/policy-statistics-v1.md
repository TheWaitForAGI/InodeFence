# Compatible policy observation statistics v1

`summarize_policy_statistics(members, allow_seed_variation=False)` first validates
the complete evaluation-bound policy dataset. Incompatible or stratified input
raises; no member is silently removed and different policies are never pooled.
Explicit independent seed variation is optional. Every raw/config binding is
reread with the just-verified digest before shared summary arithmetic runs.

Schema-v1 JSON links original binding/manifest digests and evaluation config IDs.
It reports valid completed runs, total verified executions, process-success
proportion with execution denominator, and any-contract observation proportion
with valid-run denominator. No-hit runs stay in that denominator and are explicitly
right-censored at their recorded budget. No hit index or duration is imputed.

First-hit median/Q1/Q3/IQR/min/max are conditional on runs with an observation,
using one-based execution counts and inclusive linear quantiles at `(n-1)*p`.
They are not a full-population survival median. Empty input produces a template
with null ratios/distribution, zero valid runs and no fabricated measurements.
Invalid-run count is null because completed-only policy bundles contain no
attempt ledger; it is not zero and cannot be inferred from missing directories.
Contract observations do not classify benchmark rediscovery.

CLI: `python -m inodefence.evaluation.policy_statistics DIRECTORY... --format json|markdown`
with optional `--allow-seed-variation`. Legacy statistics and failure-aware legacy
repetition metadata retain their formats and values. No automatic execution or
policy scheduler is introduced. Qualification/authorship/operator compliance and
paper readiness remain separate requirements. Tests execute benign initial cases
only; synthetic source/status/contract arithmetic is explicitly unit evidence.
