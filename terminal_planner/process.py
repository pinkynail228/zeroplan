"""Process profile v1: the project's `zplan.process.json`, its resolver, the acceptance state and the guards.

The profile names the owner's process (roles, gates, limits, rules, checks). It acts on the roles, the plan gate,
`limits.plan_rounds`, for planning the rules and, with `gates.merge: required`, the merge gate (the `checks` run on
the commit that lands, `runs.MilestoneRuns.gate_merge`); everything else is validated, stored and shown as "for later
stages", and a `required` gate whose stage is not built yet blocks its action with a named refusal (never a silent
pass). The preset zplan.default/2 adds an `autonomy` section (the level and the thresholds the later slices read) and
a `risk` section (path rules -> risk tier, path triggers -> critic triggers; `risk_of` classifies changed paths); it
is data only — nothing consumes it yet.

Resolution per key: project file -> saved user `roles.json` (roles only, only bindings explicitly saved there) ->
the frozen preset. The resolved configuration has a canonical digest that includes the content of every rules file.
The acceptance state is a versioned sidecar `process-state.json` next to `planning.json` in the project's state
directory; it is written only while the Authority session lock is held. Informational commands read it without the
lock (a single atomically replaced file). Nothing here runs a model, a check or any project command."""

import copy
from dataclasses import dataclass, field, replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Optional, Tuple

from .authority import (HISTORICAL_EFFORTS, NATIVE_EFFORTS, Blocked, atomic_state, common_directory, decode,
                        digest, production_root)
from . import user_commit
from .setup import config_root

PROFILE_FILE = "zplan.process.json"
COMMIT_MESSAGE = "zplan profile"
STATE_FILE = "process-state.json"
PRESET = "zplan.default/1"
PRESET_V2 = "zplan.default/2"
PRESET_V3 = "zplan.default/3"
ROLES = ("planner", "critic", "worker", "reviewer", "steward", "architect")
GATES = ("plan", "task", "merge")
LIMITS = ("plan_rounds", "task_rounds", "merge_rounds")
AUTONOMY = ("level", "max_runs", "worker_round_minutes", "run_minutes", "structural_round", "wakeups_per_hour",
            "architect_retries")
AUTONOMY_LEVELS = ("auto", "supervised", "manual")
# The whole-number `autonomy` keys -> (low, high); `level` is checked against AUTONOMY_LEVELS instead.
AUTONOMY_RANGES = {"max_runs": (1, 5), "worker_round_minutes": (5, 240), "run_minutes": (10, 1440),
                   "structural_round": (2, 10), "wakeups_per_hour": (1, 60), "architect_retries": (0, 10)}
TOP_KEYS = ("preset", "rules", "roles", "gates", "limits", "autonomy", "risk", "checks")
V2_KEYS = ("autonomy", "risk")  # the top keys only zplan.default/2 carries
RISK = ("rules", "triggers")
RISK_TIERS = ("low", "medium", "high")  # ascending
MAX_RISK_RULES = 32
MAX_RISK_TRIGGERS = 16
MAX_RISK_PATTERNS = 32
MAX_PATTERN_CHARS = 256
RULE_CANDIDATES = ("AGENTS.md", "CLAUDE.md")
MAX_RULE_BYTES = 256 * 1024
RULES_LIMIT = 64 * 1024  # UTF-8 bytes of all rules together that reach an agent
PLAN_ROUNDS = (1, 5)
MAX_RULES = 8
MAX_CHECKS = 8
MAX_FILE_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 1800
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,255}")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
SHA = re.compile(r"[0-9a-f]{64}")
OFF = "no check"
NO_QUALIFICATION = "no qualification"
LATER_NOTE = "profile not saved"
NEXT_STAGES = "for later stages"
LEVEL_NAMES = {"auto": "auto", "supervised": "ask about the plan", "manual": "ask about everything"}  # the owner's words for autonomy.level
UNBUILT = {"task": "the task check is not built yet: turn it off in " + PROFILE_FILE}
SOURCE_NAMES = {"file": PROFILE_FILE, "user": "roles.json", "preset": "preset " + PRESET, "proposal": "proposal",
                "snapshot": "profile snapshot"}
STATE_NAMES = {"never": "not accepted", "later": "not saved (postponed)", "accepted": "accepted",
               "missing": "the accepted profile file was deleted", "malformed": "the profile file is damaged"}

# The frozen preset zplan.default/1: today's role defaults (critic is the plan verifier), plan gate on, task and
# merge gates off. A change ships as /2 with a migration shown to the owner, never as an edit of /1.
#
# zplan.default/2 is the same roles, gates and limits plus the `autonomy` section the later slices read (the foreman,
# the autonomy gate, the wake-up and stuck rules, admission): the autonomy level and `max_runs` act today and are
# shown as they are; the rest of the section is shown "for later stages". The whole-number defaults and bounds come from ARCHITECT_DESIGN 4.2/4.3 (a worker
# round past 45 min, a run past 2 h, round 3, three runs, the wake-up hourly cap, the architect retry limit).
#
# zplan.default/3 is /2 with the worker on gpt-6.1-terra at effort max; what a first start proposes.
PRESETS = {
    PRESET: {
        "roles": {"planner": ("gpt-6.1-sol", "high"), "critic": ("gpt-6.1-sol", "high"),
                  "worker": ("gpt-6.1-sol", "medium"), "reviewer": ("gpt-6.1-sol", "high"),
                  "steward": ("gpt-6.1-sol", "high"), "architect": ("gpt-6.1-sol", "high")},
        "gates": {"plan": "required", "task": "off", "merge": "off"},
        "limits": {"plan_rounds": 3, "task_rounds": 2, "merge_rounds": 2},
    },
    PRESET_V2: {
        "roles": {"planner": ("gpt-6.1-sol", "high"), "critic": ("gpt-6.1-sol", "high"),
                  "worker": ("gpt-6.1-sol", "medium"), "reviewer": ("gpt-6.1-sol", "high"),
                  "steward": ("gpt-6.1-sol", "high"), "architect": ("gpt-6.1-sol", "high")},
        "gates": {"plan": "required", "task": "off", "merge": "off"},
        "limits": {"plan_rounds": 3, "task_rounds": 2, "merge_rounds": 2},
        "autonomy": {"level": "auto", "max_runs": 3, "worker_round_minutes": 45, "run_minutes": 120,
                     "structural_round": 3, "wakeups_per_hour": 12, "architect_retries": 3},
        # Generic defaults: documentation is low; installer, toolchain, packaging, CI manifests and secrets are high.
        # A project's own paths come from its profile (a list there replaces the preset's whole list). The last three
        # triggers have no paths: the gatekeeper raises them by name.
        "risk": {
            "rules": [{"paths": ["**/*.md", "docs/**"], "tier": "low"},
                      {"paths": ["**/install*", "pyproject.toml", "setup.py", "package.json", "Cargo.toml",
                                 "**/*.lock", "Dockerfile", ".github/**", "**/.env*", "**/*secret*",
                                 "**/*credential*", "**/*.pem", "**/*.key"], "tier": "high"}],
            "triggers": [{"name": "secrets", "paths": ["**/.env*", "**/*secret*", "**/*credential*", "**/*.pem",
                                                       "**/*.key"]},
                         {"name": "installer", "paths": ["**/install*"]},
                         {"name": "toolchain", "paths": ["pyproject.toml", "setup.py", "package.json", "Cargo.toml",
                                                         "**/*.lock"]},
                         {"name": "packaging", "paths": ["Dockerfile", ".github/**"]},
                         {"name": "data_loss", "paths": []},
                         {"name": "process_kill", "paths": []},
                         {"name": "disagreement", "paths": []}],
        },
    },
}
# zplan.default/3 is /2 as it is (gates, limits, `autonomy`, `risk`); only the worker binding differs.
PRESETS[PRESET_V3] = dict(copy.deepcopy(PRESETS[PRESET_V2]),
                          roles=dict(PRESETS[PRESET_V2]["roles"], worker=("gpt-6.1-terra", "max")))


