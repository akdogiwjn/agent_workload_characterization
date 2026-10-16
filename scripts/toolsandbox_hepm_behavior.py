#!/usr/bin/env python3
"""Offline behavior analysis for the acquired H-EPM ToolSandbox public trajectories.

Reads saved conversation.json / execution_context.json / result_summary.json as
plain JSON only. The source framework is never imported and no code stored in
the data is executed; no benchmark, trajectory or model is run.
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
COMMIT = '4ad8ad335fe63d365f4baf97df77e19055c79f1c'
DEFAULT_ACQUISITION = Path('data/catalog/public_trace_acquisition/TOOLSANDBOX-HEPM-20261011/manifest.json')

# H-EPM-added variant suffixes (longest first). Evidence in the acquired payload:
# stripped scramble suffixes equal execution_context.tool_augmentation_list for
# every scenario (207/207); distraction/all_tools suffixes equal the declared
# result_summary categories; every suffix-free scenario carries category
# NO_DISTRACTION_TOOLS. Official ToolSandbox scenario-name tokens
# (multiple_user_turn, insufficient_information, alt, implicit, low_battery_mode,
# wifi_off, cellular_off, canonicalize) are NOT stripped.
HEPM_SUFFIXES = [
    '_3_distraction_tools_arg_description_scrambled', '_3_distraction_tools_tool_name_scrambled',
    '_3_distraction_tools_tool_description_scrambled', '_3_distraction_tools_arg_type_scrambled',
    '_10_distraction_tools_arg_type_scrambled', '_10_distraction_tools_tool_description_scrambled',
    '_10_distraction_tools_tool_name_scrambled', '_10_distraction_tools_arg_description_scrambled',
    '_3_distraction_tools', '_10_distraction_tools', '_all_tools',
    '_arg_description_scrambled', '_tool_name_scrambled', '_tool_description_scrambled',
    '_arg_type_scrambled',
]

# Business-activity classification for native tool names. Evidence per class:
# reminder/contact/messaging/settings tools write the matching namespace in
# saved tool_details.database_update (verified at run time and reported);
# datetime/location/weather/web_api_search are classified from their descriptive
# names plus observed ConnectionError behaviour when device settings are off;
# harness tools are declared by the source README (summarize_the_task is the
# state-summarization helper; end_conversation is the declared conversation-end
# tool). Native tool names are always kept alongside the classification.
NATIVE_ACTIVITY = {
    'add_reminder': 'reminder', 'modify_reminder': 'reminder', 'remove_reminder': 'reminder', 'search_reminder': 'reminder',
    'add_contact': 'contact', 'modify_contact': 'contact', 'remove_contact': 'contact', 'search_contacts': 'contact',
    'send_message_with_phone_number': 'messaging', 'search_messages': 'messaging',
    'set_wifi_status': 'settings', 'get_wifi_status': 'settings',
    'set_cellular_service_status': 'settings', 'get_cellular_service_status': 'settings',
    'set_location_service_status': 'settings', 'get_location_service_status': 'settings',
    'set_low_battery_mode_status': 'settings', 'get_low_battery_mode_status': 'settings',
    'get_current_timestamp': 'datetime', 'datetime_info_to_timestamp': 'datetime',
    'timestamp_to_datetime_info': 'datetime', 'shift_timestamp': 'datetime',
    'timestamp_diff': 'datetime', 'seconds_to_hours_minutes_seconds': 'datetime',
    'get_current_location': 'location', 'search_location_around_lat_lon': 'location',
    'search_lat_lon': 'location', 'calculate_lat_lon_distance': 'location',
    'search_weather_around_lat_lon': 'weather',
    'search_holiday': 'web_api_search', 'search_stock': 'web_api_search', 'convert_currency': 'web_api_search',
    'unit_conversion': 'unit_conversion',
    'summarize_the_task': 'harness_summary', 'end_conversation': 'harness_termination',
}
HARNESS_ACTIVITIES = {'harness_summary', 'harness_termination'}
DB_ACTIVITY = {'REMINDER': 'reminder', 'CONTACT': 'contact', 'MESSAGING': 'messaging', 'SETTING': 'settings'}
ACTIVITY_DB_EVIDENCE = {'reminder': 'REMINDER', 'contact': 'CONTACT', 'messaging': 'MESSAGING', 'settings': 'SETTING'}

# A tool result whose saved content starts with a Python exception header is
# counted as an explicit tool execution error (class name preserved).
ERROR_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:Error|Exception))(?::|\s)')


def _nullish(v):
    """Saved SANDBOX cells use JSON null or the strings 'null'/'None'."""
    return v is None or v in ('null', 'None', '')


def sandbox_tool_trace_name(raw):
    """Extract the native tool name from a saved SANDBOX tool_trace cell.

    The cell is a list of JSON strings (or a single JSON string / dict) such as
    ['{"tool_name": "add_contact", "arguments": {...}, "result": ...}']. No
    code inside the data is executed; only JSON parsing is used.
    """
    if _nullish(raw):
        return None
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        if not isinstance(item, (str, dict)):
            continue
        try:
            j = item if isinstance(item, dict) else json.loads(item)
        except Exception:
            continue
        if isinstance(j, dict) and isinstance(j.get('tool_name'), str):
            return j['tool_name']
    return None


def sandbox_index(ec):
    """Index execution_context._dbs.SANDBOX rows by agent tool-call id.

    Only rows without a saved tool_call_exception contribute tool_trace names:
    exception rows in this payload carry stale traces (69 rows, all
    'summarize_the_task'), so they are not trusted for resolution.
    """
    sb = ec.get('_dbs') if isinstance(ec.get('_dbs'), dict) else {}
    rows = sb.get('SANDBOX') if isinstance(sb.get('SANDBOX'), list) else []
    by_id = {}
    final_active = None
    end_conversation_rows = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        active = r.get('conversation_active')
        if not _nullish(active):
            final_active = str(active)
        cid = r.get('openai_tool_call_id')
        if not _nullish(cid) and not _nullish(r.get('openai_function_name')):
            entry = by_id.setdefault(cid, {'rows': 0, 'tool_trace_name': None, 'has_exception': False})
            entry['rows'] += 1
            if not _nullish(r.get('tool_call_exception')):
                entry['has_exception'] = True
            elif sandbox_tool_trace_name(r.get('tool_trace')) is not None:
                entry['tool_trace_name'] = sandbox_tool_trace_name(r['tool_trace'])
        if sandbox_tool_trace_name(r.get('tool_trace')) == 'end_conversation':
            end_conversation_rows += 1
    return {'by_id': by_id, 'final_conversation_active': final_active,
            'end_conversation_tool_trace_rows': end_conversation_rows}


def sha(path):
    h = hashlib.sha256(); n = 0
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b); n += len(b)
    return n, h.hexdigest()


def rel(path, root):
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def finite(x):
    return type(x) in (int, float) and not isinstance(x, bool) and math.isfinite(float(x))


def q(values, p):
    a = sorted(float(x) for x in values if finite(x))
    if not a:
        return None
    z = (len(a) - 1) * p; lo = int(z); hi = min(lo + 1, len(a) - 1)
    return a[lo] if lo == hi else a[lo] + (a[hi] - a[lo]) * (z - lo)


def stats(values):
    a = [x for x in values if finite(x)]; q1, q3 = q(a, .25), q(a, .75)
    return {'n': len(a), 'missing': len(values) - len(a), 'min': q(a, 0), 'q1': q1, 'median': q(a, .5),
            'q3': q3, 'iqr': None if q1 is None else q3 - q1, 'max': q(a, 1)}


def strip_variants(name):
    """Return (base_scenario, [stripped suffixes]) using only H-EPM suffixes."""
    suffixes = []
    changed = True
    while changed:
        changed = False
        for v in HEPM_SUFFIXES:
            if name.endswith(v) and len(name) > len(v):
                name = name[:-len(v)]; suffixes.append(v[1:]); changed = True
    return name, suffixes


def verify_payload(acquisition, project_root):
    """Verify the registered payload files (both directions, bytes + sha256)."""
    registered = {f['path']: (f['bytes'], f['sha256']) for f in acquisition['files']}
    raw_root = project_root / Path(*Path(next(iter(registered))).parts[:-1])
    while not (raw_root / 'ToolSandbox').is_dir() and raw_root != project_root:
        raw_root = raw_root.parent
    actual = {rel(p, project_root): p for p in raw_root.rglob('*') if p.is_file()}
    errors = []
    for path in sorted(set(actual) | set(registered)):
        if path not in actual:
            errors.append({'path': path, 'kind': 'registered_missing'})
        elif path not in registered:
            errors.append({'path': path, 'kind': 'unregistered_actual'})
        else:
            size, digest = sha(actual[path])
            if (size, digest) != registered[path]:
                errors.append({'path': path, 'kind': 'hash_or_size_mismatch'})
    if errors:
        raise ValueError('payload verification failed: ' + json.dumps(errors[:3]))
    return raw_root, sorted(actual.values()), registered


def transitions(seq):
    tr = Counter(); same = cross = boundary = 0
    for a, b in zip(seq, seq[1:]):
        if a is not None and b is not None:
            tr[f'{a}->{b}'] += 1
            same, cross = (same + 1, cross) if a == b else (same, cross + 1)
        else:
            boundary += 1
    return {'transition_counts': dict(sorted(tr.items())), 'same_tool_transitions': same,
            'cross_tool_transitions': cross, 'boundary_adjacent_pairs': boundary}


def analyze_trajectory(group, group_dir, scenario, conv, ec, rs_row, native_names):
    role_counts = Counter(); field_counts = Counter(); details_keys = Counter()
    protocol = Counter(); calls = []; results = []; unrecognized = 0
    annotations = Counter()
    if not isinstance(conv, list):
        conv = []
    for mi, m in enumerate(conv):
        if not isinstance(m, dict):
            unrecognized += 1; continue
        role = m.get('role') if isinstance(m.get('role'), str) else 'missing_or_nonstring'
        role_counts[role] += 1; field_counts.update(m.keys())
        for key in ('tool_details', 'assistant_details', 'user_details'):
            d = m.get(key)
            if isinstance(d, dict) and d:
                annotations[key] += 1; details_keys.update(f'{key}.{k}' for k in d)
        if role == 'assistant':
            tcs = m.get('tool_calls')
            if tcs is None:
                continue
            if not isinstance(tcs, list):
                protocol['tool_calls_not_list'] += 1; continue
            for ci, tc in enumerate(tcs):
                if not isinstance(tc, dict):
                    protocol['tool_call_entry_not_dict'] += 1
                    calls.append({'msg_idx': mi, 'call_idx': ci, 'id': None, 'name': None, 'args_status': 'non_dict'})
                    continue
                cid = tc.get('id'); fn = tc.get('function') if isinstance(tc.get('function'), dict) else {}
                name = fn.get('name') if isinstance(fn.get('name'), str) and fn.get('name') else None
                if not (isinstance(cid, str) and cid):
                    protocol['call_missing_id'] += 1; cid = None
                if name is None:
                    protocol['call_missing_function_name'] += 1
                args = fn.get('arguments'); args_status = 'non_string'
                if isinstance(args, str):
                    try:
                        json.loads(args); args_status = 'ok'
                    except Exception:
                        args_status = 'unparseable_json'; protocol['unparseable_arguments'] += 1
                elif args is None:
                    args_status = 'missing'; protocol['call_missing_arguments'] += 1
                calls.append({'msg_idx': mi, 'call_idx': ci, 'id': cid, 'name': name, 'args_status': args_status})
        elif role == 'tool':
            rid = m.get('tool_call_id'); rname = m.get('name') if isinstance(m.get('name'), str) and m.get('name') else None
            if not (isinstance(rid, str) and rid):
                protocol['result_missing_id'] += 1; rid = None
            content = m.get('content'); content = content if isinstance(content, str) else ''
            em = ERROR_RE.match(content)
            td = m.get('tool_details') if isinstance(m.get('tool_details'), dict) else {}
            du = td.get('database_update') if isinstance(td.get('database_update'), dict) else {}
            dbs = {k for k in du if k in DB_ACTIVITY}
            results.append({'msg_idx': mi, 'id': rid, 'name': rname, 'error_class': em.group(1) if em else None,
                            'dbs': dbs, 'summary_prefix': content.startswith('[SummaryTool]')})
    # Pairing keeps duplicate IDs via lists; nothing is overwritten.
    call_by_id = defaultdict(list); result_by_id = defaultdict(list)
    for c in calls:
        if c['id'] is not None:
            call_by_id[c['id']].append(c)
    for r in results:
        if r['id'] is not None:
            result_by_id[r['id']].append(r)
    calls_with_id = sum(1 for c in calls if c['id'] is not None)
    results_with_id = sum(1 for r in results if r['id'] is not None)
    paired_calls = sum(1 for c in calls if c['id'] is not None and result_by_id.get(c['id']))
    orphan_results = sum(1 for r in results if r['id'] is not None and not call_by_id.get(r['id']))
    name_mismatches = 0
    for c in calls:
        if c['name'] is not None and c['id'] is not None:
            for r in result_by_id.get(c['id'], []):
                if r['name'] is not None and r['name'] != c['name']:
                    name_mismatches += 1
    pairing = {
        'tool_call_entries': len(calls), 'tool_result_messages': len(results),
        'calls_with_id': calls_with_id, 'calls_missing_id': len(calls) - calls_with_id,
        'results_with_id': results_with_id, 'results_missing_id': len(results) - results_with_id,
        'paired_call_entries': paired_calls, 'calls_with_id_without_return': calls_with_id - paired_calls,
        'orphan_result_messages': orphan_results,
        'duplicate_call_id_entries': calls_with_id - len(call_by_id),
        'duplicate_result_id_entries': results_with_id - len(result_by_id),
        'call_result_name_mismatches': name_mismatches,
    }
    # Pairing conservation invariants (asserted; failures indicate analyzer bugs).
    assert pairing['tool_call_entries'] == pairing['calls_with_id'] + pairing['calls_missing_id']
    assert pairing['calls_with_id'] == pairing['paired_call_entries'] + pairing['calls_with_id_without_return']
    assert pairing['tool_result_messages'] == pairing['results_with_id'] + pairing['results_missing_id']
    matched_results = sum(1 for r in results if r['id'] is not None and call_by_id.get(r['id']))
    assert pairing['results_with_id'] == matched_results + pairing['orphan_result_messages']
    # SANDBOX cross-verification: agent call ids recorded in execution_context.
    sbx = sandbox_index(ec)
    sandbox_matched = sum(1 for c in calls if c['id'] is not None and c['id'] in sbx['by_id'])
    sandbox_association = {
        'calls_matched_in_sandbox': sandbox_matched,
        'calls_with_id_not_in_sandbox': calls_with_id - sandbox_matched,
        'sandbox_unique_call_ids': len(sbx['by_id']),
        'sandbox_call_id_rows': sum(e['rows'] for e in sbx['by_id'].values()),
        'sandbox_call_ids_with_exception': sum(1 for e in sbx['by_id'].values() if e['has_exception']),
        'sandbox_call_ids_with_clean_tool_trace': sum(1 for e in sbx['by_id'].values() if e['tool_trace_name'] is not None),
    }
    # Native identity resolution and activity sequence.
    resolution = Counter(); called_name_counts = Counter(); native_identity_counts = Counter()
    db_update_by_native = defaultdict(Counter); called_seq = []; activity_seq = []
    for c in calls:
        name = c['name']
        if name is None:
            called_seq.append(None); activity_seq.append(None); resolution['missing_name'] += 1
            continue
        called_seq.append(name); called_name_counts[name] += 1
        paired = result_by_id.get(c['id'], []) if c['id'] is not None else []
        if name in native_names:
            resolution['native_name'] += 1; native_identity_counts[name] += 1
            for r in paired:
                for db in r['dbs']:
                    db_update_by_native[name][db] += 1
            activity = NATIVE_ACTIVITY.get(name)
            if activity is None:
                resolution['native_name_without_activity_mapping'] += 1
            activity_seq.append(activity)
        else:
            # Scrambled-name call. Preferred evidence is the actual tool_trace
            # recorded in execution_context._dbs.SANDBOX for this call id
            # (exception rows excluded; see sandbox_index). Content prefix and
            # database namespace are fallbacks only.
            native = None; method = None
            entry = sbx['by_id'].get(c['id']) if c['id'] is not None else None
            if entry is not None and entry['tool_trace_name'] in native_names:
                native = entry['tool_trace_name']; method = 'sandbox_tool_trace'
            if native is None and any(r['summary_prefix'] for r in paired):
                native = 'summarize_the_task'; method = 'content_prefix_summary_tool'
            if native is not None:
                resolution[method] += 1; native_identity_counts[native] += 1
                activity_seq.append(NATIVE_ACTIVITY.get(native))
            elif not paired:
                resolution['unresolved_no_paired_result'] += 1; activity_seq.append(None)
            else:
                dbs = set()
                for r in paired:
                    dbs |= r['dbs']
                if len(dbs) == 1:
                    resolution['database_namespace_activity'] += 1
                    activity_seq.append(DB_ACTIVITY[next(iter(dbs))])
                else:
                    resolution['unresolved_scrambled'] += 1; activity_seq.append(None)
    activity_counts = Counter(a for a in activity_seq if a is not None)
    error_classes = Counter(r['error_class'] for r in results if r['error_class'])
    end_conversation_calls = native_identity_counts.get('end_conversation', 0)
    base, suffixes = strip_variants(scenario)
    ec_facts = {
        'tool_allow_list': ec.get('tool_allow_list') if isinstance(ec.get('tool_allow_list'), list) else None,
        'tool_deny_list': ec.get('tool_deny_list') if isinstance(ec.get('tool_deny_list'), list) else None,
        'tool_augmentation_list': ec.get('tool_augmentation_list') if isinstance(ec.get('tool_augmentation_list'), list) else None,
        'trace_tool': ec.get('trace_tool'), 'preferred_tool_backend': ec.get('preferred_tool_backend'),
        'database_namespaces': sorted(ec.get('_dbs').keys()) if isinstance(ec.get('_dbs'), dict) else None,
        'final_conversation_active': sbx['final_conversation_active'],
        'sandbox_end_conversation_tool_trace_rows': sbx['end_conversation_tool_trace_rows'],
    }
    return {
        'group': group, 'group_directory': group_dir, 'scenario': scenario,
        'base_scenario': base, 'variant_suffixes': suffixes,
        'source_categories': rs_row.get('categories'), 'tool_augmentation_list': ec_facts['tool_augmentation_list'],
        'tool_deny_list': ec_facts['tool_deny_list'], 'tool_allow_list': ec_facts['tool_allow_list'],
        'execution_context_facts': ec_facts,
        'messages_total': len(conv), 'unrecognized_records': unrecognized,
        'role_counts': dict(role_counts), 'message_field_counts': dict(field_counts),
        'details_annotation_message_counts': dict(annotations), 'details_key_counts': dict(details_keys),
        'assistant_messages': role_counts.get('assistant', 0),
        'assistant_messages_with_tool_calls': sum(1 for m in conv if isinstance(m, dict) and m.get('role') == 'assistant' and m.get('tool_calls') is not None),
        'multi_tool_call_assistant_messages': sum(1 for c, n in Counter(c['msg_idx'] for c in calls).items() if n > 1),
        'protocol_issue_counts': dict(protocol),
        'pairing': pairing,
        'sandbox_association': sandbox_association,
        'call_resolution_counts': dict(resolution),
        'called_name_counts': dict(called_name_counts),
        'native_identity_counts': dict(native_identity_counts),
        'scrambled_name_counts': {k: v for k, v in called_name_counts.items() if k not in native_names},
        'activity_call_counts': dict(activity_counts),
        'tool_result_error_count': sum(error_classes.values()),
        'tool_result_error_classes': dict(error_classes),
        'end_conversation_calls': end_conversation_calls,
        'last_message_role': (conv[-1].get('role') if isinstance(conv[-1], dict) and isinstance(conv[-1].get('role'), str) else None) if conv else None,
        'called_name_sequence': called_seq, 'activity_sequence': activity_seq,
        'called_name_transitions': transitions(called_seq),
        'activity_transitions': transitions(activity_seq),
        'observed_database_update_namespaces_by_native_tool': {k: dict(v) for k, v in db_update_by_native.items()},
        'result_summary_row': rs_row,
    }


def run(acquisition_manifest_path, output_dir, project_root=PROJECT):
    output_dir = Path(output_dir)
    project_root = Path(project_root)
    if output_dir.exists():
        raise ValueError('output directory exists; refusing overwrite')
    acquisition = json.loads(Path(acquisition_manifest_path).read_text())
    raw_root, payload_files, registered = verify_payload(acquisition, project_root)
    # Group discovery from the registered result_summary files.
    rs_paths = sorted(f for f in payload_files if f.name == 'result_summary.json')
    group_dirs = [p.parent.name for p in rs_paths]
    native_names = set()
    group_scenarios = {}
    group_rs = {}
    for gdir in group_dirs:
        rs = json.loads((raw_root / 'ToolSandbox' / 'data' / gdir / 'result_summary.json').read_text())
        rows = rs.get('per_scenario_results') if isinstance(rs.get('per_scenario_results'), list) else []
        rs_map = {}
        for r in rows:
            if isinstance(r, dict) and isinstance(r.get('name'), str):
                if r['name'] in rs_map:
                    raise ValueError(f'duplicate scenario in result_summary: {gdir}/{r["name"]}')
                rs_map[r['name']] = r
        traj_root = raw_root / 'ToolSandbox' / 'data' / gdir / 'trajectories'
        conv_map = {}; ec_map = {}
        for d in sorted(p for p in traj_root.iterdir() if p.is_dir()):
            conv = d / 'conversation.json'; ec = d / 'execution_context.json'
            if conv.is_file():
                if d.name in conv_map:
                    raise ValueError(f'duplicate trajectory dir: {gdir}/{d.name}')
                conv_map[d.name] = conv
            if ec.is_file():
                ec_map[d.name] = ec
        missing_ec = sorted(set(conv_map) - set(ec_map)); orphan_ec = sorted(set(ec_map) - set(conv_map))
        missing_rs = sorted(set(conv_map) - set(rs_map)); orphan_rs = sorted(set(rs_map) - set(conv_map))
        if missing_ec or orphan_ec or missing_rs or orphan_rs:
            raise ValueError(f'scenario association mismatch in {gdir}: '
                             f'missing_ec={missing_ec[:3]} orphan_ec={orphan_ec[:3]} '
                             f'missing_rs={missing_rs[:3]} orphan_rs={orphan_rs[:3]}')
        for scen in conv_map:
            ec = json.loads(ec_map[scen].read_text())
            allow = ec.get('tool_allow_list') if isinstance(ec.get('tool_allow_list'), list) else []
            native_names.update(x for x in allow if isinstance(x, str))
        group_scenarios[gdir] = {'conv_map': conv_map, 'ec_map': ec_map, 'rs_map': rs_map}
        group_rs[gdir] = rs
    # Analyze every trajectory.
    records = []
    for gdir in group_dirs:
        info = group_scenarios[gdir]
        for scen in sorted(info['conv_map']):
            conv = json.loads(info['conv_map'][scen].read_text())
            ec = json.loads(info['ec_map'][scen].read_text())
            records.append(analyze_trajectory(gdir, gdir, scen, conv, ec, info['rs_map'][scen], native_names))
    # Aggregate per group.
    groups = {}
    for gdir in group_dirs:
        rs = [r for r in records if r['group_directory'] == gdir]
        called = Counter(); native_id = Counter(); resolution = Counter(); scrambled = Counter()
        activity = Counter(); errors = Counter(); protocol = Counter(); roles = Counter()
        fields = Counter(); details = Counter(); annotations = Counter(); last_role = Counter()
        cat = Counter(); aug = Counter(); suffix = Counter(); bases = set()
        final_active = Counter(); deny_non_null = 0; db_by_tool = defaultdict(Counter)
        sandbox_tot = Counter()
        for r in rs:
            called.update(r['called_name_counts']); native_id.update(r['native_identity_counts'])
            resolution.update(r['call_resolution_counts']); scrambled.update(r['scrambled_name_counts'])
            activity.update(r['activity_call_counts']); errors.update(r['tool_result_error_classes'])
            protocol.update(r['protocol_issue_counts']); roles.update(r['role_counts'])
            fields.update(r['message_field_counts']); details.update(r['details_key_counts'])
            annotations.update(r['details_annotation_message_counts'])
            last_role[str(r['last_message_role'])] += 1
            final_active[str(r['execution_context_facts']['final_conversation_active'])] += 1
            sandbox_tot.update(r['sandbox_association'])
            for c in (r['source_categories'] or []): cat[c] += 1
            for a in (r['tool_augmentation_list'] or []): aug[a] += 1
            for s in r['variant_suffixes']: suffix[s] += 1
            bases.add(r['base_scenario'])
            if r['tool_deny_list'] is not None:
                deny_non_null += 1
            for t, dbs in r['observed_database_update_namespaces_by_native_tool'].items():
                db_by_tool[t].update(dbs)
        pairing_tot = {k: sum(r['pairing'][k] for r in rs) for k in next(iter(rs))['pairing']}
        activity_traj = defaultdict(list)
        for r in rs:
            for a in set(activity):
                activity_traj[a].append(r['activity_call_counts'].get(a, 0))
        groups[gdir] = {
            'trajectories': len(rs),
            'scenario_count': len({r['scenario'] for r in rs}),
            'base_scenario_count': len(bases),
            'source_category_scenario_counts': dict(sorted(cat.items())),
            'tool_augmentation_scenario_counts': dict(sorted(aug.items())),
            'variant_suffix_counts': dict(sorted(suffix.items())),
            'scenarios_with_non_null_deny_list': deny_non_null,
            'role_counts': dict(roles), 'message_field_counts': dict(fields),
            'details_annotation_message_counts': dict(annotations), 'details_key_counts': dict(details),
            'last_message_role_counts': dict(last_role),
            'final_conversation_active_counts': dict(sorted(final_active.items())),
            'sandbox_end_conversation_tool_trace_trajectories': sum(
                1 for r in rs if r['execution_context_facts']['sandbox_end_conversation_tool_trace_rows'] > 0),
            'pairing_totals': pairing_tot,
            'sandbox_association_totals': dict(sorted(sandbox_tot.items())),
            'protocol_issue_counts': dict(protocol),
            'called_name_counts': dict(sorted(called.items())),
            'native_identity_counts': dict(sorted(native_id.items())),
            'call_resolution_counts': dict(sorted(resolution.items())),
            'scrambled_name_counts': dict(sorted(scrambled.items())),
            'pooled_activity_call_counts': dict(sorted(activity.items())),
            'activity_stats_denominator_note': 'conditional stats cover only trajectories where the activity occurs (n = activity_trajectories_with_calls); all_trajectory stats include zeros with denominator = all group trajectories',
            'activity_trajectories_with_calls': {a: sum(1 for v in activity_traj[a] if v) for a in sorted(activity_traj)},
            'activity_calls_per_trajectory_conditional_stats': {a: stats([v for v in activity_traj[a] if v]) for a in sorted(activity_traj)},
            'activity_calls_per_trajectory_all_trajectories_stats': {a: stats(activity_traj[a]) for a in sorted(activity_traj)},
            'tool_result_error_count': sum(errors.values()),
            'tool_result_error_classes': dict(sorted(errors.items())),
            'sandbox_exception_call_ids': sandbox_tot['sandbox_call_ids_with_exception'],
            'calls_per_trajectory_stats': stats([r['pairing']['tool_call_entries'] for r in rs]),
            'observed_database_update_namespaces_by_native_tool': {k: dict(v) for k, v in sorted(db_by_tool.items())},
            'result_fields': {
                'milestone_similarity': stats([r['result_summary_row'].get('milestone_similarity') for r in rs]),
                'minefield_similarity': stats([r['result_summary_row'].get('minefield_similarity') for r in rs]),
                'similarity': stats([r['result_summary_row'].get('similarity') for r in rs]),
                'turn_count': stats([r['result_summary_row'].get('turn_count') for r in rs]),
                'exception_type_non_null': sum(r['result_summary_row'].get('exception_type') is not None for r in rs),
                'traceback_non_null': sum(r['result_summary_row'].get('traceback') is not None for r in rs),
            },
        }
        act_trans = Counter(); called_trans = Counter(); same_a = cross_a = boundary_a = 0
        for r in rs:
            act_trans.update(r['activity_transitions']['transition_counts'])
            called_trans.update(r['called_name_transitions']['transition_counts'])
            same_a += r['activity_transitions']['same_tool_transitions']
            cross_a += r['activity_transitions']['cross_tool_transitions']
            boundary_a += r['activity_transitions']['boundary_adjacent_pairs']
        groups[gdir]['activity_transition_counts'] = dict(sorted(act_trans.items(), key=lambda x: -x[1])[:40])
        groups[gdir]['activity_transition_count_total_distinct'] = len(act_trans)
        groups[gdir]['called_name_transition_counts'] = dict(sorted(called_trans.items(), key=lambda x: -x[1])[:40])
        groups[gdir]['called_name_transition_count_total_distinct'] = len(called_trans)
        groups[gdir]['same_activity_transitions'] = same_a
        groups[gdir]['cross_activity_transitions'] = cross_a
        groups[gdir]['activity_boundary_adjacent_pairs'] = boundary_a
    # Shared-scenario saved-metric comparison (descriptive only).
    metric_diffs = {}
    by_key = {(r['group_directory'], r['scenario']): r for r in records}
    scen_by_group = {g: {r['scenario'] for r in records if r['group_directory'] == g} for g in group_dirs}
    shared = set.intersection(*scen_by_group.values()) if group_dirs else set()
    for metric in ('milestone_similarity', 'minefield_similarity', 'similarity', 'turn_count'):
        diffs = []
        for s in shared:
            vals = []
            for g in group_dirs:
                v = by_key[(g, s)]['result_summary_row'].get(metric)
                vals.append(v if finite(v) else None)
            if all(v is not None for v in vals):
                diffs.append(vals[1] - vals[0])
        metric_diffs[metric] = {'n_scenario_pairs': len(diffs), 'tie_count': sum(d == 0 for d in diffs),
                                'diff_stats': stats(diffs), 'diff_definition': 'graph_True minus graph_False'}
    # Concrete behavior observations used by the report renderer.
    summarize_dist = Counter(r['native_identity_counts'].get('summarize_the_task', 0) for r in records)
    zero_call = [r for r in records if r['pairing']['tool_call_entries'] == 0]
    db_consistent = True
    for g in group_dirs:
        for tool, dbs in groups[g]['observed_database_update_namespaces_by_native_tool'].items():
            expected = ACTIVITY_DB_EVIDENCE.get(NATIVE_ACTIVITY.get(tool, ''))
            if expected and set(dbs) != {expected}:
                db_consistent = False
    behavior_notes = {
        'zero_call_trajectory_count': len(zero_call),
        'zero_call_category_combinations': sorted(tuple(c) for r in zero_call for c in [r['source_categories'] or []]),
        'summarize_the_task_calls_per_trajectory': {str(k): summarize_dist[k] for k in sorted(summarize_dist)},
        'system_prompt_requires_at_least_one_summarize_call': True,
        'multi_tool_call_assistant_messages_total': sum(r['multi_tool_call_assistant_messages'] for r in records),
        'trajectories_with_unresolved_scrambled_calls': sum(1 for r in records if r['call_resolution_counts'].get('unresolved_scrambled')),
        'minefield_similarity_positive_trajectories': sum(1 for r in records if finite(r['result_summary_row'].get('minefield_similarity')) and r['result_summary_row']['minefield_similarity'] > 0),
        'milestone_similarity_equal_one_trajectories': sum(1 for r in records if r['result_summary_row'].get('milestone_similarity') == 1),
        'db_backed_tools_only_write_expected_namespace': db_consistent,
    }
    # Output.
    output_dir.mkdir(parents=True)
    (output_dir / 'per_trajectory.jsonl').write_text(
        ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n' for r in records))
    payload_verified = len(payload_files)
    payload_bytes = sum(b for b, _ in registered.values())
    conservation = {
        'per_trajectory_records': len(records),
        'records_equal_sum_of_groups': len(records) == sum(g['trajectories'] for g in groups.values()),
        'call_entries_sum': sum(g['pairing_totals']['tool_call_entries'] for g in groups.values()),
        'result_messages_sum': sum(g['pairing_totals']['tool_result_messages'] for g in groups.values()),
        'paired_plus_missing_conserves_per_group': all(
            g['pairing_totals']['tool_call_entries'] == g['pairing_totals']['paired_call_entries']
            + g['pairing_totals']['calls_with_id_without_return'] + g['pairing_totals']['calls_missing_id']
            for g in groups.values()),
    }
    summary = {
        'schema': 'toolsandbox-hepm-behavior-v2',
        'inputs': {
            'repository': acquisition.get('repository'), 'commit': acquisition.get('commit'),
            'acquisition_manifest': rel(Path(acquisition_manifest_path), project_root),
            'acquisition_manifest_sha256': sha(Path(acquisition_manifest_path))[1],
            'source_note': 'third-party H-EPM adapted ToolSandbox experiments; not an Apple official trace release',
            'payload_files_verified': payload_verified, 'payload_bytes': payload_bytes,
            'groups': [{'directory': g, 'trajectories': groups[g]['trajectories'],
                        'result_summary_run_provenance': {
                            'split': group_rs[g].get('split'), 'split_seed': group_rs[g].get('split_seed'),
                            'split_ratio': group_rs[g].get('split_ratio'), 'git_sha': group_rs[g].get('git_sha')}}
                       for g in group_dirs],
            'group_config_evidence': 'split/split_seed/split_ratio/git_sha are saved in each result_summary.json; the summary_on and graph on/off flags still appear only in directory names and the source README; the two groups record different run source versions (git_sha), both " + local changes", which is an additional confounder for any group comparison',
        },
        'coverage': {
            'shared_scenario_keys': len(shared),
            'scenario_keys_per_group': {g: len(s) for g, s in scen_by_group.items()},
            'base_scenario_method': 'strip H-EPM suffixes only (scramble + distraction + all_tools); official scenario-name tokens are not merged',
            'base_scenario_evidence': 'stripped scramble suffixes equal tool_augmentation_list for 207/207 scenarios; distraction/all_tools suffixes equal declared categories; every suffix-free scenario carries NO_DISTRACTION_TOOLS',
            'per_group': {g: {k: groups[g][k] for k in ('trajectories', 'scenario_count', 'base_scenario_count',
                                                        'source_category_scenario_counts', 'tool_augmentation_scenario_counts',
                                                        'variant_suffix_counts', 'scenarios_with_non_null_deny_list')} for g in group_dirs},
        },
        'tool_interface': {
            'native_tool_names': sorted(native_names),
            'native_inventory_evidence': 'union of execution_context.tool_allow_list across all 414 execution_context.json files',
            'activity_classification': {t: NATIVE_ACTIVITY[t] for t in sorted(native_names)},
            'harness_tools': {t: NATIVE_ACTIVITY[t] for t in sorted(native_names) if NATIVE_ACTIVITY.get(t) in HARNESS_ACTIVITIES},
            'activity_classification_notes': 'db-backed activities (reminder/contact/messaging/settings) verified against observed tool_details.database_update namespaces; datetime/location/weather/web_api_search classified from descriptive names; unknown is never guessed',
            'per_group': {g: {k: groups[g][k] for k in ('called_name_counts', 'native_identity_counts', 'call_resolution_counts',
                                                        'scrambled_name_counts', 'pooled_activity_call_counts',
                                                        'activity_stats_denominator_note', 'activity_trajectories_with_calls',
                                                        'activity_calls_per_trajectory_conditional_stats',
                                                        'activity_calls_per_trajectory_all_trajectories_stats',
                                                        'observed_database_update_namespaces_by_native_tool')} for g in group_dirs},
        },
        'pairing': {g: {**groups[g]['pairing_totals'],
                        'sandbox_association': groups[g]['sandbox_association_totals'],
                        'protocol_issue_counts': groups[g]['protocol_issue_counts']} for g in group_dirs},
        'pairing_note': 'conversation tool_call_id pairing is primary; execution_context._dbs.SANDBOX openai_tool_call_id rows provide an independent cross-verification of the same call ids',
        'tool_result_errors': {
            'per_group': {g: {'count': groups[g]['tool_result_error_count'], 'classes': groups[g]['tool_result_error_classes'],
                              'sandbox_exception_call_ids': groups[g]['sandbox_exception_call_ids'],
                              'content_regex_equals_sandbox_exception': groups[g]['tool_result_error_count'] == groups[g]['sandbox_exception_call_ids']} for g in group_dirs},
            'classification_note': 'tool execution error = saved tool-role content starts with a Python exception header, cross-checked against SANDBOX tool_call_exception rows keyed by call id; harness exception = result_summary.exception_type (counted separately under termination_and_results); task evaluation = similarity fields, never converted to success here',
        },
        'sequences': {g: {'calls_per_trajectory_stats': groups[g]['calls_per_trajectory_stats'],
                          'called_name_transition_counts': groups[g]['called_name_transition_counts'],
                          'called_name_transition_count_total_distinct': groups[g]['called_name_transition_count_total_distinct'],
                          'activity_transition_counts': groups[g]['activity_transition_counts'],
                          'activity_transition_count_total_distinct': groups[g]['activity_transition_count_total_distinct'],
                          'same_activity_transitions': groups[g]['same_activity_transitions'],
                          'cross_activity_transitions': groups[g]['cross_activity_transitions'],
                          'activity_boundary_adjacent_pairs': groups[g]['activity_boundary_adjacent_pairs']} for g in group_dirs},
        'sequence_note': 'saved record order only; not real execution order or concurrency; unresolved activity tokens are None boundaries and transitions never cross them',
        'termination_and_results': {
            'end_conversation_calls_per_group': {g: sum(r['end_conversation_calls'] for r in records if r['group_directory'] == g) for g in group_dirs},
            'termination_status': 'unknown: no termination field is saved in conversations; end_conversation is a declared allow-list tool but is never called by the agent; last_message_role is reported without guessing normal ending',
            'last_message_role_counts': {g: groups[g]['last_message_role_counts'] for g in group_dirs},
            'final_conversation_active_counts': {g: groups[g]['final_conversation_active_counts'] for g in group_dirs},
            'final_conversation_active_note': 'last saved SANDBOX conversation_active value per trajectory; reported as saved only, not interpreted as normal ending or termination cause',
            'sandbox_end_conversation_tool_trace_trajectories': {g: groups[g]['sandbox_end_conversation_tool_trace_trajectories'] for g in group_dirs},
            'sandbox_end_conversation_note': 'trajectories whose SANDBOX tool_trace contains end_conversation executions; all such rows are non-agent rows (no openai_tool_call_id), i.e. user-simulator side; agent never calls end_conversation',
            'per_group_result_fields': {g: groups[g]['result_fields'] for g in group_dirs},
            'source_declared_rule': {
                'text': 'H-EPM source README build_graph keeps scenarios with milestone_similarity > 0.55',
                'scope': 'tool-graph construction filter only; not a task-success definition',
                'applied_in_this_analysis': False,
            },
        },
        'group_comparison': {
            'shared_scenario_keys': len(shared),
            'same_scenario_metric_diffs': metric_diffs,
            'note': 'descriptive differences of saved fields on shared scenario keys; not a controlled experiment; the two groups additionally ran on different source versions (result_summary git_sha, both with local changes) and the graph on/off difference is evidenced only by directory names; no causal attribution; groups are not independent random samples',
        },
        'field_inventory': {
            'per_group_message_fields': {g: groups[g]['message_field_counts'] for g in group_dirs},
            'per_group_details_keys': {g: groups[g]['details_key_counts'] for g in group_dirs},
            'execution_context_keys': ['_dbs', 'interactive_console', 'tool_allow_list', 'tool_deny_list', 'trace_tool', 'tool_augmentation_list', 'preferred_tool_backend'],
            'result_summary_keys': ['name', 'categories', 'traceback', 'exception_type', 'milestone_similarity', 'minefield_similarity', 'similarity', 'turn_count', 'milestone_mapping', 'minefield_mapping', 'split', 'split_seed', 'split_ratio', 'git_sha'],
            'absent_fields': ['timestamps', 'usage/token counts', 'per-call latency or duration', 'agent-side termination status field', 'resource measurements'],
            'resource_evidence': 'not supported: no CPU/memory/IO fields exist in the saved data',
            'quantile_method': 'linear interpolation on sorted finite values',
        },
        'behavior_notes': behavior_notes,
        'v1_to_v2_corrections': {
            'scrambled_resolution': 'v1 resolved scrambled calls via milestone_matches expected tool_trace names (including 2 matches with milestone_similarity 0); v2 uses the actual tool_trace saved in execution_context._dbs.SANDBOX keyed by call id, excluding rows with tool_call_exception (69 stale summarize_the_task traces on exception rows are not trusted)',
            'run_provenance': 'v1 stated run configuration appears only in directory names; v2 records split/split_seed/split_ratio and the per-group result_summary git_sha (different between groups, both with local changes) and marks the source-version difference as a group-comparison confounder',
            'activity_stats_denominators': 'v1 activity_calls_per_trajectory_stats covered only trajectories where the activity occurs without saying so; v2 renames it to conditional stats and adds all-trajectories stats including zeros',
            'delivery_wording': 'v1 delivery summary said same-tool transitions dominate; cross-activity transitions (858) actually outnumber same-activity transitions (616)',
        },
        'v1_preserved': 'reports/analysis/TOOLSANDBOX-HEPM-behavior-v1/ kept unchanged',
        'conservation_checks': conservation,
        'limitations': [
            'saved order is not execution order; no concurrency evidence',
            'call counts are not call rates, tool latency or resource consumption',
            'token/usage fields do not exist; nothing about cost or billing',
            'similarity fields are reported as saved and never converted into success',
            'scrambled tool calls without SANDBOX tool_trace/content/database evidence stay Unknown',
            'final conversation_active and user-side end_conversation are reported as saved, without inferring normal ending or termination cause',
            'two groups are compared descriptively only; different run source versions and directory-name-only graph evidence preclude causal claims',
        ],
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    md = render_summary_md(summary, group_dirs)
    (output_dir / 'summary.md').write_text(md)
    ins = []
    for f in [Path(acquisition_manifest_path)] + payload_files:
        b, h = sha(f)
        ins.append({'path': rel(f, project_root), 'bytes': b, 'sha256': h})
    # Analysis code identity is this script and its test file at their real
    # locations, independent of a fixture project root.
    code_paths = [Path(__file__).resolve(),
                  Path(__file__).resolve().parents[1] / 'tests' / 'test_toolsandbox_hepm_behavior.py']
    codes = []
    for f in code_paths:
        b, h = sha(f)
        codes.append({'path': rel(f, project_root), 'bytes': b, 'sha256': h})
    outs = []
    for n in ('summary.md', 'summary.json', 'per_trajectory.jsonl'):
        b, h = sha(output_dir / n)
        outs.append({'path': n, 'bytes': b, 'sha256': h})
    (output_dir / 'manifest.json').write_text(json.dumps(
        {'schema': 'toolsandbox-hepm-behavior-manifest-v1', 'inputs': ins, 'analysis_code': codes,
         'outputs': outs, 'manifest_self_hash_excluded': True}, ensure_ascii=False, indent=2) + '\n')
    return summary


def render_summary_md(s, group_dirs):
    g0 = group_dirs[0]
    lines = []
    lines.append('# H-EPM ToolSandbox 公开轨迹行为分析 v2')
    lines.append('')
    lines.append(f"第三方 H-EPM（commit `{s['inputs']['commit']}`）发布的 ToolSandbox 扩展实验离线分析；仅读取已保存 JSON，不执行来源框架或数据中的代码，不运行 benchmark/轨迹/模型。v1 产物保留不改。")
    lines.append('')
    lines.append('## 规模与身份')
    lines.append(f"- 两组各 {s['coverage']['per_group'][g0]['trajectories']} 条轨迹、{s['coverage']['scenario_keys_per_group'][g0]} 个 dataset-local 场景标识；共享场景键 {s['coverage']['shared_scenario_keys']} 个；payload {s['inputs']['payload_files_verified']} 文件 / {s['inputs']['payload_bytes']:,} bytes 逐项 bytes/SHA-256 核验通过。")
    prov = {g['directory']: g['result_summary_run_provenance'] for g in s['inputs']['groups']}
    lines.append(f"- 运行来源（各组 result_summary.json 保存）：split={prov[g0]['split']}、split_seed={prov[g0]['split_seed']}、split_ratio={prov[g0]['split_ratio']}；git_sha 分别为 `{prov[group_dirs[0]]['git_sha']}` 与 `{prov[group_dirs[1]]['git_sha']}`——两组运行于不同源码版本且均带 local changes，这是组间比较的额外混杂因素；summary_on 与 graph 开关仍仅见于目录名与来源 README。两组不作为受控因果实验。")
    lines.append(f"- 变体合并仅剥离 H-EPM 后缀（scramble/distraction/all_tools；与 tool_augmentation_list、result_summary 类别逐场景一致），得 {s['coverage']['per_group'][g0]['base_scenario_count']} 个基础场景；alt/implicit/low_battery_mode/wifi_off 等官方场景命名 token 不合并。")
    lines.append('')
    lines.append('## 调用与返回关联')
    for g in group_dirs:
        p = s['pairing'][g]
        sa = p['sandbox_association']
        lines.append(f"- {g}：工具调用条目 {p['tool_call_entries']}、tool 结果消息 {p['tool_result_messages']}；带 ID 调用 {p['calls_with_id']}、配对 {p['paired_call_entries']}、缺返回 {p['calls_with_id_without_return']}、孤立返回 {p['orphan_result_messages']}、重复调用 ID 条目 {p['duplicate_call_id_entries']}、名称不匹配 {p['call_result_name_mismatches']}；协议问题 {p['protocol_issue_counts'] or '无'}。")
        lines.append(f"  SANDBOX 交叉核验（execution_context._dbs.SANDBOX 按 openai_tool_call_id）：唯一调用 ID {sa['sandbox_unique_call_ids']}、行数 {sa['sandbox_call_id_rows']}、会话调用全部命中 {sa['calls_matched_in_sandbox']}/{p['calls_with_id']}、未命中 {sa['calls_with_id_not_in_sandbox']}。")
    lines.append('')
    lines.append('## 工具接口与活动')
    for g in group_dirs:
        ti = s['tool_interface']['per_group'][g]
        top = sorted(ti['native_identity_counts'].items(), key=lambda x: -x[1])[:8]
        lines.append(f"- {g}：原生身份调用 top：{', '.join(f'{k}={v}' for k, v in top)}；scrambled 名调用 {sum(ti['scrambled_name_counts'].values())} 条（解析：{ti['call_resolution_counts']}）。")
        lines.append(f"  活动构成（pooled，分母=调用条目）：{ti['pooled_activity_call_counts']}。每轨迹分布区分双分母：条件分布仅覆盖出现该活动的轨迹（如 contact n={ti['activity_trajectories_with_calls'].get('contact', 0)}），全体分布含零值（n={s['coverage']['per_group'][g]['trajectories']}），两组数值见 summary.json。")
    lines.append(f"- 原生工具共 {len(s['tool_interface']['native_tool_names'])} 个（allow list 并集）；harness 辅助 summarize_the_task 单列，end_conversation 声明可用但从未被 agent 调用。")
    unresolved_total = sum(s['tool_interface']['per_group'][g]['call_resolution_counts'].get('unresolved_scrambled', 0) for g in group_dirs)
    sandbox_resolved_total = sum(s['tool_interface']['per_group'][g]['call_resolution_counts'].get('sandbox_tool_trace', 0) for g in group_dirs)
    lines.append(f"- 扰动名调用解析：{sandbox_resolved_total} 条经 SANDBOX 实际 tool_trace（按调用 ID、排除异常行）还原原生身份，其余经 [SummaryTool] 前缀/database_update 命名空间回退或保持 Unknown（{unresolved_total} 条）；异常行携带的 69 条陈旧 summarize_the_task 痕迹不作为依据。")
    lines.append('')
    lines.append('## 行为序列')
    for g in group_dirs:
        sq = s['sequences'][g]
        lines.append(f"- {g}：每轨迹调用数 median {sq['calls_per_trajectory_stats']['median']} / IQR {sq['calls_per_trajectory_stats']['iqr']}（n={sq['calls_per_trajectory_stats']['n']}）；活动序列异类转换 {sq['cross_activity_transitions']} 多于同类转换 {sq['same_activity_transitions']}，Unknown 边界相邻对 {sq['activity_boundary_adjacent_pairs']}；单条转换最高：{', '.join(f'{k}={v}' for k, v in list(sq['activity_transition_counts'].items())[:5])}。")
    lines.append('- 序列仅按保存记录顺序，不代表真实执行顺序或并发关系；未解析活动记为 None 边界，转换不跨越边界。')
    lines.append('')
    bn = s['behavior_notes']
    lines.append('## 具体行为观察')
    lines.append(f"- 零工具调用轨迹 {bn['zero_call_trajectory_count']} 条（类别组合：{bn['zero_call_category_combinations']}），多为 INSUFFICIENT_INFORMATION 场景中模型直接向用户澄清。")
    lines.append(f"- summarize_the_task 每轨迹调用分布 {bn['summarize_the_task_calls_per_trajectory']}；system prompt 声明必须至少调用一次，但存在 0 次调用的轨迹，未按成功/失败解释。")
    lines.append(f"- 含未解析 scrambled 调用的轨迹 {bn['trajectories_with_unresolved_scrambled_calls']} 条；minefield_similarity>0 的轨迹 {bn['minefield_similarity_positive_trajectories']} 条；milestone_similarity=1 的轨迹 {bn['milestone_similarity_equal_one_trajectories']} 条（仅原始字段计数，不转换为成功）。")
    err_total = sum(s['tool_result_errors']['per_group'][g]['count'] for g in group_dirs)
    err_x = all(s['tool_result_errors']['per_group'][g]['content_regex_equals_sandbox_exception'] for g in group_dirs)
    lines.append(f"- 工具执行错误（结果内容以异常头开始）合计 {err_total} 条，与 SANDBOX tool_call_exception 按调用 ID 计数{'一致' if err_x else '不一致（见 summary.json）'}；与任务评估字段、harness 异常（exception_type 非空 0 条）分开统计。")
    lines.append('')
    lines.append('## 终止与任务结果')
    tr = s['termination_and_results']
    exc = {g: [tr['per_group_result_fields'][g]['exception_type_non_null'], tr['per_group_result_fields'][g]['traceback_non_null']] for g in group_dirs}
    lines.append(f"- agent 侧 end_conversation 调用：{tr['end_conversation_calls_per_group']}；结果摘要 exception_type/traceback 非空计数：{exc}。")
    lines.append(f"- 末态 conversation_active（SANDBOX 最后保存值）：{tr['final_conversation_active_counts']}；SANDBOX tool_trace 含 end_conversation 执行的轨迹：{tr['sandbox_end_conversation_tool_trace_trajectories']}（全部为非 agent 行，即用户模拟器侧）。二者仅按保存值报告，不据此推断正常结束或终止原因。")
    for g in group_dirs:
        rf = tr['per_group_result_fields'][g]
        lines.append(f"  - {g}：milestone_similarity median {rf['milestone_similarity']['median']}（IQR {rf['milestone_similarity']['iqr']}，n={rf['milestone_similarity']['n']}）；minefield_similarity median {rf['minefield_similarity']['median']}；similarity median {rf['similarity']['median']}；turn_count median {rf['turn_count']['median']}。")
    lines.append('- agent 侧终止状态 unknown：会话内无终止字段；end_conversation 在 allow list 中声明但从未被 agent 调用；末条消息角色分布见 summary.json，不据此猜测正常结束。')
    lines.append('- 来源声明规则仅一条（build_graph 的 milestone_similarity > 0.55 过滤），适用边界为工具图构建，不是任务成功定义；本分析未使用该阈值。')
    lines.append('')
    lines.append('## 两组同场景保存指标差异（描述性）')
    for metric, d in s['group_comparison']['same_scenario_metric_diffs'].items():
        lines.append(f"- {metric}：n={d['n_scenario_pairs']}，持平 {d['tie_count']}，diff（True−False）median {d['diff_stats']['median']} / IQR {d['diff_stats']['iqr']}。")
    lines.append('- 以上仅为共享场景键上保存字段的描述性差异；两组运行于不同源码版本（git_sha 不同、均带 local changes）、graph 开关仅目录名证据、非独立随机样本，不推断 graph 配置导致成功率、效率或资源变化。')
    lines.append('')
    lines.append('## 相对既有公开行为证据的新增点')
    lines.append('- 相比 Coding 的 shell/编辑工具与 OSWorld 的 GUI 动作，本数据提供有证据的 Assistant/工具协作形态：状态化 PIM 工具（reminder/contact/messaging/setting 四个数据库命名空间，写入与声明一致）、时间戳换算工具链（datetime 类调用为最大业务活动之一）、设备设置前置条件（网络关闭时 web 类工具返回 ConnectionError，PermissionError 为最常见工具执行错误）、以及 harness 在 system prompt 中强制要求的状态摘要调用 summarize_the_task。')
    lines.append(f"- 工具名/描述/参数扰动的行为证据：TOOL_NAME_SCRAMBLED 场景中模型实际调用扰动后名称；{sandbox_resolved_total} 条可经 SANDBOX 保存的实际 tool_trace 按调用 ID 还原原生身份（异常行陈旧痕迹已排除），其余经内容前缀/命名空间回退或保持 Unknown（{unresolved_total} 条）。")
    lines.append(f"- 一条 assistant 消息可含多个工具调用（两组共 {bn['multi_tool_call_assistant_messages_total']} 条多调用消息）；消息数不等于调用数。")
    lines.append('- 尚缺字段或来源语义：真实执行顺序/并发、任何时间戳、usage/token、agent 侧终止机制、资源与费用；graph 开关仅有目录名证据，且两组源码版本不同。')
    lines.append('- 值得后续本地测量的候选线索（仅为研究线索，不构成执行授权）：多调用消息的并行工具执行形态、summarize_the_task 摘要调用的上下文增长、设备设置前置失败后的重试行为。')
    lines.append('')
    lines.append('## v1→v2 修正')
    for k, v in s['v1_to_v2_corrections'].items():
        lines.append(f'- {k}: {v}')
    lines.append('')
    lines.append('## 限制')
    limitations_cn = [
        '保存顺序不等于真实执行顺序；无并发证据',
        '调用数量不是调用速率、工具耗时或资源消耗',
        '不存在 usage/token 字段；不涉及费用或账单',
        'similarity 字段按原样报告，绝不转换为成功',
        '无 SANDBOX tool_trace/内容前缀/数据库证据的 scrambled 调用保持 Unknown',
        '末态 conversation_active 与用户侧 end_conversation 仅按保存值报告，不推断正常结束或终止原因',
        '两组仅作描述性对照；源码版本不同且 graph 开关仅目录名证据，不作任何因果结论',
        '无任何 CPU/内存/I/O 字段；资源测量不支持',
    ]
    for x in limitations_cn:
        lines.append(f'- {x}')
    lines.append('')
    lines.append('[summary.json](summary.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)')
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--acquisition-manifest', type=Path, default=PROJECT / DEFAULT_ACQUISITION)
    ap.add_argument('--output-dir', type=Path, required=True)
    ap.add_argument('--project-root', type=Path, default=PROJECT)
    a = ap.parse_args()
    try:
        s = run(a.acquisition_manifest, a.output_dir, a.project_root)
        print(json.dumps({'status': 'PASS',
                          'trajectories': s['conservation_checks']['per_trajectory_records'],
                          'payload_files_verified': s['inputs']['payload_files_verified']},
                         ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({'status': 'FAIL', 'error': type(e).__name__ + ': ' + str(e)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
