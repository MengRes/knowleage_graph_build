# -*- coding: utf-8 -*-
"""Post-import graph cleanup after PropertyGraphIndex → Neo4j (Doc → Chunk → Entity, three labels)."""
from __future__ import annotations

from typing import Any

from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from .entity_align import align_duplicate_entities, fuzzy_align_duplicate_entities

# Neo4j Browser: entity–entity subgraph (exclude MENTIONS and UUID-shaped names)
BROWSER_QUERY_ENTITY_SUBGRAPH = (
    "MATCH (s)-[r]->(o) "
    "WHERE type(r) <> 'MENTIONS' "
    "AND coalesce(s.name,'') <> '' "
    "AND coalesce(o.name,'') <> '' "
    "AND NOT s.name =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' "
    "AND NOT o.name =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' "
    "RETURN s, r, o LIMIT 300;"
)

# Doc root → chunk → entity (Browser colors by Doc / ChunkNode / Entity)
BROWSER_QUERY_DOC_CHUNK_ENTITY = (
    "MATCH (d:Doc)-[:HAS_CHUNK]->(c:ChunkNode)-[:HAS_ENTITY]->(e:Entity) "
    "RETURN d, c, e LIMIT 200;"
)


def clear_graph(graph_store: Neo4jPropertyGraphStore) -> None:
    graph_store.structured_query("MATCH (n) DETACH DELETE n")


# In LlamaIndex both chunks and entities are __Node__; entities also have __Entity__ (or entity / Entity).
_CHUNK_NOT_ENTITY = (
    "(c:Chunk OR c:ChunkNode OR c:__Node__) "
    "AND NOT c:__Entity__ AND NOT c:Entity AND NOT c:entity"
)


def project_entity_only_subgraph(graph_store: Neo4jPropertyGraphStore) -> int:
    rows = graph_store.structured_query(
        """
        MATCH (s)-[r]->(o)
        WHERE type(r) <> 'MENTIONS'
          AND coalesce(s.name, '') <> ''
          AND coalesce(o.name, '') <> ''
          AND NOT s.name =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
          AND NOT o.name =~ '(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        RETURN count(r) AS cnt
        """
    )
    return int(rows[0]["cnt"]) if rows else 0


def link_doc_roots(graph_store: Neo4jPropertyGraphStore) -> tuple[int, int]:
    """Create a Doc root per source_file and link chunks with HAS_CHUNK."""
    doc_rows = graph_store.structured_query(
        f"""
        MATCH (c)
        WHERE {_CHUNK_NOT_ENTITY} AND c.source_file IS NOT NULL
        WITH DISTINCT c.source_file AS source_file
        MERGE (d:Doc {{source_file: source_file}})
        ON CREATE SET d.doc_id = source_file, d.title = source_file
        RETURN count(d) AS cnt
        """
    )
    rel_rows = graph_store.structured_query(
        f"""
        MATCH (c)
        WHERE {_CHUNK_NOT_ENTITY} AND c.source_file IS NOT NULL
        MERGE (d:Doc {{source_file: c.source_file}})
        ON CREATE SET d.doc_id = c.source_file, d.title = c.source_file
        MERGE (d)-[r:HAS_CHUNK]->(c)
        RETURN count(r) AS cnt
        """
    )
    doc_cnt = int(doc_rows[0]["cnt"]) if doc_rows else 0
    rel_cnt = int(rel_rows[0]["cnt"]) if rel_rows else 0
    return doc_cnt, rel_cnt


