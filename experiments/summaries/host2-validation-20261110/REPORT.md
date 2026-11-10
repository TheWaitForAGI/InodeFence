# HOST2 Validation Report

## 1. Executive Summary

**Update:** Docker and WSL were subsequently updated; the later state and pending WSL memory configuration are recorded in section 17. The earlier sections retain the original observations.

**PARTIAL / host qualification UNKNOWN.** Read-only inventory at 2026-11-10 14:17–14:20 UTC (23:17–23:20 KST) found Docker Engine 29.9.2 instead of the design's 29.8.0, and the exact target image is absent. Available WSL memory was below the proposed 15 GiB preflight threshold. No smoke, concurrency test, or formal experiment was run. Observations are time-specific and self-reported, not authenticated attestation.

## 2. Hardware Inventory

Windows reports Intel Core Ultra 7 270K Plus, 24 cores / 24 logical processors, 33,693,589,504 bytes RAM and AC online. A later Windows query reports 13,173,928 KiB free physical memory. One NVMe SSD, CT1000E100SSD8, 1,000,204,886,016 bytes, was enumerated; no external SSD was enumerated at that time. This does not establish whether one is normally connected. See `windows-disks.stdout` and its command record.

## 3. Windows Configuration

Windows 11 Pro build 26200; WSL reports build 26200.9711. The collector reported active hours 16–05, no configured Windows Update/AU policy found, effective MDM policy UNKNOWN, and no reboot-required flag in the probes used. Its reboot-name task enumeration is not exhaustive proof that no restart can occur. Measurements were under a non-elevated Windows account; no elevated check was performed.

## 4. WSL2 Configuration

WSL 2.7.14.0, Ubuntu 24.04.5 LTS, kernel 6.18.33.2; affinity CPUs 0–23. `/etc/wsl.conf` enables systemd and interop. The probe could not read `.wslconfig` because the file was absent; defaults and other host limits still apply. Linux total memory 16,051,892 KiB and available 14,082,420 KiB in the collection, swap 4,194,304 KiB. Open-file limit 1,048,576 and process limit 62,659 were observed separately. Root filesystem is ext4. A Windows 10.033-second sleep corresponded to 10.160 seconds of Linux monotonic time including process startup; this coarse observation does not establish clock-rate accuracy. See clock records.

## 5. Docker Configuration

Desktop 4.96.2 (244353), CLI and Engine 29.9.2, context `default`, 24 CPUs and 16,437,137,408 bytes VM memory; cgroup v2, overlayfs using containerd snapshotter, Docker root `/var/lib/docker`. The earlier 11:00 UTC collection could not access Docker; the later collection did. This change is an observation, not an attributed configuration change. Exact target image `sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb` was separately inspected and absent; the collector's target, controller and helper tags were also absent. No image was built or changed.

## 6. Storage and VHDX Mapping

The proposed output's nearest existing parent reported ext4 1,013,508,923,392 available bytes and 66,893,114 free inodes. This is virtual filesystem capacity, not guaranteed physical free space. Windows C: on disk 0 reported 99,427,897,344 bytes free. WSL registration places the Ubuntu-24.04 distro on C:, while the default Docker data VHDX candidate was found on C:; effective Docker backing VHDX identity and actual physical usage remain UNKNOWN. No external drive was enumerated. Docker VM virtual free space alone does not establish backing-store capacity.

## 7. Resource and cgroup Limits

At collection, 14,082,420 KiB available WSL RAM is below the proposed 15 GiB minimum (15,728,640 KiB); instantaneous result **FAIL**, not a permanent hardware conclusion. Docker VM total memory exceeds 15 GiB but available VM memory and per-job effective limits are distinct. The current process cgroup `/init.scope` reports `cpu.max` = `max 100000` and `memory.max` = `max`; root cgroup does not expose these controller files. This does not rule out WSL or host limits. CPU/memory pressure was zero in the collected short averages; IO pressure varied later. Workload-specific cgroup and sustained load remain UNKNOWN.

