# node-tar 자력 발견 — 메커니즘 인과 validated summary v1

M3(퍼저가 자력으로 경계위반을 발견) 결론의 **검증된 작은 요약**이다.
[summaries 규칙](README.md)의 체인을 명시한다:

```text
raw: ~/inodefence-evidence/{m3-scale-full, m3-ablation, m3-repro}/  (저장소 밖, git-ignore; 각 디렉터리에 matrix.json)
  → validated summary: 이 문서 (raw를 아래 "재검증 명령"으로 다시 세어 작성)
  → finding: 아래 "## Finding"
  → paper 포인터: ../../paper/sections/claims-evidence-status-v1.md
  → 능력 원장(단일 기준): ../../docs/STATUS.md (Capability Ledger M3 행 / 마일스톤 M3; PR #151 머지)
```

raw는 대량 출력이라 저장소 밖(`~/inodefence-evidence/`)에 보존되고 계속 git-ignore된다
(summaries 규칙: 대량 raw는 `experiments/raw/` 상당 위치에 두고 ignore). 아래 숫자는 전부 그 raw의
step 로그(`*.steps.jsonl`)를 **재현 가능한 변환으로 다시 세어** 얻은 것이며 수동으로 지어내지 않았다.
raw 사본 위치: 작성 호스트(규민/지웅 로컬)의 `~/inodefence-evidence/`. 저장소에는 없음.

## 실험 설정 (provenance)

| 항목 | 값 |
| --- | --- |
| target | node-tar 7.5.2 (image `inodefence-node-tar-effect:7.5.2`) — 영향(affected) 릴리스 |
| mode | `demo-historical`, jobs 3 |
| budget | 1500 (campaign당) |
| raw 디렉터리 | `~/inodefence-evidence/m3-scale-full` (A1·A3, seed 1–35), `~/inodefence-evidence/m3-ablation` (A3full·A3blind, seed {1,2,11,18,24,27}), `~/inodefence-evidence/m3-repro` (A3full, seed 36–65) |
| 디렉터리 내 provenance | 각 `matrix.json` (arms·budget·seeds·run_id·wall_seconds·evidence 파일명) |
| arm 정의 | A3full = `uniform-generic-m1-state-aware-escape-hardlink-v1`; A3blind = `uniform-generic-m1-state-aware-escape-hardlink-blind-v1`(관찰 이름에서 EXTERNAL region 제외); A1 = 무작위 바닥(token-clean, state-aware 외부 주소지정 없음). search = `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1` |
| 관련 PR | #151 (메커니즘·실제규모·blind 대조, main 머지 `d44d903`) |

### hit 정의 · 재검증 명령

**hit = step에서 `oracle.C1` AND `feedback.contract_violated` 가 모두 참.** 각 campaign의
`*.steps.jsonl`을 한 줄씩 읽어 이 술어로 센다(아래 표의 모든 숫자를 이렇게 재현). s11 run은
**step 416에서 evidence-integrity 검사로 abort(returncode 1)** 하지만, 21건의 hit는 **abort 이전**에
기록된 step들이다(producer abort-drain이 거부된 외부-하드링크 시도를 valid trace로 관찰). 따라서
process returncode 1 을 "발견 없음"으로 읽으면 안 된다 — hit는 pre-abort observed trigger로 별도 집계.

## 검증된 수치 (observed, raw step 로그 재집계)

| 셀 | seeds | 기록 step 수 | 자율 C1 hit (C1 ∧ contract_violated) |
| --- | --- | --- | --- |
| **A3full s11** (scale-full, ablation 동일·결정론) | 11 | 416 (abort 전) | **21** (21건 모두 C1·C2·contract_violated 동시) |
| **A3blind s11** (identity-blind 대조) | 11 | 1475 | **0** |
| **A1 random floor** (scale-full) | 1–35 (35개) | 33,005 | **0** |
| A3full scale study | 1–35 (35개) | 41,494 | **s11만 21** (그 외 전 seed 0) |
| A3full 재현 | 36–65 (30개) | 34,585 | **0/30** |

합산: budget 1500·7.5.2에서 A3full 65 seed(1–65) 중 자율 C1을 내는 seed는 **정확히 s11 하나**다.

## Finding

영향 릴리스 7.5.2에서 **state-aware 퍼징(filesystem-state의 object-identity를 feedback으로 사용)이
경계위반을 자율 트리거**한다: A3full s11이 퍼저 생성 `../outside/sentinel.txt` 하드링크로 추출 객체↔
외부 sentinel 동일 inode(C1+C2) 21건을 만든다.

**인과(핵심 주장, observed):** 발견의 원인은 **object-identity 관찰**이다 — blind 대조(관찰 이름에서
EXTERNAL region 제외)의 A3blind s11은 1475 step에도 0, 무작위 바닥 A1은 33,005 step에도 0.
즉 **"피드백(identity 관찰)이 발견을 가능케 한다 — 없으면 도달 불가."** 이것은 가설이 명시한
object-identity feedback이 실제로 발견을 구동함을 blind 대조로 확정한 것이다.

### 정직 경계 (반드시 유지 — inferred/열린 항목)

- **blind 발견이 아니다.** 기존 외부 객체에 하드링크하려면 그 이름이 필요하고, 퍼저는 그것을
  **관찰**로 얻는다(가설이 명시한 identity feedback). 어휘·oracle에 대상 경로/식별자/정답 seed/근접
  보상을 하드코딩하지 않았고, EXTERNAL 필터는 region 기준 target-agnostic이다. 다만 state-aware
  mutation 어휘 계열(`m1_addressing`)이 `outside`/`sentinel.txt` 토큰을 포함할 수 있으므로, 어떤
  rediscovery 프레이밍에서도 **"blind 아님"을 명시**해야 한다(연구 정직성).
- **rate 우위(H1 effectiveness)는 미판정 / 진행 중.** 이 요약의 주장은 **인과**("피드백이 발견을
  가능케 함")이지 **"상태-인지 피드백이 무작위보다 빠르다(rate)"가 아니다.** 동일 seed·budget 매칭
  대조(A1 vs A3full, budget 2000, seed 100–119)의 **powered 독립 반복이 별도 세션에서 실행 중**이며,
  그 결과가 나오기 전까지 rate 결론은 **열어 둔다**. budget 100·~60 seed study는 clean exact C1 0였다.
- **seed-rare.** s11은 동일 seed에서 결정론적으로 재현(21건)되지만, 교차-seed로는 budget 1500에서
  65개 중 1개뿐이라 **이 예산에서 다른 seed로 일반화되지 않는다**(재현 0/30).
- observed(위 표의 재집계 숫자)와 inferred(메커니즘 서술·CVE 대응)를 구분한다.

## 선행연구 포지셔닝

[related-work-positioning](../../docs/research/design/related-work-positioning.md)을 따른다.
feedback-driven file-state fuzzing(LinkZard), feedback-guided archive fuzzing(ZIPDiff),
archive-extraction symlink/hardlink 공격(Wormholes)은 선행연구가 다룬다. 따라서 "최초의
state-guided archive fuzzer", "기존 연구는 inode를 안 썼다" 류 주장은 하지 않는다. 이 요약이
방어하는 것은 좁은 인과 명제(**identity 관찰이 없으면 이 경계위반에 도달 불가**)뿐이다.

## 통제 재현(M2)과의 구분

M2([cross-release 재현 요약](cross-release-identity-repro-v1.md))는 손 fixture의 통제 재현이고,
여기 M3는 퍼저 자력 발견이다. 두 결론을 섞지 않는다.
