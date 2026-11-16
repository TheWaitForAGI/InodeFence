# 보안 정책

InodeFence는 TAR 압축 해제 보안을 연구하는 프로토타입이자, 그 검사를 실제 extractor에 돌리는 도구입니다. 이 문서는
보안 문제를 발견했을 때 무엇을 해야 하는지, 그리고 이 프로젝트가 finding을 어떤 절차로 검증하고 공개하는지를
정합니다.

## 적용 범위와 저장소 상태

- 이 저장소는 **공개(PUBLIC) 저장소**입니다. 모든 브랜치의 커밋, Pull Request, Issue, 댓글, CI 로그와 CI artifact는
  외부에서 열람할 수 있습니다.
- 한 번 push한 내용은 나중에 지워도 복제본, fork, 캐시에 남을 수 있습니다. 그래서 미공개 자료는 처음부터 Git 이력과
  CI 로그에 들어가지 않게 합니다.
- Git ignore는 접근 통제가 아닙니다. 파일이 실수로 commit되는 것을 줄여 줄 뿐이고, 이미 있는 자료를 보호하지
  않습니다.
- 이 정책은 저장소의 코드, 문서, 실험 기록, 그리고 이 도구로 얻은 finding의 취급에 적용됩니다.
- 지원 버전 정책, 응답 기한, 보상 프로그램은 없습니다. 연구 프로토타입이며 그런 보장을 약속하지 않습니다.

## 보안 문제의 두 종류

제보하거나 기록하기 전에 어느 쪽인지 먼저 구분합니다. 접수 주체와 절차가 다릅니다.

| 종류 | 예 | 누가 다루는가 |
| --- | --- | --- |
| **InodeFence 자체의 문제** | CLI나 실행기의 보안 결함, 격리 경계 위반(컨테이너 밖 host 파일에 영향), 실행 결과나 로그에 민감 정보가 노출됨, 의도하지 않은 파일 접근·삭제, 증거 저장·공개 과정의 문제 | 이 저장소의 유지보수자 |
| **실험 대상 extractor의 문제** | InodeFence로 node-tar, Python `tarfile`, `@xhmikosr/decompress`, oras-go 등 지원 대상에서 관찰한 경계 위반 | 해당 extractor의 upstream 유지보수자 |

InodeFence 유지보수자는 외부 extractor의 취약점을 접수하거나 수정하는 주체가 아닙니다. extractor의 문제는 그 프로젝트가
공개한 공식 보안 연락 절차로 조정합니다. 이 문서는 upstream 연락처를 싣지 않으며, 각 프로젝트의 보안 정책을 직접
확인해야 합니다.

InodeFence가 "위반"으로 판정했다는 사실만으로 extractor의 취약점이 확인된 것은 아닙니다. 판정은 일반화된 Security
Contract에 따른 관찰이고, 취약점 여부는 아래 검증 절차의 재현과 원인 분석을 거쳐야 정해집니다.

## 비공개 제보

**현재 이 저장소에 확인된 비공개 제보 채널은 없습니다**(2026-11-17 확인).

- GitHub의 Private Vulnerability Reporting은 이 저장소에서 켜져 있지 않습니다.
- 보안 제보용 이메일 주소나 그 밖의 비공개 연락 경로는 정해지지 않았습니다.
- 채널을 마련할지와 어떤 채널을 쓸지는 유지보수자의 결정 사항입니다. 결정되면 이 절에 적습니다.

그때까지 지켜 주실 것:

- 취약점의 세부 내용(재현 입력, PoC, exploit, 영향 분석, 영향받는 버전 정보)을 공개 Issue, Pull Request, 댓글에 올리지
  않습니다. 공개 Issue는 비공개 제보를 대신하지 않습니다.
- 실험 대상 extractor의 문제는 이 저장소가 아니라 해당 upstream의 공식 보안 절차로 알립니다.
- 보안과 무관한 버그와 사용 문의는 평소처럼 공개 Issue를 씁니다.

## Finding 검증 절차

이 프로젝트 안에서 finding은 다음 순서를 따릅니다. 단계를 건너뛰지 않습니다.

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

1. **Potential Finding.** 관찰된 사실과 미확인 가설을 구분해 적습니다. 확인되지 않은 finding은 공개 Issue에 올리지
   않고, 팀이 접근을 통제하는 private 기록 경로로 공유합니다. 이 단계의 기록은 위반 후보이며 취약점이 아닙니다.
2. **Private Reproduction.** disposable sandbox와 sentinel만 써서 재현하고 target과 버전, 환경, InodeFence commit, 설정,
   재현 결과를 기록합니다. 실제 host secret이나 민감 파일을 evidence로 쓰지 않습니다. 재현되지 않은 것은 확인된
   위반이라고 부르지 않습니다.
3. **Minimization.** 원본 evidence는 그대로 보존하고, 재현에 필요한 최소 사례를 별도로 만듭니다. 원본을 고치거나 지워서
   최소 사례를 만들지 않습니다.
