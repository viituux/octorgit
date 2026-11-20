"""Contracts for the local Stitch adaptation, without pretending to render a browser."""
from html.parser import HTMLParser
from importlib.resources import files
import re
import threading
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError
from octorgit.web import LocalServer


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids=[]; self.attrs=[]; self.stack=[]
    def handle_starttag(self, tag, attrs):
        values=dict(attrs); self.attrs.append((tag,values))
        if 'id' in values:self.ids.append(values['id'])
        if tag not in {'meta','link','input','img','br','hr','source','wbr','area','base','col','embed','param','track'}:self.stack.append(tag)
    def handle_endtag(self,tag):
        if not self.stack or self.stack[-1]!=tag:raise AssertionError('Unbalanced HTML: '+tag+' after '+str(self.stack[-4:]))
        self.stack.pop()


class DesignTests(unittest.TestCase):
    def test_markup_is_balanced_and_all_javascript_ids_exist(self):
        html=files('octorgit').joinpath('static/index.html').read_text(encoding="utf-8")
        js=files('octorgit').joinpath('static/app.js').read_text(encoding="utf-8")
        parsed=Markup();parsed.feed(html)
        self.assertEqual(parsed.stack,[])
        self.assertEqual(len(parsed.ids),len(set(parsed.ids)))
        referenced=set(re.findall(r'\$\("#([A-Za-z][\w-]*)"\)',js))
        self.assertFalse(referenced-set(parsed.ids))
        self.assertIn('architecture-detail',parsed.ids)
        self.assertIn('endpoint-detail',parsed.ids)
        self.assertIn('settings-usage-panel',parsed.ids)

    def test_stitch_is_reference_not_remote_runtime_or_inline_scripts(self):
        html=files('octorgit').joinpath('static/index.html').read_text(encoding="utf-8")
        css=files('octorgit').joinpath('static/style.css').read_text(encoding="utf-8")
        parsed=Markup();parsed.feed(html)
        for tag,attrs in parsed.attrs:
            self.assertFalse(any(key.startswith('on') for key in attrs))
            if tag in {'script','img'}:self.assertFalse(attrs.get('src','').startswith('http'))
        self.assertNotIn('tailwindcss.com',html)
        self.assertNotIn('fonts.googleapis.com',css)
        self.assertNotIn('v1.4.2',html)
        self.assertIn('não baixa um PDF automaticamente',html)
        self.assertIn('Conexão GitHub',html)
        self.assertIn('private-ai-consent',parsed.ids)

    def test_bundled_fonts_served_and_arbitrary_files_rejected(self):
        server=LocalServer(0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_address[1])
        try:
            for name in ('geist-regular.ttf','geist-semibold.ttf','jetbrains-mono.ttf'):
                with urlopen(base+'/fonts/'+name,timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(),'font/ttf')
                    self.assertGreater(len(response.read()),20000)
            with self.assertRaises(HTTPError) as result:urlopen(base+'/fonts/../web.py',timeout=5)
            self.assertEqual(result.exception.code,404)
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
