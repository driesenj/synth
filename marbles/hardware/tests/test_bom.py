"""BOM group: Marblesy's (Spore's) bill of materials.

What it checks
  A  bom.py's in-memory build (its working copy, as it is now) against circuit.py: bom.check() clean,
     every netlist part of both boards owned by exactly one line, quantities per part kind and value,
     the per-board split (R80-R85 exist on both boards with different values), and the routed master's
     designators and placed devices per board (read with harness.routed(), independently of bom.py).
  B  The committed docs/bom.md, hardware/bom/marbles-bom.csv and -thonk.csv against a fresh bom.write()
     (pointed at a temporary folder: nothing in the repo is written).
  C  The repo-wide bom/thonk-order.md / .csv and bom/parts-order.md / .csv: this module's (Spore's)
     column against its own BOM lines.
  D  Part numbers and ratings against the datasheets (constants below): MCP4922-E/P, LM4040CIZ-2.5 and
     its grades, the SOT-23 fallback note's wiring, 2N3904, BAT85 and every listed alternative (package,
     VR, lead diameter against the footprint's 0.8 mm hole), TL074, the 74HC parts and the CD4051B at
     3.3 V, ceramic voltages and dielectrics, the E-series of every resistor value, worst-case resistor
     dissipation at 1/4 W (outputs shorted or patched to a rail), the gate LEDs' reverse voltage.
  E  Thonk and mechanical parts: jacks, pots (and Thonk's stock), LED buttons, LEDs, knobs, headers
     against circuit.HEADERS, DIP sockets on lines of their own, the breakout's socket strips against
     the routed U2 footprint, standoffs (mated header height) and screws, the power cable for the
     breakout's 10-pin J2, one line per PCB.

Run from marbles/hardware/tests:  python test_bom.py
Read only: imports bom.py / circuit.py, calls bom.build() and bom.write() into a temporary folder.
"""
import collections
import csv
import io
import math
import os
import re
import shutil
import sys
import tempfile

import harness

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ck = harness.Checks("bom")
circuit = harness.load("circuit")
bom = harness.load("bom")
R = harness.routed()

# ======================================================================== constants (datasheets etc.)
RAIL_MAX = 12.6          # V, a +5 % Eurorack rail (assumption; no standard tolerance)
CAP_MARGIN = 1.5         # ceramic / electrolytic rated >= 1.5 x the DC across it
# Microchip MCP4922 DS21897B: product identification "MCP4922-E/P": E = -40..+125 C, P = plastic DIP 300 mil
# (8 / 14 lead; the MCP4922 is the 14-lead part); VDD 2.7..5.5 V; VREF (buffered) 0.040 .. VDD - 0.040 V.
MCP_SUFFIX = {"E": "-40..125 C", "P": "PDIP 300 mil"}
MCP_VDD = (2.7, 5.5)
MCP_VREF_HEADROOM = 0.040
# TI LM4040-N SNOS633N (Aug 2025): tolerance grades A 0.1 %, B 0.2 %, C 0.5 %, D 1 %, E 2 % (25 C); I = -40..85 C;
# Z = TO-92 (LP); M3 = SOT-23 (DBZ). 2.5 V C grade: IRMIN 45 typ, 60 max (25 C), 65 max (over temperature) uA.
# Pin functions: SOT-23 1 = cathode, 2 = anode, 3 = "must float or connect to anode"; TO-92 (bottom view drawing):
# 1 = NC (*), 2 = cathode, 3 = anode (repo memory: an older TI table gives the anode on 1).
LM4040_GRADE = {"A": 0.1, "B": 0.2, "C": 0.5, "D": 1.0, "E": 2.0}
LM4040_IRMIN_C = 65e-6
LM4040_SOT23 = {"1": "K", "2": "A", "3": "float or anode"}
LM4040_TO92 = {"2": "K", "anode": ("1", "3")}
# onsemi 2N3904: TO-92 pin 1 emitter, 2 base, 3 collector; VCEO 40 V, IC 200 mA.
Q_PINS = {"1": "E", "2": "B", "3": "C"}
Q_VCEO = 40.0
# Schottky clamp alternatives: package and VR (V), with the source:
#   BAT85  Vishay doc 88146 / 85513: VR 30 V, DO-35 (DO-204AH) glass (Nexperia's BAT85 is SOD68 / DO-34)
#   BAT86  Vishay BAT86S doc 85514: VR 50 V, DO-35
#   BAT42, BAT43  Vishay doc 85660: VRRM 30 V, DO-35
#   SD101  Vishay doc 85629 (sd101abc): SD101A 60 V, B 50 V, C 40 V, DO-35 (search result; the PDF did not download)
#   SD103A Vishay SD103A/B/C: 40 V, DO-35 (search result)
#   BAT46  ST / Vishay: 100 V, DO-35 (not confirmed this session: the PDFs did not download)
#   1N5711 ST / Vishay: 70 V, DO-35 (not confirmed this session: st.com timed out)
SCHOTTKY = {"BAT85": (30, "DO-35"), "BAT86": (50, "DO-35"), "BAT43": (30, "DO-35"), "BAT42": (30, "DO-35"),
            "BAT46": (100, "DO-35"), "SD103A": (40, "DO-35"), "1N5711": (70, "DO-35"), "SD101": (40, "DO-35")}
