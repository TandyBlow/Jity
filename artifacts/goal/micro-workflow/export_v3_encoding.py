# -*- coding: utf-8 -*-
"""Export the v3 tokenizer tables for a browser-side encoder (no training).

The source ids come from the MiniRBT BertTokenizer that already ships with the
page; this file adds the output vocabulary (word level) and the candidate
vocabulary (char level) plus the token regexes and the fixed shapes, so the
TS port can encode a real point exactly like the Python exporter did."""
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/others/Jity')
OUT = HERE / 'micro-generative/v3-encoding.json'
PUB = ROOT / 'frontend/public/micro/v3-encoding.json'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    v3 = load('v3', HERE / 'micro_generative_v3.py')
    v2 = v3.v2
    hand_train = load('hand_train', HERE / 'hand_train.py')
    hand_test = load('hand_test', HERE / 'hand_test.py')
    exporter = load('export_v3', HERE / 'export_v3_candidate_onnx.py')
    train_rows, test_rows = exporter.build_rows()
    cand_vocab, out_vocab = exporter.build_vocabs(train_rows, test_rows)
    payload = {
        'kind': 'v3-encoding',
        'constants': {'maxSource': 96, 'maxTarget': 64, 'maxTokens': 32,
                      'maxCandidates': 10, 'candChars': 11, 'heads': 8, 'headDim': 32, 'dModel': 256},
        'patterns': {'out': v2.OUT_TOKEN.pattern, 'src': v2.SRC_TOKEN.pattern, 'cand': v3.CAND_TOKEN.pattern},
        'out': {'itos': out_vocab.itos, 'stoi': out_vocab.stoi,
                'pad': out_vocab.pad, 'bos': out_vocab.bos, 'eos': out_vocab.eos, 'unk': out_vocab.unk},
        'cand': {'itos': cand_vocab.itos, 'stoi': cand_vocab.stoi, 'pad': cand_vocab.pad, 'unk': cand_vocab.unk},
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    OUT.write_text(text, encoding='utf8')
    PUB.write_text(text, encoding='utf8')
    print(json.dumps({'outVocab': len(out_vocab.itos), 'candVocab': len(cand_vocab.itos),
                      'dModel': getattr(v3, 'D_MODEL', None), 'out': str(OUT), 'pub': str(PUB)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
