# InodeFence 에이전트 가이드

이 문서는 InodeFence 저장소에서 사람과 코딩 에이전트가 공통으로 따르는 행동 계약이다. 작업 규칙의 진입점이며
연구 설계서나 작업 일지가 아니다. 개발 절차는 [CONTRIBUTING.md](CONTRIBUTING.md), 현재 상태는
[docs/STATUS.md](docs/STATUS.md), 연구 설계는 `docs/research/`, 실험은 `experiments/`에 있다. 하위 폴더에 scoped
`AGENTS.md`(`src/inodefence/`, `experiments/`, `docs/research/`)가 있으면 이 문서와 함께 따른다.

## 프로젝트 목적

InodeFence는 TAR 압축 해제 보안을 연구하는 프로토타입이자, 그 검사를 실제 extractor에 돌리는 도구다.

- TAR extraction이 만든 filesystem 보안 상태를 관찰하고, object identity(C1)와 external effect(C2)로 경계 위반을 판정한다.
- 실제 extractor를 격리 컨테이너에서 실행한다.
- 사용자용 명령(`inodefence` CLI, 제품 드라이버)과 연구용 실험 인프라(등록 실험 러너, 사전등록, 증거)는 구분한다.
  제품 쪽 편의가 연구 실행 조건을 바꾸지 않는다.
- 주장은 기록된 증거 수준까지만 한다.

핵심 연구 질문([research-questions v2](docs/research/design/research-questions.md)):

> 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래서, filesystem security state(C1 identity·C2 effect)를
> retention·스케줄링 피드백으로 쓰는 탐색이 **무작위 탐색**과 **구조 커버리지 탐색**보다 첫 경계위반까지의
> 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가?

위협 모델 전제: 공격자는 피해 경로 이름(보호 대상 외부 객체의 추출 루트 기준 상대 경로)을 알며 세 arm 어휘에
동일하게 포함한다. blind 발견을 주장하지 않는다. CVE PoC·고정 공격 패턴·대상 경로·sentinel 이름은 oracle·feedback에
넣지 않는다. v1 질문은 2026-11-03에 폐기했다(research-questions 문서 참조).

## 현재 기준

- 현재 능력과 다음 할 일의 **단일 기준은 [STATUS의 Capability Ledger](docs/STATUS.md)**다. 날짜가 아니라
  마일스톤(M1~M4)으로 관리한다. 마일스톤별 상태는 Ledger에서 읽고 이 문서에 복사하지 않는다.
