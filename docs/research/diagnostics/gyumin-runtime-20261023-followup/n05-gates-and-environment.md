# N05 gate와 환경 후속 판정

판정 시각: 2026-10-23 KST. 이 문서는 실행 승인 record가 아니며 N05를 실행하지 않았다.

## 통합 후보와 최종 실행 source

로컬 후보는 PR #120 `02072c95537d76d1b213b9c858d96c97fff653cc` 위에 PR #115
`e83349ed1592d536e3ec0fce3c7cb204cb5c6ec9`를 cherry-pick한
`8979f248ee77fb69259292adb9c32fda371ea4e9`다. conflict 없이 #115의 7개 파일만 추가됐다.

이 SHA는 다음 이유로 **통합 후보**일 뿐 **최종 실행 source**가 아니다.

- PR #115/#118/#119/#120이 미병합이고 사람 review/approval이 완료되지 않았다.
- Track A Unit 4가 남아 최종 repository SHA가 더 바뀔 수 있다.
- N05 controller image가 이 후보로 rebuild/inspect/freeze되지 않았다.
- 새 N05 사람 authorization record가 없다.
- 이 보고서가 untracked이므로 현재 worktree는 clean execution clone이 아니다.

최종 source가 정해지면 clean 별도 clone에서 commit SHA와 executable files를 다시 hash하고,
그 source로 controller image를 만들어 exact authorization에 결합해야 한다.

## #115 실행 순서 검토

`scripts/container_host.py:1128-1134`는 N05 invocation을 승인 record에 결합한 다음
`verify_authorized_runtime_files`를 호출한다. 이 함수는 `scripts/container_host.py`,
`n05_preflight.py`, `execution/container.py`, `execution/docker_client.py`의 실제 loaded origin이
승인 worktree의 exact canonical nonsymlink file인지와 승인 SHA-256인지 검사한다.

그 뒤 `scripts/container_host.py:1141`에서 host ledger가 만들어져 attempt가 소비되고,
`scripts/container_host.py:1148`에서 Docker CLI를 처음 조회한다. 다른 checkout, origin 없음,
symlink, digest drift는 ledger 0/Docker 0으로 거부하는 tests가 있다.

PR #120에는 이 함수와 호출이 없었다. 로컬 후보에는 있다.

## 후보 executable file SHA-256

아래 값은 `8979f24` 후보 bytes의 engineering inventory이며 승인값이 아니다.

| File | Candidate SHA-256 |
| --- | --- |
| `docs/research/benchmarks/n05-five-second-preflight-task-contract-draft.md` | `6dd9425370597ea0451226cc9a19f7d1ea0cbb79e3a4ebb244a5e6749b218379` |
| `scripts/container_controller.py` | `a902217039e310c4ad44e59707f321a2f5cae30ae53567544aa9519a8c133917` |
| `scripts/container_host.py` | `b41f12aa769a770f5507ef36c3a52202a1129a067a87f105baadc299362873ac` |
| `src/inodefence/evaluation/n05_preflight.py` | `1a3cf7b34f3f2a10d02ebefc37b7c3af6fe52b487e6affd9084ba7079d533b82` |
| `src/inodefence/evaluation/n05_preflight_reader.py` | `20423a2750cb7c4901f64bcda20165eace3ada88bb8cd672cab8d6a939245da0` |
| `src/inodefence/execution/container.py` | `f064d66994e245efc9ead7c1fd07d27ae0b992e87485a43e655d5d600dc6b25e` |
| `src/inodefence/execution/docker_client.py` | `a501f1e3f442c9ba4a560acb969957ce9cd3e504167a86cb5fb174fef3c062dc` |
| `src/inodefence/targets/_node_worker.cjs` | `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b` |

## 계약과 gate 판정

