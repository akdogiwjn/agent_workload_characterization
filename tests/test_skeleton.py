"""Offline skeleton tests; no legacy data or optional libraries required."""

import contextlib
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

import agent_workload_characterization as package
from agent_workload_characterization.cli import main


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"


class PackageTests(unittest.TestCase):
    def test_version_matches_distribution(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(package.__version__, metadata["project"]["version"])
        self.assertEqual(metadata["project"]["dependencies"], ["pydantic>=2.13,<3", "PyYAML>=6.0,<7"])

    def test_console_entry_point_is_callable(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        module, attribute = metadata["project"]["scripts"]["awc"].split(":")
        self.assertIs(getattr(importlib.import_module(module), attribute), main)

    def test_direct_entry_point(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([]), 0)
        self.assertIn("read-only JSON validation", output.getvalue())


class CLITests(unittest.TestCase):
    def run_python(self, *arguments):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SOURCE)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with tempfile.TemporaryDirectory(prefix="awc-cli-test-") as directory:
            result = subprocess.run(
                [sys.executable, "-B", *arguments],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(list(Path(directory).iterdir()), [])
        return result

    def run_cli(self, *arguments):
        return self.run_python("-m", "agent_workload_characterization", *arguments)

    def test_module_help(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: awc", result.stdout)
        self.assertIn("no files are written", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_no_arguments_shows_help(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--version", result.stdout)

    def test_version(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"awc {package.__version__}")

    def test_unknown_option_fails(self):
        result = self.run_cli("--does-not-exist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_unimplemented_command_fails(self):
        result = self.run_cli("ingest")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_abbreviated_option_fails(self):
        result = self.run_cli("--ver")
        self.assertEqual(result.returncode, 2)

    def test_import_is_quiet_and_lightweight(self):
        result = self.run_python(
            "-c",
            "import sys; import agent_workload_characterization; "
            "import agent_workload_characterization.__main__; "
            "assert not ({'polars', 'pandas', 'pyarrow', 'agent_trace_analysis'} "
            "& set(sys.modules))",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
