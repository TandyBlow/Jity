"""Fail-closed execution boundary for locally imported Jity components."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys


class ReplayBoundaryError(BaseException):
    """Bypass Jity's broad Exception fallbacks; caught at the evaluator boundary."""


class MissingRecordedCall(ReplayBoundaryError):
    pass


class ForbiddenReplayOperation(ReplayBoundaryError):
    pass


_scopes = []
_installed = False


def _inside(path, roots):
    resolved = Path(os.fsdecode(path)).resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def _audit(event, args):
    if not _scopes:
        return
    roots = _scopes[-1]
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
        raise ForbiddenReplayOperation("回放禁止网络操作：" + event)
    if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
        raise ForbiddenReplayOperation("回放禁止启动外部进程：" + event)
    if event == "open":
        path, mode, flags = args
        if isinstance(path, (str, bytes, os.PathLike)):
            if Path(os.fsdecode(path)).name == ".env":
                raise ForbiddenReplayOperation("回放禁止读取 .env")
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not _inside(os.fsdecode(path), roots):
                raise ForbiddenReplayOperation("回放写入超出独立运行目录：" + os.fsdecode(path))
    elif event == "sqlite3.connect":
        path = os.fsdecode(args[0])
        if path != ":memory:" and not _inside(path, roots):
            raise ForbiddenReplayOperation("回放数据库必须位于独立运行目录")
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate"}:
        if isinstance(args[0], (str, bytes, os.PathLike)) and not _inside(os.fsdecode(args[0]), roots):
            raise ForbiddenReplayOperation("回放文件操作超出独立运行目录：" + event)
    elif event in {"os.rename", "os.link", "os.symlink"}:
        for path in args[:2]:
            if isinstance(path, (str, bytes, os.PathLike)) and not _inside(os.fsdecode(path), roots):
                raise ForbiddenReplayOperation("回放文件移动超出独立运行目录：" + event)


@contextmanager
def replay_sandbox(jity_root: Path, run_dir: Path):
    """Local imports are allowed; network, .env and out-of-run writes are denied.

    This process-wide Python audit guard is an accidental-side-effect barrier,
    not a security sandbox for hostile native code. Use in a dedicated CLI process.
    """
    global _installed
    root = Path(jity_root).resolve()
    backend = root / "backend"
    if not (backend / "app/services/memory/memory_controller/controller.py").is_file():
        raise ValueError("不是有效的 Jity checkout：" + str(root))
    run_dir = Path(run_dir).resolve()
    if run_dir == root or root in run_dir.parents:
        raise ValueError("回放运行目录不能位于 Jity 中")
    run_dir.mkdir(parents=True, exist_ok=True)
    if not _installed:
        sys.addaudithook(_audit)
        _installed = True
    # Refuse an already-imported app from another checkout.
    imported = sys.modules.get("app")
    if imported is not None and getattr(imported, "__file__", None):
        if not _inside(imported.__file__, [backend]):
            raise ValueError("当前进程已加载其他 app；请使用独立进程运行回放")
    old_path = list(sys.path)
    old_bytecode = sys.dont_write_bytecode
    sys.path.insert(0, str(backend))
    sys.dont_write_bytecode = True
    _scopes.append([run_dir])
    try:
        yield
    finally:
        _scopes.pop()
        sys.dont_write_bytecode = old_bytecode
        sys.path[:] = old_path


def code_fingerprint(jity_root: Path):
    import hashlib
    root = Path(jity_root).resolve()
    records = {}
    for path in sorted((root / "backend/app").rglob("*.py")):
        records[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not records:
        raise ValueError("Jity 源码目录为空")
    from ..storage import digest
    return {"sha256": digest(records), "files": records}
