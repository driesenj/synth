"""Offset as an EasyEDA Pro project (.epro2): the schematic of its one
board. PCB placement and the panel PCB follow in their own step (pcb.py,
panel_pcb.py, as for Marblesy, the mixer and Side FXy).

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the
file format, the connectivity check and the previews, the way the mixer
and Side FXy do. Library parts come from two caches of your MorrisSynth
export: plaitsy/hardware/easyeda/morrissynth-parts.epru (TL074ACN symbol,
WQP518MA jack, PTV09A pot symbol, LR1F resistors, FG28 capacitors, 1N5819,
net ports, ground flag, sheet frame) and
stereo-mixer/hardware/easyeda/stereo-mixer-parts.epru (LR1F 10R, the
178MU0033 10 uF, the 2x8 box header). Drawn or generated here, in the same
style and with real pin numbers:

  footprints  DIP-14 on the 7.62 mm row pitch, the Alpha 9 mm pot (the
              mixer's), TO-92, a 3 mm 2-lead LED, the Dailywell 2MS1 sub-mini
              toggle (2.54 mm pitch, from Dailywell's 2MS sheet), standing
              resistors
  symbols     LM4040 5.0 V (Marblesy's, relabelled), the 2-lead bicolour LED
              (two LEDs back to back), the SPDT toggle

Pages: one per channel (input inverters, the pots, the RANGE toggle, the
summer with its output and LED, the cascade inverter), and one for the
references, the +1 V normal, power and decoupling. Every block ends in net
ports; ports with the same name connect across the pages.

Run from attenuverter/hardware/tools:  python easyeda_export.py
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

_spec = importlib.util.spec_from_file_location("offset_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)
SECTION = circuit.SECTION
UNIT = {"A": 1, "B": 2, "C": 3, "D": 4}          # TL074 symbol units; unit 1 carries the supply pins

NAME = "Offset"
OUT = os.path.join(HERE, "..", "easyeda", "Offset.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "offset-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil

# Library devices used as they are (uuids from the two caches)
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0
    "R10k": "a9cc8fbe474242dc9110194515734c75",      # LR1F10K
    "R10R": "94e97e59e04b421d92158c6257818225",      # LR1F10R
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00
    "C10u": "21e4ec8defc34a489f66b07134d13cd6",      # 178MU0033, 10 uF 35 V
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN (its symbol; footprint replaced below)
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA (Thonkiconn)
    "POT": "be9d2c8f5f814271a402f956f18b56f9",       # PTV09A-4025F-B103 (its symbol)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819 (1 = cathode)
    "HDR16": "bbe47e9fd91b42bbaf0d36b9504a3a5e",     # DC3-2.54-16PAS, 2x8 box header
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "2k2": ("LR1F2K2", "2.2kΩ"), "39k": ("LR1F39K", "39kΩ")}
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
    f = Footprint("TO-92-INLINE-P2.54", "Q?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.line(-2.6, -1.3, 2.6, -1.3)
    f.circle(0, 0, 2.6)
    return f


def fp_led2():
    """3 mm LED, 2 leads at 2.54 mm (Marblesy's), pad 1 square. For the bicolour LED pad 1 is the lead that
    lights green when it is positive."""
    f = Footprint("LED-3MM-2P", "D?")
    f.pad(1, -1.27, 0, 0.8, 1.5, square=True)
    f.pad(2, 1.27, 0, 0.8, 1.5)
    f.circle(0, 0, 1.6)
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


def fp_toggle():
    """Dailywell 2MS1 sub-mini toggle, PC terminals (M2): three pins in a column at 2.54 mm (Dailywell's 2MS
    sheet), pin 2 (common) under the 6 mm bushing at the origin, pin 1 at +y. Body 8.13 x 9.40 mm."""
    f = Footprint("SW-TOGGLE-DAILYWELL-2MS1-PC", "SW?")
    for num, y in ((1, 2.54), (2, 0.0), (3, -2.54)):
        f.pad(num, 0, y, 1.1, 1.9, square=(num == 1))
    f.rect(-4.07, -4.7, 4.07, 4.7)
    f.circle(0, 0, 3.0)
    return f


# ------------------------------------------------------------------ symbols
def lm4040_symbol():
    """Marblesy's LM4040 drawing: a zener-style reference, 1 = cathode (the positive end), 2 = anode, and the
    TO-92's third lead as an NC pin so every pad has a pin."""
    s = Symbol("LM4040-5.0", "LM4040_5V0.1", "D?", [NAME])
    s.poly([(-20, 0), (-6, 0)])
    s.poly([(6, -7), (-6, 0), (6, 7), (6, -7)], closed=True)
    s.poly([(-6, -7), (-6, 7)])
    s.poly([(-6, -7), (-9, -9)])
    s.poly([(-6, 7), (-3, 9)])
    s.poly([(6, 0), (20, 0)])
    s.text(-14, -8, "5.0V", 6)
    s.pin("1", "K", -20, 0, 0)
    s.pin("2", "A", 20, 0, 180)
    s.pin("3", "NC", 0, 17, 90)
    return s


def led_bi_symbol():
    """2-lead bicolour LED: two LEDs back to back between pin 1 (left) and pin 2 (right). The upper one,
    lit by current from 1 to 2, is green; the lower one red."""
    s = Symbol("LED 3mm bicolour R/G 2-lead", "LEDBI2.1", "D?", [NAME])
    s.poly([(-10, -6), (-10, 6)])
    s.poly([(10, -6), (10, 6)])
    s.poly([(-10, -6), (-4, -6)])                                   # green: anode left
    s.poly([(-4, -10), (-4, -2), (4, -6), (-4, -10)], closed=True)
    s.poly([(4, -10), (4, -2)])
    s.poly([(4, -6), (10, -6)])
    s.poly([(-10, 6), (-4, 6)])                                     # red: anode right
    s.poly([(4, 2), (4, 10), (-4, 6), (4, 2)], closed=True)
    s.poly([(-4, 2), (-4, 10)])
    s.poly([(4, 6), (10, 6)])
    s.text(-2, -12, "G", 6)
    s.text(-2, 19, "R", 6)
    s.pin("1", "G+", -20, 0, 0)
    s.pin("2", "R+", 20, 0, 180)
    return s


def toggle_symbol():
    """SPDT toggle: common 2 on the left, throws 1 (upper) and 3 (lower) on the right, the blade drawn on 3
    (lever up joins 2-3 on the Dailywell 2MS1 as mounted here)."""
    s = Symbol("Toggle SPDT ON-ON", "TOGSPDT.1", "SW?", [NAME])
    s.poly([(-10, 0), (-6, 0)])
    s.poly([(-6, 0), (6, 10)])                      # the blade, resting on throw 3
    s.poly([(10, -10), (4, -10)])
    s.poly([(10, 10), (4, 10)])
    s.poly([(-7, -1), (-5, -1), (-5, 1), (-7, 1), (-7, -1)], closed=True)    # the pivot
    s.text(-12, -14, "up: 2-3", 6)
    s.pin("2", "COM", -20, 0, 0)
    s.pin("1", "1", 20, -10, 180)
    s.pin("3", "3", 20, 10, 180)
    return s


# ------------------------------------------------------------------ project
STANDING = ["R1k", "R10k", "R10R"] + ["R" + v for v in R_NEW]   # every resistor stands up (dev key + "V")


class MPage(Page):
    page_count = "4"

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
        vals = [("Symbol", sym), ("@Project Name", "Offset"), ("@Page Count", self.page_count),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", "Offset"),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V0.1"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", W), ("Height", H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", "Offset"),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), attr_payload(d.zi(), cid, k, v))


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
        fps = {"RV": self._footprint(fp_res_vertical()), "DIP14": self._footprint(fp_dip(14, "DIP-14-W7.62-P2.54")),
               "TO92": self._footprint(fp_to92()), "LED2": self._footprint(fp_led2()),
               "POT": self._footprint(fp_alpha_pot()), "TOGGLE": self._footprint(fp_toggle())}
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
        new = [
            ("LM4040", lm4040_symbol(), "LM4040-5.0", "D?", fps["TO92"],
             "Precision shunt reference 5.000 V, TO-92 (LM4040AIZ-5.0 / BIZ-5.0): 1 cathode, 2 anode, 3 NC"),
            ("LED_BI", led_bi_symbol(), "LED 3mm bicolour R/G 2-lead", "D?", fps["LED2"],
             "3 mm bicolour LED, red/green, two leads back to back: current from pad 1 to pad 2 lights green. "
             "Check which lead does that on the part bought and fit it to the square pad"),
            ("TOGGLE_SPDT", toggle_symbol(), "Dailywell 2MS1T1B1M2QES", "SW?", fps["TOGGLE"],
             "Sub-mini toggle SPDT ON-ON, PC terminals at 2.54 mm, 6 mm bushing (Thonk). Lever towards pin 1 "
             "joins 2-3, towards pin 3 joins 2-1 (Dailywell's table; ring one out before soldering)"),
        ]
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
            self._device(key, title, attrs)

    def write(self, boards, path):
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
        lines += Doc("CONFIG", "CONFIG").lines({"defaultSheet": ""})
        lines += next(d for d in self.lib.values() if d["docType"] == "BLOB")["lines"]   # one BLOB doc
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Offset: three offset attenuverters, OFFSET +-5 / +-10 V per channel, inputs "
                                  "normalled down (IN 1 to +1 V), unpatched outputs add into the next channel. "
                                  "3x TL074, two LM4040-5.0. One PCB, 10HP.",
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
        return {"100n": "C100n"}.get(part.value, "C" + part.value)
    if part.kind == "POT":
        return "POT" + part.value
    return {"CP": "C10u", "TL074": "TL074N"}.get(part.kind, part.kind)


