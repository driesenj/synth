"""The stereo mixer as an EasyEDA Pro project (.epro2): schematic pages,
both PCBs placed, and the panel PCB.

Builds on the Plaitsy stripboard exporter (../../../plaitsy/hardware/tools)
for the file format, the connectivity check and the previews, the way
Marblesy and Plaitsy do. Library parts come from two caches of your
MorrisSynth export: plaitsy/hardware/easyeda/morrissynth-parts.epru
(TL074ACN symbol, WQP518MA jack, PTV09A pot symbol, LR1F resistors, FG28 /
SR305 capacitors, 1N4148, 1N5819, net ports, ground flag, sheet frame) and
stereo-mixer-parts.epru next to this project (LR1F 10R, the 178MU0033
10 uF, the 2x8 box header). Drawn or generated here, in the same style
and with real pin numbers:

  footprints  DIP-14 on the standard 7.62 mm row pitch (the TL074ACN library
              footprint has its rows 8.89 mm apart, too wide for a socket),
              DIP-4, Alpha 9 mm single and dual-gang pots (lugs on the shaft
              line, as on the Alpha part; the library PTV09A is Bourns'),
              the Thonk LED button, standing resistors, 1xN headers
  symbols     CD4013, CD4093, AQY212EH (LED and switch as two units), the
              dual-gang pot (one unit per gang, lugs on gang A), LED button,
              headers

Pages: main board (mono channels; stereo channels, buses and outputs; mute
latch; power and headers), faceplate (jacks and pots; dual pots, buttons
and headers), panel note. Net ports with the same name connect within a
board; nets that cross between the boards are the header pins.

Run from stereo-mixer/hardware/tools:  python easyeda_export.py
"""
import collections
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAITSY = os.path.normpath(os.path.join(HERE, "..", "..", "..", "plaitsy", "hardware", "tools"))
sys.path.insert(0, PLAITSY)
import easyeda_export as ee                      # noqa: E402  (the Plaitsy stripboard exporter)
sys.path.remove(PLAITSY)

from easyeda_export import (Doc, Symbol, Page, Project, meta, attr_payload, Y, render, check,   # noqa: E402
                            new_uuid, W, H, H_TXT, V_TXT)

LIBFILES = [os.path.join(PLAITSY, "..", "easyeda", "morrissynth-parts.epru"),
            os.path.join(HERE, "..", "easyeda", "stereo-mixer-parts.epru")]


def _load(name):
    spec = importlib.util.spec_from_file_location("mixer_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")
SECTION = circuit.SECTION

NAME = "StereoMixer"
OUT = os.path.join(HERE, "..", "easyeda", "StereoMixer.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "stereo-mixer-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil

# Library devices used as they are (uuids from the two caches)
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0
    "R10k": "a9cc8fbe474242dc9110194515734c75",      # LR1F10K
    "R10R": "94e97e59e04b421d92158c6257818225",      # LR1F10R
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00
    "C1u": "bf1fe821a3774bf48d0873f872221180",       # SR305C105KAR
    "C10u": "21e4ec8defc34a489f66b07134d13cd6",      # 178MU0033, 10 uF 35 V
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol; footprint replaced below)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "POT": "be9d2c8f5f814271a402f956f18b56f9",       # PTV09A-4025F-B103 (its symbol)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819
    "HDR16": "bbe47e9fd91b42bbaf0d36b9504a3a5e",     # DC3-2.54-16PAS, 2x8 box header
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here
D1N4148 = "c0160a3f74384e849dc1cc5a24d54846"      # library 1N4148: its DO-35 footprint and attributes
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "200k": ("LR1F200K", "200kΩ"), "300k": ("LR1F300K", "300kΩ"),
         "1k5": ("LR1F1K5", "1.5kΩ")}
