"""Shared bits for Side FXy's hardware test groups (hardware/tests/test_*.py).

Each group is one script, run from this folder:  python test_<group>.py
It prints one line per check (PASS / FAIL, its name, expected against
actual) and a summary line, and exits 1 if any check failed.
run_tests.py runs every group.

The tests only read. circuit.py and the other tools are imported, the
committed exports are opened as zip files; nothing in tools/, easyeda/,
panel/, bom/, docs/ or firmware/ is written. A failing check is a finding
about the design, the boards, the firmware or the docs, not a broken test.

What is here
  paths       MODULE, TOOLS, EASYEDA, PANEL, BOM, DOCS, FIRMWARE, ROUTED, GENERATED
  load()      a module from hardware/tools by name ('circuit', 'pcb', 'copper_audit', 'panel', ...)
  ohms(), farads(), db()
  text()      a file under side-fx/ as text (design.md, bom.md, firmware sources ...)
  read_export()   {doc uuid: {"docType", "recs": [(header, payload)]}} of an .epro2, cached
  routed()    the routed master as a Routed object: .main / .face (copper_audit.RoutedBoard: parts with
              their pads in the board frame, tracks, vias, pour islands, holes, outline), .panel (the raw
              panel PCB doc), .docs, and helpers for footprints, devices and symbols
  Checks      check() / close() / within() one claim at a time; done() prints the summary and exits
"""
import collections
import importlib.util
import json
import math
import os
import sys

sys.dont_write_bytecode = True          # importing the tools must not leave __pycache__ in tools/
for _s in (sys.stdout, sys.stderr):     # the groups print µ, Ω, ±; a Windows console defaults to cp1252
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.normpath(os.path.join(HERE, "..", ".."))          # side-fx/
TOOLS = os.path.join(MODULE, "hardware", "tools")
EASYEDA = os.path.join(MODULE, "hardware", "easyeda")
PANEL = os.path.join(MODULE, "hardware", "panel")
BOM = os.path.join(MODULE, "hardware", "bom")
DOCS = os.path.join(MODULE, "docs")
FIRMWARE = os.path.join(MODULE, "firmware")
REPO = os.path.normpath(os.path.join(MODULE, ".."))
GENERATED = os.path.join(EASYEDA, "SideFXy.epro2")                # what easyeda_export.py writes
ROUTED = os.path.join(EASYEDA, "SideFXy-routed.epro2")           # the layout master boards are ordered from
MIL = 0.0254                                                       # EasyEDA Pro coordinates are in mil

BOARD_TITLES = {"main": "SideFXy Main PCB", "face": "SideFXy Faceplate PCB", "panel": "SideFXy Panel PCB"}

_loaded = {}


