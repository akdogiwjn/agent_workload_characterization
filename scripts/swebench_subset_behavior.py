#!/usr/bin/env python3
"""SWEBENCH-subset-behavior-v1: offline behavior analysis of the frozen selection.

Parses three native formats exactly as saved (no normalization across groups):
  sweagent .traj : trajectory[] with {action, observation, response, state, thought},
                   history[] messages, info.exit_status/submission
  moatless .json : transitions[] with {name, state, actions}, info (duration/cost/submission)
  sonar .json    : message list; assistant additional_kwargs.tool_calls (id + function
                   name/arguments); tool messages WITHOUT tool_call_id; blocks (thinking/text)

Conservative activity classification reuses the SWE-rebench v2 rule set
(scripts/swe_rebench_behavior.py activity/shell_argv/command_form) and is applied
ONLY to shell-like command strings (sweagent python/pip/etc action tails, sonar
bash arguments). Dedicated editor interfaces are classified as interface actions,
never as shell. Cross-group aggregates are not computed (different formats and
task sets); per-group stats only.
"""
import json, os, sys, hashlib, importlib.util
from collections import Counter, OrderedDict

ROOT = '/home/lcq/agent_workload_characterization'
B = ROOT + '/data/raw/public/swebench_public_traces/40f164d5b8f1d249bf95a6df8b74b577fd8e519d/experiments'
OUT = ROOT + '/reports/analysis/SWEBENCH-subset-behavior-v1'

_spec = importlib.util.spec_from_file_location('srb', os.path.join(ROOT, 'scripts', 'swe_rebench_behavior.py'))
_srb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_srb)
activity = _srb.activity

# SWE-agent dedicated interface commands (from the action head token)
SWEAGENT_EDITOR = {'create', 'open', 'edit', 'scroll_down', 'scroll_up', 'scroll_to',
                   'find', 'find_file', 'search', 'search_file', 'goto', 'set'}
SWEAGENT_SUBMIT = {'submit'}
# other sweagent action heads that are shell-ish commands (python, pip, ls, cd, rm, ...)
SWEAGENT_SHELLISH = {'python', 'python3', 'pip', 'pip3', 'ls', 'cd', 'rm', 'pwd', 'diff',
                     'find', 'find_file', 'cython', 'git', 'echo', 'cat', 'mkdir', 'cp',
                     'mv', 'grep', 'sed', 'awk', 'touch', 'tar', 'wget', 'curl'}
# NOTE: find/find_file appear in both editor and shell sets; SWE-agent's find/find_file
# are editor interface commands, so editor set takes precedence.

SONAR_EDITOR_TOOL = 'str_replace_based_edit_tool'
SONAR_BASH_TOOL = 'bash'


def classify_sweagent_action(action):
    """Return (interface_name, category, unknown_reason)."""
    if not isinstance(action, str) or not action.strip():
        return None, 'Unknown', 'empty_action'
    head = action.split()[0]
    rest = action[len(head):].strip()
    if head in SWEAGENT_SUBMIT:
        return head, 'Submit-marker', None
    if head in SWEAGENT_EDITOR:
        return head, 'Edit/Write' if head in {'create', 'edit'} else 'Read/Search', None
    # shell-ish or unrecognized: the action text itself is the command line;
    # classify it via the conservative shell rule set (tool interface = bash-equivalent)
    cat, reason, _form = activity('bash', action)
    return head, cat, reason


def classify_sonar_toolcall(name, arguments):
    """Return (interface_name, category, unknown_reason)."""
    if name == SONAR_EDITOR_TOOL:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        except Exception:
            return name, 'Unknown', 'argument_parse_error'
        cmd = args.get('command')
        if cmd in {'view', 'view_range'}:
            return name, 'Read/Search', None
        if cmd in {'create', 'str_replace', 'insert', 'undo_edit'}:
            return name, 'Edit/Write', None
        return name, 'Unknown', 'unknown_editor_command'
    if name in (SONAR_BASH_TOOL, 'bash_terminal', 'shell', 'terminal'):
        cat, reason, _form = activity(name, arguments if isinstance(arguments, str) else None)
        return name, cat, reason
    return name, 'Unknown', 'unrecognized_tool'


