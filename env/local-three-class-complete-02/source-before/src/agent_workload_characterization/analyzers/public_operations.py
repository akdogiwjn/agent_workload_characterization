"""Static operation labels for saved Coding calls; never executes source text.

One primary label per saved call. Shell components describe source syntax, not
how many branches actually executed. Unknown components are never discarded.
"""
from __future__ import annotations

import ast
import re
import shlex
from collections import Counter
from pathlib import PurePosixPath

LABELS = {
    'file_locate': '文件/目录定位', 'content_search': '内容/符号检索',
    'file_view': '文本查看/输出截取', 'edit_write': '内容修改/写入',
    'file_manage': '文件管理', 'environment': '环境/依赖准备',
    'build': '构建/编译', 'test': '测试/验证命令',
    'script_execute': '通用脚本执行（用途未细分）', 'vcs': '版本控制/差异检查',
    'navigate': '目录切换/定位', 'submit': '提交/结束', 'plan': '规划',
    'other': '其他明确操作', 'mixed': '多类操作组合',
    'partial': '部分可识别组合', 'unknown': '无法识别',
}


def result(parts, reason=None, heads=(), origin='command'):
    parts = parts or ['unknown']
    informative = set(parts) - {'navigate'}
    informative = informative or set(parts)
    if 'unknown' in informative:
        primary = 'partial' if informative - {'unknown'} else 'unknown'
    else:
        primary = next(iter(informative)) if len(informative) == 1 else 'mixed'
    return {'operation': primary, 'components': parts, 'reason': reason,
            'executables': list(heads), 'origin': origin}


def strip_redirections(source):
    """Remove finite shell redirections, not quoted characters or heredoc bodies.

    Redirects are bookkeeping on a command, not another saved tool call. Their
    targets are returned separately; no expansion or file access takes place.
    """
    out = []; redirects = []; i = 0; quote = None
    while i < len(source):
        c = source[i]
        if quote:
            out.append(c)
            if c == '\\' and quote == '"' and i + 1 < len(source):
                i += 1; out.append(source[i])
            elif c == quote: quote = None
            i += 1; continue
        if c in "'\"": quote = c; out.append(c); i += 1; continue
        if c == '\\' and i + 1 < len(source):
            out.extend(source[i:i+2]); i += 2; continue
        if c not in '<>': out.append(c); i += 1; continue
        if source[i:i+2] == '<<': return None, [], 'heredoc_not_interpreted'
        # Discard a preceding file descriptor only when it is a whole token.
        prefix = ''.join(out)
        fd = re.search(r'(?<!\S)\d+$', prefix)
        if fd: del out[fd.start():]
        op = c; i += 1
        if i < len(source) and source[i] == c: op += c; i += 1
        if i < len(source) and source[i] == '&': op += '&'; i += 1
        while i < len(source) and source[i] in ' \t': i += 1
        target = []; tq = None
        while i < len(source):
            c = source[i]
            if tq:
                target.append(c)
                if c == '\\' and tq == '"' and i + 1 < len(source): i += 1; target.append(source[i])
                elif c == tq: tq = None
            elif c in "'\"": tq = c; target.append(c)
            elif c == '\\' and i + 1 < len(source): target.extend(source[i:i+2]); i += 1
            elif c.isspace() or c in ';&|<>': break
            elif c in '()`' or source.startswith('$(', i): return None, [], 'dynamic_redirect_target'
            else: target.append(c)
            i += 1
        if not target or tq: return None, [], 'invalid_redirect_target'
        try: value = shlex.split(''.join(target))
        except ValueError: return None, [], 'invalid_redirect_target'
        if len(value) != 1: return None, [], 'invalid_redirect_target'
        redirects.append((op, value[0])); out.append(' ')
    return ''.join(out), redirects, None


