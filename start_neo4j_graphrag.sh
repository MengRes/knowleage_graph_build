#!/usr/bin/env bash
# Start Homebrew Neo4j with repo-local .neo4j data dir (GraphRAG helper).
# Usage: ./start_neo4j_graphrag.sh start|stop|status|restart
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
export NEO4J_CONF="$REPO_ROOT/.neo4j/conf"
NEO4J_BIN="$(command -v neo4j || true)"
if [ -z "$NEO4J_BIN" ]; then
  echo "neo4j not found; install it first (e.g. brew install neo4j)" >&2
  exit 1
fi
exec "$NEO4J_BIN" "$@"
