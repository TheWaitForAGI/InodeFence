# 작업 큐 (BACKLOG)

자율 루프(`.claude/skills/autoloop/SKILL.md`)가 읽는 할 일 목록이다. **맨 위부터 순서대로** 진행한다.
완료 기록은 [WORKLOG](WORKLOG.md), 실행 기록은 [LOG](LOG.md)에 남긴다.

분류: 아래 항목은 P0-1~P0-5가 아니다. P0 데모 루프(`make demo-native`)는 동작 상태다([STATUS](STATUS.md)).
이 항목들은 팀이 정한 다음 단계(Phase 2: 11/30 최종 연구용 N01 rediscovery 기반, Phase 3: [MIDTERM_GOALS](MIDTERM_GOALS.md) P1 A/B/C 비교)다.
P0 작업이 새로 생기면 이 표 맨 위에 끼워 넣는다.

상태 값: `대기` / `진행` / `완료(<브랜치>)` / `막힘(<날짜>, <이유>)` / `BREAKING(<브랜치>)` / `대기(머지 필요: <브랜치>)`

| 순서 | ID | 상태 | 게이트 |
| --- | --- | --- | --- |
| 1 | P2-a C1 일반화 영향 조사 | 대기 | 없음 |
| 2 | P2-b C1 일반화 + `add_hardlink` 외부 타깃 확장 | 완료(jiwoong/p2-b-c1-generalize-hardlink) | P2-a = "안전", P2-a 브랜치 머지 |
| 3 | P2-c N01 rediscovery 재실행 | 완료(jiwoong/p2-c-n01-rediscovery, 부분결과·native 무결성중단·oracle 미발견) | P2-b 머지 + 사람이 승인한 실행 범위 |
| 4 | P3 A/B/C 비교 실험 | 대기 | P2-c rediscovery 성공 |

---

## P2-a. C1 일반화 영향 조사

- 분류: Phase 2 (조사, 코드 판정 변경 없음)
- 환경: Dev Container
- 할 일:
  - 현재 C1 정의 확인: `src/inodefence/oracle/contracts.py`의 `evaluate_contracts` — post-state에서 extraction 내부 object와 protected sentinel의 lstat identity 공유만 본다. 일반화 후보(예: sentinel 외 extraction root 밖 object와의 identity 공유)를 [security-contracts](research/design/security-contracts.md) 정의와 대조해 구체적인 변경안 1개로 적는다.
  - 그 변경안을 **커밋하지 않는 실험 브랜치/임시 패치**로 적용해 영향을 실제로 실행해서 확인한다:
    - `make check` 전체 (특히 `tests/test_oracle_fixtures.py`, `tests/test_feedback_search_contracts.py`)
    - `PYTHONPATH=src python -m scripts.oracle_fixture_check` 4/4 판정 유지 여부
    - N01 경로: `src/inodefence/evaluation/n01_candidate_match.py`가 C1 relation(`_relations`, `_violated(..., C1)`)에 의존한다. N01 replay/검증 테스트가 그대로 통과하는지
    - FROZEN 입력/타깃(`src/inodefence/evaluation/n01.py`)과 기존 qualification 모드 검증이 영향을 받는지
- 완료 조건: 위 각 검사에 대해 통과/실패를 실제 실행 출력으로 기록하고, 판정을 `안전`(기존 판정·테스트 불변, 추가만) 또는 `깨뜨린다`(어느 테스트/fixture/경로가 왜) 중 하나로 낸다. 결과는 LOG 한 줄 + STATUS 갱신. 새 audit 문서를 만들지 않는다.
- 실행/검증하게 되는 것: C1 일반화가 기존 C0/C1/C2 의미와 N01 경로를 보존하는지를 실행 결과로 판단할 수 있다.
- `깨뜨린다`이면: WORKLOG에 `BREAKING`으로 기록하고 **P2-b를 자동 진행하지 않는다.** P2-b/P2-c/P3는 사람 결정 전까지 건너뛴다. 진행할 다른 안전 항목이 없으면 대기한다.

## P2-b. C1 일반화 + `add_hardlink` 외부 타깃 확장

