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
소수 타깃의 알려진 클래스에 한정되며 blind 발견을 주장하지 않고, 효과도 아직 검증되지 않았다. 범용 변이도 Wormholes 저자들이 ZIPDiff에 대해
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
> blind 발견을 주장하지 않는다.)

*(구: "고정된 공격 recipe 없이 generic archive-entry mutation을 수행하면서 … corpus를 발전시킬 수 있는가?", v1 질문,
2026-11-06 v2로 교체. research-questions v2 '폐기·대체 기록' 참조.)*

## 3.6 이 단계에서 하지 않는 주장 (엄수)

선행연구 포지셔닝 문서의 금지 목록을 그대로 지킨다. 다음은 **쓰지 않는다.**

- "InodeFence가 최초의 state-guided archive fuzzer다."
- "기존 연구는 inode 정보를 사용하지 않았다 / archive link를 fuzzing하지 않았다 / entry ordering을
  보지 않았다."
- "제안 방법이 fixed strategy보다 우수하다 / 여러 extractor에 (effectiveness 수준으로) 일반화된다."

일부는 선행연구와 충돌하고, 일부는 추가 문헌조사·실험이 필요하다. 이 드래프트가 방어하는 것은
§5의 좁은 명제들(M1 동작, M2 통제 재현, M3 이름 획득 조건의 관찰(피드백 인과 미입증), M4 oracle/adapter 일반성)뿐이다 *(구: "M3 인과 입증", 2026-11-03 정정 — 상세 §5.3.2)*.
