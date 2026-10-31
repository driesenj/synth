"""Tempo as an EasyEDA Pro project (.epro2): the schematic of both boards,
both PCBs placed and net-assigned (pcb.py) and the panel as a third PCB
(panel_pcb.py), as for Side FXy and Senay.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the
file format, the connectivity check and the previews, the way Side FXy and
Senay do. Library parts come from the two caches of your MorrisSynth export
(resistor, capacitor, diode and TL074 symbols, the WQP518MA jack, net ports,
ground flag, sheet frame). Generated here:

  footprints  SMD (Senay's): 0603 / 0805 / 1206 chips, SOIC-14, SOIC-16,
              SOT-23 for the MMBT3904 (pads named B / E / C) and for the
              LM4040 (pads 1 / 2 / 3), SOD-123. Through-hole: the Daisy Seed
              on seed_power_opamps (Marblesy's), the EC11 encoder and the Thonk
              LED button (Side FXy's), 3 mm LED, 1xN headers and the 1x8
              wire pads for the display cable
  symbols     Seed, MCP4922, LM4040-2.5 (SOT-23), 74HC165, 74HC595, MMBT3904,
              EC11, LED button, LED, headers

Pages: main board 1 (Seed, inputs, reference, gates), main board 2 (DACs
and output stages), main board 3 (decoupling, headers); faceplate 1 (panel
parts), faceplate 2 (shift registers, resistors, display, headers). Every
pin ends in a net port (or a ground flag) with its net's name, so parts sit
in blocks without wires between them; same name = same net within a board,
and the header pins carry the nets across.

Run from clock/hardware/tools:  python easyeda_export.py
"""
import collections
import importlib.util
import os
import re
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
    spec = importlib.util.spec_from_file_location("tempo_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")

