"""Docker reclaimable-space scanner.

Read-only and report-only: this never runs `docker system prune` (or any
other mutating docker command) itself — pruning volumes/containers can
destroy real data, so it's always left as a manual step the user reviews and
runs themselves. Skips gracefully if docker isn't installed or the daemon
isn't running.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import List

from core.models import CleanupItem, Tier

_UNITS = {"B": 1, "kB": 1000, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def _human_to_bytes(text: str) -> int:
    """Parse a docker size string like '1.234GB' or '512MB' into bytes."""
    text = text.strip()
    if not text or text in ("0B", "N/A"):
        return 0
    for suffix in sorted(_UNITS, key=len, reverse=True):
        if text.endswith(suffix):
            number = text[: -len(suffix)].strip()
            try:
                return int(float(number) * _UNITS[suffix])
            except ValueError:
                return 0
    return 0


def scan(skipped: List[str]) -> List[CleanupItem]:
    if shutil.which("docker") is None:
        return []

    try:
        result = subprocess.run(
            ["docker", "system", "df", "--format",
             "{{.Type}}\t{{.TotalCount}}\t{{.Size}}\t{{.Reclaimable}}"],
            capture_output=True, text=True, timeout=15, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        skipped.append(f"docker system df ({exc.__class__.__name__}: is the Docker daemon running?)")
        return []

    items: List[CleanupItem] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        type_, _count, _size, reclaimable = parts
        reclaim_bytes = _human_to_bytes(reclaimable.split(" ")[0])
        if reclaim_bytes <= 0:
            continue
        items.append(CleanupItem(
            path=None, size_bytes=reclaim_bytes, category=f"Docker {type_}",
            tier=Tier.SAFE if type_ in ("Images", "Build Cache") else Tier.REVIEW,
            reason=f"Reported reclaimable by `docker system df` ({reclaimable}). "
                   "Run `docker system prune` (images/build cache) or "
                   "`docker container prune` / `docker volume prune` (review "
                   "volumes carefully — they can hold real data) to reclaim.",
            regenerable=True, is_dir=False, action="manual"))
    return items
