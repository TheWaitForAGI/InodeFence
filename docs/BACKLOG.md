# 작업 큐 (BACKLOG)

할 일을 **마일스톤(M)** 아래 태스크로 둔다. 마일스톤은 [STATUS의 Capability Ledger](STATUS.md)의
M1~M4와 같고, 날짜가 아니라 "증거가 모이면 찍는" 지점이다. 자율 루프
(`.claude/skills/autoloop/SKILL.md`)는 **맨 위부터** `대기`이고 게이트가 열린 태스크를 집는다.
완료 기록은 [WORKLOG](WORKLOG.md), 실행 기록은 [LOG](LOG.md)에 남긴다.

상태 값: `대기` / `진행` / `완료(<브랜치>)` / `막힘(<날짜>, <이유>)` / `BREAKING(<브랜치>)` / `대기(머지 필요: <브랜치>)`

- 게이트 `사람`은 바깥에 영향을 주는 결정(머지, 외부 공개 등)에만 쓴다. 그 외는 안전경계 안에서 자율 진행한다.
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
| M2.2 | 같은 fixture를 우리 Observer/Oracle 경로(effect pipeline)로도 통과시켜 "손 probe == oracle 판정" 일치 확인 | 대기 | M2.1 |

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
| M3.1 | generic security-state gradient 설계·구현(additive): "extraction root 밖에 새 네임스페이스 객체/identity 관계가 생겼다" 같은 **target-agnostic** 부분진척 신호를 effect key에 추가. 기존 C0/C1/C2 판정·fixture·N01 경로 불변(autoloop 5.4). sentinel 경로/CVE를 feedback에 심지 않는다. **구현됨**: 거부된 외부-하드링크 시도를 valid trace로 보는 producer abort-drain + boundary-attempt 키 + opt-in P3 arm(게이트를 깨끗한 REJECTED까지 완화; **연구-정직성 판단점, PR 플래그**). 7.5.2 native에서 키 실발화 확인(LOG 2026-10-25 01:01) | 대기(머지 필요: jiwoong/m3-boundary-attempt-gradient) | 사람 |
| M3.2 | 그 gradient로 B0/B1/B3 비교: "state feedback이 random보다 먼저 위반을 찾는가". 지표는 executions-to-first-violation, unique states, 유효입력비 — 돌리기 전에 고정. negative/no-hit도 그대로 보고(right-censored). **1차 매트릭스 완료**(PR #151, P1/P2/P3 × 6 seed × budget 100): gradient 기작은 측정됨(P3 외부시도 4.6×) 그러나 **C1 rate 우위 미입증**(C1 P1 1/6·P3 0/6, budget 100 우측센서). **contamination 제거 후속**(어휘에서 대상 토큰 제거 + 관찰-이름 조합, A1/A2/A3 × 6 seed, LOG 11:00): A1 도달 바닥(0/6), A2/A3 관찰 이름으로 대상 segment 도달(target-agnostic), gradient 접근 시도↑ — 단 **clean exact C1은 전 arm 0/6**(어휘판 자율 C1은 contamination 덕이었음). powered 비교·clean exact C1은 더 많은 campaign/큰 budget 필요(M3.3) | 진행 | M3.1, 주언(feedback/eval) 협의 |
| M3.3 | (보조·대조군) escape 정책에서 budget을 크게 올려 자력 발견을 무작위로 확인 — "feedback 덕"이 아니라 대조 데이터로만 | 대기 | 없음 (호스트 docker) |
| M3.4 | (실측 pilot) 설계의 formal 420k executions를 눈감고 약속하지 말고, 먼저 **기존 N03 B0/B1/B3 feasibility pilot 제안**([n03-b0-b1-b3-pilot-task-proposal](research/benchmarks/n03-b0-b1-b3-pilot-task-proposal.md): seeds 9001–9005·budget 200·20 campaigns·4000 exec·~5.56h)을 실행 가능한 계약으로 확정·실행. 목적은 p95 full-step time·rejection/timeout율·evidence bytes·peak memory 실측으로 formal budget을 right-size(감사 EN-010 측정 갭 메움). **실행 전 고정 필요**: (a) N01 human qualification 토큰, (b) 5s/10s timeout 경로 1개 동결, (c) clean source/image/runtime provenance freeze. **contamination 재조정 필수**: 제안의 공유 grammar(`uniform-generic-m1-protected-components-v1`)는 `outside`·`sentinel.txt`를 어휘에 포함 → M3.2의 관찰-이름(contamination-free) 경로로 교체해야 blind 입증과 정합. no-hit pilot은 가설에 INCONCLUSIVE(별도 보관, formal과 분리) | 대기 | 사람(N01 토큰·timeout 동결), 주언(feedback/eval) |
| M3.5 | (양성 주장 조건) coverage-guided baseline **D** 추가 + A/B/C/D 공통지표 — 'identity-state feedback 특정 효과'를 'feedback 일반 효과'와 분리(H1 판정·참신성 방어; ZIPDiff/LinkZard류 커버리지 피드백 대비 요구 대응). 감사 EN-008('새 state 수 ≠ effectiveness') 준수. **rate 우위를 주 주장으로 올릴 때 freeze 전 필수**; 메커니즘-only 주장에는 선택. (상시 '감사 제안 baseline D' 행을 여기로 승격) | 대기 | 주언 |

## M4 — 일반성 (2번째 extractor)

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M4.1 | oras-go adapter 설계(isolated CWD 포함), 동일 generic 모델·oracle로 연결. CVE/target-specific 로직을 generic 모듈에 섞지 않는다 | 대기 | 규민·민찬 협의 |
| M4.2 | (감사 제안) decompress(JS; CVE-2026-39243/39246 = symlink + absolute hardlink, CWE-59) 또는 2026 CWE-59 군집(adm-zip·Archive::Tar·HF datasets·borg) 중 1개를 2번째 target으로 — 동일 generic oracle 재사용. **중간발표 포함 여부 확인필요**(앞선 기능) | 대기 | 규민·민찬 협의 |
| M4.1b | (감사 전진, 완료) generic oracle 2번째 extractor 일반성: Python stdlib tarfile 통제 차분(fully_trusted=C1+C2, data=거부). `tests/test_python_tarfile_generality.py`. oracle 코드 불변·target-agnostic. **중간발표 포함 여부 확인필요** | 완료(jiwoong/p-generality-python-tarfile) | 없음 |

## 상시 (레인 담당)

| 태스크 | 상태 | 게이트 |
| --- | --- | --- |
| A/B/C/D(random / structure-aware / state-aware / coverage-guided) **정의와 공통 지표** 확정 — M3.2·M3.4·M3.5가 쓸 측정의 기준(D는 M3.5) | 대기 | 주언 |
| 거부 입력에서 중간 상태 event 0개인 한계의 표현 방식 | 대기 | 민찬 |
| demo 이미지 ID 재현성(provenance attestation) | 대기 | 규민 |
| 선행연구 서지 정합성(related-work-positioning.md에 저자·venue·연도·아티팩트) | 완료(jiwoong/p-audit-prior-work-citations) | 없음 |
| (감사 제안 → **M3.5로 승격**) coverage-guided baseline(D) + A/B/C/D 공통지표 — 'identity feedback 특정 효과'를 'feedback 일반'과 분리(H1 판정용). **중간발표 포함 여부 확인필요** | 대기(M3.5) | 주언 |
| (감사 전진, 완료) C1 symlink-referent 보강: additive `symlink_referent_confinement` detector(referent가 extract/ 밖이면 보고, 3-tuple 불변). **중간발표 포함 여부 확인필요** | 완료(jiwoong/p-oracle-symlink-referent) | 없음 |
