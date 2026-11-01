"""Ringsy as an EasyEDA Pro project (.epro2): the schematic of both boards. PCB placement (pcb.py) and
the panel as a third PCB (panel_pcb.py) follow in their own step, as for Tempo.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the file format, the connectivity
check and the previews, and draws the way Plaitsy's module exporter (plaits/) does. Library parts come
from the MorrisSynth cache: LR1F resistors, FG28 / SR305 capacitors, TL074ACN, the WQP518MA jack, the
PTV09A pot symbol, the 1N5819 symbol, the 1N4148's DO-35 footprint, the 74HC595N's DIP-16, net
ports, ground flag, sheet frame. Generated here, all through-hole:

  footprints  the Daisy Seed on seed_power_opamps, DIP-14 on 7.62 mm rows (TL074), the Alpha 9 mm pot,
              the Thonk LED button, the 3 mm bicolour LED, TO-92 with its pads named E / B / C, a
              standing resistor (every main-board resistor, as on Plaitsy), a 6.3 mm radial can for
              the bipolar 10u, 1xN headers
  symbols     Seed, 74HC4051, bicolour LED, LED button, 2N3904 (pins E / B / C), headers

Pages: main board 1 (Seed, the six CV inputs, bias, V/OCT clamps, decoupling), main board 2 (the ODD /
EVEN output stages, STRUM, the probe clamps, LED resistors, headers), faceplate (jacks and their
normals, pots and the mux, LEDs, buttons, headers). The analog stages are drawn with wires; every
connection that leaves a block is a net port, same name = same net within a board, and the header
pins carry the nets across.

Run from rings/hardware/tools:  python easyeda_export.py
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

ee.LIBFILE = os.path.join(PLAITSY, "..", "easyeda", "morrissynth-parts.epru")
from easyeda_export import (Doc, Symbol, Page, Project, meta, attr_payload, Y, render, check,   # noqa: E402
                            new_uuid, DEV, SRC, W, H, H_TXT, V_TXT)


def _load(name):
    spec = importlib.util.spec_from_file_location("rings_" + name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("circuit")

NAME = "Ringsy"
OUT = os.path.join(HERE, "..", "easyeda", "Ringsy.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "rings-easyeda-{}.png")
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
    """Thonk low-profile LED button (7.5 mm square, 5.5 mm round cap): switch pins 1-4 on a 5.08 mm square
    (1+2 and 3+4 are the contacts), LED anode pin 5 and cathode pin 6 at x = +-2.7. No holes for the three
    plastic feet (they overlap the pads of pins 1 and 2): clip them off (Plaitsy's footprint)."""
    f = Footprint("SW-TACT-LP-LED-THONK", "SW?")
    for num, (x, y) in ((1, (2.54, 2.54)), (2, (-2.54, 2.54)), (3, (2.54, -2.54)), (4, (-2.54, -2.54)),
                        (5, (2.7, 0)), (6, (-2.7, 0))):
        f.pad(num, x, y, 1.0, 1.6, square=(num == 1))
    f.rect(-3.75, -3.75, 3.75, 3.75)
    f.circle(0, 0, 2.75)
    return f


def fp_res_vertical():
    """A resistor standing up, 2.54 mm: the body over pad 1, the bent lead to pad 2 (Plaitsy's / Marblesy's)."""
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
    hx, hy = half * 1.27 + 0.7, 3.25
    f.rect(-hx, -hy, hx, hy)
    f.circle(-hx + 0.9, -hy + 0.9, 0.3)
    return f


def fp_alpha_pot():
    """Alpha 9 mm vertical pot (RD901F) in the frame of the library PTV09A footprint: pins 1-3 at y = -3.5,
    x = -2.5 / 0 / 2.5, the shaft 7.5 mm from them at y = +4.0, the mounting lugs (pads 4 / 5) on the shaft
    line at x = -+4.8 as oval pads with slots (Plaitsy's)."""
    f = Footprint("POT-ALPHA-9MM-RD901F", "RV?")
    for i, x in enumerate((-2.5, 0.0, 2.5)):
        f.pad(i + 1, x, -3.5, 1.0, 1.8, square=(i == 0))
    for num, x in (("4", -4.8), ("5", 4.8)):
        f.pad(num, x, 4.0, size=2.72, h=3.24, slot=(1.1, 1.8))
    f.rect(-4.75, -2.5, 4.75, 8.85)
    f.circle(0, 4.0, 3.5)
    return f


def fp_seed_breakout():
    """Rob Heel's seed_power_opamps board, pads as measured in its PCB file (Plaitsy's). Origin at the
    centre of the Seed's pin field; pins 1 and 40 at +x (the USB end). y grows downwards on the canvas."""
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


def fp_to92_ebc():
    """TO-92 in line, 2.54 mm, the 2N3904's order: flat side towards -y, E B C left to right. The pads are
    named by function, like the symbol's pins, so nothing can swap them (Senay's rule)."""
    f = Footprint("TO-92-INLINE-P2.54-EBC", "Q?")
    for i, num in enumerate("EBC"):
        f.pad(num, (i - 1) * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.line(-2.6, -1.3, 2.6, -1.3)
    f.circle(0, 0, 2.6)
    return f


def fp_cap_radial():
    """Radial can, 6.3 mm, leads on 2.5 mm: the bipolar 10u (no polarity, both pads round)."""
    f = Footprint("CAP-RADIAL-D6.3-P2.50-NP", "C?")
    f.pad(1, -1.25, 0, 0.9, 1.6)
    f.pad(2, 1.25, 0, 0.9, 1.6)
    f.circle(0, 0, 3.25)
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


def npn_symbol():
    """Marblesy's 2N3904, its pins numbered by function (E / B / C) like the TO-92 pads."""
    s = Symbol("2N3904", "NPN_EBC.1", "Q?", [NAME])
    s.poly([(-20, 0), (-5, 0)])
    s.poly([(-5, -12), (-5, 12)])
    s.poly([(-5, -4), (10, -14), (10, -20)])
    s.poly([(-5, 4), (10, 14), (10, 20)])
    s.poly([(10, 14), (3, 13), (6, 8), (10, 14)], closed=True, fill="#000000")
    s.text(-18, -4, "B", 6)
    s.pin("B", "B", -20, 0, 0)
    s.pin("C", "C", 10, -20, 90)
    s.pin("E", "E", 10, 20, 270)
    return s


# ------------------------------------------------------------------ devices
# LR1F part numbers and values as the library writes them, for every resistor value in the netlist
R_NEW = {"150": ("LR1F150R", "150Ω"), "330": ("LR1F330R", "330Ω"), "6k8": ("LR1F6K8", "6.8kΩ"),
         "12k": ("LR1F12K", "12kΩ"), "13k": ("LR1F13K", "13kΩ"), "15k": ("LR1F15K", "15kΩ"),
         "20k": ("LR1F20K", "20kΩ"), "33k": ("LR1F33K", "33kΩ"), "43k": ("LR1F43K", "43kΩ"),
         "100k": ("LR1F100K", "100kΩ"), "470k": ("LR1F470K", "470kΩ"), "1M": ("LR1F1M0", "1MΩ")}
C_NEW = {"1n": ("FG28C0G1H102JNT00", "1nF", "±5%"), "10p": ("FG28C0G1H100DNT00", "10pF", "±0.5pF")}
RESISTORS = {"R1k", "R10k"} | {"R" + v for v in R_NEW}


def r_dev(value):
    return {"1k": "R1k", "10k": "R10k"}.get(value, "R" + value)


def c_dev(value):
    return {"100n": "C100n", "1u": "C1u", "10u NP": "C10uNP"}.get(value, "C" + value)


def dev_of(part, main=False):
    """Device key of a netlist part; main-board resistors stand up."""
    if part.kind == "R":
        return r_dev(part.value) + ("V" if main else "")
    if part.kind == "C":
        return c_dev(part.value)
    return {"1N4148": "D4148"}.get(part.kind, part.kind)


class MPage(Page):
    def __init__(self, project, title, number, count, main):
        self.page_count, self.main = str(count), main
        super().__init__(project, title, number)

    def place(self, ref, dev_key, *args, **kw):
        if self.main and dev_key in RESISTORS:   # every main-board resistor stands up
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
        self.new_docs.append(("FOOTPRINT", fp.build()))
        return fp.doc.uuid

    def _copy(self, key, src, title, tags, **changes):
        a = dict(self.device_attrs(src))
        a.update(changes)
        self._device(key, title, a, tags)

    def _new_devices(self):
        parts = circuit.all_parts()
        missing = sorted({p.value for p in parts if p.kind == "R" and r_dev(p.value) not in RESISTORS})
        assert not missing, f"resistor values without an LR1F device: {missing}"
        for val, (mpn, value) in R_NEW.items():
            self._copy("R" + val, "R1k", mpn, ["Resistors", "Through Hole Resistors"],
                       **{"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                          "LCSC Part Name": f"Metal film resistor {value} ±1% 600mW",
                          "Description": f"Metal film resistor {value} ±1% 600mW (TE LR1F series)"})
        for val, (mpn, value, tol) in C_NEW.items():
            self._copy("C" + val, "C100n", mpn, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"],
                       **{"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                          "Tolerance": tol, "Temperature Coefficient": "C0G", "LCSC Part Name": f"{value} {tol} 50V C0G",
                          "Description": f"Capacitance:{value} Tolerance:{tol} Voltage Rating:50V "
                                         "Temperature Coefficient:C0G"})
        fps = {"SEED": self._footprint(fp_seed_breakout()), "LED3": self._footprint(fp_led3()),
               "SWLED": self._footprint(fp_led_button()), "RV": self._footprint(fp_res_vertical()),
               "TO92": self._footprint(fp_to92_ebc()), "RADIAL": self._footprint(fp_cap_radial()),
               "DIP14": self._footprint(fp_dip(14, "DIP-14-W7.62-P2.54"))}
        self._copy("C10uNP", "C100n", "UES1H100MPM", ["Capacitors", "Aluminum Electrolytic Capacitors"],
                   **{"Manufacturer Part": "UES1H100MPM", "Manufacturer": "Nichicon", "Value": "10uF",
                      "Supplier Part": "", "Datasheet": "", "Tolerance": "±20%", "Temperature Coefficient": "",
                      "Footprint": fps["RADIAL"], "LCSC Part Name": "10uF 50V bipolar electrolytic 6.3x11",
                      "Description": "Bipolar (non-polarised) aluminium electrolytic 10 uF 50 V, 6.3 mm can, "
                                     "2.5 mm leads (Nichicon UES, or any bipolar 10 uF 25 V or more)"})
        d4148 = meta(self.lib[SRC["1N4148"]])["attributes"]
        diode = meta(self.lib[SRC["1N5819"]])["attributes"]["Symbol"]     # pin 1 = cathode, as in circuit.D
        for key, mpn, desc, tags in (
                ("BAT85", "BAT85", "Schottky diode 30 V 200 mA, DO-35", ["Diodes", "Schottky Diodes"]),
                ("D4148", "1N4148", "Small-signal diode 100 V 200 mA, DO-35", ["Diodes", "Switching Diodes"])):
            a = dict(d4148)
            a.update({"Symbol": diode, "Manufacturer Part": mpn, "LCSC Part Name": mpn, "Supplier Part": "",
                      "Manufacturer": "", "Datasheet": "", "Description": desc})
            self._device(key, mpn, a, tags)
        # your TL074 and pot devices on standard footprints: DIP-14 on 7.62 mm rows, the Alpha RD901F
        self._copy("TL074", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        self._copy("POT", "POT", "Alpha 9mm B10k", ["Potentiometers"], Footprint=self._footprint(fp_alpha_pot()),
                   Description="Alpha 9 mm vertical pot, B10k (Thonk)")
        for key in sorted(RESISTORS):     # each resistor again, standing up (the main board's)
            a = dict(self.device_attrs(key))
            a["Footprint"] = fps["RV"]
            self._device(key + "V", a["Manufacturer Part"], a, ["Resistors", "Through Hole Resistors"])
        dip16 = meta(self.lib[SRC["74HC595N"]])["attributes"]["Footprint"]
        colour = circuit.BUTTON_COLOUR
        new = [
            ("SEED", seed_symbol(), "Daisy Seed + seed_power_opamps", "U?", fps["SEED"],
             "Daisy Seed plugged into Rob Heel's seed_power_opamps breakout (audio in through its J5, its output "
             "op-amps fitted and unused); 2.54 mm socket strips on the main board"),
            ("MUX", ee.mux_symbol(), "74HC4051", "U?", dip16, "8-channel analog multiplexer, DIP-16"),
            ("NPN", npn_symbol(), "2N3904", "Q?", fps["TO92"], "NPN transistor, TO-92, pads E B C"),
            ("LED_RG", ee.led_symbol(), "LED 3mm bicolour R/G CC", "D?", fps["LED3"],
             "3 mm bicolour LED, red/green, common cathode on the middle lead, 1.27 mm pitch (Tayda, Kingbright)"),
            ("SWLED", led_button_symbol(), f"LED button {colour}, Thonk low profile", "SW?", fps["SWLED"],
             f"Thonk low-profile LED button, {colour}: 7.5 mm body, 5.5 mm round cap, 1+2 / 3+4 contacts, LED "
             "anode 5, cathode 6. Clip the three plastic feet off: the board has no holes for them"),
        ]
        for n in sorted({int(kind[3:]) for _, kind, _ in circuit.HEADERS}):
            new.append((f"HDR{n}", header_symbol(n), f"Pin header 1x{n}", "H?", self._footprint(fp_header(n)),
                        f"Board-to-board header 1x{n}, 2.54 mm: male on the faceplate, female on the main board"))
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "Supplier Part": "", "3D Model": "", "3D Model Title": "", "3D Model Transform": "",
                     "Description": desc}
            self._device(key, title, attrs)

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
        lines += [l for u, d in self.lib.items() if d["docType"] == "BLOB" for l in d["lines"]]
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Mutable Instruments Rings clone: Daisy Seed on the seed_power_opamps breakout, "
                                  "TL074 CV inputs and Rings' ODD / EVEN output stage, 74HC4051 pot mux, Thonk LED "
                                  "buttons; two stacked through-hole PCBs and a PCB panel, 14HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


# ------------------------------------------------------------------ drawing helpers
def find(P, kind, a, b):
    """The one part of this kind with pin 1 on net a and pin 2 on net b."""
    hits = [p for p in P.values() if p.kind == kind and p.nets.get("1") == a and p.nets.get("2") == b]
    assert len(hits) == 1, (kind, a, b, hits)
    return hits[0]


def two(pg, part, x, y, rot=0, txt=None):
    dev = r_dev(part.value) if part.kind == "R" else c_dev(part.value) if part.kind == "C" else dev_of(part)
    if txt is None:
        txt = H_TXT if rot in (0, 180) else V_TXT
    return pg.place(part.ref, dev, x, y, rot, *txt)


def adc_pin(net):
    """'A0' for the Seed pin that carries net."""
    return next(name.split("/")[-1] for name, n in circuit.SEED.values() if n == net)


def jack_label(tip):
    return next(label for ref, label, role, t, lug in circuit.JACKS if t == tip)


def amp_unit(pg, ref, sec, ox, oy, supply):
    amp = pg.place(ref, "TL074", ox, oy, unit=sec, des=(12, 22, "LEFT_BOTTOM"), value_at=(12, 32, "LEFT_BOTTOM"))
    if supply:
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))
    return amp


