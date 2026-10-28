"""Private pinned tools and user preferences, separate from project authority.

Setup never runs a model. Tool availability does not grant writer admission.
"""

from contextlib import contextmanager
import fcntl
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

from . import toolchain
from .authority import HISTORICAL_EFFORTS, NATIVE_EFFORTS, Blocked, canonical, decode, require


# Role defaults outside the process profile (the profile's own are in process.PRESETS): the efforts, the model every
# role takes unless MODEL_OVERRIDES names it.
ROLE_DEFAULTS = {"planner": "high", "plan_verifier": "high", "worker": "max", "reviewer": "high", "steward": "high"}
DEFAULT_MODEL = "gpt-6.1-sol"
MODEL_OVERRIDES = {"worker": "gpt-6.1-terra"}
EFFORTS = NATIVE_EFFORTS

def data_root():
    return (Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "planning-kit").expanduser().resolve()


def config_root():
    return (Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "planning-kit").expanduser().resolve()


def native_state_root():
    # Keep existing histories discoverable. Never silently migrate frozen paths.
    previous = data_root() / "native"
    return previous if previous.exists() else (Path.home() / ".zp").resolve()


def default_roles():
    return {role: {"model": MODEL_OVERRIDES.get(role, DEFAULT_MODEL), "effort": effort}
            for role, effort in ROLE_DEFAULTS.items()}


def validate_roles(value):
    require(isinstance(value, dict) and set(value) == set(ROLE_DEFAULTS), "Invalid role configuration.", family="readiness.roles")
    for binding in value.values():
        require(isinstance(binding, dict) and set(binding) == {"model", "effort"}
                and isinstance(binding["model"], str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,255}", binding["model"])
                # Saved preferences may predate native-only efforts; input re-asks.
                and isinstance(binding["effort"], str) and binding["effort"] in HISTORICAL_EFFORTS,
                "Invalid model/effort.")
    return value


def load_roles():
    path = config_root() / "roles.json"
    roles = default_roles()
    if path.exists():
        saved = decode(path.read_text())
        require(isinstance(saved, dict), "Invalid role configuration.", family="readiness.roles")
        # Files written by earlier versions may name other roles: unknown ones are ignored, missing ones keep defaults.
        roles.update({role: binding for role, binding in saved.items() if role in ROLE_DEFAULTS})
    return validate_roles(roles)


def save_roles(value):
    validate_roles(value)
    root = config_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=root, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, root / "roles.json")
        finally:
            temporary.unlink(missing_ok=True)


