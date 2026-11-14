"""Shared bits for the stereo mixer's test groups (hardware/tests/test_*.py).

Each group is one script, run from this folder:  python test_<group>.py
It prints one line per check (PASS / FAIL, its name, expected against
actual) and a summary line, and exits 1 if any check failed.
run_tests.py runs every group.

The tests only read. circuit.py and the other tools are imported, the
committed exports are opened as zip files; nothing in tools/, easyeda/,
panel/, bom/ or docs/ is written. A failing check is a finding about the
design, the boards or the docs, not a broken test.
"""
import importlib.util
import os
import sys

sys.dont_write_bytecode = True          # importing the tools must not leave __pycache__ in tools/

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.normpath(os.path.join(HERE, "..", ".."))          # stereo-mixer/
TOOLS = os.path.join(MODULE, "hardware", "tools")
EASYEDA = os.path.join(MODULE, "hardware", "easyeda")
PANEL = os.path.join(MODULE, "hardware", "panel")
GENERATED = os.path.join(EASYEDA, "StereoMixer.epro2")             # what easyeda_export.py writes
ROUTED = os.path.join(EASYEDA, "StereoMixer-routed.epro2")         # the layout master boards are ordered from

_loaded = {}


def load(name):
    """A module from hardware/tools by name ('circuit', 'pcb', 'copper_audit', ...), loaded once."""
    if name not in _loaded:
        if TOOLS not in sys.path:
            sys.path.insert(0, TOOLS)
        spec = importlib.util.spec_from_file_location("mixer_" + name, os.path.join(TOOLS, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _loaded[name] = mod
    return _loaded[name]


def ohms(v):
    """'100k' -> 1e5, '1k5' -> 1500, '10R' -> 10, 'A100k' / 'B10k' -> the pot's track."""
    v = v.lstrip("AB")
    for unit, mul in (("k", 1e3), ("R", 1.0), ("M", 1e6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


def farads(v):
    """'22p' -> 22e-12, '100n' -> 1e-7, '1u' / '10u' -> 1e-6 / 1e-5, '4n7' -> 4.7e-9."""
    for unit, mul in (("p", 1e-12), ("n", 1e-9), ("u", 1e-6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


def read_export(path=ROUTED):
    """{doc uuid: {"docType": ..., "recs": [(header, payload), ...]}} of an .epro2 (copper_audit's parser)."""
    return load("copper_audit").read_export(path)


def db(x):
    import math
    return 20 * math.log10(abs(x)) if x else float("-inf")


class Checks:
    """check() one claim at a time; done() prints the summary and exits."""

    def __init__(self, group):
        self.group, self.n, self.failed = group, 0, []

    def check(self, name, ok, detail=""):
        self.n += 1
        if not ok:
            self.failed.append(name)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""), flush=True)
        return ok

    def close(self, name, actual, expected, tol, unit=""):
        """|actual - expected| <= tol."""
        return self.check(name, abs(actual - expected) <= tol,
                          f"expected {expected:.4g}{unit} +- {tol:.3g}, got {actual:.4g}{unit}")

    def done(self):
        print(f"== {self.group}: {self.n} checks, {len(self.failed)} failed"
              + (f" ({', '.join(self.failed)})" if self.failed else ""), flush=True)
        sys.exit(1 if self.failed else 0)
