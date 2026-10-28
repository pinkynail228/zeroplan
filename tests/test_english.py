"""0.8.0 ships an English-only interface: no Cyrillic str constant is left in the product code.

Walks the AST of `terminal_planner/**/*.py` and `install.py` (docstrings included; comments are not constants) and
names file:line of every Cyrillic constant outside the allowed data: the ru/zh values of `strings.CATALOG` and
`strings.DISPLAY_NAMES`, any assignment to a `LEGACY_*` name (0.7.x rows and prompts stay readable) and
`setup.YES_ANSWERS` (the Russian "yes" stays accepted input). `install.sh` is checked by line.
Interpretation: Cyrillic is U+0400-U+052F; the exemption covers every constant inside the assigned value.
"""
import ast
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CYRILLIC = re.compile("[Ѐ-ԯ]")


def constants(node):
    return [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def exempt(tree, filename):
    ok = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
            name = target.id if isinstance(target, ast.Name) else ""
            if name.startswith("LEGACY_") or name == "YES_ANSWERS":
                ok.update(id(c) for c in constants(node.value))
            elif name in ("CATALOG", "DISPLAY_NAMES") and filename == "strings.py" and isinstance(node.value, ast.Dict):
                tables = [node.value] + [v for v in node.value.values if isinstance(v, ast.Dict)]
                for table in tables:
                    for key, value in zip(table.keys, table.values):
                        if isinstance(key, ast.Constant) and key.value in ("ru", "zh"):
                            ok.update(id(c) for c in constants(value))
    return ok


def cyrillic(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    ok = exempt(tree, path.name)
    return ["%s:%d" % (path.name, c.lineno) for c in constants(tree) if id(c) not in ok and CYRILLIC.search(c.value)]


class EnglishOnlyTests(unittest.TestCase):
    def test_c1_product_code_has_no_cyrillic_outside_the_allowed_data(self):
        found = [hit for path in [*sorted((ROOT / "terminal_planner").rglob("*.py")), ROOT / "install.py"]
                 for hit in cyrillic(path)]
        self.assertEqual(found, [])
        lines = (ROOT / "install.sh").read_text(encoding="utf-8").splitlines()
        self.assertEqual([n for n, line in enumerate(lines, 1) if CYRILLIC.search(line)], [])

    def test_c1_an_injected_literal_fails_with_its_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = pathlib.Path(tmp) / "cli.py"
            module.write_text('LEGACY_X = "старое"\nYES_ANSWERS = {"да"}\nprint("привет")\n', encoding="utf-8")
            self.assertEqual(cyrillic(module), ["cli.py:3"])


if __name__ == "__main__":
    unittest.main()
