# exp3-sizing-20261105 — EXP-3 규모(n, x) 산정 입력

**사전등록 계획 입력이며 결과가 아니다.** 레인 6(Evaluation), 2026-11-05. EXP-3 사전등록 초안
`experiments/preregistration/exp3-v1.md`의 "규모 산정 입력" 절·EXP-2 GO/NO-GO 제안값의 출처다. 이 폴더의
어떤 수치도 EXP-3/EXP-2의 효과 추정이나 가설 판정 입력이 아니며, EXP-0의 hit는 hazard 추정에 쓰지 않았다
(exp0-pilot-v2 (a)).

## 분석 코드

- `compute.py` → `sizing.json`. 사용 모듈 `inodefence.evaluation.power` · `inodefence.evaluation.survival` =
  **stack-E head `f655f18`**(`origin/claude/s3-exp0-confirmatory-direction`, #257 스택, **미머지**). main에는
  아직 두 모듈이 없다. **스택이 머지되면 머지된 코드로 다시 생성**하고 이 폴더를 갱신한다.
- 고정 seed(MC 검증 `20261105 + k`, 등가성 검사 `7`), 400 sims/point, 실행 시간 465 s(`run.log`).
- 실행 당시 배치: `<S>/exp3-sizing/compute.py` + `<S>/exp0-analysis-f655f18`(f655f18 worktree). 스크립트는
  자기 디렉터리의 **상위**에서 `exp0-analysis-f655f18/src`를 `sys.path`에 넣는다. 재현(머지 전):
  `git worktree add <S>/exp0-analysis-f655f18 f655f18`, `compute.py`를 `<S>/exp3-sizing/`에 두고
  `nice -n 10 .venv/bin/python -I <S>/exp3-sizing/compute.py` → 같은 폴더에 `sizing.json`. 입력 파일
  (아래 [E0]·[E0r]·[K])은 `~/inodefence-evidence/` 호스트 로컬이다(저장소에 없음).
- 사본 차이(관찰): `compute.py`는 원본(sha256 `462c84c2f23d7e93dc24667513acb66fdaa8bb760e5bfa7479862eaea0fe69bb`,
  `~/inodefence-evidence/exp3-sizing-20261105/compute.py`와 동일)에 저장소 lint/format 면제 주석 3줄
  (`# ruff: noqa`, `# fmt: off` 포함)을 shebang 다음(2~4행)에 추가한 것뿐이다 — 나머지 줄은 바이트 동일, `ast.dump` 동일.
  `report.md`는 원본(sha256 `56752b4d587734ae9a5ac2bcfc9daaaf3d0c4ddf5852f4cf4a391e17f083da84`)의 26행
  `[D3](d)`를 `[D3] (d)`로만 바꿨다(docs 링크 검사가 `(d)`를 로컬 링크로 읽음). `sizing.json`·`run.log`는
  원본·`~/inodefence-evidence/exp3-sizing-20261105/` 사본과 sha256 동일.

## 출처 (report.md와 동일 표기)

[E0] EXP-0 report JSON (`~/inodefence-evidence/exp0-20261105-analysis-premerge/exp0-report-premerge.json`);
[E0r] EXP-0 cell summaries + `.log` mtimes (`~/inodefence-evidence/exp0-20261105/`);
[M3] `experiments/summaries/m3-powered-matched-verdict-v2.json`;
[K] sentinel-count reach study (`sentinel-k-reach-20261104/kscale_raw.txt`, `~/inodefence-evidence/` 아래);
[L4] `wp-throughput-20261104/SUMMARY.md` (`~/inodefence-evidence/` 아래);
[D3] `origin/claude/s3-exp3-prereg-skeleton@bda2f3d:experiments/preregistration/exp3-v1.md`;
[ST] `docs/STATUS.md:312-324`.
"Observed" = read from evidence; "Inferred" = model output.

## 세 가지 주의 (report.md 원문 그대로)

1. **2428 exec/h is a per-stream rate.** [E0] "summed" wall (4448 s) sums per-cell walls; `.log` mtimes show pairs ran concurrently → real jobs-2 throughput ≈ **4740 exec/h** (elapsed 2278 s), consistent with lane-4's 1.79× speedup. Doubles n only on a quiet exclusive host (lane 4 measured 3.09× host-state slowdown). Per-step cost at 2000 steps is extrapolated (no drift within 200).
2. **The hazard has never been measured.** Every S-u anchor rests on one M3 hit (one sentinel, C1 only, older engine, A3full adaptive ≈ S-a), scaled by the in-process reach ratio (inferred). Holdout hazard unknown, yet it is the only confirmatory family ([D3] :209/:345). EXP-0's 0/15 aborts at budget 200 do not bound aborts at 2000 (M3: 24/60).
3. **x must be counted in first-event units; GO at n=20 is noisy.** Item-7 proxy counts hit steps: M3 A3full 66/47263 = 1.4×10⁻³ vs 2 first events (4.2×10⁻⁵) → 33× inflated. With n=20, crossing x=0.032 needs only 2 S-u events: P(GO) = 0.33 / 0.70 / 0.81 under k=1/3/5. Registered prediction HR=2 assumes D=R and is untestable under the R-floor evidence (sign test: unattainable for n ≤ 75; Schoenfeld n=94 would need R to hit 31% of campaigns).

## 파일

| 파일 | 내용 |
| --- | --- |
| `report.md` | 산정 보고(표·판정, inferred 라벨) |
| `compute.py` | 산정 스크립트(위 사본 차이) |
| `sizing.json` | 전체 격자 산출(처리량·검정력·민감도·MC 검증·planning_derivations) |
| `run.log` | 실행 로그(MC 검증 8점, `done 465.4 s`) |
