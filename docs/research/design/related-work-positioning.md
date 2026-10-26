# 선행연구 포지셔닝

이 문서는 InodeFence가 가장 가까운 선행연구와 어떤 관계에 있는지 현재 기준으로 정리한다.

이미 알려진 아이디어를 실수로 신규 기여처럼 표현하지 않기 위한 기준 문서다.

각 절의 **서지**는 저자·venue·연도·아티팩트를 2026-10-26 독립 확인한 것으로, 심사자가 원문을 찾을 수 있게 한다.

## Jana & Shmatikov — 2012

**Abusing File Processing in Malware Detectors for Fun and Profit**

서지: Suman Jana, Vitaly Shmatikov (UT Austin). IEEE S&P 2012, pp. 80–94. DOI [10.1109/SP.2012.15](https://doi.org/10.1109/SP.2012.15) · [dblp](https://dblp.org/rec/conf/sp/JanaS12.html)

확인된 관련 내용:

- file-processing 구현 사이 semantic gap 연구
- TAR 관련 공격 포함
- 일부 format에 black-box differential technique 사용
- malformed archive/file metadata가 보안 관련 해석 차이를 만들 수 있음을 보임

따라서 신규성에서 제외되는 것:

- TAR malformed input 자체
- TAR semantic-gap 공격 자체
- header/metadata mutation 자체

현재 추가 검증할 차이:

- filesystem object identity와 external-effect feedback으로 archive extraction 탐색을 유도하는 방법은 이 연구에서 확립된 것으로 확인되지 않음

## ZIPDiff — 2025

**My ZIP isn't your ZIP: Identifying and Exploiting Semantic Gaps Between ZIP Parsers**

서지: Yufan You, Jianjun Chen, Qi Wang, Haixin Duan (Tsinghua). USENIX Security 2025, Distinguished Paper. 50 parser / 19개 언어 differential, 공개 아티팩트. [USENIX](https://www.usenix.org/conference/usenixsecurity25/presentation/you) · [artifact](https://github.com/ouuan/ZipDiff)

확인된 관련 내용:

- archive-aware mutation
- byte-level mutation
- feedback-guided corpus evolution
- extraction-output comparison
- 여러 ZIP parser 대상 대규모 differential testing

따라서 신규성에서 제외되는 것:

- archive-aware fuzzing
- feedback-guided archive fuzzing
- interesting-seed retention
- path/order mutation 자체

InodeFence 관점의 중요한 한계:

후속 연구에서는 ZIPDiff가 복잡한 link composition과 creation order가 필요한 테스트 대상 symlink vulnerability를 찾지 못했다고 보고했다.

## LinkZard — 2025

**Pig in a Poke: Automatically Detecting and Exploiting Link Following Vulnerabilities in Windows File Operations**

서지: Bocheng Xiang, Yuan Zhang, Fengyu Liu, Hao Huang, Zihan Lin, Min Yang (Fudan). USENIX Security 2025 (Honorable Mention). 도구명 LinkZard; 120개 상용 프로그램에서 55 zero-day, 15 CVE. [USENIX](https://www.usenix.org/conference/usenixsecurity25/presentation/xiang-bocheng) · [artifact (Zenodo)](https://zenodo.org/records/15479538)

확인된 관련 내용:

- feedback-driven file-state fuzzing
- state-query-driven mutation
- file-operation sequence 분석
- hardlink 정보와 link count를 포함한 link-related state

따라서 신규성에서 제외되는 것:

- filesystem-state fuzzing 일반
- hardlink state 관찰
- link count 관찰
- ordered file operation 분석

현재 추가 검증할 차이:

- LinkZard는 archive-entry mutation framework가 아니며, TAR archive 자체를 evolving input corpus로 사용하지 않는다.

## Wormholes — 2026

**Wormholes in the File System: Understanding the Misunderstanding of Symlinks**

서지: Yongheng Liu, Lei Zhang, Yuhang Zhao, Yuzhou He (Fudan). USENIX Security 2026. 85개 프로젝트에서 16 arbitrary file write, 2 high-severity CVE. 아티팩트 Zenodo DOI [10.5281/zenodo.20325582](https://doi.org/10.5281/zenodo.20325582)

현재 InodeFence와 가장 직접적으로 가까운 선행연구다.

확인된 관련 내용:

- archive extraction이 핵심 scenario
- symlink composition
- entry creation order
- dangling symlink
- symlink update
- extraction-root manipulation
- symlink 관련 path를 통한 hardlink creation
- arbitrary file read/write effect

따라서 신규성에서 제외되는 것:

- symlink 공격 자체
- hardlink 공격 자체
- symlink + hardlink 조합
- entry-order 공격
- archive entry 간 state 변화
- outside-root effect

## 현재 InodeFence Research Gap 가설

현재 질문은 다음이 아니다.

> TAR hardlink, symlink, entry order가 extraction vulnerability를 만들 수 있는가?

이 부분은 이미 선행연구가 보여줬다.

현재 질문은 다음이다.

> 고정된 공격 recipe 없이 generic archive-entry mutation을 수행하면서 filesystem object identity와 external-effect state를 feedback으로 사용하면, fuzzer가 security-relevant state 방향으로 corpus를 발전시킬 수 있는가?

개념적으로:

```text
Fixed strategy
    known semantic analysis
        -> predefined bypass/write recipe
        -> target

InodeFence hypothesis
    generic seed
        -> generic mutation
        -> extractor
        -> filesystem security state
        -> retain novel state
        -> mutate again
```

## 아직 하면 안 되는 주장

현재 단계에서는 다음을 주장하지 않는다.

- "InodeFence가 최초의 state-guided archive fuzzer다."
- "기존 연구는 inode 정보를 사용하지 않았다."
- "기존 연구는 archive link를 fuzzing하지 않았다."
- "기존 연구는 entry ordering을 보지 않았다."
- "제안 방법이 fixed strategy보다 우수하다."
- "제안 방법이 여러 extractor에 일반화된다."

일부는 선행연구와 충돌하고, 일부는 추가 문헌조사나 실험이 필요하다.

## Evaluation에서 반드시 보여줘야 할 것

제안하는 state representation과 feedback loop가 실제 측정 가능한 가치를 제공해야 한다.

예:

- 동일 budget에서 더 빠른 rediscovery
- 더 높은 rediscovery rate
- 더 많은 security-relevant state 탐색
- 여러 target implementation에서 유용한 일반성
- 약한 baseline이 도달하지 못한 state 탐색

실험 전까지 이 내용은 모두 가설이다.
