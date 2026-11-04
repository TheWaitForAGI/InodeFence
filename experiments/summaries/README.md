# 검증된 작은 실험 요약

```text
raw experiment output → validated small summary → paper table / figure
```

작은 JSON/CSV/Markdown 요약을 Git으로 추적할 수 있다. 대량 raw output은
`experiments/raw/`에 두고 계속 Git ignore한다. 원본의 보존·공유 위치와 식별자 또는
checksum, 요약 생성 명령/스크립트 및 필터·집계 기준을 남겨 팀원이 검증할 수 있게 한다.

각 summary는 최소 다음 정보를 연결한다.

- experiment config (경로 또는 안정적인 식별자)
- InodeFence commit
- target 및 정확한 target version
- random seed
- execution budget와 timeout 기준
- result (실패/timeout 포함) 및 raw evidence 위치

raw data 없이 summary 숫자를 수동으로 invent하지 않는다. 원본을 수동 수정하지 않고
재현 가능한 변환으로 요약한다. 서로 다른 환경을 집계한다면 환경별 결과와 비교 가능성
검증을 남긴다. 요약 검증과 paper 해석은 별개이며 미공개 finding은
[disclosure 정책](../../SECURITY.md)을 따른다.

## raw 보존 상태 (2026-11-04)

raw는 Git에 올리지 않으므로(위 정책), 저장소에는 **checksum 목록(manifest)만** 남고 원본 바이트는
각 실험 호스트의 `~/inodefence-evidence/`에만 있다. manifest는
[`scripts/make_raw_manifest.py`](../../scripts/make_raw_manifest.py)로 생성·검증한다
(`--verify <manifest> --root <raw-dir>`; `sha256sum --check`와도 호환). 아래 표는 숨김 없이
현재 보존 상태를 적는다 — **원본 외부 백업은 아직 없다.**

| 호스트 | 아키텍처 | raw 위치 | manifest | 파일/크기 | 외부 백업 | 복구 가능성 |
| --- | --- | --- | --- | --- | --- | --- |
| mac | arm64 | `~/inodefence-evidence/` (mac 호스트) | [raw-manifest-mac-20261103.sha256](raw-manifest-mac-20261103.sha256) | 1,614 파일 / 이 호스트에서 크기 측정 불가 | **없음** | mac 호스트가 원본을 보유하는 동안만. 저장소는 checksum만 보유 |
| win (이 호스트) | x86_64 | `~/inodefence-evidence/` (WSL2) | [raw-manifest-win-20261104.sha256](raw-manifest-win-20261104.sha256) | 44 파일 / 약 20.7 MiB (gzip -9 약 2.68 MiB) | **없음** | 이 호스트의 원본 + 저장소 checksum. off-host 사본 없음 |

win manifest는 두 독립 도구가 바이트 동일하게 생성했다(이 저장소 스크립트, 그리고 코드 재사용 없이 손으로
Wilson까지 재계산한 별도 검증 — 재계산 보고는 이 세션 외부 산출물이므로 포인터만 둔다). 두 파일의
SHA-256 `0de2aef3…`가 일치하고, `--verify`는 44/44 ok다.

### win 호스트 raw 구성 메모 (오해 방지)

- **집계에 쓰인 raw (20파일)**: M4.5 등록 세트 `…-m45-{a1,sa}-s{500..509}.json`. 이 20파일에서
  [m4-5-decompress-selfdiscover-win-v1.json](m4-5-decompress-selfdiscover-win-v1.json)이 바이트 동일하게
  재생성된다(repo `scripts/analyze_m4_5_selfdiscover.py` 재실행 산출물 SHA-256 `4088be16…` 일치).
- **보고서에 파일명으로 누락됐던 raw(이 호스트 존재)**: 동시성 캘리브레이션 `…-cal-c4-s{600..603}`·
  `…-cal-c8-s{604..611}`(12, budget 100), 인프라 프로브 `…-probe-infra-s999[-b200]`(2),
  `make demo`형 node-tar 실행 `…-effect-demo-native-20261101-{223844,224453,224558}.*`(5, 그중
  `223844.steps.jsonl`은 0바이트 중단 시작), oras-go smoke `…-oras-smoke-s11`(1, budget 8).
- **윈도우 증거가 아닌 파일**: `…-oras-{a1,sa}-s11.json` 2파일은 mac manifest 항목과 SHA-256가 동일한
  **mac raw 사본**이다(M4.7은 mac에서 실행됨). manifest에는 이 호스트 트리의 사실로서 포함되지만
  윈도우 독립 실행으로 세지 않는다.
