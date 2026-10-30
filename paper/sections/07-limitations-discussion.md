# 6. Limitations & Discussion (드래프트 v1)

이 절은 §5의 결과가 **무엇을 주장하지 않는지**를 명시한다. 한계를 숨기면 증거 사슬이 끊긴다.

## 6.1 M3 rate 우위는 미판정

- **rate 우위 열림.** 이 드래프트의 M3 주장은 **인과**("object-identity 관찰이 발견을 가능케 함")이고,
  "상태-인지 feedback이 무작위보다 빠르다/많이 찾는다"는 **rate 우위는 아직 판정하지 않았다**(§5.3.3).
  동일 budget powered matched A1 vs A3full 독립 반복이 끝나야 판정 가능하다(PENDING).
- **seed-rare.** 자율 C1 트리거는 budget 1500·65 seed 중 s11 하나뿐이다(재현 0/30). 정답이 사실상
  한 점(좁은 구성)이고 final-state C1/C2 oracle이 all-or-nothing이라 adaptive 탐색에 gradient가 거의
  없기 때문이다. 따라서 정책 간 rate 차이를 검출할 **검정력이 현재 없다.**
- **abort로 줄어든 denominator.** A1 random control(budget 2000)은 12 seed 중 5개가 fail-closed
  abort로 denominator에서 제외돼 clean exact C1이 **0/7 complete**로 집계됐다(Wilson 95% CI
  [0, 0.354]). abort를 no-hit로 세지 않는 프로토콜 때문에 denominator가 줄고 CI가 넓어진다 — 이는
  정직한 right-censored 보고이며 "위반 없음의 증명"이 아니다.

## 6.2 M4 자력발견은 right-censored 음성

- **oracle/adapter 일반성 ≠ 자력발견 일반성.** §5.4.1의 3-extractor 적용은 oracle/adapter 수준의
  target-agnostic성 증거이지, 2번째 extractor에서 fuzzer가 스스로 위반을 찾는다는 주장이 아니다.
- **decompress 자력발견 음성.** M4.4 native run은 양 arm 0 C1/C2(right-censored 음성)다. 루프는
  기능 작동하나 exact 위반에 미도달했고, 1-seed 검정력 없는 음성이라 **미판정**이다(powered 반복은
  §5.4.3 PENDING).

## 6.3 blind 발견 아님 (반드시 disclose)

M3의 자율 발견은 **blind 발견이 아니다.** 기존 외부 객체에 하드링크하려면 그 이름이 필요하고
퍼저는 그것을 **관찰(가설이 지목한 object-identity feedback)**로 얻는다. 어휘·oracle에 대상 경로·
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
통제 차분으로 포착하고(M2), 그 oracle이 평가하는 바로 그 object-identity 관찰이 **없으면** 자율
경계위반 발견에 도달하지 못한다(M3 blind 대조). 이는 "filesystem-security-state를 feedback으로
쓴다"는 가설의 **메커니즘이 실제로 발견을 구동함**을 보이는 데까지는 왔다는 뜻이며, 그 feedback이
무작위보다 **얼마나 효율적인가**(rate)와 2번째 extractor로 **얼마나 일반화되는가**(자력발견
effectiveness)는 powered 독립 반복(PENDING)으로 열려 있다.