# Lead diameter, max: Vishay DO-35 outline (doc 85513, "SB-V-3906.04-031"): 0.6 mm (JEDEC DO-204AH 0.46..0.56);
# DO-41 (DO-204AL, Vishay 88525): 0.864 mm. Hole >= lead + 0.15 mm for a solderable fit.
LEAD = {"DO-35": 0.60, "DO-41": 0.864}
HOLE_MARGIN = 0.15
# TI TL07x SLOS080W: supplies up to +-18 V (abs max); ISC +-26 mA typ (new die; the old die's tables give none).
# (verifier: SLOS080W 5.7 "Electrical Characteristics for TL07xH", 25 C: ISC +-26 mA, typical only (no max); abs max
# "Output short-circuit: Continuous", note 4 "Short-circuit to ground, one amplifier per package".)
TL_VS_MAX, TL_ISC = 18.0, 26e-3
# TI SN74HC595 SCLS041J / SN74HC165 SCLS116H / CD74HC4051 SCHS122O: VCC 2..6 V recommended. fclock (SN74,
# -40..85 C) 595: 5 MHz at 2 V, 25 MHz at 4.5 V; 165: 5 MHz at 2 V, 25 MHz at 4.5 V. At 3.3 V: interpolated
# linearly between the two (the 2 V figure as the conservative bound is printed too).
HC_VCC = (2.0, 6.0)
HC_FCLK = {"HC595": (5e6, 25e6), "HC165": (5e6, 25e6)}
SPI_HZ = 6.25e6          # design.md / firmware: SPI1 at 6.25 MHz
# TI CD4051B SCHS047O (May 2026): single supply 3..20 V ("performance degrades for VDD < 3 V"); pin compatible with
# the 4051 (6 INH, 7 VEE, 8 VSS); rON (0 <= VIS <= VDD) 470 typ / 1050 max at VDD 5 V, 180 / 400 at 10 V (25 C);
# nothing at 3.3 V.
CD4051_VDD = (3.0, 20.0)
CD4051_RON = {5.0: 1050.0, 10.0: 400.0}
# Capacitor devices in the routed master: TDK FG28 '1H' = 50 V (FG28X7R1H104KNT00 100 nF X7R, FG28C0G1H102JNT00
# 1 nF C0G); KYOCERA AVX SkyCap SR305C105KAR: '5' = 50 V, X7R ('C'), 1 uF.
CAP_DEV = {"FG28X7R1H104KNT00": (100e-9, "X7R", 50), "FG28C0G1H102JNT00": (1e-9, "C0G", 50),
           "SR305C105KAR": (1e-6, "X7R", 50)}
# E-series (IEC 60063): E24 and E96 mantissas.
E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5,
       8.2, 9.1]
# E96: 10^(i/96) rounded to 3 figures; the IEC table differs from the rounding at a few steps (fixed here)
E96_FIX = {2.62: 2.61, 2.88: 2.87, 3.33: 3.32, 3.84: 3.83, 4.24: 4.22, 4.65: 4.64, 9.20: 9.20}
E96 = sorted({E96_FIX.get(round(10 ** (i / 96), 2), round(10 ** (i / 96), 2)) for i in range(96)})
RES_P = 0.25             # W, the BOM's 1/4 W (Yageo MFR-25 class, at 70 C)
LED_VR_MAX = 5.0         # V, a standard 3 mm LED's reverse voltage, abs max (Kingbright WP710A10ID "Reverse Voltage VR
#                          5 V", read 2026-11-13 by the verifier; no datasheet for Thonk's LEDs: assumed the same)
LED_VF_MIN = 1.65
# Thonk stock (repo memory "Thonk Alpha pot values", 2026-10-31; Thonk blocks fetches, not re-confirmable):
THONK_T18_VERTICAL = {"B5K", "B10K", "B25K", "B50K", "B100K", "B250K", "B1M", "A50K", "A100K", "A1M"}
# Thonk low-profile LED button colours (the stereo mixer suite's fetch of Thonk's page, 2026-11-04):
THONK_BUTTON_COLOURS = {"red", "green", "blue", "yellow", "orange", "white", "bipolar red/green"}
# Standard 2.54 mm headers: female socket body 8.5 mm (the BOM's part), male header plastic 2.5 mm: the boards sit
# 8.5 + 2.5 = 11 mm apart when fully mated (Samtec / Harwin / generic strips).
FEMALE_BODY, MALE_PLASTIC = 8.5, 2.5
# The breakout's power header: BOM_seed_power_opamps_2025-08-29.csv, J2 "HDR-M-2.54_2x5" (LCSC C178292, Amphenol
# 67997-210HLF, an unshrouded 2x5 male header): a 10-pin Eurorack connector.
BREAKOUT_J2_PINS = 10

DOC = harness.text("docs", "design.md")
MB, FB = circuit.main_board_parts(), circuit.faceplate_parts()
MBd, FBd = {p.ref: p for p in MB}, {p.ref: p for p in FB}


def thonk_rows(rows):
    return [r for r in rows if r["Source"] == "Thonk"]


# ======================================================================== A. in-memory build
print("--- A. bom.py against circuit.py and the routed master")
lines, owned = bom.build()
problems = bom.check(owned)
ck.check("A.bom_check", not problems, f"expected 0 problems, got {len(problems)}: {problems[:4]}")
# lines that buy something for a part without being that part: its socket, the breakout and its socket strips (U2)
ACCESSORY = ("IC socket", "seed_power_opamps breakout", "for the breakout's two rows")
part_lines = {k: line for k, line in lines.items() if not any(a in k[2] for a in ACCESSORY)}
for board, parts in (("Main", MB), ("Faceplate", FB)):
    for p in parts:
        n = sum(1 for line in part_lines.values() if (board, p.ref) in line["refs"])
        if n != 1:
            ck.check(f"A.one_line.{board}.{p.ref}", False, f"expected 1 line, got {n}")
ck.check("A.every_part_on_one_line", all(sum(1 for line in part_lines.values() if (b, p.ref) in line["refs"]) == 1
                                         for b, ps in (("Main", MB), ("Faceplate", FB)) for p in ps),
         f"{len(MB)} main + {len(FB)} faceplate parts")
# quantities per kind and value, counted from circuit.py independently of describe()
kinds = collections.Counter()
for board, parts in (("Main", MB), ("Faceplate", FB)):
    for p in parts:
        if p.kind in ("R", "C"):
            kinds[(p.kind, harness.ohms(p.value) if p.kind == "R" else harness.farads(p.value))] += 1
for (k, v), n in sorted(kinds.items()):
    if k == "R":
        txt = bom.ohms(next(p.value for p in MB + FB if p.kind == "R" and harness.ohms(p.value) == v))
        key = next((key for key in lines if key[1] == "Resistors" and f"Resistor {txt}," in key[2]), None)
    else:
        key = next((key for key in lines if key[1] == "Capacitors" and lines[key]["size"] and
                    abs(lines[key]["size"] - v) < v * 1e-6), None)
    got = lines[key]["qty"] if key else 0
    ck.check(f"A.qty.{k}{v:g}", got == n, f"circuit.py has {n}, BOM line {key[2][:40] if key else None!r} has {got}")
