# 양성 대조 (가) v1 — 실행 등록 파일 (비등록, `demo run`, 결과 공개 셀)

> **상태: 초안(2026-11-12, W3). 설계는 저장소 밖 팀 검토 문서 `positive-control.md` §7(W4 소유, W3 교차 서명)이다.**
> **비등록이고 EXP-3·EXP-2 데이터가 아니다.** 목적은 실행 SHA E의 캠페인 실행 경로에서, 기노출 대상 node-tar 7.5.2에 대해 파일럿 사전점검 P1과 같은 조건(S-u, seed 8002, k = 5, budget 2000)의 탐색 1셀이 예산 안에 사건을 내는지 확인하는 것이다(경로·탐색 민감도). 결과(사건 여부, T_first, 첫 사건의 contract id)는 **공개 대상**이다. 다른 결과 값은 열지 않는다.
> 사전등록 *형식*은 런처의 등록 게이트를 통과시키기 위해 빌린 것이다. 호스트마다 할당 sha가 달라서 파일을 두 개(`-HOST1`, `-HOST2`) 둔다. 두 파일은 `experiment_id`와 `seed_assignment_sha256`만 다르다.

## 1. 등록 블록 (HOST1용. HOST2용은 `experiment_id = positive-control-a-host2`와 그 할당 sha만 다르다)

```preregistration
# positive control (a) v1 (demo run, not registered). Fill TBD-FREEZE per section 3.
experiment_id = positive-control-a-host1
engine_sha = TBD-FREEZE
seeds = 8002
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
targets.node-tar-7.5.2.arms = S-u
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
jobs_max = 1
campaign_watchdog_seconds = 10800
disk_pause_fraction = 0.9
interim_analysis = forbidden
execution_deadline = TBD-FREEZE
host.HOST1.jobs = 1
host.HOST1.docker_engine = TBD-FREEZE
host.HOST2.jobs = 1
host.HOST2.docker_engine = TBD-FREEZE
seed_assignment_rule = alternate-v1
seed_assignment_sha256 = TBD-FREEZE
```

**파일럿 P1과의 대응(W1 cell_env 대조, 글자 단위).** P1 로그 머리(`~/inodefence-evidence/exp3-hazard-pilot-20261106-smoke-k5/p1/raw/7.5.2-S-u-s8002.log`)에는 `policy=effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1`, `mutation_policy=uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1`(`observed-names`의 정책, `src/inodefence/mutator/policy.py:55`), `observer_integrity_continue=True`, seed 8002, budget 2000이 찍혀 있다. 이미지 id `22c8734f…`와 Engine 29.8.0(HOST1)도 같다. P1은 jobs 1이었다(드라이버 밖 단독 실행). 다른 점은 실행 SHA(P1 `007d8e4a` → E)와 런처(P1은 `local_node_tar_smoke.sh demo-historical` 직접 호출, 여기서는 run_exp0가 같은 스크립트를 셀마다 호출)다.

할당 파일은 [`positive-control-a-v1.HOST1.assignment.json`](positive-control-a-v1.HOST1.assignment.json)(8002 → HOST1)과 [`positive-control-a-v1.HOST2.assignment.json`](positive-control-a-v1.HOST2.assignment.json)(8002 → HOST2)이다. `make_seed_assignment --rule alternate-v1 --participants HOSTn`이 같은 바이트를 다시 만든다(sha `2df19abf…70ea`, `58e0807e…589b`).

## 2. 통과 조건과 읽는 값 (실행 전 고정, §7.2)

- **PASS:** 예산 안에 C1 ∨ C2 ∧ contract_violated 사건이 1개 이상 있다(`hit = true`).
- **읽는 값(이 셀만, 키 추출):** `hit`, `t_first`, `t_first_event`, 첫 사건 step의 위반 계약 id(C1/C2), `infra_reexecution_count`, abort 여부와 사유. 그 밖의 값은 열지 않는다. 추출기는 저장소 밖 `pc_keys.py`이고 sha를 실행 전 LOG 줄에 고정한다.
- **보조:** T_first = 685(파일럿 P1, 공개값) 일치 여부. 일치하지 않아도 FAIL이 아니다(§7.0: 셀 실행 경로 파일이 바뀌었다).
- 해석은 §7.3 표를 따른다.

## 3. 절차 (호스트별, 승인 참조 `PC-A-<HOSTn>-<YYYYMMDD>-<HHMM>`)

1. E의 깨끗한 detached worktree, `PYTHONPATH=src`, `inodefence.__file__` 확인(적격성 런북 §3-4와 같다).
2. 기준 파일: 적격성에 쓴 `criteria-HOSTn.json`(E, 이미지 id 3개)을 `--expected-images`에 그대로 쓴다.
3. 등록 채움(worktree 밖): `fill_run_registration`로 `engine_sha=E`, `exposure_ledger_sha256=8a832e19b7826de3f3dcfe95a667cb82df91eb6d6e7a5fc0b55649a56565a508`(E 트리 원장), `execution_deadline`, Engine(HOST1 29.8.0, HOST2 29.9.3), `seed_assignment_sha256`. 할당 sha는 W4 순서(임시 sha로 채운 사본 → `make_seed_assignment --rule alternate-v1 --participants HOSTn` → 출력 sha 기입)로 정한다.
4. dry-run: `gate: PASS`, cells 1(`node-tar-7.5.2-S-u-s8002`).
5. 실행:

```bash
PYTHONPATH=src python -m scripts.run_exp0 --preregistration <positive-control-a-HOSTn-filled.md> --output <out-pc-a-HOSTn> \
  --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
  --observer-integrity-policy invalid-continue \
  --seed-assignment <pc-a-HOSTn.assignment.json> --host-id HOSTn \
  --jobs 1 --manifest-host hostn-pc-a \
  --manifest-out <worktree 밖>/raw-manifest-hostn-pc-a.sha256 \
  --expected-images <criteria-HOSTn.json> --skip-build
```

6. 끝나면 `pc_keys.py <out>`으로 §2의 값만 뽑아 `<evidence>/pc-a-keys-HOSTn.txt`에 저장하고 sha를 남긴다.
7. 기록: 원장 행(호스트별 1행, §7.4), LOG 한 줄(실행 전 고정 줄과 결과 줄).

**예상 시간:** P1 실측 2710 s(HOST1, 45분). HOST2는 처리량 비를 쓰면 약 25분이다(추정).