def normalize_chunk_entity_edges(
    graph_store: Neo4jPropertyGraphStore,
) -> tuple[int, int]:
    """
    Normalize chunk→entity edges to HAS_ENTITY (keep Doc→Chunk as HAS_CHUNK).
    Drop other chunk→entity rel types (e.g. MENTIONS) to avoid duplication with HAS_ENTITY.
    """
    graph_store.structured_query(
        f"""
        MATCH (c)-[r]->(e)
        WHERE {_CHUNK_NOT_ENTITY}
          AND (e:Entity OR e:entity OR e:__Entity__)
          AND type(r) <> 'HAS_CHUNK'
        MERGE (c)-[:HAS_ENTITY]->(e)
        """
    )
    rows = graph_store.structured_query(
        f"""
        MATCH (c)-[r]->(e)
        WHERE {_CHUNK_NOT_ENTITY}
          AND (e:Entity OR e:entity OR e:__Entity__)
          AND NOT type(r) IN ['HAS_CHUNK', 'HAS_ENTITY']
        DELETE r
        RETURN count(*) AS deleted
        """
    )
    deleted = int(rows[0]["deleted"]) if rows else 0
    cnt_rows = graph_store.structured_query(
        f"""
        MATCH (c)-[r:HAS_ENTITY]->(e)
        WHERE {_CHUNK_NOT_ENTITY}
          AND (e:Entity OR e:entity OR e:__Entity__)
        RETURN count(r) AS cnt
        """
    )
    has_entity = int(cnt_rows[0]["cnt"]) if cnt_rows else 0
    return deleted, has_entity


def remove_doc_entity_edges(graph_store: Neo4jPropertyGraphStore) -> int:
    """Remove direct Doc–Entity relationships; keep only Doc→Chunk→Entity."""
    rows = graph_store.structured_query(
        """
        MATCH (d:Doc)-[r]-(e)
        WHERE e:Entity OR e:entity OR e:__Entity__
        DELETE r
        RETURN count(*) AS deleted
        """
    )
    return int(rows[0]["deleted"]) if rows else 0


