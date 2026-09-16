# External sandbox boundary

Cleanroom owns decisions, permissions for its host tools, actual receipts,
provenance, configuration hashes and local learning records. External OSS launchers
own OS/process/VM isolation, mounts, network policy, secrets and resource enforcement.
SandboxBackend is an interface at the external Work proposal process boundary,
not a new sandbox engine.

## Configure

~~~sh
verantyx setup harness
verantyx setup sandbox
verantyx setup sandbox --show --json
~~~

F2 also exposes Sandbox backend. Reading or saving settings starts no process.
A trusted JSON configuration provides an absolute executable and argv_prefix.
The prefix expands {project}, {candidate_root}/{workspace_root} for .verantyx/workspaces,
and {candidate_store} for immutable .verantyx/work-candidates versions, then the external
Work harness argv is appended. No shell string is evaluated.
See [the contract example](SANDBOX_BACKENDS.ja.md#接続の入口).

The example is not a certified Docker, Podman, Bubblewrap or VM command.
Implement a launcher that maps the contract to the chosen engine and supported OS.
The source mount must actually be read-only except for explicitly allowed candidate
storage. requested_policy records intent; it does not implement the policy.

## Report the observed boundary

For a known host-only run, Cleanroom says host writes were limited to candidates.
For external harnesses, generic command model adapters and unobserved historical
runs, source_project_changed is null and the status is UNKNOWN_EXTERNAL_EFFECTS.
This means neither "changed" nor "unchanged": a whole-project audit was not made.

A configured launcher remains REQUESTED_NOT_ATTESTED, with isolation_verified=false.
A launch failure never falls back to unsandboxed execution.
An enabled external sandbox with the built-in harness is refused rather than
silently ignored. Native operations inside the external process are not converted
to verified host receipts.

## Scope and limitations

The connector covers only the external Work JSON process. It does not cover model
API calls, Reflection, search adapters or Cleanroom's host tools. The launcher must
handle environment secrets, HOME, sockets, mounts and networking itself.
Configuration hashing does not pin executable binaries or dependencies.

[Bubblewrap's own README](https://github.com/containers/bubblewrap) explains that
the security policy depends on the arguments used. An installed engine is not
evidence of correct isolation. Linux-specific tools are not assumed to work
directly on macOS. Engine-specific adapters and isolation attestation remain
separate implementation work.
