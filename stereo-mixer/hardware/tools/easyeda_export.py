"""Stereo mixer schematic as an EasyEDA Pro project (.epro2), plus PNG previews.

The netlist is netlist.py. The file format, library loading, connectivity
check and preview renderer come from Plaitsy's exporter
(plaitsy/hardware/tools/easyeda_export.py), so both projects stay alike.

Parts are your MorrisSynth library parts: TL074ACN, the WQP518MA jack,
PTV09A pots (A100K and B10K), the ATE1D toggle, LR1F resistors, FG28
capacitors, the 178MU0033 10 uF electrolytic, 1N5819, the 2x8 2.54 mm box
header (DC3-2.54-16PAS), the net ports, the ground flag and the sheet frame.
Values the library lacks (100k, 200k, 300k and 22 pF) are new devices on the
same symbols and footprints. Two parts are not in the library and are drawn
here in the same style, one unit per gang or pole and without a footprint:
the 9 mm dual-gang pot and the ATE2D-2M3-10-Z DPDT toggle.

Three A3 pages: mono channels, stereo channels and inputs, buses with the
master, outputs and power. Net ports with the same name connect.

Run from hardware/tools:  python easyeda_export.py
"""
import collections
import os
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLAITSY_TOOLS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "plaitsy", "hardware", "tools"))
sys.path.insert(0, PLAITSY_TOOLS)
import easyeda_export as ee  # noqa: E402  Plaitsy's exporter
sys.path.remove(PLAITSY_TOOLS)

from netlist import Part, all_parts, SECTION, MONO, STEREO, opamp_of  # noqa: E402

NAME = "StereoMixer"
LIBFILE = os.path.join(HERE, "..", "easyeda", "stereo-mixer-parts.epru")
OUT = os.path.join(HERE, "..", "easyeda", f"{NAME}.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "stereo-mixer-{}.png")
Y = ee.Y

# ---------------------------------------------------------------- library
DEV = {
    "R1k": "c82a8167f1d84133bc542e652bd22433",       # LR1F1K0
    "R10k": "a9cc8fbe474242dc9110194515734c75",      # LR1F10K
    "R10R": "94e97e59e04b421d92158c6257818225",      # LR1F10R
    "C100n": "2eb0447475ac403680fd2b11e4f4c945",     # FG28X7R1H104KNT00
    "C10u": "21e4ec8defc34a489f66b07134d13cd6",      # 178MU0033, 10 uF 35 V
    "TL074": "ad23edee5d134c14aa92ae80bedf6b28",     # TL074ACN
    "JACK": "f4a247c302d346488553de1a1eb440e9",      # WQP-WQP518MA
    "POTA100k": "0726d333c10d472fbc05151d7c976765",  # PTV09A-4030F-A104
    "POTB10k": "be9d2c8f5f814271a402f956f18b56f9",   # PTV09A-4025F-B103
    "SPDT": "af39adda35bb44bdb6f208544413d6a4",      # ATE1D-2M3-10-Z
    "HDR": "bbe47e9fd91b42bbaf0d36b9504a3a5e",       # DC3-2.54-16PAS (IDC-TH_16P-P2.54_C3406)
    "D5819": "f1e2836d6b9a4bf1bb0838127f6aa231",     # 1N5819_C49318088
    "GND": "eec77ec4c1d94de692d165be3817a3c4",       # Ground-GND
    "IN": "6a70cfa1bc80484e8decf4f8a0b61a9e",        # Netport-IN
    "OUT": "7956696325094941b2d15526d9c13967",       # Netport-OUT
    "FRAME": "93ae535dda0d4cce9b643bf06fbcd5ca",     # Drawing-Symbol_A4
}
ee.DEV = DEV          # Page._flag looks the ground flag up here
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "200k": ("LR1F200K", "200kΩ"), "300k": ("LR1F300K", "300kΩ")}
C_NEW = {"22p": ("FG28C0G1H220JNT00", "22pF")}


def load_library():
    """The MorrisSynth docs this project needs, cached next to the project."""
    if not os.path.exists(LIBFILE):
        with zipfile.ZipFile(ee.EXPORT) as z:
            name = next(n for n in z.namelist() if n.endswith(".epru"))
            docs = ee.parse(z.read(name).decode("utf-8").split("\n"))
        want = set(DEV.values()) | {"BLOB"}
        for u in DEV.values():
            a = ee.meta(docs[u])["attributes"]
            want |= {a["Symbol"]} | ({a["Footprint"]} if a.get("Footprint") else set())
        os.makedirs(os.path.dirname(LIBFILE), exist_ok=True)
        with open(LIBFILE, "w", encoding="utf-8", newline="\n") as f:
            for u, d in docs.items():
                if u in want:
                    f.write("\n".join(d["lines"]) + "\n")
    return ee.parse(open(LIBFILE, encoding="utf-8").read().split("\n"))