- **검증 불가 서술**: 4개 재실행 셀(a1/sa-s500, a1-s505, sa-s504)의 첫 시도 abort stub이 덮어써져,
  "sa-s504가 2회 연속 abort됐다"는 서술은 LOG/WORKLOG 기록으로만 남고 raw로 재확인되지 않는다. 현재
  남은 `…-m45-sa-s504.json`은 217바이트 abort stub 1개다.

### m4-5 통합 verdict 라벨 결함 (알려짐, 수치 무관)

[m4-5-decompress-selfdiscover-unified-v1.json](m4-5-decompress-selfdiscover-unified-v1.json)의
`hosts.mac.roll_up.architecture`가 `x86_64`로 기록돼 있다 — 맥 블록이므로 `arm64`가 맞다.
`analyze_m4_5_selfdiscover.py`의 `roll_up()`이 architecture 문자열을 하드코딩해 맥 호스트 뷰가
윈도우 기본값을 물려받은 것이다(상위 `hosts.mac.architecture`는 올바르게 `arm64`, 합산 수치는 전부 무관).
코드는 2026-11-04에 `roll_up(architecture=…, arch_disclosure=…)`로 인자화했고 통합 스크립트가 맥 블록에
`arm64`를 넘기도록 고쳤다(윈도우 경로는 기본값 유지로 바이트 동일 — 20 raw 재생성 전후 SHA-256
`6e60de8a…` 일치로 확인). 다만 **통합 JSON 재생성은 맥 raw가 필요**하고 이 윈도우 호스트에는 맥 raw가
없으므로, 저장소의 `unified-v1.json`은 맥 raw가 있는 lane에서 재생성될 때까지 라벨이 교정되지 않은
채로 남는다. 재생성 명령은 `scripts/analyze_m4_5_unified.py`(맥 glob + 윈도우 roll-up 입력).

### 외부 백업 후보 (사람 게이트 — 결정 아님, 제안만)

외부 백업 **위치·수단 결정은 사람 게이트**다(안전경계·연구 불변식). 아래는 용량과 절차만 제시한다.

1. **암호화 압축본을 팀 공유 드라이브에 보관.** 용량: win raw gzip -9 약 2.68 MiB(+ mac raw는 이
   호스트에서 측정 불가). 절차: `tar -C ~/inodefence-evidence -cf - . | gzip -9`를 age/gpg로 암호화해
   업로드하고, 압축본 SHA-256와 대상 manifest commit을 저장소에 한 줄로 기록.
2. **GitHub Release asset으로 첨부.** 용량: asset당 2 GiB 한도에 한참 못 미침. 절차: 같은 암호화
   압축본을 태그된 release에 첨부하고 asset SHA-256·release 태그를 저장소에 기록. 공개 저장소면 raw가
   공개되지 않도록 암호화 필수.

[인프라 검증 v1](infrastructure-readiness-v1.md)은 실행 전 provenance/config 도입 이후의
engineering audit와 reference semantic repeat를 기록한다. Node benchmark/evaluation 결과가 아니다.

[Native entry-transition observation qualification v2](node-transition-observation-qualification-v2.md)는
pinned node-tar의 public event, inotify, strace와 prefix replay 후보를 benign Linux fixture로
검증한 **QUALIFIED FAIL** 기록이다. Native P0/P1/P2 효과 평가 결과가 아니다.

[libarchive entry-boundary qualification v1](libarchive-entry-boundary-qualification-v1.md)은
별도 public write-disk reference target의 `archive_write_finish_entry()` 이후에도 directory
metadata가 final close까지 지연됨을 검증한 **QUALIFIED FAIL** 기록이다.

[node-tar internal completion qualification v3](node-internal-completion-qualification-v3.md)는
source-guarded private completion callback의 entry association, effect-completion order,
callback-time snapshot consistency와 stock 대비 overhead를 검증한 **QUALIFIED FAIL** 기록이다.
정확한 marker association을 native archive-ordered transition producer로 승격하지 않는다.

[node-tar causal filesystem-effect qualification v4](node-causal-effect-qualification-v4.md)는
async-context와 Node `fs` completion을 사용해 operation을 exact entry에 귀속하고 independent
work의 later-ordinal effect가 earlier completion보다 먼저 실제로 완료됨을 검증한
**QUALIFIED FAIL** 기록이다. Effect event는 complete checkpoint나 P0/P1/P2 결과가 아니다.

[node-tar native effect observation qualification v2](node-native-effect-observation-qualification-v2.md)는
WSL trusted broker에서 Gate 3 10개 검사와 Gate 4 480회를 실행하고 raw evidence를 독립적으로
재검증한 기록이다. Required replacement coverage가 실패해 정확한 판정은
**`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`**이며 native campaign은 계속 차단된다.
