# Oracle / Security Model Focused Review v1

> 담당: 주언 — Oracle / Security Model  
> 기준 branch: `main`  
> 기준 commit: `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`  
> 범위: 현재 snapshot 기반 C0/C1/C2의 의미, evidence, 공격 시나리오, 관찰 한계 검토

## 1. 결론

현재 `src/inodefence/oracle/contracts.py`의 C0/C1/C2 구현은
`docs/research/design/security-contracts.md`에 기록된 **현재 snapshot Oracle 범위**와
집중 검토 기준으로 의미가 일치한다.

이번 검토에서 즉시 수정이 필요한 blocker/major semantic mismatch는 확인하지 않았다.

다만 다음을 반드시 구분해서 설명해야 한다.

1. **C0는 raw TAR path 문자열 검사기가 아니다.**
   - `../` 존재 자체가 violation이 아니다.
   - AFTER에 남은 extraction root 밖의 persistent namespace 생성/삭제/identity/type 교체가 evidence다.

2. **C1은 path 관계가 아니라 filesystem object identity 관계다.**
   - `(st_dev, st_ino)`가 모두 같아야 한다.
   - symlink referent를 따라가서 identity를 추론하지 않는다.

3. **C2는 지정된 protected sentinel의 실제 before/after 변화다.**
   - exit code, reject 여부, PoC 문자열이 아니라 object state 변화가 기준이다.

4. **`violated=False`는 안전성 증명이 아니다.**
   - snapshot 사이에 생겼다가 사라진 transient effect,
   - state를 바꾸지 않는 외부 path direct-use,
   - sandbox 밖의 effect는 현재 Oracle만으로 확인할 수 없다.

5. **StateSignature와 Oracle truth는 독립이다.**
   - HARNESS path는 feedback normalization에서 제외될 수 있지만 C0 판정에서는 제외되지 않는다.
   - signature가 같아도 새로운 violation evidence는 별도 fingerprint로 보존해야 한다.

---

## 2. Oracle 정의표

| Contract | 보안 의미 | 현재 입력 evidence | 현재 violation predicate | 대표적으로 잡는 것 | 현재 못 잡는 것 / 한계 |
| --- | --- | --- | --- | --- | --- |
| **C0 — Path Boundary Confinement** | extraction root 밖의 persistent namespace를 target이 생성·삭제·교체하면 안 됨 | BEFORE/AFTER `StateChange` 전체 | `not is_extraction_path(change.path)` 이고 changed fields에 `EXISTENCE`, `IDENTITY`, `OBJECT_TYPE` 중 하나가 존재 | root-level/outside/HARNESS의 파일 생성·삭제·replacement·type replacement | content/mode 등 metadata-only external effect, direct path use without state change, transient create→delete, sandbox 밖 접근 |
| **C1 — Object Identity Confinement** | extraction 내부 object가 protected external sentinel과 동일 filesystem object identity를 공유하면 안 됨 | AFTER의 EXTRACTION object + protected sentinel | `internal.identity == sentinel.identity`, identity는 `(st_dev, st_ino)` | cross-boundary hardlink/shared inode relation | symlink referent identity, transient alias, sentinel이 AFTER 전에 사라진 관계 |
| **C2 — External Effect Noninterference** | untrusted extraction 때문에 protected sentinel의 state가 바뀌면 안 됨 | protected sentinel의 BEFORE/AFTER `StateChange` | protected path에 대해 하나라도 exact changed field가 있으면 violation | deletion, replacement, type, content, size, mode, nlink, uid/gid, mtime/ctime, symlink-target 변화 | protected로 지정하지 않은 external object 변화, atime, transient effect, sandbox 밖 effect |

### C0 정확한 현재 의미

현재 구현의 핵심은 다음과 같다.

```text
outside extraction root
AND
persistent namespace transition
  = existence OR identity OR object_type change
```

따라서 다음 두 경우를 구분한다.

