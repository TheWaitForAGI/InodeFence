# 4. Method (드래프트 v1)

전체 설계의 기준은 [`../../docs/research/design/architecture.md`](../../docs/research/design/architecture.md)이며,
이 절은 결과(§5)를 읽는 데 필요한 범위로 요약한다.

## 4.1 루프 (Stage A–G)

testcase 하나는 다음 책임 순서로 흐른다. 이 순서가 M1 루프의 한 바퀴다.

```text
Stage A  Seed Generator     작고 정상적인 ArchiveCase 생성
Stage B  Structure Mutator  generic rule로 archive 구조 변형
Stage C  TAR Builder        ArchiveCase -> deterministic USTAR bytes
Stage D  Target Adapter     격리 환경에서 실제 extractor 실행
Stage E  State Observer     BEFORE/AFTER StateSnapshot 캡처·비교
Stage F  Security Oracle    snapshot을 C0/C1/C2 Contract와 비교
Stage G  Feedback / Corpus  새 state/violation이면 다음 parent로 보존 -> 다음 mutation
```

단일 실행 runner는 `pipeline.run_case`이고, sandbox lifecycle은 `runtime`이다. `run_case`는
TAR/layout/sentinel/target 준비 뒤 BEFORE를 찍고, target 종료 직후 bookkeeping/cleanup 이전에
AFTER를 찍는다. `StateSnapshot`에서 결과가 둘로 갈라진다: **StateSignature**("이전과 어떻게 다른가"
→ Feedback)와 **ViolationResult**("Contract를 위반했는가" → Oracle).

## 4.2 generic과 target-specific의 분리

연구 질문이 "고정 recipe 없이 generic mutation + state feedback"이므로, target/CVE 로직이 generic
경로에 새지 않는 것이 설계의 핵심 불변식이다.

- **Generic (target 무지):** `model/`, `generator/`, `mutator/`, `builder`, `observer/`, `oracle/`,
  `feedback/`, `pipeline`. Mutator는 8개 generic operator(add/remove/duplicate/reorder/path/hardlink/
  symlink/link-target)만 가지며 target-specific vulnerability recipe를 소유하지 않는다. Observer는
  `(st_dev, st_ino)`·nlink·mode·size·content digest·link text 같은 **사실만** 기록하고 취약 여부를
  판단하지 않는다. Oracle은 Contract를 적용하되 filesystem 접근·target 실행을 하지 않는다.
- **Target-specific (격리):** `targets/`(node-tar worker 등)와 `execution/`(container backend). 실행
  command·runtime·version·option·stdout/stderr·exit code·timeout만 target-specific으로 허용하며,
  node-tar/version/CVE 조건을 generic Mutator·Observer·Oracle·Feedback에 넣지 않는다.

## 4.3 object-identity feedback

이 연구의 가설이 지목하는 feedback은 **filesystem-security-state**다: 추출 객체와 외부 객체 사이의
object identity(§2.1)와 보호된 외부 sentinel에 대한 external effect(§2.3). Feedback은 관찰된 state의
정규화 키(StateSignature)를 소비하며, 새 state 또는 새 violation fingerprint면 그 입력을 다음 parent로
보존(retention)하고 다음 mutation의 바탕으로 쓴다.

