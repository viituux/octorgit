import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from octorgit.cli import main
from octorgit.code_parser import analyze
from octorgit.documentation import validate
from octorgit.repositories import allowed, safe_text, local_snapshot, github_snapshot

REPO = {"url": None, "branch": None, "commit_sha": None, "source": "local_fixture"}
SOURCE = '''from django.urls import path as route, include
from django.http import JsonResponse

def health(request):
    return JsonResponse({"ok": True})

class Service:
    async def run(self):
        pass

urlpatterns = [route("health/", health), route("api/", include("api.urls"))]
'''


class CoreTests(unittest.TestCase):
    def test_symbols_and_literal_routes_have_valid_evidence(self):
        files = {"urls.py": SOURCE}
        ir = analyze(REPO, files, [])
        self.assertEqual({s["name"] for s in ir["symbols"]}, {"health", "Service", "Service.run"})
        self.assertEqual(len(ir["endpoints"]), 1)
        self.assertEqual(ir["endpoints"][0]["route"], "health/")
        self.assertIsNone(ir["endpoints"][0]["method"])
        self.assertTrue(any(d["reason"] == "include_module_not_found" for d in ir["diagnostics"]))
        validate(ir, files)

    def test_invalid_reference_is_rejected(self):
        files = {"urls.py": SOURCE}
        ir = analyze(REPO, files, [])
        ir["symbols"][0]["evidence"]["end_line"] = 1000
        with self.assertRaises(ValueError):
            validate(ir, files)

    def test_policy_and_secret_detection(self):
        for name in [".env", ".env.production", ".git/config", "a/../b", "/etc/passwd", "a/key.pem", "node_modules/file.py"]:
            self.assertFalse(allowed(name), name)
        self.assertTrue(allowed("app/views.py"))
        self.assertIsNone(safe_text(b"abc\x00def"))
        self.assertIsNone(safe_text(b'API_KEY = "abcdefgh12345678"'))
        self.assertIsNone(safe_text(b"-----BEGIN RSA PRIVATE KEY-----"))

    def test_local_symlinks_are_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("x = 1\n")
            try:
                (root / "link.py").symlink_to(root / "ok.py")
            except OSError as exc:
                if getattr(exc, "winerror", None) == 1314:
                    self.skipTest("Windows sem permissão de criação de links simbólicos")
                raise
            (root / ".env").write_text("DO_NOT_READ=1")
            _, files, skipped = local_snapshot(root)
            self.assertEqual(list(files), ["ok.py"])
            self.assertEqual(len(skipped), 2)

    def test_parse_errors_are_reported_and_input_never_executes(self):
        files = {"bad.py": "def !", "setup.py": "raise RuntimeError('must not run')\n"}
        ir = analyze(REPO, files, [])
        self.assertEqual(ir["metrics"]["python_files_parsed"], 1)
        self.assertEqual(ir["diagnostics"][0]["reason"], "python_parse_failed")

    def test_nested_excluded_directories_are_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["src/node_modules", "src/.venv", "src/vendor"]:
                directory = root / name
                directory.mkdir(parents=True)
                (directory / "ignored.py").write_text("x = 1\n")
            (root / "src/keep.py").write_text("x = 2\n")
            _, files, skipped = local_snapshot(root)
            self.assertEqual(list(files), ["src/keep.py"])
            self.assertEqual(skipped, [])

    def test_dynamic_and_unrelated_path_calls_are_not_endpoints(self):
        ir = analyze(REPO, {"u.py": 'from pathlib import Path as path\nurlpatterns = [path("x")]\n'}, [])
        self.assertEqual(ir["endpoints"], [])
        ir = analyze(REPO, {"u.py": "urlpatterns = build_urls()\n"}, [])
        self.assertEqual(ir["diagnostics"][0]["reason"], "dynamic_urlpatterns_not_supported")

    def test_public_github_url_validation(self):
        for url in ["http://github.com/a/b", "https://evil.test/a/b", "https://github.com/a/b?token=x", "https://github.com/../b"]:
            with self.assertRaises(ValueError):
                github_snapshot(url)

    def test_github_uses_resolved_sha_and_rejects_archive_links(self):
        archive_data = io.BytesIO()
        with tarfile.open(fileobj=archive_data, mode="w:gz") as archive:
            payload = SOURCE.encode()
            member = tarfile.TarInfo("repo-sha/urls.py")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
            member = tarfile.TarInfo("repo-sha/escape.py")
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            archive.addfile(member)
        sha = "a" * 40
        with patch("octorgit.repositories.request", side_effect=[json.dumps({"sha": sha}).encode(), archive_data.getvalue()]) as req:
            repo, files, skipped = github_snapshot("https://github.com/example/demo.git", "feature/test")
        self.assertEqual(repo["commit_sha"], sha)
        self.assertEqual(list(files), ["urls.py"])
        self.assertEqual(len(skipped), 1)
        self.assertIn("feature%2Ftest", req.call_args_list[0].args[0])
        self.assertTrue(req.call_args_list[1].args[0].endswith(sha))

    def test_cli_exports_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "urls.py").write_text(SOURCE)
            out = root / "result"
            args = ["--local", str(source), "--output", str(out)]
            self.assertEqual(main(args), 0)
            self.assertEqual({p.name for p in out.iterdir()}, {"analysis.json", "README.md", "ARCHITECTURE.md", "ENDPOINTS.md", "RELATORIO.html", "diagramas"})
            self.assertEqual(main(args), 1)
            ir = json.loads((out / "analysis.json").read_text())
            self.assertEqual(ir["repository"]["source"], "local_fixture")


if __name__ == "__main__":
    unittest.main()
