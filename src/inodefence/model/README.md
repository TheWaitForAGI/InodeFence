# 공통 데이터 모델

## 책임

실행이나 판정 없이 모듈 사이의 immutable 데이터와 evidence를 표현한다. 모두 frozen/slots dataclass와 tuple collection을 사용한다. [architecture의 현재 API](../../../docs/research/design/architecture.md)를 따른다.

| 파일 | 주요 모델 |
| --- | --- |
| [archive.py](archive.py) | ArchiveEntry, EntryType, ArchiveCase |
| [filesystem.py](filesystem.py) | ObjectSnapshot, StateSnapshot, StateChange, StateSignature |
| [results.py](results.py) | ExecutionResult, IdentityEvidence, ViolationResult, RunResult |
| [provenance.py](provenance.py) | Source/Environment/Target/Sentinel/ExecutionProvenance configuration values |
| [serialization.py](serialization.py) | canonical_json, schema version 1 |

ArchiveEntry는 raw path/link text를 보존하고 NUL·잘못된 field 조합을 거부한다. regular는 bytes content, directory는 content/target 없음, hardlink/symlink는 target 필수다. USTAR 길이 제한은 builder의 책임이다. ArchiveCase는 order/duplicate를 보존하며 versioned canonical representation의 SHA-256을 `case_id`로 제공한다. Parent lineage는 상위 campaign step에 기록하며 ArchiveCase identity에 섞지 않는다.

**Archive input path != Observed filesystem path.** `ArchiveEntry.path`/`link_target`은 `../`, absolute-looking spelling을 포함한 untrusted raw logical input이다. `ObjectSnapshot.path`는 Observer가 만든 canonical sandbox-relative evidence이며 absolute path, 빈/`.`/`..` component를 거부한다(루트 자체의 `.`는 허용). Malformed raw TAR encoding fuzzing은 향후 Builder/encoding mutation layer의 책임이며 observed snapshot invariant를 느슨하게 만들지 않는다.

ObjectSnapshot은 존재하는 lstat object다. ObjectType enum, nonnegative integer dev/inode/nlink/size/uid/gid, integer mtime/ctime nanoseconds를 검증한다. `mode`는 `stat.S_IMODE(st_mode)`의 permission/special mode bits(`0..0o7777`)이며 object type bits는 ObjectType에 따로 둔다. `content_digest`는 regular file content의 SHA-256 lowercase hexadecimal evidence(64자)이며 regular에 필수, 다른 type에는 None이다. `symlink_target`은 symlink에만 필수이며 raw readlink text를 resolve하지 않는다. Identity는 `(st_dev, st_ino)`이고 symlink는 referent가 아닌 링크 자체다. Hardlink는 별도 object type이 아니라 같은 identity를 공유하는 regular object 관계다.

StateSnapshot의 field는 `sandbox_root: str`, `phase: SnapshotPhase`, `objects: tuple[ObjectSnapshot, ...]`, `protected_paths: tuple[str, ...]`다. Objects는 canonical path 기준 unique/sorted여야 하며 ArchiveCase의 duplicate/order semantics와 다르다. `StateSnapshot.get(path) is None`은 부재를 나타내며 protected_paths는 sentinel 삭제 후에도 남는다. Snapshot은 보호 대상 설정도 검증한다.

`StateSnapshot = full raw observation/evidence`: sandbox 전체와 harness artifact의 digest/metadata를 보존한다. 공통 `Region`/`path_region`은 `extract`/`extract/**`를 EXTRACTION, `.`/`archive`/`archive/**`를 HARNESS, 그 외 모든 canonical sandbox-relative path를 EXTERNAL로 분류한다. `outside/**`와 root-level `escape.txt`도 EXTERNAL이며 sentinel 설정은 EXTERNAL만 허용한다. Harness bookkeeping은 archive 아래에 둔다.

`path_region()`은 위 namespace 분류를 따르는 현재 runtime-layout policy이며 filesystem object의 intrinsic property가 아니다. 향후 target/runtime layout 변경 시 이 정책을 함께 검토해야 한다.