NAME = "Tempo"
OUT = os.path.join(HERE, "..", "easyeda", "Tempo.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "tempo-easyeda-{}.png")
MIL = 1 / 0.0254

DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0 (its symbol)
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00 (its symbol)
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819 (its symbol: 1 = cathode)
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here

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
    """A footprint in mm, written as an EasyEDA Pro FOOTPRINT doc (Senay's). Through-hole pads are round /
    square with round holes or oval with slots; SMD pads are rectangles on the top layer with no hole, as in
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


def fp_sot23_bec():
    """SOT-23 for the MMBT3904: pad names are the pins' functions (1 B, 2 E, 3 C)."""
    f = Footprint("SOT-23-MMBT3904-BEC", "Q?")
    f.smd("B", -0.95, -1.1, 0.8, 1.0)
    f.smd("E", 0.95, -1.1, 0.8, 1.0)
    f.smd("C", 0.0, 1.1, 0.8, 1.0)
    f.rect(-1.45, -0.65, 1.45, 0.65)
    return f


def fp_sot23():
    """SOT-23-3 numbered as the datasheets do: 1 and 2 on the long side, 3 alone on the other."""
    f = Footprint("SOT-23-3", "U?")
    f.smd(1, -0.95, -1.1, 0.8, 1.0)
    f.smd(2, 0.95, -1.1, 0.8, 1.0)
    f.smd(3, 0.0, 1.1, 0.8, 1.0)
    f.rect(-1.45, -0.65, 1.45, 0.65)
    return f


def fp_sod123():
    f = Footprint("SOD-123", "D?")
    f.smd(1, -1.635, 0, 0.91, 1.22)          # cathode (the band)
    f.smd(2, 1.635, 0, 0.91, 1.22)
    f.rect(-1.35, -0.8, 1.35, 0.8)
    f.line(-0.9, -0.8, -0.9, 0.8)
    return f


def fp_led3():
    f = Footprint("LED-3MM-P2.54", "D?")
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
    f.rect(x0 - 1.25, -1.25, x0 + (n - 1) * 2.54 + 1.25, 1.25)
    return f


def fp_wire_pads(n):
    """1xN wire pads, 2.54 mm: 1.0 mm holes take the display cable's 26-28 AWG wires once the Dupont ends are
    cut off. Drawn as a header so a 1xN pin strip fits too."""
    f = Footprint(f"WIRE-PADS-1x{n}-P2.54", "CN?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.25, -1.25, x0 + (n - 1) * 2.54 + 1.25, 1.25)
    return f


def fp_led_button():
    """Thonk low-profile LED button (Side FXy's): switch pins 1-4 on a 5.08 mm square (1+2 and 3+4 are the
    contacts), LED anode 5 and cathode 6 at x = +-2.7. No holes for the plastic feet: clip them off."""
    f = Footprint("SW-TACT-LP-LED-THONK", "SW?")
    for num, (x, y) in ((1, (2.54, 2.54)), (2, (-2.54, 2.54)), (3, (2.54, -2.54)), (4, (-2.54, -2.54)),
                        (5, (2.7, 0)), (6, (-2.7, 0))):
        f.pad(num, x, y, 1.0, 1.6, square=(num == 1))
    f.rect(-3.75, -3.75, 3.75, 3.75)
    f.circle(0, 0, 2.75)
    return f


def fp_seed_breakout():
    """Rob Heel's seed_power_opamps board, pads as measured in its PCB file (Marblesy's footprint).
    Origin at the centre of the Seed's pin field; pins 1 and 40 at +x (the USB end)."""
    f = Footprint("DAISY-SEED-POWER-OPAMPS-2.54", "U?")
    for k in range(20):
        f.pad(k + 1, 24.13 - k * 2.54, 7.62, 1.0, 1.7, square=(k == 0))
        f.pad(21 + k, -24.13 + k * 2.54, -7.62, 1.0, 1.7, square=(k == 19))
    for i in range(4):   # J1 (-12 V) and J3 (+12 V): pin 1 = GND nearest the Seed, one empty position in between
        f.pad(f"J1-{i + 1}", -29.21 - i * 2.54, 7.62, 1.0, 1.7, square=(i == 0))
        f.pad(f"J3-{i + 1}", -29.21 - i * 2.54, -7.62, 1.0, 1.7, square=(i == 0))
    for i in range(4):   # J5 (audio in) and J4 (audio out): pin 4 = GND nearest the Seed, no gap
        f.pad(f"J5-{i + 1}", 34.29 - i * 2.54, 7.62, 1.0, 1.7, square=(i == 0))
        f.pad(f"J4-{i + 1}", 34.29 - i * 2.54, -7.62, 1.0, 1.7, square=(i == 0))
    f.rect(-60.8, -9.4, 36.0, 9.4)      # breakout outline (96.7 x 18.8 mm)
    f.rect(-25.5, -9.0, 25.5, 9.0)      # Daisy Seed
    f.line(26.5, -9.0, 26.5, 9.0)       # USB end
    return f


def fp_ec11():
    """Alps EC11E with switch, vertical (KiCad RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm), moved so the
    origin is the shaft (Side FXy's): A / C / B 2.5 mm apart in a row 7.5 mm from the shaft, the switch pins
    5 mm apart 7.0 mm on the other side, the two mounting tabs on the shaft line 5.6 mm out (oval 2.8 x 1.5
    slots). Bourns PEC11R parts use the same pattern; check the one you order."""
    f = Footprint("ENC-EC11E-SW-VERTICAL", "ENC?")
    f.pad("A", -7.5, 2.5, 1.0, 2.0, square=True)
    f.pad("C", -7.5, 0.0, 1.0, 2.0)
    f.pad("B", -7.5, -2.5, 1.0, 2.0)
    f.pad("S2", 7.0, 2.5, 1.0, 2.0)
    f.pad("S1", 7.0, -2.5, 1.0, 2.0)
    f.pad("MP1", 0.0, 5.6, size=3.2, h=2.0, slot=(2.8, 1.5))
    f.pad("MP2", 0.0, -5.6, size=3.2, h=2.0, slot=(2.8, 1.5))
    f.rect(-6.0, -5.8, 6.0, 5.8)        # body, 12 x 11.6 mm
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


SEED_LEFT = [(0, "J5-1"), (1, "J5-2"), (2, "J5-3"), (3, "J5-4")] + [(4 + k, str(k + 1)) for k in range(20)] + \
            [(24 + i, f"J1-{i + 1}") for i in range(4)]
SEED_RIGHT = [(0, "J4-1"), (1, "J4-2"), (2, "J4-3"), (3, "J4-4")] + [(4 + k, str(40 - k)) for k in range(20)] + \
             [(24 + i, f"J3-{i + 1}") for i in range(4)]


def seed_symbol():
    s = ic_symbol("Daisy Seed on seed_power_opamps", "DaisySeedBreakout.4",
                  [(r, n, circuit.SEED[n][0]) for r, n in SEED_LEFT],
                  [(r, n, circuit.SEED[n][0]) for r, n in SEED_RIGHT], w=80)
    s.text(-30, 120, "Daisy Seed", 10)
    s.text(-45, 133, "seed_power_opamps", 8)
    return s


def mcp4922_symbol():
    """MCP4922 (SOIC-14 and DIP-14 share the pinout); NC pins 2, 6, 7 so every pad has a pin."""
    left = [(0, "1", "VDD"), (1, "9", "/SHDN"), (3, "3", "/CS"), (4, "4", "SCK"), (5, "5", "SDI"),
            (6, "8", "/LDAC"), (8, "12", "VSS")]
    right = [(0, "14", "VOUTA"), (1, "13", "VREFA"), (3, "10", "VOUTB"), (4, "11", "VREFB"), (6, "2", "NC"),
             (7, "6", "NC"), (8, "7", "NC")]
    return ic_symbol("MCP4922", "MCP4922.2", left, right)


def lm4040_symbol():
    """Offset's LM4040 drawing for the SOT-23 part: 1 = cathode (the positive end), 2 = anode, 3 = the
    substrate, which TI asks to tie to the anode or leave open."""
    s = Symbol("LM4040-2.5 SOT-23", "LM4040_2V5_SOT23.1", "D?", [NAME])
    s.poly([(-20, 0), (-6, 0)])
    s.poly([(6, -7), (-6, 0), (6, 7), (6, -7)], closed=True)
    s.poly([(-6, -7), (-6, 7)])
    s.poly([(-6, -7), (-9, -9)])
    s.poly([(-6, 7), (-3, 9)])
    s.poly([(6, 0), (20, 0)])
    s.text(-14, -8, "2.5V", 6)
    s.pin("1", "K", -20, 0, 0)
    s.pin("2", "A", 20, 0, 180)
    s.pin("3", "SUB", 0, 17, 90)
    return s


def hc595_symbol():
    left = [(0, "14", "SER"), (1, "11", "SRCLK"), (2, "12", "RCLK"), (3, "13", "/OE"), (4, "10", "/SRCLR"),
            (6, "16", "VCC"), (7, "8", "GND")]
    right = [(0, "15", "QA"), (1, "1", "QB"), (2, "2", "QC"), (3, "3", "QD"), (4, "4", "QE"), (5, "5", "QF"),
             (6, "6", "QG"), (7, "7", "QH"), (8, "9", "QH'")]
    return ic_symbol("74HC595", "74HC595.2", left, right)


def hc165_symbol():
    left = [(0, "1", "/PL"), (1, "2", "CP"), (2, "10", "DS"), (3, "15", "CE"), (7, "16", "VCC"), (8, "8", "GND")]
    right = [(0, "11", "D0"), (1, "12", "D1"), (2, "13", "D2"), (3, "14", "D3"), (4, "3", "D4"), (5, "4", "D5"),
             (6, "5", "D6"), (7, "6", "D7"), (8, "9", "Q7"), (9, "7", "/Q7")]
    return ic_symbol("74HC165", "74HC165.2", left, right)


def led_button_symbol():
    """Tactile switch with a built-in LED: contacts 1+2 and 3+4, LED on 5 and 6."""
    left = [(0, "1", "1"), (1, "2", "2"), (3, "5", "LED A")]
    right = [(0, "3", "3"), (1, "4", "4"), (3, "6", "LED K")]
    return ic_symbol("LED button", "SWLED.4", left, right, designator="SW?")


def encoder_symbol():
    """EC11 with switch: phases A / B and common C on the left, the switch (S1 / S2) and the two mounting
    tabs on the right."""
    left = [(0, "A", "A"), (1, "B", "B"), (4, "C", "C")]
    right = [(0, "S2", "SW"), (2, "S1", "SW"), (3, "MP1", "MT"), (4, "MP2", "MT")]
    return ic_symbol("EC11 encoder with switch", "EC11SW.2", left, right, designator="ENC?", w=30)


def npn_symbol():
    s = Symbol("MMBT3904", "NPN.3", "Q?", [NAME])
    s.poly([(-20, 0), (-5, 0)])
    s.poly([(-5, -12), (-5, 12)])
    s.poly([(-5, -4), (10, -14), (10, -20)])
    s.poly([(-5, 4), (10, 14), (10, 20)])
    s.poly([(10, 14), (3, 13), (6, 8), (10, 14)], closed=True, fill="#000000")
    s.pin("B", "B", -20, 0, 0)
    s.pin("C", "C", 10, -20, 90)
    s.pin("E", "E", 10, 20, 270)
    return s


def led_symbol():
    s = Symbol("LED 3mm", "LED3.2", "D?", [NAME])
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
        """Ground-style flag carrying a named net (GND_F, GND_D_F)."""
        self._flag("GND", x, y, rot, net, True)


GROUNDS = ("GND", "GND_F", "GND_D_F")


def dev_of(part):
    k, v = part.kind, part.value
    return {"R": f"R_{v}", "C": f"C_{v}", "TL074": "TL074S", "SCHOTTKY": "D_1N5819HW",
            "SWLED": f"SWLED_{v}"}.get(k, k)


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
                    "SOT23BEC": self._footprint(fp_sot23_bec()), "SOT23": self._footprint(fp_sot23()),
                    "SOD123": self._footprint(fp_sod123()), "LED3": self._footprint(fp_led3()),
                    "SEED": self._footprint(fp_seed_breakout()), "ENC": self._footprint(fp_ec11()),
                    "SWLED": self._footprint(fp_led_button()), "WIRE8": self._footprint(fp_wire_pads(8))})
        res_sym, cap_sym = self.device_attrs("R1k")["Symbol"], self.device_attrs("C100n")["Symbol"]
        diode = self.device_attrs("D5819")["Symbol"]
        swled = self._symbol(led_button_symbol())
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
            elif p.kind == "SCHOTTKY":
                self._new(key, diode, fps["SOD123"], p.value, "D?", "Schottky 1N5819HW, 40 V 1 A, SOD-123")
            elif p.kind == "SWLED":
                self._new(key, swled, fps["SWLED"], f"LED button {p.value}, Thonk low profile", "SW?",
                          f"Thonk low-profile LED button, {p.value}: 7.5 mm body, 5.5 mm round cap, 1+2 / 3+4 "
                          "contacts, LED anode 5, cathode 6. Clip the three plastic feet off: the board has no "
                          "holes for them")
        for key, sym, fp, title, desig, desc in (
                ("SEED", seed_symbol(), fps["SEED"], "Daisy Seed + seed_power_opamps", "U?",
                 "Daisy Seed plugged into Rob Heel's seed_power_opamps breakout (its audio op-amps unused); "
                 "2.54 mm socket strips on the main board"),
                ("MCP4922", mcp4922_symbol(), fps["SOIC14"], "MCP4922-E/SL", "U?",
                 "Dual 12-bit SPI DAC with external reference, SOIC-14"),
                ("LM4040", lm4040_symbol(), fps["SOT23"], "LM4040D25IDBZR", "D?",
                 "Precision shunt reference 2.500 V 1 %, SOT-23: 1 cathode, 2 anode, 3 substrate (to the anode)"),
                ("HC595", hc595_symbol(), fps["SOIC16"], "74HC595D", "U?",
                 "8-bit shift register with output latch, SOIC-16"),
                ("HC165", hc165_symbol(), fps["SOIC16"], "74HC165D", "U?", "8-bit parallel-in shift register, SOIC-16"),
                ("NPN", npn_symbol(), fps["SOT23BEC"], "MMBT3904", "Q?", "NPN MMBT3904, SOT-23: 1 B, 2 E, 3 C"),
                ("ENC", encoder_symbol(), fps["ENC"], "EC11 encoder with switch", "ENC?",
                 "Rotary encoder with push switch, EC11 pattern, vertical, M7 bushing, D shaft (Alps EC11E or "
                 "Bourns PEC11R). A / B phases, C common, S1 / S2 switch, MP1 / MP2 mounting tabs"),
                ("LED", led_symbol(), fps["LED3"], "LED 3mm red", "D?", "3 mm LED, red; 1 anode, 2 cathode (flat)"),
                ("WIRE8", header_symbol(8), fps["WIRE8"], "Wire pads 1x8", "CN?",
                 "Eight wire pads, 2.54 mm, for the display module's cable (MX1.25 to Dupont): cut the Dupont "
                 "ends off and solder the wires in; the module end stays a plug")):
            self._new(key, self._symbol(sym), fp, title, desig, desc)
        a = dict(self.device_attrs("TL074"))
        a.update({"Footprint": fps["SOIC14"], "Manufacturer Part": "TL074CDT", "Supplier Part": "",
                  "Description": "Quad JFET op-amp, SOIC-14"})
        self._device("TL074S", "TL074 SOIC-14", a)
        for ref, kind, pins in circuit.HEADERS:
            n = len(pins)
            self._new(kind, self._symbol(header_symbol(n)), self._footprint(fp_header(n)), f"Pin header 1x{n}", "H?",
                      f"Board-to-board header 1x{n}, 2.54 mm: male on the faceplate, female on the main board")

    def write(self, boards, path, template=None):
        """boards: [(title, pages, pcb board or None)]; each gets a BOARD doc holding its schematic pages
        and, once placed, its PCB."""
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
            if pcb_board is not None:
                lines += pcb_board.doc(ee, template, board.uuid, f"{title} PCB")
        lines += Doc("CONFIG", "CONFIG").lines({"defaultSheet": ""})
        lines += next(d for d in self.lib.values() if d["docType"] == "BLOB")["lines"]   # one BLOB doc
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Tempo: a Pam's-style clock and LFO on a Daisy Seed. Eight outputs (4x MCP4922, "
                                  "Marblesy's output stage), CLOCK / RESET in, RUN / RESET out, CV 1-3, ST7789 "
                                  "display, 3 EC11 encoders, LED buttons on 74HC165/595. Two stacked PCBs, SMD main "
                                  "board, 12HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


