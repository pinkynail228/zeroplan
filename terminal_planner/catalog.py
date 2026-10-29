"""Public contract catalog: every persisted status, owner-facing state, screen action and stable error family.

Each entry has an ID, a meaning, a likely cause and the owner's remedy (a key or a command). The code references
these IDs where it raises or shows a family (`Blocked(..., family="export.branch_exists")`, `catalog.action(...)`);
tests derive the finite sets from the code and require both directions. Arbitrary model/provider text is never a
catalog entry: it stays a bounded detail next to a family code, and a failure without a family shows `unknown_error`.

Run `python -m terminal_planner.catalog --write docs/REFERENCE.md` to refresh the generated tables there.
Stdlib only, so help and docs work without tools, login, a Git project or Textual."""

from collections import namedtuple
import sys
import unicodedata

Entry = namedtuple("Entry", "id meaning cause remedy")
Action = namedtuple("Action", "id screen key label short hint meaning alt")
Screen = namedtuple("Screen", "id title meaning footer")

UNKNOWN = "unknown_error"

# Owner-facing lines that are not a status or a key: the wording lives here, with the rest of the public text.
NEXT = "Next:"
JOURNAL = "Journal"
JOURNAL_EMPTY = "The attempt journal is empty: observation has not recorded anything yet."
CHECK_DONE = "Done: everything is in order."
CHECK_EMPTY = "No check results."
CHECK_ERROR = "The check did not run: "
# D5: the one extra step a device-code login that is turned off for the account needs, shared by the failed-login
# lines the owner sees after `zplan login` and under [l]; their retry hint keeps its own wording.
LOGIN_DEVICE_CODE_OFF = ("If device-code login is turned off for the account, turn it on in the "
                         "account's ChatGPT security settings.")

# R-4: the key-free remedy of one readiness item, keyed by the item's structured id (the same ids as the
# `readiness.*` error families and `setup.readiness()`): the fix the owner runs when the Settings screen cannot
# offer the item's own key this session, so a closing line never names a key that screen does not bind. A key
# stays preferred whenever it is offered.
CHECK_REMEDY_FREE = {
    "socket": "run `zplan doctor` with a short socket path",
    "tools": "run `zplan setup` in a terminal",
    "codex": "run `zplan setup` in a terminal",
    "codex_home": "fix CODEX_HOME and run `zplan doctor`",
    "auth": "run `zplan login` in a terminal",
    "git": "install Git and run `zplan doctor`",
    "identity": "set git config --global user.name and user.email",
    "roles": "run `zplan roles`",
    "repo": "change into a Git project (cd) or pass --project",
    "branch": "switch to a branch: git switch <branch>",
    "origin": "point origin at GitHub",
}

# One id can carry two causes whose fixes differ, and the item's own structured `key` picks the applicable one:
# the auth item is either a missing login file ([l] log in repairs it, the entry above) or an unset provider
# environment key ([i] shows how; only an export repairs it, `zplan login` cannot). Without this, every auth
# failure told an env-key provider to run the login it does not need.
CHECK_REMEDY_FREE_KEY = {
    ("auth", "i"): "set the provider's environment variable (or remove the copied auth.json, see `zplan doctor`) and run zplan again",
}


def remedy_free(item_id, key=None):
    """The key-free remedy of one readiness item (R-4): its structured `(id, key)` when the id alone is ambiguous,
    else its id; "" when the catalog names none."""
    return CHECK_REMEDY_FREE_KEY.get((item_id, key)) or CHECK_REMEDY_FREE.get(item_id, "")


def cells(text):
    """How much room `text` takes in terminal cells: a wide or full-width glyph counts as two (stdlib only, so
    the catalog's own width arithmetic stays free of Textual and rich)."""
    total = 0
    for char in str(text):
        if unicodedata.combining(char):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def hint(action_id):
    """`[key] label` of one catalog action, for naming a key inside another owner-facing line."""
    return text(action_id)


def _entries(*rows):
    return {row[0]: Entry(*row) for row in rows}


# Persisted plan revision statuses (planning.json, authority.PLAN_STATUSES) ---------------------------------------

PLAN_STATUS = _entries(
    ("planning", "Goal saved, not yet sent to the planner.",
     "The goal was just written, or readiness failed before submission.", "[g] on the plan screen (readiness is checked first)."),
    ("submission_unknown", "The planner submission was sent but Zeroshot's acceptance was not confirmed.",
     "zplan or the engine was interrupted at the moment of submission.",
     "[g] sends the same frozen submission again (Zeroshot recognises its key); [i] shows the Zeroshot list command. "
     "zplan never resubmits on its own."),
    ("observing", "The planner run is being watched.", "A session is attached to the running planner.",
     "Wait; Ctrl-C detaches, the planner keeps running."),
    ("detached", "The planner runs but no session watches it.", "The owner detached or the session ended.",
     "[w] on the plan screen to watch again."),
    ("stopped", "The owner stopped the planner run; it will not be resubmitted.", "The owner asked to stop a run under observation.",
     "Open the plan screen; [g] runs the planner again in a new revision."),
    ("observation_blocked", "Watching stopped with a diagnostic while the planner may still run.",
     "A native watch call failed or returned unusable output.", "[w] watch again; [i] for the diagnostic."),
    ("run_failed", "The planner run ended without a plan.", "A provider, network, quota or authorization failure.",
     "The plan screen names the cause; [g] restarts after readiness, [r] revises the goal."),
    ("proposal_invalid", "The planner returned a plan zplan did not accept.", "The plan broke the roadmap contract.",
     "[r] revise the goal, or [g] run the planner again."),
    ("review_exhausted", "The critic did not accept the plan within the revision's plan rounds; it cannot be approved in the usual way.",
     "The goal is too broad or ambiguous, or the critic and the planner could not agree.",
     "[i] shows every round; [r] revise, [g] run the planner again, or [o] approve it over the rejection with a typed reason."),
    ("proposed", "A reviewed plan waits for the owner.", "The planner and verifier finished.",
     "[a] approve, [r] revise, [x] decline."),
    ("approved", "The owner approved this revision; milestones may run. A plan approved over a rejected plan check "
     "carries the owner's reason and is shown as approved despite the check.", "[a] on the proposed plan, or [o] on a plan the critic rejected.",
     "[g] start a milestone on the home screen; [r] to change the plan."),
)

# Milestone view states (runs.MILESTONE_STATES, the home screen) -------------------------------------------------

MILESTONE_STATE = _entries(
    ("waiting", "The milestone waits for the milestones it depends on.", "A dependency is not merged yet.",
     "Run and merge the dependency first."),
    ("ready", "Dependencies are merged; the milestone can start.", "Nothing was started for it in this plan revision.",
     "[g] start it (a preview with worktree, branches and limits asks for confirmation)."),
    ("running", "An attempt is executing.", "Started by [g].", "[w] watch; k + Enter while watching stops it."),
    ("unknown", "The attempt's submission or an interrupted run is not confirmed.",
     "zplan or the engine stopped between submission and acknowledgement.",
     "[g] reconciles with Zeroshot without resubmitting."),
    ("needs_owner", "The steward needs an answer or an accepted proposal.", "The task list could not proceed alone.",
     "[o] then [t] answer or [a] accept."),
    ("blocked", "The attempt reported it cannot proceed.", "A missing fact, access or contradiction.",
     "[o], then [t] answer and restart, or [p] revise the plan."),
    ("failed_recoverable", "The attempt failed and can continue in its worktree.", "A provider or tool error.",
     "[g] resumes the same attempt (or [o], then [g])."),
    ("failed", "The attempt failed and cannot continue.", "An unrecoverable engine or check failure.",
     "[g] starts a new attempt (or [o], then [t] / [p] revise the plan)."),
    ("awaiting_merge", "The accepted result is exported to its own branch and waits for the owner.",
     "The attempt finished with outcome done.", "[o], then [d] review the diff and [m] merge."),
    ("conflict", "Merging the result conflicted.", "The destination branch moved or touched the same files.",
     "[o]; merge the result branch by hand, then reopen zplan."),
    ("integrated", "The result is merged into the destination branch.", "[m] succeeded or ancestry was detected.",
     "Nothing; dependents become ready."),
    ("stopped", "The owner stopped the attempt.", "k + Enter while watching.", "[g] starts a new attempt (or [o], then [t] / [p] plan)."),
    ("stopping", "A stop was requested and is not confirmed yet.", "Native has not acknowledged the force-stop.",
     "[g] re-sends and reconciles the stop."),
)

