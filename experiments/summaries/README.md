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

[인프라 검증 v1](infrastructure-readiness-v1.md)은 실행 전 provenance/config 도입 이후의
engineering audit와 reference semantic repeat를 기록한다. Node benchmark/evaluation 결과가 아니다.

[Native entry-transition observation qualification v2](node-transition-observation-qualification-v2.md)는
pinned node-tar의 public event, inotify, strace와 prefix replay 후보를 benign Linux fixture로
검증한 **QUALIFIED FAIL** 기록이다. Native P0/P1/P2 효과 평가 결과가 아니다.

[libarchive entry-boundary qualification v1](libarchive-entry-boundary-qualification-v1.md)은
별도 public write-disk reference target의 `archive_write_finish_entry()` 이후에도 directory
metadata가 final close까지 지연됨을 검증한 **QUALIFIED FAIL** 기록이다.
