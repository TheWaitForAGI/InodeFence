# run_exp0 엔지니어링 smoke v1 — 실행 등록 파일 (비등록, `demo run`)

> **상태: 초안(2026-11-11, W3).** 설계는 [동시 실행 벤치마크 v3](concurrency-scaling-v3.md) §5.1(#337)을 따른다.
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

## 2. 통과 조건 (v3 §5.1, 실행 전 고정)

| 조건 | 판정 근거(기록) |
| --- | --- |
| cleanup UNKNOWN 0 | 호스트별 `<out>/start-gate/*.verdict`에 `U` 0, `acknowledged/` 비어 있음 |
| 잔존 리소스 0 | 실행 뒤 `docker ps -a`·`docker volume ls`의 `inodefence-` 접두 대조(실행 전 목록과 차이 0) |
| 러너 실패 0 | `cell-results.jsonl` end 줄에 `runner_error` 0 |
| 시작 실패 0 | end 줄에 `start_denied` 0 |
| 기록 완전성 | index `cell_completeness`: 모든 셀이 complete 또는 abort-final, `record_inconsistent` 0, `no_record` 0 |
| 병합 검사 | `merge_host_indexes` exit 0(`merge.complete = true`) |
| 호스트 키 게이트 | 두 호스트의 실제 실행이 게이트를 통과(exit 2 거부 없음) |
| 인프라 정지 0 | `infrastructure-stop` 줄 0 |

보고만 하는 값: 셀별 `infra_reexecutions` 수, 재시도 수(셀당 start 줄 수), 운영 점검(`--host-output` 두 개) 출력.
결정론 검사(D046): `infra_reexecutions`가 있는 셀만 §3 6단계로 재실행해 `compare_report_pair`의 불리언만 보고한다.

## 3. 실행·병합·운영 점검 절차 (초안)

실행은 통합 후보 HOLD 해제 뒤 오케스트레이터 승인으로만 한다. 호스트마다 같은 절차다.

1. **값 고정(한 번, 두 호스트 공통):** 실행 SHA `E`를 정하고, `engine_sha = E`, `exposure_ledger_sha256 =` 그 시점 원장
   sha, `execution_deadline =` 예상 종료 + 여유(UTC 오프셋 포함), `host.<id>.docker_engine =` 각 호스트 preflight
   `docker version --format '{{.Server.Version}}'`를 채운다. 채운 파일은 `E` **뒤** 커밋에 있어도 된다. 런처는
   checkout HEAD를 `engine_sha`와 비교하므로, 실행은 `E`의 깨끗한 detached worktree에서 하고 `--preregistration`에는
   그 worktree 밖의 채운 파일 사본을 준다(EXP-0와 같은 방식).
2. **preflight(호스트별):** detached worktree `E`, `git status` 깨끗, venv python(uv.lock 생성 금지), `docker context
   show`, Server 버전, 이미지 id(`22c8734f…`, controller, helper; HOST2는 load 직후 대조), `docker ps -a`·`docker volume
   ls`의 `inodefence-` 접두 목록을 `<out>/preflight/`에 저장. dry-run:

   ```bash
   python -m scripts.run_exp0 --preregistration <filled.md> --output <out-HOSTn> \
     --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
     --observer-integrity-policy invalid-continue \
     --seed-assignment experiments/configs/run-exp0-eng-smoke-v1.assignment.json --host-id HOSTn \
     --jobs 2 --manifest-host hostn-eng-smoke --dry-run
   ```

   `gate: PASS`, wiring 거부 없음, cells 6, seeds 두 개를 확인한다.
3. **실행:** 같은 명령에서 `--dry-run`을 뺀다(HOST2는 `--skip-build`). 실행 중 운영 점검은 다른 터미널에서
   `python -m scripts.exp_operating_check --preregistration <filled.md> --output <out-HOSTn>`(출력은 수만).
4. **실행 뒤(호스트별):** `docker ps -a`·`docker volume ls`를 다시 저장해 1단계 목록과 대조, `start-gate/` 상태 확인,
   index `cell_completeness`와 `cell-results.jsonl`의 `runner_error`·`start_denied`·`infrastructure-stop` 수 확인.
5. **병합(한 곳):**

   ```bash
   python -m scripts.merge_host_indexes --preregistration <filled.md> \
     --seed-assignment experiments/configs/run-exp0-eng-smoke-v1.assignment.json \
     --host HOST1=<out-HOST1> --host HOST2=<out-HOST2> --output <out-merged>
   python -m scripts.exp_operating_check --preregistration <filled.md> \
     --host-output HOST1=<out-HOST1> --host-output HOST2=<out-HOST2>
   ```

6. **결정론 검사(재실행이 있었던 셀만):** 미정 — 아래 §4 1번.
7. **기록:** 원장에 smoke 행(호스트, seed, budget, 셀 수, 결정론 재실행 횟수, 봉인), LOG 1줄, raw manifest.

## 4. 구현상 불가능하거나 모호한 항목 (W4·오케스트레이터 결정 필요)

1. **결정론 재실행 방법이 정해지지 않았다.** run_exp0는 기록이 있는 셀을 다시 돌리지 않는다(기록은 최종). 같은
   seed·arm·budget을 한 번 더 돌리려면 (a) 그 seed·arm만 담은 별도 등록 파일(`targets.<id>.arms`)과 새 출력 폴더로
   run_exp0를 돌리거나 (b) `local_node_tar_smoke.sh demo-historical`을 같은 env로 직접 돌려야 한다. (a)는 등록 sha가
   달라지고 셀 순서·회전이 원 실행과 다르다. (b)는 런처 경로가 아니다. 어느 쪽이 "같은 설정"인지 정해야 한다.
2. **"잔존 리소스 0"·"cleanup UNKNOWN 0"은 지금 사람이 기록으로 판정한다.** run_exp0의 잔존 리소스 확인과 preflight는
   W1 `launcher_guards`(#336) 배선 뒤에 런처가 한다. #336 전에 smoke를 돌리면 위 2·4단계의 수동 대조가 판정 근거다.
3. **"docker 호출별 timeout 수"는 보호 파일 원복 뒤 기록이 사라진다.** 그 수는 `container.py`의
   `inodefence-cleanup-attempt` stderr 줄에서 나오는데, 이 변경은 지웅 A안으로 원복된다. 원복 뒤에는 #335의
   `infra_reexecutions`와 smoke.sh 진단만 남는다. 이 항목을 빼거나 출처를 바꿔야 한다.
4. **`docker_engine` 고정 시점:** HOST2 Engine 버전을 모르는 채로 파일을 채울 수 없다. HOST2 preflight 값이
   1단계보다 먼저 와야 한다.
5. **원장 sha 시점:** smoke 결과 행을 원장에 넣으면 sha가 바뀐다. 이 파일의 `exposure_ledger_sha256`은 실행 직전
   원장 값이고, smoke 행은 실행 뒤에 넣는다. exp3-v1·exp2-v1의 동결 sha는 smoke 행까지 넣은 뒤 정한다.
6. **seed 6300–6303은 벤치마크 `RESERVED_SEED_RANGES` 밖이다.** run_exp0는 그 목록을 검사하지 않으므로 충돌 검사는
   문서 대조뿐이다(v3 §5.1 확인).