# ---------------------------------------------------------------- drawing helpers
def hpart(pg, part, x1, y, left_pin="1"):
    """Two-pin part drawn horizontally with `left_pin` at (x1, y), the other pin at (x1 + 40, y)."""
    rot = 0 if left_pin == "1" else 180
    return pg.place(part.ref, dev_of(part), x1 + 20, y, rot, des=H_TXT[0], value_at=H_TXT[1])


def vpart(pg, part, x, y1, top_pin="1"):
    """Two-pin part drawn vertically with `top_pin` at (x, y1), the other pin at (x, y1 + 40)."""
    rot = 270 if top_pin == "1" else 90
    return pg.place(part.ref, dev_of(part), x, y1 + 20, rot, *V_TXT)


def supply(pg, amp, sec):
    if UNIT[sec] == 1:   # this unit carries the supply pins
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))


def inverting(pg, ref, sec, x, y, rf, cf=None):
    """TL074 section as an inverting stage (the mixer's drawing); summing junction at (x, y), feedback above.
    Returns the output node."""
    ox, oy = x + 55, y + 10
    amp = pg.place(ref, "TL074N", ox, oy, unit=UNIT[sec], des=(14, 30, "LEFT_BOTTOM"), name=False)
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
    pg.text(ox - 30, oy + 45, f"{ref} {sec}", 8)
    return (kx, oy)


