# N04 node-tar five-second preflight Task Contract v1

Status: **AUTHORIZED BY DIRECT USER TASK CONTRACT / IMPLEMENTATION PENDING / NOT_RUN**.
Authorization date: **2026-10-16**. This contract is narrower than the proposed B0/B1/B3
pilot and does not amend the frozen N01 qualification contract.

## Objective and Layer

Current Layer: Layer 6 historical-target readiness and evidence validation.

The only experimental question is whether the exact retained node-tar 7.5.2 and 7.5.3
images remain correctly identified, contained and benign-ready when every target execution
uses the evaluation protocol's predeclared **5-second** timeout. The result may be
`PREFLIGHT_PASS`, `PREFLIGHT_FAIL` or `INCONCLUSIVE`; it is not a rediscovery or feedback
effectiveness result.

## Authorized execution budget

One attempt, no retry, with an overall wall-clock ceiling of 30 minutes:

1. read-only host broker, controller, volume and image identity inspection;
2. metadata/image admission for the two exact images;
3. one unchanged oracle control and one harness hardlink oracle control;
4. each of the four existing `minimal_seed_corpus()` cases once on node-tar 7.5.2;
5. the same four cases once on node-tar 7.5.3; and
6. one fresh-process independent read of the checksummed attempt.

The maximum target archive extractions are **8**. Identity probes and the two harness-only
oracle controls are reported separately. Every target execution uses exactly 5 seconds.
All eight readiness outcomes are retained even if one complete target outcome fails readiness;
an infrastructure or containment failure stops further execution and is retained.

The exact Linux evidence destination is
`/var/lib/inodefence/evidence/n04-five-second-preflight-20261016T130000Z`. It must be absent
before execution, is enforced by the runner rather than caller convention and is never
reused. The host must first create the exact no-overwrite attempt/cleanup ledger
`/Users/choijiwng/Projects/InodeFence-n04-5s-preflight-20261016T130000Z-host-ledger`;
its existence consumes the single attempt even if containment admission fails before Linux evidence
publication. An alternate path is not another authorized attempt. A read-only host copy may be
created at `/Users/choijiwng/Projects/InodeFence-n04-5s-preflight-20261016T130000Z` after completion.

## Frozen target candidates

| Binding | affected | fixed |
| --- | --- | --- |
| Node / node-tar | 22.22.0 / 7.5.2 | 22.22.0 / 7.5.3 |
| Image ID | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` |
| arm64 platform manifest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` |
| npm tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |
| lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| build record SHA-256 | `960b28e0699af5c6ac35709d2d14d7a8818ea8cfed0039f86b3b0217c68997ef` | `e6adeae1456771dce3e0d20acb3e231ceefd5e726a4c8bf554fc402f62ac8960` |

