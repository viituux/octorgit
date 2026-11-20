import io
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from octorgit.ai_usage import UsageStore, MeteredProvider, profile
from octorgit.ai_engine import AIError, DocumentationEngine
from octorgit.ai_config import create_provider
from octorgit.code_parser import analyze
from octorgit.web import LocalServer

CONFIG = {'provider':'openai-compatible', 'base_url':'https://api.example.test/v1', 'model':'test-model', 'api_key':'dummy-credential-not-for-persistence'}


def policy(**overrides):
    return {'profile_id':profile(CONFIG)['id'], 'input_per_million':'2', 'output_per_million':'4', 'monthly_budget':'0.001', 'paused':False, **overrides}


def answer():
    return {'sections':[{'title':'Teste', 'claims':[{'text':'Não confirmado.', 'confidence':'unconfirmed','evidence_ids':[]}]}]}


class Fake:
    model = CONFIG['model']
    provider = CONFIG['provider']
    provider_id = 'fake'
    def generate(self, context):
        return answer(), {'promptTokenCount':1000, 'candidatesTokenCount':500, 'totalTokenCount':1500}


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.store = UsageStore()
        self.addCleanup(self.store.close)

    def test_cost_exact_budget_warning_and_monthly_totals(self):
        self.store.configure(policy(), CONFIG)
        MeteredProvider(Fake(), self.store, CONFIG, 'analysis').generate({})
        summary = self.store.summary(CONFIG)
        self.assertEqual(summary['totals']['estimated_cost'], '0.004')
        self.assertEqual(summary['totals']['total_tokens'], 1500)
        self.assertTrue(summary['totals']['budget_reached'])
        # Budget is advisory: another call is allowed.
        MeteredProvider(Fake(), self.store, CONFIG, 'connection_test').generate({})
        self.assertEqual(self.store.summary(CONFIG)['totals']['requests'], 2)

    @patch("octorgit.ai_usage.datetime")
    def test_unknown_prices_are_not_zero_and_new_rates_do_not_reprice_old_calls(self, clock):
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=timezone.utc)
        wrapped = MeteredProvider(Fake(), self.store, CONFIG, 'analysis')
        wrapped.generate({})
        self.store.configure(policy(), CONFIG)
        wrapped.generate({})
        summary = self.store.summary(CONFIG)
        self.assertEqual(summary['totals']['unknown_costs'], 1)
        self.assertEqual(summary['totals']['estimated_cost'], '0.004')
        self.assertIsNone(summary['recent'][1]['estimated_cost'])

    def test_pause_prevents_external_calls_without_counting_as_request(self):
        self.store.configure(policy(paused=True), CONFIG)
        with patch.object(Fake, 'generate') as call:
            with self.assertRaises(AIError):
                MeteredProvider(Fake(), self.store, CONFIG, 'analysis').generate({})
            call.assert_not_called()
        self.assertEqual(self.store.summary(CONFIG)['totals']['requests'], 0)

    def test_cache_does_not_duplicate_usage(self):
        ir = analyze({'url':None,'branch':None,'commit_sha':None,'source':'local_fixture'}, {'app.py':'x=1\n'}, [])
        engine = DocumentationEngine()
        wrapped = MeteredProvider(Fake(), self.store, CONFIG, 'analysis')
        self.assertFalse(engine.generate(ir, wrapped)['cache_hit'])
        self.assertTrue(engine.generate(ir, wrapped)['cache_hit'])
        self.assertEqual(self.store.summary(CONFIG)['totals']['requests'], 1)
        self.store.configure(policy(paused=True), CONFIG)
        self.assertTrue(engine.generate(ir, wrapped)['cache_hit'])

    def test_failed_response_still_counts_reported_tokens(self):
        self.store.configure(policy(), CONFIG)
        wrapped = MeteredProvider(create_provider(CONFIG), self.store, CONFIG, 'connection_test')
        body = {'choices':[{'finish_reason':'length','message':{'content':'broken'}}], 'usage':{'prompt_tokens':1000,'completion_tokens':500,'total_tokens':1500}}
        with patch('octorgit.ai_engine.urlopen', return_value=io.BytesIO(json.dumps(body).encode())):
            with self.assertRaises(AIError): wrapped.generate({})
        summary = self.store.summary(CONFIG)
        self.assertEqual(summary['totals']['errors'], 1)
        self.assertEqual(summary['totals']['total_tokens'], 1500)
        self.assertEqual(summary['totals']['estimated_cost'], '0.004')

    @patch("octorgit.ai_usage.datetime")
    def test_inflight_prices_and_interrupted_calls_remain_auditable(self, clock):
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=timezone.utc)
        self.store.configure(policy(), CONFIG)
        event = self.store.begin(CONFIG, 'analysis')
        self.store.configure(policy(input_per_million='20', output_per_million='40'), CONFIG)
        self.store.finish(event, {'promptTokenCount':1000,'candidatesTokenCount':500})
        self.assertEqual(self.store.summary(CONFIG)['totals']['estimated_cost'], '0.004')
        self.store.begin(CONFIG, 'connection_test')
        summary = self.store.summary(CONFIG)
        self.assertEqual(summary['recent'][0]['status'], 'started')
        self.assertEqual(summary['totals']['unknown_costs'], 1)

    def test_network_failure_has_unknown_usage_not_zero(self):
        with patch.object(Fake, 'generate', side_effect=AIError('Falha')):
            with self.assertRaises(AIError): MeteredProvider(Fake(), self.store, CONFIG, 'analysis').generate({})
        summary = self.store.summary(CONFIG)
        self.assertEqual(summary['totals']['unknown_tokens'], 1)
        self.assertEqual(summary['totals']['unknown_costs'], 1)
        self.assertIsNone(summary['recent'][0]['estimated_cost'])

    def test_pricing_profiles_and_invalid_numbers(self):
        for bad in ['NaN','Infinity','-1','1e100','1e-999999',True,{},'1,5']:
            with self.subTest(value=bad), self.assertRaises(AIError):
                self.store.configure(policy(input_per_million=bad), CONFIG)
        self.store.configure(policy(), CONFIG)
        changed = {**CONFIG, 'model':'other-model'}
        self.assertIsNone(self.store.summary(changed)['prices']['input_per_million'])
        with self.assertRaises(AIError): self.store.configure(policy(), changed)

    def test_persistence_no_key_or_prompts_and_current_month_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'usage.sqlite3'
            store = UsageStore(path)
            store.configure(policy(), CONFIG)
            MeteredProvider(Fake(), store, CONFIG, 'analysis').generate({'private':'do-not-save-prompt'})
            event = store.begin(CONFIG, 'analysis')
            store.finish(event, {'promptTokenCount':5,'candidatesTokenCount':10})
            with store.db:
                store.db.execute("UPDATE events SET created_at='2000-01-01' WHERE id=?", (event['id'],))
            store.close()
            reopened = UsageStore(path)
            try:
                summary = reopened.summary(CONFIG)
                self.assertEqual(summary['totals']['requests'], 1)
                self.assertEqual(len(summary['recent']), 2)
                self.assertTrue(summary['persistent'])
                raw = path.read_bytes()
                self.assertNotIn(CONFIG['api_key'].encode(), raw)
                self.assertNotIn(b'do-not-save-prompt', raw)
            finally: reopened.close()

    def test_reasoning_tokens_and_missing_metadata(self):
        self.store.configure(policy(), CONFIG)
        event = self.store.begin(CONFIG, 'analysis')
        self.store.finish(event, {'promptTokenCount':100,'candidatesTokenCount':20,'thoughtsTokenCount':30,'totalTokenCount':150})
        self.assertEqual(self.store.summary(CONFIG)['totals']['output_tokens'], 50)
        event = self.store.begin(CONFIG, 'analysis')
        self.store.finish(event, {'promptTokenCount':True,'totalTokenCount':-1})
        self.assertEqual(self.store.summary(CONFIG)['totals']['unknown_tokens'], 1)


