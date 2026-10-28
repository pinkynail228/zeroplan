"""rel04-lifecycle-guard (release 0.4.0 class repair, F-1): lifecycle preconditions live in the mutation that
owns the state.

R-1: `Authority.begin` refuses, before any state change, while any run is in a `runs.ACTIVE` state — the single
"active" notion (`runs.active_run`), never a caller's copy. R-2: `Authority.approve`/`override` read the live
configuration digest from the session-bound profile they retain; no caller can disable or replace it.

Interpretations this task had to fix (the worker's summary never reaches the reviewers, so they are recorded here):

- A-1's coverage contract is fixed. A *direct* `Authority.begin` test refuses in every `runs.ACTIVE` state (the
  owner guard is what protects the class), and `BeginInventoryTests` compares the *closed syntactic inventory* of
  production `begin` calls — every `ast.Call` whose `func` is an `ast.Attribute` with `attr == "begin"` — as an
  exact multiset (`collections.Counter`), keyed by relative file, qualified scope (async included), canonical
  receiver text (`ast.unparse`) and ordinal in source order within the scope (occurrences are collected per scope
  and ordered by position — never AST visit order; a dict literal visits keys before values); no line numbers. The
  expected today is 10 occurrences: the four Authority callers (`Planning.begin`, `Planning.renew`, `Runs.revise_plan`,
  `Runs.revise`), each explicitly bound to its state x action matrix row in `AUTHORITY_BEGIN_ROWS`, plus six
  known non-Authority candidates listed by identity. The oracle behind the check is the real scanner over
  hand-written source, not a mock: an added call inside an already listed function (the round-4
  `authority = self.authority; authority.begin(...)` alias inside `cli.App.plan_flow`), a duplicated call, a
  removed call and a changed receiver each fail it, with a message that names the changed occurrence and asks for
  a review.
- The matrix domain is the production constants: actions {Planning.begin, renew, send, restart, revise (plan),
  Runs.revise (steward follow-up), approve, override} x run states {none, each of the six `runs.ACTIVE` states,
  each terminal outcome}. The terminal outcomes are `runs.OUTCOMES` (done, needs_owner, blocked, invalid) as a
  finished run, plus the terminal statuses without a done outcome (`failed_recoverable`, `failed`, `stopped`).
  `runs.OUTCOMES` is not reachable through the fixture driver's scripted outcomes alone, so `invalid` is a
  finished record whose output/manifest/result are reset exactly as the native "invalid" evaluation leaves them.
  Every state/outcome is a store the session loads and validates; the ACTIVE records come from a real submitted
  run moved to the named status.
- The matrix expectations are the production outcomes: plan-creating actions refuse in every ACTIVE state (family
  `action.refused`, the "Milestone M… is still running" message) with the Authority bytes, Git refs, the worktree
  set and the driver's side-effect counters unchanged, and append exactly one revision with no active writer —
  including beside a historical terminal attempt. `Planning.send` on the approved revision is the no-op "sent" in
  every state (bytes unchanged). `Runs.revise` (the steward follow-up) has its own matrix: it needs a *valid*
  unsuccessful follow-up target, so it is driven beside an independent active writer (M2 while M1's latest attempt
  is failed) across all six ACTIVE writer states — the refusal is the owner guard's, not `check_followup`'s "not
  the latest attempt" — and, with no writer, is allowed for every unsuccessful terminal attempt and refused for a
  successful (`done`) one. Every ACTIVE record in both the direct and the matrix cases is a validated store (an
  undispatched status never keeps a run id), so a refusal can only be the guard's: on the base the call succeeds
  and the named assertion fires. `approve`/`override` are refused for the revision-status reason in every state
  (a *proposed* revision beside an ACTIVE writer is not a reachable combination: `begin` is what would create it
  and it refuses) and are covered positively on a new revision beside *every* run state — no run, or one terminal
  attempt per outcome/status: `proposed` for approve, `review_exhausted` for override, with the historical records
  asserted byte-identical afterwards — plus in `test_plan_override`/`test_plan_gate` for the R-2 digest.
- A-2 is a regression guard: the allowed paths (observe, stop, export, merge, resume, integration refresh) keep
  their own preconditions while a writer is active or historical — the guard is not in their way.
- A-3's *plain* half is not a base failure on either base: the regression baseline `56a8b57` refuses it through
  the `Runs.revise_plan` caller copy R-1 removes, and the repair base `684c4b6` (that copy already gone) refuses
  it through the owner guard. `PlainFlowTests` is therefore the regression guard whose evidence is a
  candidate-only mutation in a scratch copy: with *only* the `Authority.begin` guard disabled, the plain `r`
  creates revision 2 and the test fails at its named behavioral assertion (`len(state["revisions"]) == 1`). The
  class-level A-3 base failure stays the TUI chat hand-over (`test_tui_chat.LifecycleGuardChatTests`).
"""

