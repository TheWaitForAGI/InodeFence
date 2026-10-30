# 7. Conclusion (드래프트 v1)

InodeFence는 고정된 CVE PoC·공격 recipe 없이 filesystem-security-state(object identity + external
effect)를 feedback으로 쓰는 archive-extraction 탐색 접근을 조사한다. 이 중간 드래프트가 방어하는
것은 좁고 증거로 닿는 네 명제다: (M1) 루프가 실제 node-tar에서 반복 재현되고, (M2) 하나의 generic
identity oracle이 릴리스 id·정답 경로 하드코딩 없이 두 root-cause(CVE-2026-23745와 그 수정이 도입한
회귀 CVE-2026-24842)를 통제 차분으로 포착하며, (M3) object-identity 관찰이 **없으면** 자율 경계위반
발견에 도달하지 못하고 **있으면** 도달한다는 인과를 blind 대조로 보이고, (M4) 동일 generic oracle이
3개 독립 extractor에 oracle/adapter 수준으로 target-agnostic하게 적용된다.

열려 있는 것도 분명히 한다: 상태-인지 feedback의 **rate 우위**(§5.3.3)와 2번째 extractor의 **powered
자력발견 판정**(§5.4.3)은 독립 반복이 끝나야 판정 가능하며 현재 **PENDING**이다. 자율 트리거는
seed-rare이고 blind 발견이 아니며, 참신성은 검증 대상 가설로 둔다. 이 드래프트는 가설의 메커니즘이
실제로 발견을 구동함을 보이는 지점까지의 정직한 보고이고, 효율·일반성의 정량 판정은 후속 PR에서
채운다.
