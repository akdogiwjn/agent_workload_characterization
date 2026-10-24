#!/usr/bin/env python3
"""Create a non-self-hashing inventory for the native-entry repair evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path("/home/lcq/agent_workload_characterization")
HERE = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01"
EXTRA = [
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/openstoryline_task_entry.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/offline_fake_model.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/agent.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/hooks/node_interceptors.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/register_tools.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/request_ledger.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/mcp/sampling_handler.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/src/open_storyline/nodes/node_manager.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/source/tests/test_native_entry_repair.py",
    "env/video/openstoryline/OPENSTORYLINE-ENV-01/Dockerfile.native-entry-repair-07",
    "env/video/openstoryline/edit-pilot-02/runtime/openstoryline_pilot_entry.py",
    "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/validation-03/input/source.mp4",
    "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/validation-03/output/output.mp4",
    "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/validation-03/output/cuts.json",
    "env/video/openstoryline/edit-pilot-02/preparation/native-entry-repair-01/validation-03/validation-report.json",
]


def digest(path: Path) -> dict:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return {"bytes": size, "sha256": h.hexdigest()}


def main() -> None:
    files = {path.resolve() for path in HERE.rglob("*") if path.is_file()
             and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    files.update((ROOT / rel).resolve() for rel in EXTRA)
    files.discard((HERE / "manifest.json").resolve())
    rows = [{"path": str(path.relative_to(ROOT)), **digest(path)}
            for path in sorted(files, key=lambda item: str(item))]
    manifest = {
        "schema": "openstoryline-native-entry-repair-manifest-v1",
        "manifest_self_hashed": False,
        "upstream": {"path": "references/repos/FireRed-OpenStoryline",
                     "commit": "c9e945215586f45c12a61c1951ee9a8e9c43a027",
                     "modified": False},
        "final_image": json.loads((HERE / "image-identity-07.json").read_text()),
        "files": rows,
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False,
                                                       indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"file_count": len(rows), "bytes": sum(row["bytes"] for row in rows),
                      "manifest": str(HERE / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
