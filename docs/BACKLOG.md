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
7.5.3은 거부함을 observed(LOG). 남은 일은 이걸 **재현 가능한 형태로 박제**하는 것이다. 재발견(자력 발견)과는
구분한다.

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M2.1 | capability probe를 repo 안 재현 스크립트/테스트로 고정: 손으로 만든 하드링크 fixture(외부 sentinel 대상)를 실제 7.5.2/7.5.3에 돌려 7.5.2=C1+C2·7.5.3=거부를 확인. generic C1/C2만 쓰고 CVE 식별자/PoC 하드코딩 없음. LOG 한 줄 + Ledger M2 증거 갱신 | 대기 | 없음 (호스트 docker) |
| M2.2 | 같은 fixture를 우리 Observer/Oracle 경로(effect pipeline)로도 통과시켜 "손 probe == oracle 판정" 일치 확인 | 대기 | M2.1 |

## M3 — 퍼저가 자력으로 위반을 찾는다 (H1 본체)

지금 막힌 진짜 지점. 정답 입력이 한 점(~1/729)인데 C1/C2 oracle이 all-or-nothing이라 adaptive 탐색에
gradient가 없다. historical 7.5.2/7.5.3 × 3 seed × budget 100에서 oracle 0건(LOG).

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M3.1 | generic security-state gradient 설계·구현(additive): "extraction root 밖에 새 네임스페이스 객체/identity 관계가 생겼다" 같은 **target-agnostic** 부분진척 신호를 effect key에 추가. 기존 C0/C1/C2 판정·fixture·N01 경로 불변(autoloop 5.4). sentinel 경로/CVE를 feedback에 심지 않는다. **구현됨**: 거부된 외부-하드링크 시도를 valid trace로 보는 producer abort-drain + boundary-attempt 키 + opt-in P3 arm(게이트를 깨끗한 REJECTED까지 완화; **연구-정직성 판단점, PR 플래그**). 7.5.2 native에서 키 실발화 확인(LOG 2026-10-25 01:01) | 대기(머지 필요: jiwoong/m3-boundary-attempt-gradient) | 사람 |
| M3.2 | 그 gradient로 B0/B1/B3 비교: "state feedback이 random보다 먼저 위반을 찾는가". 지표는 executions-to-first-violation, unique states, 유효입력비 — 돌리기 전에 고정. negative/no-hit도 그대로 보고(right-censored). **1차 매트릭스 완료**(PR #151, P1/P2/P3 × 6 seed × budget 100): gradient 기작은 측정됨(P3 외부시도 4.6×) 그러나 **C1 rate 우위 미입증**(C1 P1 1/6·P3 0/6, budget 100 우측센서). **contamination 제거 후속**(어휘에서 대상 토큰 제거 + 관찰-이름 조합, A1/A2/A3 × 6 seed, LOG 11:00): A1 도달 바닥(0/6), A2/A3 관찰 이름으로 대상 segment 도달(target-agnostic), gradient 접근 시도↑ — 단 **clean exact C1은 전 arm 0/6**(어휘판 자율 C1은 contamination 덕이었음). powered 비교·clean exact C1은 더 많은 campaign/큰 budget 필요(M3.3) | 진행 | M3.1, 주언(feedback/eval) 협의 |
| M3.3 | (보조·대조군) escape 정책에서 budget을 크게 올려 자력 발견을 무작위로 확인 — "feedback 덕"이 아니라 대조 데이터로만 | 대기 | 없음 (호스트 docker) |

## M4 — 일반성 (2번째 extractor)

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M4.1 | oras-go adapter 설계(isolated CWD 포함), 동일 generic 모델·oracle로 연결. CVE/target-specific 로직을 generic 모듈에 섞지 않는다 | 대기 | 규민·민찬 협의 |
| M4.2 | (감사 제안) decompress(JS; CVE-2026-39243/39246 = symlink + absolute hardlink, CWE-59) 또는 2026 CWE-59 군집(adm-zip·Archive::Tar·HF datasets·borg) 중 1개를 2번째 target으로 — 동일 generic oracle 재사용. **중간발표 포함 여부 확인필요**(앞선 기능) | 대기 | 규민·민찬 협의 |

## 상시 (레인 담당)

| 태스크 | 상태 | 게이트 |
| --- | --- | --- |
| A/B/C(random / structure-aware / state-aware) **정의와 공통 지표** 확정 — M3.2가 쓸 측정의 기준 | 대기 | 주언 |
| 거부 입력에서 중간 상태 event 0개인 한계의 표현 방식 | 대기 | 민찬 |
| demo 이미지 ID 재현성(provenance attestation) | 대기 | 규민 |
| (감사 제안) coverage-guided baseline(D) + A/B/C/D 공통지표 — 'identity feedback 특정 효과'를 'feedback 일반'과 분리(H1 판정용). **중간발표 포함 여부 확인필요** | 대기 | 주언 |
