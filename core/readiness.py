"""Read-only dev-environment readiness checks — completely separate from
the deletion-candidate scanners. Answers one question directly: "could I
run an Android emulator and an iOS Simulator right now, with nothing left
to download?" — shown plainly in every report so that's verifiable at a
glance, not something to take on faith about the scanners' exclusion logic.

Never produces a CleanupItem. Never affects what `clean` can touch. Pure
status, computed fresh every run.

Readiness hinges on the *expensive* resource specifically — an Android
system image or an iOS Simulator runtime, both multi-GB downloads — not on
whether an AVD/device is already configured, since creating one from an
already-installed image/runtime is a fast, local, no-download operation.
"""
from __future__ import annotations

import json
import subprocess
from typing import List, NamedTuple

import config


class AndroidReadiness(NamedTuple):
    avd_count: int
    system_image_count: int

    @property
    def ready(self) -> bool:
        return self.system_image_count > 0


class IOSReadiness(NamedTuple):
    device_count: int
    runtime_count: int

    @property
    def ready(self) -> bool:
        return self.runtime_count > 0


def android_readiness(skipped: List[str]) -> AndroidReadiness:
    avd_dir = config.ANDROID_HOME / "avd"
    try:
        avd_count = len(list(avd_dir.glob("*.avd"))) if avd_dir.exists() else 0
    except OSError as exc:
        skipped.append(f"{avd_dir} ({exc.__class__.__name__})")
        avd_count = 0

    sysimg_dir = config.ANDROID_SDK_ROOT / "system-images"
    try:
        sysimg_count = len([d for d in sysimg_dir.iterdir() if d.is_dir()]) \
            if sysimg_dir.exists() else 0
    except OSError as exc:
        skipped.append(f"{sysimg_dir} ({exc.__class__.__name__})")
        sysimg_count = 0

    return AndroidReadiness(avd_count=avd_count, system_image_count=sysimg_count)


def ios_readiness(skipped: List[str]) -> IOSReadiness:
    try:
        device_count = len([d for d in config.SIMULATOR_DEVICES.iterdir() if d.is_dir()]) \
            if config.SIMULATOR_DEVICES.exists() else 0
    except OSError as exc:
        skipped.append(f"{config.SIMULATOR_DEVICES} ({exc.__class__.__name__})")
        device_count = 0

    try:
        result = subprocess.run(
            ["xcrun", "simctl", "runtime", "list", "-j"],
            capture_output=True, text=True, timeout=15, check=True)
        data = json.loads(result.stdout)
        runtime_count = sum(1 for r in data.values() if r.get("state") == "Ready")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            OSError, json.JSONDecodeError) as exc:
        skipped.append(f"xcrun simctl runtime list ({exc.__class__.__name__})")
        runtime_count = 0

    return IOSReadiness(device_count=device_count, runtime_count=runtime_count)
