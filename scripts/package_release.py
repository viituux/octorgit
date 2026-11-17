"""Package the project's tracked sources for Windows/Linux, without local state."""

import argparse
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tomllib
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = [p for p in subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0") if p]
    entries = {}
    for path in paths:
        if Path(path).suffix in {".env", ".db", ".sqlite3", ".key", ".pem"}:
            raise ValueError("Arquivo local ou sensível rastreado; empacotamento interrompido.")
        entries[path] = subprocess.check_output(["git", "show", "HEAD:" + path], cwd=root)
    windows = out / f"octorgit-{version}-windows.zip"
    linux = out / f"octorgit-{version}-linux.tar.gz"
    with zipfile.ZipFile(windows, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in entries.items():
            if path.endswith(".bat"):
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            archive.writestr("octorgit/" + path, data)
    with tarfile.open(linux, "w:gz") as archive:
        for path, data in entries.items():
            member = tarfile.TarInfo("octorgit/" + path)
            member.size = len(data)
            member.mode = 0o755 if path.endswith(".sh") else 0o644
            archive.addfile(member, io.BytesIO(data))
    with zipfile.ZipFile(windows) as archive:
        assert archive.testzip() is None
        assert b"\r\n" in archive.read("octorgit/ABRIR_OCTORGIT.bat")
    with tarfile.open(linux) as archive:
        assert archive.getmember("octorgit/ABRIR_OCTORGIT.sh").mode & 0o111
    artifacts = [windows, linux, *sorted(out.glob(f"octorgit-{version}-*.whl"))]
    (out / f"octorgit-{version}-SHA256SUMS.txt").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in artifacts))
    print(f"Pacotes {version} verificados: {len(entries)} arquivos rastreados.")


if __name__ == "__main__":
    main()
