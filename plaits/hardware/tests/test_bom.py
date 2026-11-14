"""BOM group: Plaitsy's (Orchid's) bill of materials.

What it checks
  1  bom.py's in-memory build (bom.build(), bom.check(); its writer is never
     called) against circuit.py: every netlist part owned by exactly one line,
     quantities per kind and value, refs per board equal to the routed master's
     designators.
  2  The committed docs/bom.md, hardware/bom/plaits-bom.csv and -thonk.csv
     against what bom.py builds now (rendered in memory the way bom.write()
     formats them).
  3  Quantities: IC sockets per DIP chip, board-to-board headers against
     circuit.HEADERS, the breakout's female headers against its footprint and
     Rob Heel's Gerbers, standoffs = mounting holes in the routed boards, screws
     per standoff, standoff length against the mated header heights, knobs per
     pot, the power cable against the breakout's 10-pin header, PCB lines.
  4  Part numbers and ratings: capacitor voltage ratings against the rails they
     sit on, resistor dissipation at worst case, the BAT85 against the clamp
     current, the listed DO-35 alternatives (hole fit, VF at the clamp current),
     the 74HC4051 / "CD4051B also works" claim at 3.3 V, the bicolour LED Tayda
     sells and its green VF at 3.3 V through 470R, the button LED colour, the
     Thonk pot value, the TL074 grade (note), lead / hole fits.
  5  The Thonk table against the repo's combined bom/thonk-order.csv (read only).

Run from plaits/hardware/tests:  python test_bom.py
Only reads: imports circuit.py and bom.py (build / check / routed), opens the
committed files; nothing is written.
"""
import collections
import csv
import inspect
import io
import math
import os
import re

import harness

ck = harness.Checks("bom")
circuit = harness.load("circuit")
bom = harness.load("bom")
REPO = harness.REPO

# ==========================================================================================================
# Datasheet constants
# ----------------------------------------------------------------------------------------------------------
# Rails. The bus is +-12 V +-5 % at most (a busboard at 12.6 V); the breakout passes it through B5819W
# Schottkys (its BOM / Gerbers), so the module's +-12V nets never exceed the bus.
RAIL_MAX = 12.6
# Seed 3V3A / 3V3D: NOT CONFIRMED (the Seed datasheet v1.0.5 gives no tolerance): +-3 % assumed.
V33_MIN, V33_MAX = 3.3 * 0.97, 3.3 * 1.03
CAP_MARGIN = 1.5                     # rated voltage >= 1.5 x the largest DC across the part (usual derating)
R_MARGIN = 0.5                       # dissipation <= half the rating at the worst corner
R_TOL = 0.01                         # 1 % metal film (bom.py's resistor lines)
# Vishay BAT85S (DO-35), doc 85513 rev 2.2, 07-Nov-2024, Tamb 25 C, MAX forward voltage:
#   0.24 V at 0.1 mA, 0.32 V at 1 mA, 0.40 V at 10 mA, 0.50 V at 30 mA, 0.80 V at 100 mA; VR 30 V; IF 200 mA
# DO-35 (DO-204AH) package drawing in Vishay's sheets (rev 6, 19 Dec 2011): lead diameter 0.6 mm max.
# The alternatives bom.py lists, MAX VF at the given currents (25 C):
SCHOTTKY = {
    "BAT85": {"src": "Vishay BAT85S doc 85513 rev 2.2", "vf": [(0.1e-3, 0.24), (1e-3, 0.32), (10e-3, 0.40), (30e-3, 0.50),
                                                               (100e-3, 0.80)], "vr": 30, "if": 0.200, "lead": 0.6,
              "confirmed": True},
    # [Verify pass 2026-11-13: was "Nexperia, NOT CONFIRMED, from memory"; now read from Vishay's sheet, same figures]
    "BAT86": {"src": "Vishay BAT86S doc 85514 rev 1.9 (06-May-13), DO-35", "vf": [(0.1e-3, 0.30), (1e-3, 0.38),
                                                                             (10e-3, 0.45), (30e-3, 0.60), (100e-3, 0.90)],
              "vr": 50, "if": 0.200, "lead": 0.6, "confirmed": True},
    "BAT43": {"src": "Vishay BAT42 / BAT43 doc 85660 rev 2.2 (12-May-2025)", "vf": [(2e-3, 0.33), (15e-3, 0.45)],
              "vr": 30, "if": 0.200, "lead": 0.6, "confirmed": True},
    "BAT42": {"src": "Vishay doc 85660 rev 2.2: only 10 / 50 / 200 mA given; VF at lower current is below the 10 mA max",
              "vf": [(10e-3, 0.40), (50e-3, 0.65), (200e-3, 1.0)], "vr": 30, "if": 0.200, "lead": 0.6, "confirmed": True},
    "BAT46": {"src": "Vishay BAT46 doc 85662 rev 2.2 (07-Nov-2024)", "vf": [(0.1e-3, 0.25), (10e-3, 0.45), (250e-3, 1.0)],
              "vr": 100, "if": 0.150, "lead": 0.6, "confirmed": True},
    "SD103A": {"src": "Vishay SD103A doc 85754 rev 2.2 (08-Nov-2024): only 20 / 200 mA given",
               "vf": [(20e-3, 0.37), (200e-3, 0.60)], "vr": 40, "if": 0.200, "lead": 0.6, "confirmed": True},
    # [Verify pass 2026-11-13: both now read from the sheets; the memory figures were right, SD101's IF was 15 -> 30 mA]
    "1N5711": {"src": "ST 1N5711 (1999) and Microsemi LDS-0040 rev 2: VF max 0.41 V at 1 mA, 1.0 V at 15 mA (25 C, "
                      "pulsed), VBR 70 V, IF 15 mA (ST), DO-35 lead 0.56 max", "vf": [(1e-3, 0.41), (15e-3, 1.0)],
               "vr": 70, "if": 0.015, "lead": 0.56, "confirmed": True},
    "SD101": {"src": "Vishay SD101A/B/C doc 85629 rev 2.1 (07-Nov-2024): SD101A VF max 0.41 V at 1 mA, 1.0 V at 15 mA "
                     "(B 0.40 / 0.95, C 0.39 / 0.90), VR 60 V, IF 30 mA, DO-35 lead 0.6 max", "vf": [(1e-3, 0.41), (15e-3, 1.0)],
              "vr": 60, "if": 0.030, "lead": 0.6, "confirmed": True},
}


