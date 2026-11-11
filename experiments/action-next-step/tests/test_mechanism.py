# CPU mechanism tests for the next-action experiment.
#
# These tests never touch the real encoder and never train a real model: they
# build a 32-dim BERT and a character-proxy tokenizer so the masks, the
# variable-length candidate pointer, the frozen seed order and the freeze
# enforcement can be checked in seconds on a laptop. A green run says the
# mechanism is correct, not that the classifier works.
#
# Run: python -m pytest tests -q

from __future__ import annotations

import json
import pathlib
import random
import subprocess
import sys

import pytest
import torch

HERE = pathlib.Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP))

from dataset import (  # noqa: E402
    build_example, check_split_isolation, collate, make_tokenizer_fn, object_nulls,
    read_rows, step_counts,
)
from labels import MAX_STEPS, STEP_CLASSES, load_labels, step_count_of  # noqa: E402
from model import NextStepModel, build_tiny_encoder  # noqa: E402
from serialize import (  # noqa: E402
    candidate_ids, object_index, render_candidate, render_x, serializer_digest,
)
import train as train_module  # noqa: E402
from evaluate import score_rows  # noqa: E402

FIXTURE = HERE / "fixture"


class CharTokenizer:
    def __call__(self, texts, padding=True, truncation=False, return_tensors="pt", max_length=None):
        rows = [[1] + [(ord(ch) % 250) + 2 for ch in str(text)] + [2] for text in texts]
        width = max(len(row) for row in rows) if rows else 1
        input_ids = torch.zeros((len(rows), width), dtype=torch.long)
        mask = torch.zeros((len(rows), width), dtype=torch.long)
        for index, row in enumerate(rows):
            input_ids[index, :len(row)] = torch.tensor(row)
            mask[index, :len(row)] = 1
        return {"input_ids": input_ids, "attention_mask": mask}


def fixture_rows(name="train"):
    return read_rows(FIXTURE / f"{name}.jsonl")


def test_label_index_covers_the_frozen_list():
    labels = load_labels()
    assert len(labels) == 115
    assert len(labels.groups) == 12
    assert labels.action_id("观察") == 0
    assert labels.group_of_label("观察") == 0
    with pytest.raises(ValueError):
        labels.action_id("医护")
    # the digest is a pure function of the frozen file
    assert load_labels().digest() == labels.digest()
    assert labels.summary()["perGroup"]["身体"] == 5


def test_skip_is_an_empty_step_list_and_three_steps_are_refused():
    assert step_count_of([]) == 0
    assert step_count_of([{"action": "观察"}]) == 1
    assert step_count_of([{"action": "观察"}, {"action": "移动"}]) == 2
    with pytest.raises(ValueError):
        step_count_of([{"action": "观察"}] * 3)


def test_serializer_is_deterministic_and_prints_ids_with_names():
    row = fixture_rows()[5]
    text = render_x(row)
    assert text == render_x(row)
    for slot in ("角色：", "目标：", "地点：", "在场：", "物品：", "刚才：", "精神：", "个性：", "候选："):
        assert slot in text
    # every candidate id and name is visible, so a pointer can resolve
    for candidate in row["x"]["candidates"]:
        assert candidate["id"] in text
        assert candidate["name"] in text
    assert "nono=诺诺" in text
    assert "cage_lock=笼门挂锁" in text
    assert serializer_digest() == serializer_digest()


def test_empty_slots_are_explicit_not_omitted():
    row = fixture_rows("validation")[3]
    text = render_x(row)
    assert "在场：（无）" in text
    assert "候选：（无）" in text


def test_object_pointer_is_null_or_a_candidate_position():
    row = fixture_rows()[5]
    assert object_index(row, {"object": None}) == 0
    assert object_index(row, {}) == 0
    assert object_index(row, {"object": "cage_lock"}) == 3
    with pytest.raises(ValueError) as error:
        object_index(row, {"object": "hall_not_listed"})
    assert "not among the row's candidates" in str(error.value)
    assert candidate_ids(row) == ["nono", "fingel", "cage_lock", "west_arcade"]


def test_masks_follow_the_step_count():
    labels = load_labels()
    rows = fixture_rows()
    batch = collate([build_example(row, labels) for row in rows], make_tokenizer_fn(CharTokenizer()), 512)
    actions = batch["actions"].tolist()
    objects = batch["objects"].tolist()
    steps = batch["step"].tolist()
    for index, step in enumerate(steps):
        for slot in range(MAX_STEPS):
            if slot < step:
                assert actions[index][slot] >= 0
                assert objects[index][slot] >= 0
            else:
                # a skip row and a one-step row carry no target in slot 2
                assert actions[index][slot] == -100
                assert objects[index][slot] == -100


