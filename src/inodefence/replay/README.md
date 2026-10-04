# Benign replay execution

`replay_benign(original_directory, new_destination, target)` first verifies the
whole original manifest/config/steps/cases/TARs. It executes only the fixed
`benign-fixtures-v1` regular/directory/internal-hardlink/internal-symlink cases.
Other cases fail before target capture/runtime creation. The profile is fixed
evaluation data, independent of evolving search seed/mutation policy. Optional
original step indices are explicit and unique; no silent filtering occurs.

The exact trusted Python reference or enforced IsolatedTarget composition is
required. Isolation is captured and drift checked; each core `run_case` creates
a fresh runtime and execution. Original case ID/TAR SHA must match the new run.
Sentinel bytes/modes must match original provenance; missing custom sentinel bytes
are not guessed. New full raw results/provenance are checksummed and published
step by step in an independent new directory. Existing destinations and nesting
inside original evidence are rejected. Original files are never overwritten.

`verify_replay(original_directory, replay_directory)` verifies both sets, fresh
runtime identities, record digests and completion binding. Missing completion
means incomplete, even with all records present. Infrastructure errors preserve
published prefixes and available diagnostics in a Failure Ledger; opaque core
phase/cleanup availability remains explicit. All process statuses and changed
security observations are preserved, without rewriting originals or predicting
which outcome should repeat. There is no campaign/search resume.

This bounded execution API does not replay arbitrary attack cases or automate
vulnerability reproduction. Read-only export verification remains generic.
Qualification, rediscovery and paper readiness are separate evidence stages.
