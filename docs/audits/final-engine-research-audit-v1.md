# Final Engine / Security Contracts / Research re-audit v1 — Phase 4B

## 1. Identity, scope and recommendation

Audited integrated main: **`d1982e4cf3174e28d4eeb73af7b32829f6751b30`**,
including merged [Runtime #45](https://github.com/TheWaitForAGI/InodeFence/pull/45)
and [Engine #46](https://github.com/TheWaitForAGI/InodeFence/pull/46).
`git fetch origin`, `git switch main`, `git pull --ff-only`, HEAD and clean-worktree
checks passed before creating `audit/final-engine-research-v1` directly from main.
The maintainer's directly supplied Phase-4B specification is the Task Contract.
PR #43/#44 and frozen reports were historical evidence, never this audit's base.

Ownership: EN-001–EN-011; archive/model/builder/mutation, observation/comparison,
C0/C1/C2, signature/fingerprints/Corpus, campaign/config/export research meaning,
current navigation and PR #35 planning consistency. CR-001/002 and EX-003/004/006
were cross-checked at the engine/evidence seam and through integrated CI; this
does not replace the Runtime auditor's final execution audit.

**No new Blocker, Major or Minor established. EN-001–EN-004 are CLOSED in code.**
The three originally consolidated EN-005 locations are corrected, but current
navigation elsewhere still contradicts integrated main. **EN-005 remains OPEN
(existing Minor, residual drift)**, with exact evidence in §6. No new Blocker/Major
invalidated the foundation, so the ordered documentation-only PR #35 refresh was
completed. **EN-006 drift is corrected on the submitted Draft**, with review/main
acceptance still separate. Its exact delivery record is in §11.

**Lane recommendation on the audited main: NO-GO for unconditional global closeout**
until the residual current-documentation EN-005 and PR #35 EN-006 dispositions are
reviewed and accepted. The functional engine foundation passes this re-audit and
permits the requested planning refresh. Proposed unmerged documentation cannot
retroactively make audited main accurate. This verdict does not authorize P01–P11,
qualify a benchmark pair, or establish research effectiveness.

No production source, target, test suite, configuration, fixture or CI file was
modified. The audit adds this report and explicit acceptance witnesses only.
No vulnerable target was installed, built or executed; no benchmark campaign ran.

## 2. EN-001 — CLOSED: lossless USTAR or explicit failure

[build_tar](../../src/inodefence/builder.py) uses strict UTF-8 USTAR and fixed
metadata. `_RawPathTarInfo.get_info` preserves directory suffix spelling.
`tobuf` reconstructs the actual name/prefix header bytes and compares them with
the original encoded raw path before that header is emitted. A lossy delegated
split raises entry-indexed ValueError; the pipeline builds before runtime/target
execution. Partial in-memory bytes are never returned on failure.

The rejection-only correction deliberately does not find an alternative split,
normalize names, truncate links, promote PAX, or resolve dependencies. It may
reject a spelling for which another lossless split could exist. That is allowed
by the required invariant and is documented in the Phase-3 fix record.

[Builder regressions](../../tests/test_builder.py) cover all four entry types,
absolute/relative counterparts, leading/repeated separators, 100-byte names,
155-byte prefixes and maximum 155+1+100 split, UTF-8 byte boundaries, directory
suffixes and 100/101-byte link targets. The [final acceptance matrix](final_engine_reproductions_v1.py)
adds adjacent ASCII/2-byte/3-byte lengths and split/separator combinations for
every entry type. Every success is checked against raw header bytes, and distinct
successful spellings cannot collapse to identical TAR bytes. Every failure must
be explicit and indexed. No extraction is used for these encoding witnesses.

[Fixture regressions](../../tests/test_tar_fixtures.py) and generator/builder
checks retain ordinary fixture bytes, ordering and duplicates. ArchiveCase
encoding/IDs and `ustar-utf8-v1` are unchanged. Evidence supports CLOSED.

## 3. EN-002 — CLOSED: public immutable evidence boundaries

Reviewed [filesystem models](../../src/inodefence/model/filesystem.py),
[results](../../src/inodefence/model/results.py), [digest validation](../../src/inodefence/model/_validation.py),
[fingerprints](../../src/inodefence/feedback/fingerprint.py) and
[feedback records](../../src/inodefence/feedback/corpus.py).

| Boundary | Enforced shape/local invariant |
| --- | --- |
| ObjectSnapshot / StateSnapshot | Typed text/digest/type/numeric facts; tuples of typed objects; canonical unique sorted observed/protected paths; explicit phase |
| StateChange | Typed matching observations; immutable enum tuple in schema order; exact before/after differences |
| SignatureObject / ExternalEffect | Typed fields; regular-only count/size/digest; tagged symlink-only text; external-path effects and ordered enum fields |
| StateSignature | Exactly internal v3, not bool/string/v2; typed nested tuples; sorted unique scoped paths/effects/groups; valid group membership and protected external paths |
| ViolationResult / IdentityEvidence | Contract enum, actual bool, immutable contract-specific evidence and limitation text; evidence iff violated; typed dev+ino and path roles |
| Change/Identity/Violation fingerprints | Typed path/field/relation evidence; nonempty sorted unique whole-contract evidence; no mutable nested list accepted |
| FeedbackDecision / CorpusEntry | Actual bools/text and typed fingerprint tuples; typed case/signature records |
| ExecutionResult / RunResult | Typed process/evidence records, tuple command/collections, finite numeric seconds with bool rejected, coherent status/exit code and SHA-256 |

[Evidence validation tests](../../tests/test_evidence_validation.py) challenge
mutable, malformed and wrongly typed constructors and preserve valid equality,
hashing and canonical serialization. Core/state/feedback tests also exercise
StateSnapshot and ViolationResult negatives and frozen/slots behavior.

The [documented trusted assembly boundary](../../src/inodefence/model/README.md)
is respected: RunResult validates shape, while pipeline owns cross-record TAR,
snapshot/signature/verdict correspondence. CampaignStep/CampaignResult and
CorpusStats are trusted runner/Corpus assembly, not imported-record parsers.
Construction does not authenticate observations. No generic reader exists.
Those explicit limits are not a reopening of EN-002.

## 4. EN-003 — CLOSED: exact raw difference labels

StateChange compares supplied labels with `observed_change_fields`; compare_states
uses the same canonical helper. EXISTENCE alone represents create/delete; two
present observations compare identity `(dev, ino)`, type, nlink, mode, size,
uid/gid, mtime/ctime, readlink text and digest in ChangeField declaration order.
Unchanged pairs produce no change; false labels and missing differences reject.

Final witnesses exercise each numeric/digest dimension, both identity components,
type transitions with their required digest difference, symlink text, existence
and multi-field changes. Existing evidence/state regressions cover contradictions.
C0 remains outside-extract namespace existence/type/identity only, C1 remains
post-state lstat identity sharing, C2 remains all configured sentinel changes.
Observer/oracle/pipeline regressions passed; no Oracle redesign was made.

## 5. EN-004 — CLOSED in code: tagged StateSignature v3

[state_signature](../../src/inodefence/feedback/signature.py) emits internal v3:
exact current root or its textual `/` descendant becomes `run:<raw suffix>`;
everything else becomes `literal:<raw target>`. Exact root is `run:`. Literal
`$RUN/...`, `run:...`, `literal:...`, arbitrary relative/absolute targets and
absolute sibling roots remain literal. Repeated `/` and `..` suffix spelling is
preserved. Neither filesystem lookup nor referent resolution is introduced.

[State-semantic tests](../../tests/test_state_semantics.py) prove disjoint literal
and run tags, raw-snapshot preservation, exact-root/descendant/sibling behavior
and equality across different temporary roots with equivalent raw suffixes.
Existing allocation/harness/identity/effect and semantic-case regressions pass.
Corpus remains state OR violation novelty and ArchiveCase IDs are unchanged.
Internal v2 keys are intentionally incompatible; no reader/migration is supplied.

The basic canonical envelope remains v1. ExperimentConfig still accepts the
historical identifier `state-v2-or-violation-v1-uniform-parent-v1`; its string and
config IDs were preserved by #46, while actual B3 keys are v3. This is a legacy
configuration identifier, not v2 key compatibility. Current navigation does not
consistently explain this distinction and still describes actual signatures as
v2 in three locations: these documentation remnants belong to EN-005, below.

## 6. EN-005 — OPEN on audited main: residual current drift

The frozen three-location union is corrected: design README describes implemented
models/pipeline, feedback README describes contained benign campaigns, and Node
tool README records full-path benign validation. Model/feedback/security-contract
definitions accurately describe signature v3. Historical summaries, audit/fix
records and decisions may retain their revision's older facts.

The broader required current-navigation check nevertheless finds these remnants:

| Exact current location | Contradiction on d1982e4 | Required documentation disposition |
| --- | --- | --- |
| README.md:11, :90 | Whole repository audit is still next; actual signature called Schema v2 | Record Phases 1–3 completed and Phase-4 closeout pending; describe tagged v3 |
| docs/START_HERE.md:71, :88, :142 | Phase-3 review pending / this fix branch; feedback map says v2 | Integrated-main status and signature v3 |
| docs/STATUS.md:23–30, :50, :151 | Fix review/merge still pending; old audited main treated as current phase | Distinguish frozen old audit from integrated Phase-3 fixes and Phase 4 |
| src/inodefence/README.md:34, :88 | Signature v2; waiting for Phase-3 review | Correct actual version and current program stage |
| docs/research/design/architecture.md:26–28 | Engine fixes still feature-branch review pending | Record merged #45/#46 without claiming benchmark readiness |
| src/inodefence/model/README.md:88 | Both policy/provenance payloads called v1 | Policy v1, IsolationProvenance v2 with verified artifact origin |

Minimal reproduction is the source search for `Schema v2`, `signature v2`,
`PHASE-3 FIX REVIEW PENDING` and the cited provenance sentence, compared with
StateSignature(3), IsolationProvenance schema 2 and merged #45/#46. `check_docs`
checks integrity/links, not semantic currency; a PASS does not close this drift.
This is the existing EN-005 root cause, not an additional counted Minor.
No production repair is included here. The PR #35 refresh can safely correct
the relevant planning/navigation documents and explain the legacy config ID;
unmerged branch corrections must remain distinct from audited-main closure.

## 7. Notes and execution-seam cross-check

| Note | Final disposition | Evidence and meaning |
| --- | --- | --- |
| EN-007 | STILL VALID | Finite stems `a/b/file/dir/item`, affixes and benign seed characters cannot produce `outside` or `sentinel.txt`. Random content never becomes path text. API representability is broader than default mutation reachability. Generic protected-component addressability remains P02; this does not exclude every possible unprotected C0 effect. |
| EN-008 | STILL VALID | add_entry's random bytes and exact observed path/content keys can produce benign state novelty; append/affix growth lacks global length/corpus bounds. A valid logical child may eventually fail USTAR and abort. Novel state is no measure of progress or effectiveness. |
| EN-009 | STILL VALID | Fingerprint is one contract's entire evidence tuple. Adding a relation/path changes its novelty class; creation/deletion may share labels; raw values/direction/prose are omitted. Equality is not root-cause deduplication or a vulnerability count. |
| EN-010 | STILL VALID | Process duration excludes most orchestration/observation/evidence completion; operator details/full-step clocks are absent. Infrastructure exception propagates without returned partial campaign or general failure ledger. Completed export fsync coverage does not implement P04/P05. |
| EN-011 | STILL VALID | Persistent two-snapshot scope, actor attribution and stable stopped tree/runtime view assumptions remain. Transient/reverted effects, referent reads, out-of-view events and inode reuse are unobserved; C3/C4, special-object detail, capacity/total storage/CPU bounds and some observer-negative coverage remain limited. |

No Note is automatically converted to a defect or silently fixed. Stronger model
validation/identity probes improve evidence integrity, not snapshot/event coverage.

CR-001/EC-01: source now observes/verifies image identities before provenance freeze
and each archive; false descriptor claims fail closed. IsolationProvenance v2
records `artifact_origin=image-identification-v1`. Direct/replaced/configured/
unconfigured portable regressions and real Node rejection tests pass. Image/probe
and runtime remain trusted, rather than independent authenticity verification.

CR-002/EC-02: prepared actual Entrypoint/Cmd/WorkingDir/Env are verified with
portable mismatch/missing/order tests before start. EX-003: benign descendant
lifecycle regression passes, without treating CLI completion as target teardown.
EX-004: actual file/directory fsync/order, failure/readback and no-replace tests
are strengthened; this is the uncounted regression gap, not crash recovery or a
campaign failure ledger. EX-006 remains a valid trusted synchronous broker-progress
Note; no independent reader deadline/transport architecture was added.
EC-03 remains resolved by #42; EN-005's remnants do not reopen its old incident.

## 8. Integrated real-reference pipeline trace

The final witness runs the actual PythonTarfileTarget, four explicit benign seeds,
RNG `20261004`, seed-inclusive budget 6 and disposable Linux runtime. It rebuilds
each case/TAR and independently reassembles comparison, C0/C1/C2, v3 signature,
fingerprints, Corpus decisions and the next selected/mutated child.

| Step | Actual input/result | Feedback/next-search meaning |
| --- | --- | --- |
| 0–3 | Four unchanged minimal seed IDs; SUCCESS 4; all C0/C1/C2 nonviolations | Four distinct normalized states admitted; no fingerprints |
| 4 | Directory-seed parent `cdcc8045…`; add_entry child `61cb426a…`, regular raw `../dir/item`, bytes `461bed856ee0d230`; TAR SHA-256 `e8efb2e3efe7064edc01f8d90a216848f3b0891ea839f8cac558bbbec809b96f`; reference REJECTED | Persistent partial state has same signature as directory seed; no contract evidence; interesting=False, retained=False |
| 5 | Uniformly selected directory parent again; inapplicable mutate_link_target returns same case; SUCCESS | Same state and already retained case; no novelty/admission; no-op consumes one execution |

Flow is ArchiveCase → caller RNG mutation → build_tar → setup/prepare → BEFORE →
target execution/stop → AFTER → compare_states → C0/C1/C2 and StateSignature v3 →
semantic fingerprints → Corpus.consider → uniform retained-parent selection →
next mutation. Normal context exits remove runtime after evidence construction;
errors during either context exit prevent a returned completed result.
Final stats: observations 6, interesting 4, retained 4, unique states 4,
unique violation fingerprints 0. This is contract/integration evidence only.

## 9. Research-semantics review

Mutator imports archive models/RNG only; generic observer/oracle/feedback have no
target version or CVE predicate. Known CVE metadata remains benchmark ground truth
in research/catalog, never default PoC seeds or oracle truth. Target exit statuses
are process evidence and do not gate contract evaluation or novelty. Rejection
and timeout can still have persistent evidence; incomplete observation raises.

Interesting is new state OR fingerprint, not vulnerability. ViolationResult and
whole-contract fingerprints are scoped candidates/evidence classes, not confirmed
bugs. Corpus admission preserves mutation parents, not paper results. Parent
selection remains uniform over retained unique cases in insertion order. The eight
operator slots remain uniform including inapplicable no-ops; outcome retention
can change subsequent parent/RNG draws. No adaptive scheduler or B0/B1 dispatcher
exists. Benchmark effectiveness, rediscovery, comparative results and evaluation
readiness remain unproven/NOT_RUN.

## 10. EN-006 and PR #35 refresh scope

Actual remote PR #35 was read and fetched before edits: **OPEN / DRAFT**,
`research/benchmark-evaluation-prep-v1`, head
`5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106`. All 17 package files were inspected
from that head, not assumed from the frozen historical audit. The catalog still
pins #39 `efe1dbb…`; current handoff treats EC-01/02/03 as OPEN, benign smoke and
pre-audit freeze as pending, actual state keys as v2 and export as manifest v3.
Those are confirmed EN-006 drift, while all 15 benchmark executions remain NOT_RUN.

Safe refresh: merge exact integrated main into this same branch preserving its
published history; update current research/capability/gate/backlog/catalog and
navigation claims only. Preserve the historical review/reproductions and NOT_RUN
record with explicit superseding dispositions. No replacement research PR,
benchmark implementation, artifact installation or vulnerable execution is needed.

| Required mapping | Current source-backed disposition / refresh target |
| --- | --- |
| #40–#42 / Phases 1–2 | Benign configured smoke/pre-audit freeze and audit/cross-review/global findings freeze completed; not pending |
| #45 / CR-001/002 / EX-003/004 | Verified artifact origin, actual invocation checks, CLI descendant lifecycle fix and export regression coverage exist; old EC-01/02 no longer OPEN |
| #46 / EN-001–004 | Lossless-or-reject builder, public validation, exact difference labels and tagged v3 implemented; no v2 key compatibility |
| EN-005 | Original three locations fixed; additional current navigation corrections proposed in PR #35; integrated-main residual remains explicitly recorded |
| EC-03 | Historical incident resolved by #42, not an outstanding P00 fix |
| P01 | Freeze candidate-specific pins/setup/compatibility; reuse current verified binding/invocation/provenance/export rather than reimplement #45/#46 |
| P02 / P03 | Generic address grammar remains absent; B0/B1/projections remain future; B3 uses v3 with independent state OR violation novelty and uniform parents |
| P04 / P05 | Full-step timing/failure ledger and reader/replay/adjudication remain absent; distinguish EX-004 syscall regressions from those features |
| P06–P11 / catalog | Candidate pair qualification, pilot, rediscovery, replay, baselines and evaluation remain NOT_RUN; source/pin research does not qualify runtime |

## 11. PR #35 delivery record

The engine review and its validations above completed before any research-branch
mutation. The actual PR #35 branch was already checked out in the clean existing
`/tmp/inodefence-research` worktree at its verified remote head. It was refreshed
there; the root audit worktree remained isolated. No competing branch/PR or force
push was needed.

- History-preserving main merge: `3300ad240238790612baddfdc8580803ea9e0b2d`, parents
  `5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106` and audited `d1982e4…`.
- **Refreshed and pushed same-PR head: `cf207d89a0ec465301270f39e57841215e35a06a`.**
- Current planning/navigation and catalog engine_revision were corrected. Existing
  #39 history/reproductions remain explicitly historical; EC-01/02 are resolved
  by #45 and EC-03 remains resolved by #42. All §10 refresh mappings were applied.
- Residual EN-005 navigation/version/status/provenance corrections are proposed in
  PR #35. Production Python, tests, CI, runnable configs and fixtures match audited
  main. Neither this audit nor the research refresh repairs production engine code.
- All 15 catalog records compare equal with the published input except top-level
  engine_revision; every execution remains NOT_RUN, candidate bindings remain
  NOT_IMPLEMENTED, and no candidate is READY. Static qualification stays static.
- Refreshed branch `PYTHONPATH=src make check`: **PASS, 803 tests in 25.85s**, Ruff,
  format, Pyright 0 errors/warnings, environment checks and 74 Markdown documents.
  Catalog PASS (15 records); 14 negative metadata/state cases rejected. Diff,
  LF, source/scope and both ancestry checks PASS. Docs integrity was rechecked
  after recording those validation results.
- [Refreshed PR #35 CI 37199499806](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37199499806):
  check and container-integration PASS at the refreshed head, including raw smoke
  evidence upload and owned controller/volume cleanup. No local Docker rerun or
  benchmark qualification is inferred from those engineering jobs.

**EN-006 final verdict: corrected/CLOSED on refreshed PR #35, awaiting acceptance;
not represented as merged-main work.** Both PR #35 and audit PR #47 remain OPEN,
unmerged and auto-merge disabled; PR #35 remains Draft. The audited-main lane
recommendation remains NO-GO for unconditional closeout pending residual
documentation disposition and global final acceptance. Functional engine checks
pass; no benchmark implementation/execution or effectiveness claim follows.

## 12. Validation and limits

Environment: supported non-root Linux Dev Container, Python 3.12.3,
`/opt/venv/bin/python`, x86_64 WSL2 Linux, runtime `/var/lib/inodefence`.

| Validation | Result |
| --- | --- |
| Focused builder/models/state/observer/pipeline/fingerprint/Corpus/campaign/export/generator/mutation/fixture/docs selection | PASS, **545 tests in 18.73s** |
| Explicit `PYTHONPATH=src python -m pytest -q docs/audits/final_engine_reproductions_v1.py` | PASS, **18 acceptance witnesses in 2.45s** |
| Runtime-seam Node/backend/CLI/isolation/config/provenance/export selection | PASS, **242 tests in 3.05s** |
| `make check` on integrated production code plus audit witness file | PASS: Ruff/format, Pyright 0 errors/warnings, **803 tests in 21.65s**, environment/filesystem checks and docs integrity |
| `git diff --check` | PASS |
| Exact integrated-main canonical CI | [Run 37197933974](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37197933974): check and container-integration PASS on d1982e4 |
| Initial audit PR CI | [Run 37198831242](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37198831242): PASS on initial audit head `668f4a3…`; final report-only delivery does not change production/witness code |

CI [container job 111423543386](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37197933974/job/111423543386)
logs were independently read: helper boundary **6 passed**, image **2 passed**,
Node target **10 passed**, benign configured campaign **1 passed**. Smoke recorded
8 executions, 6 interesting/retained/states, 0 fingerprints, verified isolation v2
origin and **18/18** removed contexts (10 identity contexts + 8 archives). Evidence
upload and owned controller/volume removal passed. This confirms the integrated
canonical container path, not candidate qualification or benchmark evidence.

An initial focused command used nonexistent test filenames and collected no
tests; it was corrected to actual repository paths before the passing selection.
No failed command is counted as validation. Documentation integrity cannot prove
semantic currency, and local reference/unit tests cannot substitute for container
isolation validation. Historical evidence stays pinned to its original scope.


## 12. Post-refresh acceptance addendum — global-closeout disposition

PR #35 was reviewed, marked ready and merged after the audit at merge commit
`52692ba1567e8972fad8426c3bdd539d68df31f1`. The accepted PR #35 head was
`cf207d89a0ec465301270f39e57841215e35a06a`; its changes are documentation,
research-planning/navigation and catalog revision metadata only. It does not add
benchmark execution, vulnerable targets, production engine changes, test changes,
CI changes or runnable benchmark configuration.

The merged refresh corrects the residual current-navigation contradictions listed
under EN-005, including Phase-3 status, StateSignature v3, integrated #45/#46 state,
IsolationProvenance v2 and benchmark NOT_RUN wording. It also refreshes the
research package/backlog against current implementation, closing the stale
research-package drift tracked as EN-006 without promoting static source research
to runtime qualification.

Final post-refresh disposition:

- **EN-005: CLOSED** by accepted PR #35 documentation/navigation corrections.
- **EN-006: CLOSED** by accepted PR #35 research-package refresh.
- **EN-001–EN-004: CLOSED** as established by the pinned functional re-audit above.
- **EN-007–EN-011: STILL VALID Notes**, unchanged and explicitly deferred.
- **New Blocker / Major / Minor: 0 / 0 / 0.**
- **Engine / Research lane verdict: GO** for global Phase-4 closeout and subsequent
  benchmark implementation under new Task Contracts.

This GO does not claim benchmark qualification, rediscovery, effectiveness or a
new vulnerability. All 15 benchmark candidates remain **NOT_RUN**. The original
NO-GO wording above is preserved as the historical verdict on audited main
`d1982e4...` before the documentation/research refresh was accepted.

This audit branch was then merged with post-#35 main before this addendum, so the
final CI for the updated PR is the integration check for this closeout state.
