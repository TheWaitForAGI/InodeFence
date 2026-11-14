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

이 프로젝트는 TAR fuzzing, hardlink/symlink 공격, entry order, filesystem-state fuzzing, outside-root
write **자체가 새롭다고 주장하지 않는다.** 이들은 선행연구가 이미 다룬 영역이다(§4). 참신성은
**검증해야 할 가설**로 취급하며, 이 드래프트는 가설 전체의 최종 성능 우위를 입증했다고 주장하지
않는다.

## 1.3 정직 프레이밍 — 이 드래프트가 방어하는 것과 열어 두는 것

이 드래프트가 방어하는 주 주장은 다음 하나다.

- **주 주장 (M2, observed):** 하나의 generic identity oracle이 릴리스 id·정답 경로 하드코딩 없이
  두 root-cause를 통제 차분으로 포착한다. 이것은 "CVE 식별자를 oracle에 심지 않는다"는 연구
  규칙(아래 1.5)의 실증이다.

## 1.4 기여 (좁은 명제로 기술)

선행연구 포지셔닝([`../../docs/research/design/related-work-positioning.md`](../../docs/research/design/related-work-positioning.md))을
준수하여, 기여를 다음의 **좁은 명제**로만 기술한다.

1. **루프의 실제 동작(M1).** 실제 node-tar에 대해 입력→실행→entry별 상태 관찰→oracle→feedback→
   다음 mutation 루프가 하나의 명령으로 반복 재현된다(§5.1).
2. **outcome 기반 oracle의 2-root-cause 관통(M2).** 추출 객체↔외부 객체 identity 공유라는 하나의
   generic 조건이 CVE-2026-23745와 CVE-2026-24842에 대응하는 두 통제 차분을 모두 포착한다(CVE 대응과 회귀 원인은 추론, §5.2).
3. **oracle/adapter 수준 일반성(M4).** 동일 generic oracle(코드 불변)이 3개 독립 extractor에
   target-agnostic하게 적용된다(§5.4). 이는 **oracle/adapter 수준**이며 퍼저 탐색의 일반성이나
   효과에 대한 주장이 아니다.

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
object-identity feedback을 기술한다. §5는 M1·M2·M4의 방어 가능한 결과와 EXP-0 등록 실행을 보고한다.
§6은 한계와 논의, §7은 결론이다.
