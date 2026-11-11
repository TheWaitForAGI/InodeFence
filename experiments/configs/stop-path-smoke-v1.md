# 정지·재개 실측 smoke v1 (D042)

**상태:** 초안(사전 고정 전). 판정 기준을 이 파일로 고정하고, 이 파일의 sha256을 D042 "sha `[동결 시 기입]`" 자리에 적는다. 결과를 보기 전에 고정한다.
**승인:** 이 파일 PR의 머지가 지웅 승인이다. 주입 수단을 D042 원문(없는 docker context)에서 아래 §2로 바꾸는 것도 이 머지로 승인된다. 검증자는 W4다.
**라벨:** `demo run`. 비등록 엔지니어링 smoke이고, 결과는 봉인하며 EXP-3·EXP-2·파일럿 통계에 합치지 않는다(D042 "집계").

## 1. 근거와 범위

근거는 [D042 정지·재개 실측 smoke](../../docs/DECISIONS.md)다(원문을 바꾸지 않는다).

| 항목 | 값 | 출처 |
| --- | --- | --- |
| 셀 | R/D/S-u × seed 6101~6104 = 12셀, budget 20 | D042 :923 |
| 동시 실행 | jobs 2 | D042 :923 |
| 출력 | 차수별 전용 폴더 `stop-path-smoke-1-<날짜>`, `stop-path-smoke-2-<날짜>` | D042 :932 |
| 실행 횟수 | 2회. 1차는 수정 HEAD, 2차는 최종 `engine_sha` 후보에서 동결 전 | D042 :929-931 |
| 원장 | 차수별로 기록하고, `exposure_ledger_sha256`은 2차 뒤 고정 | D042 :932 |
| 재개 | 매 재개마다 W2 원인 LOG와 지웅 별도 승인 | D042 :913, :933 |
| 호스트 | HOST1, 오케스트레이터 승인 후 | 오케스트레이터 지시 2026-11-11 |

**시점 읽기.** D042 원문의 "벤치마크 종료와 동결 해제 뒤"(:924, :930)는 "통합 후보 확정 뒤"로 읽는다. D047로 동시 실행 벤치마크가 본실험 선행 조건에서 빠졌기 때문이다.

**원문 표 부재.** D042 :928은 "원본은 설계 §5 표, 다르면 표가 맞다"라고 하지만, 그 표는 저장소의 어느 커밋에도 없다(`git log --all -S`로 확인, 2026-11-11). 따라서 이 파일은 D042 :928의 짧은 이름을 원문으로 삼는다. 이름만으로 판정식이 정해지지 않던 4건(A3·A7·B9·C1, F1 적용 범위)은 W4 검증(2026-11-11)과 오케스트레이터 확정 문장으로 §6에 고정했다.

## 2. 주입 수단 변경 (D042 원문 → 이 파일)

D042 원문의 주입 수단은 셀 프로세스에 존재하지 않는 docker context를 넘겨 `prepare controller` 단계에서 실패시키는 것이다(기준 A6·A8이 이를 전제로 쓰였다). 현재 런처에서는 다음 세 가지 이유로 이 방법이 D042의 Guard 경로(연속 3셀 무기록 → 정지)를 타지 못한다. 모두 코드 읽기로 확인했다.