def shell_segments(source):
    """Quote-aware finite shell grammar: words and top-level separators.

    Expansion/grouping/heredoc syntax is deliberately not interpreted here.
    Quotes containing &&, ;, | or > are data, not separators.
    """
    if not isinstance(source, str) or not source.strip():
        return None, 'empty_command'
    segments = []; words = []; word = []; quote = None; started = False
    i = 0
    def finish_word():
        nonlocal word, started
        if started:
            words.append(''.join(word)); word = []; started = False
    def finish_segment():
        finish_word()
        if words:
            segments.append(words[:]); words.clear()
    while i < len(source):
        c = source[i]
        if quote == "'":
            if c == "'": quote = None
            else: word.append(c)
        elif quote == '"':
            if c == '"': quote = None
            elif c == '`' or source.startswith('$(', i): return None, 'shell_expansion'
            elif c == '\\' and i + 1 < len(source) and source[i + 1] in '$`"\\\n':
                i += 1
                if source[i] != '\n': word.append(source[i])
            else: word.append(c)
        elif c in "'\"": quote = c; started = True
        elif c == '\\' and i + 1 < len(source):
            i += 1
            if source[i] != '\n': word.append(source[i]); started = True
        elif c == '`' or source.startswith('$(', i) or c in '()':
            return None, 'shell_expansion_or_grouping'
        elif c in '<>': return None, 'redirection_or_heredoc'
        elif c == '#' and not started:
            end = source.find('\n', i)
            if end < 0: break
            i = end; finish_segment()
        elif c in ';&|\n':
            finish_segment()
            if i + 1 < len(source) and source[i + 1] == c: i += 1
        elif c.isspace(): finish_word()
        else: word.append(c); started = True
        i += 1
    if quote: return None, 'unclosed_quote'
    finish_segment()
    return segments, None


def python_parts(source):
    """Only explicit literal file IO is refined; all other Python is generic.

    Does not unroll loops, infer function execution, evaluate expressions, or
    identify tests from words appearing in printed strings or source comments.
    """
    try: tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError): return ['script_execute'], 'python_syntax_not_supported'
    parts = []
    # Descending into control flow / definitions would turn syntax into assumed execution.
    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.For,
                          ast.While, ast.If, ast.Try, ast.Lambda, ast.ListComp,
                          ast.DictComp, ast.SetComp, ast.GeneratorExp)) for n in ast.walk(tree)):
        return ['script_execute'], 'python_control_flow_or_definitions'
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call): continue
        if isinstance(n.func, ast.Name) and n.func.id == 'open':
            mode = n.args[1] if len(n.args) > 1 else next((k.value for k in n.keywords if k.arg == 'mode'), ast.Constant('r'))
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                parts.append('edit_write' if any(c in mode.value for c in 'wax+') else 'file_view')
        elif isinstance(n.func, ast.Attribute):
            # Attribute names alone do not prove this is pathlib (or even file IO).
            owner = n.func.value
            is_path = isinstance(owner, ast.Call) and (
                isinstance(owner.func, ast.Name) and owner.func.id == 'Path' or
                isinstance(owner.func, ast.Attribute) and isinstance(owner.func.value, ast.Name)
                and owner.func.value.id == 'pathlib' and owner.func.attr == 'Path')
            if is_path and n.func.attr in {'read_text', 'read_bytes'}: parts.append('file_view')
            elif is_path and n.func.attr in {'write_text', 'write_bytes'}: parts.append('edit_write')
    return parts or ['script_execute'], 'literal_python_io' if parts else 'python_purpose_not_resolved'


