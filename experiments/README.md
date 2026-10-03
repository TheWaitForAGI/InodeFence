# 실험 설정과 raw 결과

## 이 폴더는 무엇인가

재현 가능한 실험 설정과 가공 전 실행 기록을 보관한다.

## 입력

고정한 seed/config, target 버전, 환경과 엔진 실행 기록(계획).

## 출력

비교·분석 가능한 raw 결과와 재현 설정(계획).

## 책임

예: baseline과 feedback 사용 실험이 어떤 설정으로 실행됐는지 기록한다.

## 하지 않는 것

raw 결과를 검토 없이 논문 결론으로 승격하기, source mount에서 filesystem 실험하기.

## 다른 모듈과의 연결

[엔진](../src/inodefence/README.md)을 실행할 설정을 제공하며 확인한 증거는 [findings](../findings/README.md), 검토된 분석은 [paper](../paper/README.md)로 연결한다.

## 현재 상태

configs/와 raw/에는 .gitkeep만 있다. 실험 실행기와 결과는 없다.

## 파일 배치 규칙

설정은 configs/, raw 기록은 raw/에 둔다. raw/*와 results/는 Git ignore 대상이므로 결과 보존·공유 경로를 명시한다. 설정에 seed, 환경, target 버전과 결과 식별자를 남긴다.