for key, line in lines.items():
    if line["refs"] and key[1] not in ("Connectors",):
        ck.check(f"A.qty_equals_refs.{key[2][:40]}", line["qty"] == len(set(line["refs"])),
                 f"qty {line['qty']}, refs {len(set(line['refs']))}")
# the per-board split: R80-R85 on both boards with their own values
both = sorted({p.ref for p in MB} & {p.ref for p in FB}, key=bom.natural)
ck.check("A.shared_refs", both == ["R80", "R81", "R82", "R83", "R84", "R85"],
         f"refs on both boards: {both} (design.md / bom.md: R80-R85)")
for ref in both:
    for board, parts in (("Main", MBd), ("Faceplate", FBd)):
        want = f"Resistor {bom.ohms(parts[ref].value)},"
        key = next((k for k, line in lines.items() if (board, ref) in line["refs"]), None)
        ck.check(f"A.split.{board}.{ref}", key is not None and want in key[2],
                 f"{board} {ref} = {parts[ref].value}: on {key[2][:40] if key else None!r}")
# the routed master's designators and placed values, per board (harness's parser, not bom.routed())
for bk, board, parts in (("main", "Main", MB), ("face", "Faceplate", FB)):
    routed_refs = set(R.board(bk).parts)
    mine = {p.ref for p in parts}
    ck.check(f"A.routed_refs.{board}", routed_refs == mine,
             f"only routed {sorted(routed_refs - mine, key=bom.natural)}, only circuit.py "
             f"{sorted(mine - routed_refs, key=bom.natural)}")
    for p in parts:
        if p.kind not in ("R", "C") or p.ref not in routed_refs:
            continue
        mpn = R.device(bk, p.ref).get("Manufacturer Part") or ""
        if p.kind == "R":
            m = re.fullmatch(r"LR1F(\d+)([RKM])(\d*)", mpn)
            placed = float(f"{m.group(1)}.{m.group(3) or 0}") * {"R": 1, "K": 1e3, "M": 1e6}[m.group(2)] if m else None
            key = next(k for k, line in lines.items() if (board, p.ref) in line["refs"])
            mt = re.search(r"Resistor ([\d.]+) ?(Ω|k|M)", key[2])
            bom_v = float(mt.group(1)) * {"Ω": 1, "k": 1e3, "M": 1e6}[mt.group(2)]
            ck.check(f"A.placed_value.{board}.{p.ref}", placed is not None and abs(placed - bom_v) < 1e-6 * bom_v,
                     f"routed device {mpn}, BOM line {key[2][:30]}")
        else:
            placed = CAP_DEV.get(mpn, (None,))[0]
            ck.check(f"A.placed_value.{board}.{p.ref}", placed is not None and
                     abs(placed - harness.farads(p.value)) < 1e-15,
                     f"routed device {mpn} ({placed}), circuit.py {p.value}")

# ======================================================================== B. the committed files
print("--- B. committed BOM files against a fresh bom.write()")
tmp = tempfile.mkdtemp(prefix="marbles_bom_test_")
os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
_root = bom.ROOT
bom.ROOT = tmp                          # write() puts docs/bom.md and hardware/bom/*.csv under ROOT
try:
    rows = bom.write(lines)
    fresh = {}
    for rel in ("docs/bom.md", "hardware/bom/marbles-bom.csv", "hardware/bom/marbles-bom-thonk.csv"):
        fresh[rel] = open(os.path.join(tmp, rel), encoding="utf-8", newline="").read().replace("\r\n", "\n")
finally:
    bom.ROOT = _root
    shutil.rmtree(tmp, ignore_errors=True)
for rel, text in fresh.items():
    committed = open(os.path.join(harness.MODULE, rel), encoding="utf-8", newline="").read().replace("\r\n", "\n")
    diff = ""
    if text != committed:
        a, b = text.split("\n"), committed.split("\n")
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        diff = f"first difference at line {i + 1}: fresh {a[i] if i < len(a) else None!r} / committed " \
               f"{b[i] if i < len(b) else None!r}"
    ck.check(f"B.committed.{rel}", text == committed, diff or f"{len(text)} chars identical")
by_part = {r["Part"]: r for r in rows}
thonk = thonk_rows(rows)


def line_of(ref, board=None):
    for r in rows:
        refs = re.split(r"[ ,;:]+", r["Refs"])
        if ref in refs and (board is None or board in r["Board"] or f"{board}:" in r["Refs"]):
            if board and ";" in r["Refs"]:
                seg = next(s for s in r["Refs"].split(";") if s.strip().startswith(board))
                if ref not in re.split(r"[ ,:]+", seg):
                    continue
            if r["Group"] == "Connectors" and r["Part"].endswith("IC socket"):
                continue
            return r
    return None


# ======================================================================== C. the repo-wide orders
print("--- C. bom/thonk-order and bom/parts-order: the Spore column")
COL = "Spore"


def md_table(path, first):
    text = open(os.path.join(harness.REPO, "bom", path), encoding="utf-8").read().split("\n")
    out = []
    hdr = None
    for l in text:
        if l.startswith("| " + first):
            hdr = [c.strip() for c in l.strip().strip("|").split("|")]
            continue
        if hdr and l.startswith("| ") and not l.startswith("|---"):
            out.append(dict(zip(hdr, [c.strip() for c in l.strip().strip("|").split("|")])))
        elif hdr and not l.startswith("|"):
            hdr = None
    return out


def mine_thonk():
    out = {}
    for r in thonk:
        m = re.match(r"(Male pin header, 2\.54 mm|Female header, 2\.54 mm, 8\.5 mm tall): (.*)", r["Part"])
        if m:
            out[m.group(1) + ", pins (cut to length)"] = sum(int(n) * int(p) for n, p in
                                                           re.findall(r"(\d+) × 1×(\d+)", m.group(2)))
        else:
            out[r["Part"]] = out.get(r["Part"], 0) + int(r["Qty"])
    return out


want_thonk = mine_thonk()
got_md = {r["Part"]: int(r[COL]) for r in md_table("thonk-order.md", "Qty") if r.get(COL)}
got_csv = {r["Part"]: int(r[COL]) for r in csv.DictReader(open(os.path.join(harness.REPO, "bom", "thonk-order.csv"),
                                                              encoding="utf-8")) if r.get(COL)}
