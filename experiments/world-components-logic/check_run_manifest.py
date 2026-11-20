#!/usr/bin/env python3
"""Check D's paused v4 proposal without models, network or execution gates.

This checks document identity, arithmetic and the declared reference paths only.
It cannot approve execution or certify semantic quality / measured latency.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
LEDGER = "artifacts/world-components-logic/run-manifest-ledger-v4.proposal.json"
MANIFEST = "design/world-engine-reports/components-logic/run-manifest.md"
SELECTION = "design/world-engine-reports/components-logic/model-selection.md"
REGISTRY = "artifacts/world-components-logic/l2-model-sources-20261029.json"
REGISTERED_FILES = {
    "experiments/world-components-logic/data/dev-inputs.jsonl",
    "experiments/world-components-logic/data/dev-review-drafts.jsonl",
    "experiments/world-components-logic/data/dev-provenance.json",
    REGISTRY,
    "artifacts/world-components-logic/l3-1-environment.json",
}
MODEL_REPOS = {
    "M01": "hfl/minirbt-h256",
    "M02": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese",
    "M03": "Qwen/Qwen2.5-0.5B-Instruct",
    "M04": "Qwen/Qwen3-0.6B",
}
EVENT_IDS = [f"P-{i:02}" for i in range(1, 17)] + [f"M-{i:02}" for i in range(1, 11)]
BUDGETS = {event: 10 for event in EVENT_IDS if event.startswith("P-")}
BUDGETS.update({"P-14": None, "P-16": None})
BUDGETS.update(dict(zip(EVENT_IDS[16:], [40, 50, 40, 50, 50, 50, 50, 50, 50, 30])))
TOTAL_FIELDS = ("programMacroOccurrences", "modelCalls", "programBudgetMs",
                "modelBudgetMs", "subtotalMs")


def reference_paths():
    """Independent expansion of the six stated K=B=1 reference branches."""
    segment = {"P-01": 1, "P-02": 1, "P-08": 3, "P-10": 2,
               "P-11": 3, "P-12": 1, "P-13": 1,
               "M-01": 3, "M-07": 2, "M-10": 1}
    round_end = {"P-15": 1, "M-08": 1, "M-09": 1}
    chain = {"P-03": 1, "P-04": 2, "P-05": 1, "P-06": 1, "P-07": 1,
             "M-01": 1, "M-02": 1, "M-03": 2, "M-04": 1,
             "M-05": 1, "M-06": 1}
    delta = {"P-04": 1, "P-05": 1, "P-06": 1, "M-03": 1, "M-04": 1}
    ordinary = dict(chain, **round_end)
    ordinary.update({"P-01": 1, "P-02": 1, "P-09": 1, "P-10": 4,
                     "P-11": 1, "P-13": 1, "M-07": 4, "M-10": 1})
    return {"S0-segment": segment, "S0-round": dict(segment, **round_end),
            "S1": chain, "S2-delta": delta, "S3": ordinary,
            "S4": {key: 2 * value for key, value in ordinary.items()}}


REFERENCES = reference_paths()
STAGES = {"S0-segment": ["U3", "U4"], "S0-round": ["U3", "U4"],
          "S1": [], "S2-delta": [], "S3": ["U1", "U2", "U3", "U4"],
          "S4": ["U1", "U2", "U3", "U4"] * 2}
ROUNDS = dict(zip(REFERENCES, [0, 1, 0, 0, 1, 2]))
WAITS = {key: (["W_r[1]", "W_r[2]"] if key == "S4" else
               [] if key in ("S1", "S2-delta") else ["W_r[1]"])
         for key in REFERENCES}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def totals(counts, budgets):
    p_count = sum(n for key, n in counts.items() if key.startswith("P-"))
    m_count = sum(n for key, n in counts.items() if key.startswith("M-"))
    p_ms = sum(n * budgets[key] for key, n in counts.items() if key.startswith("P-"))
    m_ms = sum(n * budgets[key] for key, n in counts.items() if key.startswith("M-"))
    return dict(zip(TOTAL_FIELDS, [p_count, m_count, p_ms, m_ms, p_ms + m_ms]))


def block(text, name):
    match = re.search(r"<!-- BEGIN " + name + r" -->\s*(.*?)\s*<!-- END " + name + r" -->",
                      text, re.S)
    if not match:
        raise ValueError(f"missing Markdown block: {name}")
    return match.group(1)


def table(text):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in text.splitlines() if line.strip().startswith("|")]
    return [row for row in rows if not all(re.fullmatch(r"[-: ]+", cell) for cell in row)]


def read_small(relative):
    # Only these D-owned registered sources may be hashed. Never follow an
    # arbitrary proposal path or inspect model payloads / protected B/C data.
    path = ROOT / relative
    owner = ROOT / ("experiments/world-components-logic" if relative.startswith("experiments/")
                    else "artifacts/world-components-logic")
    if relative not in REGISTERED_FILES or not path.resolve().is_relative_to(owner):
        raise ValueError(f"unregistered or redirected input: {relative}")
    if path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ValueError(f"not a small regular registered input: {relative}")
    return path.read_bytes()


def check(document, markdown, raw, selection):
    errors = []

    def need(condition, message):
        if not condition:
            errors.append(message)

    need(document.get("schema") == "jity-d-run-manifest-v4-proposal", "schema: expected v4 proposal")
    for key in ("executionAuthorized", "modelExecutionPerformed"):
        need(document.get(key) is False, f"execution: {key} must remain false")
    need(document.get("fullRequestTargetMs") == 500, "performance: full target must remain 500 ms")
    admission = document["admission"]
    for key in ("approvedForExecution", "resumeInstructionForModelExecutionGiven"):
        need(admission.get(key) is False, f"execution: admission.{key} must remain false")
    need(admission.get("stages") == ["document-review", "batch-config-and-preconditions",
                                    "authorized-execution", "post-run-judgment"], "admission: four stages changed")
    dynamic = document["dynamicOutcomes"]
    names = {"O", "A", "skip", "S", "R", "X", "G", "stageBatches", "C", "W", "k_source", "b_group"}
    need(set(dynamic["names"]) == names and set(dynamic["values"]) == names,
         "dynamic: all actual branch/call observations must remain declared")
    need(all(value is None for value in dynamic["values"].values()),
         "dynamic: unknown outcomes must remain null, not zero/planned actuals")
    need(dynamic.get("requiresPrecomputedDynamicCounts") is False,
         "dynamic: unknown observations cannot prohibit an authorized diagnostic")
    diagnostic = document["batchTypes"]["inference_diagnostic"]
    need(diagnostic.get("preexistingMeasuredPassRequired") is False and diagnostic.get("mayObserveLatencyFail") is True,
         "diagnostic: first latency evidence may fail; no prior-pass circular gate")
    need(diagnostic.get("formalScreeningAllowed") is False, "diagnostic: cannot waive formal screening gates")
    need(document["batchTypes"]["head_training"].get("trainingGroupsIn90") == 0,
         "training: the 90 evaluation groups cannot become training allocation")
    need(document["batchTypes"]["nonbusiness_smoke"].get("requiresAll90Groups") is False,
         "smoke: nonbusiness diagnostics cannot require the entire formal dataset")

    events = document["events"]
    event_ids = [event["id"] for event in events]
    valid_event_ids = len(event_ids) == 26 and len(set(event_ids)) == 26 and set(event_ids) == set(EVENT_IDS)
    need(valid_event_ids,
         "events: require 26 unique P-01..16 / M-01..10 IDs")
    if not valid_event_ids:
        return errors
    indexed_events = {event["id"]: event for event in events}
    budgets = {event["id"]: event["budgetMs"] for event in events}
    need(budgets == BUDGETS, "events: local proposal budgets changed or unknown waits/probes became zero")
    for event_id, required in {"P-02": ["required identity allocation", "begin_point", "required Python time preview"],
                               "P-09": ["required candidate ID allocation/rewriting", "checkpoint_stage_unit"],
                               "P-12": ["required candidate ID allocation/rewriting", "checkpoint_stage_time_scan"],
                               "P-13": ["checkpoint_seal_point", "commit_point"],
                               "P-15": ["required conclusion/successor identity handling",
                                        "atomic continue/handback confirmation and necessary successor creation",
                                        "all required acknowledgments"]}.items():
        need(set(required) <= set(indexed_events[event_id].get("includes", [])),
             f"events: {event_id} lost required compound operations")
    need(indexed_events["P-12"].get("exclusiveWith") == "P-09-action-unit-path"
         and indexed_events["P-13"].get("mutuallyExclusivePerPoint") is True,
         "events: normal / pure-time submission must be mutually exclusive")
    need({"U3-all-person-task-scan", "U4-new-task-judgment", "required previews", "conditional U5/U6"}
         <= set(indexed_events["P-12"].get("after", [])),
         "events: pure-time staging must follow U3/U4, previews and applicable U5/U6")
    need(indexed_events["P-14"].get("inRequest") is True, "waits: ready waits belong in the full request")
    rpc = document["rpcMapping"]
    need(all(rpc.get(key) is True for key in ("logicalMacroBudgetCoversAllSuboperations",
                                            "sharedRpcDurationCountedOnce", "nestedIntervalsMustNotBeSummed")),
         "timing: compound work / shared RPCs need one non-overlapping timing owner")
    sharing = document["sharingRules"]["M-09"]
    need(set(document["sharingRules"]) == {"M-09", "rule"}, "sharing: unexpected forward-sharing event")
    for source in (sharing, indexed_events["M-09"]):
        need(source.get("dualHeadsShareForward") is True and source.get("sharesForwardWithGeneration") is False,
             "sharing: only the two M01 judgment heads may share; M02 generation is a separate forward")
    need(indexed_events["M-08"]["node"].startswith("M02.")
         and indexed_events["M-09"]["node"].startswith("M01."), "sharing: D07 generation/judgment model identity changed")
    for event_id in ("M-08", "M-09"):
        need(indexed_events[event_id].get("precondition") == "round-and-all-linked-segments-complete",
             f"events: {event_id} must wait for the complete round / linked segments")

    scenarios = document["scenarios"]
    scenario_ids = [scenario["id"] for scenario in scenarios]
    need(scenario_ids == list(REFERENCES), "scenarios: require the six ordered reference branches")
    by_scenario = {scenario["id"]: scenario for scenario in scenarios}
    for scenario in scenarios:
        key, counts = scenario["id"], scenario["counts"]
        valid = all(event in BUDGETS and type(n) is int and n >= 0 and BUDGETS[event] is not None
                    for event, n in counts.items())
        need(valid, f"{key}: counts must be nonnegative integers for budgeted events; waits/probes separate")
        if not valid or key not in REFERENCES:
            continue
        expected = REFERENCES[key]
        need({event: n for event, n in counts.items() if n} == expected,
             f"{key}: required reference event path changed (ordinary U1-U4 / pure-time U3-U4 / round D07)")
        computed = totals(counts, budgets)
        for field, value in computed.items():
            need(scenario.get(field) == value, f"{key}: {field} is {scenario.get(field)!r}, recomputed {value}")
        need(scenario.get("requiredD06Stages") == STAGES[key]
             and scenario.get("d06StageOccurrences") == len(STAGES[key]), f"{key}: required D06 stages incomplete")
        need(counts.get("M-07", 0) == len(STAGES[key]) and counts.get("P-10", 0) == len(STAGES[key]),
             f"{key}: every required reference stage needs a model batch and preview")
        need(scenario.get("completedRounds") == ROUNDS[key]
             and all(counts.get(event, 0) == ROUNDS[key] for event in ("M-08", "M-09", "P-15")),
             f"{key}: completed-round D07 generation, judgment and atomic confirmation missing")
        need(scenario.get("waits") == WAITS[key], f"{key}: keep distinct per-point waits, including both S4 waits")
        need(scenario.get("completeRequestReference") is (key in ("S0-round", "S3", "S4")),
             f"{key}: segment/range prefix is not a complete request")
        scope = ({"totalSegments": 2 if key == "S4" else 1,
                  "totalRounds": 2 if key == "S4" else 1, "omittedPrefix": False}
                 if key in ("S0-round", "S3", "S4") else None)
        actual_scope = scenario.get("requestScope")
        same_scope = (actual_scope is None if scope is None else isinstance(actual_scope, dict)
                      and actual_scope == scope and actual_scope.get("omittedPrefix") is False
                      and all(type(actual_scope.get(field)) is int for field in ("totalSegments", "totalRounds")))
        need(same_scope,
             f"{key}: complete request scope cannot omit prior segments/rounds")
        need(scenario.get("budgetStatus") == ("over_target_planning" if computed["subtotalMs"] > 500
                                             else "unmeasured_not_accepted"), f"{key}: budgets cannot certify measured performance")
    need(by_scenario["S4"]["counts"] == {key: 2 * value for key, value in by_scenario["S3"]["counts"].items()},
         "S4: both rounds must contain the full S3 event shape")

    inputs = document["inputs"]
    registered = [entry for entry in inputs if "path" in entry]
    need(len(registered) == len(REGISTERED_FILES) and {entry["path"] for entry in registered} == REGISTERED_FILES,
         "inputs: registered D input list changed/duplicated")
    for entry in registered:
        try:
            need(digest(read_small(entry["path"])) == entry.get("sha256"), f"input hash: {entry['path']}")
        except (OSError, ValueError) as error:
            errors.append(str(error))
        if entry.get("kind") == "development-drafts":
            need(entry.get("humanReview") == "pending-user" and entry.get("admissibleForRun") is False,
                 "inputs: unreviewed development drafts remain inadmissible")
    groups = next(entry for entry in inputs if entry.get("kind") == "first-round-groups")
    need(groups.get("counts", {}).get("sourceGroupsTotal") == 90
         and groups["counts"].get("taskSourceGroups") == 80 and groups["counts"].get("chainSourceGroups") == 10
         and groups["counts"].get("cases") is None, "inputs: 90 source groups are not an invented case/call count")
    registry = json.loads(read_small(REGISTRY))
    model_revisions = {model["id"]: model["revision"] for model in registry["models"]}
    models = document["models"]
    need(len(models) == 4 and {model["id"] for model in models} == {"M01", "M02", "M03", "M04"}, "models: four unique candidate identities required")
    for model in models:
        need(MODEL_REPOS.get(model["id"]) == model["repo"], f"model registry identity: {model['id']}")
        need(model_revisions.get(model["repo"]) == model["revision"], f"model registry revision: {model['id']}")
        need(model.get("admissibleForBusinessInference") is False, f"models: {model['id']} is not approved for business inference")

    event_rows = table(block(markdown, "EVENT-TABLE"))[1:]
    need([row[0] for row in event_rows] == EVENT_IDS, "Markdown event table: missing/duplicate/reordered ID")
    for row in event_rows:
        if row[0] in indexed_events and len(row) == 4:
            event = indexed_events[row[0]]
            need(row[2] == event["per"], f"Markdown event table: {row[0]} occurrence rule differs")
            need(row[3] == (f"{event['budgetMs']} ms" if event["budgetMs"] is not None else "实测/另计"),
                 f"Markdown event table: {row[0]} budget differs")
        else:
            need(False, "Markdown event table: malformed row")
    for event_id, terms in {"P-09": ["stage_unit"], "P-12": ["stage_time_scan"],
                            "P-13": ["seal_point", "commit_point"]}.items():
        description = next((row[1] for row in event_rows if row[0] == event_id), "")
        need(all(term in description for term in terms), f"Markdown event table: {event_id} compound operation missing")
    budget_rows = table(block(markdown, "BUDGET-SUMMARY"))[1:]
    need([row[0] for row in budget_rows] == list(REFERENCES), "Markdown budget table: six scenarios required")
    for row in budget_rows:
        scenario = by_scenario.get(row[0])
        if scenario:
            wait = " + ".join(scenario["waits"]) or "范围外/无"
            need(row[1:] == [str(scenario[field]) for field in TOTAL_FIELDS] + [wait],
                 f"Markdown budget table: {row[0]} totals/waits differ")
    matrix = table(block(markdown, "SCENARIO-MATRIX"))
    need(matrix[0][1:] == scenario_ids and [row[0] for row in matrix[1:]] == EVENT_IDS,
         "Markdown matrix: six scenario columns / 26 event rows required")
    for row in matrix[1:]:
        expected_cells = []
        for scenario in scenarios:
            expected_cells.append(f"{len(scenario['waits'])} 等待" if row[0] == "P-14" else
                                  "探针另记" if row[0] == "P-16" else str(scenario["counts"].get(row[0], 0)))
        need(row[1:] == expected_cells, f"Markdown matrix: {row[0]} counts differ")
    index = json.loads(re.search(r"```json\s*(.*?)\s*```", block(markdown, "PROPOSAL-INDEX"), re.S).group(1))
    expected_index = {key: document[key] for key in ("schema", "executionAuthorized", "modelExecutionPerformed", "fullRequestTargetMs")}
    expected_index.update({"ledgerFile": LEDGER, "ledgerSha256": digest(raw)})
    need(index == expected_index, "Markdown proposal index: path/hash/authorization/target differs from actual proposal")
    selection_rows = [row for row in table(selection) if row[0].split()[0] in REFERENCES]
    need(len(selection_rows) == 6, "model-selection summary: six current scenarios required")
    for row in selection_rows:
        scenario = by_scenario[row[0].split()[0]]
        need(row[1] == f"{scenario['programMacroOccurrences']} / {scenario['modelCalls']}",
             f"model-selection summary: {scenario['id']} call counts differ")
        need(int(re.match(r"\+?(\d+)", row[2]).group(1)) == scenario["subtotalMs"]
             and re.findall(r"W_r\[\d+\]", row[2]) == scenario["waits"],
             f"model-selection summary: {scenario['id']} subtotal/waits differ")
    return errors


def self_tests(document, markdown, selection):
    """Mutants stay in memory; rebalance arithmetic and refresh index identity."""
    def case(name, mutate, wanted, edit_markdown=None):
        changed = copy.deepcopy(document)
        mutate(changed)
        raw = (json.dumps(changed, ensure_ascii=False, indent=2) + "\n").encode()
        # Keep identity index in sync so semantic errors cannot hide behind it.
        text = re.sub(r'("ledgerSha256": ")[a-f0-9]{64}', r'\g<1>' + digest(raw), markdown)
        if edit_markdown:
            text = edit_markdown(text)
        errors = check(changed, text, raw, selection)
        if not any(wanted in error for error in errors):
            raise ValueError(f"self-test {name}: intended counterexample was not detected ({wanted})")
        print(f"  rejected: {name} [{wanted}]")

    def remove_stages(d):
        for scenario in d["scenarios"]:
            if scenario["id"] in ("S3", "S4"):
                factor = 1 if scenario["id"] == "S3" else 2
                scenario["counts"]["M-07"] = scenario["counts"]["P-10"] = 2 * factor
                scenario["requiredD06Stages"] = ["U3", "U4"] * factor
                scenario["d06StageOccurrences"] = 2 * factor
                scenario.update(totals(scenario["counts"], BUDGETS))

    def remove_round_d07(d):
        scenario = next(s for s in d["scenarios"] if s["id"] == "S0-round")
        for event in ("M-08", "M-09", "P-15"):
            del scenario["counts"][event]
        scenario.update(totals(scenario["counts"], BUDGETS))

    def old_680(d):
        remove_stages(d)
        # v3 listed 14 P events but claimed 13; its 12 model calls cost 550.
        # The same mistaken count was doubled in S4 (1360 rather than 1380).
        for scenario in d["scenarios"]:
            if scenario["id"] in ("S3", "S4"):
                factor = 1 if scenario["id"] == "S3" else 2
                scenario.update(programMacroOccurrences=13 * factor,
                                programBudgetMs=130 * factor, subtotalMs=680 * factor)

    case("old 680 undercount", old_680, "S3: programMacroOccurrences")
    case("omit ordinary stages and rebalance", remove_stages, "S3: required reference event path")
    case("omit S0-round D07 and rebalance", remove_round_d07, "S0-round: completed-round D07")
    case("cross-model shared forward", lambda d: d["sharingRules"]["M-09"].update(sharesForwardWithGeneration=True), "sharing:")
    case("execution authorization true", lambda d: d.update(executionAuthorized=True), "execution:")
    case("model execution true", lambda d: d.update(modelExecutionPerformed=True), "execution:")
    case("unknown dynamic outcome becomes zero", lambda d: d["dynamicOutcomes"]["values"].update(R=0), "dynamic:")
    case("prior measured pass blocks diagnosis", lambda d: d["batchTypes"]["inference_diagnostic"].update(preexistingMeasuredPassRequired=True), "diagnostic:")
    case("wrong registered input hash", lambda d: d["inputs"][0].update(sha256="0" * 64), "input hash:")
    case("wrong model revision", lambda d: d["models"][0].update(revision="0" * 40), "model registry revision:")
    case("wrong document index", lambda d: None, "Markdown proposal index:",
         lambda text: re.sub(r'("ledgerSha256": ")[a-f0-9]{64}', r'\g<1>' + "0" * 64, text))
    case("wrong event table", lambda d: None, "Markdown event table:",
         lambda text: text.replace("| P-01 | 段起始/冻结顺序采纳 | segment | 10 ms |", "| P-01 | 段起始/冻结顺序采纳 | segment | 0 ms |"))
    case("wrong budget table", lambda d: None, "Markdown budget table:",
         lambda text: text.replace("| S3 | 16 | 14 | 160 | 650 | 810 |", "| S3 | 16 | 14 | 160 | 650 | 680 |"))
    case("wrong count matrix", lambda d: None, "Markdown matrix:",
         lambda text: text.replace("| M-07 | 2 | 2 | 0 | 0 | 4 | 8 |", "| M-07 | 2 | 2 | 0 | 0 | 2 | 4 |"))
    case("duplicate event ID", lambda d: d["events"][-1].update(id="M-09"), "26 unique")
    case("S0 segment claims full request", lambda d: d["scenarios"][0].update(completeRequestReference=True), "segment/range prefix")
    case("S0 final segment hides earlier costs", lambda d: d["scenarios"][1]["requestScope"].update(totalSegments=2, omittedPrefix=True), "complete request scope")
    case("S4 reuses the first wait", lambda d: d["scenarios"][5].update(waits=["W_r[1]", "W_r[1]"]), "distinct per-point waits")
    case("relax the 500 ms target", lambda d: d.update(fullRequestTargetMs=1000), "full target must remain 500")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="also reject in-memory regression counterexamples")
    args = parser.parse_args()
    try:
        raw = (ROOT / LEDGER).read_bytes()
        document = json.loads(raw)
        markdown = (ROOT / MANIFEST).read_text(encoding="utf-8")
        selection = (ROOT / SELECTION).read_text(encoding="utf-8")
        errors = check(document, markdown, raw, selection)
        if errors:
            for error in errors:
                print(f"FAIL: {error}", file=sys.stderr)
            return 1
        print("PASS: v4 proposal identity, reference coverage, arithmetic and Markdown agree.")
        for scenario in document["scenarios"]:
            actual = totals(scenario["counts"], BUDGETS)
            waits = " + ".join(scenario["waits"]) or "no in-scope wait"
            print(f"  {scenario['id']}: P{actual['programMacroOccurrences']}/M{actual['modelCalls']}, "
                  f"{actual['programBudgetMs']}+{actual['modelBudgetMs']}={actual['subtotalMs']} ms; {waits}")
        if args.self_test:
            self_tests(document, markdown, selection)
            print("PASS: all in-memory counterexamples rejected.")
        print("Document check only: execution remains paused; no quality/latency approval.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as error:
        print(f"FAIL: malformed/inaccessible proposal: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
