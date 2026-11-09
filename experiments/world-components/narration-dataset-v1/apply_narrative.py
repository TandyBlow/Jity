"""Put a hand-written narrative into an existing dataset row.

The rows are produced by generator scripts; this tool overwrites only the
叙事 field of a named row file with the contents of a text file, so a target
text can be revised without re-running (and re-seeding) the whole generator.

usage: python apply_narrative.py <row.jsonl> <narrative.txt>
"""

import io
import json
import sys


def main():
    row_path, text_path = sys.argv[1], sys.argv[2]
    text = io.open(text_path, encoding="utf-8").read().strip()
    row = json.loads(io.open(row_path, encoding="utf-8").read())
    if "叙事" not in row:
        raise SystemExit("row has no 叙事 field")
    row["叙事"] = text
    with io.open(row_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{row_path}: 叙事 replaced ({len(text)} chars)")


if __name__ == "__main__":
    main()
