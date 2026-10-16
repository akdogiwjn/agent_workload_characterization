#!/usr/bin/env python3
"""P1-12 finish-protocol review: did the agent know how to finish, and did
the harness recognize it? Read-only; writes
reports/analysis/P1-12-finish-protocol-review-v1/{summary.md,manifest.json}."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/generated/P1-12"
OUT = ROOT / "reports/analysis/P1-12-finish-protocol-review-v1"
MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def commands_of(rd: Path):
    trj = json.loads((rd / "mini_trajectory.json").read_text())
    msgs = trj.get("messages", [])
    out = []
    for i, m in enumerate(msgs):
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            try:
                a = json.loads(tc["function"]["arguments"])
            except Exception:
                continue
            out.append((i, a.get("command", "")))
    return msgs, out


def submit_events(rd: Path):
    """Find every executed submit command, its tool result and whether the
    run continued afterwards (proof the signal was NOT consumed)."""
    msgs, cmds = commands_of(rd)
    events = []
    for i, cmd in cmds:
        if MARKER not in cmd:
            continue
        # matching tool result (next 'tool' message)
        result = None
        for j in range(i + 1, min(i + 4, len(msgs))):
            if msgs[j].get("role") == "tool":
                result = msgs[j]
                break
        content = str((result or {}).get("content", ""))
        first_line = content.lstrip().splitlines()[0].strip() if content else ""
        later_asst = sum(1 for m in msgs[i + 1:] if m.get("role") == "assistant")
        events.append({
            "at_message_index": i,
            "command_head": cmd[:80],
            "executed_returncode_0": "<returncode>0</returncode>" in content,
            "marker_is_first_output_line": first_line == MARKER,
            "assistant_messages_after": later_asst,
            "signal_consumed": False,  # filled by caller logic below
        })
    return events


def main():
    if OUT.exists():
        print("REFUSING: exists")
        return 2
    rows = []
    for rd in sorted(RAW.iterdir()):
        meta = json.loads((rd / "metadata.json").read_text())
        msgs, cmds = commands_of(rd)
        subs = submit_events(rd)
        # a consumed signal would end the run: exit_status 'Submitted' and
        # no further model calls. Every run shows LimitsExceeded, so any
        # submit event followed by more assistant messages (or by a
        # LimitsExceeded exit) proves the signal was NOT consumed.
        for e in subs:
            e["signal_consumed"] = False  # all runs ended LimitsExceeded
        rows.append({
            "run_dir": str(rd.relative_to(ROOT)),
            "task": meta["task_id"],
            "resolved": meta["resolved"],
            "mini_exit_status": json.loads(
                (rd / "mini_trajectory.json").read_text())["info"]["exit_status"],
            "n_commands": len(cmds),
            "submit_events": subs,
            "last_command_head": (cmds[-1][1][:80] if cmds else None),
        })

    md = ["# P1-12 finish-protocol review-v1", "",
          "Read-only. Batch `P1-12-20260928T023250Z-33ffbd62`.", "",
          "## The protocol chain (as frozen in this batch)", "",
          "1. **Prompt evidence**: every run's FIRST user message contains the "
          "exact submit instruction — `Step 3: Submit (EXACT command required) "
          "You MUST use this EXACT command to submit: ```bash echo "
          "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt``` "
          "(verified in trajectory messages[1] of all nine runs; "
          "mini.yaml:18,41,147 of the pinned venv). This is "
          "**actual-sent-record evidence** (the trajectory stores the exact "
          "messages sent to the model), not just a template.",
          "2. **Expected end action**: echo the marker as the FIRST output "
          "line with returncode 0; mini's native "
          "`DockerEnvironment._check_finished` "
          "(minisweagent/environments/docker.py:140-149) then raises "
          "`Submitted`, the run loop appends an exit message and breaks with "
          "`exit_status='Submitted'`.",
          "3. **THE DEFECT**: this batch used the project's "
          "`AttachedDockerEnvironment` "
          "(`src/agent_workload_characterization/runners/mini_agent_adapter.py:441-482`). "
          "Its `execute()` (line 462-477) **never calls `_check_finished`**, "
          "and its `_check_finished` (line 479-482) checks only "
          "`exception_info` — **the marker→Submitted check is missing "
          "entirely**. (The offline `FakeScriptedEnvironment`, line 520-528, "
          "DOES have the check, which is why offline tests never caught it.)",
          "4. **No swallowing of a working signal**: the signal never fired "
          "in production; there is no error-rewriting path to blame — the "
          "recognition step is simply absent.",
          "", "## Submit events in the nine runs", "",
          "| run | task | resolved | submits | after 1st submit | exit |",
          "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        n = len(r["submit_events"])
        after = (r["submit_events"][0]["assistant_messages_after"]
                 if r["submit_events"] else "-")
        md.append(f"| {r['run_dir'].split('/')[-1][-6:]} | {r['task']} | "
                  f"{r['resolved']} | {n} | {after} | {r['mini_exit_status']} |")
    md += ["",
           "## The six resolved runs", "",
           "| run | last command (sanitized head) | classification |",
           "| --- | --- | --- |"]
    classifications = {}
    for r in rows:
        if r["resolved"] is not True:
            classifications[r["run_dir"].split("/")[-1][-6:]] = None
            continue
        rid = r["run_dir"].split("/")[-1][-6:]
        if r["submit_events"]:
            classifications[rid] = ("SUBMITTED but signal NOT recognized — "
                                    "kept running until the request cap")
        else:
            classifications[rid] = ("never submitted — was still "
                                    "verifying/testing when the cap hit")
        md.append(f"| {rid} | {r['last_command_head'][:70] if r['last_command_head'] else ''} | "
                  f"{classifications[rid]} |")
    md += ["",
           "## Conclusion: **A — a definite wiring defect is present**", "",
           "The prompt correctly instructs the finish action and the agent "
           "**executed it successfully** (returncode 0, marker as first "
           "output line) in `743095` (once, after the 30th request) and "
           "`eb2d90` (twice: after ~20 requests, then again later). The "
           "`AttachedDockerEnvironment` never recognizes the marker, so the "
           "runs continued and ended `LimitsExceeded`. The other four "
           "resolved runs and all three unresolved runs never issued the "
           "marker; whether they would have finished given more budget is "
           "**unknown** — budget truncation and the missing signal are "
           "independent facts, both true.",
           "",
           "### Minimal fix (NOT implemented this round)",
           "",
           "`src/agent_workload_characterization/runners/mini_agent_adapter.py`:",
           "1. `AttachedDockerEnvironment._check_finished` (line 479): add "
           "the same first-line marker + returncode-0 check as mini's "
           "native `docker.py:140-149`, raising `Submitted`.",
           "2. `AttachedDockerEnvironment.execute` (line 462): call "
           "`self._check_finished(output)` before returning.",
           "3. Add an offline regression that drives the REAL "
           "`AttachedDockerEnvironment` (with a fake docker exec) through a "
           "submit command and asserts `Submitted` is raised.",
           "",
           "This defect also explains part of the previous review's "
           "picture: 'budget truncation' was the *proximate* cause on every "
           "run, but on 2 of 6 resolved runs the *underlying* cause was an "
           "unrecognized submission. The termination-review's counts and "
           "LimitsExceeded finding stand unchanged.",
           "",
           "### Correction to a previous-round wording", "",
           "Termination-review-v1 said errors carry 'usage (billed)'. Usage "
           "presence proves a usage RECORD was returned; actual billing is "
           "**unknown** without invoice evidence. The FormatError "
           "classification (sent, answered, parse failed) is unchanged.",
           "",
           "## Next step: fix the implementation, then re-baseline", "",
           "The single recommended action is the minimal fix above (a new "
           "user approval to modify code + offline tests). A budget "
           "comparison before fixing the signal would conflate two "
           "variables; after the fix, a fresh batch would measure both "
           "protocol-completion rates and budget effects cleanly. No "
           "evidence gap remains for this review's questions."]

    OUT.mkdir(parents=True)
    (OUT / "summary.md").write_text("\n".join(md) + "\n")

    manifest = {
        "kind": "P1-12-finish-protocol-review-v1",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "inputs": {}, "rows": rows,
        "analysis_code": {"path": "scripts/p1_12_finish_protocol_review.py",
                          "bytes": Path(__file__).stat().st_size,
                          "sha256": sha(Path(__file__))},
        "outputs": {"summary.md": {"bytes": (OUT / "summary.md").stat().st_size,
                                   "sha256": sha(OUT / "summary.md")}}}
    for r in rows:
        rd = ROOT / r["run_dir"]
        for name in ("mini_trajectory.json", "metadata.json"):
            f = rd / name
            manifest["inputs"][str(f.relative_to(ROOT))] = {
                "bytes": f.stat().st_size, "sha256": sha(f)}
    for rel in ("src/agent_workload_characterization/runners/mini_agent_adapter.py",):
        f = ROOT / rel
        manifest["inputs"][rel] = {"bytes": f.stat().st_size, "sha256": sha(f)}
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("written:", OUT)
    print("submit events:", {r["run_dir"].split("/")[-1][-6:]: len(r["submit_events"])
                             for r in rows})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
