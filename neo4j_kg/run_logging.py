# -*- coding: utf-8 -*-
"""Tee stdout/stderr to a UTF-8 log file while keeping console output."""
from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, TextIO


class _Tee(TextIO):
    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, s: str) -> int:
        for st in self._streams:
            st.write(s)
            st.flush()
        return len(s)

    def flush(self) -> None:
        for st in self._streams:
            st.flush()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return self._streams[0].isatty() if self._streams else False

    def fileno(self) -> int:
        """Delegate so tqdm / multiprocessing can obtain a real FD when tee wraps TTY."""
        primary = self._streams[0]
        if hasattr(primary, "fileno"):
            return int(primary.fileno())
        raise OSError("Stream has no fileno")


def default_log_path(repo_root: Path, *, prefix: str) -> Path:
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{prefix}_{ts}.log"


def resolve_log_file(
    repo_root: Path,
    log_file: str | None,
    no_log: bool,
    *,
    prefix: str,
) -> Path | None:
    """Return absolute log path, or None if ``no_log``."""
    if no_log:
        return None
    if log_file:
        p = Path(log_file)
        return (p.resolve() if p.is_absolute() else (repo_root / p).resolve())
    return default_log_path(repo_root, prefix=prefix)


@contextmanager
def tee_stdio(log_path: Path) -> Generator[None, None, None]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    f = log_path.open("w", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(old_out, f)
    sys.stderr = _Tee(old_err, f)
    try:
        yield
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        f.close()
