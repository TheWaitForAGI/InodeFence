# 추출기 대상 추가 체크리스트 v1 (#518)

> 상태: 설계 기록. 지금 구조에서 새 추출기 대상을 더하는 절차와 대상마다 정할 항목을 적는다. 근거는
> [경계 지도 v1](target-boundary-map-v1.md)(#537)이고 기준 커밋은 research/b-engine `0cf0b2d`다. 표의 내용은
> 코드 읽기로 확인했고 실행으로 확인한 것이 아니다.
> 구조 변경(컨트롤러 모드 등록 방식, 루프 통합)은 경계 지도 §5의 제안이며 **결정 안 됨**이다. 이 문서는 그것을
> 전제하지 않는다. 구조가 바뀌면 이 문서를 갱신한다.

표시:

- **[공유]**: 공유 실행 경로 파일(`scripts/launcher_guards.SHARED_PATH_FILES`)을 고친다. 사람(지웅) 결정이 필요하다.
- **[보호]**: 보호 파일(실행 백엔드, Docker 클라이언트, 격리 정책 모델)을 고친다. 사람 승인 없이 하지 않는다.
  지금 절차에는 이 단계가 없다.
- **[CI]**: `.github/` 저장소 설정이다.

## 1. 단계

| # | 단계 | 만들거나 고치는 것 | 표시 | 정해야 하는 것 |
| --- | --- | --- | --- | --- |
| 1 | 대상과 버전 축 | 이슈에 대상, 버전 범위, 실행 환경을 적는다 | — | 실행하지 않을 버전이 있는지, 버전 표기(정확한 버전, 패키지 접두 등) |
| 2 | 컨테이너 안 worker와 이미지 레시피 | `tools/<target>/`(Dockerfile, worker), 고정 base digest | — | 이미지 준비 방식(커밋된 lock, 공식 이미지 + producer, 레지스트리 생성 lock), identity로 쓸 값(worker 해시, 대상 소스 해시, 런타임 버전) |
| 3 | 대상 실행 어댑터 | `src/inodefence/targets/<target>_effect.py`. 단순하면 `targets/isolated.py`의 `IsolatedTarget`을 쓴다 | — | identity를 확인 전용 컨테이너에서만 볼지, 실행 컨테이너 안에서도 다시 볼지. 종료 코드 분류, 시간 제한, FAST 일정(`targets/identity_schedule.py`) 지원 |
| 4 | 케이스 파이프라인 | `src/inodefence/effect_pipeline_<target>.py` | — | 효과 스트림이 언제 complete인지, 미판정 규칙(USAGE 판정 표의 한 줄) |
| 5 | 탐색 루프 | 공통 `effect_campaign.run_effect_campaign`을 쓴다. 새 루프는 FAST·스트리밍·G1을 다시 붙여야 한다 | — | 지원할 보존·스케줄러 정책, `--mutation-policy`를 열지 |
| 6 | 컨트롤러 모드 | `scripts/run_effect_demo.py`(모드 상수, 인자, 검증), `scripts/container_controller.py`(모드 함수, 보고서 쓰기, 실패 시 보고서) | **[공유]** | 모드 이름, 받는 `DEMO_*` 인자, 예산 상한, 탐색 보고서 형식과 스트리밍 |
| 7 | 호스트 런처 | `scripts/local_<target>_*.sh` 새 파일(`scripts/launcher_bounded.sh`로 시간 제한), `drivers/launcher.launcher_path`, `drivers/runtime/shared_images.SKIP_BUILD_LAUNCHERS` | 새 파일은 목록 밖이지만 실행 경로라 같은 규칙으로 다룬다(D064) | 넘기는 환경 변수(FAST의 `DEMO_IDENTITY_CHECK_EVERY` 포함), 빌드 전용 실행(`BUILD_ONLY`) 지원 |
| 8 | 제품 드라이버 | `src/inodefence/drivers/<target>/`(adapter, explore, replay, 이미지 준비), `drivers/run_target.TARGETS` 한 줄 | — | `TargetAdapter` 필드, 대상 고유 옵션(`TargetOption`), 상속 환경 변수를 공통 헬퍼로 버리기 |
| 9 | 결과와 요약 | 보고서가 기존 세 모양 중 하나면 `drivers/explore_result`를 그대로 쓴다. 아니면 변환 함수 | — | result.json 축(`target_version`, `runtime_version`, `extraction_filter`), 미판정 상한, build-invalid 처리 |
| 10 | replay | `drivers/<target>/replay.py`, `case_replay` hook | 공통 replay 런처는 `local_node_tar_smoke.sh`(**[공유]**)다. 새 모드가 필요하면 [공유] | 같은 입력과 같은 이미지로 다시 돌리는 방법, 재현 판정 |
| 11 | 테스트와 fixture | `tests/`에 어댑터, 파이프라인, 드라이버, replay, 닫힌 실패 테스트. Docker 없는 추출 backend 하나. 기존 대상의 결과가 바뀌지 않음을 보이는 바이트 동일 fixture | — | 합성 fixture만 쓴다 |
| 12 | E2E와 CI | CI `product-e2e` 매트릭스 한 줄 | **[CI]** | 이미지 준비 시간, 네트워크 필요 여부 |
| 13 | 문서 | `docs/USAGE.md`(지원 환경 표, 판정 표, 탐색 예시), CHANGELOG [Unreleased], 주장 표 행 | — | 확인 수준 표시(demo run, exploratory) |

사람 결정이 필요한 지점은 6(항상)과 10(새 모드가 필요할 때)이다. 새 대상이 보호 파일을 고쳐야 한다면 설계를
다시 본다. 실행 백엔드가 Linux와 Docker JSON 모양에 묶인 것은 대상과 무관한 경계다(경계 지도 §2·§3).

## 2. 기존 네 대상의 대조표

| 항목 | node-tar | python-tarfile | decompress | oras-go |
| --- | --- | --- | --- | --- |
| identity로 확인하는 것 | Node·tar 버전, producer·lock·패키지 진입점·unpack 해시 | Python 버전, tarfile 해시, worker 해시 | 모듈, decompress 버전, Node 버전, worker 해시 | oras-go 버전, Go 버전, worker 해시 |
| 확인 전용 컨테이너 | STRICT는 케이스마다, FAST는 시작·200건마다·끝(D064) | 같음 | 같음(`IsolatedTarget`) | 같음(`IsolatedTarget`) |
| 실행 컨테이너 안 재확인 | 있음(worker가 추출 전에 해시를 다시 계산) | 없음 | 없음 | 없음 |
| 탐색 루프 | 공통 | 공통 | 자체(`decompress_effect_campaign`) | 자체(`oras_go_effect_campaign`) |
| 탐색 보고서 형식 | 스트리밍 `aggregate` + 위반 케이스 | `case_records`, 스텝은 메모리에 두지 않음(#542) | campaign 스키마 1, `steps` 포함 | campaign 스키마 1, `steps` 포함 |
| 예산 상한 | 없음(explore 모드) | 2000 | 2000 | 2000 |
| 실행 중 진행(`inodefence status`) | 있음 | 없음 | 없음 | 없음 |
| `--mutation-policy` | v2 정책 한 값 | 거부 | 거부 | 거부 |
| FAST(D064) | 있음 | 있음 | 있음 | 있음 |
| 대상 고유 옵션 | — | `--extraction-filter`(탐색은 `data`만) | 버전 칸에 패키지 접두 | 아티팩트 디렉터리 배치 |
| replay | 있음 | 있음 | 있음 | 있음 |

차이가 드러나는 곳:

- 실행 컨테이너 안 재확인은 node-tar만 한다. 그래서 FAST에서 확인 전용 컨테이너를 건너뛴 케이스의 케이스별
  identity 관찰은 node-tar에만 있다(D064).
- 예산 상한 해제는 node-tar만이다. 상한은 공유 실행 경로 파일에 있다(#542).
- decompress·oras-go 보고서에는 케이스별 feedback 키가 없다. FAST·STRICT 비교 도구가 이 두 대상을 축소
  판독기로 읽는 이유다.

## 3. 새 대상의 기본값 제안 (결정 안 됨)

아래는 지금 구조에서 중복을 늘리지 않는 선택이다. 대상마다 이슈에서 정한다.

1. 루프는 공통 `run_effect_campaign`을 쓴다(5). 스트리밍, FAST, G1, exploration_policy가 그대로 붙는다.
2. 실행 컨테이너 안에서 identity를 다시 확인할 수 있으면 한다(3). FAST에서 케이스별 identity 관찰이 남는다.
3. 보고서는 node-tar의 스트리밍 모양을 따른다(6·9). 결과 변환 분기가 늘지 않는다.
4. 상속 환경 변수(`DEMO_MUTATION_POLICY`, `DEMO_POLICY`, `DEMO_IDENTITY_CHECK_EVERY`)는 공통 헬퍼로 버린다(8).
5. 닫힌 실패 테스트를 처음부터 둔다(11): identity 불일치(중간·끝), 런처 비정상 종료, 보고서 없음 → 결과 없이
   종료 2.
