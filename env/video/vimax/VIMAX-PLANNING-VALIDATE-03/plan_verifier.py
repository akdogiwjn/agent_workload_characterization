"""Offline verifier for a single fresh ViMax script-planning session."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def verify(workspace: Path) -> dict:
    from agent_runtime.session_index import SessionIndex
    from interfaces.camera import Camera
    from interfaces.character import CharacterInScene
    from interfaces.shot_description import ShotBriefDescription, ShotDescription
    from agent_runtime.vimax_adapters import preflight_render_capability
    from utils.video_generation_capabilities import configured_video_generation_capabilities

    workspace = workspace.resolve()
    sessions_file = workspace / ".vimax" / "sessions.json"
    if not sessions_file.is_file():
        raise RuntimeError("session index missing")
    session_data = json.loads(sessions_file.read_text(encoding="utf-8"))
    sessions = session_data.get("sessions", {})
    if len(sessions) != 1:
        raise RuntimeError(f"expected exactly one fresh session; found {len(sessions)}")
    session_id = session_data.get("active_session_id")
    session = sessions.get(session_id)
    if not isinstance(session, dict):
        raise RuntimeError("active session record is missing")
    frozen_script_bytes = (workspace / "registered-script.txt").read_bytes()
    frozen_script = frozen_script_bytes.decode("utf-8")
    checks = {"fresh_single_session": True,
              "session_mode_script": session.get("planning_mode") == "script",
              "session_source_matches_registered_script":
                  str(session.get("script", "")).encode("utf-8") == frozen_script_bytes}
    if not checks["session_mode_script"] or not checks["session_source_matches_registered_script"]:
        raise RuntimeError("session did not preserve the registered script source")

    working = workspace / str(session.get("working_dir", ""))
    if workspace not in working.resolve().parents:
        raise RuntimeError("session working directory escapes fresh workspace")
    base = working / "script2video"
    script_path = base / "script.txt"
    characters_path = base / "characters.json"
    storyboard_path = base / "storyboard.json"
    camera_path = base / "camera_tree.json"
    for p in (script_path, characters_path, storyboard_path, camera_path):
        if not p.is_file():
            raise RuntimeError(f"required planning artifact missing: {p.relative_to(workspace)}")
    if script_path.read_bytes() != frozen_script_bytes:
        raise RuntimeError("pipeline script artifact differs from registered script")

    raw_characters = json.loads(characters_path.read_text(encoding="utf-8"))
    characters = [CharacterInScene.model_validate(row) for row in raw_characters]
    if not characters:
        raise RuntimeError("character artifact is empty")
    storyboard_data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard = [ShotBriefDescription.model_validate(row) for row in storyboard_data]
    if [row.idx for row in storyboard] != list(range(8)):
        raise RuntimeError("storyboard must contain exactly ordered indices 0..7")
    if [row.is_last for row in storyboard] != [False] * 7 + [True]:
        raise RuntimeError("storyboard is_last markers do not match eight-shot contract")

    descriptions_dir = base / "shots"
    description_files = sorted(descriptions_dir.glob("*/shot_description.json"),
                               key=lambda p: int(p.parent.name))
    if len(description_files) != 8:
        raise RuntimeError(f"expected eight shot descriptions; found {len(description_files)}")
    descriptions = [ShotDescription.model_validate(
        json.loads(p.read_text(encoding="utf-8"))) for p in description_files]
    if [row.idx for row in descriptions] != list(range(8)):
        raise RuntimeError("shot description indices do not match 0..7")
    char_indices = {row.idx for row in characters}
    for shot in [*storyboard, *descriptions]:
        for key in ("ff_vis_char_idxs", "lf_vis_char_idxs"):
            for idx in getattr(shot, key, []) or []:
                if idx not in char_indices:
                    raise RuntimeError(f"shot {shot.idx} has missing character reference {idx}")

    raw_cameras = json.loads(camera_path.read_text(encoding="utf-8"))
    cameras = [Camera.model_validate(row) for row in raw_cameras]
    camera_indices = {row.idx for row in cameras}
    if not cameras or len(camera_indices) != len(cameras):
        raise RuntimeError("camera tree is empty or has duplicate camera indices")
    for camera in cameras:
        if any(idx not in range(8) for idx in camera.active_shot_idxs):
            raise RuntimeError(f"camera {camera.idx} references an unknown shot")
        if camera.parent_cam_idx is not None and camera.parent_cam_idx not in camera_indices:
            raise RuntimeError(f"camera {camera.idx} references a missing parent camera")
        if camera.parent_shot_idx is not None and camera.parent_shot_idx not in range(8):
            raise RuntimeError(f"camera {camera.idx} references an unknown parent shot")
    covered_shots = {idx for camera in cameras for idx in camera.active_shot_idxs}
    if covered_shots != set(range(8)):
        raise RuntimeError("camera tree does not cover all eight shots")
    capability_ok, capability_reasons = preflight_render_capability(
        base, video_capabilities=configured_video_generation_capabilities())
    if not capability_ok:
        raise RuntimeError("configured video capability preflight failed: " + "; ".join(capability_reasons))
    parent = {row.idx: row.parent_cam_idx for row in cameras}
    for start in camera_indices:
        seen = set()
        current = start
        while current is not None:
            if current in seen:
                raise RuntimeError("camera parent tree contains a cycle")
            seen.add(current)
            current = parent[current]
    for shot in descriptions:
        if shot.cam_idx not in camera_indices:
            raise RuntimeError(f"shot {shot.idx} references missing camera {shot.cam_idx}")

    events_path = workspace / "attempt" / "agent-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    successful_plans = [e for e in events if e.get("type") == "tool_result"
                        and (e.get("tool_result") or {}).get("name") == "vimax_narrative_planning"
                        and (e.get("tool_result") or {}).get("ok") is True]
    planning_starts = [e for e in events if e.get("type") == "tool_start"
                       and (e.get("tool") or {}).get("name") == "vimax_narrative_planning"]
    source_argument_check = all(
        not ({"script", "idea"} & set((e.get("tool") or {}).get("arguments") or {}))
        for e in planning_starts)
    if not source_argument_check:
        raise RuntimeError("Agent passed a replacement source instead of the bound session")
    if not successful_plans:
        raise RuntimeError("native Agent event stream has no successful narrative-planning result")
    ledger_path = workspace / "attempt" / "model-events.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    opens = [e for e in ledger if e.get("kind") == "open" and e.get("op") == "llm_chat"]
    if not any(e.get("role") == "outer_agent" for e in opens):
        raise RuntimeError("outer Agent request is missing from shared ledger")
    if not any(e.get("role") == "inner_langchain" for e in opens):
        raise RuntimeError("planning-node request is missing from shared ledger")
    if any(e.get("kind") == "open" and e.get("op") in
           {"image_generation", "video_create", "render"} for e in ledger):
        raise RuntimeError("media generation request was unexpectedly opened")
    media_files = [p.relative_to(workspace).as_posix() for p in working.rglob("*")
                   if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".mp4"}]
    if media_files:
        raise RuntimeError("planning-only run produced media files")

    checks.update({
        "native_schema_validation": True,
        "character_artifact_nonempty": True,
        "storyboard_count_and_order": True,
        "shot_decomposition_count_and_order": True,
        "camera_tree_schema_references_and_acyclic": True,
        "configured_video_capability_preflight_passed": capability_ok,
        "character_references_resolve": True,
        "native_planning_tool_returned_success": True,
        "agent_referenced_bound_session_without_copying_source": source_argument_check,
        "outer_and_internal_requests_recorded": True,
        "media_generation_absent": True,
        "automatic_semantic_equivalence_to_all_eight_supplied_actions": "not machine-proven; index/order and frozen script are proven",
    })
    return {"ok": all(value is True for key, value in checks.items()
                       if key != "automatic_semantic_equivalence_to_all_eight_supplied_actions"),
            "session_id": session_id, "working_dir": str(working.relative_to(workspace)),
            "storyboard_count": len(storyboard),
            "shot_description_count": len(descriptions),
            "camera_count": len(cameras), "character_count": len(characters),
            "native_plan_tool_success_count": len(successful_plans),
            "logical_llm_open_count": len(opens), "checks": checks,
            "media_files": media_files,
            "capability_preflight_reasons": capability_reasons}


if __name__ == "__main__":
    try:
        result = verify(Path(sys.argv[1]))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "error": str(exc)[:1000]}, ensure_ascii=False))
        raise SystemExit(1)
