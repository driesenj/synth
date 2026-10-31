"""Side FXy as an EasyEDA Pro project (.epro2): schematic pages, both PCBs
placed (not routed), and the panel PCB.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the
file format, the connectivity check and the previews, the way the mixer
does. Library parts come from two caches of your MorrisSynth export:
plaitsy/hardware/easyeda/morrissynth-parts.epru (TL074ACN symbol, WQP518MA
jack, LR1F resistors, FG28 / SR305 capacitors, 1N4148, 1N5819, the 74HC595N's
DIP-16, net ports, ground flag, sheet frame) and
stereo-mixer/hardware/easyeda/stereo-mixer-parts.epru (the 178MU0033 10 uF).
Drawn or generated here, in the same style and with real pin numbers:

  footprints  Daisy Seed on seed_power_opamps (Marblesy's), DIP-14 and DIP-6
              on the 7.62 mm row pitch, TO-92, the Thonk LED button, standing
              resistors, 1xN headers, SIP-9, the EC11 encoder with switch
              (KiCad's RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm, origin on
              the shaft), the stereo Thonkiconn PJ366ST (the library jack's frame,
              slots from KiCad merge request 1073)
  symbols     Seed, 74HC165, 74HC595, H11L1, 2N3904, LED button, EC11, bussed
              resistor network, stereo jack, headers

Pages: main board (one page), faceplate (jacks, encoders, buttons; shift
registers, display, headers), panel note. Net ports with the same name
connect within a board; nets that cross between the boards are the header
pins. pcb.py places both PCBs (unrouted) and panel_pcb.py draws the panel as
the third board.

Run from side-fx/hardware/tools:  python easyeda_export.py
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
    spec = importlib.util.spec_from_file_location("sidefx_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")
SECTION = circuit.SECTION

NAME = "SideFXy"
OUT = os.path.join(HERE, "..", "easyeda", "SideFXy.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "side-fx-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil

# Library devices used as they are (uuids from the two caches)
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0
    "R10k": "a9cc8fbe474242dc9110194515734c75",      # LR1F10K
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00
    "C1u": "bf1fe821a3774bf48d0873f872221180",       # SR305C105KAR
    "C10u": "21e4ec8defc34a489f66b07134d13cd6",      # 178MU0033, 10 uF 35 V
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol; footprint replaced below)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "D1N4148": "c0160a3f74384e849dc1cc5a24d54846",   # 1N4148: DO-35 footprint and attributes
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819: the diode symbol (1 = cathode)
    "HC595N": "0a92c57a01f94d9c9ee2e575c9a56376",    # 74HC595N: its DIP-16 footprint
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "27k": ("LR1F27K", "27kΩ"), "15k": ("LR1F15K", "15kΩ"),
         "220": ("LR1F220R", "220Ω"), "470": ("LR1F470R", "470Ω")}
C_NEW = {"1n": ("FG28C0G1H102JNT00", "1nF")}

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
    (slot=(w, h)) like the jacks' and the encoder's tabs."""

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


