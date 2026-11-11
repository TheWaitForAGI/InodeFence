# 호스트 적격성 실행 v1 — 실행 등록 파일 (비등록, `demo run`)

> **상태: 초안(2026-11-11, W3).** 설계는 [호스트별 적격성 검증 v1](host-qualification-v1.md) §3(D047)을 따른다.
> **비등록이고 EXP-3·EXP-2 데이터가 아니다.** n, k, arm, EXP-2 GO의 입력이 아니다. oracle은 봉인한다
> (`interim_analysis = forbidden`). 사전등록 *형식*을 빌려 런처의 등록 게이트(호스트 키, 할당 규칙, Engine,
> jobs)를 적격성 실행에서도 그대로 강제하려는 것이며, `experiments/preregistration/` 밖에 둔다.
>
> `TBD-FREEZE` 값이 남아 있는 동안 파서가 실행을 거부한다(의도된 동작). 값은 §3 절차 1단계에서 채운다.

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

## 2. 판정과 기록

- 판정: `scripts/qualify_host.py`(적격성 검증 v1 §5 Q1~Q10과 입력 종속 검사). 기준 파일(임계, 기대 이미지 id 3개,
  셀 수 12)의 sha256은 측정 전에 LOG에 고정하고, 판정 때 `--criteria-sha256`으로 준다.
- 입력 종속 검사 전제(§12): 실행 전에 `qualify_host --check-environment`로 Stage A 셀 환경(정책 문자열, mutation
  policy, vocabulary, sentinel, `observer_integrity_policy`, budget, seed)과 대조한다. Stage A 키 파일은
  `~/inodefence-evidence/stage-a-j2-abort-keys-20261111/stage-a-j2-abort-keys-v3.json`(sha `3e6c734c…`, W4 봉인 확인
  대상)이다. 무효면 실행 전에 LOG에 적는다.
- 교차 호스트 비교(보고만, §7): `merge_host_indexes --compare`. 설명 절차의 재실행 대조는 `compare_cell_paths`.
- 시계 차(기록만, §4): 각 호스트 `measure_clock_offset` → `run_exp0 --clock-reference`, 시작·끝에 측정한다.

## 3. 실행 절차 (초안)

1. **값 고정:** 실행 SHA `E`, 원장 sha(실행 직전), `execution_deadline`, `host.<id>.docker_engine`(HOST1 29.8.0,
   HOST2 29.9.3; 각 호스트 preflight `docker version`으로 확인 뒤)을 채운 사본을 만든다. 실행은 `E`의 깨끗한
   detached worktree에서, 채운 사본은 worktree 밖에 둔다.
2. **실행 전 점검(§12):** `--check-environment`, seed 충돌 기계 대조 1줄, 원장 계획 1줄, 봉인 통지.
3. **실행(호스트별, 독립):**

   ```bash
   python -m scripts.run_exp0 --preregistration <filled.md> --output <out-HOSTn> \
     --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
     --observer-integrity-policy invalid-continue \
     --seed-assignment experiments/configs/host-qualification-v1-run.assignment.json --host-id HOSTn \
     --jobs 2 --clock-reference <offset-HOSTn.json> --manifest-host hostn-qual
   ```

   먼저 `--dry-run`으로 `gate: PASS`, cells 12를 확인한다. HOST2는 `--skip-build`.
4. **판정(호스트별):** `qualify_host --output <out-HOSTn> --criteria <criteria.json> --criteria-sha256 <고정값>
   --stage-a-keys <v3> --stage-a-keys-sha256 <v3 sha> [--peer <out-다른 호스트>] --out qualification-HOSTn.json`.
5. **기록:** 원장 행(호스트별, 적격성 §3 형식), LOG 1줄, raw manifest.