```text
archive/escaped.txt 새로 생성
    -> C0 violation

archive/input.tar 내용만 변경
    -> C0 non-violation
```

둘 다 extraction root 밖 변화지만, 현재 C0는 **namespace boundary evidence**만 다룬다.
두 번째와 같은 content effect는 protected sentinel이면 C2가 담당하고,
non-protected external object이면 현재 C0/C2 사이의 의도된 관찰 공백으로 남는다.

### C1 정확한 현재 의미

```text
extract/a
outside/sentinel.txt

(st_dev, st_ino)가 둘 다 동일
        -> C1 violation
```

inode 숫자만 같고 device가 다르면 C1이 아니다.

또한 다음은 현재 C1이 아니다.

```text
extract/link -> ../outside/sentinel.txt
```

Observer는 `lstat` 기반이므로 symlink object 자체의 identity를 본다.
referent를 따라가서 "같은 object"라고 추론하지 않는다.

### C2 정확한 현재 의미

protected sentinel은 BEFORE에 반드시 존재해야 한다.

현재 exact raw change label은 다음을 포함한다.

```text
EXISTENCE
OBJECT_TYPE
IDENTITY
NLINK
MODE
SIZE
UID
GID
MTIME
CTIME
SYMLINK_TARGET
CONTENT
```

단, creation/deletion은 `EXISTENCE` 하나로 표현한다.
atime은 Observer 자체의 read 영향이 있으므로 Oracle evidence에서 제외한다.

---

## 3. 공격 시나리오 / 기대 Oracle 결과

기호:

- ✅: 해당 contract가 잡아야 함
- —: 해당 contract의 violation이 아님
- △: 최종 AFTER state에 따라 달라짐

| ID | controlled sandbox 시나리오 | C0 | C1 | C2 | 해석 |
| --- | --- | ---: | ---: | ---: | --- |
| S0 | 정상 TAR가 `extract/a.txt`만 생성 | — | — | — | benign baseline |
| S1 | target 처리 결과 `escape.txt` 또는 `outside/new.txt`가 AFTER에 남음 | ✅ | — | — | persistent outside namespace creation |
| S2 | `outside/sentinel.txt`가 삭제됨 | ✅ | — | ✅ | 외부 namespace deletion + protected object destruction |
| S3 | sentinel path가 새 inode/object로 교체됨 | ✅ | — | ✅ | identity/type replacement는 C0와 C2가 함께 잡을 수 있음 |
| S4 | sentinel 내용만 바뀌고 path/object identity는 유지 | — | — | ✅ | C0는 content-only effect를 의도적으로 판단하지 않음 |
| S5 | `extract/alias`가 sentinel과 동일 `(st_dev, st_ino)`를 공유 | — | ✅ | △ | real hardlink 생성은 보통 sentinel nlink/ctime도 바꿔 C2가 함께 켜질 수 있음 |
| S6 | 내부 alias를 통해 sentinel content가 변경되고 alias가 AFTER에도 남음 | — | ✅ | ✅ | identity relation + external effect 모두 관찰 |
| S7 | `extract/link -> ../outside/sentinel.txt` symlink만 생성하고 dereference하지 않음 | — | — | — | 현재 Oracle은 symlink referent 자체를 C1 violation으로 추론하지 않음 |
| S8 | S7 symlink가 실제 write 경로로 사용되어 sentinel content가 변경됨 | — | — 또는 △ | ✅ | alias object가 hardlink가 아니면 C1은 필요 없음. 실제 external effect는 C2 |
| S9 | `../outside/rejected.txt` entry를 target이 거부하고 외부 변화가 없음 | — | — | — | reject/exit code/path spelling 자체는 violation이 아님 |
| S10 | target이 `archive/input.tar`를 삭제·교체 | ✅ | — | — | HARNESS도 extraction boundary 밖이며 C0 evidence. feedback signature의 HARNESS 제외와 독립 |
| S11 | non-protected `outside/other.txt`의 content만 변경 | — | — | — | 현재 snapshot Oracle의 명시적 blind spot |
| S12 | 외부 파일을 만들었다가 AFTER 전에 삭제 | — | — | — | transient effect는 2-snapshot 모델로 복구 불가 |
| S13 | 외부 path를 read/resolve만 하고 state를 바꾸지 않음 | — | — | — | direct-use without state change는 tracing 필요 |
| S14 | sandbox 자체 밖에 effect가 발생 | 관찰 불가 | 관찰 불가 | 관찰 불가 | Oracle보다 execution isolation에서 먼저 차단해야 하는 영역 |