def feedback(pg, amp, sec, rf, cf, ox, oy, nin, nout, a_in):
    """The inverting stage's core (Plaitsy's): Rin's far end into in-, Rf || Cf from the summing node to
    the output; returns the summing node's top corner (jx, oy - 90) and the output node (kx, oy)."""
    out, inm, inp = circuit.SECTION[sec]
    a_rf = two(pg, rf, ox, oy - 60)
    a_cf = pg.place(cf.ref, c_dev(cf.value), ox, oy - 90, des=(-20, -10, "LEFT_BOTTOM"),
                    value_at=(2, -10, "LEFT_BOTTOM"))
    jx, kx = ox - 55, ox + 60
    pg.wire([a_in["2"], (jx, oy - 10)], nin)
    pg.wire([(jx, oy - 10), amp[inm]], nin)
    pg.wire([(jx, oy - 10), (jx, oy - 60)], nin)
    pg.wire([(jx, oy - 60), a_rf["1"]], nin)
    pg.wire([(jx, oy - 60), (jx, oy - 90), a_cf["1"]], nin)
    pg.wire([amp[out], (kx, oy)], nout)
    pg.wire([(kx, oy), (kx, oy - 60)], nout)
    pg.wire([(kx, oy - 60), a_rf["2"]], nout)
    pg.wire([(kx, oy - 60), (kx, oy - 90), a_cf["2"]], nout)
    return (jx, oy - 90), (kx, oy)


