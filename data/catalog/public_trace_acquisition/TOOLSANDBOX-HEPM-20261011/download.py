"""Fetch only the two pinned H-EPM ToolSandbox trace collections; never execute data."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "LISijia-dev/H-EPM"
COMMIT = "4ad8ad335fe63d365f4baf97df77e19055c79f1c"
PROJECT = Path("/home/lcq/agent_workload_characterization")
CATALOG = PROJECT / "data/catalog/public_trace_acquisition/TOOLSANDBOX-HEPM-20261011"
RAW = PROJECT / "data/raw/public/toolsandbox_hepm" / COMMIT
RUNS = {
    "H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_False_11_24_2025_09_02_55-7": "6321ce99eae340bf129ad877fc0a31ea6c6a289c",
    "H-EPM_GPT_4_1_user_gpt-4.1_summary_on_split_test_graph_True_05_19_2026_06_52_36": "0a71cc75bb5bb7103fba208acb7f8f5d22f90c19",
}
ALLOWED = {"conversation.json", "execution_context.json", "result_summary.json"}
LOCK = threading.Lock()
TRANSFERS = []
BODY_BYTES = 0
START = time.monotonic()
DEADLINE = START + 900
MAX_BYTES = 100 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def fetch(url):
    global BODY_BYTES
    for attempt in range(2):
        remaining = DEADLINE - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("acquisition_deadline")
        record = {"url": url, "attempt": attempt + 1, "response_body_bytes": 0}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trace-acquisition/1", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=min(30, remaining)) as response:
                record["status"] = response.status
                chunks = []
                while True:
                    if time.monotonic() >= DEADLINE:
                        raise TimeoutError("acquisition_deadline")
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    with LOCK:
                        BODY_BYTES += len(chunk)
                        record["response_body_bytes"] += len(chunk)
                        if BODY_BYTES > MAX_BYTES:
                            raise RuntimeError("acquisition_byte_limit")
                    chunks.append(chunk)
                data = b"".join(chunks)
                record["sha256"] = digest(data)
                return data
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            if isinstance(exc, urllib.error.HTTPError):
                record["status"] = exc.code
            if attempt == 1 or isinstance(exc, RuntimeError):
                raise
        finally:
            with LOCK:
                TRANSFERS.append(record)


def snapshot(name, url):
    data = fetch(url)
    path = CATALOG / "source_metadata" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return json.loads(data)


def acquire(item):
    remote = item["repository_path"]
    data = fetch("https://raw.githubusercontent.com/" + REPO + "/" + COMMIT + "/" + urllib.parse.quote(remote, safe="/"))
    if len(data) != item["expected_bytes"] or blob_sha(data) != item["git_blob_sha1"]:
        raise ValueError("source_blob_identity_mismatch")
    if remote.endswith(".json"):
        json.loads(data)
    path = RAW / remote
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    return {**item, "path": str(path.relative_to(PROJECT)), "bytes": len(data), "sha256": digest(data)}


def main():
    if RAW.exists() or (CATALOG / "manifest.json").exists():
        raise RuntimeError("existing_acquisition_refused")
    RAW.mkdir(parents=True)
    files, failures, groups = [], [], []
    status = "partial"
    try:
        commit = snapshot("commit.json", f"https://api.github.com/repos/{REPO}/commits/{COMMIT}")
        if commit["sha"] != COMMIT:
            raise ValueError("commit_mismatch")
        directories = snapshot("data_directory.json", f"https://api.github.com/repos/{REPO}/contents/ToolSandbox/data?ref={COMMIT}")
        indexed = {entry["name"]: entry for entry in directories}
        items = []
        for number, (run, tree_sha) in enumerate(RUNS.items()):
            if indexed[run]["sha"] != tree_sha or indexed[run]["type"] != "dir":
                raise ValueError("commit_tree_mismatch")
            tree = snapshot(f"run_{number}_tree.json", f"https://api.github.com/repos/{REPO}/git/trees/{tree_sha}?recursive=1")
            if tree.get("truncated") or tree["sha"] != tree_sha:
                raise ValueError("incomplete_or_mismatched_tree")
            selected = [entry for entry in tree["tree"] if entry["type"] == "blob" and Path(entry["path"]).name in ALLOWED]
            groups.append({"directory": run, "git_tree_sha1": tree_sha, "selected_files": len(selected), "expected_bytes": sum(entry["size"] for entry in selected)})
            for entry in selected:
                items.append({"repository_path": "ToolSandbox/data/" + run + "/" + entry["path"], "git_blob_sha1": entry["sha"], "expected_bytes": entry["size"]})
        root = snapshot("root_directory.json", f"https://api.github.com/repos/{REPO}/contents?ref={COMMIT}")
        toolsandbox = snapshot("toolsandbox_directory.json", f"https://api.github.com/repos/{REPO}/contents/ToolSandbox?ref={COMMIT}")
        for entry in root + toolsandbox:
            if entry["type"] == "file" and (entry["name"].lower() == "readme.md" or entry["name"].lower().startswith("license")):
                items.append({"repository_path": entry["path"], "git_blob_sha1": entry["sha"], "expected_bytes": entry["size"]})
        save_json(CATALOG / "selection.json", {"repository": REPO, "commit": COMMIT, "groups": groups, "files": items, "excluded": ["pretty_print.txt", "other repository content"]})
        print(f"Selected {len(items)} files, {sum(item['expected_bytes'] for item in items)} bytes", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(acquire, item): item for item in items}
            for future in concurrent.futures.as_completed(futures):
                item = futures[future]
                try:
                    files.append(future.result())
                except Exception as exc:
                    failures.append({"repository_path": item["repository_path"], "error_type": type(exc).__name__})
                completed = len(files) + len(failures)
                if completed % 50 == 0 or completed == len(items):
                    print(f"Completed {completed}/{len(items)}; saved={len(files)} failures={len(failures)}", flush=True)
        status = "complete" if not failures else "partial"
    except Exception as exc:
        failures.append({"stage": "metadata_or_selection", "error_type": type(exc).__name__})
    finally:
        save_json(CATALOG / "transfers.json", sorted(TRANSFERS, key=lambda entry: (entry["url"], entry["attempt"])))
        metadata = []
        for path in sorted(CATALOG.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                metadata.append({"path": str(path.relative_to(PROJECT)), "bytes": len(data), "sha256": digest(data)})
        save_json(CATALOG / "manifest.json", {
            "source": "third_party_ToolSandbox_H_EPM_adapted_experiments",
            "repository": REPO, "commit": COMMIT, "status": status,
            "groups": groups, "files": sorted(files, key=lambda entry: entry["path"]),
            "evidence_files": metadata, "failures": failures,
            "saved_payload_bytes": sum(item["bytes"] for item in files),
            "observed_response_body_bytes": BODY_BYTES, "recorded_request_attempts": len(TRANSFERS),
            "network_accounting_limit": "response bodies read by this downloader only; headers/TLS and redirects not separately counted",
            "wall_s": time.monotonic() - START,
            "executed_downloaded_content": False,
            "scope_note": "Two author-published collections only; not official Apple trace release; no resource or controlled-comparison claims.",
        })
    print(json.dumps({"status": status, "saved_files": len(files), "failures": len(failures), "saved_payload_bytes": sum(item["bytes"] for item in files)}), flush=True)
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
