"""Atlasy as an EasyEDA Pro project (.epro2): schematic pages, both PCBs
placed (not routed), and the panel PCB.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the
file format, the connectivity check and the previews, the way Side FXy and
the mixer do. Library parts from your MorrisSynth caches: the TL074ACN
symbol, WQP518MA jack, PTV09A pot symbol, the 1N5819's diode symbol, the
LR1F / FG28 attributes the SMD resistors and capacitors are cloned from,
net ports, ground flag, sheet frame (plaitsy/hardware/easyeda/
morrissynth-parts.epru) and the 2x8 box header (stereo-mixer-parts.epru).

This is the first SMD module. The rear of both boards is SMD for JLC's
assembly; the panel parts and the headers are through-hole. Generated here:
  footprints  0603 and 1206 passives, SOD-123, SOT-23 and SOIC-16 (the pad
              geometry of the LCSC footprints in your MorrisSynth project),
              SOIC-14 on the same pattern, the Alpha 9 mm pot, the Dailywell
              2M toggles (terminals 2.79 mm apart, poles 5.08 mm), 1x8
              headers
  symbols     SSI2164 (four cells and a power unit), AS3360 (two VCAs and a
              common unit), BC847 / BC857, the two toggles, the 1x8 header

Pages: main board 1 (channels 1, 2), 2 (channels 3, 4), 3 (resonance
cells, scanner, power, decoupling, headers); faceplate 1 (jacks, knobs,
toggles), 2 (FREQ / RES summers, output resistors, headers); panel note.
Net ports with the same name connect within a board; nets that cross
between the boards are the header pins.

Run from atlas/hardware/tools:  python easyeda_export.py
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
            os.path.normpath(os.path.join(HERE, "..", "..", "..", "stereo-mixer", "hardware", "easyeda",
                                          "stereo-mixer-parts.epru"))]


def _load(name):
    spec = importlib.util.spec_from_file_location("atlas_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")
SECTION, CELL = circuit.SECTION, circuit.CELL

NAME = "Atlasy"
OUT = os.path.join(HERE, "..", "easyeda", "Atlasy.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "atlas-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil

# Library devices used as they are, or as the source of attributes (uuids from the two caches)
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0: symbol and attribute set for the SMD resistors
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00: the same for the capacitors
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol; footprint replaced below)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "POT": "be9d2c8f5f814271a402f956f18b56f9",       # PTV09A-4025F-B103 (its symbol)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819: the diode symbol (1 = cathode)
    "HDR16": "bbe47e9fd91b42bbaf0d36b9504a3a5e",     # DC3-2.54-16PAS, 2x8 box header
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here

# SMD values: UNI-ROYAL 0603WAF thick-film 1 % resistors (the part number follows from the value),
# Samsung CL-series MLCCs. JLC's BOM tool matches these part numbers; the LCSC numbers are left to it.
R_CODE = {"10R": "100J", "100R": "1000", "220R": "2200", "1k": "1001", "2k": "2001", "2.7k": "2701",
          "3k": "3001", "6.2k": "6201", "9.1k": "9101", "10k": "1002", "11k": "1102", "12k": "1202",
          "13k": "1302", "15k": "1502", "20k": "2002", "24k": "2402", "39k": "3902", "43k": "4302",
          "47k": "4702", "51k": "5102", "75k": "7502", "82k": "8202", "100k": "1003", "220k": "2203",
          "240k": "2403"}
C_SMD = {"22p": ("CL10C220JB8NNNC", "22pF", "C0G", "50V", "0603"),
         "220p": ("CL10C221JB8NNNC", "220pF", "C0G", "50V", "0603"),
         "1n2": ("CL10C122JB8NNNC", "1.2nF", "C0G", "50V", "0603"),
         "4n7": ("CL10B472KB8NNNC", "4.7nF", "X7R", "50V", "0603"),
         "100n": ("CL10B104KB8NNNC", "100nF", "X7R", "50V", "0603"),
         "10u": ("CL31A106KAHNNNE", "10uF", "X5R", "25V", "1206")}

# ---------------------------------------------------------------- footprints
LAYERS = [(1, "TOP", "Top Layer", "#FF0000", "#7F0000"), (2, "BOTTOM", "Bottom Layer", "#0000FF", "#00007F"),
          (3, "TOP_SILK", "Top Silkscreen Layer", "#FFCC00", "#7F6600"),
          (4, "BOT_SILK", "Bottom Silkscreen Layer", "#66CC33", "#336619"),
          (7, "TOP_PASTE_MASK", "Top Paste Mask Layer", "#808080", "#404040"),
          (8, "BOT_PASTE_MASK", "Bottom Paste Mask Layer", "#800000", "#400000"),
          (5, "TOP_SOLDER_MASK", "Top Solder Mask Layer", "#800080", "#400040"),
          (6, "BOT_SOLDER_MASK", "Bottom Solder Mask Layer", "#AA00FF", "#55007F"),
          (13, "DOCUMENT", "Document Layer", "#FFFFFF", "#7F7F7F"),
          (48, "COMPONENT_SHAPE", "Component Shape Layer", "#FFFFFF", "#7F7F7F"),
          (11, "OUTLINE", "Board Outline Layer", "#FF00FF", "#7F007F"),
          (12, "MULTI", "Multi-Layer", "#C0C0C0", "#606060")]


class Footprint:
    """A footprint in mm, written as an EasyEDA Pro FOOTPRINT doc. Through-hole pads are round (or
    square) with round holes, or oval with slot holes (slot=(w, h)); SMD pads (smd=True) are rectangles
    or ovals on the top layer, as in the LCSC footprints of your projects. The courtyard (layer 48) is
    what the placement checks use as the part's body."""

    def __init__(self, title, designator="U?"):
        self.title, self.designator = title, designator
        self.pads, self.silk, self.court = [], [], None
        self.doc = Doc("FOOTPRINT")

    def pad(self, num, x, y, hole=1.0, size=1.7, square=False, h=None, slot=None):
        self.pads.append((str(num), x, y, hole, size, h or size, square, slot, False))

    def smd(self, num, x, y, w, h, oval=False):
        self.pads.append((str(num), x, y, None, w, h, not oval, None, True))

    def line(self, x1, y1, x2, y2):
        self.silk.append(("L", (x1, y1, x2, y2)))

    def rect(self, x1, y1, x2, y2):
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)), ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
            self.line(*a, *b)

    def circle(self, x, y, r):
        self.silk.append(("C", (x, y, r)))

    def courtyard(self, x1, y1, x2, y2):
        self.court = (x1, y1, x2, y2)

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
            d.add("POLY", d.nid(), {"groupId": 0, "netName": "", "layerId": 3, "width": 6, "path": path,
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        if self.court:
            x1, y1, x2, y2 = self.court
            d.add("POLY", d.nid(), {"groupId": 0, "netName": "", "layerId": 48, "width": 2,
                                    "path": [m(x1), m(y1), "L", m(x1), m(y2), m(x2), m(y2), m(x2), m(y1), m(x1), m(y1)],
                                    "locked": False, "zIndex": d.zi(), "polyType": "NORMAL"})
        for num, x, y, hole, pw, ph, square, slot, smd in self.pads:
            if smd:
                pad = {"padType": "RECT", "width": m(pw), "height": m(ph), "radius": 0} if square else \
                      {"padType": "OVAL", "width": m(pw), "height": m(ph)}
                layer, hl, plated = 1, None, True
                exp = {"topSolderExpansion": 2, "bottomSolderExpansion": 2, "topPasteExpansion": None,
                       "bottomPasteExpansion": None}
            else:
                if slot:
                    pad = {"padType": "OVAL", "width": m(pw), "height": m(ph)}
                    hl = {"holeType": "SLOT", "width": m(slot[0]), "height": m(slot[1])}
                else:
                    pad = {"padType": "RECT", "width": m(pw), "height": m(ph), "radius": 0} if square else \
                          {"padType": "ELLIPSE", "width": m(pw), "height": m(ph)}
                    hl = {"holeType": "ROUND", "width": m(hole), "height": m(hole)}
                layer, plated = 12, True
                exp = {"topSolderExpansion": None, "bottomSolderExpansion": None, "topPasteExpansion": None,
                       "bottomPasteExpansion": None}
            d.add("PAD", d.nid(), {"groupId": 0, "netName": "", "layerId": layer, "num": num, "centerX": m(x),
                                   "centerY": m(y), "padAngle": 0, "hole": hl,
                                   "defaultPad": pad, "specialPad": [], "padOffsetX": 0, "padOffsetY": 0,
                                   "relativeAngle": 0, "plated": plated, "padType": "NORMAL", **exp,
                                   "locked": False, "zIndex": d.zi(), "connectMode": None, "spokeSpace": None,
                                   "spokeWidth": None, "spokeAngle": None, "padLen": 0})
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


def fp_chip(title, designator, half, pw, ph, body, court):
    """Two-pad chip part (0603, 1206): pads at x = -half / +half (pad 1 left), body outline as two silk
    lines along it, courtyard round it."""
    f = Footprint(title, designator)
    f.smd(1, -half, 0, pw, ph)
    f.smd(2, half, 0, pw, ph)
    bx, by = body
    f.line(-bx / 2 + 0.3, by / 2 + 0.15, bx / 2 - 0.3, by / 2 + 0.15)
    f.line(-bx / 2 + 0.3, -by / 2 - 0.15, bx / 2 - 0.3, -by / 2 - 0.15)
    f.courtyard(-court[0] / 2, -court[1] / 2, court[0] / 2, court[1] / 2)
    return f


def fp_sod123():
    """SOD-123: pad 1 (cathode) left, the band on that side."""
    f = Footprint("SOD-123", "D?")
    f.smd(1, -1.635, 0, 0.91, 1.22)
    f.smd(2, 1.635, 0, 0.91, 1.22)
    f.rect(-1.0, -0.9, 1.0, 0.9)
    f.line(-0.65, -0.9, -0.65, 0.9)
    f.courtyard(-2.35, -1.05, 2.35, 1.05)
    return f


def fp_sot23():
    """SOT-23 as your LCSC SOT-23_L2.9-W1.3-P1.90-LS2.4-BR: pins 1 and 2 on the right at y -0.95 / +0.95,
    pin 3 alone on the left."""
    f = Footprint("SOT-23-3", "Q?")
    f.smd(1, 1.15, -0.95, 1.0, 0.8)
    f.smd(2, 1.15, 0.95, 1.0, 0.8)
    f.smd(3, -1.15, 0.0, 1.0, 0.8)
    f.line(-0.7, -1.5, 0.3, -1.5)
    f.line(-0.7, 1.5, 0.3, 1.5)
    f.line(-0.7, -1.5, -0.7, -0.65)
    f.line(-0.7, 1.5, -0.7, 0.65)
    f.courtyard(-1.75, -1.6, 1.75, 1.6)
    return f


def fp_soic(n):
    """SOIC-n, 3.9 mm body, 1.27 mm pitch, pad rows 5.47 mm apart (your LCSC SOIC-16_L9.9-W3.9-P1.27-LS6.0):
    pin 1 bottom-left, counting anticlockwise, oval 0.6 x 1.97 pads."""
    f = Footprint(f"SOIC-{n}_W3.9-P1.27", "U?")
    half = n // 2
    x0 = -(half - 1) * 0.635
    for i in range(half):
        f.smd(i + 1, x0 + i * 1.27, -2.736, 0.602, 1.971, oval=True)
        f.smd(n - i, x0 + i * 1.27, 2.736, 0.602, 1.971, oval=True)
    hx = half * 0.635 + 0.3
    f.rect(-hx, -1.52, hx, 1.52)
    f.circle(-hx + 0.6, -1.0, 0.25)
    f.courtyard(-hx - 0.2, -3.95, hx + 0.2, 3.95)
    return f


def fp_header(n):
    f = Footprint(f"HDR-1x{n}-P2.54", "H?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.27, -1.27, x0 + (n - 1) * 2.54 + 1.27, 1.27)
    return f


def fp_alpha_pot():
    """Alpha 9 mm vertical pot (RD901F) in the PTV09A frame: pins 1-3 at y = -3.5, the shaft 7.5 mm from
    them at y = +4.0, the mounting lugs on the shaft line at +-4.8 (the mixer's footprint)."""
    f = Footprint("POT-ALPHA-9MM-RD901F", "RV?")
    for i, x in enumerate((-2.5, 0.0, 2.5)):
        f.pad(i + 1, x, -3.5, 1.0, 1.8, square=(i == 0))
    for num, x in (("4", -4.8), ("5", 4.8)):
        f.pad(num, x, 4.0, size=2.7, h=3.2, slot=(1.1, 1.8))
    f.rect(-4.75, -2.5, 4.75, 8.85)
    f.circle(0, 4.0, 3.5)
    return f


def fp_toggle(dpdt):
    """Dailywell 2M sub-mini toggle, PC pins: terminals 2.79 mm apart in a row along y (the lever's throw),
    the second pole's row 5.08 mm beside the first (catalogue drawing: .110 / .200 in); flat 1.52 x 0.51
    pins in slots. Origin on the bushing, which sits over the middle terminal (row). Pole A = 1, 2, 3,
    pole B = 4, 5, 6 with 1 / 4 at +y. Body 8.13 x 5.08 (SPDT) or 8.13 x 9.14 (DPDT). Check the
    footprint against the part before ordering."""
    f = Footprint("TOGGLE-DAILYWELL-2M-" + ("DPDT" if dpdt else "SPDT"), "SW?")
    cols = [(-2.54, ("1", "2", "3")), (2.54, ("4", "5", "6"))] if dpdt else [(0.0, ("1", "2", "3"))]
    for x, nums in cols:
        for num, y in zip(nums, (2.79, 0.0, -2.79)):
            f.pad(num, x, y, size=2.3, h=1.7, slot=(1.8, 0.8))
    hw = 4.57 if dpdt else 2.54
    f.rect(-hw, -4.07, hw, 4.07)
    f.circle(0, 0, 3.0)
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


class MultiSymbol:
    """A symbol with several units, in the library's style (the mixer's)."""

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
                    if rot in (0, 180):
                        nx, ny = x + (length / 2 if rot == 0 else -length / 2) - 2, y - 1
                    else:
                        nx, ny = x + 2, y + (length / 2 if rot == 270 else -length / 2) + 3
                    d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Name", name, x=x, y=y,
                                                        align="LEFT_BOTTOM", part=part))
                    d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Number", num, vv=True, x=nx, y=ny,
                                                        fs=6, align="LEFT_BOTTOM", part=part))
                    d.add("ATTR", d.nid(), attr_payload(d.zi(), pid, "Pin Type", "Undefined", x=x, y=y,
                                                        align="LEFT_BOTTOM", part=part))
        source = f"{new_uuid()}|{ee.USER['uuid']}"
        return d.lines({"title": self.title, "description": "", "tags": self.tags, "docType": 2, "source": source})


