# InodeFence 결과보고서 (교내 학술대회 제출용 초안)

> **초안 안내 — 제출 전에 이 상자를 지운다.**
>
> - **양식 UNVERIFIED.** 작성 세션에서 붙임3 결과보고서 서식을 열지 못했다(worktree 세션에서 Windows 경로
>   접근이 차단됨). 아래 절 구조는 일반 결과보고서 구조다. 서식과 대조해 절 이름과 순서를 맞춘다.
> - **제출 요건 UNVERIFIED.** 이전 세션이 붙임 원문에서 옮겨 적은 기록은 다음과 같다: 결과보고서 HWP+PDF,
>   소개영상 5분 이하, 생성형 AI 사용 내역 기입 필수, 결과물 기한 2026-11-30. 이번에 원문과 다시 대조하지 못했다.
> - **일정.** 결과보고서·영상 제출 2026-11-26, 최종발표 2026-11-30(오케스트레이터가 사용자 확정 일정으로 전달). 위 붙임 기록의
>   "결과물 기한 11-30"과 다르므로 서식을 대조할 때 함께 확인한다.
> - **수치 규칙.** 정량 문장 끝에 증거 각주를 둔다. 미머지 PR을 가리키는 각주는 머지 후 경로를 다시 확인한다.
> - **미실행.** EXP-3과 EXP-2는 실행 전이다. §7.6과 §7.7은 자리만 있다.
> - **표·그림 요구 사항**은 [표·그림 요구 목록](results-artifact-requirements.md)에 있다.

| 항목 | 내용 |
| --- | --- |
| 과제명 | InodeFence: 파일시스템 보안 상태를 피드백으로 쓰는 TAR 추출 경계위반 탐색 프로토타입 |
| 팀명·학과·학번·지도교수 | TBD (사람이 기입) |
| 역할 | 지웅: Core·Integration / 주언: Feedback·Evaluation / 규민: Runtime·Target / 민찬: Observation·Oracle·Demo |
| 저장소 공개 범위 | TBD (외부 공개는 사람 승인 사항) |

## 1. 요약

InodeFence는 TAR 아카이브 추출 과정의 보안 경계위반을 탐색하는 연구 프로토타입이다. 판정과 피드백에 CVE 식별자·PoC·고정 공격 패턴·대상 경로·sentinel 이름을
넣지 않고, 추출 결과의 파일시스템 보안 상태(외부 객체와의 identity 공유, 보호 대상 sentinel의 변화)를
관찰해 쓴다. 피해 경로 이름은 위협 모델 전제로 어휘에 포함하므로 blind 발견은 주장하지 않는다.

지금까지 확인한 것은 다음 네 가지다.

1. 실제 node-tar에서 입력 생성부터 다음 mutation 선택까지의 루프가 `make demo` 하나로 돈다(M1, TESTED).[^m1]
2. 손으로 만든 하드링크 fixture로 경계위반을 통제 재현했다. node-tar 7.5.2에서는 추출 객체가 외부 참조 파일과
   inode를 공유하고 7.5.3은 같은 입력을 거부한다(M2, TESTED).[^m2]
3. 퍼저의 자력 경계위반은 **이름 획득 조건의 관찰(피드백 인과 미입증)** 수준이다(M3).[^m3]
4. 같은 generic oracle이 3개 extractor에 adapter 수준으로 적용된다(M4, oracle 수준 일반성).[^m4]

**이 보고서는 핵심 연구 질문에 아직 답하지 않는다.** 동일 어휘·동일 예산 비교(EXP-3)는 2026-11-18 사전등록 예정이며
실행 전이다. EXP-0 등록 실행은 15셀을 모두 완주했지만 인프라 측정이고 가설 검정이 아니다.[^exp0-run]

## 2. 연구 배경과 필요성

TAR 추출은 공격자가 제어하는 입력이 신뢰 경계를 넘어 파일시스템에 객체를 만들고 연결하는 통로다. 하드링크와
심볼릭 링크, entry 순서, 링크 타깃이 결합되면 추출된 객체가 추출 디렉터리 밖 객체와 같은 `(st_dev, st_ino)`를
공유하거나 보호 대상 외부 객체를 바꿀 수 있다. 서로 다른 경로가 같은 객체를 가리킬 수 있으므로, 경로 문자열만
검사하면 이런 identity 관계를 놓칠 수 있다.

