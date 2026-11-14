"""Netlist and pinout integrity of Marblesy (both boards, the routed master, the schematics).

What it checks
  A  circuit.py on its own: unique designators per board (R80-R85 exist on both boards on purpose),
     the R90 -> R1 renumbering, no single-pin nets, every header pin pair used on both boards, faceplate
     nets end in _F and main-board nets never, the header name exceptions (SPI_MISO / MISO_F, H5.4
     GND / GND_D_F, PROBE -> PROBE_F_1 / PROBE_F_2, 3V3D / 3V3D_F, H7.3 open), design.md's "34 pins in 7
     headers, 33 used", GND_F and GND_D_F meeting only on the main board's GND.
  B  circuit.py's pin maps against the manufacturers' pinouts (constants block below): TL074, MCP4922,
     74HC595, 74HC165, 74HC4051 (its Y0..Y7 against circuit.POTS' channels, which the firmware uses),
     LM4040-2.5 TO-92, 2N3904 TO-92, BAT85, Thonkiconn, Alpha pot, Thonk LED button (unconfirmed source),
     3 mm LEDs, the Daisy Seed pin numbering; and the same against the pin names of the symbols the
     routed master uses.
  C  Polarity of D21-D23 and D11-D17 from the symbols AND the footprints used (pin names, band, flat,
     square pad), then function: the BAT85 conducts only for a negative input and keeps the 2N3904's
     emitter-base junction inside VEBO, the LM4040's cathode on VREF, the LEDs forward when lit.
  D  The routed master (Marblesy-routed.epro2): every pad's net on both PCBs against circuit.py,
     designators complete, no foreign nets, devices against kinds / values, the footprint geometry the
     pin maps depend on (DIP numbering, TO-92 order and flat, jack spacing against KiCad's PJ398SM, the
     Alpha pot against KiCad's RD901F and clockwise in the front view, the button against parts.md, the
     Seed footprint's pin order), pin 1 = the only square pad on ICs and headers, header devices.
  E  Header stacking: the faceplate's HF pins over the main board's H pins (same frame, both PCBs drawn
     from the top layer) carry the HEADERS pair of that spot; pin order; the transform's sanity check.
  F  Schematic pages in the routed master and the generated Marbles.epro2 against circuit.py (pin
     positions joined to named wires and net flags).
  G  design.md's tables and stated wiring against circuit.py and the routed board: the Seed pin map, the
     CV input, DAC output, mux, 595/165 and header tables (nets in order and x / y ranges), part counts,
     the probe header pins, the faceplate and main-board wiring the text describes.

Run from marbles/hardware/tests:  python test_netlist.py
Only reads: imports circuit.py, opens the two exports as zip files (harness.read_export / routed()).
"""
import collections
import json
import math
import re

import harness

ck = harness.Checks("netlist")
_ASCII = {"排母": "female header ", "→": "->", "−": "-", "–": "-", "Ω": " ohm", "×": "x"}
_check = ck.check


def _check_cp1252(name, ok, detail=""):
    """Details printable on a cp1252 console (run_tests.py prints FAIL lines without forcing UTF-8)."""
    for a, b in _ASCII.items():
        detail = detail.replace(a, b)
    return _check(name, ok, detail.encode("cp1252", "replace").decode("cp1252"))


ck.check = _check_cp1252
circuit = harness.load("circuit")
MIL = harness.MIL

# ==========================================================================================================
# Datasheet pinouts and footprint references (pin numbers are exact facts: no min / typ / max)
#
# TI SLOS080W "TL07xx Low-Noise FET-Input Operational Amplifiers" (rev. July 2025), Table 4-6 Pin Functions
# TL074x, N (PDIP-14) package, top view:
TL074_DS = {"1OUT": "1", "1IN-": "2", "1IN+": "3", "VCC+": "4", "2IN+": "5", "2IN-": "6", "2OUT": "7",
            "3OUT": "8", "3IN-": "9", "3IN+": "10", "VCC-": "11", "4IN+": "12", "4IN-": "13", "4OUT": "14"}
# Microchip DS21897B "MCP4921/4922 12-Bit DAC with SPI Interface" (2007), package types (14-pin PDIP) and
# Table 3-1 Pin Function Table:
MCP4922_DS = {"VDD": "1", "NC2": "2", "CS": "3", "SCK": "4", "SDI": "5", "NC6": "6", "NC7": "7", "LDAC": "8",
              "SHDN": "9", "VOUTB": "10", "VREFB": "11", "AVSS": "12", "VREFA": "13", "VOUTA": "14"}
# TI SCLS041J "SNx4HC595 8-Bit Shift Registers With 3-State Output Registers" (rev. Oct 2021), Table 5-1
# (D, N, NS, ... packages):
HC595_DS = {"QB": "1", "QC": "2", "QD": "3", "QE": "4", "QF": "5", "QG": "6", "QH": "7", "GND": "8",
            "QH'": "9", "SRCLR": "10", "SRCLK": "11", "RCLK": "12", "OE": "13", "SER": "14", "QA": "15",
            "VCC": "16"}
HC595_Q = ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH"]
# TI SCLS116H "SNx4HC165 8-Bit Parallel-Load Shift Registers" (rev. Dec 2015), Pin Functions (D, N, ...):
# SH/LD 1, CLK 2, E 3, F 4, G 5, H 6, /QH 7, GND 8, QH 9, SER 10, A 11, B 12, C 13, D 14, CLK INH 15, VCC 16.
# Parallel inputs A..H are circuit.py's D0..D7 (H is the first bit out after a load; Table 1: SH/LD low
# loads, CLK rising edge with CLK INH low shifts towards QH).
HC165_DS = {"SH/LD": "1", "CLK": "2", "E": "3", "F": "4", "G": "5", "H": "6", "/QH": "7", "GND": "8", "QH": "9",
            "SER": "10", "A": "11", "B": "12", "C": "13", "D": "14", "CLK INH": "15", "VCC": "16"}
HC165_D = ["A", "B", "C", "D", "E", "F", "G", "H"]            # D0..D7
# TI SCHS122O "CDx4HC(T)405x" (rev. Jan 2026), Table 4-1 Pin Functions for the 4051 and Table 7-1 Function
# Table (channel = 4*S2 + 2*S1 + S0, /E low enables):
HC4051_DS = {"A4": "1", "A6": "2", "COM": "3", "A7": "4", "A5": "5", "/E": "6", "VEE": "7", "GND": "8",
             "S2": "9", "S1": "10", "S0": "11", "A3": "12", "A0": "13", "A1": "14", "A2": "15", "VCC": "16"}
HC4051_CH = {HC4051_DS[f"A{c}"]: c for c in range(8)}        # pin -> channel
# TI SNOS633N "LM4040-N Precision Micropower Shunt Voltage Reference" (rev. Aug 2025), Table 4-1 and
# Figure 4-2 (LP package, TO-92, bottom view): cathode 2, anode 3, pin 1 "*": must float or connect to the
# anode. design.md: "an older TI table" put the anode on pin 1 (that revision not retrieved: not confirmed).
LM4040_TO92 = {"K": "2", "A": "3", "*": "1"}
LM4040_TO92_OLD_ANODE = "1"
# onsemi 2N3903/D rev. 9 (Aug 2021), TO-92 CASE 29 STYLE 1: pin 1 emitter, 2 base, 3 collector; the pins
# numbered 1-2-3 left to right seen from the flat face with the leads down (the onsemi / JEDEC TO-92 drawing
# convention; the drawing itself could not be read from the PDF text: convention, not confirmed here).
Q2N3904_DS = {"E": "1", "B": "2", "C": "3"}
VEBO_2N3904 = 6.0           # V, emitter-base voltage, absolute maximum (2N3903/D, Maximum Ratings)
# KiCad Package_TO_SOT_THT TO-92_Inline.kicad_mod (gitlab.com/kicad/libraries/kicad-footprints, master,
# fetched 2026-11-12): pads 1, 2, 3 left to right, the flat (straight silk line) below them in the
# top view: pin 1 is on the left seen from the flat side.
# BAT85 (DO-35): the band marks the cathode (JEDEC DO-35 marking; Vishay's BAT85 sheet could not be fetched
# in this run: not confirmed). Forward voltage at 0.1 mA, 25 C: about 0.24 V typ (Vishay BAT85 curve,
# from memory, not confirmed); the check below uses 0.40 V, above any small-signal Schottky at 0.1 mA.
VF_BAT85_SMALL = 0.40
# 3 mm LED: the flat on the body rim marks the cathode (the short lead), every LED maker's drawing.
# KiCad LED_THT LED_D3.0mm.kicad_mod: pad 1 = cathode, square, flat silk at pad 1.
# Thonkiconn PJ398SM / QingPu WQP518MA: KiCad Connector_Audio
# Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles.kicad_mod: S (0, 0), TN (0, 3.1), T (0, 11.4), barrel
# centre (0, 6.48), mm. The TN lug touches the tip spring with no plug in (switched, normally closed).
JACK_KICAD = {"S": 0.0, "TN": 3.1, "T": 11.4, "barrel": 6.48}
# Alpha RD901F-40 single 9 mm pot: KiCad Potentiometer_Alpha_RD901F-40-00D_Single_Vertical.kicad_mod: pins 1, 2,
# 3 at (0, 0), (0, 2.5), (0, 5); shaft (fab circle centre) at (7.5, 2.5); mounting lugs at (7.5, -2.3) and
# (7.5, 7.3), pads 2.72 x 3.24 mm. Seen from the shaft side with the pins at the bottom, pins 1-2-3 run left to
# right and turning clockwise moves the wiper (2) towards 3 (Alpha / Bourns convention for rotary pots).
POT_KICAD = {"pitch": 2.5, "shaft_from_pins": 7.5, "lug_half_span": 4.8, "lug_pad": (2.72, 3.24)}
# Thonk low-profile LED button: Thonk's LowProfileButton.pdf / SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod as
# recorded in .claude/skills/module-design/references/parts.md -- NOT confirmed in this run (Thonk's site blocks
# fetches, no public copy): pins (top view, y up) 1 (2.54, 2.54), 2 (-2.54, 2.54), 3 (2.54, -2.54),
# 4 (-2.54, -2.54); contacts 1+2 and 3+4; LED anode L1 = pin 5 (2.7, 0), cathode L2 = pin 6 (-2.7, 0). Which way
# round the bipolar one lights red is not documented anywhere (design.md open item).
BUTTON_DS = {"contact_a": {"1", "2"}, "contact_b": {"3", "4"}, "LED_A": "5", "LED_K": "6"}
BUTTON_XY = {"1": (2.54, 2.54), "2": (-2.54, 2.54), "3": (2.54, -2.54), "4": (-2.54, -2.54), "5": (2.7, 0.0),
             "6": (-2.7, 0.0)}
# Electrosmith "Daisy Seed datasheet" v1.0.5, Table 2 (Pin Functions) and Table 3: pin -> Daisy name (STM32 pin).
# The physical order (1-20 down one side from the USB end, 21-40 back up the other, pin 1 and 40 at the USB
# end, pin 1 on the left seen from the top with the USB up) is from Electrosmith's pinout drawing (not
# readable as text: not confirmed beyond Table 2's numbering).
SEED_DS = {"1": "D0", "2": "D1", "3": "D2", "4": "D3", "5": "D4", "6": "D5", "7": "D6", "8": "D7", "9": "D8",
           "10": "D9", "11": "D10", "12": "D11", "13": "D12", "14": "D13", "15": "D14",
           "16": "AUDIO IN L", "17": "AUDIO IN R", "18": "AUDIO OUT L", "19": "AUDIO OUT R", "20": "AGND",
           "21": "+3V3A", "22": "A0, D15", "23": "A1, D16", "24": "A2, D17", "25": "A3, D18", "26": "A4, D19",
           "27": "A5, D20", "28": "A6, D21", "29": "A7, D22", "30": "A8, D23", "31": "A9, D24", "32": "A10, D25",
           "33": "D26", "34": "D27", "35": "A11, D28", "36": "D29", "37": "D30", "38": "+3V3D", "39": "VIN",
           "40": "GND"}
# circuit.py's libDaisy names for the non-GPIO pins against the datasheet's
SEED_ALIASES = {"AIN1": "AUDIO IN L", "AIN2": "AUDIO IN R", "AOUT1": "AUDIO OUT L", "AOUT2": "AUDIO OUT R",
                "AGND": "AGND", "3V3A": "+3V3A", "3V3D": "+3V3D", "VIN": "VIN", "DGND": "GND"}
# Rob Heel's seed_power_opamps breakout (brief / its BOM 2025-08-29): J1 = GND, -12 V x3; J3 = GND, +12 V x3.
BREAKOUT_DS = {"J1-1": "GND", "J1-2": "-12V", "J1-3": "-12V", "J1-4": "-12V",
               "J3-1": "GND", "J3-2": "+12V", "J3-3": "+12V", "J3-4": "+12V"}

