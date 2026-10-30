"""Plaitsy as an EasyEDA Pro project (.epro2): schematic pages, both PCBs
placed, and the panel PCB.

Builds on the Plaitsy stripboard exporter (../../../plaitsy/hardware/tools)
for the file format and the MorrisSynth library parts cached there:
TL074ACN, the WQP518MA jack, PTV09A pots, LR1F resistors, FG28 / SR305
capacitors, net ports, ground flags and the sheet frame. Everything else is
drawn here in the same style, with real pin numbers, and gets a generated
through-hole footprint (the Marblesy set):

  Daisy Seed on seed_power_opamps   56 pads, 2.54 mm pitch, rows 15.24 mm apart
  74HC595 / 74HC4051 (DIP-16), 3 mm bicolour LED (3 leads), the Thonk
  low-profile LED button, 1xN pin headers.

Two A3 pages: Main board (Seed, eight CV inputs, bias, clamps, headers) and
Faceplate. Every connection that leaves a block is a net port; nets that
cross between the boards are the header pins.

Run from plaits/hardware/tools:  python easyeda_export.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAITSY = os.path.normpath(os.path.join(HERE, "..", "..", "..", "plaitsy", "hardware", "tools"))
sys.path.insert(0, PLAITSY)
import easyeda_export as ee                      # noqa: E402  (the Plaitsy stripboard exporter)

ee.LIBFILE = os.path.join(PLAITSY, "..", "easyeda", "morrissynth-parts.epru")
from easyeda_export import (Doc, Symbol, Page, Project, meta, attr_payload, Y, render, check,   # noqa: E402
                            new_uuid, DEV, SRC, W, H, H_TXT, V_TXT)


def _load(name):
    spec = importlib.util.spec_from_file_location("plaits_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")
pcb = _load("pcb")
panel_pcb = _load("panel_pcb")

NAME = "Plaitsy"
OUT = os.path.join(HERE, "..", "easyeda", "Plaits.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "plaits-easyeda-{}.png")
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
    """A through-hole footprint in mm; written as an EasyEDA Pro FOOTPRINT doc. Pads are round (or square)
    with round holes, or oval with slot holes (slot=(w, h)) like a pot's lugs."""

    def __init__(self, title, designator="U?"):
        self.title, self.designator = title, designator
        self.pads, self.silk = [], []        # (num, x, y, hole, pad_w, pad_h, square, slot), [(kind, data)]
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


