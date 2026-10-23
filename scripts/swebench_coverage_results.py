"""Offline SWE-bench coverage review and exact submission/instance result links.

No trace, shell command, agent, patch or benchmark is executed. Publication list
membership, evaluation outcomes and agent termination remain different evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_trace_operations as operations

ROOT = Path(__file__).resolve().parents[1]
INDEX = "40f164d5b8f1d249bf95a6df8b74b577fd8e519d"
SONAR = "test/20251219_sonar-foundation-agent_claude-opus-4-5"
INSTANCE = re.compile(r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-\d+$")
RESULT_FIELDS = {"resolved", "unresolved", "resolved_ids", "unresolved_ids", "no_generation", "generated",
                 "no_logs", "with_logs", "install_fail", "reset_failed", "no_apply", "applied",
                 "test_errored", "test_timeout"}
FAILURE_FIELDS = {"unresolved", "unresolved_ids", "no_generation", "no_logs", "install_fail",
                  "reset_failed", "no_apply", "test_errored", "test_timeout"}
ACQUISITIONS = ("BULK-NONVIDEO-20260929", "SWEBENCH-CONTINUATION-20260930", "SWEBENCH-SUPPLEMENT-20261006")


def file_record(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    try:
        name = str(path.relative_to(ROOT))
    except ValueError:
        name = str(path)
    return {"path": name, "bytes": path.stat().st_size, "sha256": h.hexdigest()}


def verified_read(entry):
    path = Path(entry["path"])
    data = path.read_bytes()
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("frozen file mismatch: " + str(path))
    return data


def finalize_gap(plan_path, allowed_root=None):
    plan_path = Path(plan_path)
    output = plan_path.parent / "manifest.json"
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text())
    verified_read(plan["old_plan"])
    files, validated = [], []
    allowed_root = Path(allowed_root or ROOT / 'data/raw/public/swebench_gap').resolve()
    for item in plan["items"]:
        partial, final = Path(item["partial_path"]), Path(item["path"])
        if not final.resolve().is_relative_to(allowed_root) or str(partial) != str(final)+'.part':
            raise ValueError('gap destination outside new raw scope')
        if final.exists():
            raise FileExistsError(final)
        data = partial.read_bytes()
        header = Path(item["headers_path"]).read_text()
        statuses = re.findall(r"^HTTP/\S+\s+(\d+)", header, re.M)
        etags = re.findall(r'^ETag:\s*"([0-9a-f]{32})"\s*$', header, re.M | re.I)
        if not statuses or statuses[-1] != "200" or len(data) != item["bytes"]:
            raise ValueError("HTTP/size mismatch: " + item["key"])
        if not etags or hashlib.md5(data).hexdigest() != etags[-1]:
            raise ValueError("S3 single-part ETag MD5 mismatch: " + item["key"])
        json.loads(data)  # Shape is analyzed later; this only rejects broken JSON.
        validated.append((item,etags[-1]))
    for item,etag in validated:
        partial,final=Path(item['partial_path']),Path(item['path'])
        partial.rename(final)
        files.append({**file_record(final), "source": item["url"], "s3_key": item["key"],
                      "group": SONAR, "task": final.stem, "http_status": 200,
                      "expected_listing_bytes": item["bytes"], "etag_md5": etag,
                      "headers": file_record(item["headers_path"])})
    manifest = {"schema": "swebench-gap-acquisition-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "index_commit": plan["index_commit"], "plan": file_record(plan_path), "files": files,
                "count": len(files), "bytes": sum(x["bytes"] for x in files),
                "verification": "HTTP 200, old listing bytes, live single-part S3 ETag MD5, local SHA256, JSON parse",
                "source_boundary": "Git metadata pinned; public S3 objects are mutable. Live ETag is not a historical upstream SHA256.",
                "old_raw_unchanged": True, "agent_or_benchmark_executed": False}
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "acquired": len(files), "bytes": manifest["bytes"], "manifest": str(output)}))
    return manifest


def split_group(group):
    parts = group.split("/", 1)
    return tuple(parts) if len(parts) == 2 else ("verified", group)


def parse_results(data):
    """Positive list memberships only. Missing/nonmembership is never failure."""
    obj = json.loads(data)
    if not isinstance(obj, dict):
        raise ValueError("result document is not a mapping")
    memberships = defaultdict(list)
    problems, fields = [], {}
    for key, value in obj.items():
        if key not in RESULT_FIELDS:
            problems.append({"field": key, "kind": "uninterpreted_field"})
            continue
        if not isinstance(value, list) or any(not isinstance(x, str) or not INSTANCE.fullmatch(x) for x in value):
            problems.append({"field": key, "kind": "not_instance_id_list"})
            continue
        counts = Counter(value)
        fields[key] = {"entries": len(value), "unique_instances": len(counts),
                       "duplicate_entries": len(value) - len(counts)}
        for tid in counts:
            memberships[tid].append(key)
    return dict(memberships), fields, problems


def result_link(task, memberships, available):
    if not isinstance(task, str) or not INSTANCE.fullmatch(task):
        return {"status": "not_an_instance_identifier", "memberships": [], "reported_resolved": None}
    if not available:
        return {"status": "evaluation_file_missing", "memberships": [], "reported_resolved": None}
    flags = sorted(memberships.get(task, []))
    resolved = bool({"resolved", "resolved_ids"} & set(flags))
    conflict = resolved and bool(FAILURE_FIELDS & set(flags))
    if conflict:
        status, value = "conflicting_saved_memberships", None
    elif resolved:
        status, value = "listed_resolved", True
    elif {"unresolved", "unresolved_ids"} & set(flags):
        status, value = "listed_unresolved", False
    elif flags:
        status, value = "listed_other_saved_fields", None
    else:
        status, value = "not_listed_in_saved_fields", None
    return {"status": status, "memberships": flags, "reported_resolved": value}


def native_summary(data, group):
    """Keep termination/submission and last saved flow state distinct."""
    selected = {"20240620_sweagent_claude3.5sonnet", "lite/20240617_moatless_gpt4o", SONAR}
    if group not in selected:
        return None
    obj = json.loads(data)
    info = obj.get("info", {}) if isinstance(obj, dict) else {}
    info = info if isinstance(info, dict) else {}
    exit_value = info.get("exit_status")
    rec = {"termination": {"source": "info.exit_status" if "exit_status" in info else None,
                           "value": exit_value if isinstance(exit_value, (str, int, float, bool)) else None},
           "submission_patch_present": bool(info.get("submission")),
           "submission_patch_sha256": hashlib.sha256(info["submission"].encode()).hexdigest() if isinstance(info.get("submission"), str) and info["submission"] else None}
    if group == "20240620_sweagent_claude3.5sonnet":
        entries = obj.get("trajectory", []) if isinstance(obj, dict) else []
        entries = entries if isinstance(entries, list) else []
        rec.update(format="sweagent-traj", saved_entries=len(entries),
                   explicit_submit_markers=sum(isinstance(x, dict) and isinstance(x.get("action"), str) and
                                               x["action"].strip().split(maxsplit=1)[:1] == ["submit"] for x in entries))
    elif group == "lite/20240617_moatless_gpt4o":
        transitions = obj.get("transitions", []) if isinstance(obj, dict) else []
        transitions = transitions if isinstance(transitions, list) else []
        rec.update(format="moatless-transitions", saved_entries=len(transitions),
                   last_saved_transition=transitions[-1].get("name") if transitions and isinstance(transitions[-1], dict) else None,
                   saved_duration_cost_fields={k: info[k] for k in ("duration", "total_cost") if k in info})
    else:
        rec.update(format="sonar-message-list", saved_entries=len(obj) if isinstance(obj, list) else None)
    return rec


def gap_parse(entry):
    data = verified_read(entry)
    parsed = operations._analyze_swebench_bytes(entry["path"], entry["group"], data)
    process = parsed["schema"] == "swe_exp_saved_process_nodes"
    coverage = {k: entry[k] for k in ("path", "bytes", "sha256", "group", "task")}
    coverage.update(schema=parsed["schema"], status=parsed["status"], reason_code=parsed["reason_code"],
                    unit_count=parsed["unit_count"], action_unit_count=0 if process else parsed["unit_count"] or 0,
                    action_protocol_detail=parsed.get("action_protocol_detail", {}))
    coverage.update(operations._coverage_fields({**coverage}))
    rows = []
    for kind, units in parsed["units_by_kind"]:
        rows.append(operations.summarize_units("SWE-bench", entry["group"], entry["task"],
                                              {"path": entry["path"]}, kind, units,
                                              parsed.get("returns", []), parsed.get("duplicate_ids")))
    return coverage, rows, data


def distribution(values):
    a = sorted(values)
    def q(p):
        if not a:
            return None
        index = (len(a)-1)*p
        lo, hi = int(index), min(int(index)+1, len(a)-1)
        return a[lo]+(a[hi]-a[lo])*(index-lo)
    return {"n": len(a), "min": q(0), "median": q(.5), "q1": q(.25), "q3": q(.75),
            "iqr": q(.75)-q(.25) if a else None, "max": q(1)}


def strata_for_instances(instances):
    metrics = defaultdict(list)
    excluded = Counter()
    for rec in instances:
        rows = rec["behavior_rows"]
        by_kind = defaultdict(list)
        for row in rows:
            by_kind[row["unit_kind"]].append(row)
        for kind, candidates in by_kind.items():
            # Multiple files can be different views or attempts. Do not sum them
            # into an invented run. One source row per instance/kind is required.
            if len(candidates) != 1:
                excluded[(rec["group"], kind, "multiple_behavior_rows")] += 1
                continue
            row = candidates[0]
            metrics[(rec["group"], kind, rec["evaluation"]["status"])].append(row["unit_count"])
    return [{"group": g, "unit_kind": k, "saved_result_stratum": s,
             "saved_units_per_instance": distribution(v)} for (g, k, s), v in sorted(metrics.items())], [
                {"group": g, "unit_kind": k, "reason": r, "instances": n} for (g,k,r),n in sorted(excluded.items())]


def run(baseline_dir, gap_manifest_path, out, recheck_negative=True):
    baseline_dir, gap_manifest_path, out = map(Path, (baseline_dir, gap_manifest_path, out))
    if out.exists():
        raise FileExistsError("refusing overwrite: " + str(out))
    if out.resolve().is_relative_to((ROOT / "data/raw").resolve()) or out.resolve().is_relative_to(baseline_dir.resolve()):
        raise ValueError("output overlaps raw/baseline")
    inputs = {}
    frozen_code=[file_record(Path(__file__).resolve()),file_record(ROOT/'tests/test_swebench_coverage_results.py')]
    def read(entry):
        data = verified_read(entry)
        inputs[entry["path"]] = {k:entry[k] for k in ("path", "bytes", "sha256")}
        return data
    base_manifest_path = baseline_dir / "manifest.json"
    base_manifest_record = file_record(base_manifest_path)
    manifest = json.loads(base_manifest_path.read_text())
    for entry in manifest["outputs"]:
        if entry["path"].endswith(("coverage.json", "per_trajectory.jsonl", "summary.json")):
            read(entry)
    code = [e for e in manifest["inputs"] if e["path"] in
            {"scripts/public_trace_operations.py", "src/agent_workload_characterization/analyzers/public_operations.py"}]
    for entry in code:
        read(entry)
    if len(code) != 2:
        raise ValueError("parser/classifier not bound by baseline")
    coverage_doc = json.loads((baseline_dir / "coverage.json").read_text())
    original = coverage_doc["objects"]
    with (baseline_dir / "per_trajectory.jsonl").open() as stream:
        behaviors = [r for r in map(json.loads, stream) if r["source"] == "SWE-bench"]
    registrations, metadata_entries, manifests = {}, {}, []
    for name in ACQUISITIONS:
        p = Path("data/catalog/public_trace_acquisition") / name / "manifest.json"
        record = file_record(p); inputs[str(p)] = record; manifests.append(record)
        obj = json.loads(p.read_text())
        for entry in obj["inputs"]:
            if entry.get("role") == "trajectory":
                previous = registrations.get(entry["path"])
                if previous and (previous["bytes"],previous["sha256"]) != (entry["bytes"],entry["sha256"]):
                    raise ValueError("conflicting trajectory registrations")
                registrations[entry["path"]] = entry
            elif entry.get("role") == "experiments_index":
                metadata_entries[entry["path"]] = entry
    gap_manifest_record = file_record(gap_manifest_path)
    inputs[str(gap_manifest_path)] = gap_manifest_record
    acquired = json.loads(gap_manifest_path.read_text())
    if acquired.get('index_commit') != INDEX:
        raise ValueError('gap index revision differs from frozen analysis')
    coverage, native, negative_audit = [], {}, []
    print("Verifying all original SWE-bench objects and rechecking non-action files", flush=True)
    for index, item in enumerate(original, 1):
        registration = registrations.get(item["path"])
        if not registration:
            raise ValueError("coverage object absent from acquisitions")
        data = read({**registration})
        if (len(data),hashlib.sha256(data).hexdigest()) != (item["bytes"],item["sha256"]):
            raise ValueError("coverage/acquisition identity conflict")
        if recheck_negative and item["status"] != "actions_extracted":
            parsed = operations._analyze_swebench_bytes(item["path"], item["group"], data)
            unchanged = (parsed["status"] == item["status"] and parsed["reason_code"] == item["reason_code"]
                         and parsed["unit_count"] == item["unit_count"])
            negative_audit.append({"path": item["path"], "group": item["group"], "status": parsed["status"],
                                   "reason_code": parsed["reason_code"], "unit_count": parsed["unit_count"],
                                   "same_as_frozen_v3": unchanged, "schema": parsed["schema"]})
            if not unchanged:
                raise ValueError("frozen-parser recheck differs: " + item["path"])
        note = native_summary(data, item["group"])
        if note is not None:
            native[item["path"]] = note
        coverage.append({**item,"acquisition_cohort":"existing_v3"})
        if index % 3000 == 0:
            print(f"Verified/reviewed {index}/{len(original)} original objects", flush=True)
    print("Parsing new gap objects", flush=True)
    for entry in acquired["files"]:
        if entry['task'] != Path(entry['path']).stem or entry['group'] != SONAR:
            raise ValueError('gap task/group identity conflict')
        if entry["path"] in {x["path"] for x in coverage}:
            raise ValueError("new object duplicates old path")
        row, added, data = gap_parse(entry)
        read(entry)
        coverage.append({**row,"acquisition_cohort":"new_sonar_gap"})
        behaviors.extend(added)
        native[entry["path"]] = native_summary(data, entry["group"])
    groups = sorted({x["group"] for x in coverage})
    evals, eval_files = {}, []
    index_root = Path("data/raw/public/swebench_public_traces") / INDEX / "experiments/evaluation"
    for group in groups:
        split, submission = split_group(group)
        results = index_root/split/submission/"results/results.json"
        metadata = index_root/split/submission/"metadata.yaml"
        note = {"group": group,"split":split,"submission":submission,"available":False,
                "binding":"exact split/submission directory; instance-ID membership; attempt/patch identity unverified"}
        if str(results) in metadata_entries:
            data=read(metadata_entries[str(results)])
            memberships, fields, problems = parse_results(data)
            note.update(available=True,path=str(results),fields=fields,problems=problems,memberships=memberships)
            eval_files.append(file_record(results))
        else:
            note.update(memberships={},fields={},problems=[],missing_reason="no results.json in fixed local index registration")
        if str(metadata) in metadata_entries:
            meta=yaml.safe_load(read(metadata_entries[str(metadata)]))
            expected=f"s3://swe-bench-submissions/{split}/{submission}/trajs"
            asset=meta.get('assets',{}).get('trajs') if isinstance(meta,dict) else None
            note['metadata_trajectory_asset']=asset
            note['asset_matches_exact_namespace']=isinstance(asset,str) and asset.rstrip('/')==expected
            note['source_checked_tag']=meta.get('tags',{}).get('checked') if isinstance(meta,dict) else None
        evals[group]=note
    by_file=defaultdict(list)
    for row in behaviors:
        by_file[row['location']['path']].append(row)
    instances=defaultdict(lambda:{"objects":[],"behavior_rows":[],"native_records":[]})
    object_links=[]
    for row in coverage:
        ev=evals[row['group']]
        linked=result_link(row['task'],ev['memberships'],ev['available'])
        object_links.append({'path':row['path'],'group':row['group'],'task':row['task'],'coverage_status':row['status'],
                             'coverage_reason':row['reason_code'],'evaluation':linked,
                             'evaluation_path':ev.get('path'),'acquisition_cohort':row['acquisition_cohort']})
        if not INSTANCE.fullmatch(row['task']):continue
        record=instances[(row['group'],row['task'])]
        record.update(group=row['group'],task=row['task'],evaluation=linked)
        record['objects'].append({'path':row['path'],'coverage_status':row['status']})
        record['behavior_rows'].extend(by_file[row['path']])
        if row['path'] in native:record['native_records'].append(native[row['path']])
    instance_rows=[v for k,v in sorted(instances.items())]
    strata, excluded = strata_for_instances(instance_rows)
    group_summary={}
    for group in groups:
        objects=[r for r in coverage if r['group']==group]
        joined=[r for r in instance_rows if r['group']==group]
        group_summary[group]={'objects':len(objects),'unique_instance_keys':len(joined),
          'multiple_objects_per_instance':sum(len(r['objects'])>1 for r in joined),
          'instances_without_behavior_rows':sum(not r['behavior_rows'] for r in joined),
          'coverage_status_counts':dict(Counter(r['status'] for r in objects)),
          'evaluation_available':evals[group]['available'],
          'evaluation_status_instances':dict(Counter(r['evaluation']['status'] for r in joined)),
          'saved_result_memberships':dict(Counter(flag for r in joined for flag in r['evaluation']['memberships'])),
          'native_termination_labels':dict(Counter(str(n['termination']['value']) for r in joined for n in r['native_records'])),
          'saved_last_transition':dict(Counter(str(n.get('last_saved_transition')) for r in joined for n in r['native_records'] if n.get('format')=='moatless-transitions'))}
    selection=Path('reports/analysis/SWEBENCH-subset-behavior-v1/selection.json')
    subset_manifest=json.loads(Path('reports/analysis/SWEBENCH-subset-behavior-v1/manifest.json').read_text())
    selection_entry=next(e for e in subset_manifest['outputs'] if e['path']==str(selection))
    selected=json.loads(read(selection_entry)); selected_links=[]
    for group in selected['groups']:
        split,sub=group['split'],group['submission'];key=sub if split=='verified' else split+'/'+sub
        for item in group['items']:
            rec=instances.get((key,item['task_id']))
            if not rec:raise ValueError('selected instance missing')
            selected_links.append({'group':key,'task':item['task_id'],'selected_path':item['file'],
                                   'evaluation':rec['evaluation'],'native_records':rec['native_records']})
    old_tasks={r['task'] for r in original if INSTANCE.fullmatch(r['task'])}
    all_tasks={r['task'] for r in coverage if INSTANCE.fullmatch(r['task'])}
    summary={'schema':'swebench-coverage-results-v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
      'status':'PASS_WITH_SOURCE_LIMITS','index_commit':INDEX,'original_objects':len(original),'new_objects':len(acquired['files']),
      'objects':len(coverage),'groups':len(groups),'group_instance_keys':len(instance_rows),
      'old_independent_task_keys':len(old_tasks),'independent_task_keys':len(all_tasks),'new_task_keys':len(all_tasks-old_tasks),
      'evaluation_groups_available':sum(e['available'] for e in evals.values()),
      'evaluation_groups_missing':[g for g,e in evals.items() if not e['available']],
      'evaluation_status_instance_counts':dict(Counter(r['evaluation']['status'] for r in instance_rows)),
      'coverage_status_counts':dict(Counter(r['status'] for r in coverage)),
      'negative_objects_rechecked':len(negative_audit),'negative_recheck_changes':sum(not r['same_as_frozen_v3'] for r in negative_audit),
      'negative_reason_counts':dict(Counter(r['reason_code'] for r in negative_audit)),
      'sonar_cumulative_objects':group_summary.get(SONAR,{}).get('objects'),
      'groups_summary':group_summary,'behavior_strata':strata,'multiple_behavior_rows_excluded':excluded,
      'subset90_evaluation_counts':{g:dict(Counter(r['evaluation']['status'] for r in selected_links if r['group']==g)) for g in sorted({r['group'] for r in selected_links})},
      'rules':{'join':'exact split+submission+instance_id; object copies not independent attempts; patch/run identity not proven',
               'membership':'positive published membership only; absence from resolved never means failed',
               'strata':'within submission and saved unit_kind; one source row per instance/kind required; no cross-group ranking',
               'termination':'info.exit_status separate from explicit submit, final saved transition and evaluation',
               'coverage':'old positive rows reused; every old object SHA verified; all non-action objects re-parsed with frozen v3 protocol; new 147 freshly parsed',
               'source':'fixed Git metadata, mutable S3 payloads; new ETag checks live data, not historical immutable identity'},
      'remaining_limits':['unattempted public submission groups outside these 41','no original CPU/memory/IO data','missing result publications for two groups',
                          'unlisted result IDs remain unknown','no attempt/patch-level alignment','saved order not execution order; tool results without IDs not position-paired']}
    out.mkdir(parents=True)
    for name,rows in [('object_links.jsonl',object_links),('per_instance.jsonl',instance_rows),('negative_coverage_review.jsonl',negative_audit),('subset90_links.jsonl',selected_links),('new_behavior_rows.jsonl',[r for r in behaviors if '/swebench_gap/' in r['location']['path']])]:
        with (out/name).open('w') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (out/'evaluation_sources.json').write_text(json.dumps({g:{k:v for k,v in e.items() if k!='memberships'} for g,e in evals.items()},ensure_ascii=False,indent=2)+'\n')
    with (out/'coverage_results.csv').open('w') as stream:
        fields=['group','objects','unique_instance_keys','evaluation_available','listed_resolved','listed_unresolved','listed_other_saved_fields','not_listed_in_saved_fields','evaluation_file_missing','conflicting_saved_memberships']
        writer=csv.DictWriter(stream,fields);writer.writeheader()
        for group,s in group_summary.items():writer.writerow({'group':group,**{k:s[k] for k in ['objects','unique_instance_keys','evaluation_available']},**{k:s['evaluation_status_instances'].get(k,0) for k in fields[4:]}})
    md=['# SWE-bench：下载缺口、覆盖复核与公开评价关联','','本轮仅下载公开数据和离线读取，不执行Agent、工具、patch、verifier或benchmark。旧raw和报告保持原样。',
        '',f"- 原登记{len(original):,}对象/41组；新增{len(acquired['files'])}个Sonar对象，累计{len(coverage):,}对象。Sonar达到{group_summary[SONAR]['objects']}/2,294。",
        f"- 独立任务键{len(old_tasks):,}→{len(all_tasks):,}（新增{len(all_tasks-old_tasks)}）；同一任务跨submission不算新的独立任务。",
        f"- 全部旧对象按获取清单与coverage哈希读取核验；{len(negative_audit):,}个非动作对象重查，原协议分流改变{summary['negative_recheck_changes']}。没有把过程节点或叙述补成调用。",
        f"- {summary['evaluation_groups_available']}/41组有同split/submission的已登记results.json；缺失：{', '.join(summary['evaluation_groups_missing'])}。",'',
        '## 三种原生格式：全组与原90条子集','','| 组 | 对象数 | 独立group×instance | 已列resolved | 列其他保存字段 | 未列入保存字段 |','|---|---:|---:|---:|---:|---:|']
    for group in ['20240620_sweagent_claude3.5sonnet','lite/20240617_moatless_gpt4o',SONAR]:
        s=group_summary[group];c=s['evaluation_status_instances'];md.append(f"| {group} | {s['objects']} | {s['unique_instance_keys']} | {c.get('listed_resolved',0)} | {c.get('listed_other_saved_fields',0)} | {c.get('not_listed_in_saved_fields',0)} |")
    md+=['','以上是发布清单成员关系，不是本项目重跑评分。未列入resolved不转为failed；no_generation/no_logs/timeout等保留来源标签。一次submission内同task的多个对象不当成多次独立attempt。','',
         '原90条选择保持冻结，只追加评价关联。关联结果：`'+json.dumps(summary['subset90_evaluation_counts'],ensure_ascii=False)+'`。','',
         '## 行为与结果分层','','各组按saved unit_kind与保存结果标签分别给出工具/操作单位数的逐instance median/IQR，见summary.json的behavior_strata。分层只覆盖有已识别保存单位、且每instance/kind来源行唯一的实例；没有行为证据不填0，instances_without_behavior_rows另列。它们是描述性分层，任务集、保存格式及harness差异不做因果解释；同instance同kind有多个来源行时不擅自求和，排除数另列。',
         '','sweagent显式info.exit_status、轨迹submit标记、moatless末条transition、提交patch存在性和评价标签分开记录。Finished/submitted不替代任务resolved；未按末条assistant文本推断正常终止。',
         '','## 覆盖仍有哪些边界','','6,054个旧部分/歧义对象中，很多是检索叙述、候选文件、请求响应日志或保存过程节点；本轮按已有冻结解析协议重查。零变化说明该协议下结果稳定，不等于所有语义已经穷尽，也不证明不存在其他可支持的协议。',
         '','此次只补已选Sonar组的147对象，没有穷尽上游所有submission。缺评价文件、未列入任何来源状态、无调用返回ID、无attempt/patch精确绑定均保持未知。没有CPU/内存/I/O/热点、可靠工具耗时或费用的新证据。',
         '','## 来源与复现','','固定索引commit `'+INDEX+'`；Git中的results/metadata与S3对象保存位置分别登记。S3可变，新增内容只证明与原listing字节、当前HTTP/ETag一致，不冒称旧commit冻结了S3字节。',
         '','[逐组覆盖/评价CSV](coverage_results.csv) · [原90条关联](subset90_links.jsonl) · [逐instance](per_instance.jsonl) · [非动作复核](negative_coverage_review.jsonl) · [评价来源](evaluation_sources.json) · [manifest](manifest.json)']
    (out/'summary.md').write_text('\n'.join(md)+'\n')
    inputs[str(base_manifest_path)]=base_manifest_record
    inputs[str(selection.parent/'manifest.json')]=file_record(selection.parent/'manifest.json')
    for record in list(inputs.values()):verified_read(record)
    for record in frozen_code:verified_read(record)
    output_manifest={'schema':'swebench-coverage-results-manifest-v1','inputs':list(inputs.values()),'analysis_code_and_tests':frozen_code,
                     'outputs':[file_record(p) for p in sorted(out.iterdir()) if p.is_file()], 'manifest_self_hash':'excluded'}
    (out/'manifest.json').write_text(json.dumps(output_manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['status','objects','groups','independent_task_keys','evaluation_groups_available','negative_objects_rechecked']},ensure_ascii=False),flush=True)
    return summary


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--finalize-gap',type=Path)
    cli.add_argument('--gap-manifest',type=Path)
    cli.add_argument('--baseline-dir',type=Path,default=Path('reports/analysis/PUBLIC-TRACE-OPERATIONS-v3'))
    cli.add_argument('--output-dir',type=Path)
    args=cli.parse_args()
    if args.finalize_gap:finalize_gap(args.finalize_gap)
    else:
        if not args.gap_manifest or not args.output_dir:cli.error('--gap-manifest and --output-dir required')
        run(args.baseline_dir,args.gap_manifest,args.output_dir)


if __name__=='__main__':main()
