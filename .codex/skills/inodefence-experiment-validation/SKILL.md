---
name: inodefence-experiment-validation
description: Validate InodeFence fuzzing experiments for reproducibility, evidence quality, and paper readiness. Use before promoting raw runs to validated summaries, findings, comparisons, or paper claims.
---

# InodeFence Experiment Validation

실험이 "돌았다"는 것과 **재현 가능한 연구 결과**인 것을 구분한다.

이 skill은 raw output을 논문 근거 또는 finding으로 승격하기 전에 사용한다.

## 1. 실험 단위 식별

각 run에서 다음 정보를 확인한다.

- experiment/run ID
- source revision/commit
- target/extractor
- exact target version
- OS/container/runtime 정보
- architecture
- filesystem/runtime root 조건
- seed corpus/version
- mutation configuration
- RNG seed 또는 재현 가능한 randomness 정보
- timeout/resource limit
- oracle/contract configuration
- 시작/종료 시각 또는 실행 budget

하나라도 결과 해석에 중요하지만 누락되면 limitation으로 기록한다.

## 2. 입력과 산출물 보존

재현에 필요한 것을 구분한다.

```text
configuration
    +
initial seed
    +
mutation/random state
    +
generated archive
    +
target version
    +
observed raw state
    +
oracle result
```

논문용 표/그래프만 남고 raw evidence가 사라지는 구조를 허용하지 않는다.

민감하거나 공개 전인 finding은 `SECURITY.md` 정책을 따른다.

## 3. 결과 계층 분리

항상 다음 네 단계를 분리한다.

### Observed fact
직접 기록된 값.

예:
- 특정 내부 path와 sentinel의 `(st_dev, st_ino)`가 동일했다.
- sentinel hash가 run 전후 달라졌다.

### Derived result
명시적 contract/oracle 규칙으로 계산된 결과.

예:
- C1 violation candidate
- C2 confirmed violation

### Interpretation
왜 그런 결과가 발생했는지에 대한 분석.

예:
- hardlink creation order가 관계 형성에 영향을 준 것으로 보인다.

### Paper claim
반복 실험과 비교군으로 뒷받침된 주장.

예:
- security-state feedback이 baseline보다 특정 class rediscovery 효율을 높였다.

한 단계의 증거로 다음 단계를 자동 확정하지 않는다.

## 4. Known vulnerability rediscovery 검사

Known CVE를 benchmark로 사용할 때 확인한다.

- PoC를 기본 fuzzing seed로 직접 넣지 않았는가?
- CVE 번호/버전이 oracle truth를 결정하지 않는가?
- generic mutation에서 rediscovery가 가능한가?
- 성공 판정은 Security Contract evidence로 이루어지는가?
- root cause와 generated case 사이의 연결을 설명할 수 있는가?

Known PoC를 별도 positive-control experiment로 사용할 수는 있지만 fuzzing rediscovery 결과와 섞지 않는다.

## 5. 비교 실험 검사

baseline과 InodeFence를 비교할 때 가능한 한 다음을 동일하게 유지한다.

- target/version
- execution budget
- initial corpus
- hardware/runtime class
- timeout
- repetition count
- success definition

달라지는 독립 변수는 명확하게 선언한다.

예:

```text
path-only feedback
vs
filesystem-security-state feedback
```

단일 lucky run을 성능 향상으로 주장하지 않는다.

## 6. Reproduction 검사

중요 finding은 최소한 다음을 제공할 수 있어야 한다.

1. clean sandbox 준비
2. exact target 설치/실행
3. archive case 또는 deterministic regeneration
4. extraction 실행
5. pre/post state 관찰
6. contract violation 확인

가능하면 fresh run에서 재현한다.

재현되지 않으면 다음 중 하나로 내린다.

- flaky candidate
- environment-dependent candidate
- invalid finding

## 7. Finding 승격 기준

새로운 취약점 가능성을 주장하기 전에 구분한다.

- crash only
- suspicious filesystem state
- contract violation
- exploitable security impact
- previously unknown vulnerability

뒤 단계일수록 추가 증거가 필요하다.

"새 CVE", "0-day", "취약점 발견" 표현은 단순 oracle hit만으로 사용하지 않는다.

## 8. 논문 준비 상태

paper evidence로 사용할 결과는 최소한 다음에 답해야 한다.

- 어떤 RQ/가설을 검증하는가?
- metric 정의가 무엇인가?
- 비교군은 무엇인가?
- 반복 횟수와 분산은?
- 환경은 재현 가능한가?
- raw result가 보존되어 있는가?
- 실패/timeout도 포함했는가?
- limitation이 무엇인가?

## 9. 최종 판정 형식

결과를 다음 중 하나로 분류한다.

- **RAW ONLY**: 실행 결과는 있으나 검증 부족
- **REPRODUCIBLE**: 같은 조건에서 재현 가능
- **VALIDATED FINDING**: contract evidence와 reproduction 확보
- **PAPER-READY EVIDENCE**: 비교/반복/방법론까지 논문 주장에 사용 가능

등급은 품질 점수가 아니라 현재 증거 단계다.

부족한 항목은 정확히 무엇을 추가하면 다음 단계로 갈 수 있는지 적는다.
