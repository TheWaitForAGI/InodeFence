# HOST2 Qualification Re-measurement Report (2026-11-11)

## 1. Executive Summary

**HOST2 NOT QUALIFIED.** Re-measured on 2026-11-11 14:06–14:20 KST by the W2 session (IF-ORCH-20261111 instruction). Memory now **PASS** (the WSL 20 GB cap is already in effect, so no `wsl --shutdown` was needed). These remain **FAIL**: Engine contract (29.9.3 vs 29.8.0), target/controller/helper images absent, clock (`CLOCK_MONOTONIC` runs about 4.7% slow against Windows Stopwatch over 60 s and 600 s brackets) and restart protection (Windows Update restarted the host automatically at 2026-11-11 10:02 KST, and updates are not paused). No smoke, benchmark, experiment, image build, image load, prune or deletion was performed. Environment changes made in this session: **none** (section 9). Raw probe outputs are redacted copies. Hostname, account names, user paths, Tailscale/LAN addresses and MACs are replaced with `<...>`.

The 11/10 report's repository path `/home/linux/projects/InodeFence` does not exist on this host. The actual checkout is `~/projects/InodeFence` (user redacted). The CPU (Intel Core Ultra 7 270K Plus, 24C/24T) and RAM (32 GB) match the HOST2 description.

## 2. PASS / FAIL / UNKNOWN Matrix

| Item | Result | Measured value (evidence file) |
| --- | --- | --- |
| WSL memory | **PASS** | MemTotal 20,478,924 KiB (19.53 GiB), available 19,356,119,040 B (18.03 GiB) ≥ 15 GiB. `.wslconfig` `memory=20GB` is in effect. WSL started 13:29 KST (timesyncd log), Windows boot 10:03 KST (`wsl_host.txt`) |
| Docker CPU / memory | **PASS** (capacity) | `docker info`: CPUs 24, Total Memory 19.53 GiB, cgroup v2, cgroupfs driver, overlayfs/containerd snapshotter. Workload headroom is unverified (`docker.txt`) |
| Disk | **PASS** (capacity) | WSL ext4 `/` 944 GB avail. Windows C: 86.3 GB free of 930.5 GB (91% used); the WSL/Docker VHDX backing is on C:, so the effective limit is about 86 GB (`wsl_host.txt`, `windows.txt`) |
| Image | **FAIL** | `inodefence-node-tar-effect:*`, controller and helper are all absent. Only 8 unrelated images are present (`docker.txt`) |
| Engine | **FAIL** (host property) | Docker Desktop 4.99.0 (245822), CLI/Engine 29.9.3, context `default`. Differs from contract 29.8.0. Not changed (`docker.txt`) |
| WSL version | record | WSL 3.0.5.0, kernel 6.18.58.1-microsoft-standard-WSL2, Windows 10.0.26200.9974. Same as after the 11/10 update |
| Clock | **FAIL** | MONOTONIC runs −4.68% (60 s) and −5.04% (600 s, ±0.3 ppm) against Stopwatch. MONOTONIC_RAW agrees within 0.1 ppm. `adjtimex` tick went from 9559 to 9093 during the measurement (nominal 10000) |
| Restart protection | **FAIL** | Event 1074 at 2026-11-11 10:02:30 KST: TrustedInstaller/SYSTEM, "Operating system: Upgrade (Planned)" restart. Update not paused, no AU policy (§6) |
| Sleep / hibernate | PASS | Balanced plan, AC sleep = 0 and AC hibernate = 0 (never) |
| Leftover resources | **PASS** (no filter hits) | 4 stopped containers and 3 volumes, none matching `inodefence-` (container) or `inodefence-local-` (volume) (§7) |
| Other load | **UNKNOWN** | At this instant Windows CPU was 3% and WSL load average 0.30. Many user apps are running or auto-start (Discord, OP.GG, INZONEHub, KakaoTalk, Steam, Riot, Battle.net, Overwolf, MYBOX, etc.). Exclusivity over 24 h is not established |
| Pending reboot | negative (limited) | CBS/WU RebootRequired/PendingFileRename all False (14:08 KST). This does not guarantee there will be no reboot |
| Python environment | PASS | No `.venv`. The dedicated venv `~/.local/share/inodefence/host2-dev-venv` (Python 3.12.3) passes `python scripts/check_dev_env.py` with rc=0 (`pyenv.txt`) |