# design.md's names for the nets that do not follow "X -> X_F" across the headers (Board-to-board headers)
HEADER_EXCEPTIONS = {("H5", 1): ("SPI_MISO", "MISO_F"), ("H5", 2): ("SPI_SCK", "SCK_F"),
                     ("H5", 4): ("GND", "GND_D_F"), ("H7", 1): ("SPI_MOSI", "MOSI_F"),
                     ("H3", 3): ("PROBE", "PROBE_F_2"), ("H6", 3): ("PROBE", "PROBE_F_1"),
                     ("H6", 1): ("3V3D", "3V3D_F"), ("H7", 3): (None, None)}


# ==========================================================================================================
# A  circuit.py on its own
MB, FB = circuit.main_board_parts(), circuit.faceplate_parts()
MBN, FBN = circuit.nets_of(MB), circuit.nets_of(FB)
PARTS = {"main": {p.ref: p for p in MB}, "face": {p.ref: p for p in FB}}
NETS = {"main": MBN, "face": FBN}

for name, parts in (("main", MB), ("face", FB)):
    dup = [r for r, n in collections.Counter(p.ref for p in parts).items() if n > 1]
    ck.check(f"A.unique_refs.{name}", not dup, f"expected no duplicate designators, got {dup}")
    nets = circuit.nets_of(parts)
    single = {n: v for n, v in nets.items() if len(v) < 2}
    ck.check(f"A.no_single_pin_nets.{name}", not single, f"expected every net on >= 2 pins, got {single}")

both = sorted(set(PARTS["main"]) & set(PARTS["face"]), key=lambda r: (r.rstrip("0123456789"), int(r[1:]) if r[1:].isdigit() else 0))
ck.check("A.refs_on_both_boards_R80_R85", both == [f"R{n}" for n in range(80, 86)],
         f"design.md: R80-R85 exist on both boards; designators on both: {both}")
r8x_bad = []
for n in range(80, 86):
    m, f = PARTS["main"].get(f"R{n}"), PARTS["face"].get(f"R{n}")
    if not m or not (any(v.startswith(("DAC_", "IN_", "OA_", "NEG_REF")) for v in m.nets.values())
                     and m.value in ("23k2", "47k", "100k", "1k")):
        r8x_bad.append(("main", f"R{n}", m and (m.value, m.nets)))
    if not f or not (f.value == "470" and any(v.startswith("L_D") for v in f.nets.values())):
        r8x_bad.append(("face", f"R{n}", f and (f.value, f.nets)))
ck.check("A.R80_R85_roles", not r8x_bad,
         f"main R80-R85 = DAC output stage resistors, faceplate R80-R85 = 470R LED resistors; bad {r8x_bad}")
r1 = PARTS["face"].get("R1")
ck.check("A.renumbered_R90_is_R1", "R90" not in PARTS["face"] and r1 is not None and r1.value == "470"
         and set(r1.nets.values()) == {"L_D17_G", "LED_D17_G"},
         f"circuit.RENUMBERED R90 -> R1: R1 the 470 of D17 (X3 output LED); R90 present: "
         f"{'R90' in PARTS['face']}, R1 {r1 and (r1.value, r1.nets)}")

pair_bad = []
for ref, kind, pins in circuit.HEADERS:
    for i, (a, b) in enumerate(pins):
        want = HEADER_EXCEPTIONS.get((ref, i + 1))
        if want is None:
            want = (a, {"GND": "GND_F"}.get(a, f"{a}_F" if a else None))
        if (a, b) != want:
            pair_bad.append((ref, i + 1, (a, b), "expected", want))
        if a and (len(MBN[a]) < 2 or len(FBN[b]) < 2):
            pair_bad.append((ref, i + 1, a, b, "pins", len(MBN[a]), len(FBN[b])))
ck.check("A.header_pairs_named_and_used_both_boards", not pair_bad,
         f"every header pin X / X_F (design.md's exceptions: MISO_F, SCK_F, MOSI_F, GND_D_F at H5.4, PROBE_F_2 at "
         f"H3.3, PROBE_F_1 at H6.3, H7.3 open) on >= 2 pins of each board; bad {pair_bad}")
# circuit.py's docstring: nets that cross the headers carry _F on the faceplate; the faceplate-only nets are the
# 595 lines (L_*), the LED nets after their resistors (LED_*), the clock jacks' switch lugs (TN_*) and the 595 chain
fb_hdr = {n for n in FBN if any(pin.startswith("HF") for pin in FBN[n])}
fb_bad = sorted(n for n in fb_hdr if not n.endswith("_F") and not n.endswith(("_F_1", "_F_2")))
fb_bad += sorted(n for n in set(FBN) - fb_hdr if not n.endswith("_F")
                 and not (n.startswith(("L_D", "LED_D", "TN_")) or n == "SR_CHAIN"))
mb_bad = sorted(n for n in MBN if n.endswith("_F") or "_F_" in n)
ck.check("A.faceplate_nets_end_in_F", not fb_bad,
         f"expected every faceplate net on a header pin *_F (PROBE_F_1/_2 allowed) and the faceplate-only ones of "
         f"circuit.py's naming list (L_*, LED_*, TN_*, SR_CHAIN); got {fb_bad}")
ck.check("A.main_nets_never_F", not mb_bad, f"expected no main-board net *_F, got {mb_bad}")
shared = sorted(set(MBN) & set(FBN))
ck.check("A.no_net_on_both_boards", not shared, f"expected no net name on both boards, got {shared}")
hdr_mb = {a for _, _, pins in circuit.HEADERS for a, b in pins if a}
hdr_fb = {b for _, _, pins in circuit.HEADERS for a, b in pins if b}
named_pairs = sorted(n[:-2] for n in FBN if n.endswith("_F") and n[:-2] in MBN and n[:-2] not in hdr_mb)
ck.check("A.cross_board_names_only_via_headers", not named_pairs,
         f"X / X_F pairs on the two boards with no header pin joining them: {named_pairs}")
hdr_ok = all(PARTS["main"][ref].nets == {str(i + 1): a for i, (a, b) in enumerate(pins) if a} and
             PARTS["face"][circuit.fb_ref(ref)].nets == {str(i + 1): b for i, (a, b) in enumerate(pins) if b}
             for ref, _, pins in circuit.HEADERS)
ck.check("A.header_parts_match_HEADERS", hdr_ok, "H<n> / HF<n> pin nets equal circuit.HEADERS on both boards")
n_pins = sum(len(p) for _, _, p in circuit.HEADERS)
n_used = sum(1 for _, _, p in circuit.HEADERS for a, b in p if a)
m = re.search(r"(\d+) pins in (\d+) headers, (\d+) used", harness.text("docs", "design.md"))
ck.check("A.header_pin_count_design_md", bool(m) and (int(m.group(1)), int(m.group(2)), int(m.group(3)))
         == (n_pins, len(circuit.HEADERS), n_used),
         f"design.md '{m.group(0) if m else None}'; circuit.HEADERS: {n_pins} pins in {len(circuit.HEADERS)} headers, "
         f"{n_used} used")
h7 = dict(enumerate({ref: pins for ref, _, pins in circuit.HEADERS}["H7"], 1))
ck.check("A.H7_3_open", h7.get(3) == (None, None) and "3" not in PARTS["main"]["H7"].nets
         and "3" not in PARTS["face"]["HF7"].nets, f"design.md: H7 pin 3 open on both boards; got {h7.get(3)}")
# the two faceplate grounds: separate on the faceplate, joined only through header pins onto the main GND
gnd_f_pins = sorted(f"{r}.{i + 1}" for r, _, p in circuit.HEADERS for i, (a, b) in enumerate(p) if b == "GND_F")
gnd_d_pins = sorted(f"{r}.{i + 1}" for r, _, p in circuit.HEADERS for i, (a, b) in enumerate(p) if b == "GND_D_F")
gnd_main = {a for r, _, p in circuit.HEADERS for a, b in p if b in ("GND_F", "GND_D_F")}
bridge = [p.ref for p in FB if {"GND_F", "GND_D_F"} <= set(p.nets.values()) and not p.ref.startswith("HF")]
ck.check("A.GND_F_GND_D_F_meet_only_on_main_GND",
         gnd_f_pins == ["H3.2", "H6.2", "H7.4"] and gnd_d_pins == ["H5.4"] and gnd_main == {"GND"} and not bridge,
         f"design.md: GND_F through H3.2, H6.2, H7.4, GND_D_F through H5.4, both GND on the main board, no faceplate "
         f"part between them; got GND_F {gnd_f_pins}, GND_D_F {gnd_d_pins}, main side {gnd_main}, bridging parts "
         f"{bridge}")
probe = [(r, i + 1, a, b) for r, _, p in circuit.HEADERS for i, (a, b) in enumerate(p) if b and b.startswith("PROBE")]
ck.check("A.PROBE_pins_join_on_main", sorted(probe) == [("H3", 3, "PROBE", "PROBE_F_2"), ("H6", 3, "PROBE", "PROBE_F_1")]
         and "PROBE" in [n for _, n in circuit.SEED.values()],
         f"design.md: the two PROBE pins join on the main board (Seed's PROBE); got {probe}")

# ==========================================================================================================
# B  pin maps against the datasheets (circuit.py), then against the routed symbols' pin names
R = harness.routed()


def symbol_of(board, ref):
    return R.device(board, ref).get("Symbol")


def sym_pins(board, ref):
    """{pin number: pin name} of the symbol the routed part was placed from."""
    s = symbol_of(board, ref)
    return {n: v[0] for n, v in R.symbol_pins(s).items()} if s in R.docs else {}


sec_ds = {s: (TL074_DS[f"{s}OUT"], TL074_DS[f"{s}IN-"], TL074_DS[f"{s}IN+"]) for s in (1, 2, 3, 4)}
ck.check("B.TL074_SECTION", circuit.SECTION == sec_ds, f"expected {sec_ds}, got {circuit.SECTION}")
for u in ("U3", "U4", "U5", "U6"):
    n = PARTS["main"][u].nets
    ck.check(f"B.TL074_supply.{u}", n.get(TL074_DS["VCC+"]) == "+12V" and n.get(TL074_DS["VCC-"]) == "-12V",
             f"expected pin 4 +12V, pin 11 -12V; got 4={n.get('4')}, 11={n.get('11')}")
    ck.check(f"B.TL074_all_pins_used.{u}", set(n) == set(TL074_DS.values()), f"pins {sorted(n, key=int)}")
# symbol pin names of the routed TL074 (named OUT1 / IN1- / IN1+ / VCC / GND ...) against SLOS080's functions
TL_SYM_OK = {"1OUT": {"OUT1", "1OUT", "OUTA"}, "1IN-": {"IN1-", "1IN-"}, "1IN+": {"IN1+", "1IN+"},
             "2OUT": {"OUT2", "2OUT"}, "2IN-": {"IN2-", "2IN-"}, "2IN+": {"IN2+", "2IN+"},
             "3OUT": {"OUT3", "3OUT"}, "3IN-": {"IN3-", "3IN-"}, "3IN+": {"IN3+", "3IN+"},
             "4OUT": {"OUT4", "4OUT"}, "4IN-": {"IN4-", "4IN-"}, "4IN+": {"IN4+", "4IN+"},
             "VCC+": {"VCC", "VCC+", "V+"}, "VCC-": {"VCC-", "V-", "VEE", "VSS"}}
tl_sym = sym_pins("main", "U3")
tl_bad = [(f, pin, tl_sym.get(pin)) for f, pin in TL074_DS.items() if tl_sym.get(pin) not in TL_SYM_OK[f]]
ck.check("B.TL074_symbol_pin_names", not tl_bad,
         f"routed TL074ACN symbol: function, pin, symbol name not matching SLOS080 {tl_bad} (pin numbers are what the "
         f"board follows; a negative supply named 'GND' misleads anyone reading the schematic, where pin 11 is tied "
         f"to -12V)")

for u, cs in (("U7", "DAC_CS1"), ("U8", "DAC_CS2")):
    n = PARTS["main"][u].nets
    want = {MCP4922_DS["VDD"]: "3V3A", MCP4922_DS["CS"]: cs, MCP4922_DS["SCK"]: "SPI_SCK",
            MCP4922_DS["SDI"]: "SPI_MOSI", MCP4922_DS["LDAC"]: "DAC_LDAC", MCP4922_DS["SHDN"]: "3V3A",
            MCP4922_DS["VREFB"]: "VREF", MCP4922_DS["AVSS"]: "GND", MCP4922_DS["VREFA"]: "VREF"}
    bad = {p: (n.get(p), w) for p, w in want.items() if n.get(p) != w}
    nc = [p for p in (MCP4922_DS["NC2"], MCP4922_DS["NC6"], MCP4922_DS["NC7"]) if p in n]
    outs = (n.get(MCP4922_DS["VOUTA"]), n.get(MCP4922_DS["VOUTB"]))
    ck.check(f"B.MCP4922_pins.{u}", not bad and not nc and all(o and o.startswith("DAC_") for o in outs),
             f"DS21897B: VDD 1, CS 3, SCK 4, SDI 5, LDAC 8, SHDN 9 (high = on), VOUTB 10, VREFB 11, AVSS 12, VREFA 13, "
             f"VOUTA 14, NC 2/6/7; wrong {bad}, NC pins wired {nc}, outputs {outs}")
