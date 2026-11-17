# 탐색 정책 `pre-violation-signal-v1-novelty-applied-split-v1` (#511, exploratory)

> 상태: **IMPLEMENTED·TESTED(합성 생산자만)**. 실제 대상에서 돈 적 없다. 탐색 성능에 대한 주장은 없다.
> 근거: #511 설계 메모(비공개 Drive)와 W4 판정(2026-11-18). 결정 기록: D063(확증 실험 중단, v2 엔진은 탐색·후속 분석용).

## 무엇인가
- `EffectCampaignConfig.exploration_policy`로만 켜는 탐색 정책이다. 기본값 `None`이면 아무것도 바뀌지 않는다(기존 보고서·golden 바이트 동일).
- `EffectSearchPolicy` 밖의 별도 형 `ExplorationPolicyId`다(`feedback/exploration_search.py`). `EffectSearchPolicy`는 수정 금지 파일에 있고 다시 넓히지 않는다(W4 판정 7, D062는 일회 예외).
- `search_policy`는 선언된 기준 S-u(`effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1`)여야 한다(설정 검증).
- 단계 기록의 `feedback`은 S-u 진단 채널이다. 기록용이고 이 정책의 결정에 쓰이지 않는다. 사슬 R이 seed-restart 상태에 기록을 맡기는 것과 같은 방식이다.

## 위반 이전 신호 (`feedback/pre_violation.py`)
관찰된 효과 이벤트에서만 계산하는 **영역 수준** 신호다. 영역은 `path_region`의 하네스 배치 규칙(추출 루트 / 하네스 / 외부)이고, 이 규칙이 C0 경계이기도 하다.

| 종류 | 조건 |
|---|---|
| `link-escape-attempt` | hardlink의 LINK 연산. 영향 경로가 루트 밖이고, 원래 대상이 절대이거나 `..`로 시작함(모양 버킷은 경계 시도 키와 같음). 결과 무관 |
| `link-external-resolve` | LINK 연산의 영향 경로에 외부 영역이 있음 |
| `symlink-external-resolve` | SYMLINK 연산의 영향 경로에 외부 영역이 있음 |
| `in-root-identity-relation` | hardlink identity 관계 생성, 영향 경로가 **모두** 루트 안. 하나라도 외부면 내지 않는다 |
| `refused-operation` | 결과가 `succeeded`가 아닌 연산(결과 열거형만 봄. 대상 오류 문구는 읽지 않음) |
| `same-path-replacement` | namespace 교체 또는 identity 관계 제거, 영향 경로가 모두 루트 안 |

- 자격: integrity 유효, 완결, 종료가 `success` 또는 `rejected`인 trace(경계 시도 키와 같은 문).
- **읽지 않는 것**(W4 선): oracle 판정·위반 지문, 보호 경로 목록, sentinel 이름·id, 외부 경로의 보호 여부·어느 객체인지·거리. 외부 영역 안에서는 "외부"보다 잔 구분을 쓰지 않는다.
- 입력 구조 신호(분류기 축)는 쓰지 않는다(W4 판정 3). 분류기는 분석 기록 전용이다.

## 보존, 부모 선택, 스케줄러
- 보존: seed(기본 코퍼스)와, 캠페인에서 처음 본 신호를 낸 실행 case. effect 키(정규 서명이 보호 목록을 읽음)·위반 지문·판정은 쓰지 않는다.
- 부모: 보존된 case에서 균등 추첨.
- 스케줄러 `PreViolationNoveltyScheduler`(`effect_scheduler.py`):
  - 보상은 새 신호가 있으면 1, 없으면 0(이진 새로움, W4 판정 4).
  - 보상은 그 실행에서 **적용된** 연산에 균등 분할한다. no-op은 받지 않고, 적용된 연산이 없으면 아무도 받지 않는다(W4 판정 5).
  - 가중치는 고정 소수점(1 = 60 단위, 6개까지 정확히 나뉨)이고, 상한은 8, 감소는 없다.
  - 증거 형 `PreViolationSchedulerEvidence`: 기존 필드에 `new_signals`, `credited_operators`, `signal_retained`, `weight_unit`을 더한다.
- 기록: 보고서 `config.exploration_policy`(켰을 때만), 변이 step의 `exploration` 키(`new_signals`, `signal_retained`, `credited_operators`, `weight_unit`). `selection.corpus_admission`은 이 정책의 보존을 따른다.

## 분리 확인 (W4 판정 1, `tests/test_exploration_pre_violation.py`)
- (a) import 그래프: 신호 모듈은 `inodefence.model`·`model.filesystem`·`feedback.effect`(탈출 모양 버킷)만 import한다. 신호·탐색 모듈은 oracle·fingerprint·sentinel·observer 모듈을 import하지 않고, 코드에서 `protected_paths`·위반 값을 읽지 않는다.
- (b) 보호 목록과 sentinel 이름을 바꾸거나 섞어도 결정이 바이트 동일하다:
  - 캠페인 전체: 신호, 보존, 부모 추첨, 보상, 가중치.
  - v2 정책은 하네스 BEFORE 이름(sentinel 이름 포함, 위협 모델상 모든 arm의 어휘)으로 자식을 만든다. 이름을 바꾸면 만들어지는 입력이 달라지는데, 이것은 입력 생성이지 feedback이 아니다. 그래서 캠페인 전체 확인은 관찰 이름을 읽지 않는 변이 정책으로 하고, v2는 case별 신호가 같은지로 확인한다.

## 실행 경로와 한계
- 공유 런처(`scripts/run_effect_demo.py`와 그것을 부르는 스크립트)는 이 정책을 고를 수 없다. `--policy` 선택지가 `EffectSearchPolicy` 값이기 때문이다. 지금은 설정을 직접 만드는 곳(테스트, 합성 생산자)에서만 돈다.
- 실제 대상 경로에는 공유 경로 파일 변경이 필요하고, 이것은 지웅 결정 사항이다(#511 메모 §7.1). 그 결정 전에는 단일 arm 타당성 기록(W4 판정 6)도 하지 않는다.
- `search_policy`만 읽는 등록 판독기(`rds_report`)는 이 정책을 S-u와 구분하지 못한다. G1 v2는 쌍 (`search_policy`, `exploration_policy`)으로 arm을 식별한다.
- 승격: 단일 arm 타당성 + 속성 테스트로는 **선택 가능한** 정책(exploratory)까지만이다. 제품 기본값이나 "더 잘 탐색한다"는 주장에는 사전등록된 비교가 필요하다(W4 판정 8). 기본값 변경은 지웅 결정이다.
