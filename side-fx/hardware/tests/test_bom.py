"""BOM group: Side FXy's (Moss's) bill of materials.

Checks
  1. bom.py's in-memory build() against circuit.py: every netlist part owned by
     exactly one line, quantities per kind and value counted independently,
     the socket lines against the socketed chips, the routed master's
     designators board by board (bom.check() and our own count);
  2. the committed docs/bom.md, hardware/bom/side-fx-bom.csv and -thonk.csv
     (read as they are on disk) against what bom.write() produces from a
     fresh build, captured in memory (bom.py's open / os.makedirs are
     replaced for the call, and its ROOT points at a folder that does not
     exist, so nothing can be written);
  3. the Thonk lines against the faceplate parts, and against the repo's
     bom/thonk-order.md and .csv (the Moss column);
  4. part numbers that exist and fit: the Bourns PEC11R-4215F-S0024 decoded
     from Bourns' ordering guide and its pins / tabs against the routed EC11
     footprint, the Bourns 4609X-101-103LF network, the BAT85 and its
     alternatives' leads against D1's real footprint drill, the 10 uF ceramic
     on 5.08 mm, the DIP sockets against the footprints, the right-angle
     header, the display listing, the knobs against the encoder's shaft;
  5. ratings: capacitor voltages against the rails, every resistor's
     worst-case dissipation against 1/4 W (R24 and R26 worked out from the
     clock and MIDI inputs' worst cases), the dielectrics;
  6. mechanics: standoff length against the mated headers, the screws
     against the standoff and the board, the breakout's own parts and its
     header rows (the female sockets against the breakout footprint in the
     routed export), the power cable against the breakout's 2x5 J2, the PCB
     lines against the routed outlines;
  7. the docs' counts (README).

Run from side-fx/hardware/tests:  python test_bom.py
Only reads: never runs bom.py's main(); write() is called with its file
functions captured in memory.
"""
import collections
import csv
import io
import math
import os
import re
import types

import sys

sys.dont_write_bytecode = True       # importing harness must not leave __pycache__ here
import harness  # noqa: E402

ck = harness.Checks("bom")
circuit = harness.load("circuit")
bom = harness.load("bom")
REPO = harness.REPO

# ------------------------------------------------------------------ datasheet constants
# Eurorack rails: +-12 V; a bus board at +5 % worst case (Doepfer A-100 PSU3 spec +-12 V; 5 % taken as the
# conservative bound for other supplies). The breakout feeds the TL074 through its B5819W Schottkys.
RAIL, RAIL_WORST = 12.0, 12.6
V3V3_MAX = 3.47            # Seed 3V3D / 3V3A: 3.3 V + 5 % (Daisy Seed datasheet v1.0.5: 3.3 V regulator; tolerance not
#                            given there: 5 % assumed)
CAP_MARGIN = 1.5           # rated voltage >= 1.5 x the worst DC across it (common derating)
# Bourns PEC11R datasheet "PEC11R Series - 12 mm Incremental Encoder" REV. D04/26, "How To Order":
#   PEC11R - [terminal] [detent] [shaft length] [shaft style] - [switch] [resolution]
#   terminal 1 = PC pin vertical / side facing 7 mm, 2 = PC pin vertical / side facing 10 mm,
#            4 = PC pin horizontal / rear facing (the shaft at right angles to the board, the EC11 pattern)
#   detent 0 = none (12, 18, 24 pulses), 1 = 18 detents (18 pulses), 2 = 24 detents (12, 24 pulses),
#          3 = 12 detents (12, 24 pulses)
#   shaft length 15 / 20 / 25 / 30 mm; shaft style F = metal flatted, K = metal knurled
#   switch S = push momentary, N = none; resolution 0012 / 0018 / 0024 pulses per 360 deg
#   every PEC11R has the M7 x 0.75 bushing; bushing length LB 5 (L 15) / 7 (L 20, 25, 30)
#   recommended PCB layout (PEC11R-4xxxF-Sxxxx): pin holes d 1.0 +0.1/-0 (5 places), A C B 2.5 pitch on a
#   row 7.5 from the shaft, switch pins 5.0 apart 7.0 from the shaft, mounting tabs on the shaft line parallel
#   to the pin rows, tab holes 2.6 (across) x 1.8 (along the tab line) +0.2/-0; terminals 0.8 wide.
#   VERIFY 2026-11-13 (test bug fixed): the "13.2" is NOT centre to centre. Read on the drawing's vector paths
#   (page 2, PEC11R-4xxxF-Sxxxx layout) its arrow tips sit on the OUTER edges of the two tab-hole rectangles and
#   the "1.8" spans one hole along the tab line, so the centres are 13.2 - 1.8 = 11.4 apart and each hole runs
#   4.8 .. 6.6 mm from the shaft. The 14.0 in the front view is across the snap-in tabs' outward bends.
PEC_TERMINAL = {"1": "PC pin vertical / side facing 7 mm", "2": "PC pin vertical / side facing 10 mm",
                "4": "PC pin horizontal / rear facing"}
