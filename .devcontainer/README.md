# 개발환경

## 이 폴더는 무엇인가

Ubuntu 24.04와 Python 3.12 기반 Linux 개발환경을 정의한다.

## 입력

Dockerfile과 devcontainer.json, host의 저장소 소스.

## 출력

/opt/venv 개발환경과 /var/lib/inodefence runtime volume.

## 책임

동일한 도구와 Linux filesystem 실험 공간을 제공한다. 소스는 /workspaces/InodeFence에 mount한다.

## 하지 않는 것

fuzzing pipeline 구현이나 정식 evaluation 환경의 자동 확정.

## 다른 모듈과의 연결

[환경 설계](../docs/research/design/development-environment.md)와 [환경 검사](../scripts/README.md).

## 현재 상태

Dockerfile과 devcontainer.json이 구현되어 있다. node-tar/ oras-go adapter 설치는 구현되어 있지 않다.

## 파일 배치 규칙

이미지 구성은 Dockerfile, mount·에디터·초기 설치 설정은 devcontainer.json에 둔다. 실험 데이터는 이 폴더에 두지 않는다.

## Codex 버전 정책

팀이 Dev Container에서 실제로 정상 사용 중인 `codex --version`을 확인한 뒤
post-create.sh의 설치 버전을 exact version으로 pin한다. 버전을 추측하지 않는다.
이번 점검의 실행 중인 컨테이너에는 Codex CLI가 없어 기존 `@latest`를 유지한다.
설치 후 정상 동작을 확인한 팀 버전으로 고정하는 후속 작업이 필요하다.