## 3. Commands and timing

Each raw file records the command, the start time (`# at`) and the exit code (`# rc=`). The Windows probe script is `windows-probe.ps1.txt` (non-elevated, `IsInRole(Administrator)=False`). Clock: `clockbracket.py.txt`, adjtimex read-only query: `adjtimex_read.py.txt` (ctypes `adjtimex` with modes=0, `adjtimex` binary not installed).

## 4. Clock

Method: a persistent PowerShell process returns `Stopwatch.GetTimestamp()` on request. Each request is bracketed by WSL `CLOCK_MONOTONIC`/`CLOCK_MONOTONIC_RAW` reads, and the narrowest of 15 repetitions is used. Stopwatch frequency is 10 MHz.

| Interval | ΔStopwatch (s) | ΔMONOTONIC (s) | ΔMONOTONIC_RAW (s) | MONO rate | RAW rate | Uncertainty |
| --- | --- | --- | --- | --- | --- | --- |
| 60 s (14:06:40 KST) | 62.955480 | 60.006838 | 62.955483 | −46,837 ppm | +0.04 ppm | ±4 ppm |
| 600 s (14:06:39–14:17:10 KST) | 631.833016 | 600.007130 | 631.832982 | −50,371 ppm | −0.05 ppm | ±0.3 ppm |

`adjtimex`: at 14:06:24 tick=9559 µs and freq=−31.80 ppm; at 14:17:10 tick=9093 and freq=+33.51 ppm; at 14:17:17 tick=9095 (11/10: 9662–9686). status=0x2000, clocksource=tsc. Over this session the tick drops monotonically, and it is lower than on 11/10. Over the same period systemd-timesyncd reported Offset +1.78 s, poll 32 s, delay 245 ms and jitter 115 ms (`clock_post.txt`). Windows UTC and WSL `CLOCK_REALTIME` agree within the bracket (about 0.47 s), so wall time is being corrected separately. Hypothesis (not verified): Hyper-V implicit time sync steps wall time while timesyncd tries to slew away the remaining offset, keeping the tick low, and MONOTONIC follows that slew. On 11/10, a test that disabled timesyncd and reset the tick was overwritten (previous report §20). Interpretation: the kernel-adjusted clocks (`CLOCK_MONOTONIC`, and with it `sleep`, timerfd and the watchdog) run about 4.7% slower than Windows real time, while the hardware-based RAW clock is accurate. A 24-hour run would show about 67 minutes less on MONOTONIC. The cause (tick adjustment from Hyper-V/timesyncd interaction) is unconfirmed, and nothing was adjusted.

## 5. Image transfer path (assuming one tar of about 2 GB)

| Path | Status |
| --- | --- |
| Google Drive desktop | **Not available.** No Drive File Stream install, no DriveFS folder, no `GoogleDriveFS` process, no G: drive. Account UNKNOWN |
| Same-LAN ssh/SMB | **UNKNOWN.** HOST2 is on wired Ethernet `<lan-ip>/24` with the Windows network profile set to **Public**. ARP shows only the router. HOST1's LAN address is unknown. Only admin shares (C$, ADMIN$, IPC$). Windows sshd is not installed |
| Tailscale | **Available (route unconfirmed).** HOST2 is on the tailnet. One Linux peer (`<peer-b>`, owned by a different tailnet account) responds to `tailscale ping`, but only through the DERP relay (Tokyo, about 67 ms; no direct connection), and TCP/22 answers `OpenSSH_9.6p1 Ubuntu-3ubuntu13.2`. Whether this is HOST1 is unknown. There is no known_hosts entry and no ssh config. WSL has ssh/scp/rsync and an ed25519 key |
| NAVER MYBOX | Installed and running (cloud sync client). Usable if HOST1 can share an account or link |
| Other | USB/external drive: not enumerated at the moment (11/10 also had no external SSD) |

