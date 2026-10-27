"""Marblesy schematic as an EasyEDA Pro project (.epro2).

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) and the
MorrisSynth library parts cached there: TL074ACN, the WQP518MA jack, PTV09A
pots, LR1F resistors, FG28 / SR305 capacitors, net ports, ground flags and
the sheet frame. Everything else is drawn here in the same style, with real
pin numbers, and gets a generated through-hole footprint:

  Daisy Seed on seed_power_opamps   56 pads, 2.54 mm pitch, rows 15.24 mm apart,
                                    positions taken from Rob Heel's PCB
  MCP4922 (DIP-14), 74HC595 / 74HC165 / 74HC4051 (DIP-16), 2N3904 and
  LM4040 (TO-92 in line), 3 mm LEDs (2 and 3 leads), the 5 x 5 mm tactile
  switch (Thonk "Highly Tactile"), 1xN pin headers.

Three A3 pages: Main board 1 (Seed, CV inputs, clock inputs, bias and
reference), Main board 2 (DACs, output stages, gate outputs, headers),
Faceplate. Every connection that leaves a block is a net port; nets that
cross between the boards are the header pins.

Run from marbles/hardware/tools:  python easyeda_export.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAITSY = os.path.normpath(os.path.join(HERE, "..", "..", "..", "plaitsy", "hardware", "tools"))
sys.path.insert(0, PLAITSY)
import easyeda_export as ee                      # noqa: E402  (the Plaitsy exporter)

ee.LIBFILE = os.path.join(PLAITSY, "..", "easyeda", "morrissynth-parts.epru")
from easyeda_export import (Doc, Symbol, Page, Project, meta, attr_payload, Y, render, check,   # noqa: E402
                            new_uuid, DEV, SRC, W, H, H_TXT, V_TXT)

_spec = importlib.util.spec_from_file_location("marbles_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

NAME = "Marblesy"
OUT = os.path.join(HERE, "..", "easyeda", "Marbles.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "marbles-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil

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
    """A through-hole footprint in mm; written as an EasyEDA Pro FOOTPRINT doc."""

    def __init__(self, title, designator="U?"):
        self.title, self.designator = title, designator
        self.pads, self.silk = [], []        # (num, x, y, hole, pad_w, pad_h, square), [(kind, data)]
        self.doc = Doc("FOOTPRINT")

    def pad(self, num, x, y, hole=1.0, size=1.7, square=False, h=None):
        self.pads.append((str(num), x, y, hole, size, h or size, square))

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
        for num, x, y, hole, pw, ph, square in self.pads:
            pad = {"padType": "RECT", "width": m(pw), "height": m(ph), "radius": 0} if square else \
                  {"padType": "ELLIPSE", "width": m(pw), "height": m(ph)}
            d.add("PAD", d.nid(), {"groupId": 0, "netName": "", "layerId": 12, "num": num, "centerX": m(x),
                                   "centerY": m(y), "padAngle": 0,
                                   "hole": {"holeType": "ROUND", "width": m(hole), "height": m(hole)},
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


def fp_to92():
    f = Footprint("TO-92-INLINE-P2.54", "Q?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.line(-2.6, -1.3, 2.6, -1.3)
    f.silk.append(("C", (0, 0, 2.6)))
    return f


def fp_led(leads):
    f = Footprint(f"LED-3MM-{leads}P", "D?")
    if leads == 3:   # 1.27 mm pitch, body centred on the middle lead (common cathode)
        for i in range(3):
            f.pad(i + 1, (i - 1) * 1.27, 0, 0.8, 1.1, square=(i == 0), h=1.7)
    else:
        f.pad(1, -1.27, 0, 0.8, 1.5, square=True)
        f.pad(2, 1.27, 0, 0.8, 1.5)
    f.circle(0, 0, 1.6)
    f.line(-1.6, 1.3, -1.6, -1.3)    # flat = cathode side marker
    return f


def fp_switch():
    """5 x 5 mm pin square, 12 mm round body: Thonk 'Highly Tactile' / C&K D6R."""
    f = Footprint("SW-TACT-5x5-D12", "SW?")
    for num, (x, y) in enumerate(((-2.5, 2.5), (2.5, 2.5), (2.5, -2.5), (-2.5, -2.5)), 1):
        f.pad(num, x, y, 1.1, 1.7, square=(num == 1))
    f.circle(0, 0, 6.0)
    f.circle(0, 0, 4.5)
    return f


def fp_seed_breakout():
    """Rob Heel's seed_power_opamps board, pads as measured in its PCB file.
    Origin at the centre of the Seed's pin field; pins 1 and 40 at +x (the
    USB end). y grows downwards on the EasyEDA canvas."""
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


def seed_symbol():
    left = [(0, "J5-1", "AIN1"), (1, "J5-2", "GND"), (2, "J5-3", "AIN2"), (3, "J5-4", "GND")]
    left += [(4 + k, str(k + 1), circuit.SEED[str(k + 1)][0]) for k in range(20)]
    left += [(24 + i, f"J1-{i + 1}", circuit.SEED[f"J1-{i + 1}"][0]) for i in range(4)]
    right = [(0, "J4-1", "AOUT1"), (1, "J4-2", "GND"), (2, "J4-3", "AOUT2"), (3, "J4-4", "GND")]
    right += [(4 + k, str(40 - k), circuit.SEED[str(40 - k)][0]) for k in range(20)]
    right += [(24 + i, f"J3-{i + 1}", circuit.SEED[f"J3-{i + 1}"][0]) for i in range(4)]
    s = ic_symbol("Daisy Seed on seed_power_opamps", "DaisySeedBreakout.2", left, right, w=80)
    s.text(-30, 120, "Daisy Seed", 10)
    s.text(-45, 133, "seed_power_opamps", 8)
    return s


def mcp4922_symbol():
    left = [(0, "1", "VDD"), (1, "3", "/CS"), (2, "4", "SCK"), (3, "5", "SDI"), (4, "8", "/LDAC"), (5, "9", "/SHDN"),
            (6, "12", "AVSS")]
    right = [(0, "14", "VOUTA"), (1, "13", "VREFA"), (3, "11", "VREFB"), (4, "10", "VOUTB")]
    return ic_symbol("MCP4922", "MCP4922.1", left, right)


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


def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.1", "H?", [NAME])
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


def lm4040_symbol():
    s = Symbol("LM4040-2.5", "LM4040.1", "D?", [NAME])
    s.poly([(-20, 0), (-6, 0)])
    s.poly([(6, -7), (-6, 0), (6, 7), (6, -7)], closed=True)
    s.poly([(-6, -7), (-6, 7)])
    s.poly([(-6, -7), (-9, -9)])
    s.poly([(-6, 7), (-3, 9)])
    s.poly([(6, 0), (20, 0)])
    s.text(-14, -8, "2.5V", 6)
    s.pin("1", "K", -20, 0, 0)     # cathode: the positive end
    s.pin("2", "A", 20, 0, 180)
    return s


def led_single_symbol():
    s = Symbol("LED 3mm green", "LED_G.1", "D?", [NAME])
    s.poly([(-20, 0), (-6, 0)])
    s.poly([(-6, -6), (6, 0), (-6, 6), (-6, -6)], closed=True, fill="#00A000")
    s.poly([(6, -6), (6, 6)])
    s.poly([(6, 0), (20, 0)])
    for x0 in (-1, 4):
        s.poly([(x0, -9), (x0 + 5, -14)])
        s.poly([(x0 + 5, -14), (x0 + 1, -13), (x0 + 4, -10), (x0 + 5, -14)], closed=True, fill="#00A000")
    s.pin("1", "A", -30, 0, 0)
    s.pin("2", "K", 30, 0, 180)
    return s


def button4_symbol():
    """Tactile switch with its four pins: 1 and 4 on one side, 2 and 3 on the other."""
    s = Symbol("Push button 4-pin", "PUSHBUTTON4.1", "SW?", [NAME])
    s.poly([(-20, 0), (-12, 0)])
    s.poly([(12, 0), (20, 0)])
    s.poly([(-12, 0), (-12, -3)])
    s.poly([(12, 0), (12, -3)])
    s.poly([(-15, -7), (15, -7)])
    s.poly([(0, -7), (0, -15)])
    s.poly([(-4, -15), (4, -15)])
    s.poly([(-20, 0), (-20, 10)])
    s.poly([(20, 0), (20, 10)])
    s.pin("1", "1", -30, 0, 0)
    s.pin("4", "4", -30, 10, 0)
    s.pin("2", "2", 30, 0, 180)
    s.pin("3", "3", 30, 10, 180)
    return s


# ------------------------------------------------------------------ project
R_NEW = {"470": ("LR1F470R", "470Ω"), "2k2": ("LR1F2K2", "2.2kΩ"), "15k": ("LR1F15K", "15kΩ"),
         "24k": ("LR1F24K", "24kΩ"), "27k": ("LR1F27K", "27kΩ"), "47k": ("LR1F47K", "47kΩ"),
         "100k": ("LR1F100K", "100kΩ")}
C_NEW = {"1n": ("FG28C0G1H102JNT00", "1nF")}


class MPage(Page):
    def frame(self):
        d, pr = self.doc, self.pr
        cid = d.nid()
        sym = pr.sym_of("FRAME")
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": pr.symgeo[sym]["parts"][0],
                                 "groupId": "", "x": 0, "y": 0, "rotation": 0, "isMirror": False, "attrs": {}})
        today = ee.time.strftime("%Y-%m-%d")
        vals = [("Symbol", sym), ("@Project Name", NAME), ("@Page Count", "3"), ("@Update Date", today),
                ("@Create Date", today), ("@Schematic Name", NAME), ("@Page No", str(self.number)),
                ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""), ("Version", "V0.1"),
                ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""), ("@Update Time", ""),
                ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"), ("X Region Count", "6"),
                ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""), ("Title Block Position", "3"),
                ("Title Block", "1"), ("@Board Name", NAME), ("Footprint", ""), ("Description", ""),
                ("Device", DEV["FRAME"])]
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


class MProject(Project):
    def _footprint(self, fp):
        lines = fp.build()
        self.new_docs.append(("FOOTPRINT", lines))
        return fp.doc.uuid

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
        d4148 = meta(self.lib[SRC["1N4148"]])["attributes"]
        a = dict(d4148)
        a.update({"Symbol": meta(self.lib[SRC["1N5819"]])["attributes"]["Symbol"], "Manufacturer Part": "BAT85",
                  "LCSC Part Name": "BAT85", "Supplier Part": "", "Manufacturer": "", "Datasheet": "",
                  "Description": "Schottky diode 30 V 200 mA, DO-35"})
        self._device("BAT85", "BAT85", a, ["Diodes", "Schottky Diodes"])
        dip16 = meta(self.lib[SRC["74HC595N"]])["attributes"]["Footprint"]
        dip14 = meta(self.lib[DEV["TL074"]])["attributes"]["Footprint"]
        fps = {"SEED": self._footprint(fp_seed_breakout()), "TO92": self._footprint(fp_to92()),
               "LED3": self._footprint(fp_led(3)), "LED2": self._footprint(fp_led(2)),
               "SW": self._footprint(fp_switch())}
        for n in (4, 6, 7, 8):
            fps[f"HDR{n}"] = self._footprint(fp_header(n))
        new = [
            ("SEED", seed_symbol(), "Daisy Seed + seed_power_opamps", "U?", fps["SEED"],
             "Daisy Seed plugged into Rob Heel's seed_power_opamps breakout; 2.54 mm socket strips on the main board"),
            ("MUX", ee.mux_symbol(), "74HC4051", "U?", dip16, "8-channel analog multiplexer, DIP-16"),
            ("HC595", hc595_symbol(), "74HC595", "U?", dip16, "8-bit shift register with output latch, DIP-16"),
            ("HC165", hc165_symbol(), "74HC165", "U?", dip16, "8-bit parallel-in shift register, DIP-16"),
            ("MCP4922", mcp4922_symbol(), "MCP4922", "U?", dip14, "Dual 12-bit SPI DAC, external reference, DIP-14"),
            ("NPN", npn_symbol(), "2N3904", "Q?", fps["TO92"], "NPN transistor, TO-92 (E B C)"),
            ("LM4040", lm4040_symbol(), "LM4040-2.5", "D?", fps["TO92"],
             "2.5 V shunt reference, TO-92: pad 1 = cathode (+), pad 2 = anode, pad 3 unused - check the datasheet of your package"),
            ("LED_RG", ee.led_symbol(), "LED 3mm bicolour R/G CC", "D?", fps["LED3"],
             "3 mm bicolour LED, red/green, common cathode on the middle lead, 1.27 mm pitch"),
            ("LED_G", led_single_symbol(), "LED 3mm green", "D?", fps["LED2"], "3 mm LED, 2.54 mm pitch"),
            ("SW", button4_symbol(), "Tactile switch 5x5", "SW?", fps["SW"],
             "Momentary tactile switch, 5 x 5 mm pins, 12 mm round body (Thonk Highly Tactile / C&K D6R)"),
        ]
        for n in (4, 6, 7, 8):
            new.append((f"HDR{n}", header_symbol(n), f"Pin header 1x{n}", "H?", fps[f"HDR{n}"],
                        f"Board-to-board header, 1x{n}, 2.54 mm"))
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
            self._device(key, title, attrs)

    def write(self, pages, path):
        board, sch = Doc("BOARD", new_uuid()[:16]), Doc("SCH")
        used = {u for u, m in self.devices.values()}
        refs = {m["attributes"].get(k) for u, m in self.devices.values() for k in ("Symbol", "Footprint")}
        keep = {"FOOTPRINT": refs, "SYMBOL": refs, "DEVICE": used}
        lines = []
        for typ in ("FOOTPRINT", "SYMBOL", "DEVICE"):
            for u, d in self.lib.items():
                if d["docType"] == typ and u in keep[typ]:
                    lines += d["lines"]
            lines += [l for t, ls in self.new_docs if t == typ for l in ls]
        lines += board.lines({"title": NAME, "zIndex": 1})
        lines += sch.lines({"title": f"{NAME} Schema", "board": board.uuid, "zIndex": None})
        for pg in pages:
            lines += pg.lines(sch.uuid)
        lines += Doc("CONFIG", "CONFIG").lines({"defaultSheet": ""})
        lines += [l for u, d in self.lib.items() if d["docType"] == "BLOB" for l in d["lines"]]
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Mutable Instruments Marbles clone: Daisy Seed on the seed_power_opamps "
                                  "breakout, TL074 CV inputs, MCP4922 DACs, 74HC4051 pot mux, 74HC595/165 UI.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


def r_dev(value):
    return {"1k": "R1k", "10k": "R10k"}.get(value, "R" + value)


def c_dev(value):
    return {"100n": "C100n", "1u": "C1u"}.get(value, "C" + value)


# ------------------------------------------------------------------ pages
def seed_block(pg, P, x, y):
    u2 = pg.place("U2", "SEED", x, y, des=(-80, -154, "LEFT_BOTTOM"), name=False)
    rows_left = {pin for pin in circuit.SEED if pin.startswith("J5") or pin.startswith("J1")}
    rows_left |= {str(k) for k in range(1, 21)}
    for pin, (name, net) in circuit.SEED.items():
        if not net:
            continue
        side = "left" if pin in rows_left else "right"
        if net == "GND":
            pg.stub_gnd(u2[pin], side, 15)
            continue
        if net in ("+12V", "-12V", "3V3A", "3V3D"):
            kind = "IN"
        elif net.startswith("ADC_") or net in ("MUX_OUT", "T_CLK", "X_CLK", "SPI_MISO"):
            kind = "IN"
        else:
            kind = "OUT"
        pg.stub_port(u2[pin], net, kind, side)
    return u2


def inverting_stage(pg, P, ox, oy, amp_ref, sec, rin, rfb, cfb, rs, nin, nout, in_net, out_net, plus_net,
                    supply=False, mid=False):
    """Plaits-style inverting op-amp stage with Rf || Cf, series resistor to the output port."""
    amp = pg.place(amp_ref, "TL074", ox, oy, unit=sec, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
    a_in = pg.place(rin.ref, r_dev(rin.value), ox - 90, oy - 10, des=H_TXT[0], value_at=H_TXT[1])
    a_rf = pg.place(rfb.ref, r_dev(rfb.value), ox, oy - 60, des=H_TXT[0], value_at=H_TXT[1])
    a_rs = pg.place(rs.ref, r_dev(rs.value), ox + 100, oy, des=H_TXT[0], value_at=H_TXT[1])
    out, inm, inp = circuit.SECTION[sec]
    jx, jy, kx = ox - 55, oy - 10, ox + 60
    pg.wire([a_in["2"], (jx, jy)], nin)
    pg.wire([(jx, jy), amp[inm]], nin)
    if mid:    # a second input resistor joins the summing node at oy - 40
        pg.wire([(jx, jy), (jx, oy - 40)], nin)
        pg.wire([(jx, oy - 40), (jx, oy - 60)], nin)
    else:
        pg.wire([(jx, jy), (jx, oy - 60)], nin)
    pg.wire([(jx, oy - 60), a_rf["1"]], nin)
    pg.wire([amp[out], (kx, oy)], nout)
    pg.wire([(kx, oy), a_rs["1"]], nout)
    pg.wire([(kx, oy), (kx, oy - 60)], nout)
    pg.wire([(kx, oy - 60), a_rf["2"]], nout)
    if cfb is not None:
        a_cf = pg.place(cfb.ref, c_dev(cfb.value), ox, oy - 90, des=(-20, -10, "LEFT_BOTTOM"),
                        value_at=(2, -10, "LEFT_BOTTOM"))
        pg.wire([(jx, oy - 60), (jx, oy - 90), a_cf["1"]], nin)
        pg.wire([(kx, oy - 60), (kx, oy - 90), a_cf["2"]], nout)
    pg.stub_port(a_in["1"], in_net, "IN", "left")
    if plus_net == "GND":
        pg.stub_gnd(amp[inp], "left", 15)
    else:
        pg.stub_port(amp[inp], plus_net, "IN", "left", length=30)
    pg.stub_port(a_rs["2"], out_net, "OUT", "right")
    if supply:
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))
    return amp


def decoupling_pair(pg, P, cp, cn, x, top):
    a = pg.place(cp, c_dev(P[cp].value), x, top + 20, 270, *V_TXT)
    b = pg.place(cn, c_dev(P[cn].value), x, top + 80, 270, *V_TXT)
    node = (x, top + 50)
    pg.wire([a["2"], node], "GND")
    pg.wire([node, b["1"]], "GND")
    pg.wire([node, (x - 15, top + 50)], "GND")
    pg.gnd(x - 15, top + 50, 270)
    pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "+12V")
    pg.port(x - 20, top - 10, "+12V", "IN", "left")
    pg.wire([b["2"], (x, top + 120), (x - 20, top + 120)], "-12V")
    pg.port(x - 20, top + 120, "-12V", "IN", "left")


def main_page_1(pr, parts):
    P = {p.ref: p for p in parts}
    pg = MPage(pr, "Main board 1: Seed, CV inputs, clocks", 1)
    pg.text(150, Y(50), "Daisy Seed on the seed_power_opamps breakout (2.54 mm sockets on this board)", 12)
    seed_block(pg, P, 260, Y(260))

    pg.text(560, Y(32), "CV inputs: TL074 inverting stages, gain -0.27 (+-5 V -> 0.33..3.03 V), biased from 3V3A, 1k into the ADC", 12)
    for i, (name, label, u, sec) in enumerate(circuit.CV_CHANNELS):
        col, row = divmod(i, 4)
        ox, oy = 730 + col * 490, Y(155 + row * 170)
        rin, rfb, rs = (P[f"R{21 + 3 * i + k}"] for k in range(3))
        inverting_stage(pg, P, ox, oy, u, sec, rin, rfb, P[f"C{21 + i}"], rs, f"IN_{name}", f"OA_{name}",
                        f"CV_{name}", f"ADC_{name}", "BIAS", supply=(sec == 1))
        pg.text(ox - 110, oy - 110, label, 9)

    # -2.5 V reference inverter on U4 section 4
    ox, oy = 730 + 490, Y(155 + 3 * 170)
    pg.text(ox - 110, oy - 110, "-2.5 V for the DAC output stages", 9)
    amp = pg.place("U4", "TL074", ox, oy, unit=4, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
    r42 = pg.place("R42", r_dev("10k"), ox - 90, oy - 10, des=H_TXT[0], value_at=H_TXT[1])
    r43 = pg.place("R43", r_dev("10k"), ox, oy - 60, des=H_TXT[0], value_at=H_TXT[1])
    jx, kx = ox - 55, ox + 60
    pg.wire([r42["2"], (jx, oy - 10)], "IN_NEGREF")
    pg.wire([(jx, oy - 10), amp["13"]], "IN_NEGREF")
    pg.wire([(jx, oy - 10), (jx, oy - 60)], "IN_NEGREF")
    pg.wire([(jx, oy - 60), r43["1"]], "IN_NEGREF")
    pg.wire([amp["14"], (kx, oy)], "NEG_REF")
    pg.wire([(kx, oy), (kx, oy - 60)], "NEG_REF")
    pg.wire([(kx, oy - 60), r43["2"]], "NEG_REF")
    pg.wire([(kx, oy), (kx + 20, oy)], "NEG_REF")
    pg.port(kx + 20, oy, "NEG_REF", "OUT", "right")
    pg.stub_port(r42["1"], "VREF", "IN", "left")
    pg.stub_gnd(amp["12"], "left", 15)

    # clock inputs
    pg.text(70, Y(600), "Clock inputs: 100k into a 2N3904 inverter, 10k pull-up to 3V3D (the Seed reads them inverted)", 12)
    for k, name in enumerate(("T", "X")):
        x0, y = 110, Y(680 + k * 150)
        r_in, r_pu = P[f"R{50 + 2 * k}"], P[f"R{51 + 2 * k}"]
        a = pg.place(r_in.ref, r_dev(r_in.value), x0 + 40, y, des=H_TXT[0], value_at=H_TXT[1])
        q = pg.place(f"Q{k + 1}", "NPN", x0 + 100, y, des=(14, -8, "LEFT_BOTTOM"), value_at=(14, 2, "LEFT_BOTTOM"))
        d = pg.place(f"D{22 + k}", "BAT85", x0 + 80, y + 50, 270, *V_TXT)
        pu = pg.place(r_pu.ref, r_dev(r_pu.value), x0 + 110, y - 60, 270, *V_TXT)
        b, c, e = (x0 + 80, y), (x0 + 110, y - 30), q["1"]
        pg.stub_port(a["1"], f"{name}_CLK_IN", "IN", "left")
        pg.wire([a["2"], b], f"B_{name}_CLK")
        pg.wire([b, q["2"]], f"B_{name}_CLK")
        pg.wire([b, d["1"]], f"B_{name}_CLK")          # cathode up to the base
        pg.stub_gnd(d["2"])
        pg.stub_gnd(e)
        pg.wire([q["3"], c], f"{name}_CLK")
        pg.wire([pu["2"], c], f"{name}_CLK")
        pg.wire([c, (x0 + 150, c[1])], f"{name}_CLK")
        pg.port(x0 + 150, c[1], f"{name}_CLK", "OUT", "right")
        pg.wire([pu["1"], (x0 + 110, y - 90), (x0 + 90, y - 90)], "3V3D")
        pg.port(x0 + 90, y - 90, "3V3D", "IN", "left")
        pg.text(x0 - 40, y + 40, f"{name} CLOCK", 9)

    # bias for the input stages
    pg.text(530, Y(760), "Bias (1.32 V) and 2.5 V reference", 12)
    x, top = 620, Y(810)
    a = pg.place("R45", r_dev("15k"), x, top + 20, 270, *V_TXT)
    b = pg.place("R46", r_dev("10k"), x, top + 80, 270, *V_TXT)
    c = pg.place("C29", c_dev("1u"), x + 40, top + 80, 270, des=(8, -2, "LEFT_BOTTOM"), value_at=(8, 8, "LEFT_BOTTOM"))
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
    # LM4040 reference
    x = 800
    a = pg.place("R47", r_dev("2k2"), x, top + 20, 270, *V_TXT)
    d = pg.place("D21", "LM4040", x, top + 80, 270, *V_TXT)
    c = pg.place("C30", c_dev("100n"), x + 40, top + 80, 270, des=(8, -2, "LEFT_BOTTOM"), value_at=(8, 8, "LEFT_BOTTOM"))
    node = (x, top + 50)
    pg.wire([a["2"], node], "VREF")
    pg.wire([node, d["1"]], "VREF")
    pg.wire([node, (x + 40, top + 50), c["1"]], "VREF")
    pg.wire([node, (x - 20, top + 50)], "VREF")
    pg.port(x - 20, top + 50, "VREF", "OUT", "left")
    pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "3V3A")
    pg.port(x - 20, top - 10, "3V3A", "IN", "left")
    pg.stub_gnd(d["2"])
    pg.stub_gnd(c["2"])

    pg.text(40, Y(1090), "Net ports with the same name connect. The *_IN clock nets, CV_* nets, PROBE, MUX_*, SPI_*, "
                        "LED_LATCH and BTN_LOAD are the header pins to the faceplate (page 2, H1..H5).", 10)
    pg.text(40, Y(1110), "GND here is one net: AGND (Seed pin 20), DGND (pin 40) and the breakout's GND pins. "
                        "The breakout ties them too.", 10)
    return pg


def main_page_2(pr, parts):
    P = {p.ref: p for p in parts}
    pg = MPage(pr, "Main board 2: DACs, outputs, gates", 2)

    pg.text(70, Y(50), "Two MCP4922 (12-bit, 3V3A supply, 2.5 V reference), LDAC shared for a simultaneous update", 12)
    for k, (u, cs) in enumerate((("U7", "DAC_CS1"), ("U8", "DAC_CS2"))):
        x, y = 260, Y(190 + k * 240)
        dac = pg.place(u, "MCP4922", x, y, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
        nets = P[u].nets
        for num in ("1", "3", "4", "5", "8", "9"):
            pg.stub_port(dac[num], nets[num], "IN", "left")
        pg.stub_gnd(dac["12"], "left", 15)
        for num in ("14", "10"):
            pg.stub_port(dac[num], nets[num], "OUT", "right")
        for num in ("13", "11"):
            pg.stub_port(dac[num], "VREF", "IN", "right")
        c = pg.place(f"C{39 + k}", c_dev("100n"), x + 40, y + 100, 270, *V_TXT)
        pg.wire([c["1"], (x + 40, y + 65), (x + 20, y + 65)], "3V3A")
        pg.port(x + 20, y + 65, "3V3A", "IN", "left")
        pg.stub_gnd(c["2"])

    pg.text(560, Y(32), "Output stages: Vout = -(100k/24k) Vdac + (100k/47k) 2.5 V = +5.3 V (code 0) .. -5.1 V (code 4095), 1k out", 12)
    for i, (name, dac, ch, u, sec) in enumerate(circuit.DAC_OUTS):
        ox, oy = 800, Y(155 + i * 170)
        ra, rb, rf, rs = (P[f"R{70 + 4 * i + k}"] for k in range(4))
        amp = inverting_stage(pg, P, ox, oy, u, sec, ra, rf, None, rs, f"IN_{name}", f"OA_{name}", f"DAC_{name}",
                              name, "GND", supply=(sec == 1), mid=True)
        r_b = pg.place(rb.ref, r_dev(rb.value), ox - 90, oy - 40, des=H_TXT[0], value_at=H_TXT[1])
        jx = ox - 55
        pg.wire([r_b["2"], (jx, oy - 40)], f"IN_{name}")
        pg.stub_port(r_b["1"], "NEG_REF", "IN", "left")
        pg.text(ox - 110, oy - 75, name, 9)

    pg.text(1130, Y(32), "Gate outputs: x2.5 from the GPIO = 0 / 8.25 V, 1k out", 12)
    for i, (name, u, sec) in enumerate(circuit.GATES):
        ox, oy = 1280, Y(155 + i * 170)
        rg, rf, rs = (P[f"R{60 + 3 * i + k}"] for k in range(3))
        out, inm, inp = circuit.SECTION[sec]
        amp = pg.place(u, "TL074", ox, oy, unit=sec, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
        a_rg = pg.place(rg.ref, r_dev(rg.value), ox - 95, oy - 10, des=H_TXT[0], value_at=H_TXT[1])
        a_rf = pg.place(rf.ref, r_dev(rf.value), ox, oy - 60, des=H_TXT[0], value_at=H_TXT[1])
        a_rs = pg.place(rs.ref, r_dev(rs.value), ox + 100, oy, des=H_TXT[0], value_at=H_TXT[1])
        jx, kx = ox - 55, ox + 60
        pg.wire([a_rg["2"], (jx, oy - 10)], f"IN_{name}")
        pg.wire([(jx, oy - 10), amp[inm]], f"IN_{name}")
        pg.wire([(jx, oy - 10), (jx, oy - 60)], f"IN_{name}")
        pg.wire([(jx, oy - 60), a_rf["1"]], f"IN_{name}")
        pg.stub_gnd(a_rg["1"], "left", 15)
        pg.wire([amp[out], (kx, oy)], f"OA_{name}")
        pg.wire([(kx, oy), a_rs["1"]], f"OA_{name}")
        pg.wire([(kx, oy), (kx, oy - 60)], f"OA_{name}")
        pg.wire([(kx, oy - 60), a_rf["2"]], f"OA_{name}")
        pg.stub_port(amp[inp], f"GATE_{name}", "IN", "left", length=30)
        pg.stub_port(a_rs["2"], name, "OUT", "right")
        pg.text(ox - 110, oy - 75, name, 9)
        if sec == 1:
            vcc, vee = amp["4"], amp["11"]
            pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
            pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))
    # spare section of U6: grounded follower
    ox, oy = 1280, Y(155 + 3 * 170)
    amp = pg.place("U6", "TL074", ox, oy, unit=4, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
    pg.stub_gnd(amp["12"], "left", 15)
    pg.wire([amp["14"], (ox + 60, oy), (ox + 60, oy - 40), (ox - 55, oy - 40), (ox - 55, oy - 10), amp["13"]], "U6_SPARE")
    pg.text(ox - 110, oy - 75, "spare (follower)", 9)

    # headers to the faceplate
    pg.text(70, Y(740), "Board-to-board headers (female sockets on this board; pin 1 marked)", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        x, y = 160 + k * 220, Y(830)
        h = pg.place(ref, kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        nets = P[ref].nets
        for num, net in nets.items():
            if net == "GND":
                pg.stub_gnd(h[num], "left", 15)
            else:
                kind_ = "OUT" if net in ("T1", "T2", "T3", "X1", "X2", "X3", "Y", "PROBE", "MUX_S0", "MUX_S1", "MUX_S2",
                                         "SPI_SCK", "SPI_MOSI", "LED_LATCH", "BTN_LOAD", "3V3D", "3V3A") else "IN"
                pg.stub_port(h[num], net, kind_, "left")

    pg.text(1180, Y(740), "Supply decoupling U3..U6", 12)
    for k, (cp, cn) in enumerate((("C31", "C32"), ("C33", "C34"), ("C35", "C36"), ("C37", "C38"))):
        decoupling_pair(pg, P, cp, cn, 1270 + k * 100, Y(790))
    return pg


def faceplate_page(pr, parts):
    P = {p.ref: p for p in parts}
    pg = MPage(pr, "Faceplate", 3)
    probe_r = {p.nets["1"]: p for p in parts if p.kind == "R" and p.nets.get("2") == "PROBE_F"}

    pg.text(70, Y(45), "Jacks (Thonkiconn). Sleeves to GND_F; CV inputs have their switch lug grounded, the two clock inputs get the probe", 12)
    for i, (ref, label, tip, tn) in enumerate(circuit.JACKS):
        col, row = divmod(i, 8)
        jx, jy = 130 + col * 360, Y(125 + row * 95)
        j = pg.place(ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
        pg.text(jx - 25, jy + 30, label, 10)
        s = j["1"]
        pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND_F")
        pg.flag(s[0] + 20, s[1] - 20, 90, "GND_F")
        if tn == "GND_F":
            pg.stub_flag(j["2"], "GND_F", "right", 20)
        elif tn:
            r = probe_r[tn]
            rp = pg.place(r.ref, r_dev(r.value), j["2"][0] + 40, j["2"][1], des=H_TXT[0], value_at=H_TXT[1])
            pg.wire([j["2"], rp["1"]], tn)
            pg.stub_port(rp["2"], "PROBE_F", "IN", "right")
        x, y = j["3"]
        pg.wire([(x, y), (x + 120, y)], tip)
        pg.port(x + 120, y, tip, "OUT" if (tip.startswith("CV_") or tip.endswith("CLK_IN_F")) else "IN", "right")

    pg.text(820, Y(45), "Pots (B10k) into the 74HC4051; channel order = mux Y0..Y7", 12)
    for i, (ref, label, wiper, mpin, ch) in enumerate(circuit.POTS):
        col, row = divmod(i, 4)
        px, py = 900 + col * 220, Y(130 + row * 95)
        p = pg.place(ref, "POT", px, py, des=(8, -22, "LEFT_BOTTOM"), value_at=(8, -12, "LEFT_BOTTOM"))
        pg.text(px - 40, py + 36, f"{label} (Y{ch})", 10)
        pg.stub_port(p["3"], "3V3A_F", "IN", "left")
        pg.stub_flag(p["1"], "GND_F", "right", 15)
        pg.wire([p["4"], (p["4"][0] - 10, p["4"][1]), (p["4"][0] - 10, p["4"][1] + 15), (p["5"][0] + 10, p["5"][1] + 15),
                 (p["5"][0] + 10, p["5"][1]), p["5"]], "GND_F")
        pg.wire([(p["5"][0] + 10, p["5"][1] + 15), (p["5"][0] + 10, p["5"][1] + 25)], "GND_F")
        pg.flag(p["5"][0] + 10, p["5"][1] + 25, 0, "GND_F")
        w = p["2"]
        pg.wire([w, (w[0], w[1] - 15), (w[0] - 20, w[1] - 15)], wiper)
        pg.port(w[0] - 20, w[1] - 15, wiper, "OUT", "left")

    ux, uy = 1450, Y(250)
    mux = pg.place("U1", "MUX", ux, uy, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
    nets = P["U1"].nets
    for row, num, name in ee.MUX_LEFT:
        pg.stub_port(mux[num], nets[num], "IN", "left")
    gnd_pins = []
    for row, num, name in ee.MUX_RIGHT:
        net = nets[num]
        if net == "GND_F":
            gnd_pins.append(mux[num])
        else:
            pg.stub_port(mux[num], net, "OUT" if net == "MUX_OUT_F" else "IN", "right")
    bx = gnd_pins[0][0] + 15
    for gp in gnd_pins:
        pg.wire([gp, (bx, gp[1])], "GND_F")
    for a, b in zip(gnd_pins, gnd_pins[1:]):
        pg.wire([(bx, a[1]), (bx, b[1])], "GND_F")
    pg.wire([(bx, gnd_pins[-1][1]), (bx, gnd_pins[-1][1] + 10)], "GND_F")
    pg.flag(bx, gnd_pins[-1][1] + 10, 0, "GND_F")
    c8 = pg.place("C8", c_dev("100n"), 1600, Y(380), 270, *V_TXT)
    pg.wire([c8["1"], (1600, Y(350)), (1580, Y(350))], "3V3A_F")
    pg.port(1580, Y(350), "3V3A_F", "IN", "left")
    pg.stub_flag(c8["2"], "GND_F")
    pg.text(1535, Y(430), "C8 at U1 pin 16", 8)

    # shift registers
    pg.text(820, Y(495), "LEDs: two 74HC595 on the SPI bus, 470R per colour. Buttons: 74HC165, 10k pull-ups", 12)
    for k, u in enumerate(("U9", "U10")):
        x, y = 880, Y(560 + k * 200)
        sr = pg.place(u, "HC595", x, y, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
        nets = P[u].nets
        for num in ("14", "11", "12", "10", "16"):
            pg.stub_port(sr[num], nets[num], "IN", "left")
        pg.stub_flag(sr["13"], "GND_D_F", "left", 15)
        pg.stub_flag(sr["8"], "GND_D_F", "left", 15)
        for num in ("15", "1", "2", "3", "4", "5", "6", "7"):
            net = nets.get(num)
            if not net:
                continue
            r = next(p for p in parts if p.kind == "R" and p.nets["1"] == net)
            rr = pg.place(r.ref, r_dev(r.value), x + 90, sr[num][1], des=(-18, -7, "LEFT_BOTTOM"),
                          value_at=(2, -7, "LEFT_BOTTOM"))
            pg.wire([sr[num], rr["1"]], net)
            pg.stub_port(rr["2"], r.nets["2"], "OUT", "right")
        if nets.get("9"):
            pg.stub_port(sr["9"], nets["9"], "OUT", "right")
    x, y = 1250, Y(640)
    sr = pg.place("U11", "HC165", x, y, des=(-50, -57, "LEFT_BOTTOM"), value_at=(-50, 63, "LEFT_BOTTOM"))
    nets = P["U11"].nets
    for num in ("1", "2", "16"):
        pg.stub_port(sr[num], nets[num], "IN", "left")
    for num in ("10", "15", "8"):
        pg.stub_flag(sr[num], "GND_D_F", "left", 15)
    for num in circuit.HC165_INPUTS:
        net = nets[num]
        if net == "GND_D_F":
            pg.stub_flag(sr[num], "GND_D_F", "right", 15)
        else:
            pg.stub_port(sr[num], net, "IN", "right")
    pg.stub_port(sr["9"], nets["9"], "OUT", "right")
    for k, cref in enumerate(("C9", "C10", "C11")):
        cx = 1470 + k * 50
        c = pg.place(cref, c_dev("100n"), cx, Y(520), 270, *V_TXT)
        pg.wire([c["1"], (cx, Y(490)), (cx - 20, Y(490))], "3V3D_F")
        pg.port(cx - 20, Y(490), "3V3D_F", "IN", "left")
        pg.stub_flag(c["2"], "GND_D_F")
    pg.text(1440, Y(600), "C9..C11 at U9..U11 pin 16", 8)

    # buttons
    pg.text(70, Y(835), "Buttons (Thonk Highly Tactile, 5x5 mm): pins 1+4 to GND_D_F, 2+3 to the 74HC165 - verify the internal pairing before soldering", 12)
    for k, (ref, label, sw) in enumerate(circuit.BUTTONS):
        bx, by = 150 + k * 185, Y(935)
        s = pg.place(ref, "SW", bx, by, des=(-12, -20, "LEFT_BOTTOM"), name=False)
        pg.text(bx - 30, by + 30, label, 9)
        net = P[ref].nets["2"]
        pg.wire([s["1"], (bx - 45, by)], "GND_D_F")
        pg.wire([s["4"], (bx - 45, by + 10)], "GND_D_F")
        pg.wire([(bx - 45, by + 10), (bx - 45, by)], "GND_D_F")
        pg.wire([(bx - 45, by), (bx - 45, by - 10)], "GND_D_F")
        pg.flag(bx - 45, by - 10, 180, "GND_D_F")
        pg.wire([s["2"], (bx + 50, by)], net)
        pg.wire([s["3"], (bx + 50, by + 10)], net)
        pg.wire([(bx + 50, by + 10), (bx + 50, by)], net)
        r = pg.place(f"R{100 + k}", r_dev("10k"), bx + 50, by - 40, 270, *V_TXT)
        pg.wire([r["2"], (bx + 50, by)], net)
        pg.wire([(bx + 50, by), (bx + 70, by)], net)
        pg.port(bx + 70, by, net, "OUT", "right")
        pg.wire([r["1"], (bx + 50, by - 70), (bx + 30, by - 70)], "3V3D_F")
        pg.port(bx + 30, by - 70, "3V3D_F", "IN", "left")

    # LEDs
    for k, (ref, label, kind, _) in enumerate(circuit.LEDS):
        lx, ly = 150 + k * 148, Y(1050)
        led = pg.place(ref, "LED_RG" if kind == "RG" else "LED_G", lx, ly, des=(-15, -24, "LEFT_BOTTOM"), name=False)
        pg.text(lx - 30, ly + 24, label, 9)
        nets = P[ref].nets
        pg.stub_flag(led["2"], "GND_D_F", "right", 15)
        if kind == "RG":
            pg.stub_port(led["1"], nets["1"], "IN", "left")
            pg.stub_port(led["3"], nets["3"], "IN", "left")
        else:
            pg.stub_port(led["1"], nets["1"], "IN", "left")

    # headers
    pg.text(1180, Y(725), "Headers to the main board (male pins here)", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        x, y = 1250 + k * 80, Y(800)
        h = pg.place(ref + "F", kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        nets = P[ref + "F"].nets
        for num, net in nets.items():
            if net in ("GND_F", "GND_D_F"):
                pg.stub_flag(h[num], net, "left", 15)
            else:
                pg.stub_port(h[num], net, "IN", "left")
    return pg


def pin_map(part, pid):
    return pid


def translated(pg, dx):
    """Copies of a page's components and wires shifted by dx, so two pages can be checked as one board."""
    comps = []
    for c in pg.comps:
        c2 = dict(c)
        c2["pins"] = {k: (x + dx, y) for k, (x, y) in c["pins"].items()}
        comps.append(c2)
    wires = [(net, [((a[0] + dx, a[1]), (b[0] + dx, b[1])) for a, b in segs], label) for net, segs, label in pg.wires]
    return comps, wires


def main():
    pr = MProject()
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    pages = [main_page_1(pr, mb), main_page_2(pr, mb), faceplate_page(pr, fb)]
    bad = []
    # the main board is drawn over two pages: check them together
    merged = MPage.__new__(MPage)
    merged.comps = pages[0].comps + translated(pages[1], 10000)[0]
    merged.wires = pages[0].wires + translated(pages[1], 10000)[1]
    merged.title = "Main board"
    bad += check(merged, mb, pin_map)
    bad += check(pages[2], fb, pin_map)
    for b in bad:
        print("PROBLEM:", b)
        if b.startswith("point ("):
            px, py = eval(b.split(" lies")[0][6:])
            for pg_ in pages:
                for c in pg_.comps:
                    for num, (x, y) in c["pins"].items():
                        if abs(x - px) < 0.01 and abs(y - py) < 0.01:
                            print("       pin", c["ref"] or c["dev"], num, "on page", pg_.number)
    pr.write(pages, OUT)
    for pg in pages:
        render(pr, pg, PREVIEW.format(pg.title.split(":")[0].lower().replace(" ", "-")))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(pages)} pages, {len(bad)} problems")


if __name__ == "__main__":
    main()