def input_stage(pg, P, rin, rf, ref, sec, x, y, cf=None):
    """Net port -> rin -> inverting stage -> net port: rin's pin 1 at x, the junction at x + 60."""
    a = hpart(pg, P[rin], x, y)
    pg.stub_port(a["1"], P[rin].nets["1"], "IN", "left")
    pg.wire([a["2"], (x + 60, y)], P[rin].nets["2"])
    kn = inverting(pg, ref, sec, x + 60, y, P[rf], P[cf] if cf else None)
    pg.stub_port(kn, P[rf].nets["2"], "OUT", "right", 40)
    return kn


def jack_block(pg, part, jx, jy, tip_kind):
    """Thonkiconn: sleeve to GND, switch lug and tip to net ports (the mixer's drawing)."""
    j = pg.place(part.ref, "JACK", jx, jy, des=(-25, -22, "LEFT_BOTTOM"), name=False)
    pg.text(jx - 25, jy + 30, part.label, 10)
    s = j["1"]
    pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND")
    pg.gnd(s[0] + 20, s[1] - 20, 90)
    lug = part.nets.get("2")
    if lug:
        pg.stub_port(j["2"], lug, "OUT" if tip_kind == "IN" else "IN", "right")
    x, y = j["3"]
    pg.wire([(x, y), (x + 100, y)], part.nets["3"])
    pg.port(x + 100, y, part.nets["3"], tip_kind, "right")


