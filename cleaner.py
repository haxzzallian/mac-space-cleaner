#!/usr/bin/env python3
"""Mac Space Cleaner Agent.

Scans your Mac for reclaimable disk space (developer-tool caches, stray
build artifacts, and large personal files), ALWAYS shows the full itemized
plan first, and only moves things to Trash after you explicitly confirm —
tier by tier, with anything inside a folder you've flagged as sensitive
(see SENSITIVE_PATHS in config.py / local_config.py) requiring a separate,
per-item, typed confirmation.

Usage:
    python3 cleaner.py scan     # read-only report, no prompts, nothing touched
    python3 cleaner.py clean    # scan, show report, then confirm + move to Trash

Run from inside this `cleaner/` directory (or `python3 cleaner/cleaner.py`
from its parent) so the local `config`/`core`/`scanners` modules import
correctly.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import List, Tuple

import config
from core.confirm import run_confirmation_flow
from core.models import CleanupItem
from core.protected import get_protected_roots, is_ancestor_or_equal
from core.readiness import android_readiness, ios_readiness
from core.report import group_by_tier, render_terminal, save_markdown
from scanners import (android_gradle, dev_caches, docker_scan, ios_runtimes,
                       large_files, project_artifacts, system_caches)


def run_scan() -> Tuple[List[CleanupItem], List[str], List[CleanupItem]]:
    skipped: List[str] = []
    items: List[CleanupItem] = []
    items += dev_caches.scan(skipped)
    items += android_gradle.scan(skipped)
    items += ios_runtimes.scan(skipped)
    items += docker_scan.scan(skipped)
    items += project_artifacts.scan(skipped)
    items += large_files.scan(skipped)
    items += large_files.scan_sensitive(skipped)
    items += system_caches.scan(skipped)

    # Final, cross-cutting safety net: never propose *deleting* anything that
    # contains part of the live toolchain (SDK roots, PATH entries, env
    # vars), no matter which scanner produced the candidate. Only applies to
    # action=="trash" items — action=="manual" items (Application Support,
    # installed apps, Docker's aggregate report, ...) were never something
    # `clean` could move to Trash in the first place, so filtering those too
    # would only hide legitimate visibility for no safety benefit. See
    # core/protected.py and the README's Core workflow rules.
    protected_roots = get_protected_roots(skipped)
    kept: List[CleanupItem] = []
    held_back: List[CleanupItem] = []
    for item in items:
        if item.action == "trash" and item.path is not None and any(
                is_ancestor_or_equal(item.path, root) for root in protected_roots):
            held_back.append(item)
        else:
            kept.append(item)

    return kept, skipped, held_back


def _print_report(items: List[CleanupItem], skipped: List[str], held_back: List[CleanupItem]):
    # Dev-environment readiness: not a candidate list, doesn't affect what
    # clean can touch — just makes the "you'll still be able to run an
    # emulator/simulator after this" guarantee visible every run instead of
    # asking you to trust the scanners' exclusion logic on faith.
    readiness_skipped: List[str] = []
    android = android_readiness(readiness_skipped)
    ios = ios_readiness(readiness_skipped)
    skipped = skipped + readiness_skipped

    print(render_terminal(items, skipped, held_back, android, ios))
    report_path = save_markdown(items, skipped, held_back, android, ios)
    print(f"\nFull report saved to: {report_path}")


def cmd_scan(_args):
    items, skipped, held_back = run_scan()
    _print_report(items, skipped, held_back)


def cmd_clean(_args):
    items, skipped, held_back = run_scan()
    _print_report(items, skipped, held_back)

    if not items:
        print("\nNothing found to clean. Nothing to confirm.")
        return

    print("\nNothing has been touched yet. You'll be asked to confirm each")
    print("group below before anything moves to Trash.")

    grouped = group_by_tier(items)
    freed, log = run_confirmation_flow(grouped)

    config.LOGS_DIR.mkdir(exist_ok=True)
    log_path = config.LOGS_DIR / f"trash-log-{time.strftime('%Y%m%d-%H%M%S')}.json"
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    print(f"\nMoved {freed / (1024**3):.2f} GB to ~/.Trash.")
    print(f"Log written to: {log_path}")
    print("Note: space is not actually freed on disk until Trash is emptied.")

    if log and _ask_empty_trash():
        _empty_trash()


def _ask_empty_trash() -> bool:
    answer = input(
        "\nEmpty Trash now? This PERMANENTLY deletes everything currently in "
        "~/.Trash, not just what was moved above. [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def _empty_trash():
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Finder" to empty trash'],
            check=True, capture_output=True, text=True)
        print("Trash emptied.")
    except subprocess.CalledProcessError as exc:
        print(f"Could not empty Trash automatically: {exc.stderr}")
        print("Empty it manually from the Finder Trash icon.")


def main():
    parser = argparse.ArgumentParser(
        prog="cleaner.py",
        description="Scan for reclaimable Mac disk space and (optionally) clean it up.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Read-only scan; prints and saves a report only.")
    p_scan.set_defaults(func=cmd_scan)

    p_clean = sub.add_parser("clean", help="Scan, show report, then confirm + move to Trash.")
    p_clean.set_defaults(func=cmd_clean)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