def ssi2164_symbol():
    """Four cells (units 1-4: current in on the left, current out on the right, control on top) and a
    power unit (5): MODE, V+, GND, V-."""
    s = MultiSymbol("SSI2164", "SSI2164", "U?", 5, [NAME])
    for n in range(1, 5):
        s.unit(n)
        iin, vc, iout = CELL[n]
        s.poly([(-20, -20), (20, 0), (-20, 20), (-20, -20)], closed=True)
        s.text(-16, 4, "2164", 6)
        s.pin(iin, f"IIN{n}", -30, 0, 0)
        s.pin(iout, f"IOUT{n}", 30, 0, 180)
        s.pin(vc, f"VC{n}", 0, -30, 270, length=20)
    s.unit(5)
    s.poly([(-30, -30), (30, -30), (30, 30), (-30, 30), (-30, -30)], closed=True)
    s.text(-22, 4, "SSI2164", 8)
    s.pin("1", "MODE", -40, 0, 0)
    s.pin("16", "V+", 0, -40, 270)
    s.pin("9", "V-", 0, 40, 90)
    s.pin("8", "GND", 20, 40, 90)
    return s


def as3360_symbol():
    """Two VCAs (units 1, 2: II left, IO right, VC on top, VE / VO below) and a common unit (3)."""
    s = MultiSymbol("AS3360", "AS3360", "U?", 3, [NAME])
    for n, pins in ((1, ("6", "2", "5", "3", "4")), (2, ("9", "13", "10", "12", "11"))):
        s.unit(n)
        ii, io, vc, ve, vo = pins
        s.poly([(-20, -20), (20, 0), (-20, 20), (-20, -20)], closed=True)
        s.text(-16, 4, "3360", 6)
        s.pin(ii, f"II{n}", -30, 0, 0)
        s.pin(io, f"IO{n}", 30, 0, 180)
        s.pin(vc, f"VC{n}", 0, -30, 270, length=20)
        s.pin(ve, f"VE{n}", -10, 30, 90, length=20)
        s.pin(vo, f"VO{n}", 10, 30, 90, length=20)
    s.unit(3)
    s.poly([(-30, -30), (30, -30), (30, 30), (-30, 30), (-30, -30)], closed=True)
    s.text(-22, 4, "AS3360", 8)
    s.pin("8", "VREF", -40, 0, 0)
    s.pin("14", "VCC", 0, -40, 270)
    s.pin("7", "VEE", 0, 40, 90)
    s.pin("1", "GND", 20, 40, 90)
    return s