# Milestone run record: native status, outcome, delivery ---------------------------------------------------------

RUN_STATUS = _entries(
    ("preparing", "The attempt's worktree and frozen documents are being prepared.", "Right after [g].",
     "Wait; an interrupted preparation is reconciled by [g]."),
    ("submission_unknown", "The submission to Zeroshot is unconfirmed.", "Interruption at submission.", "[g] reconciles."),
    ("submitted", "Zeroshot admitted the run.", "Submission was acknowledged.", "[w] watch."),
    ("running", "Zeroshot executes the run.", "The graph is working.", "[w] watch."),
    ("stopping", "A stop was requested.", "k + Enter.", "[g] reconciles."),
    ("resume_pending", "A resume was sent but its successor run is unconfirmed.", "Interruption at resume.", "[g] reconciles."),
    ("finished", "The run ended normally; see outcome.", "The graph completed.", "Per outcome."),
    ("failed", "The run ended with a failure.", "A provider or tool error.", "[o] for the failure screen."),
    ("stopped", "The run was stopped.", "Owner stop.", "[o]."),
)

OUTCOME = _entries(
    ("done", "The milestone's final verification accepted the result.", "All tasks and checks passed.",
     "Delivery follows: export then [m] merge."),
    ("needs_owner", "The steward asked the owner.", "A decision outside the task list.", "[t] answer or [a] accept."),
    ("blocked", "The run declared itself blocked.", "A fact or access is missing.", "[t] answer or [p] plan."),
    ("invalid", "The run's output did not satisfy the contract.", "Malformed result from the graph.",
     "[t] new attempt; [i] on home for diagnostics."),
)

DELIVERY = _entries(
    ("none", "Nothing exported yet.", "The run has not finished with done.", "Per run state."),
    ("exporting", "The result branch is being created.", "Right after done.", "Reopen zplan to finish export."),
    ("awaiting_merge", "The result branch exists and waits for [m].", "Export finished.", "[m] merge."),
    ("conflict", "The merge conflicted and was aborted (or left the tree dirty).", "Overlapping changes.",
     "Merge by hand, then reopen."),
    ("integrated", "The result is in the destination branch.", "[m] succeeded.", "Nothing."),
)

# Stable error families ------------------------------------------------------------------------------------------

