#!/usr/bin/env bash
set -euo pipefail

octorgit_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  octorgit_python=python3
elif command -v python >/dev/null 2>&1; then
  octorgit_python=python
else
  printf '%s\n' 'Python nao encontrado. Instale Python 3.11 ou superior.' >&2
  exit 1
fi

if ! "$octorgit_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  printf '%s\n' 'OctorGit precisa de Python 3.11 ou superior.' >&2
  exit 1
fi

export PYTHONPATH="${octorgit_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "$octorgit_python" -m octorgit.web "$@"
