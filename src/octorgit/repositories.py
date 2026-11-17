"""Read public GitHub snapshots without extracting or executing project files."""

import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.error
import urllib.parse
import urllib.request

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
MAX_FILE = 512 * 1024
MAX_FILES = 10000
EXCLUDED = {".git", ".venv", "venv", "node_modules", "vendor", "__pycache__", "dist", "build", ".aws", ".ssh"}
SENSITIVE = re.compile(r"(^\.env($|\.)|secret|credential|token|private.?key|^id_rsa|^id_ed25519|\.(pem|key|p12|pfx)$)", re.I)
SECRET_CONTENT = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:gh[pousr]_[A-Za-z0-9]{20,})|AKIA[0-9A-Z]{16}|(?:password|secret|api_key|access_token)\s*[:=]\s*[\"'][^\"'\r\n]{8,}[\"']", re.I)


def allowed(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return bool(parts) and not path.startswith("/") and ".." not in parts and not any(p in EXCLUDED or SENSITIVE.search(p) for p in parts)


def safe_text(data: bytes) -> str | None:
    if len(data) > MAX_FILE or b"\x00" in data or SECRET_CONTENT.search(data):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def request(url: str, limit: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "OctorGit/0.1", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Resposta excede o limite de tamanho.")
    return data


def github_snapshot(url: str, branch: str | None = None):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", url)
    if not match or any(x in {".", ".."} for x in match.groups()):
        raise ValueError("Use https://github.com/owner/repo para um repositório público.")
    owner, repo = match.groups()
    base = f"https://api.github.com/repos/{owner}/{repo}"
    if branch is None:
        branch = json.loads(request(base, 1024 * 1024))["default_branch"]
    commit = json.loads(request(base + "/commits/" + urllib.parse.quote(branch, safe=""), 1024 * 1024))
    sha = commit["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("SHA inválido retornado pelo GitHub.")
    data = request(f"https://codeload.github.com/{owner}/{repo}/tar.gz/{sha}", MAX_ARCHIVE)
    files, skipped, total, count = {}, [], 0, 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r|gz") as archive:
        for member in archive:
            count += 1
            if count > MAX_FILES:
                raise ValueError("Limite de entradas do arquivo excedido.")
            if member.isdir():
                continue
            parts = PurePosixPath(member.name).parts
            path = "/".join(parts[1:])
            total += max(member.size, 0)
            if total > MAX_TOTAL:
                raise ValueError("Limite de tamanho descompactado excedido.")
            if not member.isfile() or member.size > MAX_FILE or not allowed(path):
                skipped.append({"path": path, "reason": "policy"})
                continue
            stream = archive.extractfile(member)
            text = safe_text(stream.read(MAX_FILE + 1)) if stream else None
            if text is None:
                skipped.append({"path": path, "reason": "binary_encoding_size_or_secret"})
            else:
                files[path] = text
    return {"url": f"https://github.com/{owner}/{repo}", "branch": branch, "commit_sha": sha, "source": "github"}, files, skipped


def local_snapshot(root: Path):
    """Local input is for fixtures: no Git or repository commands are run."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Diretório local não existe.")
    files, skipped, total, count = {}, [], 0, 0
    import os
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if allowed((Path(directory) / d).relative_to(root).as_posix()) and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            count += 1
            if count > MAX_FILES:
                raise ValueError("Limite de arquivos excedido.")
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file() or not allowed(relative):
                skipped.append({"path": relative, "reason": "policy"})
                continue
            size = path.stat().st_size
            total += size
            if total > MAX_TOTAL:
                raise ValueError("Limite total de arquivos excedido.")
            text = safe_text(path.read_bytes()) if size <= MAX_FILE else None
            if text is None:
                skipped.append({"path": relative, "reason": "binary_encoding_size_or_secret"})
            else:
                files[relative] = text
    return {"url": None, "branch": None, "commit_sha": None, "source": "local_fixture"}, files, skipped
