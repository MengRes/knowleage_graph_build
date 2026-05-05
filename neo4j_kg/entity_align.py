# -*- coding: utf-8 -*-
"""
Entity alignment: exact then fuzzy (run both before three-label finalization).

**Exact**: collapse whitespace, lowercase → ``entity_key``; merge same key.

**Fuzzy**: after exact, compare alphanumeric-folded strings in buckets with similarity
(``rapidfuzz`` if available, else ``difflib``), union-find for transitive closure,
then ``apoc.refactor.mergeNodes``. Default threshold 88; large length gaps need higher scores.

- Requires APOC: ``apoc.refactor.mergeNodes``.
- Survivor is smallest ``id`` lexicographically; ``name`` is longest display string in group;
  ``entity_key`` stores the folded key.
- Vector indexes may reference deleted ``id``; if you rely on entity vectors, prefer ``--clean`` rebuild.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

try:
    from rapidfuzz import fuzz as _rfuzz

    def _fuzz_ratio(a: str, b: str) -> float:
        return float(_rfuzz.ratio(a, b))

except ImportError:
    from difflib import SequenceMatcher

    def _fuzz_ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100.0

_UUID_NAME = re.compile(
    r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def normalize_entity_name_key(name: str | None) -> str | None:
    """Collapse whitespace and lowercase; empty or UUID-shaped names return None (skip exact key)."""
    if name is None:
        return None
    s = " ".join(str(name).strip().split())
    if not s or _UUID_NAME.match(s):
        return None
    return s.lower()


def _alphanumeric_fold(name: str) -> str:
    """Lowercase letters and digits only (strip spaces/punctuation) for fuzzy comparison and bucketing."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def _pick_display_name(names: list[str]) -> str:
    names = [n for n in names if n and str(n).strip()]
    if not names:
        return ""
    return max(names, key=lambda x: (len(x), x))


def _merge_entity_group(
    graph_store: Neo4jPropertyGraphStore,
    eids: list[str],
    display_name: str,
    entity_key: str,
) -> None:
    survivor = eids[0]
    graph_store.structured_query(
        """
        UNWIND $eids AS eid
        MATCH (n) WHERE elementId(n) = eid
        WITH collect(n) AS nodes
        CALL apoc.refactor.mergeNodes(nodes, {mergeRels: true, properties: 'discard'})
        YIELD node
        RETURN count(node) AS c
        """,
        param_map={"eids": eids},
    )
    graph_store.structured_query(
        """
        MATCH (n) WHERE elementId(n) = $survivor
        SET n.name = $display_name, n.entity_key = $entity_key
        """,
        param_map={
            "survivor": survivor,
            "display_name": display_name,
            "entity_key": entity_key,
        },
    )


def _fetch_entity_rows(
    graph_store: Neo4jPropertyGraphStore,
) -> list[dict[str, Any]]:
    return graph_store.structured_query(
        """
        MATCH (n)
        WHERE (n:__Entity__ OR n:Entity)
          AND NOT n:Doc
          AND NOT n:ChunkNode
          AND coalesce(n.name, '') <> ''
        RETURN elementId(n) AS eid, n.id AS nid, n.name AS name
        """
    )


class _DSU:
    def __init__(self, n: int) -> None:
        self._p = list(range(n))

    def find(self, x: int) -> int:
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]
            x = self._p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._p[rb] = ra


def _pair_similar_enough(
    fold_a: str,
    fold_b: str,
    norm_a: str,
    norm_b: str,
    threshold: float,
) -> bool:
    r_fold = _fuzz_ratio(fold_a, fold_b) if fold_a and fold_b else 0.0
    r_norm = _fuzz_ratio(norm_a, norm_b) if norm_a and norm_b else 0.0
    r = max(r_fold, r_norm)
    if r < threshold:
        return False
    delta = abs(len(fold_a) - len(fold_b))
    if delta > 8 and r < 95.0:
        return False
    return True


