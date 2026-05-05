# -*- coding: utf-8 -*-
"""LlamaIndex PropertyGraphIndex: chunking, configurable KG path extractors, Neo4j persistence."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from enum import StrEnum
except ImportError:  # Python < 3.11
    from enum import Enum as _Enum

    class StrEnum(str, _Enum):  # type: ignore[misc]
        """stdlib StrEnum (3.11+) backport for older interpreters."""

from llama_index.core import Document, PropertyGraphIndex, Settings
from llama_index.core.indices.property_graph import (
    DynamicLLMPathExtractor,
    ImplicitPathExtractor,
    SchemaLLMPathExtractor,
    SimpleLLMPathExtractor,
)
from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
from llama_index.core.graph_stores.types import PropertyGraphStore
from llama_index.core.llms.llm import LLM
from llama_index.core.node_parser import SentenceSplitter

def property_graph_triplet_count(store: PropertyGraphStore) -> int:
    """Count triplets in the store (handles Simple vs Neo4j ``get_triplets`` semantics)."""
    if isinstance(store, SimplePropertyGraphStore):
        return len(store.graph.triplets)
    return len(store.get_triplets())


KG_EXTRACTOR_CHOICES: tuple[str, ...] = (
    "simple",
    "dynamic",
    "schema",
    "implicit",
    "simple_implicit",
)


@dataclass(frozen=True)
class SchemaKGConfig:
    """
    Configuration for :class:`SchemaLLMPathExtractor` (entity/relation vocab + allowed triple shapes).

    ``validation_triples`` lists allowed ``(subject_entity_type, relation_type, object_entity_type)``
    tuples. Values must match strings in ``entities`` / ``relations``.

    When ``strict=True`` on the extractor, triples not in ``validation_triples`` are dropped.
    If you omit ``validation_triples`` (empty list), use ``schema_strict=False`` so the model can
    still emit triples without being filtered against LlamaIndex defaults.
    """

    entities: list[str]
    relations: list[str]
    validation_triples: list[tuple[str, str, str]]


def load_schema_kg_config(path: str | Path) -> SchemaKGConfig:
    """Load :class:`SchemaKGConfig` from JSON (see ``schema_kg_config.example.json``)."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    entities = list(raw.get("entities") or [])
    relations = list(raw.get("relations") or [])
    if not entities or not relations:
        raise ValueError(
            f"{p}: JSON must include non-empty 'entities' and 'relations' lists"
        )
    triples_raw = raw.get("validation_triples") or []
    triples: list[tuple[str, str, str]] = []
    for i, row in enumerate(triples_raw):
        if len(row) != 3:
            raise ValueError(f"{p}: validation_triples[{i}] must be [subject_type, relation, object_type]")
        a, b, c = str(row[0]), str(row[1]), str(row[2])
        triples.append((a, b, c))
    ent_set, rel_set = set(entities), set(relations)
    for i, (a, b, c) in enumerate(triples):
        if a not in ent_set or c not in ent_set:
            raise ValueError(
                f"{p}: validation_triples[{i}] uses unknown entity type in {a!r}, {c!r}"
            )
        if b not in rel_set:
            raise ValueError(f"{p}: validation_triples[{i}] uses unknown relation {b!r}")
    return SchemaKGConfig(
        entities=entities,
        relations=relations,
        validation_triples=triples,
    )


def _unique_str_enum(name: str, values: list[str]) -> type:
    """Build a :class:`StrEnum` with stable string values (names sanitized for Python)."""
    members: dict[str, str] = {}
    used: set[str] = set()

    def member_name(label: str) -> str:
        s = re.sub(r"[^0-9A-Za-z_]", "_", label.strip())
        if not s:
            s = "LABEL"
        if s[0].isdigit():
            s = "T_" + s
        base, n = s, 0
        while s in used:
            n += 1
            s = f"{base}_{n}"
        used.add(s)
        return s

    for v in values:
        members[member_name(v)] = v
    return StrEnum(name, members)  # type: ignore[arg-type]