def checksum(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def tool_files(root):
    # Hash the native optional package too, not just Codex's JavaScript launcher.
    return {str(path.relative_to(root)): checksum(path)
            for path in sorted(root.rglob("*")) if path.is_file() and path != root / "installation.json"}


def tools_root(chain=None):
    # One directory per toolchain: a new default installs next to the older bundles, never over them.
    return data_root() / "tools" / (chain or toolchain.current()).tool_dir_name


def tool_paths(root=None, chain=None):
    root = root or tools_root(chain)
    return root / "zeroshot", root / "codex/node_modules/.bin/codex"


def run_checked(arguments, **kwargs):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=600, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Blocked("Could not run the setup command: " + str(arguments[0]), family="setup.command_failed") from error
    require(result.returncode == 0, "Setup command failed: %s (exit %s); the previous installation is kept." % (arguments[0], result.returncode), family="setup.command_failed")
    return result.stdout.strip()


def probe_environment():
    """The env of a Codex process outside a login or a turn: CODEX_HOME is `agent_home(os.environ)`, never the
    ~/.codex fallback (Codex writes `<home>/tmp/arg0` on every start, `--version` too). The home goes through
    `launch_home`, so a private home that aliases ~/.codex is refused before anything is created or started; the
    private home is created first, mode 0700, only when it is the one used."""
    env = dict(os.environ)
    home = launch_home(env)
    if not env.get("CODEX_HOME"):
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
    env["CODEX_HOME"] = str(home)
    return env


def check_versions(root, chain=None):
    chain = chain or toolchain.current()
    native, codex = tool_paths(root)
    require(run_checked([str(native), "--version"]) == chain.zeroshot_version, "Native version mismatch.", family="setup.tools_invalid")
    require(run_checked([str(codex), "--version"], env=probe_environment()) == chain.codex_version, "Codex version mismatch.", family="setup.tools_invalid")
    require((root / "restic").is_file(), "Bundled restic is missing; runtime startup is forbidden.", family="setup.tools_invalid")
    require(run_checked([str(root / "restic"), "version"]).startswith(chain.restic_version), "Bundled restic version mismatch.", family="setup.tools_invalid")


def check_installation(chain=None):
    chain = chain or toolchain.current()
    root = tools_root(chain)
    receipt = decode((root / "installation.json").read_text())
    require(isinstance(receipt, dict) and set(receipt) == {"platform", "archive_sha256", "files"}
            and receipt["platform"] == list(platform_key(chain))
            and receipt["archive_sha256"] == chain.releases[platform_key(chain)][1]
            and receipt["files"] == tool_files(root), "Private tools are damaged; execution is forbidden.", family="setup.tools_invalid")
    check_versions(root, chain)
    return root


def platform_key(chain=None):
    releases = (chain or toolchain.current()).releases
    key = (platform.system(), platform.machine())
    require(key in releases, "Setup supports Linux x86_64/aarch64 and macOS arm64; platform: " + str(key), family="setup.unsupported_platform")
    return key


@contextmanager
def setup_lock():
    root = data_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "setup.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Blocked("Another setup is already running.", family="setup.busy") from error
        yield


def install_tools(show, chain=None, archive=None):
    """Install the toolchain (default: this release's) into its own tool dir. `archive` is a local release archive
    used instead of the download (candidate qualification offline); its checksum is verified the same way."""
    chain = chain or toolchain.current()
    key = platform_key(chain)
    require(shutil.which("npm") and shutil.which("node"),
            "Node.js/npm are required. Debian/Ubuntu: sudo apt-get update && sudo apt-get install -y nodejs npm; macOS: brew install node", family="setup.prerequisite")
    version = run_checked([shutil.which("node"), "--version"])
    require(re.fullmatch(r"v\d+\.\d+\.\d+", version) and int(version[1:].split(".")[0]) >= 16,
            "Node.js >=16 is required; install a supported Node.js before setup.", family="setup.prerequisite")
    with setup_lock():
        final = tools_root(chain)
        if final.exists():
            check_installation(chain)
            show("Pinned tools are already installed and verified.")
            return
        final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix=".setup-", dir=final.parent) as directory:
            staging = Path(directory) / "tools"
            staging.mkdir(mode=0o700)
            target, expected = chain.releases[key]
            url = chain.release_url(target)
            downloaded = Path(directory) / "release.tar.gz"
            if archive is None:
                show("Downloading Zeroshot %s; checking the pinned SHA256." % chain.zeroshot)
                with urlopen(url, timeout=60) as response, downloaded.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
                archive = downloaded
            archive = Path(archive)
            require(checksum(archive) == expected, "Release checksum mismatch; installation cancelled.", family="setup.download_invalid")
            with tarfile.open(archive) as bundle:
                for name in ("zeroshot", "restic"):
                    members = [member for member in bundle.getmembers() if Path(member.name).name == name and member.isfile()]
                    require(len(members) == 1, "Release archive malformed: " + name, family="setup.download_invalid")
                    with bundle.extractfile(members[0]) as source, (staging / name).open("wb") as destination:
                        shutil.copyfileobj(source, destination)
                    (staging / name).chmod(0o700)
            npm_root = staging / "codex"
            npm_root.mkdir()
            for name in ("package.json", "package-lock.json"):
                source = (Path(chain.package_dir) / name).read_bytes() if chain.package_dir else \
                    resources.files("terminal_planner").joinpath("resources", name).read_bytes()
                (npm_root / name).write_bytes(source)
            show("Installing Codex %s with npm ci and the integrity from the bundled lockfile." % chain.codex)
            run_checked([shutil.which("npm"), "ci", "--ignore-scripts", "--no-audit", "--no-fund"], cwd=npm_root)
            check_versions(staging, chain)
            (staging / "installation.json").write_text(canonical({"platform": list(key), "archive_sha256": expected, "files": tool_files(staging)}) + "\n")
            os.rename(staging, final)
    show("Tools installed in " + str(final) + "; no model was run.")
    show("Log in: zplan login; then zplan doctor.")


def codex_home(env=None):
    """The home an env names: an explicit $CODEX_HOME, else ~/.codex (Codex's own default).

    Never chosen by which directory holds a login. This is the home of a recorded continuation and of a pre-0.5
    record (`legacy_codex_home`); fresh launches and `login` use `agent_home` instead (R-1)."""
    env = os.environ if env is None else env
    return Path(env.get("CODEX_HOME") or Path.home() / ".codex").expanduser().resolve()


def legacy_codex_home():
    """The home of a record from before 0.5 (R-1): `codex_home` of the process env the owner started zplan with,
    read at call time. Never resolved from an env zplan has modified (`native_environment()`)."""
    return codex_home(os.environ)


def private_codex_home():
    return data_root() / "codex-home"


def agent_home(env):
    """The home a fresh launch and `login` use (R-1): the nonempty `CODEX_HOME` of `env` -- an expert override,
    resolved exactly as `codex_home` resolves one -- else zplan's own `private_codex_home()`. Never ~/.codex: no
    implicit launch reads or writes it."""
    return codex_home(env) if env.get("CODEX_HOME") else private_codex_home()


def launch_home(env=None):
    """The home a launch gets: `agent_home(env)` with the implicit owner-home alias refused (R-1/A-4).

    `native_environment` and the `--native-binary` route both go through here, so no launch anywhere hands Codex
    the owner's own `~/.codex` through a symlinked private home."""
    env = os.environ if env is None else env
    home = agent_home(env)
    if not env.get("CODEX_HOME"):
        _refuse_owner_home(home)
    return home


def _regular_file(path):
    """`Path(path).is_file()` with a filesystem failure answered False: a component longer than NAME_MAX or a
    permission error is "not a file" here, never an OSError escaping the auth judgment."""
    try:
        return Path(path).is_file()
    except OSError:
        return False


