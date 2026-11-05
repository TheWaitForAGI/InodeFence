# 사전등록 (preregistration)

- 이 폴더의 파일은 **실행 전에 커밋되어야** 유효하다. 커밋 SHA가 실행 로그보다 앞서지 않으면 그 실행은 해당 사전등록의 실행이 아니다.
- 커밋된 파일은 **사후 변경 금지**다(지표·예산·hit 정의·분모 규칙·seed·arm 정의 전부).
- 수정은 새 버전 파일(`*-v1.1.md`, `*-v2.md`)로만 하고, 이전 버전은 그대로 둔다.
- `exp0-pilot-v1.md`는 `exp0-pilot-v2.md`로 **대체됨**(v1은 보존). G1 동결 시 엔진 SHA·이미지 digest·policy ID를 채운 **v2.1**이 실행 유효본이다.
- `exp3-v1.md`는 **EXP-3 본실험 사전등록 초안(11/18 동결 전)**이다. 실행 유효본이 아니며 `TBD-FREEZE`(동결 시 #245가 치환)·`TBD-LANE6`(레인 6 검정력 수치) 토큰을 채우고 동결 시 실행 전에 커밋해야 유효하다. hold-out 규칙과 7.5.6 기(旣)노출 공개를 포함한다.

## 버전 상태

| 버전 | 상태 | 비고 |
| --- | --- | --- |
| [exp0-pilot-v1](exp0-pilot-v1.md) | 대체됨(보존) | v2로 대체 |
| [exp0-pilot-v2](exp0-pilot-v2.md) | 설계 등록 | 엔진 SHA·image digest·policy ID 비어 있음 |
| [exp0-pilot-v2.1](exp0-pilot-v2.1.md) | **초안 PR (동결 전)** | 기계판독 블록 추가. `engine_sha`·`image_digest`·`sentinel_generator_seed`는 `TBD-FREEZE`; 동결 PR에서 채우면 그 커밋이 등록 SHA. 그 전엔 run_exp0 게이트가 포맷 오류로 거부(비실행본) |