- 분류: Phase 2 (oracle + mutator 변경)
- 환경: Dev Container
- 게이트: P2-a 판정 `안전`, P2-a 브랜치가 main에 머지됨.
- 할 일:
  - C1 일반화는 기존 C1 판정을 바꾸지 않고 **추가**로 구현한다(새 evidence 또는 별도 판정 경로). 기존 fixture 기대값은 그대로 둔다. 새 경계 사례 fixture를 추가한다.
  - `add_hardlink`(`src/inodefence/mutator/m1.py`, `m1_addressing.py`)는 현재 archive 안 entry path만 link target으로 고른다. archive 밖(extraction root 바깥, sandbox sentinel 방향) 대상을 고를 수 있는 **새 operator 또는 옵션**으로 확장한다. 기존 operator의 분포와 seed 재현성은 바꾸지 않는다. 특정 CVE PoC 경로를 하드코딩하지 않는다(generic 경로 생성).
  - 새 operator가 effect campaign 스케줄러에서 선택 가능하도록 연결하고, `make demo`(synthetic)로 선택·피드백 경로가 동작하는지 확인한다.
- 완료 조건: `make check` 통과, 기존 oracle fixture 4/4 유지, 새 fixture에서 일반화된 C1이 기대대로 판정, `make demo` 두 번 실행 결과 바이트 동일. 기존 테스트를 깨면 `BREAKING`.
- 실행/검증하게 되는 것: 외부 대상 hardlink를 생성하는 mutation과, 그 결과를 잡는 일반화된 C1 판정을 synthetic 루프에서 실행할 수 있다.
- 완료(2026-10-24, `jiwoong/p2-b-c1-generalize-hardlink`, base=`jiwoong/guard-destructive-block`): docker Dev Container(`inodefence-envprobe`) 안에서 `make check` 검증. 결과: 베이스라인 1722 pass/1 fail → 변경후 1737 pass/1 fail(새실패 0; 유일 실패는 C1·mutator 무관 pre-existing env 실패 — 컨테이너 root 실행으로 `test_container_backend::test_missing_backend_fails_before_runtime`가 non-root Linux 단언에 걸림), `oracle_fixture_check` 4/4 유지, `make demo` 2회 바이트 동일. 구현(전부 additive): (1) C1 일반화 — `oracle.generalized_identity_confinement(after)` + `BoundaryIdentityEvidence`(EXTRACTION↔비-EXTRACTION, HARNESS 포함) 추가. `evaluate_contracts`·`RunResult.violations` 3-tuple·`ContractId`·`ViolationResult` 불변. 새 경계 fixture: extract/shared가 HARNESS `archive/input.tar`와 inode 공유(C0/C1/C2 전부 False, 일반화 경로만 탐지). (2) add_hardlink 외부 타깃 — 새 `MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK`로 ADD_HARDLINK slot만 escape 타깃 생성 함수(`add_escaping_hardlink`, generic `..`+controlled vocabulary, CVE/PoC 경로 하드코딩 없음)로 교체. 기존 `MutationOperatorId`·8-slot 분포·seed 재현성·기존 policy 테이블 불변. `test_mutator_ablation.py` `len==6→7`, `test_mutation_scheduler.py` `_legacy_reference` dict 확장(additive). N01 경로(`n01_candidate_match._relations`, FROZEN `n01.py`) 불변.

## P2-c. N01 rediscovery 재실행

