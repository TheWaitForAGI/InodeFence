# 1. Introduction (드래프트 v1)

## 1.1 배경과 동기

TAR archive extraction은 공격자가 제어하는 입력(아카이브)이 신뢰 경계를 넘어 filesystem에
object를 생성·연결·수정하게 만드는 전형적 통로다. hardlink·symlink·entry 처리 순서·링크 타깃이
결합되면, extraction 결과 object가 extraction 디렉터리 밖의 object와 같은 filesystem identity를
공유하거나(object identity 위반) 보호된 외부 object를 변경하는(external effect 위반) 상황이 생길
수 있다. 이런 경계위반을 **문자열 수준의 path 검사**만으로 잡으려 하면, 서로 다른 path가 같은
underlying object를 가리키는 경우를 놓친다.

## 1.2 연구 질문과 가설

이 프로젝트의 핵심 연구 질문은 다음이다(상세: [`../../docs/research/design/research-questions.md`](../../docs/research/design/research-questions.md)).

> 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래서, filesystem security state(C1 identity·C2 effect)를
> retention·스케줄링 피드백으로 쓰는 탐색이 **무작위 탐색**과 **구조 커버리지 탐색**보다 첫 경계위반까지의
> 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가?
> (핵심 RQ, research-questions v2. 위협 모델 전제: 공격자는 피해 경로 이름 — 보호 대상 외부 객체의
> 추출 루트 기준 상대 경로 — 을 알며 세 arm 어휘에 동일하게 포함한다. blind 발견을 주장하지 않는다.)

(2026-11-03 정정: 드래프트 v1이 여기 적었던 H1 — "특정 CVE PoC나 고정된 공격 패턴을 하드코딩하지
않고, filesystem-security-state(특히 object identity와 external effect)를 feedback으로 사용하면
archive extraction의 보안 경계위반을 더 효과적으로 탐색할 수 있는가? (H1)" — 는 **폐기**됐고 위 v2
핵심 RQ·H-A로 대체됐다. research-questions v2 '폐기·대체 기록' 참조.)

이 프로젝트는 TAR fuzzing, hardlink/symlink 공격, entry order, filesystem-state fuzzing, outside-root
write **자체가 새롭다고 주장하지 않는다.** 이들은 선행연구가 이미 다룬 영역이다(§4). 참신성은
**검증해야 할 가설**로 취급하며, 이 드래프트는 가설 전체의 최종 성능 우위를 입증했다고 주장하지
않는다.

## 1.3 정직 프레이밍 — 이 드래프트가 방어하는 것과 열어 두는 것

중간 지점의 솔직한 보고로서, 이 드래프트는 **두 개의 방어 가능한 주 주장**과 **하나의 보조 질문
(사전등록 판정: rate CI 미분리)**을 분리한다.

- **주 주장 A (M2, observed):** 하나의 generic identity oracle이 릴리스 id·정답 경로 하드코딩 없이
  두 root-cause를 통제 차분으로 포착한다. 이것은 "CVE 식별자를 oracle에 심지 않는다"는 연구
  규칙(아래 1.5)의 실증이다.
- **주 주장 B (M3, 이름 획득 조건의 관찰):** 외부 객체 이름을 mutation 어휘에 획득하면 이 자율 경계위반을
  관찰하고, 그 이름을 뺀 조건에서는 관찰되지 않았다(구조적 불가로 단정하지 않는다). 이는 **어휘 제거 대조에서 관찰된 이름 획득 조건**이지
  retention·effect 피드백 자체의 인과 명제도 rate 우위도 아니다(피드백 인과는 어휘를 맞춘 R/D/S-u로 미분리)
  *(구: "blind 대조로 입증한 인과 명제", 2026-11-03 정정)*.
  (2026-11-03 정정: 이 어휘 제거 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 관찰된 것은 외부 객체 이름을 어휘에 넣은 조건에서 자율 C1이 나왔고 그 조건 밖에서는 관찰되지 않았다는 것이다(구조적 불가로 단정하지 않는다). 이는 (st_dev, st_ino) retention·스케줄링 피드백의 기여를 보인 것이 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.)
