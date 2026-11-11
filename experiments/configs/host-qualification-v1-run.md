# 호스트 적격성 실행 v1 — 실행 등록 파일 (비등록, `demo run`)

> **상태: 초안(2026-11-11, W3).** 설계는 [호스트별 적격성 검증 v1](host-qualification-v1.md) §3(D047)을 따른다.
> **비등록이고 EXP-3·EXP-2 데이터가 아니다.** n, k, arm, EXP-2 GO의 입력이 아니다. oracle은 봉인한다
> (`interim_analysis = forbidden`). 사전등록 *형식*을 빌려 런처의 등록 게이트(호스트 키, 할당 규칙, Engine,
> jobs)를 적격성 실행에서도 그대로 강제하려는 것이며, `experiments/preregistration/` 밖에 둔다.
>
> `TBD-FREEZE` 값이 남아 있는 동안 파서가 실행을 거부한다(의도된 동작). 값은 §3 절차 1·2단계에서 채운다.

## 1. 등록 블록

exp3-v1(#332)과 다른 값은 `experiment_id`, `seeds`, `execution_deadline`, `seed_assignment_rule = replicate-v1`과
그 `seed_assignment_sha256`뿐이다. budget 2000, arm, 대상, sentinel, watchdog, `jobs_max = 2`, `host.<id>.jobs = 2`는
exp3-v1과 같다. `replicate-v1`은 두 호스트가 등록 seed 전부(같은 12셀)를 받는 규칙이다. 확증 대비와 holdout 타깃이
없는 등록에서만 파서가 받는다.

```preregistration
# host qualification v1 (demo run, not registered). Fill TBD-FREEZE per section 3 step 1.
experiment_id = host-qual
engine_sha = TBD-FREEZE
seeds = 8110, 8102, 8103, 8106
budget = 2000
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
seed_assignment_rule = replicate-v1
seed_assignment_sha256 = e81d5fcff7976fe4527da62303bb66e728eb86f7c672dc8556a800562e7d29b3
```

할당 파일은 [`host-qualification-v1-run.assignment.json`](host-qualification-v1-run.assignment.json)이다(두 호스트
모두 8110, 8102, 8103, 8106). `python -m scripts.make_seed_assignment --rule replicate-v1`이 같은 바이트를 다시 만든다.
한 호스트만 참여하면 `--participants HOSTn`으로 만든 파일과 그 sha로 바꾼다(동결 전 결정, D047 §9).

**호스트 키와 참여(ORCH 결정 (b)).** 파서는 참여 호스트가 하나여도 `host.HOST1.*`·`host.HOST2.*` 키를 모두
요구한다. 참여하지 않는 호스트의 키는 형식상 기재일 뿐이고, 참여 여부는 할당 파일의 `participants`(와 holdout은 GO
파일)가 정한다. 비참여 호스트의 키를 참여로 읽지 않는다.
**할당 파일을 만드는 순서(W4).** `make_seed_assignment`는 `TBD`가 남은 등록 파일을 거부한다. 그래서 다른 값을 모두
채우고 `seed_assignment_sha256`만 임시값(64자리 hex)으로 둔 사본에서 할당 파일을 만든 뒤, 출력된 sha를 그 칸에
채운다.

## 2. 판정과 기록

- 판정: `scripts/qualify_host.py`(적격성 검증 v1 §5 Q1~Q10과 입력 종속 검사). 기준 파일(임계, 셀 수 12, 기대값:
  이미지 id 3개, 호스트별 Docker Engine, 공유 경로 16개 해시, 실행 SHA `E`; 키 누락·빈 값은 거부)의 sha256은 측정 전에 LOG에 고정하고, 판정 때 `--criteria-sha256`으로 준다.
- 입력 종속 검사 전제(§12): 실행 전에 `qualify_host --check-environment`로 Stage A 셀 환경(정책 문자열, mutation
  policy, vocabulary, sentinel, `observer_integrity_policy`, budget, seed)과 대조한다. Stage A 키 파일은
  `~/inodefence-evidence/stage-a-j2-abort-keys-20261111/stage-a-j2-abort-keys-v3.json`(sha `3e6c734c…`, W4 봉인 확인
  대상)이다. 무효면 실행 전에 LOG에 적는다.
- 교차 호스트 비교(보고만, §7): `merge_host_indexes --compare`. 설명 절차의 재실행 대조는 `compare_cell_paths --rerun HOSTn:<셀>=<원 실행>,<재실행>`이다. 출력은 셀별
  설명 상태, HOST1·HOST2 단독 비결정성 수, 설명 안 되는 호스트 종속 수다.
- 시계 차(기록만, §4): 각 호스트 `measure_clock_offset` → `run_exp0 --clock-reference`, 시작·끝에 측정한다.

## 3. 실행 절차 (초안)

**사람 승인 지점(지웅).** 단계 실행은 사람 승인 게이트다. 아래 승인 없이는 시작하지 않는다.

| 단계 | 승인 대상 | 승인 참조 형식 |
| --- | --- | --- |
| 1 | 런처 smoke 실행([run-exp0-eng-smoke-v1](run-exp0-eng-smoke-v1.md)) | `ENGSMOKE-<HOSTn>-<YYYYMMDD>-<HHMM>` |
| 2 | 정지·재개 smoke 1차 실행(D042, #346) | `D042-smoke-<차수>-<B\|A>-<YYYYMMDD>-<HHMM>` |
| 3 | 정지·재개 smoke의 재개(B, A 각 1회) | 위와 같은 형식, 재개마다 새 참조 |
| 4 | 적격성 실행(호스트별) | `QUAL-<HOSTn>-<YYYYMMDD>-<HHMM>` |
| 5 | 적격성 실행 중 정지 뒤 재개 | 같은 형식, 재개마다 새 참조 |

1. **실행 SHA와 기준 파일(순서 고정):** (a) 실행 SHA `E`를 정한다. (b) `E`에서 기준 파일을 만든다(임계, 셀 수 12,
   이미지 id 3개, 호스트별 Engine, 공유 경로 16개 해시, `expected_execution_sha = E`). 생성 명령(`E`의 깨끗한
   detached worktree에서, 읽기만 한다): `PYTHONPATH=src python -m scripts.make_run_criteria --execution-sha <E> --host HOST1 --engine HOST2=29.9.3 --out <worktree 밖>/criteria.json`. (c) 기준 파일 sha256을
   LOG에 고정한다. (d) 그 뒤에 실행한다. 기준 파일은 worktree 밖에 둔다.
2. **등록 값 채움:** `engine_sha = E`, `execution_deadline`, `host.<id>.docker_engine`(HOST1 29.8.0, HOST2 29.9.3; 각
   호스트 preflight `docker version`으로 확인 뒤)을 채운 사본을 worktree 밖에 만든다: `PYTHONPATH=src python -m scripts.fill_run_registration <이 파일> --set engine_sha=<E> --set exposure_ledger_sha256=<E 트리의 원장 sha> --set execution_deadline=<UTC 오프셋 포함> --set host.HOST1.docker_engine=29.8.0 --set host.HOST2.docker_engine=29.9.3 --out <worktree 밖>/<이름>-filled.md`. 이 도구는 worktree 안 출력과 남은 `TBD-FREEZE`를 거부한다.
   **원장 sha:** 실행 뒤의 원장 행은 `E` **뒤** 커밋에 들어가므로, 같은 `E`에서 도는 실행들의
   `exposure_ledger_sha256`은 `E` 트리의 원장 sha 그대로다(a76ffee에서는 `8a832e19…`). 본실험 동결 sha는 정지·재개
   smoke 2차 뒤에 고정한다.
3. **실행 전 점검(§12):** `--check-environment`, seed 충돌 기계 대조 1줄, 원장 계획 1줄, 봉인 통지.
4. **코드 경로 점검(두 호스트 공통):** 모든 명령은 실행 worktree `E`에서 `PYTHONPATH=src`를 붙여 실행한다. venv의
   `.pth`가 다른 체크아웃의 `src`를 가리킬 수 있기 때문이다(HOST2에서 `No module named
   inodefence.evaluation.cell_completeness`로 확인). 실행 전에
   `PYTHONPATH=src python -c "import inodefence; print(inodefence.__file__)"`의 출력이 실행 worktree의 `src/` 아래인지
   확인하고, 아니면 시작하지 않는다.
5. **이미지(#345):** 런처의 preflight가 warmup보다 먼저 돌며 target·controller·helper id를 `--expected-images`(기준
   파일의 `expected_image_ids`)와 대조하고, 다르면 시작 전에 거부한다. HOST1은 이미지를 확인만 하고, HOST2는
   `docker load`로 미리 넣은 뒤 `docker image inspect`로 3개 id를 대조한다. **두 호스트 모두 `--skip-build`로
   실행한다**(빌드 캐시가 같은 id를 낼지는 실 docker에서 확인하지 않았다). **dry-run PASS는 이미지 preflight를 대신하지
   않는다:** dry-run은 이미지가 하나도 없어도 `gate: PASS`다(로컬 이미지 존재와 id 대조는 live preflight에서만 한다).
6. **실행(호스트별, 독립, 승인 4):**

   ```bash
   PYTHONPATH=src python -m scripts.run_exp0 --preregistration <filled.md> --output <out-HOSTn> \
     --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
     --observer-integrity-policy invalid-continue \
     --seed-assignment experiments/configs/host-qualification-v1-run.assignment.json --host-id HOSTn \
     --jobs 2 --clock-reference <offset-HOSTn.json> --manifest-host hostn-qual \
     --manifest-out <worktree 밖>/raw-manifest-hostn-qual.sha256 \
     --expected-images <criteria.json> --skip-build
   ```

   먼저 `--dry-run`으로 `gate: PASS`, cells 12를 확인한다. **`--manifest-out`은 반드시 worktree 밖이다:** 기본 경로는
   저장소 안(`experiments/summaries/raw-manifest-<host>-<date>.sha256`)이라 실행 worktree를 더럽히고, postflight의
   실행 SHA 검사가 dirty로 실패한다.
7. **정지 시 재개:** 인프라 정지(`infrastructure-stop`)가 나면 원인을 기록하고 지웅에게 다음 문구로 승인을 요청한다:
   "적격성 <HOSTn> 실행이 <시각>에 인프라 정지했습니다. 원인: <원인 기록 경로·요약>. 잔존 리소스: <0 또는 목록>.
   재개 승인 참조 `QUAL-<HOSTn>-<YYYYMMDD>-<HHMM>`를 요청합니다." 승인되면 같은 명령에
   `--resume-after-stop QUAL-<HOSTn>-<YYYYMMDD>-<HHMM>`을 붙여 실행한다. 정지가 있었던 호스트는 Q5로 FAIL이다(재개는
   기록 완성용이고 판정을 바꾸지 않는다).
8. **판정(호스트별, 호스트 독립):**

   ```bash
   PYTHONPATH=src python -m scripts.qualify_host --preregistration <filled.md> \
     --seed-assignment experiments/configs/host-qualification-v1-run.assignment.json --host-id HOSTn \
     --output <out-HOSTn> --criteria <criteria.json> --criteria-sha256 <LOG에 고정한 값> \
     --stage-a-keys <v3> --stage-a-keys-sha256 3e6c734cf5a87865b7627165a8e1aafffd10685553000499630f9194fc56322b \
     --out qualification-HOSTn.json
   ```

   `--peer`가 없으면 두 호스트 대조(`equal_to_peer`)와 시계 차(`clock_difference`)는 나오지 않는다. **두 호스트가 모두
   끝난 뒤** 같은 명령에 `--peer <out-다른 호스트>`를 붙여 `qualification-HOSTn-peer.json`으로 한 번 더 돌린다(호스트별
   판정은 첫 실행이 기준이고, 두 번째는 Q6 대조와 시계 차를 더한다). 판정 결과는 `PASS`·`FAIL`·
   `STOPPED-INPUT-DEPENDENT`(Stage A와 같은 입력에서 abort 재발: 적격 판정을 내지 않는다)·`NOT-RUN`(시도한 셀 없음)이다.
   **한계:** 실행 SHA는 preflight와 postflight에서만 대조한다. 실행 중 체크아웃이 바뀌었다가 postflight 전에 원래대로
   돌아가면 잡지 못한다. 실행 worktree를 호스트 전용 detached worktree로 두고 실행 중 아무도 건드리지 않는 규칙으로
   이 위험을 줄인다.
9. **교차 호스트 비교(보고만, §7):** `merge_host_indexes --compare`. 비교 불가 셀은 기록이 없는 쪽 호스트에서 그 셀을
   다시 돌린 뒤, `compare_cell_paths --pair <셀>=<HOST1 steps>,<HOST2 steps> --out <파일>`을 재실행본으로 다시 호출해
   상대 호스트의 원 실행과 대조한다. 설명 절차의 자기 재실행 대조는 `--rerun HOSTn:<셀>=<원 실행>,<재실행>`이다.
10. **기록:** 원장 행(호스트별, 적격성 §3 형식), LOG 1줄, raw manifest(worktree 밖 경로).
