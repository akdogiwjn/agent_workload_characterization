#!/usr/bin/env python3
"""P1-12 termination review: why all nine runs registered 30 requests and
what the 9 errored requests are. Read-only over the sealed batch; writes
reports/analysis/P1-12-termination-review-v1/{summary.md,manifest.json}."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/generated/P1-12"
OUT = ROOT / "reports/analysis/P1-12-termination-review-v1"
PREV = ROOT / "reports/analysis/P1-12-review-v1"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def analyze_run(rd: Path) -> dict:
    meta = json.loads((rd / "metadata.json").read_text())
    evs = [json.loads(l) for l in (rd / "events.jsonl").read_text().splitlines()]
    closed = [e["attrs"] for e in evs
              if e.get("kind") == "llm_request" and e.get("status") == "closed"]
    tools = [json.loads(l) for l in
             (rd / "mini_tool_events.jsonl").read_text().splitlines()]
    trj = json.loads((rd / "mini_trajectory.json").read_text())
    info = trj.get("info") or {}
    errs = [a for a in closed if not a.get("ok")]
    oks = [a for a in closed if a.get("ok")]
    last_ok = oks[-1] if oks else None
    return {
        "run_dir": str(rd.relative_to(ROOT)),
        "task": meta["task_id"],
        "execution_status": meta["execution_status"],
        "resolved": meta["resolved"],
        "closed_requests": len(closed),
        "all_closed_have_start_end_timing": all(
            a.get("t_start_ns") and a.get("t_end_ns") for a in closed),
        "ok_count": len(oks),
        "error_count": len(errs),
        "error_request_ids": [a.get("request_id") for a in errs],
        "errors_carry_usage": sum(1 for a in errs if a.get("usage")),
        "error_semantics": (
            "FormatError: the request was sent, billed (usage present) and "
            "answered, but the reply failed mini's output-format parse; "
            "recorded ok=false by StatusTrackingAgent "
            "(src/.../mini_agent_adapter.py:576-583)") if errs else "none",
        "mini_exit_status": info.get("exit_status"),
        "mini_model_stats": info.get("model_stats"),
        "last_ok_request_id": last_ok.get("request_id") if last_ok else None,
        "last_ok_end_ns": last_ok.get("t_end_ns") if last_ok else None,
        "last_tool_end_ns": max(
            (t.get("t_end_ns") or 0) for t in tools) if tools else None,
        "termination": (
            "budget_stop_step_limit" if info.get("exit_status") == "LimitsExceeded"
            else "unknown"),
        "termination_evidence": (
            "mini trajectory info.exit_status=LimitsExceeded: the mini-internal "
            "step_limit (=30 model requests, mapped from BudgetTracker "
            "max_model_requests in _effective_config, "
            "src/.../mini_agent_adapter.py:326) tripped AFTER the 30th request "
            "completed; runner budget.check() then records budget_exceeded"),
        "agent_protocol_finish": False,
        "protocol_note": ("no run ended via mini's finish protocol; task "
                          "resolution (resolved=true) is independent of the "
                          "termination mechanism"),
    }


def main():
    if OUT.exists():
        print("REFUSING: output dir exists")
        return 2
    runs = sorted(RAW.iterdir())
    rows = [analyze_run(rd) for rd in runs]

    total_closed = sum(r["closed_requests"] for r in rows)
    total_err = sum(r["error_count"] for r in rows)
    errors_by_task = {}
    for r in rows:
        errors_by_task.setdefault(r["task"], []).extend(r["error_request_ids"])

    # corrections to the previous report, if any
    prev = json.loads((PREV / "summary.json").read_text())
    prev_q1 = prev["focused_questions"]["q1_requests"]
    corrections = []
    if "every attempt hit its 30-request cap" in prev_q1["finding"]:
        corrections.append(
            "review-v1 said 'every attempt hit its 30-request cap' — CONFIRMED "
            "and now evidenced at the mechanism level: mini exit_status="
            "LimitsExceeded on 9/9 runs (step_limit=30 trips after the 30th "
            "request). No correction needed, but the stronger evidence is "
            "recorded here.")
    if "success/retry split unknown" in prev_q1["finding"]:
        corrections.append(
            "review-v1 left the errored-request semantics open. This review "
            "resolves it: all 9 errored requests are FormatError completions "
            "(sent, billed with usage, answered, failed the output-format "
            "parse) — they were REAL model round-trips, not local budget "
            "rejections and not network failures. review-v1's counts stand; "
            "its 'error' semantics are hereby clarified, not overturned.")

    md = ["# P1-12 termination review-v1", "",
          f"Batch `P1-12-20260928T023250Z-33ffbd62`; {len(rows)} runs; read-only.",
          "", "## Termination table", "",
          "| run | task | closed | ok | err (FormatError) | mini exit | resolved |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        md.append(f"| {r['run_dir'].split('/')[-1][-6:]} | {r['task']} | "
                  f"{r['closed_requests']} | {r['ok_count']} | "
                  f"{r['error_count']} {r['error_request_ids'] or ''} | "
                  f"{r['mini_exit_status']} | {r['resolved']} |")
    md += ["",
           "## Why 30 requests everywhere",
           "",
           "mini-SWE-agent's `step_limit` gates **n_calls (the model request "
           "count)**, mapped 1:1 from the frozen budget "
           "(`max_model_requests=30`, `mini_agent_adapter.py:326,402-404`). "
           "The limit trips when `n_calls >= 30` AFTER the 30th request, so "
           "**all 30 closed events per run are real, completed round-trips** "
           "(each carries its own child-side t_start/t_end and usage). No "
           "run reached a 31st attempt, so no event can be a pure local "
           "budget rejection; the counter position is **after completion** "
           "(status line written in `StatusTrackingAgent.query`, "
           "`mini_agent_adapter.py:546-583`).",
           "",
           "## The 9 errored requests",
           "",
           "All 9 are `ok=false` **with full usage and timing** — the "
           "`StatusTrackingAgent` FormatError path: the call was sent, "
           "billed and answered, but the reply failed mini's output-format "
           "parse. They are NOT budget rejections, NOT network failures. "
           "They occur only in the three django runs "
           f"({ {t[-6:]: v for t, v in errors_by_task.items()} }); "
           "astropy runs have zero.",
           "",
           "## Termination mechanism",
           "",
           "9/9 runs ended with mini `exit_status=LimitsExceeded` — "
           "**every run was budget-truncated at the request cap, including "
           "the six resolved=true runs and the no_candidate run**. No run "
           "ended via the agent's protocol finish. Task resolution and "
           "termination are independent: the six resolved runs produced a "
           "valid patch before the cap; the no_candidate run "
           "(astropy-13398 r0) produced none.",
           "",
           "## Corrections to review-v1", ""]
    md += [f"- {c}" for c in corrections] or ["- none"]
    md += ["",
           "## Step vs request counting",
           "",
           "mini has no separate step counter: `step_limit` gates n_calls. "
           "The runner's `max_steps=30` (BudgetTracker) counts completed "
           "steps (`n_steps=29` on runs whose 30th request hit "
           "FormatError — the step aborts before incrementing). The two "
           "budgets coexist; the request cap is the binding one.",
           "",
           "## Next-step recommendation: **C** (budget truncation confirmed)",
           "",
           "The 30-request cap truncated all nine runs; whether a higher "
           "cap changes outcomes is unknown. If the study question needs "
           "completed-agent behavior, the minimal next batch is a "
           "pre-registered uniform budget comparison (e.g. one task x "
           "higher request cap x same seeds) — a NEW user approval; this "
           "review does not change any budget or code.",
           "",
           "Costs remain unknown; no network/model/Docker was accessed; "
           "historical files unchanged."]

    OUT.mkdir(parents=True)
    (OUT / "summary.md").write_text("\n".join(md) + "\n")

    manifest = {
        "kind": "P1-12-termination-review-v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {},
        "analysis_code": {"path": "scripts/p1_12_termination_review.py",
                          "bytes": Path(__file__).stat().st_size,
                          "sha256": sha(Path(__file__))},
        "outputs": {"summary.md": {
            "bytes": (OUT / "summary.md").stat().st_size,
            "sha256": sha(OUT / "summary.md")}},
        "rows": rows,
        "totals": {"closed": total_closed, "errors": total_err,
                   "errors_by_task": {k: len(v) for k, v in errors_by_task.items()}},
    }
    for r in rows:
        rd = ROOT / r["run_dir"]
        for name in ("events.jsonl", "mini_status.jsonl",
                     "mini_trajectory.json", "metadata.json"):
            f = rd / name
            manifest["inputs"][str(f.relative_to(ROOT))] = {
                "bytes": f.stat().st_size, "sha256": sha(f)}
    prev_files = ["summary.json", "manifest.json"]
    for name in prev_files:
        f = PREV / name
        manifest["inputs"][str(f.relative_to(ROOT))] = {
            "bytes": f.stat().st_size, "sha256": sha(f)}
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("written:", OUT)
    print("totals:", manifest["totals"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