ERRORS = _entries(
    # Readiness items: the same IDs as the item ids of `zplan doctor` and the readiness screen.
    ("readiness.socket", "The Zeroshot socket path is too long.", "The native state directory path is long.",
     "Use a shorter --native-state-dir or ZPLAN data path."),
    ("readiness.tools", "Pinned Zeroshot is missing or damaged.", "Setup was not run or files changed.", "[u] or `zplan setup`."),
    ("readiness.codex", "The pinned Codex binary is missing.", "Setup was not run or files changed.", "[u] or `zplan setup`."),
    ("readiness.codex_home", "Codex settings (CODEX_HOME/config.toml) cannot be read.", "A malformed or unknown config.",
     "Fix or remove the file; [i] shows the detail."),
    ("readiness.auth", "No usable Codex login for the selected provider.", "No login file or API key variable.",
     "[l] or `zplan login` in zplan's own home; in your own CODEX_HOME sign in with `codex login`; a copied "
     "auth.json: `rm` it, then `zplan login`; or set the provider key variable."),
    ("readiness.git", "Git is not installed or older than 2.38.", "git is not on PATH, or its version lacks `merge-tree --write-tree`.",
     "Install or upgrade Git to 2.38 or newer ([i] shows the command)."),
    ("readiness.identity", "No Git author identity.", "user.name/user.email are unset.",
     "git config --global user.name / user.email."),
    ("readiness.roles", "The saved role configuration is damaged or invalid.", "A hand-edited or old roles.json.",
     "`zplan roles` or delete roles.json."),
    ("readiness.repo", "The directory is not a Git project with a commit.", "Wrong directory or no commit yet.",
     "cd into the project or pass --project."),
    ("readiness.branch", "HEAD is detached.", "A checkout of a commit or tag.", "git switch <branch>."),
    ("readiness.origin", "origin is not a GitHub repository.", "No origin or another host.",
     "git remote add origin https://github.com/OWNER/REPO.git."),
    ("readiness.clean", "Some files are not in the last commit (informational: this item is always ok).", "Edited or untracked files.",
     "None needed: the plan, the checks and the runs read the last commit; your files stay as they are."),
    # Plans and submissions
    ("plan.stale", "The project or the Zeroshot it was prepared for changed after the plan was created or reviewed; the plan cannot be sent or approved.",
     "A commit or edit after the baseline was frozen, or a different Zeroshot toolchain, rebuilt binary or state directory.", "[g] on an unsent plan rebuilds it on the current project and sends it; [n] only prepares the new plan; "
     "[r] revises a proposal."),
    ("plan.gate_stale", "The plan was argued under another process configuration than the one that applies now; it cannot be approved.",
     "The process profile (limits, roles, rules selection) or a rules file changed after the critic accepted the plan.",
     "[r] revises: the plan is rebuilt under the current configuration and argued again."),
    ("plan.invalid_proposal", "The returned plan broke the roadmap contract (shape, ownership, size).",
     "The planner produced a malformed or oversized plan.", "[r] revise the goal or [g] run again."),
    ("plan.failed", "The planner run ended without an accepted plan.", "See the plan status and the cause screen.",
     "The plan screen names the next key."),
    ("plan.stop_unconfirmed", "Zeroshot did not confirm the stop of the running planner.", "The native force-stop call failed or timed out.",
     "[s] on the plan screen tries again; the run keeps being observed meanwhile."),
    ("draft.stale", "A draft was sent or opened for a state the project no longer has; it was not applied.",
     "For a goal draft: a new revision was prepared, or the same revision's state moved on (submitted, plan ready, "
     "approved). For an answer draft: the plan, the attempt, the run or the delivery moved on, or the milestone "
     "finished, after the reply the draft came from.",
     "Ask the architect again: [/plan] on the card of its new reply, or [/answer], applies normally. Nothing is "
     "exported and the stale draft's text stays copyable."),
    ("draft.malformed", "An answer draft's identity cannot be rebuilt into the attempt it was written for, so its "
     "form was not opened.",
     "A chat record written by another version, or a hand-edited or truncated draft identity.",
     "Ask the architect again for a fresh draft: only a draft whose identity rebuilds is applied by [t], and this "
     "one never is."),
    ("draft.active", "An answer draft belongs to an attempt that is still running; only a finished attempt offers "
     "an answer.",
     "The reply that carried the draft was written while the attempt was still running, and that same attempt is "
     "still the current one - its plan, attempt, run, status, outcome and delivery have not moved on since.",
     "The draft cannot be applied while it runs: [w] watches the attempt and [o] opens its end once it finishes, "
     "where [t] answers it directly. For the draft's own text, ask the architect again - its new reply carries a "
     "fresh draft."),
    ("draft.unavailable", "An answer draft's attempt has an end that offers no answer, so there is nothing left "
     "to answer.",
     "The reply's draft was written for an attempt whose end already offered no answer - it had finished and was "
     "exported or merged, or it never needed one - and its identity still matches the current one.",
     "Nothing is left to answer: [o] shows that end with its own keys ([m] merge, [d] diff), and the next step "
     "goes to the plan with [p]. A fresh draft from the architect carries the same end, so it would not help."),
    ("submission.unknown", "The engine did not confirm a submission; zplan will not resend it by itself.",
     "Interrupted between send and acknowledgement.",
     "[g]: on a plan, send the same frozen submission again (Zeroshot recognises its key); on a run, reconcile. "
     "[i] shows the Zeroshot list command."),
    ("planner.auth", "The provider rejected the authorization.", "An expired or revoked login or key.",
     "[l] refresh login, then [g]."),
    ("planner.quota", "The provider refused the request for a limit or quota.", "Rate or usage limit.",
     "Wait or check account limits, then [g]."),
    ("planner.network", "The model service was unreachable.", "Offline, DNS or proxy failure.", "Check the network, then [g]."),
    ("planner.unknown", "The planner stopped for a cause the public logs do not show.", "Anything else.",
     "[i] prints Zeroshot diagnostic commands; then [g]."),
    ("planner.detached", "Watching the planner was interrupted; it continues.", "Ctrl-C or a dropped watch.",
     "[w] on the plan screen watches again."),
    # Engine boundary
    ("engine.unavailable", "Zeroshot did not start or answer.", "Broken install or a stuck process.",
     "`zplan doctor`, then `zplan setup`."),
    ("engine.rejected", "Zeroshot deterministically rejected an operation.", "A contract or admission refusal.",
     "`zplan doctor`; diagnostics under [i]."),
    ("engine.bad_output", "Zeroshot returned oversized or malformed output.", "A tool/version mismatch.",
     "`zplan doctor`; reinstall with `zplan setup` if it persists."),
    ("engine.identity_changed", "The pinned executable or its state changed.", "Binary replaced or version mismatch.",
     "Use the original isolated paths or reinstall."),
    ("journal.history_unavailable", "The engine's run history could not be read for the journal.",
     "`zeroshot ui` did not start or answer, or returned malformed data.", "`zplan doctor`; the journal catches up later."),
    ("toolchain.mismatch", "A plan or run is frozen on another Zeroshot toolchain whose executable is gone or changed.",
     "A newer zplan release replaced the default toolchain and the recorded executable no longer matches its sha256.",
     "Finish it on the older zplan (its tools directory is kept), or start over from a new plan revision on the current toolchain."),
    ("engine.checkout", "The disposable planner checkout is missing or could not be prepared.",
     "Disk, Git or an interrupted preparation.", "Retry with a new revision ([n]); frozen history stays."),
    ("engine.intent_changed", "The frozen submission no longer matches its record.", "Hand-edited state.",
     "Not resumable; prepare a new revision ([n])."),
    ("engine.observation_lost", "No reconstructable first watch record exists for the run.", "Missing native history.",
     "[i] for the Zeroshot commands; resubmission stays forbidden."),
    # Store, project, actions
    ("store.invalid", "A stored record or envelope failed validation.", "Corruption, hand edits or a version mismatch.",
     "Do not edit state; keep the directory and report it. Older versions' records stay readable."),
    ("store.locked", "Another terminal controls this project's plan.", "A second zplan session holds the lock.",
     "Close the other session."),
    ("store.write_failed", "Persisting zplan state failed.", "Disk full or permissions.", "Free space or fix permissions, reopen."),
    ("project.unreadable", "The project could not be read as a Git tree.", "Not a project with a commit, or a changing tree.",
     "cd into the project; keep the tree still while zplan reads it."),
    ("action.refused", "The requested action is not allowed in the current state.",
     "The state moved on or the action's precondition is unmet.", "Reopen the screen; it offers the valid keys."),
    ("usage.invalid_option", "An option or explicit selection is not allowed in this mode.", "Production/fixture mix-up.",
     "`zplan help` for the options."),
    ("git.failed", "A Git command failed or timed out.", "Repository state or locks.", "Run the same git command by hand."),
    # Milestone attempts
    ("milestone.blocked", "The attempt reported it is blocked.", "A fact, access or contradiction.",
     "[t] answer and restart or [p] revise the plan."),
    ("milestone.failed", "The attempt failed and cannot continue.", "An unrecoverable failure.",
     "[t] new attempt or [p] revise the plan."),
    ("milestone.failed_recoverable", "The attempt failed but can resume.", "A transient provider or tool failure.",
     "[g] resumes in the same worktree."),
    ("milestone.conflict", "Merging the result conflicted.", "Overlapping changes in the destination.",
     "Merge the result branch by hand, commit, reopen zplan."),
    ("milestone.lost", "The attempt was interrupted and its state is unconfirmed.", "A crash or closed session.",
     "[g] reconciles with Zeroshot."),
    ("milestone.stop_unconfirmed", "Zeroshot did not confirm the stop.", "The force-stop call failed.",
     "[g] re-sends; the run stays stopping meanwhile."),
    ("milestone.preflight", "The checker preflight failed in the milestone worktree.", "A broken tool or worktree.",
     "[i] diagnostics; fix the environment and start again."),
    ("milestone.branch_exists", "The attempt branch already exists at another commit.", "A leftover branch.",
     "Delete or rename that branch."),
    ("milestone.too_many_tasks", "The milestone has more tasks than one run can execute.", "An oversized plan.",
     "[r] revise to split the milestone."),
    ("milestone.manifest_invalid", "The task manifest or an amendment is malformed.", "A worker wrote an invalid manifest.",
     "[t] new attempt; [p] revise."),
    ("milestone.merge_refused", "The merge was refused without conflicts.", "Identity, hooks or tree state, an unfinished merge (MERGE_HEAD; `git merge --abort`), or HEAD, the tree or the profile changed during the merge checks.",
     "[i] and `git status`; fix, then [m]."),
    ("milestone.merge_overlap", "The merge was not landed: it would write over files of your tree.",
     "A file the merge changes, or a parent directory of it, exists in the project as untracked, ignored or modified.",
     "The result branch is kept: move or commit those files, then merge again; the card's “show differences” lists the changes."),
    ("milestone.critic_blocked", "The merge critic blocked the candidate.", "A high risk tier or a finding the critic judged a block.",
     "Read the findings ([i], [d]); change the result or start a new attempt, then [m]."),
    ("merge.no_checks", "The merge gate is required but the profile lists no checks.", "gates.merge is `required` and `checks` is empty.",
     "List the checks in zplan.process.json, or set gates.merge to `off`."),
    ("merge.checks_failed", "The checks on the merge candidate did not pass, or could not run.",
     "A check exited non-zero or timed out, or the candidate could not be checked out.",
     "Read the evidence ([i]), fix the result, then [m]; the destination is unchanged."),
    ("merge.critic_pending", "The merge critic did not finish in the observation slice.", "The critic run is still working.",
     "zplan keeps observing the same run and lands the candidate on the critic's `go`; after leaving zplan meanwhile, [m] again observes the same run."),
    ("merge.critic_failed", "The merge critic ended without a verdict.", "The critic run failed, or its output was invalid.",
     "[m] again to start a new critic; [i] shows the diagnostic."),
    # The cause of a failed attempt, read from its own run logs: the latest observed execution failure, never a
    # proven terminal cause (see R-2/R-3 in the plan). Only the class and the bounded reset reach the screen.
    ("run.limit", "One of the attempt's executions hit a provider session or usage limit.",
     "The provider or account limit is exhausted; the log says when it resets when the provider tells it.",
     "Wait for the reset (shown when it is known) or check the account limits, then retry."),
    ("run.quota", "One of the attempt's executions was refused because the account is out of quota.",
     "No credits are left on the account.", "Top up the account, then retry."),
    ("run.auth", "One of the attempt's executions was refused for missing or invalid authorization.",
     "An expired, revoked or unreadable login.", "[l] refresh the login (`zplan login`), then retry."),
    ("run.forbidden", "One of the attempt's executions was refused with a forbidden (403) status.",
     "The provider rejects the account, the region or the workspace access.", "Check the account or the region, then retry."),
    ("run.network", "One of the attempt's executions could not reach the model service.", "A DNS, proxy or connection failure.",
     "Retry later."),
    # Export
    ("export.source_missing", "The plan's source commit is not in the project.", "History was rewritten or pruned.",
     "Revise the plan on the current project."),
    ("export.unsupported_layout", "The result contains layouts the export refuses.",
     "Submodules, nested Git, filters (LFS/ident/encoding) or special files.", "Remove them from the result or the project."),
    ("export.reserved_path", "The project tracks zplan's control directory.", ".zplan/ is committed.",
     "Untrack .zplan/ in the project."),
    ("export.snapshot_changed", "The result changed or does not match the verified candidate.",
     "Edits after acceptance or Git conversion.", "[t] new attempt."),
    ("export.branch_exists", "The result branch already exists differently.", "A leftover or concurrent export.",
     "Delete or rename the branch."),
    # Setup
    ("setup.command_failed", "A setup command could not run or exited non-zero.", "Missing tool or network.",
     "Fix the cause shown, rerun `zplan setup`; the previous install is kept."),
    ("setup.busy", "Another setup is running.", "A concurrent `zplan setup`.", "Wait for it."),
    ("setup.agent_home", "zplan could not write its agent profile (config.toml) into its own Codex home.",
     "A concurrent zplan holding the profile lock, an unwritable home, or an entry that is not a regular file.",
     "Retry; if it persists, fix the path named in the message."),
    ("setup.prerequisite", "Node.js >= 16 and npm are required.", "Not installed.", "Install Node.js/npm, rerun setup."),
    ("setup.unsupported_platform", "No pinned release for this platform.", "Not macOS arm64 or Linux x86_64/aarch64.",
     "Use a supported platform."),
    ("setup.tools_invalid", "The installed tools failed verification.", "Version or checksum mismatch.",
     "Remove the tools directory and rerun `zplan setup`."),
    ("setup.download_invalid", "The downloaded release failed verification.", "Corrupt or tampered download.",
     "Retry; nothing was installed."),
    ("setup.login_failed", "The Codex login did not finish.", "Cancelled or rejected device login, or device-code "
     "login is off for the account.",
     "If device-code login is off for the account, turn it on in the ChatGPT account security settings; then [l] or "
     "`zplan login` again."),
    # Architect turns
    ("architect.invalid_config", "The architect's executable, model or thread id is invalid.", "Bad settings.",
     "Fix the role binding with `zplan roles`."),
    ("architect.session_corrupt", "The stored architect session is damaged.", "A hand-edited or truncated file.",
     "Delete the file named in the message to start a new conversation."),
    ("architect.home_lost", "The recorded Codex home of the architect's thread is gone.",
     "That CODEX_HOME was moved or deleted, or its login is gone.",
     "Ctrl+R “new dialog” starts a new thread in the current home."),
    ("architect.project_missing", "The project directory is gone.", "Moved or deleted.", "Reopen zplan in the project."),
    ("architect.busy", "The architect is already answering.", "A turn is in progress.", "Cancel the turn or wait."),
    ("architect.closing", "The interface is leaving: no new turn or reset is accepted.", "The quit key was pressed.",
     "Start zplan again to talk to the architect."),
    ("architect.foreign_tools", "Codex would start an MCP server besides zplan's in the architect's turn, or the "
     "server list could not be checked.", "A server or plugin of your Codex config that the turn could not turn off.",
     "Remove the server named in the message from your Codex config, or fix `codex mcp list`; no turn was started."),
    ("architect.empty_message", "The message is empty.", "Nothing was typed.", "Type a message."),
    ("architect.locked", "Another zplan process talks to this project's architect.", "A second session.",
     "Close the other session."),
    # Architect read tools
    ("read.outside_project", "The path or root is outside the selected project and its worktrees.",
     "A `..` or absolute path, a link leading out, an untracked file, or a foreign root.",
     "Name a tracked file inside the project."),
    ("read.credential", "The file looks like a credential file and is never read.",
     "Its name matches a credential pattern, or it lies under `.git/` or `.zplan/`.", "Nothing to fix: by design."),
    ("read.binary", "The file is binary.", "A NUL byte in its first 8 KB.", "Read a text file."),
    ("architect.cancelled", "The owner cancelled the turn.", "Cancel key.", "Send a new message."),
    ("architect.lost_session", "Codex no longer has the stored conversation.", "Its rollout was removed.",
     "Reset to start a new conversation."),
    ("architect.auth", "Codex rejected the authorization.", "An expired login.", "`zplan login`, repeat the message."),
    ("architect.failed", "The turn ended without a result.", "A provider error, a signal or a non-zero exit.",
     "Repeat the message; the capped detail is in the transcript."),
    # Architect action tools (the live Controller boundary)
    ("architect.controller_unavailable", "The live Controller is not reachable from the architect's tools.",
     "No zplan window is serving this project, or its socket directory is gone.",
     "Open zplan in the project; the tools only reach a running Controller."),
    ("architect.controller_timeout", "The Controller did not answer an action in time; the outcome is unknown.",
     "The worker was busy past the wait (a run, a submission).",
     "Call zplan_status: the request keeps its state and its result once the job ran."),
    ("architect.request_invalid", "The architect's action tool call carried bad arguments.",
     "A missing or wrongly typed milestone, revision or run id.",
     "Call the tool with the arguments its schema names."),
    # The owner's confirmed commit of their own files (user_commit)
    ("commit.refused", "The commit of the owner's files was refused; nothing was run.",
     "No commit yet, a detached HEAD, a merge or rebase in progress, a held index.lock, a merge being landed, or none "
     "of the proposed paths is a changed file git may commit (credential files are never committed).",
     "Do what the message names (`git switch <branch>`, finish or abort the merge or rebase, wait for the other git) "
     "and ask the architect again."),
    ("commit.failed", "`git commit` did not create the commit; HEAD and the index are as they were.",
     "A hook refused, git failed, or the terminal could not be handed over.",
     "Fix what the hook or git printed and confirm the commit again."),
    # Autonomy policy
    ("autonomy.ask", "The autonomy policy asks the owner to do this action themselves.",
     "Automatic actions are off (until A7), or the level is manual, or the action is a start at a level that asks.",
     "Do it with your own key in the zplan interface."),
    # Process profile (zplan.process.json and its acceptance state)
    ("process.invalid", "The project's zplan.process.json (or its rules/checks) is not valid.",
     "A hand edit with an unknown key, a wrong type, an empty command or a rules path outside the repository.",
     "Fix the key named in the message, or delete the file and run `zplan profile init`."),
    ("process.state", "The profile's acceptance record in zplan's state directory is damaged.",
     "A hand edit or an interrupted write by another tool.",
     "Delete the file named in the message; the profile is offered again. Plans and runs are untouched."),
    ("process.missing", "The accepted zplan.process.json is gone from the project.",
     "The file was deleted or the branch without it was checked out.",
     "`git checkout -- zplan.process.json`, or `zplan profile init` to create it again."),
    ("process.pending", "The project's process profile was neither accepted nor postponed.",
     "The first-start choice was not made (the screen was left).", "Start zplan and choose accept or later, or run `zplan profile init`."),
    ("process.unbuilt", "A gate the profile requires is not implemented in this version.",
     "gates.task is `required`.", "Set the gate to `off` in zplan.process.json."),
    ("process.changed", "The profile changed after the preview was shown.",
     "zplan.process.json or the saved roles were edited meanwhile.", "Look at the preview shown again and confirm it."),
    # Interface
    ("tui.unavailable", "The full-screen interface cannot start.", "Textual is missing or not importable.",
     "`zplan --plain`, or reinstall zplan."),
    (UNKNOWN, "A failure that has no catalog family.", "An unclassified message or exception.",
     "The bounded text shown with it is the only detail: `zplan doctor`, [i] on home, then docs/REFERENCE.md."),
)

