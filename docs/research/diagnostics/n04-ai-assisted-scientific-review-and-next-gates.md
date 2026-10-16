# N04 — AI-assisted technical review and bounded continuation proposal (2026-10-16)

**Status: REVIEW PROPOSAL ONLY / NO AUTHORIZATION / NO NEW EXECUTION / NO NEW QUALIFICATION.**

**Evidence base:** repository `main` at `21e317281a2d2a7faf6198f66302f3912b429011`; N03 final report, N01 machine correspondence audit, frozen N01 qualification contract, N03 B0/B1/B3 pilot proposal, node-tar replacement diagnosis, and v3 rebinding proposal. This review was produced by an AI assistant at the user's request. It is **not** a human signature, independent inspection of the private host's raw N02 files, or a substitute for the repository's currently required human disposition.

## 1. Evidence-supported N01 technical judgment

**Provisional technical judgment: SUPPORTED FOR THIS EXACT PAIR (DOCUMENTARY/READER-BASED), NOT FORMALLY QUALIFIED.**

The retained independent audit reports the exact same TAR digest over five counterbalanced comparisons against node-tar 7.5.2 and 7.5.3; affected 5/5 produced the same-snapshot protected-sentinel hardlink identity (C1), whereas fixed 5/5 rejected the linkpath and produced no C1. The affected sentinel nlink 1 -> 2 and ctime difference are **metadata-only C2**; sentinel contents did not change; C0 was absent. The audited explanation also compares the package source behavior. This supports a bounded correspondence opinion, not feedback superiority, hit probability, release-wide safety, or new-vulnerability discovery.

Remaining epistemic limits: this review has not independently reopened the private host's immutable N02 archive, re-run the independent reader there, or personally inspected current Docker image bytes. Retain `human_disposition=pending_human_correspondence_review`; **do not** mint `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED`. The old frozen contract remains unchanged. If the team needs an expert-level human gate, seek a professor/maintainer review; if the team elects to change the gate, version it prospectively and label AI/automated verification accurately.

## 2. Scientific governance that does not require student-expert judgments

Use three distinct evidence/decision tiers, never silently convert one into another:

1. **Mechanically verified**: immutable checksums; source/target binding; independent reader; exact artifacts, replays and negative tests. Machine PASS can be issued by software.
2. **AI-assisted technical interpretation**: explicit reasoning, contrary hypotheses, reproducibility limits, reviewer identity as AI, and citations to the tested artifacts. This is an advisory conclusion, **not** a human approval token.
3. **Research-owner authorization**: a student project lead can authorize bounded resource use and the research direction without claiming expert vulnerability adjudication. The owner should see a one-page risk/budget/claim statement; a project decision does not become scientific validation merely because it is signed.

If a new protocol replaces a human judgment with predeclared mechanical criteria, keep the old report and tokens unchanged, register the exact replacement rule before any new historical outcome is inspected, and label conclusions `machine-corroborated` or `provisional` instead of `human-qualified`. Formal known-class rediscovery under the frozen protocol remains blocked until its human gate genuinely completes.

## 3. Timeout recommendation: preserve the predeclared 5 seconds, conditionally

The evaluation protocol already specifies a common **5 s** primary target timeout. The N01 pair was observed at **10 s**. Recommendation: **use 5 s for the proposed new pilot only if fresh, exact-target admission and four-benign-seed readiness pass at 5 s on one clean frozen integration SHA and the approved isolation profile**. This minimizes post hoc change to the originally declared evaluation budget. Previous 10 s admission is not transferrable.

Record the 5 s preflight result, source SHA, package/image/platform identities, docker context, controller identity, output root, method `linux-proc-self-vmhwm-v1`, independent reader, and contract digest *before* pilot. If 5 s readiness fails, do not selectively retry, drop timeouts, or silently use 10 s. Issue a prospective versioned amendment for 10 s and requalify both arms at the amended setting. A failed 5 s feasibility test must remain visible and cannot be pooled with 10 s comparisons.

**Current status: RECOMMENDED, NOT SELECTED/RE-ADMITTED/AUTHORIZED.**

## 4. v3 review recommendation: conditional design GO, not effect qualification