class ProfileChanged(Blocked):
    """The profile changed after a preview was shown: the owner confirms the new one."""
    family = "process.changed"


# Errors --------------------------------------------------------------------------------------------------------

def invalid(key, problem, fix):
    """A file problem: names the key, what is wrong and the fix."""
    return Blocked("%s: key '%s' - %s. %s" % (PROFILE_FILE, key, problem, fix), family="process.invalid")


def corrupt_state(path, reason):
    return Blocked("The profile state is damaged (%s): %s. Delete this file - the profile will be proposed again; "
                   "plans and runs are not affected." % (reason, path), family="process.state")


# Schema --------------------------------------------------------------------------------------------------------

def binding(key, value, efforts=NATIVE_EFFORTS):
    if not (isinstance(value, dict) and set(value) == {"model", "effort"}):
        raise invalid(key, "an object {\"model\": ..., \"effort\": ...} is required",
                      "Give model and effort, or delete the key to take the preset's value.")
    if not (isinstance(value["model"], str) and MODEL.fullmatch(value["model"])):
        raise invalid(key + ".model", "invalid model id", "Give a model ID, for example gpt-6.1-terra.")
    if not (isinstance(value["effort"], str) and value["effort"] in efforts):
        raise invalid(key + ".effort", "allowed: " + ", ".join(sorted(efforts)), "Fix the value.")
    return {"model": value["model"], "effort": value["effort"]}


def _object(key, value, names):
    if not isinstance(value, dict):
        raise invalid(key, "an object is required", "Allowed keys: %s." % ", ".join(names))
    for name in value:
        if name not in names:
            extra = " The role plan_verifier is called critic." if name == "plan_verifier" else ""
            raise invalid("%s.%s" % (key, name), "unknown key", "Allowed: %s.%s" % (", ".join(names), extra))
    return value


