#!/usr/bin/env python3
"""Host-only official-oracle smoke for the isolated scorer; never mounted to Agent."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 7:
        raise SystemExit("usage: oracle_validation.py VENV_PY JUDGE ENTRY SOURCE GOLDEN SUMMARY")
    venv, judge, entry, source, golden, summary_path = map(Path, sys.argv[1:7])
    judge_sha = hashlib.sha256(judge.read_bytes()).hexdigest()
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="pilot03-official-oracle-") as td:
        tmp = Path(td)
        oracle_mp4 = tmp / "oracle-output.mp4"
        oracle_cuts = tmp / "oracle-cuts.json"
        oracle_cuts.write_bytes(golden.read_bytes())
        build_code = r'''
import json, runpy, sys
from pathlib import Path
judge = runpy.run_path(sys.argv[1])
gt_path, source, output = map(Path, sys.argv[2:5])
gt = json.loads(gt_path.read_text())
ranges = judge["_parse_ranges"](gt, str(gt.get("unit", "ms")), float(gt.get("fps", 0) or 0))
judge["_reconstruct_remainder"](source, ranges, output, include_audio=True)
'''
        subprocess.run([str(venv), "-c", build_code, str(judge), str(golden),
                        str(source), str(oracle_mp4)], check=True, timeout=180,
                       capture_output=True, text=True)
        reward = tmp / "reward.json"
        reward_txt = tmp / "reward.txt"
        status = tmp / "status.json"
        completed = subprocess.run([
            str(venv), str(entry), "--judge", str(judge), "--source-mp4", str(source),
            "--output-mp4", str(oracle_mp4), "--output-cuts", str(oracle_cuts),
            "--gt-cuts", str(golden), "--reward-json", str(reward),
            "--reward-txt", str(reward_txt), "--status-json", str(status),
            "--expected-venv", str(venv.parent.parent), "--judge-sha256", judge_sha,
            "--timeout-s", "180",
        ], capture_output=True, text=True, timeout=210)
        result = json.loads(status.read_text()) if status.is_file() else {}
        summary = {
            "schema": "video-use-pilot03-official-oracle-validation-v1",
            "scope": "isolated official scorer chain validation; oracle is not an Agent result",
            "source_sha256": source_sha,
            "official_judge_sha256": judge_sha,
            "verifier_executable": str(venv),
            "wrapper_process_returncode": completed.returncode,
            "official_judge_returncode": result.get("official_judge_returncode"),
            "evaluation_status": result.get("evaluation_status"),
            "evaluation_complete": result.get("evaluation_complete"),
            "oracle_score_not_agent": result.get("task_score"),
            "checks": result.get("checks"),
            "versions": result.get("versions"),
            "oracle_video_retained": False,
            "golden_or_oracle_exposed_to_agent": False,
        }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["evaluation_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
