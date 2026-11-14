# 1. Introduction (드래프트 v2)

## 1.1 배경과 동기

TAR archive extraction은 공격자가 제어하는 입력(아카이브)이 신뢰 경계를 넘어 filesystem에
object를 생성·연결·수정하게 만드는 전형적 통로다. hardlink·symlink·entry 처리 순서·링크 타깃이
결합되면, extraction 결과 object가 extraction 디렉터리 밖의 object와 같은 filesystem identity를
공유하거나(object identity 위반) 보호된 외부 object를 변경하는(external effect 위반) 상황이 생길
수 있다. 이런 경계위반을 **문자열 수준의 path 검사**만으로 잡으려 하면, 서로 다른 path가 같은
underlying object를 가리키는 경우를 놓친다.

## 1.2 연구 질문

이 프로젝트의 핵심 연구 질문은 다음이다(상세: [`../../docs/research/design/research-questions.md`](../../docs/research/design/research-questions.md)).

> 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래서, filesystem security state(C1 identity·C2 effect)를
> retention·스케줄링 피드백으로 쓰는 탐색이 **무작위 탐색**과 **구조 커버리지 탐색**보다 첫 경계위반까지의
> 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가?

위협 모델 전제로 공격자는 피해 경로 이름(보호 대상 외부 객체의 추출 루트 기준 상대 경로)을 알고, 그 이름은 세 arm
어휘에 똑같이 들어간다(§2.4). 이 질문(H-A)은 등록 실험으로 판정하며 아직 미검증이다 [C-HA]. 판정은 holdout 확증
검정 하나로만 하고(§4.6), 그 결과는 본실험 결과 자리(봉인 해제 뒤 기입)다 [S-HOLDOUT].

이 프로젝트는 TAR fuzzing, hardlink/symlink 공격, entry order, filesystem-state fuzzing, outside-root
write **자체가 새롭다고 주장하지 않는다.** 이들은 선행연구가 이미 다룬 영역이다(§3). 참신성은
**검증해야 할 가설**로 취급한다.

## 1.3 이 드래프트가 방어하는 것과 열어 두는 것

- **방어하는 것.** 하나의 identity 오라클이 릴리스 번호·정답 경로 없이 node-tar의 두 결함을 통제 차분으로
  구분한다 [C-M2]. 같은 오라클이 다른 추출기 3개에 어댑터 수준으로 적용된다 [C-M4a]. 루프는 실제 node-tar에서
  반복 실행된다 [C-M1]. 측정 사슬은 양성·음성 대조로 확인했다 [C-PC].
- **열어 두는 것.** 상태 피드백이 첫 경계위반까지의 실행 수를 줄이는가(H-A)는 미검증이다 [C-HA]. train의 arm별
  결과와 holdout 확증 판정은 본실험 결과 자리(봉인 해제 뒤 기입)다 [S-TRAIN] [S-HOLDOUT].

## 1.4 기여 (좁은 명제로 기술)

선행연구 포지셔닝([`../../docs/research/design/related-work-positioning.md`](../../docs/research/design/related-work-positioning.md))을
준수하여, 기여를 다음의 **좁은 명제**로만 기술한다.

1. **outcome 기반 identity 오라클의 통제 차분(M2).** 판정 조건에 릴리스 번호나 정답 경로가 없는 오라클 하나가
   node-tar 5개 릴리스(7.5.2·7.5.3·7.5.6·7.5.7·7.5.8)와 고정 입력 2개에서 CVE-2026-23745와 CVE-2026-24842를
   구분한다. 통제 재현이며 퍼저의 탐색 결과가 아니다(§5.2) [C-M2].
2. **오라클·어댑터 수준 적용(M4).** 같은 오라클이 코드 변경 없이 python-tarfile(추출 필터 설정 토글 비교),
   oras-go, decompress(릴리스 비교)에 적용된다(§5.5). 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다 [C-M4a].
3. **루프의 실제 동작(M1).** 실제 node-tar에서 입력→실행→entry별 관찰→판정→feedback→다음 변이 선택 루프가
   한 명령으로 반복 실행된다(§5.1) [C-M1].
4. **사전등록 평가 절차.** 같은 어휘·같은 예산의 세 arm, 결과 전 동결, train/holdout 분리, 결과 가림
   [C-DESIGN]과, raw 매니페스트·증거 사슬 점검·호스트 적격성으로 이루어진 재현성 인프라(§4.5–§4.6) [C-INFRA].

## 1.5 연구 불변식

이 드래프트와 그 근거가 되는 모든 실험은 다음 불변식을 따른다.

- CVE 식별자나 known PoC byte sequence를 oracle 판정 조건에 넣지 않는다(일반화된 Security Contract로
  표현).
- 알려진 CVE PoC를 탐색 실험의 seed로 쓰지 않는다. known CVE는 benchmark ground truth와 root-cause 분석에만 쓴다.
- observed(실행 출력으로 확인)와 inferred(추론)를 구분한다.
- synthetic 결과를 native 증거로 승격하지 않는다.
- 비교 없이 effectiveness를 주장하지 않는다.

## 1.6 문서 구성

§2는 Linux filesystem semantics·TAR extraction·Security Contract(C0/C1/C2)와 threat model을 정리한다.
§3은 선행연구와의 중첩·차이를 서술한다. §4는 루프 구조, generic/target-specific 분리, 상태 피드백,
등록 실험 설계를 기술한다. §5는 통제 재현·측정 사슬 대조·등록 실행 EXP-0·GO 판정과 본실험 결과 자리를
보고한다. §6은 한계, §7은 결론이다.
