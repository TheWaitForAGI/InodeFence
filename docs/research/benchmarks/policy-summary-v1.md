# Verified policy observation summary v1

`summarize_policy_campaign(bound_directory, expected_binding_sha256=...)` freshly
verifies the whole explicit evaluation binding and raw policy result. It never
accepts unchecked caller records or a supplied verification flag. Output links
binding/manifest/result digests and both evaluation and policy config IDs to
source/target, declared profiles/protocol, seed/budget and all three policy IDs.

Shared raw arithmetic counts all four target statuses, C0/C1/C2 and any-contract
observed executions, first observation (zero-based step/one-based execution),
unique full signatures/fingerprints and unique executed cases. Projected feedback
key count, retained count, initial-case count and active-case ID remain separate
policy accounting fields. B0's seed bank/active child is not a retained corpus.
The legacy summary's schema/values are unchanged; no policy result is converted
into a legacy result. Full raw evidence remains in the verified source bundle.

CLI: `python -m inodefence.evaluation.policy_summary DIRECTORY --format json|markdown`
with optional `--binding-sha256`. Incomplete/corrupt input fails closed. A no-hit
first observation is null within the recorded budget; no time or hit is estimated.
Infrastructure ledgers are not counted as successful/no-violation executions.

These are per-run recorded observations, not rediscovery/qualification or paper
results. Unknown/dirty source can still be summarized as raw evidence but cannot
pass the policy dataset validator for pooling. Cross-run analysis must first
validate compatibility and respect explicit strata. Tests perform benign seed-only
executions and label synthetic status/contract model arithmetic explicitly.
