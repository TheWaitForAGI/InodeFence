# 공통 데이터 모델

## 이 폴더는 무엇인가

모듈이 주고받을 case와 결과의 표현을 위한 위치다.

## 입력

entry의 경로·종류·내용·link target과 순서, 프로세스 실행 결과 값,
filesystem object의 관찰 결과 값과 extractor 실행 전후의 관찰 시점.

## 출력

`ArchiveEntry`, `ArchiveCase`로 표현한 논리 archive 구조, `ExecutionResult`로 표현한
프로세스 실행 결과, `ObjectSnapshot`으로 표현한 filesystem object의 관찰 사실과
`StateSnapshot`으로 묶은 특정 시점의 sandbox 상태.

## 책임

예: notes.txt 파일 entry의 경로와 내용을 실행 없이 표현한다.

구현은 [archive.py](archive.py), [execution.py](execution.py), [filesystem.py](filesystem.py)에
있으며 `inodefence.model`에서 import할 수 있다. 다섯 모델은 `frozen=True` dataclass다.

| 모델 | 실제 필드 | 의미 |
| --- | --- | --- |
| `ArchiveEntry` | `path: str` | archive 내부 경로 문자열을 입력 그대로 보존 |
| | `entry_type: EntryType` | `REGULAR`, `DIRECTORY`, `HARDLINK`, `SYMLINK` Enum |
| | `content: bytes = b""` | regular file의 내용; 기본값은 빈 bytes |
| | `link_target: str \| None = None` | hardlink/symlink의 target 문자열; 다른 종류는 기본값 `None` |
| `ArchiveCase` | `entries: tuple[ArchiveEntry, ...]` | archive 순서의 entry tuple; 중복 경로와 빈 tuple도 표현 가능 |

directory와 link는 기본 `content=b""`로 표현한다. 생성자는 필드 조합이나
경로의 안전성을 검증하지 않는다. `path`와 `link_target`의 `../a`, `/a`,
`dir/../a` 같은 문자열도 normalize/sanitize하거나 해석하지 않는다.
타입 힌트에 맞춰 `entries`에는 tuple을 전달한다.

```python
from inodefence.model import ArchiveCase, ArchiveEntry, EntryType

case = ArchiveCase(
    entries=(
        ArchiveEntry(
            path="a.txt",
            entry_type=EntryType.REGULAR,
            content=b"hello inodefence",
        ),
        ArchiveEntry(path="b.txt", entry_type=EntryType.HARDLINK, link_target="a.txt"),
    )
)
```

이 예에서는 `entries[0]`이 `a.txt`, `entries[1]`이 `b.txt`다.
baseline 4종은 regular entry 하나, `dir/` directory와 `dir/a.txt` regular entry,
regular entry와 hardlink, regular entry와 symlink의 순서로 표현한다.

### ExecutionResult

향후 Target Adapter가 전달할 프로세스 실행 결과를 target-independent하게 표현한다.
모든 필드는 생성 시 명시적으로 전달한다.

| 실제 필드 | 의미 |
| --- | --- |
| `exit_code: int \| None` | 프로세스 종료 코드; timeout 등으로 코드를 얻지 못한 경우 `None` |
| `stdout: str` | 전달받은 표준 출력 문자열 그대로 |
| `stderr: str` | 전달받은 표준 오류 문자열 그대로 |
| `duration_seconds: float` | 초 단위 실행 시간 |
| `timed_out: bool` | timeout 발생 여부 |

```python
from inodefence.model import ExecutionResult

result = ExecutionResult(
    exit_code=0,
    stdout="ok",
    stderr="",
    duration_seconds=0.1,
    timed_out=False,
)
```

runtime validation이나 값 변환을 추가하지 않는다. 음수 exit code를 허용하며,
timeout과 exit code의 조합이나 duration의 범위를 제한하지 않는다.
stderr 유무와 exit code로 실패·취약 여부를 판정하지 않는다.
filesystem 상태와 Security Contract 판정은 향후 Observer / Oracle의 책임이다.

### ObjectSnapshot

향후 Observer가 전달할 filesystem object 하나의 관찰 사실을 target-independent하게 표현한다.
`ObjectSnapshot`과 `FilesystemObjectType`은 `inodefence.model`에서 import할 수 있다.

| 실제 필드 | 의미 |
| --- | --- |
| `relative_path: str` | 관찰 기준 root에 대한 상대 경로 용도; 입력 문자열 그대로 보존 |
| `object_type: FilesystemObjectType` | 실제 관찰된 종류: `REGULAR`, `DIRECTORY`, `SYMLINK`, `OTHER` |
| `st_dev: int` | 관찰된 device ID |
| `st_ino: int` | 관찰된 inode 번호; `st_dev`와 함께 object identity 표현 |
| `st_nlink: int` | 관찰된 hardlink count |
| `mode: int` | type/permission bit를 포함한 raw stat mode 값 |
| `size: int` | 관찰된 byte 단위 크기 |
| `symlink_target: str \| None = None` | readlink 결과와 같은 raw target 문자열; 미기록 시 `None` |
| `content_hash: str \| None = None` | 선택적으로 전달받은 hash 문자열; 미기록 시 `None` |

