# -*- coding: utf-8 -*-
"""Dynamic int8 quantization of the split shared model."""
import hashlib
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic

ROOT = Path('D:/others/Jity')
SRC = ROOT / '.local/micro-quant/shared-split.onnx'
DST = ROOT / '.local/micro-quant/shared-split-int8.onnx'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    quantize_dynamic(str(SRC), str(DST), weight_type=QuantType.QInt8)
    for path in (SRC, DST):
        print(path.name, path.stat().st_size, sha(path))


if __name__ == '__main__':
    main()
