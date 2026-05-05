# -*- coding: utf-8 -*-
"""Console summary after graph import (postprocess stats, Browser Cypher hints)."""
from __future__ import annotations

from typing import Any


def print_postprocess_report(
    stats: dict[str, Any],
    *,
    entity_align: bool,
    entity_fuzzy: bool,
    browser_entity_subgraph: str,
    browser_doc_chunk_entity: str,
) -> None:
    """Print summary. Uses flush=True so lines appear promptly after long LLM runs (e.g. conda)."""

    def pr(*args: Any, **kwargs: Any) -> None:
        print(*args, **kwargs, flush=True)

    pr(
        f"Document roots: Doc={stats['doc_count']}, "
        f"HAS_CHUNK={stats['has_chunk_count']}"
    )
    pr(
        "ChunkNode–Entity edges normalized to HAS_ENTITY: "
        f"removed {stats['chunk_entity_edges_deleted']} legacy edges, "
        f"HAS_ENTITY count={stats['has_entity_count']}"
    )
    if stats["doc_entity_edges_removed"]:
        pr(
            "Removed direct Doc–Entity relationships: "
            f"{stats['doc_entity_edges_removed']} edge(s)"
        )
    ea = stats["entity_align"]
    if entity_align or entity_fuzzy:
        pr(
            "Exact entity alignment: "
            f"merged {ea['exact_groups_merged']} group(s), "
            f"removed {ea['exact_nodes_removed']} duplicate node(s)"
        )
    if entity_fuzzy:
        pr(
            "Fuzzy entity alignment: "
            f"merged {ea['fuzzy_groups_merged']} group(s), "
            f"removed {ea['fuzzy_nodes_removed']} duplicate node(s)"
        )
    fin = stats["finalize"]
    pr(
        "Three-label normalization done (Browser colors by label: Doc / ChunkNode / Entity): "
        f"Doc={fin['Doc']}, ChunkNode={fin['ChunkNode']}, Entity={fin['Entity']}, "
        f"remaining Doc–Entity direct edges={fin['doc_entity_edges']}"
    )
    pr("Node props: kind, viz_color (amber / blue / green).")
    pr(
        "Entity–entity subgraph edge count (excl. MENTIONS & UUID-shaped names): "
        f"{stats['entity_subgraph_edge_count']}"
    )
    pr("Neo4j Browser — entity subgraph query:")
    pr(browser_entity_subgraph)
    pr("Neo4j Browser — Doc → Chunk → Entity path:")
    pr(browser_doc_chunk_entity)