- 수술 기간(2026-11-03~11-26)의 계획 기준은 Claude Doc 「InodeFence 독립 연구 감사 및 실험 설계 재정립」
  (https://claude.ai/artifact/JJtsK3VowEGuBFN3YXZDFq)이다. 이 문서와 STATUS·BACKLOG가 다르면 문서가 맞고 STATUS는
  그에 맞춰 갱신 중이다. 저장소에 문서 복사본을 두지 않고 포인터만 둔다.
- 실험 실행 기준은 Git에 동결된 사전등록 파일(`experiments/preregistration/`), 증거 기준은 raw + SHA-256 목록
  (`experiments/summaries/raw-manifest-*.sha256`)이다.
- 우선순위: 실제 동작 → 재현 가능성 → 기능 정확성 → 실험적 검증 → 문서화.
- Layer 0~6과 중간발표 P0 단계는 지난 개발 단계의 기록이며 현재 작업 기준이 아니다
  (중간발표 목표 문서는 저장소에서 내렸다. 이력: `git show 4cdfbe2:docs/MIDTERM_GOALS.md`).

## 작업 시작 전

모든 문서를 읽지 않는다. 최소 문맥만 확인하고 작업과 직접 관련된 문서를 더한다.

1. 최소 문맥: [docs/START_HERE.md](docs/START_HERE.md), [docs/STATUS.md](docs/STATUS.md)의 Ledger, 이 문서.
2. 관련 Issue의 수정 가능 영역과 금지 영역을 따른다. 사용자가 직접 확정한 작업 명세는 Task Contract로 따른다.
3. 변경 대상 폴더의 scoped `AGENTS.md`.
4. 작업에 필요한 것만 추가: 설계 문서(`docs/research/design/`), 결정 기록([docs/DECISIONS.md](docs/DECISIONS.md)),
   실험 규칙(`experiments/`), 안전·공개 규칙([SECURITY.md](SECURITY.md)).
5. 이 작업이 Ledger의 어느 마일스톤이나 상시 태스크에 해당하는지 밝힌다. 어디에도 안 맞으면 무엇을 하려는지
   `docs/LOG.md`에 적고 진행한다. 안전 경계와 연구 불변식은 항상 유지한다.
6. 이미 있는 코드를 먼저 찾는다. 루프의 부품은 대부분 존재한다(`effect_campaign.run_effect_campaign`,
   `effect_pipeline.run_node_tar_effect_case`, `effect_scheduler`, `feedback/effect.py`, `oracle`, `observer`).
   새로 만들기보다 연결을 우선한다.

Issue·Task Contract 범위와 Ledger 마일스톤을 넘는 기능을 임의로 추가하지 않는다.

## 권한

에이전트가 스스로 하는 일: 코드·문서 수정, 테스트 작성과 실행, 브랜치 생성과 push, PR 생성·갱신, CI 확인, 독립
검증, 충돌 해소, BACKLOG·STATUS·LOG 갱신, 병합 요청 제출.

사람(지웅)이 결정하는 일. 에이전트는 PR을 열어 두고 "사람 결정"으로 기록하며, 스스로 진행하지 않는다.

- **PR 병합**(아래 [PR](#pr) 절).
- `BREAKING`: Oracle 판정 의미가 바뀌는 변경.
- 가드·격리·allowlist 설정 변경(`.claude/settings.json`·`settings.local.json`, `.claude/hooks/`, 격리 정책 파일). 격리 정책과 Docker 실행
  경계를 완화하지 않는다.
- FROZEN 변경: 동결된 사전등록, 등록 실험 설정, 본실험 실행 SHA.
- 미공개 보안 증거의 공개, 외부 공개, 실제 릴리스(태그·GitHub Release·패키지 게시).
- 승인된 범위를 넘는 실험 실행과 예산.

가드 훅(`.claude/hooks/guard.py`)은 이 가운데 일부만 기술적으로 막는다(`docs/` 아래 금지된 이름의 새 문서, `main`으로
가는 push, 컨테이너 격리 완화 플래그, 가드 설정과 격리 정책 파일 편집). **가드가 막지 않는다고 허용된 것이 아니다.**
가드나 훅이 막으면 우회하지 않고 보고한다. 빠르게 끝내려고 위 경계를 완화하지 않는다.

## PR

병합 운영 규칙은 이 절 한 곳에만 쓴다. 결정 원문은 [docs/DECISIONS.md](docs/DECISIONS.md)의 D050(주제당 브랜치 하나,
PR 하나)과 D037(병합은 지웅)이고, 사람 결정 범위는 D035·D036에서 온다.

- **주제 하나에 브랜치 하나, PR 하나**(D050). 주제 브랜치는 `main`에서 분기한 긴 브랜치이고 이름은 `research/<주제>` 또는
  `product/<주제>`다. `main`으로 가는 PR은 주제당 하나만 열고, 병합 요청 전까지 Draft로 둔다.
- 작업 단위는 GitHub 이슈다. 에이전트는 주제 브랜치에 커밋을 직접 push하고 커밋 메시지에 이슈 번호(`#<번호>`)를 단다.
  작업 하나마다 PR을 열지 않는다. 스택 PR은 쓰지 않는다. 머지 대기는 작업 중단 사유가 아니다. 다음 작업은 같은 주제
  브랜치에 이어서 커밋한다.
- 여러 세션이 한 주제를 동시에 고칠 때만 짧은 하위 브랜치를 쓴다. PR 없이 `git merge`로 주제 브랜치에 합치고 하위
  브랜치는 바로 지운다.
- **병합은 지웅이 한다.** 주제가 `main`에 들어갈 만큼 되면 지웅이 한 번 squash merge한다(D037, D050). 에이전트는
  `gh pr merge` 등으로 스스로 병합하지 않는다. D035의 자율 머지는 보류 상태이고, 수술 기간(2026-11-03~11-26)이 끝난 뒤에도
  지웅의 별도 결정이 기록되기 전에는 재개하지 않는다.
- `main`에서 직접 개발하지 않고 `main`으로 직접 push하지 않는다.
- 주제 PR에는 그 주제의 변경만 둔다. 관계없는 문서 수정·refactor·기능을 섞지 않는다.
- 설명 첫 항목은 "이 PR을 병합하면 어떤 기능을 실제로 실행하거나 검증할 수 있게 되는가?"에 대한 답이다. 답이
  "~에 대한 문서/감사"뿐이면 PR이 아니라 STATUS 갱신이다(예외는 사람이 문서 정비를 PR로 내라고 직접 지시한 경우뿐이며, 에이전트 판단으로 넓히지 않는다).
- **PR을 열지 않는 작업.** `main`에 들어갈 것이 없는 작업(취약점 탐색 실행, 일회성 조사)은 PR 대상이 아니다. 결과는
  Drive에 두고 `docs/LOG.md`에 한 줄만 남긴다. 발견물은 공개 저장소에 올리지 않는다([SECURITY.md](SECURITY.md)).
- 검증: CI는 주제 PR에서 push마다 돈다. verifier(작성자가 아닌 검토자: verifier 에이전트 또는 사람)는 그 PR에 "어느
  SHA까지 검증했는지"를 코멘트로 남긴다.
- 병합 요청의 최소 요건: HEAD SHA까지 CI 두 job(`check`, `container-integration`) 통과와 verifier 판정이 있다.
- **HEAD SHA가 바뀐 PR은 과거 검증 결과를 재사용하지 않는다.** 최신 SHA 기준으로 CI를 다시 받고, 마지막으로 검증된
  SHA 뒤에 바뀐 구간을 verifier가 다시 검증한다.
- 충돌과 `main`의 변경 반영은 `git merge`로 한다. rebase와 force-push는 하지 않는다. 충돌(특히 `docs/LOG.md`
  끝 추가 충돌)은 양쪽 기록을 보존해 해소하고 재검증한 뒤 최신 SHA로 병합을 요청한다.
- 병합 요청은 PR 번호, HEAD SHA, 목적, 변경 범위, CI, verifier 판정, 선행 PR, 권장 순서를 표로 낸다.
- 적용 범위: 2026-11-18(D050) 이후에 시작하는 모든 작업. 그 전에 열린 PR은 그대로 둔다.

## 금지

- 새 audit / readiness / handoff / qualification / "preserve" 문서 파일을 만들지 않는다. 기록은 `docs/STATUS.md`
  갱신 또는 `docs/LOG.md`에 한 줄 추가로 한다.
- 발표 데모만을 위한 임시 구현으로 기존 기능 안정성을 해치지 않는다.
- 실제로 적용되지 않은 feedback/결과를 적용된 것처럼 기록하지 않는다.
- 결과를 본 뒤 방법·지표·예산을 바꾸지 않는다.
- 기존 architecture를 임의로 재설계하지 않는다. 모호하면 [docs/DECISIONS.md](docs/DECISIONS.md)의 기존 결정이 우선한다.

## 연구 규칙

1. CVE 식별자를 oracle 조건에 직접 하드코딩하지 않는다.
2. 알려진 CVE PoC를 rediscovery 실험의 기본 fuzzing seed로 사용하지 않는다.
3. Known CVE는 benchmark ground truth와 root-cause 분석에는 사용할 수 있다.
4. 보안 판정은 가능한 한 일반화된 Security Contract로 표현한다.
5. 관찰된 사실과 가설/예상 결과를 구분한다. 관찰한 상태(observed)와 추론·재구성한 상태(inferred)를 구분한다.
6. raw experiment output과 논문에 사용할 결론을 분리한다. raw는 손으로 고치지 않는다.
7. 성능 관련 논문 주장은 기록된 실험 설정과 결과로 재현 가능해야 한다. 실측과 비교 없이 우위를 주장하지 않는다.
8. synthetic 실행 결과를 native(실제 extractor) 증거로 올려 쓰지 않는다.
9. 구현됨, 테스트됨, 실험으로 검증됨을 구분한다(DESIGNED · IMPLEMENTED · TESTED · VALIDATED,
   [Research Contract](docs/research/design/research-contract-v1.md)).
10. 재현되지 않은 finding이나 위반 후보를 확인된 취약점이라고 부르지 않는다. 통제 재현과 퍼저의 자력 발견을
    구분한다.

## 연구 포지셔닝

새로움(novelty)은 확정된 사실이 아니라 **검증해야 할 가설**이다. 이 프로젝트는 TAR fuzzing, hardlink, symlink, entry
order, filesystem-state fuzzing, outside-root write 자체가 새롭다고 주장하지 않는다. 관련 선행연구가 중요한 부분을
이미 다룬다.

- Jana & Shmatikov: TAR 공격을 포함한 file-processing semantic gap
- ZIPDiff: feedback-guided archive differential fuzzing
- LinkZard: link 관련 상태를 포함한 feedback-driven file-state fuzzing
- Wormholes: symlink composition, hardlink, path resolution, creation order를 이용한 archive extraction 공격

InodeFence가 검증하는 가능성은 "generic TAR-entry mutation + filesystem-security-state feedback"이다. 문헌 근거가
명확하지 않은 상태에서 "최초", "새로운", "기존 연구에 없음" 같은 표현을 만들지 않는다.

## Security Contract 우선순위

1. **Path Boundary Confinement** — 기본 path 경계 sanity/baseline. 중요하지만 InodeFence의 novelty는 아니다.
2. **Object Identity Confinement** — extraction 내부 object가 보호된 외부 sentinel과 의도하지 않게 동일 filesystem
   identity를 공유하면 안 된다.
3. **External Effect Noninterference** — archive extraction으로 보호된 외부 sentinel의 content/metadata가 의도하지 않게
   변경되면 안 된다.
4. **Extraction Root Integrity** — 최소 pipeline 이후 확장.
5. **Check/Use Coherence** — instrumentation이 필요한 후속 단계.

정의는 [security-contracts.md](docs/research/design/security-contracts.md)를 따른다.

## 범위

포함: TAR extraction, Linux filesystem semantics, regular file·directory·hardlink·필요한 범위의 symlink, entry path·link
target·type·order·dependency mutation, filesystem object identity, external effect, feedback-guided corpus evolution, 알려진
취약점의 통제 재현과 재발견 실험, 여러 extractor 간 적용 가능성 평가. 연구 MVP 대상과 확장 대상은 D038을 따른다
(node-tar와 Python `tarfile`이 MVP, decompress는 확장, oras-go는 oracle 일반성 증거).

제외: 모든 archive format, GNU tar, entry 전이 관찰 계열, Windows NTFS semantics, 일반적인 kernel filesystem
vulnerability, 전체 TOCTOU/race-condition 분석, 완전한 symbolic execution, Wormholes의 모든 bypass 재구현, 전체
archive-parser ambiguity 분석.

## 안전 규칙

- `/etc/passwd`, SSH key, 사용자 문서, host secret 같은 실제 민감 파일을 공격 대상으로 사용하지 않는다.
- disposable sandbox와 sentinel만 사용한다.
- 테스트와 실험은 host를 손상시키지 않고 재현 가능해야 한다.
- 파괴적인 filesystem operation은 runtime sandbox 내부로 제한한다.
- 소스 bind mount를 filesystem semantics 실험 공간으로 쓰지 않는다. 실험 공간은 `$INODEFENCE_RUNTIME_ROOT`
  (기본 `/var/lib/inodefence`)다.
- 실제 extractor 실행은 팀이 승인한 범위(고정 버전, 실행 예산 상한, disposable sandbox + sentinel)에서만 하고, 결과는
  `demo run`으로 라벨링한다(qualification 아님). 등록 실험은 사전등록과 isolation contract를 그대로 따른다.
- docker 기반 실험은 격리 완화 없이 동일한 잠긴 하너스가 그대로 도는 환경에서만 돌린다. 클라우드 세션은 코드와
  분석의 병렬화에 쓰고, 그 조건을 만족하지 못하면 실험은 docker 호스트에 둔다.
- 미공개로 보이는 문제의 처리와 공개는 [SECURITY.md](SECURITY.md)를 따른다.

## 아키텍처 경계

```text
Seed Generator -> Structure Mutator -> TAR Builder -> Target Adapter
    -> State Observer -> Security Oracle -> Feedback / Corpus -> next mutation
```

각 책임을 분리한다. 특정 target/CVE 로직이 generic mutation, observer, oracle, feedback 모듈에 섞이지 않도록 한다.

사용자 명령 계층은 위 pipeline 바깥에 있다.

```text
inodefence (cli.py) -> locate.py -> 제품 드라이버 (src/inodefence/drivers/) -> 위 엔진 모듈
```

제품 드라이버(`inodefence.drivers`)는 대상별 verify/explore/replay 실행을 엔진 조합으로 구성한다. 엔진 모듈은
드라이버·`locate`·`cli`를 import하지 않는다. 저장소 경로는 `drivers/repo.py` 한 곳에서 얻는다. 옛 `scripts/` 경로
일부는 호환 별칭으로 남아 있다([scripts/README](scripts/README.md)).

## 구현 규칙

- 변경 대상 계층의 책임 안에서만 구현한다.
- 변경 이유를 사람이 이해할 수 있는 이름/구조로 남긴다.
- generic logic과 target-specific logic을 분리한다.
- 숨은 magic value보다 명시적인 data model/config와 typed interface를 사용한다.
- 실험 seed와 configuration은 재현 가능하게 명시한다.
- 복잡한 추상화보다 읽기 쉬운 작은 interface를 우선한다.
- 새 공통 개념을 만들면 문서 또는 docstring으로 의미를 남긴다.

## 변경 영향 규칙

다음이 바뀌면 코드만 수정하지 않고 같은 PR에서 문서를 고친다.

- 공통 data model/interface, 계층 책임 → 관련 design 문서
- Security Contract → `security-contracts.md`
- 큰 설계 결정, target 우선순위, 프로젝트 범위, experiment methodology → `docs/DECISIONS.md`와 관련 design 문서
- 현재 단계/다음 작업 → `docs/STATUS.md`
- 프로젝트 이해 흐름 → `docs/START_HERE.md`

## 개발 환경과 검사

기준 환경은 저장소 Dev Container(Ubuntu 24.04 + Python 3.12, 소스 `/workspaces/InodeFence`)이고 macOS와 Windows +
WSL2에서 같은 컨테이너를 쓴다. 완료 전에 canonical validation command `make check`를 실행한다. 환경 준비, 검사 단계,
CI는 [CONTRIBUTING.md](CONTRIBUTING.md)에 있다. 사용자 명령 `inodefence`의 설치와 실행은
[docs/USAGE.md](docs/USAGE.md)에 있다.

## 문서 책임

읽는 순서: START_HERE → STATUS → 이 문서 → 필요한 design 문서 → research notes / CVE analysis.

- `docs/research/`: 연구 근거, 설계, 선행연구, CVE 분석
- `experiments/`: 실험 설정과 결과
- `paper/`: 실제 논문에 사용할 준비가 된 내용

연구 메모가 자동으로 논문 주장이 되는 것은 아니다.

## 레인 (우선 책임자)

- 지웅: Core / Architecture / Integration (통합 책임, 병합)
- 주언: Feedback / Evaluation
- 규민: Runtime / Target Execution
- 민찬: Observation / Oracle / Demo

담당 영역은 우선 책임자를 뜻하며, 인터페이스 연결과 최종 검증은 서로 협력한다.
