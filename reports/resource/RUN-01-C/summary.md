# RUN-01 resource summary

batch: RUN-01-C
generated: 2026-09-12T12:57:22.122850+00:00
source_type: benchmark_real

## Scopes

- 20260912T125202Z-840e49-agent-sandbox (agent_container): cpu=6.411718 core-s (reason=None), wall=134.099304929s, mem_peak_basis=v1_max_usage_in_bytes
- 20260912T125202Z-840e49-verifier (verifier_container): cpu=3.423041 core-s (reason=None), wall=11.990780406s, mem_peak_basis=v1_max_usage_in_bytes

## Limitations

- scope peaks are NOT additive: no run-level peak memory exists
- avg cores = cpu/wall within a scope; not an efficiency metric
- parent/child scope overlap means scope CPUs must not be summed into a total without an explicit mutual-exclusion proof
- page cache makes block I/O differ from application bytes; io.read_bytes is the interval delta, not the cumulative value
- sample count is not accuracy evidence; boundary counters carry the CPU evidence for short bursts
- tool-level semantic events are emitted by the fake harness flow only; the real mini harness records tool activity in the mini trajectory, so tool counts here may be 0 for real runs
- host_agent_runtime scope (the host-side mini child) has no per-process CPU/RSS instrumentation; its wall/request boundaries come from the status protocol
