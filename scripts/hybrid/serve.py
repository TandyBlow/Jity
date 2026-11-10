"""Loopback API/D03 bridge. Keys and local model paths never reach the browser.

Start with --model-run and JITY_BRIDGE_TOKEN (>=32 characters). Each model
request is explicit; no fallback, hidden API target call, or state writes.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import run


def predict_targets(value, model_run, predict=run.local_predict):
    state = value['workingState']
    source = value['sourceId']
    characters = [{'id': k, 'name': state['initial']['characters'][k]['name']}
                  for k in state['characters']]
    if source not in state['characters'] or not isinstance(value.get('actionText'), str) or not value['actionText'].strip():
        raise ValueError('Missing frozen source/action')
    if len(characters) not in (2, 3):
        raise ValueError('D03 current model support is 2-3 characters; incomplete')
    # Entire effective state, no narrative history and no truncation. The
    # existing predictor rejects >512 tokens and verifies checkpoint identity.
    effective = {k: state[k] for k in ('time', 'characters', 'items', 'locations')}
    effective['definitions'] = state['initial']
    frozen = {'actorId': source, 'action': value['actionText'], 'characters': characters,
              'world': json.dumps(effective, ensure_ascii=False, separators=(',', ':')),
              'alreadyActedIds': value.get('alreadyActedIds', [])}
    result = predict(model_run, frozen)
    targets = result['targetIds']
    if len(set(targets)) != len(targets) or any(t not in state['characters'] or t == source for t in targets):
        raise ValueError('D03 invalid target proposal')
    return result


def handler(model_run, token):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send_error(403); return
            # No cross-origin browser access: use a same-origin server proxy.
            if self.headers.get('Origin'):
                self.send_error(403); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError('Invalid request size')
                value = json.loads(self.rfile.read(length).decode('utf-8'))
                if self.path == '/api':
                    result = run.api_json(value['instruction'], value['input'])
                elif self.path == '/d03':
                    result = predict_targets(value, model_run)
                else:
                    self.send_error(404); return
                payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
                self.send_response(200)
            except Exception:
                # Do not leak provider response bodies, secrets or local paths.
                payload = b'{"kind":"incomplete","reason":"D bridge request failed"}'
                self.send_response(422)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-run', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    token = os.environ.get('JITY_BRIDGE_TOKEN', '')
    if len(token) < 32:
        parser.error('Set a private JITY_BRIDGE_TOKEN of at least 32 characters')
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.model_run, token)).serve_forever()

if __name__ == '__main__':
    main()