KINDS = (("plan_status", "Plan statuses", PLAN_STATUS), ("milestone_state", "Milestone states", MILESTONE_STATE),
         ("run_status", "Run statuses", RUN_STATUS), ("outcome", "Run outcomes", OUTCOME),
         ("delivery", "Delivery states", DELIVERY), ("error", "Error families", ERRORS))
PLAN_STATUS_ORDER = tuple(PLAN_STATUS)

# Screens and their actions --------------------------------------------------------------------------------------

_BACK = "Enter or q — back."
SCREENS = {s.id: s for s in (
    Screen("home", "Home screen", "Plan overview and milestone list.",
           "Enter opens what “Next” names (start and check only with their own letter); Ctrl-D quits."),
    Screen("readiness", "Readiness", "What is missing before a model run.", _BACK),
    Screen("bootstrap", "Process profile", "First start in a project without an accepted process profile.",
           "Accept writes the profile; later works from the snapshot; q quits without deciding."),
    Screen("goal", "Goal saved", "After the goal text, before the planner starts.", _BACK),
    Screen("plan", "Plan", "A plan revision at any status.", _BACK),
    Screen("observe", "Observation", "Live view of a running attempt (type a key, then Enter).",
           "Ctrl-C detaches: the run continues."),
    Screen("unknown", "Run: status unknown", "Unconfirmed submission or an interrupted attempt.", _BACK),
    Screen("awaiting_merge", "Run: done, awaiting merge", "An accepted, exported result.", _BACK),
    Screen("conflict", "Run: merge conflict", "A conflicting merge.", _BACK),
    Screen("needs_owner", "Run: answer needed", "The steward asks the owner.", _BACK),
    Screen("blocked", "Run: blocked", "A blocked attempt.", _BACK),
    Screen("failed_recoverable", "Run: failed, can be resumed", "A resumable failure.", _BACK),
    Screen("failed", "Run: failed", "An unrecoverable failure.", _BACK),
    Screen("stopped", "Run: stopped", "A stopped attempt.", _BACK),
    Screen("tui_input", "Full-screen mode: input line", "TUI main screen, input line focused (letters are text).",
           "Letters in the input line are text; enter sends a turn, esc cancels it; actions are commands starting with “/” "
           "(palette below), tab focuses the plan panel."),
    Screen("tui_panel", "Full-screen mode: plan panel", "TUI main screen, plan panel focused.",
           "Focus in the panel: arrows select a milestone; all actions are commands starting with “/” "
           "in the input line."),
    Screen("tui_plan", "Full-screen mode: plan", "TUI plan screen (goal, planner progress, proposal).",
           "Opening the screen sends nothing: only [g] starts the planner."),
    Screen("tui_note", "Full-screen mode: plan revision", "TUI revision note editor.",
           "An empty note leaves the plan unchanged."),
    Screen("tui_run", "Full-screen mode: run result", "TUI end-of-run modal of one milestone attempt.",
           "Only the actions allowed for this result are shown; the screen refreshes when the run changes."),
    Screen("tui_diff", "Full-screen mode: changes", "TUI scrollable diff of an exported result.",
           "Viewing changes nothing."),
    Screen("tui_details", "Full-screen mode: details", "TUI scrollable plan record and diagnostics.",
           "The result first, then the plan; identifiers and commands come last under the mark “For diagnostics”."),
    Screen("tui_attempt", "Full-screen mode: new attempt", "TUI form of a new attempt of a stopped or failed "
           "milestone.", "A new attempt starts from the current HEAD; the note is optional. Esc closes the form."),
    Screen("tui_answer", "Full-screen mode: answer or note", "TUI text editor for an answer, a new-attempt note "
           "or a plan change request.", "An empty answer starts nothing."),
    Screen("tui_confirm", "Full-screen mode: confirmation", "TUI confirmation of a plan or milestone decision.", ""),
    Screen("tui_confirm_run", "Full-screen mode: run confirmation",
           "TUI confirmation of a run start: “yes” is focused at once.", ""),
    Screen("tui_bootstrap", "Full-screen mode: process profile",
           "TUI first-start screen of the process profile.", "The decision is made once per project."),
    Screen("tui_profile", "Full-screen mode: profile setup",
           "TUI editor of the process profile: autonomy, parallel runs, the merge gate and the roles.",
           "Saving validates the values; on refusal the form stays open and the file is unchanged."),
    Screen("tui_settings", "Full-screen mode: settings", "TUI settings (readiness, setup log, roles).", ""),
    Screen("tui_help", "Full-screen mode: help", "The key help overlay.", ""),
)}

