# InodeFence 소개 영상 대본

**범위.** 구현된 기능을 실제 실행 기록으로 보여 주는 영상이다. 가설을 지지한다고 주장하지 않는다. 핵심 RQ는 미판정이고
EXP-3·EXP-2 결과는 없다.

**길이.** 서식 기준은 5분 이내다(붙임1 표 3 ②). 본편 배정은 4:55이고 낭독 길이는 실측 전이다.

## 실행 기록

터미널 장면은 새로 실행하지 않고 W2 기록을 재생한다. 기록은 `~/inodefence-evidence/demo-recordings-20261107/`에 있고
(README, `SHA256SUMS`), main `f36a1ce`에서 2026-11-07 13:24–13:25 KST에 각 장면을 1회 실행한 `demo run`이다. 결과 주장이 아니다.

```bash
scriptreplay --log-timing sceneN-take1.timing --log-out sceneN-take1.typescript
```

| 장면 | 파일 | 재생 길이 | 배정 | 기대 출력 |
| --- | --- | --- | --- | --- |
| 3 | `scene3-take1.*` | 0.14 s | 0:35 | fixture 4종 모두 `(expected)` |
| 4 | `scene4-take1.*` | 34.49 s | 1:10 | `steps=20`, `oracle violations: 0`, `PASSED` |
| 5 | `scene5-take1.*` | 4.69 s | 0:50 | `IDENTICAL` |
| 7 | `scene7-take1.*` | 1.12 s | 0:35 | `verify OK: 66 ok`, EXP-0 표 |

**편집 규칙.**

1. 재생 장면마다 자막 "실행 기록 재생(2026-11-07)"을 넣는다.
2. 출력 내용을 편집으로 고치지 않는다. 시간은 정지 화면과 스크롤로 채운다. 재생 속도를 바꾸면 자막에 배속을 적고, 잘라내면 잘라낸 구간을 표시한다.
3. `typescript`를 `cat`으로 보여 주지 않는다. 1행의 내부 세션 경로가 나온다. `scriptreplay` 출력에는 머리 줄과 끝 줄이 없음을 확인했다(4장면 모두 0건).
4. 숫자 자막은 W3 검증 뒤 확정한다. 편집본은 W4가 검수한다.
5. 렌더링 판을 기본으로 쓰고, 사람이 Windows 터미널 창을 녹화하면 그것으로 교체한다. 자막은 같다.

