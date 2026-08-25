"""Generic large-file/folder scanner, plus a dedicated pass over the user's
flagged-sensitive paths (config.SENSITIVE_PATHS — empty by default, set your
own in local_config.py, e.g. `[HOME / "Downloads" / "some-folder"]`).

`scan()` covers ordinary personal folders and explicitly excludes anything
under a sensitive path — that's handled separately by `scan_sensitive()` so
it always ends up in its own bannered report tier, never mixed in here.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

import config
from core.fsutil import path_size
from core.models import CleanupItem, Tier


def _is_under(path: Path, roots: List[Path]) -> bool:
    return any(path == r or r in path.parents for r in roots)


def _has_executable_bin_dir(path: Path) -> bool:
    bin_dir = path / "bin"
    if not bin_dir.is_dir():
        return False
    try:
        return any(entry.is_file() and os.access(entry, os.X_OK)
                   for entry in bin_dir.iterdir())
    except OSError:
        return False


def _looks_like_installed_tool(path: Path) -> bool:
    """True if `path` (or one of its immediate subfolders) has a bin/
    containing an executable — the near-universal shape of an installed
    SDK/CLI tool, whether direct (shorebird/bin/shorebird) or one level
    nested in a container folder (sdks/flutter/bin/flutter — exactly the
    shape that caused a real incident: `sdks` itself has no bin/, only its
    child `flutter` does). True whether or not the tool is currently on
    PATH or named in a shell rc file — defense-in-depth alongside
    core.protected's dynamic discovery, for tools that discovery wouldn't
    know about yet."""
    if _has_executable_bin_dir(path):
        return True
    try:
        children = [c for c in path.iterdir() if c.is_dir() and not c.is_symlink()]
    except OSError:
        return False
    return any(_has_executable_bin_dir(child) for child in children)


def _scan_root(root: Path, threshold: int, max_depth: int, skipped: List[str],
                skip_paths: List[Path] = ()) -> List[Path]:
    """Entries under `root` at/above `threshold` bytes. Stops descending once
    an entry itself clears the threshold, so we surface the biggest folder
    rather than every file inside it too.

    `skip_paths` are never flagged as a single blob and never descended into
    from here — used to exclude directories (like development/projects/)
    that a more precise, code-aware scanner already covers, so this generic
    pass doesn't produce a misleading "delete this whole folder" candidate
    for a live codebase.
    """
    hits: List[Path] = []
    skip_set = set(skip_paths)

    def walk(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = list(path.iterdir())
        except (PermissionError, FileNotFoundError, OSError) as exc:
            skipped.append(f"{path} ({exc.__class__.__name__})")
            return
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry in skip_set:
                continue
            if entry.is_dir() and _looks_like_installed_tool(entry):
                continue  # looks like an installed SDK/CLI tool — never a candidate
            size = path_size(entry, skipped)
            if size >= threshold:
                hits.append(entry)
            elif entry.is_dir():
                walk(entry, depth + 1)

    walk(root, 0)
    return hits


def scan(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    for root in config.LARGE_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in _scan_root(root, config.LARGE_FILE_THRESHOLD_BYTES,
                                config.LARGE_SCAN_MAX_DEPTH, skipped,
                                skip_paths=config.DEV_PROJECT_ROOTS):
            if _is_under(path, config.SENSITIVE_PATHS):
                continue  # handled separately, with its own banner
            size = path_size(path, skipped)
            mb = config.LARGE_FILE_THRESHOLD_BYTES // (1024 * 1024)
            items.append(CleanupItem(
                path=path, size_bytes=size, category="Large file/folder",
                tier=Tier.REVIEW,
                reason=f"Over the {mb}MB threshold in a personal folder — not a "
                       "known regenerable cache, so review before removing.",
                regenerable=False, is_dir=path.is_dir()))
    return items


def scan_sensitive(skipped: List[str]) -> List[CleanupItem]:
    """Large items inside config.SENSITIVE_PATHS — always its own tier/banner,
    always confirmed individually (see core.confirm)."""
    items: List[CleanupItem] = []
    threshold = config.SENSITIVE_SCAN_THRESHOLD_BYTES
    for root in config.SENSITIVE_PATHS:
        if not root.exists():
            continue
        for path in _scan_root(root, threshold, config.LARGE_SCAN_MAX_DEPTH, skipped):
            size = path_size(path, skipped)
            items.append(CleanupItem(
                path=path, size_bytes=size, category=f"Inside {root.name}",
                tier=Tier.SENSITIVE,
                reason=f"Located inside {root} — a folder you flagged as "
                       "valuable. Only ever removed with a separate, explicit, "
                       "per-item confirmation.",
                regenerable=False, is_dir=path.is_dir()))
    return items