def fp_led3():
    """3 mm bicolour LED, 1.27 mm pitch, body centred on the middle lead (common cathode)."""
    f = Footprint("LED-3MM-3P", "D?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 1.27, 0, 0.8, 1.1, square=(i == 0), h=1.7)
    f.circle(0, 0, 1.6)
    return f


def fp_led_button():
    """Thonk low-profile LED button (7.5 mm square, 5.5 mm round cap): switch
    pins 1-4 on a 5.08 mm square (1+2 and 3+4 are the contacts), LED anode
    pin 5 and cathode pin 6 at x = +-2.7. No holes for the three plastic feet:
    Thonk's (-1.25, 1.75) and (1.25, 1.75) holes overlap the 1.6 mm pads of
    pins 1 and 2 (EasyEDA DRC errors on Marblesy), so the feet get clipped off
    and the body sits on the board, at Thonkiconn height as with the holes."""
    f = Footprint("SW-TACT-LP-LED-THONK", "SW?")
    for num, (x, y) in ((1, (2.54, 2.54)), (2, (-2.54, 2.54)), (3, (2.54, -2.54)), (4, (-2.54, -2.54)),
                        (5, (2.7, 0)), (6, (-2.7, 0))):
        f.pad(num, x, y, 1.0, 1.6, square=(num == 1))
    f.rect(-3.75, -3.75, 3.75, 3.75)
    f.circle(0, 0, 2.75)
    return f


def fp_res_vertical():
    """A resistor standing up, 2.54 mm: the body over pad 1, the bent lead to pad 2. The pads and the
    origin of the 1/4W-RESISTOR-VERTICAL footprint the routed Marblesy main board uses."""
    f = Footprint("RES-TH-VERTICAL-P2.54", "R?")
    f.pad(1, 0, 0.48006, 0.8, 1.6)
    f.pad(2, 0, -2.0574, 0.8, 1.6)
    f.circle(0, 0.48006, 1.1)
    f.line(0, -0.79, 0, -1.11)
    return f


def fp_dip(n, title):
    """DIP on the standard 300 mil (7.62 mm) row pitch, pin 1 bottom-left, counting anticlockwise. The library
    TL074ACN footprint has its rows 8.89 mm apart: no socket fits it and the chip's legs have to be bent."""
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


def fp_alpha_pot():
    """Alpha 9 mm vertical pot (RD901F) in the frame of the library PTV09A footprint (Bourns' part, its lugs
    0.5 mm off the Alpha's): pins 1-3 at y = -3.5, x = -2.5 / 0 / 2.5, the shaft 7.5 mm from them at y = +4.0,
    the mounting lugs (pads 4 / 5) on the shaft line at x = -+4.8 as oval pads with slots (KiCad RD901F-40-00D)."""
    f = Footprint("POT-ALPHA-9MM-RD901F", "RV?")
    for i, x in enumerate((-2.5, 0.0, 2.5)):
        f.pad(i + 1, x, -3.5, 1.0, 1.8, square=(i == 0))
    for num, x in (("4", -4.8), ("5", 4.8)):
        f.pad(num, x, 4.0, size=2.72, h=3.24, slot=(1.1, 1.8))
    f.rect(-4.75, -2.5, 4.75, 8.85)       # body, 9.5 wide, from 1 mm off the pin row to 4.85 mm past the shaft
    f.circle(0, 4.0, 3.5)
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
    s = ic_symbol("Daisy Seed on seed_power_opamps", "DaisySeedBreakout.3", left, right, w=80)
    s.text(-30, 120, "Daisy Seed", 10)
    s.text(-45, 133, "seed_power_opamps", 8)
    return s


def hc595_symbol():
    left = [(0, "14", "SER"), (1, "11", "SRCLK"), (2, "12", "RCLK"), (3, "13", "/OE"), (4, "10", "/SRCLR"),
            (6, "16", "VCC"), (7, "8", "GND")]
    right = [(0, "15", "QA"), (1, "1", "QB"), (2, "2", "QC"), (3, "3", "QD"), (4, "4", "QE"), (5, "5", "QF"),
             (6, "6", "QG"), (7, "7", "QH"), (8, "9", "QH'")]
    return ic_symbol("74HC595", "74HC595.2", left, right)


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


# ------------------------------------------------------------------ project
R_NEW = {"470": ("LR1F470R", "470Ω"), "12k": ("LR1F12K", "12kΩ"), "13k": ("LR1F13K", "13kΩ"),
         "15k": ("LR1F15K", "15kΩ"), "33k": ("LR1F33K", "33kΩ"), "100k": ("LR1F100K", "100kΩ")}
C_NEW = {"1n": ("FG28C0G1H102JNT00", "1nF"), "100p": ("FG28C0G1H101JNT00", "100pF")}
RESISTORS = {"R1k", "R10k"} | {"R" + v for v in R_NEW}


class MPage(Page):
    page_count = "1"

    def place(self, ref, dev_key, *args, **kw):
        if self.title.startswith("Main") and dev_key in RESISTORS:   # every main-board resistor stands up
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
        vals = [("Symbol", sym), ("@Project Name", NAME), ("@Page Count", self.page_count), ("@Update Date", today),
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
        # your TL074 and pot devices on standard footprints: DIP-14 on 7.62 mm rows, the Alpha RD901F
        a = dict(self.device_attrs("TL074"))
        a.update(Footprint=self._footprint(fp_dip(14, "DIP-14-W7.62-P2.54")),
                 Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        self._device("TL074", "TL074ACN", a, ["Amplifiers"])
        a = dict(self.device_attrs("POT"))
        a.update(Footprint=self._footprint(fp_alpha_pot()), Description="Alpha 9 mm vertical pot (Thonk)")
        self._device("POT", "Alpha 9mm B10k", a, ["Potentiometers"])
        fps = {"SEED": self._footprint(fp_seed_breakout()), "LED3": self._footprint(fp_led3()),
               "SWLED": self._footprint(fp_led_button()), "RV": self._footprint(fp_res_vertical())}
        for key in ["R1k", "R10k"] + ["R" + v for v in R_NEW]:     # each resistor again, standing up
            a = dict(self.device_attrs(key))
            a["Footprint"] = fps["RV"]
            self._device(key + "V", a["Manufacturer Part"], a, ["Resistors", "Through Hole Resistors"])
        for n in (8, 9):
            fps[f"HDR{n}"] = self._footprint(fp_header(n))
        new = [
            ("SEED", seed_symbol(), "Daisy Seed + seed_power_opamps", "U?", fps["SEED"],
             "Daisy Seed plugged into Rob Heel's seed_power_opamps breakout; 2.54 mm socket strips on the main board"),
            ("MUX", ee.mux_symbol(), "74HC4051", "U?", dip16, "8-channel analog multiplexer, DIP-16"),
            ("HC595", hc595_symbol(), "74HC595", "U?", dip16, "8-bit shift register with output latch, DIP-16"),
            ("LED_RG", ee.led_symbol(), "LED 3mm bicolour R/G CC", "D?", fps["LED3"],
             "3 mm bicolour LED, red/green, common cathode on the middle lead, 1.27 mm pitch (Tayda, Kingbright)"),
            ("SWLED", led_button_symbol(), "LED button, Thonk low profile", "SW?", fps["SWLED"],
             "Thonk low-profile LED button: 7.5 mm body, 5.5 mm round cap, 1+2 / 3+4 contacts, LED anode 5, "
             "cathode 6. Clip the three plastic feet off: the board has no holes for them"),
        ]
        for n in (8, 9):
            new.append((f"HDR{n}", header_symbol(n), f"Pin header 1x{n}", "H?", fps[f"HDR{n}"],
                        f"Board-to-board header, 1x{n}, 2.54 mm"))
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
            self._device(key, title, attrs)

    def write(self, boards, path, template):
        """boards: [(title, pages, pcb.Board)]; each gets a BOARD doc holding
        its schematic pages and its PCB."""
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
        lines += [l for u, d in self.lib.items() if d["docType"] == "BLOB" for l in d["lines"]]
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Mutable Instruments Plaits clone: Daisy Seed on the seed_power_opamps "
                                  "breakout, TL074 CV inputs, 74HC4051 pot mux, 74HC595 LED drive; two stacked "
                                  "PCBs and a PCB panel, 12HP.",
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
        if net in ("+12V", "-12V", "3V3A", "3V3D") or net.startswith("ADC_") or net in ("MUX_OUT", "BTN_A", "BTN_B"):
            kind = "IN"
        else:
            kind = "OUT"
        pg.stub_port(u2[pin], net, kind, side)
    return u2


def inverting_stage(pg, P, ox, oy, amp_ref, sec, rin, rfb, cfb, rs, nin, nout, in_net, out_net, plus_net,
                    supply=False):
    """Plaits-style inverting op-amp stage with Rf || Cf, series resistor to the output port."""
    amp = pg.place(amp_ref, "TL074", ox, oy, unit=sec, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
    a_in = pg.place(rin.ref, r_dev(rin.value), ox - 90, oy - 10, des=H_TXT[0], value_at=H_TXT[1])
    a_rf = pg.place(rfb.ref, r_dev(rfb.value), ox, oy - 60, des=H_TXT[0], value_at=H_TXT[1])
    a_rs = pg.place(rs.ref, r_dev(rs.value), ox + 100, oy, des=H_TXT[0], value_at=H_TXT[1])
    out, inm, inp = circuit.SECTION[sec]
    jx, jy, kx = ox - 55, oy - 10, ox + 60
    pg.wire([a_in["2"], (jx, jy)], nin)
    pg.wire([(jx, jy), amp[inm]], nin)
    pg.wire([(jx, jy), (jx, oy - 60)], nin)
    pg.wire([(jx, oy - 60), a_rf["1"]], nin)
    pg.wire([amp[out], (kx, oy)], nout)
    pg.wire([(kx, oy), a_rs["1"]], nout)
    pg.wire([(kx, oy), (kx, oy - 60)], nout)
    pg.wire([(kx, oy - 60), a_rf["2"]], nout)
    a_cf = pg.place(cfb.ref, c_dev(cfb.value), ox, oy - 90, des=(-20, -10, "LEFT_BOTTOM"),
                    value_at=(2, -10, "LEFT_BOTTOM"))
    pg.wire([(jx, oy - 60), (jx, oy - 90), a_cf["1"]], nin)
    pg.wire([(kx, oy - 60), (kx, oy - 90), a_cf["2"]], nout)
    pg.stub_port(a_in["1"], in_net, "IN", "left")
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


def divider(pg, P, ra, rb, c, x, top, out_net, label):
    """3V3A -> ra -> node -> rb -> GND, node decoupled by c; the node leaves as out_net."""
    a = pg.place(ra, r_dev(P[ra].value), x, top + 20, 270, *V_TXT)
    b = pg.place(rb, r_dev(P[rb].value), x, top + 80, 270, *V_TXT)
    cc = pg.place(c, c_dev(P[c].value), x + 40, top + 80, 270, des=(8, -2, "LEFT_BOTTOM"), value_at=(8, 8, "LEFT_BOTTOM"))
    node = (x, top + 50)
    pg.wire([a["2"], node], out_net)
    pg.wire([node, b["1"]], out_net)
    pg.wire([node, (x + 40, top + 50), cc["1"]], out_net)
    pg.wire([node, (x - 20, top + 50)], out_net)
    pg.port(x - 20, top + 50, out_net, "OUT", "left")
    pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "3V3A")
    pg.port(x - 20, top - 10, "3V3A", "IN", "left")
    pg.stub_gnd(b["2"])
    pg.stub_gnd(cc["2"])
    pg.text(x - 30, top - 25, label, 9)


def main_page(pr, parts):
    P = {p.ref: p for p in parts}
    pg = MPage(pr, "Main board: Seed, CV inputs", 1)
    pg.text(150, Y(50), "Daisy Seed on the seed_power_opamps breakout (2.54 mm sockets on this board); audio out via its J4", 12)
    seed_block(pg, P, 260, Y(260))

    pg.text(560, Y(32), "CV inputs: TL074 inverting stages biased from 3V3A, gain -0.13 (+-12 V -> 0.10..3.22 V); "
                        "V/OCT gain -0.33 (-2.9..+7.1 V, 0.2 units/V), 1k into the ADC", 12)
    for i, (name, label, u, sec, rf, cf, bias) in enumerate(circuit.CV_CHANNELS):
        col, row = divmod(i, 4)
        ox, oy = 730 + col * 490, Y(155 + row * 170)
        rin, rfb, rs = (P[f"R{21 + 3 * i + k}"] for k in range(3))
        inverting_stage(pg, P, ox, oy, u, sec, rin, rfb, P[f"C{21 + i}"], rs, f"IN_{name}", f"OA_{name}",
                        f"CV_{name}", f"ADC_{name}", bias, supply=(sec == 1))
        pg.text(ox - 110, oy - 110, label, 9)

    # headers to the faceplate
    pg.text(70, Y(740), "Board-to-board headers (female sockets on this board; pin 1 marked)", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        x, y = 160 + k * 190, Y(835)
        h = pg.place(ref, kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        nets = P[ref].nets
        for num, net in nets.items():
            if net == "GND":
                pg.stub_gnd(h[num], "left", 15)
            else:
                kind_ = "OUT" if net in ("OUT", "AUX", "PROBE", "MUX_S0", "MUX_S1", "MUX_S2", "SPI_SCK", "SPI_MOSI",
                                         "LED_LATCH", "3V3D", "3V3A", "BTN_LED_A", "BTN_LED_B") else "IN"
                pg.stub_port(h[num], net, kind_, "left")

    # bias dividers
    pg.text(720, Y(760), "Bias: 1.467 V for the wide channels, 1.768 V for V/OCT", 12)
    divider(pg, P, "R45", "R46", "C29", 790, Y(810), "BIAS_A", "BIAS A")
    divider(pg, P, "R47", "R48", "C30", 950, Y(810), "BIAS_V", "BIAS V")

    # V/OCT clamps: ADC pin between GND and 3V3A
    pg.text(1080, Y(760), "V/OCT clamps (BAT85)", 12)
    x, top = 1130, Y(810)
    d21 = pg.place("D21", "BAT85", x, top + 20, 270, *V_TXT)     # cathode (pin 1) up to 3V3A
    d22 = pg.place("D22", "BAT85", x, top + 80, 270, *V_TXT)     # cathode on the ADC node, anode to GND
    node = (x, top + 50)
    pg.wire([d21["2"], node], "ADC_VOCT")
    pg.wire([node, d22["1"]], "ADC_VOCT")
    pg.wire([node, (x - 20, top + 50)], "ADC_VOCT")
    pg.port(x - 20, top + 50, "ADC_VOCT", "IN", "left")
    pg.wire([d21["1"], (x, top - 10), (x - 20, top - 10)], "3V3A")
    pg.port(x - 20, top - 10, "3V3A", "IN", "left")
    pg.stub_gnd(d22["2"])

    # button LED resistors
    pg.text(1080, Y(930), "Button LEDs: GPIO -> 470R -> header", 12)
    for k, (r, a, b) in enumerate((("R60", "BTN_LED_A_IO", "BTN_LED_A"), ("R61", "BTN_LED_B_IO", "BTN_LED_B"))):
        rr = pg.place(r, r_dev("470"), 1160, Y(965 + k * 40), des=H_TXT[0], value_at=H_TXT[1])
        pg.stub_port(rr["1"], a, "IN", "left")
        pg.stub_port(rr["2"], b, "OUT", "right")

    pg.text(1300, Y(760), "Supply decoupling U3, U4", 12)
    for k, (cp, cn) in enumerate((("C31", "C32"), ("C33", "C34"))):
        decoupling_pair(pg, P, cp, cn, 1390 + k * 100, Y(810))

    pg.text(40, Y(1090), "Net ports with the same name connect. CV_*, PROBE, OUT, AUX, MUX_*, SPI_*, LED_LATCH, "
                        "BTN_* and the supplies are the header pins to the faceplate (H1..H3).", 10)
    pg.text(40, Y(1110), "GND here is one net: AGND (Seed pin 20), DGND (pin 40) and the breakout's GND pins. "
                        "The breakout ties them too.", 10)
    return pg


def faceplate_page(pr, parts):
    P = {p.ref: p for p in parts}
    pg = MPage(pr, "Faceplate", 1)
    probe_r = {p.nets["1"]: p for p in parts if p.kind == "R" and p.nets.get("2") == "PROBE_F"}

    pg.text(70, Y(45), "Jacks (Thonkiconn). Sleeves to GND_F; MODEL, HARMO and V/OCT have the switch lug grounded, "
                       "the other inputs get the probe through 10k; outputs leave it open", 12)
    for i, (ref, label, tip, tn) in enumerate(circuit.JACKS):
        col, row = divmod(i, 5)
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
        pg.port(x + 120, y, tip, "OUT" if tip.startswith("CV_") else "IN", "right")

    pg.text(820, Y(45), "Pots (B10k) into the 74HC4051; channel order = mux Y0..Y7, Y7 grounded", 12)
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
    gnd_pins = []
    for row, num, name in ee.MUX_LEFT:
        if nets[num] == "GND_F":
            pg.stub_flag(mux[num], "GND_F", "left", 15)
        else:
            pg.stub_port(mux[num], nets[num], "IN", "left")
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

    # shift registers and the LED resistors
    pg.text(820, Y(495), "LEDs: two 74HC595 on the SPI bus (U9 drives the eight red anodes, U10 the eight green), 470R per colour", 12)
    for k, u in enumerate(("U9", "U10")):
        x, y = 880, Y(560 + k * 200)
        sr = pg.place(u, "HC595", x, y, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
        nets = P[u].nets
        for num in ("14", "11", "12", "10", "16"):
            pg.stub_port(sr[num], nets[num], "IN", "left")
        pg.stub_flag(sr["13"], "GND_D_F", "left", 15)
        pg.stub_flag(sr["8"], "GND_D_F", "left", 15)
        for num in circuit.HC595_OUTS:
            net = nets[num]
            r = next(p for p in parts if p.kind == "R" and p.nets["1"] == net)
            rr = pg.place(r.ref, r_dev(r.value), x + 90, sr[num][1], des=(-18, -7, "LEFT_BOTTOM"),
                          value_at=(2, -7, "LEFT_BOTTOM"))
            pg.wire([sr[num], rr["1"]], net)
            pg.stub_port(rr["2"], r.nets["2"], "OUT", "right")
        if nets.get("9"):
            pg.stub_port(sr["9"], nets["9"], "OUT", "right")
    for k, cref in enumerate(("C9", "C10")):
        cx = 1300 + k * 80
        c = pg.place(cref, c_dev("100n"), cx, Y(560), 270, *V_TXT)
        pg.wire([c["1"], (cx, Y(530)), (cx - 20, Y(530))], "3V3D_F")
        pg.port(cx - 20, Y(530), "3V3D_F", "IN", "left")
        pg.stub_flag(c["2"], "GND_D_F")
    pg.text(1270, Y(640), "C9, C10 at U9 / U10 pin 16", 8)

    # the eight LEDs
    pg.text(70, Y(822), "Model LEDs: 3 mm bicolour, common cathode to GND_D_F", 12)
    for k, (ref, label, kind) in enumerate(circuit.LEDS):
        lx, ly = 150 + k * 148, Y(880)
        led = pg.place(ref, "LED_RG", lx, ly, des=(-15, -24, "LEFT_BOTTOM"), name=False)
        pg.text(lx - 30, ly + 26, label, 8)
        nets = P[ref].nets
        pg.stub_flag(led["2"], "GND_D_F", "right", 15)
        pg.stub_port(led["1"], nets["1"], "IN", "left")
        pg.stub_port(led["3"], nets["3"], "IN", "left")

    # buttons
    pg.text(70, Y(960), "Model buttons: Thonk low-profile LED buttons (1+2 / 3+4 contacts, Seed pull-ups), "
                        "LED on pins 5 / 6 from the main board's 470R", 12)
    for k, (ref, label, sw) in enumerate(circuit.BUTTONS):
        bx, by = 180 + k * 300, Y(1050)
        s = pg.place(ref, "SWLED", bx, by, des=(-50, -42, "LEFT_BOTTOM"), name=False)
        pg.text(bx - 50, by + 48, label, 9)
        gx = s["1"][0] - 15
        pg.wire([s["1"], (gx, s["1"][1])], "GND_D_F")
        pg.wire([s["2"], (gx, s["2"][1])], "GND_D_F")
        pg.wire([(gx, s["1"][1]), (gx, s["2"][1])], "GND_D_F")
        pg.wire([(gx, s["1"][1]), (gx, s["1"][1] - 10)], "GND_D_F")
        pg.flag(gx, s["1"][1] - 10, 180, "GND_D_F")
        net = P[ref].nets["3"]
        nx = s["3"][0] + 15
        pg.wire([s["3"], (nx, s["3"][1])], net)
        pg.wire([s["4"], (nx, s["4"][1])], net)
        pg.wire([(nx, s["3"][1]), (nx, s["4"][1])], net)
        pg.wire([(nx, s["4"][1]), (nx + 20, s["4"][1])], net)
        pg.port(nx + 20, s["4"][1], net, "OUT", "right")
        pg.stub_port(s["5"], P[ref].nets["5"], "IN", "left")
        pg.stub_flag(s["6"], "GND_D_F", "right", 15)

    # headers
    pg.text(760, Y(960), "Headers to the main board (male pins here)", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        x, y = 860 + k * 160, Y(1050)
        h = pg.place(circuit.fb_ref(ref), kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        nets = P[circuit.fb_ref(ref)].nets
        for num, net in nets.items():
            if net in ("GND_F", "GND_D_F"):
                pg.stub_flag(h[num], net, "left", 15)
            else:
                pg.stub_port(h[num], net, "IN", "left")
    return pg


def pin_map(part, pid):
    return pid


def part_info(pages):
    """ref -> device key, schematic Unique ID and the PCB's Channel ID
    ('$' + page number + id of the part's first schematic component)."""
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
    pages = [main_page(pr, mb), faceplate_page(pr, fb)]
    bad = check(pages[0], mb, pin_map) + check(pages[1], fb, pin_map)
    for b in bad:
        print("PROBLEM:", b)
        if b.startswith("point ("):
            px, py = eval(b.split(" lies")[0][6:])
            for pg_ in pages:
                for c in pg_.comps:
                    for num, (x, y) in c["pins"].items():
                        if abs(x - px) < 0.01 and abs(y - py) < 0.01:
                            print("       pin", c["ref"] or c["dev"], num, "on page", pg_.number)
    # PCBs: placed and net-assigned, not routed; part info per board, as designators may repeat across boards
    board_fb = pcb.faceplate_board(pr, fb, part_info(pages[1:]), circuit)
    board_mb = pcb.main_board(pr, mb, part_info(pages[:1]), circuit)
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb, circuit))
    for b in pcb_bad:
        print("PCB:", b)
    template = pcb.load_template(ee)
    # the panel: a board of its own, no parts; its schematic page only carries a note
    panel_page = MPage(pr, "Panel", 1)
    panel_page.text(70, Y(60), "Plaitsy 12HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the "
                               "bare-copper OUT / AUX band are in the PCB document; the art is hardware/panel/plaits-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([(f"{NAME} Main", pages[:1], board_mb), (f"{NAME} Faceplate", pages[1:], board_fb),
              (f"{NAME} Panel", [panel_page], board_panel)], OUT, template)
    for pg in pages:
        render(pr, pg, PREVIEW.format(pg.title.split(":")[0].lower().replace(" ", "-")))
    board_mb.render(PREVIEW.format("pcb-main-board"))
    board_fb.render(PREVIEW.format("pcb-faceplate"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(pages)} pages, {len(bad)} schematic problems; "
          f"{len(board_mb.placed)} + {len(board_fb.placed)} parts placed on the PCBs, {len(pcb_bad)} PCB problems")


if __name__ == "__main__":
    main()
