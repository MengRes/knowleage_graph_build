# -*- coding: utf-8 -*-
"""
Build a LlamaIndex PropertyGraphIndex from Markdown and persist triples to Neo4j.

Run (from repo root):
    python build_neo4j_kg.py

If ``conda run -n llm`` still resolves to a project ``.venv`` on ``PATH``, use::

    ./scripts/llm_env_python.sh build_neo4j_kg.py ...

Local snapshot (no Neo4j during extraction; reuse without re-running LLM)::

    python build_neo4j_kg.py --local-only --save-kg data/graph_snapshots/run1.json --all-docs

Push snapshot to Neo4j + same postprocess as a fresh build::

    python build_neo4j_kg.py --load-kg data/graph_snapshots/run1.json --clean

Markdown outside ``data/regulation`` (e.g. demo under ``data/kg_snapshots/``); **export JSON** under ``data/graph_snapshots/``::

    python build_neo4j_kg.py --markdown-root data/kg_snapshots \\
      --file rag_intro_test.md --local-only --save-kg data/graph_snapshots/rag_intro_test_kg.json
    python build_neo4j_kg.py --load-kg data/graph_snapshots/rag_intro_test_kg.json --clean

Build defaults can live in ``config/build_neo4j_kg.json`` (copy from
``config/build_neo4j_kg.example.json``); optional ``--config PATH`` overrides that path.

CLI logic lives in :mod:`neo4j_kg.property_graph_cli`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from neo4j_kg.property_graph_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
