# 개발 보조 명령

## 이 폴더는 무엇인가

개발환경 확인 등 저장소 작업을 보조하는 명령을 둔다.

## 입력

현재 스크립트는 Python 환경과 INODEFENCE_RUNTIME_ROOT를 읽는다.

## 출력

환경 정보와 검사 성공 또는 실패.

## 책임

check_dev_env.py는 임시 sandbox에서 hardlink identity, symlink, 공유 object write effect를 확인한다.

## 하지 않는 것

퍼저 구현, 실제 host 민감 파일을 대상으로 한 실험.

## 다른 모듈과의 연결

[Dev Container](../.devcontainer/README.md) 안에서 python scripts/check_dev_env.py로 실행한다. 환경 기준은 [환경 설계](../docs/research/design/development-environment.md)를 따른다.

## 현재 상태

check_dev_env.py만 있다. 실험 실행 CLI는 없다.

## 파일 배치 규칙

사용 목적을 알 수 있는 스크립트명과 입력 설정을 남긴다. 공통 엔진 로직은 src에 두고 raw output은 실험 기록으로 관리한다.
