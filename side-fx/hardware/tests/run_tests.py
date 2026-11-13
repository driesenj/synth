"""Run every test group of Side FXy and sum them up.

Run from side-fx/hardware/tests:  python run_tests.py [group ...]
Exit code 1 if any group failed. A failing check is a finding about the
design, the boards or the docs (see each group's header).
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # the groups print −, µ, Ω
except (AttributeError, ValueError):
    pass


def main(groups):
    files = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if groups:
        files = [f for f in files if os.path.basename(f)[5:-3] in groups]
    total = failed = 0
    bad = []
    env = dict(os.environ, PYTHONIOENCODING="utf-8")       # the groups print µ, Ω, ±
    for f in files:
        r = subprocess.run([sys.executable, "-B", f], cwd=HERE, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
        out = r.stdout + r.stderr
        m = re.search(r"^== (\S+): (\d+) checks, (\d+) failed", out, re.M)
        name = os.path.basename(f)[:-3]
        if not m:
            print(f"{name}: did not finish (exit {r.returncode})\n{out[-2000:]}")
            bad.append(name)
            continue
        n, k = int(m.group(2)), int(m.group(3))
        total, failed = total + n, failed + k
        print(f"{name:24s} {n:5d} checks, {k:3d} failed")
        for line in out.splitlines():
            if line.startswith("FAIL"):
                print("    " + line)
        if k or r.returncode:
            bad.append(name)
    print(f"== all: {total} checks in {len(files)} groups, {failed} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