class UsageHTTPTests(unittest.TestCase):
    def test_managing_usage_requires_session_and_pause_preserves_static_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            server = LocalServer(0, data_dir=directory)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = 'http://127.0.0.1:'+str(server.server_address[1])
            def request(path, payload=None, token=None):
                return urlopen(Request(base+path, data=json.dumps(payload).encode() if payload is not None else None,
                                      headers={'Content-Type':'application/json', 'X-OctorGit-Token':token or server.csrf}), timeout=5)
            try:
                with request('/api/ai/usage') as response: initial = json.load(response)
                self.assertEqual(initial['totals']['requests'], 0)
                with self.assertRaises(HTTPError) as rejected: request('/api/ai/usage', policy(), 'invalid')
                self.assertEqual(rejected.exception.code, 403)
                with request('/api/ai/config', CONFIG): pass
                with request('/api/ai/usage', policy()): pass
                with patch('octorgit.web.create_provider', return_value=Fake()):
                    with request('/api/ai/test', {}): pass
                with request('/api/ai/usage') as response: usage = json.load(response)
                self.assertEqual(usage['totals']['total_tokens'], 1500)
                self.assertNotIn(CONFIG['api_key'], json.dumps(usage))
                with request('/api/ai/usage', policy(paused=True)): pass
                with patch('octorgit.web.create_provider', return_value=Fake()):
                    with self.assertRaises(HTTPError) as paused: request('/api/ai/test', {})
                    self.assertEqual(paused.exception.code, 422)
                with request('/') as response:
                    html = response.read().decode()
                    self.assertIn('Consumo e custos da IA', html)
                    self.assertIn('ai-budget-form', html)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
