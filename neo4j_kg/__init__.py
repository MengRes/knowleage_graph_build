# -*- coding: utf-8 -*-
"""
Regulation Markdown → Neo4j property graph (knowledge graph build and cleanup).

**Package modules**

- ``documents`` — load Markdown under ``data/regulation``.
- ``build_index`` — chunking, LLM triple extraction, ``PropertyGraphIndex`` → Neo4j.
- ``postprocess`` — Doc roots, ``HAS_ENTITY`` normalization, three labels ``Doc`` / ``ChunkNode`` / ``Entity``, Browser Cypher constants.
- ``entity_align`` — exact / fuzzy entity alignment (APOC ``mergeNodes``).
- ``env`` — repo root, ``.env``, ``require_env``.
- ``reporting`` — console summary after import.
- ``run_logging`` — tee stdout/stderr to a log file.
- ``normalize_cli`` — post-process an existing graph only (``python -m neo4j_kg.normalize_cli``).
- ``kg_snapshot`` — save/load ``SimplePropertyGraphStore`` JSON and push into Neo4j.
- ``neo4j_connect`` — build ``Neo4jPropertyGraphStore`` from ``NEO4J_*`` env vars.
- ``property_graph_cli`` — argparse + pipelines (invoked by repo-root ``build_neo4j_kg.py``).

**Entry scripts (repo root)**

- ``build_neo4j_kg.py`` — thin launcher → ``property_graph_cli`` (optional ``--save-kg`` / ``--load-kg``).
- ``_normalize_three_labels.py`` — thin wrapper calling ``normalize_cli``.
"""

from .build_index import SchemaKGConfig, load_schema_kg_config
from .documents import load_regulation_docs
from .entity_align import (
    align_duplicate_entities,
    fuzzy_align_duplicate_entities,
    normalize_entity_name_key,
)
from .postprocess import (
    BROWSER_QUERY_DOC_CHUNK_ENTITY,
    BROWSER_QUERY_ENTITY_SUBGRAPH,
    clear_graph,
    finalize_three_node_labels,
    link_doc_roots,
    normalize_chunk_entity_edges,
    postprocess_regulation_property_graph,
    project_entity_only_subgraph,
    remove_doc_entity_edges,
)

__all__ = [
    "SchemaKGConfig",
    "load_schema_kg_config",
    "align_duplicate_entities",
    "fuzzy_align_duplicate_entities",
    "BROWSER_QUERY_DOC_CHUNK_ENTITY",
    "BROWSER_QUERY_ENTITY_SUBGRAPH",
    "clear_graph",
    "finalize_three_node_labels",
    "link_doc_roots",
    "load_regulation_docs",
    "normalize_entity_name_key",
    "normalize_chunk_entity_edges",
    "postprocess_regulation_property_graph",
    "project_entity_only_subgraph",
    "remove_doc_entity_edges",
]