C_NEW = {"22p": ("FG28C0G1H220JNT00", "22pF")}

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
    """A through-hole footprint in mm; written as an EasyEDA Pro FOOTPRINT doc.
    Pads are round (or square) with round holes, or oval with slot holes
    (slot=(w, h)) like the library pots' lugs."""

    def __init__(self, title, designator="U?"):
        self.title, self.designator = title, designator
        self.pads, self.silk = [], []
        self.doc = Doc("FOOTPRINT")

    def pad(self, num, x, y, hole=1.0, size=1.7, square=False, h=None, slot=None):
        self.pads.append((str(num), x, y, hole, size, h or size, square, slot))

    def line(self, x1, y1, x2, y2):
        self.silk.append(("L", (x1, y1, x2, y2)))

    def rect(self, x1, y1, x2, y2):
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
            self.line(*a, *b)

    def circle(self, x, y, r):
        self.silk.append(("C", (x, y, r)))

    def build(self):
        d = self.doc
        for i, (lid, typ, name, c1, c2) in enumerate(LAYERS):
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
            d.add("POLY", d.nid(), {"groupId": 0, "netName": "", "layerId": 3, "width": 8, "path": path,
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for num, x, y, hole, pw, ph, square, slot in self.pads:
            if slot:
                pad = {"padType": "OVAL", "width": m(pw), "height": m(ph)}
                hl = {"holeType": "SLOT", "width": m(slot[0]), "height": m(slot[1])}
            else:
                pad = {"padType": "RECT", "width": m(pw), "height": m(ph), "radius": 0} if square else \
                      {"padType": "ELLIPSE", "width": m(pw), "height": m(ph)}
                hl = {"holeType": "ROUND", "width": m(hole), "height": m(hole)}
            d.add("PAD", d.nid(), {"groupId": 0, "netName": "", "layerId": 12, "num": num, "centerX": m(x),
                                   "centerY": m(y), "padAngle": 0, "hole": hl,
                                   "defaultPad": pad, "specialPad": [], "padOffsetX": 0, "padOffsetY": 0,
                                   "relativeAngle": 0, "plated": True, "padType": "NORMAL",
                                   "topSolderExpansion": None, "bottomSolderExpansion": None,
                                   "topPasteExpansion": None, "bottomPasteExpansion": None, "locked": False,
                                   "zIndex": d.zi(), "connectMode": None, "spokeSpace": None, "spokeWidth": None,
                                   "spokeAngle": None, "padLen": 0})
        for key, val in (("Footprint", self.title), ("Designator", self.designator)):
            d.add("ATTR", d.nid(), {"groupId": 0, "parentId": "", "layerId": 3, "x": None, "y": None, "key": key,
                                    "value": val, "keyVisible": False, "valueVisible": False,
                                    "fontFamily": "default", "fontSize": 67.5, "strokeWidth": 6, "bold": False,
                                    "italic": False, "origin": "LEFT_BOTTOM", "angle": 0, "reverse": False,
                                    "expansion": 0, "mirror": False, "locked": False, "zIndex": d.zi()})
        d.add("NET", '["NET",""]', {"netType": None, "specialColor": None, "retLine": True, "differentialName": None,
                                    "isPositiveNet": False, "equalLengthGroupName": None})
        return d.lines({"title": self.title, "description": "", "tags": [NAME],
                        "source": f"{new_uuid()}|{ee.USER['uuid']}"})


def fp_header(n):
    f = Footprint(f"HDR-1x{n}-P2.54", "H?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.27, -1.27, x0 + (n - 1) * 2.54 + 1.27, 1.27)
    return f


def fp_led_button():
    """Thonk low-profile LED button (the Plaitsy footprint): switch pins 1-4
    on a 5.08 mm square (1+2 and 3+4 are the contacts), LED anode 5 and
    cathode 6 at x = +-2.7. No holes for the plastic feet: clip them off."""
    f = Footprint("SW-TACT-LP-LED-THONK", "SW?")
    for num, (x, y) in ((1, (2.54, 2.54)), (2, (-2.54, 2.54)), (3, (2.54, -2.54)), (4, (-2.54, -2.54)),
                        (5, (2.7, 0)), (6, (-2.7, 0))):
        f.pad(num, x, y, 1.0, 1.6, square=(num == 1))
    f.rect(-3.75, -3.75, 3.75, 3.75)
    f.circle(0, 0, 2.75)
    return f


def fp_res_vertical():
    """A resistor standing up, 2.54 mm: the body over pad 1, the bent lead to pad 2 (the Plaitsy footprint)."""
    f = Footprint("RES-TH-VERTICAL-P2.54", "R?")
    f.pad(1, 0, 0.48006, 0.8, 1.6)
    f.pad(2, 0, -2.0574, 0.8, 1.6)
    f.circle(0, 0.48006, 1.1)
    f.line(0, -0.79, 0, -1.11)
    return f


def fp_dip(n, title):
    """DIP on the standard 300 mil (7.62 mm) row pitch, pin 1 bottom-left, counting anticlockwise."""
    f = Footprint(title, "U?")
    half = n // 2
    x0 = -(half - 1) * 1.27
    for i in range(half):
        f.pad(i + 1, x0 + i * 2.54, -3.81, 0.9, 1.6, square=(i == 0))
        f.pad(n - i, x0 + i * 2.54, 3.81, 0.9, 1.6)
    hx = half * 1.27 + (0.7 if half > 2 else -0.24)      # body: 19.2 mm long for DIP-14, 4.6 for DIP-4
    hy = 3.25                                            # 6.5 mm wide
    f.rect(-hx, -hy, hx, hy)
    f.circle(-hx + 0.9, -hy + 0.9, 0.3)
    return f


def fp_alpha_pot(dual):
    """Alpha 9 mm vertical pot, single (RD901F) or dual-gang (RD902F), in the
    frame of the library PTV09A footprint: pins 1-3 at y = -3.5, x = -2.5 /
    0 / 2.5, the shaft 7.5 mm from them at y = +4.0, the two mounting lugs on
    the shaft line (KiCad: +-4.8 single, +-4.75 dual) as oval pads with
    slots. The dual's second gang (pins 4-6) is the row 2.5 mm further from
    the shaft. Lugs are pads 4 / 5 (single) or 7 / 8 (dual)."""
    f = Footprint("POT-ALPHA-9MM-" + ("RD902F-DUAL" if dual else "RD901F"), "RV?")
    for i, x in enumerate((-2.5, 0.0, 2.5)):
        f.pad(i + 1, x, -3.5, 1.0, 1.8, square=(i == 0))
        if dual:
            f.pad(i + 4, x, -6.0, 1.0, 1.8)
    lx = 4.75 if dual else 4.8
    lugs = ("7", "8") if dual else ("4", "5")
    for num, x in zip(lugs, (-lx, lx)):
        f.pad(num, x, 4.0, size=2.7, h=3.2, slot=(1.1, 1.8))
    f.rect(-4.75, -2.5, 4.75, 8.85)       # body, 9.5 wide, from 1 mm off the pin row to 4.85 mm past the shaft
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


def cd4013_symbol():
    left = [(0, "5", "D1"), (1, "3", "CLK1"), (2, "6", "SET1"), (3, "4", "RST1"),
            (5, "9", "D2"), (6, "11", "CLK2"), (7, "8", "SET2"), (8, "10", "RST2")]
    right = [(0, "1", "Q1"), (1, "2", "/Q1"), (5, "13", "Q2"), (6, "12", "/Q2"), (8, "14", "VDD"), (9, "7", "VSS")]
    return ic_symbol("CD4013B", "CD4013.1", left, right)


def cd4093_symbol():
    left = [(0, "1", "A1"), (1, "2", "B1"), (2, "5", "A2"), (3, "6", "B2"), (4, "8", "A3"), (5, "9", "B3"),
            (6, "12", "A4"), (7, "13", "B4")]
    right = [(0, "3", "Y1"), (2, "4", "Y2"), (4, "10", "Y3"), (6, "11", "Y4"), (8, "14", "VDD"), (9, "7", "VSS")]
    return ic_symbol("CD4093B", "CD4093.1", left, right)


def led_button_symbol():
    """Tactile switch with a built-in LED: contacts 1+2 and 3+4, LED on 5 and 6."""
    left = [(0, "1", "1"), (1, "2", "2"), (3, "5", "LED A")]
    right = [(0, "3", "3"), (1, "4", "4"), (3, "6", "LED K")]
    return ic_symbol("LED button", "SWLED.2", left, right, designator="SW?")


def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.2", "H?", [NAME])
    half = n * 5
    s.rect(-10, -half - 5, 10, half + 5)
    for i in range(n):
        s.pin(str(i + 1), str(i + 1), -20, -half + 5 + 10 * i, 0, show=True, edge=-10)
    return s


class MultiSymbol:
    """A symbol with several units (gangs, poles, LED / switch), in the library's style."""

    def __init__(self, title, prefix, designator, units, tags=()):
        self.title, self.designator, self.tags = title, designator, list(tags)
        self.parts = [f"{prefix}.{i + 1}" for i in range(units)]
        self.items = {p: [] for p in self.parts}
        self.cur = self.parts[0]
        self.doc = Doc("SYMBOL")

    def unit(self, n):
        self.cur = self.parts[n - 1]

    def poly(self, pts, closed=False, fill=None):
        self.items[self.cur].append(("POLY", {"points": [{"x": x, "y": y} for x, y in pts],
                                              "closed": closed, "fill": fill}))

    def text(self, x, y, s, size=None):
        self.items[self.cur].append(("TEXT", (x, y, s, size)))

    def pin(self, num, name, x, y, rot, length=10):
        self.items[self.cur].append(("PIN", (num, name, x, y, rot, length)))

    def bbox(self, part):
        xs, ys = [], []
        for t, d in self.items[part]:
            if t == "POLY":
                xs += [p["x"] for p in d["points"]]
                ys += [p["y"] for p in d["points"]]
        return [min(xs), min(ys), max(xs), max(ys)]

    def build(self):
        d = self.doc
        d.add("CANVAS", "CANVAS", {"originX": 0, "originY": 0})
        for part in self.parts:
            d.add("PART", part, {"BBOX": self.bbox(part), "title": part})
        style = {"strokeColor": None, "strokeStyle": None, "fillColor": None, "strokeWidth": None, "fillStyle": None}
        for part in self.parts:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), "", "Symbol", self.title, align="LEFT_BOTTOM", part=part))
            d.add("ATTR", d.nid(), attr_payload(d.zi(), "", "Designator", self.designator, align="LEFT_BOTTOM",
                                                part=part))
            for t, it in self.items[part]:
                if t == "POLY":
                    d.add("POLY", d.nid(), {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(),
                                            "points": it["points"], "closed": it["closed"],
                                            **dict(style, fillColor=it["fill"])})
                elif t == "TEXT":
                    x, y, s, size = it
                    d.add("TEXT", d.nid(), {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(),
                                            "x": x, "y": y, "rotation": 0, "value": s, "color": None,
                                            "fillColor": None, "fontFamily": None, "fontSize": size,
                                            "strikeout": False, "underline": False, "italic": False,
                                            "fontWeight": False, "align": "LEFT_BOTTOM", "version": "2.0"})
                else:
                    num, name, x, y, rot, length = it
                    pid = d.nid()
                    d.add("PIN", pid, {"partId": part, "groupId": "", "locked": False, "zIndex": d.zi(),
                                       "display": True, "x": x, "y": y, "length": length, "rotation": rot,
                                       "color": None, "pinShape": "NONE"})
                    if rot in (0, 180):    # number above the middle of a horizontal pin
                        nx, ny = x + (length / 2 if rot == 0 else -length / 2) - 2, y - 1
                    else:                  # beside the middle of a vertical pin
                        nx, ny = x + 2, y + (length / 2 if rot == 270 else -length / 2) + 3
                    d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Name", name, x=x, y=y,
                                                        align="LEFT_BOTTOM", part=part))
                    d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Number", num, vv=True, x=nx, y=ny,
                                                        fs=6, align="LEFT_BOTTOM", part=part))
                    d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Type", "Undefined", x=x, y=y,
                                                        align="LEFT_BOTTOM", part=part))
        source = f"{new_uuid()}|{ee.USER['uuid']}"
        return d.lines({"title": self.title, "description": "", "tags": self.tags, "docType": 2, "source": source})


