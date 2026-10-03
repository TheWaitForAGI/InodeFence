# 프로젝트 결정 기록

이 문서는 팀이 이미 합의한 **큰 결정만** 기록한다.

코딩 에이전트가 임의로 이 결정을 바꾸지 않도록 하는 것이 목적이다.

결정을 바꾸려면 PR에서 이유를 설명하고 이 문서도 함께 수정한다.

## D001 — 1차 archive format은 TAR

**상태:** 확정

ZIP 등 다른 format을 동시에 지원하지 않는다.

이유:

- hardlink/symlink entry 지원
- 선형적인 entry 구조
- 최신 취약점 benchmark 존재
- 학부 캡스톤 범위에서 관리 가능

## D002 — Linux filesystem semantics를 기준으로 개발

**상태:** 확정

Windows native filesystem semantics는 1차 범위에서 제외한다.

Mac과 Windows 사용자는 동일한 Linux Dev Container를 사용한다.

## D003 — filesystem 실험은 source mount에서 하지 않음

**상태:** 확정

실험 경로:

```text
/var/lib/inodefence
```

소스 경로:

```text
/workspaces/InodeFence
```

두 역할을 분리한다.

## D004 — 초기 Observer는 pre/post snapshot

**상태:** 확정

처음부터 eBPF/fanotify/full syscall tracing을 필수로 두지 않는다.

Minimal pipeline이 동작한 뒤 필요하면 중간 state transition으로 확장한다.

## D005 — CVE-specific oracle 금지

**상태:** 확정

다음과 같은 판정은 금지한다.

```python
if cve_id == "CVE-...":
    vulnerable = True
```

Oracle은 generic Security Contract를 판정해야 한다.

## D006 — Known CVE PoC를 proposed fuzzer 기본 seed로 사용하지 않음

**상태:** 확정

Known CVE는:

- root-cause 분석
- benchmark ground truth
- 결과 검증

에는 사용할 수 있다.

하지만 rediscovery 성능을 평가할 때 해당 PoC 자체를 시작 seed로 주지 않는다.

## D007 — Zero-day는 성공 조건이 아님

**상태:** 확정

프로젝트 성공은 다음으로도 입증할 수 있다.

- known CVE rediscovery
- baseline 대비 차이
- ablation 결과
- cross-implementation 적용
- 재현 가능한 실험

## D008 — 구현은 Layer 단위로 진행

**상태:** 확정

한 번에 전체 fuzzer를 만들지 않는다.

```text
환경
→ 연구 기반
→ Data Model
→ Minimal Pipeline
→ Mutation
→ Feedback
→ Evaluation
```

현재 Layer보다 두세 단계 앞선 기능을 임의로 추가하지 않는다.

## D009 — 첫 구현 target 우선순위

**상태:** 현재 계획

1. node-tar
2. oras-go
3. GNU tar (시간이 허용할 경우)

실제 benchmark 구성 시 version을 별도로 고정한다.

Core foundation의 Python tarfile/data reference adapter는 architecture/integration 검증용이다. 최종 benchmark target 우선순위를 바꾸지 않는다.

## D010 — 문서는 구현의 일부

**상태:** 확정

공통 interface, 연구 범위, 큰 설계 결정이 바뀌면 관련 문서를 함께 수정한다.

특히 바이브코딩에서는 "코드만 맞고 팀이 이해하지 못하는 상태"를 완료로 보지 않는다.

## D011 — 초기 직렬화와 evidence 경계

**상태:** core foundation 구현

Logical case는 raw path/link text와 ordered tuple을 유지한다. 초기 TAR encoding은 strict UTF-8 USTAR와 고정 metadata(`ustar-utf8-v1`)다. Encoding 불가능한 길이는 truncate하거나 다른 format으로 자동 전환하지 않고 거부한다. Fixture script도 core builder를 사용한다.

Model/result export는 versioned canonical JSON이다. Bytes는 base64로 보존하고 raw observations와 portable signature를 구분한다. Inode 숫자·timestamp 원값을 signature key로 쓰지 않는다. 현재 signature는 초기 schema이며 최종 feedback 정책은 Layer 5에서 평가한다.

## D012 — snapshot 판정 범위를 결과에 보존

**상태:** core foundation 구현

C0 external namespace evidence와 C2 object effect를 구분한다. External content change만으로 direct external path use를 추정하지 않는다. Full operation tracing 없이 증명할 수 없는 범위는 ViolationResult.limitations에 기록한다. Observer 오류를 incomplete snapshot이나 PASS로 바꾸지 않는다.

Runtime directory는 cleanup 경계이며 OS execution isolation을 대신하지 않는다. Unsafe benchmark adapter에는 별도 process/filesystem isolation이 필요하다. Reference worker만 추가하며 node-tar/ oras-go benchmark와 연구 효과 검증은 후속 작업으로 유지한다.

## D013 — raw evidence와 normalized security-state scope 분리

**상태:** PR #15 review 수정

Human/AI review에서 snapshot 전체를 signature로 옮기면 `archive/input.tar` digest가 input novelty를 security-state novelty로 오인하게 만든다는 문제가 확인됐다. `StateSnapshot = full raw observation/evidence`를 유지하고 `StateSignature = normalized security-state representation for future feedback/corpus`로 범위를 분리한다. ArchiveCase identity와 TAR artifact identity는 signature에 직접 포함하지 않는다.

공통 `path_region`이 fixed runtime layout의 namespace role을 정의한다. `extract`와 하위는 EXTRACTION, `.`과 `archive` 및 하위는 HARNESS, 나머지는 EXTERNAL이다. Harness bookkeeping은 archive 아래에 둔다. EXTERNAL은 outside만으로 제한하지 않으므로 sandbox root의 `escape.txt`도 C0 evidence와 signature에 남는다. Harness 경로는 C0 namespace evidence에서 제외하되 raw snapshot/change에서 보존한다. 이는 path ownership 분류이며 operation의 원인 추론이 아니다.

StateSignature v2는 HARNESS object를 제외하고 identity group도 같은 scope로 projection하여 singleton을 제거한다. Protected paths와 extraction↔sentinel relation, external-effect labels는 유지한다. `SignatureObject.st_nlink`는 regular file만 정수이며 directory/symlink/other는 None이다. Directory size와 nlink 값은 filesystem allocation/semantics에 따라 달라질 수 있기 때문이다. Raw nlink와 C2 metadata 비교, external nlink-change label은 그대로 보존한다. 따라서 portable representation은 모든 filesystem의 effect pattern이 같다는 보장은 아니다.

Signature 내부 schema는 v1→v2로 변경한다. Canonical JSON envelope v1과 case identity encoding은 유지한다. Corpus/persistence/deserializer는 아직 없고 이전 signature와 같은 key로 비교하지 않는다. 서로 독립인 regular entry 두 개의 순서만 다른 입력을 `run_case()`로 실행해 case/TAR SHA-256은 다르고 signature는 같은지 검증한다. 최종 feedback/corpus 정책과 연구 효과 평가는 Layer 5 이후다.