def analyze_sweagent(path, task_id):
    o = json.load(open(path))
    traj = o.get('trajectory') or []
    rec = {
        'format': 'sweagent-traj',
        'task_id': task_id,
        'structure': {
            'trajectory_entries': len(traj),
            'history_messages': len(o.get('history') or []),
            'history_roles': dict(Counter(m.get('role') for m in (o.get('history') or []) if isinstance(m, dict))),
            'entry_fields': sorted(set(k for e in traj for k in e.keys())),
        },
        'interface_counts': Counter(),
        'activity_counts': Counter(),
        'unknown_reasons': Counter(),
        'transitions': Counter(),
        'anomalies': {},
    }
    prev_cat = None
    obs_missing = 0
    for e in traj:
        iface, cat, reason = classify_sweagent_action(e.get('action'))
        rec['interface_counts'][iface or 'None'] += 1
        rec['activity_counts'][cat] += 1
        if reason:
            rec['unknown_reasons'][reason] += 1
        if cat == 'Unknown':
            rec['transitions']['%s->Unknown' % (prev_cat or 'START')] += 1
            prev_cat = None
        else:
            if prev_cat:
                rec['transitions']['%s->%s' % (prev_cat, cat)] += 1
            prev_cat = cat
        if 'observation' not in e:
            obs_missing += 1
    if obs_missing:
        rec['anomalies']['entries_without_observation'] = obs_missing
    info = o.get('info') or {}
    rec['termination'] = {'source': 'info.exit_status', 'value': info.get('exit_status'),
                          'explicit_in_trajectory': True}
    rec['submission_patch_present'] = bool(info.get('submission'))
    rec['evaluation_in_trajectory'] = False
    return rec


def analyze_moatless(path, task_id):
    o = json.load(open(path))
    trs = o.get('transitions') or []
    rec = {
        'format': 'moatless-transitions',
        'task_id': task_id,
        'structure': {
            'transitions': len(trs),
            'transition_names': [t.get('name') for t in trs],
            'branch_markers': None,  # filled below
            'action_parameter_fields': sorted(set(k for t in trs for a in (t.get('actions') or []) for k in (a.get('action') or {}).keys())),
        },
        'interface_counts': Counter(t.get('name') for t in trs),
        'activity_counts': Counter(),
        'unknown_reasons': Counter(),
        'transitions': Counter(),
        'anomalies': {},
    }
    # search-flow structure: linear saved sequence of named transitions; no explicit
    # branch/parent ids -> report saved structure only, never a linear execution claim
    branch_keys = set(k for t in trs for k in t.keys())
    rec['structure']['branch_markers'] = sorted(k for k in branch_keys if k in {'parent', 'children', 'branch_id', 'node_id'})
    prev = None
    for t in trs:
        name = t.get('name')
        # map search-flow node names to broad activity families (saved-structure semantics,
        # NOT execution claims)
        if name in ('SearchCode', 'IdentifyCode'):
            cat = 'Read/Search'
        elif name == 'EditCode':
            cat = 'Edit/Write'
        elif name == 'PlanToCode':
            cat = 'Plan'
        elif name == 'Finished':
            cat = 'Finished'
        else:
            cat = 'Unknown'
            rec['unknown_reasons']['unknown_transition_name'] += 1
        rec['activity_counts'][cat] += 1
        rec['transitions']['%s->%s' % (prev or 'START', name)] += 1
        prev = name
    # actions without commands: EditCode actions carry content, SearchCode carry
    # structured params - no shell commands to classify; record that explicitly
    rec['shell_command_classification'] = 'not_applicable_no_shell_commands_saved'
    info = o.get('info') or {}
    finished = bool(trs) and trs[-1].get('name') == 'Finished'
    rec['last_saved_transition'] = {'value': trs[-1].get('name') if trs else None, 'reached_Finished': finished}
    rec['termination'] = {'source': 'none', 'value': None, 'explicit_in_trajectory': False,
                          'note': 'last saved transition is not a verified termination reason'}
    rec['submission_patch_present'] = bool(info.get('submission'))
    rec['in_trajectory_fields'] = {k: True for k in info if k in ('duration', 'total_cost')}
    rec['evaluation_in_trajectory'] = False
    return rec


