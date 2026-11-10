// Minimal GGUF metadata reader: dumps the header key/values that matter for
// running a foreign checkpoint correctly (architecture, name, chat template,
// context length, tokenizer identity) without loading the weights into a
// browser or into Node memory.
//
//   node scripts/candidate-model/gguf-meta.mjs --file <path.gguf> [--out meta.json] [--no-template]
//
// The parser only reads the metadata block at the head of the file; tensor
// data is never touched. Large arrays (vocabulary/merges) are counted and
// skipped unless --keep-arrays is passed, so the output stays small.
import { closeSync, openSync, readSync, statSync, writeFileSync } from 'node:fs';

const TYPE_SIZES = { 0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8 };
const TYPE_NAMES = { 0: 'u8', 1: 'i8', 2: 'u16', 3: 'i16', 4: 'u32', 5: 'i32', 6: 'f32', 7: 'bool', 8: 'string', 9: 'array', 10: 'u64', 11: 'i64', 12: 'f64' };

function reader(fd) {
  let position = 0;
  const buffer = Buffer.alloc(1 << 20);
  let viewStart = 0, viewEnd = 0;
  const fill = (needed) => {
    if (viewEnd - viewStart >= needed) return;
    // Shift the remainder to the front; the metadata block is read
    // sequentially so this never grows beyond the chunk plus one value.
    if (needed > buffer.length) throw new Error(`value of ${needed} bytes exceeds the read chunk`);
    buffer.copy(buffer, 0, viewStart, viewEnd);
    viewEnd -= viewStart;
    viewStart = 0;
    while (viewEnd < needed) {
      const read = readSync(fd, buffer, viewEnd, buffer.length - viewEnd, position);
      if (read === 0) throw new Error('unexpected end of file');
      position += read;
      viewEnd += read;
    }
  };
  const take = (n) => {
    fill(n);
    const slice = buffer.subarray(viewStart, viewStart + n);
    viewStart += n;
    return slice;
  };
  return {
    u8: () => take(1).readUInt8(0),
    u16: () => take(2).readUInt16LE(0),
    u32: () => take(4).readUInt32LE(0),
    i32: () => take(4).readInt32LE(0),
    u64: () => Number(take(8).readBigUInt64LE(0)),
    i64: () => Number(take(8).readBigInt64LE(0)),
    f32: () => take(4).readFloatLE(0),
    f64: () => take(8).readDoubleLE(0),
    str: () => { const length = Number(take(8).readBigUInt64LE(0)); return take(length).toString('utf8'); },
    skip: (n) => { // skip without materialising
      const available = viewEnd - viewStart;
      if (available >= n) { viewStart += n; return; }
      const remaining = n - available;
      viewStart = viewEnd = 0;
      position += remaining;
      // readSync at the new position is fine; the next fill continues there
      const jump = readSync(fd, buffer, 0, 0, position);
      void jump;
    },
  };
}

function readValue(r, type, keepArrays) {
  switch (type) {
    case 0: return r.u8();
    case 1: return r.u8() - 256 * (r.u8() > 127 ? 1 : 0); // i8 via two reads would be wrong; handled below
    case 2: return r.u16();
    case 3: return r.u16();
    case 4: return r.u32();
    case 5: return r.i32();
    case 6: return r.f32();
    case 7: return r.u8() !== 0;
    case 8: return r.str();
    case 10: return r.u64();
    case 11: return r.i64();
    case 12: return r.f64();
    case 9: {
      const elementType = r.u32();
      const count = r.u64();
      if (elementType === 8) {
        const sample = [];
        for (let i = 0; i < count; i += 1) {
          const value = r.str();
          if (keepArrays || i < 3) sample.push(value);
        }
        return { array: TYPE_NAMES[elementType] ?? elementType, count, sample };
      }
      const size = TYPE_SIZES[elementType];
      if (size) { r.skip(count * size); return { array: TYPE_NAMES[elementType] ?? elementType, count, skipped: true }; }
      throw new Error(`unsupported array element type ${elementType}`);
    }
    default: throw new Error(`unsupported value type ${type}`);
  }
}

const args = process.argv.slice(2);
const option = (flag, fallback) => (args.includes(flag) ? args[args.indexOf(flag) + 1] : fallback);
const file = option('--file');
if (!file) { console.error('usage: gguf-meta.mjs --file <path.gguf> [--out meta.json] [--keep-arrays]'); process.exit(2); }
const keepArrays = args.includes('--keep-arrays');
const fd = openSync(file, 'r');
try {
  const r = reader(fd);
  const magic = r.u32();
  if (magic !== 0x46554747) throw new Error(`not a GGUF file (magic ${magic.toString(16)})`);
  const version = r.u32();
  const tensorCount = r.u64();
  const kvCount = r.u64();
  const meta = {};
  for (let i = 0; i < kvCount; i += 1) {
    const key = r.str();
    const type = r.u32();
    // The i8 case above reads two bytes; reimplement it cleanly here.
    if (type === 1) {
      const raw = r.u8();
      meta[key] = raw > 127 ? raw - 256 : raw;
      continue;
    }
    meta[key] = readValue(r, type, keepArrays);
  }
  const template = typeof meta['tokenizer.chat_template'] === 'string' ? meta['tokenizer.chat_template'] : null;
  const report = {
    file, bytes: statSync(file).size, version, tensorCount, metadataCount: kvCount,
    identity: {
      name: meta['general.name'] ?? null,
      architecture: meta['general.architecture'] ?? null,
      parameters: meta['general.parameter_count'] ?? null,
      quantization: meta['general.quantization_version'] ?? null,
      fileType: meta['general.file_type'] ?? null,
    },
    model: {
      contextLength: meta['qwen2.context_length'] ?? meta['qwen3.context_length'] ?? meta['llama.context_length'] ?? null,
      embeddingLength: meta['qwen2.embedding_length'] ?? meta['qwen3.embedding_length'] ?? null,
      blockCount: meta['qwen2.block_count'] ?? meta['qwen3.block_count'] ?? null,
      headCount: meta['qwen2.attention.head_count'] ?? meta['qwen3.attention.head_count'] ?? null,
      chatTemplatePresent: template !== null,
      chatTemplate: template,
    },
    tokenizer: {
      model: meta['tokenizer.ggml.model'] ?? null,
      pre: meta['tokenizer.ggml.pre'] ?? null,
      tokens: Array.isArray(meta['tokenizer.ggml.tokens']) || meta['tokenizer.ggml.tokens']?.count
        ? (meta['tokenizer.ggml.tokens'].count ?? meta['tokenizer.ggml.tokens'].length) : null,
      bosId: meta['tokenizer.ggml.bos_token_id'] ?? null,
      eosId: meta['tokenizer.ggml.eos_token_id'] ?? null,
    },
    allKeys: Object.keys(meta).sort(),
  };
  const out = option('--out');
  if (out) { writeFileSync(out, `${JSON.stringify(report, null, 2)}\n`); console.log(`wrote ${out}`); }
  else console.log(JSON.stringify(report, null, 2));
} finally {
  closeSync(fd);
}