for name, got in (("thonk-order.md", got_md), ("thonk-order.csv", got_csv)):
    ck.check(f"C.{name}", got == want_thonk,
             f"only in the order {sorted(set(got.items()) - set(want_thonk.items()))}, only in Spore's BOM "
             f"{sorted(set(want_thonk.items()) - set(got.items()))}")
pins = sum(len(nets) for _, _, nets in circuit.HEADERS)
ck.check("C.header_pins_in_order", got_md.get("Male pin header, 2.54 mm, pins (cut to length)") == pins ==
         got_md.get("Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)"),
         f"circuit.HEADERS has {pins} pins per side; the order {got_md.get('Male pin header, 2.54 mm, pins (cut to length)')}"
         f" male / {got_md.get('Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)')} female")
want_parts = collections.Counter()
for r in rows:
    if r["Source"] != "Thonk":
        want_parts[r["Part"]] += int(r["Qty"])
got_pmd = collections.Counter()
for t in ("Qty",):
    for r in md_table("parts-order.md", t):
        if r.get(COL):
            got_pmd[r["Part"]] += int(r[COL])
got_pcsv = collections.Counter({r["Part"]: int(r[COL]) for r in csv.DictReader(
    open(os.path.join(harness.REPO, "bom", "parts-order.csv"), encoding="utf-8")) if r.get(COL)})
for name, got in (("parts-order.md", got_pmd), ("parts-order.csv", got_pcsv)):
    ck.check(f"C.{name}", got == want_parts,
             f"only in the order {sorted(set(got.items()) - set(want_parts.items()))}, only in Spore's BOM "
             f"{sorted(set(want_parts.items()) - set(got.items()))}")

# ======================================================================== D. part numbers and ratings
print("--- D. part numbers and ratings")
fp = {("Main", r): p for r, p in R.main.parts.items()}
fp.update({("Faceplate", r): p for r, p in R.face.parts.items()})


def hole(board, ref, num="1"):
    # harness fix: the part's own footprint copy (by uuid); fp_docs[title] can return another copy of that title
    for h, p in R.fp_doc({"Main": "main", "Faceplate": "face"}[board], ref)["recs"]:
        if h["type"] == "PAD" and p and str(p["num"]) == num:
            return p["hole"]["width"] * harness.MIL
    return None


dac = line_of("U7")["Part"]
m = re.search(r"MCP4922-([A-Z])/([A-Z]+)", dac)
ck.check("D.MCP4922_part_number", m is not None and m.group(1) in MCP_SUFFIX and m.group(2) in MCP_SUFFIX
         and "DIP-14" in dac, f"'{dac}': -{m.group(1) if m else '?'} = {MCP_SUFFIX.get(m.group(1)) if m else '?'}, "
                              f"/{m.group(2) if m else '?'} = {MCP_SUFFIX.get(m.group(2)) if m else '?'} (14-lead)")
ck.check("D.MCP4922_footprint", fp[("Main", "U7")]["fp"].startswith("DIP-14") and fp[("Main", "U8")]["fp"].startswith("DIP-14"),
         f"{fp[('Main', 'U7')]['fp']}")
# verifier change: this compared constants only (3.3 and 2.5 written in); it now reads the DACs' VDD / VREF nets
# from circuit.py (pin numbers DS21897B: VDD 1, VREFB 11, VREFA 13) and the reference behind VREF (D21's cathode).
dac_nets = [(MBd[u].nets.get("1"), MBd[u].nets.get("11"), MBd[u].nets.get("13")) for u in ("U7", "U8")]
vref_src = MBd["D21"].value if MBd["D21"].nets.get("2") == "VREF" else None
m_ref = re.search(r"-(\d+\.\d+)$", vref_src or "")
v_ref = float(m_ref.group(1)) if m_ref else 99.0
ck.check("D.MCP4922_VDD_and_VREF", all(n == ("3V3A", "VREF", "VREF") for n in dac_nets) and vref_src is not None
         and MCP_VDD[0] <= 3.3 * 0.97 and 3.3 * 1.03 <= MCP_VDD[1] and v_ref <= 3.3 * 0.97 - MCP_VREF_HEADROOM,
         f"U7 / U8 (VDD, VREFB, VREFA) {dac_nets}; VREF from D21 ({vref_src}, {v_ref} V); 3V3A +-3 % in {MCP_VDD} V; "
         f"VREF <= VDD - 0.04 at 3V3A -3 %")
ref_line = line_of("D21")["Part"]
m = re.search(r"LM4040([A-E])([IE])Z-2\.5", ref_line)
grade = m.group(1) if m else None
ck.check("D.LM4040_part_number", m is not None and m.group(2) == "I" and "TO-92" in ref_line,
         f"'{ref_line[:60]}': grade {grade} ({LM4040_GRADE.get(grade)} %), I = -40..85 C, Z = TO-92")
md = re.search(r"([\d.]+) % on the reference", DOC)
ck.check("D.LM4040_grade_vs_design", grade is not None and md is not None and LM4040_GRADE[grade] <= float(md.group(1)),
         f"design.md's tolerance analysis assumes {md.group(1) if md else '?'} %; the C grade is {LM4040_GRADE.get(grade)} %")
ck.check("D.LM4040_BIZ_AIZ_note", "BIZ" in ref_line and LM4040_GRADE["B"] < LM4040_GRADE["C"]
         and LM4040_GRADE["A"] < LM4040_GRADE["B"],
         "the B grade (0.2 %) is tighter than the C (0.5 %), so 'BIZ works'; the A (0.1 %) is the tightest")
i_left = (3.3 - 2.5) / harness.ohms(MBd["R47"].value) - 2.5 / harness.ohms(MBd["R42"].value)
ck.within("D.LM4040_current_vs_IRMIN", i_left, LM4040_IRMIN_C, None, " A",
          "R47's current less the inverter's (R42), against the C grade's 65 uA over temperature")
