# 노출 원장 (exposure ledger)

이 파일은 **(extractor, version)별 기노출 사실의 단일 진실원**이다(사전등록 자산 — 감사 문서 아님).
EXP-3 다중 타깃 설계에서 `targets.<id>.role = holdout`인 타깃의 `(extractor, version)`이 이 표에 있으면
런처(레인 5 ledger 리더)가 **실행을 거부**한다. 사전등록 블록은 이 파일을
`exposure_ledger = experiments/preregistration/exposure-ledger.md` +
`exposure_ledger_sha256 = <파일 전체 sha256>`로 가리켜 동결한다(동결 후 이 파일을 고치면 사전등록도 갱신해야
하는 fail-closed). 행 id = `extractor@version`.

**규칙:** 근거 없는 행은 넣지 않는다. 확인 안 된 셀은 `미확인`으로 적고 추측하지 않는다. 리더는 아래 파이프
표에서 헤더에 `extractor`·`version` 열이 있는 표의 행만 읽고(대소문자 무시), 나머지 열·산문은 무시한다.

| extractor | version | exposure_kind | exposed_by | seeds | date | evidence | digest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| node-tar | 7.5.2 | design-input (M2 train · G1 smoke · EXP-0 대상 · 측정) | M2 repro, G1 smoke, 측정(wp-throughput·wp-parity) | G1 smoke 9001–9004; 측정 7001–7002; 측정 재실행 9001(ctl-pc-b50-s9001-nosamp, budget 50, 비등록); EXP-0 등록 9001–9005 | 2026-10~11 | `experiments/summaries/cross-release-identity-repro-v1.md`; `~/inodefence-evidence/g1-20261104/`; `~/inodefence-evidence/wp-throughput-20261104/`(MANIFEST digest `9ebdc437…`) | docker `inodefence-node-tar-effect:7.5.2` (image id prefix `sha256:21d8a0e3a5c5`) |
| node-tar | 7.5.3 | 5-release sweep (M2) | M2 cross-release | 미확인 | 미확인 | `experiments/summaries/cross-release-identity-repro-v1.md` | 미확인 |
| node-tar | 7.5.6 | fix-verification 쌍 (M2.2) | M2 cross-release | 미확인 | 미확인 | `experiments/repro/cross_release_identity.py:55,59`; `experiments/summaries/cross-release-identity-repro-v1.md:53-55`; `experiments/benchmarks/catalog-v1.json:150,153` | `node-tar-7.5.6.package-lock.json` |
| node-tar | 7.5.7 | fix-verification 쌍 (M2.2) | M2 cross-release | 미확인 | 미확인 | `experiments/summaries/cross-release-identity-repro-v1.md` | 미확인 |
| node-tar | 7.5.8 | 5-release sweep (M2) | M2 cross-release | 미확인 | 미확인 | `experiments/summaries/cross-release-identity-repro-v1.md` | 미확인 |
| decompress | 4.2.1 | M4.5 자력발견 | M4.5 campaign | 500–509 | 2026-10-30~31 | `experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.md` | producer `native-decompress[decompress=decompress@4.2.1;node=22.23.4]` |
| oras-go | v2.6.1 | M4.7 자력발견 | M4.7 campaign | 11 | 2026-10-31 | `experiments/summaries/m4-7-oras-go-selfdiscover-v1.md` | 미확인 |
| python-tarfile | 3.12 | M4.1b generality 테스트 | M4a adapter tests | 해당 없음 | 미확인 | `tests/test_python_tarfile_generality.py` | 해당 없음 (in-process) |

미확인 셀은 근거가 확보되면 갱신한다(갱신 시 동결된 사전등록은 fail-closed로 재등록 필요).
