# -*- coding: utf-8 -*-
"""Shared Neo4j ``Neo4jPropertyGraphStore`` construction from environment variables."""
from __future__ import annotations

from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore

from .env import get_neo4j_database, require_env


def connect_neo4j_graph_store(*, database: str | None = None) -> tuple[Neo4jPropertyGraphStore, str]:
    """Return ``(store, logical_database_name)`` using ``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PASSWORD``."""
    neo4j_uri = require_env("NEO4J_URI")
    neo4j_user = require_env("NEO4J_USER")
    neo4j_password = require_env("NEO4J_PASSWORD")
    neo4j_db = (database or "").strip() or get_neo4j_database()
    store = Neo4jPropertyGraphStore(
        username=neo4j_user,
        password=neo4j_password,
        url=neo4j_uri,
        database=neo4j_db,
    )
    return store, neo4j_db