_ACTIONS = []


def _a(screen, name, key, label, hint, meaning, short=None, alt=()):
    """Register one action; `short` is the narrow key-bar label ("" shows the key only), `alt` extra accepted keys."""
    _ACTIONS.append(Action("%s.%s" % (screen, name), screen, key, label, label if short is None else short, hint,
                           meaning, tuple(alt)))


_a("home", "plan", "p", "plan", "open the plan: describe the goal, approve or revise", "Open the plan screen (goal when none).")
_a("home", "revise", "r", "reconsider", "revise the approved plan", "Write a revision request for the plan.")
_a("home", "settings", "s", "settings", "model and effort of the roles", "Role bindings (model/effort).")
_a("home", "details", "i", "details", "full record of the plan and runs, diagnostic commands", "Full plan and run records, diagnostic commands.")
_a("home", "quit", "q", "quit", "close zplan; runs continue", "Leave; runs continue.")
_a("home", "watch", "w", "watch", "follow the running milestone", "Observe the running attempt.")
_a("home", "check", "g", "check", "reconcile an unconfirmed submission or stop with Zeroshot", "Reconcile an unconfirmed submission/stop.")
_a("home", "start", "g", "start", "start a ready milestone (with a preview and a confirmation)", "Start a ready milestone after a preview.")
_a("home", "resume", "g", "continue", "continue the same attempt after a failure (resume)", "Resume the failed, recoverable attempt.")
_a("home", "attempt", "g", "new attempt", "start a new attempt of a stopped or failed milestone", "Start a new attempt after a stop or an unrecoverable failure.")
_a("home", "open", "o", "open", "the end screen of a milestone that needs attention", "Open the end screen of a milestone that needs attention.")
_a("home", "tail", "e", "log", "the last lines of the Zeroshot log (on request): a running or failed run", "Show the tail of the run log.")

_a("readiness", "install", "u", "install tools", "install the pinned Zeroshot and Codex", "Run setup.")
_a("readiness", "login", "l", "log in", "log in to Codex in this terminal", "Run the Codex login.")
_a("readiness", "changes", "d", "changes", "show uncommitted changes (changes nothing)", "List uncommitted changes; changes nothing.")
_a("readiness", "recheck", "g", "check again", "repeat the check after the fix", "Re-run the readiness check.")
_a("readiness", "details", "i", "details", "instructions for each finding", "Fix instructions for each item.")
_a("readiness", "back", "q", "back", "go back", "Return to the previous screen.")
_a("readiness", "leave", "q", "quit", "quit zplan", "Leave zplan (the first readiness screen).")

_a("bootstrap", "accept", "a", "accept", "write zplan.process.json and accept the profile", "Accept the proposed profile (writes the file).")
_a("bootstrap", "later", "l", "later", "work from the proposal without writing to the project", "Postpone; the snapshot is used and the header says so.")
_a("bootstrap", "leave", "q", "quit", "quit without deciding", "Leave without deciding.")

_a("goal", "start", "g", "start the planner", "check readiness and submit the goal to the planner", "Check readiness, then submit the goal.")
_a("goal", "settings", "s", "settings", "edit the roles before starting", "Edit roles before submitting.")
_a("goal", "back", "q", "back", "leave the goal unsaved and go back", "Leave without saving the goal.")

_a("plan", "start", "g", "start the planner", "check readiness and submit the goal; a stale unsent plan is first rebuilt on the current project; an unconfirmed submission is sent again unchanged",
   "Check readiness, then submit the unsent revision; a stale unsent one is first rebuilt on the current project; an unconfirmed submission is sent again unchanged.")
_a("plan", "renew", "n", "prepare a new plan on the current project", "the same goal on the current project state; no model is run",
   "Prepare a new unsent revision, same goal, current project; nothing is sent.")
_a("plan", "details", "i", "details", "full record and diagnostic commands", "Full record and diagnostics.")
_a("plan", "tail", "e", "log", "the last lines of the planner's Zeroshot log (on request)", "Show the tail of the planner run log.")
_a("plan", "watch", "w", "watch", "follow the planner", "Watch the planner.")
_a("plan", "stop", "s", "stop planning", "stop the running planner", "Stop the running planner; the run is never resubmitted.")
_a("plan", "approve", "a", "approve", "approve the plan; no implementation is started", "Approve this revision (starts nothing).")
_a("plan", "revise", "r", "revise", "write what to change and re-plan", "Request a revision.")
_a("plan", "reject", "x", "decline", "do not approve the proposal", "Decline the proposal.")
_a("plan", "requirements", "i", "requirements and checks", "the full plan: requirements, tasks, checks", "Full plan with requirements and checks.")
_a("plan", "override", "o", "approve despite the check", "approve a plan the check rejected; a reason is required",
   "Approve a plan the critic rejected, with a typed reason (starts nothing).")
_a("plan", "restart", "g", "start the planner again", "a new revision of the same goal", "Run the planner again.")
_a("plan", "retry", "g", "check readiness and start again", "check readiness and submit a new revision", "Check readiness and resubmit.")
_a("plan", "login", "l", "refresh login", "log in to Codex again", "Refresh the Codex login.")
_a("plan", "back", "q", "back", "return to the home screen", "Back to home.")

_a("observe", "stop", "k", "stop", "k and Enter: stop the attempt (after a confirmation)", "Stop the attempt after a confirmation.")
_a("observe", "detach", "Ctrl-C", "detach", "quit; the run continues", "Detach; the run continues.")
_a("observe", "help", "?", "help", "this help", "This help.")
_a("observe", "tail", "e", "log", "the last lines of the Zeroshot log (on request)", "Show the tail of the run log.")