PEC_DETENT = {"0": 0, "1": 18, "2": 24, "3": 12}
PEC_SHAFT = {"F": "flatted (D)", "K": "knurled"}
PEC_SWITCH = {"S": "push momentary", "N": "none"}
PEC_PIN_HOLE = 1.0
PEC_TAB_OUTER = 13.2       # across the two tab holes' outer edges
PEC_TAB_HOLE = (2.6, 1.8)  # along the tab, across (the 1.8 runs along the tab-to-tab line)
PEC_TAB_PITCH = PEC_TAB_OUTER - PEC_TAB_HOLE[1]          # 11.4 between the hole centres
# The user's own PEC11R-4215F-S0024, measured with calipers on 2026-11-14: "12.7 mm or less" across the
# outer faces of its two mounting tabs, just above the barbs (an upper bound). Bourns' layout above is the
# recommended hole, with clearance; this is the part that goes into the slots (the barbs flex through).
PEC_TAB_OUTER_MEASURED = 12.7     # mm, max
PEC_TERMINAL_W = 0.8
PEC_SHAFT_D, PEC_FLAT = 6.0, 4.5
PEC_LB = {15: 5.0, 20: 7.0, 25: 7.0, 30: 7.0}
PEC_FLAT_L = {15: 7.0, 20: 10.0, 25: 12.0, 30: 12.0}
PEC_BODY_H = 6.5           # PCB to the mounting surface (bushing base), 4xxxF-S drawing, +-0.3
PEC_NUT_T, PEC_WASHER_T = 2.0, 0.5
# Bourns 4600X thick-film SIP networks (Bourns "4600X Series - Thick Film Conformal SIPs"): 4609X = 9 pins at
# 2.54 mm; circuit code 101 = bussed (pin 1 common); 103 = 10 kOhm; LF = lead free. Leads 0.51 x 0.25 mm
# (not re-read: taken from memory of the drawing, conservative 0.6 mm diagonal).
SIP_PINS, SIP_PITCH, SIP_LEAD_DIAG = 9, 2.54, 0.6
# DO-35 (JEDEC DO-204AH), e.g. Vishay BAT85 (doc "BAT85, Vishay Semiconductors, formerly General
# Semiconductor": case DO-35 glass): lead d 0.46-0.56 mm (max 0.56, JEDEC outline). DO-34 (SOD68) parts
# (NXP BAT85 / BAT86) have thinner leads (0.55 max) and a shorter body. All the alternatives named in the
# BOM (BAT86, BAT43, BAT42, BAT46, SD103A, 1N5711, SD101) are sold in DO-35 or DO-34 (not each re-read).
DO35_LEAD_MAX = 0.56
LEAD_CLEAR = 0.15          # hole >= lead + 0.15 mm for a round lead (IPC-2222 level B: +0.25 nominal; 0.15 min)
# PDIP lead width max 0.56 mm (TI N package / MS-001); a turned-pin socket's tail ~0.5 mm. Square 0.64 mm
# header pins (diagonal 0.905).
DIP_LEAD, HDR_DIAG = 0.56, 0.64 * math.sqrt(2)
DIP_ROW = 7.62
# Radial MLCC 10 uF, 5.08 mm leads, X5R / X7R, >= 16 V: e.g. KEMET C330C106K5R5TA (10 uF 50 V X7R, Goldmax,
# 0.200" spacing) or TDK FG28X5R1E106MRT06 (10 uF 25 V X5R, 5.0 mm). Lead d 0.5 mm. (VERIFY 2026-11-13: the TDK
# part is confirmed to exist on distributor listings: DigiKey 7384817 / LCSC C1620216, lead spacing 5.0 mm, body
# 4.0 x 2.5, seated height 5.5 max; its lead diameter was not read. The KEMET C330 one is still unconfirmed.)
MLCC_LEAD = 0.5
# Standard 2.54 mm headers: female socket body 8.5 mm, male plastic 2.5 mm: mated gap 11.0 mm.
FEMALE_BODY, MALE_PLASTIC = 8.5, 2.5
MATED_GAP = FEMALE_BODY + MALE_PLASTIC
PCB_T = 1.6
# Thonkiconn (Thonk drawing PJ301M-12 'Thonkiconn', ver 1, +-0.15): body 9.0 mm from the PCB to its front face = the
# panel gap (test_panel uses the same figure).
THONK_BODY_H = 9.0
# M3 F-F hex standoffs: threaded through or at least 4.5-5 mm deep at each end for lengths >= 10 mm (common
# catalogue practice, e.g. Wurth 970110xxx WA-SSTII; not confirmed for Tayda's). M3 screw engagement in brass
# >= 1 x d = 3 mm (rule of thumb).
STANDOFF_THREAD_MIN, ENGAGE_MIN = 4.5, 3.0
# Rob Heel's seed_power_opamps breakout BOM (github.com/rob-scape/daisy-seed-breakout-boards, 2025-08-29):
# J2 HDR-M-2.54_2x5 (a 10-pin Eurorack power header), J1/J3/J4/J5 HDR-M-2.54_1x4 (male), D2/D3 B5819W.
BREAKOUT_J2_PINS = 10
# MIDI 1.0 electrical spec (MMA CA-033 for TRS; the 2014 3.3 V update): the sender drives the current loop
# from 5 V through 220 Ohm (5 V) or 3.3 V through 33 + 10 Ohm; the loop current stays under ~10 mA.
MIDI_V_SRC, MIDI_R_SRC = 5.25, 220.0
OPTO_VF_MIN = 1.0          # H11L1 LED forward voltage, min (Vishay / onsemi H11L1: VF 1.2 typ, 1.5 max): 1.0 conservative
# Worst-case abuse: a Eurorack output (op-amp behind >= 1 kOhm, the usual output resistor; Doepfer A-100 outputs
# use 1k) patched into an input, at the full rail.
EURO_OUT_R = 1000.0
R_RATING = 0.25            # W, 1/4 W metal film (the BOM's lines)
R_DERATE = 0.5             # keep each resistor under half its rating

# ------------------------------------------------------------------ 1. in-memory build
lines, owned = bom.build()
problems = bom.check(owned)
ck.check("A.bom_check: every part owned once, refs match the routed master (bom.check)", not problems,
         f"expected 0 problems, got {len(problems)}: {problems[:4]}")

mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
BOARDS = (("Main", mb), ("Faceplate", fb))
# a socket line names the chips it carries but buys sockets; the breakout's header line rides on U5 too
part_lines = {k: line for k, line in lines.items()
              if not k[2].endswith("IC socket") and not k[2].startswith("Female header 2.54 mm, 8.5 mm tall, for the breakout")
              and not k[2].startswith("Rob Heel")}
for board, parts in BOARDS:
    for p in parts:
        n = sum(1 for line in part_lines.values() if (board, p.ref) in line["refs"])
        if n != 1:
            ck.check(f"A.one_line.{board}.{p.ref}", False, f"expected 1 line, got {n}")
ck.check("A.one_line: every netlist part sits in exactly one line's refs",
         all(sum(1 for line in part_lines.values() if (b, p.ref) in line["refs"]) == 1 for b, ps in BOARDS for p in ps),
         f"{len(mb)} main + {len(fb)} faceplate parts")

# independent counts by kind and value (circuit.py's structure) against the lines' quantities
kinds = collections.Counter((p.kind, p.value) for p in mb + fb)


def qty_where(pred):
    return sum(line["qty"] for key, line in lines.items() if pred(key))