def cv_stage(pg, P, i, ox, oy):
    """Plaitsy's CV input: 100k into an inverting TL074 section round the bias, Rf || Cf, 1k to the ADC."""
    name, u, sec, rf, cf, bias = circuit.CV_CHANNELS[i]
    nin, nout = f"IN_{name}", f"OA_{name}"
    amp = amp_unit(pg, u, sec, ox, oy, supply=(sec == 1))
    a_in = two(pg, find(P, "R", f"CV_{name}", nin), ox - 90, oy - 10)
    _, k = feedback(pg, amp, sec, find(P, "R", nin, nout), find(P, "C", nin, nout), ox, oy, nin, nout, a_in)
    a_rs = two(pg, find(P, "R", nout, f"ADC_{name}"), ox + 100, oy)
    pg.wire([k, a_rs["1"]], nout)
    pg.stub_port(a_in["1"], f"CV_{name}", "IN", "left")
    pg.stub_port(amp[circuit.SECTION[sec][2]], bias, "IN", "left", length=30)
    pg.stub_port(a_rs["2"], f"ADC_{name}", "OUT", "right")
    gain = -circuit.value(rf) / 100e3
    pg.text(ox - 150, oy - 110, f"{jack_label(f'CV_{name}_F')}: gain {gain:.2f} round {bias}, 1k to {adc_pin(f'ADC_{name}')}",
            9)
    return amp