_a("unknown", "check", "g", "check", "reconcile with Zeroshot without resubmitting", "Reconcile without resubmitting.")
_a("unknown", "back", "q", "back", "go back", "Back.")
_a("awaiting_merge", "merge", "m", "merge into %s", "merge the result (merge --ff-only of the finished commit) after a confirmation", "Merge the result branch after a confirmation.")
_a("awaiting_merge", "diff", "d", "diff", "show the result's changes", "Show the result's diff.")
_a("awaiting_merge", "later", "l", "later", "go back, changing nothing", "Leave unmerged.")
_a("conflict", "merge", "m", "retry the merge", "retry the merge (after a manual resolution)", "Retry the merge.")
_a("conflict", "diff", "d", "diff", "show the result's changes", "Show the result's diff.")
_a("conflict", "later", "l", "later", "go back, changing nothing", "Leave as is.")
_a("needs_owner", "accept", "a", "accept", "accept the steward's proposal", "Accept the steward's proposal.")
_a("needs_owner", "answer", "t", "answer", "answer and start a new attempt", "Answer and start a new attempt.")
_a("needs_owner", "stop", "x", "stop", "leave unanswered", "Leave unanswered.")
_a("needs_owner", "back", "q", "back", "go back", "Back.")
_a("blocked", "answer", "t", "answer and restart", "answer and start a new attempt", "Answer and start a new attempt.")
_a("blocked", "plan", "p", "plan", "revise the plan", "Revise the plan.")
_a("blocked", "back", "q", "back", "go back", "Back.")
_a("failed_recoverable", "resume", "g", "continue", "continue the same attempt in its worktree", "Resume the same attempt.")
_a("failed_recoverable", "new_attempt", "t", "new attempt", "start an attempt from the current HEAD", "New attempt from the current HEAD.")
_a("failed_recoverable", "plan", "p", "plan", "revise the plan", "Revise the plan.")
_a("failed_recoverable", "back", "q", "back", "go back", "Back.")
_a("failed", "new_attempt", "t", "new attempt", "start an attempt from the current HEAD", "New attempt from the current HEAD.")
_a("failed", "plan", "p", "plan", "revise the plan", "Revise the plan.")
_a("failed", "back", "q", "back", "go back", "Back.")
_a("stopped", "new_attempt", "t", "new attempt", "start an attempt from the current HEAD", "New attempt from the current HEAD.")
_a("stopped", "plan", "p", "plan", "revise the plan", "Revise the plan.")
_a("stopped", "back", "q", "back", "go back", "Back.")

_a("tui_input", "panel", "tab", "panel", "move to the plan panel",
   "Focus the plan panel; with the `/` palette shown and a command prefix typed, complete the highlighted command instead.")
_a("tui_input", "pick", "up", "pick", "a command in the palette or the previous line",
   "Up/Down move the palette highlight; in an empty input they recall the owner's previous lines of this run.", alt=("down",))
_a("tui_input", "send", "enter", "send", "send the message to the architect as one turn",
   "Send the typed message to the architect as one turn.", short="send")
_a("tui_input", "cancel", "esc", "cancel turn", "interrupt the architect's turn (a milestone is not touched)",
   "Cancel the running architect turn; a milestone keeps running.", short="cancel")
_a("tui_input", "reset", "/new", "new dialog", "start a new dialog with the architect",
   "Start a new architect session; the transcript keeps a reset entry.", short="new")
_a("tui_input", "settings", "/setup", "settings", "open settings", "Open settings.", short="sett.")
_a("tui_input", "help", "/help", "keys", "help on this screen's commands", "Key and command help.",
   short="")
_a("tui_input", "quit", "ctrl+q", "quit", "quit", "Quit.")
_a("tui_panel", "input", "tab", "input", "return to the input line", "Focus the input line.")
_a("tui_panel", "plan", "/view", "plan", "open the plan: goal, progress, proposal (with no plan — /plan <goal>)", "Open the plan screen; with no plan, a note names `/plan <goal>`.")
_a("tui_panel", "answer_draft", "/answer", "answer draft",
   "open the newest answer draft of a milestone in the answer form",
   "Open the newest actionable answer draft of the selected milestone in the answer form; nothing is submitted. "
   "A malformed identity, a still-running attempt and an end that offers no answer are refused as "
   "`draft.malformed`, `draft.active` and `draft.unavailable`, and a moved-on draft as `draft.stale`.",
   short="answer")
_a("tui_panel", "run", "/run", "start", "start the selected ready milestone", "Start the selected ready milestone "
   "after a confirmation.")
_a("tui_panel", "resume", "/run", "continue", "continue the same attempt in its worktree", "Resume the failed attempt "
   "after a confirmation.")
_a("tui_panel", "attempt", "/run", "new attempt", "a new attempt of a stopped or failed milestone",
   "Open the new-attempt form of a stopped or failed milestone.", short="new att.")
_a("tui_panel", "check", "/run", "check", "reconcile an unconfirmed submission or stop with Zeroshot",
   "Reconcile an unconfirmed submission or stop; nothing is sent again.")
_a("tui_panel", "stop", "/stop", "stop", "stop the running run",
   "Stop the running attempt after a confirmation.", short="stop")
_a("tui_panel", "open", "/attempt", "open", "the end result of a milestone run; a running run is watched again",
   "Open the end-of-run view of the selected milestone; a running attempt is observed again.")
_a("tui_panel", "details", "/details", "details", "result, plan, diagnostics", "Outcome first, then the plan, "
   "diagnostics last.", short="det.")
_a("tui_panel", "tail", "/log", "log", "the last lines of the Zeroshot log (on request)", "Show the tail of the run log.", short="log")
_a("tui_panel", "select", "↑↓", "select", "select a milestone", "Select a milestone row.", short="")
_a("tui_panel", "scroll_up", "pageup", "history up", "scroll the chat history to the start (PgUp)",
   "Scroll the chat history up: its oldest retained rows become reachable; nothing else changes.", short="")
_a("tui_panel", "scroll_down", "pagedown", "history down", "scroll the chat history to the end (PgDn)",
   "Scroll the chat history back down toward the newest rows.", short="")
_a("tui_panel", "settings", "/setup", "settings", "open settings", "Open settings.", short="sett.")
_a("tui_panel", "help", "/help", "keys", "this help", "Key and command help.", short="")
_a("tui_panel", "quit", "ctrl+q", "quit", "quit", "Quit.")
_a("tui_run", "move", "tab", "to button", "move to the next button (Tab, ←/→ switch buttons)", "Move to the next button (Tab, Left/Right switch buttons).")
_a("tui_run", "press", "enter", "press", "press the focused button; ↑↓ PgUp PgDn scroll the result", "Press the focused button; arrows and PgUp/PgDn scroll the end screen.")
_a("tui_run", "merge", "enter", "merge", "merge the result into the destination branch", "Merge the exported result "
   "after a confirmation.")
_a("tui_run", "diff", "enter", "changes", "show the result's changes", "Show the result's diff.", short="")
_a("tui_run", "accept", "enter", "accept", "accept the steward's proposal",
   "Accept the steward's proposal.")
_a("tui_run", "answer", "enter", "answer", "answer in a note: a new attempt with it", "Answer in a note; a "
   "new attempt starts with it.")
_a("tui_run", "attempt", "enter", "new attempt", "note optional",
   "A new attempt from the destination HEAD.", short="new")
_a("tui_run", "plan", "enter", "to plan", "the request goes to plan revision", "Route a scope change back to "
   "plan revision.", short="plan")
_a("tui_run", "resume", "enter", "continue", "continue the same attempt in its worktree", "Resume the same attempt.")
_a("tui_run", "check", "enter", "check", "reconcile with Zeroshot, no resubmit",
   "Reconcile an unconfirmed submission or stop; never resubmits.")
_a("tui_run", "tail", "enter", "log", "the last lines of the Zeroshot log (on request)", "Show the tail of the run log.", short="log")
_a("tui_run", "details", "enter", "details", "attempt journal: the saved observation entries",
   "The retained journal entries of this attempt, from the store; no native log is read.", short="det.")
_a("tui_run", "leave", "enter", "leave", "leave unanswered", "Leave unanswered.")
_a("tui_run", "back", "esc", "close", "close; nothing changes", "Close; nothing changes.",
   short="")
