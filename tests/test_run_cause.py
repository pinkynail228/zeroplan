"""0.5 S4: a failed milestone run says why the provider failed (G-1..G-3, A-1..A-6).

G-1 lives in `terminal_planner.engine` (the record grammars, the classifier and the evidence read of the retained
`zeroshot logs` lines), G-2 in `terminal_planner.engine`/`runs`/`delivery` (the reset predicate, the store and the
two surfaces) and G-3 in `terminal_planner.live` (the bounded reader). R-1's planner extraction and rendering are
unchanged and live in `terminal_planner.engine`/`planning` (the end-to-end planner journeys are in tests/test_ux.py).

Interpretations recorded here, as the worker's summary never reaches a reviewer:

* G-1's execution id ("a nonempty string; other non-null values are skipped") is read as three cases: `execution`
  absent or null is the run-wide record and is ignored (row 3 of the disposition table); a nonempty string is the
  execution id; any other non-null value -- a number, an object, an empty string -- makes the line *skipped*, never
  a record of any execution (`test_a_non_string_execution_id_is_skipped`, `test_an_empty_execution_id_is_skipped`).
* G-1's level is compared exactly: only the literal `error` is an error record, and info, debug, system and model
  output are ignored there and then (`test_only_the_error_level_is_a_record`).
* G-1's deduplication and its conflict rule cover the error records that name an execution -- exactly the records of
  the disposition table. A non-error record is "ignored: never evidence, never decisive, never changes the result",
  so it cannot make the result unknown either; the run-wide record is ignored for the same reason
  (`test_identical_duplicate_records_are_deduplicated`, `test_conflicting_records_sharing_a_cursor_are_unknown`,
  `test_an_info_duplicate_does_not_conflict`).
* G-1's "identical" is the whole record, every durable field of the parsed line, not the execution and the message
  alone: a pair that shares a cursor but differs in `record.target`, in the timestamp, in the cursor's own spelling
  or in any other field is a conflict and leaves the result unknown, while the same payload in another key order is
  still one duplicate (`test_records_that_differ_beyond_their_message_are_not_identical` and, through persistence,
  `test_records_that_share_a_cursor_and_differ_in_their_target_are_unknown`,
  `test_records_that_share_a_cursor_and_differ_in_their_timestamp_are_unknown`). The reviewers rejected the
  narrower identity of execution and message, so the payload, not its summary, decides.
* G-1's native envelope level is the literal `error` in the planner path too: `fatal`, `err`, `ERROR` and every
  other spelling are not the engine's error level, so an envelope that carries one is not evidence on stdout or on
  stderr, while the flat legacy formats keep their own error markers
  (`PlannerCauseTests.test_a_native_envelope_with_a_non_error_level_is_not_read_by_the_planner`).
* G-1 rule 5's "winning message" is the highest-cursor detail *among those matching the winning class*, so the
  class and the reset of G-2 always come from the same limit detail
  (`test_the_reset_comes_from_the_highest_limit_detail`).
* G-1's PROVIDER cause requires the engine's own capsule label: a cause that *opens* with the bare
  `<Provider> provider failure: <detail>` never fullmatches it, so it is unknown even though the text is provider
  shaped -- the label is where the supervisor writes that diagnostic, and the retry's bare diagnostic reaches the
  read as a DIAGNOSTIC record instead (`test_a_cause_without_the_engine_label_is_unknown`).
* G-1's `reason` decides before the cause, as the ordering of its selection rules says: `: authentication required`
  is auth and any other reason the engine can write (policy denied, interactive input required, a contract
  mismatch) is unknown, whatever the same completion also carries (`test_the_engine_reasons_decide_before_the_cause`).
* A-1's flat planner formats are untouched by G-1: `error_lines` still returns the flat error shapes, and the
  planner's own families and wording are unchanged (`CompatibilityTests.test_flat_error_lines_still_classify`,
  `PlannerCauseTests`).
* G-2's reset is read after the *last* `resets ` of the winning message and cut at the first `;`, `.`, `<`, CR or
  LF, outer spaces stripped; nothing is scrubbed or otherwise transformed afterwards, and one predicate (R-4's time
  language, at most 96 characters) is applied at extraction, at persistence, at store validation and at both
  surfaces (`test_the_reset_is_the_text_after_the_last_resets`, `test_only_the_reset_language_passes`,
  `test_the_reset_of_the_winning_limit_detail_is_stored`, `test_the_store_rejects_a_forged_cause_and_a_bad_reset`,
  `test_an_unusable_reset_reaches_neither_surface`).
* G-2's stored reset is a present, accepted *string*: the store refuses a record whose `reset` key is present but
  holds a value the predicate does not return -- a null, a number, an empty string -- beside its limit cause
  (`test_a_null_reset_beside_a_limit_cause_is_refused`, `test_the_store_rejects_a_forged_cause_and_a_bad_reset`).
* G-2's boundaries are exactly the language's: a grammar-valid value of 95 or 96 characters is kept, 97 is dropped,
  and a single character outside the language at the start, the middle or the end drops the value whole
  (`test_the_reset_length_boundaries`, `test_a_character_outside_the_language_drops_the_value`).
* G-3's completeness is the conjunction of its three conditions: a real EOF read inside the deadline, an exit code
  0 read inside the deadline, and no read error. A read that expires at any of those transitions -- the loop head, a
  read, the EOF, the successful wait -- is incomplete and never provider evidence
  (`test_the_deadline_is_latched_at_every_transition`, `test_a_read_error_is_not_a_complete_read`).
* G-3's cleanup holds on every path after a successful spawn: stdout is closed, a still-running reader is killed
  (its own session, its own process) and reaped with `wait` for at most two seconds, and a reader that already
  exited is only reaped, never signalled (`test_a_running_reader_is_killed_and_reaped`,
  `test_a_reader_that_already_exited_is_never_signalled`).
* G-3's retention is the last `buffer` bytes, so exactly `buffer` bytes is not an overflow and only the leading
  partial line of an overflow goes (`test_the_oversized_window_boundary`,
  `test_a_one_byte_overflow_keeps_the_complete_record_in_the_window`).

A-6, the two base revisions. Every behavioural check of the new contracts is run against two revisions that do not
implement them, from a private copy so nothing in the shared worktree is reverted:

    S=$(mktemp -d /tmp/zs-agent-XXXXXX)
    python3 -c 'import shutil,sys; shutil.copytree(".", sys.argv[1],
        ignore=shutil.ignore_patterns(".git", ".tools", "__pycache__"))' $S/repo
    # base 9871d2d (the run base, no S4 at all) and f3f4cf0 (the preserved earlier candidate):
    for f in terminal_planner/engine.py terminal_planner/live.py terminal_planner/runs.py \
             terminal_planner/planning.py terminal_planner/delivery.py terminal_planner/catalog.py; do
        git show <revision>:$f > $S/repo/$f
    done
    (cd $S/repo && TMPDIR=$S PYTHONPATH=$S/repo:$S/repo/tests python3 -m unittest tests.test_run_cause)

Observed (Python 3.9.6, macOS, TMPDIR in the private copy):

    f3f4cf0: Ran 97 tests ... FAILED (failures=76, errors=265)
    9871d2d: Ran 97 tests ... FAILED (failures=269, errors=318)

The 265/318 errors are the absent or differently shaped API of those revisions (the G-1 entry point takes the
retained lines here and one text blob there; the base has no S4 names at all), so the A-6 evidence is the assertion
failures. At least one behavioural test per contract fails at its named assertion on f3f4cf0 (G-1
`StoreTests.test_a_conflicting_cursor_at_the_store_is_unknown` and `test_a_non_enum_code_at_the_store_is_unknown`,
plus the whole-record conflict pair `test_records_that_share_a_cursor_and_differ_in_their_target_are_unknown` and
`test_records_that_share_a_cursor_and_differ_in_their_timestamp_are_unknown`; G-2
`ResetTests.test_only_the_reset_language_passes`; G-3 `ReaderTests.test_a_read_error_is_not_a_complete_read`), and
all seven `CompatibilityTests` pass on both revisions. The `reset=null` refusal is a repair of this candidate
alone, so that test passes on f3f4cf0 as well (`Ran 7 tests ... OK` for `CompatibilityTests` on both).
The receipt carries the full output.

The environment keeps the task's rules: no provider, no network, deterministic fixtures, and every read of a run's
logs replaced by a scripted double (the reader itself is exercised with real child processes and with scripted
`popen`/`clock` doubles)."""

import copy
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terminal_planner import delivery, engine, live, runs, toolchain
from terminal_planner.authority import Blocked, canonical, decode
from terminal_planner.runs import MilestoneRuns
from test_runs import RunsTest
from test_terminal_planner import ROLES


def envelope(cursor, message, level="error", execution=None, target="zeroshot", timestamp=1791935230934):
    """One `zeroshot logs` JSON line exactly as the CLI writes it (native_v2_observation.rs / projection.rs)."""
    value = {"subscriptionId": "subscription", "runId": "run", "timestamp": timestamp,
             "record": {"level": level, "target": target, "message": message}}
    if cursor is not None:
        value["cursor"] = cursor
    if execution is not None:
        value["execution"] = execution
    return json.dumps(value, ensure_ascii=False)


def stream(*records):
    return "\n".join(records) + "\n"


# The four excerpts of the run records, each as the engine would summarise it in a `Node <node> failed:` record,
# plus a provider failure of a class none of them names.
CLAUDE_LIMIT = ("Node code failed: crash after 55.0s: node execution failed: Claude provider failure: "
                "You've hit your session limit · resets 3:10am (Europe/Moscow); provider process exited with status 1")
CODEX_403 = ("Node acceptance failed: crash after 544.1s: node execution failed: Codex provider failure: "
             "workspace routing discovery failed; stderr: unexpected status 403 Forbidden: <html>\n  <body>denied</body>")
CODEX_401 = ("Node code failed: crash after 46.9s: node execution failed: Codex provider failure: "
             "workspace routing discovery unauthorized (401); provider process exited with status 1")
CODEX_CREDITS = ("Node code failed: crash after 287.9s: node execution failed: Codex provider failure: "
                 "Your workspace is out of credits. Ask your workspace owner to refill in order to continue.")
UNKNOWN_ERROR = ("Node code failed: crash after 9.0s: node execution failed: Codex provider failure: "
                 "the workspace rules file could not be read")
RETRY_DIAGNOSTIC = "Claude provider failure: session limit · resets 3:10am (Europe/Moscow)"
OPAQUE_SUMMARY = ("Node code failed: crash after 5.0s: node execution failed: Codex provider failure: "
                  "the workspace rules file could not be read")


class ReaderScript:
    """A native driver whose one `zeroshot logs` read is scripted and counted, shared by the store classes."""

    def script(self, responses, lines=(), complete=True):
        driver, calls = self.driver(list(responses))
        reads = []

        def log_records(binding, run_id, cwd, **options):
            reads.append((binding, run_id, cwd, dict(options)))
            return list(lines), complete

        driver.log_records = log_records
        return driver, calls, reads

    @staticmethod
    def done():
        return {"signal": "done", "message": "Milestone complete.", "question": None, "proposal": None}