def auth_served(home, auth, env):
    """Whether `home` serves the login the provider `auth` needs (R-4), judged by presence only: no value is ever
    read out, printed or logged.

    File auth is served by `<home>/auth.json` being a file, by a nonempty `CODEX_API_KEY`, or by `OPENAI_API_KEY`
    when `CODEX_API_KEY` is absent from `env` -- the native engine copies OPENAI_API_KEY to CODEX_API_KEY only
    when CODEX_API_KEY is absent (upstream `configure_openai_auth`), so an existing empty `CODEX_API_KEY` blocks
    that fallback. Env-key auth is served by its nonempty variable; `None` (no login needed) is always served."""
    if auth == "file":
        if _regular_file(Path(home) / "auth.json"):
            return True
        if env.get("CODEX_API_KEY"):
            return True
        return "CODEX_API_KEY" not in env and bool(env.get("OPENAI_API_KEY"))
    if isinstance(auth, tuple):
        return bool(env.get(auth[1]))
    return True


def child_auth_env(env):
    """`env` as the architect's Codex child must see it (R-4b): when `CODEX_API_KEY` is absent and a nonempty
    `OPENAI_API_KEY` is present, `CODEX_API_KEY` is set to it, mirroring the native engine's own mapping. Returns
    a copy; no value is ever logged."""
    environment = dict(env)
    if "CODEX_API_KEY" not in environment and environment.get("OPENAI_API_KEY"):
        environment["CODEX_API_KEY"] = environment["OPENAI_API_KEY"]
    return environment


def _refuse_owner_home(home):
    """Refuse an implicit zplan home that resolves to Codex's own home or into it (R-1/A-4).

    Only the implicit home is judged: an explicit `CODEX_HOME` is the owner's documented opt-in, even `~/.codex`.
    A private home that is a symlink -- the home itself or any parent -- to `~/.codex` would make zplan replace the
    owner's `config.toml` with the packaged profile, leave a `config.toml.bak` behind and hand Codex the owner's
    home, so the launch and the profile write are refused instead. Raises `setup.agent_home`.

    Both sides go through `os.path.realpath`, never `Path.resolve`: a broken owner path (a `~/.codex` symlink that
    loops) must not crash a launch. Such a path is no usable Codex home, so the check then simply does not fire and
    zplan keeps its own independent private home."""
    try:
        own = Path(os.path.realpath(str(Path.home() / ".codex")))
        resolved = Path(os.path.realpath(str(home)))
    except OSError:
        return
    if resolved == own or own in resolved.parents:
        raise Blocked(
            "The Codex home for zplan %s points into your %s; zplan writes no profile there and runs no Codex there. "
            "Remove the link or set CODEX_HOME to a separate directory." % (home, own),
            family="setup.agent_home")


def _refuse_escaped_profile_lock(home):
    """Refuse a profile lock that would take the write outside `home` (R-1/A-4).

    `agent_profile.ensure` opens `<home>/.zplan-profile.lock` with `O_CREAT` (only to hold its `flock`), so a
    symlink at that name -- e.g. to an absent `~/.codex/unexpected-lock-target` -- makes zplan create a file in the
    owner's home. Any non-regular entry there is refused; the name itself is `agent_profile`'s. Raises
    `setup.agent_home`."""
    from . import agent_profile  # lazily: agent_profile imports this module
    lock = Path(home) / agent_profile.LOCK_NAME
    if not os.path.lexists(str(lock)):
        return
    if os.path.islink(str(lock)) or not os.path.isfile(str(lock)):
        raise Blocked("Agent profile not written: %s is not a regular file; zplan does not write through a link. "
                      "Remove it and retry." % lock, family="setup.agent_home")


def tilde(path):
    """A path for display, with the home directory shortened to ~."""
    home, path = str(Path.home().resolve()), str(path)
    return "~" + path[len(home):] if path == home or path.startswith(home + os.sep) else path


def native_environment(profile=True):
    """The process env of a Codex child: the pinned tools on PATH and CODEX_HOME set to `agent_home(os.environ)`.

    `profile=True` (a fresh launch or `login`) writes zplan's own profile into `private_codex_home()` through
    `agent_profile.ensure` -- exactly when the process env's `CODEX_HOME` is empty or unset, after the tool check
    and before the env is returned. `profile=False` (`status`, which only reads records) writes nothing (R-3c).
    An implicit home that resolves into the owner's own Codex home is refused (R-1/A-4) before anything is written
    or launched, and so is a profile lock that would take that write outside the home; an explicit `CODEX_HOME`
    stays the owner's documented opt-in. A `setup.agent_home` Blocked is never swallowed here."""
    root = check_installation()
    home = launch_home()
    env = dict(os.environ)
    env["PATH"] = str(root / "codex/node_modules/.bin") + os.pathsep + env.get("PATH", "")
    env["CODEX_HOME"] = str(home)
    if profile and not os.environ.get("CODEX_HOME"):
        from . import agent_profile  # lazily: agent_profile imports this module
        _refuse_escaped_profile_lock(private_codex_home())
        agent_profile.ensure(private_codex_home())
    return env


def owned_home(home):
    """Whether `home` is the Codex home zplan owns: the same real directory as `private_codex_home()` (D6a). Judged by
    `os.path.realpath` on both sides, so an alias spelling counts and an override home that merely differs does not.
    zplan logs in and out of an owned home only; any other home is the owner's own Codex."""
    return os.path.realpath(str(home)) == os.path.realpath(str(private_codex_home()))


COPIED_AUTH = ("remove the copy: rm %s — it is a link or a copy of someone else's login, not a zplan login: the refresh token is single-use, "
               "and the copy breaks the other Codex's login at the first refresh. Then run zplan login.")


