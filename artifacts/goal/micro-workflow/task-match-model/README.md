# Task/fact verifier pilot (int8)

MiniRBT pair encoder + `relevance` + `satisfaction` (yes/partial/no).

    cat artifacts/goal/micro-workflow/task-match-model/part-* > frontend/public/micro/task-match-int8.onnx

sha256: a3c115163e9239e66c90839d10554bb4bacda582e7cfd24cd58cd2c171cccd06

Trained from `task-match-data.jsonl` (80 hand-authored pairs, 20 held-out rows)
by `train_task_match.py`. Held-out: relevance 18/20, satisfaction 9/15 on
related facts. This is a pilot; the port abstains on low confidence and the
LLM verifier remains the authority.
