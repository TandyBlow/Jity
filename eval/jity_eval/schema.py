"""Strict, offline JSON contracts for public histories and private answer keys.

The loader never contacts a model.  Public suites and gold answers deliberately
have separate schemas so an adapter need not receive the answer key.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Tuple


class SchemaError(ValueError):
    """An invalid configuration, public suite, or answer key."""


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MODES = {"full", "recent", "state"}


def _fail(where: str, message: str) -> None:
    raise SchemaError(f"{where}: {message}")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SchemaError(f"JSON: duplicate key {key!r}")
        result[key] = value
    return result


def _read(path) -> Dict[str, Any]:
    location = Path(path).expanduser().resolve()
    try:
        with location.open(encoding="utf-8") as stream:
            value = json.load(
                stream, object_pairs_hook=_pairs,
                parse_constant=lambda value: _fail("JSON", f"invalid number {value}"),
            )
    except SchemaError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"{location}: cannot read valid JSON: {exc}") from exc
    if type(value) is not dict:
        _fail(str(location), "expected a JSON object")
    return value


def _object(value, required, optional, where):
    if type(value) is not dict:
        _fail(where, "expected an object")
    missing = set(required) - set(value)
    unknown = set(value) - set(required) - set(optional) - {"description"}
    if missing:
        _fail(where, f"missing fields: {', '.join(sorted(missing))}")
    if unknown:
        _fail(where, f"unknown fields: {', '.join(sorted(unknown))}")
    if "description" in value:
        _string(value["description"], where + ".description", nonempty=False)


def _string(value, where, nonempty=True):
    if type(value) is not str or (nonempty and not value.strip()):
        _fail(where, "expected a non-empty string" if nonempty else "expected a string")
    return value


def _identifier(value, where):
    _string(value, where)
    if not _ID.fullmatch(value):
        _fail(where, "use letters, digits, underscores, hyphens, or dots; no spaces or slashes")
    return value


def _integer(value, where, minimum=None):
    # bool is an int subclass; accepting it silently corrupts turn/attempt IDs.
    if type(value) is not int or (minimum is not None and value < minimum):
        _fail(where, f"expected an integer >= {minimum}" if minimum is not None else "expected an integer")
    return value


def _list(value, where, nonempty=True):
    if type(value) is not list or (nonempty and not value):
        _fail(where, "expected a non-empty array" if nonempty else "expected an array")
    return value


def _version(value, where):
    if type(value) is not int or value != 1:
        _fail(where, "only schema_version 1 is supported")


def _enum(value, choices, where):
    if type(value) is not str or value not in choices:
        _fail(where, f"expected one of: {', '.join(sorted(choices))}")


def load_config(path) -> Dict[str, Any]:
    """Load a run config; suite/gold paths resolve beside the config file."""
    config = _read(path)
    _object(config, {"schema_version", "suite", "gold", "adapter", "modes",
                     "repeats", "seed", "recent_window"}, {"failure_injections"}, "config")
    _version(config["schema_version"], "config.schema_version")
    _enum(config["adapter"], {"offline"}, "config.adapter")
    base = Path(path).expanduser().resolve().parent
    for key in ("suite", "gold"):
        _string(config[key], "config." + key)
        target = Path(config[key]).expanduser()
        config[key] = str((target if target.is_absolute() else base / target).resolve())
    modes = _list(config["modes"], "config.modes")
    for mode in modes:
        _enum(mode, _MODES, "config.modes")
    if len(set(modes)) != len(modes):
        _fail("config.modes", "duplicate mode")
    _integer(config["repeats"], "config.repeats", 1)
    _integer(config["seed"], "config.seed")
    _integer(config["recent_window"], "config.recent_window", 1)
    injections = _list(config.get("failure_injections", []), "config.failure_injections", False)
    seen = set()
    for index, injection in enumerate(injections):
        where = f"config.failure_injections[{index}]"
        _object(injection, {"case_id", "probe_id", "mode", "repeat", "stage", "attempt"}, set(), where)
        _identifier(injection["case_id"], where + ".case_id")
        _identifier(injection["probe_id"], where + ".probe_id")
        _enum(injection["mode"], set(modes), where + ".mode")
        _enum(injection["stage"], {"adapter", "grader"}, where + ".stage")
        _integer(injection["repeat"], where + ".repeat", 1)
        _integer(injection["attempt"], where + ".attempt", 1)
        if injection["repeat"] > config["repeats"]:
            _fail(where + ".repeat", "exceeds config.repeats")
        key = tuple(injection[k] for k in ("case_id", "probe_id", "mode", "repeat", "stage", "attempt"))
        if key in seen:
            _fail(where, "duplicate failure injection")
        seen.add(key)
    return config


def load_suite(path) -> Dict[str, Any]:
    """Validate public event history and independent delayed probes."""
    suite = _read(path)
    _object(suite, {"schema_version", "suite_id", "title", "cases"}, set(), "suite")
    _version(suite["schema_version"], "suite.schema_version")
    _identifier(suite["suite_id"], "suite.suite_id")
    _string(suite["title"], "suite.title")
    cases = _list(suite["cases"], "suite.cases")
    case_ids = set()
    for ci, case in enumerate(cases):
        where = f"suite.cases[{ci}]"
        _object(case, {"id", "title", "history", "probes"}, set(), where)
        _identifier(case["id"], where + ".id")
        if case["id"] in case_ids:
            _fail(where + ".id", "duplicate case ID")
        case_ids.add(case["id"])
        _string(case["title"], where + ".title")
        history = _list(case["history"], where + ".history")
        previous_turn = 0
        turns = set()
        evidence = {}
        for hi, event in enumerate(history):
            event_where = f"{where}.history[{hi}]"
            _object(event, {"turn", "text", "facts"}, set(), event_where)
            turn = _integer(event["turn"], event_where + ".turn", 1)
            if turn != previous_turn + 1:
                _fail(event_where + ".turn", "turns must be strictly increasing and contiguous, starting at 1")
            previous_turn = turn
            turns.add(turn)
            _string(event["text"], event_where + ".text")
            event_ids = set()
            for fi, fact in enumerate(_list(event["facts"], event_where + ".facts", False)):
                fact_where = f"{event_where}.facts[{fi}]"
                _object(fact, {"id", "value", "storage"}, set(), fact_where)
                _identifier(fact["id"], fact_where + ".id")
                _string(fact["value"], fact_where + ".value")
                _enum(fact["storage"], {"narrative", "structured", "both"}, fact_where + ".storage")
                if fact["id"] in event_ids:
                    _fail(fact_where + ".id", "duplicate fact within one turn")
                event_ids.add(fact["id"])
                evidence.setdefault(fact["id"], []).append(turn)
        probe_ids = set()
        for pi, probe in enumerate(_list(case["probes"], where + ".probes")):
            probe_where = f"{where}.probes[{pi}]"
            _object(probe, {"id", "fact_id", "kind", "question", "source_turn", "delay"}, set(), probe_where)
            _identifier(probe["id"], probe_where + ".id")
            _identifier(probe["fact_id"], probe_where + ".fact_id")
            if probe["id"] in probe_ids:
                _fail(probe_where + ".id", "duplicate probe ID")
            probe_ids.add(probe["id"])
            _enum(probe["kind"], {"recall", "action"}, probe_where + ".kind")
            _string(probe["question"], probe_where + ".question")
            source = _integer(probe["source_turn"], probe_where + ".source_turn", 1)
            delay = _integer(probe["delay"], probe_where + ".delay", 1)
            target = source + delay
            if source not in turns:
                _fail(probe_where + ".source_turn", "must refer to a history turn")
            if target > previous_turn:
                _fail(probe_where + ".delay", "probe falls beyond the available history")
            occurrences = [turn for turn in evidence.get(probe["fact_id"], []) if turn <= target]
            if occurrences and occurrences[-1] != source:
                _fail(probe_where + ".source_turn", "must be the last evidence turn before this probe; repeated facts reset the delay")
    return suite


def load_gold(path, suite) -> Dict[str, Dict[str, Any]]:
    """Load private answers indexed by 'case_id/probe_id', verifying truth."""
    document = _read(path)
    _object(document, {"schema_version", "records"}, set(), "gold")
    _version(document["schema_version"], "gold.schema_version")
    expected = {}
    for case in suite["cases"]:
        for probe in case["probes"]:
            value = None
            target = probe["source_turn"] + probe["delay"]
            for event in case["history"]:
                if event["turn"] > target:
                    break
                for fact in event["facts"]:
                    if fact["id"] == probe["fact_id"]:
                        value = fact["value"]
            expected[case["id"] + "/" + probe["id"]] = value
    records = {}
    for index, record in enumerate(_list(document["records"], "gold.records")):
        where = f"gold.records[{index}]"
        _object(record, {"case_id", "probe_id", "expected_value"}, set(), where)
        _identifier(record["case_id"], where + ".case_id")
        _identifier(record["probe_id"], where + ".probe_id")
        if record["expected_value"] is not None:
            _string(record["expected_value"], where + ".expected_value")
        key = record["case_id"] + "/" + record["probe_id"]
        if key in records:
            _fail(where, "duplicate answer record")
        if key not in expected:
            _fail(where, "answer refers to a missing case/probe")
        if record["expected_value"] != expected[key]:
            _fail(where + ".expected_value", "answer disagrees with the last public fact at the probe time")
        records[key] = record
    missing = set(expected) - set(records)
    if missing:
        _fail("gold.records", "missing answers: " + ", ".join(sorted(missing)))
    return records


def validate_bundle(config_path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Validate the complete local bundle before any work is scheduled."""
    config = load_config(config_path)
    suite = load_suite(config["suite"])
    gold = load_gold(config["gold"], suite)
    for index, injection in enumerate(config.get("failure_injections", [])):
        key = injection["case_id"] + "/" + injection["probe_id"]
        if key not in gold:
            _fail(f"config.failure_injections[{index}]", "injection refers to a missing case/probe")
    return config, suite, gold
