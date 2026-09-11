"""SMOKE-01 credential launcher: safe read of the approved provider entry.

Reads the user-designated OpenCode config ONCE, ONLY after the SMOKE-01
approval, selecting the single 火山AI网关 + deepseek-v4-flash entry, and
spawns the smoke subprocess with a RESTRICTED environment containing only:
PILOT_API_BASE / PILOT_API_KEY + minimal PATH/locale/ssl + the offline
cost-map and retry pins. Credentials stay in process memory/environment;
never printed, hashed, persisted, or placed in argv.

No raw config or parse-exception text is ever echoed: failures produce
fixed, safe error messages. JSONC is parsed with the same comment-safe
in-memory stripper validated in the earlier audited rounds (no regex
comment-stripping that could alter values).

This module contains NO network access. The child it launches performs the
one approved request (guarded by smoke.py's own double-flag gate).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VENV_PY = PROJECT_ROOT / ".venvs" / "mini-swe-agent-2.4.6-env01" / "bin" / "python"
DEFAULT_CONFIG = Path("/home/lcq/.config/opencode/opencode.json")

PROVIDER_NAME = "火山AI网关"
MODEL_KEY = "deepseek-v4-flash"

_URL_USERINFO_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@\s]+@")
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class LauncherError(RuntimeError):
    """Fixed-message failure; never includes config content or raw errors."""


def _strip_jsonc(text: str) -> str:
    """Comment-safe JSONC stripping (same algorithm audited in earlier rounds):
    only removes // and /* */ outside string literals; never touches values."""
    out, i, n = [], 0, len(text)
    in_str, esc = False, False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
        else:
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
            elif ch == "/" and i + 1 < n and text[i + 1] == "/":
                while i < n and text[i] != "\n":
                    i += 1
            elif ch == "/" and i + 1 < n and text[i + 1] == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
            else:
                out.append(ch)
                i += 1
    return "".join(out)


