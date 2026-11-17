"""Identify declared technology from accepted files; never execute project settings."""

import ast
from collections import Counter
import json
from pathlib import PurePosixPath
import re
import tomllib

LANGUAGES = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
             ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".php": "PHP", ".cs": "C#", ".rb": "Ruby", ".swift": "Swift",
             ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sql": "SQL", ".dart": "Dart", ".lua": "Lua", ".sh": "Shell"}
PACKAGES = {"django": ("framework", "Django"), "djangorestframework": ("framework", "Django REST Framework"),
            "fastapi": ("framework", "FastAPI"), "flask": ("framework", "Flask"), "react": ("framework", "React"),
            "next": ("framework", "Next.js"), "express": ("framework", "Express"), "@nestjs/core": ("framework", "NestJS"),
            "vue": ("framework", "Vue"), "celery": ("worker", "Celery"), "kafka-python": ("queue", "Kafka (cliente)"),
            "confluent-kafka": ("queue", "Kafka (cliente)"), "redis": ("cache", "Redis (cliente)"),
            "psycopg": ("driver", "PostgreSQL (driver)"), "psycopg2": ("driver", "PostgreSQL (driver)"),
            "psycopg2-binary": ("driver", "PostgreSQL (driver)"), "pymongo": ("driver", "MongoDB (driver)"),
            "mysqlclient": ("driver", "MySQL (driver)"), "sqlalchemy": ("library", "SQLAlchemy")}
IMAGES = {"postgres": ("database", "PostgreSQL"), "mysql": ("database", "MySQL"), "mariadb": ("database", "MariaDB"),
          "mongo": ("database", "MongoDB"), "redis": ("cache", "Redis"), "valkey": ("cache", "Valkey"),
          "kafka": ("queue", "Kafka"), "cp-kafka": ("queue", "Kafka"), "rabbitmq": ("queue", "RabbitMQ"),
          "nginx": ("proxy", "Nginx"), "traefik": ("proxy", "Traefik"), "haproxy": ("proxy", "HAProxy")}


