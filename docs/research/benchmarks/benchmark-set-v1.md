# Benchmark Set v1: selection and qualification

**SELECTED FOR POST-AUDIT IMPLEMENTATION, NOT BENCHMARK READY.** No candidate
has been executed here. [Catalog](../../../experiments/benchmarks/catalog-v1.json)
is metadata, not ExperimentConfig and not permission to run a target.

## Selection rules

Admit a primary candidate only with an authoritative root-cause account,
identified fixed patch/release, a controlled disposable precondition, expected
persistent C0/C1/C2 evidence and a justified route to generic generation after
the documented minimal gaps. Platform/range/invocation uncertainty is an explicit
qualification gate. Diversity and reproducibility matter more than CVE count.

## Admission gates and current disposition

Selection means planned membership only. PASS below is documentary evidence,
PENDING requires independent verification, and BLOCKED names missing implementation.
READY requires every gate to pass with immutable evidence links; no ordinal score
or famous CVE compensates for a failed gate.

| Gate | Required evidence | N01 | N03 | N04 | O01 |
| --- | --- | --- | --- | --- | --- |
| G1 Source trust | Upstream advisory plus production fixing patch | PASS | PASS | PASS | PASS |
| G2 Exact pin | Exact releases, artifact hashes/locks and runtime compatibility | Artifacts PENDING | Artifacts PENDING | Artifacts PENDING | Artifacts PENDING |
| G3 Semantics | Selected arm matched to Linux/default safety settings | Relative arm PENDING | Linux PENDING | Strict/cache PENDING | Public unpack/CWD PENDING |
| G4 Reachability | USTAR plus constructive generic reachability from benign seeds | BLOCKED M1 | BLOCKED M1 | BLOCKED M1 | BLOCKED CWD/adapter |
| G5 Execution | Audited candidate image/config/provenance/full-path binding | BLOCKED | BLOCKED | BLOCKED | BLOCKED |
| G6 Observation | Complete lifecycle-valid persistent C0/C1/C2 evidence | Predicted; PENDING | Predicted; PENDING | Predicted; PENDING | Predicted; PENDING |
| G7 Expected outcome | Fresh same-input affected/fixed comparison and root-cause review | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED | NOT EXECUTED |
| G8 Explicit setup | Named owned same-device objects, CWD/root mapping, no magic state | Freeze PENDING | Freeze PENDING | Freeze PENDING | External CWD freeze PENDING |

All primary admission states are IMPLEMENTATION_BLOCKED, execution NOT_RUN.
G1 does not assert G7. Missing platform reproduction, incompatible options or a
failed fixed comparison keeps that benchmark out of formal cells. Record the
dataset reduction and protocol amendment instead of substituting a case.

## Selection judgments

Scores are ordinal prioritization judgments, not experimental results. 0 means
poor/unestablished, 1 conditional, 2 strong evidence. Columns: root-cause
relevance (R), filesystem-state relevance (F), contract observability (O), current
mutation readiness (M), exact pair/patch availability (V), Linux reproducibility
basis (L), target diversity contribution (T), semantic/evaluation diversity (D).
Do not sum these correlated dimensions into a pseudo-precise quality score.
T reflects contribution relative to the proposed Node-heavy set, not quality of
a language ecosystem. Hard gates and semantic overlap override scores.

| Candidate | R | F | O | M | V | L | T | D | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| N01 | 2 | 2 | 2 | 0 | 2 | 1 | 1 | 2 | Primary sanitation/identity arm |
| N02 | 2 | 2 | 2 | 0 | 2 | 1 | 1 | 1 | Secondary replication of O01 class |
| N03 | 2 | 2 | 2 | 0 | 2 | 1 | 1 | 2 | Primary composed-link identity arm, conditional Linux gate |
| N04 | 2 | 2 | 2 | 0 | 2 | 1 | 1 | 2 | Primary cache transition/external effect |
| N05 | 2 | 1 | 2 | 0 | 1 | 1 | 1 | 1 | Secondary path-only sanity; strict-mode gate |
| N06 | 2 | 2 | 2 | 0 | 1 | 1 | 1 | 1 | Secondary cache variant, extra alphabet gap |
| N07 | 1 | 2 | 1 | 0 | 1 | 0 | 1 | 1 | Excluded platform requirement |
| N08 | 1 | 2 | 1 | 0 | 1 | 0 | 1 | 1 | Excluded platform/race requirement |
| N09 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 0 | Excluded parser differential scope |
| O01 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | 2 | Primary Go/CWD validation mismatch |
| O02 | 2 | 2 | 2 | 0 | 1 | 1 | 2 | 1 | Secondary composition/write; unconfirmed patch |
| O03 | 1 | 2 | 1 | 0 | 1 | 1 | 2 | 0 | Excluded non-TAR sink |
| G01 | 2 | 2 | 1 | 0 | 0 | 1 | 2 | 2 | Secondary pending pair/root mapping |
| G02 | 2 | 1 | 2 | 0 | 1 | 1 | 2 | 1 | Secondary pending selected-member invocation |
| G03 | 1 | 2 | 1 | 0 | 0 | 1 | 2 | 0 | Excluded policy dispute/reused state/no pair |

## Primary pairs and expected evidence

Versions below are **selected exact release pairs**, backed by the adjacent
[candidate sources](candidate-matrix.md), not installed/qualified artifacts.
Use one Node 22.22.0 runtime for all Node pairs if benign qualification succeeds;
otherwise choose and document a common compatible Node runtime before formal
runs, rerun qualification, and freeze the revised environment. Do not change
runtime between vulnerable and fixed members to manufacture a difference.