- **보조 질문 (rate 우위, v1 H1에서 유래, 사전등록 판정: CI 미분리):** 상태-인지 feedback이 무작위보다 **더
  빨리/더 많이** 경계위반을 찾는가(rate 우위). powered matched 독립 반복(budget 2000, disjoint seed
  {100..129}, A1 0/19 vs A3full 1/17)으로 판정한 결과 매칭 Wilson CI가 겹쳐 **rate 우위는 미입증**이다(~0.06 효과 검정력 부족;
  신규 seed s101에서 재현 1건 추가, 인과 강화 아님 *(구: "메커니즘은 멀티-seed로 강화", 2026-11-06 정정)*). 주 주장이 아니며 CI 분리는 사람-게이트 대예산
  pilot이 필요하다(§5.3.3, §6).

## 1.4 기여 (좁은 명제로 기술)

선행연구 포지셔닝([`../../docs/research/design/related-work-positioning.md`](../../docs/research/design/related-work-positioning.md))을
준수하여, 기여를 다음의 **좁은 명제**로만 기술한다.

1. **루프의 실제 동작(M1).** 실제 node-tar에 대해 입력→실행→entry별 상태 관찰→oracle→feedback→
   다음 mutation 루프가 하나의 명령으로 반복 재현된다(§5.1).
2. **outcome 기반 oracle의 2-root-cause 관통(M2).** 추출 객체↔외부 객체 identity 공유라는 하나의
   generic 조건이 CVE-2026-23745와 CVE-2026-24842에 대응하는 두 통제 차분을 모두 포착한다(CVE 대응과 회귀 원인은 추론, §5.2).
3. **이름 획득 조건의 자율 발견 관찰(M3).** 외부 객체 이름을 어휘에 획득한 조건에서만 자율 발견이 관찰됨을
   어휘 제거 대조로 보인다(§5.3); retention·effect 피드백 자체의 인과는 미입증이다 *(구: "발견의 인과 입증", 2026-11-03 정정)*. blind 발견이 아니라는 점과 seed-rare라는 점을 함께 명시한다.
   (2026-11-03 정정: 이 어휘 제거 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 관찰된 것은 외부 객체 이름을 어휘에 넣은 조건에서 자율 C1이 나왔고 그 조건 밖에서는 관찰되지 않았다는 것이다(구조적 불가로 단정하지 않는다). 이는 (st_dev, st_ino) retention·스케줄링 피드백의 기여를 보인 것이 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.)
4. **oracle/adapter 수준 일반성(M4).** 동일 generic oracle(코드 불변)이 3개 독립 extractor에
   target-agnostic하게 적용된다(§5.4). 이는 **oracle/adapter 수준**이며 fuzzer 자력 발견의 일반성이나
   effectiveness 주장이 아니다.

## 1.5 연구 불변식

이 드래프트와 그 근거가 되는 모든 실험은 다음 불변식을 따른다.

- CVE 식별자나 known PoC byte sequence를 oracle 판정 조건에 넣지 않는다(일반화된 Security Contract로
  표현).
- 알려진 CVE PoC를 rediscovery 실험의 기본 fuzzing seed로 쓰지 않는다. known CVE는 benchmark
  ground truth와 root-cause 분석에만 쓴다.
- observed(실행 출력으로 확인)와 inferred(추론)를 구분한다.
- synthetic 결과를 native 증거로 승격하지 않는다.
- 비교 없이 effectiveness를 주장하지 않는다.

## 1.6 문서 구성

§2는 Linux filesystem semantics·TAR extraction·Security Contract(C0/C1/C2)와 threat model을 정리한다.
§3은 선행연구와의 정직한 중첩/차별을 서술한다. §4는 루프 구조와 generic/target-specific 분리,
object-identity feedback을 기술한다. §5는 M1–M4의 방어 가능한 결과와 powered 판정(음성·미분리) 소절을 보고한다.
§6은 한계와 논의, §7은 결론이다.
