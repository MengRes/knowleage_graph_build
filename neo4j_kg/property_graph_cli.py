# -*- coding: utf-8 -*-
"""CLI implementation for ``build_neo4j_kg`` (argparse + pipelines)."""
from __future__ import annotations

import argparse
import sys
from contextlib import nullcontext
from typing import Any

from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

from .build_config import (
    BUILD_CONFIG_EXAMPLE_RELPATH,
    merge_file_into_defaults,
    peek_config_arg,
    resolve_effective_config_path,
)
from .build_index import KG_EXTRACTOR_CHOICES, build_regulation_property_graph_index
from .documents import load_regulation_docs
from .env import get_repo_root, load_repo_dotenv, require_env, resolve_repo_path
from .kg_snapshot import (
    DEFAULT_GRAPH_SNAPSHOT_SUBDIR,
    load_property_graph_snapshot,
    push_snapshot_to_neo4j,
    save_property_graph_snapshot,
)
from .neo4j_connect import connect_neo4j_graph_store
from .postprocess import (
    BROWSER_QUERY_DOC_CHUNK_ENTITY,
    BROWSER_QUERY_ENTITY_SUBGRAPH,
    clear_graph,
    postprocess_regulation_property_graph,
)
from .reporting import print_postprocess_report
from .run_logging import resolve_log_file, tee_stdio


def build_parser(cfg: dict[str, Any]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build PropertyGraphIndex from regulation docs and write to Neo4j."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "JSON build defaults (chunking, models, paths, entity flags). "
            "Repo-relative or absolute; see template "
            f"{BUILD_CONFIG_EXAMPLE_RELPATH.as_posix()}. "
            "If omitted and config/build_neo4j_kg.json exists, that file is loaded. "
            "CLI flags override merged values."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Before import: delete all nodes and relationships in the current Neo4j database.",
    )
    parser.add_argument(
        "--markdown-root",
        type=str,
        default=cfg["markdown_root"],
        metavar="DIR",
        help="Directory of Markdown sources (repo-relative or absolute).",
    )
    parser.add_argument(
        "--all-docs",
        action="store_true",
        help="Process every .md file under --markdown-root.",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Process only this file name relative to --markdown-root "
        "(e.g. rag_intro_test.md).",
    )
    parser.add_argument(
        "--entity-align",
        action=argparse.BooleanOptionalAction,
        default=cfg["entity_align"],
        help="Exact alignment: merge entities with identical normalized name (APOC). Default: on.",
    )
    parser.add_argument(
        "--entity-fuzzy",
        action=argparse.BooleanOptionalAction,
        default=cfg["entity_fuzzy"],
        help="Fuzzy alignment after exact (rapidfuzz recommended). Default: on.",
    )
    parser.add_argument(
        "--entity-fuzzy-threshold",
        type=float,
        default=cfg["entity_fuzzy_threshold"],
        help="Fuzzy similarity threshold 0–100 (rapidfuzz.ratio scale).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=cfg["chunk_size"],
        metavar="N",
        help="SentenceSplitter chunk size (characters).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=cfg["chunk_overlap"],
        metavar="N",
        help="SentenceSplitter chunk overlap (characters).",
    )
    parser.add_argument(
        "--max-paths-per-chunk",
        type=int,
        default=cfg["max_paths_per_chunk"],
        metavar="N",
        help="Max paths/triplets per chunk for LLM path extractors.",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=cfg["num_workers"],
        metavar="N",
        help="Parallel workers for applicable extractors.",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=cfg["llm_model"],
        metavar="NAME",
        help="OpenAI chat model for extraction.",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=cfg["embedding_model"],
        metavar="NAME",
        help="OpenAI embedding model for PropertyGraphIndex.",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=cfg["llm_temperature"],
        metavar="T",
        help="Sampling temperature for the chat model.",
    )
    parser.add_argument(
        "--kg-extractor",
        type=str,
        default=cfg["kg_extractor"],
        choices=KG_EXTRACTOR_CHOICES,
        help=(
            "Property-graph path extractor(s): simple=SimpleLLMPathExtractor; "
            "dynamic=DynamicLLMPathExtractor; schema=SchemaLLMPathExtractor (typed schema); "
            "implicit=ImplicitPathExtractor only (chunk prev/next edges, no LLM triples); "
            "simple_implicit=simple then implicit."
        ),
    )
    parser.add_argument(
        "--schema-config",
        type=str,
        default=cfg["schema_config"],
        help=(
            "JSON file for SchemaLLMPathExtractor: entities, relations, validation_triples "
            "(see neo4j_kg/schema_kg_config.example.json). "
            "Path relative to repo root or absolute. Only used when --kg-extractor schema."
        ),
    )
    parser.add_argument(
        "--schema-relaxed",
        action=argparse.BooleanOptionalAction,
        default=cfg["schema_relaxed"],
        help=(
            "With schema extractor: strict=False (allow types outside validation_triples filtering). "
            "Useful if validation_triples is empty or incomplete."
        ),
    )
    parser.add_argument(
        "--schema-allow-additional-properties",
        action=argparse.BooleanOptionalAction,
        default=cfg["schema_allow_additional_properties"],
        help="Schema extractor JSON schema: allow properties not listed (default: on).",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Also tee stdout/stderr to this path; default "
        "logs/neo4j_kg_build_<timestamp>.log under repo root.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not write a log file; terminal only.",
    )
    parser.add_argument(
        "--neo4j-database",
        type=str,
        default=cfg["neo4j_database"],
        help=(
            "Neo4j logical database name (Neo4j 5+). Overrides env NEO4J_DATABASE; "
            "default is 'neo4j'. Create DBs in Browser: CREATE DATABASE mygraph IF NOT EXISTS;"
        ),
    )
    parser.add_argument(
        "--save-kg",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "After LLM extraction: persist graph to this JSON file (LlamaIndex property graph format). "
            "If not --local-only, snapshot is written then pushed to Neo4j (single extraction pass). "
            f"Typical path under repo root: {DEFAULT_GRAPH_SNAPSHOT_SUBDIR}/<name>.json "
            "(avoid mixing with Markdown demos in data/kg_snapshots/)."
        ),
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help=(
            "Extract into memory only and save with --save-kg; do not connect to Neo4j "
            "(NEO4J_* not required). Implies no postprocess here."
        ),
    )
    parser.add_argument(
        "--load-kg",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Skip LLM extraction: load a JSON snapshot from --save-kg and upsert into Neo4j, "
            "then run postprocess. Requires NEO4J_*; OPENAI_API_KEY not used."
        ),
    )
    return parser


