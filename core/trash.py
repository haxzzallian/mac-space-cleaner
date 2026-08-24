"""Moves confirmed items into ~/.Trash. Never a permanent delete.

This is a plain filesystem move into ~/.Trash (recoverable by opening Trash
in the Finder), not the Finder's "Put Back" mechanism specifically — that
tradeoff keeps this dependency-free (stdlib `shutil` only) while still making
every deletion fully reversible until the user empties Trash.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

TRASH_DIR = Path.home() / ".Trash"


def _unique_trash_path(name: str) -> Path:
    dest = TRASH_DIR / name
    if not dest.exists():
        return dest
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stem, dot, ext = name.partition(".")
    candidate = f"{stem}-{stamp}{dot}{ext}" if dot else f"{name}-{stamp}"
    return TRASH_DIR / candidate


def move_to_trash(path: Path) -> Path:
    """Move `path` into ~/.Trash, renaming on collision. Returns the new path."""
    TRASH_DIR.mkdir(exist_ok=True)
    dest = _unique_trash_path(path.name)
    shutil.move(str(path), str(dest))
    return dest
