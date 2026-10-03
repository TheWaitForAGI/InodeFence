# Safe reference campaign 개발 pilot v1

이 기록은 engineering validation이다. 연구 effectiveness, 취약점 rediscovery, finding 또는
paper evidence가 아니다. Evidence 분류는 **REPRODUCIBLE (development semantic checks only)**다.

Engine revision은 `cac0ed3`이며 runner의 SHA-256와 exact Python/target/kernel/architecture,
initial ArchiveCases, RNG seeds, budgets, timeout과 모든 status 수는
[기계가 생성한 요약](reference-campaign-pilot-v1.json)에 기록했다. Python 3.12.3/data reference,
Linux aarch64 Dev Container와 `/var/lib/inodefence` disposable runtime만 사용했다.

실행 명령 (repository root, Linux Dev Container):

```bash
python -m scripts.reference_campaign_pilot --output experiments/raw/<new-directory>
```

[Runner](../../scripts/reference_campaign_pilot.py)는 regular/directory/hardlink/symlink의 기존
4종 정상 baseline을 명시적으로 전달했다. 두 seed × budget 25/50/100과 seed 23/budget 50의
repeat를 포함해 7 campaigns, 총 400 executions다. Summary는 runner가 raw CampaignResult의
status/stats를 집계하며 성공만 필터하지 않는다. Raw 결과는 canonical JSON으로
`experiments/raw/reference-pilot-v1/`에 로컬 보존돼 있고 Git ignore 대상이다. 각 파일명과
SHA-256은 요약에 있다. 공유 storage에 업로드하지 않았으며 다른 checkout은 위 명령으로
재생성해야 한다. 원본 summary.json을 그대로 복사했으며 raw evidence는 수동 수정하지 않았다.

| RNG seed | Budget | Retained cases | Success | Rejected | Failed | Timed out | Peak traced bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 11 | 25 | 12 | 22 | 2 | 1 | 0 | 525592 |
| 11 | 50 | 20 | 41 | 6 | 3 | 0 | 730723 |
| 11 | 100 | 38 | 76 | 14 | 10 | 0 | 1193604 |
| 23 | 25 | 14 | 17 | 5 | 3 | 0 | 501090 |
| 23 | 50 | 20 | 33 | 10 | 7 | 0 | 718083 |
| 23 | 100 | 34 | 74 | 17 | 9 | 0 | 1151049 |
| 23 | 50 | 20 | 33 | 10 | 7 | 0 | 718095 |

모든 campaign이 정확한 budget과 zero-based indices로 종료했다. 예상하지 못한 exception은
없었다. 모든 run sandbox가 정리됐으며 runtime directory inventory는 시작 상태로 돌아왔다.
Repeat는 ArchiveCase sequence, parent lineage, FeedbackDecision semantic fields, retained order와
final stats가 일치했다. Raw inode/timestamp/duration은 비교하지 않았다. No-op과 네 status의
budget accounting은 별도 회귀 검사에서도 확인한다; 이번 pilot에는 timeout이 발생하지 않았다.

Peak는 tracemalloc으로 campaign 호출 중 측정한 Python allocation이며 worker/OS RSS나
전체 process memory가 아니다. 소규모 실행에서 100-budget peak는 약 1.2 MB 이하였으나
이 수치로 대규모 campaign의 resource bound 또는 throughput을 주장하지 않는다. Full RunResult
보존은 O(budget)이며 output/evidence 크기도 memory에 영향을 준다. Corpus 성장 자체를
효과의 증거로 해석하지 않았고 feedback policy를 바꾸지 않았다.

현재 limitation: reference 한 종류와 작은 budgets, transient/sandbox 밖 관찰 불가,
RNG/Python version과 semantic feedback에 의존하는 lineage, 로컬 raw evidence 보관이다.
Formal comparison, repetition variance, benchmark version validation이나 paper claim은 없다.