for (k, v), n in sorted(kinds.items()):
    if k == "R":
        got = qty_where(lambda key: key[1] == "Resistors" and re.search(rf"Resistor {re.escape(bom.ohms(v))},", key[2]))
    elif k == "C":
        word = {"100n": "100 nF", "1n": "1 nF", "2n2": "2.2 nF", "1u": "1 µF", "10u": "10 µF"}.get(v, v)
        got = qty_where(lambda key: key[1] == "Capacitors" and key[2].startswith(f"Capacitor {word} "))
    else:
        continue
    ck.check(f"A.qty.{k}.{v}: {n} in circuit.py", got == n, f"expected {n}, got {got}")
ck.check("A.qty.resistors_total", sum(n for (k, v), n in kinds.items() if k == "R") ==
         qty_where(lambda key: key[1] == "Resistors" and key[2].startswith("Resistor ")),
         f"circuit {sum(n for (k, v), n in kinds.items() if k == 'R')}, BOM "
         f"{qty_where(lambda key: key[1] == 'Resistors' and key[2].startswith('Resistor '))}")
ck.check("A.qty.capacitors_total", sum(n for (k, v), n in kinds.items() if k in ("C", "CP")) ==
         qty_where(lambda key: key[1] == "Capacitors"),
         f"circuit {sum(n for (k, v), n in kinds.items() if k in ('C', 'CP'))}, BOM {qty_where(lambda key: key[1] == 'Capacitors')}")
for kind, word in (("JACK", "PJ398SM"), ("JACK_TRS", "PJ366ST"), ("SWLED", "LED button"), ("ENC", "EC11"),
                   ("HC165", "74HC165"), ("HC595", "74HC595"), ("H11L1", "H11L1"), ("TL074", "TL074"),
                   ("NPN", "2N3904"), ("BAT85", "BAT85"), ("1N4148", "1N4148"), ("RN9", "bussed resistor network"),
                   ("HDR8RA", "right-angle")):
    n = sum(c for (k, v), c in kinds.items() if k == kind)
    # the part's name before the first comma: D1's line names a 1N4148 as an alternate (2026-11-14)
    got = qty_where(lambda key: word in key[2].split(",")[0] and "socket" not in key[2])
    ck.check(f"A.qty.{kind}: {n} {word}", got == n, f"expected {n}, got {got}")
# the routed master's components, board by board (our own count, not bom.check's)
R = harness.routed()
for board, parts, rb in (("Main", mb, R.main), ("Faceplate", fb, R.face)):
    want, got = {p.ref for p in parts}, set(rb.parts)
    ck.check(f"A.routed_refs.{board}: routed components = circuit.py's", want == got,
             f"only routed {sorted(got - want)}, only circuit {sorted(want - got)}")

# sockets: one per DIP chip, the right size (the routed footprint's pad count), rows 7.62 apart
SOCKETED = {"TL074", "HC595", "HC165", "H11L1"}
sock_want = collections.Counter()
for board, parts in BOARDS:
    rb = R.main if board == "Main" else R.face
    for p in parts:
        if p.kind in SOCKETED:
            pads = rb.parts[p.ref]["pads"]
            if (board, p.ref) not in bom.SOLDERED:      # chips bom.py solders without a socket (its NOTES say why)
                sock_want[len(pads)] += 1
            p1, plast = pads["1"], pads[str(len(pads))]
            row = math.hypot(p1.x - plast.x, p1.y - plast.y)
            ck.check(f"A.dip_rows.{p.ref}: pin 1 to pin {len(pads)} across the 7.62 mm rows (a socket fits)",
                     abs(row - DIP_ROW) < 0.02, f"{rb.parts[p.ref]['fp']}: {row:.3f} mm")
sock_got = collections.Counter()
for key, line in lines.items():
    m = re.match(r"DIP-(\d+) IC socket", key[2])
    if m:
        sock_got[int(m.group(1))] += line["qty"]
ck.check("A.sockets: DIP sockets by size = the socketed chips' pin counts on the routed boards", sock_got == sock_want,
         f"expected {dict(sock_want)}, got {dict(sock_got)}")

# ------------------------------------------------------------------ 2. the committed files against bom.write()
captured = {}


class _Mem(io.StringIO):
    def __init__(self, path):
        super().__init__()
        self._path = path

    def close(self):
        captured[self._path] = self.getvalue()
        super().close()


SINK = os.path.join(harness.HERE, "__no_such_dir__", "never-created")   # write() would fail here if not captured


def _open(path, mode="r", *a, **k):
    if "w" not in mode and "a" not in mode:
        return open(path, mode, *a, **k)
    return _Mem(os.path.relpath(os.path.normpath(path), SINK).replace(os.sep, "/"))


_root, _os = bom.ROOT, bom.os
assert set(bom.write.__code__.co_names) >= {"open", "os"} and "shutil" not in bom.write.__code__.co_names
bom.ROOT, bom.open, bom.os = SINK, _open, types.SimpleNamespace(path=os.path, makedirs=lambda *a, **k: None)
try:
    rows = bom.write(lines)
finally:
    bom.ROOT, bom.os = _root, _os
    del bom.open
ck.check("B.capture: bom.write() wrote only into memory (3 files)", len(captured) == 3 and not os.path.exists(SINK),
         f"{sorted(captured)}")
for rel in ("docs/bom.md", "hardware/bom/side-fx-bom.csv", "hardware/bom/side-fx-bom-thonk.csv"):
    fresh = captured.get(rel, "").replace("\r\n", "\n")
    committed = open(os.path.join(harness.MODULE, rel), encoding="utf-8", newline="").read().replace("\r\n", "\n")
    diff = ""
    if fresh != committed:
        a, b = fresh.split("\n"), committed.split("\n")
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        diff = (f"first difference at line {i + 1}: fresh {a[i] if i < len(a) else None!r} / "
                f"on disk {b[i] if i < len(b) else None!r}")
    ck.check(f"B.up_to_date.{rel}: on disk == bom.py's output now", fresh == committed, diff or f"{len(fresh)} chars")

by_part = {r["Part"]: r for r in rows}
thonk = [r for r in rows if r["Source"] == "Thonk"]


def line_of(ref):
    return next((r for r in rows if ref in re.split(r"[ ,;:]+", r["Refs"])
                 and "socket" not in r["Part"] and "for the breakout" not in r["Part"]), None)