def finalize_three_node_labels(
    graph_store: Neo4jPropertyGraphStore,
) -> dict[str, int]:
    """
    Collapse to three mutually exclusive labels: Doc / ChunkNode / Entity; set kind and viz_color.
    Requires APOC (apoc.create.removeLabels). Browser can color by label.
    """
    graph_store.structured_query(
        """
        MATCH (d:Doc)-[r:HAS_CHUNK]->(e)
        WHERE e:__Entity__ OR e:Entity OR e:entity
        DELETE r
        """
    )
    graph_store.structured_query(
        f"""
        MATCH (c)
        WHERE {_CHUNK_NOT_ENTITY} AND c.source_file IS NOT NULL
        MERGE (d:Doc {{source_file: c.source_file}})
        ON CREATE SET d.doc_id = c.source_file, d.title = c.source_file
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
    )

    strip_on_doc = [
        "Chunk",
        "ChunkNode",
        "__Node__",
        "__Entity__",
        "entity",
        "Entity",
        "DisplayChunk",
        "DisplayEntity",
    ]
    for lab in strip_on_doc:
        graph_store.structured_query(
            f"""
            MATCH (d:Doc)
            WHERE '{lab}' IN labels(d)
            CALL apoc.create.removeLabels(d, ['{lab}']) YIELD node
            RETURN count(*)
            """
        )

    graph_store.structured_query(
        """
        MATCH (:Doc)-[:HAS_CHUNK]->(c)
        WHERE NOT c:__Entity__ AND NOT c:Entity AND NOT c:entity
        SET c:ChunkNode
        """
    )
    strip_on_chunk = [
        "__Node__",
        "Chunk",
        "DisplayChunk",
        "entity",
        "__Entity__",
        "Entity",
    ]
    for lab in strip_on_chunk:
        graph_store.structured_query(
            f"""
            MATCH (:Doc)-[:HAS_CHUNK]->(c)
            WHERE NOT c:__Entity__ AND NOT c:Entity AND NOT c:entity
              AND '{lab}' IN labels(c)
            CALL apoc.create.removeLabels(c, ['{lab}']) YIELD node
            RETURN count(*)
            """
        )

    graph_store.structured_query(
        """
        MATCH (n)
        WHERE NOT n:Doc AND NOT n:ChunkNode
          AND (n:__Entity__ OR n:entity OR n:Entity)
        SET n:Entity
        """
    )
    strip_on_entity = [
        "__Entity__",
        "entity",
        "DisplayEntity",
        "__Node__",
        "Chunk",
        "ChunkNode",
    ]
    for lab in strip_on_entity:
        graph_store.structured_query(
            f"""
            MATCH (n:Entity)
            WHERE '{lab}' IN labels(n)
            CALL apoc.create.removeLabels(n, ['{lab}']) YIELD node
            RETURN count(*)
            """
        )

    for lab in (
        "__Node__",
        "__Entity__",
        "entity",
        "Chunk",
        "DisplayChunk",
        "DisplayEntity",
    ):
        graph_store.structured_query(
            f"""
            MATCH (n)
            WHERE '{lab}' IN labels(n)
            CALL apoc.create.removeLabels(n, ['{lab}']) YIELD node
            RETURN count(*)
            """
        )

    graph_store.structured_query(
        "MATCH (d:Doc) SET d.kind = 'doc', d.viz_color = '#FF9800'"
    )
    graph_store.structured_query(
        "MATCH (c:ChunkNode) SET c.kind = 'chunk', c.viz_color = '#1E88E5'"
    )
    graph_store.structured_query(
        "MATCH (e:Entity) SET e.kind = 'entity', e.viz_color = '#43A047'"
    )

    graph_store.structured_query("MATCH (d:Doc)-[r]-(e:Entity) DELETE r")

    def _cnt(q: str) -> int:
        rows = graph_store.structured_query(q)
        return int(rows[0]["c"]) if rows else 0

    return {
        "Doc": _cnt("MATCH (n:Doc) RETURN count(n) AS c"),
        "ChunkNode": _cnt("MATCH (n:ChunkNode) RETURN count(n) AS c"),
        "Entity": _cnt("MATCH (n:Entity) RETURN count(n) AS c"),
        "doc_entity_edges": _cnt(
            "MATCH (d:Doc)-[r]-(e:Entity) RETURN count(r) AS c"
        ),
    }


def postprocess_regulation_property_graph(
    graph_store: Neo4jPropertyGraphStore,
    *,
    entity_align: bool = False,
    entity_fuzzy: bool = False,
    entity_fuzzy_threshold: float = 88.0,
) -> dict[str, Any]:
    """
    After PropertyGraph import: Doc roots, HAS_ENTITY normalization, drop Doc–entity edges,
    optional exact then fuzzy entity alignment, three-label normalization, entity subgraph edge count.
    """
    doc_cnt, has_chunk_cnt = link_doc_roots(graph_store)
    del_ce, has_entity_cnt = normalize_chunk_entity_edges(graph_store)
    doc_entity_removed = remove_doc_entity_edges(graph_store)
    entity_align_stats: dict[str, int] = {
        "exact_groups_merged": 0,
        "exact_nodes_removed": 0,
        "fuzzy_groups_merged": 0,
        "fuzzy_nodes_removed": 0,
    }
    if entity_align or entity_fuzzy:
        ex = align_duplicate_entities(graph_store)
        entity_align_stats["exact_groups_merged"] = ex["groups_merged"]
        entity_align_stats["exact_nodes_removed"] = ex["nodes_removed"]
    if entity_fuzzy:
        fz = fuzzy_align_duplicate_entities(
            graph_store, threshold=entity_fuzzy_threshold
        )
        entity_align_stats["fuzzy_groups_merged"] = fz["groups_merged"]
        entity_align_stats["fuzzy_nodes_removed"] = fz["nodes_removed"]
    fin = finalize_three_node_labels(graph_store)
    entity_rel_count = project_entity_only_subgraph(graph_store)
    return {
        "doc_count": doc_cnt,
        "has_chunk_count": has_chunk_cnt,
        "chunk_entity_edges_deleted": del_ce,
        "has_entity_count": has_entity_cnt,
        "doc_entity_edges_removed": doc_entity_removed,
        "entity_align": entity_align_stats,
        "finalize": fin,
        "entity_subgraph_edge_count": entity_rel_count,
    }