**쓰지 않는 화면.** 생존 곡선, dense 신호, 파일럿 콘솔, 벤치마크 raw. M3 그림은 2026-11-06에 재렌더한 판만 쓴다(제목이 "name-acquisition
condition"인 판). 그 전 판은 철회한 인과 문구를 담고 있다.

## 본편

### 장면 1 (0:00–0:25) 제목과 범위

- **화면:** 제목 슬라이드 "InodeFence: TAR 추출 경계위반 탐색 프로토타입" + 자막 "구현 시연 · 가설 검정 결과 아님".
- **내레이션:** InodeFence는 TAR 추출의 보안 경계위반을 탐색하는 연구 프로토타입입니다. 이 영상은 지금까지 구현한 기능을
  실행 기록으로 보여 줍니다. 핵심 가설의 검정 결과는 아직 없습니다.

### 장면 2 (0:25–1:00) 문제와 판정 기준

- **화면:** 슬라이드 2장. 하드링크로 inode를 공유하는 관계, C0/C1/C2 정의(`docs/research/design/security-contracts.md`).
- **내레이션:** 아카이브의 하드링크 하나로, 추출된 객체가 폴더 밖 파일과 같은 inode를 공유할 수 있습니다. 경로 문자열만
  보면 놓칠 수 있는 관계입니다. 그래서 세 규칙으로 판정합니다. C0은 추출 폴더 밖의 경로 변화, C1은 보호 대상과의 inode
  공유, C2는 보호 대상의 내용이나 메타데이터 변화입니다. 판정 조건에 CVE 번호나 릴리스 번호는 없습니다.

### 장면 3 (1:00–1:35) Oracle 판정 확인

- **기록한 명령:**

  ```bash
  PYTHONPATH=src python3 -m scripts.oracle_fixture_check
  ```

- **기대 출력** (`dev:ino` 값은 실행마다 다르다):

  ```text
  [controlled oracle check (not node-tar)] extractor=controlled-unchecked-extractor ...
  fixture normal: ...  C0/C1/C2 모두 not violated (expected)
  fixture c0: ...      C0: VIOLATED (expected)
  fixture c1: ...      C1: VIOLATED (expected)  C2: VIOLATED (expected)
  fixture c2: ...      C2: VIOLATED (expected)
  ```

- **내레이션:** 먼저 판정기를 확인합니다. 이 extractor는 경계 검사를 일부러 뺀 통제용 코드이고 node-tar 결과가 아닙니다.
  정상 입력은 위반이 없고, 나머지 세 fixture는 기대한 규칙에서 위반으로 나옵니다. 판정이 fixture와 일치한다는 것만
  보여 줍니다.

### 장면 4 (1:35–2:45) 실제 node-tar 루프 (M1, TESTED)

- **화면:** 구성도 슬라이드(`paper/figures/system-architecture.png`), 이어서 실행 기록 재생.
- **기록한 명령:**

  ```bash
  SKIP_BUILD=1 INODEFENCE_EVIDENCE_DIR=/tmp/inodefence-video make demo
  ```

- **기대 출력** (끝부분):

  ```text
  step 20/20  duplicate_entry  success  ...  C0 ok C1 ok C2 ok  new-keys 2  reward 1  corpus 6->7  weight duplicate_entry 1->2
  demo summary: producer=native steps=20 label='demo run' node-tar=7.5.22
    termination: rejected 2, success 18
    oracle violations: 0 (C0 0, C1 0, C2 0)
    feedback: unique effect keys 25, reward steps 6,13,20, retained corpus 7 (initial 4)
    final weights: add_entry 3, duplicate_entry 2 (others 1)
  PASSED: node-tar demo (context=default)
  ```

- **내레이션:** 다음은 실제 node-tar 7.5.22의 실행 기록입니다. seed 123, budget 20입니다. 명령 하나로 입력 생성, 실행, entry별
  상태 관찰, 판정, 피드백, 다음 mutation 선택이 이어집니다. 각 줄이 한 번의 실행이고, 스무 번 모두 C0, C1, C2 위반은 없습니다.
  위반 0은 안전성을 뜻하지 않습니다. 새 상태 키가 나오면 그 입력을 corpus에 남기고 해당 연산의 가중치를 올립니다. 이것은
  피드백이 다음 선택에 연결된다는 동작 확인입니다. 탐색 성능을 뜻하지 않고, 취약점 발견을 주장하지도 않습니다.

### 장면 5 (2:45–3:35) 통제 재현 (M2, TESTED)

- **화면:** 실행 기록 재생, 이어서 `paper/figures/m2-cross-release-evidence.png`.
- **기록한 명령:**

  ```bash
  python3 experiments/repro/cross_release_identity.py --out /tmp/inodefence-video/repro
  jq '.releases | map_values(.verdict | {outcome, nlink_before, nlink_after, reason})' /tmp/inodefence-video/repro/toplevel_hardlink.json
  diff /tmp/inodefence-video/repro/summary.json experiments/repro/evidence/summary.json && echo IDENTICAL
  ```

- **기대 출력:**

  ```text
  "toplevel_hardlink": { "fixed_pair": ["7.5.2","7.5.3"], "boundary_ok": true, ... }
  "nested_hardlink":   { "fixed_pair": ["7.5.6","7.5.7"], "boundary_ok": true, ... }
  "7.5.2": { "outcome": "resolved", "nlink_before": 1, "nlink_after": 2, "reason": null }
  "7.5.3": { "outcome": "declined", ..., "reason": "TAR_ENTRY_ERROR: linkpath contains '..'" }
  IDENTICAL
  ```

- **내레이션:** 다음은 통제 재현의 실행 기록입니다. 손으로 만든 하드링크 fixture 두 개를 node-tar 릴리스 다섯 개에 넣었습니다.
  최상위 fixture에서 7.5.2는 외부 참조 파일과 inode를 공유하고 nlink가 1에서 2로 늘어납니다. 7.5.3은 거부합니다. 중첩
  fixture는 7.5.6이 공유하고 7.5.7이 거부합니다. 판정 조건에 릴리스 번호나 정답 경로는 없습니다. 고정 쌍과 CVE의 대응은
  추론이고, 이것은 퍼저가 스스로 찾은 결과가 아닙니다.

### 장면 6 (3:35–4:05) 자력 발견의 현재 판정 (M3)

- **화면:** Ledger 문구(`docs/STATUS.md`, main `f36a1ce`)를 인용한 슬라이드와 `paper/figures/m3-blind-ablation.png`(재렌더 판). STATUS를 고쳐도 영상이 바뀌지 않도록 명령 출력 대신 슬라이드로 인용한다.
- **내레이션:** 퍼저의 자력 발견에 대한 현재 판정은 Ledger 문구 그대로, 이름 획득 조건의 관찰, 피드백 인과 미입증입니다.
  외부 객체 이름을 어휘에 넣은 조건에서 자율 C1이 관찰됐지만, 이 대조는 어휘(이름 포함 여부)를 달리한 것이라 피드백의 효과로 읽지
  않습니다. blind 발견도 아닙니다.

### 장면 7 (4:05–4:40) EXP-0 인프라 측정

- **기록한 명령:**

  ```bash
  python3 scripts/make_raw_manifest.py --verify experiments/summaries/raw-manifest-win-20261105-20261105.sha256 --root ~/inodefence-evidence/exp0-20261105
  sed -n '/^# EXP-0 pilot infrastructure measurement$/,/^Summed/p' experiments/summaries/exp0-20261105-report.md
  ```

- **기대 출력:**

  ```text
  verify OK: 66 ok, 0 mismatched, 0 missing, 0 extra (root .../exp0-20261105)
  # EXP-0 pilot infrastructure measurement
  Cells: 15 (valid 15, invalid 0) | arms: D, R, S-u | seeds: 5
  _Infrastructure measurement only; not an H-A test, not an effectiveness claim._
  | D | 5 | 5 | 0 | 0 | 0.000 |  (R, S-u도 같음)
  Pooled p95: 1.5489997629993013 s over 3000 steps.
  Summed: 2428.1045209054023 exec/h over 3000 executions.
  ```

  공식 리포트(#268)의 생성기 출력 원문이다. 편차 11건은 같은 파일 §3에 있다.
- **자막:** "화면 값 = monotonic clock 기록값. `Summed 2428`은 스트림당 값. 실시간 환산: p95 1.419 s · 호스트 집계 약 4760 exec/h (실시간 기준,
  장기 편차 검증 중)".
- **내레이션:** 이어서 EXP-0 등록 실행의 증거입니다. 세 arm, seed 다섯 개, budget 200의 15셀을 모두 완주했고 abort는 0입니다.
  C1과 C2 hit도 0인데, 사전등록에서 기본 결과로 예상한 값입니다. 화면의 시간과 처리량은 기록값이고, 자막이 실시간 환산값입니다.
  당시 이 호스트의 clock이 실제보다 빠르게 갔기 때문입니다. 인프라 측정이며 가설 검정이 아닙니다.

### 장면 8 (4:40–4:55) 본실험과 맺음

**최종 실험값 반영 대기.** 등록 실행과 W3 검증이 끝나면 이 장면의 화면과 내레이션을 그 값으로 다시 쓴다. 결과가 없으면 아래 판을 쓴다.

- **화면:** 본실험 구조 슬라이드(탐색용 EXP-3 → 확증용 EXP-2, "최종 실험값 반영 대기"), 끝에 출처 문구 "본 결과물은 상명대학교 대학혁신지원사업비의 지원을 받아 제작되었습니다."
- **내레이션:** 본실험은 탐색용 EXP-3과 확증용 EXP-2로 나뉘고, 결과는 아직 반영되지 않았습니다. 탐색 파일럿 40캠페인은 설계
  입력일 뿐 우위의 근거가 아닙니다. 감사합니다.

## 말하지 않는 것

- 피드백이 무작위나 커버리지보다 빠르다거나 많이 찾는다는 말.
- M3를 인과나 입증으로 부르는 말. 표현은 "이름 획득 조건의 관찰(피드백 인과 미입증)" 그대로 쓴다.
- 선행연구 대비 우선권이나 참신성을 단정하는 말.
- 새 상태 키 수나 dense 신호를 효과의 근거로 드는 말(EN-008).
- `make demo`의 위반 0을 node-tar의 안전성으로 읽는 말.
- EXP-0의 기록값(1.549 s, 2428 exec/h)을 실시간 값이나 호스트 전체 처리량처럼 읽는 말.
- docker events 발췌를 "데몬 정지"나 원인으로 읽는 말. 파일럿의 S-u 사건 수를 우위로 읽는 말.
- 장면 4의 실행 시간("약 34초").