부분 진척 신호로 **target-agnostic boundary-attempt 신호**가 effect key에 추가된다("extraction root
밖에 새 네임스페이스 객체/identity 관계가 생기려는 시도"). 이는 거부된 외부-하드링크 시도도 valid
trace로 관찰(producer abort-drain)해 all-or-nothing final oracle이 주지 못하는 gradient를 준다.
sentinel 경로·CVE를 feedback에 심지 않으며, EXTERNAL 판정은 region 기준 target-agnostic이다. 이
신호는 M1 경로에 additive로 들어가며 기존 C0/C1/C2 판정·fixture·N01 경로를 바꾸지 않는다.

> **EN-008 준수:** "새 state/fingerprint 수"는 진척·effectiveness의 척도가 아니다. boundary-attempt
> 키 수나 unique state 수를 effectiveness 결론으로 옮기지 않는다(중간상태는 search behavior로만 서술).

## 4.4 비교 arm 정의 (§5에서 사용)

결과에서 쓰는 arm 라벨은 다음 두 축에서 정의된다. 라벨의 정확한 정의는 각 validated summary와
[`../../docs/research/design/research-questions.md`](../../docs/research/design/research-questions.md)의
RQ2/RQ3를 따른다.

- **M3 자력발견 study arm**([M3 요약](../../experiments/summaries/node-self-discovery-mechanism-v1.md) 정의):
  `A3full` = state-aware escape-hardlink(`uniform-generic-m1-state-aware-escape-hardlink-v1`),
  `A3blind` = 동일하되 관찰 이름에서 EXTERNAL region 제외(identity-blind 대조),
  `A1` = 무작위 바닥(token-clean, state-aware 외부 주소지정 없음). search 정책은
  `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1`.
- **item-3 단일경로 A/B/C/D arm**(Ledger 정의): `A` = B0/legacy(무작위), `B` = B0/M1(구조),
  `C` = B3/M1(identity-state feedback), `D` = coverage-guided/M1. 이들은 한 `run_search_campaign`
  경로로 돌리고 공통 지표로 읽는다.

## 4.5 증거 사슬 규율

모든 정량 주장은 다음 사슬로 추적 가능해야 한다.

```text
raw experiment output -> validated summary -> finding -> 이 드래프트 -> Capability Ledger 행
```

Research Plane(무엇을 위험으로 볼지 정의) → Runtime Engine(생성·변형·실행·관찰·판정·선택) →
Evidence Plane(raw 결과 → 재현·최소화 → finding → paper)의 세 Plane을 분리하며, **raw 결과가 곧
논문 주장은 아니다.** observed(실행 출력으로 확인)와 inferred(추론)를 문장에서 구분하고, synthetic을
native 증거로 승격하지 않는다(§5의 각 소절이 이 규율을 따른다).

## 4.6 실험 설계 (계획 — 11/18 사전등록 후 잠금)

이 소절은 **결과가 아니라 계획**이다. 설계 기준은 [research-questions v2 H-A](../../docs/research/design/research-questions.md)와
[EXP-0 파일럿 사전등록 v2](../../experiments/preregistration/exp0-pilot-v2.md)이며, **지표·예산·hit 정의·분모 규칙은
11/18 사전등록 시점에 잠근다** — 그 이후에는 바꾸지 않고 수정은 새 버전 파일로만 한다. 엔진 SHA·이미지
digest·**policy ID 문자열은 G1(구현 수리) 동결 시 사전등록 v2.1에 채운다. 현재 미동결(TBD)이므로 아래 arm은
retention·스케줄러 정의로만 고정하고 policy ID 문자열은 v2.1에서 기록한다.**

### 4.6.1 비교 arm (R / D / S-u; S-a는 ablation)

세 주 arm은 어휘(관찰 이름 포함 여부를 세 arm에 동일 적용)·seed·예산·이미지·oracle·operator 선택(uniform)이
모두 같고 **retention 정책만** 다르다. 주 비교의 S는 **S-u(uniform 스케줄러)**다(D와 operator 정책을 동일 통제해
retention 효과만 분리). adaptive 스케줄러를 얹은 **S-a**는 주 비교가 아니라 탐색적 ablation(선택)이며 S-a − S-u는
스케줄러 효과로 따로 해석한다.

| arm | retention | operator 선택 | 뜻 | policy ID |
| --- | --- | --- | --- | --- |
| **R** | 없음 | uniform | 무작위 탐색(바닥) | TBD (v2.1 동결 시 기록) |
| **D** | 구조 커버리지(`SearchPolicy.D` = target-agnostic extraction 구조 키) | uniform | 커버리지 피드백 대조 | TBD (v2.1; `SearchPolicy.D` 러너) |
| **S-u** (주) | identity/effect/boundary-attempt 상태 키 | uniform | InodeFence retention 피드백 | TBD (v2.1 동결 시 기록) |
| S-a (선택, ablation) | S-u와 동일 | adaptive | 스케줄러 효과 분리용, 주 비교 아님 | TBD (v2.1) |

> policy ID 각주: 구현 후보 ID는 PR #206의 `EffectSearchPolicy`/`MutationPolicy`를 참조하며, 최종 문자열은
> 사전등록 v2.1 동결 시 기록한다.

**sentinel.** ≥ 3개를 쓰고, 이름은 **seed 고정 무작위 생성기**로 만들며 생성기 seed를 결과에 기록한다(손으로 정한
이름 없음). 어휘에 피해 경로 이름을 넣는 것은 위협 모델(research-questions v2)의 일부이며 세 arm에 동일하게
적용한다 — 따라서 blind 발견을 주장하지 않는다.

### 4.6.2 지표와 분석

- **1차 종속변수 T_first** — 첫 `C1 ∨ C2`까지의 실행 수. **우측중도절단**(완주 무hit = 예산 N에서 절단, abort =
  abort 시점에서 절단). **생존분석**으로 비교한다: Kaplan–Meier 곡선, 로그랭크 검정, Vargha–Delaney A12.
- **1차 종속변수 U_viol** — 고유 위반 입력 수(정규화 서명 기준; 같은 lineage·같은 fingerprint는 1).
- **hit 정의** — post-state oracle `C1 ∨ C2`이고 `contract_violated`인 step. **C0만은 hit가 아니다**(path-boundary
  baseline으로 별도 집계).
- **dense 신호**(boundary-attempt 키 수·C0 도달 인덱스/비율·rejected 비율·exec/h·abort 사유별 수) — 탐색 거동
  설명용이며 **effectiveness 척도가 아니다(EN-008)**. 새 state key 수를 보안 이득 결론으로 옮기지 않는다.
- **seed-block paired** — 동일 seed 블록 안에서 arm을 **쌍으로** 비교한다(seed 간 분산을 공통 블록으로 통제).
- **abort 민감도(3정책)** — abort 처리 규칙을 바꿔 결론 robustness를 확인한다: (1) **우측중도절단**(1차 분석),
  (2) **완주-only**(abort 셀 제외), (3) **abort = no-hit**(보수적 하한). 분모는 항상 abort 포함/제외를 명시하고
  abort를 몰래 빼지 않는다.

### 4.6.3 실험 순서

1. **EXP-0 파일럿** — seed {9001..9005} × budget 200 × R/D/S-u, 인프라·dense 신호 실측. **zero-hit이 기본 결과**이며
   C1/C2 hit으로 hazard를 추정하지 않는다(zero면 캠페인 단위 rule-of-three 상한만 참고로 병기).
2. **11/18 사전등록 잠금** — EXP-3 본실험 + EXP-2 GO/NO-GO 규칙을 고정한다. 규칙의 n(arm당 캠페인 수)·x(목표
   효과)는 EXP-0 처리량·abort율 실측에서 **11/14 확정**한다. EXP-0의 hit 수는 x 산정에 쓰지 않는다.
3. **EXP-3 본실험** — 20 seed × budget 2000 × R/D/S-u, 다수 sentinel. 1차 지표 T_first(우측중도절단)·U_viol.
4. **11/20 규칙 기계 적용** — EXP-3 결과에 사전등록된 GO/NO-GO 규칙을 **그대로** 적용한다(결과를 본 뒤 규칙을
   바꾸지 않는다).
5. **EXP-2 조건부** — GO일 때만 수행한다.

### 4.6.4 판정 시나리오

아래 표는 [research-questions v2 '판정 시나리오'](../../docs/research/design/research-questions.md)를 그대로 인용한다
(S는 주 비교의 S-u; S-a는 ablation으로 별도 보고).

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

**예측(사전등록 전 가설).** S-u가 R보다 T_first 중앙값이 2배 이상 빠르고(로그랭크 p < 0.05, A12 ≥ 0.64) S-u ≠ D.
**반증.** S-u와 R의 생존곡선이 분리되지 않는다.

### 4.6.5 결과 자리 (실험 전 — TBD)

다음은 EXP-3 실행 후 채운다. 현재는 **TBD**다.

- 표: arm별 T_first 생존표(중앙값·로그랭크 p·A12), U_viol 수, abort 3정책 민감도. — **TBD**
- 그림: R/D/S-u Kaplan–Meier 생존곡선. — **TBD**

## 4.7 AI 도구 사용 (재현성·공개)

이 프로젝트는 코드 작성·분석·문서화에 Claude(Claude Code) 코딩 에이전트를 적극 사용했다(저장소 바이브코딩
정책 [`AGENTS.md`](../../AGENTS.md)). 공개 기준으로 다음을 명시한다.

- **검토 게이트.** 모든 코드 변경은 브랜치 → PR → CI → 검토(verifier 또는 사람) → squash 머지 경로를 거친다.
  안전경계와 연구 불변식(disposable sandbox + sentinel, 격리 완화 0, D005 CVE-specific oracle 금지, D006 known
  PoC seed 금지, D007 zero-day는 성공 조건 아님, oracle C0/C1/C2 정의 불변)은 에이전트가 바꾸지 못한다.
- **정량 지표(기준 SHA `24867be` = main #204 머지, 2026-11-04 핀).** 이 커밋 기준 전체 **414개** 커밋 중
  **96개**가 Claude를 co-author로 명시한다(`git log 24867be --grep='Co-Authored-By: Claude' --format=%H | wc -l`
  = 96; `git rev-list --count 24867be` = 414). 지정 집계 명령 `git log 24867be --format=%b | grep -c
  "Co-Authored-By: Claude"`는 trailer **라인 143**을 반환하는데, 이는 squash 머지가 여러 커밋의 co-author
  trailer를 하나의 커밋 본문에 합치기 때문이다(라인 수 ≥ 커밋 수). 기준 SHA를 핀했으므로 main이 진행해도
  같은 값으로 재현된다.
- **증거 규율.** 에이전트 산출물과 사람 검증을 구분하며, raw 결과 → validated summary → finding → 이 드래프트의
  증거 사슬(§4.5)과 observed/inferred 구분을 유지한다. 에이전트가 생성한 수치가 자동으로 논문 주장이 되지 않는다.
