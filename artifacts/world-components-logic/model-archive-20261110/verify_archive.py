"""Verify archived training files without loading or executing model weights."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
failures = []
for row in manifest["files"]:
    path = root / row["archivePath"]
    if not path.is_file() or path.stat().st_size != row["bytes"]:
        failures.append(row["archivePath"])
        continue
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != row["sha256"]:
        failures.append(row["archivePath"])
if failures:
    raise SystemExit("Archive verification failed: " + ", ".join(failures))
print(f"Verified {len(manifest['files'])} archived files.")
