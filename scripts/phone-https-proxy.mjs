// Local HTTPS front for real-device testing: a phone on the LAN gets a secure
// context (crypto.subtle) and full-speed WiFi model downloads. Self-signed
// cert in .local/phone-tls; run from the repo root:
//   node scripts/phone-https-proxy.mjs
import { readFileSync } from 'node:fs';
import { request } from 'node:http';
import { createServer } from 'node:https';

const key = readFileSync('.local/phone-tls/key.pem');
const cert = readFileSync('.local/phone-tls/cert.pem');
const UPSTREAM = { hostname: '127.0.0.1', port: 3177 };

const server = createServer({ key, cert }, (req, res) => {
  const upstream = request({ ...UPSTREAM, path: req.url, method: req.method, headers: req.headers }, (answer) => {
    res.writeHead(answer.statusCode ?? 502, answer.headers);
    answer.pipe(res);
  });
  upstream.on('error', () => {
    res.writeHead(502, { 'content-type': 'text/plain' });
    res.end('upstream error');
  });
  req.pipe(upstream);
});

server.listen(3443, '0.0.0.0', () => {
  console.log('[phone-https] https://10.250.11.141:3443 -> http://127.0.0.1:3177');
});