def argv_operation(argv, depth=0):
    if not argv or depth > 4: return result([], 'empty_or_deep_wrapper')
    argv = list(argv)
    while argv and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', argv[0], re.S): argv.pop(0)
    if not argv: return result([], 'assignment_only')
    exe = PurePosixPath(argv[0]).name
    args = argv[1:]; low = [x.lower() for x in args]
    if exe == 'env':
        while args and (args[0].startswith('-') or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', args[0], re.S)):
            if args[0] in ('-u', '--unset') and len(args) > 1: args = args[2:]
            else: args = args[1:]
        return argv_operation(args, depth + 1)
    if exe in ('timeout', 'time'):
        # Only the simple forms used in the corpus; flags with values stay unknown.
        if exe == 'timeout' and args and re.fullmatch(r'\d+(?:\.\d+)?[smhd]?', args[0]): args = args[1:]
        elif args and args[0].startswith('-'): return result([], 'wrapper_flags_unsupported', [exe])
        return argv_operation(args, depth + 1)
    if exe in ('bash', 'sh', 'zsh') and args and args[0] in ('-c', '-lc'):
        return classify_command(args[1], depth + 1) if len(args) == 2 else result([], 'shell_wrapper_shape', [exe])
    def one(label, reason=None): return result([label], reason, [exe])
    if exe in {'open', 'readfile', 'find_file', 'search_file', 'search_dir', 'goto',
               'edit', 'create', 'replace', 'insert', 'scroll_down', 'scroll_up'}:
        return one(NATIVE[exe], 'explicit_terminal_interface')
    if exe in ('cd', 'pwd', 'pushd', 'popd'): return one('navigate')
    if exe in ('submit', 'exit_cost'): return one('submit')
    if exe in ('pytest', 'py.test', 'ctest', 'tox', 'nosetests'):
        return one('other' if set(low) & {'--help', '-h', '--version', '-v-help'} else 'test')
    if exe in ('python', 'python3', 'python3.11', 'python3.12', 'python3.10', 'python3.9'):
        # Strip finite interpreter options; never search arbitrary arguments for 'pytest'.
        while args and args[0] in ('-u', '-B', '-b', '-E', '-s', '-S', '-I', '-q'): args = args[1:]
        if args[:1] == ['-m'] and len(args) > 1:
            if args[1] in ('pytest', 'unittest'): return one('other' if set(args[2:]) & {'--help', '-h', '--version'} else 'test')
            if args[1] in ('pip', 'venv', 'virtualenv', 'ensurepip'): return one('environment')
            if args[1] in ('build', 'compileall', 'cython'): return one('build')
        if args[:1] == ['-c'] and len(args) == 2:
            parts, reason = python_parts(args[1]); return result(parts, reason, [exe], 'python_inline')
        if args and PurePosixPath(args[0]).name == 'setup.py':
            return one('build' if any(x.startswith(('build', 'bdist', 'sdist')) for x in args[1:]) else 'environment')
        if args and (args[0].endswith('/runtests.py') or args[0] == 'runtests.py' or PurePosixPath(args[0]).name == 'manage.py' and args[1:2] == ['test']): return one('test')
        return one('script_execute', 'python_script_purpose_not_resolved')
    if exe in ('npm', 'yarn', 'pnpm'):
        target = args[1] if args[:1] == ['run'] and len(args) > 1 else (args[0] if args else '')
        if target == 'test' or target.startswith('test:'): return one('test')
        if target == 'build' or target.startswith('build:'): return one('build')
        if target in ('install', 'ci', 'add', 'remove', 'update', 'init'): return one('environment')
    if exe in ('make', 'gmake', 'ninja', 'mvn', 'mvnw', 'gradle', 'gradlew', 'cargo', 'go', 'bazel'):
        if set(low) & {'--help', '-h', '--version'}: return one('other')
        if any(x in {'test', 'check', 'verify'} or x.startswith('test:') for x in low): return one('test')
        if exe in ('make', 'gmake', 'ninja') or set(low) & {'build', 'compile', 'package', 'install'}: return one('build')
    if exe in ('gcc', 'g++', 'cc', 'c++', 'clang', 'clang++', 'cmake', 'cython', 'cythonize') or exe in ('compile_extensions.sh',): return one('build')
    if exe in ('pip', 'pip3', 'uv', 'conda', 'mamba', 'poetry', 'apt', 'apt-get', 'yum', 'dnf', 'source'): return one('environment')
    if exe in ('find', 'locate', 'tree', 'ls') or exe in ('rg', 'ripgrep') and '--files' in args:
        return result(['file_locate', 'unknown'], 'find_exec_not_interpreted', [exe]) if any(x in args for x in ('-exec', '-execdir', '-delete')) else one('file_locate')
    if exe in ('grep', 'egrep', 'fgrep', 'rg', 'ripgrep', 'ag', 'ack'): return one('content_search')
    if exe in ('cat', 'head', 'tail', 'less', 'more', 'nl', 'stat', 'file', 'wc'): return one('file_view')
    if exe in ('sed', 'perl'):
        return one('edit_write' if any(x == '--in-place' or x.startswith('-i') for x in args) else 'file_view')
    if exe in ('cp', 'mv', 'rm', 'mkdir', 'rmdir', 'touch', 'chmod', 'chown', 'ln', 'install'): return one('file_manage')
    if exe in ('apply_patch', 'patch', 'tee'): return one('edit_write')
    if exe == 'git': return one('content_search' if args[:1] == ['grep'] else 'vcs')
    if exe in ('diff',): return one('vcs')
    if exe in ('node', 'ruby', 'bash', 'sh', 'zsh', 'java', 'julia'): return one('script_execute')
    if exe in ('echo', 'printf', 'true', 'false', 'sleep', 'uname', 'date', 'which', 'whoami', 'export', 'unset'): return one('other')
    return result([], 'unrecognized_executable', [exe] if re.fullmatch(r'[A-Za-z0-9_.+-]+', exe) else [])


def classify_command(command, depth=0):
    if isinstance(command, list) and all(isinstance(x, str) for x in command):
        return argv_operation(command, depth)
    if not isinstance(command, str): return result([], 'missing_or_unsupported_command')
    stripped, redirects, reason = strip_redirections(command)
    if stripped is None:
        return classify_heredoc(command, depth) if reason == 'heredoc_not_interpreted' else result([], reason)
    segments, reason = shell_segments(stripped)
    if segments is None: return result([], reason)
    parts = []; heads = []; reasons = []
    for argv in segments:
        r = argv_operation(argv, depth)
        parts.extend(r['components']); heads.extend(r['executables'])
        if r['reason']: reasons.append(r['reason'])
    if redirects:
        reasons.append('redirection_separate_from_command_purpose')
        # A single literal output-writing command is distinguishable from log capture.
        if len(segments) == 1 and heads and heads[0] in {'echo', 'printf', 'cat'} and any(
                op in ('>', '>>') and target != '/dev/null' for op, target in redirects):
            parts = ['edit_write']
    return result(parts, '|'.join(sorted(set(reasons))) or None, heads)


def classify_heredoc(source, depth=0):
    """One literal, closed heredoc with a known consumer, not a shell evaluator."""
    header, newline, rest = source.partition('\n')
    if not newline: return result([], 'unclosed_heredoc')
    quote = None; i = 0; found = None
    while i < len(header):
        c = header[i]
        if quote:
            if c == '\\' and quote == '"': i += 1
            elif c == quote: quote = None
        elif c in "'\"": quote = c
        elif c == '\\': i += 1
        elif header.startswith('<<', i): found = i; break
        i += 1
    if found is None: return result([], 'unsupported_heredoc_header')
    match = re.match(r'<<(-?)[ \t]*(?:\'([A-Za-z_][A-Za-z0-9_]*)\'|"([A-Za-z_][A-Za-z0-9_]*)"|([A-Za-z_][A-Za-z0-9_]*))', header[found:])
    if match is None: return result([], 'dynamic_heredoc_marker')
    marker = next(x for x in match.groups()[1:] if x is not None)
    body_lines = rest.split('\n'); end = next((j for j,x in enumerate(body_lines) if (x.lstrip('\t') if match.group(1) else x) == marker), None)
    if end is None: return result([], 'unclosed_heredoc')
    prefix = header[:found] + ' ' + header[found+match.end():]
    clean, redirects, reason = strip_redirections(prefix)
    if clean is None: return result([], 'multiple_or_unsupported_heredoc')
    segments, reason = shell_segments(clean)
    if not segments: return result([], reason or 'missing_heredoc_consumer')
    argv = segments[-1]
    while argv and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', argv[0], re.S): argv = argv[1:]
    if not argv: return result([], 'missing_heredoc_consumer')
    exe = PurePosixPath(argv[0]).name
    # Only cd/path prefixes are supported; a pipe into the consumer is not simulated.
    if any(PurePosixPath(a[0]).name not in ('cd', 'pwd') for a in segments[:-1]): return result([], 'complex_heredoc_prefix')
    parts = ['navigate'] * len(segments[:-1]); heads = [a[0] for a in segments[:-1]] + [exe]
    body = '\n'.join(body_lines[:end]); purpose_reason = None
    if exe in ('python', 'python3', 'python3.11', 'python3.12') and all(a in ('-', '-u', '-B') for a in argv[1:]):
        use, purpose_reason = python_parts(body); parts.extend(use)
    elif exe in ('edit', 'replace', 'create', 'apply_patch', 'patch'): parts.append('edit_write')
    elif exe == 'cat' and any(op in ('>', '>>') and target != '/dev/null' for op,target in redirects): parts.append('edit_write')
    elif exe in ('bash', 'sh'): parts.append('script_execute'); purpose_reason = 'heredoc_script_purpose_unresolved'
    else: return result([], 'unsupported_heredoc_consumer', heads)
    tail = '\n'.join(body_lines[end+1:]).strip()
    if tail:
        if depth > 4: return result([], 'deep_heredoc_tail')
        r = classify_command(tail, depth+1); parts.extend(r['components']); heads.extend(r['executables'])
    if match.group(4) is not None and ('$' in body or '`' in body):
        parts.append('unknown'); purpose_reason = 'unquoted_heredoc_expansion_not_interpreted'
    return result(parts, purpose_reason or 'literal_heredoc_syntax', heads, 'heredoc_source')


NATIVE = {
    'read': 'file_view', 'open': 'file_view', 'readfile': 'file_view',
    'glob': 'file_locate', 'find': 'file_locate', 'list': 'file_locate', 'ls': 'file_locate',
    'find_file': 'file_locate', 'grep': 'content_search', 'search': 'content_search',
    'search_file': 'content_search', 'search_dir': 'content_search', 'find_symbols': 'content_search',
    'edit': 'edit_write', 'write': 'edit_write', 'multiedit': 'edit_write',
    'notebookedit': 'edit_write', 'replace': 'edit_write', 'insert': 'edit_write',
    'delete': 'edit_write', 'create': 'edit_write', 'apply_patch': 'edit_write',
    'submit': 'submit', 'goto': 'file_view', 'scroll_down': 'file_view', 'scroll_up': 'file_view',
    'findfile': 'file_locate', 'searchfile': 'content_search', 'searchdirectory': 'content_search',
    'finish': 'submit',
}
SHELL = {'bash', 'bash_terminal', 'shell', 'terminal', 'execute', 'run_command',
         'execute_bash', 'sendshellinput'}


def classify_call(tool, arguments):
    name = str(tool or 'missing'); lower = name.lower()
    if lower in NATIVE: return result([NATIVE[lower]], origin='native_tool')
    if lower in ('str_replace_editor', 'str_replace_based_edit_tool', 'stringreplaceeditor'):
        cmd = arguments.get('command') if isinstance(arguments, dict) else None
        label = {'view': 'file_view', 'str_replace': 'edit_write', 'create': 'edit_write',
                 'insert': 'edit_write', 'undo_edit': 'edit_write'}.get(cmd, 'unknown')
        return result([label], None if label != 'unknown' else 'unknown_editor_operation', origin='native_editor')
    if lower in SHELL:
        if lower == 'sendshellinput' and isinstance(arguments, dict):
            if arguments.get('isControlCharacter') is True: return result(['other'], 'terminal_control_character', origin='native_tool')
            command = arguments.get('input')
        else: command = arguments.get('command', arguments.get('cmd')) if isinstance(arguments, dict) else arguments
        return classify_command(command)
    return result([], 'unrecognized_native_tool', origin='native_tool')


def shares(counts):
    counts = Counter(counts); denominator = sum(counts.values())
    return {'denominator': denominator,
            'counts': dict(sorted(counts.items())),
            'percent_all': {k: 100 * v / denominator if denominator else None for k, v in sorted(counts.items())}}
