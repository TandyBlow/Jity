"""Split dataset rows into model input (X) and target text (y).

Currently every row keeps both halves in one JSON object, so nothing stops a
loader from feeding the whole line to a model — which would hand the model the
answer. This tool is the single place that decides the boundary:

  X = 视角 + 上回合状态 + 本回合变化 + 本回合状态
  y = 叙事

It reads every row-*.jsonl in this directory, writes one line per row to
rows-xy.jsonl with {id, x, y, xText}, and refuses to run if the target text
appears inside the serialised input.

x       the structured input, for prompt building or debugging
y       the target narrative
xText   the same input as one flat string (the JSON above, nothing else)

usage: python split_xy.py
"""

import glob
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "rows-xy.jsonl")

FIELDS = ["视角", "上回合状态", "本回合变化", "本回合状态"]


def build_x(row):
    return {name: row[name] for name in FIELDS}


def build_text(x):
    """No instruction and no wrapper text: the model input is exactly the data."""
    return json.dumps(x, ensure_ascii=False)


def main():
    paths = sorted(glob.glob(os.path.join(HERE, "row-*-scene.jsonl")))
    # row-scene-only.jsonl is an early format sample (three long paragraphs and an
    # unregistered character); it does not follow this dataset's shape, so it is
    # kept on disk for reference but kept OUT of training.
    records, total_x, total_y = [], 0, 0
    for path in paths:
        row = json.loads(io.open(path, encoding="utf-8").read())
        missing = [name for name in FIELDS + ["叙事"] if name not in row]
        if missing:
            raise SystemExit(f"{path}: missing fields {missing}")
        x = build_x(row)
        y = row["叙事"]
        text = build_text(x)
        if y.strip() and y.strip() in text:
            raise SystemExit(f"{path}: target text found inside the input")
        # a crude but effective leak check: any 40-character run of y inside X
        for start in range(0, max(len(y) - 40, 0), 40):
            chunk = y[start:start + 40]
            if chunk and chunk in json.dumps(x, ensure_ascii=False):
                raise SystemExit(f"{path}: 40-character run of the target leaked into X")
        records.append({"id": os.path.basename(path).replace("-scene.jsonl", "")
                                      .replace(".jsonl", ""),
                        "x": x, "y": y, "xText": text})
        total_x += len(text)
        total_y += len(y)

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{OUT}: {len(records)} rows")
    print(f"X 总字符 {total_x}，y 总字符 {total_y}")


if __name__ == "__main__":
    main()