def vf_junction_rs(pts, i, slope=0.07):
    """For a part given only at two far-apart currents: VF = VF(i0) + slope per decade + I * Rs, with Rs fitted so the
    curve meets the second point (the log interpolation between the two overstates the middle: a junction plus series
    resistance is convex in log I). slope 70 mV / decade ASSUMED (Schottky, n ~ 1.1-1.2 at max). An estimate, not a
    bound."""
    (i0, v0), (i1, v1) = pts[0], pts[-1]
    rs = max(v1 - v0 - slope * math.log10(i1 / i0), 0) / (i1 - i0)
    return v0 + slope * math.log10(i / i0) + rs * (i - i0)
# The STM32's own clamp on the ADC pin. STMicro DS12556 rev 7 (STM32H750), Table 19: VIN on FT_xxx pins min
# VSS - 0.3 V; Table 20: injected current on FT pins -5 / +0 mA (positive injection not possible: no diode to VDD);
# Table 57 (functional susceptibility): PA1 (Seed pin 31, A9 = V/OCT) 0 mA negative injection. The VF of the
# chip's internal junction is not given: a silicon junction is assumed to start conducting (> 1 % of the clamp
# current) above 0.45 V at mA levels (ASSUMPTION, not from the sheet).
STM32_VIN_MIN = -0.3
SI_ONSET = 0.45
# 74HC595 at 3.3 V. TI SCLS041J (SN74HC595) VOH at VCC 4.5 V, IOH -6 mA: 4.3 V typ, 3.98 V min (25 C), 3.84 V min
# (full range) -> output resistance 33 ohm typ, 110 ohm max at 4.5 V. Scaled x1.5 for VCC = 3.3 V (ASSUMPTION:
# CMOS on-resistance ~ 1 / (VCC - Vt); TI gives no 3.3 V figure).
HC595_ROUT_TYP, HC595_ROUT_MAX = 33 * 1.5, 110 * 1.5
# Tayda 3 mm bicolour red / green common-cathode LED, SKU A-8599, OEM, no datasheet (taydaelectronics.com/
# new-arrivals/bi-color-led-red-green-3mm-common-cathode.html, read in the browser pane 2026-11-13): Forward
# Voltage Red 1.8-2.2 V, Forward Voltage Green 2.8-3.0 V, Forward Current 20 mA, white diffused lens, 40 deg.
# Lead size and pitch not given. A GaP green (565-570 nm) is about 2.1 V typ / 2.5 V max; 2.8-3.0 V is an
# InGaN-class green. [Verify pass 2026-11-13: page re-read, figures confirmed; the power group now uses the same.]
# No test current is given for the VF: read as at the listed 20 mA. At the 0.3-2.5 mA here VF is lower, so the 20 mA
# maximum is an upper bound (right for the worst-case minimum current); the typical currents below, from the 20 mA
# mid-range, come out somewhat low (the green's shortfall against 'about 3 mA' is far larger than that).
# [2026-11-14: (typical, max) per colour, typical = the middle of Tayda's range; and the Kingbright L-3WEGW that
# bom.py names since the test report's M1 fix: DSAA6458 V.18A at 25 C, IF = 20 mA, red (GaAsP/GaP) typ 2.0 / max
# 2.5 V, green (GaP) typ 2.2 / max 2.5 V. The part the BOM's D1 line names is used; Tayda's when it names none.]
LED_VF_TAYDA = {"R": (2.0, 2.2), "G": (2.9, 3.0)}
LED_VF_L3WEGW = {"R": (2.0, 2.5), "G": (2.2, 2.5)}
LED_MIN_MA = 1.0                     # ASSUMPTION: below ~1 mA a 3 mm diffused LED is dim beside one at 2-3 mA
LED_LEAD = 0.5                       # mm square, typical T-1 LED lead (NOT CONFIRMED for the Tayda part)
# Thonk low-profile LED button drawing PB01-109TL rev A (thonk.co.uk LowProfileButton.pdf, read 2026-11-13): LED
# material GaAsP / GaP (red, orange, yellow, green); blue and white are not covered by the drawing.
BUTTON_LED_COLOURS_GAP = {"red", "orange", "yellow", "green"}
# TI SCHS047O (CD4051B, rev. May 2026), 5.5: rON at VDD = 5 V (VEE = VSS = 0): 470 ohm typ, 1050 ohm max (25 C),
# 1200 ohm (85 C); rON is specified at VDD = 5, 10, 15 V only (none at 3.3 V). VIH min = 3.5 V at VDD = 5 V
# (0.7 VDD).
CD4051_RON_5V_MAX = 1050.0
CD4051_VIH_FRAC = 0.7
# TI SCHS122O (CD74HC4051): specified for VCC 2 V to 6 V (the 3.3 V supply is inside its range).
HC4051_VCC_RANGE = (2.0, 6.0)
# STM32H750 VOH (DS12556 rev 7, CMOS port, 8 mA): VDD - 0.4 V min.
SEED_VOH_MIN = V33_MIN - 0.4
# TI SLOS080W (TL07xx, rev. July 2025) offset voltage max at 25 C: TL07xC 10 mV, TL07xAC 6 mV, TL07xBC 3 mV,
# TL07xH 4 mV.
TL074_VOS_MAX = {"TL074 (C)": 10e-3, "TL074A": 6e-3, "TL074B": 3e-3, "TL074H": 4e-3}
# Thonk's Alpha 9 mm vertical T18 values (the user's paste of the shop list, 2026-10-31, in the module-design
# skill's parts.md): B5K, B10K, B25K, B50K, B100K, B250K, B1M, A50K, A100K, A1M (A10K out).
THONK_SINGLE = {"B5K", "B10K", "B25K", "B50K", "B100K", "B250K", "B1M", "A50K", "A100K", "A1M"}
# Board-to-board headers (2.54 mm). NOT CONFIRMED in this run (from Samtec's SSW / TSW drawings as remembered):
# SSW female socket insulator 0.335" = 8.51 mm; TSW male insulator 0.100" = 2.54 mm. Thonk's header bag gives no
# heights. Mated, the male's plastic sits on the socket: gap = 8.51 + 2.54 = 11.05 mm (design.md: about 11 mm).
FEMALE_BODY, MALE_PLASTIC = 8.51, 2.54
MATED_GAP = FEMALE_BODY + MALE_PLASTIC
STANDOFF_TOL = 0.3                   # mm: within a washer's thickness
# Rob Heel's seed_power_opamps breakout (github.com/rob-scape/daisy-seed-breakout-boards, Gerbers and drill file of
# 2025-08-29, BOM_seed_power_opamps_2025-08-29.csv): J2 "HDR-M-2.54_2x5" (LCSC C178292) = the 10-pin Eurorack power
# header (Gerber: 10 holes of 0.889 mm in 2 x 5); the Seed rows: 2 x 20 holes of 1.2 mm; J1 / J3 / J4 / J5:
# 4 x 4 holes of 0.889 mm in line with the Seed rows (J4 / J5 directly beyond pins 1 / 40, J1 / J3 one empty
# position beyond pins 20 / 21).
BREAKOUT_POWER_PINS = 10
BREAKOUT_ROW_PINS = {"seed": 2 * 20, "1x4": 4 * 4}
# Lead sizes for the hole checks (max): 1/4 W metal film resistor lead 0.6 mm (Yageo MFR-25: 0.55 +- 0.05 mm);
# DIP lead width 0.56 mm (TI N package); 0.64 mm square header pin (diagonal 0.905 mm).
LEAD_R, LEAD_DIP, HDR_DIAG = 0.6, 0.56, 0.64 * 2 ** 0.5
ROUND_CLEAR, SQUARE_CLEAR = 0.15, 0.05
# Thonk PJ398SM drawing: slots 0.6 x 1.3 (pin 1, sleeve), 0.6 x 1.5 (pin 2, switch), 0.5 x 1.5 (pin 3, tip).
JACK_SLOTS = {"1": (1.3, 0.6), "2": (1.5, 0.6), "3": (1.5, 0.5)}
# Taiwan Alpha SLH-211-414 (RD901F): pin holes 1.0 mm, lug slots 1.8 x 1.1 mm. Thonk PB01-109TL: 7 x 1.0 mm holes.
ALPHA_PIN_HOLE, ALPHA_LUG_SLOT, BUTTON_HOLE = 1.0, (1.8, 1.1), 1.0

