"""Scanner for stray build artifacts (node_modules/, Pods/, build/, .dart_tool/)
sitting inside project directories that haven't been touched in a while.

Only flags artifacts whose containing folder hasn't been modified in
config.STALE_DAYS — actively worked-on projects are left alone entirely.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, List, Set

import config
from core.fsutil import days_since_modified, path_size
from core.models import CleanupItem, Tier

_CATEGORY_NAMES = {
    "node_modules": "Stray node_modules",
    "Pods": "Stray CocoaPods Pods/",
    "build": "Stray build/ artifacts",
    ".dart_tool": "Stray Flutter .dart_tool/",
}


def _walk(root: Path, max_depth: int, skipped: List[str]) -> Iterator[Path]:
    root_depth = len(root.parts)
    for dirpath, dirnames, _filenames in os.walk(root, followlinks=False, onerror=(
            lambda exc: skipped.append(f"{exc.filename} ({exc.__class__.__name__})"))):
        depth = len(Path(dirpath).parts) - root_depth
        if depth >= max_depth:
            dirnames[:] = []
            continue
        matched = [d for d in dirnames if d in config.PROJECT_ARTIFACT_DIRNAMES]
        for name in matched:
            yield Path(dirpath) / name
        # Don't descend into matched artifact dirs or .git — noisy, irrelevant.
        exclude = set(matched) | {".git"}
        dirnames[:] = [d for d in dirnames if d not in exclude]


def scan(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    seen: Set[Path] = set()
    for root in config.DEV_PROJECT_ROOTS:
        if not root.exists():
            continue
        for artifact_path in _walk(root, config.PROJECT_ARTIFACT_MAX_DEPTH, skipped):
            if artifact_path in seen:
                continue
            seen.add(artifact_path)
            age_days = days_since_modified(artifact_path)
            if age_days < config.STALE_DAYS:
                continue  # looks like an active project; leave it alone
            size = path_size(artifact_path, skipped)
            if size < config.PROJECT_ARTIFACT_MIN_SIZE_BYTES:
                continue  # not worth flagging (and filters SDK/tooling noise)
            name = artifact_path.name
            items.append(CleanupItem(
                path=artifact_path,
                size_bytes=size,
                category=_CATEGORY_NAMES.get(name, f"Stray {name}/"),
                tier=Tier.REVIEW,
                reason=f"Not modified in {int(age_days)} day(s) — looks like an "
                       "inactive project. Regenerable (`npm install`, "
                       "`pod install`, `flutter pub get`, or a fresh build) but "
                       "confirm you don't need this project as-is first.",
                regenerable=True,
                is_dir=True))
    return items
