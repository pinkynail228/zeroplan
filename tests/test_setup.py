"""Deterministic installation/preferences checks; no credentials or model calls."""

from contextlib import contextmanager
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from terminal_planner import agent_profile, catalog, process, setup, toolchain
from terminal_planner.authority import Blocked
from terminal_planner.cli import Terminal, configure_roles, main, session
from terminal_planner.engine import FixtureEngine


class Steps(io.StringIO):
    """Typed lines; a callable step runs right before the next line is read (the owner acting in another terminal)."""

    def __init__(self, *steps):
        super().__init__()
        self.steps = list(steps)

    def readline(self, *_):
        while self.steps and callable(self.steps[0]):
            self.steps.pop(0)()
        return self.steps.pop(0) + "\n" if self.steps else ""


class ConfirmAnswerTests(unittest.TestCase):
    """The English interface still accepts the Russian "yes" typed at a [y/N] prompt (0.7.x habit), through the one
    constant `setup.YES_ANSWERS`, in the setup prompt and in both CLI prompts. Interpretation: only the answer
    set is pinned, not the prompt wording."""

    def test_the_russian_yes_still_confirms_at_every_prompt(self):
        from terminal_planner.cli import terminal_confirm
        for answer in ("y", "Yes", "д", "да", " Да "):
            with patch("builtins.input", return_value=answer):
                self.assertTrue(setup.ask_confirm("Go on?"), answer)
            self.assertTrue(terminal_confirm(Terminal(io.StringIO(answer + "\n"), io.StringIO()))("Go on?"), answer)
        for answer in ("", "n", "нет"):
            with patch("builtins.input", return_value=answer):
                self.assertFalse(setup.ask_confirm("Go on?"), answer)
            self.assertFalse(terminal_confirm(Terminal(io.StringIO(answer + "\n"), io.StringIO()))("Go on?"), answer)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"), "XDG_CONFIG_HOME": str(self.root / "config")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.platform = patch.object(setup, "platform_key", return_value=("Darwin", "arm64"))
        self.platform.start()
        self.addCleanup(self.platform.stop)

    def archive(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name in ("zeroshot", "restic"):
                info = tarfile.TarInfo("../../" + name)
                info.size = len(b"native")
                archive.addfile(info, io.BytesIO(b"native"))
        return buffer.getvalue()

    def install(self, fail=False):
        body = self.archive()

        def run(arguments, **kwargs):
            if arguments[-1] == "--version":
                return "v22.0.0"
            if fail:
                raise Blocked("npm rejected")
            codex = Path(kwargs["cwd"]) / "node_modules/.bin/codex"
            codex.parent.mkdir(parents=True)
            codex.write_text("codex")
            return ""

        with patch.object(setup, "urlopen", return_value=io.BytesIO(body)), \
                patch.object(toolchain, "DEFAULT", replace(toolchain.DEFAULT, releases={("Darwin", "arm64"): ("aarch64-apple-darwin", __import__("hashlib").sha256(body).hexdigest())})), \
                patch.object(setup, "run_checked", side_effect=run), \
                patch.object(setup, "check_versions"), \
                patch.object(setup.shutil, "which", return_value="tool"):
            setup.install_tools(lambda _: None)

    def test_install_atomic_failure_and_success(self):
        with self.assertRaises(Blocked):
            self.install(fail=True)
        self.assertFalse(setup.tools_root().exists())
        self.install()
        root = setup.tools_root()
        receipt = json.loads((root / "installation.json").read_text())
        self.assertEqual(receipt["files"], setup.tool_files(root))
        self.assertEqual((root / "zeroshot").read_text(), "native")
        self.assertFalse((root.parent.parent / "zeroshot").exists())
        self.assertFalse(list(root.parent.glob(".setup-*")))

    def test_codex_version_probe_gets_a_codex_home_never_dot_codex(self):
        """T3c K1/K2 (R6 of 0.8.0): the pinned Codex writes `<CODEX_HOME>/tmp/arg0` on every start, `--version` too.
        Interpretation: check_versions is the only Codex process setup.py starts outside a login or a turn."""
        chain = toolchain.current()
        root = self.root / "tools"
        (root / "codex/node_modules/.bin").mkdir(parents=True)
        home = self.root / "home"
        home.mkdir()
        record = self.root / "record"
        for path, output in ((root / "zeroshot", chain.zeroshot_version), (root / "restic", chain.restic_version),
                             (root / "codex/node_modules/.bin/codex", chain.codex_version)):
            records = "printf %s \"$CODEX_HOME\" > \"$RECORD\"\n" if path.name == "codex" else ""
            path.write_text("#!/bin/sh\n" + records + "echo '" + output + "'\n")
            path.chmod(0o755)

        def probe(**extra):
            env = {key: value for key, value in os.environ.items() if key != "CODEX_HOME"}
            env.update(HOME=str(home), RECORD=str(record), **extra)
            with patch.dict(os.environ, env, clear=True):
                setup.check_versions(root)
            return record.read_text()

        self.assertEqual(probe(), str(setup.private_codex_home()))
        self.assertEqual(os.stat(setup.private_codex_home()).st_mode & 0o777, 0o700)
        self.assertFalse((home / ".codex").exists())
        setup.private_codex_home().rmdir()
        override = self.root / "x/override"
        self.assertEqual(probe(CODEX_HOME=str(override)), str(override.resolve()))
        self.assertFalse(setup.private_codex_home().exists())
        self.assertFalse((home / ".codex").exists())

    def test_codex_version_probe_refuses_the_owner_home_alias_like_a_launch(self):
        """T3d G1: a private home `data_root()/codex-home` symlinked to `~/.codex` is refused by `launch_home`'s own
        guard before `codex --version` starts, so `~/.codex/tmp/arg0` is never written.
        Interpretation: the refusal is compared with `launch_home`'s own on the same state."""
        chain = toolchain.current()
        root = self.root / "tools"
        (root / "codex/node_modules/.bin").mkdir(parents=True)
        home = self.root / "home"
        owner = home / ".codex"
        owner.mkdir(parents=True)
        record = self.root / "record"
        for path, output in ((root / "zeroshot", chain.zeroshot_version), (root / "restic", chain.restic_version),
                             (root / "codex/node_modules/.bin/codex", chain.codex_version)):
            records = "mkdir -p \"$HOME/.codex/tmp\"; : > \"$RECORD\"\n" if path.name == "codex" else ""
            path.write_text("#!/bin/sh\n" + records + "echo '" + output + "'\n")
            path.chmod(0o755)
        env = {key: value for key, value in os.environ.items() if key != "CODEX_HOME"}
        env.update(HOME=str(home), RECORD=str(record))
        with patch.dict(os.environ, env, clear=True):
            setup.private_codex_home().parent.mkdir(parents=True, exist_ok=True)
            setup.private_codex_home().symlink_to(owner)
            with self.assertRaises(Blocked) as launch:
                setup.launch_home()
            with self.assertRaises(Blocked) as probed:
                setup.check_versions(root)
        self.assertEqual(probed.exception.family, "setup.agent_home")
        self.assertEqual((probed.exception.family, str(probed.exception)), (launch.exception.family, str(launch.exception)))
        self.assertFalse(record.exists())
        self.assertFalse((owner / "tmp").exists())

    def test_checksum_rejected_before_npm(self):
        with patch.object(setup, "urlopen", return_value=io.BytesIO(b"bad archive")), \
                patch.object(setup, "run_checked", return_value="v22.0.0") as runner, \
                patch.object(setup.shutil, "which", return_value="tool"):
            with self.assertRaisesRegex(Blocked, "checksum"):
                setup.install_tools(lambda _: None)
            self.assertEqual(runner.call_count, 1)
            self.assertFalse(setup.tools_root().exists())

    def test_rerun_checks_existing_without_download(self):
        setup.tools_root().mkdir(parents=True)
        with patch.object(setup, "check_installation") as check, \
                patch.object(setup, "urlopen") as download, \
                patch.object(setup, "run_checked", return_value="v22.0.0"), \
                patch.object(setup.shutil, "which", return_value="tool"):
            setup.install_tools(lambda _: None)
            check.assert_called_once()
            download.assert_not_called()
            check.side_effect = Blocked("corrupt")
            with self.assertRaises(Blocked):
                setup.install_tools(lambda _: None)
            download.assert_not_called()

    def test_modified_tools_rejected_before_version_execution(self):
        self.install()
        receipt = json.loads((setup.tools_root() / "installation.json").read_text())
        with patch.object(toolchain, "DEFAULT", replace(toolchain.DEFAULT, releases={("Darwin", "arm64"): ("test", receipt["archive_sha256"])})), \
                patch.object(setup, "check_versions") as versions:
            self.assertEqual(setup.check_installation(), setup.tools_root())
            versions.reset_mock()
            setup.tool_paths()[0].write_text("tampered")
            with self.assertRaisesRegex(Blocked, "damaged"):
                setup.check_installation()
            versions.assert_not_called()

    def test_preferences_persist_and_malformed_values_fail_closed(self):
        roles = setup.default_roles()
        self.assertEqual(roles["worker"], {"model": "gpt-6.1-terra", "effort": "max"})   # M3: terra / max
        self.assertEqual(roles["plan_verifier"], {"model": "gpt-6.1-sol", "effort": "high"})
        roles["worker"] = {"model": "other-model", "effort": "low"}
        setup.save_roles(roles)
        terminal = Terminal(io.StringIO("\n" * 10), io.StringIO())
        terminal.role_preferences = setup.load_roles()
        self.assertEqual(configure_roles(terminal), roles)
        self.assertEqual(setup.load_roles(), roles)
        self.assertEqual((setup.config_root() / "roles.json").stat().st_mode & 0o777, 0o600)
        (setup.config_root() / "roles.json").write_text('{"worker": {"model": "bad"}}')
        with self.assertRaises(Blocked):
            setup.load_roles()
        with self.assertRaises(Blocked):
            setup.validate_roles({role: {"model": "x", "effort": []} for role in setup.ROLE_DEFAULTS})

    def test_role_defaults_come_from_one_table(self):
        """M3: Enter on every prompt of `configure_roles` keeps `default_roles()` (worker terra / max, the others
        sol / high) when nothing is saved. Interpretation: the shell's `_roles` start value is `default_roles()`
        itself (cli.py), so this covers it; the model hint is process.py's `binding`, read here through a bad id."""
        roles = configure_roles(Terminal(io.StringIO("\n" * 10), io.StringIO()), {})
        self.assertEqual(roles, setup.default_roles())
        self.assertEqual(roles["worker"], {"model": "gpt-6.1-terra", "effort": "max"})
        self.assertEqual(roles["plan_verifier"], {"model": "gpt-6.1-sol", "effort": "high"})
        with self.assertRaisesRegex(Blocked, "for example gpt-6.1-terra"):
            process.binding("roles.worker", {"model": "bad model", "effort": "max"})

    def test_legacy_effort_preference_loads_but_input_requires_native_value(self):
        self.assertEqual(setup.EFFORTS, {"low", "medium", "high", "xhigh", "max"})
        roles = setup.default_roles()
        roles["worker"]["effort"] = "ultra"
        setup.save_roles(roles)
        output = io.StringIO()
        terminal = Terminal(io.StringIO("\n\n" * 3 + "\nxhigh\n" + "\n\n" * 3), output)
        terminal.role_preferences = setup.load_roles()
        self.assertEqual(configure_roles(terminal)["worker"]["effort"], "xhigh")
        self.assertIn("A model ID and an effort are required: high, low, max, medium, xhigh", output.getvalue())
        self.assertEqual(setup.load_roles()["worker"]["effort"], "xhigh")

    def test_login_only_passes_official_device_command_without_capturing_output(self):
        home = setup.private_codex_home()  # D6a: login acts in the home zplan owns (test_login_home covers the rest)
        env = {"CODEX_HOME": str(home), "PATH": "test"}
        with patch.object(setup, "native_environment", return_value=env), patch.object(setup, "on_terminal", return_value=True), \
                patch.object(setup.subprocess, "call", return_value=7) as call:
            self.assertEqual(setup.login(lambda line: None), 7)
        status, login = call.call_args_list
        self.assertEqual(status.args[0][-2:], ["login", "status"])  # an existing login is looked for first
        args, kwargs = login
        self.assertEqual(args[0][-2:], ["login", "--device-auth"])
        self.assertIn('cli_auth_credentials_store="file"', args[0])
        self.assertEqual(kwargs, {"env": env})
        self.assertFalse((home / "auth.json").exists())

    def test_a1_a_failed_login_names_the_device_code_guidance_before_the_retry(self):
        """A1/A2 (D5 repair 1): `zplan login` prints, on a failed login, the one catalog constant with the Russian
        device-code guidance before the retry hint and the tag, which keep their own wording. Interpretation: the
        guidance is a standalone sentence appended after the existing retry line, so that line itself is unchanged;
        the guidance also lives in the catalog (catalog.LOGIN_DEVICE_CODE_OFF), not inline here."""
        output = io.StringIO()
        terminal = Terminal(io.StringIO(), output)
        with patch("terminal_planner.cli.Terminal", return_value=terminal), patch.object(setup, "on_terminal", return_value=True), \
                patch("terminal_planner.cli.login", return_value=7):
            self.assertEqual(main(["login"]), 7)
        shown = output.getvalue()
        self.assertIn(catalog.LOGIN_DEVICE_CODE_OFF, shown)  # the one constant holds the guidance
        self.assertIn("If device-code login is turned off for the account, turn it on in the "
                      "account's ChatGPT security settings.", shown)
        self.assertIn("Login not finished; retry zplan login.", shown)  # the retry hint stays as it was
        self.assertIn(catalog.tag("setup.login_failed"), shown)  # and so does the tag

    def test_socket_preflight_counts_bytes_and_preserves_existing_history(self):
        from terminal_planner.engine import check_socket_path
        with patch("terminal_planner.engine.platform.system", return_value="Linux"), patch.object(Path, "resolve", lambda path: path):
            self.assertEqual(check_socket_path("/home/testuser/.zp"), 81)
            with self.assertRaisesRegex(Blocked, "110 bytes.*--native-state-dir"):
                check_socket_path("/home/testuser/.local/share/planning-kit/native")
            with self.assertRaises(Blocked):
                check_socket_path("/" + "я" * 30)
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}):
            old = setup.data_root() / "native"
            self.assertEqual(setup.native_state_root(), (Path.home() / ".zp").resolve())
            old.mkdir(parents=True)
            self.assertEqual(setup.native_state_root(), old)

    def test_version_does_not_select_project_or_install(self):
        with patch("terminal_planner.cli.install_tools") as install:
            with self.assertRaises(SystemExit) as exit_status:
                main(["--version"])
            self.assertEqual(exit_status.exception.code, 0)
            install.assert_not_called()

    def test_first_launch_shows_readiness_and_q_exits_without_project_changes(self):
        project = self.root / "project"
        project.mkdir()
        for args in (("init", "-q", "-b", "main"), ("-c", "user.name=F", "-c", "user.email=f@example.invalid",
                                                    "commit", "-q", "--allow-empty", "-m", "fixture")):
            subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True)
        terminal = Terminal(io.StringIO("q\n"), io.StringIO())
        with patch.dict(os.environ, {"HOME": str(self.root / "home")}), \
                patch("terminal_planner.cli.Terminal", return_value=terminal), \
                patch("terminal_planner.cli.choose_project", return_value=project), \
                patch("terminal_planner.cli.install_tools") as install:
            self.assertEqual(main([]), 0)
            install.assert_not_called()
        output = terminal.output.getvalue()
        self.assertIn("zplan · project · main", output)
        self.assertIn("! The zplan tools are not installed", output)
        self.assertIn("! No GitHub origin — [i] instructions", output)
        self.assertIn("[u] install tools", output)
        self.assertIn("[q] quit", output)
        self.assertNotIn("There is no plan.", output)  # q on the readiness block exits; home is never reached
        self.assertEqual(sorted(p.name for p in project.iterdir()), [".git"])

    def test_setup_timeout_is_not_success(self):
        with patch.object(setup.subprocess, "run", side_effect=subprocess.TimeoutExpired("npm", 600)):
            with self.assertRaises(Blocked):
                setup.run_checked(["npm", "ci"])


