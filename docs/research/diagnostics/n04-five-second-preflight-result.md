# N04 five-second preflight result

Status: **PREFLIGHT_INCONCLUSIVE / ATTEMPT CONSUMED / NO RETRY**.

Execution date: 2026-10-18 KST (host ledger start
`2026-10-17T16:14:46.687762+00:00`). This is machine evidence and an AI technical assessment,
not human expert approval or an N01 qualification token.

## Exact execution boundary

- execution source: clean detached
  `f545639b9e7fd8fdb5b0089ac31455cf66db1c77`;
- controller: disposable full ID
  `f31bb2d7de29310e11ff7c2b933aa53ffbfcee2ea30019dce1b4eb12b8681e3f`;
- targets: frozen node-tar 7.5.2 and 7.5.3 immutable image IDs from the Task Contract;
- requested timeout: exactly 5 seconds per target;
- authorized schedule: two harness controls and at most eight benign target extractions;
- observed target extractions: **0**;
- observed oracle controls: **0**; and
- B0/B1/B3, known-class replay, native P0/P1/P2 and a 10-second fallback: **NOT_RUN**.

Before the attempt, both GitHub jobs passed for the exact source object. A canonical Ubuntu
24.04/Python 3.12 arm64 validation also passed Ruff, format, Pyright, 1,556 pytest cases,
environment validation and documentation validation. A pre-attempt operator inspection observed
the fresh controller's required network, privilege, capability, namespace, resource and mount
values, and observed that its dedicated labelled volume had exactly that controller as its sole
consumer. The broker failed before publishing these facts into Linux raw evidence, so they cannot
be used to infer containment admission or a readiness PASS.

## Retained evidence and reconstruction

The immutable host evidence is:

`/Users/choijiwng/Projects/InodeFence-n04-5s-preflight-20261016T130000Z-host-ledger`

The directory is mode `0500`; its three files are mode `0400`.

| File | SHA-256 |
| --- | --- |
| `started.json` | `1dab6f33e22d80ab5a525d4f8f87eb88539a555a5f061a49d7c015f851633074` |
| `terminal.json` | `39a3e8e2e7e85be9bcc756b8f5c5dfcb690f7dd3385ff8c425c21907f5dc18fc` |
| `manifest.json` | `a59901f3938c105717f437faf05853f3f5698b65e6e57b955fd2a34d713136b0` |

`verify_n04_host_ledger(...)` successfully reconstructed the bound host records and returned:

```text
overall_status=PREFLIGHT_INCONCLUSIVE
raw_manifest_sha256=None
final_manifest_sha256=None
```

The ledger records elapsed time `0.1519525838084519` seconds, no deadline expiry, no target names,
`cleanup_status=not_needed`, no cleanup errors and this exact terminal exception:

```text
inodefence.execution.base.BackendError: invalid trusted Docker command request
```

The Linux evidence root was never created, so a Linux raw manifest, Linux final manifest and fresh
Linux independent-reader verdict are **NOT_RUN / unavailable**, not failed evidence. No read-only
Linux evidence copy exists. The disposable controller and its empty dedicated volume were stopped
and removed after their absence of experiment evidence and target consumers was verified; both were
then confirmed absent. The host ledger was retained.

## Root cause and scientific decision

The host broker attempted `docker info --format {{json .}}` through `DockerCLI.run()`. The generic
transport allowlist intentionally permits target lifecycle operations but not daemon-wide `info` or
container-list requests. It therefore rejected the first broker metadata request before initial
JSON reached the controller. The controller's JSON decode traceback is a consequence of the broker
closing that stream, not a target result.

This is an orchestration defect, not evidence that either node-tar target passes or fails a
five-second readiness bound. The correct scientific decision is therefore:

- containment admission: **INCONCLUSIVE** (broker attestation did not publish);
- five-second benign readiness: **NOT_EVALUATED**;
- timeout comparison or change to ten seconds: **NOT_EVALUATED / NOT_RUN**; and
- central feedback-effectiveness hypothesis: **NOT_EVALUATED** by this attempt.

The post-attempt implementation separates two exact host-only, read-only inspections from the
controller-visible stdio command allowlist and adds a regression test. That correction was not used
to produce experimental evidence. Because the no-overwrite host ledger consumed the sole authorized
attempt, another historical-target run requires a new explicit Task Contract, attempt ID and evidence
destinations. It must not overwrite or reinterpret this result.