## 3. 연구 목표와 연구 질문

**핵심 연구 질문.** 피해 경로 이름을 아는 동일 어휘·동일 예산 아래서, filesystem security state(C1 identity·C2
effect)를 retention·스케줄링 피드백으로 쓰는 탐색이 무작위 탐색과 구조 커버리지 탐색보다 첫 경계위반까지의 실행
수를 줄이고 고유 위반 입력을 더 많이 찾는가?[^rq]

**위협 모델 전제.** 공격자는 피해 경로 이름을 안다고 가정하고 그 이름을 세 arm의 어휘에 똑같이 넣는다. 따라서 이
연구는 blind 발견을 주장하지 않는다.

**가설.** H-A(주 가설)는 위 질문의 피드백 정책 비교이고, H-B는 generic oracle이 여러 extractor의 취약·수정 쌍을
손 fixture로 구분하는지 묻는다.[^rq] H-A는 미판정이다. 참신성은 확정된 사실이 아니라 검증 대상 가설로 둔다.

## 4. 위협 모델과 판정 기준

대상은 고정 버전의 TAR extractor이고 공격면은 공격자가 제어하는 아카이브 바이트다. 실제 host의 민감 파일은 대상으로
쓰지 않으며, disposable sandbox 안의 sentinel만 쓴다.[^contracts]

| 계약 | 이름 | 위반 후보 조건 |
| --- | --- | --- |
| C0 | Path Boundary Confinement | 추출 루트 밖 경로에서 생성·삭제·identity/type 교체가 생김 (기준선, 이 연구의 기여로 주장하지 않음) |
| C1 | Object Identity Confinement | 추출 내부 객체가 보호된 외부 sentinel과 같은 `(st_dev, st_ino)`를 공유함 |
| C2 | External Effect Noninterference | 보호된 sentinel의 존재·종류·inode·내용·크기·mode·nlink·uid/gid·mtime/ctime이 바뀜 |

Oracle의 위반 판정은 후보다. 확정 취약점으로 보려면 재현과 root-cause 검토가 따로 필요하다. 판정 조건에는 CVE
식별자, 릴리스 번호, 정답 경로를 넣지 않는다.[^contracts]

## 5. 시스템 설계와 구현

한 testcase는 다음 순서로 흐른다.

```text
Seed Generator -> Structure Mutator -> TAR Builder -> Target Adapter
  -> State Observer -> Security Oracle -> Feedback / Corpus -> 다음 mutation
```

- **generic 부분**(mutator, observer, oracle, feedback)은 대상 extractor를 모른다. Observer는 사실만 기록하고,
  Oracle은 계약을 적용할 뿐 파일시스템에 접근하지 않는다.
- **target 부분**(adapter, worker, recipe)만 extractor별 실행 방법을 안다. 격리된 컨테이너에서 실행한다.
- **피드백**은 관찰된 상태의 정규화 키를 받아 새 상태나 새 위반이면 입력을 corpus에 남기고 다음 mutation의 바탕으로
  쓴다. 새 상태 키의 수는 탐색 거동이며 효과의 척도가 아니다(EN-008).

상세 설계는 [§4 Method](../sections/05-method.md)에 있다.

## 6. 실험 설계

| 실험 | 목적 | 상태 |
| --- | --- | --- |
| EXP-0 | 인프라 측정(처리량, abort, dense 신호). H-A 검정 아님 | 등록 실행 완료 |
| EXP-3 | H-A 본실험(R/D/S-u, 동일 어휘·동일 예산) | **사전등록 예정(11/18), 실행 예정** |
| EXP-2 | EXP-3 결과에 사전등록 규칙을 적용해 GO일 때만 수행 | 조건부, 미정 |

- **비교 arm.** R(retention 없음), D(구조 커버리지), S-u(identity/effect/boundary-attempt 상태 키). 어휘, seed, 예산,
  이미지, oracle, operator 선택은 같고 retention 정책만 다르다.[^rq]
- **지표.** T_first는 첫 `C1 ∨ C2`까지의 실행 수이고 우측중도절단한다(무hit는 예산에서, abort는 abort 시점에서).
  U_viol은 고유 위반 입력 수다. C0만 나온 step은 hit가 아니다.[^rq]
