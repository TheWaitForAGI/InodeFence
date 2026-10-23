# 규민 Runtime / Vulnerability Owner 후속 보고서

수행 시각은 2026-10-23 09:36–10:23 KST이다. 이 보고서는 2026-10-22에 작성된
`/tmp/inodefence-pr114-binding/docs/research/diagnostics/gyumin-runtime-20261024/`의 다섯 문서를
보존한 채, 이후 추가된 PR #118–#120과 로컬 원본 차이를 후속 검토한 결과다. 영상 제작·녹화·재생
확인은 범위에서 제외했다. N01 historical target, N05, Track A pilot은 실행하지 않았다.

## 저장소와 작업 트리

| 항목 | 확인값 | 판정 |
| --- | --- | --- |
| 실제 저장소 | `/workspaces/InodeFence` | 확인 |
| Remote | `git@github.com:TheWaitForAGI/InodeFence.git` | 확인 |
| Primary | `main` / `8d29982c26cebfcce7a413b3ba9177fcd28078de` | clean, `origin/main`과 동일 |
| 기존 worktree | `/tmp/inodefence-pr114-binding`, `codex/n05-host-source-binding`, `e83349ed1592d536e3ec0fce3c7cb204cb5c6ec9` | 기존 untracked 보고서만 보존 |
| 후속 worktree | `/tmp/inodefence-gyumin-runtime-20261023` | 새 별도 worktree |
| 후속 branch | `codex/gyumin-runtime-followup-20261023` | 로컬 전용, push 안 함 |
| 통합 후보 HEAD | `8979f248ee77fb69259292adb9c32fda371ea4e9` | #120 위에 #115를 clean cherry-pick한 engineering 후보 |
| 현재 dirty 사유 | 이 디렉터리의 새 보고서 | 코드 후보 commit과 분리 |

현재 process는 Dev Container 안의 WSL2 Linux x86_64다. macOS host path는 이 namespace에 없으며,
OrbStack daemon도 없다. 세 worktree는 같은 Git object store를 공유하지만 서로 다른 checkout이다.
따라서 현재 WSL 검사는 Mac/OrbStack 배치 검증을 대신하지 않는다.

원격 fetch 후 clean `main`은 이미 최신이라 fast-forward가 필요하지 않았다. 기존 dirty branch에
pull/reset/clean을 하지 않았고, 원격 push·PR 병합·실행 승인 생성도 하지 않았다.

## 기존 작업에서 재사용한 것과 이번 추가분

재사용한 것은 기존 N01/N04 문서 checksum chain, PR #115의 source-origin 수정, N05 계약 및 기존
demo script다. 코드를 새로 중복 작성하지 않고 PR #120 head 위에 PR #115 commit 하나만 적용했다.

이번에 새로 확인하거나 추가한 것은 다음과 같다.

1. GitHub PR 페이지와 원격 pull head를 다시 확인해 #108/#112/#113/#114/#115/#118/#119/#120의
   최신 head/base/open-draft 상태를 고정했다.
2. #118(Unit 1), #119(Unit 2), #120(Unit 3)의 실제 code path를 검토하고 #120에 #115가 없음을
   `git merge-base`, `git grep`과 diff로 확인했다.
3. #120 위에 #115만 적용한 로컬 통합 후보 `8979f24`를 만들었다. Track A Unit 4는 구현하지 않았다.
4. ignored local static acquisition 디렉터리에서 node-tar 7.5.2/7.5.3 npm tarball bytes를 발견해
   전체 checksum file, tarball SHA-256, tar member bytes와 source 차이를 직접 재검증했다.
5. 후보 HEAD에서 target-free focused 277 tests와 canonical `make check` 1,757 tests를 통과했다.

## PR 최신 상태와 실제 차이

2026-10-23 KST에 GitHub 페이지와 fetch된 pull head를 확인했다. 모든 PR은 미병합이며 제출된 사람
승인을 확인하지 못했다. 최신 CI check는 성공 상태였지만 CI 성공은 review·authorization·실험
결과가 아니다.

