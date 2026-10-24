# 작업 큐 (BACKLOG)

자율 루프(`.claude/skills/autoloop/SKILL.md`)가 읽는 할 일 목록이다. **맨 위부터 순서대로** 진행한다.
완료 기록은 [WORKLOG](WORKLOG.md), 실행 기록은 [LOG](LOG.md)에 남긴다.

분류: 1–4는 11/2 중간발표 P0 작업이다([MIDTERM_GOALS](MIDTERM_GOALS.md)). 목표는 `make demo` 하나로
실제 node-tar에서 입력 생성 → 실행 → 중간 상태 관찰 → Oracle → Feedback → 다음 Mutation 선택이
재현되는 것이다. P0 작업이 새로 생기면 이 표의 `대기` 항목 사이에 끼워 넣는다.

상태 값: `대기` / `진행` / `완료(<브랜치>)` / `막힘(<날짜>, <이유>)` / `BREAKING(<브랜치>)` / `대기(머지 필요: <브랜치>)`

상태 칸에 위 값 대신 사람이 적은 일정·승인 조건이 있는 항목은 autoloop가 집지 않는다.
사람이 상태를 `대기`로 바꿀 때만 진행한다.

| 순서 | ID | 상태 | 게이트 |
| --- | --- | --- | --- |
| 1 | P0-2/P0-4 native 연결: 중간 상태 렌더링 + 선택 근거를 demo-native JSON에 | 완료(jiwoong/p0-2-native-trace) | 없음 |
| 2 | P0-5 `make demo` = native, `make demo-synthetic` 분리 + SYNTHETIC 라벨 | 진행 | 1 머지 |
| 3 | P0-5 JSONL 부분 저장 + CI에 effect producer/effect-demo 추가 | 대기 | 2 머지 |
| 4 | P0-1 N01 native 무결성 결함 원인 조사 | 대기 | 없음 (조사만; 수정·재현 실행은 사람 승인 후) |
| 5 | P2-b(#129), P2-c(#130) 머지 | 10/27 사람 리뷰 후 머지 예정 (중간발표 N01 추가 성과용) | 사람 |
| 6 | P2-c N01 rediscovery 실행 | 10/27~28 사람 승인 후 실행 예정, 마감 10/30. 그 전 autoloop 실행 금지 | 사람 |
| 7 | P3 A/B/C 비교 실험 | 중간발표 이후, 사람 승인 필요 | 사람 |

---

## 1. P0-2/P0-4 native 연결

- 분류: P0-2(중간 상태 관찰 출력), P0-4(선택 근거 기록)
- 환경: 구현·테스트는 Dev Container, native 확인은 **호스트 터미널**(`make demo-native`, docker 필요)
- 현재: `scripts/run_effect_demo.py`의 `native_demo_report`는 `effect_campaign_report`의 steps(feedback, scheduler_evidence)와 `native_checks`, `timing`만 남긴다. `src/inodefence/effect_demo.py`의 `render_effect_trace`(값마다 archive/observed/not_observed/derived 출처 라벨)는 native JSON에 들어가지 않는다. 선택 근거 helper(`_selection`, `_feedback_events`)는 정책 비교(`compare_effect_campaign_reports`)에서만 쓰인다.
- 할 일:
  - native report의 각 step에 `render_effect_trace` 결과와 선택 근거(parent, 선택 전 corpus 크기, weights_before, 선택 operator와 weight, 새 effect key 수, reward, weights_after)를 **추가**한다. 기존 필드와 의미는 바꾸지 않는다. 새로 계산하지 말고 기존 helper를 재사용한다.
  - synthetic report에 같은 필드가 생기면 `·SYNTHETIC` 라벨을 유지한다.
- 완료 조건: `make check` 통과. synthetic report로 새 필드를 확인하는 테스트 추가. 호스트에서 `make demo-native` 1회 실행해 JSON에 새 필드가 있는지 확인하고 LOG 한 줄(`demo run` 라벨). 호스트 실행을 못 하면 그 부분만 `막힘(호스트 실행 필요)`.
- 실행/검증하게 되는 것: 실제 node-tar 실행의 entry별 중간 상태와 "피드백 때문에 이 mutation이 선택됐다"는 근거를 demo-native JSON 하나로 확인할 수 있다.

## 2. P0-5 `make demo` = native

- 분류: P0-5
- 환경: Dev Container(synthetic, `make check`) + **호스트 터미널**(native)
- 게이트: 1 머지(같은 report 코드를 고친다. 스택 금지)
- 현재: `Makefile`의 `demo`는 `DEMO_PRODUCER ?= synthetic`로 synthetic을 돌리고, native는 `demo-native`(`scripts/local_node_tar_smoke.sh demo`)다. AGENTS.md 목표는 `make demo`가 실제 node-tar 루프다.
- 할 일:
  - `make demo`가 native 경로(지금 `demo-native`와 같은 명령)를 돌리게 하고, synthetic은 `make demo-synthetic`으로 분리한다. `demo-native`는 호환용으로 남길지 정해 이유를 커밋 메시지에 적는다.
  - synthetic 산출물은 파일명과 report label 모두에 SYNTHETIC을 드러낸다. native 산출물에 SYNTHETIC이 섞이지 않게 한다.
  - `make demo`를 언급하는 문서(START_HERE, STATUS, README 등)를 함께 고친다.
- 완료 조건: `make check` 통과. Dev Container에서 `make demo-synthetic` 2회 결과 바이트 동일. 호스트에서 `make demo` 1회 성공과 LOG 한 줄(`demo run`). 호스트 실행을 못 하면 그 부분만 `막힘(호스트 실행 필요)`.
- 실행/검증하게 되는 것: `make demo` 하나로 실제 node-tar 루프를 재현하고, synthetic 결과를 native로 착각할 수 없다.

## 3. P0-5 JSONL 부분 저장 + CI

- 분류: P0-5(재현성), P0-1(실패 증거)
- 환경: Dev Container, CI
- 게이트: 2 머지(같은 demo 경로를 고친다. 스택 금지)
- 현재: native demo가 중단되면(`NativeDemoAborted`) `scripts/container_controller.py`는 `aborted` 블록(step index, case ID, reason, raw frame·stderr)만 쓴다. 그 전에 완료된 step의 루프 기록은 남지 않는다. CI의 container job(`.github/workflows/ci.yml`)은 `benign-node-smoke`만 돌리고 effect producer와 effect demo는 돌리지 않는다.
- 할 일:
  - step이 끝날 때마다 루프 기록을 JSONL로 append해서, 중단돼도 완료된 step이 남게 한다. 기존 `src/inodefence/campaign_export.py`의 `steps.jsonl` 형식을 먼저 재사용할 수 있는지 본다. 최종 JSON 형식은 바꾸지 않는다.
  - CI container job에 effect producer smoke와 작은 budget의 effect demo를 추가한다. 격리 완화 플래그를 쓰지 않는다(가드 R3/R5).
- 완료 조건: `make check` 통과. 강제 중단 테스트에서 완료된 step이 JSONL에 남는 것을 확인. PR CI 통과.
- 실행/검증하게 되는 것: native 실행이 중간에 멈춰도 그때까지의 관찰·feedback·선택 기록을 잃지 않고, effect 경로 회귀를 CI가 잡는다.

## 4. P0-1 N01 native 무결성 결함 원인 조사

- 분류: P0-1(native 실행 실패 원인과 증거). demo-native와 같은 producer/reader 경로(`src/inodefence/targets/node_tar_effect.py`)를 쓴다.
- 환경: **호스트 터미널**(증거 파일이 호스트에 있다). 읽기만 한다.
- 근거(관찰 기록): #130 브랜치(`jiwoong/p2-c-n01-rediscovery`) LOG 2026-10-24 01:58. node-tar 7.5.2, seed 456, step 72 ABORT. target은 success(exit 0)인데 trace invalid: integrity_valid False, completeness invalid, controller_flush False, `transport is not one LF-terminated frame`, observation_failures `source_reader_disagreement` + `incomplete_flush`. 증거: `~/inodefence-evidence/p2c-native-matrix/`의 `…-015543.json`(raw frame·stderr 보존).
- 할 일:
  - 증거 JSON의 에러 메시지, raw frame, stderr부터 읽는다.
  - `node_tar_effect.py`의 framing/flush 검사(`transport is not one LF-terminated frame`, `INCOMPLETE_FLUSH`, `SOURCE_READER_DISAGREEMENT` 발생 지점)와 대조해 원인을 producer 출력 / controller flush / transport / reader 중 하나로 분류한다.
  - 관찰한 사실(observed)과 추론(inferred)을 구분해 적는다.
- 금지: 코드 수정, 재현 실행(7.5.2/7.5.3 historical 재실행 포함)은 사람 승인 후에만 한다. 새 audit 문서를 만들지 않는다.
- 완료 조건: LOG 한 줄(원인 분류, 근거 위치, observed/inferred 구분). 수정이 필요하면 수정안 요약을 WORKLOG 요약에 적고 상태를 `막힘(<날짜>, 사람 승인 필요)`로 둔다.
- 실행/검증하게 되는 것: native 관찰 무결성 중단이 어디서 생기는지 증거로 판단할 수 있고, `make demo`가 반복 성공하는 데 필요한 수정 범위를 정할 수 있다.
