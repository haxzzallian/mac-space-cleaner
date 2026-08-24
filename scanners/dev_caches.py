"""Scanners for known, regenerable developer-tool caches: Xcode, CocoaPods,
Flutter/Dart, npm/yarn/pnpm, Homebrew.

Never flags a currently-booted iOS Simulator — that's excluded from the
results outright (see _booted_simulator_udids), not just soft-flagged.
"""
from __future__ import annotations

import json
import subprocess
from typing import List, Set

import config
from core.fsutil import days_since_modified, path_size
from core.models import CleanupItem, Tier

_NEEDS_NETWORK = (
    " Needs an internet connection to rebuild — make sure you're online "
    "before you rely on this again after clearing it."
)


def _booted_simulator_udids(skipped: List[str]) -> Set[str]:
    """Best-effort: UDIDs of currently-booted iOS Simulators, via
    `xcrun simctl`. Returns an empty set (never raises) if simctl isn't
    available or the call fails — callers just won't get this protection,
    they still fall back to the staleness-based REVIEW flagging."""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "--json"],
            capture_output=True, text=True, timeout=15, check=True)
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, json.JSONDecodeError) as exc:
        skipped.append(f"xcrun simctl list devices ({exc.__class__.__name__})")
        return set()
    booted: Set[str] = set()
    for devices in data.get("devices", {}).values():
        for device in devices:
            if device.get("state") == "Booted":
                udid = device.get("udid")
                if udid:
                    booted.add(udid)
    return booted


def _item_if_exists(path, category: str, tier: Tier, reason: str,
                     skipped: List[str], regenerable: bool = True) -> List[CleanupItem]:
    if not path.exists():
        return []
    size = path_size(path, skipped)
    if size <= 0:
        return []
    return [CleanupItem(path=path, size_bytes=size, category=category, tier=tier,
                         reason=reason, regenerable=regenerable, is_dir=path.is_dir())]


def scan(skipped: List[str]) -> List[CleanupItem]:
    items: List[CleanupItem] = []

    items += _item_if_exists(
        config.XCODE_DERIVED_DATA, "Xcode DerivedData", Tier.SAFE,
        "Build intermediates Xcode fully regenerates on the next build.", skipped)

    items += _item_if_exists(
        config.COCOAPODS_CACHE, "CocoaPods cache", Tier.SAFE,
        "Downloaded pod sources; re-fetched automatically by `pod install`."
        + _NEEDS_NETWORK, skipped)

    items += _item_if_exists(
        config.PUB_CACHE, "Flutter/Dart pub cache", Tier.SAFE,
        "Downloaded package cache; re-fetched by `flutter pub get`."
        + _NEEDS_NETWORK, skipped)

    items += _item_if_exists(
        config.NPM_CACHE, "npm cache", Tier.SAFE,
        "npm's local package cache; rebuilt automatically as needed."
        + _NEEDS_NETWORK, skipped)

    items += _item_if_exists(
        config.YARN_CACHE, "Yarn cache", Tier.SAFE,
        "Yarn's local package cache; rebuilt automatically as needed."
        + _NEEDS_NETWORK, skipped)

    items += _item_if_exists(
        config.PNPM_STORE, "pnpm store", Tier.REVIEW,
        "pnpm's shared content-addressable store — other pnpm projects on this "
        "machine may still use it; safe to remove but slows the next install."
        + _NEEDS_NETWORK, skipped)

    items += _item_if_exists(
        config.HOMEBREW_CACHE, "Homebrew cache", Tier.SAFE,
        "Downloaded bottles/formulae; re-downloaded automatically if needed."
        + _NEEDS_NETWORK, skipped)

    # iOS DeviceSupport: keep the most recently used version, flag older ones.
    if config.XCODE_DEVICE_SUPPORT.exists():
        try:
            versions = sorted(
                (p for p in config.XCODE_DEVICE_SUPPORT.iterdir() if p.is_dir()),
                key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError as exc:
            skipped.append(f"{config.XCODE_DEVICE_SUPPORT} ({exc.__class__.__name__})")
            versions = []
        for old in versions[1:]:
            size = path_size(old, skipped)
            if size > 0:
                items.append(CleanupItem(
                    path=old, size_bytes=size, category="Xcode iOS DeviceSupport (old)",
                    tier=Tier.REVIEW,
                    reason="Symbol files for an iOS version other than the most "
                           "recently used; Xcode re-downloads these if you plug in "
                           "a device running this version again.",
                    regenerable=True, is_dir=True))

    # iOS Simulator devices — recreated by Xcode/simctl, but review before
    # removing one you actively test with. Currently-booted ones are never
    # a candidate at all.
    if config.SIMULATOR_DEVICES.exists():
        booted = _booted_simulator_udids(skipped)
        try:
            devices = [d for d in config.SIMULATOR_DEVICES.iterdir() if d.is_dir()]
        except OSError as exc:
            skipped.append(f"{config.SIMULATOR_DEVICES} ({exc.__class__.__name__})")
            devices = []
        for dev in devices:
            if dev.name in booted:
                continue  # currently booted — never a candidate
            size = path_size(dev, skipped)
            if size <= 0:
                continue
            age_days = int(days_since_modified(dev))
            items.append(CleanupItem(
                path=dev, size_bytes=size, category="iOS Simulator device",
                tier=Tier.REVIEW,
                reason=f"Simulator runtime/device data, last touched {age_days} day(s) "
                       "ago. Recreated by Xcode/`xcrun simctl` if removed — "
                       "review before deleting one you actively use.",
                regenerable=True, is_dir=True))

    # Old iOS device backups via Finder — NOT regenerable without a fresh backup.
    if config.MOBILE_SYNC_BACKUPS.exists():
        try:
            backups = [b for b in config.MOBILE_SYNC_BACKUPS.iterdir() if b.is_dir()]
        except OSError as exc:
            skipped.append(f"{config.MOBILE_SYNC_BACKUPS} ({exc.__class__.__name__})")
            backups = []
        for backup in backups:
            size = path_size(backup, skipped)
            if size <= 0:
                continue
            items.append(CleanupItem(
                path=backup, size_bytes=size, category="iOS device backup",
                tier=Tier.REVIEW,
                reason="A full local backup of an iOS device. NOT regenerable "
                       "unless you re-back-up the device — review carefully "
                       "before removing.",
                regenerable=False, is_dir=True))

    return items
