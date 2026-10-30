# 표 M2 — Cross-release identity 통제 재현 증거표

M2(§5.2)의 근거표다. verdict = "추출된 객체가 외부 참조파일의 `(st_dev, st_ino)` identity를
공유하는가" — 이것이 C1 oracle이 평가하는 바로 그 관찰이며, 릴리스 id나 정답 경로를 판정 조건에
넣지 않는다. 두 fixture 모두 링크 타깃은 동일한 상대 경로(추출 디렉터리를 벗어남)이고, top-level에
두느냐 subdir 안에 두느냐만 다르다.

## Provenance

| 항목 | 값 |
| --- | --- |
| raw 조합 요약 | [`../../experiments/repro/evidence/summary.json`](../../experiments/repro/evidence/summary.json) |
| experiment config | [`../../experiments/repro/cross_release_identity.py`](../../experiments/repro/cross_release_identity.py) |
| validated summary | [cross-release-identity-repro-v1](../../experiments/summaries/cross-release-identity-repro-v1.md) |
| target | node-tar (JS), 고정 릴리스 5종 (docker image `inodefence-node-tar-effect:{release}`) |
| seed / budget | 해당 없음 — 손으로 만든 결정론적 fixture(퍼저 입력 아님), 릴리스당 1회 추출 |
| 실행 환경 | 호스트 docker, 릴리스별 disposable Linux 컨테이너; `make check` 미수집(호스트 전용 재현) |
| 재생성 | `python experiments/repro/cross_release_identity.py --out experiments/repro/evidence` (호스트 docker + 5개 이미지 필요) |

## verdict 표 (observed)

| 릴리스 | toplevel_hardlink | nested_hardlink |
| --- | --- | --- |
| 7.5.2 | **공유** (resolved, nlink 1→2) | **공유** (resolved, nlink 1→2) |
| 7.5.3 | 거부 `linkpath contains '..'` | 거부 `linkpath contains '..'` |
| 7.5.6 | 거부 `linkpath escapes extraction directory` | **공유** (resolved, nlink 1→2) |
| 7.5.7 | 거부 `linkpath contains '..'` | 거부 `linkpath contains '..'` |
| 7.5.8 | 거부 `linkpath contains '..'` | 거부 `linkpath contains '..'` |

- **고정 쌍(fixed pair):** toplevel = (7.5.2 공유 → 7.5.3 거부) = R1 = CVE-2026-23745 (catalog N01);
  nested = (7.5.6 공유 → 7.5.7 거부) = R2 = CVE-2026-24842 (catalog N02, GHSA-34x7-hfp2-rc4v).
- **비단조 분포:** nested fixture는 7.5.2 공유 · 7.5.3 거부 · 7.5.6 공유 · 7.5.7 거부 · 7.5.8 거부로,
  7.5.3이 닫은 경로를 7.5.6이 되돌렸고 7.5.7이 다시 닫았음을 보인다. R2는 R1 수정이 도입한
  check/use mismatch 회귀다.

## observed vs inferred

- **observed:** 위 5×2 verdict(raw JSON에서 직접 읽음), nlink 전이, 거부 메시지, 비단조 분포.
- **inferred:** 특정 CVE↔fixture 대응(R1↔toplevel 쌍, R2↔nested 쌍)과 "7.5.6 회귀가 R1 수정이
  도입한 것"이라는 인과 서술. advisory 범위(24842 `<7.5.7`)와 이 **특정** fixture의 observed 거동은
  다를 수 있어 **exact 하한은 미검증**이다.

핵심: **outcome 기반 oracle 하나가 R1·R2 두 root-cause를 릴리스 id·정답 경로 하드코딩 없이
포착한다.** 이는 통제 재현이지 퍼저 자력 발견이 아니다(자력 발견은 [표 M3](m3-blind-ablation.md)).
