from helpers_ai import structured_response
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from octorgit.ai_config import AIConfiguration, create_provider, validate_config
from octorgit.ai_engine import AIError, DocumentationEngine, NoRedirect
from octorgit.code_parser import analyze
from octorgit.documentation import validate
from octorgit.reports import technology_svg, report_html
from octorgit.insights import build_insights

REPO = {"url": None, "branch": None, "commit_sha": None, "source": "local_fixture"}


def answer():
    return structured_response()


class TechnologyTests(unittest.TestCase):
    def test_django_database_and_framework_have_exact_evidence(self):
        files = {"settings.py": '''import os
from django.conf import settings
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": os.environ["DB_NAME"]}}
'''}
        ir = analyze(REPO, files, [])
        tech = ir["technology"]
        self.assertIn("Python", {l["name"] for l in tech["languages"]})
        db = next(c for c in tech["components"] if c["kind"] == "database")
        self.assertEqual(db["name"], "PostgreSQL")
        self.assertEqual(db["evidence_chain"][0]["start_line"], 3)
        self.assertTrue(any(r["kind"] == "database_configuration" for r in tech["relations"]))
        validate(ir, files)

    def test_compose_images_and_declared_dependencies_only(self):
        files = {"compose.yaml": '''services:
  api:
    build: .
    depends_on: [db, broker]
  db:
    image: postgres:16
  broker:
    image: apache/kafka:3.9
  proxy:
    image: nginx:1.27
    depends_on:
      api:
        condition: service_started
''', "Dockerfile": "FROM python:3.12\n", "app.py": "import django\n"}
        ir = analyze(REPO, files, [])
        names = {c["name"] for c in ir["technology"]["components"]}
        self.assertIn("PostgreSQL · db", names)
        self.assertIn("Kafka · broker", names)
        self.assertIn("Nginx · proxy", names)
        self.assertIn("Docker Compose", names)
        self.assertEqual(len([r for r in ir["technology"]["relations"] if r["kind"] == "declared_dependency"]), 3)
        validate(ir, files)
        ET.fromstring(technology_svg(ir))

    def test_dependency_driver_does_not_confirm_database_or_cloud(self):
        ir = analyze(REPO, {"requirements.txt": "psycopg[binary]\n", "main.py": "x = 1\n"}, [])
        self.assertFalse(any(c["kind"] == "database" for c in ir["technology"]["components"]))
        image = technology_svg(ir)
        self.assertIn("Banco não confirmado", image)
        self.assertIn("Hospedagem não confirmada", image)
        self.assertNotIn("Kafka", image)
        self.assertNotIn("MICROSERVICE", image)

    def test_queue_and_cache_client_dependencies_are_not_drawn_as_servers(self):
        ir = analyze(REPO, {"requirements.txt": "redis\nkafka-python\n"}, [])
        self.assertTrue(any(c["name"] == "Redis (cliente)" for c in ir["technology"]["components"]))
        image = technology_svg(ir)
        self.assertNotIn("Redis (cliente)", image)
        self.assertNotIn("Kafka (cliente)", image)

    def test_language_identification_does_not_claim_endpoint_parser_for_other_languages(self):
        ir = analyze(REPO, {"src/app.ts": "const app = 1;", "package.json": '{"dependencies":{"express":"5"}}'}, [])
        self.assertEqual(ir["files"][1]["language"], "typescript")
        self.assertIn("TypeScript", {l["name"] for l in ir["technology"]["languages"]})
        self.assertIn("Express", {c["name"] for c in ir["technology"]["components"]})
        self.assertEqual(ir["endpoints"], [])
        self.assertEqual(ir["metrics"]["python_files_parsed"], 0)

    def test_test_examples_and_commented_terraform_are_not_deployment_evidence(self):
        files = {"tests/fixtures/settings.py": 'DATABASES = {"default":{"ENGINE":"django.db.backends.mysql"}}',
                 "examples/compose.yml": 'services:\n  db:\n    image: postgres:16\n',
                 "main.tf": '# provider "aws" {}\n/*\nprovider "google" {}\n*/\nprovider "azurerm" {}\n',
                 "app.py": "x = 1\n"}
        ir = analyze(REPO, files, [])
        names = {c["name"] for c in ir["technology"]["components"]}
        self.assertIn("Azure", names)
        self.assertNotIn("AWS", names)
        self.assertNotIn("Google Cloud", names)
        self.assertFalse(any(c["kind"] == "database" for c in ir["technology"]["components"]))
        validate(ir, files)

    def test_report_has_technology_map_and_no_first_contact(self):
        ir = analyze(REPO, {"app.py": "import flask\n", "compose.yml": "services:\n  cache:\n    image: redis:7\n"}, [])
        report = report_html(ir, build_insights(ir))
        self.assertIn("Redis", report)
        self.assertIn("Flask", report)
        self.assertNotIn("Primeiro contato", report)
        self.assertNotIn("primeiro-contato", report)
        self.assertNotIn("Guia de primeiro contato", report)
        self.assertEqual(report.count('<svg xmlns='), 6)


