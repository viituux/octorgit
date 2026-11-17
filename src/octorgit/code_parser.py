"""Python AST extraction. Never imports the target repository."""

import ast
import hashlib
from pathlib import PurePosixPath
from .technology import LANGUAGES, detect_technology
from . import SCHEMA_VERSION, __version__


def record(**fields):
    return {"schema_version": SCHEMA_VERSION, "parser_version": __version__, **fields}


def evidence(path, node, symbol=None):
    return record(file=path, symbol=symbol, start_line=node.lineno, end_line=node.end_lineno, confidence="extracted")


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted(node.value)
        return parent + "." + node.attr if parent else None
    return None


def literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


class Symbols(ast.NodeVisitor):
    def __init__(self, path, result):
        self.path, self.result, self.scope = path, result, []

    def visit_ClassDef(self, node):
        self.symbol(node, "class")

    def visit_FunctionDef(self, node):
        self.symbol(node, "method" if self.scope and self.scope[-1][1] == "class" else "function")

    visit_AsyncFunctionDef = visit_FunctionDef

    def symbol(self, node, kind):
        name = ".".join([s[0] for s in self.scope] + [node.name])
        self.result["symbols"].append(record(id=f"{self.path}:{name}", name=name, kind=kind, evidence=evidence(self.path, node, name)))
        self.scope.append((node.name, kind))
        self.generic_visit(node)
        self.scope.pop()


def analyze(repository, files, skipped, root_urlconf=None):
    result = record(repository=record(**repository), files=[], symbols=[], imports=[], relations=[], endpoints=[], diagnostics=[], skipped=skipped)
    python_count = parsed = 0
    trees = {}
    for path, text in sorted(files.items()):
        result["files"].append(record(path=path, language=LANGUAGES.get(PurePosixPath(path).suffix.lower(), "text").lower(), sha256=hashlib.sha256(text.encode()).hexdigest(), line_count=len(text.splitlines())))
        if not path.lower().endswith(".py"):
            continue
        python_count += 1
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, RecursionError, ValueError):
            result["diagnostics"].append(record(file=path, reason="python_parse_failed"))
            continue
        parsed += 1
        Symbols(path, result).visit(tree)
        trees[path] = tree
    result["metrics"] = {"python_files_accepted": python_count, "python_files_parsed": parsed, "parsing_coverage": parsed / python_count if python_count else None, "skipped_files": len(skipped)}
    from .django_parser import DjangoParser
    DjangoParser(trees, result).run(root_urlconf)
    result["technology"] = detect_technology(files, SCHEMA_VERSION, __version__)
    return result