def load(name):
    """A module from hardware/tools by name ('circuit', 'pcb', 'copper_audit', ...), loaded once."""
    if name not in _loaded:
        if TOOLS not in sys.path:
            sys.path.insert(0, TOOLS)
        spec = importlib.util.spec_from_file_location("sidefx_test_" + name, os.path.join(TOOLS, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _loaded[name] = mod
    return _loaded[name]


def ohms(v):
    """'100k' -> 1e5, '1k5' -> 1500, '23k2' -> 23200, '470' -> 470, '10R' -> 10, 'B10k' -> the pot's track."""
    v = v.lstrip("AB")
    for unit, mul in (("k", 1e3), ("R", 1.0), ("M", 1e6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


def farads(v):
    """'22p' -> 22e-12, '100n' -> 1e-7, '1u' -> 1e-6, '4n7' -> 4.7e-9."""
    for unit, mul in (("p", 1e-12), ("n", 1e-9), ("u", 1e-6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


def db(x):
    return 20 * math.log10(abs(x)) if x else float("-inf")


def text(*parts):
    """A file under side-fx/ as text: text('docs', 'design.md'), text('firmware', 'src', 'hal_daisy.cc')."""
    with open(os.path.join(MODULE, *parts), encoding="utf-8") as f:
        return f.read()


_exports = {}


def read_export(path=ROUTED):
    """{doc uuid: {"docType": ..., "recs": [(header, payload), ...]}} of an .epro2 (copper_audit's parser), cached."""
    if path not in _exports:
        _exports[path] = load("copper_audit").read_export(path)
    return _exports[path]


def meta(doc):
    return next((p for h, p in doc["recs"] if h["type"] == "META"), {})


def rid(h):
    """A record id that may be a JSON list (PAD_NET, POURED)."""
    i = h.get("id")
    if isinstance(i, str) and i.startswith("["):
        return json.loads(i)
    return i


class Routed:
    """The routed master (or any export with the same three boards).

    .main, .face   copper_audit.RoutedBoard: .parts {ref: {"x", "y", "angle", "bottom", "fp" (title), "cid",
                   "pads" {num: Pad (board frame, .x .y .w .h .shape .net)}, "nets", "body" (bbox)}},
                   .tracks [{"a", "b", "w", "layer", "net"}], .vias [{"c", "r", "net"}], .islands, .spokes,
                   .holes [(x, y, d)], .outline (x1, y1, x2, y2)
    .panel         the panel PCB doc (raw records)
    .pcb_docs      {"main" | "face" | "panel": raw PCB doc}
    .fp_docs       {footprint title: raw FOOTPRINT doc};  .fp_by_uuid {uuid: raw doc}
    .attrs(board, ref)   every ATTR of a placed component {key: value} (Designator, Footprint, Device, ...)
    .device(board, ref)  the DEVICE doc's META attributes the component was placed from
    .symbol_pins(uuid)   {pin number: (pin name, x, y, partId)} of a SYMBOL doc
    """

    def __init__(self, path=ROUTED):
        ca = load("copper_audit")
        pcbmod = load("pcb")
        self.path = path
        self.docs = read_export(path)
        self.fp_by_uuid = {u: d for u, d in self.docs.items() if d["docType"] == "FOOTPRINT"}
        self.fp_docs = {meta(d).get("title"): d for d in self.fp_by_uuid.values()}
        fps = {}
        for u, d in self.fp_by_uuid.items():
            g = dict(pcbmod.footprint_geometry(d), title=meta(d).get("title"))
            for h, p in d["recs"]:
                if h["type"] == "PAD" and p:
                    g["pads"][str(p["num"])]["shape"] = p["defaultPad"]["padType"]
            fps[u] = g
        self.fp_geo = fps
        self.pcb_docs = {}
        for u, d in self.docs.items():
            if d["docType"] == "PCB":
                t = meta(d).get("title")
                for k, want in BOARD_TITLES.items():
                    if t == want:
                        self.pcb_docs[k] = d
        self.main = ca.RoutedBoard(BOARD_TITLES["main"], self.pcb_docs["main"], fps)
        self.face = ca.RoutedBoard(BOARD_TITLES["face"], self.pcb_docs["face"], fps)
        self.panel = self.pcb_docs.get("panel")
        self.devices = {u: meta(d).get("attributes", {}) for u, d in self.docs.items() if d["docType"] == "DEVICE"}
        self._attrs = {}
        for k in ("main", "face"):
            a = collections.defaultdict(dict)
            for h, p in self.pcb_docs[k]["recs"]:
                if h["type"] == "ATTR" and p and p.get("parentId"):
                    a[p["parentId"]][p["key"]] = p["value"]
            self._attrs[k] = a

    def board(self, k):
        return {"main": self.main, "face": self.face}[k]

    def attrs(self, board, ref):
        return self._attrs[board][self.board(board).parts[ref]["cid"]]

    def device(self, board, ref):
        return self.devices.get(self.attrs(board, ref).get("Device"), {})

    def symbol_pins(self, uid):
        pins, out = {}, {}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "PIN" and p:
                pins[h["id"]] = {"x": p["x"], "y": p["y"], "part": p.get("partId")}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "ATTR" and p and p.get("parentId") in pins:
                pins[p["parentId"]][p["key"]] = p["value"]
        for pid, q in pins.items():
            out[q.get("Pin Number")] = (q.get("Pin Name"), q["x"], q["y"], q["part"])
        return out


_routed = {}


def routed(path=ROUTED):
    """The routed master as a Routed object (built once per path)."""
    if path not in _routed:
        _routed[path] = Routed(path)
    return _routed[path]


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

    def within(self, name, actual, lo, hi, unit="", why=""):
        """lo <= actual <= hi (None = unbounded on that side)."""
        ok = (lo is None or actual >= lo) and (hi is None or actual <= hi)
        rng = f"{'-inf' if lo is None else f'{lo:.4g}'} .. {'+inf' if hi is None else f'{hi:.4g}'}{unit}"
        return self.check(name, ok, f"expected {rng}, got {actual:.4g}{unit}" + (f" ({why})" if why else ""))

    def done(self):
        print(f"== {self.group}: {self.n} checks, {len(self.failed)} failed"
              + (f" ({', '.join(self.failed)})" if self.failed else ""), flush=True)
        sys.exit(1 if self.failed else 0)
