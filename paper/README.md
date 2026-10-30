# 논문용 자료

## 이 폴더는 무엇인가

검토를 거쳐 실제 논문에 사용할 글·그림·표를 둔다.

## 입력

출처가 확인된 문헌, 재현된 실험과 검토된 분석.

## 출력

논문 section, figure, table(계획).

## 책임

예: 성능 표의 값이 어떤 experiment 설정과 raw 결과에서 왔는지 연결한다.

## 하지 않는 것

연구 메모나 예상 성능을 측정된 결과로 표현하기.

## 다른 모듈과의 연결

설계 근거는 [research](../docs/research/README.md), 수치 근거는 [experiments](../experiments/README.md), 재현 증거는 [findings](../findings/README.md)에 둔다.

## 현재 상태

조립본 드래프트 v1이 있다. 읽는 순서·상태 범례는 [sections/00-outline.md](sections/00-outline.md)를
본다. 드래프트는 방어 가능한 좁은 주장(M1 동작·M2 통제 재현·M3 메커니즘 인과·M4 oracle/adapter
일반성)만 적고, **effectiveness/성능 우위(rate)는 주장하지 않는다**(PENDING으로 열어 둠). 능력
판정의 단일 기준은 [Capability Ledger](../docs/STATUS.md)이고, 주장↔증거 매핑은
[sections/claims-evidence-status-v1.md](sections/claims-evidence-status-v1.md)다.

## 파일 배치 규칙

본문은 sections/, 그림은 figures/, 표는 tables/에 둔다. 각 주장·수치는 출처와 실험 설정에 추적 가능해야 한다.
