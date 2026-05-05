# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from llama_index.core import Document


def load_regulation_docs(
    regulation_dir: Path,
    *,
    all_docs: bool,
    file_name: str | None,
) -> tuple[list[Path], list[Document]]:
    """Load Markdown under ``data/regulation``; set ``metadata["source_file"]`` to the file name."""
    md_files = sorted(regulation_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found under {regulation_dir}")

    if file_name:
        target = regulation_dir / file_name
        if not target.exists():
            raise FileNotFoundError(f"Requested file does not exist: {target}")
        selected = [target]
    elif all_docs:
        selected = md_files
    else:
        selected = [md_files[0]]

    documents = [
        Document(
            text=path.read_text(encoding="utf-8"),
            metadata={"source_file": path.name},
        )
        for path in selected
    ]
    return selected, documents
