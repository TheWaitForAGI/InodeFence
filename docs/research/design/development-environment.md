# 개발 환경

## 목표

InodeFence는 다음 두 환경에서 동일한 저장소와 Dev Container를 이용해 개발할 수 있어야 한다.

- macOS
- Windows + WSL2

Host 환경 자체를 canonical filesystem-semantics 환경으로 간주하지 않는다.

## 기준 Container

현재 기준:

- Ubuntu 24.04
- Python 3.12
- pytest
- Ruff
- tar / gzip / xz
- jq
- strace

가상환경:

```text
/opt/venv
```

저장소 mount 경로:

```text
/workspaces/InodeFence
```

## Runtime Filesystem

Filesystem-security 실험은 다음 경로를 사용한다.

```text
/var/lib/inodefence
```

이 경로는 source-code bind mount가 아니라 Docker volume으로 제공된다.

이유:

InodeFence는 hardlink, symlink, inode, filesystem side effect를 연구한다. macOS와 WSL host의 공유 폴더는 filesystem semantics가 달라질 수 있기 때문에 소스 디렉터리와 실험 디렉터리를 분리한다.

## 검증한 Host

### macOS

검증 조건:

- ARM64 host
- OrbStack Docker engine
- Ubuntu 24.04 Dev Container
- Python 3.12.3
- hardlink/symlink가 정상 동작하는 Linux volume

### Windows / WSL2

검증 조건:

- x86_64 WSL2 host
- Ubuntu 24.04 Dev Container
- Python 3.12.3
- Linux ext4-backed runtime volume
- hardlink/symlink 정상 동작

개발 중 CPU architecture와 backing filesystem은 host에 따라 달라질 수 있다.

서로 다른 개발 host에서 나온 결과를 하나의 정식 논문 evaluation dataset으로 섞지 않는다.

## 환경 확인

Dev Container 내부:

```bash
python scripts/check_dev_env.py
```

확인 항목:

- Python 3.12
- runtime root 존재 여부
- hardlink identity
- symlink 동작
- shared-object write effect

이후:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

## 줄바꿈

저장소의 텍스트 파일은 LF를 사용한다.

다음으로 강제한다.

- `.gitattributes`
- `.editorconfig`
- Ruff formatting 설정

확인이 필요할 때:

```bash
git ls-files --eol
```

내용이 있는 일반 텍스트 파일은 보통 다음처럼 보여야 한다.

```text
i/lf w/lf
```

## WSL 저장소 위치

저장소는 WSL Linux filesystem 안에 둔다.

예:

```text
~/Projects/InodeFence
```

Filesystem-sensitive 개발에서 `/mnt/c/...` 아래를 기본 프로젝트 경로로 사용하지 않는다.

## 정식 Evaluation

최종 논문 실험에서는 하나의 canonical evaluation environment를 고정한다.

최소 기록 항목:

- OS version
- CPU architecture
- filesystem
- container/runtime setup
- Python version
- target version
- experiment configuration

개발의 이식성과 논문 실험의 재현성은 서로 다른 요구사항으로 관리한다.
