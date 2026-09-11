"""Read-only CLI; heavy model imports are deferred until validation."""

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Describe implemented functionality only, not planned commands."""
    parser = argparse.ArgumentParser(
        prog="awc",
        description="AI Agent workload characterization.",
        epilog=(
            "Help, version and read-only JSON validation are implemented. "
            "Catalog inspection and AgentX sample checks are also available. No source-specific "
            "ingest CLI, collection or analysis pipeline; no files are written."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    validate = commands.add_parser("validate", help="validate one Trace IR JSON document", allow_abbrev=False)
    validate.add_argument("path", type=Path)
    inspect = commands.add_parser("inspect-source", help="stat one catalog locator without reading trace payloads", allow_abbrev=False)
    inspect.add_argument("source_id")
    inspect.add_argument("--catalog", type=Path, default=Path("data/catalog/sources.yaml"))
    agentx = commands.add_parser("check-agentx-samples", help="read-only regression of AX-7 and AX-SUB; no batch writes", allow_abbrev=False)
    agentx.add_argument("--catalog", type=Path, default=Path("data/catalog/sources.yaml"))
    agentx.add_argument("--samples", type=Path, default=Path("data/catalog/sample_candidates.yaml"))
    applied = commands.add_parser("check-applied-samples", help="read-only regression of AC-N2 and subtype smokes; no batch writes", allow_abbrev=False)
    applied.add_argument("--catalog", type=Path, default=Path("data/catalog/sources.yaml"))
    applied.add_argument("--samples", type=Path, default=Path("data/catalog/sample_candidates.yaml"))
    vw = commands.add_parser("check-videoweaver-samples", help="read-only regression of VW-LONG main run and auxiliary incomplete request; no batch writes", allow_abbrev=False)
    vw.add_argument("--catalog", type=Path, default=Path("data/catalog/sources.yaml"))
    vw.add_argument("--samples", type=Path, default=Path("data/catalog/sample_candidates.yaml"))
    macro = commands.add_parser("analyze-macro-pilot", help="P0-08/09 macro+coverage closed loop over pilot samples; read-only by default", allow_abbrev=False)
    macro.add_argument("--catalog", type=Path, default=Path("data/catalog/sources.yaml"))
    macro.add_argument("--selection", type=Path, default=Path("data/catalog/macro_pilot.yaml"))
    macro.add_argument("--output-dir", type=Path, default=None)
    prep = commands.add_parser("prepare-pilot", help="PREP-01 offline preparation: safe task projection, config checks, read-only host preflight; never executes anything", allow_abbrev=False)
    prep.add_argument("--record", type=Path, default=Path("data/raw/public/swebench_verified/78f471bf655a3137b2e8a75af1501690ec009ec3/django__django-16485/record.json"))
    prep.add_argument("--config", type=Path, default=Path("data/catalog/pilot_run_config.yaml"))
    prep.add_argument("--output-dir", type=Path, default=None, help="write report package under reports/preparation/ (exclusive create; no overwrite)")
    prep.add_argument("--skip-docker", action="store_true", help="skip the docker probe")
    prep.add_argument("--skip-preflight", action="store_true", help="offline checks only (no host probes)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Show help by default; argparse rejects unsupported operations."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "check-agentx-samples":
        import json
        import yaml
        from .adapters.agentx_checks import check_samples

        try:
            result = check_samples(arguments.catalog, arguments.samples)
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, RecursionError):
            print("INVALID: AgentX sample regression could not complete", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if arguments.command == "check-applied-samples":
        import json
        import yaml
        from .adapters.applied_checks import check_samples

        try:
            result = check_samples(arguments.catalog, arguments.samples)
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, RecursionError):
            print("INVALID: Applied sample regression could not complete", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if arguments.command == "check-videoweaver-samples":
        import json
        import yaml
        from .adapters.videoweaver_checks import check_samples

        try:
            result = check_samples(arguments.catalog, arguments.samples)
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, RecursionError):
            print("INVALID: VideoWeaver sample regression could not complete", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if arguments.command == "analyze-macro-pilot":
        import json as _json
        from .analyzers.analyze import run_pilot

        try:
            result = run_pilot(arguments.catalog, arguments.selection,
                               Path("data/catalog/sample_candidates.yaml"), arguments.output_dir)
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
            print(f"INVALID: macro pilot analysis failed: {exc}", file=sys.stderr)
            return 1
        print(_json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0 if result["status"] == "PASS" else 1
    if arguments.command == "prepare-pilot":
        import json as _json
        from .runners.preparation import prepare, PreparationError
        from .collectors.preflight import run_preflight

        try:
            if not arguments.config.is_file():
                print("INVALID: pilot run config not found (provide --config)", file=sys.stderr)
                return 1
            import yaml as _yaml
            config = _yaml.safe_load(arguments.config.read_text())
            result = prepare(arguments.record, config,
                             expected_instance_id="django__django-16485",
                             expected_sha256="762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a")
            preflight = None
            if not arguments.skip_preflight:
                preflight = run_preflight(Path(".").resolve(), docker=not arguments.skip_docker)
            import dataclasses as _dc
            def _to_jsonable(obj):
                if _dc.is_dataclass(obj) and not isinstance(obj, type):
                    return _to_jsonable(_dc.asdict(obj))
                if isinstance(obj, dict):
                    return {k: _to_jsonable(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [_to_jsonable(v) for v in obj]
                if isinstance(obj, Path):
                    return str(obj)
                return obj
            payload = {"preparation": _to_jsonable(_dc.asdict(result)),
                       "preflight": preflight,
                       "record_sha256": "762de270d1ce06ab23104a35322098178624865c886d7b0ddadf9044d8fec46a"}
            output = None
            if arguments.output_dir is not None:
                from .runners.report_writer import write_preparation_report
                output = write_preparation_report(arguments.output_dir, payload,
                                                  project_root=Path(".").resolve())
                payload["output"] = output
            print(_json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str))
            return 0
        except PreparationError as exc:
            print(f"INVALID: {exc}", file=sys.stderr)
            return 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"INVALID: preparation failed: {exc}", file=sys.stderr)
            return 1
    if arguments.command == "inspect-source":
        import json
        from .adapters.catalog import Catalog

        try:
            result = Catalog(arguments.catalog).inspect(arguments.source_id)
        except (OSError, ValueError, RecursionError):
            print("INVALID: cannot inspect catalog source", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "exists" else 1
    if arguments.command == "validate":
        from pydantic import ValidationError
        from .ir import validate_json

        try:
            document = validate_json(arguments.path.read_bytes())
        except ValidationError as error:
            # Never echo input values, which may contain sensitive trace payloads.
            for item in error.errors(include_input=False, include_context=False, include_url=False):
                location = ".".join(map(str, item["loc"])) or "document"
                print(f"INVALID {location}: {item['msg']}", file=sys.stderr)
            return 1
        except (OSError, ValueError, UnicodeError, RecursionError):
            print("INVALID: cannot read or parse JSON document", file=sys.stderr)
            return 1
        print(f"VALID schema={document.schema_version} profile={document.profile}")
        return 0
    parser.print_help()
    return 0
