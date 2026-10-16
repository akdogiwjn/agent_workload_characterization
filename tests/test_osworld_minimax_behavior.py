import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("osworld_minimax_behavior", ROOT / "scripts" / "osworld_minimax_behavior.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value)


def _make_input(tmp_path):
    root = tmp_path / "raw"
    task = root / "website_demo" / "MiniMax-M3" / "tasks" / "001"
    rows = [
        {"step_num": 1, "action": "pyautogui.click(1, 2); pyautogui.click(2, 3); pyautogui.scroll(3)", "done": False, "reward": 0},
        {"step_num": 2, "action": "not a call", "done": False},
        {"step_num": 3, "action": "pyautogui.press('x'); pyautogui.press('y'); pyautogui.click(4, 5)", "done": True, "reward": 1},
    ]
    _write(task / "traj.jsonl", "\n".join(json.dumps(row) for row in rows) + "\n")
    _write(task / "result.json", json.dumps({"score": 0}))
    _write(task / "result.txt", "0\nunknown-state\n")
    _write(task / "checkpoint_results.json", json.dumps([{"score": 0}, {"passed": False}]))
    return root, _make_inventory(root, tmp_path / "inventory.json")


def _make_inventory(root, path):
    files = []
    for source in sorted(root.rglob("*")):
        if source.is_file():
            data = source.read_bytes()
            files.append({"path": str(source.relative_to(root)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    path.write_text(json.dumps({"requested_revision": MOD.EXPECTED_REVISION, "files": files}))
    return path


def test_supported_parser_is_conservative_and_preserves_source_occurrences():
    parsed = MOD.static_calls("pyautogui.click(1, 2); pyautogui.scroll(1)")
    assert parsed["status"] == "known"
    assert [item["category"] for item in parsed["calls"]] == ["click", "scroll"]
    assert MOD.static_calls("def f():\n    pyautogui.click(1, 2)")["reason"] == "unsupported_structure"
    assert MOD.static_calls("[pyautogui.click(i, i) for i in range(2)")["reason"] == "syntax_error"
    assert MOD.static_calls("[pyautogui.click(i, i) for i in range(2)]")["reason"] == "unsupported_structure"
    assert MOD.static_calls("custom_click('click scroll')")["reason"] == "unknown_call"
    assert MOD.static_calls("pyautogui.press('click scroll')")["calls"][0]["category"] == "text_or_key"
    assert MOD.static_calls("pyautogui.click(1, nested())")["reason"] == "nested_call"


def test_segments_transitions_and_unknown_boundaries(tmp_path):
    root, inventory = _make_input(tmp_path)
    summary = MOD.run(root, inventory, tmp_path / "out")
    record = summary["tasks"][0]
    assert record["transition_counts"] == {
        "click->click": 1, "click->scroll": 1,
        "text_or_key->text_or_key": 1, "text_or_key->click": 1,
    }
    assert "scroll->press" not in record["transition_counts"]
    assert record["contiguous_segment_counts"] == {"click": 2, "scroll": 1, "text_or_key": 1}
    assert record["contiguous_segment_action_counts"] == {"click": 3, "scroll": 1, "text_or_key": 2}
    assert record["contiguous_segment_length_counts"] == {"click:1": 1, "click:2": 1, "scroll:1": 1, "text_or_key:2": 1}
    assert record["unknown_action_record_count"] == 1
    assert record["analysis_status"] == "partial"


def test_single_action_and_unknown_tail_do_not_create_cross_boundary_edges(tmp_path):
    root, inventory = _make_input(tmp_path)
    trajectory = root / "website_demo" / "MiniMax-M3" / "tasks" / "001" / "traj.jsonl"
    trajectory.write_text(json.dumps({"step_num": 1, "action": "pyautogui.click(1, 2)"}) + "\n" + json.dumps({"step_num": 2, "action": "not a call"}) + "\n")
    inventory = _make_inventory(root, tmp_path / "inventory2.json")
    record = MOD.run(root, inventory, tmp_path / "out2")["tasks"][0]
    assert record["transition_counts"] == {}
    assert record["contiguous_segment_counts"] == {"click": 1}
    assert record["contiguous_segment_action_counts"] == {"click": 1}


def test_result_reward_and_done_are_separate_and_zero_is_retained(tmp_path):
    root, inventory = _make_input(tmp_path)
    record = MOD.run(root, inventory, tmp_path / "out")["tasks"][0]
    assert record["reward"]["numeric_or_bool_value_counts"] == {"0": 1, "1": 1}
    assert record["done_counts"] == {"False": 2, "True": 1}
    assert record["results"]["result_json"]["score"]["value"] == 0.0
    assert record["results"]["result_txt"]["numeric_values"][0]["value"] == 0.0
    assert record["results"]["result_txt"]["nonnumeric_line_count"] == 1
    assert record["results"]["checkpoint_results"]["recognized_scalar_fields"][0]["value"] == 0


def test_hash_and_revision_mismatch_are_rejected(tmp_path):
    root, inventory = _make_input(tmp_path)
    (root / "website_demo" / "MiniMax-M3" / "tasks" / "001" / "traj.jsonl").write_text("{}\n")
    try:
        MOD.run(root, inventory, tmp_path / "bad_hash")
    except MOD.AnalysisError as exc:
        assert "input hash mismatch" in str(exc)
    else:
        raise AssertionError("hash mismatch was accepted")
    root, inventory = _make_input(tmp_path / "revision")
    payload = json.loads(inventory.read_text())
    payload["requested_revision"] = "wrong"
    inventory.write_text(json.dumps(payload))
    try:
        MOD.run(root, inventory, tmp_path / "bad_revision")
    except MOD.AnalysisError as exc:
        assert "revision mismatch" in str(exc)
    else:
        raise AssertionError("revision mismatch was accepted")


def test_input_change_changes_report_via_complete_entry(tmp_path):
    root, inventory = _make_input(tmp_path)
    first = MOD.run(root, inventory, tmp_path / "first")
    trajectory = root / "website_demo" / "MiniMax-M3" / "tasks" / "001" / "traj.jsonl"
    trajectory.write_text(trajectory.read_text().replace("pyautogui.scroll(3)", "pyautogui.moveTo(3, 3)"))
    inventory2 = _make_inventory(root, tmp_path / "inventory2.json")
    second = MOD.run(root, inventory2, tmp_path / "second")
    assert first["pooled_category_counts"] != second["pooled_category_counts"]
    assert (tmp_path / "first" / "summary.json").read_bytes() != (tmp_path / "second" / "summary.json").read_bytes()
