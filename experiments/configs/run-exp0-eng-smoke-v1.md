# run_exp0 엔지니어링 smoke v1 — 실행 등록 파일 (비등록, `demo run`)

> **상태: 초안(2026-11-11, W3).** 설계는 [호스트별 적격성 검증 v1](host-qualification-v1.md) §2(#342)를 따른다.
> **비등록이고 판정 입력이 아니다.** EXP-3·EXP-2 데이터, 벤치마크 §6 판정, 사전등록 값에 쓰지 않는다. oracle은
> 봉인한다(`interim_analysis = forbidden`). 이 파일은 사전등록 *형식*을 빌려 런처의 등록 게이트를 실제로 통과시키려는
> 것일 뿐이며, `experiments/preregistration/` 밖에 둔다.
>
> `TBD-FREEZE` 값이 남아 있는 동안 파서가 실행을 거부한다(의도된 동작). 값은 아래 §3 절차의 1단계에서 채운다.

## 1. 등록 블록

exp3-v1(#332)과 다른 값은 `experiment_id`, `seeds`, `budget`, `jobs`(`host.<id>.jobs`·`jobs_max`),
`execution_deadline`, 그리고 seed가 다르므로 결정적으로 따라오는 `seed_assignment_sha256`뿐이다.

```preregistration
# run_exp0 engineering smoke v1 (demo run, not registered). Fill TBD-FREEZE per section 3 step 1.
experiment_id = exp3-eng-smoke
engine_sha = TBD-FREEZE
seeds = 6300, 6301, 6302, 6303
budget = 300
vocabulary = observed-names
arm.R = unretained-seed-restart-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
targets.node-tar-7.5.2.extractor = node-tar
targets.node-tar-7.5.2.version = 7.5.2
targets.node-tar-7.5.2.image_digest = sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb
targets.node-tar-7.5.2.role = train
targets.node-tar-7.5.2.hypothesis = H-A
targets.node-tar-7.5.2.exposure = pre-exposed
targets.node-tar-7.5.2.exposure_ref = experiments/preregistration/exposure-ledger.md
exposure_ledger = experiments/preregistration/exposure-ledger.md
exposure_ledger_sha256 = TBD-FREEZE
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 20261104
sentinel_count = 5
observer_integrity_policy = invalid-continue
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
primary_endpoint = t_first
execution_mode = per-case-container
jobs_max = 2
campaign_watchdog_seconds = 10800
disk_pause_fraction = 0.9
interim_analysis = forbidden
execution_deadline = TBD-FREEZE
host.HOST1.jobs = 2
host.HOST1.docker_engine = TBD-FREEZE
host.HOST2.jobs = 2
host.HOST2.docker_engine = TBD-FREEZE
seed_assignment_rule = alternate-v1
seed_assignment_sha256 = a395367b5a617a63ba92bd04183b45e8a79d33885eed81096d4bd2c7a537accc
```

할당 파일은 [`run-exp0-eng-smoke-v1.assignment.json`](run-exp0-eng-smoke-v1.assignment.json)이다(6300·6302 →
HOST1, 6301·6303 → HOST2). `python -m scripts.make_seed_assignment --rule alternate-v1`이 같은 바이트를 다시 만든다.

**호스트 키와 참여(ORCH 결정 (b)).** 파서는 참여 호스트가 하나여도 `host.HOST1.*`·`host.HOST2.*` 키를 모두
요구한다. 참여하지 않는 호스트의 키는 형식상 기재일 뿐이고, 참여 여부는 할당 파일의 `participants`(와 holdout은 GO
파일)가 정한다. 비참여 호스트의 키를 참여로 읽지 않는다.
**할당 파일을 만드는 순서(W4).** `make_seed_assignment`는 `TBD`가 남은 등록 파일을 거부한다. 그래서 다른 값을 모두
채우고 `seed_assignment_sha256`만 임시값(64자리 hex)으로 둔 사본에서 할당 파일을 만든 뒤, 출력된 sha를 그 칸에
채운다.

## 2. 통과 조건 (적격성 검증 v1 §2, 실행 전 고정)

| 조건 | 판정 근거(기록) |
| --- | --- |
| cleanup UNKNOWN 0 | 호스트별 `<out>/start-gate/*.verdict`에 `U` 0, `acknowledged/` 비어 있음 |
| 잔존 리소스 0 | 실행 뒤 `docker ps -a`·`docker volume ls`의 `inodefence-` 접두 대조(실행 전 목록과 차이 0) |
| 러너 실패 0 | `cell-results.jsonl` end 줄에 `runner_error` 0 |
| 시작 실패 0 | end 줄에 `start_denied` 0 |
| 기록 완전성 | index `cell_completeness`: 모든 셀이 complete 또는 abort-final, `record_inconsistent` 0, `no_record` 0 |
| 병합 검사 | `merge_host_indexes` exit 0(`merge.complete = true`). 두 호스트 smoke가 모두 끝났을 때만 판정하며, 호스트별 smoke 통과에는 넣지 않는다(잠정, D047 호스트 독립 판정) |
| 호스트 키 게이트 | 두 호스트의 실제 실행이 게이트를 통과(exit 2 거부 없음) |
| 인프라 정지 0 | `infrastructure-stop` 줄 0 |

보고만 하는 값: 셀별 `infra_reexecutions` 수, 재시도 수(셀당 start 줄 수), 운영 점검(`--host-output` 두 개) 출력.
결정론 검사(D046): `infra_reexecutions`가 있는 셀만 §3 6단계로 재실행해 `compare_report_pair`의 불리언만 보고한다.

## 3. 실행·병합·운영 점검 절차 (초안)

실행은 통합 후보 HOLD 해제 뒤 지웅 승인으로만 한다(사람 승인 게이트; 승인 지점 표는 [적격성 실행 등록
파일](host-qualification-v1-run.md) §3). 승인 참조 형식은 `ENGSMOKE-<HOSTn>-<YYYYMMDD>-<HHMM>`이다. 호스트마다
같은 절차다.

1. **값 고정(한 번, 두 호스트 공통):** 실행 SHA `E`를 정하고, `engine_sha = E`, `exposure_ledger_sha256 =` 그 시점 원장
   sha, `execution_deadline =` 예상 종료 + 여유(UTC 오프셋 포함), `host.<id>.docker_engine =` 각 호스트 preflight
   `docker version --format '{{.Server.Version}}'`를 채운다. 채운 파일은 `E` **뒤** 커밋에 있어도 된다. 런처는
   checkout HEAD를 `engine_sha`와 비교하므로, 실행은 `E`의 깨끗한 detached worktree에서 하고 `--preregistration`에는
   그 worktree 밖의 채운 파일 사본을 준다(EXP-0와 같은 방식). 채움 명령: `PYTHONPATH=src python -m scripts.fill_run_registration <이 파일> --set engine_sha=<E> --set exposure_ledger_sha256=<E 트리의 원장 sha> --set execution_deadline=<UTC 오프셋 포함> --set host.HOST1.docker_engine=29.8.0 --set host.HOST2.docker_engine=29.9.3 --out <worktree 밖>/<이름>-filled.md`.
   **기준 파일(순서 고정):** `E` 확정 → `E`에서 기준 파일 생성(이미지 id 3개, 호스트별 Engine, 공유 경로 16개 해시,
   `expected_execution_sha = E`; 생성 명령 `PYTHONPATH=src python -m scripts.make_run_criteria --execution-sha <E> --host HOST1 --engine HOST2=29.9.3 --out <worktree 밖>/criteria.json`) → 기준 파일 sha256을 LOG에 고정 → 실행. `--expected-images`에 이 파일을 준다.
   **원장 sha:** 실행 뒤 원장 행은 `E` 뒤 커밋에 들어가므로, 같은 `E`에서 도는 실행들의 `exposure_ledger_sha256`은
   `E` 트리의 원장 sha 그대로다(a76ffee에서는 `8a832e19…`).
2. **preflight(호스트별):** detached worktree `E`, `git status` 깨끗, venv python(uv.lock 생성 금지), `docker context
   show`, Server 버전, 이미지 id(`22c8734f…`, controller, helper; HOST2는 load 직후 대조), `docker ps -a`·`docker volume
   ls`의 `inodefence-` 접두 목록을 `<out>/preflight/`에 저장. dry-run:

   ```bash
   PYTHONPATH=src python -m scripts.run_exp0 --preregistration <filled.md> --output <out-HOSTn> \
     --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
     --observer-integrity-policy invalid-continue \
     --seed-assignment experiments/configs/run-exp0-eng-smoke-v1.assignment.json --host-id HOSTn \
     --jobs 2 --manifest-host hostn-eng-smoke \
     --manifest-out <worktree 밖>/raw-manifest-hostn-eng-smoke.sha256 \
     --expected-images <criteria.json> --skip-build --dry-run
   ```

   **`--manifest-out`은 반드시 worktree 밖이다:** 기본 경로가 저장소 안(`experiments/summaries/`)이라 실행 worktree를
   더럽히고, postflight의 실행 SHA 검사가 dirty로 실패한다.

   **이미지는 미리 준비한다(#345):** 런처의 preflight가 warmup보다 먼저 돌며 target·controller·helper id를
   `--expected-images`(기준 파일의 `expected_image_ids`)와 대조해 불일치면 시작 전에 거부한다. 그래서 HOST1은 이미지를
   확인만 하고 HOST2는 `docker load`로 미리 넣은 뒤 `docker image inspect`로 3개 id를 대조한다. **두 호스트 모두
   `--skip-build`로 실행**한다(빌드 캐시가 같은 id를 낼지 실 docker에서 확인하지 않았다).

   **코드 경로 점검(두 호스트 공통):** 모든 명령은 실행 worktree `E`에서 `PYTHONPATH=src`를 붙여 실행한다. venv의
   `.pth`가 다른 체크아웃의 `src`를 가리킬 수 있기 때문이다(HOST2에서 `No module named
   inodefence.evaluation.cell_completeness`로 확인). 실행 전에
   `PYTHONPATH=src python -c "import inodefence; print(inodefence.__file__)"`의 출력이 실행 worktree의 `src/` 아래인지
   확인하고, 아니면 시작하지 않는다.
   **dry-run PASS는 이미지 preflight를 대신하지 않는다:** dry-run은 이미지가 하나도 없어도 `gate: PASS`이다(로컬
   이미지 존재와 id 대조는 live preflight에서만 한다). 이미지 id는 위 대조로 따로 확인한다.
   `gate: PASS`, wiring 거부 없음, cells 6, seeds 두 개를 확인한다.
3. **실행:** 같은 명령에서 `--dry-run`을 뺀다(`--skip-build`·`--manifest-out`은 두 호스트 모두 유지). 실행 중 운영
   점검은 다른 터미널에서
   `PYTHONPATH=src python -m scripts.exp_operating_check --preregistration <filled.md> --output <out-HOSTn>`(출력은 수만).
   **정지 시 재개:** 인프라 정지가 나면 원인을 기록하고 지웅에게 "런처 smoke <HOSTn> 실행이 <시각>에 인프라
   정지했습니다. 원인: <원인 기록 경로·요약>. 잔존 리소스: <0 또는 목록>. 재개 승인 참조
   `ENGSMOKE-<HOSTn>-<YYYYMMDD>-<HHMM>`를 요청합니다."로 승인을 요청한다. 승인되면 같은 명령에
   `--resume-after-stop ENGSMOKE-<HOSTn>-<YYYYMMDD>-<HHMM>`을 붙인다. 정지가 있었으면 이 smoke는 불통과다(인프라 정지 0
   조건).
4. **실행 뒤(호스트별):** `docker ps -a`·`docker volume ls`를 다시 저장해 1단계 목록과 대조, `start-gate/` 상태 확인,
   index `cell_completeness`와 `cell-results.jsonl`의 `runner_error`·`start_denied`·`infrastructure-stop` 수 확인.
5. **병합(한 곳):**

   ```bash
   PYTHONPATH=src python -m scripts.merge_host_indexes --preregistration <filled.md> \
     --seed-assignment experiments/configs/run-exp0-eng-smoke-v1.assignment.json \
     --host HOST1=<out-HOST1> --host HOST2=<out-HOST2> --output <out-merged>
   PYTHONPATH=src python -m scripts.exp_operating_check --preregistration <filled.md> \
     --host-output HOST1=<out-HOST1> --host-output HOST2=<out-HOST2>
   ```

   **부분 GO 도구 형식 점검(보고만, 판정 아님):** 부분 GO 경로(D047 §9.1)는 실 데이터로 돈 적이 없다. 그래서 두 호스트
   smoke가 끝나면 그 출력으로 한 번 돌려 입력 형식 문제를 미리 잡는다. 이 도구는 cell-results, 셀 상태, abort 스텁, 파일
   해시만 읽고 oracle 필드는 읽지 않는다. GO 파일은 worktree 밖의 임시 파일(`{"decided_at": "<지금, UTC 오프셋>"}`)이고,
   `--record-in-go-decision`은 쓰지 않는다:

   ```bash
   PYTHONPATH=src python -m scripts.partial_go_check --preregistration <filled.md> \
     --seed-assignment experiments/configs/run-exp0-eng-smoke-v1.assignment.json \
     --host HOST1=<out-HOST1> --host HOST2=<out-HOST2> \
     --go-decision <worktree 밖>/go-format-check.json --out <worktree 밖>/partial-go-format-check.json
   ```

   기대값: exit 0, 정지가 없었으면 `status`가 `full`이고, 두 호스트의 `seed_blocks`에 smoke seed가 모두 완주로 나온다.
   exit 2이거나 seed 블록이 기대와 다르면 GO 산출 전에 도구를 고쳐야 하므로 보고한다.
6. **결정론 검사(재실행이 있었던 셀만, D046, 적격성 검증 v1 §2):** `infra_reexecutions`가 0보다 큰 셀마다 그 seed와
   arm만 담은 별도 등록 파일(이 파일 사본에 `seeds = <그 seed>`, `targets.node-tar-7.5.2.arms = <그 arm>`, 그 seed만 담은
   할당 파일과 sha)을 만들고 **새 출력 폴더**로 run_exp0를 그 호스트에서 다시 돌린다. "같은 설정"은 seed, arm, budget,
   정책, sentinel, 이미지, `engine_sha`, 셀 env가 같다는 뜻이다. 등록 sha와 회전 순서는 원 실행과 달라지며, 그 값을
   기록한다. 두 보고서를 `scripts/check_native_determinism.py`의 `compare_report_pair`로 비교해 `case_sequence`와
   `oracle_and_feedback` 일치 여부(불리언)만 남긴다. 재실행이 0이면 "재실행 0, 결정론 미검정"(UNKNOWN)이다.
7. **기록:** 원장에 smoke 행(호스트, seed, budget, 셀 수, 결정론 재실행 횟수, 봉인), LOG 1줄, raw manifest.

## 4. 결정된 사항 (적격성 검증 v1 §2, W4 답)과 남은 조건

1. **결정론 재실행:** 위 6단계의 (a) 방식이다.
2. **실행 조건:** 이 smoke는 W1 `launcher_guards`(#336) 배선이 들어간 통합 head에서만 실행한다(오케스트레이터
   방침). 그래서 잔존 리소스와 cleanup UNKNOWN은 런처가 판정하고, 위 2·4단계의 수동 대조는 보조 기록이 된다.
3. **docker 호출 timeout 수의 출처:** broker `.calls.jsonl`, #335 `anomalous_calls`, smoke cleanup CLI 진단 줄이다.
   보호 파일 원복 뒤에는 그 파일의 cleanup 재조회 진단 줄이 없으므로 출처로 쓰지 않는다.
4. **`host.<id>.docker_engine`:** 등록 파일을 채우기 전에 각 호스트의 `docker version --format
   '{{.Server.Version}}'`로 정한다. 지웅 결정(Engine B안)으로 HOST1 29.8.0, HOST2 29.9.3을 유지한다. HOST2 값은
   HOST2에서 확인한 뒤 고정한다.
5. **원장 sha:** 같은 `E`에서 도는 실행은 `E` 트리의 원장 sha를 쓴다(§3 1단계). smoke 행은 실행 뒤 `E` 뒤 커밋에
   넣고, exp3-v1·exp2-v1의 동결 sha는 정지·재개 smoke 2차 뒤에 고정한다.
6. **seed 충돌 검사:** 실행 전에 `RESERVED_SEED_RANGES`(`scripts/run_concurrency_benchmark.py:106`)와 원장의 seed
   서술(4자리 숫자와 `a–b` 범위)을 기계로 대조하고 LOG에 1줄 남긴다. 2026-11-11 원장 `9947d662…` 기준 6300–6303은
   예약 범위·원장 숫자·원장 범위·configs·preregistration·DECISIONS 어디에도 없다(충돌 0).
   **예외 1건(2026-11-11, ORCH 지시):** 정지·재개 smoke(D042, #346)의 6101–6104는 원장 :49(main 기준 :42)의
   벤치마크 v1 seed 예정 산문 "6100–6103"과 겹쳐 대조에 걸린다. 6101–6103은 LOG에도 원장 표에도 실행 행이 없다(원장
   :56은 6101–6103의 실행 여부를 확인하지 않았다고 적는다). D042가 6101–6104를 지정했으므로 이 겹침은 충돌로 보지
   않는다. 근거는 LOG에 한 줄로 남겼다. 다른 겹침은 예외가 아니다.