_a("tui_diff", "scroll", "↑↓", "scroll", "scroll the changes", "Scroll the diff.", short="")
_a("tui_diff", "close", "esc", "close", "return to the run result", "Close the diff.")
_a("tui_details", "scroll", "↑↓", "scroll", "scroll the details", "Scroll the details.", short="")
_a("tui_details", "close", "esc", "close", "return to the home screen", "Close the details.")
_a("tui_answer", "button", "tab", "to button", "from the text field move to the “send” button", "Move from the text field to the send button.", short="")
_a("tui_answer", "send", "enter", "send", "Enter on the “send” button: send the text (an empty answer starts nothing)", "Press the send button: send the text.")
_a("tui_answer", "back", "esc", "back", "close without changes", "Close without changes.", short="")
_a("tui_attempt", "button", "tab", "to button", "from the text field move to the “start attempt” button", "Move from the text field to the start button.", short="")
_a("tui_attempt", "send", "enter", "start attempt", "Enter on the “start attempt” button: start a new attempt (the note is optional)",
   "Press the start button: start the new attempt with the note (may be empty).", short="start")
_a("tui_attempt", "back", "esc", "back", "close without changes: the attempt does not start", "Close; nothing starts.",
   short="")
_a("tui_plan", "move", "tab", "to button", "move to the next button (Tab, ←/→ switch buttons)", "Move to the next button (Tab, Left/Right switch buttons).")
_a("tui_plan", "press", "enter", "press", "press the focused button; ↑↓ PgUp PgDn scroll the plan", "Press the focused button; arrows and PgUp/PgDn scroll the plan.")
_a("tui_plan", "run", "enter", "start the planner", "check readiness and submit the goal; a stale unsent plan is first rebuilt on the current project; an unconfirmed submission is sent again unchanged",
   "Check readiness, then submit the unsent or failed revision; a stale unsent one is first rebuilt on the current "
   "project.", short="start")
_a("tui_plan", "renew", "enter", "new revision", "the same goal on the current project", "New revision, same goal, current project.",
   short="new")
_a("tui_plan", "login", "enter", "log in", "log in to Codex again (the terminal is suspended)", "Codex login under suspend.",
   short="")
_a("tui_plan", "watch", "enter", "watch", "follow the planner", "Resume watching the planner.", short="")
_a("tui_plan", "tail", "enter", "log", "the last lines of the planner's Zeroshot log (on request)", "Show the tail of the planner run log.", short="log")
_a("tui_plan", "approve", "enter", "approve", "approve the plan; no implementation is started", "Approve (starts nothing).")
_a("tui_plan", "override", "enter", "approve despite the check", "approve a plan the check rejected; a reason is required",
   "Approve a plan the critic rejected, with a typed reason (starts nothing).", short="despite")
_a("tui_plan", "revise", "enter", "revise", "write what to change and re-plan", "Request a revision.",
   short="revise")
_a("tui_plan", "reject", "enter", "decline", "do not approve the proposal", "Decline the proposal.", short="decline")
_a("tui_plan", "info", "enter", "details", "requirements and checks; for a failure, diagnostics", "Full requirements and "
   "checks, or the diagnostics of a failure.", short="det.")
_a("tui_plan", "back", "esc", "back", "return to the home screen", "Back to the main screen.", short="")
_a("tui_plan", "quit", "ctrl+q", "quit", "quit", "Quit.")
_a("tui_note", "button", "tab", "to button", "from the text field move to the “send revision” button", "Move from the text field to the send button.", short="")
_a("tui_note", "send", "enter", "send revision", "Enter on the “send revision” button: re-plan with this text", "Press the send button: send the revision request.",
   short="send")
_a("tui_note", "back", "esc", "back", "close without changes", "Close without changes.", short="")
_a("tui_confirm", "yes", "tab", "yes", "move to the “yes” button (Tab, ←/→ switch buttons)", "Move to the “yes” button (Tab, Left/Right switch buttons).")
_a("tui_confirm", "press", "enter", "press", "press the focused button; focus starts on “no”, on “yes” for a run start", "Press the focused button; it starts on “no”, on “yes” for a run start.")
_a("tui_confirm_run", "start", "enter", "start", "“yes” is already focused: Enter starts at once", "“yes” is already focused: Enter starts at once.")
_a("tui_confirm", "no", "esc", "no", "cancel; nothing changes", "Cancel; nothing changes.")
_a("tui_bootstrap", "accept", "enter", "accept", "the “accept” button (focused at once): write zplan.process.json and accept the profile", "The “accept” button, focused at once: accept the proposed profile (writes the file).")
_a("tui_bootstrap", "configure", "right", "configure", "move to the “configure” button (→): set your own values before the file is written", "Move to the “configure” button: set your own values before the file is written.")
_a("tui_bootstrap", "later", "tab", "later", "move on to the “later” button (Tab or →, after “configure”): work from the proposal without writing to the project", "Move to the “later” button: postpone; the snapshot is used and the header says so.")
_a("tui_bootstrap", "quit", "ctrl+q", "quit", "quit without deciding", "Quit without deciding.")
_a("tui_profile", "move", "←→/tab", "move", "move to another button or field (←/→ switch buttons within a row, Tab goes to the next field)", "Move between buttons and fields (Left/Right switch buttons within a row; Tab goes to the next field).")
_a("tui_profile", "pick", "enter/space", "pick", "pick the focused button: it gets the mark “● ”", "Pick the focused button; the picked one is marked «● ».")
_a("tui_profile", "save", "ctrl+s", "save", "validate the values and write the profile (the “save” button does the same)", "Validate the values and write the profile (the “save” button does the same).")
_a("tui_profile", "cancel", "esc", "cancel", "close the form, writing nothing", "Close the editor; nothing is written.")
_a("tui_settings", "move", "tab", "to button", "move to the next button (Tab, ←/→ switch buttons)", "Move to the next button (Tab, Left/Right switch buttons).")
_a("tui_settings", "press", "enter", "press", "press the focused button", "Press the focused button.")
_a("tui_settings", "setup", "enter", "install", "install tools", "Run setup with a live log.", short="")
_a("tui_settings", "login", "enter", "log in", "log in to Codex (the terminal is suspended)", "Codex login under suspend.", short="")
_a("tui_settings", "recheck", "enter", "check", "check readiness again", "Re-check readiness.", short="")
_a("tui_settings", "roles", "enter", "roles", "show the roles", "Toggle the roles view.", short="")
_a("tui_settings", "profile", "right", "profile", "open the process profile: autonomy, parallelism, merge, roles", "Edit the accepted process profile.", short="")
_a("tui_settings", "back", "esc", "back", "return to the home screen", "Back to the main screen.", short="")
_a("tui_settings", "quit", "ctrl+q", "quit", "quit", "Quit.")
_a("tui_help", "close", "esc", "close", "close the help", "Close the help.")

ACTIONS = {a.id: a for a in _ACTIONS}
del _ACTIONS


def action(action_id):
    return ACTIONS[action_id]


def label(action_id, *args):
    found = ACTIONS[action_id]
    return found.label % args if args else found.label


def text(action_id, *args):
    """`[k] label` exactly as a menu shows it."""
    return "[%s] %s" % (ACTIONS[action_id].key, label(action_id, *args))


def keys_of(*action_ids):
    return {ACTIONS[i].key for i in action_ids}


class Menu(str):
    """A menu line that remembers the screen and action IDs behind it, so `?` can explain exactly these keys."""

    def __new__(cls, line, ids):
        self = super().__new__(cls, line)
        self.ids = tuple(ids)
        return self


def menu(*items):
    """Menu line of catalog actions; an item is an ID or (ID, label argument...)."""
    parts, ids = [], []
    for item in items:
        action_id, args = (item, ()) if isinstance(item, str) else (item[0], tuple(item[1:]))
        parts.append(text(action_id, *args))
        ids.append(action_id)
    return Menu("  ".join(parts), ids)


def variants(screen, include=None):
    """Key bar of a TUI screen as (labels, short labels, keys only): the widest that fits is shown."""
    # `include` names the actions to show: with it the bar follows those IDs whatever their screen, so an
    # end screen can present the delivery catalog's own actions (A1's [g]/[t]/[p]/[q]) beside its tui_run ones.
    chosen = [a for a in ACTIONS.values()
              if (a.screen == screen and include is None) or (include is not None and a.id in include)]

    def part(a, shown):
        return "[%s] %s" % (a.key, shown) if shown else "[%s]" % a.key
    return ("  ".join(part(a, a.label) for a in chosen), "  ".join(part(a, a.short) for a in chosen),
            " ".join(a.key for a in chosen))


