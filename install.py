"""Install this checkout in a private virtual environment; never replace globals.

    python3 install.py [--wheelhouse DIR]

Needs Python 3.11 or newer: an older interpreter re-runs this script with python3.13/3.12/3.11 from PATH.
Each version gets its own application directory next to the older ones; their files and the
planning/tool state are never touched. Only the `zplan` launcher moves, and only when it is ours.
Re-running for the version the launcher already points at is a no-op; replacing another owned version copies the
production store (`production_root()`) to a sibling `v3.backup-<old version>-<UTC timestamp>` before the launcher
moves, so the previous version can be restored (docs/UPGRADE.md).
`--wheelhouse` installs offline: pip, its build step and the runtime dependencies (Textual) see only DIR
(--no-index --find-links).
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv

VERSION = "0.8.3"
OWNED = ("0.1.0", "0.2.0", "0.2.1", "0.3.0", "0.3.1", "0.4.0", "0.5.0", "0.5.1", "0.5.2", "0.6.0", "0.6.1", "0.6.2", "0.6.3", "0.7.0", "0.8.0", "0.8.1", "0.8.2", VERSION)
MINIMUM = (3, 11)
INTERPRETERS = ("python3.13", "python3.12", "python3.11")


def ensure_python(argv, version=None):
    """Return when this interpreter is new enough; otherwise replace the process with the first of
    python3.13/3.12/3.11 found on PATH, or stop with a message that names the requirement."""
    if tuple(version or sys.version_info[:2]) >= MINIMUM:
        return
    for name in INTERPRETERS:
        found = shutil.which(name)
        if found:
            os.execv(found, [found, str(Path(__file__).resolve()), *argv])
    raise SystemExit("zplan requires Python %s.%s or newer (found %s.%s), and python3.13, python3.12 and python3.11 "
                     "are not on PATH. Install, for example, python3.13 and run install.py again."
                     % (MINIMUM + tuple(version or sys.version_info[:2])))


def has_node():
    """True when both Node.js and npm are on PATH (`zplan setup` installs the pinned Codex through `npm ci`)."""
    return bool(shutil.which("node") and shutil.which("npm"))


NODE_REFUSAL = ("zplan requires Node.js >= 16 and npm (they install the pinned Codex): they are not on PATH. Install "
                "Node.js (Debian/Ubuntu: sudo apt-get install -y nodejs npm; macOS: brew install node) and run "
                "install.py again.")


def on_path(directory, path=None):
    """True when `directory` is one of the PATH entries (compared resolved; empty entries are not the cwd here)."""
    path = os.environ.get("PATH", "") if path is None else path
    return any(Path(entry).expanduser().resolve() == directory for entry in path.split(os.pathsep) if entry)


SETUP_FOLLOWS = "ZPLAN_SETUP_FOLLOWS"


def installed_message(entry, bin_dir, path=None, setup_follows=False, node=True):
    """The closing install line. `setup_follows` marks the two callers that run `zplan setup` themselves
    (`install.sh` and `zplan update`, through the `ZPLAN_SETUP_FOLLOWS` environment variable): the line then
    never sends the user to a `zplan setup` they did not ask for, and names `zplan login` as the next step. A
    manual `python3 install.py` keeps naming `zplan setup`. Without `node` (Node.js/npm missing) that caller's
    setup refuses right away with its own line, so no next step is named here."""
    if setup_follows and not node:
        return "Installed " + str(entry) + "."
    next_step = "zplan login" if setup_follows else "zplan setup"
    if on_path(bin_dir, path):
        return "Installed " + str(entry) + ". The zplan command is ready; next step: " + next_step + "."
    return "Installed " + str(entry) + ". Add " + str(bin_dir) + " to PATH; then " + next_step + "."


def reports_version(executable, version):
    """True when `executable --version` prints exactly `zplan <version>`: the app there is really this version, so
    re-installing it in place would only re-run `--force-reinstall` on the live application."""
    if not Path(executable).exists():
        return False
    result = subprocess.run([str(executable), "--version"], capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "zplan " + version


def store_root(python):
    """The production store path as the *newly installed* package computes it (its own `production_root()`).

    The probe runs isolated (`-I`: no PYTHONPATH, no user site, no working-directory entry on sys.path), so it
    always answers from the package installed in the new venv. `install.py` is routinely run from inside a zplan
    checkout (manual install, `install.sh`, dogfooding); without `-I` that checkout shadows the installed package
    and the store path would be read from the wrong tree."""
    code = "from terminal_planner.authority import production_root; print(production_root())"
    result = subprocess.run([str(python), "-I", "-c", code], check=True, capture_output=True, text=True)
    return Path(result.stdout.strip())


def backup_store(python, old_version):
    """Copy the production store next to itself as `v3.backup-<old version>-<UTC timestamp>`. Returns the copy's
    path, or None when there is no store yet. A failed copy raises, stopping the caller before the launcher swap."""
    store = store_root(python)
    if not store.exists():
        return None
    destination = store.parent / ("%s.backup-%s-%s" % (store.name, old_version,
                                                        time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())))
    try:
        shutil.copytree(store, destination)
    except OSError as error:
        raise RuntimeError("Could not copy the store %s (%s); the launcher was not switched." % (store, error))
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install zplan %s into a private virtual environment." % VERSION)
    parser.add_argument("--wheelhouse", help="offline: build backend and runtime dependency wheels (setuptools, wheel, textual…) in this directory; no index")
    args = parser.parse_args(argv)
    ensure_python(sys.argv[1:] if argv is None else argv)
    node = has_node()
    if not node and not os.environ.get(SETUP_FOLLOWS):
        raise SystemExit(NODE_REFUSAL)  # nothing is installed for a zplan that cannot set itself up
    source = Path(__file__).resolve().parent
    apps = (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "planning-kit/app").expanduser().resolve()
    root = apps / VERSION
    bin_dir = (Path(os.environ["ZEROSHOT_TOOLS"]) / "bin" if os.environ.get("ZEROSHOT_TOOLS") else Path.home() / ".local/bin").expanduser().resolve()
    entry = bin_dir / "zplan"
    target = root / "bin/zplan"
    previous = None  # the app directory an owned launcher points at right now, when there is one
    if entry.exists() or entry.is_symlink():
        owned = {apps / version / "bin/zplan" for version in OWNED}
        if not entry.is_symlink() or entry.resolve() not in owned:
            raise RuntimeError("Existing zplan is not owned by this installer: " + str(entry))
        previous = entry.resolve().parent.parent
    if previous == root and reports_version(target, VERSION):
        print("zplan " + VERSION + " is already installed")
        return 0
    offline = []
    if args.wheelhouse:
        wheelhouse = Path(args.wheelhouse).expanduser().resolve()
        if not wheelhouse.is_dir():
            raise RuntimeError("Wheelhouse not found: " + str(wheelhouse))
        offline = ["--no-index", "--find-links", str(wheelhouse)]
    venv.EnvBuilder(with_pip=True).create(root)
    subprocess.run([str(root / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                    "--force-reinstall", *offline, str(source)], check=True)
    subprocess.run([str(target), "--version"], check=True)
    if previous is not None and previous != root:
        backup = backup_store(root / "bin/python", previous.name)
        if backup is not None:
            print("Store backup: " + str(backup))
        print("Previous app (rollback target): " + str(previous))
    bin_dir.mkdir(parents=True, exist_ok=True)
    if not entry.is_symlink() or entry.resolve() != target:
        pending = bin_dir / (".zplan-" + VERSION)
        if pending.exists() or pending.is_symlink():
            raise RuntimeError("Installer temporary entry already exists: " + str(pending))
        pending.symlink_to(target)
        os.replace(pending, entry)
    print(installed_message(entry, bin_dir, setup_follows=bool(os.environ.get(SETUP_FOLLOWS)), node=node))
    return 0


if __name__ == "__main__":
    sys.exit(main())