`FilesystemObjectType(Enum)`의 값은 각각 `"regular"`, `"directory"`, `"symlink"`, `"other"`다.
archive가 요청한 logical type인 `EntryType`과 구분한다. hardlink는 별도 object type이
아니며 서로 다른 path의 snapshot에 같은 `st_dev` / `st_ino`와 link count를 기록할 수 있다.
`OTHER`는 regular file, directory, symlink 이외의 관찰된 종류를 표현한다.

설계 후보의 `selected_content_hash`는 `content_hash`로 구현했다. 선택적 수집이라는 의미는
`None` 허용으로 유지하며 모델이 hash를 계산하거나 algorithm/문자열 형식을 검사하지 않는다.
숫자 범위, 상대 경로 여부, object type과 symlink target의 조합을 검증하지 않는다.
`../outside/file`, absolute path 등도 보존하며 path/target을 normalize하거나 resolve하지 않는다.
mode bit를 해석하거나 filesystem에 접근하지 않는다. identity 비교와 Security Contract 판정은
이후 소비자의 책임이다.

### StateSnapshot

특정 관찰 시점의 sandbox 상태를 기존 `ObjectSnapshot`의 두 tuple로 묶는다.
`StateSnapshot`과 `SnapshotPhase`는 `filesystem.py`에 있으며 `inodefence.model`에서 import한다.
모든 필드는 생성 시 명시적으로 전달한다.

| 실제 필드 | 의미 |
| --- | --- |
| `phase: SnapshotPhase` | extractor 실행 전(`PRE`) 또는 실행 후(`POST`)의 관찰 시점 |
| `extraction_objects: tuple[ObjectSnapshot, ...]` | extraction root 내부에서 관찰된 object들 |
| `protected_objects: tuple[ObjectSnapshot, ...]` | extraction root 밖이면서 disposable sandbox 안에 있는 controlled sentinel / protected object들 |

`SnapshotPhase(Enum)`의 값은 `PRE = "pre"`, `POST = "post"`다.
현재 Minimal Pipeline의 관찰 시점은 이 phase로 표현하며 timestamp나 observation metadata는 추가하지 않는다.
protected object는 실험용 sentinel을 의미하며 실제 host 민감 파일을 대상으로 하지 않는다.
각 object의 경로와 metadata는 `ObjectSnapshot`에 보존한다.

두 tuple은 빈 값, 입력 순서, 중복 path/object와 동일 identity를 가진 여러 path까지 그대로 보존한다.
정렬, 중복 제거, path 정규화나 identity 병합을 하지 않는다.
PRE/POST별 collection의 비어 있음 여부, path/identity 유일성, 두 collection의 겹침이나
protected object의 존재를 검증하지 않는다.
filesystem 접근·관찰, sentinel 생성·관리, PRE/POST 비교, identity 비교와 보안 판정을 수행하지 않는다.
상태 정규화와 Security Contract 판정은 향후 `StateSignature` / Oracle의 책임이다.

## 하지 않는 것

TAR serialization, filesystem 작업, extractor 실행, mutation, 경로 보안 검증·정규화,
observation, oracle, feedback, CVE-specific 처리.

## 다른 모듈과의 연결

[architecture의 데이터 흐름](../../../docs/research/design/architecture.md)에서 각 모델의 소비자를 본다.

## 현재 상태

`ArchiveEntry`, `ArchiveCase`, `EntryType`을 구현했고
[논리 구조 테스트](../../../tests/test_archive_model.py)로 baseline 4종과 데이터 보존을 검증한다.
`ExecutionResult`를 구현했고 [실행 결과 모델 테스트](../../../tests/test_execution_model.py)로
성공·non-zero 종료·timeout 표현, 출력·시간 보존과 불변성을 검증한다.
`ObjectSnapshot`, `FilesystemObjectType`을 구현했고
[filesystem 모델 테스트](../../../tests/test_filesystem_model.py)로 object 종류, raw 값 보존,
선택적 hash, 검증 없는 필드 조합, 여러 path의 동일 identity 표현과 불변성을 검증한다.
같은 테스트 파일에서 `StateSnapshot`, `SnapshotPhase`의 PRE/POST 표현, 빈 collection,
영역별 tuple의 순서·중복·겹침·동일 identity 보존과 불변성을 검증한다.
[STATUS](../../../docs/STATUS.md)의 Layer 2는 진행 중이며 다른 공통 모델과 pipeline은 미구현이다.

## 파일 배치 규칙

모델 구현 시 필드 의미와 제약을 docstring과 관련 design 문서에 남긴다. target별 실행 옵션은 넣지 않는다.
