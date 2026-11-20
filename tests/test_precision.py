"""Regressions from the 2026-11-20 audit, including misleading declarations."""
import unittest
from octorgit.code_parser import analyze
from octorgit.documentation import validate
from octorgit.reports import technology_svg

REPO = {'url': None, 'branch': None, 'commit_sha': None, 'source': 'local_fixture'}


class PrecisionTests(unittest.TestCase):
    def test_auxiliary_routes_do_not_pollute_application_or_root_selection(self):
        files = {
            'settings.py': 'ROOT_URLCONF = "urls"\n',
            'urls.py': 'from django.urls import path\nfrom views import health\nurlpatterns = [path("health/", health)]\n',
            'views.py': 'from django.views.decorators.http import require_GET\n@require_GET\ndef health(request): pass\n',
            'tests/settings.py': 'ROOT_URLCONF = "tests.urls"\n',
            'tests/urls.py': 'from django.urls import path\nfrom views import health\nurlpatterns = [path("fake/", health)]\n',
            'examples/urls.py': 'from django.urls import path\nfrom views import health\nurlpatterns = [path("example/", health)]\n',
        }
        ir = analyze(REPO, files, [])
        self.assertEqual([(e['method'], e['route']) for e in ir['endpoints']], [('GET', 'health/')])
        self.assertIn('tests/urls.py', {f['path'] for f in ir['files']})
        self.assertTrue(any(d['reason'] == 'auxiliary_file_excluded_from_endpoints' for d in ir['diagnostics']))
        validate(ir, files)

    def test_fixture_selected_as_input_root_keeps_routes(self):
        files = {'urls.py': 'from django.urls import path\nfrom views import health\nurlpatterns = [path("health/", health)]',
                 'views.py': 'from django.views.decorators.http import require_GET\n@require_GET\ndef health(request): pass'}
        self.assertEqual(len(analyze(REPO, files, [], 'urls')['endpoints']), 1)

    def test_compose_nested_image_build_and_dependencies_are_not_service_properties(self):
        files = {'Dockerfile': 'FROM python:3.12\n', 'compose.yaml': '''services:
    web:
        image: python:3.12
        environment:
            image: postgres:16
            build: .
            depends_on: [db]
    db:
        image: mysql:8
'''}
        ir = analyze(REPO, files, [])
        tech = ir['technology']
        self.assertIn('web', {c['name'] for c in tech['components']})
        self.assertIn('MySQL · db', {c['name'] for c in tech['components']})
        self.assertNotIn('PostgreSQL', technology_svg(ir))
        self.assertEqual(tech['relations'], [])
        validate(ir, files)

    def test_compose_direct_dependencies_support_nonstandard_indentation(self):
        files = {'compose.yml': '''services:
    web:
        image: python:3.12
        depends_on:
            db:
                condition: service_healthy
    db:
        image: postgres:16
'''}
        ir = analyze(REPO, files, [])
        self.assertEqual(len(ir['technology']['relations']), 1)
        validate(ir, files)

    def test_sqlite_calls_aliases_and_nested_functions_have_evidence(self):
        for code in ['import sqlite3\ndef save(path):\n    return sqlite3.connect(path)\n',
                     'import sqlite3 as db\nconnection = db.connect(":memory:")\n',
                     'from sqlite3 import connect as open_db\nconnection = open_db("app.db")\n',
                     'def save(path):\n    import sqlite3\n    return sqlite3.connect(path)\n']:
            with self.subTest(code=code):
                files = {'app.py': code}
                ir = analyze(REPO, files, [])
                sqlite = next(c for c in ir['technology']['components'] if c['name'] == 'SQLite')
                self.assertEqual(sqlite['scope'], 'sqlite_connection')
                self.assertTrue(any(r['target'] == sqlite['id'] for r in ir['technology']['relations']))
                self.assertIn('connect', code.splitlines()[sqlite['evidence_chain'][0]['start_line']-1] if 'open_db' not in code else code)
                validate(ir, files)

    def test_sqlite_import_only_shadowed_names_and_examples_do_not_confirm_database(self):
        for code in ['import sqlite3\n',
                     'import sqlite3\ndef save(sqlite3):\n    return sqlite3.connect("app.db")\n',
                     'import sqlite3\nsqlite3 = object()\nsqlite3.connect("app.db")\n',
                     'def other():\n    import sqlite3\ndef save():\n    return sqlite3.connect("app.db")\n',
                     'from other import connect\nconnect("app.db")\n']:
            with self.subTest(code=code):
                ir = analyze(REPO, {'app.py': code, 'examples/demo.py': 'import sqlite3\nsqlite3.connect("demo.db")'}, [])
                self.assertFalse(any(c['kind'] == 'database' for c in ir['technology']['components']))
