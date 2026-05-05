#!/usr/bin/env bash
# Exercise build_neo4j_kg features against data/kg_snapshots/rag_intro_test.md.
#
# Prerequisites: conda env ``llm`` (see scripts/llm_env_python.sh), OPENAI_API_KEY in env or .env.
#
# Usage (repo root):
#   ./scripts/test_rag_intro_features.sh
#
# All ``--kg-extractor`` modes (simple, dynamic, schema, implicit, simple_implicit)::
#   ./scripts/test_all_extractors.sh
#
# Optional Neo4j steps (requires NEO4J_* in .env):
#   RUN_NEO4J_LOAD=1      — after builds, --load-kg the simple snapshot with --clean
#   RUN_NEO4J_NORMALIZE=1 — run python -m neo4j_kg.normalize_cli
#
# Skip the heavier LLM extractors in the extractor matrix (delegate script):
#   SKIP_LLM_EXTRACTORS=1 ./scripts/test_all_extractors.sh
#
# Skip calling ``test_all_extractors.sh`` from this script (config + entity-flag smoke only):
#   SKIP_EXTRACTOR_MATRIX=1 ./scripts/test_rag_intro_features.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
RUN_PY="${REPO_ROOT}/scripts/llm_env_python.sh"

ROOT_MD="data/kg_snapshots"
FILE="rag_intro_test.md"
OUT_DIR="data/graph_snapshots"
mkdir -p "$OUT_DIR"

if [[ ! -f "${ROOT_MD}/${FILE}" ]]; then
    echo "Missing ${ROOT_MD}/${FILE}" >&2
    exit 1
fi

# shellcheck source=/dev/null
if [[ -f "${REPO_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.env"
    set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OPENAI_API_KEY is not set (export it or add to .env)." >&2
    exit 1
fi

run_build() {
    echo ""
    echo "=== $* ==="
    "$RUN_PY" build_neo4j_kg.py "$@"
}

echo "Using: ${ROOT_MD}/${FILE} -> ${OUT_DIR}/rag_intro_test_*.json"

run_build \
    --markdown-root "$ROOT_MD" --file "$FILE" \
    --kg-extractor implicit \
    --local-only --save-kg "$OUT_DIR/rag_intro_test_implicit_entity_flags.json" \
    --chunk-size 384 --chunk-overlap 40 \
    --no-entity-fuzzy \
    --no-log

run_build \
    --config config/build_neo4j_kg.example.json \
    --markdown-root "$ROOT_MD" --file "$FILE" \
    --chunk-size 200 \
    --kg-extractor implicit \
    --local-only --save-kg "$OUT_DIR/rag_intro_test_config_override.json" \
    --no-log

if [[ "${SKIP_EXTRACTOR_MATRIX:-0}" != "1" ]]; then
    ROOT_MD="$ROOT_MD" FILE="$FILE" OUT_DIR="$OUT_DIR" \
        "${REPO_ROOT}/scripts/test_all_extractors.sh"
fi

if [[ "${RUN_NEO4J_LOAD:-0}" == "1" ]]; then
    if [[ ! -f "$OUT_DIR/rag_intro_test_simple.json" ]]; then
        echo "RUN_NEO4J_LOAD=1 needs rag_intro_test_simple.json (run without SKIP_LLM_EXTRACTORS=1)." >&2
        exit 1
    fi
    echo ""
    echo "=== Neo4j load (clean + postprocess) ==="
    "$RUN_PY" build_neo4j_kg.py \
        --load-kg "$OUT_DIR/rag_intro_test_simple.json" \
        --clean --no-log
fi

if [[ "${RUN_NEO4J_NORMALIZE:-0}" == "1" ]]; then
    echo ""
    echo "=== normalize_cli ==="
    "$RUN_PY" -m neo4j_kg.normalize_cli --no-log
fi

echo ""
echo "Done. Artifacts under ${OUT_DIR}/ (JSON may be gitignored)."
