import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from app import initialize, connect, ingest, SOURCES, state, seed_demo, review, newsletter, Handler, ThreadingHTTPServer
from collector import Page
from analysis import validate

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'test.db'; initialize(self.path); self.con=connect(self.path)
    def tearDown(self):
        self.con.close(); self.tmp.cleanup()
    def test_baseline_unchanged_changed_and_reversion(self):
        sid,c=ingest(self.con,SOURCES[0],'Example','Original'); self.assertEqual(c,'baseline')
        same,c=ingest(self.con,SOURCES[0],'Example','Original'); self.assertEqual((same,c),(sid,'unchanged'))
        updated,c=ingest(self.con,SOURCES[0],'Example','Revised'); self.assertEqual(c,'changed')
        back,c=ingest(self.con,SOURCES[0],'Example','Original'); self.assertEqual(c,'changed'); self.assertNotEqual(back,sid)
        self.assertEqual(state(self.con,'live')['items'][0]['id'],back)
    def test_mode_separation(self):
        ingest(self.con,SOURCES[0],'Live','Real text');seed_demo(self.con)
        self.assertEqual(len(state(self.con,'live')['items']),1);self.assertEqual(len(state(self.con,'demo')['items']),3)
        self.assertNotIn('TRAINING EDITION',newsletter(self.con,'live'))
    def test_export_approval_gate_and_new_version(self):
        seed_demo(self.con); item=state(self.con,'demo')['items'][0]
        self.assertIn('No approved current items',newsletter(self.con,'demo'))
        review(self.con,{'id':item['id'],'status':'approved','reviewer':'Tester','note':'Training only'})
        self.assertIn(item['title'],newsletter(self.con,'demo'));self.assertIn('TRAINING EDITION',newsletter(self.con,'demo'))
        ingest(self.con,item['source'],'New version','A new body','demo')
        self.assertIn('No approved current items',newsletter(self.con,'demo'))
        with self.assertRaises(ValueError):review(self.con,{'id':item['id'],'status':'approved','reviewer':'Tester'})
    def test_reject_and_name_required(self):
        seed_demo(self.con); item=state(self.con,'demo')['items'][0]
        with self.assertRaises(ValueError):review(self.con,{'id':item['id'],'status':'approved','reviewer':''})
        review(self.con,{'id':item['id'],'status':'rejected','reviewer':'Tester'})
        self.assertIn('No approved current items',newsletter(self.con,'demo'))
    def test_evidence_and_dates(self):
        seed_demo(self.con);item=state(self.con,'demo')['items'][0];a=item['analysis']
        validate(a,item['body'])
        with self.assertRaises(ValueError):validate(dict(a,evidence='Invented quotation'),item['body'])
        checked=validate(dict(a,deadline='Tomorrow'),item['body'])
        self.assertEqual(checked['deadline'],'Not established');self.assertIn('removed',checked['validation_note'])
        validate(dict(a,evidence=a['evidence'].replace(' ', '\n')),item['body'])
    def test_no_analysis_cannot_approve(self):
        sid,_=ingest(self.con,SOURCES[0],'Example','Original')
        with self.assertRaises(ValueError):review(self.con,{'id':sid,'status':'approved','reviewer':'Tester'})
    def test_parser_ignores_page_chrome(self):
        page=Page();page.feed('<html><title>Example</title><nav>Menu</nav><main><h1>Title</h1><p>Body</p><script>Bad</script></main><footer>Footer</footer></html>')
        self.assertEqual(page.main,['Title','Body']);self.assertNotIn('Menu',page.parts)
    def test_html_escaping(self):
        seed_demo(self.con);item=state(self.con,'demo')['items'][0]
        review(self.con,{'id':item['id'],'status':'approved','reviewer':'<script>bad()</script>'})
        self.assertNotIn('<script>',newsletter(self.con,'demo'));self.assertIn('&lt;script&gt;',newsletter(self.con,'demo'))
    def test_http_and_collection_error_retention(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.db=self.path
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        def post(path,payload,origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            with urlopen(Request(base+path,data=json.dumps(payload).encode(),headers=headers)) as r:return json.load(r)
        try:
            with urlopen(base+'/api/health') as r:self.assertEqual(json.load(r)['status'],'ok')
            with patch('app.collect',return_value=('Source title','Captured content')):post('/api/collect',{})
            with patch('app.collect',side_effect=ValueError('Offline')):result=post('/api/collect',{})
            self.assertEqual(sum(x['outcome']=='failed' for x in result['outcomes']),3)
            with urlopen(base+'/api/state') as r:self.assertEqual(len(json.load(r)['items']),3)
            with self.assertRaises(HTTPError) as cm:post('/api/demo',{},'https://foreign.example')
            self.assertEqual(cm.exception.code,403)
            post('/api/demo',{})
            with urlopen(base+'/newsletter?mode=demo') as r:self.assertIn('No approved current items',r.read().decode())
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
