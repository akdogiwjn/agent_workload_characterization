"""Offline regression for TOOLSANDBOX-RESOURCE-PILOT-01 wiring.

Every fake-transport test drives the REAL official chain in the worker
subprocess: official role message conversion and response handling,
Scenario.play, the official ExecutionEnvironment (including parallel-call
permutation execution) and the official evaluator. No pre-baked success
summaries; no network; no credentials; all data stays under temporary roots.

Executed by direct function calls (the environment has no pytest); the runner
at the bottom reports the actual pass count.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "tsb_entry", ROOT / "scripts/toolsandbox_resource_pilot_01_entry.py")
entry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entry)

SCENARIO = "send_message_with_contact_content_cellular_off"
ORIGIN = ROOT / "references/repos/ToolSandbox"

AGENT_SEND = {"id": "call_a3", "type": "function", "function": {
    "name": "send_message_with_phone_number",
    "arguments": "{\"phone_number\": \"+12453344098\", \"content\": \"How's the new album coming along\"}"}}
AGENT_MULTI = [
    {"id": "call_a1", "type": "function", "function": {
        "name": "search_contacts", "arguments": "{\"name\": \"Fredrik Thordendal\"}"}},
    {"id": "call_a2", "type": "function", "function": {
        "name": "set_cellular_service_status", "arguments": "{\"on\": true}"}}]
USER_END = {"id": "call_u1", "type": "function", "function": {
    "name": "end_conversation", "arguments": "{}"}}
FINAL_CONTENT = "Your message to Fredrik Thordendal has been sent saying: How's the new album coming along"


def fake_transport(agent_script, user_script=None, model_name="fake-request-model"):
    return {"kind": "fake", "model_name": model_name,
            "script": {"agent": agent_script,
                       "user": user_script if user_script is not None else
                       [{"tool_calls": [USER_END],
                         "usage": {"prompt_tokens": 80, "completion_tokens": 8,
                                   "total_tokens": 88},
                         "model": "fake-user-model"}]}}


def standard_agent_script():
    return [
        {"tool_calls": AGENT_MULTI,
         "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                   "prompt_cache_hit_tokens": 42},
         "model": "fake-agent-model"},
        {"tool_calls": [AGENT_SEND],
         "usage": {"prompt_tokens": 200, "completion_tokens": 30, "total_tokens": 230},
         "model": "fake-agent-model"},
        {"content": FINAL_CONTENT,
         "usage": {"prompt_tokens": 300, "completion_tokens": 40, "total_tokens": 340},
         "model": "fake-agent-model"},
    ]


def prepare_root(tmp, budgets=None, profile=None):
    """Fresh temp root with source prepared, frozen identity and approval."""
    root = Path(tmp)
    profile = profile or entry.PILOT_01_PROFILE
    if profile.shared_entry_script is not None:
        source_origin = ROOT / entry.PILOT_01_PROFILE.source_copy_rel
        source_manifest = ROOT / entry.PILOT_01_PROFILE.env_rel / "source-manifest.json"
        shutil.copytree(source_origin, root / profile.source_copy_rel)
        manifest_copy = root / entry.PILOT_01_PROFILE.env_rel / "source-manifest.json"
        manifest_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_manifest, manifest_copy)
    entry.prepare_source(root, profile=profile)
    entry.freeze(root, budgets=budgets, profile=profile)
    plan = entry.plan_mode(root, budgets=budgets, profile=profile)
    approval = {"schema": "toolsandbox-pilot-approval-v1", "collection": profile.collection,
                "user_approval": "approved", "identity_sha256": plan["identity_sha256"],
                "accept_unknown_cost_no_hard_cap": True}
    approval_path = root / profile.report_rel / "APPROVAL.json"
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(json.dumps(approval))
    plan = entry.plan_mode(root, budgets=budgets, profile=profile)
    if not budgets or all(value > 0 for value in budgets.values()):
        assert plan["ready_for_execution"] is True
    return root


def minimal_initialized_attempt(root, profile=None):
    profile = profile or entry.PILOT_01_PROFILE
    plan = {"ready_for_execution": True, "identity_sha256": "a" * 64,
            "identity": {"budgets": {**entry.BUDGETS}, "retry": {},
                "official_source": {"frozen_copy": "source",
                                    "source_manifest": "env/source-manifest.json"}}}
    return root, plan, profile


def run_fake(root, transport, profile=None):
    profile = profile or entry.PILOT_01_PROFILE
    saved = json.loads((root / profile.env_rel / "plan-identity.json").read_text())
    plan = entry.plan_mode(root, budgets=saved["identity"]["budgets"], profile=profile)
    rc = entry.execute(root, plan, transport=transport, profile=profile)
    report = json.loads((root / profile.report_rel / "run-report.json").read_text())
    run_dir = root / profile.raw_rel / report["run_id"]
    return rc, report, run_dir


def load_events(run_dir):
    return [json.loads(l) for l in (run_dir / "events.jsonl").read_text().splitlines() if l.strip()]


def spans(events, kind, status=None):
    return [e for e in events if e["kind"] == kind
            and (status is None or e["status"] == status)]


def span_pairs(events, kind):
    """One entry per span (open+closed rows share the event_id); merged attrs."""
    pairs = {}
    for e in events:
        if e["kind"] != kind:
            continue
        entry = pairs.setdefault(e["event_id"], {})
        entry[e["status"]] = e
    out = []
    for event_id, entry in pairs.items():
        if "open" in entry:
            merged = {**entry["open"].get("attrs", {}),
                      **entry.get("closed", entry.get("error", entry.get("unclosed", {}))).get("attrs", {})}
            out.append({"event_id": event_id, "status": entry["open"]["status"] if "closed" not in entry else "closed",
                        "t_open_ns": entry["open"]["t_monotonic_ns"],
                        "attrs": merged})
    out.sort(key=lambda e: e["t_open_ns"])
    return out


def tree_hash(path):
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_default_plan_zero_side_effects():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        entry.prepare_source(root)
        entry.freeze(root)
        before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        plan = entry.plan_mode(root)
        after = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
        assert before == after, "plan mode created files"
        assert plan["ready_for_approval"] is True
        assert plan["ready_for_execution"] is False
        assert plan["approval_status"] == "missing"
        assert not (root / entry.RAW_REL).exists()
        assert plan["identity"]["route"]["api_key_env"] == "DEEPSEEK_API_KEY"
        assert plan["identity"]["route"]["real_api_compatibility_verified"] is False
        assert plan["identity"]["retry"]["sdk_max_retries"] == 0
        assert "requests.exceptions.HTTPError" in plan["identity"]["retry"]["official_defaults_and_deviation"]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            entry.plan_mode(Path(tmp))
            raise AssertionError("expected refusal without prepared source")
        except ValueError:
            pass


def test_full_fake_run_lifecycle_and_counts():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp)
        rc, report, run_dir = run_fake(root, fake_transport(standard_agent_script()))
        assert rc == 0 and report["killed_by_deadline"] is False
        wr = report["worker_result"]
        # stop condition recorded from the official ending context
        assert wr["stop"]["reason"] == "user_end_conversation"
        assert wr["stop"]["user_end_conversation_executed"] is True
        # logical model calls per role; batches and logical calls not confused
        assert wr["counts"]["agent_logical_calls"] == 3
        assert wr["counts"]["user_logical_calls"] == 1
        assert wr["counts"]["tool_batches"]["started"] == 3
        assert wr["counts"]["logical_tool_calls"]["started"] == 4
        assert wr["counts"]["tool_call_executions"] == 5
        assert wr["failure"] is None
        # official evaluator really ran and produced raw fields
        assert wr["evaluation"]["milestone_similarity"] == 1.0
        assert wr["evaluation"]["similarity"] == 1.0
        assert wr["evaluation"]["turn_count"] == 7
        assert wr["final_max_sandbox_message_index"] - wr["initial_max_sandbox_message_index"] > 0
        events = load_events(run_dir)
        llm = span_pairs(events, "llm_request")
        assert len(llm) == 4
        by_role = {}
        for e in llm:
            by_role.setdefault(e["attrs"]["role"], []).append(e)
        assert len(by_role["agent"]) == 3 and len(by_role["user"]) == 1
        assert all(e["status"] == "closed" for e in llm)
        first = by_role["agent"][0]["attrs"]
        assert first["usage"]["prompt_cache_hit_tokens"] == 42  # vendor field preserved
        assert first["model"] == "fake-request-model"
        assert first["response_model"] == "fake-agent-model"
        assert first["transport_attempt_count"] == 1
        # logical tool calls: roles, names, request links, results
        calls = span_pairs(events, "tool_call")
        assert len(calls) == 4 and all(c["status"] == "closed" for c in calls)
        agent_calls = [e for e in calls if e["attrs"]["role"] == "agent"]
        assert [e["attrs"]["tool_name"] for e in agent_calls] == [
            "search_contacts", "set_cellular_service_status", "send_message_with_phone_number"]
        user_calls = [e for e in calls if e["attrs"]["role"] == "user"]
        assert [e["attrs"]["tool_name"] for e in user_calls] == ["end_conversation"]
        assert user_calls[0]["attrs"]["request_event_id"] == "user-1"
        # last tool return persisted (end_conversation result) even with no later request
        assert len(user_calls) == 1 and user_calls[0]["attrs"]["ok"] is True
        # batches: permutation path for the parallel batch
        batches = span_pairs(events, "tool_batch")
        assert len(batches) == 3
        b1 = batches[0]["attrs"]
        assert b1["call_ids"] == ["call_a1", "call_a2"]
        assert b1["planned_orderings"] == 2
        assert b1["executed_orderings"] == 2
        assert "resource_before" in b1 and "resource_after" in b1
        # no model request after the user's end_conversation call: the final
        # batch (executing end_conversation) begins after every closed llm span
        final_batch = batches[-1]
        assert final_batch["t_open_ns"] >= max(e["t_open_ns"] for e in llm)
        assert not spans(events, "budget")
        # official outputs exist in the official format
        for name in ("conversation.json", "execution_context.json", "pretty_print.txt"):
            assert (run_dir / "official" / "trajectories" / SCENARIO / name).is_file()
        # host sampling and phase boundaries
        assert report["host_sampling"]["rows"] > 0
        phases = [p["phase"] for p in report["budget_phase_report"]["phases"]]
        for phase in ("worker_start", "play_begin", "evaluate_begin", "evaluate_end", "worker_end"):
            assert phase in phases
        # transport request counts: agent 3, user 1 (one request per logical call)
        assert wr["transport"]["stats"] == {"agent_requests": 3, "user_requests": 1}
        assert report["archive_verification"]["valid"] is True
        assert report["evaluation_status"] == "completed"
        assert report["cleanup"]["wait_reaped"] and report["cleanup"]["original_process_gone"]
        assert report["cleanup"]["sampler_stopped"] and report["within_total_budget"]
        supplement_path = run_dir / "supplemental_measurements.json"
        assert supplement_path.is_file()
        supplement = json.loads(supplement_path.read_text())
        assert supplement["network"]["scope_kind"] == "network_namespace_shared"
        assert supplement["disk_footprint"]["paths"][0]["role"] == "attempt_output"
        assert supplement["task_workspace"]["status"] == "not_applicable"
        assert supplement["task_workspace"]["visible_output"] == "host_visible_worker_output"
        assert "supplemental_measurements.json" in {
            row["path"] for row in json.loads((run_dir / "manifest.json").read_text())["files"]}
        assert report["host_sampling"]["resource_intervals"]
        edges = {p["phase"]: p for p in report["budget_phase_report"]["phases"]}
        assert edges["play_end"]["phase_end_ns"] < edges["evaluate_begin"]["phase_start_ns"]
        assert edges["worker_start"]["t_monotonic_ns"] >= report["parent_start_ns"]
        for stage in ("play", "evaluate"):
            start = edges[stage + "_begin"]
            assert start["common_work_deadline_ns"] == report["common_work_deadline_ns"]
            assert start["phase_deadline_ns"] == min(
                start["phase_start_ns"] + int(wr["budgets"][stage + "_s"] * 1e9),
                report["common_work_deadline_ns"])


def test_budget_cap_blocks_next_request():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"agent_logical_calls": 2})
        rc, report, run_dir = run_fake(root, fake_transport(standard_agent_script()))
        wr = report["worker_result"]
        assert rc == 3
        assert wr["failure"] == {"kind": "model_budget_exhausted", "role": "agent", "limit": 2}
        assert wr["counts"]["agent_logical_calls"] == 2
        # exactly cap requests reached the transport; the 3rd was refused before it
        assert wr["transport"]["stats"]["agent_requests"] == 2
        events = load_events(run_dir)
        budget_points = spans(events, "budget")
        assert len(budget_points) == 1
        assert budget_points[0]["attrs"]["limit_name"] == "agent_logical_calls"
        assert len(span_pairs(events, "llm_request")) == 2


def test_tool_error_model_retry_and_evaluation_separated():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp)
        agent_script = [
            {"http_status": 500, "error_message": "fake transient server error"},
            {"tool_calls": [AGENT_SEND],  # fails: cellular still off
             "usage": {"prompt_tokens": 150, "completion_tokens": 25, "total_tokens": 175},
             "model": "fake-agent-model"},
            {"tool_calls": AGENT_MULTI,
             "usage": {"prompt_tokens": 250, "completion_tokens": 25, "total_tokens": 275},
             "model": "fake-agent-model"},
            {"tool_calls": [AGENT_SEND],
             "usage": {"prompt_tokens": 350, "completion_tokens": 30, "total_tokens": 380},
             "model": "fake-agent-model"},
            {"content": FINAL_CONTENT,
             "usage": {"prompt_tokens": 450, "completion_tokens": 40, "total_tokens": 490},
             "model": "fake-agent-model"},
        ]
        rc, report, run_dir = run_fake(root, fake_transport(agent_script))
        assert rc == 0
        wr = report["worker_result"]
        events = load_events(run_dir)
        llm = span_pairs(events, "llm_request")
        # logical vs transport: 4 logical agent calls, 5 transport hits (500 + retry)
        assert wr["counts"]["agent_logical_calls"] == 4
        assert wr["transport"]["stats"]["agent_requests"] == 5
        agent_llm = [e for e in llm if e["attrs"]["role"] == "agent"]
        assert agent_llm[0]["attrs"]["transport_attempt_count"] == 2
        assert agent_llm[0]["attrs"]["usage"]["prompt_tokens"] == 150
        # tool error: first send_message fails with ConnectionError (cellular off)
        calls = span_pairs(events, "tool_call")
        failed = [e for e in calls if e["attrs"].get("ok") is False]
        assert len(failed) == 1 and failed[0]["attrs"]["error"] == "ConnectionError:<sanitized>"
        # model exception path and tool error path and evaluation are distinct records
        assert wr["evaluation"]["milestone_similarity"] == 1.0
        assert wr["stop"]["reason"] == "user_end_conversation"
        assert not spans(events, "infra")


def test_timeout_kills_worker_and_preserves_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"total_wall_s": 30.0, "cleanup_reserve_s": 3.0,
                                          "play_s": 5.0, "evaluate_s": 2.0})
        agent_script = [{"sleep_s": 30, "content": "never returned in time"}]
        rc, report, run_dir = run_fake(root, fake_transport(agent_script))
        assert report["killed_by_deadline"] is True
        assert rc == 4
        assert report["worker_result"] is None  # worker never wrote result.json
        for name in ("ATTEMPT_STARTED.json", "job.json", "events.jsonl", "samples.jsonl",
                     "worker.stderr", "worker.stdout"):
            assert (run_dir / name).is_file(), name
        events = load_events(run_dir)
        # the hung request stays open (right-censored); no fabricated closure
        assert len(spans(events, "llm_request", "open")) == 1
        assert spans(events, "run", "open")  # run marker survives the kill
        assert report["host_sampling"]["rows"] >= 4
        assert report["archive_verification"]["valid"] is True


def test_archive_hashes_bind_final_content():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp)
        rc, report, run_dir = run_fake(root, fake_transport(standard_agent_script()))
        assert rc == 0
        valid, errors = entry.verify_run_archive(run_dir)
        assert valid and errors == []
        target = run_dir / "result.json"
        original = target.read_bytes()
        target.write_bytes(original + b"\n")
        valid2, errors2 = entry.verify_run_archive(run_dir)
        assert not valid2 and any("hash_mismatch" in e for e in errors2)
        target.write_bytes(original)
        (run_dir / "unlisted.txt").write_text("x")
        valid3, errors3 = entry.verify_run_archive(run_dir)
        assert not valid3 and any("unlisted_actual" in e for e in errors3)


def assert_timeout_reaped_and_archived(report, run_dir, kind, evaluation_status):
    assert report["exit_code"] == 4 and report["killed_by_deadline"]
    assert report["deadline_timeout"]["kind"] == kind
    assert report["worker_result"] is None
    assert report["evaluation"] is None and report["evaluation_status"] == evaluation_status
    assert report["cleanup"]["wait_reaped"] and report["cleanup"]["original_process_gone"]
    assert report["cleanup"]["sampler_stopped"]
    pid = report["cleanup"]["pid"]
    try:
        os.waitpid(pid, os.WNOHANG)
        raise AssertionError("parent has not reaped worker")
    except ChildProcessError:
        pass
    assert report["within_total_budget"] and report["remaining_cleanup_archive_s"] > 1
    assert entry.verify_run_archive(run_dir) == (True, [])
    marker = json.loads((run_dir / "ATTEMPT_COMPLETED.json").read_text())
    assert marker["exit_code"] == report["exit_code"]
    assert marker["deadline_timeout"] == report["deadline_timeout"]
    assert marker["cleanup"] == report["cleanup"]
    parent_manifest = json.loads((run_dir.parents[4] / entry.REPORT_REL / "manifest.json").read_text())
    for item in parent_manifest["outputs"]:
        path = run_dir.parents[4] / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    events_before = (run_dir / "events.jsonl").read_bytes()
    time.sleep(.05)
    assert events_before == (run_dir / "events.jsonl").read_bytes()


def test_play_phase_deadline_kills_blocked_worker_before_common_deadline():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"total_wall_s": 20., "cleanup_reserve_s": 4.,
                                          "play_s": .6, "evaluate_s": 3.})
        _, report, run_dir = run_fake(root, fake_transport([{"sleep_s": 30, "content": "blocked"}]))
        assert_timeout_reaped_and_archived(report, run_dir, "play_deadline", "not_started")
        assert report["deadline_timeout"]["deadline_ns"] < report["common_work_deadline_ns"]
        phases = [p["phase"] for p in report["budget_phase_report"]["phases"]]
        assert "play_begin" in phases and "play_end" not in phases and "evaluate_begin" not in phases
        events = load_events(run_dir)
        assert len(spans(events, "llm_request", "open")) == 1
        assert not spans(events, "llm_request", "closed")


def test_evaluate_phase_deadline_kills_worker_preserving_completed_play():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"total_wall_s": 20., "cleanup_reserve_s": 4.,
                                          "play_s": 6., "evaluate_s": .4})
        transport = fake_transport(standard_agent_script())
        transport["evaluate_sleep_s"] = 30
        _, report, run_dir = run_fake(root, transport)
        assert_timeout_reaped_and_archived(report, run_dir, "evaluate_deadline", "incomplete")
        assert report["deadline_timeout"]["deadline_ns"] < report["common_work_deadline_ns"]
        phases = [p["phase"] for p in report["budget_phase_report"]["phases"]]
        assert "play_end" in phases and "evaluate_begin" in phases and "evaluate_end" not in phases
        events = load_events(run_dir)
        assert len(spans(events, "llm_request", "closed")) == 4
        assert len(spans(events, "tool_call", "closed")) == 4
        assert (run_dir / "official/trajectories" / SCENARIO / "execution_context.json").is_file()


def test_common_deadline_wins_when_evaluator_starts_with_little_time():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"total_wall_s": 23., "cleanup_reserve_s": 3.,
                                          "play_s": 5., "evaluate_s": 4.})
        transport = fake_transport(standard_agent_script())
        transport.update(evaluate_start_remaining_s=.3, evaluate_sleep_s=30)
        _, report, run_dir = run_fake(root, transport)
        assert_timeout_reaped_and_archived(report, run_dir, "common_work_deadline", "incomplete")
        start = next(p for p in report["budget_phase_report"]["phases"] if p["phase"] == "evaluate_begin")
        assert 0 < (report["common_work_deadline_ns"]-start["phase_start_ns"])/1e9 <= .31
        assert start["phase_deadline_ns"] == report["common_work_deadline_ns"]
        assert report["deadline_timeout"]["observed_ns"] - report["common_work_deadline_ns"] < 500_000_000


def test_no_phase_budget_refuses_phase_before_model_or_evaluator():
    for stage in ("play", "evaluate"):
        with tempfile.TemporaryDirectory() as tmp:
            root = prepare_root(tmp, budgets={stage + "_s": 0.})
            rc, report, run_dir = run_fake(root, fake_transport(standard_agent_script()))
            assert rc == 4 and report["killed_by_deadline"] is False
            assert report["worker_result"]["failure"]["phase"] == stage
            assert report["evaluation"] is None and report["evaluation_status"] == "not_started"
            phases = [p["phase"] for p in report["budget_phase_report"]["phases"]]
            assert stage + "_not_started" in phases and stage + "_begin" not in phases
            if stage == "play":
                assert report["worker_result"]["counts"]["agent_logical_calls"] == 0
                assert report["worker_result"]["counts"]["user_logical_calls"] == 0
                assert not spans(load_events(run_dir), "llm_request")
            assert report["cleanup"]["wait_reaped"] and report["cleanup"]["original_process_gone"]
            assert entry.verify_run_archive(run_dir) == (True, [])


def test_short_test_budgets_do_not_change_production_values():
    original = dict(entry.BUDGETS)
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"play_s": .1})
        assert entry.plan_mode(root, budgets={"play_s": .1})["identity"]["budgets"]["play_s"] == .1
    assert entry.BUDGETS == original
    try:
        entry.build_identity(ROOT, budgets={"play_s": .1})
        raise AssertionError("production budget override allowed")
    except ValueError:
        pass


def test_expired_common_work_window_refuses_stage_start():
    from agent_workload_characterization.runners.toolsandbox_worker import (
        BoundaryWriter, PhaseDeadlineExceeded, begin_phase)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "boundaries.jsonl"
        writer = BoundaryWriter(path)
        common = time.monotonic_ns() - 1
        for stage, budget in (("play", 300), ("evaluate", 60)):
            try:
                begin_phase(writer, stage, budget, common)
                raise AssertionError("expired common window started a blocking phase")
            except PhaseDeadlineExceeded as exc:
                assert exc.phase == stage and exc.deadline_kind == "common_work_deadline"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert [r["phase"] for r in rows] == ["play_not_started", "evaluate_not_started"]
        assert all(r["phase_deadline_ns"] == common for r in rows)


def test_default_openai_clients_construct_for_agent_and_user_without_http_requests():
    import httpx
    import openai
    from agent_workload_characterization.runners.toolsandbox_worker import (
        construct_openai_role_clients)

    requests = []
    original = httpx.HTTPTransport.handle_request

    def forbidden_send(self, request):
        requests.append(str(request.url))
        raise AssertionError("client construction must not send HTTP")

    httpx.HTTPTransport.handle_request = forbidden_send
    clients = []
    try:
        clients = list(construct_openai_role_clients(
            openai, base_url="https://api.deepseek.com/v1", api_key="sk-synthetic-key"))
        assert len(clients) == 2
        assert all(client.max_retries == 0 for client in clients)
    finally:
        for client in clients:
            client.close()
        httpx.HTTPTransport.handle_request = original
    assert requests == []


def test_client_initialization_failure_is_archived_as_safe_infra_result():
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp)
        transport = fake_transport(standard_agent_script())
        transport["simulate_client_init_failure"] = True
        rc, report, run_dir = run_fake(root, transport)
        assert rc == 5
        assert report["worker_result"]["failure"] == {
            "kind": "infra_error", "phase": "client_initialization",
            "error_type": "TypeError"}
        assert report["evaluation_status"] == "not_started"
        events = load_events(run_dir)
        infra = spans(events, "infra", "point")
        assert len(infra) == 1
        assert infra[0]["attrs"]["detail"] == "openai_client_initialization:TypeError"
        assert not spans(events, "llm_request")
        assert not spans(events, "tool_call")
        assert entry.verify_run_archive(run_dir) == (True, [])
        assert report["cleanup"]["wait_reaped"] and report["cleanup"]["original_process_gone"]


def test_pilot02_profile_isolated_and_plan_identity_is_collection_specific():
    profile = entry.PILOT_02_PROFILE
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        entry.prepare_source(root)
        entry.prepare_source(root, profile=profile)
        plan = entry.freeze(root, profile=profile)
        assert plan["collection"] == "TOOLSANDBOX-RESOURCE-PILOT-02"
        assert plan["identity"]["paths"]["env"] == str(profile.env_rel)
        assert plan["identity"]["paths"]["approval"] == str(profile.report_rel / "APPROVAL.json")
        assert plan["identity"]["approval_flag"] == profile.approval_flag
        assert any(x["path"] == "scripts/toolsandbox_resource_pilot_02_entry.py"
                   for x in plan["identity"]["code_and_runtime_files"])
        assert any(x["path"] == "scripts/toolsandbox_resource_pilot_01_entry.py"
                   for x in plan["identity"]["code_and_runtime_files"])
        assert entry.plan_mode(root, profile=profile)["ready_for_approval"]
        approval_path = root / profile.report_rel / "APPROVAL.json"
        approval_path.parent.mkdir(parents=True)
        approval_path.write_text(json.dumps({
            "schema": "toolsandbox-pilot-approval-v1",
            "collection": profile.collection, "user_approval": "approved",
            "identity_sha256": plan["identity_sha256"],
            "accept_unknown_cost_no_hard_cap": True}))
        assert entry.plan_mode(root, profile=profile)["ready_for_execution"]
        try:
            entry.main(["--execute", "--i-approve-the-toolsandbox-resource-pilot-01"],
                       root=root, profile=profile)
            raise AssertionError("P01 approval flag accepted by P02")
        except SystemExit as exc:
            assert exc.code == 2
        (root / profile.raw_rel / "occupied-attempt").mkdir(parents=True)
        occupied = entry.plan_mode(root, profile=profile)
        assert occupied["existing_attempts"] == ["occupied-attempt"]
        assert not occupied["ready_for_approval"]
        try:
            entry.execute(root, occupied, profile=profile,
                          transport=fake_transport(standard_agent_script()))
            raise AssertionError("occupied P02 attempt namespace accepted")
        except ValueError as exc:
            assert "identity/approval/namespace gate" in str(exc)


def test_runtime_environment_record_saves_host_and_key_dependency_identity():
    record = entry.runtime_environment_record(os.getpid(), 1)
    assert record["architecture"]
    assert record["kernel_release"]
    assert record["python_version"]
    assert "cpu_model" in record
    assert set(record["key_dependency_versions"]) == {"openai", "httpx", "httpcore", "polars"}
    assert all(item["status"] in ("observed", "not_installed")
               for item in record["key_dependency_versions"].values())


def test_references_and_real_namespace_unchanged():
    before = tree_hash(ORIGIN)
    real_env = ROOT / entry.ENV_REL
    env_before = tree_hash(real_env)
    real_raw = ROOT / entry.RAW_REL
    real_report = ROOT / entry.REPORT_REL
    raw_before = tree_hash(real_raw) if real_raw.exists() else None
    report_before = tree_hash(real_report) if real_report.exists() else None
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp)
        rc, _, _ = run_fake(root, fake_transport(standard_agent_script()))
        assert rc == 0
    after = tree_hash(ORIGIN)
    assert before == after, "reference tree changed"
    # Existing P01 attempt evidence is protected; tests only write temp roots.
    assert (tree_hash(real_raw) if real_raw.exists() else None) == raw_before
    assert (tree_hash(real_report) if real_report.exists() else None) == report_before
    assert tree_hash(real_env) == env_before, "test changed real preparation/stop records"
    # frozen copy matches the reference tree byte-for-byte
    src_manifest = json.loads((real_env / "source-manifest.json").read_text())
    for rec in src_manifest["files"]:
        origin_file = ORIGIN / rec["path"]
        frozen_file = real_env / "source" / rec["path"]
        assert origin_file.read_bytes() == frozen_file.read_bytes() == origin_file.read_bytes()
        assert hashlib.sha256(frozen_file.read_bytes()).hexdigest() == rec["sha256"]


def test_pilot02_real_execute_path_archives_shared_capture():
    profile = entry.PILOT_02_PROFILE
    with tempfile.TemporaryDirectory() as tmp:
        root = prepare_root(tmp, budgets={"total_wall_s": 60., "cleanup_reserve_s": 5.,
                                          "play_s": 30., "evaluate_s": 20.}, profile=profile)
        rc, report, run_dir = run_fake(root, fake_transport(standard_agent_script()), profile=profile)
        assert rc == 0
        assert report["cleanup"]["wait_reaped"] and report["cleanup"]["sampler_stopped"]
        assert report["supplemental_measurements"] == "supplemental_measurements.json"
        environment = json.loads((run_dir / "environment.json").read_text())
        assert environment["architecture"] and environment["kernel_release"]
        assert set(environment["key_dependency_versions"]) == {
            "openai", "httpx", "httpcore", "polars"}
        supplement = json.loads((run_dir / "supplemental_measurements.json").read_text())
        assert supplement["network"]["scope_kind"] == "network_namespace_shared"
        assert supplement["disk_footprint"]["paths"][0]["role"] == "attempt_output"
        assert supplement["task_workspace"]["status"] == "not_applicable"
        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert "supplemental_measurements.json" in {row["path"] for row in manifest["files"]}


def test_worker_popen_failure_stops_supplement_and_archives_partial_attempt():
    with tempfile.TemporaryDirectory() as tmp:
        root, plan, profile = minimal_initialized_attempt(Path(tmp))
        with mock.patch.object(entry.subprocess, "Popen", side_effect=OSError("spawn")):
            rc = entry.execute(root, plan, transport=fake_transport(standard_agent_script()),
                               run_id="popen-fails", profile=profile)
        run_dir = root / profile.raw_rel / "popen-fails"
        assert rc == 7
        assert (run_dir / "ATTEMPT_STARTED.json").is_file()
        assert (run_dir / "ATTEMPT_COMPLETED.json").is_file()
        assert (run_dir / "supplemental_measurements.json").is_file()
        assert entry.verify_run_archive(run_dir) == (True, [])
        report = json.loads((root / profile.report_rel /
                             "run-report.json").read_text())
        assert report["evaluation_status"] == "not_started"
        assert report["infra_failure"]["error_type"] == "OSError"


def test_environment_write_failure_reaps_spawned_worker_and_archives():
    class FakeProc:
        pid = 987654

        def __init__(self):
            self.returncode = None
            self.terminated = 0
            self.waited = 0

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated += 1

        def wait(self, timeout=None):
            self.waited += 1
            self.returncode = -15
            return self.returncode

        def kill(self):
            self.returncode = -9

    with tempfile.TemporaryDirectory() as tmp:
        root, plan, profile = minimal_initialized_attempt(Path(tmp))
        proc = FakeProc()
        with mock.patch.object(entry.subprocess, "Popen", return_value=proc), \
             mock.patch.object(entry, "runtime_environment_record",
                               side_effect=OSError("environment write")):
            rc = entry.execute(root, plan, transport=fake_transport(standard_agent_script()),
                               run_id="environment-write-fails", profile=profile)
        run_dir = root / profile.raw_rel / "environment-write-fails"
        assert rc == 7 and proc.terminated == 1 and proc.waited >= 1
        marker = json.loads((run_dir / "ATTEMPT_COMPLETED.json").read_text())
        assert marker["status"] == "failed" and marker["worker_reaped"]
        assert (run_dir / "supplemental_measurements.json").is_file()
        assert entry.verify_run_archive(run_dir) == (True, [])


def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception:
            failed += 1
            print("FAIL", name)
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