Recommendation: if `<peer-b>` is HOST1, use `rsync --partial` or `scp` over Tailscale, then compare `sha256sum`, then `docker load`, then check the image id. A DERP relay can make a 2 GB transfer slow. A shared cloud or USB drive is the alternative.

## 6. Restart protection

| Item | Current value | Required change / command | Applied |
| --- | --- | --- | --- |
| Windows Update pause | Not paused (no `Pause*` value). KB5132061 installed 11/11, then automatic restart at 10:02 | Settings > Windows Update > Pause (up to 5 weeks; pause until after 11/26). Equivalent registry under HKLM `...\WindowsUpdate\UX\Settings` `PauseUpdatesExpiryTime` etc. requires admin | **Not applied** (no admin; needs operator GUI action) |
| Active hours | 16:00–05:00 (the 10:02 restart was outside this window) | Active hours can be at most 18 h, so they cannot protect a 24 h run. Pausing is required | No |
| Automatic restart policy | No AU policy (`HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU` absent) | (admin, Jiwoong to decide) `reg add HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f`. Alternatively `AUOptions=2` (notify only) | No (proposal only) |
| Sleep / hibernate (AC) | 0 / 0 (never). Display off AC 0 | No change needed | — |
| WSL idle shutdown | `.wslconfig` has only `memory=20GB`. While Docker Desktop runs, the `docker-desktop` distro keeps the VM alive | (optional) add `vmIdleTimeout=-1` under `[wsl2]`. Takes effect only after a WSL restart, so do it together with the next coordinated restart | No |
| Docker Desktop updates | `settings-store.json` has no update-related key (default value UNKNOWN). The Run key auto-starts Docker Desktop, while `AutoStart:false` | Docker Desktop Settings > Software updates > turn off "Automatically check for updates"/"Always download updates" (GUI; key name unconfirmed, so no direct file edit) | No |
| WSL updates | WSL 3.0.5.0. Updates come through the Store/Windows Update path. No WindowsStore policy | Covered by the Windows Update pause. (admin) `HKLM\SOFTWARE\Policies\Microsoft\WindowsStore AutoDownload=2` | No |

## 7. Existing containers and volumes (list only, nothing deleted)

| Type | Name | Created (KST) | Image | Note | Filter hit |
| --- | --- | --- | --- | --- | --- |
| container | agitated_aryabhata | 2026-10-24 14:09 | vsc-inodefence-…-uid | InodeFence devcontainer, Exited (0) | No |
| container | gracious_margulis | 2026-10-05 19:50 | vsc-thewaitforagi-…-uid | different project devcontainer | No |
| container | hspase-fast | 2026-06-07 16:28 | sagemath/sagemath | unrelated | No |
| container | webgoat | 2026-06-03 00:12 | ubuntu | unrelated, ports 8080/9090 | No |
| volume | inodefence-codex | — | local | devcontainer mount | No (`inodefence-local-` prefix does not match) |
| volume | inodefence-runtime | — | local | devcontainer runtime | No |
| volume | vscode | — | local | VS Code | No |

Full labels are in `docker.txt`. `docker system df`: containers 8.7 GB, volumes 5.7 GB, build cache 4.5 GB.

## 8. Repository and execution worktree

