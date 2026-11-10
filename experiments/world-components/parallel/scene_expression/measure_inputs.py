"""量冻结输入的实际 token 长度，供冻结协议引用。

只读：frozen/inputs.json、u240 tokenizer。
只写：frozen/prompt-tokens.json。

用法（仓库根）：
  /d/software/Anaconda/envs/nndl_proj/python.exe -X utf8 \
    experiments/world-components/parallel/scene_expression/measure_inputs.py
"""
import json
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FROZEN = HERE / "frozen"
MODEL_DIR = pathlib.Path(r"D:\others\Jity\.local\models")


def main():
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(str(MODEL_DIR), legacy=False,
                                      local_files_only=True)
    inputs = json.loads((FROZEN / "inputs.json").read_text(encoding="utf-8"))

    out = {}
    for sid, doc in inputs.items():
        if sid == "ns-pos-1":
            continue  # 仅调试样本，不进十题统计
        rows = []
        for idx, slot in enumerate(doc["slots"]):
            if slot["owner"] != "model":
                continue
            counts = {arm: len(tok(text)["input_ids"])
                      for arm, text in slot["prompts"].items()}
            rows.append({"slot": idx, "kind": slot["kind"], "tokens": counts})
        out[sid] = {"calls": rows,
                    "perArm": {arm: [r["tokens"][arm] for r in rows]
                               for arm in "ABC"}}

    summary = {}
    for arm in "ABC":
        vals = [t for sid in out for t in out[sid]["perArm"][arm]]
        summary[arm] = {"count": len(vals), "min": min(vals) if vals else None,
                        "p50": statistics.median(vals) if vals else None,
                        "max": max(vals) if vals else None}

    dst = FROZEN / "prompt-tokens.json"
    dst.write_text(json.dumps({"perSample": out, "summary": summary},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("保存:", dst)


if __name__ == "__main__":
    main()