- **판정.** 결과를 본 뒤 규칙을 바꾸지 않고 [판정 시나리오 표](../../docs/research/design/research-questions.md)를 그대로
  적용한다. 전 arm 위반 0(⑤)이나 S ≤ R(⑧)도 그대로 보고한다.
- **EXP-3 초안 설계.** 예산 2000, 1차 지표 T_first, 확증 검정은 seed-block 순열 로그랭크와 holdout 패밀리의 Holm
  보정이다. 동결 전 초안 기준이며 seed 수와 hold-out 정체는 11/18에 확정한다.[^exp3-draft] *(실험 구조(2단계 여부), 대상 타깃 범위,
  비기각 판정 규칙, U_viol 지위는 파일럿 후 재판정 대기)*

## 7. 결과

증거 수준 어휘(TESTED 등)는 [Capability Ledger](../../docs/STATUS.md)를 따른다. observed는 실행 출력으로 확인한 것,
inferred는 추론한 것이다.

### 7.1 M1: 실제 node-tar 루프 (TESTED)

입력 생성 → node-tar 실행 → entry별 중간 상태 관찰 → C0/C1/C2 판정 → 피드백 → 다음 mutation 선택이 `make demo` 하나로
돈다.[^m1]

2026-11-06 재실행(observed): node-tar 7.5.22에서 20 step을 완주했고 C0/C1/C2 위반은 0건이다. 두 번 실행한 20개 step 줄이
서로 같았다.[^m1-run] 피드백이 선택에 연결되는 것도 출력으로 확인된다. corpus가 4에서 7로 늘고
`add_entry` 가중치가 1에서 3으로 올랐다.[^m1-run] 이는 동작 확인이며 탐색 성능이나 취약점 발견을 뜻하지 않는다.

### 7.2 M2: 실제 경계위반 통제 재현 (TESTED)

손으로 만든 결정론적 하드링크 fixture 2종을 고정 릴리스 5개에 넣어, 추출 객체가 외부 참조 파일과 inode를
공유하는지 봤다.[^m2]

| 릴리스 | 최상위 하드링크 | 중첩 하드링크 |
| --- | --- | --- |
| 7.5.2 | **공유** (nlink 1→2) | **공유** (nlink 1→2) |
| 7.5.3 | 거부 | 거부 |
| 7.5.6 | 거부 | **공유** (nlink 1→2) |
| 7.5.7 | 거부 | 거부 |
| 7.5.8 | 거부 | 거부 |

![node-tar 릴리스별 하드링크 identity verdict 그리드](../figures/m2-cross-release-evidence.png)

*그림 7-1. 릴리스별 verdict(observed). CVE 대응과 회귀 원인 서술은 inferred다.*

- **observed:** 위 표, nlink 전이, 거부 메시지. 2026-11-06 재실행의 `summary.json`은 저장소의 raw와 같았다.[^m2]
- **production 경로 일치:** 같은 외부 하드링크를 production Observer+Oracle로 판정한 결과가 C1+C2로 일치함을 테스트로
  고정했다.[^m2-oracle]
- **inferred:** 고정 쌍과 CVE의 대응(7.5.2→7.5.3 = CVE-2026-23745, 7.5.6→7.5.7 = CVE-2026-24842)과 "7.5.6 회귀를
  앞선 수정이 도입했다"는 서술. 이 fixture의 거동과 advisory 범위는 다를 수 있어 exact 하한은 미검증이다.[^m2]
- **범위:** 통제 재현이며 퍼저 자력 발견이 아니다.

### 7.3 M3: 이름 획득 조건의 관찰(피드백 인과 미입증)

Ledger 판정: 외부 객체 이름을 어휘에 획득한 조건에서 자율 C1 관찰 (A3 21 vs A1 0 vs identity-blind 0); 어휘 미통제라
retention·effect 피드백 인과는 미입증.[^m3]

![M3 대조 막대그래프: 외부 이름을 어휘에 넣은 A3full s11 21 hits, 이름을 뺀 A3blind s11 0, 이름을 철자할 수 없는 A1 0](../figures/m3-blind-ablation.png)

