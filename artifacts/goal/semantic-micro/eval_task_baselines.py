#!/usr/bin/env python3
"""Baselines for the task-achievement (goal, fact) dataset.

Runs on experiments/semantic-micro/dataset/{train,val,test,eval_frozen}.jsonl:
- program: decomposed goal conditions must all be covered and the fact outcome
  must be completed;
- lexical: char-bigram overlap threshold plus completed outcome;
- condition head: /micro/task-condition-int8.onnx (4 classes);
- pair verifier: /micro/task-match-int8.onnx (relevance + satisfaction);
- logistic: char n-gram TF-IDF + logistic regression trained on train only.

Usage:
  python artifacts/goal/semantic-micro/eval_task_baselines.py \
      --data experiments/semantic-micro/dataset
"""
import argparse
import json
import os
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

import onnxruntime as ort

WORLD = "data/worlds/dragon-raja-free-day.world.json"
VOCAB = "frontend/public/micro/minirbt-vocab.txt"
CONDITION_MODEL = "frontend/public/micro/task-condition-int8.onnx"
PAIR_MODEL = "frontend/public/micro/task-match-int8.onnx"

CONFIRM = ["确认", "报告", "说明", "告知", "问清", "核实", "看见", "检查", "证明", "登记", "回答", "听清", "核对"]
TIME = re.compile(r"\d{1,2}:\d{2}|停赛前|结束前|午夜|天亮|天黑|明天|次日|黄昏|清晨|小时后|分钟后|入夜")
ACTION = ["前往", "走向", "走进", "进入", "赶到", "回到", "退到", "离开", "登上", "走到",
          "守住", "护住", "挡住", "拦住", "守", "递给", "交给", "戴上", "戴好", "拿起", "开笼", "放出",
          "发布", "扣好", "恢复", "更换", "换上", "打开", "使用", "到达"]


def load_world():
    data = json.load(open(WORLD, encoding="utf-8"))
    initial = data.get("initial") or data
    names = {"characters": [], "items": [], "locations": []}
    for group in names:
        for entity in (initial.get(group) or {}).values():
            name = entity.get("name") or ""
            if name:
                names[group].append(name)
    return names


def decompose(goal, world):
    item = next((name for name in world["items"]
                 if name in goal and (len(name.split("的")[-1]) >= 3 or name in goal)), None)
    target = next((name for name in world["characters"] if name in goal), None)
    decision = None
    if re.search(r"选择|决定|选定|选一条", goal):
        match = re.search(r"选择[^，。；]*|决定[^，。；]*|选定[^，。；]*|选一条[^，。；]*", goal)
        decision = match.group(0) if match else "选择"
    location = None if decision else next((name for name in sorted(world["locations"], key=len, reverse=True)
                                           if name in goal), None)
    time = TIME.search(goal)
    confirmation = next((word for word in CONFIRM if word in goal), None)
    action = next((word for word in ACTION if word in goal), None)
    rows = []
    if time:
        rows.append(("time", time.group(0)))
    if location:
        rows.append(("location", location))
    if item:
        rows.append(("item", item))
    if target:
        rows.append(("target", target))
    if decision:
        rows.append(("decision", decision))
    if confirmation:
        rows.append(("confirmation", confirmation))
    if action:
        rows.append(("action", action))
    return rows


def coverage(conditions, fact):
    matched, missing = 0, []
    for kind, value in conditions:
        if kind == "time":
            hit = value in fact
        elif kind in ("location", "target"):
            hit = value in fact or (len(value) > 4 and value[-4:] in fact)
        elif kind == "item":
            hit = value in fact or value.split("的")[-1] in fact
        elif kind == "decision":
            hit = bool(re.search(r"决定|选择|选定|选了|就走|走这", fact))
        elif kind == "confirmation":
            hit = any(word in fact for word in CONFIRM)
        elif kind == "action":
            hit = value in fact or any(word in fact for word in ACTION)
        else:
            hit = False
        if hit:
            matched += 1
        else:
            missing.append(f"{kind}：{value}")
    return matched, len(conditions), missing


def outcome_of(text):
    for marker, label in (("达到目的", "completed"), ("只完成一部分", "partial"),
                          ("没有成功", "failed"), ("被阻止", "blocked"), ("没有变化", "unaffected")):
        if marker in text:
            return label
    return "unknown"


