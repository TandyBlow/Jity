# -*- coding: utf-8 -*-
"""Dynamic int8 quantization for the pair scorer."""
import hashlib
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic

OUT = Path('D:/others/Jity/.local/micro-generalize')
SRC = OUT / 'pair-scorer.onnx'
DST = OUT / 'pair-scorer-int8.onnx'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    quantize_dynamic(str(SRC), str(DST), weight_type=QuantType.QInt8)
    for path in (SRC, DST):
        print(path.name, path.stat().st_size, sha(path))


if __name__ == '__main__':
    main()