mcp_sym = sym_pins("main", "U7")
SYM_NAME = {"VDD": "VDD", "NC2": "NC", "CS": "/CS", "SCK": "SCK", "SDI": "SDI", "NC6": "NC", "NC7": "NC",
            "LDAC": "/LDAC", "SHDN": "/SHDN", "VOUTB": "VOUTB", "VREFB": "VREFB", "AVSS": "AVSS", "VREFA": "VREFA",
            "VOUTA": "VOUTA"}
bad = [(f, p, mcp_sym.get(p)) for f, p in MCP4922_DS.items() if mcp_sym.get(p) != SYM_NAME[f]]
ck.check("B.MCP4922_symbol_pin_names", not bad, f"routed MCP4922 symbol against DS21897B Table 3-1: {bad}")

for u in ("U9", "U10"):
    n = PARTS["face"][u].nets
    want = {HC595_DS["SRCLK"]: "SCK_F", HC595_DS["RCLK"]: "LED_LATCH_F", HC595_DS["SRCLR"]: "3V3D_F",
            HC595_DS["OE"]: "GND_D_F", HC595_DS["VCC"]: "3V3D_F", HC595_DS["GND"]: "GND_D_F"}
    bad = {p: (n.get(p), w) for p, w in want.items() if n.get(p) != w}
    outs = {q: n.get(HC595_DS[q]) for q in HC595_Q}
    ck.check(f"B.HC595_pins.{u}", not bad and all(v is None or v.startswith("L_D") for v in outs.values()),
             f"SCLS041J: SRCLK 11 = SCK_F, RCLK 12 = LED_LATCH_F, /SRCLR 10 high, /OE 13 low, VCC 16, GND 8; QA 15, "
             f"QB-QH 1-7 drive L_ lines; wrong {bad}, outputs {outs}")
u9, u10 = PARTS["face"]["U9"].nets, PARTS["face"]["U10"].nets
ck.check("B.HC595_chain", u9.get(HC595_DS["SER"]) == "MOSI_F" and u9.get(HC595_DS["QH'"]) == u10.get(HC595_DS["SER"])
         and u10.get(HC595_DS["SER"]) not in (None, "MOSI_F") and HC595_DS["QH'"] not in u10,
         f"U9 SER (14) = MOSI_F, U9 QH' (9) -> U10 SER (14), U10 QH' open; got U9 SER {u9.get('14')}, U9 QH' "
         f"{u9.get('9')}, U10 SER {u10.get('14')}, U10 QH' {u10.get('9')}")
SYM595 = {"QB": "QB", "QC": "QC", "QD": "QD", "QE": "QE", "QF": "QF", "QG": "QG", "QH": "QH", "GND": "GND",
          "QH'": "QH'", "SRCLR": "/SRCLR", "SRCLK": "SRCLK", "RCLK": "RCLK", "OE": "/OE", "SER": "SER", "QA": "QA",
          "VCC": "VCC"}
s595 = sym_pins("face", "U9")
bad = [(f, p, s595.get(p)) for f, p in HC595_DS.items() if s595.get(p) != SYM595[f]]
ck.check("B.HC595_symbol_pin_names", not bad, f"routed 74HC595 symbol against SCLS041J Table 5-1: {bad}")

u11 = PARTS["face"]["U11"].nets
want = {HC165_DS["SH/LD"]: "BTN_LOAD_F", HC165_DS["CLK"]: "SCK_F", HC165_DS["CLK INH"]: "GND_D_F",
        HC165_DS["SER"]: "GND_D_F", HC165_DS["QH"]: "MISO_F", HC165_DS["VCC"]: "3V3D_F", HC165_DS["GND"]: "GND_D_F",
        HC165_DS["H"]: "GND_D_F"}
bad = {p: (u11.get(p), w) for p, w in want.items() if u11.get(p) != w}
btn_in = [u11.get(HC165_DS[d]) for d in HC165_D[:7]]
ck.check("B.HC165_pins", not bad and HC165_DS["/QH"] not in u11 and btn_in == [f"BTN_{s}_F" for _, _, s in circuit.BUTTONS],
         f"SCLS116H: SH/LD 1 = BTN_LOAD_F, CLK 2 = SCK_F, CLK INH 15 low, SER 10 low, QH 9 = MISO_F, /QH 7 open, H (6) "
         f"tied low, A..G = the seven buttons in BUTTONS order; wrong {bad}, A..G {btn_in}")
ck.check("B.HC165_INPUTS_vs_DS", circuit.HC165_INPUTS == [HC165_DS[d] for d in HC165_D],
         f"circuit.HC165_INPUTS (D0..D7) {circuit.HC165_INPUTS} against SCLS116H A..H {[HC165_DS[d] for d in HC165_D]}")
SYM165 = {"SH/LD": "/PL", "CLK": "CP", "E": "D4", "F": "D5", "G": "D6", "H": "D7", "/QH": "/Q7", "GND": "GND",
          "QH": "Q7", "SER": "DS", "A": "D0", "B": "D1", "C": "D2", "D": "D3", "CLK INH": "CE", "VCC": "VCC"}
s165 = sym_pins("face", "U11")
bad = [(f, p, s165.get(p)) for f, p in HC165_DS.items() if s165.get(p) != SYM165[f]]
ck.check("B.HC165_symbol_pin_names", not bad, f"routed 74HC165 symbol (Nexperia names) against SCLS116H: {bad}")

u1 = PARTS["face"]["U1"].nets
want = {HC4051_DS["COM"]: "MUX_OUT_F", HC4051_DS["S0"]: "MUX_S0_F", HC4051_DS["S1"]: "MUX_S1_F",
        HC4051_DS["S2"]: "MUX_S2_F", HC4051_DS["/E"]: "GND_F", HC4051_DS["VEE"]: "GND_F", HC4051_DS["GND"]: "GND_F",
        HC4051_DS["VCC"]: "3V3A_F"}
bad = {p: (u1.get(p), w) for p, w in want.items() if u1.get(p) != w}
ck.check("B.HC4051_pins", not bad, f"SCHS122O: COM 3, S0 11 / S1 10 / S2 9, /E 6 low, VEE 7 and GND 8 at 0 V, VCC 16 "
                                   f"on 3V3A_F; wrong {bad}")
ch_bad = [(ref, label, mpin, ch, HC4051_CH.get(mpin), u1.get(mpin), wiper) for ref, label, wiper, mpin, ch in circuit.POTS
          if HC4051_CH.get(mpin) != ch or u1.get(mpin) != wiper or PARTS["face"][ref].nets.get("2") != wiper]
ck.check("B.HC4051_channels_vs_POTS", not ch_bad and sorted(ch for *_, ch in circuit.POTS) == list(range(8)),
         f"each pot's 4051 pin is channel Y<ch> per SCHS122O (A0 13, A1 14, A2 15, A3 12, A4 1, A5 5, A6 2, A7 4) and "
         f"carries its wiper; bad {ch_bad}")
SYM4051 = {"A4": "Y4", "A6": "Y6", "COM": "Z", "A7": "Y7", "A5": "Y5", "/E": "/E", "VEE": "VEE", "GND": "GND",
           "S2": "S2", "S1": "S1", "S0": "S0", "A3": "Y3", "A0": "Y0", "A1": "Y1", "A2": "Y2", "VCC": "VCC"}
s4051 = sym_pins("face", "U1")
bad = [(f, p, s4051.get(p)) for f, p in HC4051_DS.items() if s4051.get(p) != SYM4051[f]]
ck.check("B.HC4051_symbol_pin_names", not bad, f"routed 74HC4051 symbol (Nexperia names) against SCHS122O: {bad}")

d21 = PARTS["main"]["D21"].nets
cases = {"TI SNOS633N": LM4040_TO92["A"], "older TI table": LM4040_TO92_OLD_ANODE}
fit = {k: d21.get(LM4040_TO92["K"]) == "VREF" and d21.get(a) == "GND" for k, a in cases.items()}
star_ok = d21.get(LM4040_TO92["*"]) in (None, d21.get(LM4040_TO92["A"]))
# turned round in its pads (pin 1 in pad 3, pin 3 in pad 1): the cathode stays in pad 2
rev = {"1": d21.get("3"), "2": d21.get("2"), "3": d21.get("1")}
fit_rev = rev.get(LM4040_TO92["K"]) == "VREF" and rev.get(LM4040_TO92["A"]) == "GND"
ck.check("B.LM4040_TO92_either_pinout", all(fit.values()) and star_ok and fit_rev,
         f"design.md: pads 1 and 3 both GND, cathode pad 2 = VREF, so the part fits TI's current drawing (anode 3, "
         f"pin 1 '*' must float or go to the anode), the older table (anode 1) and either way round; D21 {d21}, fits "
         f"{fit}, '*' pin ok {star_ok}, reversed ok {fit_rev}")
s21 = sym_pins("main", "D21")
ck.check("B.LM4040_symbol_pins", s21.get(LM4040_TO92["K"]) == "K" and s21.get(LM4040_TO92["A"]) == "A",
         f"routed LM4040 symbol: K on pin {LM4040_TO92['K']}, A on pin {LM4040_TO92['A']} (SNOS633N); got {s21}")
for q, b, c in (("Q1", "B_T_CLK", "T_CLK"), ("Q2", "B_X_CLK", "X_CLK")):
    n = PARTS["main"][q].nets
    ck.check(f"B.2N3904_pins.{q}", n.get(Q2N3904_DS["E"]) == "GND" and n.get(Q2N3904_DS["B"]) == b
             and n.get(Q2N3904_DS["C"]) == c,
             f"2N3903/D TO-92 style 1: 1 E = GND, 2 B = {b}, 3 C = {c}; got {n}")
sq = sym_pins("main", "Q1")
ck.check("B.2N3904_symbol_pins", {sq.get(p) for p in "123"} == {"E", "B", "C"}
         and all(sq.get(p) == f for f, p in Q2N3904_DS.items()), f"routed 2N3904 symbol {sq} against E 1, B 2, C 3")
for d, b in (("D22", "B_T_CLK"), ("D23", "B_X_CLK")):
    n = PARTS["main"][d].nets
    ck.check(f"B.BAT85_pins.{d}", n == {"1": b, "2": "GND"}, f"pin 1 cathode on the base node {b}, pin 2 anode GND; got {n}")

jack_bad = []
for ref, label, tip, tn in circuit.JACKS:
    n = PARTS["face"][ref].nets
    if n.get("1") != "GND_F" or n.get("3") != tip or n.get("2") != tn:
        jack_bad.append((ref, n))
ck.check("B.jacks_S_TN_T", not jack_bad, f"design.md: pads 1 = sleeve GND_F, 2 = switch lug, 3 = tip; bad {jack_bad}")
norm = {ref: tn for ref, _, _, tn in circuit.JACKS}
cv_in = [ref for ref, label, tip, tn in circuit.JACKS if tip.startswith("CV_")]
outs = [ref for ref, label, tip, tn in circuit.JACKS if tip[:-2] in ("T1", "T2", "T3", "X1", "X2", "X3", "Y")]
r9, r10 = PARTS["face"]["R9"], PARTS["face"]["R10"]
ck.check("B.jack_normalling", all(norm[r] == "GND_F" for r in cv_in) and all(norm[r] is None for r in outs)
         and norm["J1"] == "TN_TCLK" and norm["J12"] == "TN_XCLK"
         and set(r9.nets.values()) == {"TN_TCLK", "PROBE_F_2"} and set(r10.nets.values()) == {"TN_XCLK", "PROBE_F_1"}
         and r9.value == r10.value == "10k" and len(cv_in) == 7 and len(outs) == 7,
         f"design.md: CV lugs to GND_F, clock lugs through R9 / R10 10k to PROBE_F_2 (T) / PROBE_F_1 (X), outputs "
         f"open; got {norm}, R9 {r9.nets}, R10 {r10.nets}")
pot_bad = [(ref, PARTS["face"][ref].nets) for ref, *_ in circuit.POTS
           if PARTS["face"][ref].nets != {"1": "GND_F", "2": [w for r2, _, w, _, _ in circuit.POTS if r2 == ref][0],
                                          "3": "3V3A_F", "4": "GND_F", "5": "GND_F"} or PARTS["face"][ref].value != "B10k"]
ck.check("B.pots_CW_to_3V3A", not pot_bad,
         f"Alpha pot: 1 CCW = GND_F, 2 wiper, 3 CW = 3V3A_F (clockwise raises the reading), lugs 4 / 5 GND_F, B10k; "
         f"bad {pot_bad}")