def copied_auth(home):
    """The path of the private `auth.json` of the owned `home` when it is a copy of someone else's login, else None.

    A copy is an `auth.json` that is a symlink, is not a regular file, or whose bytes equal `~/.codex/auth.json`
    (compared by digest in this process; nothing of either file is read out, printed or logged). A file that cannot
    be read is no evidence of a copy."""
    path = Path(home) / "auth.json"
    try:
        if not os.path.lexists(str(path)):
            return None
        if path.is_symlink() or not path.is_file():
            return str(path)
        theirs = Path.home() / ".codex" / "auth.json"
        if theirs.is_file() and checksum(path) == checksum(theirs):
            return str(path)
    except OSError:
        return None
    return None


def refuse_copied_auth(home):
    """Raise `readiness.auth` naming the `rm` of a copied private `auth.json` (never a logout: signing a copy out
    would revoke the owner's own session). Login, logout and doctor all go through here."""
    path = copied_auth(home)
    if path is not None:
        raise Blocked(COPIED_AUTH % shlex.quote(path), family="readiness.auth")


def home_in_use(home):
    """Why the Codex `home` is busy: a milestone run, a planner run or an architect turn of any project acts in it
    right now (read from the project stores and the architect locks), else None. Read only; a store that cannot be
    read is no evidence of a live run."""
    from . import planning, record_home, runs  # lazily: both import this module
    from .authority import production_root
    target = os.path.realpath(str(home))

    def acts_in(binding):
        try:
            return os.path.realpath(str(record_home.binding_home(binding))) == target
        except (ValueError, TypeError, OSError):
            return False
    for store in sorted(production_root().glob("*/planning.json")):
        try:
            state = json.loads(store.read_text(encoding="utf-8"))
            records = list(state.get("runs", ())) + list(state.get("revisions", ()))
        except (OSError, ValueError, AttributeError):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            status = record.get("status")
            if "native_binding" in record:  # a plan revision: the planner is live from the receipt on
                live = status in planning.OBSERVING + ("submission_unknown",) or (status == "planning" and record.get("run_id"))
                binding = record["native_binding"]
            else:
                live = status in runs.ACTIVE
                binding = record.get("binding")
            if live and isinstance(binding, dict) and acts_in(binding):
                return "a run is active in this Codex directory"
    for lock in sorted((data_root() / "architect").glob("*/lock")):
        try:
            session = json.loads((lock.parent / "session.json").read_text(encoding="utf-8"))
            recorded = session.get("codex_home") if isinstance(session, dict) else None
        except (OSError, ValueError):
            recorded = None
        if recorded is not None and os.path.realpath(str(recorded)) != target:
            continue
        try:
            with lock.open("a") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "the architect is answering in this Codex directory"
        except OSError:
            continue
    return None


def codex_command(*arguments, store=True):
    """The pinned Codex with `arguments`; `login` flows pass the file credential store explicitly."""
    return [str(tool_paths()[1]), *(["-c", 'cli_auth_credentials_store="file"'] if store else []), *arguments]


def foreign(home, verb, show):
    """The answer for a home zplan does not own (L1): no Codex process runs; the owner signs in or out with their
    own `codex`. Returns the exit code: 0 when a login is present there, else 1 (judged by presence only)."""
    show("This is your Codex (%s): %s via codex %s" % (home, "log in" if verb == "login" else "log out", verb))
    try:
        _, auth = codex_provider(home)
        present = auth_served(home, auth, os.environ)
    except Blocked:
        present = False
    show("There is a login there." if present else "There is no login there.")
    return 0 if present else 1


YES_ANSWERS = {"y", "yes", "д", "да"}  # the [y/N] answers that confirm; the Russian short and full "yes" stay accepted as input
INTERRUPTED = 130  # the exit code of a login the owner cut with Ctrl-C (shell convention: 128 + SIGINT)


def plain_output(env):
    """A Codex child whose output is not a terminal gets no colour and no cursor control (`env` is changed)."""
    if not sys.stdout.isatty():
        env.update(NO_COLOR="1", TERM="dumb")
    return env


def ask_confirm(question):
    return input(question + " [y/N]: ").strip().lower() in YES_ANSWERS


def login(show=print, *, home=None, refresh=False, confirm=ask_confirm):
    """Codex device login, only into the home zplan owns (D6a). `home` names the home a recorded run used (the
    auth-failure action); None is `agent_home(os.environ)`.

    A home that is not owned runs no Codex (`foreign`). In the owned home an existing login is kept ("Login already present",
    nothing else runs); `refresh` (the auth-failure action) asks to confirm, signs out of that home and logs in
    again. A copied `auth.json` is refused first. The single `native_environment()` call also writes the profile
    (R-3c); the `mkdir` stays for the owned home, which may not exist yet."""
    home = Path(home) if home else agent_home(os.environ)
    if not owned_home(home):
        return foreign(home, "login", show)
    refuse_copied_auth(home)
    env = plain_output(native_environment())
    env["CODEX_HOME"] = str(home)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        if refresh:
            busy = home_in_use(home)
            require(busy is None, "Login not refreshed: %s." % busy, family="action.refused")
            require(confirm("Sign out of the zplan login (%s) and log in again?" % home), "Login not refreshed: not confirmed.",
                    family="action.refused")
            # Only Codex handles credential bytes; never capture or persist its output.
            if subprocess.call(codex_command("logout", store=False), env=env):
                return 1
        elif subprocess.call(codex_command("login", "status"), env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL) == 0:
            show("Login already present")
            return 0
        code = subprocess.call(codex_command("login", "--device-auth"), env=env)
    except KeyboardInterrupt:
        code = INTERRUPTED
    if code in (INTERRUPTED, -signal.SIGINT):  # Ctrl-C reached the Codex child (or only it)
        show("Login interrupted.")
        return INTERRUPTED
    return code