# ------------------------------------------------------------------ schematic layout
class Flow:
    """Places part units left to right in rows on a page (Senay's); every connected pin gets a short stub
    ending in a net port (or a ground flag), so the drawing carries the netlist without wires between parts."""

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


def opamp_note(part, s):
    """What a TL074 section does, named by its output net."""
    out = part.nets[circuit.SECTION[s][0]]
    word = {"NREF": "NREF inverter"}.get(out, out.replace("OA_", "").replace("U9_SPARE", "spare "))
    return word + (" + supply" if s == 1 else "")


def units(fl, P, refs, sections=(1, 2, 3, 4)):
    """Draw the parts in order; a TL074 named as (ref, section) draws that unit only."""
    for r in refs:
        if isinstance(r, tuple):
            ref, s = r
            fl.unit(P[ref], s, note=opamp_note(P[ref], s))
        elif P[r].kind == "TL074":
            for s in sections:
                fl.unit(P[r], s, note=opamp_note(P[r], s))
        else:
            fl.unit(P[r])


def rr(a, b):
    return [f"R{n}" for n in range(a, b + 1)]


def main_pages(pr, P):
    blocks = [
        ("Main 1: Seed, CLOCK / RESET, CV inputs, reference", [
            ("Daisy Seed on the seed_power_opamps breakout (sockets on this board; its audio parts unused)", ["U1"]),
            ("CLOCK and RESET in: 100k into an MMBT3904 inverter, 1N5819HW clamp, 10k pull-up (CLK / RST active low)",
             ["R76", "Q1", "D9", "R77", "R78", "Q2", "D10", "R79"]),
            ("CV inputs (U8 A-C): 100k / 27k round BIAS 1.32 V, +-5 V -> 0.33..3.03 V, 1k into the ADC; BIAS divider",
             [("U8", 1), ("U8", 2), ("U8", 3)] + rr(62, 70) + ["C10", "C11", "C12", "R74", "R75", "C13"]),
            ("Reference: LM4040-2.5 (pin 3 to the anode) fed by 1k5; U8D inverts it, NREF = -2.50 V",
             ["D11", "R73", "C14", ("U8", 4), "R71", "R72"])]),
        ("Main 2: DACs and output stages", [
            ("DACs: MCP4922 on SPI3 (D2 SCK, D6 MOSI), own /CS each, shared /LDAC; VREF on both references",
             ["U2", "U3", "U4", "U5"])] + [
            (f"Outputs {a}-{a + 3} (U{6 + a // 5}): Vout = 5.32 V - 4.17 Vdac. Rdac 24k, Rref 47k from NREF, "
             f"Rf 100k, 1k out", [r for k in range(a, a + 4)
                                  for r in [("U6" if k < 5 else "U7", (k - 1) % 4 + 1)] + rr(26 + 4 * k, 29 + 4 * k)])
            for a in (1, 5)]),
        ("Main 3: RUN / RESET out, decoupling, headers", [
            ("RUN and RESET out (U9 A, B): x2.5 from D18 / D19 (0 / 8.25 V), 1k out; U9 C, D grounded followers",
             [("U9", 1), ("U9", 2), ("U9", 3), ("U9", 4)] + rr(80, 85)),
            ("Decoupling: 100 n per rail beside each TL074 (C15-C22), 100 n at each DAC (C23-C26), 10 u bulk by J1 / J3",
             [f"C{n}" for n in range(15, 29)]),
            ("Board-to-board sockets (female on this board, pin 1 at the top); the faceplate has the male pins",
             ["H1", "H2", "H3", "H4"])]),
    ]
    return paged(pr, blocks)