btn_bad = []
for ref, label, sw in circuit.BUTTONS:
    n = PARTS["face"][ref].nets
    if {n[p] for p in BUTTON_DS["contact_a"]} != {"GND_D_F"} or {n[p] for p in BUTTON_DS["contact_b"]} != {f"BTN_{sw}_F"}:
        btn_bad.append((ref, n))
ck.check("B.buttons_contacts", not btn_bad, f"parts.md (unconfirmed): contacts 1+2 = GND_D_F, 3+4 = the input; bad {btn_bad}")
led_btn_bad = []
for sw, d in circuit.LED_BUTTONS.items():
    n = PARTS["face"][sw].nets
    kind = [k for r, _, k, _ in circuit.LEDS if r == d][0]
    if kind == "G" and not (n["5"] == f"LED_{d}_G" and n["6"] == "GND_D_F"):
        led_btn_bad.append((sw, d, n["5"], n["6"]))
    if kind == "RG" and not (n["5"] == f"LED_{d}_R" and n["6"] == f"L_{d}_G"):
        led_btn_bad.append((sw, d, n["5"], n["6"]))
ck.check("B.button_LED_pins", not led_btn_bad,
         f"parts.md (unconfirmed): LED anode 5 (through the 470 for the green ones), cathode 6 = GND_D_F; bipolar: 5 = "
         f"red line through its 470, 6 = green line; bad {led_btn_bad}")
sg, srg = sym_pins("face", "SW1"), sym_pins("face", "SW2")
ck.check("B.button_symbol_pins", sg.get("5") == "LED A" and sg.get("6") == "LED K" and srg.get("5") == "LED R"
         and srg.get("6") == "LED G",
         f"routed symbols: green button LED A 5 / LED K 6; bipolar LED R 5 / LED G 6 (red when 5 is the higher, the "
         f"firmware's assumption; the part's die orientation is unconfirmed); got {sg}, {srg}")
led_bad = [(r, PARTS["face"][r].nets) for r in ("D11", "D12", "D13", "D14", "D15", "D16", "D17")
           if not (PARTS["face"][r].nets.get("1", "").startswith("LED_") and
                   PARTS["face"][r].nets.get("2") in ("GND_F", "GND_D_F"))]
ck.check("B.LED_pins", not led_bad, f"3 mm LEDs: pin 1 anode (from the resistor), pin 2 cathode to ground; bad {led_bad}")

# Daisy Seed: circuit.SEED's libDaisy names against Electrosmith's Table 2
seed_bad = []
for pin in [str(i) for i in range(1, 41)]:
    name = circuit.SEED[pin][0]
    ds = SEED_DS[pin]
    ds_names = {t.strip() for t in ds.split(",")}
    mine = set(name.split("/"))
    if name in SEED_ALIASES:
        ok = SEED_ALIASES[name] == ds
    else:
        ok = mine == ds_names
    if not ok:
        seed_bad.append((pin, name, ds))
ck.check("B.Seed_pin_names_vs_datasheet", not seed_bad and len(circuit.SEED) == 56,
         f"circuit.SEED pins 1-40 against the Daisy Seed datasheet v1.0.5 Table 2 (D0..D30, A0..A11, 20 AGND, "
         f"21 3V3A, 38 3V3D, 39 VIN, 40 DGND); bad {seed_bad}")
pw = {p: circuit.SEED[p][1] for p in ("20", "21", "38", "39", "40")}
ck.check("B.Seed_power_pins", pw == {"20": "GND", "21": "3V3A", "38": "3V3D", "39": None, "40": "GND"},
         f"AGND (20) and DGND (40) on GND, 3V3A (21) and 3V3D (38) are the Seed's outputs, VIN (39) left to the "
         f"breakout's DC/DC; got {pw}")
br = {p: circuit.SEED[p][1] for p in BREAKOUT_DS}
ck.check("B.breakout_power_headers", br == BREAKOUT_DS, f"J1 GND, -12V x3; J3 GND, +12V x3 (seed_power_opamps BOM); got {br}")
u2s = sym_pins("main", "U2")
bad = [(p, n, u2s.get(p)) for p, (n, _) in circuit.SEED.items() if u2s.get(p) != n]
ck.check("B.Seed_symbol_pin_names", not bad, f"routed U2 symbol pin names against circuit.SEED: {bad}")

# ==========================================================================================================
# Export parsing (own code on harness.read_export's records)


def doc_meta(doc):
    return next((p for h, p in doc["recs"] if h["type"] == "META"), {})


def _path_pts(path):
    pts, i = [], 0
    while i < len(path):
        if path[i] == "L":
            i += 1
            continue
        if isinstance(path[i], str):            # ARC: sweep, x, y
            pts.append((path[i + 2] * MIL, path[i + 3] * MIL))
            i += 4
            continue
        pts.append((path[i] * MIL, path[i + 1] * MIL))
        i += 2
    return pts


