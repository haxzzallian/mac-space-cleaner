"""Discovers paths this Mac's shell/toolchain currently depends on, so they
can be hard-excluded from every scanner's results — never soft-flagged,
never a "review before removing" candidate. See README's Core workflow
rules for why this exists: a generic large-file scanner once blob-flagged
an entire SDK install because nothing checked whether it was load-bearing.

Three independent signals feed one set, because any single one misses part
of a real setup:
- a tool reached only via a PATH-prepended shim (not its own `which`-able
  command) is invisible to signal 3 but visible in signal 1's PATH line
- an SDK pointed at by an env var (FLUTTER_ROOT and friends) that isn't
  itself a command is invisible to signal 3 entirely
- a var set outside any dotfile (exported by an IDE, launchctl, etc.) is
  invisible to signal 1 but visible in signal 2
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import List, Set

import config

_EXPORT_VAR_RE = re.compile(r'export\s+(\w+)=["\']?([^"\'\s]+)')
_PATH_SEGMENT_RE = re.compile(r'[^:"\'\s]+')


def _expand(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def _protected_roots_from_shell_rc(skipped: List[str]) -> Set[Path]:
    roots: Set[Path] = set()
    for rc_path in config.SHELL_RC_FILES:
        if not rc_path.exists():
            continue
        try:
            text = rc_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            skipped.append(f"{rc_path} ({exc.__class__.__name__})")
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _EXPORT_VAR_RE.search(stripped)
            if not match:
                continue
            var_name, value = match.group(1), match.group(2)
            if var_name == "PATH":
                for segment in _PATH_SEGMENT_RE.findall(value):
                    # Skip the self-reference ($PATH/${PATH}) every PATH
                    # export chains onto — expanding it pulls in this
                    # process's entire (often huge, duplicated) live PATH
                    # as if it were one path, which isn't a real directory
                    # and can crash a later .exists() call ("File name too
                    # long"). Real segments are the other pieces of the line.
                    if segment in ("$PATH", "${PATH}"):
                        continue
                    if segment.startswith(("/", "~", "$")):
                        roots.add(_expand(segment))
            elif var_name.endswith("_ROOT") or var_name.endswith("_HOME"):
                roots.add(_expand(value))
    return roots


def _protected_roots_from_environ() -> Set[Path]:
    roots: Set[Path] = set()
    for name, value in os.environ.items():
        if (name.endswith("_ROOT") or name.endswith("_HOME")) and value:
            roots.add(_expand(value))
    return roots


def _protected_roots_from_which() -> Set[Path]:
    roots: Set[Path] = set()
    for command in config.PROTECTED_COMMANDS:
        found = shutil.which(command)
        if not found:
            continue
        resolved = Path(found).resolve()
        # If reached via a bin/ dir, protect the SDK root (bin's parent),
        # not just the one binary.
        roots.add(resolved.parent.parent if resolved.parent.name == "bin" else resolved.parent)
    return roots


def is_ancestor_or_equal(maybe_ancestor: Path, path: Path) -> bool:
    """True if `maybe_ancestor` is `path` itself or one of its ancestors."""
    try:
        path.resolve().relative_to(maybe_ancestor.resolve())
        return True
    except (ValueError, OSError):
        return False


def _safe_normalize(path: Path, skipped: List[str]) -> Path:
    """Resolve `path` if it exists, else return it as-is. A malformed or
    absurdly long path (e.g. from a shell-rc line this parser misread)
    must never crash the scan over a *safety* check — fail open to the
    unresolved path instead, which is still usable by is_ancestor_or_equal."""
    try:
        return path.resolve() if path.exists() else path
    except OSError as exc:
        skipped.append(f"{path} (protected-root check: {exc.__class__.__name__})")
        return path


def get_protected_roots(skipped: List[str]) -> Set[Path]:
    """Every path this Mac's shell/toolchain currently depends on, plus the
    configured dev-project roots. Never propose deleting anything that
    contains one of these."""
    roots: Set[Path] = set()
    roots |= _protected_roots_from_shell_rc(skipped)
    roots |= _protected_roots_from_environ()
    roots |= _protected_roots_from_which()
    roots |= set(config.DEV_PROJECT_ROOTS)
    return {_safe_normalize(r, skipped) for r in roots}
