# -*- coding: utf-8 -*-
"""Dynamic int8 quantization for a joint model."""
import argparse
import hashlib
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic

OUT = Path('D:/others/Jity/.local/micro-joint')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    args = ap.parse_args()
    src = OUT / f'{args.name}.onnx'
    dst = OUT / f'{args.name}-int8.onnx'
    quantize_dynamic(str(src), str(dst), weight_type=QuantType.QInt8)
    for path in (src, dst):
        print(path.name, path.stat().st_size, sha(path))


if __name__ == '__main__':
    main()
