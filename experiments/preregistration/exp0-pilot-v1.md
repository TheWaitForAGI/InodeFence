# EXP-0 파일럿 사전등록 v1 (설계 등록)

**등록일:** 2026-11-03 · **단계:** 수술 4a(BACKLOG) · **기준:** [research-questions v2](../../docs/research/design/research-questions.md) · [D038](../../docs/DECISIONS.md)

> **구속력.** 이 v1은 엔진 SHA·이미지 digest·policy ID가 비어 있는 **설계 등록**이다. G1(구현 수리) 동결 시 그 값을
> 채운 **v1.1을 실행 전에 커밋**해야 실행이 유효하다. **v1.1 커밋 이전의 실행은 EXP-0이 아니다.** v1.1은 아래 내용을
> 바꾸지 않고 빈 칸만 채운다.

## 목적

**인프라 측정**이다. 가설(H-A) 검증이 아니며, 파일럿 데이터는 **formal 추정(EXP-3)에 합산하지 않는다.** 목적은
EXP-3 규모와 EXP-2 GO/NO-GO 규칙의 숫자(x·n)를 실측으로 정하는 것이다.

## 대상

| 항목 | 값 | v1.1에서 채움 |
| --- | --- | --- |
| node-tar | 7.5.2 AFFECTED, frozen overlay `inodefence-node-tar-effect:7.5.2` (image_id prefix `sha256:21d8a0e3a5c5`) | 전체 image digest |
| Python tarfile | 3.12 `fully_trusted` (in-process) | 인터프리터 버전 문자열 |
| 엔진 | InodeFence main | 엔진 commit SHA |
| 컨트롤러 이미지 | 기존 production backend(격리계약·완화 플래그 0) | 컨트롤러 image digest |

## arm (R/D/S — research-questions v2 H-A와 동일)

| arm | retention | operator | policy ID (v1.1에서 채움) |
| --- | --- | --- | --- |
| R | 없음 | uniform | — |
| D | 구조 커버리지(`SearchPolicy.D`) | uniform | — |
| S | identity/effect/boundary-attempt | adaptive | — |

세 arm은 **동일 어휘**(관찰 이름 포함 여부를 세 arm에 동일 적용)·seed·예산·이미지·oracle. policy ID는 Evaluation
세션이 어휘 동등 R/D/S 러너를 구현한 뒤 v1.1에 기록한다.

## 설계

- **seed:** 9001, 9002, 9003, 9004, 9005 (5개; 기존 전 실험과 disjoint).
- **budget:** 200 / cell. 셀 = seed × arm × 타깃.
- **sentinel:** ≥ 3개. 이름은 **seed 고정 무작위 생성기**로 생성하고 생성기 seed를 결과에 기록한다(손으로 정한 이름 없음).
- **hit 정의:** post-state oracle **C1 ∨ C2**이고 `contract_violated`인 step. C0만은 hit가 아니다(baseline으로 별도 집계).
- **분모:** 모든 셀(abort 포함). abort는 우측중도절단으로 보고하고 분모에서 몰래 빼지 않는다.

## 측정 (전부 기록)

1. abort 수 — 사유별(observer evidence-integrity / docker broker / container cleanup / 기타)과 arm별 비율.
2. p95 full-step 시간(셀별·합산).
3. exec/h — 셀별·합산.
4. **per-case 컨테이너 vs 워커 풀** 처리량을 나란히(parity 확인; G1 조건).
5. arm별 첫 C0 / C1 / C2 인덱스(우측중도절단; 무hit=200, abort=abort 시점).
6. **hazard proxy** = (C1 ∨ C2 step 수) / (실행 수), arm별·합산.

## 파생 결정 (4a에서 작성)

EXP-2 GO/NO-GO 규칙 템플릿:

> **EXP-3 R/D/S 합산 hazard ≥ x** 이고 **남은 호스트 시간으로 arm당 ≥ n 캠페인이 가능**하면 GO, 아니면 NO-GO.

x·n은 EXP-0 실측(hazard proxy·exec/h·abort율)으로 **11/14 확정**하고 **11/18 사전등록**(EXP-3 + EXP-2 규칙)에 넣는다.
11/20에 EXP-3 결과에 규칙을 **기계적으로** 적용한다.

## 바뀌지 않는 것

안전경계(disposable sandbox + sentinel, 격리 완화 0), oracle 정의(C0/C1/C2 불변), CVE/대상경로/정답 seed/근접 보상
하드코딩 없음(D005/D006). 어휘에 피해 경로 이름을 넣는 것은 위협 모델(research-questions v2)의 일부이며 세 arm에
동일하게 적용된다.