def logout(show=print):
    """`codex logout` of the home zplan owns (D6a): revokes zplan's own token only. Refused for a home that is not
    owned (no Codex runs), for a copied `auth.json`, and while a run or the architect acts in the home."""
    home = agent_home(os.environ)
    if not owned_home(home):
        return foreign(home, "logout", show)
    refuse_copied_auth(home)
    busy = home_in_use(home)
    require(busy is None, "Logout not done: %s." % busy, family="action.refused")
    return subprocess.call(codex_command("logout", store=False), env=plain_output(native_environment()))


GITHUB_ORIGIN = re.compile(r"(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|ssh://git@github\.com/)"
                           r"([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?")
# 10.12's GitRemoteUrl rejects HTTPS userinfo; a credentialed origin must be fixed, never echoed.
GITHUB_USERINFO = re.compile(r"^https://[^@/]+@")


def item(name, ok, doctor, line, detail="", key=None, severity=None):
    """One readiness check: `doctor` is the `zplan doctor` line, `line` the short start-screen line, `detail` the
    fix instruction ([i]) and `key` the start-screen key that fixes it (u install, l login, d changes, i details).
    `severity` is "ok", "warn" or "block"; None keeps the old two-state meaning, "ok" when ok else "block" (R-1).
    A warning keeps ok=True, so it never blocks a start, plan or resume; only a block does. An inconsistent pair
    (a warn or ok with ok=False, a block with ok=True) or an unknown word is refused."""
    if severity is None:
        severity = "ok" if ok else "block"
    elif severity == "block":
        if ok:
            raise ValueError("severity 'block' needs ok=False")
    elif severity in ("ok", "warn"):
        if not ok:
            raise ValueError("severity %r needs ok=True" % (severity,))
    else:
        raise ValueError("unknown severity %r" % (severity,))
    return {"id": name, "ok": ok, "doctor": doctor, "line": line, "detail": detail, "key": key, "severity": severity}


def severity(check):
    """The severity of one readiness item: its own `severity` key, else "ok" when ok and "block" when not. Reads
    dicts the product did not build (older items, tests): a missing key stays valid (R-1)."""
    return check.get("severity") or ("ok" if check["ok"] else "block")


def check_target(project):
    """Milestone runs need an attached branch and a GitHub-shaped origin; the raw URL is never shown. Uncommitted
    changes never block: the `clean` item only says how many files the last commit does not hold.

    Yields one readiness item per check; stops after a failure the later checks depend on."""
    from .authority import discover, git
    try:
        root = discover(project)
    except Blocked:
        yield item("repo", False, "Target is not a Git project with a commit; cd into a project or give --project.",
                   "The directory is not a Git project with a commit", "cd into a project or give --project.", "i")
        return
    yield item("repo", True, "Target: Git project " + str(root), "Project " + root.name)
    try:
        branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
        yield item("branch", True, "Target: branch " + branch, "Branch " + branch)
    except Blocked:
        yield item("branch", False, "Target HEAD is detached; switch to a branch: git switch <branch>.",
                   "HEAD detached — [i] instructions", "Switch to a branch: git switch <branch>.", "i")
    try:
        origin = git(root, "remote", "get-url", "origin").decode().strip()
    except Blocked:
        origin = ""
    match = GITHUB_ORIGIN.fullmatch(origin)
    if match:
        repository = "github.com/%s/%s" % (match.group(1), match.group(2))
        if GITHUB_USERINFO.match(origin):
            # Never print the URL: it carries credentials the native Git remote parser refuses.
            fix = "git remote set-url origin https://%s.git" % repository
            yield item("origin", False, "Target origin %s carries userinfo; 10.12 rejects such a URL. %s."
                       % (repository, fix), "Origin with credentials — [i] instructions",
                       "Your URL carries a login/password (zplan does not show it). Run it yourself: " + fix, "i")
        else:
            yield item("origin", True, "Target: origin %s" % repository, "GitHub origin present")
    else:
        yield item("origin", False, "Target origin is not a GitHub repository; add one: "
                   "git remote add origin https://github.com/OWNER/REPO.git (or git remote set-url origin ...).",
                   "No GitHub origin — [i] instructions",
                   "Zeroshot names the project after its origin; zplan pushes nothing. Add one yourself: "
                   "git remote add origin https://github.com/OWNER/REPO.git (or git remote set-url origin ...).", "i")
    from . import process, project_read  # lazily: both import this module
    changed = project_read.uncommitted_paths(root)
    if changed:
        # Informational (ok, never a block): planner, checks and runs work on the last commit, whatever the tree holds.
        count = len(changed)
        noun = "file" if count == 1 else "files"
        note = "Not committed: %d %s — the plan sees the last commit" % (count, noun)
        if process.PROFILE_FILE in changed:
            note += "; %s is not committed — runs see the last commit" % process.PROFILE_FILE
        yield item("clean", True, "Target: " + note, note)
    else:
        yield item("clean", True, "Target: working tree clean", "Working tree clean")