class CompatibilityTests(ReaderScript, RunsTest):
    """A-6: the compatibility contract -- every check here passes on base 9871d2d AND on this change.

    Nothing here calls an S4-only entry point: the flat extractor and the non-error exclusion already held (R-1),
    a stopped, successful or pre-dispatch conclude already read nothing (G-3), a poll loop still reads no failure
    cause -- it now follows the active executions' logs at most once per 30 s (C3a, A2) -- and an old-format failed
    record without a `cause` loads, keeps today's text and reads nothing (G-2). The module docstring records the
    exact commands; the new behaviour lives in the other classes."""

    def test_flat_error_lines_still_classify(self):
        self.assertEqual(engine.classify(engine.error_lines("", "provider error: 401 Unauthorized\n")[0]), "auth")
        self.assertEqual(engine.classify(engine.error_lines("", "429 Too Many Requests: usage limit reached")[0]), "quota")
        record = canonical({"level": "error", "message": "provider: 429 rate limit exceeded"})
        self.assertEqual(engine.classify("\n".join(engine.error_lines(record + "\n", ""))), "quota")

    def test_info_system_and_model_records_are_never_classified(self):
        text = [envelope("v2:1", "Claude rate limit: status=allowed_warning, resetsAt=2026-10-19T05:00:00Z", level="debug"),
                envelope("v2:2", "plain model text about authentication and 429 limits", level="info"),
                envelope("v2:3", "tool output: usage limit reached", level="warn")]
        self.assertEqual(engine.error_lines(stream(*text), ""), [])
        # The same shape without a native record (the flat format) is unchanged.
        self.assertEqual(engine.error_lines(canonical({"type": "message", "text": "usage limit"}) + "\n", ""), [])

    def test_a_stopped_conclude_reads_nothing(self):
        r = self.started()
        with self.authority() as a:
            controller = MilestoneRuns(a, None, worktrees=self.worktrees)
            controller.active()["status"] = "stopping"
            controller.save(controller.active())
        with self.authority() as a:
            driver, calls, reads = self.script([(self.finished(r, reason="force_stopped"),)])
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            record = controller.observe(controller.active())
        self.assertEqual((record["status"], record.get("cause")), ("stopped", None))
        self.assertEqual(reads, [])

    def test_a_poll_loop_reads_at_most_one_execution_log_per_30s(self):
        r = self.started()
        with self.authority() as a:
            driver, calls, reads = self.script([(self.running(r),), (self.running(r),)])
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            for _ in range(2):
                record = controller.observe(controller.active())
        # C3a/A2: two slices within 30 s read at most one execution log -- the command read (an `execution` ref
        # and its own short deadline), never the failure-cause diagnosis read; the run is not concluding, so no
        # cause is stored. "At most one" holds on the base too (it read none), which keeps this contract check.
        self.assertLessEqual(len(reads), 1)
        self.assertTrue(all(options.get("execution") == "e1" for _, _, _, options in reads))
        self.assertNotIn("cause", record)

    def test_a_successful_conclude_reads_nothing(self):
        r = self.started()
        self.complete(r)
        with self.authority() as a:
            driver, calls, reads = self.script([(self.finished(r, output=self.done()),)])
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            record = controller.observe(controller.active())
        self.assertEqual((record["status"], record["outcome"], record.get("cause")), ("finished", "done", None))
        self.assertEqual(reads, [])

    def test_a_pre_dispatch_start_reads_nothing(self):
        with self.authority() as a:
            driver, calls, reads = self.script([{"valid": False}])
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            with self.assertRaises(Blocked):
                controller.start("M1", 2, ROLES)
        self.assertEqual(reads, [])

    def test_an_old_format_failed_record_loads_shows_todays_text_and_reads_nothing(self):
        # G-2/A-5: a record written before the cause existed has no `cause` key; it still loads as a failed run,
        # still shows exactly today's text and triggers no read. Nothing here needs an S4-only entry point, so the
        # check holds on the base as well.
        r = self.started()
        with self.authority() as a:
            driver, calls, reads = self.script([(self.finished(r, reason="review_failed"),),
                                                self.status(r, {"recoverable": False})])
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            controller.observe(controller.active())
            state = decode(a.path.read_text())
            state["runs"][0].pop("cause", None)  # an old format has neither key
            state["runs"][0].pop("reset", None)
            a.path.write_text(canonical(state) + "\n")
        reads = []
        with self.authority() as a:
            driver, calls = self.driver([])
            driver.log_records = lambda *args, **options: reads.append((args, options)) or ([], True)
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            stored = decode(a.path.read_text())["runs"][0]
            self.assertEqual((stored["status"], stored.get("cause"), stored.get("reset")), ("failed", None, None))
            self.assertEqual(runs.run_state(stored), "failed")
            self.assertEqual(delivery.Delivery.state_text({"state": "failed", "record": stored}),
                             delivery.STATE_TEXT["failed"])
            view = delivery.Delivery(a, controller, None).end(stored)
        self.assertEqual(list(view.body), ["  Reason: «review_failed»"])
        self.assertEqual(reads, [])
        self.assertEqual(calls, [])


class ExtractorTests(unittest.TestCase):
    """R-1: the native envelope joins the flat formats; the flat formats themselves live in CompatibilityTests."""

    def test_a_native_error_record_is_read_through_its_message(self):
        line = envelope("v2:204", "Claude provider failure: session limit", execution="nv2-1")
        self.assertEqual(engine.error_lines(line + "\n", ""), ["Claude provider failure: session limit"])
        self.assertEqual(engine.error_lines("", line + "\n"), ["Claude provider failure: session limit"])
        self.assertEqual(engine.error_lines("", canonical({"level": "error", "message": "boom"}) + "\n"), ["boom"])
        self.assertEqual(engine.error_lines("", "plain diagnostic\n"), ["plain diagnostic"])

    def test_a_native_envelope_is_filtered_by_level_on_both_streams(self):
        for level in ("info", "debug", "system", "warn"):
            line = envelope("v2:1", "Claude provider failure: You've hit your session limit", level=level)
            self.assertEqual(engine.error_lines(line + "\n", ""), [])
            self.assertEqual(engine.error_lines("", line + "\n"), [])
        good = envelope("v2:3", "session limit", level="error")
        self.assertEqual(engine.error_lines(good + "\n", ""), ["session limit"])

    def test_a_flat_structured_record_is_filtered_by_level_on_both_streams(self):
        for level in ("info", "debug", "system", "warn"):
            line = canonical({"level": level, "message": "Model example: 401 Unauthorized"})
            self.assertEqual(engine.error_lines(line + "\n", ""), [])
            self.assertEqual(engine.error_lines("", line + "\n"), [])

    def test_an_explicit_non_error_kind_wins_over_an_error_field(self):
        for line in (canonical({"level": "info", "message": "model example", "error": "401 Unauthorized"}),
                     canonical({"type": "message", "role": "assistant", "error": "401 Unauthorized"})):
            self.assertIsNone(engine.classify("\n".join(engine.error_lines("", line + "\n"))))
            self.assertIsNone(engine.classify("\n".join(engine.error_lines(line + "\n", ""))))
        legacy = canonical({"error": "401 Unauthorized"})
        self.assertEqual(engine.classify("\n".join(engine.error_lines("", legacy + "\n"))), "auth")

    def test_a_malformed_structured_stderr_record_is_not_a_plain_diagnostic(self):
        fragment = envelope("v2:1", "Codex provider failure: unexpected status 403 Forbidden", level="info")[:-2]
        self.assertEqual(engine.error_lines("", fragment + "\n"), [])
        self.assertEqual(engine.error_lines("", "provider error: 403 Forbidden\n"), ["provider error: 403 Forbidden"])

    def test_a_separator_inside_a_json_string_does_not_hide_a_record(self):
        # LF is the only record boundary: U+2028/U+2029/U+0085 inside a JSON string are part of the string.
        message = "Codex provider failure: unexpected status 403 Forbidden \u2028 denied \u0085 denied"
        self.assertEqual(engine.error_lines(envelope("v2:1", message, execution="nv2-1") + "\n", ""), [message])
        self.assertEqual(engine.observed_cause([envelope("v2:1", "Node x failed: crash: node execution failed: " + message,
                                                         execution="nv2-1")]), ("forbidden", None))