class Export:
    def __init__(self, path):
        self.path = path
        self.docs = harness.read_export(path)
        self.devices = {u: doc_meta(d).get("attributes", {}) for u, d in self.docs.items() if d["docType"] == "DEVICE"}
        self.boards = {u: doc_meta(d).get("title") for u, d in self.docs.items() if d["docType"] == "BOARD"}

    def of_type(self, t):
        return {u: d for u, d in self.docs.items() if d["docType"] == t}

    def footprint_pads(self, uid):
        """{num: (x mm, y mm, padType)} of a FOOTPRINT doc (deleted records skipped)."""
        return {str(p["num"]): (p["centerX"] * MIL, p["centerY"] * MIL, p["defaultPad"]["padType"])
                for h, p in self.docs[uid]["recs"] if h["type"] == "PAD" and p}

    def footprint_silk(self, uid, layers=(3,)):
        """Silk straight segments [(x1, y1, x2, y2)] and circles [(cx, cy, r)] on the given layers, mm."""
        segs, circles = [], []
        for h, p in self.docs[uid]["recs"]:
            if h["type"] != "POLY" or not p or p.get("layerId") not in layers:
                continue
            path = p["path"]
            if path and path[0] == "CIRCLE":
                circles.append((path[1] * MIL, path[2] * MIL, path[3] * MIL))
            elif path and not isinstance(path[0], str) and "ARC" not in path:
                pts = _path_pts(path)
                segs += [(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
        return segs, circles

    def symbol_pins(self, uid):
        pins, out = {}, {}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "PIN" and p:
                pins[h["id"]] = {"x": p["x"], "y": p["y"], "part": p.get("partId")}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "ATTR" and p and p.get("parentId") in pins:
                pins[p["parentId"]][p["key"]] = p["value"]
        for pid, q in pins.items():
            out[q.get("Pin Number")] = (q.get("Pin Name"), q["x"], q["y"], q["part"])
        return out


ROUTED = Export(harness.ROUTED)


def fp_uid(board, ref):
    return R.attrs(board, ref).get("Footprint")


def fp_pads(board, ref):
    return ROUTED.footprint_pads(fp_uid(board, ref))


def to_board(part, lx, ly):
    """Board position of a footprint-local point: bottom layer mirrors y, then rotate (easyeda-format.md)."""
    if part["bottom"]:
        ly = -ly
    a = math.radians(part["angle"])
    return part["x"] + lx * math.cos(a) - ly * math.sin(a), part["y"] + lx * math.sin(a) + ly * math.cos(a)


# ==========================================================================================================
# C  diodes and LEDs: symbol, footprint marking, function
def cathode_pin_symbol(board, ref):
    pins = sym_pins(board, ref)
    k = [n for n, name in pins.items() if name in ("C", "K", "Cathode", "CATHODE", "LED K")]
    a = [n for n, name in pins.items() if name in ("A", "Anode", "ANODE", "LED A")]
    return (k[0] if len(k) == 1 else None), (a[0] if len(a) == 1 else None), pins


def band_pad(uid):
    """DO-35: the pad on the band side (a silk line across the body strictly inside its two ends)."""
    pads = ROUTED.footprint_pads(uid)
    segs, _ = ROUTED.footprint_silk(uid)
    across = sorted({round(s[0], 3) for s in segs if abs(s[0] - s[2]) < 0.01 and abs(s[1] - s[3]) > 1.0})
    ends = [x for x in across if any(abs(x + y) < 0.02 for y in across) and x > 0]
    end = max(ends) if ends else 0
    inner = [x for x in across if abs(x) < end - 0.05 and not any(abs(x + y) < 0.02 for y in across)]
    if len(inner) != 1:
        return None, across
    x = inner[0]
    return min(pads, key=lambda n: abs(pads[n][0] - x)), across


def flat_pad(uid):
    """3 mm LED: the pad on the side of the straight silk line that cuts the body circle (the flat)."""
    pads = ROUTED.footprint_pads(uid)
    segs, circles = ROUTED.footprint_silk(uid)
    if len(circles) != 1:
        return None
    cx, cy, r = circles[0]
    flats = [s for s in segs if abs(math.hypot((s[0] + s[2]) / 2 - cx, (s[1] + s[3]) / 2 - cy) - r) < 0.15]
    if len(flats) != 1:
        return None
    mx, my = (flats[0][0] + flats[0][2]) / 2, (flats[0][1] + flats[0][3]) / 2
    return min(pads, key=lambda n: math.hypot(pads[n][0] - mx, pads[n][1] - my))


for ref in ("D22", "D23"):
    k, a, pins = cathode_pin_symbol("main", ref)
    band, xs = band_pad(fp_uid("main", ref))
    ck.check(f"C.{ref}.symbol_cathode_pin", (k, a) == ("1", "2"),
             f"BAT85 symbol: pin named C = {k}, A = {a} (circuit.py: 1 = cathode); pins {pins}")
    ck.check(f"C.{ref}.footprint_band_pad", band == "1",
             f"DO-35 footprint {R.board('main').parts[ref]['fp']}: band (silk across the body at x {xs} mm) next to pad "
             f"{band}, expected pad 1 = the symbol's cathode")
for ref in ("D11", "D12", "D13", "D14", "D15", "D16", "D17"):
    k, a, pins = cathode_pin_symbol("face", ref)
    fl = flat_pad(fp_uid("face", ref))
    ck.check(f"C.{ref}.symbol_and_flat", (k, a) == ("2", "1") and fl == k,
             f"LED symbol K = {k}, A = {a}; footprint flat (cathode mark) next to pad {fl}: the flat must be on the "
             f"symbol's cathode, pad 2")
led_fp = fp_pads("face", "D11")
sq_led = [n for n, v in led_fp.items() if v[2] == "RECT"]
ck.check("C.LED_square_pad_on_cathode", sq_led == [flat_pad(fp_uid("face", "D11"))],
         f"LED-3MM-2P: square pad {sq_led}, flat at pad {flat_pad(fp_uid('face', 'D11'))}: the square pad marks the "
         f"anode while the flat marks the cathode; KiCad's LED_D3.0mm (and many kits) put the square pad on the "
         f"cathode, so the two marks on these 7 LEDs point opposite ways for anyone used to that convention")
k21, a21, p21 = cathode_pin_symbol("main", "D21")
ck.check("C.D21.symbol_cathode_middle_pad", k21 == "2" and fp_pads("main", "D21")["2"][0] == 0.0
         and abs(fp_pads("main", "D21")["1"][0] + fp_pads("main", "D21")["3"][0]) < 0.01,
         f"LM4040 cathode pin {k21} (expected 2) is the middle pad of the TO-92 footprint, so the part's orientation "
         f"cannot swap it; symbol {p21}")

# function. Clock input: jack -> 100k -> base node; B-E junction to GND; BAT85 cathode on the base, anode GND.
# Base node voltage for a source V_in: forward B-E clamps at about +0.65 V, the BAT85 at -VF; between them
# the node follows V_in. A diode conducts when its anode is VF above its cathode.
def base_node(v_in, clamp_neg):
    return min(v_in, 0.65) if v_in >= 0 else (max(v_in, -clamp_neg) if clamp_neg is not None else v_in)


for ref, base in (("D22", "B_T_CLK"), ("D23", "B_X_CLK")):
    n = PARTS["main"][ref].nets
    anode, cathode = n["2"], n["1"]
    pos = {base: base_node(5.0, VF_BAT85_SMALL), "GND": 0.0}
    neg_unclamped = {base: base_node(-12.0, None), "GND": 0.0}
    ck.check(f"C.{ref}.off_for_positive_input", pos[anode] - pos[cathode] < 0.1,
             f"+5 V clock: base at {pos[base]:+.2f} V, anode {anode} {pos[anode]:+.2f} V, cathode {cathode} "
             f"{pos[cathode]:+.2f} V: must not conduct")
    ck.check(f"C.{ref}.conducts_for_negative_input", neg_unclamped[anode] - neg_unclamped[cathode] > VF_BAT85_SMALL,
             f"-12 V input: without the diode the base would sit at {neg_unclamped[base]:+.1f} V; anode {anode} "
             f"{neg_unclamped[anode]:+.1f} V vs cathode {cathode} {neg_unclamped[cathode]:+.1f} V: must conduct and clamp")
    q = "Q1" if ref == "D22" else "Q2"
    # verifier change: veb was base_node(-12 V) with the clamp always on, a constant 0.4 V whatever way the diode
    # was wired; the clamp now counts only when this diode's anode is on GND and its cathode on the base node.
    clamps = n.get("2") == "GND" and n.get("1") == base
    veb = 0.0 - base_node(-12.0, VF_BAT85_SMALL if clamps else None)
    ck.check(f"C.{ref}.keeps_{q}_inside_VEBO", PARTS["main"][q].nets[Q2N3904_DS["B"]] == base and veb < VEBO_2N3904,
             f"-12 V input clamped: reverse emitter-base voltage {veb:.2f} V (BAT85 VF taken as {VF_BAT85_SMALL} V) against "
             f"the 2N3904's VEBO {VEBO_2N3904} V; the unclamped node would see 12 V")
r47 = PARTS["main"]["R47"]
ck.check("C.D21.reverse_biased_shunt", d21.get(LM4040_TO92["K"]) == "VREF" and set(r47.nets.values()) == {"3V3A", "VREF"},
         f"LM4040 cathode on VREF (+2.5 V), anode on GND, fed through R47 from 3V3A; D21 {d21}, R47 {r47.nets}")
lit_bad = []
for ref, label, net in circuit.GATE_LEDS:
    rr = [p for p in FB if p.kind == "R" and set(p.nets.values()) == {net, f"LED_{ref}"}]
    if len(rr) != 1 or PARTS["face"][ref].nets != {"1": f"LED_{ref}", "2": "GND_F"}:
        lit_bad.append(ref)
for ref, jack in circuit.OUTPUT_LEDS.items():
    if ref in ("D11", "D12", "D13"):
        continue
    rr = [p for p in FB if p.kind == "R" and set(p.nets.values()) == {f"L_{ref}_G", f"LED_{ref}_G"}]
    if len(rr) != 1 or PARTS["face"][ref].nets != {"1": f"LED_{ref}_G", "2": "GND_D_F"}:
        lit_bad.append(ref)
ck.check("C.LEDs_forward_when_lit", not lit_bad,
         f"D11-D13: gate jack net -> 3k3 -> anode, cathode GND_F; D14-D17: 595 line -> 470 -> anode, cathode GND_D_F; "
         f"bad {lit_bad}")

# ==========================================================================================================
# D  the routed master against circuit.py: parts, devices, every pad's net, footprint geometry


def expected_device(part):
    """A substring the device title / Manufacturer Part must contain for this part."""
    if part.kind == "R":
        v = part.value.upper()
        if "K" not in v and "M" not in v:
            v += "R"
        elif v.endswith("K"):
            v = v if len(v) > 2 else v + "0"
        return "LR1F" + v
    if part.kind == "C":
        return {"100n": "FG28X7R1H104", "1n": "FG28C0G1H102", "1u": "SR305C105"}[part.value]
    return {"SEED": "Daisy Seed", "TL074": "TL074", "MCP4922": "MCP4922", "LM4040": "LM4040-2.5", "NPN": "2N3904",
            "BAT85": "BAT85", "HDR8": "1x8", "HDR4": "1x4", "HDR3": "1X3", "JACK": "WQP518MA", "POT": "B103",
            "MUX": "74HC4051", "HC595": "74HC595", "HC165": "74HC165", "LED_G": "LED 3mm green",
            "SWLED": "LED button green", "SWLED_RG": "LED button bipolar"}[part.kind]


def device_name(board, ref):
    u = R.attrs(board, ref).get("Device")
    t = doc_meta(R.docs[u]).get("title", "") if u in R.docs else ""
    return f"{t} | {R.devices.get(u, {}).get('Manufacturer Part', '')}"


for b, parts in (("main", MB), ("face", FB)):
    want = PARTS[b]
    got = R.board(b).parts
    missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
    ck.check(f"D.designators_complete.{b}", not missing and not extra,
             f"{len(want)} parts in circuit.py, {len(got)} on the routed PCB; missing {missing}, extra {extra}")
    pad_bad, dev_bad = [], []
    for ref, part in want.items():
        c = got.get(ref)
        if not c:
            continue
        no_pad = sorted(set(part.nets) - set(c["pads"]))
        if no_pad:
            pad_bad.append((ref, "circuit pins without a pad", no_pad))
        for num, pad in c["pads"].items():
            if pad.net != part.nets.get(num):
                pad_bad.append((ref, num, "routed", pad.net, "circuit", part.nets.get(num)))
        name = device_name(b, ref)
        if expected_device(part).lower() not in name.lower():
            dev_bad.append((ref, part.kind, part.value, name))
    ck.check(f"D.every_pad_net.{b}", not pad_bad,
             f"every pad of every part against circuit.py; {len(pad_bad)} differences: {pad_bad[:20]}")
    ck.check(f"D.devices_match_values.{b}", not dev_bad, f"device against kind / value: {dev_bad[:20]}")
    routed_nets = {p.net for c in got.values() for p in c["pads"].values() if p.net}
    ck.check(f"D.no_foreign_nets.{b}", routed_nets == set(NETS[b]),
             f"routed pad nets minus circuit: {sorted(routed_nets - set(NETS[b]))}, circuit minus routed: "
             f"{sorted(set(NETS[b]) - routed_nets)}")
    track_nets = {t["net"] for t in R.board(b).tracks if t["net"]} | {v["net"] for v in R.board(b).vias if v["net"]}
    ck.check(f"D.no_foreign_track_nets.{b}", track_nets <= set(NETS[b]),
             f"tracks / vias on nets circuit.py does not have: {sorted(track_nets - set(NETS[b]))}")

# header devices: female sockets on the main board, male pins on the faceplate (design.md / the BOM)
gender_bad = []
for ref, _, _ in circuit.HEADERS:
    m_name, f_name = device_name("main", ref), device_name("face", circuit.fb_ref(ref))
    if not ("排母" in m_name or "female" in m_name.lower() or "socket" in m_name.lower()):
        gender_bad.append((ref, m_name))
    if "排母" in f_name or "female" in f_name.lower() or "socket" in f_name.lower():
        gender_bad.append((circuit.fb_ref(ref), f_name))
ck.check("D.header_device_gender", not gender_bad,
         f"design.md: female sockets on the main board, male pins on the faceplate; EasyEDA devices that say otherwise "
         f"(only matters for a BOM taken from EasyEDA, bom.py is right): {gender_bad}")
pot_dev = {device_name("face", r) for r, *_ in circuit.POTS}
ck.check("D.pot_device_is_Alpha", all("alpha" in n.lower() or "rd901" in n.lower() for n in pot_dev),
         f"the pots are Alpha 9 mm (design.md, BOM); the routed device says {pot_dev} (Bourns' PTV09A part number on an "
         f"Alpha footprint: right value, wrong part name for anyone ordering from EasyEDA)")


# footprint geometry
def dip_ok(pads, n):
    half = n // 2
    rows = all(abs(pads[str(i)][1] + 3.81) < 0.01 and abs(pads[str(n + 1 - i)][1] - 3.81) < 0.01
               and abs(pads[str(i)][0] - pads[str(n + 1 - i)][0]) < 0.01 for i in range(1, half + 1))
    order = all(abs(pads[str(i + 1)][0] - pads[str(i)][0] - 2.54) < 0.01 for i in range(1, half))
    return rows and order and len(pads) == n


for refs, n, b in ((("U3", "U4", "U5", "U6", "U7", "U8"), 14, "main"), (("U1", "U9", "U10", "U11"), 16, "face")):
    uids = sorted({fp_uid(b, r) for r in refs})
    ok = all(dip_ok(ROUTED.footprint_pads(u), n) for u in uids)
    top = all(not R.board(b).parts[r]["bottom"] for r in refs)
    ck.check(f"D.DIP{n}_numbering", ok and top,
             f"{refs}: pin 1 at one end of the y = -3.81 row, 1-{n // 2} along it 2.54 mm apart, {n // 2 + 1}-{n} back along "
             f"the y = +3.81 row (rows 7.62 mm apart), counter-clockwise from the top (JEDEC), all on the top layer; "
             f"{len(uids)} footprint(s)")
    dots = []
    for u in uids:
        pads = ROUTED.footprint_pads(u)
        _, circles = ROUTED.footprint_silk(u)
        small = [c for c in circles if c[2] < 0.5]
        dots.append(bool(small) and all(min(pads, key=lambda k: math.hypot(pads[k][0] - c[0], pads[k][1] - c[1])) == "1"
                                        for c in small))
    ck.check(f"D.DIP{n}_pin1_silk_dot", all(dots), f"the silk pin-1 dot of each DIP-{n} footprint sits nearest pad 1")

to92 = ROUTED.footprint_pads(fp_uid("main", "Q1"))
segs, circles = ROUTED.footprint_silk(fp_uid("main", "Q1"))
flats = [s for s in segs if abs(s[1] - s[3]) < 0.01 and abs(s[0] - s[2]) > 2.0]
flat_y = flats[0][1] if len(flats) == 1 else None
inline = all(abs(to92[p][1]) < 0.01 for p in "123") and abs(to92["2"][0] - to92["1"][0] - 2.54) < 0.01 \
    and abs(to92["3"][0] - to92["2"][0] - 2.54) < 0.01
# seen from the flat side (top view, the part on the top layer): the viewer looks from the flat towards the body
if flat_y is not None:
    v = (0.0, 1.0) if flat_y < 0 else (0.0, -1.0)
    right = (v[1], -v[0])
    p1_left = (to92["3"][0] - to92["1"][0]) * right[0] + (to92["3"][1] - to92["1"][1]) * right[1] > 0
else:
    p1_left = False
ck.check("D.TO92_order_and_flat", inline and p1_left and not R.main.parts["Q1"]["bottom"] and not R.main.parts["Q2"]["bottom"],
         f"TO-92-INLINE-P2.54: pads 1-2-3 in line 2.54 mm apart, flat silk at y {flat_y}; pin 1 must be on the left "
         f"seen from the flat (onsemi style 1 E-B-C, KiCad TO-92_Inline) so a 2N3904 fitted by its flat puts E in pad 1")
jack = fp_pads("face", "J1")
d12 = math.hypot(jack["2"][0] - jack["1"][0], jack["2"][1] - jack["1"][1])
d13 = math.hypot(jack["3"][0] - jack["1"][0], jack["3"][1] - jack["1"][1])
ck.check("D.jack_pad_spacing_vs_KiCad", abs(d12 - JACK_KICAD["TN"]) < 0.05 and abs(d13 - JACK_KICAD["T"]) < 0.05
         and len({fp_uid("face", r) for r, *_ in circuit.JACKS}) == 1,
         f"KiCad PJ398SM: S->TN {JACK_KICAD['TN']} mm, S->T {JACK_KICAD['T']} mm; footprint pad 1->2 {d12:.2f}, 1->3 "
         f"{d13:.2f} (so 1 = S, 2 = TN, 3 = T)")
pot = R.fp_geo[fp_uid("face", "RV1")]["pads"]
row_y = pot["1"]["y"]
shaft_y = row_y + POT_KICAD["shaft_from_pins"]
ok = (abs(pot["2"]["x"] - pot["1"]["x"] - POT_KICAD["pitch"]) < 0.01 and abs(pot["3"]["x"] - pot["2"]["x"] - POT_KICAD["pitch"]) < 0.01
      and abs(pot["1"]["y"] - pot["3"]["y"]) < 0.01 and abs(pot["4"]["y"] - shaft_y) < 0.01 and abs(pot["5"]["y"] - shaft_y) < 0.01
      and abs(pot["5"]["x"] - pot["4"]["x"] - 2 * POT_KICAD["lug_half_span"]) < 0.01 and abs(pot["4"]["x"] + pot["5"]["x"]) < 0.01
      and abs(pot["2"]["x"]) < 0.01 and abs(shaft_y - circuit.POT_SHAFT) < 0.01
      and all(abs(pot[k]["w"] - POT_KICAD["lug_pad"][0]) < 0.01 and abs(pot[k]["h"] - POT_KICAD["lug_pad"][1]) < 0.01 for k in "45"))
ck.check("D.pot_footprint_vs_KiCad_RD901F", ok and len({fp_uid("face", r) for r, *_ in circuit.POTS}) == 1,
         f"KiCad RD901F: pins 2.5 mm apart, shaft 7.5 mm from the pin row (= circuit.POT_SHAFT {circuit.POT_SHAFT} from the "
         f"origin), lugs +-4.8 on the shaft line, 2.72 x 3.24 pads; footprint "
         f"{ {k: (round(v['x'], 2), round(v['y'], 2), round(v['w'], 2), round(v['h'], 2)) for k, v in pot.items()} }")
# clockwise in the front view: x_front = W - x; seen from the front with the pins "down" (towards the pin row),
# pin 1 on the left, pin 3 on the right (pots on the bottom layer, shafts towards the panel)
W = R.face.outline[2]
cw_bad = []
for ref, label, *_ in circuit.POTS:
    c = R.face.parts[ref]
    p1, p3 = c["pads"]["1"], c["pads"]["3"]
    sh = to_board(c, 0.0, circuit.POT_SHAFT)
    f1, f3, fs = (W - p1.x, p1.y), (W - p3.x, p3.y), (W - sh[0], sh[1])
    d = ((f1[0] + f3[0]) / 2 - fs[0], (f1[1] + f3[1]) / 2 - fs[1])            # shaft -> pin row ("down")
    right = (-d[1], d[0])                                                    # down rotated +90 deg
    if not (c["bottom"] and (f3[0] - f1[0]) * right[0] + (f3[1] - f1[1]) * right[1] > 0):
        cw_bad.append((ref, label, round(fs[0], 2), round(fs[1], 2)))
ck.check("D.pots_CW_front_view", not cw_bad,
         f"front view, pins towards the bottom: pin 1 left, pin 3 right, so clockwise turns the wiper to 3 (3V3A_F); "
         f"bad {cw_bad}")
shaft_bad = [(ref, tuple(round(v, 2) for v in to_board(R.face.parts[ref], 0.0, circuit.POT_SHAFT)), circuit.POT_XY[ref])
             for ref in circuit.POT_XY
             if math.hypot(W - to_board(R.face.parts[ref], 0.0, circuit.POT_SHAFT)[0] - circuit.POT_XY[ref][0],
                           to_board(R.face.parts[ref], 0.0, circuit.POT_SHAFT)[1] - circuit.POT_XY[ref][1]) > 0.02]
ck.check("D.pot_shafts_at_POT_XY", not shaft_bad, f"routed shafts (front view) at circuit.POT_XY; bad {shaft_bad}")
btn_uids = {fp_uid("face", r) for r, *_ in circuit.BUTTONS}
btn = fp_pads("face", "SW1")
ck.check("D.button_footprint_vs_parts_md", len(btn_uids) == 1 and set(btn) == set(BUTTON_XY)
         and all(abs(btn[n][0] - x) < 0.01 and abs(btn[n][1] - y) < 0.01 for n, (x, y) in BUTTON_XY.items()),
         f"parts.md (unconfirmed source) pins {BUTTON_XY}, no feet holes (design.md: clip the feet); footprint(s) "
         f"{len(btn_uids)}, pads { {n: (round(v[0], 2), round(v[1], 2)) for n, v in btn.items()} }")
sq_bad = []
for b, refs in (("main", ("U3", "U4", "U5", "U6", "U7", "U8") + tuple(r for r, _, _ in circuit.HEADERS)),
                ("face", ("U1", "U9", "U10", "U11") + tuple(circuit.fb_ref(r) for r, _, _ in circuit.HEADERS))):
    for ref in refs:
        rects = sorted(n for n, v in fp_pads(b, ref).items() if v[2] == "RECT")
        if rects != ["1"]:
            sq_bad.append((ref, rects))
ck.check("D.pin1_square_pad", not sq_bad, f"DIP and header footprints: square pad = pin 1 only; footprints without it "
                                          f"(pin 1 then marked by silk only): {sq_bad}")
# the Seed footprint: 1-20 one column, 21-40 back up the other, pin n across from 41 - n, 2.54 mm pitch,
# pins 1 / 40 at the USB end (the extra silk line), pin 1 on the left in the top view with the USB end up
u2 = R.main.parts["U2"]
P = u2["pads"]
cols = all(abs(P[str(i)].x - P["1"].x) < 0.01 and abs(P[str(41 - i)].x - P["40"].x) < 0.01
           and abs(P[str(i)].y - P[str(41 - i)].y) < 0.01 for i in range(1, 21))
pitch = all(abs(math.hypot(P[str(i + 1)].x - P[str(i)].x, P[str(i + 1)].y - P[str(i)].y) - 2.54) < 0.01 for i in range(1, 40) if i != 20)
segs, _ = ROUTED.footprint_silk(fp_uid("main", "U2"))
xs = [s[0] for s in segs if abs(s[0] - s[2]) < 0.01]
usb_x = max(xs, key=lambda x: (sum(1 for y in xs if abs(y - x) < 0.01) == 1, x)) if xs else None
usb = to_board(u2, usb_x, 0.0) if usb_x is not None else (0, 0)
d1, d20 = math.hypot(P["1"].x - usb[0], P["1"].y - usb[1]), math.hypot(P["20"].x - usb[0], P["20"].y - usb[1])
up = (usb[0] - u2["x"], usb[1] - u2["y"])
right = (up[1], -up[0])
p1_left = ((P["40"].x - P["1"].x) * right[0] + (P["40"].y - P["1"].y) * right[1]) > 0
ck.check("D.Seed_footprint_pin_order", cols and pitch and d1 < d20 and p1_left and not u2["bottom"],
         f"pins 1-20 / 21-40 in two columns, n across from 41-n, 2.54 mm pitch, pin 1 at the USB end (silk marker at "
         f"({usb[0]:.1f}, {usb[1]:.1f})) and on the left with the USB end up (Electrosmith's top-view pinout); columns "
         f"{cols}, pitch {pitch}, pin 1 {d1:.1f} mm / pin 20 {d20:.1f} mm from the marker, pin 1 left {p1_left}")

# ==========================================================================================================
# E  header stacking
ck.check("E.same_outline", tuple(round(v, 2) for v in R.main.outline) == tuple(round(v, 2) for v in R.face.outline),
         f"main {R.main.outline}, faceplate {R.face.outline}")
sides_bad = [(ref, R.main.parts[ref]["bottom"], R.face.parts[circuit.fb_ref(ref)]["bottom"]) for ref, _, _ in circuit.HEADERS
             if not R.main.parts[ref]["bottom"] or R.face.parts[circuit.fb_ref(ref)]["bottom"]]
ck.check("E.header_sides", not sides_bad, f"design.md: sockets on the main board's bottom, male pins on the faceplate's "
                                          f"top (both the facing sides); bad (ref, main bottom, face bottom) {sides_bad}")
mpads = [(ref, num, pad) for ref, _, _ in circuit.HEADERS for num, pad in R.main.parts[ref]["pads"].items()]
pairs = {(ref, str(i + 1)): (a, b) for ref, _, pins in circuit.HEADERS for i, (a, b) in enumerate(pins)}
stack_bad, matched, open_ok = [], 0, 0
for ref, _, pins in circuit.HEADERS:
    fref = circuit.fb_ref(ref)
    for num, fp in R.face.parts[fref]["pads"].items():
        near = [m for m in mpads if math.hypot(m[2].x - fp.x, m[2].y - fp.y) < 0.05]
        if len(near) != 1:
            stack_bad.append((fref, num, "no single main-board pin under it", len(near)))
            continue
        mref, mnum, mp = near[0]
        want = pairs.get((mref, mnum))
        if (mp.net, fp.net) != want:
            stack_bad.append((fref, num, fp.net, "over", mref, mnum, mp.net, "HEADERS", want))
        elif want == (None, None):
            open_ok += 1
        else:
            matched += 1
ck.check("E.stacked_pins_carry_pairs", not stack_bad and matched == n_used and open_ok == n_pins - n_used,
         f"{matched} of {n_used} stacked used pins carry the HEADERS pair, {open_ok} open pin(s) open on both; "
         f"bad {stack_bad[:12]}")
order_bad = []
for b in ("main", "face"):
    for ref, _, pins in circuit.HEADERS:
        r = ref if b == "main" else circuit.fb_ref(ref)
        pd = R.board(b).parts[r]["pads"]
        n = len(pins)
        steps = [(pd[str(i + 1)].x - pd[str(i)].x, pd[str(i + 1)].y - pd[str(i)].y) for i in range(1, n)]
        if not all(abs(math.hypot(*s) - 2.54) < 0.01 and abs(s[0] - steps[0][0]) < 0.01 and abs(s[1] - steps[0][1]) < 0.01
                   for s in steps) or len(pd) != n:
            order_bad.append((r, steps))
ck.check("E.pin_order", not order_bad, f"each header's pins 1..n in a straight line, 2.54 mm apart, in order; bad {order_bad}")


def track_ends(board):
    ends = collections.defaultdict(list)
    for t in board.tracks:
        ends[t["net"]] += [t["a"], t["b"]]
    for v in board.vias:
        ends[v["net"]].append(v["c"])
    return ends


hit = tot = 0
miss = []
for b in ("main", "face"):
    ends = track_ends(R.board(b))
    for ref, _, _ in circuit.HEADERS:
        r = ref if b == "main" else circuit.fb_ref(ref)
        for num, pad in R.board(b).parts[r]["pads"].items():
            if pad.net in (None, "GND", "GND_F"):
                continue
            tot += 1
            if any(math.hypot(e[0] - pad.x, e[1] - pad.y) < 0.3 for e in ends[pad.net]):
                hit += 1
            else:
                miss.append(f"{r}.{num}")
ck.check("E.transform_sanity_tracks_end_on_pads", hit == tot,
         f"{hit} of {tot} non-ground header pads have a same-net track end or via within 0.3 mm of the computed pad "
         f"centre (validates the bottom-layer mirror + rotation used for stacking); missing {miss}")


# ==========================================================================================================
# F  schematic pages against circuit.py (routed master and generated project)
def _on_seg(p, a, b, tol=0.01):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if min(x1, x2) - tol <= x <= max(x1, x2) + tol and min(y1, y2) - tol <= y <= max(y1, y2) + tol:
        return abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) <= tol * max(1, math.hypot(x2 - x1, y2 - y1))
    return False


def _xf(cand, comp, px, py):
    order, sigma, phi = cand
    m = -1 if comp.get("isMirror") else 1
    a = math.radians(sigma * (comp.get("rotation") or 0))
    if order == "mirror-first":
        px = m * px
    x, y = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
    if order == "rotate-first":
        x = m * x
    return round(comp["x"] + x, 3), round(comp["y"] + phi * y, 3)


CANDS = [(o, s, f) for o in ("mirror-first", "rotate-first") for s in (-1, 1) for f in (1, -1)]
NONPOLAR = ("R", "C")


def schematic_nets(ex):
    """{board title: (pins_of, groups, stats)} from the SCH_PAGE docs.

    pins_of {ref: {pin: net name, or ('wire', page, group id) for a pin whose wires carry no name, or None for a
    pin touching nothing}}. Wires are joined into groups by geometry (an end of one on a segment of another); a
    group takes the NET names of its wires and of the net flags standing on it. Names join groups across pages;
    unnamed groups exist on their own page only (EasyEDA names them itself)."""
    sch_board = {u: ex.boards.get(doc_meta(d).get("board")) for u, d in ex.of_type("SCH").items()}
    pages = collections.defaultdict(list)
    for u, d in ex.of_type("SCH_PAGE").items():
        pages[sch_board.get(doc_meta(d).get("schematic"))].append((u, d))
    sympins, result = {}, {}

    def pins_of_sym(sym):
        if sym not in sympins:
            sympins[sym] = ex.symbol_pins(sym)
        return sympins[sym]

    for board, docs in pages.items():
        page_data = []
        for u, d in docs:
            comps = {h["id"]: p for h, p in d["recs"] if h["type"] == "COMPONENT" and p}
            attrs = collections.defaultdict(dict)
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p:
                    attrs[p.get("parentId")][p["key"]] = p["value"]
            wires = {h["id"]: [] for h, p in d["recs"] if h["type"] == "WIRE" and p}
            for h, p in d["recs"]:
                if h["type"] == "LINE" and p and p.get("lineGroup") in wires:
                    wires[p["lineGroup"]].append(((p["startX"], p["startY"]), (p["endX"], p["endY"])))
            named = {w: attrs[w].get("NET") for w in wires if attrs[w].get("NET")}
            page_data.append((u, comps, attrs, wires, named))
        best = None
        for cand in CANDS:
            score = 0
            for u, comps, attrs, wires, named in page_data:
                ptset = {(round(x, 3), round(y, 3)) for w in wires for seg in wires[w] for x, y in seg}
                for cid, comp in comps.items():
                    sym = attrs[cid].get("Symbol")
                    if sym not in ex.docs or "Designator" not in attrs[cid]:
                        continue
                    for num, (name, px, py, part) in pins_of_sym(sym).items():
                        if part and part != comp.get("partId"):
                            continue
                        score += _xf(cand, comp, px, py) in ptset
            if best is None or score > best[0]:
                best = (score, cand)
        cand = best[1]
        pins_of = collections.defaultdict(dict)
        groups = collections.defaultdict(list)          # unnamed group id -> [(ref, pin)]
        conflicts = []
        for u, comps, attrs, wires, named in page_data:
            parent = {w: w for w in wires}

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            segs = [(w, sg) for w in wires for sg in wires[w]]
            ends = [(w, q) for w in wires for sg in wires[w] for q in sg]
            for w, q in ends:
                for w2, sg in segs:
                    if w2 != w and find(w2) != find(w) and _on_seg(q, *sg):
                        parent[find(w)] = find(w2)
            gname = collections.defaultdict(set)
            for w, n in named.items():
                gname[find(w)].add(n)
            flag_pts = []
            for cid, comp in comps.items():
                a = attrs[cid]
                sym = a.get("Symbol")
                if "Designator" in a or not a.get("Name") or sym not in ex.docs:
                    continue
                for num, (name, px, py, part) in pins_of_sym(sym).items():
                    q = _xf(cand, comp, px, py)
                    flag_pts.append((q, a["Name"]))
                    for w, sg in segs:
                        if _on_seg(q, *sg):
                            gname[find(w)].add(a["Name"])
            for g, ns in gname.items():
                if len(ns) > 1:
                    conflicts.append(("wire group", sorted(ns)))
            for cid, comp in comps.items():
                a = attrs[cid]
                ref, sym = a.get("Designator"), a.get("Symbol")
                if not ref or sym not in ex.docs:
                    continue
                for num, (name, px, py, part) in pins_of_sym(sym).items():
                    if part and part != comp.get("partId"):
                        continue
                    q = _xf(cand, comp, px, py)
                    gs = {find(w) for w, sg in segs if _on_seg(q, *sg)}
                    nets = set().union(*(gname[g] for g in gs)) if gs else set()
                    nets |= {n for fq, n in flag_pts if abs(fq[0] - q[0]) < 0.01 and abs(fq[1] - q[1]) < 0.01}
                    if len(nets) > 1:
                        conflicts.append((ref, num, sorted(nets)))
                    if nets:
                        val = sorted(nets)[0]
                    elif gs:
                        val = ("wire", u, min(gs))
                        groups[val].append((ref, num))
                    else:
                        val = None
                    prev = pins_of[ref].get(num)
                    if isinstance(prev, str) and isinstance(val, str) and prev != val:
                        conflicts.append((ref, num, prev, val))
                    if prev is None or (not isinstance(prev, str) and isinstance(val, str)):
                        pins_of[ref][num] = val
        result[board] = (pins_of, groups, {"transform": cand, "score": best[0], "conflicts": conflicts})
    return result


def compare_schematic(label, ex):
    res = schematic_nets(ex)
    for board, parts in (("Marblesy Main", MB), ("Marblesy Faceplate", FB)):
        tag = board.split()[-1].lower()
        nets_here = NETS["main" if tag == "main" else "face"]
        if board not in res:
            ck.check(f"F.{label}.{tag}.pages_present", False, f"no schematic pages for {board}")
            continue
        pins_of, groups, st = res[board]
        want = {p.ref: p for p in parts}
        missing, extra = sorted(set(want) - set(pins_of)), sorted(set(pins_of) - set(want))
        ck.check(f"F.{label}.{tag}.parts", not missing and not extra,
                 f"{len(want)} parts in circuit.py, {len(pins_of)} on the pages; missing {missing}, extra {extra}")
        ck.check(f"F.{label}.{tag}.no_conflicting_labels", not st["conflicts"],
                 f"pins or wire groups touching two differently named nets: {st['conflicts'][:10]}")
        # two-pin R / C read with pins 1 / 2 the other way round under the picked convention: compare swapped
        swapped = []
        for ref, p in want.items():
            got = pins_of.get(ref, {})
            if p.kind in NONPOLAR and len(p.nets) == 2 and all(isinstance(v, str) for v in got.values()) \
                    and sorted(got.values()) == sorted(p.nets.values()) and got != p.nets:
                swapped.append(ref)

        def circuit_net(ref, num):
            if ref in swapped:
                num = {"1": "2", "2": "1"}.get(num, num)
            return want[ref].nets.get(num)
        diffs, loose = [], []
        n_named = n_wire = 0
        for ref, p in want.items():
            got = pins_of.get(ref, {})
            for num in sorted(set(p.nets) | set(got), key=lambda s: int(s) if s.isdigit() else 0):
                g, c = got.get(num), circuit_net(ref, num)
                if isinstance(g, str):
                    n_named += 1
                    if g != c:
                        diffs.append((ref, num, "page", g, "circuit", c))
                elif g is None and c is not None:
                    loose.append((ref, num, c))
                elif g is not None:
                    n_wire += 1
        ck.check(f"F.{label}.{tag}.pin_nets", not diffs,
                 f"transform {st['transform']}, {n_named} pins on named nets; {len(diffs)} differ from circuit.py: "
                 f"{diffs[:15]}")
        ck.check(f"F.{label}.{tag}.no_unconnected_pins", not loose,
                 f"pins circuit.py connects that touch no wire or net flag on the pages: {loose[:15]}")
        bad_groups = []
        for gid, members in groups.items():
            cn = {circuit_net(r, n) for r, n in members}
            whole = max((len(nets_here.get(c, [])) for c in cn if c), default=0)
            if len(cn) != 1 or None in cn or (len(members) == 1 and whole > 1):
                bad_groups.append(sorted(f"{r}.{n}={circuit_net(r, n)}" for r, n in members))
        ck.check(f"F.{label}.{tag}.unnamed_wires_join_one_net", not bad_groups,
                 f"{len(groups)} wire groups without a net name ({n_wire} pins): each must join pins of one circuit.py "
                 f"net, and more than one pin; bad {bad_groups[:10]}")
        polar_rot = [r for r in swapped if want[r].kind not in NONPOLAR]
        ck.check(f"F.{label}.{tag}.polar_parts_unambiguous", not polar_rot,
                 f"{len(swapped)} non-polar two-pin parts read with pins 1 / 2 the other way round under this "
                 f"convention (harmless on R / C); polar parts affected: {polar_rot}")


compare_schematic("routed", ROUTED)
compare_schematic("generated", Export(harness.GENERATED))

# ==========================================================================================================
# G  design.md's tables and stated wiring against circuit.py and the routed board
DESIGN = harness.text("docs", "design.md")
ALL = {**PARTS["main"], **{f"face:{r}": p for r, p in PARTS["face"].items()}}


def md_table(after):
    """Rows (lists of cells) of the first markdown table after the first line containing `after`."""
    lines = DESIGN[DESIGN.index(after):].splitlines()
    rows, started = [], False
    for ln in (lines if lines[0].startswith("|") else lines[1:]):
        if ln.startswith("|"):
            started = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif started:
            break
    return rows


def expand(tok):
    """'23..28' -> 23..28; 'A1..A6' -> A1..A6; 'GATE_T1..T3' -> GATE_T1, GATE_T2, GATE_T3."""
    tok = re.sub(r"\s*\(.*?\)", "", tok).strip()
    m = re.match(r"^(.*?)(\d+)\.\.[A-Za-z_]*?(\d+)$", tok)
    if not m:
        return [tok]
    return [f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(3)) + 1)]


