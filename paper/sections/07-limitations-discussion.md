# 6. Limitations & Discussion (드래프트 v1)

이 절은 §5의 결과가 **무엇을 주장하지 않는지**를 명시한다. 한계를 숨기면 증거 사슬이 끊긴다.

## 6.1 M3 rate 우위는 CI 미분리(사전등록 판정)

- **rate 우위 CI 미분리.** 이 드래프트의 M3 주장은 **이름 획득 조건의 관찰**("외부 객체 이름을 어휘에 획득한
  조건에서만 자율 C1이 관찰됨"; retention·effect 피드백 자체의 인과는 미입증) *(구: "인과 — object-identity 관찰이 발견을 가능케 함", 2026-11-03 정정)*이고,
  "상태-인지 feedback이 무작위보다 빠르다/많이 찾는다"는 **rate 우위는 CI로 분리되지 않았다**(§5.3.3).
  동일 budget powered matched A1 vs A3full(disjoint seed {100..119})을 사전등록 후 판정한 결과 A3full
  1/10 vs A1 0/12로 매칭 Wilson CI가 겹친다(~0.1 효과 검정력 부족). CI 분리는 사람-게이트 대예산
  pilot(M3.4)이 필요하다.
  (2026-11-03 정정: 이 blind 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 입증된 것은 "외부 객체 이름의 관찰(어휘 획득)이 자율 C1의 필요조건"이지 (st_dev, st_ino) retention·스케줄링 피드백의 기여가 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.)
- **seed-rare.** 자율 C1 트리거는 budget 1500·65 seed 중 s11 하나뿐이다(재현 0/30). 정답이 사실상
  한 점(좁은 구성)이고 final-state C1/C2 oracle이 all-or-nothing이라 adaptive 탐색에 gradient가 거의
  없기 때문이다. 따라서 정책 간 rate 차이를 검출할 **검정력이 현재 없다.**
- **abort로 줄어든 denominator.** powered v2 {100..129}에서 A1 random floor는 30 seed 중 abort 11
  (완주 19), A3full은 abort 13(완주 17)으로, fail-closed abort를 no-hit로 세지 않는 프로토콜 때문에
  denominator가 줄고 CI가 넓어진다(A1 0/19 [0, 0.1682], A3full 1/17 [0.0105, 0.2698]). abort 사유는
  observer "evidence integrity failed(malformed_identity)"가 대부분(100–149 92셀 기준 A1 19/A3full 18)이고
  docker broker disconnected·container runtime cleanup inspect failed·remove failed가 나머지다. 이는 정직한
  right-censored 보고이며 "위반 없음의 증명"이 아니다. 이 드래프트 v1이 여기 적었던 "12 seed 중 5 abort,
  0/7 complete [0, 0.354]"는 powered run이 아니라 M3.3 A1 단독 대조 배치(seeds 11, 66–70 등)의 수치였다.

## 6.2 M4 자력발견은 right-censored 음성

- **oracle/adapter 일반성 ≠ 자력발견 일반성.** §5.4.1의 3-extractor 적용은 oracle/adapter 수준의
  target-agnostic성 증거이지, 2번째 extractor에서 fuzzer가 스스로 위반을 찾는다는 주장이 아니다.
- **자력발견 음성(2·3번째 extractor).** decompress 통합 판정(§5.4.3)은 맥+윈도우 pooled C1/C2 0/28
  (Wilson≤0.121)로 **사후 분석(post-hoc by_contract) 기준 음성이며 사전등록 판정이 아니다**(등록 hit 정의는
  discovered_violation = C0 포함; C1/C2 분리·0/28 합산은 사후 축), oras-go(§5.4.4)는 0/1로 **약한 음성**이다. 루프는 기능
  작동하고 path-boundary(C0)는 자력도달하나 identity/effect 위반은 이 예산에서 미도달이다. 이는
  generality≠self-discovery≠effectiveness 구분을 지킨 음성이다.

## 6.3 blind 발견 아님 (반드시 disclose)

M3의 자율 발견은 **blind 발견이 아니다.** 기존 외부 객체에 하드링크하려면 그 이름이 필요하고
퍼저는 그것을 **관찰(어휘 획득)**로 얻는다(이 이름 획득이 자율 C1의 필요조건이며, retention·effect 피드백 자체의
인과 기여는 어휘를 맞춘 R/D/S-u로 미분리) *(구: "관찰(가설이 지목한 object-identity feedback)로 얻는다", 2026-11-03 정정)*. 어휘·oracle에 대상 경로·
식별자·정답 seed·근접 보상은 하드코딩하지 않았으나, state-aware mutation 어휘 계열이
`outside`/`sentinel.txt` 토큰을 포함할 수 있다. 어떤 rediscovery 프레이밍에서도 이 사실을 명시한다.

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
- **synthetic ≠ native.** synthetic 하너스 결과(예: 단일경로 비교 하너스의 synthetic 검증)를 native
  증거로 승격하지 않는다. 비교 없이 effectiveness를 주장하지 않는다.

## 6.6 논의 — 중간 지점에서 방어 가능한 서사

방어 가능한 서사는 다음이다: 하나의 outcome 기반 generic oracle이 CVE 식별자 없이 두 root-cause를
통제 차분으로 포착하고(M2), 외부 객체 이름을 mutation 어휘에 넣지 **않으면** 자율
경계위반 발견에 도달하지 못한다(M3 blind 대조는 어휘 통제). 이는 "filesystem-security-state를 feedback으로
쓴다"는 가설에서 **외부 이름의 관찰(어휘 획득)이 자율 발견의 필요조건임을 보이는 데까지** 왔다는 뜻이다
*(구: "메커니즘이 실제로 발견을 구동함을 보이는 데까지 왔다", 2026-11-03 정정; retention·effect 피드백 자체의 인과는 R/D/S-u로 미분리)*. 그 feedback이
무작위보다 **얼마나 효율적인가**(rate)와 여러 extractor로 **얼마나 일반화되는가**(자력발견
effectiveness)는 powered 독립 반복으로 판정했고 **모두 효과 우위를 보이지 않았다**(rate CI 미분리·
decompress·oras-go 자력발견 음성). 음성·미분리도 정직한 결과로 보고한다.

(2026-11-03 정정: 이 blind 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 입증된 것은 "외부 객체 이름의 관찰(어휘 획득)이 자율 C1의 필요조건"이지 (st_dev, st_ino) retention·스케줄링 피드백의 기여가 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.) 따라서 위 "메커니즘이 실제로 발견을 구동함"은 "이름 획득 조건에서 자율 트리거가
관찰됨"으로 읽는다.


## 6.7 EXP-0/EXP-3 계획의 한계와 공개

- **informative censoring.** abort(관찰 무결성 실패 등)가 arm마다 다른 비율로 일어나면 right-censoring이
  **정보적**이 되어 arm 간 T_first 추정이 편향될 수 있다(기존 item-3에서 gradient arm C/D의 abort율이
  A/B보다 높았던 관찰과 정합). 따라서 §4.6.2의 abort 민감도 정책으로 결론 robustness를 보고한다 — 현재
  생성기(`analyze_exp0` item5)는 **right-censored(1차)**만 산출하고 **완주-only · abort=no-hit 2정책은 from-raw
  민감도(후속, 레인 6 보강 PR 대기)**다. 분모의 abort 포함/제외는 항상 명시한다.
- **sentinel 이름 무작위화의 한계.** sentinel 이름을 seed 고정 무작위 생성기로 만들어도(§4.6.1), 위협 모델상
  그 이름은 세 arm 어휘에 동일하게 포함된다. 무작위화는 특정 이름에의 과적합을 줄일 뿐 **blind 발견을
  만들지 않으며**, 생성기 seed를 결과에 기록해야 재현·감사가 가능하다.
- **EXP-0 seed 사전 노출.** EXP-0 seed(9001–9005)는 unregistered G1 smoke에서 이미 노출됐다(§5.6). 이
  smoke 출력은 결과가 아니지만, 사전 노출 자체가 EXP-0/EXP-3의 "신규 seed" 독립성 해석을 약화시킬 수 있으므로
  공개한다. 해석은 사전등록 판정에만 의존하고, 사전 노출 관측은 판정에 쓰지 않는다.
