"""Acceptance for a1 S1: the preflight probe uses the flags an unattended worker and reviewer depend on."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import slice_run as sr
from slice_run_test import Base


class PreflightProbe(Base):
    def test_probe_uses_the_review_flags(self):
        self.contract()
        self.steps({"verdict": "accept"})
        sr.main(["preflight", str(self.dir)])
        argv = self.calls()[0]["argv"]
        for flag in ("--permission-mode", "--permission-prompts", "--json-schema"):
            self.assertIn(flag, argv, f"preflight probe lacks {flag}")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(argv[argv.index("--permission-prompts") + 1], "none")
        self.assertEqual(json.loads(argv[argv.index("--json-schema") + 1]), sr.REVIEW_SCHEMA)


if __name__ == "__main__":
    unittest.main()
