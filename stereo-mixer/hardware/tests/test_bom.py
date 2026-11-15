"""BOM group: the stereo mixer's (Mycelium's) bill of materials.

Checks
  - bom.py's in-memory build against circuit.py: every netlist part owned by
    exactly one line, quantities per kind and value on both boards, the
    routed master's designators;
  - the committed docs/bom.md, hardware/bom/stereo-mixer-bom.csv and
    -thonk.csv against a fresh build (bom.write() with its ROOT pointed
    into a scratch folder, so nothing in the repo is written);
  - the Thonk table against the faceplate parts (pots by taper / value /
    single / dual, jacks, LED buttons, knobs) and against bom/thonk-order.md's
    Mycelium column;
  - part choices, ratings and types against the datasheets (constants below):
    footprints and pitches (DIP-14 chips, the CD4053B mute switches on the
    DIP-16 since 2026-11-15, diodes, caps, standing resistors, headers), the
    CD4053BE line and its 8 DIP-16 sockets, the 10 R rail filters against
    design.md's maximum +12 V current;
  - the mechanics: standoff length against the mated header + socket height,
    the power cable, the knob count, PCB quantities.

Footprints and refs are read from the routed master; since 2026-11-15 its
main board is the generated placement (placed, unrouted), so they are the
CD4053B design's.

Run from stereo-mixer/hardware/tests:  python test_bom.py
"""
import collections
import csv
import io
import os
import re
import sys
import tempfile

import harness

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ck = harness.Checks("bom")
circuit = harness.load("circuit")
bom = harness.load("bom")
REPO = os.path.normpath(os.path.join(harness.MODULE, ".."))

# ------------------------------------------------------------------ datasheet constants
# TI CD4053B (SCHS047O rev. O, May 2026): 5.1 absolute maximum supply V+ to V- (VDD - VEE) -0.5 .. 20 V; features
# "single supply range 3 V to 20 V"; DC input voltage -0.5 .. VDD + 0.5 V. Orderable CD4053BE = PDIP (N), 16 pins
# (package option addendum); the M / NS / PW suffixes are SMD. (Replaces the AQY212EH PhotoMOS, 2026-11-15.)
CD4053_SUPPLY_MAX = 20.0   # V, VDD - VEE, abs max
CD4053_THT = "CD4053BE"    # the through-hole (PDIP-16) part number
# TI TL074 (SLOS080): TL074CN / TL074ACN / TL074BCN are the PDIP-14 (N) parts. Supply max +-18 V.
TL074_VCC_MAX = 18.0       # V per rail, abs max
# TI CD4093B / CD4013B (SCHS115, SCHS023): CD40xxBE = PDIP-14, VDD 3..18 V recommended, 20 V abs max.
CMOS_VDD_MAX = 18.0        # V recommended max
RAIL = 12.0                # V, Eurorack rail, nominal
RAIL_WORST = 12.6          # V, a busboard at +5 %
# 1N5819 (Vishay / ON 1N5817-19 datasheet): 1 A, 40 V VRRM, DO-41 (DO-204AL).
D5819_VRRM = 40.0
# BAT85 (Vishay): 30 V VR, DO-35 (D903, D904; until 2026-11-14 D903 was a 1N4148).
# Capacitor voltage: a ceramic or electrolytic must be rated above the DC across it; 1.5x margin is the
# usual derating (and X7R loses capacitance with DC bias). Rated voltages of the library parts the
# exporter uses (easyeda_export.DEV / C_NEW):
#   TDK FG28X7R1H104KNT00: 100 nF X7R 50 V ("1H" = 50 V, TDK FG series catalogue)
#   TDK FG28C0G1H220JNT00: 22 pF C0G 50 V
#   KYOCERA AVX SR305C105KAR: 1 uF X7R 50 V ("5" = 50 V in AVX SkyCap SR code), 5.08 mm leads
#   KNSCHA 178MU0033 (library 10 uF): dipped tantalum, 10 uF +-20 % 35 V, P 2.54 mm (LCSC C18164674, 2026-11-04)
CAP_MARGIN = 1.5
# Standard 2.54 mm headers (Samtec / Harwin / generic): female socket body 8.5 mm tall (the BOM's part);
# male header plastic 2.5 mm. Fully mated, the male's plastic sits on the socket's top, so the board
# gap = socket body + male plastic = 8.5 + 2.5 = 11.0 mm (design.md: "about 11 mm").
FEMALE_BODY = 8.5          # mm, typ
MALE_PLASTIC = 2.5         # mm, typ
MATED_GAP = FEMALE_BODY + MALE_PLASTIC
HOLE_R_STANDING = 0.0      # filled below from the routed export


def thonk_rows(rows):
    return [r for r in rows if r["Source"] == "Thonk"]


# ------------------------------------------------------------------ 1. in-memory build
lines, owned = bom.build()
problems = bom.check(owned)
ck.check("bom.check: every part owned once, refs match the routed master", not problems,
         f"expected 0 problems, got {len(problems)}: {problems[:4]}")