def cells(s):
    return [t for part in s.split(",") for t in expand(part.strip())]


def parse_ohms(s):
    s = s.strip()
    if re.match(r"^\d+\.\d+k$", s):
        return float(s[:-1]) * 1e3
    return harness.ohms(s)


main_parts = PARTS["main"]
face_parts = PARTS["face"]
U2P = R.main.parts["U2"]["pads"]

# Seed pin map
st = md_table("### Daisy Seed pin map")
seed_bad = []
covered = set()
for row in st[1:]:
    pins, names = cells(row[0]), cells(row[1])
    nets = cells(row[2]) if row[2] not in ("—", "-") else [None] * len(pins)
    if len(nets) == 1 and len(pins) > 1:
        nets = nets * len(pins)
    if not (len(pins) == len(names) == len(nets)):
        seed_bad.append(("row shape", row))
        continue
    for pin, name, net in zip(pins, names, nets):
        covered.add(pin)
        cname, cnet = circuit.SEED[pin]
        rnet = U2P[pin].net
        if name not in set(cname.split("/")) | {cname} or cnet != net or rnet != net:
            seed_bad.append((pin, "md", name, net, "circuit", cname, cnet, "routed", rnet))
ck.check("G.seed_pin_map", not seed_bad and covered >= {str(i) for i in range(1, 41)} - {"16", "17", "18", "19"},
         f"design.md Seed pin map against circuit.SEED and the routed U2 pads; bad {seed_bad}; pins not in the table "
         f"{sorted({str(i) for i in range(1, 41)} - covered, key=int)}")

