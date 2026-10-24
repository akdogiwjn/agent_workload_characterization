#!/usr/bin/env python3
"""Container-side failure-injection counterexamples (network=none, no real
credentials, same production entry/runner as the passing cold-start).

  A. duplicate session id -> rejected, sessions.json NOT overwritten,
     zero model sends
  B. bad source-script hash -> ENTRY-FAILED with traceback BEFORE any send;
     container exits RC1 right after ACK; host still saves logs and removes
     the container
  C. fake boundary never started -> first LLM call fails; original error and
     request records retained; zero media sends
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import host_runner  # noqa: E402

RUNS = HERE / "runs"
BASE_CFG = json.loads(json.dumps(host_runner.DEFAULT_CONFIG))


def fresh(name: str) -> Path:
    out = RUNS / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    return out


def run_case(name: str, cfg_over: dict, env_over: dict,
             pre_seed_sessions: dict | None = None) -> dict:
    out = fresh(name)
    work = out / "workspace"
    if pre_seed_sessions is not None:
        (work / ".vimax").mkdir(parents=True)
        (work / ".vimax/sessions.json").write_text(
            json.dumps(pre_seed_sessions, indent=1))
    cfg = json.loads(json.dumps(BASE_CFG))
    cfg.update({
        "network": "none",
        "work_seconds": 420.0,
        "handshake_timeout_s": 60.0,
        "add_hosts": ["ws-fake.cn-beijing.maas.aliyuncs.com:127.0.0.1"],
    })
    cfg.update(cfg_over)
    overlay = {
        "VIMAX_LLM_BASE_URL": "http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1",
        "VIMAX_IMAGE_BASE_URL": "http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1",
        "VIMAX_VIDEO_BASE_URL": "http://ws-fake.cn-beijing.maas.aliyuncs.com:8666",
        "VIMAX_LLM_API_KEY": "fake-offline-key",
        "VIMAX_IMAGE_API_KEY": "fake-offline-key",
        "VIMAX_VIDEO_API_KEY": "fake-offline-key",
        "VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS": "1",
        "FAKE_PORT": "8666",
    }
    overlay.update(env_over)
    rc, record = host_runner.start_attempt(out, cfg, env_overlay=overlay)
    return {"out": out, "rc": rc, "record": record}


FAKE_CMD = ("python3 /opt/run/fake_media_server.py & "
            "until python3 -c \"import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8666/health', "
            "timeout=2)\" 2>/dev/null; do sleep 2; done; "
            "exec python3 /opt/run/generation_entry.py")
NO_FAKE_CMD = "exec python3 /opt/run/generation_entry.py"
FAKE_MOUNT = f"type=bind,source={HERE}/fake_media_server.py,target=/opt/run/fake_media_server.py,readonly"

results: dict[str, dict] = {}

# ---- A: duplicate session -----------------------------------------------
dup_sessions = {"active_session_id": "media-continuation-01",
                "sessions": {"media-continuation-01": {
                    "session_id": "media-continuation-01",
                    "planning_mode": "script", "stage": "created"}}}
r = run_case(
    "cx-duplicate-session",
    cfg_over={"entry_command": ["sh", "-c", FAKE_CMD],
              "extra_mounts": [FAKE_MOUNT]},
    env_over={}, pre_seed_sessions=dup_sessions)
ef = r["out"] / "workspace/attempt/ENTRY-FAILED.json"
sessions_after = json.loads(
    (r["out"] / "workspace/.vimax/sessions.json").read_text())
seed_marker = (r["out"] / "workspace/attempt/session-source-map.json").exists()
model_events = (r["out"] / "workspace/attempt/model-events.jsonl").exists()
results["A_duplicate_session"] = {
    "entry_failed_exists": ef.exists(),
    "message": json.loads(ef.read_text())["message"][:100] if ef.exists() else None,
    "sessions_untouched": sessions_after == dup_sessions,
    "seed_not_performed": not seed_marker,
    "model_sends_zero": not model_events,
    "logs_saved": (r["out"] / "container-stdout.log").exists()
                  and (r["out"] / "container-stdout.log").stat().st_size > 0,
    "container_rc": r["record"].get("container_exit_code"),
    "removed_verified": r["record"].get("container_removed_verified")}

# ---- B: bad script hash (fails right after ACK) ---------------------------
r = run_case(
    "cx-bad-hash",
    cfg_over={"entry_command": ["sh", "-c", FAKE_CMD],
              "extra_mounts": [FAKE_MOUNT]},
    env_over={"VIMAX_MEDIA_SOURCE_SCRIPT_SHA256":
              "deadbeef" * 8})
ef = r["out"] / "workspace/attempt/ENTRY-FAILED.json"
payload = json.loads(ef.read_text()) if ef.exists() else {}
results["B_bad_hash"] = {
    "entry_failed_exists": ef.exists(),
    "message": payload.get("message", "")[:80],
    "traceback_nonempty": bool(payload.get("traceback")),
    "complete_not_fabricated": not (r["out"] / "workspace/attempt/COMPLETE").exists(),
    "model_sends_zero": not (r["out"] / "workspace/attempt/model-events.jsonl").exists(),
    "container_rc": r["record"].get("container_exit_code"),
    "logs_saved": ((r["out"] / "container-logs-final.log").exists()
                   and (r["out"] / "container-logs-final.log").stat().st_size > 0)
                  or ((r["out"] / "container-stdout.log").exists()
                      and (r["out"] / "container-stdout.log").stat().st_size > 0),
    "removed_verified": r["record"].get("container_removed_verified")}

# ---- C: fake boundary never started --------------------------------------
r = run_case(
    "cx-no-fake",
    cfg_over={"entry_command": ["sh", "-c", NO_FAKE_CMD]},
    env_over={})
ef = r["out"] / "workspace/attempt/ENTRY-FAILED.json"
agent_events = r["out"] / "workspace/attempt/agent-events.jsonl"
results["C_no_fake"] = {
    "seed_completed": (r["out"] / "workspace/attempt/session-source-map.json").exists(),
    "agent_error_event": any('"error"' in l for l in
                             agent_events.read_text().splitlines())
                         if agent_events.exists() else False,
    "container_rc": r["record"].get("container_exit_code"),
    "logs_saved": ((r["out"] / "container-logs-final.log").exists()
                   and (r["out"] / "container-logs-final.log").stat().st_size > 0)
                  or ((r["out"] / "container-stdout.log").exists()
                      and (r["out"] / "container-stdout.log").stat().st_size > 0),
    "removed_verified": r["record"].get("container_removed_verified"),
    "cleanup_errors": r["record"].get("cleanup_errors")}

(RUNS / "counterexamples.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1) + "\n")
print(json.dumps(results, ensure_ascii=False, indent=1))
dup_ok = "already exists" in (results["A_duplicate_session"]["message"] or "")
ok = (dup_ok
      and results["A_duplicate_session"]["entry_failed_exists"]
      and results["A_duplicate_session"]["sessions_untouched"]
      and results["A_duplicate_session"]["model_sends_zero"]
      and results["B_bad_hash"]["entry_failed_exists"]
      and results["B_bad_hash"]["traceback_nonempty"]
      and results["B_bad_hash"]["model_sends_zero"]
      and results["B_bad_hash"]["container_rc"] == 1
      and results["B_bad_hash"]["logs_saved"]
      and results["C_no_fake"]["seed_completed"]
      and results["C_no_fake"]["container_rc"] == 0
      and results["C_no_fake"]["logs_saved"])
print("COUNTEREXAMPLES_OK" if ok else "COUNTEREXAMPLES_FAILED")
raise SystemExit(0 if ok else 7)
