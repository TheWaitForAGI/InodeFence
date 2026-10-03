# 보안 finding과 공개 운영 규칙

InodeFence는 보안 연구 프로토타입이며 현재 private 저장소도 향후 공개될 수 있다.
Git 이력과 CI 로그 역시 공개될 수 있는 자료로 취급한다.

## Finding lifecycle

```text
Potential Finding
  → Private Reproduction
  → Minimization
  → Root Cause Analysis
  → Team Review
  → Vendor Coordination
  → Disclosure Decision
  → Public Finding / Paper
```

1. Potential Finding: 관찰된 사실과 미확인 가설을 구분한다. 확인되지 않은 finding은
   공개 Issue에 올리지 않는다. 팀이 접근을 통제하는 private 기록 경로로 공유한다.
2. Private Reproduction: disposable sandbox와 sentinel만 사용해 target/version,
   환경, commit, 설정, 재현 결과를 기록한다. 실제 host secret을 evidence로 사용하지 않는다.
3. Minimization: 원본 evidence를 보존하며 재현에 필요한 최소 사례를 별도로 만든다.
4. Root Cause Analysis: harness/environment 오류와 target 동작을 구분하고,
   Known CVE와 unknown finding을 명확히 구분한다.
5. Team Review: 재현성과 원인 분석, 영향 범위, 민감 자료 포함 여부를 사람이 검토한다.
6. Vendor Coordination: 팀이 확인한 공식 보안 연락 경로를 사용한다. 실제 취약점
   PoC / exploit artifact는 vendor coordination 전에 public branch에 commit하지 않는다.
7. Disclosure Decision: CVE 신청, vendor 연락, 공개 시점과 공개 범위는 팀 합의 후 진행한다.
   coordination을 시작했다는 사실만으로 공개 승인이 되지 않는다.
8. Public Finding / Paper: 공개 결정이 끝난 sanitized/reproducible 자료만
   [published](findings/published/README.md)에 추적한다. 논문 주장에는 검토된 evidence를 연결한다.

## 저장과 공유

미공개 자료는 `findings/private/` 또는 접근이 통제된 별도 저장소에 둔다.
Git ignore는 접근 통제를 대신하지 않는다. `git add -f`, 로그, 첨부파일을 통해
미공개 artifact가 이력에 들어가지 않도록 검토한다. 이 저장소가 private이라는 이유만으로
민감 자료를 commit하지 않는다. 대량 raw 실험 결과의 보존·공유 경로도 별도로 기록한다.

공개 가능 여부가 모호하면 팀 검토에서 결정하고 공개 단계로 넘기지 않는다.
연락처나 vendor 이메일을 추측해 문서에 추가하지 않는다.