class BertTokenizer:
    def __init__(self, path=VOCAB):
        self.vocab = {}
        for index, token in enumerate(open(path, encoding="utf-8").read().splitlines()):
            if token:
                self.vocab[token] = index
        self.unk = self.vocab.get("[UNK]", 100)

    @staticmethod
    def basic(text):
        text = re.sub(r"[\u0000�]", "", text)
        spaced = "".join(f" {ch} " if (0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF) else ch
                         for ch in text)
        import unicodedata

        def is_punct(ch):
            code = ord(ch)
            if 33 <= code <= 47 or 58 <= code <= 64 or 91 <= code <= 96 or 123 <= code <= 126:
                return True
            return unicodedata.category(ch).startswith("P")

        out = []
        for word in spaced.split():
            current = ""
            for ch in word.lower():
                if is_punct(ch):
                    if current:
                        out.append(current)
                    out.append(ch)
                    current = ""
                else:
                    current += ch
            if current:
                out.append(current)
        return out

    def wordpiece(self, token):
        if len(token) > 100:
            return ["[UNK]"]
        pieces, start = [], 0
        while start < len(token):
            end, piece = len(token), None
            while start < end:
                candidate = ("##" if start else "") + token[start:end]
                if candidate in self.vocab:
                    piece = candidate
                    break
                end -= 1
            if piece is None:
                return ["[UNK]"]
            pieces.append(piece)
            start = end
        return pieces

    def tokens(self, text):
        return [piece for token in self.basic(text) for piece in self.wordpiece(token)]

    def encode_pair(self, left, right, max_len=160):
        left = self.tokens(left)
        right = self.tokens(right)
        budget = max(0, max_len - 3)
        while len(left) + len(right) > budget:
            if len(left) > len(right):
                left.pop()
            else:
                right.pop()
            if not left and not right:
                break
        toks = ["[CLS]"] + left + ["[SEP]"] + right + ["[SEP]"]
        ids = [self.vocab.get(token, self.unk) for token in toks]
        return ids


def run_onnx(session, ids):
    data = np.array([ids], dtype=np.int64)
    mask = np.ones_like(data)
    return session.run(None, {"input_ids": data, "attention_mask": mask})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="experiments/semantic-micro/dataset")
    args = parser.parse_args()
    world = load_world()
    tokenizer = BertTokenizer()
    cond = ort.InferenceSession(CONDITION_MODEL, providers=["CPUExecutionProvider"])
    pair = ort.InferenceSession(PAIR_MODEL, providers=["CPUExecutionProvider"])

    data = {}
    for split in ("train", "val", "test", "eval_frozen"):
        path = os.path.join(args.data, f"{split}.jsonl")
        data[split] = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()] if os.path.exists(path) else []

    def label(row):
        return 1 if row["label"] == "yes" else 0

    def evaluate(name, predict, splits=("val", "test", "eval_frozen")):
        print(f"\n== {name}")
        for split in splits:
            rows = data[split]
            if not rows:
                continue
            y = [label(row) for row in rows]
            p = [predict(row) for row in rows]
            print(f"-- {split} n={len(rows)} yes={sum(y)}")
            print(confusion_matrix(y, p, labels=[0, 1]))
            print(classification_report(y, p, labels=[0, 1], target_names=["no", "yes"], zero_division=0, digits=3))

    def program_predict(row):
        conditions = decompose(row["goal"], world)
        matched, total, _ = coverage(conditions, row["factText"])
        return int(total > 0 and matched == total and outcome_of(row["factText"]) == "completed")

    def lexical(thresh=0.35):
        def predict(row):
            clean = lambda text: re.sub(r"[^一-鿿A-Za-z0-9]", "", text)
            left, right = clean(row["factText"]), clean(row["goal"])
            grams = lambda text: {text[i:i + 2] for i in range(len(text) - 1)}
            goal_grams = grams(right)
            score = len(grams(left) & goal_grams) / len(goal_grams) if goal_grams else 0
            return int(score >= thresh and outcome_of(row["factText"]) == "completed")
        return predict

    def condition_predict(row):
        ids = tokenizer.encode_pair("条件：" + row["goal"], row["factText"], 160)
        logits = run_onnx(cond, ids)[0][0]
        return int(int(np.argmax(logits)) == 3)

    def pair_predict(row):
        ids = tokenizer.encode_pair("任务：" + row["goal"], row["factText"], 160)
        rel, sat = run_onnx(pair, ids)
        rel = float(rel[0])
        probs = np.exp(sat[0] - sat[0].max()) / np.exp(sat[0] - sat[0].max()).sum()
        return int(rel >= 0.5 and float(probs[0]) >= 0.7)

    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=20000, sublinear_tf=True)
    train_rows = data["train"]
    x_train = vectorizer.fit_transform([row["goal"] + " ␟ " + row["factText"] for row in train_rows])
    y_train = [label(row) for row in train_rows]
    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(x_train, y_train)

    def learned_predict(row):
        x = vectorizer.transform([row["goal"] + " ␟ " + row["factText"]])
        return int(model.predict(x)[0])

    evaluate("program", program_predict)
    evaluate("lexical(0.35)+completed", lexical())
    evaluate("condition-head", condition_predict)
    evaluate("pair-verifier", pair_predict)
    evaluate("logistic", learned_predict, splits=("val", "test", "eval_frozen"))


if __name__ == "__main__":
    main()
