"""S&H as an EasyEDA Pro project (.epro2): the schematic of its one board,
that board placed (pcb.py), and the panel as a second PCB (panel_pcb.py).

Copied from the Offset exporter (attenuverter/hardware/tools; its
footprints, project helpers and checks are copies here, not imports, so
work on one module can't break the other) and built on the Plaitsy
exporter for the file format, the connectivity check and the previews. Library parts come from two caches of your MorrisSynth
export: plaitsy/hardware/easyeda/morrissynth-parts.epru (TL074ACN symbol,
WQP518MA jack, PTV09A pot symbol, LR1F resistors, FG28 capacitors, 1N5819,
the 1N4148's DO-35 footprint, net ports, ground flag, sheet frame) and
stereo-mixer/hardware/easyeda/stereo-mixer-parts.epru (LR1F 10R, the
178MU0033 electrolytic, the 2x8 box header). Drawn or generated here, in the
same style and with real pin numbers:

  footprints  DIP-14 and DIP-8 on the 7.62 mm row pitch, the Alpha 9 mm pot,
              TO-92, a 3 mm 2-lead LED, standing resistors (all the Offset's),
              a 5 mm film capacitor
  symbols     TL072 (the library TL074 symbol's units 1-2, supply pins
              renumbered 8 / 4), NPN for the BC548 (1 C, 2 B, 3 E) and the
              2N3904 (1 E, 2 B, 3 C), the J113 N-JFET (1 D, 2 S, 3 G), a 3 mm
              LED; the 1N4148 takes the 1N5819 symbol (1 = cathode), as
              Plaitsy's BAT85 does

Pages: noise; clock and trigger; S&H, slew and gate; power. Every block
ends in net ports; ports with the same name connect across the pages.

Run from sample-hold/hardware/tools:  python easyeda_export.py
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
    spec = importlib.util.spec_from_file_location("sh_" + name, os.path.join(HERE, name + ".py"))
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
SUPPLY_PINS = {"TL074": ("4", "11"), "TL072": ("8", "4")}

NAME = "SampleHold"
TITLE = "S&H"
OUT = os.path.join(HERE, "..", "easyeda", "SampleHold.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "sample-hold-easyeda-{}.png")
MIL = 1 / 0.0254   # footprint units are mil

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
    "HDR16": "bbe47e9fd91b42bbaf0d36b9504a3a5e",     # DC3-2.54-16PAS, 2x8 box header
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "4k7": ("LR1F4K7", "4.7kΩ"), "680": ("LR1F680R", "680Ω"),
         "1M": ("LR1F1M0", "1MΩ"), "470k": ("LR1F470K", "470kΩ"), "20k": ("LR1F20K", "20kΩ"),
         "33k": ("LR1F33K", "33kΩ"), "22k": ("LR1F22K", "22kΩ"), "47k": ("LR1F47K", "47kΩ"),
         "2k": ("LR1F2K0", "2kΩ"), "51k": ("LR1F51K", "51kΩ")}
C_NEW = {"680p": ("FG28C0G1H681JNT00", "680pF"), "1n": ("FG28C0G1H102JNT00", "1nF"),
         "2n2": ("FG28C0G1H222JNT00", "2.2nF"), "5n6": ("FG28C0G1H562JNT00", "5.6nF")}
# film capacitors: the hold, slew and clock-timing caps and the noise coupling cap (MKI: foil)
C_FILM = {"100n": "100nF", "470n": "470nF", "1u": "1uF", "2u2": "2.2uF"}


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
    """A through-hole footprint in mm; written as an EasyEDA Pro FOOTPRINT doc (the Offset's).
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
    f = Footprint("TO-92-INLINE-P2.54", "Q?")
    for i in range(3):
        f.pad(i + 1, (i - 1) * 2.54, 0, 0.9, 1.6, square=(i == 0))
    f.line(-2.6, -1.3, 2.6, -1.3)
    f.circle(0, 0, 2.6)
    return f


def fp_led2():
    """3 mm LED, 2 leads at 2.54 mm (Marblesy's), pad 1 (square) = anode."""
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


def fp_film(width=5.5):
    """Box film capacitor, 5 mm lead pitch, 7.2 mm long (WIMA MKS2 and the like): 5.5 mm thick fits up to 1 uF
    63 V; the 2.2 uF gets a generous 8.5 mm."""
    f = Footprint(f"CAP-FILM-P5.08-7.2x{width}", "C?")
    f.pad(1, -2.54, 0, 0.8, 1.6, square=True)
    f.pad(2, 2.54, 0, 0.8, 1.6)
    f.rect(-3.6, -width / 2, 3.6, width / 2)
    return f


# ------------------------------------------------------------------ symbols
def npn_symbol(title, part_id, nums):
    """NPN in the library's style: base left, collector up, emitter down with the arrow. nums: pin numbers
    for B, C, E (they differ between the BC548 and the 2N3904)."""
    s = Symbol(title, part_id, "Q?", [NAME])
    s.poly([(-4, -9), (-4, 9)])                                # base bar
    s.poly([(-10, 0), (-4, 0)])
    s.poly([(-4, -4), (10, -10)])                              # collector
    s.poly([(-4, 4), (10, 10)])                                # emitter
    s.poly([(10, 10), (4.4, 10.3), (6.4, 5.7), (10, 10)], closed=True, fill="#000000")
    s.pin(nums["B"], "B", -20, 0, 0)
    s.pin(nums["C"], "C", 10, -20, 270)
    s.pin(nums["E"], "E", 10, 20, 90)
    return s


def jfet_symbol():
    """N-channel JFET as a horizontal switch: source left, drain right, the gate on top with its arrow into
    the channel. J113 TO-92: 1 = D, 2 = S, 3 = G."""
    s = Symbol("J113", "J113.1", "Q?", [NAME])
    s.poly([(-10, 0), (10, 0)])                                # channel
    s.poly([(-10, 6), (-6, 6), (-6, 0)])                       # source
    s.poly([(10, 6), (6, 6), (6, 0)])                          # drain
    s.poly([(0, -10), (0, -4)])                                # gate
    s.poly([(-2.5, -5), (2.5, -5), (0, -1), (-2.5, -5)], closed=True, fill="#000000")
    s.text(-9, 15, "S      D", 6)
    s.pin("2", "S", -20, 6, 0)
    s.pin("1", "D", 20, 6, 180)
    s.pin("3", "G", 0, -20, 270)
    return s


def led_symbol():
    """3 mm LED: anode (1) left, cathode (2) right."""
    s = Symbol("LED 3mm red", "LED3R.1", "D?", [NAME])
    s.poly([(-10, 0), (-6, 0)])
    s.poly([(-6, -6), (6, 0), (-6, 6), (-6, -6)], closed=True, fill="#FF0000")
    s.poly([(6, -6), (6, 6)])
    s.poly([(6, 0), (10, 0)])
    for x0 in (-2, 3):                                         # light arrows
        s.poly([(x0, -9), (x0 + 5, -14)])
        s.poly([(x0 + 5, -14), (x0 + 1, -13), (x0 + 4, -10), (x0 + 5, -14)], closed=True, fill="#FF0000")
    s.pin("1", "A", -20, 0, 0)
    s.pin("2", "K", 20, 0, 180)
    return s


def tl072_symbol_lines(lib_doc):
    """The library TL074ACN symbol cut to its first two units, supply pins renumbered 4 -> 8 and 11 -> 4:
    a TL072 in exactly the TL074's drawing."""
    keep = {"TL074ACN.1": "TL072.1", "TL074ACN.2": "TL072.2"}
    d = Doc("SYMBOL")
    pins_of_unit1 = {h["id"] for h, p in lib_doc["recs"] if h["type"] == "PIN" and p["partId"] == "TL074ACN.1"}
    for h, p in lib_doc["recs"]:
        t = h["type"]
        if t in ("DOCHEAD", "META"):
            continue
        p = dict(p)
        if t == "PART":
            if h["id"] not in keep:
                continue
            d.add(t, keep[h["id"]], {**p, "title": keep[h["id"]]})
            continue
        if "partId" in p:
            if p["partId"] not in keep:
                continue
            p["partId"] = keep[p["partId"]]
        if t == "ATTR" and p.get("key") == "Symbol":
            p["value"] = "TL072"
        if t == "ATTR" and p.get("parentId") in pins_of_unit1 and p["key"] in ("Pin Number", "Pin Name"):
            p["value"] = {"4": "8", "11": "4"}.get(p["value"], p["value"])
        d.add(t, h["id"], p)
    return d.uuid, d.lines({"title": "TL072", "description": "", "tags": [NAME], "docType": 2,
                            "source": f"{new_uuid()}|{ee.USER['uuid']}"})


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
               "DIP8": self._footprint(fp_dip(8, "DIP-8-W7.62-P2.54")), "TO92": self._footprint(fp_to92()),
               "LED2": self._footprint(fp_led2()), "POT": self._footprint(fp_alpha_pot()),
               "FILM": self._footprint(fp_film()), "FILM_L": self._footprint(fp_film(8.5))}
        for val, value in C_FILM.items():
            a = dict(c100n)
            a.update({"Manufacturer Part": f"Film capacitor {value} 63V P5", "Value": value, "Supplier Part": "",
                      "Datasheet": "", "Tolerance": "±5%", "Temperature Coefficient": "",
                      "Footprint": fps["FILM_L" if val == "2u2" else "FILM"],
                      "LCSC Part Name": f"Film capacitor {value} 63V", "Manufacturer": "",
                      "Description": f"Polyester or polypropylene film capacitor {value} 63 V, 5 mm lead pitch "
                                     "(WIMA MKS2 or similar)"})
            self._device("CF" + val, f"Film {value}", a, ["Capacitors", "Film Capacitors"])
        self._copy("C47u", "C10u", "Electrolytic 47uF 25V", ["Capacitors", "Aluminum Electrolytic Capacitors"],
                   **{"Manufacturer Part": "Electrolytic 47uF 25V", "Value": "47uF", "Supplier Part": "",
                      "Datasheet": "", "Description": "Aluminium electrolytic 47 uF 25 V radial, 5 mm can, "
                                                      "pin 2 = +"})
        d4148 = self.device_attrs("D4148LIB")
        self._copy("D4148", "D4148LIB", "1N4148", ["Diodes", "Switching Diodes"],
                   Symbol=self.device_attrs("D5819")["Symbol"], Datasheet="",
                   Description="Small-signal diode 1N4148, DO-35. Symbol pin 1 = cathode = the band = pad 1")
        assert d4148["Footprint"]
        for key in STANDING:                                      # each resistor again, standing up
            a = self.device_attrs(key)
            self._copy(key + "V", key, a["Manufacturer Part"], ["Resistors", "Through Hole Resistors"],
                       Footprint=fps["RV"])
        self._copy("TL074N", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        for value, mpn in (("B250k", "Alpha RD901F-40-15R1 B250K"), ("B100k", "Alpha RD901F-40-15R1 B100K"),
                           ("A1M", "Alpha RD901F-40-15R1 A1M")):
            self._copy("POT" + value, "POT", f"Alpha 9mm {value}", ["Potentiometers"], Footprint=fps["POT"],
                       Name="={Value}", Value=value, **{"Manufacturer Part": mpn, "Supplier Part": "",
                                                       "Datasheet": "",
                                                       "Description": f"Alpha 9 mm vertical pot {value}, T18 shaft "
                                                                      "(Thonk). Pin 3 = CW end, lugs 4 / 5"})
        su, lines = tl072_symbol_lines(self.lib[self.device_attrs("TL074")["Symbol"]])
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(su, lines)
        self._device("TL072N", "TL072", {"Name": "={Manufacturer Part}", "Manufacturer Part": "TL072CP",
                                         "Designator": "U?", "Add into BOM": "yes", "Convert to PCB": "yes",
                                         "Symbol": su, "Footprint": fps["DIP8"], "3D Model": "",
                                         "3D Model Title": "", "3D Model Transform": "",
                                         "Description": "Dual JFET op-amp, DIP-8"}, ["Amplifiers"])
        new = [
            ("BC548", npn_symbol("BC548", "BC548.1", {"C": "1", "B": "2", "E": "3"}), "BC548", "Q?", fps["TO92"],
             "NPN, TO-92: 1 C, 2 B, 3 E (flat face towards you, legs down). Here only its base-emitter junction "
             "is used, in reverse breakdown: the noise source"),
            ("2N3904", npn_symbol("2N3904", "2N3904.1", {"E": "1", "B": "2", "C": "3"}), "2N3904", "Q?", fps["TO92"],
             "NPN, TO-92: 1 E, 2 B, 3 C (flat face towards you, legs down)"),
            ("J113", jfet_symbol(), "J113", "Q?", fps["TO92"],
             "N-channel JFET switch, TO-92 (onsemi J113): 1 D, 2 S, 3 G. J112 also works"),
            ("LED", led_symbol(), "LED 3mm red", "D?", fps["LED2"],
             "3 mm red LED, pad 1 (square) = anode. Stands off the board to reach the panel"),
        ]
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
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
        lines += next(d for d in self.lib.values() if d["docType"] == "BLOB")["lines"]   # one BLOB doc
        project = {"title": TITLE, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "S&H: sample & hold, white / pink / blue noise, slew and a random gate, after "
                                  "Moritz Klein's MKI x ES.EDU S&H/Noise. 2x TL074, TL072, J113. One PCB, 10HP.",
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
        if part.label.startswith("film"):
            return "CF" + part.value
        return {"100n": "C100n"}.get(part.value, "C" + part.value)
    if part.kind == "CP":
        return "C" + part.value
    if part.kind == "POT":
        return "POT" + part.value
    return {"TL074": "TL074N", "TL072": "TL072N"}.get(part.kind, part.kind)


# ---------------------------------------------------------------- drawing helpers
def hpart(pg, part, x1, y, left_pin="1"):
    """Two-pin part drawn horizontally with `left_pin` at (x1, y), the other pin at (x1 + 40, y)."""
    rot = 0 if left_pin == "1" else 180
    return pg.place(part.ref, dev_of(part), x1 + 20, y, rot, des=H_TXT[0], value_at=H_TXT[1])


def vpart(pg, part, x, y1, top_pin="1"):
    """Two-pin part drawn vertically with `top_pin` at (x, y1), the other pin at (x, y1 + 40)."""
    rot = 270 if top_pin == "1" else 90
    return pg.place(part.ref, dev_of(part), x, y1 + 20, rot, *V_TXT)


def opamp(pg, ref, sec, ox, oy, des=(14, 30, "LEFT_BOTTOM")):
    """An op-amp section at (ox, oy): in- at (ox - 40, oy - 10), in+ at (ox - 40, oy + 10), out at (ox + 40, oy).
    Unit 1 also gets its supply pins labelled +12V / -12V."""
    kind = circuit.CHIPS[ref]
    amp = pg.place(ref, kind + "N", ox, oy, unit=UNIT[sec], des=des, name=False)
    if UNIT[sec] == 1:
        vp, vn = SUPPLY_PINS[kind]
        a, b = amp[vp], amp[vn]
        pg.wire([a, a], "+12V", label=(a[0] + 3, a[1] - 2, "LEFT_BOTTOM"))
        pg.wire([b, b], "-12V", label=(b[0] + 3, b[1] + 8, "LEFT_BOTTOM"))
    pg.text(ox - 30, oy + 45, f"{ref}{sec}", 8)
    return amp


def pins(ref, sec):
    """(out, in-, in+) pin numbers of a section."""
    return SECTION[sec]


def noninv(pg, P, ref, sec, ox, oy, rf, rg):
    """Non-inverting stage: in+ left for the caller at (ox - 40, oy + 10); in- to a junction J above-left, with
    rf (pin 1 on the output) to the output node and rg (pin 2 on GND) to ground on the left. Returns the
    output node (ox + 60, oy)."""
    amp = opamp(pg, ref, sec, ox, oy)
    out, inm, inp = pins(ref, sec)
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


def follower(pg, ref, sec, ox, oy, net, loop=35):
    """Unity follower: the output looped back over the top to in-. Returns the output node (ox + 55, oy)."""
    amp = opamp(pg, ref, sec, ox, oy)
    out, inm, inp = pins(ref, sec)
    k = (ox + 55, oy)
    pg.wire([amp[out], k], net)
    pg.wire([k, (ox + 55, oy - loop), (ox - 55, oy - loop), (ox - 55, oy - 10), amp[inm]], net)
    return k


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


def lugs_to_gnd(pg, p, rot):
    """A pot's mounting lugs 4 / 5 joined and grounded, under the pot (rot 0) or over it (rot 180)."""
    d = 15 if rot == 0 else -15
    a, b = p["4"], p["5"]
    lo, hi = sorted((a, b))
    pg.wire([lo, (lo[0] - 10, lo[1]), (lo[0] - 10, lo[1] + d), (hi[0] + 10, hi[1] + d), (hi[0] + 10, hi[1]), hi],
            "GND")
    end = (hi[0] + 10, hi[1] + d + (10 if rot == 0 else -10))
    pg.wire([(hi[0] + 10, hi[1] + d), end], "GND")
    pg.gnd(*end, 0 if rot == 0 else 180)


def pot(pg, part, px, py, rot=0):
    """Library pot symbol, rot 0: CW end (3) left at (px - 22, py + 5), CCW end (1) right at (px + 18, py + 5),
    wiper up at (px - 2, py - 15). The lugs are grounded."""
    up = rot == 0
    p = pg.place(part.ref, dev_of(part), px, py, rot, des=(-40, -22, "LEFT_BOTTOM") if up else (-45, 36, "LEFT_BOTTOM"),
                 value_at=(-40, -12, "LEFT_BOTTOM") if up else (-45, 46, "LEFT_BOTTOM"))
    pg.text(px - 40, py + 60 if up else py - 50, part.label, 10)
    lugs_to_gnd(pg, p, rot)
    return p


# ------------------------------------------------------------------ pages
def noise_page(pr, P):
    pg = MPage(pr, "Noise", 1)
    pg.text(40, Y(40), "Noise: Q1's base-emitter junction in reverse breakdown, x148 (white), a +3 dB/oct shelf "
                       "(blue) and a -3 dB/oct network (pink)", 12)
    pg.text(40, Y(70), "After the MKI x ES.EDU S&H/Noise (Moritz Klein), production schematic EDUSH2 rev 2.0", 10)
    # -- source and white amp
    pg.text(80, Y(120), "Source: the 4k7 / 47u filter keeps rail ripple out of the x148", 10)
    r101 = vpart(pg, P["R101"], 140, Y(150))
    pg.stub_port(r101["1"], "+12V", "IN", "left")
    n1 = (140, Y(200))
    pg.wire([r101["2"], n1], "NSUP")
    c101 = vpart(pg, P["C101"], 90, Y(200), top_pin="2")
    pg.wire([n1, c101["2"]], "NSUP")
    pg.stub_gnd(c101["1"], "down", 10)
    r102 = vpart(pg, P["R102"], 140, Y(210))
    pg.wire([n1, r102["1"]], "NSUP")
    n2 = (140, Y(260))
    pg.wire([r102["2"], n2], "NE")
    q1 = pg.place("Q1", "BC548", 150, Y(290), 180, des=(-52, 0, "LEFT_BOTTOM"), value_at=(-52, 10, "LEFT_BOTTOM"))
    pg.wire([n2, q1["3"]], "NE")
    pg.stub_gnd(q1["2"], "down", 10)
    pg.text(118, Y(325), "C open", 7)
    c102 = hpart(pg, P["C102"], 200, Y(260))
    pg.wire([n2, c102["1"]], "NE")
    n3 = (270, Y(260))
    pg.wire([c102["2"], n3], "NIN")
    r103 = vpart(pg, P["R103"], 270, Y(270))
    pg.wire([n3, r103["1"]], "NIN")
    pg.stub_gnd(r103["2"], "down", 10)
    pg.text(330, Y(130), "White: x148 (100k / 680)", 10)
    ox, oy = 420, Y(250)
    k = noninv(pg, P, "U1", "B", ox, oy, "R104", "R105")
    pg.wire([n3, (ox - 40, oy + 10)], "NIN")
    r106 = hpart(pg, P["R106"], k[0] + 20, k[1])
    pg.wire([k, r106["1"]], "WN")
    pg.stub_port(r106["2"], "WHITE", "OUT", "right")
    pg.wire([k, (k[0], k[1] + 50)], "WN")
    pg.port(k[0], k[1] + 50, "WN", "OUT", "right")
    pg.text(k[0] + 25, k[1] + 70, "to blue, pink, and IN's normal", 8)
    # -- blue
    pg.text(80, Y(380), "Blue: three series RC legs into 20k (about +3 dB/oct), then x1.33", 10)
    ys = [Y(440), Y(480), Y(520)]
    pg.port(120, ys[0], "WN", "IN", "left")
    pg.wire([(120, ys[0]), (170, ys[0])], "WN")
    for (cref, rref), y, a, b in zip((("C103", "R107"), ("C104", "R108"), ("C105", "R109")), ys, (170,) * 3,
                                     (340,) * 3):
        c = hpart(pg, P[cref], 190, y)
        r = hpart(pg, P[rref], 250, y)
        pg.wire([(a, y), c["1"]], "WN")
        pg.wire([c["2"], r["1"]], P[cref].nets["2"])
        pg.wire([r["2"], (b, y)], "BLN")
    for y0, y1 in zip(ys, ys[1:]):
        pg.wire([(170, y0), (170, y1)], "WN")
        pg.wire([(340, y0), (340, y1)], "BLN")
    r110 = vpart(pg, P["R110"], 340, ys[2] + 10)
    pg.wire([(340, ys[2]), r110["1"]], "BLN")
    pg.stub_gnd(r110["2"], "down", 10)
    ox, oy = 520, ys[1] - 10
    k = noninv(pg, P, "U1", "C", ox, oy, "R111", "R112")
    pg.wire([(340, ys[1]), (ox - 40, oy + 10)], "BLN")
    r113 = hpart(pg, P["R113"], k[0] + 20, k[1])
    pg.wire([k, r113["1"]], "BOUT")
    pg.stub_port(r113["2"], "BLUE", "OUT", "right")
    # -- pink
    pg.text(80, Y(590), "Pink: 100k into three shunt RC legs (about -3 dB/oct above 300 Hz), then x5.5", 10)
    yb = Y(680)
    pg.port(120, yb, "WN", "IN", "left")
    r114 = hpart(pg, P["R114"], 140, yb)
    pg.wire([(120, yb), r114["1"]], "WN")
    xs = [220, 280, 340]
    pg.wire([r114["2"], (xs[0], yb)], "PKN")
    for (cref, rref), x in zip((("C106", "R115"), ("C107", "R116"), ("C108", "R117")), xs):
        c = vpart(pg, P[cref], x, yb + 10)
        r = vpart(pg, P[rref], x, yb + 60)
        pg.wire([(x, yb), c["1"]], "PKN")
        pg.wire([c["2"], r["1"]], P[cref].nets["2"])
        pg.stub_gnd(r["2"], "down", 10)
    for x0, x1 in zip(xs, xs[1:]):
        pg.wire([(x0, yb), (x1, yb)], "PKN")
    ox, oy = 520, yb - 10
    k = noninv(pg, P, "U1", "A", ox, oy, "R118", "R119")
    pg.wire([(xs[-1], yb), (ox - 40, oy + 10)], "PKN")
    r120 = hpart(pg, P["R120"], k[0] + 20, k[1])
    pg.wire([k, r120["1"]], "POUT")
    pg.stub_port(r120["2"], "PINK", "OUT", "right")
    # -- jacks
    pg.text(960, Y(130), "Outputs (panel)", 11)
    for i, ref in enumerate(("J5", "J7", "J8")):
        jack_block(pg, P[ref], 1000, Y(220 + 160 * i), "IN")
    pg.text(40, Y(1100), "Resistors 1 % metal film, all standing. 680p-5n6 C0G (the MKI uses foil); C102 film. Net "
                         "ports with the same name connect across the pages; GND is one net.", 9)
    return pg


def clock_page(pr, P):
    pg = MPage(pr, "Clock and trigger", 2)
    pg.text(40, Y(40), "Internal clock (Schmitt relaxation oscillator), trigger shaping and the clock LED", 12)
    pg.text(40, Y(70), "f = 1 / (2.2 x (2k + RATE) x 2u2): 0.8 Hz (CCW) .. 103 Hz (CW). CLOCK unpatched takes it "
                       "through R204.", 10)
    # -- oscillator
    ox, oy = 400, Y(320)
    amp = opamp(pg, "U2", "A", ox, oy)
    out, inm, inp = SECTION["A"]
    j1 = (320, Y(310))
    pg.wire([amp[inm], j1], "OSC_C")
    c201 = vpart(pg, P["C201"], 280, Y(310))
    pg.wire([j1, c201["1"]], "OSC_C")
    pg.stub_gnd(c201["2"], "down", 10)
    r201 = hpart(pg, P["R201"], 320, Y(200))
    pg.wire([j1, r201["1"]], "OSC_C")
    rv1 = pot(pg, P["RV1"], 452, r201["2"][1] - 5)       # the pot's ends sit 5 below its origin
    assert rv1["3"][1] == r201["2"][1]
    pg.wire([r201["2"], rv1["3"]], "RT")
    k = (520, oy)
    m = (520, Y(200))
    pg.wire([amp[out], k], "OSC")
    pg.wire([k, m], "OSC")
    pg.wire([rv1["1"], m], "OSC")
    w = rv1["2"]
    pg.wire([w, (w[0], w[1] - 10), (m[0], w[1] - 10), m], "OSC")
    pg.text(540, Y(170), "RATE as a rheostat: CW = 0 ohm, the fastest", 8)
    p = (340, Y(400))
    pg.wire([amp[inp], (340, amp[inp][1]), p], "OSC_P")
    r203 = vpart(pg, P["R203"], 340, Y(400))
    assert r203["1"] == p
    pg.stub_gnd(r203["2"], "down", 10)
    r202 = hpart(pg, P["R202"], 360, Y(400), left_pin="2")
    pg.wire([p, r202["2"]], "OSC_P")
    pg.wire([r202["1"], (k[0], Y(400)), k], "OSC")
    r204 = hpart(pg, P["R204"], k[0] + 20, k[1])
    pg.wire([k, r204["1"]], "OSC")
    pg.stub_port(r204["2"], "CLK_INT", "OUT", "right")
    # -- trigger shaping
    pg.text(80, Y(492), "Trigger: 1n / 100k differentiator, positive edges only, compared with 3 V (100k / 33k): "
                        "SAMP, about 50-100 us at +-11 V per rising edge", 10)
    yt = Y(640)
    pg.port(120, yt, "CLK", "IN", "left")
    c202 = hpart(pg, P["C202"], 160, yt)
    pg.wire([(120, yt), c202["1"]], "CLK")
    dn = (230, yt)
    pg.wire([c202["2"], dn], "DIFF")
    r207 = vpart(pg, P["R207"], 230, yt + 10)
    pg.wire([dn, r207["1"]], "DIFF")
    pg.stub_gnd(r207["2"], "down", 10)
    d201 = hpart(pg, P["D201"], 250, yt, left_pin="2")
    pg.wire([dn, d201["2"]], "DIFF")
    tn = (330, yt)
    pg.wire([d201["1"], tn], "TRG")
    r208 = vpart(pg, P["R208"], 330, yt + 10)
    pg.wire([tn, r208["1"]], "TRG")
    pg.stub_gnd(r208["2"], "down", 10)
    ox, oy = 460, yt - 10
    amp = opamp(pg, "U2", "B", ox, oy)
    out, inm, inp = SECTION["B"]
    pg.wire([tn, amp[inp]], "TRG")
    th = (400, yt - 80)
    pg.wire([amp[inm], (400, amp[inm][1]), th], "THR")
    r209 = vpart(pg, P["R209"], 400, th[1] - 50)
    pg.stub_port(r209["1"], "+12V", "IN", "left")
    pg.wire([r209["2"], th], "THR")
    r210 = hpart(pg, P["R210"], 340, th[1], left_pin="2")
    pg.wire([th, r210["1"]], "THR")
    pg.stub_gnd(r210["2"], "down", 10)
    pg.stub_port(amp[out], "SAMP", "OUT", "right", 40)
    # -- the clock LED
    pg.text(760, Y(530), "Clock LED: lit while CLOCK is high, internal or patched", 10)
    yl = Y(700)
    pg.port(780, yl, "CLK", "IN", "left")
    r205 = hpart(pg, P["R205"], 800, yl)
    pg.wire([(780, yl), r205["1"]], "CLK")
    q2 = pg.place("Q2", "2N3904", 880, yl, des=(16, 2, "LEFT_BOTTOM"), value_at=(16, 12, "LEFT_BOTTOM"))
    pg.wire([r205["2"], q2["2"]], "LED_B")
    pg.stub_gnd(q2["1"], "down", 10)
    d1 = vpart(pg, P["D1"], 890, yl - 70)
    pg.wire([d1["2"], q2["3"]], "LED_K")
    r206 = vpart(pg, P["R206"], 890, yl - 130)
    pg.stub_port(r206["1"], "+12V", "IN", "left")
    pg.wire([r206["2"], d1["1"]], "LED_A")
    # -- the CLOCK jack
    pg.text(1180, Y(130), "Input (panel)", 11)
    jack_block(pg, P["J1"], 1220, Y(220), "OUT")
    pg.text(40, Y(1100), "C201 film (it sees +-5.5 V); C202 C0G. RATE and LEVEL are Alpha 9 mm pots on the panel.", 9)
    return pg


def sh_page(pr, P):
    pg = MPage(pr, "S&H, slew, gate", 3)
    pg.text(40, Y(40), "Sample & hold (J113 into a 100n film cap), slew, and the random gate", 12)
    # -- S&H
    pg.text(80, Y(110), "IN (unpatched: white noise) -> LEVEL -> buffer -> J113 -> hold cap -> buffer -> S&H. SAMP "
                        "high: D301 blocks, R301 holds the gate at the source (on). SAMP low: gate at -10 V (hold)",
            10)
    ys = Y(300)
    rv2 = pot(pg, P["RV2"], 270, ys + 25)
    pg.stub_port(rv2["3"], "IN", "IN", "left", 30)
    pg.stub_gnd(rv2["1"], "right", 10)
    ox, oy = 410, ys - 10
    w = rv2["2"]
    amp_in = (ox - 40, oy + 10)
    pg.wire([w, (w[0], amp_in[1]), amp_in], "LV")
    f = follower(pg, "U2", "D", ox, oy, "SHI")
    x = (490, f[1])
    pg.wire([f, x], "SHI")
    q3 = pg.place("Q3", "J113", 560, f[1] - 6, des=(-12, 26, "LEFT_BOTTOM"), value_at=(-12, 36, "LEFT_BOTTOM"))
    pg.wire([x, q3["2"]], "SHI")
    g = (q3["3"][0], Y(200))
    r301 = hpart(pg, P["R301"], 490, g[1])
    pg.wire([x, r301["1"]], "SHI")
    pg.wire([r301["2"], g], "JG")
    pg.wire([g, q3["3"]], "JG")
    d301 = hpart(pg, P["D301"], g[0] + 20, g[1], left_pin="2")
    pg.wire([g, d301["2"]], "JG")
    pg.stub_port(d301["1"], "SAMP", "IN", "right")
    hn = (620, f[1])
    pg.wire([q3["1"], hn], "HOLD")
    c301 = vpart(pg, P["C301"], 620, f[1])
    assert c301["1"] == hn
    pg.stub_gnd(c301["2"], "down", 10)
    ox, oy = 700, f[1] - 10
    pg.wire([hn, (ox - 40, oy + 10)], "HOLD")
    b = follower(pg, "U2", "C", ox, oy, "SHB")
    r302 = hpart(pg, P["R302"], b[0] + 20, b[1])
    pg.wire([b, r302["1"]], "SHB")
    pg.stub_port(r302["2"], "SH_OUT", "OUT", "right")
    pg.wire([b, (b[0], b[1] + 50)], "SHB")
    pg.port(b[0], b[1] + 50, "SHB", "OUT", "right")
    pg.text(b[0] + 25, b[1] + 70, "to SLEW IN's normal and the gate", 8)
    # -- slew
    pg.text(80, Y(470), "Slew: SLEW IN (unpatched: the S&H) -> buffer -> SLEW (A1M rheostat, CCW = 0) -> 470n film -> "
                        "buffer -> SLEW. tau 0-0.47 s", 10)
    yl = Y(600)
    ox, oy = 410, yl - 10
    pg.port(330, yl, "SLI", "IN", "left")
    pg.wire([(330, yl), (ox - 40, yl)], "SLI")
    sb = follower(pg, "U3", "B", ox, oy, "SLB")
    rv3 = pot(pg, P["RV3"], sb[0] + 53, sb[1] + 5, rot=180)
    pg.wire([sb, rv3["1"]], "SLB")
    sc = (rv3["3"][0] + 30, sb[1])
    pg.wire([rv3["3"], sc], "SLC")
    w = rv3["2"]
    pg.wire([w, (w[0], w[1] + 10), (sc[0], w[1] + 10), sc], "SLC")
    sd = (sc[0] + 30, sb[1])
    pg.wire([sc, sd], "SLC")
    c401 = vpart(pg, P["C401"], sd[0], sd[1])
    assert c401["1"] == sd
    pg.stub_gnd(c401["2"], "down", 10)
    ox2, oy2 = sd[0] + 80, sb[1] - 10
    pg.wire([sd, (ox2 - 40, oy2 + 10)], "SLC")
    so = follower(pg, "U3", "A", ox2, oy2, "SLO", loop=55)
    r401 = hpart(pg, P["R401"], so[0] + 20, so[1])
    pg.wire([so, r401["1"]], "SLO")
    pg.stub_port(r401["2"], "SLEW", "OUT", "right")
    # -- gate
    pg.text(80, Y(760), "Random gate (new; the TL074 section the MKI leaves idle): high above +0.11 V, low below "
                        "-0.11 V (10k / 1M). Out through 1N4148 and 1k: 0 V or about +10 V", 10)
    yg = Y(880)
    pg.port(300, yg, "SHB", "IN", "left")
    r501 = hpart(pg, P["R501"], 320, yg)
    pg.wire([(300, yg), r501["1"]], "SHB")
    gp = (390, yg)
    pg.wire([r501["2"], gp], "GTP")
    ox, oy = 480, yg - 10
    amp = opamp(pg, "U1", "D", ox, oy)
    out, inm, inp = SECTION["D"]
    pg.wire([gp, amp[inp]], "GTP")
    pg.stub_gnd(amp[inm], "left", 10)
    k = (ox + 60, oy)
    pg.wire([amp[out], k], "GTO")
    r502 = hpart(pg, P["R502"], 410, yg + 60, left_pin="2")
    pg.wire([gp, (gp[0], yg + 60), r502["2"]], "GTP")
    pg.wire([r502["1"], (k[0], yg + 60), k], "GTO")
    d501 = hpart(pg, P["D501"], k[0] + 20, k[1], left_pin="2")
    pg.wire([k, d501["2"]], "GTO")
    gd = (k[0] + 90, k[1])
    pg.wire([d501["1"], gd], "GTD")
    r503 = vpart(pg, P["R503"], gd[0], gd[1] + 10)
    pg.wire([gd, r503["1"]], "GTD")
    pg.stub_gnd(r503["2"], "down", 10)
    r504 = hpart(pg, P["R504"], gd[0] + 20, gd[1])
    pg.wire([gd, r504["1"]], "GTD")
    pg.stub_port(r504["2"], "GATE", "OUT", "right")
    # -- jacks
    pg.text(1180, Y(130), "Inputs and outputs (panel)", 11)
    for i, (ref, kind) in enumerate((("J2", "OUT"), ("J3", "OUT"), ("J6", "IN"), ("J9", "IN"), ("J4", "IN"))):
        jack_block(pg, P[ref], 1220, Y(220 + 160 * i), kind)
    pg.text(40, Y(1100), "C301 (hold) and C401 (slew) film. The JFET switches off for inputs above about -7 V: "
                         "white noise is +-5 V; turn LEVEL down for hotter signals.", 9)
    return pg


def power_block(pg, P, x0, t0):
    """16-pin header (red stripe = pin 1 = -12 V; 3-8 GND, 9-10 +12 V, 11-16 open), a 1N5819 per rail (the -12 V cathode on the header),
    10R and 47 uF (the mixer's drawing)."""
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J10", "HDR16", xh, yh, des=(-30, -45, "LEFT_BOTTOM"), value_at=(-30, 52, "LEFT_BOTTOM"))
    for side, pns, sgn in (("left", ("3", "5", "7"), -1), ("right", ("4", "6", "8"), 1)):
        bx = xh + sgn * 45
        pts = []
        for n in pns:
            p = h[n]
            pg.wire([p, (bx, p[1])], "GND")
            pts.append((bx, p[1]))
        for a, b in zip(pts, pts[1:]):
            pg.wire([a, b], "GND")
        mid = pts[1]                         # the middle GND pin (5 / 6): clear of the P12_IN ports on 9 / 10
        pg.wire([mid, (bx + sgn * 15, mid[1])], "GND")
        pg.gnd(bx + sgn * 15, mid[1], 90 if sgn > 0 else 270)
    pg.stub_port(h["1"], "N12_IN", "OUT", "left", 30)
    pg.stub_port(h["2"], "N12_IN", "OUT", "right", 30)
    pg.stub_port(h["9"], "P12_IN", "OUT", "left", 30)
    pg.stub_port(h["10"], "P12_IN", "OUT", "right", 30)
    xa = x0 + 330
    for k, (port, d, r, c, rail) in enumerate((("P12_IN", "D901", "R901", "C901", "+12V"),
                                               ("N12_IN", "D902", "R902", "C902", "-12V"))):
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
    pg = MPage(pr, "Power", 4)
    pg.text(40, Y(40), "Power: 16-pin Eurorack header (red stripe = pin 1 = -12 V; 3-8 GND, 9-10 +12 V, 11-16 open), a 1N5819 per rail: +12 V anode on "
                       "the header, -12 V cathode on the header", 12)
    power_block(pg, P, 80, 120)
    pg.text(900, Y(40), "Decoupling: a 100n pair per op-amp, beside its supply pins", 12)
    for i, u in enumerate(circuit.CHIPS):
        x, top = 980 + i * 140, Y(160)
        decoupling_pair(pg, P, f"C{903 + 2 * i}", f"C{904 + 2 * i}", x, top)
        pg.text(x + 8, top + 140, f"{u} ({circuit.CHIPS[u]})", 10)
    pg.text(40, Y(1100), "About 25 mA on +12 V and 15 mA on -12 V: three TL07x and the clock LED.", 9)
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


def validate(path):
    """Parse the written project: every schematic component's Device, Symbol and Footprint must be in it;
    on the PCBs every PAD_NET must name a real pad of its component's footprint and a net with a NET
    record, and every component's Device must exist (EasyEDA drops a net silently otherwise)."""
    with ee.zipfile.ZipFile(path) as z:
        docs = ee.parse(z.read(f"{NAME}.epru").decode("utf-8").split("\n"))
    problems = []
    for u, d in docs.items():
        if d["docType"] == "SCH_PAGE":
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p["key"] in ("Device", "Symbol", "Footprint") and p["value"] \
                        and p["value"] not in docs:
                    problems.append(f"{meta(d)['title']}: {p['key']} {p['value']} missing")
        elif d["docType"] == "PCB":
            comps, nets, attrs = set(), set(), {}
            for h, p in d["recs"]:
                if h["type"] == "COMPONENT":
                    comps.add(h["id"])
                elif h["type"] == "NET":
                    nets.add(ee.json.loads(h["id"])[1])
                elif h["type"] == "ATTR" and p.get("parentId"):
                    attrs.setdefault(p["parentId"], {})[p["key"]] = p["value"]
            for cid in comps:
                a = attrs.get(cid, {})
                if a.get("Device") not in docs or a.get("Footprint") not in docs:
                    problems.append(f"{meta(d)['title']}: component {cid} has no Device or Footprint")
            for h, p in d["recs"]:
                if h["type"] != "PAD_NET":
                    continue
                _, cid, num, pad_id = ee.json.loads(h["id"])
                fp = docs.get(attrs.get(cid, {}).get("Footprint"))
                pad_ids = {hh["id"] for hh, _ in fp["recs"] if hh["type"] == "PAD"} if fp else set()
                if pad_id not in pad_ids:
                    problems.append(f"{meta(d)['title']}: PAD_NET {cid}.{num} names no pad of its footprint")
                if p["padNet"] not in nets:
                    problems.append(f"{meta(d)['title']}: net {p['padNet']} has no NET record")
    return problems, collections.Counter(d["docType"] for d in docs.values())


def main():
    pr = MProject()
    parts = circuit.all_parts()
    P = {p.ref: p for p in parts}
    pages = [noise_page(pr, P), clock_page(pr, P), sh_page(pr, P), power_page(pr, P)]
    bad = coverage(pages, parts)
    for pg in pages:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    used = {c["dev"] for pg in pages for c in pg.comps if c["ref"]}
    bad += pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    board = pcb.one_board(pr, parts, part_info(pages), circuit)
    pcb_bad = board.check() + pcb.placement_check(board, circuit) + pcb.front_housing_check(board)
    for b in pcb_bad:
        print("PCB:", b)
    panel_page = MPage(pr, "Panel", 1)
    panel_page.page_count = "1"
    panel_page.text(70, Y(60), "S&H 10HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the "
                               "bare-copper output block are in the PCB document; the art is "
                               "hardware/panel/sample-hold-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([(TITLE, pages, board), (f"{TITLE} Panel", [panel_page], board_panel)], OUT, pcb.load_template(ee))
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in pages:
        render(pr, pg, PREVIEW.format(pg.title.split(",")[0].lower().replace(" ", "-").replace("&", "")))
    board.render(PREVIEW.format("pcb"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(pages)} pages, {len(bad)} schematic problems; "
          f"{len(board.placed)} parts placed, {len(pcb_bad)} PCB problems; {len(missing)} file problems; "
          f"docs {dict(counts)}")


if __name__ == "__main__":
    main()
