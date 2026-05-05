# -*- coding: utf-8 -*-
"""Persist / reload LlamaIndex ``SimplePropertyGraphStore`` JSON and push into Neo4j."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

# Repo-relative folder for exported PropertyGraph JSON (not mixed with demo Markdown in ``data/kg_snapshots/``).
DEFAULT_GRAPH_SNAPSHOT_SUBDIR = "data/graph_snapshots"


def save_property_graph_snapshot(store: SimplePropertyGraphStore, path: Path) -> None:
    """Write ``LabelledPropertyGraph`` JSON (LlamaIndex native format)."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    store.persist(str(path))


def load_property_graph_snapshot(path: Path) -> SimplePropertyGraphStore:
    """Load snapshot written by :func:`save_property_graph_snapshot`."""
    p = path.resolve()
    if not p.is_file():
        raise FileNotFoundError(f"KG snapshot not found: {p}")
    return SimplePropertyGraphStore.from_persist_path(str(p))


def push_snapshot_to_neo4j(
    simple: SimplePropertyGraphStore,
    neo: Neo4jPropertyGraphStore,
) -> dict[str, Any]:
    """
    Upsert all chunk/entity nodes and relations from the in-memory graph into Neo4j.

    Mirrors what ``PropertyGraphIndex`` does when built directly against Neo4j.
    """
    nodes = simple.graph.get_all_nodes()
    relations = simple.graph.get_all_relations()
    neo.upsert_nodes(nodes)
    neo.upsert_relations(relations)
    return {
        "nodes": len(nodes),
        "relations": len(relations),
        "triplet_edges": len(simple.graph.triplets),
    }
