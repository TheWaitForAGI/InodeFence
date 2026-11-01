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
