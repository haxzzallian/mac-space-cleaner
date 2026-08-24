# Mac Space Cleaner Agent

A small, dependency-free Python 3 CLI that scans your Mac for reclaimable
disk space — dev-tool caches, stray build artifacts, and ordinary app
clutter alike — and **always shows you the full itemized plan before
deleting anything**. Nothing is ever permanently deleted — confirmed items
are moved to `~/.Trash`, and you decide separately whether to empty it.

## Getting Started (new clone)

1. **Prerequisites** — macOS only. Python 3 comes preinstalled; confirm with
   `python3 --version`. No `pip install` required — everything here is
   Python standard library.
2. **Clone and enter the folder:**
   ```bash
   git clone https://github.com/<your-username>/mac-space-cleaner.git
   cd mac-space-cleaner
   ```
3. **(Optional) Protect a folder of your own.** One folder's contents can be
   treated as extra-sensitive — always broken into its own section of the
   report, and only ever removed one item at a time by typing its exact
   name (see the SENSITIVE row in the tier table below). Nothing is
   protected by default. To set one, create a file named `local_config.py`
   right here next to `config.py`:
   ```python
   from config import HOME
   SENSITIVE_PATHS = [HOME / "Downloads" / "some-folder-you-care-about"]
   ```
   `local_config.py` is gitignored — it's yours alone and never gets
   committed or pushed. Skip this step entirely if you don't need it;
   everything else works with zero setup.
4. **Grant Full Disk Access** — see the section right below; without it,
   the scan still runs but misses some caches.
5. **Run a scan first, always:**
   ```bash
   python3 cleaner.py scan
   ```
   This is read-only — it prints a full report and saves a copy under
   `reports/`, and touches nothing on disk. Read through it before you ever
   run `clean`.
6. **Clean, once you're comfortable with what scan found:**
   ```bash
   python3 cleaner.py clean
   ```
   Shows the identical report, then walks you through the tiered
   confirmations described in "How the plan is organized" below — nothing
   moves without you explicitly saying yes to it.

## Core workflow rules

1. **Nothing here is ever proposed if removing it could stop you from writing
   or running Flutter, Node.js, Docker, or Python right now.** A build-tools
   version a project's `build.gradle` actually references, a system image
   backing a configured Android emulator, a currently-booted iOS
   Simulator/running AVD, and non-stale project directories are excluded
   from the results outright — not soft-flagged with a warning you could
   bulk-approve past. Regenerable caches that need network access to rebuild
   say so in their reason text, so you know before clearing them offline.
2. **The full plan is always shown, and always requires your explicit
   approval, before anything is touched — every run, no exceptions.** `scan`
   never deletes anything at all; `clean` shows the identical report first,
   then walks through tiered confirmations (see below) before moving
   anything to Trash.

Built for a Flutter / Node.js / Docker workflow, so it specifically
understands: Xcode DerivedData/Archives/DeviceSupport, iOS Simulators, iOS
device backups, CocoaPods cache, Flutter/Dart `.pub-cache`/`.dartServer`,
Gradle's cache, the Android SDK (old system images/build-tools, emulator
AVDs), npm/yarn/pnpm caches, Homebrew cache, Docker's reclaimable space, and
stray `node_modules` / `Pods` / `build` / `.dart_tool` folders left behind
in old projects.

It doesn't stop at the tech stack, though — space fills up from ordinary
app usage too, long before you ever open an IDE. So it also sweeps every
subfolder of `~/Library/Caches` (any app's cache, by Apple's own
convention, not just dev tools), `~/Library/Logs`, and a generic large-file
scan — plus gives you **read-only visibility** into the big non-cache
consumers that are riskier to touch automatically: `~/Library/Application
Support/<app>`, `~/Library/Containers/<app>` (including Docker Desktop's
VM disk), and installed apps under `/Applications`. Those last few are
reported so nothing stays invisible, but never auto-deleted — they hold
real app data/settings, not just cache, so it's your call app-by-app.

Note on numbers: `df -h /` on macOS often reports a small, misleading
"used" figure because your actual data lives on a separate APFS volume.
Check real usage with `df -H /System/Volumes/Data`, or just trust this
tool's own GRAND TOTAL.