*그림 7-2. 이름 획득 조건의 관찰(피드백 인과 미입증). 어휘가 다른 셀의 대조이며 rate 비교가 아니다.*

- 이 대조는 피드백이 아니라 **어휘**를 통제했다. 피드백의 기여는 어휘를 맞춘 R/D/S-u 비교(EXP-3)로 아직 분리되지
  않았다.[^m3]
- **blind 발견이 아니다.** 기존 외부 객체에 하드링크하려면 이름이 필요하고 퍼저는 그것을 관찰로 얻는다.[^m3]
- **seed-rare다.** 예산 1500에서 자율 트리거는 65 seed 중 s11 1개였다. 21건은 그 run의 1 lineage이고, run은 step 416에서 abort했다.
  막대마다 분모(step 수)도 다르다.[^m3]
- **rate 우위는 미입증이다.** 사전등록 매칭 대조의 Wilson 구간이 겹쳤다.[^m3-rate]

### 7.4 M4: oracle 수준 일반성

동일 generic C0/C1/C2 oracle(코드 불변)이 python-tarfile, oras-go, decompress 3개 extractor에서 통제 차분을 구분했다
(일부 TESTED, oracle·adapter 수준).[^m4] 이는 fuzzer 자력 발견의 일반성이나 효과 주장이 아니다. decompress와 oras-go의
자력발견 실행은 C1/C2에 도달하지 못했다.[^m4-neg]

### 7.5 EXP-0 등록 실행: 인프라 측정

**인프라 측정이다. 가설 검정이 아니고 효과 주장도 아니다.** 사전등록 조건은 R/D/S-u × seed 9001–9005 × budget 200,
node-tar 7.5.2다.[^exp0-prereg]

| 항목 | 값 (observed) | 주석 |
| --- | --- | --- |
| 셀 / 실행 수 | 15셀 / 3,000 실행 | [^exp0-run] |
| 완주 | 15/15 | abort 0, invalid 셀 0, arm 간 어휘 동등. 셀 판정과 별개로 trace가 invalid인 step 11개(D 8, S-u 3)와 failed step 10개(D 4, S-u 6)가 있다 [^exp0-run] [^exp0-analysis] |
| C1/C2 hit | 0 | 사전등록의 zero-hit 기본 결과 [^exp0-prereg] |
| rule-of-three 참고 상한 (사전등록 v2 (a)) | arm당 캠페인 단위 3/5 = 0.6, 실행 단위 3/1000 = 0.003(탐색적) | 판정 입력 아님 [^exp0-analysis] |
| p95 full-step | 기록값 1.549 s / 실시간 환산 1.419 s | 3,000 step 합산, nearest-rank [^exp0-analysis] [^exp0-clock] |
| 처리량 (스트림당) | 기록값 2428 exec/h / 실시간 환산 2650 exec/h | 리포트 내부 시간 합 기준, 셀 준비 시간 제외. 런처 wall 합 기준(준비 포함)은 기록값 2307 / 환산 2518이다. 호스트 전체 처리량이 아니다 [^exp0-analysis] [^exp0-clock] |
| 처리량 (호스트 전체) | ≈4760 exec/h | jobs 2, 실제 경과에서 직접 계산(배율 환산 아님) [^exp0-clock] |
| raw 무결성 | 66 파일 verify 통과 | 66 ok, 0 mismatched, 0 missing, 0 extra [^exp0-manifest] |

**시간 지표 주의.** 기록값은 monotonic clock(`perf_counter`) 기준이다. EXP-0 당시 이 호스트의 monotonic clock은 실시간보다
1.091배 빠르게 갔다(셀별 1.086–1.096).[^exp0-clock] 환산값은 실시간 기준이며, `CLOCK_REALTIME`의 장기 편차는 검증 중이다. T_first와
hazard proxy는 실행 수로 세므로 시계와 무관하다(관찰). oracle과 U_viol은 파일 시각을 포함한 파일시스템 스냅샷을 보지만 파일 시각은
실시간 시계로 찍히므로 이 배율의 영향을 받지 않는다고 본다(추론).[^exp0-clock]

위 수치의 기준은 공식 리포트이고, 사전등록 대비 편차 11건도 그 리포트에 공개돼 있다.[^exp0-analysis]

