"""Read-only project status/evidence checks; never an execution gate."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- PROJECT_STATE:START -->'
END = '<!-- PROJECT_STATE:END -->'
PAGES = ('README.md', 'methodology.md', 'docs/README.md',
         'docs/project_status.md', 'docs/development_tasks.md',
         'docs/g1_consolidated_review.md')


def render(state, page):
    prefix = '../' if page.startswith('docs/') else ''
    rows = [START, '当前状态由 [' + state['updated_at'] + ' 状态真源]('
            + prefix + 'project_state.json)统一登记；这是进度记录，不是执行授权。', '']
    rows += ['- ' + line for line in state['public_summary']]
    return '\n'.join(rows + [END])


def check(root=ROOT):
    state = json.loads((root / 'project_state.json').read_text())
    errors = []
    if state.get('execution_authorization') != 'none_this_state_is_not_an_approval':
        errors.append('state must not authorize execution')
    for page in PAGES:
        text = (root / page).read_text()
        if text.count(START) != 1 or text.count(END) != 1:
            errors.append(page + ': missing/duplicate status block')
        elif render(state, page) != text[text.index(START):text.index(END)+len(END)]:
            errors.append(page + ': status drift')
    for item in state['evidence']:
        path = Path(item['path'])
        if path.is_absolute() or '..' in path.parts:
            errors.append('invalid evidence path')
            continue
        path = root / path
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append(item['path'] + ': evidence mismatch')
    return errors


if __name__ == '__main__':
    failures = check()
    print(json.dumps({'status': 'FAIL' if failures else 'PASS', 'errors': failures}, ensure_ascii=False))
    sys.exit(bool(failures))
