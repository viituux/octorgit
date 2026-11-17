import copy
from pathlib import Path
import unittest

from octorgit.benchmark import compare, evaluate
from octorgit.code_parser import analyze
from octorgit.documentation import validate

REPO = {"url": None, "branch": None, "commit_sha": None, "source": "local_fixture"}
FIXTURES = Path(__file__).parent / "fixtures"


class DjangoTests(unittest.TestCase):
    def test_manual_fixture_manifests(self):
        report = evaluate(FIXTURES)
        self.assertEqual(len(report["fixtures"]), 3)
        self.assertEqual(report["totals"]["true_positive"], 20)
        self.assertEqual(report["totals"]["false_positive"], 0)
        self.assertEqual(report["totals"]["false_negative"], 0)

    def test_configured_root_and_reference_chain(self):
        from octorgit.repositories import local_snapshot
        repo, files, skipped = local_snapshot(FIXTURES / "django_nested" / "repo")
        ir = analyze(repo, files, skipped)
        self.assertEqual({e["scope"] for e in ir["endpoints"]}, {"configured_root"})
        endpoint = next(e for e in ir["endpoints"] if e["route"] == "api/internal/ping/")
        self.assertEqual(endpoint["method"], "GET")
        self.assertEqual({r["file"] for r in endpoint["evidence_chain"]}, {"config/settings.py", "config/urls.py", "api/urls.py", "api/internal/urls.py", "api/views.py"})
        validate(ir, files)
        broken = copy.deepcopy(ir)
        broken["endpoints"][0]["evidence_chain"][0]["file"] = "absent.py"
        with self.assertRaises(ValueError):
            validate(broken, files)

    def test_include_cycles_stop_with_diagnostic(self):
        files = {"urls.py": 'from django.urls import path, include\nurlpatterns = [path("loop/", include("urls"))]\n'}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual(ir["endpoints"], [])
        self.assertIn("include_cycle_or_depth_limit", {d["reason"] for d in ir["diagnostics"]})

    def test_inline_include_and_keyword_arguments(self):
        files = {"urls.py": '''from django.urls import path, include
from django.views.decorators.http import require_POST
@require_POST
def submit(request): pass
inner = [path(route="send/", view=submit)]
urlpatterns = [path("v1/", include((inner, "app")))]
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual([(e["method"], e["route"]) for e in ir["endpoints"]], [("POST", "v1/send/")])
        validate(ir, files)

    def test_reexport_resolution(self):
        files = {"urls.py": 'from django.urls import path\nfrom app import ping\nurlpatterns = [path("ping/", ping)]',
                 "app/__init__.py": "from .views import ping\n",
                 "app/views.py": "from django.views.decorators.http import require_GET\n@require_GET\ndef ping(request): pass\n"}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual(ir["endpoints"][0]["method"], "GET")
        self.assertEqual(ir["endpoints"][0]["view"], "app.views.ping")

    def test_ambiguous_roots_stay_local(self):
        files = {"one.py": 'ROOT_URLCONF = "urls"', "two.py": 'ROOT_URLCONF = "other"',
                 "urls.py": 'from django.urls import path\ndef v(r): pass\nurlpatterns = [path("a/", v)]',
                 "other.py": 'from django.urls import path\ndef v(r): pass\nurlpatterns = [path("b/", v)]'}
        ir = analyze(REPO, files, [])
        self.assertEqual({e["scope"] for e in ir["endpoints"]}, {"local_urlconf"})
        self.assertTrue(all("mounted_prefix" in e["unknown_fields"] for e in ir["endpoints"]))

    def test_custom_lookup_is_reported_without_default_pk_guess(self):
        files = {"urls.py": '''from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ModelViewSet
class Items(ModelViewSet):
    lookup_field = "slug"
router = SimpleRouter()
router.register("items", Items)
urlpatterns = router.urls
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual(ir["endpoints"], [])
        self.assertIn("custom_lookup_not_supported", {d["reason"] for d in ir["diagnostics"]})

    def test_shadowed_path_does_not_create_endpoint(self):
        files = {"urls.py": 'from django.urls import path\npath = something_else\nurlpatterns = [path("x", v)]'}
        self.assertEqual(analyze(REPO, files, [], "urls")["endpoints"], [])

    def test_api_view_class_inheritance_and_method_restrictions(self):
        files = {"urls.py": '''from django.urls import path
from rest_framework.views import APIView
class Base(APIView):
    def get(self, request): pass
    def post(self, request): pass
class Child(Base):
    http_method_names = ["post"]
urlpatterns = [path("x/", Child.as_view())]
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual([(e["method"], e["route"]) for e in ir["endpoints"]], [("POST", "x/")])
        validate(ir, files)

    def test_manual_viewset_action_mapping(self):
        files = {"urls.py": '''from django.urls import path
from rest_framework.viewsets import ViewSet
class Users(ViewSet):
    def list(self, request): pass
urlpatterns = [path("users/", Users.as_view({"get": "list"}))]
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual(ir["endpoints"][0]["method"], "GET")
        validate(ir, files)

    def test_benchmark_penalizes_duplicates_and_unknown_methods(self):
        expected = [{"method": "GET", "route": "x/"}]
        actual = [*expected, *expected, {"method": None, "route": "x/"}]
        report = compare(actual, expected)
        self.assertEqual((report["true_positive"], report["false_positive"], report["false_negative"]), (1, 2, 0))

    def test_dynamic_attribute_does_not_crash(self):
        files = {"urls.py": 'from django.urls import path\nurlpatterns = [path("x/", factory().view)]'}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual(ir["endpoints"][0]["confidence"], "unconfirmed")
        self.assertIn("view_symbol_not_resolved", {d["reason"] for d in ir["diagnostics"]})

    def test_non_viewset_action_map_is_not_confirmed(self):
        files = {"urls.py": '''from django.urls import path
class Unknown:
    def list(self, request): pass
urlpatterns = [path("x/", Unknown.as_view({"get": "list"}))]
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertIsNone(ir["endpoints"][0]["method"])

    def test_router_action_can_be_disabled(self):
        files = {"urls.py": '''from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ModelViewSet
class Users(ModelViewSet):
    list = None
router = SimpleRouter()
router.register("users", Users)
urlpatterns = router.urls
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertNotIn(("GET", "users/"), {(e["method"], e["route"]) for e in ir["endpoints"]})
        self.assertEqual(len(ir["endpoints"]), 5)

    def test_router_renderers_do_not_hide_action_route(self):
        files = {"urls.py": '''from rest_framework.routers import SimpleRouter
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
class Users(ViewSet):
    @action(detail=True, renderer_classes=[CustomRenderer])
    def highlight(self, request): pass
router = SimpleRouter()
router.register("users", Users)
urlpatterns = router.urls
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual([(e["method"], e["route"]) for e in ir["endpoints"]], [("GET", "users/{pk}/highlight/")])
        self.assertEqual(ir["endpoints"][0]["confidence"], "inferred")
        validate(ir, files)

    def test_expansion_budget(self):
        routes = ",".join('path("x/", v)' for _ in range(10001))
        files = {"urls.py": 'from django.urls import path\ndef v(r): pass\nurlpatterns = [' + routes + ']'}
        with self.assertRaisesRegex(ValueError, "Limite de expansão"):
            analyze(REPO, files, [], "urls")

    def test_keyword_method_decorators(self):
        files = {"urls.py": '''from django.urls import path
from rest_framework.decorators import api_view
from django.views.decorators.http import require_http_methods
@api_view(http_method_names=["POST"])
def create(request): pass
@require_http_methods(request_method_list=["DELETE"])
def remove(request): pass
urlpatterns = [path("create/", create), path("remove/", remove)]
'''}
        ir = analyze(REPO, files, [], "urls")
        self.assertEqual([(e["method"], e["route"]) for e in ir["endpoints"]], [("POST", "create/"), ("DELETE", "remove/")])
        validate(ir, files)


if __name__ == "__main__":
    unittest.main()
