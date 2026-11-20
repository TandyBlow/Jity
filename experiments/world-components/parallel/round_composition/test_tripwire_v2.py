# Boundary tests for the real-batch tripwire (v2).
#
# The v1 runner implemented the pre-registered line wrongly: the registration
# says ">=3/10 samples fail the hard gates" (n5Pass <= 7) but the code used
# `< 7`, and port failures were counted by final sample instead of by call.
# These tests pin the registered text so the 384 batch cannot repeat it.
#
# Usage: python -X utf8 test_tripwire_v2.py

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from real_batch_v2 import tripwire  # noqa: E402

FAILURES = []


def check(cond, label):
    if not cond:
        FAILURES.append(label)


def main() -> int:
    # hard-gate failing SAMPLES: the line fires at 3, not at 4
    check(not tripwire(0, 0), "0 failures, 0 port calls -> no tripwire")
    check(not tripwire(2, 0), "2 failing samples -> no tripwire")
    check(tripwire(3, 0), "3 failing samples -> tripwire (registered >=3)")
    check(tripwire(10, 0), "10 failing samples -> tripwire")

    # port failures are counted by CALL, and the line fires at 2
    check(not tripwire(0, 1), "1 failing port call -> no tripwire")
    check(tripwire(0, 2), "2 failing port calls -> tripwire (registered >=2)")
    check(tripwire(0, 5), "5 failing port calls -> tripwire")

    # the two conditions are independent
    check(tripwire(3, 0) and tripwire(0, 2),
          "each condition alone can fire the line")
    check(not tripwire(1, 1), "1 + 1 stays below both lines")

    # boundary sanity: n5Pass <= 7 equals >=3 failing samples out of 10
    for n5_pass in range(0, 11):
        fails = 10 - n5_pass
        expected = fails >= 3 or False
        check(tripwire(fails, 0) == expected,
              f"n5Pass={n5_pass} -> fails={fails} must match >=3 rule")

    if FAILURES:
        print(f"FAIL ({len(FAILURES)})")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("PASS: tripwire boundaries (>=3 failing samples, >=2 failing port "
          "calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
