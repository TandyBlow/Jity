"""Fail closed if a live capture attempts networking outside its recorder."""
from contextlib import contextmanager
import sys

_active = 0
_installed = False


def _audit(event, args):
    if not _active:
        return
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
        from .transport import network_allowed, network_dns_hosts
        host = args[0].decode() if event == "socket.getaddrinfo" and isinstance(args[0], bytes) else args[0] if event == "socket.getaddrinfo" else None
        permitted_dns = event == "socket.getaddrinfo" and network_dns_hosts.get(host, 0) > 0
        if not network_allowed.get() and not permitted_dns:
            from .journal import CaptureBoundaryError
            raise CaptureBoundaryError("Unrecorded network operation blocked: " + event)
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
        from .journal import CaptureBoundaryError
        raise CaptureBoundaryError("Unrecorded subprocess blocked during capture: " + event)


@contextmanager
def capture_network_guard():
    global _installed, _active
    if not _installed:
        sys.addaudithook(_audit)
        _installed = True
    _active += 1
    try:
        yield
    finally:
        _active -= 1
