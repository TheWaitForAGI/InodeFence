# N01 historical execution progress — 2026-10-15

## Evidence boundary

This record covers Stage 1 integration and Stage 2 contract review for the requested N01
historical execution pipeline. Historical images were not built or loaded, and archive
extractions against node-tar 7.5.2/7.5.3 remain **0**. No C1/C2 historical result or
B0/B1/B3 pilot result exists yet.

## Stage 1 — reviewed integration

Base: `57f751992f60a534c5b07506e72124abe5d6b07d` (`origin/main` and remote HEAD
after refresh). Integration branch: `integration/n01-historical-readiness-v1`.
Exact tested integration revision:
`ee6ce6501368ff8a5ab420e254790c3451b997ae`.

Integrated inputs:

- protected-component addressing source `a7aa735bfada38309984066202b1ceda5aa93e34`;
- N01 wrapper locks source `12fe37953e96f3b3d24eb956affa9d1b986eab02`.

The only content conflict was `docs/STATUS.md`. Its resolution preserves both independent
facts: the protected-component policy has only constructive logical reachability evidence,
and the exact locks have only portable packaging evidence. Every non-conflicting source,
test and artifact blob is byte-identical to its reviewed source branch.

Review findings:

- Existing M1 policy IDs, component tuple, eight slots and frozen deterministic test vectors
  are unchanged. The new protected-component policy and its no-reorder variant have separate
  identifiers and the same slot/RNG structure.
- The constructive child has hardlink target `../outside/sentinel.txt`, case ID
  `55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87`
  and TAR SHA-256
  `2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6`.
  This is addressability, not measured mutation probability or rediscovery.
- Both wrapper locks bind the selected tar release and the same five-package non-target
  production closure. Their SHA-256 values are
  `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243`
  and `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24`.
- Generic C0/C1/C2, target, observer, oracle and native-effect semantics are unchanged.
- No CVE, package version or expected status enters mutation or oracle truth.

Validation:

- focused mutation/policy/provenance/lock/packaging selection: **81 passed**;
- combined `make check`: Ruff PASS, format PASS, Pyright 0 errors, **1,467 tests PASS**,
  environment PASS and docs PASS;
- `git diff --check`: PASS;
- combined worktree after validation: clean.

The branch was pushed. Authenticated connector access later became available and the existing
head was checked before opening
[PR #93](https://github.com/TheWaitForAGI/InodeFence/pull/93). No duplicate branch or PR was
created.

## Stage 2 — technical review, human decision pending

Stacked review branch: `review/n01-pair-qualification-v1`. It contains the tested Stage 1
integration, the canonical proposed contract and technical review record. Contract review
commit: `b80c8c0` before this additive progress record.

Technical review reproduced the package, lock, worker, case, TAR and sentinel bindings and
confirmed the existing lifecycle, C1/C2, pair-storage and checksum-reader semantics needed
by the contract. The user-reported host results—boundary 6/6, current image 2/2 and current
target 10/10—establish the existing normal-target broker path only. They do not identify or
admit historical images.

The frozen contract remains 8 benign archive extractions plus 10 pair extractions, no
automatic retry, counterbalanced pair order, affected C1 as the selected observation and C2
metadata as corroboration. Human authorization is **NOT_RECORDED**, so the execution gate is
`BLOCKED_FOR_HUMAN_APPROVAL`.

Review-branch validation after the contract update: `make check` PASS with **1,467 tests**,
environment/docs PASS, followed by `git diff --check` PASS.

Authenticated connector access later opened the reviewed stack as
[PR #94](https://github.com/TheWaitForAGI/InodeFence/pull/94), based on the integration branch.

## Stage 3 implementation audit

No Stage 3 implementation or execution was authorized. Static review established these
requirements for the post-approval implementation:

1. Existing `check_node_image.py` cannot admit historical images because it deliberately
   requires tar 7.5.22 and the baseline lock path.
2. The full existing `check_node_target.py` is not the N01 benign-readiness phase. Besides
   four benign cases it executes invalid-input, real-timeout and controlled failure cases;
   invoking it for both historical images would silently exceed the frozen qualification
   archive budget.
3. The old unmerged `experiment/n01-node-historical-qualification` runner uses a different
   root-level sentinel and mutation transcript, groups releases instead of counterbalancing,
   can assert before preserving every completed result, lacks `PairComparison` bundles and
   has no independent all-or-nothing reader. It is not reused.
4. The smallest acceptable implementation therefore needs distinct metadata-only historical
   image admission, an exactly-four-case benign mode per image, then the approved 10-run pair
   mode with result-first publication, last manifest, cleanup records and a fresh-process
   reader. Existing broker/backend/target/oracle/storage code must be composed rather than
   duplicated.

Historical image build, admission and benign readiness are **NOT_RUN**. Exact immutable image
IDs do not exist yet. Stage 4 and Stage 5 remain gated.

## Stage 4 — authorization and contained implementation

The project owner recorded the exact approval statement **“N01 pair qualification contract
v1을 승인한다.”** on 2026-10-15. Work continued on
`experiment/n01-contained-qualification-v1` from the reviewed `d882789` stack.

The additive implementation keeps generic builder/mutation/runtime/observer/oracle/feedback
semantics unchanged. It adds strict completed build-record validation, N01-only immutable
image admission, two oracle controls, exactly eight readiness runs, the frozen counterbalanced
ten-run pair, result-first records, five `PairComparison` records and a fresh-process reader
that recomputes artifact integrity, case/TAR/image identity, snapshots, inode relationships and
C0/C1/C2. Controlled adapters exercise the complete 8+10 schedule and failure paths; these are
engineering tests rather than historical execution evidence.

The current Dev Container has the validated Linux runtime volume but no Docker CLI or direct
daemon access. That is the intended trust boundary, so historical images were not built and
the broker-backed N01 mode was not invoked from this environment. Historical admission,
readiness, pair qualification and B0/B1/B3 pilot remain **NOT_RUN**.

The project owner subsequently reported macOS/OrbStack boundary validation **6/6 PASS** with
the existing `scripts.container_host` path and running Dev Container. This restores the
intended trusted-host transport precondition without a Docker socket mount or privilege
change inside the Dev Container. It is boundary engineering evidence only: the two historical
images are still not built and the approved extraction count remains **0/18**.

The contained implementation checkpoint is
`0699099806dad1c8df12d8e9cc22dd35b334a4d0`. It is published for review in
[PR #95](https://github.com/TheWaitForAGI/InodeFence/pull/95). The complete review handoff is
recorded in [the autonomous execution final review](n01-autonomous-execution-final-review.md).
That review also resolves the checkpoint test-count discrepancy: PR #95 CI collected and
passed 1,476 tests, equal to the 1,467-test parent plus nine new tests. The earlier 1,475 entry
is not reproducible at the checkpoint and accounts for only eight of those nine new tests.

## Next authorized transition

After human code review and canonical validation of this branch, run the documented explicit
macOS/OrbStack build and `scripts.container_host ... qualify-node-n01` command with two full
immutable image IDs and a new runtime-volume evidence path. Admission failure must stop before
archive execution. Only an independently verified `N01_PAIR_AUTOMATED_REPLAY_COMPLETE` may
advance to human correspondence review; it is not itself the pair-qualified token or pilot
authorization.
