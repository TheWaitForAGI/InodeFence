# 6. Limitations & Discussion (드래프트 v2)

이 절은 §5의 결과가 **무엇을 주장하지 않는지**를 명시한다. 한계를 숨기면 증거 사슬이 끊긴다.

## 6.1 벤치마크 결함의 깊이

현재 변이 문법에서 경계위반 입력은 seed에서 변이 1회 거리에 있다 [C-LIM1]. 이 한계를 빼고 탐색 난이도를 말하지 않는다.
등록 예측(§4.6.4, 사전등록 예측이며 결과 아님)의 근거는 문법 몬테카를로 상한 U_sim이다(exp2-v1 §1) [C-DESIGN].

## 6.2 확증 범위

확증 범위는 node-tar 한 계보(train 7.5.2, holdout 7.4.4)와 하드링크 identity 공유 계열이다. holdout 7.4.4는 고정 입력에서
train과 같은 계열의 위반을 내는 릴리스다 [C-LIM2]. 다른 추출기나 다른 결함 계열로 넓혀 쓰지 않는다 [C-LIM2].
다른 추출기 3개에 대한 적용(§5.5)은 오라클·어댑터 수준이며, 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다 [C-M4a].
Rust `tar` 프로브는 "적용된다"까지만 쓴다 [C-RUST].

## 6.3 snapshot oracle의 설계상 한계

- 오라클은 추출 전후 두 스냅숏을 비교하는 탐지기다. 위반 없음(`violated=False`)은 관찰 범위 안에서 위반 증거가 없다는
  뜻일 뿐이며, 두 시점 사이에 생겼다 사라진 변화, inode 번호 재사용, 샌드박스 밖 접근은 판정하지 못한다 [C-LIM3].
- entry 사이의 중간 상태 전이는 feedback 근거로만 쓰고 C0/C1/C2 판정으로 올리지 않는다. 관찰 실패는 위반 없음으로 세지
  않는다 [C-LIM3].
- 이것은 시험으로 확인한 성질이 아니라 오라클의 정의에서 나오는 설계상 한계다 [C-LIM3].

## 6.4 범위와 주장하지 않는 것

- **범위.** Linux TAR/USTAR, C0/C1/C2, fresh extract, controlled sentinel. archive format 일반,
  Windows NTFS semantics, 일반 kernel FS 취약점, 전체 TOCTOU/race, 완전한 symbolic execution,
  전체 archive-parser ambiguity는 범위 밖이다.
- **취약점 주장 없음.** 이 드래프트는 현재 취약점이나 새 CVE를 주장하지 않는다. known CVE는
  benchmark ground truth·root-cause 분석에만 쓴다(§1.5). **Interesting ≠ Vulnerable.**
- **참신성은 가설.** 참신성은 확정 사실이 아니라 검증 대상 가설이다(§3).
- **synthetic ≠ native.** synthetic 하너스 결과를 native 증거로 승격하지 않는다. 비교 없이 effectiveness를 주장하지 않는다.

## 6.5 등록 실험 설계의 한계와 공개

- **결과 전 결정의 범위.** 설계는 결과를 보기 전에 동결했지만, 표본 수·R 변형·예측은 공개된 비등록 파일럿을 보고
  정했다 [C-DESIGN] [C-PILOT].
- **결과 전 개정의 공개.** 동결 전에 등록을 고친 내용(예측 문장, 판정표의 비기각 행, N 결정 규칙, 범위 문구, 동결일
  정의)은 등록 실행을 시작하기 전의 개정이며 사전등록 변경 이력(exp2-v1 §8)에 공개돼 있다 [C-DESIGN].
- **informative censoring.** abort가 arm마다 다른 비율로 일어나면 우측중도절단이 정보적이 되어 arm 간 T_first 추정이
  편향될 수 있다. 그래서 abort 정책 세 가지(`censor-at-abort` 1차, `censor-at-budget`, `exclude`)를 함께 보고하고, 정책에
  따라 기각이 갈리면 "abort 가정에 좌우됨"으로 적는다(exp2-v1 §5) [C-DESIGN].
- **sentinel 이름 무작위화의 한계.** sentinel 이름을 seed 고정 무작위 생성기로 만들어도 위협 모델상 그 이름은 세 arm
  어휘에 똑같이 들어간다. 무작위화는 특정 이름에의 과적합을 줄일 뿐, 피해 경로 이름을 모르는 조건(blind)의 결과를
  만들지 않는다.
- **인프라 정지.** train과 holdout에서 HOST2 인프라 정지가 각각 1회 있었고, 직접 원인은 Docker Desktop API 무응답이며
  근본 원인은 확인하지 못했다 [C-OPS]. 원인이 생긴 층은 단정하지 않는다.
- **EXP-0 seed 사전 노출.** EXP-0 seed 9001–9004는 동결 전 비등록 도구 검증 실행에 이미 쓰였다(주장 목록의 "EXP-0 seed 사전 노출"
  공개 사실 행, 공식 리포트 편차 9). 그 출력은 결과로 쓰지 않는다 [C-EXP0].
- **근거 시점.** 근거 경로의 날짜와 SHA는 그 기록이 만들어진 시점의 것이다.
