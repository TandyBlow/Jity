/** Serve a GGUF with byte-range support.
 *
 * wllama's wasm file reader asks the URL how it may read it: it sends a HEAD,
 * checks `Content-length` and `Accept-Ranges`. When the server advertises
 * `Accept-Ranges: bytes`, the reader streams 1 MiB chunks; when it does not,
 * the reader picks the whole file as a single chunk and calls
 * `fetch(url).arrayBuffer()`. That works for a 1.1 GB model and fails for the
 * 2.5 GB Qwen3-4B (the browser cannot materialize it as one ArrayBuffer), which
 * is exactly the “Failed to fetch” this project saw.
 *
 * So: always advertise ranges and answer `Range` with 206. A production model
 * host must do the same; this is not a test-only convenience.
 */
import { createReadStream, statSync } from 'node:fs';

const RANGE = /^bytes=(\d*)-(\d*)$/;

export function sendGguf(request, response, file) {
  const total = statSync(file).size;
  const header = request.headers.range;
  response.setHeader('Accept-Ranges', 'bytes');
  response.setHeader('Content-Type', 'application/octet-stream');
  response.setHeader('Cache-Control', 'no-store');
  // wllama first asks with HEAD for length + range support; do not stream 2.5 GB
  // of body for a metadata request.
  if (request.method === 'HEAD') {
    response.statusCode = 200;
    response.setHeader('Content-Length', total);
    response.end();
    return;
  }
  if (header) {
    const match = RANGE.exec(header.trim());
    if (!match) {
      response.statusCode = 416;
      response.setHeader('Content-Range', `bytes */${total}`);
      response.end();
      return;
    }
    const start = match[1] === '' ? Math.max(0, total - Number(match[2])) : Number(match[1]);
    const end = match[1] !== '' && match[2] !== '' ? Math.min(Number(match[2]), total - 1) : total - 1;
    if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || start >= total) {
      response.statusCode = 416;
      response.setHeader('Content-Range', `bytes */${total}`);
      response.end();
      return;
    }
    response.statusCode = 206;
    response.setHeader('Content-Range', `bytes ${start}-${end}/${total}`);
    response.setHeader('Content-Length', end - start + 1);
    createReadStream(file, { start, end }).pipe(response);
    return;
  }
  response.statusCode = 200;
  response.setHeader('Content-Length', total);
  createReadStream(file).pipe(response);
}
