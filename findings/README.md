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

private/와 published/ 보관 경로만 있다. finding은 아직 없다.

## 파일 배치 규칙

finding별로 입력·환경·근거·재현 방법과 후보/확인 상태를 묶는다.

- `private/`: 아직 공개하면 안 되는 finding. 내용은 Git ignore하고 `.gitkeep`만 추적한다.
- [published/](published/README.md): 공개 결정이 끝난 sanitized/reproducible finding만 추적한다.

공개 운영은 [SECURITY.md](../SECURITY.md)를 따른다. private 데이터의 접근 통제와
보존·공유 경로는 별도로 관리한다.