def run_load_snapshot_pipeline(args: argparse.Namespace) -> None:
    load_repo_dotenv()
    graph_store, neo4j_db = connect_neo4j_graph_store(database=args.neo4j_database)
    print(f"Neo4j database: {neo4j_db}")

    snap_path = resolve_repo_path(args.load_kg)
    simple = load_property_graph_snapshot(snap_path)
    print(f"Loaded KG snapshot: {snap_path} ({len(simple.graph.triplets)} triplet edges)")

    if args.clean:
        print("--clean: clearing all nodes and relationships in Neo4j ...")
        clear_graph(graph_store)
        print("Graph cleared.")

    pushed = push_snapshot_to_neo4j(simple, graph_store)
    print(
        "Pushed to Neo4j: "
        f"nodes={pushed['nodes']}, relations={pushed['relations']}, "
        f"triplet_edges={pushed['triplet_edges']}"
    )

    stats = postprocess_regulation_property_graph(
        graph_store,
        entity_align=args.entity_align or args.entity_fuzzy,
        entity_fuzzy=args.entity_fuzzy,
        entity_fuzzy_threshold=args.entity_fuzzy_threshold,
    )
    print_postprocess_report(
        stats,
        entity_align=args.entity_align or args.entity_fuzzy,
        entity_fuzzy=args.entity_fuzzy,
        browser_entity_subgraph=BROWSER_QUERY_ENTITY_SUBGRAPH,
        browser_doc_chunk_entity=BROWSER_QUERY_DOC_CHUNK_ENTITY,
    )