def dual_pot_symbol():
    """Two gangs drawn like the library pot standing up: CW end on top, CCW
    end below, wiper from the right. Gang A pins 3/2/1 with the two mounting
    lugs 7 / 8 on its left, gang B 6/5/4."""
    s = MultiSymbol("Pot 9mm dual-gang", "POT_DUAL", "RV?", 2, [NAME])
    for unit, (cw, w, ccw, letter) in enumerate((("3", "2", "1", "A"), ("6", "5", "4", "B")), start=1):
        s.unit(unit)
        s.poly([(0, -12), (3, -10), (-3, -6), (3, -2), (-3, 2), (3, 6), (-3, 10), (0, 12)])
        s.poly([(10, 0), (6, 0)])
        s.poly([(4, 0), (8, -2.5), (8, 2.5), (4, 0)], closed=True)
        s.text(-13, 3, letter, 8)
        s.pin(cw, "CW", 0, -20, 270, 8)
        s.pin(ccw, "CCW", 0, 20, 90, 8)
        s.pin(w, "W", 20, 0, 180, 10)
        if unit == 1:
            s.poly([(-14, -14), (-14, 14)])
            s.pin("7", "MT", -30, -10, 0, 16)
            s.pin("8", "MT", -30, 10, 0, 16)
    return s


def photomos_symbol():
    """AQY212EH as two units: the LED (1 anode on top, 2 cathode below) and the
    switch (3 on top, 4 below)."""
    s = MultiSymbol("AQY212EH", "AQY212", "K?", 2, [NAME])
    s.unit(1)
    s.poly([(-5, -4), (5, -4), (0, 4), (-5, -4)], closed=True)
    s.poly([(-5, 4), (5, 4)])
    s.poly([(7, -2), (11, 2)])
    s.poly([(7, 2), (11, 6)])
    s.pin("1", "A", 0, -20, 270, 16)
    s.pin("2", "K", 0, 20, 90, 16)
    s.unit(2)
    s.poly([(0, -12), (0, -6)])
    s.poly([(0, 6), (0, 12)])
    s.poly([(0, 6), (-6, -5)])
    s.poly([(-12, -2), (-8, 2)])
    s.poly([(-12, 2), (-8, 6)])
    s.pin("3", "D", 0, -20, 270, 8)
    s.pin("4", "D", 0, 20, 90, 8)
    return s


# ------------------------------------------------------------------ project
RV_KEYS = ["R1k", "R10k", "R10R"] + ["R" + v for v in R_NEW]