def detect_technology(sources, schema_version, parser_version, inventory=None):
    components, relations, indexes = [], [], {}
    def ref(path, start, end=None):
        return {"schema_version": schema_version, "parser_version": parser_version, "file": path, "symbol": None,
                "start_line": start, "end_line": end or start, "confidence": "extracted"}
    def add(kind, name, evidence, scope, key=None):
        key = key or kind + ":" + name
        if key not in indexes:
            indexes[key] = len(components)
            components.append({"id": key, "kind": kind, "name": name, "scope": scope, "confidence": "extracted", "evidence_chain": []})
        item = components[indexes[key]]
        if evidence not in item["evidence_chain"]:
            item["evidence_chain"].append(evidence)
        return key
    def connect(source, target, evidence, kind="declared_dependency"):
        if source != target and not any(r["source"] == source and r["target"] == target and r["kind"] == kind for r in relations):
            relations.append({"source": source, "target": target, "kind": kind, "confidence": "extracted", "evidence_chain": [evidence]})
    paths = list(sources) if sources else [f["path"] for f in inventory or []]
    counts = Counter(LANGUAGES[PurePosixPath(p).suffix.lower()] for p in paths if PurePosixPath(p).suffix.lower() in LANGUAGES)
    languages = []
    for name, count in counts.most_common():
        path = next(p for p in paths if LANGUAGES.get(PurePosixPath(p).suffix.lower()) == name)
        if sources and sources[path].splitlines():
            evidence = ref(path, 1)
        else:
            evidence = None
        languages.append({"name": name, "files": count, "confidence": "inferred", "basis": "file_extension", "evidence_chain": [evidence] if evidence else []})
    app_id = "application"
    # This node is an inventory grouping, not an inferred deployment or microservice.
    components.append({"id": app_id, "kind": "application", "name": "Código do projeto", "scope": "repository", "confidence": "inferred", "evidence_chain": []})
    indexes[app_id] = 0

    def dependency(path, package, line):
        canonical = re.split(r"[<>=!~\[;\s]", package.strip(), maxsplit=1)[0].lower().replace("_", "-")
        if canonical in PACKAGES:
            kind, name = PACKAGES[canonical]
            add(kind, name, ref(path, line), "dependency")

    for path, text in sorted(sources.items()):
        if any(part.lower() in {"tests", "test", "fixtures", "examples", "docs"} for part in PurePosixPath(path).parts[:-1]):
            continue
        lines = text.splitlines()
        basename = PurePosixPath(path).name.lower()
        if basename.startswith("requirements") and basename.endswith(".txt"):
            for number, line in enumerate(lines, 1):
                if line.strip() and not line.lstrip().startswith(("#", "-")):
                    dependency(path, line, number)
        if basename == "pyproject.toml":
            try:
                project = tomllib.loads(text)
                for dep in project.get("project", {}).get("dependencies", []):
                    if isinstance(dep, str):
                        line = next((i for i, value in enumerate(lines, 1) if dep in value), 1)
                        dependency(path, dep, line)
            except (ValueError, TypeError, AttributeError):
                pass
        if basename == "package.json":
            try:
                package = json.loads(text)
                for group in ("dependencies", "devDependencies"):
                    declared = package.get(group, {})
                    for dep in declared if isinstance(declared, dict) else []:
                        dependency(path, dep, next((i for i, value in enumerate(lines, 1) if json.dumps(dep) in value), 1))
            except (ValueError, TypeError, AttributeError):
                pass
        if path.endswith(".py"):
            try:
                tree = ast.parse(text)
            except (ValueError, SyntaxError, RecursionError):
                continue
            for statement in tree.body:
                if isinstance(statement, ast.ImportFrom) and statement.module:
                    module = statement.module.split(".")[0]
                    package = {"rest_framework": "djangorestframework", "kafka": "kafka-python", "confluent_kafka": "confluent-kafka"}.get(module, module)
                    if package in PACKAGES:
                        kind, name = PACKAGES[package]
                        add(kind, name, ref(path, statement.lineno, statement.end_lineno), "import")
                elif isinstance(statement, ast.Import):
                    for alias in statement.names:
                        package = alias.name.split(".")[0].replace("_", "-")
                        if package in PACKAGES:
                            kind, name = PACKAGES[package]
                            add(kind, name, ref(path, statement.lineno, statement.end_lineno), "import")
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                if not any(isinstance(t, ast.Name) and t.id == "DATABASES" for t in targets):
                    continue
                if statement.value is None:
                    continue
                # Literal ENGINE leaves may coexist with dynamic NAME/PASSWORD; never evaluate those.
                for node in ast.walk(statement.value):
                    if isinstance(node, ast.Dict):
                        for key, value in zip(node.keys, node.values):
                            if isinstance(key, ast.Constant) and key.value == "ENGINE" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                                backend = value.value
                                mapping = {"postgresql": "PostgreSQL", "sqlite3": "SQLite", "mysql": "MySQL", "oracle": "Oracle", "mongodb": "MongoDB"}
                                name = next((v for k, v in mapping.items() if backend.rsplit(".", 1)[-1] == k), None)
                                if name:
                                    evidence = ref(path, value.lineno, value.end_lineno)
                                    target = add("database", name, evidence, "django_settings")
                                    connect(app_id, target, evidence, "database_configuration")
        if basename.startswith("dockerfile") and lines:
            for number, line in enumerate(lines, 1):
                match = re.match(r"\s*FROM\s+(?:--\S+\s+)?([^\s$]+)", line, re.I)
                if match:
                    add("infrastructure", "Docker", ref(path, number), "build_configuration")
        if basename in {"render.yaml", "render.yml"} and lines:
            add("cloud", "Render", ref(path, 1), "deployment_manifest")
        if ".github/workflows/" in path and path.endswith((".yaml", ".yml")) and lines:
            add("ci", "GitHub Actions", ref(path, 1), "ci_configuration")
        if path.endswith(".tf"):
            clean = re.sub(r"/\*.*?\*/", lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text, flags=re.S)
            for number, line in enumerate(clean.splitlines(), 1):
                match = re.match(r'\s*provider\s+"(aws|google|azurerm)"', line)
                if match:
                    add("cloud", {"aws": "AWS", "google": "Google Cloud", "azurerm": "Azure"}[match[1]], ref(path, number), "terraform_declaration")
                resource = re.match(r'\s*resource\s+"(aws_lb|aws_db_instance|aws_elasticache_cluster)"', line)
                if resource:
                    kind, name = {"aws_lb": ("proxy", "AWS Load Balancer"), "aws_db_instance": ("database", "Amazon RDS"), "aws_elasticache_cluster": ("cache", "ElastiCache")}[resource[1]]
                    add(kind, name, ref(path, number), "terraform_declaration")
        if path.endswith((".yaml", ".yml")) and re.search(r"(?m)^apiVersion:\s*\S+", text) and re.search(r"(?m)^kind:\s*(Deployment|StatefulSet|Service|Ingress)\s*$", text):
            number = next(i for i, line in enumerate(lines, 1) if line.startswith("kind:"))
            add("infrastructure", "Kubernetes", ref(path, number), "manifest")
        if not re.fullmatch(r"(?:docker-)?compose(?:\.[a-z0-9_-]+)?\.ya?ml", basename):
            continue
        # Conservative Compose subset: literal service names, images/build and depends_on.
        service_indent, current, blocks = None, None, {}
        in_services = False
        for number, line in enumerate(lines, 1):
            if re.match(r"^services:\s*(?:#.*)?$", line):
                in_services = True
                continue
            if not in_services or not line.strip() or line.lstrip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 0:
                in_services = False
                continue
            match = re.match(r"\s*([A-Za-z0-9_.-]+):\s*(?:#.*)?$", line)
            if match and (service_indent is None or indent == service_indent):
                service_indent = indent
                current = match[1]
                blocks[current] = {"line": number, "rows": []}
            elif current:
                blocks[current]["rows"].append((number, line, indent))
        ids = {}
        for name, block in blocks.items():
            kind, display, evidence = "service", name, ref(path, block["line"])
            for number, line, _ in block["rows"]:
                image = re.match(r"\s*image:\s*['\"]?([^\s'\"#$]+)", line)
                if image:
                    base = image[1].split("@", 1)[0].split(":", 1)[0].rsplit("/", 1)[-1]
                    if base in IMAGES:
                        kind, label = IMAGES[base]
                        display = f"{label} · {name}"
                    evidence = ref(path, number)
            ids[name] = add(kind, display, evidence, "compose_service", "compose:" + path + ":" + name)
        for name, block in blocks.items():
            depends_indent = None
            for number, line, indent in block["rows"]:
                if re.fullmatch(r"\s*build:\s*['\"]?\./?['\"]?\s*", line) and str(PurePosixPath(path).parent) == "." and "Dockerfile" in sources:
                    connect(app_id, ids[name], ref(path, number), "build_context")
                match = re.match(r"\s*depends_on:\s*(.*)", line)
                if match:
                    depends_indent = indent
                    inline = match[1].strip().strip("[]")
                    for target in inline.split(",") if inline else []:
                        target = target.strip().strip("'\"")
                        if target in ids:
                            connect(ids[name], ids[target], ref(path, number))
                    continue
                if depends_indent is not None:
                    if indent <= depends_indent:
                        depends_indent = None
                        continue
                    match = re.match(r"\s*(?:-\s*([A-Za-z0-9_.-]+)|([A-Za-z0-9_.-]+):\s*)$", line)
                    if match and indent <= depends_indent + 2:
                        target = match[1] or match[2]
                        if target in ids:
                            connect(ids[name], ids[target], ref(path, number))
        if blocks:
            add("infrastructure", "Docker Compose", ref(path, next(b["line"] for b in blocks.values())), "compose_manifest")
    components[0]["evidence_chain"] = [r for lang in languages for r in lang["evidence_chain"]][:4] + [r for c in components if c["kind"] == "framework" for r in c["evidence_chain"]][:4]
    return {"schema_version": schema_version, "parser_version": parser_version, "languages": languages,
            "components": components[:100], "relations": [r for r in relations if all(any(c["id"] == x for c in components[:100]) for x in (r["source"], r["target"]))],
            "limits": ["Declarações e dependências não confirmam infraestrutura em execução.", "Sem evidência não são adicionados nuvem, Kafka, balanceador ou microserviços.", "Pastas de testes, fixtures, exemplos e docs são excluídas da detecção de componentes.", "Reconhecimento limitado a regras estáticas; configurações dinâmicas podem não ser detectadas."]}