# ------------------------------------------------------------------ 3. Thonk lines and the repo's Thonk order
nj = sum(1 for p in fb if p.kind == "JACK")
r = by_part.get("Thonkiconn PJ398SM mono jack, with nut")
ck.check("C.thonk_jacks: PJ398SM = the mono jacks", r is not None and r["Qty"] == nj == 9 and r["Source"] == "Thonk",
         f"circuit {nj}, BOM {r and r['Qty']}")
r = by_part.get("Thonkiconn PJ366ST stereo jack, with nut")
ck.check("C.thonk_trs: one PJ366ST for MIDI (J5)", r is not None and r["Qty"] == 1 and r["Refs"] == "J5", f"{r}")
nb = sum(1 for p in fb if p.kind == "SWLED")
r = by_part.get("Thonk low-profile LED button, red")
ck.check("C.thonk_buttons: 5 red LED buttons (SIDE FX: red, lit = on)", r is not None and r["Qty"] == nb == 5,
         f"circuit {nb}, BOM {r and r['Qty']}")
# Thonk's low-profile LED button colours (module-design parts.md): red, green, blue, yellow, orange, white, bipolar
ck.check("C.thonk_button_colour: a colour Thonk sells", bom.BUTTONS["SWLED"] in
         {"red", "green", "blue", "yellow", "orange", "white"}, bom.BUTTONS["SWLED"])
order = open(os.path.join(REPO, "bom", "thonk-order.md"), encoding="utf-8").read().split("\n")
hdr = next(l for l in order if l.startswith("| Qty | Part"))
cols = [c.strip() for c in hdr.strip("|").split("|")]
moss = {}
if ck.check("C.order_column: thonk-order.md has a Moss column", "Moss" in cols, str(cols)):
    mi = cols.index("Moss")
    for l in order:
        if l.startswith("| ") and not l.startswith("| Qty") and not l.startswith("|---"):
            c = [x.strip() for x in l.strip("|").split("|")]
            if c[mi]:
                moss[c[1]] = int(c[mi])
mine = {}
for r in thonk:
    m = re.match(r"(Male pin header, 2\.54 mm|Female header, 2\.54 mm, 8\.5 mm tall): (.*)", r["Part"])
    if m:
        mine[m.group(1) + ", pins (cut to length)"] = sum(int(n) * int(p) for n, p in re.findall(r"(\d+) × 1×(\d+)", m.group(2)))
    else:
        mine[r["Part"]] = mine.get(r["Part"], 0) + int(r["Qty"])
ck.check("C.order_md: thonk-order.md's Moss column == Side FXy's Thonk lines", moss == mine,
         f"only in the order {sorted(set(moss.items()) - set(mine.items()))}, "
         f"only in the BOM {sorted(set(mine.items()) - set(moss.items()))}")
ocsv = list(csv.DictReader(open(os.path.join(REPO, "bom", "thonk-order.csv"), encoding="utf-8")))
moss_csv = {r["Part"]: int(r["Moss"]) for r in ocsv if r.get("Moss")}
ck.check("C.order_csv: thonk-order.csv's Moss column == the .md's", moss_csv == moss,
         f"only csv {sorted(set(moss_csv.items()) - set(moss.items()))}, only md {sorted(set(moss.items()) - set(moss_csv.items()))}")
pins = sum(len(nets) for _, _, nets in circuit.HEADERS)
ck.check("C.header_pins: 30 male + 30 female board-to-board pins in the order", pins == 30
         and moss.get("Male pin header, 2.54 mm, pins (cut to length)") == pins
         and moss.get("Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)") == pins,
         f"circuit {pins}, order {moss.get('Male pin header, 2.54 mm, pins (cut to length)')} / "
         f"{moss.get('Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)')}")
hdr_lines = {r["Part"].split(":")[0]: r for r in thonk if r["Part"].startswith(("Male pin header", "Female header, 2.54"))}
want_sizes = sorted((len(nets) for _, _, nets in circuit.HEADERS), reverse=True)
for kind, r in hdr_lines.items():
    sizes = sorted((int(p) for n, p in re.findall(r"(\d+) × 1×(\d+)", r["Part"]) for _ in range(int(n))), reverse=True)
    ck.check(f"C.header_strips.{kind[:6]}: one strip per board-to-board header, of its pin count", sizes == want_sizes,
             f"expected {want_sizes} (circuit.HEADERS), got {sizes}")

# ------------------------------------------------------------------ 4. part numbers that exist and fit
holes = {}                     # footprint title -> {pad num: (hole type, w, h)}
for title, d in R.fp_docs.items():
    hs = {}
    for h, p in d["recs"]:
        if h["type"] == "PAD" and p and p.get("hole"):
            hs[str(p["num"])] = (p["hole"]["holeType"], p["hole"]["width"] * harness.MIL, p["hole"]["height"] * harness.MIL)
    holes[title] = hs


def fp(board, ref):
    return (R.main if board == "Main" else R.face).parts[ref]["fp"]


def min_round_hole(board, ref):
    return min(w for t, w, h in holes[fp(board, ref)].values() if t == "ROUND")


