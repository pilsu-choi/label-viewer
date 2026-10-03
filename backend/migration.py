"""Import legacy metadata without overwriting PostgreSQL edits; export for rollback."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import unquote
from . import db as DB
from .golden_history import golden_revision


def configure_from_file(data_dir: Path) -> None:
    config = Path(data_dir) / '_database.json'
    if config.exists():
        value = json.loads(config.read_text(encoding='utf-8'))
        os.environ.setdefault('LABEL_VIEWER_DATABASE_URL', value['url'])
        if value.get('namespace'):
            os.environ.setdefault('LABEL_VIEWER_DB_NAMESPACE', value['namespace'])



def save_configuration(data_dir: Path) -> None:
    path = Path(data_dir) / '_database.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='._database-', dir=path.parent)
    tmp = Path(temporary)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'url': os.environ['LABEL_VIEWER_DATABASE_URL'],
                       'namespace': DB.namespace(data_dir)}, stream)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)



def import_files(data_dir: Path, dry_run: bool = False) -> dict:
    data_dir = Path(data_dir)
    counts = dict(bundles=0, history=0, jobs=0)
    bundles = sorted(p for p in (data_dir / 'bundles').glob('*') if p.is_dir() and not p.name.startswith('.'))
    if dry_run:
        for bdir in bundles:
            counts['bundles'] += 1
            counts['history'] += len(list((bdir / '.history/golden').glob('*/*.meta.json')))
        counts['jobs'] = len(list((data_dir / '.cache/export-jobs').glob('*/*/job.json')))
        return counts
    if not DB.enabled():
        raise RuntimeError('PostgreSQL configuration is required')
    DB.initialize()
    from psycopg.types.json import Jsonb
    ns = DB.namespace(data_dir)
    with DB.lock(data_dir, 'metadata-migration'), DB.connection() as conn:
        for bdir in bundles:
            exists = conn.execute('SELECT 1 FROM bundles WHERE namespace=%s AND bundle_id=%s',
                                  (ns, bdir.name)).fetchone()
            if not exists:
                state_path = bdir / '_state.json'
                state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'name': bdir.name, 'created_at': '', 'review': {}}
                DB.write_bundle_state(bdir, state)
                counts['bundles'] += 1
            for meta_path in sorted((bdir / '.history/golden').glob('*/*.meta.json')):
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
                history_id = meta_path.name.removesuffix('.meta.json')
                if meta['id'] != history_id:
                    raise ValueError('Golden history ID mismatch')
                raw = meta_path.with_name(history_id + '.json').read_bytes() if meta['has_golden'] else None
                if golden_revision(raw) != meta['revision']:
                    raise ValueError('Golden history checksum mismatch')
                cur = conn.execute('''INSERT INTO golden_history(namespace,bundle_id,doc_id,id,created_at,action,revision,raw)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                    (ns, bdir.name, unquote(meta_path.parent.name), history_id, meta['created_at'], meta['action'], meta['revision'], raw))
                counts['history'] += cur.rowcount
        for path in sorted((data_dir / '.cache/export-jobs').glob('*/*/job.json')):
            bid, jid = path.parent.parent.name, path.parent.name
            if not conn.execute('SELECT 1 FROM bundles WHERE namespace=%s AND bundle_id=%s', (ns, bid)).fetchone():
                continue
            state = json.loads(path.read_text(encoding='utf-8'))
            if state.get('state') in ('queued', 'running'):
                state.update(state='failed', phase='failed', message='DB 전환 중 종료된 작업입니다. 다시 시도해 주세요.')
            cur = conn.execute('INSERT INTO export_jobs(namespace,bundle_id,id,state) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                               (ns, bid, jid, Jsonb(state)))
            counts['jobs'] += cur.rowcount
    return counts


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def export_files(data_dir: Path) -> dict:
    """Run with application stopped. Keeps DB/config intact until caller switches modes."""
    from .golden_history import history_dir
    if not DB.enabled():
        raise RuntimeError('PostgreSQL configuration is required')
    counts = dict(bundles=0, history=0, jobs=0)
    ns = DB.namespace(data_dir)
    with DB.lock(data_dir, 'metadata-migration'), DB.connection() as conn:
        bids = conn.execute('SELECT bundle_id FROM bundles WHERE namespace=%s', (ns,)).fetchall()
        for (bid,) in bids:
            bdir = data_dir / 'bundles' / bid
            if not bdir.is_dir():
                raise RuntimeError('Bundle files are missing; rollback aborted')
            _write_json(bdir / '_state.json', DB.read_bundle_state(bdir))
            counts['bundles'] += 1
        for bid, doc_id, hid, created, action, revision, raw in conn.execute(
            'SELECT bundle_id,doc_id,id,created_at,action,revision,raw FROM golden_history WHERE namespace=%s', (ns,)):
            directory = history_dir(data_dir / 'bundles' / bid, doc_id)
            directory.mkdir(parents=True, exist_ok=True)
            if raw is not None:
                tmp = directory / (hid + '.tmp')
                tmp.write_bytes(raw)
                tmp.replace(directory / (hid + '.json'))
            _write_json(directory / (hid + '.meta.json'), dict(id=hid, created_at=created, action=action, revision=revision, has_golden=raw is not None))
            counts['history'] += 1
        for bid, jid, state in conn.execute('SELECT bundle_id,id,state FROM export_jobs WHERE namespace=%s', (ns,)):
            if state.get('state') in ('queued', 'running'):
                state.update(state='failed', phase='failed', message='저장 방식 전환 중 종료된 작업입니다.')
            _write_json(data_dir / '.cache/export-jobs' / bid / jid / 'job.json', state)
            counts['jobs'] += 1
    return counts
