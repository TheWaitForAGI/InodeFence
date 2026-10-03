# InodeFence 엔진 모듈

## 이 폴더는 무엇인가

TAR 입력을 만들고 extractor 실행 결과를 관찰·판정·선택할 엔진의 위치다. 상세 구조와 데이터 흐름은 [architecture](../../docs/research/design/architecture.md)가 canonical source다.

## 입력

초기 case 설정, 기존 corpus 입력, target 및 sandbox 설정(계획).

## 출력

case, 실행 기록, snapshot, 계약 판정, corpus 선택 결과(계획).

## 책임

각 모듈은 아래 한 가지 책임을 맡는다. 예를 들어 “두 path의 identity가 같다”는 Observer의 사실이고, “보호 대상과의 공유가 계약을 위반한다”는 Oracle의 판정이다.

| 폴더 | 책임 |
| --- | --- |
| [model](model/README.md) | 공통 입력과 결과 표현 |
| [generator](generator/README.md) | 초기 archive case 생성 |
| [mutator](mutator/README.md) | 기존 case 구조 변경 |
| [targets](targets/README.md) | 실제 extractor 실행 |
| [observer](observer/README.md) | filesystem 상태 관찰 |
| [oracle](oracle/README.md) | Security Contract 위반 판정 |
| [feedback](feedback/README.md) | interesting state 판정 및 corpus 관리 |

TAR Builder는 별도 직렬화 책임이며 파일 위치는 아직 미확정이다.

## 하지 않는 것

Observer의 취약 판정, Oracle의 filesystem 실행·mutation, Feedback의 계약 정의, generic 모듈의 target-specific 처리.

## 다른 모듈과의 연결

[tests](../../tests/README.md)는 구현을 검증하고 [experiments](../../experiments/README.md)는 실험 설정과 결과를 관리한다. 보존할 증거는 [findings](../../findings/README.md)와 [artifacts](../../artifacts/README.md)에 연결한다.

## 현재 상태

model/에는 ArchiveEntry, ArchiveCase와 EntryType이 구현되어 있고 다른 엔진 하위 패키지는 빈 __init__.py만 있다. 동작하는 pipeline이나 공개 실행 API는 없으며 [STATUS](../../docs/STATUS.md)의 공통 Data Model은 진행 중이다.

## 파일 배치 규칙

변경할 책임의 하위 폴더에 코드를 둔다. 새로운 공통 interface는 관련 design 문서와 함께 설명하고, 조율 코드나 Builder 위치는 구현 단계에서 합의한다. 연구 문서나 runtime 결과를 Python 패키지에 넣지 않는다.
