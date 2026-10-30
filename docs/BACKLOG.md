# 작업 큐 (BACKLOG)

할 일을 **마일스톤(M)** 아래 태스크로 둔다. 마일스톤은 [STATUS의 Capability Ledger](STATUS.md)의
M1~M4와 같고, 날짜가 아니라 "증거가 모이면 찍는" 지점이다. 자율 루프
(`.claude/skills/autoloop/SKILL.md`)는 **맨 위부터** `대기`이고 게이트가 열린 태스크를 집는다.
완료 기록은 [WORKLOG](WORKLOG.md), 실행 기록은 [LOG](LOG.md)에 남긴다.

상태 값: `대기` / `진행` / `완료(<브랜치>)` / `완료(머지됨 #<PR>, main)` / `막힘(<날짜>, <이유>)` / `BREAKING(<브랜치>)` / `대기(머지 필요: <브랜치>)`

- 루프의 끝은 BACKLOG 소진이 아니라 **프로젝트 완료**(가설 검증·M1~M4; autoloop 7.1, D036)다. 큐가 비면 루프가
  STATUS Ledger의 빈 칸(증거 수준이 가장 낮은 미완 마일스톤의 다음 gate)에서 항목을 보충한다(autoloop 7.2).
- 게이트 `사람`은 안전경계·연구 불변식에 걸리는 결정(외부 공개, 가드·격리·allowlist 설정, FROZEN 변경, BREAKING 판정)에만 쓴다.
  머지는 사람 게이트가 아니다(D035): PR·CI·verifier 통과 후 자율 머지. 그 외는 안전경계 안에서 자율 진행한다.
- 안전경계(변경 없음): disposable sandbox + sentinel만, 고정 node-tar 버전, 격리 완화 플래그 금지,
  가드 훅 우회 금지, 실제 민감 파일 대상 금지. 이건 느슨하게 하지 않는다.
- 연구 불변식(변경 없음): CVE-specific oracle 금지(D005), 알려진 PoC를 fuzzing seed로 안 씀(D006),
  observed/inferred 구분, synthetic을 native로 승격하지 않음, 비교 없이 effectiveness 주장 안 함.

## 완료 (이력은 WORKLOG/LOG)

**M1 — 루프가 실제 node-tar에서 돈다: 완료.** 과거 P0-1~P0-5 큐(중간 상태 trace, `make demo`=native,
JSONL 부분 저장+CI, producer 견고성)와 P2-b/P2-c 머지가 main에 있다. 세부는 Ledger 1~6행과 WORKLOG.

---

## M2 — 실제 경계위반 통제 재현 + 버전 구분 (실증됨 → 박제)

2026-10-24 capability probe로 node-tar 7.5.2가 외부 sentinel로 하드링크를 만들어 C1+C2가 성립하고
7.5.3은 거부함을 observed(LOG). 재현 스크립트+증거는 `experiments/repro/`에 박제됐고(5 릴리스 sweep),
이는 **2개 CVE의 차분 경계**다: 최상위 7.5.2/7.5.3 = CVE-2026-23745(catalog N01·R1), 중첩 7.5.6/7.5.7 =
CVE-2026-24842(CVE-2026-23745 수정이 도입한 check/use 회귀; catalog N02·R2). 두 CVE 모두 catalog에 이미
등록됨. 동일 generic identity oracle이 두 root-cause를 outcome으로 포착한다. 재발견(자력 발견)과는 구분한다.

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M2.1 | capability probe를 repo 안 재현 스크립트/테스트로 고정: 손으로 만든 하드링크 fixture(외부 sentinel 대상)를 실제 7.5.2/7.5.3에 돌려 7.5.2=C1+C2·7.5.3=거부를 확인. generic C1/C2만 쓰고 CVE 식별자/PoC 하드코딩 없음. LOG 한 줄 + Ledger M2 증거 갱신 | 완료(experiments/repro/cross_release_identity.py) | 없음 (호스트 docker) |
| M2.2 | 같은 fixture를 우리 Observer/Oracle 경로(effect pipeline)로도 통과시켜 "손 probe == oracle 판정" 일치 확인 | 완료(claude/m2-2-oracle-path-7d09f3) | M2.1 |

