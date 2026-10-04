# Archive-extraction candidate matrix

**Public-source research, accessed 2026-10-04; no reproduction performed.**
Fifteen serious candidates cover node-tar, oras-go and GNU tar. Upstream advisory
ranges below are reported ranges, not proof that every historical version was
tested. Proposed exact pairs are in [Benchmark Set v1](benchmark-set-v1.md).
The [static catalog](../../../experiments/benchmarks/catalog-v1.json) records
component, dates, root cause, effect, entries, paths, order, preconditions,
observation, operators, observer requirements, status, references and uncertainty
for each candidate. This document is the readable index to those records.

A **root cause** is the implementation mistake, such as validating relative to
one directory and linking relative to another. An **effect** is the filesystem
result, such as an internal name sharing an external inode. Similar effects do
not imply identical bugs; several identifiers for the same mistake do not imply
independent semantic coverage.

## Engine fit at the audited main

Machine fields are canonical in the catalog: `candidate_id` joins this index to
stable `benchmark_id`; S IDs join the [semantic taxonomy](taxonomy-and-reachability.md).
All cases are TAR except O03 (OCI blob-title input). Representation is logical
input ability within USTAR bounds, not proof of target behavior. Seed proximity
means some benign types exist, not an attack-bearing seed. Reachability includes
actual controlled setup; the taxonomy separately records structural reachability.
Observability concerns a predicted persistent effect only.

At f02024c, enforced low-level Node/backend binding and benign container fixture
validation exist (see [engine audit](engine-contract-audit.md)). In the table,
"candidate campaign binding" means the still-missing frozen image/config/
provenance and campaign admission for the exact benchmark versions, not the
implemented benign Node invocation. No candidate gate changes in this review.

| Candidate | ArchiveCase represents semantics? | Minimal seeds start near them? | Mutation/setup reaches benchmark now? | Oracle observes selected effect? | Future isolated Linux route / qualification |
| --- | --- | --- | --- | --- | --- |
| N01 | YES | PARTIAL internal hardlink | NO default sentinel address | YES hardlink arm; PARTIAL whole advisory | Exact candidate image/campaign binding pending; IMPLEMENTATION_BLOCKED |
| N02 | YES | PARTIAL internal hardlink | NO addressing/composition | YES persistent alias | Exact candidate image/campaign binding pending; IMPLEMENTATION_BLOCKED |
| N03 | YES | PARTIAL separate link seeds | NO addressing/chain composition | YES persistent alias | Candidate campaign binding plus Linux gate; IMPLEMENTATION_BLOCKED |
| N04 | YES | PARTIAL directory seed | NO addressing/type-path alignment | YES protected write/C0 namespace | Candidate campaign binding plus runtime/strict qualification; IMPLEMENTATION_BLOCKED |
| N05 | YES | PARTIAL regular file | NO selected external address | YES controlled persistent effect | Candidate campaign binding plus absolute input/run binding; IMPLEMENTATION_BLOCKED |
| N06 | YES POSIX arm | PARTIAL directory seed | NO backslash vocabulary/addressing | YES persistent POSIX effect | Candidate campaign binding/grammar missing; IMPLEMENTATION_BLOCKED |
| N07 | YES raw names | NO equivalent-name class | NO alphabet/platform | PARTIAL on required platform | Linux v1 platform gate failed; SOURCE_VERIFIED, excluded |
| N08 | YES raw names/order | NO concurrency/equivalence | NO platform/race | PARTIAL persistent effect only | Linux v1 platform/race gate failed; SOURCE_VERIFIED, excluded |
| N09 | NO PAX/GNU metadata | NO | NO encoding | NO parser-disagreement verdict | Encoding/measurement scope gate failed; SOURCE_VERIFIED, excluded |
| O01 | YES | PARTIAL hardlink seed | PARTIAL generic-name sentinel possible; CWD/adapter absent | YES persistent alias | ORAS adapter/external CWD pending; IMPLEMENTATION_BLOCKED |
| O02 | YES | PARTIAL link/file seeds | NO composition/addressing | YES persistent protected write | ORAS binding/exact fix unresolved; IMPLEMENTATION_BLOCKED |
| O03 | NO non-TAR input/setup | NO | NO | PARTIAL with extra setup | Outside TAR v1; SOURCE_VERIFIED, excluded |
| G01 | YES types; invocation UNKNOWN | PARTIAL link/file seeds | UNKNOWN pin/root semantics | PARTIAL narrower boundary | GNU adapter/pair/root gates pending; SOURCE_VERIFIED |
| G02 | YES regular member | PARTIAL regular file | NO addressing; invocation UNKNOWN | YES persistent controlled effect | GNU adapter/member-selection pin pending; IMPLEMENTATION_BLOCKED |
| G03 | PARTIAL entries, no reused session | NO initial tree | NO fresh-empty setup | PARTIAL with reused setup | Existing-state scope gate failed; SOURCE_VERIFIED, excluded |