class MPage(Page):
    page_count = "6"

    def place(self, ref, dev_key, *args, **kw):
        if self.title.startswith("Main") and dev_key in RV_KEYS:   # every main-board resistor stands up
            dev_key += "V"
        p = super().place(ref, dev_key, *args, **kw)
        # remember the schematic component id: the PCB's Channel ID attribute points at it
        self.comps[-1]["cid"] = next(h["id"] for h, _ in reversed(self.doc.recs) if h["type"] == "COMPONENT")
        return p

    def frame(self):
        d, pr = self.doc, self.pr
        cid = d.nid()
        sym = pr.sym_of("FRAME")
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": pr.symgeo[sym]["parts"][0],
                                 "groupId": "", "x": 0, "y": 0, "rotation": 0, "isMirror": False, "attrs": {}})
        today = ee.time.strftime("%Y-%m-%d")
        vals = [("Symbol", sym), ("@Project Name", "Stereo Mixer"), ("@Page Count", self.page_count),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", "Stereo Mixer"),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V0.2"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", "Stereo Mixer"),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))

    def flag(self, x, y, rot, net):
        """Ground-style flag carrying a named net (GND_F)."""
        self._flag("GND", x, y, rot, net, True)

    def stub_flag(self, pin, net, direction="down", length=10):
        x, y = pin
        end = {"down": (x, y + length), "right": (x + length, y), "left": (x - length, y), "up": (x, y - length)}
        x2, y2 = end[direction]
        self.wire([(x, y), (x2, y2)], net)
        self.flag(x2, y2, {"down": 0, "right": 90, "left": 270, "up": 180}[direction], net)


class MProject(Project):
    def __init__(self):     # noqa: super().__init__ would load only Plaitsy's library
        self.lib = {}
        for f in LIBFILES:
            self.lib.update(ee.parse(open(f, encoding="utf-8").read().split("\n")))
        self.symgeo = {u: ee.symbol_geometry(d) for u, d in self.lib.items() if d["docType"] == "SYMBOL"}
        self.devices = {k: (u, meta(self.lib[u])) for k, u in DEV.items()}
        self.new_docs = []
        self.uids, self.next_uid = {}, 2
        self._new_devices()

    def device_attrs(self, key):
        return self.devices[key][1]["attributes"]

    def _footprint(self, fp):
        lines = fp.build()
        self.new_docs.append(("FOOTPRINT", lines))
        return fp.doc.uuid

    def footprint_geo(self, uid):
        """Pads and body box of a library or generated footprint, by uuid."""
        if not hasattr(self, "_fpgeo"):
            self._fpgeo = {}
            docs = {u: d for u, d in self.lib.items() if d["docType"] == "FOOTPRINT"}
            for typ, lines in self.new_docs:
                if typ == "FOOTPRINT":
                    docs.update(ee.parse(lines))
            for u, d in docs.items():
                self._fpgeo[u] = pcb.footprint_geometry(d)
        return self._fpgeo[uid]

    def _copy(self, key, src, title, tags, **changes):
        a = dict(self.device_attrs(src))
        a.update(changes)
        self._device(key, title, a, tags)

    def _new_devices(self):
        r1k = meta(self.lib[DEV["R1k"]])["attributes"]
        for val, (mpn, value) in R_NEW.items():
            a = dict(r1k)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "LCSC Part Name": f"Metal film resistor {value} ±1% 600mW",
                      "Description": f"Metal film resistor {value} ±1% 600mW (TE LR1F series)"})
            self._device("R" + val, mpn, a, ["Resistors", "Through Hole Resistors"])
        c100n = meta(self.lib[DEV["C100n"]])["attributes"]
        for val, (mpn, value) in C_NEW.items():
            a = dict(c100n)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "Tolerance": "±5%", "Temperature Coefficient": "C0G",
                      "LCSC Part Name": f"{value} ±5% 50V C0G",
                      "Description": f"Capacitance:{value} Tolerance:±5% Voltage Rating:50V Temperature Coefficient:C0G"})
            self._device("C" + val, mpn, a, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"])
        fps = {"RV": self._footprint(fp_res_vertical()), "DIP14": self._footprint(fp_dip(14, "DIP-14-W7.62-P2.54")),
               "DIP4": self._footprint(fp_dip(4, "DIP-4-W7.62-P2.54")), "SWLED": self._footprint(fp_led_button()),
               "POT": self._footprint(fp_alpha_pot(False)), "POT2": self._footprint(fp_alpha_pot(True))}
        for n in (8, 12):
            fps[f"HDR{n}"] = self._footprint(fp_header(n))
        for key in RV_KEYS:                                       # each resistor again, standing up
            a = self.device_attrs(key)
            self._copy(key + "V", key, a["Manufacturer Part"], ["Resistors", "Through Hole Resistors"],
                       Footprint=fps["RV"])
        a = dict(meta(self.lib[D1N4148])["attributes"])            # its own symbol is not cached: the 1N5819's
        a["Symbol"] = self.device_attrs("D5819")["Symbol"]
        self._device("D4148S", "1N4148", a, ["Diodes"])
        self._copy("TL074N", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        for value in ("A100k", "B10k"):                           # your pot symbol on the Alpha footprint
            self._copy("POT" + value, "POT", f"Alpha 9mm {value}", ["Potentiometers"], Footprint=fps["POT"],
                       Name="={Value}", Value=value, **{"Manufacturer Part": f"Alpha RD901F-40-15R1 {value}",
                                                        "Supplier Part": "", "Datasheet": "",
                                                        "Description": f"Alpha 9 mm vertical pot {value}, T18 "
                                                                       "shaft (Thonk). Pin 3 = CW end"})
        new = [
            ("CD4013", cd4013_symbol(), "CD4013B", "U?", fps["DIP14"], "Dual D flip-flop, DIP-14"),
            ("CD4093", cd4093_symbol(), "CD4093B", "U?", fps["DIP14"], "Quad 2-input Schmitt NAND, DIP-14"),
            ("SWLED", led_button_symbol(), "LED button, Thonk low profile", "SW?", fps["SWLED"],
             "Thonk low-profile LED button: 7.5 mm body, 5.5 mm round cap, 1+2 / 3+4 contacts, LED anode 5, "
             "cathode 6. Clip the three plastic feet off: the board has no holes for them"),
        ]
        for n in (8, 12):
            new.append((f"HDR{n}", header_symbol(n), f"Pin header 1x{n}", "H?", fps[f"HDR{n}"],
                        f"Board-to-board header, 1x{n}, 2.54 mm"))
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
            self._device(key, title, attrs)
        su = self._symbol(dual_pot_symbol())
        self._device("POT2", "Alpha 9mm dual-gang A100k", {
            "Name": "={Value}", "Value": "A100k", "Manufacturer Part": "Alpha RD902F-40-15R1 A100K",
            "Designator": "RV?", "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su,
            "Footprint": fps["POT2"], "3D Model": "", "3D Model Title": "", "3D Model Transform": "",
            "Description": "Alpha 9 mm vertical dual-gang pot, A100K (audio). Gang A pins 1-2-3 (the row nearer "
                           "the shaft), gang B 4-5-6, wipers 2 and 5, mounting lugs 7 / 8"})
        su = self._symbol(photomos_symbol())
        self._device("PHOTOMOS", "AQY212EH", {
            "Name": "={Manufacturer Part}", "Manufacturer": "Panasonic", "Manufacturer Part": "AQY212EH",
            "Designator": "K?", "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su,
            "Footprint": fps["DIP4"], "3D Model": "", "3D Model Title": "", "3D Model Transform": "",
            "Description": "PhotoMOS relay, 1 form A, 60 V 0.5 A, DIP-4: LED 1 (anode) / 2, switch 3 / 4"})

    def _symbol(self, sym):
        lines = sym.build()
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(sym.doc.uuid, lines)
        return sym.doc.uuid

    def write(self, boards, path, template):
        """boards: [(title, pages, pcb.Board)]; each gets a BOARD doc holding its schematic pages and its PCB."""
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
        lines += next(d for d in self.lib.values() if d["docType"] == "BLOB")["lines"]   # one BLOB doc, both caches have it
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Stereo master mixer for the Eurorack voice case: 6 mono channels with pan, "
                                  "2 stereo channels, LED-button mutes, Clouds send and return, drum input. "
                                  "4x TL074; two stacked PCBs and a PCB panel, 28HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


def dev_of(part):
    if part.kind == "R":
        return {"1k": "R1k", "10k": "R10k", "10R": "R10R"}.get(part.value, "R" + part.value)
    if part.kind == "C":
        return {"100n": "C100n", "1u": "C1u"}.get(part.value, "C" + part.value)
    if part.kind == "POT":
        return "POT" + part.value
    return {"CP": "C10u", "D5819": "D5819", "D4148": "D4148S", "JACK": "JACK", "TL074": "TL074N",
            "CD4013": "CD4013", "CD4093": "CD4093", "PHOTOMOS": "PHOTOMOS", "POT2": "POT2", "SWLED": "SWLED",
            "HDR8": "HDR8", "HDR12": "HDR12", "HDR16": "HDR16"}[part.kind]



# ---------------------------------------------------------------- drawing helpers
def hpart(pg, part, x1, y, left_pin="1"):
    """Two-pin part drawn horizontally with `left_pin` at (x1, y), the other pin at (x1 + 40, y)."""
    rot = 0 if left_pin == "1" else 180
    return pg.place(part.ref, dev_of(part), x1 + 20, y, rot, des=H_TXT[0], value_at=H_TXT[1])


def vpart(pg, part, x, y1, top_pin="1", texts_left=False):
    """Two-pin part drawn vertically with `top_pin` at (x, y1), the other pin at (x, y1 + 40)."""
    rot = 270 if top_pin == "1" else 90
    txt = ((-8, -2, "RIGHT_BOTTOM"), (-8, 8, "RIGHT_BOTTOM")) if texts_left else V_TXT
    return pg.place(part.ref, dev_of(part), x, y1 + 20, rot, *txt)


def down_port(pg, pin, net, kind="OUT", length=20):
    """A wire down from pin and a net port at its end, flag to the right."""
    x, y = pin
    pg.wire([(x, y), (x, y + length)], net)
    pg.port(x, y + length, net, kind, "right")


def supply(pg, amp, sec):
    if sec == 1:   # this unit carries the supply pins
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))


def follower(pg, ref, sec, x, y, net):
    """TL074 section as a voltage follower with its + input at (x, y). Returns
    the amp and the junction right of the output (row y - 10)."""
    ox, oy = x + 40, y - 10
    amp = pg.place(ref, "TL074N", ox, oy, unit=sec, des=(-6, 32, "LEFT_BOTTOM"), name=False)
    out, inm, _ = SECTION[sec]
    node = (ox + 55, oy)
    pg.wire([amp[out], node], net)
    pg.wire([node, (ox + 55, oy - 35), (ox - 55, oy - 35), (ox - 55, oy - 10), amp[inm]], net)
    supply(pg, amp, sec)
    return amp, node


def inverting(pg, ref, sec, x, y, rf, cf=None):
    """TL074 section as an inverting stage; summing junction at (x, y), feedback above.
    Returns (amp, junction, output node)."""
    ox, oy = x + 55, y + 10
    amp = pg.place(ref, "TL074N", ox, oy, unit=sec, des=(14, 30, "LEFT_BOTTOM"), name=False)
    out, inm, inp = SECTION[sec]
    jx, kx = x, ox + 60
    nin, nout = rf.nets["1"], rf.nets["2"]
    a_rf = hpart(pg, rf, ox - 20, oy - 60)
    pg.wire([(jx, y), amp[inm]], nin)
    pg.wire([(jx, y), (jx, oy - 60)], nin)
    pg.wire([(jx, oy - 60), a_rf["1"]], nin)
    pg.wire([amp[out], (kx, oy)], nout)
    pg.wire([(kx, oy), (kx, oy - 60)], nout)
    pg.wire([(kx, oy - 60), a_rf["2"]], nout)
    if cf is not None:
        a_cf = hpart(pg, cf, ox - 20, oy - 90)
        pg.wire([(jx, oy - 60), (jx, oy - 90), a_cf["1"]], nin)
        pg.wire([(kx, oy - 60), (kx, oy - 90), a_cf["2"]], nout)
    pg.stub_gnd(amp[inp], "left", 10)
    supply(pg, amp, sec)
    return amp, (jx, y), (kx, oy)


