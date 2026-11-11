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
| Clock | FAIL (fixed criteria) / stable phase observed | §11; permanent change pending approval. **Update 17:22: confirmation test PASS (§23)**; W32Time sync pending |
| Restart protection | FAIL | §6, §12 not applied by the owner; even once applied, "configuration compliant, effect not observed" |
| Leftover resources | PASS | §7 |
| Load | UNKNOWN | §12 item 7 |
| Execution SHA | UNKNOWN | not yet delivered; worktree location `~/inodefence-host2-20261111/execution` |
| smoke | NOT RUN | prohibited |

## 17. Changes after 14:55, and prerequisites (as of 15:30 KST)

- 15:23:36 `wsl.exe -u root -d Ubuntu-24.04 -- systemctl disable systemd-timesyncd`, rc=0. Before: inactive/enabled; after: inactive/disabled. Basis: the HOST2 user's message "다 승인" ("everything approved"), which approved all pending items. ORCH had treated permanent disable as an approval item, so this is reported to ORCH. The running state is unchanged (it was already stopped), so the confirmation test is not affected (ORCH accepted that the test conditions were maintained; the state is left as is, neither reverted nor changed further). Revert: `wsl.exe -u root -d Ubuntu-24.04 -- systemctl enable --now systemd-timesyncd` (`timesyncd_disable.txt`).
- 15:18 the elevated restart-protection script was started via `Start-Process -Verb RunAs`. The UAC prompt is waiting for the owner's click, so it is **not applied yet**. Contents: Pause 35 days (UX Settings Pause* values), AU NoAutoRebootWithLoggedOnUsers=1 and AUOptions=2, powercfg AC 0/0, before/after reads, R6 admin query, systeminfo.
- W32Time start/resync: **not applied.** A clock step (about 1.36 s) during the confirmation test (ending about 17:20) would invalidate the REALTIME−WinUTC criterion. Since then Jiwoong decided environment changes remain prohibited, so it is held. Owner commands (admin): `Start-Service W32Time; w32tm /resync /force; Set-Service W32Time -StartupType Automatic`. Revert: `Set-Service W32Time -StartupType Manual; Stop-Service W32Time`.
- Engine: Jiwoong conditionally approved option B. Keep 4.99.0 / 29.9.3 and do not change versions until the main run ends. Docker Desktop automatic updates: `settings-store.json` has no update or Resource Saver key (defaults apply; the GUI value has not been confirmed by the owner).

Scope note (ORCH): the owner's blanket approval covers HOST2 machine settings. Changes that touch experiment conditions (Docker, Engine or WSL versions; context, storage, network, `.wslconfig`; image rebuild or deletion; smoke or experiment runs) are reported to ORCH before being applied.

| Prerequisite | Status | Waiting on |
| --- | --- | --- |
| Load 4 images and match Ids | Not started | Owner accepting the Tailscale share invite (HOST1 not visible at 15:29) |
| Restart protection applied | Not applied | Owner clicking "Yes" in UAC. Verdict will be "configuration compliant / effect not observed". Recheck the pause expiry on 11/18. After the main run, revert per §12 |
| Clock confirmation test PASS | **PASS** 17:22 (§23) | After a WSL restart, recheck the tick and timesyncd state. Next: W32Time sync (owner) → criteria (a)(b)(c) |
| Clean up user apps | Not done | Owner's call (list in §12 item 7, AnyDesk is the owner's decision) |
| Docker Desktop auto-update off | Unconfirmed | Owner turning it off in the GUI and recording the value |
| Execution SHA checkout | Not done | ORCH delivering the SHA (`~/inodefence-host2-20261111/execution`) |
| Volume in-use deletion refusal check | Not done | After transfer and load (W2) |
| Launcher smoke 6 cells / qualification 12 campaigns | Prohibited | ORCH delivering the SHA and commands |

## 18. Evidence manifest

`SHA256SUMS` covers every public file in this directory. Raw probe files are redacted copies. CRLF was converted to LF, and trailing whitespace and blank lines at end of file were removed. The original unredacted outputs are kept only in the session-local scratch area.

