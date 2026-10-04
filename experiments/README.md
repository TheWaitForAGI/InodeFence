# 실험 설정과 raw 결과

## 이 폴더는 무엇인가

재현 가능한 실험 설정과 가공 전 실행 기록을 보관한다.

## 입력

명시적 seed/config, exact target 버전, 실행 전 provenance와 엔진 실행 기록.

## 출력

Configuration JSON, campaign manifest와 raw steps JSONL. 비교 실험과 분석은 아직 없다.

## 책임

예: baseline과 feedback 사용 실험이 어떤 설정으로 실행됐는지 기록한다.

## 하지 않는 것

raw 결과를 검토 없이 논문 결론으로 승격하기, source mount에서 filesystem 실험하기.

## 다른 모듈과의 연결

[엔진](../src/inodefence/README.md)을 실행할 설정을 제공하며 확인한 증거는 [findings](../findings/README.md), 검토된 분석은 [paper](../paper/README.md)로 연결한다.

## 현재 상태

Execution Provenance v1은 campaign 시작 전에 source/environment/adapter/sentinel 값을 고정한다.
Manifest v4는 stored configuration과 실제 RunResult contexts/exporter 환경을 분리한다. Git 정보가
없으면 None이며 dirty checkout의 commit은 patch 내용을 보존하지 않는다. Metadata만으로
연구 결과의 재현성 또는 OS execution isolation을 보장하지 않는다.

summaries/에는 [safe reference 개발 pilot](summaries/reference-campaign-pilot-v1.md)의 작은
engineering summary가 있다. Raw 결과는 로컬 experiments/raw/reference-pilot-v1/에 Git ignore로
보관하며 재생성 명령과 checksum을 요약에 기록한다. Formal effectiveness 실험 결과는 없다.

Strict JSON ExperimentConfig v1/v2와 [reference config CLI](../scripts/run_configured_reference.py)가
실행 전 binding을 검증하고 stored config ID/actual execution provenance를 raw export에 연결한다.
Configuration identity는 result/source/kernel를 포함하지 않으며 평가 결과가 아니다.

[인프라 검증 요약](summaries/infrastructure-readiness-v1.md)은 clean source의 작은 reference repeat,
uncontained Node campaign 실행 전 거부와 local raw checksums를 연결하는 역사적 기록이다.
현재는 [pre-audit readiness](summaries/pre-audit-readiness-v1.md)의 contained Node benign smoke,
lifecycle, durable export와 dependency 검증까지 완료했다. 다음은 full audit이며 evaluation은 미실행이다.

## 파일 배치 규칙

설정은 configs/, raw 기록은 raw/에 둔다. raw/*와 results/는 Git ignore 대상이므로 결과 보존·공유 경로를 명시한다. 설정에 seed, 환경, target 버전과 결과 식별자를 남긴다.

작은 검증 요약은 [summaries/](summaries/README.md)에 config, commit, target/version, seed, budget, result와 원본 근거를 연결해 추적한다.


Container-bound configurations use explicit ExperimentConfig v2 and frozen isolation
policy/runtime/image/worker/lock provenance. Uncontained third-party campaigns fail
before setup; this pre-audit contract authorizes only the tiny benign Node smoke.
Manifest v4 stores these facts; snapshot/security/novelty semantics are unchanged.
No benchmark effectiveness or known-vulnerability result is implied.


The [benign Node container smoke](summaries/benign-node-container-smoke-v1.md) records
one tiny engineering campaign, exact stored conditions/checksums and observed stats.
CI retains its raw bundle as an artifact. Lifecycle/export review and limited integration freeze
are complete; next is the full repository audit. No effectiveness/security evaluation follows automatically.

## Completed export publication

Manifest v4 stages closed/flushed/fsynced files and verifies JSONL/checksum/read-back before
Linux `renameat2(RENAME_NOREPLACE)` publication; supported libc/kernel/filesystem are required.
An existing or concurrently created destination is never replaced. Optional immutable config JSON
is checked against the stored config ID and published in the same bundle. Before-publication errors
leave the final destination absent and staging cleaned. Parent directories may remain. Hard process
interruption can leave staging; a post-publication parent-fsync error leaves the complete bundle
and propagates. Unexpected-evidence emergency preservation is separate and can still be partial
if its writes fail. This is atomic publication, not resume/database or crash-proof storage.

Schemas1/2/3 are historical exports; the writer emits v4. Step JSONL/ArchiveCase/RunResult/signature
encoding and provenance/config schemas are unchanged. The no-overwrite mechanism follows the
[Linux rename manual](https://man7.org/linux/man-pages/man2/rename.2.html).
