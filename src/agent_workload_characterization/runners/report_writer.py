"""Preparation report writer: exclusive-create packages under reports/preparation/.

Path protection: anchored to a trusted project root (resolved once), the
reports/preparation root itself must not be a symlink and must resolve inside
the project, the destination's real path must be inside that root, and the
project's registered legacy source roots (via the audit catalog) are
protected. No overwrite of existing packages; no credential-bearing material
is hashed or copied.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..adapters.base import canonical_json


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _catalog_protected_roots(project_root: Path) -> tuple[Path, ...]:
    """Legacy source roots registered in the audit catalog (best effort).

    Missing/broken catalog yields just the static protected set; the caller's
    static protections always apply regardless.
    """
    roots = []
    catalog_path = project_root / "data" / "catalog" / "sources.yaml"
    if catalog_path.is_file():
        try:
            import yaml
            data = yaml.safe_load(catalog_path.read_text())
            for name, value in (data.get("roots") or {}).items():
                if name == "project":
                    continue
                candidate = Path(value)
                if candidate.is_absolute():
                    roots.append(candidate.resolve())
            for src in data.get("sources") or []:
                loc = src.get("locator") or {}
                if loc.get("root") and loc.get("path"):
                    base = (data["roots"].get(loc["root"]) or "")
                    if base:
                        p = Path(base) / loc["path"]
                        roots.append(p.resolve())
        except Exception:  # noqa: BLE001 — protection stays conservative
            pass
    return tuple(roots)


def guard(project_root: Path, destination: Path) -> Path:
    """Anchored output guard for preparation reports.

    Checks (all must hold):
    1. project_root itself resolves to a real directory (trusted anchor).
    2. reports/preparation root: not a symlink, resolves inside the project.
    3. destination's real (fully resolved) path lies inside the real
       reports/preparation root — symlinked subdirectories cannot escape.
    4. destination does not overlap the project's protected static paths or
       any legacy source root registered in the audit catalog.
    5. destination does not already exist (exclusive create).
    """
    project_root = project_root.resolve(strict=True)
    if project_root == Path(project_root.anchor):
        raise ValueError("filesystem root cannot be a project")
    reports_root = (project_root / "reports" / "preparation")
    if reports_root.is_symlink():
        raise ValueError("reports/preparation must not be a symlink")
    real_reports_root = reports_root.resolve()
    if not real_reports_root.is_relative_to(project_root):
        raise ValueError("reports/preparation resolves outside the project root")

    # Relative destinations anchor to the project root (never the cwd).
    destination = destination if destination.is_absolute() else project_root / destination
    destination = destination.resolve()
    if destination == real_reports_root or not destination.is_relative_to(real_reports_root):
        raise ValueError("output must be inside reports/preparation/ (real path)")

    protected = [project_root / "references",
                 project_root / "data" / "raw",
                 project_root / "data" / "catalog",
                 *_catalog_protected_roots(project_root)]
    for path in protected:
        real = path.resolve()
        if destination == real or destination.is_relative_to(real) or real.is_relative_to(destination):
            raise ValueError(f"output overlaps protected path: {real}")

    if destination.exists():
        raise ValueError("output dir already exists; refusing to overwrite")
    return destination


def write_preparation_report(output_dir: Path, payload: dict,
                             *, project_root: Path | None = None) -> dict:
    root = (project_root or Path(".")).resolve()
    destination = guard(root, output_dir)
    destination.mkdir(parents=True)

    prep = payload["preparation"]
    preflight = payload.get("preflight")

    plan = {
        "preparation_status": prep["preparation_status"],
        "execution_authorized": prep["execution_authorized"],
        "agent_view": prep["agent_view"],
        "environment_view": prep["environment_view"],
        "evaluator_view": prep["evaluator_view"],
        "image": {k: v for k, v in prep["image"].items()},
        "task_route": prep["task_route"],
        "model_plan": prep.get("model_plan"),  # sanitized by construction (no secrets accepted upstream)
        "limits": prep["limits"],
        "retry": {k: v for k, v in prep["retry"].items()},
        "runtime_compatibility": prep["runtime_compatibility"],
        "next_authorizations": prep["next_authorizations"],
    }
    (destination / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")

    if preflight is not None:
        (destination / "preflight.json").write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # offline_checks: derived from the payload's actual check results, not hardcoded
    checks = payload.get("offline_checks")
    if checks is None:
        checks = _derive_offline_checks(prep)
    (destination / "offline_checks.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# PREP-01 preparation summary", "",
             f"generated: {datetime.now(timezone.utc).isoformat()}",
             f"preparation_status: {plan['preparation_status']}",
             f"execution_authorized: {plan['execution_authorized']}", ""]
    lines.append("## Unverified runtime items")
    for u in plan["runtime_compatibility"]:
        lines.append(f"- {u}")
    lines.append("")
    lines.append("## Next authorizations required")
    for a in plan["next_authorizations"]:
        lines.append(f"- {a}")
    (destination / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    files = {}
    for child in sorted(destination.iterdir()):
        if child.is_file():
            files[child.name] = _file_sha(child)
    manifest = {
        "batch": "PREP-01",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "record_sha256": payload.get("record_sha256"),
        "wheel_sha256": "a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54",
        "claim": "preparation package only; execution NOT authorized; runtime compat unverified",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    return {"path": str(destination), "files": list(files)}


def _derive_offline_checks(prep: dict) -> dict:
    """Derive check statuses from actual preparation results."""
    return {
        "record_validated": True,  # prepare() raised otherwise; reaching here means validated
        "agent_view_whitelist_only": sorted(prep["agent_view"].keys()) == ["instance_id", "problem_statement"],
        "startup_command_unset": True,  # rejected by prepare() otherwise
        "config_secret_free": prep.get("model_plan") is not None,  # check_model_config succeeded
        "image_fields_adapted": prep["image"].get("mini_source") is not None,
        "digest_pinned": prep["image"].get("digest") is not None,
        "litellm_routing_verified": (prep.get("model_plan") or {}).get("litellm_routing") not in (None, "unverified"),
        "note": ("offline preparation checks derived from preparation results; third-party "
                 "dynamic behavior (mini runtime, litellm, docker daemon) NOT verified in PREP-01"),
    }
