# Completed policy-aware evidence v1

`evaluation.policy_evidence.export_policy_result(result, directory)` consumes a
completed public `SearchCampaignResult`. It performs no target execution,
mutation or search selection. This new format preserves the whole raw result:
declared B0/B1/B3, mutation and projection IDs, seed/budget, initial IDs, lineage,
all RunResults/logs/snapshots/changes/full signatures/C0/C1/C2, SearchDecision v2,
full-state counters, projected-key count, retained IDs, B0 active ID and provenance.
Legacy manifest-v4/config IDs/readers remain unchanged; there is no B3 fallback.

The exact two-file bundle has a checksummed canonical `result.json` and a
checksummed `PolicyEvidenceManifest` v1 in `manifest.json`. The manifest binds
result bytes, the canonical SearchCampaignConfig digest, count, current pinned
builder and result/step/decision/signature schema versions. It is published last
as the completion marker. Linux synced temporary files, atomic no-overwrite
publication and trusted parents/single writer are required. Failed publication
may preserve an incomplete result; existing directories are never reused.

`verify_policy_evidence(directory, expected_manifest_sha256=...)` verifies the
whole bundle before returning `VerifiedPolicyEvidence`. Missing markers, extra
files, symlinks, torn bytes, unsupported schemas, unknown policy IDs, checksum,
case/TAR, snapshot derivation, provenance, lineage or accounting mismatches fail
closed. The CLI is `python -m inodefence.evaluation.policy_evidence DIRECTORY`.

Admission is recomputed with the existing public pure `SearchState`. B0's first
post-seed parent must be in the initial seed bank; subsequent parents must be
the previous observed child. B1/B3 parents must already be policy-retained.
Projected admission keys never replace full diagnostic states or raw contracts.
Verification checks permissible lineage, not RNG draws or mutation proposals.

Checksums are integrity anchors, not proof of authorship or genuine execution.
An external trusted manifest digest is optional. This format is completed raw
engineering evidence, not qualification, rediscovery or paper readiness. It
does not invent an ExperimentConfig ID, environment/protocol binding or missing
timing. Legacy dataset/journal/repetition APIs refuse this distinct format;
the separate policy journal/repetition path composes it without changing legacy
formats. Core exposes completed-step/record callbacks but still returns no failed
partial result; durable prefixes belong to the evaluation journal.

Tests execute only the four fixed benign fixtures with budget equal to their
count (zero mutations). Parent-chain tests use explicitly synthetic assembly of
benign raw observations, not measured campaigns or expected research outcomes.
