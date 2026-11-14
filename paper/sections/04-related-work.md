# 3. Related Work (드래프트 v1)

이 절은 InodeFence가 가장 가까운 선행연구와 어떤 관계에 있는지, 이미 알려진 아이디어를 실수로
신규 기여처럼 표현하지 않도록 정리한다. 전체 기준과 서지는
[`../../docs/research/design/related-work-positioning.md`](../../docs/research/design/related-work-positioning.md)를
그대로 따른다(서지는 2026-10-26 독립 확인).

## 3.1 Jana & Shmatikov (IEEE S&P 2012)

"Abusing File Processing in Malware Detectors for Fun and Profit"는 file-processing 구현 사이의
semantic gap을 연구했고 TAR 관련 공격을 포함하며, malformed archive/metadata가 보안 관련 해석
차이를 만들 수 있음을 보였다. 따라서 **TAR malformed input 자체, TAR semantic-gap 공격 자체,
header/metadata mutation 자체는 신규성에서 제외된다.** 이 연구에서 확립된 것으로 확인되지 않은
것은 "filesystem object identity와 external-effect state를 feedback으로 써서 archive extraction 탐색을
유도하는 방법"이며, 이는 추가 검증 대상 차이다.

## 3.2 ZIPDiff (USENIX Security 2025)

"My ZIP isn't your ZIP"은 archive-aware·byte-level mutation, feedback-guided corpus evolution,
extraction-output 비교로 50개 ZIP parser를 대규모 differential testing했다. 따라서 **archive-aware
fuzzing, feedback-guided archive fuzzing, interesting-seed retention, path/order mutation 자체는
신규성에서 제외된다.** Wormholes 저자들은 ZIPDiff 구현을 재현해 자신들의 ZIP 도구 20개(그중 8개에 symlink 취약점)에 적용했을 때
하나도 탐지하지 못했다고 보고하고, 그 이유로 이런 공격에는 정교한 symlink target과 creation order가 필요한데 ZIPDiff로는 복잡한 symlink
composition을 만들 수 없다고 설명한다(Wormholes §5.6). 이는 단일 출처의 저자 평가이고 입력 생성과 판정 방식 중 무엇이 원인인지 분리하지
않았으므로, 일반적인 ZIPDiff 한계로 읽지 않는다.[^zipdiff-wormholes]

[^zipdiff-wormholes]: evidence: [Wormholes in the File System](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yongheng) §5.6(p. 5223): "We reproduced the open-source implementation of ZIPDIFF and evaluated it on 20 zip tools from our dataset, eight of which contain symlink vulnerabilities. ZIPDIFF fails to detect any of them.", "cannot generate ZIP inputs with such complex symlink compositions". 원문 확인은 2026-11-06 독립 심사(W3) 정독이며 이 문장을 쓸 때 다시 대조하지 않았다.

## 3.3 LinkZard (USENIX Security 2025)

"Pig in a Poke"는 feedback-driven file-state fuzzing, state-query-driven mutation, file-operation
sequence 분석, hardlink 정보·link count를 포함한 link-related state를 사용했다. 따라서
**filesystem-state fuzzing 일반, hardlink state 관찰, link count 관찰, ordered file operation 분석은
신규성에서 제외된다.** LinkZard의 대상은 제목과 발표 페이지 기준 Windows 파일 연산이다. 추가 검증할 차이(확정이 아니라 가설)는
LinkZard가 archive-entry mutation framework가 아니며 TAR 아카이브 자체를 evolving input corpus로 쓰지 않는다는 점이다.

## 3.4 Wormholes (USENIX Security 2026)

"Wormholes in the File System"은 archive extraction을 핵심 시나리오로 symlink composition, entry
creation order, dangling symlink, symlink update, extraction-root manipulation, symlink 경유 hardlink
creation, arbitrary file read/write effect를 다룬다. 현재 InodeFence와 가장 직접적으로 가까운
선행연구이며, 따라서 **symlink 공격·hardlink 공격·그 조합·entry-order 공격·archive entry 간 state
변화·outside-root effect 자체는 신규성에서 제외된다.**

