import io
import json
import re
import threading
import time
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import zipfile

from octorgit.web import Jobs, LocalServer, default_data_dir
from pathlib import Path


class WebTests(unittest.TestCase):
    def test_data_directory_respects_platform_environment(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": "/tmp/appdata"}, clear=True):
            self.assertEqual(default_data_dir(), Path("/tmp/appdata") / "OctorGit")
        with patch.dict("os.environ", {"XDG_DATA_HOME": "/tmp/xdg-data"}, clear=True):
            self.assertEqual(default_data_dir(), Path("/tmp/xdg-data") / "octorgit")
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path, payload=None, headers=None):
        request_headers = {} if headers is None else dict(headers)
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            request_headers.setdefault("Content-Type", "application/json")
            request_headers.setdefault("X-OctorGit-Token", self.server.csrf)
        return urlopen(Request(self.base + path, data=data, headers=request_headers), timeout=5)

    def finished(self, job_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with self.request(f"/api/jobs/{job_id}") as response:
                job = json.load(response)
            if job["status"] in {"completed", "failed"}:
                return job
            time.sleep(.01)
        self.fail("A análise de teste não foi concluída.")

    def test_demo_to_result_evidence_and_zip(self):
        with self.request("/api/jobs", {"source": "demo"}) as response:
            self.assertEqual(response.status, 202)
            job = json.load(response)
        self.assertEqual(self.finished(job["id"])["status"], "completed")
        with self.request(f"/api/jobs/{job['id']}/result") as response:
            data = json.load(response)
        ir = data["analysis"]
        self.assertEqual(len(ir["endpoints"]), 11)
        self.assertIn(("GET", "health/"), {(e["method"], e["route"]) for e in ir["endpoints"]})
        self.assertTrue(all(e["evidence_chain"] for e in ir["endpoints"]))
        self.assertIsNone(ir["repository"]["commit_sha"])
        with self.request(f"/api/jobs/{job['id']}/download") as response:
            self.assertEqual(response.headers.get_content_type(), "application/zip")
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        self.assertTrue({"README.md", "ENDPOINTS.md", "ARCHITECTURE.md", "analysis.json", "RELATORIO.html", "diagramas/endpoints.svg"} <= set(archive.namelist()))
        self.assertEqual(len([n for n in archive.namelist() if n.endswith(".svg")]), 6)
        self.assertIsNone(archive.testzip())
        with self.request(f"/api/jobs/{job['id']}/documents/ENDPOINTS.md") as response:
            self.assertIn("health/", response.read().decode())
        with self.request("/api/jobs") as response:
            history = json.load(response)["jobs"]
        self.assertTrue(any(j["id"] == job["id"] for j in history))
        self.assertFalse(any("ir" in j or "documents" in j for j in history))

    def test_assets_packaged_and_session_token_in_html(self):
        with self.request("/") as response:
            text = response.read().decode()
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(self.server.csrf, text)
        self.assertNotIn("__CSRF__", text)
        for path, expected in [("/app.js", "text/javascript"), ("/style.css", "text/css")]:
            with self.request(path) as response:
                self.assertEqual(response.headers.get_content_type(), expected)
                self.assertGreater(len(response.read()), 100)
        # Every script/style src in the document is a bundled local resource.
        self.assertEqual(re.findall(r'<script[^>]+src="([^"]+)"', text), ["/app.js"])

    def test_post_requires_token(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/jobs", {"source": "demo"}, {"X-OctorGit-Token": "bad"})
        self.assertEqual(caught.exception.code, 403)

    def test_cross_origin_and_host_rejected(self):
        for headers in [{"Origin": "https://evil.example"}, {"Host": "evil.example"}]:
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/jobs", {"source": "demo"}, headers)
            self.assertEqual(caught.exception.code, 403)

    def test_arbitrary_files_and_paths_not_accepted(self):
        for payload in [{"source": "local", "repo": "/etc/passwd"}, {"source": "demo", "path": "/etc/passwd"}, {"source": "github", "repo": "http://localhost:8000"}]:
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/jobs", payload)
            self.assertEqual(caught.exception.code, 400)
        for path in ["/../pyproject.toml", "/static/demo.json", "/api/jobs/not-a-job/download", "/favicon.ico"]:
            with self.assertRaises(HTTPError) as caught:
                self.request(path)
            self.assertEqual(caught.exception.code, 404)

    def test_failed_github_job_returns_actionable_error(self):
        from urllib.error import HTTPError
        error = HTTPError("https://api.github.com/", 404, "Not found", {}, None)
        with patch("octorgit.web.github_snapshot", side_effect=error):
            with self.request("/api/jobs", {"source": "github", "repo": "https://github.com/example/missing"}) as response:
                job = json.load(response)
            result = self.finished(job["id"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("não encontrado", result["error"])
        with self.assertRaises(HTTPError) as caught:
            self.request(f"/api/jobs/{job['id']}/result")
        self.assertEqual(caught.exception.code, 409)

    def test_gemini_config_and_optional_downloads_over_http(self):
        class FakeProvider:
            model = "gemini-test"

            def generate(self, context):
                return {"sections": [{"title": "Organização", "claims": [
                    {"text": "Uma rota está declarada no projeto.", "confidence": "inferred", "evidence_ids": [context["facts"][0]["id"]]}
                ]}]}, {"totalTokenCount": 99}
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-http-private-key", "GEMINI_MODEL": "gemini-test"}):
            with self.request("/api/config") as response:
                config_bytes = response.read()
            self.assertTrue(json.loads(config_bytes)["ai"]["configured"])
            self.assertNotIn(b"test-http-private-key", config_bytes)
            with patch("octorgit.web.GeminiProvider", return_value=FakeProvider()):
                with self.request("/api/jobs", {"source": "demo", "use_ai": True}) as response:
                    job = json.load(response)
                self.assertEqual(self.finished(job["id"])["status"], "completed")
            with self.request(f"/api/jobs/{job['id']}/documents/AI.md") as response:
                self.assertIn("**Inferido**", response.read().decode())
            with self.request(f"/api/jobs/{job['id']}/download") as response:
                archive = zipfile.ZipFile(io.BytesIO(response.read()))
            self.assertIn("AI.json", archive.namelist())
            self.assertNotIn(b"test-http-private-key", archive.read("AI.json"))

    def test_only_one_analysis_runs_at_a_time(self):
        from octorgit.web import BusyError
        entered, release = threading.Event(), threading.Event()
        def blocked_snapshot(*args):
            entered.set()
            release.wait(timeout=5)
            raise ValueError("Teste de concorrência")
        jobs = Jobs()
        try:
            with patch("octorgit.web.github_snapshot", side_effect=blocked_snapshot):
                jobs.submit({"source": "github", "repo": "https://github.com/example/demo"})
                self.assertTrue(entered.wait(timeout=2))
                with self.assertRaises(BusyError):
                    jobs.submit({"source": "demo"})
                release.set()
                jobs.close()
        finally:
            release.set()
            jobs.close()

    def test_recent_history_is_bounded(self):
        jobs = Jobs()
        try:
            for index in range(9):
                job = jobs.submit({"source": "demo"})
                deadline = time.monotonic() + 3
                while jobs.get(job["id"])["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(jobs.get(job["id"])["status"], "completed")
            self.assertEqual(len(jobs.list()), 8)
        finally:
            jobs.close()

    def test_visual_report_comparison_and_svg_routes(self):
        with self.request("/api/jobs", {"source": "demo"}) as response:
            before = json.load(response)
        self.assertEqual(self.finished(before["id"])["status"], "completed")
        with self.request("/api/jobs", {"source": "demo-next"}) as response:
            after = json.load(response)
        self.assertEqual(self.finished(after["id"])["status"], "completed")
        query = f"?base={before['id']}"
        with self.request(f"/api/jobs/{after['id']}/compare" + query) as response:
            diff = json.load(response)["comparison"]
        self.assertTrue(any(e["route"] == "status/" for e in diff["added"]))
        with self.request(f"/api/jobs/{after['id']}/report" + query + "&download=1") as response:
            report = response.read().decode()
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers.get_content_type(), "text/html")
        self.assertEqual(report.count('<svg xmlns='), 6)
        self.assertIn("status/", report)
        with self.request(f"/api/jobs/{after['id']}/diagrams/arquitetura.svg" + query) as response:
            self.assertEqual(response.headers.get_content_type(), "image/svg+xml")
            self.assertIn(b"<svg", response.read())
        with self.request(f"/api/jobs/{after['id']}/compare?base=none") as response:
            self.assertIsNone(json.load(response)["comparison"])
        for path in [f"/api/jobs/{after['id']}/report?base=missing", f"/api/jobs/{after['id']}/download?base=missing"]:
            with self.assertRaises(HTTPError) as caught:
                self.request(path)
            self.assertEqual(caught.exception.code, 400)

    def test_persisted_result_can_be_reopened_after_http_server_restart(self):
        def request(base, path, server, payload=None):
            headers = {}
            data = None
            if payload is not None:
                data = json.dumps(payload).encode()
                headers = {"Content-Type": "application/json", "X-OctorGit-Token": server.csrf}
            return urlopen(Request(base + path, data=data, headers=headers), timeout=5)
        with tempfile.TemporaryDirectory() as directory:
            job = None
            for iteration in range(2):
                server = LocalServer(0, data_dir=directory)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_address[1]}"
                try:
                    if not iteration:
                        with request(base, "/api/jobs", server, {"source": "demo"}) as response:
                            job = json.load(response)
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline and server.jobs.get(job["id"])["status"] not in {"completed", "failed"}:
                            time.sleep(.01)
                    with request(base, f"/api/jobs/{job['id']}/result", server) as response:
                        result = json.load(response)
                    self.assertEqual(len(result["analysis"]["endpoints"]), 11)
                    self.assertTrue(result["insights"]["snippets"])
                finally:
                    server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
