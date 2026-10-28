"""Pure plan task tree: milestone -> slice -> task, with each task's status from the delivery manifest.

`build()` takes the approved `proposal` (the `authority.validate_proposal` shape) and, per milestone, the latest
attempt's manifest (`runs.read_manifest`, None before delivery or when absent); `lines()` renders the tree as plain
text. No I/O: the caller supplies both documents.
"""

from dataclasses import dataclass
from typing import Tuple

from .runs import current_task


STATUSES = ("done", "current", "open", "dropped")
MARKS = {"done": "✓", "current": "▸", "open": "·", "dropped": "✗"}
INDENT = "  "


@dataclass(frozen=True)
class Task:
    """One task: `status` is one of `STATUSES`; `added` marks a manifest task outside the proposal."""
    id: str
    title: str
    status: str
    added: bool = False


@dataclass(frozen=True)
class Slice:
    """One slice of a milestone with its plan tasks, in plan order."""
    id: str
    title: str
    tasks: Tuple[Task, ...]


@dataclass(frozen=True)
class Milestone:
    """One milestone: its slices, the manifest tasks outside the plan (`added`, after the slices) and the counter
    (`done` of `total` = every task not dropped, added ones included)."""
    id: str
    title: str
    slices: Tuple[Slice, ...]
    added: Tuple[Task, ...] = ()
    done: int = 0
    total: int = 0


def build(proposal, manifests):
    """Milestone nodes of `proposal` in plan order; `manifests` maps a milestone id to its manifest or None.

    A task's status comes from the manifest; the first open task of a milestone with a manifest is `current`. A
    manifest task whose id is not a plan id anywhere in the proposal is an `added` node after the slices, with its
    own status. A milestone without a manifest shows every task open and no current."""
    proposal_ids = {task["id"] for milestone in proposal["milestones"]
                    for slice_ in milestone["slices"] for task in slice_["tasks"]}
    tree = []
    for milestone in proposal["milestones"]:
        manifest = manifests.get(milestone["id"])
        statuses = {task["id"]: task["status"] for task in manifest["tasks"]} if manifest else {}
        found = current_task(manifest)
        current_id = found[2] if found else None

        def status(task_id):
            value = statuses.get(task_id, "open")
            return "current" if value == "open" and task_id == current_id else value

        slices = []
        for slice_ in milestone["slices"]:
            tasks = []
            for task in slice_["tasks"]:
                tasks.append(Task(task["id"], task["title"], status(task["id"])))
            slices.append(Slice(slice_["id"], slice_["title"], tuple(tasks)))
        added = tuple(Task(task["id"], task["title"], status(task["id"]), added=True)
                      for task in (manifest["tasks"] if manifest else []) if task["id"] not in proposal_ids)
        statuses_of = [task.status for slice_ in slices for task in slice_.tasks] + [task.status for task in added]
        tree.append(Milestone(milestone["id"], milestone["title"], tuple(slices), added,
                              statuses_of.count("done"), sum(value != "dropped" for value in statuses_of)))
    return tree


def lines(tree):
    """Plain text of `build`: two spaces of indent per level, one status mark per task and a `done/total` counter on
    the milestone line. An added task shows `+ `, then its mark, at slice indent."""
    out = []
    for milestone in tree:
        out.append("%s %s %d/%d" % (milestone.id, milestone.title, milestone.done, milestone.total))
        for slice_ in milestone.slices:
            out.append(INDENT + "%s %s" % (slice_.id, slice_.title))
            for task in slice_.tasks:
                out.append(INDENT * 2 + "%s %s %s" % (MARKS[task.status], task.id, task.title))
        for task in milestone.added:
            out.append(INDENT + "+ %s %s %s" % (MARKS[task.status], task.id, task.title))
    return out