# ==========================================================================================================
# 1  bom.py in memory
MB, FB = circuit.main_board_parts(), circuit.faceplate_parts()
lines, owned = bom.build()
problems = bom.check(owned)
ck.check("1.bom_check", not problems, f"bom.check(): every part owned once, refs = the routed master's; problems {problems}")
part_lines = {k: v for k, v in lines.items() if not k[2].endswith("IC socket")}
multi = []
for board, parts in (("Main", MB), ("Faceplate", FB)):
    for p in parts:
        n = sum(1 for k, line in part_lines.items() if (board, p.ref) in line["refs"] and k[2] not in (
            "Rob Heel's seed_power_opamps breakout, built: its own PCB and parts",) and "for the breakout's two rows" not in k[2])
        if n != 1:
            multi.append((board, p.ref, n))
ck.check("1.every_part_in_one_line", not multi, f"{len(MB)} main + {len(FB)} faceplate parts; owned by != 1 line: {multi}")
routed_refs = bom.routed()
for board, parts in (("Main", MB), ("Faceplate", FB)):
    ck.check(f"1.refs_equal_routed.{board}", routed_refs[board][1] == {p.ref for p in parts},
             f"routed only {sorted(routed_refs[board][1] - {p.ref for p in parts})}, circuit only "
             f"{sorted({p.ref for p in parts} - routed_refs[board][1])}")
want = collections.Counter()
for parts in (MB, FB):
    for p in parts:
        d = bom.describe(p)
        if d:
            want[d] += 1
qty_bad = [(k[2][:50], n, lines.get(k, {}).get("qty")) for k, n in want.items() if lines.get(k, {}).get("qty") != n]
ck.check("1.quantities_per_kind_value", not qty_bad, f"line qty = circuit.py count per (kind, value); bad {qty_bad}")
kinds = collections.Counter((p.kind, p.value) for p in MB + FB)
n_r = sum(n for (k, v), n in kinds.items() if k == "R")
n_c = sum(n for (k, v), n in kinds.items() if k in ("C", "CP"))
ck.check("1.resistor_total", n_r == sum(l["qty"] for k, l in lines.items() if k[1] == "Resistors"),
         f"circuit {n_r}, BOM {sum(l['qty'] for k, l in lines.items() if k[1] == 'Resistors')}")
ck.check("1.capacitor_total", n_c == sum(l["qty"] for k, l in lines.items() if k[1] == "Capacitors"),
         f"circuit {n_c}, BOM {sum(l['qty'] for k, l in lines.items() if k[1] == 'Capacitors')}")


# ==========================================================================================================
# 2  the committed files against a fresh build, rendered in memory exactly as bom.write() formats them
def render(lines):
    rows = []
    for (source, group, part), line in lines.items():
        refs = sorted(set(line["refs"]), key=lambda br: (br[0], bom.natural(br[1])))
        boards = sorted({b for b, _ in refs})
        if len(boards) > 1:
            text = "; ".join(f"{b}: " + ", ".join(r for bb, r in refs if bb == b) for b in boards)
        else:
            text = ", ".join(r for _, r in refs)
        rows.append({"Source": source, "Group": group, "Qty": line["qty"], "Part": part, "Refs": text,
                     "Board": " + ".join(boards) or "—", "Note": line["note"], "_size": line["size"]})
    rows.sort(key=lambda r: (r["Source"] != "Thonk", r["Source"], bom.GROUPS.index(r["Group"]), r["_size"], r["Part"]))
    fields = ["Source", "Group", "Qty", "Part", "Refs", "Board", "Note"]
    files = {}
    for suffix, keep in (("", lambda r: True), ("-thonk", lambda r: r["Source"] == "Thonk")):
        f = io.StringIO(newline="")
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(r for r in rows if keep(r))
        files[f"hardware/bom/{bom.MODULE['file']}-bom{suffix}.csv"] = f.getvalue()

    def table(sel):
        return ["| Qty | Part | Refs | Board | Note |", "|---|---|---|---|---|"] + [
            f"| {r['Qty']} | {r['Part']} | {r['Refs']} | {r['Board']} | {r['Note']} |" for r in sel]

    A = bom.panel.ART
    hp = round((bom.panel.PANEL_W + 0.3) / 5.08)
    md = [f"# {bom.MODULE['project']} BOM: {A['title']}, {A['subtitle'].lower()}, {hp}HP", "",
          "Generated by `hardware/tools/bom.py` from `circuit.py`: don't edit it by hand. Quantities are for",
          f"one module. The netlist's refs are checked against `{bom.MODULE['routed']}`, board by board.",
          f"CSV: `hardware/bom/{bom.MODULE['file']}-bom.csv` (everything) and `hardware/bom/{bom.MODULE['file']}-bom-thonk.csv`",
          "(the Thonk lines).", "", "## From Thonk", ""]
    md += table([r for r in rows if r["Source"] == "Thonk"])
    md += ["", "## Everything else", ""]
    for source in sorted({r["Source"] for r in rows} - {"Thonk"}):
        md += [f"### {source}", ""] + table([r for r in rows if r["Source"] == source]) + [""]
    md += ["## Notes", ""] + [f"- {n}" for n in bom.NOTES] + [""]
    files["docs/bom.md"] = "\n".join(md)
    return rows, files