def output_stage(pg, P, name, u, sec, ox, oy, normal=None):
    """Rings' output stage: Seed AOUT -> Cin -> (Rdc to GND) -> Rin -> inverting TL074 with Rf || Cf ->
    1k -> jack; ODD also sums EVEN's lug through the normal resistor."""
    ac, nin, nout = f"AC_{name}", f"IN_{name}", f"OA_{name}"
    amp = amp_unit(pg, u, sec, ox, oy, supply=(sec == 1))
    a_c = two(pg, find(P, "C", f"AOUT_{name}", ac), ox - 200, oy - 10)
    a_dc = two(pg, find(P, "R", ac, "GND"), ox - 150, oy + 30, 270)
    a_in = two(pg, find(P, "R", ac, nin), ox - 90, oy - 10)
    node = (ox - 150, oy - 10)
    pg.wire([a_c["2"], node], ac)
    pg.wire([node, a_in["1"]], ac)
    pg.wire([node, a_dc["1"]], ac)
    pg.stub_gnd(a_dc["2"])
    corner, k = feedback(pg, amp, sec, find(P, "R", nin, nout), find(P, "C", nin, nout), ox, oy, nin, nout, a_in)
    a_rs = two(pg, find(P, "R", nout, name), ox + 100, oy)
    pg.wire([k, a_rs["1"]], nout)
    pg.stub_gnd(amp[circuit.SECTION[sec][2]], "down", 10)
    pg.stub_port(a_c["1"], f"AOUT_{name}", "IN", "left")
    pg.stub_port(a_rs["2"], name, "OUT", "right")
    if normal:
        a_n = two(pg, normal, ox - 90, oy - 90)
        pg.wire([a_n["2"], corner], nin)
        pg.stub_port(a_n["1"], normal.nets["1"], "IN", "left")
    return amp


def clamps(pg, P, upper, lower, x, top, node_net, rail):
    """Two diodes holding node_net between GND and rail: upper's anode on the node and cathode up to the
    rail, lower's cathode on the node and anode to GND (the library symbol: pin 1 = cathode)."""
    d1 = pg.place(upper, dev_of(P[upper]), x, top + 20, 270, *V_TXT)
    d2 = pg.place(lower, dev_of(P[lower]), x, top + 80, 270, *V_TXT)
    node = (x, top + 50)
    pg.wire([d1["2"], node], node_net)
    pg.wire([node, d2["1"]], node_net)
    pg.wire([node, (x - 20, top + 50)], node_net)
    pg.port(x - 20, top + 50, node_net, "IN", "left")
    pg.wire([d1["1"], (x, top - 10), (x - 20, top - 10)], rail)
    pg.port(x - 20, top - 10, rail, "IN", "left")
    pg.stub_gnd(d2["2"])


