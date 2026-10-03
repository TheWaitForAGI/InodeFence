# 재현 가능한 finding

## 이 폴더는 무엇인가

관찰된 위반 후보와 재현·검토 증거를 의도적으로 보존한다.

## 입력

case, target 버전, 설정, snapshot과 oracle 근거(계획).

## 출력

재현 가능한 후보 또는 확인된 위반 기록(계획).

## 책임

예: C1 후보의 두 object identity와 재실행 결과를 함께 기록한다.

## 하지 않는 것

모든 interesting state를 confirmed vulnerability라고 부르기, corpus 전체 저장.

## 다른 모듈과의 연결

원인 분석은 [cve-analysis](../docs/research/cve-analysis/README.md), 실험 설정과 raw 기록은 [experiments](../experiments/README.md), 검토된 주장은 [paper](../paper/README.md)에 연결한다.

## 현재 상태

.gitkeep과 이 안내만 있다. finding은 아직 없다.

## 파일 배치 규칙

finding별로 입력·환경·근거·재현 방법과 후보/확인 상태를 묶는다. README와 .gitkeep 외 파일은 Git ignore 대상이므로 공유할 증거는 별도로 명시한다.
