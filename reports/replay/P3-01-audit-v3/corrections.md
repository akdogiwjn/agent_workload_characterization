# Corrections to P3-01 audit-v1/v2

1. The prior claim that commands were not recoverable was too strong. v2 parses `function.arguments.command` and independently verifies every command hash and length against the hook projection.
2. The v1 call-14 hash was manually incomplete. v2 generates it from source data and records the full digest; the source hash is not hand-entered.
3. `metadata.json` does not establish image identity. v3 links the R2 marker, catalog and registered code/config identity: image, planned cwd and interpreters are derived context, while actual runtime observation remains unknown.
4. Field coverage is per call: recorded, derived, missing or unknown, including output presence/truncation, cwd, stdin, environment, initial state, dependencies and correctness.
5. v3 makes orphan hook events, duplicate events and global trajectory/event order part of the association validity gate.
6. These corrections do not convert a shell command string into safe structured argv or authorize replay.
