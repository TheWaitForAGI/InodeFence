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

## 10. Evidence manifest

`SHA256SUMS` covers every public file in this directory. Raw probe files are redacted copies. CRLF was converted to LF, and trailing whitespace and blank lines at end of file were removed. The original unredacted outputs are kept only in the session-local scratch area.