# Minimal TOML for Python < 3.11 (no tomllib): enough of Codex config.toml to select the provider.
TOML_KEY = r'[A-Za-z0-9_-]+|"(?:[^"\\\n]|\\.)*"|\'[^\'\n]*\''
TOML_PATH = re.compile(r'[ \t]*((?:%s)(?:[ \t]*\.[ \t]*(?:%s))*)[ \t]*' % (TOML_KEY, TOML_KEY))
TOML_STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'[^\'\n]*\'')
TOML_SCALAR = re.compile(r'true|false|[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[T ][0-9:.]+(?:Z|[+-][0-9:]+)?)?|[0-9:.]{8,}'
                         r'|0x[0-9A-Fa-f_]+|0o[0-7_]+|0b[01_]+|[+-]?(?:inf|nan)'
                         r'|[+-]?[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9_]+)?')
TOML_END = re.compile(r'[ \t]*(?:#[^\n]*)?(?:\r?\n|$)')


def toml_keys(path):
    return [json.loads(key) if key.startswith('"') else key.strip("'") for key in re.findall(TOML_KEY, path)]


def toml_opaque(text, start):
    """End of an array, inline table or multi-line string; their contents are not needed."""
    for quote in ('"""', "'''"):
        if text.startswith(quote, start):
            end = text.find(quote, start + 3)
            if end < 0:
                raise ValueError("unterminated string")
            return end + 3
    depth, i = 0, start
    while i < len(text):
        if text[i] in "[{":
            depth += 1
        elif text[i] in "]}":
            depth -= 1
            if depth == 0:
                return i + 1
        elif text[i] in "\"'":
            match = TOML_STRING.match(text, i)
            if not match:
                raise ValueError("bad string")
            i = match.end()
            continue
        elif text[i] == "#":
            i = text.find("\n", i)
            if i < 0:
                break
        i += 1
    raise ValueError("unterminated value")


def minimal_toml(text):
    data, i = {}, 0
    table = data
    while i < len(text):
        blank = TOML_END.match(text, i)
        if blank and blank.end() > i:
            i = blank.end()
            continue
        header = re.compile(r'[ \t]*\[(\[?)').match(text, i)
        if header:
            path = TOML_PATH.match(text, header.end())
            close = "]]" if header.group(1) else "]"
            if not path or not text.startswith(close, path.end()):
                raise ValueError("bad table header at offset %d" % i)
            table = data
            for key in toml_keys(path.group(1)) if not header.group(1) else ():
                table = table.setdefault(key, {})
                if not isinstance(table, dict):
                    raise ValueError("table redefines a value")
            if header.group(1):
                table = {}  # array-of-tables entries are not needed
            i = path.end() + len(close)
        else:
            path = TOML_PATH.match(text, i)
            if not path or not text.startswith("=", path.end()):
                raise ValueError("expected key = value at offset %d" % i)
            start = re.compile(r'=[ \t]*').match(text, path.end()).end()
            value = None
            if text.startswith(('"""', "'''", "[", "{"), start):
                end = toml_opaque(text, start)
            else:
                match = TOML_STRING.match(text, start) or TOML_SCALAR.match(text, start)
                if not match:
                    raise ValueError("bad value at offset %d" % start)
                end, raw = match.end(), match.group()
                value = (json.loads(raw) if raw.startswith('"') else raw[1:-1] if raw.startswith("'")
                         else {"true": True, "false": False}.get(raw, raw))
            keys, target = toml_keys(path.group(1)), table
            for key in keys[:-1]:
                target = target.setdefault(key, {})
                if not isinstance(target, dict):
                    raise ValueError("key redefines a value")
            target[keys[-1]] = value
            i = end
        end = TOML_END.match(text, i)
        if not end:
            raise ValueError("trailing characters at offset %d" % i)
        i = end.end()
    return data


def read_toml(text):
    try:
        import tomllib
    except ImportError:
        return minimal_toml(text)
    return tomllib.loads(text)  # TOMLDecodeError is a ValueError


# Codex built-in providers and how each authenticates: "file" = ChatGPT/OpenAI login in CODEX_HOME/auth.json.
CODEX_PROVIDERS = {"openai": "file", "oss": None, "ollama": None, "lmstudio": None}


def codex_provider(home):
    """(provider, auth) as Codex selects them from CODEX_HOME/config.toml; auth is None, "file" or ("env", NAME)."""
    path = home / "config.toml"
    if not path.exists():
        return "openai", "file"
    try:
        config = read_toml(path.read_text())
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Blocked("Codex config %s cannot be read (%s); fix the file or remove it to restore the Codex defaults."
                      % (path, type(error).__name__), family="readiness.codex_home") from error
    def table(value):
        return value if isinstance(value, dict) else {}

    provider = config.get("model_provider", "openai")
    profile = config.get("profile")
    if profile is not None:
        selected = table(config.get("profiles")).get(profile) if isinstance(profile, str) else None
        require(isinstance(selected, dict), "Codex profile %r not found in %s; fix the profile or add [profiles.%s]."
                % (profile, path, profile), family="readiness.codex_home")
        provider = selected.get("model_provider", provider)
    require(isinstance(provider, str), "Codex model_provider in %s is not a string; fix the file." % path, family="readiness.codex_home")
    custom = table(config.get("model_providers")).get(provider)
    if isinstance(custom, dict):
        if isinstance(custom.get("env_key"), str) and custom["env_key"]:
            return provider, ("env", custom["env_key"])
        return provider, "file" if custom.get("requires_openai_auth") is True else None
    require(provider in CODEX_PROVIDERS, "Codex provider %r is not defined in %s; add [model_providers.%s] or choose openai."
            % (provider, path, provider), family="readiness.codex_home")
    return provider, CODEX_PROVIDERS[provider]


