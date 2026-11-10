# -*- coding: utf-8 -*-
"""Forward a local TCP port to a compute node through the cluster login host.

The product engine runs locally (node + vite SSR); the model runs on a GPU node
that is not reachable from outside. This opens a paramiko direct-tcpip channel
through the login connection, so the local engine can POST to the model server
without exposing anything publicly.

    python hpc/forward.py --node hpcgpu01 --port 18080 --local-port 18080

Stop it with Ctrl-C; the channel and the local listener are closed together.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
import beats_job as B  # noqa: E402


def pump(source: socket.socket, target, name: str) -> None:
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            target.sendall(data)
    except OSError:
        pass
    finally:
        try:
            target.close()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", required=True)
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--local-port", type=int, default=18080)
    parser.add_argument("--probe", action="store_true", help="exit after one successful health check")
    args = parser.parse_args()

    h = B.hpc()
    transport = h.c.get_transport()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", args.local_port))
    listener.listen(16)
    print(json.dumps({"forwarding": f"127.0.0.1:{args.local_port} -> {args.node}:{args.port}"}),
          flush=True)

    def serve() -> None:
        while True:
            client, _ = listener.accept()
            try:
                channel = transport.open_channel(
                    "direct-tcpip", (args.node, args.port), client.getpeername()[:2])
            except Exception as error:  # noqa: BLE001 - report and drop this connection
                print(json.dumps({"channelFailed": str(error)}), flush=True)
                client.close()
                continue
            threading.Thread(target=pump, args=(client, channel, "up"), daemon=True).start()
            threading.Thread(target=pump, args=(channel, client, "down"), daemon=True).start()

    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