def divider(pg, P, ra, rb, c, x, top, out_net, label):
    """3V3A -> ra -> node -> rb -> GND, node decoupled by c; the node leaves as out_net (Plaitsy's)."""
    a = two(pg, P[ra], x, top + 20, 270)
    b = two(pg, P[rb], x, top + 80, 270)
    cc = pg.place(c, c_dev(P[c].value), x + 40, top + 80, 270, des=(8, -2, "LEFT_BOTTOM"),
                  value_at=(8, 8, "LEFT_BOTTOM"))
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


def decoupling_pair(pg, P, cp, cn, x, top):
    a = two(pg, P[cp], x, top + 20, 270)
    b = two(pg, P[cn], x, top + 80, 270)
    node = (x, top + 50)
    pg.wire([a["2"], node], "GND")
    pg.wire([node, b["1"]], "GND")
    pg.wire([node, (x - 15, top + 50)], "GND")
    pg.gnd(x - 15, top + 50, 270)
    pg.wire([a["1"], (x, top - 10), (x - 20, top - 10)], "+12V")
    pg.port(x - 20, top - 10, "+12V", "IN", "left")
    pg.wire([b["2"], (x, top + 120), (x - 20, top + 120)], "-12V")
    pg.port(x - 20, top + 120, "-12V", "IN", "left")


# Nets that leave the Seed (the rest come in) and nets the main board sends up the headers
SEED_IN = {"+12V", "-12V", "IN", "STRUM", "MUX_OUT", "BTN_POLY", "BTN_MODEL", "POT_FREQUENCY", "POT_STRUCTURE"}
TO_FACEPLATE = {"3V3A", "PROBE", "ODD", "EVEN", "MUX_S0", "MUX_S1", "MUX_S2", "BTN_LED_POLY", "BTN_LED_MODEL",
                "LED_POLY_R", "LED_POLY_G", "LED_MODEL_R", "LED_MODEL_G"}


def headers(pg, P, x0, y, dx, side):
    """The board-to-board headers, every pin a port (GND a flag)."""
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        r = ref if side == "main" else circuit.fb_ref(ref)
        x = x0 + k * dx
        h = pg.place(r, kind, x, y, des=(-10, -len(pins) * 5 - 10, "LEFT_BOTTOM"), name=False)
        for num, net in P[r].nets.items():
            if net == "GND":
                pg.stub_gnd(h[num], "left", 15)
            elif net in ("GND_F", "GND_D_F"):
                pg.stub_flag(h[num], net, "left", 15)
            else:
                out = (net in TO_FACEPLATE) == (side == "main")
                pg.stub_port(h[num], net, "OUT" if out else "IN", "left")


# ------------------------------------------------------------------ pages
def seed_block(pg, x, y):
    u2 = pg.place("U2", "SEED", x, y, des=(-80, -154, "LEFT_BOTTOM"), name=False)
    left = {str(k) for k in range(1, 21)} | {p for p in circuit.SEED if p[:2] in ("J5", "J1")}
    for pin, (name, net) in circuit.SEED.items():
        if not net:
            continue
        side = "left" if pin in left else "right"
        if net == "GND":
            pg.stub_gnd(u2[pin], side, 15)
        else:
            pg.stub_port(u2[pin], net, "IN" if net in SEED_IN or net.startswith("ADC_") else "OUT", side)
    return u2


def main_page_1(pr, P, count):
    pg = MPage(pr, "Main board 1: Seed, CV inputs", 1, count, True)
    seed_block(pg, 270, Y(270))
    for k, line in enumerate((
            "Daisy Seed on the seed_power_opamps breakout, 2.54 mm sockets on this board.",
            "IN arrives through the breakout's J5 input stage (AIN1); its J4 output op-amps",
            "stay fitted and unused: ODD / EVEN leave from Seed pins 18 / 19 (main board 2).",
            "Free pins: D8, D10-D13, A7, A8, D29, D30, AIN2, VIN.")):
        pg.text(40, Y(450 + 16 * k), line, 10)

    pg.text(540, Y(40), "CV inputs (Plaitsy's): 100k into a TL074 inverting stage round a bias from 3V3A, 1n across "
                        "Rf, 1k into the ADC. Wide channels: 13k round BIAS_A, +-12 V -> 3.22..0.10 V; "
                        "V/OCT: 33k round BIAS_V, -2.9..+7.1 V, BAT85 clamps", 10)
    for i in range(len(circuit.CV_CHANNELS)):
        col, row = divmod(i, 3)
        cv_stage(pg, P, i, 800 + col * 540, Y(175 + row * 175))

    pg.text(540, Y(675), "Bias: BIAS_A 1.467 V (15k / 12k) for the wide channels, BIAS_V 1.768 V (13k / 15k) "
                         "for V/OCT", 10)
    divider(pg, P, "R40", "R41", "C27", 620, Y(750), "BIAS_A", "BIAS A")
    divider(pg, P, "R42", "R43", "C28", 780, Y(750), "BIAS_V", "BIAS V")
    pg.text(930, Y(710), "V/OCT clamps (BAT85)", 10)
    clamps(pg, P, "D3", "D4", 990, Y(750), "ADC_VOCT", "3V3A")
    pg.text(1130, Y(710), "Supply decoupling at U3, U4", 10)
    for k, (cp, cn) in enumerate((("C33", "C34"), ("C35", "C36"))):
        decoupling_pair(pg, P, cp, cn, 1200 + k * 100, Y(750))

    pg.text(40, Y(1060), "Net ports with the same name connect across the main board's two pages; CV_*, PROBE, "
                         "STRUM_IN, IN, ODD, EVEN, TN_EVEN, POT_*, MUX_*, BTN_*, LED_*", 9)
    pg.text(40, Y(1076), "and 3V3A are header pins to the faceplate (main board 2). GND is one net: AGND (pin 20), "
                         "DGND (pin 40) and the breakout's GND pins.", 9)
    return pg


