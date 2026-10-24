# 자율 작업 목록 (WORKLOG)

자율 루프가 끝낸 작업을 누적한다. 사람이 이 표를 보고 브랜치를 main과 비교해 머지 여부를 정한다.
한 작업 = 한 행. 작업 브랜치의 커밋에 함께 넣는다. 실행 상세는 [LOG](LOG.md), 할 일은 [BACKLOG](BACKLOG.md).

상태: `검토대기`(검증 통과, 사람 비교 대기) / `BREAKING`(기존 테스트·판정을 깸, 머지 대기, 후속 진행 금지) / `막힘`(진행 불가, 필요한 것을 요약에 적음)

비교 명령: `git diff main...<브랜치> --stat`

| 날짜 | 브랜치명 | P0/Phase | 한 줄 요약 | main 대비 핵심 변경 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 | jiwoong/p0-5-jsonl-partial-ci | P0-5 (BACKLOG 3) | native demo가 중단돼도 끝난 step의 루프 기록이 `<evidence>.steps.jsonl`에 남고(최종 JSON 형식 불변), CI container job이 effect producer smoke + budget 6 effect-demo를 돌림 | `src/inodefence/effect_campaign.py`(on_step), `src/inodefence/effect_demo.py`(EffectStepReporter·render_effect_step_line), `scripts/run_effect_demo.py`(step_sink), `scripts/container_controller.py`(JSONL append+fsync), `scripts/local_node_tar_smoke.sh`(JSONL 복사), `.github/workflows/ci.yml`, `tests/test_effect_demo_steps_jsonl.py`, `docs/START_HERE.md` | 검토대기 (PR CI 결과는 LOG 참고) |
| 2026-10-24 | (코드 변경 없음) | P0-1 (BACKLOG 4) | N01 native 무결성 결함 원인을 producer 출력으로 분류(`tar.x` 미settle → exit 0·빈 프레임, PathReservations 교착 추론). 필요한 것: 재현 실험(로컬 tar 7.5.22 단일 엔트리)과 producer `beforeExit` 수정에 대한 사람 승인 | LOG 2026-10-24 18:00 두 번째 줄 | 막힘 |
| 2026-10-23 | jiwoong/p0-0-autoloop-setup | 도구 세팅(P0 아님) | 자율 루프용 PreToolUse 가드 훅(R1–R8), 역할 4종(전부 claude-opus-4-8), autoloop 규칙, BACKLOG/WORKLOG; 10-24 BACKLOG를 11/2 P0 큐(1–4)로 재정렬, N01·P3는 사람 일정·승인으로 막음 | `.claude/settings.json`, `.claude/hooks/guard.py`, `.claude/agents/{orchestrator,builder,runtime,verifier}.md`, `.claude/skills/autoloop/SKILL.md`, `docs/BACKLOG.md`, `docs/WORKLOG.md`, `tests/test_claude_guard.py` | 검토대기 |
| 2026-10-23 | jiwoong/p2-a-c1-impact | P2-a | C1 일반화(EXTERNAL object 전체 비교) 영향 조사 — 임시 패치로 Dev Container 실행·되돌림, 판정 안전(additive) | docs만: `docs/LOG.md`, `docs/WORKLOG.md`, `docs/STATUS.md` (소스 변경 0, 패치 미커밋) | 검토대기 |
| 2026-10-23 | jiwoong/guard-destructive-block | 도구 세팅(P0 아님, 사람 직접 지시) | guard.py에 파괴적 명령 차단 R9–R16(git reset --hard/clean -f/checkout·restore/branch -D/force push, rm -rf 프로젝트경로, rm 다수파일, .git 손상) 추가 시도 | docs만: `docs/LOG.md`, `docs/WORKLOG.md` (guard.py·tests 변경 0). 필요한 것: 사람이 라이브 가드를 끄거나 사람이 직접 guard.py를 교체해야 함 (R4가 모든 역할에 guard.py 편집을 무조건 차단, scratch 스테이징도 R5 차단, settings.json 수정·우회 금지) | 막힘 |
| 2026-10-24 | jiwoong/p2-c-n01-rediscovery | Phase 2 (P2-c) | 엔트리포인트 code(additive) + **native 매트릭스 실행(Step B)**, 스택 2/3. historical effect-campaign scoped 엔트리포인트(`effect-demo-historical`): catalog(7.5.2/7.5.3)+wrapper locks+frozen n01 교차검증 allowlist, arm=P2 adaptive·mutation=escape-hardlink 기본, seed/budget 지정(1..100), 라벨 'demo run'/'oracle-detected Cx event'. benign 7.5.22 핀·격리·budget상한100·oracle·FROZEN 전부 불변. **Step B native(승인범위 LOG 01:05, context=orbstack, budget 100):** PILOT 7.5.2 s123 b10 무결성 정상·oracle 0. 매트릭스 {7.5.2}×{123,456,789}: s123 완료(79succ/21rej·oracle 0), s456 **step 72 native 관찰 무결성 결함으로 ABORT**(success 케이스인데 trace invalid), s789 완료(67succ/33rej·oracle 0) → 무결성 STOP 규칙에 따라 7.5.3 미실행. 완료분 C0/C1/C2 0건, 총 native wall ~6분(4h 미도달), 라벨 demo run | code 변경은 엔트리포인트 커밋(아래 목록) 그대로; 이 Step B run은 docs만 추가: `scripts/run_effect_demo.py`(historical_demo_report+allowlist+게이트), `scripts/container_controller.py`·`scripts/container_host.py`(effect-demo-historical 모드), `scripts/local_node_tar_smoke.sh`(demo-historical), `Makefile`(demo-native-historical), `tests/test_effect_demo.py`, docs(LOG/WORKLOG/BACKLOG). make check 1750 pass/1 fail(pre-existing env, 새실패 0), oracle 4/4, demo 바이트동일. native evidence: `~/inodefence-evidence/p2c-native-matrix/` | 부분결과(native 무결성중단·oracle 미발견) |
| 2026-10-24 | jiwoong/p2-b-c1-generalize-hardlink | Phase 2 (P2-b) | docker Dev Container(inodefence-envprobe) 안 make check 검증, base=guard-destructive-block, 스택 1/3. C1 일반화 additive(oracle.generalized_identity_confinement + BoundaryIdentityEvidence, evaluate_contracts·C0/C1/C2 3-tuple 불변) + add_hardlink 외부 타깃 확장(새 MutationPolicy.M1_PROTECTED_COMPONENTS_ESCAPE_HARDLINK, 기존 operator·seed 재현성 불변) | `src/inodefence/model/results.py`·`model/__init__.py`·`oracle/contracts.py`·`oracle/__init__.py`·`mutator/{m1,m1_addressing,policy,dispatch}.py`·`mutator/README.md`·`docs/research/design/security-contracts.md`·tests(`test_mutator_ablation`·`test_mutation_scheduler`·`test_mutator_addressing`·`test_oracle_fixtures`)·docs(LOG/WORKLOG/BACKLOG). make check 1737 pass/1 fail(pre-existing env, 새실패 0), oracle 4/4, demo 바이트동일 | 검토대기 |

