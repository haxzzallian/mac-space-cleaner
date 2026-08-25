"""Configuration for the cleaner agent: thresholds, scan roots, sensitive paths.

Tune anything here without touching scanner logic.
"""
from pathlib import Path

HOME = Path.home()

# --- Generic large-file scan (Downloads/Desktop/Documents/Movies etc.) ---
LARGE_FILE_THRESHOLD_BYTES = 200 * 1024 * 1024  # 200 MB
LARGE_SCAN_ROOTS = [
    HOME / "Downloads",
    HOME / "Desktop",
    HOME / "Documents",
    HOME / "Movies",
    HOME / "development",  # catches non-project dirs (e.g. a data dump)
                            # as single big line items. SDK/tool checkouts
                            # living here are NOT candidates: excluded live
                            # by large_files.py's bin/ heuristic, and again,
                            # authoritatively, by core.protected's dynamic
                            # discovery (shell rc / env / which) applied in
                            # cleaner.py after all scanners run. See the
                            # README's Core workflow rules. Project folders
                            # under development/projects/ are handled by
                            # project_artifacts.py instead, not here.
]
LARGE_SCAN_MAX_DEPTH = 6  # don't recurse forever into huge trees

# --- Dev project artifact scan (stray node_modules/, Pods/, build/, .dart_tool/) ---
# Deliberately scoped to development/projects/ (not all of ~/development) so
# it doesn't crawl SDK checkouts like development/sdks/flutter, which have
# their own build/.dart_tool dirs that aren't "your" projects.
DEV_PROJECT_ROOTS = [
    HOME / "development" / "projects",
    HOME / "Projects",
    HOME / "Documents" / "Projects",
    HOME / "Sites",
]
STALE_DAYS = 30  # a build artifact not touched in this many days is fair game to flag
PROJECT_ARTIFACT_DIRNAMES = {"node_modules", "Pods", "build", ".dart_tool"}
PROJECT_ARTIFACT_MAX_DEPTH = 6
PROJECT_ARTIFACT_MIN_SIZE_BYTES = 1024 * 1024  # 1 MB — filters out near-empty noise

# --- Sensitive, must-be-clearly-announced paths ---
# Anything under one of these paths is always broken into its own bannered
# report section and requires a separate, explicit, per-item confirmation
# before being touched. NOT excluded from scanning — just handled with extra
# scrutiny. Empty by default; set your own in local_config.py (see the
# override import at the bottom of this file, and the README's "Getting
# Started" section), e.g.:
#   SENSITIVE_PATHS = [HOME / "Downloads" / "some-folder-you-care-about"]
SENSITIVE_PATHS = []
# Lower threshold than the generic large-file scan, since anything in here
# deserves a closer look regardless of size.
SENSITIVE_SCAN_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB

# --- Xcode / iOS dev caches ---
XCODE_DERIVED_DATA = HOME / "Library" / "Developer" / "Xcode" / "DerivedData"
XCODE_ARCHIVES = HOME / "Library" / "Developer" / "Xcode" / "Archives"
XCODE_DEVICE_SUPPORT = HOME / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport"
SIMULATOR_DEVICES = HOME / "Library" / "Developer" / "CoreSimulator" / "Devices"
MOBILE_SYNC_BACKUPS = HOME / "Library" / "Application Support" / "MobileSync" / "Backup"

# --- CocoaPods / Flutter / Dart ---
COCOAPODS_CACHE = HOME / "Library" / "Caches" / "CocoaPods"
PUB_CACHE = HOME / ".pub-cache"

# --- Node ecosystem caches ---
NPM_CACHE = HOME / ".npm"
YARN_CACHE = HOME / "Library" / "Caches" / "Yarn"
PNPM_STORE = HOME / "Library" / "pnpm" / "store"

# --- Homebrew ---
HOMEBREW_CACHE = HOME / "Library" / "Caches" / "Homebrew"

# --- Android / Gradle / Dart tooling ---
GRADLE_HOME = HOME / ".gradle"
DART_SERVER_CACHE = HOME / ".dartServer"
ANDROID_HOME = HOME / ".android"
ANDROID_SDK_ROOT = HOME / "Library" / "Android" / "sdk"

# --- Generic macOS cache/app-data locations (NOT dev-specific) ---
# ~/Library/Caches/* is fair game system-wide: Apple's own developer docs say
# apps must function correctly if this directory is cleared, so every
# subfolder here is treated as SAFE regardless of which app owns it.
LIBRARY_CACHES_DIR = HOME / "Library" / "Caches"
LIBRARY_LOGS_DIR = HOME / "Library" / "Logs"
# These hold real app data (settings, login sessions, browser profiles), not
# just cache, so they're only ever reported for visibility (action="manual")
# — never auto-trashed by this tool.
APPLICATION_SUPPORT_DIR = HOME / "Library" / "Application Support"
LIBRARY_CONTAINERS_DIR = HOME / "Library" / "Containers"
LIBRARY_GROUP_CONTAINERS_DIR = HOME / "Library" / "Group Containers"
APPLICATIONS_DIR = Path("/Applications")

SYSTEM_CACHE_MIN_SIZE_BYTES = 20 * 1024 * 1024     # 20 MB — filters noise
APP_SUPPORT_MIN_SIZE_BYTES = 300 * 1024 * 1024      # 300 MB
INSTALLED_APP_MIN_SIZE_BYTES = 500 * 1024 * 1024    # 500 MB

# Already reported by name elsewhere (dev_caches.py) — excluded from the
# generic ~/Library/Caches sweep so they aren't listed twice.
KNOWN_CACHE_PATHS = [
    COCOAPODS_CACHE,
    YARN_CACHE,
    HOMEBREW_CACHE,
]

# --- Protected toolchain roots (see core/protected.py) ---
# Never propose deleting anything that contains one of these — discovered
# dynamically each run (shell config, environment, `which`), not just this
# fixed command list, which is only one of three signals.
PROTECTED_COMMANDS = [
    "flutter", "dart", "fvm",
    "node", "npm", "npx", "yarn", "pnpm",
    "docker", "docker-compose",
    "python3", "python", "pip3",
    "java", "javac", "gradle", "adb",
    "pod", "git", "ruby", "brew",
]
SHELL_RC_FILES = [
    HOME / ".zshrc",
    HOME / ".zprofile",
    HOME / ".bash_profile",
    HOME / ".bashrc",
    HOME / ".profile",
]

# --- Output locations ---
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
LOGS_DIR = Path(__file__).resolve().parent / "logs"

# --- Optional per-user overrides ---
# local_config.py is gitignored and never shipped — create your own to
# override any constant above (most usefully SENSITIVE_PATHS) without
# touching this tracked file. See README's "Getting Started" section.
try:
    from local_config import *  # noqa: F401,F403 — optional, gitignored, per-user overrides
except ImportError:
    pass