---

## 4. 시나리오별 핵심 설명

### S1 — persistent path escape

예상 최종 상태:

```text
run/
├── extract/
├── outside/
│   └── sentinel.txt
├── archive/
│   └── input.tar
└── escape.txt        <- BEFORE에는 없고 AFTER에 존재
```

`escape.txt`는 EXTRACTION이 아니며 existence transition이 남기 때문에 C0 evidence다.

중요한 점은 raw archive entry가 꼭 `../escape.txt`일 필요가 없다는 것이다.
Oracle은 입력 문자열이 아니라 **실제 관찰된 결과 상태**를 판정한다.

### S5 — cross-boundary object identity

예상 관계:

```text
extract/alias ───────────────┐
                             ├─ same (st_dev, st_ino)
outside/sentinel.txt ────────┘
```

이 관계가 AFTER에 존재하면 C1이다.

실제 Linux hardlink 생성에서는 `st_nlink`와 `ctime`이 변할 수 있으므로
C2도 함께 violation이 될 수 있다. 따라서 평가에서 "C1 case는 항상 C1만 켜진다"고
가정하면 안 된다. Contract는 상호 배타적인 분류가 아니다.

### S7 / S8 — symlink relation과 effect의 분리

```text
extract/link -> ../outside/sentinel.txt
```

symlink만 존재하고 외부 object가 바뀌지 않았다면 현재 C1/C2 violation은 아니다.

하지만 target이 이 symlink를 실제로 따라가 sentinel을 변경하면 C2 evidence가 생긴다.

즉 현재 Oracle은 다음을 구분한다.

```text
potential reference relation
        !=
observed external security effect
```

### S9 — rejection은 PASS/FAIL 근거가 아니다

archive 안에 suspicious spelling이 있어도 target이 안전하게 reject했고
BEFORE/AFTER에 contract evidence가 없다면 C0/C1/C2는 모두 non-violation이다.

```text
ExecutionStatus.REJECTED
        !=
Security Contract violation
```

반대로 target이 failure/nonzero exit를 반환해도 external effect가 남았다면
Oracle은 동일하게 violation을 판정해야 한다.

---

## 5. Evidence flow 검토

현재 역할 분리는 다음과 같다.

```text
Filesystem
  ↓
observer.capture_state()
  ↓
StateSnapshot (raw evidence)
  ↓
observer.compare_states()
  ↓
StateChange
  ↓
oracle.evaluate_contracts()
  ↓
ViolationResult C0/C1/C2
  ↓
state_signature() / violation_fingerprints()
  ↓
Feedback / Corpus
```

집중 검토 결과 다음 책임 분리는 유지되고 있다.

- Observer는 violation을 확정하지 않는다.
- Oracle은 filesystem을 다시 탐색하지 않고 snapshot evidence만 사용한다.
- StateSignature가 raw StateSnapshot을 대체하지 않는다.
- exit status가 security truth를 결정하지 않는다.
- CVE ID/known target version/known PoC bytes가 Oracle predicate에 들어가지 않는다.

---

## 6. 현재 구현에서 특히 중요한 독립성

### 6.1 C0 verdict vs HARNESS normalization

