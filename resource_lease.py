"""Self-service exclusive local inference lease; no human approval gate.

The lock is a file created with O_EXCL. The commands are safe against the two
real races we have seen:

* two lanes checking `status` and then both loading a model: `acquire` is the
  atomic step; a status check is never a reservation;
* a lane releasing a lock it no longer owns (or a stale lock from a dead
  supervisor): `release` verifies the owner token/holder pid, and takeover of a
  stale lock is a guarded compare-and-swap, not a blind unlink.

Every mutation of an existing lock happens under a short guard file so a release
and a stale takeover cannot interleave. No model is involved in any of this.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
LOCK = ROOT / 'resources/local-inference.lock'
GUARD = ROOT / 'resources/local-inference.guard'
DEFAULT_TTL_SECONDS = 1800


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _read_record():
    try:
        return json.loads(LOCK.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except Exception:
        return {'status': 'corrupt', 'raw': LOCK.read_text(encoding='utf-8', errors='replace')[:500]}


def _pid_alive(pid):
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) can raise SystemError on Windows; use the Win32 API.
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # ACCESS_DENIED: live but protected
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, SystemError):
        return False


def _age_seconds(record):
    stamp = record.get('acquiredAt')
    if not stamp:
        return None
    try:
        acquired = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return (_now() - acquired).total_seconds()


def _stale_reason(record, ttl_seconds):
    if not isinstance(record, dict):
        return None
    if record.get('status') == 'corrupt':
        return 'corrupt record'
    holder = record.get('holderPid')
    if holder:
        return None if _pid_alive(holder) else f'holder pid {holder} is not alive'
    age = _age_seconds(record)
    if age is not None and age > ttl_seconds:
        return f'age {age:.0f}s exceeds ttl {ttl_seconds}s'
    return None


class Guard:
    """Short exclusive guard around a read-modify-write of the lock file."""

    def __init__(self, timeout_seconds=5.0):
        self.timeout = timeout_seconds
        self.fd = None

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        GUARD.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(GUARD, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise SystemExit('lease guard is held by another process')
                time.sleep(0.02)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            GUARD.unlink()
        except FileNotFoundError:
            pass
        return False


def acquire(lane, purpose, ttl_seconds, token=None, holder_pid=None):
    # The holder must be the long-lived driver, not this short-lived CLI process:
    # using os.getpid() here made every fresh lock look dead the moment the
    # command returned, which is exactly how two lanes once both "acquired".
    if holder_pid is None:
        holder_pid = os.environ.get('JITY_PI_SUPERVISOR_PID') or None
    record = {
        'lane': lane,
        'purpose': purpose,
        'acquiredAt': _now().isoformat(),
        'supervisorPid': os.environ.get('JITY_PI_SUPERVISOR_PID'),
        'holderPid': int(holder_pid) if holder_pid else None,
        'token': token or uuid.uuid4().hex,
    }
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        with LOCK.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False)
        return {'status': 'acquired', **record}
    except FileExistsError:
        pass

    current = _read_record()
    reason = _stale_reason(current, ttl_seconds)
    if reason is None:
        return {'status': 'busy', 'holder': current}
    # Guarded compare-and-swap: only replace the exact stale record we saw.
    with Guard():
        current_now = _read_record()
        if current_now != current:
            return {'status': 'busy', 'holder': current_now, 'note': 'lock changed during takeover'}
        reason_now = _stale_reason(current_now, ttl_seconds)
        if reason_now is None:
            return {'status': 'busy', 'holder': current_now}
        tmp = LOCK.with_suffix('.takeover')
        tmp.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        try:
            os.replace(tmp, LOCK)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        return {'status': 'acquired', 'takeover': reason, **record}


def release(lane, token=None):
    lock_record = _read_record()
    if lock_record is None:
        return {'status': 'free'}
    if lock_record.get('status') == 'corrupt':
        return {'status': 'refused', 'reason': 'corrupt lock; take over with acquire'}
    if lock_record.get('lane') != lane:
        return {'status': 'refused', 'reason': 'another lane holds the lease', 'holder': lock_record}
    recorded_token = lock_record.get('token')
    if recorded_token:
        if token != recorded_token:
            return {'status': 'refused', 'reason': 'owner token mismatch', 'holder': lock_record}
    else:
        holder = lock_record.get('holderPid') or lock_record.get('supervisorPid')
        if holder and int(holder) not in (os.getpid(), int(os.environ.get('JITY_PI_SUPERVISOR_PID') or 0)):
            return {'status': 'refused', 'reason': 'holder pid mismatch', 'holder': lock_record}
    with Guard():
        current = _read_record()
        if current != lock_record:
            return {'status': 'refused', 'reason': 'lock changed during release', 'holder': current}
        try:
            LOCK.unlink()
        except FileNotFoundError:
            return {'status': 'free'}
    return {'status': 'released'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['acquire', 'release', 'status'])
    parser.add_argument('--lane', default=os.environ.get('JITY_PI_LANE'))
    parser.add_argument('--purpose', default='targeted local inference')
    parser.add_argument('--token', default=None)
    parser.add_argument('--ttl-seconds', type=int, default=DEFAULT_TTL_SECONDS)
    parser.add_argument('--holder-pid', type=int, default=None,
                        help='long-lived owner pid; defaults to JITY_PI_SUPERVISOR_PID')
    args = parser.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if args.action == 'status':
        record = _read_record()
        if record is None:
            print('{"status":"free"}')
            return
        reason = _stale_reason(record, args.ttl_seconds)
        print(json.dumps({'status': 'held', 'stale': reason, 'holder': record}, ensure_ascii=False))
        return
    if not args.lane:
        parser.error('--lane is required')
    if args.action == 'release':
        result = release(args.lane, args.token)
        print(json.dumps(result, ensure_ascii=False))
        if result['status'] == 'refused':
            sys.exit(3)
        return
    result = acquire(args.lane, args.purpose, args.ttl_seconds, args.token, args.holder_pid)
    print(json.dumps(result, ensure_ascii=False))
    if result['status'] != 'acquired':
        sys.exit(2)


if __name__ == '__main__':
    main()
