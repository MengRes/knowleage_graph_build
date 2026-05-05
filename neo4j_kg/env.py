# -*- coding: utf-8 -*-
"""Repository root, ``.env`` loading, and required environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def get_repo_root() -> Path:
    """Project repo root (this file lives under ``neo4j_kg/``)."""
    return Path(__file__).resolve().parent.parent


def resolve_repo_path(rel_or_abs: str) -> Path:
    """Resolve *rel_or_abs* against :func:`get_repo_root` when not already absolute."""
    root = get_repo_root()
    p = Path(rel_or_abs)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def load_repo_dotenv() -> None:
    load_dotenv(get_repo_root() / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_neo4j_database() -> str:
    """Neo4j 5+ logical database name (default ``neo4j``); set ``NEO4J_DATABASE`` for another graph on the same server."""
    name = os.getenv("NEO4J_DATABASE", "neo4j").strip()
    return name or "neo4j"