def main_page_2(pr, P, count):
    pg = MPage(pr, "Main board 2: outputs, STRUM, probe, headers", 2, count, True)
    o = circuit.OUT_STAGE
    pg.text(60, Y(40), f"ODD / EVEN: Rings' output stage with its resistors x2.1 (Seed AOUT -> {o['Cin']} -> "
                       f"{o['Rdc']} to GND / Rin {o['Rin']} -> {o['Rf']} || {o['Cf']} -> 1k), gain -5; "
                       "an unpatched EVEN jack's lug feeds EVEN into ODD through 100k", 10)
    pg.text(60, Y(56), "Rin (R45, R49) is fitted after measuring the Seed's full-scale output: Rin = 100k x V_fs / "
                       "9.8 V (20k for 1.8 V, docs/design.md)", 10)
    normal = find(P, "R", "TN_EVEN", "IN_ODD")
    for k, (name, u, sec) in enumerate(circuit.OUTPUTS):
        ox, oy = 420 + k * 640, Y(230)
        output_stage(pg, P, name, u, sec, ox, oy, normal if name == "ODD" else None)
        pg.text(ox - 240, oy - 125, f"{name}: Seed {'AOUT1 (pin 18)' if k == 0 else 'AOUT2 (pin 19)'} -> "
                                    f"{u} section {sec} -> {name} jack", 9)

    # STRUM: Marblesy's clock input
    x0, y = 90, Y(560)
    pg.text(60, Y(440), "STRUM: Rings' 2N3904 (a gate or the probe pulls D9 low), 10k pull-up; "
                        "the 1N4148 keeps a negative input off the base-emitter junction", 10)
    a = two(pg, find(P, "R", "STRUM_IN", "B_STRUM"), x0 + 40, y)
    q = pg.place("Q1", "NPN", x0 + 120, y, des=(14, -8, "LEFT_BOTTOM"), value_at=(14, 2, "LEFT_BOTTOM"))
    d = pg.place("D5", dev_of(P["D5"]), x0 + 80, y + 50, 270, *V_TXT)
    pu = two(pg, find(P, "R", "3V3D", "STRUM"), x0 + 130, y - 60, 270)
    b, c = (x0 + 80, y), (x0 + 130, y - 30)
    pg.stub_port(a["1"], "STRUM_IN", "IN", "left")
    pg.wire([a["2"], b], "B_STRUM")
    pg.wire([b, q["B"]], "B_STRUM")
    pg.wire([b, d["1"]], "B_STRUM")          # cathode up to the base
    pg.stub_gnd(d["2"])
    pg.stub_gnd(q["E"])
    pg.wire([q["C"], c], "STRUM")
    pg.wire([pu["2"], c], "STRUM")
    pg.wire([c, (x0 + 170, c[1])], "STRUM")
    pg.port(x0 + 170, c[1], "STRUM", "OUT", "right")
    pg.wire([pu["1"], (x0 + 130, y - 90), (x0 + 110, y - 90)], "3V3D")
    pg.port(x0 + 110, y - 90, "3V3D", "IN", "left")

    pg.text(480, Y(470), "Probe (D14), clamped at the Seed pin (Rings: BAT54S)", 10)
    clamps(pg, P, "D6", "D7", 560, Y(510), "PROBE", "3V3D")

    pg.text(900, Y(440), "LEDs: Seed GPIO -> resistor -> header; the faceplate LEDs return to GND_D_F", 10)
    led_nets = ("BTN_LED_POLY", "BTN_LED_MODEL", "LED_POLY_R", "LED_POLY_G", "LED_MODEL_R", "LED_MODEL_G")
    for k, net in enumerate(led_nets):
        r = two(pg, find(P, "R", f"{net}_IO", net), 1100, Y(480 + 36 * k))
        pg.stub_port(r["1"], f"{net}_IO", "IN", "left")
        pg.stub_port(r["2"], net, "OUT", "right")
    pg.text(1240, Y(500), f"{circuit.LED_R['button']} R: Thonk LED buttons ({circuit.BUTTON_COLOUR})", 9)
    pg.text(1240, Y(572), f"{circuit.LED_R['bicolour']} R: 3 mm red / green bicolour", 9)

    pg.text(60, Y(770), "Board-to-board headers (female sockets on this board, pin 1 at the top)", 10)
    headers(pg, P, 170, Y(870), 200, "main")
    return pg