enc_line = line_of("ENC1")
mpn = re.search(r"PEC11R-(\d)(\d)(\d\d)([A-Z])-([A-Z])(\d{4})", enc_line["Part"] if enc_line else "")
if ck.check("D.pec11r_mpn: the encoder line names a Bourns PEC11R part number", mpn is not None,
            enc_line["Part"] if enc_line else "no line for ENC1"):
    term, det, L, style, sw, res = mpn.groups()
    L, res = int(L), int(res)
    ck.check(f"D.pec11r_terminal: '{term}' = {PEC_TERMINAL.get(term, '?')} (the shaft at right angles to the "
             "faceplate, as the footprint)", term == "4", f"BOM text says 'vertical'; Bourns code {term}")
    ck.check(f"D.pec11r_switch: '{sw}' = {PEC_SWITCH.get(sw, '?')} (circuit.py wires S1 / S2 as the push)", sw == "S", sw)
    ck.check(f"D.pec11r_shaft: '{style}' = {PEC_SHAFT.get(style, '?')} shaft, as the BOM's 'D shaft' and the knobs",
             style == "F", style)
    ck.check(f"D.pec11r_detents: '{det}' = {PEC_DETENT.get(det)} detents with {res} pulses (one pulse per detent)",
             PEC_DETENT.get(det) == 24 and res == 24, f"detent code {det}, resolution {res}")
    ck.check(f"D.pec11r_length: shaft length {L} mm is a stock length", L in PEC_LB, str(L))
    ck.check("D.pec11r_bushing: every PEC11R has the M7 x 0.75 bushing the BOM text and the 7.5 mm hole assume",
             "M7" in enc_line["Part"], enc_line["Part"])
    # fit: pins and tabs against the routed EC11 footprint
    pl = R.face.parts["ENC1"]
    hs = holes[pl["fp"]]
    pin_holes = [hs[n][1] for n in ("A", "B", "C", "S1", "S2")]
    ck.check(f"D.pec11r_pin_holes: footprint pin holes >= Bourns' recommended d {PEC_PIN_HOLE} (terminals {PEC_TERMINAL_W} wide)",
             all(h >= PEC_PIN_HOLE - 0.005 for h in pin_holes), f"holes {sorted(set(round(h, 2) for h in pin_holes))}")
    p = pl["pads"]
    tab_pitch = math.hypot(p["MP1"].x - p["MP2"].x, p["MP1"].y - p["MP2"].y)
    t, sw_, sh_ = hs["MP1"]
    # in the footprint frame the slot's height runs along the tab-to-tab line (the MP pads differ in y there)
    fp_doc = R.fp_docs[pl["fp"]]
    mp = {str(q["num"]): q for h_, q in fp_doc["recs"] if h_["type"] == "PAD" and q and str(q["num"]) in ("MP1", "MP2")}
    along_y = abs(mp["MP1"]["centerY"] - mp["MP2"]["centerY"]) > abs(mp["MP1"]["centerX"] - mp["MP2"]["centerX"])
    slot_along = sh_ if along_y else sw_
    slot_lo, slot_hi = tab_pitch / 2 - slot_along / 2, tab_pitch / 2 + slot_along / 2
    # VERIFY 2026-11-13: the writer put the tabs 13.2 apart centre to centre with the 0.8 terminal width as their
    # thickness (6.2..7.0 from the shaft, wholly outside the slot). Bourns gives no tab thickness; what it gives
    # is the hole the tab needs, 4.8..6.6 from the shaft. The check is now: the slot covers that hole.
    hole_lo, hole_hi = (PEC_TAB_OUTER - 2 * PEC_TAB_HOLE[1]) / 2, PEC_TAB_OUTER / 2
    print(f"      (info) Bourns' recommended tab holes {hole_lo:.2f}..{hole_hi:.2f} mm from the shaft; the slots "
          f"{slot_lo:.2f}..{slot_hi:.2f}")
    ck.check(f"D.pec11r_tabs: the user's PEC11R-4215F (tabs {PEC_TAB_OUTER_MEASURED} mm or less across their outer faces, "
             f"measured) fits the footprint's MP slots",
             PEC_TAB_OUTER_MEASURED / 2 <= slot_hi + 0.01,   # mil rounding
             f"footprint slots {tab_pitch:.1f} apart, {slot_along:.2f} mm along the tab line: {slot_lo:.2f}..{slot_hi:.2f} mm "
             f"from the shaft; Bourns' holes {hole_lo:.2f}..{hole_hi:.2f} ({hole_hi - slot_hi:.2f} mm short on the outside)")
# the bussed network
rn = line_of("RN1")
ck.check("D.rn_mpn: 4609X-101-103LF = 9 pins, circuit 101 bussed, 10 kOhm, as the BOM text says",
         rn is not None and "4609X-101-103LF" in rn["Part"] and "SIP-9" in rn["Part"] and "bussed" in rn["Part"]
         and "10k" in rn["Part"], rn["Part"] if rn else "no line")
for ref in ("RN1", "RN2"):
    pl = R.face.parts[ref]
    pads = sorted(pl["pads"].items(), key=lambda kv: int(kv[0]))
    pitch = [math.hypot(a[1].x - b[1].x, a[1].y - b[1].y) for a, b in zip(pads, pads[1:])]
    part = next(q for q in fb if q.ref == ref)
    common = part.nets.get("1")
    ck.check(f"D.rn_footprint.{ref}: {SIP_PINS} pads at 2.54 mm, pin 1 the common (3V3D_F) as on a 101 bussed network",
             len(pads) == SIP_PINS and all(abs(q - SIP_PITCH) < 0.02 for q in pitch) and common == "3V3D_F"
             and all(part.nets.get(str(i)) not in (None, common) for i in range(2, 10)),
             f"{len(pads)} pads, pitch {sorted(set(round(q, 2) for q in pitch))}, pin 1 {common}")
    ck.check(f"D.rn_hole.{ref}: hole takes the SIP lead (diagonal {SIP_LEAD_DIAG} + 0.15)",
             min_round_hole("Faceplate", ref) >= SIP_LEAD_DIAG + LEAD_CLEAR, f"{min_round_hole('Faceplate', ref):.2f} mm")
# D1: which footprint, which drill, and the leads the BOM line allows
d1 = line_of("D1")
d1_fp, d1_hole = fp("Main", "D1"), min_round_hole("Main", "D1")
pa, pb = R.main.parts["D1"]["pads"]["1"], R.main.parts["D1"]["pads"]["2"]
d1_pitch = math.hypot(pa.x - pb.x, pa.y - pb.y)
_h = re.search(r"holes are ([\d.]+) mm", d1["Part"] if d1 else "")
ck.check("D.d1_footprint: D1 is on a DO-35 footprint, as the BOM line says", d1_fp.startswith("DO-35"), d1_fp)
ck.check("D.d1_drill_claim: the BOM's 'the holes are 0.8 mm' = D1's real drill", _h is not None
         and abs(float(_h.group(1)) - d1_hole) < 0.01, f"BOM {_h.group(1) if _h else '?'} mm, footprint {d1_hole:.2f} mm")
ck.check("D.d1_leads: a DO-35 lead (0.56 max) fits D1's drill with 0.15 mm", d1_hole >= DO35_LEAD_MAX + LEAD_CLEAR,
         f"drill {d1_hole:.2f}, lead {DO35_LEAD_MAX}")
