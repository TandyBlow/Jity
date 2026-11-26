# -*- coding: utf-8 -*-
"""Export encoder + decoder-step graphs for a real token-by-token ONNX loop.

Fixed 96/64 padding; the loop runs in onnxruntime (CPU). This is the Python
proof for the browser probe, not a browser measurement.
"""
import importlib.util
import json
import random
import statistics
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import torch.nn as nn
import onnxruntime.quantization as quant

HERE = Path(__file__).resolve().parent
ROOT = Path('D:/others/Jity')
spec = importlib.util.spec_from_file_location('pilot', HERE / 'micro_generative_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

random.seed(20261126)
torch.manual_seed(20261126)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
rows = pilot.condition_rows() + pilot.event_rows()
vocab = pilot.Vocab([row['input'] + row['output'] for row in rows])
model, _, _ = pilot.train_arm(rows, '5M', 'probe', device, vocab, epochs=40)
model.eval().to('cpu')


class EncoderExport(nn.Module):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def forward(self, src):
        pos = self.source.pos(torch.arange(src.shape[1], device=src.device))[None]
        return self.source.encoder(self.source.src_emb(src) + pos, src_key_padding_mask=src.eq(0))


class DecoderExport(nn.Module):
    def __init__(self, source):
        super().__init__()
        self.source = source

    def forward(self, memory, tgt, src_mask):
        pos = self.source.pos(torch.arange(tgt.shape[1], device=tgt.device))[None]
        causal = nn.Transformer.generate_square_subsequent_mask(tgt.shape[1], device=tgt.device)
        return self.source.out(self.source.decoder(
            self.source.tgt_emb(tgt) + pos, memory, tgt_mask=causal,
            tgt_key_padding_mask=tgt.eq(0), memory_key_padding_mask=src_mask.eq(0)))


encoder = EncoderExport(model)
decoder = DecoderExport(model)
src = torch.zeros(1, 96, dtype=torch.long)
tgt = torch.zeros(1, 64, dtype=torch.long)
mask = torch.ones(1, 96, dtype=torch.long)
memory = encoder(src)
enc_path = HERE / 'micro-generative' / 'seq2seq-encoder.onnx'
dec_path = HERE / 'micro-generative' / 'seq2seq-decoder.onnx'
enc_int8 = HERE / 'micro-generative' / 'seq2seq-encoder-int8.onnx'
dec_int8 = HERE / 'micro-generative' / 'seq2seq-decoder-int8.onnx'
torch.onnx.export(encoder, (src,), enc_path, opset_version=17, input_names=['src'],
                  output_names=['memory'])
torch.onnx.export(decoder, (memory, tgt, mask), dec_path, opset_version=17,
                  input_names=['memory', 'tgt', 'src_mask'], output_names=['logits'])
quant.quantize_dynamic(enc_path.as_posix(), enc_int8.as_posix(), weight_type=quant.QuantType.QInt8)
quant.quantize_dynamic(dec_path.as_posix(), dec_int8.as_posix(), weight_type=quant.QuantType.QInt8)
enc_session = ort.InferenceSession(enc_int8.as_posix(), providers=['CPUExecutionProvider'])
dec_session = ort.InferenceSession(dec_int8.as_posix(), providers=['CPUExecutionProvider'])


def tokenize(text):
    return [vocab.stoi.get(token, vocab.unk) for token in pilot.TOKEN.findall(text)]


def run(text, prefix, max_len=32):
    src_ids = tokenize(text)[:94] + [vocab.eos]
    source = np.full((1, 96), vocab.pad, dtype=np.int64)
    source[0, :len(src_ids)] = src_ids
    src_mask = (source != vocab.pad).astype(np.int64)
    began = time.perf_counter()
    memory_out = enc_session.run(None, {'src': source})[0]
    encode_ms = (time.perf_counter() - began) * 1000
    out = [vocab.bos] + tokenize(prefix)[-30:]
    token_ms = []
    for _ in range(max_len):
        target = np.full((1, 64), vocab.pad, dtype=np.int64)
        sequence = out[-64:]
        target[0, :len(sequence)] = sequence
        began = time.perf_counter()
        logits = dec_session.run(None, {'memory': memory_out, 'tgt': target, 'src_mask': src_mask})[0]
        token_ms.append((time.perf_counter() - began) * 1000)
        best = int(np.argmax(logits[0, len(sequence) - 1]))
        out.append(best)
        if best == vocab.eos:
            break
    text_out = ''.join(vocab.itos[index] for index in out[1 + len(tokenize(prefix)[-30:]):]
                       if index not in (vocab.pad, vocab.bos, vocab.eos))
    return text_out, encode_ms, token_ms


sample_row = next(row for row in rows if row['task'] == 'events' and len(row['output']) > 25)
sample = sample_row['input']
prefix = sample_row['prefix']
got, encode_ms, token_ms = run(sample, prefix)
times = []
for _ in range(5):
    began = time.perf_counter()
    run(sample, prefix)
    times.append((time.perf_counter() - began) * 1000)
times.sort()
report = {
    'params': sum(p.numel() for p in model.parameters()),
    'encoderInt8MB': round(enc_int8.stat().st_size / 1e6, 2),
    'decoderInt8MB': round(dec_int8.stat().st_size / 1e6, 2),
    'encodeMs': round(encode_ms, 1),
    'perTokenMs': round(statistics.median(token_ms), 2),
    'tokens': len(token_ms),
    'fullP50Ms': round(statistics.median(times), 1),
    'fullP95Ms': round(times[min(len(times) - 1, int(len(times) * 0.95))], 1),
    'sampleInput': sample,
    'sampleOutput': got,
    'note': 'fixed 96/64, int8 onnxruntime CPU; not browser',
}
(HERE / 'micro-generative' / 'seq2seq-steps-report.json').write_text(
    json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
(HERE / 'micro-generative' / 'probe-vocab.json').write_text(
    json.dumps({'itos': vocab.itos, 'pad': vocab.pad, 'bos': vocab.bos, 'eos': vocab.eos,
                'unk': vocab.unk, 'tokenPattern': pilot.TOKEN.pattern}, ensure_ascii=False),
    encoding='utf8')
public = ROOT / 'frontend/public/micro'
public.mkdir(parents=True, exist_ok=True)
for source_path, name in ((enc_int8, 'probe-encoder-int8.onnx'), (dec_int8, 'probe-decoder-int8.onnx')):
    (public / name).write_bytes(source_path.read_bytes())
(public / 'probe-vocab.json').write_text(
    (HERE / 'micro-generative' / 'probe-vocab.json').read_text(encoding='utf8'), encoding='utf8')
for path in (enc_path, dec_path):
    path.unlink()
print(json.dumps(report, ensure_ascii=False, indent=1))
