from copy import deepcopy
import io
import json
import time
import unittest
from unittest.mock import patch
import zipfile

from helpers_ai import structured_response
from octorgit.ai_engine import CATEGORIES, DocumentationEngine, AIError, build_context, render_markdown, validate_response
from octorgit.code_parser import analyze
from octorgit.insights import build_insights
from octorgit.reports import report_html
from octorgit.web import Jobs


class Provider:
    model='test-summary'
    provider='mock'
    def generate(self,context):
        result=structured_response()
        result['sections'][0]['claims']=[{'text':'O código contém declarações de aplicação e dados.', 'confidence':'inferred','evidence_ids':[context['facts'][0]['id']]}]
        return result,{'totalTokenCount':123}


def ir():
    return analyze({'url':None,'branch':None,'commit_sha':None,'source':'local_fixture'}, {'app.py':'import sqlite3\nconnection=sqlite3.connect("app.db")\n','web.ts':'const app = 1;\n'}, [])


class ProjectSummaryTests(unittest.TestCase):
    def test_all_categories_required_without_padding_or_fabricating_sections(self):
        context=build_context(ir())
        for mutation in ['missing','duplicate','unknown','long','dump','multiline']:
            candidate=structured_response()
            if mutation=='missing':candidate['sections'].pop()
            elif mutation=='duplicate':candidate['sections'][1]['title']=candidate['sections'][0]['title']
            elif mutation=='unknown':candidate['sections'][0]['title']='Outra seção'
            elif mutation=='long':candidate['sections'][0]['claims'][0]['text']='x'*321
            elif mutation=='dump':candidate['sections'][0]['claims']*=3
            elif mutation=='multiline':candidate['sections'][0]['claims'][0]['text']='Texto\nInventário enorme'
            with self.subTest(mutation=mutation),self.assertRaises(AIError):validate_response(candidate,context)

    def test_fixed_order_template_evidence_and_concise_markdown(self):
        class Reversed(Provider):
            def generate(self,context):
                result,usage=super().generate(context);result['sections'].reverse();return result,usage
        analysis=ir();result=DocumentationEngine().generate(analysis,Reversed())
        self.assertEqual([s['category'] for s in result['sections']],[c[0] for c in CATEGORIES])
        self.assertEqual(result['template_version'],'project-summary-v1')
        self.assertTrue(result['sections'][0]['claims'][0]['evidence_chain'])
        markdown=render_markdown(result,analysis['repository'])
        self.assertEqual(markdown.count('\n## '),9)
        self.assertIn('Não confirmado',markdown)
        self.assertNotIn('Primeiro contato',markdown)

    def test_context_includes_languages_and_organization_without_raw_code(self):
        context=build_context(ir())
        self.assertIn('language',{f['kind'] for f in context['facts']})
        self.assertIn('organization',{f['kind'] for f in context['facts']})
        self.assertNotIn('sqlite3.connect',json.dumps(context))

    def test_summary_report_and_technical_annex_have_different_scopes(self):
        analysis=ir();result=DocumentationEngine().generate(analysis,Provider())
        short=report_html(analysis,build_insights(analysis),ai=result)
        full=report_html(analysis,build_insights(analysis),ai=result,detailed=True)
        self.assertEqual(short.count('<section id="summary-'),9)
        self.assertEqual(short.count('<svg xmlns='),3)
        self.assertEqual(full.count('<svg xmlns='),6)
        self.assertNotIn('Símbolos extraídos',short)
        self.assertIn('anexo técnico',short)
        hostile=deepcopy(result);hostile['sections'][0]['claims'][0]['text']='<script>alert(1)</script>'
        self.assertNotIn('<script>',report_html(analysis,ai=hostile))

    def test_summary_is_in_documents_and_legacy_alias_preserved(self):
        jobs=Jobs()
        try:
            with patch('octorgit.web.create_provider',return_value=Provider()):
                job=jobs.submit({'source':'demo','use_ai':True})
            deadline=time.monotonic()+5
            while jobs.get(job['id'])['status'] not in ('completed','failed') and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(jobs.get(job['id'])['status'],'completed')
            result=jobs.result(job['id'])
            self.assertEqual(result['documents']['PROJECT.md'],result['documents']['AI.md'])
            self.assertEqual(result['documents']['PROJECT.md'].count('\n## '),9)
        finally:jobs.close()