# the copy above must follow bom.write(): a few of its format strings, checked in its source
src = inspect.getsource(bom.write)
mirror_ok = all(s in src for s in ('"| Qty | Part | Refs | Board | Note |"', 'f"| {r[\'Qty\']} | {r[\'Part\']} | {r[\'Refs\']} | '
                                   '{r[\'Board\']} | {r[\'Note\']} |"', '"Board": " + ".join(boards) or "—"',
                                   'GROUPS.index(r["Group"]), r["_size"], r["Part"]', '"(the Thonk lines).", "", "## From Thonk", ""'))
ck.check("2.render_mirrors_bom_write", mirror_ok, "the in-memory renderer copies bom.write()'s formatting (test upkeep "
                                                  "if this fails, not a finding)")
rows, files = render(lines)
for rel, fresh in files.items():
    path = os.path.join(harness.MODULE, *rel.split("/"))
    committed = open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")
    fresh = fresh.replace("\r\n", "\n")
    diff = ""
    if fresh != committed:
        a, b = fresh.split("\n"), committed.split("\n")
        i = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        diff = (f"first difference at line {i + 1}: fresh {a[i] if i < len(a) else None!r} / committed "
                f"{b[i] if i < len(b) else None!r}")
    ck.check(f"2.committed_equals_fresh.{os.path.basename(rel)}", fresh == committed,
             diff or f"{len(fresh)} chars identical")

by_part = {r["Part"]: r for r in rows}
thonk = [r for r in rows if r["Source"] == "Thonk"]


def line_of(ref):
    return next(r for r in rows if ref in re.split(r"[ ,;:]+", r["Refs"]) and "socket" not in r["Part"]
                and "breakout" not in r["Part"])


def part(ref):
    return next(p for p in MB + FB if p.ref == ref)


# ==========================================================================================================
# 3  quantities and mechanics
R = harness.routed()
# [2026-11-14: the socketed chips are the DIP chips bom.py does not list in SOLDERED (the test report's M3 fix
# solders U1 / U9 / U10 straight in); the check was {14: 2, 16: 3}, a count of today's chips.]
socketed = [(board, p) for board, parts in (("Main", MB), ("Faceplate", FB)) for p in parts
            if p.kind in bom.SOCKETS and (board, p.ref) not in bom.SOLDERED]
dips = collections.Counter(bom.SOCKETS[p.kind] for _, p in socketed)
socks = {int(m.group(1)): r["Qty"] for r in rows for m in [re.fullmatch(r"DIP-(\d+) IC socket", r["Part"])] if m}
fp_pins = {}
for b, parts in (("main", MB), ("face", FB)):
    for p in parts:
        if p.kind in bom.SOCKETS:
            fp_pins[p.ref] = len(R.board(b).parts[p.ref]["pads"])
ck.check("3.sockets_per_DIP", socks == dict(dips)
         and all(fp_pins[p.ref] == bom.SOCKETS[p.kind] for p in MB + FB if p.kind in bom.SOCKETS),
         f"a socket per socketed DIP chip ({[p.ref for _, p in socketed]}; soldered: "
         f"{sorted(r for _, r in bom.SOLDERED)}); BOM {socks}, chips {dict(dips)}, footprint pads {fp_pins}")
hdr_pins = {ref: len(pins) for ref, _, pins in circuit.HEADERS}
sizes = collections.Counter(hdr_pins.values())
want_text = ", ".join(f"{n} × 1×{pins}" for pins, n in sorted(sizes.items(), reverse=True))
fem = [r for r in rows if r["Part"].startswith("Female header, 2.54 mm, 8.5 mm tall:")]
mal = [r for r in rows if r["Part"].startswith("Male pin header")]
ck.check("3.board_headers", len(fem) == 1 and len(mal) == 1 and fem[0]["Part"].endswith(want_text)
         and mal[0]["Part"].endswith(want_text) and fem[0]["Qty"] == mal[0]["Qty"] == len(circuit.HEADERS),
         f"circuit.HEADERS {hdr_pins} -> '{want_text}' female (main) and male (faceplate); BOM "
         f"{[(r['Qty'], r['Part']) for r in fem + mal]}")
fp_hdr = {ref: len(R.main.parts[ref]["pads"]) for ref in hdr_pins}
ck.check("3.header_footprints_pin_counts", fp_hdr == hdr_pins and all(len(R.face.parts[circuit.fb_ref(r)]["pads"]) == n
                                                                    for r, n in hdr_pins.items()),
         f"routed H / HF pads {fp_hdr} against {hdr_pins}")
# the breakout's female headers: 2 x 1x24 + 2 x 1x4
bk = next((r for r in rows if "for the breakout's two rows" in r["Part"]), None)
u2 = R.main.parts["U2"]["pads"]
m = re.search(r"(\d+) × 1×(\d+) \(audio header \+ Seed pins\) and (\d+) × 1×(\d+)", bk["Part"]) if bk else None
bom_pins = int(m.group(1)) * int(m.group(2)) + int(m.group(3)) * int(m.group(4)) if m else None
# count the footprint's pads per contiguous run along each row
runs = []
for row in (sorted((p for p in u2.values() if abs(p.x - u2["1"].x) < 0.1), key=lambda p: p.y),
            sorted((p for p in u2.values() if abs(p.x - u2["40"].x) < 0.1), key=lambda p: p.y)):
    run = 1
    for a, b in zip(row, row[1:]):
        if abs((b.y - a.y) - 2.54) < 0.02:
            run += 1
        else:
            runs.append(run)
            run = 1
    runs.append(run)
ck.check("3.breakout_female_headers", bk is not None and bk["Qty"] == 4 and sorted(runs) == [4, 4, 24, 24]
         and bom_pins == len(u2) == BREAKOUT_ROW_PINS["seed"] + BREAKOUT_ROW_PINS["1x4"],
         f"BOM '{bk and bk['Qty']} x ({m and m.groups()})' = {bom_pins} pins; footprint runs {sorted(runs)} "
         f"({len(u2)} pads); Gerbers {BREAKOUT_ROW_PINS['seed']} + {BREAKOUT_ROW_PINS['1x4']} holes")
# standoffs, screws, length
so = next((r for r in rows if "standoff" in r["Part"].lower()), None)
holes = (len(R.main.holes), len(R.face.holes))
ck.check("3.standoffs_per_hole", so is not None and so["Qty"] == holes[0] == holes[1] == len(bom.pcb.HOLES_FRONT),
         f"BOM {so and so['Qty']}, routed holes main {holes[0]} / faceplate {holes[1]}, pcb.HOLES_FRONT "
         f"{len(bom.pcb.HOLES_FRONT)}")
screw = next((r for r in rows if "screw" in r["Part"].lower() and "standoff" not in r["Part"].lower()), None)
ck.check("3.screws_two_per_standoff", screw is not None and so is not None and screw["Qty"] == 2 * so["Qty"]
         and re.search(r"M3 ?× ?\d+ mm", screw["Part"]) is not None,
         f"screws {screw and (screw['Qty'], screw['Part'])}, standoffs {so and so['Qty']}")