def pot_block(pg, part, px, py):
    """Library pot symbol: CW end (3) and CCW end (1) to ports left and right, the wiper up to a port,
    lugs 4 / 5 joined to GND underneath (the mixer's drawing)."""
    p = pg.place(part.ref, dev_of(part), px, py, des=(8, -22, "LEFT_BOTTOM"), value_at=(8, -12, "LEFT_BOTTOM"))
    pg.text(px - 40, py + 36, part.label, 10)
    nets = part.nets
    pg.stub_port(p["3"], nets["3"], "IN", "left")
    pg.stub_port(p["1"], nets["1"], "IN", "right")
    pg.wire([p["4"], (p["4"][0] - 10, p["4"][1]), (p["4"][0] - 10, p["4"][1] + 15), (p["5"][0] + 10, p["5"][1] + 15),
             (p["5"][0] + 10, p["5"][1]), p["5"]], "GND")
    pg.wire([(p["5"][0] + 10, p["5"][1] + 15), (p["5"][0] + 10, p["5"][1] + 25)], "GND")
    pg.gnd(p["5"][0] + 10, p["5"][1] + 25, 0)
    w = p["2"]
    pg.wire([w, (w[0], w[1] - 15), (w[0] - 20, w[1] - 15)], nets["2"])
    pg.port(w[0] - 20, w[1] - 15, nets["2"], "OUT", "left")


def toggle_block(pg, part, x, y):
    s = pg.place(part.ref, "TOGGLE_SPDT", x, y, des=(-20, -24, "LEFT_BOTTOM"), value_at=(-20, 34, "LEFT_BOTTOM"))
    pg.text(x - 40, y + 50, part.label + ": lever up = 10V", 10)
    pg.stub_port(s["2"], part.nets["2"], "IN", "left")
    pg.stub_port(s["3"], part.nets["3"], "OUT", "right")


def summer_block(pg, P, k, x, y):
    """ATTEN, OFFSET (twice, the second through RANGE) and the cascade into SUM k; the C section with
    100k || 22p; 1k to OUT k and 2k2 to the bicolour LED."""
    r = 100 * k
    ins = [f"R{r + 5}", f"R{r + 6}", f"R{r + 13}"] + ([f"R{r + 10}"] if k > 1 else [])
    xb, xj = x + 60, x + 90                       # the input bus, the junction
    pts = []
    for i, ref in enumerate(ins):
        yi = y + 40 * i
        a = hpart(pg, P[ref], x, yi)
        pg.stub_port(a["1"], P[ref].nets["1"], "IN", "left")
        pg.wire([a["2"], (xb, yi)], f"SUM{k}")
        pts.append((xb, yi))
    for a, b in zip(pts, pts[1:]):
        pg.wire([a, b], f"SUM{k}")
    pg.wire([(xb, y), (xj, y)], f"SUM{k}")
    kn = inverting(pg, f"U{k}", "C", xj, y, P[f"R{r + 7}"], P[f"C{r + 1}"])
    ro = hpart(pg, P[f"R{r + 8}"], kn[0] + 20, kn[1])
    pg.wire([kn, ro["1"]], f"OA{k}")
    pg.stub_port(ro["2"], f"OUT{k}", "OUT", "right")
    rl = vpart(pg, P[f"R{r + 9}"], kn[0], kn[1] + 40)
    pg.wire([kn, rl["1"]], f"OA{k}")
    led = pg.place(f"D{k}", "LED_BI", kn[0], kn[1] + 120, 270, des=(16, 2, "LEFT_BOTTOM"),
                   value_at=(16, 12, "LEFT_BOTTOM"))
    pg.wire([rl["2"], led["1"]], f"LED{k}")
    pg.stub_gnd(led["2"], "down", 10)
    pg.text(kn[0] + 30, kn[1] + 175, f"LED {k}: green = OUT {k} positive", 8)