Region.HARNESS는 normalization namespace role이며 security trust boundary나 생성 주체의 증거가 아니다. `is_extraction_path`는 region과 독립적으로 fixed extraction namespace membership을 표현한다. 이 layout 사실을 소비해 C0 정책을 적용하는 책임은 Oracle에 있다. Baseline ownership은 setup 후 BEFORE의 실제 objects로 기록하고, SnapshotPhase는 target 실행을 전후로 구분한다. Phase가 actor provenance를 제공하지는 않는다. Runner/adapter는 BEFORE 이전에 setup을 마치고 AFTER 이후에 bookkeeping/cleanup을 해야 한다.

`StateSignature = normalized security-state representation for future feedback/corpus`: 내부 schema v2는 HARNESS를 제외한다. ArchiveCase identity와 TAR artifact identity는 직접 포함하지 않는다. Identity group도 같은 object scope로 projection하고 singleton을 제거한다. Protected paths와 extraction↔sentinel relation, external effect labels는 유지한다. `SignatureObject.st_nlink: int | None`은 regular만 정수이고 directory/symlink/other는 None이다. Raw nlink와 C2 metadata 판정은 바뀌지 않는다.

**ExecutionResult = process evidence, not security verdict.** Status, exit code, duration을 safe/vulnerable 의미로 해석하지 않는다. `TIMED_OUT`가 authoritative하며 별도 timed_out bool은 없다. 기존 status/exit-code consistency를 유지한다.

| ExecutionResult field | type / 의미 |
| --- | --- |
| target_id, target_version | str / target 실행 provenance |
| command | tuple[str, ...] / 실행 command |
| status | ExecutionStatus / SUCCESS, REJECTED, FAILED, TIMED_OUT |
| exit_code | int \| None / 완료된 exit code; TIMED_OUT은 None, SUCCESS만 0 |
| stdout, stderr | str / decoded process output |
| duration_seconds | float / 필수 monotonic elapsed seconds, finite 및 >= 0 |
| timeout_seconds | float \| None / configured budget, 주어지면 finite 및 > 0; default None |

Python reference는 `time.perf_counter()`로 subprocess 실행 직전부터 정상 완료 또는 timeout kill/wait 이후까지의 actual monotonic elapsed duration을 초 단위로 측정한다. Startup, output collection, timeout 시 kill/wait도 포함하며 setup·snapshot·전체 pipeline 시간은 아니다. 네 status 모두 duration을 기록하며 configured timeout보다 길 수 있다. `canonical_json`에 duration도 raw execution evidence로 남고 Oracle/StateSignature에는 입력하지 않는다.

RunResult는 case, TAR format/hash, 실행 provenance, before/after, 변화, signature와 계약 evidence를 보존한다. 실제 run directory는 반환 전에 삭제된다.

ExecutionResult의 필수 `duration_seconds`는 finite/0 이상인 실제 monotonic elapsed execution evidence이며 0.0과 numeric int 값도 허용한다. `timeout_seconds`는 configured budget으로 별개다. Duration은 process startup과 timeout 종료·회수 overhead를 포함하고 RunResult.execution의 canonical JSON으로 보존한다. Security verdict, StateSignature v2와 case ID에는 사용하지 않는다.

`canonical_json(model)`은 envelope schema v1/model type과 정렬된 JSON key를 기록하고 bytes를 base64로 보존한다. Signature 내부 schema v2와는 별개이며 case encoding은 유지한다. Raw snapshot에는 inode·timestamp 원값이 있지만 portable signature에는 없다. 이는 export 경계이며 database나 deserializer는 아니다. 상위 campaign exporter도 이 encoding을 그대로 사용한다. Config/seed/budget은 campaign result에
있으며 실행 전 source/environment/target/sentinel provenance는 CampaignResult에 별도 보존한다.
모델은 실행 logic이 없고 capture helper는 상위 provenance.py에 있다. Full Git ID 또는 None,
dirty bool/None, platform 문자열, declared target/timeout, sorted unique sentinel name/digest/mode를
검증한다. Raw inode/timestamp/process 결과는 이 configuration contract에 없다.

## 하지 않는 것

TargetProvenance.execution_safety는 ExecutionSafety enum으로 검증한다. Default는
ISOLATION_REQUIRED이고 TRUSTED_REFERENCE는 현재 controlled reference adapter의 trust 선언이다.
이 값은 configuration이며 model 자체가 OS 격리를 수행하거나 보장하지 않는다.

TAR encoding, target-specific 옵션, filesystem 실행, mutation, security/interestingness 판정.