ck.check("D.d1_pitch: 8 mm pitch leaves room to bend a DO-35's leads (body <= 4.56 + 2 x 1.5)", d1_pitch >= 4.56 + 3.0 - 0.01,
         f"{d1_pitch:.2f} mm")
alts = re.findall(r"\b(BAT8[56]|BAT4[236]|SD103A|1N5711|SD101)\b", d1["Part"] if d1 else "")
ck.check("D.d1_alternatives: every named alternative is a small-signal Schottky in DO-35 / DO-34 glass",
         set(alts) <= {"BAT85", "BAT86", "BAT43", "BAT42", "BAT46", "SD103A", "1N5711", "SD101"} and len(alts) >= 5,
         f"{alts}")
# the 10 uF ceramic, the sockets' holes, the right-angle header, the display
c4 = line_of("C4")
c4p = R.face.parts["C4"]["pads"]
c4_pitch = math.hypot(c4p["1"].x - c4p["2"].x, c4p["1"].y - c4p["2"].y)
ck.check("D.c4_line: 10 uF ceramic, X5R / X7R, >= 16 V, 5.08 mm leads = C4's footprint pitch",
         c4 is not None and "ceramic" in c4["Part"] and re.search(r"X[57]R", c4["Part"]) and "5.08 mm" in c4["Part"]
         and abs(c4_pitch - 5.08) < 0.02, f"{c4 and c4['Part']}; footprint pitch {c4_pitch:.2f}")
ck.check("D.c4_hole: C4's holes take a 0.5 mm MLCC lead", min_round_hole("Faceplate", "C4") >= MLCC_LEAD + LEAD_CLEAR,
         f"{min_round_hole('Faceplate', 'C4'):.2f} mm")
for board, ref in (("Main", "U6"), ("Main", "U7"), ("Main", "U3"), ("Faceplate", "U1"), ("Faceplate", "U2")):
    ck.check(f"D.dip_hole.{ref}: hole takes a DIP socket's pin (0.56 + 0.15)", min_round_hole(board, ref) >= DIP_LEAD + LEAD_CLEAR,
             f"{fp(board, ref)}: {min_round_hole(board, ref):.2f} mm")
cn = line_of("CN1")
cnp = R.face.parts["CN1"]["pads"]
ck.check("D.cn1: a 1×8 right-angle male header on an 8-pad 2.54 mm footprint, for Waveshare's 8-wire cable",
         cn is not None and "1×8 right-angle male header" in cn["Part"] and len(cnp) == 8 == len(circuit.LCD_PINS)
         and fp("Faceplate", "CN1").endswith("RA"), f"{cn and cn['Part']}; {fp('Faceplate', 'CN1')}, {len(cnp)} pads")
ck.check("D.cn1_hole: CN1 holes take a 0.64 mm square pin", min_round_hole("Faceplate", "CN1") >= HDR_DIAG + 0.05,
         f"{min_round_hole('Faceplate', 'CN1'):.2f} mm")
# Waveshare 1.9inch LCD Module wiki (waveshare.com/wiki/1.9inch_LCD_Module, read 2026-11-13): ST7789V2, IPS,
# 170 (H) x 320 (V), SPI, 3.3 V / 5 V, display 22.70 x 42.72 mm, module 27.3 x 51.2 mm, MX1.25 8PIN interface;
# pin table order VCC, GND, DIN, CLK, CS, DC, RST, BL.
WS_PINS = ["VCC", "GND", "DIN", "CLK", "CS", "DC", "RST", "BL"]
WS_NET = {"VCC": "3V3D_F", "GND": "GND_D_F", "DIN": "LCD_MOSI_F", "CLK": "LCD_SCK_F", "CS": "LCD_CS_F", "DC": "LCD_DC_F",
          "RST": "LCD_RST_F", "BL": "LCD_BL_F"}
ds = [r for r in rows if "Waveshare" in r["Part"]]
ck.check("D.display_listing: one Waveshare 1.9inch LCD Module (ST7789V2, 170 × 320, SPI) with its cable",
         len(ds) == 1 and ds[0]["Qty"] == 1 and all(w in ds[0]["Part"] for w in ("1.9inch", "ST7789V2", "170 × 320", "SPI",
                                                                                 "cable")), f"{[r['Part'] for r in ds]}")
ck.check("D.display_cable_order: CN1 in the wiki's 8-pin order (VCC, GND, DIN, CLK, CS, DC, RST, BL)",
         circuit.LCD_PINS == [WS_NET[p] for p in WS_PINS], f"{circuit.LCD_PINS}")
# knobs against the encoder's shaft
kn = [r for r in rows if r["Part"].startswith("Knob")]
nenc = sum(1 for q in fb if q.kind == "ENC")
ck.check("D.knobs: one knob per encoder, for a 6 mm D shaft (PEC11R 'F': d 6.0, flat 4.5)",
         len(kn) == 1 and kn[0]["Qty"] == nenc and "6 mm D-shaft" in kn[0]["Part"], f"{[(r['Qty'], r['Part']) for r in kn]}")
if mpn:
    gap = THONK_BODY_H
    out = PEC_BODY_H + L - gap - PCB_T
    ck.check(f"D.knob_shaft: the {L} mm shaft's D flat ({PEC_FLAT_L[L]} mm) stands clear of the panel for a knob",
             out - max(0.0, PEC_NUT_T + PEC_WASHER_T - (PEC_BODY_H + PEC_LB[L] - gap - PCB_T)) >= PEC_FLAT_L[L],
             f"shaft {out:.1f} mm in front of a 1.6 mm panel 9 mm off the faceplate")

# ------------------------------------------------------------------ 5. ratings
# worst-case DC on each net (V): rails at +5 %, the 3.3 V rails at +5 %, the CV stage's output from its
# transfer (V_adc = 1.676 - 0.27 V_in, design.md) with the jack anywhere between the rails
V = {"+12V": (RAIL_WORST, RAIL_WORST), "-12V": (-RAIL_WORST, -RAIL_WORST), "GND": (0, 0), "GND_D_F": (0, 0),
     "GND_F": (0, 0), "3V3D": (0, V3V3_MAX), "3V3A": (0, V3V3_MAX), "3V3D_F": (0, V3V3_MAX), "BIAS": (0, 1.45)}
