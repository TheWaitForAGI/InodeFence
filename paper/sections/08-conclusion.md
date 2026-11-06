# 7. Conclusion (드래프트 v1)

InodeFence는 고정된 CVE PoC·공격 recipe 없이 filesystem-security-state(object identity + external
effect)를 feedback으로 쓰는 archive-extraction 탐색 접근을 조사한다. 이 중간 드래프트가 방어하는
것은 좁고 증거로 닿는 네 명제다: (M1) 루프가 실제 node-tar에서 반복 재현되고, (M2) 하나의 generic
identity oracle이 릴리스 id·정답 경로 하드코딩 없이 두 root-cause(CVE-2026-23745와 그 수정이 도입한
회귀 CVE-2026-24842)를 통제 차분으로 포착하며, (M3) 외부 객체 이름을 어휘에 획득한 조건에서만 자율 경계위반이
관찰됨을 blind 대조(어휘 통제)로 보이고(retention·effect 피드백 자체의 인과는 미입증) *(구: "관찰이 없으면 도달 못하고 있으면 도달한다는 인과를 보이고", 2026-11-03 정정)*, (M4) 동일 generic oracle이
3개 독립 extractor에 oracle/adapter 수준으로 target-agnostic하게 적용된다.

(2026-11-03 정정: 이 blind 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 입증된 것은 "외부 객체 이름의 관찰(어휘 획득)이 자율 C1의 필요조건"이지 (st_dev, st_ino) retention·스케줄링 피드백의 기여가 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.)

판정한 것도 분명히 한다: 상태-인지 feedback의 **rate 우위**(§5.3.3)와 2·3번째 extractor의 **powered
자력발견**(§5.4.3–5.4.4)은 사전등록 후 판정했고 **모두 효과 우위를 보이지 않았다** — rate는 매칭
Wilson CI가 겹쳐 미분리(단 신규 seed s101로 메커니즘이 멀티-seed로 강화), decompress·oras-go
자력발견은 각각 사후 분석 기준 음성(사전등록 판정 아님)·약한 음성이다. blind 발견이 아니며, 참신성은 검증 대상 가설로 둔다. 이
드래프트는 외부 객체 이름을 어휘에 획득한 조건에서 자율 트리거가 **관찰됨**을 보이되, 그 피드백 자체의 인과 기여와
효율·발견 effectiveness는 이 예산에서는 입증되지 않았다는 정직한 보고다 *(구: "메커니즘이 실제로 발견을 구동함을 보이되", 2026-11-03 정정; 피드백 인과는 R/D/S-u로 미분리)*.


**(EXP-3 결과 반영 — TBD.)** 위 네 명제는 중간 상태다. 결과별 판정 문장 틀은 #265 §7.2를 참조한다.