## M3 — 퍼저가 자력으로 위반을 찾는다 (H1 본체)

**현재 판정(정직).** 메커니즘은 인과적으로 입증됐다: blind 대조에서 object-identity 관찰을 끄면
(A3blind) 자율 발견 0, 켜면(A3full) seed 11에서 21건 재현 — 발견의 원인이 가설이 지목한 바로 그
피드백임을 보였다(하드코딩 아님, EXTERNAL region 기준; LOG 2026-10-26). M2는 2개 CVE 통제 차분을
하나의 generic oracle로 포착해 이미 박제됐다. **그러나 rate 우위는 미입증이다**: budget 100에서 C1
0~1/6, budget 1500·65 seed에서도 자율 C1은 s11 하나뿐(seed-rare)이라 정책 간 rate 차이를 검출할
검정력이 없다. 근본 원인은 정답이 한 점(~1/729)인데 final-state C1/C2 oracle이 all-or-nothing이라
adaptive 탐색에 gradient가 없다는 것이다(historical 7.5.2/7.5.3 × 3 seed × budget 100 oracle 0건, LOG).

**주장 입장(설계 결정).** 주 주장은 **메커니즘 인과 입증 + M2 통제 재현**(이미 방어 가능)으로 두고,
rate 우위는 **탐색적 보조**로 둔다. rate 우위를 주 주장으로 올리려면 M3.4 pilot로 검정력을 확보하고
M3.5 baseline D로 'identity-state 피드백 특정 효과'를 '피드백 일반 효과'와 분리해야 한다. 가장 신호가
풍부한 길은 중간상태(entry-transition) 피드백이지만 native node-tar entry-completion 경계가
NOT_IMPLEMENTED이라([transition-feedback-v1](research/design/transition-feedback-v1.md); 감사 EN-011),
이 신호는 M4의 2번째 extractor가 쓸 만한 경계를 줄 때까지 열리지 않는다. 음성/희소 결과도 정당한
결과로 보고한다(H1). 감사 EN-008 준수: 새 state/fingerprint 수는 진척·effectiveness의 척도가 아니다.

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M3.1 | generic security-state gradient 설계·구현(additive): "extraction root 밖에 새 네임스페이스 객체/identity 관계가 생겼다" 같은 **target-agnostic** 부분진척 신호를 effect key에 추가. 기존 C0/C1/C2 판정·fixture·N01 경로 불변(autoloop 5.4). sentinel 경로/CVE를 feedback에 심지 않는다. **구현됨**: 거부된 외부-하드링크 시도를 valid trace로 보는 producer abort-drain + boundary-attempt 키 + opt-in P3 arm(게이트를 깨끗한 REJECTED까지 완화; **연구-정직성 판단점, PR 플래그**). 7.5.2 native에서 키 실발화 확인(LOG 2026-10-25 01:01) | 완료(머지됨 main #151) | 사람 |
| M3.2 | 그 gradient로 B0/B1/B3 비교: "state feedback이 random보다 먼저 위반을 찾는가". 지표는 executions-to-first-violation, unique states, 유효입력비 — 돌리기 전에 고정. negative/no-hit도 그대로 보고(right-censored). **1차 매트릭스 완료**(PR #151, P1/P2/P3 × 6 seed × budget 100): gradient 기작은 측정됨(P3 외부시도 4.6×) 그러나 **C1 rate 우위 미입증**(C1 P1 1/6·P3 0/6, budget 100 우측센서). **contamination 제거 후속**(어휘에서 대상 토큰 제거 + 관찰-이름 조합, A1/A2/A3 × 6 seed, LOG 11:00): A1 도달 바닥(0/6), A2/A3 관찰 이름으로 대상 segment 도달(target-agnostic), gradient 접근 시도↑ — 단 **clean exact C1은 전 arm 0/6**(어휘판 자율 C1은 contamination 덕이었음). powered 비교·clean exact C1은 더 많은 campaign/큰 budget 필요(M3.3) | 진행(단일경로 A/B/C/D 비교 하너스+공통지표 readout 구현: claude/m3-2-eval-d81a84 `evaluation/arm_comparison.py`; **안전 reference 단일경로 실행 완료**(scripts/run_abcd_comparison.py → python-tarfile-data, seed×3·budget 50, 전 arm right-censored>N·effectiveness 주장 없음, evidence abcd-reference-20261030-005915); node-tar affected-mode terminal-C1 run=**설계결정 C+(host-broker 미구축)**: feasible budget right-censored null·node-tar H1 인과는 effect-path(s11+blind)에 이미 존재; **중간상태 gradient 차분 지표 소비경로 준비**(evaluation/intermediate_metrics.py, additive, dense non-right-censored arm 차분, EN-008 search-behavior, #174·2nd extractor 비의존)=규민 2nd-extractor+민찬 wiring landing 대기; powered 통합런 대기 M3.3/M3.4; **M3.3 right-censored roll-up 도구 ready**(evaluation/right_censored.py: Wilson+censoring+complete/incomplete 분리, 추상 per-seed facts 소비)=배치 1+2 통합 소비 완료(scripts/analyze_m3_3_control.py 다배치 pooling: clean C1 0/7 complete·Wilson[0,0.354]·5 abort denominator 제외·0 clean C1/12 seed/~20,163 exec, 인과 대조 rate 아님)); **item-3 effect-path A/B/C/D 1차 지표 PASS 1**(scripts/analyze_m3_item3.py, 규민 run 1c0fb7c 소비 18 full+14 informative abort: s77 짝비교 bAtt **C≡D 0.057**>A 0.023>B 0.007·terminal C1 0/18 Wilson[0,0.176]; inferred gradient>random/structure는 informative censoring 강건·**identity-state C는 coverage D 안 넘음**·arm 차분 underpowered→규민 de-censor 2차; readout ~/inodefence-evidence/m3-item3-abcd-20261030/primary-metric-readout.md); **PASS 2 de-censored 확정**(규민 재런 c94c86a·d1e06cc 소비, full 18→21·짝 seed 4-arm 3{77,82,83}·C-vs-D 4{77,79,82,83}): gradient(C/D)>random(A)>structure(B) 일관·**identity-state C≡coverage D 4/4 짝 seed operationally identical**(동일 case_id 시퀀스; external-resolve rung이 escape-hardlink 문법서 boundary-attempt와 중복→동일 corpus 진화)·terminal C1 0/21 Wilson[0,0.155]; 범위 한정 negative·abort observer-side 비결정·PASS 1 lower-bound 추론 measured 철회(recover C/D 0.046<full 0.054)·Wilson/head-sensitivity 보강(EN-008), readout ~/inodefence-evidence/m3-item3-abcd-decensor-20261030/primary-metric-readout-pass2.md) | M3.1, 주언(feedback/eval) 협의 |
| M3.3 | (보조·대조군) escape 정책에서 budget을 크게 올려 자력 발견을 무작위로 확인 — "feedback 덕"이 아니라 대조 데이터로만 | 진행(규민 A1 대조 배치1+2 봉인 #178 commit 6417b75; 주언 통합 right-censored roll-up: clean C1 **0/12**·0/7 complete Wilson[0,0.354]·5 abort denominator 제외, 인과 대조 random floor 0 vs effect-path s11=21 — rate 아님 EN-008) | 없음 (호스트 docker) |
| M3.4 | (실측 pilot) 설계의 formal 420k executions를 눈감고 약속하지 말고, 먼저 **기존 N03 B0/B1/B3 feasibility pilot 제안**([n03-b0-b1-b3-pilot-task-proposal](research/benchmarks/n03-b0-b1-b3-pilot-task-proposal.md): seeds 9001–9005·budget 200·20 campaigns·4000 exec·~5.56h)을 실행 가능한 계약으로 확정·실행. 목적은 p95 full-step time·rejection/timeout율·evidence bytes·peak memory 실측으로 formal budget을 right-size(감사 EN-010 측정 갭 메움). **실행 전 고정 필요**: (a) N01 human qualification 토큰, (b) 5s/10s timeout 경로 1개 동결, (c) clean source/image/runtime provenance freeze. **contamination 재조정 필수**: 제안의 공유 grammar(`uniform-generic-m1-protected-components-v1`)는 `outside`·`sentinel.txt`를 어휘에 포함 → M3.2의 관찰-이름(contamination-free) 경로로 교체해야 blind 입증과 정합. no-hit pilot은 가설에 INCONCLUSIVE(별도 보관, formal과 분리). **측정 설계(주언, 설계만 — 실행 게이트 불변)**: all-or-nothing terminal oracle은 검정력이 없으므로(C+ 결정) pilot의 1차 arm-비교 신호를 **중간상태 gradient 차분**(`evaluation/intermediate_metrics.py`, non-right-censored: unique keys·novelty rate·cumulative trajectory·directed boundary-attempt/proximity milestone)으로 두고, terminal C1은 **right-censored roll-up**(`evaluation/right_censored.py`: Wilson+censoring, single-arm/arm별)으로 부차 보고. 공통지표는 arm_comparison(terminal) + intermediate_metrics(gradient) 재사용(새 effectiveness 지표 없음, EN-008). gradient는 규민 2nd-extractor+민찬 wiring landing 시 활성. 실행 전 고정 (a)(b)(c)는 사람 게이트 그대로 | 대기 | 사람(N01 토큰·timeout 동결), 주언(feedback/eval) |
| M3.5 | (양성 주장 조건) coverage-guided baseline **D** 추가 + A/B/C/D 공통지표 — 'identity-state feedback 특정 효과'를 'feedback 일반 효과'와 분리(H1 판정·참신성 방어; ZIPDiff/LinkZard류 커버리지 피드백 대비 요구 대응). 감사 EN-008('새 state 수 ≠ effectiveness') 준수. **rate 우위를 주 주장으로 올릴 때 freeze 전 필수**; 메커니즘-only 주장에는 선택. (상시 '감사 제안 baseline D' 행을 여기로 승격) **구현됨**: `SearchPolicy.D`(최종상태 `run_search_campaign` 경로) + `feedback/coverage.py`(target-agnostic: object type·region·depth·symlink anchor; `identity_groups`/`external_effects`·content/size/mode 제외), A/B/C/D 공통지표 `evaluation-protocol-v1.md`에 정의(기존 지표 재사용·새 effectiveness 주장 없음). seed=base corpus, mutation은 새 coverage feature만 admit. B0/B1/B3 의미 불변(additive). **단일경로 A/B/C/D 통합런은 NOT_RUN**(M3.2/M3.4 의존). | 완료(머지됨 main #166) | 주언 |
| M3.6 | (중간상태 gradient 설계 → honest negative) ordered-transition 경계접근 gradient(none<external_namespace<cross_boundary_identity, Region·ChangeField만·answer-agnostic=protected/sentinel 근접 미보상)를 설계했으나, 그 rung이 요구하는 **ordered·entry-correlated entry-completion 경계가 현 extractor군에서 fundamental하게 관찰 불가**(node-tar 전면 QUALIFIED FAIL; decompress 동시·재정렬·컨텍스트 미전파 동류; oras-go 더 어려움 — generality-m4 feasibility, observed). → 구현 코드(`feedback/transition_gradient.py`·`TransitionBoundaryProximity`·테스트)는 **dead로 제거**(소비자 0, EN-008); **설계+negative 발견은 transition-feedback-v1.md에 보존**(코드는 지우되 발견은 문서로). 2번째 extractor로 실제 일반화되는 건 set 기반 effect-path boundary-attempt frame(generality lane canonical `feedback/boundary_attempt_frame.py`가 `inodefence-boundary-attempt-v1` frame emit+normalize → main M3.1 + 주언 metrics 소비), 이 ordered-transition 경로 아님. transition **모델**(checkpoint/transition/novelty/retention)은 불변 | 완료(jiwoong/m3-transition-gradient-signal: honest-negative 기록 + dead/중복 제거) | 사람(머지) |

## M4 — 일반성 (2번째 extractor)

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M4.1 | oras-go adapter 설계(isolated CWD 포함), 동일 generic 모델·oracle로 연결. CVE/target-specific 로직을 generic 모듈에 섞지 않는다 | 완료(jiwoong/m4-1-oras-go-adapter) | 규민·민찬 협의 |
| M4.2 | (감사 제안) decompress(JS; CVE-2026-39243/39246 = symlink + absolute hardlink, CWE-59) 또는 2026 CWE-59 군집(adm-zip·Archive::Tar·HF datasets·borg) 중 1개를 2번째 target으로 — 동일 generic oracle 재사용. **중간발표 포함 여부 확인필요**(앞선 기능) | 완료(jiwoong/m4-2-decompress) | 규민·민찬 협의 |
| M4.1b | (감사 전진, 완료) generic oracle 2번째 extractor 일반성: Python stdlib tarfile 통제 차분(fully_trusted=C1+C2, data=거부). `tests/test_python_tarfile_generality.py`. oracle 코드 불변·target-agnostic. **중간발표 포함 여부 확인필요** | 완료(jiwoong/p-generality-python-tarfile) | 없음 |
| M4.3 | (지휘관 stage-4, 보충 캠페인) decompress C-vs-D boundary-channel 캠페인(A random floor / C external-resolve / D boundary): CWD-상대 하드링크 문법에서 identity-state(C)가 coverage(D)를 넘는지 **측정만**(C>D 가정 0, 결과 scoped). frame-native loop(canonical `frame_boundary_attempt_keys` #179 재사용) + token-clean M1_GENERIC_ESCAPE_HARDLINK. observed(4 seed): **C≈D≫A** — gradient 일반성 positive, 'identity>coverage' negative(C≡D가 CWD-하드링크 문법으로 일반화). 8-seed 재런(seeds 94-101, budget 500, equivalence margin δ=0.05+TOST 사전등록; 통계/CI=독립검증, borderline boundary D-lean ~3.1pp disclose)으로 검정력 보강. oracle/arms/item-3 FROZEN/민찬 canonical 불변(additive 실험 스크립트), D005/D006 clean grammar | 진행(jiwoong/m4-decompress-cvd-infra; 8-seed 재런 실행 중) | 없음(머지는 루프PR정리 단일 드라이버) |

## 상시 (레인 담당)

| 태스크 | 상태 | 게이트 |
| --- | --- | --- |
| A/B/C/D(random / structure-aware / state-aware / coverage-guided) **정의와 공통 지표** 확정 — M3.2·M3.4·M3.5가 쓸 측정의 기준(D는 M3.5) | 진행(정의·공통지표 완료[머지됨 main #166]; 단일경로 A/B/C/D 비교 하너스+readout 구현: claude/m3-2-eval-d81a84 `evaluation/arm_comparison.py`; powered 통합 native run 대기 M3.3/M3.4) | 주언 |
| 거부 입력에서 중간 상태 event 0개인 한계의 표현 방식 | 완료(claude/m3-reject-trace-limit-1b064d) | 민찬 |
| demo 이미지 ID 재현성(provenance attestation) | 완료(gyumin/p0-1-image-id-reproducible: same-host image ID 결정론(BuildKit attestation 해제) · jiwoong/p-demo-image-recipe-provenance: 빌드 레시피 recipe_sha256 provenance + attest) | 규민 |
| 선행연구 서지 정합성(related-work-positioning.md에 저자·venue·연도·아티팩트) | 완료(jiwoong/p-audit-prior-work-citations) | 없음 |
| (감사 제안 → **M3.5로 승격**) coverage-guided baseline(D) + A/B/C/D 공통지표 — 'identity feedback 특정 효과'를 'feedback 일반'과 분리(H1 판정용). **중간발표 포함 여부 확인필요** | 완료(M3.5: claude/m3-5-baseline-d-65d6ae) | 주언 |
| (감사 전진, 완료) C1 symlink-referent 보강: additive `symlink_referent_confinement` detector(referent가 extract/ 밖이면 보고, 3-tuple 불변). **중간발표 포함 여부 확인필요** | 완료(jiwoong/p-oracle-symlink-referent) | 없음 |