Container helper/image/benign Node fixture validation is shared infrastructure
evidence, not candidate qualification. Every candidate `isolated_execution`
(exact candidate campaign binding) is NOT_IMPLEMENTED and every
execution state is NOT_RUN. Unknown platform/version/invocation facts remain
UNKNOWN; no third-party target is TRUSTED_REFERENCE. These claims become stale
when the [audited engine](engine-contract-audit.md) changes.

## Candidates and version evidence

| ID / target | Component and root cause | Advisory date; reported affected → fixed | Minimum semantic requirements and expected effect | Disposition / uncertainty |
| --- | --- | --- | --- | --- |
| N01 / node-tar CVE-2026-23745 | Unpack linkpath sanitation omits the confinement applied to member paths | 2026-01-16; <=7.5.2 → 7.5.3 | Internal hardlink with external target (advisory absolute arm; source-backed relative arm inferred); existing same-device controlled file; post-state alias. Symlink text alone is a separate effect | PRIMARY, hardlink arm only; Linux and strict-mode qualification pending [N01 sources](#n01) |
| N02 / node-tar CVE-2026-24842 | Hardlink validation uses entry parent; creation uses extraction CWD | 2026-01-27; <=7.5.6 → >=7.5.7 | Nested destination, relative hardlink target, existing same-device external file; alias persists | SECONDARY; same validation-base class as O01, useful cross-target replication [N02 sources](#n02) |
| N03 / node-tar CVE-2026-26960 | Lexical target check fails to model composed symlink resolution before hardlink creation | 2026-02-16; <=7.5.7 → 7.5.8 | Multiple symlinks plus hardlink, nested paths, link dependency order, existing external file; final alias | PRIMARY conditional; published demonstration is macOS, Linux support inferred from semantics and patch, not observed [N03 sources](#n03) |
| N04 / node-tar CVE-2021-32803 | Cached directory safety survives directory replacement by symlink | 2021-08-03; <3.2.3; 4.x<4.4.15; 5.x<5.0.7; 6.x<6.1.2 → those patch versions | Directory/symlink collision followed by regular-file descendant; external directory exists; external creation or overwrite | PRIMARY; older runtime compatibility and equivalent strict options must be qualified [N04 sources](#n04) |
| N05 / node-tar CVE-2021-32804 | Only one absolute root is stripped, leaving repeated-root paths absolute | 2021-08-03; <3.2.2; 4.x<4.4.14; 5.x<5.0.6; 6.x<6.1.1 → those patch versions | Regular member with repeated absolute roots; external writable location; external namespace/content effect | SECONDARY simple path baseline; vulnerable/fixed warnings under strict mode could suppress effect [N05 sources](#n05) |
| N06 / node-tar CVE-2021-37701 | Cache path semantics disagree with POSIX backslash names; additional case-folding variant | 2021-08-31; <4.4.16; 5<5.0.8; 6<6.1.7 → 4.4.16/5.0.8/6.1.7 | Directory→symlink→file order with alternate spellings; external destination | SECONDARY POSIX arm only; current mutation alphabet cannot create backslashes [N06 sources](#n06) |
| N07 / node-tar CVE-2021-37712 | Unicode/short-name equivalents evade directory-cache invalidation | 2021-08-31; 6<=6.1.8; 5<=5.0.9; <=4.4.17 → 6.1.9/5.0.10/4.4.18 | Colliding names on a filesystem that treats them as equivalent, directory/symlink/file order | EXCLUDED from Linux v1; ordinary case-sensitive Linux does not supply the required equivalence [N07 sources](#n07) |
| N08 / node-tar CVE-2026-23950 | Path reservations do not serialize filesystem-equivalent Unicode names | 2026-01-19; <=7.5.3 → 7.5.4 | Equivalent names and concurrent operations on normalization/case-insensitive filesystem; possible external writes | EXCLUDED: macOS/APFS and race dependence; no Linux equivalence evidence [N08 sources](#n08) |
| N09 / node-tar CVE-2026-53655 | PAX size applied to intervening GNU metadata headers desynchronizes parsers | 2026-06-01; <=7.5.15 → 7.5.16 | PAX plus GNU long-name/link metadata; conflicting parser interpretation | EXCLUDED: builder cannot encode it; parser disagreement itself has no C0/C1/C2 verdict [N09 sources](#n09) |
| O01 / oras-go CVE-2026-50163 | Validated target returned unresolved, then os.Link interprets it against process CWD | 2026-06-11; upstream names v2.6.0; reviewed ecosystem range <2.6.2 → v2.6.2 | Relative hardlink, external process CWD with same-device controlled file, local unpack-enabled layer; internal alias | PRIMARY; pin 2.6.0, rather than assert all earlier versions tested [O01 sources](#o01) |
| O02 / oras-go CVE-2026-85731 | Lexical symlink checks and missing final-component check allow composed links to be followed by file write | 2026-08-01; <=2.6.1 → v2.6.2 per advisory | Nested directory/link chain, duplicate symlink/regular path, ordered writes; external writable object | SECONDARY; patch identity not independently confirmed, release mentions O01 but not this issue [O02 sources](#o02) |
| O03 / oras-go CVE-2026-50162 | file.Store pushFile checks lexical title confinement but follows existing symlink components | 2026-06-11; upstream names v2.6.0→v2.6.2; reviewed ecosystem <2.6.1→2.6.1 | Blob annotation title and pre-existing symlink under store root; external write | EXCLUDED from TAR rediscovery: pushFile/OCI title input, not archive entry mutation; conflicting upstream range recorded [O03 sources](#o03) |
| G01 / GNU tar CVE-2026-18508 | --one-top-level does not confine hardlink targets to the chosen top-level directory | 2026-08-03 CNA; upstream exact range unknown; RHEL fixes include 2:1.30-13.el8_10, 2:1.34-13.el9_8, 2:1.35-13.el10_2 | Configured top-level boundary, hardlink, existing object; pre-existing symlink can permit writes beyond working directory | SECONDARY pending upstream patch/version and root mapping; vendor versions are not upstream tar releases [G01 sources](#g01) |
| G02 / GNU tar CVE-2016-6321 | Extract path sanitation bypass with member selection; patch rejects original member names containing parent components | 2016 public reports; CNA 2016-12-09; reported 1.14–1.29; identified patch in 1.29.90 Git development line | Regular member traversal, selected member names/CLI conditions, external destination | SECONDARY pending invocation qualification; do not assume default full extraction or label 1.29.90 a released fixed version [G02 sources](#g02) |
| G03 / GNU tar CVE-2025-45582 | Extraction into reused tree violates documented empty-directory assumption | 2025-07-11 CNA; reported through 1.35; no accepted fixed pair identified | Symlink state left by first archive, second extraction follows it; external write | EXCLUDED: two-run/pre-existing extraction state, maintainer says documented misuse; no clean vulnerable/fixed comparator [G03 sources](#g03) |

## Evidence ledger

References are adjacent to each candidate, with source role and exact patch where
identified. Upstream advisories and CVE records corroborate disclosures; release
and patch evidence corroborate the implementation change. Sources can disagree:
retain the discrepancy, select a documented exact vulnerable version, and gate
formal use on post-audit qualification. A URL is not a claim that its PoC ran.

### N01

- Upstream maintainer, [GHSA-8qq5-rm4j-mr97](https://github.com/isaacs/node-tar/security/advisories/GHSA-8qq5-rm4j-mr97): linkpath sanitation and ranges.
- Upstream [patch 340eb285](https://github.com/isaacs/node-tar/commit/340eb285b6d986e91969a1170d7fe9b0face405e): applies stripping/checking to linkpath as well as path; inspected production diff and regression filename.
- Official [CVE record](https://www.cve.org/CVERecord?id=CVE-2026-23745): corroborates 7.5.3.
- Upstream [v7.5.2 Unpack source](https://github.com/isaacs/node-tar/blob/v7.5.2/src/unpack.ts): hardlink creation resolves raw linkpath against extraction CWD. Combined with the inspected missing link-field check and fix, a relative external-target sanitation arm is a source-based inference, still requiring qualification. Prefer it to requiring a new stable absolute mount alias.

### N02

- Upstream [GHSA-34x7-hfp2-rc4v](https://github.com/isaacs/node-tar/security/advisories/GHSA-34x7-hfp2-rc4v).
- Upstream [patch f4a7aa9](https://github.com/isaacs/node-tar/commit/f4a7aa9bc3d717c987fdf1480ff7a64e87ffdb46): hardlink parent-component rejection, inspected.

### N03

- Upstream [GHSA-83g3-92jg-28cx](https://github.com/isaacs/node-tar/security/advisories/GHSA-83g3-92jg-28cx): composed-link effect and macOS validation context.
- Upstream [patch d18e4e1](https://github.com/isaacs/node-tar/commit/d18e4e1f846f4ddddc153b0f536a19c050e7499f): adds symlink component checks to link target operations, inspected.
- Official [CVE record](https://www.cve.org/CVERecord?id=CVE-2026-26960) also references [2cb1120](https://github.com/isaacs/node-tar/commit/2cb1120bcefe28d7ecc719b41441ade59c52e384). Its inspected change improves error-path accuracy; it is not the core confinement fix.

### N04

- Upstream [GHSA-r628-mhmh-qjhw](https://github.com/isaacs/node-tar/security/advisories/GHSA-r628-mhmh-qjhw).
- Upstream [patch 9dbdeb6](https://github.com/isaacs/node-tar/commit/9dbdeb6df8e9dbd96fa9e84341b9d74734be6c20) and [6.1.1…6.1.2 comparison](https://github.com/isaacs/node-tar/compare/v6.1.1...v6.1.2): invalidate cached paths when an entry ceases to be a directory, inspected.

### N05

- Upstream [GHSA-3jfq-g458-7qm9](https://github.com/isaacs/node-tar/security/advisories/GHSA-3jfq-g458-7qm9).
- Upstream [6.1.0…6.1.1 version comparison](https://github.com/isaacs/node-tar/compare/v6.1.0...v6.1.1): patch pointer; not independently inspected during this pass.

### N06

- Upstream [GHSA-9r2w-394v-53qc](https://github.com/isaacs/node-tar/security/advisories/GHSA-9r2w-394v-53qc): distinguishes POSIX backslash and case-insensitive variants and describes cache fix.
- Upstream [6.1.6…6.1.7 version comparison](https://github.com/isaacs/node-tar/compare/v6.1.6...v6.1.7): uninspected patch pointer.

### N07

- Upstream [GHSA-qq89-hq3f-393p](https://github.com/isaacs/node-tar/security/advisories/GHSA-qq89-hq3f-393p): Unicode and Windows short-name equivalence requirements.

### N08

- Upstream [GHSA-r6q2-hw4h-h46w](https://github.com/isaacs/node-tar/security/advisories/GHSA-r6q2-hw4h-h46w): filesystem equivalence and concurrent path reservations.

### N09

- Upstream [GHSA-vmf3-w455-68vh](https://github.com/isaacs/node-tar/security/advisories/GHSA-vmf3-w455-68vh): PAX/GNU parser discrepancy and 7.5.16 fix.

### O01

- Upstream [GHSA-fxhp-mv3v-67qp](https://github.com/oras-project/oras-go/security/advisories/GHSA-fxhp-mv3v-67qp): exact observed version and CWD root cause.
- Reviewed ecosystem [GHSA record](https://github.com/advisories/GHSA-fxhp-mv3v-67qp) and official [CVE record](https://www.cve.org/CVERecord?id=CVE-2026-50163): broader reported range; early cached ecosystem pages showed no patched version. Current upstream patch/release establish the selected fixed pair.
- Upstream [PR #1232](https://github.com/oras-project/oras-go/pull/1232), [patch c463c654](https://github.com/oras-project/oras-go/commit/c463c654ab3ef34422c1764cd619806cebf20451), [v2.6.2 release](https://github.com/oras-project/oras-go/releases/tag/v2.6.2): resolves the hardlink source explicitly before os.Link; production diff inspected.

### O02

- Upstream [GHSA-m37j-52j7-pjw7](https://github.com/oras-project/oras-go/security/advisories/GHSA-m37j-52j7-pjw7): pushDir-specific chain and write behavior.
- [v2.6.2 release](https://github.com/oras-project/oras-go/releases/tag/v2.6.2): available release, but does not identify this fix. Advisory publication follows release. Keep status conditional until tag patch is identified.

### O03

- Upstream [GHSA-8xwf-rjm4-xvhv](https://github.com/oras-project/oras-go/security/advisories/GHSA-8xwf-rjm4-xvhv), reviewed [ecosystem record](https://github.com/advisories/GHSA-8xwf-rjm4-xvhv).
- Upstream [v2.6.1 release](https://github.com/oras-project/oras-go/releases/tag/v2.6.1): file.Store symlink write confinement. Distinct from tar pushDir; do not apply its fix to O02 automatically.

### G01

- Vendor/CNA [Red Hat CVE-2026-18508](https://access.redhat.com/security/cve/CVE-2026-18508), official [CVE record](https://www.cve.org/CVERecord?id=CVE-2026-18508).
- Vendor [RHSA-2026:50807](https://access.redhat.com/errata/RHSA-2026:50807) and [RHBZ 2509843](https://bugzilla.redhat.com/show_bug.cgi?id=2509843): fix/investigation references from CNA; upstream patch and exact source pair unresolved.

### G02

- Official [CVE record](https://www.cve.org/CVERecord?id=CVE-2016-6321): reported range and upstream patch reference.
- Upstream [7340f67](https://git.savannah.gnu.org/cgit/tar.git/commit/?id=7340f67b9860ea0531c1450e5aa261c50f67165d): production patch/NEWS inspected through upstream patch endpoint; rejects original parent-component members when absolute-name option is disabled.
- Vendor [Ubuntu USN-3132-1](https://ubuntu.com/security/notices/USN-3132-1), 2016-11-21: member-selection condition and exact distribution fixes (including 1.29b-1ubuntu0.1). Do not conflate backport package versions with upstream versions.

### G03

- Official [CVE record](https://www.cve.org/CVERecord?id=CVE-2025-45582): reported two-extraction scenario.
- Upstream maintainer [Paul Eggert, bug-tar 2025-08-11](https://lists.gnu.org/archive/html/bug-tar/2025-08/msg00012.html): says scenario violates documented usage assumptions; previously inspected mailing-list text.
- Later upstream [Paul Eggert, 2025-11-15](https://lists.gnu.org/r/bug-tar/2025-11/msg00014.html) identifies hardening at [75b03fd](https://cgit.git.savannah.gnu.org/cgit/tar.git/commit/?id=75b03fdff48916bd0654677ed21379bdb0db016d) and says additional patches are required. This is a source-backed patch pointer, not an inspected complete patch set or qualified fixed release. The reused-state exclusion still applies.
- Upstream [manual: integrity](https://www.gnu.org/software/tar/manual/html_node/Integrity.html): usage-policy reference from maintainer; direct retrieval timed out this pass. No claim of independently inspecting that page.

## Scope screening

Windows drive-relative issues (node-tar CVE-2026-29786/31802 and 2021-37713),
listing-only memory exposure (2025-64118), depth/resource DoS (2024-28863 and
2026 parsing DoS advisories) and ORAS network credential/SSRF advisories were
screened using the upstream advisory indexes. They do not materially improve
this Linux filesystem-contract benchmark, so were not promoted to serious
candidate records. Resource failures remain campaign data, not rediscovery.
No additional extractor family is needed to explain the selected classes.
