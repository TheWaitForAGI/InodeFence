# 연구 질문과 가설 (v2)

**v2 — 2026-11-03.** 2026-11-03 독립 감사 문서(Claude Doc 「InodeFence 독립 연구 감사 및 실험 설계 재정립」,
https://claude.ai/artifact/JJtsK3VowEGuBFN3YXZDFq)를 채택해 전면 교체했다([D038](../../DECISIONS.md)).
v1의 RQ1–RQ6·H1–H4는 아래 **'폐기·대체 기록'**에 남긴다. 실행 기준은 Git에 동결된 사전등록 파일
([`experiments/preregistration/`](../../../experiments/preregistration/README.md))이고, 증거 기준은 raw +
SHA-256 목록이다. DESIGNED / IMPLEMENTED / TESTED / EXPERIMENTALLY VALIDATED 구분과 observed/inferred 구분은
그대로 유지한다. 현재 취약점을 주장하지 않는다.

## 연구 동기 (why)

2026-11-03 독립 감사(Report 2 꼭지 02 '연구 필요성')의 권고를 채택해 동기를 세 문장으로 고정한다:

1. 2026년 node-tar 하드링크 회귀(CVE-2026-23745 → 그 수정이 만든 회귀 CVE-2026-24842)는 **수정 자체가 새
   경계위반을 만들 수 있음**을 보인다(M2 2-CVE 차분).
2. 그러므로 CVE별 PoC가 아니라 **일반 불변식(C1/C2)으로 릴리스마다 자동 검사**할 도구가 필요하다.
3. 이 프로젝트는 그 불변식을 **generic oracle로 구현**하고, 그 oracle이 **퍼징 탐색 신호로도 유효한지**(H-A)
   묻는다. 음성 결과("피드백이 무작위와 다르지 않다")도 "oracle은 유용하되 탐색 신호로는 약하다"는 지식으로
   보고한다.

**수혜자 산출물.** 1차 수혜자는 extractor 유지보수자다 — 릴리스 전 회귀 검사 명령
`make regression TAR_VERSION=<x>`([#218](https://github.com/TheWaitForAGI/InodeFence/pull/218), 감사 산출물 ⑫)로
C1/C2 경계 회귀를 CVE 하드코딩 없이 점검한다.

## 핵심 RQ

> 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래서, filesystem security state(C1 identity·C2 effect)를
> retention·스케줄링 피드백으로 쓰는 탐색이 **무작위 탐색**과 **구조 커버리지 탐색**보다 첫 경계위반까지의
> 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가?

### 하위 질문

- **SQ-a (oracle 일반성).** 같은 generic oracle(C0/C1/C2, CVE 문자열 없음)이 여러 extractor의 취약/수정 쌍을
  코드 변경 없이 구분하는가?
- **SQ-b (피드백 분리).** identity/effect 피드백이 커버리지 피드백과 **다른 탐색 경로**를 만드는가? 현재
  escape-hardlink 문법에서는 identity(C) ≡ coverage(D)가 operationally identical(4/4 짝 seed)인 **음성**이고,
  symlink 계열 문법(M4.8)에서는 mechanistic distinctiveness만 관찰됐다(effectiveness 아님).

## 위협 모델 (v2 추가)

공격자는 **피해 경로 이름**(보호 대상 외부 객체의 추출 루트 기준 상대 경로)을 안다고 가정하고, 그 이름을
세 arm의 어휘에 **동일하게** 포함한다. 따라서 이 연구는 blind 발견을 주장하지 않으며, 어떤 프레이밍에서도
"blind 아님"을 명시한다. 비교의 대상은 "이름을 아는 상태에서 **어떤 피드백이 위반에 더 빨리·더 많이
도달시키는가**"다.

## H-A (주 가설) — 피드백 정책

**독립변수: retention 피드백 정책 3 arm.** 세 arm은 어휘(관찰 이름 포함 여부를 세 arm에 동일 적용)·seed·
예산·이미지·oracle·**operator 선택(uniform)**이 모두 같고 retention 정책만 다르다. 주 비교의 S는
**S-u(uniform 스케줄러)**다 — D와 operator 정책을 동일하게 통제해 retention 효과만 분리한다. adaptive
스케줄러(기존 P3)를 얹은 **S-a**는 주 비교가 아니라 **탐색적 ablation(선택)**이며, S-a − S-u는 스케줄러
효과로 따로 해석한다(retention 효과와 섞지 않는다).

| arm | retention | operator 선택 | 뜻 |
| --- | --- | --- | --- |
| **R** | 없음 | uniform | 무작위 탐색(바닥) |
| **D** | 구조 커버리지(`SearchPolicy.D` = target-agnostic extraction 구조 키) | uniform | 커버리지 피드백 대조 |
| **S-u** (주) | identity/effect/boundary-attempt 상태 키 | uniform | InodeFence retention 피드백 |
| S-a (선택, ablation) | S-u와 동일 | adaptive | 스케줄러 효과 분리용, 주 비교 아님 |

**종속변수.**

- **T_first** — 첫 C1 ∨ C2까지의 실행 수. **우측중도절단**: 완주 무hit는 N(예산)에서 절단, abort는 abort
  시점에서 절단. 생존분석(Kaplan–Meier, 로그랭크, Vargha–Delaney A12)으로 비교한다.
- **U_viol** — 고유 위반 입력 수(정규화 서명 기준; 같은 lineage·같은 fingerprint는 1).

**예측.** S-u가 R보다 T_first 중앙값이 **2배 이상 빠르고**(로그랭크 p < 0.05, A12 ≥ 0.64) **S-u ≠ D**다.

**반증.** S-u와 R의 생존곡선이 분리되지 않는다.

## H-B — generic oracle 일반성

CVE 문자열·버전·PoC 바이트를 넣지 않은 generic C0/C1/C2가 **≥ 3 extractor**의 취약/수정 쌍을 손 fixture로
구분한다. 사실상 충족(node-tar 5 릴리스 차분 M2, Python tarfile `fully_trusted`/`data`, oras-go·decompress 통제
차분 #176/#177)이며 수술 기간에 **재확인**한다. snapshot 한계상 transient effect와 check/use coherence는
측정 범위가 아니다.

## H-C (보조) — 어휘 음성 통제

현재 generic 어휘로는 기본 sentinel 이름을 철자할 수 없고(코드상 사실: `src/inodefence/mutator/m1.py`의
`COMPONENTS` 7토큰, `m1_addressing.py` 주석), 실험상 A1 0/19 완주·A3blind 6셀 7,983 step에서 C1이 관찰되지
않았다(음성 통제, observed). 외부 객체 이름이 어휘 토큰과 일치하는 설정에서는 도달할 수 있으므로 일반적
"구조적 불가"로 단정하지 않는다. 이는 위협 모델 전제(이름을 알아야 도달)를 지지하는 **미관찰** 결과이지
effectiveness 주장이 아니다.

## 판정 시나리오

아래 S는 주 비교의 **S-u**다(S-a는 ablation으로 별도 보고).

| # | 관찰 | 판정 |
| --- | --- | --- |
| ① | S > R **그리고** S > D (T_first·U_viol 양쪽) | 가속 주장 가능 |
| ② | S > R이나 S ≈ D | 피드백 **일반** 효과만(identity 특정 효과 미입증) |
| ③ | 탐색 지표(새 state key 등)는 다르나 위반은 동등 | 보안 이득 미입증(EN-008) |
| ④ | 알려진 클래스만 발견 | 정상(D007: zero-day는 성공 조건 아님) |
| ⑤ | 전 arm 위반 0 | 미관찰로 보고·분모 명시·rule of three 상한(캠페인 단위 참고 상한일 뿐, 판정 입력 아님) |
| ⑥ | extractor 간 불일치 | oracle 일반성(H-B)과 피드백 일반성(H-A)을 분리해 보고 |
| ⑦ | S의 비용 과다 | 실행 수 외에 시간 정규화 지표 병기 |
| ⑧ | S ≤ R | **반증** |

## 평가 원칙

- 동일 어휘·seed·이미지(digest)·oracle·operator 선택(uniform). 세 arm은 retention 정책 외 어떤 것도 다르지 않다.
- **사전등록 뒤 변경 금지.** 지표·예산·hit 정의·분모 규칙은 `experiments/preregistration/`에 커밋된 뒤 바꾸지
  않는다. 수정은 새 버전 파일로만.
- 검정력은 EXP-0 파일럿 **실측**(검정력 입력은 dense 중간상태 신호·처리량·abort율)에서 산출하고 그 값으로
  EXP-3 규모를 고정한다. hazard proxy는 **참고값으로만 기록하며 검정력·판정 입력이 아니다**(사전등록 v2 (a)·(b)).
- 새 state key 수·fingerprint 수는 **탐색 거동 설명용**일 뿐 effectiveness 척도가 아니다(EN-008).
- 분모는 항상 abort 포함 여부를 명시하고, abort는 우측중도절단으로 보고한다.
- Paired seed, 독립 반복, negative/invalid 결과를 보존한다. 결과를 본 뒤 방법을 바꾸지 않는다.

## 폐기·대체 기록 (v1 → v2)

| v1 | v2 처분 |
| --- | --- |
| RQ1 Known Vulnerability Rediscovery | **EXP-5 산출물**(최소화·교차 replay)로 이동. 성공 조건이 아니라 산출물이다. |
| RQ2 Feedback Effectiveness (B0/B1/B3) | **H-A R/D/S로 대체.** |
| RQ3 Feedback/Mutation Ablation (A1/A2/A3 projection·reorder) | **H-A R/D/S로 대체.** 기호 **A1/A3**는 [baseline-and-ablation-v1](../benchmarks/baseline-and-ablation-v1.md)의 projection 의미와 M3 요약의 arm 이름(A1 random floor·A3full state-aware)이 충돌했으므로 **더 쓰지 않는다**. |
| RQ4 Cross-Implementation Generality | **H-B.** |
| RQ5 Unknown-State Discovery | **D007 유지**(성공 조건 아님). |
| RQ6 Entry-Transition Feedback · H3 Transition Retention · H4 Transition-Adaptive Mutation | **폐기.** BACKLOG M3.6: ordered entry-transition 경계는 현 extractor군에서 관찰 불가(honest negative, [transition-feedback-v1](transition-feedback-v1.md)). |
| H1 State-Guided Search | **H-A.** |
| H2 Generic Security Contract | **H-B.** |

v1의 G0 freeze 기준(main `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`, [Research Contract v1](research-contract-v1.md))은
역사 기록으로 남고, v2의 실행 기준은 사전등록 파일이 가리키는 엔진 SHA·이미지 digest·policy ID다.
