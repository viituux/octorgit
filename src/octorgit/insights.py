"""Reading guide, coverage and bounded evidence snippets derived from the IR."""

from collections import Counter, defaultdict
import hashlib
import json


def reference_key(ref):
    return hashlib.sha256(json.dumps([ref["file"], ref["start_line"], ref["end_line"]]).encode()).hexdigest()[:20]


def references(value):
    if isinstance(value, dict):
        if {"file", "start_line", "end_line", "confidence"} <= value.keys():
            yield value
        else:
            for child in value.values():
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def build_insights(ir, sources=None):
    sources = sources or {}
    guide, seen = [], set()
    def add(title, explanation, path, ref=None, confidence="inferred"):
        if path in seen or len(guide) >= 8:
            return
        file = next((f for f in ir["files"] if f["path"] == path and f["line_count"]), None)
        if not file:
            return
        seen.add(path)
        ref = ref or {"schema_version": ir["schema_version"], "parser_version": ir["parser_version"], "file": path, "symbol": None,
                      "start_line": 1, "end_line": min(file["line_count"], 10), "confidence": "extracted"}
        guide.append({"order": len(guide) + 1, "title": title, "explanation": explanation, "file": path, "confidence": confidence, "evidence": ref})
    for path in ir.get("routing", {}).get("roots", []):
        add("Comece pelas URLs", "Este arquivo foi selecionado como URLconf. Confira os prefixos e as montagens antes de seguir para as views.", path)
    for endpoint in ir["endpoints"]:
        for ref in endpoint["evidence_chain"]:
            if ref.get("symbol"):
                add("Siga para a implementação", "Uma classe ou função deste arquivo participa de uma rota detectada. Leia os métodos e as dependências declaradas.", ref["file"], ref)
        value = endpoint.get("serializer")
        if value:
            for symbol in ir["symbols"]:
                module = symbol["evidence"]["file"].removesuffix(".py").replace("/", ".")
                if module + "." + symbol["name"] == value:
                    add("Confira a representação dos dados", "Esta classe é referenciada por serializer_class. Campos calculados ou escolhas dinâmicas podem exigir leitura adicional.", symbol["evidence"]["file"], symbol["evidence"])
    for file in ir["files"]:
        if file["path"].endswith("models.py"):
            add("Investigue os modelos", "Sugestão por convenção de nome: confira aqui as estruturas de dados. O nome do arquivo, sozinho, não confirma tabelas ou relações.", file["path"])
    if not guide:
        for symbol in ir["symbols"][:4]:
            add("Conheça os símbolos do projeto", "Nenhuma entrada de roteamento foi confirmada. Este símbolo é um ponto de leitura, não uma entrada de execução comprovada.", symbol["evidence"]["file"], symbol["evidence"])

    failed = {d["file"] for d in ir["diagnostics"] if d["reason"] == "python_parse_failed"}
    groups = defaultdict(lambda: {"accepted": 0, "python": 0, "parsed": 0})
    for file in ir["files"]:
        group = file["path"].split("/")[0] if "/" in file["path"] else "(raiz)"
        groups[group]["accepted"] += 1
        if file["language"] == "python":
            groups[group]["python"] += 1
            groups[group]["parsed"] += file["path"] not in failed
    coverage = {"accepted_files": len(ir["files"]), "python_accepted": ir["metrics"]["python_files_accepted"],
                "python_parsed": ir["metrics"]["python_files_parsed"], "python_failed": len(failed),
                "skipped_files": len(ir["skipped"]), "skipped_python": sum(s["path"].endswith(".py") for s in ir["skipped"]),
                "parsing_ratio": ir["metrics"]["parsing_coverage"], "diagnostic_reasons": dict(Counter(d["reason"] for d in ir["diagnostics"])),
                "skip_reasons": dict(Counter(s["reason"] for s in ir["skipped"])),
                "endpoint_unknowns": {key: sum(e.get(key) is None for e in ir["endpoints"]) for key in ("method", "serializer", "permissions", "authentication")},
                "groups": [{"directory": name, **value} for name, value in sorted(groups.items())],
                "note": "Cobertura de parsing entre arquivos Python aceitos; não mede precisão nem recall de endpoints. Diretórios podados no modo local não são inventariados integralmente."}
    snippets, total_bytes = {}, 0
    for ref in references([guide, ir["endpoints"], ir["symbols"]]):
        key = reference_key(ref)
        if key in snippets or ref["file"] not in sources or len(snippets) >= 1500:
            continue
        lines = sources[ref["file"]].splitlines()
        start = max(1, ref["start_line"] - 2)
        end = min(len(lines), max(ref["start_line"], min(ref["end_line"], ref["start_line"] + 25)) + 2)
        rows = [{"number": i, "text": lines[i - 1][:400]} for i in range(start, end + 1)]
        size = sum(len(r["text"].encode()) for r in rows)
        if total_bytes + size > 2_000_000:
            break
        total_bytes += size
        snippets[key] = {"id": key, "evidence": ref, "file": ref["file"], "start_line": start, "end_line": end,
                         "lines": rows, "truncated": end < ref["end_line"] or any(len(lines[i - 1]) > 400 for i in range(start, end + 1))}
    return {"guide": guide, "coverage": coverage, "snippets": snippets,
            "snippets_note": "Trechos filtrados da versão analisada, com até cerca de 30 linhas por referência e limite total de 2 MB. Não contém o snapshot completo."}