def bjt_symbol(pnp):
    """BC847 / BC857 in SOT-23: 1 base (left), 3 collector, 2 emitter; the emitter at the bottom for an
    NPN, at the top for a PNP."""
    s = Symbol("BC857B" if pnp else "BC847B", "PNP.1" if pnp else "NPN.1", "Q?", [NAME])
    s.poly([(-20, 0), (-5, 0)])
    s.poly([(-5, -12), (-5, 12)])
    s.poly([(-5, -4), (10, -14), (10, -20)])
    s.poly([(-5, 4), (10, 14), (10, 20)])
    if pnp:      # arrow into the base, on the top (emitter) leg
        s.poly([(-5, -4), (2, -5), (0, -10), (-5, -4)], closed=True, fill="#000000")
        s.pin("2", "E", 10, -20, 90)
        s.pin("3", "C", 10, 20, 270)
    else:
        s.poly([(10, 14), (3, 13), (6, 8), (10, 14)], closed=True, fill="#000000")
        s.pin("3", "C", 10, -20, 90)
        s.pin("2", "E", 10, 20, 270)
    s.text(-18, -4, "B", 6)
    s.pin("1", "B", -20, 0, 0)
    return s


def spdt_symbol():
    left = [(1, "2", "COM")]
    right = [(0, "3", "UP: 2-3"), (2, "1", "DOWN: 2-1")]
    return ic_symbol("Toggle SPDT ON-ON", "SPDT.1", left, right, designator="SW?", w=35)


def dpdt_symbol():
    left = [(0, "2", "COM A"), (3, "5", "COM B")]
    right = [(0, "3", "A UP+MID"), (1, "1", "A DOWN"), (3, "6", "B UP"), (4, "4", "B MID+DOWN")]
    return ic_symbol("Toggle DPDT ON-ON-ON", "DPDT3.1", left, right, designator="SW?", w=45)


def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.3", "H?", [NAME])
    half = n * 5
    s.rect(-10, -half - 5, 10, half + 5)
    for i in range(n):
        s.pin(str(i + 1), str(i + 1), -20, -half + 5 + 10 * i, 0, show=True, edge=-10)
    return s


