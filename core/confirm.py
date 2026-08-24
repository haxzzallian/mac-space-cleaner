"""Interactive confirmation flows for the `clean` command.

The full report (core.report) is always shown in its entirety before any of
this runs, and every group here is confirmed before its items are touched.
Nothing is deleted permanently — see core.trash.move_to_trash.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from core.models import CleanupItem, Tier
from core.trash import move_to_trash


def _ask_yes_no(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def _trash_items(items: List[CleanupItem], log: List[dict]) -> int:
    freed = 0
    for item in items:
        if item.action != "trash" or item.path is None:
            continue
        try:
            dest = move_to_trash(item.path)
            freed += item.size_bytes
            log.append({
                "path": str(item.path),
                "trashed_to": str(dest),
                "size_bytes": item.size_bytes,
                "category": item.category,
            })
            print(f"  moved: {item.path} -> {dest}")
        except OSError as exc:
            print(f"  FAILED to move {item.path}: {exc}")
    return freed


def _by_category(items: List[CleanupItem]) -> Dict[str, List[CleanupItem]]:
    grouped: Dict[str, List[CleanupItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    return grouped


def run_confirmation_flow(grouped: Dict[Tier, List[CleanupItem]]) -> Tuple[int, List[dict]]:
    """Walks the user through tiered confirmations. Returns (bytes_freed, log)."""
    log: List[dict] = []
    freed = 0

    # --- SAFE tier: one bulk confirmation ---
    safe_all = grouped.get(Tier.SAFE, [])
    safe_items = [i for i in safe_all if i.action == "trash"]
    manual_safe = [i for i in safe_all if i.action == "manual"]
    if safe_items:
        total_gb = sum(i.size_bytes for i in safe_items) / (1024 ** 3)
        print(f"\n{len(safe_items)} SAFE item(s) totaling {total_gb:.2f} GB "
              "are regenerable caches.")
        if _ask_yes_no("Move ALL of these to Trash?"):
            freed += _trash_items(safe_items, log)
    if manual_safe:
        print(f"\n{len(manual_safe)} additional SAFE-tier item(s) require a manual "
              "step (see report above) — this tool does not run them automatically.")

    # --- REVIEW tier: confirmed per category ---
    review_all = grouped.get(Tier.REVIEW, [])
    review_items = [i for i in review_all if i.action == "trash"]
    manual_review = [i for i in review_all if i.action == "manual"]
    if review_items:
        print(f"\n{len(review_items)} REVIEW item(s) need a closer look — "
              "confirming one category at a time.")
        for category, cat_items in _by_category(review_items).items():
            total_gb = sum(i.size_bytes for i in cat_items) / (1024 ** 3)
            print(f"\n  {category}: {len(cat_items)} item(s), {total_gb:.2f} GB")
            for item in cat_items:
                print(f"    - {item.path}  ({item.size_bytes / (1024**2):.1f} MB) — {item.reason}")
            if _ask_yes_no(f"  Move all '{category}' items to Trash?"):
                freed += _trash_items(cat_items, log)
    if manual_review:
        print(f"\n{len(manual_review)} additional REVIEW-tier item(s) require a manual "
              "step (see report above) — this tool does not run them automatically.")

    # --- SENSITIVE tier: separate, per-item, typed confirmation ---
    sensitive_items = [i for i in grouped.get(Tier.SENSITIVE, []) if i.action == "trash"]
    if sensitive_items:
        total_gb = sum(i.size_bytes for i in sensitive_items) / (1024 ** 3)
        print("\n" + "!" * 72)
        print(f"  {len(sensitive_items)} item(s) found inside a folder you flagged as "
              f"sensitive (see SENSITIVE_PATHS), totaling {total_gb:.2f} GB.")
        print("  Nothing here is touched unless you explicitly confirm EACH item")
        print("  below by typing its exact name.")
        print("!" * 72)
        for item in sensitive_items:
            print(f"\n  - {item.path}  ({item.size_bytes / (1024**2):.1f} MB)")
            print(f"    reason: {item.reason}")
            typed = input(f"    Type exactly '{item.path.name}' to confirm deletion, "
                           "or press Enter to skip: ").strip()
            if typed == item.path.name:
                freed += _trash_items([item], log)
            else:
                print("    skipped.")

    return freed, log
