"""In-sample evaluation of a checkpoint on the frozen training pairs, to tell
overfitting (high train, low validation) from underfitting."""
from __future__ import annotations
import argparse, json, pathlib, sys
import torch
from transformers import BertTokenizer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pairwise_model as pm, pairwise_serialize as ps, pairwise_train as pt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True); ap.add_argument("--labels", required=True)
    ap.add_argument("--checkpoint", required=True); ap.add_argument("--freeze", required=True)
    ap.add_argument("--pairs", required=True); ap.add_argument("--pairs-freeze", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    frozen = json.loads(pathlib.Path(args.freeze).read_text(encoding="utf-8"))
    groups = ps.load_predicate_groups(args.labels)
    pairs = pt.load_frozen_pairs(pathlib.Path(args.pairs), pathlib.Path(args.pairs_freeze))
    ck = torch.load(args.checkpoint, map_location="cpu")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tok = BertTokenizer.from_pretrained(args.base, do_lower_case=True)
    model = pm.PairwiseModel(args.base, dropout=frozen["training"]["dropout"])
    model.load_state_dict(ck["state"]); model.to(device).eval()
    ds = pm.PairsDataset(pairs, tok, int(ck["maxLen"]))
    res = pt.evaluate(model, ds, tok, device)
    pathlib.Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"step1RowHit": res["step1"]["rowHit"], "allRowHit": res["all"]["rowHit"],
                      "decisions": res["all"]["decisions"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
