"""Shared host-side ASR cache contract for offline test and official launchers."""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path("/home/lcq/agent_workload_characterization")
CONTRACT_PATH = PROJECT_ROOT / "env/video/openstoryline/OPENSTORYLINE-ENV-01/asr-cache-contract.json"


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def host_cache_root() -> Path:
    return (PROJECT_ROOT / contract()["host_cache_root_relative"]).resolve()


def validate_host_cache() -> list[dict]:
    spec = contract()
    root = host_cache_root()
    if not root.is_dir():
        raise RuntimeError(f"registered ASR cache directory is absent: {root}")
    records = []
    for model, rel_dir in spec["model_dirs"].items():
        for filename in spec["required_files"][model]:
            path = root / "models" / rel_dir / filename
            try:
                path.relative_to(root)
                with path.open("rb") as stream:
                    stat = os.fstat(stream.fileno())
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"registered ASR cache file unavailable: {path}: {exc}") from exc
            if not path.is_file() or stat.st_size <= 0:
                raise RuntimeError(f"registered ASR cache file is not a nonempty regular file: {path}")
            records.append({"model": model, "path": str(path), "bytes": stat.st_size, "readable": True})
    return records


def docker_asr_args() -> list[str]:
    spec = contract()
    mount = spec["container_cache_mount"]
    model_root = spec["container_model_root"]
    args = ["--mount", f"type=bind,src={host_cache_root()},dst={mount},readonly"]
    env = {
        "OPENSTORYLINE_ASR_MODEL_ROOT": model_root,
        "OPENSTORYLINE_ASR_CONTRACT_PATH": "/opt/openstoryline/asr-cache-contract.json",
        "OPENSTORYLINE_ASR_DIR": str(Path(model_root) / spec["model_dirs"]["asr"]),
        "OPENSTORYLINE_ASR_VAD_DIR": str(Path(model_root) / spec["model_dirs"]["vad"]),
        "OPENSTORYLINE_ASR_PUNC_DIR": str(Path(model_root) / spec["model_dirs"]["punc"]),
        **spec["offline_environment"],
    }
    for name, value in env.items():
        args.extend(["--env", f"{name}={value}"])
    return args


if __name__ == "__main__":
    result = validate_host_cache()
    print(json.dumps({"cache_root": str(host_cache_root()), "files": result}, indent=2))