def test_reads_the_real_lane13_row_shape():
    """The delivered row is produced by 13's project_x, not by this repo's
    fixture builder. This row is that projection of the committed snapshot
    3f65452daf352c63 for caesar; only its `y` is a fixture target (marked
    labelSource=fixture), so the pointer can be exercised on the real slots."""
    rows = read_rows(FIXTURE / "row13-shape.jsonl")
    assert len(rows) == 1
    row = rows[0]
    labels = load_labels()
    example = build_example(row, labels)
    assert example.row_id == "shape13-caesar-probe"
    assert example.step == 2
    # goals are 'id：text' strings, not objects, and every one is printed
    assert len(row["x"]["goals"]) == 5 and all("：" in goal for goal in row["x"]["goals"])
    assert all(goal in example.text for goal in row["x"]["goals"])
    # the character's carried items are visible, so a held item is not confused
    # with one lying in a container
    assert "（持有：" in example.text
    for held in row["x"]["character"]["holds"]:
        assert held["id"] in example.text
    # candidate objects keep their container, and the pointer resolves through
    # the real 13 candidate objects (dicts with id/name/type/place)
    assert "radio_battery1=" in example.text and "/第一格" in example.text
    assert example.objects == [2, 5]
    ids = candidate_ids(row)
    assert ids[example.objects[0] - 1] == "radio_battery1"
    assert ids[example.objects[1] - 1] == "radio_caesar"
    # and the fixture row survives a real batch collation
    batch = collate([example], make_tokenizer_fn(CharTokenizer()), 1024)
    assert batch["step"].tolist() == [2]
    assert batch["actions"].tolist()[0] == [labels.action_id("核实"), labels.action_id("操作")]


def test_split_isolation_refuses_a_goal_on_both_sides():
    rows = fixture_rows() + fixture_rows("validation")
    check_split_isolation(rows)  # fixture goals repeat inside a split only
    crossed = [{"rowId": "a", "split": "train", "goalId": "g1"}, {"rowId": "b", "split": "validation", "goalId": "g1"}]
    with pytest.raises(ValueError) as error:
        check_split_isolation(crossed)
    assert "appears in both" in str(error.value)


def test_model_emits_steps_actions_and_a_variable_pointer():
    labels = load_labels()
    rows = fixture_rows()
    examples = [build_example(row, labels) for row in rows]
    batch = collate(examples, make_tokenizer_fn(CharTokenizer()), 512)
    encoder, hidden = build_tiny_encoder()
    model = NextStepModel(encoder, hidden=hidden, n_fine=115, freeze_encoder=True)
    outputs = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                    cand_ids=batch["cand_ids"], cand_mask=batch["cand_mask"])
    size = len(examples)
    width = batch["cand_ids"].shape[1]
    assert outputs["step_logits"].shape == (size, STEP_CLASSES)
    assert outputs["action_logits"].shape == (size, MAX_STEPS, 115)
    assert outputs["object_logits"].shape == (size, MAX_STEPS, width + 1)
    # a padded candidate column can never win the pointer
    padded = batch["cand_mask"].sum(-1) == 0
    for row_index in range(size):
        for slot in range(MAX_STEPS):
            for column in range(width):
                if padded[row_index][column]:
                    assert float(outputs["object_logits"][row_index, slot, column + 1]) < -1e30


def test_skip_rows_train_the_step_head_only():
    labels = load_labels()
    skip_rows = [row for row in fixture_rows() if not ((row.get("y") or {}).get("steps"))]
    assert len(skip_rows) >= 1
    batch = collate([build_example(row, labels) for row in skip_rows], make_tokenizer_fn(CharTokenizer()), 512)
    encoder, hidden = build_tiny_encoder()
    model = NextStepModel(encoder, hidden=hidden, n_fine=115, freeze_encoder=True)
    outputs = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                    cand_ids=batch["cand_ids"], cand_mask=batch["cand_mask"])
    step_weights = torch.tensor([0.3, 1.0, 1.0])
    fine_weights = torch.ones(115)
    loss, parts = train_module.masked_losses(outputs, batch, step_weights, fine_weights)
    assert parts["action_1"] is None and parts["object_1"] is None
    assert parts["action_2"] is None and parts["object_2"] is None
    only_step = torch.nn.functional.cross_entropy(outputs["step_logits"], batch["step"], weight=step_weights)
    assert abs(float(loss) - float(only_step)) < 1e-6