## 8. Power and Restart Protection

AC sleep and hibernate timeouts were both zero in the measured active power plan. Update AU and MDM effective policies were not established, and no automatic restart policy was verified. A negative pending-reboot probe does not guarantee no reboot. Restart protection **UNKNOWN**; no settings were modified.

## 9. Image / Execution SHA Consistency

The separate execution checkout was clean at `afdc720da6eb6ae143bd4754cb39d6dd34ea8f16`; the collector checkout was `6dddb7568ff3101a30eeba93cdabac5fccdfd369`. On 2026-11-10 GitHub API showed PR #325 open at that candidate SHA and #316 open at the tool SHA; neither represents a newly established freeze. The pinned image is absent and Engine mismatches the design, so the execution contract is **FAIL** on the observed prerequisites; transferability of another engine has not been established. No rebuild or downgrade was performed.

## 10. Engineering Smoke Results

**NOT RUN / BLOCKED.** The required image and exact engine prerequisites are not met; HOST2-specific approval and execution conditions have not been established. No seeds, sentinel or budgets were executed. Formal EXP-2/EXP-3, H1 reruns and Stage A were not run.

## 11. Container / Volume Cleanup

The later inventory reported four stopped containers and three volumes, including existing InodeFence volumes. They predate this inspection; ownership and experiment relevance require review. No container or volume was removed or created. This is not a clean-runtime qualification.

## 12. HOST1 vs HOST2 Comparison

The v2 design specifies Engine 29.8.0 and target image above, while HOST2 observed 29.9.2 and missing image. Direct HOST1 measured hardware, current free capacity, and host-specific runtime values were not independently obtained here and are UNKNOWN. H1 remains `halted` / `selected_jobs=null`; these observations cannot change it.

## 13. PASS / FAIL / UNKNOWN Matrix

| Condition | Result | Basis / limit |
| --- | --- | --- |
| Available memory | FAIL | 14,082,420 KiB at collection, below proposed 15 GiB |
| Docker CPU and memory | UNKNOWN | 24 CPUs and 16,437,137,408 total bytes; workload headroom unverified |
| Effective cgroups | UNKNOWN | process and ancestors do not establish per-job limits |
| Output space and inodes | UNKNOWN | virtual ext4 free exceeds proposed threshold; backing physical capacity must be evaluated |
| Docker storage | UNKNOWN | virtual free and candidate VHDX do not establish effective physical capacity |
| Resource conflicts | UNKNOWN | existing stopped containers and volumes need ownership review |
| Sleep and restart | UNKNOWN | AC timers checked; restart protection not established |
| Other users / load | UNKNOWN | instantaneous process list is not a sustained host-wide exclusivity check |
| HOST1 contract | FAIL | Engine mismatch and target image absent |
| Clock / watchdog timing | UNKNOWN | bracketed follow-up indicates a time-dependent monotonic rate discrepancy; see section 19 |
| Qualification / freeze | UNKNOWN | verifier does not grant either |

## 14. Remaining Blockers

Obtain an approved compatible engine/image path without rebuilding or changing versions until comparability is decided; verify runtime and parent cgroups, real backing disks and capacity; establish sufficient available memory, restart protection and exclusive host usage; resolve existing resource ownership; establish HOST2-specific smoke approval, seed exposure and exact command. Treat failed or inaccessible probes as UNKNOWN. The collector's target-image inspection failed; its verifier accordingly returns inputs-consistent UNKNOWN, while independent image inspection confirmed absence on this daemon at that time.

## 15. Recommended HOST2 Qualification Steps

Resolve the blockers with the research owner, record a new preflight and independently verify any changed settings. Use a new output path and explicitly approved HOST2-specific execution contract and exposure procedure before any smoke. Run only separately authorized concurrency checks, then assess host transferability and freeze independently. Do not infer qualification from this report or change H1's existing decision.