ml = re.search(r"female-female, ([\d.]+) mm", so["Part"]) if so else None
length = float(ml.group(1)) if ml else None
ck.check("3.standoff_length_vs_header_stack", length is not None and abs(length - MATED_GAP) <= STANDOFF_TOL,
         f"8.51 mm socket + 2.54 mm male plastic = {MATED_GAP:.2f} mm (heights not confirmed); BOM {length} mm")
dm = re.search(r"about (\d+) mm; measure", harness.text("docs", "design.md"))
ck.check("3.design_md_standoff_length", dm is not None and length == float(dm.group(1)),
         f"design.md 'about {dm and dm.group(1)} mm', BOM {length} mm")
# screw length: 1.6 mm board, the standoff's thread at least 3 mm deep (assumed for an M3 F-F standoff)
sl = re.search(r"M3 × (\d+) mm", screw["Part"]) if screw else None
ck.check("3.screw_engagement", sl is not None and 3.0 <= int(sl.group(1)) - 1.6 <= length / 2,
         f"M3 x {sl and sl.group(1)} through 1.6 mm: {int(sl.group(1)) - 1.6 if sl else 0:.1f} mm in the standoff "
         f"(>= 3 mm, <= half its {length} mm so the two screws do not meet)")
# knobs
knob_rows = [r for r in rows if r["Part"].startswith("Knob")]
n_pots = sum(1 for p in FB if p.kind == "POT")
ck.check("3.knobs_one_per_pot", sum(r["Qty"] for r in knob_rows) == n_pots == 7,
         f"7 pots; knob lines {[(r['Qty'], r['Part']) for r in knob_rows]}")
sz = collections.Counter(bom.panel.KNOB_SIZE[p.ref] for p in FB if p.kind == "POT")
want_k = {f"about {2 * bom.panel.ART['knob'][s]:.0f} mm": n for s, n in sz.items()}
got_k = {re.search(r"about \d+ mm", r["Part"]).group(0): r["Qty"] for r in knob_rows}
ck.check("3.knob_sizes_vs_panel", got_k == want_k, f"panel.KNOB_SIZE / ART['knob'] {want_k}, BOM {got_k}")
# power cable: the breakout's J2 is a 10-pin header
cable = [r for r in rows if "power cable" in r["Part"].lower()]
ctext = " ".join(r["Part"] + " " + r["Note"] for r in cable)
ck.check("3.power_cable_count", len(cable) == 1 and cable[0]["Qty"] == 1, f"{[(r['Qty'], r['Part']) for r in cable]}")
ck.check("3.power_cable_10_pin", "10" in re.sub(r"\(10 or 16\)", "", ctext) and "16" in ctext and "10 or 16" not in ctext,
         f"the breakout's J2 is HDR-M-2.54_2x5 (its BOM, LCSC C178292; 10 holes in its drill file): the cable must be "
         f"10-pin at the module end (10-to-16 for a 16-pin bus). BOM: '{ctext}'")
# PCB lines
pcbs = [r for r in rows if r["Group"] == "PCBs"]
(wm, hm), _ = routed_refs["Main"]
(wf, hf), _ = routed_refs["Faceplate"]
ck.check("3.pcb_lines", sum(r["Qty"] for r in pcbs) == 3 and (round(wm, 1), round(hm, 1)) == (round(wf, 1), round(hf, 1))
         == (circuit.BOARD_W, circuit.BOARD_H), f"3 boards (main, faceplate, panel), {wm:.1f} x {hm:.1f} / {wf:.1f} x {hf:.1f}")
ck.check("3.panel_12HP", abs(bom.panel.PANEL_W - (12 * 5.08 - 0.36)) < 0.1 and bom.panel.PANEL_H == 128.5,
         f"12HP = 60.6 x 128.5 mm; panel.py {bom.panel.PANEL_W} x {bom.panel.PANEL_H}")
# jacks / pots / buttons / LEDs counts in the panel lines
cnt = {"JACK": (by_part.get("Thonkiconn PJ398SM mono jack, with nut") or {}).get("Qty"),
       "POT": (by_part.get("Alpha 9 mm vertical pot B10K, T18 shaft") or {}).get("Qty"),
       "SWLED": sum(r["Qty"] for r in rows if r["Part"].startswith("Thonk low-profile LED button")),
       "LED_RG": sum(r["Qty"] for r in rows if "bicolour LED" in r["Part"])}
ck.check("3.panel_part_counts", cnt == {"JACK": 10, "POT": 7, "SWLED": 2, "LED_RG": 8},
         f"10 jacks, 7 pots, 2 buttons, 8 LEDs; BOM {cnt}")

# ==========================================================================================================
# 4  part numbers and ratings
DEVS = {}
for b in ("main", "face"):
    for ref in R.board(b).parts:
        DEVS[ref] = R.device(b, ref)


# node voltage intervals (worst case) for the rating checks
def stage_range(name):
    """(min, max) of the stage's op-amp output for a jack voltage of +-RAIL_MAX, 1 % parts, 3V3A tolerance."""
    _, _, u, s, rf, cf, bias = next(c for c in circuit.CV_CHANNELS if c[0] == name)
    top, bot = ("R45", "R46") if bias == "BIAS_A" else ("R47", "R48")
    rt, rb = harness.ohms(part(top).value), harness.ohms(part(bot).value)
    vb = [v * rb * (1 + kb) / (rt * (1 + kt) + rb * (1 + kb)) for v in (V33_MIN, V33_MAX) for kt in (-R_TOL, R_TOL)
          for kb in (-R_TOL, R_TOL)]
    g = [harness.ohms(rf) * (1 + a) / (harness.ohms("100k") * (1 + b)) for a in (-R_TOL, R_TOL) for b in (-R_TOL, R_TOL)]
    outs = [b_ * (1 + gg) - gg * vin for b_ in vb for gg in g for vin in (-RAIL_MAX, RAIL_MAX)]
    return min(outs), max(outs), (min(vb), max(vb))


VF85_MIN = 0.15                                      # BAT85 VF at the clamp current, low bound (for the max current)


