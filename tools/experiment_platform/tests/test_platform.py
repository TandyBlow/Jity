from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path
    _write(root / "artifacts/goal/fam/good.json", '{"runId": "r1", "items": [1, 2]}')
    _write(root / "artifacts/goal/fam/bad.json", '{"broken": ')
    _write(root / "artifacts/goal/fam/dup-a.jsonl", '{"id": 1, "text": "same"}\n')
    _write(root / "artifacts/goal/fam/dup-b.jsonl", '{"id": 1, "text": "same"}\n')
    _write(root / "artifacts/goal/fam/empty.jsonl", "")
    _write(root / "artifacts/goal/fam/train-drift.jsonl", '{"a": 1, "b": 2}\n{"a": 3}\n')
    _write(root / "design/x.md", "refs `artifacts/goal/fam/good.json` and `artifacts/goal/fam/missing.json`.\n")
    return root


def test_index_records_format_and_roles(tmp_path):
    from tools.experiment_platform.data_index import build_index

    repo = _fixture(tmp_path)
    index = build_index(repo, ["artifacts/goal", "design"], with_last_commit=False)
    files = {e["path"]: e for e in index["files"]}
    assert files["artifacts/goal/fam/good.json"]["format"]["runId"] == "r1"
    assert files["artifacts/goal/fam/good.json"]["family"] == "fam"
    assert "parseError" in files["artifacts/goal/fam/bad.json"]["format"]
    assert files["artifacts/goal/fam/dup-a.jsonl"]["format"]["lineCount"] == 1
    assert index["summary"]["fileCount"] == 7


