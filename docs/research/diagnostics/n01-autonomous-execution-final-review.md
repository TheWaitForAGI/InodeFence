# N01 autonomous execution final review — 2026-10-15

```text
IMPLEMENTATION STATUS: COMPLETE; STATIC_REVIEW_PASS on experiment/n01-contained-qualification-v1
TEST STATUS: PASS; checkpoint CI 1,476 tests; review follow-up make check 1,478 tests
HISTORICAL QUALIFICATION: NOT_RUN; no historical image build and 0/18 approved extractions
INDEPENDENT VERIFICATION: TOOLING_TESTED; HISTORICAL_NOT_RUN; human review still required
MAC BOUNDARY: USER-REPORTED 6/6 PASS with existing host broker and running Dev Container
PILOT STATUS: NOT_RUN; blocked until valid N01 qualification and pilot authorization review
RESEARCH CLAIMS SUPPORTED: contained qualification mechanics are implemented and tested
RESEARCH CLAIMS NOT SUPPORTED: historical behavior, rediscovery, feedback efficacy, or vulnerability claims
REVIEW REQUIRED: code, frozen identities, containment, evidence derivation, and Mac execution correspondence
NEXT CRITICAL PATH: stacked review -> trusted Mac build -> admission -> 8 readiness -> 10 pair -> reader -> human verdict
```

This document is a code-review handoff, not a historical qualification report. No node-tar
7.5.2 or 7.5.3 archive extraction occurred during this work. The controlled adapters used by
the tests are engineering evidence only and are not historical target evidence.

## 1. Repository state at start

The work started from a clean `review/n01-pair-qualification-v1` worktree at
`d8827893ed758ee0437820373964d13564727c6d`. The reviewed stack was:

- `origin/main`: `57f751992f60a534c5b07506e72124abe5d6b07d`;
- integration: `ee6ce6501368ff8a5ab420e254790c3451b997ae`;
- review head: `d8827893ed758ee0437820373964d13564727c6d`;
- reported and reproduced canonical baseline: 1,467 tests PASS;
- historical qualification and pilot: `NOT_RUN`.

The implementation branch was created as
`experiment/n01-contained-qualification-v1`. The Dev Container provided Python 3.12,
the Linux runtime root `/var/lib/inodefence`, and the required filesystem semantics. It did
not provide the Docker CLI or direct daemon access. The absence of that trusted-host
capability was treated as an execution gate, not bypassed by weakening containment.

The project owner additionally reported a **6/6 PASS** from the macOS/OrbStack host using the
existing `scripts.container_host` path and running Dev Container. This establishes the
broker/controller boundary check for that host session. It is not a historical image build,
N01 admission, or one of the approved 18 archive extractions. No Docker socket mount or
privileged Dev Container change is needed or allowed.

The local `gh` CLI was unavailable. Authenticated GitHub connector access was available and
was used only after searching for existing pull requests, so no duplicate PR was created.

## 2. Changed files and reasons

The implementation checkpoint changes 15 files with 2,220 insertions and 28 deletions. The
review follow-up adds this handoff and only N01-specific reader/admission checks, tests, PR
links, and runbook clarification; it does not modify generic fuzzing or Security Contract
semantics.

- `src/inodefence/evaluation/n01.py` adds the N01-only frozen identity, admission,
  readiness, pair scheduling, evidence, failure-ledger, and automated decision logic.
- `src/inodefence/evaluation/n01_reader.py` adds a fresh-process artifact reader that
  recomputes the accepted evidence instead of accepting the runner's final verdict.
- `src/inodefence/evaluation/node_packaging.py` adds strict validation for a completed
  historical Node build record.
- `scripts/container_host.py` and `scripts/container_controller.py` add the bounded
  two-image/two-context broker path and invoke the independent reader after execution.
- `tests/evaluation/test_n01_qualification.py` adds ten N01 tests covering the full controlled
  8+10 schedule, critical failure/tamper cases, frozen resource admission, and reader
  provenance binding.