def node_range(net):
    n = net[:-2] if net.endswith("_F") else net
    if n == "+12V":
        return (11.0, RAIL_MAX)
    if n == "-12V":
        return (-RAIL_MAX, -11.0)
    if n in ("GND", "GND_D"):
        return (0.0, 0.0)
    if n in ("3V3A", "3V3D", "MOSI", "SCK", "LED_LATCH", "PROBE", "MUX_OUT", "MUX_S0", "MUX_S1", "MUX_S2", "SR_CHAIN") \
            or n.startswith(("L_", "LED_", "BTN_", "TN_", "POT_", "ATT_")):
        return (0.0, V33_MAX)
    if n.startswith("CV_"):
        return (-RAIL_MAX, RAIL_MAX)
    if n.startswith("BIAS_"):
        lo, hi, vb = stage_range("MODEL" if n == "BIAS_A" else "VOCT")
        return vb
    if n.startswith(("IN_", "OA_", "ADC_")):
        name = n.split("_", 1)[1]
        lo, hi, vb = stage_range(name)
        if n.startswith("IN_"):
            return (vb[0] - 0.05, vb[1] + 0.05)       # the virtual ground sits on the bias (TL074 Vos < 15 mV)
        if n == "ADC_VOCT":
            return (max(lo, -0.45), min(hi, V33_MAX + 0.45))    # clamped by D21 / D22
        return (lo, hi)
    raise KeyError(net)


def across(p):
    a, b = (node_range(n) for n in p.nets.values())
    return max(abs(a[1] - b[0]), abs(b[1] - a[0]))


# capacitors: rated voltage (BOM text and the routed master's device) against the DC across them
cap_bad = []
for p in MB + FB:
    if p.kind != "C":
        continue
    v = across(p)
    txt = line_of(p.ref)["Part"]
    mt = re.search(r"(\d+) V\b", txt)
    dv = re.search(r"(\d+)\s*V", DEVS[p.ref].get("Voltage Rating", "") or "")
    rated = min(int(mt.group(1)) if mt else 0, int(dv.group(1)) if dv else 10 ** 6)
    if rated < CAP_MARGIN * v:
        cap_bad.append((p.ref, p.value, f"{v:.1f} V across", f"BOM {mt and mt.group(0)}", f"device {dv and dv.group(0)}"))
ck.check("4.capacitor_voltage_ratings", not cap_bad,
         f"every capacitor rated >= {CAP_MARGIN} x the largest DC across it (BOM text and the routed device); bad {cap_bad}")
# resistors: worst-case dissipation against half the rating the BOM orders
r_bad, r_top = [], []
for p in MB + FB:
    if p.kind != "R":
        continue
    v = across(p)
    pw = v * v / (harness.ohms(p.value) * (1 - R_TOL))
    txt = line_of(p.ref)["Part"]
    w = re.search(r"(1/4|1/2|\d+(?:\.\d+)?) W", txt)
    rating = {"1/4": 0.25, "1/2": 0.5}.get(w.group(1), None) if w else None
    if rating is None and w:
        rating = float(w.group(1))
    r_top.append((pw, p.ref))
    if rating is None or pw > R_MARGIN * rating:
        r_bad.append((p.ref, p.value, f"{pw * 1e3:.1f} mW", txt))
r_top.sort(reverse=True)
ck.check("4.resistor_dissipation", not r_bad,
         f"worst case <= half the rating; highest {[(r, f'{pw * 1e3:.1f} mW') for pw, r in r_top[:4]]}; bad {r_bad}")
for ref in ("R60", "R61"):
    p = part(ref)
    i = (V33_MAX - 1.6) / (harness.ohms(p.value) * (1 - R_TOL))      # button LED VF >= 1.6 V (GaAsP / GaP, assumed)
    ck.check(f"4.{ref}_button_LED_current", i * i * harness.ohms(p.value) < R_MARGIN * 0.25 and i < 20e-3,
             f"{i * 1e3:.1f} mA from the Seed GPIO (STM32 IIO 20 mA max, DS12556 Table 20), "
             f"{i * i * harness.ohms(p.value) * 1e3:.1f} mW in {p.value} R")
# BAT85 clamps: the worst-case clamp currents
lo_v, hi_v, _ = stage_range("VOCT")
rs = harness.ohms(part("R44").value) * (1 - R_TOL)
I_POS = (hi_v - V33_MIN - VF85_MIN) / rs
I_NEG = (-lo_v - VF85_MIN) / rs if lo_v < 0 else 0.0


def vf_max(name, i):
    """Datasheet VF max at current i: log-interpolated between the given points; below the first point the first
    point's value (an upper bound, VF rises with I)."""
    pts = SCHOTTKY[name]["vf"]
    if i <= pts[0][0]:
        return pts[0][1]
    for (i0, v0), (i1, v1) in zip(pts, pts[1:]):
        if i0 <= i <= i1:
            return v0 + (v1 - v0) * math.log10(i / i0) / math.log10(i1 / i0)
    return pts[-1][1]


b85 = SCHOTTKY["BAT85"]
ck.check("4.BAT85_current_rating", b85["if"] >= 10 * max(I_POS, I_NEG),
         f"clamp current at worst {I_POS * 1e3:.2f} mA (D21, OA_VOCT up to {hi_v:.2f} V) / {I_NEG * 1e3:.2f} mA (D22, OA "
         f"down to {lo_v:.2f} V) through R44; BAT85 IF {b85['if'] * 1e3:.0f} mA")
vr_need = V33_MAX + vf_max("BAT85", I_POS)
ck.check("4.BAT85_reverse_rating", b85["vr"] >= 2 * vr_need, f"largest reverse voltage {vr_need:.2f} V, VR {b85['vr']} V")
vneg = -vf_max("BAT85", I_NEG)
ck.check("4.D22_holds_PA1_within_VSS-0.3V", vneg >= STM32_VIN_MIN,
         f"at the worst negative clamp current {I_NEG * 1e3:.2f} mA the BAT85's VF max ({-vneg:.3f} V, {b85['src']}) puts "
         f"PA1 (V/OCT, A9) at {vneg:.3f} V; DS12556 Table 19 VIN min is VSS - 0.3 V and Table 57 gives PA1 0 mA "
         f"negative-injection susceptibility (other ADC readings may shift while V/OCT is above about +7.1 V, where D22 clamps). Within the "
         f"-5 mA injection limit (Table 20) either way: no damage")