# ------------------------------------------------------------------ project
class MPage(Page):
    page_count = "4"

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
        vals = [("Symbol", sym), ("@Project Name", "Atlasy"), ("@Page Count", self.page_count),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", "Atlasy"),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V0.1"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", "Atlasy"),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))

    def flag(self, x, y, rot, net):
        """Ground-style flag carrying a named net (GND_F)."""
        self._flag("GND", x, y, rot, net, True)

    def ground(self, pin, net, direction="down", length=10):
        """GND on the main board, a named ground flag on the faceplate."""
        x, y = pin
        end = {"down": (x, y + length), "right": (x + length, y), "left": (x - length, y), "up": (x, y - length)}
        x2, y2 = end[direction]
        self.wire([(x, y), (x2, y2)], net)
        rot = {"down": 0, "right": 90, "left": 270, "up": 180}[direction]
        if net == "GND":
            self.gnd(x2, y2, rot)
        else:
            self.flag(x2, y2, rot, net)

    def tie(self, pin, net, side="left", kind="IN", length=20):
        """A pin to its net: a ground flag for a ground net, else a net port."""
        if net.startswith("GND"):
            self.ground(pin, net, {"left": "left", "right": "right"}[side], 10)
        else:
            self.stub_port(pin, net, kind, side, length)


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

    def _symbol(self, sym):
        lines = sym.build()
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(sym.doc.uuid, lines)
        return sym.doc.uuid

    def _new_devices(self):
        fps = {"0603": self._footprint(fp_chip("R0603", "R?", 0.8, 0.8, 0.95, (1.6, 0.8), (3.1, 1.5))),
               "C0603": self._footprint(fp_chip("C0603", "C?", 0.8, 0.8, 0.95, (1.6, 0.8), (3.1, 1.5))),
               "1206": self._footprint(fp_chip("C1206", "C?", 1.5, 1.0, 1.75, (3.2, 1.6), (4.6, 2.3))),
               "SOD123": self._footprint(fp_sod123()), "SOT23": self._footprint(fp_sot23()),
               "SOIC14": self._footprint(fp_soic(14)), "SOIC16": self._footprint(fp_soic(16)),
               "POT": self._footprint(fp_alpha_pot()), "SPDT": self._footprint(fp_toggle(False)),
               "DPDT": self._footprint(fp_toggle(True)), "HDR8": self._footprint(fp_header(8))}
        r1k, c100n = self.device_attrs("R1k"), self.device_attrs("C100n")
        drop = ("3D Model", "3D Model Title", "3D Model Transform")
        for val, code in R_CODE.items():
            a = {k: v for k, v in r1k.items() if k not in drop}
            value = val.replace("R", "") + "Ω" if val.endswith("R") else val + "Ω"
            a.update({"Manufacturer": "UNI-ROYAL", "Manufacturer Part": f"0603WAF{code}T5E", "Value": value,
                      "Supplier Part": "", "Datasheet": "", "Supplier Footprint": "0603", "JLCPCB Part Class": "",
                      "Footprint": fps["0603"], "Type": "Thick Film Resistor", "Power(Watts)": "100mW",
                      "Temperature Coefficient": "±100ppm/℃", "LCSC Part Name": f"{value} ±1% 100mW 0603",
                      "Description": f"Thick-film resistor {value} ±1% 100mW, 0603"})
            self._device("R" + val, f"0603WAF{code}T5E", a, ["Resistors", "Chip Resistor - Surface Mount"])
        for val, (mpn, value, diel, volts, pkg) in C_SMD.items():
            a = {k: v for k, v in c100n.items() if k not in drop}
            a.update({"Manufacturer": "Samsung Electro-Mechanics", "Manufacturer Part": mpn, "Value": value,
                      "Supplier Part": "", "Datasheet": "", "Supplier Footprint": pkg, "JLCPCB Part Class": "",
                      "Footprint": fps["1206" if pkg == "1206" else "C0603"], "Voltage Rating": volts,
                      "Temperature Coefficient": diel, "Tolerance": "±5%" if diel == "C0G" else "±10%",
                      "LCSC Part Name": f"{value} {volts} {diel} {pkg}",
                      "Description": f"MLCC {value} {volts} {diel}, {pkg}"})
            self._device("C" + val, mpn, a, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - SMD/SMT"])
        diode = self.device_attrs("D5819")["Symbol"]
        tl074 = self.device_attrs("TL074")["Symbol"]
        pot = self.device_attrs("POT")["Symbol"]
        sym = {"SSI2164": self._symbol(ssi2164_symbol()), "AS3360": self._symbol(as3360_symbol()),
               "NPN": self._symbol(bjt_symbol(False)), "PNP": self._symbol(bjt_symbol(True)),
               "SPDT": self._symbol(spdt_symbol()), "DPDT": self._symbol(dpdt_symbol()),
               "HDR8": self._symbol(header_symbol(8))}
        new = [
            ("TL074", tl074, "TL074CDR", "U?", fps["SOIC14"], "TL074CDR",
             "Quad JFET op-amp, SOIC-14 (TL074CDR / TL074IDR)"),
            ("SSI2164", sym["SSI2164"], "SSI2164S", "U?", fps["SOIC16"], "SSI2164S-TU",
             "Sound Semiconductor quad VCA, SOIC-16 (JEDEC MS-012-AC); MODE (pin 1) open = class AB"),
            ("AS3360", sym["AS3360"], "AS3360D", "U?", fps["SOIC14"], "AS3360D",
             "Alfa dual VCA (CEM3360 clone), SOIC-14: 1 GND, 2 IO1, 3 VE1, 4 VO1, 5 VC1, 6 II1, 7 VEE, 8 VREF, "
             "9 II2, 10 VC2, 11 VO2, 12 VE2, 13 IO2, 14 VCC"),
            ("D4148", diode, "1N4148W", "D?", fps["SOD123"], "1N4148W", "Switching diode 100 V 150 mA, SOD-123"),
            ("D5819", diode, "B5819W", "D?", fps["SOD123"], "B5819W", "Schottky diode 40 V 1 A, SOD-123"),
            ("NPN", sym["NPN"], "BC847B", "Q?", fps["SOT23"], "BC847B", "NPN transistor, SOT-23 (1 B, 2 E, 3 C)"),
            ("PNP", sym["PNP"], "BC857B", "Q?", fps["SOT23"], "BC857B", "PNP transistor, SOT-23 (1 B, 2 E, 3 C)"),
            ("POT100k", pot, "Alpha 9mm B100k", "RV?", fps["POT"], "RD901F-40-15F-B100K",
             "Alpha 9 mm vertical pot B100k, 15 mm D shaft (Thonk)"),
            ("POT10k", pot, "Alpha 9mm B10k", "RV?", fps["POT"], "RD901F-40-15F-B10K",
             "Alpha 9 mm vertical pot B10k, 15 mm D shaft (Thonk)"),
            ("TOGGLE_SPDT", sym["SPDT"], "2MS1T1B1M2QES", "SW?", fps["SPDT"], "2MS1T1B1M2QES",
             "Dailywell 2M sub-mini toggle SPDT ON-ON, PC pins (Thonk): up joins 2-3, down 2-1"),
            ("TOGGLE_DPDT", sym["DPDT"], "2MD6T1B1M2QES", "SW?", fps["DPDT"], "2MD6-T1-B1-M2-Q-E-S",
             "Dailywell 2M sub-mini toggle DPDT ON-ON-ON, PC pins (Tayda): 2-3 + 5-6, 2-3 + 5-4, 2-1 + 5-4"),
            ("HDR8", sym["HDR8"], "Pin header 1x8", "H?", fps["HDR8"], "1x8 2.54 mm",
             "Board-to-board header 1x8, 2.54 mm: male on the faceplate, female socket on the main board"),
        ]
        for key, su, title, desig, fp, mpn, desc in new:
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": mpn, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "Supplier Part": "", "Description": desc}
            self._device(key, title, attrs)

    def write(self, boards, path, template):
        """boards: [(title, pages, pcb board)]; each gets a BOARD doc holding its schematic pages and its PCB."""
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
        lines += next(d for d in self.lib.values() if d["docType"] == "BLOB")["lines"]   # one BLOB doc
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Vostok Atlas clone: four SSI2164 multimode filters (AN701 pole mixing, "
                                  "bandpass-fed resonance) and an AS3360 interpolating scanner. Two stacked "
                                  "PCBs, SMD on the rear of each, 16HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


def dev_of(part):
    if part.kind == "R":
        return "R" + part.value
    if part.kind == "C":
        return "C" + part.value
    if part.kind == "POT":
        return "POT" + part.value[1:]           # B100k -> POT100k
    return part.kind


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


def other(part, net):
    """The pin of a two-pin part that is not on `net`."""
    return next(pid for pid, n in part.nets.items() if n != net)


def pin_on(part, net):
    return next(pid for pid, n in part.nets.items() if n == net)


def supply(pg, amp, part, sec):
    """Supply pins on the unit that carries them (the library TL074's unit 1)."""
    if sec == 1:
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], part.nets["4"], label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], part.nets["11"], label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))


def summer(pg, P, ref, sec, jx, y, inputs, rf, cf=None, clamp=None, out_kind="OUT"):
    """A TL074 section as an inverting summer, its summing junction column at jx: the input resistors
    hang left of the junction, one row each from y down, with a net port at their far end; Rf (and Cf)
    above, from the junction to the output column. clamp = (d_out, d_back): the precision clamp of the
    CV summers, the output diode before the output node and the second diode across the op-amp.
    Returns the output node."""
    part = P[ref]
    out, inm, inp = SECTION[sec]
    jnet = part.nets[inm]
    amp = pg.place(ref, "TL074", jx + 60, y + 10, unit=sec, des=(14, 30, "LEFT_BOTTOM"), name=False)
    pg.wire([(jx, y), amp[inm]], jnet)
    pg.ground(amp[inp], part.nets[inp], "left", 10)
    supply(pg, amp, part, sec)
    for i, r in enumerate(inputs):
        yy = y + 30 * i
        a = hpart(pg, r, jx - 60, yy, left_pin=other(r, jnet))
        pg.wire([a[pin_on(r, jnet)], (jx, yy)], jnet)
        if i:
            pg.wire([(jx, yy - 30), (jx, yy)], jnet)
        pg.stub_port(a[other(r, jnet)], r.nets[other(r, jnet)], "IN", "left")
    ox, oy = amp[out]
    kx = ox + 20
    onet = part.nets[out]
    pg.wire([(ox, oy), (kx, oy)], onet)
    if clamp:                                  # out -> D (anode at the op-amp) -> the clamped node
        d_out, d_back = clamp
        d = hpart(pg, d_out, kx, oy, left_pin="2")
        node = d["1"]
        vnet = d_out.nets["1"]
        nx = node[0] + 20
        pg.wire([node, (nx, oy)], vnet)
        db = hpart(pg, d_back, jx + 10, y - 70, left_pin="2")       # anode on the junction side
        pg.wire([(jx, y - 40), (jx, y - 70)], jnet)
        pg.wire([(jx, y - 70), db["2"]], jnet)
        pg.wire([db["1"], (kx, y - 70)], onet)
        pg.wire([(kx, oy), (kx, y - 70)], onet)
        fb_from, top = (nx, oy), vnet
    else:
        fb_from, top, nx = (kx, oy), onet, kx
    a_rf = hpart(pg, rf, jx + 20, y - 40, left_pin=pin_on(rf, jnet))
    pg.wire([(jx, y), (jx, y - 40)], jnet)
    pg.wire([(jx, y - 40), a_rf[pin_on(rf, jnet)]], jnet)
    pg.wire([a_rf[other(rf, jnet)], (fb_from[0], y - 40)], top)
    pg.wire([(fb_from[0], y - 40), fb_from], top)
    if cf is not None:
        a_cf = hpart(pg, cf, jx + 20, y - 100, left_pin=pin_on(cf, jnet))
        pg.wire([(jx, y - 40), (jx, y - 100)], jnet)
        pg.wire([(jx, y - 100), a_cf[pin_on(cf, jnet)]], jnet)
        pg.wire([a_cf[other(cf, jnet)], (fb_from[0], y - 100)], top)
        pg.wire([(fb_from[0], y - 100), (fb_from[0], y - 40)], top)
    end = (fb_from[0] + 20, fb_from[1])
    pg.wire([fb_from, end], top)
    pg.port(end[0], end[1], top, out_kind, "right")
    return fb_from


