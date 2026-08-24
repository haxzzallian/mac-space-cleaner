"""Data models shared across the cleaner agent."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Tier(str, Enum):
    """How confident we are that an item is safe to remove.

    SAFE      - regenerable caches, bulk-confirmed together.
    REVIEW    - regenerable but riskier / less certain, confirmed per category.
    SENSITIVE - inside a folder the user flagged as valuable; always its own
                bannered section, confirmed one item at a time by typing
                the exact filename.
    """

    SAFE = "SAFE"
    REVIEW = "REVIEW"
    SENSITIVE = "SENSITIVE"


def human_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable string (e.g. '1.3 GB')."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - unreachable in practice


@dataclass
class CleanupItem:
    """A single file, folder, or aggregate finding proposed for cleanup."""

    path: Optional[Path]     # None for aggregate findings (e.g. Docker's report)
    size_bytes: int
    category: str            # e.g. "Xcode DerivedData", "npm cache", "Large file"
    tier: Tier
    reason: str              # human-readable justification shown in the report
    regenerable: bool = True
    is_dir: bool = True
    # "trash"  -> this tool can move `path` to ~/.Trash on confirmation
    # "manual" -> report-only; user must act themselves (e.g. `docker system prune`)
    action: str = "trash"

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes)
