# Candidate affected/fixed pair replay v1

Status: **IMPLEMENTED / TESTED / NOT A KNOWN-CLASS VERDICT**. This contract adds the raw
offline replay layer required after a final-state policy campaign nominates an exact case.
It does not authorize historical targets, classify a CVE, or replace human root-cause review.

## Task Contract

### Objective

Starting only from a checksummed completed `PolicyEvaluationConfig` bundle, select one exact
observed case and retain a counterbalanced three-affected plus three-fixed replay under one
declared setup. Make complete, failed and interrupted evidence independently reconstructable
before any expected-outcome or known-class decision.

### Allowed changes

- a separate candidate nomination/replay schema and reader;
- exact case/TAR/builder and original occurrence binding to verified policy evidence;
- six bounded fresh `run_case` executions through an existing `CampaignTarget` boundary;
- result-first records, generic pair comparisons, failure record and completion marker;
- benign reference-target engineering tests and documentation.

### Prohibited changes

- CVE, package version or expected vulnerable/fixed outcome in C0/C1/C2, feedback or mutation;
- declaring a generic C0/C1/C2 observation to be a matching historical class;
- using a seed-phase case as credited rediscovery;
- adding a PoC or N02 positive-control case to a fuzzing corpus;
- retrying an existing evidence root or converting an incomplete/failed attempt to no-hit;
- changing target options, timeout, sentinel, source or environment between replay arms;
- treating B0/B1/B3 replay evidence as P0/P1/P2 intermediate-effect evidence.

## Nomination

`nominate_policy_candidate` first invokes the completed policy reader with an optional trusted
binding digest. The requested lowercase SHA-256 case ID must occur in that verified campaign.
The nomination binds:

- source binding, campaign manifest and evaluation config SHA-256 identities;
- the full immutable `ArchiveCase`, TAR SHA-256 and builder format; and
- every original step index, seed/mutation origin and parent case ID for that case.

All occurrences must agree on case/TAR/builder identity. The replay reader reopens the source
bundle and reconstructs the nomination; a copied declaration is insufficient. Selection is
case-ID based and generic. A benchmark-specific process still decides which observed cases
are candidates and whether mutation origin is required for a later credit.

## Exact replay schedule

The protocol ID is `policy-candidate-pair-replay-v1`. It freezes three repetitions and no
automatic retry:

| Repetition | Position 0 | Position 1 |
| ---: | --- | --- |
| 0 | affected | fixed |
| 1 | fixed | affected |
| 2 | affected | fixed |

Both targets, raw sentinel specifications and source candidate identity are written to
`request.json` before target preparation. After target/isolation capture, `header.json` binds
both `ExecutionProvenance` values and requires equal source, environment and sentinel setup.
Target adapter ID, timeout and safety must match; only the declared target version may differ.
Isolation implementation/runtime/resource fields must match while immutable image and verified
target artifact identities may differ as declared by the affected/fixed pair.

Each run executes the same case through the existing prepared campaign boundary, which
enforces target identity/isolation and calls the normal TAR builder, `run_case`, observer and
C0/C1/C2 oracle. The result is published before the next target execution. Once both arms of
a repetition exist, an ordinary `PairComparison` binds their equal case/TAR/builder identity.
All returned SUCCESS/REJECTED/FAILED/TIMED_OUT statuses are raw results and consume their
scheduled replay; none is itself a match or safety verdict.
Each run also records that its fresh runtime root is absent after return. A surviving root
turns the attempt into infrastructure-invalid evidence after preserving the run record.

## Publication and failure semantics

`completion.json` is the only complete marker. It binds request, header, exactly six ordered
run records and exactly three pair records. The reader verifies canonical bytes/checksums,
source nomination, provenance, schedule, raw run derivations and recomputed pair equality.

An ordinary setup/execution/publication exception writes an infrastructure-invalid
`failure.json` referencing the accessible prefix and is re-raised. A hard interruption is not
caught: it leaves a readable unclassified prefix with no completion/failure claim. A complete,
failed or interrupted root is never resumed or reused; a new authorized attempt requires a
new path and remains a separate denominator.

Missing completion is incomplete even when all six runs are present. Missing/noncontiguous
runs, unexpected files, checksum mismatch, source mismatch, forged pairing and simultaneous
completion/failure fail closed. Atomic no-overwrite publication has the same trusted-parent,
single-writer and Linux assumptions as other evaluation records.

CLI verification:

```bash
python -m inodefence.evaluation.candidate_replay \
  <candidate-replay-root> <source-policy-evidence> \
  --completion-sha256 <trusted-digest>
```

## Claim boundary and remaining work

This layer answers only: “were these exact six raw extractions retained and linked to the
actual policy-generated input?” It does not answer whether affected evidence matches N01,
whether fixed evidence excludes the matching class, whether 3/3 plus 0/3 passed, or whether
source/patch semantics correspond to the historical class. Those decisions require a
separately reviewed benchmark-specific mechanical matcher followed by the protocol's human
root-cause disposition.

Tests use benign cases and the trusted Python reference target. They establish engineering
behavior, failure accounting and independent reconstruction, not historical rediscovery or
feedback effectiveness.
