# Evaluation evidence

This package consumes core results without owning Search / Mutation / Feedback
policy. The direct user Task Contract authorizes evaluation infrastructure at
Layer 6; earlier audit navigation remains a historical record.

`python -m inodefence.evaluation DIRECTORY [--manifest-sha256 TRUSTED_DIGEST]`
reads a completed manifest-v4 export. `verify_campaign(Path(...))` returns an
immutable `VerifiedCampaign` only after the whole bundle passes. Invalid input
raises `VerificationError`; the CLI exits 1. It never executes targets.

Verification covers strict schema/JSON, declared file checksums, optional config
file and config ID, budget/count/index/lineage, canonical ArchiveCase/base64,
recomputed case IDs, current pinned builder format and regenerated TAR SHA-256.
Snapshots, changes, current signature/contracts, sentinel configuration, target
provenance, recorded feedback decisions and final corpus counters are checked
for consistency using existing core functions. No algorithm is reimplemented.

Only the current step-v1, signature-v3 and manifest-v4 formats are supported.
An unsupported historical/future format fails closed. Raw stdout/stderr,
snapshots, timestamps and durations survive typed decoding unchanged.

Checksums establish integrity relative to declarations, not authorship. The
existing exporter declares no checksum of the manifest itself. An optional
externally trusted manifest digest provides that anchor. Without it, a coherent
fabricated bundle cannot be distinguished from genuine evidence. Verification
does not establish runtime qualification, reproduction, rediscovery or paper
readiness. It does not reconstruct RNG/search execution or a dirty source patch.
The caller owns the directory's parents; bundle/file symlinks are rejected.
This reader loads the complete bundle in memory, matching the core's bounded
campaign representation. No partial record is returned as verified evidence.

## Pair records

`compare_pair(case, PairArm(provenance_a, result_a), PairArm(provenance_b, result_b))`
checks two caller-produced runs against the requested case and regenerated TAR.
`export_pair(pair, path)` preserves their full core results and their respective
execution provenance in a canonical checksummed record. `read_pair(path)` fails
closed on corruption or input/binding drift. Targets and outcomes may differ.
No CVE, expected result, ranking or automatic target execution is encoded here.
Execution remains caller-owned; this first pair API is the evidence boundary.

Evaluation records use a strict schema-v1 wrapper around existing canonical model
encoding. Payload SHA-256 is declared in the wrapper; whole-file digest is returned
for external anchoring. A synced temporary file is published with Linux atomic
no-overwrite hardlink and parent fsync. Prepublication failure leaves no final
file; postpublication fsync failure may leave a complete file and propagates.
Hard interruption can leave an ignored temporary file. Parents are trusted.
