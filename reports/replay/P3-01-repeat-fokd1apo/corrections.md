# Corrections to P3-01 audit-v1

1. The prior claim that commands were not recoverable was too strong. v2 parses `function.arguments.command` and independently verifies every command hash and length against the hook projection.
2. The v1 call-14 hash was manually incomplete. v2 generates it from source data and records the full digest; the source hash is not hand-entered.
3. `metadata.json` does not establish an image identity. Model/harness fields are separated: model is derived from trajectory config, harness version from trajectory info, and image remains missing.
4. Field coverage is now per call: recorded, derived, missing or unknown, including output presence/truncation, cwd, stdin, environment, initial state, dependencies and correctness.
5. This correction does not convert a shell command string into safe structured argv or authorize replay.
