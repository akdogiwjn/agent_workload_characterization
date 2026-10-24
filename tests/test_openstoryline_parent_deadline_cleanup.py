"""Narrow Docker regression: parent timeout must remove its workload and archive."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agent_workload_characterization.runners.container_runtime import (  # noqa: E402
    ContainerSpec, DockerCliRuntime,
)

IMAGE = "openstoryline-task:arm64-native-confirm-flow-03"
IMAGE_ID = "sha256:9a1e876c08c10d56c7959111af1a2afc382245e6657032c5da3dd195df5e8bd0"
EVIDENCE_ROOT = ROOT / "env/video/openstoryline/edit-pilot-02/preparation/real-native-short-04/preflight"


class ParentDeadlineCleanupTests(unittest.TestCase):
    def test_expired_execute_is_stopped_removed_and_archived(self):
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        run_id = f"short-deadline-regression-{uuid.uuid4().hex[:12]}"
        evidence = EVIDENCE_ROOT / run_id
        evidence.mkdir()
        output = evidence / "output"
        output.mkdir()
        mount = f"type=bind,src={output.resolve()},dst=/workspace/output"
        runtime = DockerCliRuntime(
            authorized=True, collection="OPENSTORYLINE-PARENT-DEADLINE-REGRESSION")
        spec = ContainerSpec(
            run_id=run_id, scope="openstoryline_agent", image=IMAGE,
            cwd="/workspace", cpu_limit="4", mem_limit="8g",
            network="none", mounts=[mount], pull="never")
        inspected = __import__("subprocess").run(
            ["docker", "--host", "unix:///var/run/docker.sock", "image", "inspect",
             IMAGE, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"],
            capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(inspected,
                         f"{IMAGE_ID} linux/arm64",
                         "pinned candidate image identity changed")

        handle = None
        record: dict = {"image": {"tag": IMAGE, "id": IMAGE_ID},
                        "network": "none", "cpus": 4, "memory": "8g",
                        "timeout_s": 0.5, "run_id": run_id}
        try:
            handle = runtime.start(spec, deadline=time.monotonic() + 30)
            record["container_id"] = handle.container_id
            result = runtime.execute(
                handle,
                "sleep 3; printf late > /workspace/output/late-marker",
                timeout_s=0.5, output_limit=1000)
            record["exec"] = {key: value for key, value in result.items()
                              if key != "output"}
            self.assertTrue(result.get("timed_out"), result)
        finally:
            if handle is not None:
                runtime.stop(handle, timeout_s=15)
                record["removal"] = runtime.verify_removal(handle, timeout_s=15)
            record["archive_written_after_cleanup"] = True
            record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            (evidence / "timeout-regression.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertEqual(record.get("removal"), "removed")
        self.assertTrue((evidence / "timeout-regression.json").is_file())
        time.sleep(3.1)
        self.assertFalse((output / "late-marker").exists(),
                         "timed-out workload wrote after container cleanup")
        record["late_marker_absent_after_3s"] = True
        (evidence / "timeout-regression.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
