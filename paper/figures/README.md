# 논문 Figure

논문에 사용할 architecture figure와 검증된 실험 figure를 둔다.

정량 figure는 가능하면 다음 경로를 역추적할 수 있어야 한다.

```text
Figure
  ↓
analysis input
  ↓
experiment result
  ↓
experiment config
  ↓
InodeFence commit / target version
```

설명용 개념도와 측정 결과 그래프를 구분한다.

## 렌더된 그림 (observed only)

| 그림 | PNG | 생성 소스 | 데이터 근거(observed) |
| --- | --- | --- | --- |
| M2 cross-release verdict | [`m2-cross-release-evidence.png`](m2-cross-release-evidence.png) | [`render_m2_cross_release.py`](render_m2_cross_release.py) | [표 M2](../tables/m2-cross-release-evidence.md), [raw summary.json](../../experiments/repro/evidence/summary.json) |
| M3 blind-ablation | [`m3-blind-ablation.png`](m3-blind-ablation.png) | [`render_m3_blind_ablation.py`](render_m3_blind_ablation.py) | [표 M3](../tables/m3-blind-ablation.md), [자력발견 요약](../../experiments/summaries/node-self-discovery-mechanism-v1.md) |

두 그림은 **observed 수치만** 쓴다(스크립트가 수치를 하드코딩, 추측 없음). 렌더는 `make check` 밖의
ephemeral matplotlib 환경에서 하며, 각 스크립트 docstring의 명령으로 재생성한다. PENDING 소절
(Results §5.3.3 rate · §5.4.3 decompress powered)의 그림은 네이티브 결과 착지 후 후속으로 추가한다.
