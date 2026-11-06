# InodeFence 시연 영상 대본 (초안)

**범위.** 구현된 기능을 실제 명령으로 보여 주는 영상이다. 가설을 지지한다고 주장하지 않는다. 핵심 RQ는 미판정이고
EXP-3 결과는 없다.

**길이.** 본편 4:55. 확장 장면 4개를 넣으면 6:55다. 이전 세션이 붙임에서 옮겨 적은 기록은 소개영상 5분 이하이고, 작업
지시는 5–7분이다. **서식을 대조(UNVERIFIED)해 길이를 정하기 전까지는 5분 안에 드는 본편을 기본으로 한다.**

## 명령 검증 기록

호스트: WSL2 x86_64, Docker 29.8.0, Python 3.12.3, main `23e5c66`. 검증일: 2026-11-06. 소요 시간은 이 호스트 clock 기준의
대략값이다(이 clock은 실제보다 빠르게 간다).

| 장면 | 명령 | 결과 |
| --- | --- | --- |
| 3 | `PYTHONPATH=src python3 -m scripts.oracle_fixture_check` | exit 0, fixture 4종 모두 `(expected)` |
| 4 | `SKIP_BUILD=1 INODEFENCE_EVIDENCE_DIR=... make demo` | exit 0, 약 34초, `PASSED: node-tar demo` |
| 5 | `python3 experiments/repro/cross_release_identity.py --out ...` | exit 0, 약 5초, `summary.json`이 저장소 raw와 동일 |
| 7 | `python3 scripts/make_raw_manifest.py --verify ... --root ...` | exit 0, `66 ok, 0 mismatched, 0 missing, 0 extra` |
| 6, 7, E1–E4 | `grep`, `sed`, `jq` 표시 명령 | 출력 확인 |

**검증하지 않은 것.** `SKIP_BUILD=1` 없는 `make demo`(이미지 재빌드 포함)는 이번에 돌리지 않았다. 공유 태그
`inodefence-controller:local` 등을 다시 만들기 때문이다. 이 호스트에서 통과한 이전 기록은 LOG 10/27에 있다.

## 녹화 전 준비 (화면 밖)

1. **EXP-3 등록 실행 중에는 녹화하지 않는다.** 처리량 측정이 호스트 상태에 민감하고 등록 실행 중에는 호스트를 동결한다.
2. `docker info`에서 엔진을 확인한다. native dockerd가 소켓을 잡으면 `make demo`가 격리 정책 검사에서 실패할 수 있다.
3. 이미지를 확인한다: `docker images inodefence-node-tar-effect`에 7.5.2, 7.5.3, 7.5.6, 7.5.7, 7.5.8이 있어야 한다. 없는
   릴리스만 아래처럼 빌드한다. **7.5.2는 동결 이미지이므로 다시 빌드하지 않는다.**

   ```bash
   BUILDX_NO_DEFAULT_ATTESTATIONS=1 docker build -q -f tools/node-tar/effect/Dockerfile \
     --build-arg TAR_VERSION=7.5.3 -t inodefence-node-tar-effect:7.5.3 .
   ```

4. PR #262가 머지되어 매니페스트가 저장소에 있어야 한다. 머지 전이면 장면 7을 찍지 않는다.
5. 이 호스트에는 `python`이 없다. 대본의 `python3`를 그대로 쓴다.
6. 터미널 글꼴을 키우고, 프롬프트와 환경변수에 토큰이나 개인정보가 보이지 않는지 확인한다.
7. 찍기 전에 `rm -rf /tmp/inodefence-video`로 이전 결과를 지운다(장면 4와 E1의 파일 glob이 1개만 잡히도록).