1. **`--context <없는 이름>`:** `scripts/run_exp0.py`는 `--context`를 셀 env(`INODEFENCE_DOCKER_CONTEXT`)뿐 아니라 등록 게이트의 엔진 확인(`host_mismatches` → `docker_engine_version(args.context)`)과 host preflight(`guard_docker(args.context)`)에도 쓴다. 그래서 셀 0개로 거부된다. 이 동작은 올바르므로 그대로 둔다.
2. **런처 환경 변수 `INODEFENCE_DOCKER_CONTEXT=<없는 이름>`(`--context` 생략):** 셀에만 전달되지만, smoke의 `volume create`가 실패한 뒤 trap이 같은 context로 volume 부재를 확인하지 못해 U를 기록한다(#334 L1, volume 생성 시도 플래그). 그러면 첫 셀에서 게이트 정지가 된다. 이 경로는 §5 시나리오 A로 따로 확인한다.
3. **`INODEFENCE_EVIDENCE_DIR`을 쓰기 불가 경로로(오케스트레이터 1차 채택안):** `scripts/run_parallel_native.py`의 `cell_env`가 셀마다 `INODEFENCE_EVIDENCE_DIR=<출력 경로>`로 덮어쓴다. 그래서 런처 환경 변수로 준 값이 셀에 닿지 않는다. 또 단일 target인 targets 형식에서는 증거 경로가 출력 루트(런처가 `cell-results.jsonl`을 쓰는 곳)라 디렉터리를 쓰기 불가로 만들 수도 없다.

**채택 수단(시나리오 B): 런처 환경 변수 `HISTORICAL_IMAGE=inodefence-node-tar-effect:does-not-exist`**(`--context` 없음). 동작은 다음과 같다.

**D042 :925 사전 확인(W1)의 대응 문장:** HISTORICAL_IMAGE가 셀 단계에 전달되고, 셀 프로세스에 한정되며, 전역 context와 preflight 대상이 바뀌지 않는다(근거: 아래 "전달 범위"·"host 가드", 코드 읽기).

- **전달 범위:** 이 변수는 `scripts/local_node_tar_smoke.sh`만 읽는다(:403). `run_exp0.py`·`cell_env`·host preflight·`--expected-images`는 읽지 않는다(저장소 검색 결과 smoke 외 사용 없음). `base_env = dict(os.environ)`으로 셀 프로세스에만 전달되며, 전역·런처 docker context는 바뀌지 않는다(docker CLI는 `DOCKER_CONTEXT`만 읽는다).
- **실패 지점:** `local_node_tar_smoke.sh:404` `IF_HISTORICAL_IMAGE="$(dk image inspect "$HISTORICAL_IMAGE" ...)"`. 이것은 **로컬 조회**다. `docker image inspect`는 레지스트리 pull을 하지 않고 네트워크 호출도 없다. 이 태그로 `create`·`run`·`pull`을 하는 코드는 없다(실패가 먼저 난다). 이 줄은 `prepare controller`(:370) 다음 단계인 `effect-demo-historical`에 있다.
- **host 가드:** preflight·postflight가 보는 이미지는 등록 파일의 대상 태그(`inodefence-node-tar-effect:<version>`)와 controller·helper뿐이다(`run_exp0.guard_images`). 주입한 태그는 보지 않으므로 preflight는 통과하고, "이미지 변화"로 기록되지도 않는다.
- **스크래치 가짜 docker로 확인함, 실 docker는 미확인(2026-11-11):** 실제 smoke 스크립트를 `demo-historical` 모드, 게이트 env와 함께 돌렸다. 결과:
  - exit 1, `FAILED at step: effect-demo-historical`, UNKNOWN 표식 0
  - volume과 controller가 생성된 뒤 제거되고 부재가 확인됨, 남은 자원 0
  - 증거 파일 0(무기록), 게이트 판정 S
  - host broker 미실행이라 target 컨테이너 0이고 `.calls.jsonl`도 없음

## 3. 실행 구성

- **등록 파일:** targets 형식(InfrastructureGuard와 StartGate는 이 형식에서만 돈다), target 1개(node-tar 7.5.2, 등록 digest), arm R-restart·D·S-u, seed 6101~6104, budget 20. 파일 이름은 `experiments/configs/stop-path-smoke-<차수>-v1.md`(차수별, D042 :932; D042는 위치를 정하지 않고, 비등록 실행은 `experiments/configs`에 두는 관례를 따른다. 2c60d49의 `experiments/preregistration/`에서 2026-11-11 실행 전 변경). R arm은 `arm.R = unretained-seed-restart-v1-uniform-mutation-v1`(D040-D6, exp3-v1 등록 :30-31, 코드 상수 `src/inodefence/feedback/effect_search.py:62` `R_UNRETAINED_SEED_RESTART`)이다. EXP-3 등록과 같은 값이다(D042는 R 변형을 따로 정하지 않는다).
- **런처 인자(양 시나리오 공통):** `--jobs 2 --output <전용 출력> --skip-build --expected-images <기준 파일>`. `--host-id`는 쓰지 않는다(2호스트 실행이 아니다). `--expected-images`는 넘겨서 이미지 거부 경로도 함께 확인한다.
- **기대 이미지 파일:** 저장소에 커밋하지 않고 각 출력 폴더에 둔다(`<출력>/expected-images.json`). 내용은 `expected_image_ids` 3개(대상·controller·helper)이고, 값은 실행 직전 읽기 전용 `docker image inspect`로 확인한다. 파일의 sha256은 preflight 기록의 `expected_images`에 남는다.

## 4. 시나리오 B (D042 본래 목적, Guard 경로)

| 단계 | 명령(요지) | 기대 |
| --- | --- | --- |
| B-0 사전 | 잔존 리소스 0, 다른 실험 없음, 출력 폴더 없음 | preflight 통과 |
| B-1 주입 | `HISTORICAL_IMAGE=inodefence-node-tar-effect:does-not-exist python scripts/run_exp0.py … --jobs 2` | 셀마다 2시도 모두 무기록 → 셀이 끝나는 순서로 무기록 3셀 → `infrastructure-stop` 1줄, 새 시작 없음, 실행 중 시도는 완주, 호출은 스스로 끝남 |
| B-2 플래그 없는 호출 | 주입 없이 `python scripts/run_exp0.py …`(재개 플래그 없음) | 셀 시작 0 |
| B-3 원인·승인 | W2가 원인을 LOG에 적는다(oracle 값 없이). 오케스트레이터가 지웅에게 §8 문구로 요청한다 | 승인 참조 확보 |
| B-4 승인 재개 | 주입 없이 `… --resume-after-stop <승인 참조>` | `infrastructure-resume` 줄(approval_ref)과 나머지 셀 진행. no-record 셀은 다시 돌리지 않음 |
| B-5 완주·멱등 | 같은 인자로 한 번 더(재개 플래그 없음), 그리고 `--summarize-only` | 새 시작 0, 기록 불변 |

**abort-pending 없음:** targets 형식에는 `abort-pending` 상태가 없고(셀 상태는 complete·abort-final·record-inconsistent·unattempted·no-record, `cell_completeness.py:42`), `--finalize-abort`는 targets 등록에서 거부된다(`run_exp0.py:1056-1059`). abort 기록은 종료 기록으로 바로 분류된다. 따라서 B-5 전 finalize 단계는 없다. 판정 도구는 B5에서 `abort-pending`을 보면 targets 형식 실행이 아니라고 근거 키로 알린다.

B-2·B-4·B-5 각 호출 직전에 `env | grep -c '^HISTORICAL_IMAGE='`의 결과(0이어야 함)를 실행 기록에 남긴다(§6 X3).

## 5. 시나리오 A (추가 확인, D042 기준 밖 — 게이트 정지와 ack 재개)

목적: 2026-11-11에 생긴 경로("cleanup unknown → 게이트 U → 정지 → `approval=` ack → 승인 재개")가 실 docker에서 도는지 확인한다. 이 시나리오의 결과는 D042 21개 판정에 넣지 않는다. 방법론상 문제가 없는지는 W4 검증에서 본다.

- **주입:** 런처 환경 변수로만 `INODEFENCE_DOCKER_CONTEXT=does-not-exist`를 주고 `--context`는 생략한다. 셀 수를 최소로 하기 위해 별도 출력 폴더를 쓰고, 등록은 시나리오 B와 같다(budget 20).
- **원장 구분:** 시나리오 A는 별도 출력 폴더와 별도 원장 행을 쓴다. 정지 구간에서는 셀이 대상을 실행하지 않는다(volume 생성 실패, 노출 없음). ack 재개 뒤 실행된 셀만 seed 6101~6104를 노출한다. A와 B는 원장에 따로 적는다(§7).
- **판정상 위치:** A의 결과는 21개 판정과 합격에 넣지 않는다. 다만 A가 FAIL이면(특히 SA3: U 상태에서 재개가 거부되지 않음, SA6: 잔존 리소스) 본실험 금지 사유로 올린다.
- **승인과 ack:** 지웅의 재개 승인은 시나리오 A에 1회다. 그 승인 참조 하나로 게이트 판정 U인 셀을 **모두** ack한다(각 ack note의 `approval=`에 같은 참조). 이 주입(`INODEFENCE_DOCKER_CONTEXT=does-not-exist`)은 모든 셀을 같은 이유로 실패시키므로, jobs 2에서는 두 worker의 첫 셀이 모두 U가 되는 것이 보통이다.
- **ack 전 잔존 확인:** ack 전에 읽기 전용 잔존 확인(`docker ps -a --filter name=inodefence-`, `docker volume ls --filter name=inodefence-local-`)의 결과를 ack note `residual=`에 반드시 남긴다.

| # | 확인 | 판정 근거 |
| --- | --- | --- |
| SA1 | 첫 셀에서 정지 | `infrastructure-stop` 1줄, reason에 `cleanup unknown` 또는 `start gate denied`. 정지 줄 앞의 start 줄은 (a) 게이트 판정 U인 셀(1개 이상, 각 1회), (b) 게이트 판정 S로 끝난 셀, (c) 끝 줄에 `start_denied`가 있는 시도뿐이다. U 셀 수와 (c)의 수의 합은 jobs 이하다. (b)의 start 줄은 가장 이른 U 셀의 end 줄보다 앞에 있고, 그 end 줄 뒤의 start 줄은 모두 (c)다. 시작한 셀의 총수에는 상한을 두지 않는다. U 커밋과 그 end 줄 사이의 시작 거부는 게이트 lock으로 보장되며 줄 순서로는 확인되지 않는다. |
| SA2 | 이후 시작 0 | 정지 줄 뒤 `start` 줄 0 |
| SA3 | U 상태에서 재개 거부 | `--resume-after-stop <ref>`가 exit 2이고 stderr에 `start gate still closed` |
| SA4 | ack 뒤 재개 허용 | 게이트 판정 U인 셀 **각각**에 `start_gate.py ack <dir> <cell> "approval=<ref>; checked_at=…; by=…; residual=<읽기 전용 명령 → 결과>; reason=…"`(모든 ack에 같은 승인 참조) 뒤 재개 exit 0 |
| SA5 | 재개 기록 | `infrastructure-resume` 줄에 `approval_ref`와 `gate_acks`(path, cell, note_sha256). `gate_acks` 수 ≥ U 셀 수이고 모든 U 셀이 들어 있음 |
| SA6 | 잔존 리소스 0 | 각 호출 뒤 `docker ps -a --filter name=inodefence-`, `docker volume ls --filter name=inodefence-local-` 비어 있음, host postflight `problems` 비어 있음 |

## 6. 판정 기준 대응표 (D042 :928의 21개 + 이 주입에 따른 추가 3개)

표기: **그대로**는 원문 의미를 그대로 적용(판정식이 원문 이름만으로 정해지지 않던 기준은 "해석 확정"·"판정식 확정"으로 표시), **대체**는 주입 변경에 맞게 대체 문구 적용, **추가**는 이 주입 때문에 새로 둔 기준. 기준을 빼지 않는다. 근거 파일은 시나리오 B 출력 폴더 기준이다.

| # | D042 원문(:928) | 적용 | 판정식(근거 파일·필드) |
| --- | --- | --- | --- |
| A1 | 정지 기록과 스스로 종료 | 그대로 | B-1 호출의 `cell-results.jsonl`에 `event = infrastructure-stop` 정확히 1줄. 호출 exit가 정상 종료(0 또는 1, 신호 아님). `summaries/index.json` `cell_completeness.infrastructure_stopped = true` |
| A2 | no-record 3 또는 4 | 그대로 | B-1 뒤 `cell_completeness.no_record ∈ {3, 4}` |
| A3 | 각 2시도·즉시 재시도·파일 보존 | 그대로(해석 확정) | no-record 셀 X마다 (i) attempt 1·2의 `start` 줄이 같은 호출 안에 있음 (ii) attempt 2 `start`가 X의 attempt 1 `end` 뒤이고, 그 사이 다른 셀의 `start` 줄이 jobs−1 = 1개 이하(시간 상한 없음 — `wait_for_cleanups` 대기는 정상). 그 셀이 `matrix.json` `disk_pauses`에 있으면 (ii)는 해당 없음으로 보고한다(디스크 대기는 재시도 전 간격을 늘린다) (iii) `attempts/<X>.attempt1.*`의 sha256이 B-1 직후와 B-5 뒤에 같음 |
| A4 | 시작 셀 3 또는 4, 나머지 시작 줄 없음 | 그대로 | `start` 줄이 있는 셀 수 ∈ {3, 4}. 나머지 셀은 `start` 줄 0이고 `matrix.json` `cells_not_started`에 있음. 런처는 첫 시도만 끝난 A5 셀도 `cells_not_started`에 넣는다(판정 도구는 이미 그렇게 판정한다) |
| A5 | 첫 시도만 끝난 셀 0 또는 1 | 그대로 | `start` 줄이 정확히 1개이고 `end`가 있는 셀 수 ∈ {0, 1} |
| A6 | 컨테이너·볼륨 생성 0, context 불변 | **대체** | 원문은 `prepare controller` 실패를 전제로 한다. 이 주입에서는 volume과 controller가 생성된 뒤 정리된다. 대체: "B-1 뒤 잔존 리소스 0(X2), 전역 docker context 불변(`docker context show`가 실행 전후로 같음), 그리고 모든 no-record **시도**(셀이 아니라 시도마다)의 게이트 판정이 S이고 각 시도 로그에 정리 trap 실행 흔적(controller·volume 제거)이 있음(X1 포함)" |
| A7 | 결과 가림과 manifest | 그대로(판정식 확정) | (i) B-1·B-2 뒤, 그리고 정지 중 모든 호출 뒤: `summaries/index.json`에서 `outcomes_redacted = true`, `interim.redacted = true`, `interim.reasons`가 비어 있지 않음. `cells[]` 어느 항목에도 `hit`·`t_first`·`t_first_event`·`t_first_censored` 키가 없고 모든 `summary`가 null. `summaries/*.summary.json` 파일 0개(근거: `run_exp0.py` 가림 사유와 `_remove_summaries`, `run_g1_smoke.py` 요약기). (ii) B-5 뒤: `manifest-verification.json`의 `raw_manifest.generated = true`, `verification.verified = true`, 그리고 index의 `interim.manifest`가 `{generated: null, verified: null}`(성공 경로; 런처는 index를 manifest 생성 전에 null로 쓰고 실패 때만 다시 쓴다, `run_exp0.py:1972`, `:2005`, `:2008-2022`), B-5 뒤 같은 manifest에서 `manifest-verification.json` 줄을 뺀 사본으로 `make_raw_manifest.py --verify`를 돌려 exit 0. 그 파일은 manifest 생성 뒤 런처가 다시 쓰는 기록이라 비교에서 뺀다(C1 예외 3개 중 생성 뒤 바뀌는 유일한 파일). (iii) 확인은 키 존재·개수만 출력하는 스크립트(`scripts/check_stop_path_smoke.py`)로 하고, 값(hit·T_first)은 사람이 열람하지 않음 |
| A8 | 로그 `FAILED at step: prepare controller`, `engine=` 빈 값 | **대체** | 대체: no-record 시도의 셀 로그에 `FAILED at step: effect-demo-historical`과 `No such image: inodefence-node-tar-effect:does-not-exist`가 있음. `engine=` 값은 비어 있지 않음(context가 정상) |
| N1 | 플래그 없는 호출은 시작 없음 | 그대로 | B-2 호출 전후로 `start` 줄 수 불변, exit 0 또는 1(신호 아님; 정지 중에는 no-record 셀 때문에 G1 판정이 통과하지 못해 1이 정상), stderr에 `infrastructure stop in effect` |
| P1 | 재개 전 W2 원인 LOG와 지웅 승인 | 그대로 | `docs/LOG.md`에 원인 줄(oracle 값 없음)이 있고, 그 커밋 시각이 B-4 `infrastructure-resume` `clocks.realtime`보다 앞섬. 지웅 승인 참조가 존재 |
| B1 | 승인 참조 기록 | 그대로 | `infrastructure-resume.approval_ref`가 §8 형식이고 index `cell_completeness.infrastructure_resumes`에 같은 값 |
| B2 | 재개 뒤 정지 해제·정지 기록 유지 | 그대로 | B-4 뒤 `infrastructure_stopped = false`, B-1의 `infrastructure-stop` 줄이 그대로 남음(줄 수·내용 동일) |
| B3 | no-record 셀 재실행 없음 | 그대로 | A2 셀들의 `start` 줄이 B-4 뒤에도 2개(늘지 않음) |
| B4 | 남은 시도 유지 | 그대로 | A5에 해당하는 셀은 B-4에서 attempt 2만 시작 |
| B5 | 나머지 셀 complete 또는 abort-final | 그대로 | B-4 뒤 no-record 셀을 뺀 셀의 상태가 모두 `complete` 또는 `abort-final`(`summaries/index.json` 셀 상태) |
| B6 | `.calls.jsonl`과 시계 | 그대로(범위 주석) | B-4에서 실행된 셀마다 `<evidence>.calls.jsonl` 존재. `start`·`end` 줄에 `clocks`(realtime·monotonic) 존재. no-record 시도는 host broker를 실행하지 않으므로 `.calls.jsonl`이 없는 것이 정상 |
| B7 | append-only | 그대로 | 단계마다 `cell-results.jsonl`의 앞부분 바이트가 이전 단계 파일과 같음(접두 일치) |
| B8 | `cell_completeness` 집계 | 그대로 | B-5 index의 `cell_completeness` 수치(complete·aborts·no_record·unattempted)를 `cell-results.jsonl`과 셀 파일에서 다시 계산한 값과 일치 |
| B9 | invalid 경로와 분석기 정상 종료 | 그대로(판정식 확정) | "invalid 경로" = no-record 셀이 invalid로 처리되는 경로(런처가 no-record·record-inconsistent 셀을 `invalid_cells`로 넘기고, 요약기가 index 항목에 `invalid = true`, summary 파일에 `invalid_reason`이 `no-record:`를 포함(실제 값은 `ReportFormatError: no-record: …`)하고 `summary = null`로 기록). 판정식: (i) B-5 index에서 `invalid = true`인 셀 집합이 A2의 no-record 셀 집합과 정확히 같고 `invalid_count`도 그 수 (ii) `interim.integrity_problems`가 비어 있음 (iii) `scripts/analyze_exp0.py --index <B-5 index> --format json --output <파일>`이 exit 0이고 출력에 대비별 `number_blocks_invalid_excluded` 키가 있음(값은 열람하지 않고 키 존재만) |
| C1 | 멱등 | 그대로(판정식 확정) | B-5 두 번째 호출 전후로 `cell-results.jsonl`, 셀 증거 파일, `attempts/`, 시작 게이트 디렉터리, `host/` 기록, `summaries/index.json`, `summaries/*.summary.json`이 바이트 동일하고 새 `start` 줄이 0이다. raw manifest는 `registration.json`·`matrix.json`·`manifest-verification.json` 세 줄을 뺀 나머지 줄이 동일하다. 예외 파일은 이 세 개뿐이다. 할 일이 없는 호출은 host preflight·postflight를 쓰지 않으므로 `host/`에 새 기록이 생기면 FAIL. 다르면 FAIL이고 다른 파일을 기록하며, 사후에 허용 목록을 늘리지 않음 |
| F1 | PR-D 요약 필드 | 그대로(**매 차수 적용**, 확정) | D042의 "1차 해당 없음"은 삭제한다(PR-D가 이미 통합 트리에 있다). B-5 뒤(가림 해제): invalid가 아닌 모든 셀의 `summaries/<run_id>.summary.json`에 `dense_detail` 키가 있음, invalid 셀의 summary에는 `dense_detail` 키가 없고 `invalid_reason`에 `no-record:`가 들어 있음(요약기는 가림이 아니면 invalid 셀을 포함한 모든 셀의 summary를 쓰고 `dense_detail`은 정상 적재 뒤에만 붙인다, `run_g1_smoke.py:367`, `:409-413`), `record_inconsistent_prefix`는 record-inconsistent 셀에만 있음(0개 예상). 어긋나면 해당 차수 FAIL(1차 FAIL이면 원인 수정 뒤 2차 필수). 키 존재만 확인 |
| X1 | (추가) 주입 시도의 정리 확인 S | 추가(A6에 포함) | no-record **시도**마다 게이트 판정이 `S`(U 0)이고, 셀마다 controller destroy 이벤트가 시도 수(2) 이상(`host/events.jsonl`). `host/recorder-failures.jsonl`이나 `matrix.json` `host_guards.recording_notes`에 events 수집기 실패가 있으면 destroy 수 대신 시도 로그로 판정하고 그 사실을 보고한다: 로그에 `FAILED cleanup`과 `INODEFENCE_CLEANUP_UNKNOWN:`이 없음(정리 trap은 성공 때 로그를 남기지 않고, S는 trap이 정리를 확인한 뒤에만 쓴다) |
| X2 | (추가) 잔존 리소스 0 | 추가 | 각 단계 뒤 `docker ps -a --filter name=inodefence-`와 `docker volume ls --filter name=inodefence-local-`가 비어 있고, host postflight `problems`가 비어 있음 |
| X3 | (추가) 주입 해제 확인 | 추가 | B-2·B-4·B-5 각 호출 직전 `env`에 `HISTORICAL_IMAGE` 없음(기록). 재개 뒤 실행된 셀의 로그·report가 등록 대상 이미지를 쓰고, 그 호출의 preflight `image_ids`가 기대값과 같음 |

**합격:** 위 표의 21개와 추가 3개(X1~X3)가 모두 PASS다. 표에 "확인 필요"로 남은 기준은 없다(A3·A7·B9·C1·F1은 W4 검증과 오케스트레이터 확정 문장으로 고정, 2026-11-11). 시나리오 A(§5)는 합격에 넣지 않는다. 판정은 `scripts/check_stop_path_smoke.py`(snapshot·verify-tools·judge)로 한다.

**정정 이력(2026-11-11, 실행 전).** 2c60d49(#346 머지본)의 A7(ii)·F1·B9 문구와 C1 문구는 코드 읽기 오류였다. 문구대로면 정상 실행에서도 항상 FAIL이었다(A7(ii): index는 성공 때 manifest 결과를 다시 쓰지 않는다. F1: invalid 셀에도 summary 파일이 있다. B9: `invalid_reason`은 예외 이름으로 시작한다. C1: raw manifest는 매 호출 바뀌는 세 파일을 포함한다). 실행 전에 정정했고 판정의 의도·임계는 바꾸지 않았다. 검증자 동의 2026-11-11. 같은 날 같은 유형 두 건을 더 실행 전에 정정했다: A7(ii)의 `--verify` 재실행(런처가 manifest 생성 뒤 `manifest-verification.json`을 다시 써서 그대로 돌리면 항상 rc 1, W4 재현)과 N1의 exit 0(정지 중 호출은 1). 재발 방지로 `tests/test_stop_path_smoke_end_to_end.py`가 실제 `run_exp0`로 시나리오 B·A 절차를 끝까지 돌리고 실제 판정 도구로 24개 기준과 SA1~SA6이 모두 PASS함을 고정한다(셀 실행·docker 잔존·destroy 이벤트·셀 로그 문구만 대역). 같은 날 SA1을 두 번 정정했다(실행 전): 처음 문구 "정지 전 start ≤ jobs"는 코드상 보장되지 않았고(게이트는 U 셀이 실행 중인 동안 다른 시작을 허용, CI에서 start 4), 다음 판정 도구의 "U 셀 1개"도 실제 주입(모든 셀 같은 실패)에서 U 셀 2개가 되는 경로를 막았다. 위 SA1 문장은 W4가 확정했다. SA4·SA5는 U 셀 각각의 ack로 맞췄다. A3(ii)에 디스크 대기 단서를, X1에 events 수집기 실패 때의 판정 경로를 더했다(F-3). F-2(B-5 전 `--finalize-abort`)는 targets 형식에 해당 상태와 명령이 없어 절차 대신 그 사실을 §4에 적었다.

## 7. 원장(exposure ledger) 행 초안

차수별로 행 하나씩 둔다. `exposure_ledger_sha256`은 2차 뒤에 고정한다(D042 :932).

| extractor | version | exposure_kind | exposed_by | seeds | date | evidence | digest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| node-tar | 7.5.2 | 정지·재개 smoke `demo run`(1차, D042) — 정지 구간(주입)은 대상 미실행, 재개 뒤 실행 셀만 노출 | W2(D042 smoke 1차) | 6101~6104 중 재개 뒤 실행된 셀의 seed(budget 20) | `<날짜>` | `<출력>/stop-path-smoke-1-<날짜>/` | 등록 digest |
| node-tar | 7.5.2 | 같음(2차) | W2(D042 smoke 2차) | 같음 | `<날짜>` | `<출력>/stop-path-smoke-2-<날짜>/` | 등록 digest |
| node-tar | 7.5.2 | 정지·재개 smoke 시나리오 A `demo run`(차수별) — 게이트 정지 구간은 대상 미실행, ack 재개 뒤 실행 셀만 노출 | W2(D042 smoke 시나리오 A) | 6101~6104 중 ack 재개 뒤 실행된 셀의 seed(budget 20) | `<날짜>` | `<출력>/stop-path-smoke-<차수>-A-<날짜>/` | 등록 digest |

시나리오 A와 B는 별도 출력 폴더, 별도 원장 행이다.

## 8. 지웅에게 요청할 재개 승인과 승인 참조 형식

오케스트레이터가 전달할 요청 문구(시나리오마다 1회):

> "D042 정지·재개 smoke <차수>차 <시나리오 B|A>가 정지했습니다. 원인: <W2 LOG 줄 요약, oracle 값 없음>. 잔존 리소스: <읽기 전용 확인 결과>. 같은 출력 폴더, 같은 engine_sha(`<sha>`), 같은 이미지, jobs 2로 재개해도 됩니까? 승인하시면 승인 참조 `D042-smoke-<차수>-<B|A>-<YYYYMMDD>-<지웅 확인 시각 HHMM KST>`로 `--resume-after-stop`과 게이트 ack(`approval=…`)에 기록합니다."

- 승인 참조는 `D042-smoke-<차수>-<시나리오>-<YYYYMMDD>-<HHMM>` 형식이다. 이 값을 `--resume-after-stop`과 게이트 ack note의 `approval=`에 **같은 문자열로** 쓴다(런처가 대조한다).
- ack note 형식: `approval=<승인 참조>; checked_at=<UTC ISO>; by=<사람>; residual=<읽기 전용 명령 → 결과>; reason=<U 사유 원문>`.

## 9. 예상 소요(추정, 보장 아님)

- 시나리오 B 주입 구간: 무기록 시도 1회는 controller·volume 생성과 정리에 수십 초가 걸린다. 셀 3~4개 × 2시도이고 jobs 2이므로 약 3~6분이다.
- 재개 구간: 남은 8~9셀 × budget 20. HOST1의 jobs 2 실측 약 4,760 exec/h이면 실행 자체는 약 2~3분이고, 셀당 준비·정리를 더하면 약 5~10분이다.
- 시나리오 A: 정지 구간은 1분 이내이고, ack 재개 뒤 남은 약 11셀 × budget 20이 실행되므로 B 재개 구간과 같은 약 5~10분이다. 그 밖에 지웅 승인 대기 시간이 붙는다.
- 차수당 합계는 승인 대기를 빼고 약 20~30분이다.

## 10. 횟수·순서와 실행 전 점검

**횟수:** 2회(D042 문구 그대로).

**순서(오케스트레이터 결정, W4 권고 채택):** 런처 smoke → **정지·재개 smoke 1차** → 적격성(약 5시간) → **2차**(동결 직전) → 원장 sha 고정 → 동결.

- 1차를 적격성 앞에 두는 이유: 약 30분짜리 smoke로 정지 경로의 결함을 먼저 걸러, 그 수정이 5시간짜리 적격성 실행을 무효로 만드는 일을 막는다.
- 1차 뒤 실행 경로(`SHARED_PATH_FILES` 해시 또는 실행 SHA)가 바뀌면 2차는 필수이고 적격성도 무효다.
- 같은 SHA에서 하는 2차는 회귀 확인이 아니라 반복 재현이다.
- HOST2는 D042 요구 밖이다. HOST2(Engine 29.9.3)의 정지 경로 동작은 UNKNOWN이고, 이 한계를 결과 보고에 적는다.

**실행 전 점검(오케스트레이터 승인 조건):**

1. 이 파일 머지(지웅 승인)
2. HOST1에 다른 실험·테스트가 없음. 잔존 리소스 0
3. 출력 폴더의 기대 이미지 파일 값을 읽기 전용으로 확인
4. 1차는 통합 후보 확정 뒤 HEAD, 2차는 최종 `engine_sha` 후보

**다른 문서에 넣을 제안 문장(#330·#332 담당 W3·W4에게 전달):**

- 본실험 금지 조건(#330 점검표, exp3-v1 체크리스트): "D042 정지·재개 smoke 1차·2차 PASS(`experiments/configs/stop-path-smoke-v1.md` sha256 `<동결 시 기입>`)와 원장 행 반영 전에는 본실험을 시작하지 않는다."
- Code Freeze 선행 조건: "D042 정지·재개 smoke 1차 PASS."
- 호스트 적격성 §12: 넣지 않는다.