def faceplate_pages(pr, P):
    blocks = [
        ("Faceplate 1: jacks, encoders, buttons, LEDs", [
            ("Inputs (Thonkiconn): sleeve and switch lug to GND_F, so an open input reads 0 V",
             ["J1", "J2", "J3", "J4", "J5"]),
            ("Outputs: RUN, RESET, 1-8; switch lugs open", [f"J{n}" for n in range(6, 16)]),
            ("Encoders (EC11 with push): C, switch and tabs to GND_D_F; phases pulled up (page 2) to Seed pins",
             ["ENC1", "ENC2", "ENC3"]),
            ("LED buttons (Thonk low profile): RUN green, TAP white, SHIFT red", ["SW1", "SW2", "SW3"]),
            ("Output LEDs, 3 mm red, from U11 through 470R", [f"D{n}" for n in range(1, 9)])]),
        ("Faceplate 2: shift registers, display, headers", [
            ("Switches into U10 (74HC165, Q7 = SR_DIN; D6 / D7 tied high); 10k pull-ups R7-R12, encoder phases "
             "R1-R6", ["U10"] + rr(1, 12)),
            ("LEDs: U11 (outputs 1-8, R13-R20 470R) shifts on into U12 (RUN, TAP, SHIFT: R21 / R22 150R, R23 470R)",
             ["U11"] + rr(13, 20) + ["U12"] + rr(21, 23)),
            ("Display cable (Waveshare order) soldered to wire pads; decoupling at U10-U12, 10 u beside CN1",
             ["CN1", "C1", "C2", "C3", "C4"]),
            ("Headers to the main board (male pins here, pin 1 at the top)", ["HF1", "HF2", "HF3", "HF4"])]),
    ]
    return paged(pr, blocks)