d21 = MBd["D21"].nets
ck.check("D.LM4040_TO92_wiring", d21.get(next(k for k, v in LM4040_TO92.items() if v == "K")) == "VREF"
         and all(d21.get(a) == "GND" for a in LM4040_TO92["anode"]),
         f"TO-92 cathode pin 2 on VREF, pins 1 and 3 (anode in either TI drawing) on GND; circuit {d21}")
notes = " ".join(bom.NOTES)
mn = re.search(r"SOT-23 one \((LM4040[A-Z0-9.-]+)/NOPB[^)]*\) fits D21 on two short wire legs: its pin 1 \(cathode\) into "
               r"the middle hole, pin 2 \(anode\) into either outer hole, pin 3 left free", notes)
ck.check("D.LM4040_SOT23_note", mn is not None and LM4040_SOT23["1"] == "K" and LM4040_SOT23["2"] == "A"
         and "float" in LM4040_SOT23["3"] and d21.get("2") == "VREF" and d21.get("1") == d21.get("3") == "GND"
         and re.fullmatch(r"LM4040[A-E]IM3-2\.5", mn.group(1) if mn else "") is not None,
         f"note: {mn.group(1) if mn else 'not found'}: SOT-23 pin 1 = cathode -> middle pad 2 ({d21.get('2')}), pin 2 = "
         f"anode -> pad 1 or 3 (GND), pin 3 must float or go to the anode: free is allowed")
ck.check("D.LM4040_SOT23_pin_sides", re.search(r"Pins 1 and 2 are the two leads on one side, pin 1 on the left with the "
                                               r"marking upright", notes) is not None,
         "SOT-23 (JEDEC TO-236, TI DBZ drawing): pins 1 and 2 on one side, 3 alone; top view with the leads 1-2 at the "
         "bottom: pin 1 left")
q = MBd["Q1"].nets
ck.check("D.2N3904_pinout", all(q.get(k) and {"E": "GND", "B": "B_T_CLK", "C": "T_CLK"}[v] == q[k] for k, v in Q_PINS.items())
         and "2N3904" in line_of("Q1")["Part"] and "TO-92" in line_of("Q1")["Part"],
         f"onsemi TO-92 E B C; circuit Q1 {q}")
# verifier change: this compared two constants (40 V >= 3.4 V); it now finds each collector's pull-up in circuit.py
pulls = {}
c_pin = next(k for k, v in Q_PINS.items() if v == "C")
for qn in ("Q1", "Q2"):
    col = MBd[qn].nets.get(c_pin)
    sup = [next(v for v in p.nets.values() if v != col) for p in MB if p.kind == "R" and col in p.nets.values()]
    pulls[qn] = (col, sup)
v_col = max((3.3 * 1.03 if s.startswith("3V3") else RAIL_MAX) for c, ss in pulls.values() for s in ss) if all(
    ss for c, ss in pulls.values()) else 99.0
ck.check("D.2N3904_VCEO", Q_VCEO >= v_col, f"collectors and their pull-ups {pulls}: at most {v_col:.2f} V; VCEO {Q_VCEO} V")
# Schottky clamps
bat = line_of("D22")["Part"]
listed = re.findall(r"\b(BAT\d+|SD10\d[A-C]?|1N5711)\b", bat)
ck.check("D.Schottky_list_known", set(listed) <= set(SCHOTTKY) and len(listed) == 8,
         f"BOM lists {listed}; data for {sorted(SCHOTTKY)}")
h = hole("Main", "D22")
mhole = re.search(r"holes are ([\d.]+) mm", bat)
ck.check("D.DO35_hole_as_noted", mhole is not None and abs(float(mhole.group(1)) - h) < 0.01,
         f"BOM says {mhole.group(1) if mhole else '?'} mm; footprint {fp[('Main', 'D22')]['fp']} hole {h:.2f} mm")
for part in listed:
    vr, pkg = SCHOTTKY[part]
    vr_need = 12.0       # conservative: the input's full swing (the base-emitter junction holds it to ~0.8 V)
    ck.check(f"D.Schottky.{part}", vr >= vr_need and pkg == "DO-35" and LEAD[pkg] + HOLE_MARGIN <= h + 1e-6,
             f"{pkg}, VR {vr} V (>= {vr_need}); lead {LEAD[pkg]} mm + {HOLE_MARGIN} <= hole {h:.2f} mm")
ck.check("D.DO41_does_not_fit", LEAD["DO-41"] + HOLE_MARGIN > h and "DO-35 only" in bat,
         f"a DO-41 lead ({LEAD['DO-41']} mm) needs {LEAD['DO-41'] + HOLE_MARGIN:.2f} mm: 'DO-35 only' is right")
d22 = MBd["D22"].nets
ck.check("D.BAT85_orientation", d22 == {"1": "B_T_CLK", "2": "GND"},
         f"cathode (pin 1) on the base, anode on GND: clamps negative swings; circuit {d22}")
# TL074 and logic at their supplies
ck.check("D.TL074_part", "TL074" in line_of("U3")["Part"] and "DIP-14" in line_of("U3")["Part"]
         and RAIL_MAX <= TL_VS_MAX, f"{line_of('U3')['Part']}; +-{RAIL_MAX} V within +-{TL_VS_MAX} V")
for kind, ref in (("HC595", "U9"), ("HC165", "U11"), ("MUX", "U1")):
    part = line_of(ref, "Faceplate")["Part"]
    ck.check(f"D.{kind}_at_3V3", HC_VCC[0] <= 3.3 * 0.97 and 3.3 * 1.03 <= HC_VCC[1] and "DIP-16" in part,
             f"'{part[:50]}': VCC 3.3 V +-3 % within {HC_VCC} V")
    if kind in HC_FCLK:
        f2, f45 = HC_FCLK[kind]
        f33 = f2 + (f45 - f2) * (3.3 * 0.97 - 2.0) / (4.5 - 2.0)
        ck.within(f"D.{kind}_fclock_at_3V3", SPI_HZ, None, f33, " Hz",
                  f"interpolated fclock {f33 / 1e6:.1f} MHz at 3.2 V (SN74, -40..85 C); the 2.0 V figure "
                  f"({f2 / 1e6:.0f} MHz) alone would not cover 6.25 MHz")
