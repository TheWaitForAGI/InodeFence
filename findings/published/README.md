# 공개 승인된 finding

팀의 공개 결정이 끝난 sanitized/reproducible finding만 Git으로 추적한다.
[SECURITY.md](../../SECURITY.md)의 lifecycle을 따른다.

공개 전에 다음을 확인한다.

- private 재현, 최소화, root cause 분석과 사람의 team review 완료
- 필요한 vendor coordination 및 팀의 공개 시점·범위 합의 완료
- secret, 개인정보, 미공개 exploit artifact와 불필요한 환경 식별 정보 제거
- Known CVE / unknown finding 및 관찰 / 가설 / 확인 상태 명시
- target/version, 환경, InodeFence commit, config와 안전한 재현 절차 연결
- 실험 evidence와 공개 가능한 작은 summary 연결

공개 자료가 있다는 사실만으로 새로운 취약점이나 paper claim이 확정되는 것은 아니다.