**쓰지 않는 화면.** 생존 곡선과 dense 신호는 올리지 않는다. M3 그림은 2026-11-06에 재렌더한 판만 쓴다(제목이 "name-acquisition
condition"인 판). 그 전 판은 철회한 인과 문구를 담고 있다.

## 본편

### 장면 1 (0:00–0:25) 제목과 범위

- **화면:** 제목 슬라이드 "InodeFence: TAR 추출 경계위반 탐색 프로토타입" + 자막 "구현 시연 · 가설 검정 결과 아님".
- **내레이션:** InodeFence는 TAR 추출의 보안 경계위반을 탐색하는 연구 프로토타입입니다. 이 영상은 지금까지 구현한 기능을
  실제 명령으로 보여 줍니다. 핵심 가설의 검정 결과는 아직 없습니다.

### 장면 2 (0:25–1:00) 문제와 판정 기준

- **화면:** 슬라이드 또는 `docs/research/design/security-contracts.md`의 C0/C1/C2 정의.
- **내레이션:** 아카이브의 하드링크 하나로, 추출된 객체가 폴더 밖 파일과 같은 inode를 공유할 수 있습니다. 경로 문자열만
  보면 놓칠 수 있는 관계입니다. 그래서 세 규칙으로 판정합니다. C0은 추출 폴더 밖의 경로 변화, C1은 보호 대상과의 inode
  공유, C2는 보호 대상의 내용이나 메타데이터 변화입니다. 판정 조건에 CVE 번호나 릴리스 번호는 없습니다.

### 장면 3 (1:00–1:35) Oracle 판정 확인

- **명령:**

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

- **명령:**

  ```bash
  SKIP_BUILD=1 INODEFENCE_EVIDENCE_DIR=/tmp/inodefence-video make demo
  ```

- **기대 출력** (약 34초, 끝부분):

  ```text
  step 20/20  duplicate_entry  success  ...  C0 ok C1 ok C2 ok  new-keys 2  reward 1  corpus 6->7  weight duplicate_entry 1->2
  demo summary: producer=native steps=20 label='demo run' node-tar=7.5.22
    termination: rejected 2, success 18
    oracle violations: 0 (C0 0, C1 0, C2 0)
    feedback: unique effect keys 25, reward steps 6,13,20, retained corpus 7 (initial 4)
    final weights: add_entry 3, duplicate_entry 2 (others 1)
  PASSED: node-tar demo (context=default)
  ```

- **내레이션:** 이제 실제 node-tar 7.5.22로 루프를 돌립니다. 명령 하나로 입력 생성, 실행, entry별 상태 관찰, 판정, 피드백,
  다음 mutation 선택이 이어집니다. 각 줄이 한 번의 실행이고, 스무 번 모두 C0, C1, C2 위반은 없습니다. 새 상태 키가 나오면
  그 입력을 corpus에 남기고 해당 연산의 가중치를 올립니다. 이것은 피드백이 다음 선택에 연결된다는 동작 확인입니다. 탐색
  성능을 뜻하지 않고, 취약점 발견을 주장하지도 않습니다.

### 장면 5 (2:45–3:35) 통제 재현 (M2, TESTED)

- **명령:**

  ```bash
  python3 experiments/repro/cross_release_identity.py --out /tmp/inodefence-video/repro
  jq '.releases | map_values(.verdict | {outcome, nlink_before, nlink_after, reason})' /tmp/inodefence-video/repro/toplevel_hardlink.json
  diff /tmp/inodefence-video/repro/summary.json experiments/repro/evidence/summary.json && echo IDENTICAL
  ```

- **기대 출력** (약 5초):

  ```text
  "toplevel_hardlink": { "fixed_pair": ["7.5.2","7.5.3"], "boundary_ok": true, ... }
  "nested_hardlink":   { "fixed_pair": ["7.5.6","7.5.7"], "boundary_ok": true, ... }
  "7.5.2": { "outcome": "resolved", "nlink_before": 1, "nlink_after": 2, "reason": null }
  "7.5.3": { "outcome": "declined", ..., "reason": "TAR_ENTRY_ERROR: linkpath contains '..'" }
  IDENTICAL
  ```

- **내레이션:** 다음은 통제 재현입니다. 손으로 만든 하드링크 fixture 두 개를 node-tar 릴리스 다섯 개에 넣습니다. 최상위
  fixture에서 7.5.2는 외부 참조 파일과 inode를 공유하고 nlink가 1에서 2로 늘어납니다. 7.5.3은 거부합니다. 중첩 fixture는
  7.5.6이 공유하고 7.5.7이 거부합니다. 판정 조건에 릴리스 번호나 정답 경로는 없습니다. 고정 쌍과 CVE의 대응은 추론이고,
  이것은 퍼저가 스스로 찾은 결과가 아닙니다.

### 장면 6 (3:35–4:05) 자력 발견의 현재 판정 (M3)

- **명령:**

  ```bash
  grep '^| 퍼저가' docs/STATUS.md | cut -d'|' -f2-3
  ```

- **기대 출력:** `퍼저가 **자력으로** 경계위반을 발견 | 이름 획득 조건의 관찰(피드백 인과 미입증): 외부 객체 이름을 어휘에
  획득한 조건에서 자율 C1 관찰 (A3 21 vs A1 0 vs identity-blind 0); 어휘 미통제라 retention·effect 피드백 인과는 미입증 *(구: 입증(인과), 2026-11-03 정정; 비고 끝에 상세)*`
  (끝의 "구:" 부분은 옛 표현이 정정됐다는 기록이다.)
- **화면:** 이어서 `paper/figures/m3-blind-ablation.png`(재렌더 판).
- **내레이션:** 퍼저의 자력 발견에 대한 현재 판정은 Ledger 문구 그대로, 이름 획득 조건의 관찰, 피드백 인과 미입증입니다.
  외부 객체 이름을 어휘에 넣은 조건에서 자율 위반이 관찰됐지만, 이 대조는 어휘를 통제한 것이라 피드백의 효과로 읽지
  않습니다. blind 발견도 아닙니다.

### 장면 7 (4:05–4:40) EXP-0 인프라 측정

- **명령:**

  ```bash
  python3 scripts/make_raw_manifest.py --verify experiments/summaries/raw-manifest-win-20261105-20261105.sha256 --root ~/inodefence-evidence/exp0-20261105
  sed -n 1,21p ~/inodefence-evidence/exp0-20261105-analysis-premerge/exp0-report-premerge.md
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

  스택 머지 후 재생성한 리포트가 있으면 그 파일로 바꾼다. 위 경로는 pre-merge 분석이다.
- **자막:** "화면 값 = monotonic clock 기록값. 실시간 환산: p95 1.419 s · 스트림당 2650 exec/h · 호스트 전체 ≈4760 exec/h (실시간 기준,
  장기 편차 검증 중)".
- **내레이션:** 이어서 EXP-0 등록 실행의 증거입니다. 세 arm, seed 다섯 개, budget 200의 15셀을 모두 완주했고 abort는 0입니다.
  C1과 C2 hit도 0인데, 사전등록에서 기본 결과로 예상한 값입니다. 화면의 시간과 처리량은 기록값이고, 자막이 실시간 환산값입니다.
  당시 이 호스트의 clock이 실제보다 빠르게 갔기 때문입니다. 인프라 측정이며 가설 검정이 아닙니다.

### 장면 8 (4:40–4:55) 다음 단계

- **화면:** `paper/deliverables/capstone-report-draft.md` §7.6의 TBD 표.
- **내레이션:** 본실험 EXP-3은 11월 18일 사전등록 뒤 실행할 예정이고 아직 결과가 없습니다. 결과는 사전등록 규칙대로
  보고합니다. 감사합니다.

## 확장 장면 (선택, 서식이 허용할 때만)

### E1 (장면 4 뒤, +40초) 선택 근거

- **명령:**

  ```bash
  jq '.steps[5] | {oracle, retained: .selection.corpus_admission, operator: .selection.selected_operator_id, reward: .selection.operator_weights.reward}' /tmp/inodefence-video/inodefence-effect-demo-native-*.json
  ```

- **기대 출력:** `oracle` C0/C1/C2 모두 false, `retained.corpus_size_before` 4, `retained.retained` true, `operator`
  `add_entry`, `reward` 1.
- **내레이션:** 결과 파일에는 step마다 선택 근거가 남습니다. 이 step은 새 상태 키가 나와 입력이 corpus에 남았고, add_entry의
  보상이 1입니다. 실제로 적용된 feedback만 기록합니다.

### E2 (E1 뒤, +25초) 중간 상태 기록

- **명령:**

  ```bash
  jq '.steps[5].trace | {synthetic, first_event: (.effect_events[0] | {operation, evidence_strength, path: .paths[0].path, after: .paths[0].after})}' /tmp/inodefence-video/inodefence-effect-demo-native-*.json
  ```

- **기대 출력:** `synthetic` false, `operation` `mkdir`, `evidence_strength` `state_change_verified`, `path` `extract/a.txt`,
  `after`의 `st_dev`·`st_ino`·`st_nlink` (값은 실행마다 다르다).
- **내레이션:** 중간 상태는 entry별로 기록하고, 합성 데이터가 아님을 표시합니다.

### E3 (장면 5 뒤, +30초) 비단조 분포

- **명령:**

  ```bash
  jq '.nested_hardlink.per_release_shared' /tmp/inodefence-video/repro/summary.json
  ```

- **기대 출력:** 7.5.2 `true`, 7.5.3 `false`, 7.5.6 `true`, 7.5.7 `false`, 7.5.8 `false`.
- **내레이션:** 중첩 fixture의 공유 여부는 릴리스가 올라가면서 단조롭게 바뀌지 않습니다. 관찰된 것은 이 분포이고, 원인에 대한
  서술은 추론입니다.

### E4 (장면 6 뒤, +25초) M4 범위

- **명령:**

  ```bash
  grep '^| cross-implementation' docs/STATUS.md | cut -d'|' -f2-3
  ```

- **기대 출력:** `cross-implementation(2번째 extractor에 generic oracle 적용) | 일부 TESTED(oracle 수준)`
- **내레이션:** 같은 oracle을 python-tarfile, oras-go, decompress 세 extractor에 adapter로 적용했습니다. oracle 수준의 일반성이며,
  자력 발견이나 효과의 일반성이 아닙니다.

## 말하지 않는 것

- 피드백이 무작위나 커버리지보다 빠르다거나 많이 찾는다는 말.
- M3를 인과나 입증으로 부르는 말. 표현은 "이름 획득 조건의 관찰(피드백 인과 미입증)" 그대로 쓴다.
- 선행연구 대비 우선권이나 참신성을 단정하는 말.
- 새 상태 키 수나 dense 신호를 효과의 근거로 드는 말(EN-008).
- `make demo`의 위반 0을 node-tar의 안전성으로 읽는 말.
- EXP-0의 기록값(1.549 s, 2428 exec/h)을 실시간 값이나 호스트 전체 처리량처럼 읽는 말.