- 분류: Phase 2 (native 실행)
- 환경: **호스트 터미널** (docker 필요)
- 게이트: P2-b 머지. 그리고 사람이 승인한 실행 범위(타깃 이미지 7.5.2/7.5.3 고정, 실행 예산 상한, seed)가 STATUS 또는 LOG에 명시돼 있어야 한다. 없으면 `막힘(승인 범위 없음)`으로 기록하고 진행하지 않는다. STATUS 기준 native P0/P1/P2 campaign은 아직 NOT_AUTHORIZED다.
- 할 일: 승인된 범위에서 effect campaign을 실제 node-tar historical 타깃에 돌려, 알려진 PoC를 seed로 쓰지 않고(연구 규칙 2) 일반화된 C1/C2 위반이 나오는지 본다.
- 완료 조건: 실행 산출물(JSON, raw evidence 경로)이 남고, 결과가 `발견` / `미발견` / `중단(원인)` 중 하나로 LOG에 기록된다. Oracle 탐지를 취약점 재현 성공으로 기록하지 않는다. 결과는 `demo run` 또는 승인 문서가 정한 라벨로 적는다(qualification 아님).
- 실행/검증하게 되는 것: feedback 기반 탐색이 실제 node-tar historical 타깃에서 C1/C2 위반을 찾는지 확인할 수 있다.
- 진행(2026-10-24, `jiwoong/p2-c-n01-rediscovery`, base=`jiwoong/p2-b-c1-generalize-hardlink`, 스택 2/3): **엔트리포인트 code만 추가(additive), native 실행은 runtime 대기.** runtime Step A가 기록한 '엔트리포인트 부재'(LOG 2026-10-24 01:20)를 메움. 새 scoped 엔트리포인트 `effect-demo-historical`(`scripts.container_host … effect-demo-historical --image <frozen effect image> --tar-version 7.5.2|7.5.3 --seed … --budget … --evidence …` → `container_controller.run_native_historical_demo` → `run_effect_demo.historical_demo_report`). 타깃 버전 allowlist는 catalog(`node-link-sanitize` selected_pair)+wrapper locks+frozen `n01.FROZEN_TARGETS`(읽기전용) 교차검증으로 7.5.2/7.5.3만 허용(lock sha256 일치 확인), 임의 이미지·버전 거부. arm=P2 adaptive·mutation=escape-hardlink 기본, seed·budget 지정 가능(budget 1..100, >100 거부). 결과 라벨 'demo run'+oracle hit 'oracle-detected Cx event'(rediscovery/취약점 문자열 없음). 안전 제약 불변: benign `make demo-native`의 7.5.22 핀(`native_demo_report`)·기존 격리(`NodeTarEffectTarget`/disposable sandbox+sentinel; `--privileged`/`--cap-add`/`--security-opt` 추가 없음)·`MAX_NATIVE_BUDGET=100`·FROZEN(`n01.py`/locks/guard/settings)·oracle(`evaluate_contracts` C0/C1/C2 3-tuple) 전부 미변경. 검증: docker Dev Container `make check` 1750 pass/1 fail(pre-existing env, 새실패 0)·oracle 4/4·`make demo` 2회 바이트 동일. **게이트 미충족(P2-b 미머지 + 사람 승인 실행 범위는 LOG 2026-10-24 01:05에 있으나 native는 runtime 소관)이므로 native pilot은 실행하지 않음.** 상세는 [LOG](LOG.md).
- Step B native 실행(2026-10-24, 승인범위 LOG 2026-10-24 01:05, context=orbstack, 격리완화 없음, 검증된 엔트리포인트 `make demo-native-historical`만 사용): **결과 = 중단(원인: native 관찰 무결성 결함); 완료분 oracle C0/C1/C2 미발견.** B1 PILOT 7.5.2 s123 b10 → node-tar 실제 실행 10/10·무결성 정상(operation-correlation 충돌 없음)·oracle 0·per-step wall ~0.84s. B2 산정 budget=min(100, fit≈1992)=100(6캠페인 ~10분 ≪ 3h). B3 매트릭스 {7.5.2}×{123,456,789}: s123 완료(79 success/21 rejected·oracle 0), s456 **step 72 ABORT — success(exit0) 케이스인데 trace invalid**(integrity_valid False·completeness invalid·'transport is not one LF-terminated frame'), s789 완료(67 success/33 rejected·oracle 0). 완료 7.5.2 run의 invalid-completeness는 전부 rejected 케이스(거부시점 미완료=기대동작)이며 abort는 success+invalid에서만 발동. 무결성 결함 STOP 규칙(완화·재시도·우회 금지)에 따라 **7.5.3(0/3) 미실행**. 총 native wall ~6분(4h 미도달), 컨트롤러·볼륨 매회 정리. 라벨 demo run(취약점 재현/CVE 재발견 아님). 소스 미변경(docs만). evidence: `~/inodefence-evidence/p2c-native-matrix/`(…-015414 완료·…-015543 ABORT+raw 보존·…-015648 완료). 상세는 [LOG](LOG.md).

## P3. A/B/C 비교 실험

- 분류: Phase 3 ([MIDTERM_GOALS](MIDTERM_GOALS.md) P1)
- 환경: synthetic 비교는 Dev Container, native 비교는 호스트 터미널
- 게이트: P2-c 결과 `발견`.
- 할 일: A(random) / B(structure-aware) / C(intermediate FS state-aware) 세 전략을 같은 seed·예산·Oracle 조건으로 돌린다. 지표(중간 상태 다양성, 고유 상태 전이, 유효 입력 비율, Oracle 이벤트)를 실행 **전에** 고정해 LOG에 적는다. 기존 `scripts/compare_effect_policies.py`를 먼저 재사용한다.
- 완료 조건: 세 전략 각각의 raw 결과 파일과 지표 표가 남고, 같은 명령으로 재실행 시 같은 결과가 나온다. 우위 주장은 기록된 결과 범위 안에서만 한다.
- 실행/검증하게 되는 것: 같은 예산에서 상태 피드백이 mutation 선택에 주는 차이를 재현 가능한 수치로 비교할 수 있다.