mb, fb = circuit.main_board_parts(), circuit.faceplate_parts()
# a socket line names the chips it carries but buys sockets, not the chips: it does not count as their line
part_lines = {k: line for k, line in lines.items() if not k[2].endswith("IC socket")}
for board, parts in (("Main", mb), ("Faceplate", fb)):
    for p in parts:
        n = sum(1 for line in part_lines.values() if (board, p.ref) in line["refs"])
        if n != 1:
            ck.check(f"one line per part {board} {p.ref}", False, f"expected 1 line, got {n}")
ck.check("every netlist part sits in exactly one line's refs",
         all(sum(1 for line in part_lines.values() if (b, p.ref) in line["refs"]) == 1
             for b, ps in (("Main", mb), ("Faceplate", fb)) for p in ps),
         f"{len(mb)} main + {len(fb)} faceplate parts")
socketed = sorted(r for k, line in lines.items() if k[2].endswith("IC socket") for _, r in line["refs"])
ck.check("the socket lines carry exactly the DIP chips (U1-U18: TL074, CD4093B, CD4013B, CD4053B), each once",
         socketed == sorted(p.ref for p in mb if p.kind in ("TL074", "CD4093", "CD4013", "CD4053"))
         and len(socketed) == 18, f"{socketed}")

# quantities per kind and value against circuit.py
want = collections.Counter()
for board, parts in (("Main", mb), ("Faceplate", fb)):
    for p in parts:
        d = bom.describe(p)
        if d:
            want[d] += 1
for key, n in sorted(want.items()):
    got = lines.get(key, {}).get("qty", 0)
    ck.check(f"qty {key[2][:50]}", got == n, f"expected {n} (count of circuit.py parts), got {got}")
# every quantity equals the number of refs it owns (no line that adds qty without refs, except the extras)
for key, line in lines.items():
    if line["refs"] and key[1] not in ("Connectors",) and key[2] not in ("",):
        ck.check(f"qty == refs {key[2][:50]}", line["qty"] == len(set(line["refs"])),
                 f"expected {len(set(line['refs']))}, got {line['qty']}")

# kind/value counts from first principles (circuit.py's structure, counted independently of describe())
kinds = collections.Counter((p.kind, p.value) for p in mb + fb)
ck.check("resistor total: BOM == circuit.py", sum(n for (k, v), n in kinds.items() if k == "R") ==
         sum(line["qty"] for key, line in lines.items() if key[1] == "Resistors"),
         f"circuit {sum(n for (k, v), n in kinds.items() if k == 'R')}, BOM "
         f"{sum(line['qty'] for key, line in lines.items() if key[1] == 'Resistors')}")
ck.check("C + CP count", sum(n for (k, v), n in kinds.items() if k in ("C", "CP")) ==
         sum(line["qty"] for key, line in lines.items() if key[1] == "Capacitors"),
         f"circuit {sum(n for (k, v), n in kinds.items() if k in ('C', 'CP'))}, BOM "
         f"{sum(line['qty'] for key, line in lines.items() if key[1] == 'Capacitors')}")


# ------------------------------------------------------------------ 2. the committed files against a fresh build
SCRATCH = os.path.join(os.environ.get("TEMP", tempfile.gettempdir()), "claude", "C--Users-joep-Code-synth-git",
                       "01cd17fb-22f5-4709-9954-d90581efdb03", "scratchpad", "bom")
os.makedirs(os.path.join(SCRATCH, "docs"), exist_ok=True)
_root = bom.ROOT
bom.ROOT = SCRATCH                      # write() puts docs/bom.md and hardware/bom/*.csv under ROOT
try:
    rows = bom.write(lines)
finally:
    bom.ROOT = _root
for rel in ("docs/bom.md", "hardware/bom/stereo-mixer-bom.csv", "hardware/bom/stereo-mixer-bom-thonk.csv"):
    fresh = open(os.path.join(SCRATCH, rel), encoding="utf-8", newline="").read().replace("\r\n", "\n")
    committed = open(os.path.join(harness.MODULE, rel), encoding="utf-8", newline="").read().replace("\r\n", "\n")
    diff = ""
    if fresh != committed:
        a, b = fresh.split("\n"), committed.split("\n")
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        diff = (f"first difference at line {i + 1}: fresh {a[i] if i < len(a) else None!r} / "
                f"committed {b[i] if i < len(b) else None!r}")
    ck.check(f"committed {rel} == fresh bom.py output", fresh == committed, diff or f"{len(fresh)} chars identical")

thonk = thonk_rows(rows)
by_part = {r["Part"]: r for r in rows}

# ------------------------------------------------------------------ 3. the Thonk table against the faceplate
singles = collections.Counter(v.upper() for _, _, v, _ in circuit.POTS)
duals = collections.Counter(v.upper() for _, _, v, _, _ in circuit.POTS2)
for v, n in singles.items():
    r = by_part.get(f"Alpha 9 mm vertical pot {v}, T18 shaft")
    ck.check(f"Thonk single pot {v}", r is not None and r["Qty"] == n and r["Source"] == "Thonk",
             f"expected {n} single {v} from Thonk (circuit.POTS), got {r and r['Qty']}")
for v, n in duals.items():
    r = by_part.get(f"Alpha 9 mm vertical dual-gang pot {v} (RD902F), T18 shaft")
    ck.check(f"Thonk dual-gang pot {v}", r is not None and r["Qty"] == n and r["Source"] == "Thonk",
             f"expected {n} dual {v} (circuit.POTS2), got {r and r['Qty']}")