## 16. Evidence Manifest and SHA-256

`SHA256SUMS` covers the public files alongside this report. The original read-only collector bundle is retained locally, unmodified, outside the repository; it contains machine-identifying paths and process details and must be reviewed before sharing. Its `collection.json` SHA-256 is `f699ea2aec9a6a602c65e8cda03ad5f4a59c7136faf8330d736f0e593029ad7e`. `verifier.json` is the unmodified output of the documented verifier with the proposed jobs=2, memory=16106127360, disk=20000000000 thresholds. The collector records per-command timestamps, argv, exit codes, timeout and stdout/stderr hashes in that private bundle. Linux and Docker extracts are byte-identical; Windows disk and clock outputs have CRLF normalized to LF, and the Linux command path is redacted. The public extracts are not a complete bundle. Hashes detect alteration, not machine identity or authenticity. No Oracle or feedback raw data was accessed or published. `make check` was attempted on this WSL host and stopped at lint because the `python` executable was absent (exit 2); the required Dev Container validation was not performed. The public manifest was independently checked with `sha256sum -c`, and the staged diff passed `git diff --cached --check`.

## 17. Subsequent changes and post-change inventory

The user initially requested general updates, then clarified that changes should serve HOST2 experiment readiness. Docker Desktop was updated from 4.96.2 to 4.99.0 using `winget.exe upgrade --id Docker.DockerDesktop --exact --accept-source-agreements --disable-interactivity`; the installer reported hash verification and successful installation. Docker restarted with no running containers observed beforehand. Engine changed from 29.9.2 to 29.9.3; it still does not satisfy the frozen 29.8.0 contract. The subsequent read-only collection observed the same four stopped container IDs and three volume names as before; this comparison does not establish volume content integrity.

`wsl.exe --update` changed WSL 2.7.14.0 / kernel 6.18.33.2 to WSL 3.0.5.0 / running kernel 6.18.58.1. Its process handle was lost during the update, so the exit code was not recovered; installed and running versions were checked afterward. The WSL environment restarted during the update. No Windows reboot was initiated. The post-update collector still found the target, controller, and helper image tags absent, and the verifier still returned UNKNOWN for host qualification and freeze eligibility. Post-update available WSL memory was 14,288,360 KiB, still below the proposed 15 GiB threshold. These measurements do not qualify a smoke or experiment.

At 14:35 UTC, the previously absent Windows user `.wslconfig` was created with `[wsl2]` and `memory=20GB`. The exact content and hash are in `wsl-memory-change.json`. This sets a maximum, not a reservation; host availability and memory pressure still need measurement. No WSL shutdown was requested after this change, so application of the new cap is **pending**, not PASS. Avoid interrupting other work; recheck the actual limit and preflight after a coordinated restart.

A later non-elevated registry query found pending file-rename operations; this is evidence of pending operations, not proof that Windows Update requires a reboot. It narrows the earlier negative reboot probe and leaves restart protection UNKNOWN. No firmware, drivers, Windows Update, image, or Docker downgrade was applied. The exact target image and compatible execution engine remain prerequisites; PR #325 is review-only and #328 reports an unresolved stop/start defect, so neither indicates execution approval.

The post-update collector bundle is retained locally; its collection.json SHA-256 is `6b173bc5b4b2f9df6002fbaa19a59a26de90fe8f642aa0d256c98c5ad4d2d3d0`. Post-update Linux, Docker version and verifier outputs are included here.

