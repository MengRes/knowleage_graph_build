#!/usr/bin/env bash
# Run build_neo4j_kg once per --kg-extractor value (see neo4j_kg/build_index.KG_EXTRACTOR_CHOICES).
#
# Default corpus: data/kg_snapshots/rag_intro_test.md  →  data/graph_snapshots/rag_intro_test_<extractor>.json
#
# Prerequisites: conda env ``llm`` (scripts/llm_env_python.sh), OPENAI_API_KEY.
#
# Usage:
#   ./scripts/test_all_extractors.sh
#   ROOT_MD=data/kg_snapshots FILE=demo.md ./scripts/test_all_extractors.sh
#
#   SKIP_LLM_EXTRACTORS=1  — only ``implicit`` (chunk graph edges, no LLM path extraction).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
RUN_PY="${REPO_ROOT}/scripts/llm_env_python.sh"

ROOT_MD="${ROOT_MD:-data/kg_snapshots}"
FILE="${FILE:-rag_intro_test.md}"
OUT_DIR="${OUT_DIR:-data/graph_snapshots}"
SCHEMA_CONFIG="${SCHEMA_CONFIG:-neo4j_kg/schema_kg_config.example.json}"
MAX_PATHS="${MAX_PATHS:-12}"

mkdir -p "$OUT_DIR"

if [[ ! -f "${ROOT_MD}/${FILE}" ]]; then
    echo "Missing ${ROOT_MD}/${FILE}" >&2
    exit 1
fi

if [[ -f "${REPO_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.env"
    set +a
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
    echo "OPENAI_API_KEY is not set." >&2
    exit 1
fi

run_one() {
    local extractor="$1"
    shift
    local out="${OUT_DIR}/rag_intro_test_${extractor}.json"
    echo ""
    echo "=== kg-extractor=${extractor} -> ${out} ==="
    "$RUN_PY" build_neo4j_kg.py \
        --markdown-root "$ROOT_MD" --file "$FILE" \
        --kg-extractor "$extractor" \
        --local-only --save-kg "$out" \
        --max-paths-per-chunk "$MAX_PATHS" \
        --no-log \
        "$@"
}

echo "Corpus: ${ROOT_MD}/${FILE}"
echo "Order matches KG_EXTRACTOR_CHOICES: simple, dynamic, schema, implicit, simple_implicit"

if [[ "${SKIP_LLM_EXTRACTORS:-0}" == "1" ]]; then
    run_one implicit --chunk-size 384 --chunk-overlap 40
    echo ""
    echo "Done (SKIP_LLM_EXTRACTORS=1: implicit only)."
    exit 0
fi

# LLM path extractors (same max_paths for comparable cost ceiling)
run_one simple
run_one dynamic

# Typed schema extractor (example ontology JSON + relaxed strictness)
run_one schema \
    --schema-config "$SCHEMA_CONFIG" \
    --schema-relaxed

# No LLM triples: chunk adjacency only
run_one implicit --chunk-size 384 --chunk-overlap 40

# LLM simple then implicit
run_one simple_implicit

echo ""
echo "Done. Snapshots: ${OUT_DIR}/rag_intro_test_{simple,dynamic,schema,implicit,simple_implicit}.json"
