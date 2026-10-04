# Benign Node container plumbing validation v1

Classification: engineering validation with raw evidence. No vulnerability finding,
benchmark effectiveness comparison or evaluation result is claimed.

## Actual path and conditions

Pinned image identity discovery → ExperimentConfig v2 → exact target/policy binding
→ fail-closed safety gate → frozen source/environment/target/sentinel/isolation facts
→ four minimal generic seeds → bounded Campaign/Corpus/mutation → run_case → disposable
Node target container → BEFORE/AFTER Observer → C0/C1/C2 + StateSignature v2 → Feedback
→ CampaignResult → stored manifest v3 and canonical JSONL (export durability is next).

The trusted Ubuntu 24.04/Python 3.12.3 Linux controller runs outside the untrusted target.
The explicit host broker uses Docker 29.4.0/OrbStack, API 1.54, Linux arm64; no socket or
additional privilege was added to the Dev Container. Runtime is the existing named Linux
volume at /var/lib/inodefence; only the current core-run subdirectory is exposed.

Node 22.22.0, tar 7.5.22, strict=true/preservePaths=false, timeout10 seconds.
Target image ID:
`sha256:4b73ec653ee295ce63c58b9bac6db7dd9e5d584e12704ee4db740a307b8f1697`.
Worker SHA-256: `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`.
Lock SHA-256: `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930`.
Config ID: `5fe3249f599d74259fd4f76aeb6da085e66e7e075d00053cd1ba1b4b9c88ee13`.
Source revision efe1dbb5ec3787dee42eadb643646be2b326b489 with dirty=true
(the new validation entry/test); dirty patch contents are not embedded in provenance.

Enforced policy: network none; read-only rootfs; uid/gid1000; cap-drop ALL;
no-new-privileges; private PID/IPC/cgroup namespaces; 512MiB memory and memory+swap;
64 PIDs; nofile1024; per-file FSIZE64MiB; tmpfs/tmp32MiB/noexec/nosuid/nodev;
private shared memory16MiB; first1MiB per output stream, overflow aborts incomplete evidence.
The controlled archive/extract/outside run is writable; source/home/socket and adjacent
runs are not mounted. Kernel/runtime trust and non-volume ephemeral mounts remain limits.

## Observed result

Fixed RNG11, budget8: four initial cases plus four mutations, exact indexes0–7 and
valid prior-parent lineage. Every archive was checked for ordinary relative POSIX
path/link spelling before actual execution. No known exploit/PoC/CVE input was used.
The guard does not alter mutation, RNG, budgets or outcomes and is validation-only.

| Record | Actual value |
| --- | --- |
| Archive executions | 8 |
| Status counts | SUCCESS8; REJECTED0; FAILED0; TIMED_OUT0 |
| Corpus observations | 8 |
| Interesting observations / retained cases | 6 / 6 |
| Unique normalized states | 6 |
| Violation fingerprints | 0 |
| C0/C1/C2 | No violated verdict in this observed snapshot scope |
| Containers | 9 created / 9 removed (one identify + eight archives) |
| Runtime | All nine controlled roots absent; existing runtime listing preserved |

Stopped PID0/top-unavailable state was checked before removal; each identity was absent
before the next case. JSONL canonical parsing, stored provenance/config ID, image/policy
and checksum were verified. Interesting states are not vulnerability evidence.

Local ignored evidence is `experiments/raw/benign-node-container-20261004-e1/`.

| File | SHA-256 |
| --- | --- |
| steps.jsonl | ada0b6cdb36231a792a0554be2f24360b8e0d952a3d08c5681de2c485695462d |
| manifest.json | 04e923a4ff73e2aead9c5590d5807819d55f1ba281e338e85017085893d5fc4c |
| experiment.json | b0920e91776e9493dd5d5fc30b950e82b19d2e060fa7b36dffb1e2090445bec2 |

Raw inode/times/durations are preserved and are not expected to repeat byte-for-byte.
Image IDs/config IDs may differ across builds/platforms even with the pinned inputs;
bit-for-bit image reconstruction and remote registry availability are not promised.

## Re-run and stop policy

Build the [pinned image](../../tools/node-tar/README.md), resolve its immutable ID, then:

```bash
PYTHONPATH=src python3.12 -m scripts.container_host --context orbstack \
  --controller <dev-container-ID> --volume inodefence-runtime \
  --image <immutable-image-ID> --evidence /tmp/<new-evidence-directory> benign-node-smoke
```

Evidence is written in the trusted Linux controller. Copy it to host storage before
removing that controller; CI preserves/uploads produced evidence before cleanup.
Existing evidence destinations are rejected. If unexpected contract evidence appears,
raw RunResult, the already-frozen provenance and immutable config are preserved, then
validation stops. A portable regression exercises this policy with an intentional
metadata change to a disposable sentinel, never an exploit archive or real host file.

Next: focused lifecycle review, staged-export durability, and limited architecture
freeze before the separate full repository audit. Snapshot-only observation, total
volume/CPU limits, container/kernel portability/trust, dirty-patch preservation and
finite artifact retention remain explicit limitations.
