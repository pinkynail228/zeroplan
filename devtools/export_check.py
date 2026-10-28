#!/usr/bin/env python3
"""Content and manifest check for the public export (devtools only).

Everything is read from one commit (``REV``) of a git repository -- the manifest
and the exemptions included -- never from the working tree, so a working-tree
edit cannot change the result for the same ``REV``.

Exit codes: 0 clean, 1 findings, 2 usage/git error, 3 incomplete (no private
terms were supplied and there are no other findings).

Besides the content rules the checker runs a link/path policy over the live
markdown set of the commit (S-2): every inline link, reference definition and
top-level-state path must stay inside the export, and a live line may name an
excluded directory only as plain wording about the private archive.
"""
import argparse
import fnmatch
import hashlib
import os
import posixpath
import re
import stat
import subprocess
import sys
import urllib.parse

MANIFEST_PATH = "devtools/export-manifest.txt"
EXEMPTIONS_PATH = "devtools/export-exemptions.txt"

CONTENT_RULES = (
    ("openai", re.compile(r"sk-(?!ant-)[A-Za-z0-9_-]{20,}")),
    ("anthropic", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("github", re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}")),
    ("aws", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("yandex", re.compile(r"(?:y0_|AQVN)[A-Za-z0-9_-]{20,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("credential", re.compile(
        r"(api_key|token|password|secret)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']",
        re.IGNORECASE)),
    ("url-userinfo", re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
    ("bearer", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{16,}")),
    ("home-path", re.compile(
        r"/(?:Users|home)/(?!(?:user|testuser|runner)(?![A-Za-z0-9._-]))"
        r"[A-Za-z0-9._-]+")),
)

IMAGE_DIR = "docs/img/"
IMAGE_MAX_BYTES = 2 * 1024 * 1024
IMAGE_SIGNATURES = {
    ".gif": (b"GIF87a", b"GIF89a"),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}

REPORT_ORDER = (
    "openai", "anthropic", "github", "aws", "slack", "google", "yandex",
    "private-key", "jwt", "credential", "url-userinfo", "bearer", "home-path",
    "private-term", "private-path", "secret-path",
    "symlink", "gitlink", "unreadable",
    "bad-link", "dead-link", "state-path", "plain-path",
    "dir-extra", "dir-missing", "dir-changed", "stale-exemption",
)


class CheckError(Exception):
    """Usage or git error (mapped to exit code 2)."""


class _ArgumentParser(argparse.ArgumentParser):
    """Never echo user-supplied argument values in a diagnostic."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("export_check: error: invalid command line\n")
        raise SystemExit(2)


def _git(repo, *args):
    try:
        return subprocess.run(
            ["git", "-C", repo, *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError as exc:
        raise CheckError("cannot run git (%s)" % exc.__class__.__name__)


def resolve_repo(repo_arg):
    proc = _git(repo_arg or ".", "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        raise CheckError("not a git repository (or git is unavailable)")
    return proc.stdout.decode("utf-8", "replace").strip()


def resolve_rev(repo, rev):
    proc = _git(repo, "rev-parse", "--verify", "%s^{commit}" % rev)
    if proc.returncode != 0:
        raise CheckError("unknown revision")
    return proc.stdout.decode("ascii", "replace").strip()


def read_rev_file(repo, rev, path):
    proc = _git(repo, "cat-file", "blob", "%s:%s" % (rev, path))
    if proc.returncode != 0:
        return None
    return proc.stdout


def ls_tree(repo, rev):
    proc = _git(repo, "ls-tree", "-r", "-z", rev)
    if proc.returncode != 0:
        raise CheckError("cannot read the tree of the requested revision")
    entries = []
    for record in proc.stdout.split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        parts = meta.split(b" ")
        if len(parts) != 3:
            raise CheckError("unexpected ls-tree record")
        mode = parts[0].decode("ascii")
        entries.append((raw_path.decode("utf-8", "surrogateescape"), mode,
                        parts[2].decode("ascii")))
    return entries


def parse_manifest(data):
    if data is None:
        raise CheckError("missing %s in the requested revision" % MANIFEST_PATH)
    includes, excludes = [], []
    for raw in data.decode("utf-8", "surrogateescape").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        sign, pattern = line[0], line[1:].strip()
        if sign not in "+-" or not pattern:
            raise CheckError("malformed line in %s" % MANIFEST_PATH)
        (includes if sign == "+" else excludes).append(pattern)
    return includes, excludes


def parse_exemptions(data):
    ordered = []
    if data is None:
        return ordered
    for raw in data.decode("utf-8", "surrogateescape").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise CheckError("malformed line in %s" % EXEMPTIONS_PATH)
        ordered.append((parts[0], parts[1], parts[2].lower()))
    return ordered


def parse_private_terms(data):
    terms = []
    for raw in data.splitlines():
        term = raw.strip().lower()
        if term:
            terms.append(term)
    return terms


def matches(pattern, path):
    if pattern.endswith("/"):
        return path.startswith(pattern)
    return fnmatch.fnmatchcase(path, pattern)


def is_exported(path, includes, excludes):
    if not any(matches(p, path) for p in includes):
        return False
    return not any(matches(p, path) for p in excludes)


def redact(path):
    digest = hashlib.sha256(path.encode("utf-8", "surrogateescape")).hexdigest()
    return "<redacted:%s>" % digest[:12]


_PATH_ESCAPES = {code: "\\x%02x" % code for code in range(0x20)}
_PATH_ESCAPES[0x7F] = "\\x7f"
_PATH_ESCAPES.update({code: "\\u%04x" % code for code in range(0x80, 0xA0)})
_PATH_ESCAPES[0x2028] = "\\u2028"
_PATH_ESCAPES[0x2029] = "\\u2029"


def printable(text):
    """Render a path for the report.

    Undecodable bytes and control characters (tab, newline, terminal escapes,
    line separators) are escaped so one finding stays exactly one line and the
    report cannot be corrupted by a crafted name.  Checks and hashes still use
    the original path.
    """
    text = text.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
    return text.translate(_PATH_ESCAPES)


def is_readme_image(path, blob):
    """The one non-UTF-8 blob the export accepts: a GIF or PNG under docs/img/.

    The path, the format's signature and the size must all hold.
    """
    if not path.startswith(IMAGE_DIR) or len(blob) > IMAGE_MAX_BYTES:
        return False
    signatures = IMAGE_SIGNATURES.get(posixpath.splitext(path)[1])
    return signatures is not None and blob.startswith(signatures)


def line_digest(line):
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def iter_lines(text):
    for line in text.split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        yield line


def collect_disk(root):
    """Return (files, dirs) below ``root`` keyed by relative path.

    An incomplete walk (an unreadable directory) is an error, never a silently
    truncated tree.
    """
    files = {}
    dirs = {}

    def onerror(_error):
        raise CheckError("cannot read the --dir tree completely")

    for current, subdirs, names in os.walk(root, onerror=onerror):
        relative = os.path.relpath(current, root)
        if relative != ".":
            dirs[relative] = current
        for name in list(subdirs):
            full = os.path.join(current, name)
            if os.path.islink(full):
                subdirs.remove(name)
                files[os.path.relpath(full, root)] = full
        for name in names:
            full = os.path.join(current, name)
            files[os.path.relpath(full, root)] = full
    return files, dirs


_LIVE_TASKS = "devtools/zeroshot/tasks/"
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_REF_DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(\S+)")
_WHITESPACE = re.compile(r"\s")
_PATH_TOKEN = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:md|py|sh|json|txt)")
_PLAIN_PATHS = ("docs/history/", "prototype/", "reference/")
_ARCHIVE_MARKER = "private archive"


def live_markdown(paths):
    """The S-2 live set: exported markdown except the closed task records."""
    return sorted(path for path in paths
                  if path.endswith(".md") and not path.startswith(_LIVE_TASKS))


def _link_target(line, start):
    """Target of the link opened by ``](`` at ``start``; ``(None, False)``
    means the ``](`` has no closing ``)`` on the line (fail closed)."""
    rest = line[start + 2:]
    close = rest.find(")")
    if close < 0:
        return None, False
    space = _WHITESPACE.search(rest)
    if space is not None and space.start() < close:
        return rest[:space.start()], True
    return rest[:close], True


def _resolve_target(path, target):
    """Resolve one link target against the file's directory.

    ``(None, None)`` is external (scheme target, ``<scheme:...>`` autolink,
    bare ``#fragment``); ``(None, message)`` is a grammar finding;
    ``(resolved, None)`` must be checked against the export set.

    The target is classified before any local path handling: a scheme is read
    off the raw target, so ``https://host/%zz`` never reaches the percent
    checks and an encoded colon (``missing%3Afile.md``) stays a local path.
    The angle form must be a whole ``<scheme:...>`` autolink: a suffix after the
    closing ``>`` (``<https://host>missing.md``) is a finding.
    """
    if target.startswith("<"):
        if target.endswith(">") and ">" not in target[1:-1] \
                and _SCHEME.match(target[1:-1]):
            return None, None
        if ">" not in target:
            return None, "unclosed angle target"
        return None, "angle target without a scheme"
    if target.startswith("#"):
        return None, None
    if _SCHEME.match(target):
        return None, None
    cut = len(target)
    for mark in ("#", "?"):
        index = target.find(mark)
        if 0 <= index < cut:
            cut = index
    core = target[:cut]
    if not core:
        return None, None
    if _BAD_ESCAPE.search(core):
        return None, "invalid percent escape"
    try:
        decoded = urllib.parse.unquote(core, errors="strict")
    except UnicodeDecodeError:
        return None, "invalid percent escape"
    resolved = _resolve_relative(posixpath.dirname(path), decoded)
    if resolved is None:
        return None, "escapes the repository root"
    return resolved, None


def _resolve_relative(base, decoded):
    """Resolve the decoded target against ``base`` (the file's directory).

    ``None`` when the target walks above the repository root.  The walk runs on
    the decoded components *before* any normalization, so ``/../root.md`` and
    ``/docs/../../root.md`` cannot be flattened back onto an exported path.
    A leading ``/`` starts at the repository root and ignores ``base``.
    """
    stack = [] if decoded.startswith("/") else [
        piece for piece in base.split("/") if piece not in ("", ".")]
    for piece in decoded.split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if not stack:
                return None
            stack.pop()
        else:
            stack.append(piece)
    return "/".join(stack)


def _in_export(resolved, exported):
    """True when the resolved target is exported or a prefix of exported paths."""
    if resolved in ("", "."):
        return True
    if resolved in exported:
        return True
    prefix = resolved + "/"
    return any(candidate.startswith(prefix) for candidate in exported)


def markdown_findings(path, text, exported):
    """Yield ``(rule, line)`` link/path findings for one live markdown file.

    Closed grammar (S-2): inline ``[text](target)`` (the target runs to the
    first ``)`` or whitespace, an optional ``"title"`` is ignored) and
    reference definitions ``[label]: target``; a scheme target, a
    ``<scheme:...>`` autolink and a bare ``#fragment`` are external; any other
    ``<...>`` target that is not a whole ``<scheme:...>`` autolink and any
    ``](`` without a closing ``)`` on the line fail closed.  Percent escapes
    are decoded (an invalid one fails), the target
    resolves relative to the file's directory (a leading ``/`` is the repo
    root) and must be exported or a directory prefix of exported paths; a
    target walking above the repository root fails.  A live line naming an
    excluded directory is a finding unless it carries the marker ``private
    archive``; ``upstream/`` is allowed.
    """
    plain = _PLAIN_PATHS + (("history/",) if path.startswith("docs/") else ())
    for number, line in enumerate(iter_lines(text), 1):
        if _ARCHIVE_MARKER not in line and any(token in line for token in plain):
            yield "plain-path", number
        index = line.find("](")
        while index >= 0:
            target, closed = _link_target(line, index)
            if not closed:
                yield "bad-link", number
            else:
                resolved, error = _resolve_target(path, target)
                if error is not None:
                    yield "bad-link", number
                elif resolved is not None and not _in_export(resolved, exported):
                    yield "dead-link", number
            index = line.find("](", index + 2)
        definition = _REF_DEFINITION.match(line)
        if definition is not None:
            resolved, error = _resolve_target(path, definition.group(2))
            if error is not None:
                yield "bad-link", number
            elif resolved is not None and not _in_export(resolved, exported):
                yield "dead-link", number


def state_path_findings(text, exported, top_level):
    """Yield ``(rule, line)`` for repo paths named by STATE.md (S-2).

    Every token matching the path grammar that contains ``/`` or is a top-level
    file of the commit must be in the export set.
    """
    for number, line in enumerate(iter_lines(text), 1):
        for token in dict.fromkeys(_PATH_TOKEN.findall(line)):
            if ("/" in token or token in top_level) and token not in exported:
                yield "state-path", number


def check(repo, rev, dir_path=None, private_terms=None):
    entries = ls_tree(repo, rev)
    includes, excludes = parse_manifest(read_rev_file(repo, rev, MANIFEST_PATH))
    exemption_keys = parse_exemptions(read_rev_file(repo, rev, EXEMPTIONS_PATH))

    rows = []
    used_exemptions = set()
    exported = {}
    contents = {}
    display_cache = {}
    flagged = set()

    def flags(path):
        if path not in display_cache:
            secret = any(rx.search(path) for _, rx in CONTENT_RULES)
            private = bool(private_terms) and any(
                t in path.lower() for t in private_terms)
            shown = redact(path) if (secret or private) else path
            display_cache[path] = (shown, secret, private)
        return display_cache[path]

    def add(rule, path, line, raw_line=None):
        rows.append({
            "rule": rule,
            "display": flags(path)[0],
            "line": line,
            "raw_line": raw_line,
            "raw_path": path,
            "sort": path,
        })

    def flag_path(path):
        if path in flagged:
            return
        flagged.add(path)
        _, secret, private = flags(path)
        if secret:
            add("secret-path", path, 0)
        if private:
            add("private-path", path, 0)

    for path, mode, obj in entries:
        if not is_exported(path, includes, excludes):
            continue
        exported[path] = (mode, obj)
        flag_path(path)
        if mode == "160000":
            add("gitlink", path, 0)
            continue
        if mode not in ("100644", "100755"):
            add("symlink", path, 0)
            continue
        proc = _git(repo, "cat-file", "blob", obj)
        if proc.returncode != 0:
            add("unreadable", path, 0)
            continue
        blob = proc.stdout
        contents[path] = blob
        image = False
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            if not is_readme_image(path, blob):
                add("unreadable", path, 0)
                continue
            # An accepted image is still scanned for private terms on its raw
            # bytes, so a GIF comment or a PNG text chunk cannot leak one.
            image = True
            text = blob.decode("latin-1")
        for number, text_line in enumerate(iter_lines(text), 1):
            for rule, rx in (() if image else CONTENT_RULES):
                if rx.search(text_line):
                    add(rule, path, number, raw_line=text_line)
            if private_terms:
                folded = text_line.lower()
                if any(term in folded for term in private_terms):
                    add("private-term", path, number, raw_line=text_line)

    top_level = {entry for entry, _mode, _obj in entries if "/" not in entry}
    for path in live_markdown(exported):
        blob = contents.get(path)
        if blob is None:
            continue
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for rule, number in markdown_findings(path, text, exported):
            add(rule, path, number)
    if "STATE.md" in exported:
        blob = contents.get("STATE.md")
        if blob is not None:
            try:
                text = blob.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                for rule, number in state_path_findings(text, exported, top_level):
                    add(rule, "STATE.md", number)

    if dir_path is not None:
        if not os.path.isdir(dir_path):
            raise CheckError("--dir is not a directory")
        files, dirs = collect_disk(dir_path)
        expected_dirs = set()
        for path in exported:
            parts = path.split("/")
            for depth in range(1, len(parts)):
                expected_dirs.add("/".join(parts[:depth]))
        for path in sorted(set(files) - set(exported)):
            flag_path(path)
            add("dir-extra", path, 0)
        for path in sorted(set(dirs) - expected_dirs):
            flag_path(path)
            add("dir-extra", path, 0)
        for path in sorted(set(exported) - set(files)):
            add("dir-missing", path, 0)
        for path in sorted(set(exported) & set(files)):
            mode, _ = exported[path]
            full = files[path]
            info = os.lstat(full)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                add("dir-changed", path, 0)
                continue
            try:
                with open(full, "rb") as handle:
                    data = handle.read()
            except OSError:
                add("dir-changed", path, 0)
                continue
            want_exec = mode == "100755"
            have_exec = bool(info.st_mode & stat.S_IXUSR)
            if data != contents.get(path) or want_exec != have_exec:
                add("dir-changed", path, 0)

    kept = []
    for row in rows:
        if row["raw_line"] is not None:
            key = (row["raw_path"], row["rule"], line_digest(row["raw_line"]))
            if key in exemption_keys:
                used_exemptions.add(key)
                continue
        kept.append(row)

    stale_from = len(rows)
    for key in exemption_keys:
        if key not in used_exemptions:
            flag_path(key[0])
            add("stale-exemption", key[0], 0)
    kept.extend(rows[stale_from:])

    kept.sort(key=lambda row: (row["sort"], row["line"], row["rule"]))
    return kept


def render(rows):
    counts = {}
    for row in rows:
        counts[row["rule"]] = counts.get(row["rule"], 0) + 1
    parts = ["%s=%d" % (rule, counts[rule])
             for rule in REPORT_ORDER if counts.get(rule)]
    summary = "summary: %d findings" % len(rows)
    if parts:
        summary += " " + " ".join(parts)
    return counts, summary


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    parser = _ArgumentParser(
        prog="export_check",
        description="Content and manifest check for the public export.")
    parser.add_argument("--repo", default=None,
                        help="git repository (default: the cwd's toplevel)")
    parser.add_argument("--commit", default="HEAD",
                        help="revision to check (default: HEAD)")
    parser.add_argument("--dir", dest="dir_path", default=None,
                        help="exported tree on disk to compare against")
    parser.add_argument("--private-terms", dest="terms_path", default=None,
                        help="file of private terms (outside the repository)")
    args = parser.parse_args(argv)

    try:
        terms = None
        if args.terms_path is not None:
            try:
                with open(args.terms_path, "r", encoding="utf-8") as handle:
                    terms = parse_private_terms(handle.read())
            except (OSError, UnicodeDecodeError):
                raise CheckError("cannot read the private-terms file")
        repo = resolve_repo(args.repo)
        rev = resolve_rev(repo, args.commit)
        rows = check(repo, rev, args.dir_path, terms)
    except CheckError as exc:
        print("export_check: error: %s" % exc, file=sys.stderr)
        return 2
    except Exception:
        print("export_check: error: unexpected failure", file=sys.stderr)
        return 2

    for row in rows:
        print("%s\t%s\t%d"
              % (row["rule"], printable(row["display"]), row["line"]))
    if terms is None:
        print("private-term rule skipped")
    _, summary = render(rows)
    print(summary)

    if rows:
        return 1
    if terms is None:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
