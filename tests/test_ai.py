from helpers_ai import structured_response
from copy import deepcopy
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from octorgit.ai_engine import (AIError, DocumentationEngine, GeminiProvider, MAX_CONTEXT_BYTES,
                               build_context, render_markdown, settings, validate_response)
from octorgit.code_parser import analyze
from octorgit.repositories import local_snapshot
from octorgit.web import Jobs

FIXTURE = Path(__file__).parent / "fixtures/django_nested/repo"


def analysis():
    repo, files, skipped = local_snapshot(FIXTURE)
    return analyze(repo, files, skipped, root_urlconf="config.urls")


def response(context):
    result = structured_response()
    result["sections"][0]["claims"] = [
        {"text": "O projeto declara uma rota de consulta.", "confidence": "inferred", "evidence_ids": [context["facts"][0]["id"]]},
        {"text": "As instruções para executar o projeto não foram confirmadas.", "confidence": "unconfirmed", "evidence_ids": []}
    ]
    return result


class FakeProvider:
    model = "gemini-test"

    def __init__(self):
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        return response(context), {"totalTokenCount": 120}


class AITests(unittest.TestCase):
    def test_context_budget_and_no_raw_source(self):
        ir = analysis()
        context = build_context(ir)
        serialized = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        self.assertLessEqual(len(serialized.encode()), MAX_CONTEXT_BYTES)
        self.assertNotIn("def health(", serialized)
        self.assertNotIn("return JsonResponse", serialized)
        self.assertTrue(context["partial"])
        self.assertTrue(context["facts"])
        small = build_context(ir, budget=3500)
        self.assertLessEqual(len(json.dumps(small, ensure_ascii=False, separators=(",", ":")).encode()), 3500)

    def test_valid_response_and_enriched_evidence(self):
        ir = analysis()
        provider = FakeProvider()
        result = DocumentationEngine().generate(ir, provider)
        claim = result["sections"][0]["claims"][0]
        self.assertTrue(claim["evidence_chain"])
        self.assertEqual(result["reference_validation"], "valid_fact_ids_not_semantic_proof")
        self.assertEqual(result["usage"]["totalTokenCount"], 120)
        self.assertIn("**Inferido**", render_markdown(result, ir["repository"]))

    def test_invalid_ids_and_false_extracted_claim_are_rejected(self):
        context = build_context(analysis())
        for fields in [{"evidence_ids": ["F99999"]}, {"evidence_ids": []}, {"confidence": "extracted"}, {"confidence": []}, {"text": ""}, {"confidence": "unconfirmed", "evidence_ids": ["F0001"]}]:
            candidate = response(context)
            candidate["sections"][0]["claims"][0].update(fields)
            with self.assertRaises(AIError):
                validate_response(candidate, context)
        for candidate in [None, [], {}, {"sections": []}, {"sections": [], "markdown": "invented"}]:
            with self.assertRaises(AIError):
                validate_response(candidate, context)

    def test_cache_is_by_context_model_and_commit(self):
        ir = analysis()
        provider, engine = FakeProvider(), DocumentationEngine()
        first = engine.generate(ir, provider)
        cached = engine.generate(ir, provider)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(provider.calls, 1)
        ir["repository"]["commit_sha"] = "b" * 40
        self.assertFalse(engine.generate(ir, provider)["cache_hit"])
        self.assertEqual(provider.calls, 2)

    def test_configuration_never_exposes_key(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-private-key", "GEMINI_MODEL": "gemini-test"}, clear=True):
            config = settings()
            self.assertTrue(config["configured"])
            self.assertNotIn("test-private-key", json.dumps(config))
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIError):
                GeminiProvider()

    def test_provider_request_uses_header_and_structured_schema(self):
        context = build_context(analysis())
        answer = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(response(context))}]}}], "usageMetadata": {"totalTokenCount": 300}}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-private-key", "GEMINI_MODEL": "gemini-test"}, clear=True):
            with patch("octorgit.ai_engine.urlopen", return_value=io.BytesIO(json.dumps(answer).encode())) as request:
                data, usage = GeminiProvider().generate(context)
        validate_response(data, context)
        req = request.call_args.args[0]
        self.assertNotIn("test-private-key", req.full_url)
        self.assertNotIn("test-private-key", req.data.decode())
        self.assertEqual(req.get_header("X-goog-api-key"), "test-private-key")
        payload = json.loads(req.data)
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 4096)
        self.assertEqual(usage["totalTokenCount"], 300)

    def test_provider_error_does_not_leak_error_body_or_key(self):
        error = HTTPError("https://example.test", 403, "test-private-key", {}, io.BytesIO(b"test-private-key"))
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-private-key", "GEMINI_MODEL": "gemini-test"}, clear=True):
            with patch("octorgit.ai_engine.urlopen", side_effect=error):
                with self.assertRaises(AIError) as caught:
                    GeminiProvider().generate(build_context(analysis()))
        self.assertNotIn("test-private-key", str(caught.exception))
        self.assertIn("autorizou", str(caught.exception))

    def test_truncated_model_output_is_not_accepted(self):
        answer = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}}]}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-private-key"}, clear=True):
            with patch("octorgit.ai_engine.urlopen", return_value=io.BytesIO(json.dumps(answer).encode())):
                with self.assertRaises(AIError):
                    GeminiProvider().generate(build_context(analysis()))

    def test_invalid_response_is_not_cached(self):
        provider = FakeProvider()
        engine = DocumentationEngine()
        with patch.object(provider, "generate", return_value=({"sections": []}, {})):
            with self.assertRaises(AIError):
                engine.generate(analysis(), provider)
        self.assertEqual(engine.cache, {})

    def test_web_preserves_static_result_on_ai_failure(self):
        jobs = Jobs()
        try:
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-private-key"}, clear=True):
                with patch.object(jobs.ai_engine, "generate", side_effect=AIError("Cota indisponível")):
                    job = jobs.submit({"source": "demo", "use_ai": True})
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline and jobs.get(job["id"])["status"] not in {"completed", "failed"}:
                        time.sleep(.01)
                    result = jobs.result(job["id"])
            self.assertIsNotNone(result)
            self.assertEqual(result["ai"]["status"], "failed")
            self.assertIn("ENDPOINTS.md", result["documents"])
            self.assertEqual(len(result["analysis"]["endpoints"]), 11)
        finally:
            jobs.close()

    def test_web_generates_optional_ai_files(self):
        jobs = Jobs()
        try:
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-private-key"}, clear=True):
                with patch("octorgit.web.create_provider", return_value=FakeProvider()):
                    job = jobs.submit({"source": "demo", "use_ai": True})
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline and jobs.get(job["id"])["status"] not in {"completed", "failed"}:
                        time.sleep(.01)
                    result = jobs.result(job["id"])
            self.assertEqual(result["ai"]["status"], "completed")
            self.assertIn("AI.md", result["documents"])
            self.assertIn("AI.json", result["documents"])
        finally:
            jobs.close()

    def test_ai_opt_in_requires_key_and_boolean(self):
        jobs = Jobs()
        try:
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ValueError):
                    jobs.submit({"source": "demo", "use_ai": True})
            with self.assertRaises(ValueError):
                jobs.submit({"source": "demo", "use_ai": "yes"})
        finally:
            jobs.close()
