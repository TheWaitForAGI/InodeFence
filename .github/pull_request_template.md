## 이 PR을 병합하면 실제로 실행/검증할 수 있게 되는 것

_필수 1~2줄. 답이 "~에 대한 문서/감사"뿐이면 PR이 아니라 docs/STATUS.md 갱신으로 처리한다._

## 해당 마일스톤·레인 (docs/STATUS.md Capability Ledger)

- [ ] M2 실제 경계위반 통제 재현
- [ ] M3 자력 발견 (H1 본체)
- [ ] M4 일반성
- [ ] PRODUCT (D049)
- [ ] 상시 태스크 또는 해당 없음 — 리더 확인 받음

## Related Issue

Closes #

## 무엇을 바꿨나?

<!-- 2~5줄로 설명 -->

## 왜 바꿨나?

<!-- 현재 Layer와 문제를 설명 -->

## 어느 Layer인가?

- [ ] Data Model
- [ ] Generator / TAR Builder
- [ ] Mutator
- [ ] Target Adapter / Harness
- [ ] Observer
- [ ] Oracle
- [ ] Feedback / Corpus
- [ ] Experiment
- [ ] Documentation / Environment

## Generic vs Target-specific

- [ ] Generic logic
- [ ] Target-specific logic
- [ ] 둘 다 포함 — 경계를 설명함

## 관련 Security Contract

- [ ] Path Boundary Confinement
- [ ] Object Identity Confinement
- [ ] External Effect Noninterference
- [ ] Extraction Root Integrity
- [ ] Check/Use Coherence
- [ ] 직접 관련 없음

## 확인

- [ ] `make check` (Dev Container에서 실행; 실제 결과를 아래에 기록)

<!-- 실행 환경, 통과/실패와 실행하지 못한 검사를 기록 -->

- [ ] 필요한 문서를 갱신함
- [ ] CVE-specific PoC/조건을 generic logic에 하드코딩하지 않음
- [ ] 실제 host 민감 파일을 실험 대상으로 사용하지 않음

## 사람이 확인한 AI 설계 판단

<!-- AI가 생성한 코드 중 사람이 직접 이해하고 확인한 설계 판단은 무엇인가? -->

## 리뷰어가 꼭 봐야 할 부분

<!-- AI가 만든 코드 중 사람이 확인해야 할 설계 판단이나 위험한 부분 -->
