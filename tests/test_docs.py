"""Live docs render as intended Markdown: a heading, a list, a table or a code block never starts glued to the
paragraph line above it (CommonMark would show the list or table as plain text of that paragraph)."""

from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parents[1]
LIVE = ("README.md", "docs/USER_FLOW.md", "docs/INSTALLATION.md", "docs/UPGRADE.md", "docs/REFERENCE.md", "docs/ARCHITECTURE.md")
LIST = re.compile(r"\s*(?:[-*+] |\d+[.)] )")
TABLE = re.compile(r"\s*\|")
LINE_UI = "\n# Line UI\n"
# What the full-screen shell no longer has: a bracketed letter (`[g]`), a backticked single letter as a key, the keys
# `Ctrl+G`, `Ctrl+S`, `Ctrl+R` and `F1`, and the goal form.
LETTER_KEY = re.compile(r"\[[A-Za-z?]\]|`[A-Za-z?]`|Ctrl\+[GSR]\b|\bF1\b|goal form", re.IGNORECASE)


def glued(text):
    """(line number, line) of every block start that directly follows a paragraph line."""
    lines, found, fence = text.split("\n"), [], False
    for number, line in enumerate(lines):
        if line.startswith("```"):
            if not fence and number and lines[number - 1].strip() and not lines[number - 1].startswith("#"):
                found.append((number + 1, line))
            fence = not fence
            continue
        if fence or not number or not lines[number - 1].strip():
            continue
        before = lines[number - 1]
        if before.startswith("<!--"):
            continue  # a one-line HTML comment is a complete block of its own
        if LIST.match(before) or TABLE.match(before) or before.startswith(("#", "```")) or before.startswith(" "):
            if before.startswith("#") and line.strip():
                found.append((number + 1, line))  # text right under a heading
            continue
        if LIST.match(line) or TABLE.match(line) or line.startswith("#"):
            found.append((number + 1, line))
    return found


def full_screen_part(text):
    """The text before the line UI's heading: the part of USER_FLOW that describes the full-screen shell."""
    head, found, _ = text.partition(LINE_UI)
    assert found, "docs/USER_FLOW.md lost its line UI heading"
    return head


def letter_keys(text):
    """Every (line number, match) in `text` that names a letter key or a key the full-screen shell no longer has."""
    return [(number, found.group(0)) for number, line in enumerate(text.split("\n"), 1)
            for found in LETTER_KEY.finditer(line)]


class InstallationLoginDecisionTests(unittest.TestCase):
    """A4: docs/INSTALLATION.md states the login decision in two sentences of one bullet."""

    def test_installation_states_zplans_own_login_and_why_it_is_not_shared(self):
        text = " ".join((REPO / "docs/INSTALLATION.md").read_text(encoding="utf-8").split())
        self.assertIn("zplan has its own login in its own Codex home; it never copies or links `~/.codex` credentials, "
                      "because a shared refresh token can log out the other copy.", text)


class DocsMarkdownTests(unittest.TestCase):
    def test_live_docs_have_no_list_table_heading_or_fence_glued_to_a_paragraph(self):
        for name in LIVE:
            with self.subTest(name):
                self.assertEqual(glued((REPO / name).read_text(encoding="utf-8")), [])

    def test_the_check_sees_a_glued_list(self):
        self.assertEqual(glued("Required tools:\n- git\n- node\n"), [(2, "- git")])
        self.assertEqual(glued("Required tools:\n\n- git\n- node\n"), [])
        self.assertEqual(glued("## Tools\ntext\n"), [(2, "text")])
        self.assertEqual(glued("Run:\n```sh\nx\n```\n"), [(2, "```sh")])


class FullScreenDocsTests(unittest.TestCase):
    """K1e C5: the full-screen part of USER_FLOW describes slash commands and buttons, never a letter key.

    Interpretation: "the full-screen part" is everything before the line UI's heading, because the line UI keeps its
    letters; "a backticked single letter as a key" is a code span holding one ASCII letter or `?`."""

    def test_the_full_screen_part_names_no_letter_key_and_no_removed_key(self):
        text = (REPO / "docs/USER_FLOW.md").read_text(encoding="utf-8")
        self.assertEqual(letter_keys(full_screen_part(text)), [])
        self.assertIn("[g]", text.partition(LINE_UI)[2])  # the line UI part keeps its letters

    def test_the_check_sees_each_removed_key_form(self):
        for line in ("| main | `p` | plan |", "start with [g] now", "press Ctrl+G", "`F1` helps", "Ctrl+S opens it",
                     "the goal form opens", "Goal Form"):
            with self.subTest(line):
                self.assertTrue(letter_keys(line), line)
        for line in ("| main | `Tab` | focus |", "type `/run`, then `Enter`", "[INSTALLATION.md](INSTALLATION.md)"):
            with self.subTest(line):
                self.assertEqual(letter_keys(line), [])
