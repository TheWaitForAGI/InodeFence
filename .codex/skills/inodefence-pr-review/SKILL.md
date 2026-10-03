---
name: inodefence-pr-review
description: Review an InodeFence pull request for Task Contract compliance, architecture boundaries, research correctness, tests, documentation impact, and merge readiness.
---

# InodeFence PR Review

InodeFence PR을 merge하기 전에 사용하는 repository-specific review 절차다.

스타일 취향보다 **correctness, security semantics, research validity, regression risk**를 우선한다.

## 1. 리뷰 전 기준점

먼저 확인한다.

1. PR title/body
2. linked Issue 또는 사용자 Task Contract
3. base/head branch
4. changed files 전체
5. `docs/START_HERE.md`
6. `docs/STATUS.md`
7. `AGENTS.md`
8. 변경 영역의 scoped `AGENTS.md`와 design 문서

stacked PR이면 base branch를 반드시 확인한다.
main 기준으로 이미 해결된 문제를 다시 지적하거나, 아직 base에 없는 API를 있다고 가정하지 않는다.

## 2. Task Contract 일치

확인한다.

- 요청한 목표를 실제로 해결하는가?
- 수정 가능 영역을 넘지 않았는가?
- 금지 영역을 건드리지 않았는가?
- 완료 조건을 충족하는가?
- unrelated refactor/docs/feature가 섞이지 않았는가?

scope creep은 기능이 좋아 보여도 별도 PR 후보로 분리한다.

## 3. Layer / architecture 경계

변경을 pipeline에 배치한다.

```text
Seed Generator
→ Structure Mutator
→ TAR Builder
→ Target Adapter
→ State Observer
→ Security Oracle
→ Feedback / Corpus
→ next mutation
```

확인한다.

- Model이 실행 logic을 가지지 않는가?
- Mutator가 observer/oracle/feedback을 참조하지 않는가?
- TargetAdapter가 보안 truth를 결정하지 않는가?
- Observer가 raw evidence 수집을 넘어 policy를 결정하지 않는가?
- Oracle이 mutation 전략을 결정하지 않는가?
- Feedback signature가 raw StateSnapshot을 대체하지 않는가?

## 4. Research contract 검사

다음은 높은 우선순위 finding이다.

- CVE identifier가 generic oracle에 하드코딩됨
- known PoC가 기본 rediscovery seed가 됨
- vulnerable version 조건으로 violation을 확정
- target-specific behavior가 generic core에 섞임
- path-only evidence로 object identity/effect를 확정
- raw observation과 paper conclusion이 같은 data model에 섞임

Security Contract 관련 변경이면 `inodefence-security-contract-review` 관점으로 C0~C4를 추가 검토한다.

## 5. Filesystem semantics 검사

Linux filesystem 의미를 코드가 단순화하지 않았는지 본다.

특히:

- path != object identity
- hardlink는 같은 object에 대한 directory entry 관계
- identity는 초기 기준에서 `(st_dev, st_ino)`
- symlink target text와 resolved object는 다름
- entry order/duplicate path는 archive semantics에서 의미 있음
- raw archive path/link text를 불필요하게 normalize하지 않음
- source bind mount와 runtime filesystem을 혼동하지 않음

의심되면 unit test만 믿지 말고 실제 filesystem behavior를 재현하는 test/probe가 있는지 본다.

## 6. 테스트 품질

확인한다.

- 새 behavior의 regression test가 있는가?
- happy path만 검사하지 않는가?
- negative case가 있는가?
- deterministic behavior를 요구하는 부분이 reproducible한가?
- inapplicable mutation/no-op semantics가 명시적인가?
- test가 구현 내부 구조가 아니라 public contract를 검증하는가?
- test fixture가 host 환경에 위험하지 않은가?

버그 수정인데 regression test가 없으면 원칙적으로 finding으로 남긴다.

## 7. 문서 일관성

다음 변경은 문서 영향이 있을 수 있다.

- shared interface/data model
- architecture responsibility
- Security Contract
- experiment methodology
- current Layer/status
- major design decision

코드와 문서가 충돌하면 코드가 동작하더라도 merge-ready로 보지 않는다.

반대로 내부 refactor인데 불필요하게 대형 연구 문서를 수정했다면 scope creep 여부를 본다.

## 8. Validation 신뢰성

PR body의 validation 문구를 그대로 신뢰하지 않는다.

가능하면 CI/check status와 실제 변경에 맞는 테스트를 확인한다.

다음 표현을 구분한다.

- 실행함 + PASS
- 실행함 + FAIL
- 실행하지 않음
- CI에서만 확인
- 환경 제약으로 미확인

검증하지 않은 것을 PASS로 추정하지 않는다.

## 9. 리뷰 finding 기준

중요도 순으로만 작성한다.

### Blocker
merge하면 security/research contract 또는 architecture가 명백히 깨짐.

### Major
잘못된 결과, false positive/negative, 데이터 손실, 재현성 손상, 중요한 regression 가능성.

### Minor
유지보수성/명확성 문제지만 현재 correctness는 보존됨.

단순 취향, naming 선호, 이미 자동 formatter가 해결하는 내용은 가능하면 finding으로 만들지 않는다.

각 finding에는 반드시 포함한다.

1. 정확한 파일/위치
2. 현재 behavior
3. 왜 문제인지
4. 최소 수정 방향
5. 필요한 test

## 10. 리뷰 종료 조건

다음을 확인한 뒤 결론을 낸다.

- Task Contract
- architecture boundary
- security/research semantics
- test coverage
- docs impact
- validation evidence
- stacked/base branch context

finding이 없다면 "LGTM"만 쓰지 말고 무엇을 검토했고 남은 limitation이 무엇인지 짧게 기록한다.

사람 reviewer가 최종 merge 판단을 할 수 있도록 사실과 근거를 우선 제공한다.
