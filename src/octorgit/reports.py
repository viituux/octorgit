"""Self-contained visual reports: escaped HTML + deterministic evidence-based SVG."""

from collections import defaultdict
from html import escape
import hashlib
import json

from .insights import build_insights, reference_key

BLUE = "#4285f4"


def h(value):
    text = ''.join(c if c in "\t\n\r" or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF else "�" for c in str(value))
    return escape(text, quote=True)


def value_text(value):
    if value is None:
        return "Não confirmado"
    if isinstance(value, list):
        return ", ".join(value) if value else "Lista vazia declarada"
    return str(value)


def svg_start(title, width, height):
    marker = "arrow-" + hashlib.sha256(title.encode()).hexdigest()[:8]
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{h(title)}"><title>{h(title)}</title>',
            f'<defs><marker id="{marker}" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="{BLUE}"/></marker></defs>',
            f'<rect width="{width}" height="{height}" rx="12" fill="#f2f5f8"/>'], marker


def label(x, y, text, size=12, color="#334452", weight="400"):
    return f'<text x="{x}" y="{y}" font-family="Segoe UI,Arial,sans-serif" font-size="{size}" fill="{color}" font-weight="{weight}">{h(text)}</text>'


def node(x, y, title, subtitle="", width=235, color="#ffffff"):
    title, subtitle = str(title), str(subtitle)
    return f'<g><title>{h(title + ": " + subtitle)}</title><rect x="{x}" y="{y}" width="{width}" height="65" rx="7" fill="{color}" stroke="#cfdbe5"/>' + label(x + 12, y + 26, title if len(title) <= 31 else "…" + title[-30:], 12, weight="600") + label(x + 12, y + 48, subtitle if len(subtitle) <= 36 else subtitle[:33] + "…", 10, "#6c8192") + "</g>"


def edge(x1, y1, x2, y2, marker):
    return f'<path d="M{x1} {y1} C{x1 + 35} {y1}, {x2 - 35} {y2}, {x2} {y2}" stroke="{BLUE}" stroke-width="1.6" fill="none" marker-end="url(#{marker})" opacity=".8"/>'


