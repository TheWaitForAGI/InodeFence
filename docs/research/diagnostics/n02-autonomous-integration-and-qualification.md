# N02 autonomous integration and historical qualification — 2026-10-15

```text
ENGINEERING INTEGRATION: PASS; PRs #93, #94 and #95 reviewed and merged in order
CANONICAL VALIDATION: PASS; 1,478 tests on the exact execution revision
TRUSTED CONTROLLER: PASS; macOS/OrbStack host and exact Linux controller identified
HISTORICAL BUILD/ADMISSION: PASS; 7.5.2 and 7.5.3 admitted by immutable image ID
BOUNDED EXECUTION: COMPLETE; 8/8 readiness and 10/10 pair extractions retained
INDEPENDENT READER: PASS; N01_PAIR_AUTOMATED_REPLAY_COMPLETE
FINAL QUALIFICATION: AWAITING_HUMAN_CORRESPONDENCE_REVIEW
B0/B1/B3: NOT_RUN
RESEARCH HYPOTHESIS: NOT_EVALUATED
```

This report records one bounded N01 historical qualification attempt. The automated evidence
is complete, but the frozen contract requires a separate human correspondence disposition
before `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` may be issued.

## 1. Revisions and repository state

The live repository was re-fetched before review. The developer checkout was on main
`57f751992f60a534c5b07506e72124abe5d6b07d`; the task's N01 checkpoint was PR #95 head
`387a68139d32c1e01e15179d00b33b4fe33b1183`. The pre-existing unstaged
`.devcontainer/devcontainer.json` change was not modified, staged or discarded.

The merged execution baseline is `e987c855eee522008443002ee7da5bb6919d64f9`. A standalone
clean clone at that exact revision was mounted into the trusted controller, and every run
records `dirty=false`.

