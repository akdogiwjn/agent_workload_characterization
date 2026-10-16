#!/usr/bin/env python3
"""Offline public-trace operation and toolkit census. No recorded code is run.

All registered local SWE-bench objects are inventoried. Only explicit structured
actions/calls and Moatless transitions are interpreted; prose is not tool evidence.
Existing OSWorld/H-EPM/macro results remain source-separated and immutable.
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from agent_workload_characterization.analyzers.public_operations import (
    LABELS, SHELL, NATIVE, classify_call, classify_command, result, shares,
)

ACQUISITIONS = ('BULK-NONVIDEO-20260929', 'SWEBENCH-CONTINUATION-20260930',
                'SWEBENCH-SUPPLEMENT-20261006')
PACKAGES = ('SWE-REBENCH-behavior-v2', 'SWEBENCH-subset-behavior-v1',
            'OSWORLD-task-behavior-v3', 'TOOLSANDBOX-HEPM-behavior-v2',
            'AGENTX-APPLIED-MACRO-v1')
REBENCH = 'data/raw/public/swe_rebench_nonofficial/cdae27cdd16673f0c682871ad55d325f24cc7020'
SWEBENCH = 'data/raw/public/swebench_public_traces/40f164d5b8f1d249bf95a6df8b74b577fd8e519d'


def digest(data): return hashlib.sha256(data).hexdigest()


class Inputs:
    def __init__(self, root): self.root = Path(root); self.files = {}

    def read(self, path, expected=None):
        path = Path(path)
        path = path if path.is_absolute() else self.root / path
        name = str(path.relative_to(self.root))
        data = path.read_bytes()
        item = {'path': name, 'bytes': len(data), 'sha256': digest(data)}
        if expected is not None and (expected.get('sha256') != item['sha256'] or
                                    expected.get('bytes', len(data)) != len(data)):
            raise ValueError('input identity mismatch: ' + name)
        if name in self.files and self.files[name] != item: raise ValueError('input changed: ' + name)
        self.files[name] = item
        return data

    def json(self, path, expected=None): return json.loads(self.read(path, expected))

    def package(self, name):
        directory = 'reports/analysis/' + name + '/'
        manifest = self.json(directory + 'manifest.json')
        for item in manifest['outputs']:
            path = item['path'] if '/' in item['path'] else directory + item['path']
            self.read(path, item)
        return self.json(directory + 'summary.json'), manifest


def load_registrations(inputs):
    entries = {}; conflicts = {}
    for name in ACQUISITIONS:
        manifest_path = 'data/catalog/public_trace_acquisition/' + name + '/manifest.json'
        manifest = inputs.json(manifest_path)
        for item in manifest['inputs']:
            if not item['path'].startswith(SWEBENCH + '/') or item.get('role') != 'trajectory': continue
            item = {**item, 'acquisition_manifest': manifest_path}
            old = entries.get(item['path'])
            if old and (old['bytes'], old['sha256']) != (item['bytes'], item['sha256']):
                conflicts.setdefault(item['path'], [old])
                conflicts[item['path']].append(item)
                entries.pop(item['path'], None)
                continue
            if item['path'] not in conflicts: entries.setdefault(item['path'], item)
    return entries, conflicts


def arguments(value):
    if isinstance(value, str):
        try: return json.loads(value), None
        except (ValueError, TypeError): return None, 'unparseable_arguments'
    return value, None if isinstance(value, (dict, list)) else 'missing_arguments'


def message_tool_records(messages, group=None):
    """Extract only explicit assistant action blocks, plus separate returns."""
    units = []; returns = []; duplicate_ids = Counter(); seen = {}

    def add(tool, args, position, call_id=None, protocol='message_action'):
        arg, error = arguments(args)
        unit = {'tool': str(tool or 'missing'), 'arguments': arg, 'argument_error': error,
                'position': position, 'call_id': call_id, 'protocol': protocol}
        if call_id:
            signature = (unit['tool'], json.dumps(arg, sort_keys=True, ensure_ascii=False, default=str))
            if call_id in seen:
                duplicate_ids['exact' if seen[call_id] == signature else 'conflicting'] += 1
                return
            seen[call_id] = signature
        units.append(unit)

    def xml_blocks(content, mi):
        # OpenHands-style action envelopes. Only assistant messages are passed here;
        # system/user examples and tool output are never searched for calls.
        for ci, match in enumerate(re.finditer(r'<function=([A-Za-z_][\w.-]*)>(.*?)</function>', content, re.S)):
            params = {}
            for pm in re.finditer(r'<parameter=([A-Za-z_][\w.-]*)>(.*?)</parameter>', match.group(2), re.S):
                params[pm.group(1)] = html.unescape(pm.group(2)).strip()
            yield match.start(), match.group(1), params, ci

    for mi, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        role = message.get('role')
        content = message.get('content')
        # Explicit return records, not inferred by matching array positions.
        if role in ('tool', 'function'):
            returns.append({'call_id': message.get('tool_call_id'), 'tool': message.get('name'),
                            'position': mi, 'status': 'saved_tool_message'})
        if isinstance(content, list):
            for ci, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'tool_result':
                    returns.append({'call_id': block.get('tool_use_id'), 'tool': None,
                                    'position': [mi, ci],
                                    'status': 'error' if block.get('is_error') else 'saved_tool_result'})
        if role == 'user':
            text = content if isinstance(content, str) else ''
            for match in re.finditer(r'EXECUTION RESULT of \[([^\]]+)\]', text):
                returns.append({'call_id': None, 'tool': match.group(1), 'position': mi,
                                'status': 'saved_execution_result_without_id'})
            if group and '20241125_marscode-agent-dev' in group:
                for match in re.finditer(r'(?m)^\s*###\s*Observation\s*:', text):
                    returns.append({'call_id': None, 'tool': None, 'position': [mi, match.start()],
                                    'status': 'saved_marscode_observation_without_call_id'})
            if group and '20250118_codeshellagent' in group:
                for match in re.finditer(r'USER:\s*OBSERVATION:', text):
                    returns.append({'call_id': None, 'tool': None, 'position': [mi, match.start()],
                                    'status': 'saved_codeshell_observation_without_call_id'})
            continue
        if role != 'assistant':
            continue

        extra = message.get('additional_kwargs') if isinstance(message.get('additional_kwargs'), dict) else {}
        calls = message.get('tool_calls', extra.get('tool_calls'))
        structured_seen = False
        if isinstance(calls, list):
            structured_seen = True
            for ci, call in enumerate(calls):
                fn = call.get('function', {}) if isinstance(call, dict) else {}
                raw_args = fn.get('arguments')
                call_id = call.get('id') if isinstance(call, dict) else None
                add(fn.get('name', 'missing'), raw_args, [mi, ci], call_id, 'explicit_tool_calls')
        if isinstance(content, list):
            for ci, block in enumerate(content):
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    structured_seen = True
                    add(block.get('name'), block.get('input'), [mi, ci], block.get('id'), 'anthropic_tool_use')
        if structured_seen:
            continue
        if isinstance(content, list):
            content = '\n'.join(str(x.get('text', '')) for x in content if isinstance(x, dict) and isinstance(x.get('text'), str))
        if not isinstance(content, str):
            continue

        # XML calls are accepted only for the inspected source groups whose
        # saved assistant format documents this as an action envelope.
        if group and ('20250203_openhands' in group or '20250616_Skywork-SWE-32B' in group):
            for offset, tool, params, ordinal in xml_blocks(content, mi):
                add(tool, params, [mi, offset], None, 'assistant_function_xml')
        if group and '20250522_tools_claude-4-opus' in group and '<antml:function_calls>' in content:
            antml_units, antml_returns = _antml_records(content)
            for unit in antml_units:
                add(unit['tool'], unit['arguments'], [mi, unit['position']], None, 'antml_invoke')
            returns.extend(antml_returns)
        # The following direct tags are enabled only for the inspected CodeShell
        # assistant protocol; user/system prompt examples are never considered.
        if group and '20250118_codeshellagent' in group:
            for tag in ('execute_bash', 'execute_ipython'):
                for match in re.finditer(rf'<{tag}>(.*?)</{tag}>', content, re.S):
                    add(tag, {'command': html.unescape(match.group(1)).strip()}, [mi, match.start()], None,
                        'assistant_execute_tag')
            for match in re.finditer(r'<file_edit\s+path=["\']([^"\']+)["\']\s*>(.*?)</file_edit>', content, re.S):
                add('file_edit', {'path': html.unescape(match.group(1)), 'content': html.unescape(match.group(2))},
                    [mi, match.start()], None, 'assistant_file_edit_tag')
        # Marscode serializes actions as one explicit ### Action fenced block.
        for match in re.finditer(r'(?ms)^\s*###\s*Action:\s*```(bash|sh|shell|diff)\s*\n(.*?)\n```', content):
            lang, body = match.group(1).lower(), match.group(2).strip()
            add('patch_action' if lang == 'diff' else 'shell_action',
                {'patch': body} if lang == 'diff' else {'command': body}, [mi, match.start()], None,
                'marscode_fenced_action')

    return units, returns, dict(duplicate_ids)


def _file_edit_blocks(text):
    """Read the observed finite file_edit attribute grammar without XML recovery."""
    units = []; candidates = 0; closed_candidates = 0; rejected = Counter(); pos = 0
    while True:
        match = re.search(r'(?m)^[ \t]*<file_edit\b([^>]*)>', text[pos:], re.I | re.S)
        if not match: break
        start = pos + match.start(); body_start = pos + match.end(); candidates += 1
        raw_attrs = match.group(1); cursor = 0; attrs = {}; valid = True
        attr_re = re.compile(r'\s*([A-Za-z_][\w-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')
        while cursor < len(raw_attrs):
            if raw_attrs[cursor:].strip() == '': break
            parsed = attr_re.match(raw_attrs, cursor)
            if not parsed:
                valid = False; break
            key = parsed.group(1).lower()
            value = next(v for v in parsed.groups()[1:] if v is not None)
            if key in attrs: valid = False; break
            attrs[key] = html.unescape(value); cursor = parsed.end()
        end = re.search(r'</file_edit\s*>', text[body_start:], re.I)
        if not end:
            rejected['unclosed_block'] += 1; break
        closed_candidates += 1
        body_end = body_start + end.start(); close_end = body_start + end.end()
        if not valid or not attrs.get('path'):
            rejected['malformed_or_missing_path_attribute'] += 1
        else:
            units.append({'tool': 'file_edit', 'arguments': {'path': attrs['path'],
                          'attributes': attrs, 'content': html.unescape(text[body_start:body_end])},
                          'position': start, 'call_id': None,
                          'protocol': 'learn_by_interact_file_edit_tag'})
        pos = close_end
    return units, {'candidate_count': candidates, 'closed_candidate_count': closed_candidates,
                   'extracted_count': len(units),
                   'rejected_or_ambiguous_count': sum(rejected.values()),
                   'rejection_reasons': dict(rejected)}


def _learn_by_interact_strings(messages):
    """Extract explicit assistant action envelopes, stopping at saved observations."""
    units = []; returns = []; file_edit_detail = Counter(); rejected = Counter()
    for mi, content in enumerate(messages):
        if not isinstance(content, str): continue
        boundary = re.search(r'(?m)^USER:', content)
        assistant_text = content[:boundary.start()] if boundary else content
        for tag in ('execute_bash', 'execute_ipython'):
            for match in re.finditer(rf'<{tag}>(.*?)</{tag}>', assistant_text, re.S):
                units.append({'tool': tag, 'arguments': {'command': html.unescape(match.group(1)).strip()},
                              'position': [mi, match.start()], 'call_id': None,
                              'protocol': 'learn_by_interact_action_tag'})
        edits, detail = _file_edit_blocks(assistant_text)
        file_edit_detail['candidate_count'] += detail['candidate_count']
        file_edit_detail['closed_candidate_count'] += detail['closed_candidate_count']
        file_edit_detail['extracted_count'] += detail['extracted_count']
        file_edit_detail['rejected_or_ambiguous_count'] += detail['rejected_or_ambiguous_count']
        rejected.update(detail['rejection_reasons'])
        for edit in edits:
            edit['position'] = [mi, edit['position']]
            units.append(edit)
        if boundary:
            for match in re.finditer(r'USER:\s*OBSERVATION:', content[boundary.start():]):
                returns.append({'call_id': None, 'position': [mi, boundary.start() + match.start()],
                                'status': 'saved_observation_without_call_id'})
    return units, returns, {'file_edit_candidates': file_edit_detail['candidate_count'],
                            'file_edit_closed_candidates': file_edit_detail['closed_candidate_count'],
                            'file_edit_extracted': file_edit_detail['extracted_count'],
                            'file_edit_rejected_or_ambiguous': file_edit_detail['rejected_or_ambiguous_count'],
                            'file_edit_rejection_reasons': dict(rejected)}


def _sage_messages(messages):
    units = []; returns = []; rejected = Counter(); marker_count = 0; other_action_candidates = 0
    command_marker = re.compile(r'(?m)^[ \t]*Running command:[ \t]*')
    return_pattern = re.compile(r'<return_code>\s*(.*?)\s*</return_code>', re.S | re.I)
    for mi, message in enumerate(messages):
        if not isinstance(message, dict): continue
        content = message.get('content')
        if message.get('role') == 'assistant' and isinstance(content, str):
            other_action_candidates += int(bool(message.get('tool_calls')))
            other_action_candidates += int(isinstance(message.get('function_call'), dict))
            other_action_candidates += len(re.findall(r'(?m)^[ \t]*(?:<function=|<action>|<execute_bash>|<execute_ipython>)', content))
            markers = list(command_marker.finditer(content)); marker_count += len(markers)
            for index, marker in enumerate(markers):
                end = markers[index + 1].start() if index + 1 < len(markers) else len(content)
                command = content[marker.end():end].strip()
                if not command:
                    rejected['empty_running_command'] += 1; continue
                units.append({'tool': 'bash', 'arguments': {'command': command},
                              'position': [mi, marker.start()], 'call_id': None,
                              'protocol': 'sage_running_command'})
        if message.get('role') == 'user' and isinstance(content, str):
            for ri, match in enumerate(return_pattern.finditer(content)):
                code = match.group(1).strip()
                returns.append({'call_id': None, 'tool': 'bash', 'position': [mi, match.start()],
                                'return_index': ri, 'status': 'saved_return_code',
                                'exit_code': int(code) if re.fullmatch(r'-?\d+', code) else None})
    adjacent_returns = sum(1 for unit in units
                           if isinstance(unit['position'], list) and unit['position'][0] + 1 < len(messages)
                           and isinstance(messages[unit['position'][0] + 1], dict)
                           and messages[unit['position'][0] + 1].get('role') == 'user'
                           and isinstance(messages[unit['position'][0] + 1].get('content'), str)
                           and return_pattern.search(messages[unit['position'][0] + 1]['content']))
    return units, returns, {'candidate_action_segment_count': marker_count,
                            'extracted_action_segment_count': len(units),
                            'rejected_or_ambiguous_segment_count': sum(rejected.values()) + other_action_candidates,
                            'rejection_reasons': dict(rejected),
                            'other_explicit_action_protocol_candidates': other_action_candidates,
                            'adjacent_following_return_code_record_count': adjacent_returns,
                            'return_records_have_native_call_ids': False}


def _swe_exp_process_nodes(obj):
    if not isinstance(obj, list): return None
    units = []; candidate_nodes = 0; rejected = Counter(); instructor_types = Counter()
    node_id_present = assistant_strings = observation_strings = 0
    for index, node in enumerate(obj):
        if not isinstance(node, dict): continue
        if not any(key in node for key in ('assistant', 'observation', 'node_id')): continue
        candidate_nodes += 1
        node_id_present += node.get('node_id') is not None
        assistant_strings += isinstance(node.get('assistant'), str)
        observation_strings += isinstance(node.get('observation'), str)
        if not all(key in node for key in ('assistant', 'observation')):
            rejected['missing_assistant_or_observation'] += 1; continue
        instructor = node.get('instructor')
        if isinstance(instructor, dict) and isinstance(instructor.get('ty'), str): instructor_types[instructor['ty']] += 1
        units.append({'tool': 'saved_process_node', 'arguments': None, 'position': index,
                      'call_id': None, 'protocol': 'swe_exp_process_node',
                      'node_id': node.get('node_id'),
                      'instructor_type': instructor.get('ty') if isinstance(instructor, dict) else None})
    if not candidate_nodes: return None
    return units, {'candidate_process_node_count': candidate_nodes,
                   'extracted_process_node_count': len(units),
                   'rejected_or_ambiguous_process_node_count': sum(rejected.values()),
                   'rejection_reasons': dict(rejected), 'node_id_present_count': node_id_present,
                   'instructor_type_counts': dict(instructor_types),
                   'assistant_string_count': assistant_strings,
                   'observation_string_count': observation_strings,
                   'unit_semantics': 'saved_process_node_not_tool_invocation'}


def _antml_records(text):
    units = []; returns = []
    for block in re.finditer(r'<antml:function_calls>(.*?)</antml:function_calls>', text, re.S):
        for invoke in re.finditer(r'<antml:invoke\s+name=["\']([^"\']+)["\']>(.*?)</antml:invoke>', block.group(1), re.S):
            params = {p.group(1): html.unescape(p.group(2)).strip() for p in
                      re.finditer(r'<antml:parameter\s+name=["\']([^"\']+)["\']>(.*?)</antml:parameter>', invoke.group(2), re.S)}
            units.append({'tool': invoke.group(1), 'arguments': params,
                          'position': text.count('\n', 0, block.start() + invoke.start()) + 1,
                          'call_id': None, 'protocol': 'antml_invoke'})
    returns.extend({'position': text.count('\n', 0, m.start()) + 1, 'status': 'antml_function_results'}
                   for m in re.finditer(r'<function_results>', text))
    return units, returns


def extract_structured(obj, group=None):
    """Return schema and action units; never search prompt/thought prose for commands."""
    if group and '20250806_SWE-Exp_DeepSeek-V3' in group:
        parsed = _swe_exp_process_nodes(obj)
        if parsed is not None: return 'swe_exp_saved_process_nodes', parsed[0]
    if group and '20251103_SalesforceAIResearch_SAGE_OpenHands' in group:
        messages = obj.get('messages') if isinstance(obj, dict) else None
        if isinstance(messages, list): return 'sage_running_command_messages', _sage_messages(messages)[0]
    if isinstance(obj, dict) and isinstance(obj.get('transitions'), list):
        return 'moatless_saved_transitions', [
            {'tool': t.get('name', 'missing'), 'arguments': None, 'position': i,
             'transition': True} for i, t in enumerate(obj['transitions']) if isinstance(t, dict)]
    if isinstance(obj, dict) and isinstance(obj.get('trajectory'), list):
        traj = obj['trajectory']
        if traj and all(isinstance(t, dict) and 'action' in t for t in traj):
            return 'sweagent_saved_actions', [
                {'tool': (t['action'].split()[0] if isinstance(t['action'], str) and t['action'].split() else 'missing'),
                 'arguments': t['action'], 'position': i, 'terminal_action': True}
                for i, t in enumerate(traj)]
    messages = obj.get('llm_call_data') if isinstance(obj, dict) and isinstance(obj.get('llm_call_data'), list) else obj.get('messages') if isinstance(obj, dict) else obj
    if not isinstance(messages, list):
        return 'unsupported_saved_structure', None
    if messages and all(isinstance(m, str) for m in messages):
        if group and '20250110_learn_by_interact' in group:
            units, _, _ = _learn_by_interact_strings(messages)
            return ('learn_by_interact_action_tag_messages', units) if units else ('string_messages_without_action_tag', None)
        return 'string_message_list_unrecognized_source_protocol', None
    units, _, _ = message_tool_records(messages, group)
    if units:
        if any(x.get('protocol') == 'anthropic_tool_use' for x in units): return 'anthropic_tool_use_messages', units
        if any(x.get('protocol') == 'antml_invoke' for x in units): return 'claude_antml_function_calls', units
        if any(x.get('protocol') == 'assistant_function_xml' for x in units): return 'assistant_function_xml_messages', units
        if any(x.get('protocol') == 'learn_by_interact_action_tag' for x in units): return 'learn_by_interact_action_tag_messages', units
        if any(x.get('protocol') in ('assistant_execute_tag', 'assistant_file_edit_tag') for x in units): return 'assistant_execute_tag_messages', units
        if any(x.get('protocol') == 'marscode_fenced_action' for x in units): return 'marscode_fenced_action_messages', units
        return 'explicit_message_tool_calls', units
    if messages and all(isinstance(m, dict) for m in messages):
        return 'messages_without_explicit_action', None
    return 'unsupported_saved_structure', None


TRANSITIONS = {'SearchCode': 'content_search', 'IdentifyCode': 'file_view',
               'EditCode': 'edit_write', 'PlanToCode': 'plan', 'Finished': 'submit',
               'ClarifyCodeChange': 'plan', 'Rejected': 'other'}


def classify_unit(unit):
    protocol = unit.get('protocol')
    if protocol == 'swe_exp_process_node':
        return result([], 'saved_process_node_not_tool_invocation', origin='swe_exp_node_record')
    if unit.get('tool_identity_status') == 'unparsed':
        return result([], 'saved_tool_field_is_not_a_native_identifier', origin='saved_event_tool_field')
    if protocol == 'globant_toolu_call':
        name = str(unit.get('tool', '')).lower()
        labels = {'detect_language_and_get_dependencies': 'environment', 'search_codebase': 'content_search',
                  'read_file': 'file_view', 'get_related_files': 'file_locate', 'apply_diff_change': 'edit_write'}
        if name in labels: return result([labels[name]], origin='globant_saved_toolu_call')
        return result([], unit.get('argument_error') or 'unrecognized_globant_tool_name', origin='globant_saved_toolu_call')
    if protocol == 'lingxi_heading_action':
        name = str(unit.get('tool', '')).lower()
        if name == 'think': return result(['plan'], origin='lingxi_explicit_think_action')
        labels = {'view_file_content': 'file_view', 'view_directory': 'file_locate',
                  'search_files_by_keywords': 'content_search', 'str_replace_editor': 'edit_write'}
        if name in labels: return result([labels[name]], origin='lingxi_explicit_action_tool')
        if name == 'bash':
            args = unit.get('arguments')
            positional = args.get('_positional', []) if isinstance(args, dict) else []
            command = positional[0].get('command') if positional and isinstance(positional[0], dict) else (positional[0] if positional else None)
            return classify_command(command)
    if unit.get('argument_error'): return result([], unit['argument_error'], origin='protocol')
    if unit.get('transition'):
        return result([TRANSITIONS.get(unit['tool'], 'unknown')], origin='saved_transition')
    if protocol == 'solver_operation_event':
        event = unit.get('event_type')
        if event == 'execution':
            data = unit.get('arguments') if isinstance(unit.get('arguments'), dict) else {}
            return classify_command(data.get('command'))
        return result([{'open': 'file_view', 'edit': 'edit_write', 'create': 'edit_write',
                        'revert': 'vcs', 'submit': 'submit'}.get(event, 'unknown')],
                      origin='solver_saved_operation_event')
    if protocol == 'solver_retrieval_event':
        return result(['content_search'], origin='solver_saved_retrieval_event')
    if protocol == 'masai_action':
        action = str(unit['tool']).upper()
        if action == 'COMMAND':
            args = unit.get('arguments') or {}
            return classify_command(args.get('command') if isinstance(args, dict) else args)
        label = {'READ': 'file_view', 'LIST': 'file_locate', 'WRITE': 'edit_write',
                 'EDIT': 'edit_write', 'ADD': 'edit_write', 'DONE': 'submit'}.get(action)
        return result([label or 'unknown'], origin='masai_explicit_action_tag')
    if protocol == 'patch_action': return result(['edit_write'], origin='marscode_explicit_patch_action')
    if protocol in ('nfactorial_logged_command', 'warp_explicit_command_request',
                    'marscode_fenced_action', 'assistant_execute_tag', 'assistant_file_edit_tag',
                    'learn_by_interact_action_tag', 'learn_by_interact_file_edit_tag'):
        name = str(unit['tool']).lower()
        if name == 'file_edit': return result(['edit_write'], origin='explicit_file_edit_tag')
        if name == 'patch_action': return result(['edit_write'], origin='marscode_explicit_patch_action')
        if name == 'execute_ipython': return result(['script_execute'], origin='explicit_ipython_action_tag')
        if name in ('shell_action', 'logged_shell_script', 'requestcommandoutput', 'execute_bash'):
            args = unit.get('arguments') or {}
            command = args.get('command') if isinstance(args, dict) else args
            return classify_command(command)
    if unit.get('terminal_action'):
        if unit['tool'] in {'open', 'edit', 'create', 'find_file', 'search_file', 'search_dir',
                            'goto', 'scroll_down', 'scroll_up', 'submit'}:
            return result([NATIVE[unit['tool']]], origin='sweagent_editor_interface')
        return classify_command(unit['arguments'])
    return classify_call(unit['tool'], unit['arguments'])


def pairing_summary(units, returns=(), duplicate_ids=None):
    call_ids = [u.get('call_id') for u in units if u.get('call_id')]
    return_ids = [r.get('call_id') for r in returns if r.get('call_id')]
    call_counts = Counter(call_ids); return_counts = Counter(return_ids)
    paired = sum(1 for cid, n in call_counts.items() if n == 1 and return_counts.get(cid, 0) == 1)
    non_one_to_one = sum(1 for cid in set(call_counts) | set(return_counts)
                         if call_counts.get(cid, 0) != 1 or return_counts.get(cid, 0) != 1)
    co_recorded = sum(1 for r in returns if r.get('associated_action_position') is not None)
    return {'call_event_count': len(units), 'return_record_count': len(returns),
            'call_ids_present': len(call_ids), 'distinct_call_ids': len(call_counts),
            'missing_call_id_count': len(units) - len(call_ids),
            'duplicate_call_id_counts': {'exact': (duplicate_ids or {}).get('exact', 0),
                                         'conflicting': (duplicate_ids or {}).get('conflicting', 0)},
            'conflicting_duplicate_call_id_count': (duplicate_ids or {}).get('conflicting', 0),
            'return_ids_present': len(return_ids), 'return_ids_missing': len(returns) - len(return_ids),
            'distinct_return_ids': len(return_counts),
            'duplicate_return_id_count': sum(n - 1 for n in return_counts.values() if n > 1),
            'paired_1_to_1_by_id_count': paired,
            'call_only_id_count': sum(1 for cid, n in call_counts.items() if n == 1 and return_counts.get(cid, 0) == 0),
            'return_only_id_count': sum(1 for cid, n in return_counts.items() if n == 1 and call_counts.get(cid, 0) == 0),
            'non_1_to_1_id_count': non_one_to_one,
            'same_record_action_result_count': co_recorded,
            'calls_without_id_match_count': len(units) - paired,
            'orphan_return_id_count': sum(n for cid, n in return_counts.items() if cid not in call_counts),
            'unmatched_return_without_id_count': len(returns) - len(return_ids),
            'pairing_rule': 'ID association only for unique 1:1 IDs; same-record relation is separately counted when schema provides it; no array-position pairing'}


def summarize_units(source, group, task, location, unit_kind, units, returns=(), duplicate_ids=None):
    operations = Counter(); tools = Counter(); components = Counter(); heads = Counter(); reasons = Counter()
    call_presence = Counter(); unparsed_tool_identities = Counter(); process_node_count = 0
    subagent_operations = defaultdict(Counter); subagent_tools = defaultdict(Counter); subagent_units = Counter()
    command_available = 0; examples = {}
    for unit in units:
        if unit.get('protocol') == 'swe_exp_process_node':
            process_node_count += 1
            continue
        r = classify_unit(unit); operation = r['operation']
        operations[operation] += 1; tools[str(unit['tool'])] += 1
        if unit.get('subagent'):
            subagent = unit['subagent']; subagent_units[subagent] += 1
            subagent_operations[subagent][operation] += 1
            subagent_tools[subagent][str(unit['tool'])] += 1
        if unit.get('tool_identity_status') == 'unparsed':
            unparsed_tool_identities[(unit.get('raw_tool_name_length'), unit.get('raw_tool_name_sha256'))] += 1
        components.update(r['components']); heads.update(r['executables'])
        call_presence.update(set(r['components']))
        if r['reason']: reasons[r['reason']] += 1
        arg = unit.get('arguments')
        command = arg.get('command', arg.get('cmd')) if isinstance(arg, dict) else arg
        if unit.get('protocol') == 'lingxi_heading_action' and isinstance(arg, dict):
            positional = arg.get('_positional', [])
            if positional and isinstance(positional[0], dict): command = positional[0].get('command')
        if str(unit['tool']).lower() == 'sendshellinput' and isinstance(arg, dict): command = arg.get('input')
        if (unit.get('terminal_action') or str(unit['tool']).lower() in SHELL or
                unit.get('protocol') in ('assistant_execute_tag', 'assistant_file_edit_tag',
                  'learn_by_interact_action_tag', 'learn_by_interact_file_edit_tag',
                  'nfactorial_logged_command', 'warp_explicit_command_request',
                  'marscode_fenced_action', 'antml_invoke', 'assistant_function_xml',
                  'lingxi_action_function')):
            command_available += int(isinstance(command, (str, list)))
        if operation not in examples:
            # Point back to source rather than copying command arguments or messages.
            examples[operation] = {'position': unit['position'], 'tool': unit['tool'],
                                   'saved_arguments_sha256': digest(json.dumps(arg, sort_keys=True, ensure_ascii=False).encode()),
                                   'rule_origin': r['origin']}
    n = len(units); action_n = n - process_node_count
    assert sum(operations.values()) == sum(tools.values()) == action_n
    return {'source': source, 'group': group, 'task': task, 'location': location,
            'unit_kind': unit_kind, 'unit_count': n, 'action_unit_count': action_n,
            'saved_process_node_count': process_node_count, 'operation_counts': dict(operations),
            'native_tool_counts': dict(tools), 'syntactic_component_counts': dict(components),
            'operation_call_presence_counts': dict(call_presence),
            'subagent_unit_counts': dict(subagent_units),
            'subagent_operation_counts': {a: dict(c) for a, c in sorted(subagent_operations.items())},
            'subagent_native_tool_counts': {a: dict(c) for a, c in sorted(subagent_tools.items())},
            'executable_counts': dict(heads), 'classification_reasons': dict(reasons),
            'saved_command_available_count': command_available, 'evidence_examples': examples,
            'structured_arguments_available_count': sum(isinstance(u.get('arguments'), (dict, list)) for u in units),
            'missing_or_unparsed_arguments_count': sum(u.get('argument_error') is not None or u.get('arguments') is None for u in units),
            'unparsed_native_tool_identity_count': sum(u.get('tool_identity_status') == 'unparsed' for u in units),
            'unparsed_native_tool_identities': [{'length': length, 'sha256': sha, 'count': count}
                                                for (length, sha), count in sorted(unparsed_tool_identities.items())],
            'call_return_evidence': pairing_summary(units, returns, duplicate_ids)}


def analyze_rebench(inputs, old):
    base = inputs.root / REBENCH
    index = [json.loads(line) for line in inputs.read(base / 'index.jsonl').decode().split('\n') if line]
    expected = {r['path']: r for r in old['coverage']['shards']}
    rows = []; seen = set()
    for item in index:
        compressed = inputs.read(base / item['path'], expected[item['path']])
        data = gzip.decompress(compressed)
        if digest(data) != item['content_sha256']: raise ValueError('decompressed shard mismatch')
        parsed = 0
        for line_no, line in enumerate(data.decode().split('\n'), 1):
            if not line.strip(): continue
            obj = json.loads(line); parsed += 1
            key = obj['trajectory_id']
            if key in seen: raise ValueError('duplicate trajectory identity')
            seen.add(key)
            calls = []; returns = []; call_signatures = {}; duplicate_calls = Counter()
            for i, event in enumerate(obj.get('events', [])):
                if event.get('type') == 'tool_call':
                    raw_tool = event.get('tool')
                    valid_tool = valid_native_tool_identifier(raw_tool)
                    call = {'tool': raw_tool if valid_tool else 'unparsed_tool_identity',
                                  'tool_identity_status': 'parsed' if valid_tool else 'unparsed',
                                  'raw_tool_name_length': len(raw_tool) if isinstance(raw_tool, str) else None,
                                  'raw_tool_name_sha256': digest(raw_tool.encode('utf-8')) if isinstance(raw_tool, str) else None,
                                  'arguments': event.get('input'), 'position': i,
                                  'call_id': event.get('tool_call_id')}
                    calls.append(call)
                    cid = call.get('call_id')
                    if cid:
                        signature = (call['tool'], json.dumps(call.get('arguments'), sort_keys=True,
                                                              ensure_ascii=False, default=str))
                        if cid in call_signatures:
                            duplicate_calls['exact' if call_signatures[cid] == signature else 'conflicting'] += 1
                        else:
                            call_signatures[cid] = signature
                elif event.get('type') == 'tool_result':
                    returns.append({'call_id': event.get('tool_call_id'), 'tool': event.get('tool'),
                                    'position': i, 'status': event.get('status'),
                                    'error_present': event.get('error') is not None})
            rows.append(summarize_units('SWE-rebench', obj['participant']['key'], obj['instance_id'],
                        {'path': REBENCH + '/' + item['path'], 'line': line_no, 'trajectory_id': key},
                        'saved_tool_call', calls, returns, duplicate_calls))
        if parsed != item['rows']: raise ValueError('shard row count mismatch')
    if len(rows) != old['scope']['record_count']: raise ValueError('corpus row count mismatch')
    if sum(r['unit_count'] for r in rows) != sum(old['native_tool_counts'].values()): raise ValueError('corpus tool count mismatch')
    return rows


def valid_native_tool_identifier(value):
    return (isinstance(value, str) and len(value) <= 128 and
            re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:/-]*', value) is not None)


def _solver_events(obj):
    if not isinstance(obj, list) or not obj or not all(isinstance(x, dict) and 'event_type' in x for x in obj):
        return None
    actions = []; retrieval = []; event_types = Counter(); ids = {}; duplicate = Counter()
    for i, event in enumerate(obj):
        typ = str(event.get('event_type', 'unknown')); event_types[typ] += 1
        eid = event.get('id')
        if eid:
            signature = (typ, json.dumps(event.get('event_data'), sort_keys=True, ensure_ascii=False, default=str))
            if eid in ids:
                duplicate['exact' if ids[eid] == signature else 'conflicting'] += 1
                continue
            ids[eid] = signature
        data = event.get('event_data')
        if typ in {'open', 'edit', 'create', 'execution', 'revert', 'submit'}:
            args = data if isinstance(data, dict) else None
            actions.append({'tool': typ, 'arguments': args, 'position': i, 'call_id': eid,
                            'protocol': 'solver_operation_event', 'event_type': typ})
        elif typ == 'retrieval':
            retrieval.append({'tool': typ, 'arguments': data, 'position': i, 'call_id': eid,
                              'protocol': 'solver_retrieval_event', 'event_type': typ})
    returns = []
    for i, event in enumerate(obj):
        data = event.get('event_data')
        if event.get('event_type') == 'execution' and isinstance(data, dict) and any(k in data for k in ('stdout', 'stderr', 'exit_code')):
            returns.append({'call_id': event.get('id'), 'tool': 'execution', 'position': i,
                            'status': 'result_embedded_in_execution_event',
                            'unit_kind': 'saved_operation_event',
                            'associated_action_position': i})
    return actions, retrieval, returns, duplicate, dict(event_types)


def _json_object_records(obj, group=None):
    if group and '20250806_SWE-Exp_DeepSeek-V3' in group:
        parsed = _swe_exp_process_nodes(obj)
        if parsed is not None:
            units, detail = parsed
            return ([('saved_process_node', units)], [], {}, 'swe_exp_saved_process_nodes', detail)
    if group and '20251103_SalesforceAIResearch_SAGE_OpenHands' in group:
        messages = obj.get('messages') if isinstance(obj, dict) else None
        if isinstance(messages, list):
            units, returns, detail = _sage_messages(messages)
            return ([('saved_tool_call', units)] if units else []), returns, {}, 'sage_running_command_messages', detail
    solver = _solver_events(obj)
    if solver is not None:
        actions, retrieval, returns, duplicate, types = solver
        return ([('saved_operation_event', actions), ('saved_retrieval_event', retrieval)],
                returns, duplicate, 'solver_event_list', {'event_type_counts': types})
    schema, units = extract_structured(obj, group)
    if units is None:
        return [], [], {}, schema, {}
    if schema == 'sweagent_saved_actions':
        returns = []
        for i, step in enumerate(obj.get('trajectory', [])):
            if isinstance(step, dict) and any(step.get(k) not in (None, '') for k in ('observation', 'response')):
                returns.append({'call_id': None, 'position': i,
                                'status': 'observation_or_response_saved_in_same_trajectory_entry',
                                'associated_action_position': i})
        return [('saved_action_or_tool_call', units)], returns, {}, schema, {}
    messages = obj.get('llm_call_data') if isinstance(obj, dict) and isinstance(obj.get('llm_call_data'), list) else obj.get('messages') if isinstance(obj, dict) else obj
    returns = []
    duplicates = {}
    extra = {}
    if isinstance(messages, list):
        if messages and all(isinstance(m, str) for m in messages):
            if group and '20250110_learn_by_interact' in group:
                parsed, returns, extra = _learn_by_interact_strings(messages)
            else:
                parsed, returns, extra = [], [], {}
            duplicates = {}
        else:
            parsed, returns, duplicates = message_tool_records(messages, group)
            extra = {}
        # extract_structured is also the single format gate; reusing its exact
        # selected units preserves trajectory/transition precedence.
        if schema not in ('sweagent_saved_actions', 'moatless_saved_transitions'):
            units = parsed
    kind = 'saved_transition' if schema == 'moatless_saved_transitions' else 'saved_action_or_tool_call'
    return [(kind, units)], returns, duplicates, schema, extra


def _masai_text(text):
    units = []; sections = Counter(); candidate_tags = 0
    agents = ('Template Generation Agent', 'Test Case Reproducer Agent', 'Search Agent')
    agent_alternation = '|'.join(re.escape(agent) for agent in agents)
    dated_header = re.compile(r'(?m)^=+[ \t]+\d{2}-\d{2}-\d{4}[ \t]+\d{2}:\d{2}:\d{2}[ \t]+[^\n]*$')
    section_pattern = re.compile(rf'(?m)^=+[ \t]+\d{{2}}-\d{{2}}-\d{{4}}[ \t]+\d{{2}}:\d{{2}}:\d{{2}}[ \t]+({agent_alternation}) Model response:[ \t]*$')
    matches = list(section_pattern.finditer(text))
    for index, section in enumerate(matches):
        agent = section.group(1); sections[agent] += 1
        next_header = dated_header.search(text, section.end())
        end = next_header.start() if next_header else len(text)
        body = text[section.end():end]
        actions = list(re.finditer(r'<action>\s*([^<\s]+)\s*</action>', body, re.I))
        candidate_tags += len(actions)
        for j, action in enumerate(actions):
            end = actions[j + 1].start() if j + 1 < len(actions) else len(body)
            tail = body[action.end():end]
            args = {}
            for key, value in re.findall(r'<([A-Za-z_][\w-]*)>(.*?)</\1>', tail, re.S):
                if key.lower() not in {'reasoning', 'action'}: args[key.lower()] = html.unescape(value).strip()
            absolute = section.end() + action.start()
            units.append({'tool': action.group(1).upper(), 'arguments': args,
                          'position': text.count('\n', 0, absolute) + 1, 'call_id': None,
                          'protocol': 'masai_action', 'subagent': agent})
    returns = [{'position': text.count('\n', 0, m.start()) + 1, 'status': 'saved_masai_action_result_block'}
               for m in re.finditer(r'Your actions returned:', text)]
    all_action_tags = len(list(re.finditer(r'<action>\s*([^<\s]+)\s*</action>', text, re.I)))
    outside = all_action_tags - candidate_tags
    return units, returns, {'model_response_sections_by_subagent': dict(sections),
                            'action_tags_in_model_responses': candidate_tags,
                            'action_tags_outside_model_response_sections': outside,
                            'rejected_or_ambiguous_segment_count': 0,
                            'return_blocks_without_native_call_ids': len(returns)}


def _nfactorial_text(text):
    units = []; return_records = []
    starts = list(re.finditer(r'(?m)^.*\bINFO -\s*\n#!/bin/bash\s*\n', text))
    next_log = re.compile(r'(?m)^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ - .*? - (?:INFO|ERROR|WARNING) -')
    for i, match in enumerate(starts):
        body_start = match.end(); next_match = next_log.search(text, body_start)
        end = next_match.start() if next_match else len(text)
        command = text[body_start:end]
        command = re.split(r'(?m)^Exit code:\s*-?\d+\s*$', command, maxsplit=1)[0].strip()
        line = text.count('\n', 0, match.start()) + 1
        units.append({'tool': 'logged_shell_script', 'arguments': {'command': command},
                      'position': line, 'call_id': None, 'protocol': 'nfactorial_logged_command'})
    for m in re.finditer(r'(?m)^Exit code:\s*(-?\d+)\s*$', text):
        return_records.append({'position': text.count('\n', 0, m.start()) + 1,
                               'status': 'saved_exit_code', 'code': int(m.group(1))})
    return units, return_records


def _warp_text(text):
    units = []; returns = []
    for m in re.finditer(r'RequestCommandOutput:\s*(.*?)(?:\s+\(read_only:.*?\))?(?=\r?\n)', text):
        command = m.group(1).strip()
        units.append({'tool': 'RequestCommandOutput', 'arguments': {'command': command},
                      'position': text.count('\n', 0, m.start()) + 1, 'call_id': None,
                      'protocol': 'warp_explicit_command_request'})
    for m in re.finditer(r'ActionResult:\s*Command .*?completed with exit code (-?\d+)', text):
        returns.append({'position': text.count('\n', 0, m.start()) + 1,
                        'status': 'saved_action_result_without_id', 'code': int(m.group(1))})
    return units, returns


def _lingxi_text(text):
    units = []; returns = []
    for heading in re.finditer(r'###\s*🎯\s*Action', text):
        end = re.search(r'(?m)^#{2,3}\s', text[heading.end():])
        block_end = heading.end() + end.start() if end else len(text)
        body = text[heading.end():block_end]
        action = re.search(r'(?m)^\s*([A-Za-z_][\w.-]*)\s*\((.*)\)\s*$', body, re.S)
        if action:
            tool = action.group(1); pos = heading.end() + action.start()
            args = None; error = None
            try:
                call = ast.parse(action.group(0).strip(), mode='eval').body
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != tool:
                    raise ValueError
                args = {}
                for kw in call.keywords:
                    args[kw.arg or '**kwargs'] = ast.literal_eval(kw.value)
                if call.args:
                    args['_positional'] = [ast.literal_eval(value) for value in call.args]
            except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
                error = 'nonliteral_or_unsupported_lingxi_action_arguments'
            units.append({'tool': tool, 'arguments': args, 'argument_error': error,
                          'position': text.count('\n', 0, pos) + 1, 'call_id': None,
                          'protocol': 'lingxi_heading_action'})
    returns.extend({'position': text.count('\n', 0, m.start()) + 1,
                    'status': 'saved_function_result_without_call_id'}
                   for m in re.finditer(r'<function_results>', text))
    # Each explicit step observation is kept as a result record without
    # positional association to the preceding action.
    returns.extend({'position': text.count('\n', 0, m.start()) + 1,
                    'status': 'saved_lingxi_observation_without_call_id'}
                   for m in re.finditer(r'###\s*👁️\s*Observation', text))
    return units, returns


def _globant_text(text):
    """The saved log carries explicit toolu IDs, tool names, and optional args."""
    headers = list(re.finditer(r'Suggested tool call \(toolu_([A-Za-z0-9]+)\):\s*([A-Za-z_][\w.-]*)', text))
    units = []; returns = []; seen = {}; duplicate = Counter(); arg_count = 0
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        segment = text[header.end():end]
        args = None; argument_error = 'arguments_not_saved'
        match = re.search(r'(?m)^Arguments:\s*\n\s*(\{.*?\})\s*\n\*{5,}', segment, re.S)
        if match:
            try:
                args = json.loads(match.group(1)); argument_error = None; arg_count += 1
            except ValueError:
                argument_error = 'saved_arguments_not_valid_json'
        call_id = 'toolu_' + header.group(1); tool = header.group(2)
        signature = (tool, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str))
        if call_id in seen:
            duplicate['exact' if seen[call_id] == signature else 'conflicting'] += 1
            continue
        seen[call_id] = signature
        units.append({'tool': tool, 'arguments': args, 'argument_error': argument_error,
                      'position': text.count('\n', 0, header.start()) + 1,
                      'call_id': call_id, 'protocol': 'globant_toolu_call'})
    return units, returns, {'explicit_call_envelopes': len(headers), 'structured_argument_blocks': arg_count,
                            'missing_or_invalid_argument_blocks': len(headers) - arg_count,
                            'duplicate_call_ids': dict(duplicate)}


def _text_action_records(text, group, path):
    if 'lite/20241127_globant_codefixer_agent' in group:
        units, returns, detail = _globant_text(text)
        return units, returns, 'globant_toolu_call_envelopes', detail
    if '20240612_MASAI_gpt4o' in group:
        units, returns, detail = _masai_text(text)
        return units, returns, 'masai_model_action_sections', detail
    if '20241007_nfactorial' in group:
        units, returns = _nfactorial_text(text)
        return units, returns, 'nfactorial_timestamped_shell_blocks', {'raw_shell_block_count': len(units)}
    if '20250623_warp' in group:
        units, returns = _warp_text(text)
        return units, returns, 'warp_exchange_command_protocol', {'raw_result_markers': len(returns)}
    if '20251014_Lingxi_kimi_k2' in group and '<problem_decoder' in text:
        units, returns = _lingxi_text(text)
        return units, returns, 'lingxi_problem_decoder_action_sections', {}
    if '20250522_tools_claude-4-opus' in group:
        units, returns = _antml_records(text)
        return units, returns, 'claude_antml_function_call_protocol', {}
    if '20241212_google_jules' in group:
        return [], [], 'jules_retrieval_or_solution_artifact', {}
    return [], [], 'plain_text_without_explicit_action_protocol', {}


def _no_action_disposition(path, text, obj, schema):
    name = Path(path).name.lower()
    if name in {'readme.md', 'link_to_trajs.txt', 'retrieval_trajs.json', 'edit_trajs.jsonl',
                'verified_trajs.jsonl', 'loc_outputs.jsonl', 'passing_tests.jsonl',
                'problem_statement_outputs.jsonl', 'repair_parameters.json'}:
        return 'companion_artifact', 'known_metadata_retrieval_or_prediction_output_not_execution_log'
    if '20250806_SWE-Exp_DeepSeek-V3' in path:
        if isinstance(obj, list) and obj and isinstance(obj[0], dict) and 'problem_statement' in obj[0]:
            return 'companion_artifact', 'problem_statement_only_without_saved_process_node'
        return 'process_partial_or_ambiguous', 'swe_exp_saved_structure_not_recognized_as_process_node_or_tool_call'
    if 'lite/20241127_globant_codefixer_agent' in path:
        return 'process_partial_or_ambiguous', 'fault_localization_and_patch_narrative_without_toolu_call_envelope'
    if '20250120_Bracket' in path:
        return 'process_partial_or_ambiguous', 'setup_indexing_and_problem_log_without_saved_agent_action_boundary'
    if '20240721_amazon-q' in path:
        return 'process_partial_or_ambiguous', 'assistant_action_narration_without_observation_or_execution_protocol'
    if '20240918_lingma' in path or '20241002_lingma' in path:
        return 'process_partial_or_ambiguous', 'assistant_text_mentions_search_apis_but_no_native_action_or_result_id'
    if '20241108_devlo' in path or '20241213_devlo' in path:
        return 'process_partial_or_ambiguous', 'thought_response_or_retrieval_text_without_explicit_operation_request'
    if '20241212_google_jules' in path:
        return 'companion_artifact', 'search_result_or_solution_report_without_operation_invocation_parameters'
    if '20250214_agentless' in path or '20250615_agentless' in path:
        return 'process_partial_or_ambiguous', 'llm_request_response_log_has_no_nonnull_tool_call_record'
    if '20250120_Bracket' in path or '20250110_learn_by_interact' in path:
        return 'process_partial_or_ambiguous', 'process_or_model_text_has_no_explicit_saved_action_envelope'
    if '20241128_SWE-Fixer' in path or '20250306_SWE-Fixer' in path or '20250112_ugaiforge' in path:
        return 'companion_artifact', 'retrieval_prediction_problem_or_test_result_artifact_not_tool_execution'
    if '20241212_epam' in path and isinstance(obj, dict):
        return 'process_partial_or_ambiguous', 'saved_llm_message_context_has_no_tool_use_blocks'
    if '20250203_openhands' in path and isinstance(obj, list) and not any(isinstance(x, dict) and x.get('role') == 'assistant' for x in obj):
        return 'process_partial_or_ambiguous', 'saved_context_contains_no_assistant_action_message'
    if isinstance(obj, list) and not obj:
        return 'companion_artifact', 'empty_saved_json_list_no_trajectory_or_action_records'
    if isinstance(obj, dict) and obj.get('messages') == []:
        return 'companion_artifact', 'empty_message_context_no_saved_agent_action'
    if schema == 'messages_without_explicit_action':
        return 'process_partial_or_ambiguous', 'messages_saved_without_machine_action_protocol'
    if isinstance(obj, dict) and set(obj) == {'instance_id', 'trajectory'}:
        return 'process_partial_or_ambiguous', 'planning_and_candidate_file_stages_not_execution_events'
    if isinstance(obj, dict) and 'agents' in obj and 'llm_final_response' in obj:
        return 'process_partial_or_ambiguous', 'multi_agent_response_stages_without_tool_execution_records'
    if text and ('Find files (' in text or 'Knowledge Graph' in text or 'Top 20 candidate locations' in text):
        return 'companion_artifact', 'retrieval_or_location_candidate_output_without_invocation'
    if text and ('Thought:' in text or 'THOUGHT:' in text or 'Response:' in text or 'assistant:' in text.lower()):
        return 'process_partial_or_ambiguous', 'narrative_or_model_response_without_explicit_action_boundary'
    return 'process_partial_or_ambiguous', 'saved_structure_has_no_positive_companion_artifact_evidence_or_supported_action_protocol'


def _coverage_fields(result_data):
    status = result_data.get('status')
    schema = result_data.get('schema', '')
    detail = result_data.get('action_protocol_detail') or {}
    is_process = schema == 'swe_exp_saved_process_nodes'
    extracted = result_data.get('unit_count') or 0
    process_count = detail.get('extracted_process_node_count', 0) if is_process else 0
    if 'candidate_action_segment_count' in detail:
        candidates = detail['candidate_action_segment_count']
    elif 'action_tags_in_model_responses' in detail:
        candidates = detail['action_tags_in_model_responses']
    elif 'file_edit_candidates' in detail:
        candidates = extracted + detail.get('file_edit_rejected_or_ambiguous', 0)
    elif status == 'actions_extracted':
        candidates = extracted
    else:
        candidates = 0
    rejected = detail.get('rejected_or_ambiguous_segment_count',
                          detail.get('file_edit_rejected_or_ambiguous', 0))
    if is_process:
        assessment = 'saved_process_nodes_not_tool_actions'
    elif status == 'actions_extracted':
        explicit_scan = ('candidate_action_segment_count' in detail or
                         'action_tags_in_model_responses' in detail or
                         'file_edit_candidates' in detail)
        if explicit_scan and rejected == 0 and candidates == extracted:
            assessment = 'complete_within_inspected_protocol_boundary'
        elif explicit_scan:
            assessment = 'partial_protocol_coverage'
        else:
            assessment = 'extracted_units_protocol_scope_not_exhaustively_scanned'
    elif status == 'companion_artifact':
        assessment = 'companion_artifact_positive_evidence'
    else:
        assessment = 'no_supported_action_record_found_not_proof_of_absence'
    return {'inspected': status not in ('missing_registered_file', 'isolated_content_identity_mismatch',
                                        'isolated_registration_conflict'),
            'protocol_recognized': status == 'actions_extracted' or is_process,
            'candidate_action_segment_count': candidates,
            'extracted_action_segment_count': extracted - process_count,
            'rejected_or_ambiguous_segment_count': rejected,
            'saved_process_node_count': process_count,
            'file_edit_candidate_block_count': detail.get('file_edit_candidates'),
            'file_edit_closed_candidate_block_count': detail.get('file_edit_closed_candidates'),
            'file_edit_extracted_block_count': detail.get('file_edit_extracted'),
            'file_edit_rejected_or_ambiguous_block_count': detail.get('file_edit_rejected_or_ambiguous'),
            'coverage_assessment': assessment}


def _task_from_registered_path(name):
    rel = name.split('/trajs/', 1)[1]
    first = rel.split('/', 1)[0]
    return Path(first).stem


def _analyze_swebench_bytes(name, group, data):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return {'schema': 'non_utf8_or_binary', 'status': 'process_partial_or_ambiguous',
                'reason_code': 'utf8_decode_failed', 'units_by_kind': [], 'returns': [],
                'unit_count': None, 'action_protocol_detail': {}}
    obj = None
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        obj = None

    # The protected raw newline-delimited prediction/retrieval products are
    # parsed line-by-line, but a patch or search result is not an action.
    if obj is None and Path(name).suffix.lower() == '.jsonl':
        records = []; bad_lines = 0
        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip(): continue
            try: records.append((line_no, json.loads(line)))
            except ValueError: bad_lines += 1
        all_units = []; all_returns = []; schemas = Counter(); details = []
        for line_no, record in records:
            groups, returns, duplicate, schema, extra = _json_object_records(record, group)
            schemas[schema] += 1; all_returns.extend(returns)
            for kind, units in groups:
                for unit in units:
                    unit['position'] = {'line': line_no, 'record_position': unit.get('position')}
                if units: all_units.extend((kind, unit) for unit in units)
        if all_units:
            units_by_kind = []
            by_kind = defaultdict(list)
            for kind, unit in all_units: by_kind[kind].append(unit)
            units_by_kind = sorted(by_kind.items())
            status = 'process_partial_or_ambiguous' if bad_lines else 'actions_extracted'
            reason = 'jsonl_rows_include_unparsed_lines' if bad_lines else 'jsonl_rows_contain_explicit_saved_action_protocol'
        else:
            disposition, reason = _no_action_disposition(name, text, records[0][1] if records else None, 'jsonl_rows')
            status = 'process_partial_or_ambiguous' if bad_lines else disposition
            if bad_lines: reason = 'jsonl_rows_include_unparsed_lines_no_complete_action_record'
            units_by_kind = []
        return {'schema': 'jsonl:' + ','.join(sorted(schemas)) if schemas else 'jsonl_invalid',
                'status': status, 'reason_code': reason, 'units_by_kind': units_by_kind,
                'returns': all_returns, 'unit_count': len(all_units) if all_units else 0,
                'jsonl_record_count': len(records), 'jsonl_invalid_line_count': bad_lines,
                'action_protocol_detail': {'row_schemas': dict(schemas)}}

    if obj is not None:
        groups, returns, duplicates, schema, extra = _json_object_records(obj, group)
        nonempty = [(kind, units) for kind, units in groups if units]
        if nonempty:
            if schema == 'swe_exp_saved_process_nodes':
                status = 'process_partial_or_ambiguous'
                reason = 'saved_process_nodes_not_tool_invocation_records'
            else:
                status = 'actions_extracted'; reason = 'explicit_json_action_protocol'
            return {'schema': schema, 'status': status, 'reason_code': reason,
                    'units_by_kind': nonempty, 'returns': returns, 'duplicate_ids': duplicates,
                    'unit_count': sum(len(u) for _, u in nonempty), 'action_protocol_detail': extra}
        disposition, reason = _no_action_disposition(name, text, obj, schema)
        return {'schema': schema, 'status': disposition, 'reason_code': reason,
                'units_by_kind': [], 'returns': returns, 'unit_count': 0,
                'action_protocol_detail': extra}

    units, returns, schema, detail = _text_action_records(text, group, name)
    if units:
        kind = {'masai_model_action_sections': 'saved_action_or_tool_call',
                'nfactorial_timestamped_shell_blocks': 'saved_shell_invocation',
                'warp_exchange_command_protocol': 'saved_shell_invocation',
                'learn_by_interact_action_tag_messages': 'saved_action_or_tool_call',
                'globant_toolu_call_envelopes': 'saved_tool_call',
                'lingxi_problem_decoder_action_sections': 'saved_action_or_tool_call',
                'claude_antml_function_call_protocol': 'saved_action_or_tool_call'}.get(schema, 'saved_action_or_tool_call')
        return {'schema': schema, 'status': 'actions_extracted', 'reason_code': 'explicit_saved_text_action_protocol',
                'units_by_kind': [(kind, units)], 'returns': returns, 'unit_count': len(units),
                'duplicate_ids': detail.get('duplicate_call_ids', {}), 'action_protocol_detail': detail}
    disposition, reason = _no_action_disposition(name, text, obj, schema)
    return {'schema': schema, 'status': disposition, 'reason_code': reason,
            'units_by_kind': [], 'returns': returns, 'unit_count': 0,
            'action_protocol_detail': detail}


def analyze_swebench(inputs, entries, conflicts=None):
    rows = []; inventory = []; group_counts = defaultdict(Counter); group_returns = Counter(); conflicts = conflicts or {}
    all_paths = sorted(set(entries) | set(conflicts))
    for object_index, name in enumerate(all_paths, 1):
        group = name.split('/experiments/', 1)[1].split('/trajs/', 1)[0]
        task = _task_from_registered_path(name)
        if name in conflicts:
            actual = inputs.read(name) if (inputs.root / name).is_file() else b''
            inventory.append({'path': name, 'group': group, 'task': task, 'schema': 'registration_conflict',
                              'status': 'isolated_registration_conflict',
                              'reason_code': 'acquisition_manifests_disagree_on_bytes_or_sha256',
                              'inspected': False, 'protocol_recognized': False,
                              'candidate_action_segment_count': None, 'extracted_action_segment_count': None,
                              'rejected_or_ambiguous_segment_count': None, 'saved_process_node_count': None,
                              'coverage_assessment': 'blocked_by_registration_conflict',
                              'registrations': [{'bytes': x.get('bytes'), 'sha256': x.get('sha256'),
                                                 'acquisition_manifest': x.get('acquisition_manifest')} for x in conflicts[name]],
                              'actual_bytes': len(actual) if actual else None,
                              'actual_sha256': digest(actual) if actual else None,
                              'unit_count': None})
            group_counts[group]['isolated_registration_conflict'] += 1
            continue
        registration = entries[name]
        try:
            data = inputs.read(name, registration)
        except FileNotFoundError:
            result_data = {'schema': 'missing_file', 'status': 'missing_registered_file',
                           'reason_code': 'registered_path_not_present_locally', 'units_by_kind': [], 'returns': [],
                           'unit_count': None, 'actual_bytes': None, 'actual_sha256': None,
                           'inspected': False, 'protocol_recognized': False,
                           'candidate_action_segment_count': None, 'extracted_action_segment_count': None,
                           'rejected_or_ambiguous_segment_count': None, 'saved_process_node_count': None,
                           'coverage_assessment': 'blocked_by_missing_registered_file'}
            inventory.append({'path': name, 'group': group, 'task': task, **result_data,
                              'expected_bytes': registration.get('bytes'), 'expected_sha256': registration.get('sha256')})
            group_counts[group][result_data['status']] += 1
            continue
        except ValueError:
            actual = inputs.files.get(name, {})
            result_data = {'schema': 'hash_mismatch', 'status': 'isolated_content_identity_mismatch',
                           'reason_code': 'local_bytes_or_sha256_differ_from_acquisition_manifest', 'units_by_kind': [], 'returns': [],
                           'unit_count': None, 'actual_bytes': actual.get('bytes'), 'actual_sha256': actual.get('sha256'),
                           'inspected': False, 'protocol_recognized': False,
                           'candidate_action_segment_count': None, 'extracted_action_segment_count': None,
                           'rejected_or_ambiguous_segment_count': None, 'saved_process_node_count': None,
                           'coverage_assessment': 'blocked_by_content_identity_mismatch'}
            inventory.append({'path': name, 'group': group, 'task': task, **result_data,
                              'expected_bytes': registration.get('bytes'), 'expected_sha256': registration.get('sha256')})
            group_counts[group][result_data['status']] += 1
            continue
        result_data = _analyze_swebench_bytes(name, group, data)
        result_data.update(_coverage_fields(result_data))
        item = {'path': name, 'group': group, 'task': task, 'bytes': len(data), 'sha256': digest(data),
                'expected_bytes': registration.get('bytes'), 'expected_sha256': registration.get('sha256'),
                **result_data}
        item['unit_kinds'] = {kind: len(units) for kind, units in result_data['units_by_kind']}
        item['units_by_kind'] = item.pop('units_by_kind')
        item['return_record_count'] = len(result_data.get('returns', []))
        group_returns[group] += item['return_record_count']
        item['message_or_record_count'] = result_data.get('jsonl_record_count')
        # Full action arguments stay in memory for classification only; the coverage
        # artifact receives positions and counts, never commands or message text.
        nonempty_kinds = result_data['units_by_kind']
        assigned_returns = 0
        for kind, units in nonempty_kinds:
            returns = result_data.get('returns', [])
            if any(r.get('unit_kind') is not None for r in returns):
                returns = [r for r in returns if r.get('unit_kind') == kind]
            elif len(nonempty_kinds) > 1:
                # File-level results without a native type cannot be copied onto
                # several independent action/retrieval rows.
                returns = []
            assigned_returns += len(returns)
            rows.append(summarize_units('SWE-bench', group, task, {'path': name}, kind, units,
                                        returns, result_data.get('duplicate_ids')))
        item['return_records_assigned_to_unit_rows'] = assigned_returns
        item['unassigned_file_level_return_record_count'] = item['return_record_count'] - assigned_returns
        item['unit_count'] = result_data.get('unit_count')
        item['action_unit_count'] = sum(len(units) for kind, units in result_data.get('units_by_kind', [])
                                        if kind != 'saved_process_node')
        item['saved_process_node_count'] = sum(len(units) for kind, units in result_data.get('units_by_kind', [])
                                               if kind == 'saved_process_node')
        item['action_extracted'] = item['action_unit_count'] > 0
        # Do not serialize source arguments or large event payloads into coverage.
        item.pop('units_by_kind', None); item.pop('returns', None); item.pop('duplicate_ids', None)
        group_counts[group][item['status']] += 1
        inventory.append(item)
        if object_index % 2500 == 0:
            print('checked SWE-bench registered objects', object_index, '/', len(all_paths), flush=True)

    registered = set(entries) | set(conflicts)
    actual = {str(p.relative_to(inputs.root)) for p in (inputs.root / SWEBENCH / 'experiments').rglob('*')
              if p.is_file() and '/trajs/' in str(p)}
    unregistered = []
    for name in sorted(actual - registered):
        raw = inputs.read(name)
        unregistered.append({'path': name, 'bytes': len(raw), 'sha256': digest(raw),
                             'status': 'unregistered_local_object',
                             'reason_code': 'present_under_scoped_trajs_tree_but_absent_from_three_acquisition_manifests'})
    schema_counts = defaultdict(Counter); reason_counts = defaultdict(Counter)
    for item in inventory:
        schema_counts[item['group']][item.get('schema', 'unknown')] += 1
        reason_counts[item['group']][item.get('reason_code', 'unknown')] += 1
    return rows, {'registered_object_count': len(all_paths), 'registered_group_count': len(group_counts),
                  'action_object_count': sum(bool(x.get('action_unit_count')) for x in inventory),
                  'process_node_object_count': sum(bool(x.get('saved_process_node_count')) for x in inventory),
                  'process_node_object_count_is_subset_of_partial_or_ambiguous': True,
                  'process_partial_or_ambiguous_count': sum(x['status'] == 'process_partial_or_ambiguous' for x in inventory),
                  'companion_artifact_count': sum(x['status'] == 'companion_artifact' for x in inventory),
                  'missing_registered_count': sum(x['status'] == 'missing_registered_file' for x in inventory),
                  'identity_mismatch_count': sum(x['status'] == 'isolated_content_identity_mismatch' for x in inventory),
                  'registration_conflict_count': sum(x['status'] == 'isolated_registration_conflict' for x in inventory),
                  'parsed_unit_count': sum(r.get('action_unit_count', r['unit_count']) for r in rows),
                  'saved_process_node_count': sum(r.get('saved_process_node_count', 0) for r in rows),
                  'unregistered_actual_object_count': len(unregistered),
                  'per_group_status_counts': {g: dict(c) for g, c in sorted(group_counts.items())},
                  'per_group_return_record_count': dict(sorted(group_returns.items())),
                  'saved_return_record_count': sum(group_returns.values()),
                  'unassigned_file_level_return_record_count': sum(x.get('unassigned_file_level_return_record_count', 0) for x in inventory),
                  'per_group_schema_counts': {g: dict(c) for g, c in sorted(schema_counts.items())},
                  'per_group_reason_counts': {g: dict(c) for g, c in sorted(reason_counts.items())},
                  'registered_path_set_count': len(registered),
                  'unregistered_actual_paths': unregistered, 'objects': inventory,
                  'note': 'Every registered path was hash-checked and assigned an evidence status. Action count excludes prose, planning nodes, result-only and companion outputs; all formats remain source-specific.'}


def aggregate(rows):
    counts = Counter(); tools = Counter(); tool_presence = Counter(); presence = Counter()
    components = Counter(); executables = Counter(); reasons = Counter()
    call_presence = Counter()
    argument_available = 0; argument_missing = 0; command_available = 0; unparsed_tool_count = 0
    pairing = Counter(); tool_trajectories = defaultdict(set); operation_trajectories = defaultdict(set)
    subagent_units = Counter(); subagent_operations = defaultdict(Counter); subagent_tools = defaultdict(Counter)
    process_node_count = 0
    trajectory_ids = set()
    for row in rows:
        loc = row.get('location', {})
        trace_id = loc.get('trajectory_id') or loc.get('path')
        if trace_id is not None: trajectory_ids.add(trace_id)
        counts.update(row['operation_counts']); tools.update(row['native_tool_counts'])
        process_node_count += row.get('saved_process_node_count', 0)
        subagent_units.update(row.get('subagent_unit_counts', {}))
        for agent, values in row.get('subagent_operation_counts', {}).items(): subagent_operations[agent].update(values)
        for agent, values in row.get('subagent_native_tool_counts', {}).items(): subagent_tools[agent].update(values)
        for k, v in row['native_tool_counts'].items():
            if v: tool_trajectories[k].add(trace_id)
        for k, v in row['operation_counts'].items():
            if v: operation_trajectories[k].add(trace_id)
        presence.update(k for k, v in row['operation_counts'].items() if v)
        components.update(row['syntactic_component_counts']); executables.update(row['executable_counts'])
        call_presence.update(row['operation_call_presence_counts'])
        reasons.update(row['classification_reasons'])
        argument_available += row.get('structured_arguments_available_count', 0)
        argument_missing += row.get('missing_or_unparsed_arguments_count', 0)
        command_available += row['saved_command_available_count']
        unparsed_tool_count += row.get('unparsed_native_tool_identity_count', 0)
        pairing.update({k: v for k, v in row['call_return_evidence'].items()
                        if isinstance(v, int) and not isinstance(v, bool)})
    n = sum(counts.values())
    return {'record_count': len(trajectory_ids), 'trajectory_count': len(trajectory_ids),
            'analysis_row_count': len(rows), 'operations': shares(counts), 'native_tools': shares(tools),
            'operation_call_presence': {'all_call_denominator': n, 'counts': dict(call_presence),
                                        'percent_all_calls': {k: 100*v/n if n else None for k,v in call_presence.items()},
                                        'overlapping': True},
            'operation_record_presence': dict(sorted({k: len(v) for k, v in operation_trajectories.items()}.items())),
            'tool_record_presence': dict(sorted({k: len(v) for k, v in tool_trajectories.items()}.items())),
            'syntactic_components': shares(components), 'executables': shares(executables),
            'classification_reasons': dict(reasons),
            'saved_process_node_count': process_node_count,
            'subagents': {a: {'unit_count': subagent_units[a], 'operation_counts': dict(subagent_operations[a]),
                              'native_tool_counts': dict(subagent_tools[a])}
                          for a in sorted(subagent_units)},
            'saved_command_available_count': command_available,
            'structured_arguments_available_count': argument_available,
            'missing_or_unparsed_arguments_count': argument_missing,
            'unparsed_native_tool_identity_count': unparsed_tool_count,
            'call_return_evidence': {**dict(pairing),
                'pairing_rule': 'ID association only for unique 1:1 IDs; same-record relation counted separately; no array-position pairing'}}


def coding_summary(rows):
    groups = defaultdict(list); repos = defaultdict(list)
    for row in rows:
        groups[(row['source'], row['group'], row['unit_kind'])].append(row)
        repos[(row['source'], row['group'], row['unit_kind'], row['task'].rsplit('-', 1)[0])].append(row)
    return {'groups': [{'source': s, 'group': g, 'unit_kind': u, **aggregate(rr)}
                       for (s, g, u), rr in sorted(groups.items())],
            'repository_scenarios': [{'source': s, 'group': g, 'unit_kind': u, 'repository': repo, **aggregate(rr)}
                                    for (s, g, u, repo), rr in sorted(repos.items())],
            'swe_rebench_pooled': aggregate([r for r in rows if r['source'] == 'SWE-rebench']),
            'pooling': 'SWE-bench submissions/transitions and SWE-rebench participants are not a shared population; per-group denominators retained; pooled SWE-rebench is call-weighted, not typical participant'}


def _group_record(groups, submission, source='SWE-bench'):
    return next((g for g in groups if g['source'] == source and g['group'] == submission), None)


def correction_summary(old_summary, old_coverage, new_coding, inventory):
    old_groups = old_summary['coding']['groups']; new_groups = new_coding['groups']
    old_status = old_coverage.get('per_group_status_counts', {})
    v2_rebench = old_summary['coding']['swe_rebench_pooled']['call_return_evidence']
    v3_rebench = new_coding['swe_rebench_pooled']['call_return_evidence']
    def objects(group): return [o for o in inventory['objects'] if o['group'] == group]
    def file_edit_counts(group):
        group_objects = objects(group)
        return {key: sum(o.get(key) or 0 for o in group_objects) for key in (
            'file_edit_candidate_block_count', 'file_edit_closed_candidate_block_count',
            'file_edit_extracted_block_count', 'file_edit_rejected_or_ambiguous_block_count')}
    masai = _group_record(new_groups, '20240612_MASAI_gpt4o')
    masai_v2 = _group_record(old_groups, '20240612_MASAI_gpt4o')
    solver_groups = [g for g in new_groups if g['group'] in {
        '20240920_solver', '20240924_solver', '20241028_solver'}]
    solver_old = [g for g in old_groups if g['group'] in {g['group'] for g in solver_groups}]
    solver_v2_retrieval_returns = sum(g['call_return_evidence']['return_record_count'] for g in solver_old
                                      if g['unit_kind'] == 'saved_retrieval_event')
    solver_v3_operation_returns = sum(g['call_return_evidence']['return_record_count'] for g in solver_groups
                                     if g['unit_kind'] == 'saved_operation_event')
    solver_v3_retrieval_returns = sum(g['call_return_evidence']['return_record_count'] for g in solver_groups
                                      if g['unit_kind'] == 'saved_retrieval_event')
    sage_group = _group_record(new_groups, '20251103_SalesforceAIResearch_SAGE_OpenHands')
    exp_group = _group_record(new_groups, '20250806_SWE-Exp_DeepSeek-V3')
    exp_objects = objects('20250806_SWE-Exp_DeepSeek-V3')
    exp_types = Counter()
    for item in exp_objects:
        exp_types.update(item.get('action_protocol_detail', {}).get('instructor_type_counts', {}))
    learn = _group_record(new_groups, '20250110_learn_by_interact_claude3.5')
    learn_v2 = _group_record(old_groups, '20250110_learn_by_interact_claude3.5')
    return {
        'sage_openhands': {'v2_file_statuses': old_status.get('20251103_SalesforceAIResearch_SAGE_OpenHands', {}),
            'v3_file_statuses': inventory['per_group_status_counts'].get('20251103_SalesforceAIResearch_SAGE_OpenHands', {}),
            'command_candidates': sum(o.get('candidate_action_segment_count') or 0 for o in objects('20251103_SalesforceAIResearch_SAGE_OpenHands')),
            'extracted_commands': sage_group['operations']['denominator'] if sage_group else 0,
            'rejected_or_ambiguous': sum(o.get('rejected_or_ambiguous_segment_count') or 0 for o in objects('20251103_SalesforceAIResearch_SAGE_OpenHands')),
            'saved_return_records': sage_group['call_return_evidence']['return_record_count'] if sage_group else 0,
            'adjacent_following_return_code_records': sum(o.get('action_protocol_detail', {}).get('adjacent_following_return_code_record_count', 0) for o in objects('20251103_SalesforceAIResearch_SAGE_OpenHands')),
            'id_pairing_claims': 0},
        'swe_exp': {'v2_file_statuses': old_status.get('20250806_SWE-Exp_DeepSeek-V3', {}),
            'v3_file_statuses': inventory['per_group_status_counts'].get('20250806_SWE-Exp_DeepSeek-V3', {}),
            'saved_process_nodes': sum(o.get('saved_process_node_count') or 0 for o in exp_objects),
            'action_calls': 0,
            'instructor_type_counts': dict(exp_types),
            'interpretation': 'node_id identifies a saved process node; instructor supplies reasoning/instruction/context fields; assistant and observation are process content, not a native tool call or verified execution timeline'},
        'masai': {'v2_action_count': masai_v2['operations']['denominator'] if masai_v2 else 0,
            'v3_action_count': masai['operations']['denominator'] if masai else 0,
            'test_case_reproducer_prior_scan_hint_count': 8212 if len(objects('20240612_MASAI_gpt4o')) == 500 else None,
            'v3_subagents': masai['subagents'] if masai else {},
            'v3_return_records_without_id': masai['call_return_evidence']['return_ids_missing'] if masai else 0,
            'v3_outside_response_action_like_tags': sum(o.get('action_protocol_detail', {}).get('action_tags_outside_model_response_sections', 0) for o in objects('20240612_MASAI_gpt4o'))},
        'learn_by_interact': {'v2_action_count': learn_v2['operations']['denominator'] if learn_v2 else 0,
            'v3_action_count': learn['operations']['denominator'] if learn else 0,
            'v2_file_edit_count': learn_v2['native_tools']['counts'].get('file_edit', 0) if learn_v2 else 0,
            **file_edit_counts('20250110_learn_by_interact_claude3.5'),
            'returns_without_id': learn['call_return_evidence']['return_ids_missing'] if learn else 0,
            'codeshell_file_edit_candidates': sum(o.get('file_edit_candidate_block_count') or 0 for o in objects('20250118_codeshellagent_gemini_2.0_flash_experimental'))},
        'swe_rebench': {'v2': v2_rebench, 'v3': v3_rebench},
        'solver': {'v2_retrieval_rows_duplicate_returns': solver_v2_retrieval_returns,
            'v3_operation_return_records': solver_v3_operation_returns,
            'v3_retrieval_return_records': solver_v3_retrieval_returns,
            'v3_total_unique_return_records_in_solver_rows': solver_v3_operation_returns + solver_v3_retrieval_returns}}


def render_corrections(c):
    sage = c['sage_openhands']; exp = c['swe_exp']; masai = c['masai']
    learn = c['learn_by_interact']; rb = c['swe_rebench']; solver = c['solver']
    masai_test_count = masai['v3_subagents'].get('Test Case Reproducer Agent', {}).get('unit_count', 0)
    masai_hint = masai['test_case_reproducer_prior_scan_hint_count']
    masai_scan_note = (f"Test Case Reproducer Agent重算 {masai_test_count:,}，前置扫描线索 {masai_hint:,}，差 {masai_test_count - masai_hint:+,}；无稳定ID或无效标签证据支持去重，差异原因未确认。"
                       if masai_hint is not None else '当前夹具不含完整MASAI组，不比较全组扫描线索。')
    lines = ['# v2 → v3 集中更正', '',
             '| 问题 | v2错误 | 修复依据与v3结果 | 仍未知/限制 |',
             '| --- | --- | --- | --- |',
             f"| SAGE OpenHands 命令协议 | 499个文件被留在过程/歧义类 | 检出 {sage['command_candidates']:,} 个 `Running command:` 候选，提取 {sage['extracted_commands']:,} 条非空命令；{sage['rejected_or_ambiguous']:,} 个空命令标记拒绝；另存 {sage['saved_return_records']:,} 个 return_code 结果记录 | {sage['id_pairing_claims']} 个ID配对；消息相邻只单列 {sage['adjacent_following_return_code_records']:,} 条结果线索，不宣称一一关联；未把提示/叙述作为命令 |",
             f"| SWE-Exp | 500个文件因首项problem_statement被判配套产物 | 按完整列表读取 {exp['saved_process_nodes']:,} 个带assistant/observation的保存过程节点，并按instructor类型汇总 | 节点不是工具调用或真实执行时间线；未推断工具名 |",
             f"| MASAI | 只读Template Generation Agent，v2计 {masai['v2_action_count']:,} 个动作 | 按三类明确Model response段读取，v3共 {masai['v3_action_count']:,} 个动作；分Agent计数见summary.json/toolkits.json | {masai_scan_note} 另有 {masai['v3_return_records_without_id']:,} 个无ID返回块不与动作配对，响应段外 {masai['v3_outside_response_action_like_tags']:,} 个同形标签被排除 |",
             f"| Learn-by-Interact file_edit | v2提取 {learn['v2_file_edit_count']:,} 个file_edit | v3候选 {learn['file_edit_candidate_block_count']:,}、闭合 {learn['file_edit_closed_candidate_block_count']:,}、提取 {learn['file_edit_extracted_block_count']:,}、拒绝/歧义 {learn['file_edit_rejected_or_ambiguous_block_count']:,}；该submission总动作 {learn['v2_action_count']:,} → {learn['v3_action_count']:,} | 仍无调用ID；不执行编辑正文。CodeShell同形候选 {learn['codeshell_file_edit_candidates']:,}，未发现同类实际遗漏 |",
             f"| SWE-rebench关联 | v2调用 {rb['v2']['call_event_count']:,}、返回0、调用缺ID {rb['v2']['missing_call_id_count']:,} | v3从原生tool_call_id/tool_result重算：调用 {rb['v3']['call_event_count']:,}、返回 {rb['v3']['return_record_count']:,}、唯一1:1 {rb['v3']['paired_1_to_1_by_id_count']:,}、仅调用侧ID {rb['v3']['call_only_id_count']:,} | 重复、孤立、缺ID及非1:1仍分列，不按位置补配；147个不可识别tool字段仍未知身份 |",
             f"| Solver返回归属 | v2将 {solver['v2_retrieval_rows_duplicate_returns']:,} 个操作返回重复挂到检索行 | v3按事件类型归属：操作事件 {solver['v3_operation_return_records']:,} 个，检索事件 {solver['v3_retrieval_return_records']:,} 个，总计 {solver['v3_total_unique_return_records_in_solver_rows']:,} | 返回只表示保存的execution事件结果字段，不代表成功执行；retrieval仍用独立单位 |",
             '', 'v2与历史原始文件保持原字节。v2绑定源码在修改前的精确快照位于 `env/public-trace-operations-v3/source-before-edit/`；v3 manifest同时登记快照、当前代码及输入输出哈希。']
    return '\n'.join(lines) + '\n'


def imported_rows(inputs, package):
    path = 'reports/analysis/' + package + '/per_trajectory.jsonl'
    return [json.loads(line) for line in inputs.read(path).decode().split('\n') if line]


def osworld_summary(inputs, old, manifest):
    base = 'reports/analysis/OSWORLD-task-behavior-v3/'
    tasks = {r['task_key']: r for r in [json.loads(x) for x in inputs.read(base + 'task_semantics.jsonl').decode().split('\n') if x]}
    rows = imported_rows(inputs, 'OSWORLD-task-behavior-v3')
    expected = {r['path']: r for r in manifest['inputs']}
    by_model = defaultdict(list); by_app = defaultdict(list); examples = {}
    for row in rows:
        # Existing source_file is relative to the downloaded trajectory root.
        name = 'data/raw/public/osworld2_trajectory_light/' + row['source_file']
        data = inputs.read(name, expected[name])
        native = Counter(); interfaces = Counter()
        for line in data.decode().split('\n'):
            if not line.strip(): continue
            obj = json.loads(line); action = obj.get('action')
            if isinstance(action, dict):
                payload = action.get('input') if isinstance(action.get('input'), dict) else action.get('action')
                action_name = payload.get('action') if isinstance(payload, dict) else None
                if isinstance(action_name, str): native[action_name] += 1
                elif action.get('action_type') in ('computer_call', 'tool_use'): native['unknown'] += 1
                if action.get('action_type'): interfaces[str(action['action_type'])] += 1
        item = {'task': row['task_key'], 'native': dict(native), 'static': row['static_category_counts'],
                'interfaces': dict(interfaces), 'applicable': row['native_representation_status'] == 'applicable',
                'analysis_status': row['analysis_status']}
        if sum(native.values()) != row['native_action_record_count']: raise ValueError('OSWorld native action count drift')
        by_model[row['model']].append(item)
        apps = tasks[row['task_key']].get('related_apps')
        apps = apps if isinstance(apps, list) else [apps] if isinstance(apps, str) else ['unknown']
        for app in set(apps or ['unknown']): by_app[(row['model'], str(app))].append(item)
    def summarize(rr):
        native = Counter(); static = Counter(); interfaces = Counter()
        for r in rr: native.update(r['native']); static.update(r['static']); interfaces.update(r['interfaces'])
        return {'trajectory_count': len(rr), 'native_applicable_trajectories': sum(r['applicable'] for r in rr),
                'native_saved_actions': shares(native), 'static_source_call_categories': shares(static),
                'saved_interfaces': dict(interfaces), 'analysis_status_counts': dict(Counter(r['analysis_status'] for r in rr))}
    return {'models': {m: summarize(rr) for m, rr in sorted(by_model.items())},
            'declared_application_scenarios': [{'model': m, 'declared_app': app, **summarize(rr)} for (m, app), rr in sorted(by_app.items())],
            'toolkit': ['computer/computer_call/tool_use saved actions: click, key/type/hotkey, scroll, pointer, screenshot, wait',
                        'pyautogui command-source static calls, kept separate from native actions'],
            'limits': ['declared related_apps are overlapping task-definition context, not proof which application each action operated on',
                       'historical task-version binding unknown; no application-specific business action is inferred from clicks',
                       'native action counts and static Python calls are separate denominators, never added together',
                       'no public DocOps tool execution corpus in this source set; local xlsx/ppt/pdf tools excluded']}


def assistant_summary(inputs, old):
    rows = imported_rows(inputs, 'TOOLSANDBOX-HEPM-behavior-v2')
    groups = defaultdict(list); scenarios = defaultdict(list)
    for row in rows:
        groups[row['group_directory']].append(row)
        for activity in row['activity_call_counts']:
            scenarios[(row['group_directory'], activity)].append(row)
    def summarize(rr):
        activity = Counter(); native = Counter(); called = Counter(); presence = Counter(); n = 0
        for row in rr:
            n += row['pairing']['tool_call_entries']; activity.update(row['activity_call_counts'])
            native.update(row['native_identity_counts']); called.update(row['called_name_counts'])
            presence.update(k for k, v in row['native_identity_counts'].items() if v)
        activity['unknown'] += n - sum(activity.values())
        return {'trajectory_count': len(rr), 'activities': shares(activity),
                'resolved_native_tools': {'all_call_denominator': n, 'resolved_count': sum(native.values()),
                                          'unresolved_identity_count': n - sum(native.values()), 'counts': dict(native),
                                          'percent_all_calls': {k: 100*v/n if n else None for k,v in native.items()}},
                'called_interfaces': shares(called), 'native_tool_trajectory_presence': dict(presence)}
    return {'groups': {g: summarize(rr) for g, rr in sorted(groups.items())},
            'conditional_activity_scenarios': [{'group': g, 'activity_present': a, **summarize(rr)} for (g, a), rr in sorted(scenarios.items())],
            'available_tool_inventory': old['tool_interface']['native_tool_names'],
            'native_tool_to_activity': old['tool_interface']['activity_classification'],
            'limits': ['H-EPM third-party extension, not Apple official trace release',
                       'available allow-list names are not all observed calls; observed and resolved identities kept separate',
                       'scenario groups are conditional overlapping slices; group-wide counts retain zero-call traces',
                       'two groups share scenario keys and have different source revisions; no causal comparison',
                       'summarize_the_task is H-EPM harness overhead, not a business tool; User end_conversation not agent calls']}


def render_toolkits(summary):
    """Readable scene/tool map, based only on observed identities and saved context."""
    lines = ['# 不同场景常用哪些工具', '',
             '工具名来自保存调用/动作，不把任务中提到的软件名当作已调用API。调用次数和轨迹覆盖分开；以下不是性能或能力排名。', '',
             '## Coding：工具接口与命令程序两层', '',
             '| 场景 | 可观察工具/命令 | 分类边界 |', '| --- | --- | --- |',
             '| 文件定位 | Glob/glob、find_file、find/ls、rg --files | 定位路径，不与内容检索合并 |',
             '| 内容/符号检索 | Grep/grep、search_file/search_dir、rg、find_symbols、SearchCode | 结构化搜索节点与shell调用分母不同 |',
             '| 文件查看 | Read/read、open、编辑器view、cat/head/sed -n | head也可作为检索命令的输出过滤，组合单列 |',
             '| 修改内容 | Edit/edit、Write、str_replace_based_edit_tool、apply_patch | 文件管理cp/mv等另列 |',
             '| 构建/编译 | make、cmake、编译器、python setup.py build等明确命令头/参数 | 不从thought中出现build一词推断 |',
             '| 测试 | pytest、python -m pytest/unittest、npm test、cargo/go test等 | grep/echo提及pytest不是测试 |',
             '| 环境准备 | pip、uv、conda、npm install等 | 与构建、测试分开 |', '',
             '上表是有限分类规则对应的工具族，不声称每个来源都调用了全部工具；下表给实际出现的原生接口。', '',
             '| 来源/组 | 保存记录数 | 保存单位数 | 实际高频接口（次数；出现记录数） |', '| --- | ---: | ---: | --- |']
    for g in summary['coding']['groups']:
        top = sorted(g['native_tools']['counts'].items(), key=lambda x: -x[1])[:8]
        names = '；'.join(f"`{name}` {n:,}；{g['tool_record_presence'][name]}条" for name, n in top)
        lines.append(f"| {g['source']} / {g['group']} | {g['record_count']} | {g['operations']['denominator']} | {names} |")
    lines += ['', '### Coding各来源组的互斥操作构成与命令程序', '',
              '主标签每个保存单位恰好一个；命令程序为静态拆分的程序名，另用组件分母，不能解释为运行次数。没有命令参数的结构化接口不会被强行映射成shell程序。', '',
              '| 来源/组 | 单位/分母 | 常见主操作（次数；占本组单位） | 常见原生接口 | 常见命令程序（静态组件次数） | 参数可用性（结构化/命令） |',
              '| --- | --- | --- | --- | --- | --- |']
    for g in summary['coding']['groups']:
        den = g['operations']['denominator']
        if g.get('saved_process_node_count'):
            ops = f"保存过程节点 {g['saved_process_node_count']:,}（非工具调用）"
        else:
            ops = '；'.join(f"{LABELS[k]} {v:,}（{100*v/den:.1f}%）" for k, v in
                            sorted(g['operations']['counts'].items(), key=lambda x: -x[1])[:4]) if den else '无可分类保存单位'
        heads = '；'.join(f'`{k}` {v:,}' for k, v in sorted(g['executables']['counts'].items(), key=lambda x: -x[1])[:5]) or '无命令组件'
        native = ('非工具单位' if g.get('saved_process_node_count') else
                  '；'.join(f'`{k}` {v:,}' for k, v in sorted(g['native_tools']['counts'].items(), key=lambda x: -x[1])[:5]) or '无接口名')
        args = f"{g['structured_arguments_available_count']:,}/{den:,}；命令 {g['saved_command_available_count']:,}/{den:,}"
        lines.append(f"| {g['source']} / {g['group']} / {g['unit_kind']} | {g['record_count']} / {den:,} | {ops} | {native} | {heads} | {args} |")
    masai = _group_record(summary['coding']['groups'], '20240612_MASAI_gpt4o') or {
        'operations': {'denominator': 0}, 'call_return_evidence': {'return_record_count': 0}, 'subagents': {}}
    lines += ['', '### MASAI 子Agent动作（明确 Model response 段）', '',
              f"submission 合计 {masai['operations']['denominator']:,} 个动作单位；返回块 {masai['call_return_evidence']['return_record_count']:,} 个，无原生ID，未按顺序配对。", '',
              '| 子Agent | 动作数 | 主操作构成 | 原生动作标签 |', '| --- | ---: | --- | --- |']
    if masai:
        for agent, item in sorted(masai['subagents'].items()):
            total = item['unit_count']
            ops = '；'.join(f"{LABELS[k]} {v:,} ({100*v/total:.1f}%)" for k, v in
                            sorted(item['operation_counts'].items(), key=lambda x: -x[1])) if total else '—'
            native = '；'.join(f'`{k}`={v:,}' for k, v in sorted(item['native_tool_counts'].items(), key=lambda x:-x[1]))
            lines.append(f"| {agent} | {total:,} | {ops} | {native} |")
    lines += ['', 'MASAI 输入prompt和响应段外的标签不计作调用；动作返回独立保存，未按相邻顺序强配。',
              '各代码仓库切片的同类统计在toolkits.json的coding.repository_scenarios；这是仓库来源切片，不是独立随机任务类别。', '',
              '## Computer/Office：桌面操作，不是文档API日志', '',
              'OSWorld保存接口以computer/computer_call/tool_use原生动作、以及pyautogui命令源码呈现。两者不能相加。', '',
              '| 保存接口层 | 常见动作 | 能说明什么 |', '| --- | --- | --- |',
              '| 原生桌面动作 | left_click/double_click、key/type/hotkey、scroll、mouse_move/drag、screenshot、wait | 已保存的动作接口分布 |',
              '| command静态源码 | pyautogui点击、按键、输入、滚动、移动；sleep等等待源码 | 静态可识别调用，不是实际GUI执行次数 |', '',
              '### 按任务声明应用分组', '',
              '同一任务可以涉及多个应用，因此以下场景重叠；应用来自当前下载的任务定义，与历史轨迹版本对应仍unknown。动作不自动归因给该应用。', '',
              '| 任务声明应用 | 涉及模型×任务记录 | 原生动作中高频保存名 |', '| --- | ---: | --- |']
    apps = defaultdict(list)
    for r in summary['computer_office']['declared_application_scenarios']: apps[r['declared_app']].append(r)
    for app, rr in sorted(apps.items()):
        native = Counter()
        for r in rr: native.update(r['native_saved_actions']['counts'])
        lines.append(f"| {app} | {sum(r['trajectory_count'] for r in rr)} | " + '；'.join(f'`{k}`={v:,}' for k,v in native.most_common(5)) + ' |')
    lines += ['', '具体模型下的应用切片、动作比例在toolkits.json；MiniMax-M3/Qwen的原生字段不适用，不填成0。',
              '未找到公开DocOps执行轨迹，不能据此列出openpyxl/python-docx等库的公开调用占比；本地DocOps测量在另一个证据集合，不混入本轮。', '',
              '## Assistant：状态化个人助理工具', '',
              '| 来源组 | 活动 | 保存调用数（全部调用占比） | 已还原原生身份中实际调用的工具 |', '| --- | --- | ---: | --- |']
    mapping = summary['assistant']['native_tool_to_activity']
    for group, row in summary['assistant']['groups'].items():
        for activity, n in sorted(row['activities']['counts'].items(), key=lambda x:-x[1]):
            native = [(k,v) for k,v in row['resolved_native_tools']['counts'].items() if mapping.get(k) == activity]
            names = '；'.join(f'`{k}`={v}' for k,v in sorted(native, key=lambda x:-x[1])) or '身份未完全还原，保留Unknown/活动级证据'
            lines.append(f"| {group} | {activity} | {n}（{row['activities']['percent_all'][activity]:.2f}%） | {names} |")
    lines += ['', '联系人、提醒、消息、设备状态、日期时间、位置/天气与网络查询分开。summarize_the_task属于H-EPM框架辅助，不与业务工具混称；allow-list中可用不代表实际调用。', '',
              '## 宏观模板与视频', '',
              '- AgentX：可分析请求与subagent结构，缺具体业务工具名，工具集无法从该语料恢复。',
              '- Applied Compute：agentic_coding/code_qa/office_work是派生模板类别，不是工具名或真实Office执行日志。',
              '- Video：当前VideoWeaver旧样本为宏观/部分解析；不在这里用推测的FFmpeg或生成工具名填补公开视频工具集。', '',
              '[操作占比与限制](summary.md) · [完整机器可读工具集](toolkits.json) · [覆盖清单](coverage.json)']
    return '\n'.join(lines)+'\n'


def write_operation_csv(path, coding):
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['source', 'group', 'unit_kind', 'records', 'all_units', 'operation',
                         'exclusive_label_count', 'exclusive_percent_all',
                         'contains_operation_calls', 'contains_percent_all_nonexclusive'])
        for row in coding['groups']:
            for label in LABELS:
                writer.writerow([row['source'], row['group'], row['unit_kind'], row['record_count'],
                    row['operations']['denominator'], label, row['operations']['counts'].get(label, 0),
                    row['operations']['percent_all'].get(label, 0) if row['operations']['denominator'] else None,
                    row['operation_call_presence']['counts'].get(label, 0),
                    row['operation_call_presence']['percent_all_calls'].get(label, 0) if row['operations']['denominator'] else None])


def render_coverage(inventory):
    lines = ['# SWE-bench 本地对象覆盖清单', '',
             '覆盖范围是三轮获取manifest登记的本地对象，不等同于上游所有公开提交。每个登记文件均按登记bytes/SHA回读；跨登记身份冲突、缺失或漂移单独隔离。文件状态是证据分类，不直接等于轨迹数。', '',
             '| submission | 对象 | 明确动作记录 | 保存过程节点 | 部分/歧义 | 配套产物 | 缺失/身份冲突 | 动作候选/提取/拒绝 |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for group, counts in inventory['per_group_status_counts'].items():
        all_items = [x for x in inventory['objects'] if x['group'] == group]
        nodes = sum(x.get('saved_process_node_count') or 0 for x in all_items)
        candidates = sum(x.get('candidate_action_segment_count') or 0 for x in all_items)
        extracted = sum(x.get('extracted_action_segment_count') or 0 for x in all_items)
        rejected = sum(x.get('rejected_or_ambiguous_segment_count') or 0 for x in all_items)
        lines.append(f"| {group} | {len(all_items)} | {counts.get('actions_extracted', 0)} | {nodes:,} | {counts.get('process_partial_or_ambiguous', 0)} | {counts.get('companion_artifact', 0)} | {counts.get('missing_registered_file', 0) + counts.get('isolated_content_identity_mismatch', 0) + counts.get('isolated_registration_conflict', 0)} | {candidates:,} / {extracted:,} / {rejected:,} |")
    lines += ['',
              f"互斥文件分流：登记对象 {inventory['registered_object_count']:,} = 动作对象 {inventory['action_object_count']:,} + 部分/歧义对象 {inventory['process_partial_or_ambiguous_count']:,} + 有正面依据的配套产物 {inventory['companion_artifact_count']:,}。其中部分/歧义对象内有 {inventory['process_node_object_count']:,} 个保存过程节点的对象（{inventory['saved_process_node_count']:,} 个节点），该子集不另加到对象总数。缺失 {inventory['missing_registered_count']:,}；哈希漂移 {inventory['identity_mismatch_count']:,}；登记冲突 {inventory['registration_conflict_count']:,}。动作单位 {inventory['parsed_unit_count']:,}；静态命令组件另有独立分母。", '',
              '覆盖按逐文件协议、候选段、提取段及拒绝/歧义段记录。已提取一个动作不自动意味着整文件完整；C类必须有配套产物的正面结构或文件依据。SWE-Exp保存节点独立计数，不当作工具调用或时间线。',
              '调用与返回只有显式ID或同一原生记录结构提供的关系才标明；无ID的结果单列，不按数组位置或命令文本强配。自由叙述、thought、system/user示例命令不计入调用。', '',
              f"实际存在但未登记的路径数：{len(inventory['unregistered_actual_paths'])}；路径逐项见coverage.json。", '',
              'JSONL解析异常、非UTF-8、登记缺失/哈希漂移、以及仍未纳入显式读取协议的每个文件，均在coverage.json逐项给出status与reason_code。', '',
              '[逐文件覆盖JSON](coverage.json) · [操作总结](summary.md)']
    return '\n'.join(lines)+'\n'


def render(summary):
    coding = summary['coding']; inv = summary['swebench_inventory']; rb = coding['swe_rebench_pooled']
    delta = summary['swebench_v1_comparison']
    fixes = summary['corrections']
    lines = ['# 公开轨迹：操作构成与常用工具集', '',
             '本轮仅离线读取公开数据与已验收分析；不运行轨迹、Agent、工具或模型。比例均注明来源、分母和可识别范围。', '',
             '## 先看结论', '',
             '- Coding：终端/shell、文件/代码检索、文件查看、编辑接口，以及命令内的构建/测试共同构成工具集；不能把 bash 都叫作“执行”。',
             '- Computer/Office：这里的公开证据来自 OSWorld 的桌面操作接口与 pyautogui 源码；可描述点击、输入、滚动等，不能从点击自动判断“编辑公式”。',
             '- Assistant：联系人、消息、提醒、设备设置、日期时间、位置/天气/查询等结构化工具；H-EPM 的摘要工具单列为框架辅助。',
             '- AgentX 与 Applied Compute 没有可用于统计具体工具名的完整工具日志；模板名 office_work 不证明使用了某个 Office API。',
             '- VideoWeaver 既有小样没有在本轮升级成完整公开工具语料；视频工具集仍不能从现有公开证据完整汇总。', '',
             '## Coding：SWE-rebench 全量已登记语料', '',
             f"{rb['record_count']:,} 条轨迹、{rb['operations']['denominator']:,} 个保存的 tool_call、{rb['call_return_evidence']['return_record_count']:,} 个 tool_result；按原生ID只对唯一1:1计关联，不是平均 participant，也不是耗时/CPU占比。", '',
             '| 操作 | 单一主要用途/组合标签次数 | 占全部保存调用 |', '| --- | ---: | ---: |']
    for label, count in sorted(rb['operations']['counts'].items(), key=lambda x: -x[1]):
        lines.append(f"| {LABELS[label]} | {count:,} | {rb['operations']['percent_all'][label]:.3f}% |")
    lines += ['', 'mixed=一个保存调用中包含多类可识别操作；partial=含未识别片段；script_execute只确认解释器执行，不能细说用途。Unknown不排除分母。', '',
              '### 含某类操作的调用（允许重叠）', '',
              '一次 `grep ... | head ...` 同时涉及检索和查看。下表每类在同一调用内最多记一次，分母仍为全部调用；类别间不能相加成100%，也不证明条件分支实际执行。', '',
              '| 保存命令涉及的操作 | 调用数 | 全部调用占比 |', '| --- | ---: | ---: |']
    for label, count in sorted(rb['operation_call_presence']['counts'].items(), key=lambda x: -x[1]):
        lines.append(f"| {LABELS[label]} | {count:,} | {rb['operation_call_presence']['percent_all_calls'][label]:.3f}% |")
    lines += ['',
              '### 常用原生工具接口', '', '| 接口 | 调用数 | 调用占比 | 出现轨迹 / 全部轨迹 |', '| --- | ---: | ---: | ---: |']
    for name, n in sorted(rb['native_tools']['counts'].items(), key=lambda x: -x[1])[:15]:
        lines.append(f"| `{name}` | {n:,} | {rb['native_tools']['percent_all'][name]:.2f}% | {rb['tool_record_presence'][name]} / {rb['record_count']} |")
    lines += ['', f"其中有 {rb['unparsed_native_tool_identity_count']:,} 条 tool_call 的 tool 字段不是受支持的短接口标识（如包含多行正文或超长内容）；按 `unparsed_tool_identity` 计入未知接口，逐组保留长度与SHA-256，不把该正文当接口名展示。原始事件位置仍可回查。", '']
    lines += ['', '### 常见命令程序（源码片段口径）', '',
              '以下是保存命令静态拆分后的程序名频数，不是实际执行次数；&&/||、管道等不证明所有分支都执行。', '',
              ', '.join(f'`{k}`={v:,}' for k, v in sorted(rb['executables']['counts'].items(), key=lambda x: -x[1])[:25]), '',
              '### 分组与仓库场景', '',
              'toolkits.json 保留每个 participant、每个原生 submission、每个代码仓库切片的完整操作/工具计数、调用占比与轨迹出现次数；不合并跨格式分母。', '',
              '## SWE-bench：本地三轮登记对象', '',
             f"登记对象 {inv['registered_object_count']:,} 个，覆盖 {inv['registered_group_count']} 个 submission；互斥文件分流为动作对象 {inv['action_object_count']:,}、部分/歧义 {inv['process_partial_or_ambiguous_count']:,}、有正面依据的配套产物 {inv['companion_artifact_count']:,}。其中部分/歧义对象内有 {inv['process_node_object_count']:,} 个文件保存 {inv['saved_process_node_count']:,} 个过程节点（不是工具调用，且不另加到对象数）；动作单位 {inv['parsed_unit_count']:,}。缺失/身份漂移/登记冲突为 {inv['missing_registered_count']:,}/{inv['identity_mismatch_count']:,}/{inv['registration_conflict_count']:,}。", '',
              '不同协议按来源组保留原生工具与操作分母；SWE-Exp过程节点、Solver retrieval、Moatless transition和shell调用不混成同一种单位。对象并非都是真实执行轨迹。逐组清单见[coverage.md](coverage.md)，逐文件原因见coverage.json。', '',
             '| submission | 单位类型 | 保存记录数 | 单位总数 | Unknown / Partial |', '| --- | --- | ---: | ---: | ---: |']
    for group in coding['groups']:
        if group['source'] != 'SWE-bench': continue
        c = group['operations']['counts']
        lines.append(f"| {group['group']} | {group['unit_kind']} | {group['record_count']} | {group['operations']['denominator']} | {c.get('unknown', 0)} / {c.get('partial', 0)} |")
    lines += ['', '### 集中更正与 v2 对照', '',
              f"SAGE的命令协议、SWE-Exp过程节点、MASAI三个子Agent阶段、Learn-by-Interact编辑块、SWE-rebench原生调用关联及Solver返回归属均已按本地记录重算；详见[逐项更正](corrections.md)。例如MASAI v2计 {fixes['masai']['v2_action_count']:,} 次，v3计 {fixes['masai']['v3_action_count']:,} 次；Learn-by-Interact file_edit由 {fixes['learn_by_interact']['v2_file_edit_count']:,} 增至 {fixes['learn_by_interact']['file_edit_extracted_block_count']:,} 次。", '',
              f"v1标记{delta['v1_interpreted_objects']:,}个对象已解释、{delta['v1_parsed_units']:,}个保存单位；v3相对v1新增{delta['new_action_objects_beyond_v1']:,}个含明确动作的对象、{delta['new_units_beyond_v1']:,}个动作单位。该差值包含读取规则改变，不代表新增下载。", '',
              'v2绑定的脚本、分类器与测试原始字节及SHA已保存在env/public-trace-operations-v3/source-before-edit/；v1/v2报告和manifest保持原样。历史绑定代码与当前代码的路径/字节差异见summary.json与manifest。', '',
              '不解析自由文本中的thought、prompt或示例命令作为真实工具调用。Moatless与SWE-Exp保存过程节点不当作工具执行；Solver retrieval也独立列为检索事件。B类不等于“文件没有动作”，C类须有正面配套产物依据。', '',
              '## Computer/Office：OSWorld', '',
              '| 模型 | 轨迹 | 原生动作记录 | 静态源码调用节点 |', '| --- | ---: | ---: | ---: |']
    for model, row in summary['computer_office']['models'].items():
        lines.append(f"| {model} | {row['trajectory_count']} | {row['native_saved_actions']['denominator'] if row['native_applicable_trajectories'] else '不适用'} | {row['static_source_call_categories']['denominator']} |")
    lines += ['', '### 各模型保存的常用桌面动作', '']
    for model, row in summary['computer_office']['models'].items():
        native = row['native_saved_actions']
        if row['native_applicable_trajectories']:
            lines.append('- ' + model + '：' + '、'.join(f"`{k}` {v:,}（{native['percent_all'][k]:.1f}%）" for k,v in sorted(native['counts'].items(), key=lambda x:-x[1])[:8]))
        else: lines.append('- ' + model + '：原生动作字段不适用；只报告另一层静态源码类别，不填原生动作0%。')
    lines += ['', '原生动作保存了点击、键盘输入、滚动、指针移动、截图和等待等接口；静态 command 调用单列，不能与原生动作重复相加，也不证明实际GUI执行次数。',
              '按任务定义声明的应用（浏览器、表格、文档、邮件等）分组的动作构成见toolkits.json。一个任务可涉及多个应用，不把多应用切片强行加成100%。历史任务版本绑定仍unknown。',
              '没有公开DocOps执行轨迹作为本轮分母；不能把本地DocOps的xlsx/ppt/pdf工具名单冒充公开Office工具统计。', '',
              '## Assistant：H-EPM ToolSandbox', '']
    for group, row in summary['assistant']['groups'].items():
        lines += [f'### {group}', '', f"{row['trajectory_count']} 条轨迹，{row['activities']['denominator']} 个Agent调用。", '',
                  '| 活动 | 调用数 | 全部调用占比 |', '| --- | ---: | ---: |']
        for k, v in sorted(row['activities']['counts'].items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} | {row['activities']['percent_all'][k]:.2f}% |")
        lines += ['', '常用已解析原生工具：' + ', '.join(f'`{k}`={v}' for k,v in sorted(row['resolved_native_tools']['counts'].items(), key=lambda x:-x[1])[:12]), '']
    lines += ['允许工具清单不等于实际调用；扰动名的身份解析依据既有v2的SANDBOX记录，24条无法分类调用保留Unknown。User结束工具和Agent业务调用不混合。', '',
              '## 不可提供具体工具集的来源', '',
              '- AgentX：请求流及显式subagent结构，具体业务工具名/参数未提供。',
              '- Applied Compute：三类派生workload模板，只有轮次、token长度与模拟延迟；没有实际Office API调用。',
              '- VideoWeaver：现有宏观小样/部分解析不能替代完整公开视频工具语料。', '',
              '## 口径与可复核性', '',
              '- 主操作比例：每个保存单位一个标签，含mixed/partial/unknown，合计等于该来源分母。',
              '- 文本查看包括cat/read以及管道中的head/tail输出截取，不都代表直接打开源码文件；内容修改/写入也包含生成脚本与其他文件，不冒称全部都是仓库源码修改。',
              '- 组件比例：静态命令片段单独分母，只表示保存源码构成，不是实际执行频率。',
              '- 重定向只辅助识别命令用途：测试日志保存不另算一次工具操作；单条echo/printf/cat输出写入文件另识别为写入。仅对单个闭合、字面量marker及已知消费者的heredoc做静态解析，不执行正文；其他情况Unknown。',
              '- 常用工具同时给调用频数和轨迹出现数，避免少数长轨迹决定全部结论。',
              '- 所有分类都不代表时间或CPU占比；没有新增性能、成功率或因果结论。',
              '- 不执行数据中的代码、AST、shell、工具、evaluator；不读取凭据或访问网络。', '',
              '## 历史更正', '',
              '原90条子集中的SWE-agent组，旧summary.md写1053个action，但同包summary.json接口与活动合计均为1064。本轮从该组30份原件重新统计，见summary.json的historical_corrections；旧包不改写。', '',
              '[场景工具表](toolkits.md) · [逐项更正](corrections.md) · [操作统计CSV](coding_operations.csv) · [summary.json](summary.json) · [toolkits.json](toolkits.json) · [coverage.json](coverage.json) · [per_trajectory.jsonl](per_trajectory.jsonl) · [manifest.json](manifest.json)']
    return '\n'.join(lines) + '\n'


def run(root, out):
    root = Path(root); out = Path(out)
    if out.exists(): raise FileExistsError('refusing to overwrite output')
    inputs = Inputs(root); packages = {}
    for name in PACKAGES:
        print('verifying source package', name, flush=True)
        packages[name] = inputs.package(name)
    old_v1, old_v1_manifest = inputs.package('PUBLIC-TRACE-OPERATIONS-v1')
    old_v2, old_v2_manifest = inputs.package('PUBLIC-TRACE-OPERATIONS-v2')
    print('verified source analysis outputs', flush=True)
    registrations, registration_conflicts = load_registrations(inputs)
    rows = analyze_rebench(inputs, packages['SWE-REBENCH-behavior-v2'][0])
    print('classified SWE-rebench', len(rows), flush=True)
    swe_rows, inventory = analyze_swebench(inputs, registrations, registration_conflicts); rows += swe_rows
    print('inventoried SWE-bench', inventory['registered_object_count'], 'interpreted', len(swe_rows), flush=True)
    old_coverage = inputs.json('reports/analysis/PUBLIC-TRACE-OPERATIONS-v1/coverage.json')
    old_objects = {x['path']: x for x in old_coverage.get('objects', [])}
    new_object_map = {x['path']: x for x in inventory['objects']}
    inventory['v1_comparison'] = {
        'v1_interpreted_objects': old_coverage.get('interpreted_object_count'),
        'v1_parsed_units': sum(x.get('unit_count') or 0 for x in old_objects.values()),
        'new_action_objects_beyond_v1': sum(1 for path, item in new_object_map.items()
                                           if item.get('action_unit_count') and not old_objects.get(path, {}).get('interpreted')),
        'new_units_beyond_v1': sum((item.get('action_unit_count') or 0) for path, item in new_object_map.items()
                                   if not old_objects.get(path, {}).get('interpreted'))}
    osworld = osworld_summary(inputs, *packages['OSWORLD-task-behavior-v3'])
    assistant = assistant_summary(inputs, packages['TOOLSANDBOX-HEPM-behavior-v2'][0])
    macro = packages['AGENTX-APPLIED-MACRO-v1'][0]
    selection = inputs.json('reports/analysis/SWEBENCH-subset-behavior-v1/selection.json')
    first = selection['groups'][0]
    selected = []
    for item in first['items']:
        obj = inputs.json(item['file'], item)
        selected.append(len(obj['trajectory']))
    old_group = packages['SWEBENCH-subset-behavior-v1'][0]['groups'][first['submission']]
    json_total = sum(old_group['interface_totals'].values())
    old_text = inputs.read('reports/analysis/SWEBENCH-subset-behavior-v1/summary.md').decode()
    match = re.search(r'sweagent 组 ([\d,]+) 个 action', old_text)
    historical_corrections = {'sweagent_old_30': {'reported_text_total': int(match.group(1).replace(',', '')) if match else None,
                                     'registered_json_total': json_total,
                                     'raw_recomputed_total': sum(selected),
                                     'old_artifacts_modified': False}}
    if sum(selected) != json_total: raise ValueError('old subset discrepancy needs further review')
    coding = coding_summary(rows)
    old_v2_coverage = inputs.json('reports/analysis/PUBLIC-TRACE-OPERATIONS-v2/coverage.json')
    issue_corrections = correction_summary(old_v2, old_v2_coverage, coding, inventory)
    for path in (Path(__file__), PROJECT/'src/agent_workload_characterization/analyzers/public_operations.py', PROJECT/'tests/test_public_trace_operations.py'):
        inputs.read(root/path.relative_to(PROJECT))
    v1_snapshot_manifest = 'env/public-trace-operations-v2/source-before-edit/manifest.json'
    v1_source_snapshot = inputs.json(v1_snapshot_manifest)
    for item in v1_source_snapshot['files']:
        inputs.read('env/public-trace-operations-v2/source-before-edit/' + item['path'], item)
    v2_snapshot_manifest = 'env/public-trace-operations-v3/source-before-edit/manifest.json'
    v2_source_snapshot = inputs.json(v2_snapshot_manifest)
    for item in v2_source_snapshot['files']:
        inputs.read('env/public-trace-operations-v3/source-before-edit/' + item['path'], item)
    v1_sources = {item['path']: item for item in old_v1_manifest['inputs']
                  if item['path'] in {'scripts/public_trace_operations.py',
                    'src/agent_workload_characterization/analyzers/public_operations.py',
                    'tests/test_public_trace_operations.py'}}
    current_sources = {name: item for name, item in inputs.files.items()
                       if name in {'scripts/public_trace_operations.py',
                         'src/agent_workload_characterization/analyzers/public_operations.py',
                         'tests/test_public_trace_operations.py'}}
    v2_sources = {item['path']: item for item in old_v2_manifest['inputs']
                  if item['path'] in {'scripts/public_trace_operations.py',
                    'src/agent_workload_characterization/analyzers/public_operations.py',
                    'tests/test_public_trace_operations.py'}}
    summary = {'schema': 'public-trace-operations-v3', 'coding': coding,
               'swebench_inventory': {k:v for k,v in inventory.items() if k != 'objects'},
               'swebench_v1_comparison': inventory['v1_comparison'],
               'corrections': issue_corrections,
               'v1_source_provenance': {'v1_manifest_inputs': v1_sources,
                   'current_analysis_code': current_sources,
                   'preserved_exact_v1_source_snapshot': v1_source_snapshot['files'],
                   'v1_report_and_manifest_modified': False},
               'v2_source_provenance': {'v2_manifest_inputs': v2_sources,
                   'preserved_exact_v2_source_snapshot': v2_source_snapshot['files'],
                   'current_analysis_code': current_sources,
                   'source_bytes_drifted_since_v2': {name: v2_sources.get(name) != current_sources.get(name)
                                                     for name in v2_sources},
                   'v2_report_and_manifest_modified': False},
               'computer_office': osworld, 'assistant': assistant,
               'macro_sources': macro['sources'], 'historical_corrections': historical_corrections,
               'taxonomy': LABELS,
               'scope': 'public data only; no local resource runs; source-specific denominators; no blanket completeness claim',
               'limits': ['SWE-bench each registered object assigned an evidence-based status; B/C are not proof that the historical run had no actions',
                          'command source occurrences are not execution or resource counts',
                          'OSWorld native and static representations never pooled',
                          'H-EPM extension is third-party; Applied templates are not real tool traces',
                          'Video public toolkit evidence incomplete; no remote CPU claims']}
    out.mkdir(parents=True)
    (out/'per_trajectory.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, separators=(',',':'))+'\n' for r in rows))
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (out/'toolkits.json').write_text(json.dumps({'coding': coding, 'computer_office': osworld, 'assistant': assistant}, ensure_ascii=False, indent=2)+'\n')
    (out/'coverage.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
    (out/'coverage.md').write_text(render_coverage(inventory))
    (out/'summary.md').write_text(render(summary))
    (out/'toolkits.md').write_text(render_toolkits(summary))
    write_operation_csv(out/'coding_operations.csv', coding)
    (out/'corrections.md').write_text(render_corrections(issue_corrections))
    # Catch changes during a long single-pass analysis before sealing results.
    for item in list(inputs.files.values()):
        reread = (root / item['path']).read_bytes()
        if len(reread) != item['bytes'] or digest(reread) != item['sha256']:
            raise ValueError('input changed during analysis: ' + item['path'])
    outputs = [{'path': str(p.relative_to(root)), 'bytes': p.stat().st_size, 'sha256': digest(p.read_bytes())}
               for p in sorted(out.iterdir()) if p.is_file()]
    manifest = {'schema': 'public-trace-operations-manifest-v3', 'inputs': list(inputs.files.values()),
                'outputs': outputs, 'manifest_self_hash': 'excluded',
                'verification_scope': 'Three acquisition manifests and every registered SWE-bench object bytes/SHA; scoped local object-set difference; exact v1/v2 source report outputs; v2-bound source snapshot; current analysis code; selected OSWorld raw action files; H-EPM and macro outputs reused, not re-executed; old v1/v2 reports and raw files not modified'}
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    # Read back every sealed report output; manifest intentionally excludes itself.
    for item in outputs:
        raw = (root / item['path']).read_bytes()
        if len(raw) != item['bytes'] or digest(raw) != item['sha256']:
            raise ValueError('output hash readback mismatch: ' + item['path'])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(PROJECT, args.output_dir.resolve())
    return 0


if __name__ == '__main__': raise SystemExit(main())
