# Frozen engine findings v1 — Phase-3 fix record

This branch implements the maintainer's Engine / Research Semantics Fix Task Contract
for EN-001–005. These are proposed fixes pending PR review and merge. They do not
change the frozen global counts or disposition findings owned by another lane.

## Frozen evidence and ancestry

- Audited main: `fae2954906fa1a95235cde5cddd4dcb73f334169`.
- [Engine Phase-2 report](https://github.com/TheWaitForAGI/InodeFence/blob/42c2afcc4e88d045e94248882311f5c360159016/docs/audits/engine-contract-audit-v1.md):
  `42c2afcc4e88d045e94248882311f5c360159016`.
- [Runtime Phase-2 report](https://github.com/TheWaitForAGI/InodeFence/blob/f00d6dfb26b47447210341d2c77bc642cc6f20b7/docs/audits/runtime-execution-audit-v1.md):
  `f00d6dfb26b47447210341d2c77bc642cc6f20b7`.
- Global Findings Freeze v1: 0 Blocker, 2 Major, 7 Minor, 6 Note,
  1 uncounted regression gap.

`fix/engine-findings-v1` starts directly from audited main, not PR #43 or an audit
commit. The pinned audit artifacts remain unchanged on their own history. The
[Phase-1/2 witnesses](https://github.com/TheWaitForAGI/InodeFence/blob/42c2afcc4e88d045e94248882311f5c360159016/docs/audits/engine_contract_reproductions_v1.py)
assert the observed defects at that revision; they are not post-fix acceptance tests.
To reproduce them, create a separate detached checkout at the Engine Phase-2 SHA,
use the supported Linux/Python 3.12 environment and disposable runtime root, and run:

```bash
PYTHONPATH=src python -m pytest -q docs/audits/engine_contract_reproductions_v1.py
```

Do not run those defect assertions as the current production regression suite.
Historical readiness/smoke summaries and earlier decisions retain their revisions.

## Finding disposition on this branch

| Finding | Status | Change and regressions |
| --- | --- | --- |
| EN-001 MAJOR | FIXED | [builder.py](../../src/inodefence/builder.py) checks actual USTAR name/prefix header reconstruction before emission. Lossy spelling fails with the entry index. [test_builder.py](../../tests/test_builder.py) covers all entry types, absolute/relative counterparts, repeated slashes, name/prefix byte limits, multibyte text and link limits; existing fixture/generator tests keep deterministic baseline bytes. |
| EN-002 MINOR | FIXED | [filesystem.py](../../src/inodefence/model/filesystem.py), [results.py](../../src/inodefence/model/results.py), [shared digest validation](../../src/inodefence/model/_validation.py), [fingerprint.py](../../src/inodefence/feedback/fingerprint.py) and [corpus.py](../../src/inodefence/feedback/corpus.py) enforce immutable typed public evidence/key fields. [test_evidence_validation.py](../../tests/test_evidence_validation.py) rejects mutable/wrong-type text, nested collections, unsupported signature schemas and boolean seconds; valid records retain hash/equality/canonical encoding. |
| EN-003 MINOR | FIXED | StateChange validates exact before/after field coherence through the same pure model difference helper used by [compare.py](../../src/inodefence/observer/compare.py). Evidence tests reject false/omitted labels and cover exact multi-field comparison, creation/deletion and unchanged pairs. Existing observer/oracle/pipeline regressions retain C0/C1/C2 semantics. |
| EN-004 MINOR | FIXED | [signature.py](../../src/inodefence/feedback/signature.py) emits StateSignature v3, tagging every symlink target as `run:<raw suffix>` or `literal:<raw target>`. [test_state_semantics.py](../../tests/test_state_semantics.py) distinguishes `$RUN`, tag-looking literals and run-root siblings, preserves exact-root/repeated-slash/`..` text and cross-run equality. Existing signature-version assertions are updated to v3. Raw snapshots and referents are untouched. |
| EN-005 MINOR | FIXED | Current [design navigation](../research/design/README.md), [feedback navigation](../../src/inodefence/feedback/README.md) and [Node navigation](../../tools/node-tar/README.md) describe implemented bounded/contained benign capabilities. [START_HERE](../START_HERE.md), [STATUS](../STATUS.md) and current module/design contracts reflect the audit/fix phase and signature v3. Historical summaries/decisions remain historical; PR #35 is untouched. |

## Contract and compatibility decisions

The builder uses a rejection-only guard. Even when another lossless USTAR split might
exist, a delegated split that changes spelling is rejected explicitly. The logical
model is unchanged. Previously valid lossless encodings and `ustar-utf8-v1` are
preserved; no alternate spelling, PAX promotion or target workaround is introduced.

Runtime validation is focused on the public model and feedback key constructors.
It validates immutable typed shape and local invariants. Pipeline still owns
cross-record TAR/snapshot/signature/verdict derivation. CampaignStep/CampaignResult
and CorpusStats are explicitly trusted runner/Corpus assembly records, not validated
ingest constructors. This is not a reader, authenticity check or fix for CR-001.

Signature's internal schema advances from v2 to v3; its canonical envelope stays v1.
Literal and run tags occupy disjoint encodings, including when raw text contains a
tag itself. No v2 key compatibility or migration is provided. Only textual run-root
allocation is normalized; no symlink resolution occurs. ArchiveCase IDs, raw evidence,
fingerprint meaning, independent novelty policy, target independence, C0/C1/C2,
mutation/oracle separation and deterministic RNG/budget behavior remain unchanged.
See [D028](../DECISIONS.md) and the [public model boundary](../../src/inodefence/model/README.md).

No benchmark implementation, ORAS work, CVE execution, new mutation strategy,
Phase-4 PR #35 refresh or changes to other frozen findings are included. No benchmark
qualification, evaluation readiness or research-effectiveness result is claimed.

## Validation

Before production edits, the new regression selection failed on the frozen code:
75 failed, 148 passed. After fixes and seven additional tagged-target constructor edge cases, the focused
builder/evidence/state/feedback selection passed: 261 tests. This is defect regression evidence, not evaluation.

Validation environment: supported Linux Dev Container, Python 3.12.3,
`/opt/venv/bin/python`, x86_64/WSL2 Linux, runtime `/var/lib/inodefence`.

- Broader focused Linux/reference selection: 383 passed. This includes builder/model,
  observer/runtime/pipeline, fixture bytes, mutation/building, reference campaign,
  export, generator, feedback integration and execution-duration regressions.
- `make check`: PASS (Ruff, format, Pyright, full pytest, runtime filesystem/environment
  and documentation integrity): 761 tests passed.
- `git diff --check`: PASS.

Actual contained helper/Node image, fixture/lifecycle and tiny benign configured campaign
validation runs in the existing PR CI job; its results are linked in the PR. Local
reference checks do not substitute for that container job or benchmark qualification.