@contextmanager
def hidden(path):
    away = path.with_name(path.name + ".away")
    path.rename(away)
    try:
        yield
    finally:
        away.rename(path)


@contextmanager
def written(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    try:
        yield
    finally:
        path.unlink()


class DoctorTests(unittest.TestCase):
    """Every doctor check: a ready line, and one BLOCKED line naming the fix; secrets never printed."""

    SECRET = "sk-doctor-secret-value"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.codex_home = self.root / "codex"
        self.patch(patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data"), "XDG_CONFIG_HOME": str(self.root / "config"),
                                           "HOME": str(self.home), "CODEX_HOME": str(self.codex_home), "GIT_CONFIG_NOSYSTEM": "1"}))
        os.environ.pop("GIT_CONFIG_GLOBAL", None)  # restored with the patched environment
        for name in ("CODEX_API_KEY", "OPENAI_API_KEY"):  # R-4 judges these too; the runner's values stay out
            os.environ.pop(name, None)
        self.patch(patch.object(setup, "platform_key", return_value=("Darwin", "arm64")))
        self.patch(patch.object(setup, "check_installation", return_value=setup.tools_root()))
        self.patch(patch("terminal_planner.engine.check_socket_path", return_value=81))
        self.home.mkdir()
        (self.home / ".gitconfig").write_text("[user]\n\tname = Owner\n\temail = owner@example.com\n")
        codex = setup.tool_paths()[1]
        codex.parent.mkdir(parents=True)
        codex.write_text("#!/bin/sh\n")
        codex.chmod(0o755)
        self.codex_home.mkdir()
        (self.codex_home / "auth.json").write_text('{"tokens": "%s"}' % self.SECRET)

    def patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def target(self):
        project = self.root / "project"
        project.mkdir()
        for args in (("init", "-q", "-b", "main"), ("commit", "-q", "--allow-empty", "-m", "start"),
                     ("remote", "add", "origin", "https://github.com/owner/project.git")):
            subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True)
        return project

    def journey(self, project, name, *steps, install=None, login=None):
        """One startup through the real readiness list; returns (output, goals sent to the planner)."""
        submitted = []

        class Engine(FixtureEngine):
            def proposal(self, authority, progress, slice=None):
                submitted.append(authority.current["goal"])
                return super().proposal(authority, progress, slice)
        output = io.StringIO()
        session(Terminal(Steps(*steps), output), project, self.root / ("state-" + name), lambda *_: Engine(),
                fixture_id=name, readiness=lambda: setup.readiness(project), install=install, login=login)
        text = output.getvalue()
        self.assertNotIn(self.SECRET, text)
        return text, submitted

    def run_doctor(self, project=None):
        messages = []
        code = setup.doctor(messages.append, project=project)
        text = "\n".join(messages)
        self.assertNotIn(self.SECRET, text)
        self.assertNotIn("Docker", text)
        self.assertEqual("Plan: ready." in messages, code == 0)
        return code, text

    def test_doctor_shows_the_active_toolchain_and_its_tool_dir(self):
        chain = replace(toolchain.DEFAULT, zeroshot="10.12.0", codex="0.161.0", restic="0.20.0")
        for active in (toolchain.DEFAULT, chain):
            with self.subTest(active.zeroshot_version), patch.object(toolchain, "DEFAULT", active):
                text = self.run_doctor()[1]
                lines = [line for line in text.splitlines() if line.startswith("Toolchain: ")]
                self.assertEqual(len(lines), 1, text)
                for part in (active.zeroshot_version, active.codex_version, active.restic_version, active.tool_dir_name):
                    self.assertIn(part, lines[0])
        self.assertIn("zeroshot-10.12.0-codex-0.161.0-runtime2", lines[0])

    def test_doctor_shows_the_active_toolchain_and_its_tool_dir(self):
        chain = replace(toolchain.DEFAULT, zeroshot="10.12.0", codex="0.161.0", restic="0.20.0")
        for active in (toolchain.DEFAULT, chain):
            with self.subTest(active.zeroshot_version), patch.object(toolchain, "DEFAULT", active):
                text = self.run_doctor()[1]
                lines = [line for line in text.splitlines() if line.startswith("Toolchain: ")]
                self.assertEqual(len(lines), 1, text)
                for part in (active.zeroshot_version, active.codex_version, active.restic_version, active.tool_dir_name):
                    self.assertIn(part, lines[0])
        self.assertIn("zeroshot-10.12.0-codex-0.161.0-runtime2", lines[0])

    def blocked(self, text):
        return [line for line in text.splitlines() if line.startswith("BLOCKED: ")]

    def test_uncommitted_changes_are_information_never_a_block(self):
        """K1: any uncommitted change leaves the `clean` item ok (a plain ok, no key), saying how many files the last
        commit does not hold; an uncommitted zplan.process.json is named, because runs read the committed one.
        Interpretation: the count is the paths of `git status --porcelain=v1`, untracked or modified alike."""
        project = self.target()
        clean = lambda: next(i for i in setup.check_target(project) if i["id"] == "clean")
        self.assertEqual(clean()["line"], "Working tree clean")
        (project / "notes.txt").write_text("draft\n")
        item = clean()
        self.assertTrue(item["ok"])
        self.assertEqual((item["severity"], item["key"]), ("ok", None))
        self.assertEqual(item["line"], "Not committed: 1 file — the plan sees the last commit")
        self.assertNotIn("zplan.process.json", item["line"])
        (project / "zplan.process.json").write_text("{}\n")
        item = clean()
        self.assertTrue(item["ok"])
        self.assertIn("Not committed: 2 files — the plan sees the last commit", item["line"])
        self.assertIn("zplan.process.json", item["line"])
        self.assertIn(item["line"], item["doctor"])

    def test_ready_prints_one_ok_line_per_check(self):
        code, text = self.run_doctor()
        self.assertEqual(code, 0, text)
        for line in ("OK: native socket path 81 bytes", "OK: zeroshot 10.16.0", "OK: codex " + str(setup.tool_paths()[1]),
                     # R-5: an override home names itself, and the profile line belongs to zplan's own home alone
                     "OK: CODEX_HOME %s (your $CODEX_HOME, not zplan's profile) · provider openai "
                     "(no config.toml: Codex defaults)" % self.codex_home.resolve(),
                     "OK: auth: login file present in CODEX_HOME", "OK: git ", "OK: Git identity Owner <owner@example.com>",
                     "OK: roles planner=gpt-6.1-sol/high", "Target: not selected"):
            self.assertIn(line, text)
        self.assertEqual(self.blocked(text), [])
        self.assertNotIn("zplan agent profile", text)  # the profile line is for zplan's own home only (R-5)

    def test_each_failed_check_prints_one_russian_fix_line_and_exits_1(self):
        breakages = {
            "socket": (patch("terminal_planner.engine.check_socket_path",
                             side_effect=Blocked("Socket path 110 bytes; give --native-state-dir")), "--native-state-dir"),
            "zeroshot": (patch.object(setup, "check_installation", side_effect=Blocked("missing")), "zeroshot is not installed"),
            "codex": (hidden(setup.tool_paths()[1]), "codex binary is missing"),
            "auth": (hidden(self.codex_home / "auth.json"), "run zplan login"),
            "git": (patch.object(setup.shutil, "which", return_value=None), "git is missing"),
            "identity": (hidden(self.home / ".gitconfig"), "git config --global user.name"),
            "roles": (written(setup.config_root() / "roles.json", "[]"), "zplan roles"),
        }
        for name, (breakage, fix) in breakages.items():
            with self.subTest(name), breakage:
                code, text = self.run_doctor()
                self.assertEqual(code, 1, text)
                self.assertEqual(len(self.blocked(text)), 1, text)
                self.assertIn(fix, self.blocked(text)[0])
        self.assertEqual(self.run_doctor()[0], 0)

    def test_effective_codex_home_and_provider_auth(self):
        config = self.codex_home / "config.toml"
        auth = self.codex_home / "auth.json"
        corp = ('model_provider = "corp"\n[model_providers.corp]\nname = "Corp"\n'
                'base_url = "https://llm.example/v1"\nenv_key = "CORP_KEY"\n')
        with written(config, corp), hidden(auth):
            code, text = self.run_doctor()
            self.assertEqual(code, 1)
            self.assertIn("provider corp", text)
            self.assertIn("BLOCKED: variable CORP_KEY for provider corp is not set", text)
            with patch.dict(os.environ, {"CORP_KEY": self.SECRET}):
                code, text = self.run_doctor()  # a custom API provider needs no file login
            self.assertEqual(code, 0, text)
            self.assertIn("OK: auth: $CORP_KEY is set", text)
        profile = 'profile = "local"\nmodel_provider = "corp"\n[profiles.local]\nmodel_provider = "ollama"\n'
        with written(config, profile), hidden(auth):
            code, text = self.run_doctor()
        self.assertEqual(code, 0, text)
        self.assertIn("provider ollama", text)
        self.assertIn("OK: auth: provider ollama needs no login", text)
        chatgpt = 'model_provider = "proxy"\n[model_providers.proxy]\nname = "P"\nrequires_openai_auth = true\n'
        with written(config, chatgpt), hidden(auth):
            self.assertIn("zplan login", self.blocked(self.run_doctor()[1])[0])
        for broken, fix in (('model_provider = "nope"\n', "provider 'nope' is not defined"),
                            ('profile = "gone"\n', "profile 'gone' not found"),
                            ("model_provider = \n", "cannot be read")):
            with self.subTest(broken), written(config, broken):
                code, text = self.run_doctor()
                self.assertEqual(code, 1)
                self.assertEqual(len(self.blocked(text)), 1, text)
                self.assertIn(fix, self.blocked(text)[0])
                self.assertNotIn("auth:", text)
        with patch.dict(os.environ):
            del os.environ["CODEX_HOME"]
            private = setup.private_codex_home()  # R-1: no override means zplan's own home, never ~/.codex
            code, text = self.run_doctor()
            self.assertEqual(code, 1)  # the zplan home has no login yet
            self.assertIn("CODEX_HOME %s (zplan)" % private, text)
            self.assertIn("no login for provider openai in %s" % private, text)
            self.assertFalse((self.home / ".codex").exists())
            self.assertIn("zplan agent profile: not written yet (written at login or first launch).", text)
            self.assertEqual(agent_profile.ensure(private), "written")  # the informational line of a written one
            self.assertIn("zplan agent profile: profile %s (packaged %s)." % (
                agent_profile.written_version(private), agent_profile.version(agent_profile.packaged())),
                self.run_doctor()[1])

    def test_the_blocking_auth_line_guides_one_own_login_and_leaves_the_owner_codex_untouched(self):
        """A1/A5. The auth item's start-screen key stays `l` (`setup.item(..., key="l")`), so the one blocking
        doctor line names both `zplan login` and [l] instead of introducing a second key. The ~/.codex files below
        are the owner's own home: zplan must never read, copy or link them (a shared refresh token rotates and
        would log the owner's own Codex out), so they stay byte-identical here."""
        owner = self.home / ".codex"
        owner.mkdir()
        (owner / "auth.json").write_text('{"tokens": "owner-token"}\n')
        (owner / "config.toml").write_text('model = "owner-model"\n')
        before = {path.name: path.read_bytes() for path in owner.iterdir()}
        with patch.dict(os.environ):
            del os.environ["CODEX_HOME"]
            private = setup.private_codex_home()
            code, text = self.run_doctor()
        self.assertEqual(code, 1)
        line = self.blocked(text)[0]
        self.assertIn("no login for provider openai in %s" % private, line)
        self.assertIn("zplan needs its own Codex login once", line)
        self.assertIn("run zplan login", line)
        self.assertIn("[l]", line)
        self.assertIn("~/.codex", line)
        self.assertIn("is not used or changed", line)
        self.assertIn("CODEX_HOME", line)
        self.assertFalse((private / "auth.json").exists())  # nothing copied or linked into zplan's own home
        self.assertEqual({path.name: path.read_bytes() for path in owner.iterdir()}, before)

    def test_a_present_login_in_zplans_own_home_keeps_the_existing_ok_line(self):
        """A3/A5. A login already in zplan's own Codex home keeps the unchanged OK auth line and asks for nothing
        (no [l] prompt); the owner's ~/.codex fixtures stay byte-identical while the private login is read."""
        owner = self.home / ".codex"
        owner.mkdir()
        (owner / "auth.json").write_text('{"tokens": "owner-token"}\n')
        before = {path.name: path.read_bytes() for path in owner.iterdir()}
        with patch.dict(os.environ):
            del os.environ["CODEX_HOME"]
            private = setup.private_codex_home()
            private.mkdir(parents=True)
            (private / "auth.json").write_text('{"tokens": "zplan-token"}\n')
            auth = [i for i in setup.readiness() if i["id"] == "auth"]
            self.assertEqual([(i["ok"], i["doctor"]) for i in auth],
                             [(True, "auth: login file present in CODEX_HOME (presence, not validity)")])
            self.assertTrue(auth[0]["line"].startswith("Codex: login found"))
            code, text = self.run_doctor()
        self.assertEqual(code, 0, text)
        self.assertIn("OK: auth: login file present in CODEX_HOME (presence, not validity)", text)
        self.assertNotIn("no login for provider", text)
        self.assertEqual({path.name: path.read_bytes() for path in owner.iterdir()}, before)

    def test_the_auth_checks_never_copy_or_link_the_owner_codex(self):
        """A5. Readiness and doctor judge auth by presence in zplan's own home only: the owner's ~/.codex fixtures
        stay byte-identical, and no entry of that home is copied or linked into the private home (a copied refresh
        token rotates and can log the owner's own Codex out)."""
        owner = self.home / ".codex"
        owner.mkdir()
        (owner / "auth.json").write_text('{"tokens": "owner-token"}\n')
        (owner / "config.toml").write_text('model = "owner-model"\n')
        before = {path.name: path.read_bytes() for path in owner.iterdir()}
        with patch.dict(os.environ):
            del os.environ["CODEX_HOME"]
            private = setup.private_codex_home()
            setup.readiness()  # no login in zplan's home yet: the blocking path
            self.run_doctor()
            private.mkdir(parents=True)  # a login the owner later adds to zplan's own home: the OK path
            (private / "auth.json").write_text('{"tokens": "zplan-token"}\n')
            setup.readiness()
            self.run_doctor()
        self.assertEqual({path.name: path.read_bytes() for path in owner.iterdir()}, before)
        self.assertNotEqual((owner / "auth.json").read_bytes(), (private / "auth.json").read_bytes())
        self.assertEqual(sorted(path.name for path in private.iterdir()), ["auth.json"])  # nothing of the owner's

    def test_codex_home_is_explicit_env_else_home_codex_never_by_login_presence(self):
        private = setup.private_codex_home()
        private.mkdir(parents=True)
        (private / "auth.json").write_text("{}")  # a login in the private home must not attract the default
        with patch.dict(os.environ):
            del os.environ["CODEX_HOME"]
            self.assertEqual(setup.codex_home(), (self.home / ".codex").resolve())
            self.assertFalse((self.home / ".codex").exists())  # resolving never creates or copies anything
            os.environ["CODEX_HOME"] = str(private)  # the documented opt-in
            self.assertEqual(setup.codex_home(), private.resolve())
        self.assertEqual(setup.codex_home(), self.codex_home.resolve())  # explicit env wins
        self.assertEqual(setup.codex_home({"CODEX_HOME": str(private)}), private.resolve())
        self.assertEqual(setup.codex_home({}), (self.home / ".codex").resolve())
        self.assertEqual(sorted(p.name for p in private.iterdir()), ["auth.json"])

    def test_doctor_and_start_screen_share_one_check_list(self):
        project = self.root / "target"
        project.mkdir()
        for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "init"]):
            subprocess.run(["git", "-C", str(project), *args], check=True)
        (project / "draft.txt").write_text("untracked")
        with hidden(self.codex_home / "auth.json"):
            items = setup.readiness(project)
            text = self.run_doctor(project)[1]
        self.assertEqual([line for line in text.splitlines() if line.startswith(("OK: ", "BLOCKED: "))],
                         [("OK: " if i["ok"] else "BLOCKED: ") + i["doctor"] for i in items])
        self.assertEqual([i["id"] for i in items if not i["ok"]], ["auth", "origin"])
        # An override home is the owner's own Codex: zplan does not log in there, so the key is the instruction.
        self.assertEqual([i["key"] for i in items if not i["ok"]], ["i", "i"])
        self.assertEqual([i["id"] for i in setup.readiness(project, tools=False)],
                         ["git", "identity", "repo", "branch", "origin", "clean"])

    def test_minimal_toml_selects_like_tomllib(self):
        text = ('# Codex\nmodel = "gpt-6.1-sol"   # trailing\nprofile = \'work\'\napproval = true\nn = 1_000\n'
                'when = 1979-05-27T07:32:00Z\nnotify = [\n  "a", # c\n  "b]",\n]\ninline = { a = 1, b = "}" }\n'
                'doc = """\nmulti [ line\n"""\n\n[profiles.work]\nmodel_provider = "corp"\n'
                '[ model_providers . "corp" ]\nname = "Corp \\"Q\\""\nenv_key = "CORP_KEY"\n'
                '[[mcp_servers.list]]\nname = "x"\n[profiles.other]\nmodel_provider.x = 1\n')
        minimal = setup.minimal_toml(text)
        self.assertEqual(minimal["profile"], "work")
        self.assertEqual(minimal["profiles"]["work"], {"model_provider": "corp"})
        self.assertEqual(minimal["model_providers"]["corp"], {"name": 'Corp "Q"', "env_key": "CORP_KEY"})
        self.assertIs(minimal["approval"], True)
        try:
            import tomllib
        except ImportError:
            tomllib = None
        if tomllib:
            full = tomllib.loads(text)
            for key in ("model", "profile", "approval"):
                self.assertEqual(minimal[key], full[key])
            self.assertEqual(minimal["profiles"]["work"], full["profiles"]["work"])
            self.assertEqual(minimal["model_providers"], full["model_providers"])
        for broken in ("model_provider = \n", "model_provider\n", "[profiles\n", 'x = "a" b\n', "x = [1, 2\n",
                       'x = """open\n', "x = 'a\n"):
            with self.subTest(broken):
                with self.assertRaises(ValueError):
                    setup.minimal_toml(broken)
                if tomllib:
                    with self.assertRaises(ValueError):
                        tomllib.loads(broken)
        config = self.codex_home / "config.toml"
        with written(config, text), patch.dict(os.environ, {"CORP_KEY": "x"}):
            self.assertEqual(setup.codex_provider(self.codex_home.resolve()), ("corp", ("env", "CORP_KEY")))
            with patch.object(setup, "read_toml", setup.minimal_toml):
                self.assertEqual(setup.codex_provider(self.codex_home.resolve()), ("corp", ("env", "CORP_KEY")))

    def test_project_checks_repo_branch_origin_and_clean_tree_without_printing_the_url(self):
        project = self.root / "target"
        project.mkdir()
        for args in (["init", "-q", "-b", "main"], ["commit", "-q", "--allow-empty", "-m", "init"]):
            subprocess.run(["git", "-C", str(project), *args], check=True)
        code, text = self.run_doctor(self.root / "missing")
        self.assertEqual(code, 1)
        self.assertIn("--project", self.blocked(text)[0])
        code, text = self.run_doctor(project)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.blocked(text)), 1, text)
        self.assertIn("git remote add origin https://github.com/OWNER/REPO.git", text)
        # 10.12's GitRemoteUrl rejects HTTPS userinfo: the doctor refuses it and never prints the URL.
        subprocess.run(["git", "-C", str(project), "remote", "add", "origin", "https://user:secret@github.com/o/r.git"], check=True)
        code, text = self.run_doctor(project)
        self.assertEqual(code, 1)
        self.assertEqual(len(self.blocked(text)), 1, text)
        self.assertIn("git remote set-url origin https://github.com/o/r.git", text)
        self.assertNotIn("secret", text)
        subprocess.run(["git", "-C", str(project), "remote", "set-url", "origin", "https://github.com/o/r.git"], check=True)
        code, text = self.run_doctor(project)
        self.assertEqual(code, 0, text)
        for line in ("OK: Target: Git project", "OK: Target: branch main", "OK: Target: origin github.com/o/r",
                     "OK: Target: working tree clean"):
            self.assertIn(line, text)
        subprocess.run(["git", "-C", str(project), "remote", "set-url", "origin", "git@gitlab.com:o/r.git"], check=True)
        self.assertEqual(self.run_doctor(project)[0], 1)
        subprocess.run(["git", "-C", str(project), "remote", "set-url", "origin", "git@github.com:o/r.git"], check=True)
        (project / "draft.txt").write_text("untracked")
        code, text = self.run_doctor(project)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.blocked(text), [])
        self.assertIn("OK: Target: Not committed: 1 file — the plan sees the last commit", text)
        (project / "draft.txt").unlink()
        subprocess.run(["git", "-C", str(project), "checkout", "-q", "--detach"], check=True)
        code, text = self.run_doctor(project)
        self.assertEqual(code, 1)
        self.assertIn("git switch <branch>", self.blocked(text)[0])
        subprocess.run(["git", "-C", str(project), "checkout", "-q", "main"], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.name", "Repo Owner"], check=True)
        subprocess.run(["git", "-C", str(project), "config", "user.email", "repo@example.com"], check=True)
        self.assertIn("OK: Git identity Repo Owner <repo@example.com>", self.run_doctor(project)[1])


if __name__ == "__main__":
    unittest.main()