4. **Root Cause Analysis.** harness·환경 오류와 target의 실제 동작을 구분합니다. generic Oracle의 판정과 target 코드의
   원인을 구분합니다. 이미 알려진 CVE(통제 재현)와 알려지지 않은 finding을 명확히 구분합니다.
5. **Team Review.** 재현성, 원인 분석, 영향 범위, 민감 자료 포함 여부를 사람이 검토합니다. 재현된 위반을 취약점으로
   부를지는 이 검토에서 정합니다.
6. **Vendor Coordination.** 팀이 확인한 upstream의 공식 보안 연락 경로를 씁니다. 실제 취약점의 PoC와 exploit artifact는
   vendor coordination 전에 public branch에 commit하지 않습니다.
7. **Disclosure Decision.** CVE 신청, vendor 연락, 공개 시점과 공개 범위는 팀 합의 뒤에 진행합니다. coordination을
   시작했다는 사실만으로 공개 승인이 되지 않습니다.
8. **Public Finding / Paper.** 공개 결정이 끝난 sanitized/reproducible 자료만 [findings/published](findings/published/README.md)에
   추적합니다. 논문 주장에는 검토된 evidence를 연결합니다.

## Vendor coordination과 공개 권한

미공개 취약점을 외부에 알리는 일은 사람의 결정입니다. 다음은 팀 합의와 사람(유지보수자)의 승인 없이 하지 않습니다.

- upstream에 미공개 PoC나 재현 자료를 전달하는 것
- 외부 vulnerability report 제출과 CVE 신청
- exploit이나 취약점 상세의 공개, 공개 시점의 확정
- GitHub Security Advisory 발행
- 미공개 자료를 공개 Pull Request, Issue, 댓글, CI artifact에 붙이는 것

코딩 에이전트는 재현 증거를 정리하고 공개 가능성 검토를 도울 수 있지만 위 행동을 스스로 하지 않습니다. 사람 결정의
범위는 [AGENTS.md의 권한 절](AGENTS.md#권한)에 있습니다. upstream 연락처나 vendor 이메일은 추측해 문서에 적지
않습니다. 공개 가능 여부가 모호하면 팀 검토에서 정하고, 정해지기 전에는 공개 단계로 넘기지 않습니다.

## 민감 증거의 보존과 공유

- 미공개 자료는 `findings/private/` 또는 접근이 통제된 별도 저장소에 둡니다. `findings/private/`의 내용은 Git ignore
  대상이지만, 그것만으로 보호되지 않습니다. `git add -f`, 로그, 첨부파일, CI artifact로 미공개 자료가 이력에 들어가지
  않게 commit 전에 확인합니다.
- raw evidence와 최소화된 재현 사례를 구분해 보관합니다. 원본을 지우거나 고쳐 증거 무결성을 해치지 않습니다. 실험
  증거의 기준은 raw와 SHA-256 목록입니다([summaries 규칙](experiments/summaries/README.md)).
- 실험 출력은 저장소 밖에 둡니다. `inodefence` 명령은 출력 위치가 저장소 안이면 실행 전에 거부합니다. 클라우드 동기화
  폴더에도 위반 입력과 raw 데이터를 두지 않습니다.
- 공개하려는 자료에 개인정보, secret, 불필요한 환경 식별 정보(계정 이름, 로컬 경로, 내부 주소, 호스트 이름)가 들어
  있는지 확인하고 제거합니다.
- 공개 권고문의 영향 범위 안에 있는 특정 버전의 탐색 수치(위반 수, 종료 상태 분포 등)는 공개 문서에 적지 않습니다.
- 대량 raw 실험 결과의 보존·공유 경로는 별도로 기록하고 접근을 통제합니다.

## 공개 자료와 연구 주장

- [findings/published](findings/published/README.md)에는 공개 결정이 끝난 자료만 둡니다. 공개 전 확인 항목은 그 문서에
  있고, 폴더 구성은 [findings](findings/README.md)에 있습니다.
- 논문과 발표 자료에 넣는 정보도 별도의 공개 검토를 거칩니다. 연구 결과를 정리하는 일과 vendor에 알리는 일은 서로를
  대신하지 않습니다.
- 공개 자료가 있다는 사실만으로 새로운 취약점이나 논문 주장이 확정되지 않습니다. 알려진 취약점의 통제 재현과 퍼저의
  자력 발견을 구분하고, 주장은 기록된 증거 수준까지만 합니다([AGENTS.md의 연구 규칙](AGENTS.md#연구-규칙)).

## 라이선스와 보증

InodeFence 소스는 [MIT License](LICENSE)로 배포되며 보증 없이 제공됩니다. 실험 대상 extractor와 의존성은 각자의
라이선스를 따릅니다. 이 도구는 격리된 실험 환경에서 자신이 권한을 가진 대상에만 사용합니다. 실제 host의 민감 파일을
실험 대상으로 쓰지 않습니다([README의 보안 및 실행 제한](README.md#보안-및-실행-제한)).
