from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent_runtime.session_index import SessionIndex
from interfaces.camera import Camera
from interfaces.character import CharacterInScene
from interfaces.shot_description import ShotBriefDescription, ShotDescription

WORKSPACE = Path("/evidence/workspace")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    session_data = json.loads((WORKSPACE / ".vimax/sessions.json").read_text())
    sessions = session_data.get("sessions", {})
    session_id = session_data.get("active_session_id")
    session = sessions.get(session_id) or {}
    expected_script = (WORKSPACE / "registered-script.txt").read_bytes()
    session_script = str(session.get("script", "")).encode("utf-8")
    script_artifact = (
        WORKSPACE / session.get("working_dir", "") / "script2video/script.txt"
    ).read_bytes()
    base = WORKSPACE / session.get("working_dir", "") / "script2video"
    characters = [
        CharacterInScene.model_validate(item)
        for item in json.loads((base / "characters.json").read_text())
    ]
    storyboard = [
        ShotBriefDescription.model_validate(item)
        for item in json.loads((base / "storyboard.json").read_text())
    ]
    descriptions = [
        ShotDescription.model_validate(json.loads(path.read_text()))
        for path in sorted(
            (base / "shots").glob("*/shot_description.json"),
            key=lambda item: int(item.parent.name),
        )
    ]
    cameras = [
        Camera.model_validate(item)
        for item in json.loads((base / "camera_tree.json").read_text())
    ]
    character_indices = {item.idx for item in characters}
    camera_indices = {item.idx for item in cameras}
    references_ok = all(
        index in character_indices
        for shot in [*storyboard, *descriptions]
        for field in ("ff_vis_char_idxs", "lf_vis_char_idxs")
        for index in getattr(shot, field, []) or []
    )
    camera_refs_ok = all(
        all(index in range(8) for index in camera.active_shot_idxs)
        and (camera.parent_cam_idx is None
             or camera.parent_cam_idx in camera_indices)
        and (camera.parent_shot_idx is None
             or camera.parent_shot_idx in range(8))
        for camera in cameras
    )
    covered_shots = {idx for camera in cameras
                     for idx in camera.active_shot_idxs}
    parent = {camera.idx: camera.parent_cam_idx for camera in cameras}
    acyclic = True
    for start in camera_indices:
        seen = set()
        current = start
        while current is not None:
            if current in seen:
                acyclic = False
                break
            seen.add(current)
            current = parent.get(current)
    descriptions_cam_refs_ok = all(
        shot.cam_idx in camera_indices for shot in descriptions
    )
    media_files = sorted(
        path.relative_to(WORKSPACE).as_posix()
        for path in (WORKSPACE / session.get("working_dir", "")).rglob("*")
        if path.is_file() and path.suffix.lower() in {
            ".png", ".jpg", ".jpeg", ".mp4", ".mov", ".webm"
        }
    )
    checks = {
        "single_fresh_session": len(sessions) == 1,
        "session_mode_script": session.get("planning_mode") == "script",
        "session_script_byte_identical": session_script == expected_script,
        "script_artifact_byte_identical": script_artifact == expected_script,
        "characters_native_schema_nonempty": bool(characters),
        "storyboard_native_schema_eight_ordered": (
            len(storyboard) == 8
            and [item.idx for item in storyboard] == list(range(8))
            and [item.is_last for item in storyboard] == [False] * 7 + [True]
        ),
        "shot_descriptions_native_schema_eight_ordered": (
            len(descriptions) == 8
            and [item.idx for item in descriptions] == list(range(8))
        ),
        "character_references_resolve": references_ok,
        "camera_tree_native_schema_nonempty": bool(cameras),
        "camera_tree_indices_unique": len(camera_indices) == len(cameras),
        "camera_references_resolve_and_cover_eight": (
            camera_refs_ok and covered_shots == set(range(8))
        ),
        "camera_tree_acyclic": acyclic,
        "shot_camera_references_resolve": descriptions_cam_refs_ok,
        "unsupported_variation_absent": not any(
            item.variation_type in {"medium", "large"}
            for item in descriptions
        ),
        "media_files_absent": not media_files,
    }
    result = {
        "session_id": session_id,
        "session_count": len(sessions),
        "session_mode": session.get("planning_mode"),
        "registered_script_sha256": sha(expected_script),
        "session_script_sha256": sha(session_script),
        "script_artifact_sha256": sha(script_artifact),
        "character_count": len(characters),
        "storyboard_count": len(storyboard),
        "storyboard_indices": [item.idx for item in storyboard],
        "shot_description_count": len(descriptions),
        "shot_description_indices": [item.idx for item in descriptions],
        "variation_types": [item.variation_type for item in descriptions],
        "camera_count": len(cameras),
        "camera_indices": sorted(camera_indices),
        "camera_covered_shots": sorted(covered_shots),
        "media_files": media_files,
        "checks": checks,
        "planning_contract": (
            "pass" if all(checks.values()) else "fail"
        ),
        "semantic_equivalence_to_story_actions":
            "not machine-proven; order/schema and the frozen source are verifiable",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
