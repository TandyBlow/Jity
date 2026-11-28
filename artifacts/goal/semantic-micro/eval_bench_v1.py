#!/usr/bin/env python3
"""Evaluate verifier candidates on the human-labeled benchmark (bench-v1).

Binary target: yes vs not-yes (partial and no do not commit a task).
"""
import json
import os
import sys

import numpy as np
import onnxruntime as ort
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_gate_v2 as gate  # noqa: E402
from eval_task_baselines import BertTokenizer, run_onnx  # noqa: E402

BENCH = "experiments/semantic-micro/bench-v1.jsonl"
TRAIN = "experiments/semantic-micro/dataset/train.jsonl"
PAIR_MODEL = "frontend/public/micro/task-match-int8.onnx"


def load(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def main():
    bench = [row for row in load(BENCH) if row["verdict"] in ("yes", "no", "partial")]
    y = [1 if row["verdict"] == "yes" else 0 for row in bench]
    tokenizer = BertTokenizer()
    pair = ort.InferenceSession(PAIR_MODEL, providers=["CPUExecutionProvider"])
    train = load(TRAIN)
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), max_features=20000, sublinear_tf=True)
    x = vectorizer.fit_transform([(row.get("goal") or "") + " ␟ " + row.get("factText", "") for row in train])
    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(x, [1 if row["label"] == "yes" else 0 for row in train])

    def program(row):
        conditions = gate.decompose(row["goal"])
        if not conditions:
            return 0
        return 1 if gate.gate(conditions, row["fact"]) else 0

    def pair_verifier(row):
        ids = tokenizer.encode_pair("任务：" + row["goal"], row["fact"], 160)
        rel, sat = run_onnx(pair, ids)
        probs = np.exp(sat[0] - sat[0].max()) / np.exp(sat[0] - sat[0].max()).sum()
        return int(float(rel[0]) >= 0.5 and float(probs[0]) >= 0.7)

    def logistic(row):
        text = row["goal"] + " ␟ " + row["fact"]
        return int(model.predict(vectorizer.transform([text]))[0])

    def llm(row):
        return 1 if row.get("llm") == "yes" else 0

    for name, predict in (("llm-recorded", llm), ("program", program),
                          ("pair-verifier", pair_verifier), ("logistic", logistic)):
        p = [predict(row) for row in bench]
        print(f"\n== {name} n={len(bench)} yes={sum(y)}")
        print(confusion_matrix(y, p, labels=[0, 1]))
        print(classification_report(y, p, labels=[0, 1], target_names=["no", "yes"],
                                    zero_division=0, digits=3))
        for sheet in ("hard", "committed"):
            items = [row for row in bench if row["sheet"] == sheet]
            hits = sum(1 for row in items if predict(row) == (1 if row["verdict"] == "yes" else 0))
            print(f"  {sheet}: {hits}/{len(items)}")


if __name__ == "__main__":
    main()
