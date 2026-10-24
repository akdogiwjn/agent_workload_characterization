# Official CLI contract comparison

Compared against `references/repos/FireRed-OpenStoryline/cli.py` at
`c9e945215586f45c12a61c1951ee9a8e9c43a027` (reference worktree unchanged).

| Contract | Official CLI | Repaired task entry |
| --- | --- | --- |
| Agent creation | `build_agent(cfg, session_id, ArtifactStore(cfg.project.outputs_dir), tool_interceptors=[inject_media_content_before, save_media_content_after, inject_tts_config])` | Same native `build_agent`; all three interceptors are passed. The client `save_media_content_after` interceptor remains the single persistence owner. |
| Runtime context | `ClientContext` with config, session, media/BGM/output directories, `NodeManager`, model key | Same context fields; one session ID is used by context, MCP header, ArtifactStore and history. |
| Initial messages | Instruction `SystemMessage` and media statistics `SystemMessage`, then user request | Same instruction and upload/media overview, then requested task. No scoring/golden context is added. |
| Tool identity | Interceptor metadata maps public tools to registered nodes | Exact public-name map; no arbitrary prefix stripping. Unmapped names fail clearly. |
| Artifact/history | Official after-interceptor saves node outputs into the session store | Same save mechanism; returned artifact IDs are checked against the persisted record. Server history reads the configured output root and header session. |
| Local media | Official interceptor prepares media inputs | Shared-container path-only mode supplies absolute paths; server reconstructs internal `inputs` that are excluded from public MCP schema. |
| Render submission | CLI has no fixed submission export | Host wrapper resolves the current session's actual RenderVideo artifact, maps `/workspace/output` to the mounted host directory, validates it, then copies exact bytes to `output.mp4`; `cuts.json` comes from final timeline source intervals. |
| Request tracing | No per-request budget ledger in CLI | Separate pre-send logical-request gate, per-request output cap, post-response observed-usage soft threshold, and request/tool association records. MCP sampling is excluded from inherited Agent callbacks to prevent duplicate ledger rows. |

Offline production-entry evidence: [`validation-03/validation-report.json`](validation-03/validation-report.json).
It passed with a container-loopback fake model and real MCP/local nodes. This does not pass the separate real-model/API gate.