pot_lines = [r for r in thonk if r["Part"].startswith("Alpha 9 mm")]
ck.check("pot lines total = 25 pots (21 single + 4 dual)",
         sum(r["Qty"] for r in pot_lines) == len(circuit.POTS) + len(circuit.POTS2) == 25,
         f"expected 25, BOM {sum(r['Qty'] for r in pot_lines)}, circuit {len(circuit.POTS)} + {len(circuit.POTS2)}")
# Thonk's stock list (module-design parts.md, 2026-10-31) and Thonk's dual-gang page (fetched 2026-11-04):
THONK_SINGLE = {"B5K", "B10K", "B25K", "B50K", "B100K", "B250K", "B1M", "A50K", "A100K", "A1M"}
THONK_DUAL_IN_STOCK = {"B10K", "B100K", "B1M", "A10K", "A100K", "A1M"}   # B50K / A50K out, 2026-11-04
ck.check("single pot values are ones Thonk stocks", set(singles) <= THONK_SINGLE,
         f"expected within {sorted(THONK_SINGLE)}, got {sorted(singles)}")
ck.check("dual-gang values are in stock at Thonk (thonk.co.uk dual-gang page, 2026-11-04)",
         set(duals) <= THONK_DUAL_IN_STOCK, f"got {sorted(duals)}")
stale = [n for n in bom.NOTES if "dual-gang" in n.lower() and "check before ordering" in n.lower()]
ck.check("BOM note on dual-gang A100K stock is current", not stale,
         "expected no 'not in stock, check before ordering' note: Thonk lists A100K dual-gang T18 in stock "
         f"(2026-11-04); got: {stale[0][:110] if stale else ''}...")

njacks = sum(1 for p in fb if p.kind == "JACK")
r = by_part.get("Thonkiconn PJ398SM mono jack, with nut")
ck.check("jacks: 17 PJ398SM from Thonk", r is not None and r["Qty"] == njacks == len(circuit.JACKS) == 17,
         f"expected 17, circuit {njacks}, BOM {r and r['Qty']}")
nbtn = sum(1 for p in fb if p.kind == "SWLED")
r = by_part.get("Thonk low-profile LED button, red")
ck.check("LED buttons: 8 red (lit = muted)", r is not None and r["Qty"] == nbtn == 8,
         f"expected 8, circuit {nbtn}, BOM {r and r['Qty']}")
# Thonk's low-profile LED button page (2026-11-04): red, green, blue, yellow, orange, white, bipolar R/G
ck.check("button colour is one Thonk sells", bom.BUTTONS["SWLED"] in
         {"red", "green", "blue", "yellow", "orange", "white"}, bom.BUTTONS["SWLED"])
knob_rows = [r for r in rows if r["Part"].startswith("Knob")]
ck.check("knobs: one per pot shaft (25)", sum(r["Qty"] for r in knob_rows) == 25,
         f"expected 25 (README: 25 knobs), got {[(r['Part'], r['Qty']) for r in knob_rows]}")
ck.check("24 small knobs (about 10 mm) and 1 MASTER knob (about 12 mm)",
         any("10 mm" in r["Part"] and r["Qty"] == 24 for r in knob_rows)
         and any("12 mm" in r["Part"] and r["Qty"] == 1 for r in knob_rows),
         f"{[(r['Part'], r['Qty']) for r in knob_rows]}")
pitch = min(abs(a - b) for a, b in zip(circuit.CH_X, circuit.CH_X[1:]))
ck.check("small knob leaves >= 2 mm between knobs at the channel pitch",
         2 * bom.panel.ART["knob"]["small"] + 2.0 <= pitch,
         f"knob {2 * bom.panel.ART['knob']['small']} mm, pitch {pitch} mm")

# against bom/thonk-order.md's Mycelium column
order = open(os.path.join(REPO, "bom", "thonk-order.md"), encoding="utf-8").read().split("\n")
hdr = next(l for l in order if l.startswith("| Qty | Part"))
cols = [c.strip() for c in hdr.strip("|").split("|")]
mi = cols.index("Mycelium")
myc = {}
for l in order:
    if l.startswith("| ") and not l.startswith("| Qty") and not l.startswith("|---"):
        c = [x.strip() for x in l.strip("|").split("|")]
        if c[mi]:
            myc[c[1]] = int(c[mi])
mine = {}
for r in thonk:
    m = re.match(r"(Male pin header, 2\.54 mm|Female header, 2\.54 mm, 8\.5 mm tall): (.*)", r["Part"])
    if m:
        mine[m.group(1) + ", pins (cut to length)"] = sum(int(n) * int(p) for n, p in re.findall(r"(\d+) × 1×(\d+)", m.group(2)))
    else:
        mine[r["Part"]] = mine.get(r["Part"], 0) + r["Qty"]
ck.check("thonk-order.md Mycelium column == this module's Thonk lines", myc == mine,
         f"only in order {sorted(set(myc.items()) - set(mine.items()))}, "
         f"only in BOM {sorted(set(mine.items()) - set(myc.items()))}")
