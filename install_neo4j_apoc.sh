#!/usr/bin/env bash
# Download APOC core JAR into repo .neo4j/plugins (matches server.directories.plugins in .neo4j/conf/neo4j.conf).
# Neo4j and APOC versions should be roughly aligned; after brew neo4j upgrades, bump APOC_VERSION and re-run.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
PLUGINS_DIR="$REPO_ROOT/.neo4j/plugins"
APOC_VERSION="${APOC_VERSION:-2026.03.1}"
JAR="apoc-${APOC_VERSION}-core.jar"
URL="https://github.com/neo4j/apoc/releases/download/${APOC_VERSION}/${JAR}"
mkdir -p "$PLUGINS_DIR"
echo "Downloading $URL -> $PLUGINS_DIR/$JAR"
curl -fsSL -o "$PLUGINS_DIR/$JAR" "$URL"
echo "Done. Restart Neo4j (e.g. ./start_neo4j_graphrag.sh restart)."
