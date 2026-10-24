#!/usr/bin/env python3
"""Run the unmodified AgenticVBench judge in the pinned verifier venv.

This adapter reports infrastructure/evaluation completeness separately from
the judge's reward. It does not change the judge or any scoring thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


def _write_status(path: Path, status: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n")


def _versions() -> dict:
    result = {"python": sys.version.split()[0], "executable": sys.executable,
              "prefix": sys.prefix}
    try:
        import numpy
        import scipy
        import skimage
        from skimage.metrics import structural_similarity  # noqa: F401
        result["numpy"] = numpy.__version__
        result["scipy"] = scipy.__version__
        result["scikit_image"] = skimage.__version__
    except Exception as exc:
        result["dependency_error"] = f"{type(exc).__name__}: {exc}"
    for name in ("ffmpeg", "ffprobe"):
        try:
            proc = subprocess.run([name, "-version"], capture_output=True,
                                  text=True, timeout=10)
            result[name] = proc.stdout.splitlines()[0] if proc.returncode == 0 else None
        except Exception:
            result[name] = None
    return result


def _source_has_audio(source: Path) -> bool:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1",
             str(source)], capture_output=True, text=True, timeout=20)
        return proc.returncode == 0 and "audio" in proc.stdout
    except Exception:
        return False


def classify_result(judge_rc: int, emitted: dict | None, gt: dict,
                    source_has_audio: bool) -> dict:
    """Classify judge execution, completed checks, and task score independently."""
    reward = emitted.get("reward") if isinstance(emitted, dict) else None
    details = emitted.get("details") if isinstance(emitted, dict) else None
    details = details if isinstance(details, dict) else {}
    reason = str(details.get("reason") or "")
    audio_required = str(gt.get("audio", "required")) != "skip" and source_has_audio

    if judge_rc != 0:
        evaluation = "evaluation_error"
        issue = f"official judge exited with code {judge_rc}"
    elif not isinstance(emitted, dict) or reward is None:
        evaluation = "evaluation_error"
        issue = "official judge did not emit a parseable reward object"
    elif any(token in reason.lower() for token in (
            "ssim sampling failed", "ffmpeg reconstruct failed", "verifier error")):
        evaluation = "evaluation_error"
        issue = reason
    elif reason.startswith("no output.mp4") or reason.startswith("source.mp4 missing"):
        evaluation = "partial"
        issue = reason
    else:
        required_fields = ("per_cut", "duration_pass", "duration_diff_s")
        missing = [key for key in required_fields if key not in details]
        if missing:
            evaluation, issue = "partial", "missing judge fields: " + ", ".join(missing)
        elif details.get("ssim") is None:
            evaluation, issue = "partial", "SSIM was not evaluated"
        elif audio_required and details.get("audio_xcorr") is None:
            evaluation, issue = "partial", "required audio correlation was not evaluated"
        else:
            evaluation, issue = "complete", None

    ssim_status = ("evaluated" if details.get("ssim") is not None else
                   "not_evaluated" if evaluation == "partial" and "SSIM" in str(issue) else
                   "error" if evaluation == "evaluation_error" else "unknown")
    if not audio_required:
        audio_status = "not_evaluated"
    elif details.get("audio_xcorr") is not None:
        audio_status = "evaluated"
    elif evaluation == "evaluation_error":
        audio_status = "unknown"
    else:
        audio_status = "not_evaluated" if evaluation == "partial" else "unknown"

    return {
        "evaluation_status": evaluation,
        "evaluation_complete": evaluation == "complete",
        "evaluation_issue": issue,
        "official_judge_returncode": judge_rc,
        "judge_emitted_reward": reward,
        "task_score": reward if evaluation == "complete" else None,
        "checks": {
            "cut_ranges": "evaluated" if "per_cut" in details else "unknown",
            "duration": "evaluated" if "duration_pass" in details else "unknown",
            "ssim": ssim_status,
            "audio_xcorr": audio_status,
        },
    }


def run(args: argparse.Namespace) -> tuple[int, dict]:
    expected = Path(args.expected_venv).resolve()
    actual = Path(sys.prefix).resolve()
    versions = _versions()
    base = {"schema": "video-use-pilot03-verifier-result-v1",
            "verifier_python": sys.executable, "verifier_prefix": sys.prefix,
            "expected_verifier_prefix": str(expected), "versions": versions,
            "judge_path": str(Path(args.judge).resolve()),
            "judge_sha256": args.judge_sha256}
    judge_path = Path(args.judge).resolve()
    actual_judge_sha = (hashlib.sha256(judge_path.read_bytes()).hexdigest()
                        if judge_path.is_file() else None)
    base["actual_judge_sha256"] = actual_judge_sha
    if actual_judge_sha != args.judge_sha256:
        result = {**base, "actual_judge_sha256": actual_judge_sha,
                  "evaluation_status": "evaluation_error",
                  "evaluation_complete": False,
                  "evaluation_issue": "judge hash mismatch or judge file missing",
                  "official_judge_returncode": None, "judge_emitted_reward": None,
                  "task_score": None, "checks": {}}
        _write_status(Path(args.status_json), result)
        return 20, result
    if actual != expected or sys.prefix == sys.base_prefix:
        result = {**base, "evaluation_status": "evaluation_error",
                  "evaluation_complete": False,
                  "evaluation_issue": "wrong Python interpreter; dedicated verifier venv required",
                  "official_judge_returncode": None, "judge_emitted_reward": None,
                  "task_score": None, "checks": {}}
        _write_status(Path(args.status_json), result)
        return 20, result
    if versions.get("dependency_error") or not versions.get("ffmpeg") or not versions.get("ffprobe"):
        result = {**base, "evaluation_status": "evaluation_error",
                  "evaluation_complete": False,
                  "evaluation_issue": versions.get("dependency_error") or "ffmpeg/ffprobe unavailable",
                  "official_judge_returncode": None, "judge_emitted_reward": None,
                  "task_score": None, "checks": {}}
        _write_status(Path(args.status_json), result)
        return 20, result

    reward_json = Path(args.reward_json).resolve()
    reward_json.parent.mkdir(parents=True, exist_ok=True)
    reward_json.unlink(missing_ok=True)
    reward_txt = Path(args.reward_txt).resolve()
    reward_txt.unlink(missing_ok=True)
    command = [sys.executable, str(Path(args.judge).resolve()),
               "--source-mp4", str(Path(args.source_mp4).resolve()),
               "--output-mp4", str(Path(args.output_mp4).resolve()),
               "--output-cuts", str(Path(args.output_cuts).resolve()),
               "--gt-cuts", str(Path(args.gt_cuts).resolve()),
               "--reward-json", str(reward_json), "--reward-txt", str(reward_txt)]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=args.timeout_s)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        result = {**base, "evaluation_status": "evaluation_error",
                  "evaluation_complete": False, "evaluation_issue": "official judge timed out",
                  "official_judge_returncode": proc.returncode,
                  "judge_emitted_reward": None, "task_score": None,
                  "checks": {"cut_ranges": "unknown", "duration": "unknown",
                             "ssim": "unknown", "audio_xcorr": "unknown"},
                  "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:],
                  "process_group_terminated": True}
        _write_status(Path(args.status_json), result)
        return 20, result

    try:
        emitted = json.loads(reward_json.read_text()) if reward_json.is_file() else None
    except (OSError, json.JSONDecodeError):
        emitted = None
    try:
        gt = json.loads(Path(args.gt_cuts).read_text())
    except (OSError, json.JSONDecodeError):
        gt = {}
    classified = classify_result(proc.returncode, emitted, gt,
                                 _source_has_audio(Path(args.source_mp4)))
    result = {**base, **classified, "stdout_tail": stdout[-2000:],
              "stderr_tail": stderr[-2000:]}
    _write_status(Path(args.status_json), result)
    return (0 if classified["evaluation_complete"] else 20), result


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("judge", "source-mp4", "output-mp4", "output-cuts", "gt-cuts",
                 "reward-json", "reward-txt", "status-json", "expected-venv",
                 "judge-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--timeout-s", type=float, default=600)
    args = parser.parse_args()
    code, result = run(args)
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