## First-time setup: Full Disk Access

Many caches live under `~/Library/...`, which macOS blocks from an ordinary
Terminal by default. Without access the scan still works, but skips those
paths and tells you so at the end (look for the "skipped" note).

To scan everything: **System Settings → Privacy & Security → Full Disk
Access** → enable it for your terminal app (Terminal, iTerm2, etc.), then
restart the terminal.

## Usage

Run from inside this directory:

```bash
cd cleaner

# 1. Read-only. Prints a full report and saves a copy to reports/. Nothing is touched.
python3 cleaner.py scan

# 2. Same report, then walks you through confirming what to move to Trash.
python3 cleaner.py clean
```

## How the plan is organized

Every finding is placed into one of three tiers, always shown in this order:

| Tier | Meaning | How it's confirmed |
|---|---|---|
| **SAFE** | Regenerable caches (Xcode DerivedData, CocoaPods/pub/npm/yarn/Homebrew/Gradle caches, any `~/Library/Caches/<app>` subfolder, etc.) | One bulk yes/no for everything in this tier |
| **REVIEW** | Regenerable but needs a look (stale `node_modules`/`Pods`/`build`, old Simulators/device backups/AVDs, old Android SDK images, app logs, large personal files) | One yes/no per category |
| **SENSITIVE** | Anything inside a folder you've listed in `SENSITIVE_PATHS` (empty by default — see Getting Started above) | Each item individually — you must type its exact filename to confirm |

A few things are **report-only** — always shown in the plan, but never
touched by this tool at all (no confirmation offered):
- Docker's reclaimable space (from `docker system df`) — pruning volumes can
  destroy real data, so the report gives you the exact command to run yourself.
- `~/Library/Application Support/<app>`, `~/Library/Containers/<app>`
  (including Docker Desktop's own VM disk) and `~/Library/Group Containers/<app>`
  — these hold real app data/settings, not just cache.
- `/Applications/*.app` — installed apps, listed by size so you can spot ones
  worth uninstalling yourself; this tool never uninstalls anything.

`scan` never deletes anything. `clean` shows the identical report first, then
walks through the confirmations above — declining a group just leaves it
alone. Confirmed items are moved into `~/.Trash` (a real, recoverable move,
not a permanent delete), and every move is logged to `logs/` with a
timestamp. At the end you're asked, separately, whether to empty Trash now.

## Tuning

Two ways to tune behavior, without touching any scanner logic:
- **Shared defaults** — edit [`config.py`](config.py) directly: thresholds
  (what counts as "large"), which folders count as dev-project roots, the
  staleness cutoff for build artifacts, etc. This file is tracked — changes
  here would be part of a commit/PR.
- **Personal-only overrides** — create `local_config.py` (gitignored, never
  committed) to override any of the above just for you, without touching the
  tracked file. `SENSITIVE_PATHS` is the most common use — see Getting
  Started above.

## Project layout

```
cleaner.py              CLI entrypoint (scan / clean)
config.py                thresholds, scan roots, sensitive-path rules
local_config.py          your personal overrides (gitignored, not in repo)
scanners/
  dev_caches.py            Xcode / CocoaPods / Flutter / npm / yarn / Homebrew
  android_gradle.py         Gradle / Dart analysis cache / Android SDK & AVDs
  docker_scan.py            docker system df (report-only)
  project_artifacts.py      stray node_modules / Pods / build / .dart_tool
  large_files.py            generic large files + the sensitive-folder pass
  system_caches.py          ~/Library/Caches, Logs, Application Support,
                             Containers, and /Applications (non-dev-specific)
core/
  models.py                CleanupItem, Tier
  fsutil.py                 permission-safe size/mtime helpers
  trash.py                  move_to_trash()
  report.py                 terminal + markdown report rendering
  confirm.py                 tiered interactive confirmation flow
reports/                  generated markdown reports (gitignored)
logs/                      JSON logs of what was actually trashed (gitignored)
```

## License

[MIT](LICENSE) — use it, modify it, share it.
