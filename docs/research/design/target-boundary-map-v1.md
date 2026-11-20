# 대상·운영체제·CPU 구조·런타임 경계 지도 v1 (#537)

> 상태: 설계 기록. 코드 읽기로 만든 지도이며 실행으로 확인한 내용이 아니다. 기준 커밋은 research/b-engine
> `0cf0b2d`이고 줄 수는 그 커밋의 `wc -l` 값이다. 구조 변경 제안(§5)은 **결정 안 됨**이다.
> 새 대상을 더하는 절차는 [대상 추가 체크리스트 v1](target-addition-checklist-v1.md)에 있다.
> 관련 이슈: #518(일반성), #536(FAST), #515(백엔드 메모리), #517(node-tar 옛 주 버전).

## 1. 대상 축

대상 축이 가장 넓게 퍼져 있다.

| 층 | 대상마다 있는 것 | 공통으로 묶는 곳 |
| --- | --- | --- |
| 제품 드라이버 | `drivers/<target>/`(어댑터, explore, replay, 이미지 준비). 줄 수: node-tar 1,178, python-tarfile 1,147, decompress 1,548, oras-go 1,594 | `drivers/run_target.py`의 `TARGETS`(대상 이름 → 어댑터 경로)와 `TargetAdapter` 인터페이스 |
| 대상 실행 어댑터 | `targets/<target>*.py`, 컨테이너 안 worker(`targets/_node_effect_producer.cjs`, `tools/<target>/`) | `targets/isolated.py`의 `IsolatedTarget`(decompress·oras-go가 씀), `targets/identity_schedule.py` |
| 케이스 파이프라인 | `effect_pipeline.py`(node-tar), `effect_pipeline_python_tarfile.py`, `effect_pipeline_decompress.py`, `effect_pipeline_oras_go.py` | `runtime.disposable_sandbox`, `observer.capture_state`, `oracle` |
| 탐색 루프 | node-tar·python-tarfile은 공통 `effect_campaign.run_effect_campaign`. decompress(`decompress_effect_campaign.py`, 663줄)와 oras-go(`oras_go_effect_campaign.py`, 565줄)는 각자의 루프 | `campaign_hooks.CampaignHooks` |
| 컨트롤러 모드 | `scripts/run_effect_demo.py`의 모드 상수 4개와 인자 검증, `scripts/container_controller.py`의 모드별 함수 | 두 파일 모두 공유 실행 경로 파일(`scripts/launcher_guards.SHARED_PATH_FILES`) |
| 호스트 런처 | `scripts/local_node_tar_smoke.sh`(540줄, 공유 실행 경로), `local_python_tarfile_explore.sh`(130), `local_decompress_selfdiscover.sh`(151), `local_oras_go_selfdiscover.sh`(152) | `drivers/launcher.launcher_path`, `drivers/runtime/shared_images.SKIP_BUILD_LAUNCHERS` |
| 결과 | 없음(공통) | `drivers/explore_result.build_campaign_result`. decompress·python-tarfile은 감싸는 변환이 더 있다 |
| 실행 중 진행 | node-tar만 `LiveRecorder`를 쓴다(`inodefence status`의 실행 중 수치). 나머지 셋은 실행 중 `?` | `live_exploration.py` |

대상 고유 로직이 공통 모듈에 들어간 곳:

1. 공유 실행 경로 파일 `scripts/run_effect_demo.py`와 `scripts/container_controller.py`에 대상별 모드, 인자 검증,
   보고서 키가 있다. 예: oras-go 아티팩트 배치 인자, python-tarfile 모드 분기, node-tar 전용 버전 검증.
2. `drivers/explore_result.py`는 대상 이름이 아니라 보고서 모양으로 갈라진다. 보고서 모양은 셋이다.
   - node-tar: 스트리밍 `aggregate` + 위반 케이스
   - python-tarfile: `case_records`
   - decompress·oras-go: 대상별 campaign 스키마 1(`steps` 포함)
