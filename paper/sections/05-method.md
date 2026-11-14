# 4. Method (드래프트 v2)

전체 설계의 기준은 [`../../docs/research/design/architecture.md`](../../docs/research/design/architecture.md)이며,
이 절은 결과(§5)를 읽는 데 필요한 범위로 요약한다. 등록 실험의 기준은 동결된 사전등록 파일
`experiments/preregistration/exp3-v1.md`(EXP-3 train)와 `experiments/preregistration/exp2-v1.md`(EXP-2 holdout)다.

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

핵심 RQ는 동일 어휘·동일 예산 아래 피드백 정책만 바꿔 비교한다. 따라서 CVE 식별자·PoC·고정 공격 패턴·대상 경로·sentinel 이름을
oracle과 feedback에 넣지 않고, target/CVE 로직이 generic 경로에 새지 않는 것이 설계의 핵심 불변식이다.

- **Generic (target 무지):** `model/`, `generator/`, `mutator/`, `builder`, `observer/`, `oracle/`,
  `feedback/`, `pipeline`. Mutator는 8개 generic operator(add/remove/duplicate/reorder/path/hardlink/
  symlink/link-target)를 가지며 CVE별 PoC를 소유하지 않는다. 다만 mutation 정책에는 escape-hardlink 문법과 관찰 이름 어휘가 있으므로 고정 패턴이 전혀 없다는 뜻은 아니다. Observer는
  `(st_dev, st_ino)`·nlink·mode·size·content digest·link text 같은 **사실만** 기록하고 취약 여부를
  판단하지 않는다. Oracle은 Contract를 적용하되 filesystem 접근·target 실행을 하지 않는다.
- **Target-specific (격리):** `targets/`(node-tar worker 등)와 `execution/`(container backend). 실행
  command·runtime·version·option·stdout/stderr·exit code·timeout만 target-specific으로 허용하며,
  node-tar/version/CVE 조건을 generic Mutator·Observer·Oracle·Feedback에 넣지 않는다.

## 4.3 상태 피드백 (S-u가 보존하는 것)

가설이 지목하는 feedback은 **filesystem-security-state**다: 추출 객체와 외부 객체 사이의
object identity(§2.1)와 보호된 외부 sentinel에 대한 external effect(§2.3). Feedback은 관찰된 state의
정규화 키(StateSignature)를 소비하며, 새 state 또는 새 violation fingerprint면 그 입력을 다음 parent로
보존(retention)하고 다음 mutation의 바탕으로 쓴다.