`archive/**`는 StateSignature에서 HARNESS로 제외되지만 security boundary 면제 영역은 아니다.

따라서:

```text
archive/input.tar replacement
    ↓
C0 = violated

하지만
StateSignature = benign baseline과 동일할 수 있음
```

이 경우에도 violation fingerprint 채널이 독립적으로 interesting testcase를 보존해야 한다.
현재 regression은 이 separation을 명시적으로 검사한다.

### 6.2 C1/C2는 동시에 발생할 수 있음

Contract ID는 원인을 하나만 선택하는 mutually-exclusive label이 아니다.

예를 들어 hardlink 기반 cross-boundary alias가 생기고 그 alias를 통해 sentinel까지 수정되면:

```text
C1 = identity relation violation
C2 = protected external effect
```

두 결과를 모두 보존하는 것이 맞다.

---

## 7. 현재 snapshot Oracle의 false-negative boundary

다음은 "안전"이 아니라 **현재 관찰 모델로 증거를 남기지 못하는 경우**다.

### A. transient effect

```text
BEFORE
  ↓
outside/tmp 생성
  ↓
outside/tmp 삭제
  ↓
AFTER
```

AFTER에 흔적이 없으면 2-snapshot 비교로 복구할 수 없다.

### B. external direct-use without mutation

외부 path를 open/read/resolve했지만 상태를 전혀 바꾸지 않으면 C0/C2 evidence가 없다.

### C. non-protected external content-only change

C0는 namespace transition만 다루고,
C2는 protected sentinel만 다루므로 보호 대상으로 지정되지 않은 existing external object의
content/metadata-only 변경은 현재 gap이다.

### D. sandbox 밖 effect

Observer의 snapshot scope 밖이다.
이 영역은 contained target backend/isolation에서 먼저 제한하는 것이 현재 architecture다.

---

## 8. focused review 결과

### Blocker

없음.

### Major

없음.

### Review notes

1. C0 설명 시 "path traversal detector"라고 축약하지 말고 **persistent outside-boundary namespace oracle**이라고 설명하는 편이 정확하다.
2. C1 실험 결과를 해석할 때 C2와 동시 발생 가능성을 허용해야 한다.
3. C2의 의미는 "모든 external file integrity"가 아니라 **protected sentinel noninterference**다.
4. `violated=False`를 "safe"라고 표현하지 않는다.
5. transient/direct-use를 다루려면 snapshot Oracle 확장이 아니라 operation tracing 계층이 필요하다.

---

## 9. 현재 관련 regression 근거

집중 검토에서 확인한 대표 regression:

- `tests/test_state_semantics.py`
  - safe internal hardlink는 violation 아님
  - C1은 device+inode equality를 요구
  - symlink referent를 C1로 추론하지 않음
  - C2 selected metadata/content effect
  - sentinel deletion/replacement 및 outside creation
- `tests/test_pipeline.py`
  - 정상 TAR baseline C0/C1/C2 non-violation
  - HARNESS namespace 생성/삭제/replacement/type change는 C0
  - HARNESS content/mode-only 변화는 C0 아님
  - reject 자체는 violation이 아님
- `tests/test_evidence_validation.py`
  - `StateChange` field가 실제 before/after difference와 정확히 일치해야 함

---

## 10. 오늘 주언 담당 산출물 요약

### Oracle 정의

```text
C0 = outside extraction root의 persistent namespace transition
C1 = extraction object ↔ protected sentinel의 filesystem identity sharing
C2 = protected sentinel의 before/after external effect
```

### 공격 시나리오에서 가장 중요한 세 가지

```text
1. outside file가 남는다
   -> C0

2. extract object가 sentinel과 같은 inode object가 된다
   -> C1

3. sentinel 자체가 바뀐다
   -> C2
```

그리고 이 세 contract는 서로 독립적이므로 한 run에서 둘 이상이 동시에 violation일 수 있다.
