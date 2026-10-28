"""`zplan update`: move an installed zplan to the newest release tag (0.6 and later).

The release repository is named once, in `REPOSITORY` (override `ZPLAN_REPOSITORY`; `install.sh` carries the same
default and the same override). Releases are `vX.Y.Z` tags; the newest one is installed by running *its own*
`install.py` (the venv, the store backup and the launcher swap all happen there, A4), then `zplan setup`.
An installation only ever moves forward: a same-or-older newest tag is a no-op.
"""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from . import __version__

REPOSITORY = "https://github.com/pinkynail228/zeroplan.git"
TAG = re.compile(r"^refs/tags/v(\d+)\.(\d+)\.(\d+)$")


class UpdateError(RuntimeError):
    """A git or release failure the owner can act on; `zplan update` prints it and exits non-zero."""


def repository():
    """The release repository: `ZPLAN_REPOSITORY` when set (tests point it at a local bare repo), else the default."""
    return os.environ.get("ZPLAN_REPOSITORY") or REPOSITORY


def version_tuple(text):
    """`X.Y.Z` as a comparable tuple, so v0.10.0 sorts after v0.9.0 (never lexically)."""
    return tuple(int(part) for part in text.split("."))


def versions(output):
    """The `X.Y.Z` of every tag whose reference is exactly `refs/tags/vX.Y.Z`, oldest first; other tags are
    ignored. The whole reference must match, so a `v0.10`, an unrelated `nightly`, and a *namespaced* tag such as
    `refs/tags/archive/v9.9.9` are not releases: the final path component alone would wrongly select the last
    one."""
    found = set()
    for line in output.splitlines():
        fields = line.split()
        if not fields:
            continue
        match = TAG.match(fields[-1])
        if match:
            found.add(".".join(match.groups()))
    return sorted(found, key=version_tuple)


def remote_versions(repo=None):
    """The release versions the repository advertises; raises `UpdateError` when git cannot be asked."""
    url = repo or repository()
    result = subprocess.run(["git", "ls-remote", "--tags", "--refs", url], capture_output=True, text=True)
    if result.returncode:
        raise UpdateError("Could not read the releases of %s: %s" % (url, result.stderr.strip() or "git ls-remote failed"))
    return versions(result.stdout)


def launcher():
    """The `zplan` launcher of this installation, resolved the same way install.py resolves it: `ZEROSHOT_TOOLS`
    (with `~` expanded, so `ZEROSHOT_TOOLS=~/zplan-tools` works) or the default `~/.local/bin`."""
    if os.environ.get("ZEROSHOT_TOOLS"):
        return Path(os.environ["ZEROSHOT_TOOLS"]).expanduser() / "bin/zplan"
    return Path.home() / ".local/bin/zplan"


def clone(destination, version, repo=None):
    """A shallow checkout of tag `v<version>` under `destination`."""
    url = repo or repository()
    result = subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", "v" + version, url, str(destination)],
                            capture_output=True, text=True)
    if result.returncode:
        raise UpdateError("Could not fetch release v%s from %s: %s"
                          % (version, url, result.stderr.strip() or "git clone failed"))
    return Path(destination)


def install(checkout, show):
    """Run the released tag's own `install.py` with this interpreter; its output (the store backup path) stays
    visible. `ZPLAN_SETUP_FOLLOWS` (the same name as `install.SETUP_FOLLOWS`) tells it that this caller runs
    `zplan setup` next, so its closing line does not ask the owner to. Returns True when the installer succeeded."""
    script = Path(checkout) / "install.py"
    if not script.is_file():
        raise UpdateError("The release has no install.py: " + str(script))
    show("Installing the new version via " + str(script) + " …")
    environment = dict(os.environ, ZPLAN_SETUP_FOLLOWS="1")
    return subprocess.run([sys.executable, str(script)], env=environment).returncode == 0


def run(check=False, show=print):
    """`zplan update [--check]`; returns the process exit code. Every failure before the launcher swap leaves the
    launcher and the store to the installer (which does not swap until it has succeeded)."""
    current = __version__
    try:
        found = remote_versions()
    except UpdateError as error:
        show(str(error))
        return 1
    if not found:
        show("%s has no vX.Y.Z releases." % repository())
        return 1
    newest = found[-1]
    if check:
        show("Current zplan version %s; newest release %s." % (current, newest))
        return 0
    if version_tuple(newest) <= version_tuple(current):
        show("zplan %s is already the newest: no update needed." % current)
        return 0
    try:
        with tempfile.TemporaryDirectory(prefix="zplan-update-") as temp:
            checkout = clone(Path(temp) / "src", newest)
            if not install(checkout, show):
                show("Installation of v%s did not finish; the launcher and store are unchanged." % newest)
                return 1
    except UpdateError as error:
        show(str(error))
        return 1
    launch = launcher()
    try:
        code = subprocess.run([str(launch), "setup"]).returncode
    except OSError as error:
        show("zplan updated to %s, but %s setup could not be started (%s); run zplan setup manually."
             % (newest, launch, error))
        return 1
    if code:
        show("zplan updated to %s, but zplan setup exited with code %d; run zplan setup again." % (newest, code))
        return 1
    show("zplan updated to %s." % newest)
    show("Rollback: point the launcher at app/%s and restore production/v3 from the copy above (docs/UPGRADE.md)." % current)
    return 0