def find(P, kind, pin, net):
    return next(p for p in P.values() if p.kind == kind and p.nets.get(pin) == net)


def mute_input(pg, P, s, x, y):
    """Port LV -> 10k (pin 1 at (x, y)) -> FI junction at (x + 60, y) -> PhotoMOS switch to GND below it.
    Returns the junction."""
    rs = find(P, "R", "2", f"FI{s}")
    km = find(P, "PHOTOMOS", "3", f"FI{s}")
    a = hpart(pg, rs, x, y)
    pg.wire([(x - 20, y), a["1"]], f"LV{s}")
    pg.port(x - 20, y, f"LV{s}", "IN", "left")
    j = (x + 60, y)
    pg.wire([a["2"], j], f"FI{s}")
    sw = pg.place(km.ref, "PHOTOMOS", x + 60, y + 40, unit=2, des=(8, 4, "LEFT_BOTTOM"), name=False)
    pg.wire([j, sw["3"]], f"FI{s}")
    pg.stub_gnd(sw["4"], "down", 10)
    return j


def channel_input(pg, P, s, x0, y):
    """Mute input and follower of one channel side; returns the follower's output junction."""
    j = mute_input(pg, P, s, x0 + 40, y)
    u, sec = circuit.opamp_of("FOL", s)
    pg.wire([j, (x0 + 140, y)], f"FI{s}")
    amp, node = follower(pg, u, sec, x0 + 140, y, f"CH{s}")
    return node


# ------------------------------------------------------------------ main board pages
def mono_block(pg, P, k, x0, t0):
    """One mono channel: mute, follower, CH to the header, pan feeds, bus resistors."""
    r = 100 * k
    pg.text(x0, Y(t0), f"Channel {k} (mono)", 12)
    nx, ny = channel_input(pg, P, str(k), x0, Y(t0 + 70))
    xc = nx + 40
    pg.wire([(nx, ny), (xc, ny)], f"CH{k}")
    pg.wire([(xc, ny), (xc + 40, ny)], f"CH{k}")
    pg.port(xc + 40, ny, f"CH{k}", "OUT", "right")
    pg.wire([(xc, ny), (xc, ny + 30)], f"CH{k}")
    a_pl = vpart(pg, P[f"R{r + 2}"], xc, ny + 60)
    a_pr = vpart(pg, P[f"R{r + 3}"], xc + 110, ny + 60)
    pg.wire([(xc, ny + 30), a_pl["1"]], f"CH{k}")
    pg.wire([(xc, ny + 30), (xc + 110, ny + 30), a_pr["1"]], f"CH{k}")
    for a, net, bus, rb, x, side in ((a_pl, f"PL{k}", "SUM_L", r + 4, xc, "left"),
                                     (a_pr, f"PR{k}", "SUM_R", r + 5, xc + 110, "right")):
        jn = (x, ny + 130)
        pg.wire([a["2"], jn], net)
        ab = vpart(pg, P[f"R{rb}"], x, ny + 160)
        pg.wire([jn, ab["1"]], net)
        px = x - 40 if side == "left" else x + 40
        pg.wire([jn, (px, ny + 130)], net)
        pg.port(px, ny + 130, net, "OUT", side)
        down_port(pg, ab["2"], bus)
    a_sd = hpart(pg, P[f"R{r + 6}"], x0 + 40, ny + 210)
    pg.wire([(x0 + 20, ny + 210), a_sd["1"]], f"SD{k}")
    pg.port(x0 + 20, ny + 210, f"SD{k}", "IN", "left")
    pg.stub_port(a_sd["2"], "SUM_S", "OUT", "right")


def mono_page(pr, P):
    pg = MPage(pr, "Main board: mono channels", 1)
    pg.page_count = "4"
    pg.text(40, Y(30), "Mono channels: LEVEL wiper (LV, from the faceplate) -> 10k -> follower; the PhotoMOS from the "
                       "follower input to GND is the mute. CH goes to the SEND pot and into the pan network.", 12)
    for i, k in enumerate(circuit.MONO):
        col, row = i % 2, i // 2
        mono_block(pg, P, k, 60 + col * 820, 70 + row * 330)
    pg.text(40, Y(1080), "Pan: 10k from CH to each end of the B10k PAN pot (PL, PR, on the faceplate), wiper to GND, "
                         "each end through 100k into its bus. SEND taps CH after the mute (post-fader).", 10)
    pg.text(40, Y(1100), "LV, CH, PL, PR, SD are header pins to the faceplate; SUM_L, SUM_R, SUM_S are the bus summing "
                         "nodes on the next page.", 10)
    return pg