def align_duplicate_entities(
    graph_store: Neo4jPropertyGraphStore,
) -> dict[str, int]:
    """
    Exact alignment: merge entities whose normalized name key matches.

    Returns:
        groups_merged, nodes_removed
    """
    rows = _fetch_entity_rows(graph_store)
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = normalize_entity_name_key(row.get("name"))
        if key is None:
            continue
        by_key[key].append(row)

    groups_merged = 0
    nodes_removed = 0
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: str(r.get("nid") or ""))
        eids = [str(r["eid"]) for r in group]
        names = [str(r.get("name") or "") for r in group]
        display = _pick_display_name(names)
        _merge_entity_group(graph_store, eids, display, key)
        groups_merged += 1
        nodes_removed += len(group) - 1

    return {"groups_merged": groups_merged, "nodes_removed": nodes_removed}


def fuzzy_align_duplicate_entities(
    graph_store: Neo4jPropertyGraphStore,
    *,
    threshold: float = 88.0,
    min_fold_len: int = 4,
) -> dict[str, int]:
    """
    Fuzzy alignment: on the **current** graph, merge entities with sufficiently similar names
    (typically after exact alignment).

    - Only consider folded alphanumeric strings at least ``min_fold_len`` to avoid merging short tokens.
    - Buckets reduce complexity; union-find merges transitive groups.

    Args:
        threshold: similarity 0–100 (same scale as rapidfuzz.ratio).
    """
    rows = _fetch_entity_rows(graph_store)
    records: list[dict[str, Any]] = []
    for row in rows:
        raw_name = str(row.get("name") or "")
        norm = normalize_entity_name_key(raw_name)
        if norm is None:
            continue
        fold = _alphanumeric_fold(raw_name)
        if len(fold) < min_fold_len:
            continue
        records.append(
            {
                "eid": str(row["eid"]),
                "nid": str(row.get("nid") or ""),
                "name": raw_name,
                "norm": norm,
                "fold": fold,
            }
        )

    n = len(records)
    if n < 2:
        return {"groups_merged": 0, "nodes_removed": 0}

    dsu = _DSU(n)
    by_block: dict[tuple[str, int], list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        f = rec["fold"]
        bid = (f[: min(4, len(f))], min(len(f) // 7, 40))
        by_block[bid].append(i)

    def _union_pairs_in_bucket(bucket: list[int]) -> None:
        if len(bucket) < 2:
            return
        if len(bucket) <= 120:
            for a in range(len(bucket)):
                ia = bucket[a]
                for b in range(a + 1, len(bucket)):
                    ib = bucket[b]
                    if dsu.find(ia) == dsu.find(ib):
                        continue
                    ra, rb = records[ia], records[ib]
                    if _pair_similar_enough(
                        ra["fold"], rb["fold"], ra["norm"], rb["norm"], threshold
                    ):
                        dsu.union(ia, ib)
            return
        sorted_idx = sorted(bucket, key=lambda i: len(records[i]["fold"]))
        window = 60
        for i, ia in enumerate(sorted_idx):
            for k in range(i + 1, min(i + 1 + window, len(sorted_idx))):
                ib = sorted_idx[k]
                if dsu.find(ia) == dsu.find(ib):
                    continue
                ra, rb = records[ia], records[ib]
                if _pair_similar_enough(
                    ra["fold"], rb["fold"], ra["norm"], rb["norm"], threshold
                ):
                    dsu.union(ia, ib)

    for idxs in by_block.values():
        if len(idxs) < 2:
            continue
        if len(idxs) > 200:
            sub: dict[str, list[int]] = defaultdict(list)
            for i in idxs:
                f = records[i]["fold"]
                sk = f[: min(8, len(f))]
                sub[sk].append(i)
            for grp in sub.values():
                _union_pairs_in_bucket(grp)
        else:
            _union_pairs_in_bucket(idxs)

    comp: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        comp[dsu.find(i)].append(i)

    groups_merged = 0
    nodes_removed = 0
    for members in comp.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda i: records[i]["nid"])
        group = [records[i] for i in members]
        eids = [g["eid"] for g in group]
        names = [g["name"] for g in group]
        display = _pick_display_name(names)
        canon_fold = _alphanumeric_fold(display)
        entity_key = canon_fold if canon_fold else group[0]["norm"]
        _merge_entity_group(graph_store, eids, display, entity_key)
        groups_merged += 1
        nodes_removed += len(group) - 1

    return {"groups_merged": groups_merged, "nodes_removed": nodes_removed}