| PR | Reviewed head | Contribution | Merge commit | Result |
| --- | --- | --- | --- | --- |
| [#93](https://github.com/TheWaitForAGI/InodeFence/pull/93) | `ee6ce6501368ff8a5ab420e254790c3451b997ae` | protected-component policy and exact locks | `1fa29962083080cd25641c0dfa8c855d50218fca` | MERGED |
| [#94](https://github.com/TheWaitForAGI/InodeFence/pull/94) | `d8827893ed758ee0437820373964d13564727c6d` | frozen N01 qualification contract | `06175dd088648da209c9a90478420eb9a5fe2a51` | MERGED |
| [#95](https://github.com/TheWaitForAGI/InodeFence/pull/95) | `387a68139d32c1e01e15179d00b33b4fe33b1183` | bounded runner, broker and reader | `e987c855eee522008443002ee7da5bb6919d64f9` | MERGED |

GitHub had no branch-protection rule requiring a human approval. All three PRs were
mergeable with successful required checks. They were merged by the permitted merge-commit
method in dependency order. #94 and #95 were retargeted to main after their parent merged,
so no parent commits were duplicated.

## 2. Independent and adversarial PR review

Review covered actual diffs, ancestry, CI, source, tests, documentation and runtime paths
through the host broker, controller, `IsolatedTarget`, pipeline, BEFORE/AFTER snapshots,
C0/C1/C2, result-first publication and fresh-process reader. No blocking defect was found,
so no production repair PR was necessary.

- #93 keeps the new path vocabulary behind a separate versioned policy and does not change
  legacy/M1 behavior, oracle definitions or feedback semantics.
- #94 freezes input, hashes, target closure, schedule, budget, decision rule and human gate.
- #95 fails closed on broker, admission, observation, cleanup, provenance and artifact
  errors; publishes a completed run before checking expectations; and recomputes evidence
  rather than trusting the stored runner verdict.
- Every extraction uses a fresh runtime root. Targets stop before AFTER, owned containers are
  removed, and cleanup is recorded after evidence capture.
- Missing/malformed oracle evidence is rejected. A failed subprocess cannot become success,
  and a generic failed fixed-arm process cannot become a safe result.
- Admission binds full image ID, version, lock, worker, architecture, runtime and isolation.
  Mutable tags are insufficient.

The adversarial pass explicitly checked no-op target execution, subprocess error coercion,
empty oracle evidence, missing-data-as-zero, environment contamination, version drift and a
wrong Docker daemon. The controller full ID is resolved on the named context and revalidated
with its runtime volume.

One initial detached-clone invocation imported an older editable package from the developer
checkout and could not import `n01_reader`. Repeating the exact checkout with
`PYTHONPATH=src` passed. This was environment contamination, not a code defect; no test or
assertion was weakened.

## 3. CI and local validation

- #93 CI [38692252320](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38692252320):
  `check` and `container-integration` PASS.
- #94 CI [38692405290](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38692405290):
  `check` and `container-integration` PASS.
- #95 CI [38696893021](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38696893021):
  `check` and `container-integration` PASS.

At exact revision `e987c855`, Linux `make check` passed: Ruff lint, Ruff format across 323
files, Pyright with 0 errors, 1,478 pytest tests, environment validation and 114 Markdown
documents. Focused review checks also passed: 50 #93 mutation/lock tests and five #94 contract
tests. This is engineering evidence, not historical runtime evidence.

## 4. Trusted controller and runtime identity

| Field | Recorded value |
| --- | --- |
| Host | macOS 27.0.1, build 26A434, Darwin arm64 |
| Docker CLI/context | `/usr/local/bin/docker`; `orbstack` |
| Daemon | Docker 29.8.2, API 1.56, Linux arm64, OrbStack |
| Daemon ID | `792829ab-98aa-4fde-a654-5e3bf360bed8` |
| Controller name | `inodefence-n02-controller-20261015211952` |
| Controller ID | `9b8c028d35505651d5e803d776d3a2b53c82fda78cc9e48386f68155c80b39aa` |
| Controller image | `sha256:470e82d0541507e58ad8daf4f4371a44a99f7e8cafa2001138cbb41c00b44a1a` |
| Linux | kernel `7.2.9-orbstack-00391-g2b298d05fbd4`, aarch64, Python 3.12.3, UID/GID 1000 |
| Source | clean `e987c855eee522008443002ee7da5bb6919d64f9` at `/workspaces/InodeFence` |
| Runtime | `inodefence-runtime` at `/var/lib/inodefence`; btrfs; observed `st_dev=42` |

The source bind mount was distinct from the runtime volume. Broker validation passed 6/6
using helper image
`sha256:6d6774e4bd7d46784eedd9e85bd23af5914b28abc60abd66987e82a3bf2c0fdf`.
No Docker socket or extra privilege was added to the controller.

## 5. Historical source and image identities

Official npm tarballs were checked before build. Direct inspection of
`dist/commonjs/unpack.js` found that 7.5.2 sanitizes the member path only, while 7.5.3 adds
`STRIPABSOLUTEPATH` handling to both `path` and `linkpath` and rejects `..`. This source fact,
rather than version order, supports the affected/fixed expectation. The remaining pinned
dependency closure was identical after normalizing the root target version fields.

| Binding | affected | fixed |
| --- | --- | --- |
| node-tar | 7.5.2 | 7.5.3 |
| Tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |
| Lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| Image ID / exported manifest-list digest | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` |
| Exported platform-manifest digest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` |
| Architecture | arm64 | arm64 |
| Dockerfile SHA-256 | `b04330bd51f5cc14723f495dff70f19830622ab10aeac66f4136e0ce6efcd53f` | `34042a353a4e923fcdd8c603c20456bc0948feed2e7f753992f02ff265be7aa9` |
| Build-context manifest (`packaging.json`) SHA-256 | `23ade91175d4660d00ef416a0631208edf043ce5308ac06f4211273e0b52e2e5` | `99151b902355c8f8dc92e2659924d94bcbbc67100aa388ef77a5881f69b2057a` |
| Build record SHA-256 | `960b28e0699af5c6ac35709d2d14d7a8818ea8cfed0039f86b3b0217c68997ef` | `e6adeae1456771dce3e0d20acb3e231ceefd5e726a4c8bf554fc402f62ac8960` |

Both use worker SHA-256
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`
and the contract's pinned bases. The untagged images expose no `RepoDigests`; full image IDs,
build records and file digests are the immutable local identity evidence. Both builds exited
zero, and their logs are retained in the build records.

## 6. Attempt, admission and artifact identity

Exactly one bounded attempt ran without retry from `2026-10-15T12:21:35.075125Z` through
`2026-10-15T12:21:51.733095Z`.

- Linux evidence root:
  `/var/lib/inodefence/evidence/n02-n01-qualification-20261015T122200Z`.
- Read-only host copy:
  `/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z`.
- `raw-manifest.json` SHA-256:
  `2a05b5c92cdc679b73b79630102f2cedc238369c1f8167d8eeee6448e0a3cfac`.
- `independent-verification.json` SHA-256:
  `5c8c5a1841d9b55e3b1470d07e850ec7edafcaa6c826ab1136cec41317cf72ae`.
- Final `manifest.json` SHA-256:
  `0665f739f5aa37ab13953c043f321edb409e821ecb65c303d40db93f6c58bf59`.

The raw manifest binds every build, admission, control, run and comparison by path and
SHA-256. It records 18 started, 18 completed, `attempt_status=complete` and no infrastructure
failure. Metadata admission passed 2/2 before any extraction, matching image ID, target,
Node 22.22.0, lock, worker, architecture, Docker runtime/API and isolation policy.

The unchanged oracle control produced C0=false, C1=false and C2=false. The harness hardlink
control produced C0=false, C1=true and C2=true, with cleanup complete. The latter is a
harness control, not historical target behavior.

## 7. Benign readiness — 8 runs

All eight readiness runs passed. Each image extracted the four original benign seeds once.
Every run was `SUCCESS`, exit 0, no timeout, C0/C1/C2 false, input unchanged and cleanup
complete.

| Target | Runs | Success | Timeout | C0 | C1 | C2 | Cleanup |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| node-tar 7.5.2 | 4 | 4 | 0 | 0 | 0 | 0 | 4 |
| node-tar 7.5.3 | 4 | 4 | 0 | 0 | 0 | 0 | 4 |
| Total | 8 | 8 | 0 | 0 | 0 | 0 | 8 |

The four paired input TAR hashes were identical across releases. This establishes readiness
for this bounded attempt only.

## 8. Historical pair — 10 runs and C0/C1/C2

Every record uses child case
`55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87`
and TAR SHA-256
`2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6`.
Order was affected→fixed for repetitions 0/2/4 and fixed→affected for 1/3.

| Target | Runs | Status / exit | Timeout | C0 | C1 | C2 | Cleanup |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| node-tar 7.5.2 | 5 | 5 `SUCCESS` / 0 | 0 | 0 | 5 | 5 | 5 |
| node-tar 7.5.3 | 5 | 5 `REJECTED` / 2 | 0 | 0 | 0 | 0 | 5 |

In every 7.5.2 run, `extract/b.txt` and `outside/sentinel.txt` shared the same post-extraction
`(st_dev, st_ino)`. Sentinel link count changed from 1 to 2 and ctime changed, producing C2;
content did not change. Stdout and stderr were empty.

In every 7.5.3 run, `extract/b.txt` was absent and sentinel identity, link count and content
were unchanged. Stderr was exactly:

```json
{"code":"TAR_ENTRY_ERROR","message":"TAR_ENTRY_ERROR: linkpath contains '..'"}
```

No run changed its input, produced C0, timed out, reused a sandbox or left descendants or
owned containers behind.

## 9. Independent-reader results

The fresh-process reader returned PASS and independently recomputed
`N01_PAIR_AUTOMATED_REPLAY_COMPLETE`. It verified 2 admissions, 2 controls, 8 readiness
records, 10 pair records and 5 comparisons; the runner verdict was consistent.

| Evidence class | Reader result |
| --- | --- |
| Valid positive | accepted C1/C2 in the harness control and all five 7.5.2 runs |
| Valid negative | accepted unchanged/readiness controls and all five 7.5.3 runs |
| Missing record | exit 1, FAIL, `INCONCLUSIVE`, missing-file diagnostic |
| Malformed/tampered record | exit 1, FAIL, `INCONCLUSIVE`, checksum-mismatch diagnostic |

Missing and malformed tests used disposable copies and did not alter the attempt. The reader
therefore distinguishes an executed nonviolation from missing or invalid evidence.

## 10. Qualification verdict

**FACT:** every frozen mechanical predicate passed and the independent reader issued the
automated token.

**FACT:** final `manifest.json` records
`final_status=AWAITING_HUMAN_CORRESPONDENCE_REVIEW` and
`human_disposition=pending_human_correspondence_review`.

**INFERENCE:** the evidence is internally reproducible and shows the expected persistent
identity/effect difference for this exact pair on this controller.

The final N01 contract verdict remains **PENDING**. The contract reserves
`N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` for a separate human correspondence review.

## 11. B0, B1, B3 and the hypothesis

B0: **NOT_RUN**. B1: **NOT_RUN**. B3: **NOT_RUN**. The final N01 qualification token is a
prerequisite, and no campaign rule was changed to bypass it.

The feedback-effectiveness hypothesis is **NOT_EVALUATED**. This known-class archive was a
frozen positive control, not a seed or a mutation discovered by B0/B1/B3. The pair does not
measure prioritization, rediscovery rate or comparative effectiveness under equal budgets.

## 12. Supported and unsupported scientific claims

Supported facts:

- the prerequisite PRs were independently reviewed and correctly merged;
- exact 7.5.2/7.5.3 images were built and admitted on Linux arm64;
- all 18 authorized extractions ran once under the frozen schedule and isolation policy;
- persistent C1 and metadata-only C2 appeared in 5/5 affected runs and 0/5 fixed runs;
- 7.5.3 rejected the exact input in 5/5 runs with the retained diagnostic; and
- an independent reader reproduced the mechanical result from immutable artifacts.

Unsupported claims:

- final N01 qualification before human correspondence review;
- fuzzing rediscovery, new vulnerability discovery or general release safety;
- feedback, mutation or corpus strategy effectiveness;
- B0/B1/B3 results, statistical effect size or performance advantage; and
- absence of transient or out-of-snapshot behavior not represented by C0/C1/C2.

## 13. Remaining blocker and recommended action

The sole decision blocker is the contract-required human correspondence review of source
expectation, exact input, runtime records, inode relation, C2 metadata cause, fixed rejection
and target/environment identity. This is a scientific disposition gate, not a GitHub approval
or infrastructure failure.

The next action is independent human review of the read-only evidence copy and this report.
If it records the exact `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` token, prepare a separate frozen
pilot contract for eligible B0/B1/B3 work. If it rejects or cannot resolve correspondence,
retain that result and do not run dependent campaigns.

## 14. Exact reproduction procedure

Start from the exact clean source and verify the recorded host boundary:

```bash
git checkout --detach e987c855eee522008443002ee7da5bb6919d64f9
PYTHONPATH=src make check
docker --context orbstack info
docker --context orbstack inspect --format '{{.Id}}' \
  inodefence-n02-controller-20261015211952
```

Prepare new absent build contexts and build through the same daemon:

```bash
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging prepare \
  experiments/benchmarks/locks/node-tar-7.5.2.package-lock.json \
  /private/tmp/inodefence-n01-7.5.2 --repository "$PWD"
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging prepare \
  experiments/benchmarks/locks/node-tar-7.5.3.package-lock.json \
  /private/tmp/inodefence-n01-7.5.3 --repository "$PWD"
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging build \
  /private/tmp/inodefence-n01-7.5.2 --docker-context orbstack
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging build \
  /private/tmp/inodefence-n01-7.5.3 --docker-context orbstack
```

Check the full image IDs and build hashes against section 5. Then use a new evidence path;
never overwrite or retry into this report's evidence root:

```bash
PYTHONPATH=src python3.12 -m scripts.container_host \
  --context orbstack \
  --controller 9b8c028d35505651d5e803d776d3a2b53c82fda78cc9e48386f68155c80b39aa \
  --volume inodefence-runtime \
  --image sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520 \
  --image sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f \
  --build-context /private/tmp/inodefence-n01-7.5.2 \
  --build-context /private/tmp/inodefence-n01-7.5.3 \
  --evidence /var/lib/inodefence/evidence/<new-n01-attempt> \
  qualify-node-n01
```

The command performs admission, controls, 8 readiness runs, 10 pair runs and a fresh-process
read. Compare every referenced artifact hash, not only aggregate counts.