- `tests/evaluation/test_node_packaging.py` covers the completed build-record validation.
- `scripts/README.md`, evaluation/test/experiment READMEs, `docs/START_HERE.md`,
  `docs/STATUS.md`, the qualification contract, and the execution-progress record document
  the authorization, execution boundary, runbook, and evidence status.

No raw historical artifact or pilot artifact was created.

## 3. Core algorithms implemented

### Frozen input reconstruction

The runner reconstructs the frozen N01 child through the versioned
`M1_PROTECTED_COMPONENTS` policy and exact scripted mutation draws. It compares full SHA-256
identities for the contract, worker, locks, parent and child cases, input TAR, and sentinel.
Prefix or display-string matches are not accepted. The reconstructed child must produce the
frozen `../outside/sentinel.txt` hardlink target and the exact TAR identity before any target
is admitted.

### Historical admission and readiness

Admission is N01-specific and metadata-only. It validates each completed build context,
immutable full image ID, expected target version, Node version, dependency closure, worker,
and isolation metadata. It does not reuse the normal node-tar 7.5.22 validator and does not
execute the N01 archive. Any admission failure stops before extraction.

After both admissions, four benign cases run independently on each image. The runner checks
regular-file, directory, hardlink, and symlink semantics; successful status; absence of
C0/C1/C2; input immutability; and cleanup. All eight records must pass before the historical
pair is eligible.

### Pair execution and verdict separation

The pair uses the contract's counterbalanced affected/fixed order for five runs per image.
Every completed target attempt is published before expectation checks. Runtime failure,
observation failure, and an observed non-violation remain distinct. The affected expectation
requires successful extraction, sentinel inode aliasing, C1 and C2, and no C0. The fixed
expectation requires the exact rejected status, no alias, and no C0/C1/C2; a generic failed
status is not converted into a safe negative result.

The output retains raw run records, snapshots, inode relations, oracle evidence, artifact
hashes, cleanup records, an infrastructure failure ledger, and five `PairComparison`
records. The path has a hard upper bound of 18 archive extractions and does not retry a
failed attempt.

### Independent reader

The reader starts as a new Python process. It verifies artifact bytes and checksums, frozen
case/TAR/image/build identities, clean source/environment/sentinel bindings, exact isolation
policy, schedule cardinality and order, filesystem snapshots, cleanup, inode relationships,
C0/C1/C2 derivations, target status, and affected/fixed pair validity. It recomputes the
decision and rejects a tampered stored verdict. Its automated completion token is only
eligibility evidence for human correspondence review; it is not the final
`N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` decision.

## 4. Behavior changed from existing code

The normal node-tar 7.5.22 path remains unchanged. The new `qualify-node-n01` broker mode is
additive and requires exactly two full image IDs and two validated build contexts. Existing
single-image modes continue to require exactly one image.

The implementation deliberately composes the existing backend, target, snapshot, oracle,
and pair-storage models. It does not change generic C0/C1/C2 semantics, mutation feedback,
corpus admission, target execution, or observer behavior. Version-specific expectations
exist only in the N01 benchmark decision layer and do not enter generic oracle truth.

The historical readiness phase is not the existing 18-case normal-target transport check.
Only the contract's four benign cases per historical image count as readiness. The old
unmerged historical runner was not reused because its sentinel, transcript, order,
publication, comparison, and independent-reading behavior did not satisfy this contract.

## 5. Validation and results

At implementation checkpoint `0699099806dad1c8df12d8e9cc22dd35b334a4d0`:

- focused mutation/evaluation/broker/reader validation: 228 tests PASS;
- final N01 qualification module suite: 8 tests PASS;
- canonical `make check`: PASS;
- Ruff lint: PASS;
- Ruff format check: PASS across 322 files;
- Pyright: 0 errors, 0 warnings;
- pytest: 1,476 tests PASS in 41.84 seconds;
- Linux runtime environment validation: PASS;
- documentation validation: PASS across 113 Markdown files;
- `git diff --check`: PASS.