def paged(pr, blocks):
    pages = []
    for i, (title, groups) in enumerate(blocks):
        pg = MPage(pr, title, i + 1)
        pg.page_count = str(len(blocks))
        fl = Flow(pg)
        P = pr.parts
        for heading, refs in groups:
            fl.heading(heading)
            units(fl, P, refs)
        pages.append(pg)
    return pages


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


def netlist_pins(pr, parts):
    """Every netlist pin must exist on its device's symbol (a pin the symbol lacks would never be drawn)."""
    problems = []
    for p in parts:
        sym = pr.device_attrs(dev_of(p))["Symbol"]
        pins = {q["num"] for q in pr.symgeo[sym]["pins"]}
        problems += [f"{p.ref}.{pid} is not a pin of {dev_of(p)}" for pid in p.nets if pid not in pins]
    return problems


def validate(path):
    """Parse the written project: every schematic component's Device, Symbol and Footprint must be in it;
    on the PCBs every PAD_NET must name a pad of its component's footprint and a net with a NET record."""
    with ee.zipfile.ZipFile(path) as z:
        docs = ee.parse(z.read(f"{NAME}.epru").decode("utf-8").split("\n"))
    problems = []
    pad_ids = {u: {h["id"] for h, p in d["recs"] if h["type"] == "PAD"}
               for u, d in docs.items() if d["docType"] == "FOOTPRINT"}
    for u, d in docs.items():
        if d["docType"] == "SCH_PAGE":
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p["key"] in ("Device", "Symbol", "Footprint") and p["value"]                         and p["value"] not in docs:
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