**이 연구와의 경계.** Wormholes는 언어 표준 라이브러리의 경로 해석 불일치에서 출발해 symlink 체인·갱신·dangling·추출 루트 조작 등 5개 우회
방식과 3개 쓰기 방법(symlink 경유 hardlink 포함)을 설계하고 85개 프로젝트에서 임의 쓰기 16건을 보고했다. 이런 공격 구성의 존재, creation
order의 중요성, 실제 구현에서의 발생 규모는 이 연구의 기여가 아니다. 외부 객체 hardlink 공격 자체도 advisory로 이미 알려져 있다. 이 연구가
검증하려는 것은 더 좁은 비교 가설이다. 피해 경로 이름을 아는 같은 어휘·같은 예산 아래에서, 범용 TAR entry 변이에 filesystem security
state(C1 identity·C2 effect) retention을 더한 탐색이 무작위 탐색과 구조 커버리지 탐색보다 첫 경계위반까지의 실행 수를 줄이는가. Wormholes
본문은 이런 arm 간 비교나 피드백 기반 탐색을 기술하지 않으며(아티팩트는 확인하지 않았다), 자동화 워크플로는 seed archive로 추출기 동작을
확인한 뒤 설계된 우회 방식을 고른다(Wormholes §5.5). 이 차이는 우위를 뜻하지 않는다. Wormholes는 다수 구현에서 실제 취약점을 찾았고, 이 연구는
소수 타깃의 알려진 클래스에 한정되며 피해 경로 이름을 모르는 조건(blind)의 결과를 주장하지 않으며, 효과도 아직 검증되지 않았다. 범용 변이도 Wormholes 저자들이 ZIPDiff에 대해
평가한 한계(복잡한 symlink composition을 만들지 못함, Wormholes §5.6)를 똑같이 가질 수 있으며, 이는 이 가설이 시험해야 할 위험이다.[^wormholes-boundary]

[^wormholes-boundary]: evidence: [Wormholes in the File System](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yongheng) 전문(pp. 5213–5226)을 2026-11-06 독립 심사(W3)가 정독했다. 아티팩트(Zenodo 20325582)는 열지 않았고 프로젝트명이 익명화돼 node-tar 포함 여부는 알 수 없다. 이 문단을 쓸 때 원문을 다시 대조하지 않았다.

## 3.5 InodeFence가 조사하는 좁은 질문

위 선행연구를 고려하면, 현재 질문은 "TAR hardlink/symlink/entry order가 extraction 취약점을 만들
수 있는가"가 **아니다**(이미 보여졌다). 현재 질문은 다음이다.

> 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래서, filesystem security state(C1 identity·C2 effect)를
> retention·스케줄링 피드백으로 쓰는 탐색이 **무작위 탐색**과 **구조 커버리지 탐색**보다 첫 경계위반까지의
> 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가?
> (핵심 RQ, [research-questions v2](../../docs/research/design/research-questions.md). 위협 모델 전제: 공격자는
> 피해 경로 이름 — 보호 대상 외부 객체의 추출 루트 기준 상대 경로 — 을 알며 세 arm 어휘에 동일하게 포함한다.
> 피해 경로 이름을 모르는 조건(blind)의 결과를 주장하지 않는다.)

## 3.6 이 단계에서 하지 않는 주장 (엄수)

선행연구 포지셔닝 문서의 금지 목록을 그대로 지킨다. 다음은 **쓰지 않는다.**

- "InodeFence가 최초의 state-guided archive fuzzer다."
- "기존 연구는 inode 정보를 사용하지 않았다 / archive link를 fuzzing하지 않았다 / entry ordering을
  보지 않았다."
- "제안 방법이 fixed strategy보다 우수하다 / 여러 extractor에 (effectiveness 수준으로) 일반화된다."

일부는 선행연구와 충돌하고, 일부는 추가 문헌조사·실험이 필요하다. 이 드래프트가 방어하는 것은
§5의 좁은 명제들(M1 동작 [C-M1], M2 통제 재현 [C-M2], M4 오라클·어댑터 수준 적용 [C-M4a])뿐이다.

## 3.7 비교 축과 평가 방법론 (감사 03 권고)

### 3.7.1 5축 비교표

아래 표는 포지셔닝 문서([related-work-positioning.md](../../docs/research/design/related-work-positioning.md))에
**이미 명시된 사실만** 다섯 축(입력·관찰·판정(oracle)·피드백·평가)으로 재배열한 것이다. 문서에 그 축이 서술돼
있지 않으면 "— (명시 없음)"으로 둔다. 각 원문에 대한 추가 대조는 TBD이며, 읽지 않은 원문의 수치·주장은 적지
않는다. 서지는 §3.1–3.4와 포지셔닝 문서(2026-10-26 독립 확인)를 따른다.

| 연구 | 입력 | 관찰 | 판정(oracle) | 피드백 | 평가(규모·방법) |
| --- | --- | --- | --- | --- | --- |
| Jana & Shmatikov 2012 | malformed archive/파일 metadata (TAR 포함) | file-processing 구현 간 semantic gap | 일부 format에 black-box differential | — (명시 없음) | — (정량 명시 없음; differential) |
| ZIPDiff 2025 | archive-aware + byte-level mutation (ZIP) | extraction-output 비교 | parser 간 differential | feedback-guided corpus evolution + interesting-seed retention | 50 parser / 19개 언어 대규모 differential, 공개 아티팩트 |
| LinkZard 2025 | Windows 파일 연산(링크 추종; archive corpus 아님) | file-operation sequence + hardlink/link-count state | link-following 취약점 탐지 | feedback-driven file-state fuzzing + state-query-driven mutation | 120개 상용 프로그램, 55 zero-day, 15 CVE |
| Wormholes 2026 | archive extraction(symlink composition·entry order·dangling·update·extraction-root manipulation·symlink 경유 hardlink) | — (명시 없음) | arbitrary file read/write effect | — (명시 없음) | 85개 프로젝트, 16 arbitrary file write, 2 high-severity CVE |
| InodeFence (현재) | generic archive-entry mutation (TAR; 8 generic operator + escape-hardlink 문법; 피해 경로 이름은 세 arm 어휘에 동일 포함, blind 아님) | object identity `(st_dev, st_ino)`·external effect·boundary-attempt | generic C0/C1/C2 Security Contract (CVE 비하드코딩) | S-u 입회: effect 키(boundary-attempt 포함) 신규 또는 새 위반 fingerprint. StateSignature 파생 구조 특징으로 입회하는 것은 대조군 D | 등록 실험: R/D/S-u T_first(§4.6) — 본실험 결과 자리(봉인 해제 뒤 기입); 현재: M1·M2·M4 좁은 명제 |

