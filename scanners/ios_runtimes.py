"""iOS Simulator runtime images — the actual OS disk images Xcode/simctl
boot a Simulator from. NOT the same thing as Simulator *devices*
(dev_caches.py handles those, under ~/Library/Developer/CoreSimulator).

Runtimes live entirely outside ~/Library — root-owned, under
/System/Library/AssetsV2, tracked in macOS's own asset database
(mobileassetd) — so they can never be trash-moved like everything else this
tool deletes. The only sanctioned removal path is Apple's own
`xcrun simctl runtime delete <id>`, which properly deregisters it. See
CleanupItem.delete_command / core.confirm for how that's executed.

Always keeps the highest-version runtime out of the results entirely — same
"always keep at least one" principle as core.fsutil.newest_of, applied to
version-highest here since "keep the current OS version, drop the rest" is
what actually matches wanting exactly one Simulator that works, not
whichever was used most recently.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from core.models import CleanupItem, Tier

_ASSET_DIR_RE = re.compile(r"(.*\.asset)")
_PLATFORM_IOS = "com.apple.platform.iphonesimulator"


def _version_key(version: str) -> Tuple[int, ...]:
    """'26.3.1' -> (26, 3, 1). Numeric-tuple comparison, not string sort —
    string-sorting would put '9.0' after '18.1'."""
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts) if parts else (0,)


def _asset_path(parent_image_path: str) -> Optional[Path]:
    """Extract the real on-disk .asset folder from simctl's own
    parentImagePath, for display and an accurate size only — not used as
    the removal mechanism."""
    match = _ASSET_DIR_RE.match(parent_image_path)
    return Path(match.group(1)) if match else None


def scan(skipped: List[str]) -> List[CleanupItem]:
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "runtime", "list", "-j"],
            capture_output=True, text=True, timeout=15, check=True)
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, json.JSONDecodeError) as exc:
        skipped.append(f"xcrun simctl runtime list ({exc.__class__.__name__})")
        return []

    runtimes = [
        (rid, info) for rid, info in data.items()
        if info.get("state") == "Ready"
        and info.get("platformIdentifier") == _PLATFORM_IOS
    ]
    if len(runtimes) <= 1:
        return []  # nothing to remove without approaching zero

    runtimes.sort(key=lambda kv: _version_key(kv[1].get("version", "0")))
    keep_id, keep_info = runtimes[-1]
    keep_version = keep_info.get("version", "?")

    items: List[CleanupItem] = []
    for rid, info in runtimes:
        if rid == keep_id:
            continue
        version = info.get("version", "?")
        size_bytes = int(info.get("sizeBytes", 0))
        if size_bytes <= 0:
            continue
        asset_path = _asset_path(info.get("parentImagePath", "")) or Path(f"<runtime {rid}>")
        items.append(CleanupItem(
            path=asset_path, size_bytes=size_bytes,
            category="iOS Simulator runtime", tier=Tier.REVIEW,
            reason=f"iOS {version} Simulator runtime. Re-downloadable via "
                   f"Xcode's Platforms settings — iOS {keep_version} (the "
                   "highest installed version) is always kept so a "
                   "Simulator can still run.",
            regenerable=True, is_dir=True,
            delete_command=["xcrun", "simctl", "runtime", "delete", rid]))
    return items