def slug(title):
    return "-".join(re.findall(r"[a-z0-9]+", title.split(":")[0].lower()))


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
    bad = netlist_pins(pr, mb + fb)
    pr.parts = {p.ref: p for p in mb}
    mpages = main_pages(pr, pr.parts)
    pr.parts = {p.ref: p for p in fb}
    fpages = faceplate_pages(pr, pr.parts)
    bad += coverage(mpages, mb) + coverage(fpages, fb)
    for pg, parts in [(p, mb) for p in mpages] + [(p, fb) for p in fpages]:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in mpages + fpages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    board_fb = pcb.faceplate_board(pr, fb, part_info(fpages), circuit)
    board_mb = pcb.main_board(pr, mb, part_info(mpages), circuit)
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb))
    for b in pcb_bad:
        print("PCB:", b)
    template = pcb.load_template(ee)
    panel_page = MPage(pr, "Panel", 1)
    panel_page.text(70, Y(60), "Tempo 12HP panel as a PCB: no parts, no nets. Holes, slots, the display window, "
                               "silkscreen and the bare-copper output band are in the PCB document; the art is "
                               "hardware/panel/tempo-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("Tempo Main", mpages, board_mb), ("Tempo Faceplate", fpages, board_fb),
              ("Tempo Panel", [panel_page], board_panel)], OUT, template)
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in mpages + fpages:
        render(pr, pg, PREVIEW.format(slug(pg.title)))
    board_mb.render(PREVIEW.format("pcb-main-board"))
    board_fb.render(PREVIEW.format("pcb-faceplate"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in mpages + fpages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(mpages) + len(fpages)} pages, "
          f"{len(bad)} schematic problems; {len(board_mb.placed)} + {len(board_fb.placed)} parts placed, "
          f"{len(pcb_bad)} PCB problems; {len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
