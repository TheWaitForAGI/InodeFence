---
name: inodefence-security-contract-review
description: Review InodeFence security-state observation and oracle logic against C0-C4 contracts. Use for observer, oracle, StateSnapshot, StateSignature, violation evidence, and security semantics changes.
---

# InodeFence Security Contract Review

보안 판정 코드가 단순히 테스트를 통과하는지가 아니라 **InodeFence가 정의한 security property를 실제로 측정하는지** 검토한다.

기준 문서는 `docs/research/design/security-contracts.md`다.

## 1. 먼저 역할을 분리

검토 대상 로직을 다음 흐름에 배치한다.

```text
Filesystem / extractor result
    ↓
raw observation
    ↓
evidence model
    ↓
security contract evaluation
    ↓
ViolationResult
    ↓
normalized StateSignature / feedback
```

각 단계가 섞여 있으면 먼저 그것을 finding으로 기록한다.

특히 다음 결합을 경계한다.

- Observer가 violation을 확정
- Oracle이 filesystem을 직접 재탐색
- StateSignature가 raw evidence를 대신함
- Feedback이 security truth를 정의
- TargetAdapter가 generic contract를 결정

## 2. C0 — Path Boundary Confinement

확인한다.

- 단순 `../` 문자열 검사만으로 끝나지 않는가?
- raw archive spelling과 resolved/observed path를 혼동하지 않는가?
- extraction boundary 밖의 직접 효과를 증거로 남길 수 있는가?
- C0를 C1/C2의 대체물로 사용하지 않는가?

C0는 baseline/sanity이며 InodeFence novelty라고 표현하지 않는다.

## 3. C1 — Object Identity Confinement

초기 identity 기준은 같은 filesystem의 `(st_dev, st_ino)`다.

확인한다.

- path equality를 object identity로 착각하지 않는가?
- hardlink를 별도 filesystem object type처럼 모델링하지 않는가?
- 내부 object와 protected outside sentinel의 identity 관계를 비교할 수 있는가?
- identity violation을 재현할 raw evidence가 남는가?

inode 번호만 단독 비교하지 않는다. filesystem/device 의미를 잃지 않는다.

## 4. C2 — External Effect Noninterference

sentinel의 before/after evidence를 확인한다.

최소 후보:

- existence
- content hash
- size
- mode
- 필요 시 timestamp/ownership

확인한다.

- archive 내부 결과 변화와 외부 sentinel 변화를 구분하는가?
- pre-state 없이 post-state만 보고 변경을 추론하지 않는가?
- host의 실제 민감 파일이 아니라 controlled sentinel을 사용하는가?
- content와 metadata effect가 명시적으로 구분되는가?

## 5. C3 — Extraction Root Integrity

현재 단계에서 구현 대상이 아니라면 억지로 추가하지 않는다.

관련 변경이면 확인한다.

- extraction root의 path string뿐 아니라 실제 object/redirect 의미를 관찰하는가?
- root replacement/redirect가 이후 operation과 연결되는 증거가 있는가?

## 6. C4 — Check/Use Coherence

instrumentation이 필요한 후속 contract다.

관련 변경이면 확인한다.

- validation 시점의 대상과 실제 operation 대상이 각각 관찰되는가?
- 두 이벤트의 연결 근거가 있는가?
- 단순 결과 상태만 보고 TOCTOU/check-use mismatch를 확정하지 않는가?

근거가 부족하면 confirmed violation 대신 suspicious/candidate로 남긴다.

## 7. CVE 독립성 검사

다음 패턴은 blocker 후보로 본다.

```text
if cve_id == ...
if target_version == known_vulnerable_version ...
if payload == known_poc_bytes ...
if path == exact_known_exploit_path ...
```

Known CVE/PoC는 benchmark ground truth와 root-cause 분석에는 사용할 수 있다.
generic contract 판정의 정의가 되어서는 안 된다.

## 8. Evidence completeness

각 violation에 대해 최소한 다음을 추적할 수 있어야 한다.

- Contract ID
- run/case identifier
- relevant archive entries
- target + version
- pre-state
- post-state
- violated relation/effect
- 재현에 필요한 configuration

증거가 부족하면 "취약점 발견"으로 승격하지 않는다.

## 9. 리뷰 결과 형식

finding은 심각도 순으로 작성한다.

각 finding:

1. 파일/위치
2. 어떤 contract 의미가 깨지는지
3. 잘못된 positive/negative가 어떻게 생기는지
4. 최소 수정 방향
5. 필요한 regression test

문제가 없으면 어떤 contract와 evidence path를 확인했는지 명시한다.
