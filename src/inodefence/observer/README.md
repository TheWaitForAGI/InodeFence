# filesystem 사실 관찰

## 이 폴더는 무엇인가

실행 전후 filesystem 상태를 snapshot으로 기록한다.

## 입력

run sandbox, 관찰 대상과 보호 sentinel 설정, 실행 기록(계획).

## 출력

ObjectSnapshot / StateSnapshot(계획).

## 책임

예: 두 경로의 (st_dev, st_ino)가 같다는 사실과 sentinel hash의 전후 값을 기록한다.

## 하지 않는 것

취약 여부 판정, mutation, extractor 실행.

## 다른 모듈과의 연결

[targets](../targets/README.md) 실행 전후에 관찰하고 snapshot을 [oracle](../oracle/README.md)과 [feedback](../feedback/README.md)에 전달한다.

## 현재 상태

빈 __init__.py만 있다. 초기 설계는 pre/post snapshot이며 full operation trace는 없다.

## 파일 배치 규칙

filesystem 정보 수집을 둔다. C0~C4 판정이나 CVE 조건을 넣지 않는다. 관찰 한계는 [architecture](../../../docs/research/design/architecture.md)에 명시한다.