# ------------------------------------------------------------------ pages
def channel_page(pr, P, k):
    r = 100 * k
    pg = MPage(pr, f"Channel {k}", k)
    pg.text(40, Y(40), f"Channel {k}: OUT {k} = ATTEN {k} x IN {k} + OFFSET {k}"
                       + (f" (+ OUT {k - 1} while OUT {k - 1} is unpatched)" if k > 1 else ""), 12)
    nrm = "NORM (+1 V, page 4)" if k == 1 else f"IN {k - 1}"
    pg.text(40, Y(80), f"IN {k} unpatched takes {nrm} through the jack's switch lug. A and B make -IN and +IN, "
                       "so the ATTEN pot's ends are driven low-impedance; every stage inverts.", 10)
    # row 1: IN jack, A, B, the two pots
    y1 = Y(220)
    jack_block(pg, P[f"J{k}"], 90, y1, "OUT")
    pg.text(330, y1 - 120, "A: N = -IN", 10)
    input_stage(pg, P, f"R{r + 1}", f"R{r + 2}", f"U{k}", "A", 330, y1)
    pg.text(640, y1 - 120, "B: P = +IN", 10)
    input_stage(pg, P, f"R{r + 3}", f"R{r + 4}", f"U{k}", "B", 640, y1)
    pg.text(990, y1 - 120, "ATTEN: -1 (CCW) .. +1 (CW); OFFSET: -5 V .. +5 V", 10)
    pot_block(pg, P[f"RV{2 * k - 1}"], 1060, y1)
    pot_block(pg, P[f"RV{2 * k}"], 1360, y1)
    # row 2: summer, output, LED; OUT jack; RANGE
    y2 = Y(560)
    pg.text(330, y2 - 140, "C: summer; RANGE up adds a second 100k from the OFFSET wiper (+-10 V)", 10)
    summer_block(pg, P, k, 330, y2)
    jack_block(pg, P[f"J{circuit.CHANNELS + k}"], 900, y2, "IN")
    toggle_block(pg, P[f"SW{k}"], 1260, y2)
    # row 3: the cascade inverter, or the note on U3 D
    y3 = Y(900)
    if k < circuit.CHANNELS:
        pg.text(330, y3 - 120, f"D: OUT {k} unpatched -> -OUT {k} into channel {k + 1}'s summer "
                               "(patched: the lug opens, D gives 0 V)", 10)
        input_stage(pg, P, f"R{r + 11}", f"R{r + 12}", f"U{k}", "D", 330, y3)
    else:
        pg.text(330, y3 - 60, "U3 D: the +1 V normal follower, on page 4. OUT 3 has no channel after it.", 10)
    pg.text(40, Y(1100), "Resistors 1 % metal film, all standing. Net ports with the same name connect across the "
                         "pages; GND is one net.", 9)
    return pg


def reference_block(pg, P, x, top, plus):
    """+5 V: 1k from +12 V, LM4040 cathode on REF_P. -5 V: LM4040 cathode on GND, anode on REF_N, 1k to
    -12 V. A 100n across each."""
    if plus:
        rf, d, c, node, rail = P["R901"], "D4", P["C901"], "REF_P", "+12V"
        a = vpart(pg, rf, x, top)
        pg.stub_port(a["1"], rail, "IN", "left")
        n = (x, top + 50)
        pg.wire([a["2"], n], node)
        ref = pg.place(d, "LM4040", x, top + 80, 270, des=(10, 4, "LEFT_BOTTOM"), value_at=(10, 14, "LEFT_BOTTOM"))
        pg.wire([n, ref["1"]], node)
        pg.stub_gnd(ref["2"], "down", 10)
    else:
        rf, d, c, node, rail = P["R902"], "D5", P["C902"], "REF_N", "-12V"
        ref = pg.place(d, "LM4040", x, top + 20, 270, des=(10, 4, "LEFT_BOTTOM"), value_at=(10, 14, "LEFT_BOTTOM"))
        pg.stub_gnd(ref["1"], "up", 10)
        n = (x, top + 50)
        pg.wire([ref["2"], n], node)
        a = vpart(pg, rf, x, top + 60)
        pg.wire([n, a["1"]], node)
        pg.stub_port(a["2"], rail, "IN", "left")
    cp = vpart(pg, c, x + 60, top + 50, top_pin="1" if plus else "2")
    pg.wire([n, cp["1" if plus else "2"]], node)
    pg.stub_gnd(cp["2" if plus else "1"], "down", 10)
    pg.wire([n, (x - 40, n[1])], node)
    pg.port(x - 40, n[1], node, "OUT", "left")


