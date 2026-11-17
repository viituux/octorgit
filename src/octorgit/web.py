"""Local browser UI. Bind only to loopback; never serve this as a public service."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files as resources
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tarfile
import tempfile
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
import webbrowser
import zipfile

from . import __version__
from .code_parser import analyze
from .documentation import export, validate
from .repositories import github_snapshot
from .ai_engine import AIError, DocumentationEngine, GeminiProvider, render_markdown, settings
from .history import HistoryStore, compare_analyses, metadata, repository_identity, snapshot_fingerprint
from .insights import build_insights
from .reports import diagrams, report_html

DOCUMENTS = ("README.md", "ENDPOINTS.md", "ARCHITECTURE.md", "analysis.json")


class BusyError(Exception):
    pass


class Jobs:
    def __init__(self, store=None):
        self.lock = threading.Lock()
        self.items = {}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="octorgit")
        self.ai_engine = DocumentationEngine()
        self.store = store

    def submit(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Informe os dados da análise em JSON.")
        if set(payload) - {"source", "repo", "branch", "root_urlconf", "use_ai"}:
            raise ValueError("Opção de análise não reconhecida.")
        source = payload.get("source", "github")
        if not isinstance(payload.get("use_ai", False), bool):
            raise ValueError("A opção Gemini deve ser verdadeira ou falsa.")
        if payload.get("use_ai") and not settings()["configured"]:
            raise ValueError("Configure GEMINI_API_KEY no Windows e reinicie o aplicativo para usar o Gemini.")
        if source not in {"github", "demo", "demo-next"}:
            raise ValueError("Escolha GitHub ou exemplo integrado.")
        for key in ("repo", "branch", "root_urlconf"):
            if key in payload and (not isinstance(payload[key], str) or len(payload[key]) > 300):
                raise ValueError("Campos devem ser textos de até 300 caracteres.")
        if source == "github":
            import re
            if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/)?", payload.get("repo", "")):
                raise ValueError("Use uma URL pública no formato https://github.com/autor/repositorio.")
        with self.lock:
            if any(j["status"] in {"queued", "running"} for j in self.items.values()):
                raise BusyError("Uma análise já está em andamento. Aguarde sua conclusão.")
            while len(self.items) >= 8:
                del self.items[next(iter(self.items))]
            job_id = secrets.token_hex(12)
            job = {"id": job_id, "status": "queued", "progress": 0, "stage": "Preparando análise",
                   "created_at": datetime.now(timezone.utc).isoformat(), "source": source,
                   "label": ("Exemplo Django/DRF · alterado" if source == "demo-next" else "Exemplo Django/DRF") if source.startswith("demo") else payload["repo"].removeprefix("https://github.com/"),
                   "error": None}
            self.items[job_id] = job
        self.pool.submit(self.run, job_id, dict(payload))
        return self.get(job_id)

    def update(self, job_id, **fields):
        with self.lock:
            self.items[job_id].update(fields)
            if self.store and fields.get("status") in {"completed", "failed"}:
                try:
                    self.store.save(self.items[job_id])
                except (sqlite3.Error, OSError):
                    self.items[job_id]["storage_error"] = "Não foi possível salvar o histórico em disco. Exporte o resultado antes de encerrar."

    def full(self, job_id):
        with self.lock:
            job = self.items.get(job_id)
        return job or (self.store.get(job_id) if self.store else None)

    def get(self, job_id):
        job = self.full(job_id)
        return metadata(job) if job else None

    def list(self):
        stored = {j["id"]: j for j in self.store.list()} if self.store else {}
        with self.lock:
            stored.update({j["id"]: metadata(j) for j in self.items.values()})
        return sorted(stored.values(), key=lambda j: j["created_at"], reverse=True)[:100]

    def result(self, job_id):
        job = self.full(job_id)
        if job and job["status"] == "completed":
            history = [entry for entry in self.list() if entry.get("repository_id") == job.get("repository_id") and entry["status"] == "completed"]
            previous = next((entry for entry in history if entry["id"] != job_id and entry["created_at"] < job["created_at"] and entry.get("fingerprint") != job.get("fingerprint")), None)
            return {"analysis": job["ir"], "documents": job["documents"], "ai": job["ai_result"],
                    "insights": job["insights"], "history": history, "previous_id": previous["id"] if previous else None, "storage_error": job.get("storage_error")}
        return None

    def visual_context(self, job_id, base_id=None):
        result = self.result(job_id)
        if not result:
            raise ValueError("Análise concluída não encontrada.")
        base_id = None if base_id == "none" else (base_id or result["previous_id"])
        diff = None
        if base_id:
            before = self.result(base_id)
            if not before:
                raise ValueError("Análise de base não encontrada.")
            diff = compare_analyses(before["analysis"], result["analysis"])
            diff.update(base_id=base_id, after_id=job_id)
        return result, diff

    def run(self, job_id, payload):
        try:
            self.update(job_id, status="running", progress=10, stage="Lendo snapshot do repositório")
            if payload.get("source", "").startswith("demo"):
                demo = resources("octorgit").joinpath("static/demo.json").read_text(encoding="utf-8")
                snapshot = json.loads(demo)
                repository, source, skipped = snapshot["repository"], snapshot["files"], []
                if payload["source"] == "demo-next":
                    source["config/urls.py"] = source["config/urls.py"].replace('"health/"', '"status/"')
                    source["api/views.py"] = source["api/views.py"].replace("permission_classes = [IsAuthenticated]", "permission_classes = [AllowAny]")
                root_urlconf = "config.urls"
            else:
                repository, source, skipped = github_snapshot(payload["repo"], payload.get("branch") or None)
                root_urlconf = payload.get("root_urlconf") or None
            self.update(job_id, progress=45, stage="Extraindo símbolos e resolvendo rotas")
            ir = analyze(repository, source, skipped, root_urlconf=root_urlconf)
            self.update(job_id, progress=75, stage="Validando referências e evidências")
            validate(ir, source)
            insights = build_insights(ir, source)
            ai_result = {"status": "disabled"}
            if payload.get("use_ai"):
                self.update(job_id, progress=85, stage="Gerando explicações com Gemini e validando referências")
                try:
                    ai_result = self.ai_engine.generate(ir, GeminiProvider())
                except AIError as exc:
                    ai_result = {"status": "failed", "error": str(exc)}
            self.update(job_id, progress=95, stage="Preparando documentos para exportação")
            with tempfile.TemporaryDirectory(prefix="octorgit-") as directory:
                output = Path(directory)
                export(ir, output)
                documents = {name: (output / name).read_text(encoding="utf-8") for name in DOCUMENTS}
            if ai_result["status"] == "completed":
                documents["AI.md"] = render_markdown(ai_result, repository)
                documents["AI.json"] = json.dumps(ai_result, indent=2, ensure_ascii=False) + "\n"
            self.update(job_id, status="completed", progress=100, stage="Análise concluída", ir=ir, documents=documents, ai_result=ai_result, insights=insights,
                        repository_id=repository_identity(ir), repository_url=repository.get("url"), commit_sha=repository.get("commit_sha"), fingerprint=snapshot_fingerprint(ir),
                        summary={"files": len(ir["files"]), "symbols": len(ir["symbols"]), "endpoints": len(ir["endpoints"]), "diagnostics": len(ir["diagnostics"])})
        except HTTPError as exc:
            message = {403: "O GitHub limitou as requisições. Aguarde e tente novamente.",
                       404: "Repositório público ou branch não encontrado.",
                       429: "Limite de requisições do GitHub atingido. Tente mais tarde."}.get(exc.code, "O GitHub não conseguiu fornecer o snapshot. Tente novamente.")
            self.update(job_id, status="failed", stage="Análise interrompida", error=message)
        except ValueError as exc:
            self.update(job_id, status="failed", stage="Análise interrompida", error=str(exc))
        except (OSError, URLError, tarfile.TarError, EOFError, KeyError, RecursionError):
            self.update(job_id, status="failed", stage="Análise interrompida", error="Não foi possível ler o snapshot. Verifique a conexão, o tamanho e a compatibilidade do projeto.")
        except Exception:
            self.update(job_id, status="failed", stage="Análise interrompida", error="A análise encontrou uma estrutura ainda não suportada. Experimente outro repositório.")

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765, data_dir=None):
        super().__init__(("127.0.0.1", port), Handler)
        self.jobs = Jobs(HistoryStore(data_dir) if data_dir is not None else None)
        self.csrf = secrets.token_urlsafe(32)
        port = self.server_address[1]
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    def server_close(self):
        super().server_close()
        if hasattr(self, "jobs"):
            self.jobs.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "OctorGitLocal"

    def log_message(self, *args):
        # Do not log repository URLs, source contents or session tokens.
        pass

    def respond(self, status, content, content_type="application/json; charset=utf-8", filename=None, standalone=False):
        if not isinstance(content, bytes):
            content = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'" if standalone else "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def json(self, status, data):
        self.respond(status, json.dumps(data, ensure_ascii=False))

    def trusted(self):
        if self.headers.get("Host") not in self.server.hosts:
            self.json(403, {"error": "Endereço local não permitido."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in self.server.hosts}:
            self.json(403, {"error": "Origem não permitida."})
            return False
        return True

    def do_GET(self):
        if not self.trusted():
            return
        path = urlsplit(self.path).path
        if path in {"/", "/app.js", "/style.css"}:
            name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[path]
            body = resources("octorgit").joinpath("static/" + name).read_text(encoding="utf-8")
            if name == "index.html":
                body = body.replace("__CSRF__", self.server.csrf).replace("__VERSION__", __version__)
            mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
            self.respond(200, body, mime + "; charset=utf-8")
            return
        if path == "/api/jobs":
            self.json(200, {"jobs": self.server.jobs.list()})
            return
        if path == "/api/config":
            self.json(200, {"ai": settings(), "persistent_history": self.server.jobs.store is not None})
            return
        parts = path.strip("/").split("/")
        if len(parts) in {3, 4, 5} and parts[:2] == ["api", "jobs"]:
            job = self.server.jobs.get(parts[2])
            if not job:
                self.json(404, {"error": "Análise não encontrada nesta sessão."})
                return
            if len(parts) == 3:
                self.json(200, job)
                return
            result = self.server.jobs.result(parts[2])
            if result is None:
                self.json(409, {"error": "A análise ainda não está disponível."})
                return
            if parts[3:] == ["result"]:
                self.json(200, result)
                return
            if parts[3:] in (["report"], ["compare"]) or len(parts) == 5 and parts[3] == "diagrams":
                base_id = parse_qs(urlsplit(self.path).query).get("base", [None])[0]
                try:
                    visual, diff = self.server.jobs.visual_context(parts[2], base_id)
                except ValueError as exc:
                    self.json(400, {"error": str(exc)})
                    return
                if parts[3:] == ["compare"]:
                    self.json(200, {"comparison": diff})
                elif parts[3:] == ["report"]:
                    body = report_html(visual["analysis"], visual["insights"], visual["history"], diff, visual["ai"])
                    download = "download" in parse_qs(urlsplit(self.path).query)
                    self.respond(200, body, "text/html; charset=utf-8", "RELATORIO.html" if download else None, standalone=True)
                else:
                    name = parts[4].removesuffix(".svg")
                    charts = diagrams(visual["analysis"], visual["insights"], visual["history"], diff)
                    if name not in charts:
                        self.json(404, {"error": "Diagrama não encontrado."})
                    else:
                        self.respond(200, charts[name], "image/svg+xml; charset=utf-8", name + ".svg" if "download" in parse_qs(urlsplit(self.path).query) else None)
                return
            if parts[3:] == ["download"]:
                try:
                    visual, diff = self.server.jobs.visual_context(parts[2], parse_qs(urlsplit(self.path).query).get("base", [None])[0])
                except ValueError as exc:
                    self.json(400, {"error": str(exc)})
                    return
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                    for name, content in result["documents"].items():
                        archive.writestr(name, content)
                    archive.writestr("RELATORIO.html", report_html(visual["analysis"], visual["insights"], visual["history"], diff, visual["ai"]))
                    for name, content in diagrams(visual["analysis"], visual["insights"], visual["history"], diff).items():
                        archive.writestr("diagramas/" + name + ".svg", content)
                self.respond(200, buffer.getvalue(), "application/zip", "octorgit-documentacao.zip")
                return
            if len(parts) == 5 and parts[3] == "documents" and parts[4] in (*DOCUMENTS, "AI.md", "AI.json") and parts[4] in result["documents"]:
                self.respond(200, result["documents"][parts[4]], "text/plain; charset=utf-8", parts[4])
                return
        self.json(404, {"error": "Página não encontrada."})

    def do_POST(self):
        if not self.trusted():
            return
        if urlsplit(self.path).path != "/api/jobs":
            self.json(404, {"error": "Página não encontrada."})
            return
        if not secrets.compare_digest(self.headers.get("X-OctorGit-Token", ""), self.server.csrf):
            self.json(403, {"error": "Sessão inválida. Atualize a página."})
            return
        if self.headers.get_content_type() != "application/json":
            self.json(415, {"error": "Envie JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("Requisição inválida ou muito grande.")
            payload = json.loads(self.rfile.read(size))
            job = self.server.jobs.submit(payload)
        except (ValueError, UnicodeDecodeError) as exc:
            self.json(400, {"error": str(exc)})
            return
        except BusyError as exc:
            self.json(429, {"error": str(exc)})
            return
        self.json(202, job)


def default_data_dir():
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "OctorGit"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "octorgit"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Abre a interface local do OctorGit no navegador.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="Pasta do histórico SQLite local")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Escolha uma porta de 1 a 65535.")
    try:
        server = LocalServer(args.port, data_dir=args.data_dir)
    except (OSError, sqlite3.Error):
        print("Não foi possível abrir a porta ou o histórico. Confira a pasta de dados ou tente: py -m octorgit.web --port 8766")
        return 1
    url = f"http://127.0.0.1:{args.port}"
    print(f"\nOctorGit {__version__} — interface local\n\nAbra no navegador: {url}\nMantenha esta janela aberta. Para encerrar: Ctrl+C.\n", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except webbrowser.Error:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando OctorGit…")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
