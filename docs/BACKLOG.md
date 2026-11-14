# 작업 큐 (BACKLOG)

할 일을 **마일스톤(M)** 아래 태스크로 둔다. 마일스톤은 [STATUS의 Capability Ledger](STATUS.md)의
M1~M4와 같고, 날짜가 아니라 "증거가 모이면 찍는" 지점이다. 자율 루프
(`.claude/skills/autoloop/SKILL.md`)는 **맨 위부터** `대기`이고 게이트가 열린 태스크를 집는다.
완료 기록은 [WORKLOG](WORKLOG.md), 실행 기록은 [LOG](LOG.md)에 남긴다.

상태 값: `대기` / `진행` / `완료(<브랜치>)` / `완료(머지됨 #<PR>, main)` / `막힘(<날짜>, <이유>)` / `BREAKING(<브랜치>)` / `대기(머지 필요: <브랜치>)`

- 루프의 끝은 BACKLOG 소진이 아니라 **프로젝트 완료**(가설 검증·M1~M4; autoloop 7.1, D036)다. 큐가 비면 루프가
  STATUS Ledger의 빈 칸(증거 수준이 가장 낮은 미완 마일스톤의 다음 gate)에서 항목을 보충한다(autoloop 7.2).
- 게이트 `사람`은 안전경계·연구 불변식에 걸리는 결정(외부 공개, 가드·격리·allowlist 설정, FROZEN 변경, BREAKING 판정)에만 쓴다.
  머지는 사람 게이트가 아니다(D035): PR·CI·verifier 통과 후 자율 머지. 그 외는 안전경계 안에서 자율 진행한다.
- 안전경계(변경 없음): disposable sandbox + sentinel만, 고정 node-tar 버전, 격리 완화 플래그 금지,
  가드 훅 우회 금지, 실제 민감 파일 대상 금지. 이건 느슨하게 하지 않는다.
- 연구 불변식(변경 없음): CVE-specific oracle 금지(D005), 알려진 PoC를 fuzzing seed로 안 씀(D006),
  observed/inferred 구분, synthetic을 native로 승격하지 않음, 비교 없이 effectiveness 주장 안 함.

## 수술 (2026-11-03 ~ 11-30) — 단일 기준: Claude Doc

