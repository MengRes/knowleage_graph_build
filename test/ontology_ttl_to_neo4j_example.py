# -*- coding: utf-8 -*-
"""
Read RDF ontology triples from Turtle (``.ttl``) and write a Neo4j property graph (example).

Mapping (simplified RDF → property graph):
- Each URI / blank node → one ``OntologyEntity`` node (configurable), ``uri`` is a stable string;
- Object is URI/blank → directed edge ``(subject)-[predicate_local_name]->(object)``;
- Object is literal → set property ``lit_<predicate_local_name>`` on the subject (prefix configurable).

Independent from LlamaIndex ``PropertyGraphIndex`` document–entity graphs; same Neo4j instance is fine.
Prefer ``--clean-ontology`` before import to delete only nodes tagged by this script, not the regulation graph.

Requires: ``rdflib``, ``neo4j`` driver, ``.env`` with ``NEO4J_URI`` / ``NEO4J_USER`` / ``NEO4J_PASSWORD``.

Example (from repo root)::

    pip install rdflib neo4j
    python test/ontology_ttl_to_neo4j_example.py \\
        --ttl data/ontology_example/regulation_mini_ontology.ttl \\
        --clean-ontology

    python test/ontology_ttl_to_neo4j_example.py \\
        --config ontology_graph_config.example.json \\
        --clean-ontology

Two levels of “ontology-backed graph”:
1. **Structure graph (this script)**: import OWL/RDFS classes, properties, axioms for query/alignment.
2. **Constrained extraction**: use semantics to constrain LLM/rule output (read the same TTL in your pipeline).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from neo4j_kg.env import get_repo_root, load_repo_dotenv, require_env  # noqa: E402


def _safe_rel_type(predicate_iri: str, max_len: int = 60) -> str:
    """Neo4j relationship type: must start with a letter; alphanumeric and underscore only."""
    if "#" in predicate_iri:
        name = predicate_iri.rsplit("#", 1)[-1]
    else:
        name = predicate_iri.rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not name:
        name = "related"
    if name[0].isdigit():
        name = "P_" + name
    if not name[0].isalpha():
        name = "P_" + name.lstrip("_")
    return name[:max_len]


def _safe_prop_key(predicate_iri: str, prefix: str, max_len: int = 80) -> str:
    base = _safe_rel_type(predicate_iri, max_len=max_len - len(prefix))
    key = f"{prefix}{base.lower()}"
    return key[:max_len]


def _term_uri(term: Any) -> str:
    from rdflib import BNode, URIRef

    if isinstance(term, URIRef):
        return str(term)
    if isinstance(term, BNode):
        return f"_:{term}"
    raise TypeError(f"Expected URIRef or BNode, got {type(term)}")


_NEO4J_LABEL_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _assert_neo4j_label(label: str) -> str:
    if not _NEO4J_LABEL_OK.match(label):
        raise ValueError(
            f"Invalid Neo4j node label (letter first, alphanumeric/underscore only): {label!r}"
        )
    return label


def _resolve_single_ttl(repo: Path, ttl_arg: Path) -> list[Path]:
    tp = ttl_arg if ttl_arg.is_absolute() else (repo / ttl_arg)
    return [tp.resolve()]


def import_ttl_files_to_neo4j(
    *,
    ttl_paths: list[Path],
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    node_label: str = "OntologyEntity",
    literal_prefix: str = "lit_",
    source_tag: str = "ontology_import",
    clean_ontology: bool = False,
) -> tuple[int, int]:
    """
    Returns:
        (triple_count, total statement count in rdflib graph)
    """
    from rdflib import BNode, Graph, Literal, URIRef
    from neo4j import GraphDatabase

    node_label = _assert_neo4j_label(node_label)

    g = Graph()
    for p in ttl_paths:
        if not p.is_file():
            raise FileNotFoundError(f"TTL file not found: {p}")
        g.parse(p, format="turtle")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    triple_count = 0

    with driver.session() as session:
        if clean_ontology:
            session.run(
                f"MATCH (n:{node_label}) WHERE n._source = $tag DETACH DELETE n",
                tag=source_tag,
            )

        for s, p, o in g:
            triple_count += 1
            suri = _term_uri(s)

            session.run(
                f"""
                MERGE (a:{node_label} {{uri: $uri}})
                SET a._source = $tag
                """,
                uri=suri,
                tag=source_tag,
            )

            pred = str(p)
            if isinstance(o, Literal):
                prop = _safe_prop_key(pred, literal_prefix)
                val = o.toPython()
                if isinstance(val, (list, dict)):
                    val = str(val)
                session.run(
                    f"""
                    MERGE (a:{node_label} {{uri: $uri}})
                    SET a._source = $tag, a[$prop] = $val
                    """,
                    uri=suri,
                    tag=source_tag,
                    prop=prop,
                    val=val,
                )
            elif isinstance(o, (URIRef, BNode)):
                ouri = _term_uri(o)
                rel = _safe_rel_type(pred)
                session.run(
                    f"""
                    MERGE (a:{node_label} {{uri: $suri}})
                    SET a._source = $tag
                    MERGE (b:{node_label} {{uri: $ouri}})
                    SET b._source = $tag
                    MERGE (a)-[r:`{rel}`]->(b)
                    """,
                    suri=suri,
                    ouri=ouri,
                    tag=source_tag,
                )
            else:
                continue

    driver.close()
    n_stmts = len(g)
    return triple_count, n_stmts


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Import TTL ontology into Neo4j (OntologyEntity subgraph; "
        "independent from regulation pipeline)."
    )
    p.add_argument(
        "--ttl",
        type=Path,
        default=None,
        help="Single Turtle file path (relative to repo root or absolute).",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="JSON config with ttl_files / node_label / literal_property_prefix.",
    )
    p.add_argument(
        "--clean-ontology",
        action="store_true",
        help="Before import: delete nodes imported by this script (_source = 'ontology_import'; "
        "label from --node-label).",
    )
    p.add_argument(
        "--node-label",
        type=str,
        default="OntologyEntity",
        help="Neo4j node label, default OntologyEntity.",
    )
    p.add_argument(
        "--literal-prefix",
        type=str,
        default="lit_",
        help="Property name prefix for literal object predicates.",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    load_repo_dotenv()
    repo = get_repo_root()

    node_label = args.node_label
    literal_prefix = args.literal_prefix
    if args.config:
        cfg_file = (
            args.config if args.config.is_absolute() else (repo / args.config)
        ).resolve()
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        node_label = cfg.get("node_label", node_label)
        literal_prefix = cfg.get("literal_property_prefix", literal_prefix)
        ttl_paths = []
        for p in cfg.get("ttl_files") or []:
            pp = Path(p)
            ttl_paths.append(
                pp.resolve() if pp.is_absolute() else (repo / pp).resolve()
            )
        if not ttl_paths:
            parser.error("Config file has empty ttl_files")
    elif args.ttl:
        ttl_paths = _resolve_single_ttl(repo, args.ttl)
    else:
        parser.error("Specify --ttl or --config")

    neo4j_uri = require_env("NEO4J_URI")
    neo4j_user = require_env("NEO4J_USER")
    neo4j_password = require_env("NEO4J_PASSWORD")

    n_triples, n_graph_len = import_ttl_files_to_neo4j(
        ttl_paths=ttl_paths,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        node_label=node_label,
        literal_prefix=literal_prefix,
        clean_ontology=args.clean_ontology,
    )
    print(f"Processed triples: {n_triples} (rdflib graph statements: {n_graph_len})")
    print(f"Node label: {node_label}; literal property prefix: {literal_prefix}")
    print("Neo4j Browser example:")
    print(
        f"MATCH (n:{node_label}) WHERE n._source = 'ontology_import' "
        "RETURN n LIMIT 200;"
    )


if __name__ == "__main__":
    main()
