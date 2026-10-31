"""Envy as an EasyEDA Pro project (.epro2): the schematic of its one board,
and (from pcb.py) the placed PCB and the panel as a PCB.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the file
format, the connectivity check and the previews, and on Offset's exporter
(../../../attenuverter/hardware/tools) for the footprints and drawings the two
modules share: the Alpha pot, DIP-14 on 7.62 mm, TO-92, the 2-lead 3 mm LED,
the Dailywell 2MS1 toggle and its symbol, standing resistors, jack, pot and
inverting-stage blocks. Library parts come from the two caches of your
MorrisSynth export (morrissynth-parts.epru, stereo-mixer-parts.epru): TL074ACN
symbol, WQP518MA jack, PTV09A pot symbol, LR1F resistors, FG28 100n, SR305 1u,
1N5819, the DO-35 footprint, net ports, ground flag, sheet frame. Drawn or
generated here, in the same style and with real pin numbers:

  footprints  a standing DO-35 (2.54 mm), a 1 uF film box (5.08 mm), a 6.3 mm
              electrolytic, the 2 x 5 shrouded Eurorack header
  symbols     BC548 (TO-92 1 C, 2 B, 3 E), a red LED, a polarised cap, the
              10-pin header

Pages: one per channel (gate input and comparator, burst, sustain; MODE,
buffers, steering and timing; OUT, INV, LED, loop Schmitt), and one for the
shared references, power and decoupling. Every block ends in net ports;
ports with the same name connect across the pages.

Run from envelope/hardware/tools:  python easyeda_export.py
"""
import collections
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLAITSY = os.path.normpath(os.path.join(HERE, "..", "..", "..", "plaitsy", "hardware", "tools"))
OFFSET = os.path.normpath(os.path.join(HERE, "..", "..", "..", "attenuverter", "hardware", "tools"))
sys.path.insert(0, PLAITSY)
import easyeda_export as ee                      # noqa: E402  (the Plaitsy stripboard exporter)
sys.path.remove(PLAITSY)
from easyeda_export import (Doc, Symbol, meta, attr_payload, Y, render, check,   # noqa: E402
                            new_uuid, W, H, H_TXT, V_TXT)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("envy_circuit", os.path.join(HERE, "circuit.py"))
pcb = _load("envy_pcb", os.path.join(HERE, "pcb.py"))
panel_pcb = _load("envy_panel_pcb", os.path.join(HERE, "panel_pcb.py"))
off = _load("offset_export", os.path.join(OFFSET, "easyeda_export.py"))    # footprints, symbols, blocks
SECTION = circuit.SECTION
UNIT = off.UNIT
Footprint, MIL = off.Footprint, off.MIL

