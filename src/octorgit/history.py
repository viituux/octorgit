"""SQLite snapshots and comparison of observed facts; no source execution."""

from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

HIDDEN = {"ir", "documents", "ai_result", "insights"}


def metadata(job):
    return {k: v for k, v in job.items() if k not in HIDDEN}


class HistoryStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "history.sqlite3"
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, metadata TEXT NOT NULL, payload TEXT NOT NULL)")
            db.commit()

    def save(self, job):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("INSERT OR REPLACE INTO analyses VALUES (?, ?, ?, ?)",
                       (job["id"], job["created_at"], json.dumps(metadata(job), ensure_ascii=False), json.dumps(job, ensure_ascii=False)))
            db.commit()

    def get(self, job_id):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            row = db.execute("SELECT payload FROM analyses WHERE id = ?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            rows = db.execute("SELECT metadata FROM analyses ORDER BY created_at DESC LIMIT 100").fetchall()
        return [json.loads(r[0]) for r in rows]


def repository_identity(ir):
    repo = ir["repository"]
    if repo.get("url"):
        return repo["url"].removesuffix(".git").rstrip("/").lower()
    return "fixture-local"


def snapshot_fingerprint(ir):
    return hashlib.sha256(json.dumps(sorted((f["path"], f["sha256"]) for f in ir["files"])).encode()).hexdigest()[:16]


def compare_analyses(before, after):
    if repository_identity(before) != repository_identity(after):
        raise ValueError("Escolha duas análises do mesmo repositório.")
    left_files = {f["path"]: f["sha256"] for f in before["files"]}
    right_files = {f["path"]: f["sha256"] for f in after["files"]}
    changed_files = sorted(p for p in left_files.keys() & right_files.keys() if left_files[p] != right_files[p])
    files = {"added": sorted(right_files.keys() - left_files.keys()), "removed": sorted(left_files.keys() - right_files.keys()), "changed": changed_files}
    def group(ir):
        result = defaultdict(list)
        for endpoint in ir["endpoints"]:
            result[(endpoint.get("method"), endpoint["route"], endpoint["scope"])].append(endpoint)
        return result
    left, right = group(before), group(after)
    added, removed, changed = [], [], []
    for key in sorted(left.keys() | right.keys(), key=str):
        a, b = sorted(left.get(key, []), key=lambda e: e["view"]), sorted(right.get(key, []), key=lambda e: e["view"])
        count = min(len(a), len(b))
        added.extend(b[count:]); removed.extend(a[count:])
        for old, new in zip(a[:count], b[:count]):
            fields = [name for name in ("view", "serializer", "permissions", "authentication", "confidence") if old.get(name) != new.get(name)]
            refs = [r["file"] for r in new["evidence_chain"]]
            if any(p in changed_files for p in refs):
                fields.append("evidence_file_changed")
            if fields:
                changed.append({"before": old, "after": new, "fields": fields})
    warnings = []
    if before["parser_version"] != after["parser_version"]:
        warnings.append("Versões do parser diferentes: parte das diferenças pode vir da ferramenta.")
    if before.get("routing", {}).get("roots") != after.get("routing", {}).get("roots"):
        warnings.append("Raízes de URLs diferentes: a seleção altera o escopo da comparação.")
    if any(e["scope"] == "local_urlconf" for ir in (before, after) for e in ir["endpoints"]):
        warnings.append("Há rotas com prefixo não confirmado; mudanças de montagem podem estar incompletas.")
    if before["repository"].get("commit_sha") == after["repository"].get("commit_sha") and before["repository"].get("commit_sha"):
        warnings.append("As duas análises estão no mesmo commit; diferenças não indicam necessariamente mudanças de código.")
    docs = []
    if added or removed or changed:
        docs.append({"document": "ENDPOINTS.md", "reason": "Rotas/configurações ou arquivos de evidência mudaram; revise o mapa."})
    if any(files.values()):
        docs.extend([{"document": name, "reason": "O snapshot de arquivos mudou; revise as explicações e as evidências."} for name in ("README.md", "ARCHITECTURE.md", "AI.md", "RELATORIO.html")])
    return {"before_sha": before["repository"].get("commit_sha"), "after_sha": after["repository"].get("commit_sha"),
            "before_fingerprint": snapshot_fingerprint(before), "after_fingerprint": snapshot_fingerprint(after),
            "added": added, "removed": removed, "changed": changed, "files": files, "documents_to_review": docs, "warnings": warnings,
            "note": "Diferenças entre fatos detectados, não garantia de todas as alterações do projeto. Arquivo de evidência alterado é sinal de revisão; não prova mudança em cada função."}