Both images must report worker SHA-256
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`.
The retained N02 build contexts are permitted only as immutable admission inputs; their
source revision remains historical. The new attempt separately records and requires a clean
current controller source revision whose worker and locks match those image artifacts.

The target image IDs, architecture, package/lock/worker bytes, exported repo/manifest
identities when available and current runtime inspection must agree before an archive runs.
A mutable tag cannot replace an image ID.

The exact official `tar-7.5.2.tgz` and `tar-7.5.3.tgz` byte streams are admission inputs,
not Docker build inputs. The runner publishes both under `packages/` and compares their
SHA-256 values with the table before build admission. The independent reader rehashes the
retained bytes. A missing or mismatched tarball stops before target execution and is
`INCONCLUSIVE`.

## Frozen environment and containment predicates

The trusted route is host macOS/OrbStack Docker context `orbstack` to one newly created,
unprivileged Linux arm64 controller with:

- a read-only source bind at `/workspaces/InodeFence`, separate from runtime;
- named volume `inodefence-runtime` at `/var/lib/inodefence`;
- no Docker socket mount and no direct target subprocess fallback; and
- broker requests restricted to the existing owner-labelled container backend.

The controller additionally requires the dedicated `org.inodefence.n04-preflight-controller=v1`
label, network `none`, read-only rootfs, cap-drop `ALL`, no-new-privileges, no devices, a 1 GiB
memory/swap cap, 256 PID cap and a 256 MiB `nosuid,nodev` tmpfs. Its inspected creation time must
be no more than 15 minutes before this broker invocation. The host clock starts before
controller/daemon/image inspection and bounds every Docker request, the controller, fresh reader and
target cleanup to 30 minutes. A cooperative controller deadline reserves reader/finalization time;
the host hard deadline is only a fallback. The no-overwrite host ledger records early failure,
deadline state, the controller return code, invocation-owned target names and cleanup outcome.

The broker attestation records the Docker executable, context, daemon ID/version/API,
controller full ID/image/mounts/privilege state, volume identity and both inspected images.
The execution source is the exact clean reviewed commit containing this contract and the
preflight implementation; its full SHA is recorded by the attempt rather than predicted in
this document.

Every target container must retain the existing `docker-volume-subpath-v1` policy:

- UID/GID 1000, network none, read-only rootfs, cap-drop `ALL`, no-new-privileges;
- private PID/IPC/cgroup namespaces;
- 512 MiB memory and swap, 64 PIDs, 1,024 open files;
- 64 MiB file-size limit, 32 MiB `/tmp`, 16 MiB `/dev/shm`;
- 1 MiB capture per stream; and
- one fresh runtime-volume subpath, empty `extract/`, controlled same-filesystem sentinel,
  stopped target/descendants before AFTER and cleanup after evidence capture.

The controlled sentinel is `outside/sentinel.txt`, mode `0600`, with the existing frozen
benign content digest
`caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b`.

## Input, output and decision rule

The input corpus is exactly `minimal_seed_corpus()` in its existing order. The runner must
recompute all four logical case IDs and deterministic USTAR digests. It performs no mutation,
candidate replay, positive known-class extraction or corpus evolution.

The unchanged oracle control passes only with C0/C1/C2 all false. The harness hardlink control
passes only with C0 false and C1/C2 true; it is labelled harness behavior.

Readiness passes only if all eight records:

- return `SUCCESS` without timeout at configured timeout 5 seconds;
- preserve the exact input TAR before/after;
- produce no C0/C1/C2 observation;
- reproduce the expected regular/directory/internal-hardlink/internal-symlink benign state;
- bind exact source, target, sentinel, environment and isolation provenance; and
- prove their runtime root absent after return.

`PREFLIGHT_PASS` requires two admissions, two passing controls, eight passing readiness
records, no failure record and independent-reader agreement. A complete but unexpected target
result is `PREFLIGHT_FAIL`. Missing/corrupt evidence, broker/identity/containment mismatch,
observer error, failed cleanup or interruption is `INCONCLUSIVE` / infrastructure invalid.
No result automatically selects 10 seconds or authorizes the pilot.

## Implementation boundary

Allowed files/modules:

- one separately versioned preflight runner and independent reader under
  `src/inodefence/evaluation/`;
- additive, allowlisted broker/controller mode wiring;
- focused controlled-adapter and broker-schema tests;
- this contract, a raw-evidence report and minimal STATUS routing.

Forbidden changes:

- `src/inodefence/evaluation/n01.py`, its frozen timeout/token/decision rule or old evidence;
- generic builder, mutator, observer, C0/C1/C2 oracle, feedback or campaign policy semantics;
- N01 positive-control extraction, any B0/B1/B3 execution, 4,000-run pilot, v2/v3 native
  qualification or P0/P1/P2 effectiveness work; and
- host secrets, primary checkout edits, PR #92 changes or source bind mounts as target runtime.

The preflight schema/protocol IDs are new. No N01 human token or pilot token can be emitted.

## Stop conditions and validation

Stop before target execution on dirty/unavailable source, wrong broker/controller/volume,
privileged controller or Docker-socket mount, unexpected image/package/worker/lock identity,
wrong architecture, mutable identity, isolation/resource mismatch or unavailable independent
reader. Stop the attempt on infrastructure/cleanup failure. Preserve every published partial
record and never retry into this evidence root.

Before execution, the functional head receives Ruff, format, Pyright, pytest, environment and
docs validation plus independent adversarial review. The final PR must also pass GitHub
`check` and `container-integration`. This authorization covers this preflight only; the
4,000-run B0/B1/B3 pilot and all native effectiveness campaigns remain **NOT_AUTHORIZED /
NOT_RUN**.
