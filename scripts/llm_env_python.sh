#!/usr/bin/env bash
# Run a command with conda env "llm" Python, without picking up project .venv first.
# Usage (from repo root): ./scripts/llm_env_python.sh build_neo4j_kg.py --help
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [[ -z "$CONDA_BASE" ]]; then
    echo "conda not found" >&2
    exit 1
fi
PY="${CONDA_BASE}/envs/llm/bin/python"
if [[ ! -x "$PY" ]]; then
    echo "Not found: $PY (create env: conda create -n llm python=3.12 ...)" >&2
    exit 1
fi
cd "$REPO_ROOT"
exec "$PY" "$@"