## 야간 루프 요약 (2026-10-24)

야간 자율 루프(P2-b, P2-c)를 한 곳에 정리한다. 실행 상세는 [LOG](LOG.md), 할 일 상태는 [BACKLOG](BACKLOG.md). observed(실행 출력·파일로 확인)와 inferred(추론·재구성)를 구분한다. native 결과는 라벨 `demo run`이며 취약점 재현/CVE 재발견이 아니다.

### 1. 브랜치별 한 일 / 상태 / make check

- `jiwoong/p2-b-c1-generalize-hardlink` (PR #129, base=`guard-destructive-block`, 상태 검토대기·verifier PASS): C1 일반화 additive(`generalized_identity_confinement` + `BoundaryIdentityEvidence`, `evaluate_contracts`·C0/C1/C2 3-tuple·기존 4 fixture·N01 경로 전부 불변) + 외부 타깃 escape hardlink operator 추가(기존 8-slot 분포·seed 재현성 불변). make check(컨테이너) 1737 pass / 1 fail(새 실패 0), oracle 4/4, make demo 2회 바이트 동일. (observed)
- `jiwoong/p2-c-n01-rediscovery` (PR #130, base=`p2-b`, 스택 2/3): (a) historical effect-campaign 엔트리포인트 additive 추가(verifier PASS) — 벤치 7.5.22 핀·격리·MAX_NATIVE_BUDGET(100)·FROZEN·oracle 전부 불변, catalog 7.5.2/7.5.3만 허용, 거부 테스트 +13. make check 1750 pass / 1 fail(새 실패 0). (b) native 매트릭스 실행 = 아래 3절. (observed)
- make check의 유일 실패 `test_container_backend::test_missing_backend_fails_before_runtime`는 변경 무관 pre-existing env 실패(컨테이너 root 실행이 non-root Linux 단언에 걸림, baseline에도 존재). (observed)

### 2. native 승인 범위 (사람)

타깃 7.5.2/7.5.3(FROZEN `n01.py` 불변), arm P2 adaptive, mutation M1 escape, seed {123,456,789}, budget ≤ 100, wall-clock 4h 상한, disposable sandbox + sentinel, 격리 완화 없음. (LOG 2026-10-24 01:05에 기록됨.)

### 3. native 결과 (라벨 `demo run` — 취약점 재현/CVE 재발견 아님)

- observed: 7.5.2 s123(budget 100) oracle C0/C1/C2 **0건**(79 success / 21 reject), 7.5.2 s789(b100) **0건**(67 success / 33 reject). PILOT 7.5.2 s123 b10도 0건, per-step ~0.84s, 무결성 정상.
- **중단**(observed): 7.5.2 s456 step 72 — target exit 0(success)인데 trace invalid("transport is not one LF-terminated frame", integrity_valid False, completeness invalid, controller_flush False). 엔트리포인트 integrity gate가 fail-closed abort + evidence 보존. 매트릭스 STOP.
- 7.5.3 ×3 **미실행**. 총 wall-clock ~6분(4h 상한 미도달). (observed)
- evidence(절대경로): `/Users/choijiwng/inodefence-evidence/p2c-native-matrix/` 아래 4개 JSON(pilot, s123, s456 abort+raw, s789).
- 해석(observed만, 단정 금지): 완료된 7.5.2 run은 oracle 0건. 7.5.3 미실행이라 7.5.2 vs 7.5.3 비교 성립 불가. **가설(state-aware가 C1/C2를 더 일찍/많이) 미확인.**

### 4. 사람 판단 필요 (핵심 블로커)

success 케이스(exit 0)에서 발생한 native 관찰 무결성 결함(malformed transport frame). STATUS가 문서화한 native effect observation NOT_QUALIFIED 취약점과 일치(inferred). 오버라이드의 즉시 중단·사람 판단 조건이라 **자율로 고쳐 재시도하지 않았다.** 사람이 (a) 생산자/transport 무결성 결함의 원인 조사·수정 여부, (b) P2-c 재실행 여부를 결정해야 함.

### 5. P3 상태

게이트 "P2-c 결과 발견" **미충족**(결과 = 중단/미발견). native P3 진행 불가. synthetic A/B/C 비교(`compare_effect_policies.py` 재사용)는 같은 게이트로 자율 진행하지 않음 — **사람 승인 시 synthetic으로 수행 가능**(중간 상태 다양성·고유 전이·유효 입력비·oracle 이벤트/첫 히트 지표를 LOG에 먼저 고정한 뒤).

### 6. 권장 머지 순서 (사람)

1. PR #129(P2-b) — 단, base가 docs-only `jiwoong/guard-destructive-block`이라 머지 전에 guard-destructive-block 선처리 또는 P2-b를 main으로 rebase 결정 필요(소스/테스트 diff는 base와 독립, main 대비 diff ≈ base 대비 diff).
2. PR #130(P2-c, base=`p2-b`).

둘 다 draft·미머지. P2-c의 native 결과는 중단/미발견이므로 "검증된 기능"이 아니라 "엔트리포인트 추가 + demo run 부분결과"로만 소개한다.

### 7. 루프 개선안 (피드백 — 사람이 아침에 조정)

- R6 가드가 orchestrator의 read-only 환경 확인(`command -v docker`)까지 차단하는데 orchestrator.md는 그걸 직접 시킴(모순). → R6 allowlist에 read-only 조회 추가 또는 "docker 확인은 runtime 위임"으로 명문화.
- orchestrator에 Edit/Write 없음 → 승인 범위·요약 기록도 builder 라운드트립. → LOG/WORKLOG append 좁은 권한 또는 사람이 승인 범위 선커밋.
- TodoWrite 비활성 → 계획 추적을 메시지로만. → 활성화 또는 BACKLOG로 일원화.
- 동시 작업자가 같은 워킹트리·WORKLOG 편집 충돌 → 병렬화 제약. → 작업자 `isolation:worktree` 또는 orchestrator가 기록 직렬 커밋.
- PR 생성 주체 모호(orchestrator 금지 vs override 요구) → builder가 draft PR 생성으로 처리. → autoloop에 명문화.
- autoloop 스택 금지 vs 오늘밤 스택 허용 충돌 → "스택 모드" 절 추가.
- 가드 R3가 커밋 **메시지 본문**의 격리 플래그 토큰을 오탐 차단(코드는 격리 미변경) → R3는 실제 명령 인자만 스캔하거나 커밋 메시지 본문 예외.
- BACKLOG P2-c가 "엔트리포인트 존재"를 전제했으나 실제로는 없었음(벤치 데모 7.5.22 하드핀, historical은 FROZEN qualification 전용) → 엔트리포인트 전제 항목은 사전 확인 필요. 이번엔 builder가 additive로 추가해 메웠음.
- 참고(minor): P2-b `mutator/README.md`의 escape slot RNG 소비 서술이 부정확(기능·재현성 문제 아님) — 아침 정리 시 수정 권장.
- 남은 자원: dev container `inodefence-envprobe`가 살아있음(필요 시 `docker rm -f inodefence-envprobe`).