# CV input table
ct = md_table("| Input | Section |")
cv_bad = []
by_letter = {"A": 1, "B": 2, "C": 3, "D": 4}
names = []
for row in ct:
    if row[0] == "Input":
        continue
    label, sec, rin, rf, cf, rs, adc = row
    key = label.upper().replace("DEJA VU", "DEJAVU").replace(" ", "_")
    names.append(key)
    u, s = sec[:-1], by_letter[sec[-1]]
    out, inm, inp = circuit.SECTION[s]
    tl = main_parts[u].nets
    ok = (tl[out] == f"OA_{key}" and tl[inm] == f"IN_{key}" and tl[inp] == "BIAS"
          and set(main_parts[rin].nets.values()) == {f"CV_{key}", f"IN_{key}"} and main_parts[rin].value == "100k"
          and set(main_parts[rf].nets.values()) == {f"IN_{key}", f"OA_{key}"} and main_parts[rf].value == "13k"
          and set(main_parts[cf].nets.values()) == {f"IN_{key}", f"OA_{key}"} and main_parts[cf].value == "1n"
          and set(main_parts[rs].nets.values()) == {f"OA_{key}", f"ADC_{key}"} and main_parts[rs].value == "1k")
    seed_pin = [p for p, (n, net) in circuit.SEED.items() if adc in n.split("/")]
    if not ok or len(seed_pin) != 1 or circuit.SEED[seed_pin[0]][1] != f"ADC_{key}" or U2P[seed_pin[0]].net != f"ADC_{key}":
        cv_bad.append(row)
ck.check("G.cv_input_table", not cv_bad and names == [n for n, *_ in circuit.CV_CHANNELS],
         f"design.md CV input table (section, 100k / 13k / 1n / 1k, ADC pin) against circuit.py and the routed U2; "
         f"bad rows {cv_bad}; inputs {names}")

# DAC output table
dt = md_table("| Output | DAC | Section |")
dac_bad = []
outs = []
for row in dt:
    if row[0] == "Output":
        continue
    o, dac, sec, rdac, rref, rf, rs = row
    outs.append(o)
    chip, ch = dac.split()
    pin = MCP4922_DS["VOUTA" if ch == "A" else "VOUTB"]
    u, s = sec[:-1], by_letter[sec[-1]]
    out, inm, inp = circuit.SECTION[s]
    refs = [c.split()[0] for c in (rdac, rref, rf, rs)]
    vals = [c.split()[1] if len(c.split()) > 1 else None for c in (rdac, rref, rf, rs)]
    want_nets = [{f"DAC_{o}", f"IN_{o}"}, {"NEG_REF", f"IN_{o}"}, {f"IN_{o}", f"OA_{o}"}, {f"OA_{o}", o}]
    ok = main_parts[chip].nets.get(pin) == f"DAC_{o}" and R.main.parts[chip]["pads"][pin].net == f"DAC_{o}"
    tl = main_parts[u].nets
    ok = ok and tl[out] == f"OA_{o}" and tl[inm] == f"IN_{o}" and tl[inp] == "GND"
    for ref, val, nets in zip(refs, vals, want_nets):
        p = main_parts.get(ref)
        if not p or set(p.nets.values()) != nets or (val and abs(parse_ohms(val) - harness.ohms(p.value)) > 1):
            ok = False
    if not ok:
        dac_bad.append(row)
ck.check("G.dac_output_table", not dac_bad and outs == [n for n, *_ in circuit.DAC_OUTS],
         f"design.md DAC output table (VOUTA 14 / VOUTB 10, section, resistors and values) against circuit.py and the "
         f"routed U7 / U8 pads; bad rows {dac_bad}")

# mux table
mt = md_table("| Mux channel (Y) |")
mux_bad = []
for row in mt[1:]:
    ch, pin, pot = int(row[0]), row[1], row[2].split()[0]
    wiper = face_parts[pot].nets["2"]
    if HC4051_CH.get(pin) != ch or face_parts["U1"].nets.get(pin) != wiper or R.face.parts["U1"]["pads"][pin].net != wiper:
        mux_bad.append((row, HC4051_CH.get(pin), face_parts["U1"].nets.get(pin), wiper))
ck.check("G.mux_table", not mux_bad and len(mt) == 9,
         f"design.md mux table: channel of the 4051 pin (SCHS122O) and the pot's wiper on it (circuit.py and the routed "
         f"U1); bad {mux_bad}")

