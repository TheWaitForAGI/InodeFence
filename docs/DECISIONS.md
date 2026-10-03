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

## D010 — 문서는 구현의 일부

**상태:** 확정

공통 interface, 연구 범위, 큰 설계 결정이 바뀌면 관련 문서를 함께 수정한다.

특히 바이브코딩에서는 "코드만 맞고 팀이 이해하지 못하는 상태"를 완료로 보지 않는다.
