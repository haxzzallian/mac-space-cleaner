"""Android / Gradle / Dart tooling caches.

Easy to miss because none of it lives under a project folder or the obvious
~/Library/Caches — but for a Flutter/Android developer it's routinely tens
of GB: Gradle's build cache, the Dart analysis server cache, and the Android
SDK's emulator images / system images / old build-tools versions.

Never flags anything that would break the ability to build/run right now:
- a build-tools version actually referenced by a project's build.gradle(.kts)
- a system image actually backing a configured AVD
- an AVD that's currently running (has a lock file)
are excluded from the results outright, not just soft-flagged. On top of
that, system images and AVDs always keep at least one (the most recently
used) out of the results entirely — see core.fsutil.newest_of — so
bulk-approving a whole category can never leave you with zero of either.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Set

import config
from core.fsutil import days_since_modified, newest_of, path_size
from core.models import CleanupItem, Tier
from core.protected import is_ancestor_or_equal

_NEEDS_NETWORK = (
    " Needs an internet connection to rebuild — make sure you're online "
    "before you rely on this again after clearing it."
)
_BUILD_TOOLS_VERSION_RE = re.compile(r'buildToolsVersion\s*[=]?\s*["\']([\w.\-]+)["\']')
_GRADLE_BUILD_FILENAMES = ("build.gradle", "build.gradle.kts")


def _item_if_exists(path, category: str, tier: Tier, reason: str,
                     skipped: List[str], regenerable: bool = True) -> List[CleanupItem]:
    if not path.exists():
        return []
    size = path_size(path, skipped)
    if size <= 0:
        return []
    return [CleanupItem(path=path, size_bytes=size, category=category, tier=tier,
                         reason=reason, regenerable=regenerable, is_dir=path.is_dir())]


def _referenced_build_tools_versions(skipped: List[str]) -> Set[str]:
    """buildToolsVersion values found in any project's build.gradle(.kts)
    under config.DEV_PROJECT_ROOTS — never flag these as "old". Prunes the
    walk the same way project_artifacts.py does, so it doesn't descend into
    node_modules/Pods/build/.dart_tool or .git."""
    versions: Set[str] = set()
    for root in config.DEV_PROJECT_ROOTS:
        if not root.exists():
            continue
        root_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=(
                lambda exc: skipped.append(f"{exc.filename} ({exc.__class__.__name__})"))):
            depth = len(Path(dirpath).parts) - root_depth
            if depth >= config.PROJECT_ARTIFACT_MAX_DEPTH:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                            if d not in config.PROJECT_ARTIFACT_DIRNAMES and d != ".git"]
            for filename in filenames:
                if filename not in _GRADLE_BUILD_FILENAMES:
                    continue
                path = Path(dirpath) / filename
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError as exc:
                    skipped.append(f"{path} ({exc.__class__.__name__})")
                    continue
                versions.update(_BUILD_TOOLS_VERSION_RE.findall(text))
    return versions


def _avd_backed_system_images(skipped: List[str]) -> Set[Path]:
    """system-images/<api>/<tag>/<abi> paths actually backing a configured
    AVD — never flag these, independent of whether the AVD itself looks
    stale.

    NOTE: these are always *deeper* than the android-XX/ directories scan()
    iterates (config.ini's image.sysdir.1= includes the tag/abi segments
    too) — a caller must check ancestry (is_ancestor_or_equal), not exact
    equality, against this set. Getting that wrong once already meant this
    protection silently never matched anything."""
    backed: Set[Path] = set()
    avd_dir = config.ANDROID_HOME / "avd"
    if not avd_dir.exists():
        return backed
    try:
        avds = list(avd_dir.glob("*.avd"))
    except OSError as exc:
        skipped.append(f"{avd_dir} ({exc.__class__.__name__})")
        return backed
    for avd in avds:
        config_ini = avd / "config.ini"
        if not config_ini.exists():
            continue
        try:
            text = config_ini.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            skipped.append(f"{config_ini} ({exc.__class__.__name__})")
            continue
        for line in text.splitlines():
            # Real INI-style parse (key = value or key=value — Android Studio
            # rewrites this file and isn't guaranteed to keep the same
            # spacing every time) — NOT a `startswith("key=")` exact-prefix
            # check. That exact bug already happened once: the file had
            # "image.sysdir.1 = ..." (a space before "="), the prefix check
            # never matched, and this protection silently did nothing while
            # still claiming to guard the path.
            key, sep, value = line.partition("=")
            if sep and key.strip() == "image.sysdir.1":
                rel = value.strip()
                if rel:
                    backed.add((config.ANDROID_SDK_ROOT / rel).resolve())
    return backed


def _is_avd_running(avd: Path) -> bool:
    """True if the Android emulator's own *.lock convention shows this AVD
    is currently running — never flag a running emulator's image."""
    try:
        return any(avd.glob("*.lock"))
    except OSError:
        return False