mux = line_of("U1", "Faceplate")["Part"]
u1 = FBd["U1"].nets
r_on = CD4051_RON[5.0] * (5.0 - (CD4051_RON[5.0] * 5.0 - CD4051_RON[10.0] * 10.0) / (CD4051_RON[5.0] - CD4051_RON[10.0]))
vt = (CD4051_RON[5.0] * 5.0 - CD4051_RON[10.0] * 10.0) / (CD4051_RON[5.0] - CD4051_RON[10.0])
ron33 = CD4051_RON[5.0] * (5.0 - vt) / (3.3 - vt)
ck.check("D.CD4051B_alternative", "CD4051B" in mux and CD4051_VDD[0] <= 3.3 * 0.97
         and u1.get("6") == u1.get("7") == u1.get("8") == "GND_F",
         f"VDD 3.3 V -3 % = {3.3 * 0.97:.2f} V against its {CD4051_VDD[0]} V minimum (just inside); INH / VEE / VSS "
         f"(6, 7, 8) all on GND_F as for the 74HC4051. rON is not specified below 5 V; extrapolated from 5 / 10 V "
         f"(rON ~ 1/(VDD - {vt:.2f} V)): about {ron33 / 1e3:.1f} kOhm max at 3.3 V, against the 74HC4051's 180 R at 4.5 V")
# ceramic capacitors
for r in (r for r in rows if r["Group"] == "Capacitors"):
    mv = re.search(r"(\d+) V\b", r["Part"])
    ck.check(f"D.cap_voltage.{r['Part'][:24]}", mv is not None and int(mv.group(1)) >= CAP_MARGIN * RAIL_MAX,
             f"'{r['Part']}': expected >= {CAP_MARGIN * RAIL_MAX:.0f} V")
ck.check("D.1nF_C0G", "C0G" in line_of("C21")["Part"], line_of("C21")["Part"])
ck.check("D.100nF_X7R", "X7R" in line_of("C31")["Part"], line_of("C31")["Part"])
ck.check("D.no_10uF_text_needed", not any(p.kind in ("C", "CP") and p.value == "10u" for p in MB + FB)
         and not any("10 µF" in r["Part"] for r in rows), "no 10 uF part in the netlist or the BOM")
# E-series
for v in sorted({harness.ohms(p.value) for p in MB + FB if p.kind == "R"}):
    mant = round(v / 10 ** math.floor(math.log10(v)), 2)
    in24, in96 = mant in E24, mant in E96
    r = next(r for r in rows if r["Group"] == "Resistors" and harness.ohms(p_val := next(
        p.value for p in MB + FB if p.kind == "R" and harness.ohms(p.value) == v)) and f"Resistor {bom.ohms(p_val)}," in r["Part"])
    ck.check(f"D.E_series.{v:g}", in24 or (in96 and "1 %" in r["Part"]),
             f"{v:g} ohm: E24 {in24}, E96 {in96}; BOM '{r['Part'][:40]}'")
# worst-case dissipation of every resistor at 1/4 W


def net_range(net):
    """(min, max) volts a net can reach, normal use plus an external +-12.6 V on a jack."""
    if net in ("GND", "GND_F", "GND_D_F", "IN_NEGREF"):
        return 0.0, 0.0
    if net.startswith("3V3") or net.startswith(("L_", "SR_", "BTN_", "MUX_", "SCK", "MOSI", "MISO", "LED_LATCH",
                                                 "BTN_LOAD", "DAC_CS", "DAC_LDAC", "SPI", "PROBE", "POT_", "GATE_",
                                                 "T_CLK", "X_CLK", "DAC_X", "DAC_Y")):
        return 0.0, 3.3 * 1.03
    if net.startswith("LED_D1") and net[5:].split("_")[0] in ("11", "12", "13"):
        return -0.5, 2.2
    if net.startswith("LED_"):
        return LED_VF_MIN, 2.2
    if net in ("VREF",):
        return 2.5, 2.5
    if net == "NEG_REF":
        return -2.5, -2.5
    if net == "BIAS":
        return 1.32, 1.36
    if net.startswith("B_"):
        return -0.45, 0.85
    if net.startswith("ADC_"):
        return -0.6, 4.0
    if net.startswith("IN_"):
        return 0.0, 1.36
    if net.startswith("OA_T") and net[3:] in ("T1", "T2", "T3"):
        return 0.0, 8.25
    if net in ("OA_X1", "OA_X2", "OA_X3", "OA_Y"):
        return -5.45, 5.32
    if net.startswith("OA_"):
        return -1.6, 4.92
    if net in ("+12V",):
        return RAIL_MAX, RAIL_MAX
    if net in ("-12V",):
        return -RAIL_MAX, -RAIL_MAX
    return -RAIL_MAX, RAIL_MAX          # jack nets, switch lugs: anything a patch cable brings


worst_p = {}
for board, parts in (("Main", MB), ("Faceplate", FB)):
    for p in parts:
        if p.kind != "R":
            continue
        r = harness.ohms(p.value) * (1 - 0.01)
        (a0, a1), (b0, b1) = net_range(p.nets["1"]), net_range(p.nets["2"])
        v = max(abs(a1 - b0), abs(b1 - a0))
        i = v / r
        if any(n.startswith("OA_") for n in p.nets.values()):
            i = min(i, TL_ISC)           # an op-amp output limits the current to its short-circuit current
        worst_p[(board, p.ref)] = (i * i * r, v, p.nets)
hot = {k: x for k, x in worst_p.items() if x[0] > RES_P}
for (board, ref), (pw, v, nets) in sorted(worst_p.items(), key=lambda kv: -kv[1][0])[:12]:
    print(f"    {board} {ref} {nets}: {v:.1f} V worst -> {pw * 1e3:.0f} mW")
# verifier note: the figures are right for a zero-impedance source at the opposite rail (20.9 mA through a gate
# output's 1k is under the TL07x's 26 mA, a typical figure from SLOS080W's TL07xH table, so the op-amp's limit does
# not bite). If the other module's output has the usual 1k series resistor of its own, our 1k sees a quarter of it
# (at most ~0.11 W). An abuse case the original Marbles does not cover either (its output resistors are 0603).
hot_1k = {k: (x[1] / 2) ** 2 / harness.ohms("1k") for k, x in hot.items()}
ck.check("D.resistor_dissipation_quarter_watt", not hot,
         f"over {RES_P} W at the worst case (an output patched to another module's output at the opposite rail, "
         f"limited by the TL074's ~26 mA): {', '.join(f'{b} {r} {x[0] * 1e3:.0f} mW' for (b, r), x in sorted(hot.items()))}; "
         f"with a 1k in the other output: at most {max(hot_1k.values(), default=0) * 1e3:.0f} mW; "
         f"the library part behind them is TE's LR1F (0.6 W), the BOM asks for 1/4 W")