# [2026-11-14: the line Plaitsy's BOM prints for D21 / D22 (bom.describe, which takes the module's REF_PART
# override), not the shared catalogue entry, which other modules' copies keep identical.]
alt_text = bom.describe(part("D21"))[2]
alts = re.findall(r"\b(BAT8\d|BAT4\d|SD10\d\w?|1N57\d\d)\b", alt_text)
# [Verify pass 2026-11-13: this required exactly today's list (a snapshot of bom.py), so dropping SD101 / 1N5711 as
# proposed would have failed it. Now: the BAT85 is named first and every alternative gets a datasheet entry below
# (4.alternative_known fails for one without).]
ck.check("4.alternatives_listed", bool(alts) and alts[0] == "BAT85", f"bom.py lists {alts}")
d21_fp = R.fp_docs[R.main.parts["D21"]["fp"]]
d_hole = min(p["hole"]["width"] * harness.MIL for h, p in d21_fp["recs"] if h["type"] == "PAD")
for name in [a for a in alts if a != "BAT85"] + ["BAT85"]:
    s = SCHOTTKY.get(name)
    if s is None:
        ck.check(f"4.alternative_known.{name}", False, f"no datasheet entry for {name}")
        continue
    fit = s["lead"] + ROUND_CLEAR <= d_hole
    vneg_a, vpos_a = vf_max(name, I_NEG), vf_max(name, I_POS)
    # two points more than a decade apart: also the junction + series-R estimate (the log interpolation overstates
    # the middle); the verdict takes the lower of the two, so a part only fails if both are above SI_ONSET
    est = ""
    if len(s["vf"]) == 2 and s["vf"][1][0] / s["vf"][0][0] > 10 and s["vf"][0][0] <= I_NEG:
        jn, jp = vf_junction_rs(s["vf"], I_NEG), vf_junction_rs(s["vf"], I_POS)
        est = f" (junction + series-R estimate {jn:.3f} / {jp:.3f} V)"
        vneg_a, vpos_a = min(vneg_a, jn), min(vpos_a, jp)
    ok = fit and vneg_a <= SI_ONSET and vpos_a <= SI_ONSET and s["if"] >= 2 * I_POS
    ck.check(f"4.clamp_diode.{name}", ok,
             f"lead {s['lead']} mm in the {d_hole:.2f} mm hole ({'fits' if fit else 'too tight'}); VF max "
             f"{vf_max(name, I_NEG):.3f} V at {I_NEG * 1e3:.1f} mA / {vf_max(name, I_POS):.3f} V at {I_POS * 1e3:.1f} mA"
             f"{est} (BAT85 {vf_max('BAT85', I_NEG):.3f} / {vf_max('BAT85', I_POS):.3f}) against {SI_ONSET} V (a "
             f"silicon junction, assumed); IF {s['if'] * 1e3:.0f} mA; source: {s['src']}")
# 74HC4051 and "CD4051B also works"
mux_txt = bom.describe(part("U1"))[2]          # Plaitsy's own line (see alt_text above)
ck.check("4.HC4051_supply_range", HC4051_VCC_RANGE[0] <= V33_MIN and V33_MAX <= HC4051_VCC_RANGE[1],
         f"3V3A {V33_MIN:.2f}..{V33_MAX:.2f} V inside SCHS122O's {HC4051_VCC_RANGE} V")
claims_cd = "CD4051B also works" in mux_txt
ck.check("4.CD4051B_logic_levels_at_3V3", SEED_VOH_MIN >= CD4051_VIH_FRAC * V33_MAX,
         f"CD4051B VIH = 0.7 VDD = {CD4051_VIH_FRAC * V33_MAX:.2f} V at VDD 3V3A max; Seed VOH min {SEED_VOH_MIN:.2f} V")
ck.check("4.CD4051B_specified_at_3V3", not claims_cd,
         f"bom.py: '{mux_txt}'. TI SCHS047O specifies rON only at VDD 5 / 10 / 15 V (at 5 V already {CD4051_RON_5V_MAX:.0f} "
         f"ohm max); at 3.3 V it is unspecified and several times higher, in series with the pot's up to 2.5k: the claim "
         f"is unproven. Drop it, or name the CD74HC4051 / 74HC4051 only")
# the bicolour LED
led_txt = line_of("D1")["Part"]
ck.check("4.LED_line", "bicolour" in led_txt and "common cathode" in led_txt and "3 leads" in led_txt
         and line_of("D1")["Qty"] == 8, f"{line_of('D1')['Qty']} x '{led_txt}'")
led_hole = min(p["hole"]["width"] * harness.MIL for h, p in R.fp_docs[R.face.parts["D1"]["fp"]]["recs"] if h["type"] == "PAD")
ck.check("4.LED_lead_in_hole", LED_LEAD * 2 ** 0.5 + SQUARE_CLEAR <= led_hole,
         f"{LED_LEAD} mm square lead (diagonal {LED_LEAD * 2 ** 0.5:.2f}) in the LED-3MM-3P {led_hole:.2f} mm holes "
         "(lead not confirmed)")      # [2026-11-14: the hole read from the footprint, 0.9 mm since M2]
r_led = harness.ohms("470")


LED_PART = "Kingbright L-3WEGW" if "L-3WEGW" in led_txt else "Tayda A-8599"
LED_VF = LED_VF_L3WEGW if "L-3WEGW" in led_txt else LED_VF_TAYDA


def led_ma(colour, worst):
    vf = LED_VF[colour][1] if worst else LED_VF[colour][0]
    v = V33_MIN if worst else 3.3
    rout = HC595_ROUT_MAX if worst else HC595_ROUT_TYP
    return max(v - vf, 0) / (r_led * (1 + (R_TOL if worst else 0)) + rout) * 1e3


m3 = re.search(r"about (\d+(?:\.\d+)?) mA per colour", harness.text("docs", "design.md"))
claim = float(m3.group(1)) if m3 else None
typ = {c: led_ma(c, False) for c in "RG"}
ck.check("4.design_md_LED_current_typ", claim is not None and all(abs(v - claim) <= 0.35 * claim for v in typ.values()),
         f"design.md 'about {claim} mA per colour'; typical with the {LED_PART} the BOM names (VF red "
         f"{LED_VF['R'][0]}, green {LED_VF['G'][0]} V typ), 470R and the 595's output: red {typ['R']:.2f} mA, green "
         f"{typ['G']:.2f} mA")
worst = {c: led_ma(c, True) for c in "RG"}
ck.check("4.LED_green_lit_at_3V3", worst["G"] >= LED_MIN_MA and LED_VF["G"][1] <= 2.6,
         f"{LED_PART} green VF max {LED_VF['G'][1]} V: at 3V3D {V33_MIN:.2f} V through 470R + the 595 "
         f"({HC595_ROUT_MAX:.0f} ohm) the green gets {worst['G']:.2f} mA at worst ({typ['G']:.2f} typ) against red "
         f"{worst['R']:.2f} ({typ['R']:.2f}); with Tayda's A-8599 (green 2.8-3.0 V, an InGaN-class green) 'yellow = "
         f"both on' would come out red-orange and the green bank dim")
# the button LED
btn_txt = bom.BUTTONS["SWLED"]
ck.check("4.button_LED_colour_named", any(c in btn_txt for c in BUTTON_LED_COLOURS_GAP),
         f"bom.py BUTTONS: '{btn_txt}' (known: colour still open). Thonk PB01-109TL lists a GaAsP / GaP LED: red, orange, "
         f"yellow or green suit 3.3 V through 470R; blue / white (VF ~3 V) would be almost dark")
