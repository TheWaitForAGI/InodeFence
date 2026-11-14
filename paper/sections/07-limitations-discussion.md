# 6. Limitations & Discussion (드래프트 v1)

이 절은 §5의 결과가 **무엇을 주장하지 않는지**를 명시한다. 한계를 숨기면 증거 사슬이 끊긴다.

## 6.2 M4 일반성의 범위

- **oracle/adapter 수준 일반성.** §5.4.1의 3-extractor 적용은 oracle/adapter 수준의
  target-agnostic성 증거이며, 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다.

## 6.4 snapshot oracle의 구조적 한계

- `violated=False`는 "관찰 범위 안에서 위반 증거 없음"이지 모든 operation이 안전했다는 증명이
  아니다. 관찰 실패는 오류로 올리며 nonviolation을 만들지 않는다.
- 두 snapshot 사이 중간 변화, transient 생성 후 삭제, inode 번호 재사용, sandbox 밖 접근, 외부 path
  direct-use, symlink referent는 현재 범위에서 판정하지 못한다. C3/C4와 full tracing은 후속 단계다.
- entry checkpoint 사이의 transition은 feedback evidence일 뿐이고 confirmed verdict로 승격하지 않는다.
  ordered·entry-correlated 경계는 현 extractor군에서 fundamental하게 관찰 불가로 확인됐다(honest
  negative; Ledger의 entry-transition 행).

## 6.5 범위와 주장하지 않는 것

- **범위.** Linux TAR/USTAR, C0/C1/C2, fresh extract, controlled sentinel. archive format 일반,
  Windows NTFS semantics, 일반 kernel FS 취약점, 전체 TOCTOU/race, 완전한 symbolic execution,
  전체 archive-parser ambiguity는 범위 밖이다.
- **취약점 주장 없음.** 이 드래프트는 현재 취약점이나 새 CVE를 주장하지 않는다. known CVE는
  benchmark ground truth·root-cause 분석에만 쓴다(§1.5). **Interesting ≠ Vulnerable.**
- **참신성은 가설.** 참신성은 확정 사실이 아니라 검증 대상 가설이다(§3). "최초/기존연구에 없음" 류
  표현을 쓰지 않는다.
- **synthetic ≠ native.** synthetic 하너스 결과를 native
  증거로 승격하지 않는다. 비교 없이 effectiveness를 주장하지 않는다.

## 6.7 EXP-0·EXP-3·EXP-2 설계의 한계와 공개

- **informative censoring.** abort(관찰 무결성 실패 등)가 arm마다 다른 비율로 일어나면 right-censoring이
  **정보적**이 되어 arm 간 T_first 추정이 편향될 수 있다. 따라서 §4.6.2의 abort 민감도 **3정책**으로 결론 robustness를 보고한다 —
  **right-censored(CENSOR_AT_ABORT) 1차 + 완주-only(exclude) · abort=no-hit(censor-at-budget)**를
  `item5_first_contract_index.sensitivity`(#243)로 **셀 summary 레벨에서 산출**한다(RdsCellSummary의
  `disposition · executions · t_first/t_first_event · budget`만 사용, raw `.steps.jsonl` 불요 → EXP-0 실행 시
  즉시 가용; 완주 셀 정책 불변 · abort만 이동, EN-008 bracket). 분모의 abort 포함/제외는 항상 명시한다.
- **sentinel 이름 무작위화의 한계.** sentinel 이름을 seed 고정 무작위 생성기로 만들어도(§4.6.1), 위협 모델상
  그 이름은 세 arm 어휘에 동일하게 포함된다. 무작위화는 특정 이름에의 과적합을 줄일 뿐 **blind 발견을
  만들지 않으며**, 생성기 seed를 결과에 기록해야 재현·감사가 가능하다.
- **EXP-0 seed 사전 노출.** EXP-0 seed 중 9001–9004는 동결 전 비등록 실행에 이미 노출됐다(seed 9001은 10런, v2.1 미공개 6런·
  노출 원장 누락 3런; §5.6, 공식 리포트 편차 9). 이 출력은 결과가 아니지만, 사전 노출 자체가 EXP-0/EXP-3의 "신규 seed" 독립성 해석을 약화시킬 수 있으므로
  공개한다. 해석은 사전등록 판정에만 의존하고, 사전 노출 관측은 판정에 쓰지 않는다.
