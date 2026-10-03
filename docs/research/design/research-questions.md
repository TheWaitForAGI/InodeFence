# 연구 질문과 가설

## RQ1 — Known Vulnerability Rediscovery

InodeFence는 해당 CVE PoC를 seed로 직접 제공하지 않고도 알려진 TAR extraction link/path 보안 위반을 재발견할 수 있는가?

후보 benchmark:

- node-tar CVE-2026-23745
- node-tar CVE-2026-24842
- node-tar CVE-2026-26960
- oras-go CVE-2026-50163
- GNU tar CVE-2026-18508 (선택)

최종 평가 전에 정확한 benchmark와 target version을 고정한다.

## RQ2 — Feedback Effectiveness

Filesystem-security-state feedback은 다음 baseline과 비교했을 때 발견 효율을 높이는가?

- random mutation
- path-only feedback
- fixed attack strategy

주요 측정 지표:

- Detection Rate
- Time to First Violation
- Executions to First Violation
- Unique Security States

## RQ3 — Feedback Ablation

State representation의 어떤 요소가 실제 탐색에 기여하는가?

후보 구성:

- F0: path only
- F1: path + object type
- F2: path + object identity / link relation
- F3: identity + external effect
- Full state

최종 실험 전에 정확한 State Signature 정의를 고정한다.

## RQ4 — Cross-Implementation Generality

동일한 security-state representation과 generic oracle logic을 여러 TAR extractor에 적용할 수 있는가?

초기 target 순서:

1. node-tar
2. oras-go
3. 일정이 허용하면 GNU tar

## RQ5 — Unknown-State Discovery

동일한 framework를 patched/current target version에 적용했을 때 기존에 정의하지 않은 security-contract violation을 발견할 수 있는가?

이 RQ는 탐색적이다. Zero-day 발견은 프로젝트 성공의 필수조건이 아니다.

## H1 — State-Guided Search

동일한 execution/time budget에서 object-identity와 external-effect feedback을 사용하는 corpus-guided fuzzer가 fixed attack-recipe 방식이나 더 약한 feedback baseline보다 archive-extraction boundary violation을 더 효과적으로 탐색할 것이다.

이는 **검증할 가설**이며, 아직 결과가 아니다.

## H2 — Generic Security Contract

특정 CVE 문자열이나 코드 경로를 encoding하지 않는 일반화된 security contract가 여러 TAR extractor의 유사한 보안 실패를 판정할 수 있을 것이다.

이 역시 실험 가설이다.

## Evaluation 원칙

실험은 가능한 한 다음 조건을 맞춘다.

- 동일 initial corpus
- feedback baseline 간 가능한 동일 mutation operator
- 고정된 target version
- 동일 time/execution budget
- 반복 실행
- 재현 가능한 random seed 또는 기록된 RNG seed

최소 보고 항목:

- median
- IQR 등 분산/범위
- success rate
- 정확한 target/environment configuration

실험으로 확인되기 전에는 예상 순서를 실제 결과처럼 표현하지 않는다.