pins = sum(len(nets) for _, _, nets in circuit.HEADERS)
ck.check("header pins: 76 male + 76 female", pins == 76
         and myc.get("Male pin header, 2.54 mm, pins (cut to length)") == pins
         and myc.get("Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)") == pins,
         f"expected 76 each (8 x 8 + 12), circuit {pins}, order says "
         f"{myc.get('Male pin header, 2.54 mm, pins (cut to length)')} / "
         f"{myc.get('Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)')}")

# ------------------------------------------------------------------ 4. part choices: names, packages, footprints
ca = harness.load("copper_audit")
docs = harness.read_export()
fps = ca.footprints_of(docs)
boards = {("Main" if "Main" in t else "Faceplate"): b for t, b in ca.boards_of(docs, fps).items() if "Panel" not in t}
holes, fp_docs = {}, {}        # footprint title -> smallest round hole (mm) / its records
for u, d in docs.items():
    if d["docType"] == "FOOTPRINT":
        title = next(p["title"] for h, p in d["recs"] if h["type"] == "META")
        fp_docs[title] = d
        hs = [p["hole"]["width"] * ca.MIL for h, p in d["recs"]
              if h["type"] == "PAD" and p.get("hole") and p["hole"]["holeType"] == "ROUND"]
        if hs:
            holes[title] = min(hs)


def fp_of(ref, board="Main"):
    return boards[board].parts[ref]["fp"]


def pitch_of(ref, a, b, board="Main"):
    pa, pb = boards[board].parts[ref]["pads"][a], boards[board].parts[ref]["pads"][b]
    return ((pa.x - pb.x) ** 2 + (pa.y - pb.y) ** 2) ** 0.5


def part(ref):
    return next(p for p in mb if p.ref == ref)


def line_of(ref):
    return next(r for r in rows if ref in re.split(r"[ ,;:]+", r["Refs"]))


# Lead sizes (max), for hole >= lead + 0.15 mm (round) / pin diagonal + 0.05 (square header pins)
LEAD = {
    "R": 0.60,        # 1/4 W metal film, Yageo MFR-25 0.54 +- 0.05 (max 0.59); Tayda's 0.6
    "D5819": 0.864,   # DO-41 (DO-204AL) lead, Vishay 1N5817-19 doc 88525: 0.71..0.864
    "D4148": 0.56,    # DO-35 lead, Vishay 1N4148 doc 81857: 0.56 max (conservative)
    "BAT85": 0.56,    # DO-35 lead (Vishay BAT85, DO-204AH): the same 0.56 max
    "C315": 0.56,     # KEMET C315 (Goldmax 300): 0.51 mm (0.020 in) leads, 0.56 with tolerance (ASSUMED)
    "DIP": 0.56,      # PDIP lead width max, TI N package (MS-001): 0.36..0.56 (a turned socket pin ~0.5)
    "CP": 0.5,        # 5 mm radial electrolytic lead, Panasonic / Nichicon: 0.5
}
HDR_DIAG = 0.64 * 2 ** 0.5        # 0.64 mm square header pin: 0.905 mm diagonal


def hole_ok(name, ref, lead, board="Main", extra=0.15):
    h = holes[fp_of(ref, board)]
    ck.check(name, h >= lead + extra, f"{ref} {fp_of(ref, board)}: hole {h:.2f} mm, lead {lead:.2f} + {extra} mm")


for ref in ("U1", "U5", "U7"):
    ck.check(f"{ref} footprint is DIP-14 on the 7.62 mm rows (socket fits)",
             fp_of(ref) == "DIP-14-W7.62-P2.54" and abs(pitch_of(ref, "1", "14") - 7.62) < 0.02
             and abs(pitch_of(ref, "1", "2") - 2.54) < 0.02,
             f"{fp_of(ref)}, rows {pitch_of(ref, '1', '14'):.2f} mm, pitch {pitch_of(ref, '1', '2'):.2f} mm")
    hole_ok(f"{ref} hole takes a DIP socket pin", ref, LEAD["DIP"])
for ref in sorted(circuit.SWITCH.values(), key=lambda r: int(r[1:])):
    ck.check(f"{ref} footprint is DIP-16 on the 7.62 mm rows (CD4053BE = PDIP-16; its socket fits)",
             fp_of(ref) == "DIP-16-W7.62-P2.54" and abs(pitch_of(ref, "1", "16") - 7.62) < 0.02
             and abs(pitch_of(ref, "1", "2") - 2.54) < 0.02 and abs(pitch_of(ref, "1", "8") - 7 * 2.54) < 0.02,
             f"{fp_of(ref)}, rows {pitch_of(ref, '1', '16'):.2f} mm, pitch {pitch_of(ref, '1', '2'):.2f} mm, "
             f"1-8 {pitch_of(ref, '1', '8'):.2f} mm")
hole_ok("U11 hole takes a DIP socket pin", "U11", LEAD["DIP"])
n4053 = sum(1 for p in mb if p.kind == "CD4053")
mux = [r for r in rows if "4053" in r["Part"]]
ck.check(f"CD4053B line: {n4053}, {CD4053_THT}, DIP-16, Tayda",
         n4053 == 8 and len(mux) == 1 and mux[0]["Qty"] == n4053 and CD4053_THT in mux[0]["Part"]
         and "DIP-16" in mux[0]["Part"] and mux[0]["Source"] == "Tayda"
         and sorted(re.split(r",\s*", mux[0]["Refs"])) == sorted(circuit.SWITCH.values()),
         f"circuit {n4053} CD4053B; BOM {[(r['Source'], r['Qty'], r['Part'], r['Refs']) for r in mux]}")
