# 7. Conclusion (드래프트 v1)

## 7.1 현재 방어하는 명제

InodeFence는 CVE 식별자·PoC·고정 공격 패턴·대상 경로·sentinel 이름을 oracle과 feedback에 넣지 않고 filesystem-security-state(object identity + external
effect)를 feedback으로 쓰는 archive-extraction 탐색 접근을 조사한다. 이 드래프트가 방어하는
것은 좁고 증거로 닿는 세 명제다: (M1) 루프가 실제 node-tar에서 반복 재현되고, (M2) 하나의 generic
identity oracle이 릴리스 id·정답 경로 하드코딩 없이 두 root-cause(CVE-2026-23745와 CVE-2026-24842;
CVE 대응과 회귀 원인은 추론)를 통제 차분으로 포착하며, (M4) 동일 generic oracle이
3개 독립 extractor에 oracle/adapter 수준으로 target-agnostic하게 적용된다.

## 7.2 핵심 RQ 판정: 본실험 결과 자리 (봉인 해제 뒤 기입)

EXP-3 train은 끝났고 GO 판정(2026-11-13)을 거쳐 EXP-2 holdout이 실행 중이다. 판정 규칙과 결론 문장은 동결 등록
파일(`experiments/preregistration/exp3-v1.md`·`exp2-v1.md`)을 따르며, 단계 B에서 그 파일을 가리켜 다시 쓴다.
결과를 본 뒤 규칙을 바꾸지 않는다.