def load_credentials(config_path: Path | None = None,
                     provider_name: str = PROVIDER_NAME,
                     model_key: str = MODEL_KEY) -> tuple[str, str]:
    """Return (api_base, api_key) for the single approved provider+model entry.

    ONLY call after SMOKE-01 approval. Raises LauncherError with fixed
    messages on any ambiguity/missing/malformed input. Never logs values.
    """
    path = config_path or DEFAULT_CONFIG
    try:
        raw = path.read_bytes()
    except OSError:
        raise LauncherError("E_CONFIG_UNREADABLE")
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError:
        try:
            cfg = json.loads(_strip_jsonc(raw.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise LauncherError("E_CONFIG_MALFORMED")
    if not isinstance(cfg, dict):
        raise LauncherError("E_CONFIG_MALFORMED")

    providers = cfg.get("provider")
    if not isinstance(providers, dict):
        raise LauncherError("E_PROVIDER_MISSING")
    provider = providers.get(provider_name)
    if not isinstance(provider, dict):
        raise LauncherError("E_PROVIDER_MISSING")

    models = provider.get("models")
    if not isinstance(models, dict) or model_key not in models:
        raise LauncherError("E_MODEL_MISSING")
    # uniqueness: exact key match only (display-name aliases not consumed)
    entry = models[model_key]

    options = provider.get("options")
    if not isinstance(options, dict):
        raise LauncherError("E_CREDENTIALS_MISSING")
    api_base = options.get("baseURL")
    api_key = options.get("apiKey")
    if not isinstance(api_base, str) or not api_base.strip():
        raise LauncherError("E_CREDENTIALS_MISSING")
    if not isinstance(api_key, str) or not api_key.strip():
        raise LauncherError("E_CREDENTIALS_MISSING")
    # reference-style credentials: ${VAR}, {env:VAR}, {ENV:VAR}, env:VAR
    stripped = api_key.strip()
    if stripped.startswith(("${", "{env:", "{ENV:", "env:", "{secret:", "{op:")) or ":" in stripped[:8]:
        # supported reference: {env:VAR} / {ENV:VAR} — resolve from os.environ
        import re as _re
        m = _re.match(r"^\{env:([A-Za-z_][A-Za-z0-9_]*)\}$", stripped, _re.IGNORECASE)
        if m:
            var = m.group(1)
            resolved = os.environ.get(var)
            if not resolved or not resolved.strip():
                raise LauncherError("E_ENV_VAR_EMPTY")
            api_key = resolved
            if api_key.strip().startswith(("${", "{", "env:")):
                raise LauncherError("E_CREDENTIAL_REFERENCE_UNSUPPORTED")
        else:
            raise LauncherError("E_CREDENTIAL_REFERENCE_UNSUPPORTED")

    if not _URL_SCHEME_RE.match(api_base):
        raise LauncherError("E_BASE_NOT_ABSOLUTE_URL")
    if not api_base.lower().startswith("https://"):
        raise LauncherError("E_BASE_NOT_HTTPS")
    if _URL_USERINFO_RE.match(api_base):
        raise LauncherError("E_BASE_USERINFO_REJECTED")

    # model display-name check: entry['name'] must match the approved model
    # (case-insensitive compare of the stem)
    display = entry.get("name") if isinstance(entry, dict) else None
    if not isinstance(display, str) or display.strip().lower() != "deepseek-v4-flash":
        raise LauncherError("E_MODEL_ENTRY_MISMATCH")

    return api_base, api_key


def build_restricted_env(api_base: str, api_key: str) -> dict[str, str]:
    """Minimal child environment: no proxies, no unrelated credentials."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": os.environ.get("HOME", "/home/lcq"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt"),
        "PYTHONPATH": str(PROJECT_ROOT / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        # offline cost map + retry pins (approved switches)
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT": "1",
        # credentials (in-memory env of the child only)
        "PILOT_API_BASE": api_base,
        "PILOT_API_KEY": api_key,
    }
    # never inherit any proxy variables from the parent environment;
    # an APPROVED explicit proxy may be set below (user authorization
    # recorded in the SMOKE-01 delivery: local proxy 127.0.0.1:22111)
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        env.pop(var, None)
    approved_proxy = os.environ.get("SMOKE_APPROVED_PROXY", "")
    if approved_proxy:
        env["https_proxy"] = approved_proxy
        env["HTTPS_PROXY"] = approved_proxy
    return env


def launch_smoke(config_path: Path, result_dir: Path,
                 api_base: str, api_key: str,
                 deadline_s: int = 30) -> tuple[int, dict | None]:
    """Spawn the ONE approved smoke request with the restricted environment.

    The child's stdout is the smoke record JSON (sanitized by smoke.py);
    stderr captured. No retry, no loop — a single Popen.
    """
    cmd = [str(VENV_PY), "-B", "-m",
           "agent_workload_characterization.runners.smoke",
           "--config", str(config_path),
           "--result-dir", str(result_dir),
           "--execute", "--i-approve-the-smoke"]
    env = build_restricted_env(api_base, api_key)
    # overall parent budget: query deadline + child spawn overhead margin
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                          timeout=deadline_s + 25, cwd=str(PROJECT_ROOT))
    # The smoke child prints diagnostic lines (e.g. litellm banners) BEFORE
    # the final record JSON, and the record itself is multi-line pretty JSON —
    # single-line parsing cannot find it. Parse by locating the LAST top-level
    # JSON object instead: scan for a line that starts a valid JSON object and
    # attempt json.loads on the remainder of stdout from that point.
    record = _extract_last_json_object(proc.stdout)
    return proc.returncode, record


def _extract_last_json_object(stdout: str) -> dict | None:
    """Find the last parseable JSON object in mixed-line stdout.

    Handles both single-line and pretty-printed (multi-line) records that
    follow arbitrary diagnostic output. Returns None when nothing parses.
    """
    if not stdout:
        return None
    # try whole output first (fast path when stdout is only the record)
    try:
        obj = json.loads(stdout)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # scan candidate start positions from the end; the record is the LAST
    # object, so a '{' closer to the end wins
    lines = stdout.splitlines(keepends=True)
    for start in range(len(lines) - 1, -1, -1):
        if not lines[start].lstrip().startswith("{"):
            continue
        candidate = "".join(lines[start:])
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            # object may be followed by trailing text; try trimming
            # trailing non-JSON lines one at a time
            trimmed = candidate
            for end in range(len(lines), start, -1):
                trimmed = "".join(lines[start:end])
                try:
                    obj = json.loads(trimmed)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    continue
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="smoke-launcher",
        description="SMOKE-01 credential launcher (reads the approved config entry once and spawns the single approved request)",
        allow_abbrev=False)
    parser.add_argument("--config", type=Path,
                        default=Path("data/catalog/smoke_01_config.yaml"))
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--batch", required=True,
                        help="UTC batch id, e.g. 20260912T000000Z")
    args = parser.parse_args(argv)

    if not VENV_PY.is_file():
        print("LAUNCHER_ERROR: E_VENV_MISSING", file=sys.stderr)
        return 1
    try:
        api_base, api_key = load_credentials()
    except LauncherError as exc:
        print(f"LAUNCHER_ERROR: {exc}", file=sys.stderr)
        return 1

    result_dir = args.result_dir if args.result_dir.is_absolute() else \
        PROJECT_ROOT / args.result_dir
    rc, record = launch_smoke(args.config, result_dir, api_base, api_key)
    # print only the sanitized record (smoke.py guarantees no credentials)
    if record is not None:
        safe = {k: v for k, v in record.items()
                if k in ("run_id", "ok", "outcome", "usage", "cost",
                         "cost_status", "error", "duration_ms", "deadline_s",
                         "retries", "max_tokens", "semantics", "result_path",
                         "finish_reason", "request_started_before_kill",
                         "model", "request_model_id")}
        print(json.dumps(safe, ensure_ascii=False, indent=2))
    else:
        print("LAUNCHER_ERROR: E_NO_RECORD (child produced no record; "
              "treat as outcome-unknown, possibly sent/billed)", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
