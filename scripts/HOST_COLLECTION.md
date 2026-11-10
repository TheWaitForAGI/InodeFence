# HOST 1 / HOST 2 evidence collection

These commands collect read-only observations. A matching checksum detects changes after
collection; it does **not** authenticate the machine or prove that the results remain current.
Keep host files private until reviewed: Windows paths and process names can identify users.
No command below starts an experiment or modifies Windows configuration.

In WSL, from an existing repository (replace paths to suit the host):

```bash
git fetch origin
mkdir -p ~/inodefence-host-work
git worktree add --detach ~/inodefence-host-work/tools origin/codex/host-freeze-validation-20261109
git worktree add --detach ~/inodefence-host-work/execution afdc720da6eb6ae143bd4754cb39d6dd34ea8f16
cd ~/inodefence-host-work/execution
git status --short
git rev-parse HEAD
python3 ~/inodefence-host-work/tools/scripts/collect_host_evidence.py \
  --host-id HOST2 --output ~/inodefence-host2-evidence-001 \
  --output-path ~/inodefence-benchmarks/host2-new-output
```

Use a new output directory each time. The collector runs the included PowerShell probe from
WSL and records stdout, stderr, argv, exit status, timeout and SHA-256 per command. It queries
Windows power and update settings, WSL, Docker, images, resources, process names and free
space. `collection.json` includes the declared future output path; a declaration is not a
measurement. The collector's tool checkout and the execution checkout are distinct: the
recorded Git HEAD refers to the working directory, not the tool source. Review Windows and
Docker raw outputs and verify the tool checkout SHA independently. A timed-out, missing, or
inaccessible measurement remains UNKNOWN. The filesystem test uses the nearest existing
parent of the proposed output directory.

Retain the printed collection hash in a separate trusted channel. To inspect and check:

```bash
cd ~/inodefence-host2-evidence-001
sha256sum collection.json
cat windows.stdout
cat docker_vm.stdout
cd ~/inodefence-host-work/tools
python3 -m scripts.verify_host_collection \
  --input ~/inodefence-host2-evidence-001 --collection-sha256 <printed-sha256> \
  --expected-sha afdc720da6eb6ae143bd4754cb39d6dd34ea8f16 \
  --image-id sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb \
  --jobs 2 --min-memory-bytes 16106127360 --min-disk-bytes 20000000000
```

The minimums and jobs shown are the proposed smoke thresholds, not an approved HOST 2
qualification. The verifier deliberately reports qualification and freeze eligibility UNKNOWN:
VHDX identity, restart protection, runtime cgroup limits and authenticity need independent
verification. The input is not a signed attestation. Failed commands are UNKNOWN. Do not put
unreviewed machine-specific evidence, personal information or experiment raw data in the repo.

To share, create a separate private branch in the teammate's own evidence repository, after
reviewing its access and contents. For example, inside that repository:

```bash
git switch -c host2/evidence-001
mkdir -p host2/evidence-001
cp -a ~/inodefence-host2-evidence-001/. host2/evidence-001/
git add host2/evidence-001
git commit -m 'Record HOST2 inventory evidence'
git push -u origin host2/evidence-001
```

On HOST 1, retrieve that private branch through the approved channel, obtain the collection
hash independently from its author, and run the same `verify_host_collection` command with
`--input` pointing to the received directory and `--collection-sha256` to that hash. This
cannot replace a separately approved execution plan, HOST 2 runtime qualification, complete
preregistered assignment, or the halted H1 decision. Never send raw oracle fields.