3. 탐색 루프 둘(decompress·oras-go)이 공통 루프 밖에 있다. 그래서 FAST, 스트리밍, exploration_policy 같은 공통
   기능을 대상마다 다시 붙인다(#542의 decompress·oras-go 결정이 그 예).
4. `effect_demo.render_effect_campaign_summary`에 `case_records` 보고서 분기가 있다(#542, 보고서 모양 기준).

## 2. 운영체제·CPU 구조 축

이 축은 좁게 묶여 있다.

- 실행 경계는 Linux만이다. 실행 백엔드 `execution/container.py`가 Linux가 아닌 호스트와 root 실행을 거부하고,
  Docker 서버와 이미지의 `Os`가 `linux`인지 확인한다. 이 파일은 보호 파일이다.
- CPU 구조로 갈라지는 코드는 없다. 이미지는 각 호스트의 Docker가 그 구조로 빌드하거나 가져온다.
  - 기록된 환경: WSL2 x86_64, Ubuntu arm64 VM(D049 조건 6), OrbStack Linux arm64(`execution/README.md`).
  - 구조 차이가 결과에 들어오는 길: 이미지 ID는 구조마다 다르다. node-tar 결정성 주장은 같은 호스트에만 한다
    (`local_node_tar_smoke.sh` 머리 주석).
- 런타임 버전 축은 python-tarfile만 명시적이다(`--version`이 Python 런타임이고 어댑터가 실제 버전을 확인한다).
  node-tar는 Node 버전을 이미지 identity의 일부로 확인한다(`targets/node_tar_effect.py`).

## 3. 컨테이너 런타임 축

- Docker CLI 하나에 묶여 있다.
  - 브로커가 호출마다 `docker` 프로세스를 띄운다: `scripts/container_host.py`(공유), `execution/docker_client.py`(보호).
  - context 선택: `INODEFENCE_DOCKER_CONTEXT`, `drivers/runtime/shared_images.docker_context`,
    `run_parallel_native.py --context`.
- Docker Desktop 전제는 코드 분기가 아니라 안내 문구에 있다: `drivers/run_target.py`·`cli.py`의 메모리 UNKNOWN
  설명, `abort_classification.py`의 WSL2 생성 직렬화 설명, `execution/start_gate.py`의 WSL drvfs/9p 설명.
- 네이티브 Docker Engine 기록: arm64 VM 기록, CI의 `container-integration`·`product-e2e` job.
- Podman 같은 다른 런타임은 지원하지 않는다. 브로커가 docker CLI 인자와 `docker inspect` JSON 모양에 묶여 있고,
  생성 직후 정책 대조(`execution/container.py`)가 Docker JSON 키를 읽는다. 바꾸려면 보호 파일을 고쳐야 한다.

## 4. 다른 이슈와의 관계

- #536 방안 1(D064)은 대상 어댑터 층(`targets/`)에서 끝났다. 전달 통로가 없어 실행 경로 6파일에 승인된 줄을
  더했다. 그중 3개가 공유 실행 경로 파일이다.
- #536의 다른 방안(한 컨테이너 여러 케이스, 컨테이너 풀)은 보호 파일(실행 백엔드, 격리 정책 모델)에 묶여 있다.
  축 구조와 관계없이 격리 계약 변경이다.
- #515(컨테이너 생애 수에 비례하는 메모리)는 런타임 축(Docker Desktop 백엔드)의 문제다. 네이티브 Engine에서
  같은 현상이 있는지는 기록이 없다.
- #517(node-tar 옛 주 버전): producer(`targets/_node_effect_producer.cjs`)는 node-tar의 `unpack` 모듈 경로와 API를
  가정하고 그 해시를 identity로 확인한다. 옛 주 버전은 모듈 배치가 달라 producer와 레시피
  (`targets/node_tar_recipe.py`, `drivers/node_tar/registry_prepare.py`)를 고쳐야 할 것으로 읽힌다. 이것은 코드
  읽기에서 나온 추론이며 실행으로 확인하지 않았다. 실행이 금지된 버전 범위는 운영 규칙을 따른다.

## 5. 중복을 줄이는 구조 변경 제안 (결정 안 됨)

이 문서 범위 밖이다. 각각 사람 결정이 필요하다.

1. **컨트롤러 모드 등록 방식.** 모드 상수, 인자 검증, 모드 함수를 대상 패키지의 컨트롤러 진입점 하나로 받는다.
   공유 실행 경로 파일을 한 번 고친 뒤에는 새 대상이 공유 파일을 고치지 않게 된다. 결정 안 됨.
2. **decompress·oras-go 루프를 공통 루프로.** 두 대상은 공통 루프가 받는 순서 있는 효과 trace를 실행 경계 안에서
   만들지 못한다(`decompress_effect_campaign.py` 모듈 설명). 그래서 이 안은 공통 루프에 다른 신호원을 받는
   추상을 더하는 엔진 재설계가 되고, 보고서 형식도 바뀐다. 결정 안 됨.
3. **런처 넷을 매개변수화된 하나로.** 대상별 차이는 모드 이름과 환경 변수 몇 개다. 공유 실행 경로와 런처라
   1과 함께 결정한다. 결정 안 됨.
