from copy import deepcopy
from importlib.resources import files as resources
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from octorgit.code_parser import analyze
from octorgit.documentation import validate
from octorgit.history import HistoryStore, compare_analyses, snapshot_fingerprint
from octorgit.insights import build_insights
from octorgit.reports import diagrams, report_html
from octorgit.web import Jobs


def demo():
    snapshot = json.loads(resources("octorgit").joinpath("static/demo.json").read_text())
    return snapshot["repository"], snapshot["files"]


def wait(jobs, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = jobs.get(job["id"])
        if current["status"] in {"completed", "failed"}:
            return current
        time.sleep(.01)
    raise AssertionError("Análise não terminou")


class VisualTests(unittest.TestCase):
    def test_technology_and_snippets_point_to_actual_code(self):
        repo, source = demo()
        ir = analyze(repo, source, [], "config.urls")
        insights = build_insights(ir, source)
        self.assertNotIn("guide", insights)
        self.assertTrue(ir["technology"]["languages"])
        for snippet in insights["snippets"].values():
            for row in snippet["lines"]:
                self.assertEqual(row["text"], source[snippet["file"]].splitlines()[row["number"] - 1][:400])
            self.assertLessEqual(len(snippet["lines"]), 30)
        validate(ir, source)

    def test_coverage_keeps_python_and_exclusions_separate(self):
        repo, source = demo()
        source["broken.py"] = "def ?"
        skipped = [{"path": "ignored.py", "reason": "policy"}, {"path": "large.bin", "reason": "policy"}]
        ir = analyze(repo, source, skipped, "config.urls")
        coverage = build_insights(ir, source)["coverage"]
        self.assertEqual(coverage["python_failed"], 1)
        self.assertEqual(coverage["python_parsed"] + 1, coverage["python_accepted"])
        self.assertEqual(coverage["skipped_python"], 1)
        self.assertEqual(coverage["skipped_files"], 2)

    def test_svg_images_are_well_formed_and_self_contained(self):
        repo, source = demo()
        ir = analyze(repo, source, [], "config.urls")
        charts = diagrams(ir, build_insights(ir, source))
        self.assertEqual(set(charts), {"arquitetura", "arquivos", "endpoints", "historico", "comparacao", "cobertura"})
        for svg in charts.values():
            tree = ET.fromstring(svg)
            self.assertTrue(tree.tag.endswith("svg"))
            self.assertNotIn("<script", svg)
            self.assertNotIn("<image", svg)
            for rect in tree.iter("{http://www.w3.org/2000/svg}rect"):
                self.assertGreaterEqual(float(rect.get("width")), 0)

    def test_control_characters_in_route_do_not_break_svg(self):
        repo, source = demo()
        ir = analyze(repo, source, [], "config.urls")
        ir["endpoints"][0]["route"] = "unsafe\x01<route>"
        from octorgit.reports import endpoint_svg
        svg = endpoint_svg(ir)
        ET.fromstring(svg)
        self.assertNotIn("\x01", svg)
        self.assertIn("&lt;route&gt;", svg)

    def test_html_report_contains_all_chapters_and_escaped_code(self):
        repo, source = demo()
        source["api/views.py"] += '\ndef extra():\n    return "<img src=x onerror=alert(1)>"\n'
        ir = analyze(repo, source, [], "config.urls")
        report = report_html(ir, build_insights(ir, source))
        self.assertEqual(report.count('<svg xmlns='), 6)
        for name in ("tecnologias", "codigo", "arquitetura", "endpoints", "historico", "comparacao", "cobertura"):
            self.assertIn(f'id="{name}"', report)
        self.assertNotIn('<img src=x', report)
        self.assertIn('&lt;img src=x', report)
        self.assertNotIn('<script', report)
        self.assertIn('@media print', report)
        self.assertIn('default-src', report)

    def test_history_survives_new_store_and_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(HistoryStore(directory))
            try:
                job = jobs.submit({"source": "demo"})
                self.assertEqual(wait(jobs, job)["status"], "completed")
                original = jobs.result(job["id"])
            finally:
                jobs.close()
            reopened = Jobs(HistoryStore(directory))
            try:
                restored = reopened.result(job["id"])
                self.assertEqual(restored["analysis"], original["analysis"])
                self.assertEqual(restored["insights"]["snippets"], original["insights"]["snippets"])
                self.assertEqual(len(reopened.list()), 1)
                self.assertNotIn("insights", reopened.list()[0])
            finally:
                reopened.close()

    def test_persisted_history_outlives_eight_item_memory_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            jobs = Jobs(HistoryStore(directory))
            try:
                first = None
                for i in range(10):
                    job = jobs.submit({"source": "demo"})
                    first = first or job["id"]
                    self.assertEqual(wait(jobs, job)["status"], "completed")
                self.assertEqual(len(jobs.list()), 10)
                self.assertIsNotNone(jobs.result(first))
                self.assertEqual(len(jobs.items), 8)
            finally:
                jobs.close()

    def test_demo_comparison_has_real_added_and_removed_route(self):
        jobs = Jobs()
        try:
            before = jobs.submit({"source": "demo"})
            self.assertEqual(wait(jobs, before)["status"], "completed")
            after = jobs.submit({"source": "demo-next"})
            self.assertEqual(wait(jobs, after)["status"], "completed")
            _, diff = jobs.visual_context(after["id"])
            self.assertEqual(diff["base_id"], before["id"])
            self.assertIn(("GET", "status/"), {(e["method"], e["route"]) for e in diff["added"]})
            self.assertIn(("GET", "health/"), {(e["method"], e["route"]) for e in diff["removed"]})
            self.assertTrue(any("permissions" in row["fields"] for row in diff["changed"]))
            self.assertIn("ENDPOINTS.md", {d["document"] for d in diff["documents_to_review"]})
            _, none = jobs.visual_context(after["id"], "none")
            self.assertIsNone(none)
        finally:
            jobs.close()

    def test_comparison_rejects_other_repo_and_warns_about_parser(self):
        repo, source = demo()
        before = analyze(repo, source, [], "config.urls")
        after = deepcopy(before)
        after["repository"]["url"] = "https://github.com/another/project"
        with self.assertRaises(ValueError):
            compare_analyses(before, after)
        after = deepcopy(before)
        after["parser_version"] = "another-version"
        self.assertTrue(compare_analyses(before, after)["warnings"])
        self.assertEqual(snapshot_fingerprint(before), snapshot_fingerprint(after))

    def test_unchanged_analysis_does_not_mark_documents_stale(self):
        repo, source = demo()
        ir = analyze(repo, source, [], "config.urls")
        diff = compare_analyses(ir, deepcopy(ir))
        self.assertFalse(diff["added"])
        self.assertFalse(diff["removed"])
        self.assertFalse(diff["changed"])
        self.assertFalse(diff["documents_to_review"])

    def test_disk_failure_keeps_result_but_surfaces_storage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(directory)
            jobs = Jobs(store)
            try:
                with patch.object(store, "save", side_effect=sqlite3.OperationalError("disk full")):
                    job = jobs.submit({"source": "demo"})
                    self.assertEqual(wait(jobs, job)["status"], "completed")
                result = jobs.result(job["id"])
                self.assertTrue(result["storage_error"])
                self.assertIn("ENDPOINTS.md", result["documents"])
            finally:
                jobs.close()


class EndpointConfigurationTests(unittest.TestCase):
    def test_demo_serializer_permissions_authentication_and_evidence(self):
        repo, source = demo()
        ir = analyze(repo, source, [], "config.urls")
        user = next(e for e in ir["endpoints"] if e["view"] == "api.views.Users.list")
        self.assertEqual(user["serializer"], "api.serializers.UserSerializer")
        self.assertEqual(user["permissions"], ["rest_framework.permissions.IsAuthenticated"])
        self.assertEqual(user["authentication"], ["rest_framework.authentication.SessionAuthentication"])
        self.assertNotIn("serializer", user["unknown_fields"])
        reports = next(e for e in ir["endpoints"] if e["view"] == "api.views.Reports.list")
        self.assertEqual(reports["authentication"], [])
        validate(ir, source)

    def test_action_overrides_and_dynamic_getters(self):
        source = {"urls.py": '''from django.urls import path, include
from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.serializers import Serializer
class PublicSerializer(Serializer): pass
class PrivateSerializer(Serializer): pass
class Users(ModelViewSet):
    serializer_class = PrivateSerializer
    permission_classes = [IsAuthenticated]
    @action(detail=False, permission_classes=[AllowAny], serializer_class=PublicSerializer)
    def public(self, request): pass
class Dynamic(Users):
    def get_serializer_class(self): return choose()
router = SimpleRouter()
router.register("users", Users, basename="user")
router.register("dynamic", Dynamic, basename="dynamic")
urlpatterns = router.urls
'''}
        repo, _ = demo()
        ir = analyze(repo, source, [], "urls")
        action = next(e for e in ir["endpoints"] if e["view"] == "urls.Users.public")
        self.assertEqual(action["serializer"], "urls.PublicSerializer")
        self.assertEqual(action["permissions"], ["rest_framework.permissions.AllowAny"])
        dynamic = next(e for e in ir["endpoints"] if e["view"] == "urls.Dynamic.list")
        self.assertIsNone(dynamic["serializer"])
        validate(ir, source)

    def test_global_settings_only_apply_to_drf_views(self):
        repo, _ = demo()
        source = {"settings.py": 'REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.BasicAuthentication"], "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"]}',
                  "urls.py": '''from django.urls import path
from rest_framework.decorators import api_view, permission_classes
@api_view(["GET"])
def drf(request): pass
def django(request): pass
@api_view(["GET"])
@permission_classes(dynamic())
def unknown(request): pass
urlpatterns = [path("drf/", drf), path("django/", django), path("unknown/", unknown)]
'''}
        ir = analyze(repo, source, [], "urls")
        drf = next(e for e in ir["endpoints"] if e["route"] == "drf/")
        self.assertEqual(drf["authentication"], ["rest_framework.authentication.BasicAuthentication"])
        django = next(e for e in ir["endpoints"] if e["route"] == "django/")
        self.assertIsNone(django["authentication"])
        unknown = next(e for e in ir["endpoints"] if e["route"] == "unknown/")
        self.assertIsNone(unknown["permissions"])
        validate(ir, source)


if __name__ == "__main__":
    unittest.main()