def fp_header_ra(n):
    """1xN right-angle male header lying on the board, pins in a row like fp_header; the drawn body
    covers the plastic and the Dupont plug pushed onto the pins (about 16.5 mm out from the row, -y)."""
    f = Footprint(f"HDR-1x{n}-P2.54-RA", "CN?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.27, -17.8, x0 + (n - 1) * 2.54 + 1.27, 1.27)
    f.line(x0 - 1.27, -3.8, x0 + (n - 1) * 2.54 + 1.27, -3.8)    # where the plastic ends and the plug begins
    return f


def fp_sip(n):
    """Single-in-line resistor network, 2.54 mm, pin 1 (common) square; body 2.5 mm thick."""
    f = Footprint(f"SIP-{n}-P2.54", "RN?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.rect(x0 - 1.4, -1.25, x0 + (n - 1) * 2.54 + 1.4, 1.25)
    f.line(x0 + 1.27, -1.25, x0 + 1.27, 1.25)      # pin 1 end marked
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
    hx, hy = half * 1.27 + 0.7, 3.25       # body: 19.2 x 6.5 mm for DIP-14, 9.0 x 6.5 for DIP-6
    f.rect(-hx, -hy, hx, hy)
    f.circle(-hx + 0.9, -hy + 0.9, 0.3)
    return f


def fp_to92():
    f = Footprint("TO-92-INLINE-P2.54", "Q?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.line(-2.6, -1.3, 2.6, -1.3)
    f.circle(0, 0, 2.6)
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
    origin is the shaft: A / C / B 2.5 mm apart in a row 7.5 mm from the shaft, the switch pins 5 mm apart
    7.0 mm on the other side, the two mounting tabs on the shaft line 5.6 mm out (oval 2.8 x 1.5 slots).
    Bourns PEC11R parts use the same pattern; check the one you order."""
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


def fp_pj366st():
    """Stereo Thonkiconn (QingPu WQP-PJ366ST) in the library WQP518MA's frame: sleeve, ring and tip where the
    mono jack has sleeve, switch lug and tip (0, -5.7 / -2.6 / +5.7), so the barrel is again 0.78 mm from
    the origin. Slots and pads from KiCad merge request 1073 (not merged; check against the part)."""
    f = Footprint("JACK-PJ366ST-STEREO", "J?")
    f.pad(1, 0, -5.7, size=2.41, h=1.19, slot=(1.9, 0.68))
    f.pad(2, 0, -2.6, size=2.61, h=1.19, slot=(2.1, 0.68))
    f.pad(3, 0, 5.7, size=2.49, h=1.06, slot=(2.0, 0.57))
    f.rect(-5.0, -3.67, 5.0, 6.78)
    f.circle(0, 0.78, 1.8)
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
    s = ic_symbol("Daisy Seed on seed_power_opamps", "DaisySeedBreakout.3",
                  [(r, n, circuit.SEED[n][0]) for r, n in SEED_LEFT],
                  [(r, n, circuit.SEED[n][0]) for r, n in SEED_RIGHT], w=80)
    s.text(-30, 120, "Daisy Seed", 10)
    s.text(-45, 133, "seed_power_opamps", 8)
    return s


def hc595_symbol():
    left = [(0, "14", "SER"), (1, "11", "SRCLK"), (2, "12", "RCLK"), (3, "13", "/OE"), (4, "10", "/SRCLR"),
            (6, "16", "VCC"), (7, "8", "GND")]
    right = [(0, "15", "QA"), (1, "1", "QB"), (2, "2", "QC"), (3, "3", "QD"), (4, "4", "QE"), (5, "5", "QF"),
             (6, "6", "QG"), (7, "7", "QH"), (8, "9", "QH'")]
    return ic_symbol("74HC595", "74HC595.1", left, right)


def hc165_symbol():
    left = [(0, "1", "/PL"), (1, "2", "CP"), (2, "10", "DS"), (3, "15", "CE"), (7, "16", "VCC"), (8, "8", "GND")]
    right = [(0, "11", "D0"), (1, "12", "D1"), (2, "13", "D2"), (3, "14", "D3"), (4, "3", "D4"), (5, "4", "D5"),
             (6, "5", "D6"), (7, "6", "D7"), (8, "9", "Q7"), (9, "7", "/Q7")]
    return ic_symbol("74HC165", "74HC165.1", left, right)


def h11l1_symbol():
    left = [(0, "1", "A"), (1, "2", "K"), (2, "3", "NC")]
    right = [(0, "6", "VCC"), (1, "4", "VO"), (2, "5", "GND")]
    return ic_symbol("H11L1", "H11L1.1", left, right, w=40)


def led_button_symbol():
    """Tactile switch with a built-in LED: contacts 1+2 and 3+4, LED on 5 and 6."""
    left = [(0, "1", "1"), (1, "2", "2"), (3, "5", "LED A")]
    right = [(0, "3", "3"), (1, "4", "4"), (3, "6", "LED K")]
    return ic_symbol("LED button", "SWLED.3", left, right, designator="SW?")


def encoder_symbol():
    """EC11 with switch: phases A / B and common C on the left, the switch (S1 / S2) and the two mounting
    tabs on the right."""
    left = [(0, "A", "A"), (1, "B", "B"), (4, "C", "C")]
    right = [(0, "S2", "SW"), (2, "S1", "SW"), (3, "MP1", "MT"), (4, "MP2", "MT")]
    return ic_symbol("EC11 encoder with switch", "EC11SW.1", left, right, designator="ENC?", w=30)


def network_symbol():
    left = [(0, "1", "COM")]
    right = [(i, str(i + 2), f"R{i + 1}") for i in range(8)]
    return ic_symbol("Resistor network 8x bussed", "RN8BUS.1", left, right, designator="RN?", w=30)


def trs_symbol():
    """Stereo jack, pins where the library jack has them: 1 sleeve, 2 ring, 3 tip."""
    s = Symbol("Jack 3.5mm stereo", "JACKTRS.1", "J?", [NAME])
    s.rect(-15, -22, 15, 17)
    s.text(-12, 2, "TRS", 8)
    for num, name, y in (("1", "S", -15), ("2", "R", -5), ("3", "T", 10)):
        s.pin(num, name, 25, y, 180, show=True, edge=15)
    return s


def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.3", "H?", [NAME])
    half = n * 5
    s.rect(-10, -half - 5, 10, half + 5)
    for i in range(n):
        s.pin(str(i + 1), str(i + 1), -20, -half + 5 + 10 * i, 0, show=True, edge=-10)
    return s


def npn_symbol():
    s = Symbol("2N3904", "NPN.1", "Q?", [NAME])
    s.poly([(-20, 0), (-5, 0)])
    s.poly([(-5, -12), (-5, 12)])
    s.poly([(-5, -4), (10, -14), (10, -20)])
    s.poly([(-5, 4), (10, 14), (10, 20)])
    s.poly([(10, 14), (3, 13), (6, 8), (10, 14)], closed=True, fill="#000000")
    s.text(-18, -4, "B", 6)
    s.pin("2", "B", -20, 0, 0)
    s.pin("3", "C", 10, -20, 90)
    s.pin("1", "E", 10, 20, 270)
    return s


# ------------------------------------------------------------------ project
STANDING = ["R1k", "R10k"] + ["R" + v for v in R_NEW]    # main-board resistors stand up (dev key + "V")


class MPage(Page):
    page_count = "1"

    def place(self, ref, dev_key, *args, **kw):
        if self.title.startswith("Main") and dev_key in STANDING:
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
        vals = [("Symbol", sym), ("@Project Name", "Side FXy"), ("@Page Count", self.page_count),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", "Side FXy"),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V0.1"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", "Side FXy"),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))

    def flag(self, x, y, rot, net):
        """Ground-style flag carrying a named net (GND_F, GND_D_F)."""
        self._flag("GND", x, y, rot, net, True)

    def stub_flag(self, pin, net, direction="down", length=10):
        x, y = pin
        end = {"down": (x, y + length), "right": (x + length, y), "left": (x - length, y), "up": (x, y - length)}
        x2, y2 = end[direction]
        self.wire([(x, y), (x2, y2)], net)
        self.flag(x2, y2, {"down": 0, "right": 90, "left": 270, "up": 180}[direction], net)

    def ground(self, pin, net, direction="down", length=10):
        """GND on the main board, a named ground flag on the faceplate."""
        if net == "GND":
            self.stub_gnd(pin, direction, length)
        else:
            self.stub_flag(pin, net, direction, length)


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

    def _symbol(self, sym):
        lines = sym.build()
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(sym.doc.uuid, lines)
        return sym.doc.uuid

    def _new_devices(self):
        r1k = self.device_attrs("R1k")
        for val, (mpn, value) in R_NEW.items():
            a = dict(r1k)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "LCSC Part Name": f"Metal film resistor {value} ±1% 600mW",
                      "Description": f"Metal film resistor {value} ±1% 600mW (TE LR1F series)"})
            self._device("R" + val, mpn, a, ["Resistors", "Through Hole Resistors"])
        c100n = self.device_attrs("C100n")
        for val, (mpn, value) in C_NEW.items():
            a = dict(c100n)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "Tolerance": "±5%", "Temperature Coefficient": "C0G",
                      "LCSC Part Name": f"{value} ±5% 50V C0G",
                      "Description": f"Capacitance:{value} Tolerance:±5% Voltage Rating:50V Temperature Coefficient:C0G"})
            self._device("C" + val, mpn, a, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"])
        self._copy("C10uK", "C100n", "10uF MLCC", ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"],
                   **{"Manufacturer Part": "10uF MLCC 5.08mm", "Value": "10uF", "Supplier Part": "", "Datasheet": "",
                      "Tolerance": "±10%", "Temperature Coefficient": "X5R / X7R",
                      "LCSC Part Name": "10uF 16V+ X5R/X7R, leaded, 5.08 mm",
                      "Description": "10 uF ceramic, 16 V or more, leads on 5.08 mm: low enough for the 8.5 mm "
                                     "gap between the boards, where an electrolytic is not"})
        fps = {"RV": self._footprint(fp_res_vertical()), "DIP14": self._footprint(fp_dip(14, "DIP-14-W7.62-P2.54")),
               "DIP6": self._footprint(fp_dip(6, "DIP-6-W7.62-P2.54")), "TO92": self._footprint(fp_to92()),
               "SEED": self._footprint(fp_seed_breakout()), "SWLED": self._footprint(fp_led_button()),
               "ENC": self._footprint(fp_ec11()), "TRS": self._footprint(fp_pj366st()),
               "SIP9": self._footprint(fp_sip(9))}
        sizes = sorted({int(kind[3:]) for _, kind, _ in circuit.HEADERS})
        for n in sizes:
            fps[f"HDR{n}"] = self._footprint(fp_header(n))
        fps["HDR8RA"] = self._footprint(fp_header_ra(8))
        dip16 = self.device_attrs("HC595N")["Footprint"]
        for key in STANDING:                                      # each main-board resistor again, standing up
            a = self.device_attrs(key)
            self._copy(key + "V", key, a["Manufacturer Part"], ["Resistors", "Through Hole Resistors"],
                       Footprint=fps["RV"])
        diode = self.device_attrs("D5819")["Symbol"]              # the 1N4148's own symbol is not cached
        self._copy("D4148", "D1N4148", "1N4148", ["Diodes"], Symbol=diode)
        self._copy("BAT85", "D1N4148", "BAT85", ["Diodes", "Schottky Diodes"], Symbol=diode,
                   **{"Manufacturer Part": "BAT85", "LCSC Part Name": "BAT85", "Supplier Part": "",
                      "Manufacturer": "", "Datasheet": "", "Description": "Schottky diode 30 V 200 mA, DO-35"})
        self._copy("TL074N", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        new = [
            ("SEED", seed_symbol(), "Daisy Seed + seed_power_opamps", "U?", fps["SEED"],
             "Daisy Seed plugged into Rob Heel's seed_power_opamps breakout, audio in and out through the "
             "breakout's op-amps; 2.54 mm socket strips on the main board"),
            ("HC595", hc595_symbol(), "74HC595", "U?", dip16, "8-bit shift register with output latch, DIP-16"),
            ("HC165", hc165_symbol(), "74HC165", "U?", dip16, "8-bit parallel-in shift register, DIP-16"),
            ("H11L1", h11l1_symbol(), "H11L1", "U?", fps["DIP6"],
             "Optocoupler with Schmitt-trigger open-collector output, 3-15 V, DIP-6: 1 anode, 2 cathode, "
             "4 output, 5 GND, 6 VCC (MIDI in)"),
            ("NPN", npn_symbol(), "2N3904", "Q?", fps["TO92"], "NPN transistor, TO-92 (E B C)"),
            ("SWLED", led_button_symbol(), "LED button red, Thonk low profile", "SW?", fps["SWLED"],
             "Thonk low-profile LED button, red: 7.5 mm body, 5.5 mm round cap, 1+2 / 3+4 contacts, LED anode 5, "
             "cathode 6. Clip the three plastic feet off: the board has no holes for them"),
            ("ENC", encoder_symbol(), "EC11 encoder with switch", "ENC?", fps["ENC"],
             "Rotary encoder with push switch, EC11 pattern, vertical, M7 bushing, D shaft (Alps EC11E or Bourns "
             "PEC11R). A / B phases, C common, S1 / S2 switch, MP1 / MP2 mounting tabs"),
            ("RN9", network_symbol(), "10k x8 bussed SIP-9", "RN?", fps["SIP9"],
             "Resistor network, 8 x 10k bussed, SIP-9, pin 1 common (Bourns 4609X-101-103LF, Tayda A103J)"),
            ("JACK_TRS", trs_symbol(), "Thonkiconn stereo PJ366ST", "J?", fps["TRS"],
             "3.5 mm stereo jack, QingPu WQP-PJ366ST (Thonk): 1 sleeve, 2 ring, 3 tip, no switches"),
        ]
        for n in sizes:
            new.append((f"HDR{n}", header_symbol(n), f"Pin header 1x{n}", "H?", fps[f"HDR{n}"],
                        f"Board-to-board header, 1x{n}, 2.54 mm"))
        new.append(("HDR8RA", header_symbol(8), "Pin header 1x8 right angle", "CN?", fps["HDR8RA"],
                    "Right-angle male header 1x8, 2.54 mm, for the display module's cable (MX1.25 to Dupont); the "
                    "plug lies flat on the board"))
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
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
                   "description": "RYK SIDE FX clone: Daisy Seed on the seed_power_opamps breakout, TL074 CV inputs, "
                                  "H11L1 MIDI in, EC11 encoders and LED buttons on 74HC165/595, 1.9in ST7789 "
                                  "display. Two stacked PCBs, 14HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


def dev_of(part):
    if part.kind == "R":
        return {"1k": "R1k", "10k": "R10k"}.get(part.value, "R" + part.value)
    if part.kind == "C":
        return {"100n": "C100n", "1u": "C1u", "10u": "C10uK"}.get(part.value, "C" + part.value)
    return {"TL074": "TL074N", "1N4148": "D4148"}.get(part.kind, part.kind)


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


def supply(pg, amp, sec):
    if sec == 1:   # this unit carries the supply pins
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))


def cap_to_rail(pg, part, x, top, rail_kind="IN"):
    """A decoupling cap standing at x: its rail port above, its ground below."""
    c = vpart(pg, part, x, top + 20)
    pg.wire([c["1"], (x, top + 5), (x - 20, top + 5)], part.nets["1"])
    pg.port(x - 20, top + 5, part.nets["1"], rail_kind, "left")
    pg.ground(c["2"], part.nets["2"])
    return c


# ------------------------------------------------------------------ main board
def port_kind(net):
    """Direction of a net port, seen from the Seed."""
    if net in ("CLK", "MIDI_RX", "BTN_SHIFT", "SR_DIN", "IN1", "IN2") or net.startswith(("ADC_", "CV", "MIDI_")):
        return "IN"
    if net in ("+12V", "-12V", "3V3A", "3V3D", "BIAS", "CLK_IN"):
        return "IN"
    return "OUT"


def seed_block(pg, x, y):
    u = pg.place("U5", "SEED", x, y, des=(-80, -154, "LEFT_BOTTOM"), name=False)
    left = {n for _, n in SEED_LEFT}
    for pin, (name, net) in circuit.SEED.items():
        if not net:
            continue
        side = "left" if pin in left else "right"
        if net == "GND":
            pg.stub_gnd(u[pin], side, 15)
        else:
            pg.stub_port(u[pin], net, port_kind(net), side)
    return u


def cv_stage(pg, P, ox, oy, name, sec):
    """Marblesy's inverting stage around U6: Rin from the jack's port, Rf || Cf, Rs to the ADC port."""
    k = int(name[-1]) - 1
    rin, rfb, rs = P[f"R{10 + 3 * k}"], P[f"R{11 + 3 * k}"], P[f"R{12 + 3 * k}"]
    cfb = P[f"C{10 + k}"]
    amp = pg.place("U6", "TL074N", ox, oy, unit=sec, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
    a_in = pg.place(rin.ref, dev_of(rin), ox - 90, oy - 10, des=H_TXT[0], value_at=H_TXT[1])
    a_rf = pg.place(rfb.ref, dev_of(rfb), ox, oy - 60, des=H_TXT[0], value_at=H_TXT[1])
    a_rs = pg.place(rs.ref, dev_of(rs), ox + 100, oy, des=H_TXT[0], value_at=H_TXT[1])
    a_cf = pg.place(cfb.ref, dev_of(cfb), ox, oy - 90, des=(-20, -10, "LEFT_BOTTOM"), value_at=(2, -10, "LEFT_BOTTOM"))
    out, inm, inp = SECTION[sec]
    nin, nout = f"IN_{name}", f"OA_{name}"
    jx, kx = ox - 55, ox + 60
    pg.wire([a_in["2"], (jx, oy - 10)], nin)
    pg.wire([(jx, oy - 10), amp[inm]], nin)
    pg.wire([(jx, oy - 10), (jx, oy - 60)], nin)
    pg.wire([(jx, oy - 60), a_rf["1"]], nin)
    pg.wire([(jx, oy - 60), (jx, oy - 90), a_cf["1"]], nin)
    pg.wire([amp[out], (kx, oy)], nout)
    pg.wire([(kx, oy), a_rs["1"]], nout)
    pg.wire([(kx, oy), (kx, oy - 60)], nout)
    pg.wire([(kx, oy - 60), a_rf["2"]], nout)
    pg.wire([(kx, oy - 60), (kx, oy - 90), a_cf["2"]], nout)
    pg.stub_port(a_in["1"], name, "IN", "left")
    pg.stub_port(amp[inp], "BIAS", "IN", "left", length=30)
    pg.stub_port(a_rs["2"], f"ADC_{name}", "OUT", "right")
    supply(pg, amp, sec)
    pg.text(ox - 110, oy - 110, f"{name.replace('CV', 'CV ')}  ({['A', 'B', 'C', 'D'][sec - 1]} section)", 9)


def clock_block(pg, P, x0, y):
    """100k into a 2N3904 inverter, BAT85 clamp, 10k pull-up (Marblesy's stage)."""
    a = pg.place("R24", dev_of(P["R24"]), x0 + 40, y, des=H_TXT[0], value_at=H_TXT[1])
    q = pg.place("Q1", "NPN", x0 + 100, y, des=(14, -8, "LEFT_BOTTOM"), value_at=(14, 2, "LEFT_BOTTOM"))
    d = pg.place("D1", "BAT85", x0 + 80, y + 50, 270, *V_TXT)
    pu = pg.place("R25", dev_of(P["R25"]), x0 + 110, y - 60, 270, *V_TXT)
    b, c = (x0 + 80, y), (x0 + 110, y - 30)
    pg.stub_port(a["1"], "CLK_IN", "IN", "left")
    pg.wire([a["2"], b], "B_CLK")
    pg.wire([b, q["2"]], "B_CLK")
    pg.wire([b, d["1"]], "B_CLK")          # cathode up to the base
    pg.stub_gnd(d["2"])
    pg.stub_gnd(q["1"])
    pg.wire([q["3"], c], "CLK")
    pg.wire([pu["2"], c], "CLK")
    pg.wire([c, (x0 + 150, c[1])], "CLK")
    pg.port(x0 + 150, c[1], "CLK", "OUT", "right")
    pg.wire([pu["1"], (x0 + 110, y - 90), (x0 + 90, y - 90)], "3V3D")
    pg.port(x0 + 90, y - 90, "3V3D", "IN", "left")


def midi_block(pg, P, ux, uy):
    """TRS type A into the H11L1: ring -> 220R -> LED anode, tip -> LED cathode, 1N4148 across the LED;
    open-collector output pulled up to 3V3D."""
    u = pg.place("U7", "H11L1", ux, uy, des=(-40, -27, "LEFT_BOTTOM"), value_at=(-40, 37, "LEFT_BOTTOM"))
    a, k = u["1"], u["2"]                         # left column, rows 0 and 1
    xn = a[0] - 40                                # the node column left of the opto
    r = hpart(pg, P["R26"], xn - 80, a[1])
    pg.wire([r["2"], (xn, a[1])], "OPTO_A")
    pg.wire([(xn, a[1]), a], "OPTO_A")
    d = vpart(pg, P["D2"], xn, a[1] + 20, texts_left=True)      # pin 1 (cathode) on the anode side
    pg.wire([(xn, a[1]), d["1"]], "OPTO_A")
    tip = (xn, a[1] + 80)
    pg.wire([d["2"], tip], "MIDI_TIP")
    pg.wire([k, (xn + 20, k[1]), (xn + 20, tip[1]), tip], "MIDI_TIP")
    pg.wire([tip, (xn - 100, tip[1])], "MIDI_TIP")
    pg.port(xn - 100, tip[1], "MIDI_TIP", "IN", "left")
    pg.stub_port(r["1"], "MIDI_RING", "IN", "left")
    vcc, vo, gnd = u["6"], u["4"], u["5"]
    pg.stub_port(vcc, "3V3D", "IN", "right")
    xo = vo[0] + 80                               # the pull-up's column, clear of the 3V3D port's name
    pu = vpart(pg, P["R27"], xo, vo[1] - 60)
    pg.wire([pu["1"], (xo, vo[1] - 70), (xo + 20, vo[1] - 70)], "3V3D")
    pg.port(xo + 20, vo[1] - 70, "3V3D", "IN", "right")
    pg.wire([vo, (xo, vo[1])], "MIDI_RX")
    pg.wire([pu["2"], (xo, vo[1])], "MIDI_RX")
    pg.wire([(xo, vo[1]), (xo + 40, vo[1])], "MIDI_RX")
    pg.port(xo + 40, vo[1], "MIDI_RX", "OUT", "right")
    pg.stub_gnd(gnd, "down", 20)
    cap_to_rail(pg, P["C17"], xo + 130, vo[1] + 20)
    pg.text(xo + 145, vo[1] + 75, "C17 at U7 pin 6", 8)


def bias_block(pg, P, x, top):
    a = vpart(pg, P["R22"], x, top)
    b = vpart(pg, P["R23"], x, top + 60)
    c = vpart(pg, P["C14"], x + 40, top + 60)
    node = (x, top + 50)
    pg.wire([a["2"], node], "BIAS")
    pg.wire([node, b["1"]], "BIAS")
    pg.wire([node, (x + 40, top + 50), c["1"]], "BIAS")
    pg.wire([node, (x - 20, top + 50)], "BIAS")
    pg.port(x - 20, top + 50, "BIAS", "OUT", "left")
    pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "3V3A")
    pg.port(x - 20, top - 10, "3V3A", "IN", "left")
    pg.stub_gnd(b["2"])
    pg.stub_gnd(c["2"])


def decoupling_pair(pg, P, cp, cn, x, top):
    a = vpart(pg, P[cp], x, top)
    b = vpart(pg, P[cn], x, top + 60)
    node = (x, top + 50)
    pg.wire([a["2"], node], "GND")
    pg.wire([node, b["1"]], "GND")
    pg.wire([node, (x - 15, top + 50)], "GND")
    pg.gnd(x - 15, top + 50, 270)
    pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "+12V")
    pg.port(x - 20, top - 10, "+12V", "IN", "left")
    pg.wire([b["2"], (x, top + 110), (x - 20, top + 110)], "-12V")
    pg.port(x - 20, top + 110, "-12V", "IN", "left")


def headers_row(pg, P, refs, x0, y, pitch, gnds):
    for k, ref in enumerate(refs):
        kind = P[ref].kind
        n = int(kind[3:])
        x = x0 + k * pitch
        h = pg.place(ref, kind, x, y, des=(-10, -n * 5 - 10, "LEFT_BOTTOM"), name=False)
        for num, net in P[ref].nets.items():
            if net in gnds:
                pg.ground(h[num], net, "left", 15)
            else:
                pg.stub_port(h[num], net, "IN", "left")


def main_page(pr, P):
    pg = MPage(pr, "Main board: Seed, CV inputs, clock, MIDI, headers", 1)
    pg.text(40, Y(40), "Daisy Seed on the seed_power_opamps breakout (2.54 mm sockets on this board); audio in and "
                       "out through the breakout's op-amps (J5 / J4)", 12)
    seed_block(pg, 230, Y(260))
    pg.text(560, Y(70), "CV inputs: TL074 inverting stages, gain -0.27 (+-5 V -> 0.33..3.03 V) around BIAS, "
                        "1k into the ADC", 12)
    for i, (name, sec) in enumerate(circuit.CV_CHANNELS):
        cv_stage(pg, P, 700, Y(200 + i * 170), name, sec)
    pg.text(1000, Y(130), "Clock input: 100k into a 2N3904 inverter (CLK is active low)", 12)
    clock_block(pg, P, 1060, Y(250))
    pg.text(1000, Y(400), "MIDI in, TRS type A (ring = source, tip = sink); sleeve left open on the jack", 12)
    midi_block(pg, P, 1290, Y(470))
    pg.text(1400, Y(100), "Bias 1.32 V; U6 decoupling", 12)
    bias_block(pg, P, 1440, Y(160))
    decoupling_pair(pg, P, "C15", "C16", 1580, Y(160))
    pg.text(1545, Y(300), "C15 / C16 at U6", 8)
    pg.text(40, Y(810), "Board-to-board headers: female sockets on this board, pin 1 at the top; the faceplate has "
                        "the male pins (HF1..HF4)", 12)
    headers_row(pg, P, [r for r, _, _ in circuit.HEADERS], 140, Y(900), 200, ("GND",))
    pg.text(900, Y(700), "Button LEDs: 74HC595 at the chain's end (QF..QH spare), 470R per LED to H3", 12)
    sr595_block(pg, P, 1000, Y(820))
    led_resistors(pg, P, 1330, Y(770))
    cap_to_rail(pg, P["C3"], 1560, Y(770))
    pg.text(1525, Y(860), "C3 at U3 pin 16", 8)
    pg.text(40, Y(1090), "Net ports with the same name connect. GND is one net here: AGND (Seed pin 20), DGND "
                         "(pin 40) and the breakout's GND pins; the faceplate's GND_F and GND_D_F join it at the "
                         "headers.", 10)
    pg.text(40, Y(1110), "Presets live in the Seed's QSPI flash; SDMMC1 (D1..D6) stays free.", 10)
    return pg


# ------------------------------------------------------------------ faceplate
def jack_block(pg, part, jx, jy):
    trs = part.kind == "JACK_TRS"
    j = pg.place(part.ref, part.kind if trs else "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
    pg.text(jx - 25, jy + 30, part.label + (" (TRS, sleeve open)" if trs else ""), 10)
    nets = part.nets
    if "1" in nets:
        s = j["1"]
        pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND_F")
        pg.flag(s[0] + 20, s[1] - 20, 90, "GND_F")
    tn = nets.get("2")
    if tn == "GND_F":
        pg.stub_flag(j["2"], "GND_F", "right", 20)
    elif tn:
        pg.stub_port(j["2"], tn, "IN", "right", length=50 if trs else 20)
    x, y = j["3"]
    pg.wire([(x, y), (x + 100, y)], nets["3"])
    pg.port(x + 100, y, nets["3"], "OUT" if (tn or trs) else "IN", "right")


def encoder_block(pg, part, ex, ey):
    e = pg.place(part.ref, "ENC", ex, ey, des=(-30, -32, "LEFT_BOTTOM"), name=False)
    pg.text(ex - 30, ey + 42, f"{part.label} encoder", 9)
    nets = part.nets
    pg.stub_port(e["A"], nets["A"], "OUT", "left")
    pg.stub_port(e["B"], nets["B"], "OUT", "left")
    pg.stub_flag(e["C"], "GND_D_F", "left", 15)
    pg.stub_port(e["S2"], nets["S2"], "OUT", "right")
    bx = e["S1"][0] + 15
    pts = []
    for num in ("S1", "MP1", "MP2"):
        pg.wire([e[num], (bx, e[num][1])], "GND_D_F")
        pts.append((bx, e[num][1]))
    for a, b in zip(pts, pts[1:]):
        pg.wire([a, b], "GND_D_F")
    pg.wire([pts[-1], (bx, pts[-1][1] + 10)], "GND_D_F")
    pg.flag(bx, pts[-1][1] + 10, 0, "GND_D_F")


def button_block(pg, P, part, bx, by):
    s = pg.place(part.ref, "SWLED", bx, by, des=(-50, -42, "LEFT_BOTTOM"), name=False)
    pg.text(bx - 50, by + 48, f"{part.label} (LED button)", 9)
    net = part.nets["3"]
    gx = s["1"][0] - 15
    pg.wire([s["1"], (gx, s["1"][1])], "GND_D_F")
    pg.wire([s["2"], (gx, s["2"][1])], "GND_D_F")
    pg.wire([(gx, s["1"][1]), (gx, s["2"][1])], "GND_D_F")
    pg.wire([(gx, s["1"][1]), (gx, s["1"][1] - 10)], "GND_D_F")
    pg.flag(gx, s["1"][1] - 10, 180, "GND_D_F")
    nx = s["3"][0] + 15
    pg.wire([s["3"], (nx, s["3"][1])], net)
    pg.wire([s["4"], (nx, s["4"][1])], net)
    pg.wire([(nx, s["3"][1]), (nx, s["4"][1])], net)
    pull = next((p for p in P.values() if p.kind == "R" and p.nets["2"] == net), None)
    if pull:                                       # SHIFT's own pull-up (the others are in RN2)
        r = vpart(pg, pull, nx, s["3"][1] - 40)
        pg.wire([r["2"], (nx, s["3"][1])], net)
        pg.wire([r["1"], (nx, s["3"][1] - 50), (nx - 20, s["3"][1] - 50)], "3V3D_F")
        pg.port(nx - 20, s["3"][1] - 50, "3V3D_F", "IN", "left")
    pg.wire([(nx, s["4"][1]), (nx + 20, s["4"][1])], net)
    pg.port(nx + 20, s["4"][1], net, "OUT", "right")
    pg.stub_port(s["5"], part.nets["5"], "IN", "left")
    pg.stub_flag(s["6"], "GND_D_F", "right", 15)


def faceplate_page_1(pr, P):
    pg = MPage(pr, "Faceplate 1: jacks, encoders, buttons", 1)
    pg.page_count = "2"
    pg.text(40, Y(40), "Jacks (Thonkiconn): sleeves to GND_F, unpatched inputs grounded by the switch lug, IN 2 "
                       "normalled to IN 1, outputs leave the lug open; MIDI on a stereo Thonkiconn", 12)
    jacks = sorted((p for p in P.values() if p.kind in ("JACK", "JACK_TRS")), key=lambda p: int(p.ref[1:]))
    for i, part in enumerate(jacks):
        col, row = divmod(i, 5)
        jack_block(pg, part, 110 + col * 360, Y(140 + row * 105))
    pg.text(860, Y(80), "Encoders (EC11 with push): C, switch and tabs to GND_D_F; A, B and the switch pulled "
                        "up into the 74HC165s (page 2)", 12)
    for k, (ref, label) in enumerate(circuit.ENCODERS):
        encoder_block(pg, P[ref], 1000 + (k % 2) * 380, Y(180 + (k // 2) * 150))
    pg.text(40, Y(690), "Buttons: Thonk low-profile LED buttons, red (contacts 1+2 / 3+4, LED on 5 / 6). The sends "
                        "are pulled up in RN2, SHIFT by R6 to its own Seed pin; LEDs from U3 through 470R", 12)
    for k, (ref, label, net) in enumerate(circuit.BUTTONS):
        button_block(pg, P, P[ref], 150 + k * 310, Y(820))
    return pg


def sr165_block(pg, P, ref, x, y):
    sr = pg.place(ref, "HC165", x, y, des=(-50, -57, "LEFT_BOTTOM"), value_at=(-50, 63, "LEFT_BOTTOM"))
    nets = P[ref].nets
    for num in ("1", "2", "10", "15", "16", "8"):
        if nets[num] == "GND_D_F":
            pg.stub_flag(sr[num], "GND_D_F", "left", 15)
        else:
            pg.stub_port(sr[num], nets[num], "IN" if num != "10" else "IN", "left")
    for num in circuit.HC165_INPUTS:
        pg.stub_port(sr[num], nets[num], "IN", "right")
    pg.stub_port(sr["9"], nets["9"], "OUT", "right")


def network_block(pg, P, ref, x, y):
    rn = pg.place(ref, "RN9", x, y, des=(-30, -47, "LEFT_BOTTOM"), value_at=(-30, 53, "LEFT_BOTTOM"))
    nets = P[ref].nets
    pg.stub_port(rn["1"], nets["1"], "IN", "left")
    for i in range(8):
        pg.stub_port(rn[str(i + 2)], nets[str(i + 2)], "OUT", "right")


def sr595_block(pg, P, x, y):
    sr = pg.place("U3", "HC595", x, y, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
    nets = P["U3"].nets
    for num in ("14", "11", "12", "10", "16"):
        pg.stub_port(sr[num], nets[num], "IN", "left")
    pg.ground(sr["13"], nets["13"], "left", 15)
    pg.ground(sr["8"], nets["8"], "left", 15)
    for num in ("15", "1", "2", "3", "4", "5", "6", "7"):
        if nets.get(num):
            pg.stub_port(sr[num], nets[num], "OUT", "right")


def led_resistors(pg, P, x, y):
    """The 470R per button LED, in a column of their own: 595 output port -> R -> the LED's port."""
    for k, ref in enumerate(circuit.LED_ORDER):
        r = P[f"R{k + 1}"]
        rr = hpart(pg, r, x, y + 30 * k)
        pg.stub_port(rr["1"], r.nets["1"], "IN", "left")
        pg.stub_port(rr["2"], r.nets["2"], "OUT", "right")


def lcd_block(pg, P, x, y):
    h = pg.place("CN1", "HDR8RA", x, y, des=(-10, -50, "LEFT_BOTTOM"), name=False)
    names = ["VCC", "GND", "DIN", "CLK", "CS", "DC", "RST", "BL"]
    for i, net in enumerate(circuit.LCD_PINS):
        p = h[str(i + 1)]
        if net == "GND_D_F":
            pg.stub_flag(p, net, "left", 15)
        else:
            pg.stub_port(p, net, "IN", "left")
        pg.text(x + 14, p[1] + 3, names[i], 8)


def faceplate_page_2(pr, P):
    pg = MPage(pr, "Faceplate 2: shift registers, display, headers", 2)
    pg.page_count = "2"
    pg.text(40, Y(40), "One chain: SR_CLK to the 74HC165s here and the main board's 74HC595, SR_LOAD = /PL and "
                       "RCLK; U2 shifts into U1, U1 Q7 = SR_DIN; every 165 input pulled up by its network", 12)
    sr165_block(pg, P, "U1", 230, Y(200))
    sr165_block(pg, P, "U2", 230, Y(440))
    network_block(pg, P, "RN1", 640, Y(200))
    network_block(pg, P, "RN2", 640, Y(440))
    pg.text(1100, Y(100), "Display cable (Waveshare order), right-angle header", 12)
    lcd_block(pg, P, 1300, Y(220))
    pg.text(950, Y(380), "Decoupling: C1 / C2 at U1 / U2 pin 16, C4 (10 uF MLCC) beside CN1", 12)
    for k, ref in enumerate(("C1", "C2", "C4")):
        cap_to_rail(pg, P[ref], 1010 + k * 120, Y(430))
    pg.text(40, Y(640), "Headers to the main board (male pins here, pin 1 at the top)", 12)
    headers_row(pg, P, [circuit.fb_ref(r) for r, _, _ in circuit.HEADERS], 140, Y(740), 260, ("GND_F", "GND_D_F"))
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
    main_pages = [main_page(pr, PM)]
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
    # the panel: a board of its own, no parts; its schematic page only carries a note
    panel_page = MPage(pr, "Panel", 1)
    panel_page.text(70, Y(60), "Side FXy 14HP panel as a PCB: no parts, no nets. Holes, slots, the display window, "
                               "silkscreen and the bare-copper output band and block stack are in the PCB document; "
                               "the art is hardware/panel/side-fx-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("SideFXy Main", main_pages, board_mb), ("SideFXy Faceplate", fp_pages, board_fb),
              ("SideFXy Panel", [panel_page], board_panel)], OUT, template)
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
