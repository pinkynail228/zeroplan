"""U3: the read-only canvas views (`terminal_planner.tui.viewer`).

`resolve` returns a file under the project root and refuses everything else with a `ViewError` carrying a catalog
id and its format values; `file_view` lexes by suffix with line numbers and word wrap, cuts a file over `max_bytes`
and refuses non-UTF-8 text; `diff_view` colours a unified diff and shows a dim line when there is none. Each
renderable is checked by rendering it to plain text with a `rich.console.Console` (width 80, no colour) and reading
the lines (A5).

Interpretations recorded here, because the run's worker summary never reaches the reviewers:

- `note.view_empty` carries no format values (u2's frozen list gives it no `{name}`); the other three path ids
  carry `{"name": name}` — the name exactly as `resolve` was given it.
- The `canvas.view_cut` values `shown` and `total` are whole kilobytes, rounded up (`_kb`); the lab's file view has
  no such line, so the task's "KB" is read as "the values are in KB".
- `file_view` returns the bare `Syntax` when nothing is cut and a `rich.console.Group` (the `Syntax` plus the dim
  cut line) when the file is over `max_bytes`; `diff_view` returns the `Syntax`, or a dim `rich.text.Text` when the
  diff is empty. All are renderables, as the task asks.
- `words` is a callable parameter whose default is the module's built-in Russian wording, so the integration run
  (i5) can pass the string catalog's `text` instead.
- The functions are unannotated because the package carries no type hints anywhere; A1's `resolve(root: Path,
  name: str) -> Path` is read as the interface (`root` and `name` in, the resolved `Path` out).

The source-hygiene scan (`tests.test_toolchain`) imports every test module with neither Textual nor Rich
importable, so Rich — and `viewer`, which draws with it — is imported only when it is there; the render tests are
then declared and skipped, never hidden (unittest discovery must see them, and the declared count must not depend
on the dependency being importable)."""

import ast
import io
from pathlib import Path
import tempfile
import unittest

try:
    from rich.console import Console
    from terminal_planner.tui import viewer
except ImportError:  # pragma: no cover - covered by the bare import scan of tests.test_toolchain
    Console = viewer = None
HAVE_RICH = viewer is not None
RICH_REASON = "Rich недоступен: нужен ZPLAN_TEST_WHEELHOUSE с wheels rich"

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "terminal_planner" / "tui" / "viewer.py"


def rendered(renderable):
    """The renderable as plain lines: a `rich.console.Console`, width 80, no colour (A5)."""
    console = Console(width=80, no_color=True, record=True, file=io.StringIO())
    console.print(renderable)
    return console.export_text().splitlines()