def bar(screen, include, width, primary=(), keep=("help",), reserve=()):
    """The key bar of a TUI screen for `width` terminal cells: whole actions only, never cut mid-word, and every
    action that is shown keeps a nonempty label while the bar can afford it.

    `width` is the usable width of the bar widget. The mandatory actions are the offered ones named by `primary`,
    `reserve` or `keep`: the actions the screen cannot do without. Let M be the width of the mandatory actions
    joined with the same separators, each at its shortest nonempty catalog label (its short label when it has one,
    else its full label): M is the least the bar can be with every mandatory action still labelled.

    Whenever `width >= M`, every displayed action has a nonempty label (R-1): the label is given up by the
    lower-priority keys first, in reverse catalog order and never to an empty one. The bar first takes every
    action's full label, then the shortest nonempty label of the secondary actions (not in `primary` or `reserve`),
    then drops those optional actions (`keep` names stay); only then do the primary and, last, the `reserve`d
    actions lose their full label (down to their shortest nonempty one). The mandatory actions are never dropped
    and never left unlabelled. When `width < M` the previous fallback is preserved: the secondary actions lose
    their label (short label, then the key alone); whole secondary actions are dropped from the end (`keep` names
    stay); the primary ones lose their label (short label, then the key alone); as a last resort the primary ones
    are dropped from the end too (`keep` stays). A `reserve`d action gives up its label only after every other
    action has lost its label or been dropped."""
    # `include` names the actions to show: with it the bar follows those IDs whatever their screen, so an
    # end screen can present the delivery catalog's own actions (A1's [g]/[t]/[p]/[q]) beside its tui_run ones.
    chosen = [a for a in ACTIONS.values()
              if (a.screen == screen and include is None) or (include is not None and a.id in include)]
    name = [a.id.split(".", 1)[1] for a in chosen]
    needed = [n in primary or n in reserve or n in keep for n in name]

    def part(a, shown):
        return "[%s] %s" % (a.key, shown) if shown else "[%s]" % a.key

    def joined(items):
        return "  ".join(part(a, shown) for a, shown in items)

    def shortest(a):
        return a.short or a.label

    def optional(n):
        return n not in primary and n not in reserve

    def main(n):
        return n not in reserve

    floor = joined([(a, shortest(a)) for a, need in zip(chosen, needed) if need])
    if cells(floor) <= width:
        # W >= M (R-1): no shown action goes unlabelled; the lower-priority keys give up their label, then go.
        levels = [0] * len(chosen)

        def render():
            return joined([(a, (a.label, shortest(a))[levels[i]]) for i, a in enumerate(chosen)])

        def shorten(pick):
            for i in reversed(range(len(chosen))):
                if cells(render()) <= width:
                    return True
                if pick(name[i]) and levels[i] == 0:
                    levels[i] = 1
            return cells(render()) <= width

        def drop(pick):
            index = next((i for i in reversed(range(len(chosen))) if pick(name[i])), None)
            if index is None:
                return False
            del chosen[index], levels[index], name[index], needed[index]
            return True

        if shorten(optional):
            return render()
        while cells(render()) > width and drop(lambda n: optional(n) and n not in keep):
            pass  # whole secondary actions go, lowest priority first; help stays
        if shorten(main) or shorten(lambda n: n in reserve):
            return render()
        return render()

    levels = [0] * len(chosen)

    def render():
        return joined([(a, (a.label, a.short, "")[levels[i]]) for i, a in enumerate(chosen)])

    def shrink(step, pick):
        for i in reversed(range(len(chosen))):
            if cells(render()) <= width:
                return True
            if pick(name[i]):
                levels[i] = step
        return cells(render()) <= width

    def drop(pick):
        index = next((i for i in reversed(range(len(chosen))) if pick(name[i])), None)
        if index is None:
            return False
        del chosen[index], levels[index], name[index], needed[index]
        return True

    if shrink(1, optional) or shrink(2, optional):
        return render()
    while cells(render()) > width and drop(lambda n: optional(n) and n not in keep):
        pass  # whole secondary actions go, lowest priority first; help stays
    if shrink(1, main) or shrink(2, main):
        return render()
    while cells(render()) > width and len(chosen) > 1 and drop(lambda n: main(n) and n not in keep):
        pass
    if shrink(1, lambda n: n in reserve) or shrink(2, lambda n: n in reserve):
        return render()
    while cells(render()) > width and len(chosen) > 1 and drop(lambda n: n in reserve and n not in keep):
        pass
    return render()


def key_lines(screen, ids=None):
    """One line per action of the screen (only the offered ones when `ids` is given): `[key] label — hint`."""
    lines = []
    for a in ACTIONS.values():
        if a.screen == screen and (ids is None or a.id in ids):
            keys = " / ".join((a.key,) + a.alt)
            lines.append("  [%s]  %s — %s" % (keys, label(a.id, "…") if "%s" in a.label else a.label, a.hint))
    return lines


def help_lines(screen, ids=None):
    """The owner's key help of one screen, from the same actions its menu or key bar is built from."""
    found = SCREENS[screen]
    lines = ["Keys · " + found.title] + key_lines(screen, ids)
    if found.footer:
        lines.append("  " + found.footer)
    return lines


def family(error):
    """The catalog family of a raised error; `unknown_error` when it carries none (or an unknown one)."""
    found = getattr(error, "family", None)
    return found if found in ERRORS else UNKNOWN


def tag(error_or_family):
    """The code shown next to a failure: ` [code: plan.stale]`."""
    value = error_or_family if isinstance(error_or_family, str) else family(error_or_family)
    return " [code: %s]" % (value if value in ERRORS else UNKNOWN)


# Generated reference tables --------------------------------------------------------------------------------------

def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def commands_table():
    from . import commands
    rows = []
    for item in commands.COMMANDS:
        shown = "`zplan`" if item.name == commands.START else "`zplan %s`" % item.name
        rows.append((shown, "`%s`" % item.usage, item.purpose, item.meaning))
    flags = [("`%s`" % commands.flag_text(f), ", ".join(c if c != commands.START else "(none)" for c in f.commands)
              or "all", f.purpose, f.meaning) for f in commands.FLAGS]
    return "\n".join([_table(("Command", "Usage", "Purpose (as in `--help`)", "Meaning"), rows), "",
                      _table(("Flag", "Commands", "Purpose (as in `--help`)", "Meaning"), flags)])


def keys_table():
    rows = []
    for a in ACTIONS.values():
        rows.append(("`%s`" % a.screen, "`%s`" % " / ".join((a.key,) + a.alt), "`%s`" % a.id,
                     a.label if "%s" not in a.label else a.label % "<branch>", a.hint, a.meaning))
    return _table(("Screen", "Key", "Action ID", "Label (as shown)", "Hint (as in `?`)", "Meaning"), rows)


def screens_table():
    return _table(("Screen", "Title (as shown)", "Meaning"),
                  [("`%s`" % s.id, s.title, s.meaning) for s in SCREENS.values()])


def entries_table(kind):
    entries = next(items for name, _, items in KINDS if name == kind)
    return _table(("ID", "Meaning", "Likely cause", "Owner remedy"),
                  [("`%s`" % e.id, e.meaning, e.cause, e.remedy) for e in entries.values()])


SECTIONS = (("commands", commands_table), ("screens", screens_table), ("keys", keys_table),
            ("plan_status", lambda: entries_table("plan_status")),
            ("milestone_state", lambda: entries_table("milestone_state")),
            ("run_status", lambda: entries_table("run_status")), ("outcome", lambda: entries_table("outcome")),
            ("delivery", lambda: entries_table("delivery")), ("error", lambda: entries_table("error")))


def begin(name):
    return "<!-- BEGIN GENERATED: %s -->" % name


def end(name):
    return "<!-- END GENERATED: %s -->" % name


def generated(name):
    return dict(SECTIONS)[name]()


def render(document):
    """`document` with every generated block replaced by the current tables; a missing marker is an error."""
    for name, build in SECTIONS:
        start, stop = begin(name), end(name)
        if start not in document or stop not in document:
            raise SystemExit("docs/REFERENCE.md: missing markers for %r" % name)
        head, rest = document.split(start, 1)
        _, tail = rest.split(stop, 1)
        document = head + start + "\n" + build() + "\n" + stop + tail
    return document


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] in ("--write", "--check"):
        from pathlib import Path
        path = Path(argv[1])
        current = path.read_text(encoding="utf-8")
        wanted = render(current)
        if argv[0] == "--check":
            print("docs current" if wanted == current else "docs stale")
            return 0 if wanted == current else 1
        path.write_text(wanted, encoding="utf-8")
        return 0
    print("usage: python -m terminal_planner.catalog --write|--check docs/REFERENCE.md", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