# gate LEDs: a gate jack driven to -12 V by another output
# verifier change: this compared two constants (12.6 V against 5 V) and read nothing from circuit.py. Now: every
# faceplate LED whose anode resistor goes to a jack tip net (which a patch cable can pull to -12.6 V) gets that
# reverse voltage; the others get the lowest voltage their drive net reaches. LED VR 5 V max: Kingbright WP710A10ID
# (the 3 mm T-1 the mixer's suite read) absolute maximum rating; Thonk publishes no LED datasheet (assumption).
tips = {tip for _, _, tip, _ in circuit.JACKS}
led_rev = {}
for p in FB:
    if p.kind != "LED_G":
        continue
    an = p.nets["1"]
    drive = [next(v for v in r.nets.values() if v != an) for r in FB if r.kind == "R" and an in r.nets.values()]
    led_rev[p.ref] = (max((-net_range(d)[0] if d in tips else -min(net_range(d)[0], 0.0)) for d in drive) if drive else 0.0,
                      drive)
bad_led = {r: v for r, v in led_rev.items() if v[0] > LED_VR_MAX}
ck.check("D.gate_LED_reverse_voltage", not bad_led and len(led_rev) == 7,
         f"reverse volts across the LED, drive net: {bad_led} (D11-D13 sit from the gate jack (T1_F-T3_F) through "
         f"3k3 to GND_F: a gate patched to another module's output at -12 V; with a 1k in that output about half); "
         f"3 mm LEDs VR {LED_VR_MAX} V max")

# ======================================================================== E. Thonk and mechanical parts
print("--- E. Thonk and mechanical parts")
jacks = [p for p in FB if p.kind == "JACK"]
r = by_part.get("Thonkiconn PJ398SM mono jack, with nut")
ck.check("E.jacks", r is not None and int(r["Qty"]) == len(jacks) == len(circuit.JACKS) == 16 and r["Source"] == "Thonk",
         f"expected 16 (design.md: 16 Thonkiconn jacks), circuit {len(jacks)}, BOM {r and r['Qty']}")
pots = [p for p in FB if p.kind == "POT"]
vals = collections.Counter(p.value.upper() for p in pots)
for v, n in vals.items():
    r = by_part.get(f"Alpha 9 mm vertical pot {v}, T18 shaft")
    ck.check(f"E.pots.{v}", r is not None and int(r["Qty"]) == n == 8, f"expected 8 Alpha B10K (design.md), BOM {r and r['Qty']}")
    ck.check(f"E.pots_in_Thonk_stock.{v}", v in THONK_T18_VERTICAL, f"{v} against {sorted(THONK_T18_VERTICAL)}")
btn = collections.Counter(p.kind for p in FB if p.kind.startswith("SWLED"))
for kind, colour, n in (("SWLED", "green", 3), ("SWLED_RG", "bipolar red/green", 4)):
    r = by_part.get(f"Thonk low-profile LED button, {colour}")
    ck.check(f"E.buttons.{colour}", r is not None and int(r["Qty"]) == btn[kind] == n and colour in THONK_BUTTON_COLOURS,
             f"expected {n} (design.md: green deja vu pair + EXT, bipolar mode / range), circuit {btn[kind]}, "
             f"BOM {r and r['Qty']}")
leds = [p for p in FB if p.kind == "LED_G"]
r = by_part.get("3 mm LED, green, 2 leads")
ck.check("E.LEDs", r is not None and int(r["Qty"]) == len(leds) == 7, f"7 output LEDs (D11-D17), BOM {r and r['Qty']}")
knob_rows = [r for r in rows if r["Part"].startswith("Knob")]
big = [ref for ref, label, *_ in circuit.POTS if ref in bom.panel.BIG_POTS]
big_labels = sorted(label for ref, label, *_ in circuit.POTS if ref in bom.panel.BIG_POTS)
ck.check("E.knobs", sum(int(r["Qty"]) for r in knob_rows) == len(pots)
         and any("15 mm" in r["Part"] and int(r["Qty"]) == 3 for r in knob_rows)
         and any("10 mm" in r["Part"] and int(r["Qty"]) == 5 for r in knob_rows)
         and big_labels == ["DEJA VU", "RATE", "SPREAD"],
         f"8 knobs: 3 x 15 mm on {big_labels} (design.md: RATE, DEJA VU, SPREAD), 5 x 10 mm; BOM "
         f"{[(r['Qty'], r['Part'][:40]) for r in knob_rows]}")
sizes = collections.Counter(len(nets) for _, _, nets in circuit.HEADERS)
want = ", ".join(f"{n} × 1×{p}" for p, n in sorted(sizes.items(), reverse=True))
for gender, text in (("female", "Female header, 2.54 mm, 8.5 mm tall"), ("male", "Male pin header, 2.54 mm")):
    r = by_part.get(f"{text}: {want}")
    ck.check(f"E.headers.{gender}", r is not None and int(r["Qty"]) == len(circuit.HEADERS) == 7
             and want == "2 × 1×8, 3 × 1×4, 2 × 1×3",
             f"circuit.HEADERS: {want}; BOM {r and r['Part']}")
