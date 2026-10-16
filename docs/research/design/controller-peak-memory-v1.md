# Controller peak-memory observation v1

Status: **IMPLEMENTED / ENGINEERING TESTED; PILOT MEASUREMENT NOT_RUN**.

This contract defines the passive controller-memory measurement required by the proposed
B0/B1/B3 pilot. It does not authorize the pilot, measure a historical campaign, or change any
search, mutation, target, oracle or feedback semantics.

## Measurement and scope

The profile is `linux-proc-self-vmhwm-v1`. Immediately before a repetition slot is claimed,
the controller reads these Linux procfs facts for its own process:

- `Pid`, `VmRSS` and `VmHWM` from `/proc/self/status`;
- process start ticks from field 22 of `/proc/self/stat`;
- `/proc/sys/kernel/random/boot_id`; and
- the system clock-tick frequency.

After the policy journal and repetition terminal have been published, it reads the same facts
again. `VmHWM` is multiplied from the kernel's `kB` unit to bytes. The reported feasibility
value is the final **process-lifetime peak resident bytes**. It is not `end - start`, an
allocation total, a campaign-attributable delta or a target-container measurement.

For pilot interpretation, each campaign must be launched in a fresh dedicated controller
process. The reader binds `(boot_id, pid, process_start_ticks)` and rejects reuse of one
process identity across measured slots; `execute_measured` also refuses reuse before claiming
another slot. A process may still have imported code or performed launcher setup before the
first sample, so its lifetime HWM is deliberately a conservative controller-process upper
bound. The separately isolated target container remains governed by its recorded 512 MiB
limit and is outside this value.

## Evidence binding

`controller-memory.json` is an atomic no-overwrite record in one repetition run directory. It
binds:

- plan, run index/ID, configuration and attempt identity;
- checksums of `claim.json` and `terminal.json`;
- the exact completed or failure journal terminal artifact;
- start/end UTC timestamps and monotonic elapsed nanoseconds; and
- both typed procfs samples and the fixed scope string
  `current-process-lifetime-not-campaign-delta`.

The independent repetition reader recomputes all referenced digests, checks the terminal
state/artifact relation, requires stable process identity and nondecreasing HWM, and rejects
duplicate measured process identities. For a pilot read, pass
`--require-controller-memory`; every completed/failed/invalid terminal must then carry the
record. Pending and hard-interrupted STARTED slots cannot invent a terminal HWM and remain
incomplete under the existing failure rules.

```bash
PYTHONPATH=src python -m inodefence.evaluation.policy_repeated \
  <repetition-root> --plan-sha256 <trusted-plan-sha256> \
  --require-controller-memory
```

## Perturbation and interpretation limits

There is no polling thread, sampling loop or target instrumentation. Two small procfs reads
and final record serialization add controller work; the final HWM can include the first read
and all pre-existing process-lifetime allocations. Measurement record serialization happens
after the final HWM sample and is not included. These limits must accompany reported pilot
values.

The profile is Linux-only and fails closed when procfs fields/units are missing, process
identity changes or publication fails. It does not measure aggregate host memory, Docker
daemon memory, target-container RSS, allocator ownership, swap, cgroup pressure or
instantaneous combined controller-plus-target memory. No value exists until an authorized
campaign actually runs.
