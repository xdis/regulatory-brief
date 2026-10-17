"""Regulatory Brief: a small localhost collection, review and newsletter PoC."""
import argparse
import difflib
import hashlib
import html
import json
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from collector import SOURCES, collect
from analysis import analyze, MODEL

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'brief.sqlite3'
GATE = threading.Lock()

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def connect(path=DB):
    con = sqlite3.connect(path, timeout=10); con.row_factory = sqlite3.Row
    return con

def initialize(path=DB):
    with connect(path) as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS snapshots (
          id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, mode TEXT NOT NULL,
          title TEXT NOT NULL, body TEXT NOT NULL, hash TEXT NOT NULL,
          captured TEXT NOT NULL, previous_id INTEGER, change TEXT NOT NULL,
          analysis TEXT, engine TEXT, status TEXT NOT NULL DEFAULT 'pending',
          reviewer TEXT, review_note TEXT, reviewed TEXT);
        CREATE INDEX IF NOT EXISTS latest ON snapshots(source_id,mode,id);
        CREATE TABLE IF NOT EXISTS checks (source_id TEXT PRIMARY KEY, checked TEXT, outcome TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT, action TEXT, snapshot_id INTEGER, detail TEXT);
        ''')

def audit(con, action, sid, detail):
    con.execute('INSERT INTO audit(at,action,snapshot_id,detail) VALUES(?,?,?,?)', (now(), action, sid, detail))

def ingest(con, source, title, body, mode='live'):
    digest = hashlib.sha256(body.encode()).hexdigest()
    old = con.execute('SELECT * FROM snapshots WHERE source_id=? AND mode=? ORDER BY id DESC LIMIT 1', (source['id'], mode)).fetchone()
    if old and old['hash'] == digest: return old['id'], 'unchanged'
    change = 'changed' if old else 'baseline'
    sid = con.execute('INSERT INTO snapshots(source_id,mode,title,body,hash,captured,previous_id,change) VALUES(?,?,?,?,?,?,?,?)',
                      (source['id'], mode, title, body, digest, now(), old['id'] if old else None, change)).lastrowid
    audit(con, 'capture', sid, mode + ': ' + change)
    return sid, change

def seed_demo(con):
    if con.execute("SELECT COUNT(*) FROM snapshots WHERE mode='demo'").fetchone()[0]:
        return {'message': 'Offline examples already loaded. Existing reviews were preserved.'}
    for i, source in enumerate(SOURCES):
        body = ('SIMULATED TRAINING CONTENT. This is not a regulation or an official source capture.\n'
                + source['name'] + '\nThe fictional monitoring team is reviewing supplier documentation and will confirm the scope before proposing any business action.\n'
                + 'No legal deadline is established in this training example.')
        sid, _ = ingest(con, source, 'Training example: ' + source['name'], body, 'demo')
        if i == 0:
            body += '\nSIMULATED REVISION: The review now includes packaging specifications and a request to validate supplier evidence.'
            sid, _ = ingest(con, source, 'Training example: ' + source['name'], body, 'demo')
        brief = {'summary': 'Fictional review of supplier documentation, used to demonstrate a source-to-newsletter workflow.',
                 'impact': 'Illustrative only: a packaging or product team might need to check supplier evidence.',
                 'action': 'Review the example, inspect the captured evidence, and decide whether to approve this training item.',
                 'priority': ['High','Medium','Low'][i], 'reason': 'Preset training priority to demonstrate sorting; not a legal risk assessment.',
                 'deadline': 'Not established', 'deadline_evidence': '',
                 'evidence': 'The fictional monitoring team is reviewing supplier documentation and will confirm the scope before proposing any business action.'}
        con.execute('UPDATE snapshots SET analysis=?,engine=? WHERE id=?', (json.dumps(brief), 'Offline fixture — no AI call', sid))
    return {'message': 'Three clearly labeled training examples loaded, including one simulated revision.'}

def record(con, sid):
    row = con.execute('SELECT * FROM snapshots WHERE id=?', (sid,)).fetchone()
    if not row: raise ValueError('Snapshot not found.')
    item = dict(row); item['analysis'] = json.loads(item['analysis']) if item['analysis'] else None
    item['source'] = next(s for s in SOURCES if s['id'] == item['source_id'])
    return item

def state(con, mode):
    rows = con.execute('SELECT MAX(id) AS id FROM snapshots WHERE mode=? GROUP BY source_id', (mode,)).fetchall()
    items = [record(con, r['id']) for r in rows]
    items.sort(key=lambda x: ({'High':0,'Medium':1,'Low':2}.get((x['analysis'] or {}).get('priority'),3), x['source_id']))
    return {'items': items, 'sources': SOURCES, 'checks': [dict(r) for r in con.execute('SELECT * FROM checks')],
            'history': [dict(r) for r in con.execute('SELECT id,source_id,mode,captured,change,status,hash FROM snapshots WHERE mode=? ORDER BY id DESC', (mode,))],
            'audit': [dict(r) for r in con.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 20')], 'model': MODEL}

def review(con, payload):
    sid = payload.get('id'); item = record(con, sid)
    status = payload.get('status'); reviewer = payload.get('reviewer', '').strip(); note = payload.get('note', '').strip()
    if status not in ('approved', 'rejected'): raise ValueError('Choose approved or rejected.')
    if not reviewer or len(reviewer) > 80 or len(note) > 1000: raise ValueError('Enter a reviewer name (1–80 characters) and a note of at most 1000 characters.')
    latest = con.execute('SELECT MAX(id) FROM snapshots WHERE source_id=? AND mode=?', (item['source_id'], item['mode'])).fetchone()[0]
    if sid != latest: raise ValueError('A newer snapshot exists. Review the latest version.')
    if status == 'approved' and not item['analysis']: raise ValueError('Analyze the snapshot before approval.')
    con.execute('UPDATE snapshots SET status=?,reviewer=?,review_note=?,reviewed=? WHERE id=?', (status, reviewer, note, now(), sid))
    audit(con, status, sid, reviewer + ': ' + note)
    return {'message': 'Review saved. Only approved current versions are included in the newsletter.'}

def newsletter(con, mode):
    items = [x for x in state(con, mode)['items'] if x['status'] == 'approved']
    esc = html.escape
    sections = []
    for item in items:
        a = item['analysis']; source = item['source']
        sections.append(f'''<article><p class="tag">{esc(a['priority'])} editorial priority · {esc(source['owner'])}</p>
        <h2>{esc(item['title'])}</h2><p>{esc(a['summary'])}</p>
        <p><b>Potential impact:</b> {esc(a['impact'])}</p><p><b>Suggested action:</b> {esc(a['action'])}</p>
        <p><b>Date / deadline:</b> {esc(a['deadline'])}</p><p>{esc(a.get('validation_note',''))}</p><blockquote>{esc(a['evidence'])}</blockquote>
        <p><a href="{esc(source['url'])}">Official reference</a> · Snapshot #{item['id']} · Captured {esc(item['captured'])}</p>
        <p>Analysis: {esc(item['engine'])}. Reviewed by {esc(item['reviewer'])} at {esc(item['reviewed'])}.</p>
        <p>Review note: {esc(item['review_note'] or 'None')}</p><p class="hash">SHA-256: {item['hash']}</p></article>''')
    label = 'TRAINING EDITION — SYNTHETIC CONTENT' if mode == 'demo' else 'PUBLIC SOURCE REVIEW'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Regulatory Brief — Newsletter</title>
    <style>body{{font:16px/1.7 system-ui;color:#183a37;background:#f4f3ed;max-width:850px;margin:48px auto;padding:0 24px}}h1{{font:48px Georgia}}article{{background:white;padding:28px;margin:24px 0;border:1px solid #d8dfda;border-radius:12px}}.tag{{color:#986127;font-size:12px;font-weight:bold}}blockquote{{border-left:3px solid #368575;padding-left:16px}}.hash{{overflow-wrap:anywhere;font-size:11px;color:#687772}}a{{color:#196f5e}}@media print{{body{{background:white;margin:0}}article{{break-inside:avoid}}}}</style>
    <p class="tag">REGULATORY BRIEF / {label}</p><h1>The review brief.</h1><p>Packaging & product sustainability · Generated {now()} · {len(items)} approved items</p>
    <p>This is a locally reviewed PoC brief, not legal advice or an authenticated legal sign-off. Sources may be historical; capture date is not publication date. {'Official links are contextual only; training text was not collected from those pages.' if mode == 'demo' else 'Recommendations require subject-matter validation.'}</p>
    {''.join(sections) or '<article>No approved current items. Review an item before exporting a populated brief.</article>'}
    <footer>Prepared with Regulatory Brief · No email was sent.</footer></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, data, status=200, kind='application/json; charset=utf-8'):
        body = json.dumps(data).encode() if kind.startswith('application/json') else data.encode()
        self.send_response(status); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(body)
    def trusted(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
    def do_GET(self):
        if not self.trusted(): return self.send({'error':'Invalid host.'},403)
        url = urlparse(self.path); query = parse_qs(url.query); mode = query.get('mode',['live'])[0]
        if mode not in ('live','demo'): return self.send({'error':'Invalid mode.'},400)
        with connect(self.server.db) as con:
            if url.path == '/': return self.send((ROOT/'index.html').read_text(), kind='text/html; charset=utf-8')
            if url.path == '/api/state': return self.send(state(con, mode))
            if url.path == '/api/health': return self.send({'status':'ok'})
            if url.path == '/newsletter': return self.send(newsletter(con, mode), kind='text/html; charset=utf-8')
            if url.path == '/api/snapshot':
                try:
                    item = record(con, int(query.get('id',['0'])[0]))
                    old = record(con, item['previous_id'])['body'] if item['previous_id'] else ''
                    item['diff'] = '\n'.join(difflib.unified_diff(old.splitlines(), item['body'].splitlines(), fromfile='Previous snapshot', tofile='Current snapshot', lineterm='')) if old else 'First observation. No previous snapshot to compare.'
                    return self.send(item)
                except (ValueError, TypeError): return self.send({'error':'Snapshot not found.'},404)
        self.send({'error':'Not found.'},404)
    def do_POST(self):
        if not self.trusted() or self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host','')):
            return self.send({'error':'Cross-origin requests are not allowed.'},403)
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json': return self.send({'error':'JSON required.'},415)
        if not GATE.acquire(blocking=False): return self.send({'error':'Another operation is running. Please retry shortly.'},409)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 8192: raise ValueError('Invalid request size.')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload,dict): raise ValueError('Expected a JSON object.')
            with connect(self.server.db) as con:
                if self.path == '/api/collect':
                    outcomes = []
                    for source in SOURCES:
                        try:
                            title, body = collect(source); sid, outcome = ingest(con, source, title, body)
                            error = ''; outcomes.append({'source':source['name'],'outcome':outcome,'id':sid})
                        except Exception as exc:
                            outcome = 'failed'; error = str(exc)[:300]; outcomes.append({'source':source['name'],'outcome':outcome,'error':error})
                        con.execute('INSERT OR REPLACE INTO checks VALUES(?,?,?,?)',(source['id'],now(),outcome,error))
                    result = {'message': 'Collection finished. ' + str(sum(x['outcome'] != 'failed' for x in outcomes)) + '/3 sources checked successfully.', 'outcomes':outcomes}
                elif self.path == '/api/demo': result = seed_demo(con)
                elif self.path == '/api/analyze':
                    item = record(con, payload.get('id'))
                    if item['mode'] != 'live': raise ValueError('Offline examples use preset analyses. Choose Live sources for a real AI call.')
                    a = analyze(item['title'],item['body'])
                    con.execute("UPDATE snapshots SET analysis=?,engine=?,status='pending',reviewer=NULL,review_note=NULL,reviewed=NULL WHERE id=?",(json.dumps(a),'Codex · requested model '+MODEL,item['id']))
                    audit(con,'analyze',item['id'],'Exact evidence validated; human review required')
                    result = {'message':'AI draft saved. Verify scope, dates and evidence before approving.'}
                elif self.path == '/api/review': result = review(con,payload)
                else: return self.send({'error':'Not found.'},404)
            self.send(result)
        except (ValueError, TypeError) as exc: self.send({'error':str(exc)},400)
        except Exception: self.send({'error':'Operation failed. Existing snapshots were preserved.'},500)
        finally: GATE.release()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8767); args=parser.parse_args()
    initialize(); server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler); server.db=DB
    print(f'Regulatory Brief running at http://127.0.0.1:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
