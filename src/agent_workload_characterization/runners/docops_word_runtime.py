"""Project-owned, narrow DOCX formatting tools for the DocOps Word pilot.

This module is uploaded into the task container and extends the read/write
tools from the unchanged DocOps runtime. Formatting values are direct OOXML
properties only; Word style inheritance and rendered appearance are not
resolved here.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.sax.saxutils import quoteattr

ROOT_DIR = Path('/root')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
ET.register_namespace('w', W)
ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')


def _tag(name: str) -> str:
    return f'{{{W}}}{name}'


def _serialize_preserving_root_namespaces(xml_bytes: bytes, root: ET.Element) -> bytes:
    namespaces = []
    for _, declaration in ET.iterparse(io.BytesIO(xml_bytes), events=('start-ns',)):
        if declaration not in namespaces:
            namespaces.append(declaration)
        prefix, uri = declaration
        ET.register_namespace(prefix, uri)
    serialized = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    root_start = serialized.find(b'<', serialized.find(b'?>') + 2)
    opening_end = serialized.find(b'>', root_start)
    if root_start < 0 or opening_end < 0:
        raise ValueError('serialized document has no root element')
    opening = serialized[root_start:opening_end]
    for prefix, uri in namespaces:
        name = b'xmlns' if not prefix else b'xmlns:' + prefix.encode('utf-8')
        if re.search(rb'(?:^|\s)' + re.escape(name) + rb'=', opening) is None:
            opening += b' ' + name + b'=' + quoteattr(uri).encode('utf-8')
    return serialized[:root_start] + opening + serialized[opening_end:]


def _root_path(raw: str) -> Path:
    posix = PurePosixPath(raw)
    if (not posix.is_absolute() or len(posix.parts) < 2
            or posix.parts[1] != 'root' or '..' in posix.parts):
        raise ValueError('document path must be under /root and contain no traversal')
    path = ROOT_DIR.joinpath(*posix.parts[2:])
    if not path.resolve().is_relative_to(ROOT_DIR.resolve()):
        raise ValueError('document path escapes the container root')
    return path


def _metadata() -> dict[str, Any]:
    path = ROOT_DIR / 'task_metadata.json'
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('task metadata must be a JSON object')
    return value


def _paragraphs(root: ET.Element) -> list[ET.Element]:
    body = root.find('w:body', NS)
    if body is None:
        raise ValueError('DOCX document body is missing')
    # Match python-docx Document.paragraphs: only direct body paragraphs.
    return list(body.findall('w:p', NS))


def _paragraph_text(paragraph: ET.Element) -> str:
    parts = []
    for node in paragraph.iter():
        if node.tag == _tag('t'):
            parts.append(node.text or '')
        elif node.tag == _tag('tab'):
            parts.append('\t')
        elif node.tag in (_tag('br'), _tag('cr')):
            parts.append('\n')
    return ''.join(parts)


def _direct(value: Any) -> dict[str, Any]:
    return {'status': 'directly_set', 'value': value} if value is not None else {
        'status': 'not_directly_set', 'value': None}


def _style_names(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        styles = ET.fromstring(zf.read('word/styles.xml'))
    except KeyError:
        return {}
    result = {}
    for style in styles.findall('w:style', NS):
        sid = style.get(_tag('styleId'))
        name = style.find('w:name', NS)
        if sid:
            result[sid] = name.get(_tag('val')) if name is not None else sid
    return result


def _paragraph_style(paragraph: ET.Element, styles: dict[str, str]) -> dict[str, Any]:
    ppr = paragraph.find('w:pPr', NS)
    style = ppr.find('w:pStyle', NS) if ppr is not None else None
    style_id = style.get(_tag('val')) if style is not None else None
    if style_id is None:
        return {'status': 'not_directly_set', 'style_id': None, 'name': None}
    return {'status': 'directly_set', 'style_id': style_id,
            'name': styles.get(style_id)}


def _paragraph_format(paragraph: ET.Element) -> dict[str, Any]:
    ppr = paragraph.find('w:pPr', NS)
    if ppr is None:
        ppr = ET.Element(_tag('pPr'))
    alignment = ppr.find('w:jc', NS)
    ind = ppr.find('w:ind', NS)
    spacing = ppr.find('w:spacing', NS)
    def attr(node, key):
        return node.get(_tag(key)) if node is not None else None
    return {
        'alignment': _direct(attr(alignment, 'val')),
        'indent_twips': {
            'left': _direct(attr(ind, 'left')),
            'right': _direct(attr(ind, 'right')),
            'first_line': _direct(attr(ind, 'firstLine')),
            'hanging': _direct(attr(ind, 'hanging')),
        },
        'spacing_raw': {
            'before': _direct(attr(spacing, 'before')),
            'after': _direct(attr(spacing, 'after')),
            'line': _direct(attr(spacing, 'line')),
            'line_rule': _direct(attr(spacing, 'lineRule')),
        },
    }


def _run_font(run: ET.Element) -> dict[str, Any]:
    rpr = run.find('w:rPr', NS)
    fonts = rpr.find('w:rFonts', NS) if rpr is not None else None
    size = rpr.find('w:sz', NS) if rpr is not None else None
    color = rpr.find('w:color', NS) if rpr is not None else None
    bold = rpr.find('w:b', NS) if rpr is not None else None
    font_names = {}
    for key in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
        font_names[key] = _direct(fonts.get(_tag(key)) if fonts is not None else None)
    size_raw = size.get(_tag('val')) if size is not None else None
    size_pt = None
    if size_raw is not None:
        try:
            size_pt = int(size_raw) / 2
        except ValueError:
            size_pt = {'invalid_raw': size_raw}
    color_value = None
    if color is not None:
        color_value = {k: color.get(_tag(k)) for k in ('val', 'themeColor', 'themeTint', 'themeShade')
                       if color.get(_tag(k)) is not None}
    bold_value = None
    if bold is not None:
        raw = bold.get(_tag('val'))
        bold_value = raw not in ('0', 'false', 'off')
    return {
        'font_names': font_names,
        'size_pt': _direct(size_pt),
        'color': _direct(color_value),
        'bold': _direct(bold_value),
    }


def tool_word_inspect_format(path: str, paragraph_index: int) -> dict[str, Any]:
    if isinstance(paragraph_index, bool) or not isinstance(paragraph_index, int) or paragraph_index < 0:
        raise ValueError('paragraph_index must be a non-negative integer')
    file_path = _root_path(path)
    with zipfile.ZipFile(file_path) as zf:
        root = ET.fromstring(zf.read('word/document.xml'))
        paragraphs = _paragraphs(root)
        if paragraph_index >= len(paragraphs):
            raise IndexError('paragraph_index is outside the document')
        paragraph = paragraphs[paragraph_index]
        runs = paragraph.findall('.//w:r', NS)
        return {
            'ok': True,
            'paragraph_index': paragraph_index,
            'text': _paragraph_text(paragraph),
            'style': _paragraph_style(paragraph, _style_names(zf)),
            'paragraph_format_direct': _paragraph_format(paragraph),
            'runs': [{'text': _paragraph_text(run), 'font_direct': _run_font(run)}
                     for run in runs],
            'format_semantics': 'direct OOXML properties only; style inheritance and rendered effective formatting are not resolved',
        }


def _require_submission_path(raw: str) -> None:
    output = _metadata().get('output_path')
    if not isinstance(output, str):
        raise ValueError('task metadata output_path is unavailable')
    local_expected = _root_path(output).resolve()
    if (PurePosixPath(raw) != PurePosixPath(output)
            and Path(raw).resolve() != local_expected):
        raise ValueError('format modification is restricted to metadata output_path')


def _get_or_add(parent: ET.Element, name: str, order: list[str]) -> ET.Element:
    node = parent.find(f'w:{name}', NS)
    if node is not None:
        return node
    node = ET.Element(_tag(name))
    rank = order.index(name)
    insert_at = len(parent)
    for i, child in enumerate(list(parent)):
        local = child.tag.rsplit('}', 1)[-1]
        if local in order and order.index(local) > rank:
            insert_at = i
            break
    parent.insert(insert_at, node)
    return node


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f'{name} must be >= {minimum}')
    return number


def _set_run_format(run: ET.Element, arguments: dict[str, Any]) -> None:
    order = ['rFonts', 'b', 'bCs', 'i', 'iCs', 'caps', 'smallCaps', 'strike',
             'dstrike', 'outline', 'shadow', 'emboss', 'imprint', 'noProof',
             'snapToGrid', 'vanish', 'webHidden', 'color', 'spacing', 'w', 'kern',
             'position', 'sz', 'szCs']
    rpr = run.find('w:rPr', NS)
    if rpr is None:
        rpr = ET.Element(_tag('rPr'))
        run.insert(0, rpr)
    if 'font_name' in arguments:
        name = arguments['font_name']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('font_name must be a non-empty string')
        fonts = _get_or_add(rpr, 'rFonts', order)
        for key in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
            fonts.set(_tag(key), name)
    if 'font_size_pt' in arguments:
        pt = _number(arguments['font_size_pt'], 'font_size_pt', minimum=0.5)
        half_points = round(pt * 2)
        if abs(half_points / 2 - pt) > 1e-9:
            raise ValueError('font_size_pt must use half-point increments')
        _get_or_add(rpr, 'sz', order).set(_tag('val'), str(half_points))
    if 'color' in arguments:
        color = arguments['color']
        if not isinstance(color, str) or re.fullmatch(r'#?[0-9A-Fa-f]{6}', color) is None:
            raise ValueError('color must be a six-digit RGB value')
        node = _get_or_add(rpr, 'color', order)
        for key in ('themeColor', 'themeTint', 'themeShade', 'auto'):
            node.attrib.pop(_tag(key), None)
        node.set(_tag('val'), color.lstrip('#').upper())
    if 'bold' in arguments:
        if not isinstance(arguments['bold'], bool):
            raise ValueError('bold must be boolean')
        _get_or_add(rpr, 'b', order).set(_tag('val'), '1' if arguments['bold'] else '0')


def _set_paragraph_format(paragraph: ET.Element, arguments: dict[str, Any]) -> None:
    ppr_order = ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr',
                 'widowControl', 'numPr', 'suppressLineNumbers', 'pBdr', 'shd',
                 'tabs', 'suppressAutoHyphens', 'kinsoku', 'wordWrap', 'overflowPunct',
                 'topLinePunct', 'autoSpaceDE', 'autoSpaceDN', 'bidi', 'adjustRightInd',
                 'snapToGrid', 'spacing', 'ind', 'contextualSpacing', 'mirrorIndents',
                 'suppressOverlap', 'jc']
    ppr = paragraph.find('w:pPr', NS)
    if ppr is None:
        ppr = ET.Element(_tag('pPr'))
        paragraph.insert(0, ppr)
    if 'style_name' in arguments:
        style_name = arguments['style_name']
        if not isinstance(style_name, str) or not style_name:
            raise ValueError('style_name must be a non-empty string')
        style_id = arguments['_style_name_to_id'].get(style_name.casefold())
        if style_id is None:
            raise ValueError('style_name does not identify an existing paragraph style')
        _get_or_add(ppr, 'pStyle', ppr_order).set(_tag('val'), style_id)
    alignments = {'left', 'center', 'right', 'both', 'justify', 'distribute'}
    if 'alignment' in arguments:
        value = arguments['alignment']
        if value not in alignments:
            raise ValueError('alignment must be left, center, right, justify, or distribute')
        _get_or_add(ppr, 'jc', ppr_order).set(_tag('val'), 'both' if value == 'justify' else value)
    ind_fields = {'left_indent_pt': 'left', 'right_indent_pt': 'right',
                  'first_line_indent_pt': 'firstLine'}
    if any(k in arguments for k in ind_fields):
        ind = _get_or_add(ppr, 'ind', ppr_order)
        for key, attr in ind_fields.items():
            if key in arguments:
                value = _number(arguments[key], key)
                ind.set(_tag(attr), str(round(value * 20)))
    spacing_fields = {'space_before_pt': 'before', 'space_after_pt': 'after'}
    if any(k in arguments for k in spacing_fields) or 'line_spacing' in arguments:
        spacing = _get_or_add(ppr, 'spacing', ppr_order)
        for key, attr in spacing_fields.items():
            if key in arguments:
                value = _number(arguments[key], key, minimum=0)
                spacing.set(_tag(attr), str(round(value * 20)))
        if 'line_spacing' in arguments:
            value = _number(arguments['line_spacing'], 'line_spacing', minimum=0.1)
            spacing.set(_tag('line'), str(round(value * 240)))
            spacing.set(_tag('lineRule'), 'auto')


def tool_word_set_format(path: str, paragraph_index: int, **arguments) -> dict[str, Any]:
    if isinstance(paragraph_index, bool) or not isinstance(paragraph_index, int) or paragraph_index < 0:
        raise ValueError('paragraph_index must be a non-negative integer')
    _require_submission_path(path)
    file_path = _root_path(path)
    if not file_path.is_file() or file_path.is_symlink():
        raise ValueError('submission path must be an existing regular DOCX file')
    allowed = {'style_name', 'font_name', 'font_size_pt', 'color', 'bold',
               'alignment', 'left_indent_pt', 'right_indent_pt', 'first_line_indent_pt',
               'space_before_pt', 'space_after_pt', 'line_spacing'}
    unexpected = set(arguments) - allowed
    if unexpected:
        raise ValueError('unsupported format fields: ' + ','.join(sorted(unexpected)))
    temp_path = file_path.with_name(file_path.name + '.format-tmp')
    try:
        with zipfile.ZipFile(file_path, 'r') as source:
            files = [(info, source.read(info.filename)) for info in source.infolist()]
            document_xml = source.read('word/document.xml')
            root = ET.fromstring(document_xml)
            styles_xml = ET.fromstring(source.read('word/styles.xml'))
        paragraphs = _paragraphs(root)
        if paragraph_index >= len(paragraphs):
            raise IndexError('paragraph_index is outside the document')
        names = {}
        for style in styles_xml.findall('w:style', NS):
            sid = style.get(_tag('styleId'))
            name_node = style.find('w:name', NS)
            if sid and name_node is not None:
                names[(name_node.get(_tag('val')) or '').casefold()] = sid
        args = dict(arguments, _style_name_to_id=names)
        paragraph = paragraphs[paragraph_index]
        before = _paragraph_text(paragraph)
        _set_paragraph_format(paragraph, args)
        if any(k in arguments for k in ('font_name', 'font_size_pt', 'color', 'bold')):
            for run in paragraph.findall('.//w:r', NS):
                _set_run_format(run, arguments)
        if _paragraph_text(paragraph) != before:
            raise AssertionError('format modification changed paragraph text')
        replacement = _serialize_preserving_root_namespaces(document_xml, root)
        with zipfile.ZipFile(temp_path, 'w') as target:
            for info, data in files:
                target.writestr(info, replacement if info.filename == 'word/document.xml' else data)
        temp_path.replace(file_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return {'ok': True, 'path': path, 'paragraph_index': paragraph_index,
            'text_preserved': True, 'format_fields_set': sorted(arguments)}


def dispatch(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError('tool arguments must be an object')
    if tool_name == 'get_task_metadata':
        return {'ok': True, 'metadata': _metadata()}
    if tool_name in {'word_inspect_format', 'word_set_format'}:
        kwargs = dict(arguments)
    else:
        # Keep the official tool implementation as the production path for its
        # existing tools. Import it only in the task container, where its
        # frozen document-tool dependencies are present.
        import document_tools_runtime as official_runtime
        official_runtime.TOOLS['get_task_metadata'] = lambda: {
            'ok': True, 'metadata': _metadata()}
        kwargs = official_runtime._normalize_args(tool_name, arguments)
    if tool_name == 'word_set_format':
        _require_submission_path(kwargs.get('path', ''))
    if tool_name in {'word_inspect_format', 'word_set_format'}:
        fn = {'word_inspect_format': tool_word_inspect_format,
              'word_set_format': tool_word_set_format}[tool_name]
    else:
        for key in ('path', 'src', 'dest'):
            value = kwargs.get(key)
            if isinstance(value, str) and value.startswith('/root/'):
                kwargs[key] = str(_root_path(value))
        fn = official_runtime.TOOLS.get(tool_name)
    if fn is None:
        return {'ok': False, 'error': f'unknown tool: {tool_name}'}
    return fn(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', required=True)
    parser.add_argument('--args-json', default='{}')
    args = parser.parse_args()
    try:
        result = dispatch(args.tool, json.loads(args.args_json))
    except Exception as exc:
        result = {'ok': False, 'error': type(exc).__name__}
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
