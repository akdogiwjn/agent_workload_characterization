#!/usr/bin/env python3
"""VIDEO-USE-EDIT-PILOT-02 entry point, reusing the bounded pilot lifecycle."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import video_use_edit_pilot_01 as runner  # noqa: E402

TASK = "VIDEO-USE-EDIT-PILOT-02"
RUN_ID = "20261021T0937Z-video-use-edit-02"
IMAGE = "video-use-task:arm64-codex-bailian-v2"
IMAGE_ID = "sha256:faf015927f9a71c820c82abc11d1a996037d7d684e6e149f2787908ad422c20f"
PLAN_ROOT = ROOT / "env/video/video-use" / TASK
IDENTITY = PLAN_ROOT / "frozen-identity.json"

runner.TASK = TASK
runner.RUN_ID = RUN_ID
runner.IMAGE = IMAGE
runner.IMAGE_ID = IMAGE_ID
runner.PLAN_ROOT = PLAN_ROOT
runner.RAW_ROOT = ROOT / "data/raw/generated" / TASK / RUN_ID
runner.REPORT_ROOT = ROOT / "reports/resource" / TASK
runner._IDENTITY_FILE = IDENTITY


def frozen_inputs() -> list[Path]:
    return [
        Path(__file__),
        Path(runner.__file__),
        ROOT / "tests/test_video_use_edit_pilot_02.py",
        ROOT / "env/video/video-use/codex-bailian-integration-02/Dockerfile",
        ROOT / "env/video/video-use/codex-bailian-integration-01/config.toml",
        ROOT / "env/video/video-use/source/helpers/transcribe.py",
        ROOT / "env/video/video-use/source/helpers/render.py",
        ROOT / "env/video/video-use/source-manifest.json",
        runner.TASK_PATH / "steps/solve/instruction.md",
        runner.INPUT,
    ]


runner.frozen_inputs = frozen_inputs


def main() -> int:
    """Start this invocation's budget clock immediately before shared execution."""
    runner.PROCESS_START_NS = time.monotonic_ns()
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
