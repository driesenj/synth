"""Senay as an EasyEDA Pro project (.epro2): schematic pages, both PCBs placed
(not routed), and the panel PCB.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the
file format, the connectivity check and the previews, the way Side FXy does.
Library parts come from the two caches of your MorrisSynth export (resistor,
capacitor, diode, TL074 and pot symbols, the WQP518MA jack, the 2x8 box
header, net ports, ground flag, sheet frame). Generated here:

  footprints  SMD: 0603 / 0805 / 1206 chips, SOIC-14, SOIC-16, SOT-23 (pads
              named B / E / C), SOD-123, SOT-89, in the pad format of your
              library's SOIC-16 and SOT-23; through-hole: DIP-16 (7.62 mm
              rows), Bourns 3296W, the sub-mini toggle, 3 mm LED, 1xN headers,
              the Alpha 9 mm pot (the mixer's)
  symbols     AS3340, LM13700, MMBT3904, trimmer, 78L05 / 79L05, toggle, LED,
              headers

Pages: one per channel (oscillator + its modifier), the noise bank, power and
headers, the faceplate. Every pin ends in a net port (or a ground flag) with
its net's name, so parts sit in blocks without wires between them; same name
= same net within a board, and the header pins carry the nets across.

Run from sena/hardware/tools:  python easyeda_export.py
"""
import collections
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAITSY = os.path.normpath(os.path.join(HERE, "..", "..", "..", "plaitsy", "hardware", "tools"))
sys.path.insert(0, PLAITSY)
import easyeda_export as ee                      # noqa: E402  (the Plaitsy exporter)
sys.path.remove(PLAITSY)

from easyeda_export import (Doc, Symbol, Page, Project, meta, attr_payload, Y, render, check,   # noqa: E402
                            new_uuid, W, H)

LIBFILES = [os.path.join(PLAITSY, "..", "easyeda", "morrissynth-parts.epru"),
            os.path.normpath(os.path.join(HERE, "..", "..", "..", "stereo-mixer", "hardware", "easyeda",
                                          "stereo-mixer-parts.epru"))]


def _load(name):
    spec = importlib.util.spec_from_file_location("sena_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")