def analyze_sonar(path, task_id):
    msgs = json.load(open(path))
    rec = {
        'format': 'sonar-message-list',
        'task_id': task_id,
        'structure': {
            'messages': len(msgs),
            'roles': dict(Counter(m.get('role') for m in msgs if isinstance(m, dict))),
            'block_types': dict(Counter(b.get('block_type') for m in msgs for b in (m.get('blocks') or []))),
        },
        'interface_counts': Counter(),
        'activity_counts': Counter(),
        'unknown_reasons': Counter(),
        'transitions': Counter(),
        'anomalies': {},
    }
    call_ids = []
    tool_msgs = 0
    prev_cat = None
    for m in msgs:
        role = m.get('role')
        if role == 'assistant':
            for tc in (m.get('additional_kwargs') or {}).get('tool_calls') or []:
                fn = tc.get('function') or {}
                name = fn.get('name')
                args = fn.get('arguments')
                rec['interface_counts'][name] += 1
                _iface, cat, reason = classify_sonar_toolcall(name, args)
                rec['activity_counts'][cat] += 1
                if reason:
                    rec['unknown_reasons'][reason] += 1
                call_ids.append(tc.get('id'))
                if cat == 'Unknown':
                    rec['transitions']['%s->Unknown' % (prev_cat or 'START')] += 1
                    prev_cat = None
                else:
                    if prev_cat:
                        rec['transitions']['%s->%s' % (prev_cat, cat)] += 1
                    prev_cat = cat
        elif role == 'tool':
            tool_msgs += 1
    dup_ids = len(call_ids) - len(set(i for i in call_ids if i))
    if dup_ids:
        rec['anomalies']['duplicate_tool_call_ids'] = dup_ids
    # association protocol: tool messages carry NO tool_call_id in this corpus
    rec['anomalies']['tool_messages_without_tool_call_id'] = tool_msgs
    rec['association'] = {'tool_calls_with_id': len(call_ids), 'tool_result_messages': tool_msgs,
                          'explicit_id_linkage': False,
                          'note': 'tool result messages lack tool_call_id; calls and results counted separately, no positional pairing'}
    rec['termination'] = {'source': 'none', 'value': None, 'explicit_in_trajectory': False,
                          'note': 'last message is assistant text; no exit/submission field in format'}
    rec['submission_patch_present'] = False
    rec['evaluation_in_trajectory'] = False
    return rec


ANALYZERS = {
    '20240620_sweagent_claude3.5sonnet': ('verified', analyze_sweagent),
    '20240617_moatless_gpt4o': ('lite', analyze_moatless),
    '20251219_sonar-foundation-agent_claude-opus-4-5': ('test', analyze_sonar),
}