`git fetch origin` rc=0; `origin/main` = `bb87e69f9f3911c0067be1a727aa043858d56849` (matches). The evidence branch is `claude/p0-332-host2-qualification`, branched from `origin/codex/host2-validation-20261110` (`9c5c981`); main is an ancestor. Planned execution-candidate worktree location: `~/inodefence-host2-20261111/execution` (detached, not yet created; created with `git worktree add --detach <path> <SHA>` once the SHA arrives). The existing main checkout is on `minchan/p0-2-observation-capture` and is left untouched.

## 9. Environment changes

None. The WSL memory cap was already in effect before measurement, so `wsl --shutdown` was not run. Windows Update pause, Docker Desktop update settings and `.wslconfig` were not changed (no admin rights / needs GUI / requires a WSL restart). The only file created on the Windows side is the temporary probe script `%LOCALAPPDATA%\Temp\if_host2_probe.ps1` (same content as `windows-probe.ps1.txt`).

## 11. Clock intervention test (ORCH-approved, executed with the user's permission to use `wsl.exe -u root`)

Criteria fixed in advance (ORCH): |MONOTONIC − Stopwatch| ≤ 500 ppm, tick=10000 held for 30 minutes, and REALTIME−Windows UTC drift ≤ 0.5 s → PASS. Otherwise, restore.

| Time (KST) | Action / observation | Evidence |
| --- | --- | --- |
| 14:23:14 | Before: tick 9367, freq −46.7 ppm, timesyncd active/enabled, timesyncd Offset +1.82 s. **Windows W32Time Stopped (Manual)**, `w32tm /query /status` → 0x80070426 (service not started) | `clock_intervention_pre.txt` |
| 14:24:52 | `wsl.exe -u root -d Ubuntu-24.04 -- systemctl stop systemd-timesyncd` rc=0 (enabled kept). Just before: tick 9093, freq +33.5 → `adjtimex` ADJ_TICK=10000 and ADJ_FREQUENCY=0, rc=0, re-read matches | `clock_intervention_apply.txt`, `adjtimex_set.py.txt` |
| 14:25:09–14:27:12 | **After timesyncd stopped, something still rewrote tick/freq**: tick swung 9474 → 9882 → 9093 → 10747 → 10833 → … → 10000. No new user process appeared at the change times (it looks like an in-kernel or WSL-side time sync agent; not identified) | `clock_intervention_30min.txt` |
| 14:27:12–14:55:16 | tick=10000 held (169 samples, every 10 s). freq is still rewritten every 10 s within −9.2 to +7.2 ppm | same |
| 14:25:07–14:35:11 | 600 s bracket ①: MONO −4,116 ppm, RAW −0.05 ppm, REALTIME +455 ppm (±0.4 ppm); includes the unstable stretch | `clock_intervention_600s.txt` |
| 14:35:24–14:45:25 | 600 s bracket ② (stable stretch, extra observation): MONO −0.02 ppm, RAW −0.05 ppm, REALTIME −0.02 ppm (±0.3 ppm) | `clock_intervention_600s_b.txt` |
| 14:25–14:55 | REALTIME−Windows UTC: −0.534 → −0.187 → −0.204 → −0.188 → −0.189 → −0.180 → −0.189 s (bracket about 0.48 s) | `clock_intervention_30min.txt` |

**Verdict under the fixed criteria: FAIL.** The 600 s ① MONO reading of −4,116 ppm exceeds 500 ppm, and tick did not hold 10000 for the first 2 minutes. The REALTIME criterion was met (drift 0.35 s). Observation: after the transient settled, MONO ran −0.02 ppm against Stopwatch for 28 minutes. This is about 2,500 times better than before the intervention (−50,371 ppm). The criteria were not changed after the fact.

Current state (14:55): timesyncd is **inactive / enabled**. The newer ORCH instruction (B: "stopped state only, permanent disable needs Jiwoong's approval") takes precedence, so it was left stopped and **not disabled**. A WSL restart brings timesyncd back. Restore: `wsl.exe -u root -d Ubuntu-24.04 -- systemctl start systemd-timesyncd`. Permanent application (`systemctl disable systemd-timesyncd`) is pending approval. Windows W32Time being stopped means the Windows clock itself is not NTP-synchronized; this is a separate issue (it affects absolute time, not rate).