## 19. Cross-check against main `c159406` `experiments/configs/host-qualification-v1.md` §4 preflight and §12 checklist (read-only, 17:01 KST)

Values measured 2026-11-11 17:01 KST with read-only commands (`docker version`, `docker context show`, `docker info`, `docker images`, `docker ps -a`, `docker volume ls`, `.wslconfig`, `wsl.exe --version`, `uptime -s`, `/proc/loadavg`, `free`, `df`). Nothing was changed.

### 19.1 §4 preflight

| §4 item | HOST2 expected | HOST2 measured now | Met now? | Waiting on / who |
| --- | --- | --- | --- | --- |
| Execution SHA clean, detached worktree, venv python, no `uv.lock` | the candidate SHA ORCH sends | not delivered. venv `~/.local/share/inodefence/host2-dev-venv` (Python 3.12.3) ready | No | ORCH sends the SHA → W2 creates `~/inodefence-host2-20261111/execution` |
| Target image id | `sha256:22c8734f…6f3dbb` (node-tar 7.5.2) | absent | No | owner accepts the Tailscale invite → W2 transfers, loads, compares ids (§14) |
| Controller image id | `sha256:d44900e1…91d7a4` | absent | No | same |
| Helper image id | `sha256:9b9dd606…81cc27` | absent | No | same |
| Holdout image (EXP-2) | `sha256:f5d3e9a9…080421` (node-tar 7.4.4) | absent | No | same (not a §4 item, but part of the same transfer) |
| Engine `Server.Version` | 29.9.3 (option B) | 29.9.3, client 29.9.3, context `default`, daemon Docker Desktop (`OperatingSystem=Docker Desktop`) | **Yes** | keep unchanged until the main run ends (owner turns off Desktop auto-update, §21) |
| Shared-path hash, 16 files | equal to HOST1 at the execution SHA | not computed (no execution SHA). A preview at the integration head is in §22 | No | execution SHA (ORCH) |
| Running containers 0 | 0 | 0 running. `inodefence-` containers: 0 | **Yes** | — |
| Leftover volumes 0 | 0 | code filter `name=inodefence-local-` (`scripts/launcher_guards.py:162` @ `129324d`): 0. **However**, the §4 text says "`inodefence-` prefix containers and volumes". Under that wording the two dev-container volumes `inodefence-codex` and `inodefence-runtime` match | Yes (code) / **No (text)** | ORCH/W3 decide whether the §4 wording or the code filter governs. Not deleted (deletion prohibited) |
| Disk ≥ 20 GB | ≥ 20 GB | WSL `/` 944 GB free. C: (holds the VHDX) about 87 GB free | **Yes** | recheck after the image load |
| Available memory ≥ 15 GiB | ≥ 15 GiB | 18 GiB available (WSL total 19.5 GiB) | **Yes** | — |
| load < 3 and < 25% of cores (6) | < 3 | 0.22 (24 cores) | **Yes (instant)** | over 24 h: owner closes background apps (§21) |
| Restart protection capture | captured at start | elevated script waiting for UAC since 15:18 | No | owner clicks "Yes" (§21) |
| Boot time (start and end) | recorded | Windows boot 2026-11-11 10:03 KST, WSL start 13:31:40 KST | recordable | record again at start and end of the qualification run |
| Docker Desktop version | 4.99.0 (245822) | 4.99.0 (245822) (§2) | **Yes** | auto-update off (owner) |
| WSL version | 3.0.5.0 | WSL 3.0.5.0, kernel 6.18.58.1-1, WSLg 1.0.79 | **Yes** | — |
| `.wslconfig` | memory and processor caps recorded | `[wsl2] memory=20GB`; no `processors` key (24 visible) | recordable | — |
| Realtime sync state | timesyncd off + W32Time synced to NTP (Jiwoong) | timesyncd inactive/disabled, tick 10000. W32Time not started | partly | confirmation verdict (W2, about 17:22) → owner starts/resyncs W32Time → W2 checks criteria (a)(b)(c) |
| Cross-host realtime difference (record only) | SNTP offset difference measured on both hosts | HOST2 side measured: +1.572 s (time.windows.com), +1.575 s (pool.ntp.org) (§20) | HOST2 half done | HOST1 measures with the same servers (ORCH/HOST1). Remeasure after W32Time sync |
| jobs | `host.HOST2.jobs = 2` | registration file check: §22 | see §22 | — |

