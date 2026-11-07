# exp3-sizing-20261107: 파일럿 입력으로 낸 EXP-3 검정력

**계획 입력이며 결과가 아니다.** 어떤 값도 EXP-2·EXP-3의 효과 추정이나 가설 판정이 아니고, 확증 검정력 확보를 뜻하지 않는다. n 결정은 지웅 몫이다(D7). 이 폴더는 #263의 `exp3-sizing-20261105`를 대체한다. 그 값은 파일럿 전 가정(`R=D=0`)에 기댄다.

## 결과

| n/arm | 두 대비 동시 기각 검정력 (seed 20261107) | 표준오차 | 다른 seed 20261108 |
| --- | --- | --- | --- |
| 70 | .760 | .015 | .771 |
| 76 | .809 | .014 | .826 |
| 82 | .825 | .013 | .846 |
| 88 | .882 | .011 | .876 |
| 120 | .973 | .006 | .959 |

80% 검정력은 이 격자에서 n=76 부근이다(70은 두 seed 모두 미달, 76은 두 seed 모두 도달). 격자 간격과 표준오차보다 정밀하게 읽지 않는다.

- **입력:** p_S .670, p_R .413(R-restart), p_D .401, abort .275, abort 시점은 파일럿 11건에서 재표집. 출처는 [결과 메모](../../summaries/exp3-hazard-pilot-v1-result.md) §3.
- **검정:** 합동 2-arm 로그랭크, seed 블록 내 라벨 순열, 두 대비, Holm 패밀리 α .05, S-u 쪽.
- **가정:** 일정 hazard, 블록 안 arm 독립. p 입력은 점추정이고 구간이 넓다(S-u 양측 .262–.878). train 7.5.2 hazard가 holdout에 전이된다는 것은 미검증이다.
- **규칙 C와의 관계:** 파일럿 규칙 C 기계 출력(n 114)은 부호검정 근사이고 소급 변경하지 않는다. 이 값은 그 판정을 바꾸지 않는다(어느 값에서도 "가능").

## 대조

W3 명령을 그대로 재실행했다(W2, 2026-11-07 10:37 KST, 67.7 s, 다른 컨테이너 0).

```text
timeout 590 nice -n 15 /usr/bin/python3 -I exp3_power_registered.py permutation --sims 800 --perms 1000 --n 70 76 82 88 120
```

Python 3.12.3, numpy 1.26.4, seed 기본값 20261107. 스크립트는 증거 폴더 복사본(sha256 `5f02b06b54489d3d2a9e64a08c3565fcc42b769c2b96f55bf97595f26dc622c6`)이다.

| n | W3 (`run-w3-original.log`) | W2 재실행 (`run.log`) | 일치 |
| --- | --- | --- | --- |
| 70 | .760 | .760 | 예 |
| 76 | .809 | .809 | 예 |
| 82 | .825 | .825 | 예 |
| 88 | .882 | .882 | 예 |
| 120 | .973 | .973 | 예 |

**이 대조가 말하는 범위.** 같은 코드와 seed이므로 결정론을 확인할 뿐 모형의 옳음을 확인하지 않는다. 그래서 두 가지를 더 했다.

1. **다른 seed**(`run-seed-20261108.log`): 차이 최대 .021(n=82). 모든 n에서 합성 표준오차의 2배 안이라 몬테카를로 오차 수준이다.
2. **등록 통계량과 대조**(`check_stat_vs_registered.py`, `check-stat.log`): 같은 데이터 300벌(n=76)을 저장소의 `seed_block_logrank_permutation`에 넣었다. 시간 동률이 없을 때 통계량 차이 최대 7.11e-14, p 값 차이 중앙값 .0010. 정수 T_first 형태(동률 있음)에서는 통계량 차이 중앙값 4.63e-03이다. p ≤ .05 판정은 300벌 중 262 대 263으로, 이 대비(S-u 대 R) 하나만 본 값이다. 이 검사는 W2가 추가했고 W3 원 실행에는 없다.

스크립트의 p 값은 분자·분모에 1을 더한다. 등록 함수는 더하지 않는다. 순열 1000개에서 영향은 작다.

**격자.** `/usr/bin/python3 -I exp3_power_registered.py grid`(같은 환경, 기본 seed)의 7줄이 W3가 전한 값과 정확히 일치한다. 격자는 χ² 근사(시나리오·n 조합당 8000회)이고 a=.43 칸은 지수 abort 모형이다. 위 순열 표와 같은 값으로 읽지 않는다.

## 파일

| 파일 | 내용 |
| --- | --- |
| `exp3_power_registered.py` | W3 검정력 스크립트 |
| `run.log`, `run-seed-20261108.log`, `run-w3-original.log` | 실행 로그 |
| `results.json` | 위 표 |
| `run-grid.log` | 시나리오 격자(n=94, 120, 150; 뒤쪽은 a=.43). `grid` 모드는 **χ² 근사**이고 순열 검정이 아니다 |
| `check_stat_vs_registered.py`, `check-stat.log` | 등록 통계량 대조 |
| `rule_c_pair_riskset.py` | 결과 메모 §3 참고값(n 120, 32) |
| `pilot_fixed_section.py`, `pilot_w3_items.py` | 결과 메모 §4·§5·§6 수치의 산출 |
| `analysis-sha256.txt` | 증거 `~/inodefence-evidence/exp3-hazard-pilot-20261106/analysis/` 전체 목록 (14개) |

**사본 차이.** 저장소 `.py`에는 lint·format 면제 주석 3줄이 맨 앞에 있고, 나머지는 증거 폴더 원본과 byte 동일하다. 확인: `tail -n +4 <파일> | sha256sum`이 `analysis-sha256.txt`의 값과 같다(`check_stat_vs_registered.py`는 이번에 만든 것이라 목록에 없다).

**재현 한계.** `pilot_*.py`는 이 호스트의 증거 경로를 고정해 읽는다. raw와 `analysis/`는 저장소에 없으므로 다른 호스트에서는 다시 돌릴 수 없다. raw 무결성은 [manifest](../../summaries/raw-manifest-exp3-hazard-pilot-v1.sha256)로 확인한다. `rule_c_pair_riskset.py`는 파일럿 게이트 SHA 체크아웃과 `pilot-report.json`이 필요하다. 결과 메모 본문은 `make_result_memo.py`(증거 `analysis/`)로 생성한 뒤 이후 수정을 직접 반영했으므로, 그 스크립트의 출력과 현재 메모는 다르다. `analysis/`의 산출물은 #267 시점 값이고 이 PR에서 다시 만들지 않았다.
