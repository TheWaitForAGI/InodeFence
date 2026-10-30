# 2. Background & Threat Model (드래프트 v1)

## 2.1 Linux filesystem semantics (필요 범위)

이 연구의 범위는 Linux filesystem semantics와 TAR extraction이다(상세 범위: [`../../docs/STATUS.md`](../../docs/STATUS.md)).
경계위반 판정에 필요한 최소 개념만 정리한다.

- **object identity `(st_dev, st_ino)`.** 서로 다른 path가 같은 underlying object(같은 inode)를
  가리킬 수 있다. hardlink가 대표적이며, 같은 filesystem에서 두 이름이 같은 `(st_dev, st_ino)`를
  공유하면 둘은 동일 object다. 따라서 **path-only 관찰은 보안 관련 identity 관계를 놓칠 수 있다.**
- **hardlink / symlink.** hardlink는 기존 object에 새 이름을 더한다(참조 대상이 이미 존재해야 하며
  nlink가 증가한다). symlink는 텍스트 referent를 담는 별도 object다. 이 드래프트의 Observer는
  symlink의 **자기 lstat identity**만 비교하고 referent identity는 추론하지 않는다(한계는 2.5).
- **nlink.** 한 object를 가리키는 hardlink 수. 외부 object를 가리키는 하드링크가 extraction 안에
  생기면 그 외부 object의 nlink가 증가한다(예: 1→2).

## 2.2 TAR extraction과 신뢰 경계

TAR 아카이브의 각 entry는 path·type·link target·처리 순서를 가진다. extractor는 이들을 읽어
filesystem에 regular file·directory·hardlink·symlink를 만든다. 공격자가 제어하는 것은 아카이브
bytes이고, 신뢰 경계는 **extraction root**(`extract/**`)다. entry가 이 경계 밖을 가리키거나 경계 밖
object와 연결되면 경계위반 후보다.

공통 Region 분류(model의 `path_region`에서 단일 정의)는 다음과 같다.

```text
EXTRACTION = extract/**        (추출 결과가 머물러야 하는 영역)
HARNESS    = . / archive / archive/**   (아카이브·하네스 영역; security trust boundary 아님)
EXTERNAL   = 그 밖의 모든 sandbox-relative path   (extraction 밖, 보호 대상)
```

`HARNESS`는 input/harness novelty 오염 방지용 **normalization 정책**이지 security trust boundary가
아니다(C0 scope는 이 정책과 독립적으로 실제 extraction root boundary를 따른다).

## 2.3 Security Contract C0 / C1 / C2

Security Contract는 안전한 archive extraction이 지켜야 할 **일반화된 보안 규칙**이며 특정 CVE
식별자와 독립적으로 정의한다(정의 원문: [`../../docs/research/design/security-contracts.md`](../../docs/research/design/security-contracts.md)).
C0/C1/C2는 IMPLEMENTED / TESTED persistent-snapshot detector이고, C3(Extraction Root Integrity)·
C4(Check/Use Coherence)는 DESIGNED 단계의 후속 계약이다. Oracle의 `violated=True`는 contract
violation **후보**이며, confirmed vulnerability로 보려면 재현과 root-cause 검토가 따로 필요하다.

- **C0 — Path Boundary Confinement.** extraction root 밖(`is_extraction_path`가 False)의 모든
  sandbox-relative path에서 BEFORE→AFTER 사이에 persistent namespace 생성·삭제·identity/type 교체가
  생기면 위반 후보. HARNESS도 포함한다. 기본 path 경계 sanity/baseline이며 **InodeFence의 신규
  기여로 주장하지 않는다.**
- **C1 — Object Identity Confinement.** extraction 내부 object와 보호된 외부 sentinel이 post-state에서
  같은 `(st_dev, st_ino)`를 공유하면 위반 후보. symlink는 lstat object 자체만 비교하고 referent
  identity는 추론하지 않는다.
- **C2 — External Effect Noninterference.** 지정 sentinel의 existence·object type·dev/inode·content
  digest·size·mode·nlink·uid/gid·mtime/ctime이 바뀌면 위반 후보. atime은 Observer 자신의 read로
  바뀔 수 있어 제외한다.

## 2.4 Threat model과 sentinel 정책

- **대상.** 고정 버전의 TAR extractor(본문은 주로 node-tar). 공격면은 공격자 제어 아카이브 bytes다.
- **sentinel.** 실제 host의 민감 파일(`/etc/passwd`, SSH key 등)을 **대상으로 쓰지 않는다.** 각 run은
  전용 runtime sandbox 안에 controlled sentinel(`outside/**` 등 EXTERNAL object)을 만들고, Observer가
  extraction 전후 sentinel 상태를 기록한다.
- **격리.** disposable sandbox + sentinel만 쓰며, third-party target은 검증된 isolated target으로
  실행하고 Linux runtime volume을 source bind mount와 분리한다. **disposable directory는 OS sandbox가
  아니다**(격리의 정확한 의미와 한계는 2.5).

## 2.5 관찰 범위와 한계 (observed vs inferred의 토대)

snapshot 기반 Oracle은 다음을 **판정하지 못한다**(이 한계가 뒤의 모든 observed/inferred 구분의
토대다).

- `violated=False`는 "관찰 범위 안에서 위반 증거가 없다"는 뜻이지 모든 operation이 안전했다는
  증명이 아니다(각 ViolationResult는 이 한계를 `limitations`에 기록).
- 두 snapshot 시점 사이의 중간 변화, transient 생성 후 삭제, inode 번호 재사용, sandbox 밖 접근,
  외부 path의 direct-use는 operation tracing/추가 격리 없이는 복구하지 못한다.
- snapshot은 actor를 식별하지 못한다. 관찰 구간에 harness가 namespace write를 하면 C0 false
  positive가 생길 수 있고, 이를 경로 면제로 풀면 실제 HARNESS escape를 놓친다.
- entry checkpoint 사이의 transition signature는 feedback evidence일 뿐이며, 현재 C0/C1/C2 confirmed
  verdict로 승격하지 않는다. C0/C1/C2는 final BEFORE→AFTER persistent evidence에만 적용한다.

이 경계 덕분에 "**Interesting ≠ Vulnerable**"(탐색 가치 있는 상태 ≠ 확정 취약점)이 전체 설계의
핵심 구분으로 유지된다.