class MilestoneTests(unittest.TestCase):
    """G-1: which record is decisive, what its evidence is and which class it names."""

    def test_the_four_excerpts_give_their_classes(self):
        self.assertEqual(engine.observed_cause([envelope("v2:204", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:220", CLAUDE_LIMIT, execution="nv2-1")]),
                         ("limit", "3:10am (Europe/Moscow)"))
        self.assertEqual(engine.observed_cause([envelope("v2:813", CODEX_403, execution="nv2-1")]), ("forbidden", None))
        self.assertEqual(engine.observed_cause([envelope("v2:76", CODEX_401, execution="nv2-1")]), ("auth", None))
        self.assertEqual(engine.observed_cause([envelope("v2:1084", CODEX_CREDITS, execution="nv2-1")]), ("quota", None))

    def test_the_code_enum_is_closed(self):
        for code in ("timeout", "crash", "malformed", "refusal"):
            self.assertEqual(engine.observed_cause([envelope("v2:9", "Node code failed: %s: node execution failed: "
                                                             "Codex provider failure: unexpected status 403 Forbidden"
                                                             % code, execution="nv2-1")]), ("forbidden", None))
        # Another code is not the engine's completion summary, so the record is ignored and the result unknown.
        self.assertEqual(engine.observed_cause([envelope("v2:9", "Node code failed: declared_failure: node execution "
                                                         "failed: Codex provider failure: unexpected status 403 Forbidden",
                                                         execution="nv2-1")]), (None, None))

    def test_the_engine_reasons_decide_before_the_cause(self):
        self.assertEqual(engine.observed_cause([envelope("v2:9", "Node code failed: crash: authentication required",
                                                         execution="nv2-1")]), ("auth", None))
        for reason in (": policy denied", ": interactive input required", ": result did not match the node contract"):
            message = ("Node code failed: malformed: final output rejected" + reason + ": node execution failed: "
                       "Claude provider failure: You've hit your session limit · resets 3:10am (Europe/Moscow)")
            with self.subTest(reason):
                self.assertEqual(engine.observed_cause([envelope("v2:9", message, execution="nv2-1")]), (None, None))

    def test_a_cause_without_the_engine_label_is_unknown(self):
        # G-1's PROVIDER grammar carries the engine's own capsule label; a completion cause that is the bare
        # provider diagnostic does not fullmatch it. The retry's bare diagnostic is a DIAGNOSTIC record instead.
        message = "Node code failed: crash: Claude provider failure: unexpected status 403 Forbidden"
        self.assertEqual(engine.observed_cause([envelope("v2:9", message, execution="nv2-1")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", "Claude provider failure: unexpected status 403 "
                                                         "Forbidden", execution="nv2-1"),
                                                envelope("v2:9", OPAQUE_SUMMARY, execution="nv2-1")]), ("forbidden", None))

    def test_the_provider_wording_counts_at_the_diagnostic_origin_only(self):
        quoted = ("Node code failed: crash: node execution failed: final output rejected: schema invalid: "
                  "unknown field `x: Codex provider failure: authentication required (401)`")
        nested = ("Node code failed: malformed: result did not match the node contract: node execution failed: "
                  "Codex provider failure: authentication required (401)")
        for message in (quoted, nested):
            with self.subTest(message):
                self.assertEqual(engine.observed_cause([envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-1"),
                                                        envelope("v2:2", message, execution="nv2-1")]), (None, None))
                self.assertEqual(engine.observed_cause([envelope("v2:2", message, execution="nv2-1")]), (None, None))

    def test_a_class_word_alone_is_not_a_provider_failure(self):
        for message in ("Node worker failed: crash: node execution failed: task input file "
                        "/tmp/authentication.json could not be read",
                        "Node code failed: refusal after 1.0s: run is already closed",
                        "Node code failed: crash after 1.0s: plain diagnostic without the label"):
            with self.subTest(message):
                self.assertEqual(engine.observed_cause([envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-1"),
                                                        envelope("v2:2", message, execution="nv2-1")]), (None, None))

    def test_the_run_wide_records_are_never_decisive_and_are_never_evidence(self):
        # Row 3: an absent or null execution id is the run-wide record. Rule 3: a completion whose cause is
        # `run <reason>` is not decisive. Neither is evidence, so a class-bearing reason names nothing.
        self.assertEqual(engine.observed_cause([envelope("v2:1", "Run failed: review_failed")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", CLAUDE_LIMIT)]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:2", "Node code failed: crash: run review_failed",
                                                         execution="nv2-1")]), ("limit", "3:10am (Europe/Moscow)"))
        opaque = ("Node code failed: crash after 5.0s: node execution failed: Codex provider failure: "
                  "the workspace rules file could not be read")
        self.assertEqual(engine.observed_cause([envelope("v2:1", "Node acceptance failed: crash: run quota_exhausted",
                                                         execution="nv2-1"),
                                                envelope("v2:2", opaque, execution="nv2-1")]), (None, None))

    def test_the_latest_completion_decides(self):
        # A later completion with no provider cause is decisive too, and then gives unknown (rule 3) whatever an
        # earlier execution said; a later *diagnostic* alone never decides.
        self.assertEqual(engine.observed_cause([envelope("v2:1", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:5", "Node acceptance failed: refusal after 5.0s",
                                                         execution="nv2-2")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", OPAQUE_SUMMARY, execution="nv2-1"),
                                                envelope("v2:5", RETRY_DIAGNOSTIC, execution="nv2-1")]), (None, None))

    def test_the_evidence_is_the_decisive_detail_and_its_own_execution_only(self):
        self.assertEqual(engine.observed_cause([envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-1"),
                                                envelope("v2:6", OPAQUE_SUMMARY, execution="nv2-1")]),
                         ("limit", "3:10am (Europe/Moscow)"))
        self.assertEqual(engine.observed_cause([envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-2"),
                                                envelope("v2:6", OPAQUE_SUMMARY, execution="nv2-1")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-1"),
                                                envelope("v2:6", OPAQUE_SUMMARY, execution="nv2-2")]), (None, None))

    def test_the_precedence_is_the_causes_order(self):
        # The class is the highest of the *evidence* classes, so each case is one decisive completion whose own
        # detail names nothing plus two same-execution diagnostics that carry the classes at lower cursors.
        self.assertEqual([name for name, _ in engine.CAUSES],
                         ["limit", "quota", "forbidden", "auth", "network"])
        detail = {"limit": "Claude provider failure: session limit · resets 2:00am (Europe/Moscow)",
                  "quota": "Codex provider failure: Your workspace is out of credits.",
                  "forbidden": "Codex provider failure: unexpected status 403 Forbidden",
                  "auth": "Codex provider failure: workspace routing discovery unauthorized (401)",
                  "network": "Codex provider failure: connection refused (ECONNREFUSED)"}
        for first in engine.CAUSES:
            for second in engine.CAUSES:
                if first[0] == second[0]:
                    continue
                expected = first[0] if engine.CAUSES.index(first) < engine.CAUSES.index(second) else second[0]
                lines = [envelope("v2:2", detail[first[0]], execution="nv2-1"),
                         envelope("v2:5", detail[second[0]], execution="nv2-1"),
                         envelope("v2:9", OPAQUE_SUMMARY, execution="nv2-1")]
                with self.subTest(first=first[0], second=second[0]):
                    self.assertEqual(engine.observed_cause(lines)[0], expected)

    def test_the_reset_comes_from_the_highest_limit_detail(self):
        first = "Claude provider failure: session limit · resets 1:00am (Europe/Moscow)"
        second = "Claude provider failure: session limit · resets 2:00am (Europe/Moscow)"
        self.assertEqual(engine.observed_cause([envelope("v2:1", first, execution="nv2-1"),
                                                envelope("v2:2", second, execution="nv2-1"),
                                                envelope("v2:9", OPAQUE_SUMMARY, execution="nv2-1")]),
                         ("limit", "2:00am (Europe/Moscow)"))
        # A quota detail at the highest cursor does not win the class, so the reset still belongs to the highest
        # limit detail (interpretation: rule 5's "matching detail" matches the winning class).
        self.assertEqual(engine.observed_cause([envelope("v2:1", second, execution="nv2-1"),
                                                envelope("v2:2", "Codex provider failure: Your workspace is out of "
                                                                 "credits.", execution="nv2-1"),
                                                envelope("v2:9", OPAQUE_SUMMARY, execution="nv2-1")]),
                         ("limit", "2:00am (Europe/Moscow)"))

    def test_a_truncated_detail_matches_only_on_what_it_contains(self):
        # Rule 6: a cut detail is classified like any other. Cut before the class word, it matches nothing; cut
        # after one, that word decides and a cut reset is still read from the retained text.
        self.assertEqual(engine.observed_cause([envelope("v2:9", "Node code failed: crash: node execution failed: "
                                                         "Codex provider failure: unexpected status 40",
                                                         execution="nv2-1")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:9", "Node code failed: crash: node execution failed: "
                                                         "Codex provider failure: unexpected status 403 Fo",
                                                         execution="nv2-1")]), ("forbidden", None))
        self.assertEqual(engine.observed_cause([envelope("v2:9", "Node code failed: crash: node execution failed: "
                                                         "Codex provider failure: hit your session limit · resets 3am",
                                                         execution="nv2-1")]), ("limit", "3am"))

    def test_the_execution_id_domain(self):
        limit = CLAUDE_LIMIT
        self.assertEqual(engine.observed_cause([envelope("v2:1", limit, execution="")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", limit, execution=7)]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", limit, execution={"id": "x"})]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:1", limit, execution=None)]), (None, None))

    def test_the_cursor_domain(self):
        for cursor in ("v2:1", "v2:" + "9" * 19, "v2:18446744073709551615"):
            with self.subTest(cursor):
                self.assertEqual(engine.observed_cause([envelope(cursor, CLAUDE_LIMIT, execution="nv2-1")]),
                                 ("limit", "3:10am (Europe/Moscow)"))
        for cursor in ("v2:18446744073709551616", "v2:" + "9" * 21, "v2:", "v2:١٢", "v2:1 ", "1", "v2:1\n", "v2:1.0"):
            with self.subTest(cursor):
                self.assertEqual(engine.observed_cause([envelope(cursor, CLAUDE_LIMIT, execution="nv2-1")]), (None, None))
        for cursor in (None, 7, ["v2:1"]):
            with self.subTest(repr(cursor)):
                self.assertEqual(engine.observed_cause([envelope(cursor, CLAUDE_LIMIT, execution="nv2-1")]), (None, None))

    def test_an_unusable_cursor_on_any_record_of_the_run_is_unknown(self):
        # Row 4: an error record that names an execution and carries no valid cursor leaves the *whole* result
        # unknown, whatever its message says and whatever the other records say.
        self.assertEqual(engine.observed_cause([envelope("v2:1", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:" + "9" * 21, "Codex command completed", execution="nv2-2")]),
                         (None, None))
        self.assertEqual(engine.observed_cause([envelope(None, RETRY_DIAGNOSTIC, execution="nv2-1")]), (None, None))

    def test_identical_duplicate_records_are_deduplicated(self):
        line = envelope("v2:7", CLAUDE_LIMIT, execution="nv2-1")
        self.assertEqual(engine.observed_cause([line, line, line]), ("limit", "3:10am (Europe/Moscow)"))
        # The same cursor twice with the same message but another execution is a conflict, not a duplicate.
        self.assertEqual(engine.observed_cause([envelope("v2:7", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:7", CLAUDE_LIMIT, execution="nv2-2")]), (None, None))

    def test_conflicting_records_sharing_a_cursor_are_unknown(self):
        self.assertEqual(engine.observed_cause([envelope("v2:7", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:7", CODEX_401, execution="nv2-1")]), (None, None))
        self.assertEqual(engine.observed_cause([envelope("v2:7", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:7", RETRY_DIAGNOSTIC, execution="nv2-1")]), (None, None))

    def test_records_that_differ_beyond_their_message_are_not_identical(self):
        """G-1's conflict rule is decided on the whole record, not on its execution and message.

        Class: G-1's identical-record requirement (deduplication and the conflict rule). Domain: pairs of error
        records that share one cursor, one execution and one message and differ only in a durable field -- the
        completion's `record.target`, the envelope's `timestamp`, a field inside the record, and the cursor's own
        spelling (`v2:07` vs `v2:7`, numerically the same sequence) -- plus the same payload written in another key
        order as the duplicate control. Oracle: each differing pair is unknown, the reordered pair is the same
        record and still limit. Interpretation: "identical duplicate records" means identical lines, so every
        durable field of the payload counts and none of `target`, `timestamp`, `cursor` spelling or an unknown
        extra field may be dropped before the comparison (the reviewers rejected reducing identity to execution and
        message)."""
        limit = ("Node code failed: crash: node execution failed: Claude provider failure: session limit "
                 "· resets 3:10am (Europe/Moscow)")
        first = envelope("v2:9", limit, execution="E1")
        others = {
            "record.target": envelope("v2:9", limit, execution="E1", target="codex"),
            "timestamp": envelope("v2:9", limit, execution="E1", timestamp=1791935230935),
            "cursor spelling": envelope("v2:09", limit, execution="E1"),
            "the message": envelope("v2:9", CODEX_401, execution="E1"),
        }
        for name, other in others.items():
            with self.subTest(name):
                self.assertEqual(engine.observed_cause([first, other]), (None, None))
        self.assertEqual(engine.observed_cause([first, first]), ("limit", "3:10am (Europe/Moscow)"))
        reordered = canonical({"execution": "E1", "cursor": "v2:9", "record": {"message": limit, "target": "zeroshot",
                                                                             "level": "error"},
                               "timestamp": 1791935230934, "runId": "run", "subscriptionId": "subscription"})
        self.assertEqual(engine.observed_cause([first, reordered]), ("limit", "3:10am (Europe/Moscow)"))

    def test_an_info_duplicate_does_not_conflict(self):
        # A non-error record is ignored, never evidence and never decisive, so it cannot make the result unknown.
        self.assertEqual(engine.observed_cause([envelope("v2:7", CLAUDE_LIMIT, execution="nv2-1"),
                                                envelope("v2:7", "session limit", level="info", execution="nv2-1")]),
                         ("limit", "3:10am (Europe/Moscow)"))

    def test_only_the_error_level_is_a_record(self):
        for level in ("info", "debug", "system", "warn"):
            with self.subTest(level):
                self.assertEqual(engine.observed_cause([envelope("v2:7", CLAUDE_LIMIT, level=level, execution="nv2-1"),
                                                        envelope("v2:8", "handled", level=level, execution="nv2-1")]),
                                 (None, None))
        # ... and a record without level or message, or one that is not a JSON object, is skipped, never fatal.
        self.assertEqual(engine.observed_cause(['{"record": {"message": "x"}}', "not json",
                                                "[]", envelope("v2:7", CODEX_401, execution="nv2-1")]), ("auth", None))
        self.assertEqual(engine.observed_cause(['{"record": {"level": "error"}, "cursor": "v2:1", "execution": "e"}']),
                         (None, None))
        self.assertEqual(engine.observed_cause(['{"record": {"level": 7, "message": "x"}, "cursor": "v2:1", '
                                                '"execution": "e"}']), (None, None))
        # A truncated envelope is not a record either, and it never hides the readable line beside it (A-3).
        cut = envelope("v2:1", CLAUDE_LIMIT, execution="nv2-1")[:-2]
        self.assertEqual(engine.observed_cause([cut, envelope("v2:9", CODEX_401, execution="nv2-1")]), ("auth", None))

    def test_a_pathologically_nested_line_is_skipped(self):
        deep = '{"cursor": "v2:1", "record": ' + "[" * 10000
        self.assertEqual(engine.observed_cause([deep, envelope("v2:9", CODEX_401, execution="nv2-1")]), ("auth", None))

    def test_a_run_wide_record_of_another_execution_is_no_evidence(self):
        # A reason the engine propagated into every active execution is never that execution's diagnostic.
        self.assertEqual(engine.observed_cause([envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-1"),
                                                envelope("v2:2", "Node acceptance failed: crash: run quota_exhausted",
                                                         execution="nv2-1"),
                                                envelope("v2:6", OPAQUE_SUMMARY, execution="nv2-1")]),
                         ("limit", "3:10am (Europe/Moscow)"))

    def test_no_records_at_all_is_unknown(self):
        self.assertEqual(engine.observed_cause([]), (None, None))
        self.assertEqual(engine.observed_cause(["", "   "]), (None, None))


def long_reset(size):
    """A grammar-valid reset of exactly `size` characters: a long `Area/City/Zone` time zone."""
    return "1am (Aa/Bb%s/Cc)" % ("b" * (size - 8 - 6))


class ResetTests(unittest.TestCase):
    """G-2: the reset is extracted after the last `resets `, cut, stripped, and kept only as R-4's time language."""

    def test_the_reset_is_the_text_after_the_last_resets(self):
        self.assertEqual(engine.reset_text("session limit · resets 3:10am (Europe/Moscow); x"), "3:10am (Europe/Moscow)")
        self.assertEqual(engine.reset_text("resets 1am; x resets 2:05pm (UTC) <html>"), "2:05pm (UTC)")
        for stop in (";", "·", "<", "\r", "\n"):
            with self.subTest(repr(stop)):
                self.assertEqual(engine.reset_text("resets   3am %s junk" % stop), "3am")
        self.assertIsNone(engine.reset_text("no marker here"))
        self.assertIsNone(engine.reset_text("resets "))

    def test_only_the_reset_language_passes(self):
        accepted = ("3:10am (Europe/Moscow)", "Oct 20, 5am (UTC)", "5am", "12:59pm", "Oct 1, 12am", "3:10am",
                    "5am (America/Argentina/Buenos_Aires)", "13:70am")  # the language, not a clock, is the oracle
        for value in accepted:
            with self.subTest(value):
                self.assertEqual(engine.reset_value(value), value)
        rejected = ("", " 3am", "3am ", "3.10am (UTC)", "3:10am (Europe/Moscow) please", "(UTC) 3am",
                    "3:10am (utc)", "3:10am (Europe/Moscow/Buenos_Aires/City)", "=3am", '"3am"', "[3am]",
                    "3:10:20am", "100am", "Oct 20,5am", "3am (sk-ABC)", "3am (token=x)", "3am\t", "tomorrow",
                    "resets", "3am (Moscow)", "3:10am (Europe/Moscow)=")
        for value in rejected:
            with self.subTest(value):
                self.assertIsNone(engine.reset_value(value))

    def test_the_reset_length_boundaries(self):
        self.assertEqual([len(long_reset(size)) for size in (95, 96, 97)], [95, 96, 97])
        for size, kept in ((95, True), (96, True), (97, False)):
            with self.subTest(size):
                value = long_reset(size)
                self.assertEqual(engine.reset_value(value), value if kept else None)
                self.assertEqual(engine.reset_value(engine.reset_text("resets " + value + "; x")),
                                 value if kept else None)
        # Each optional part, present and absent: the date and the zone.
        for value in ("5am", "5:30am", "Oct 20, 5am", "5am (UTC)", "5am (Europe/Moscow)", "Oct 20, 5am (Europe/Moscow)"):
            with self.subTest(value):
                self.assertEqual(engine.reset_value(value), value)

    def test_a_character_outside_the_language_drops_the_value(self):
        for value in ("=3:10am (Europe/Moscow)", "3:10am (Europe/Moscow)x", "3:10am (Europe/Moscow.)", "3:10am-x",
                      "3:10am (Europe/ Moscow)"):
            with self.subTest(value):
                self.assertIsNone(engine.reset_value(value))


class FakeStdout:
    def __init__(self, process):
        self.process = process

    def fileno(self):
        return 7

    def close(self):
        self.process.events.append("close")


class FakeProcess:
    """A scripted `popen` double for `live.records`: its `os.read` chunks, its exit and its signals are recorded."""

    def __init__(self, chunks, code=0, running=False, ticks=None):
        self.chunks = list(chunks)
        self.exit_code = code
        self.alive = running
        self.returncode = None if running else code
        self.events = []
        self.ticks = iter(ticks if ticks is not None else [0.0] * 32)
        self.stdout = FakeStdout(self)
        self.killed = False

    def read(self, fd, size):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk.encode() if isinstance(chunk, str) else chunk

    def wait(self, timeout=None):
        self.events.append(("wait", timeout))
        if self.alive and not self.killed:  # a reader that outlives the deadline never completes its wait in time
            raise subprocess.TimeoutExpired("zeroshot", timeout)
        self.alive = False
        self.returncode = -9 if self.killed else self.exit_code
        return self.returncode

    def poll(self):
        return None if self.alive else self.returncode

    def kill(self):
        self.events.append("kill")
        self.killed = True
        self.alive = False

    def clock(self):
        try:
            return next(self.ticks)
        except StopIteration:
            return 0.0


def scripted(chunks, code=0, running=False, ticks=None, deadline=30.0, buffer=None, spawn=None):
    """`live.records` over a scripted process: the ready set, `os.read` and the clock are the test's own."""
    process = FakeProcess(chunks, code, running, ticks)

    def popen(*args, **options):
        if spawn is not None:
            raise spawn
        return process

    with patch.object(live.select, "select", lambda r, w, x, timeout: (list(r), [], [])), \
            patch.object(live.os, "read", process.read):
        return live.records(["zeroshot", "logs", "run"], {}, None, deadline=deadline,
                            buffer=buffer if buffer is not None else engine.LOG_LIMIT,
                            popen=popen, clock=process.clock), process


def deadline_read(payload, ticks, deadline=30.0, buffer=None):
    """`live.records` over a scripted process whose stdout is a real pipe holding `payload`.

    The process reports itself already exited 0, so the only way the read can be incomplete is the deadline: the
    instrument is the reader's own output, never the assertion's oracle. `ticks` places a clock value past
    `deadline` exactly at the transition under test."""
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload if isinstance(payload, bytes) else payload.encode())
    os.close(write_fd)

    class _Stdout:
        def fileno(self):
            return read_fd

        def close(self):
            os.close(read_fd)

    class _Process:
        stdout = _Stdout()
        returncode = 0

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

        def kill(self):  # a process that already exited is never killed (poll() is not None)
            raise AssertionError("a process that already exited must not be killed")

    ticks = iter(ticks)
    return live.records(["zeroshot", "logs", "run"], {}, None, deadline=deadline,
                        buffer=buffer if buffer is not None else engine.LOG_LIMIT,
                        popen=lambda *args, **options: _Process(), clock=lambda: next(ticks))


class ReaderTests(unittest.TestCase):
    """G-3: the bounded reader itself, with scripted doubles and with real child processes."""

    @staticmethod
    def read(code, **options):
        return live.records([sys.executable, "-c", code], dict(os.environ), os.getcwd(), **options)

    def read_payload(self, payload, **options):
        """Read a real child that streams exactly `payload`: the bytes travel through a file, never a `-c` argument.

        One `execve` argument is bounded far below these fixtures -- Linux x86_64 allows 131072 bytes per argument,
        a 262144-byte payload needs more than 524288 as hex -- so the inline form cannot even start the child
        (E2BIG) there. The child opens the file the harness wrote and copies it to its stdout (A-3)."""
        handle, path = tempfile.mkstemp(prefix="run-cause-payload-")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
            code = "import sys; sys.stdout.buffer.write(open(%r, 'rb').read())" % path
            self.assertLess(len(code.encode()), 131072)  # the fixture's own guard, independent of the reader
            return self.read(code, **options)
        finally:
            os.unlink(path)

    def test_a_clean_read_is_complete_and_never_signals(self):
        line = envelope("v2:9", CODEX_401, execution="nv2-1")
        (lines, complete), process = scripted([line + "\n", b""], ticks=[0.0] * 6)
        self.assertEqual((lines, complete), ([line], True))
        self.assertEqual(process.events, [("wait", 30.0), "close", ("wait", 2)])
        self.assertNotIn("kill", process.events)

    def test_a_nonzero_exit_is_not_a_complete_read(self):
        (lines, complete), process = scripted(["boom\n", b""], code=3)
        self.assertEqual((lines, complete), (["boom"], False))
        self.assertNotIn("kill", process.events)

    def test_a_read_error_is_not_a_complete_read(self):
        """G-3: "no read error happened" is one of the three conditions of `complete`.

        Class: the read error path, at the loop and at the cleanup. Domain: a scripted process whose second read
        raises OSError, once already exited and once still running; checked values: `(lines, complete)`, that no
        exception escapes, and the cleanup events. Oracle: the lines read before the error are returned, `complete`
        is False, stdout is closed and a reader that is still running is killed. Interpretation: a read error is a
        condition of completeness, never an error of the caller."""
        line = envelope("v2:9", CODEX_401, execution="nv2-1")
        try:
            (lines, complete), process = scripted([line + "\n", OSError(5, "Input/output error")], ticks=[0.0] * 6)
        except OSError:
            self.fail("a read error is a condition of `complete`, never an error of the caller")
        self.assertEqual((lines, complete), ([line], False))
        self.assertEqual(process.events, [("wait", 30.0), "close", ("wait", 2)])
        (lines, complete), process = scripted([line + "\n", OSError(5, "Input/output error")], running=True,
                                              ticks=[0.0] * 6)
        self.assertEqual((lines, complete), ([line], False))
        self.assertIn("kill", process.events)
        self.assertIn("close", process.events)

    def test_a_spawn_failure_signals_nothing(self):
        with self.assertRaises(OSError):
            scripted([], spawn=OSError(2, "No such file or directory"))

    def test_a_running_reader_is_killed_and_reaped(self):
        """G-3: a reader still running when the read ends is killed (its own process) and reaped for at most 2 s."""
        line = envelope("v2:9", CODEX_401, execution="nv2-1")
        (lines, complete), process = scripted([line + "\n", line + "\n"], running=True,
                                              ticks=[0.0, 0.0, 31.0, 31.0])
        self.assertEqual((lines, complete), ([line], False))
        self.assertEqual(process.events, ["kill", "close", ("wait", 2)])

    def test_a_reader_that_already_exited_is_never_signalled(self):
        line = envelope("v2:9", CODEX_401, execution="nv2-1")
        (lines, complete), process = scripted([line + "\n", line + "\n"], ticks=[0.0, 0.0, 31.0, 31.0])
        self.assertEqual((lines, complete), ([line], False))
        self.assertNotIn("kill", process.events)
        self.assertEqual(process.events, ["close", ("wait", 2)])

    def test_the_deadline_is_latched_at_every_transition(self):
        """G-3: the read expires at the loop head, at the equality, at EOF and at the successful wait.

        Class: the deadline of the reader. Domain: a scripted process (a real record, an injected clock); each case
        puts the clock past `deadline=30` at exactly one transition: the loop head after a read, the equality
        `clock() == end`, the EOF read, and the `wait` that follows a successful EOF. Oracle: `complete` is False in
        all four and the record read before the expiry is still returned. Interpretation: an observation at
        `clock() >= end` is expired, and an expiration is never cleared."""
        line = envelope("v2:9", CODEX_401, execution="nv2-1")
        cases = {  # the clock is read once for `end`, then at each transition of the read
            "during a read (loop head)": [0.0, 0.0, 31.0, 31.0],
            "equality at the deadline": [0.0, 0.0, 30.0, 30.0],
            "at the EOF read": [0.0, 0.0, 0.0, 31.0, 31.0],
            "during the wait": [0.0, 0.0, 0.0, 0.0, 0.0, 31.0, 31.0],
        }
        for name, ticks in cases.items():
            with self.subTest(name):
                (lines, complete), _ = scripted([line + "\n"], ticks=ticks)
                self.assertEqual((lines, complete), ([line], False))

    def test_the_deadline_latch_holds_for_a_real_pipe(self):
        # The same two transitions over a real pipe: the EOF and the successful wait of an already-exited process.
        line = envelope("v2:9", CODEX_401, execution="nv2-1")
        self.assertEqual(deadline_read(line + "\n", [0.0, 0.0, 0.0, 31.0, 31.0]), ([line], False))
        self.assertEqual(deadline_read(line + "\n", [0.0, 0.0, 0.0, 0.0, 0.0, 31.0, 31.0]), ([line], False))

    def test_empty_output_and_a_clean_exit(self):
        self.assertEqual(self.read("pass"), ([], True))

    def test_a_deadline_that_passes_first_is_not_a_complete_read(self):
        self.assertEqual(self.read("import time; time.sleep(3)", deadline=0.2), ([], False))

    def test_stderr_is_never_evidence(self):
        lines, complete = self.read("import sys; sys.stderr.write('session limit\\n')")
        self.assertEqual((lines, complete), ([], True))

    def test_a_command_that_outlives_its_deadline_is_not_a_complete_read(self):
        # G-3: the reader kills only its own process when the deadline passes, and reads nothing after it.
        code = ("import sys, time\n"
                "sys.stdout.write('session limit exists elsewhere\\n'); sys.stdout.flush()\n"
                "time.sleep(3)\n")
        lines, complete = self.read(code, deadline=0.3)
        self.assertEqual((lines, complete), (["session limit exists elsewhere"], False))

    def test_a_read_requires_a_real_eof_not_just_the_command_exit(self):
        """G-3, real EOF: the command's own exit is not the end of its stdout.

        Domain: `live.records` over a real child that prints one record and exits at once while its own child holds
        stdout past the deadline; checked value: `(lines, complete)` at a 0.4 s deadline. Interpretation: `complete`
        needs a real `os.read` EOF inside the deadline, never just the process exit."""
        early = "early record"
        code = ("import subprocess, sys\n"
                "print(%r); sys.stdout.flush()\n"
                "subprocess.Popen([sys.executable, '-c', \"import time; time.sleep(0.6); print('late record')\"])"
                % early)
        lines, complete = live.records([sys.executable, "-c", code], dict(os.environ), os.getcwd(), deadline=0.4)
        self.assertEqual((lines, complete), ([early], False))

    def payload(self, size):
        """A `zeroshot logs` stream of exactly `size` bytes: a run of multi-byte Cyrillic lines, then the tail record."""
        tail = (envelope("v2:900", CODEX_403, execution="nv2-2") + "\n").encode()
        lead = ("я" * ((size - len(tail) - 1) // 2)).encode()  # 2 bytes each
        return lead + b"z" * ((size - len(tail) - 1) - len(lead)) + b"\n" + tail, tail

    def test_the_oversized_window_boundary(self):
        # The 262143/262144/262145 boundary with a multi-byte character at the cut: exactly `buffer` bytes is not an
        # overflow, and one byte over drops only the leading partial line.
        tail_record = envelope("v2:900", CODEX_403, execution="nv2-2")
        for size in (262143, 262144):
            with self.subTest(size):
                payload, _ = self.payload(size)
                self.assertEqual(len(payload), size)
                lines, complete = self.read_payload(payload, buffer=256 * 1024, deadline=20)
                self.assertTrue(complete)
                self.assertIn(tail_record, lines)  # the whole stream fits: nothing is dropped
                self.assertTrue(all("\ufffd" not in line for line in lines))
        payload, _ = self.payload(262145)
        self.assertEqual(len(payload), 262145)
        lines, complete = self.read_payload(payload, buffer=256 * 1024, deadline=20)
        self.assertTrue(complete)
        self.assertEqual(lines, [tail_record])  # one byte over: the cut multi-byte fragment is dropped whole
        self.assertEqual(engine.observed_cause(lines), ("forbidden", None))

    def test_a_one_byte_overflow_keeps_the_complete_record_in_the_window(self):
        """G-3/A-3: the retained window is the last `buffer` bytes, so a one-byte overflow cuts one byte.

        Domain: a real child writing exactly `buffer + 1` bytes -- a complete native envelope at byte 3, then a
        whitespace tail and a final newline -- and the same stream with the envelope pushed out of the window.
        Oracle: the window is the last `buffer` bytes, so the envelope (wholly inside it) survives and only the
        leading partial `{}` record goes; the out-of-window copy is dropped."""
        buffer = 256 * 1024
        record = envelope("v2:9", CODEX_401, execution="nv2-1")
        head = "{}\n"
        padding = buffer + 1 - len(head) - len(record) - 2
        payload = (head + record + "\n" + " " * padding + "\n").encode()
        self.assertEqual(len(payload), buffer + 1)
        lines, complete = self.read_payload(payload, buffer=buffer, deadline=20)
        self.assertEqual((lines, complete), ([record], True))
        self.assertEqual(engine.observed_cause(lines), ("auth", None))
        outside = (head + record + "\n" + " " * buffer + "\n").encode()
        self.assertEqual(self.read_payload(outside, buffer=buffer, deadline=20), ([], True))

    def test_blank_lines_are_dropped(self):
        lines, complete = self.read("import sys; sys.stdout.write('a\\n\\n   \\nb\\n')")
        self.assertEqual((lines, complete), (["a", "b"], True))


class ReaderTestsRealProcesses(unittest.TestCase):
    """G-3's completeness conditions over real children, with no scripted double at all."""

    def test_a_multi_byte_character_at_the_cut_is_only_in_the_dropped_line(self):
        # The window's leading partial line is the only place a replacement character can appear, and it is dropped.
        record = envelope("v2:9", CODEX_401, execution="nv2-1")
        payload = ("я" * 8 + "\n" + record + "\n").encode()
        buffer = len(record.encode()) + 9  # the window starts nine bytes in, inside a `я`
        self.assertEqual((len(payload) - buffer) % 2, 1)  # an odd cut: half a multi-byte character
        handle, path = tempfile.mkstemp(prefix="run-cause-cut-")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(payload)
            lines, complete = live.records([sys.executable, "-c",
                                            "import sys; sys.stdout.buffer.write(open(%r, 'rb').read())" % path],
                                           dict(os.environ), os.getcwd(), buffer=buffer, deadline=20)
        finally:
            os.unlink(path)
        self.assertEqual((lines, complete), ([record], True))


class StoreTests(ReaderScript, RunsTest):
    """G-1..G-3 at the milestone store: what a failed conclude keeps, shows and reads."""

    def conclude_failed(self, lines=(), complete=True, recovery=None, reason="review_failed", status=None):
        """One failed observe slice with a scripted logs read; returns (record, calls, reads, stored as saved).

        `status` replaces the recovery-status response, so a scripted error can stand in for an unreadable one."""
        r = self.started()
        response = self.status(r, recovery or {"recoverable": False}) if status is None else status
        with self.authority() as a:
            driver, calls, reads = self.script([(self.finished(r, reason=reason),), response], lines, complete)
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            record = controller.observe(controller.active())
            stored = copy.deepcopy(decode(a.path.read_text())["runs"][0])
        return copy.deepcopy(record), calls, reads, stored

    def test_a_failed_conclude_stores_the_cause_and_the_reset(self):
        record, calls, reads, stored = self.conclude_failed([envelope("v2:204", CLAUDE_LIMIT, execution="nv2-1")])
        self.assertEqual((record.get("cause"), record.get("reset")), ("limit", "3:10am (Europe/Moscow)"))
        self.assertEqual(record, stored)  # what observe returned is what was saved
        self.assertEqual((stored["status"], stored.get("cause"), stored.get("reset")),
                         ("failed", "limit", "3:10am (Europe/Moscow)"))

    def test_the_cause_survives_a_reload(self):
        self.conclude_failed([envelope("v2:204", CLAUDE_LIMIT, execution="nv2-1")])
        with self.authority() as a:  # a fresh session over the same store
            stored = decode(a.path.read_text())["runs"][0]
        self.assertEqual((runs.run_state(stored), stored.get("cause"), stored.get("reset")),
                         ("failed", "limit", "3:10am (Europe/Moscow)"))
        self.assertIn("provider limit; resets: 3:10am (Europe/Moscow)",
                      delivery.Delivery.state_text({"state": "failed", "record": stored}))

    def test_the_excerpts_are_stored_and_an_unknown_cause_is_stored_as_unknown(self):
        # Branches kept: `conclude` stores a known class (`quota`) or `unknown`; the classes themselves are `MilestoneTests`'.
        cases = [([envelope("v2:9", CODEX_CREDITS, execution="nv2-1")], "quota"),
                 ([envelope("v2:9", UNKNOWN_ERROR, execution="nv2-1")], "unknown")]
        for lines, expected in cases:
            with self.subTest(expected):
                self.setUp()
                record, _, reads, stored = self.conclude_failed(lines)
                self.assertEqual((stored.get("cause"), record.get("cause")), (expected, expected))
                self.assertNotIn("reset", stored)
                self.assertEqual(len(reads), 1)

    def test_a_403_html_body_is_never_stored_or_rendered(self):
        record, _, _, stored = self.conclude_failed([envelope("v2:9", CODEX_403, execution="nv2-1")])
        self.assertEqual(stored.get("cause"), "forbidden")
        self.assertNotIn("reset", stored)
        line = delivery.Delivery.state_text({"state": "failed", "record": stored})
        for raw in ("<html>", "<body>", "denied</body>", "workspace routing discovery", "stderr"):
            self.assertNotIn(raw, line)  # only the catalog sentence reaches the screen
        self.assertIn("[code: run.forbidden]", line)

    def test_a_token_never_reaches_the_store_or_the_line(self):
        token = "sk-" + "live-" + "0123456789ABCDEF"  # assembled so no source line is a credential literal
        record, _, _, stored = self.conclude_failed([envelope("v2:9", "Node code failed: crash: node execution "
                                                               "failed: Claude provider failure: session limit · "
                                                               "resets " + token + "; x", execution="nv2-1")])
        self.assertEqual((stored.get("cause"), "reset" in stored), ("limit", False))
        for text in (delivery.Delivery.state_text({"state": "failed", "record": stored}),
                     delivery.Delivery.state_text({"state": "failed", "record": stored})):
            self.assertNotIn(token, text)
            self.assertNotIn("resets ", text)

    def test_an_unusable_reset_keeps_the_limit_cause(self):
        """G-2 at the store: a reset the one predicate refuses is dropped whole and the cause is kept.

        Class: the reset predicate at persistence (extraction, the store and the surfaces share it). Domain: a
        failed conclude whose only limit evidence carries, in turn, a credential inside the parentheses and a value
        of 97 characters; checked values: the
        stored cause and reset and the rendered attempt line. Oracle: the cause stays `limit`, nothing is stored
        under `reset`, and the line shows the limit remedy without a reset. Interpretation: nothing is scrubbed or
        cleaned after extraction, and no token, `<`, field name or phrase survives into the store. Each of
        `reset_value`'s two refusals is one case: inside `RESET_LIMIT` but outside the time language (the
        credential), and past the limit; the other non-language values reach the same refusal."""
        token = "sk-" + "live-" + "0123456789ABCDEF"  # assembled so no source line is a credential literal
        # Branches kept: a value over the length limit, and a value inside it that the time language refuses.
        for value in ("5am (%s)" % token, long_reset(97)):
            with self.subTest(repr(value[:16])):
                self.setUp()
                message = ("Node code failed: crash: node execution failed: Claude provider failure: session limit "
                           "· resets " + value + "; x")
                _, _, reads, stored = self.conclude_failed([envelope("v2:9", message, execution="nv2-1")])
                self.assertEqual((stored.get("cause"), stored.get("reset")), ("limit", None))
                self.assertEqual(len(reads), 1)
                line = delivery.Delivery.state_text({"state": "failed", "record": stored})
                self.assertNotIn(token, line)
                self.assertIn("Provider limit; check the account limits and try again later.", line)

    def test_an_earlier_auth_failure_stays_the_stored_cause_after_a_reviewer_rejection(self):
        """A-1 at the store: an auth failure, a successful re-execution and a reviewer rejection keep the auth cause.

        Domain: one failed conclude whose read carries the auth excerpt in E1, no record for the (successful)
        re-execution, and then the reviewer's run-wide `run review_failed` completion and the id-less
        `Run failed: review_failed`; checked values: the stored cause and the rendered attempt line.
        Interpretation: run-wide records are never decisive and their words name no class, so the latest observed
        execution failure is still E1's auth failure, and the line carries it with the observational prefix."""
        _, _, reads, stored = self.conclude_failed([
            envelope("v2:1", CODEX_401, execution="E1"),
            envelope("v2:5", "Node acceptance failed: refusal: run review_failed", execution="E1"),
            envelope("v2:6", "Run failed: review_failed")])
        self.assertEqual((stored.get("cause"), stored.get("reset"), len(reads)), ("auth", None, 1))
        line = delivery.Delivery.state_text({"state": "failed", "record": stored})
        self.assertIn("Recorded in one of the executions:", line)
        self.assertIn("zplan login", line)

    def test_a_retry_diagnostic_of_the_same_execution_augments_its_store_summary(self):
        """A-1 at the store: the single provider retry's diagnostic belongs to the execution that then failed.

        Domain: one failed conclude whose read carries the retry's own provider diagnostic and, at a higher cursor
        of the same execution (and of no other one), the completion summary whose own detail is opaque; checked
        values: the stored cause and reset and the single read. Interpretation: same-execution diagnostics with a
        lower cursor are evidence, other executions' are not."""
        _, _, reads, stored = self.conclude_failed([
            envelope("v2:1", RETRY_DIAGNOSTIC, execution="nv2-3"),
            envelope("v2:6", OPAQUE_SUMMARY, execution="nv2-3"),
            envelope("v2:7", RETRY_DIAGNOSTIC, execution="nv2-2")])
        self.assertEqual((stored.get("cause"), stored.get("reset"), len(reads)),
                         ("limit", "3:10am (Europe/Moscow)", 1))

    def test_the_read_uses_the_frozen_run_once_and_never_retries_resumes_or_restarts(self):
        _, calls, reads, stored = self.conclude_failed([envelope("v2:9", CODEX_401, execution="nv2-1")])
        self.assertEqual([call[0][1] for call in calls], ["watch", "status"])  # no run/resume/force-stop/logs CLI call
        self.assertEqual(len(reads), 1)
        binding, run_id, worktree, options = reads[0]
        self.assertEqual(binding, stored["binding"])
        self.assertEqual(run_id, stored["run_id"])
        self.assertEqual(worktree, stored["worktree"])
        self.assertEqual(options, {"deadline": runs.LOG_DEADLINE, "buffer": engine.LOG_LIMIT})
        self.assertEqual((runs.LOG_DEADLINE, engine.LOG_LIMIT), (30.0, 262144))

    def test_an_incomplete_read_leaves_the_cause_unknown(self):
        for complete in (False,):
            with self.subTest(complete):
                self.setUp()
                record, _, reads, stored = self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1")],
                                                                complete=complete)
                self.assertEqual(stored.get("cause"), "unknown")
                self.assertNotIn("reset", stored)
                self.assertEqual(len(reads), 1)

    def test_a_read_that_expires_at_its_eof_or_wait_stores_unknown(self):
        """G-3/A-5 at the store: a read that expires at its EOF or at its wait keeps the cause `unknown`.

        Class: the two deadline transitions carried through a failed conclude -- an expired read never becomes
        provider evidence. Domain: `deadline_read`'s own `(lines, complete)` for both transitions (a real pipe, an
        injected clock), each fed to a failed conclude. Oracle: the store's cause is `unknown` and no `reset` is
        stored, although the retained record is perfectly readable. Interpretation: the deadline is latched at every
        transition that ends the read, so an exit is never enough by itself."""
        record = envelope("v2:9", CODEX_401, execution="nv2-1")
        for ticks in ([0.0, 0.0, 0.0, 31.0, 31.0], [0.0, 0.0, 0.0, 0.0, 0.0, 31.0, 31.0]):
            with self.subTest(ticks):
                lines, complete = deadline_read(record + "\n", ticks)
                self.assertEqual((lines, complete), ([record], False))
                self.setUp()
                _, _, reads, stored = self.conclude_failed(lines, complete=complete)
                self.assertEqual(stored.get("cause"), "unknown")
                self.assertNotIn("reset", stored)
                self.assertEqual(len(reads), 1)

    def test_a_fixture_attempt_reads_nothing(self):
        self.approve_fixture()
        reads = []
        with self.fixture_authority() as a:
            controller = self.fixture_runs(a, "failed_recoverable")
            controller.engine.log_records = lambda *args, **options: reads.append((args, options)) or ([], True)
            record = controller.observe(controller.start("M1", 1, ROLES))
        self.assertEqual((record["status"], record.get("cause")), ("failed", "unknown"))
        self.assertEqual(reads, [])

    def test_a_blocked_recovery_query_still_reads_the_diagnosis(self):
        # G-3: the required single diagnosis read does not depend on the recovery status being readable.
        _, calls, reads, stored = self.conclude_failed([envelope("v2:9", CODEX_401, execution="nv2-1")],
                                                        status=Blocked("socket"))
        self.assertEqual((stored["status"], stored.get("cause"), stored["recoverable"]), ("failed", "auth", None))
        self.assertEqual([call[0][1] for call in calls], ["watch", "status"])
        self.assertEqual(len(reads), 1)

    def test_a_conflicting_cursor_at_the_store_is_unknown(self):
        """G-1/A-6 at the store: two records that share a cursor and disagree make the whole result unknown.

        Class: G-1's conflict rule through persistence. Domain: one failed conclude whose read carries the limit
        excerpt and the 403 excerpt under the same cursor; checked values: the stored cause, the reset and the single
        read. Oracle: the result is unknown and no reset is stored, although both records are readable -- the pair
        cannot be ordered. Interpretation: the conflict covers the error records that name an execution, and it is
        decided before any class is read."""
        _, _, reads, stored = self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1"),
                                                    envelope("v2:9", CODEX_403, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), stored.get("reset"), len(reads)), ("unknown", None, 1))

    def test_a_non_enum_code_at_the_store_is_unknown(self):
        """G-1/A-6 at the store: only the engine's four error codes make a completion summary.

        Class: the closed code enum through persistence. Domain: one failed conclude whose read carries a
        `Node ... failed:` record with a code outside timeout|crash|malformed|refusal but a readable provider
        detail; checked values: the stored cause and the single read. Oracle: the record is no completion, so the
        result is unknown rather than the class its own detail names."""
        message = ("Node code failed: declared_failure: node execution failed: Codex provider failure: "
                   "unexpected status 403 Forbidden")
        _, _, reads, stored = self.conclude_failed([envelope("v2:9", message, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), len(reads)), ("unknown", 1))

    def test_records_that_share_a_cursor_and_differ_in_their_target_are_unknown(self):
        """G-1's identical-record requirement through persistence: the record's payload, not its message, decides.

        Class: G-1's conflict rule (whole-record identity). Domain: one failed conclude whose read carries the same
        cursor, execution and message twice while only `record.target` differs; checked values: the stored cause,
        the stored reset and the single read. Oracle: the pair is not one duplicate record, so the result is
        unknown and no reset is stored. Interpretation: the durable fields of the payload are what makes two lines
        the same record (the reviewers rejected the identity of execution and message alone)."""
        _, _, reads, stored = self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1"),
                                                    envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1", target="codex")])
        self.assertEqual((stored.get("cause"), stored.get("reset"), len(reads)), ("unknown", None, 1))

    def test_records_that_share_a_cursor_and_differ_in_their_timestamp_are_unknown(self):
        """G-1's identical-record requirement through persistence: a rewritten record is not the same record.

        Class: G-1's conflict rule (whole-record identity). Domain: one failed conclude whose read carries the same
        cursor, execution, level and message twice while only the envelope's `timestamp` differs; checked values:
        the stored cause, the stored reset and the single read. Oracle: unknown, with nothing stored under
        `reset`, because the two lines are not the identical duplicate the ledger may repeat."""
        _, _, reads, stored = self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1"),
                                                    envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1",
                                                             timestamp=1791935230935)])
        self.assertEqual((stored.get("cause"), stored.get("reset"), len(reads)), ("unknown", None, 1))

    def test_a_null_reset_beside_a_limit_cause_is_refused(self):
        """G-2's store validation: a present reset must be a string the predicate accepts, and null is not.

        Class: G-2's store predicate. Domain: a stored limit record whose `reset` key is present and holds JSON
        null (the forgery the reviewers reproduced), reloaded through the authority; checked values: the load
        raises `Blocked` and the same file without the key still loads. Oracle: the presence of the key is what is
        checked, so the predicate's None -- which means "no usable reset" -- can never satisfy a present value;
        the optional pair stays optional (absent is valid) and never accepts a non-string."""
        _, _, _, stored = self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), stored.get("reset")), ("limit", "3:10am (Europe/Moscow)"))
        with self.authority() as a:
            state = decode(a.path.read_text())
            path = a.path
        forged = copy.deepcopy(state)
        forged["runs"][0]["reset"] = None
        path.write_text(canonical(forged) + "\n")
        with self.assertRaises(Blocked):
            with self.authority():
                pass
        without = copy.deepcopy(state)
        without["runs"][0].pop("reset")
        path.write_text(canonical(without) + "\n")
        with self.authority():
            pass

    def test_an_unusable_cursor_does_not_break_the_failed_conclude(self):
        # G-1/A-3: a hostile cursor is unusable, not fatal -- conclude still persists the diagnosis (unknown).
        _, _, reads, stored = self.conclude_failed([envelope("v2:" + "9" * 5000, CODEX_403, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), len(reads)), ("unknown", 1))

    def test_a_pathologically_nested_line_does_not_break_the_conclude(self):
        # A-3: a line whose decoder recursion fails is not a record; the conclude still persists the diagnosis from
        # the readable line and never aborts.
        deep = '{"cursor": "v2:1", "record": ' + "[" * 10000
        _, _, reads, stored = self.conclude_failed([deep, envelope("v2:9", CODEX_401, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), len(reads)), ("auth", 1))

    def test_the_store_rejects_a_forged_cause_and_a_bad_reset(self):
        """G-2's store validation: an optional cause from the closed enum and an optional reset the predicate
        accepts only beside `limit`."""
        self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1")])
        with self.authority() as a:
            good = decode(a.path.read_text())
            path = a.path
        forgeries = {
            "cause outside the enum": lambda s: s["runs"][0].update(cause="surprise"),
            "cause not a string": lambda s: s["runs"][0].update(cause=7),
            "reset without a limit cause": lambda s: s["runs"][0].update(cause="quota", reset="5:00am"),
            "reset without a cause": lambda s: (s["runs"][0].pop("cause", None), s["runs"][0].update(reset="5:00am")),
            "reset outside the language": lambda s: s["runs"][0].update(reset="soon"),
            "reset with a credential": lambda s: s["runs"][0].update(reset="5am (token=x)"),
            "overlong reset": lambda s: s["runs"][0].update(reset=long_reset(97)),
            "empty reset": lambda s: s["runs"][0].update(reset=""),
            "reset that is not a string": lambda s: s["runs"][0].update(reset=7),
            "null reset": lambda s: s["runs"][0].update(reset=None),
        }
        for name, mutate in forgeries.items():
            with self.subTest(name):
                state = copy.deepcopy(good)
                mutate(state)
                path.write_text(canonical(state) + "\n")
                with self.assertRaises(Blocked):
                    with self.authority():
                        pass
        path.write_text(canonical(good) + "\n")
        with self.authority() as a:
            self.assertEqual(decode(a.path.read_text())["runs"][0].get("cause"), "limit")

    def test_a_valid_reset_of_each_shape_is_accepted_by_the_store(self):
        """Interpretation: the store keeps a reset the one predicate accepts, whole; the predicate's own shapes are
        `ResetTests`' (and the other tests of this class store a clock time with minutes and a zone), so the store
        needs the longest value the limit allows (96 characters), the one value where the store's and the
        extractor's length checks could differ."""
        # Branches kept: a reset exactly at `RESET_LIMIT` is stored whole.
        value = long_reset(96)
        message = "Node code failed: crash: node execution failed: Claude provider failure: session limit · resets " + value
        _, _, _, stored = self.conclude_failed([envelope("v2:9", message, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), stored.get("reset")), ("limit", value))

    def test_a4_the_stored_cause_of_generated_sequences_matches_the_oracle(self):
        """A-4 through the store: the fixed-seed sequences of `GeneratorTests` concluded and persisted, checked
        against the same independent oracle of G-1/G-2 (the in-memory check only exercises the extractor).

        Class checked: a mutation that makes `MilestoneRuns.failure_cause` always return `(None, None)` -- the
        diagnosis reaching the store -- fails here for the first known class, while the in-memory test still passes.
        Domain: the same 20 sequences; one `conclude` and one read per sequence. Interpretations: the class is
        compared after `unknown` is normalized (a record without a cause means unknown), and the record is put back
        to `running` between cases, which is exactly the state a failed conclude starts from."""
        cases = list(GeneratorTests().cases())
        record = self.started()
        holder, reads = {}, []
        with self.authority() as a:
            driver, calls = self.driver([self.status(record, {"recoverable": False})] * len(cases))
            driver.log_records = lambda binding, run_id, cwd, **options: reads.append(1) or (list(holder["lines"]), True)
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            stored = controller.runs[0]
            for lines, expected in cases:
                stored.update(status="running", terminal=None, outcome=None, recoverable=None)
                stored.pop("cause", None)
                stored.pop("reset", None)
                holder["lines"] = lines
                controller.conclude(stored, {"status": "failed", "reason": "review_failed"})
                with self.subTest(expected):
                    self.assertEqual((stored.get("cause"), stored.get("reset")), (expected[0] or "unknown", expected[1]),
                                     "\n".join(lines))
        self.assertEqual(len(reads), len(cases))


class DisplayTests(ReaderScript, RunsTest):
    """R-5/A-2: both surfaces show the cause and its remedy; unknown keeps today's text; the cause survives a reload."""

    REMEDY = {"limit": "provider limit; resets: 3:10am (Europe/Moscow)", "quota": "top up the account",
              "auth": "zplan login", "forbidden": "check the account or region", "network": "try again later"}
    EXCERPT = {"limit": CLAUDE_LIMIT, "quota": CODEX_CREDITS, "auth": CODEX_401, "forbidden": CODEX_403,
               "network": ("Node code failed: crash: node execution failed: Codex provider failure: connection "
                           "refused (ECONNREFUSED)")}

    def conclude_failed(self, lines=(), complete=True, recovery=None):
        r = self.started()
        with self.authority() as a:
            driver, calls, reads = self.script([(self.finished(r, reason="review_failed"),),
                                                self.status(r, recovery or {"recoverable": False})], lines, complete)
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            record = controller.observe(controller.active())
            stored = copy.deepcopy(decode(a.path.read_text())["runs"][0])
        return record, reads, stored

    def ended(self, record):
        with self.authority() as a:
            controller = MilestoneRuns(a, None, worktrees=self.worktrees)
            return delivery.Delivery(a, controller, None).end(record)

    def test_both_surfaces_show_the_cause_and_its_remedy_for_failed_and_failed_recoverable(self):
        for recoverable, state in ((False, "failed"), (True, "failed_recoverable")):
            with self.subTest(state):
                self.setUp()
                record, reads, stored = self.conclude_failed([envelope("v2:9", CLAUDE_LIMIT, execution="nv2-1")],
                                                             recovery={"recoverable": recoverable})
                self.assertEqual(runs.run_state(stored), state)
                line = delivery.Delivery.state_text({"state": state, "record": stored})
                self.assertTrue(line.startswith(delivery.STATE_TEXT[state]), line)
                self.assertIn("Recorded in one of the executions:", line)
                self.assertIn("provider limit; resets: 3:10am (Europe/Moscow)", line)
                self.assertIn("[code: run.limit]", line)
                view = self.ended(stored)
                self.assertEqual(view.state, state)
                body = "\n".join(view.body)
                self.assertIn("Reason: «review_failed»", body)
                self.assertIn("Recorded in one of the executions:", body)
                self.assertIn("provider limit; resets: 3:10am (Europe/Moscow)", body)
                self.assertIn("[code: run.limit]", body)
                if state == "failed_recoverable":
                    self.assertIn("[g] continue resumes the same attempt", body)

    def test_every_class_shows_its_own_remedy_and_only_the_reset(self):
        for cause, remedy in self.REMEDY.items():
            with self.subTest(cause):
                self.setUp()
                _, _, stored = self.conclude_failed([envelope("v2:9", self.EXCERPT[cause], execution="nv2-1")])
                self.assertEqual(stored.get("cause"), cause)
                line = delivery.Delivery.state_text({"state": "failed", "record": stored})
                self.assertTrue(line.startswith(delivery.STATE_TEXT["failed"] + " · "), line)
                self.assertIn("Recorded in one of the executions:", line)
                self.assertIn(remedy, line)
                self.assertIn("[code: run.%s]" % cause, line)
                self.assertNotIn("<html>", line)  # the 403 HTML body never reaches the line
                self.assertNotIn("\n", line)

    def test_an_unusable_reset_reaches_neither_surface(self):
        """G-2/R-5 on both surfaces: a stored reset the predicate refuses is not rendered; the limit line is.

        Domain: the attempt line and the end view's body for a failed conclude whose only limit evidence carries a
        credential inside the parentheses; checked values: the two rendered texts. Interpretation: both surfaces
        apply the one reset predicate, so the limit remedy is shown without a reset."""
        token = "sk-" + "live-" + "0123456789ABCDEF"  # assembled so no source line is a credential literal
        _, _, stored = self.conclude_failed([envelope("v2:9", "Node code failed: crash: node execution failed: "
                                                      "Claude provider failure: session limit · resets 5am (%s)"
                                                      % token, execution="nv2-1")])
        self.assertEqual((stored.get("cause"), stored.get("reset")), ("limit", None))
        body = "\n".join(self.ended(stored).body)
        for text in (delivery.Delivery.state_text({"state": "failed", "record": stored}), body):
            self.assertNotIn(token, text)
            self.assertIn("Provider limit; check the account limits and try again later.", text)
            self.assertIn("[code: run.limit]", text)

    def test_an_out_of_band_reset_is_never_rendered(self):
        # The store writes only values the predicate accepts, so this record is forged on disk: rendering refuses
        # the value on its own and keeps the limit line.
        record = {"status": "failed", "cause": "limit", "reset": '{"token sk-ABC":"x"}', "terminal": {"reason": "r"}}
        line = delivery.Delivery.state_text({"state": "failed", "record": record})
        self.assertNotIn("sk-ABC", line)
        self.assertIn("Provider limit; check the account limits and try again later.", line)
        self.assertEqual(delivery.cause_line(record), "Recorded in one of the executions: Provider limit; "
                                                      "check the account limits and try again later. [code: run.limit]")

    def test_the_attempt_line_shows_the_cause_through_an_entry_point_the_base_also_has(self):
        # A-6's behavioural regression: `Delivery.state_text` already existed on the base, so this reaches its
        # assertion there and fails at it (today's failed text carries no cause) instead of raising on a new name.
        _, _, stored = self.conclude_failed([envelope("v2:9", CODEX_401, execution="nv2-1")])
        line = delivery.Delivery.state_text({"state": "failed", "record": stored})
        self.assertIn("Recorded in one of the executions:", line)
        self.assertIn("The service rejected the authorization; [l] refresh login (`zplan login`) and retry the attempt.", line)

    def test_unknown_shows_todays_text_unchanged_on_both_surfaces(self):
        _, _, stored = self.conclude_failed([envelope("v2:9", UNKNOWN_ERROR, execution="nv2-1")])
        self.assertEqual(stored.get("cause"), "unknown")
        self.assertEqual(delivery.Delivery.state_text({"state": "failed", "record": stored}),
                         delivery.STATE_TEXT["failed"])
        self.assertEqual(list(self.ended(stored).body), ["  Reason: «review_failed»"])

    def test_the_cause_line_helper_tolerates_a_missing_record(self):
        # Supplementary (the R-5 helper itself): an absent or unknown cause renders nothing.
        self.assertEqual(delivery.cause_line({"cause": "unknown"}), "")
        self.assertEqual(delivery.cause_line(None), "")
        self.assertEqual(delivery.cause_line({}), "")


class GeneratorTests(unittest.TestCase):
    """A-4: a bounded generator (fixed seed, 20 cases) checked against an oracle independent of the G-1/G-2 helpers.

    Interpretations recorded for the reviewers:

    * the oracle is written from the plant -- every record knows the class, the run-wide flag and the reset the
      generator put in it -- and never from `engine.classify`/`engine.observed_cause`, so a shared misreading of the
      text cannot hide on both sides;
    * the checked domain is a sequence of 0..7 error records over two or three execution ids plus the run-wide
      id-less record: the five classes, an opaque provider detail, a declared completion, the engine's four reasons,
      the class-bearing run-wide reason (`run quota_exhausted`, `run authentication_required`, `run forbidden_access`)
      that names no class, a plain completion whose cause is not the engine's provider diagnostic, an info record,
      the run-wide `Run failed: <reason>` record, an identical duplicate, a conflict sharing a cursor and an
      unusable cursor;
    * the conflict and the unusable cursor make the whole result unknown even when a class is readable beside them,
      which is G-1's own wording ("the whole result is unknown")."""

    ORDER = ("limit", "quota", "forbidden", "auth", "network")
    DETAIL = {"limit": "Claude provider failure: You've hit your session limit · resets %s",
              "quota": "Codex provider failure: Your workspace is out of credits. Ask your workspace owner to refill.",
              "forbidden": "Codex provider failure: unexpected status 403 Forbidden: <html><body>denied</body></html>",
              "auth": "Codex provider failure: workspace routing discovery unauthorized (401)",
              "network": "Codex provider failure: connection refused (ECONNREFUSED)"}
    OPAQUE = "Codex provider failure: the workspace rules file could not be read"
    RESETS = ("3:10am (Europe/Moscow)", "Oct 20, 5am (UTC)", "5am", "12:59pm")
    BAD_RESETS = ("5am (token=x)", "wait a moment", "5:00am\x9b", "1am (" + "A" * 200 + "/B/C)")

    def cases(self, count=20):
        rng = random.Random(20261019)  # a fixed seed: the same 20 cases on every run
        for _ in range(count):
            yield self.case(rng)

    def test_a4_generated_sequences_match_the_oracle(self):
        seen = set()
        for lines, expected in self.cases():
            with self.subTest(expected):
                self.assertEqual(engine.observed_cause(lines), expected, "\n".join(lines))
            seen.add(expected[0])
        self.assertEqual(seen, {None} | set(self.ORDER))

    def case(self, rng):
        executions = ["nv2-%d" % n for n in range(1, rng.randint(2, 3) + 1)]
        planted, cursor = [], 1

        def add(cursor, kind):
            planted.append(self.plant(cursor, rng.choice(executions), kind, rng))

        for _ in range(rng.randint(0, 3)):
            add(cursor, rng.choice(("diagnostic", "diagnostic", "provider", "run_wide", "plain", "idless", "info")))
            cursor += rng.randint(1, 4)
        end = rng.choice(("provider", "provider", "provider", "declared", "reason", "run_wide", "absent"))
        if end != "absent":
            add(cursor, end)
            cursor += 2
        for _ in range(rng.randint(0, 2)):
            add(cursor, rng.choice(("diagnostic", "run_wide", "info", "idless")))
            cursor += 1
        if planted and rng.random() < 0.2:  # an identical duplicate record
            planted.append(copy.deepcopy(rng.choice(planted)))
        if planted and rng.random() < 0.2:  # a record that conflicts with another one's cursor
            victim = rng.choice(planted)
            other = self.plant(victim["cursor"], rng.choice(executions), "provider", rng)
            if other["message"] != victim["message"]:
                planted.append(other)
        if planted and rng.random() < 0.1:  # a cursor the ledger cannot order
            rng.choice(planted)["cursor"] = None
        lines = [envelope(None if item["cursor"] is None else "v2:%d" % item["cursor"], item["message"],
                          level=item["level"], execution=item["execution"]) for item in planted]
        return lines, self.oracle(planted)

    def plant(self, cursor, execution, kind, rng):
        """One planted record: its own text and the meaning the generator put in it, for the oracle alone."""
        node = rng.choice(("code", "worker", "acceptance", "acceptance_review"))
        item = {"cursor": cursor, "execution": execution, "level": "error", "kind": kind, "class": None, "reset": None,
                "reason": None}
        if kind == "provider":
            item["class"] = rng.choice(self.ORDER + (None,))
            detail = self.OPAQUE
            if item["class"] is not None:
                detail = self.DETAIL[item["class"]]
                if item["class"] == "limit":
                    value = rng.choice(self.RESETS + self.BAD_RESETS)
                    detail = detail % value
                    item["reset"] = value if value in self.RESETS else None
            item["message"] = "Node %s failed: %s after 12.3s: node execution failed: %s" % (
                node, rng.choice(("crash", "timeout", "malformed", "refusal")), detail)
        elif kind == "diagnostic":
            item["class"] = rng.choice(self.ORDER + (None,))
            detail = self.OPAQUE
            if item["class"] is not None:
                detail = self.DETAIL[item["class"]]
                if item["class"] == "limit":
                    value = rng.choice(self.RESETS + self.BAD_RESETS)
                    detail = detail % value
                    item["reset"] = value if value in self.RESETS else None
            item["message"] = detail
        elif kind == "declared":
            item["message"] = "Node %s failed: refusal after 3.0s" % node
        elif kind == "reason":
            item["reason"] = rng.choice((": policy denied", ": interactive input required", ": authentication required",
                                         ": result did not match the node contract"))
            tail = ""
            if rng.random() < 0.5:  # a provider detail after the engine's own reason: the reason still decides
                cls = rng.choice(self.ORDER)
                tail = ": node execution failed: " + (self.DETAIL[cls] % rng.choice(self.RESETS) if cls == "limit"
                                                      else self.DETAIL[cls])
            item["message"] = "Node %s failed: malformed after 1.0s%s%s" % (node, item["reason"], tail)
        elif kind == "run_wide":
            item["message"] = "Node %s failed: crash: run %s" % (node, rng.choice(
                ("review_failed", "quota_exhausted", "authentication_required", "forbidden_access")))
        elif kind == "plain":
            item["message"] = "Node %s failed: crash: node execution failed: task input file could not be read" % node
        elif kind == "idless":
            item["execution"] = None
            item["message"] = "Run failed: %s" % rng.choice(("review_failed", "quota_exhausted"))
        elif kind == "info":
            item["level"] = "info"
            item["message"] = "Claude provider failure: You've hit your session limit · resets 3am"
        return item

    def oracle(self, planted):
        """G-1/G-2 from the plant alone: the decisive completion, its evidence, the class and the reset."""
        # The identity of a record is the whole line this corpus builds from the item: its level, cursor, execution
        # and message (every other field of the envelope is fixed here), never the message alone (G-1).
        records = [item for item in planted if item["level"] == "error" and item["execution"]]
        if any(item["cursor"] is None for item in records):
            return None, None  # an error record that names an execution and cannot be ordered
        identities, unique = {}, {}
        for item in records:
            identity = (item["level"], item["cursor"], item["execution"], item["message"])
            if item["cursor"] in identities and identities[item["cursor"]] != identity:
                return None, None  # conflicting records sharing a cursor
            identities[item["cursor"]] = identity
            unique.setdefault(item["cursor"], item)
        decisive = None
        for item in unique.values():
            if item["kind"] not in ("provider", "declared", "plain", "reason"):
                continue  # not a completion (the run-wide `run <reason>` record is never decisive)
            if decisive is None or item["cursor"] > decisive["cursor"]:
                decisive = item
        if decisive is None:
            return None, None
        if decisive["kind"] == "reason":
            return ("auth", None) if decisive["reason"] == ": authentication required" else (None, None)
        if decisive["kind"] in ("declared", "plain"):
            return None, None  # no cause, or one that is not the engine's provider diagnostic
        evidence = [(decisive["cursor"], decisive["class"], decisive["reset"])]
        for item in unique.values():
            if item["kind"] == "diagnostic" and item["execution"] == decisive["execution"] \
                    and item["cursor"] < decisive["cursor"]:
                evidence.append((item["cursor"], item["class"], item["reset"]))
        found = {entry[1] for entry in evidence if entry[1] is not None}
        winning = next((name for name in self.ORDER if name in found), None)
        if winning is None:
            return None, None
        latest = max((entry for entry in evidence if entry[1] == winning), key=lambda entry: entry[0])
        return winning, latest[2] if winning == "limit" else None


class ReadBoundaryTests(unittest.TestCase):
    """G-3: at the CLI boundary a bounded read follows the frozen binding's state root, not the current engine's."""

    # NativeEngine resolves its executable; /bin/true is a symlink into /usr/bin on merged-/usr Linux hosts.
    TRUE = str(Path("/bin/true").resolve())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.current = self.root / "current"
        self.frozen = self.root / "frozen"

    def capture(self, binding):
        seen = []
        reader = lambda argv, env, cwd, **options: seen.append((argv, dict(env), cwd)) or ([], True)
        # The socket-path admission of the frozen root is a precondition of the read, not its subject.
        with patch.object(engine, "check_socket_path", lambda root: 0), patch.object(live, "records", reader):
            self.assertEqual(engine.NativeEngine(self.TRUE, self.current).log_records(binding, "m-run", self.root),
                             ([], True))
        return seen[0]

    def test_the_read_runs_in_the_frozen_state_root_not_the_current_one(self):
        binding = {"executable": self.TRUE, "state_root": str(self.frozen), "sha256": "0" * 64,
                   "version": toolchain.current().zeroshot_version}
        argv, env, cwd = self.capture(binding)
        self.assertEqual(env["ZEROSHOT_STATE_DIR"], str(self.frozen / "runs"))
        self.assertEqual(env["ZEROSHOT_CONFIG_DIR"], str(self.frozen / "config"))
        self.assertEqual(argv[1:2], ["logs"])
        self.assertEqual(cwd, str(self.root))

    def test_a_binding_of_the_current_root_keeps_the_current_engine(self):
        binding = {"executable": self.TRUE, "state_root": str(self.current), "sha256": "0" * 64,
                   "version": toolchain.current().zeroshot_version}
        argv, env, cwd = self.capture(binding)
        self.assertEqual(env["ZEROSHOT_STATE_DIR"], str(self.current / "runs"))

    def capture_execution(self, binding, execution):
        seen = []
        reader = lambda argv, env, cwd, **options: seen.append(argv) or ([], True)
        with patch.object(engine, "check_socket_path", lambda root: 0), patch.object(live, "records", reader):
            self.assertEqual(engine.NativeEngine(self.TRUE, self.current).log_records(
                binding, "m-run", self.root, execution=execution), ([], True))
        return seen[0]

    def test_the_execution_option_appends_one_execution_ref(self):
        # C3a/A2: `log_records(..., execution=ref)` reads `logs RUN --execution REF`; without it the whole run.
        binding = {"executable": self.TRUE, "state_root": str(self.current), "sha256": "0" * 64,
                   "version": toolchain.current().zeroshot_version}
        self.assertEqual(self.capture_execution(binding, "e2")[1:], ["logs", "m-run", "--execution", "e2"])


class PlannerCauseTests(unittest.TestCase):
    """R-1/R-2: the planner renders the shared classes with its own families and wording (the journeys live in test_ux)."""

    def test_an_info_envelope_on_either_stream_is_not_a_planner_cause(self):
        """R-1 for the planner path: the planner reads the shared extractor, so model output is not evidence.

        Domain: `engine.error_lines`+`engine.classify` with the envelope on stdout, on stderr and on both, plus an
        error envelope as the positive control. Interpretation: the same level filter the extractor applies, so a
        debug/info envelope leaves the planner cause unknown instead of rendering planner.auth."""
        info = envelope("v2:1", "model example: 401 Unauthorized", level="info")
        debug = envelope("v2:2", "Claude rate limit: status=allowed_warning", level="debug")
        self.assertIsNone(engine.classify("\n".join(engine.error_lines("", info + "\n"))))
        self.assertIsNone(engine.classify("\n".join(engine.error_lines(info + "\n", ""))))
        self.assertIsNone(engine.classify("\n".join(engine.error_lines(debug + "\n", debug + "\n"))))
        error = envelope("v2:3", "provider error: 401 Unauthorized")
        self.assertEqual(engine.classify("\n".join(engine.error_lines("", error + "\n"))), "auth")

    def test_a_flat_structured_info_record_is_not_a_planner_cause(self):
        """R-1 for the planner path: a flat structured non-error record is not evidence.

        Domain: `engine.error_lines`+`engine.classify` with a flat `{"level": "info"|"debug"|"system"}` record on
        stderr and on stdout, plus a flat error record as the positive control. Interpretation: the level filter is
        shared with the native path, so the planner sees no cause instead of rendering planner.auth."""
        for level in ("info", "debug", "system"):
            with self.subTest(level):
                record = canonical({"level": level, "message": "Model example: 401 Unauthorized"})
                self.assertIsNone(engine.classify("\n".join(engine.error_lines("", record + "\n"))))
                self.assertIsNone(engine.classify("\n".join(engine.error_lines(record + "\n", ""))))
        error = canonical({"level": "error", "message": "provider error: 401 Unauthorized"})
        self.assertEqual(engine.classify("\n".join(engine.error_lines("", error + "\n"))), "auth")

    def test_a_flat_model_record_with_an_error_field_is_not_a_planner_cause(self):
        """R-1 for the planner path: a declared model/info kind wins over an `error` field.

        Domain: `engine.error_lines`+`engine.classify` with a flat message record carrying `error: 401 ...` on
        stderr and on stdout, plus the legacy kind-less `error` record as a positive control. Interpretation: the
        planner reads the shared extractor, so a record's own declared kind decides and no remedy is rendered."""
        text = canonical({"type": "message", "role": "assistant", "error": "401 Unauthorized"})
        self.assertIsNone(engine.classify("\n".join(engine.error_lines("", text + "\n"))))
        self.assertIsNone(engine.classify("\n".join(engine.error_lines(text + "\n", ""))))
        legacy = canonical({"error": "401 Unauthorized"})
        self.assertEqual(engine.classify("\n".join(engine.error_lines("", legacy + "\n"))), "auth")

    CASES = (("limit", "quota", "planner.quota", "the service rejected the request because of a limit or quota"),
             ("forbidden", "auth", "planner.auth", "the service rejected the authorization"))

    def test_the_planner_normalizes_limit_and_forbidden_into_its_own_classes(self):
        """R-2 through `Planning.failure`: the shared extra classes render as the planner's own screen (A-6).

        Domain: `Planning.failure` over a failed revision whose engine reports each raw shared cause, checked
        through the returned `PlanView` -- `.cause`, `.family`, the rendered wording and the action list. Oracle:
        the raw cause -> (planner cause, family, wording) table written out below, independent of
        `planning.PLANNER_CAUSE`; the mutation that drops the normalization renders both classes as
        `planner.unknown`, which this case catches. Interpretations: `limit` is the planner's `quota` and
        `forbidden` its `auth`; the planner keeps its own families and wording, offers no login action for a limit
        while `forbidden`/`auth` insert `login`, and never shows a reset."""
        cases = self.CASES + (("auth", "auth", "planner.auth", "the service rejected the authorization"),
                              ("quota", "quota", "planner.quota", "the service rejected the request because of a limit or quota"),
                              ("network", "network", "planner.network", "no connection to the model service"),
                              (None, None, "planner.unknown", "the cause is unknown"))
        for raw, cause, family, wording in cases:
            with self.subTest(raw):
                view = self.planner_failure(raw)
                self.assertEqual((view.cause, view.family), (cause, family))
                text = "\n".join(view.lines)
                self.assertIn(wording, text)
                self.assertIn("[code: %s]" % family, text)
                self.assertEqual("login" in view.actions, cause == "auth")

    def test_the_planner_cause_mapping_is_the_documented_one(self):
        """R-2's mapping as data: the two extra classes normalize into the planner's own names.

        Domain: `planning.PLANNER_CAUSE`/`PLANNER_FAMILY` themselves; interpretation: `limit` -> `quota`,
        `forbidden` -> `auth`, and every shared class has a planner family."""
        from terminal_planner import planning
        self.assertEqual(planning.PLANNER_CAUSE, {"limit": "quota", "forbidden": "auth"})
        self.assertEqual(set(planning.PLANNER_FAMILY) - {None}, {name for name, _ in engine.CAUSES})
        cases = [(raw, cause, family) for raw, cause, family, _ in self.CASES]
        for raw, cause, family in cases + [("auth", "auth", "planner.auth"), ("quota", "quota", "planner.quota"),
                                           ("network", "network", "planner.network")]:
            with self.subTest(raw):
                self.assertEqual(planning.PLANNER_CAUSE.get(raw, raw), cause)
                self.assertEqual(planning.PLANNER_FAMILY[cause], family)

    @staticmethod
    def planner_failure(raw):
        """The view `Planning.failure` renders for a failed revision whose engine reports `raw` as the cause."""
        from terminal_planner import planning
        report = type("Report", (), {"failure_cause": staticmethod(lambda authority: raw)})()
        plan = planning.Planning(None, None, lambda name, terminal: report)
        return plan.failure({"version": 1, "status": "run_failed", "engine": "native", "run_id": None,
                             "diagnostic": "plan_verifier_failed"}, "Цель")

    def test_a_native_envelope_reaches_the_planner_classifier(self):
        # The planner reads bounded logs and flattens them: a native envelope is classified like a flat line.
        text = envelope("v2:1", "Codex provider failure: unexpected status 403 Forbidden", level="error")
        self.assertEqual(engine.classify("\n".join(engine.error_lines(text, ""))), "forbidden")

    def test_a_native_envelope_with_a_non_error_level_is_not_read_by_the_planner(self):
        """G-1 for the planner path: the engine's envelope level is the literal `error`, not any error-like word.

        Class: G-1's level rule in the planner extraction (R-1's flat formats stay unchanged). Domain:
        `engine.error_lines`+`engine.classify` with a native envelope whose `record.level` is `fatal`, `err`,
        `ERROR`, `warn` or `info` and whose message is a bare `401 Unauthorized` (the shape the reviewers showed
        rendering planner.auth), on stdout and on stderr; plus the literal `error` envelope as the positive
        control and the flat legacy `{"level": "fatal"}` record as the flat control. Oracle: no envelope level but
        the literal `error` is evidence, so the planner cause stays unknown on either stream, while the literal
        error envelope and the legacy flat error record still classify. Interpretation: the native envelope is the
        engine's own record, so only its own error level counts -- `fatal` and `err` remain error markers of the
        *flat* formats, whose behaviour this change leaves untouched."""
        for level in ("fatal", "err", "ERROR", "Error", "warn", "info", "FATAL"):
            with self.subTest(level):
                for stdout, stderr in ((envelope("v2:1", "401 Unauthorized", level=level) + "\n", ""),
                                       ("", envelope("v2:2", "401 Unauthorized", level=level) + "\n")):
                    self.assertIsNone(engine.classify("\n".join(engine.error_lines(stdout, stderr))))
        error = envelope("v2:3", "provider error: 401 Unauthorized", level="error")
        self.assertEqual(engine.classify("\n".join(engine.error_lines(error + "\n", ""))), "auth")
        flat = canonical({"level": "fatal", "message": "provider error: 401 Unauthorized"})
        self.assertEqual(engine.classify("\n".join(engine.error_lines("", flat + "\n"))), "auth")


class FaultCauseWordsTests(ReaderScript, RunsTest):
    """Fault case "the run ended with an engine failure": the owner reads which role failed, plus the next key.

    A node the engine fails ends the run with the terminal reason `<node>_failed`, stored as the record's
    diagnostic (runs.py `conclude`); `Delivery.reason` (delivery.py:878) renders it. Interpretations recorded
    here, as the worker's summary never reaches a reviewer:

    * A1's "<node>_failed" is matched on the *raw* diagnostic (=== the plain text only when nothing is stripped),
      never on `plain()`'s output: `plain` drops the `; manifest: …` suffix that runs.py appends to normal blocked
      outcomes, so matching after it would expand A1 to diagnostics that are not exactly `<node>_failed`. `plain`
      stays in use for the existing fallback rendering only (regression: `test_a_suffixed_known_node_failure_is_unchanged`).
    * A1's `<node>` is `live.base(node)` (a graph-path prefix and an `empty_` variant prefix are stripped), the
      same normalization `live.role` uses; the trailing code is the raw diagnostic, unquoted.
    * A2's "exactly as today" is byte for byte: an unknown node, free text, the empty diagnostic and a `<node>_failed`
      with any suffix all keep the present line (quoted, or the "not given" fallback)."""

    def ended(self, reason, recovery=None):
        """The body of the end view of a run that failed with the terminal `reason` (and a fixed recovery read)."""
        r = self.started()
        with self.authority() as a:
            driver, calls, reads = self.script([(self.finished(r, reason=reason),),
                                                self.status(r, recovery or {"recoverable": False})])
            controller = MilestoneRuns(a, driver, worktrees=self.worktrees)
            controller.observe(controller.active())
            stored = copy.deepcopy(decode(a.path.read_text())["runs"][0])
        with self.authority() as a:
            delivery_service = delivery.Delivery(a, MilestoneRuns(a, None, worktrees=self.worktrees), None)
            return delivery_service.end(stored).body

    def test_a_known_node_failure_names_the_role_and_keeps_the_code(self):
        # A1: `<node>_failed` for a node whose `live.base` is a role reads as the role word plus the code.
        for reason, role in (("acceptance_review_failed", "acceptance"), ("code_review_failed", "code review"),
                             ("empty_acceptance_review_failed", "acceptance")):
            with self.subTest(reason):
                self.setUp()
                body = self.ended(reason)
                self.assertEqual(body[0], "  Reason: the %s step gave no answer (timeout, failure or invalid answer) — %s"
                                 % (role, reason))
                self.assertNotIn("«%s»" % reason, body[0])

    def test_any_other_diagnostic_is_unchanged(self):
        # A2: an unknown node, free text and the empty diagnostic keep today's line, byte for byte.
        service = delivery.Delivery(None, None, None)
        for diagnostic, expected in (("foo_failed", "  Reason: «foo_failed»"),
                                     ("review_failed", "  Reason: «review_failed»"),
                                     ("engine stopped early", "  Reason: «engine stopped early»"),
                                     ("", "  Reason: not given; details — [i] on the main screen")):
            with self.subTest(diagnostic):
                self.assertEqual(service.reason({"diagnostic": diagnostic}), expected)

    def test_a_suffixed_known_node_failure_is_unchanged(self):
        # Regression (A2): a `<node>_failed` diagnostic carrying the manifest suffix runs.py adds to blocked
        # outcomes is not exactly `<node>_failed`, so it keeps today's line; `plain` still strips the suffix.
        # See the class docstring: matching must use the raw diagnostic, never `plain()`'s output.
        service = delivery.Delivery(None, None, None)
        for diagnostic, expected in (
                ("acceptance_review_failed; manifest: manifest unavailable", "  Reason: «acceptance_review_failed»"),
                ("acceptance_review_failed; manifest: missing manifest", "  Reason: «acceptance_review_failed»"),
                ("code_review_failed; manifest: manifest unavailable", "  Reason: «code_review_failed»"),
                ("acceptance_review_failed ", "  Reason: «acceptance_review_failed»")):
            with self.subTest(diagnostic):
                self.assertEqual(service.reason({"diagnostic": diagnostic}), expected)
                self.assertNotIn("gave no answer", service.reason({"diagnostic": diagnostic}))


if __name__ == "__main__":
    unittest.main()
