"""Restore the byte-exact large-file snapshot. Requires the zstd command."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true', help='Check the compressed contents without restoring files.')
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    repo = bundle.parents[2]
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if not shutil.which('zstd'):
        raise SystemExit('Install zstd first (macOS: brew install zstd), then rerun this command.')
    whole = hashlib.sha256()
    for part in manifest['parts']:
        path = bundle / part['path']
        if not path.is_file() or path.stat().st_size != part['bytes']:
            raise SystemExit(f'Missing or incomplete part: {path}. Run git lfs pull first.')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(chunk)
                whole.update(chunk)
        if digest.hexdigest() != part['sha256']:
            raise SystemExit(f'Part checksum mismatch: {path}')
    if whole.hexdigest() != manifest['archiveSha256']:
        raise SystemExit('Combined archive checksum mismatch.')
    expected = {row['path']: row for row in manifest['files']}
    process = subprocess.Popen(['zstd', '-dc', '--long=31'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    feeder_errors = []

    def feed():
        try:
            with process.stdin:
                for part in manifest['parts']:
                    with (bundle / part['path']).open('rb') as stream:
                        shutil.copyfileobj(stream, process.stdin, 8 * 1024 * 1024)
        except Exception as error:
            feeder_errors.append(error)

    thread = threading.Thread(target=feed, daemon=True)
    thread.start()
    seen = set()
    try:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                if not member.isfile() or member.name not in expected or member.name in seen:
                    raise RuntimeError(f'Unexpected archive member: {member.name}')
                row = expected[member.name]
                if member.size != row['bytes']:
                    raise RuntimeError(f'Archive size mismatch: {member.name}')
                target = (repo / member.name).resolve()
                if repo not in target.parents:
                    raise RuntimeError(f'Invalid archive path: {member.name}')
                exists = target.exists()
                if not args.verify_only and exists and (not target.is_file() or target.stat().st_size != row['bytes'] or file_hash(target) != row['sha256']):
                    raise RuntimeError(f'Refusing to overwrite a different existing file: {target}')
                temporary = None
                output = None
                if not args.verify_only and not exists:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    output = tempfile.NamedTemporaryFile(dir=target.parent, prefix='.restore-', delete=False)
                    temporary = Path(output.name)
                try:
                    digest = hashlib.sha256()
                    stream = archive.extractfile(member)
                    for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                        digest.update(chunk)
                        if output:
                            output.write(chunk)
                    if output:
                        output.close()
                    if digest.hexdigest() != row['sha256']:
                        raise RuntimeError(f'Archive content mismatch: {member.name}')
                    if temporary:
                        if target.exists():
                            raise RuntimeError(f'Target appeared during restore; preserving it: {target}')
                        os.replace(temporary, target)
                        temporary = None
                    seen.add(member.name)
                finally:
                    if output and not output.closed:
                        output.close()
                    if temporary:
                        temporary.unlink(missing_ok=True)
        thread.join()
        if process.wait() or feeder_errors or seen != set(expected):
            raise RuntimeError('Incomplete archive or decompression failure.')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
    print(f"{'Verified' if args.verify_only else 'Restored/verified'} {len(seen)} large files; original bytes and paths are preserved.")


if __name__ == '__main__':
    main()
