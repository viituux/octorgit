import argparse
from pathlib import Path
import sys
import tarfile
import urllib.error

from .repositories import github_snapshot, local_snapshot
from .code_parser import analyze
from .documentation import export, validate


def main(argv=None):
    parser = argparse.ArgumentParser(description="OctorGit — análise estática de Python/Django, sem executar o repositório.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="URL pública https://github.com/owner/repo")
    source.add_argument("--local", type=Path, help="Diretório de fixture local; sem SHA de commit")
    parser.add_argument("--branch", help="Branch/tag/ref; padrão: branch padrão do GitHub")
    parser.add_argument("--root-urlconf", help="Módulo raiz de URLs, por exemplo config.urls; evita prefixos ambíguos")
    parser.add_argument("--gemini", action="store_true", help="Enviar contexto selecionado da IR ao Google Gemini (exige GEMINI_API_KEY)")
    parser.add_argument("--output", type=Path, required=True, help="Diretório novo ou vazio para os resultados")
    args = parser.parse_args(argv)
    try:
        if args.local and args.branch:
            raise ValueError("--branch só pode ser usado com --repo.")
        if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
            raise ValueError("O diretório de saída deve estar vazio para evitar sobrescrita.")
        if args.local and args.output.resolve().is_relative_to(args.local.resolve()):
            raise ValueError("Use um diretório de saída fora do repositório de entrada.")
        repo, files, skipped = github_snapshot(args.repo, args.branch) if args.repo else local_snapshot(args.local)
        ir = analyze(repo, files, skipped, root_urlconf=args.root_urlconf)
        validate(ir, files)
        export(ir, args.output)
        ai_result = None
        if args.gemini:
            import json
            from .ai_engine import AIError, DocumentationEngine, GeminiProvider, render_markdown
            try:
                result = DocumentationEngine().generate(ir, GeminiProvider())
                ai_result = result
                (args.output / "AI.md").write_text(render_markdown(result, repo), encoding="utf-8")
                (args.output / "AI.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("Documentação Gemini gerada com referências verificadas; afirmações continuam inferidas.")
            except AIError as exc:
                print(f"Gemini: {exc} A exportação estática está disponível.", file=sys.stderr)
        from .insights import build_insights
        from .reports import report_html, diagrams
        insights = build_insights(ir, files)
        (args.output / "RELATORIO.html").write_text(report_html(ir, insights, ai=ai_result), encoding="utf-8")
        diagrams_dir = args.output / "diagramas"
        diagrams_dir.mkdir()
        for name, svg in diagrams(ir, insights).items():
            (diagrams_dir / (name + ".svg")).write_text(svg, encoding="utf-8")
    except ValueError as exc:
        print(f"Entrada ou análise inválida: {exc}", file=sys.stderr)
        return 1
    except (OSError, urllib.error.URLError, KeyError, tarfile.TarError, EOFError) as exc:
        print(f"Não foi possível concluir a análise ({type(exc).__name__}). Verifique entrada, limites e conexão. Nenhum código foi executado.", file=sys.stderr)
        return 1
    print(f"Análise concluída: {len(ir['symbols'])} símbolos, {len(ir['endpoints'])} registros de rotas/métodos; {len(ir['diagnostics'])} lacunas. Saída: {args.output}")
    return 0