ck.check("no PhotoMOS left in the BOM (2026-11-15)", not any("AQY" in r["Part"] or "PhotoMOS" in r["Part"] for r in rows),
         f"{[r['Part'] for r in rows if 'AQY' in r['Part'] or 'PhotoMOS' in r['Part']]}")
# the switch's supply: VDD = +12V, VEE = VSS = GND (circuit.py), so VDD - VEE is the +12 V rail, at most 12.6 V
sw = part("U11").nets
ck.check(f"CD4053B: VDD - VEE = the {RAIL_WORST} V rail at most, within its {CD4053_SUPPLY_MAX:.0f} V absolute maximum",
         sw["16"] == circuit.VP and sw["7"] == circuit.GND and RAIL_WORST <= CD4053_SUPPLY_MAX,
         f"VDD (16) {sw['16']}, VEE (7) {sw['7']}; {RAIL_WORST} / {CD4053_SUPPLY_MAX} V")
ck.check("D901 / D902 DO-41 footprints and a DO-41 1N5819 line",
         fp_of("D901").startswith("DO-41") and fp_of("D902").startswith("DO-41")
         and "1N5819" in line_of("D901")["Part"] and "DO-41" in line_of("D901")["Part"],
         f"{fp_of('D901')}, {fp_of('D902')}, {line_of('D901')['Part']}")
hole_ok("D901 hole takes a DO-41 lead", "D901", LEAD["D5819"])
ck.check("1N5819 VRRM >= 2 x 12 V", D5819_VRRM >= 2 * RAIL, f"{D5819_VRRM} V")
ck.check("D903 DO-35 footprint for the BAT85, a BAT85 line", fp_of("D903").startswith("DO-35")
         and "BAT85" in line_of("D903")["Part"], f"{fp_of('D903')}, {line_of('D903')['Part']}")
hole_ok("D903 hole takes a DO-35 lead", "D903", LEAD["BAT85"])
ck.check("D904 (the +12 V clamp, a 1N5819 since 2026-11-15) on the DO-41 footprint and the 1N5819 line",
         fp_of("D904").startswith("DO-41") and "1N5819" in line_of("D904")["Part"],
         f"{fp_of('D904')}, {line_of('D904')['Part']}")
hole_ok("D904 hole takes a DO-41 lead", "D904", LEAD["D5819"])
for ref, val in (("C907", "4p7"), ("C908", "4p7"), ("C909", "10p")):
    ck.check(f"{ref} {val}: 2.54 mm C0G footprint and a 2.54 mm C0G line", fp_of(ref) == "CAP-TH_P2.54-L4.0-W2.5"
             and abs(pitch_of(ref, "1", "2") - 2.54) < 0.02 and "C0G" in line_of(ref)["Part"]
             and "2.54 mm" in line_of(ref)["Part"], f"{fp_of(ref)}, {line_of(ref)['Part']}")
    hole_ok(f"{ref} hole takes the C315's lead", ref, LEAD["C315"])


def silk_x(title):
    """x (mil) of the footprint's vertical silk lines inside the pad span: the cathode band."""
    out = []
    for h, p in fp_docs[title]["recs"]:
        path = p.get("path") if h["type"] == "POLY" and p.get("layerId") == 3 else None
        if path and len(path) == 5 and path[2] == "L":          # [x0, y0, "L", x1, y1]
            x0, x1 = path[0], path[3]
            # a band line: vertical, between the pads (the outline's ends sit beyond +-70 mil)
            if abs(x0 - x1) < 0.01 and abs(x0) < 70:
                out.append(x0)
    return out


def pad_x(title, num):
    return next(p["centerX"] for h, p in fp_docs[title]["recs"] if h["type"] == "PAD" and p["num"] == num)


for ref in ("D901", "D903", "D904"):
    band, p1 = silk_x(fp_of(ref)), pad_x(fp_of(ref), "1")
    ck.check(f"{fp_of(ref)[:5]} footprint: cathode band on pad 1", bool(band) and all((x < 0) == (p1 < 0) for x in band),
             f"band x {band} mil, pad 1 x {p1} mil")
ck.check("D901 (+12 V series): anode on the header, cathode (pad 1) towards the load",
         part("D901").nets == {"2": "P12_IN", "1": "P12_D"}, f"{part('D901').nets}")
ck.check("D902 (-12 V series): cathode (pad 1) on the header", part("D902").nets == {"1": "N12_IN", "2": "N12_D"},
         f"{part('D902').nets}")
ck.check("D903: cathode (pad 1) on POR, anode on GND, so it clamps POR and empties C906 at power-off",
         part("D903").nets == {"1": "POR", "2": circuit.GND}, f"{part('D903').nets}")
