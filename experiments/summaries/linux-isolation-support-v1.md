# Linux execution isolation support v1 — environment blocker

Pre-audit Task Contract의 Work Package A1 지원 조사다. 현재 상태는
**ENGINEERING FOUNDATION; execution isolation blocked in the checked Dev Container**다.
격리 구현 또는 benign Node configured campaign을 완료한 기록이 아니다.

## 범위와 재실행

Engine 기준점은 clean main `83397aacb1b53fed9a08b1087521bd8acb649ed1`이다.
2026-10-04 실행 중인 repository Dev Container에서 `vscode` (uid/gid 1000)로 조사했다.
Ubuntu 24.04, Python 3.12.3, Linux aarch64, kernel
`7.0.14-orbstack-00380-ga7e0a2dc9535`, runtime `/var/lib/inodefence` (btrfs volume)다.
macOS host filesystem을 canonical evidence로 사용하지 않았다.

지원 환경 안에서 실행한다:

```bash
python scripts/check_linux_isolation_support.py > experiments/raw/isolation-support.json
```

[진단 코드](../../scripts/check_linux_isolation_support.py)는 고정된 `unshare`/`true` 8개 probe를
각각 wall-clock timeout 5초로 실행한다. RNG/seed, archive, target adapter, execution budget,
sentinel 설정은 해당 없음이며 Node campaign archive execution 수는 0이다.
새 namespace 생성 외에 mount operation, fork, network traffic, runtime 생성은 하지 않는다.
PID probe는 `pid_for_children` namespace 생성 전제만 검사하며 새 PID namespace의 child 실행이나
reaping을 검증하지 않는다. Resource 값은 현재 process의 관찰값이며 target limit policy가 아니다.

CLI exit 0은 user 및 user+mount/network/PID/combined 생성 5개 probe의 성공만 의미한다.
Direct mount/network/PID probe는 capability 의존성을 구분하는 보조 정보다. Exit 1은 필요한 생성
probe의 실패/missing tool/platform이다. Timeout/launch error도 실패로 남는다.
어느 결과도 campaign 실행 허가, frozen isolation provenance나 containment certificate가 아니다.

## 관찰 사실

| 항목 | 실제 결과 |
| --- | --- |
| User namespace | `unshare --user --map-root-user true`: exit 1, EPERM |
| User + mount/network/PID 각각 | 세 명령 모두 exit 1, EPERM |
| User + mount + network + PID | exit 1, EPERM |
| Mount/network/PID 각각 | 세 명령 모두 exit 1, EPERM |
| Trace | `strace -e unshare unshare --user --map-root-user true`: `unshare(CLONE_NEWUSER) = -1 EPERM` |
| Credentials / capability | uid/gid 1000; `CapEff=0000000000000000`; `NoNewPrivs=0` |
| Seccomp | mode 2, filter count 1 |
| User namespace limit | `/proc/sys/user/max_user_namespaces=96377` |
| `unprivileged_userns_clone` | sysctl file absent; 이것만으로 kernel feature 부재를 추론하지 않음 |
| Cgroup | cgroup v2 mount read-only; membership `0::/`; harness에 writable delegation 없음 |
| Tools | `unshare`, `setpriv`, `prlimit` 존재; `bwrap`, `newuidmap`, `newgidmap`, in-container Docker CLI/socket 없음 |
| Observed limits | AS/FSIZE unlimited; NPROC 96377/96377 per real UID; NOFILE 20480/1048576 |
| Container policy | `Privileged=false`, CapAdd/SecurityOpt 없음; writable source bind/runtime volume, bridge network |

Namespace 존재와 namespace 생성 권한을 구분한다. 기존 `/proc/self/ns`는 읽을 수 있고 `/proc`는
procfs지만, per-execution namespace 생성은 거부됐다. Private mount namespace가 없으므로 별도 mount
operation을 시도하지 않았다. `setpriv`/resource API 존재나 process-group kill만으로 요구된
filesystem view/network/process context를 제공한다고 주장하지 않는다.

## Blocker와 필요한 architectural decision