def architecture_svg(ir):
    directories = defaultdict(list)
    for file in ir["files"]:
        if file["language"] == "python":
            directories[file["path"].rpartition("/")[0] or "(raiz)"].append(file["path"])
    groups = sorted(directories.items())[:8]
    columns, group_height = min(3, max(1, len(groups))), 420
    height = max(190, ((len(groups) + columns - 1) // columns) * group_height + 90)
    parts, marker = svg_start("Arquitetura · arquivos e imports locais", columns * 330 + 10, height)
    parts.append(label(25, 30, "ARQUIVOS E IMPORTS LOCAIS", 12, weight="600"))
    positions = {}
    for i, (directory, paths) in enumerate(groups):
        x, y = 20 + i % columns * 330, 55 + i // columns * group_height
        parts.append(f'<rect x="{x}" y="{y}" width="305" height="395" rx="8" fill="#e3f3fb" stroke="#fff" stroke-width="2"/>')
        parts.append(label(x + 15, y + 25, directory[:38], 12, "#5c7a8d", "600"))
        for j, path in enumerate(paths[:4]):
            positions[path] = (x + 30, y + 45 + j * 78)
        parts.append(label(x + 15, y + 380, f"{min(4, len(paths))} de {len(paths)} arquivos mostrados", 10, "#78909f"))
    edges_seen = set()
    for relation in ir["relations"]:
        pair = relation["source"], relation["target"]
        if pair in edges_seen or pair[0] == pair[1] or any(p not in positions for p in pair):
            continue
        edges_seen.add(pair)
        a, b = positions[pair[0]], positions[pair[1]]
        if a[0] == b[0]:
            x1 = x2 = a[0] + 235
            control = x1 + 27
        elif a[0] < b[0]:
            x1, x2 = a[0] + 235, b[0]
            control = (x1 + x2) / 2
        else:
            x1, x2 = a[0], b[0] + 235
            control = (x1 + x2) / 2
        parts.append(f'<path d="M{x1} {a[1] + 33} C{control} {a[1] + 33}, {control} {b[1] + 33}, {x2} {b[1] + 33}" stroke="{BLUE}" stroke-width="1.6" fill="none" marker-end="url(#{marker})" opacity=".85"/>')
    for path, (x, y) in positions.items():
        parts.append(node(x, y, "▱ " + path.rsplit("/", 1)[-1], path))
    if not groups:
        parts.append(label(30, 90, "Nenhum arquivo Python aceito no snapshot."))
    parts.append(label(25, height - 30, "Grupos por diretório; não são camadas confirmadas.", 9, "#78909f"))
    parts.append(label(25, height - 12, "Setas: imports locais. Até 8 grupos e 4 arquivos por grupo.", 9, "#78909f"))
    return "".join(parts) + "</svg>"


def guide_svg(insights):
    steps = insights["guide"]
    parts, marker = svg_start("Guia de primeiro contato · ordem sugerida de leitura", 1000, max(190, ((len(steps) + 2) // 3) * 120 + 70))
    parts.append(label(25, 30, "ORDEM SUGERIDA DE LEITURA · INFERIDA", 12, weight="600"))
    for i, step in enumerate(steps):
        x, y = 25 + i % 3 * 330, 55 + i // 3 * 120
        if i % 3:
            parts.append(edge(x - 40, y + 33, x, y + 33, marker))
        parts.append(node(x, y, f"{i + 1:02d} · {step['title']}", step["file"], 285, "#eaf5fc" if not i else "white"))
    if not steps:
        parts.append(label(25, 90, "Pontos de entrada insuficientes. Consulte os símbolos e os diagnósticos."))
    return "".join(parts) + "</svg>"


def endpoint_svg(ir):
    grouped = {}
    for endpoint in ir["endpoints"]:
        key = endpoint["route"], endpoint["view"]
        if key not in grouped:
            grouped[key] = {"endpoint": endpoint, "methods": []}
        grouped[key]["methods"].append(endpoint["method"] or "?")
    selected = list(grouped.values())[:14]
    parts, marker = svg_start("Mapa de endpoints · configuração declarada", 1250, max(200, len(selected) * 115 + 95))
    for i, title in enumerate(("MÉTODO / ROTA", "VIEW / AÇÃO", "SERIALIZER", "PERMISSÕES / AUTENTICAÇÃO")):
        parts.append(label(22 + i * 310, 32, title, 11, "#6c8192", "600"))
    for i, group in enumerate(selected):
        endpoint, y = group["endpoint"], 55 + i * 115
        values = [(endpoint["route"] or "(raiz)", " · ".join(dict.fromkeys(group["methods"]))),
                  (endpoint["view"], "Extraído" if endpoint["confidence"] == "extracted" else "Inferido / não confirmado"),
                  (value_text(endpoint.get("serializer")), "Declaração estática"),
                  (value_text(endpoint.get("permissions")), value_text(endpoint.get("authentication")))]
        for j, (title, subtitle) in enumerate(values):
            x = 22 + j * 310
            if j:
                parts.append(edge(x - 35, y + 33, x, y + 33, marker))
            parts.append(node(x, y, title, subtitle, 275, "#e6f3fc" if j == 0 else "white"))
    if not selected:
        parts.append(label(25, 95, "Nenhum endpoint detectado; isso não prova que o projeto não tenha rotas."))
    parts.append(label(25, max(180, len(selected) * 115 + 80), f"{len(selected)} de {len(grouped)} grupos visuais. Configurações não comprovam comportamento em runtime; consulte as evidências.", 11, "#78909f"))
    return "".join(parts) + "</svg>"


def coverage_svg(insights):
    c = insights["coverage"]
    parts, _ = svg_start("Cobertura do parsing e filtros", 1000, 300)
    parts.append(label(25, 35, "COBERTURA DE PARSING ≠ PRECISÃO DE ENDPOINTS", 12, weight="600"))
    for row, (title, first, second, first_label, second_label) in enumerate([
        ("Arquivos Python aceitos", c["python_parsed"], c["python_failed"], "analisados", "erro de parsing"),
        ("Arquivos inventariados", c["accepted_files"], c["skipped_files"], "aceitos", "excluídos")]):
        y = 90 + row * 105
        total = first + second
        split = 0 if not total else round(900 * first / total, 2)
        parts.append(label(25, y - 20, title, 13, weight="600"))
        parts.append(f'<rect x="25" y="{y}" width="900" height="25" rx="4" fill="#e2e7eb"/>')
        parts.append(f'<rect x="25" y="{y}" width="{split}" height="25" rx="4" fill="{BLUE}"/>')
        parts.append(label(25, y + 48, f"{first} {first_label} · {second} {second_label} · total {total}", 12, "#6c8192"))
    return "".join(parts) + "</svg>"


def history_svg(history):
    items = list(reversed(history[:8]))
    parts, marker = svg_start("Histórico local por commit e snapshot", 1000, max(200, ((len(items) + 2) // 3) * 125 + 70))
    parts.append(label(25, 32, "VERSÕES SALVAS LOCALMENTE · ATÉ 8 NESTE DIAGRAMA", 12, weight="600"))
    for i, entry in enumerate(items):
        x, y = 25 + i % 3 * 330, 65 + i // 3 * 125
        if i % 3:
            parts.append(edge(x - 45, y + 33, x, y + 33, marker))
        sha = entry.get("commit_sha") or ("fixture · " + entry.get("fingerprint", "sem SHA"))
        parts.append(node(x, y, sha[:32], entry.get("created_at", "")[:19].replace("T", " ") + " UTC", 280))
    if not items:
        parts.append(label(25, 95, "Não há outras análises salvas para este repositório."))
    return "".join(parts) + "</svg>"


def comparison_svg(diff):
    parts, marker = svg_start("Comparação de snapshots", 1000, 270)
    parts.append(label(25, 32, "MUDANÇAS OBSERVADAS PELO PARSER", 12, weight="600"))
    if diff is None:
        parts.append(node(50, 90, "Selecione duas análises", "Mesmo repositório · versões distintas", 375, "#e5f3fc"))
        parts.append(edge(425, 123, 520, 123, marker))
        parts.append(node(520, 90, "Compare os fatos", "Rotas, configurações, arquivos e documentos", 400))
    else:
        labels = [("Adicionados", len(diff["added"]), "#e8f5e9"), ("Removidos", len(diff["removed"]), "#fceeee"), ("Revisar", len(diff["changed"]), "#fff7e6")]
        for i, (title, count, color) in enumerate(labels):
            parts.append(node(25 + 330 * i, 80, str(count) + " · " + title, "Pares método / rota detectados", 280, color))
        before = diff.get("before_sha") or diff["before_fingerprint"]
        after = diff.get("after_sha") or diff["after_fingerprint"]
        parts.append(label(25, 205, str(before)[:16] + " → " + str(after)[:16], 13, weight="600"))
        parts.append(label(25, 238, "Revisar: configuração ou arquivo de evidência mudou; não prova alteração em cada função.", 11, "#78909f"))
    return "".join(parts) + "</svg>"


def diagrams(ir, insights, history=None, diff=None):
    return {"arquitetura": architecture_svg(ir), "primeiro-contato": guide_svg(insights), "endpoints": endpoint_svg(ir),
            "cobertura": coverage_svg(insights), "historico": history_svg(history or []), "comparacao": comparison_svg(diff)}


def report_html(ir, insights=None, history=None, diff=None, ai=None):
    insights = insights or build_insights(ir)
    charts = diagrams(ir, insights, history, diff)
    repo = ir["repository"]
    title = repo.get("url") or "Exemplo / fixture local"
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'; form-action \'none\'">',
             '<title>OctorGit · Relatório visual</title><style>body{font:15px/1.7 "Segoe UI",Arial,sans-serif;background:#f4f7fa;color:#233744;margin:0}main{max-width:1160px;margin:auto;padding:35px}header{border-top:5px solid #4285f4;padding:30px;background:white}h1{font-size:34px;line-height:1.2;margin:12px 0}h2{font-size:25px;margin:10px 0}h3{font-size:17px}section{margin:28px 0;padding:28px;background:white;border:1px solid #e0e7ef;border-radius:8px;break-before:auto}svg{width:100%;height:auto}p,li{overflow-wrap:anywhere}a{color:#286bd3}nav{display:flex;flex-wrap:wrap;gap:15px;font-size:13px;margin-top:20px}.muted{font-size:12px;color:#718594}.notice{padding:15px;background:#eef5fd;border-left:3px solid #4285f4}.chart{margin:20px 0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:11px}th,td{padding:9px;border-bottom:1px solid #e2eaf1;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#f1f5fa}code,pre{font:12px/1.7 Consolas,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#142630;color:#dfecf4;padding:18px;border-radius:7px}.code-row{display:block}.number{display:inline-block;width:35px;color:#83a5bd;user-select:none}.evidence{font-size:12px;color:#5c788d}details{margin:12px 0}.stat{font-size:28px;color:#286bd3}@media print{body{background:white}main{padding:0;max-width:none}section{border:0;padding:12px 0;margin:14px 0}nav{display:none}svg{max-height:250mm}header{padding:15px 0}tr,pre{break-inside:avoid}details{display:block}a{color:#233744}h2,h3{break-after:avoid}a:after{content:none}}@page{size:A4;margin:14mm}</style></head><body><main>',
             '<header><div class="muted">OCTORGIT · RELATÓRIO VISUAL COM EVIDÊNCIAS</div><h1>Entenda o projeto,<br>confira cada origem.</h1>',
             f'<p>{h(title)}</p><p class="muted">Commit: {h(repo.get("commit_sha") or "não disponível — fixture local")} · Parser {h(ir["parser_version"])} · IR {h(ir["schema_version"])}</p>',
             '<p class="notice">Análise estática: o código não foi executado. Diagramas mostram fatos e agrupamentos indicados, sem prometer arquitetura de runtime. Abra este HTML no navegador e use Ctrl+P → Salvar como PDF para exportar com as imagens.</p><nav>']
    sections = [("guia", "Guia"), ("codigo", "Código e evidências"), ("arquitetura", "Arquitetura"), ("endpoints", "Endpoints"), ("historico", "Histórico"), ("comparacao", "Comparação"), ("cobertura", "Cobertura")]
    parts.extend(f'<a href="#{key}">{h(name)}</a>' for key, name in sections)
    parts.append('</nav></header><section id="guia"><h2>01 · Guia de primeiro contato</h2><p>Uma ordem sugerida de leitura. A organização é inferida a partir dos arquivos e referências encontrados.</p><div class="chart">' + charts["primeiro-contato"] + '</div>')
    included_snippets = {s["id"] for s in list(insights["snippets"].values())[:80]}
    def evidence(ref):
        snippet = reference_key(ref)
        if snippet not in included_snippets:
            return f'<span>{h(ref["file"])}:{ref["start_line"]}–{ref["end_line"]} (trecho fora do recorte)</span>'
        return f'<a href="#snippet-{snippet}">{h(ref["file"])}:{ref["start_line"]}–{ref["end_line"]}</a>'
    for step in insights["guide"]:
        parts.append(f'<h3>{step["order"]}. {h(step["title"])}</h3><p>{h(step["explanation"])}</p><p class="evidence">Inferido · {evidence(step["evidence"])}</p>')
    parts.append('</section><section id="arquitetura"><h2>02 · Mapa da organização</h2><p>Arquivos agrupados por diretório. As setas representam imports locais resolvidos, não chamadas de runtime ou serviços de nuvem.</p>' + charts["arquitetura"] + '</section>')
    parts.append('<section id="endpoints"><h2>03 · Mapa de endpoints</h2><p>Do caminho à view e às configurações declaradas. “Não confirmado” não significa que não exista autenticação ou serializer.</p>' + charts["endpoints"])
    parts.append('<div class="table-wrap"><table><thead><tr><th>Método / rota</th><th>View</th><th>Serializer</th><th>Permissões</th><th>Autenticação</th><th>Evidência</th></tr></thead><tbody>')
    for endpoint in ir["endpoints"][:500]:
        refs = [endpoint["evidence"]] + [r for config in endpoint.get("configuration", {}).values() for r in config["evidence_chain"]]
        parts.append('<tr>' + ''.join(f'<td>{h(value)}</td>' for value in [f'{endpoint["method"] or "?"} {endpoint["route"] or "(raiz)"}', endpoint["view"], value_text(endpoint.get("serializer")), value_text(endpoint.get("permissions")), value_text(endpoint.get("authentication"))]) + '<td>' + '<br>'.join(evidence(r) for r in refs) + '</td></tr>')
    parts.append(f'</tbody></table></div><p class="muted">{min(500, len(ir["endpoints"]))} de {len(ir["endpoints"])} registros na tabela. JSON contém todos os registros. Métodos automáticos HEAD/OPTIONS e variantes de formato permanecem fora da enumeração.</p></section>')
    parts.append('<section id="historico"><h2>04 · Histórico por commit</h2><p>Análises salvas localmente em SQLite. O histórico comprova quais snapshots foram analisados; não afirma conter todos os commits do GitHub.</p>' + charts["historico"] + '</section>')
    parts.append('<section id="comparacao"><h2>05 · Comparação e revisão de documentos</h2>' + charts["comparacao"])
    if diff is not None:
        parts.append('<p>' + h(diff["note"]) + '</p>')
        for warning in diff["warnings"]:
            parts.append('<p class="notice">' + h(warning) + '</p>')
        for name, rows in (("Rotas adicionadas", diff["added"]), ("Rotas removidas", diff["removed"])):
            parts.append('<h3>' + name + f' ({len(rows)})</h3><ul>')
            parts.extend(f'<li>{h(e["method"] or "?")} {h(e["route"])} → {h(e["view"])}</li>' for e in rows[:100])
            parts.append('</ul>')
        parts.append(f'<h3>Registros para revisão ({len(diff["changed"])})</h3><ul>')
        names = {"evidence_file_changed": "arquivo de evidência alterado", "permissions": "permissões", "authentication": "autenticação", "view": "view/ação", "confidence": "confiança"}
        parts.extend(f'<li>{h(row["after"]["method"] or "?")} {h(row["after"]["route"])}: {h(", ".join(names.get(f, f) for f in row["fields"]))}</li>' for row in diff["changed"][:100])
        parts.append('</ul><h3>Documentos que precisam de revisão</h3><ul>')
        parts.extend(f'<li><strong>{h(item["document"])}</strong>: {h(item["reason"])}</li>' for item in diff["documents_to_review"])
        parts.append('</ul><p class="muted">Até 100 itens por grupo; comparação JSON contém a lista completa.</p>')
    else:
        parts.append('<p>Ainda não há uma base selecionada. Salve duas análises do mesmo repositório e use a tela Comparar para exportar esta seção preenchida.</p>')
    parts.append('</section><section id="cobertura"><h2>06 · Relatório de cobertura</h2>' + charts["cobertura"] + '<p>' + h(insights["coverage"]["note"]) + '</p>')
    parts.append('<h3>Campos ainda não confirmados</h3><ul>')
    parts.extend(f'<li>{h(key)}: {count} de {len(ir["endpoints"])} registros</li>' for key, count in insights["coverage"]["endpoint_unknowns"].items())
    parts.append('</ul><h3>Diagnósticos</h3><ul>')
    parts.extend(f'<li>{h(d["reason"])} · {h(d["file"])}</li>' for d in ir["diagnostics"][:100])
    parts.append('</ul><h3>Exclusões inventariadas</h3><ul>')
    parts.extend(f'<li>{h(reason)}: {count}</li>' for reason, count in insights["coverage"]["skip_reasons"].items())
    parts.append('</ul></section><section id="codigo"><h2>07 · Código ao lado das evidências</h2><p>Trechos da versão analisada. Referências não incluídas neste recorte continuam no JSON e nos links por commit.</p>')
    snippets = list(insights["snippets"].values())[:80]
    for snippet in snippets:
        parts.append(f'<article id="snippet-{h(snippet["id"])}"><h3>{h(snippet["file"])}:{snippet["start_line"]}–{snippet["end_line"]}</h3><pre>')
        parts.extend(f'<span class="code-row"><span class="number">{row["number"]}</span>{h(row["text"])}</span>' for row in snippet["lines"])
        parts.append('</pre>')
        if snippet["truncated"]:
            parts.append('<p class="muted">Trecho limitado; a declaração completa pode continuar além destas linhas.</p>')
        parts.append('</article>')
    parts.append(f'<p class="muted">{len(snippets)} trechos incluídos no HTML. {h(insights["snippets_note"])}</p></section>')
    if ai and ai.get("status") == "completed":
        parts.append('<section><h2>08 · Explicações do Gemini</h2><p class="notice">Explicações inferidas. Referências por IDs foram validadas; a semântica das afirmações não é automaticamente comprovada.</p>')
        for section in ai["sections"]:
            parts.append('<h3>' + h(section["title"]) + '</h3><ul>')
            for claim in section["claims"]:
                parts.append('<li>' + h(claim["text"]) + ' <span class="evidence">' + h(claim["confidence"]) + '</span></li>')
            parts.append('</ul>')
        parts.append('</section>')
    parts.append('<footer class="muted">OctorGit · Documento independente, sem scripts, CDNs ou imagens externas. Diagramas vetoriais SVG derivados da análise. As limitações acompanham os resultados.</footer></main></body></html>')
    return ''.join(parts)
