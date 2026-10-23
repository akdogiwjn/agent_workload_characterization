"""Backed-up, optimistic, cooperative project-state updates; no execution gate."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from scripts.check_project_state import START, END, PAGES, render

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact_json(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()


def merge_dict(current, patch):
    """Add/update named values; never replace a dictionary with a scalar."""
    if not isinstance(patch, dict):
        raise ValueError('patch must be a JSON object')
    result = dict(current)
    for key, value in patch.items():
        if isinstance(result.get(key), dict):
            if not isinstance(value, dict):
                raise ValueError('cannot replace an existing dictionary: '+key)
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result


@contextmanager
def lock(root):
    directory = root/'local_archive/project-state-snapshots'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'.update.lock').open('a') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield directory
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def safe_path(root, name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('expected a repository-relative evidence path')
    if not (root/p).resolve().is_relative_to(root.resolve()):
        raise ValueError('evidence path escapes repository')
    return p


def save_snapshot(root, directory, files):
    state = files['project_state.json']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    destination = directory/(stamp+'-'+digest(state)[:12]+'-'+uuid.uuid4().hex[:6])
    destination.mkdir()
    records = []
    for name, data in files.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({'path':name,'bytes':len(data),'sha256':digest(data)})
    (destination/'manifest.json').write_bytes(exact_json({'schema':'project-state-local-snapshot-v1',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'files':records,
        'does_not_authorize_execution':True}))
    return destination


def snapshot(root=ROOT):
    root = Path(root)
    with lock(root) as directory:
        files = {name:(root/name).read_bytes() for name in ['project_state.json',*PAGES]}
        saved = save_snapshot(root,directory,files)
        return {'status':'SNAPSHOT_SAVED','state_sha256':digest(files['project_state.json']),
                'snapshot':str(saved),'execution_authorized':False}


def replace_bytes(path, data):
    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp',delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(temporary,mode)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(root, patch, expected_sha256, append_summary=(), refresh_evidence=()):
    root = Path(root)
    if any(k in patch for k in ['execution_authorization','evidence','public_summary']):
        raise ValueError('patch may not replace authorization, evidence, or public_summary; use named options')
    with lock(root) as directory:
        before = {name:(root/name).read_bytes() for name in ['project_state.json',*PAGES]}
        if digest(before['project_state.json']) != expected_sha256:
            raise ValueError('stale project_state.json base; re-read and merge, no files overwritten')
        current = json.loads(before['project_state.json'])
        if current.get('execution_authorization') != 'none_this_state_is_not_an_approval':
            raise ValueError('state must not authorize execution')
        candidate = merge_dict(current,patch)
        for text in append_summary:
            if not isinstance(text,str) or '\n' in text or not text.strip():
                raise ValueError('summary addition must be one nonempty line')
            if text not in candidate['public_summary']:
                candidate['public_summary'].append(text)
        outputs = {}
        for page in PAGES:
            text = before[page].decode()
            if text.count(START)!=1 or text.count(END)!=1:
                raise ValueError('missing/duplicate status block: '+page)
            a,b=text.index(START),text.index(END)+len(END)
            outputs[page]=(text[:a]+render(candidate,page)+text[b:]).encode()
        rows={r['path']:dict(r) for r in candidate['evidence']}
        for name in [*PAGES,*refresh_evidence]:
            p=safe_path(root,name);name=str(p)
            if name=='project_state.json':
                raise ValueError('state cannot hash itself as evidence')
            data=outputs[name] if name in outputs else (root/p).read_bytes()
            row=dict(rows.get(name,{'path':name,'role':'explicit current-state evidence update'}))
            row.update(bytes=len(data),sha256=digest(data));rows[name]=row
        candidate['evidence']=list(rows.values())
        for row in candidate['evidence']:
            p=safe_path(root,row['path']);data=outputs.get(str(p))
            if data is None:data=(root/p).read_bytes()
            if digest(data)!=row['sha256']:
                raise ValueError('evidence mismatch; do not blindly refresh historical hashes: '+str(p))
        outputs['project_state.json']=exact_json(candidate)
        saved=save_snapshot(root,directory,before)
        for name,data in before.items():
            if (root/name).read_bytes()!=data:
                raise ValueError('concurrent writer detected; snapshot retained at '+str(saved))
        for name in [*PAGES,'project_state.json']:
            # Refuse a write observed since the transaction's initial read.
            if (root/name).read_bytes()!=before[name]:
                raise ValueError('concurrent writer detected during write; recovery snapshot: '+str(saved))
            replace_bytes(root/name,outputs[name])
        return {'status':'UPDATED','snapshot':str(saved),
                'previous_sha256':expected_sha256,'state_sha256':digest(outputs['project_state.json']),
                'evidence_checked':len(candidate['evidence']),'execution_authorized':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('snapshot')
    update=sub.add_parser('apply')
    update.add_argument('--patch',type=Path,required=True)
    update.add_argument('--expected-sha256',required=True)
    update.add_argument('--append-summary',action='append',default=[])
    update.add_argument('--refresh-evidence',action='append',default=[])
    args=parser.parse_args()
    if args.command=='snapshot':result=snapshot(args.root)
    else:
        patch=json.loads(args.patch.read_text())
        if not isinstance(patch,dict):raise ValueError('patch must be an object')
        result=apply(args.root,patch,args.expected_sha256,args.append_summary,args.refresh_evidence)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
