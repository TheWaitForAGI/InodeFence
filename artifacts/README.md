# 생성물 보관

## 이 폴더는 무엇인가

의도적으로 남길 생성 파일의 보관 위치다.

## 입력

향후 생성한 TAR 또는 분석·검토용 파일.

## 출력

원래 case/config와 연결할 수 있는 생성물.

## 책임

예: TAR 파일에 해당 case와 실험 기록 식별자를 연결한다.

## 하지 않는 것

filesystem 실행 sandbox, canonical 설계 문서, 영구 corpus 위치의 확정.

## 다른 모듈과의 연결

[experiments](../experiments/README.md)와 [findings](../findings/README.md)의 기록에서 생성물 출처를 연결한다. 실행 공간 규칙은 [architecture](../docs/research/design/architecture.md)를 따른다.

## 현재 상태

`overnight-n05-track-a-20261023/`에는 2026-10-23 통합 감사의 작은 inventory와
target-free 검증 로그를 의도적으로 보존한다. 출처와 실행 한계는
[인수인계 보고서](../docs/research/diagnostics/n05-track-a-overnight-integration-2026-10-23.md)를 따른다.

`linux-integration-validation-20261023/`에는 같은 통합 코드 SHA의 Linux 공학 검증 명령,
원본 로그의 무손실 gzip, JUnit, 실패 분석 및 source bundle을 보존한다. 정확한 revision,
설정 변경 전후 결과와 실행 gate는
[Linux 검증 보고서](../docs/research/diagnostics/n05-track-a-linux-integration-validation-2026-10-23.md)를 따른다.
이 자료는 N05 승인이나 Track A 실험 결과가 아니다.

## 파일 배치 규칙

생성물에 출처와 재생성 방법을 연결한다. README와 .gitkeep 외 파일은 기본적으로 Git ignore
대상이다. 위 감사·검증 파일만 명시적으로 보존하며 대용량 파일을 자동으로 Git에 추가하지 않는다.