계획 기준은 Claude Doc 「InodeFence 독립 연구 감사 및 실험 설계 재정립」(https://claude.ai/artifact/JJtsK3VowEGuBFN3YXZDFq)이다
([STATUS 다음 연구 gate](STATUS.md) 수술 기준·[D038](DECISIONS.md)·[research-questions v2](research/design/research-questions.md)).
2026-11-03 이전 마일스톤 M3·M4 캠페인 기록은 [pre-20261103-results](archive/pre-20261103-results.md)로 옮겼다. 머지 방식은 S-D37 행(D037)을 따른다.

| 단계 | 늦어도 | 핵심 작업 | 게이트 | 상태 |
| --- | --- | --- | --- | --- |
| 1 보존·통제 | 11/5 | 태그 `audit-baseline-20261103`(=bb3fd7c), 맥 raw SHA-256 목록(1,614파일), 윈도우 raw 미반입 기록, 보고 누락 4건 LOG 기록, 논문 06/07 정정, 덱 8장 stale 기록 | 없음 | 이 PR에서 저장소 반영; **원본 백업 미완료**(맥 raw 체크섬 목록만, 윈도우 raw 미반입, 외부/공유 백업 없음) |
| 2 방향 재정립 | 11/7 | research-questions v2(핵심 RQ·H-A/H-B/H-C·R/D/S), D038, EXP-0 사전등록 v1, STATUS 수술 기준·모순 표, 이 큐 | D037(병합 정책)은 지웅 결정 대기 | 이 PR에서 완료(D037 제외) |
| 3 구현 수리 | 11/10 (G1 늦어도 11/13) | **Runtime:** abort 수정(observer malformed_identity·broker·cleanup)·워커풀 + per-case parity. **Evaluation:** 어휘 동등 R/D/S 러너·KM/logrank/A12·사전등록 실행기. **Oracle:** 다수 sentinel·oracle FP/FN 점검. **Evidence:** replay 연결 | G1: R/D/S×budget 50 완주, 어휘 동등 테스트, 10캠페인 smoke abort≤1, 워커풀 parity | 완료 — G1 4조건 native PASS(2026-11-04, 레인 10 독립 재현, g1-20261104·wp-parity-20261104). PR 머지 이력은 LOG |
| 4a EXP-0 | 11/14 | 파일럿 5 seed×200×R/D/S-u 실행(사전등록 v2.1 커밋 후), zero-hit 기본·dense 신호로 EXP-3 설계 입력·x·n 확정 | G1 | 완료(#262·#268, 2026-11-05) |
| 4b 사전등록 | 11/18 | EXP-3 + EXP-2 GO/NO-GO 규칙 사전등록 커밋(SHA·digest·policy ID) | 4a | 완료(2026-11-13 동결, F `72de299`, #332) |
| 4c EXP-3 | ≈11/20 | EXP-3 train([exp3-v1](../experiments/preregistration/exp3-v1.md)); 규칙 기계 적용 | 4b | 완료(train 실행·GO/NO-GO 판정 기록 #368) |
| 4d EXP-2 조건부 | ≈11/25 | EXP-2 holdout([exp2-v1](../experiments/preregistration/exp2-v1.md)), GO일 때만 실행 | 4c 규칙 | 진행(holdout 실행 중, LOG 2026-11-14) |
| 5 저장소 정리 | 실험 중 (11/24 중단) | 모순 표 #1–#4·#11·#12 정정(README·src/README·architecture·Makefile/fanout 상한·n04_preflight 경로), 죽은 문서 정리 | 3단계 이후, 실험과 병행, 실험 코드 불변 | 진행(2026-11-14 정리 지시 단계 A: PR (1) A-repo-docs 진행 중) |
| 6 최종 | 11/30 | 논문·Ledger·증거 사슬 최종, 제출 | G2 11/26 | 대기 |

### 수술 보강 큐 (2026-11-04, 연속 운영 지시 — 머지 대기는 작업 중단 사유가 아님)

감사 15개 꼭지 대응표(Report 2 확정 조건 ↔ 구현·PR·증거)에서 드러난 결함과 사람 결정 항목. 상태 구분:
**구현 완료**(코드·문서가 PR에 있음) / **검증 완료**(독립 verifier가 최신 SHA에서 확인) / **실험 입증 완료**(사전등록된 native 실험 결과) — 세 가지를 섞어 쓰지 않는다.

| 항목 | 감사 기준 | 담당 | 상태 | 게이트 |
| --- | --- | --- | --- | --- |
| S-08 **7.5.6 hold-out 규칙 사전등록** — 훈련(7.5.2/7.5.3)·평가(7.5.6/7.5.7) 쌍, "훈련 노출"의 정의, 기존 7.5.6 실행 이력 공개(있으면 '수정 검증 쌍'으로 재분류 선택지). 결과를 본 뒤 규칙을 정하지 않는다 | 08 실험 대상 | 레인 9 | 진행 — 지웅 결정 7 = B(2026-11-05): 7.5.6/7.5.7은 기노출 수정 검증 쌍(등록 역할 fix-verification·pre-exposed, 캠페인 hit 수 비예측 — 7.5.6은 고정 fixture affected), 독립 hold-out = 노출 node-tar 집합 {7.5.2, 7.5.3, 7.5.6, 7.5.7, 7.5.8, 7.5.22} 밖·LOG 실행 기록 없는 node-tar 릴리스 중 선정, 정체 `TBD-FREEZE`(이전 7.2.0/7.3.0/7.4.4 확정은 minipass 버전 오독 근거라 철회 — #239 bda2f3d)(advisory-blind 규칙, 고정 fixture 상태 확인만, 등록 전 역할 배정 규칙), #239(bda2f3d) 반영·verifier PASS(2026-11-05, bda2f3d에서 재검증), 11/18 동결 전 | 지웅(11/18 #239 머지) |
| S-UV **U_viol 정의 확정** — Git 동결 EXP-0 v2/v2.1은 U_viol을 등록하지 않음(research-questions v2 L50만 정의). native 보고서 경로(rds_report)는 feedback-eligible이 아닌 step의 oracle 위반을 fingerprint에서 제외(unfingerprinted_hit_steps로 분리 집계), 메모리 경로(rds.py)는 포함 → 서명 단위·lineage·eligibility·invalid step 처리·arm 공통 규칙을 EXP-3 사전등록에 명시해야 함. 정의를 구현에 맞춰 조용히 바꾸지 않는다 | 11·14 | 레인 10 판정 → 레인 5 수정 | 해소 — 레인 10 판정(문제 실재, G1 15셀 영향 0) → #240(oracle-evidence 기반 u_viol·u_viol_feedback 분리·G1 fixture 전후 회귀 테스트, verifier PASS, 8라운드 main 반영); 서명 단위·lineage·eligibility 정의는 지웅 결정(oracle-evidence 채택)으로 #239에 명시 | 없음 |
| S-V21 **EXP-0 사전등록 v2.1 PR** — `TBD-FREEZE`(engine_sha·image_digest·sentinel_generator_seed) 토큰, 사전 노출 공개(G1 smoke가 seed 9001~9004 사용, D-s9002 step 42 C2 1건), 동결 PR에서 값 채움 | 06·12 | 레인 8 | 완료(머지됨 #258, main 23e5c66) — #238 초안 12라운드 main 반영, 동결 PR #258(engine_sha b609981·image_digest 22c8734f·seed 20261104, F=60cc78b1…) verifier PASS·16라운드 머지 = 등록 커밋 23e5c66 | 없음(#258 머지 완료) |
| S-BK **외부 raw 백업 위치** — 번들 생성·로컬 복원 검증(①manifest ②raw 존재 ③SHA 일치 ④복원)까지 진행, 외부 업로드는 승인 뒤 | 13·15⑦ | 레인 8 | 승인됨 — 비공개 저장소 `TheWaitForAGI/InodeFence-evidence`(private, 번들+manifest+사이드카, 클론 재검증), 생성·업로드는 EXP-0 호스트 동결 해제 후; Mac 1,614 raw 읽기 전용 이관 계획 작성(실행은 지웅) | 없음(결정됨) |
| S-C2 **C2 sentinel 대상 집합 확장**(1개 → ≥3 무작위 이름 → 외부 영역 전체) — FP/FN 영향·v2.1 키 연결 브리프 | 01 | 레인 7 | 결정됨 — 선택지 B(contract 기본값 유지, 실험 count=3, generator `sentinel-names/seed-random-v1`, 고정 seed 20261104, describe() 지문 레인 7·10 독립 재현) | 없음 |
| S-D37 **D037 결정안** — 선택지·권장안·영향 | 07 | 오케스트레이터 | 결정됨 — 선택지 A(#237 기록: 지웅 squash merge만, 나머지 위임, HEAD 변경 PR 재검증, 라운드 방식) | 없음 |
| S-D6 **EXP-3 확증 검정** — 지웅 결정 6(2026-11-05): seed-block paired exact 순열 로그랭크(모든 n 1차) + Holm(holdout 패밀리 S-u vs R → S-u vs D), event<5 = underpowered 플래그, rule-of-three 서술 병기, 방향 규칙(기각 ∧ faster_arm==S-u → ①, 기각 ∧ R/D → ⑧, 무기각 → ⑤); 구현 #248/#257(verifier 재검증 PASS), #239 반영 | 06·14 | 레인 6·9·10 | 완료(#248·#257 머지됨; #239 미머지) | 없음 |
| S-D8 **Tier-B 새 계보 extractor**(Rust `tar` 등) 추가 여부 — audit-07 MVP 범위 재개방이라 사람 결정; 권장 B(Rust 1개, 11/18 못 맞추면 A 폴백) | 03·04 | 레인 7 브리프 | 결정됨 — B 승인 — Rust `tar` 1개 조건부 추가. 11월 18일 사전등록을 지연시키면 A로 복귀(지웅, 2026-11-05; 출처 오케스트레이터 지시, DECISIONS 항목은 Rust 레인 PR 브랜치 `claude/s3-rust-tar-target`에서 추가 예정) | 없음(결정됨) |
| S-15 **STATUS 산출물 체크리스트 12항목**(확인 명령·경로 부착) + 15개 꼭지 충족도(구현/검증/실험 구분) | 15 | 오케스트레이터 | 진행 — STATUS 산출물 체크리스트 #259(#221 위 스택, verifier 판정은 PR 코멘트 기준); 15꼭지 대조(레인 9, 2026-11-05) LOG 기록 | 없음 |

## 완료 (이력은 WORKLOG/LOG)

**M1 — 루프가 실제 node-tar에서 돈다: 완료.** 과거 P0-1~P0-5 큐(중간 상태 trace, `make demo`=native,
JSONL 부분 저장+CI, producer 견고성)와 P2-b/P2-c 머지가 main에 있다. 세부는 Ledger 1~6행과 WORKLOG.

---

## M2 — 실제 경계위반 통제 재현 + 버전 구분 (실증됨 → 박제)

2026-10-24 capability probe로 node-tar 7.5.2가 외부 sentinel로 하드링크를 만들어 C1+C2가 성립하고
7.5.3은 거부함을 observed(LOG). 재현 스크립트+증거는 `experiments/repro/`에 박제됐고(5 릴리스 sweep),
이는 **2개 CVE의 차분 경계**다: 최상위 7.5.2/7.5.3 = CVE-2026-23745(catalog N01·R1), 중첩 7.5.6/7.5.7 =
CVE-2026-24842(CVE-2026-23745 수정이 도입한 check/use 회귀; catalog N02·R2). 두 CVE 모두 catalog에 이미
등록됨. 동일 generic identity oracle이 두 root-cause를 outcome으로 포착한다. 재발견(자력 발견)과는 구분한다.

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M2.1 | capability probe를 repo 안 재현 스크립트/테스트로 고정: 손으로 만든 하드링크 fixture(외부 sentinel 대상)를 실제 7.5.2/7.5.3에 돌려 7.5.2=C1+C2·7.5.3=거부를 확인. generic C1/C2만 쓰고 CVE 식별자/PoC 하드코딩 없음. LOG 한 줄 + Ledger M2 증거 갱신 | 완료(experiments/repro/cross_release_identity.py) | 없음 (호스트 docker) |
| M2.2 | 같은 fixture를 우리 Observer/Oracle 경로(effect pipeline)로도 통과시켜 "손 probe == oracle 판정" 일치 확인 | 완료(claude/m2-2-oracle-path-7d09f3) | M2.1 |

## M3 — 퍼저가 자력으로 위반을 찾는다 (H1 본체)

초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다. 현재 작업은 위 수술 큐(4c EXP-3·4d EXP-2)를 따른다. 이전 판정과 태스크 M3.1–M3.6은 [archive](archive/pre-20261103-results.md)로 옮겼다.

## M4 — 일반성 (2번째 extractor)

| 순서 | 태스크 | 상태 | 게이트 |
| --- | --- | --- | --- |
| M4.1 | oras-go adapter 설계(isolated CWD 포함), 동일 generic 모델·oracle로 연결. CVE/target-specific 로직을 generic 모듈에 섞지 않는다 | 완료(jiwoong/m4-1-oras-go-adapter) | 규민·민찬 협의 |
| M4.2 | (감사 제안) decompress(JS; CVE-2026-39243/39246 = symlink + absolute hardlink, CWE-59) 또는 2026 CWE-59 군집(adm-zip·Archive::Tar·HF datasets·borg) 중 1개를 2번째 target으로 — 동일 generic oracle 재사용. | 완료(jiwoong/m4-2-decompress) | 규민·민찬 협의 |
| M4.1b | (감사 전진, 완료) generic oracle 2번째 extractor 일반성: Python stdlib tarfile 통제 차분(fully_trusted=C1+C2, data=거부). `tests/test_python_tarfile_generality.py`. oracle 코드 불변·target-agnostic. | 완료(jiwoong/p-generality-python-tarfile) | 없음 |

## 상시 (레인 담당)

| 태스크 | 상태 | 게이트 |
| --- | --- | --- |
| 거부 입력에서 중간 상태 event 0개인 한계의 표현 방식 | 완료(claude/m3-reject-trace-limit-1b064d) | 민찬 |
| demo 이미지 ID 재현성(provenance attestation) | 완료(gyumin/p0-1-image-id-reproducible: same-host image ID 결정론(BuildKit attestation 해제) · jiwoong/p-demo-image-recipe-provenance: 빌드 레시피 recipe_sha256 provenance + attest) | 규민 |
| 선행연구 서지 정합성(related-work-positioning.md에 저자·venue·연도·아티팩트) | 완료(jiwoong/p-audit-prior-work-citations) | 없음 |
| (감사 전진, 완료) C1 symlink-referent 보강: additive `symlink_referent_confinement` detector(referent가 extract/ 밖이면 보고, 3-tuple 불변). | 완료(jiwoong/p-oracle-symlink-referent) | 없음 |