def test_two_step_rows_train_both_slots_and_one_step_rows_only_slot_one():
    labels = load_labels()
    rows = fixture_rows()
    two = next(row for row in rows if len((row.get("y") or {}).get("steps") or []) == 2)
    one = next(row for row in rows if len((row.get("y") or {}).get("steps") or []) == 1)
    encoder, hidden = build_tiny_encoder()
    model = NextStepModel(encoder, hidden=hidden, n_fine=115, freeze_encoder=True)
    fine = torch.ones(115)
    step = torch.tensor([0.3, 1.0, 1.0])
    for row, expect_two in ((two, True), (one, False)):
        batch = collate([build_example(row, labels)], make_tokenizer_fn(CharTokenizer()), 512)
        outputs = model(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"],
                        cand_ids=batch["cand_ids"], cand_mask=batch["cand_mask"])
        _, parts = train_module.masked_losses(outputs, batch, step, fine)
        assert parts["action_1"] is not None
        assert (parts["action_2"] is not None) is expect_two


def test_seed_is_applied_before_the_head_is_created():
    def build(seed):
        random.seed(seed)
        torch.manual_seed(seed)
        encoder, hidden = build_tiny_encoder()
        model = NextStepModel(encoder, hidden=hidden, n_fine=115, freeze_encoder=True)
        return [parameter.detach().clone() for parameter in model.parameters() if parameter.requires_grad]

    first = build(20261111)
    second = build(20261111)
    assert len(first) and len(first) == len(second)
    for left, right in zip(first, second):
        assert torch.equal(left, right)
    other = build(7)
    assert not all(torch.equal(left, right) for left, right in zip(first, other))


def test_freeze_verifies_the_current_tree_and_detects_drift(tmp_path):
    frozen = train_module.verify_freeze()
    assert frozen["freezeId"] == train_module.freeze_id(frozen)
    assert frozen["labels"]["fine"] == 115
    # a modified copy of a registered source is drift
    copied = json.loads(train_module.FREEZE.read_text(encoding="utf-8"))
    copied["sources"]["serialize.py"] = "0" * 64
    copied["freezeId"] = train_module.freeze_id(copied)
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(copied, ensure_ascii=False), encoding="utf-8")
    original = train_module.FREEZE
    train_module.FREEZE = path
    try:
        with pytest.raises(SystemExit) as error:
            train_module.verify_freeze()
        assert "registered source changed" in str(error.value)
    finally:
        train_module.FREEZE = original


def test_fine_weights_are_clipped_and_absent_classes_stay_zero():
    step_weights, fine_weights = train_module.class_weights([0, 1, 1, 2, 2, 2], [0, 0, 1, 1, 1, 2, 2, 2], 
                                                            {"loss": {"stepWeights": [0.3, 1.0, 1.0]}})
    assert [round(float(value), 6) for value in step_weights] == [0.3, 1.0, 1.0]
    # counts are [2, 3, 3] -> median 3 -> class 0 clipped to the 1.5 ceiling
    assert float(fine_weights[0]) == 1.5
    assert float(fine_weights[1]) == 1.0
    assert float(fine_weights[2]) == 1.0
    assert float(fine_weights[3]) == 0.0  # absent from train


def test_scorer_counts_skip_separately_and_refuses_a_free_pass():
    labels = load_labels()
    rows = fixture_rows()
    predictions = []
    for row in rows:
        steps = (row.get("y") or {}).get("steps") or []
        predictions.append({
            "step": len(steps),
            "actions": [step["action"] for step in steps],
            "objects": [step.get("object") for step in steps],
        })
    scored = score_rows(rows, predictions, labels)
    assert scored["skipRows"] == 1 and scored["nonSkipRows"] == 5
    assert scored["skipRecall"] == 1.0
    assert scored["primaryGroupHit"] == 1.0
    assert scored["fullHit"] == 1.0
    assert scored["wrongActionRate"] == 0.0
    wrong = [{"step": 0, "actions": [], "objects": []}] * len(rows)
    scored_wrong = score_rows(rows, wrong, labels)
    assert scored_wrong["wrongActionRate"] == 1.0
    # skip-everything still "hits" the one real skip row and nothing else: this
    # is why skip recall and non-skip accuracy are reported apart
    assert scored_wrong["fullHit"] == round(1 / 6, 4)


