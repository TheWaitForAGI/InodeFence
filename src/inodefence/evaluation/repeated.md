# Independent run orchestration metadata

`RepetitionPlan` requires canonical public ExperimentConfig JSON, an explicit
unique ordered seed list (first seed matches base config), and captured expected
source/target/runtime/sentinel/isolation provenance. Budget and all non-seed
settings stay fixed. Each seed has its own derived config ID and result directory.

`RepetitionController.create(directory, plan)` creates a new immutable plan.
`claim(index, attempt_id=...)` exclusively reserves a directory before execution.
Callers own independent executions and put their export at `slot/evidence`.
`complete(index)` verifies the full export, exact derived config and provenance,
then publishes an immutable terminal marker. Existing directories, claims and
terminal records are never overwritten. A separate observer can use
`read_repetitions(directory, expected_plan_sha256=...)` to check persisted facts.

PENDING is unclaimed. STARTED is claimed without an acknowledged terminal record,
even if raw export files exist. COMPLETED requires verified matching raw evidence.
FAILED is an infrastructure-aborted attempt with a bound Failure Ledger. INVALID
is an explicitly invalidated attempt with a ledger, or a directory reservation
interrupted before claim publication. Both are invalid analysis denominators,
not target FAILED status or evidence of no contract violation. Unknown phase,
cleanup or partial core observations are not invented. Timestamps are metadata
record times, not campaign elapsed time. Corrupt evidence raises verification
failure rather than disappearing from counts. Incomplete reservations are never
automatically retried; no duplicate campaign execution is scheduled.

Reconstructing a controller resumes scheduling metadata only. There is no search
checkpoint/resume or automatic arbitrary-case campaign executor. A trusted
single writer owns publication; raw artifact parents must be trusted. An aborted
terminal publication can leave a completed ledger/export without acknowledgement,
which remains STARTED for explicit recovery. COMPLETED means verified export,
not qualification, dataset compatibility, rediscovery or paper readiness.