# the pots
pot_vals = {p.value.upper() for p in FB if p.kind == "POT"}
ck.check("4.pot_values_in_Thonk_stock", pot_vals <= THONK_SINGLE, f"{sorted(pot_vals)} against Thonk's T18 list")
ck.check("4.pot_line_Alpha_B10K_T18", by_part.get("Alpha 9 mm vertical pot B10K, T18 shaft", {}).get("Source") == "Thonk",
         "Alpha 9 mm vertical pot B10K, T18 shaft from Thonk")
# TL074 grade: a note, not a pass / fail on the design (calibration takes the offset out)
noise_gain = 1 + harness.ohms("33k") / harness.ohms("100k")
g_v = harness.ohms("33k") / harness.ohms("100k")
err = {k: v * noise_gain / g_v for k, v in TL074_VOS_MAX.items()}
tl_txt = line_of("U3")["Part"]
# [Verify pass 2026-11-13: this was ck.check(..., True, ...), a check that could not fail; kept as an info line.]
print("    (info) 4.note_TL074_grade: " +
      f"BOM '{tl_txt}' (routed device {DEVS['U3'].get('Manufacturer Part')}); worst V/OCT error before calibration, "
      f"referred to the jack: " + ", ".join(f"{k} {v * 1e3:.0f} mV ({v / (1 / 12) :.2f} semitone)" for k, v in err.items()))
# holes and leads
ROUTED_DOCS = R.fp_docs


def holes_of(fp_title):
    return {str(p["num"]): (p["hole"]["width"] * harness.MIL, p["hole"]["height"] * harness.MIL, p["hole"]["holeType"])
            for h, p in ROUTED_DOCS[fp_title]["recs"] if h["type"] == "PAD"}


fit_bad = []
for b in ("main", "face"):
    for ref, pl in R.board(b).parts.items():
        hs = holes_of(pl["fp"])
        p = part(ref)
        need = {"R": LEAD_R + ROUND_CLEAR, "C": 0.5 + ROUND_CLEAR, "TL074": LEAD_DIP + ROUND_CLEAR,
                "MUX": LEAD_DIP + ROUND_CLEAR, "HC595": LEAD_DIP + ROUND_CLEAR, "BAT85": 0.6 + ROUND_CLEAR,
                "HDR8": HDR_DIAG + SQUARE_CLEAR, "HDR9": HDR_DIAG + SQUARE_CLEAR, "SEED": HDR_DIAG + SQUARE_CLEAR,
                "POT": ALPHA_PIN_HOLE - 0.01, "SWLED": BUTTON_HOLE - 0.01}.get(p.kind)
        if need is None:
            continue
        small = [(n, round(w, 3)) for n, (w, h, t) in hs.items() if t == "ROUND" and w < need]
        if small:
            fit_bad.append((ref, pl["fp"], small, need))
ck.check("4.holes_take_the_leads", not fit_bad, f"round holes >= lead + clearance; bad {fit_bad}")
jh = holes_of(R.face.parts["J1"]["fp"])
slot_ok = all(abs(max(jh[n][:2]) - JACK_SLOTS[n][0]) < 0.01 and abs(min(jh[n][:2]) - JACK_SLOTS[n][1]) < 0.01 for n in JACK_SLOTS)
ck.check("4.jack_slots_vs_Thonk", slot_ok, f"Thonk PJ398SM: {JACK_SLOTS}; footprint { {n: jh[n] for n in sorted(jh)} }")
ph = holes_of(R.face.parts["RV1"]["fp"])
lug_ok = all(abs(max(ph[n][:2]) - ALPHA_LUG_SLOT[0]) < 0.01 and abs(min(ph[n][:2]) - ALPHA_LUG_SLOT[1]) < 0.01 for n in ("4", "5"))
ck.check("4.pot_lug_slots_vs_Alpha", lug_ok, f"Alpha SLH-211-414 lug slots {ALPHA_LUG_SLOT}; footprint 4 {ph['4']}, 5 {ph['5']}")
# the BOM's notes
notes = " ".join(bom.NOTES)
stand = re.search(r"\(R21–R48, R60, R61\) stand up on a 2.54 mm footprint", notes)
lying = sorted(ref for ref in ("R60", "R61") if R.main.parts[ref]["fp"] != "RES-TH-VERTICAL-P2.54")
ck.check("4.note_standing_resistors", not (stand and lying),
         f"bom.py NOTES: '(R21–R48, R60, R61) stand up on a 2.54 mm footprint'; in the routed master {lying} lie flat on "
         f"{sorted({R.main.parts[r]['fp'] for r in lying})} (design.md: 'R60 / R61 ... lying flat')")
vert = sorted(ref for ref, pl in R.main.parts.items() if pl["fp"] == "RES-TH-VERTICAL-P2.54")
ck.check("4.standing_resistor_set", vert == sorted(f"R{k}" for k in range(21, 49)),
         f"RES-TH-VERTICAL-P2.54 on {vert[:3]}...{vert[-3:]} ({len(vert)})")
ck.check("4.note_three_holes", "Three mounting holes" in notes and holes == (3, 3), f"notes vs routed holes {holes}")

# ==========================================================================================================
# 5  the Thonk table against bom/thonk-order.csv (read only)
order_path = os.path.join(REPO, "bom", "thonk-order.csv")
with open(order_path, encoding="utf-8", newline="") as f:
    order = list(csv.DictReader(f))
col = "Orchid"
ck.check("5.thonk_order_has_Orchid", order and col in order[0], f"columns {list(order[0]) if order else None}")
orc = {r["Part"]: int(r[col]) for r in order if r.get(col, "").strip()}
mine = {}
for r in thonk:
    mh = re.match(r"(Male pin header, 2\.54 mm|Female header, 2\.54 mm, 8\.5 mm tall): (.*)", r["Part"])
    if mh:
        mine[mh.group(1) + ", pins (cut to length)"] = sum(int(n) * int(p) for n, p in re.findall(r"(\d+) × 1×(\d+)", mh.group(2)))
    else:
        mine[r["Part"]] = mine.get(r["Part"], 0) + r["Qty"]
ck.check("5.thonk_order_Orchid_column", orc == mine,
         f"only in thonk-order.csv {sorted(set(orc.items()) - set(mine.items()))}, only in this BOM "
         f"{sorted(set(mine.items()) - set(orc.items()))}")
ck.check("5.thonk_order_header_pins", orc.get("Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)") ==
         orc.get("Male pin header, 2.54 mm, pins (cut to length)") == sum(hdr_pins.values()),
         f"26 male + 26 female pins; order says {orc.get('Male pin header, 2.54 mm, pins (cut to length)')} / "
         f"{orc.get('Female header, 2.54 mm, 8.5 mm tall, pins (cut to length)')}")
ck.done()