현재 process/runtime/container 정책 안에서 **검증된 execution backend를 확보하지 못했다**.
EPERM은 생성 권한/policy 차단의 관찰값이며 정확히 어느 seccomp/LSM/kernel policy가 거부했는지
분리 입증하지 않았다. Kernel에 namespace 기능이 없다고 단정하지 않는다.
[Docker 문서](https://docs.docker.com/engine/security/seccomp/)는 기본 seccomp가 namespace 관련
syscall과 mount를 제한한다고 설명한다. 현재 실패와 일치하지만 원인 분리 검증을 대신하지 않는다.

계속하려면 maintainer가 지원 execution 환경의 경계를 선택해야 한다:

- nonprivileged namespace 생성을 지원하는 환경과 명시적인 container/kernel policy를 선택하고,
  source/home 노출 없이 filesystem view, network, credentials/resources와 PID lifecycle를 검증한다.
- 또는 별도 관리되는 execution service/container backend와 그 권한·filesystem 공유 방식을
  설계하고 review한다. 현재 Dev Container에 해당 backend/broker는 없다.

이 PR은 container security policy를 넓히거나 privileged mode/Docker socket/sudo 기반 executor를
도입하지 않는다. Landlock/seccomp/resource controls만 덧붙여 full descendant lifecycle을 검증했다고
주장하지 않는다. Process-group cleanup의 detached descendant 한계는 기존 contract 그대로다.
아직 환경 선택이 없으므로 production isolation interface/fallback을 만들지 않았다.

환경을 정한 뒤 A를 구현·검증·merge하고 B의 frozen isolation config/provenance binding,
C의 tiny benign Node full-path smoke를 진행한다. D/E/F/G와 full architecture freeze는 후속이다.
Status를 READY FOR FULL CODE / ARCHITECTURE AUDIT로 올리지 않는다.

## 검증과 한계

초기 supported Linux `make check`는 462 passed와 lint/format/Pyright/environment/docs PASS였다.
Focused namespace/Node/process/campaign/config 검사는 100 passed였다. 두 Node campaign entry는
provenance capture/runtime/첫 archive 이전 거부하며 runtime listing이 그대로임을 확인했다.
Local review에서 진단을 거짓 positive로 바꾸면 1 regression이 실패하고, campaign gate를 생략하면
두 entry regression이 실패했다. 변형을 복원했고 production engine 변경은 없다.

C0/C1/C2, BEFORE/AFTER, signature/fingerprint, budget/RNG, frozen provenance와 export semantics는
변경하지 않았다. Snapshot-only observation, detached descendants, exact dependency contents,
dirty-patch preservation, resource policy와 interrupted export 한계는 그대로 남는다.
이번 결과는 해당 환경의 support 진단이며 다른 OS/kernel/container policy로 일반화하지 않는다.
취약점 finding, evaluation 또는 paper-ready evidence가 아니다.


## 보존된 원본과 최종 local validation

[Support JSON 원본](linux-isolation-support-v1.json)은 clean diagnostic revision
`04c418f881b7ce817579281901745c4197db77bc`에서 수집했다. Source dirty=false다.
로컬 Git-ignored `experiments/raw/preaudit-isolation-20261004/isolation-support.json`과 byte-identical
복사본이며 SHA-256은 `5a026225c30d25f171d52a25986d1cf8701a99e7328a55c0642e8ec5d1b354c7`다. JSON을 수동 수정하지 않았다.
원본 실행의 engine은 기준 main과 같으며 diagnostic/script/tests/docs만 추가됐다.
Util-linux (`unshare`, `setpriv`, `prlimit`) version은 2.39.3이었다.

최종 local `make check`: **474 passed**, Ruff/format/Pyright/environment/docs PASS.
`git diff --check` PASS. `make fixtures`와 regular-file/directory/hardlink/symlink 4 probes PASS,
기존 fixture bytes 불변이다. 기존 test 삭제/skip/weakening과 production engine 변경은 없다.

같은 clean diagnostic revision에서 reference config CLI를 실행했다:

```bash
python -m scripts.run_configured_reference experiments/configs/reference-smoke-v1.json --output experiments/raw/preaudit-isolation-20261004/reference
```

Config ID `5a24679b4a55f55fa20272e8817c9fd8f7d97fc994495c964d2b37f0967863a0`, seed 11/budget 8, Python 3.12.3/timeout 5초다.
실제 8 SUCCESS, CorpusStats observations=8 / interesting_observations=5 / retained_cases=5 /
unique_states=5 / unique_violation_fingerprints=0이었다. C0/C1/C2 위반 evidence는 없었다.
Supported Linux 안에서 exact count/index, earlier retained parent lineage, canonical JSONL,
stored source/config ID, checksum과 모든 run root cleanup을 확인했다. 이 결과는 plumbing 검사다.
Node configured campaign은 실행하지 않았다.

Raw reference는 로컬 Git-ignored `experiments/raw/preaudit-isolation-20261004/reference/`에 보존하고
검증 기록은 그 상위 `reference-verification.json`에 있다. 공유 upload는 하지 않았다.

| 원본 | SHA-256 |
| --- | --- |
| experiment.json | `4d99dfed6077c87f75f55d519256e1c3c1ea843fa275a7fc6706bd96aaf34527` |
| manifest.json | `cf28d19d14615979cd3d91c1e91e804800b320c468f38282bd681f35d39b48b9` |
| steps.jsonl | `c566115230c9ce398a66977989fba66274851b4f33fdc8e116910b3600ca7c37` |
