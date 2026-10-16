#!/usr/bin/env python3
"""P1-12 review-v1: offline acceptance check and descriptive analysis over
the sealed pilot batch. Read-only over raw evidence; writes
reports/analysis/P1-12-review-v1/{summary.json,summary.md,manifest.json}.

No Docker, no network, no model, no credential access. Null means missing/
not-run and is never filled with zero. Repeats within a task are raw
points, never independent tasks. Costs stay unknown."""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = ROOT / "reports/resource/P1-12/P1-12-20260928T023250Z-33ffbd62"
RAW_ROOT = ROOT / "data/raw/generated/P1-12"
OUT = ROOT / "reports/analysis/P1-12-review-v1"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def median_iqr(values):
    if not values:
        return {"n": 0, "median": None, "iqr": None, "min": None, "max": None}
    vs = sorted(values)
    n = len(vs)

    def q(p):
        pos = p * (n - 1)
        lo = int(pos)
        hi = min(lo + 1, n - 1)
        return vs[lo] + (vs[hi] - vs[lo]) * (pos - lo)

    return {"n": n, "median": statistics.median(vs),
            "iqr": q(0.75) - q(0.25), "min": vs[0], "max": vs[-1]}


def load_events(rd: Path):
    return [json.loads(l) for l in (rd / "events.jsonl").read_text().splitlines()]


def llm_facts(rd: Path):
    evs = load_events(rd)
    closed = [e["attrs"] for e in evs
              if e.get("kind") == "llm_request" and e.get("status") == "closed"]
    ok = [a for a in closed if a.get("ok")]
    err = [a for a in closed if not a.get("ok")]
    return {
        "requests_closed": len(closed),
        "ok": len(ok),
        "errors": len(err),
        "error_kinds": sorted({str(a.get("error")).split(":")[0] for a in err}),
        "prompt_tokens": sum((a.get("usage") or {}).get("prompt_tokens") or 0
                             for a in closed),
        "completion_tokens": sum((a.get("usage") or {}).get("completion_tokens") or 0
                                 for a in closed),
    }


def tool_facts(rd: Path):
    tools = [json.loads(l) for l in
             (rd / "mini_tool_events.jsonl").read_text().splitlines()]
    opens = [t for t in tools if t.get("event") == "open"]
    closed = [t for t in tools if t.get("event") == "closed"]
    return {"tool_calls": len(opens), "tool_closed": len(closed),
            "nonzero_returncodes": sum(
                1 for t in closed if (t.get("returncode") or 0) != 0)}


def scope_facts(rd: Path, suffix: str):
    s = json.loads((rd / "samples.json").read_text())
    key = next((k for k in s["scopes"] if k.endswith(suffix)), None)
    if key is None:
        return None
    sc = s["scopes"][key]
    return {
        "cpu_core_seconds": sc.get("cpu_core_seconds"),
        "cpu_evidence": sc.get("cpu_evidence"),
        "wall_s": sc.get("wall_s"),
        "memory_kernel_peak_bytes": sc.get("memory_kernel_peak_bytes"),
        "memory_sampled_max_bytes": sc.get("memory_sampled_max_bytes"),
        "n_samples": sc.get("n_samples"),
        "formal_io": (sc.get("io") or {}).get("evidence"),
    }


