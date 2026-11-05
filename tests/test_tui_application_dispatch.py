"""The H1 owner intent through the real TUI at compact and wide terminal sizes."""
import json
import unittest

from terminal_planner.application import ApplicationService
from terminal_planner.tui.chat import ChatHeader
from test_application_dispatch import ScriptProvider, plan_tool
from test_tui_chat import ChatShell, chat_band
from tui_support import HAVE_TEXTUAL


@unittest.skipUnless(HAVE_TEXTUAL, "Textual wheels required")
class ApplicationParityTests(ChatShell):
    async def scenario(self, size):
        provider = ScriptProvider(self.root, self.project, [plan_tool()])
        prepare = lambda project: (provider.architect, ChatHeader(model="fixture-model", effort="high"))
        async with self.shell(size=size, chat_prepare=prepare) as pilot:
            await self.loaded(pilot)
            await self.chat_ready(pilot)
            await self.say(pilot, "Plan a small useful change")
            await self.until(pilot, lambda: bool(provider.rows("results")))
            await self.until(pilot, lambda: self.app.snapshot is not None and self.app.snapshot.version == 1)
            await self.chat_done(pilot)
            await self.until(pilot, lambda: "Initial dispatch recorded." in chat_band(self.app))
            self.assertIn("Plan a small useful change", chat_band(self.app))
            self.assertTrue(self.query("#input").region.width)
            self.assertEqual(self.app.snapshot.status, "proposed")
            service = ApplicationService(provider.architect)
            child = service.tool_request(provider.rows("requests")[0])
            self.assertTrue(child.replayed)
            self.assertTrue(child.detail["dispatch"]["run_id"])
            self.assertEqual(len(provider.rows("requests")), 1)
            # A real plan decision remains visible/actionable; the screen did not dispatch it.
            await self.until(pilot, lambda: bool(self.app.query("Card")))
        with self.subTest(reopen=True):
            async with self.shell(size=size, chat_prepare=prepare) as pilot:
                await self.loaded(pilot)
                await self.chat_ready(pilot)
                await self.until(pilot, lambda: "Initial dispatch recorded." in chat_band(self.app))
                self.assertEqual(self.app.snapshot.version, 1)
                self.assertEqual(len(provider.rows("requests")), 1)
        rows = provider.architect.store.transcript()
        self.assertEqual(sum(row["role"] == "owner" for row in rows), 1)
        records = [json.loads(line) for line in service.operations_path.read_text().splitlines()]
        child_records = [r for r in records if r["operation_id"] == "plan-child"]
        self.assertEqual(len(child_records), 2)

    async def test_compact_owner_dispatch(self):
        await self.scenario((80, 24))

    async def test_wide_owner_dispatch(self):
        await self.scenario((140, 45))
