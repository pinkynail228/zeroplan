"""O2a-mini: the start screen (`terminal_planner/tui/start.py`) and the way `cli.main` reaches it.

One smoke test per criterion of the task, over a scratch folder and an isolated HOME and Git config (never the
runner's own): C1 the look (mascot constant, word mark, version, card; no mascot below 60x24, one SVG screenshot),
C2 a folder without Git or a repo without a commit becomes a project with one empty commit, C3 «Another folder», C4 every
way out leaves Git alone; C5 lives in tests/test_terminal_planner.py (`ProjectChoiceTests`).

Worker interpretations (the reviewers never see the worker's summary):

- «at 60x24» is the smallest size that still shows the mascot («Below 60x24 no mascot»): width < 60 or height < 24
  hides it. Under 36 rows it stands beside the word mark so the card still fits 24 rows.
- The commit is made from the empty tree with plumbing (`commit-tree`, `update-ref`), not `git commit --allow-empty`:
  a repo without a commit may already have files staged, and `commit` would put them in the first commit («no file is
  added»). The new repo's branch is `main` unless the owner configured `init.defaultBranch`.
- «last commit» on the project card is the subject line of HEAD; «N files not in the commit» counts untracked and changed
  entries of `git status` ("1 file" / "N files").
- A relative path on «Another folder» is read from the folder the screen was opened for.
- The user is asked for name and email when `git config` yields no `user.name` or no `user.email`; both are written
  to the repo's local config.
- Two tests drive the whole start app (look and journey; other folder and exits); the rest call the Git steps.

O2b (the origin step), worker interpretations:

- «not a GitHub URL» is `setup.GITHUB_ORIGIN` not matching `git remote get-url origin` (an absent origin included);
  an origin with credentials matches it and is left to the readiness check, which never prints it.
- The prefilled `local/<folder name>` replaces characters outside `[A-Za-z0-9_.-]` in the folder name with `-`, so the
  suggestion is itself valid for a folder such as «project with spaces».
- The step is reached from every way a project opens (the «Open this project» row, «Continue» after create, and a
  ready folder typed on «Another folder»); «Add origin» and «Skip» are the card's two rows, ↑↓ move the mark
  while the field has focus and Enter does the marked row. Esc goes back one card like on any other card.
- The journey test covers the add path (invalid value, then the suggestion, `git remote get-url origin`); the
  other-folder test covers «Skip» and a GitHub origin that shows no step; `OriginTests` call `add_origin`
  (`add` and `set-url`, no fetch or push).
"""

import asyncio
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tui_support  # noqa: F401  (joins the offline wheelhouse to sys.path before the guarded imports)

try:
    from terminal_planner.tui import start
except ImportError:  # pragma: no cover - the bare import scan of tests.test_toolchain covers this path
    start = None

GIT_ENV = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL", "GIT_DIR",
           "GIT_WORK_TREE", "GIT_CONFIG_COUNT")


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True).stdout.strip()


def screen_text(app):
    return "\n".join(strip.text.rstrip() for strip in app.screen._compositor.render_strips())


