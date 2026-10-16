# N03 independent N01 machine correspondence audit

Status: **PASS (AUTOMATED EVIDENCE CORRESPONDENCE) / HUMAN DISPOSITION PENDING**.
Audit date: **2026-10-16**. This audit reads the retained N02 artifacts and source; it does
not execute either historical target, alter immutable evidence, or supply the human review
required by the frozen N01 contract.

## Scope and evidence identity

The read-only host evidence copy is
`/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z`.
The audit independently checked the N02 report, frozen contract, target packaging records,
raw records, comparisons, checksums, final manifest and fresh-process reader result.

| Artifact | SHA-256 | Audit result |
| --- | --- | --- |
| `raw-manifest.json` | `2a05b5c92cdc679b73b79630102f2cedc238369c1f8167d8eeee6448e0a3cfac` | **PASS** |
| `independent-verification.json` | `5c8c5a1841d9b55e3b1470d07e850ec7edafcaa6c826ab1136cec41317cf72ae` | **PASS** |
| final `manifest.json` | `0665f739f5aa37ab13953c043f321edb409e821ecb65c303d40db93f6c58bf59` | **PASS** |

The independent reader derived `N01_PAIR_AUTOMATED_REPLAY_COMPLETE`, agreed with the
runner, and reconstructed counts `(2 admissions, 2 controls, 8 readiness, 10 pair runs,
5 comparisons)`. This is machine verification only.

## Correspondence findings

### 1. Exact target identities — PASS

**FACT:** the affected arm identifies Node 22.22.0 / node-tar 7.5.2, npm tarball SHA-256
`22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a`, lock
SHA-256 `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243`,
image ID `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520`
and arm64 platform manifest
`sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542`.

**FACT:** the fixed arm identifies Node 22.22.0 / node-tar 7.5.3, npm tarball SHA-256
`9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66`, lock
SHA-256 `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24`,
image ID `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f`
and arm64 platform manifest
`sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0`.

**FACT:** both arms bind worker SHA-256
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`.
The dependency closure, except for the selected `tar` package identity, was normalized and
compared by the retained reader.

### 2. Frozen input identity — PASS

**FACT:** all ten pair runs used case ID
`55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87`
and USTAR SHA-256
`2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6`.
The input is the policy-generated child of benign hardlink seed
`de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620`.

**INFERENCE:** canonical case, TAR and builder equality across all pair records is sufficient
to call the target input identical. It is not evidence that future search campaigns will
generate this child.

### 3. Source-derived affected/fixed expectation — PASS

**FACT:** retained source inspection records that 7.5.2 applies absolute-path sanitation to
the entry path but not the hardlink target, while 7.5.3 applies the added link-target
handling and rejects `..` in this input. The expectation is therefore patch/source-derived,
not inferred only from version order or observed outcome.

### 4. Same-input execution — PASS

**FACT:** five counterbalanced repetitions were completed without automatic retry. The order
was affected then fixed in repetitions 0, 2 and 4, and fixed then affected in repetitions
1 and 3. Pair records bind equal case ID, TAR digest and builder format while retaining both
complete arm results.

### 5. Controlled sentinel setup and identity — PASS

**FACT:** every arm used the controlled `outside/sentinel.txt`, mode `0600`, with initial
content SHA-256
`caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b`.
Sentinel provenance, target provenance and isolation provenance match the admitted arm.

### 6. Actual `lstat` identity relation — PASS

**FACT:** after each affected run, `extract/b.txt` and `outside/sentinel.txt` had equal
`(st_dev, st_ino)`. C1 was true in 5/5 affected records. The fixed arm left the alias absent
and C1 false in 5/5 records.

**INFERENCE:** equal device/inode values in the same complete post-state establish the
persistent hardlink identity relation represented by C1. Inode number alone, or values from
separated lifetimes, would not be sufficient.

### 7. Cause of C1 — PASS

**FACT:** the affected extraction created `extract/b.txt` as a hardlink whose target resolved
to the controlled external sentinel. The two paths consequently named one persistent
filesystem object at AFTER. There was no C0 outside-root namespace creation.

### 8. Cause of C2 — PASS

**FACT:** the sentinel link count changed from 1 to 2 and ctime changed in all five affected
runs. These metadata fields account for C2. The fixed sentinel link count and ctime remained
unchanged in the five fixed runs.

**INFERENCE:** link creation explains the nlink transition and associated ctime update. C2
here is metadata-only corroboration of the C1 relation, not content corruption.

### 9. Sentinel content claim — PASS

**FACT:** no affected or fixed pair record reports a sentinel content-digest change. The
audit found no claim in N02 that sentinel bytes changed.

**FAIL condition not observed:** describing this C2 as a content write would contradict the
raw records.

### 10. Exact fixed rejection — PASS

**FACT:** node-tar 7.5.3 returned `REJECTED`, exit code 2, in 5/5 runs. Retained stderr was
exactly `{"code":"TAR_ENTRY_ERROR","message":"TAR_ENTRY_ERROR: linkpath contains '..'"}`.
The alias was absent, C0/C1/C2 were false, the input was unchanged and cleanup completed.

### 11. Oracle controls and readiness — PASS

**FACT:** the unchanged negative control produced C0/C1/C2 false. The harness hardlink
positive produced C0 false and C1/C2 true. Both target images then completed the four
original benign seeds: 8/8 success, no timeout, no C0/C1/C2, unchanged inputs and verified
cleanup. The positive control is harness evidence, not historical target behavior.

### 12. Isolation, cleanup and provenance — PASS

**FACT:** the attempt ran in the admitted macOS/OrbStack to Linux arm64 boundary with a
separate runtime volume. Every extraction used a fresh runtime root; all 18 started runs
completed; no target timeout, infrastructure failure, sandbox reuse, owned-container leak or
descendant-process leak was recorded. Source was clean revision
`e987c855eee522008443002ee7da5bb6919d64f9`.

### 13. Independent-reader completeness — PASS

**FACT:** the fresh reader re-read checksummed records, recomputed case/TAR/snapshot/oracle
derivations and reconstructed the automated verdict. Disposable missing/tampered controls
failed closed as `INCONCLUSIVE`; immutable evidence was not modified.

### 14. Raw/summary/claim consistency — PASS

**FACT:** raw denominators, derived tables and N02 prose agree: affected C1/C2 5/5 and C0
0/5; fixed strict rejection 5/5 and C0/C1/C2 0/5; readiness 8/8. The final manifest preserves
`final_status=AWAITING_HUMAN_CORRESPONDENCE_REVIEW` and
`human_disposition=pending_human_correspondence_review`.

## Unresolved and excluded decisions

**UNRESOLVED:** the contract-required human correspondence review has not been performed.
This automated audit cannot decide whether a human accepts the source/input/runtime
correspondence or issue `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED`.

**INCONCLUSIVE:** these five controlled repetitions do not estimate fuzzing hit probability,
feedback effectiveness, release-wide safety or behavior on other platforms/configurations.

**PASS:** the retained artifacts are internally consistent and sufficient for the existing
automated token.

**FAIL:** none of the fourteen machine correspondence checks failed.

Final machine disposition: **PASS / AWAITING_HUMAN_CORRESPONDENCE_REVIEW**.