### 7.6 EXP-3 본실험: 사전등록 예정(11/18), 실행 예정

**아직 실행하지 않았다. 아래 값은 모두 자리다.** 타깃 역할을 섞지 않고 역할별로 보고한다.[^exp3-draft] *(역할 구성은 초안 기준이다. 실험 구조와
대상 타깃 범위는 파일럿 후 재판정 대기)*

**표 7-A. `role=holdout` (확증)**

| arm | n | T_first 중앙값 | U_viol | p(Holm) |
| --- | --- | --- | --- | --- |
| R | TBD | TBD | TBD | S-u vs R: TBD |
| D | TBD | TBD | TBD | S-u vs D: TBD |
| S-u | TBD | TBD | TBD | 기준 arm |

**표 7-B. `role=train` (탐색적, 기노출)**

| arm | n | T_first 중앙값 | U_viol | p(Holm) |
| --- | --- | --- | --- | --- |
| R | TBD | TBD | TBD | 해당 없음 |
| D | TBD | TBD | TBD | 해당 없음 |
| S-u | TBD | TBD | TBD | 해당 없음 |

**표 7-C. `role=fix-verification` (기노출, 확증 아님)**

| arm | n | T_first 중앙값 | U_viol | p(Holm) |
| --- | --- | --- | --- | --- |
| R | TBD | TBD | TBD | 해당 없음 |
| D | TBD | TBD | TBD | 해당 없음 |
| S-u | TBD | TBD | TBD | 해당 없음 |

읽는 법:

- 확증 결과는 holdout 패밀리의 Holm 판정뿐이다. 나머지 역할은 확증이 아니다.
- 검정은 양측이다. 기각되어도 어느 arm이 빠른지(`faster_arm`)를 함께 읽는다. 비기각 판정 규칙은 파일럿 후 재판정 대기다.
- T_first 중앙값은 Kaplan–Meier 중앙값이고, 사건이 절반에 못 미치면 "미도달"로 적는다.
- 전 arm 위반 0이면 미관찰로 보고하고 캠페인 단위 rule-of-three 상한을 참고로 병기한다.

### 7.7 EXP-2: 조건부

EXP-3 결과에 사전등록 GO/NO-GO 규칙을 적용해 GO일 때만 수행한다. 현재 TBD다.

## 8. 한계

- **핵심 RQ 미판정.** EXP-3 전이므로 피드백의 효과에 대해 어떤 주장도 하지 않는다.
- **검정력.** 사전 규모 산정상 현재 hazard에서는 T_first 사건 수가 적을 수 있어, 전 arm 위반 0(시나리오 ⑤)이나
  검정력 부족 판정도 가능한 결과다.[^exp3-sizing]
- **판정의 범위.** snapshot 기반 oracle은 중간 변화, transient 생성 후 삭제, 외부 경로 직접 사용을 복구하지 못한다.
  `violated=False`는 관찰 범위에서 위반 증거가 없다는 뜻이지 안전 증명이 아니다.[^contracts]
- **M2.** 손 fixture 범위의 통제 재현이며 CVE 대응은 추론이다.[^m2]
- **M3.** blind 발견이 아니고 seed-rare이며 피드백 인과는 미입증이다.[^m3]
- **M4.** 일반성은 oracle·adapter 수준에 한정된다.[^m4]
- **EXP-0 seed 사전 노출.** seed 9001–9004는 동결 전 비등록 실행에 이미 노출됐고, 그 관찰은 등록 결과로 집계하지 않는다. seed 9001은
  이 호스트 raw 기준 10런이며, 사전등록 공개에서 6런이, 노출 원장에서 3런이 빠져 공식 리포트에 공개했다.[^exp0-analysis] EXP-3 seed는 이들과
  겹치지 않게 정한다.[^exp3-draft]
- **EXP-0 측정 항목 미충족.** 사전등록 측정 4(per-case 대 워커 풀 처리량 비교)는 미충족이다. 등록 실행은 per-case뿐이다.[^exp0-analysis]
- **EXP-0 편차.** invalid trace, 시계 배율을 포함한 사전등록 대비 편차 11건은 공식 리포트 §3에 있다.[^exp0-analysis]
- **EXP-0 시간 지표.** 기록값은 빠르게 간 monotonic clock 기준이고 환산값은 실시간 기준이다. 실시간의 장기 편차는 검증
  중이다(§7.5).[^exp0-clock]
