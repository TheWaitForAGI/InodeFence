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

- [ ] `python -m ruff check .`
- [ ] `python -m ruff format --check .`
- [ ] `python -m pytest`
- [ ] 필요한 문서를 갱신함
- [ ] CVE-specific PoC/조건을 generic logic에 하드코딩하지 않음
- [ ] 실제 host 민감 파일을 실험 대상으로 사용하지 않음

## 리뷰어가 꼭 봐야 할 부분

<!-- AI가 만든 코드 중 사람이 확인해야 할 설계 판단이나 위험한 부분 -->
