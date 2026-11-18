# evidence/registered-experiments

이 브랜치는 등록 실험(EXP-3, EXP-2)의 증거 커밋을 한곳에 묶어 보존하는 이력 전용 브랜치다.

- 이 커밋은 아래 표의 각 커밋을 부모로 갖는 병합 커밋이며, 트리에는 이 파일 하나만 들어 있다.
  원래 커밋의 SHA·작성 시각·내용은 바뀌지 않으며, 각 커밋은 이 브랜치의 조상으로 그대로 닿는다.
- 이 브랜치는 main에 병합하지 않는다.
- 결정: 2026-11-18 지웅(이슈 #496). 옛 브랜치들을 이 브랜치 하나로 묶은 뒤 옛 브랜치는 지운다.
- "GitHub에 보존용 브랜치를 새로 만들지 않는다"는 정리 원칙의 명시적 예외다.
- 동결 태그는 지우지 않으며, 태그가 가리키는 커밋도 함께 부모로 넣었다.

| 종류 | 옛 이름 | tip SHA | 관련 PR | 비고 |
| --- | --- | --- | --- | --- |
| 브랜치 | claude/p0-331-exp3-control-integration | f133b85115ae5c2d3b07422dad94a01ad4aacf7f | #330(merged) |  |
| 브랜치 | claude/p0-332-host2-qualification | cab465287f3ba2d72cd0e7a3eba66125188ddb7c | #333(merged) |  |
| 브랜치 | claude/p0-334-exp3-exp2-prereg-draft | 671788c3382c9ac7e541368a7340e244aeefa4c0 | #332(merged) | 사전등록 초안. 지웅이 보존을 지시했던 브랜치 |
| 브랜치 | claude/p0-339-d4-holdout-locks | bbdcbfdf64e3e856fcc0048c98a2835f725589b8 | #338(closed) |  |
| 브랜치 | claude/p0-351-host-qual-host1-log | 3c6d7b7c9d6e10060a2cd8e65a5c928bc3bbec06 | #351(merged) |  |
| 브랜치 | claude/p0-358-exp3-train-pin | 1edb4c21a3f177375d272e8439b66354150987bb | #360(merged) |  |
| 브랜치 | claude/p0-369-w3-exp3-go | 4efde658a21bf3edccc8462a2f8c0a9ae1eddd52 | #368(merged) |  |
| 브랜치 | claude/p0-372-exp2-holdout-host2-stop1 | 5d9551b42d9e4eaf9721bc79f4c517bb895279bc | #370(merged) |  |
| 브랜치 | claude/p0-389-w3-unseal-record-tool-log | b0bb1be25439c639271da078ccabc935b61fbe6d | #389(merged) |  |
| 브랜치 | claude/p0-holdout-host1-stop1 | ccb36488d28d3058d3ca476dc9c566547b0760da | #454(merged) |  |
| 브랜치 | claude/p0-holdout-host1-stop2 | 9db9ca361712be18fa67fe879688d668dc530525 | #458(merged) |  |
| 브랜치 | claude/p0-holdout-host2-stop2 | 3af4d478d91f4a9516b9b1ee8b9aeebbec4b2b04 | #417(merged) |  |
| 브랜치 | claude/p0-holdout-host2-stop3 | c582018e96303f17f79ff96358a31d9bae184120 | #453(merged) |  |
| 브랜치 | claude/p0-holdout-host2-stop4 | c8c24fe289ab4125cd25de3b389927af63c2eb9e | #460(merged) |  |
| 브랜치 | claude/p0-holdout-host2-stop5 | 9e7938b0fbdf6ff1a6e8cac0fd1dfaa9bc1dc737 | #478(merged) |  |
| 브랜치 | claude/s3-exp0-prereg-v2.1 | ef8bad1062c050bd5be44b442ec4df0f8eec17e6 | #238(merged) |  |
| 브랜치 | claude/s3-exp3-launcher | fc94473d70f71b373d974cd2da5c3cae4e05c87d | #230(merged) |  |
| 브랜치 | claude/s3-exp3-prereg-parsercompat | e11d302e77b7122e4056af2374bf4682d282f16b | #264(closed) |  |
| 브랜치 | claude/s3-exp3-prereg-skeleton | 00762a5e181e5dce7d695f5b61505a07e97720e9 | #239(closed) |  |
| 브랜치 | claude/s3-exp3-sizing-input | 72c42d023631a2658e43450aec5393f3e3643b2a | #263(closed) |  |
| 브랜치 | claude/s3-exp3-targets | a7249cf981727844f38f02c21fc9ca1bad3117f2 | #244(merged) |  |
| 브랜치 | claude/s3-g1-integration | 80904b882b0a2933a023835943c182c627014a08 | - |  |
| 브랜치 | claude/s3-rds-runner | b02edf6c21aad42620b64978b4ea9cb31b4a5b00 | #206(merged) |  |
| 브랜치 | claude/w1-exp3-analysis-values | c0594cc7de306c077423f81952a2e9324f289371 | #299(closed) |  |
| 브랜치 | claude/w1-exp3-cell-results | 5555e19a5e7fbc5132eb7ecde626eba55e3d78e5 | #297(closed) |  |
| 브랜치 | claude/w1-exp3-operating-check | 9afc04120c3aafb07de3b32223fd63cc1e880bf7 | #302(closed) |  |
| 브랜치 | claude/w1-exp3-permutation-d10 | c14c75d6b411aba3cf7556473392271930359dd1 | #300(closed) |  |
| 브랜치 | claude/w1-exp3-synthetic-e2e | 59939d7d45da963fd384d088e253da00f9ee9b01 | #301(closed) |  |
| 브랜치 | claude/w1-exp3-table-generators | de25418a90154eff91bd9472c0aad2d94fe91793 | #298(closed) |  |
| 브랜치 | claude/w2-exp3-hazard-pilot-v1 | 99955fa1cde9d4f06df9c2e2b593afe8448e3623 | #267(merged) |  |
| 브랜치 | codex/host2-validation-20261110 | 9c5c98138f2a1c618eb4711832ae27afdfbc0857 | - |  |
| 브랜치 | claude/p0-370-exp2-holdout-pin | b78ef8569206c98dbfd45a549f6487de48424db6 | #369(merged) | EXP-2 holdout 사전 고정 |
| 브랜치 | claude/p0-485-w3-exp2-unseal-record | 3bee69d65c9b29d492798c7691a18db148d28694 | #485(merged) | 봉인 해제 기록 |
| 태그 | prereg-exp3-exp2-freeze-20261113 | 72de29912dbe061c998bf5baf61720eb74987f14 | - | 동결 태그가 가리키는 커밋(태그는 유지) |
| 태그 | audit-baseline-20261103 | bb3fd7c889cb27684d3193b5e895978f97ba28c1 | - | 동결 태그가 가리키는 커밋(태그는 유지) |

## 2026-11-18 추가: 실험·원장 문서가 인용하는 커밋 7개

독립 검토(QA, 이슈 #496)에서 실험·원장 문서가 인용하지만 이 브랜치와 main 어디에서도 닿지 않던 커밋 7개를 찾았다.
이 커밋 하나로 그 7개를 부모로 더했다. 첫 부모는 앞의 병합 커밋 `0fadbd1`이고, 앞의 내용은 바뀌지 않는다.
7개 모두 예전에 공개 원격에 있던 브랜치의 조상이다(2026-11-17 mirror bundle에서 확인). 그 브랜치는 정리 때 지웠다.

| 종류 | 그 커밋을 갖고 있던 옛 브랜치 | 커밋 SHA | 인용 | 비고 |
| --- | --- | --- | --- | --- |
| 인용 커밋 | jiwoong/p-m4-5-decompress-selfdiscover-win | 5361c6225e0f2694b47167197afdf2a707f20634 | M4.5 사전등록·실행 | |
| 인용 커밋 | jiwoong/p-m4-5-decompress-selfdiscover-win | 746adc0a87f6c8146209d3a777930c4bf1aeb747 | M4.5 사전등록·실행 | |
| 인용 커밋 | jiwoong/p-m4-5-decompress-selfdiscover-win | ad384e4bc7da2c9c3e44625034ccdab3a6ba458c | M4.5 사전등록·실행 | |
| 인용 커밋 | claude/p0-355-exp-run-runbook | 89b63bad8f2a650f9ca9c3c4eb808174278b39d3 | #354 등록 | |
| 인용 커밋 | minchan/p0-2-observation-capture | 1f6ca9022fda4d468d7b6ead2f0644f2cf5d9e09 | host2 validation | |
| 인용 커밋 | codex/host-freeze-validation-20261109 | 6dddb7568ff3101a30eeba93cdabac5fccdfd369 | host2 validation | |
| 인용 커밋 | claude/s3-exp0-confirmatory-direction | f655f185d778228b33d908ebf1d8f39f32fcd5a1 | EXP-0 premerge 리포트 코드 | |

## 이 브랜치에 넣지 않은 인용 커밋 (Drive bundle에만 있음)

등록 실험 증거가 아니라서 이 브랜치의 범위 밖이다. 원격에는 브랜치로 남아 있지 않다.
되살릴 때는 Drive `InodeFence/Archive/Git-Refs-20261117/`의 bundle에서 `git fetch <bundle> <ref>`로 가져온다.

- 주장 목록(`paper/sections/claims-evidence-status-v1.md`)의 측정 시점 커밋 5개:

| 커밋 SHA | 들어 있는 Drive bundle |
| --- | --- |
| 0f37cfc5d17f1ee1e601e66e5daf7a03a833155f | InodeFence-github-mirror-all-20261118b.bundle(`refs/pull/490/head`, `refs/pull/506/head`. GitHub의 PR 참조로도 남아 있다) |
| 6a2031f4a94b012374366f2cb430d0de9331baaa | InodeFence-github-mirror-all-20261118.bundle |
| 7ee495be996cfec230502063b6cf83ad6e350a95 | InodeFence-github-mirror-all-20261118.bundle |
| aa4cda3c6235949868e4c907500d0adc4cfc16d8 | InodeFence-github-mirror-all-20261118.bundle |
| f108e361ca0b2aa54c79d665fbf6ad810048fe67 | InodeFence-github-mirror-all-20261118.bundle |

- `docs/LOG.md`에만 나오는 개발 커밋 약 90개: 같은 폴더의 `InodeFence-github-mirror-all-20261117.bundle`과 `…-20261118.bundle`에 있다(QA 대조, 이슈 #496 코멘트).
- 후속: main 쪽 문서(주장 목록 등)에 "Drive bundle에만 있음" 주석을 다는 일은 `paper/` 변경이라 이번에 하지 않았다.
