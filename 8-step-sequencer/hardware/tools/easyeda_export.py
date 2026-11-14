"""Eight as an EasyEDA Pro project (.epro2): the schematic of its one board,
that board placed (pcb.py), and the panel as a second PCB (panel_pcb.py).

Copied from the S&H exporter (sample-hold/hardware/tools) with the LED
button, the bussed network and the IC symbol from Side FXy's and the 2 x 5
header from Envy's (copies here, not imports, so work on one module can't
break the other). Built on the Plaitsy exporter for the file format, the
connectivity check and the previews. Library parts come from two caches of
your MorrisSynth export: plaitsy/hardware/easyeda/morrissynth-parts.epru
(TL074ACN symbol, WQP518MA jack, PTV09A pot symbol, LR1F resistors, FG28
capacitors, 1N5819, the 1N4148's DO-35 footprint, net ports, ground flag,
sheet frame) and stereo-mixer/hardware/easyeda/stereo-mixer-parts.epru (LR1F
10R, the 178MU0033 electrolytic). Drawn or generated here, in the same style
and with real pin numbers:

  footprints  the Mega 2560 Pro's sockets (circuit.MEGA_PADS, pad numbers =
              its pin names), the ADS1115 and MCP4725 breakouts on 1 x 10 /
              1 x 6 sockets, R-78E (SIP-3), DIP-14, TO-92, the Alpha 9 mm pot,
              the Thonk LED button, SIP-9, the 2 x 5 power header, standing
              resistors
  symbols     Mega 2560 Pro, ADS1115 and MCP4725 breakouts, LM4040 in TO-92
              (2 = cathode; 1 and 3 both to GND, so TI's LM4040 and the
              LM4040-N both fit), R-78E, LED button, bussed network, 2 x 5
              header; BAT85 takes the 1N5819 symbol (1 = cathode)

Pages: Mega, CLOCK and RESET; row A; row B; controls, ADC and DACs; outputs;
power. Every block ends in net ports; ports with the same name connect
across the pages.

Run from 8-step-sequencer/hardware/tools:  python easyeda_export.py
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


def _load(name):
    spec = importlib.util.spec_from_file_location("eight_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")

LIBFILES = [os.path.join(PLAITSY, "..", "easyeda", "morrissynth-parts.epru"),
            os.path.normpath(os.path.join(HERE, "..", "..", "..", "stereo-mixer", "hardware", "easyeda",
                                          "stereo-mixer-parts.epru"))]
SECTION = circuit.SECTION
UNIT = {"A": 1, "B": 2, "C": 3, "D": 4}          # op-amp symbol units; unit 1 carries the supply pins

NAME = "Eight"
TITLE = "Eight"
OUT = os.path.join(HERE, "..", "easyeda", "Eight.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "eight-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil
PAGE_COUNT = "6"

# Library devices used as they are (uuids from the two caches)
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0
    "R10k": "a9cc8fbe474242dc9110194515734c75",      # LR1F10K
    "R10R": "94e97e59e04b421d92158c6257818225",      # LR1F10R
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00
    "C10u": "21e4ec8defc34a489f66b07134d13cd6",      # 178MU0033, 10 uF 35 V (2 = +)
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol; footprint replaced below)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "POT": "be9d2c8f5f814271a402f956f18b56f9",       # PTV09A-4025F-B103 (its symbol)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819 (1 = cathode)
    "D4148LIB": "c0160a3f74384e849dc1cc5a24d54846",  # 1N4148 (its DO-35 footprint, pad 1 = the band)
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "22k": ("LR1F22K", "22kΩ"), "820R": ("LR1F820R", "820Ω")}
C_NEW = {"1n": ("FG28C0G1H102JNT00", "1nF"), "100p": ("FG28C0G1H101JNT00", "100pF")}


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
    """A through-hole footprint in mm; written as an EasyEDA Pro FOOTPRINT doc (the S&H's).
    Pads are round (or square) with round holes, or oval with slot holes (slot=(w, h)) like the
    library pots' lugs."""

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
    hx, hy = half * 1.27 + 0.7, 3.25       # body: 19.2 x 6.5 mm for DIP-14
    f.rect(-hx, -hy, hx, hy)
    f.circle(-hx + 0.9, -hy + 0.9, 0.3)
    return f


def fp_to92():
    f = Footprint("TO-92-INLINE-P2.54", "U?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.line(-2.6, -1.3, 2.6, -1.3)
    f.circle(0, 0, 2.6)
    return f


def fp_alpha_pot():
    """Alpha 9 mm vertical pot, RD901F (the mixer's footprint), in the frame of the library PTV09A footprint:
    pins 1-3 at y = -3.5, x = -2.5 / 0 / 2.5, the shaft 7.5 mm from them at y = +4.0, the two mounting lugs
    4 / 5 on the shaft line at +-4.8 as oval pads with slots."""
    f = Footprint("POT-ALPHA-9MM-RD901F", "RV?")
    for i, x in enumerate((-2.5, 0.0, 2.5)):
        f.pad(i + 1, x, -3.5, 1.0, 1.8, square=(i == 0))
    for num, x in (("4", -4.8), ("5", 4.8)):
        f.pad(num, x, 4.0, size=2.7, h=3.2, slot=(1.1, 1.8))
    f.rect(-4.75, -2.5, 4.75, 8.85)       # body, 9.5 wide, from 1 mm off the pin row to 4.85 mm past the shaft
    f.circle(0, 4.0, 3.5)
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


def fp_sip(n):
    """Single-in-line resistor network, 2.54 mm, pin 1 (common) square; body 2.5 mm thick."""
    f = Footprint(f"SIP-{n}-P2.54", "RN?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.rect(x0 - 1.4, -1.25, x0 + (n - 1) * 2.54 + 1.4, 1.25)
    f.line(x0 + 1.27, -1.25, x0 + 1.27, 1.25)      # pin 1 end marked
    return f


def fp_box_header(n):
    """Shrouded 2 x n/2 box header, 2.54 mm, odd pins in the row at -1.27 (pin 1 square, the red stripe)."""
    f = Footprint(f"IDC-TH_{n}P-P2.54-BOX", "J?")
    cols = n // 2
    x0 = -(cols - 1) * 1.27
    for i in range(cols):
        f.pad(2 * i + 1, x0 + 2.54 * i, -1.27, 1.0, 1.6, square=(i == 0))
        f.pad(2 * i + 2, x0 + 2.54 * i, 1.27, 1.0, 1.6)
    hx = (cols - 1) * 1.27 + 5.08
    f.rect(-hx, -4.45, hx, 4.45)
    f.rect(-2.25, 4.45, 2.25, 3.6)                 # the key slot
    return f


def fp_mega():
    """The Mega 2560 Pro (Embed) on female sockets: circuit.MEGA_PADS (Alarm-Siren's measured
    Clone_Mega2560_Pro_Socket, the board's top view) turned into this frame, y up, origin at the module's
    centre; the USB end is at -x. Pad numbers are the pin names (D52, A7, 5V1 ...). 1.73 mm pads, 1.0 mm
    holes; the ICSP header gets no socket and no pads."""
    f = Footprint("MEGA2560-PRO-EMBED-SOCKETS", "U?")
    cx, cy = circuit.MEGA_W / 2, circuit.MEGA_H / 2
    for name, (x, y) in circuit.MEGA_PADS.items():
        f.pad(name, round(x - cx, 4), round(cy - y, 4), 1.0, 2 * circuit.MEGA_PAD, square=(name == "VIN1"))
    f.rect(-cx, -cy, cx, cy)
    f.rect(-cx, -4.0, -cx + 5.0, 4.0)            # the micro-USB socket at the USB end (about where it sits)
    return f


def fp_breakout(n, title, width, depth):
    """A breakout module on a 1 x n socket strip, pin 1 square, the module's outline drawn to one side of
    the row (width along the row, depth away from it). Outlines are the usual boards' sizes: check them
    against the ones you use before placing."""
    f = Footprint(title, "U?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.27, -1.27, x0 + (n - 1) * 2.54 + 1.27, 1.27)
    f.rect(-width / 2, -depth + 1.5, width / 2, 1.5)
    return f


def fp_r78e():
    """Recom R-78E (and Traco TSR 0.5), SIP-3 on 2.54 mm: 1 +Vin, 2 GND, 3 +Vout; body 11.6 x 7.5 mm,
    the pins 1.5 mm in from its front face."""
    f = Footprint("SIP-3-P2.54-R78E", "U?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(-5.8, -1.5, 5.8, 6.0)
    return f


# ------------------------------------------------------------------ symbols
def ic_symbol(title, part_id, left, right, designator="U?", w=50):
    """Rectangular IC symbol; left/right = [(row, num, name)], rows 10 apart (Side FXy's)."""
    rows = max([r for r, _, _ in left + right]) + 1
    half = rows * 5
    s = Symbol(title, part_id, designator, [NAME])
    s.rect(-w, -half - 5, w, half + 5)
    for row, num, name in left:
        s.pin(num, name, -w - 10, -half + 5 + 10 * row, 0, show=True, edge=-w)
    for row, num, name in right:
        s.pin(num, name, w + 10, -half + 5 + 10 * row, 180, show=True, edge=w)
    return s


# The Mega's pins in two columns: the 2 x 21 row (power, D0-D31) on the left, the 2 x 16 row and its
# 2 x 3 stub (A0-A15, D32-D53) on the right
MEGA_LEFT = ["VIN1", "VIN2", "GND1", "GND2", "5V1", "5V2", "3V31", "3V32", "AREF", "RST1"] + [f"D{i}" for i in range(32)]
MEGA_RIGHT = [f"A{i}" for i in range(16)] + [f"D{i}" for i in range(32, 54)]
MEGA_SHOWN = {"VIN1": "VIN", "VIN2": "VIN", "GND1": "GND", "GND2": "GND", "5V1": "5V", "5V2": "5V",
              "3V31": "3V3", "3V32": "3V3", "RST1": "RST"}


def mega_symbol():
    assert set(MEGA_LEFT + MEGA_RIGHT) == set(circuit.MEGA_PADS)
    s = ic_symbol("Mega 2560 Pro (Embed)", "MEGA2560PRO.1",
                  [(r, n, MEGA_SHOWN.get(n, n)) for r, n in enumerate(MEGA_LEFT)],
                  [(r, n, MEGA_SHOWN.get(n, n)) for r, n in enumerate(MEGA_RIGHT)], w=60)
    s.text(-40, 150, "Mega 2560 Pro", 10)
    s.text(-40, 163, "(Embed), on sockets", 8)
    return s


# The breakouts' symbols: pins in the order drawn (the ground pins last on the left, so one flag takes
# them all); pin numbers from the header order in circuit.BREAKOUT_PINS
BREAKOUT_SIDES = {"ADS1115_MOD": (["VDD", "SCL", "SDA", "ALRT", "ADDR", "GND"], ["A0", "A1", "A2", "A3"]),
                  "MCP4725_MOD": (["VCC", "SCL", "SDA", "A0", "GND"], ["OUT"])}


def breakout_symbol(kind, title, part_id):
    names = circuit.BREAKOUT_PINS[kind]
    left_names, right_names = BREAKOUT_SIDES[kind]
    assert sorted(left_names + right_names) == sorted(names)
    left = [(r, str(names.index(nm) + 1), nm) for r, nm in enumerate(left_names)]
    right = [(r, str(names.index(nm) + 1), nm) for r, nm in enumerate(right_names)]
    return ic_symbol(title, part_id, left, right, w=40)


def lm4040_symbol():
    """LM4040 in TO-92 as wired here: 2 = cathode; 1 and 3 both go to GND (TI's LM4040: 3 anode, 1 tied to
    it; LM4040-N: 1 anode, 3 NC), so either part fits. K left, the anode pin 3 right, pin 1 down."""
    s = Symbol("LM4040-5.0 TO-92", "LM4040_5V0_TO92.1", "U?", [NAME])
    s.poly([(-20, 0), (-6, 0)])
    s.poly([(6, -7), (-6, 0), (6, 7), (6, -7)], closed=True)
    s.poly([(-6, -7), (-6, 7)])
    s.poly([(-6, -7), (-9, -9)])
    s.poly([(-6, 7), (-3, 9)])
    s.poly([(6, 0), (20, 0)])
    s.poly([(0, 4), (0, 10)])
    s.text(-14, -8, "5.0V", 6)
    s.pin("2", "K", -30, 0, 0)
    s.pin("3", "A", 30, 0, 180)
    s.pin("1", "A/NC", 0, 20, 90)
    return s


def r78e_symbol():
    """3-pin switching regulator: +Vin (1) left, +Vout (3) right, GND (2) down."""
    s = Symbol("R-78E5.0-0.5", "R78E.1", "U?", [NAME])
    s.rect(-30, -15, 30, 15)
    s.text(-20, -2, "R-78E 5V", 8)
    s.pin("1", "VIN", -40, 0, 0, show=True, edge=-30)
    s.pin("3", "VOUT", 40, 0, 180, show=True, edge=30)
    s.pin("2", "GND", 0, 25, 90)
    return s


def led_button_symbol():
    """Tactile switch with a built-in LED: contacts 1+2 and 3+4, LED on 5 and 6 (Side FXy's)."""
    left = [(0, "1", "1"), (1, "2", "2"), (3, "5", "LED A")]
    right = [(0, "3", "3"), (1, "4", "4"), (3, "6", "LED K")]
    return ic_symbol("LED button", "SWLED.3", left, right, designator="SW?")


def network_symbol():
    left = [(0, "1", "COM")]
    right = [(i, str(i + 2), f"R{i + 1}") for i in range(8)]
    return ic_symbol("Resistor network 8x bussed", "RN8BUS.1", left, right, designator="RN?", w=30)


def hdr10_symbol():
    """2 x 5 Eurorack power header: odd pins on the left, even on the right, pin 1 at the top (-12 V)."""
    s = Symbol("Eurorack power 2x5", "HDR2X5.1", "J?", [NAME])
    s.rect(-20, -25, 20, 25)
    for i in range(5):
        y = -20 + 10 * i
        s.pin(str(2 * i + 1), str(2 * i + 1), -30, y, 0, show=True, edge=-20)
        s.pin(str(2 * i + 2), str(2 * i + 2), 30, y, 180, show=True, edge=20)
    return s


# ------------------------------------------------------------------ project
STANDING = ["R1k", "R10k", "R10R"] + ["R" + v for v in R_NEW]   # every resistor stands up (dev key + "V")


class MPage(Page):
    page_count = PAGE_COUNT

    def place(self, ref, dev_key, *args, **kw):
        if dev_key in STANDING:
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
        vals = [("Symbol", sym), ("@Project Name", TITLE), ("@Page Count", self.page_count),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", TITLE),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V0.1"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", TITLE),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))

    def rail(self, pin, net, side="left", rise=10, length=20, kind="IN"):
        """A rail port above a pin: up `rise`, then `length` to the side."""
        x, y = pin
        x2 = x - length if side == "left" else x + length
        self.wire([(x, y), (x, y - rise), (x2, y - rise)], net)
        self.port(x2, y - rise, net, kind, side)


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

    def _new(self, key, symbol_uuid, fp_uuid, title, desig, desc, mpn=None):
        attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": mpn or title, "Designator": desig,
                 "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": symbol_uuid, "Footprint": fp_uuid,
                 "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
        self._device(key, title, attrs)

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
        self._copy("C47u", "C10u", "Electrolytic 47uF 25V", ["Capacitors", "Aluminum Electrolytic Capacitors"],
                   **{"Manufacturer Part": "Electrolytic 47uF 25V", "Value": "47uF", "Supplier Part": "",
                      "Datasheet": "", "Description": "Aluminium electrolytic 47 uF 25 V radial, 5 mm can, "
                                                      "pin 2 = +"})
        diode = self.device_attrs("D5819")["Symbol"]              # the 1N4148's own symbol is not cached
        self._copy("BAT85", "D4148LIB", "BAT85", ["Diodes", "Schottky Diodes"], Symbol=diode,
                   **{"Manufacturer Part": "BAT85", "LCSC Part Name": "BAT85", "Supplier Part": "",
                      "Manufacturer": "", "Datasheet": "",
                      "Description": "Schottky diode 30 V 200 mA, DO-35. Symbol pin 1 = cathode = the band = pad 1"})
        fps = {"RV": self._footprint(fp_res_vertical()), "DIP14": self._footprint(fp_dip(14, "DIP-14-W7.62-P2.54")),
               "TO92": self._footprint(fp_to92()), "POT": self._footprint(fp_alpha_pot()),
               "SWLED": self._footprint(fp_led_button()), "SIP9": self._footprint(fp_sip(9)),
               "HDR10": self._footprint(fp_box_header(10)), "MEGA": self._footprint(fp_mega()),
               "ADS": self._footprint(fp_breakout(10, "ADS1115-MODULE-1x10", 28.0, 17.8)),
               "MCP": self._footprint(fp_breakout(6, "MCP4725-MODULE-1x6", 18.0, 18.0)),
               "R78E": self._footprint(fp_r78e())}
        for key in STANDING:                                      # each resistor again, standing up
            a = self.device_attrs(key)
            self._copy(key + "V", key, a["Manufacturer Part"], ["Resistors", "Through Hole Resistors"],
                       Footprint=fps["RV"])
        self._copy("TL074N", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        self._copy("POTB10k", "POT", "Alpha 9mm B10k", ["Potentiometers"], Footprint=fps["POT"],
                   Name="={Value}", Value="B10k", **{"Manufacturer Part": "Alpha RD901F-40-15R1 B10K",
                                                     "Supplier Part": "", "Datasheet": "",
                                                     "Description": "Alpha 9 mm vertical pot B10k, T18 shaft "
                                                                    "(Thonk). Pin 3 = CW end, lugs 4 / 5"})
        swled = self._symbol(led_button_symbol())
        for key, colour in (("SWLED_R", "red"), ("SWLED_G", "green"), ("SWLED", "any colour")):
            self._new(key, swled, fps["SWLED"], f"LED button {colour}, Thonk low profile", "SW?",
                      f"Thonk low-profile LED button, {colour}: 7.5 mm body, 5.5 mm round cap, 1+2 / 3+4 contacts, "
                      "LED anode 5, cathode 6. Clip the three plastic feet off: the board has no holes for them")
        net = self._symbol(network_symbol())
        for key, val, mpn in (("RN9_10K", "10k", "4609X-101-103LF"), ("RN9_1K", "1k", "4609X-101-102LF")):
            self._new(key, net, fps["SIP9"], f"{val} x8 bussed SIP-9", "RN?",
                      f"Resistor network, 8 x {val} bussed, SIP-9, pin 1 common (Bourns {mpn})", mpn=mpn)
        new = [
            ("MEGA", mega_symbol(), fps["MEGA"], "Mega 2560 Pro (Embed)", "U?",
             "RobotDyn-style Mega 2560 Pro (Embed), CH340G, on 2.54 mm female sockets (2 x 21, 2 x 16, 2 x 3); "
             "its headers soldered pointing down. Pad numbers are the pin names"),
            ("ADS", breakout_symbol("ADS1115_MOD", "ADS1115 breakout", "ADS1115MOD.1"), fps["ADS"], "ADS1115 breakout", "U?",
             "ADS1115 16-bit ADC breakout (Adafruit 1085 or the generic blue board), 1 x 10 socket: VDD GND SCL SDA "
             "ADDR ALRT A0 A1 A2 A3"),
            ("MCP", breakout_symbol("MCP4725_MOD", "MCP4725 breakout", "MCP4725MOD.1"), fps["MCP"], "MCP4725 breakout", "U?",
             "MCP4725 12-bit DAC breakout, A0 chip (0x60 / 0x61, SparkFun style), 1 x 6 socket: VCC GND SCL SDA A0 "
             "OUT. Check the pin order against your boards"),
            ("LM4040", lm4040_symbol(), fps["TO92"], "LM4040-5.0 TO-92", "U?",
             "Precision shunt reference 5.000 V, TO-92 (LM4040DIZ-5.0 or TI's LM4040 in LP): 2 = cathode; 1 and 3 "
             "both to GND, which fits both pinouts"),
            ("R78E", r78e_symbol(), fps["R78E"], "R-78E5.0-0.5", "U?",
             "5 V 0.5 A switching regulator, SIP-3, 7805 pinout: 1 +Vin, 2 GND, 3 +Vout (Recom R-78E5.0-0.5 or "
             "Traco TSR 0.5-2450)"),
            ("HDR10", hdr10_symbol(), fps["HDR10"], "Box header 2x5 2.54mm", "J?",
             "Shrouded 2 x 5 Eurorack power header: pins 1-2 -12 V (red stripe), 3-8 GND, 9-10 +12 V"),
        ]
        for key, sym, fp, title, desig, desc in new:
            self._new(key, self._symbol(sym), fp, title, desig, desc)

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
        project = {"title": TITLE, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Eight: dual 8-step sequencer after the Korg SQ-1, the Kosmo build rebuilt for "
                                  "Eurorack. Mega 2560 Pro on sockets, ADS1115, 2x MCP4725, TL074. One PCB, 26HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


def dev_of(part):
    if part.kind == "R":
        return {"1k": "R1k", "10k": "R10k", "10k 1%": "R10k", "10R": "R10R"}.get(part.value, "R" + part.value)
    if part.kind == "C":
        return {"100n": "C100n"}.get(part.value, "C" + part.value)
    if part.kind == "CP":
        return "C" + part.value
    if part.kind == "POT":
        return "POT" + part.value
    if part.kind == "SWLED":
        return "SWLED_R" if "red" in part.value else "SWLED_G" if "green" in part.value else "SWLED"
    if part.kind == "RN9":
        return "RN9_10K" if part.value.startswith("10k") else "RN9_1K"
    return {"TL074": "TL074N", "DBAT85": "BAT85", "MEGA2560PRO": "MEGA", "ADS1115_MOD": "ADS",
            "MCP4725_MOD": "MCP"}.get(part.kind, part.kind)


def pin_map(part, pid):
    """Netlist pin id -> symbol pin number: the breakouts are wired by pin name."""
    if part.kind in circuit.BREAKOUT_PINS:
        return str(circuit.BREAKOUT_PINS[part.kind].index(pid) + 1)
    return pid


# ---------------------------------------------------------------- drawing helpers
def hpart(pg, part, x1, y, left_pin="1"):
    """Two-pin part drawn horizontally with `left_pin` at (x1, y), the other pin at (x1 + 40, y)."""
    rot = 0 if left_pin == "1" else 180
    return pg.place(part.ref, dev_of(part), x1 + 20, y, rot, des=H_TXT[0], value_at=H_TXT[1])


def vpart(pg, part, x, y1, top_pin="1"):
    """Two-pin part drawn vertically with `top_pin` at (x, y1), the other pin at (x, y1 + 40)."""
    rot = 270 if top_pin == "1" else 90
    return pg.place(part.ref, dev_of(part), x, y1 + 20, rot, *V_TXT)


def opamp(pg, sec, ox, oy):
    """A U5 section at (ox, oy): in- at (ox - 40, oy - 10), in+ at (ox - 40, oy + 10), out at (ox + 40, oy).
    Unit 1 also gets its supply pins labelled +12V / -12V."""
    amp = pg.place("U5", "TL074N", ox, oy, unit=UNIT[sec], des=(14, 30, "LEFT_BOTTOM"), name=False)
    if UNIT[sec] == 1:
        a, b = amp["4"], amp["11"]
        pg.wire([a, a], "+12V", label=(a[0] + 3, a[1] - 2, "LEFT_BOTTOM"))
        pg.wire([b, b], "-12V", label=(b[0] + 3, b[1] + 8, "LEFT_BOTTOM"))
    pg.text(ox - 30, oy + 45, f"U5{sec}", 8)
    return amp


def noninv(pg, P, sec, ox, oy, rf, rg):
    """Non-inverting stage (the S&H's): in+ left for the caller at (ox - 40, oy + 10); in- to a junction J
    above-left, with rf (pin 1 on the output) to the output node and rg (pin 2 on GND) to ground on the
    left. Returns the output node (ox + 60, oy)."""
    amp = opamp(pg, sec, ox, oy)
    out, inm, inp = SECTION[sec]
    fb, nout = P[rf].nets["2"], P[rf].nets["1"]
    j = (ox - 60, oy - 60)
    a_rf = hpart(pg, P[rf], ox - 20, oy - 60, left_pin="2")
    a_rg = hpart(pg, P[rg], ox - 100, oy - 60, left_pin="2")      # pin 1 lands on j
    pg.wire([amp[inm], (ox - 60, oy - 10), j], fb)
    pg.wire([j, a_rf["2"]], fb)
    assert a_rg["1"] == j
    pg.stub_gnd(a_rg["2"], "down", 10)
    k = (ox + 60, oy)
    pg.wire([amp[out], k], nout)
    pg.wire([k, (ox + 60, oy - 60), a_rf["1"]], nout)
    return k


def jack_block(pg, part, jx, jy, tip_kind):
    """Thonkiconn: sleeve to GND, the switch lug to a net port (or a ground flag), the tip to a net port
    (Envy's)."""
    j = pg.place(part.ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
    pg.text(jx - 25, jy + 30, part.label, 10)
    s = j["1"]
    pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND")
    pg.gnd(s[0] + 20, s[1] - 20, 90)
    lug = part.nets.get("2")
    if lug == "GND":
        pg.stub_gnd(j["2"], "right", 40)
    elif lug:
        pg.stub_port(j["2"], lug, "OUT" if tip_kind == "IN" else "IN", "right")
    x, y = j["3"]
    pg.wire([(x, y), (x + 100, y)], part.nets["3"])
    pg.port(x + 100, y, part.nets["3"], tip_kind, "right")


def lugs_to_gnd(pg, p):
    """The pot's mounting lugs 4 and 5 joined underneath it and grounded (Envy's)."""
    l4, l5 = p["4"], p["5"]
    yb = max(l4[1], l5[1]) + 10
    pg.wire([l4, (l4[0], yb), (l5[0], yb), l5], "GND")
    pg.wire([(l4[0], yb), (l4[0], yb + 10)], "GND")
    pg.gnd(l4[0], yb + 10, 0)


def pot_block(pg, part, px, py):
    """Library pot symbol at (px, py): CW end (3) left at (px - 22, py + 5), CCW end (1) right at
    (px + 18, py + 5), the wiper up at (px - 2, py - 15), the lugs under the ends. An end on GND joins the
    lug under it; an end on a rail gets a port; the wiper goes up to a port."""
    p = pg.place(part.ref, dev_of(part), px, py, des=(-40, -22, "LEFT_BOTTOM"), value_at=(-40, -12, "LEFT_BOTTOM"))
    lugs_to_gnd(pg, p)
    for pin, lug, side in (("3", "4", "left"), ("1", "5", "right")):
        net = part.nets[pin]
        if net == "GND":
            pg.wire([p[pin], p[lug]], "GND")
        else:
            pg.stub_port(p[pin], net, "IN", side)
    w = p["2"]
    wiper = part.nets["2"]
    pg.wire([w, (w[0], w[1] - 25), (w[0] + 20, w[1] - 25)], wiper)
    pg.port(w[0] + 20, w[1] - 25, wiper, "OUT", "right")
    pg.text(px - 40, py + 66, part.label, 9)            # under the lugs' ground flag
    return p


def button_block(pg, part, bx, by):
    """LED button at (bx, by): contacts 1+2 joined to a port (or GND), 3+4 joined to the button's net,
    the LED's anode and cathode to ports (left open on SHIFT, which has its LED unused)."""
    s = pg.place(part.ref, dev_of(part), bx, by, des=(-50, -42, "LEFT_BOTTOM"), name=False)
    pg.text(bx - 50, by + 48, part.label, 9)
    common, net = part.nets["1"], part.nets["3"]
    gx = s["1"][0] - 15
    pg.wire([s["1"], (gx, s["1"][1])], common)
    pg.wire([s["2"], (gx, s["2"][1])], common)
    pg.wire([(gx, s["1"][1]), (gx, s["2"][1])], common)
    if common == "GND":
        pg.wire([(gx, s["2"][1]), (gx, s["2"][1] + 30)], "GND")
        pg.gnd(gx, s["2"][1] + 30, 0)
    else:
        pg.rail((gx, s["1"][1]), common, "left", 15)
    nx = s["3"][0] + 15
    pg.wire([s["3"], (nx, s["3"][1])], net)
    pg.wire([s["4"], (nx, s["4"][1])], net)
    pg.wire([(nx, s["3"][1]), (nx, s["4"][1])], net)
    pg.wire([(nx, s["4"][1]), (nx + 20, s["4"][1])], net)
    pg.port(nx + 20, s["4"][1], net, "OUT", "right")
    if "5" in part.nets:
        pg.stub_port(s["5"], part.nets["5"], "IN", "left")
        pg.stub_port(s["6"], part.nets["6"], "OUT", "right")


def breakout_block(pg, part, dev, x, y, label=None):
    """A breakout at (x, y): its left pins to ports, the ground pins at the bottom of the left side joined
    to one flag, the right pins to ports."""
    b = pg.place(part.ref, dev, x, y, des=(-40, -(len(BREAKOUT_SIDES[part.kind][0]) * 5 + 12), "LEFT_BOTTOM"),
                 name=False)
    left_names, right_names = BREAKOUT_SIDES[part.kind]
    grounds = []
    for name in left_names:
        net = part.nets.get(name)
        if net == "GND":
            px, py = b[pin_map(part, name)]
            pg.wire([(px, py), (px - 15, py)], "GND")
            grounds.append((px - 15, py))
        elif net:
            pg.stub_port(b[pin_map(part, name)], net, "IN", "left", 25)
    for a, c in zip(grounds, grounds[1:]):
        pg.wire([a, c], "GND")
    if grounds:
        gx, gy = grounds[-1]
        pg.wire([(gx, gy), (gx, gy + 15)], "GND")
        pg.gnd(gx, gy + 15, 0)
    for name in right_names:
        if part.nets.get(name):
            pg.stub_port(b[pin_map(part, name)], part.nets[name], "OUT", "right")
    if label:
        pg.text(x + 50, y + len(left_names) * 5 + 20, label, 9)
    return b


def network_block(pg, part, x, y):
    """Bussed network: the common pin to GND or a rail port, the eight resistors to ports."""
    rn = pg.place(part.ref, dev_of(part), x, y, des=(-30, -47, "LEFT_BOTTOM"), value_at=(-30, 53, "LEFT_BOTTOM"))
    com = part.nets["1"]
    if com == "GND":
        pg.stub_gnd(rn["1"], "left", 15)
    else:
        pg.stub_port(rn["1"], com, "IN", "left")
    for i in range(8):
        pg.stub_port(rn[str(i + 2)], part.nets[str(i + 2)], "OUT", "right")


# ------------------------------------------------------------------ pages
INTO_MEGA = ("POT_", "BTN_", "CLOCK", "RESET", "SHIFT")


def mega_page(pr, P):
    pg = MPage(pr, "Mega, CLOCK and RESET", 1)
    pg.text(40, Y(40), "Mega 2560 Pro (Embed) on sockets: the Kosmo build's pins, plus RESET on D2. Unused pins "
                       "stay open (D0 / D1 serial, D3-D14, D16, VIN, 3V3, AREF, RST)", 12)
    u = P["U1"]
    m = pg.place("U1", "MEGA", 330, Y(560), des=(-60, -232, "LEFT_BOTTOM"), name=False)
    # the two GND pins and the two 5V pins, each pair joined to one flag or port
    for a, b, net in (("GND1", "GND2", "GND"), ("5V1", "5V2", "+5V")):
        assert u.nets[a] == u.nets[b] == net
        bx = m[a][0] - 15
        pg.wire([m[a], (bx, m[a][1])], net)
        pg.wire([m[b], (bx, m[b][1])], net)
        pg.wire([(bx, m[a][1]), (bx, m[b][1])], net)
        if net == "GND":
            pg.wire([(bx, m[a][1]), (bx - 15, m[a][1])], net)
            pg.gnd(bx - 15, m[a][1], 270)
        else:
            pg.wire([(bx, m[b][1]), (bx - 20, m[b][1])], net)
            pg.port(bx - 20, m[b][1], net, "IN", "left")
    for num, net in u.nets.items():
        if num in ("GND1", "GND2", "5V1", "5V2"):
            continue
        side = "left" if num in MEGA_LEFT else "right"
        kind = "IN" if net.startswith(INTO_MEGA) else "OUT"
        pg.stub_port(m[num], net, kind, side)
    pg.text(760, Y(110), "CLOCK and RESET inputs: tip -> 22k -> pin, 100k and 1n to GND, BAT85 clamps to +5V and "
                         "GND.", 11)
    pg.text(760, Y(130), "Non-inverting; trips at 1.8-3.7 V at the jack. An unpatched jack's lug grounds its tip.", 11)
    for i, (jack, tip, pin) in enumerate((("J1", "CLOCK_IN", "CLOCK"), ("J2", "RESET_IN", "RESET"))):
        y = Y(260 + 230 * i)
        input_stage(pg, P, tip, pin, 820, y)
        jack_block(pg, P[jack], 1340, y - 10, "OUT")
    pg.text(40, Y(1100), "Net ports with the same name connect across the pages; GND is one net. The Mega's 5V pins "
                         "are fed by U7 (page 6), bypassing its own regulator: flash it with the rack off.", 9)
    return pg


def input_stage(pg, P, tip, pin, x0, y):
    """tip port -> 22k -> node: BAT85 up to +5V and down to GND, 100k and 1n to GND -> the Mega's pin."""
    i = 0 if pin == "CLOCK" else 1
    r_s, r_pd, cap = P[f"R{101 + 2 * i}"], P[f"R{102 + 2 * i}"], P[f"C{101 + i}"]
    d_up, d_dn = P[f"D{101 + 2 * i}"], P[f"D{102 + 2 * i}"]
    a = hpart(pg, r_s, x0 + 20, y)
    pg.stub_port(a["1"], tip, "IN", "left")
    n1, n2, n3, end = (x0 + 110, y), (x0 + 180, y), (x0 + 250, y), (x0 + 310, y)
    pg.wire([a["2"], n1], pin)
    pg.wire([n1, n2], pin)
    pg.wire([n2, n3], pin)
    pg.wire([n3, end], pin)
    pg.port(*end, pin, "OUT", "right")
    up = vpart(pg, d_up, n1[0], y - 40, top_pin="1")       # cathode up on +5V, anode on the node
    assert up["2"] == n1
    pg.rail(up["1"], "+5V", "left", 10)
    dn = vpart(pg, d_dn, n1[0], y, top_pin="1")            # cathode on the node, anode down on GND
    pg.stub_gnd(dn["2"])
    rp = vpart(pg, r_pd, n2[0], y)
    pg.stub_gnd(rp["2"])
    cp = vpart(pg, cap, n3[0], y)
    pg.stub_gnd(cp["2"])


def row_page(pr, P, row, number):
    pg = MPage(pr, f"Row {row}: step pots and buttons", number)
    first = 1 if row == "A" else 9
    pg.text(40, Y(40), f"Row {row}: eight B10k step pots (CCW to +5V, CW to GND: the sketch plays 1 - reading) "
                       f"into the Mega's ADC, eight Thonk LED buttons", 12)
    for k in range(8):
        pot_block(pg, P[f"RV{first + k}"], 110 + k * 195, Y(250))
    pg.text(40, Y(390), "Buttons: a contact to +5V and one to the Mega's pin (pulled down in the network below: "
                        "pressed reads HIGH); the LED from +5V through the network's 1k into the Mega's pin "
                        "(LED_ON is LOW)", 11)
    for k in range(8):
        button_block(pg, P[f"SW{first + k}"], 190 + (k % 4) * 390, Y(500 + (k // 4) * 170))
    pd, led = ("RN1", "RN3") if row == "A" else ("RN2", "RN4")
    pg.text(40, Y(810), f"{pd}: the buttons' 10k pull-downs; {led}: the LEDs' 1k (about 3 mA red, 2 mA green). "
                        "Bussed SIP-9, pin 1 common.", 11)
    network_block(pg, P[pd], 300, Y(930))
    network_block(pg, P[led], 800, Y(930))
    return pg


def controls_page(pr, P):
    pg = MPage(pr, "Controls, ADC and DACs", 4)
    pg.text(40, Y(40), "ROWS, DIRECTION, BUTTONS (CW to +5V: their first position is fully CCW) and DUTY (CW to GND, "
                       "the sketch inverts it) into the ADS1115; SHIFT to GND on D19's pull-up", 12)
    for k, ref in enumerate(("RV17", "RV18", "RV19", "RV20")):
        pot_block(pg, P[ref], 110 + k * 210, Y(250))
    button_block(pg, P["SW17"], 1000, Y(250))
    pg.text(930, Y(320), "LED pins 5 / 6 open", 8)
    pg.text(40, Y(430), "ADS1115 at 0x48 (ADDR to GND), ±6.144 V range: 5 V reads about 26700. ALRT open.", 11)
    breakout_block(pg, P["U2"], "ADS", 300, Y(560))
    pg.text(560, Y(430), "Two MCP4725 (A0 chip): VCC from VDAC, which is their reference. A0 high = 0x61 = CV A, "
                         "A0 low = 0x60 = CV B", 11)
    for i, ref in enumerate(("U3", "U4")):
        breakout_block(pg, P[ref], "MCP", 720, Y(540 + 170 * i), P[ref].label)
    pg.text(1050, Y(430), "VDAC: LM4040-5.0 from +12V through 820R (7.2-8.8 mA)", 11)
    vdac_block(pg, P, 1180, Y(500))
    pg.text(40, Y(1100), "ADC inputs read 0..5 V: the knobs sit across the +5V rail, the same rail as the "
                         "ADS1115's VDD.", 9)
    return pg


def vdac_block(pg, P, x, top):
    """R903 from +12V down to VDAC; the LM4040's cathode on VDAC, pins 3 and 1 to GND; C905 beside it."""
    r = vpart(pg, P["R903"], x, top + 20)
    pg.rail(r["1"], "+12V", "left", 10)
    n = (x, top + 80)
    pg.wire([r["2"], n], "VDAC")
    ref = pg.place("U6", "LM4040", x, n[1] + 50, 270, des=(12, 4, "LEFT_BOTTOM"), value_at=(12, 14, "LEFT_BOTTOM"))
    pg.wire([n, ref["2"]], "VDAC")
    pg.stub_gnd(ref["3"])
    pg.stub_gnd(ref["1"], "left", 15)
    c = vpart(pg, P["C905"], x + 110, n[1], top_pin="2")
    pg.wire([n, (x + 110, n[1])], "VDAC")
    pg.stub_gnd(c["1"])
    pg.wire([(x + 110, n[1]), (x + 160, n[1])], "VDAC")
    pg.port(x + 160, n[1], "VDAC", "OUT", "right")


def cv_stage(pg, P, ch, sec, ox, oy):
    """DAC -> in+; x2 with the feedback from the jack side of the 1k; 100p from the output to in-."""
    amp = opamp(pg, sec, ox, oy)
    out, inm, inp = SECTION[sec]
    r = 201 if ch == "A" else 209
    rg, rf, rs, cf = P[f"R{r}"], P[f"R{r + 1}"], P[f"R{r + 2}"], P[f"C{201 if ch == 'A' else 202}"]
    n, o, jack = f"CV_{ch}_N", f"CV_{ch}_O", f"CV_{ch}"
    pg.wire([(ox - 100, oy + 10), amp[inp]], f"DAC_{ch}")
    pg.port(ox - 100, oy + 10, f"DAC_{ch}", "IN", "left")
    k = (ox + 60, oy)
    pg.wire([amp[out], k], o)
    a_rs = hpart(pg, rs, ox + 80, oy)
    pg.wire([k, a_rs["1"]], o)
    m = (ox + 160, oy)
    pg.wire([a_rs["2"], m], jack)
    pg.wire([m, (ox + 200, oy)], jack)
    pg.port(ox + 200, oy, jack, "OUT", "right")
    a_cf = hpart(pg, cf, ox - 20, oy - 70, left_pin="2")
    pg.wire([k, (ox + 60, oy - 70), a_cf["1"]], o)
    j1, j2 = (ox - 60, oy - 70), (ox - 60, oy - 120)
    pg.wire([amp[inm], (ox - 60, oy - 10), j1], n)
    pg.wire([j1, a_cf["2"]], n)
    pg.wire([j1, j2], n)
    a_rf = hpart(pg, rf, ox + 40, oy - 120, left_pin="2")
    pg.wire([j2, a_rf["2"]], n)
    pg.wire([m, (ox + 160, oy - 120), a_rf["1"]], jack)
    a_rg = hpart(pg, rg, ox - 140, oy - 120, left_pin="2")
    pg.wire([a_rg["1"], j2], n)
    pg.stub_gnd(a_rg["2"], "down", 10)
    pg.text(ox - 140, oy - 165, f"CV {ch}: x2 from MCP4725 {'0x61' if ch == 'A' else '0x60'}; the loop closes at "
                                f"the jack, so the 1k drops nothing into a VCO's input", 9)


def gate_stage(pg, P, ch, sec, ox, oy):
    """The Mega's gate pin (100k to GND) -> 10k -> in+; x2 -> 1k -> GATE."""
    r = 201 if ch == "A" else 209
    pd, rin, rg, rf, rs = (P[f"R{r + i}"] for i in (3, 4, 5, 6, 7))
    pin, plus, o = f"GATE_{ch}_PIN", f"GATE_{ch}_P", f"GATE_{ch}_O"
    k = noninv(pg, P, sec, ox, oy, rf.ref, rg.ref)
    a_in = hpart(pg, rin, ox - 120, oy + 10)
    pg.wire([a_in["2"], (ox - 40, oy + 10)], plus)
    p0 = (ox - 160, oy + 10)
    pg.wire([p0, a_in["1"]], pin)
    pg.wire([(ox - 200, oy + 10), p0], pin)
    pg.port(ox - 200, oy + 10, pin, "IN", "left")
    a_pd = vpart(pg, pd, p0[0], p0[1])
    pg.stub_gnd(a_pd["2"])
    a_rs = hpart(pg, rs, k[0] + 20, k[1])
    pg.wire([k, a_rs["1"]], o)
    pg.stub_port(a_rs["2"], f"GATE_{ch}", "OUT", "right")
    pg.text(ox - 140, oy - 105, f"GATE {ch}: x2 of the Mega's {'D17' if ch == 'A' else 'D15'}, about 9.6 V; 100k "
                                "holds it low while the Mega boots", 9)


def outputs_page(pr, P):
    pg = MPage(pr, "Outputs", 5)
    pg.text(40, Y(40), "U5 TL074 on +-12 V: CV A (A), GATE A (B), CV B (C), GATE B (D); 1k out to each jack", 12)
    cv_stage(pg, P, "A", "A", 360, Y(270))
    gate_stage(pg, P, "A", "B", 360, Y(470))
    cv_stage(pg, P, "B", "C", 360, Y(770))
    gate_stage(pg, P, "B", "D", 360, Y(970))
    pg.text(960, Y(110), "Outputs (panel)", 11)
    for i, ref in enumerate(("J3", "J4", "J5", "J6")):
        jack_block(pg, P[ref], 1000, Y(200 + 160 * i), "IN")
    pg.text(1300, Y(110), "U5 decoupling, beside its pins", 11)
    decoupling_pair(pg, P, "C203", "C204", 1380, Y(180))
    pg.text(40, Y(1120), "R201 / R202 and R209 / R210 1 % metal film (all are LR1F 1 %); C201 / C202 C0G.", 9)
    return pg


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


def power_block(pg, P, x0, t0):
    """2 x 5 header (red stripe = pin 1 = -12 V), a 1N5819 per rail (the -12 V cathode on the header),
    10R and 47 uF (Envy's); P12_D, between the +12 V diode and its 10R, also feeds the 5 V switcher."""
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J7", "HDR10", xh, yh, des=(-30, -40, "LEFT_BOTTOM"), value_at=(-30, 45, "LEFT_BOTTOM"))
    for side, pins, sgn in (("left", ("3", "5", "7"), -1), ("right", ("4", "6", "8"), 1)):
        bx = xh + sgn * 45
        pts = []
        for n in pins:
            p = h[n]
            pg.wire([p, (bx, p[1])], "GND")
            pts.append((bx, p[1]))
        for a, b in zip(pts, pts[1:]):
            pg.wire([a, b], "GND")
        mid = pts[1]
        pg.wire([mid, (bx + sgn * 15, mid[1])], "GND")
        pg.gnd(bx + sgn * 15, mid[1], 90 if sgn > 0 else 270)
    pg.stub_port(h["1"], "N12_IN", "OUT", "left", 30)
    pg.stub_port(h["2"], "N12_IN", "OUT", "right", 30)
    pg.stub_port(h["9"], "P12_IN", "OUT", "left", 30)
    pg.stub_port(h["10"], "P12_IN", "OUT", "right", 30)
    xa = x0 + 330
    for k, (port, d, r, c, rail) in enumerate((("P12_IN", "D901", "R901", "C901", "+12V"),
                                               ("N12_IN", "D902", "R902", "C902", "-12V"))):
        y = Y(t0 + 10 + 150 * k)
        plus = rail == "+12V"
        dp = hpart(pg, P[d], xa, y, left_pin="2" if plus else "1")
        pg.wire([(xa - 20, y), dp["2" if plus else "1"]], port)
        pg.port(xa - 20, y, port, "IN", "left")
        mid = "P12_D" if plus else "N12_D"
        jd = (xa + 60, y)
        pg.wire([dp["1" if plus else "2"], jd], mid)
        rp = hpart(pg, P[r], xa + 80, y)
        pg.wire([jd, rp["1"]], mid)
        if plus:                                   # the switcher's feed, ahead of the 10R
            pg.wire([jd, (jd[0], y + 50), (jd[0] + 20, y + 50)], mid)
            pg.port(jd[0] + 20, y + 50, mid, "OUT", "right")
        jn = (xa + 150, y)
        pg.wire([rp["2"], jn], rail)
        pg.wire([jn, (xa + 190, y)], rail)
        pg.port(xa + 190, y, rail, "OUT", "right")
        cp = vpart(pg, P[c], jn[0], y + 20, top_pin="2" if plus else "1")
        pg.wire([jn, cp["2" if plus else "1"]], rail)
        pg.stub_gnd(cp["1" if plus else "2"], "down", 10)


def switcher_block(pg, P, x, y):
    """P12_D -> U7 R-78E -> +5V, 10 uF on each side."""
    u = pg.place("U7", "R78E", x, y, des=(-30, -32, "LEFT_BOTTOM"), value_at=(-30, -20, "LEFT_BOTTOM"))
    pg.stub_gnd(u["2"])
    ji, jo = (x - 90, y), (x + 90, y)
    pg.wire([u["1"], ji], "P12_D")
    pg.wire([ji, (x - 140, y)], "P12_D")
    pg.port(x - 140, y, "P12_D", "IN", "left")
    ci = vpart(pg, P["C903"], ji[0], y, top_pin="2")
    pg.stub_gnd(ci["1"])
    pg.wire([u["3"], jo], "+5V")
    pg.wire([jo, (x + 140, y)], "+5V")
    pg.port(x + 140, y, "+5V", "OUT", "right")
    co = vpart(pg, P["C904"], jo[0], y, top_pin="2")
    pg.stub_gnd(co["1"])


def power_page(pr, P):
    pg = MPage(pr, "Power", 6)
    pg.text(40, Y(40), "Power: 10-pin Eurorack header (red stripe = pin 1 = -12 V), a 1N5819 per rail: +12 V anode on "
                       "the header, -12 V cathode on the header", 12)
    power_block(pg, P, 80, 120)
    pg.text(860, Y(110), "+5V for the Mega, the pots, buttons, LEDs and the ADS1115: about 100 mA, about 56 mA "
                         "from +12 V", 11)
    switcher_block(pg, P, 1100, Y(200))
    pg.text(40, Y(1100), "U7's input sits ahead of R901, so its current pulses stay out of the TL074's and the "
                         "LM4040's +12V. +12 V total about 75 mA, -12 V about 10 mA.", 9)
    return pg


# ------------------------------------------------------------------ checks
def page_check(pg, parts):
    drawn = {(c["ref"], num) for c in pg.comps if c["ref"] for num in c["pins"]}
    sub = []
    for p in parts:
        nets = {pid: n for pid, n in p.nets.items() if (p.ref, pin_map(p, pid)) in drawn}
        if nets:
            sub.append(circuit.Part(p.ref, p.kind, p.value, nets))
    return check(pg, sub, pin_map)


def coverage(pages, parts):
    seen = collections.Counter((c["ref"], num) for pg in pages for c in pg.comps if c["ref"] for num in c["pins"])
    placed = {c["ref"] for pg in pages for c in pg.comps if c["ref"]}
    problems = [f"{p.ref} not drawn" for p in parts if p.ref not in placed]
    for p in parts:
        for pid in p.nets:
            if seen[(p.ref, pin_map(p, pid))] != 1:
                problems.append(f"{p.ref}.{pid} drawn {seen[(p.ref, pin_map(p, pid))]} times")
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
    footprint and a net with a NET record (else EasyEDA drops the net silently). Side FXy's."""
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


def pcb_parts(parts):
    """The netlist for the PCB: the breakouts' pins by their pad numbers, as in their footprints."""
    out = []
    for p in parts:
        if p.kind in circuit.BREAKOUT_PINS:
            p = circuit.Part(p.ref, p.kind, p.value, {pin_map(p, pid): n for pid, n in p.nets.items()}, p.label)
        out.append(p)
    return out


def main():
    pr = MProject()
    parts = circuit.all_parts()
    P = {p.ref: p for p in parts}
    pages = [mega_page(pr, P), row_page(pr, P, "A", 2), row_page(pr, P, "B", 3), controls_page(pr, P),
             outputs_page(pr, P), power_page(pr, P)]
    bad = coverage(pages, parts)
    for pg in pages:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in pages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    board = pcb.one_board(pr, pcb_parts(parts), part_info(pages), circuit)
    pcb_bad = board.check() + pcb.placement_check(board, circuit) + pcb.front_housing_check(board)
    for b in pcb_bad:
        print("PCB:", b)
    panel_page = MPage(pr, "Panel", 1)
    panel_page.page_count = "1"
    panel_page.text(70, Y(60), "Eight 26HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the "
                               "bare-copper output block are in the PCB document; the art is "
                               "hardware/panel/eight-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([(TITLE, pages, board), (f"{TITLE} Panel", [panel_page], board_panel)], OUT, pcb.load_template(ee))
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in pages:
        render(pr, pg, PREVIEW.format(pg.title.split(",")[0].split(":")[0].lower().replace(" ", "-")))
    board.render(PREVIEW.format("pcb"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(pages)} pages, {len(bad)} schematic problems; "
          f"{len(board.placed)} parts placed ({board.improve_rounds} improve rounds), {len(pcb_bad)} PCB "
          f"problems; {len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
