# D042 정지·재개 smoke 1차 — 실행 등록 파일 (비등록, `demo run`)

> **상태: 초안(2026-11-11, W1).** 판정 기준과 절차는 [정지·재개 smoke v1](stop-path-smoke-v1.md)(D042)를 따른다.
> **비등록이고 판정 입력이 아니다.** EXP-3·EXP-2 데이터, 벤치마크 판정, 사전등록 값에 쓰지 않는다. oracle은
> 봉인한다(`interim_analysis = forbidden`). 사전등록 *형식*은 런처의 등록 게이트와 targets 형식(InfrastructureGuard,
> StartGate)을 실제로 타기 위해 빌렸을 뿐이다. 그래서 `experiments/preregistration/` 밖에 둔다.
>
> `TBD-FREEZE` 값이 남아 있는 동안 파서가 실행을 거부한다(의도된 동작). 값은 아래 §2의 1단계에서 채운다.

## 1. 등록 블록

[엔지니어링 smoke](run-exp0-eng-smoke-v1.md)와 다른 값은 `experiment_id`, `seeds`(D042가 정한 6101~6104), `budget`(20)이다.
단일 호스트 실행이라 `host.*` 키와 seed 할당 키가 없다. 따라서 `--host-id`·`--seed-assignment` 없이 돌고,
`--expected-images`는 선택이지만 쓴다(X3의 preflight `image_ids` 대조).

```preregistration
# D042 stop-path smoke round 1 (demo run, not registered). Fill TBD-FREEZE per section 2 step 1.
experiment_id = stop-path-smoke-1
engine_sha = TBD-FREEZE
seeds = 6101, 6102, 6103, 6104
budget = 20
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
```

**seed 충돌 기계 대조:** 원장 :42의 "아직 노출이 아닌 예정" 산문에 동시 실행 벤치마크 seed "6100–6103"이 있다.
그래서 eng-smoke 방식의 대조가 6101~6103을 잡는다. 그 벤치마크는 실행되지 않았다(예정 산문). D042가
6101~6104를 정했으므로 실행 전 LOG에 이 예외를 한 줄 남긴다.

## 2. 절차 (HOST1, 실행 SHA의 깨끗한 detached worktree에서)

`<E>`는 실행 SHA, `<S>`는 worktree **밖**의 작업 폴더다. 출력·raw manifest·채운 사본·스냅샷은 모두 `<S>` 아래에 둔다.
저장소 안에 쓰면 checkout이 dirty가 되어 postflight가 문제로 기록하고, 호스트 실행은 시작 전에 거부된다.

0. **실행 코드 확인:** 모든 명령은 실행 worktree에서 `PYTHONPATH=src` 접두로 부른다(venv의 .pth가 다른 체크아웃을 가리킬 수 있다). 먼저 `PYTHONPATH=src python -c "import inodefence; print(inodefence.__file__)"`가 이 worktree의 `src/inodefence/__init__.py`인지 확인한다.
1. **값 채우기:** `sha256sum experiments/preregistration/exposure-ledger.md`로 원장 sha를 얻고 기준 파일과 사본을 만든다.
   ```bash
   PYTHONPATH=src python -m scripts.make_run_criteria --execution-sha <E> --host HOST1 --out <S>/criteria-HOST1.json
   PYTHONPATH=src python -m scripts.fill_run_registration experiments/configs/stop-path-smoke-1-v1.md \
     --set engine_sha=<E> --set exposure_ledger_sha256=<원장 sha> \
     --set execution_deadline=<예상 종료+여유, +09:00> --out <S>/stop-path-smoke-1-filled.md
   ```
2. **dry-run:** 아래 공통 인자에 `--dry-run`을 붙여 gate PASS, 12셀, "would be refused: (nothing)"을 확인한다.
3. **B-0~B-5 실행:** 공통 인자는 다음과 같다.
   ```bash
   PYTHONPATH=src python -m scripts.run_exp0 --preregistration <S>/stop-path-smoke-1-filled.md --output <S>/out \
     --target-digest node-tar-7.5.2=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
     --observer-integrity-policy invalid-continue --jobs 2 --skip-build \
     --expected-images <S>/criteria-HOST1.json --manifest-out <S>/raw-manifest.sha256 --manifest-host host1-spsmoke
   ```
   B-1만 `HISTORICAL_IMAGE=inodefence-node-tar-effect:does-not-exist`를 런처 환경에 둔다(stop-path-smoke-v1 §4).
   B-4는 원인 LOG 1줄과 지웅 승인 뒤 `--resume-after-stop D042-smoke-1-B-<YYYYMMDD>-<HHMM>`로 실행한다.
4. **스냅샷(판정 입력):** 각 호출 직후와, B-2·B-4·B-5 각 호출 직전에 다음을 한 번씩 남긴다. 호출의 exit code와 stderr 파일도 넘긴다.
   ```bash
   PYTHONPATH=src python -m scripts.check_stop_path_smoke snapshot --output <S>/out --snapshots <S>/snaps \
     --stage <b0|b1|pre-b2|b2|pre-b4|b4|pre-b5a|b5a|pre-b5b|b5b> --exit-code <rc> --stderr <S>/stderr-<stage>.txt \
     [--manifest <S>/raw-manifest.sha256]   # pre-b5b와 b5b에서
   PYTHONPATH=src python -m scripts.check_stop_path_smoke verify-tools --output <S>/out --snapshots <S>/snaps \
     --manifest <S>/raw-manifest.sha256    # B-5 뒤
   PYTHONPATH=src python -m scripts.check_stop_path_smoke judge --snapshots <S>/snaps --round 1 \
     --cause-logged-at <원인 LOG 줄의 epoch 초> --out <S>/judgement-1.json \
     [--scenario-a-snapshots <S>/snaps-a]  # 시나리오 A(a1, a-refused, a2, a-final)는 합격에 넣지 않는다
   ```
   스냅샷과 판정 출력에는 키·개수·해시만 있고 oracle 값은 없다. 각 호출의 stderr는 `2> <S>/stderr-<stage>.txt`로 받아 스냅샷에 넘긴다.
   시나리오 A는 출력·manifest·스냅샷을 모두 따로 둔다(같은 `--manifest-out`을 쓰면 B의 raw manifest를 덮어쓴다). 공통 인자에서 `--output <S>/out-a --manifest-out <S>/raw-manifest-a.sha256 --manifest-host host1-spsmoke-a`로 바꾼다. 주입 `INODEFENCE_DOCKER_CONTEXT=does-not-exist`는 첫 호출(a1)의 런처 환경에만 둔다. 거부 확인(a-refused), ack 뒤 재개(a2), 마지막 호출(a-final)에는 두지 않는다. 스냅샷은 `snapshot --output <S>/out-a --snapshots <S>/snaps-a --stage <a1|a-refused|a2|a-final>`로 각 호출 직후에 남긴다.
   시나리오 A(별도 출력 폴더): 지웅의 재개 승인은 1회다. 그 참조 `D042-smoke-1-A-<YYYYMMDD>-<HHMM>` 하나로 게이트 판정 U인 셀을 **모두** ack한 뒤(`PYTHONPATH=src python src/inodefence/execution/start_gate.py ack <S>/out-a/start-gate <cell> "approval=<참조>; checked_at=…; by=…; residual=<읽기 전용 잔존 확인 → 결과>; reason=…"`, U 셀마다), `--resume-after-stop <참조>`로 재개한다.
5. **원장:** 실행 뒤 stop-path-smoke-v1 §7의 행 초안을 실제 셀 수로 채워 1행씩 추가한다.
