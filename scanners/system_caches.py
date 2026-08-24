"""Generic, non-dev-specific macOS locations — this is what makes the report
cover *everything* using space, not just your tech stack.

- ~/Library/Caches/<app>  -> SAFE. Apple's own convention: apps must work
  correctly if this directory is cleared, so every subfolder here is fair
  game no matter which app owns it (Chrome, Postman's updater, etc.).
- ~/Library/Logs/<app>    -> REVIEW. Safe to remove, but you lose that app's
  history if you're mid-debug with it.
- ~/Library/Application Support/<app>, ~/Library/Containers/<app>,
  ~/Library/Group Containers/<app> -> reported for VISIBILITY ONLY
  (action="manual"). These hold real app data/settings/login sessions, not
  just cache, so this tool never auto-trashes them — you decide per app
  (clear its own in-app cache, or uninstall it).
- /Applications/*.app -> reported for visibility only, same reason: this
  tool never uninstalls an app for you.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import config
from core.fsutil import path_size
from core.models import CleanupItem, Tier

_DOCKER_CONTAINER_NAME = "com.docker.docker"


def _iter_top_level(root: Path, skipped: List[str]):
    if not root.exists():
        return []
    try:
        return list(root.iterdir())
    except OSError as exc:
        skipped.append(f"{root} ({exc.__class__.__name__})")
        return []


def scan_library_caches(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    known = set(config.KNOWN_CACHE_PATHS)
    for entry in _iter_top_level(config.LIBRARY_CACHES_DIR, skipped):
        if entry.is_symlink() or entry in known:
            continue
        size = path_size(entry, skipped)
        if size < config.SYSTEM_CACHE_MIN_SIZE_BYTES:
            continue
        items.append(CleanupItem(
            path=entry, size_bytes=size, category="macOS app cache",
            tier=Tier.SAFE,
            reason="Under ~/Library/Caches — by Apple's own convention apps "
                   "must tolerate this being cleared; regenerated automatically.",
            regenerable=True, is_dir=entry.is_dir()))
    return items


def scan_library_logs(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    for entry in _iter_top_level(config.LIBRARY_LOGS_DIR, skipped):
        if entry.is_symlink():
            continue
        size = path_size(entry, skipped)
        if size < config.SYSTEM_CACHE_MIN_SIZE_BYTES:
            continue
        items.append(CleanupItem(
            path=entry, size_bytes=size, category="App logs",
            tier=Tier.REVIEW,
            reason="Under ~/Library/Logs — safe to remove, but you'll lose "
                   "this app's history if you're mid-way through debugging "
                   "something with it.",
            regenerable=True, is_dir=entry.is_dir()))
    return items


def _scan_app_data_dir(root: Path, category: str, skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    for entry in _iter_top_level(root, skipped):
        if entry.is_symlink():
            continue
        size = path_size(entry, skipped)
        if size < config.APP_SUPPORT_MIN_SIZE_BYTES:
            continue
        if entry.name.startswith(_DOCKER_CONTAINER_NAME):
            reason = ("Docker Desktop's app container, including its VM disk. "
                       "Don't delete this by hand — use Docker Desktop's own "
                       "Troubleshoot -> \"Clean / Purge data\" to reclaim this "
                       "safely without breaking Docker.")
        else:
            reason = ("Holds this app's real data/settings, not just cache — "
                       "removing it may sign you out or reset its configuration. "
                       "Check inside for its own Cache/ subfolder, or uninstall "
                       "the app from /Applications if you no longer use it.")
        items.append(CleanupItem(
            path=entry, size_bytes=size, category=category, tier=Tier.REVIEW,
            reason=reason, regenerable=False, is_dir=entry.is_dir(), action="manual"))
    return items


def scan_app_data(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    items += _scan_app_data_dir(config.APPLICATION_SUPPORT_DIR,
                                 "App data (Application Support)", skipped)
    items += _scan_app_data_dir(config.LIBRARY_CONTAINERS_DIR,
                                 "App data (sandboxed Container)", skipped)
    items += _scan_app_data_dir(config.LIBRARY_GROUP_CONTAINERS_DIR,
                                 "App data (Group Container)", skipped)
    return items


def scan_installed_apps(skipped: List[str]) -> List[CleanupItem]:
    """Visibility only — this tool never uninstalls an app for you."""
    items: List[CleanupItem] = []
    root = config.APPLICATIONS_DIR
    if not root.exists():
        return items
    try:
        apps = list(root.glob("*.app"))
    except OSError as exc:
        skipped.append(f"{root} ({exc.__class__.__name__})")
        apps = []
    for entry in apps:
        size = path_size(entry, skipped)
        if size < config.INSTALLED_APP_MIN_SIZE_BYTES:
            continue
        items.append(CleanupItem(
            path=entry, size_bytes=size, category="Installed application",
            tier=Tier.REVIEW,
            reason="Listed for visibility only — uninstall manually (drag to "
                   "Trash, or the app's own uninstaller) if you no longer use it.",
            regenerable=False, is_dir=True, action="manual"))
    return items


def scan(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []
    items += scan_library_caches(skipped)
    items += scan_library_logs(skipped)
    items += scan_app_data(skipped)
    items += scan_installed_apps(skipped)
    return items
