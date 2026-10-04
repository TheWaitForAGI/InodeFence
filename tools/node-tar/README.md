# node-tar adapter validation dependency

Node 22.22.0 and npm-lockfile `tar` 7.5.22 are the benign integration baseline.
The package lock records transitive versions/integrities. Install in supported Linux:

```bash
make target-tools
make check
```

Dev Container post-create and CI install this dependency using `npm ci --ignore-scripts`.
Node is pinned in both environment definitions; an existing container may need rebuilding.
Python distribution includes the CJS worker, while this external dependency root remains
an explicit `NodeTarTarget(package_root=...)` argument. No dependency installation occurs
inside an extraction observation window. node_modules is ignored.

This is adapter engineering with ordinary controlled fixtures. `NodeTarTarget` always
declares ISOLATION_REQUIRED; generated-input campaigns remain rejected. Process-group
cleanup is not an OS sandbox. No benchmark security evaluation or vulnerable-version
selection is provided. API/options follow [upstream node-tar](https://github.com/isaacs/node-tar).
