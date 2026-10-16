"""Read back this acquisition without importing or executing downloaded content."""
import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT = Path("/home/lcq/agent_workload_characterization")
CATALOG = Path(__file__).parent


def main():
    manifest_path = CATALOG / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    selection = json.loads((CATALOG / "selection.json").read_bytes())
    assert manifest["status"] == "complete" and not manifest["failures"]
    assert {item["repository_path"] for item in selection["files"]} == {item["repository_path"] for item in manifest["files"]}
    counts, scenario_sets, summary_counts = Counter(), {}, {}
    for item in manifest["files"] + manifest["evidence_files"]:
        data = (PROJECT / item["path"]).read_bytes()
        assert len(data) == item["bytes"], item["path"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
        if "git_blob_sha1" in item:
            assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["git_blob_sha1"], item["path"]
        if "repository_path" not in item:
            continue
        path = Path(item["repository_path"])
        counts[path.name] += 1
        if path.suffix != ".json":
            continue
        value = json.loads(data)
        run = path.parts[2]
        if path.name == "conversation.json":
            assert isinstance(value, list), item["path"]
            scenario_sets.setdefault(run, set()).add(path.parent.name)
            assert (PROJECT / item["path"]).with_name("execution_context.json").is_file()
        elif path.name == "execution_context.json":
            assert isinstance(value, dict), item["path"]
        elif path.name == "result_summary.json":
            results = value["per_scenario_results"]
            summary_counts[run] = len(results)
    assert len(scenario_sets) == 2
    for run, scenarios in scenario_sets.items():
        assert len(scenarios) == 207 and summary_counts[run] == 207
    sets = list(scenario_sets.values())
    result = {
        "status": "PASS",
        "acquisition_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "payload_files_verified": len(manifest["files"]),
        "acquisition_evidence_files_verified": len(manifest["evidence_files"]),
        "files_by_basename": dict(counts),
        "trajectories": counts["conversation.json"],
        "dataset_local_scenario_keys": len(sets[0] | sets[1]),
        "scenario_keys_shared_between_groups": len(sets[0] & sets[1]),
        "per_group_trajectory_counts": {run: len(values) for run, values in scenario_sets.items()},
        "saved_payload_bytes": manifest["saved_payload_bytes"],
        "scope_note": "Scenario keys are local identifiers, not proven independent tasks. Third-party adapted experiments; no execution or resource claims.",
    }
    with (CATALOG / "verification.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