def scan(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []

    # ~/.gradle is deliberately NOT scanned. It was previously a SAFE-tier
    # candidate ("technically regenerable"), got cleared, and the resulting
    # re-download made the next Flutter/Android build take a very long
    # time — the user asked for it to never be touched again, full stop.
    # "Regenerable" isn't the same as "cheap to regenerate," and Gradle's
    # cache is load-bearing enough for a Flutter workflow that it's not
    # this tool's call to make. If you want it back in scope, see
    # config.GRADLE_HOME.

    items += _item_if_exists(
        config.DART_SERVER_CACHE, "Dart analysis server cache", Tier.SAFE,
        "Dart/Flutter tooling's analysis cache; rebuilt automatically the "
        "next time an editor opens a Dart project.", skipped)

    items += _item_if_exists(
        config.ANDROID_HOME / "cache", "Android SDK tool cache", Tier.SAFE,
        "Android SDK manager's download cache; rebuilt automatically." + _NEEDS_NETWORK,
        skipped)

    # Emulator images (AVDs) — large, keep the ones you actively use or that
    # are currently running. Also always keep at least one AVD out of the
    # results entirely (the most recently used), even if none are running
    # right now — bulk-approving this category must never be able to leave
    # you with zero emulators.
    avd_dir = config.ANDROID_HOME / "avd"
    if avd_dir.exists():
        try:
            avds = list(avd_dir.glob("*.avd"))
        except OSError as exc:
            skipped.append(f"{avd_dir} ({exc.__class__.__name__})")
            avds = []
        candidates = [a for a in avds if not _is_avd_running(a)]
        keep = newest_of(candidates)
        for avd in candidates:
            if avd == keep:
                continue  # most recently used of what's left — always kept
            size = path_size(avd, skipped)
            if size <= 0:
                continue
            age_days = int(days_since_modified(avd))
            items.append(CleanupItem(
                path=avd, size_bytes=size, category="Android emulator (AVD)",
                tier=Tier.REVIEW,
                reason=f"Emulator device image, last touched {age_days} day(s) "
                       "ago. Recreated via Android Studio's Device Manager if "
                       "removed — review before deleting one you still use.",
                regenerable=True, is_dir=True))

    # SDK system images (one per API level + ABI) — big, re-downloadable,
    # except the ones actively backing a configured AVD, AND always keeping
    # at least one (the most recently used of what's left) out of the
    # results — a real incident is exactly why: every system image got
    # cleared in one category approval, and re-downloading one back took a
    # long time. You must always have at least one to fall back on.
    sysimg_dir = config.ANDROID_SDK_ROOT / "system-images"
    if sysimg_dir.exists():
        avd_backed = _avd_backed_system_images(skipped)
        try:
            api_dirs = [d for d in sysimg_dir.iterdir() if d.is_dir()]
        except OSError as exc:
            skipped.append(f"{sysimg_dir} ({exc.__class__.__name__})")
            api_dirs = []
        candidates = [d for d in api_dirs
                      if not any(is_ancestor_or_equal(d, backed) for backed in avd_backed)]
        keep = newest_of(candidates)
        for api_dir in candidates:
            if api_dir == keep:
                continue  # always keep at least one system image available
            size = path_size(api_dir, skipped)
            if size <= 0:
                continue
            items.append(CleanupItem(
                path=api_dir, size_bytes=size, category="Android SDK system image",
                tier=Tier.REVIEW,
                reason=f"Emulator system image for {api_dir.name}. "
                       "Re-downloadable via Android Studio's SDK Manager — "
                       "only remove API levels you don't target or emulate."
                       + _NEEDS_NETWORK,
                regenerable=True, is_dir=True))

    # Older build-tools versions — keep the newest AND anything a project
    # actually references, flag the rest.
    bt_dir = config.ANDROID_SDK_ROOT / "build-tools"
    if bt_dir.exists():
        referenced = _referenced_build_tools_versions(skipped)
        try:
            versions = sorted((d for d in bt_dir.iterdir() if d.is_dir()), key=lambda d: d.name)
        except OSError as exc:
            skipped.append(f"{bt_dir} ({exc.__class__.__name__})")
            versions = []
        newest = versions[-1] if versions else None
        for old in versions:
            if old is newest or old.name in referenced:
                continue  # newest, or a version a project actually needs
            size = path_size(old, skipped)
            if size <= 0:
                continue
            items.append(CleanupItem(
                path=old, size_bytes=size, category="Android SDK build-tools (old)",
                tier=Tier.REVIEW,
                reason=f"Older build-tools version ({old.name}); not referenced "
                       "by any build.gradle found under your project roots. "
                       "Re-downloadable via the SDK Manager." + _NEEDS_NETWORK,
                regenerable=True, is_dir=True))

    return items
