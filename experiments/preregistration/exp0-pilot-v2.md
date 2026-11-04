# EXP-0 파일럿 사전등록 v2 (설계 등록; v1 대체)

**등록일:** 2026-11-03 · **단계:** 수술 4a(BACKLOG) · **기준:** [research-questions v2](../../docs/research/design/research-questions.md) · [D038](../../docs/DECISIONS.md) · **대체:** [exp0-pilot-v1](exp0-pilot-v1.md)(보존)

## 변경 사유 (v1 → v2)

1. **S 스케줄러 통제.** v1의 S는 adaptive 스케줄러라 retention 효과와 스케줄러 효과가 섞였다. 주 비교의 S를
   **S-u(identity/effect/boundary-attempt retention + uniform)**로 바꿔 D와 operator 정책을 동일하게 통제하고,
   adaptive를 얹은 **S-a는 탐색적 ablation(선택)**으로 분리한다.
2. **zero-hit 방침.** 5 seed × 200 × 3 arm = 3,000 실행이고 현 hazard 추정이 ~2e-5이면 기대 hit ≈ 0.06이라
   zero-hit이 기본 결과다. EXP-0이 hit로 무엇을 하지 않는지(아래 절)를 명시한다.
3. **백업 상태.** 원본 백업은 **미완료**다: 맥 raw는 체크섬 목록(`experiments/summaries/raw-manifest-mac-20261103.sha256`)만
   저장소에 있고 raw 자체는 호스트 로컬, 윈도우 raw 미반입, 외부/공유 저장소 백업 없음. EXP-0 raw도 같은 상태로
   시작하므로 실행 후 체크섬 목록을 저장소에 커밋하는 것을 완료 조건에 넣는다.
4. **rule-of-three 독립성 단위.** zero-hit 상한의 분모를 실행 수가 아니라 캠페인 수로 한다(실행 step은 캠페인 내
   비독립); 실행 단위 상한은 탐색적으로만 병기하고, 단위·계산 방식은 11/18 사전등록 전에 확정한다.

> **구속력.** 이 v2는 엔진 SHA·이미지 digest·policy ID가 비어 있는 **설계 등록**이다. G1(구현 수리) 동결 시 그 값을
> 채운 **v2.1을 실행 전에 커밋**해야 실행이 유효하다. **v2.1 커밋 이전의 실행은 EXP-0이 아니다.** v2.1은 아래 내용을
> 바꾸지 않고 빈 칸만 채운다.

## 목적

**인프라 측정**이다. 가설(H-A) 검증이 아니며, 파일럿 데이터는 **formal 추정(EXP-3)에 합산하지 않는다.** 목적은
EXP-3 규모와 EXP-2 GO/NO-GO 규칙의 숫자(x·n)를 실측으로 정하는 것이다.

## 대상

| 항목 | 값 | v2.1에서 채움 |
| --- | --- | --- |
| node-tar | 7.5.2 AFFECTED, frozen overlay `inodefence-node-tar-effect:7.5.2` (image_id prefix `sha256:21d8a0e3a5c5`) | 전체 image digest |
| Python tarfile | 3.12 `fully_trusted` (in-process) | 인터프리터 버전 문자열 |
| 엔진 | InodeFence main | 엔진 commit SHA |
| 컨트롤러 이미지 | 기존 production backend(격리계약·완화 플래그 0) | 컨트롤러 image digest |

## arm (R/D/S-u — research-questions v2 H-A와 동일)

| arm | retention | operator 선택 | 역할 | policy ID (v2.1에서 채움) |
| --- | --- | --- | --- | --- |
| R | 없음 | uniform | 무작위 바닥 | — |
| D | 구조 커버리지(`SearchPolicy.D`) | uniform | 커버리지 대조 | — |
| **S-u** | identity/effect/boundary-attempt | **uniform** | 주 비교 | — |
| S-a (선택) | S-u와 동일 | adaptive | 탐색적 ablation, 주 비교 아님; 호스트 시간이 남을 때만 | — |

세 주 arm은 **동일 어휘**(관찰 이름 포함 여부를 세 arm에 동일 적용)·seed·예산·이미지·oracle·operator 선택(uniform).
policy ID는 Evaluation 세션이 어휘 동등 R/D/S 러너를 구현한 뒤 v2.1에 기록한다.