- **raw 보존.** raw는 호스트 로컬에 있고 저장소에는 체크섬 목록만 들어간다.[^exp0-manifest]

## 9. 결론과 향후 계획

현재 방어하는 명제는 좁다. 루프가 실제 node-tar에서 돌고(M1), 하나의 generic oracle이 통제 fixture의 affected/fixed를
릴리스 번호 없이 구분하며(M2), 자력 경계위반은 이름 획득 조건에서 관찰됐고(M3), oracle은 adapter 수준에서 여러
extractor에 적용된다(M4). 피드백 정책의 효과는 아직 판정하지 않았다.

**결론 TBD.** EXP-3 결과가 나오면 판정 시나리오에 따라 이 절을 갱신한다.

| 다음 단계 | 내부 일정 |
| --- | --- |
| EXP-3·EXP-2 규칙 사전등록 고정 | 11/18 |
| EXP-3 실행과 분석, 논문 반영 (G2) | 11/26 |
| 결과보고서·영상 제출 | 11/26 |
| 최종발표 | 11/30 |

## 10. 선행연구와의 관계

TAR fuzzing, hardlink·symlink 공격, entry 순서, 파일 상태 기반 fuzzing은 선행연구가 이미 다뤘다. 이 연구는 그 영역 자체를
기여로 주장하지 않으며, 선행연구 대비 우선권도 주장하지 않는다.[^related]

- Jana & Shmatikov, "Abusing File Processing in Malware Detectors for Fun and Profit", IEEE S&P 2012: TAR를 포함한 file-processing semantic gap.
- ZIPDiff, "My ZIP isn't your ZIP", USENIX Security 2025: feedback-guided archive differential testing.
- LinkZard, "Pig in a Poke", USENIX Security 2025: link 상태를 포함한 feedback-driven file-state fuzzing.
- Wormholes, "Wormholes in the File System", USENIX Security 2026: archive extraction의 symlink·hardlink 조합과 생성 순서.

## 11. 생성형 AI 사용 내역

> 서식의 기입 항목과 대조 필요(UNVERIFIED). 정량 값은 제출 직전 기준 SHA로 다시 집계한다.

| 항목 | 내용 |
| --- | --- |
| 도구 | Claude Code (Anthropic Claude 코딩 에이전트) |
| 사용 범위 | 코드 작성, 분석 스크립트, 실험 실행 보조, 문서 작성. 이 보고서 초안도 에이전트 세션이 작성했고 사람 검토 전이다 |
| 검토 방식 | 브랜치 → PR → CI → 검토(verifier 또는 사람) → 머지. 수술 기간 머지는 사람이 수행한다 |
| 변경 불가 경계 | 안전경계, 격리, oracle 정의, 사전등록 동결 값은 에이전트가 임의로 바꾸지 않는다 |
| 정량 (SHA `24867be` 기준) | 전체 414 커밋 중 96 커밋이 Claude를 co-author로 명시 [^ai] |
| 증거 규율 | 에이전트가 낸 수치는 raw와 요약으로 추적될 때만 보고한다 |

## 12. 재현 방법

명령, 전제 조건, 기대 출력은 [시연 영상 대본](demo-video-script.md)에 있다. 네 명령 모두 2026-11-06에 호스트에서 실행해
확인했다. `make demo`는 공유 이미지를 다시 만들지 않도록 `SKIP_BUILD=1`로 확인했다.[^m1-run]

| 무엇을 | 명령 |
| --- | --- |
| Oracle 판정과 fixture 일치 | `PYTHONPATH=src python3 -m scripts.oracle_fixture_check` |
| 실제 node-tar 루프 | `make demo` |
| 통제 재현 | `python3 experiments/repro/cross_release_identity.py --out <dir>` |
| EXP-0 raw 무결성 | `python3 scripts/make_raw_manifest.py --verify <manifest> --root ~/inodefence-evidence/exp0-20261105` |

## 증거 각주