def faceplate_page(pr, P, count):
    pg = MPage(pr, "Faceplate: panel parts, normals, mux", 1, count, False)
    inputs = {"cv in", "cv in, FM", "cv in, pitch", "trigger in", "audio in"}
    pg.text(60, Y(40), "Jacks (Thonkiconn): sleeves to GND_F; switch lugs grounded or to their normals (below); "
                       "ODD's lug open", 10)
    for i, (ref, label, role, tip, lug) in enumerate(circuit.JACKS):
        col, row = divmod(i, 5)
        jx, jy = 120 + col * 370, Y(115 + row * 95)
        j = pg.place(ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
        pg.text(jx - 25, jy + 30, label, 9)
        s = j["1"]
        pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND_F")
        pg.flag(s[0] + 20, s[1] - 20, 90, "GND_F")
        if lug == "GND_F":
            pg.stub_flag(j["2"], "GND_F", "right", 20)
        elif lug:
            pg.stub_port(j["2"], lug, "OUT", "right")
        x, yt = j["3"]
        pg.wire([(x, yt), (x + 130, yt)], tip)
        pg.port(x + 130, yt, tip, "OUT" if role in inputs else "IN", "right")

    # the lug networks
    pg.text(60, Y(600), "Jack normals: what an unpatched input reads (Rings' scheme, docs/design.md)", 10)
    notes = {"R1": "FREQUENCY CV: 6k8 to GND_F divides BIAS_A through the stage's 100k: +0.093 V, so the "
                   "attenuverter is a +-1 semitone fine tune",
             "R2": "STRUM: the probe through 100k; the 2N3904 follows it",
             "R3": "V/OCT: the probe through 470k; the stage sees the tip move 0.58 V",
             "R4": "IN: the probe through 1M, 43k to GND_F, so its level at the tip does not depend on "
                   "the breakout's input"}
    for k, (ref, value, a, b) in enumerate(circuit.LUG_PARTS[:4]):
        y = Y(650 + 45 * k)
        r = two(pg, P[ref], 260, y)
        if a == "TN_IN_F":                     # node -> 1M to the probe, 43k down to GND_F
            r5 = P["R5"]
            assert r5.nets == {"1": "TN_IN_F", "2": "GND_F"}
            node = (215, y)
            pg.wire([(195, y), node], a)
            pg.port(195, y, a, "IN", "left")
            pg.wire([node, r["1"]], a)
            pg.wire([node, (215, y + 20)], a)
            r5p = two(pg, r5, 215, y + 40, 270, txt=((-28, -2, "LEFT_BOTTOM"), (-36, 8, "LEFT_BOTTOM")))
            pg.stub_flag(r5p["2"], "GND_F", "down", 10)
        else:
            pg.stub_port(r["1"], a, "IN", "left")
        if b == "GND_F":
            pg.stub_flag(r["2"], b, "right", 15)
        else:
            pg.stub_port(r["2"], b, "IN", "right")
        pg.text(400, y + 4, notes[ref], 9)

    # pots and the mux
    pg.text(840, Y(40), "Pots (Alpha 9 mm B10k): FREQUENCY and STRUCTURE straight to the Seed (A6, A9), "
                        "the other eight through the 74HC4051", 10)
    for i, (ref, label, size) in enumerate(circuit.POTS):
        col, row = i % 4, i // 4
        px, py = 990 + col * 200, Y(115 + row * 110)
        p = pg.place(ref, "POT", px, py, des=(8, -22, "LEFT_BOTTOM"), value_at=(8, -12, "LEFT_BOTTOM"))
        where = f"Y{circuit.MUX_CHANNEL[ref]}" if ref in circuit.MUX_CHANNEL else "to the Seed"
        pg.text(px - 60, py + 58, f"{label} ({where})", 8)
        nets = P[ref].nets
        pg.stub_port(p["3"], nets["3"], "IN", "left")
        pg.stub_flag(p["1"], "GND_F", "right", 15)
        pg.wire([p["4"], (p["4"][0] - 10, p["4"][1]), (p["4"][0] - 10, p["4"][1] + 15), (p["5"][0] + 10, p["5"][1] + 15),
                 (p["5"][0] + 10, p["5"][1]), p["5"]], "GND_F")
        pg.wire([(p["5"][0] + 10, p["5"][1] + 15), (p["5"][0] + 10, p["5"][1] + 25)], "GND_F")
        pg.flag(p["5"][0] + 10, p["5"][1] + 25, 0, "GND_F")
        w = p["2"]
        pg.wire([w, (w[0], w[1] - 15), (w[0] - 20, w[1] - 15)], nets["2"])
        pg.port(w[0] - 20, w[1] - 15, nets["2"], "OUT", "left")

    ux, uy = 1260, Y(500)
    pg.text(1060, Y(430), "Pot mux: Y0..Y7 = the channel table in circuit.py (MUX_CHANNEL)", 10)
    mux = pg.place("U1", "MUX", ux, uy, des=(-50, -52, "LEFT_BOTTOM"), value_at=(-50, 58, "LEFT_BOTTOM"))
    nets = P["U1"].nets
    gnd_pins = []
    for row, num, name in ee.MUX_LEFT:
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
    cx = 1580
    c1 = two(pg, P["C1"], cx, Y(510), 270)
    pg.wire([c1["1"], (cx, Y(480)), (cx - 20, Y(480))], "3V3A_F")
    pg.port(cx - 20, Y(480), "3V3A_F", "IN", "left")
    pg.stub_flag(c1["2"], "GND_F")
    pg.text(cx - 40, Y(560), "C1 at U1 pin 16", 8)

    # LEDs and buttons
    pg.text(840, Y(620), "LEDs: 3 mm red / green bicolour, common cathode to GND_D_F (green / yellow / red as on Rings)",
            10)
    for k, (ref, label, name) in enumerate(circuit.LEDS):
        lx, ly = 1010 + k * 330, Y(680)
        led = pg.place(ref, "LED_RG", lx, ly, des=(-15, -24, "LEFT_BOTTOM"), name=False)
        pg.text(lx - 40, ly + 30, label, 8)
        nets = P[ref].nets
        pg.stub_flag(led["2"], "GND_D_F", "right", 15)
        pg.stub_port(led["1"], nets["1"], "IN", "left")
        pg.stub_port(led["3"], nets["3"], "IN", "left")
    pg.text(840, Y(760), f"Buttons: Thonk low-profile LED buttons ({circuit.BUTTON_COLOUR}), contacts 1+2 / 3+4 "
                         "(Seed pull-ups), LED on pins 5 / 6 from the main board's resistor", 10)
    for k, (ref, label, name) in enumerate(circuit.BUTTONS):
        bx, by = 1010 + k * 380, Y(840)
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

    pg.text(60, Y(900), "Headers to the main board (male pins here, pin 1 at the top)", 10)
    headers(pg, P, 170, Y(990), 200, "face")
    return pg


# ------------------------------------------------------------------ checks
def page_check(pg, parts):
    """check() on the part of the netlist this page draws."""
    drawn = {(c["ref"], num) for c in pg.comps if c["ref"] for num in c["pins"]}
    sub = []
    for p in parts:
        nets = {pid: n for pid, n in p.nets.items() if (p.ref, pid) in drawn}
        if nets:
            sub.append(circuit.Part(p.ref, p.kind, p.value, nets))
    return check(pg, sub, lambda part, pid: pid)


def coverage(pages, parts):
    """Every part drawn, every netlist pin drawn exactly once on its board's pages."""
    seen = collections.Counter((c["ref"], num) for pg in pages for c in pg.comps if c["ref"] for num in c["pins"])
    placed = {c["ref"] for pg in pages for c in pg.comps if c["ref"]}
    problems = [f"{p.ref} not drawn" for p in parts if p.ref not in placed]
    for p in parts:
        for pid in p.nets:
            if seen[(p.ref, pid)] != 1:
                problems.append(f"{p.ref}.{pid} drawn {seen[(p.ref, pid)]} times")
    return problems


def netlist_pins(pr, parts, main):
    """Every netlist pin must exist on its device's symbol, and the device must exist."""
    problems = []
    for p in parts:
        key = dev_of(p, main)
        if key not in pr.devices:
            problems.append(f"{p.ref}: no device {key}")
            continue
        pins = {q["num"] for q in pr.symgeo[pr.sym_of(key)]["pins"]}
        problems += [f"{p.ref}.{pid} is not a pin of {key}" for pid in p.nets if pid not in pins]
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
    """Parse the written project: every schematic component's Device, Symbol and Footprint must be in it."""
    with ee.zipfile.ZipFile(path) as z:
        docs = ee.parse(z.read(f"{NAME}.epru").decode("utf-8").split("\n"))
    problems = []
    for u, d in docs.items():
        if d["docType"] == "SCH_PAGE":
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p["key"] in ("Device", "Symbol", "Footprint") and p["value"] \
                        and p["value"] not in docs:
                    problems.append(f"{meta(d)['title']}: {p['key']} {p['value']} missing")
    return problems, collections.Counter(d["docType"] for d in docs.values())


def slug(title):
    return "-".join(re.findall(r"[a-z0-9]+", title.split(":")[0].lower()))


def main():
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    pr = MProject()
    bad = netlist_pins(pr, mb, True) + netlist_pins(pr, fb, False)
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    mpages = [main_page_1(pr, PM, 2), main_page_2(pr, PM, 2)]
    fpages = [faceplate_page(pr, PF, 1)]
    bad += coverage(mpages, mb) + coverage(fpages, fb)
    for pg, parts in [(p, mb) for p in mpages] + [(p, fb) for p in fpages]:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in mpages + fpages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    pr.write([(f"{NAME} Main", mpages, None), (f"{NAME} Faceplate", fpages, None)], OUT)
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in mpages + fpages:
        name = slug(pg.title) if pg.main else "faceplate"
        render(pr, pg, PREVIEW.format(name))
    n = sum(1 for pg in mpages + fpages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(mpages) + len(fpages)} pages, "
          f"{len(bad)} schematic problems; {len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
