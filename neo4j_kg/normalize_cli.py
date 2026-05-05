# -*- coding: utf-8 -*-
"""
Post-process an existing Neo4j graph: edge cleanup, optional entity alignment,
three-label normalization (no LLM calls).

Uses the same ``postprocess_regulation_property_graph`` as
``build_neo4j_kg.py`` and prints the same English summary
(``print_postprocess_report``).

From repo root::

    python -m neo4j_kg.normalize_cli
    python _normalize_three_labels.py
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext

from dotenv import load_dotenv

from .env import get_repo_root
from .neo4j_connect import connect_neo4j_graph_store
from .postprocess import (
    BROWSER_QUERY_DOC_CHUNK_ENTITY,
    BROWSER_QUERY_ENTITY_SUBGRAPH,
    postprocess_regulation_property_graph,
)
from .reporting import print_postprocess_report
from .run_logging import resolve_log_file, tee_stdio


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Neo4j regulation graph: optional entity alignment + "
        "three-label normalization (APOC required)."
    )
    p.add_argument(
        "--entity-align",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exact alignment: merge nodes whose normalized name matches. Default: on.",
    )
    p.add_argument(
        "--entity-fuzzy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fuzzy alignment (runs exact alignment first). Default: on.",
    )
    p.add_argument(
        "--entity-fuzzy-threshold",
        type=float,
        default=88.0,
        help="Fuzzy similarity threshold 0–100, default 88.",
    )
    p.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Also write stdout/stderr to this path; default "
        "logs/neo4j_kg_normalize_<timestamp>.log under repo root.",
    )
    p.add_argument(
        "--no-log",
        action="store_true",
        help="Do not write a log file; terminal only.",
    )
    p.add_argument(
        "--neo4j-database",
        type=str,
        default=None,
        help="Neo4j logical database name; overrides NEO4J_DATABASE env (default neo4j).",
    )
    return p


def _run_normalize(args: argparse.Namespace) -> None:
    load_dotenv(get_repo_root() / ".env")
    graph_store, neo4j_db = connect_neo4j_graph_store(database=args.neo4j_database)
    print(f"Neo4j database: {neo4j_db}", flush=True)
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


def main() -> None:
    args = _build_parser().parse_args()
    repo = get_repo_root()
    log_path = resolve_log_file(
        repo,
        args.log_file,
        args.no_log,
        prefix="neo4j_kg_normalize",
    )
    ctx = tee_stdio(log_path) if log_path is not None else nullcontext()
    with ctx:
        if log_path is not None:
            print(f"Log file: {log_path}", flush=True)
        _run_normalize(args)


if __name__ == "__main__":
    main()
