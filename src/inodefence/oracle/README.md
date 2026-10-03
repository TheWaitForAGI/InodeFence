# Security Contract 판정

## 입력과 출력

`evaluate_contracts(before, after) -> tuple[ViolationResult, ...]`

[구현](contracts.py)은 같은 run의 snapshot을 비교하며 초기 보호 sentinel의 존재를 요구한다. Runner가 archive case와 execution provenance를 결과에 함께 보존한다. Oracle은 archive spelling이나 exit status로 verdict를 결정하지 않으며 reject/failure 뒤에도 같은 기준을 적용한다.

정확한 계약과 관찰 한계는 [security-contracts](../../../docs/research/design/security-contracts.md)가 canonical source다.

| 계약 | 현재 evidence |
| --- | --- |
| C0 | HARNESS 포함 extraction root 밖 path의 생성·삭제·identity/type 교체 |
| C1 | extraction object와 지정 sentinel의 post-state lstat identity 공유 |
| C2 | 지정 sentinel의 존재·내용·identity·선택 metadata 전후 변화 |

C0는 model의 `is_extraction_path` membership과 Oracle의 `_is_c0_namespace_transition` 정책을 사용한다. Region.HARNESS는 security trust boundary가 아니므로 `archive/escaped.txt` 생성과 input.tar 삭제·identity/type 교체도 evidence다. Root-level `escape.txt`와 outside namespace도 계속 포함한다. Content/metadata-only effect는 C0에서 제외하며 직접 외부 path 사용을 추정하지 않는다. C1 초기 정책은 cross-boundary identity 공유를 허용하지 않으며 runner는 빈 extraction root에서 시작한다. C2는 atime을 제외하고 raw nlink·timestamp를 포함한 기존 metadata 비교를 유지한다.

정상 harness setup은 BEFORE baseline에 이미 포함되어 C0가 아니다. BEFORE→target.run→AFTER 관찰 구간에는 harness namespace write가 없어야 한다. Adapter diagnostics는 ExecutionResult로 반환하고 setup/bookkeeping은 구간 밖에 둔다. Snapshot은 actor를 알 수 없으므로 이 계약을 어긴 bookkeeping은 false positive가 될 수 있으며 HARNESS exemption으로 숨기지 않는다. 이 attribution 전제를 C0 limitations에 기록한다. Transient operation/direct path use/sandbox 밖 접근은 여전히 snapshot만으로 완전히 판정하지 못한다.

Oracle은 full raw evidence인 StateSnapshot을 사용한다. Feedback용 normalized security-state representation인 StateSignature의 HARNESS 제외/nonregular nlink normalization이 C1/C2 evidence를 줄이지 않는다. Signature는 ArchiveCase/TAR artifact identity를 직접 포함하지 않는다.

Evidence는 StateChange의 전후 observation 또는 IdentityEvidence의 경로/identity 관계다. `violated=False`는 관찰 범위 내 증거 부재이며 모든 실행의 안전성 증명이 아니다. 각 verdict에 limitations를 기록한다. 결과는 vulnerability 확정이 아닌 재현·원인 분석 대상 contract candidate다.

## 하지 않는 것

Filesystem read/write, target 실행, mutation, signature/interestingness 결정, CVE 문자열/버전 판정. C3/C4와 full operation tracing은 후속 작업이다.