def main():
    sel = json.load(open(OUT + '/selection.json'))
    rows = []
    errors = []
    for g in sel['groups']:
        sub = g['submission']
        split, fn = ANALYZERS[sub]
        for item in g['items']:
            p = os.path.join(ROOT, item['file'])
            try:
                with open(p) as f:
                    head = f.read(1)
                if head not in '{[':
                    raise ValueError('not JSON')
                rec = fn(p, item['task_id'])
                rec['source'] = 's3://swe-bench-submissions/%s/%s/trajs' % (split if split != 'verified' else 'verified', sub)
                rec['submission'] = sub
                rec['split'] = split
                rec['file'] = item['file']
                rec['activity_counts'] = dict(rec['activity_counts'])
                rec['interface_counts'] = dict(rec['interface_counts'])
                rec['unknown_reasons'] = dict(rec['unknown_reasons'])
                rec['transitions'] = dict(rec['transitions'])
                rows.append(rec)
            except Exception as e:
                errors.append({'file': item['file'], 'error': str(e)[:200]})
    # write per-trajectory
    with open(OUT + '/per_trajectory.jsonl', 'w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    # per-group aggregates (no cross-group pooling)
    summary_groups = {}
    for g in sel['groups']:
        sub = g['submission']
        rs = [r for r in rows if r['submission'] == sub]
        agg = {
            'n_selected': g['selected_n'], 'n_analyzed': len(rs),
            'format': rs[0]['format'] if rs else None,
            'interface_totals': dict(sum((Counter(r['interface_counts']) for r in rs), Counter())),
            'activity_totals': dict(sum((Counter(r['activity_counts']) for r in rs), Counter())),
            'unknown_reasons': dict(sum((Counter(r['unknown_reasons']) for r in rs), Counter())),
            'transition_totals_top': dict(sum((Counter(r['transitions']) for r in rs), Counter()).most_common(12)),
            'termination_values': dict(Counter(str(r['termination'].get('value')) for r in rs)),
            'last_saved_transition_values': dict(Counter(str(r['last_saved_transition']['value']) for r in rs if 'last_saved_transition' in r)),
            'submission_patch_present_n': sum(1 for r in rs if r.get('submission_patch_present')),
            'evaluation_in_trajectory_any': any(r.get('evaluation_in_trajectory') for r in rs),
            'anomaly_totals': {},
        }
        # medians for per-trajectory message/entry counts
        def med(vals):
            s = sorted(vals)
            return s[len(s) // 2] if s else None
        key_map = {
            'sweagent-traj': ('structure', 'trajectory_entries'),
            'moatless-transitions': ('structure', 'transitions'),
            'sonar-message-list': ('structure', 'messages'),
        }
        k1, k2 = key_map[agg['format']]
        vals = [r['structure'][k2] for r in rs]
        s_vals = sorted(vals)
        agg['per_trajectory_size'] = {'median': med(vals), 'min': s_vals[0] if s_vals else None,
                                      'max': s_vals[-1] if s_vals else None, 'n': len(vals)}
        anomaly_counter = Counter()
        for r in rs:
            for k, v in r['anomalies'].items():
                anomaly_counter[k] += v if isinstance(v, int) else 1
        agg['anomaly_totals'] = dict(anomaly_counter)
        summary_groups[sub] = agg
    summary = {
        'schema': 'swebench-subset-behavior-summary-v1',
        'generated_at_utc': '2026-10-07',
        'selection': 'selection.json (frozen before analysis)',
        'n_trajectories': len(rows), 'n_errors': len(errors), 'errors': errors,
        'groups': summary_groups,
        'method_notes': {
            'activity_rules': 'SWE-rebench v2 conservative shell rule set reused verbatim (scripts/swe_rebench_behavior.py activity); applied only to shell-like command strings; dedicated editor interfaces classified as interface actions',
            'no_cross_group_aggregation': 'three groups use different saved formats and different task sets; only per-group statistics reported',
            'unknown_breaks_sequence': 'Unknown entries break the saved-sequence transition counting (START after Unknown)',
            'no_resource_claims': 'no CPU/memory/IO/duration-as-resource/bill claims; moatless info.duration/total_cost reported only as saved fields',
        },
    }
    json.dump(summary, open(OUT + '/summary.json', 'w'), indent=1, ensure_ascii=False)
    print('analyzed %d trajectories, %d errors' % (len(rows), len(errors)))
    for sub, agg in summary_groups.items():
        print('\n==', sub, '(%s, n=%d)' % (agg['format'], agg['n_analyzed']))
        print('  interfaces:', dict(Counter(agg['interface_totals']).most_common(8)))
        print('  activities:', agg['activity_totals'])
        print('  termination:', agg['termination_values'])
        print('  anomalies:', agg['anomaly_totals'])


if __name__ == '__main__':
    main()