def test_fixture_run_end_to_end_on_cpu(tmp_path):
    """The whole pipeline on 6+4 fixture rows and a 32-dim encoder. The report is
    labelled `mechanism`; it is not a training result."""
    token_lengths = tmp_path / "token-lengths.json"
    # the fixture is short; the stub measurement is what train.py requires
    subprocess.run(
        [sys.executable, str(EXP / "measure_tokens.py"), "--stub-tokenizer",
         "--rows", str(FIXTURE / "train.jsonl"), str(FIXTURE / "validation.jsonl"),
         "--out", str(token_lengths)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    out = tmp_path / "run"
    result = subprocess.run(
        [sys.executable, str(EXP / "train.py"), "--base", str(tmp_path),
         "--train", str(FIXTURE / "train.jsonl"), "--validation", str(FIXTURE / "validation.jsonl"),
         "--token-lengths", str(token_lengths), "--out", str(out), "--dry-run-tiny", "--epochs", "2"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["kind"] == "mechanism"
    assert report["seedAppliedBeforeInit"] is True
    assert report["data"]["train"] == 6 and report["data"]["validation"] == 4
    assert report["maxLen"] % 32 == 0
    assert len(report["history"]) >= 1
    assert (out / "head.pt").exists()
    assert report["headSha256"]
    assert report["data"]["trainStepCounts"] == step_counts(fixture_rows())
    assert report["data"]["trainObjects"] == object_nulls(fixture_rows())
    # a second identical run reproduces the same best-epoch metric
    out2 = tmp_path / "run2"
    again = subprocess.run(
        [sys.executable, str(EXP / "train.py"), "--base", str(tmp_path),
         "--train", str(FIXTURE / "train.jsonl"), "--validation", str(FIXTURE / "validation.jsonl"),
         "--token-lengths", str(token_lengths), "--out", str(out2), "--dry-run-tiny", "--epochs", "2"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert again.returncode == 0, again.stdout + again.stderr
    report2 = json.loads((out2 / "report.json").read_text(encoding="utf-8"))
    assert [entry["validation"]["loss"] for entry in report2["history"]] == \
        [entry["validation"]["loss"] for entry in report["history"]]


def test_train_refuses_a_test_row_and_a_bad_max_len(tmp_path):
    fixture = FIXTURE / "train.jsonl"
    token_lengths = tmp_path / "token-lengths.json"
    token_lengths.write_text(json.dumps({"measured": True, "maxLen": 100, "truncatedRows": 0}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(EXP / "train.py"), "--base", str(tmp_path), "--train", str(fixture),
         "--validation", str(FIXTURE / "validation.jsonl"), "--token-lengths", str(token_lengths),
         "--out", str(tmp_path / "run"), "--dry-run-tiny", "--epochs", "1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode != 0
    assert "maxLen" in result.stdout + result.stderr
    token_lengths.write_text(json.dumps({"measured": True, "maxLen": 96, "truncatedRows": 3}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(EXP / "train.py"), "--base", str(tmp_path), "--train", str(fixture),
         "--validation", str(FIXTURE / "validation.jsonl"), "--token-lengths", str(token_lengths),
         "--out", str(tmp_path / "run"), "--dry-run-tiny", "--epochs", "1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode != 0
    assert "truncation" in (result.stdout + result.stderr)


def test_rows_without_a_split_field_take_the_file_role(tmp_path):
    """Lane 13's delivered rows carry no `split` (the file is the role). The
    corpus above is copied without the field to prove the trainer still refuses
    a misplaced row and accepts an honest one."""
    import copy as _copy

    train = fixture_rows()
    validation = fixture_rows("validation")
    for row in train + validation:
        row.pop("split", None)
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    train_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in train) + "\n", encoding="utf-8")
    validation_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in validation) + "\n", encoding="utf-8")
    token_lengths = tmp_path / "token-lengths.json"
    subprocess.run(
        [sys.executable, str(EXP / "measure_tokens.py"), "--stub-tokenizer",
         "--rows", str(train_path), str(validation_path), "--out", str(token_lengths)],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    ok = subprocess.run(
        [sys.executable, str(EXP / "train.py"), "--base", str(tmp_path), "--train", str(train_path),
         "--validation", str(validation_path), "--token-lengths", str(token_lengths),
         "--out", str(tmp_path / "run"), "--dry-run-tiny", "--epochs", "1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    report = json.loads((tmp_path / "run" / "report.json").read_text(encoding="utf-8"))
    assert report["data"]["train"] == 6 and report["data"]["validation"] == 4
    # a validation row inside the train file is still refused
    misplaced = _copy.deepcopy(train)
    misplaced[0]["split"] = "validation"
    train_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in misplaced) + "\n", encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(EXP / "train.py"), "--base", str(tmp_path), "--train", str(train_path),
         "--validation", str(validation_path), "--token-lengths", str(token_lengths),
         "--out", str(tmp_path / "run2"), "--dry-run-tiny", "--epochs", "1"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert bad.returncode != 0 and "declares split" in (bad.stdout + bad.stderr)
