# Continuation four heads (int8)

MiniRBT encoder + `novelty` / `unfinished` / `necessity` / `intervene` heads.

Reassemble with:

    cat artifacts/goal/micro-workflow/continuation-model/part-* > frontend/public/micro/continuation-heads-int8.onnx

sha256: d0fd9058d7af0e74088982f639abc5fe81bde9c674cb96c1e7f554f3534f25ea

Trained from `continuation-data.jsonl` by `train_continuation_heads.py`
(held-out actors: caesar, lin, qin, tomiyama). Labels are rule-derived; the
report is `continuation-training-report.json`. This is a pilot head, not
evidence of semantic generalization.