def global_identity():
    values = [subprocess.run(["git", "config", "--global", "--get", key], capture_output=True, text=True,
                             timeout=60).stdout.strip() for key in ("user.name", "user.email")]
    return tuple(values) if all(values) else None


def tools_missing():
    chain = toolchain.current()
    return ("The zplan tools are not installed\n"
            "  Verified Zeroshot %s and Codex %s are required (zplan's own copy; global ones are left alone)." % (chain.zeroshot, chain.codex))


def readiness(project=None, native_state_dir=None, tools=True):
    """The one readiness check list behind `zplan doctor` and the start screen, in doctor order.

    tools=False (the deterministic fixture engine) keeps only the git and project checks. Secrets and credential
    files are never read out: auth is judged by presence only."""
    from .engine import check_socket_path
    from .runs import configured_identity
    items = []
    if tools:
        try:
            items.append(item("socket", True, "native socket path %s bytes" % check_socket_path(native_state_dir or native_state_root()), ""))
        except Blocked as error:
            items.append(item("socket", False, str(error), "The Zeroshot socket path is too long — [i] details", str(error), "i"))
        zeroshot, codex = tool_paths()
        try:
            check_installation()
            items.append(item("tools", True, "%s · pinned checksums · %s" % (toolchain.current().zeroshot_version, zeroshot), ""))
        except (Blocked, OSError, ValueError) as error:
            items.append(item("tools", False, "zeroshot is not installed or damaged (%s); run zplan setup." % error,
                              tools_missing(), "Install: [u] or zplan setup.", "u"))
        if codex.is_file() and os.access(codex, os.X_OK):
            items.append(item("codex", True, "codex " + str(codex), ""))
        else:
            items.append(item("codex", False, "codex binary is missing: %s; run zplan setup." % codex,
                              tools_missing(), "Install: [u] or zplan setup.", "u"))
        home = agent_home(os.environ)
        source = "your $CODEX_HOME, not zplan's profile" if os.environ.get("CODEX_HOME") else "zplan"
        try:
            provider, auth = codex_provider(home)
            items.append(item("codex_home", True, "CODEX_HOME %s (%s) · provider %s%s" % (
                home, source, provider, "" if (home / "config.toml").exists() else " (no config.toml: Codex defaults)"), ""))
        except Blocked as error:
            items.append(item("codex_home", False, str(error), "Codex settings cannot be read — [i] details", str(error), "i"))
            auth = provider = None
        where = "%s · provider %s" % (tilde(home), provider)
        if provider is None:
            pass  # the provider line already blocks; auth of an unknown provider cannot be judged
        elif auth == "file" and owned_home(home) and (copy := copied_auth(home)):
            fix = COPIED_AUTH % shlex.quote(copy)
            items.append(item("auth", False, "auth: " + fix, "Codex: login in %s — copy: remove the copy: rm %s" % (where, shlex.quote(copy)),
                              fix, "i"))
        elif auth is None:
            items.append(item("auth", True, "auth: provider %s needs no login" % provider,
                              "Codex: %s · no login needed" % where))
        elif auth_served(home, auth, os.environ):
            if auth == "file":
                items.append(item("auth", True, "auth: login file present in CODEX_HOME (presence, not validity)",
                                  "Codex: login found in " + where))
            else:
                items.append(item("auth", True, "auth: $%s is set (presence, not validity)" % auth[1],
                                  "Codex: %s · key $%s is set" % (where, auth[1])))
        elif auth == "file":
            if owned_home(home):
                fix = ("no login for provider %s in %s; zplan needs its own Codex login once — run zplan login or "
                       "press [l]. Your ~/.codex login is not used or changed; to use your own Codex, log in with "
                       "codex login and set CODEX_HOME=... before zplan." % (provider, home))
                items.append(item("auth", False, fix, "Codex: no login in %s — [l] log in (zplan's own login, not ~/.codex)" % where,
                                  "[l] starts a Codex login in %s; zplan does not read, copy or change your ~/.codex login; "
                                  "to use your own Codex, log in with codex login and set CODEX_HOME=... before zplan." % tilde(home), "l"))
            else:
                fix = ("no login for provider %s in %s: this is your Codex, zplan does not log into it. Run codex login with "
                       "CODEX_HOME=%s and run zplan again; or unset CODEX_HOME — zplan has its own directory and its own "
                       "login (run zplan login)." % (provider, home, home))
                items.append(item("auth", False, fix, "Codex: no login in your %s — [i] instructions" % where, fix, "i"))
        else:
            items.append(item("auth", False, "variable %s for provider %s is not set; export %s=... before zplan."
                              % (auth[1], provider, auth[1]),
                              "Codex: variable %s for provider %s is not set — [i] instructions" % (auth[1], provider),
                              "Quit, run export %s=... and start zplan again; zplan does not show the value."
                              % auth[1], "i"))
    git_path = shutil.which("git")
    if git_path and (old := old_git(git_path)):
        fix = "update git to %d.%d or newer (macOS: brew upgrade git; Debian/Ubuntu: the git-core PPA or a newer distribution)." % GIT_MINIMUM
        items.append(item("git", False, "git %s is too old: git %d.%d or newer is required (merge-tree --write-tree); %s"
                          % (old, *GIT_MINIMUM, fix),
                          "Git %s is too old — %d.%d is required, [i] instructions" % (old, *GIT_MINIMUM), fix, "i"))
    elif git_path:
        items.append(item("git", True, "git " + git_path, ""))
        # Outside a project only the global identity applies; `git -C <home>` would also read a home repository.
        identity = (configured_identity(project) if project is not None and Path(project).is_dir()
                    else global_identity())
        if identity:
            items.append(item("identity", True, "Git identity %s <%s>" % identity, ""))
        else:
            fix = "git config --global user.name \"Name\" and user.email you@example.com."
            items.append(item("identity", False, "Git identity is not set; " + fix,
                              "The Git author name is not set — [i] instructions", "Run " + fix, "i"))
    else:
        fix = "macOS: xcode-select --install; Debian/Ubuntu: sudo apt-get install -y git."
        items.append(item("git", False, "git is missing; " + fix, "Git is not installed — [i] instructions", fix, "i"))
    if tools:
        try:
            items.append(item("roles", True, "roles " + "; ".join("%s=%s/%s" % (role, value["model"], value["effort"])
                                                                for role, value in load_roles().items()), ""))
        except (Blocked, OSError, ValueError) as error:
            fix = "run zplan roles or delete %s." % (config_root() / "roles.json")
            items.append(item("roles", False, "roles config is damaged (%s); %s" % (error, fix),
                              "Role settings are damaged — [i] instructions", fix, "i"))
    if project is not None:
        items.extend(check_target(project))
    return items