def norm_block(pg, P, x, top):
    """39k / 10k from REF_P, buffered by U3 D: the +1 V normal for IN 1."""
    a = vpart(pg, P["R903"], x, top)
    pg.stub_port(a["1"], "REF_P", "IN", "left")
    n = (x, top + 50)
    pg.wire([a["2"], n], "NDIV")
    b = vpart(pg, P["R904"], x, top + 60)
    pg.wire([n, b["1"]], "NDIV")
    pg.stub_gnd(b["2"], "down", 10)
    xi = x + 60                                    # the follower's + input
    pg.wire([n, (xi, n[1])], "NDIV")
    ox, oy = xi + 40, n[1] - 10
    amp = pg.place("U3", "TL074N", ox, oy, unit=UNIT["D"], des=(-6, 32, "LEFT_BOTTOM"), name=False)
    out, inm, inp = SECTION["D"]
    node = (ox + 55, oy)
    pg.wire([amp[out], node], "NORM")
    pg.wire([node, (ox + 55, oy - 35), (ox - 55, oy - 35), (ox - 55, oy - 10), amp[inm]], "NORM")
    pg.wire([node, (ox + 95, oy)], "NORM")
    pg.port(ox + 95, oy, "NORM", "OUT", "right")
    pg.text(ox - 30, oy + 45, "U3 D", 8)


def power_block(pg, P, x0, t0):
    """16-pin header (red stripe = pin 1 = -12 V), a 1N5819 per rail (the -12 V cathode on the header),
    10R and 10 uF (the mixer's drawing)."""
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J7", "HDR16", xh, yh, des=(-30, -45, "LEFT_BOTTOM"), value_at=(-30, 52, "LEFT_BOTTOM"))
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
    for k, (port, d, r, c, rail) in enumerate((("P12_IN", "D6", "R905", "C903", "+12V"),
                                               ("N12_IN", "D7", "R906", "C904", "-12V"))):
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


def power_page(pr, P):
    pg = MPage(pr, "References, +1 V normal, power", 4)
    pg.text(40, Y(40), "OFFSET references: two LM4040-5.0 (1 = cathode). 1k feeds give 7 mA each; the three "
                       "OFFSET pots (B10k, REF_P to REF_N) take 3 mA of it", 12)
    pg.text(80, Y(110), "+5 V", 11)
    reference_block(pg, P, 160, Y(140), True)
    pg.text(380, Y(110), "-5 V", 11)
    reference_block(pg, P, 460, Y(140), False)
    pg.text(720, Y(110), "+1 V normal for IN 1: 39k / 10k from REF_P (1.02 V), buffered by U3 D", 11)
    norm_block(pg, P, 800, Y(160))
    pg.text(40, Y(440), "Power: 16-pin Eurorack header (red stripe = pin 1 = -12 V), a 1N5819 per rail: +12 V anode "
                        "on the header, -12 V cathode on the header", 12)
    power_block(pg, P, 80, 520)
    pg.text(900, Y(440), "Decoupling: a 100n pair per TL074, beside its supply pins", 12)
    for i, k in enumerate(circuit.CH):
        x, top = 980 + i * 140, Y(560)
        decoupling_pair(pg, P, f"C{903 + 2 * k}", f"C{904 + 2 * k}", x, top)
        pg.text(x + 8, top + 140, f"U{k}", 10)
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
    """Parse the written project: every component's Device, Symbol and Footprint must be in it."""
    with ee.zipfile.ZipFile(path) as z:
        docs = ee.parse(z.read(f"{NAME}.epru").decode("utf-8").split("\n"))
    problems = []
    for u, d in docs.items():
        if d["docType"] != "SCH_PAGE":
            continue
        for h, p in d["recs"]:
            if h["type"] == "ATTR" and p["key"] in ("Device", "Symbol", "Footprint") and p["value"] \
                    and p["value"] not in docs:
                problems.append(f"{meta(d)['title']}: {p['key']} {p['value']} missing")
    return problems, collections.Counter(d["docType"] for d in docs.values())


def main():
    pr = MProject()
    parts = circuit.all_parts()
    P = {p.ref: p for p in parts}
    pages = [channel_page(pr, P, k) for k in circuit.CH] + [power_page(pr, P)]
    bad = coverage(pages, parts)
    for pg in pages:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in pages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    pr.write([("Offset", pages, None)], OUT)
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in pages:
        render(pr, pg, PREVIEW.format(pg.title.split(",")[0].lower().replace(" ", "-")))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(pages)} pages, {len(bad)} schematic problems, "
          f"{len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