@unittest.skipIf(start is None, "Textual недоступен")
class StartTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.config = self.root / "gitconfig"
        environ = patch.dict(os.environ, {"HOME": str(self.root / "home"), "GIT_CONFIG_GLOBAL": str(self.config),
                                          "GIT_CONFIG_NOSYSTEM": "1"})
        environ.start()
        self.addCleanup(environ.stop)
        for name in GIT_ENV:
            os.environ.pop(name, None)

    def folder(self, name="proj", files=()):
        path = self.root / name
        path.mkdir()
        for file in files:
            (path / file).write_text("x\n")
        return path

    def identify(self):
        self.config.write_text("[user]\n\tname = Global\n\temail = global@example.invalid\n")

    def repo(self, name="ready", origin="https://github.com/owner/ready.git"):
        """A repo with one commit `fixture` on `main`; `origin` None: no remote (the start screen asks for one)."""
        self.identify()
        path = self.folder(name, ["source.txt"])
        git(path, "init", "-q", "-b", "main")
        git(path, "add", "source.txt")
        git(path, "commit", "-qm", "fixture")
        if origin:
            git(path, "remote", "add", "origin", origin)
        return path

    def run_app(self, path, scenario, size=(120, 40)):
        """Open the start screen on `path`, run `scenario(app, pilot)`, return (app, the screen's result)."""
        app = start.StartApp(path)

        async def drive():
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                await scenario(app, pilot)
                await pilot.pause()
        asyncio.run(drive())
        return app, app.return_value

    def test_c1_c2_look_and_journey_from_an_empty_folder_to_the_open_project_and_the_asked_identity(self):
        folder = self.folder("folder-with-files", [f"file{n}.txt" for n in range(5)])
        seen = []
        shot = []

        async def scenario(app, pilot):
            seen.append(screen_text(app))
            shot.append(app.export_screenshot())
            self.assertFalse((folder / ".git").exists())
            await pilot.press("enter")  # «Create a project here»: Git has no identity yet, so it is asked first
            seen.append(screen_text(app))
            self.assertFalse((folder / ".git").exists(), "nothing is written before the identity card is answered")
            app.query_one("#name").value = "Ada Lovelace"
            await pilot.press("enter")
            app.query_one("#email").value = "ada@example.invalid"
            await pilot.press("enter")
            seen.append(screen_text(app))
            await pilot.press("enter")  # Continue: the folder has no GitHub origin, so one step more
            seen.append(screen_text(app))
            app.query_one("#origin").value = "not a name"
            await pilot.press("enter")
            seen.append(screen_text(app) + "|" + app.step[0])
            app.query_one("#origin").value = start.suggested_repository(folder)
            await pilot.press("enter")

        _, result = self.run_app(folder, scenario)
        self.assertTrue(start.MASCOT.startswith("      ⣠⠖⡺⣛⡶⣶⣤⣄⡀"), "the mascot is the ascii_logo.py braille 24 128 output")
        for line in start.MASCOT.splitlines() + start.WORDMARK.splitlines() + [start.__version__]:
            self.assertIn(line.strip(), seen[0])
        self.assertIn("<svg", shot[0])
        for size, mascot in (((80, 24), True), ((60, 24), True), ((59, 24), False), ((60, 23), False)):
            with self.subTest(size=size):
                shown = []

                async def look(app, pilot):
                    shown.append(screen_text(app))
                self.run_app(folder, look, size)
                self.assertEqual(start.MASCOT.splitlines()[0].strip() in shown[0], mascot)
                self.assertIn("Quit", shown[0])  # the card is there at every size
        self.assertIn("There is no Git project here", seen[0])
        self.assertIn("Create a project here (git init + first commit)", seen[0])
        self.assertIn("Who is the commit author?", seen[1])
        self.assertIn("main · Initial commit", seen[2])
        self.assertIn("5 files not in the commit", seen[2])
        self.assertIn("No GitHub origin", seen[3])
        self.assertIn("local/folder-with-files", seen[3])
        self.assertIn("OWNER/REPO", seen[4])  # an invalid value keeps the step with a note
        self.assertTrue(seen[4].endswith("|origin"))
        self.assertEqual(result, folder)
        self.assertEqual(git(folder, "remote", "get-url", "origin"), "https://github.com/local/folder-with-files.git")
        self.assertEqual(git(folder, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(git(folder, "log", "-1", "--format=%s|%an|%ae"), "Initial commit|Ada Lovelace|ada@example.invalid")
        self.assertEqual(git(folder, "config", "--local", "user.name"), "Ada Lovelace")
        self.assertFalse(self.config.exists(), "the global config is never written")

    def test_c2_create_adds_no_file_even_a_staged_one_and_keeps_the_branch_and_identity_rules(self):
        self.identify()
        folder = self.folder("repo-without-commit", ["staged.txt", "loose.txt", "other.txt"])
        git(folder, "init", "-q", "-b", "trunk")
        git(folder, "add", "staged.txt")
        before = start.inspect(folder)
        self.assertEqual((before.exists, before.root, before.ready), (True, folder, False))
        start.create_project(folder)  # Git has the identity: none is asked or written
        self.assertEqual(git(folder, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(git(folder, "ls-tree", "-r", "--name-only", "HEAD"), "", "the first commit holds no file")
        self.assertEqual(git(folder, "diff", "--cached", "--name-only"), "staged.txt")  # still staged, not committed
        self.assertEqual(start.unstaged_files(folder), 3)
        found = start.inspect(folder)
        self.assertEqual((found.ready, found.branch, found.commit), (True, "trunk", "Initial commit"))
        fresh = self.folder("fresh")
        start.create_project(fresh)
        self.assertEqual(start.inspect(fresh).branch, "main")
        self.assertEqual(git(fresh, "log", "-1", "--format=%an"), "Global")
        self.assertEqual(subprocess.run(["git", "-C", str(fresh), "config", "--local", "user.name"], capture_output=True).returncode, 1)

    def test_c2_inspect_tells_a_project_from_a_folder_without_git_or_a_commit(self):
        ready = self.repo()
        found = start.inspect(ready)
        self.assertEqual((found.ready, found.root, found.branch, found.commit), (True, ready, "main", "fixture"))
        self.assertEqual(start.inspect(ready / "nope").exists, False)
        plain = start.inspect(self.folder("plain"))
        self.assertEqual((plain.exists, plain.root, plain.ready), (True, None, False))
        self.assertEqual(start.identity_missing(ready), False)
        self.config.write_text("")
        self.assertEqual(start.identity_missing(ready), True)

    # C3, C4 ----------------------------------------------------------------------------------------------------------

    def test_c3_c4_other_folder_and_every_way_out_leaves_git_alone(self):
        ready = self.repo()
        empty = self.folder("empty")
        seen = {}

        async def other(app, pilot):
            await pilot.press("down", "enter")  # «Another folder»
            seen["card"] = screen_text(app)
            app.query_one("#path").value = str(self.root / "nope")
            await pilot.press("enter")
            seen["missing"] = screen_text(app)
            app.query_one("#path").value = str(empty)
            await pilot.press("enter")  # a folder without Git: the create card for it
            seen["not_ready"] = screen_text(app)
            await pilot.press("escape")  # back to the path card
            seen["back"] = app.step
            app.query_one("#path").value = str(ready)
            await pilot.press("enter")

        _, result = self.run_app(empty, other)
        self.assertIn("Another folder", seen["card"])
        self.assertIn("The folder does not exist", seen["missing"])
        self.assertIn("Create a project here", seen["not_ready"])
        self.assertIn(empty.name, seen["not_ready"])
        self.assertEqual(seen["back"], ("other",))
        self.assertEqual(result, ready)

        async def open_here(app, pilot):
            seen["ready"] = screen_text(app)
            await pilot.press("enter")
        _, result = self.run_app(ready, open_here)
        self.assertIn("ready · main · fixture", seen["ready"])
        self.assertIn("Open this project", seen["ready"])
        self.assertEqual(result, ready)  # a GitHub origin: no step

        bare = self.repo("bare", origin=None)

        async def skip(app, pilot):
            await pilot.press("enter")  # open: the origin step
            seen["step"] = app.step[0]
            await pilot.press("down", "enter")  # «Skip»
        _, result = self.run_app(bare, skip)
        self.assertEqual((seen["step"], result), ("origin", bare))
        self.assertEqual(git(bare, "remote"), "", "skipping writes nothing")

        for name, keys in (("escape", ("escape",)), ("ctrl+c", ("ctrl+c",)), ("ctrl+q", ("ctrl+q",)),
                           ("Quit", ("down", "down", "enter"))):
            with self.subTest(way=name):
                async def leave(app, pilot, keys=keys):
                    await pilot.press(*keys)
                app, result = self.run_app(empty, leave)
                self.assertIsNone(result)
                self.assertEqual(app.return_code, 0)
                self.assertFalse((empty / ".git").exists())

        async def leave_from_a_nested_card(app, pilot):
            await pilot.press("down", "enter")
            await pilot.press("ctrl+c")  # from the path input
        app, result = self.run_app(empty, leave_from_a_nested_card)
        self.assertIsNone(result)
        self.assertFalse((empty / ".git").exists())

    def test_o2c_an_existing_origin_is_kept_by_default_named_and_restorable_and_never_shown_with_userinfo(self):
        """O2c, worker interpretations: the origin card keeps the scheme and cuts only the userinfo of a URL that has
        one (P2b), in «Current origin» and in the restore command; the field keeps the `local/<folder>`
        suggestion, and Enter in the field does the marked row. A missing origin is covered by the journey test."""
        old = "https://gitlab.com/a/b.git"
        kept = self.repo("kept", origin=old)
        seen = {}

        async def skip(app, pilot):
            await pilot.press("enter")  # open: the origin step
            seen["card"] = screen_text(app)
            await pilot.press("enter")  # the first row
        _, result = self.run_app(kept, skip)
        self.assertEqual(result, kept)
        self.assertEqual(git(kept, "remote", "get-url", "origin"), old, "the first row leaves the remote untouched")
        self.assertIn("Current origin: " + old, seen["card"])
        self.assertIn("git remote set-url origin " + old, seen["card"])
        self.assertLess(seen["card"].index("Skip"), seen["card"].index("Replace origin"))
        self.assertNotIn("Add origin", seen["card"])

        async def replace(app, pilot):
            await pilot.press("enter")
            app.query_one("#origin").value = "a/b"
            await pilot.press("down", "enter")
        _, result = self.run_app(kept, replace)
        self.assertEqual((result, git(kept, "remote", "get-url", "origin")), (kept, "https://github.com/a/b.git"))

        private = "https://u" + ":t@gitlab.com/a/b.git"
        hidden = self.repo("hidden", origin=private)

        async def look(app, pilot):
            await pilot.press("enter")
            seen["hidden"] = screen_text(app)
        self.run_app(hidden, look)
        self.assertNotIn("u:t", seen["hidden"])
        self.assertIn("Current origin: " + old, seen["hidden"])
        self.assertIn("git remote set-url origin " + old, seen["hidden"])
        self.assertEqual(git(hidden, "remote", "get-url", "origin"), private)
        self.assertEqual(start.shown_url("git@gitlab.com:a/b.git"), "git@gitlab.com:a/b.git")

    def test_c1_add_origin_adds_or_replaces_and_refuses_an_invalid_name(self):
        bare = self.repo("bare", origin=None)
        self.assertTrue(start.needs_origin(bare))
        start.add_origin(bare, "local/bare")
        self.assertEqual(git(bare, "remote", "get-url", "origin"), "https://github.com/local/bare.git")
        self.assertFalse(start.needs_origin(bare))
        elsewhere = self.repo("elsewhere", origin="https://example.invalid/team/elsewhere.git")
        self.assertTrue(start.needs_origin(elsewhere))
        start.add_origin(elsewhere, "team/elsewhere")  # set-url, not add
        self.assertEqual(git(elsewhere, "remote", "get-url", "origin"), "https://github.com/team/elsewhere.git")
        for bad in ("", "one", "a/b/c", "a b/c", "-o/x y", "a/b;c"):
            with self.subTest(bad=bad), self.assertRaises(start.StartError):
                start.add_origin(bare, bad)
        self.assertEqual(git(bare, "remote", "get-url", "origin"), "https://github.com/local/bare.git")
        self.assertEqual(start.suggested_repository(self.root / "project with spaces"), "local/project-with-spaces")


if __name__ == "__main__":
    unittest.main()
