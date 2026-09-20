# P3-01 audit-v2

Read-only audit of `fixture`; no recorded command was executed.

- trajectory calls: 1
- hook events: 2
- paired hook calls: 1
- all trajectory command hashes match hook projections: `True`

The shell command string and its SHA-256/length are recorded, but this is not structured argv and is not an execution authorization. Per-call cwd/stdin, actual child environment, initial file state, dependency graph, remote dependency and semantic output correctness remain explicitly classified in `inventory.json`. Output content presence is recorded where available; truncation is unknown because no truncation marker is recorded.

The trace supports a bounded local description of tool-call identity, ordering, pairing, command hashes, durations and return codes. It does not yet support safe or faithful replay. CPU-02 remains paused; P3-02 and G3-R are not authorized or passed.