**target-agnostic boundary-attempt 신호**가 effect key에 추가된다("extraction root
밖에 새 네임스페이스 객체/identity 관계가 생기려는 시도"). 거부된 외부-하드링크 시도도 valid
trace로 관찰(producer abort-drain)해 이 키로 기록한다.
sentinel 경로·CVE를 feedback에 심지 않으며, EXTERNAL 판정은 region 기준 target-agnostic이다. 이
신호는 M1 경로에 additive로 들어가며 기존 C0/C1/C2 판정·fixture 경로를 바꾸지 않는다.

> **EN-008 준수:** "새 state/fingerprint 수"는 진척·effectiveness의 척도가 아니다. boundary-attempt
> 키 수나 unique state 수를 effectiveness 결론으로 옮기지 않는다(중간상태는 search behavior로만 서술).

## 4.4 비교 arm 설계 경위

초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다(§4.6.1).

## 4.5 증거 사슬 규율과 재현성 인프라

모든 정량 주장은 다음 사슬로 추적 가능해야 한다.

```text
raw experiment output -> validated summary -> finding -> 이 드래프트 -> Capability Ledger 행
```

raw 출력은 SHA-256 매니페스트(`experiments/summaries/raw-manifest-*.sha256`)로 고정하고, 요약이 raw까지 닿는지를
증거 사슬 점검(`scripts/check_evidence_chain.py`, `make check`에 연결)으로 검사하며, 표 생성기의 출력과 커밋된 표를
바이트로 대조한다. 실험 호스트는 호스트 적격성 검증(호스트별 12 캠페인)을 통과해야 쓰고, 두 호스트의 공통 셀 12개를
교차 비교했다 [C-INFRA]. observed(실행 출력으로 확인)와 inferred(추론)를 문장에서 구분하고, synthetic을 native 증거로
승격하지 않는다.

## 4.6 등록 실험 설계 (2026-11-13 동결)

이 소절은 **결과가 아니라 설계**다. 가설·arm·표본 수·분석·판정표는 결과를 보기 전에 Git에 동결됐다(동결 커밋
`72de299`) [C-DESIGN]. 동결 전에 본 결과는 공개된 EXP-0(§5.6), 비등록 위험도 파일럿(§5.7), 측정 사슬 대조(§5.4)뿐이며,
파일럿 값은 표본 수 산정, R 변형 선택(D6), 사전등록 예측의 개정에 썼다 [C-PILOT].

### 4.6.1 비교 arm (R / D / S-u)

세 arm은 어휘(관찰 이름 포함 여부를 세 arm에 동일 적용)·seed·예산·이미지·oracle·operator 선택(uniform)이 모두 같고
**retention 정책만** 다르다 [C-DESIGN].

| arm | retention | 뜻 | 등록 policy ID |
| --- | --- | --- | --- |
| **R** | 없음, 매 실행 seed에서 다시 시작 | 무작위 탐색 | `unretained-seed-restart-v1-uniform-mutation-v1` |
| **D** | 구조 커버리지(target-agnostic extraction 구조 키) | 커버리지 피드백 대조 | `structure-coverage-v1-uniform-mutation-v1` |
| **S-u** | identity/effect/boundary-attempt 상태 키(§4.3) | 상태 피드백 | `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1` |

S-u의 boundary 키는 특정 패턴이나 경로를 담지 않지만 결함 계열 수준의 사전 지식이다. D는 구조 커버리지 유도 퍼징의
대리이며 코드 커버리지 기준선이 아니다(exp2-v1 §6) [C-DESIGN]. 어휘에 피해 경로 이름을 넣는 것은 위협 모델의 일부이며
세 arm에 똑같이 적용한다. sentinel은 5개이고 이름은 seed
고정 무작위 생성기로 만든다(등록 블록 `sentinel_count`, `sentinel_generator_seed`).

### 4.6.2 지표

- **1차 종단점 T_first** — 첫 `C1 ∨ C2` 사건까지의 실행 수. 우측중도절단(사건 없이 완주하면 예산에서, abort는 abort
  시점에서 절단).
- **hit 정의** — post-state oracle `C1 ∨ C2`이고 `contract_violated`인 step. C0만은 hit가 아니다.
- **U_viol**(고유 위반 입력 수)은 확증 종단점이 아니며 보고만 한다(exp2-v1 §5).
- **dense 신호**(boundary-attempt 키 수 등)는 탐색 거동 설명용이며 effectiveness 척도가 아니다(EN-008).
- **abort 민감도** — 1차 분석은 `censor-at-abort`이고, `censor-at-budget`·`exclude`를 함께 보고한다. 분모의 abort
  포함·제외를 항상 밝힌다.

### 4.6.3 실험 순서와 규모

1. **EXP-0(등록 실행, 인프라 측정, 2026-11-05).** node-tar 7.5.2, seed 9001–9005 × R/D/S-u, 캠페인당 실행 200(§5.6) [C-EXP0].
2. **사전등록 동결(2026-11-13, `72de299`)** [C-DESIGN].
3. **EXP-3 train(탐색).** node-tar 7.5.2, seed 9006–9025(20개) × R/D/S-u, 캠페인당 실행 2000, 두 호스트(jobs 2).
   arm별 결과는 탐색이며 확증에 쓰지 않는다 [C-DESIGN].
4. **GO 판정.** train이 끝난 뒤 등록 규칙 `GO = E ≥ 1 ∧ ⌊H_rem·r ÷ (6000·e)⌋ ≥ 76 ∧ train abort ≤ .45`를 기계적으로
   적용한다. E는 세 arm 합산 첫 C1∨C2 캠페인 수이고, arm별 값은 GO 입력이 아니다(exp3-v1 §5) [C-GO].
5. **EXP-2 holdout(확증).** node-tar 7.4.4, seed 9026–9185(N = 160) × R/D/S-u, 캠페인당 실행 2000. holdout 할당은 GO
   파일의 호스트별 처리량으로 정했다(exp2-v1 §4). 마감(2026-11-25 12:00 KST)에 끝나지 않은 seed는 블록째 분석에서
   빠지고 N은 바뀌지 않는다 [C-DESIGN].

### 4.6.4 확증 분석과 판정표

holdout 확증 분석은 exp2-v1 §5를 따른다 [C-DESIGN].

- **통계량.** 대비마다 합동 2-arm 로그랭크 χ², 기준 분포는 seed 블록 안 arm 라벨 순열이다.
- **다중성.** 확증 패밀리는 S-u vs R, S-u vs D 두 대비이고, 패밀리 α = .05 양측 Holm이다. 방향은 `faster_arm`으로 읽는다.
- **HR 추정.** 대비마다 Peto 추정량과 seed 블록 부트스트랩 95% 구간을 등록 스크립트로 낸다.
- **판정표(D12).** 두 대비의 기각 여부와 방향, 정보 블록 수 I(임계 7), HR 구간 상한(2 기준)으로 ①(두 대비 모두 S-u
  쪽 기각), ②(S-u vs R만), 분리 실패(HR 2 배제 / 판단 유보), 미검정, ⑤(사건 0), ⑧(R 쪽 기각, 반증) 등의 행 하나를
  고른다. 결과 문장은 이 표의 문장만 쓴다.

**사전등록 예측(결과 아님).** 문법 몬테카를로로 계산한 R의 캠페인당 사건 확률은 .445(.38–.50)이고, retention 효과의
해석적 낙관 상한은 HR 약 1.1–1.3이다. 등록된 기대 결말은 비기각과 HR 2 배제다(exp2-v1 §1) [C-DESIGN] [C-LIM1].

### 4.6.5 본실험 결과 자리

- EXP-3 train의 arm별 결과: 본실험 결과 자리(봉인 해제 뒤 기입) [S-TRAIN]
- EXP-2 holdout 확증 판정: 본실험 결과 자리(봉인 해제 뒤 기입) [S-HOLDOUT]

## 4.7 AI 도구 사용 (재현성·공개)

이 프로젝트는 코드 작성·분석·문서화에 Claude(Claude Code) 코딩 에이전트를 적극 사용했다(저장소 바이브코딩
정책 [`AGENTS.md`](../../AGENTS.md)). 공개 기준으로 다음을 명시한다.

- **검토 게이트.** 모든 코드 변경은 브랜치 → PR → CI → 검토(verifier 또는 사람) → squash 머지 경로를 거친다.
  안전경계와 연구 불변식(disposable sandbox + sentinel, 격리 완화 0, CVE-specific oracle 금지, known PoC seed 금지,
  oracle C0/C1/C2 정의 불변)은 에이전트가 바꾸지 못한다. 동결·GO·재개·해제 같은 실험 절차의 결정은 사람이 하거나
  사람이 위임한 규칙으로 한다.
- **증거 규율.** 에이전트 산출물과 사람 검증을 구분하며, raw 결과 → validated summary → finding → 이 드래프트의
  증거 사슬(§4.5)과 observed/inferred 구분을 유지한다. 에이전트가 생성한 수치가 자동으로 논문 주장이 되지 않는다.
