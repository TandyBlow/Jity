#!/usr/bin/env python3
"""Run the novel→campaign pipeline on prepared TXT files.

Usage:
  python scripts/run_novel_pipeline.py [novel_name]

Examples:
  python scripts/run_novel_pipeline.py 龙族Ⅰ_火之晨曦
  python scripts/run_novel_pipeline.py          # process all novels

Requires: backend running (uvicorn app.main:app --port 8000)
          DEEPSEEK_API_KEY configured in backend/.env
"""
import subprocess
import sys
from pathlib import Path

NOVELS_DIR = Path("backend/data/novels")
NOVELS = [
    "龙族Ⅰ_火之晨曦",
    "龙族Ⅱ_悼亡者之瞳",
    "龙族Ⅲ_黑月之潮",
]

API_URL = "http://localhost:8000"


def run_pipeline(novel_name: str) -> bool:
    txt_path = NOVELS_DIR / f"{novel_name}.txt"
    if not txt_path.exists():
        print(f"  SKIP: {txt_path} not found")
        return False

    print(f"  Processing: {novel_name} ({txt_path.stat().st_size:,} bytes)")
    result = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"{API_URL}/campaigns/generate-from-novel",
         "-F", f"file=@{txt_path}"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"  ERROR: curl failed: {result.stderr[:200]}")
        return False

    print(f"  Response: {result.stdout[:300]}...")
    return True


def main():
    if len(sys.argv) > 1:
        targets = [sys.argv[1]]
    else:
        targets = NOVELS

    print(f"Novel→Campaign Pipeline")
    print(f"API: {API_URL}")
    print(f"Targets: {len(targets)} novel(s)")
    print()

    for name in targets:
        run_pipeline(name)
        print()

    print("Done. Check backend/data/campaigns/ for generated files.")
    print("Review each campaign in the curator: http://localhost:3000/curator")


if __name__ == "__main__":
    main()