def test_validator_finds_defects(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = _fixture(tmp_path)
    index = build_index(repo, ["artifacts/goal", "design"], with_last_commit=False)
    report = validate(index, repo)
    checks = report["checks"]

    assert [f["path"] for f in checks["malformed"]["findings"]] == ["artifacts/goal/fam/bad.json"]
    assert checks["empty_dataset"]["count"] == 1
    assert checks["duplicate_content"]["count"] == 1
    assert checks["duplicate_content"]["findings"][0]["count"] == 2
    drift = checks["key_drift"]["findings"]
    assert len(drift) == 1 and drift[0]["missingCounts"] == {"b": 1}
    missing = {f["missing"] for f in checks["missing_ref"]["findings"]}
    assert "artifacts/goal/fam/missing.json" in missing
    assert "artifacts/goal/fam/good.json" not in missing
    assert report["failed"] is True


def test_integrity_sidecar_and_manifest(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    base = repo / "artifacts/goal/mw"
    raw = base / "real-semantic.jsonl"
    train = base / "real-semantic-train.jsonl"
    test = base / "real-semantic-test.jsonl"
    _write(raw, '{"id": "a"}\n')
    _write(train, '{"id": "a", "labels": {}}\n')
    _write(test, '{"id": "t"}\n')

    def canon(path: Path) -> str:
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()

    manifest = {"raw": hashlib.sha256(raw.read_bytes()).hexdigest(), "train": canon(train),
                "test": canon(test), "rawRows": 1, "trainRows": 1, "testRows": 1}
    _write(base / "real-semantic-manifest.json", json.dumps(manifest))

    frozen = base / "frozen.json"
    _write(frozen, "{}")
    _write(base / "frozen.json.sha256", hashlib.sha256(b"{}").hexdigest() + "  frozen.json\n")

    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    report = validate(index, repo)
    assert report["checks"]["semantic_manifest"]["count"] == 0
    assert report["checks"]["sidecar_hash"]["count"] == 0

    _write(train, '{"id": "a", "labels": {"x": 1}}\n')
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    report = validate(index, repo)
    assert report["checks"]["semantic_manifest"]["count"] == 1
    assert report["checks"]["semantic_manifest"]["findings"][0]["key"] == "train"


def test_split_check_flags_overlap(tmp_path):
    from tools.experiment_platform.split_sets import check

    repo = tmp_path
    _write(repo / "data/train.jsonl", '{"id": "a"}\n{"id": "b"}\n')
    _write(repo / "data/eval.jsonl", '{"id": "b"}\n{"id": "c"}\n')
    _write(repo / "data/hold.json", '["a", "b", "x"]\n')
    registry = {
        "sets": [
            {"name": "train", "path": "data/train.jsonl", "key": "id"},
            {"name": "eval", "path": "data/eval.jsonl", "key": "id"},
            {"name": "hold", "path": "data/hold.json", "key": "list"},
        ],
        "pairs": [
            {"left": "train", "right": "eval", "expect": "disjoint"},
            {"left": "hold", "right": "train", "expect": "subset"},
            {"left": "hold", "right": "eval", "expect": "report"},
        ],
    }
    report = check(repo, registry)
    assert report["pairs"][0]["overlap"] == 1 and report["pairs"][0]["ok"] is False
    assert report["pairs"][1]["ok"] is False  # x is not in train
    assert report["pairs"][2]["ok"] is True
    assert report["failed"] is True


def test_evidence_refs_flagged(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    _write(repo / "artifacts/goal/fam/e.json", "{}")
    _write(repo / "artifacts/goal/fam/inputs.jsonl",
           '{"id": "x", "evidence": "e.json"}\n{"id": "y", "evidence": "missing.json"}\n')
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    findings = validate(index, repo)["checks"]["evidence_ref"]["findings"]
    statuses = {(f["evidence"], f["status"]) for f in findings}
    assert ("e.json", "untracked") in statuses
    assert ("missing.json", "missing") in statuses


def test_eval_set_validate_freeze_check(tmp_path):
    from tools.experiment_platform.eval_set import main, validate_rows

    rows = [
        {"id": "n1", "modality": "narration", "world": "w", "split": "dev",
         "input": {"facts": "a"}, "expected": {"facts": ["a"]},
         "provenance": {"labelSource": "settled-record"}},
        {"id": "n2", "modality": "narration", "world": "w", "split": "test",
         "input": {"facts": "b"}, "expected": {"facts": ["b"]},
         "forbidden": {"newNames": True}, "provenance": {"labelSource": "settled-record"}},
    ]
    assert validate_rows(rows) == []
    bad = [dict(rows[0]), dict(rows[0])]
    assert any("duplicate id" in f for f in validate_rows(bad))
    assert any("expected.facts" in f for f in validate_rows([{**rows[0], "expected": {}}]))

    path = tmp_path / "set.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    assert main(["freeze", "--path", str(path)]) == 0
    manifest = path.with_suffix(".jsonl.manifest.json")
    assert manifest.exists()
    assert main(["check", "--path", str(path), "--manifest", str(manifest)]) == 0
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(rows[0], ensure_ascii=False) + "\n",
                    encoding="utf-8")
    assert main(["check", "--path", str(path), "--manifest", str(manifest)]) == 1


def test_absolute_path_scan(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    _write(repo / "artifacts/goal/fam/bad_script.py", "from pathlib import Path\nROOT = Path('D:/others/Jity')\n")
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    findings = validate(index, repo)["checks"]["absolute_path"]["findings"]
    assert len(findings) == 1 and findings[0]["count"] == 1


def test_run_experiment_manifest_and_resume(tmp_path):
    from tools.experiment_platform.run_experiment import main

    out = tmp_path / "run1"
    args = ["--name", "smoke", "--command", "python -c \"print('ok')\"",
            "--out-dir", str(out), "--inputs", "package.json"]
    assert main(args) == 0
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "done" and result["attempt"] == 1
    assert manifest["inputs"][0]["sha256"]
    assert "ok" in (out / "attempt1.out.log").read_text(encoding="utf-8")
    assert main(args + ["--resume"]) == 0
    assert json.loads((out / "result.json").read_text(encoding="utf-8"))["attempt"] == 1

    fail_out = tmp_path / "run2"
    fail_args = ["--name", "fail", "--command", "python -c \"raise SystemExit(3)\"",
                 "--out-dir", str(fail_out)]
    assert main(fail_args) == 1
    assert main(fail_args + ["--resume"]) == 1
    assert (fail_out / "result.attempt1.json").exists()
    assert json.loads((fail_out / "result.json").read_text(encoding="utf-8"))["attempt"] == 2


def test_semantic_score_and_verify_run(tmp_path):
    from tools.experiment_platform.semantic_score import score
    from tools.experiment_platform.verify_run import check

    cases = [
        {'id': 'a', 'family': 'item_inspect', 'split': 'test',
         'expected': {'facts': ['信息=规则牌:牌面写明禁射'], 'anyOf': ['牌面写明禁射'], 'status': {'info': 'present'}}},
        {'id': 'b', 'family': 'unknown_entity', 'split': 'test',
         'expected': {'facts': ['信息=储物柜:未登记'], 'anyOf': [], 'status': {'info': 'absent'}}},
    ]
    preds = {'a': {'facts': ['信息=规则牌:牌面写明禁射']}, 'b': {'facts': []}}
    report = score(cases, preds)
    assert report['statusAccuracy'] == 1.0 and report['contentAccuracy'] == 1.0
    assert score(cases, {'a': preds['a']})['missing'] == ['b']

    doc = {'runId': 'r', 'status': 'COMPLETED', 'models': {'requests': 2, 'ok': 2, 'failed': []},
           'turns': [{'product': {'narrationModel': 'qwen3-1.7b', 'microEnabled': True,
                                  'semanticPrompts': [], 'engines': [
                                      {'label': 'narration', 'loadCount': 1, 'generations': 3},
                                      {'label': 'semantic', 'loadCount': 1, 'generations': 2}]}}]}
    ok = check(doc, {'narration': ['qwen3-1.7b']}, ['narration', 'semantic'], 0, True)
    assert ok['pass'] is True and ok['llmSemanticPrompts'] == 0
    bad = check({**doc, 'models': {'failed': ['x']}}, None, ['narration'], 0, False)
    assert bad['pass'] is False
    program = {**doc, 'programNarrationAccepted': True,
               'turns': [{'product': {'narrationModel': 'rules', 'source': 'program',
                                      'microEnabled': True, 'semanticPrompts': [],
                                      'engines': [{'label': 'narration', 'loadCount': 0, 'generations': 0}]}}]}
    assert check(program, None, None, None, False, True)['pass'] is False
    assert check(doc, None, None, None, False, False, 2)['pass'] is False
    assert check(doc, None, None, None, False, False, 1)['pass'] is True


def test_resource_monitor_samples_child(tmp_path):
    import subprocess
    import sys
    import time
    from tools.experiment_platform.resource_monitor import main

    proc = subprocess.Popen([sys.executable, '-c',
                             'import time; x=bytearray(20*1024*1024); time.sleep(4)'])
    try:
        time.sleep(0.3)
        out = tmp_path / 'monitor.csv'
        code = main(['--pid', str(proc.pid), '--duration', '1.2', '--interval', '0.2', '--out', str(out)])
        assert code == 0
        summary = json.loads(out.with_suffix('.summary.json').read_text(encoding='utf-8'))
        assert summary['samples'] >= 3 and summary['peakRssMB'] > 0
    finally:
        proc.terminate()


def test_perf_report_summarize():
    from tools.experiment_platform.perf_report import summarize

    timing = {'sources': [{'file': 'x'}], 'coldStarts': [{'readyMs': 20}, {'readyMs': 30}],
              'points': [{'clocks': {'pointCommittedAtMs': 1, 'narrationStartedAtMs': None,
                                     'firstReadableAtMs': 2, 'pointTextFinishedAtMs': 3},
                          'stages': [{'task': 'updates', 'ms': 10}]}],
              'gates': {'status': 'PASS'}}
    report = summarize(timing, [])
    assert report['coldStart']['medianMs'] == 25
    assert report['topStagesByTotalMs'][0]['task'] == 'updates'
    assert report['nullClocks']['narrationStartedAtMs'] == 1


def test_anonymize_is_deterministic(tmp_path):
    from tools.experiment_platform.anonymize import blind

    rows = [{'id': '1', 'arm': 'a', 'text': 'x'}, {'id': '1', 'arm': 'b', 'text': 'y'},
            {'id': '2', 'arm': 'a', 'text': 'z'}, {'id': '2', 'arm': 'b', 'text': 'w'}]
    first, key = blind(rows, seed=7)
    second, _ = blind(rows, seed=7)
    assert first == second
    assert set(key['1']) == {'A', 'B'}
    for row in first:
        assert set(row['variants']) == {'A', 'B'}
        for label, arm in key[row['id']].items():
            assert row['variants'][label] == next(r['text'] for r in rows
                                                  if r['id'] == row['id'] and r['arm'] == arm)


def test_narration_metrics_sensitivity():
    from tools.experiment_platform.narration_metrics import evaluate

    row = {'factsText': '路明非拿起了护目镜。诺诺没有成功打开门。',
           'settlementText': '诺诺：打开门（没有成功）',
           'resultLines': ['诺诺：打开门（没有成功）']}
    good = '路明非拿起了护目镜。诺诺打开门，却没有成功。'
    bad = '路明非打开了门，却没有成功。'
    good_metrics, bad_metrics = evaluate(row, good), evaluate(row, bad)
    assert good_metrics['coverRate'] > bad_metrics['coverRate']
    assert good_metrics['outHit'] == 1
    assert bad_metrics['outHit'] == 0


def test_task_gold_eval_commit_and_not_triggered():
    from tools.experiment_platform.task_gold_eval import score

    cases = [{'id': 'a', 'taskId': 't', 'verdict': 'yes'},
             {'id': 'b', 'taskId': 't', 'verdict': 'no'},
             {'id': 'c', 'taskId': 't', 'verdict': 'partial'},
             {'id': 'd', 'taskId': 't', 'verdict': 'not_triggered'}]
    preds = {'a': 'yes', 'b': 'yes', 'c': 'partial', 'd': 'not_triggered'}
    report = score(cases, preds)
    assert report['accuracy'] == 0.75
    assert report['yesPrecision'] == 0.5 and report['yesRecall'] == 1.0
    assert report['falseCommits'] == ['b']
    assert report['missing'] == []


def test_soak_report_summarizes_heap_and_turns():
    from tools.experiment_platform.soak_report import summarize

    doc = {'status': 'COMPLETED', 'failures': [], 'turns': [
        {'id': 'a', 'text': 'x' * 10, 'jsHeap': {'usedJSHeapSize': 100 * 1048576},
         'timings': {'waitMs': 1000}, 'product': {'source': 'model', 'acceptedMs': 900, 'narrationModel': 'm'}},
        {'id': 'b', 'text': 'y' * 20, 'jsHeap': {'usedJSHeapSize': 140 * 1048576},
         'timings': {'waitMs': 2000}, 'product': {'source': 'model', 'acceptedMs': 1900, 'narrationModel': 'm'}},
    ]}
    report = summarize(doc, {'file': 'm.csv', 'peakEdgeMB': 100})
    assert report['heapPeakMB'] == 140.0 and report['heapDriftMB'] == 40.0
    assert report['waitMaxMs'] == 2000 and report['turns'] == 2


def test_timing_gates_check_control_return():
    from tools.experiment_platform.timing_gates import evaluate

    timing = {'points': [
        {'id': 'a', 'clocks': {'firstReadableAtMs': 1000, 'narrationStartedAtMs': 1000,
                               'pointTextFinishedMinusCommitMs': 2000, 'driverDoneMs': 5000}},
        {'id': 'b', 'clocks': {'firstReadableAtMs': 70000, 'narrationStartedAtMs': 5000,
                               'pointTextFinishedMinusCommitMs': 400000, 'driverDoneMs': 80000}},
    ]}
    report = evaluate(timing)
    assert report['firstReadable']['pass'] == 1
    assert report['pointText']['pass'] == 1
    assert report['controlReturned']['pass'] == 1
    assert report['firstEqualsNarrationStart'] == 1
    assert report['overallPass'] is False


def test_narration_org_selection_order_and_heads():
    from tools.experiment_platform.narration_org_eval import evaluate

    case = {'id': 'x', 'input': {'factsText': '路明非拿起护目镜。诺诺没有成功开门。',
                                 'resultLines': ['诺诺：开门（没有成功）']},
            'expected': {'mustSelect': ['路明非拿起护目镜', '诺诺没有成功开门'],
                         'outcomes': [{'actor': '诺诺', 'outcome': '没有成功'}],
                         'order': [['路明非拿起护目镜', '诺诺没有成功开门']]}}
    good = evaluate(case, '路明非拿起护目镜。诺诺开门，却没有成功。')
    assert good['selectionRate'] == 1.0 and good['outcomeHit'] == 1
    assert good['orderViolations'] == 0 and good['sameHeadPairs'] == 0
    bad = evaluate(case, '诺诺开门，却没有成功。路明非拿起护目镜。')
    assert bad['orderViolations'] == 1
    repeated = evaluate(case, '路明非拿起护目镜。路明非走进庭院。')
    assert repeated['sameHeadPairs'] == 1
    invented = evaluate(case, '苏茜拿起护目镜。诺诺开门，却没有成功。')
    assert invented['inventedNames'] >= 1


def test_clean_tree_passes(tmp_path):
    from tools.experiment_platform.data_index import build_index
    from tools.experiment_platform.validate_data import validate

    repo = tmp_path
    _write(repo / "artifacts/goal/fam/train.jsonl", '{"id": 1}\n{"id": 2}\n')
    index = build_index(repo, ["artifacts/goal"], with_last_commit=False)
    report = validate(index, repo)
    assert report["summary"]["malformed"]["status"] == "pass"
    assert report["summary"]["duplicate_content"]["status"] == "pass"
    assert report["failed"] is False