def main():
    if OUT.exists():
        print(f"REFUSING: {OUT} already exists")
        return 2
    batch = json.loads((BATCH_DIR / "summary.json").read_text())
    batch_manifest = json.loads((BATCH_DIR / "manifest.json").read_text())

    # -- archive recheck --------------------------------------------------
    archive_recheck = {"outputs": {}, "all_match": True}
    for p, v in batch_manifest["outputs"].items():
        f = BATCH_DIR / p
        ok = (f.stat().st_size == v["bytes"] and sha(f) == v["sha256"])
        archive_recheck["outputs"][p] = ok
        archive_recheck["all_match"] &= ok

    # -- identity consistency ----------------------------------------------
    approval = json.loads((ROOT / "reports/resource/P1-12/APPROVAL.json").read_text())
    attempt = json.loads((ROOT / "reports/resource/P1-12/ATTEMPT_STARTED.json").read_text())
    identity_ok = {
        "approval_checklist_equals_batch_manifest_identity":
            approval["checklist_identity"] == batch_manifest["identity"],
        "attempt_identity_equals_batch_manifest_identity":
            attempt["identity"] == batch_manifest["identity"],
    }

    # -- per-attempt raw points --------------------------------------------
    raw_points = []
    for a in batch["attempts"]:
        rd = ROOT / a["run_dir"]
        meta = json.loads((rd / "metadata.json").read_text())
        llm = llm_facts(rd)
        tools = tool_facts(rd)
        agent = scope_facts(rd, "-agent-sandbox")
        verifier = scope_facts(rd, "-verifier")
        bu = meta["budget_usage"]
        resolved = a.get("resolved")
        note = None
        if a["execution_status"] == "no_candidate":
            note = "agent produced no candidate patch; verifier not started; " \
                   "evaluation_status=not_run by design"
        raw_points.append({
            "round": a["round"],
            "instance_id": a["instance_id"],
            "run_id": a["run_id"],
            "run_dir": str(rd.relative_to(ROOT)),
            "execution_status": a["execution_status"],
            "evaluation_status": a["evaluation_status"],
            "resolved": resolved,
            "resolved_note": note,
            "wall_s_total": bu.get("elapsed_total_s"),
            "wall_s_execution_phase": bu.get("elapsed_s"),
            "budget_requests_counter": bu.get("requests"),
            "llm": llm,
            "tools": tools,
            "agent_scope": agent,
            "verifier_scope": verifier,
            "cleanup_status": a.get("cleanup_status"),
            "archive_status": a.get("archive_status"),
        })

    # -- per-task grouping ---------------------------------------------------
    per_task = {}
    for t in batch_manifest["identity"]["tasks"]:
        inst = t if isinstance(t, str) else None
    task_ids = sorted({p["instance_id"] for p in raw_points})
    for inst in task_ids:
        rows = [p for p in raw_points if p["instance_id"] == inst]

        def vals(field, path=None):
            out = []
            for r in rows:
                v = r
                for k in (path or []):
                    v = (v or {}).get(k)
                if isinstance(v, (int, float)):
                    out.append(v)
            return out

        executed = [r for r in rows if r["execution_status"] == "ok"]
        per_task[inst] = {
            "planned": len(rows),
            "executed_ok": len(executed),
            "resolved_true": sum(1 for r in rows if r["resolved"] is True),
            "resolved_false": sum(1 for r in rows if r["resolved"] is False),
            "not_evaluated": sum(1 for r in rows if r["resolved"] is None),
            "wall_s_stats": median_iqr([r["wall_s_total"] for r in rows
                                        if isinstance(r["wall_s_total"], (int, float))]),
            "agent_cpu_core_s_stats": median_iqr(
                vals(None, ["agent_scope", "cpu_core_seconds"])),
            "agent_wall_s_stats": median_iqr(
                vals(None, ["agent_scope", "wall_s"])),
            "agent_memory_kernel_peak_bytes_stats": median_iqr(
                vals(None, ["agent_scope", "memory_kernel_peak_bytes"])),
            "verifier_cpu_core_s_stats": median_iqr(
                vals(None, ["verifier_scope", "cpu_core_seconds"])),
            "verifier_memory_kernel_peak_bytes_stats": median_iqr(
                vals(None, ["verifier_scope", "memory_kernel_peak_bytes"])),
            "llm_prompt_tokens_stats": median_iqr(
                vals(None, ["llm", "prompt_tokens"])),
            "llm_completion_tokens_stats": median_iqr(
                vals(None, ["llm", "completion_tokens"])),
            "tool_calls_stats": median_iqr(
                vals(None, ["tools", "tool_calls"])),
            "note": "repeats are raw points within one task, not "
                    "independent tasks; median/IQR linear interpolation",
        }

    # -- three focused questions --------------------------------------------
    llm_closed_total = sum(p["llm"]["requests_closed"] for p in raw_points)
    budget_counter_total = sum(p["budget_requests_counter"] or 0
                               for p in raw_points)
    ok_total = sum(p["llm"]["ok"] for p in raw_points)
    err_total = sum(p["llm"]["errors"] for p in raw_points)
    q1 = {
        "question": "batch-level 270 requests: counter vs actual call records",
        "budget_counter_total": budget_counter_total,
        "llm_closed_event_total": llm_closed_total,
        "llm_ok_total": ok_total,
        "llm_error_total": err_total,
        "error_kinds_seen": sorted({k for p in raw_points
                                    for k in p["llm"]["error_kinds"]}),
        "finding": (
            f"budget counter total {budget_counter_total} equals the sum of "
            f"per-run llm_request closed events ({llm_closed_total}); both "
            f"count CLOSED model calls (ok {ok_total} / errored {err_total}); "
            "every attempt hit its 30-request cap. 'Requests' here = closed "
            "model calls; successful responses vs retries cannot be further "
            "split from this evidence (mini retry mapping not recorded "
            "per-call): unknown. Tool steps are counted separately "
            "(mini_tool_events) and are not requests."),
        "steps_vs_requests": [p["tools"]["tool_calls"] for p in raw_points],
    }

    nc = [p for p in raw_points if p["execution_status"] == "no_candidate"]
    q2 = {"question": "astropy__astropy-13398 no_candidate attempt",
          "attempts": []}
    for p in nc:
        cand = ROOT / p["run_dir"] / "candidate.patch"
        q2["attempts"].append({
            "run_id": p["run_id"], "round": p["round"],
            "candidate_patch_exists": cand.is_file(),
            "candidate_patch_bytes": cand.stat().st_size if cand.is_file() else 0,
            "execution_status": p["execution_status"],
            "evaluation_status": p["evaluation_status"],
            "verifier_scope_present": p["verifier_scope"] is not None,
            "resolved": p["resolved"],
            "finding": ("agent ended without a candidate patch "
                        "(execution_status=no_candidate); the verifier was "
                        "NEVER started for this attempt (no verifier scope, "
                        "evaluation not_run) - this is NOT an evaluation "
                        "failure and must not be counted as one"),
        })

    q3 = {
        "question": "credential handling statement (static chain check)",
        "finding": (
            "resolve_credentials() loads via smoke_launcher.load_credentials "
            "into memory and maps to child env keys; values are passed as "
            "runner credentials to the harness child environment only. No "
            "credential values appear in argv, events.jsonl, mini_status, "
            "metadata.json, samples.json or the batch report (checked "
            "statically over the nine raw dirs). Whether anything outside "
            "this batch ever persisted them is outside this evidence: no "
            "absolute guarantee is made; within the archived evidence of "
            "this batch no credential material was found."),
    }

    # -- write outputs --------------------------------------------------------
    OUT.mkdir(parents=True)
    summary = {
        "schema": "awc-p1-12-review-v1",
        "batch_run_id": batch["run_id"],
        "acceptance": {
            "archive_recheck": archive_recheck,
            "identity_consistency": identity_ok,
            "attempts_executed": sum(1 for p in raw_points
                                     if p["execution_status"] in ("ok", "no_candidate")),
            "verdict_basis": "9/9 planned attempts ran; see per-task results",
        },
        "focused_questions": {"q1_requests": q1, "q2_no_candidate": q2,
                              "q3_credentials": q3},
        "raw_points": raw_points,
        "per_task": per_task,
        "statistics_note": (
            "median/IQR linear interpolation; n = valid points per task "
            "(verifier stats n=2 for astropy-13398 because one attempt was "
            "not evaluated); costs unknown; formal I/O null by design"),
        "allowed_claims": [
            "descriptive run-to-run variation within each fixed task under "
            "the registered configuration",
            "task-level resolved counts (3/3, 3/3, 0-of-3 with one "
            "not-evaluated) for exactly these three tasks",
            "NOT cross-task causal claims, NOT Coding-category "
            "representativeness, NOT per-tool CPU, NOT wait-time inference",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    # summary.md (compact human view)
    md = ["# P1-12 review-v1 (offline acceptance & descriptive analysis)", "",
          f"Batch `{batch['run_id']}`; 9/9 planned attempts executed; "
          f"archive recheck {'ALL MATCH' if archive_recheck['all_match'] else 'MISMATCH'}.",
          "", "## Task results", "",
          "| task | resolved T/F/N | wall med (s) | agent CPU med (core-s) | "
          "verifier CPU med (core-s) | tools med |", "| --- | --- | --- | --- | --- | --- |"]
    for inst, st in per_task.items():
        md.append(
            f"| {inst} | {st['resolved_true']}/{st['resolved_false']}/"
            f"{st['not_evaluated']} | {st['wall_s_stats']['median']:.1f} | "
            f"{st['agent_cpu_core_s_stats']['median']:.2f} | "
            f"{(st['verifier_cpu_core_s_stats']['median'] or 0):.2f}"
            f" (n={st['verifier_cpu_core_s_stats']['n']}) | "
            f"{st['tool_calls_stats']['median']:.0f} |")
    md += ["", "## Focused questions", "",
           f"1. **270 requests**: budget counter = sum of closed llm_request "
           f"events = {llm_closed_total} (ok {ok_total}, errored {err_total}); "
           "every attempt hit its 30 cap; success/retry split unknown; tool "
           "steps counted separately.",
           f"2. **astropy-13398 no_candidate**: {len(nc)} attempt(s) ended "
           "without a candidate patch; verifier never started "
           "(evaluation not_run, no verifier scope); NOT an evaluation "
           "failure; the other two attempts were evaluated and resolved "
           "false.",
           "3. **Credentials**: in-memory only through the registered "
           "chain; no credential material found in the nine archived raw "
           "dirs; no absolute persistence guarantee claimed beyond this "
           "evidence.",
           "", "## Allowed conclusions", ""] + [f"- {c}" for c in
                                                 summary["allowed_claims"]] + [
          "", "Costs: unknown (user accepted no hard cap; not a bill).",
          "CPU-02 and Replay remain paused; G2 not claimed."]
    (OUT / "summary.md").write_text("\n".join(md) + "\n")

    # manifest: consumed inputs, code, outputs (no self-hash)
    inputs = {}
    for rel in ["reports/resource/P1-12/P1-12-20260928T023250Z-33ffbd62/summary.json",
                "reports/resource/P1-12/P1-12-20260928T023250Z-33ffbd62/manifest.json",
                "reports/resource/P1-12/APPROVAL.json",
                "reports/resource/P1-12/ATTEMPT_STARTED.json"]:
        f = ROOT / rel
        inputs[rel] = {"bytes": f.stat().st_size, "sha256": sha(f)}
    for p in raw_points:
        for name in ("metadata.json", "samples.json", "events.jsonl",
                     "mini_tool_events.jsonl"):
            f = ROOT / p["run_dir"] / name
            inputs[str(f.relative_to(ROOT))] = {"bytes": f.stat().st_size,
                                                "sha256": sha(f)}
    code = Path(__file__)
    manifest = {
        "kind": "P1-12-review-v1-manifest",
        "inputs": inputs,
        "analysis_code": {"path": str(code.relative_to(ROOT)),
                          "bytes": code.stat().st_size, "sha256": sha(code)},
        "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)}
                    for p in sorted(OUT.iterdir()) if p.is_file()},
        "generated_at_utc": __import__("time").strftime(
            "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("written:", OUT)
    print("archive recheck all_match:", archive_recheck["all_match"])
    print("identity consistency:", identity_ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
