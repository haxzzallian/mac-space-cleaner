"""Builds and renders the cleanup report.

The full report is ALWAYS produced and shown before anything is deleted —
`scan` stops here entirely; `clean` shows this same report before asking for
any confirmation.
"""
from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import config
from core.models import CleanupItem, Tier, human_size

_TIER_ORDER = [Tier.SAFE, Tier.REVIEW, Tier.SENSITIVE]
_TIER_TITLES = {
    Tier.SAFE: "SAFE — regenerable caches",
    Tier.REVIEW: "REVIEW — check before removing",
    Tier.SENSITIVE: "SENSITIVE — inside a folder you flagged as valuable",
}


def group_by_tier(items: List[CleanupItem]) -> Dict[Tier, List[CleanupItem]]:
    grouped: Dict[Tier, List[CleanupItem]] = defaultdict(list)
    for item in items:
        grouped[item.tier].append(item)
    for tier_items in grouped.values():
        tier_items.sort(key=lambda i: i.size_bytes, reverse=True)
    return grouped


def _group_by_category(items: List[CleanupItem]) -> Dict[str, List[CleanupItem]]:
    by_category: Dict[str, List[CleanupItem]] = defaultdict(list)
    for item in items:
        by_category[item.category].append(item)
    return by_category


def render_terminal(items: List[CleanupItem], skipped: List[str]) -> str:
    lines: List[str] = []
    grouped = group_by_tier(items)
    grand_total = sum(i.size_bytes for i in items)

    lines.append("=" * 72)
    lines.append("MAC SPACE CLEANER — PROPOSED CLEANUP PLAN (nothing deleted yet)")
    lines.append("=" * 72)

    if not items:
        lines.append("\nNo cleanup candidates found.")

    for tier in _TIER_ORDER:
        tier_items = grouped.get(tier, [])
        if not tier_items:
            continue
        tier_total = sum(i.size_bytes for i in tier_items)
        banner = "!" if tier == Tier.SENSITIVE else "-"
        lines.append("")
        lines.append(f"[{tier.value}] {_TIER_TITLES[tier]}")
        lines.append(banner * 72)
        for category, cat_items in sorted(
            _group_by_category(tier_items).items(),
            key=lambda kv: sum(i.size_bytes for i in kv[1]),
            reverse=True,
        ):
            cat_total = sum(i.size_bytes for i in cat_items)
            lines.append(f"\n  {category}  ({human_size(cat_total)}, {len(cat_items)} item(s))")
            for item in cat_items:
                loc = str(item.path) if item.path else "(aggregate — see reason)"
                note = "" if item.action == "trash" else "  [manual step — not moved by this tool]"
                lines.append(f"    - {human_size(item.size_bytes):>10}  {loc}{note}")
                lines.append(f"        reason: {item.reason}")
        lines.append(f"\n  Tier total: {human_size(tier_total)}")

    lines.append("")
    lines.append("=" * 72)
    lines.append(f"GRAND TOTAL FOUND: {human_size(grand_total)}")
    trashable_total = sum(i.size_bytes for i in items if i.action == "trash")
    lines.append(f"  of which movable to Trash by this tool: {human_size(trashable_total)}")
    lines.append("=" * 72)

    if skipped:
        lines.append("")
        lines.append(f"NOTE: {len(skipped)} path(s) skipped (permission denied or vanished mid-scan).")
        lines.append("  Grant Full Disk Access to your terminal app for a complete scan:")
        lines.append("  System Settings -> Privacy & Security -> Full Disk Access.")

    return "\n".join(lines)


def save_markdown(items: List[CleanupItem], skipped: List[str]) -> Path:
    config.REPORTS_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = config.REPORTS_DIR / f"cleanup-report-{stamp}.md"

    grouped = group_by_tier(items)
    grand_total = sum(i.size_bytes for i in items)
    lines = [f"# Cleanup report — {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    lines.append(f"**Grand total found:** {human_size(grand_total)}\n")

    for tier in _TIER_ORDER:
        tier_items = grouped.get(tier, [])
        if not tier_items:
            continue
        lines.append(f"## [{tier.value}] {_TIER_TITLES[tier]}\n")
        for category, cat_items in _group_by_category(tier_items).items():
            cat_total = sum(i.size_bytes for i in cat_items)
            lines.append(f"### {category} — {human_size(cat_total)}\n")
            for item in cat_items:
                loc = str(item.path) if item.path else "(aggregate)"
                note = "" if item.action == "trash" else " _(manual step)_"
                lines.append(f"- `{loc}` — {human_size(item.size_bytes)}{note}  \n  _{item.reason}_")
            lines.append("")

    if skipped:
        lines.append("## Skipped paths (permission denied)\n")
        for s in skipped:
            lines.append(f"- {s}")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