import ast
import collections
import copy
from pathlib import Path
import shutil
import unittest

from terminal_planner import runs
from terminal_planner.authority import Authority as RealAuthority, Blocked
from terminal_planner.engine import FixtureEngine
from terminal_planner.planning import Planning
from terminal_planner.runs import FixtureDriver, MilestoneRuns
import test_terminal_planner as tp
from test_terminal_planner import ROLES, ScriptedTerminal

PACKAGE = Path(__file__).resolve().parents[1] / "terminal_planner"
#
# A-1's coverage is a *closed syntactic inventory* of `begin` calls: every `ast.Call` whose `func` is an
# `ast.Attribute` with `attr == "begin"`. Strings, comments and alias resolution are out of scope — this is a
# change inventory, not a runtime call-graph proof. An occurrence's identity is its relative file path, its
# qualified class/function scope (async included), the canonical receiver text (`ast.unparse`) and its ordinal in
# source order within that scope; never a line number. The expectation is the exact multiset (`collections.Counter`).
#
# Today there are 10 occurrences. Four are the Authority callers, each explicitly bound to the state x action
# matrix row it backs (`AUTHORITY_BEGIN_ROWS`); the other six are the known non-Authority candidates, listed by
# identity:
#   architect.py       Architect.send                self
#   cli.py             App.plan_flow                 self.planning
#   runs.py            FixtureDriver.resume          self
#   runs.py            FixtureDriver.submit          self
#   tui/chat.py        ArchitectChat._turn           architect
#   tui/controller.py  Controller.start_planning.work planning
EXPECTED_BEGIN_INVENTORY = collections.Counter({
    ("planning.py", "Planning.begin", "a", 0): 1,
    ("planning.py", "Planning.renew", "self.authority", 0): 1,
    ("runs.py", "MilestoneRuns.revise_plan", "self.authority", 0): 1,
    ("runs.py", "MilestoneRuns.revise", "self.authority", 0): 1,
    ("architect.py", "Architect.send", "self", 0): 1,
    ("cli.py", "App.plan_flow", "self.planning", 0): 1,
    ("runs.py", "FixtureDriver.resume", "self", 0): 1,
    ("runs.py", "FixtureDriver.submit", "self", 0): 1,
    ("tui/chat.py", "ArchitectChat._turn", "architect", 0): 1,
    ("tui/controller.py", "Controller.start_planning.work", "planning", 0): 1,
})

# The four Authority callers, each explicitly bound to its row in the A-1 state x action matrix (`BeginGuardTests`
# and its steward matrix): the rows that create or renew a plan revision *through* `Authority.begin`. The other
# matrix rows (`Planning.revise`, `Planning.restart`, `Planning.send`) reach these rows through a pair, and
# `Runs.revise` is the steward follow-up row.
AUTHORITY_BEGIN_ROWS = {
    ("planning.py", "Planning.begin", "a", 0): "Planning.begin",
    ("planning.py", "Planning.renew", "self.authority", 0): "Planning.renew",
    ("runs.py", "MilestoneRuns.revise_plan", "self.authority", 0): "Runs.revise_plan",
    ("runs.py", "MilestoneRuns.revise", "self.authority", 0): "Runs.revise",
}
# Every action label the state x action matrix drives, in call order.
MATRIX_ACTIONS = ("Planning.begin", "Planning.renew", "Planning.restart", "Planning.revise",
                  "Runs.revise_plan", "Planning.send", "Runs.revise")


