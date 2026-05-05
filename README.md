# knowleage_graph_build

Build a **LlamaIndex PropertyGraph** from **Markdown** and persist it to **Neo4j**. Supports multiple path extractors, local JSON snapshots, JSON configuration, and post-processing (entity alignment and label normalization).

## Features

- **Extractors**: `simple`, `dynamic`, `schema` (JSON ontology constraints), `implicit` (chunk adjacency only), `simple_implicit`
- **Persistence**: Connect directly to Neo4j, or use `--local-only --save-kg` to export a snapshot and later `--load-kg` to import
- **Configuration**: `config/build_neo4j_kg.json` (copy from [`config/build_neo4j_kg.example.json`](config/build_neo4j_kg.example.json)); CLI flags override file values
- **Post-processing**: APOC-based entity alignment (exact + optional fuzzy matching via `rapidfuzz`) and three-label normalization; or run `python -m neo4j_kg.normalize_cli` alone
- **Extra**: [`test/ontology_ttl_to_neo4j_example.py`](test/ontology_ttl_to_neo4j_example.py) imports a Turtle ontology into Neo4j (independent of the LlamaIndex document graph)

## Requirements

- **Python 3.10+** ( **3.12** recommended for current LlamaIndex typing)
- **Neo4j 5+** (APOC required for alignment / some Cypher steps)
- **OpenAI API** (extraction and embeddings; model names configurable, e.g. `gpt-4o-mini`, `text-embedding-3-small`)

## Install

```bash
cd knowleage_graph_build
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If you use a conda env named `llm` but a project `.venv` shadows `PATH`, prefer:

```bash
./scripts/llm_env_python.sh build_neo4j_kg.py --help
```

## Environment variables

Create **`.env`** at the repo root (**do not commit**):

```env
OPENAI_API_KEY=sk-...
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
# Optional Neo4j 5 logical database (default: neo4j)
# NEO4J_DATABASE=neo4j
```

For **`--local-only`** snapshot workflows without Neo4j import, `NEO4J_*` may be omitted.

## Quick start

```bash
# Uses merged config / built-in defaults; processes Markdown under default --markdown-root
python build_neo4j_kg.py --all-docs

# Export JSON only (no Neo4j during extraction)
python build_neo4j_kg.py --local-only --save-kg data/graph_snapshots/run1.json --all-docs

# Load snapshot into Neo4j and run post-processing
python build_neo4j_kg.py --load-kg data/graph_snapshots/run1.json --clean

# Custom Markdown root, single file, schema extractor
python build_neo4j_kg.py \
  --markdown-root path/to/md_dir \
  --file doc.md \
  --kg-extractor schema \
  --schema-config neo4j_kg/schema_kg_config.example.json \
  --schema-relaxed
```

Full CLI reference:

```bash
python build_neo4j_kg.py --help
```

## Configuration

1. Copy the example: `cp config/build_neo4j_kg.example.json config/build_neo4j_kg.json`
2. Edit `config/build_neo4j_kg.json` (this path is gitignored)
3. If that file exists at repo startup it is merged automatically; use `--config path/to/other.json` to point elsewhere

Schema extractor vocabulary example: [`neo4j_kg/schema_kg_config.example.json`](neo4j_kg/schema_kg_config.example.json)

## Test scripts

With `OPENAI_API_KEY` set and conda `llm` (or an equivalent Python) available:

```bash
# All kg-extractor modes: simple, dynamic, schema, implicit, simple_implicit
./scripts/test_all_extractors.sh

# Config override smoke test + optional full extractor matrix
./scripts/test_rag_intro_features.sh

# Implicit extractor only (fewer LLM calls)
SKIP_LLM_EXTRACTORS=1 ./scripts/test_all_extractors.sh
```

Scripts expect demo Markdown at `data/kg_snapshots/rag_intro_test.md`. The whole `data/` tree is gitignored; clone the repo and add your own corpus or adjust `.gitignore` if you want samples tracked.

## Other scripts

| Path | Purpose |
|------|---------|
| `_normalize_three_labels.py` | Same as `python -m neo4j_kg.normalize_cli` |
| `install_neo4j_apoc.sh`, `start_neo4j_graphrag.sh` | Optional local Neo4j / APOC helpers |

## Repository layout

```
build_neo4j_kg.py          # CLI entry
neo4j_kg/                  # Package: CLI, indexing, Neo4j, snapshots, post-process
config/                    # Build JSON example + local overrides
scripts/                   # llm Python wrapper and test scripts
test/ontology_ttl_to_neo4j_example.py
```

## License

No default license is bundled; add a `LICENSE` file if you publish this project openly.