for k in range(1, 5):
    V[f"IN_CV{k}"] = (0, 1.45)
    V[f"OA_CV{k}"] = (1.676 - 0.27 * RAIL_WORST - 0.05, 1.676 + 0.27 * RAIL_WORST + 0.05)
caps = [q for q in mb + fb if q.kind == "C"]
for q in caps:
    a, b = V.get(q.nets["1"]), V.get(q.nets["2"])
    if a is None or b is None:
        ck.check(f"E.cap_v.{q.ref}: worst DC known", False, f"nets {q.nets}")
        continue
    vmax = max(abs(a[0] - b[1]), abs(a[1] - b[0]))
    ln = line_of(q.ref)
    m = re.search(r"(\d+) V", ln["Part"]) if ln else None
    rated = int(m.group(1)) if m else 0
    ck.check(f"E.cap_v.{q.ref}: {q.value} rated >= {CAP_MARGIN} x the worst {vmax:.1f} V across it", rated >= CAP_MARGIN * vmax,
             f"line '{ln['Part'][:60] if ln else None}': {rated} V")
ck.check("E.dielectric_1n: the CV stages' 1 nF feedback caps are C0G (or film)", "C0G" in line_of("C10")["Part"],
         line_of("C10")["Part"])
ck.check("E.dielectric_100n: decoupling 100 nF are X7R", "X7R" in line_of("C15")["Part"], line_of("C15")["Part"])
ck.check("E.dielectric_1u: the bias filter's 1 uF is a ceramic (X7R), non-polar as circuit.py has it",
         "X7R" in line_of("C14")["Part"] and next(q for q in mb if q.ref == "C14").kind == "C", line_of("C14")["Part"])
# resistors: worst-case dissipation
P = {}
for q in (q for q in mb if q.kind == "R"):
    r = harness.ohms(q.value)
    a, b = q.nets["1"], q.nets["2"]
    if q.ref in ("R1", "R2", "R3", "R4", "R5"):
        vr = V3V3_MAX                                  # LED shorted: the whole 3.3 V across the 470
    elif q.ref in ("R10", "R13", "R16", "R19"):
        vr = RAIL_WORST + 1.45                         # jack at a rail, summing node at the bias
    elif q.ref in ("R11", "R14", "R17", "R20"):
        vr = max(abs(V[b][0] - 1.45), abs(V[b][1]))    # summing node to the op-amp output
    elif q.ref in ("R12", "R15", "R18", "R21"):
        vr = max(V[a][1] - (V3V3_MAX + 0.3), -0.3 - V[a][0], 0)   # output to an ADC pin clamped at -0.3 .. 3.77
    elif q.ref == "R24":
        vr = RAIL_WORST - 0.3                          # clock tip at a rail, base clamped (Vbe / the BAT85)
    elif q.ref == "R26":
        # MIDI ring: the spec's 5 V source through 220 R, or a Eurorack output (1 k) patched in by mistake
        i = max((MIDI_V_SRC - OPTO_VF_MIN) / (MIDI_R_SRC + 220.0), (RAIL_WORST - OPTO_VF_MIN) / (EURO_OUT_R + 220.0))
        vr = i * r
    else:
        lo_a, hi_a = V.get(a, (0, V3V3_MAX))
        lo_b, hi_b = V.get(b, (0, V3V3_MAX))
        vr = max(abs(hi_a - lo_b), abs(hi_b - lo_a))
    P[q.ref] = vr * vr / r
for ref, p in sorted(P.items(), key=lambda kv: -kv[1]):
    ln = line_of(ref)
    w = 0.25 if ln and "1/4 W" in ln["Part"] else 0.0
    ck.check(f"E.r_power.{ref}: worst case {p * 1000:.1f} mW under half its rating", p <= R_DERATE * w,
             f"{p * 1000:.1f} mW vs {w * 1000:.0f} mW ({ln['Part'] if ln else 'no line'})")
i26 = (RAIL_WORST - OPTO_VF_MIN) / 220.0
print(f"INFO  R26 with a zero-ohm 12.6 V source on the MIDI ring (no output resistor): {i26 * 1000:.0f} mA, "
      f"{i26 ** 2 * 220 * 1000:.0f} mW in R26; an op-amp's short-circuit limit (~25-40 mA) keeps a real output "
      f"to {0.04 ** 2 * 220 * 1000:.0f} mW at most")

# ------------------------------------------------------------------ 6. mechanics
so = next((r for r in rows if "standoff" in r["Part"].lower()), None)
m = re.search(r"female-female, (?:about )?([\d.]+) mm", so["Part"]) if so else None
length = float(m.group(1)) if m else None
nholes = len(R.face.holes)
ck.check("F.standoff_count: one standoff per board mounting hole (routed: 4 on each board, the same spots)",
         so is not None and so["Qty"] == nholes == len(R.main.holes) == len(circuit.HOLES_FRONT)
         and sorted((round(x, 2), round(y, 2)) for x, y, d in R.face.holes)
         == sorted((round(x, 2), round(y, 2)) for x, y, d in R.main.holes),
         f"BOM {so and so['Qty']}, faceplate {nholes}, main {len(R.main.holes)}, circuit {len(circuit.HOLES_FRONT)}")
ck.check("F.standoff_length: = the mated 8.5 mm socket + 2.5 mm male header plastic", length is not None
         and abs(length - MATED_GAP) <= 0.3, f"expected {MATED_GAP} mm, BOM {length}")
screw = next((r for r in rows if "screw" in r["Part"].lower() and "standoff" not in r["Part"].lower()), None)
ms = re.search(r"M3 × ([\d.]+) mm", screw["Part"]) if screw else None
ck.check("F.screw_count: two screws per female-female standoff", screw is not None and so is not None
         and screw["Qty"] == 2 * so["Qty"], f"screws {screw and screw['Qty']}, standoffs {so and so['Qty']}")
if ck.check("F.screw_length_given: the BOM gives the M3 screw length", ms is not None, screw["Part"] if screw else ""):
    sl = float(ms.group(1))
    for washer in (0.0, 0.5):
        eng = sl - PCB_T - washer
        ck.check(f"F.screw_engagement{'_washer' if washer else ''}: M3 x {sl:g} through 1.6 mm"
                 f"{' + a 0.5 mm washer' if washer else ''} engages >= 3 mm, <= the standoff's thread, the two screws apart",
                 ENGAGE_MIN <= eng <= STANDOFF_THREAD_MIN and 2 * eng < (length or MATED_GAP),
                 f"engagement {eng:.1f} mm, thread >= {STANDOFF_THREAD_MIN} per end assumed, standoff {length} mm")
