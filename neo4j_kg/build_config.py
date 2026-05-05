# -*- coding: utf-8 -*-
"""JSON build defaults for ``property_graph_cli``; CLI flags override the merged config."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .env import get_repo_root, resolve_repo_path

USER_BUILD_CONFIG_RELPATH = Path("config") / "build_neo4j_kg.json"
BUILD_CONFIG_EXAMPLE_RELPATH = Path("config") / "build_neo4j_kg.example.json"

DEFAULT_BUILD_CONFIG: dict[str, Any] = {
    "chunk_size": 512,
    "chunk_overlap": 50,
    "max_paths_per_chunk": 15,
    "num_workers": 2,
    "markdown_root": "data/regulation",
    "kg_extractor": "simple",
    "schema_config": None,
    "schema_relaxed": False,
    "schema_allow_additional_properties": True,
    "entity_align": True,
    "entity_fuzzy": True,
    "entity_fuzzy_threshold": 88.0,
    "llm_model": "gpt-4o-mini",
    "embedding_model": "text-embedding-3-small",
    "llm_temperature": 0.0,
    "neo4j_database": None,
}

ALLOWED_KEYS = frozenset(DEFAULT_BUILD_CONFIG.keys())


def peek_config_arg(argv: Sequence[str] | None = None) -> str | None:
    """Parse ``--config PATH`` from *argv* without consuming other arguments."""
    if argv is None:
        argv = sys.argv[1:]
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=str, default=None)
    ns, _ = pre.parse_known_args(argv)
    return ns.config


def resolve_effective_config_path(explicit: str | None) -> Path | None:
    """
    If *explicit* is set, resolve it like ``--config`` (repo-relative or absolute).

    Otherwise, if ``config/build_neo4j_kg.json`` exists under the repo root, use it.
    """
    if explicit:
        return resolve_repo_path(explicit)
    candidate = (get_repo_root() / USER_BUILD_CONFIG_RELPATH).resolve()
    return candidate if candidate.is_file() else None


def merge_file_into_defaults(path: Path | None) -> dict[str, Any]:
    """
    Start from :data:`DEFAULT_BUILD_CONFIG` and overlay keys from a JSON object file.

    Raises:
        FileNotFoundError: if *path* is set but not a file.
        ValueError: if JSON is not an object or contains unknown keys.
    """
    merged = dict(DEFAULT_BUILD_CONFIG)
    if path is None:
        return merged
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a JSON object: {path}")
    unknown = set(raw) - ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"Unknown config keys {sorted(unknown)} in {path}; "
            f"allowed: {sorted(ALLOWED_KEYS)}"
        )
    merged.update(raw)
    return merged
