# Security Contract 판정

## 입력과 출력

`evaluate_contracts(before, after) -> tuple[ViolationResult, ...]`

[구현](contracts.py)은 같은 run의 snapshot을 비교하며 초기 보호 sentinel의 존재를 요구한다. Runner가 archive case와 execution provenance를 결과에 함께 보존한다. Oracle은 archive spelling이나 exit status로 verdict를 결정하지 않으며 reject/failure 뒤에도 같은 기준을 적용한다.

정확한 계약과 관찰 한계는 [security-contracts](../../../docs/research/design/security-contracts.md)가 canonical source다.

| 계약 | 현재 evidence |
| --- | --- |
| C0 | external namespace path의 생성·삭제·identity/type 교체 |
| C1 | extraction object와 지정 sentinel의 post-state lstat identity 공유 |
| C2 | 지정 sentinel의 존재·내용·identity·선택 metadata 전후 변화 |

C0는 content effect만으로 external path의 직접 사용을 추정하지 않는다. C1 초기 정책은 cross-boundary identity 공유를 허용하지 않으며 runner는 빈 extraction root에서 시작한다. C2는 atime을 제외한다.

Evidence는 StateChange의 전후 observation 또는 IdentityEvidence의 경로/identity 관계다. `violated=False`는 관찰 범위 내 증거 부재이며 모든 실행의 안전성 증명이 아니다. 각 verdict에 limitations를 기록한다. 결과는 vulnerability 확정이 아닌 재현·원인 분석 대상 contract candidate다.

## 하지 않는 것

Filesystem read/write, target 실행, mutation, signature/interestingness 결정, CVE 문자열/버전 판정. C3/C4와 full operation tracing은 후속 작업이다.