NAME = "Senay"
OUT = os.path.join(HERE, "..", "easyeda", "Senay.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "senay-easyeda-{}.png")
MIL = 1 / 0.0254

DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0 (its symbol and attributes)
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00 (its symbol)
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "POT": "be9d2c8f5f814271a402f956f18b56f9",       # PTV09A-4025F-B103 (its symbol)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819 (its symbol: 1 = cathode)
    "HDR16": "bbe47e9fd91b42bbaf0d36b9504a3a5e",     # DC3-2.54-16PAS, 2x8 box header
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV

# ---------------------------------------------------------------- footprints
LAYERS = [(1, "TOP", "Top Layer", "#FF0000", "#7F0000"), (2, "BOTTOM", "Bottom Layer", "#0000FF", "#00007F"),
          (3, "TOP_SILK", "Top Silkscreen Layer", "#FFCC00", "#7F6600"),
          (4, "BOT_SILK", "Bottom Silkscreen Layer", "#66CC33", "#336619"),
          (7, "TOP_PASTE_MASK", "Top Paste Mask Layer", "#808080", "#404040"),
          (8, "BOT_PASTE_MASK", "Bottom Paste Mask Layer", "#800000", "#400000"),
          (5, "TOP_SOLDER_MASK", "Top Solder Mask Layer", "#800080", "#400040"),
          (6, "BOT_SOLDER_MASK", "Bottom Solder Mask Layer", "#AA00FF", "#55007F"),
          (13, "DOCUMENT", "Document Layer", "#FFFFFF", "#7F7F7F"),
          (11, "OUTLINE", "Board Outline Layer", "#FF00FF", "#7F007F"),
          (12, "MULTI", "Multi-Layer", "#C0C0C0", "#606060")]


class Footprint:
    """A footprint in mm, written as an EasyEDA Pro FOOTPRINT doc. Through-hole pads are round / square
    with round holes or oval with slots; SMD pads are rectangles on the top layer with no hole, as in
    your library's SOIC-16 and SOT-23."""

    def __init__(self, title, designator="U?"):
        self.title, self.designator = title, designator
        self.pads, self.silk = [], []
        self.doc = Doc("FOOTPRINT")

    def pad(self, num, x, y, hole=1.0, size=1.7, square=False, h=None, slot=None):
        self.pads.append((str(num), x, y, hole, size, h or size, square, slot, False))

    def smd(self, num, x, y, w, h):
        self.pads.append((str(num), x, y, None, w, h, True, None, True))

    def line(self, x1, y1, x2, y2):
        self.silk.append(("L", (x1, y1, x2, y2)))

    def rect(self, x1, y1, x2, y2):
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
            self.line(*a, *b)

    def circle(self, x, y, r):
        self.silk.append(("C", (x, y, r)))

    def build(self):
        d = self.doc
        for lid, typ, name, c1, c2 in LAYERS:
            d.add("LAYER", f'["LAYER",{lid}]', {"layerType": typ, "layerName": name, "use": True, "show": True,
                                                 "locked": False, "activeColor": c1, "activateTransparency": 1,
                                                 "inactiveColor": c2, "inactiveTransparency": 1})
        d.add("ACTIVE_LAYER", "ACTIVE_LAYER", {"layerId": 1})
        d.add("CANVAS", "CANVAS", {"originX": 0, "originY": 0, "unit": "mm", "gridXSize": 10, "gridYSize": 10,
                                   "snapXSize": 10, "snapYSize": 10, "gridType": "NONE", "multiGridType": "NONE",
                                   "highlightValue": 0.5})
        m = lambda v: round(v * MIL, 3)   # noqa: E731
        for kind, data in self.silk:
            if kind == "L":
                x1, y1, x2, y2 = data
                path = [m(x1), m(y1), "L", m(x2), m(y2)]
            else:
                x, y, r = data
                path = ["CIRCLE", m(x), m(y), m(r)]
            d.add("POLY", d.nid(), {"groupId": 0, "netName": "", "layerId": 3, "width": 6, "path": path,
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for num, x, y, hole, pw, ph, square, slot, smd in self.pads:
            if smd:
                pad, hl, layer = {"padType": "RECT", "width": m(pw), "height": m(ph), "radius": 0}, None, 1
            elif slot:
                pad = {"padType": "OVAL", "width": m(pw), "height": m(ph)}
                hl, layer = {"holeType": "SLOT", "width": m(slot[0]), "height": m(slot[1])}, 12
            else:
                pad = {"padType": "RECT", "width": m(pw), "height": m(ph), "radius": 0} if square else \
                      {"padType": "ELLIPSE", "width": m(pw), "height": m(ph)}
                hl, layer = {"holeType": "ROUND", "width": m(hole), "height": m(hole)}, 12
            d.add("PAD", d.nid(), {"groupId": 0, "netName": "", "layerId": layer, "num": num, "centerX": m(x),
                                   "centerY": m(y), "padAngle": 0, "hole": hl, "defaultPad": pad, "specialPad": [],
                                   "padOffsetX": 0, "padOffsetY": 0, "relativeAngle": 0, "plated": True,
                                   "padType": "NORMAL", "topSolderExpansion": None, "bottomSolderExpansion": None,
                                   "topPasteExpansion": None, "bottomPasteExpansion": None, "locked": False,
                                   "zIndex": d.zi(), "connectMode": None, "spokeSpace": None, "spokeWidth": None,
                                   "spokeAngle": None, "padLen": 0})
        for key, val in (("Footprint", self.title), ("Designator", self.designator)):
            d.add("ATTR", d.nid(), {"groupId": 0, "parentId": "", "layerId": 3, "x": None, "y": None, "key": key,
                                    "value": val, "keyVisible": False, "valueVisible": False,
                                    "fontFamily": "default", "fontSize": 40, "strokeWidth": 5, "bold": False,
                                    "italic": False, "origin": "LEFT_BOTTOM", "angle": 0, "reverse": False,
                                    "expansion": 0, "mirror": False, "locked": False, "zIndex": d.zi()})
        d.add("NET", '["NET",""]', {"netType": None, "specialColor": None, "retLine": True, "differentialName": None,
                                    "isPositiveNet": False, "equalLengthGroupName": None})
        return d.lines({"title": self.title, "description": "", "tags": [NAME],
                        "source": f"{new_uuid()}|{ee.USER['uuid']}"})


def fp_chip(size, prefix):
    """0603 / 0805 / 1206 two-terminal chip (IPC nominal lands), pad 1 at -x."""
    x, w, h, bx, by = {"0603": (0.8, 0.95, 1.0, 0.8, 0.4), "0805": (1.0, 1.1, 1.4, 1.0, 0.63),
                       "1206": (1.5, 1.2, 1.8, 1.6, 0.8)}[size]
    f = Footprint(f"{prefix}{size}", prefix + "?")
    f.smd(1, -x, 0, w, h)
    f.smd(2, x, 0, w, h)
    f.rect(-bx, -by, bx, by)
    return f


def fp_soic(n):
    """SOIC, 1.27 mm pitch, 150 mil body, pads 1.55 x 0.6 at +-2.7; pin 1 at the lower left, counting
    anticlockwise like the DIPs."""
    f = Footprint(f"SOIC-{n}-P1.27-W3.9", "U?")
    half = n // 2
    x0 = -(half - 1) * 0.635
    for i in range(half):
        f.smd(i + 1, x0 + i * 1.27, -2.7, 0.6, 1.55)
        f.smd(n - i, x0 + i * 1.27, 2.7, 0.6, 1.55)
    hx = half * 0.635 + 0.3
    f.rect(-hx, -1.95, hx, 1.95)
    f.circle(-hx + 0.7, -1.3, 0.25)
    return f


def fp_dip(n, title):
    """DIP on the standard 300 mil (7.62 mm) row pitch, pin 1 bottom-left, counting anticlockwise."""
    f = Footprint(title, "U?")
    half = n // 2
    x0 = -(half - 1) * 1.27
    for i in range(half):
        f.pad(i + 1, x0 + i * 2.54, -3.81, 0.9, 1.6, square=(i == 0))
        f.pad(n - i, x0 + i * 2.54, 3.81, 0.9, 1.6)
    hx, hy = half * 1.27 + 0.7, 3.25
    f.rect(-hx, -hy, hx, hy)
    f.circle(-hx + 0.9, -hy + 0.9, 0.3)
    return f


def fp_sot23():
    """SOT-23 for the MMBT3904: pad names are the pins' functions (1 B, 2 E, 3 C)."""
    f = Footprint("SOT-23-MMBT3904-BEC", "Q?")
    f.smd("B", -0.95, -1.1, 0.8, 1.0)
    f.smd("E", 0.95, -1.1, 0.8, 1.0)
    f.smd("C", 0.0, 1.1, 0.8, 1.0)
    f.rect(-1.45, -0.65, 1.45, 0.65)
    return f


def fp_sod123():
    f = Footprint("SOD-123", "D?")
    f.smd(1, -1.635, 0, 0.91, 1.22)          # cathode (the band)
    f.smd(2, 1.635, 0, 0.91, 1.22)
    f.rect(-1.35, -0.8, 1.35, 0.8)
    f.line(-0.9, -0.8, -0.9, 0.8)
    return f


def fp_sot89():
    """SOT-89-3: pins 1 and 3 at +-1.5, the middle pin and its tab as one pad 2."""
    f = Footprint("SOT-89-3", "U?")
    f.smd(1, -1.5, -1.9, 0.9, 1.3)
    f.smd(3, 1.5, -1.9, 0.9, 1.3)
    f.smd(2, 0.0, -0.4, 2.0, 4.3)
    f.rect(-2.25, -1.25, 2.25, 1.25)
    return f


def fp_3296w():
    """Bourns 3296W multi-turn trimmer, top adjust: pins 1-2-3 in a row, 2.54 mm; body 9.53 x 4.83."""
    f = Footprint("TRIM-3296W", "TR?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 0.8, 1.5, square=(i == 0))
    f.rect(-4.77, -1.15, 4.77, 3.68)
    f.circle(-3.4, 2.4, 0.9)                 # the adjust screw
    return f


def fp_toggle():
    """Sub-mini SPDT toggle with PCB pins (Dailywell 2MS1T1B1M2QES): pins 1-2-3 in a row, 2.54 mm, under
    the bushing (the origin); body 8.13 x 5.08 (Tayda's figures, check against the part)."""
    f = Footprint("TOGGLE-SUBMINI-SPDT-P2.54", "SW?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 1.0, 1.8, square=(i == 0))
    f.rect(-4.07, -2.54, 4.07, 2.54)
    f.circle(0, 0, 2.5)
    return f


def fp_led3():
    f = Footprint("LED-3MM-P2.54", "LED?")
    f.pad(1, -1.27, 0, 0.9, 1.6, square=True)      # anode
    f.pad(2, 1.27, 0, 0.9, 1.6)                    # cathode (flat side)
    f.circle(0, 0, 1.9)
    f.line(1.6, -1.0, 1.6, 1.0)
    return f


def fp_header(n):
    f = Footprint(f"HDR-1x{n}-P2.54", "H?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.25, -1.25, x0 + (n - 1) * 2.54 + 1.25, 1.25)    # 2.5 mm housing: columns 2.54 apart clear
    return f


def fp_alpha_pot():
    """Alpha 9 mm vertical pot (RD901F) in the frame of the library PTV09A footprint (the mixer's)."""
    f = Footprint("POT-ALPHA-9MM-RD901F", "RV?")
    for i, x in enumerate((-2.5, 0.0, 2.5)):
        f.pad(i + 1, x, -3.5, 1.0, 1.8, square=(i == 0))
    for num, x in (("4", -4.8), ("5", 4.8)):
        f.pad(num, x, 4.0, size=2.7, h=3.2, slot=(1.1, 1.8))
    f.rect(-4.75, -2.5, 4.75, 8.85)
    f.circle(0, 4.0, 3.5)
    return f


# ------------------------------------------------------------------ symbols
def ic_symbol(title, part_id, left, right, designator="U?", w=50):
    """Rectangular IC symbol; left/right = [(row, num, name)], rows 10 apart."""
    rows = max([r for r, _, _ in left + right]) + 1
    half = rows * 5
    s = Symbol(title, part_id, designator, [NAME])
    s.rect(-w, -half - 5, w, half + 5)
    for row, num, name in left:
        s.pin(num, name, -w - 10, -half + 5 + 10 * row, 0, show=True, edge=-w)
    for row, num, name in right:
        s.pin(num, name, w + 10, -half + 5 + 10 * row, 180, show=True, edge=w)
    return s


def as3340_symbol():
    left = [(0, "15", "FREQ CV"), (1, "13", "LIN FM / IREF"), (2, "14", "SCALE"), (3, "1", "SCALE 1"),
            (4, "2", "SCALE 2"), (5, "5", "PW"), (6, "6", "HARD SYNC"), (7, "9", "SOFT SYNC")]
    right = [(0, "10", "TRI"), (1, "8", "SAW"), (2, "4", "PULSE"), (3, "11", "CAP"), (4, "7", "HF TRACK"),
             (5, "16", "VCC"), (6, "12", "GND"), (7, "3", "VEE")]
    return ic_symbol("AS3340", "AS3340.1", left, right, w=60)


def lm13700_symbol():
    left = [(0, "3", "+IN A"), (1, "4", "-IN A"), (2, "1", "IABC A"), (3, "2", "DIODE A"), (4, "7", "BUF IN A"),
            (6, "14", "+IN B"), (7, "13", "-IN B"), (8, "16", "IABC B"), (9, "15", "DIODE B"), (10, "10", "BUF IN B")]
    right = [(0, "5", "OUT A"), (1, "8", "BUF OUT A"), (6, "12", "OUT B"), (7, "9", "BUF OUT B"),
             (9, "11", "V+"), (10, "6", "V-")]
    return ic_symbol("LM13700", "LM13700.1", left, right, w=60)


def reg_symbol(title, pins):
    """Three-terminal regulator: pins = {num: name}; IN left, OUT right, GND below."""
    s = Symbol(title, title + ".1", "U?", [NAME])
    s.rect(-30, -15, 30, 15)
    s.text(-14, -3, title, 7)
    names = {v: k for k, v in pins.items()}
    s.pin(names["IN"], "IN", -40, 0, 0, show=True, edge=-30)
    s.pin(names["OUT"], "OUT", 40, 0, 180, show=True, edge=30)
    s.pin(names["GND"], "GND", 0, 25, 90)
    return s


def npn_symbol():
    s = Symbol("MMBT3904", "NPN.2", "Q?", [NAME])
    s.poly([(-20, 0), (-5, 0)])
    s.poly([(-5, -12), (-5, 12)])
    s.poly([(-5, -4), (10, -14), (10, -20)])
    s.poly([(-5, 4), (10, 14), (10, 20)])
    s.poly([(10, 14), (3, 13), (6, 8), (10, 14)], closed=True, fill="#000000")
    s.pin("B", "B", -20, 0, 0)
    s.pin("C", "C", 10, -20, 90)
    s.pin("E", "E", 10, 20, 270)
    return s


def trimmer_symbol():
    s = Symbol("Trimmer", "TRIM.1", "TR?", [NAME])
    s.rect(-15, -5, 15, 5)
    s.poly([(0, 15), (0, 6)])
    s.poly([(-3, 9), (0, 5), (3, 9)], closed=True, fill="#000000")
    s.pin("1", "1", -25, 0, 0)
    s.pin("3", "3", 25, 0, 180)
    s.pin("2", "W", 0, 25, 90)
    return s


def toggle_symbol():
    """SPDT: common 2 in the middle below, throws 1 and 3 above."""
    s = Symbol("Toggle SPDT on-on", "SPDT.1", "SW?", [NAME])
    s.poly([(0, 10), (0, 2)])
    s.poly([(0, 2), (-8, -8)])
    s.poly([(-12, -10), (-10, -10)])
    s.poly([(10, -10), (12, -10)])
    s.pin("1", "1", -20, -10, 0)
    s.pin("3", "3", 20, -10, 180)
    s.pin("2", "C", 0, 20, 90)
    return s


def led_symbol():
    s = Symbol("LED 3mm", "LED3.1", "LED?", [NAME])
    s.poly([(-6, -6), (6, 0), (-6, 6), (-6, -6)], closed=True, fill="#FF0000")
    s.poly([(6, -6), (6, 6)])
    s.poly([(-12, 0), (-6, 0)])
    s.poly([(6, 0), (12, 0)])
    s.poly([(0, -9), (5, -14)])
    s.pin("1", "A", -22, 0, 0)
    s.pin("2", "K", 22, 0, 180)
    return s


def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.3", "H?", [NAME])
    half = n * 5
    s.rect(-10, -half - 5, 10, half + 5)
    for i in range(n):
        s.pin(str(i + 1), str(i + 1), -20, -half + 5 + 10 * i, 0, show=True, edge=-10)
    return s


# ------------------------------------------------------------------ project
class MPage(Page):
    page_count = "1"

    def place(self, ref, dev_key, *args, **kw):
        p = super().place(ref, dev_key, *args, **kw)
        self.comps[-1]["cid"] = next(h["id"] for h, _ in reversed(self.doc.recs) if h["type"] == "COMPONENT")
        return p

    def frame(self):
        d, pr = self.doc, self.pr
        cid = d.nid()
        sym = pr.sym_of("FRAME")
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": pr.symgeo[sym]["parts"][0],
                                 "groupId": "", "x": 0, "y": 0, "rotation": 0, "isMirror": False, "attrs": {}})
        today = ee.time.strftime("%Y-%m-%d")
        vals = [("Symbol", sym), ("@Project Name", NAME), ("@Page Count", self.page_count),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", NAME),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V0.1"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", NAME),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))

    def flag(self, x, y, rot, net):
        self._flag("GND", x, y, rot, net, True)


GROUNDS = ("GND", "GND_F")


def dev_of(part):
    k, v = part.kind, part.value
    return {"R": f"R_{v}", "C": f"C_{v}", "TRIM": f"TRIM_{v}", "POT": f"POT_{v}", "D4148": "D_1N4148W",
            "D5819": "D_1N5819HW", "ZENER": "D_BZT52C4V7", "TL074": "TL074S"}.get(k, k)


def chip_size(value):
    return {"10u": "1206", "1u": "0805"}.get(value, "0603")


class MProject(Project):
    def __init__(self, parts):     # noqa: super().__init__ would load only Plaitsy's library
        self.lib = {}
        for f in LIBFILES:
            self.lib.update(ee.parse(open(f, encoding="utf-8").read().split("\n")))
        self.symgeo = {u: ee.symbol_geometry(d) for u, d in self.lib.items() if d["docType"] == "SYMBOL"}
        self.devices = {k: (u, meta(self.lib[u])) for k, u in DEV.items()}
        self.new_docs = []
        self.uids, self.next_uid = {}, 2
        self._new_devices(parts)

    def device_attrs(self, key):
        return self.devices[key][1]["attributes"]

    def _footprint(self, fp):
        self.new_docs.append(("FOOTPRINT", fp.build()))
        return fp.doc.uuid

    def footprint_geo(self, uid):
        if not hasattr(self, "_fpgeo"):
            self._fpgeo = {}
            docs = {u: d for u, d in self.lib.items() if d["docType"] == "FOOTPRINT"}
            for typ, lines in self.new_docs:
                if typ == "FOOTPRINT":
                    docs.update(ee.parse(lines))
            for u, d in docs.items():
                self._fpgeo[u] = pcb.footprint_geometry(d)
        return self._fpgeo[uid]

    def _symbol(self, sym):
        lines = sym.build()
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(sym.doc.uuid, lines)
        return sym.doc.uuid

    def _new(self, key, symbol_uuid, fp_uuid, title, desig, desc, value=None):
        attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                 "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": symbol_uuid, "Footprint": fp_uuid,
                 "Supplier Part": "", "3D Model": "", "3D Model Title": "", "3D Model Transform": "",
                 "Description": desc}
        if value:
            attrs["Value"] = value
        self._device(key, title, attrs)

    def _new_devices(self, parts):
        fps = {s: {p: self._footprint(fp_chip(s, p)) for p in ("R", "C")} for s in ("0603", "0805", "1206")}
        fps.update({"SOIC14": self._footprint(fp_soic(14)), "SOIC16": self._footprint(fp_soic(16)),
                    "DIP16": self._footprint(fp_dip(16, "DIP-16-W7.62-P2.54")), "SOT23": self._footprint(fp_sot23()),
                    "SOD123": self._footprint(fp_sod123()), "SOT89": self._footprint(fp_sot89()),
                    "3296W": self._footprint(fp_3296w()), "TOGGLE": self._footprint(fp_toggle()),
                    "LED3": self._footprint(fp_led3()), "POT": self._footprint(fp_alpha_pot())})
        res_sym, cap_sym = self.device_attrs("R1k")["Symbol"], self.device_attrs("C100n")["Symbol"]
        diode = self.device_attrs("D5819")["Symbol"]
        trim_sym = self._symbol(trimmer_symbol())
        seen = set()
        for p in parts:
            key = dev_of(p)
            if key in seen or key in self.devices:
                continue
            seen.add(key)
            if p.kind == "R":
                self._new(key, res_sym, fps["0603"]["R"], f"0603 {p.value} 1%", "R?",
                          f"Thick film resistor {p.value} 1% 0603", p.value)
            elif p.kind == "C":
                size = chip_size(p.value)
                diel = "X7R" if p.value in ("100n", "1u", "10u") else "C0G"
                volts = "25V" if p.value == "10u" else "50V"
                self._new(key, cap_sym, fps[size]["C"], f"{size} {p.value} {volts} {diel}", "C?",
                          f"MLCC {p.value} {volts} {diel} {size}", p.value)
            elif p.kind in ("D4148", "D5819", "ZENER"):
                self._new(key, diode, fps["SOD123"], p.value, "D?" if p.kind != "ZENER" else "ZD?",
                          {"D4148": "Switching diode 1N4148W, SOD-123", "D5819": "Schottky 1N5819HW, 40 V 1 A, SOD-123",
                           "ZENER": "Zener 4.7 V, BZT52C4V7, SOD-123"}[p.kind])
            elif p.kind == "TRIM":
                self._new(key, trim_sym, fps["3296W"], f"3296W {p.value}", "TR?",
                          f"Bourns 3296W-1-xxxLF multi-turn trimmer {p.value}, top adjust", p.value)
            elif p.kind == "POT":
                a = dict(self.device_attrs("POT"))
                a.update({"Footprint": fps["POT"], "Manufacturer Part": f"Alpha RD901F {p.value}", "Value": p.value,
                          "Supplier Part": "", "Description": f"Alpha 9 mm vertical pot {p.value} (Thonk)"})
                self._device(key, f"Alpha 9mm {p.value}", a)
        for key, sym, fp, title, desig, desc in (
                ("AS3340", as3340_symbol(), fps["DIP16"], "AS3340", "U?",
                 "Alfa AS3340 (or AS3340A, CEM3340) VCO, DIP-16 in a socket"),
                ("LM13700", lm13700_symbol(), fps["SOIC16"], "LM13700M", "U?", "Dual OTA LM13700, SOIC-16"),
                ("78L05", reg_symbol("78L05", {"1": "OUT", "2": "GND", "3": "IN"}), fps["SOT89"], "78L05 SOT-89", "U?",
                 "+5 V 100 mA regulator, SOT-89: 1 OUT, 2 GND, 3 IN"),
                ("79L05", reg_symbol("79L05", {"1": "GND", "2": "IN", "3": "OUT"}), fps["SOT89"], "79L05 SOT-89", "U?",
                 "-5 V 100 mA regulator, SOT-89: 1 GND, 2 IN, 3 OUT"),
                ("NPN", npn_symbol(), fps["SOT23"], "MMBT3904", "Q?", "NPN MMBT3904, SOT-23: 1 B, 2 E, 3 C"),
                ("TOGGLE", toggle_symbol(), fps["TOGGLE"], "Sub-mini toggle SPDT on-on", "SW?",
                 "Sub-mini toggle SPDT on-on, PCB pins 2.54 mm (Dailywell 2MS1T1B1M2QES or equal)"),
                ("LED", led_symbol(), fps["LED3"], "LED 3mm", "LED?", "3 mm LED, red; 1 anode, 2 cathode (flat)")):
            self._new(key, self._symbol(sym), fp, title, desig, desc)
        a = dict(self.device_attrs("TL074"))
        a.update({"Footprint": fps["SOIC14"], "Manufacturer Part": "TL074CDT", "Supplier Part": "",
                  "Description": "Quad JFET op-amp, SOIC-14"})
        self._device("TL074S", "TL074 SOIC-14", a)
        for ref, kind, pins in circuit.HEADERS:
            n = len(pins)
            self._new(kind, self._symbol(header_symbol(n)), self._footprint(fp_header(n)), f"Pin header 1x{n}", "H?",
                      f"Board-to-board header 1x{n}, 2.54 mm: male on the faceplate, female on the main board")

    def write(self, boards, path, template):
        used = {u for u, m in self.devices.values()}
        refs = {m["attributes"].get(k) for u, m in self.devices.values() for k in ("Symbol", "Footprint")}
        keep = {"FOOTPRINT": refs, "SYMBOL": refs, "DEVICE": used}
        lines = []
        for typ in ("FOOTPRINT", "SYMBOL", "DEVICE"):
            for u, d in self.lib.items():
                if d["docType"] == typ and u in keep[typ]:
                    lines += d["lines"]
            lines += [l for t, ls in self.new_docs if t == typ for l in ls]
        for k, (title, pages, pcb_board) in enumerate(boards):
            board, sch = Doc("BOARD", new_uuid()[:16]), Doc("SCH")
            lines += board.lines({"title": title, "zIndex": k + 1})
            lines += sch.lines({"title": f"{title} Schema", "board": board.uuid, "zIndex": None})
            for pg in pages:
                lines += pg.lines(sch.uuid)
            lines += pcb_board.doc(ee, template, board.uuid, f"{title} PCB")
        lines += Doc("CONFIG", "CONFIG").lines({"defaultSheet": ""})
        lines += next(d for d in self.lib.values() if d["docType"] == "BLOB")["lines"]
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Vostok Sena clone: four AS3340 oscillators with sine fold, trapezoid, phase and "
                                  "PWM modifiers, white / pink / blue / brown noise. Two stacked PCBs, SMD, 14HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


# ------------------------------------------------------------------ schematic layout
class Flow:
    """Places part units left to right in rows on a page; every connected pin gets a short stub ending
    in a net port (or a ground flag), so the drawing carries the netlist without wires between parts."""

    LEFT, RIGHT, TOP, BOTTOM = 50, 1600, 95, 1090

    def __init__(self, pg):
        self.pg, self.x, self.y, self.row_h = pg, self.LEFT, self.TOP, 0

    def heading(self, s):
        if self.x > self.LEFT:
            self.newline()
        self.pg.text(self.LEFT, Y(self.y + 12), s, 11)
        self.y += 24

    def newline(self):
        self.x, self.y, self.row_h = self.LEFT, self.y + self.row_h + 8, 0

    def unit(self, part, unit=1, note=None):
        pg = self.pg
        key = dev_of(part)
        sym = pg.pr.sym_of(key)
        geo = pg.pr.symgeo[sym]
        pid = geo["parts"][unit - 1]
        pins = [(p["num"], p["x"], p["y"]) for p in geo["pins"] if p["part"] == pid]
        lab = lambda n: 6.5 * len(n) + 34     # noqa: E731  port flag and its name
        xs, ys = [x for _, x, _ in pins], [y for _, _, y in pins]
        bx1, bx2 = min(xs + [-15]), max(xs + [15])
        by1, by2 = min(ys + [-12]), max(ys + [12])
        left = max([lab(part.nets[n]) + 22 for n, x, y in pins if n in part.nets and x <= bx1 + 0.1] + [0])
        right = max([lab(part.nets[n]) + 22 for n, x, y in pins if n in part.nets and x > bx1 + 0.1] + [0])
        w = left + (bx2 - bx1) + right + 20
        h = (by2 - by1) + 34
        if self.x + w > self.RIGHT:
            self.newline()
        if self.y + h > self.BOTTOM:
            raise ValueError(f"page {pg.title} is full at {part.ref}")
        ox, oy = self.x + left - bx1, Y(self.y + 18 - by1)
        u = pg.place(part.ref, key, ox, oy, unit=unit, des=(bx1, by1 - 6, "LEFT_BOTTOM"),
                     value_at=(bx1, by2 + 16, "LEFT_BOTTOM"))
        for n, sx, sy in pins:
            net = part.nets.get(n)
            if not net:
                continue
            px, py = u[n]
            side = "left" if sx <= bx1 + 0.1 else "right"
            if abs(sx) < 0.1 and abs(sy) > 0.1:        # a pin pointing up or down: bend it to the right
                step = -10 if sy < 0 else 10
                if net in GROUNDS:
                    self._ground((px, py), net, "up" if sy < 0 else "down")
                    continue
                pg.wire([(px, py), (px, py + step), (px + 20, py + step)], net)
                pg.port(px + 20, py + step, net, "OUT", "right")
                continue
            if net in GROUNDS:
                self._ground((px, py), net, side)
            else:
                pg.stub_port((px, py), net, "IN" if side == "left" else "OUT", side)
        if note:
            pg.text(self.x, Y(self.y + h + 4), note, 7)
        self.x += w
        self.row_h = max(self.row_h, h + (10 if note else 0))

    def _ground(self, pin, net, direction):
        if net == "GND":
            self.pg.stub_gnd(pin, direction, 10)
        else:
            x, y = pin
            end = {"down": (x, y + 10), "right": (x + 10, y), "left": (x - 10, y), "up": (x, y - 10)}[direction]
            self.pg.wire([pin, end], net)
            self.pg.flag(*end, {"down": 0, "right": 90, "left": 270, "up": 180}[direction], net)


def opamp_units(part):
    """(unit, note) per TL074 section with something on it."""
    out = []
    for s in (1, 2, 3, 4):
        fn = circuit.OPAMPS.get((part.ref, s))
        out.append((s, fn))
    return out


def draw_parts(fl, parts, P):
    for p in parts:
        part = P[p.ref]
        if part.kind == "TL074":
            for s, fn in opamp_units(part):
                fl.unit(part, s, note=f"{fn}" + (" + supply" if s == 1 else ""))
        else:
            fl.unit(part)


def main_pages(pr, P):
    blocks = [
        ("Channel 1: oscillator, sine and fold", [
            ("AS3340 core, pitch inputs, trims, timing, rate LED", circuit.core(1)),
            ("Sine shaper (OTA A) and two-stage diode folder; FOLD control into Iabc A", circuit.fold1()),
            ("U6: transimpedance, inverter, folder summer, FOLD control. U9: LM13700, OTA A here, OTA B on channel 2",
             [P["U6"], P["U9"]])]),
        ("Channel 2: oscillator, triangle and shape", [
            ("AS3340 core, pitch inputs, trims, timing, rate LED", circuit.core(2)),
            ("OTA B gain into the zener-limited transimpedance; SHAPE control into Iabc B", circuit.shape2()),
            ("U7: TIA 2 and SHAPE control for this channel; sections 3 and 4 serve channels 3 and 4", [P["U7"]])]),
        ("Channel 3: oscillator, saw and phase", [
            ("AS3340 core, pitch inputs, trims, timing, rate LED", circuit.core(3)),
            ("PHASE sets PW; the summer (U7 section 3) adds 2 x saw, the pulse, -PW and an offset", circuit.phase3())]),
        ("Channel 4: oscillator, pulse and PWM", [
            ("AS3340 core, pitch inputs, trims, timing, rate LED", circuit.core(4)),
            ("PW from pin 9 and the PWM pot; output stage (U7 section 4). U7 is drawn on channel 2's page",
             circuit.pwm4())]),
        ("Noise bank", [("Avalanche source, WHITE amp (LEVEL trimmer), PINK and BLUE ladders, BROWN integrator (U8)",
                         circuit.noise() + [P["U8"]])]),
        ("Power, references, headers", [
            ("Eurorack power: 1N5819HW per rail (-12 V: cathode on the header), 10R + 10 uF; +-5 V references; "
             "op-amp decoupling", circuit.power()),
            ("Board-to-board sockets (female on this board, pin 1 at the top)", [P["H1"], P["H2"]])]),
    ]
    pages = []
    for i, (title, groups) in enumerate(blocks):
        pg = MPage(pr, title, i + 1)
        pg.page_count = str(len(blocks))
        fl = Flow(pg)
        for heading, parts in groups:
            fl.heading(heading)
            draw_parts(fl, [p for p in parts if p.ref in P], P)
        pages.append(pg)
    return pages


def faceplate_pages(pr, P):
    pg1 = MPage(pr, "Faceplate 1: panel parts", 1)
    pg1.page_count = "2"
    fl = Flow(pg1)
    for k in circuit.CHANNELS:
        fl.heading(f"Channel {k}: jacks, pots, toggles, LED (the FREQ jacks' switch lugs carry the chain)")
        for r in (f"J{3 * k - 2}", f"J{3 * k - 1}", f"J{3 * k}", f"RV{2 * k - 1}", f"RV{2 * k}",
                  f"SW{3 * k - 2}", f"SW{3 * k - 1}", f"SW{3 * k}", f"LED{k}"):
            fl.unit(P[r])
    pg2 = MPage(pr, "Faceplate 2: noise jacks, FREQ followers, headers", 2)
    pg2.page_count = "2"
    fl = Flow(pg2)
    fl.heading("Noise outputs")
    for r in ("J13", "J14", "J15", "J16"):
        fl.unit(P[r])
    fl.heading("FREQ followers on the rear (U5), their input resistors, decoupling")
    draw_parts(fl, [P["U5"]] + [P[r] for r in sorted(P) if P[r].kind == "R"] + [P["C911"], P["C912"]], P)
    fl.heading("Headers to the main board (male here, pin 1 at the top)")
    fl.unit(P["HF1"])
    fl.unit(P["HF2"])
    return [pg1, pg2]


# ------------------------------------------------------------------ checks
def page_check(pg, parts):
    drawn = {(c["ref"], num) for c in pg.comps if c["ref"] for num in c["pins"]}
    sub = []
    for p in parts:
        nets = {pid: n for pid, n in p.nets.items() if (p.ref, pid) in drawn}
        if nets:
            sub.append(circuit.Part(p.ref, p.kind, p.value, nets))
    return check(pg, sub, lambda part, pid: pid)


def coverage(pages, parts):
    seen = collections.Counter((c["ref"], num) for pg in pages for c in pg.comps if c["ref"] for num in c["pins"])
    placed = {c["ref"] for pg in pages for c in pg.comps if c["ref"]}
    problems = [f"{p.ref} not drawn" for p in parts if p.ref not in placed]
    for p in parts:
        for pid in p.nets:
            if seen[(p.ref, pid)] != 1:
                problems.append(f"{p.ref}.{pid} drawn {seen[(p.ref, pid)]} times")
    return problems


def pins_and_pads(pr, keys):
    docs = dict(pr.lib)
    for typ, lines in pr.new_docs:
        docs.update(ee.parse(lines))
    problems = []
    for key in sorted(keys):
        a = pr.device_attrs(key)
        pins = {p["num"] for p in pr.symgeo[a["Symbol"]]["pins"]}
        pads = {p["num"] for h, p in docs[a["Footprint"]]["recs"] if h["type"] == "PAD"}
        if pins != pads:
            problems.append(f"{key}: symbol pins {sorted(pins - pads)} without pads, pads {sorted(pads - pins)} "
                            "without pins")
    return problems


def validate(path):
    with ee.zipfile.ZipFile(path) as z:
        docs = ee.parse(z.read(f"{NAME}.epru").decode("utf-8").split("\n"))
    problems = []
    pad_ids = {u: {h["id"] for h, p in d["recs"] if h["type"] == "PAD"}
               for u, d in docs.items() if d["docType"] == "FOOTPRINT"}
    for u, d in docs.items():
        if d["docType"] == "SCH_PAGE":
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p["key"] in ("Device", "Symbol", "Footprint") and p["value"] \
                        and p["value"] not in docs:
                    problems.append(f"{meta(d)['title']}: {p['key']} {p['value']} missing")
        elif d["docType"] == "PCB":
            title = meta(d)["title"]
            nets = {ee.json.loads(h["id"])[1] for h, p in d["recs"] if h["type"] == "NET"}
            fp_of = {}
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p.get("key") in ("Footprint", "Device"):
                    if p["value"] not in docs:
                        problems.append(f"{title}: {p['key']} {p['value']} missing")
                    if p["key"] == "Footprint":
                        fp_of[p["parentId"]] = p["value"]
            for h, p in d["recs"]:
                if h["type"] == "PAD_NET":
                    _, cid, num, pid = ee.json.loads(h["id"])
                    if pid not in pad_ids.get(fp_of.get(cid), ()):
                        problems.append(f"{title}: PAD_NET {cid}.{num} names no pad of its footprint")
                    if p["padNet"] not in nets:
                        problems.append(f"{title}: net {p['padNet']} has no NET record")
    return problems, collections.Counter(d["docType"] for d in docs.values())


def part_info(pages):
    info = {}
    for pg in pages:
        for c in pg.comps:
            if c["ref"] and c["ref"] not in info:
                info[c["ref"]] = {"dev": c["dev"], "uid": pg.pr.unique_id(c["ref"]),
                                  "channel": f"${pg.number}{c['cid']}"}
    return info


def main():
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    pr = MProject(mb + fb)
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    mpages, fpages = main_pages(pr, PM), faceplate_pages(pr, PF)
    bad = coverage(mpages, mb) + coverage(fpages, fb)
    for pg, parts in [(p, mb) for p in mpages] + [(p, fb) for p in fpages]:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in mpages + fpages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    fi, mi = part_info(fpages), part_info(mpages)
    holes = pcb.find_holes([pcb.faceplate_board(pr, fb, fi, circuit), pcb.main_board(pr, mb, mi, circuit)])
    board_fb = pcb.faceplate_board(pr, fb, fi, circuit, holes)
    board_mb = pcb.main_board(pr, mb, mi, circuit, holes)
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb))
    if len(board_fb.holes) != 4:
        pcb_bad.append(f"only {len(board_fb.holes)} mounting holes found")
    for b in pcb_bad:
        print("PCB:", b)
    template = pcb.load_template(ee)
    panel_page = MPage(pr, "Panel", 1)
    panel_page.text(70, Y(60), "Senay 14HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the "
                               "bare-copper output squares and noise band are in the PCB document; the art is "
                               "hardware/panel/senay-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("Senay Main", mpages, board_mb), ("Senay Faceplate", fpages, board_fb),
              ("Senay Panel", [panel_page], board_panel)], OUT, template)
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in mpages + fpages:
        render(pr, pg, PREVIEW.format("-".join(__import__("re").findall(r"[a-z0-9]+", pg.title.split(":")[0].lower()))))
    board_mb.render(PREVIEW.format("pcb-main-board"))
    board_fb.render(PREVIEW.format("pcb-faceplate"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in mpages + fpages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(mpages) + len(fpages)} pages, "
          f"{len(bad)} schematic problems; {len(board_mb.placed)} + {len(board_fb.placed)} parts placed, "
          f"{len(pcb_bad)} PCB problems; {len(missing)} file problems; holes {board_fb.holes}; docs {dict(counts)}")


if __name__ == "__main__":
    main()