def stereo_block(pg, P, c, x0, t0):
    """Stereo channel c: two mute inputs and followers, 200k into each bus, (L + R) / 2 to the SEND pot."""
    r = 100 * c
    pg.text(x0, Y(t0), f"Channel {c} (stereo)", 12)
    yl = Y(t0 + 70)
    nodes = {}
    for side, y in (("L", yl), ("R", yl + 130)):
        nodes[side] = channel_input(pg, P, f"{c}{side}", x0, y)
    xc = nodes["L"][0] + 40
    for side, rb, bus in (("L", r + 3, "SUM_L"), ("R", r + 4, "SUM_R")):
        nx, ny = nodes[side]
        pg.wire([(nx, ny), (xc, ny)], f"CH{c}{side}")
        a = hpart(pg, P[f"R{rb}"], xc, ny)
        pg.stub_port(a["2"], bus, "OUT", "right")
    nyl, nyr = nodes["L"][1], nodes["R"][1]
    a_l = vpart(pg, P[f"R{r + 5}"], xc, nyl + 20, top_pin="1")
    a_r = vpart(pg, P[f"R{r + 6}"], xc, nyr - 60, top_pin="2")
    pg.wire([(xc, nyl), a_l["1"]], f"CH{c}L")
    pg.wire([a_r["1"], (xc, nyr)], f"CH{c}R")
    av = (xc, (nyl + nyr) // 2)
    pg.wire([a_l["2"], av], f"AV{c}")
    pg.wire([a_r["2"], av], f"AV{c}")
    pg.wire([av, (xc + 60, av[1])], f"AV{c}")
    pg.port(xc + 60, av[1], f"AV{c}", "OUT", "right")
    a_sd = hpart(pg, P[f"R{r + 7}"], x0 + 40, nyr + 130)
    pg.wire([(x0 + 20, nyr + 130), a_sd["1"]], f"SD{c}")
    pg.port(x0 + 20, nyr + 130, f"SD{c}", "IN", "left")
    pg.stub_port(a_sd["2"], "SUM_S", "OUT", "right")


def bus_rows(pg, P):
    """Summers, the MASTER loop through the faceplate and the output stages."""
    x_in = 760
    pg.text(x_in - 80, Y(40), "Buses: inverting summers (100k || 22p); MASTER (dual pot on the faceplate) between MIX "
                              "and MST; output stages x2 (L, R) and x1 (SEND), 1k to the jacks", 12)
    for side, t, (rf, cf), (rin, rfb, rs), out in (
            ("L", 200, ("R901", "C901"), ("R904", "R905", "R906"), "OUT_L"),
            ("R", 470, ("R902", "C902"), ("R907", "R908", "R909"), "OUT_R"),
            ("S", 740, ("R903", "C903"), ("R910", "R911", "R912"), "SEND")):
        y = Y(t)
        u, sec = circuit.opamp_of("SUM", side)
        amp, jn, kn = inverting(pg, u, sec, x_in, y, P[rf], P[cf])
        pg.wire([(x_in - 40, y), jn], f"SUM_{side}")
        pg.port(x_in - 40, y, f"SUM_{side}", "IN", "left")
        a_in = hpart(pg, P[rin], kn[0] + 150, kn[1] + 30)
        if side == "S":                      # the send bus feeds its inverter directly
            pg.wire([kn, (kn[0] + 130, kn[1]), (kn[0] + 130, kn[1] + 30), a_in["1"]], "MIX_S")
        else:                                # MIX out to the MASTER pot top, MST back from its wiper
            pg.wire([kn, (kn[0] + 40, kn[1])], f"MIX_{side}")
            pg.port(kn[0] + 40, kn[1], f"MIX_{side}", "OUT", "right")
            pg.wire([(kn[0] + 130, kn[1] + 30), a_in["1"]], f"MST_{side}")
            pg.port(kn[0] + 130, kn[1] + 30, f"MST_{side}", "IN", "left")
        uo, so = circuit.opamp_of("OUT", side)
        amp2, jn2, kn2 = inverting(pg, uo, so, kn[0] + 210, kn[1] + 30, P[rfb])
        pg.wire([a_in["2"], jn2], f"NO_{side}")
        a_s = hpart(pg, P[rs], kn2[0] + 20, kn2[1])
        pg.wire([kn2, a_s["1"]], f"OA_{side}")
        pg.stub_port(a_s["2"], out, "OUT", "right")


def inputs_block(pg, P, x0, t0):
    pg.text(x0, Y(t0), "Return, drums, FX IN (from the faceplate) into the buses", 12)
    for i, (ref, a, b) in enumerate((("R913", "RW_L", "SUM_L"), ("R914", "RW_R", "SUM_R"), ("R915", "DRW", "SUM_L"),
                                     ("R916", "DRW", "SUM_R"), ("R917", "FXI", "SUM_S"))):
        y = Y(t0 + 40 + 40 * i)
        p = hpart(pg, P[ref], x0 + 80, y)
        pg.stub_port(p["1"], a, "IN", "left")
        pg.stub_port(p["2"], b, "OUT", "right")


def stereo_page(pr, P):
    pg = MPage(pr, "Main board: stereo channels, buses, outputs", 2)
    pg.page_count = "4"
    stereo_block(pg, P, 7, 40, 60)
    stereo_block(pg, P, 8, 40, 440)
    inputs_block(pg, P, 40, 840)
    bus_rows(pg, P)
    pg.text(40, Y(1080), "Stereo channels: IN R takes IN L when unpatched (faceplate). One button mutes both sides "
                         "(two PhotoMOS, LEDs in series). SEND gets (L + R) / 2 through the two 10k.", 10)
    pg.text(40, Y(1100), "Every path inverts twice: all outputs are in phase with all inputs, so Clouds' wet signal "
                         "returns in phase with the dry channel.", 10)
    return pg


def latch_block(pg, P, k, x0, t0):
    """Pull-up, debounce, LED / PhotoMOS current path of channel k."""
    pg.text(x0, Y(t0), f"MUTE {k}", 11)
    y = Y(t0 + 40)
    rp = find(P, "R", "2", f"BTN{k}")
    rd = find(P, "R", "1", f"BTN{k}")
    cd = find(P, "C", "1", f"DB{k}")
    rl = find(P, "R", "1", f"QK{k}")
    a = hpart(pg, rp, x0 + 40, y)
    pg.stub_port(a["1"], "+12V", "IN", "left")
    jb = (x0 + 100, y)
    pg.wire([a["2"], jb], f"BTN{k}")
    b = hpart(pg, rd, x0 + 120, y)
    pg.wire([jb, b["1"]], f"BTN{k}")
    pg.wire([jb, (x0 + 100, y - 25), (x0 + 120, y - 25)], f"BTN{k}")
    pg.port(x0 + 120, y - 25, f"BTN{k}", "IN", "right")
    jd = (x0 + 180, y)
    pg.wire([b["2"], jd], f"DB{k}")
    c = vpart(pg, cd, x0 + 180, y + 20)
    pg.wire([jd, c["1"]], f"DB{k}")
    pg.stub_gnd(c["2"], "down", 10)
    pg.wire([jd, (x0 + 220, y)], f"DB{k}")
    pg.port(x0 + 220, y, f"DB{k}", "OUT", "right")
    yl = y + 100
    d = hpart(pg, rl, x0 + 40, yl)
    pg.stub_port(d["1"], f"QK{k}", "IN", "left")
    ks = circuit.PHOTOMOS[k]
    led = pg.place(ks[0], "PHOTOMOS", x0 + 100, yl + 20, unit=1, des=(8, 4, "LEFT_BOTTOM"), name=False)
    pg.wire([d["2"], (x0 + 100, yl)], f"LA{k}")
    last = led["2"]
    if len(ks) == 2:
        led2 = pg.place(ks[1], "PHOTOMOS", x0 + 100, yl + 80, unit=1, des=(8, 4, "LEFT_BOTTOM"), name=False)
        pg.wire([last, led2["1"]], f"LM{k}")
        last = led2["2"]
    pg.wire([last, (last[0], last[1] + 20), (last[0] + 40, last[1] + 20)], f"LED{k}")
    pg.port(last[0] + 40, last[1] + 20, f"LED{k}", "OUT", "right")


def chip(pg, P, ref, x, y):
    """A logic chip with every pin on a net port."""
    dev = dev_of(P[ref])
    s = pg.place(ref, dev, x, y, des=(-50, -62, "LEFT_BOTTOM"), value_at=(-50, 68, "LEFT_BOTTOM"))
    geo = pg.pr.symgeo[pg.pr.sym_of(dev)]
    outputs = ("3", "4", "10", "11") if ref in ("U5", "U6") else ("1", "2", "12", "13")
    for p in geo["pins"]:
        num = p["num"]
        net = P[ref].nets[num]
        side = "left" if p["x"] < 0 else "right"
        # GND pins as net ports too (ports connect by name): ground flags would crowd the next pins
        pg.stub_port(s[num], net, "OUT" if num in outputs else "IN", side)


def latch_page(pr, P):
    pg = MPage(pr, "Main board: mute latch", 3)
    pg.page_count = "4"
    pg.text(40, Y(30), "Mute latch, per channel: button (to GND_F on the faceplate) with a 100k pull-up, 10k / 100n "
                       "debounce, CD4093 Schmitt NAND, CD4013 toggle (D = /Q). Q high = muted: Q -> 1k5 -> "
                       "PhotoMOS LED(s) -> button LED -> GND_F, about 4-5 mA.", 11)
    for i, k in enumerate(circuit.MONO + circuit.STEREO):
        col, row = i % 2, i // 2
        latch_block(pg, P, k, 50 + col * 380, 80 + row * 250)
    for i, ref in enumerate(("U5", "U6", "U7", "U8", "U9", "U10")):
        col, row = i % 2, i // 2
        chip(pg, P, ref, 1000 + col * 330, Y(170 + row * 290))
    # power-on reset: C906 from +12 V, R920 to GND, D903 empties C906 at power-off
    x0, t0 = 1000, 950
    pg.text(x0 - 60, Y(t0 - 50), "Power-on reset: POR high for ~100 ms, every channel starts unmuted", 11)
    y = Y(t0)
    c = vpart(pg, P["C906"], x0, y)
    pg.wire([c["1"], (x0, y - 15), (x0 - 20, y - 15)], "+12V")
    pg.port(x0 - 20, y - 15, "+12V", "IN", "left")
    jp = (x0, y + 60)
    pg.wire([c["2"], jp], "POR")
    r = vpart(pg, P["R920"], x0, y + 80)
    pg.wire([jp, r["1"]], "POR")
    pg.stub_gnd(r["2"], "down", 10)
    dd = vpart(pg, P["D903"], x0 + 80, y + 10, top_pin="1")
    pg.wire([dd["1"], (x0 + 80, y - 15), (x0 + 100, y - 15)], "+12V")
    pg.port(x0 + 100, y - 15, "+12V", "IN", "right")
    pg.wire([jp, (x0 + 80, y + 60), dd["2"]], "POR")
    pg.wire([jp, (x0 - 40, y + 60)], "POR")
    pg.port(x0 - 40, y + 60, "POR", "OUT", "left")
    return pg


def power_page(pr, P):
    pg = MPage(pr, "Main board: power, decoupling, headers", 4)
    pg.page_count = "4"
    x0, t0 = 80, 120
    pg.text(x0 - 40, Y(t0 - 70), "Power: 16-pin Eurorack header (red stripe = pin 1 = -12 V), series 1N5819 per rail, "
                                 "10R, 10 uF", 12)
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J18", "HDR16", xh, yh, des=(-30, -45, "LEFT_BOTTOM"), value_at=(-30, 52, "LEFT_BOTTOM"))
    for side, pins, sgn in (("left", ("3", "5", "7", "9"), -1), ("right", ("4", "6", "8", "10"), 1)):
        bx = xh + sgn * 45
        pts = []
        for n in pins:
            p = h[n]
            pg.wire([p, (bx, p[1])], "GND")
            pts.append((bx, p[1]))
        for a, b in zip(pts, pts[1:]):
            pg.wire([a, b], "GND")
        mid = pts[2]
        pg.wire([mid, (bx + sgn * 15, mid[1])], "GND")
        pg.gnd(bx + sgn * 15, mid[1], 90 if sgn > 0 else 270)
    pg.stub_port(h["1"], "N12_IN", "OUT", "left", 30)
    pg.stub_port(h["2"], "N12_IN", "OUT", "right", 30)
    pg.stub_port(h["11"], "P12_IN", "OUT", "left", 30)
    pg.stub_port(h["12"], "P12_IN", "OUT", "right", 30)
    xa = x0 + 330
    for k, (port, d, r, c, rail) in enumerate((("P12_IN", "D901", "R918", "C904", "+12V"),
                                               ("N12_IN", "D902", "R919", "C905", "-12V"))):
        y = Y(t0 + 10 + 120 * k)
        plus = rail == "+12V"
        dp = hpart(pg, P[d], xa, y, left_pin="2" if plus else "1")
        pg.wire([(xa - 20, y), dp["2" if plus else "1"]], port)
        pg.port(xa - 20, y, port, "IN", "left")
        mid = "P12_D" if plus else "N12_D"
        rp = hpart(pg, P[r], xa + 60, y)
        pg.wire([dp["1" if plus else "2"], rp["1"]], mid)
        jn = (xa + 130, y)
        pg.wire([rp["2"], jn], rail)
        pg.wire([jn, (xa + 160, y)], rail)
        pg.port(xa + 160, y, rail, "OUT", "right")
        cp = vpart(pg, P[c], xa + 130, y + 20, top_pin="2" if plus else "1")
        pg.wire([jn, cp["2" if plus else "1"]], rail)
        pg.stub_gnd(cp["1" if plus else "2"], "down", 10)
    # decoupling: a pair per TL074, one cap per CMOS chip
    pg.text(x0 - 40, Y(t0 + 300), "Decoupling: 100n per TL074 per rail, 100n per CMOS chip, each beside its chip", 12)
    caps = [(f"U{i + 1}", f"C{911 + 2 * i}", f"C{912 + 2 * i}") for i in range(4)]
    caps += [(f"U{5 + i}", f"C{921 + i}", None) for i in range(6)]
    for i, (u, cp, cn) in enumerate(caps):
        x, top = x0 + 20 + i * 90, Y(t0 + 350)
        a = vpart(pg, P[cp], x, top + 20)
        pg.wire([a["1"], (x, top + 5), (x - 20, top + 5)], "+12V")
        pg.port(x - 20, top + 5, "+12V", "IN", "left")
        if cn:
            b = vpart(pg, P[cn], x, top + 80)
            node = (x, top + 70)
            pg.wire([a["2"], node], "GND")
            pg.wire([node, b["1"]], "GND")
            pg.wire([node, (x - 15, top + 70)], "GND")
            pg.gnd(x - 15, top + 70, 270)
            pg.wire([b["2"], (x, top + 135), (x - 20, top + 135)], "-12V")
            pg.port(x - 20, top + 135, "-12V", "IN", "left")
        else:
            pg.stub_gnd(a["2"], "down", 10)
        pg.text(x + 8, top + 160, u, 10)
    # headers (female sockets on this board)
    pg.text(x0 - 40, Y(700), "Board-to-board headers, female sockets on this board (pin 1 marked); the faceplate "
                             "has the male pins", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        x, y = 140 + k * 165, Y(830 + (20 if len(pins) > 8 else 0))
        hh = pg.place(ref, kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        for num, net in P[ref].nets.items():
            if net == "GND":
                pg.stub_gnd(hh[num], "left", 15)
            else:
                pg.stub_port(hh[num], net, "IN", "left")
    return pg


# ------------------------------------------------------------------ faceplate pages
def single_pot(pg, part, px, py, label):
    """Library pot symbol, Plaitsy-style: lugs 4 / 5 joined to GND_F underneath."""
    p = pg.place(part.ref, dev_of(part), px, py, des=(8, -22, "LEFT_BOTTOM"), value_at=(8, -12, "LEFT_BOTTOM"))
    pg.text(px - 40, py + 36, label, 10)
    nets = part.nets
    for num, side in (("3", "left"), ("1", "right")):
        if nets[num] == "GND_F":
            pg.stub_flag(p[num], "GND_F", side, 15)
        else:
            pg.stub_port(p[num], nets[num], "IN", side)
    pg.wire([p["4"], (p["4"][0] - 10, p["4"][1]), (p["4"][0] - 10, p["4"][1] + 15), (p["5"][0] + 10, p["5"][1] + 15),
             (p["5"][0] + 10, p["5"][1]), p["5"]], "GND_F")
    pg.wire([(p["5"][0] + 10, p["5"][1] + 15), (p["5"][0] + 10, p["5"][1] + 25)], "GND_F")
    pg.flag(p["5"][0] + 10, p["5"][1] + 25, 0, "GND_F")
    w = p["2"]
    pg.wire([w, (w[0], w[1] - 15), (w[0] - 20, w[1] - 15)], nets["2"])
    if nets["2"] == "GND_F":
        pg.flag(w[0] - 20, w[1] - 15, 270, "GND_F")
    else:
        pg.port(w[0] - 20, w[1] - 15, nets["2"], "OUT", "left")
    return p


def jack_drawn(pg, part, jx, jy):
    j = pg.place(part.ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
    pg.text(jx - 25, jy + 30, part.label, 10)
    s = j["1"]
    pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND_F")
    pg.flag(s[0] + 20, s[1] - 20, 90, "GND_F")
    tn = part.nets.get("2")
    if tn == "GND_F":
        pg.stub_flag(j["2"], "GND_F", "right", 20)
    elif tn:
        pg.stub_port(j["2"], tn, "IN", "right")
    x, y = j["3"]
    pg.wire([(x, y), (x + 100, y)], part.nets["3"])
    pg.port(x + 100, y, part.nets["3"], "IN" if tn is None else "OUT", "right")


def faceplate_jacks_page(pr, P):
    pg = MPage(pr, "Faceplate: jacks and pots", 1)
    pg.page_count = "2"
    pg.text(60, Y(40), "Jacks (Thonkiconn): sleeves to GND_F, unpatched inputs grounded by the switch lug; IN 7 R, "
                       "IN 8 R and RETURN R follow their L input; outputs leave the lug open", 12)
    jacks = sorted((p for p in P.values() if p.kind == "JACK"), key=lambda p: int(p.ref[1:]))
    for i, part in enumerate(jacks):
        col, row = divmod(i, 6)
        jack_drawn(pg, part, 100 + col * 250, Y(130 + row * 105))
    pg.text(930, Y(40), "Pots (Alpha 9 mm): pin 3 = CW end, lugs to GND_F", 12)
    pots = sorted((p for p in P.values() if p.kind == "POT"), key=lambda p: int(p.ref[2:]))
    for i, part in enumerate(pots):
        col, row = divmod(i, 7)
        single_pot(pg, part, 990 + col * 225, Y(140 + row * 130), part.label)
    return pg


def faceplate_controls_page(pr, P):
    pg = MPage(pr, "Faceplate: dual pots, mute buttons, headers", 2)
    pg.page_count = "2"
    pg.text(60, Y(40), "Dual-gang pots (Alpha 9 mm, A100k): gang A = L (pins 1-3, nearer the shaft), gang B = R "
                       "(4-6), lugs 7 / 8 to GND_F", 12)
    for i, part in enumerate(p for p in P.values() if p.kind == "POT2"):
        x, y = 160 + i * 380, Y(150)
        pg.text(x - 60, y - 50, part.label, 11)
        for unit, dx in ((1, 0), (2, 170)):
            p = pg.place(part.ref, "POT2", x + dx, y, unit=unit, des=(8, -30, "LEFT_BOTTOM"),
                         value_at=(8, -40, "LEFT_BOTTOM"))
            cw, w, ccw = ("3", "2", "1") if unit == 1 else ("6", "5", "4")
            pg.wire([p[cw], (p[cw][0], p[cw][1] - 10), (p[cw][0] + 30, p[cw][1] - 10)], part.nets[cw])
            pg.port(p[cw][0] + 30, p[cw][1] - 10, part.nets[cw], "IN", "right")
            pg.stub_port(p[w], part.nets[w], "OUT", "right")
            pg.stub_flag(p[ccw], "GND_F", "down", 10)
            if unit == 1:
                for lug in ("7", "8"):
                    pg.stub_flag(p[lug], "GND_F", "left", 10)
    pg.text(60, Y(330), "Mute buttons: Thonk low-profile LED buttons. Contacts 1+2 to GND_F, 3+4 to the pull-up on "
                        "the main board; the LED (5 / 6) lights when the channel is muted", 12)
    for i, (ref, label, k) in enumerate(circuit.BUTTONS):
        col, row = i % 4, i // 4
        bx, by = 160 + col * 380, Y(430 + row * 150)
        s = pg.place(ref, "SWLED", bx, by, des=(-50, -42, "LEFT_BOTTOM"), name=False)
        pg.text(bx - 50, by + 48, label, 9)
        gx = s["1"][0] - 15
        pg.wire([s["1"], (gx, s["1"][1])], "GND_F")
        pg.wire([s["2"], (gx, s["2"][1])], "GND_F")
        pg.wire([(gx, s["1"][1]), (gx, s["2"][1])], "GND_F")
        pg.wire([(gx, s["1"][1]), (gx, s["1"][1] - 10)], "GND_F")
        pg.flag(gx, s["1"][1] - 10, 180, "GND_F")
        net = P[ref].nets["3"]
        nx = s["3"][0] + 15
        pg.wire([s["3"], (nx, s["3"][1])], net)
        pg.wire([s["4"], (nx, s["4"][1])], net)
        pg.wire([(nx, s["3"][1]), (nx, s["4"][1])], net)
        pg.wire([(nx, s["4"][1]), (nx + 20, s["4"][1])], net)
        pg.port(nx + 20, s["4"][1], net, "OUT", "right")
        pg.stub_port(s["5"], P[ref].nets["5"], "IN", "left")
        pg.stub_flag(s["6"], "GND_F", "right", 15)
    pg.text(60, Y(760), "Headers to the main board (male pins here); pin 1 at the top", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        fr = circuit.fb_ref(ref)
        x, y = 140 + k * 165, Y(890 + (20 if len(pins) > 8 else 0))
        h = pg.place(fr, kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        for num, net in P[fr].nets.items():
            if net == "GND_F":
                pg.stub_flag(h[num], "GND_F", "left", 15)
            else:
                pg.stub_port(h[num], net, "IN", "left")
    return pg


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
    problems = []
    for p in parts:
        for pid in p.nets:
            if seen[(p.ref, pid)] != 1:
                problems.append(f"{p.ref}.{pid} drawn {seen[(p.ref, pid)]} times")
    return problems


def part_info(pages):
    """ref -> device key, schematic Unique ID and the PCB's Channel ID ('$' + page number + id of the
    part's first schematic component)."""
    info = {}
    for pg in pages:
        for c in pg.comps:
            if c["ref"] and c["ref"] not in info:
                info[c["ref"]] = {"dev": c["dev"], "uid": pg.pr.unique_id(c["ref"]),
                                  "channel": f"${pg.number}{c['cid']}"}
    return info


def preview_name(title):
    board, _, rest = title.partition(": ")
    return (board.split()[0] + "-" + rest.split(",")[0]).lower().replace(" ", "-")


def main():
    pr = MProject()
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    main_pages = [mono_page(pr, PM), stereo_page(pr, PM), latch_page(pr, PM), power_page(pr, PM)]
    fp_pages = [faceplate_jacks_page(pr, PF), faceplate_controls_page(pr, PF)]
    bad = coverage(main_pages, mb) + coverage(fp_pages, fb)
    for pg, parts in [(p, mb) for p in main_pages] + [(p, fb) for p in fp_pages]:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    for b in bad:
        print("PROBLEM:", b)
    board_fb = pcb.faceplate_board(pr, fb, part_info(fp_pages), circuit)
    board_mb = pcb.main_board(pr, mb, part_info(main_pages), circuit)
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb, circuit))
    for b in pcb_bad:
        print("PCB:", b)
    template = pcb.load_template(ee)
    panel_page = MPage(pr, "Panel", 1)
    panel_page.page_count = "1"
    panel_page.text(70, Y(60), "Stereo mixer 28HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the "
                               "bare-copper output band are in the PCB document; the art is "
                               "hardware/panel/stereo-mixer-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("Mixer Main", main_pages, board_mb), ("Mixer Faceplate", fp_pages, board_fb),
              ("Mixer Panel", [panel_page], board_panel)], OUT, template)
    for pg in main_pages + fp_pages:
        render(pr, pg, PREVIEW.format(preview_name(pg.title)))
    board_mb.render(PREVIEW.format("pcb-main-board"))
    board_fb.render(PREVIEW.format("pcb-faceplate"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in main_pages + fp_pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(main_pages) + len(fp_pages)} pages, "
          f"{len(bad)} schematic problems; {len(board_mb.placed)} + {len(board_fb.placed)} parts placed on the "
          f"PCBs, {len(pcb_bad)} PCB problems")


if __name__ == "__main__":
    main()
