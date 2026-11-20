"""Deterministic exports from IR, with reference validation."""

import json


def validate(ir, files):
    symbols = {(s["evidence"]["file"], s["name"]) for s in ir["symbols"]}
    def visit(value):
        if isinstance(value, dict):
            if {"file", "symbol", "start_line", "end_line", "confidence"} <= value.keys():
                e = value
                if e["file"] not in files or not 1 <= e["start_line"] <= e["end_line"] <= len(files[e["file"]].splitlines()):
                    raise ValueError("Referência de arquivo/linhas inválida.")
                if e["symbol"] and (e["file"], e["symbol"]) not in symbols:
                    raise ValueError("Referência de símbolo inválida.")
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(ir)


def ref(e, repo):
    label = f"{e['file']}:{e['start_line']}-{e['end_line']}"
    if repo.get("url") and repo.get("commit_sha"):
        from urllib.parse import quote
        return f"[{label}]({repo['url']}/blob/{repo['commit_sha']}/{quote(e['file'])}#L{e['start_line']}-L{e['end_line']})"
    return f"`{label}`"


def export(ir, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis.json").write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    repo = ir["repository"]
    endpoints = ["# Mapa de rotas e métodos", "", "`scope` informa se a raiz foi selecionada ou se o prefixo permanece desconhecido. Rotas `drf_template` usam `{pk}` para o lookup padrão `[^/.]+`. HEAD/OPTIONS automáticos, API root e sufixos de formato não são enumerados. Configurações de serializer, permissões e autenticação são declarações estáticas, não provas de comportamento em runtime.", ""]
    for e in ir["endpoints"]:
        confidence = {"extracted": "Extraído", "inferred": "Inferido", "unconfirmed": "Não confirmado"}[e["confidence"]]
        endpoints.append(f"- **{confidence}**: `{e['method'] or '?'} {e['route']}` → `{e['view']}` ({e['route_kind']}; {e['scope']}).")
        endpoints.append("  Evidências: " + ", ".join(dict.fromkeys(ref(r, repo) for r in e["evidence_chain"])) + ".")
        endpoints.append("  Não confirmado: " + ", ".join(e["unknown_fields"]) + ".")
        from .reports import value_text
        for field, config in e.get("configuration", {}).items():
            endpoints.append(f"  {field}: {value_text(config['value'])}. " + ", ".join(ref(r, repo) for r in config["evidence_chain"]))
    if not ir["endpoints"]:
        endpoints.append("Nenhuma rota literal reconhecida. Isso não significa que o projeto não possui endpoints.")
    (output / "ENDPOINTS.md").write_text("\n".join(endpoints) + "\n", encoding="utf-8")
    architecture = ["# Inventário de arquitetura", "", "Nós representam arquivos Python aceitos. A organização em camadas ainda não é inferida.", "", "```mermaid", "flowchart LR"]
    pyfiles = [f for f in ir["files"] if f["language"] == "python"]
    # IDs are generated; untrusted filenames use escaped numeric entities in labels.
    for i, f in enumerate(pyfiles):
        label = "".join(c if c.isalnum() or c in "/._-" else f"#{ord(c)};" for c in f["path"])
        architecture.append(f'  f{i}["{label}"]')
    architecture.extend(["```", "", "## Imports extraídos", ""])
    for item in ir["imports"]:
        destination = f"Arquivo local: `{item['target_file']}`" if item["resolved"] else "Destino não resolvido"
        architecture.append(f"- `{item['source']}` importa `{item['target']}`. {destination}. {ref(item['evidence'], repo)}.")
    (output / "ARCHITECTURE.md").write_text("\n".join(architecture) + "\n", encoding="utf-8")
    readme = ["# Documentação extraída pelo OctorGit", "", f"Commit: `{repo.get('commit_sha') or 'não disponível — fixture local'}`.", "", "Exportação determinística, sem IA. Instruções para executar o projeto não confirmadas.", "", "## Símbolos extraídos", ""]
    if repo.get("private"):
        readme.insert(2, "Repositório privado: este documento pode conter informações internas.")
    for s in ir["symbols"]:
        readme.append(f"- `{s['name']}` ({s['kind']}) — {ref(s['evidence'], repo)}.")
    readme.extend(["", "## Cobertura", "", f"Arquivos Python lidos: {ir['metrics']['python_files_parsed']}/{ir['metrics']['python_files_accepted']}.", f"Arquivos excluídos: {ir['metrics']['skipped_files']}.", f"Lacunas registradas: {len(ir['diagnostics'])}. Consulte `analysis.json`."])
    (output / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
