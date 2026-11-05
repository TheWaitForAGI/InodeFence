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
| node-tar | 7.5.2 | M2 train · M3.3 overlay (맥 빌드) | M2 repro, M3.3 | 미확인 | 2026-10 | `experiments/summaries/cross-release-identity-repro-v1.md` | docker `inodefence-node-tar-effect:7.5.2` **맥 호스트 빌드** `sha256:21d8a0e3a5c5…` |
| node-tar | 7.5.2 | G1 smoke · EXP-0 대상 · 측정 (이 호스트 재빌드, 같은 recipe) | G1 smoke, EXP-0, 측정(wp-throughput·wp-parity) | **seed 9001 = EXP-0 동결 전 3회 노출**: ① G1 completion R/D/S-u×s9001×b50(`docs/LOG.md:164` "completion 3/3") ② G1 smoke R/D/S-u×9001–9004×b50(`docs/LOG.md:164` "smoke 12/12"; 9002–9004는 1회) ③ 측정 재실행 ctl-pc-b50-s9001-nosamp(budget 50, 비등록; `exp0-pilot-v2.1.md:163–166`); 측정 7001–7002(wp-throughput jobs1 b50×{pc,wp}×{7001,7002}×{r1,r2} + b200×{pc,wp}×7001, jobs2 b50 7001, ctl-pc-b50-s7001-nosamp — raw `SUMMARY.md:6,8,23`, MANIFEST `9ebdc437…`); EXP-0 등록 9001–9005 | 2026-11 | `~/inodefence-evidence/g1-20261104/`; `~/inodefence-evidence/wp-throughput-20261104/`(MANIFEST digest `9ebdc437…`; 저장소 내 체크섬 목록은 #251 `raw-manifest-win-20261104-2317.sha256`, 미머지) | docker `inodefence-node-tar-effect:7.5.2` **이 호스트 빌드** `sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb`(G1 report image_id·`docker inspect` 동일) |
| node-tar | 7.5.3 | 5-release sweep (M2) | M2 cross-release | 미확인 | 미확인 | `experiments/summaries/cross-release-identity-repro-v1.md` | 미확인 |
| node-tar | 7.5.6 | fix-verification 쌍 (M2.2) | M2 cross-release | 미확인 | 미확인 | `experiments/repro/cross_release_identity.py:55,59`; `experiments/summaries/cross-release-identity-repro-v1.md:53-55`; `experiments/benchmarks/catalog-v1.json:150,153` | `node-tar-7.5.6.package-lock.json` |
| node-tar | 7.5.7 | fix-verification 쌍 (M2.2) | M2 cross-release | 미확인 | 미확인 | `experiments/summaries/cross-release-identity-repro-v1.md` | 미확인 |
| node-tar | 7.5.8 | 5-release sweep (M2) | M2 cross-release | 미확인 | 미확인 | `experiments/summaries/cross-release-identity-repro-v1.md` | 미확인 |
| node-tar | 7.5.22 | M1 native demo · 정책 매트릭스 (benign validation baseline, `make demo` 기본 핀) | M1 `make demo-native`/`make demo`, BACKLOG 7 native 정책 매트릭스 1·2차 | demo 123(budget 20); 매트릭스 P0/P1/P2×{123,456,789}(budget 100) | 2026-10-23~24 (이후 `make demo` 반복) | `docs/LOG.md:15,18,56,60`; `docs/DECISIONS.md:296`; `tools/node-tar/package.json:7` | `tools/node-tar/package-lock.json:56-58`(tar 7.5.22 resolved); 이미지 digest 미확인 |
| decompress | 4.2.1 | M4.5 자력발견 | M4.5 campaign | 500–509 | 2026-10-30~31 | `experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.md` | producer `native-decompress[decompress=decompress@4.2.1;node=22.23.4]` |
| oras-go | v2.6.1 | M4.7 자력발견 | M4.7 campaign | 11 | 2026-10-31 | `experiments/summaries/m4-7-oras-go-selfdiscover-v1.md` | 미확인 |
| python-tarfile | 3.12 | M4.1b generality 테스트 | M4a adapter tests | 해당 없음 | 미확인 | `tests/test_python_tarfile_generality.py` | 해당 없음 (in-process) |
| libarchive | 3.7.2 | qualification 실행으로 노출 (public write-disk entry-boundary, benign 결정론 fixture 2종 × quiet 20 + strace 20 = 80 실행, 퍼징 아님) | libarchive entry-boundary qualification v1 | 해당 없음 (고정 fixture) | 2026-10-09 (raw UTC 구간) | `experiments/summaries/libarchive-entry-boundary-qualification-v1.md:39-58,113-118`; `docs/STATUS.md:198` | qualification image `sha256:3e12bcd8a99e32bd1ea04dbc7d423edd61236ae5f62c6e2406da0b73cc6dadda`; pkg `libarchive13t64` `3.7.2-2ubuntu0.9` |

미확인 셀은 근거가 확보되면 갱신한다(갱신 시 동결된 사전등록은 fail-closed로 재등록 필요).