BAT85_VR = 30.0
ck.check("BAT85 VR >= 2 x the 12 V it blocks (D903 at power-up)", BAT85_VR >= 2 * RAIL, f"{BAT85_VR} V")
ck.check("D904: cathode (pad 1) on +12V, anode on GND: it clamps the +12V net when the bus has no +12 V",
         part("D904").nets == {"1": circuit.VP, "2": circuit.GND}, f"{part('D904').nets}")
plus = [p for h, p in fp_docs[fp_of("C904")]["recs"] if h["type"] == "FILL" and p["layerId"] == 3]
plus_x = sum(p["path"][0] for p in plus) / len(plus) if plus else 0
p2 = pad_x(fp_of("C904"), "2")
ck.check("10 uF footprint: '+' mark beside pad 2", bool(plus) and (plus_x > 0) == (p2 > 0),
         f"'+' x {plus_x} mil, pad 2 x {p2} mil")
for ref, hi in (("C904", circuit.VP), ("C905", circuit.GND)):
    ck.check(f"{ref} '+' (pad 2) on the more positive net", part(ref).nets["2"] == hi,
             f"pad 2 {part(ref).nets['2']}, pad 1 {part(ref).nets['1']}")
cp = line_of("C904")
ck.check("10 uF BOM line is an electrolytic, 2 off, like the polarised footprint",
         "electrolytic" in cp["Part"] and cp["Qty"] == 2, cp["Part"])
# EIA / Panasonic FC / Nichicon UPW radial tables: an aluminium can of 5 mm has 2.0 mm lead spacing; 2.5 mm
# belongs to the 6.3 mm can. The library part behind the footprint (easyeda_export.DEV "C10u") is KNSCHA
# 178MU0033, a dipped TANTALUM bead, 10 uF 35 V, P 2.54 mm (LCSC C18164674, X-On listing, 2026-11-04): the
# footprint CAP-TH_BD4.8-P2.50 is that 4.8 mm bead. So the BOM text either names the tantalum, or, if it asks
# for an aluminium electrolytic, gives the lead spacing that can size really has.
CAN_PITCH = {4.0: 1.5, 5.0: 2.0, 6.3: 2.5, 8.0: 3.5}
cp_pitch = pitch_of("C904", "1", "2")
mcan = re.search(r"([\d.]+) mm across", cp["Part"])
mlead = re.search(r"([\d.]+) mm leads", cp["Part"])
text_ok = "tantalum" in cp["Part"].lower() or (
    mcan is not None and mlead is not None and float(mcan.group(1)) in CAN_PITCH
    and abs(CAN_PITCH[float(mcan.group(1))] - float(mlead.group(1))) < 0.05)
ck.check("10 uF: the BOM's '5 mm across, 2.5 mm leads' is a stock combination",
         text_ok,
         f"BOM text '{cp['Part']}': a {mcan and mcan.group(1)} mm aluminium can comes with "
         f"{mcan and CAN_PITCH.get(float(mcan.group(1)))} mm leads (Panasonic FC / Nichicon UPW); the library part is "
         f"the KNSCHA 178MU0033 dipped tantalum (P 2.54) on a {cp_pitch:.2f} mm footprint")
hole_ok("C904 hole takes the electrolytic's lead", "C904", LEAD["CP"])

r_fps = collections.Counter(fp_of(p.ref) for p in mb if p.kind == "R")
ck.check("every resistor stands on RES-TH-VERTICAL-P2.54", set(r_fps) == {"RES-TH-VERTICAL-P2.54"}, f"{dict(r_fps)}")
ck.check("standing resistor pitch 2.54 mm", abs(pitch_of("R101", "1", "2") - 2.54) < 0.02,
         f"{pitch_of('R101', '1', '2'):.3f} mm")
hole_ok("standing resistor hole takes a 1/4 W lead", "R101", LEAD["R"])
r_lines = [r for r in rows if r["Group"] == "Resistors"]
ck.check("resistor lines: metal film 1 %, 1/4 W (2.5 mm body: stands on 2.54 mm)",
         all("metal film 1 %" in r["Part"] and "1/4 W" in r["Part"] for r in r_lines), f"{len(r_lines)} lines")
