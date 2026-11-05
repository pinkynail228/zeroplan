"""The shared Application Service: typed owner-message operations over the existing architect store."""

from dataclasses import replace
import fcntl
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from terminal_planner import application
from terminal_planner.architect import Architect, ArchitectStore, TurnResult, parse_drafts
from terminal_planner.authority import Blocked


class FakeArchitect:
    """The provider boundary: no process or network, with the real durable store beside it."""

    def __init__(self, store, result=None):
        self.store = store
        self.project = store.project
        self.model = "fake-model"
        self.result = result or TurnResult()
        self.result.status = "completed"
        self.result.text = "answer"
        self.calls = []
        self.rows_at_call = []

    def send(self, text, snapshot=None, on_event=None, role="owner", turn=None, recorded=False, turn_id=None):
        self.calls.append({"text": text, "snapshot": snapshot, "role": role, "turn": turn,
                           "recorded": recorded, "turn_id": turn_id})
        self.rows_at_call.append(self.store.transcript())
        return self.result


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="zs-app-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        self.project.mkdir()
        self.store = ArchitectStore(self.project)
        self.architect = FakeArchitect(self.store)
        self.service = application.ApplicationService(self.architect, store=self.store)

    def request(self, text="Ship the smallest path"):
        return self.service.new_request(text, snapshot={"revision": 1})

    def operations(self):
        path = self.store.directory / "operations.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_send_persists_a_typed_owner_message_before_the_provider_and_completes_the_operation(self):
        request = self.request()
        result = self.service.send_message(request)
        self.assertEqual(result.status, "completed")
        self.assertFalse(result.replayed)
        self.assertEqual((result.operation_id, result.message_id, result.turn_id),
                         (request.operation_id, request.message_id, request.turn_id))
        self.assertEqual(len(self.architect.calls), 1)
        call = self.architect.calls[0]
        self.assertTrue(call["recorded"])
        (row,) = self.architect.rows_at_call[0]
        self.assertEqual(row["role"], "owner")
        self.assertEqual(row["text"], request.text)
        self.assertEqual((row["id"], row["project_id"], row["conversation_id"], row["turn_id"], row["operation_id"]),
                         (request.message_id, request.project_id, request.conversation_id, request.turn_id,
                          request.operation_id))
        self.assertIsInstance(row["ts"], str)
        self.assertEqual(self.operations()[-1]["state"], "completed")
        self.assertEqual(self.service.conversation_id(), request.conversation_id)

    def test_reopening_and_replaying_the_same_operation_does_not_call_the_provider_or_duplicate_history(self):
        request = self.request()
        first = self.service.send_message(request)
        reopened = application.ApplicationService(self.architect, store=ArchitectStore(self.project))
        second = reopened.send_message(request)
        self.assertEqual(first.turn.text, second.turn.text)
        self.assertTrue(second.replayed)
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(len(self.store.transcript()), 1)
        self.assertEqual(reopened.conversation_id(), request.conversation_id)
        self.assertEqual(len(self.operations()), 2)  # running + terminal, no new operation on replay

    def test_an_operation_id_cannot_be_reused_for_another_request(self):
        request = self.request()
        self.service.send_message(request)
        changed = replace(request, text="another goal")
        with self.assertRaises(Blocked) as raised:
            self.service.send_message(changed)
        self.assertEqual(raised.exception.family, "operation.conflict")
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(len(self.store.transcript()), 1)

    def test_a_provider_failure_keeps_the_owner_message_and_replays_the_same_outcome(self):
        self.architect.result.status = "failed"
        self.architect.result.cause = "provider unavailable"
        request = self.request()
        first = self.service.send_message(request)
        second = self.service.send_message(request)
        self.assertEqual((first.status, second.status, second.replayed), ("failed", "failed", True))
        self.assertEqual(second.turn.cause, "provider unavailable")
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(len(self.store.transcript()), 1)
        self.assertEqual(self.operations()[-1]["state"], "failed")

    def test_the_operation_journal_excludes_raw_provider_messages_and_scrubs_process_output(self):
        secret = "sk-abcdefghijklmnop"
        self.architect.result.messages = [{"command": "echo " + secret, "output": secret}]
        self.architect.result.stderr_tail = "api_key: " + secret
        self.architect.result.detail = "Authorization: Bearer " + secret
        self.architect.result.text = "```zplan-goal\napi_key: " + secret + "\n```"
        self.architect.result.drafts = parse_drafts(self.architect.result.text, {})
        request = self.request()
        self.service.send_message(request)
        stored = (self.store.directory / "operations.jsonl").read_text()
        self.assertNotIn(secret, stored)
        self.assertNotIn('"messages"', stored)
        replay = self.service.send_message(request)
        self.assertTrue(replay.replayed)
        self.assertNotIn(secret, json.dumps(replay.turn.drafts))
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(replay.turn.status, "completed")

    def test_legacy_terminal_replay_scrubs_nested_evidence_without_rewriting_history(self):
        request = self.request()
        secret = "sk-syntheticabcdefghijklmnop"
        record = {"operation_id": request.operation_id, "kind": "send_message",
                  "fingerprint": self.service.fingerprint(request), "state": "completed",
                  "turn": {"status": "completed", "drafts": [{"kind": "goal", "nested": {
                      "text": "api_key: " + secret, "items": [secret]}}],
                           "messages": [{"raw": secret}]}}
        path = self.store.directory / "operations.jsonl"
        path.write_text(json.dumps(record) + "\n")
        original = path.read_bytes()
        reopened = application.ApplicationService(self.architect, ArchitectStore(self.project))
        result = reopened.send_message(request)
        self.assertEqual((result.status, result.replayed), ("completed", True))
        self.assertNotIn(secret, json.dumps(result.turn.drafts))
        self.assertFalse(result.turn.messages)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.architect.calls, [])

    def test_accepted_input_dispatches_once_and_running_replay_is_indeterminate(self):
        request = self.request()
        self.service.accept_message(request)
        self.assertEqual(self.store.transcript()[0]["text"], request.text)
        self.assertEqual(self.architect.calls, [])
        other = application.ApplicationService(self.architect, ArchitectStore(self.project))
        def provider():
            replay = other.send_message(request)
            self.assertEqual((replay.status, replay.replayed), ("indeterminate", True))
            return self.architect.send(request.text)
        self.assertEqual(self.service.send_message(request, runner=provider).status, "completed")
        self.assertEqual(other.send_message(request).status, "completed")
        self.assertEqual(len(self.architect.calls), 1)
        self.assertEqual(len(self.store.transcript()), 1)

    def test_a_real_architect_lock_failure_is_visible_after_reopen_and_replays_without_resending(self):
        architect = Architect("/unused/codex", {}, self.project, "fake-model", "high", store=self.store)
        service = application.ApplicationService(architect)
        request = service.new_request("Keep this accepted message")
        with self.store.lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Blocked) as raised:
                service.send_message(request)
        self.assertEqual(raised.exception.family, "architect.locked")
        reopened = ArchitectStore(self.project)
        owner, failure = reopened.transcript()
        self.assertEqual((owner["role"], failure["role"], failure["status"]), ("owner", "error", "failed"))
        self.assertEqual(owner["turn_id"], failure["turn_id"])
        self.assertIn("another", failure["text"].lower())
        replay = application.ApplicationService(architect, reopened).send_message(request)
        self.assertEqual((replay.status, replay.replayed), ("failed", True))
        self.assertEqual(len(reopened.transcript()), 2)

    def test_torn_tail_keeps_completed_replay_and_indeterminate_operations_but_blocks_new_appends(self):
        completed = self.request("completed")
        self.service.send_message(completed)
        unfinished = self.request("interrupted")
        path = self.store.directory / "operations.jsonl"
        with path.open("a") as stream:
            stream.write(json.dumps({"operation_id": unfinished.operation_id, "kind": "send_message",
                                    "fingerprint": self.service.fingerprint(unfinished), "state": "running"}) + "\n")
            stream.write('{"operation_id":"torn')
        before = path.read_bytes()
        reopened = application.ApplicationService(self.architect, ArchitectStore(self.project))
        self.assertEqual(reopened.send_message(completed).status, "completed")
        self.assertEqual(reopened.send_message(unfinished).status, "indeterminate")
        with self.assertRaises(Blocked) as raised:
            reopened.send_message(self.request("new"))
        self.assertEqual(raised.exception.family, "operation.store_invalid")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.architect.calls), 1)

    def test_torn_tail_during_provider_completion_never_hides_prior_replay(self):
        for fails in (False, True):
            with self.subTest(exception=fails):
                store = ArchitectStore(self.project, root=Path(self.temp.name) / str(fails))
                architect = FakeArchitect(store)
                service = application.ApplicationService(architect)
                completed = service.new_request("earlier completed turn")
                service.send_message(completed)
                active = service.new_request("running turn")
                torn = []

                def provider():
                    # A different process owns the journal lock and dies mid-write while the
                    # provider is in flight. Completion must revalidate, not concatenate JSON.
                    subprocess.run([sys.executable, "-c", '''
import fcntl, os, sys
with open(sys.argv[1], "a+") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    fd = os.open(sys.argv[2], os.O_WRONLY | os.O_APPEND)
    os.write(fd, b'{"operation_id":"crashed-writer"')
    os.fsync(fd)
    os._exit(0)
''', str(service.operation_lock_path), str(service.operations_path)], check=True)
                    torn.append(service.operations_path.read_bytes())
                    if fails:
                        raise ValueError("provider failed")
                    return architect.result

                with self.assertRaises(Blocked) as raised:
                    service.send_message(active, runner=provider)
                self.assertEqual(raised.exception.family, "operation.store_invalid")
                self.assertEqual(service.operations_path.read_bytes(), torn[0])
                reopened = application.ApplicationService(architect, ArchitectStore(self.project, root=store.directory.parent))
                self.assertEqual(reopened.send_message(completed).status, "completed")
                self.assertEqual(reopened.send_message(active).status, "indeterminate")
                self.assertEqual(len(architect.calls), 1)
                if fails:
                    self.assertEqual(store.transcript()[-1]["turn_id"], active.turn_id)
                    self.assertIn("provider failed", store.transcript()[-1]["text"])

    def test_middle_corruption_is_not_treated_as_a_torn_tail(self):
        request = self.request()
        self.service.send_message(request)
        path = self.store.directory / "operations.jsonl"
        with path.open("a") as stream:
            stream.write('not json\n')
            stream.write(json.dumps({"operation_id": "later", "state": "running"}) + "\n")
        before = path.read_bytes()
        with self.assertRaises(Blocked) as raised:
            self.service.send_message(request)
        self.assertEqual(raised.exception.family, "operation.store_invalid")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.architect.calls), 1)

    def test_an_unfinished_operation_is_indeterminate_and_is_never_resent(self):
        request = self.request()
        record = {"operation_id": request.operation_id, "kind": "send_message",
                  "fingerprint": self.service.fingerprint(request), "state": "running", "request": {"text": request.text}}
        with (self.store.directory / "operations.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        result = self.service.send_message(request)
        self.assertEqual((result.status, result.replayed), ("indeterminate", True))
        self.assertEqual(self.architect.calls, [])
        self.assertEqual(self.store.transcript(), [])


if __name__ == "__main__":
    unittest.main()