def validate_rule_path(index, value):
    key = "rules[%d]" % index
    if not (isinstance(value, str) and value.strip() and "\0" not in value):
        raise invalid(key, "a file path in the repository is required", "Give a relative path, for example AGENTS.md.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise invalid(key, "path %r is outside the repository" % value, "Give a path relative to the project root without '..'.")
    return value


def validate_check(index, value):
    key = "checks[%d]" % index
    if not (isinstance(value, dict) and {"name", "argv"} <= set(value) <= {"name", "argv", "timeout_s"}):
        raise invalid(key, "an object {\"name\", \"argv\", \"timeout_s\"} is required",
                      "Example: {\"name\": \"unit\", \"argv\": [\"python3\", \"-m\", \"unittest\"], \"timeout_s\": 1800}.")
    if not (isinstance(value["name"], str) and NAME.fullmatch(value["name"])):
        raise invalid(key + ".name", "a short name of Latin letters, digits, '_', '.', '-' is required", "Fix the check name.")
    argv = value["argv"]
    if not isinstance(argv, list) or not argv:
        raise invalid(key + ".argv", "the check command is empty",
                      "Give a program and arguments, for example [\"npm\", \"test\"], or delete this check.")
    if not all(isinstance(a, str) and a and "\0" not in a for a in argv):
        raise invalid(key + ".argv", "every command element must be a non-empty string", "Fix the command.")
    timeout = value.get("timeout_s", DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 86400:
        raise invalid(key + ".timeout_s", "a whole number of seconds from 1 to 86400 is required", "Fix the timeout.")
    return {"name": value["name"], "argv": list(argv), "timeout_s": timeout}


def validate_pattern(key, value):
    """A relative POSIX glob (`glob_match`): not absolute, no `..`, at most MAX_PATTERN_CHARS."""
    if not (isinstance(value, str) and value.strip() and "\0" not in value):
        raise invalid(key, "a path pattern is required", "For example \"docs/**\".")
    if len(value) > MAX_PATTERN_CHARS:
        raise invalid(key, "the pattern is longer than %d characters" % MAX_PATTERN_CHARS, "Shorten the pattern.")
    if value.startswith("/") or ".." in PurePosixPath(value).parts:
        raise invalid(key, "pattern %r is outside the repository" % value,
                      "Give a path relative to the project root, without a leading '/' and without '..'.")
    return value


def validate_patterns(key, value, least):
    if not isinstance(value, list) or not least <= len(value) <= MAX_RISK_PATTERNS:
        raise invalid(key, "a list of path patterns is required (%d to %d)" % (least, MAX_RISK_PATTERNS),
                      "For example [\"docs/**\"].")
    return [validate_pattern("%s[%d]" % (key, i), v) for i, v in enumerate(value)]


def validate_risk(value):
    risk = _object("risk", value, RISK)
    result = {}
    if "rules" in risk:
        rules = risk["rules"]
        if not isinstance(rules, list) or not 1 <= len(rules) <= MAX_RISK_RULES:
            raise invalid("risk.rules", "a list of rules is required (1 to %d)" % MAX_RISK_RULES,
                          "For example [{\"paths\": [\"docs/**\"], \"tier\": \"low\"}].")
        result["rules"] = []
        for index, rule in enumerate(rules):
            key = "risk.rules[%d]" % index
            rule = _object(key, rule, ("paths", "tier"))
            if set(rule) != {"paths", "tier"}:
                raise invalid(key, "an object {\"paths\", \"tier\"} is required", "Give both keys.")
            if not (isinstance(rule["tier"], str) and rule["tier"] in RISK_TIERS):
                raise invalid(key + ".tier", "allowed: " + ", ".join(RISK_TIERS), "Fix the value.")
            result["rules"].append({"paths": validate_patterns(key + ".paths", rule["paths"], 1),
                                    "tier": rule["tier"]})
    if "triggers" in risk:
        triggers = risk["triggers"]
        if not isinstance(triggers, list) or not 1 <= len(triggers) <= MAX_RISK_TRIGGERS:
            raise invalid("risk.triggers", "a list of triggers is required (1 to %d)" % MAX_RISK_TRIGGERS,
                          "For example [{\"name\": \"secrets\", \"paths\": [\"**/.env*\"]}].")
        result["triggers"] = []
        for index, trigger in enumerate(triggers):
            key = "risk.triggers[%d]" % index
            trigger = _object(key, trigger, ("name", "paths"))
            if set(trigger) != {"name", "paths"}:
                raise invalid(key, "an object {\"name\", \"paths\"} is required", "Give both keys.")
            if not (isinstance(trigger["name"], str) and NAME.fullmatch(trigger["name"])):
                raise invalid(key + ".name", "a short name of Latin letters, digits, '_', '.', '-' is required",
                              "Fix the trigger name.")
            result["triggers"].append({"name": trigger["name"],
                                       "paths": validate_patterns(key + ".paths", trigger["paths"], 0)})
        if len({t["name"] for t in result["triggers"]}) != len(triggers):
            raise invalid("risk.triggers", "the trigger name is given twice", "Give the triggers different names.")
    return result


def validate_profile(value):
    """Strict check of a profile (file or snapshot): returns the normalized partial document; raises
    Blocked(process.invalid) naming the key. File existence and containment of `rules` are checked by
    `read_rules`, because they depend on the project."""
    if not isinstance(value, dict):
        raise invalid("(root)", "a JSON object is required", "Allowed keys: %s." % ", ".join(TOP_KEYS))
    for name in value:
        if name not in TOP_KEYS:
            raise invalid(name, "unknown key", "Delete it or fix the typo; allowed: %s." % ", ".join(TOP_KEYS))
    result = {}
    preset_name = PRESET
    if "preset" in value:
        if not isinstance(value["preset"], str) or value["preset"] not in PRESETS:
            raise invalid("preset", "unknown preset %r" % (value["preset"],),
                          "Available: " + ", ".join(PRESETS) + ".")
        result["preset"] = value["preset"]
        preset_name = value["preset"]
    if "rules" in value:
        rules = value["rules"]
        if not isinstance(rules, list) or len(rules) > MAX_RULES:
            raise invalid("rules", "a list of paths is required (at most %d)" % MAX_RULES, "For example [\"AGENTS.md\"].")
        result["rules"] = [validate_rule_path(i, v) for i, v in enumerate(rules)]
        if len(set(result["rules"])) != len(rules):
            raise invalid("rules", "the path is given twice", "Remove the repeat.")
    if "roles" in value:
        roles = _object("roles", value["roles"], ROLES)
        result["roles"] = {name: binding("roles." + name, roles[name]) for name in roles}
    if "gates" in value:
        gates = _object("gates", value["gates"], GATES)
        result["gates"] = {}
        for name in gates:
            if gates[name] not in ("required", "off"):
                raise invalid("gates." + name, "allowed: required or off", "Fix the value.")
            result["gates"][name] = gates[name]
        if result["gates"].get("plan", "required") != "required":
            raise invalid("gates.plan", "in this version the plan is always checked",
                          "Restore required or delete the key.")
    if "limits" in value:
        limits = _object("limits", value["limits"], LIMITS)
        result["limits"] = {}
        for name in limits:
            number = limits[name]
            top = PLAN_ROUNDS[1] if name == "plan_rounds" else 10
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= top:
                raise invalid("limits." + name, "a whole number from 1 to %d is required" % top, "Fix the value.")
            result["limits"][name] = number
    if "autonomy" in value:
        # The section is data of zplan.default/2 only; in /1 it is refused naming the preset that carries it (the
        # key is a top key so the owner gets this fix, not the generic "unknown key").
        if "autonomy" not in PRESETS[preset_name]:
            raise invalid("autonomy", "the autonomy section exists only in preset %s; give \"preset\": \"%s\""
                          % (PRESET_V2, PRESET_V2), "Fix the value.")
        autonomy = _object("autonomy", value["autonomy"], AUTONOMY)
        result["autonomy"] = {}
        for name in autonomy:
            number = autonomy[name]
            if name == "level":
                if not (isinstance(number, str) and number in AUTONOMY_LEVELS):
                    raise invalid("autonomy.level", "allowed: " + ", ".join(sorted(AUTONOMY_LEVELS)),
                                  "Fix the value.")
            else:
                low, high = AUTONOMY_RANGES[name]
                if isinstance(number, bool) or not isinstance(number, int) or not low <= number <= high:
                    raise invalid("autonomy." + name, "a whole number from %d to %d is required" % (low, high),
                                  "Fix the value.")
            result["autonomy"][name] = number
    if "risk" in value:
        if "risk" not in PRESETS[preset_name]:  # like `autonomy`: refused in /1 naming the preset that carries it
            raise invalid("risk", "the risk section exists only in preset %s; give \"preset\": \"%s\""
                          % (PRESET_V2, PRESET_V2), "Fix the value.")
        result["risk"] = validate_risk(value["risk"])
    if "checks" in value:
        checks = value["checks"]
        if not isinstance(checks, list) or len(checks) > MAX_CHECKS:
            raise invalid("checks", "a list of checks is required (at most %d)" % MAX_CHECKS, "An empty list means no qualification.")
        result["checks"] = [validate_check(i, v) for i, v in enumerate(checks)]
        if len({c["name"] for c in result["checks"]}) != len(checks):
            raise invalid("checks", "the check name is given twice", "Give the checks different names.")
    return result


def read_rules(project, paths):
    """((path, sha256), ...) of the rules files in listed order. A path outside the repository (also through a
    link) or a missing file is refused with the key and the fix."""
    root = Path(project).resolve()
    found = []
    for index, name in enumerate(paths):
        key = "rules[%d]" % index
        target = (root / name).resolve()
        if root != target and root not in target.parents:
            raise invalid(key, "path %r is outside the repository" % name, "Give a file inside the project.")
        if not target.is_file():
            raise invalid(key, "file %r not found" % name, "Create the file or remove the path from rules.")
        try:
            if target.stat().st_size > MAX_RULE_BYTES:
                raise invalid(key, "file %r is larger than %d KB" % (name, MAX_RULE_BYTES // 1024), "Shorten the rules.")
            content = target.read_bytes()
        except OSError as error:
            raise invalid(key, "file %r cannot be read (%s)" % (name, error.strerror or error), "Check the permissions.") from error
        found.append((name, hashlib.sha256(content).hexdigest()))
    return tuple(found)


def freeze_rules(project, rules):
    """The rules of a resolved configuration as an agent gets them: [{path, sha256, text}] in listed order, read
    once more from the project and checked against the hashes the configuration was resolved with. Together at
    most RULES_LIMIT UTF-8 bytes (the file that goes over is named); a non-UTF-8 file is refused."""
    root = Path(project).resolve()
    total, frozen = 0, []
    for index, (name, expected) in enumerate(rules):
        key = "rules[%d]" % index
        try:
            content = (root / name).resolve().read_bytes()
        except OSError as error:
            raise invalid(key, "file %r cannot be read (%s)" % (name, error.strerror or error), "Check the file.") from error
        if hashlib.sha256(content).hexdigest() != expected:
            raise ProfileChanged("The rules %s changed while the plan was being prepared. Repeat the action." % name)
        total += len(content)
        if total > RULES_LIMIT:
            raise invalid(key, "the rules together are larger than %d KiB: file %r does not fit" % (RULES_LIMIT // 1024, name),
                          "Shorten %s or remove the file from rules: agents get at most %d KiB."
                          % (name, RULES_LIMIT // 1024))
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise invalid(key, "file %r is not UTF-8" % name, "Save it as UTF-8 or remove it from rules.") from error
        frozen.append({"path": name, "sha256": expected, "text": text})
    return frozen


# Resolution ----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolved:
    """The effective configuration, where each key came from, and its canonical digest (rules content included)."""
    config: dict
    sources: dict
    rules: Tuple[Tuple[str, str], ...]
    digest: str

    @property
    def short(self):
        return self.digest[:12]

    def roles(self):
        """The five role bindings the planning and milestone services take (`critic` is their `plan_verifier`)."""
        names = {"planner": "planner", "plan_verifier": "critic", "worker": "worker", "reviewer": "reviewer",
                 "steward": "steward"}
        return {legacy: dict(self.config["roles"][name]) for legacy, name in names.items()}


def config_digest(config, rules):
    return digest({"version": 1, "config": config, "rules": [list(r) for r in rules]})


def saved_roles(path=None):
    """Bindings explicitly saved in the user's roles.json under profile names (`plan_verifier` read as `critic`);
    empty when the file is absent or empty. Never the defaults `setup.load_roles()` fills in."""
    path = Path(path) if path is not None else config_root() / "roles.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError) as error:
        raise Blocked("roles.json cannot be read (%s); run zplan roles or delete %s." % (error, path),
                      family="readiness.roles") from error
    if not text.strip():
        return {}
    try:
        value = decode(text)
    except Blocked as error:
        raise Blocked("roles.json is damaged; run zplan roles or delete %s." % path,
                      family="readiness.roles") from error
    if not isinstance(value, dict):
        raise Blocked("roles.json is damaged: an object is required; run zplan roles or delete %s." % path,
                      family="readiness.roles")
    found = {}
    for name, item in value.items():
        target = "critic" if name == "plan_verifier" else name
        if target not in ROLES or (name == "plan_verifier" and "critic" in value):
            continue  # roles of other versions are ignored, like setup.load_roles
        try:
            saved = binding(name, item, HISTORICAL_EFFORTS)
        except Blocked as error:
            raise Blocked("roles.json: role %s is set incorrectly; run zplan roles or delete %s." % (name, path),
                          family="readiness.roles") from error
        if saved["effort"] in NATIVE_EFFORTS:  # a legacy effort counts as not saved: the preset applies
            found[target] = saved
    return found


def resolve(partial, saved, project=None, origin="file"):
    """Project document (already validated; None: none) -> saved roles.json -> preset, per key."""
    partial = partial or {}
    preset_name = partial.get("preset", PRESET)
    preset = PRESETS[preset_name]
    config = {"preset": preset_name, "rules": [], "roles": {}, "gates": {}, "limits": {}, "checks": []}
    if "autonomy" in preset:  # the key set follows the preset: /1 has no `autonomy`, so its config and digest hold
        config["autonomy"] = {}
    if "risk" in preset:
        config["risk"] = {}
    sources = {"preset": origin if "preset" in partial else "preset"}
    for name in ROLES:
        if name in partial.get("roles", {}):
            config["roles"][name], sources["roles." + name] = dict(partial["roles"][name]), origin
        elif name in saved:
            config["roles"][name], sources["roles." + name] = dict(saved[name]), "user"
        else:
            model, effort = preset["roles"][name]
            config["roles"][name], sources["roles." + name] = {"model": model, "effort": effort}, "preset"
    for section, names in (("gates", GATES), ("limits", LIMITS)):
        for name in names:
            if name in partial.get(section, {}):
                config[section][name], sources["%s.%s" % (section, name)] = partial[section][name], origin
            else:
                config[section][name], sources["%s.%s" % (section, name)] = preset[section][name], "preset"
    if "autonomy" in preset:
        for name in AUTONOMY:
            if name in partial.get("autonomy", {}):
                config["autonomy"][name], sources["autonomy." + name] = partial["autonomy"][name], origin
            else:
                config["autonomy"][name], sources["autonomy." + name] = preset["autonomy"][name], "preset"
    if "risk" in preset:
        for name in RISK:  # each list comes whole from the file or whole from the preset
            if name in partial.get("risk", {}):
                config["risk"][name], sources["risk." + name] = copy.deepcopy(partial["risk"][name]), origin
            else:
                config["risk"][name], sources["risk." + name] = copy.deepcopy(preset["risk"][name]), "preset"
    for name in ("rules", "checks"):
        config[name] = list(partial.get(name, ()))
        sources[name] = origin if name in partial else "preset"
    rules = read_rules(project, config["rules"]) if config["rules"] else ()
    return Resolved(config, sources, rules, config_digest(config, rules))


def complete(config):
    """A full resolved configuration (a snapshot), validated; returns it normalized."""
    if not isinstance(config, dict):
        raise ValueError("snapshot keys")
    normalized = validate_profile(config)
    # The key set is the preset's: /1 has no `autonomy` or `risk`, /2 has both in full; a snapshot must carry
    # exactly the keys its own preset resolves to.
    expected = set(TOP_KEYS) - {k for k in V2_KEYS if k not in PRESETS[normalized["preset"]]}
    if set(config) != expected:
        raise ValueError("snapshot keys")
    if (set(normalized.get("roles", ())) != set(ROLES) or set(normalized.get("gates", ())) != set(GATES)
            or set(normalized.get("limits", ())) != set(LIMITS) or "preset" not in normalized):
        raise ValueError("snapshot is not complete")
    if "autonomy" in PRESETS[normalized["preset"]] and set(normalized.get("autonomy", ())) != set(AUTONOMY):
        raise ValueError("snapshot is not complete")
    if "risk" in PRESETS[normalized["preset"]] and set(normalized.get("risk", ())) != set(RISK):
        raise ValueError("snapshot is not complete")
    return normalized


def _glob_segment(part):
    """One path segment -> a regular expression where `*` and `?` stay inside the segment (`[^/]`); the hand-written
    translation `fnmatch.translate` would produce, classes (`[...]`, `[!...]`, ranges) included."""
    out = []
    index, size = 0, len(part)
    while index < size:
        char = part[index]
        index += 1
        if char == "*":
            if not out or out[-1] != "[^/]*":
                out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = index
            if end < size and part[end] == "!":
                end += 1
            if end < size and part[end] == "]":
                end += 1
            while end < size and part[end] != "]":
                end += 1
            if end >= size:  # an unterminated `[` is a literal bracket
                out.append(r"\[")
            else:
                stuff = part[index:end]
                if "-" not in stuff:
                    stuff = stuff.replace("\\", r"\\")
                else:
                    chunks = []
                    k = index + 2 if part[index] == "!" else index + 1
                    while True:
                        k = part.find("-", k, end)
                        if k < 0:
                            break
                        chunks.append(part[index:k])
                        index = k + 1
                        k = k + 3
                    chunk = part[index:end]
                    if chunk:
                        chunks.append(chunk)
                    else:
                        chunks[-1] += "-"
                    for k in range(len(chunks) - 1, 0, -1):
                        if chunks[k - 1][-1] > chunks[k][0]:
                            chunks[k - 1] = chunks[k - 1][:-1] + chunks[k][1:]
                            del chunks[k]
                    stuff = "-".join(s.replace("\\", r"\\").replace("-", r"\-") for s in chunks)
                stuff = re.sub(r"([&~|])", r"\\\1", stuff)
                index = end + 1
                if not stuff:
                    out.append("(?!)")
                elif stuff == "!":
                    out.append(".")
                else:
                    if stuff[0] == "!":
                        stuff = "^" + stuff[1:]
                    elif stuff[0] in ("^", "["):
                        stuff = "\\" + stuff
                    out.append("[%s]" % stuff)
        else:
            out.append(re.escape(char))
    return "".join(out)


def glob_match(path, pattern):
    """`PurePosixPath.full_match` (Python 3.13+) for the pattern domain `validate_pattern` accepts, on every
    Python >= 3.11: segments split on `/`; `**` as a whole segment covers zero or more segments (inside a segment it
    acts as `*`); `*` matches within one segment, `?` one character other than `/`, `[...]`/`[!...]` one character of
    a class; matching is case-sensitive and the whole path must match."""
    parts = PurePosixPath(pattern).parts
    text = "/".join(PurePosixPath(path).parts)
    regex, last = [], len(parts) - 1
    for index, part in enumerate(parts):
        if part == "*":
            regex.append("[^/]+" if index == last else "[^/]+/")
        elif part == "**":
            if index == last:
                regex.append("(?:[^/]+/)*(?:[^/]+)?")
            elif parts[index + 1] != "**":
                regex.append("(?:[^/]+/)*")
        else:
            if part:
                regex.append(_glob_segment(part))
            if index != last:
                regex.append("/")
    return re.compile("".join(regex) + r"\Z", re.DOTALL).match(text) is not None


def risk_of(config, paths):
    """The risk of a candidate's changed paths under a resolved /2 configuration: {"tier", "triggers" (names, sorted),
    "unmatched" (paths no rule covers)}. A path takes the highest tier of the rules it matches; a path no rule
    covers counts as medium; the result is the highest of the paths, and no paths at all is high (nothing to judge)."""
    risk = config["risk"]
    order = {tier: n for n, tier in enumerate(RISK_TIERS)}
    tier, unmatched, triggers = None, [], set()
    for path in paths:
        found = [rule["tier"] for rule in risk["rules"] if any(glob_match(path, p) for p in rule["paths"])]
        if not found:
            unmatched.append(path)
            found = ["medium"]
        top = max(found, key=order.__getitem__)
        if tier is None or order[top] > order[tier]:
            tier = top
        triggers.update(t["name"] for t in risk["triggers"] if any(glob_match(path, p) for p in t["paths"]))
    return {"tier": tier or "high", "triggers": sorted(triggers), "unmatched": unmatched}


# Proposal ------------------------------------------------------------------------------------------------------

def detect_checks(root):
    """The one obvious test command, found by reading files only (nothing is executed): package.json scripts.test,
    else a Makefile `test:` target, else pytest when it is configured, else `test_*.py` files under tests/ (unittest
    discovery); otherwise none."""
    root = Path(root)
    manifest = root / "package.json"
    try:
        if manifest.is_file() and manifest.stat().st_size <= MAX_FILE_BYTES * 16:
            scripts = json.loads(manifest.read_text(encoding="utf-8")).get("scripts")
            text = scripts.get("test") if isinstance(scripts, dict) else None
            if isinstance(text, str) and text.strip() and "no test specified" not in text:
                return [{"name": "test", "argv": ["npm", "test"], "timeout_s": DEFAULT_TIMEOUT}]
    except (OSError, UnicodeError, ValueError, AttributeError):
        pass
    try:
        make = root / "Makefile"
        if make.is_file() and make.stat().st_size <= MAX_FILE_BYTES * 16:
            if re.search(r"^test[ \t]*:", make.read_text(encoding="utf-8", errors="replace"), re.MULTILINE):
                return [{"name": "test", "argv": ["make", "test"], "timeout_s": DEFAULT_TIMEOUT}]
    except OSError:
        pass
    if _pytest_configured(root):
        return [{"name": "test", "argv": ["python3", "-m", "pytest"], "timeout_s": DEFAULT_TIMEOUT}]
    try:
        if next((root / "tests").rglob("test_*.py"), None) is not None:
            return [{"name": "test", "argv": ["python3", "-m", "unittest", "discover", "-s", "tests"],
                     "timeout_s": DEFAULT_TIMEOUT}]
    except OSError:
        pass
    return []


def _pytest_configured(root):
    """pytest.ini, a `[tool.pytest` table in pyproject.toml or a `[tool:pytest]` section in setup.cfg (files read only)."""
    if (root / "pytest.ini").is_file():
        return True
    for name, marker in (("pyproject.toml", "[tool.pytest"), ("setup.cfg", "[tool:pytest]")):
        try:
            path = root / name
            if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES * 16 \
                    and marker in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def found_rules(root):
    root = Path(root).resolve()
    names = []
    for name in RULE_CANDIDATES:
        target = (root / name).resolve()
        try:
            if root in target.parents and target.is_file() and target.stat().st_size <= MAX_RULE_BYTES:
                names.append(name)
        except OSError:
            continue
    return names


def propose(project, saved):
    """The profile a first start offers: the preset with the roles the owner already saved, the rules files found
    and the obvious test command. Written verbatim on accept. The merge gate is offered `required` only where a check
    was found (a required gate without checks refuses every merge); the preset's constants are not changed."""
    base = resolve({"preset": PRESET_V3}, saved, project)
    checks = detect_checks(project)
    gates = dict(base.config["gates"])
    if checks:
        gates["merge"] = "required"
    return {"preset": PRESET_V3, "rules": found_rules(project),
            "roles": {name: dict(base.config["roles"][name]) for name in ROLES},
            "gates": gates, "limits": dict(base.config["limits"]),
            "autonomy": dict(base.config["autonomy"]), "checks": checks}


@dataclass(frozen=True)
class Form:
    """What the profile editor starts from: the effective values of the keys it offers. `level` and `max_runs` are
    None for a preset without `autonomy` (the editor hides them); `checks` says whether a check exists, because the
    merge gate `required` runs them."""
    level: Optional[str]
    max_runs: Optional[int]
    merge: str
    checks: bool
    roles: Tuple[Tuple[str, str, str], ...]  # (role, model, effort) in ROLES order


def form_of(config):
    autonomy = config.get("autonomy", {})
    return Form(autonomy.get("level"), autonomy.get("max_runs"), config["gates"]["merge"], bool(config["checks"]),
                tuple((name, config["roles"][name]["model"], config["roles"][name]["effort"]) for name in ROLES))


CHANGE_KEYS = ("level", "max_runs", "merge", "roles")


def apply_changes(document, changes):
    """A copy of the profile `document` with the owner's `changes` set and nothing else touched, validated like a
    file: {"level", "max_runs", "merge", "roles": {name: {"model", "effort"}}}, each only when the owner changed it.
    Keys the editor does not offer, other sections and unknown parts of `document` stay as they were. Raises
    Blocked(process.invalid) naming the key, so nothing is written for a refused value."""
    if not set(changes) <= set(CHANGE_KEYS):
        raise ValueError("unknown change: %s" % ", ".join(sorted(set(changes) - set(CHANGE_KEYS))))
    result = copy.deepcopy(document)
    for key in ("level", "max_runs"):
        if key in changes:
            result.setdefault("autonomy", {})[key] = changes[key]
    if "merge" in changes:
        result.setdefault("gates", {})["merge"] = changes["merge"]
    for name, bound in changes.get("roles", {}).items():
        result.setdefault("roles", {})[name] = dict(bound)
    validate_profile(result)
    if changes.get("merge") == "required" and not result.get("checks"):
        raise invalid("gates.merge", "merging on checks requires at least one check, and there are none",
                      "Choose 'ask' or add checks to %s." % PROFILE_FILE)
    return result


def document_of(config):
    """The profile document a snapshot stands for: its resolved keys, `risk` only where it differs from the preset's
    (a proposal never carries it)."""
    preset = PRESETS[config["preset"]]
    return {key: copy.deepcopy(config[key]) for key in TOP_KEYS
            if key in config and not (key == "risk" and config[key] == preset.get("risk"))}


# State sidecar -------------------------------------------------------------------------------------------------

def _snapshot_ok(snapshot):
    if not (isinstance(snapshot, dict) and set(snapshot) == {"config", "rules", "sources"}):
        return False
    try:
        complete(snapshot["config"])
    except (Blocked, ValueError):
        return False
    rules = snapshot["rules"]
    return (isinstance(rules, list) and all(isinstance(r, list) and len(r) == 2 and isinstance(r[0], str)
                                           and isinstance(r[1], str) and SHA.fullmatch(r[1]) for r in rules)
            and isinstance(snapshot["sources"], dict)
            and all(isinstance(k, str) and v in SOURCE_NAMES for k, v in snapshot["sources"].items()))


def _record_ok(value, nested=False):
    if not isinstance(value, dict) or set(value) != {"state", "digest", "snapshot"} | (set() if nested else {"schema", "previous"}):
        return False
    state = value["state"]
    if state not in (("later", "accepted") if nested else ("later", "accepting", "accepted")):
        return False
    if state == "accepting":
        return value["digest"] is None and value["snapshot"] is None
    if not (isinstance(value["digest"], str) and SHA.fullmatch(value["digest"])):
        return False
    # "accepted" normally has no snapshot (the file is the source). A fixture session records the accepted
    # snapshot here instead of writing the target's file (R-3), so an accepted record may carry one; "later"
    # always does.
    if state == "accepted":
        return value["snapshot"] is None or _snapshot_ok(value["snapshot"])
    return _snapshot_ok(value["snapshot"])


def read_record(directory):
    """The sidecar's content, or None when there is none (never accepted). Corrupt: Blocked(process.state)."""
    path = Path(directory) / STATE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as error:
        raise corrupt_state(path, "cannot be read") from error
    try:
        value = decode(text)
    except Blocked as error:
        raise corrupt_state(path, "not JSON") from error
    ok = (_record_ok(value) and value["schema"] == 1 and
          (value["previous"] is None or (value["state"] == "accepting" and _record_ok(value["previous"], True))))
    if not ok or (value["state"] != "accepting" and value["previous"] is not None):
        raise corrupt_state(path, "unknown format")
    return value


def make_record(state, digest_value=None, snapshot=None, previous=None):
    return {"schema": 1, "state": state, "digest": digest_value, "snapshot": snapshot, "previous": previous}


def snapshot_of(resolved):
    return {"config": resolved.config, "rules": [list(r) for r in resolved.rules], "sources": resolved.sources}


def from_snapshot(snapshot, project):
    """The "later" configuration the owner saw, with its rules read again from the project as they are now (a change
    or a deletion changes the digest or is refused like in a file profile; the stored hashes are only what was shown)."""
    config = complete(snapshot["config"])
    rules = read_rules(project, config["rules"]) if config["rules"] else ()
    return Resolved(config, dict(snapshot["sources"]), rules, config_digest(config, rules))


# Status --------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Status:
    """Where the project's profile stands now. `resolved` is None for missing/malformed (new actions refused)."""
    state: str  # never | later | accepted | missing | malformed
    resolved: Optional[Resolved]
    present: bool = False  # the project file exists
    problem: str = ""
    notice: str = ""
    proposal: Optional[dict] = field(default=None, compare=False)  # state never: what accept writes

    @property
    def digest(self):
        return self.resolved.digest if self.resolved is not None else ""


class Profile:
    """The project's profile for one Authority directory. `authority` (the session holding the lock) is required for
    every write; without it the object only reads."""

    def __init__(self, project, directory, authority=None, roles_path=None, fixture=False):
        self.project = Path(project).resolve()
        self.directory = Path(directory)
        self.authority = authority
        self.roles_path = roles_path
        self.fixture = fixture  # a `--fixture ID` session: the target's file is never written (R-3)

    @classmethod
    def of(cls, authority, roles_path=None):
        return cls(authority.project, authority.directory, authority, roles_path,
                   fixture=authority.fixture_id is not None)

    @classmethod
    def peek(cls, project, roles_path=None, root=None, fixture_id=None):
        """Read-only view without a session (doctor, `zplan profile`, `zplan roles`): the state directory an
        Authority would use, no lock and nothing created. The sidecar is replaced atomically, so reading it without
        the lock sees either the old or the new record, never a torn one; doctor needs this while a session is open."""
        project = Path(project)
        project_id = hashlib.sha256(str(common_directory(project)).encode()).hexdigest()
        if fixture_id is not None:
            base = Path(root).expanduser().resolve() if root else production_root().parent.parent
            directory = base / "v3" / "fixtures" / fixture_id / project_id
        else:
            directory = production_root() / project_id
        return cls(project, directory, None, roles_path, fixture=fixture_id is not None)

    @property
    def file(self):
        return self.project / PROFILE_FILE

    def writable(self):
        return self.authority is not None and getattr(self.authority, "lock", None) is not None

    def _write(self, record):
        if not self.writable():
            raise Blocked("The profile can only be changed in the session that holds the project.", family="action.refused")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_state(self.directory / STATE_FILE, record)

    def _accepted_record(self, resolved):
        """The `accepted` record this session writes: a native one names the file's digest only (the project file
        is the source), while a fixture session also carries the effective snapshot, so the accepted profile still
        resolves after the project file is removed (R-3) instead of reading as deleted."""
        return make_record("accepted", resolved.digest, snapshot_of(resolved) if self.fixture else None)

    def _drop(self):
        if self.writable():
            (self.directory / STATE_FILE).unlink(missing_ok=True)

    def _read_file(self):
        """The validated project document, None when the file is absent; Blocked(process.invalid) otherwise."""
        path = self.file
        try:
            if not os.path.lexists(path):
                return None
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise invalid("(file)", "this is not a regular file or it is larger than %d KB" % (MAX_FILE_BYTES // 1024),
                              "Replace it with valid JSON or delete it and run zplan profile init.")
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise invalid("(file)", "cannot be read (%s)" % error, "Check the permissions or delete the file.") from error
        try:
            value = decode(text)
        except Blocked as error:
            raise invalid("(file)", "not JSON or a repeated key",
                          "Fix the file (git diff shows the changes) or delete it and run zplan profile init.") from error
        return validate_profile(value)

    def status(self, write=True):
        """Evaluate file + sidecar (+ roles.json); finishes an interrupted accept and adopts a file that appeared
        after "later" when this session holds the lock. `write=False` reports the same status and writes nothing."""
        write = write and self.writable()
        record = read_record(self.directory)
        saved = saved_roles(self.roles_path)
        present = os.path.lexists(self.file)
        try:
            partial = self._read_file()
            resolved = resolve(partial, saved, self.project) if partial is not None else None
            problem = ""
        except Blocked as error:
            partial, resolved, problem = None, None, str(error)
        if record is not None and record["state"] == "accepting":
            if present:  # the file was written: finish the accept (an unreadable file is refused below)
                # R-3: in a fixture session the finished accept keeps the effective snapshot too, so an accept
                # interrupted between the file and the record still survives the file's removal.
                record = (self._accepted_record(resolved) if self.fixture and resolved is not None
                          else make_record("accepted", resolved.digest if resolved is not None else digest(None)))
                if write:
                    self._write(record)
            else:  # the crash came before the file: back to what it was
                before = record["previous"]
                record = make_record(before["state"], before["digest"], before["snapshot"]) if before else None
                if write:
                    self._write(record) if record is not None else self._drop()
        state = record["state"] if record is not None else "never"
        if problem:
            return Status("malformed", None, present, problem)
        if present:
            if state == "never":
                return Status("never", resolved, True, proposal=partial)
            notice = ""
            if state == "later":
                notice = "Found %s: the profile is accepted." % PROFILE_FILE
                if write:
                    self._write(self._accepted_record(resolved))
            elif state == "accepted" and write and resolved is not None:
                if self.fixture and record["snapshot"] is None:
                    # R-3: an accepted record without a snapshot (an older or interrupted fixture accept) is
                    # completed with the file's effective snapshot, so the accepted profile still resolves if that
                    # file is later removed instead of reading as deleted.
                    self._write(self._accepted_record(resolved))
                elif record["snapshot"] is not None and record["digest"] != resolved.digest:
                    # R-3: a project file that changes is the source again; a fixture session keeps its snapshot
                    # beside the new digest (a native record has none to keep), so the accepted profile still
                    # resolves if that file is later removed. Written only when the file's digest moved.
                    self._write(self._accepted_record(resolved))
            return Status("accepted", resolved, True, notice=notice)
        if state == "accepted":
            snapshot = record["snapshot"]
            if self.fixture and snapshot is not None:
                # R-3: the demo records the accepted snapshot in the fixture state and never writes the target's
                # file; a reopen resolves the accepted profile from that snapshot instead of reading as deleted.
                try:
                    return Status("accepted", from_snapshot(snapshot, self.project), False)
                except Blocked as error:  # the project's rules changed under the snapshot: a file profile's refusal
                    return Status("malformed", None, False, str(error))
            return Status("missing", None, False, "The accepted profile %s was deleted from the project. Restore the file "
                          "(git checkout -- %s) or create it again: zplan profile init."
                          % (PROFILE_FILE, PROFILE_FILE))
        if state == "later":
            try:
                complete(record["snapshot"]["config"])
            except (Blocked, ValueError, KeyError) as error:
                raise corrupt_state(self.directory / STATE_FILE, "profile snapshot") from error
            try:
                return Status("later", from_snapshot(record["snapshot"], self.project), False)
            except Blocked as error:  # the project's rules changed under the snapshot: a file profile's refusal
                return Status("malformed", None, False, str(error))
        proposal = propose(self.project, saved)
        return Status("never", resolve(proposal, saved, self.project, "proposal"), False, proposal=proposal)

    # Owner decisions -----------------------------------------------------------------------------------------

    def accept(self, changes=None):
        """Accept the proposal: write zplan.process.json (never over an existing file) and record it. An existing
        valid file is only recorded. Crash-safe: the intent is recorded first and finished on the next start.

        `changes` (the owner's edits from the profile editor, see `apply_changes`) are set on the document that
        would be written: the proposal, or for a "later" profile the document its snapshot stands for. They are
        refused, before anything is written, for an existing file, which stays as it is.

        In a fixture session (R-3) the project file of the target is never written: the accepted record carries the
        effective snapshot (whether it came from the proposal or from an existing file), so a reopen resolves the
        profile from the fixture state even when that file later appears, changes or goes away — an "accepted"
        record with neither file nor snapshot would read as "missing". An existing file is still only recorded and
        stays byte-identical. A "missing" fixture profile (the file is gone and the record kept no snapshot) is
        re-decided from the proposal, exactly like a production `init`, and recorded in the fixture state only."""
        status = self.status()
        if status.state == "accepted":
            return status
        if status.state == "malformed":
            raise Blocked(status.problem, family="process.invalid")
        if status.present:
            if changes:
                raise Blocked("%s already exists; it stays as it is." % PROFILE_FILE, family="action.refused")
            self._write(self._accepted_record(status.resolved))
            return self.status()
        saved = saved_roles(self.roles_path)
        if self.fixture:
            resolved = status.resolved
            if changes:
                resolved = resolve(validate_profile(apply_changes(self._base_document(status), changes)), saved,
                                   self.project, "proposal")
            elif resolved is None:
                # "missing": the accepted file is gone and the record carries no snapshot to fall back on. Like a
                # production `profile init`, decide again from the proposal — but record it in the fixture state
                # only; the target's file is never written (R-3).
                proposal = status.proposal or propose(self.project, saved)
                resolved = resolve(validate_profile(proposal), saved, self.project)
            self._write(self._accepted_record(resolved))
            return self.status()
        previous = read_record(self.directory)
        previous = (make_record(previous["state"], previous["digest"], previous["snapshot"])
                    if previous is not None and previous["state"] != "accepting" else None)
        proposal = apply_changes(self._base_document(status), changes) if changes else (
            status.proposal or propose(self.project, saved))
        text = json.dumps(proposal, ensure_ascii=False, indent=2) + "\n"
        resolved = resolve(validate_profile(proposal), saved, self.project)
        nested = None
        if previous is not None:
            nested = {"state": previous["state"], "digest": previous["digest"], "snapshot": previous["snapshot"]}
        self._write(make_record("accepting", None, None, nested))
        self._create(text)
        self._write(make_record("accepted", resolved.digest))
        status = self.status()
        problem = self._commit_file()
        return replace(status, notice=problem) if problem else status

    def _base_document(self, status):
        """What an accept with edits starts from: the document a "later" snapshot stands for, else the proposal."""
        if status.state == "later" and status.resolved is not None:
            return document_of(status.resolved.config)
        return status.proposal or propose(self.project, saved_roles(self.roles_path))

    def revise(self, changes):
        """Change an accepted profile with the editor's `changes` (`apply_changes`): the file's own document is
        read, only the changed values are set (other keys and sections stay as they were), the file is replaced
        atomically, committed alone like `_commit_file`, and the new digest is recorded. Nothing is written when
        a value is refused or nothing changes. A fixture session never writes the target's file: it records the
        edited snapshot, and refuses when a file of the target is the source."""
        status = self.status()
        if status.state != "accepted":
            raise Blocked("The profile is not accepted yet: accept it or postpone it.", family="action.refused")
        saved = saved_roles(self.roles_path)
        if self.fixture:
            if status.present:
                raise Blocked("In a --fixture session the project's %s is not changed." % PROFILE_FILE,
                              family="action.refused")
            resolved = resolve(validate_profile(apply_changes(document_of(status.resolved.config), changes)), saved,
                               self.project, "proposal")
            self._write(self._accepted_record(resolved))
            return self.status()
        try:
            document = decode(self.file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, Blocked) as error:
            raise invalid("(file)", "cannot be read", "Fix the file or delete it.") from error
        edited = apply_changes(document, changes)
        if edited == document:
            return status
        resolved = resolve(validate_profile(edited), saved, self.project)
        self._replace(json.dumps(edited, ensure_ascii=False, indent=2) + "\n")
        self._write(make_record("accepted", resolved.digest))
        status = self.status()
        problem = self._commit_file("changed")
        return replace(status, notice=problem) if problem else status

    def _commit_file(self, done="created"):
        """Commit the file this accept (`done` "created") or revision ("changed") just wrote, alone: `git commit --only
        -m "zplan profile" -- zplan.process.json`, other changes (staged or not) untouched. A new file is made known
        by `add -N` first and taken out of the index again when the commit does not land (`user_commit.commit_only`).
        "" when it is done, else the line naming the command to run by hand; the file stays either way."""
        command = 'git add %s && git commit -m "zplan profile" -- %s' % (PROFILE_FILE, PROFILE_FILE)
        try:
            tracked = subprocess.run(["git", "-C", str(self.project), "ls-files", "--error-unmatch", "--", PROFILE_FILE],
                                     capture_output=True, start_new_session=True).returncode == 0
            result = user_commit.commit_only(self.project, [PROFILE_FILE], COMMIT_MESSAGE,
                                             untracked=() if tracked else (PROFILE_FILE,))
            if not result.returncode:
                return ""
        except (OSError, Blocked):
            pass
        return "%s %s, but not committed; run: %s" % (PROFILE_FILE, done, command)

    def _replace(self, text):
        """Replace the project file atomically (same directory, fsync, rename), keeping its permissions."""
        mode = self.file.stat().st_mode & 0o777
        fd, name = tempfile.mkstemp(dir=self.project, prefix=".zplan-process-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, mode)
            os.replace(name, self.file)
        except BaseException:
            try:
                os.unlink(name)
            except OSError:
                pass
            raise

    def _create(self, text):
        """Create the project file atomically and never over an existing one."""
        fd, name = tempfile.mkstemp(dir=self.project, prefix=".zplan-process-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(name, 0o644)
            try:
                os.link(name, self.file)
            except FileExistsError as error:
                raise Blocked("%s already exists; it is not overwritten." % PROFILE_FILE, family="action.refused") from error
        finally:
            try:
                os.unlink(name)
            except OSError:
                pass

    def defer(self):
        """"Later": the effective configuration is stored outside the project and used; the header says so."""
        status = self.status()
        if status.state != "never" or status.present:
            raise Blocked("The profile is already decided or a file was found: accept it.", family="action.refused")
        shown = status.resolved  # the proposal the bootstrap screen shows: rules and checks found, not the bare preset
        self._write(make_record("later", shown.digest, snapshot_of(shown)))
        return self.status()

    # Guards --------------------------------------------------------------------------------------------------

    def guard(self, kind):
        """The shared refusal for a new planning ("plan"), milestone ("milestone") or merge ("merge") action;
        returns the Status whose resolved configuration the action must use. Raises before any side effect."""
        status = self.status()
        if status.state == "never":
            raise Blocked("The project's process profile is not accepted yet: accept or postpone it (run zplan, "
                          "or zplan profile init).", family="process.pending")
        if status.state == "missing":
            raise Blocked(status.problem, family="process.missing")
        if status.state == "malformed":
            raise Blocked(status.problem, family="process.invalid")
        if kind == "plan":
            freeze_rules(self.project, status.resolved.rules)  # rules that cannot reach the agents refuse here
        gates = status.resolved.config["gates"]
        if kind == "milestone" and gates["task"] == "required":
            raise Blocked(UNBUILT["task"], family="process.unbuilt")
        return status

    def freeze_plan(self):
        """The one snapshot a new plan revision runs on, read now: (planning roles, frozen) where frozen is
        {plan_rounds, task_rounds, rules: [{path, sha256, text}], config_digest}. Raises like `guard("plan")`."""
        resolved = self.guard("plan").resolved
        roles = resolved.roles()
        return ({name: roles[name] for name in ("planner", "plan_verifier")},
                {"plan_rounds": resolved.config["limits"]["plan_rounds"],
                 "task_rounds": resolved.config["limits"]["task_rounds"],
                 "rules": freeze_rules(self.project, resolved.rules), "config_digest": resolved.digest})

    def live_digest(self):
        """The digest of the configuration as it is now (the plan gate's invalidation key); "" when the profile is
        not usable, which never equals a gate's digest. A pure read: a refusal writes nothing."""
        try:
            status = self.status(write=False)
        except Blocked:
            return ""
        return status.resolved.digest if status.resolved is not None else ""

    def roles(self):
        """The planning/milestone role preferences of the profile as it is now, None when it is not usable.
        A pure read."""
        try:
            status = self.status(write=False)
        except Blocked:
            return None
        return status.resolved.roles() if status.resolved is not None else None


# Presentation --------------------------------------------------------------------------------------------------

def gate_text(value):
    return "required" if value == "required" else OFF


def check_text(check):
    return "%s: %s (%d s)" % (check["name"], " ".join(check["argv"]), check["timeout_s"])


def source_name(resolved, key):
    """The "[...]" marker of one key: the preset is named by the resolved configuration, so /2's keys read
    "[preset zplan.default/2]" (a value taken from `roles.json` or the file names that instead)."""
    source = resolved.sources[key]
    return "preset " + resolved.config["preset"] if source == "preset" else SOURCE_NAMES[source]


def describe(status, with_sources=True):
    """The resolved profile, line by line (doctor, `zplan profile`, Settings)."""
    head = "Process profile: %s" % STATE_NAMES[status.state]
    if status.state == "accepted" or status.present:
        head += " · file " + PROFILE_FILE
    lines = [head]
    if status.resolved is None:
        lines.append("  " + status.problem)
        return lines
    resolved = status.resolved
    lines[0] += " · digest " + resolved.short
    where = lambda key: ("  [%s]" % source_name(resolved, key)) if with_sources else ""  # noqa: E731
    lines.append("  preset %s%s" % (resolved.config["preset"], where("preset")))
    for role in ROLES:
        b = resolved.config["roles"][role]
        lines.append("  role %-9s %s / %s%s" % (role, b["model"], b["effort"], where("roles." + role)))
    lines.append("  plan check: %s%s" % (gate_text(resolved.config["gates"]["plan"]), where("gates.plan")))
    lines.append("  task check: %s%s (%s)" % (gate_text(resolved.config["gates"]["task"]), where("gates.task"), NEXT_STAGES))
    lines.append("  merge check: %s%s" % (gate_text(resolved.config["gates"]["merge"]), where("gates.merge")))
    limits = resolved.config["limits"]
    lines.append("  rounds: plan %d%s; task retries %d%s; merge %d (%s)" % (
        limits["plan_rounds"], where("limits.plan_rounds"), limits["task_rounds"], where("limits.task_rounds"),
        limits["merge_rounds"], NEXT_STAGES))
    if resolved.config.get("autonomy"):
        a = resolved.config["autonomy"]
        lines.append("  autonomy: %s · up to %d runs · worker round %d min · run %d min · check after round "
                     "%d · wake-ups %d/h · retries %d%s" % (
                         a["level"], a["max_runs"], a["worker_round_minutes"], a["run_minutes"], a["structural_round"],
                         a["wakeups_per_hour"], a["architect_retries"], where("autonomy.level")))
    if resolved.config.get("risk"):
        lines.append("  risk: %d rules · %d triggers%s (%s)" % (
            len(resolved.config["risk"]["rules"]), len(resolved.config["risk"]["triggers"]), where("risk.rules"),
            NEXT_STAGES))
    if resolved.rules:
        lines.append("  rules (apply when planning; tasks and merge: %s): %s"
                     % (NEXT_STAGES, ", ".join(path for path, _ in resolved.rules)))
    else:
        lines.append("  rules (when planning): none")
    if resolved.config["checks"]:
        lines.append("  checks (%s): %s" % (NEXT_STAGES, "; ".join(check_text(c) for c in resolved.config["checks"])))
    else:
        lines.append("  checks: %s" % NO_QUALIFICATION)
    if status.notice:
        lines.append("  " + status.notice)
    return lines


def bootstrap_lines(status):
    """The one first-start screen: the proposed (or found) profile and what each key does."""
    resolved = status.resolved
    if status.present:
        lines = ["Project process profile: found %s - its values are shown." % PROFILE_FILE]
    else:
        lines = ["Project process profile (%s): proposal." % (resolved.config["preset"] if resolved is not None
                                                             else PRESET_V3)]
    rules = [p for p, _ in resolved.rules] if resolved is not None else []
    lines.append("  Rules for agents (apply when planning): %s" % (", ".join(rules) if rules
                                                                             else "none found (AGENTS.md, CLAUDE.md)"))
    checks = resolved.config["checks"] if resolved is not None else []
    if checks:
        lines.append("  Check (qualification, %s): %s" % (NEXT_STAGES, "; ".join(" ".join(c["argv"]) for c in checks)))
    else:
        lines.append("  Check: %s" % NO_QUALIFICATION)
    if resolved is not None:
        gates = resolved.config["gates"]
        lines.append("  Plan check: %s · tasks: %s · merge: %s" % (
            gate_text(gates["plan"]), gate_text(gates["task"]), gate_text(gates["merge"])))
        lines.append("  Roles: " + " · ".join("%s %s/%s" % (n, resolved.config["roles"][n]["model"],
                                                           resolved.config["roles"][n]["effort"]) for n in ROLES[:5]))
        autonomy = resolved.config.get("autonomy")
        if autonomy:
            lines.append("  Autonomy: %s · parallel runs: %d" % (
                LEVEL_NAMES.get(autonomy["level"], autonomy["level"]), autonomy["max_runs"]))
    if status.present:
        lines.append("  Accept - the file stays as it is; the decision is remembered outside the project.")
    else:
        lines.append("  Accept - zplan creates %s in the project root and commits it in one commit '%s', touching nothing else."
                     % (PROFILE_FILE, COMMIT_MESSAGE))
        lines.append("  Later - nothing is written to the project; these values apply, shown in the header: '%s'." % LATER_NOTE)
    return lines


def header_note(status):
    if status.state == "later":
        return LATER_NOTE
    if status.state == "never":
        return "profile not accepted"
    if status.state in ("missing", "malformed"):
        return "profile: error"
    return ""


@dataclass(frozen=True)
class View:
    """The profile as the screens show it: frozen text, no behaviour."""
    state: str
    note: str
    lines: Tuple[str, ...]
    bootstrap: Tuple[str, ...]
    present: bool
    problem: str = ""
    form: Optional[Form] = None  # the editor's start values; None when the profile cannot be edited here


def view(profile):
    """A `View` of the profile now; a refusal to read it is a view too (state malformed, the reason as a line)."""
    try:
        status = profile.status()
    except Blocked as error:
        return View("malformed", "profile: error", (str(error),), (), False, str(error))
    editable = status.resolved is not None and (status.state in ("later", "accepted")
                                                or status.state == "never" and not status.present)
    return View(status.state, header_note(status), tuple(describe(status)),
                tuple(bootstrap_lines(status)) if status.state == "never" else (), status.present, status.problem,
                form_of(status.resolved.config) if editable else None)