이 표는 신규성 주장이 아니라 **포지셔닝**이다(§3.6 금지 목록 준수). InodeFence 행의 평가 칸 결과는
봉인 해제 뒤에만 채운다.

### 3.7.2 평가 방법론 기준

정량 비교(§4.6)는 퍼징 평가 방법론 문헌의 권고를 따르는 것을 목표로 한다. 아래 세 편의 서지는 2026-11-04
웹에서 확인했고, 각 연결 문장은 해당 논문의 **초록·권고 목록에서 실제로 읽은 범위**에 한정한다(읽지 못한
본문 통계는 적지 않는다).

- **Klees et al., "Evaluating Fuzz Testing," ACM CCS 2018** (DOI [10.1145/3243734.3243804](https://doi.org/10.1145/3243734.3243804);
  arXiv [1808.09700](https://arxiv.org/abs/1808.09700)). 이 논문은 복수 trial + 통계 검정(randomized algorithm에
  Mann-Whitney U), 서로 다른 seed, 더 긴 timeout(≥24h), "unique crashes" 같은 중복제거 heuristic 대신
  ground-truth 버그 기준 측정을 권고한다(초록·본문 §4–§8에서 읽음; 자체 실험은 ≥30 run 중앙값·95% CI). 우리
  설계는 EXP-3 train에서 20 seed를 반복하고, holdout 확증에 seed 블록 순열 로그랭크 검정을 쓰며, 문서화된 seed를 쓰고 hit을 generic
  C0/C1/C2 oracle 판정으로 둔다(§4.6) [C-DESIGN]. 다만 U_viol은 oracle fingerprint 중복제거로 세므로 이 논문이 경계한 중복제거 부류에
  속하며, ground-truth 버그 수로 읽지 않는다. 단 우리 1차 지표는 wall-time이 아니라 executions-to-first(T_first)이며 시간
  값은 보조이며 실시간 타임스탬프로 계산한다(exp3-v1).
- **Böhme, Liyanage & Wüstholz, "Estimating Residual Risk in Greybox Fuzzing," ESEC/FSE 2021**
  (DOI [10.1145/3468264.3468570](https://doi.org/10.1145/3468264.3468570); [PDF](https://mboehme.github.io/paper/FSE21.pdf)).
  초록은 오류 없는 campaign에도 잔여 위험(residual risk)이 남으며 greybox에서는 이를 직접 추정할 수 없어
  discovery probability(다음 입력이 커버리지를 늘릴 확률)를 상한으로 쓰고 campaign 중 추정해 중단 시점을
  정한다고 밝힌다(초록에서 읽음; reachability 주장은 초록에 없음). 우리 설계의 우측중도절단과 zero-hit
  rule-of-three 상한(§4.6.2, 판정표 ⑤ 행 §7.2)도 '위반 0 = 안전'으로 읽지 않는다는 취지는 같지만, 우리 상한은 캠페인 단위 hit 확률이지 잔여 위험
  추정이 아니다.
- **Schloegel et al., "SoK: Prudent Evaluation Practices for Fuzzing," IEEE S&P 2024**
  (DOI [10.1109/SP54263.2024.00137](https://doi.org/10.1109/SP54263.2024.00137); arXiv [2405.10220](https://arxiv.org/abs/2405.10220)).
  2018–2023 top-venue 150편을 분석해 통계 검정 권고의 광범위한 미준수를 보고하고, baseline 비교·충분한 trial
  수와 통계 검정·효과크기·문서화된 seed·버그 기준 지표(fuzzer 고유 proxy 지양)를 갱신 guideline으로 제시한다
  (초록·§II 권고 목록에서 읽음). 우리 설계의 R/D baseline·paired seed·로그랭크+A12 효과크기·EN-008(중간상태는
  search behavior이지 effectiveness 아님)이 이에 대응한다.

> **아직 적지 않는 것(TBD).** 위 논문들의 **본문 설문 통계(논문 수·비율 분해 등)** 중 이번에 원문에서 직접
> 확인하지 못한 수치는 적지 않는다. 필요 시 전체 PDF 확인 후 채운다.