| Benchmark ID | Known issue / pair vulnerable → fixed | Root class | Expected evidence / required operations | Current reachability / why selected |
| --- | --- | --- | --- | --- |
| node-link-sanitize | N01, CVE-2026-23745; tar 7.5.2 → 7.5.3 | R1 | C1 persistent internal/protected identity; C2 nlink/ctime expected; C0 not necessary. add_hardlink, mutate_link_target, generic component support M1 | NO for current default sentinel; simplest identity acquisition versus link-field fix |
| node-link-compose | N03, CVE-2026-26960; tar 7.5.7 → 7.5.8 | R3 | C1 persistent alias; C2 link metadata; C0 not necessary. add_symlink, add_hardlink, mutate_path/link_target, reorder, duplicate, M1 | NO default sentinel, PARTIAL structural grammar; tests composition beyond simple text checks; Linux qualification required |
| node-cache-transition | N04, CVE-2021-32803; tar 6.1.1 → 6.1.2 | R4 | C2 protected content/size/mode change, or C0 protected-path creation/replacement; C1 not required. directory seed, add_symlink, add_entry, mutate_path/link_target, reorder, duplicate, M1 | NO default protected destination, PARTIAL collision grammar; adds state/order and external-effect class |
| oras-cwd-hardlink | O01, CVE-2026-50163; oras-go 2.6.0 → 2.6.2 | R2 | C1 internal/protected CWD-file alias; C2 link metadata; C0 not required. add_hardlink, mutate_link_target/path; generic-name sentinel and explicit isolated CWD | PARTIAL setup; adds independent Go implementation and a different resolution base |

N01/N03 share the alias effect but have different fixes and structural
requirements. N02/O01 intentionally share R2; keep N02 secondary unless a
cross-target replication is explicitly added. Never count four CVEs as four
independent kinds of effect. No candidate-specific initial attack case is needed.

## Setup profiles and comparison gates for each primary

Common setup: fresh empty extract, at least one owned writable regular sentinel
on the same device, explicit isolated relative names, no real secrets, default upstream
safety controls enabled. Use the same benign initial seeds, M1 policy,
execution/timeout budgets, RNG sequence and isolation limits for each version
pair. All controlled names/layouts are public test configuration available to
every variant; none encodes a vulnerability sequence.

- **node-link-sanitize:** protect a file inside the observed run sandbox. Prefer
  the relative external-target hardlink arm inferred from the inspected 7.5.2
  source and sanitation fix; qualify its root-cause correspondence before use.
  The advisory-described absolute arm remains optional and requires explicit
  absolute addressing under the actual per-run mount. Do not demand a new stable
  mount alias solely for that arm. A dangling external symlink alone does not
  satisfy the success condition. No post-extraction application write is needed.
- **node-link-compose:** allow archive-created nested parents and links, with no
  pre-installed internal links. Final hardlink must name the sentinel object at
  AFTER. Published macOS evidence is not Linux validation. No downstream reads
  or writes are required for classification.
- **node-cache-transition:** protect a regular file in an existing outside
  directory. Required directory/link replacement comes from mutated archive
  entries. Distinguish protected overwrite from unrelated new outside files:
  latter are C0 candidates, and count as this benchmark only after cache-transition
  matching. Qualify strict=true, preservePaths=false unchanged on both releases.
- **oras-cwd-hardlink:** process CWD must be the controlled outside directory,
  while extraction root remains extract/. Protect a generic-name file there.
  A local offline layer wrapper must reach public file.Store unpack behavior
  with fixed benign title and unpack annotation; it must not bypass upstream
  validation by exporting/calling a private helper. No network registry needed.
  Preserve equivalent target-visible extraction layout and title across versions.

Before formal runs: record exact package source/image SHA-256 or digest, npm
lock or Go module sums, worker options and runtime; perform benign adapter and
container-boundary qualification after audit; verify finite generic logical
reachability without injecting PoCs into seeds; then run a separately authorized
qualification pilot. A vulnerability effect mismatch, incompatible strict mode,
or absent Linux reproduction means **NOT QUALIFIED**, with reason retained.
No-hit random pilot alone cannot prove that a release is fixed or non-vulnerable.
If fewer than two target families qualify, report RQ4 as unevaluated rather than
promote a weak substitute. Catalog remains selected_pending_qualification until
the future track attaches its actual evidence.

## Secondary and excluded candidates

Secondary priority: N02 for an inexpensive Node/Go R2 replication; N05 for an
ordinary path-boundary sanity comparator; O02 after its exact fix is inspected;
G01 only after version/root mapping; G02 only after selected-member semantics;
N06 only if extra POSIX spelling coverage answers a predeclared question.
Use N02 7.5.6→7.5.7, N05 6.1.0→6.1.1 and N06 6.1.6→6.1.7 as proposed pairs,
not validated installations. O02's claimed 2.6.1→2.6.2 pair stays conditional.
No exact GNU pair is frozen by this plan.

N07/N08 need excluded filesystem semantics/concurrency. N09 needs excluded
metadata/parser differential instrumentation. O03 is not a TAR-entry mutation
input. G03 has documented-use disagreement, reused-tree requirements and no
accepted fixed comparator. These exclusions preserve a meaningful single-case
Linux evaluation; they do not imply the reports have no security relevance.
