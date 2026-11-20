import json
import threading
import unittest
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from octorgit.technology_icons import catalog, resolve_icon
from octorgit.code_parser import analyze
from octorgit.reports import technology_svg, report_html
from octorgit.insights import build_insights
from octorgit.web import LocalServer


class IconTests(unittest.TestCase):
    def test_supported_marks_aliases_and_unknown_fallback(self):
        self.assertGreaterEqual(len(catalog()['icons']),40)
        for name in ('Python','JavaScript','TypeScript','Django','React','PostgreSQL · db','PostgreSQL (driver)','Redis (cliente)','Docker Compose','Kubernetes','AWS','Azure'):
            with self.subTest(name=name):self.assertTrue(resolve_icon(name))
        self.assertIsNone(resolve_icon('Banco não confirmado'))
        self.assertIsNone(resolve_icon('<script>unknown</script>'))
        self.assertIsNone(resolve_icon('NotARealTechnology'))
        self.assertEqual(resolve_icon('Docker'),resolve_icon('Docker Compose'))

    def test_report_uses_local_vector_paths_not_external_images(self):
        source={'app.py':'import sqlite3\nsqlite3.connect("app.db")','compose.yml':'services:\n  db:\n    image: postgres:16\n','Dockerfile':'FROM python:3.12'}
        ir=analyze({'url':None,'branch':None,'commit_sha':None,'source':'local_fixture'},source,[])
        image=technology_svg(ir);root=ET.fromstring(image)
        paths={node.get('d') for node in root.iter('{http://www.w3.org/2000/svg}path')}
        self.assertTrue(set(resolve_icon('Python')['paths'])<=paths)
        self.assertTrue(set(resolve_icon('PostgreSQL')['paths'])<=paths)
        self.assertNotIn('<image',image)
        self.assertIn('Hospedagem não confirmada',image)
        html=report_html(ir,build_insights(ir,source))
        self.assertNotIn('cdn.jsdelivr',html)
        self.assertNotIn('<script',html)

    def test_catalog_served_locally_without_runtime_downloads(self):
        server=LocalServer(0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with urlopen('http://127.0.0.1:'+str(server.server_address[1])+'/technology-icons.json',timeout=5) as response:
                self.assertEqual(response.headers.get_content_type(),'application/json')
                data=json.load(response)
            self.assertIn('python',data['icons'])
            self.assertNotIn('https://',json.dumps(data))
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