class MultiSymbol:
    """A symbol with several units (gangs, poles), in the library's style."""

    def __init__(self, title, prefix, designator, units, tags=()):
        self.title, self.designator, self.tags = title, designator, list(tags)
        self.parts = [f"{prefix}.{i + 1}" for i in range(units)]
        self.items = {p: [] for p in self.parts}
        self.cur = self.parts[0]
        self.doc = ee.Doc("SYMBOL")

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
            d.add("ATTR", d.nid(), ee.attr_payload(d.zi(), "", "Symbol", self.title, align="LEFT_BOTTOM", part=part))
            d.add("ATTR", d.nid(), ee.attr_payload(d.zi(), "", "Designator", self.designator, align="LEFT_BOTTOM",
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
                    d.add("ATTR", d.nid(), ee.attr_payload(d.zi(), pid, "Pin Name", name, x=x, y=y,
                                                           align="LEFT_BOTTOM", part=part))
                    d.add("ATTR", d.nid(), ee.attr_payload(d.zi(), pid, "Pin Number", num, vv=True, x=nx, y=ny,
                                                           fs=6, align="LEFT_BOTTOM", part=part))
                    d.add("ATTR", d.nid(), ee.attr_payload(d.zi(), pid, "Pin Type", "Undefined", x=x, y=y,
                                                           align="LEFT_BOTTOM", part=part))
        source = f"{ee.new_uuid()}|{ee.USER['uuid']}"
        return d.lines({"title": self.title, "description": "", "tags": self.tags, "docType": 2, "source": source})


def dual_pot_symbol():
    """Two gangs drawn like the library pot standing up: CW end on top,
    CCW end below, wiper from the right. Gang A pins 3/2/1, gang B 6/5/4."""
    s = MultiSymbol("Pot 9mm dual-gang", "POT_DUAL", "RV?", 2, ["StereoMixer"])
    for unit, (cw, w, ccw, letter) in enumerate((("3", "2", "1", "A"), ("6", "5", "4", "B")), start=1):
        s.unit(unit)
        s.poly([(0, -12), (3, -10), (-3, -6), (3, -2), (-3, 2), (3, 6), (-3, 10), (0, 12)])
        s.poly([(10, 0), (6, 0)])
        s.poly([(4, 0), (8, -2.5), (8, 2.5), (4, 0)], closed=True)
        s.text(-13, 3, letter, 8)
        s.pin(cw, "CW", 0, -20, 270, 8)
        s.pin(ccw, "CCW", 0, 20, 90, 8)
        s.pin(w, "W", 20, 0, 180, 10)
    return s


def dpdt_symbol():
    """Two poles: throws on the left (upper, lower), common on the right.
    Pole A pins 1/3 and common 2, pole B 4/6 and common 5."""
    s = MultiSymbol("Toggle DPDT on-on", "DPDT", "SW?", 2, ["StereoMixer"])
    for unit, (up, com, low, letter) in enumerate((("1", "2", "3", "A"), ("4", "5", "6", "B")), start=1):
        s.unit(unit)
        s.poly([(12, 0), (-10, -8)])
        s.poly([(-12, -12), (-12, -8)])
        s.poly([(-12, 8), (-12, 12)])
        s.poly([(12, -2), (12, 2)])
        s.text(-2, 13, letter, 8)
        s.pin(up, "1", -20, -10, 0, 8)
        s.pin(low, "3", -20, 10, 0, 8)
        s.pin(com, "C", 20, 0, 180, 8)
    return s


class MixerProject(ee.Project):
    def __init__(self):  # noqa: super().__init__ would load Plaitsy's library
        self.lib = load_library()
        self.symgeo = {u: ee.symbol_geometry(d) for u, d in self.lib.items() if d["docType"] == "SYMBOL"}
        self.devices = {k: (u, ee.meta(self.lib[u])) for k, u in DEV.items()}
        self.new_docs = []
        self.uids, self.next_uid = {}, 2
        self._new_devices()

    def device_attrs(self, key):
        a = self.devices[key][1]["attributes"]
        if key == "POTA100k":         # the library device has an empty Name; show its value in previews
            a = dict(a, Name="={Value}")
        return a

    def _new_devices(self):
        r1k = ee.meta(self.lib[DEV["R1k"]])["attributes"]
        for val, (mpn, value) in R_NEW.items():
            a = dict(r1k)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "LCSC Part Name": f"Metal film resistor {value} ±1% 600mW",
                      "Description": f"Metal film resistor {value} ±1% 600mW (TE LR1F series)"})
            self._device("R" + val, mpn, a, ["Resistors", "Through Hole Resistors"])
        c100n = ee.meta(self.lib[DEV["C100n"]])["attributes"]
        for val, (mpn, value) in C_NEW.items():
            a = dict(c100n)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "Tolerance": "±5%", "Temperature Coefficient": "C0G",
                      "LCSC Part Name": f"{value} ±5% 50V C0G",
                      "Description": f"Capacitance:{value} Tolerance:±5% Voltage Rating:50V Temperature Coefficient:C0G"})
            self._device("C" + val, mpn, a, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"])
        su = self._symbol(dual_pot_symbol())
        for value in ("A100k", "A10k"):
            self._device("POT2_" + value, f"Pot 9mm dual-gang {value}", {
                "Name": "={Value}", "Value": value, "Manufacturer Part": f"9mm dual-gang vertical pot {value}",
                "Designator": "RV?", "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": "",
                "3D Model": "", "3D Model Title": "", "3D Model Transform": "",
                "Description": f"9 mm dual-gang vertical pot, {value} (audio taper), e.g. Alpha RD902F series. "
                               "Gang A pins 1-2-3, gang B 4-5-6, 2 and 5 wipers."})
        sd = self._symbol(dpdt_symbol())
        self._device("DPDT", "ATE2D-2M3-10-Z", {
            "Name": "={Manufacturer Part}", "Manufacturer": "NIDEC COPAL", "Manufacturer Part": "ATE2D-2M3-10-Z",
            "Supplier": "LCSC", "Supplier Part": "C2921532", "Designator": "SW?", "Add into BOM": "yes",
            "Convert to PCB": "yes", "Symbol": sd, "Footprint": "", "3D Model": "", "3D Model Title": "",
            "3D Model Transform": "",
            "Description": "Toggle switch DPDT on-on, 2.54 mm pins: the two-pole version of the ATE1D. "
                           "Check the datasheet pinout: poles 1-2-3 and 4-5-6, commons 2 and 5."})

    def _symbol(self, sym):
        lines = sym.build()
        self.new_docs.insert(0, ("SYMBOL", lines))
        self.lib_symbol(sym.doc.uuid, lines)
        return sym.doc.uuid

    def write(self, pages, path):
        board, sch = ee.Doc("BOARD", ee.new_uuid()[:16]), ee.Doc("SCH")
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
        lines += ee.Doc("CONFIG", "CONFIG").lines({"defaultSheet": ""})
        lines += [l for u, d in self.lib.items() if d["docType"] == "BLOB" for l in d["lines"]]
        project = {"title": NAME, "cbb_project": False, "editorVersion": ee.EDIT, "introduction": "",
                   "description": "Stereo master mixer for the Eurorack voice case: 6 mono channels with pan, "
                                  "2 stereo channels, Clouds return, drum input, one send. 4x TL074.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")


PAGE_COUNT = 3


class MixerPage(ee.Page):
    def frame(self):
        d, pr = self.doc, self.pr
        cid = d.nid()
        sym = pr.sym_of("FRAME")
        d.add("COMPONENT", cid, {"locked": False, "zIndex": d.zi(), "partId": pr.symgeo[sym]["parts"][0],
                                 "groupId": "", "x": 0, "y": 0, "rotation": 0, "isMirror": False, "attrs": {}})
        today = time.strftime("%Y-%m-%d")
        vals = [("Symbol", sym), ("@Project Name", "Stereo Mixer"), ("@Page Count", str(PAGE_COUNT)),
                ("@Update Date", today), ("@Create Date", today), ("@Schematic Name", "Stereo Mixer"),
                ("@Page No", str(self.number)), ("@Page Name", self.title), ("Company", ""), ("Reviewed", ""),
                ("Version", "V1.0"), ("Page Size", "A3"), ("Drawn", ""), ("Name", ""), ("@Create Time", ""),
                ("@Update Time", ""), ("Border", "1"), ("Width", ee.W), ("Height", ee.H), ("Region Start", "1"),
                ("X Region Count", "6"), ("Y Region Count", "4"), ("Blade Width", "10"), ("Color", ""),
                ("Title Block Position", "3"), ("Title Block", "1"), ("@Board Name", "Stereo Mixer"),
                ("Footprint", ""), ("Description", ""), ("Device", DEV["FRAME"])]
        for k, v in vals:
            d.add("ATTR", d.nid(), ee.attr_payload(d.zi(), cid, k, v))


# ---------------------------------------------------------------- drawing helpers
def dev_of(part):
    if part.kind == "R":
        return {"1k": "R1k", "10k": "R10k", "10R": "R10R"}.get(part.value, "R" + part.value)
    if part.kind == "C":
        return {"100n": "C100n"}.get(part.value, "C" + part.value)
    if part.kind == "POT":
        return "POT" + part.value
    if part.kind == "POT2":
        return "POT2_" + part.value
    return {"CP": "C10u", "D": "D5819", "JACK": "JACK", "SPDT": "SPDT", "DPDT": "DPDT", "TL074": "TL074",
            "HDR": "HDR"}[part.kind]


def hpart(pg, part, x1, y, left_pin="1"):
    """Two-pin part drawn horizontally with `left_pin` at (x1, y), the other pin at (x1 + 40, y)."""
    rot = 0 if left_pin == "1" else 180
    return pg.place(part.ref, dev_of(part), x1 + 20, y, rot, des=ee.H_TXT[0], value_at=ee.H_TXT[1])


def vpart(pg, part, x, y1, top_pin="1", texts_left=False):
    """Two-pin part drawn vertically with `top_pin` at (x, y1), the other pin at (x, y1 + 40)."""
    rot = 270 if top_pin == "1" else 90
    txt = ((-8, -2, "RIGHT_BOTTOM"), (-8, 8, "RIGHT_BOTTOM")) if texts_left else ee.V_TXT
    return pg.place(part.ref, dev_of(part), x, y1 + 20, rot, *txt)


def pot(pg, part, x, y, label=None):
    """Pot standing up: CW end (pin 3) at (x, y), CCW end (pin 1) at (x, y + 40),
    wiper (pin 2) at (x + 20, y + 20). Texts go on the left."""
    if part.value == "B10k":     # library symbol PTV09A-4025F-B103
        ox, oy, mirror = x + 5, y + 22, False
    else:                        # library symbol PTV09A-4030F-A104, mirrored
        ox, oy, mirror = x - 5, y + 18, True
    p = pg.place(part.ref, dev_of(part), ox, oy, 270, mirror=mirror,
                 des=(x - 8 - ox, y + 14 - oy, "RIGHT_BOTTOM"), value_at=(x - 8 - ox, y + 24 - oy, "RIGHT_BOTTOM"))
    if label:
        pg.text(x - 10 - 5.6 * len(label), y + 36, label, 9)
    return p


def pot2(pg, part, unit, x, y, label=None):
    """One gang of a dual pot: same geometry as pot()."""
    p = pg.place(part.ref, dev_of(part), x, y + 20, 0, unit=unit,
                 des=(-8, -6, "RIGHT_BOTTOM"), value_at=(-8, 4, "RIGHT_BOTTOM"))
    if label:
        pg.text(x - 10 - 5.6 * len(label), y + 36, label, 9)
    return p


def follower(pg, ref, sec, x, y, net):
    """TL074 section as a voltage follower with its + input at (x, y).
    Returns the junction point right of the output (row y - 10)."""
    ox, oy = x + 40, y - 10
    amp = pg.place(ref, "TL074", ox, oy, unit=sec, des=(-6, 32, "LEFT_BOTTOM"), name=False)
    out, inm, _ = SECTION[sec]
    node = (ox + 55, oy)
    pg.wire([amp[out], node], net)
    pg.wire([node, (ox + 55, oy - 35), (ox - 55, oy - 35), (ox - 55, oy - 10), amp[inm]], net)
    return node


def inverting(pg, ref, sec, x, y, rf, cf=None):
    """TL074 section as an inverting stage. Its - input is at (x + 15, y);
    the summing junction is at (x, y). Feedback resistor (and cap) above it.
    Returns (amp, junction, output node)."""
    ox, oy = x + 55, y + 10
    amp = pg.place(ref, "TL074", ox, oy, unit=sec, des=(14, 30, "LEFT_BOTTOM"), name=False)
    out, inm, inp = SECTION[sec]
    jx, kx = x, ox + 60
    nin = rf.nets["1"]
    nout = rf.nets["2"]
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
    if sec == 1:   # this unit carries the supply pins
        vcc, vee = amp["4"], amp["11"]
        pg.wire([vcc, vcc], "+12V", label=(vcc[0] + 3, vcc[1] - 2, "LEFT_BOTTOM"))
        pg.wire([vee, vee], "-12V", label=(vee[0] + 3, vee[1] + 8, "LEFT_BOTTOM"))
    return amp, (jx, y), (kx, oy)


def jack_in(pg, part, x, y_tip):
    """Input jack, tip (pin 3) at (x + 25, y_tip) pointing right. Sleeve to GND;
    the switch lug to GND or to a net port."""
    j = pg.place(part.ref, "JACK", x, y_tip - 10, des=(-25, -22, "LEFT_BOTTOM"), name=False)
    pg.text(x - 25, y_tip + 20, part.label, 10)
    s = j["1"]
    pg.wire([s, (s[0], s[1] - 20), (s[0] + 20, s[1] - 20)], "GND")
    pg.gnd(s[0] + 20, s[1] - 20, 90)
    tn = part.nets.get("2")
    if tn == "GND":
        pg.stub_gnd(j["2"], "right", 20)
    elif tn:
        pg.stub_port(j["2"], tn, "IN", "right", 20)
    return j


def jack_out(pg, part, x, y_tip):
    """Output jack, mirrored: tip at (x - 25, y_tip) pointing left; switch lug open."""
    j = pg.place(part.ref, "JACK", x, y_tip - 10, mirror=True, des=(6, -22, "LEFT_BOTTOM"), name=False)
    pg.text(x - 5, y_tip + 20, part.label, 10)
    s = j["1"]
    pg.wire([s, (s[0], s[1] - 20), (s[0] - 20, s[1] - 20)], "GND")
    pg.gnd(s[0] - 20, s[1] - 20, 270)
    return j


# ---------------------------------------------------------------- pages
def mono_strip(pg, P, k, x0, t0):
    """Mono channel k. x0: left edge; t0: row of the follower output, from the top."""
    yu = Y(t0)
    rv, r = 3 * k - 2, 5 * k - 4
    jp, lv, pan, snd, sw = P[f"J{k}"], P[f"RV{rv}"], P[f"RV{rv + 1}"], P[f"RV{rv + 2}"], P[f"SW{k}"]
    ra, rb, rc, rd, re = (P[f"R{r + i}"] for i in range(5))
    u, sec = opamp_of("FOL", str(k))
    pg.text(x0, yu - 112, f"Channel {k} (mono)", 12)

    xj = x0 + 30
    j = jack_in(pg, jp, xj, yu - 40)
    xp = xj + 85
    lvp = pot(pg, lv, xp, yu - 10, lv.label)
    pg.wire([j["3"], (xp, yu - 40), lvp["3"]], f"IN{k}")
    pg.stub_gnd(lvp["1"], "down", 10)
    node = follower(pg, u, sec, xp + 50, yu + 10, f"BF{k}")
    pg.wire([lvp["2"], (xp + 50, yu + 10)], f"LV{k}")

    # mute: ATE1D upside down, pins up; pin 3 = ON (follower), 1 = MUTE (GND), 2 = common
    xs = node[0] + 45
    swp = pg.place(sw.ref, "SPDT", xs, yu + 50, 180, des=(-22, 34, "LEFT_BOTTOM"), name=False)
    pg.text(xs - 22, yu + 92, sw.label, 9)
    pg.wire([node, (xs - 10, yu), swp["3"]], f"BF{k}")
    pg.wire([swp["1"], (xs + 30, yu + 20)], "GND")
    pg.gnd(xs + 30, yu + 20, 0)
    yc = yu - 20
    s0 = (xs + 80, yc)
    pg.wire([swp["2"], (xs, yc), s0], f"CH{k}")

    # send, after the mute
    sp = pot(pg, snd, xs + 80, yc + 40)
    pg.text(xs + 86, yc + 112, snd.label, 9)
    pg.wire([s0, sp["3"]], f"CH{k}")
    pg.stub_gnd(sp["1"], "down", 10)
    a_re = hpart(pg, re, xs + 130, yc + 60)
    pg.wire([sp["2"], a_re["1"]], f"SD{k}")
    pg.stub_port(a_re["2"], "SUM_S", "OUT", "right")

    # pan network
    xc = xs + 270
    pg.wire([s0, (xc, yc)], f"CH{k}")
    a_ra = vpart(pg, ra, xc, yc - 60, top_pin="2")    # pin 1 at the bottom, on CH
    a_rb = vpart(pg, rb, xc, yc + 20, top_pin="1")    # pin 1 on top, on CH
    pg.wire([(xc, yc), a_ra["1"]], f"CH{k}")
    pg.wire([(xc, yc), a_rb["1"]], f"CH{k}")
    pl, pr_ = (xc + 60, yc - 60), (xc + 60, yc + 60)
    pg.wire([a_ra["2"], pl], f"PL{k}")
    pg.wire([a_rb["2"], pr_], f"PR{k}")
    pp = pot(pg, pan, xc + 60, yc - 20)
    pg.text(xc + 68, yc + 40, pan.label, 9)
    pg.wire([pl, pp["3"]], f"PL{k}")
    pg.wire([pr_, pp["1"]], f"PR{k}")
    pg.stub_gnd(pp["2"], "right", 15)
    a_rc = hpart(pg, rc, xc + 80, yc - 60)
    a_rd = hpart(pg, rd, xc + 80, yc + 60)
    pg.wire([pl, a_rc["1"]], f"PL{k}")
    pg.wire([pr_, a_rd["1"]], f"PR{k}")
    pg.stub_port(a_rc["2"], "SUM_L", "OUT", "right")
    pg.stub_port(a_rd["2"], "SUM_R", "OUT", "right")


def mono_page(pr, P):
    pg = MixerPage(pr, "Mono channels", 1)
    for i, k in enumerate(MONO):
        col, row = divmod(i, 3)
        mono_strip(pg, P, k, 20 + col * 810, 150 + row * 300)
    pg.text(40, Y(1060), "Every mono channel: LEVEL -> follower -> MUTE -> pan network (10k + B10k + 10k, wiper "
                         "to GND) -> 100k into the L and R buses; SEND taps after the mute (post-fader).", 10)
    pg.text(40, Y(1080), "MUTE: ATE1D toggle, common = pin 2, pin 3 = ON, pin 1 = MUTE. PAN: fully CCW = left. "
                         "Net ports with the same name connect (SUM_L, SUM_R, SUM_S: page 3).", 10)
    return pg


def stereo_strip(pg, P, c, x0, t0):
    """Stereo channel c (7 or 8): L row at t0, R row 160 below."""
    i = c - 7
    jl, jr, rv, r = P[f"J{7 + 2 * i}"], P[f"J{8 + 2 * i}"], P[f"RV{19 + 2 * i}"], 31 + 5 * i
    snd, sw = P[f"RV{20 + 2 * i}"], P[f"SW{c}"]
    r_l, r_r, r_al, r_ar, r_s = (P[f"R{r + k}"] for k in range(5))
    yl = Y(t0)
    yr = yl + 160
    pg.text(x0, yl - 112, f"Channel {c} (stereo)", 12)
    xj = x0 + 30
    xp = xj + 85
    xs = xp + 200
    for row, (jack, unit, side) in enumerate(((jl, 1, "L"), (jr, 2, "R"))):
        yu = yl + 160 * row
        j = jack_in(pg, jack, xj, yu - 40)
        g = pot2(pg, rv, unit, xp, yu - 10, rv.label if row == 0 else None)
        pg.wire([j["3"], (xp, yu - 40), g["3" if unit == 1 else "6"]], f"IN{c}{side}")
        pg.stub_gnd(g["1" if unit == 1 else "4"], "down", 10)
        u, sec = opamp_of("FOL", f"{c}{side}")
        node = follower(pg, u, sec, xp + 60, yu + 10, f"BF{c}{side}")
        pg.wire([g["2" if unit == 1 else "5"], (xp + 60, yu + 10)], f"LV{c}{side}")
        s = pg.place(sw.ref, "DPDT", xs, yu + 10, 0, unit=unit, des=(-14, -16, "LEFT_BOTTOM"), name=False)
        on, com, mute = ("1", "2", "3") if unit == 1 else ("4", "5", "6")
        pg.wire([node, s[on]], f"BF{c}{side}")
        pg.wire([s[mute], (xs - 30, yu + 20)], "GND")
        pg.gnd(xs - 30, yu + 20, 0)
    pg.text(xs - 40, yl + 58, sw.label, 9)
    # bus resistors and the send average
    yc_l, yc_r = yl + 10, yr + 10
    jl_, jr_ = (xs + 50, yc_l), (xs + 50, yc_r)
    com_a = _pin(pg, sw.ref, "2")
    com_b = _pin(pg, sw.ref, "5")
    pg.wire([com_a, jl_], f"CH{c}L")
    pg.wire([com_b, jr_], f"CH{c}R")
    a_al = vpart(pg, r_al, xs + 50, yc_l + 20, top_pin="1", texts_left=True)
    a_ar = vpart(pg, r_ar, xs + 50, yc_r - 60, top_pin="2", texts_left=True)
    pg.wire([jl_, a_al["1"]], f"CH{c}L")
    pg.wire([jr_, a_ar["1"]], f"CH{c}R")
    av = (xs + 50, yc_l + 80)
    pg.wire([a_al["2"], av], f"AV{c}")
    pg.wire([a_ar["2"], av], f"AV{c}")
    sp = pot(pg, snd, xs + 90, yc_l + 90)        # enter the CW pin from above: the tab pin sits left of it
    pg.text(xs + 98, yc_l + 140, snd.label, 9)
    pg.wire([av, (xs + 90, yc_l + 80), sp["3"]], f"AV{c}")
    pg.stub_gnd(sp["1"], "down", 10)
    a_s = hpart(pg, r_s, xs + 140, yc_l + 110)
    pg.wire([sp["2"], a_s["1"]], f"SD{c}")
    pg.stub_port(a_s["2"], "SUM_S", "OUT", "right")
    a_l = hpart(pg, r_l, xs + 230, yc_l)
    a_r = hpart(pg, r_r, xs + 230, yc_r)
    pg.wire([jl_, a_l["1"]], f"CH{c}L")
    pg.wire([jr_, a_r["1"]], f"CH{c}R")
    pg.stub_port(a_l["2"], "SUM_L", "OUT", "right")
    pg.stub_port(a_r["2"], "SUM_R", "OUT", "right")


def _pin(pg, ref, num):
    for c in pg.comps:
        if c["ref"] == ref and num in c["pins"]:
            return c["pins"][num]
    raise KeyError((ref, num))


def stereo_page(pr, P):
    pg = MixerPage(pr, "Stereo channels and inputs", 2)
    stereo_strip(pg, P, 7, 20, 160)
    stereo_strip(pg, P, 8, 20, 590)

    # Clouds return: dual-gang level straight into the buses
    x0, t0 = 840, 160
    yl = Y(t0)
    pg.text(x0, yl - 112, "Return (Clouds L/R)", 12)
    xj, xp = x0 + 30, x0 + 115
    for row, (ref, unit, side, rr) in enumerate((("J11", 1, "L", "R41"), ("J12", 2, "R", "R42"))):
        yu = yl + 130 * row
        j = jack_in(pg, P[ref], xj, yu - 40)
        g = pot2(pg, P["RV23"], unit, xp, yu - 10, P["RV23"].label if row == 0 else None)
        pg.wire([j["3"], (xp, yu - 40), g["3" if unit == 1 else "6"]], f"RT_{side}")
        pg.stub_gnd(g["1" if unit == 1 else "4"], "down", 10)
        a = hpart(pg, P[rr], xp + 60, yu + 10)
        pg.wire([g["2" if unit == 1 else "5"], a["1"]], f"RW_{side}")
        pg.stub_port(a["2"], f"SUM_{side}", "OUT", "right")

    # drum mixer in: centred, 300k into each bus
    t0 = 520
    yu = Y(t0)
    pg.text(x0, yu - 112, "Drums (drum mixer output, centred)", 12)
    j = jack_in(pg, P["J13"], xj, yu - 40)
    dp = pot(pg, P["RV24"], xp, yu - 10, P["RV24"].label)
    pg.wire([j["3"], (xp, yu - 40), dp["3"]], "DRM")
    pg.stub_gnd(dp["1"], "down", 10)
    jn = (xp + 50, yu + 10)
    pg.wire([dp["2"], jn], "DRW")
    a = hpart(pg, P["R43"], xp + 80, yu + 10)
    pg.wire([jn, a["1"]], "DRW")
    pg.stub_port(a["2"], "SUM_L", "OUT", "right")
    b = hpart(pg, P["R44"], xp + 80, yu + 70)
    pg.wire([jn, (xp + 50, yu + 70), b["1"]], "DRW")
    pg.stub_port(b["2"], "SUM_R", "OUT", "right")

    # FX IN: the drum mixer's send joins the send bus
    t0 = 760
    yu = Y(t0)
    pg.text(x0, yu - 112, "FX IN (drum mixer send -> send bus)", 12)
    j = jack_in(pg, P["J14"], xj, yu - 40)
    a = hpart(pg, P["R45"], xp + 40, yu - 40)
    pg.wire([j["3"], a["1"]], "FXI")
    pg.stub_port(a["2"], "SUM_S", "OUT", "right")

    pg.text(40, Y(1060), "Stereo channels: R input takes L when unpatched. Dual-gang LEVEL, two followers, DPDT MUTE "
                         "(pins 1/4 = ON, 3/6 = MUTE), 200k into each bus; SEND gets (L+R)/2.", 10)
    pg.text(40, Y(1080), "RETURN R takes RETURN L when unpatched. DRUMS sits in the centre at -3.5 dB per side, "
                         "like a centred mono channel. No send on RETURN or DRUMS.", 10)
    return pg


def bus_page(pr, P):
    pg = MixerPage(pr, "Buses, master, outputs, power", 3)
    pg.text(60, Y(55), "Buses (inverting summers, 100k || 22p), MASTER (dual A10k), output stages (gain -2)", 12)
    x_in = 160
    rows = {"L": 230, "R": 450}
    for side, t in rows.items():
        y = Y(t)
        u, sec = opamp_of("SUM", side)
        amp, jn, kn = inverting(pg, u, sec, x_in, y, P[{"L": "R46", "R": "R47"}[side]],
                                P[{"L": "C1", "R": "C2"}[side]])
        pg.wire([(x_in - 40, y), jn], f"SUM_{side}")
        pg.port(x_in - 40, y, f"SUM_{side}", "IN", "left")
        # master gang
        xm = kn[0] + 80
        unit = 1 if side == "L" else 2
        g = pot2(pg, P["RV25"], unit, xm, kn[1], P["RV25"].label if side == "L" else None)
        pg.wire([kn, g["3" if unit == 1 else "6"]], f"MIX_{side}")
        pg.stub_gnd(g["1" if unit == 1 else "4"], "down", 10)
        # output stage
        rin, rfb, rser = (P[r] for r in {"L": ("R49", "R50", "R51"), "R": ("R52", "R53", "R54")}[side])
        a_in = hpart(pg, rin, xm + 40, kn[1] + 20)
        pg.wire([g["2" if unit == 1 else "5"], a_in["1"]], f"MST_{side}")
        uo, so = opamp_of("OUT", side)
        amp2, jn2, kn2 = inverting(pg, uo, so, xm + 100, kn[1] + 20, rfb)
        pg.wire([a_in["2"], jn2], f"NO_{side}")
        a_s = hpart(pg, rser, kn2[0] + 20, kn2[1])
        pg.wire([kn2, a_s["1"]], f"OA_{side}")
        jo = jack_out(pg, P[{"L": "J16", "R": "J17"}[side]], a_s["2"][0] + 60, kn2[1])
        pg.wire([a_s["2"], jo["3"]], f"OUT_{side}")

    # send bus
    t = 690
    y = Y(t)
    pg.text(60, y - 125, "Send bus -> inverter -> SEND (to Clouds IN L)", 12)
    u, sec = opamp_of("SUM", "S")
    amp, jn, kn = inverting(pg, u, sec, x_in, y, P["R48"], P["C3"])
    pg.wire([(x_in - 40, y), jn], "SUM_S")
    pg.port(x_in - 40, y, "SUM_S", "IN", "left")
    a_in = hpart(pg, P["R55"], kn[0] + 40, kn[1] + 20)
    pg.wire([kn, (kn[0] + 20, kn[1]), (kn[0] + 20, kn[1] + 20), a_in["1"]], "MIX_S")
    uo, so = opamp_of("OUT", "S")
    amp2, jn2, kn2 = inverting(pg, uo, so, kn[0] + 100, kn[1] + 20, P["R56"])
    pg.wire([a_in["2"], jn2], "NO_S")
    a_s = hpart(pg, P["R57"], kn2[0] + 20, kn2[1])
    pg.wire([kn2, a_s["1"]], "OA_S")
    jo = jack_out(pg, P["J15"], a_s["2"][0] + 60, kn2[1])
    pg.wire([a_s["2"], jo["3"]], "SEND")

    power(pg, P)
    pg.text(40, Y(1040), "Gains at full LEVEL: mono hard-panned 0.95, centred 0.65 per side (-3.4 dB); stereo, "
                         "RETURN 1.0; DRUMS 0.67 per side; sends 1.0. MASTER at full = those values.", 10)
    pg.text(40, Y(1060), "Op-amps: section 1 of each TL074 has the supply pins, so it does a summer or output "
                         "stage. Followers: U1 2-4 = ch 1-3, U2 2-4 = ch 4-6, U3 2-4 = 7L, 7R, 8L, U4.2 = 8R.", 10)
    pg.text(40, Y(1080), "Power: series 1N5819 per rail (-12 V: cathode to the header), 10R, 10 uF bulk, "
                         "100n per TL074 per rail. Header pins 13-16 (+5V, CV, gate) unused.", 10)
    return pg


def power(pg, P):
    x0, t0 = 980, 120
    pg.text(x0 - 40, Y(t0 - 65), "Power: 16-pin Eurorack header (red stripe = pin 1 = -12 V)", 12)
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J18", "HDR", xh, yh, des=(-30, -45, "LEFT_BOTTOM"), value_at=(-30, 52, "LEFT_BOTTOM"))
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

    # protection: header -> 1N5819 -> 10R -> rail, 10 uF to GND
    xa = x0 + 330
    for k, (port, d, r, c, rail, gnd_top) in enumerate((("P12_IN", "D1", "R58", "C4", "+12V", False),
                                                        ("N12_IN", "D2", "R59", "C5", "-12V", True))):
        y = Y(t0 + 10 + 120 * k)
        dp = hpart(pg, P[d], xa, y, left_pin="2" if rail == "+12V" else "1")
        pg.wire([(xa - 20, y), dp["2" if rail == "+12V" else "1"]], port)
        pg.port(xa - 20, y, port, "IN", "left")
        mid = "P12_D" if rail == "+12V" else "N12_D"
        rp = hpart(pg, P[r], xa + 60, y)
        pg.wire([dp["1" if rail == "+12V" else "2"], rp["1"]], mid)
        jn = (xa + 130, y)
        pg.wire([rp["2"], jn], rail)
        pg.wire([jn, (xa + 160, y)], rail)
        pg.port(xa + 160, y, rail, "OUT", "right")
        cp = vpart(pg, P[c], xa + 130, y + 20, top_pin="2" if rail == "+12V" else "1")
        pg.wire([jn, cp["2" if rail == "+12V" else "1"]], rail)
        pg.stub_gnd(cp["1" if rail == "+12V" else "2"], "down", 10)

    # decoupling, one pair per TL074
    pg.text(x0 - 40, Y(t0 + 280), "Decoupling: 100n per TL074 per rail, next to the chip", 12)
    for i in range(4):
        x, top = x0 + 40 + i * 120, Y(t0 + 330)
        cp, cn = P[f"C{6 + 2 * i}"], P[f"C{7 + 2 * i}"]
        a = vpart(pg, cp, x, top + 20, top_pin="1")     # pin 1 = +12V on top
        b = vpart(pg, cn, x, top + 80, top_pin="1")     # pin 1 = GND on top
        node = (x, top + 70)
        pg.wire([a["2"], node], "GND")
        pg.wire([node, b["1"]], "GND")
        pg.wire([node, (x - 15, top + 70)], "GND")
        pg.gnd(x - 15, top + 70, 270)
        pg.wire([a["1"], (x, top + 5), (x - 20, top + 5)], "+12V")
        pg.port(x - 20, top + 5, "+12V", "IN", "left")
        pg.wire([b["2"], (x, top + 135), (x - 20, top + 135)], "-12V")
        pg.port(x - 20, top + 135, "-12V", "IN", "left")
        pg.text(x + 8, top + 160, f"U{i + 1}", 10)


# ---------------------------------------------------------------- checks
def page_check(pg, parts):
    drawn = {(c["ref"], num) for c in pg.comps if c["ref"] for num in c["pins"]}
    sub = []
    for p in parts:
        nets = {pid: n for pid, n in p.nets.items() if (p.ref, pid) in drawn}
        if nets:
            sub.append(Part(p.ref, p.kind, p.value, nets))
    return ee.check(pg, sub, lambda part, pid: pid)


def coverage(pages, parts):
    seen = collections.Counter((c["ref"], num) for pg in pages for c in pg.comps if c["ref"] for num in c["pins"])
    problems = []
    for p in parts:
        for pid in p.nets:
            if seen[(p.ref, pid)] != 1:
                problems.append(f"{p.ref}.{pid} drawn {seen[(p.ref, pid)]} times")
    return problems


def main():
    pr = MixerProject()
    parts = all_parts()
    P = {p.ref: p for p in parts}
    pages = [mono_page(pr, P), stereo_page(pr, P), bus_page(pr, P)]
    bad = coverage(pages, parts)
    for pg in pages:
        bad += [f"{pg.title}: {b}" for b in page_check(pg, parts)]
    for b in bad:
        print("PROBLEM:", b)
    pr.write(pages, OUT)
    for pg in pages:
        ee.render(pr, pg, PREVIEW.format(pg.title.lower().replace(",", "").replace(" ", "-")))
    n = sum(1 for pg in pages for c in pg.comps if c["ref"])
    print(f"{OUT}: {n} part units on {len(pages)} pages, {len(bad)} problems")


if __name__ == "__main__":
    main()
