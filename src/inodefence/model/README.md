# 공통 데이터 모델

## 책임

실행이나 판정 없이 모듈 사이의 immutable 데이터와 evidence를 표현한다. 모두 frozen/slots dataclass와 tuple collection을 사용한다. [architecture의 현재 API](../../../docs/research/design/architecture.md)를 따른다.

| 파일 | 주요 모델 |
| --- | --- |
| [archive.py](archive.py) | ArchiveEntry, EntryType, ArchiveCase |
| [filesystem.py](filesystem.py) | ObjectSnapshot, StateSnapshot, StateChange, StateSignature |
| [results.py](results.py) | ExecutionResult, IdentityEvidence, ViolationResult, RunResult |
| [serialization.py](serialization.py) | canonical_json, schema version 1 |

ArchiveEntry는 raw path/link text를 보존하고 NUL·잘못된 field 조합을 거부한다. regular는 bytes content, directory는 content/target 없음, hardlink/symlink는 target 필수다. USTAR 길이 제한은 builder의 책임이다. ArchiveCase는 order/duplicate를 보존하며 versioned canonical representation의 SHA-256을 `case_id`로 제공한다. Mutation lineage는 후속 설계다.

ObjectSnapshot은 존재하는 lstat object다. `StateSnapshot.get(path) is None`은 부재를 나타내며 protected_paths는 sentinel 삭제 후에도 남는다. Snapshot은 path 순서와 보호 대상 설정을 검증한다. Symlink identity는 referent가 아닌 링크 자체다.

`StateSnapshot = full raw observation/evidence`: sandbox 전체와 harness artifact의 digest/metadata를 보존한다. 공통 `Region`/`path_region`은 `extract`와 하위를 EXTRACTION, `.`/`archive`와 하위를 HARNESS, 나머지를 EXTERNAL로 분류한다. Root-level escape도 EXTERNAL이며 sentinel 설정은 EXTERNAL만 허용한다. Harness bookkeeping은 archive 아래에 둔다.

Region.HARNESS는 normalization namespace role이며 security trust boundary나 생성 주체의 증거가 아니다. `is_extraction_path`는 region과 독립적으로 fixed extraction namespace membership을 표현한다. 이 layout 사실을 소비해 C0 정책을 적용하는 책임은 Oracle에 있다. Baseline ownership은 setup 후 BEFORE의 실제 objects로 기록하고, SnapshotPhase는 target 실행을 전후로 구분한다. Phase가 actor provenance를 제공하지는 않는다. Runner/adapter는 BEFORE 이전에 setup을 마치고 AFTER 이후에 bookkeeping/cleanup을 해야 한다.

`StateSignature = normalized security-state representation for future feedback/corpus`: 내부 schema v2는 HARNESS를 제외한다. ArchiveCase identity와 TAR artifact identity는 직접 포함하지 않는다. Identity group도 같은 object scope로 projection하고 singleton을 제거한다. Protected paths와 extraction↔sentinel relation, external effect labels는 유지한다. `SignatureObject.st_nlink: int | None`은 regular만 정수이고 directory/symlink/other는 None이다. Raw nlink와 C2 metadata 판정은 바뀌지 않는다.

ExecutionResult의 status와 filesystem verdict는 독립적이다. RunResult는 case, TAR format/hash, 실행 provenance, before/after, 변화, signature와 계약 evidence를 보존한다. 실제 run directory는 반환 전에 삭제된다.

ExecutionResult의 필수 `duration_seconds`는 finite/0 이상인 실제 monotonic elapsed execution evidence이며 0.0과 numeric int 값도 허용한다. `timeout_seconds`는 configured budget으로 별개다. Duration은 process startup과 timeout 종료·회수 overhead를 포함하고 RunResult.execution의 canonical JSON으로 보존한다. Security verdict, StateSignature v2와 case ID에는 사용하지 않는다.

`canonical_json(model)`은 envelope schema v1/model type과 정렬된 JSON key를 기록하고 bytes를 base64로 보존한다. Signature 내부 schema v2와는 별개이며 case encoding은 유지한다. Raw snapshot에는 inode·timestamp 원값이 있지만 portable signature에는 없다. 이는 export 경계이며 database나 deserializer는 아니다. Formal experiment runner는 commit, OS/kernel, config/seed/budget provenance를 추가해야 한다.

## 하지 않는 것

TAR encoding, target-specific 옵션, filesystem 실행, mutation, security/interestingness 판정.
