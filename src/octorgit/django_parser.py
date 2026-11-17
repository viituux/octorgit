"""Conservative Django/DRF rules over AST only; no target imports or eval."""

import ast
from .code_parser import dotted, evidence, literal, record

HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
VIEW_BASES = {"django.views.View", "django.views.generic.View", "rest_framework.views.APIView"}
ROUTERS = {"rest_framework.routers.SimpleRouter", "rest_framework.routers.DefaultRouter"}
MODEL_ACTIONS = {"list": "GET", "create": "POST", "retrieve": "GET", "update": "PUT", "partial_update": "PATCH", "destroy": "DELETE"}


def assignments(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.value, node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            yield node.target.id, node.value, node


def argument(call, index, key):
    if len(call.args) > index:
        return call.args[index]
    return next((k.value for k in call.keywords if k.arg == key), None)


class DjangoParser:
    def __init__(self, trees, result):
        self.trees, self.result = trees, result
        self.modules = {}
        for path in trees:
            name = path[:-3].replace("/", ".")
            if name.endswith(".__init__"):
                name = name[:-9]
            # Do not guess sys.path roots (src/, backend/). Select explicitly later.
            self.modules[name] = path
        self.names = {path: {} for path in trees}
        self.module_for_path = {path: module for module, path in self.modules.items()}
        self.defs = {}
        self.values = {}
        self.router_defs = {}
        self.registrations = {}
        self.urlpatterns = {}
        self.import_records = []
        self.route_visits = 0
        self.index()

    def diag(self, path, node, reason):
        item = record(file=path, reason=reason)
        if node is not None and hasattr(node, "lineno"):
            item["evidence"] = evidence(path, node)
        if item not in self.result["diagnostics"]:
            self.result["diagnostics"].append(item)

    def index(self):
        for path, tree in self.trees.items():
            module = self.module_for_path[path]
            package = module if path.endswith("/__init__.py") else module.rpartition(".")[0]
            for node in tree.body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs[module + "." + node.name] = (path, node)
                    self.names[path][node.name] = module + "." + node.name
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    if node.level:
                        pieces = package.split(".") if package else []
                        if node.level > len(pieces):
                            self.diag(path, node, "relative_import_outside_package")
                            continue
                        base = ".".join(pieces[:len(pieces) - node.level + 1] + ([base] if base else []))
                    for alias in node.names:
                        target = base + "." + alias.name
                        self.names[path][alias.asname or alias.name] = target
                        self.import_records.append((path, target, node))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.names[path][alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
                        self.import_records.append((path, alias.name, node))
            for name, value, node in assignments(tree):
                self.values[(path, name)] = (value, node)
                if name == "urlpatterns":
                    self.urlpatterns[path] = value
                # A rebinding invalidates imported/defined names for static resolution.
                self.names[path].pop(name, None)
            for node in tree.body:
                if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "urlpatterns":
                    previous = self.urlpatterns.get(path)
                    if previous is not None and isinstance(node.op, ast.Add):
                        self.urlpatterns[path] = ast.BinOp(left=previous, op=ast.Add(), right=node.value)
                    else:
                        self.diag(path, node, "dynamic_urlpatterns_not_supported")
        for path, target, node in self.import_records:
            resolved = self.locate(target)
            self.result["imports"].append(record(source=path, target=target, resolved=resolved is not None, target_file=resolved, evidence=evidence(path, node)))
            if resolved:
                self.result["relations"].append(record(source=path, target=resolved, kind="imports", evidence=evidence(path, node)))
        for (path, name), (value, node) in self.values.items():
            if isinstance(value, ast.Call) and self.resolve(path, value.func) in ROUTERS:
                kwargs = {k.arg: literal(k.value) for k in value.keywords}
                if set(kwargs) - {"trailing_slash"} or value.args or kwargs.get("trailing_slash", True) not in (True, False):
                    self.diag(path, node, "custom_router_configuration_not_supported")
                    continue
                self.router_defs[(path, name)] = (self.resolve(path, value.func), kwargs.get("trailing_slash", True), node)
                self.registrations[(path, name)] = []
        for path, tree in self.trees.items():
            for node in tree.body:
                call = node.value if isinstance(node, ast.Expr) else None
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "register" and isinstance(call.func.value, ast.Name):
                    key = (path, call.func.value.id)
                    if key in self.registrations:
                        self.registrations[key].append(call)

    def locate(self, target):
        while target:
            if target in self.modules:
                return self.modules[target]
            target = target.rpartition(".")[0]
        return None

    def resolve(self, path, node):
        name = dotted(node)
        if not name:
            return None
        head, *tail = name.split(".")
        target = self.names[path].get(head)
        if target is None:
            return None
        target = ".".join([target, *tail])
        # Resolve re-exports through local modules, with cycle protection.
        seen = set()
        while target not in seen:
            seen.add(target)
            module, _, symbol = target.rpartition(".")
            source = self.modules.get(module)
            new = self.names[source].get(symbol) if source else None
            if not new or new == target:
                break
            target = new
        return target

    def router_key(self, path, node):
        if not isinstance(node, ast.Attribute) or node.attr != "urls":
            return None
        if isinstance(node.value, ast.Name) and (path, node.value.id) in self.router_defs:
            return path, node.value.id
        target = self.resolve(path, node.value)
        if target:
            module, _, name = target.rpartition(".")
            key = self.modules.get(module), name
            if key in self.router_defs:
                return key
        return None

    def expand_list(self, path, node, seen=()):
        key = self.router_key(path, node)
        if key:
            return [("router", key)]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [("route", n) for n in node.elts]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.expand_list(path, node.left, seen) + self.expand_list(path, node.right, seen)
        if isinstance(node, ast.Name) and node.id not in seen and (path, node.id) in self.values:
            return self.expand_list(path, self.values[(path, node.id)][0], (*seen, node.id))
        self.diag(path, node, "dynamic_urlpatterns_not_supported")
        return []

    def run(self, root_urlconf=None):
        roots = []
        if root_urlconf:
            if root_urlconf not in self.modules:
                raise ValueError("--root-urlconf não corresponde a um módulo Python analisado.")
            roots = [(self.modules[root_urlconf], [], "explicit_root")]
        else:
            configured = {}
            for (path, name), (value, node) in self.values.items():
                if name == "ROOT_URLCONF" and not isinstance(literal(value), str):
                    self.diag(path, node, "dynamic_root_urlconf_not_supported")
                elif name == "ROOT_URLCONF" and isinstance(literal(value), str):
                    target = self.modules.get(literal(value))
                    if target:
                        configured.setdefault(target, []).append(evidence(path, node))
                    else:
                        self.diag(path, node, "root_urlconf_module_not_found")
            if len(configured) == 1:
                path, refs = next(iter(configured.items()))
                roots = [(path, refs, "configured_root")]
            else:
                if len(configured) > 1:
                    self.diag(next(iter(configured)), None, "multiple_root_urlconfs_select_explicitly")
                roots = [(path, [], "local_urlconf") for path in sorted(self.urlpatterns)]
        self.result["routing"] = record(roots=[p for p, _, _ in roots], root_selection="explicit" if root_urlconf else "settings_or_local", automatic_methods="HEAD and OPTIONS not enumerated")
        for path, refs, scope in roots:
            if path not in self.urlpatterns:
                self.diag(path, None, "root_urlpatterns_not_found")
                continue
            self.walk_urls(path, self.urlpatterns[path], "", refs, (), scope)

    def walk_urls(self, path, value, prefix, refs, stack, scope):
        current = (path, id(value))
        if current in stack or len(stack) >= 32:
            self.diag(path, value, "include_cycle_or_depth_limit")
            return
        for kind, node in self.expand_list(path, value):
            self.route_visits += 1
            if self.route_visits > 10000:
                raise ValueError("Limite de expansão de rotas excedido.")
            if kind == "router":
                self.emit_router(node, prefix, refs, scope)
                continue
            if not isinstance(node, ast.Call) or self.resolve(path, node.func) not in {"django.urls.path", "django.urls.re_path"}:
                self.diag(path, node, "dynamic_route_not_supported")
                continue
            route = literal(argument(node, 0, "route"))
            view = argument(node, 1, "view")
            if not isinstance(route, str) or view is None:
                self.diag(path, node, "dynamic_route_not_supported")
                continue
            regex = self.resolve(path, node.func) == "django.urls.re_path"
            if regex and prefix:
                self.diag(path, node, "nested_regex_not_supported")
                continue
            route_refs = refs + [evidence(path, node)]
            if isinstance(view, ast.Call) and self.resolve(path, view.func) == "django.urls.include":
                if regex:
                    self.diag(path, node, "regex_include_not_supported")
                    continue
                included = argument(view, 0, "arg")
                if isinstance(included, ast.Tuple) and included.elts:
                    included = included.elts[0]
                module = literal(included)
                if isinstance(module, str):
                    child = self.modules.get(module)
                    if not child or child not in self.urlpatterns:
                        self.diag(path, node, "include_module_not_found")
                    else:
                        self.walk_urls(child, self.urlpatterns[child], prefix + route, route_refs, (*stack, current), scope)
                elif self.router_key(path, included):
                    self.emit_router(self.router_key(path, included), prefix + route, route_refs, scope)
                elif isinstance(included, (ast.List, ast.Name, ast.BinOp)):
                    # Inline patterns do not cross module boundaries.
                    self.walk_urls(path, included, prefix + route, route_refs, (*stack, current), scope)
                else:
                    self.diag(path, node, "dynamic_include_not_supported")
                continue
            target = self.resolve(path, view)
            action_mapping = None
            if isinstance(view, ast.Call) and isinstance(view.func, ast.Attribute) and view.func.attr == "as_view":
                target = self.resolve(path, view.func.value)
                if view.args:
                    action_mapping = literal(view.args[0])
                if any(k.arg not in {"name", "suffix", "detail", "basename", "url_name"} for k in view.keywords):
                    self.diag(path, node, "as_view_overrides_not_supported")
                    continue
            if not target:
                self.diag(path, node, "view_symbol_not_resolved")
            methods = self.view_methods(target, action_mapping)
            if not methods:
                methods = [(None, [], "unconfirmed")]
            for method, method_refs, confidence in methods:
                action = action_mapping.get(method.lower()) if isinstance(action_mapping, dict) and method else None
                responsible = target + "." + action if target and action else target
                self.emit(prefix + route, responsible or dotted(view) or "unresolved", method, path, node, route_refs + method_refs, scope, "regex" if regex else "path", confidence)

    def hierarchy(self, target, seen=()):
        if target in seen or len(seen) >= 24 or target not in self.defs:
            return []
        path, node = self.defs[target]
        if not isinstance(node, ast.ClassDef):
            return []
        items = [(target, path, node)]
        for base in node.bases:
            items.extend(self.hierarchy(self.resolve(path, base), (*seen, target)))
        return items

    def view_methods(self, target, mapping=None):
        definition = self.defs.get(target)
        if not definition:
            return []
        path, node = definition
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                func = dec.func if isinstance(dec, ast.Call) else dec
                name = self.resolve(path, func)
                methods = None
                if name in {"rest_framework.decorators.api_view", "django.views.decorators.http.require_http_methods"} and isinstance(dec, ast.Call):
                    key = "http_method_names" if name.endswith("api_view") else "request_method_list"
                    methods = literal(argument(dec, 0, key))
                    if methods is None and name.endswith("api_view") and (not dec.args and not dec.keywords or isinstance(argument(dec, 0, key), ast.Constant) and argument(dec, 0, key).value is None):
                        methods = ["GET"]
                elif name == "django.views.decorators.http.require_GET":
                    methods = ["GET"]
                elif name == "django.views.decorators.http.require_POST":
                    methods = ["POST"]
                elif name == "django.views.decorators.http.require_safe":
                    methods = ["GET", "HEAD"]
                if isinstance(methods, (list, tuple)) and all(isinstance(m, str) and m.lower() in HTTP for m in methods):
                    return [(m.upper(), [evidence(path, dec, node.name)], "extracted") for m in dict.fromkeys(methods)]
            return []
        hierarchy = self.hierarchy(target)
        bases = {self.resolve(p, b) for _, p, n in hierarchy for b in n.bases}
        if mapping is not None:
            if not bases & {"rest_framework.viewsets.ViewSet", "rest_framework.viewsets.GenericViewSet", "rest_framework.viewsets.ModelViewSet", "rest_framework.viewsets.ReadOnlyModelViewSet"}:
                self.diag(path, node, "action_mapping_requires_known_viewset")
                return []
            if not isinstance(mapping, dict) or not all(isinstance(k, str) and k.lower() in HTTP and isinstance(v, str) for k, v in mapping.items()):
                self.diag(path, node, "dynamic_action_mapping_not_supported")
                return []
            result = []
            for method, action in mapping.items():
                for _, p, n in hierarchy:
                    match = next((m for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == action), None)
                    if match:
                        result.append((method.upper(), [evidence(p, match, n.name + "." + match.name)], "extracted"))
                        break
            return result
        if not bases & VIEW_BASES:
            return []
        members = {}
        for _, p, n in hierarchy:
            for member in n.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.setdefault(member.name, (p, n.name, member))
        if "dispatch" in members or "as_view" in members:
            self.diag(path, node, "custom_dispatch_not_supported")
            return []
        allowed = HTTP
        for _, p, n in hierarchy:
            restriction = next(((v, a) for name, v, a in assignments(n) if name == "http_method_names"), None)
            if restriction:
                methods = literal(restriction[0])
                if not isinstance(methods, (list, tuple)) or not all(isinstance(m, str) for m in methods):
                    return []
                allowed = {m.lower() for m in methods} & HTTP
                break
        return [(name.upper(), [evidence(p, m, cls + "." + name)], "extracted") for name, (p, cls, m) in members.items() if name in allowed]

    def emit(self, route, view, method, path, node, refs, scope, route_kind="path", confidence="extracted"):
        details = self.endpoint_details(view)
        unknown = [key for key, value in details.items() if value["value"] is None]
        if method is None:
            unknown.append("method")
        if scope == "local_urlconf":
            unknown.append("mounted_prefix")
        self.result["endpoints"].append(record(route=route, route_kind=route_kind, view=view, method=method,
            serializer=details["serializer"]["value"], authentication=details["authentication"]["value"], permissions=details["permissions"]["value"],
            configuration=details, scope=scope, confidence=confidence, evidence=evidence(path, node), evidence_chain=refs, unknown_fields=unknown))

    def endpoint_details(self, target):
        result = {name: record(value=None, confidence="unconfirmed", evidence_chain=[]) for name in ("serializer", "permissions", "authentication")}
        action = None
        if target not in self.defs and target and target.rpartition(".")[0] in self.defs:
            target, _, action = target.rpartition(".")
        if target not in self.defs:
            return result
        path, definition = self.defs[target]
        attrs = {"serializer": "serializer_class", "permissions": "permission_classes", "authentication": "authentication_classes"}
        getters = {"serializer": "get_serializer_class", "permissions": "get_permissions", "authentication": "get_authenticators"}
        hierarchy = self.hierarchy(target)
        bases = {self.resolve(p, b) for _, p, n in hierarchy for b in n.bases}
        drf = any(b and b.startswith("rest_framework.") for b in bases)
        declared_function_fields = set()

        def extract(field, p, value, ref):
            if field == "serializer":
                resolved = self.resolve(p, value)
            elif isinstance(value, (ast.List, ast.Tuple)):
                resolved = [self.resolve(p, item) for item in value.elts]
                if not all(resolved):
                    resolved = None
            else:
                resolved = None
            if resolved is not None:
                result[field] = record(value=resolved, confidence="extracted", evidence_chain=[ref])

        if isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in definition.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                name = self.resolve(path, dec.func)
                if name == "rest_framework.decorators.api_view":
                    drf = True
                for field in ("permissions", "authentication"):
                    if name == "rest_framework.decorators." + attrs[field]:
                        declared_function_fields.add(field)
                        extract(field, path, argument(dec, 0, attrs[field]), evidence(path, dec, definition.name))
        else:
            for field, attribute in attrs.items():
                dynamic = next(((p, cls) for _, p, cls in hierarchy if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == getters[field] for n in cls.body)), None)
                if dynamic:
                    self.diag(dynamic[0], dynamic[1], "dynamic_" + attribute + "_not_supported")
                    continue
                for _, p, cls in hierarchy:
                    # Dynamic getter overrides prevent a claim about effective configuration.
                    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == getters[field] for n in cls.body):
                        self.diag(p, cls, "dynamic_" + attribute + "_not_supported")
                        break
                    override = None
                    if action:
                        method = next((n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == action), None)
                        if method:
                            for dec in method.decorator_list:
                                if isinstance(dec, ast.Call) and self.resolve(p, dec.func) == "rest_framework.decorators.action":
                                    override = next((k.value for k in dec.keywords if k.arg == attribute), None)
                                    if override is not None:
                                        extract(field, p, override, evidence(p, dec, cls.name + "." + action))
                    if override is not None:
                        break
                    assignment = next(((value, node) for name, value, node in assignments(cls) if name == attribute), None)
                    if assignment:
                        extract(field, p, assignment[0], evidence(p, assignment[1], cls.name))
                        break
        # Only explicit, unique literal REST_FRAMEWORK defaults. Never apply DRF defaults to Django views.
        defaults = [(p, value, node) for (p, name), (value, node) in self.values.items() if name == "REST_FRAMEWORK"]
        if drf and len(defaults) == 1:
            p, value, node = defaults[0]
            if isinstance(value, ast.Dict):
                config = {literal(k): v for k, v in zip(value.keys, value.values) if k is not None and isinstance(literal(k), str)}
                for field, key in (("permissions", "DEFAULT_PERMISSION_CLASSES"), ("authentication", "DEFAULT_AUTHENTICATION_CLASSES")):
                    if result[field]["value"] is None and key in config:
                        # Do not bypass a dynamic getter/local declaration with a global default.
                        blocked = field in declared_function_fields or any(any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == getters[field] for n in cls.body) or any(name == attrs[field] for name, _, _ in assignments(cls)) for _, _, cls in hierarchy)
                        values = literal(config[key])
                        if not blocked and isinstance(values, (list, tuple)) and all(isinstance(v, str) for v in values):
                            result[field] = record(value=list(values), confidence="extracted", evidence_chain=[evidence(p, node)])
        return result

    def emit_router(self, key, prefix, refs, scope):
        kind, slash, constructor = self.router_defs[key]
        path, _ = key
        if kind.endswith("DefaultRouter"):
            self.diag(path, constructor, "default_router_api_root_and_format_suffix_not_enumerated")
        for registration in self.registrations[key]:
            route = literal(argument(registration, 0, "prefix"))
            target = self.resolve(path, argument(registration, 1, "viewset"))
            if not isinstance(route, str) or not target:
                self.diag(path, registration, "dynamic_router_registration_not_supported")
                continue
            hierarchy = self.hierarchy(target)
            bases = {self.resolve(p, b) for _, p, n in hierarchy for b in n.bases}
            if "rest_framework.viewsets.ModelViewSet" in bases:
                actions = dict(MODEL_ACTIONS)
            elif "rest_framework.viewsets.ReadOnlyModelViewSet" in bases:
                actions = {"list": "GET", "retrieve": "GET"}
            elif bases & {"rest_framework.viewsets.ViewSet", "rest_framework.viewsets.GenericViewSet"}:
                actions = {}
            else:
                self.diag(path, registration, "viewset_base_not_supported")
                continue
            mixins = {"ListModelMixin": "list", "CreateModelMixin": "create", "RetrieveModelMixin": "retrieve", "UpdateModelMixin": "update", "DestroyModelMixin": "destroy"}
            for base in bases:
                if base and base.startswith("rest_framework.mixins.") and base.rsplit(".", 1)[-1] in mixins:
                    action = mixins[base.rsplit(".", 1)[-1]]
                    actions[action] = MODEL_ACTIONS[action]
                    if action == "update":
                        actions["partial_update"] = "PATCH"
            members, attrs = {}, {}
            class_refs = []
            for _, p, n in hierarchy:
                class_refs.append(evidence(p, n, n.name))
                for member in n.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        members.setdefault(member.name, (p, n, member))
                for name, value, assignment in assignments(n):
                    attrs.setdefault(name, (literal(value), p, assignment))
            if any(n in members for n in ("get_routes", "get_extra_actions", "as_view", "dispatch")):
                self.diag(path, registration, "custom_viewset_dispatch_not_supported")
                continue
            if any(n in attrs for n in ("lookup_field", "lookup_url_kwarg", "lookup_value_regex", "lookup_value_converter")):
                self.diag(path, registration, "custom_lookup_not_supported")
                continue
            if "http_method_names" in attrs:
                allowed = attrs["http_method_names"][0]
                if not isinstance(allowed, (list, tuple)) or not all(isinstance(m, str) for m in allowed):
                    self.diag(path, registration, "dynamic_http_method_names_not_supported")
                    continue
                allowed = {m.upper() for m in allowed}
            else:
                allowed = {m.upper() for m in HTTP}
            for action, method in MODEL_ACTIONS.items():
                if action in members:
                    actions[action] = method
                elif action in attrs:
                    actions.pop(action, None)
                    if attrs[action][0] is not None:
                        self.diag(path, registration, "dynamic_action_override_not_supported")
            router_refs = refs + [evidence(path, constructor), evidence(path, registration)] + class_refs
            suffix = "/" if slash else ""
            for action, method in actions.items():
                if method not in allowed:
                    continue
                detail = action not in {"list", "create"}
                # DRF's default lookup uses [^/.]+, not Django's <str:pk>.
                route_text = prefix + route + ("/{pk}" if detail else "") + suffix
                action_refs = []
                if action in members:
                    p, cls, member = members[action]
                    action_refs = [evidence(p, member, cls.name + "." + member.name)]
                self.emit(route_text, target + "." + action, method, path, registration, router_refs + action_refs, scope, "drf_template", "inferred")
            for name, (p, cls, member) in members.items():
                for decorator in member.decorator_list:
                    if not isinstance(decorator, ast.Call) or self.resolve(p, decorator.func) != "rest_framework.decorators.action":
                        continue
                    kwargs = {k.arg: literal(k.value) for k in decorator.keywords}
                    detail, methods = kwargs.get("detail"), kwargs.get("methods", ["get"])
                    url_path = kwargs.get("url_path", name)
                    safe_options = {"detail", "methods", "url_path", "url_name", "renderer_classes", "permission_classes", "authentication_classes", "serializer_class", "throttle_classes", "filter_backends", "pagination_class"}
                    if not isinstance(detail, bool) or not isinstance(methods, (list, tuple)) or not all(isinstance(m, str) and m.lower() in HTTP for m in methods) or not isinstance(url_path, str) or set(kwargs) - safe_options:
                        self.diag(p, decorator, "custom_action_not_supported")
                        continue
                    for method in dict.fromkeys(m.upper() for m in methods):
                        if method in allowed:
                            self.emit(prefix + route + ("/{pk}" if detail else "") + "/" + url_path + suffix, target + "." + name, method, path, registration, router_refs + [evidence(p, decorator, cls.name + "." + name)], scope, "drf_template", "inferred")
