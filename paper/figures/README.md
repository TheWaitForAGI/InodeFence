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

`make demo` 끝 화면 [`make-demo-screen.png`](make-demo-screen.png)은 2026-11-07 `script` 기록을 그대로 그린 실행 기록 재생이고 새 실행이 아니다. 생성 소스: [`render_make_demo_screen.py`](render_make_demo_screen.py). 이 스크립트는 Pillow가 필요하고 개발 의존성 밖이다.

## 렌더된 그림 (observed only)

| 그림 | PNG | 생성 소스 | 데이터 근거(observed) |
| --- | --- | --- | --- |
| M2 cross-release verdict | [`m2-cross-release-evidence.png`](m2-cross-release-evidence.png) | [`render_m2_cross_release.py`](render_m2_cross_release.py) | [표 M2](../tables/m2-cross-release-evidence.md), [raw summary.json](../../experiments/repro/evidence/summary.json) |
| EXP-0 결합 T_first (인프라 측정) | [`exp0-survival.png`](exp0-survival.png) | [`render_exp0_survival.py`](render_exp0_survival.py) | [표 EXP-0](../tables/exp0-summary.md), [공식 리포트 JSON](../../experiments/summaries/exp0-20261105-report.json) |

두 그림은 **observed 수치만** 쓴다(M2는 스크립트가 수치를 하드코딩, EXP-0은 리포트 JSON을 읽음; 추측 없음). EXP-0 그림은 전 arm 사건 0이라
세 곡선이 S(t)=1에 겹쳐 맨 위 S-u만 보이며, arm 비교가 아니다. EXP-0은 `--report` 경로로 직접 실행한다. 렌더는 `make check` 밖의
ephemeral matplotlib 환경에서 하며, 각 스크립트 docstring의 명령으로 재생성한다.