def _scan_module(tree, name):
    """The real scanner: every `.<receiver>.begin(...)` of one parsed module, as identities of
    (file, qualified scope, canonical receiver, ordinal in source order within the scope). The ordinal is the
    occurrence's *source* order — positions order the occurrences and are then dropped — never the AST traversal
    order: a dict literal visits its keys before its values, so `{a.begin(): b.begin()}` would otherwise number
    `a=0, b=2`."""
    found = collections.Counter()
    per_scope = {}
    stack = []

    class Scan(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "begin":
                scope = ".".join(stack)
                # The position orders the occurrences; it never enters the identity (no line numbers).
                per_scope.setdefault((name, scope), []).append(((node.lineno, node.col_offset),
                                                                ast.unparse(func.value)))
            self.generic_visit(node)

    Scan().visit(tree)
    for (file, scope), occurrences in per_scope.items():
        for ordinal, (_, receiver) in enumerate(sorted(occurrences, key=lambda item: item[0])):
            found[(file, scope, receiver, ordinal)] += 1
    return found


def _package_sources():
    for path in sorted(PACKAGE.rglob("*.py")):
        yield str(path.relative_to(PACKAGE)), path.read_text(encoding="utf-8")


def begin_inventory(sources=None):
    """The closed `begin` inventory of the package source, exactly and by the one predicate. `sources` is an
    iterable of (name, text) pairs — the oracle probes drive the same scanner over hand-written source."""
    inventory = collections.Counter()
    for name, text in (_package_sources() if sources is None else sources):
        inventory.update(_scan_module(ast.parse(text, filename=name), name))
    return inventory


def _render_occurrence(identity):
    name, scope, receiver, ordinal = identity
    return "%s:%s receiver=%s ordinal=%d" % (name, scope, receiver, ordinal)


def check_begin_inventory(inventory, expected):
    """The one comparison of the exact-multiset checks and the oracle probes: `Counter` exact equality over the
    closed inventory. On a mismatch raise an `AssertionError` that names every changed occurrence (added, removed
    or changed receiver) and asks for a review; a match returns None."""
    if inventory == expected:
        return
    changed = []
    for identity in sorted(set(inventory) | set(expected)):
        before, after = expected.get(identity, 0), inventory.get(identity, 0)
        if before != after:
            changed.append("%s (expected x%d, found x%d)" % (_render_occurrence(identity), before, after))
    raise AssertionError(
        "begin call inventory changed: %d occurrence(s) differ from the reviewed set; review the change:\n  %s"
        % (len(changed), "\n  ".join(changed)))


class BeginInventoryTests(unittest.TestCase):
    """A-1 (coverage): the closed syntactic inventory of production `begin` calls, so an added, duplicated,
    removed or re-received call fails the test."""

    def test_the_ten_production_begin_calls_are_the_exact_multiset(self):
        check_begin_inventory(begin_inventory(), EXPECTED_BEGIN_INVENTORY)

    def test_the_four_authority_callers_are_each_bound_to_a_matrix_row(self):
        inventory = begin_inventory()
        self.assertEqual(len(AUTHORITY_BEGIN_ROWS), 4)
        for site, row in AUTHORITY_BEGIN_ROWS.items():
            self.assertEqual(inventory[site], 1)      # the caller is present exactly once...
            self.assertIn(row, MATRIX_ACTIONS)        # ...and bound to a row the matrix drives

    def test_the_six_other_begin_calls_are_listed_by_identity(self):
        inventory = begin_inventory()
        others = {site for site in inventory if site not in AUTHORITY_BEGIN_ROWS}
        self.assertEqual(len(others), 6)
        self.assertEqual(others, {site for site in EXPECTED_BEGIN_INVENTORY if site not in AUTHORITY_BEGIN_ROWS})

    # The real scanner, driven over hand-written source (never a mock): a miniature `cli` whose `App.plan_flow`
    # reaches `Authority.begin` through `self.planning`, exactly as the production `cli.py` does.
    ORACLE_SOURCE = ("class App:\n"
                     "    def plan_flow(self, goal):\n"
                     "        self.planning.begin(goal, self.roles)\n")
    ORACLE_EXPECTED = collections.Counter({("cli.py", "App.plan_flow", "self.planning", 0): 1})

    def test_the_comparison_accepts_the_reviewed_source(self):
        self.assertIsNone(check_begin_inventory(begin_inventory([("cli.py", self.ORACLE_SOURCE)]),
                                                self.ORACLE_EXPECTED))

    def test_the_ordinals_are_source_order_not_ast_traversal_order(self):
        """The real scanner over the round-5 finding: a dict literal visits its keys before its values, so a
        traversal-ordered scanner numbers `{a: b, c: d}` as a=0, c=1, b=2, d=3. The ordinal must be the *source*
        order — a=0, b=1, c=2, d=3 — and the traversal order must fail the comparison. The position only orders the
        occurrences; it never enters the identity."""
        source = ("class Store:\n"
                  "    def plan(self):\n"
                  "        return {self.a.begin(): self.b.begin(), self.c.begin(): self.d.begin()}\n")
        source_order = collections.Counter({
            ("a.py", "Store.plan", "self.a", 0),
            ("a.py", "Store.plan", "self.b", 1),
            ("a.py", "Store.plan", "self.c", 2),
            ("a.py", "Store.plan", "self.d", 3),
        })
        traversal_order = collections.Counter({
            ("a.py", "Store.plan", "self.a", 0),
            ("a.py", "Store.plan", "self.c", 1),
            ("a.py", "Store.plan", "self.b", 2),
            ("a.py", "Store.plan", "self.d", 3),
        })
        inventory = begin_inventory([("a.py", source)])
        self.assertEqual(inventory, source_order)           # the ordinal is the source order
        self.assertNotEqual(inventory, traversal_order)     # and never the AST visit order
        self.assertIsNone(check_begin_inventory(inventory, source_order))

    def test_the_comparison_flags_every_change(self):
        """The oracle, on the real scanner over synthetic source: each change to the inventory fails the comparison
        and the message names the changed occurrence and asks for a review."""
        added = ("class App:\n"                      # the round-4 case: a second call in the same listed function
                 "    def plan_flow(self, goal):\n"
                 "        self.planning.begin(goal, self.roles)\n"
                 "        authority = self.authority\n"
                 "        authority.begin(goal, self.roles)\n")
        duplicated = ("class App:\n"
                      "    def plan_flow(self, goal):\n"
                      "        self.planning.begin(goal, self.roles)\n"
                      "        self.planning.begin(goal, self.roles)\n")
        removed = ("class App:\n"
                   "    def plan_flow(self, goal):\n"
                   "        pass\n")
        changed = ("class App:\n"
                   "    def plan_flow(self, goal):\n"
                   "        self.helper.begin(goal, self.roles)\n")
        for label, source, named in (("added in an already listed function (round-4 alias)", added, "authority"),
                                     ("duplicated", duplicated, "self.planning"),
                                     ("removed", removed, "self.planning"),
                                     ("changed receiver", changed, "self.helper")):
            with self.subTest(label):
                with self.assertRaises(AssertionError) as raised:
                    check_begin_inventory(begin_inventory([("cli.py", source)]), self.ORACLE_EXPECTED)
                message = str(raised.exception)
                self.assertIn("cli.py", message)          # the changed occurrence is named...
                self.assertIn("App.plan_flow", message)
                self.assertIn(named, message)
                self.assertIn("review", message)          # ...and the message asks for a review


class CountingDriver(FixtureDriver):
    """The fixture driver with explicit side-effect counters: every submission, force-stop, resume and watch is
    counted, so a refused owner action can be shown to have touched nothing (no extra dispatch, no extra slice)."""

    def __init__(self, root, outcome="done"):
        super().__init__(root, outcome)
        self.calls = {"submit": 0, "force_stop": 0, "resume": 0, "watch": 0}

    def submit(self, r, paths):
        self.calls["submit"] += 1
        return super().submit(r, paths)

    def force_stop(self, r):
        self.calls["force_stop"] += 1
        return super().force_stop(r)

    def resume(self, r, run_id):
        self.calls["resume"] += 1
        return super().resume(r, run_id)

    def watch(self, r, after, seconds=None):
        self.calls["watch"] += 1
        return super().watch(r, after, seconds)


class GuardCase(tp.ProjectTest):
    """A fixture authority with helpers to store an approved plan and one milestone run in a named state."""

    # Each terminal outcome as a finished run, plus the terminal statuses that carry no done outcome.
    TERMINAL_KEYS = tuple(runs.OUTCOMES) + ("failed_recoverable", "failed", "stopped")
    FIXTURE_OUTCOME = {"needs_owner": "needs_owner", "blocked": "blocked", "invalid": "done",
                       "failed_recoverable": "failed_recoverable", "failed": "failed", "stopped": "done"}

    def setUp(self):
        super().setUp()
        self.driver = CountingDriver(self.root / "fixture-runs")

    def runs_of(self, authority):
        return MilestoneRuns(authority, self.driver, worktrees=self.root / "worktrees")

    def planning_of(self, authority):
        return Planning(authority, self.runs_of(authority), lambda *args: FixtureEngine(), None, None, None)

    def path(self):
        return RealAuthority(self.state, self.project, fixture_id="test").path

    def store_bytes(self):
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            return authority.path.read_bytes()

    def refs(self):
        return self.git("for-each-ref", "--format=%(refname) %(objectname)")

    def head(self):
        return self.git("rev-parse", "HEAD").decode().strip()

    def reset(self):
        """A clean store, fixture run root and worktree root: each scenario starts from nothing."""
        for path in (self.state, self.root / "fixture-runs", self.root / "worktrees"):
            shutil.rmtree(path, ignore_errors=True)
        self.state.mkdir(parents=True)
        self.driver = CountingDriver(self.root / "fixture-runs")

    def counters(self, authority):
        """The side effects a refusal must leave exactly as they were: the Authority bytes, the Git refs, the
        revision and run records, the worktree directories and the driver's own dispatch counters."""
        trees = self.root / "worktrees"
        return (authority.path.read_bytes(), self.refs(), len(authority.state["revisions"]),
                len(authority.state.get("runs", [])),
                tuple(sorted(p.name for p in trees.iterdir())) if trees.is_dir() else (),
                tuple(sorted(self.driver.calls.items())))

    def build(self, key=None):
        """Store an approved fixture plan and, for a non-None `key`, one M1 run in that state.

        ACTIVE states are reached from a real submitted record; `preparing`/`submission_unknown`/`resume_pending`
        drop the run id, as an undispatched record requires, and every scenario is saved (and so validated). The
        `invalid` outcome is not a scripted fixture outcome: it is the finished record reset exactly as the native
        "invalid" evaluation leaves it (no output, no manifest, no result)."""
        self.driver = CountingDriver(self.root / "fixture-runs", self.FIXTURE_OUTCOME.get(key, "done"))
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(authority.current["version"])
            if key is not None:
                controller = self.runs_of(authority)
                r = controller.start("M1", authority.current["version"], ROLES)
                if key == "stopped":
                    controller.stop(r)
                    controller.observe(r)
                elif key in runs.ACTIVE:
                    r["status"] = key
                    if key in runs.UNDISPATCHED:  # an undispatched record never keeps its run id
                        r["run_id"] = None
                    authority.save()
                else:
                    controller.observe(r)
                    if key == "invalid":
                        r.update(delivery="none", result=None, integration=None, outcome="invalid", output=None,
                                 manifest=None, diagnostic="invalid root output")
                        authority.save()
        return self.store_bytes()


class BeginGuardTests(GuardCase):
    """A-1: the owner guard refuses in every ACTIVE state, before any state change."""

    def test_a1_direct_authority_begin_refuses_in_every_active_state(self):
        """The state is a *validated* store, so nothing but the owner guard can refuse — on the base the call
        appends revision 2 and the `assertRaises` is the named failure (a record that only had its status changed
        would fail `save()`'s `validate_state` with the wrong family instead). Interpretation: `begin` refuses
        through the one `active_run` check, so one active state stands for the six."""
        # Branches kept: the one `status in ACTIVE` refusal in `Authority.begin`, via `running`.
        self.reset()
        raw = self.build("running")
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            before, head = self.counters(authority), self.head()
            with self.assertRaises(Blocked) as raised:
                authority.begin("Another goal", ROLES, "fixture")
            self.assertEqual(raised.exception.family, "action.refused")
            self.assertIn("is still running", str(raised.exception))
            self.assertEqual(self.counters(authority), before)   # bytes, refs, counters: nothing moved
            self.assertEqual(self.head(), head)
            self.assertEqual(len(authority.state["revisions"]), 1)  # no revision appended
            self.assertEqual(authority.path.read_bytes(), raw)  # the store on disk is untouched

    def test_a1_plan_creating_actions_refuse_in_every_active_state_and_are_allowed_for_every_terminal_outcome(self):
        # Branches kept: one active state (`status in ACTIVE`) and one terminal outcome; all six entry points.
        creating = (
            ("Planning.begin", lambda p, a: p.begin("Second goal", ROLES)),
            ("Planning.renew", lambda p, a: p.renew()),
            ("Planning.restart", lambda p, a: p.restart()),
            ("Planning.revise", lambda p, a: p.revise("Change it")),
            ("Runs.revise_plan", lambda p, a: p.runs.revise_plan("Change it")),
            ("Planning.send", lambda p, a: p.send()),
        )
        states = [("running", "running"), ("done", "done")]
        for label, key in states:
            self.reset()
            raw = self.build(key)
            for action_label, action in creating:
                with self.subTest(state=label, action=action_label):
                    self.path().write_bytes(raw)
                    with RealAuthority(self.state, self.project, fixture_id="test") as authority:
                        planning = self.planning_of(authority)
                        before = self.counters(authority)
                        if action_label == "Planning.send":  # the approved revision is already as sent as it gets
                            self.assertEqual(action(planning, authority).kind, "sent")
                            self.assertEqual(self.counters(authority), before)
                        elif key in runs.ACTIVE:
                            with self.assertRaises(Blocked) as raised:
                                action(planning, authority)
                            self.assertEqual(raised.exception.family, "action.refused")
                            self.assertIn("is still running", str(raised.exception))
                            self.assertEqual(self.counters(authority), before)   # refusals write nothing
                        else:
                            action(planning, authority)  # positive control: no active writer
                            self.assertEqual(len(authority.state["revisions"]), before[2] + 1)
                            self.assertEqual(self.refs(), before[1])            # no Git side effect either way

    def delivered_then_failed(self, authority):
        """M1 attempt 1 delivered and merged (so a second milestone may start) and attempt 2 an unsuccessful, latest
        attempt: the `(controller, target)` a steward follow-up needs. `check_followup`'s own conditions hold for
        the target, so the only thing left that can refuse `Runs.revise` is the owner guard."""
        self.driver = CountingDriver(self.root / "fixture-runs", "done")
        controller = self.runs_of(authority)
        done = controller.observe(controller.start("M1", authority.current["version"], ROLES))
        controller.finish(done)
        controller.merge(done)  # M1 delivered, so M2 may start
        self.driver = CountingDriver(self.root / "fixture-runs", "failed")
        controller = self.runs_of(authority)  # a controller over the failed-outcome driver
        target = controller.observe(controller.start("M1", authority.current["version"], ROLES))
        self.assertEqual((target["status"], target["outcome"], target["attempt"]), ("failed", None, 2))
        self.driver = CountingDriver(self.root / "fixture-runs", "done")
        return self.runs_of(authority), target

    def test_a1_steward_revise_refuses_in_every_active_writer_state_and_proceeds_for_every_terminal_attempt(self):
        """`Runs.revise` (steward follow-up) x run states, over a *valid* target `check_followup` accepts.

        An independent M2 writer is refused with the owner guard — the same `Milestone … is still running` message
        `revise_plan` gives — so the refusal is the shared lifecycle precondition, never `check_followup`'s "not
        the latest attempt". With no active writer the same follow-up creates the revision for an unsuccessful
        terminal attempt, and is refused by a different, pre-existing condition for a successful (`done`) attempt.
        Interpretation: the guard is one `status in ACTIVE` check, so one active writer (`submitted`, as started)
        stands for the six, and `check_followup`'s `outcome != "done"` has two sides, `done` and `failed`."""
        # Branches kept: one active writer (`status in ACTIVE`); `done` (refused) and `failed` (proceeds).
        self.reset()
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.begin(authority)
            self.propose(authority)
            authority.approve(authority.current["version"])
            controller, target = self.delivered_then_failed(authority)
            writer = controller.start("M2", authority.current["version"], ROLES)
            self.assertIs(controller.active(), writer)
            self.assertIn(writer["status"], runs.ACTIVE)
            before = self.counters(authority)
            with self.assertRaises(Blocked) as raised:
                self.planning_of(authority).runs.revise(target, "Change it")
            self.assertEqual(raised.exception.family, "action.refused")
            self.assertIn("M2 is still running", str(raised.exception))
            self.assertEqual(self.counters(authority), before)  # the follow-up wrote nothing at all
            self.assertEqual(len(authority.state["revisions"]), 1)
            controller.stop(writer)
            controller.observe(writer)  # release the independent writer
        for key in ("done", "failed"):
            with self.subTest(target=key):
                self.reset()
                self.build(key)
                with RealAuthority(self.state, self.project, fixture_id="test") as authority:
                    target = authority.state["runs"][0]
                    before = self.counters(authority)
                    if key == "done":  # a successful attempt is not a follow-up: the pre-existing condition refuses
                        with self.assertRaises(Blocked) as raised:
                            self.planning_of(authority).runs.revise(target, "Change it")
                        self.assertEqual(raised.exception.family, "action.refused")
                        self.assertIn("only after an unsuccessful attempt", str(raised.exception))
                        self.assertEqual(self.counters(authority), before)
                    else:  # no active writer: the follow-up proceeds and creates revision 2
                        self.planning_of(authority).runs.revise(target, "Change it")
                        self.assertEqual(len(authority.state["revisions"]), 2)
                        self.assertEqual(authority.current["status"], "planning")

    def test_a1_approve_and_override_are_refused_for_the_revision_status_in_every_state(self):
        """Interpretation: `approve` (`status != "proposed"`) and `override` (`status != "review_exhausted"`) refuse
        on the revision's own status and read no run record, so each is checked once on the already approved
        revision, beside one active writer."""
        # Branches kept: the `approve` and the `override` status refusal, beside one active run (`running`).
        self.reset()
        raw = self.build("running")
        for name, call in (("approve", lambda p, a: p.approve(a.current["version"])),
                           ("override", lambda p, a: p.override(a.current["version"], "x" * 20))):
            with self.subTest(action=name):
                self.path().write_bytes(raw)
                with RealAuthority(self.state, self.project, fixture_id="test") as authority:
                    before = self.counters(authority)
                    with self.assertRaises(Blocked) as raised:
                        call(self.planning_of(authority), authority)
                    self.assertEqual(raised.exception.family, "action.refused")
                    self.assertEqual(self.counters(authority), before)

    def test_a1_approve_and_override_are_allowed_on_a_new_revision_beside_every_terminal_outcome(self):
        """The valid approval contexts the refusal matrix cannot reach: revision 1 is approved with a terminal
        attempt (`done`) and no active writer, so `revise_plan` creates revision 2. Its gate leaves revision 2
        `proposed` (accepted scenario) for `approve` or `review_exhausted` (rejected scenario) for `override`, and
        either then succeeds with the historical revision record and every run record untouched.

        This is the oracle for a state-dependent refusal: a product change that refused approval beside a terminal
        history fails here, while the refusal matrix above (which only ever sees an already-approved revision) and
        `test_plan_override` (which only builds a fresh project) would both still pass. Approval is not what the
        owner guard owns: only a plan-creating action is refused in an `ACTIVE` state. Interpretation: the guard
        reads the status, never the outcome, so one terminal outcome (`done`) stands for the others."""
        # Branches kept: one terminal history (`done`), for `approve` and for `override`.
        for scenario, expected, action in (("accept", "proposed", "approve"),
                                           ("exhausted", "review_exhausted", "override")):
            with self.subTest(action=action):
                self.reset()
                self.build("done")            # revision 1 approved, with a terminal attempt
                with RealAuthority(self.state, self.project, fixture_id="test") as authority:
                    planning = self.planning_of(authority)
                    first = copy.deepcopy(authority.state["revisions"][0])
                    history = copy.deepcopy(authority.state.get("runs", []))
                    planning.runs.revise_plan("Change it")   # no active writer: revision 2 is created
                    self.assertEqual([r["version"] for r in authority.state["revisions"]], [1, 2])
                    FixtureEngine(scenario).proposal(authority, lambda _: None)
                    self.assertEqual(authority.current["status"], expected)
                    version = authority.current["version"]
                    before = self.counters(authority)
                    if action == "approve":
                        planning.approve(version)
                    else:
                        planning.override(version, "x" * 20)
                    self.assertEqual(authority.current["status"], "approved")
                    self.assertNotEqual(self.counters(authority), before)  # the approval wrote the new state
                    self.assertEqual(authority.state["revisions"][0], first)  # the old revision record is intact
                    self.assertEqual(authority.state.get("runs", []), history)  # ... and so is every run record


class AllowedPathsTests(GuardCase):
    """A-2: the allowed paths keep their own preconditions while a writer is active or historical."""

    def test_a2_observe_stop_then_export_and_merge_keep_working_beside_the_guard(self):
        self.reset()
        self.build("submitted")
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            controller = self.runs_of(authority)
            r = controller.active()
            self.assertIsNotNone(r)                       # a real writer is active; stop stays allowed
            controller.stop(r)
            self.assertEqual(controller.observe(r)["status"], "stopped")
            controller.refresh()                          # integration refresh stays a read
        # a done attempt (historical terminal) still exports and merges
        self.reset()
        raw = self.build("done")
        self.path().write_bytes(raw)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            controller = self.runs_of(authority)
            r = controller.runs[0]
            controller.finish(r)
            self.assertEqual(r["delivery"], "awaiting_merge")
            self.assertEqual(controller.merge(r)["delivery"], "integrated")

    def test_a2_resume_stays_available_after_a_recoverable_failure(self):
        self.reset()
        raw = self.build("failed_recoverable")
        self.path().write_bytes(raw)
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            controller = self.runs_of(authority)
            r = controller.runs[0]
            self.assertIs(r["recoverable"], True)
            successor = controller.resume(r)
            self.assertEqual(successor["status"], "submitted")   # resume/adopt is not blocked by R-1


class PlainFlowTests(GuardCase):
    """A-3 (plain): [r] while a writer is active is refused and the later observe/export/merge stay usable.

    Interpretation (amended A-3): this refusal is not a base failure on either base — the regression baseline
    `56a8b57` refuses it through the `Runs.revise_plan` caller copy that R-1 removes, and the repair base `684c4b6`
    (that copy already gone) refuses it through the owner guard. This is therefore the regression guard for the
    plain path, and its evidence is a candidate-only mutation in a scratch copy: with *only* the `Authority.begin`
    guard disabled, the plain `r` creates revision 2, so the named behavioral assertion
    `len(authority.state["revisions"]) == 1` (and the "is still running" assertion) fires. The class-level A-3 base
    failure stays the TUI chat hand-over (`test_tui_chat.LifecycleGuardChatTests`)."""

    def session(self, text, keys=()):
        from terminal_planner import cli
        import io
        output = io.StringIO()
        driver = FixtureDriver(self.root / "fixture-runs", "done")
        cli.session(ScriptedTerminal(text, output, keys), self.project, self.state, lambda *_: FixtureEngine(),
                    fixture_id="test", driver_factory=lambda _: driver, worktrees=self.root / "worktrees")
        return output.getvalue()

    def test_a3_plain_revise_is_refused_while_active_and_the_run_still_delivers(self):
        self.reset()
        self.build("submitted")
        # The trailing [q]s only matter when the guard is gone: the mutated `r` then reaches the planner and the
        # plan screen (`Plan r2`), so the run must be able to end for the assertion below — not input exhaustion —
        # to be the failure.
        output = self.session("r\nChange roadmap\n\nq\nq\n")
        self.assertIn("is still running", output)                 # the R-1 message, in the line UI
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(len(authority.state["revisions"]), 1)   # revision identity unchanged
            self.assertEqual(len(authority.state["runs"]), 1)        # run identity unchanged
        output = self.session("w\n" + "m\ny\n" + "q\n")           # observation, then export + merge
        with RealAuthority(self.state, self.project, fixture_id="test") as authority:
            self.assertEqual(authority.state["runs"][0]["delivery"], "integrated")


if __name__ == "__main__":
    unittest.main()