GIT_MINIMUM = (2, 38)  # `git merge-tree --write-tree`: the merge is built off the owner's tree
GIT_VERSION = re.compile(r"git version (\d+)\.(\d+)")


def old_git(git_path):
    """The version text («2.37») of `git_path` when it is older than `GIT_MINIMUM`, else None -- also when the version
    cannot be read: an unreadable one is no evidence of an old git, and a merge it cannot build is refused later."""
    try:
        out = subprocess.run([git_path, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = GIT_VERSION.match(out)
    return "%s.%s" % found.groups() if found and tuple(map(int, found.groups())) < GIT_MINIMUM else None


def profile_lines(show, project):
    """The project's process profile for doctor: state, file, digest, role bindings with sources, gates, checks.
    Reads only (no lock, no prompt, no model); False when the accepted profile is missing or invalid."""
    if project is None:
        return True
    from . import process  # lazily: process imports this module
    from .authority import Blocked, discover
    try:
        try:
            project = discover(project)  # the profile lives at the Git top level, also from a subdirectory
        except Blocked:
            pass  # outside Git: peek reports what it can
        status = process.Profile.peek(project).status()
    except Blocked as error:
        show("BLOCKED: " + str(error))
        return False
    broken = status.state in ("missing", "malformed")
    lines = process.describe(status)
    if broken:  # only a refusal is a doctor check line; a usable profile is plain information
        lines[0] = "BLOCKED: " + lines[0]
    for line in lines:
        show(line)
    return not broken


def doctor(show, native_state_dir=None, project=None):
    """One line per readiness check; a failed check names its fix.

    After the items comes one informational line about zplan's own agent profile, for the zplan home only (R-5);
    an override home gets none. Doctor writes nothing."""
    from . import __version__
    show("Planning Kit " + __version__ + " · " + " ".join(platform_key()))
    chain = toolchain.current()
    show("Toolchain: %s · %s · %s · directory %s" % (chain.zeroshot_version, chain.codex_version, chain.restic_version,
                                                  tilde(tools_root(chain))))
    items = readiness(project, native_state_dir)
    for check in items:
        show({"ok": "OK: ", "warn": "WARN: ", "block": "BLOCKED: "}[severity(check)] + check["doctor"])
    if not os.environ.get("CODEX_HOME"):  # R-5: the profile line belongs to zplan's own home
        from . import agent_profile  # lazily: agent_profile imports this module
        try:  # R-5: doctor writes nothing and must never abort -- an entry that cannot be read is no profile
            written = agent_profile.written_version(private_codex_home())
        except OSError:
            written = None
        packaged = agent_profile.version(agent_profile.packaged())
        show("zplan agent profile: " + ("profile %s (packaged %s)." % (written, packaged) if written is not None
                                           else "not written yet (written at login or first launch)."))
    if project is None:
        show("Target: not selected (cd into a Git project or give --project); it does not affect tools readiness.")
        show("Process profile: no project selected.")
    profile_ready = profile_lines(show, project)  # always shown, also while other checks are blocked
    ready = all(severity(check) != "block" for check in items) and profile_ready
    if ready:
        show("Plan: ready.")
    return 0 if ready else 1
