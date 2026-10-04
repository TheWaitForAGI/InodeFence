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

Dev Container는 Linux toolchain/filesystem semantics 개발환경이며 hostile target sandbox가 아니다.
저장소는 writable bind mount이고 runtime/Codex 등 configured volumes와 network 및 같은 user의
파일 접근이 남는다. Runtime TemporaryDirectory는 cleanup boundary다. CI도 extraction별 mount,
credential/network/resource boundary를 제공하지 않는다. Generated third-party target campaign에는
별도 검증된 execution isolation이 필요하며 현재 campaign entry가 이를 거부한다.

Dockerfile과 devcontainer.json이 구현되어 있다. Node 22.22.0과 locked node-tar 7.5.22 정상 fixture dependency를 준비한다. oras-go는 미구현이다.

## 파일 배치 규칙

이미지 구성은 Dockerfile, mount·에디터·초기 설치 설정은 devcontainer.json에 둔다. 실험 데이터는 이 폴더에 두지 않는다.

## Codex CLI 업데이트 정책

Codex CLI는 팀의 바이브코딩 생산성을 위한 개발 도구이며, 빠르게 개선되는 특성을
고려해 exact version으로 고정하지 않고 rolling latest로 운영한다.

Dev Container 생성 시 post-create.sh에서 최신 버전을 설치한다.

```bash
npm install --global @openai/codex@latest
```

기존 Dev Container를 사용하는 팀원도 필요할 때 다음 명령으로 업데이트하고 버전을
확인할 수 있다. Codex 업데이트가 나오면 최신 버전 사용을 우선한다.

```bash
npm install --global @openai/codex@latest
codex --version
```

Codex CLI 버전은 formal experiment reproducibility 기준에 포함하지 않는다.
실험 재현성은 다음을 기준으로 관리한다.

- InodeFence Git commit
- target 및 target version
- Python/runtime
- experiment config
- random seed
- execution budget
- OS / architecture 및 실험에 실제 영향을 주는 runtime dependency version