def pole(pg, P, k, n, xs, y):
    """Pole n of channel k: port P[n-1] -> 15k -> node I -> SSI2164 cell n -> integrator (220p) -> port
    P[n]; the 15k local feedback hangs below I with a port P[n]; the cell's input network stands above I;
    VC to its port."""
    r0 = 100 * k
    rin, rfb, rc, cc, ci = (P[f"R{r0 + 2 + 3 * n}"], P[f"R{r0 + 3 + 3 * n}"], P[f"R{r0 + 4 + 3 * n}"],
                            P[f"C{r0 + 1 + n}"], P[f"C{r0 + 5 + n}"])
    i_net = f"I{k}{n}"
    a = hpart(pg, rin, xs + 20, y, left_pin=other(rin, i_net))
    pg.stub_port(a[other(rin, i_net)], rin.nets[other(rin, i_net)], "IN", "left")
    ix = xs + 70
    pg.wire([a[pin_on(rin, i_net)], (ix, y)], i_net)
    cell = pg.place(f"U{k}", "SSI2164", ix + 40, y, unit=n, des=(-14, -36, "LEFT_BOTTOM"), name=False)
    iin, vc, iout = CELL[n]
    pg.wire([(ix, y), cell[iin]], i_net)
    vx, vy = cell[vc]                       # VC up past the integrator's cap row, then its port
    pg.wire([(vx, vy), (vx, vy - 30)], f"VF{k}")
    pg.stub_port((vx, vy - 30), f"VF{k}", "IN", "right", length=10)
    # the input network above I: 220R then 1n2 to ground
    r = vpart(pg, rc, ix, y - 60, top_pin=other(rc, i_net), texts_left=True)
    pg.wire([(ix, y), r[pin_on(rc, i_net)]], i_net)
    c = vpart(pg, cc, ix, y - 110, top_pin=other(cc, rc.nets[other(rc, i_net)]), texts_left=True)
    pg.wire([r[other(rc, i_net)], c[pin_on(cc, rc.nets[other(rc, i_net)])]], rc.nets[other(rc, i_net)])
    pg.ground(c[other(cc, rc.nets[other(rc, i_net)])], "GND", "up", 10)
    # the local feedback below I, its far end on the stage's output port
    fb = vpart(pg, rfb, ix, y + 20, top_pin=pin_on(rfb, i_net))
    pg.wire([(ix, y), fb[pin_on(rfb, i_net)]], i_net)
    onet = rfb.nets[other(rfb, i_net)]
    bx, by = fb[other(rfb, i_net)]
    pg.wire([(bx, by), (bx, by + 10)], onet)
    pg.stub_port((bx, by + 10), onet, "IN", "left", length=10)
    # integrator
    g_net = f"G{k}{n}"
    gx, gy = cell[iout]
    ua = circuit.UA[k]
    amp = pg.place(ua, "TL074", gx + 40, gy + 10, unit=n, des=(14, 30, "LEFT_BOTTOM"), name=False)
    out, inm, inp = SECTION[n]
    pg.wire([(gx, gy), amp[inm]], g_net)
    pg.ground(amp[inp], "GND", "down", 10)
    supply(pg, amp, P[ua], n)
    ox, oy = amp[out]
    kx = ox + 20
    pg.wire([(ox, oy), (kx, oy)], onet)
    cap = hpart(pg, ci, gx + 20, gy - 40, left_pin=pin_on(ci, g_net))
    pg.wire([(gx, gy), (gx, gy - 40)], g_net)
    pg.wire([(gx, gy - 40), cap[pin_on(ci, g_net)]], g_net)
    pg.wire([cap[other(ci, g_net)], (kx, gy - 40)], onet)
    pg.wire([(kx, gy - 40), (kx, oy)], onet)
    pg.wire([(kx, oy), (kx + 20, oy)], onet)
    pg.port(kx + 20, oy, onet, "OUT", "right")


def two_pin_ports(pg, part, x, y, kinds=("IN", "OUT")):
    """A two-pin part drawn horizontally with a port or ground on each end."""
    a = hpart(pg, part, x, y)
    for pid, side, kind in (("1", "left", kinds[0]), ("2", "right", kinds[1])):
        pg.tie(a[pid], part.nets[pid], side, kind)
    return a


def chip_power(pg, ref, dev, unit, x, y, nets):
    """The power unit of a multi-unit chip, every pin on a port or ground."""
    u = pg.place(ref, dev, x, y, unit=unit, des=(-30, -46, "LEFT_BOTTOM"), name=False)
    for pid, (px, py) in u.pins.items():
        net = nets.get(pid)
        if net is None:
            continue
        side = "left" if px < x else "right"
        if py > y + 30 and abs(px - x) < 25:        # bottom pins: straight down
            pg.ground((px, py), net, "down", 10) if net.startswith("GND") else None
            if not net.startswith("GND"):
                pg.wire([(px, py), (px, py + 10)], net)
                pg.stub_port((px, py + 10), net, "IN", "right" if px >= x else "left", length=10)
        elif py < y - 30:                           # top pin
            pg.wire([(px, py), (px, py - 10)], net)
            pg.stub_port((px, py - 10), net, "IN", "right", length=10)
        else:
            pg.tie((px, py), net, side)
    return u


