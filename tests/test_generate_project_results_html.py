import hashlib
import json
import tempfile
import unittest
import copy
import re
from unittest.mock import patch
from html.parser import HTMLParser
from pathlib import Path

from scripts.generate_project_results_html import (
    HISTORY_DRIFT, PACKAGES, REPORT_FILES, ROOT, check_historical_inputs,
    coding_evidence_projection, coding_phase_projection, coding_resource_svg,
    declared_file, load_json, load_lines, manifest_entries, render_site,
    hash_matches, sample_projection, sha256,
    office02_card, office02_call_projection, office02_sample_projection,
    office02_task_plots, office02_timeline,
    check_projection_input, office02_provenance_notice,
)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.srcs = []
        self.tables = []
        self._table = self._row = self._cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.hrefs.append(attrs["href"])
        if attrs.get("src"):
            self.srcs.append(attrs["src"])
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("th", "td") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self._cell is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


class ProjectResultsHtmlTests(unittest.TestCase):
    def _source_snapshot(self):
        paths = set()
        for name, rel in PACKAGES.items():
            package = ROOT / rel
            manifest_path = package / "manifest.json"
            paths.add(manifest_path)
            manifest = load_json(manifest_path)
            for item in manifest_entries(manifest, "outputs"):
                p = declared_file(ROOT, package, item["path"])
                if p.is_file():
                    paths.add(p)
            for filename in REPORT_FILES[name]:
                p = package / filename
                if p.is_file():
                    paths.add(p)
        for row in load_lines(ROOT / PACKAGES["office"] / "per_run.jsonl"):
            paths.add(ROOT / "data/raw/generated/DOCOPS-OFFICE-REPEAT-01" / row["run_id"] / "summary.json")
        word = load_json(ROOT / PACKAGES["word"] / "summary.json")
        for row in word["runs"]:
            paths.add(ROOT / "data/raw/generated" / row["collection"] / row["run_id"] / "summary.json")
        coding_batch = ROOT / "reports/resource/P1-12/repeats/CODING-REPEAT-01/batch"
        paths.update({coding_batch / "manifest.json", coding_batch / "summary.json"})
        for attempt in load_json(coding_batch / "summary.json")["attempts"]:
            run_dir = Path(attempt["run_dir"])
            raw_manifest_path = run_dir / "manifest.json"
            paths.add(raw_manifest_path)
            paths.update(run_dir / rel for rel in load_json(raw_manifest_path).get("files", {}))
        v1 = ROOT / "reports/html/PROJECT-RESULTS-v1"
        for version in ("PROJECT-RESULTS-v1", "PROJECT-RESULTS-v2", "PROJECT-RESULTS-v3", "PROJECT-RESULTS-v4"):
            package = ROOT / "reports/html" / version
            if package.is_dir():
                paths.update(p for p in package.rglob("*") if p.is_file())
        paths.update({ROOT / "project_state.json", ROOT / "docs/current_task.md"})
        new_manifest = load_json(ROOT / PACKAGES["office02"] / "manifest.json")
        paths.update(ROOT / e["path"] for e in manifest_entries(new_manifest, "inputs"))
        for row in load_lines(ROOT / PACKAGES["office02"] / "per_run.jsonl"):
            folder = (ROOT / row["source"]).parent
            paths.update(folder / e["path"] for e in load_json(folder / "manifest.json")["outputs"])
        paths.update((ROOT / "reports/resource/DOCOPS-MEASUREMENT-VALIDATE-01").glob("*.json"))
        return {p: (p.stat().st_size, sha256(p)) for p in paths}

    def test_cpu_projection_uses_real_differences_and_keeps_gaps(self):
        raw = {"samples": [
            {"t_monotonic_ns": 1_000_000_000, "container": {"cpu_usage_usec": 100, "mem_current_bytes": 0}},
            {"t_monotonic_ns": 2_000_000_000, "container": {"cpu_usage_usec": 600_100, "mem_current_bytes": 1048576}},
            {"t_monotonic_ns": 3_000_000_000, "container": {"cpu_usage_usec": 20, "mem_current_bytes": None}},
            {"t_monotonic_ns": 4_000_000_000, "container": {"cpu_usage_usec": 20, "mem_current_bytes": 0}},
        ], "events": []}
        p = sample_projection(raw)["points"]
        self.assertIsNone(p[0]["cpu_cores"])
        self.assertAlmostEqual(p[1]["cpu_cores"], 0.6)
        self.assertEqual(p[1]["memory_mib"], 1)
        self.assertIsNone(p[2]["cpu_cores"])  # counter reset is a gap
        self.assertIsNone(p[2]["memory_mib"])
        self.assertEqual(p[3]["memory_mib"], 0)  # observed zero stays zero

    def test_historical_reference_path_mapping_and_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="reference-map-test-") as td:
            root = Path(td)
            target = root / HISTORY_DRIFT["coding"]["analysis/tool_timing.py"]
            target.parent.mkdir(parents=True)
            target.write_bytes(b"registered reference\n")
            manifest = {"reference_files": [{
                "path": "analysis/tool_timing.py", "bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }]}
            result = check_historical_inputs(root, manifest, "coding", {
                "analysis/tool_timing.py": HISTORY_DRIFT["coding"]["analysis/tool_timing.py"]})[0]
            self.assertEqual(result["status"], "match")
            target.write_bytes(b"changed reference\n")
            result = check_historical_inputs(root, manifest, "coding", {
                "analysis/tool_timing.py": HISTORY_DRIFT["coding"]["analysis/tool_timing.py"]})[0]
            self.assertEqual(result["status"], "mismatch")
            self.assertEqual(result["manifest_path"], "analysis/tool_timing.py")
            self.assertEqual(result["resolved_project_path"], HISTORY_DRIFT["coding"]["analysis/tool_timing.py"])

    def test_registered_input_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="hash-check-") as td:
            path = Path(td) / "samples.json"
            path.write_bytes(b"registered bytes")
            self.assertTrue(hash_matches(path, sha256(path), path.stat().st_size))
            self.assertFalse(hash_matches(path, "0" * 64, path.stat().st_size))
            self.assertFalse(hash_matches(path, sha256(path), path.stat().st_size + 1))

    @staticmethod
    def _evidence_point(scope_id, kind, t, cpu, mem, cpu_status="ok_ns_converted_to_usec",
                        memory_status="ok"):
        return {"scope": scope_id, "scope_kind": kind, "t_monotonic_ns": t,
                "cpu_usage_usec": cpu, "mem_current_bytes": mem,
                "read_status": {"cpuacct.usage": cpu_status,
                                "memory.usage_in_bytes": memory_status}}

    def test_nested_evidence_structure_projects_real_cpu_and_memory_curves(self):
        raw = {"scopes": {}, "evidence": {}}
        for kind, scope_id, cpu_step, mem_base in (
                ("agent_container", "run-agent-sandbox", 600_000, 1_048_576),
                ("verifier_container", "run-verifier", 2_000_000, 10_485_760)):
            raw["scopes"][scope_id] = {"scope_kind": kind, "cpu_core_seconds": 99,
                                       "memory_sampled_max_bytes": mem_base * 10}
            raw["evidence"][scope_id] = {"scope": scope_id, "scope_kind": kind,
                "interval_target_s": .5, "boundary_start": self._evidence_point(scope_id, kind, 0, 0, 0),
                "samples": [self._evidence_point(scope_id, kind, 1_000_000_000, cpu_step, mem_base)],
                "boundary_end": self._evidence_point(scope_id, kind, 2_000_000_000,
                                                     cpu_step * 2, mem_base * 2),
                "sample_gaps_ns": [1_000_000_000], "notes": []}
        projection = coding_evidence_projection(raw)
        self.assertEqual(set(projection["scopes"]), {"agent_container", "verifier_container"})
        phases = coding_phase_projection([], projection["common_origin_ns"], 2)
        for scope in projection["scopes"].values():
            cpu_svg = coding_resource_svg(scope, "cpu", phases)
            mem_svg = coding_resource_svg(scope, "memory", phases)
            self.assertIn('class="cpu-interval"', cpu_svg)
            self.assertIn('class="memory-point"', mem_svg)
        self.assertAlmostEqual(projection["scopes"]["agent_container"]["cpu_intervals"][0]["average_cores"], .6)
        self.assertAlmostEqual(projection["scopes"]["verifier_container"]["cpu_intervals"][0]["average_cores"], 2.0)
        self.assertEqual(projection["scopes"]["agent_container"]["memory_points"][1]["memory_current_mib"], 1)
        self.assertEqual(projection["scopes"]["verifier_container"]["memory_points"][1]["memory_current_mib"], 10)
        # Aggregate CPU/memory summaries are kept by scope and are never summed into the curves.
        self.assertEqual(projection["scopes"]["agent_container"]["aggregate"]["cpu_core_seconds"], 99)
        self.assertEqual(projection["scopes"]["verifier_container"]["aggregate"]["cpu_core_seconds"], 99)

    def test_missing_reads_time_repeats_and_counter_resets_break_cpu_intervals(self):
        kind, scope_id = "agent_container", "gap-agent-sandbox"
        values = [
            self._evidence_point(scope_id, kind, 0, 0, 0),
            self._evidence_point(scope_id, kind, 1_000_000_000, 1_000_000, 1_048_576),
            self._evidence_point(scope_id, kind, 2_000_000_000, None, 0, "read_error", "ok"),
            self._evidence_point(scope_id, kind, 3_000_000_000, 3_000_000, 3_145_728),
            self._evidence_point(scope_id, kind, 3_000_000_000, 4_000_000, 4_194_304),
            self._evidence_point(scope_id, kind, 4_000_000_000, 3_000_000, 5_242_880),
            self._evidence_point(scope_id, kind, 5_000_000_000, 4_000_000, 6_291_456),
        ]
        other = "gap-verifier"
        raw = {"scopes": {scope_id: {"scope_kind": kind},
                          other: {"scope_kind": "verifier_container"}},
               "evidence": {scope_id: {"scope": scope_id, "scope_kind": kind,
                    "boundary_start": values[0], "samples": values[1:],
                    "boundary_end": self._evidence_point(scope_id, kind, 6_000_000_000, 5_000_000, 7_340_032),
                    "sample_gaps_ns": []},
                    other: {"scope": other, "scope_kind": "verifier_container",
                    "boundary_start": self._evidence_point(other,"verifier_container",7_000_000_000,0,0),
                    "samples": [], "boundary_end": self._evidence_point(other,"verifier_container",8_000_000_000,0,0),
                    "sample_gaps_ns": []}}}
        # The start is part of the boundary, not duplicated in evidence.samples.
        raw["evidence"][scope_id]["boundary_start"] = values[0]
        raw["evidence"][scope_id]["samples"] = values[1:]
        projection = coding_evidence_projection(raw)["scopes"][kind]
        self.assertEqual(len(projection["cpu_intervals"]), 3)  # start→first, reset epoch→next→end
        counts = projection["counts"]
        self.assertEqual(counts["cpu_invalid_read_status"], 1)
        self.assertEqual(counts["cpu_nonincreasing_time"], 1)
        self.assertEqual(counts["cpu_counter_decrease"], 1)
        self.assertTrue(any(p["memory_current_bytes"] == 0 for p in projection["memory_points"]))
        svg = coding_resource_svg(projection, "cpu", [])
        self.assertEqual(svg.count('class="cpu-interval"'), 3)
        self.assertEqual(projection["counts"]["memory_valid_sample_points"], 6)

    def test_actual_generation_entry_builds_all_pages_and_manifest(self):
        with tempfile.TemporaryDirectory(prefix="project-results-test-", dir=ROOT) as td:
            output = Path(td) / "site"
            before = self._source_snapshot()
            result = render_site(ROOT, output)
            self.assertEqual(before, self._source_snapshot())
            self.assertEqual(result["detail_runs"], 29)
            self.assertEqual(set(result["pages"]), {"index.html", "public-traces.html", "local-measurements.html", "run-details.html"})
            manifest = json.loads((output / "manifest.json").read_text())
            verification = json.loads((output / "verification.json").read_text())
            self.assertEqual(manifest["schema"], "project-results-html-v5")
            self.assertEqual((verification["coding_detail_count"], verification["office_detail_count"],
                              verification["word_detail_count"]), (9, 9, 2))
            self.assertEqual(verification["coding_raw_manifest_verified_file_count"], 81)
            self.assertEqual(verification["coding_detail_integrity"], "verified")
            self.assertEqual(verification["coding_detail_errors"], [])
            self.assertEqual(len(verification["coding_sampling"]), 9)
            self.assertTrue(all(set(x["scopes"]) == {"agent_container", "verifier_container"}
                                for x in verification["coding_sampling"]))
            for run in verification["coding_sampling"]:
                raw_doc = load_json(ROOT / run["samples_source"])
                for kind, scope in run["scopes"].items():
                    raw_evidence = raw_doc["evidence"][scope["scope_id"]]
                    self.assertGreater(scope["saved_sample_count"], 0, (run["run_id"], kind))
                    self.assertEqual(scope["saved_sample_count"], len(raw_evidence["samples"]))
                    self.assertEqual(scope["sample_timestamps_ns"],
                                     [x.get("t_monotonic_ns") for x in raw_evidence["samples"]])
                    self.assertGreater(scope["effective_cpu_interval_count"], 0, (run["run_id"], kind))
                    self.assertGreater(scope["effective_memory_sample_point_count"], 0, (run["run_id"], kind))
                    self.assertEqual(scope["curve_status"], "generated")
            self.assertEqual(verification["office_table_column_count"], 10)
            self.assertEqual(verification['office02']['source_provenance_status'], 'PARTIAL')
            drift = [r for r in verification['office02']['input_checks'] if not r['match']]
            self.assertEqual({r['path'] for r in drift}, {'docs/trace_contract.md',
                'src/agent_workload_characterization/collectors/semantic_recorder.py'})
            self.assertTrue(all(r['kind'] == 'historical_source_context' for r in drift))
            self.assertNotIn("manifest.json", [Path(x["path"]).name for x in manifest["outputs"]])
            for entry in manifest["outputs"]:
                path = ROOT / entry["path"]
                self.assertEqual(path.stat().st_size, entry["bytes"])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
            overview = (output / "index.html").read_text()
            self.assertIn('provenance-drift', overview)
            self.assertIn('PARTIAL', overview)
            synthesis=load_json(ROOT / PACKAGES["synthesis"] / "evidence_matrix.json")
            self.assertEqual(verification["research_question_count"], 6)
            self.assertEqual(verification["next_task_status"], "proposed_not_started")
            self.assertFalse(synthesis["next_task"]["execution_authorized"])
            self.assertEqual([r["rq"] for r in synthesis["matrix"]],
                             ["RQ1", "RQ2", "RQ3", "RQ4", "RQ5", "RQ6"])
            parser_overview=Links(); parser_overview.feed(overview)
            rq_table=next(t for t in parser_overview.tables if t[0][0] == "研究问题")
            self.assertEqual(len(rq_table), 7)
            for row, rq in zip(rq_table[1:], synthesis["matrix"]):
                self.assertEqual(row, [rq["rq"]+"："+rq["question"], rq["status"],
                                       rq["allowed_claim"], rq["missing"]])
            for finding in synthesis["findings"]:
                self.assertIn(finding["title"], overview)
            office_source=load_json(ROOT / PACKAGES["office"] / "summary.json")
            self.assertEqual(synthesis["local_measurements"]["office"]["tools"],
                             office_source["agent_tool_call_count"])
            for task, stats in synthesis["local_measurements"]["office"]["task_stats"].items():
                for metric, values in stats["metrics"].items():
                    for field in ("n", "median", "iqr"):
                        self.assertEqual(values[field], office_source["task_summaries"][task]["metrics"][metric][field])
            coding_source=load_json(ROOT / PACKAGES["coding"] / "summary.json")
            for task, stats in synthesis["local_measurements"]["coding"]["per_task"].items():
                for metric, values in stats.items():
                    self.assertEqual(values, coding_source["per_task"][task][metric])
            self.assertNotIn("综合 evidence matrix 是 2026-10-07 历史快照", overview)
            self.assertIn("TOOL-OBSERVABILITY-01", overview)
            local = (output / "local-measurements.html").read_text()
            details = (output / "run-details.html").read_text()
            new_source = load_json(ROOT / PACKAGES["office02"] / "summary.json")
            new_rows = load_lines(ROOT / PACKAGES["office02"] / "per_run.jsonl")
            new_check = verification["office02"]
            self.assertEqual(new_check["totals"], new_source["totals"])
            self.assertEqual(new_check["by_task"], new_source["by_task"])
            self.assertEqual(new_check["detail_count"], len(new_source["explicit_run_ids"]))
            self.assertEqual(details.count('class="call-timeline"'), len(new_rows))
            self.assertEqual(details.count('class="office02-resource"'), 2*len(new_rows))
            self.assertEqual(details.count('class="failed-call"'), new_source["totals"]["bootstrap_ok_false"])
            self.assertEqual(len(set(re.findall(r'<article class="run-panel" id="([^"]+)"', details))), 29)
            old_ids = {x["run_id"] for x in load_json(ROOT / "reports/html/PROJECT-RESULTS-v4/verification.json")["detail_runs"]}
            self.assertTrue(old_ids.issubset({x["run_id"] for x in verification["detail_runs"]}))
            self.assertFalse(verification["single_excel_validation"]["included_in_repeat_stats"])
            self.assertIn("单次验证结果", local)
            for row, shown in zip(new_rows, new_check["runs"]):
                self.assertIn(row["run_id"], details)
                self.assertIn(f'#run-{20+new_rows.index(row)}', local)
                self.assertEqual(shown["run_id"], row["run_id"])
                raw = load_json(ROOT / row["source"])
                events = load_lines((ROOT / row["source"]).parent / "agent/events.jsonl")
                projection = office02_call_projection(row, events)
                self.assertEqual(shown["timeline"], projection)
                self.assertEqual(shown["sample_count"], len(raw["samples"]))
                self.assertGreater(shown["valid_cpu_intervals"], 0)
                self.assertGreater(shown["valid_memory_points"], 0)
                projected = office02_sample_projection(raw)
                self.assertEqual(shown["phase_boundaries"], projected["phases"])
                self.assertEqual(shown["valid_cpu_intervals"], len(projected["curve_scope"]["cpu_intervals"]))
                self.assertEqual(shown["valid_memory_points"], len(projected["curve_scope"]["memory_points"]))
                self.assertIn('shared_task_container agent_container', details)
                self.assertIn(row["last_agent_tool_terminal"]["event_id"], details)
                self.assertTrue(shown["image_retention"])
                for call in projection["calls"]:
                    self.assertIn(f'data-event-id="{call["event_id"]}"', details)
                for filename in ("summary.json", "measurement.json", "agent/events.jsonl"):
                    rel = str(Path(row["source"]).parent / filename)
                    self.assertIn(rel, {e["path"] for e in manifest["inputs"]})
            new_tables = Links(); new_tables.feed(local)
            statistics = [t for t in new_tables.tables if t[0][:3] == ["指标", "单位", "原始点"]]
            self.assertEqual(len(statistics), 3)
            for group, shown in zip(new_source["by_task"].values(), statistics):
                metric = group["metrics"]["attempt_wall_s"]
                self.assertEqual(shown[1][2], ', '.join(str(p["value"]).rstrip('0').rstrip('.') for p in metric["points"]))
                self.assertEqual(float(shown[1][5]), metric["median"])
                self.assertAlmostEqual(float(shown[1][6]), metric["iqr"], places=6)
            coding_raw_file_roles = {"coding_raw_manifest_verified_output", "coding_raw_sample_or_stage_input"}
            self.assertEqual(sum(x["role"] in coding_raw_file_roles for x in manifest["inputs"]), 81)
            self.assertIn('class="phase-timeline"', details)
            self.assertIn("agent_end", details)
            self.assertIn("verifier_end", details)
            self.assertNotIn("未保存可绘制的逐样本 cgroup 时间序列", details)
            self.assertIn("evidence.&lt;scope_id&gt;.samples", local)
            self.assertIn("逐点值来自", details)
            self.assertEqual(details.count('class="coding-resource"'), 36)
            self.assertGreater(details.count('class="cpu-interval"'), 1000)
            self.assertGreater(details.count('class="memory-point"'), 2000)
            local_parser = Links(); local_parser.feed(local)
            office_table = next(t for t in local_parser.tables if t and t[0][:3] == ["任务", "n", "三次操作顺序"])
            self.assertEqual(len(office_table[0]), 10)
            excel = next(row for row in office_table[1:] if row[0] == "Excel")
            self.assertEqual(excel[3].split("；")[0], "7, 6, 8")
            self.assertEqual(excel[4].split("；")[0], "6, 5, 5")
            self.assertEqual(excel[5].split("；")[0], "50.3, 32.34, 34.47")
            self.assertEqual(excel[6].split("；")[0], "7.069852, 6.006818, 5.969424")
            self.assertEqual(excel[7].split("；")[0], "64.51, 75.12, 72.64")
            self.assertIn("160.75", excel[9])
            self.assertIn("37", local)  # corrected Agent tool count
            self.assertIn("bootstrap", local)
            self.assertIn("未登记工具时间顺序", details)
            self.assertIn("range", details.lower()) if "range" in details.lower() else self.assertIn("区间平均", details)
            self.assertNotIn("Gantt", details)
            self.assertNotIn("api_key_sha256", overview + local + details)
            self.assertNotIn("<script src=\"https://", overview + local + details)
            self.assertNotIn("https://cdn", overview + local + details)
            self.assertIn("G2 / G3-R 未通过", overview)
            verification_text = (output / "verification.json").read_text()
            self.assertIn("historical_reference_checks", verification_text)
            self.assertIn("historical_status_snapshot_checks", verification_text)
            input_paths = {x["path"] for x in manifest["inputs"]}
            self.assertIn("references/repos/agentcgroup/analysis/tool_timing.py", input_paths)
            self.assertIn("references/repos/agentcgroup/analysis/compute_active_time.py", input_paths)
            self.assertIn("local_archive/20261016-full-docs/methodology.md", input_paths)
            parser = Links()
            parser.feed(overview + local + details)
            for src in parser.srcs:
                self.assertTrue((output / src).is_file(), src)
            for html_file in output.glob("*.html"):
                parser = Links(); parser.feed(html_file.read_text())
                for href in parser.hrefs:
                    if href.startswith(("http:", "https:", "mailto:", "#")):
                        continue
                    target = (html_file.parent / href.split("#", 1)[0]).resolve()
                    self.assertTrue(target.exists(), f"broken link {html_file.name}: {href}")
                    if '#' in href and target.suffix == '.html':
                        anchor = href.split('#', 1)[1]
                        self.assertIn(f'id="{anchor}"', target.read_text())


    def test_office02_card_and_source_points_change_with_input(self):
        source = load_json(ROOT / PACKAGES["office02"] / "summary.json")
        changed = copy.deepcopy(source)
        changed["totals"]["logical_requests"] += 100
        self.assertNotEqual(office02_card(source), office02_card(changed))
        stat = next(iter(changed["by_task"].values()))["metrics"]["attempt_wall_s"]
        stat["points"][0]["value"] = 123.456
        stat["median"] = 88.88
        changed_html = office02_task_plots(changed)
        self.assertIn("123.456", changed_html)
        self.assertIn("88.88", changed_html)
        self.assertNotEqual(office02_task_plots(source), changed_html)

    def test_office02_real_event_ids_not_position_pairing_and_final_return(self):
        row = load_lines(ROOT / PACKAGES["office02"] / "per_run.jsonl")[0]
        events = load_lines((ROOT / row["source"]).parent / "agent/events.jsonl")
        result = office02_call_projection(row, events)
        # Reordering the records does not fabricate different ID associations.
        self.assertEqual(result, office02_call_projection(row, list(reversed(events))))
        last = row["last_agent_tool_terminal"]
        self.assertTrue(any(c["event_id"] == last["event_id"] and c["end_ns"] == last["end_ns"]
                            for c in result["calls"]))
        self.assertEqual(len(result["finish_ns"]), row["action_counts"]["finish"])
        without_last = [e for e in events if not (e["event_id"] == last["event_id"] and e["status"] != "open")]
        with self.assertRaisesRegex(ValueError, "pairing mismatch"):
            office02_call_projection(row, without_last)
        duplicate = events + [next(e for e in events if e["event_id"] == last["event_id"])]
        with self.assertRaisesRegex(ValueError, "pairing mismatch"):
            office02_call_projection(row, duplicate)

    def test_office02_timeline_escapes_names_and_preserves_failed_bootstrap(self):
        row = next(r for r in load_lines(ROOT / PACKAGES["office02"] / "per_run.jsonl")
                   if r["bootstrap_error_tool_count"])
        events = load_lines((ROOT / row["source"]).parent / "agent/events.jsonl")
        projection = office02_call_projection(row, events)
        self.assertEqual(sum(c["ok"] is False for c in projection["calls"]), row["bootstrap_error_tool_count"])
        projection["calls"][0]["name"] = '<script>"&'
        text = office02_timeline(row, projection)
        self.assertIn('&lt;script&gt;&quot;&amp;', text)
        self.assertNotIn('<script>', text)
        self.assertEqual(text.count('class="failed-call"'), row["bootstrap_error_tool_count"])
        self.assertEqual(text.count('class="terminal-marker"'), len(projection["calls"]))
        self.assertIn('class="finish-marker"', text)

    def test_office02_resource_units_gaps_and_scope(self):
        def sample(t, cpu, mem, status="ok_ns_converted_to_usec", scope="agent_container"):
            return {"t_monotonic_ns": t, "clock_domain": "system_monotonic", "role": "sample", "container": {
                "scope": scope, "scope_kind": scope, "cpu_usage_usec": cpu, "mem_current_bytes": mem,
                "read_status": {"cpuacct.usage": status, "memory.usage_in_bytes": "ok"}}}
        raw = {"samples": [sample(0, 0, 0), sample(1_000_000_000, 600_000, 1048576),
                           sample(2_000_000_000, 1_200_000, 0, "read_error"),
                           sample(3_000_000_000, 1_800_000, 1048576),
                           sample(3_000_000_000, 2_000_000, 1048576),
                           sample(4_000_000_000, 100, 1048576),
                           sample(5_000_000_000, 900_000, 1048576, scope="verifier_container")], "events": []}
        points = office02_sample_projection(raw)["points"]
        self.assertAlmostEqual(points[1]["cpu_cores"], .6)
        self.assertEqual(points[1]["memory_mib"], 1)
        self.assertEqual(points[2]["memory_mib"], 0)
        for i in (0, 2, 3, 4, 6):
            self.assertIsNone(points[i]["cpu_cores"])
        # Duplicate time is a gap; a later valid reading starts a fresh CPU epoch.
        self.assertIsNone(points[4]["memory_mib"])
        self.assertIsNone(points[5]["cpu_cores"])
        self.assertIsNone(points[6]["memory_mib"])

    def test_source_context_drift_is_visible_not_a_hash_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root / 'docs/live.md'
            p.parent.mkdir(); p.write_bytes(b'current')
            entry = {'path': 'docs/live.md', 'bytes': 3, 'sha256': hashlib.sha256(b'old').hexdigest()}
            result = check_projection_input(root, entry, 'inputs')
            self.assertFalse(result['match'])
            self.assertEqual(result['status'], 'current_source_drift')
            self.assertEqual(result['expected_sha256'], entry['sha256'])
            self.assertIn('PARTIAL', office02_provenance_notice({'input_checks': [result]}))
            p.unlink()
            self.assertEqual(check_projection_input(root, entry, 'inputs')['status'], 'historical_source_unavailable')

    def test_analysis_code_and_raw_evidence_mismatch_still_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, section in [('scripts/analyze.py', 'analysis_code'),
                                 ('data/raw/generated/run/summary.json', 'inputs'),
                                 ('env/pilot/frozen-identity.json', 'inputs')]:
                p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
                    check_projection_input(root, {'path': rel, 'bytes': 3, 'sha256': '0' * 64}, section)

    def test_office02_hash_conflict_rejects_actual_entry_without_outputs(self):
        with tempfile.TemporaryDirectory(prefix="office02-html-hash-", dir=ROOT) as td:
            fixture = Path(td) / "source"
            fixture.mkdir()
            source = ROOT / PACKAGES["office02"]
            for name in REPORT_FILES["office02"]:
                (fixture / name).write_bytes((source / name).read_bytes())
            manifest = load_json(fixture / "manifest.json")
            manifest["inputs"][0]["sha256"] = "0" * 64
            (fixture / "manifest.json").write_text(json.dumps(manifest))
            output = Path(td) / "site"
            with patch.dict(PACKAGES, {"office02": str(fixture.relative_to(ROOT))}):
                with self.assertRaisesRegex(ValueError, "REPEAT-02 source hash mismatch"):
                    render_site(ROOT, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
