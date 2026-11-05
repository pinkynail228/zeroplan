"""Full-screen terminal UI (Textual). Imported only when a TTY session starts; plain mode never loads it."""

from .controller import Controller


def run(project, state_root, fixture_id=None, driver_factory=None, worktrees=None, readiness=None, install=None,
        login=None, role_preferences=None, engine_factory=None, profile=False):
    """Open the TUI for `project`; returns the process exit code. The terminal is restored on every way out."""
    from .app import ZplanApp
    controller = Controller.for_project(project, state_root, fixture_id=fixture_id, driver_factory=driver_factory,
                                        worktrees=worktrees, readiness=readiness, install=install, login=login,
                                        role_preferences=role_preferences, engine_factory=engine_factory,
                                        profile=profile, scripted=fixture_id is not None)
    # A `--fixture ID` session has a scripted architect over its own fixture store: no provider, no tool probe
    # (R-2). `fixture_id is not None` classifies the mode, never its truthiness (R-1).
    if fixture_id is None:
        app = ZplanApp(controller)
    else:
        from ..architect import FixtureArchitect, fixture_store
        from .chat import ChatHeader
        store = fixture_store(project, state_root, fixture_id)
        app = ZplanApp(controller, chat_store=store, chat_prepare=lambda _: (FixtureArchitect(store), ChatHeader()),
                       chat_binding=lambda _: ("", ""))
        app.origin_told = True
    try:
        app.run()
        return app.return_code or 0
    finally:
        # The whole cleanup shares the exit budget [ctrl+q] started: after unmount only what is left of it is waited
        # for (a stuck non-mutating read cannot add a second full timeout); without a quit key the usual default.
        left = app.quit_left()
        controller.stop() if left is None else controller.stop(timeout=left)
