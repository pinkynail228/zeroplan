"""The one qualified toolchain of this zplan release: exact versions, platform archive checksums, bundled Codex
lockfile and restic pin. Every other module reads it from here; a Zeroshot/Codex upgrade is a change to DEFAULT
(docs/UPGRADE.md) plus a new zplan release. There is deliberately no registry of several versions.

Stdlib only: setup, engine, authority and the candidate qualification script all import it.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass(frozen=True)
class Toolchain:
    zeroshot: str
    codex: str
    restic: str
    # Names the private bundle layout. Bump it with any change to the bundle's contents (restic, lockfile, layout)
    # that keeps the versions: a bundle is never replaced in place.
    runtime: str
    url_template: str
    # (system, machine) -> (release target, SHA256 of that release archive)
    releases: dict = field(default_factory=dict)
    # Directory holding package.json and package-lock.json for the Codex npm ci; None: the files bundled in the wheel.
    package_dir: str = None

    @property
    def zeroshot_version(self):
        return "zeroshot " + self.zeroshot

    @property
    def codex_version(self):
        return "codex-cli " + self.codex

    @property
    def restic_version(self):
        return "restic " + self.restic

    @property
    def tool_dir_name(self):
        return "zeroshot-%s-codex-%s-%s" % (self.zeroshot, self.codex, self.runtime)

    def release_url(self, target):
        return self.url_template.format(version=self.zeroshot, target=target)


DEFAULT = Toolchain(
    zeroshot="11.0.0", codex="0.162.1", restic="0.19.1", runtime="runtime2",
    url_template="https://github.com/the-open-engine/zeroshot/releases/download/v{version}/zeroshot-v{version}-{target}.tar.gz",
    releases={
        ("Linux", "x86_64"): ("x86_64-unknown-linux-musl", "8276d1a601975d8f21afa1cbe39744d2f3f6c206a195654fdf83519107e30c4c"),
        ("Linux", "aarch64"): ("aarch64-unknown-linux-musl", "dc663492b9ebccb902227057a61ab78b9a3e7e0a96cdf5746cfc4b34b3ad6465"),
        ("Darwin", "arm64"): ("aarch64-apple-darwin", "f3e349870e58a0b1da366389bfdb7298d5f28b287c420632ed91a07f96cf1710"),
    })

# Shape of a stored native binding (planning.json `native_binding`, run record `binding`).
BINDING_FIELDS = frozenset({"executable", "state_root", "sha256", "version"})
_VERSION = re.compile(r"zeroshot \d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def current():
    """The default toolchain, read at call time (tests and the candidate script substitute it)."""
    return DEFAULT


def valid_codex_home(value):
    """A recorded Codex home by shape only (R-2): an absolute, nonempty str without NUL, at most 4096 characters.
    Never resolved, created or checked for existence: a missing recorded home is the engine's own error (R-4)."""
    return (isinstance(value, str) and bool(value) and len(value) <= 4096 and "\x00" not in value
            and Path(value).is_absolute())


def valid_binding(binding):
    """A recorded native binding by shape only: absolute paths, a `zeroshot X.Y.Z` version string and a sha256.
    A pre-0.5 record carries the four BINDING_FIELDS alone; a record from 0.5 on adds `codex_home` (R-2); any other
    key set is invalid. Never compared with the current default: records of an older toolchain stay readable."""
    if not isinstance(binding, dict):
        return False
    keys = set(binding)
    if keys not in (BINDING_FIELDS, BINDING_FIELDS | {"codex_home"}):
        return False
    return (all(isinstance(binding[k], str) and Path(binding[k]).is_absolute() for k in ("executable", "state_root"))
            and bool(_VERSION.fullmatch(binding["version"])) and bool(_SHA256.fullmatch(binding["sha256"]))
            and (keys == BINDING_FIELDS or valid_codex_home(binding["codex_home"])))