## 12. Restart protection: commands for the owner (administrator PowerShell, run by the HOST2 owner)

Record before and after with the same read commands (`R*`). Do not permanently disable the Windows Update service and do not remove security features.

| # | Item | Read (before/after) | Apply (owner) | Revert after the main run (after 11/26) |
| --- | --- | --- | --- | --- |
| 1 | Pause updates | R1: `Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings' \| fl Pause*,ActiveHours*` | GUI: Settings > Windows Update > "Pause updates" > choose the longest period (up to 5 weeks, about 12/16). Record the expiry date shown on screen | Same screen > "Resume updates" |
| 2 | Automatic restart policy | R2: `Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU' -EA SilentlyContinue \| fl *` | `reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f` and `reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v AUOptions /t REG_DWORD /d 2 /f` (2 = notify only before download/install) | `reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /f` and `reg delete ... /v AUOptions /f` (the AU key did not exist before) |
| 3 | Active hours | R1 (currently 16–05) | No change (an 18-hour cap cannot protect 24 hours). Rely on #1 and #2 | — |
| 4 | Sleep / hibernate | R4: `powercfg /query SCHEME_CURRENT SUB_SLEEP` | Already AC 0/0. To make sure: `powercfg /change standby-timeout-ac 0` and `powercfg /change hibernate-timeout-ac 0` | No revert needed (same as current) |
| 5 | Pending reboot | R5: `Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'`, `Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending'`, `Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -Name PendingFileRenameOperations -EA SilentlyContinue` | If any is True, reboot once before the main run, then check again | — |
| 6 | Scheduled restart tasks | R6: `Get-ScheduledTask -TaskPath '\Microsoft\Windows\UpdateOrchestrator\' \| Get-ScheduledTaskInfo \| ft TaskName,NextRunTime,LastRunTime` (requires admin; empty when non-admin) | No change. Record only | — |
| 7 | Background apps | R7: `Get-CimInstance Win32_StartupCommand \| ft Name,Command`, `Get-Process \| sort CPU -desc \| select -first 20` | Before the run, quit and turn off startup in Settings > Apps > Startup: Discord, Steam, Riot Client, Battle.net, Overwolf, OP.GG, KakaoTalk, LG HUB, INZONE Hub, Samsung Magician, Notion, Adobe Acrobat Synchronizer, NAVER MYBOX, Edge auto-launch. **Keep Docker Desktop and Tailscale** | Turn each startup entry back on |
| 8 | Evidence | Save R1–R7 before and after as `Start-Transcript` output, and also `systeminfo` and `Get-ComputerInfo -Property OsName,OsBuildNumber,WindowsUpdate*` | — | — |

Interpretation: when all of the above are applied, the result is "configuration compliant". "Restart prevention effective" stays UNKNOWN until an observed automatic restart is actually withheld (for example, a restart deferred while an update is pending). A pause has an expiry, so recheck the expiry date before the main run (11/18).

Additional startup entries (14:45, `restart-protection-before.txt`): AnyDesk (remote access), Riot Vanguard (HKLM Run, kernel anti-cheat), McAfee Security Scan Plus, VMware tray. Add these to the exit/startup-disable review in item 7. In the 14:45 before-state, Pause and AU policy are absent, AC sleep/hibernate are 0, the three pending-reboot flags are False, and the UpdateOrchestrator task list is empty for a non-admin user (UNKNOWN).

## 13. Engine mismatch: investigation of a return to 4.91.0 (read-only, not applied)