def run_extract_pipeline(args: argparse.Namespace) -> None:
    load_repo_dotenv()

    openai_api_key = require_env("OPENAI_API_KEY")
    llm = OpenAI(
        model=args.llm_model,
        api_key=openai_api_key,
        temperature=args.llm_temperature,
    )
    embed_model = OpenAIEmbedding(model=args.embedding_model, api_key=openai_api_key)

    use_simple = bool(args.save_kg) or args.local_only
    if args.local_only and not args.save_kg:
        raise SystemExit("--local-only requires --save-kg")

    neo_store = None
    neo4j_db = None
    if not args.local_only:
        neo_store, neo4j_db = connect_neo4j_graph_store(database=args.neo4j_database)
        print(f"Neo4j database: {neo4j_db}")
        if args.clean:
            print("--clean: clearing all nodes and relationships in Neo4j ...")
            clear_graph(neo_store)
            print("Graph cleared.")

    regulation_dir = resolve_repo_path(args.markdown_root)
    source_paths, documents = load_regulation_docs(
        regulation_dir,
        all_docs=args.all_docs,
        file_name=args.file,
    )
    print("Input files:")
    for p in source_paths:
        print(f"- {p}")

    schema_path = None
    if args.schema_config:
        schema_path = resolve_repo_path(args.schema_config)

    print(
        "Building PropertyGraphIndex "
        f"(kg-extractor={args.kg_extractor}"
        f"{', schema-config=' + str(schema_path) if schema_path else ''}) ..."
    )

    if use_simple:
        simple = SimplePropertyGraphStore()
        _, n_triplets = build_regulation_property_graph_index(
            graph_store=simple,
            documents=documents,
            llm=llm,
            embed_model=embed_model,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            max_paths_per_chunk=args.max_paths_per_chunk,
            num_workers=args.num_workers,
            kg_extractor=args.kg_extractor,
            schema_config_path=schema_path,
            schema_strict=not args.schema_relaxed,
            schema_allow_additional_properties=args.schema_allow_additional_properties,
        )
        print(f"Done. Triplet edges in graph: {n_triplets}")
        assert args.save_kg
        out_path = resolve_repo_path(args.save_kg)
        save_property_graph_snapshot(simple, out_path)
        print(f"Saved KG snapshot: {out_path}")
        if args.local_only:
            return
        assert neo_store is not None
        pushed = push_snapshot_to_neo4j(simple, neo_store)
        print(
            "Pushed to Neo4j: "
            f"nodes={pushed['nodes']}, relations={pushed['relations']}, "
            f"triplet_edges={pushed['triplet_edges']}"
        )
        graph_store = neo_store
    else:
        assert neo_store is not None
        _, n_triplets = build_regulation_property_graph_index(
            graph_store=neo_store,
            documents=documents,
            llm=llm,
            embed_model=embed_model,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            max_paths_per_chunk=args.max_paths_per_chunk,
            num_workers=args.num_workers,
            kg_extractor=args.kg_extractor,
            schema_config_path=schema_path,
            schema_strict=not args.schema_relaxed,
            schema_allow_additional_properties=args.schema_allow_additional_properties,
        )
        print(f"Done. Triplet count (entity subgraph query): {n_triplets}")
        graph_store = neo_store

    stats = postprocess_regulation_property_graph(
        graph_store,
        entity_align=args.entity_align or args.entity_fuzzy,
        entity_fuzzy=args.entity_fuzzy,
        entity_fuzzy_threshold=args.entity_fuzzy_threshold,
    )
    print_postprocess_report(
        stats,
        entity_align=args.entity_align or args.entity_fuzzy,
        entity_fuzzy=args.entity_fuzzy,
        browser_entity_subgraph=BROWSER_QUERY_ENTITY_SUBGRAPH,
        browser_doc_chunk_entity=BROWSER_QUERY_DOC_CHUNK_ENTITY,
    )


def run_pipeline(args: argparse.Namespace) -> None:
    if args.load_kg:
        run_load_snapshot_pipeline(args)
    else:
        run_extract_pipeline(args)


def main() -> None:
    raw_config = peek_config_arg(sys.argv[1:])
    cfg_path = resolve_effective_config_path(raw_config)
    merged = merge_file_into_defaults(cfg_path)
    parser = build_parser(merged)
    args = parser.parse_args()
    if args.load_kg and (args.save_kg or args.local_only):
        parser.error("--load-kg cannot be combined with --save-kg or --local-only")
    repo = get_repo_root()
    log_path = resolve_log_file(
        repo,
        args.log_file,
        args.no_log,
        prefix="neo4j_kg_build",
    )
    ctx = tee_stdio(log_path) if log_path is not None else nullcontext()
    with ctx:
        if log_path is not None:
            print(f"Log file: {log_path}", flush=True)
        run_pipeline(args)


if __name__ == "__main__":
    main()