def decoupling_grid(pg, P, chips, x0, y0, cols=6):
    """Each chip's two 100 n, a small column per chip: +12 V cap above ground, -12 V cap below."""
    dec = circuit.decoupling()
    for i, u in enumerate(chips):
        cp, cn = dec[u]
        x, top = x0 + (i % cols) * 70, y0 + (i // cols) * 150
        a = vpart(pg, P[cp], x, top)
        b = vpart(pg, P[cn], x, top + 60)
        node = (x, top + 50)
        g = P[cp].nets["2"]
        pg.wire([a["2"], node], g)
        pg.wire([node, b["1"]], g)
        pg.ground(node, g, "left", 10)
        pg.wire([a["1"], (x, top - 10)], P[cp].nets["1"])
        pg.stub_port((x, top - 10), P[cp].nets["1"], "IN", "right", length=10)
        pg.wire([b["2"], (x, top + 110)], P[cn].nets["2"])
        pg.stub_port((x, top + 110), P[cn].nets["2"], "IN", "right", length=10)
        pg.text(x - 15, top + 135, u, 8)


def headers_row(pg, P, refs, x0, y, pitch):
    for k, ref in enumerate(refs):
        x = x0 + k * pitch
        h = pg.place(ref, "HDR8", x, y, des=(-10, -50, "LEFT_BOTTOM"), name=False)
        for num, net in P[ref].nets.items():
            pg.tie(h[num], net, "left")


# ------------------------------------------------------------------ main board pages
def channel_block(pg, P, k, x0, t0):
    """One channel: input summer and the four poles on the top row, HP / BP / LP and the resonance path
    below."""
    r0 = 100 * k
    pg.text(x0, t0 + 20, f"Channel {k}: input summer (x0.51), four SSI2164 poles (15k / 15k / 220p, 48 kHz at "
                         f"0 V), HP = -1.95 (A + 2B + C), BP = -4.17 (C + 2D + E), LP = -2E", 11)
    y = t0 + 170
    summer(pg, P, circuit.UB[k], 1, x0 + 90, y, [P[f"R{r0 + 1}"]], P[f"R{r0 + 2}"], P[f"C{r0 + 1}"])
    pg.wire([(x0 + 90, y), (x0 + 90, y + 40)], f"S{k}")
    pg.stub_port((x0 + 90, y + 40), f"S{k}", "IN", "left", length=10)
    pg.text(x0 + 30, y + 60, "U5 cell current", 7)
    for n in range(1, 5):
        pole(pg, P, k, n, x0 + 290 + (n - 1) * 330, y)
    y2 = t0 + 400
    summer(pg, P, circuit.UB[k], 2, x0 + 90, y2, [P[f"R{r0 + 20}"], P[f"R{r0 + 21}"], P[f"R{r0 + 22}"]],
           P[f"R{r0 + 23}"])
    summer(pg, P, circuit.UB[k], 3, x0 + 410, y2, [P[f"R{r0 + 24}"], P[f"R{r0 + 25}"], P[f"R{r0 + 26}"]],
           P[f"R{r0 + 27}"])
    summer(pg, P, circuit.UB[k], 4, x0 + 730, y2, [P[f"R{r0 + 28}"]], P[f"R{r0 + 29}"])
    # resonance: BP -> 11k -> M (two diodes each way to ground) -> 13k -> Q (the U5 cell), its input network
    xr = x0 + 980
    pg.text(xr - 20, y2 - 60, f"Resonance feedback to U5 cell {k}, limiter", 9)
    a = hpart(pg, P[f"R{r0 + 30}"], xr, y2)
    pg.stub_port(a["1"], f"BP{k}", "IN", "left")
    mx = xr + 60
    pg.wire([a["2"], (mx, y2)], f"M{k}")
    b = hpart(pg, P[f"R{r0 + 31}"], mx + 20, y2)
    pg.wire([(mx, y2), b["1"]], f"M{k}")
    qx = mx + 80
    pg.wire([b["2"], (qx, y2)], f"Q{k}")
    pg.wire([(qx, y2), (qx + 20, y2)], f"Q{k}")
    pg.port(qx + 20, y2, f"Q{k}", "OUT", "right")
    rc = vpart(pg, P[f"R{r0 + 32}"], qx, y2 + 20)
    pg.wire([(qx, y2), rc["1"]], f"Q{k}")
    cc = vpart(pg, P[f"C{r0 + 10}"], qx, y2 + 70)
    pg.wire([rc["2"], cc["1"]], f"QK{k}")
    pg.ground(cc["2"], "GND", "down", 10)
    for i, (dp, dn, mid) in enumerate(((f"D{r0 + 1}", f"D{r0 + 2}", f"MA{k}"), (f"D{r0 + 4}", f"D{r0 + 3}", f"MB{k}"))):
        x = mx - 20 + 40 * i
        d1 = vpart(pg, P[dp], x, y2 + 30, top_pin="2" if i == 0 else "1")
        pg.wire([(mx, y2), (x, y2), (x, y2 + 30)] if x != mx else [(mx, y2), (x, y2 + 30)], f"M{k}")
        d2 = vpart(pg, P[dn], x, y2 + 80, top_pin="2" if i == 0 else "1")
        pg.wire([d1["1" if i == 0 else "2"], d2["2" if i == 0 else "1"]], mid)
        pg.ground(d2["1" if i == 0 else "2"], "GND", "down", 10)
    # SEL -> 47k -> the scanner VCA input
    two_pin_ports(pg, P[f"R{r0 + 34}"], xr + 230, y2 + 120)
    pg.text(xr + 190, y2 + 100, "to the scanner VCA", 8)
    chip_power(pg, f"U{k}", "SSI2164", 5, xr + 300, y2 - 10, P[f"U{k}"].nets)
    pg.text(xr + 250, y2 + 50, "MODE open: class AB", 7)


def main_page(pr, P, ks, number):
    pg = MPage(pr, f"Main {number}: channels {ks[0]} and {ks[1]}", number)
    for i, k in enumerate(ks):
        channel_block(pg, P, k, 40, Y(40 + i * 560))
    return pg


def scanner_block(pg, P, x0, t0):
    pg.text(x0, t0 + 20, "Scanner: S1 = 5.3 V + 0.34 knob + 0.42 CV; S2 / S3 shifted down 2.8 V each; three "
                         "degenerated BC857 pairs share the 0.5 mA tail between W1..W4 (always summing to it); "
                         "3.0k loads -> AS3360 linear control 0..1.5 V", 10)
    y = t0 + 120
    # S1: passive mix on the + input, gain 2
    part = P["U16"]
    amp = pg.place("U16", "TL074", x0 + 220, y + 10, unit=1, des=(14, 30, "LEFT_BOTTOM"), name=False)
    supply(pg, amp, part, 1)
    out, inm, inp = SECTION[1]
    px, py = amp[inp]
    pg.wire([(px, py), (px - 30, py)], "SP")
    for i, ref in enumerate(("R501", "R502", "R503")):
        r = P[ref]
        yy = py + 30 * i
        a = hpart(pg, r, px - 90, yy, left_pin=other(r, "SP"))
        pg.wire([a[pin_on(r, "SP")], (px - 30, yy)], "SP")
        if i:
            pg.wire([(px - 30, yy - 30), (px - 30, yy)], "SP")
        pg.tie(a[other(r, "SP")], r.nets[other(r, "SP")], "left")
    g = vpart(pg, P["R504"], px - 30, py + 90)
    pg.wire([(px - 30, py + 60), g["1"]], "SP")
    pg.ground(g["2"], "GND", "down", 10)
    mx, my = amp[inm]
    ox, oy = amp[out]
    rf = hpart(pg, P["R505"], mx, my - 40, left_pin="2")
    pg.wire([(mx, my), (mx - 10, my), (mx - 10, my - 40), rf["2"]], "SN")
    pg.wire([rf["1"], (ox + 20, my - 40), (ox + 20, oy)], "S1")
    pg.wire([(ox, oy), (ox + 20, oy)], "S1")
    rn = vpart(pg, P["R506"], mx - 10, my - 100, top_pin="2")      # SN at its lower end, ground on top
    pg.wire([(mx - 10, my - 40), rn["1"]], "SN")
    pg.ground(rn["2"], "GND", "up", 10)
    pg.wire([(ox + 20, oy), (ox + 40, oy)], "S1")
    pg.port(ox + 40, oy, "S1", "OUT", "right")
    # level shifts and the sink
    xs = x0 + 450
    for i, ref in enumerate(("R507", "R508")):
        two_pin_ports(pg, P[ref], xs, y + 40 * i, ("IN", "OUT"))
    q = pg.place("Q508", "NPN", xs + 40, y + 150, des=(14, -8, "LEFT_BOTTOM"), value_at=(14, 2, "LEFT_BOTTOM"))
    for pid in ("1", "2", "3"):
        pg.tie(q[pid], P["Q508"].nets[pid], "left" if pid == "1" else "right")
    for i, ref in enumerate(("R509", "R510", "R511")):
        two_pin_ports(pg, P[ref], xs, y + 230 + 30 * i)
    # ladder, tail source and bias
    xl = x0 + 760
    for i, ref in enumerate(("R512", "R513", "R514", "R515", "R516", "R517", "R518")):
        two_pin_ports(pg, P[ref], xl, y + 30 * i)
    q = pg.place("Q501", "PNP", xl + 40, y + 270, des=(14, -8, "LEFT_BOTTOM"), value_at=(14, 2, "LEFT_BOTTOM"))
    for pid in ("1", "2", "3"):
        pg.tie(q[pid], P["Q501"].nets[pid], "left" if pid == "1" else "right")
    # the stack: three pairs, each transistor with its emitter resistor above it
    xq = x0 + 1080
    for i, ref in enumerate(("Q502", "Q503", "Q504", "Q505", "Q506", "Q507")):
        x, yy = xq + (i % 2) * 280, y + 30 + (i // 2) * 120
        q = pg.place(ref, "PNP", x, yy, des=(14, -8, "LEFT_BOTTOM"), value_at=(14, 2, "LEFT_BOTTOM"))
        n = P[ref].nets
        pg.tie(q["1"], n["1"], "left")
        pg.tie(q["3"], n["3"], "right")
        re = P[f"R{519 + i}"]
        r = vpart(pg, re, q["2"][0], q["2"][1] - 40, top_pin=other(re, n["2"]))
        pg.wire([q["2"], r[pin_on(re, n["2"])]], n["2"])
        top = r[other(re, n["2"])]
        pg.wire([top, (top[0], top[1] - 10)], re.nets[other(re, n["2"])])
        pg.stub_port((top[0], top[1] - 10), re.nets[other(re, n["2"])], "IN", "right", length=10)
    pg.text(xq - 40, y + 325, "VCA control loads and their clamps", 9)
    for k in range(1, 5):
        two_pin_ports(pg, P[f"R{524 + k}"], xq, y + 350 + 30 * (k - 1))
        two_pin_ports(pg, P[f"D{500 + k}"], xq + 280, y + 350 + 30 * (k - 1))
    # the AS3360s: one VCA per channel, the four output currents into SO
    xv, yv = x0 + 100, t0 + 640
    pg.text(x0, yv - 70, "AS3360 VCAs: SEL k through 47k into II, W k on the linear control, IO into the I-V stage; "
                         "log converters bridged (VE-VO), VREF 4.7 nF", 9)
    for k, (u, half) in circuit.VCA.items():
        x = xv + (k - 1) * 230
        v = pg.place(u, "AS3360", x, yv, unit=half, des=(-14, -46, "LEFT_BOTTOM"), name=False)
        for pid, (px2, py2) in v.pins.items():
            net = P[u].nets[pid]
            if py2 < yv - 20:
                pg.wire([(px2, py2), (px2, py2 - 10)], net)
                pg.stub_port((px2, py2 - 10), net, "IN", "right", length=10)
            elif py2 > yv + 20:
                pg.wire([(px2, py2), (px2, py2 + 10)], net)
                pg.stub_port((px2, py2 + 10), net, "IN", "left" if px2 < x else "right", length=10)
            else:
                pg.tie((px2, py2), net, "left" if px2 < x else "right")
    for i, u in enumerate(("U17", "U18")):
        chip_power(pg, u, "AS3360", 3, xv + 1000 + i * 200, yv, P[u].nets)
    for i, ref in enumerate(("C502", "C503")):
        two_pin_ports(pg, P[ref], xv + 1400, yv - 20 + 40 * i)
    yo = t0 + 830
    pg.text(x0, yo - 130, "Scanner output: I-V stage, 51k || 22 pF, 1k to SCAN OUT; U16 C and D spare (followers on "
                          "ground)", 9)
    summer(pg, P, "U16", 2, x0 + 120, yo, [], P["R529"], P["C501"])
    pg.wire([(x0 + 120, yo), (x0 + 100, yo)], "SO")
    pg.port(x0 + 100, yo, "SO", "IN", "left")
    two_pin_ports(pg, P["R530"], x0 + 460, yo + 10)
    for s_ in (3, 4):            # spare sections: followers on ground
        part = P["U16"]
        out, inm, inp = SECTION[s_]
        amp = pg.place("U16", "TL074", x0 + 720 + (s_ - 3) * 200, yo, unit=s_, des=(14, 30, "LEFT_BOTTOM"),
                       name=False)
        net = part.nets[out]
        ox, oy = amp[out]
        mx, my = amp[inm]
        pg.wire([(ox, oy), (ox + 10, oy), (ox + 10, my - 20), (mx - 10, my - 20), (mx - 10, my), (mx, my)], net)
        pg.ground(amp[inp], "GND", "left", 10)


def power_block(pg, P, x0, t0):
    pg.text(x0, t0 + 20, "Power: 16-pin Eurorack header (pin 1 = -12 V, the red stripe; 3-8 GND, 9-10 +12 V), B5819W the right way round "
                         "(+12 V anode, -12 V cathode at the header), 10R + 10 uF per rail; 100R + 10 uF for the "
                         "knobs and the scan ladder", 10)
    hx, hy = x0 + 120, t0 + 140
    h = pg.place("J19", "HDR16", hx, hy, des=(-30, -45, "LEFT_BOTTOM"), name=False)
    nets = P["J19"].nets
    for side, sx in ((-1, hx - 30), (1, hx + 30)):
        pins = sorted(((pid, xy) for pid, xy in h.pins.items() if (xy[0] < hx) == (side < 0)), key=lambda t: t[1][1])
        gnd = [(pid, xy) for pid, xy in pins if nets.get(pid) == "GND"]
        bx = sx + 20 * side
        for pid, (px, py) in gnd:                      # the ground pins onto a bus, one flag at its end
            pg.wire([(px, py), (bx, py)], "GND")
        for (_, (_, ya)), (_, (_, yb)) in zip(gnd, gnd[1:]):
            pg.wire([(bx, ya), (bx, yb)], "GND")
        pg.ground((bx, gnd[1][1][1]), "GND", "left" if side < 0 else "right", 20)   # sideways, off the other pins' rows
        for pid, (px, py) in pins:
            net = nets.get(pid)
            if net and net != "GND":
                pg.wire([(px, py), (px + 50 * side, py)], net)
                pg.port(px + 50 * side, py, net, "IN", "left" if side < 0 else "right")
    pg.text(hx - 30, hy + 60, "11-16 (+5 V, CV, gate) open", 8)
    for i, ref in enumerate(("D901", "R901", "R903")):
        two_pin_ports(pg, P[ref], x0 + 400 + i * 260, t0 + 100)
    for i, ref in enumerate(("D902", "R902", "R904")):
        two_pin_ports(pg, P[ref], x0 + 400 + i * 260, t0 + 160)
    for i, ref in enumerate(("C901", "C902", "C903", "C904")):
        two_pin_ports(pg, P[ref], x0 + 400 + i * 260, t0 + 230)


def main_page_3(pr, P):
    pg = MPage(pr, "Main 3: resonance cells, scanner", 3)
    pg.text(40, Y(1130), "Net ports with the same name connect; the faceplate's nets end in _F and join these at "
                         "H1..H5.", 10)
    pg.text(40, 60 - H, "Resonance cells (U5): input Q k, control VR k, output into the input summer S k", 10)
    for k in range(1, 5):
        x, y = 100 + (k - 1) * 220, 140 - H
        c = pg.place("U5", "SSI2164", x, y, unit=k, des=(-14, -36, "LEFT_BOTTOM"), name=False)
        iin, vc, iout = CELL[k]
        pg.tie(c[iin], f"Q{k}", "left")
        pg.tie(c[iout], f"S{k}", "right", "OUT")
        vx, vy = c[vc]
        pg.wire([(vx, vy), (vx, vy - 10)], f"VR{k}")
        pg.stub_port((vx, vy - 10), f"VR{k}", "IN", "right", length=10)
    chip_power(pg, "U5", "SSI2164", 5, 1000, 140 - H, P["U5"].nets)
    scanner_block(pg, P, 40, 230 - H)
    return pg


def main_page_4(pr, P):
    pg = MPage(pr, "Main 4: power, decoupling, headers", 4)
    power_block(pg, P, 40, Y(40))
    pg.text(40, Y(420), "Decoupling: a 100 n per rail beside each chip (the PCB places each pair at its chip's "
                        "supply pins)", 10)
    chips = sorted([u for u in circuit.decoupling() if u in P], key=lambda s: int(s[1:]))
    decoupling_grid(pg, P, chips, 80, Y(470), cols=12)
    pg.text(40, Y(820), "Board-to-board sockets on the main board's front (pin 1 at the top); the faceplate has the "
                        "male pins HF1..HF5", 10)
    headers_row(pg, P, [r for r, _, _ in circuit.HEADERS], 160, Y(950), 250)
    return pg


# ------------------------------------------------------------------ faceplate
def jack_block(pg, part, jx, jy):
    j = pg.place(part.ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
    pg.text(jx - 25, jy + 30, part.label, 9)
    nets = part.nets
    s = j["1"]
    pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND_F")
    pg.flag(s[0] + 20, s[1] - 20, 90, "GND_F")
    tn = nets.get("2")
    if tn == "GND_F":
        pg.ground(j["2"], "GND_F", "right", 20)
    elif tn:
        pg.stub_port(j["2"], tn, "IN", "right", length=20)
    x, y = j["3"]
    pg.wire([(x, y), (x + 100, y)], nets["3"])
    pg.port(x + 100, y, nets["3"], "OUT" if tn else "IN", "right")


def pot_block(pg, part, x, y):
    p = pg.place(part.ref, dev_of(part), x, y, des=(-30, -30, "LEFT_BOTTOM"), value_at=(-30, -20, "LEFT_BOTTOM"))
    pg.text(x - 30, y + 40, part.label, 9)
    for pid, (px, py) in p.pins.items():
        pg.tie((px, py), part.nets[pid], "left" if px < x else "right")


def toggle_block(pg, part, x, y):
    dev = part.kind
    t = pg.place(part.ref, dev, x, y, des=(-40, -45 if dev.endswith("DPDT") else -30, "LEFT_BOTTOM"), name=False)
    pg.text(x - 40, y + (50 if dev.endswith("DPDT") else 35), part.label, 9)
    for pid, (px, py) in t.pins.items():
        pg.tie((px, py), part.nets[pid], "left" if px < x else "right")


def faceplate_page_1(pr, P):
    pg = MPage(pr, "Faceplate 1: jacks, knobs, toggles", 1)
    pg.page_count = "2"
    pg.text(40, Y(40), "Jacks (Thonkiconn): sleeves to GND_F; IN and FREQ normalled down the rows (row 1 from "
                       "ground), FM2/RES and SCAN grounded unpatched, outputs leave the lug open", 12)
    jacks = sorted((p for p in P.values() if p.kind == "JACK"), key=lambda p: int(p.ref[1:]))
    for i, part in enumerate(jacks):
        col, row = divmod(i, 5)
        jack_block(pg, part, 110 + col * 330, Y(140 + row * 100))
    pg.text(40, Y(660), "Knobs (Alpha 9 mm): FREQ between the filtered rails, RES and SCAN from +12 V to ground; "
                        "lugs to GND_F", 12)
    pots = sorted((p for p in P.values() if p.kind == "POT"), key=lambda p: int(p.ref[2:]))
    for i, part in enumerate(pots):            # two rows, wide enough for the ports
        pot_block(pg, part, 150 + (i % 5) * 330, Y(750 + (i // 5) * 100))
    pg.text(40, Y(930), "Toggles: mode (DPDT ON-ON-ON, up LP, middle HP, down BP: SEL on 2, 5 tied to 3), FM2/RES "
                        "(SPDT: up FM2 = 2-3, down RES = 2-1)", 12)
    toggles = sorted((p for p in P.values() if p.kind.startswith("TOGGLE")), key=lambda p: int(p.ref[2:]))
    for i, part in enumerate(toggles):         # the four mode toggles, then the four FM2/RES
        toggle_block(pg, part, 160 + (i % 4) * 380, Y(1000 + (i // 4) * 100))
    return pg


def faceplate_page_2(pr, P):
    pg = MPage(pr, "Faceplate 2: FREQ / RES summers, outputs, headers", 2)
    pg.page_count = "2"
    pg.text(40, Y(40), "FREQ and RES summers with precision clamps (never below 0 V on the SSI2164 control pins): "
                       "about -0.2 V/oct, 1 V/oct at the jacks", 12)
    for k in range(1, 5):
        r = 100 * k + 40
        d = 100 * k + 4
        u, s = circuit.CV_AMP[(k, "F")]
        x = 190 + (k - 1) * 380
        summer(pg, P, u, s, x, Y(200), [P[f"R{r + 1}"], P[f"R{r + 2}"], P[f"R{r + 3}"], P[f"R{r + 4}"]],
               P[f"R{r + 5}"], clamp=(P[f"D{d + 1}"], P[f"D{d + 2}"]))
        u, s = circuit.CV_AMP[(k, "R")]
        summer(pg, P, u, s, x, Y(470), [P[f"R{r + 6}"], P[f"R{r + 7}"], P[f"R{r + 8}"]], P[f"R{r + 9}"],
               clamp=(P[f"D{d + 3}"], P[f"D{d + 4}"]))
    pg.text(40, Y(640), "Output resistors (1k), decoupling at U14 / U15", 12)
    for k in range(1, 5):
        two_pin_ports(pg, P[f"R{100 * k + 33}"], 120 + (k - 1) * 260, Y(700))
    decoupling_grid(pg, P, ["U14", "U15"], 1000, Y(700))
    pg.text(40, Y(860), "Headers to the main board (male pins here, pin 1 at the top)", 12)
    headers_row(pg, P, [circuit.fb_ref(r) for r, _, _ in circuit.HEADERS], 160, Y(980), 250)
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
    placed = {c["ref"] for pg in pages for c in pg.comps if c["ref"]}
    problems = [f"{p.ref} not drawn" for p in parts if p.ref not in placed]
    for p in parts:
        for pid in p.nets:
            if seen[(p.ref, pid)] != 1:
                problems.append(f"{p.ref}.{pid} drawn {seen[(p.ref, pid)]} times")
    return problems


def pins_and_pads(pr, keys):
    """EasyEDA's DRC wants a symbol pin for every footprint pad (and the netlist needs the reverse)."""
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
    """Parse the written project: every schematic component's Device, Symbol and Footprint must be in it;
    on every PCB, each component's Device and Footprint exist, each PAD_NET names a real pad of that
    footprint and a net with a NET record (else EasyEDA drops the net silently)."""
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
    """ref -> device key, schematic Unique ID and the PCB's Channel ID ('$' + page number + id of the
    part's first schematic component)."""
    info = {}
    for pg in pages:
        for c in pg.comps:
            if c["ref"] and c["ref"] not in info:
                info[c["ref"]] = {"dev": c["dev"], "uid": pg.pr.unique_id(c["ref"]),
                                  "channel": f"${pg.number}{c['cid']}"}
    return info


def main():
    pr = MProject()
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    main_pages = [main_page(pr, PM, (1, 2), 1), main_page(pr, PM, (3, 4), 2), main_page_3(pr, PM),
                  main_page_4(pr, PM)]
    fp_pages = [faceplate_page_1(pr, PF), faceplate_page_2(pr, PF)]
    bad = coverage(main_pages, mb) + coverage(fp_pages, fb)
    for pg, parts in [(p, mb) for p in main_pages] + [(p, fb) for p in fp_pages]:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in main_pages + fp_pages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    board_fb = pcb.faceplate_board(pr, fb, part_info(fp_pages), circuit)
    board_mb = pcb.main_board(pr, mb, part_info(main_pages), circuit)
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb))
    for b in pcb_bad:
        print("PCB:", b)
    template = pcb.load_template(ee)
    panel_page = MPage(pr, "Panel", 1)
    panel_page.page_count = "1"
    panel_page.text(70, Y(60), "Atlasy 16HP panel as a PCB: no parts, no nets. Holes, mounting slots, silkscreen "
                               "and the bare-copper OUT column, scanner OUT patch and numerals are in the PCB "
                               "document; the art is hardware/panel/atlas-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("Atlasy Main", main_pages, board_mb), ("Atlasy Faceplate", fp_pages, board_fb),
              ("Atlasy Panel", [panel_page], board_panel)], OUT, template)
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in main_pages + fp_pages:
        render(pr, pg, PREVIEW.format(pg.title.split(":")[0].lower().replace(" ", "-")))
    board_mb.render(PREVIEW.format("pcb-main-board"))
    board_fb.render(PREVIEW.format("pcb-faceplate"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in main_pages + fp_pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(main_pages) + len(fp_pages)} pages, "
          f"{len(bad)} schematic problems; {len(board_mb.placed)} + {len(board_fb.placed)} parts placed, "
          f"{len(pcb_bad)} PCB problems; {len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