| Gate | 계약/필요 조건 | 현재 근거 | 판정 |
| --- | --- | --- | --- |
| Attempt | `n05-five-second-preflight-v2-attempt-001` | constants/contract 일치, path absent | 충족(미소비) |
| Budget | affected 4 + fixed 4 benign, 각 5초, 전체 30분, retry 없음 | contract/source 일치 | 설계 충족 |
| Controls | target 전 unchanged C0/C1/C2 false; harness hardlink C0 false/C1/C2 true | code와 synthetic tests | 설계 충족, 실제 미검증 |
| Pilot flag | N05 record `pilot_authorized=false` | schema/contract 일치 | 충족 |
| Clean source | reviewed exact clean SHA와 executable hashes | 후보만 존재, current report untracked | 불충족 |
| Loaded host source | 실제 host entry/module origin을 승인 worktree에 결합 | #115/local 후보 구현·tests | 구현 충족, 실제 host 미검증 |
| Controller source | 같은 read-only source mount의 controller/reader | code/contract상 요구 | 배치 미확인 |
| Mac host | arm64 macOS, `/usr/local/bin/docker`, context `orbstack`, exact daemon identity | 현재 WSL2 x86_64, Docker CLI 없음 | 불충족 |
| Linux controller | fresh Linux arm64, immutable image, fixed resource/isolation | candidate image 문서값만 있음 | 미확인 |
| Storage separation | read-only source, dedicated runtime volume, separate host/Linux evidence | code/contract상 요구 | 실제 배치 미확인 |
| Runtime volume | fresh labelled `inodefence-n05-preflight-runtime-v2-attempt-001`, sole young controller consumer | 현재 environment에서 admission 안 함 | 미확인 |
| New evidence | Linux root와 host ledger absent/no-overwrite | 두 required path 모두 현재 namespace에서 absent | 부분 확인; Mac에서 재검사 |
| N04 isolation | consumed N04 attempt/path 재사용 금지 | contract와 tests 유지 | 충족 |
| Independent readers | Linux reader와 host verifier가 source에 존재 | code/tests PASS | 구현 충족 |
| stderr/cleanup | 첫 1 MiB 보존·계속 drain, exact checksum, owned cleanup, uncertainty→INCONCLUSIVE | code/tests PASS | 구현 충족, 실제 미검증 |
| Human authorization | exact source/controller/daemon/attempt/scope의 canonical record | 검색 결과 없음; prompt는 승인 아님 | 불충족 |

## Target identity

| Identity | affected | fixed | 현재 판정 |
| --- | --- | --- | --- |
| Node / node-tar | 22.22.0 / 7.5.2 | 22.22.0 / 7.5.3 | 계약 고정 |
| Image ID | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` | 실제 daemon inspect 미확인 |
| arm64 manifest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` | 실제 daemon inspect 미확인 |
| npm tarball | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` | local static bytes 직접 일치; N05 host input path 부재 |
| Lock | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` | 계약/current files 일치 |
| Build record | `960b28e0699af5c6ac35709d2d14d7a8818ea8cfed0039f86b3b0217c68997ef` | `e6adeae1456771dce3e0d20acb3e231ceefd5e726a4c8bf554fc402f62ac8960` | historical record 값; actual host re-open 미확인 |
| Worker | `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b` | 동일 | current bytes 직접 일치; image 내부는 미확인 |

Controller candidate image는
`sha256:8ea6aad0328af475f0060809bf9bf642399edecee818cb9b771eb19ac635ac09`이나 최종 source로
rebuild/reinspect/refreeze해야 한다.

## Track A source와 원본 경로 연결

구현상 source equality는 다음 위치에서 강제된다.

- `track_a_admission.py:745-821`: pilot binding, N05 authorization
  `execution_source_revision`, N05 raw provenance와 pilot `source_revision`을 exact equality로 검사한다.
- `track_a_exploratory.py:635-725`: original pilot/N05/protocol을 다시 열고 execution manifest의
  source와 현재 clean source를 비교한다.
- `track_a_host_ledger.py:430-525`: retained Track A admission과 original pilot/N05 graph를 다시 열고
  host ledger source를 execution manifest에 결합한다.
- `scripts/track_a_container_controller.py:76-115`: controller 시작 전에 host ledger와 Track A
  execution을 다시 읽는다.

Unit 3 설계는 controller namespace가 다음 recorded absolute paths를 열 수 있어야 한다.

| 원본 | Code-level reopen | 실제 namespace mapping |
| --- | --- | --- |
| Track A host ledger | 구현·합성 검증 | 미검증 |
| Track A evidence root | 구현·합성 검증 | 미검증 |
| original pilot authorization | 구현·합성 검증 | 미검증 |
| N05 host ledger | 구현·합성 검증 | 미검증 |
| N05 Linux evidence | 구현·합성 검증 | 미검증 |
| protocol file | 구현·합성 검증 | 미검증 |

Digest-only fallback이나 격리 완화는 허용되지 않는다. 실제 Mac/controller volume/mount plan이
없으므로 현재는 **설계 확인**, 배치 검증은 **미완료**다. Unit 4는 20 host attempt terminal을 final
manifest/analysis에 연결하고 어느 host-ledger copy가 publication authority인지 정해야 한다.

## Attempt 소비와 실행 판정

승인 record read, invocation binding, clean source/executable digest 및 loaded host-code origin 검사는
host ledger와 Docker 접근 전에 수행된다. 이 단계의 거부는 attempt를 소비하지 않는다. 이 검사를
통과한 뒤 host ledger를 생성하는 순간 attempt 001이 소비된다. 이후 Docker identity/admission,
target, stderr 또는 cleanup에서 실패해도 같은 attempt를 재시도할 수 없다. N04의 consumed attempt나
경로도 재사용할 수 없다.

현재 authorization record, final clean source, controller image와 Mac/OrbStack environment가 없어
ledger를 만들지 않았다. N05 실행 상태는 **NOT_RUN**, 판정은 **없음**이다. PASS 또는 violation
0건으로 기록하지 않는다. 이후 N05가 PASS하더라도 별도 Track A pilot authorization은 여전히
필요하다.
