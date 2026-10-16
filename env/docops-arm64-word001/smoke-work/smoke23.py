import json, sys
from pathlib import Path
from docx import Document

# S2a: read the real input docx (read-only mount, copy to writable tmp for safety)
src = Path('/work/input.docx')
d = Document(str(src))
paras = [p.text for p in d.paragraphs if p.text.strip()]
print('S2a read real docx: paragraphs=%d, first=%r' % (len(paras), paras[0][:60] if paras else None))

# S2b: synthetic doc minimal write-reopen
out = Path('/out/synthetic.docx')
nd = Document()
nd.add_paragraph('hello smoke')
nd.save(str(out))
rd = Document(str(out))
assert rd.paragraphs[0].text == 'hello smoke'
print('S2b synthetic write-reopen: OK')

# S3: runtime tool interfaces (document_tools_runtime.py mounted at /work)
sys.path.insert(0, '/work')
import document_tools_runtime as rt
meta = rt.tool_get_task_metadata()
print('S3 get_task_metadata: task_id=%s input=%s output=%s' % (meta.get('task_id'), meta.get('input_path'), meta.get('output_path')))
r1 = rt.tool_copy_file('/out/synthetic.docx', '/out/copied.docx')
print('S3 copy_file:', r1.get('ok', r1))
r2 = rt.tool_inspect_document('/out/copied.docx', max_items=3)
print('S3 inspect_document keys:', sorted(r2.keys())[:6] if isinstance(r2, dict) else str(r2)[:80])
r3 = rt.tool_word_replace_text('/out/copied.docx', [{'old': 'hello smoke', 'new': 'hello replaced'}])
chk = Document('/out/copied.docx')
print('S3 word_replace_text:', r3 if not isinstance(r3, dict) else {k: r3[k] for k in list(r3)[:3]}, '| verify:', chk.paragraphs[0].text)
print('SMOKE23 PASS')
