# 공통 데이터 모델

## 이 폴더는 무엇인가

모듈이 주고받을 case와 결과의 표현을 위한 위치다.

## 입력

entry의 경로·종류·내용·link target과 순서. 실행 기록과 관찰 자료는 향후 모델의 입력 후보다.

## 출력

`ArchiveEntry`, `ArchiveCase`로 표현한 논리 archive 구조.

## 책임

예: notes.txt 파일 entry의 경로와 내용을 실행 없이 표현한다.

구현은 [archive.py](archive.py)에 있으며 `inodefence.model`에서 import할 수 있다.
두 모델은 `frozen=True` dataclass다.

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

## 하지 않는 것

TAR serialization, filesystem 작업, extractor 실행, mutation, 경로 보안 검증·정규화,
observation, oracle, feedback, CVE-specific 처리.

## 다른 모듈과의 연결

[architecture의 데이터 흐름](../../../docs/research/design/architecture.md)에서 각 모델의 소비자를 본다.

## 현재 상태

`ArchiveEntry`, `ArchiveCase`, `EntryType`을 구현했고
[논리 구조 테스트](../../../tests/test_archive_model.py)로 baseline 4종과 데이터 보존을 검증한다.
[STATUS](../../../docs/STATUS.md)의 Layer 2는 진행 중이며 다른 공통 모델과 pipeline은 미구현이다.

## 파일 배치 규칙

모델 구현 시 필드 의미와 제약을 docstring과 관련 design 문서에 남긴다. target별 실행 옵션은 넣지 않는다.