socket_rows = [r for r in rows if r["Part"].endswith("IC socket")]
# M2 (2026-11-13): the faceplate's DIP-16s (U1, U9, U10, U11) are soldered without sockets (bom.SOLDERED); every
# other DIP footprint gets a socket, on a line of its own
soldered = getattr(bom, "SOLDERED", set())
for pins_n, refs, sold in ((14, ["U3", "U4", "U5", "U6", "U7", "U8"], []), (16, [], ["U1", "U9", "U10", "U11"])):
    dips = sorted([(b, ref) for (b, ref), p in fp.items() if re.match(rf"DIP-{pins_n}\b|DIP-{pins_n}_", p["fp"])],
                  key=lambda br: bom.natural(br[1]))
    want = [ref for b, ref in dips if (b, ref) not in soldered]
    got_sold = [ref for b, ref in dips if (b, ref) in soldered]
    r = by_part.get(f"DIP-{pins_n} IC socket")
    ok = (r is not None and int(r["Qty"]) == len(want) and r["Group"] == "Connectors") if want else r is None
    ck.check(f"E.DIP{pins_n}_sockets", ok and want == refs and got_sold == sold,
             f"a socket line for the {len(want)} socketed DIP-{pins_n} footprints in the routed master {want} "
             f"(soldered: {got_sold}); BOM {r and (r['Qty'], r['Refs'])}")
# the breakout's socket strips against the routed U2 footprint
u2 = R.main.parts["U2"]["pads"]
rows_x = collections.defaultdict(list)
for num, pd in u2.items():
    rows_x[round(pd.x, 1)].append(pd.y)
runs_all = []
for x, ys in sorted(rows_x.items()):
    ys = sorted(ys)
    runs, cur = [], 1
    gaps = []
    for a, b in zip(ys, ys[1:]):
        if abs(b - a - 2.54) < 0.02:
            cur += 1
        else:
            runs.append(cur)
            gaps.append(round((b - a) / 2.54) - 1)
            cur = 1
    runs.append(cur)
    runs_all.append((sorted(runs, reverse=True), gaps))
strip = next((r for r in rows if "breakout's two rows" in r["Part"]), None)
ms = re.search(r"(\d) × 1×(\d+) .*?and (\d) × 1×(\d+) .*?after (one) empty position", strip["Part"]) if strip else None
ck.check("E.breakout_strips", len(u2) == 56 and all(r == ([24, 4], [1]) for r in runs_all) and ms is not None
         and (int(ms.group(1)), int(ms.group(2)), int(ms.group(3)), int(ms.group(4))) == (2, 24, 2, 4)
         and int(strip["Qty"]) == 4,
         f"U2: {len(u2)} pads, per row (runs, empty positions) {runs_all}; BOM '{strip and strip['Part'][:120]}' x "
         f"{strip and strip['Qty']}")
print("    (open) the 40 male pins under the breakout's Seed rows (the Seed's own headers through the breakout, or "
      "long-tail stacking sockets as the breakout's README uses) are on no list; the breakout's BOM has only its "
      "1x4 headers")
# standoffs and screws
so = next((r for r in rows if "standoff" in r["Part"].lower()), None)
mso = re.search(r"female-female, ([\d.]+) mm", so["Part"]) if so else None
holes = len(R.main.holes)
ck.check("E.standoff_count", so is not None and int(so["Qty"]) == holes == len(R.face.holes) == len(bom.pcb.HOLES_FRONT) == 4,
         f"BOM {so and so['Qty']}, routed holes {holes} / {len(R.face.holes)}, pcb.HOLES_FRONT {len(bom.pcb.HOLES_FRONT)}")
ck.check("E.standoff_length", mso is not None and abs(float(mso.group(1)) - (FEMALE_BODY + MALE_PLASTIC)) <= 0.25
         and "8.5 mm female header" in so["Part"] and "2.5 mm plastic" in so["Part"],
         f"expected {FEMALE_BODY + MALE_PLASTIC} mm (8.5 mm socket + 2.5 mm male plastic), BOM "
         f"'{so and so['Part']}'")
screw = next((r for r in rows if "screw" in r["Part"].lower() and "standoff" not in r["Part"].lower()), None)
ck.check("E.screws", screw is not None and re.search(r"M3 × \d+ mm", screw["Part"]) is not None
         and int(screw["Qty"]) == 2 * holes, f"{screw and (screw['Qty'], screw['Part'])}: two per standoff")
# the power cable
cable = [r for r in rows if "power cable" in r["Part"].lower()]
txt = " ".join(r["Part"] + " " + r["Note"] for r in cable)
ck.check("E.power_cable_line", len(cable) == 1 and int(cable[0]["Qty"]) == 1, f"{[(r['Qty'], r['Part']) for r in cable]}")
ck.check("E.power_cable_10pin_module_end", re.search(r"10-pin (at|on) the module", txt) is not None
         and "10 or 16" not in txt,
         f"the breakout's J2 is a {BREAKOUT_J2_PINS}-pin unshrouded 2x5 (its BOM: HDR-M-2.54_2x5, Amphenol "
         f"67997-210HLF): the cable needs a 10-pin socket at the module end (verifier: a 16-pin socket on the bare "
         f"2x5 has 8 positions, one of them right, and its normal overhang hides the wrong ones, which put bus "
         f"rails on the module's GND; see test_power A); BOM says '{txt}'")
# one line per PCB
pcbs = [r for r in rows if r["Group"] == "PCBs"]
ck.check("E.one_line_per_PCB", len(pcbs) == 3 and all(int(r["Qty"]) == 1 for r in pcbs)
         and sorted(r["Part"].split()[0] for r in pcbs) == ["Faceplate", "Main", "Panel"],
         f"{[(r['Qty'], r['Part'][:30]) for r in pcbs]}")
(w, hh), _ = bom.routed()["Main"]
ck.check("E.PCB_sizes", (round(w, 1), round(hh, 1)) == (circuit.BOARD_W, circuit.BOARD_H)
         and abs(bom.panel.PANEL_W - (18 * 5.08 - 0.15)) < 0.2 and bom.panel.PANEL_H == 128.5,
         f"main {w:.1f} x {hh:.1f} (circuit {circuit.BOARD_W} x {circuit.BOARD_H}); panel {bom.panel.PANEL_W} x "
         f"{bom.panel.PANEL_H} for 18HP")
ck.check("E.no_stale_stock_notes", not any("check before ordering" in n.lower() or "dual-gang" in n.lower()
                                           for n in bom.NOTES), "no dual-gang pots here; no stock caveats left over")
ck.check("E.breakout_line", any("seed_power_opamps" in r["Part"] and int(r["Qty"]) == 1 for r in rows)
         and by_part.get("Electrosmith Daisy Seed", {}).get("Qty") in (1, "1"), "one breakout and one Seed")
ck.done()
