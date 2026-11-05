"""Freeze the code/data/base combination a run will use.

Writes sha256 for every file that affects the result, plus interpreter and
library versions. Run it before an upload so the remote copy can be checked
against the same numbers.
"""
import hashlib, json, pathlib, platform, sys

HERE = pathlib.Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
OUT = ROOT / "artifacts" / "world-components" / "n4-run-freeze-r1.json"

CODE = [HERE / n for n in ("train_n4_formal.py", "train_n4_struct.py",
                           "train_verbalizer.py", "eval_n4_holdout.py",
                           "sequence_policy.py", "smoke_full_length.py",
                           "verify_sequence_policy.py", "test_sequence_policy.py")]
DATA = [HERE / "formal_pairs.jsonl",
        HERE / "verbalizer_pairs.jsonl", HERE / "holdout_pairs.jsonl",
        EXP / "n4_rewrite60" / "corpus140.jsonl",
        EXP / "n4_rewrite60" / "checker.py",
        EXP / "n4_rewrite60" / "checker-v7-freeze.json",
        EXP / "n4_rewrite60" / "isolated-v1" / "isolated-v1.jsonl",
        EXP / "n4_rewrite60" / "isolated-v1" / "isolated-v1.labels.json"]
BASE = EXP / "assets" / "randeng-t5-77m"
BASE_FILES = ("model.safetensors", "config.json", "spiece.model",
              "tokenizer_config.json", "special_tokens_map.json")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    rec = {"purpose": "freeze code/data/base for the three-arm run",
           "local": {"python": sys.version.split()[0],
                     "platform": platform.platform(),
                     "torch": __import__("torch").__version__,
                     "transformers": __import__("transformers").__version__,
                     "numpy": __import__("numpy").__version__},
           "remoteEnv": {"torch": "2.5.1+cu124", "transformers": "4.51.3",
                         "gpu": "RTX 4090 D 24GB",
                         "source": "frontend/scripts/_hpc_probe_crf.py 2026-11-04"},
           "code": {}, "data": {}, "base": {}}
    for p in CODE + DATA:
        if p.exists():
            rec["code" if p in CODE else "data"][str(p.relative_to(ROOT))] = sha(p)
        else:
            rec["code" if p in CODE else "data"][str(p.relative_to(ROOT))] = "MISSING"
    for n in BASE_FILES:
        p = BASE / n
        rec["base"][n] = sha(p) if p.exists() else "MISSING"
    missing = [k for sect in ("code", "data", "base")
               for k, v in rec[sect].items() if v == "MISSING"]
    rec["missing"] = missing
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"files frozen: code {len(rec['code'])}, data {len(rec['data'])}, "
          f"base {len(rec['base'])}; missing {len(missing)}")
    print(f"-> {OUT}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
