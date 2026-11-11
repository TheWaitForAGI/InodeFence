# EXP-3 train · EXP-2 holdout 실행 런북 v1 (2026-11-12, W3 작성·W1 검토)

> **상태: 초안. 등록이 아니다.** 판정·임계·seed·arm·budget·GO 식은 `experiments/preregistration/exp3-v1.md`·`exp2-v1.md`(#332, 동결 전 초안)이 정한다. 이 문서는 그 값을 바꾸지 않고 명령과 순서만 적는다. 둘이 다르면 등록이 이긴다. E 뒤 문서의 적용은 [정지·재개 smoke v1 부록 C](stop-path-smoke-v1.md)를 따른다: 절차 문구는 main 최신, 코드·등록·기준 파일·원장 sha는 E.

## 0. 공통 규칙

- 실행 트리: 호스트별 E의 detached worktree. 모든 명령은 그 worktree에서 `PYTHONPATH=src`로 실행한다. 실행 전 `PYTHONPATH=src python -c "import inodefence; print(inodefence.__file__)"`가 그 worktree의 `src/` 아래인지 확인한다.
- 출력·manifest·기준 파일·채운 등록 사본은 모두 worktree 밖(`~/inodefence-evidence/<실험>-<host>-<날짜>/`)에 둔다.
- 봉인: 실행 중 결과 값(oracle·steps·summary 값) 열람 금지. 운영 점검(`exp_operating_check`)과 인프라 값만 본다.
- 승인 참조: train `EXP3-<HOSTn>-<YYYYMMDD>-<HHMM>`, holdout `EXP2-<HOSTn>-<YYYYMMDD>-<HHMM>`. 재개마다 새 참조.
- 본실험 주간 HOST1 전원 유지(야간 수동 종료 금지)는 지웅 결정 사항이다. 결정 전에는 시작하지 않는다.

## 1. 동결 당일 (상세는 #332 동결 체크리스트)

1. 선행: 런처 smoke, D042 1·2차, 두 호스트 적격성 판정, 교차 비교 보고, 원장 행 머지, 원장 sha 확정.
2. #332 `TBD-FREEZE`를 채운 head 머지(F). 실행 등록 파일은 F의 경로, 코드는 E.
3. train 할당 파일(`alternate-v1`, 동결 참여 집합 P) 생성·sha 기입(적격성 런북 §1의 "할당 파일을 만드는 순서"와 같다).
4. 호스트별 기준 파일(`make_run_criteria`, E)과 그 sha를 LOG에 고정. **실험마다 따로 만든다.** `--expected-images`는 그 등록의 모든 node-tar 타깃 이미지 + controller + helper와 정확히 같은 집합이어야 한다(`run_exp0.py:644-670`, 다르면 거부). train(타깃 7.5.2 하나)은 적격성 기준 파일과 같은 이미지 집합이다. holdout(타깃 7.4.4 하나)은 `make_run_criteria --target-image inodefence-node-tar-effect:7.4.4`(`make_run_criteria.py:145`)로 새로 만든다. exp3-v1·exp2-v1은 각각 타깃이 하나다(#332 `bf0dc2e`).
5. 호스트별 `--dry-run`: `gate: PASS`, 셀 수 = 그 호스트 seed 수 × 3.
6. **네트워크 의존 점검(읽기 전용, 실행 직전과 매 재개 직전).** 셀마다 컨트롤러 준비 단계에서 `python -m pip install --quiet --disable-pip-version-check pytest`를 PyPI에서 받는다(`scripts/local_node_tar_smoke.sh:390`, 버전 미고정). 이름 해석이나 도달이 실패하면 셀이 무기록으로 끝나고, 3연속이면 Guard 정지다. 다음 결과를 실행 기록에 남기고, 실패하면 시작·재개하지 않는다:
   - `getent hosts pypi.org files.pythonhosted.org`
   - `curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://pypi.org/simple/pytest/`(200)
   - 2026-11-12에 ubuntu.com 이름 해석 장애가 실제로 있었다(GitHub 러너 container-integration 실패, PyPI는 정상).

## 2. train 실행 (호스트별, 독립)

```bash
PYTHONPATH=src python -m scripts.run_exp0 --preregistration <F의 exp3-v1 채운 사본> --output <out-exp3-HOSTn> \
  --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
  --observer-integrity-policy invalid-continue \
  --seed-assignment <train 할당 파일> --host-id HOSTn \
  --jobs 2 --clock-reference <offset-HOSTn.json> --manifest-host hostn-exp3 \
  --manifest-out <worktree 밖>/raw-manifest-hostn-exp3.sha256 \
  --expected-images <criteria-HOSTn.json> --skip-build
```

- `--target-digest`는 타깃마다 한 번씩 반복한다(`action="append"`, `run_exp0.py:1593-1598`). train·holdout은 타깃이 하나라 한 줄이다.
- `--clock-reference`는 실행 직전에 새로 잰 오프셋 파일이다. 끝날 때도 따로 재서 별도 파일로 남긴다(적격성과 같다).

## 3. 정지와 재개 (train·holdout 공통)

1. 인프라 정지(`infrastructure-stop`) 또는 게이트 U 정지가 나면 원인을 기록한다(oracle 미열람). **원인 분류 첫 단계는 "pip 네트워크 오류" 확인이다.** 무기록 셀의 로그에서 찾는다. 현재 시도는 `<out>/<target_id>/<run_id>.log`, 이전 시도는 `<out>/attempts/<run_id>.attemptN.log`다. 찾을 문자열은 `FAILED at step: prepare controller (exit N)`(`local_node_tar_smoke.sh:177`)와, 함께 나오는 pip 줄 `Temporary failure in name resolution`, `Failed to establish a new connection`, `Could not find a version that satisfies the requirement pytest`, `No matching distribution found for pytest` 중 하나다. 지금 §1-6의 도달 점검을 다시 돌린다. 이 경우 원인은 인프라(외부 네트워크)다. 도달이 회복된 뒤에만 재개 승인을 요청한다.
2. **events 보존:** 재개 전, 그리고 미완 호출 다음의 어떤 호출 전에도 `<out>/host/events.jsonl`을 `<evidence>/host-events/events-<UTC stamp>-before-<step>.jsonl`로 복사하고 sha256을 실행 기록에 남긴다. 런처가 pending 셀이 있는 호출마다 이 파일을 `"wb"`로 다시 연다(`scripts/launcher_guards.py:330`, `scripts/run_exp0.py:793`). abort 3분할(§6)의 입력이므로 빠뜨리면 그 구간 abort는 "미관찰"로 떨어진다.
3. 승인 요청 문구: "<EXP3|EXP2> <HOSTn> 실행이 <시각>에 <인프라|게이트> 정지했습니다. 원인: <경로·요약>. 잔존 리소스: <0 또는 목록>. 재개 승인 참조 `<EXP3|EXP2>-<HOSTn>-<YYYYMMDD>-<HHMM>`를 요청합니다."
4. 승인 뒤 같은 명령에 `--resume-after-stop <참조>`. 정지 공백은 `infrastructure-stop`·`infrastructure-resume` 줄로만 r에서 빠진다(exp3-v1 §5). pip 네트워크 정지도 같다(D043). 그 공백은 r에서 빠지지만 H_rem·마감에서는 빠지지 않는다(벽시계).
5. 미재개로 GO 시각을 맞으면 D047 §9.1(부분 GO)이다. `partial_go_check`가 판정 입력을 만든다(§4).

**한계(공개):** 셀 경로의 pytest 설치가 네트워크·버전 미고정이다. 근원 수정(이미지에 고정 버전 포함)은 E·이미지 변경이라 본실험 뒤로 미룬다. pytest는 측정 경로에서 쓰이지 않는다(W1 확인: `container_controller.py:14`의 import뿐이고, pytest 함수는 suite 모드에서만 부르며 `src/`에는 pytest import가 없다). 그래도 실행 중 새 pytest 릴리스가 나오면 셀마다 설치 버전이 다를 수 있고, 셀별 설치 버전은 기록되지 않는다.

**사후 점검(실행마다):** 실행 구간(첫 `start` ~ 마지막 `end`, realtime)에 PyPI에 pytest 새 릴리스가 있었는지 `https://pypi.org/pypi/pytest/json`의 릴리스 시각으로 확인해 기록한다. 셀별 버전 기록이 없으므로 이것이 버전 범위의 유일한 근거다. 릴리스가 있었으면 "구간 안에서 설치 버전이 바뀌었을 수 있음"을 한계에 적는다.

## 4. GO (train 종료 뒤, W3)

1. **GO 판정 시각을 먼저 적는다**: `experiments/summaries/exp3-train-go-decision.json`의 `decided_at`과 LOG 한 줄. 적은 뒤 고치지 않는다(D043). 그 전에는 GO 입력을 보지 않는다.
2. `partial_go_check --record-in-go-decision`(두 호스트 출력, raw manifest, 정지 진술). 상태가 held면 지웅 판단으로 올리고 멈춘다.
3. `merge_host_indexes`(train) → `analyze_exp0` → `gen_exp3_tables --artifact T-EXP3-2`(GO 입력 표). 판정 줄은 사람이 쓴다.
4. GO면 holdout 할당: `make_seed_assignment --rule rh-proportional-v1 --go-decision <GO 파일> --train-preregistration <exp3 사본> --train-assignment <train 할당>`. 할당 파일 sha를 LOG에 고정한다(게이트가 GO 파일 r_h로 재생성해 바이트 대조한다).

## 5. holdout 실행

§2와 같고 바뀌는 인자는 다음뿐이다:
- 등록: exp2-v1 채운 사본
- 할당: §4.4 파일
- `--target-digest node-tar-holdout=sha256:f5d3e9a999cfad0a5f37002bf36802378b20777646be3684eb97baeaa4080421`
- `--expected-images`: §1.4의 **holdout 기준 파일**(7.4.4 이미지 포함). train 기준 파일은 게이트에서 거부된다.
- manifest 이름: `hostn-exp2`

 각 호스트는 자기 seed를 오름차순으로 돈다. 마감(2026-11-25 12:00 KST)에 끝나지 않은 셀이 있는 seed는 블록 전체 제외다. **봉인 해제 시점은 미정이다(동결 전 결정):** D041 분석 수정 2번은 "봉인 해제는 마감 시각 뒤에만"이라고 하는데, E의 run_exp0는 호스트별로 모든 셀이 끝나고 무결성이 확인되면 마감 전에도 index를 가리지 않는다(`scripts/run_exp0.py:1874-1883`). 결정 전까지는 마감 전에 어느 호스트의 index·summary도 열지 않는다.

**먼저 끝난 호스트가 있는 구간(W4 조건, 어느 안이든 적용):**
- 먼저 끝난 호스트의 종료 시각과, 그때의 `summaries/index.json`·`summaries/*.summary.json` sha256을 LOG에 고정한다. sha는 파일을 해시만 하고 열지는 않는다.
- 전체 해제 전에는 어떤 세션도 그 호스트의 `summaries/`, 셀 report(`*.json`), `*.steps.jsonl`를 읽지 않는다. 해제 뒤 세션 도구 호출 기록에서 그 경로를 검색해 위반 0을 확인하고 결과 보고에 적는다.
- 남은 호스트의 운영 결정(정지·재개, 운영 중단, 참여)은 사전 고정 규칙(D042 승인 재개, D041 운영 중단)이나 인프라 키 근거로만 한다. 인프라 키는 `cell-results.jsonl` 상태 줄, abort 수·사유, 게이트 판정이다. "왜 일찍 끝났나"도 이 키로만 답한다.
- 분석은 두 호스트를 병합한 index로만 시작한다. 호스트별 부분 분석은 하지 않는다.

## 6. 분석과 표 (해제 뒤)

1. 호스트별 raw manifest 대조 → `merge_host_indexes`(holdout, 부분 GO면 미완 블록 제외 반영) → `analyze_exp0 --format json`(확증 절 포함).
2. `gen_exp3_tables`로 T-EXP2-1~6, `regenerate_paper_artifacts --verify`.
3. **abort 3분할(T-EXP2-3 손 입력, `exp2-holdout-hand-input.json`)** — 생산 도구가 없다. 절차(파일럿 결과 메모 §4.1의 방법):
   - 입력: abort 스텁(`aborted.step_index`, `reason`, `error_chain`, abort 시각)과 그 셀의 마지막 step 파일 시각, events 원본과 §3.2 사본 전부. oracle 필드·steps 내용은 열지 않는다.
   - 묶음: (1) `target_not_started` = abort 시간창 안에 create 뒤 start 없이 destroy된 컨테이너가 있음. (2) `lost_after_execution` = 마지막 컨테이너가 start·die 뒤 소실. (3) `first_error_unconfirmed` = 시간창이 이벤트 기록 범위 밖(수집기 실패·사본 없음 포함).
   - 하한 검사: `lost_after_execution` ≥ 분석기의 스텁 하한(`unknown_outcome_steps.lost_after_execution_lower_bound`). 생성기가 위반을 거부한다(`gen_exp3_tables.py` t_exp2_3).
   - 두 사람(작성 W2 또는 W1, 대조 W3)이 독립으로 세고 다르면 셀 목록으로 맞춘다. 사본이 없어 (3)으로 간 셀 수를 따로 적는다.
   - **셀 대응은 시간창 대조로 한다(W1 확인).**
     - controller는 이름에 셀이 있다: `inodefence-local-controller-<run_id>`(`local_node_tar_smoke.sh:82`).
     - case별 대상 컨테이너는 `inodefence-<32hex>`이고, 라벨 `org.inodefence.execution-owner=<owner>`를 단다. owner는 셀 호출마다 새 uuid4다(`container_host.py:731`). cell-results·로그·report에 기록되지 않고, controller 라벨과도 맞지 않는다.
     - 그래서 "그 owner의 첫 create가 어느 셀 controller의 create~destroy 구간 안에 드는가"로 대응한다. owner 하나 = 셀 시도 하나다(그 시도의 create 전부, step당 약 2개).
     - jobs 2에서 두 셀이 몇 초 차이로 시작해 모호하면, abort 스텁의 abort 시각과 cell-results의 start/end로 가른다. 그래도 남는 모호함은 (3) `first_error_unconfirmed`로 두고 사유를 적는다.
4. 판정 칸 선택: D12 표와 사전 작성 문단(`d12` 문서, 저장소 밖 → 머지 전 위치 결정).

## 7. 기록

원장 행(호스트·실험별), LOG 한 줄(시작·정지·재개·GO·종료), raw manifest(worktree 밖) sha.