# 595 / 165 table
lt = md_table("| 595 output | LED line |")
led_bad, btn_bad = [], []
for row in lt[1:]:
    left, line, _, right, button = (row + [""] * 5)[:5]
    if left:
        chip, qs = left.split(" ", 1)
        qs = [q.strip() for q in qs.split(",")]
        if line == "spare":
            for q in qs:
                if HC595_DS[q] in face_parts[chip].nets or R.face.parts[chip]["pads"][HC595_DS[q]].net:
                    led_bad.append((left, "spare but wired"))
        else:
            ref = line.split()[0]
            m = re.search(r"\(([RG, ]+)\)", line)
            colours = [c.strip() for c in m.group(1).split(",")] if m else ["G"]
            for q, col in zip(qs, colours):
                pin = HC595_DS[q]
                want = f"L_{ref}_{col}"
                if face_parts[chip].nets.get(pin) != want or R.face.parts[chip]["pads"][pin].net != want:
                    led_bad.append((left, q, line, face_parts[chip].nets.get(pin), want))
    if right:
        d = int(right[1:])
        pin = HC165_DS[HC165_D[d]]
        if button == "tied low":
            want = "GND_D_F"
        else:
            sw = button.split()[0]
            want = face_parts[sw].nets["3"]
        if face_parts["U11"].nets.get(pin) != want or R.face.parts["U11"]["pads"][pin].net != want:
            btn_bad.append((right, button, face_parts["U11"].nets.get(pin), want))
ck.check("G.595_table", not led_bad, f"design.md 595 output table against the 595 pinout (SCLS041J) and circuit.py / the "
                                     f"routed U9, U10; bad {led_bad}")
ck.check("G.165_table", not btn_bad, f"design.md 165 input table against the 165 pinout (SCLS116H: D0 = A, pin 11 ... D7 = "
                                     f"H, pin 6) and circuit.py / the routed U11; bad {btn_bad}")

# header table: nets in order and the x / y ranges against the routed pads (rear-view PCB frame)
ht = md_table("| Header | Pins | Where |")
hdr_bad = []
hdr = {ref: pins for ref, _, pins in circuit.HEADERS}
for row in ht[1:]:
    ref, npins, where, nets = row
    toks = [t.strip() for t in nets.split(",")]
    want = []
    for t in toks:
        m = re.match(r"^(\S+)(?: \((\S+)\))?$", t)
        if t == "open":
            want.append((None, None))
        elif m:
            a, b = m.group(1), m.group(2) or {"GND": "GND_F"}.get(m.group(1), m.group(1) + "_F")
            want.append((a, b))
    if want != hdr.get(ref) or int(npins) != len(hdr.get(ref, [])):
        hdr_bad.append((ref, "nets", want, hdr.get(ref)))
    m = re.match(r"x ([\d.]+), y ([\d.]+)[–-]([\d.]+)", where)
    if not m:
        hdr_bad.append((ref, "where unreadable", where))
        continue
    x, y0, y1 = (float(g) for g in m.groups())
    for b, r in (("main", ref), ("face", circuit.fb_ref(ref))):
        pads = R.board(b).parts[r]["pads"].values()
        px = [p.x for p in pads]
        py = [p.y for p in pads]
        if max(abs(v - x) for v in px) > 0.3 or abs(min(py) - y0) > 1.0 or abs(max(py) - y1) > 1.0:
            hdr_bad.append((r, where, (round(min(px), 2), round(max(px), 2)), (round(min(py), 2), round(max(py), 2))))
ck.check("G.header_table", not hdr_bad and len(ht) == 8,
         f"design.md header table: nets pin 1 first (faceplate names in brackets or + _F) against circuit.HEADERS, and "
         f"x (0.3 mm) / y range (1 mm) against the routed pads of both boards; bad {hdr_bad}")
probe_txt = re.search(r"H3\.3 = (PROBE_F_\d) for T, H6\.3 = (PROBE_F_\d) for X", DESIGN)
ck.check("G.probe_header_pins", bool(probe_txt) and probe_txt.groups() == (dict(enumerate(hdr["H3"], 1))[3][1],
                                                                       dict(enumerate(hdr["H6"], 1))[3][1])
         and circuit.PROBE_NETS == {"TN_TCLK": "PROBE_F_2", "TN_XCLK": "PROBE_F_1"}
         and R.face.parts["R9"]["nets"] == face_parts["R9"].nets and R.face.parts["R10"]["nets"] == face_parts["R10"].nets,
         f"design.md '{probe_txt.group(0) if probe_txt else None}' against HEADERS H3.3 / H6.3 and R9 (T) / R10 (X) on "
         f"the routed faceplate")

# part counts and the stated wiring
kinds = collections.Counter(p.kind for p in MB + FB)
ck.check("G.panel_counts", (kinds["JACK"], kinds["POT"], kinds["SWLED"] + kinds["SWLED_RG"],
                            sum(1 for r in circuit.OUTPUT_LEDS if r in face_parts)) == (16, 8, 7, 7),
         f"design.md: 16 jacks, 8 Alpha pots, 7 LED buttons, 7 output LEDs; got {kinds['JACK']}, {kinds['POT']}, "
         f"{kinds['SWLED'] + kinds['SWLED_RG']}, {sum(1 for r in circuit.OUTPUT_LEDS if r in face_parts)}")
ck.check("G.chip_counts", (kinds["TL074"], kinds["MCP4922"], kinds["HC595"], kinds["HC165"], kinds["MUX"], kinds["LM4040"],
                           kinds["NPN"], kinds["BAT85"]) == (4, 2, 2, 1, 1, 1, 2, 2),
         f"design.md: 4 TL074 (U3-U6), 2 MCP4922, 2 74HC595, 74HC165, 74HC4051, LM4040, 2 x 2N3904, 2 x BAT85; got "
         f"{[kinds[k] for k in ('TL074', 'MCP4922', 'HC595', 'HC165', 'MUX', 'LM4040', 'NPN', 'BAT85')]}")
stages = (sum(1 for u, s in [(u, s) for _, _, u, s in circuit.CV_CHANNELS] if main_parts[u].nets[circuit.SECTION[s][2]] == "BIAS"),
          sum(1 for _, u, s in circuit.GATES if main_parts[u].nets[circuit.SECTION[s][2]].startswith("GATE_")),
          sum(1 for *_, u, s in circuit.DAC_OUTS if main_parts[u].nets[circuit.SECTION[s][2]] == "GND"))
ck.check("G.stage_counts", stages == (7, 3, 4), f"design.md: 7 CV input stages, 3 gate stages, 4 output stages; got {stages}")
vert = sum(1 for p in R.main.parts.values() if p["fp"] == "1/4W-RESISTOR-VERTICAL")
m = re.search(r"(\d+) of the resistors stand up", DESIGN)
ck.check("G.vertical_resistor_count", bool(m) and int(m.group(1)) == vert,
         f"design.md '{m.group(0) if m else None}'; routed main board has {vert} on 1/4W-RESISTOR-VERTICAL")
fb_bad = []
for k, (sw, d) in enumerate(sorted(circuit.LED_BUTTONS.items(), key=lambda kv: int(kv[1][1:]))):
    r = face_parts.get(f"R{80 + k}")
    kind = [kk for rr, _, kk, _ in circuit.LEDS if rr == d][0]
    col = "R" if kind == "RG" else "G"
    if not r or r.value != "470" or set(r.nets.values()) != {f"L_{d}_{col}", f"LED_{d}_{col}"}:
        fb_bad.append((f"R{80 + k}", d))
for ref, q, rr in (("D14", "QG", "R87"), ("D15", "QF", "R88"), ("D16", "QE", "R89"), ("D17", "QC", "R1")):
    r = face_parts[rr]
    if face_parts["U10"].nets.get(HC595_DS[q]) != f"L_{ref}_G" or set(r.nets.values()) != {f"L_{ref}_G", f"LED_{ref}_G"} \
            or r.value != "470":
        fb_bad.append((ref, q, rr))
for k, (ref, label, net) in enumerate(circuit.GATE_LEDS):
    r = face_parts[f"R{91 + k}"]
    if r.value != "3k3" or set(r.nets.values()) != {net, f"LED_{ref}"} or face_parts[ref].nets.get("2") != "GND_F":
        fb_bad.append((ref, f"R{91 + k}"))
for k, (ref, label, sw) in enumerate(circuit.BUTTONS):
    r = face_parts[f"R{100 + k}"]
    if r.value != "10k" or set(r.nets.values()) != {"3V3D_F", f"BTN_{sw}_F"}:
        fb_bad.append((f"R{100 + k}", sw))
for c in ("C9", "C10", "C11"):
    if set(face_parts[c].nets.values()) != {"3V3D_F", "GND_D_F"} or face_parts[c].value != "100n":
        fb_bad.append(c)
if set(face_parts["C8"].nets.values()) != {"3V3A_F", "GND_F"} or face_parts["U1"].nets.get(HC4051_DS["VCC"]) != "3V3A_F":
    fb_bad.append("C8")
ck.check("G.faceplate_wiring_text", not fb_bad,
         f"design.md faceplate bullets: R80-R86 the button LEDs' 470s, D14-D17 on U10 QG/QF/QE/QC through R87/R88/R89/R1, "
         f"R91-R93 3k3 gate LEDs to GND_F, R100-R106 10k pull-ups to 3V3D_F, C9-C11 on 3V3D_F, C8 100n at U1's VCC; "
         f"bad {fb_bad}")
mb_bad = []
for u in ("U7", "U8"):
    n = main_parts[u].nets
    if not (n[MCP4922_DS["VDD"]] == n[MCP4922_DS["SHDN"]] == "3V3A" and n[MCP4922_DS["VREFA"]] == n[MCP4922_DS["VREFB"]] == "VREF"):
        mb_bad.append(u)
for c in ("C39", "C40"):
    if set(main_parts[c].nets.values()) != {"3V3A", "GND"}:
        mb_bad.append(c)
dec = [c for c in (f"C{k}" for k in range(31, 39)) if main_parts[c].value == "100n"]
plus = sum(1 for c in dec if set(main_parts[c].nets.values()) == {"+12V", "GND"})
minus = sum(1 for c in dec if set(main_parts[c].nets.values()) == {"-12V", "GND"})
if (plus, minus) != (4, 4):
    mb_bad.append(("C31-C38", plus, minus))
for rin, rpu, q, d, name in (("R50", "R51", "Q1", "D22", "T"), ("R52", "R53", "Q2", "D23", "X")):
    if not (set(main_parts[rin].nets.values()) == {f"{name}_CLK_IN", f"B_{name}_CLK"} and main_parts[rin].value == "100k"
            and set(main_parts[rpu].nets.values()) == {"3V3D", f"{name}_CLK"} and main_parts[rpu].value == "10k"
            and main_parts[q].nets[Q2N3904_DS["C"]] == f"{name}_CLK" and main_parts[d].nets["1"] == f"B_{name}_CLK"):
        mb_bad.append((name, "clock stage"))
for i, (name, u, s) in enumerate(circuit.GATES):
    out, inm, inp = circuit.SECTION[s]
    rg, rfb, ro = (main_parts[f"R{60 + 3 * i + k}"] for k in range(3))
    if not (main_parts[u].nets[inp] == f"GATE_{name}" and rg.value == "10k" and set(rg.nets.values()) == {"GND", f"IN_{name}"}
            and rfb.value == "15k" and ro.value == "1k" and set(ro.nets.values()) == {f"OA_{name}", name}):
        mb_bad.append((name, "gate stage"))
u6 = main_parts["U6"].nets
if not (u6[circuit.SECTION[4][0]] == u6[circuit.SECTION[4][1]] and u6[circuit.SECTION[4][2]] == "GND"):
    mb_bad.append("U6D follower")
u4 = main_parts["U4"].nets
if not (u4[circuit.SECTION[4][0]] == "NEG_REF" and u4[circuit.SECTION[4][2]] == "GND"
        and set(main_parts["R42"].nets.values()) == {"VREF", "IN_NEGREF"} and set(main_parts["R43"].nets.values()) == {"IN_NEGREF", "NEG_REF"}
        and main_parts["R42"].value == main_parts["R43"].value == "10k"):
    mb_bad.append("U4D inverter")
if not (main_parts["R47"].value == "1k5" and set(main_parts["C30"].nets.values()) == {"VREF", "GND"}
        and main_parts["R45"].value == "11k" and main_parts["R46"].value == "10k"
        and set(main_parts["R45"].nets.values()) == {"3V3A", "BIAS"} and set(main_parts["R46"].nets.values()) == {"BIAS", "GND"}
        and set(main_parts["C29"].nets.values()) == {"BIAS", "GND"} and main_parts["C29"].value == "1u"):
    mb_bad.append("reference / bias")
ck.check("G.main_board_wiring_text", not mb_bad,
         f"design.md main-board text: MCP4922 VDD + /SHDN on 3V3A, VREFA/B on VREF, C39/C40; 100n per rail per TL074 "
         f"(C31-C38); clock stages R50/R52 100k, R51/R53 10k to 3V3D, collector to the GPIO, BAT85 cathode on the base; "
         f"gate stages 10k / 15k / 1k on U6A-C, U6D grounded follower; U4D inverter R42/R43 10k; R47 1k5, C30; bias R45 "
         f"11k / R46 10k / C29 1u; bad {mb_bad}")

ck.done()