def kb(size):
    """`size` bytes as whole kilobytes, rounded up — what `canvas.view_cut` receives."""
    return -(-size // 1024)


class SourceTests(unittest.TestCase):
    """A4: the module reads only — no writes, no subprocess, no network."""

    def test_a4_the_module_reads_only_and_imports_no_subprocess_socket_or_shutil(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(imported & {"subprocess", "socket", "shutil"}, set())
        self.assertTrue(imported <= {"pathlib", "rich"}, imported)

        calls = [node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                 for node in ast.walk(tree) if isinstance(node, ast.Call)]
        self.assertEqual(set(calls) & {"write", "write_text", "write_bytes", "unlink", "mkdir", "rmdir", "rename",
                                       "replace", "touch", "chmod", "symlink_to", "system", "popen", "run",
                                       "check_output", "urlopen"}, set())
        self.assertIn("read_bytes", calls)  # the one file access is a read
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                mode = node.args[1] if len(node.args) > 1 else next(
                    (k.value for k in node.keywords if k.arg == "mode"), None)
                self.assertIn(mode.value if mode is not None else "r", ("r", "rb"))


@unittest.skipUnless(HAVE_RICH, RICH_REASON)
class ResolveTests(unittest.TestCase):
    def test_a1_resolve_returns_the_file_and_each_refusal_carries_its_catalog_id_and_values(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / "project"
            (root / "notes").mkdir(parents=True)
            (root / "notes" / "a.md").write_text("привет\n", encoding="utf-8")
            (root / "dir").mkdir()
            outside = base / "outside.txt"
            outside.write_text("x\n", encoding="utf-8")
            (root / "link").symlink_to(outside)

            self.assertEqual(viewer.resolve(root, "notes/a.md"), (root / "notes" / "a.md").resolve())
            for name, id, values in (
                ("", "note.view_empty", {}),
                (str(outside), "note.view_outside", {"name": str(outside)}),
                ("link", "note.view_outside", {"name": "link"}),
                ("../outside.txt", "note.view_outside", {"name": "../outside.txt"}),
                ("nothing.txt", "note.view_missing", {"name": "nothing.txt"}),
                ("dir", "note.view_directory", {"name": "dir"}),
            ):
                with self.subTest(name):
                    with self.assertRaises(viewer.ViewError) as caught:
                        viewer.resolve(root, name)
                    self.assertEqual(caught.exception.id, id)
                    self.assertEqual(caught.exception.values, values)


@unittest.skipUnless(HAVE_RICH, RICH_REASON)
class FileViewTests(unittest.TestCase):
    def test_a2_file_view_lexes_by_suffix_numbers_lines_and_cuts_a_big_file_with_a_dim_line(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for suffix, lexer in ((".py", "python"), (".md", "markdown"), (".json", "json"), (".toml", "toml"),
                                  (".yaml", "yaml"), (".yml", "yaml"), (".sh", "bash"), (".txt", "text"),
                                  (".rs", "text")):
                with self.subTest(suffix):
                    path = root / ("sample" + suffix)
                    path.write_text("alpha = 1\n", encoding="utf-8")
                    view = viewer.file_view(path)
                    self.assertIn(lexer, view.lexer.aliases)
                    lines = rendered(view)
                    self.assertTrue(lines[0].startswith("  1 "), lines[:1])  # line numbers are on

            # A file over max_bytes shows its head only and closes with the dim cut line.
            content = ("abcdef" * 10 + "\n") * 2000 + "THE-END-MARKER\n"
            big = root / "big.py"
            big.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            seen = []

            def capture(id, **values):
                seen.append((id, values))
                return "cut"

            view = viewer.file_view(big, max_bytes=100_000, words=capture)
            lines = rendered(view)
            self.assertEqual(seen, [("canvas.view_cut", {"shown": kb(100_000), "total": kb(size)})])
            self.assertEqual(lines[-1], "cut")
            self.assertEqual(str(view.renderables[-1].style), "dim")
            self.assertIn("abcdef", lines[0])
            self.assertNotIn("THE-END-MARKER", "\n".join(lines))

            default = rendered(viewer.file_view(big, max_bytes=100_000))[-1]
            self.assertIn(str(kb(100_000)), default)  # the built-in wording names what is shown...
            self.assertIn(str(kb(size)), default)     # ...and the whole size

            # A cap splitting a multi-byte character drops only the partial one; the rest is still shown.
            cut = root / "cut.md"
            cut.write_text("я" * 10, encoding="utf-8")
            self.assertIn("яя", "\n".join(rendered(viewer.file_view(cut, max_bytes=5))))

            # A file that is not UTF-8 text is refused (also when a binary head is cut by the cap).
            for name, data, limit in (("blob.bin", b"\xff\xfe\x00\x01", viewer.MAX_BYTES),
                                      ("head.bin", b"\xff" * 50, 10)):
                with self.subTest(name):
                    blob = root / name
                    blob.write_bytes(data)
                    with self.assertRaises(viewer.ViewError) as caught:
                        viewer.file_view(blob, max_bytes=limit)
                    self.assertEqual(caught.exception.id, "note.view_binary")
                    self.assertEqual(caught.exception.values, {"name": name})


@unittest.skipUnless(HAVE_RICH, RICH_REASON)
class FileViewBinaryRegressionTests(unittest.TestCase):
    """Regression (A2): the whole file must be UTF-8 text, not only the head the cap shows.

    Interpretation recorded for the reviewers: A2 says "a file that is not UTF-8 text raises `note.view_binary`"
    without limiting that to the displayed prefix, so `file_view` validates every byte of the file and only then
    trims the shown head at a valid character boundary. An invalid byte past `max_bytes` — or a truncated multi-byte
    character straddling the cap — is therefore refused instead of rendered.
    """

    def test_a2_a_bad_byte_beyond_or_across_the_cap_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = {
                "beyond.bin": b"a" * 200_000 + b"\xff",
                "across.bin": b"a" * 199_999 + b"\xc3\xff",
                "straddle.bin": b"a" * 199_999 + b"\xc3X",
            }
            for name, data in cases.items():
                with self.subTest(name):
                    path = root / name
                    path.write_bytes(data)
                    with self.assertRaises(viewer.ViewError) as caught:
                        viewer.file_view(path, max_bytes=200_000)
                    self.assertEqual(caught.exception.id, "note.view_binary")
                    self.assertEqual(caught.exception.values, {"name": name})

            # A valid cut still drops only the split character and shows the rest of the head.
            ok = root / "ok.md"
            ok.write_bytes(("я" * 100_000 + "ХВОСТ").encode("utf-8"))
            lines = rendered(viewer.file_view(ok, max_bytes=5))
            self.assertIn("яя", "\n".join(lines))


@unittest.skipUnless(HAVE_RICH, RICH_REASON)
class DiffViewTests(unittest.TestCase):
    DIFF = ("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n")

    def test_a3_diff_view_colours_by_the_diff_lexer_and_shows_a_dim_line_when_empty(self):
        view = viewer.diff_view(self.DIFF)
        self.assertEqual(view.lexer.name, "Diff")
        lines = rendered(view)
        self.assertIn("--- a/x", lines)
        self.assertIn("+new", lines)

        empty = viewer.diff_view("")
        self.assertEqual(str(empty.style), "dim")
        self.assertEqual(rendered(empty), [viewer.words("canvas.diff_empty")])
        self.assertEqual(rendered(viewer.diff_view("", words=lambda id, **values: "нет")), ["нет"])


if __name__ == "__main__":
    unittest.main()
