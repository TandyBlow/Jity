# -*- coding: utf-8 -*-
"""Check a fixed-length ONNX export after the legacy dynamic-axis defect.

The legacy exporter bakes the dummy lengths. Fixed 96/64 padding is a valid
fallback; this measures the runtime and size, not a browser decode loop.
"""
import importlib.util
import json
import statistics
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import onnxruntime.quantization as quant

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pilot', HERE / 'micro_generative_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

rows = pilot.condition_rows() + pilot.event_rows()
vocab = pilot.Vocab([row['input'] + row['output'] for row in rows])
model = pilot.Seq2Seq(len(vocab.itos), 224, 3, 7)
model.eval()
src = torch.zeros(1, 96, dtype=torch.long)
tgt = torch.zeros(1, 64, dtype=torch.long)
fp32 = HERE / 'micro-generative' / 'fixed-5M.onnx'
int8 = HERE / 'micro-generative' / 'fixed-5M-int8.onnx'
torch.onnx.export(model, (src, tgt), fp32, opset_version=17, input_names=['src', 'tgt'],
                  output_names=['logits'])
quant.quantize_dynamic(fp32.as_posix(), int8.as_posix(), weight_type=quant.QuantType.QInt8)
session = ort.InferenceSession(int8.as_posix(), providers=['CPUExecutionProvider'])
outputs = {}
for length in (96, 95):
    try:
        out = session.run(None, {'src': np.zeros((1, length), dtype=np.int64),
                                 'tgt': np.zeros((1, 64), dtype=np.int64)})
        outputs[length] = list(out[0].shape)
    except Exception as error:
        outputs[length] = f'{type(error).__name__}: {str(error).splitlines()[0][:160]}'
times = []
for _ in range(20):
    began = time.perf_counter()
    session.run(None, {'src': np.zeros((1, 96), dtype=np.int64), 'tgt': np.zeros((1, 64), dtype=np.int64)})
    times.append((time.perf_counter() - began) * 1000)
times.sort()
report = {'fp32MB': round(fp32.stat().st_size / 1e6, 2), 'int8MB': round(int8.stat().st_size / 1e6, 2),
          'outputs': outputs, 'p50Ms': round(statistics.median(times), 1),
          'p95Ms': round(times[int(len(times) * 0.95)], 1),
          'note': 'teacher-forcing forward at fixed 96/64; not the browser decode loop'}
(HERE / 'micro-generative' / 'fixed-onnx-report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
print(json.dumps(report, ensure_ascii=False, indent=1))
fp32.unlink()