# Worst-case +12 V current: design.md's maximum (TL074s at TI SLOS080's ICC max, every channel muted,
# full-swing loads; test_power computes it), against the rating bom.md orders the 10 R filters at. Since 2026-11-15
# the doc's figure is an estimate ("about 115 mA"); the fallback below, used only when the sentence is gone, is
# this group's own rough sum for the CD4053B design: 16 amplifiers at 2.5 mA, every button LED lit through its
# LED resistor from a 12.6 V Q with a 1.6 V LED (the lowest VF the suite assumes), 18 mA of full-swing loads (the
# figure this check used before), the CD4053Bs' microamps left out.
TL074_ICC_MAX = 0.0025   # A per amplifier, max (TI SLOS080)
VF_LED_MIN = 1.6         # V, red button LED, low end (Thonk sheet unavailable; as test_netlist / test_latch)
_mx = re.search(r"about (\d+) mA on \+12 V\s+\(all muted\)", design_text := open(
    os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read())
_led_r = [p for p in mb if p.kind == "R" and len({n for n in p.nets.values() if re.fullmatch(r"(QK|LED)\d", n)}) == 2]
I_EST = 16 * TL074_ICC_MAX + sum((RAIL_WORST - VF_LED_MIN) / harness.ohms(p.value) for p in _led_r) + 0.018
I_MAX = float(_mx.group(1)) / 1000 if _mx else I_EST
r10 = line_of("R918")["Part"]
_w = re.search(r"(\d+(?:\.\d+)?|1/4|1/2) W", r10)
P10 = {"1/4": 0.25, "1/2": 0.5}.get(_w.group(1)) or float(_w.group(1)) if _w else 0.25
ck.check(f"10 R filter resistors stay under half their {P10} W rating at design.md's maximum +12 V current",
         _mx is not None and I_MAX ** 2 * 10 < P10 / 2,
         f"design.md 'about {_mx and _mx.group(1)} mA on +12 V (all muted)' (this group's rough sum {I_EST * 1e3:.0f} mA, "
         f"{len(_led_r)} LED resistors): {I_MAX * 1000:.0f} mA: {I_MAX ** 2 * 10 * 1000:.1f} mW (limit "
         f"{P10 * 500:.0f} mW), drop {I_MAX * 10:.2f} V; BOM: {r10}")
# design.md's BOM build notes give R918's current too; it must be the Power section's maximum
_r918 = re.search(r"R918 carries up to about (\d+) mA", design_text)
ck.check("design.md's build note on R918's current agrees with its Power section's +12 V maximum",
         _mx is not None and _r918 is not None and abs(int(_r918.group(1)) - int(_mx.group(1))) <= 5,
         f"build note 'R918 carries up to about {_r918 and _r918.group(1)} mA', Power 'about "
         f"{_mx and _mx.group(1)} mA on +12 V (all muted)'")
for ref, board in (("H1", "Main"), ("HF1", "Faceplate"), ("H9", "Main")):
    hole_ok(f"{ref} hole takes a 0.64 mm square pin", ref, HDR_DIAG, board, extra=0.05)
ck.check("J18 2x8 box header footprint", fp_of("J18").startswith("IDC-TH_16P"), fp_of("J18"))
dip14 = sum(1 for p in mb if p.kind in ("TL074", "CD4093", "CD4013"))
sock = sum(r["Qty"] for r in rows if re.search(r"DIP-14 (IC )?socket", r["Part"]))
ck.check("DIP-14 sockets in the BOM = DIP-14 chips (10)", sock == dip14 == 10, f"chips {dip14}, socket mentions {sock}")
dip16 = sum(1 for p in mb if p.kind == "CD4053")
sock16 = sum(r["Qty"] for r in rows if re.search(r"DIP-16 (IC )?socket", r["Part"]))
ck.check("DIP-16 sockets in the BOM = CD4053B chips (8)", sock16 == dip16 == 8, f"chips {dip16}, socket mentions {sock16}")
for pins, n in ((14, dip14), (16, dip16)):
    sock_lines = [r for r in rows if re.fullmatch(rf"DIP-{pins} IC socket", r["Part"]) and r["Group"] == "Connectors"]
    where = ", ".join(f"{r['Source']} {r['Qty']} ({r['Part']})" for r in rows if f"DIP-{pins}" in r["Part"]
                      and "socket" in r["Part"].lower())
    ck.check(f"DIP-{pins} sockets as a line of their own (one count to buy)", len(sock_lines) == 1
             and sock_lines[0]["Qty"] == n, f"expected one 'DIP-{pins} IC socket' x {n} line; got {where}")

# ------------------------------------------------------------------ 5. ratings and types
for r in (r for r in rows if r["Group"] == "Capacitors"):
    m = re.search(r"(\d+)\s*V\b", r["Part"])
    ck.check(f"capacitor line states its voltage: {r['Part'][:38]}",
             m is not None and int(m.group(1)) >= CAP_MARGIN * RAIL_WORST,
             f"expected '>= {CAP_MARGIN * RAIL_WORST:.0f} V' in the part text, got {m.group(0) if m else 'no voltage'}")
ck.check("22 pF are C0G", "C0G" in line_of("C901")["Part"], line_of("C901")["Part"])
ck.check("100 nF are X7R", "X7R" in line_of("C911")["Part"], line_of("C911")["Part"])
ck.check("C906 1 uF: a non-polar ceramic, as circuit.py's plain C and the 7.6 x 3.8 footprint have it",
         part("C906").kind == "C" and "ceramic" in line_of("C906")["Part"] and "L7.6-W3.8" in fp_of("C906"),
         f"kind {part('C906').kind}, BOM {line_of('C906')['Part']}, footprint {fp_of('C906')}")
LIB_V = {"100n (TDK FG28X7R1H104KNT00)": 50, "22p (TDK FG28C0G1H220JNT00)": 50,
         "1u (AVX SR305C105KAR)": 50, "10u (178MU0033)": 35}
for v, rated in LIB_V.items():
    ck.check(f"{v} rated >= {CAP_MARGIN} x 12.6 V", rated >= CAP_MARGIN * RAIL_WORST, f"{rated} V")
ck.check("CMOS VDD 12.6 V within CD40xxB's 18 V", RAIL_WORST <= CMOS_VDD_MAX, f"{RAIL_WORST} / {CMOS_VDD_MAX} V")
ck.check("TL074 on +-12.6 V within +-18 V", RAIL_WORST <= TL074_VCC_MAX, f"{RAIL_WORST} / {TL074_VCC_MAX} V")
ck.check("chip names: CD4093BE / CD4013BE / CD4053BE (PDIP 'E'), TL074 DIP-14",
         "CD4093BE" in line_of("U5")["Part"] and "CD4013BE" in line_of("U7")["Part"]
         and CD4053_THT in line_of("U11")["Part"]
         and "TL074" in line_of("U1")["Part"] and "DIP-14" in line_of("U1")["Part"],
         f"{line_of('U5')['Part']} / {line_of('U7')['Part']} / {line_of('U11')['Part']} / {line_of('U1')['Part']}")

# ------------------------------------------------------------------ 6. mechanics
so = next((r for r in rows if "standoff" in r["Part"].lower()), None)
m = re.search(r"female-female, (?:about )?([\d.]+) mm", so["Part"]) if so else None
length = float(m.group(1)) if m else None
ck.check("standoff count = mounting holes (4)", so is not None and so["Qty"] == len(circuit.HOLES_FRONT) == 4,
         f"BOM {so and so['Qty']}, holes {len(circuit.HOLES_FRONT)}")
ck.check("standoff length = mated 8.5 mm female socket + 2.5 mm male header plastic",
         length is not None and abs(length - MATED_GAP) <= 0.5,
         f"expected {MATED_GAP:.1f} mm (design.md: 'about 11 mm'), BOM says {length} mm")
design = open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
m2 = re.search(r"about ([\d.]+) mm with standard\s+sockets", design)
ck.check("design.md and the BOM give the same standoff length", m2 is not None and length == float(m2.group(1)),
         f"design.md {m2 and m2.group(1)} mm, BOM {length} mm")
# Qty 4 of 'standoff + 2 M3 screws' reads as 8 screws; what is missing is the screw length (and a low head:
# on the faceplate the head sits between the board and the panel).
screw = next((r for r in rows if "screw" in r["Part"].lower() and "standoff" not in r["Part"].lower()), None)
screw_text = " ".join(r["Part"] + " " + r["Note"] for r in (so, screw) if r)
ck.check("screws: the BOM gives the M3 screw length",
         re.search(r"M3 ?[×x] ?\d+(\.\d+)? ?mm", screw_text) is not None,
         f"expected 'M3 x <length> mm' (M3 x 6 for 1.6 mm boards on female-female standoffs); BOM: '{screw_text}'")
ck.check("screws: two per standoff", screw is not None and so is not None and screw["Qty"] >= 2 * so["Qty"],
         f"screws {screw and screw['Qty']}, standoffs {so and so['Qty']}")
cable = [r for r in rows if "power cable" in r["Part"].lower()]
j18 = part("J18")
ck.check("power cable: one, 16-pin at the module end for the 16-pin J18",
         len(cable) == 1 and cable[0]["Qty"] == 1 and "16-pin" in cable[0]["Part"] and j18.kind == "HDR16",
         f"{[(r['Qty'], r['Part']) for r in cable]}, J18 {j18.kind}")
ck.check("J18 leaves pins 11-16 (+5 V, CV, Gate) open: the module uses only the 10-pin part of the bus",
         not any(n in j18.nets for n in ("11", "12", "13", "14", "15", "16")), f"J18 pins {sorted(j18.nets, key=int)}")
pcbs = [r for r in rows if r["Group"] == "PCBs"]
ck.check("PCB lines count 3 designs to order (main, faceplate, panel)",
         sum(r["Qty"] for r in pcbs) == 3, f"expected qty 3, got {[(r['Qty'], r['Part'][:44]) for r in pcbs]}")
(w, h), _ = bom.routed()["Main"]
(wf, hf), _ = bom.routed()["Faceplate"]
ck.check("main and faceplate boards the same size as circuit.py's", (round(w, 1), round(h, 1)) ==
         (round(wf, 1), round(hf, 1)) == (circuit.BOARD_W, circuit.BOARD_H),
         f"main {w:.1f} x {h:.1f}, faceplate {wf:.1f} x {hf:.1f}")
ck.check("panel line = 28HP (28 x 5.08 - 0.3) x 128.5", abs(bom.panel.PANEL_W - (28 * 5.08 - 0.3)) < 0.05
         and bom.panel.PANEL_H == 128.5, f"{bom.panel.PANEL_W} x {bom.panel.PANEL_H}")

# ------------------------------------------------------------------ 7. the docs' counts
readme = open(os.path.join(harness.MODULE, "README.md"), encoding="utf-8").read()
m = re.search(r"(\d+) knobs \((\d+) dual-gang\), (\d+) LED buttons, (\d+) jacks", readme)
ck.check("README panel counts match the BOM", m is not None and tuple(map(int, m.groups())) ==
         (sum(r["Qty"] for r in knob_rows), sum(duals.values()), nbtn, njacks), f"README {m and m.groups()}")
m = re.search(r"main board (\d+) parts, faceplate (\d+)", readme)
ck.check("README part counts", m is not None and (int(m.group(1)), int(m.group(2))) == (len(mb), len(fb)),
         f"README {m and m.groups()}, circuit {len(mb)} / {len(fb)}")
ck.done()