Docker documentation identifies Desktop 4.91.0 as including Engine 29.8.0 ([release notes](https://docs.docker.com/desktop/release-notes/#4910)). This is a candidate for investigation, not evidence that downgrading preserves this installation, is compatible with WSL 3.0.5, or is safe. The [Engine 29 release notes](https://docs.docker.com/engine/release-notes/29/) identify security fixes in releases later than 29.8.0. The tradeoff and reproducibility must be resolved before any version change; no downgrade or image rebuild was performed.

## 18. Follow-up: image custody, storage, administrator policies and clock

Decision D18 in `docs/DECISIONS.md` specifies retaining a single built image using `docker save`; the fixed ID is host-built and a rebuild is not assumed to reproduce it. A filename-only search of this user's Linux home found no matching image archive, and the first page of repository CI artifacts did not expose an obvious image archive. Neither search proves that no copy exists elsewhere. The HOST1 image archive and trusted transport/checksum remain to be located; no image was rebuilt or loaded.

A subsequent Windows query identified the active Ubuntu-24.04 registration's ext4 VHDX on C: and Windows mapped C: to NVMe disk 0, with 107,948,929,024 bytes available at the query time. A candidate Docker data VHDX also exists on C: (29,126,295,552 bytes), but `Get-DiskImage` returned `Attached=false` and no device path. That API result does not establish which file Docker's WSL backend actively uses; Docker backing mapping remains UNKNOWN. The public excerpt redacts user-specific paths, and the original output and hash remain in private local evidence.

An **elevated** read-only Windows policy and scheduled-task diagnostic at 14:42:58 UTC returned `ADMIN=True`. The queried policy and reboot-required keys were not found or not accessible; pending rename operations were present. The UpdateOrchestrator tasks and their reported next-run values are in the redacted excerpt. This does not prove a reboot is pending due to Windows Update or that all automatic restarts are prevented. No Windows policy was changed; restart protection remains UNKNOWN.

An additional four-sample Windows Stopwatch/WSL clock comparison over approximately 30 seconds yielded Windows Stopwatch 30.039 seconds and WSL monotonic 29.194 seconds between received markers. Windows and Linux UTC samples also showed varying apparent offsets. Variable cross-process output propagation and scheduling are not bounded, so this observation is **not** a calibrated rate or a PASS/FAIL; the discrepancy warrants a controlled independent clock-rate check before using elapsed-time-sensitive watchdogs. `clock-repeat.json` contains the samples and exact command. No experiment was run.

## 19. Bracketed clock follow-up

A read-only request/response measurement at 14:46 UTC brackets every Windows Stopwatch sample with WSL clock reads, limiting interop latency uncertainty. Between requests 1 and 4, Windows Stopwatch advanced 30.992023 seconds; WSL `CLOCK_MONOTONIC_RAW` advanced between 30.991349 and 30.992525 seconds, whereas `CLOCK_MONOTONIC` advanced between 30.001609 and 30.002757 seconds. This sample indicates approximately 3.2% slower monotonic progression relative to Windows Stopwatch, within the measured request brackets. It is a short engineering observation, not a calibrated long-duration guarantee. The source and raw samples are provided; the public script changes only its output path to avoid disclosing a local path.

A separate read-only `adjtimex` query reported `tick_us=9686` with `CLK_TCK=100`; an earlier query reported 9662. The tick adjustment is consistent with a shortened adjusted-clock interval but its cause and persistence are not established. At approximately the same time, systemd-timesyncd reported an offset of +1.052 seconds; this is the Linux service's estimate, not a Windows measurement. Neither a clock adjustment nor a service restart was performed. Treat clock-rate adequacy as UNKNOWN and investigate before a watchdog-sensitive experiment; no threshold has been silently changed.

## 20. Time synchronization intervention and rollback

A subsequent elevated Windows diagnostic found W32Time using `Local CMOS Clock` and reporting unsynchronized status. The configured peer was `time.windows.com`. A first `w32tm /resync` attempt reported that the service was stopping; the command's exit code alone was misleading and the follow-up status query failed. An elevated operator then started the existing **Manual** W32Time service and issued `w32tm /resync` again; the command reported success and its immediate status identified `time.windows.com,0x9` as source and stratum 5. This is a point-in-time observation, not proof of sustained synchronization or a permanent startup-policy change. Both attempts and their original transcript hashes are retained.

Ubuntu's [WSL time synchronization guidance](https://ubuntu.com/wsl/docs/latest/explanation/time-sync/) notes that Ubuntu 24.04 `systemd-timesyncd` may conflict with implicit Hyper-V synchronization. With both enabled and after the Windows resync, an authorized reversible test stopped and disabled `systemd-timesyncd`; Hyper-V `timesync_implicit` remained enabled. Its previous state was active/enabled. A 30-second bracketed comparison still showed Windows Stopwatch 31.031397 seconds vs WSL monotonic 30.001285–30.002607 seconds. The adjusted kernel tick was then reset from 9665 to 10000 microseconds and scaled frequency from 1465180 to 0 using `adjtimex`, with no explicit wall-clock step. The rate setting subsequently changed again, and the next comparison still showed Windows 30.613345 seconds vs WSL monotonic 30.001713–30.003384 seconds.

Because normal behavior was not demonstrated, the service was restored using `systemctl enable --now systemd-timesyncd.service`, returning it to **active/enabled**, its original persistent state. A further comparison after restoration found Windows 30.895992 seconds vs WSL monotonic 30.002180–30.004089 seconds. These short observations indicate a persistent discrepancy; they do not identify the component responsible. The experimental tick reset is not a persistent configuration and was subsequently overwritten. Windows W32Time was started and resynchronized; no Windows reboot, WSL shutdown, or Docker restart was initiated during this intervention. Further investigation and a sustained independent timing check remain necessary before watchdog-sensitive execution.

`clock-adjustment-log.json`, the three clock samples, `reset-rate.c`, and the redacted Windows admin transcripts preserve commands, before/after states, statuses and source hashes. The Windows transcripts contain Korean text; NUL bytes introduced by native command output and identifying transcript headers were removed from public excerpts, and their original bytes are retained privately. No experiment was run.

## 21. Time-service syscall observation

A bounded read-only `strace` attached to the running `systemd-timesyncd` process and observed two `clock_adjtime(CLOCK_REALTIME, ...)` calls with `ADJ_SETOFFSET` during the observation. The `timeout` command exited 124 as intended; its outer Python timeout did not trigger. Afterward the service was still active/running and no `strace` process remained. This establishes that this service issued realtime-offset adjustment calls in the observed interval. The trace does **not** identify the actor changing `tick`, establish the magnitude of either adjustment, prove the source of the monotonic-rate discrepancy, or show whether other components also adjust the clock. The original trace and command/exit/hash metadata are included. No experiment was run.

## 22. Time syscall trace and attribution limitation

A separate tracefs instance observed syscall entry events for 40 seconds at approximately 15:05 UTC and was removed afterward; the runner exited 0 with no timeout. The trace reported 28 entries in its buffer and 28 written: 26 `clock_adjtime` entries by a task named `chronyd` and two by a task named `systemd-timesyn`. It recorded syscall entry only: arguments were pointers, so the modes and results cannot be inferred. Later process listings in the Ubuntu, Docker Desktop, and WSL system views did not identify the `chronyd` task; its namespace, owner, ongoing state and effect remain UNKNOWN. Do not stop an unidentified service. A subsequent controlled probe demonstrated that the trace PID differs from the PID visible in the Ubuntu distribution (section 23). Consequently the chronyd event cannot be attributed to HOST2 or treated as evidence of its effect on HOST2 clocks. This discovery does not establish the cause of the observed monotonic behavior. The public trace summary removes PIDs, CPU numbers and pointers; its original trace and collector script hashes are recorded and the originals are retained locally.

## 23. Trace PID calibration

A benign program queried `adjtimex` with zero modes and then waited; it reported Ubuntu-local PID 5910, while the isolated tracefs instance recorded that same probe as PID 6968. The trace also contained other tasks. This confirms that the tracer can report task identities outside the PID view used by the Ubuntu process listing. It does not identify where any other task ran, whether it was part of HOST2, or whether its clock calls modified HOST2. In particular, the `chronyd` entries in section 22 are not HOST2-attributed evidence and must not be used as the basis for disabling a service. The trace instance was removed; the source trace remains private because it contains pointer values. `trace-pid-calibration.json` preserves redacted entries and source hashes.

## 24. Dev Container check, first attempt

A disposable container from the locally available development image was used with no network during checks, no Docker socket, a fresh source snapshot, and a private `/var/lib/inodefence` tmpfs. The test dependencies were installed separately into a temporary directory. The first `make check` on snapshot `563531daf9065f5cdc99a0eaf2a26cdd7646816f` stopped at lint: the archived clock measurement script in this evidence bundle had nine style errors. No tests ran. The archived script was renamed from `.py` to `.py.txt` without changing its bytes; its provenance file records the new name. The raw first attempt log is retained locally. This attempt is not an experiment or a qualification result.

## 25. Dev Container check follow-up

On evidence-branch snapshot `b0ba5e0` (full source SHA and archive hash in `dev-container-check.json`), a disposable development-image container completed `make check` with exit 0: Ruff lint and format passed, Pyright had zero errors, pytest reported **3103 passed, 6 skipped**, and environment, documentation and evidence-chain checks passed. The six skips were one unavailable G1 host-local evidence input, four missing locked node-tar package tests and one missing matplotlib. They are not passes. The container had no network and no Docker socket during the checks, used a synthetic Git commit of the archived source tree, tmpfs for the runtime, 4 GiB memory and 512 PID limits; uid 1000 ran the checks after root installed the local project package in its disposable overlay. This is engineering validation of that snapshot, not validation of execution candidate `afdc720` or HOST2 qualification. No formal experiment or target campaign was run.

Two intermediate attempts are retained as failures: the first synthetic container run after the archived script rename reported 30 failed / 3073 passed / 6 skipped, with missing installed package and a `noexec` tmpfs accounting for many failures. A following bootstrap attempt stopped because `su` reset PATH and `python` was unavailable. The successful run installed the local package, enabled tmpfs execution and restored the development image's Python path. Logs, command metadata and hashes for all attempts and dependency installation are retained outside the repo; the public summary includes hashes and sanitized arguments. The check container was automatically removed; existing containers and volumes were not removed. `make check` preceded this report-only addition, so its exact source SHA is the snapshot rather than the final report commit.

## 26. Candidate and verifier test follow-up

A disposable development-image container ran `make check` on a `git archive` of execution candidate `afdc720da6eb6ae143bd4754cb39d6dd34ea8f16`. The container had no network or Docker socket, used private tmpfs for runtime, and ran tests as uid 1000 after a root bootstrap installed the local project package. A synthetic Git commit was used for Git-aware checks, so Git identity-sensitive behavior was not tested against the original commit object. The command exited 0: lint, format, Pyright, environment, documentation and evidence-chain checks passed; pytest reported **3143 passed, 6 skipped**. Skips were one unavailable G1 host-local raw evidence, four missing locked node-tar module tests and one missing matplotlib. The container was removed after completion.

Separately, `tests/test_host_collection.py` and `tests/test_verify_host_freeze.py` at tool SHA `6dddb7568ff3101a30eeba93cdabac5fccdfd369` ran with synthetic fixtures in WSL: **26 passed**, exit 0. These tests validate selected verifier behaviors and do not qualify a host. Both local checkouts remained clean. At this check, GitHub API still reported #316 and #325 open at those respective SHAs. Neither result grants a smoke, H1 rerun, EXP run, or freeze approval; target image, engine, memory, clock and restart issues remain. Command metadata, archive hash and original log hashes are in `candidate-and-tools-check.json`; complete logs remain private.