def build_kg_extractors(
    kind: str,
    *,
    llm: LLM,
    max_paths_per_chunk: int,
    num_workers: int,
    schema_strict: bool = True,
    schema_allow_additional_properties: bool = True,
    schema_config: SchemaKGConfig | None = None,
) -> list:
    """
    Instantiate one or more LlamaIndex property-graph path extractors.

    - ``simple``: :class:`SimpleLLMPathExtractor` (default triplet template).
    - ``dynamic``: :class:`DynamicLLMPathExtractor` (flexible JSON / head-tail-relation).
    - ``schema``: :class:`SchemaLLMPathExtractor` (typed entities/relations; optional :class:`SchemaKGConfig`).
    - ``implicit``: :class:`ImplicitPathExtractor` only (chunk ``prev``/``next`` / structural edges; no LLM).
    - ``simple_implicit``: ``SimpleLLMPathExtractor`` then ``ImplicitPathExtractor`` (KG + chunk order links).

    Args:
        kind: One of :data:`KG_EXTRACTOR_CHOICES`.
        llm: Used by all LLM-based extractors (still passed to ``PropertyGraphIndex`` for implicit-only runs).
        max_paths_per_chunk: ``max_paths_per_chunk`` for ``simple``; ``max_triplets_per_chunk`` for ``dynamic``/``schema``.
        num_workers: Parallel workers for LLM extractors.
        schema_strict: Passed to ``SchemaLLMPathExtractor`` (stricter validation when ``True``).
        schema_allow_additional_properties: Passed to ``SchemaLLMPathExtractor`` (set ``False`` for some strict JSON-schema APIs).
        schema_config: For ``kind=='schema'`` only: custom entity/relation labels and ``validation_triples``.
            If ``None``, uses LlamaIndex built-in default schema (PRODUCT, PERSON, …).
    """
    key = kind.strip().lower().replace("-", "_")
    if key not in KG_EXTRACTOR_CHOICES:
        raise ValueError(
            f"Unknown kg extractor {kind!r}; expected one of {KG_EXTRACTOR_CHOICES}"
        )

    if key == "simple":
        return [
            SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=max_paths_per_chunk,
                num_workers=num_workers,
            )
        ]
    if key == "dynamic":
        return [
            DynamicLLMPathExtractor(
                llm=llm,
                max_triplets_per_chunk=max_paths_per_chunk,
                num_workers=num_workers,
            )
        ]
    if key == "schema":
        schema_kwargs: dict[str, Any] = dict(
            llm=llm,
            max_triplets_per_chunk=max_paths_per_chunk,
            num_workers=num_workers,
            strict=schema_strict,
            allow_additional_properties=schema_allow_additional_properties,
        )
        if schema_config is not None:
            schema_kwargs["possible_entities"] = _unique_str_enum(
                "KgSchemaEntity", schema_config.entities
            )
            schema_kwargs["possible_relations"] = _unique_str_enum(
                "KgSchemaRelation", schema_config.relations
            )
            if schema_config.validation_triples:
                schema_kwargs["kg_validation_schema"] = list(
                    schema_config.validation_triples
                )
        return [SchemaLLMPathExtractor(**schema_kwargs)]
    if key == "implicit":
        return [ImplicitPathExtractor()]
    if key == "simple_implicit":
        return [
            SimpleLLMPathExtractor(
                llm=llm,
                max_paths_per_chunk=max_paths_per_chunk,
                num_workers=num_workers,
            ),
            ImplicitPathExtractor(),
        ]
    raise ValueError(f"Unhandled kg extractor {kind!r}")


def build_regulation_property_graph_index(
    *,
    graph_store: PropertyGraphStore,
    documents: list[Document],
    llm: LLM,
    embed_model,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    max_paths_per_chunk: int = 15,
    num_workers: int = 2,
    kg_extractor: str = "simple",
    schema_strict: bool = True,
    schema_allow_additional_properties: bool = True,
    schema_config: SchemaKGConfig | None = None,
    schema_config_path: str | Path | None = None,
) -> tuple[PropertyGraphIndex, int]:
    """
    Chunk → configured path extractor(s) → ``PropertyGraphIndex`` persisted to ``graph_store``
    (``Neo4jPropertyGraphStore`` or in-memory ``SimplePropertyGraphStore`` for local snapshots).

    Args:
        kg_extractor: See :func:`build_kg_extractors` (``simple`` | ``dynamic`` | ``schema`` | ``implicit`` | ``simple_implicit``).
        max_paths_per_chunk: For ``simple`` this is ``max_paths_per_chunk``; for ``dynamic``/``schema`` it maps to ``max_triplets_per_chunk``.
        schema_config: In-memory schema for ``SchemaLLMPathExtractor`` (overrides LlamaIndex defaults).
        schema_config_path: Load :class:`SchemaKGConfig` from this JSON file. If both ``schema_config`` and
            ``schema_config_path`` are set, ``schema_config`` wins.

    Returns:
        (index, triplet count)
    """
    resolved_schema: SchemaKGConfig | None = schema_config
    if resolved_schema is None and schema_config_path is not None:
        resolved_schema = load_schema_kg_config(schema_config_path)

    Settings.llm = llm
    Settings.embed_model = embed_model

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = splitter.get_nodes_from_documents(documents)
    extractors = build_kg_extractors(
        kg_extractor,
        llm=llm,
        max_paths_per_chunk=max_paths_per_chunk,
        num_workers=num_workers,
        schema_strict=schema_strict,
        schema_allow_additional_properties=schema_allow_additional_properties,
        schema_config=resolved_schema,
    )
    index = PropertyGraphIndex(
        nodes=nodes,
        llm=llm,
        embed_model=embed_model,
        property_graph_store=graph_store,
        kg_extractors=extractors,
        show_progress=True,
    )
    n_triplets = property_graph_triplet_count(graph_store)
    return index, n_triplets
