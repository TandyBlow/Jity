"""Read-only preview server for the frozen adapter.

Serves one world and point at a time from a committed record. Nothing is written: the adapter opens the
database read-only and this server only serialises its result. It exists so the preview page can call
the frozen adapter instead of reading a stale file.
"""
import argparse
import json
import pathlib
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import adapt_facts  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    database = None
    backend = adapt_facts.DEFAULT_BACKEND

    def _send(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == '/worlds':
            db = adapt_facts.connect(self.database)
            worlds = []
            for (world_id,) in db.execute('SELECT id FROM worlds ORDER BY id'):
                points = [{'pointId': row[0], 'sequence': row[1], 'kind': row[2], 'previousPointId': row[3]}
                          for row in db.execute('SELECT id, sequence, kind, previous_point_id FROM world_points '
                                                'WHERE world_id=? ORDER BY sequence', (world_id,))]
                worlds.append({'worldId': world_id, 'points': points})
            db.close()
            self._send({'worlds': worlds})
            return
        if parsed.path == '/preview':
            world_id = (query.get('world') or [''])[0]
            point_id = (query.get('point') or [''])[0]
            if not world_id or not point_id:
                self._send({'error': 'world and point are required'}, 400)
                return
            db = adapt_facts.connect(self.database)
            names = adapt_facts.labels(db, world_id)
            point = adapt_facts.load_point(db, world_id, point_id)
            if point is None:
                self._send({'error': 'point not found'}, 404)
                return
            facts, gaps, unshown = adapt_facts.adapt_point(db, world_id, point_id, names, self.backend)
            db.close()
            self._send({'worldId': world_id, 'pointId': point_id, 'sequence': point['sequence'],
                        'previousPointId': point['previous_point_id'],
                        'delta': json.loads(point['delta_json']) if point['delta_json'] else None,
                        'sentences': [f['sentence'] for f in facts],
                        'facts': facts, 'gaps': gaps, 'notDisplayed': unshown})
            return
        self._send({'error': 'unknown path'}, 404)

    def log_message(self, fmt, *args):
        sys.stderr.write('[preview] ' + (fmt % args) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--backend', default=adapt_facts.DEFAULT_BACKEND)
    parser.add_argument('--port', type=int, default=8711)
    args = parser.parse_args()
    Handler.database = args.db
    Handler.backend = args.backend
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print('preview server on http://127.0.0.1:%d  db=%s' % (args.port, args.db), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