[^m1]: evidence: [Capability Ledger](../../docs/STATUS.md) 1–6행, 마일스톤 M1.
[^m1-run]: evidence: `~/inodefence-evidence/w4-script-verification-20261106/`의 `demo-run1`, `demo-run2`, `stdout/`(MANIFEST sha256 `88ac345e…`). [LOG](../../docs/LOG.md) 같은 날짜 W4 항목.
[^m2]: evidence: `experiments/repro/evidence/summary.json`, [cross-release-identity-repro-v1](../../experiments/summaries/cross-release-identity-repro-v1.md), Ledger 마일스톤 M2. 2026-11-06 재실행은 `~/inodefence-evidence/w4-script-verification-20261106/repro/`, [LOG](../../docs/LOG.md) 같은 날짜 W4 항목.
[^m2-oracle]: evidence: `tests/test_cross_release_oracle_agreement.py`, `tests/container_integration/check_cross_release_oracle_agreement.py`, Ledger M2.2.
[^m3]: evidence: [Capability Ledger](../../docs/STATUS.md) "퍼저가 자력으로 경계위반을 발견" 행과 마일스톤 M3, PR #151, [§5.3.2 정정](../sections/06-results.md), [node-self-discovery-mechanism-v1](../../experiments/summaries/node-self-discovery-mechanism-v1.md).
[^m3-rate]: evidence: [m3-powered-matched-verdict-v2](../../experiments/summaries/m3-powered-matched-verdict-v2.md), PR #200.
[^m4]: evidence: [Capability Ledger](../../docs/STATUS.md) cross-implementation 행과 마일스톤 M4, `tests/test_python_tarfile_generality.py`, PR #176, PR #177.
[^m4-neg]: evidence: [m4-5 통합 verdict](../../experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.md), [m4-7 oras-go](../../experiments/summaries/m4-7-oras-go-selfdiscover-v1.md), PR #197, PR #198.
[^rq]: evidence: [research-questions v2](../../docs/research/design/research-questions.md).
[^contracts]: evidence: [security-contracts](../../docs/research/design/security-contracts.md), [threat-model](../../docs/research/design/threat-model.md), [§2](../sections/03-background-threat-model.md).
[^exp0-prereg]: evidence: [exp0-pilot-v2.1](../../experiments/preregistration/exp0-pilot-v2.1.md) '사전 노출 공개'·'zero-hit 방침' 절, 동결 커밋 23e5c66 (PR #258).
[^exp0-run]: evidence: `~/inodefence-evidence/exp0-20261105/summaries/index.json`(abort_count 0, invalid_count 0, cells 15), `registration.json`(last_status), 매니페스트 PR #262.
[^exp0-analysis]: evidence: `experiments/summaries/exp0-20261105-report.md`와 `.json`(PR #268)의 §2 측정 상태, §3 편차 2·3·9. 분석 코드는 main `f3e6035`의 `scripts/analyze_exp0.py`.
[^exp0-clock]: evidence: `experiments/summaries/exp0-20261105-report.md` 편차 1(합산 1.0914, 셀별 1.0855~1.0964; 표기 1.091). 호스트 전체 처리량은 셀 구간 4763, 해시 고정 타임스탬프 4758 exec/h. 실시간 기준, 장기 편차 검증 중.
[^exp0-manifest]: evidence: `experiments/summaries/raw-manifest-win-20261105-20261105.sha256`(PR #262, sha256 `a9dc149c…`), `scripts/make_raw_manifest.py --verify` 2026-11-06 재실행.
[^exp3-draft]: evidence: PR #239→#263→#264의 `experiments/preregistration/exp3-v1.md`(head e11d302, 미머지·미동결), PR #248과 #257의 confirmatory 출력.
[^exp3-sizing]: evidence: [§4.6.3](../sections/05-method.md) "계획 단계 검정력 한계"(PR #216), PR #263 '규모 산정 입력' 절(미머지).
[^related]: evidence: [related-work-positioning](../../docs/research/design/related-work-positioning.md), [§3](../sections/04-related-work.md).
[^ai]: evidence: `git rev-list --count 24867be` = 414, `git log 24867be --grep='Co-Authored-By: Claude' --format=%H | wc -l` = 96 (2026-11-06 재실행). [§4.7](../sections/05-method.md)(PR #216).
