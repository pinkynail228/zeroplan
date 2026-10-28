"""A-5/A-V of R-6: the pure connection-metadata store check (`terminal_planner.connections`).

A fake `call` spy records argv, kwargs and env; state roots are temp dirs; no binary, network, adapter or port
8797 is touched. Every store-check case spawns exactly one `connection list` with timeout=30 under the engine's
own `ZEROSHOT_STATE_DIR`. The tests cover A-5's ready/missing/unknown cases (unknown standing for
`lane.connection_unknown`), A-V (no stdout/stderr text in `detail` or `repr`) and one named killing test per
mutation of the task.

Worker interpretations recorded here (silence/ambiguity in the task, decided as noted):
- Shape strictness: R-3 validates every summary, so one malformed summary makes the whole result `unknown`
  (never a partially trusted list); extra envelope and summary keys are ignored, as R-3 ignores other envelope
  keys and lists only the required summary keys.
- Check order: a nonzero exit is checked before parsing, so a nonzero exit with unparseable stdout is `exit`,
  not `decode` (R-5 gives `exit` to a nonzero exit and `decode` to a decoder failure).
- Non-str stdout maps to `decode`, the label R-5 groups with decoder failures.
- The `fields` argument is not validated here: the R-3 protocol says it is an iterable of str, and callers are
  trusted (no task rule asks this module to reject a bad argument).
"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from terminal_planner import connections


class FakeEngine:
    """A native-engine double for R-6: engine-like `executable` and `native_environment`, a scripted `call` spy.

    `native_environment` returns only the state-dir contract (never the host `os.environ`), so the env assertions
    are deterministic and a mutant that reaches for `os.environ` cannot satisfy them by accident.
    """

    def __init__(self, root, response, returncode=0, stderr=""):
        self.executable = "/opt/zeroshot/bin/zeroshot"
        self.state_root = Path(root)
        self.response = response
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def native_environment(self):
        return {"ZEROSHOT_STATE_DIR": str(self.state_root / "runs"),
                "ZEROSHOT_CONFIG_DIR": str(self.state_root / "config")}

    def call(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return subprocess.CompletedProcess(argv, self.returncode, self.response, self.stderr)


class FaultyEngine:
    """An engine whose pre-invocation evaluation fails; the invocation itself is never reached.

    `where` selects which evaluation raises before `connection_ready` guards the invocation: `executable` (the
    argv build), `environment` (`native_environment()`) or `call` (looking up the `call` attribute). Only a
    failure *inside* the resolved callable counts as a call failure.
    """

    def __init__(self, root, error, where):
        self._executable = "/opt/zeroshot/bin/zeroshot"
        self.error = error
        self.where = where
        self.calls = []
        self.state_root = Path(root)

    @property
    def executable(self):
        if self.where == "executable":
            raise self.error
        return self._executable

    def native_environment(self):
        if self.where == "environment":
            raise self.error
        return {"ZEROSHOT_STATE_DIR": str(self.state_root / "runs")}

    @property
    def call(self):
        if self.where == "call":
            raise self.error

        def invoke(argv, **kwargs):
            self.calls.append((argv, kwargs))
            raise AssertionError("call must not be reached")

        return invoke


class ConnectionReadyTests(unittest.TestCase):
    KEY = "gateway"
    FIELDS = ("GATEWAY_BASE_URL", "GATEWAY_API_KEY")

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="zs-con-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def engine(self, response, returncode=0, stderr=""):
        return FakeEngine(self.root, response, returncode=returncode, stderr=stderr)

    def summary(self, key=None, scope="user", kind="env", fields=None):
        return {"key": self.KEY if key is None else key, "scope": scope, "kind": kind,
                "fields": list(self.FIELDS if fields is None else fields)}

    def raw(self, **overrides):
        """A summary dict with any field overridden verbatim (no `list()` coercion, for malformed shapes)."""
        summary = self.summary()
        summary.update(overrides)
        return summary

    def envelope(self, summaries, **extra):
        document = {"connections": summaries}
        document.update(extra)
        return json.dumps(document)

    def check(self, engine, state, detail):
        """Run one case and enforce A-5's call contract: exactly one `connection list`, timeout 30, engine env."""
        result = connections.connection_ready(engine, self.KEY, self.FIELDS)
        self.assertEqual(result, (state, detail))
        self.assertEqual(len(engine.calls), 1, "each case must spawn exactly one connection list")
        argv, kwargs = engine.calls[0]
        self.assertEqual(argv, [engine.executable, "connection", "list"])
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])
        self.assertTrue(kwargs["start_new_session"])
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["timeout"], 30)
        self.assertEqual(kwargs["env"]["ZEROSHOT_STATE_DIR"], str(engine.state_root / "runs"))
        return result

    # Ready / missing (R-4) -------------------------------------------------------------------------------------

    def test_ready_with_exact_fields(self):
        self.check(self.engine(self.envelope([self.summary()])), "ready", "")

    def test_ready_with_extra_fields(self):
        listed = self.summary(fields=("GATEWAY_BASE_URL", "GATEWAY_API_KEY", "EXTRA"))
        self.check(self.engine(self.envelope([listed])), "ready", "")

    def test_ready_when_only_one_of_several_summaries_matches(self):
        summaries = [self.summary(key="other"), self.summary()]
        self.check(self.engine(self.envelope(summaries)), "ready", "")

    def test_missing_key_is_missing(self):
        self.check(self.engine(self.envelope([self.summary(key="other")])), "missing", "missing")

    def test_empty_store_is_missing(self):
        self.check(self.engine(self.envelope([])), "missing", "missing")

    def test_missing_field_is_missing(self):
        listed = self.summary(fields=("GATEWAY_BASE_URL",))
        self.check(self.engine(self.envelope([listed])), "missing", "missing")

    def test_org_scope_is_missing(self):
        """Kills the `accept org scope` mutation: only a `user`-scope summary can make the check ready."""
        self.check(self.engine(self.envelope([self.summary(scope="org")])), "missing", "missing")

    def test_shared_field_is_not_ready(self):
        """Kills the `intersection instead of subset` mutation: a single shared field must not read as ready."""
        listed = self.summary(fields=("GATEWAY_BASE_URL", "UNRELATED"))
        self.check(self.engine(self.envelope([listed])), "missing", "missing")

    # Unknown: shape (R-3) --------------------------------------------------------------------------------------

    def test_non_object_envelope_is_unknown_schema(self):
        self.check(self.engine(json.dumps([self.summary()])), "unknown", "schema")

    def test_missing_connections_is_unknown_schema(self):
        self.check(self.engine(json.dumps({"connections_typo": []})), "unknown", "schema")

    def test_non_list_connections_is_unknown_schema(self):
        self.check(self.engine(json.dumps({"connections": "gateway"})), "unknown", "schema")

    def test_non_object_summary_is_unknown_schema(self):
        self.check(self.engine(self.envelope(["gateway"])), "unknown", "schema")

    def test_wrong_type_key_is_unknown_schema(self):
        self.check(self.engine(self.envelope([self.raw(key=7)])), "unknown", "schema")

    def test_wrong_type_scope_is_unknown_schema(self):
        self.check(self.engine(self.envelope([self.raw(scope=None)])), "unknown", "schema")

    def test_wrong_type_kind_is_unknown_schema(self):
        self.check(self.engine(self.envelope([self.raw(kind=1)])), "unknown", "schema")

    def test_wrong_type_fields_is_unknown_schema(self):
        self.check(self.engine(self.envelope([self.raw(fields="GATEWAY_BASE_URL")])), "unknown", "schema")

    def test_non_str_field_element_is_unknown_schema(self):
        self.check(self.engine(self.envelope([self.raw(fields=("GATEWAY_BASE_URL", 7))])), "unknown", "schema")

    def test_malformed_summary_is_unknown_not_raised(self):
        """Kills the `let a malformed summary raise` mutation: a bad summary is `unknown`, never an exception.

        Shape strictness (see the module docstring): a single malformed summary fails the whole result, and a
        malformed summary never replaces the closed failure set with an uncaught exception.
        """
        malformed = [self.raw(key=7), self.raw(scope=7), self.raw(kind=7),
                     self.raw(fields=[7]), self.raw(fields=7), self.raw(fields="gateway"), "not-an-object"]
        for summary in malformed:
            with self.subTest(summary=summary):
                self.check(self.engine(self.envelope([summary])), "unknown", "schema")

    # Unknown: exit, timeout, io, decode (R-3/R-5) --------------------------------------------------------------

    def test_nonzero_exit_is_unknown_exit(self):
        self.check(self.engine(self.envelope([self.summary()]), returncode=3), "unknown", "exit")

    def test_timeout_is_unknown_timeout(self):
        error = subprocess.TimeoutExpired(["/opt/zeroshot/bin/zeroshot", "connection", "list"], 30)
        self.check(self.engine(error), "unknown", "timeout")

    def test_oserror_is_unknown_io(self):
        self.check(self.engine(OSError("executable missing")), "unknown", "io")

    def test_non_json_is_unknown_decode(self):
        self.check(self.engine("not json at all"), "unknown", "decode")

    def test_non_str_stdout_is_unknown_decode(self):
        self.check(self.engine(b'{"connections": []}'), "unknown", "decode")

    def test_deeply_nested_stdout_is_unknown_decode(self):
        self.check(self.engine("[" * 3000), "unknown", "decode")

    def test_other_exceptions_are_not_suppressed(self):
        """No bare except: only the R-3 failures are mapped; anything else from `call` propagates."""
        with self.assertRaises(ValueError):
            connections.connection_ready(self.engine(ValueError("boom")), self.KEY, self.FIELDS)
        with self.assertRaises(RuntimeError):
            connections.connection_ready(self.engine(RuntimeError("boom")), self.KEY, self.FIELDS)

    def test_engine_argument_errors_propagate_not_unknown(self):
        """Repair regression (class: pre-invocation evaluation of the passed object must not be suppressed).

        R-3 maps exactly one OSError—the one raised *inside* `call`—to `unknown`/`io`; everything the engine
        exposes is resolved before the guarded invocation: `executable` and `native_environment()` (argument
        build) and the `call` attribute itself. Any exception from those (OSError included) propagates with zero
        invocations. Domain checked: {`executable`, `native_environment`, `call` lookup} x {OSError,
        RuntimeError}; the reviewers' reproductions were the OSError-from-`native_environment` and
        OSError-from-`call`-lookup cells.
        """
        for where in ("executable", "environment", "call"):
            for error in (OSError("environment failure"), RuntimeError("boom")):
                with self.subTest(where=where, error=type(error).__name__):
                    engine = FaultyEngine(self.root, error, where)
                    with self.assertRaises(type(error)):
                        connections.connection_ready(engine, self.KEY, self.FIELDS)
                    self.assertEqual(engine.calls, [], "no call may run when evaluation fails")

    # A-5 call contract (named for the timeout mutation) --------------------------------------------------------

    def test_timeout_is_thirty_seconds(self):
        """Kills the `drop timeout=30` mutation."""
        engine = self.engine(self.envelope([self.summary()]))
        connections.connection_ready(engine, self.KEY, self.FIELDS)
        self.assertEqual(engine.calls[0][1]["timeout"], 30)

    def test_call_uses_engine_native_environment(self):
        """Kills the `os.environ instead of engine.native_environment()` mutation.

        The double's `native_environment` carries the state dirs and nothing the host env has, so only a call
        that forwards `engine.native_environment()` can carry `ZEROSHOT_STATE_DIR` for this engine.
        """
        engine = self.engine(self.envelope([self.summary()]))
        connections.connection_ready(engine, self.KEY, self.FIELDS)
        self.assertEqual(engine.calls[0][1]["env"], engine.native_environment())

    # A-V: no values --------------------------------------------------------------------------------------------

    def test_detail_never_carries_stdout_or_stderr(self):
        """Kills the `put stderr text into detail` mutation and covers A-V for every outcome.

        A sentinel placed in stdout (payload, extra envelope key or raw text), stderr or both never appears in
        `detail` or the `repr` of the result: the detail is one closed label from R-5.
        """
        sentinel = "SENTINEL-c0ffee-not-a-value"
        cases = [
            (self.envelope([self.summary()], note=sentinel), 0, sentinel),          # ready
            (self.envelope([self.summary(key="other")]), 0, sentinel),              # missing
            (self.envelope([self.raw(key=7)]), 0, sentinel),                        # schema
            ("%s is not json" % sentinel, 0, sentinel),                             # decode
            (self.envelope([self.summary()]), 4, sentinel),                         # exit
        ]
        for response, returncode, stderr in cases:
            with self.subTest(returncode=returncode, response=response[:20]):
                engine = self.engine(response, returncode=returncode, stderr=stderr)
                result = connections.connection_ready(engine, self.KEY, self.FIELDS)
                self.assertNotIn(sentinel, result.detail)
                self.assertNotIn(sentinel, repr(result))


if __name__ == "__main__":
    unittest.main()