## 설계

- **seed:** 9001, 9002, 9003, 9004, 9005 (5개; 기존 전 실험과 disjoint).
- **budget:** 200 / cell. 셀 = seed × arm × 타깃. 주 비교 3 arm = 3,000 실행(타깃당).
- **sentinel:** ≥ 3개. 이름은 **seed 고정 무작위 생성기**로 생성하고 생성기 seed를 결과에 기록한다(손으로 정한 이름 없음).
- **hit 정의:** post-state oracle **C1 ∨ C2**이고 `contract_violated`인 step. C0만은 hit가 아니다(baseline으로 별도 집계).
- **분모:** 모든 셀(abort 포함). abort는 우측중도절단으로 보고하고 분모에서 몰래 빼지 않는다.

## zero-hit 방침 (v2 추가)

3,000 실행 × hazard ~2e-5 → 기대 hit ≈ 0.06. **zero-hit이 기본 결과**이며 다음을 미리 정한다.

- **(a)** EXP-0은 C1/C2 hit으로 hazard를 **추정하지 않는다**. zero-hit이면 rule-of-three 상한만 보고하되, 실행 step은
  같은 캠페인 안에서 독립이 아니므로(corpus 계보·retention) 분모는 실행 수가 아니라 **캠페인 수**(3/n, n = 캠페인 수)로
  계산한다. 실행 단위 3/n(n = 실행 수)은 **탐색적 상한**으로만 병기한다. 독립성 단위(캠페인 vs 실행)와 상한 계산
  방식은 11/18 본실험 사전등록 전에 확정한다.
- **(b)** EXP-3 설계 입력은 **dense 신호**로 정한다: boundary-attempt 키 수, C0 도달(인덱스·비율), rejected 비율,
  처리량(exec/h), abort 사유별 수.
- **(c)** EXP-2 GO/NO-GO는 EXP-0이 아니라 **EXP-3 결과**에 11/18 사전등록된 규칙을 적용해 결정한다.
- **(d)** zero-hit은 NO-GO 사유가 **아니다**. "검정력 산정 불가 → EXP-3 hazard 상향 설계(다수 sentinel·budget 2000)
  진행"으로 처리한다.

## 측정 (전부 기록)

1. abort 수 — 사유별(observer evidence-integrity / docker broker / container cleanup / 기타)과 arm별 비율.
2. p95 full-step 시간(셀별·합산).
3. exec/h — 셀별·합산.
4. **per-case 컨테이너 vs 워커 풀** 처리량을 나란히(parity 확인; G1 조건).
5. arm별 첫 C0 / C1 / C2 인덱스(우측중도절단; 무hit=200, abort=abort 시점).
6. dense 신호 — boundary-attempt 키 수, rejected 비율(arm별).
7. hazard proxy = (C1 ∨ C2 step 수) / (실행 수) — zero면 캠페인 단위 rule-of-three 상한만 보고하고 실행 단위는 탐색적 상한으로 병기(위 (a)).
8. EXP-0 raw의 SHA-256 체크섬 목록(실행 후 저장소 커밋; 완료 조건).

## 파생 결정 (4a에서 작성)

EXP-2 GO/NO-GO 규칙 템플릿(EXP-3 결과에 적용):

> **EXP-3 R/D/S-u 합산 hazard ≥ x** 이고 **남은 호스트 시간으로 arm당 ≥ n 캠페인이 가능**하면 GO, 아니면 NO-GO.

**n**은 EXP-0 처리량·abort율 실측에서, **x**는 EXP-2 검정력 요구(목표 효과·n)에서 역산해 **11/14 확정**하고
**11/18 사전등록**(EXP-3 + EXP-2 규칙)에 넣는다. EXP-0의 hit 수는 x 산정에 쓰지 않는다((a)). 11/20에 EXP-3 결과에
규칙을 **기계적으로** 적용한다.

## 바뀌지 않는 것

안전경계(disposable sandbox + sentinel, 격리 완화 0), oracle 정의(C0/C1/C2 불변), CVE/대상경로/정답 seed/근접 보상
하드코딩 없음(D005/D006). 어휘에 피해 경로 이름을 넣는 것은 위협 모델(research-questions v2)의 일부이며 세 arm에
동일하게 적용된다.