### 19.2 §12 pre-run checklist (for HOST2)

| §12 item | Status | Who |
| --- | --- | --- |
| D047 and the qualification file on main; "provisional" values fixed in a commit | D047 merged (`c159406`). Whether the provisional values are fixed: UNKNOWN to W2 | W4 review → Jiwoong |
| Candidate SHA with #340, #335, #334, #336 wiring, `replicate-v1`, 3-image-id recording; independent verification PASS | not delivered (integration head under fixes after the W4 FAIL) | W1/W3 → W4 → ORCH |
| Stage 0 smoke PASS (HOST2) | not run (prohibited) | needs SHA, images and Jiwoong approval; W2 runs it |
| All §4 preflight items, record path in LOG | see 19.1 | W2 records; owner items in §21 |
| Verdict tool and cross-host comparator at that SHA | not present per §13 | W3 |
| Cell env key/value check, `observer_integrity_policy = invalid-continue` | not checked (no SHA) | W2 at the execution SHA, or W3 |
| Exposure ledger plan line, seed-collision machine check | not done | ORCH/W3 |
| Notify other sessions: sealing, no other docker or `make check` | not done | ORCH |
| Jiwoong approval per host and stage | not given | Jiwoong |

## 20. SNTP clock offset (first real-network run of the integration script, 17:01 KST)

Script `scripts/measure_clock_offset.py` from `origin/claude/p0-331-exp3-control-integration` @ `129324d` (file sha256 `4d5ccf5e…7328af5`), extracted to the session scratch area and run with `python3 -I` inside WSL. Usage (`--help`): `--server SERVER --host-id {HOST1,HOST2} [--samples SAMPLES] --out OUT`. Both runs rc=0. The clock was not touched.

| Server | Samples ok / taken | Chosen | offset_s | RTT_s | uncertainty_s (= RTT/2) | measured_at (UTC) |
| --- | --- | --- | --- | --- | --- | --- |
| time.windows.com | **3 / 5** (samples 1 and 2: `TimeoutError: timed out`) | index 0 | +1.5723 | 0.0138 | 0.0069 | 08:01:15.03 |
| pool.ntp.org | 5 / 5 | index 1 | +1.5746 | 0.0177 | 0.0089 | 08:01:15.96 |

- Sign (script docstring): `offset_s` = server − this host, so the **WSL REALTIME clock is about 1.57 s behind NTP**. The two servers agree within 2.3 ms. With WSL REALTIME − Windows UTC ≈ −0.19 s (tickmon, same hour), Windows is about 1.38 s behind NTP. This matches the step of about 1.36 s expected when W32Time is synced.
- Format: per-host file `{schema: inodefence-clock-offset-v1, host_id, server, method: sntp-v1, samples[5], chosen{index, offset_s, rtt_s}, offset_s, uncertainty_s, measured_at}`. The design's `{method, samples, chosen, diff_s, uncertainty_s, measured_at}` belongs to the two-host combined record. `diff_s` comes from the script's `combine` step, which this one-host run cannot produce. Failed samples stay in `samples` with an `error` field and are excluded from `chosen`.
- Observation: 2 of 5 time.windows.com queries timed out. The script still chose a sample, but HOST1 should use the same server pair. pool.ntp.org answered 5/5 here.
- Evidence: `sntp_offset_time_windows_com.txt`, `sntp_offset_pool_ntp_org.txt`.

## 21. Owner one-pass task sheet (HOST2 owner, in this order)

