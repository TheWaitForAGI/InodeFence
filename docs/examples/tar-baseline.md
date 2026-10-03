# TAR baseline fixture와 수동 filesystem probe

이 예제는 Layer 2 Data Model과 pipeline을 구현하기 전에 TAR entry와 실제 Linux
filesystem 상태를 사람이 비교하는 기초 실험이다. 취약점 발견이나 fuzzing 성능을
평가하는 실험이 아니다. Python 표준 라이브러리 `tarfile`로 만든 4개 fixture를
같은 라이브러리로 풀고 관찰한다.

## 실행

저장소 루트에서 Linux Dev Container의 Python 3.12로 실행한다.

```bash
python scripts/check_dev_env.py
python scripts/generate_tar_fixtures.py

python scripts/manual_tar_probe.py tests/fixtures/tar/regular-file/fixture.tar
python scripts/manual_tar_probe.py tests/fixtures/tar/directory/fixture.tar
python scripts/manual_tar_probe.py tests/fixtures/tar/hardlink/fixture.tar
python scripts/manual_tar_probe.py tests/fixtures/tar/symlink/fixture.tar

python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Fixture TAR는 소스에 보관하지만 extraction은 `/var/lib/inodefence` 안의 매번 새로운
임시 sandbox에서 수행한다. `INODEFENCE_RUNTIME_ROOT`를 지정하면 이 경로 안에 있는
기존 디렉터리만 허용한다. Probe와 테스트 모두 같은 sandbox 생성 함수를 사용하며,
관찰이나 예외 처리 후 자신이 만든 sandbox를 삭제한다. 출력의 extraction 경로는
명령 종료 후 남지 않는다.

## 네 가지 testcase

각 디렉터리의 `fixture.tar`가 하나의 testcase다. 모든 regular file의 내용은
`hello inodefence`이며 끝에 줄바꿈 없이 정확히 16 bytes다.

| Fixture 디렉터리 | TAR entry 순서 | 확인할 filesystem 상태 |
| --- | --- | --- |
| `tests/fixtures/tar/regular-file/` | regular `a.txt` | 내용 16 bytes, regular file |
| `tests/fixtures/tar/directory/` | directory `dir/`, regular `dir/a.txt` | 디렉터리와 그 안의 파일 |
| `tests/fixtures/tar/hardlink/` | regular `a.txt`, hardlink `b.txt` → `a.txt` | 두 경로의 `(st_dev, st_ino)` 동일, `st_nlink >= 2` |
| `tests/fixtures/tar/symlink/` | regular `a.txt`, symlink `b.txt` → `a.txt` | `b.txt` 자체는 symlink, `readlink(b.txt) == "a.txt"` |

### Regular file

내용을 저장하는 일반 파일이다. `a.txt`라는 디렉터리 entry가 inode를 가리키고,
inode에는 파일의 크기, 권한, link count 등의 metadata가 있다.

### Directory entry

TAR의 directory entry는 extractor에게 디렉터리를 만들도록 지시한다. 이 fixture는
`dir/`를 명시적으로 먼저 기록하고 그 안에 `dir/a.txt`를 기록한다. 디렉터리 자체도
inode와 metadata를 가지며, 크기와 link count는 filesystem 구현에 따라 달라질 수 있다.

### Hardlink

기존 regular file과 같은 filesystem object를 가리키는 또 하나의 이름이다.
TAR에는 link target `a.txt`가 기록되지만 extraction 이후 `b.txt`가 별도의 path 문자열을
저장하는 symlink가 되는 것은 아니다. 두 경로 모두 regular file로 보인다.

```text
a.txt ─┐
       ├─ 같은 device의 같은 inode (st_nlink = 2)
b.txt ─┘
```

이 baseline에서는 두 이름만 있어 `st_nlink`가 2다. Object identity는 inode 번호만이
아니라 `(st_dev, st_ino)` 쌍으로 비교한다. Inode 번호는 실행마다 달라질 수 있어
특정 숫자를 기대값으로 쓰지 않는다.

### Symlink

다른 경로를 가리키는 문자열을 저장하는 별도 object다. 상대 target `a.txt`는
symlink가 있는 디렉터리를 기준으로 해석된다.

```text
b.txt (symlink 자체의 inode)
  ↓
"a.txt"라는 path 문자열
  ↓
a.txt (regular file의 inode)
```

`lstat(b.txt)`는 symlink 자체를 관찰하고 `stat(b.txt)`는 target을 따라간다.
이 fixture에서 symlink 자체의 크기는 target 문자열 `a.txt`의 길이인 5 bytes다.
Target의 내용은 16 bytes이며 symlink를 추가해도 target의 hardlink count는 증가하지 않는다.

## Probe 출력 읽기

출력은 상대 경로 순서로 정렬되며 다음 값을 표시한다.

| 필드 | 의미 |
| --- | --- |
| `path` | Extraction root 기준 상대 경로 |
| `type` | `lstat()`으로 본 `regular`, `directory`, `symlink` 등의 종류 |
| `st_dev` | Filesystem device 식별자 |
| `st_ino` | 해당 device 안에서의 inode 번호 |
| `st_nlink` | 해당 object의 hardlink count |
| `mode` | Permission/special bits를 8진수로 표시 |
| `size` | `lstat().st_size`; symlink는 target 문자열의 길이 |
| `symlink_target` | `readlink()` 결과; symlink가 아니면 `-` |
| `same_object_as` | 앞서 출력한 regular file 중 같은 `(st_dev, st_ino)`를 가진 경로, 없으면 `-` |

Hardlink fixture에서 `a.txt`와 `b.txt`의 `type`은 모두 `regular`이고 device와 inode가
같다. `b.txt`에는 `same_object_as: a.txt`가 표시된다. Symlink fixture에서는 `b.txt`의
`type`이 `symlink`이고 `symlink_target: a.txt`가 표시된다. Probe는 symlink를 따라
디렉터리를 탐색하지 않는다.

## 재현성과 범위

생성기는 source file의 현재 시간이나 소유자를 읽지 않고 `TarInfo`로 entry를 만든다.
USTAR format, entry 순서, 내용, mode를 고정하며 `mtime`, `uid`, `gid`는 0,
`uname`, `gname`은 빈 문자열이다. Regular/hardlink mode는 `0644`, directory는 `0755`,
symlink header는 `0777`이다. 테스트는 재생성한 TAR를 다시 생성한 결과 및 저장된
fixture와 byte 단위로 비교한다. Filesystem의 실제 inode/device 값과 디렉터리 크기까지
고정되는 것은 아니다.

Extraction은 Python 3.12 `tarfile.extractall(filter="data")`를 사용한다. 이 filter는
extraction root 밖으로 향하는 entry/link와 특수 파일을 제한하고 일부 metadata를 조정한다.
출력은 archive header 대신 extraction 후 실제 상태를 보여준다. 이 도구는 작은
신뢰된 baseline fixture를 위한 것이며 임의의 비신뢰 TAR에 대한 resource 제한이나
격리 harness를 제공하지 않는다. 다른 extractor의 결과를 일반화하지 않는다.

앞으로 `ArchiveCase` → TAR Builder → Target Adapter → State Observer를 구현할 때
이 fixture의 entry 구조와 관찰 결과를 기준으로 비교할 수 있다. 이번 작업은
`src/inodefence/`의 architecture를 변경하거나 공통 data model, StateObserver,
security oracle, mutation/feedback algorithm, fuzzing loop, CVE payload, node-tar
취약점 재현을 구현하지 않는다.