N03 shows that node-tar's default duplicate regular-file case reuses and truncates an inode, while exercised genuine namespace changes are multi-operation `unlink -> create/link` rebinding. The frozen v2 one-operation `namespace_replacement` event is correctly unqualified; do **not** relabel it as a false negative or repair it by collapsing intervals.

The separate v3 `namespace_rebinding_sequence` is a defensible **candidate** intermediate-state observation **only if**:

- Removal and creation are independently successful, same archive entry and normalized destination path, with explicit endpoint absence on both sides of the gap.
- The producer supports a verifiable dependency edge that links the operations (not mere timing, ordering, or path equality), and an independent reader reconstructs it from complete raw evidence.
- A conflicting intervening binding invalidates the composite; inode-number reuse is explicitly allowed but never treated as proof of continuity.
- Underlying v2 realized removal/creation keys are retained alongside a new tagged composite key; v2 schemas, gates, raw evidence and P0/P1/P2-v2 identifiers are unchanged.
- Synthetic negatives include same-inode truncation, no dependency edge, missing absence, failed operation, distinct entry/path, intervening rebind, incomplete trace and tampered provenance.
- A **nonredundancy check** quantifies whether the v3 composite distinguishes bounded causal patterns not already distinguished by the existing ordered v2 evidence/feedback projection. If it adds no observable discrimination, report this and reconsider the expense before running a full effectiveness matrix.

The v3 proposal can be accepted as a *research design to test* with new implementation/qualification contracts; that is **not** acceptance of its correctness or effectiveness. Native qualification requires separate frozen finite fixtures and repeated real-target runs. Formal P0/P1/P2-v3 experiments require yet another versioned gate; P0/P1/P2-v2 stay NOT_RUN.

**Current status: CONDITIONAL DESIGN RECOMMENDATION ONLY / V3 NOT IMPLEMENTED OR QUALIFIED.**

## 5. Concrete work order for the next bounded session

1. Re-run the read-only N01 independent reader against the retained host raw evidence and record its digest/result. If the private N02 evidence is inaccessible, report `NOT_VERIFIED_IN_THIS_SESSION`, do not infer PASS from prose alone.
2. Author a **new** 5-second pilot task contract with exact clean commit SHA, image digests, retained four-seed readiness, full-step timing, required per-terminal controller lifetime `VmHWM`, immutable output root, explicit pilot/nonformal claim, 20 original scheduled cells, 200 seed-inclusive executions per cell, no retry, and an independent ledger join. Execute nothing until these values are pinned and authorization is recorded.
3. Separate **engineering/feasibility pilot evidence** from **confirmed N01 known-class rediscovery**. Mechanical 3/3 versus 0/3 may be reported after it actually runs; human-qualified rediscovery may not.
4. For v3, write a new bounded implementation Task Contract specifying producer dependency provenance and independent reconstruction. Implement and test the smallest positive/negative archive-only fixtures before any native matrix proposal, without touching v2.
5. Execute only in the user's trusted, disposable, pre-admitted Linux environment. No execution can be claimed from GitHub document inspection. Preserve the existing uncommitted `.devcontainer/devcontainer.json` change and unrelated draft PR #92.

## 6. Stop conditions and reserved claims

Stop on source/image/protocol mismatch, readiness failure, absent required memory/timing records, missing bounded dependency evidence, invalid isolation, or an attempt to reinterpret old v2 evidence. Save failed/STARTED and invalid slots, full denominators, and exact cause; no retry-as-success.

Explicit current verdicts:

- N01 historical **machine** correspondence: PASS as reported in N03; **human gate pending**.
- B0/B1/B3: IMPLEMENTED/TESTED infrastructure; **NOT_RUN** against historical targets.
- v2 native observation: `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`.
- v3: PROPOSED; **NOT_IMPLEMENTED / NOT_QUALIFIED**.
- P0-v2/P1-v2/P2-v2 and central hypothesis: **NOT_EVALUATED**.

This document contains no trial results and does not change any previous frozen experimental contract. Its role is to make a bounded, auditable student-team continuation possible without misrepresenting an AI review as a human scientific sign-off.