| PR | State | Base → head | Head SHA | 실제 범위 |
| --- | --- | --- | --- | --- |
| #108 | draft | `main` → `experiment/track-a-exploratory-pilot` | `64a7a1645c03512d50ff5e0246108d297d1e6aa8` | 기존 Track A 준비 |
| #112 | draft | `main` → `fix/n05-preflight-host-evidence` | `0eca90f44a249d3ab1e66966b7ab3cfe80f79055` | host stderr/transport 보완 |
| #113 | draft | `main` → `docs/n05-native-qualification-critical-path` | `00356e43f5e6bc1623cc7b36cba0479b755b1118` | N05 critical-path 문서 |
| #114 | draft | `main` → `feat/n05-preflight-readiness-v2` | `f7aaa33050e247e0718d4ceb1ba01485802e269d` | N05 mode/reader 후보 |
| #115 | open | #114 branch → `codex/n05-host-source-binding` | `e83349ed1592d536e3ec0fce3c7cb204cb5c6ec9` | 실제 loaded host code origin/hash gate |
| #118 | draft | `docs/mid03-n05-consumer-integration-plan` → `feat/track-a-admission-reader` | `7f8696f9ea701c8438585843d5f78d0248de8933` | Unit 1 typed admission |
| #119 | draft | #118 branch → `feat/preserve-track-a-admission-evidence` | `348e809fc37b1c03fcbfad55393c2425e84c969c` | Unit 2 evidence preservation/reverification |
| #120 | draft | #119 branch → `feat/track-a-host-attempt-ledger` | `02072c95537d76d1b213b9c858d96c97fff653cc` | Unit 3 host attempt ledger/controller 연결 |

PR #120은 #118/#119를 ancestry로 포함하고 #108/#114 계열 code도 포함하지만, #115
`e83349e`는 ancestor가 아니다. `verify_authorized_runtime_files`는 #115와 로컬 후보에만 있고 #120
head에는 없다. PR 설명과 실제 코드는 이 점에서 일치한다. #120은 Unit 3까지라고 명시하며 Unit 4
final-manifest/analysis 연결을 남긴다.

## 코드 검토 결론

PR #115의 순서는 요구와 일치한다.

- `scripts/container_host.py:1128-1134`: invocation과 실제 loaded source path/hash를 검증한다.
- `scripts/container_host.py:1141`: 검증 뒤에 처음 `N05HostLedger`를 만든다.
- `scripts/container_host.py:1148`: 그 뒤에 처음 Docker executable을 조회한다.
- `src/inodefence/evaluation/n05_preflight.py:337-390`: 승인 worktree, exact loaded origin,
  nonsymlink path와 승인 SHA-256을 fail closed로 비교한다.

Track A는 `track_a_admission.py:745-821`에서 N05 host/Linux evidence를 다시 열고 N05 authorization,
pilot authorization, provenance와 source revision을 일치시킨다. `track_a_exploratory.py:635-725`는
freeze/read/실행 직전에 pilot/N05/protocol과 clean source를 재검증한다. `track_a_host_ledger.py:430-525`
및 controller entry는 기록된 원본 경로를 다시 연다. 다만 #120만으로는 N05 host process가 실제로
승인 checkout의 code를 load했는지 증명하지 못하므로 #115의 결합이 필요하다.

로컬 통합 후보는 #120 대비 정확히 #115의 7개 파일, `+277/-23`만 포함하며 cherry-pick conflict는
없었다. 후보는 review되거나 승인된 최종 source가 아니다. 보고서가 untracked라 worktree도 최종
clean source가 아니다. 최종 source SHA는 Unit 4와 review 결정 후 다시 동결해야 한다.

## 완료·미완료·차단

| 작업 | 상태 | 실제 근거 | 다음 담당자 / 완료 조건 |
| --- | --- | --- | --- |
| 저장소·worktree·PR 최신 상태 확인 | 완료 | 이 문서와 `validation-log.md` | 없음 |
| #115가 ledger/Docker 전 실행 source를 검증하는지 확인 | 완료 | 위 code line 및 regression tests | 없음 |
| 최신 Track A stack의 #115 누락 확인 | 완료 | #120 grep/ancestry, 로컬 후보 diff | 주언/리드: 통합 PR 결정 |
| N01 static package/source 재검증 | 완료 | `n01-evidence-review.md` | 사람 correspondence는 별도 |
| N01 retained raw per-run 재감사 | 차단 | N02/N04 evidence roots 부재 | 자료 소유자: immutable copy 제공; 규민: offline reader/원문 대조 |
| N01 human correspondence | 차단 | AI는 token 미발급 | 사람 reviewer: 질문표에 disposition 기록 |
| N05 코드 engineering 검증 | 완료 | focused 277, `make check` 1,757 PASS | final SHA에서 재실행 필요 |
| Mac/OrbStack 실제 환경 admission | 차단 | 현재 WSL2 x86_64, Docker CLI 없음 | 규민+host 소유자: exact host에서 read-only admission |
| N05 사람 승인 | 차단 | authorization JSON 없음 | 승인자: exact source/controller/attempt/scope 승인 |
| N05 attempt 001 실행 | 미실행 | ledger/evidence root absent | 모든 gate 충족 후 규민이 단 한 번 실행 |
| Track A Unit 4 | 미완료·범위 밖 | plan `Unit 4`와 STATUS | 주언: final manifest/analysis 연결 |
| Track A pilot | 미실행 | N05 PASS와 별도 pilot 승인 모두 없음 | 주언+승인자 |
| 영상 | 제외 | 사용자 지정 | 이번 범위에서 후속 없음 |