class AISettingsTests(unittest.TestCase):
    def config(self, **overrides):
        return {"provider": "openai-compatible", "base_url": "https://api.example.test/v1", "model": "my-model", "api_key": "dummy-session-secret", **overrides}

    def test_key_is_not_persisted_or_echoed_and_reopening_requires_new_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            path = Path(directory) / "ai-settings.json"
            config = AIConfiguration(path)
            public = config.apply(self.config())
            self.assertTrue(public["key_present"])
            self.assertNotIn("dummy-session-secret", json.dumps(public))
            self.assertNotIn("dummy-session-secret", path.read_text())
            reopened = AIConfiguration(path)
            self.assertEqual(reopened.public()["model"], "my-model")
            self.assertFalse(reopened.public()["key_present"])

    def test_destination_change_does_not_reuse_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            config = AIConfiguration()
            config.apply(self.config())
            config.apply({"model": "another-model"})
            self.assertEqual(config.snapshot()["api_key"], "dummy-session-secret")
            public = config.apply({"base_url": "https://another.example.test/v1"})
            self.assertFalse(public["key_present"])
            config.apply({"api_key": "new-session-secret"})
            config.apply({"clear_key": True})
            self.assertFalse(config.public()["key_present"])

    def test_provider_and_urls_are_validated_without_echoing_secrets(self):
        for overrides in [{"provider": []}, {"provider": "unknown"}, {"base_url": "http://remote.example/v1"},
                          {"base_url": "https://user:password@api.example/v1"}, {"base_url": "https://api.example/v1?key=secret"},
                          {"base_url": "https://api.example/v1#secret"}, {"model": "x\nsecret"}, {"api_key": "key with spaces"}]:
            with self.assertRaises(AIError):
                validate_config(self.config(**overrides))
        local = validate_config(self.config(base_url="http://127.0.0.1:11434/v1", api_key=""))
        self.assertEqual(create_provider(local).provider, "openai-compatible")

    def test_openai_compatible_transport_and_token_usage(self):
        body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer())}}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}
        with patch("octorgit.ai_engine.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as transport:
            response, usage = create_provider(self.config()).generate({"facts": []})
        self.assertEqual(response, answer())
        request = transport.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/v1/chat/completions"))
        self.assertEqual(request.get_header("Authorization"), "Bearer dummy-session-secret")
        self.assertNotIn("dummy-session-secret", request.data.decode())
        self.assertEqual(usage["totalTokenCount"], 30)
        self.assertIn("max_tokens", json.loads(request.data))

    def test_anthropic_transport(self):
        body = {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(answer())}], "usage": {"input_tokens": 5, "output_tokens": 7}}
        with patch("octorgit.ai_engine.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as transport:
            response, usage = create_provider(self.config(provider="anthropic", model="claude-test")).generate({"facts": []})
        request = transport.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/messages"))
        self.assertEqual(request.get_header("X-api-key"), "dummy-session-secret")
        self.assertNotIn("dummy-session-secret", request.data.decode())
        self.assertEqual(response, answer())
        self.assertEqual(usage["totalTokenCount"], 12)

    def test_rejected_or_truncated_response_is_not_published(self):
        error = HTTPError("https://api.example", 401, "dummy-session-secret", {}, None)
        with patch("octorgit.ai_engine.urlopen", side_effect=error):
            with self.assertRaises(AIError) as caught:
                create_provider(self.config()).generate({})
        self.assertNotIn("dummy-session-secret", str(caught.exception))
        body = {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}
        with patch("octorgit.ai_engine.urlopen", return_value=io.BytesIO(json.dumps(body).encode())):
            with self.assertRaises(AIError):
                create_provider(self.config()).generate({})

    def test_redirect_does_not_forward_key(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    def test_provider_cannot_echo_credentials_into_documents(self):
        body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"sections": [{"title": "dummy-session-secret", "claims": []}]})}}]}
        with patch("octorgit.ai_engine.urlopen", return_value=io.BytesIO(json.dumps(body).encode())):
            with self.assertRaises(AIError) as caught:
                create_provider(self.config()).generate({})
        self.assertNotIn("dummy-session-secret", str(caught.exception))

    def test_cache_separates_providers_with_same_model_name(self):
        class FakeProvider:
            model = "same-model"
            provider = "fake"
            def __init__(self, identity): self.provider_id = identity; self.calls = 0
            def generate(self, context): self.calls += 1; return answer(), {}
        ir = analyze(REPO, {"main.py": "def main(): pass\n"}, [])
        engine = DocumentationEngine()
        one, two = FakeProvider("one"), FakeProvider("two")
        self.assertFalse(engine.generate(ir, one)["cache_hit"])
        self.assertFalse(engine.generate(ir, two)["cache_hit"])
        self.assertTrue(engine.generate(ir, one)["cache_hit"])
        self.assertEqual((one.calls, two.calls), (1, 1))


if __name__ == "__main__":
    unittest.main()