NAME = "Envy"
OUT = os.path.join(HERE, "..", "easyeda", "Envy.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "envy-easyeda-{}.png")
LIBFILES = off.LIBFILES

DEV = dict(off.DEV)
DEV.update({"C1u": "bf1fe821a3774bf48d0873f872221180",      # SR305C105KAR, 1 uF ceramic, 5.08 mm
            "DO35": "c0160a3f74384e849dc1cc5a24d54846"})    # 1N4148 (its DO-35 footprint; no cached symbol)
ee.DEV = DEV
off.DEV = DEV
R_NEW = {"100k": ("LR1F100K", "100kΩ"), "100R": ("LR1F100R", "100Ω"), "1k5": ("LR1F1K5", "1.5kΩ"),
         "27k": ("LR1F27K", "27kΩ"), "68k": ("LR1F68K", "68kΩ")}


# ---------------------------------------------------------------- footprints
def fp_diode_vertical():
    """DO-35 standing, 2.54 mm: the body over pad 1 (the cathode, square), the bent lead to pad 2."""
    f = Footprint("DIODE-TH-VERTICAL-P2.54", "D?")
    f.pad(1, 0, 1.27, 0.8, 1.6, square=True)
    f.pad(2, 0, -1.27, 0.8, 1.6)
    f.circle(0, 1.27, 1.2)
    f.line(-1.2, 2.9, 1.2, 2.9)                    # the band: cathode end
    return f


def fp_film():
    """1 uF / 63 V polyester box, 5.08 mm pitch (WIMA MKS2 class): body 7.5 x 5.0 mm."""
    f = Footprint("CAP-FILM-P5.08-7.5x5.0", "C?")
    f.pad(1, -2.54, 0, 0.9, 1.6)
    f.pad(2, 2.54, 0, 0.9, 1.6)
    f.rect(-3.75, -2.5, 3.75, 2.5)
    return f


def fp_elec():
    """Radial electrolytic, 6.3 mm can, 2.5 mm pitch; pad 2 is + (square)."""
    f = Footprint("CAP-ELEC-D6.3-P2.50", "C?")
    f.pad(1, -1.25, 0, 0.9, 1.6)
    f.pad(2, 1.25, 0, 0.9, 1.6, square=True)
    f.circle(0, 0, 3.25)
    f.line(2.6, -2.2, 2.6, -1.2)                   # + mark beside pad 2
    f.line(2.1, -1.7, 3.1, -1.7)
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


def fp_header(n):
    """1 x n 2.54 mm pin header (male on the faceplate, female socket on the main board), pin 1 square."""
    f = Footprint(f"HDR-1x{n}-P2.54", "H?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.27, -1.27, x0 + (n - 1) * 2.54 + 1.27, 1.27)
    return f


# ------------------------------------------------------------------ symbols
def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.1", "H?", [NAME])
    half = n * 5
    s.rect(-10, -half - 5, 10, half + 5)
    for i in range(n):
        s.pin(str(i + 1), str(i + 1), -20, -half + 5 + 10 * i, 0, show=True, edge=-10)
    return s


def npn_symbol():
    """BC548, TO-92 pinout C B E = 1 2 3."""
    s = Symbol("BC548", "BC548.1", "Q?", [NAME])
    s.poly([(-20, 0), (-5, 0)])
    s.poly([(-5, -12), (-5, 12)])
    s.poly([(-5, -4), (10, -14), (10, -20)])
    s.poly([(-5, 4), (10, 14), (10, 20)])
    s.poly([(10, 14), (3, 13), (6, 8), (10, 14)], closed=True, fill="#000000")
    s.text(-18, -4, "B", 6)
    s.pin("2", "B", -20, 0, 0)
    s.pin("1", "C", 10, -20, 90)
    s.pin("3", "E", 10, 20, 270)
    return s


def led_symbol():
    s = Symbol("LED 3mm red", "LED_RED.1", "D?", [NAME])
    s.poly([(-20, 0), (-6, 0)])
    s.poly([(-6, -6), (6, 0), (-6, 6), (-6, -6)], closed=True, fill="#E02020")
    s.poly([(6, -6), (6, 6)])
    s.poly([(6, 0), (20, 0)])
    for x0 in (-1, 4):
        s.poly([(x0, -9), (x0 + 5, -14)])
        s.poly([(x0 + 5, -14), (x0 + 1, -13), (x0 + 4, -10), (x0 + 5, -14)], closed=True, fill="#E02020")
    s.pin("1", "A", -30, 0, 0)
    s.pin("2", "K", 30, 0, 180)
    return s


def cp_symbol():
    """Polarised capacitor: pin 2 (right) is +."""
    s = Symbol("Electrolytic capacitor", "CPOL.1", "C?", [NAME])
    s.poly([(-20, 0), (-4, 0)])
    s.poly([(-4, -8), (-4, 8)])
    s.poly([(4, -8), (4, 8)])
    s.poly([(4, 0), (20, 0)])
    s.poly([(8, -10), (12, -10)])
    s.poly([(10, -12), (10, -8)])
    s.pin("1", "-", -20, 0, 0)
    s.pin("2", "+", 20, 0, 180)
    return s


HDR_ROWS = 5


def hdr10_symbol():
    """2 x 5 Eurorack power header: odd pins on the left, even on the right, pin 1 at the top (-12 V)."""
    s = Symbol("Eurorack power 2x5", "HDR2X5.1", "J?", [NAME])
    s.rect(-20, -25, 20, 25)
    for i in range(HDR_ROWS):
        y = -20 + 10 * i
        s.pin(str(2 * i + 1), str(2 * i + 1), -30, y, 0, show=True, edge=-20)
        s.pin(str(2 * i + 2), str(2 * i + 2), 30, y, 180, show=True, edge=20)
    return s


# ------------------------------------------------------------------ project
STANDING = ["R1k", "R10k", "R10R"] + ["R" + v for v in R_NEW]   # every resistor stands up (dev key + "V")


class MPage(off.MPage):
    page_count = "5"

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


off.STANDING[:] = STANDING                         # MPage.place in Offset's exporter stands these up


class MProject(off.MProject):
    def _new_devices(self):
        r1k = self.device_attrs("R1k")
        for val, (mpn, value) in R_NEW.items():
            a = dict(r1k)
            a.update({"Manufacturer Part": mpn, "Value": value, "Supplier Part": "", "Datasheet": "",
                      "LCSC Part Name": f"Metal film resistor {value} ±1% 600mW",
                      "Description": f"Metal film resistor {value} ±1% 600mW (TE LR1F series)"})
            self._device("R" + val, mpn, a, ["Resistors", "Through Hole Resistors"])
        fps = {"RV": self._footprint(off.fp_res_vertical()), "DV": self._footprint(fp_diode_vertical()),
               "DIP14": self._footprint(off.fp_dip(14, "DIP-14-W7.62-P2.54")), "TO92": self._footprint(off.fp_to92()),
               "LED2": self._footprint(off.fp_led2()), "POT": self._footprint(off.fp_alpha_pot()),
               "TOGGLE": self._footprint(off.fp_toggle()), "FILM": self._footprint(fp_film()),
               "ELEC": self._footprint(fp_elec()), "HDR10": self._footprint(fp_box_header(10)),
               "HDR13": self._footprint(fp_header(13))}
        for key in STANDING:                                      # each resistor again, standing up
            a = self.device_attrs(key)
            self._copy(key + "V", key, a["Manufacturer Part"], ["Resistors", "Through Hole Resistors"],
                       Footprint=fps["RV"])
        self._copy("TL074N", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch")
        for val, mpn in (("A1M", "Alpha RD901F-40-15R1 A1M"), ("A100k", "Alpha RD901F-40-15R1 A100K")):
            self._copy("POT" + val, "POT", f"Alpha 9mm {val}", ["Potentiometers"], Footprint=fps["POT"],
                       Name="={Value}", Value=val, **{"Manufacturer Part": mpn, "Supplier Part": "", "Datasheet": "",
                                                      "Description": f"Alpha 9 mm vertical pot {val}, T18 shaft "
                                                                     "(Thonk). Pin 3 = CW end, lugs 4 / 5"})
        schottky_sym = self.device_attrs("D5819")["Symbol"]           # pin 1 = cathode
        for key, mpn, desc in (("D4148", "1N4148", "Small-signal diode 100 V 200 mA, DO-35, standing"),
                               ("DBAT85", "BAT85", "Schottky diode 30 V 200 mA, DO-35, standing")):
            a = dict(self.device_attrs("DO35"))
            a.update({"Symbol": schottky_sym, "Footprint": fps["DV"], "Manufacturer Part": mpn, "Name": mpn,
                      "LCSC Part Name": mpn, "Supplier Part": "", "Manufacturer": "", "Datasheet": "",
                      "Description": desc})
            self._device(key, mpn, a, ["Diodes"])
        film = dict(self.device_attrs("C1u"))
        film.update({"Footprint": fps["FILM"], "Manufacturer Part": "MKS2 1uF 63V 5mm", "Supplier Part": "",
                     "Datasheet": "", "Value": "1uF", "Tolerance": "±10%",
                     "Description": "1 uF 63 V polyester film, 5.08 mm pitch (WIMA MKS2 or similar)"})
        self._device("CF1u", "1uF film", film, ["Capacitors"])
        dnf = dict(film, **{"Add into BOM": "no",
                            "Description": "1 uF film, NOT FITTED by default: fit to double this channel's times"})
        self._device("CF1uDNF", "1uF film (not fitted)", dnf, ["Capacitors"])
        new = [
            ("NPN", npn_symbol(), "BC548", "Q?", fps["TO92"], "NPN 30 V 100 mA, TO-92: 1 C, 2 B, 3 E"),
            ("LED", led_symbol(), "LED 3mm red", "D?", fps["LED2"], "3 mm red LED, pad 1 (square) = anode"),
            ("TOGGLE_SPDT", off.toggle_symbol(), "Dailywell 2MS1T1B1M2QES", "SW?", fps["TOGGLE"],
             "Sub-mini toggle SPDT ON-ON, PC terminals at 2.54 mm, 6 mm bushing (Thonk). Mounted with pin 3 at "
             "the bottom, lever up joins 2-3 (Dailywell's table; ring one out before soldering)"),
            ("CP47u", cp_symbol(), "47uF 25V", "C?", fps["ELEC"], "Electrolytic 47 uF 25 V, 6.3 mm, pad 2 = +"),
            ("HDR10", hdr10_symbol(), "Box header 2x5 2.54mm", "J?", fps["HDR10"],
             "Shrouded 2 x 5 Eurorack power header: pins 1-2 -12 V (red stripe), 3-8 GND, 9-10 +12 V"),
            ("HDR13", header_symbol(13), "Pin header 1x13", "H?", fps["HDR13"],
             "1 x 13 2.54 mm: male pin header on the faceplate (HF1-HF4), female socket on the main board (H1-H4)"),
        ]
        for key, sym, title, desig, fp, desc in new:
            su = self._symbol(sym)
            attrs = {"Name": "={Manufacturer Part}", "Manufacturer Part": title, "Designator": desig,
                     "Add into BOM": "yes", "Convert to PCB": "yes", "Symbol": su, "Footprint": fp,
                     "3D Model": "", "3D Model Title": "", "3D Model Transform": "", "Description": desc}
            self._device(key, title, attrs)

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
                   "description": "Envy: four Moritz Klein envelopes (MKI x ES.EDU EG): attack, decay/release, "
                                  "sustain, LOOP, OUT and INV per channel, gates normalled down. 6x TL074. "
                                  "Two stacked PCBs (faceplate + main board), 16HP.",
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
        if part.ref == "C902":
            return "C1u"                                      # AXIS: ceramic
        return {"100n": "C100n", "1u": "CF1u", "1u DNF": "CF1uDNF"}[part.value]
    if part.kind == "POT":
        return "POT" + part.value
    return {"CP": "CP47u", "TL074": "TL074N", "TOGGLE": "TOGGLE_SPDT"}.get(part.kind, part.kind)


off.dev_of = dev_of                                    # Offset's hpart / vpart / blocks look devices up here


# ---------------------------------------------------------------- drawing helpers
hpart, vpart, supply = off.hpart, off.vpart, off.supply


def jack_block(pg, part, jx, jy, tip_kind):
    """Thonkiconn: sleeve to GND, the switch lug to a net port (or a ground flag), the tip to a net port."""
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


def roles(k):
    """(ref, section) of channel k's six op-amp sections (circuit.opamp_parts)."""
    a = k % 2 == 1
    base = 0 if k <= 2 else 3
    u = [f"U{base + 1}", f"U{base + 2}", f"U{base + 3}"]
    return {"gate": (u[0], "A" if a else "D"), "burst": (u[0], "B" if a else "C"),
            "inbuf": (u[1], "A" if a else "D"), "outbuf": (u[1], "B" if a else "C"),
            "schmitt": (u[2], "A" if a else "D"), "inv": (u[2], "B" if a else "C")}


def opamp(pg, role, x, y):
    """A TL074 section with its + input at (x, y); returns (out, in-, in+) points."""
    ref, sec = role
    ox, oy = x + 40, y - 10
    amp = pg.place(ref, "TL074N", ox, oy, unit=UNIT[sec], des=(14, 30, "LEFT_BOTTOM"), name=False)
    supply(pg, amp, sec)
    pg.text(ox - 30, oy + 45, f"{ref} {sec}", 8)
    out, inm, inp = SECTION[sec]
    return amp[out], amp[inm], amp[inp]


def follower(pg, role, x, y, net):
    """Unity follower, + input at (x, y); returns the output node (15 right of the output pin)."""
    out, inm, inp = opamp(pg, role, x, y)
    node = (out[0] + 15, out[1])
    pg.wire([out, node], net)
    pg.wire([node, (node[0], node[1] - 35), (inm[0] - 15, node[1] - 35), (inm[0] - 15, inm[1]), inm], net)
    return node


def down_to_gnd(pg, part, x, y, top_pin="1"):
    """A two-pin part hanging from (x, y) to a ground flag."""
    a = vpart(pg, part, x, y, top_pin)
    other = "2" if top_pin == "1" else "1"
    pg.stub_gnd(a[other], "down", 10)
    return a


def lugs_to_gnd(pg, p):
    """The pot's mounting lugs 4 and 5 joined underneath it and grounded."""
    l4, l5 = p["4"], p["5"]
    yb = max(l4[1], l5[1]) + 10
    pg.wire([l4, (l4[0], yb), (l5[0], yb), l5], "GND")
    pg.wire([(l4[0], yb), (l4[0], yb + 10)], "GND")
    pg.gnd(l4[0], yb + 10, 0)


def pot(pg, part, px, py, mirror=False):
    p = pg.place(part.ref, dev_of(part), px, py, des=(-20, -24, "LEFT_BOTTOM"),
                 value_at=(8, -24, "LEFT_BOTTOM"), mirror=mirror)
    lugs_to_gnd(pg, p)
    return p


def rheostat(pg, part, x, y):
    """A time pot drawn left to right: pin 1 at (x, y), the wiper tied to pin 3; returns the CT end."""
    px, py = x + 18, y - 5                           # mirrored symbol: pin 1 at (-18, +5)
    p = pot(pg, part, px, py, mirror=True)
    end = (p["3"][0] + 10, p["3"][1])
    pg.wire([p["3"], end], part.nets["3"])
    pg.wire([p["2"], (end[0], p["2"][1]), end], part.nets["3"])
    pg.text(px - 18, py - 30, part.label, 9)
    return end


# ------------------------------------------------------------------ channel blocks
def gate_block(pg, P, k, x0, y0):
    """GATE port -> 10k -> GIN (100k down, clamp diode) -> gate comparator -> 1N4148 -> G (10k down) -> port."""
    r = 100 * k
    pg.port(x0, y0, f"GATE{k}", "IN", "left")
    a = hpart(pg, P[f"R{r + 1}"], x0 + 20, y0)
    pg.wire([(x0, y0), a["1"]], f"GATE{k}")
    j1, j2 = (a["2"][0] + 20, y0), (a["2"][0] + 50, y0)
    pg.wire([a["2"], j1], f"GIN{k}")
    pg.wire([j1, j2], f"GIN{k}")
    rd = vpart(pg, P[f"R{r + 2}"], j1[0], y0 + 20)
    pg.wire([j1, rd["1"]], f"GIN{k}")
    pg.stub_gnd(rd["2"], "down", 10)
    dc = vpart(pg, P[f"D{r + 1}"], j2[0], y0 + 20, top_pin="1")
    pg.wire([j2, dc["1"]], f"GIN{k}")
    pg.stub_gnd(dc["2"], "down", 10)
    out, inm, inp = opamp(pg, roles(k)["gate"], j2[0] + 40, y0)
    pg.wire([j2, inp], f"GIN{k}")
    pg.stub_port(inm, "VREF", "IN", "left", 20)
    d = hpart(pg, P[f"D{r + 2}"], out[0] + 20, out[1], left_pin="2")
    pg.wire([out, d["2"]], f"GC{k}")
    g = (d["1"][0] + 20, out[1])
    pg.wire([d["1"], g], f"G{k}")
    rg = vpart(pg, P[f"R{r + 3}"], g[0], g[1] + 20)
    pg.wire([g, rg["1"]], f"G{k}")
    pg.stub_gnd(rg["2"], "down", 10)
    pg.stub_port(g, f"G{k}", "OUT", "right", 30)
    pg.text(x0 - 10, y0 - 70, f"GATE {k}: 10k in, 100k pull-down, clamp; comparator against VREF (2.55 V)", 9)


def burst_block(pg, P, k, x0, y0):
    """G port -> 1u -> HP (10k down, clamp) -> burst comparator -> 1N4148 -> N port."""
    r = 100 * k
    pg.port(x0, y0, f"G{k}", "IN", "left")
    c = hpart(pg, P[f"C{r + 1}"], x0 + 20, y0)
    pg.wire([(x0, y0), c["1"]], f"G{k}")
    h1, h2 = (c["2"][0] + 25, y0), (c["2"][0] + 55, y0)
    pg.wire([c["2"], h1], f"HP{k}")
    pg.wire([h1, h2], f"HP{k}")
    rh = vpart(pg, P[f"R{r + 5}"], h1[0], y0 + 20)
    pg.wire([h1, rh["1"]], f"HP{k}")
    pg.stub_gnd(rh["2"], "down", 10)
    dc = vpart(pg, P[f"D{r + 3}"], h2[0], y0 + 20, top_pin="1")
    pg.wire([h2, dc["1"]], f"HP{k}")
    pg.stub_gnd(dc["2"], "down", 10)
    out, inm, inp = opamp(pg, roles(k)["burst"], h2[0] + 40, y0)
    pg.wire([h2, inp], f"HP{k}")
    pg.stub_port(inm, "VREF", "IN", "left", 20)
    d = hpart(pg, P[f"D{r + 4}"], out[0] + 20, out[1], left_pin="2")
    pg.wire([out, d["2"]], f"BC{k}")
    pg.stub_port(d["1"], f"N{k}", "OUT", "right", 30)
    pg.text(x0 - 10, y0 - 70, "Burst: a 13.7 ms full-level pulse on each rising gate, overriding the sustain level", 9)


def sustain_block(pg, P, k, x, y):
    """The SUSTAIN wiper (faceplate, through the header) -> 100k -> N."""
    r = 100 * k
    pg.port(x, y, f"SUS{k}", "IN", "left")
    rs = hpart(pg, P[f"R{r + 4}"], x + 20, y)
    pg.wire([(x, y), rs["1"]], f"SUS{k}")
    pg.stub_port(rs["2"], f"N{k}", "OUT", "right", 30)
    pg.text(x - 30, y - 30, f"SUSTAIN {k} wiper (faceplate) into the buffer node", 9)


def timing_block(pg, P, k, x0, y0):
    """MODE toggle -> input buffer -> 100R -> steering diodes -> ATTACK / DEC/REL -> C_T -> output buffer."""
    r = 100 * k
    pg.port(x0, y0, f"BI{k}", "IN", "left")
    pg.text(x0 - 60, y0 + 40, f"BI {k}: the MODE {k} toggle's common (faceplate)", 9)
    bi = (x0 + 30, y0)
    pg.wire([(x0, y0), bi], f"BI{k}")
    node = follower(pg, roles(k)["inbuf"], bi[0], bi[1], f"BUF{k}")
    ra = hpart(pg, P[f"R{r + 6}"], node[0] + 20, node[1])
    pg.wire([node, ra["1"]], f"BUF{k}")
    bo = (ra["2"][0] + 20, node[1])
    pg.wire([ra["2"], bo], f"BO{k}")
    up, dn = (bo[0], bo[1] - 50), (bo[0], bo[1] + 50)
    pg.wire([bo, up], f"BO{k}")
    pg.wire([bo, dn], f"BO{k}")
    da = hpart(pg, P[f"D{r + 5}"], up[0], up[1], left_pin="2")       # attack: anode on BO
    dr = hpart(pg, P[f"D{r + 6}"], dn[0], dn[1], left_pin="1")       # release: cathode on BO
    pg.stub_port(da["1"], f"AK{k}", "OUT", "right", 30)
    pg.stub_port(dr["2"], f"RK{k}", "IN", "right", 30)
    pg.text(da["1"][0] + 50, up[1] - 8, f"to ATTACK {k}", 8)
    pg.text(dr["2"][0] + 50, dn[1] - 8, f"from DEC/REL {k}", 8)
    cx = bo[0] + 170
    ct = (cx, bo[1])
    pg.port(cx - 30, ct[1], f"CT{k}", "IN", "left")
    pg.wire([(cx - 30, ct[1]), ct], f"CT{k}")
    pg.text(cx - 80, ct[1] - 12, "the time pots' other ends", 8)
    c1, c2 = (cx + 30, ct[1]), (cx + 60, ct[1])
    pg.wire([ct, c1], f"CT{k}")
    pg.wire([c1, c2], f"CT{k}")
    ca = vpart(pg, P[f"C{r + 2}"], c1[0], c1[1] + 20)
    pg.wire([c1, ca["1"]], f"CT{k}")
    pg.stub_gnd(ca["2"], "down", 10)
    cb = vpart(pg, P[f"C{r + 3}"], c2[0], c2[1] + 20)
    pg.wire([c2, cb["1"]], f"CT{k}")
    pg.stub_gnd(cb["2"], "down", 10)
    pg.text(c2[0] + 8, c2[1] + 80, "C" + str(r + 3) + ": not fitted", 8)
    env = follower(pg, roles(k)["outbuf"], c2[0] + 30, c2[1], f"ENV{k}")
    pg.wire([c2, (c2[0] + 30, c2[1])], f"CT{k}")
    pg.stub_port(env, f"ENV{k}", "OUT", "right", 30)
    pg.text(x0 - 60, y0 - 110, "Buffer, 100R, BAT85 steering: ATTACK (AK) charges C_T, DEC/REL (RK) discharges it; "
                               "the pots are on the faceplate", 9)


def output_block(pg, P, k, x0, y0):
    """ENV -> 1k -> OUT; inverter about AXIS -> 1k -> INV; the two jacks."""
    r = 100 * k
    pg.port(x0, y0, f"ENV{k}", "IN", "left")
    ro = hpart(pg, P[f"R{r + 7}"], x0 + 20, y0)
    pg.wire([(x0, y0), ro["1"]], f"ENV{k}")
    pg.stub_port(ro["2"], f"OUT{k}", "OUT", "right", 30)
    # inverter: ENV -> 100k -> IV, feedback 100k, + on AXIS
    y1 = y0 + 140
    pg.port(x0, y1, f"ENV{k}", "IN", "left")
    ri = hpart(pg, P[f"R{r + 8}"], x0 + 20, y1)
    pg.wire([(x0, y1), ri["1"]], f"ENV{k}")
    j = (ri["2"][0] + 20, y1)
    pg.wire([ri["2"], j], f"IV{k}")
    ref, sec = roles(k)["inv"]
    ox, oy = j[0] + 55, y1 + 10
    amp = pg.place(ref, "TL074N", ox, oy, unit=UNIT[sec], des=(14, 30, "LEFT_BOTTOM"), name=False)
    supply(pg, amp, sec)
    pg.text(ox - 30, oy + 45, f"{ref} {sec}", 8)
    out, inm, inp = SECTION[sec]
    pg.wire([j, amp[inm]], f"IV{k}")
    pg.stub_port(amp[inp], "AXIS", "IN", "left", 20)
    kx = ox + 60
    rf = hpart(pg, P[f"R{r + 9}"], ox - 20, oy - 60)
    pg.wire([j, (j[0], oy - 60), rf["1"]], f"IV{k}")
    pg.wire([amp[out], (kx, oy)], f"INVO{k}")
    pg.wire([(kx, oy), (kx, oy - 60), rf["2"]], f"INVO{k}")
    rv = hpart(pg, P[f"R{r + 10}"], kx + 20, oy)
    pg.wire([(kx, oy), rv["1"]], f"INVO{k}")
    pg.stub_port(rv["2"], f"INV{k}", "OUT", "right", 30)
    pg.text(x0 - 10, y0 - 40, f"OUT {k}, and INV {k} = 2 x AXIS - ENV = 9.71 V - ENV", 9)


def led_block(pg, P, k, x, y):
    """BC548 emitter follower on ENV: collector +12 V, emitter -> 1k5 -> LED -> GND."""
    r = 100 * k
    q = pg.place(f"Q{k}", "NPN", x, y, des=(14, -6, "LEFT_BOTTOM"), value_at=(14, 4, "LEFT_BOTTOM"))
    pg.stub_port(q["2"], f"ENV{k}", "IN", "left", 30)
    c = q["1"]
    pg.wire([c, (c[0], c[1] - 20)], "+12V")
    pg.port(c[0], c[1] - 20, "+12V", "IN", "left")
    rl = vpart(pg, P[f"R{r + 11}"], q["3"][0], q["3"][1] + 10)
    pg.wire([q["3"], rl["1"]], f"QE{k}")
    pg.stub_port(rl["2"], f"LE{k}", "OUT", "right", 30)
    pg.text(x - 120, y + 40, f"LED {k} (faceplate): brightness follows ENV", 9)


def schmitt_block(pg, P, k, x0, y0):
    """Loop Schmitt: ENV on -, + from 100k to +12 V, 100k to GND, 100k from its output; -> 1N4148 -> L."""
    r = 100 * k
    pg.port(x0, y0, "+12V", "IN", "left")
    ra = hpart(pg, P[f"R{r + 12}"], x0 + 20, y0)
    pg.wire([(x0, y0), ra["1"]], "+12V")
    s2, s1 = (ra["2"][0] + 20, y0), (ra["2"][0] + 50, y0)
    pg.wire([ra["2"], s2], f"SP{k}")
    pg.wire([s2, s1], f"SP{k}")
    rb = vpart(pg, P[f"R{r + 13}"], s2[0], y0 + 20)
    pg.wire([s2, rb["1"]], f"SP{k}")
    pg.stub_gnd(rb["2"], "down", 10)
    out, inm, inp = opamp(pg, roles(k)["schmitt"], s1[0] + 20, y0)
    pg.wire([s1, inp], f"SP{k}")
    pg.stub_port(inm, f"ENV{k}", "IN", "left", 50)
    node = (out[0] + 15, out[1])
    pg.wire([out, node], f"SC{k}")
    fb_y = y0 + 60
    rf = hpart(pg, P[f"R{r + 14}"], s1[0] + 40, fb_y, left_pin="2")
    pg.wire([node, (node[0], fb_y), rf["1"]], f"SC{k}")
    pg.wire([rf["2"], (s1[0], fb_y), s1], f"SP{k}")
    d = hpart(pg, P[f"D{r + 7}"], node[0] + 20, node[1], left_pin="2")
    pg.wire([node, d["2"]], f"SC{k}")
    lj = (d["1"][0] + 20, node[1])
    pg.wire([d["1"], lj], f"L{k}")
    rl = vpart(pg, P[f"R{r + 15}"], lj[0], lj[1] + 20)
    pg.wire([lj, rl["1"]], f"L{k}")
    pg.stub_gnd(rl["2"], "down", 10)
    pg.stub_port(lj, f"L{k}", "OUT", "right", 30)
    pg.text(x0 - 10, y0 - 50, "LOOP: Schmitt trigger on ENV, thresholds 0.5 V / 7.5 V; drives the buffer through L", 9)


def channel_page(pr, P, k):
    pg = MPage(pr, f"Channel {k}", k)
    nrm = "0 V" if k == 1 else f"GATE {k - 1}"
    pg.text(40, Y(40), f"Channel {k}: the MKI x ES.EDU envelope (main board). GATE {k} unpatched takes {nrm} "
                       "through the jack's switch lug on the faceplate; the panel parts' nets come in on H{k}.", 12)
    y1 = Y(210)
    gate_block(pg, P, k, 150, y1)
    burst_block(pg, P, k, 700, y1)
    sustain_block(pg, P, k, 1300, y1)
    y2 = Y(560)
    timing_block(pg, P, k, 130, y2)
    y3 = Y(830)
    output_block(pg, P, k, 80, y3)
    led_block(pg, P, k, 900, y3 + 20)
    schmitt_block(pg, P, k, 1090, y3 + 40)
    pg.text(40, Y(1110), "Resistors 1 % metal film and diodes all standing. Net ports with the same name connect "
                         "across the pages; GND is one net.", 9)
    return pg


# ------------------------------------------------------------------ shared page
def divider_block(pg, P, top_r, bot_r, cap, node, x, top, note):
    a = vpart(pg, P[top_r], x, top)
    pg.stub_port(a["1"], "+12V", "IN", "left", 20)
    n = (x, top + 60)
    pg.wire([a["2"], n], node)
    n2 = (x + 50, top + 60)
    pg.wire([n, n2], node)
    rb = down_to_gnd(pg, P[bot_r], x, top + 80)
    pg.wire([n, rb["1"]], node)
    cb = down_to_gnd(pg, P[cap], n2[0], top + 80)
    pg.wire([n2, cb["1"]], node)
    pg.stub_port(n2, node, "OUT", "right", 40)
    pg.text(x - 40, top - 30, note, 10)


def power_block(pg, P, x0, t0):
    """2 x 5 header (red stripe = pin 1 = -12 V), a 1N5819 per rail (the -12 V cathode on the header),
    10R and 47 uF."""
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J13", "HDR10", xh, yh, des=(-30, -40, "LEFT_BOTTOM"), value_at=(-30, 45, "LEFT_BOTTOM"))
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
    for k, (port, d, r, c, rail) in enumerate((("P12_IN", "D901", "R905", "C903", "+12V"),
                                               ("N12_IN", "D902", "R906", "C904", "-12V"))):
        y = Y(t0 + 10 + 130 * k)
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


def shared_page(pr, P):
    pg = MPage(pr, "References, power", 5)
    pg.text(40, Y(40), "Shared by the four channels: the comparators' threshold and the inverters' axis", 12)
    divider_block(pg, P, "R901", "R902", "C901", "VREF", 160, Y(150),
                  "VREF: 100k / 27k = 2.55 V, all eight comparators' - inputs")
    divider_block(pg, P, "R903", "R904", "C902", "AXIS", 560, Y(150),
                  "AXIS: 100k / 68k = 4.86 V, the four inverters' + inputs (INV = 9.71 V - ENV)")
    pg.text(40, Y(440), "Power: 10-pin Eurorack header (red stripe = pin 1 = -12 V), a 1N5819 per rail: +12 V "
                        "anode on the header, -12 V cathode on the header", 12)
    power_block(pg, P, 80, 520)
    pg.text(860, Y(440), "Decoupling: a 100n pair per TL074, beside its supply pins", 12)
    for u in range(1, 7):
        x, top = 900 + (u - 1) * 120, Y(560)
        off.decoupling_pair(pg, P, f"C{903 + 2 * u}", f"C{904 + 2 * u}", x, top)
        pg.text(x + 8, top + 140, f"U{u}", 10)
    sockets_block(pg, P, 1000, Y(960))
    return pg


def header_block(pg, part, x, y, title):
    """A 1 x 13 header: every pin to a net port on its left, GND to a ground flag."""
    h = pg.place(part.ref, "HDR13", x, y, des=(-10, -80, "LEFT_BOTTOM"), name=False)
    for num, net in part.nets.items():
        if net == "GND":
            pg.stub_gnd(h[num], "left", 20)
        else:
            pg.stub_port(h[num], net, "IN", "left", 30)
    pg.text(x - 90, y + 85, title, 9)


def sockets_block(pg, P, x0, top):
    pg.text(x0 - 60, top - 100, "Board-to-board: female sockets H1-H4 (bottom side), under the faceplate's HF1-HF4", 12)
    for k in circuit.CH:
        header_block(pg, P[f"H{k}"], x0 + 170 * (k - 1), top, f"H{k}: channel {k}")


# ------------------------------------------------------------------ faceplate page
class FPage(MPage):
    page_count = "1"


def fp_rheostat(pg, part, x, y):
    """Time pot on the faceplate: pin 1 to a port on its left, the wiper and pin 3 to a port on its right."""
    pg.port(x - 30, y, part.nets["1"], "IN", "left")
    pg.wire([(x - 30, y), (x, y)], part.nets["1"])
    end = rheostat(pg, part, x, y)
    pg.stub_port(end, part.nets["3"], "OUT", "right", 20)


def faceplate_column(pg, P, k, cx):
    n = circuit.CHANNELS
    pg.text(cx - 20, Y(110), f"Channel {k}", 12)
    jack_block(pg, P[f"J{k}"], cx, Y(170), "OUT")
    fp_rheostat(pg, P[f"RV{3 * k - 2}"], cx + 30, Y(280))
    fp_rheostat(pg, P[f"RV{3 * k - 1}"], cx + 30, Y(380))
    sus = P[f"RV{3 * k}"]
    p = pot(pg, sus, cx + 70, Y(480))
    pg.stub_port(p["3"], sus.nets["3"], "IN", "left", 30)
    pg.stub_gnd(p["1"], "right", 20)
    w = p["2"]
    pg.wire([w, (w[0], w[1] - 20), (w[0] + 50, w[1] - 20)], sus.nets["2"])
    pg.port(w[0] + 50, w[1] - 20, sus.nets["2"], "OUT", "right")
    pg.text(cx + 30, Y(480) + 62, f"{sus.label}: CW = more", 9)
    sw = P[f"SW{k}"]
    t = pg.place(sw.ref, "TOGGLE_SPDT", cx + 70, Y(590), des=(-12, -26, "LEFT_BOTTOM"),
                 value_at=(-12, 36, "LEFT_BOTTOM"))
    pg.stub_port(t["2"], sw.nets["2"], "OUT", "left", 30)
    pg.stub_port(t["1"], sw.nets["1"], "IN", "right", 30)
    pg.stub_port(t["3"], sw.nets["3"], "IN", "right", 30)
    pg.text(cx - 10, Y(590) + 52, f"MODE {k}: up (2-3) LOOP, down (2-1) SINGLE", 8)
    led = P[f"D{k}"]
    d = pg.place(led.ref, "LED", cx + 70, Y(680), des=(-10, -12, "LEFT_BOTTOM"), value_at=(14, -12, "LEFT_BOTTOM"))
    pg.stub_port(d["1"], led.nets["1"], "IN", "left", 30)
    pg.stub_gnd(d["2"], "right", 20)
    jack_block(pg, P[f"J{n + k}"], cx, Y(760), "IN")
    jack_block(pg, P[f"J{2 * n + k}"], cx, Y(850), "IN")
    header_block(pg, P[f"HF{k}"], cx + 290, Y(1010), f"HF{k}: to the main board's H{k}")


def faceplate_page(pr, P):
    pg = FPage(pr, "Faceplate", 1)
    pg.text(40, Y(40), "Faceplate board: the panel parts on its front, the male headers HF1-HF4 on its rear. "
                       "Nets ending in _F join the main board's nets of the same name through the headers.", 12)
    for k in circuit.CH:
        faceplate_column(pg, P, k, 70 + 395 * (k - 1))
    return pg


# ------------------------------------------------------------------ main
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
    """Parse the written project: every component's Device, Symbol and Footprint must be in it, every
    PAD_NET must name a real pad of its component's footprint, every pad net must have a NET record."""
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
            fp_of = {p["parentId"]: p["value"] for h, p in d["recs"]
                     if h["type"] == "ATTR" and p.get("key") == "Footprint"}
            nets = {ee.json.loads(h["id"])[1] for h, p in d["recs"] if h["type"] == "NET"}
            for h, p in d["recs"]:
                if h["type"] != "PAD_NET":
                    continue
                _, cid, num, pad_id = ee.json.loads(h["id"])
                fp = docs.get(fp_of.get(cid))
                pads = {(str(pp["num"]), hh["id"]) for hh, pp in fp["recs"] if hh["type"] == "PAD"} if fp else set()
                if (str(num), pad_id) not in pads:
                    problems.append(f"{meta(d)['title']}: PAD_NET {num} of {cid} is not a pad of its footprint")
                if p["padNet"] not in nets:
                    problems.append(f"{meta(d)['title']}: net {p['padNet']} has no NET record")
    return problems, collections.Counter(d["docType"] for d in docs.values())


def main():
    pr = MProject()
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    main_pages = [channel_page(pr, PM, k) for k in circuit.CH] + [shared_page(pr, PM)]
    fp_pages = [faceplate_page(pr, PF)]
    bad = off.coverage(main_pages, mb) + off.coverage(fp_pages, fb)
    for pg, parts in [(p, mb) for p in main_pages] + [(p, fb) for p in fp_pages]:
        bad += [f"{pg.title}: {b}" for b in off.page_check(pg, parts)]
    used = {c["dev"] for pg in main_pages + fp_pages for c in pg.comps if c["ref"]}
    bad += off.pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    info_m, info_f = part_info(main_pages), part_info(fp_pages)
    holes = pcb.find_holes([pcb.faceplate_board(pr, fb, info_f, circuit), pcb.main_board(pr, mb, info_m, circuit)])
    board_fb = pcb.faceplate_board(pr, fb, info_f, circuit, holes)
    board_mb = pcb.main_board(pr, mb, info_m, circuit, holes)
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb)
               + pcb.panel_pad_check(board_fb))
    if len(holes) != 4:
        pcb_bad.append(f"only {len(holes)} mounting holes found")
    for b in pcb_bad:
        print("PCB:", b)
    template = pcb.load_template(ee)
    panel_page = FPage(pr, "Panel", 1)
    panel_page.text(70, Y(60), "Envy 16HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the bare-"
                               "copper output band are in the PCB document; the art is hardware/panel/envy-panel.svg.",
                    12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("Envy Main", main_pages, board_mb), ("Envy Faceplate", fp_pages, board_fb),
              ("Envy Panel", [panel_page], board_panel)], OUT, template)
    missing, counts = validate(OUT)
    for b in missing:
        print("FILE:", b)
    for pg in main_pages + fp_pages:
        render(pr, pg, PREVIEW.format(pg.title.split(",")[0].lower().replace(" ", "-")))
    board_mb.render(PREVIEW.format("pcb-main-board"))
    board_fb.render(PREVIEW.format("pcb-faceplate"))
    board_panel.render(PREVIEW.format("pcb-panel"))
    n = sum(1 for pg in main_pages + fp_pages for c in pg.comps if c["ref"])
    print(f"{os.path.normpath(OUT)}: {n} part units on {len(main_pages) + len(fp_pages)} pages, "
          f"{len(bad)} schematic problems; {len(board_mb.placed)} + {len(board_fb.placed)} parts placed, "
          f"holes {[tuple(round(v, 2) for v in h) for h in holes]}, {len(pcb_bad)} PCB problems; "
          f"{len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