| # | Task | How | Expected time | Why it is needed |
| --- | --- | --- | --- | --- |
| 1 | Accept the Tailscale share invite | Open the invite link (email or Tailscale admin) while signed in to the HOST2 tailnet account, then accept. W2 then checks that HOST1 `100.69.212.56` appears | 2 min | The three experiment images and the holdout image come from HOST1 through this share, and W2 checks they keep the same ids. No rebuild is allowed |
| 2 | Approve the restart-protection UAC prompt | Click "Yes" on the UAC window that has been open since 15:18. If it closed, tell W2 and it relaunches it | 1 min | Pauses Windows Update for 35 days and blocks automatic restarts while logged on. Windows restarted HOST2 automatically at 10:02 today, and one restart ends a 24 h unattended run |
| 3 | Turn off Docker Desktop auto-update and report Resource Saver | Docker Desktop > Settings > Software updates: turn off "Automatically check/download updates". Settings > Resources > Advanced: tell W2 the "Resource Saver" state and its timeout. Change nothing else | 3 min | Engine 29.9.3 and Desktop 4.99.0 must stay unchanged from the qualification start to the end of the main run (§11 ⑤). Resource Saver can stop the engine VM when idle |
| 4 | Close background programs during measurement | Quit, and turn off at startup: Discord, Steam, Riot Client, Battle.net, Overwolf, OP.GG, KakaoTalk, LG HUB, INZONE Hub, Samsung Magician, Notion, Adobe Acrobat Synchronizer, NAVER MYBOX, Edge auto-launch (AnyDesk is the owner's decision). **Keep Docker Desktop and Tailscale running** | 5–10 min | The load criterion (< 3) must hold for 24 h. Game launchers and updaters cause CPU and disk spikes |
| 5 | (After W2 reports the clock verdict) Start W32Time and resync | Admin PowerShell: `Start-Service W32Time; w32tm /resync /force; Set-Service W32Time -StartupType Automatic` (or run `if_host2_w32time.ps1` when W2 asks). Revert: `Set-Service W32Time -StartupType Manual; Stop-Service W32Time` | 2 min, plus a 30-minute check by W2 | Windows is about 1.4 s behind NTP (§20). Jiwoong approved syncing Windows to NTP with WSL timesyncd off. W2 then checks the (a)(b)(c) criteria |

## 22. Code portability (docker-free tests) and registration dry-run (17:22–17:24 KST)

Separate detached worktree `~/inodefence-host2-20261111/check-129324d` at the integration head `origin/claude/p0-331-exp3-control-integration` = `129324de3841e56b81fe7d22e81d41fb856ead64` (clean). **This is for checking only and is not an execution candidate.** Kernel `6.18.58.1-microsoft-standard-WSL2`, WSL 3.0.5.0, Python 3.12.3 (venv `~/.local/share/inodefence/host2-dev-venv`). Docker container count was 4 before and after (unchanged), and `git status` stayed clean afterwards.

### 22.1 Tests

`python -m pytest tests/test_start_gate.py tests/test_h1_incomplete_evidence.py tests/test_run_exp0.py tests/test_two_host_split.py tests/test_stall_recovery.py tests/test_host_qualification_assignment.py tests/test_run_exp0_host_guards.py tests/test_qualify_host.py tests/test_launcher_guards.py -q -p no:cacheprovider`: all 9 files present, **293 passed, 0 failed, 0 skipped, 7.0 s**, rc=0. This includes the start gate (flock, fd inheritance, process termination) on the HOST2 kernel. pytest's `pythonpath = ["src"]` made `inodefence` import from the worktree (checked) (`portability_pytest.txt`).

### 22.2 Dry-run of `run-exp0-eng-smoke-v1.md` and `host-qualification-v1-run.md` with `--host-id HOST2 --jobs 2 --skip-build --dry-run`

| Run | Result |
| --- | --- |
| venv python, as in the registration files' procedure | **rc=1 ImportError**: `No module named 'inodefence.evaluation.cell_completeness'`. The venv's `inodefence-host2.pth` points to the main checkout `~/projects/InodeFence/src` (an older branch), not to the worktree, so `python -m scripts.run_exp0` loads stale library code. **Finding:** with this venv, execution from a detached worktree needs `PYTHONPATH=src` (or a `.pth` that points to the execution worktree). Otherwise the wrong code runs or fails. Nothing was changed. The fix is to be decided before the execution SHA (ORCH) |
| `PYTHONPATH=src`, files as committed | both rc=2 `preregistration unusable: engine_sha must be a 40-hex git commit`. **This is the intended refusal** (`TBD-FREEZE` is still in place) |
| `PYTHONPATH=src`, a **scratch test copy** with TBD values filled (engine_sha = 129324d, ledger sha from the worktree file, deadline +7 d, HOST1 29.8.0, HOST2 29.9.3). For parser checking only, not a value proposal (`dryrun_testfill_*.diff.txt`) | both rc=0, `gate: PASS`, `would be refused at live run: (nothing)`. Smoke: cells 6, seeds [6301, 6303] (alternate-v1, HOST2 share), budget 300. Qualification: cells 12, seeds [8110, 8102, 8103, 8106] (replicate-v1), budget 2000. Engine gate read `docker version` = 29.9.3 and matched. The output directory was not created |

- Paths: no breakage. The cell command and report paths derive from the worktree and `--output` (lowercase `projects` and a different account are fine). `git grep '/home/linux|Projects/InodeFence'` over scripts, src and configs finds hits only off the main-run path: `concurrency-scaling-v1.md:283`, `concurrency-scaling-v2.md:297` (doc examples), and `src/inodefence/evaluation/n04_preflight.py:66-76` (older N04 macOS paths). `run_exp0.py`, `launcher_guards.py`, `local_node_tar_smoke.sh` and the two registration files have none.
- Observation 1: the dry-run returned `gate: PASS` with **no target, controller or helper image present** on HOST2. The dry-run does not inspect images (the `--target-digest` value is compared with the registration only). The existence check on `LOCAL_IMAGES` (`scripts/run_exp0.py:614,627`) happens only in a live run. Image-id comparison is a separate code item (§13 of the qualification file), so a dry-run PASS does not cover the image preflight.
- Observation 2: the dry-run prints `warmup: BUILD_ONLY=1 …` even with `--skip-build` (`scripts/run_exp0.py:1414`). A live run skips it (`:1995`, `if pending and not args.skip_build`). The output is misleading but the behaviour is correct.
- Evidence: `dryrun_registrations.txt`, `dryrun_testfill_run-exp0-eng-smoke-v1.diff.txt`, `dryrun_testfill_host-qualification-v1-run.diff.txt`.

## 23. Clock confirmation test verdict (fixed criteria): **PASS**

Run 14:57:25–17:22:28 KST (`clock_confirm.txt`, scripts `confirm_run.sh.txt`, `clockbracket2.py.txt`, `tickmon2.py.txt`). timesyncd inactive (enabled at start, disabled at 15:23 with no running-state change). W32Time not running. No transfer or other heavy I/O ran during the brackets.

| Criterion (fixed before measurement) | Measured | Result |
| --- | --- | --- |
| Bracket ① 600 s (14:57–15:07): \|MONO\| ≤ 500 ppm | MONO −0.067 ppm, REALTIME −0.067 ppm, RAW −0.054 ppm (±0.23 ppm) | PASS |
| Bracket ② 600 s (17:12–17:22): \|MONO\| ≤ 500 ppm | MONO +0.012 ppm, REALTIME +0.013 ppm, RAW −0.041 ppm (±0.39 ppm) | PASS |
| tick = 10000 throughout | 763 records (10 s change detection + 10-minute samples + adjtimex at start and end): tick ∈ {10000} only | PASS |
| REALTIME − Windows UTC change over 2 h ≤ 0.5 s | −0.192 s (15:07) → −0.190 s (17:22 region); range of 14 samples 0.011 s | PASS |

- freq kept being rewritten every 10 s (−9.0 to +19.2 ppm, mostly near 0). Its source is still unidentified. This is not a criterion and is reported only.
- The first test's transient (tick 9093–9559 while timesyncd was running) is kept separate from this verdict (§11).
- Absolute offset (not a criterion): WSL is about 1.57 s behind NTP (§20). W32Time sync comes next (owner, §21 item 5), then criteria (a)(b)(c).

## 24. ORCH decisions on the §22 findings (17:26 KST) and how they enter the checklist

| Topic | Decision (ORCH) | HOST2 checklist entry |
| --- | --- | --- |
| venv `.pth` points to the main checkout | Do not change the `.pth`. Set `PYTHONPATH=src` explicitly in the execution worktree command (passed to W3 for the runbook) | Pre-run check: in the execution worktree, `PYTHONPATH=src <venv>/bin/python -c "import inodefence, sys; print(inodefence.__file__)"` must print a path under `~/inodefence-host2-20261111/execution/src/`. Otherwise do not start |
| Leftover-resource criterion | **The code governs:** containers `name=inodefence-`, volumes `name=inodefence-local-` (same as the driver filter since D041). The §4 wording is inaccurate and will be corrected (methodology owner) | Dev-container volumes `inodefence-codex` and `inodefence-runtime` do not count as leftovers. Do not delete them. §19.1 row "Leftover volumes 0" → **Yes** |
| Dry-run observations (no image check, misleading `warmup` line) | Passed to W3 | **A dry-run PASS does not replace the image preflight.** Before the run, compare the ids of the target, controller, helper and holdout images separately with `docker image inspect` |
| SNTP | HOST1 measured at 17:26 KST with the same script: time.windows.com −0.5196 s (2/5 timeouts), pool.ntp.org −0.7273 s (5/5). HOST1 has timesyncd running and tick 10398. The difference from HOST2 is about 2.1–2.3 s (record only) | Remeasure HOST2 after the W32Time sync (built into `post_w32.sh`) |
| Check worktree `check-129324d` | Keep it. It is not an execution candidate. The integration head has moved to `a76ffee` | Execution SHA and criteria file (3 expected image ids, Engine 29.9.3, 16 shared-path hashes, execution SHA) will come from ORCH |

## 25. Restart protection applied (owner UAC approval 17:33:55 KST): **configuration compliant / effect not observed**

The elevated script started at 15:18 (`if_host2_elevated.ps1.txt` = `if_host2_pause.ps1.txt` then `if_host2_restart_apply.ps1.txt`) ran after the owner clicked "Yes". Log: `restart_protection_apply.txt`, transcript header `restart_protection_transcript.txt`, both redacted (host name, account, registered owner, product id).

| Item | Before (`restart-protection-before.txt`, 14:xx, and log BEFORE) | After (17:33:57) |
| --- | --- | --- |
| Update pause (UX Settings) | none | `PauseUpdatesStartTime` 2026-11-11T08:33:55Z, `PauseUpdatesExpiryTime`/`Pause{Feature,Quality}UpdatesEndTime` **2026-12-16T08:33:55Z (17:33 KST)**, 35 days. The log's BEFORE block already shows the pause because the pause script runs first |
| AU policy `NoAutoRebootWithLoggedOnUsers` | key absent | 1 |
| AU policy `AUOptions` | key absent | 2 (notify before download) |
| powercfg AC standby / hibernate | 0 / 0 | 0 / 0 (unchanged) |
| Pending reboot WU / CBS / PFRO | False / False / False | False / False / False |
| UpdateOrchestrator scheduled tasks (R6, admin) | listed | listed (not changed; `Schedule Scan` next run 19:16 KST today) |

- Verdict: **configuration compliant.** "Restart prevention effective" stays UNKNOWN until an automatic restart is observed being withheld.
- Rechecks: the pause expiry (12/16) is after the main run window (11/18–11/25). Recheck it on 11/18 before the run. Revert after the main run per §12 (Resume updates; `reg delete` both AU values).

## 26. Image transfer, identity, volume in-use test (17:37–17:39 KST)

**Transfer verification: PASS.** (`transfer_run.txt`)
- HOST1 appeared on the tailnet (shared node). Host key fingerprint `SHA256:LHkKFflNNKPIzTB/ljwOuInFGX1OjSCs6ZRqRtLEiuM` (ED25519, port 2222). Recorded at first contact (TOFU). HOST1 should confirm it matches its `/etc/ssh` key.
- rrsync restriction, once each: shell command refused (`SSH_ORIGINAL_COMMAND does not run rsync`, rc=1); write refused (`sending to read-only server is not allowed`, rc=12); `..` refused (`do not use .. in arg`, rc=12); `/etc/` was anchored inside the restricted dir (`/home/linux/inodefence-transfer/etc` not found, rc=23).
- `rsync -av --partial` of `images-20261111/`: 10 files, 463,887,484 bytes in 45 s (10.2 MB/s), rc=0. Route: direct (Tailscale ping 9 ms via a public endpoint; earlier pings at 17:37 went through DERP tok, 71 ms).
- `sha256sum -c SHA256SUMS`: 4/4 OK, sizes equal the expected values.

**Image identity: PASS.** (`image_load.txt`) `docker load -i` for each tar, rc=0, about 1 s each. `docker image inspect`:

| Tag | Id | Expected | Match |
| --- | --- | --- | --- |
| inodefence-node-tar-effect:7.5.2 | sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb | same | yes, amd64/linux |
| inodefence-node-tar-effect:7.4.4 | sha256:f5d3e9a999cfad0a5f37002bf36802378b20777646be3684eb97baeaa4080421 | same | yes, amd64/linux |
| inodefence-controller:local | sha256:d44900e13ed5083db54cefda8833328d4da61148f62213d86f07afa78191d7a4 | same | yes, amd64/linux |
| inodefence-helper:local | sha256:9b9dd606c49ff0051465fe9e435351f33623d949f360d6518580855e3781cc27 | same | yes, amd64/linux |

`docker system df` images 8 → 12 (9.353 → 9.881 GB). Containers 4 and volumes 3 unchanged, running 0. The tars are kept at `~/inodefence-host2-20261111/images-20261111/` (not inside the repo). Transfer and load finished before the W32Time (c) bracket.

**Volume in-use test (Engine 29.9.3): refusal confirmed.** (`volume_inuse.txt`) `docker volume create w2-volprobe-20261111` → `docker create` (not started) `alpine:3.20` mounting it → `docker volume rm` refused with `volume is in use - [adf22b26…]`, rc=1. Then only the self-created container and volume were removed (rc=0). After: total containers 4 and volumes 3, the same as before.

## 27. W32Time sync (owner UAC 17:33:53 and retry 17:37:41): criteria (a)(b)(c) in progress

`w32time_before_wsl.txt`, `w32time_apply.txt` (Korean w32tm text in the log is mojibake from code-page mixing, but numbers and English fields are intact), scripts `if_host2_w32time.ps1.txt`, `if_host2_w32resync2.ps1.txt`.

| Time | Event |
| --- | --- |
| 17:25:35 | BEFORE (WSL side): timesyncd inactive/disabled, tick 10000, freq +0.08 ppm, REALTIME − WinUTC −0.198 s. W32Time Stopped/Manual |
| 17:33:54 | BEFORE (Windows): stripchart vs time.windows.com +1.622 s (Windows behind) |
| 17:34 | `Start-Service` True. `w32tm /resync /force`: "no time data was available" (sync failed). Startup type → Automatic. AFTER: Running/Automatic, leap 3 (unsynchronized), source Local CMOS Clock, stripchart +1.6235 s |
| 17:37:41 | Retry (owner UAC; no config change; `NtpServer` was already `time.windows.com,0x9`, Type NTP): `/resync /rediscover` and `/resync /force` print the same message, but **last sync 17:38:08, source time.windows.com,0x9**, peer state active. Stripchart −0.0001 / +0.0017 / +0.0003 s. `/query /status` still shows leap 3 / stratum 0 (it updates on the next poll) |

- **(a) Windows↔NTP |offset| ≤ 0.5 s: PASS** (max 0.0017 s, 17:38:15–19).
- (b) WSL REALTIME − WinUTC ≤ 0.5 s within 30 min, and (c) one 600 s bracket with |MONO| ≤ 500 ppm and tick 10000: running (`post_w32.sh`: 1-minute samples 17:34–18:04, bracket about 18:04–18:14, then SNTP remeasure). The effective sync time is 17:38:08, so the 30-minute window for (b) is counted from then.
- Startup type changed Manual → Automatic. Revert: `Set-Service W32Time -StartupType Manual; Stop-Service W32Time`.
