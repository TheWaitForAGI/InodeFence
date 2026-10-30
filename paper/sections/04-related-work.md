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
신규성에서 제외된다.** 후속 연구는 ZIPDiff가 복잡한 link composition과 creation order가 필요한
symlink 취약점을 찾지 못했다고 보고한 바 있다(선행연구 보고로만 인용).

## 3.3 LinkZard (USENIX Security 2025)

"Pig in a Poke"는 feedback-driven file-state fuzzing, state-query-driven mutation, file-operation
sequence 분석, hardlink 정보·link count를 포함한 link-related state를 사용했다. 따라서
**filesystem-state fuzzing 일반, hardlink state 관찰, link count 관찰, ordered file operation 분석은
신규성에서 제외된다.** 확인된 차이는 LinkZard가 archive-entry mutation framework가 아니며 TAR
아카이브 자체를 evolving input corpus로 쓰지 않는다는 점이다.

## 3.4 Wormholes (USENIX Security 2026)

"Wormholes in the File System"은 archive extraction을 핵심 시나리오로 symlink composition, entry
creation order, dangling symlink, symlink update, extraction-root manipulation, symlink 경유 hardlink
creation, arbitrary file read/write effect를 다룬다. 현재 InodeFence와 가장 직접적으로 가까운
선행연구이며, 따라서 **symlink 공격·hardlink 공격·그 조합·entry-order 공격·archive entry 간 state
변화·outside-root effect 자체는 신규성에서 제외된다.**

## 3.5 InodeFence가 조사하는 좁은 질문

위 선행연구를 고려하면, 현재 질문은 "TAR hardlink/symlink/entry order가 extraction 취약점을 만들
수 있는가"가 **아니다**(이미 보여졌다). 현재 질문은 다음이다.

> 고정된 공격 recipe 없이 generic archive-entry mutation을 수행하면서 filesystem object identity와
> external-effect state를 feedback으로 쓰면, fuzzer가 security-relevant state 방향으로 corpus를
> 발전시킬 수 있는가?

## 3.6 이 단계에서 하지 않는 주장 (엄수)

선행연구 포지셔닝 문서의 금지 목록을 그대로 지킨다. 다음은 **쓰지 않는다.**

- "InodeFence가 최초의 state-guided archive fuzzer다."
- "기존 연구는 inode 정보를 사용하지 않았다 / archive link를 fuzzing하지 않았다 / entry ordering을
  보지 않았다."
- "제안 방법이 fixed strategy보다 우수하다 / 여러 extractor에 (effectiveness 수준으로) 일반화된다."

일부는 선행연구와 충돌하고, 일부는 추가 문헌조사·실험이 필요하다. 이 드래프트가 방어하는 것은
§5의 좁은 명제들(M1 동작, M2 통제 재현, M3 인과 입증, M4 oracle/adapter 일반성)뿐이다.