The exact 1,476 count is independently supported by
[PR #95 CI run 38692409079](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38692409079):
the check job records `collected 1476 items` and `1476 passed`. The reviewed parent had 1,467
tests; checkpoint `0699099` adds eight N01 qualification tests and one completed-build-record
test, so 1,467 + 9 = 1,476. The 1,475 count is not reproducible at the checkpoint; it equals
the parent plus only the eight N01 qualification tests and therefore predates or omits the
separate completed-build-record test.

The review follow-up adds two contract regressions, for a current total of **1,478** tests.
Canonical `make check` passed locally: Ruff PASS, format PASS across 323 files, Pyright 0
errors/0 warnings, 1,478 pytest tests PASS in 40.47 seconds, Linux runtime environment PASS,
and documentation PASS across 114 Markdown files. This does not retroactively change the
checkpoint's verified 1,476.

The ten N01 tests cover exact reconstruction, a controlled full 8+10 schedule with the
fresh-process reader, zero-extraction admission failure, broker-preflight failure retention,
readiness blocking, artifact tamper detection, stored-verdict distrust, source-binding drift,
frozen resource admission, and rejection of a fixed-target generic failure as a safe result.
Assertions were added rather than weakened, and no existing test was removed.

Current stacked GitHub state verified on 2026-10-15:

| PR | Head / base | Scope at inspected head | CI |
| --- | --- | --- | --- |
| [#93](https://github.com/TheWaitForAGI/InodeFence/pull/93) | `ee6ce6501368ff8a5ab420e254790c3451b997ae` → `main` | 29 files, protected-component policy + exact locks | [run 38692252320 PASS](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38692252320) |
| [#94](https://github.com/TheWaitForAGI/InodeFence/pull/94) | `d8827893ed758ee0437820373964d13564727c6d` → `integration/n01-historical-readiness-v1` | 4 files, reviewed/authorized qualification contract | [run 38692405290 PASS](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38692405290) |
| [#95](https://github.com/TheWaitForAGI/InodeFence/pull/95) | current head `f1d93ddd5ecba6617484601944eae9717d22fc7a` → `review/n01-pair-qualification-v1` | 16 files, contained implementation and review follow-up | [run 38694353851 PASS](https://github.com/TheWaitForAGI/InodeFence/actions/runs/38694353851) |

All three PRs were open, non-draft, unmerged, and reported mergeable when inspected. The
stacked bases match the intended sequence; no PR was duplicated or retargeted.

## 6. Experiments executed and not executed

Executed:

- deterministic case/TAR reconstruction in tests;
- controlled adapter executions of the qualification state machine;
- independent-reader consistency and tamper/failure-path tests.

Not executed:

- historical image preparation or build;
- historical image metadata admission against real immutable image IDs;
- the eight benign readiness archive extractions;
- the ten node-tar 7.5.2/7.5.3 N01 pair archive extractions;
- independent reading of real historical artifacts;
- human affected/fixed correspondence adjudication;
- B0/B1/B3 pilot configuration, campaign, analysis, or figures.

Therefore the actual approved archive-extraction count is **0/18**, the historical
qualification is `NOT_RUN`, and the pilot is `NOT_RUN`.

## 7. Problems encountered and resolutions

The Dev Container had no Docker CLI. This is consistent with the intended trusted-host
boundary. The implementation and runbook were completed, but no attempt was made to install
a daemon, expose a new socket, use a mutable tag, or execute historical archives outside the
approved broker path.

The owner-provided macOS/OrbStack 6/6 boundary result resolves Docker-broker availability for
that host/controller session without changing the Dev Container. It does not resolve the
separate absence of N01 historical images and immutable image IDs.

A broker-preflight failure could otherwise be lost before target construction. A regression
test now requires that failure to be retained before target load. Static contract review also
found that admission accepted non-default resource values and the reader did not explicitly
join source/environment/sentinel bindings back to the manifest. The review follow-up closes
both gaps in N01-only code and adds regressions. Reader tests also exercise the command-line
entry point as a fresh process.

GitHub PR tooling was not available through the local CLI when the stack was created.
Authenticated connector access was verified, existing PRs were searched by head branch, and
the three stacked PRs were then created without changing their reviewed bases. During the
later autonomous-resume audit, an authenticated `gh` CLI was available and independently
confirmed all three current heads, bases, CI results and empty review lists.

## 8. Research facts established

Observed engineering facts:

- the frozen mutation transcript reconstructs the expected child case and input TAR in the
  tested source revision;
- full identity mismatches and artifact tampering fail closed in the covered paths;
- the controlled runner enforces the 8+10 order and blocks the pair after admission or
  readiness failure;
- the controlled independent reader can recompute the accepted schedule, filesystem/oracle
  evidence, and pair decision, and it rejects a modified stored verdict;
- the generic observer and C0/C1/C2 oracle implementation were not changed.

These facts establish implementation readiness for review. They do not establish actual
node-tar 7.5.2/7.5.3 behavior.

## 9. Hypotheses still unverified

The following remain hypotheses or planned measurements:

- node-tar 7.5.2 will complete the frozen archive and produce the expected C1/C2 evidence;
- node-tar 7.5.3 will reject it without C0/C1/C2 or inode aliasing;
- the exact historical images can be built and admitted reproducibly on the already validated
  trusted Mac/OrbStack boundary;
- intermediate filesystem-state feedback improves rediscovery rate or time/executions to a
  verified violation relative to B0/B1 at equal budgets;
- any observed state diversity is security-relevant rather than merely a larger signature
  space;
- the pilot will have enough evidence for anything beyond an exploratory result.

There is no supported known-vulnerability rediscovery, unknown-vulnerability discovery,
new-CVE, superiority, or paper-level effectiveness claim.

## 10. Mandatory human code-review areas

Reviewers should verify:

1. every frozen full identity against the contract and immutable source artifacts;
2. mutation reconstruction and the exact parent/child/TAR correspondence;
3. build-context validation, full image-ID transport, and the host/controller isolation
   boundary;
4. the exact four-case-per-image readiness semantics and the no-retry 18-extraction cap;
5. result-first publication and preservation of timeout, exception, observation, and
   infrastructure failures;
6. C1 `(device, inode)` and C2 before/after sentinel derivations, including C0 exclusion;
7. the exact affected-success and fixed-rejection expectations;
8. raw-manifest/checksum ordering, cleanup evidence, and partial-attempt readability;
9. the reader's independence from the stored runner verdict and any shared-assumption risk;
10. the correspondence between the trusted-Mac commands and the reviewed Python path.

An automated reader PASS must not be recorded as an independent human review.

## 11. Remaining risks and follow-up

No immutable historical image IDs exist yet. The package locks pin npm SHA-512 integrity and
the N01 constants retain the expected package-tarball SHA-256 values. During the later
autonomous-resume audit, both official registry tarballs were fetched to an isolated `/tmp`
directory and independently matched the frozen SHA-256 values. This supplemental container
check does not replace the required trusted-host pre-build verification or create an admitted
image. The runbook gives the exact HTTPS URLs and expected SHA-256 values before either host
build context is prepared.

The first real attempt must use two new build contexts outside the source tree, the
`inodefence-runtime` volume, and a new evidence destination. An admission failure must stop
at zero archive extractions. Any later failure must remain in the original evidence path and
must not trigger a retry or a favorable-run replacement.

If and only if the reader produces the automated replay-complete token, a human must compare
the affected and fixed evidence before recording the contract's final pair-qualified token.
Only after a valid qualification may the separate pilot gate be reviewed. Pilot budgets,
seeds, policies, metrics, stopping rules, and artifact schema must be frozen before any pilot
run; the positive-control TAR must not enter the general seed corpus.

The PR stack must be reviewed and merged in order. Its current unmerged layering is expected
to make later PRs appear non-mergeable until their bases advance; bases must not be rewritten
merely to hide that dependency.

## 12. Commits and pull requests

Relevant revisions:

- main base: `57f751992f60a534c5b07506e72124abe5d6b07d`;
- tested integration: `ee6ce6501368ff8a5ab420e254790c3451b997ae`;
- reviewed contract head: `d8827893ed758ee0437820373964d13564727c6d`;
- tested implementation checkpoint: `0699099806dad1c8df12d8e9cc22dd35b334a4d0`.

Stacked pull requests:

- [#93 — integrate N01 historical readiness prerequisites](https://github.com/TheWaitForAGI/InodeFence/pull/93), base `main`;
- [#94 — freeze N01 pair qualification contract v1](https://github.com/TheWaitForAGI/InodeFence/pull/94), base `integration/n01-historical-readiness-v1`;
- [#95 — implement contained N01 pair qualification](https://github.com/TheWaitForAGI/InodeFence/pull/95), base `review/n01-pair-qualification-v1`.

The executable trusted-host procedure is in `scripts/README.md`. This review package and any
subsequent review-only corrections belong to PR #95; no historical result should be added
until it is backed by the immutable evidence directory from the approved execution path.

## 13. Autonomous resume checkpoint — 2026-10-15 UTC

The requested resume audit independently established the following current facts:

- repository HEAD and remote PR #95 head are both
  `f1d93ddd5ecba6617484601944eae9717d22fc7a`; remote `main` remains
  `57f751992f60a534c5b07506e72124abe5d6b07d`;
- commit ancestry is exactly `main` → PR #93 `ee6ce6501368ff8a5ab420e254790c3451b997ae`
  → PR #94 `d8827893ed758ee0437820373964d13564727c6d` → PR #95 `f1d93ddd...`;
- PRs #93, #94 and #95 are open, non-draft and mergeable with both CI checks successful;
  GitHub reports no submitted reviews and no requested reviewers for any of the three;
- branch-protection details could not be read because GitHub returned HTTP 403 for this
  private repository/plan. PR #95 also explicitly states that it must not be auto-merged, so
  no merge was attempted and no human review was recorded by inference;
- CI run `38694353851` is complete/success at the exact current head; both `check` and
  `container-integration` passed;
- the active checkout contains an unrelated, pre-existing modification to
  `.devcontainer/devcontainer.json`. It was preserved and excluded from this checkpoint;
  the exact PR head was instead validated in a detached clean worktree;
- the frozen lock, contract, worker, child case, generated TAR and sentinel hashes all match
  the contract. Official registry tarballs matched
  `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a`
  for 7.5.2 and
  `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66`
  for 7.5.3;
- clean, no-overwrite packaging preparation succeeded for both versions at source revision
  `f1d93ddd...` with `dirty:false`. Temporary prepared contexts are
  `/tmp/inodefence-n01-context-7.5.2-f1d93dd` and
  `/tmp/inodefence-n01-context-7.5.3-f1d93dd`; they are pre-build engineering output, not
  historical images or qualification evidence;
- `/var/lib/inodefence` is the separate `inodefence-runtime` btrfs volume, device 42, owned by
  UID/GID 1000. The environment checker passed hardlink, symlink and shared-object-effect
  probes, and no existing `/var/lib/inodefence/evidence` directory was present;
- the session is inside the Linux OrbStack Dev Container (`aarch64`, Python 3.12.3), not the
  trusted macOS host. There is no Docker CLI in the controller, so controller full identity,
  historical image builds, immutable image IDs, broker admission and archive execution could
  not be performed without violating the approved trust boundary;
- focused N01/mutation/packaging validation passed 71 tests. A clean-head `make check` passed
  Ruff, format across 323 files, Pyright with zero errors/warnings, all 1,478 pytest tests,
  runtime environment validation and documentation validation across 114 Markdown files;
  diff whitespace checks also passed.

Historical execution status remains exactly **0/18**: metadata admission is `NOT_RUN`, benign
readiness is **0/8**, the historical pair is **0/10**, and real-artifact independent reading
is `NOT_RUN`. Therefore no C0/C1/C2 historical evidence exists. B0/B1/B3 remain `NOT_RUN` and
blocked by the qualification gate. The research hypothesis is **NOT_EVALUATED**; the verified
facts support implementation and frozen-input readiness only.