Summary of web research (sources in parentheses):
- 4.91.0 = build 239619, Engine v29.8.0. Installer: `https://desktop.docker.com/win/main/amd64/239619/Docker%20Desktop%20Installer.exe` ([release notes](https://docs.docker.com/desktop/release-notes/)). **Docker publishes no SHA-256.** If HOST1's installer is still available, compare it with `Get-FileHash`; otherwise there is no reference hash (UNKNOWN). Only versions less than 6 months old are offered for download.
- WSL: the documented minimum is 2.1.5 and no maximum is documented ([install](https://docs.docker.com/desktop/setup/install/windows-install/)). WSL 3.0.x-related fixes appear in 4.95 and 4.98. Whether 4.91.0 works properly on WSL 3.0.5 is **UNKNOWN**. Security fixes from 4.94–4.98 would be lost (CVE IDs as reported by the research summary; recheck against the release notes before applying).
- Downgrade: an older version cannot be installed over a newer one; uninstall first ([for-win#14177](https://github.com/docker/for-win/issues/14177)). **Uninstalling deletes local images, containers and volumes** ([uninstall](https://docs.docker.com/desktop/uninstall/)). Back up first ([backup-and-restore](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/)). Reusing a data disk written by containerd v2.4.2 under an older containerd is UNKNOWN; recommended route is restoring with `docker save` and a volume backup. Whether settings are preserved is UNKNOWN.
- Blocking automatic updates: Settings > Software updates ("Automatically check for updates" is on by default, "Always download updates" is off by default; [settings](https://docs.docker.com/desktop/settings-and-maintenance/settings/)). The `settings-store.json` key names are UNKNOWN (find them by checking the file after changing the GUI setting). Enforcing via `admin-settings.json` `disableUpdate` requires Docker Business.
- Estimated time (not documented): backup, uninstall, reboot, install, setup, restore, about 45–120 minutes. Requires one Windows reboot.

## 14. Image transfer preparation

`~/.ssh/inodefence_transfer` (ed25519, no passphrase, 0600; for unattended transfer, relying on HOST1-side `rrsync -ro` restriction) was created at 14:38 KST. Public key fingerprint `SHA256:X6GBdnJKknPjFyGYVge4yfn6pXGzk1avO/P6jy7UwrA`. rsync 3.2.7 present, zstd absent (uncompressed tar, so no problem). No transfer attempted (HOST1 access not yet opened). Expected values received from ORCH: controller-local.tar `4d2570f4…076d` 309,895,168 B, helper-local.tar `c9b36013…8d7d` 45,441,536 B, node-tar-effect-7.5.2.tar `ebd80de8…0e61` 54,267,392 B.

Native docker (read-only, `native_docker.txt`): no docker-ce/containerd packages, no units, no apt docker repository registered. `/usr/bin/docker` is the Docker Desktop WSL integration CLI (`IntegratedWslDistros=[Ubuntu-24.04]`).

## 15. HOST2 qualification checklist (as of 14:55 KST; HOST1 PASS is not carried over)

| Item | Result | Basis |
| --- | --- | --- |
| Memory | PASS | §2 |
| CPU (Docker) | PASS (capacity) | §2 |
| Disk | PASS (capacity) | §2, C: 86 GB |
| Images | FAIL | not yet transferred (§14) |
| Engine | FAIL | 29.9.3 ≠ 29.8.0, §13 pending decision |
| Clock | FAIL (fixed criteria) / stable phase observed | §11; permanent change pending approval |
| Restart protection | FAIL | §6, §12 not applied by the owner; even once applied, "configuration compliant, effect not observed" |
| Leftover resources | PASS | §7 |
| Load | UNKNOWN | §12 item 7 |
| Execution SHA | UNKNOWN | not yet delivered; worktree location `~/inodefence-host2-20261111/execution` |
| smoke | NOT RUN | prohibited |

## 16. Evidence manifest

`SHA256SUMS` covers every public file in this directory. Raw probe files are redacted copies. CRLF was converted to LF, and trailing whitespace and blank lines at end of file were removed. The original unredacted outputs are kept only in the session-local scratch area.
