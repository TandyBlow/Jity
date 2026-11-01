# Judge browser-generated N4 texts with the frozen recognizer core (batch 3
# driver helper): reads a JSON object {name: text} on argv[2], the baked
# probe inputs (for plans) on argv[3], prints {name: {fails, reviews,
# clean}}. The recognizer core is corpus_check.check_narration — the SAME
# code the offline N5 stage uses; browser texts get no separate standard.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "n4_corpus"))
import corpus_check  # noqa: E402


def main() -> int:
    texts = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    probe = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    plans = {c["name"]: c["plan"] for c in probe["cases"]}
    out = {}
    for name, text in texts.items():
        plan = plans[name]
        refs = [e.get("ref", i) for i, e in enumerate(plan)]
        sentences = [s for s in text.split("。") if s.strip()]
        fails, reviews = corpus_check.check_narration(
            plan, text, [refs for _ in sentences], list(refs))
        out[name] = {"fails": fails, "reviews": reviews, "clean": not fails}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
