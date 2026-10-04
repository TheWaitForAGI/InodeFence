# Engine capabilities and research assumptions

**Observed implementation facts, not experiment results.** Inspected source:
`433ffb0f49f82476b1c3d152e647a5c9a9710485` (2026-10-04). The main checkout
was clean. No open PR or issue appeared in the initial GitHub search. `gh` was
unavailable; Git transport and the GitHub connector supply the equivalent checks.
An independent worktree avoids switching the other engineer's main checkout.

## Inputs the engine can represent and generate

[ArchiveEntry](../../../src/inodefence/model/archive.py) represents regular,
directory, hardlink and symlink entries. Order, duplicates, absolute-looking
paths and unresolved link text survive in ArchiveCase. NUL and surrogate text
are rejected. [Builder](../../../src/inodefence/builder.py) emits deterministic
strict UTF-8 USTAR with fixed owner/time metadata; no PAX/GNU extension headers,
malformed headers or byte-level parser differentials are generated.

[Minimal seeds](../../../src/inodefence/generator/minimal.py) are four benign
cases in fixed order: regular file, directory plus file, regular plus internal
hardlink, regular plus internal symlink. Links refer to preceding internal files.
These are development baselines, not known-vulnerability recipes.

[Mutation v1](../../../src/inodefence/mutator/operators.py) has exactly eight
operators: add_entry, remove_entry, duplicate_entry, reorder_entries,
mutate_path, add_hardlink, add_symlink, mutate_link_target. The convenience
mutate API samples uniformly, once, including inapplicable no-ops. New entries
are appended except duplicates, which are inserted at random positions.
There is no arbitrary type conversion or new-directory constructor.

New names come from `a`, `b`, `file`, `dir/item`, with empty, dot-relative,
parent-relative or root prefixes. Existing text only receives `../`, `./`, `/`
prefixes or `/..`, `x` suffixes. This preserves all original characters: it
cannot substitute arbitrary path components or spell any requested sentinel
name. Link target selection can copy an existing entry path, but cannot compose
an arbitrary multi-component target. Reordering alone cannot create missing
names, filesystem state or relationships.

## What current C0/C1/C2 actually classify

Canonical definitions are [security-contracts](../design/security-contracts.md);
implementation is [oracle/contracts.py](../../../src/inodefence/oracle/contracts.py).
Every returned process status is followed by observation; exit status is not a
security verdict.

| Contract | Evidence accepted now | Important blind spot |
| --- | --- | --- |
| C0 | Before/after existence, identity or type transition at any observed path outside extract/, including HARNESS | External in-place content/metadata changes alone; transient effects; paths outside the observed sandbox; direct path-use events |
| C1 | Post-state internal object and configured external sentinel have equal `(st_dev, st_ino)` | Symlink referent identity, aliases removed before AFTER, external objects that are not protected sentinels |
| C2 | Configured sentinel existence, type, identity, digest, size, mode, nlink, uid/gid, mtime/ctime changes | Unprotected external objects; atime (deliberately excluded); effects reverted between snapshots |

Creating an internal hardlink can produce C1 **and C2 metadata evidence** because
sentinel nlink/ctime change even without writing its bytes. C0 need not fire:
the new directory entry is internal, and nlink alone is not a namespace change.
An internal symlink pointing outside produces no C1 merely by existing; lstat
observes the link itself. Do not claim all symlink poisoning is detected.

[Observer](../../../src/inodefence/observer/snapshot.py) walks the complete run
sandbox with lstat and no symlink following, hashes regular files, and raises
ObservationError on incomplete capture. It cannot reconstruct an operation
sequence or identify its actor. All setup must precede BEFORE; all target
children must finish before AFTER; bookkeeping must follow AFTER. Any violation
of that lifecycle invalidates attribution, rather than earning a path exemption.

## What normalization discards, and retention preserves

[StateSignature v2](../../../src/inodefence/feedback/signature.py) discards
HARNESS objects/identity members, case/TAR identity, raw device/inode values,
timestamp values, uid/gid and nonregular size/nlink. It retains scoped paths,
types, modes, regular size/digest/nlink, symlink text, non-singleton identity
groups, protected paths and EXTERNAL changed-field labels. Run-root-prefixed
absolute symlink text is normalized textually, without referent resolution.
Consequently random file contents and ever-growing path spellings can create
novel states without advancing toward a vulnerability.

[Fingerprints](../../../src/inodefence/feedback/fingerprint.py) keep contract ID
and observed path/changed-field labels (C0/C2), or internal/sentinel relations
(C1). Raw values, process status, duration and prose are discarded. One
fingerprint summarizes the whole evidence tuple of one violated contract;
creation and deletion with identical path/field labels can share a fingerprint.
Counts measure representation diversity, not distinct bugs.

[Corpus](../../../src/inodefence/feedback/corpus.py) tracks state and violation
novelty independently: interesting = new state OR new fingerprint. It advances
seen indexes even for already retained cases, admits each case_id once, keeps
only first-admission signature/fingerprints and selects uniformly with caller
RNG. Full RunResult and lineage belong to CampaignResult, not CorpusEntry.

## Campaign, configuration and export constraints

[Campaign](../../../src/inodefence/campaign.py) executes the ordered initial
seeds first, consuming budget but no search RNG. One Random(seed) serves parent
selection and mutation thereafter. No-op, reject, failure and timeout consume
one execution when a result returns. Infrastructure exceptions propagate; an
aborted run does not return a partial CampaignResult. Memory is O(budget) full
run evidence. The exporter writes completed manifest v2/steps JSONL; no reader,
checkpoint or resume exists.

[ExperimentConfig](../../../src/inodefence/experiment_config.py) currently
accepts exactly minimal-generic-v1, uniform-generic-v1 and
state-v2-or-violation-v1-uniform-parent-v1. Merely naming a baseline in JSON
cannot enable it. Config ID is configuration identity, separate from frozen
source/environment/target/sentinel provenance. Image/dependency locks, CPU,
filesystem/mount properties, CWD and environment qualification need explicit
supplemental evidence where not supplied by infrastructure work.

[Targets](../../../src/inodefence/targets/README.md) declares node-tar
ISOLATION_REQUIRED. Locked benign tooling is Node 22.22.0 / tar 7.5.22, not a
vulnerable benchmark pin. Adapter options are strict=true, preservePaths=false;
other defaults remain upstream. Campaign still rejects third-party execution
before runtime/provenance capture. ORAS and GNU benchmark adapters do not exist.

## Moving-main review rule

At each research milestone fetch origin/main and inspect HEAD..origin/main.
Re-read changes to target contract, isolation, ExperimentConfig, provenance,
CampaignResult and export before updating assumptions. At a clean milestone
merge origin/main if needed (never overwrite main or rebase unfinished edits).
Record the final checked SHA in [handoff](post-audit-backlog.md).

The research lane does not claim the infrastructure blocker is resolved.
Primary completion requires implemented container isolation, a validated benign
Node full-path campaign and a documented pre-audit freeze; full audit and its
fixes still precede benchmark implementation. A future completion signal is
not permission for this branch to execute vulnerabilities.