미완료/차단 항목의 종료 조건은 다음처럼 고정한다.

| 항목 | 담당자 | 필요한 입력 | 다음 행동 | 완료 기준 |
| --- | --- | --- | --- | --- |
| N01 retained raw audit | 자료 소유자 + 규민 | checksum이 알려진 immutable N02/N04 copy | 원본을 수정하지 않고 rehash하고 writable audit copy에서 offline reader 실행 | manifest/reference/per-run bytes와 reader 결과가 모두 일치하거나 불일치가 보존됨 |
| N01 human correspondence | 사람 reviewer | 위 raw audit, source/package limitation, 질문 7개 | 승인·거부·불충분 중 하나를 서명성 기록 | 사람 disposition과 근거 위치가 남고 AI token과 분리됨 |
| Final source freeze | 주언 + 규민 + research lead | Unit 4 포함 최종 integration commit과 review | #115 포함 여부, clean tree, executable hashes, CI를 다시 확인 | reviewed clean commit 하나와 file digest inventory가 고정됨 |
| Mac/OrbStack admission | 규민 + host 소유자 | exact Mac arm64/OrbStack daemon, controller/image/package/volume | read-only pre-ledger admission 수행 | authorization의 모든 identity/path/isolation 값과 실제 값이 일치 |
| N05 authorization/run | 사람 승인자 + 규민 | final source/image와 canonical authorization JSON | 승인 scope 확인 후 ledger 생성부터 single attempt 실행 | host/Linux verifier의 실제 terminal 판정이 보존됨; retry 없음 |
| Track A Unit 4/pilot | 주언 + 사람 승인자 | N05 PASS, publication authority 결정, 별도 pilot approval | 20 attempt final reader/analysis 연결 후 승인된 경우만 실행 | 전체 denominator와 raw/summary graph가 보존되고 final reader가 재개방 성공 |

## 기존 demo script 점검

기존 `demo-script.md`는 수정하지 않고 다시 읽었다. 실제 화면이 없는 구간을 모두
`[설명용 시각화]`로 표시하고, C1을 `(st_dev, st_ino)` 공유, C2를 nlink/ctime metadata-only로
설명하며 fixed rejection만으로 안전을 주장하지 않는다. “npm tarball 원 bytes는 retained root에
없다”는 문구도 N02 root에 관해서는 여전히 정확하다. 별도 ignored static bytes가 발견됐다는
사실은 이 후속 N01 문서에만 추가했다. 영상 제작·녹화·재생 확인은 수행하지 않았다.

## 최종 상태

- N01: current static package/source 및 frozen input bytes는 직접 검증했지만 historical raw root는
  부재한다. 상태는 `AWAITING_HUMAN_CORRESPONDENCE_REVIEW` 유지다.
- N05 구현: 로컬 통합 후보에서 engineering 검증 완료다.
- N05 승인: `NOT_AUTHORIZED`다.
- N05 실행: `NOT_RUN`이다. PASS나 violation 0으로 기록하지 않는다.
- Track A: Units 1–3은 target-free 후보와 tests가 있으나 Unit 4, 실제 path mapping, N05 PASS,
  별도 pilot approval이 없다. Pilot은 `NOT_RUN`이다.

세부 N01 판단은 `n01-evidence-review.md`, N05 gate는 `n05-gates-and-environment.md`, 이번 명령과
종료 코드는 `validation-log.md`, 주언 인계는 `handoff-to-jueon.md`에 있다.
