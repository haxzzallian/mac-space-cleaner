"""Filesystem helpers shared by the scanners.

Every size computation swallows PermissionError/OSError on individual entries
(recording them into a shared `skipped` list) instead of raising, so one
locked file under ~/Library/Caches never aborts an entire scan.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional


def _actual_bytes(st: os.stat_result) -> int:
    """Actual disk usage for a stat result, in bytes — st_blocks * 512, the
    same thing `du` reports.

    Deliberately NOT st_size: a sparse file (e.g. Docker Desktop's
    Docker.raw VM disk) can report a huge logical st_size — sometimes
    hundreds of GB — while occupying only a few GB of real disk blocks.
    Summing st_size for those inflates totals by 10-100x versus what
    deleting the file would actually free.
    """
    return st.st_blocks * 512


def dir_size(path: Path, skipped: Optional[List[str]] = None) -> int:
    """Recursively sum actual disk usage under `path`, skipping unreadable entries."""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        total += dir_size(Path(entry.path), skipped)
                    else:
                        total += _actual_bytes(entry.stat(follow_symlinks=False))
                except (PermissionError, FileNotFoundError, OSError) as exc:
                    if skipped is not None:
                        skipped.append(f"{entry.path} ({exc.__class__.__name__})")
    except (PermissionError, FileNotFoundError, OSError) as exc:
        if skipped is not None:
            skipped.append(f"{path} ({exc.__class__.__name__})")
    return total


def path_size(path: Path, skipped: Optional[List[str]] = None) -> int:
    """Actual disk usage of a file, or recursive usage of a directory. 0 on error."""
    try:
        if path.is_symlink():
            return 0
        if path.is_dir():
            return dir_size(path, skipped)
        return _actual_bytes(path.stat())
    except (PermissionError, FileNotFoundError, OSError) as exc:
        if skipped is not None:
            skipped.append(f"{path} ({exc.__class__.__name__})")
        return 0


def days_since_modified(path: Path) -> float:
    """Days since `path` (non-recursive mtime) was last modified. 0 on error."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return 0.0
    return (time.time() - mtime) / 86400


def newest_of(paths: List[Path]) -> Optional[Path]:
    """The most-recently-modified path in `paths`, or None if empty.

    Used everywhere this tool offers a *set* of interchangeable installed
    things (Xcode iOS DeviceSupport versions, Android system images, AVDs,
    Simulator devices) as REVIEW candidates: always keep this one out of the
    results, so bulk-approving the whole category can never leave zero of
    them behind. A real incident is why this exists — an Android system
    image got fully cleared this way, and re-downloading one took a long
    time. "You can always get another one back" isn't good enough if
    approving one category can take you to none at all.
    """
    if not paths:
        return None

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    return max(paths, key=_mtime)
