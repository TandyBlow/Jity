"""Mechanism tests for the short pair serializer and the pairwise model.

No training, no network. The real 300-row file is used read-only when present;
the tests skip the parts that need it otherwise.

    python -m pytest tests/test_pairwise.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import pairwise_serialize as ps  # noqa: E402

ROWS = Path("D:/others/Jity/.local/parallel-local-game/worktrees/13-action-dataset/"
            "experiments/action-dataset-v1/rows/train13-full-candidates.jsonl")
LABELS = Path("D:/others/Jity/.local/parallel-local-game/results/"
              "action-dataset-20261111/labels-v1.json")
SNAPSHOT = Path("D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot")

needs_rows = pytest.mark.skipif(not ROWS.exists(), reason="real 300-row file not present")
needs_labels = pytest.mark.skipif(not LABELS.exists(), reason="frozen labels file not present")


def toy_row(goals, *, present=None, items=None, recent=None, holds=None, group="感知",
            steps=None, skip=False):
    row = {
        "rowId": "toy-1",
        "characterId": "lu",
        "yGroup": "skip" if skip else group,
        "y": {"steps": [] if skip else (steps or [{"action": "查看", "object": "map"}])},
        "skipReason": "waiting" if skip else None,
        "yRationale": "RATIONALE-SHOULD-NOT-APPEAR",
        "labelSource": "tester",
        "x": {
            "character": {"id": "lu", "name": "路明非", "place": "服务巷/检修口",
                          "appearance": ["APPEARANCE-SHOULD-NOT-APPEAR"],
                          "holds": [{"id": "g", "name": "护目镜"}] if holds is None else holds},
            "goals": goals,
            "place": "服务巷（地点） < 庭院 < 学院 时间=2009-10-17T15:20:00",
            "present": [{"id": "nono", "name": "诺诺"}][:len(present or [1])] if present is None else present,
            "items": [{"id": "map", "name": "庭院路线图"}, {"id": "rules", "name": "演习规则牌"}]
                     if items is None else items,
            "recent": [] if recent is None else recent,
            "sanity": 58,
            "personality": "PERSONALITY-SHOULD-NOT-APPEAR",
            "candidates": [{"id": "map", "name": "庭院路线图", "type": "物品", "place": "服务巷"},
                           {"id": "lu", "name": "路明非", "type": "人物", "place": "服务巷"}],
        },
    }
    return row


def test_short_context_matches_the_agreed_format():
    goal = "把胸前的护目镜戴好并确认镜片没有裂纹，并记录结果"
    row = toy_row([f"task_lu_goggles：{goal}"])
    context, omitted = ps.short_context(row)
    text = ps.render_pair(context, "物品")
    lines = text.split("\n")
    assert lines[0].startswith("任务：")
    assert lines[1].startswith("所见：服务巷/检修口；在场：诺诺；物品：庭院路线图，演习规则牌")
    assert lines[2].startswith("刚见：（无）")
    assert lines[3] == "动作：物品"
    # 18-char goal clip, task id stripped
    assert lines[0] == f"任务：{goal[:18]}"
    assert len(goal[:18]) == ps.GOAL_CHARS
    assert omitted["goalsClipped"] == 1


def test_dropped_sections_never_reach_the_text():
    row = toy_row(["task_lu_goggles：把胸前的护目镜戴好并确认镜片没有裂纹"])
    text = ps.render_pair(ps.short_context(row)[0], "感知")
    for banned in ("APPEARANCE", "PERSONALITY", "任务id", "task_lu_goggles", "RATIONALE", "sanity",
                   "58", "演习规则牌，庭院路线图"):
        assert banned not in text
    assert ps.leak_check(row, [text]) == []


def test_all_goals_are_kept_including_six():
    goals = [f"task_t{i}：目标编号{i}的内容描述文本很长需要截断" for i in range(1, 7)]
    row = toy_row(goals)
    context, omitted = ps.short_context(row)
    assert omitted["goalsTotal"] == 6
    assert context["tasks"].count("|") == 5


def test_thirteen_pairs_one_positive_and_skip_is_the_thirteenth():
    row = toy_row(["task_lu_goggles：把胸前的护目镜戴好并确认镜片没有裂纹"])
    pairs = ps.pairs_for_row(row)
    assert len(pairs) == 13
    assert [pair["group"] for pair in pairs] == ps.ALL_GROUPS
    positives = [pair["group"] for pair in pairs if pair["label"] == 1]
    assert positives == ["感知"]

    skip_row = toy_row(["task_lu_goggles：把胸前的护目镜戴好并确认镜片没有裂纹"], skip=True)
    skip_pairs = ps.pairs_for_row(skip_row)
    assert [pair["group"] for pair in skip_pairs if pair["label"] == 1] == [ps.SKIP_GROUP]
    assert skip_pairs[ps.SKIP_INDEX]["label"] == 1


def test_second_step_uses_the_coarse_group_of_the_first_step():
    row = toy_row(
        ["task_a：把盒子打开", "task_b：检查盒盖"],
        group="言语",
        steps=[{"action": "提问", "object": "lu"}, {"action": "告知", "object": "lu"}],
    )
    groups = {predicate: "言语" for predicate in ("提问",)}
    groups["告知"] = "言语"
    pairs = ps.pairs_for_step(row, 1, predicate_to_group=groups)
    text = pairs[0]["text"]
    assert "已做：言语（lu）" in text
    assert [pair["group"] for pair in pairs if pair["label"] == 1] == ["言语"]
    # the fine predicate is not a candidate group
    assert "提问" not in text


def test_second_step_without_a_predicate_map_is_refused():
    row = toy_row(["task_a：把盒子打开"], steps=[{"action": "提问", "object": "lu"},
                                                 {"action": "告知", "object": "lu"}])
    with pytest.raises(ValueError):
        ps.pairs_for_step(row, 1)


def test_present_and_items_are_capped_and_the_rest_is_recorded():
    row = toy_row(
        ["task_a：把盒子打开"],
        present=[{"id": f"p{i}", "name": f"人物{i}"} for i in range(1, 6)],
        items=[{"id": f"i{i}", "name": f"物品{i}"} for i in range(1, 6)],
    )
    context, omitted = ps.short_context(row)
    assert context["present"] == ["人物1", "人物2", "人物3"]
    assert context["items"] == ["物品1", "物品2", "物品3"]
    assert omitted["presentOmitted"] == ["人物4", "人物5"]
    assert omitted["itemsOmitted"] == ["物品4", "物品5"]


def test_recent_uses_the_latest_event_and_records_the_clip():
    long_event = "路明非走到服务巷检修口，蹲下看盖板，确认螺丝有没有松动，然后退开"
    row = toy_row(["task_a：把盒子打开"], recent=["早先的事", long_event])
    context, omitted = ps.short_context(row)
    assert context["recent"] == long_event[:30]
    assert omitted["recentTotal"] == 2
    assert omitted["recentClipped"] is True


def test_candidate_table_is_metadata_and_object_index_comes_from_the_answer():
    row = toy_row(["task_a：把盒子打开"])
    pairs = ps.pairs_for_row(row)
    assert pairs[0]["candidates"][0]["id"] == "map"
    assert pairs[0]["objectIndex"] == 1  # the y step names "map", first candidate
    row["y"] = {"steps": [{"action": "查看", "object": None}]}
    pairs = ps.pairs_for_row(row)
    assert pairs[0]["objectIndex"] is None
    # The candidate table is metadata: the same item name may appear because it is
    # a visible item, not because the candidate list was printed (the table has an
    # entry the text never names: the row's own character).
    assert "路明非" in [candidate["name"] for candidate in pairs[0]["candidates"]]
    assert "路明非，" not in pairs[0]["text"]


@needs_rows
@needs_labels
def test_real_file_renders_4290_pairs_with_330_positives():
    groups = ps.load_predicate_groups(LABELS)
    rows = ps.load_rows(ROWS)
    pairs = ps.pairs_for_rows(rows, groups)
    assert len(pairs) == 4290
    assert sum(pair["label"] for pair in pairs) == 330
    assert sum(1 for pair in pairs if pair["stepIndex"] == 1) == 390
    assert sum(1 for pair in pairs if pair["stepIndex"] == 1 and pair["label"]) == 30
    # every pair has exactly one positive per decision
    by_decision = {}
    for pair in pairs:
        by_decision.setdefault((pair["rowId"], pair["stepIndex"]), []).append(pair["label"])
    assert all(sum(labels) == 1 and len(labels) == 13 for labels in by_decision.values())


@needs_rows
@needs_labels
def test_real_rows_with_six_goals_keep_all_six():
    rows = ps.load_rows(ROWS)
    six = [row for row in rows if len(row["x"].get("goals") or []) == 6]
    assert len(six) == 35
    for row in six:
        context, _ = ps.short_context(row)
        assert context["tasks"].count("|") == 5


@needs_rows
@needs_labels
def test_no_pair_text_leaks_a_label_or_rationale():
    groups = ps.load_predicate_groups(LABELS)
    rows = ps.load_rows(ROWS)
    for row in rows[:60]:
        texts = [pair["text"] for pair in ps.pairs_for_row(row, groups)]
        assert ps.leak_check(row, texts) == []


def test_serializer_digest_is_stable_and_changes_with_the_format():
    first = ps.serializer_digest()
    assert first == ps.serializer_digest()
    original = ps.GOAL_CHARS
    try:
        ps.GOAL_CHARS = original + 1
        assert ps.serializer_digest() != first
    finally:
        ps.GOAL_CHARS = original


def test_metrics_and_loss_normalisation():
    import torch

    import pairwise_model as pm

    decisions = [
        {"stepIndex": 0, "gold": "感知", "pred": "感知"},
        {"stepIndex": 0, "gold": "物品", "pred": "感知"},
        {"stepIndex": 0, "gold": "不动", "pred": "不动"},
        {"stepIndex": 1, "gold": "言语", "pred": "言语"},
    ]
    result = pm.metrics(decisions)
    assert result["rowHit"] == 0.75
    assert result["skipPrecision"] == 1.0
    assert result["skipRecall"] == 1.0
    assert result["stepDecisions"] == {0: 3, 1: 1}

    # one decision of 13 pairs: 1 positive with pos_weight 12, rest negative
    logits = torch.zeros(13)
    labels = torch.zeros(13)
    labels[4] = 1.0
    loss = pm.decision_loss(logits, labels, 13)
    manual = (12.0 * torch.log(torch.tensor(2.0)) + 12 * torch.log(torch.tensor(2.0))) / 13
    assert torch.allclose(loss, manual, atol=1e-6)


def test_predict_decision_reports_margin_and_runner_up():
    from pairwise_model import predict_decision

    prediction = predict_decision([0.1, 0.2, 0.9])
    assert prediction["top1"] == ps.ALL_GROUPS[2]
    assert prediction["top2"] == ps.ALL_GROUPS[1]
    assert abs(prediction["margin"] - 0.7) < 1e-9


def test_pooling_ignores_padding():
    import torch

    import pairwise_model as pm

    class Encoder(torch.nn.Module):
        def forward(self, input_ids, attention_mask=None):
            values = input_ids.to(torch.float32).unsqueeze(-1).repeat(1, 1, 2)
            values = torch.cat([values, data_probe(input_ids)], dim=-1)
            return type("Out", (), {"last_hidden_state": values})()

    def data_probe(input_ids):
        # mark padding rows with a huge value that must not reach the mean
        return torch.where(input_ids == 0, torch.full_like(input_ids, 1e6, dtype=torch.float32),
                           torch.zeros_like(input_ids, dtype=torch.float32)).unsqueeze(-1)

    model = pm.PairwiseModel.__new__(pm.PairwiseModel)
    torch.nn.Module.__init__(model)
    model.encoder = Encoder()
    model.dropout = torch.nn.Identity()
    cfg = type("Cfg", (), {"hidden_size": 3})()
    model.encoder.config = cfg
    model.head = torch.nn.Linear(3, 1, bias=False)
    with torch.no_grad():
        model.head.weight.zero_()
    ids = torch.tensor([[5, 7, 0, 0]])
    mask = torch.tensor([[1, 1, 0, 0]])
    moved = pm.PairwiseModel.forward(model, ids, mask)
    short = pm.PairwiseModel.forward(model, torch.tensor([[5, 7]]), torch.tensor([[1, 1]]))
    assert torch.allclose(moved, short)


class _FakeTokenizer:
    pad_token_id = 0

    def __call__(self, text, add_special_tokens=True):
        return {"input_ids": [1] + [2 + (ord(char) % 500) for char in text[:40]] + [2]}


def _stub_model(dim=6):
    import torch

    import pairwise_model as pm

    class Encoder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.config = type("Cfg", (), {"hidden_size": dim})()

        def forward(self, input_ids, attention_mask=None):
            values = torch.nn.functional.one_hot(input_ids % dim, dim).to(torch.float32)
            return type("Out", (), {"last_hidden_state": values})()

    model = pm.PairwiseModel.__new__(pm.PairwiseModel)
    torch.nn.Module.__init__(model)
    model.encoder = Encoder()
    model.dropout = torch.nn.Identity()
    model.head = torch.nn.Linear(dim, 1)
    return model


def test_train_loop_and_evaluation_execute_end_to_end():
    """The training loop, loss, checkpoint save/load and evaluation all run on a
    tiny toy model. This proves the mechanism only, never accuracy."""
    import torch

    import pairwise_model as pm
    import pairwise_train as pt

    groups = {"查看": "感知", "告知": "言语", "提问": "言语"}
    train_rows = [toy_row(["task_a：把盒子打开", "task_b：说明盒子的状态"], group="感知")]
    train_rows.append(toy_row(["task_c：告诉对方盒子在哪"], group="言语",
                              steps=[{"action": "告知", "object": "lu"}]))
    valid_rows = [toy_row(["task_a：把盒子打开"], group="感知")]
    tokenizer = _FakeTokenizer()
    train_set = pm.PairwiseDataset(train_rows, tokenizer, 64, groups, [("toy-1", 0), ("toy-1", 0)])
    valid_set = pm.PairwiseDataset(valid_rows, tokenizer, 64, groups, [("toy-1", 0)])

    model = _stub_model()
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=1e-2)
    stats = pt.run_epoch(model, train_set, tokenizer, optimizer, 1, 7)
    assert stats["batches"] >= 1 and stats["loss"] > 0
    result = pt.evaluate(model, valid_set, tokenizer)
    assert result["step1"]["decisions"] == 1
    assert result["step1"]["rowHit"] in (0.0, 1.0)
    assert set(result["rows"][0]["logits"]) and len(result["rows"][0]["logits"]) == 13

    checkpoint = Path(__file__).resolve().parent / "_smoke.pt"
    torch.save({"state": model.state_dict(), "serializerDigest": ps.serializer_digest()}, checkpoint)
    loaded = torch.load(checkpoint, map_location="cpu")
    assert loaded["serializerDigest"] == ps.serializer_digest()
    checkpoint.unlink()