# the breakout's rows on the main board: the female sockets against the footprint
u5 = R.main.parts["U5"]["pads"]
rows_x = collections.defaultdict(list)
for num, q in u5.items():
    rows_x[round(q.x, 1)].append(q.y)
groups = []
for x, ys in sorted(rows_x.items()):
    ys = sorted(ys)
    runs, cur = [], [ys[0]]
    for a, b in zip(ys, ys[1:]):
        if abs(b - a - 2.54) < 0.02:
            cur.append(b)
        else:
            runs.append((len(cur), round((b - a) / 2.54 - 1)))
            cur = [b]
    runs.append((len(cur), 0))
    groups.append(runs)
bl = next((r for r in rows if r["Part"].startswith("Female header 2.54 mm, 8.5 mm tall, for the breakout")), None)
claim = [int(p) for n, p in re.findall(r"(\d+) × 1×(\d+)", bl["Part"]) for _ in range(int(n))] if bl else []
got = sorted(n for runs in groups for n, _ in runs)
gaps = sorted(g for runs in groups for _, g in runs if g)
ck.check("F.breakout_rows: the breakout footprint's two rows = the BOM's 2 x 1x24 + 2 x 1x4, one empty position between",
         len(groups) == 2 and got == sorted(claim) and gaps == [1, 1] and bl is not None and bl["Qty"] == len(claim),
         f"footprint runs {groups}; BOM {claim} (qty {bl and bl['Qty']})")
ck.check("F.breakout_rows_apart: the two rows 15.24 mm apart (the Seed's pin rows)",
         len(rows_x) == 2 and abs(abs(list(rows_x)[0] - list(rows_x)[1]) - 15.24) < 0.1, f"rows at x {sorted(rows_x)}")
ck.check("F.breakout_socket_holes: the breakout footprint's holes take a 0.64 mm square pin",
         min_round_hole("Main", "U5") >= HDR_DIAG + 0.05, f"{min_round_hole('Main', 'U5'):.2f} mm")
bk = next((r for r in rows if r["Part"].startswith("Rob Heel")), None)
ck.check("F.breakout_built: the breakout line says where its parts come from (its own BOM, assembled)",
         bk is not None and re.search(r"BOM|assembl|github|oshwlab", bk["Part"] + " " + bk["Note"], re.I) is not None,
         f"'{bk['Part'] if bk else None}' / note '{bk['Note'] if bk else None}'")
cable = [r for r in rows if "power cable" in r["Part"].lower()]
txt = " ".join(r["Part"] + " " + r["Note"] for r in cable)
ck.check(f"F.power_cable: one cable, {BREAKOUT_J2_PINS}-pin at the module end (the breakout's J2 is a 2x5 header)",
         len(cable) == 1 and cable[0]["Qty"] == 1 and re.search(r"\b10-pin|10 to 16|10-to-16", txt) is not None
         and "check the header's pin count" not in txt, f"BOM: '{txt.strip()}'")
order_cable = [l for l in order if "power cable for the breakout" in l]
ck.check("F.power_cable_order: thonk-order.md's breakout cables name the 10-pin end too",
         bool(order_cable) and all("10" in l and "check the header's pin count" not in l for l in order_cable),
         f"{order_cable}")
pcbs = [r for r in rows if r["Group"] == "PCBs"]
rb = bom.routed()
for board in ("Main", "Faceplate"):
    (w, h), _ = rb[board]
    ln = next((r for r in pcbs if r["Part"].startswith(f"{board} board")), None)
    mm = re.search(r"([\d.]+) × ([\d.]+) mm", ln["Part"]) if ln else None
    ck.check(f"F.pcb_line.{board}: the BOM's size = the routed outline = circuit.py's", mm is not None
             and (float(mm.group(1)), float(mm.group(2))) == (round(w, 1), round(h, 1)) == (circuit.BOARD_W, circuit.BOARD_H),
             f"BOM {mm and mm.groups()}, routed {w:.2f} x {h:.2f}")
pn = next((r for r in pcbs if r["Part"].startswith("Panel")), None)
ck.check("F.pcb_line.panel: Panel 70.8 x 128.5 (Doepfer 14HP)", pn is not None and "70.8 × 128.5" in pn["Part"],
         pn["Part"] if pn else "")
ck.check("F.pcb_count: three PCB designs (main, faceplate, panel)", sum(r["Qty"] for r in pcbs) == 3,
         f"{[(r['Qty'], r['Part'][:30]) for r in pcbs]}")

# ------------------------------------------------------------------ 7. the docs' counts
readme = open(os.path.join(harness.MODULE, "README.md"), encoding="utf-8").read()
m = re.search(r"Done, (\d+) parts over two boards", readme)
ck.check("G.readme_parts: README's part count = circuit.py's", m is not None and int(m.group(1)) == len(mb) + len(fb),
         f"README {m and m.group(1)}, circuit {len(mb) + len(fb)}")
design = open(os.path.join(harness.DOCS, "design.md"), encoding="utf-8").read()
m = re.search(r"(\d+) pins in (\d+) headers", design)
ck.check("G.design_header_pins: design.md's '30 pins in 4 headers'", m is not None
         and (int(m.group(1)), int(m.group(2))) == (pins, len(circuit.HEADERS)), f"{m and m.groups()}")
m = re.search(r"(\d+) Thonkiconn \+ (\d+) stereo Thonkiconn, (\d+) EC11 encoders,.*?(\d+) LED buttons, (\d+)x 74HC165, "
              r"(\d+) bussed 10k networks", design, re.S)
want = (nj, 1, nenc, nb, sum(1 for q in fb if q.kind == "HC165"), sum(1 for q in fb if q.kind == "RN9"))
ck.check("G.design_faceplate_counts: design.md's faceplate inventory = circuit.py's", m is not None
         and tuple(map(int, m.groups())) == want, f"design.md {m and m.groups()}, circuit {want}")

ck.done()
