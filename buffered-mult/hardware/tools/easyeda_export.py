"""Six as an EasyEDA Pro project (.epro2): the schematics of its two boards,
and (from pcb.py and panel_pcb.py) both placed PCBs and the panel as a PCB.

Builds on the Plaitsy exporter (../../../plaitsy/hardware/tools) for the file
format, the connectivity check and the previews, and on Offset's exporter
(../../../attenuverter/hardware/tools) for the footprints, symbols and blocks
the modules share: DIP-14 on 7.62 mm, the 2-lead 3 mm LED and its bicolour
symbol, standing resistors, the inverting stage, the decoupling pair. Library
parts come from the caches of your MorrisSynth export (morrissynth-parts.epru,
stereo-mixer-parts.epru): TL074ACN symbol, WQP518MA jack, LR1F resistors, FG28
capacitors, 1N5819, the 178MU0033 10 uF, the 2 x 8 box header, net ports,
ground flag, sheet frame. Drawn or generated here, in the same style:

  footprints  1 x 2 and 1 x 4 pin headers (Envy's drawing)
  symbols     the 1 x n header
  devices     100k 0.1 % (standing), 10 p C0G (the 100n's 5.08 mm footprint)

Pages. Main board: one per group (the input inverter and its LED resistor,
the three output stages with the 1k inside the loop), and one for power,
decoupling and the four sockets. Faceplate: the jacks, LEDs and male headers.
Every block ends in net ports; ports with the same name connect across the
pages of a board.

Run from buffered-mult/hardware/tools:  python easyeda_export.py
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
from easyeda_export import Doc, Symbol, meta, attr_payload, Y, render, new_uuid, W, H   # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


circuit = _load("six_circuit", os.path.join(HERE, "circuit.py"))
pcb = _load("six_pcb", os.path.join(HERE, "pcb.py"))
panel_pcb = _load("six_panel_pcb", os.path.join(HERE, "panel_pcb.py"))
off = _load("offset_export", os.path.join(OFFSET, "easyeda_export.py"))    # footprints, symbols, blocks
SECTION, UNIT = circuit.SECTION, off.UNIT
Footprint = off.Footprint

NAME = "Six"
OUT = os.path.join(HERE, "..", "easyeda", "Six.epro2")
PREVIEW = os.path.join(HERE, "..", "easyeda", "six-easyeda-{}.png")

DEV = dict(off.DEV)
ee.DEV = DEV
off.DEV = DEV
STANDING = ["R1k", "R10R", "R2k2", "R100kP"]       # every resistor stands up (dev key + "V")
off.STANDING[:] = STANDING                         # MPage.place in Offset's exporter stands these up


# ---------------------------------------------------------------- footprints, symbols
def fp_header(n):
    """1 x n 2.54 mm pin header (male on the faceplate, female socket on the main board), pin 1 square."""
    f = Footprint(f"HDR-1x{n}-P2.54", "H?")
    x0 = -(n - 1) * 1.27
    for i in range(n):
        f.pad(i + 1, x0 + i * 2.54, 0, 1.0, 1.7, square=(i == 0))
    f.rect(x0 - 1.27, -1.27, x0 + (n - 1) * 2.54 + 1.27, 1.27)
    return f


def fp_cap254():
    """Small leaded ceramic, 2.54 mm lead spacing (KEMET C315 class): body 4.0 x 2.5 mm."""
    f = Footprint("CAP-TH_P2.54-L4.0-W2.5", "C?")
    f.pad(1, -1.27, 0, 0.8, 1.6)
    f.pad(2, 1.27, 0, 0.8, 1.6)
    f.rect(-2.0, -1.25, 2.0, 1.25)
    return f


def header_symbol(n):
    s = Symbol(f"Pin header 1x{n}", f"HDR{n}.1", "H?", [NAME])
    half = n * 5
    s.rect(-10, -half - 5, 10, half + 5)
    for i in range(n):
        s.pin(str(i + 1), str(i + 1), -20, -half + 5 + 10 * i, 0, show=True, edge=-10)
    return s


# ------------------------------------------------------------------ project
class MPage(off.MPage):
    def __init__(self, pr, title, number, count):
        self.page_count = str(count)
        super().__init__(pr, title, number)

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


class MProject(off.MProject):
    def _new_devices(self):
        r1k = self.device_attrs("R1k")
        for key, mpn, value, tol, desc in (
                ("R2k2", "LR1F2K2", "2.2kΩ", "±1%", "Metal film resistor 2.2kΩ ±1% 600mW (TE LR1F series)"),
                ("R100kP", "100k 0.1% 25ppm", "100kΩ", "±0.1%",
                 "Metal film resistor 100kΩ ±0.1% 25ppm/°C 0.25W, any make (Yageo MFP, Vishay MBB0207, TE H8). "
                 "Sets the gain: or 1% parts paired to 0.05% with a meter")):
            a = dict(r1k)
            a.update({"Manufacturer Part": mpn, "Value": value, "Tolerance": tol, "Supplier Part": "",
                      "Datasheet": "", "LCSC Part Name": desc.split(",")[0], "Description": desc})
            self._device(key, mpn, a, ["Resistors", "Through Hole Resistors"])
        fps = {"C254": self._footprint(fp_cap254()), "RV": self._footprint(off.fp_res_vertical()),
               "DIP14": self._footprint(off.fp_dip(14, "DIP-14-W7.62-P2.54")),
               "LED2": self._footprint(off.fp_led2()), "HDR2": self._footprint(fp_header(2)),
               "HDR4": self._footprint(fp_header(4))}
        c = dict(self.device_attrs("C100n"))
        c.update({"Manufacturer Part": "10pF C0G 50V P2.54", "Value": "10pF", "Supplier Part": "", "Datasheet": "",
                  "Tolerance": "±5%", "Temperature Coefficient": "C0G", "LCSC Part Name": "10pF 50V C0G",
                  "Footprint": fps["C254"],
                  "Description": "10 pF C0G ceramic, 2.54 mm lead spacing (KEMET C315 class or similar)"})
        self._device("C10p", "10pF C0G", c, ["Capacitors", "Multilayer Ceramic Capacitors MLCC - Leaded"])
        for key in STANDING:                                      # each resistor again, standing up
            a = self.device_attrs(key)
            self._copy(key + "V", key, a["Manufacturer Part"], ["Resistors", "Through Hole Resistors"],
                       Footprint=fps["RV"])
        self._copy("TL074N", "TL074", "TL074ACN", ["Amplifiers"], Footprint=fps["DIP14"],
                   Description="Quad JFET op-amp, DIP-14 on the 7.62 mm row pitch (TL074BCN for pitch duty)")
        new = [
            ("LED_BI", off.led_bi_symbol(), "LED 3mm bicolour R/G 2-lead", "D?", fps["LED2"],
             "3 mm bicolour LED, red/green, two leads back to back: current from pad 1 to pad 2 lights green. "
             "Pad 1 is on GND here, so green = positive input. Check which lead does that on the part bought"),
            ("HDR4", header_symbol(4), "Pin header 1x4", "H?", fps["HDR4"],
             "1 x 4 2.54 mm: male pin header on the faceplate (HF1, HF3), female socket on the main board (H1, H3)"),
            ("HDR2", header_symbol(2), "Pin header 1x2", "H?", fps["HDR2"],
             "1 x 2 2.54 mm: male pin header on the faceplate (HF2, HF4), female socket on the main board (H2, H4)"),
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
                   "description": "Six: buffered mult, 2 x 1 -> 3, IN 2 normalled to IN 1, one TL074 section per "
                                  "output with the 1k inside the loop, a bicolour LED per group. 2x TL074. Two "
                                  "stacked PCBs (faceplate + main board), 4HP.",
                   "tags": "[]"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with ee.zipfile.ZipFile(path, "w", ee.zipfile.ZIP_DEFLATED) as z:
            z.writestr("IMAGE/", "")
            z.writestr("project2.json", ee.json.dumps(project, indent=2, ensure_ascii=False))
            z.writestr(f"{NAME}.epru", "\n".join(lines) + "\n")
        return lines


def dev_of(part):
    if part.kind == "R":
        return {"1k": "R1k", "10R": "R10R", "2k2": "R2k2", circuit.PRECISE: "R100kP"}[part.value]
    if part.kind == "C":
        return {"100n": "C100n", "10p": "C10p"}[part.value]
    return {"CP": "C10u", "TL074": "TL074N"}.get(part.kind, part.kind)


off.dev_of = dev_of                                    # Offset's hpart / vpart / blocks look devices up here
hpart, vpart, supply = off.hpart, off.vpart, off.supply


# ------------------------------------------------------------------ group pages
def input_block(pg, P, g, x, y):
    """IN g port -> 100k -> section A (100k || 10p) -> N g; N g -> 2k2 -> the LED port."""
    r = 100 * g
    a = hpart(pg, P[f"R{r + 1}"], x, y)
    pg.stub_port(a["1"], f"IN{g}", "IN", "left")
    pg.wire([a["2"], (x + 60, y)], f"NA{g}")
    kn = off.inverting(pg, f"U{g}", "A", x + 60, y, P[f"R{r + 2}"], P[f"C{r + 1}"])
    pg.stub_port(kn, f"N{g}", "OUT", "right", 40)
    pg.text(x - 20, y - 130, f"A: N{g} = -IN {g}, 100k in (the input impedance), 100k || 10p", 10)
    xl = x + 560
    pg.port(xl, y, f"N{g}", "IN", "left")
    rl = hpart(pg, P[f"R{r + 3}"], xl + 20, y)
    pg.wire([(xl, y), rl["1"]], f"N{g}")
    pg.stub_port(rl["2"], f"LED{g}", "OUT", "right", 30)
    pg.text(xl - 40, y - 40, f"LED {g} (faceplate, pin 1 on GND): green = IN {g} positive", 10)


def output_stage(pg, P, g, i, x, y):
    """N g port -> 100k -> S; the TL074 section; 10p from its output back to S; output -> 1k -> the jack tip;
    100k from the tip back to S, so the loop holds the tip itself at +IN."""
    r = 100 * g + 10 * i
    xo = circuit.OUTS[i - 1]
    sec = circuit.OUT_SECTION[xo]
    rin, rf, rs, cf = P[f"R{r + 1}"], P[f"R{r + 2}"], P[f"R{r + 3}"], P[f"C{r + 1}"]
    s, oa, tip = rin.nets["2"], rs.nets["1"], rs.nets["2"]
    a = hpart(pg, rin, x, y)
    pg.stub_port(a["1"], rin.nets["1"], "IN", "left")
    jx = x + 60
    pg.wire([a["2"], (jx, y)], s)
    ox, oy = jx + 55, y + 10
    amp = pg.place(f"U{g}", "TL074N", ox, oy, unit=UNIT[sec], des=(14, 30, "LEFT_BOTTOM"), name=False)
    out, inm, inp = SECTION[sec]
    kx = ox + 60
    pg.wire([(jx, y), amp[inm]], s)
    pg.wire([(jx, y), (jx, oy - 60)], s)
    c = hpart(pg, cf, ox - 20, oy - 60, left_pin="2")            # 10p: pin 2 on S, pin 1 on the output
    pg.wire([(jx, oy - 60), c["2"]], s)
    f = hpart(pg, rf, ox - 20, oy - 110, left_pin="2")           # 100k: pin 2 on S, pin 1 on the tip
    pg.wire([(jx, oy - 60), (jx, oy - 110), f["2"]], s)
    pg.wire([amp[out], (kx, oy)], oa)
    pg.wire([(kx, oy), (kx, oy - 60), c["1"]], oa)
    ro = hpart(pg, rs, kx + 20, oy)
    pg.wire([(kx, oy), ro["1"]], oa)
    t = (ro["2"][0] + 20, oy)
    pg.wire([ro["2"], t], tip)
    pg.wire([t, (t[0], oy - 110), f["1"]], tip)
    pg.stub_port(t, tip, "OUT", "right", 30)
    pg.stub_gnd(amp[inp], "left", 10)
    supply(pg, amp, sec)
    pg.text(ox - 30, oy + 45, f"U{g} {sec}", 8)
    pg.text(x - 20, oy - 150, f"OUT {g}{xo.lower()}: 1k inside the loop", 10)


def group_page(pr, P, g):
    pg = MPage(pr, f"Group {g}", g, 3)
    nrm = "0 V (its switch lug is on GND)" if g == 1 else "IN 1 (its switch lug takes IN 1's tip)"
    pg.text(40, Y(40), f"Group {g}: IN {g} to three buffered outputs (main board). IN {g} unpatched takes {nrm}; "
                       f"the jack nets come in on H{2 * g - 1} and H{2 * g}.", 12)
    pg.text(40, Y(80), "Every stage inverts, so no op-amp input moves with the signal; two inversions give +1. The "
                       "100k in the signal path are 0.1 %: they set the gain.", 10)
    input_block(pg, P, g, 200, Y(270))
    pg.text(40, Y(470), "One TL074 section per output. The 100k feedback comes from the jack side of the 1k, so "
                        "the tip holds +IN under load; above ~160 kHz the 10p from the op-amp output closes the "
                        "loop instead (cable capacitance cannot make it ring).", 10)
    for i in range(1, 4):
        output_stage(pg, P, g, i, 110 + 520 * (i - 1), Y(700))
    pg.text(40, Y(1110), "Resistors metal film, all standing. Net ports with the same name connect across the pages; "
                         "GND is one net.", 9)
    return pg


# ------------------------------------------------------------------ power page
def power_block(pg, P, x0, t0):
    """16-pin header (red stripe = pin 1 = -12 V; 3-8 GND, 9-10 +12 V, 11-16 open), a 1N5819 per rail (the -12 V cathode on the header),
    10R and 10 uF (Offset's drawing, this module's designators)."""
    yh = Y(t0 + 40)
    xh = x0 + 60
    h = pg.place("J9", "HDR16", xh, yh, des=(-30, -45, "LEFT_BOTTOM"), value_at=(-30, 52, "LEFT_BOTTOM"))
    for side, pins, sgn in (("left", ("3", "5", "7"), -1), ("right", ("4", "6", "8"), 1)):
        bx = xh + sgn * 45
        pts = []
        for n in pins:
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
    for k, (port, d, r, c, rail) in enumerate((("P12_IN", "D3", "R901", "C901", "+12V"),
                                               ("N12_IN", "D4", "R902", "C902", "-12V"))):
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


def header_block(pg, part, x, y, title):
    """A 1 x n header: every pin to a net port on its left, GND to a ground flag turned away from the next pin's
    wire (up from the first pin, down from the last), so its bar does not lie across that wire."""
    h = pg.place(part.ref, part.kind, x, y, des=(-10, -15 - 5 * len(part.nets), "LEFT_BOTTOM"), name=False)
    last = str(len(part.nets))
    for num, net in part.nets.items():
        if net == "GND" and num in ("1", last):
            px, py = h[num]
            dy = -15 if num == "1" else 15
            pg.wire([(px, py), (px - 15, py), (px - 15, py + dy)], "GND")
            pg.gnd(px - 15, py + dy, 180 if num == "1" else 0)
        elif net == "GND":
            pg.stub_gnd(h[num], "left", 20)
        else:
            pg.stub_port(h[num], net, "IN", "left", 30)
    pg.text(x - 90, y + 20 + 5 * len(part.nets), title, 9)


def power_page(pr, P):
    pg = MPage(pr, "Power, sockets", 3, 3)
    pg.text(40, Y(40), "Power: 16-pin Eurorack header (red stripe = pin 1 = -12 V; 3-8 GND, 9-10 +12 V, 11-16 open), a 1N5819 per rail: +12 V anode "
                       "on the header, -12 V cathode on the header", 12)
    power_block(pg, P, 80, 120)
    pg.text(900, Y(40), "Decoupling: a 100n pair per TL074, beside its supply pins", 12)
    for g in circuit.GROUPS:
        x, top = 980 + (g - 1) * 160, Y(160)
        off.decoupling_pair(pg, P, f"C{901 + 2 * g}", f"C{902 + 2 * g}", x, top)
        pg.text(x + 8, top + 140, f"U{g}", 10)
    pg.text(40, Y(560), "Board-to-board: female sockets H1-H4 (bottom side), under the faceplate's HF1-HF4. "
                        "H1 / H3: the tips (left strip, front view); H2 / H4: GND and the LED (right strip).", 12)
    for k, (ref, kind, pins) in enumerate(circuit.HEADERS):
        g = k // 2 + 1
        what = "IN and OUT tips" if kind == "HDR4" else "GND, LED"
        header_block(pg, P[ref], 220 + 330 * k, Y(760), f"{ref}: group {g}, {what}")
    return pg


# ------------------------------------------------------------------ faceplate page
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


def faceplate_page(pr, P):
    pg = MPage(pr, "Faceplate", 1, 1)
    pg.text(40, Y(40), "Faceplate board: the jacks and LEDs on its front, the male headers HF1-HF4 on its rear. "
                       "Nets ending in _F join the main board's nets of the same name through the headers.", 12)
    pg.text(40, Y(75), "The jacks lie on their sides, sleeve lug to the right (front view): stood up in one column "
                       "their tip and sleeve pads would collide at this pitch.", 10)
    for g in circuit.GROUPS:
        cx = 120 + 760 * (g - 1)
        j = 4 * (g - 1)
        pg.text(cx - 40, Y(140), f"Group {g}", 12)
        jack_block(pg, P[f"J{j + 1}"], cx, Y(220), "OUT")
        led = P[f"D{g}"]
        d = pg.place(led.ref, "LED_BI", cx + 70, Y(330), des=(-10, -14, "LEFT_BOTTOM"),
                     value_at=(14, -14, "LEFT_BOTTOM"))
        pg.stub_gnd(d["1"], "left", 20)
        pg.stub_port(d["2"], led.nets["2"], "IN", "right", 30)
        pg.text(cx - 20, Y(330) + 40, f"LED {g}: green = IN {g} positive", 9)
        for i in range(3):
            jack_block(pg, P[f"J{j + 2 + i}"], cx, Y(450 + 120 * i), "IN")
        h4, h2 = P[f"HF{2 * g - 1}"], P[f"HF{2 * g}"]
        header_block(pg, h4, cx + 420, Y(420), f"{h4.ref}: to the main board's H{2 * g - 1}")
        header_block(pg, h2, cx + 420, Y(640), f"{h2.ref}: to the main board's H{2 * g}")
    return pg


# ------------------------------------------------------------------ checks, files
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
                pads = {(str(pp["num"]), hh["id"]) for hh, pp in fp["recs"] if hh["type"] == "PAD"} if fp else set()
                if (str(num), pad_id) not in pads:
                    problems.append(f"{meta(d)['title']}: PAD_NET {cid}.{num} names no pad of its footprint")
                if p["padNet"] not in nets:
                    problems.append(f"{meta(d)['title']}: net {p['padNet']} has no NET record")
    return problems, collections.Counter(d["docType"] for d in docs.values())


def main():
    pr = MProject()
    mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
    PM, PF = {p.ref: p for p in mb}, {p.ref: p for p in fb}
    main_pages = [group_page(pr, PM, g) for g in circuit.GROUPS] + [power_page(pr, PM)]
    fp_pages = [faceplate_page(pr, PF)]
    bad = off.coverage(main_pages, mb) + off.coverage(fp_pages, fb)
    for pg, parts in [(p, mb) for p in main_pages] + [(p, fb) for p in fp_pages]:
        bad += [f"{pg.title}: {b}" for b in off.page_check(pg, parts)]
    used = {c["dev"] for pg in main_pages + fp_pages for c in pg.comps if c["ref"]}
    bad += off.pins_and_pads(pr, used)
    for b in bad:
        print("PROBLEM:", b)
    board_fb = pcb.faceplate_board(pr, fb, part_info(fp_pages), circuit)
    board_mb = pcb.main_board(pr, mb, part_info(main_pages), circuit)
    holes = {ref: (hx, hy) for kind, ref, label, ox, oy, hx, hy in panel_pcb.panel.features() if kind == "jack"}
    pcb_bad = (board_fb.check("top") + board_mb.check("bottom") + pcb.header_check(board_fb, board_mb, circuit)
               + pcb.placement_check(board_fb, circuit) + pcb.front_housing_check(board_fb)
               + pcb.panel_pad_check(board_fb) + pcb.barrel_check(board_fb, circuit, holes))
    for b in pcb_bad:
        print("PCB:", b)
    panel_page = MPage(pr, "Panel", 1, 1)
    panel_page.text(70, Y(60), "Six 4HP panel as a PCB: no parts, no nets. Holes, slots, silkscreen and the bare-"
                               "copper bands are in the PCB document; the art is hardware/panel/six-panel.svg.", 12)
    board_panel = panel_pcb.PanelBoard()
    pr.write([("Six Main", main_pages, board_mb), ("Six Faceplate", fp_pages, board_fb),
              ("Six Panel", [panel_page], board_panel)], OUT, pcb.load_template(ee))
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
          f"{len(pcb_bad)} PCB problems; {len(missing)} file problems; docs {dict(counts)}")


if __name__ == "__main__":
    main()
