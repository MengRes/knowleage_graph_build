# -*- coding: utf-8 -*-
"""Compatibility entrypoint; same as ``python -m neo4j_kg.normalize_cli``."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from neo4j_kg.normalize_cli import main  # noqa: E402

if __name__ == "__main__":
    main()
