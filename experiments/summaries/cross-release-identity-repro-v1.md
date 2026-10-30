# Cross-release identity 통제 재현 — validated summary v1

M2(실제 경계위반 통제 재현 + 버전 구분) 결론의 **검증된 작은 요약**이다.
[summaries 규칙](README.md)의 체인을 명시한다:

```text
raw: experiments/repro/evidence/*.json
  → validated summary: 이 문서
  → finding: 아래 "## Finding"
  → paper 포인터: ../../paper/sections/claims-evidence-status-v1.md
  → 능력 원장(단일 기준): ../../docs/STATUS.md (Capability Ledger M2 행 / 마일스톤 M2)
```

이 요약은 raw JSON을 **재현 가능한 변환**(아래 재생성 명령)으로 읽은 것이며, raw 없이 수동으로
숫자를 지어내지 않았다. observed(실행 출력으로 확인)와 inferred(추론)를 구분한다.

## 실험 설정 (provenance)

| 항목 | 값 |
| --- | --- |
| experiment config | [`../repro/cross_release_identity.py`](../repro/cross_release_identity.py) |
| raw 생성 commit (InodeFence) | `86a4585` (feat(M2): 통제 재현을 스크립트+raw 증거로 박제) |
| 요약 검증 base commit | `df9652c` (이 PR 브랜치 base = main) |
| target | node-tar (JS), 고정 릴리스 5종 |
| target 정확 버전 | 7.5.2, 7.5.3, 7.5.6, 7.5.7, 7.5.8 (docker image `inodefence-node-tar-effect:{release}`) |
| random seed | **해당 없음** — 손으로 만든 결정론적 fixture(퍼저 입력 아님) |
| execution budget | **해당 없음** — 릴리스당 fixture 1회 추출(퍼징 아님) |
| timeout | `docker run` 당 90s |
| 실행 환경 | 호스트 docker, 릴리스별 disposable Linux 컨테이너(`--user 0:0`); `make check` 미수집(호스트 전용 재현) |

### raw 증거 위치 · 재생성

- 조합 요약: [`../repro/evidence/summary.json`](../repro/evidence/summary.json)
- fixture별 원본: [`../repro/evidence/toplevel_hardlink.json`](../repro/evidence/toplevel_hardlink.json),
  [`../repro/evidence/nested_hardlink.json`](../repro/evidence/nested_hardlink.json)
- 재생성(호스트 docker + 5개 이미지 필요): `python experiments/repro/cross_release_identity.py --out experiments/repro/evidence`

## 검증된 표 (observed)

verdict = "추출된 객체가 외부 참조파일의 `(st_dev, st_ino)` identity를 공유하는가" — 이것이 C1
oracle이 평가하는 바로 그 관찰이며, 릴리스 id나 "정답" 경로를 판정 조건에 넣지 않는다.
두 fixture 모두 링크 타깃은 동일한 상대 경로(`../ext/reference.bin`, 추출 디렉터리를 벗어남)이고,
top-level에 두느냐 subdir 안에 두느냐만 다르다.

| 릴리스 | toplevel_hardlink | nested_hardlink |
| --- | --- | --- |
| 7.5.2 | **공유**(resolved, nlink 1→2) | **공유**(resolved, nlink 1→2) |
| 7.5.3 | 거부 `linkpath contains '..'` | 거부 `linkpath contains '..'` |
| 7.5.6 | 거부 `linkpath escapes extraction directory` | **공유**(resolved, nlink 1→2) |
| 7.5.7 | 거부 `linkpath contains '..'` | 거부 `linkpath contains '..'` |
| 7.5.8 | 거부 `linkpath contains '..'` | 거부 `linkpath contains '..'` |

고정 쌍(fixed pair): toplevel = (7.5.2 공유 → 7.5.3 거부), nested = (7.5.6 공유 → 7.5.7 거부).
nested fixture의 분포는 **비단조**(7.5.2 O · 7.5.3 X · 7.5.6 O · 7.5.7 X · 7.5.8 X): 7.5.3이
닫은 경로를 7.5.6이 되돌렸고 7.5.7이 다시 닫았음을 보인다.

## Finding

**동일한 generic identity oracle 하나**(추출 객체 ↔ 외부 참조파일 inode 공유 = C1, 참조파일의
전후 metadata 변화 = C2)가 서로 다른 **두 root-cause**를 릴리스 id·정답 경로 하드코딩 없이
모두 포착한다.

- **R1 = CVE-2026-23745** (catalog N01): linkpath sanitation 누락. toplevel 하드링크가 7.5.2에서
  공유되고 7.5.3에서 거부되는 전환으로 재현(observed).
- **R2 = CVE-2026-24842** (catalog N02, GHSA-34x7-hfp2-rc4v): 검증 base ≠ 생성 base의 check/use
  mismatch 회귀(= R1 수정이 도입). nested 하드링크가 7.5.6에서 공유되고 7.5.7에서 거부되는
  전환으로 재현(observed).

핵심: outcome 기반 oracle 하나로 R1·R2를 관통한다 — "CVE PoC나 고정 공격 패턴을 하드코딩하지
않고 filesystem-security-state(object identity + external effect)를 판정에 쓴다"는 연구 자세와 정합.
known CVE를 ground-truth로 쓰는 것은 연구 규칙 3에 따라 허용된다(oracle 조건에 CVE 식별자를
심지 않는다 = 규칙 1 준수).

### observed vs inferred

- **observed**: 위 5×2 verdict 표(raw JSON에서 직접 읽음), nlink 전이, 거부 메시지, 비단조 분포.
- **inferred**: 특정 CVE ↔ fixture 대응(R1↔toplevel 쌍, R2↔nested 쌍)과 "7.5.6 회귀가 R1 수정이
  도입한 것"이라는 인과 서술. advisory 범위(24842 `<7.5.7`)와 이 **특정** fixture의 observed 거동은
  다를 수 있어 **exact 하한은 미검증**이다.

## Production-path 일치 (M2.2 박제)

손 probe(위 raw)의 판정이 우리 production Observer+Oracle 경로의 판정과 **일치**함을 additive
테스트로 고정했다(손 probe == oracle 판정):

- CI 수집: [`../../tests/test_cross_release_oracle_agreement.py`](../../tests/test_cross_release_oracle_agreement.py)
  — `run_case` 경로로 7.5.2 공유 post-state를 재현해 generic C1+C2 일치 + M2.1 증거 바인딩.
- native closure(호스트 docker+이미지, `make check` 미수집):
  [`../../tests/container_integration/check_cross_release_oracle_agreement.py`](../../tests/container_integration/check_cross_release_oracle_agreement.py)
  — `run_node_tar_effect_case` 경로.

oracle/fixture/N01 경로는 불변이고, 릴리스 문자열은 증거 키일 뿐 판정 조건이 아니다.

## 정직 경계 (반드시 유지)

- 이것은 **통제 재현**이지 **퍼저 자력 발견이 아니다**(자력 발견은 M3,
  [node self-discovery 요약](node-self-discovery-mechanism-v1.md)).
- fixture는 손으로 만든 generic 하드링크 엔트리다(퍼저가 발견한 입력 아님).
- observed(실제 node-tar 거동)와 reproduced/inferred(통제 extractor post-state, CVE 대응)를 구분한다.
- 선행연구 포지셔닝은 [related-work-positioning](../../docs/research/design/related-work-positioning.md)을
  따른다("최초/새로운" 금지). 하드링크·링크 상태 관찰·버전 차분 자체는 선행연구(LinkZard·ZIPDiff·
  Wormholes)가 다루므로 신규 기여로 표현하지 않는다.
