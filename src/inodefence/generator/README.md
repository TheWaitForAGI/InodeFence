# 초기 case 생성

## 책임

작고 설명 가능한 초기 ArchiveCase를 생성하는 정책을 둔다. 기존 case mutation, TAR encoding, extractor 실행이나 CVE recipe를 소유하지 않는다.

## 현재 상태

Generic generator는 아직 미구현이다. 작은 4종 baseline case는 개발용 [fixture script](../../../scripts/generate_tar_fixtures.py)의 `baseline_case`에 있다. Script는 공통 [model](../model/README.md)과 [builder.py](../builder.py)를 사용하므로 TAR encoding을 중복하지 않는다.

후속 generator는 ArchiveCase를 반환하고 [mutator](../mutator/README.md)에 연결한다. 직렬화 정책은 builder에 둔다. 책임 기준은 [architecture](../../../docs/research/design/architecture.md)다.
