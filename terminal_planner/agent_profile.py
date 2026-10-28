"""The packaged agent profile and its write lifecycle into zplan's own Codex home (0.5 item S2, slice s2b1): the
profile (`resources/agent_profile.toml`) is written as `config.toml` into `setup.private_codex_home()`, keeping the
previous entry as `config.toml.bak`. No launch, login or doctor path calls it yet (R-1); s2b2 adds
`setup.agent_home(env)` and must skip `ensure` entirely whenever `CODEX_HOME` is set and nonempty — the private-home
guard here is necessary but not sufficient, since `CODEX_HOME=<private_codex_home()>` passes it.

The file holds the `docs/AGENT_ENV_PLAN.md` decision table (:65-79): first line `# zplan-agent-profile: <N>` (N a
positive ASCII integer), then the keys `EXPECTED` flattens; N is read from the bytes, never a second constant.
`version` rejects bytes that are not decodable UTF-8 anywhere, so a valid marker with a corrupt tail is R-2's
"undecodable bytes" (case 4), never "current"; `ensure` refuses a packaged profile whose marker is unreadable
before any write, so a markerless `config.toml` is never "current".
"""

from importlib import resources
import fcntl
import os
from pathlib import Path
import re
import stat
import tempfile

from . import setup
from .authority import Blocked


EXPECTED = {
    "approval_policy": "never",
    "sandbox_mode": "danger-full-access",
    "cli_auth_credentials_store": "file",
    "features.apps": False,
    "features.hooks": False,
    "features.plugins": False,
    "features.multi_agent": False,
    "features.goals": False,
    "features.memories": False,
    "skills.include_instructions": False,
    "skills.bundled.enabled": False,
}  # R-2: the flattened key -> value map the packaged file must hold; a test pins both directions.

_MARKER_PREFIX = b"# zplan-agent-profile: "
_NUMBER = re.compile(rb"[1-9][0-9]{0,8}")
LOCK_NAME = ".zplan-profile.lock"
_BAK_PREFIX = ".config.toml.bak-"
_NEW_PREFIX = ".config.toml.new-"


def packaged():
    """The packaged profile bytes through `importlib.resources` (the wheel smoke is the orchestrator's)."""
    return resources.files("terminal_planner").joinpath("resources", "agent_profile.toml").read_bytes()


def version(data):
    """The marker's N as an int, or None (R-2): no marker, another spelling, a leading zero, a CRLF, a BOM, bytes
    that are not decodable UTF-8 anywhere in `data`, or a marker area outside the closed grammar `[1-9][0-9]{0,8}`."""
    if not isinstance(data, (bytes, bytearray)):
        return None
    data = bytes(data)
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    head, newline, _ = data.partition(b"\n")
    if not newline or not head.startswith(_MARKER_PREFIX):
        return None
    number = head[len(_MARKER_PREFIX):]
    return int(number) if _NUMBER.fullmatch(number) else None


def written_version(home):
    """The N of `<home>/config.toml`, or None when it is absent (R-4): reads only, never writes, never locks."""
    try:
        return version((Path(home) / "config.toml").read_bytes())
    except FileNotFoundError:
        return None


def ensure(home):
    """Bring `<home>/config.toml` to the packaged profile under `<home>/.zplan-profile.lock` (R-3).

    Returns `"written"` (no config), `"current"` (already this N, even if hand-edited) or `"replaced"` (another N,
    no marker, undecodable bytes or a symlink). Refuses with ValueError a home other than
    `setup.private_codex_home()`, and with `setup.agent_home` a held lock, a non-file entry or an OSError; a refusal
    removes its own temp and never writes the target of a `config.toml` symlink."""
    home = Path(home)
    if home.resolve() != setup.private_codex_home().resolve():
        raise ValueError("agent_profile.ensure writes only zplan's own home: " + str(home))
    data = packaged()
    current = version(data)
    if current is None:
        raise _refuse(home, "packaged profile without a version marker")
    try:
        _make_home(home)  # F1
    except OSError as error:
        raise _refuse(home, error) from error
    try:
        lock = _open_lock(home / LOCK_NAME)  # F2
    except OSError as error:
        raise _refuse(home, error) from error
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Blocked("Another zplan is updating the profile in %s; try again." % home,
                          family="setup.agent_home") from error
        try:
            return _apply(home, data, current)
        except OSError as error:
            raise _refuse(home, error) from error
    finally:
        lock.close()


def _apply(home, data, current):
    """Classify `<home>/config.toml` under the lock and reach the state for `current` (R-3, in precedence)."""
    config = home / "config.toml"
    backup = home / "config.toml.bak"
    try:
        info = os.lstat(config)
    except FileNotFoundError:
        _publish(home, data, config, None, None)
        return "written"
    except OSError as error:
        raise _refuse(config, error) from error
    if stat.S_ISLNK(info.st_mode):
        _publish(home, data, config, backup, ("link", os.readlink(config)))
        return "replaced"  # precedence 2 over 3: a symlink is never "current", whatever its target carries
    if stat.S_ISREG(info.st_mode):
        body = config.read_bytes()
        if version(body) == current:
            return "current"
        _publish(home, data, config, backup, ("bytes", body))
        return "replaced"
    raise Blocked("Agent profile not written: %s is not a regular file." % config, family="setup.agent_home")


def _publish(home, data, config, backup, old):
    """Back `old` up (a byte copy or the link, never its target) and install the profile (R-3, atomic)."""
    if old is not None:
        kind, value = old
        staged = _stage(home, value, _BAK_PREFIX) if kind == "bytes" else _stage_link(home, value, _BAK_PREFIX)
        _swap(staged, backup)  # F3 (the stage) then F4 (the move)
    _swap(_stage(home, data, _NEW_PREFIX), config)  # F5 then F6


def _make_home(home):
    home.mkdir(parents=True, exist_ok=True, mode=0o700)


def _open_lock(path):
    """The per-home lock file, opened for `fcntl.flock` (the non-blocking shape of `setup.setup_lock`)."""
    return path.open("a")


def _stage(home, data, prefix):
    """A fresh temp file in `home` holding `data`, fsynced; a failing write removes its own temp."""
    handle, name = tempfile.mkstemp(prefix=prefix, dir=str(home))
    path = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        _discard(path)
        raise
    return path


def _stage_link(home, target, prefix):
    """A fresh symlink in `home` pointing at `target`; `target` itself is never opened."""
    for _ in range(16):
        path = home / (prefix + os.urandom(8).hex())
        if not os.path.lexists(str(path)):
            os.symlink(target, str(path))
            return path
    raise OSError("could not pick a name for the temporary link")


def _swap(source, destination):
    """Publish a staged entry with `os.replace`, removing the stage when the move fails."""
    try:
        os.replace(source, destination)
    except OSError:
        _discard(source)
        raise


def _discard(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _refuse(path, detail):
    return Blocked("Could not write the agent profile in %s: %s." % (path, detail), family="setup.agent_home")
