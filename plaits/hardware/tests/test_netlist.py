"""Netlist and pinout integrity of Plaitsy (Orchid).

What it checks
  A  circuit.py on its own: unique designators per board, no single-pin nets,
     no part pin on two nets, every header pin pair used on both boards,
     faceplate nets end in _F and main-board nets never do, the two faceplate
     grounds (GND_F analog, GND_D_F digital) on the parts design.md gives them,
     the header pin orders design.md describes.
  B  circuit.py's pin maps against the manufacturers' pinouts (constants block
     below): TL074 sections and supplies, 74HC4051 channels / Z / E / VEE /
     S0..S2, 74HC595 QA..QH / QH' / SRCLR / SRCLK / RCLK / OE / SER, the
     Thonkiconn (sleeve / switch / tip, switch on the tip unplugged), the Alpha
     pot (CW raises the reading, checked on the footprint in the front view),
     the Thonk LED button (contacts 1+2 / 3+4, LED 5 / 6), the 3-lead
     bicolour LED, the Daisy Seed pin numbers against its datasheet and
     libDaisy, the breakout's J1 / J3 / J4 / J5 against Rob Heel's Gerbers and
     silkscreen, and the BAT85 clamps: cathode in the symbol AND the footprint
     the routed master uses, then which way each conducts.
  D  Both exports (the routed master Plaits-routed.epro2 and the generated
     Plaits.epro2): every pad's net on both PCBs against circuit.py, pad by
     pad; designators complete; no stray nets; DIP numbering; layers.
  E  Header stacking: each HFn pin over its Hn pin (same x / y within 0.05 mm)
     with the net pair circuit.HEADERS gives; GND_F and GND_D_F never meet on
     the faceplate's copper and do meet on the main board's GND.
  F  The schematic pages of both exports against circuit.py (pin positions
     joined to named wires and net flags).
  G  design.md's tables (Seed pin map, CV inputs, mux, 595, headers, the
     faceplate circuits text) and firmware/test/board_tables.h against
     circuit.py and the datasheet pinouts.

Run from plaits/hardware/tests:  python test_netlist.py
Only reads: imports circuit.py, opens the two exports as zip files, reads the docs.
"""
import collections
import json
import math
import os
import re

import harness

ck = harness.Checks("netlist")
circuit = harness.load("circuit")
MIL = harness.MIL

# ==========================================================================================================
# Datasheet constants (pin numbers are exact facts: no min / typ / max). Positions in mm.
# ----------------------------------------------------------------------------------------------------------
# TI SLOS080W "TL07xx Low-Noise FET-Input Operational Amplifiers" (rev. July 2025), Pin Functions, N (PDIP-14):
TL074_DS = {"1OUT": "1", "1IN-": "2", "1IN+": "3", "VCC+": "4", "2IN+": "5", "2IN-": "6", "2OUT": "7",
            "3OUT": "8", "3IN-": "9", "3IN+": "10", "VCC-": "11", "4IN+": "12", "4IN-": "13", "4OUT": "14"}
# TI SCHS122O "CD74HC4051 ... Analog Multiplexers" (rev. Jan 2026), Pin Configuration (PDIP-16): channels A0..A7,
# common A ("Z" in NXP's 74HC4051 sheet), E active LOW (low = a channel is on), VEE pin 7, GND 8, VCC 16.
HC4051_CH = {0: "13", 1: "14", 2: "15", 3: "12", 4: "1", 5: "5", 6: "2", 7: "4"}
HC4051_DS = {"Z": "3", "E": "6", "VEE": "7", "GND": "8", "S2": "9", "S1": "10", "S0": "11", "VCC": "16"}
# TI SCLS041J "SNx4HC595 8-Bit Shift Registers With 3-State Output Registers" (rev. Oct 2021), Table 5-1, PDIP-16:
HC595_DS = {"QB": "1", "QC": "2", "QD": "3", "QE": "4", "QF": "5", "QG": "6", "QH": "7", "GND": "8", "QH'": "9",
            "SRCLR": "10", "SRCLK": "11", "RCLK": "12", "OE": "13", "SER": "14", "QA": "15", "VCC": "16"}
HC595_Q = ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH"]
# SRCLR and OE are active LOW (SCLS041J function table): SRCLR must sit HIGH, OE LOW for the outputs to drive.
# Thonk "Thonkiconn 3.5mm switching jack socket" drawing PJ398SM (thonk.co.uk/wp-content/uploads/2018/07/
# Thonkiconn_Jack_Datasheet-new.jpg, read 2026-11-13): schematic 1 = sleeve, 2 = switch, 3 = tip spring, the
# switch's contact drawn ON the tip spring (normally closed: the tip connects to pin 2 with no plug in).
# PCB layout (top view): pin 2 3.10 mm from pin 1, barrel centre 6.48 mm from pin 1, pin 3 4.92 mm beyond the barrel.
# KiCad Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles.kicad_mod agrees: S (0, 0), TN (0, 3.1), T (0, 11.4).
JACK_DS = {"S": "1", "TN": "2", "T": "3", "S_TN": 3.10, "S_T": 6.48 + 4.92, "S_barrel": 6.48}
# Taiwan Alpha drawing SLH-211-414, RD901F-40-(L)R1-XXX-0XD (in Tayda's spec SP26020021, 2026-02-04): front view
# from the shaft with the pins at the bottom, terminals 1 2 3 left to right, "shaft shown in full C.C.W. position",
# the circuit's wiper at terminal 1 there and the rotation arrow clockwise: turning CW moves the wiper 1 -> 3.
# The A taper is specified as V1-2 / V1-3 (10-25 % at 150 deg), the same convention. PCB hole detail: pins 2.5 mm
# apart (5.0 over three), the pin row 7.5 mm from the shaft / lug line, lug slots 1.8 x 1.1 mm 11.4 mm overall
# (centres +-4.8 mm), pin holes 1.0 mm.
ALPHA_DS = {"pitch": 2.5, "row_to_shaft": 7.5, "lug_x": 4.8, "pin_hole": 1.0}
# Thonk low-profile LED button drawing "TACT SWITCH" PB01-109TL rev A (thonk.co.uk/wp-content/uploads/2021/12/
# LowProfileButton.pdf, read 2026-11-13): CIRCUIT 1 and 2 joined, 3 and 4 joined, the switch between the pairs;
# LED L1 (+, anode) to L2 (-, cathode). Pin view: 1 and 2 along one edge, 3 and 4 along the other, 1 above 3,
# 2 above 4, L1 on the 1 / 3 side and L2 on the 2 / 4 side. Switch legs 5.08 mm apart, LED legs 5.4 mm apart.
# LED material GaAsP / GaP, rating 12 V DC 50 mA (switch). No built-in resistor shown.
BUTTON_DS = {"pair_a": ("1", "2"), "pair_b": ("3", "4"), "L1_anode": "5", "L2_cathode": "6", "sw_pitch": 5.08,
             "led_pitch": 5.4}
# Electrosmith Daisy Seed datasheet v1.0.5, Pinout figure and Table 2 (pin -> Daisy pin name, STM32 pin):
SEED_DS = {"1": "D0", "2": "D1", "3": "D2", "4": "D3", "5": "D4", "6": "D5", "7": "D6", "8": "D7", "9": "D8",
           "10": "D9", "11": "D10", "12": "D11", "13": "D12", "14": "D13", "15": "D14", "16": "AIN1", "17": "AIN2",
           "18": "AOUT1", "19": "AOUT2", "20": "AGND", "21": "3V3A", "22": "D15/A0", "23": "D16/A1", "24": "D17/A2",
           "25": "D18/A3", "26": "D19/A4", "27": "D20/A5", "28": "D21/A6", "29": "D22/A7", "30": "D23/A8",
           "31": "D24/A9", "32": "D25/A10", "33": "D26", "34": "D27", "35": "D28/A11", "36": "D29", "37": "D30",
           "38": "3V3D", "39": "VIN", "40": "DGND"}
# Same datasheet, Pinout: pin 9 = SPI1 SCK, pin 10 = SPI1 MISO, pin 11 = SPI1 MOSI. Table 1: every GPIO is 5 V
# tolerant except pins 24, 25, 28, 29, 30 (3.3 V tolerant). Table 2 STM32 pins of the ADC inputs:
SEED_SPI = {"SCK": "9", "MISO": "10", "MOSI": "11"}
SEED_STM32 = {"22": "PC0", "23": "PA3", "24": "PB1", "25": "PA7", "26": "PA6", "27": "PC1", "28": "PC4",
              "29": "PA5", "30": "PA4", "31": "PA1", "32": "PA0", "33": "PD11", "34": "PG9", "35": "PA2",
              "1": "PB12", "2": "PC11", "3": "PC10", "4": "PC9", "9": "PG11", "11": "PB5", "14": "PB6", "15": "PB7"}
# Seed pin numbering, top view (components up): counter-clockwise like a DIP, pins 1 / 40 at the USB end.
# Rob Heel's seed_power_opamps breakout (github.com/rob-scape/daisy-seed-breakout-boards, folder
# daisy-seed-dcdc-opamps, Gerbers + Excellon of 2025-08-29, BOM_seed_power_opamps_2025-08-29.csv), traced
# 2026-11-13 from the copper layers and the drill file: the Seed's 40 holes (1.2 mm) in two rows 15.24 mm apart;
# a 1x4 (0.889 mm holes) continues each row 2.54 mm beyond pins 1 / 40 (J5 on the pin 1-20 row, J4 on the 21-40
# row); the other two 1x4 sit beyond pins 20 / 21 after ONE empty position (J1 on the 1-20 row, J3 on 21-40).
# Copper: the 10-pin power header J2 pins 1 / 2 (-12 V) -> D3 B5819W -> J1's three outer pins; J2 9 / 10 (+12 V)
# -> D2 -> J3's three outer pins; J1 / J3's pin next to the Seed = GND (silk "GND"); J4 / J5: outer pin (square,
# pin 1) and the third = signal, the second and the one next to the Seed = GND; bottom silkscreen "A OUT 1, GND,
# A OUT 2, GND" on the 21-40 row's 1x4 (J4) and "A IN 1, GND, A IN 2, GND" on the 1-20 row's (J5). Seed pins 20
# (AGND) and 40 (DGND) on the breakout's one GND; pin 39 (VIN) on the DC/DC output; no breakout copper on any other
# Seed pin except the codec pins 16-19. (Which op-amp channel ends on which J4 pin is taken from the silkscreen,
# not traced through the op-amps.)
BREAKOUT = {
    "row_gap": 15.24, "pitch": 2.54,
    "nets": {"J1-1": "GND", "J1-2": "-12V", "J1-3": "-12V", "J1-4": "-12V",
             "J3-1": "GND", "J3-2": "+12V", "J3-3": "+12V", "J3-4": "+12V",
             "J4-1": "AOUT1", "J4-2": "GND", "J4-3": "AOUT2", "J4-4": "GND",
             "J5-1": "AIN1", "J5-2": "GND", "J5-3": "AIN2", "J5-4": "GND"},
    # positions along a row in pitches from the Seed's end pin (pin 1 / 40 for J5 / J4, pin 20 / 21 for J1 / J3)
    "offset": {"J5": (1, 2, 3, 4), "J4": (1, 2, 3, 4), "J1": (2, 3, 4, 5), "J3": (2, 3, 4, 5)},
    "seed_pins_used": {"16", "17", "18", "19", "20", "39", "40"},
}
# BAT85 (Vishay BAT85 doc 85661 / NXP BAT85 SOD68): the band marks the cathode. 3-lead bicolour LED: see LED_DS.
# 3 mm red / green bicolour LED, common cathode, 3 leads: the part bom.py names is Tayda's SKU A-8599 ("Bi-color
# LED Red/Green 3mm Common Cathode", OEM, no datasheet). Its product drawing (taydaelectronics.com image 36_4.jpg,
# read in the browser pane 2026-11-13): leads A, C, B side by side, C (the longest, in the middle) = common
# cathode, A (outer, medium length) = red anode, B (other outer, shortest) = green anode. No pitch given; three
# leads inside a 3 mm body cannot be further apart than about 1.27 mm.
LED_DS = {"A_R": "1", "K": "2", "A_G": "3", "confirmed": True, "lead_order": ("A red", "C cathode", "B green")}

# ==========================================================================================================
# A  circuit.py on its own
MB, FB = circuit.main_board_parts(), circuit.faceplate_parts()
MBN, FBN = circuit.nets_of(MB), circuit.nets_of(FB)
PARTS = {"main": {p.ref: p for p in MB}, "face": {p.ref: p for p in FB}}
ALL = list(MB) + list(FB)

for name, parts in (("main", MB), ("face", FB)):
    dup = [r for r, n in collections.Counter(p.ref for p in parts).items() if n > 1]
    ck.check(f"A.unique_refs.{name}", not dup, f"expected no duplicate designators, got {dup}")
    nets = circuit.nets_of(parts)
    single = {n: v for n, v in nets.items() if len(v) < 2}
    ck.check(f"A.no_single_pin_nets.{name}", not single, f"expected every net on >= 2 pins, got {single}")
    pins = collections.Counter((p.ref, pid) for p in parts for pid in p.nets)
    twice = [k for k, n in pins.items() if n > 1]
    ck.check(f"A.no_pin_on_two_nets.{name}", not twice, f"part pins listed twice: {twice}")
    none_net = [(p.ref, pid) for p in parts for pid, n in p.nets.items() if not n]
    ck.check(f"A.no_empty_net_names.{name}", not none_net, f"pins with an empty net name: {none_net}")

bad_pairs = []
for ref, kind, pins in circuit.HEADERS:
    for i, (a, b) in enumerate(pins):
        if len(MBN.get(a, [])) < 2 or len(FBN.get(b, [])) < 2:
            bad_pairs.append((ref, i + 1, a, b, len(MBN.get(a, [])), len(FBN.get(b, []))))
ck.check("A.header_nets_used_both_boards", not bad_pairs,
         f"expected every header pin's main net on >= 2 main pins and its faceplate net on >= 2 faceplate pins, "
         f"got {bad_pairs}")
pair_bad = [(ref, i + 1, a, b) for ref, _, pins in circuit.HEADERS for i, (a, b) in enumerate(pins)
            if not (b == a + "_F" or (a == "GND" and b in ("GND_F", "GND_D_F"))
                    or (a, b) in (("SPI_MOSI", "MOSI_F"), ("SPI_SCK", "SCK_F")))]
ck.check("A.header_pair_names", not pair_bad, f"X -> X_F (GND -> GND_F / GND_D_F, SPI_* -> *_F): {pair_bad}")
# circuit.py's convention: nets that cross a header end in _F on the faceplate; board-local ones (SR_CHAIN, the
# L_* / LED_* lines) may keep a plain name, but then must not touch a header pin
hdr_fb = {b for _, _, pins in circuit.HEADERS for a, b in pins}
fb_bad = sorted(n for n in FBN if not n.endswith("_F") and (n in hdr_fb or any(p.startswith("HF") for p in FBN[n])))
mb_bad = sorted(n for n in MBN if n.endswith("_F"))
ck.check("A.faceplate_header_nets_end_in_F", not fb_bad and all(b.endswith("_F") for b in hdr_fb),
         f"faceplate nets on a header pin all end in _F; bad {fb_bad}")
ck.check("A.main_nets_never_F", not mb_bad, f"expected no main-board net *_F, got {mb_bad}")
shared = sorted(set(MBN) & set(FBN))
ck.check("A.no_net_on_both_boards", not shared, f"expected no net name on both boards, got {shared}")
hdr_mb = {a for _, _, pins in circuit.HEADERS for a, b in pins}
named_pairs = sorted(n[:-2] for n in FBN if n.endswith("_F") and n[:-2] in MBN and n[:-2] not in hdr_mb)
ck.check("A.cross_board_names_only_via_headers", not named_pairs,
         f"X / X_F pairs on the two boards with no header pin joining them: {named_pairs}")
hdr_ok = all(len(PARTS["main"][ref].nets) == len(pins) == len(PARTS["face"][circuit.fb_ref(ref)].nets)
             and all(PARTS["main"][ref].nets[str(i + 1)] == a and PARTS["face"][circuit.fb_ref(ref)].nets[str(i + 1)] == b
                     for i, (a, b) in enumerate(pins))
             for ref, _, pins in circuit.HEADERS)
ck.check("A.header_parts_match_HEADERS", hdr_ok, "H<n> / HF<n> pin nets equal circuit.HEADERS on both boards")
npins = sum(len(p) for _, _, p in circuit.HEADERS)
kinds_ok = all(int(kind[3:]) == len(pins) for _, kind, pins in circuit.HEADERS)
ck.check("A.header_kind_matches_pin_count", kinds_ok,
         f"HDRn kind = pin count: {[(r, k, len(p)) for r, k, p in circuit.HEADERS]}")
# design.md: "each supply next to its ground", "OUT and AUX kept apart by GND and 3V3A"
adj_bad = []
for ref, _, pins in circuit.HEADERS:
    mb = [a for a, b in pins]
    for i, (a, b) in enumerate(pins):
        if a in ("3V3A", "3V3D"):
            neigh = [pins[j][0] for j in (i - 1, i + 1) if 0 <= j < len(pins)]
            if "GND" not in neigh:
                adj_bad.append((ref, i + 1, a, neigh))
h2 = [a for a, b in dict((r, p) for r, _, p in circuit.HEADERS)["H2"]]
apart = abs(h2.index("OUT") - h2.index("AUX")) >= 2 and all(
    x in h2[min(h2.index("OUT"), h2.index("AUX")) + 1:max(h2.index("OUT"), h2.index("AUX"))] for x in ("GND", "3V3A"))
ck.check("A.supply_beside_ground", not adj_bad, f"design.md: each supply next to its ground; bad {adj_bad}")
ck.check("A.OUT_AUX_apart_by_GND_3V3A", apart, f"design.md: OUT and AUX kept apart by GND and 3V3A; H2 = {h2}")
# GND_F (jacks, pots, mux) and GND_D_F (LEDs, buttons, shift registers) as design.md splits them
gf = {p.split(".")[0] for p in FBN["GND_F"]}
gd = {p.split(".")[0] for p in FBN["GND_D_F"]}
kind_of = {p.ref: p.kind for p in FB}
gf_kinds = collections.Counter(kind_of[r] for r in gf)
gd_kinds = collections.Counter(kind_of[r] for r in gd)
ck.check("A.GND_F_parts", set(gf_kinds) <= {"JACK", "POT", "MUX", "C", "HDR9", "HDR8"}
         and not any(kind_of[r] in ("HC595", "LED_RG", "SWLED") for r in gf),
         f"design.md: GND_F = jacks, pots, mux (+ C8, H2); got {dict(gf_kinds)}")
# [2026-11-14: + the shift registers' clock pull-downs R14 / R15 (resistors whose other end is a 595 clock)]
_pull = {r for r in gd if kind_of[r] == "R" and set(next(p for p in FB if p.ref == r).nets.values()) - {"GND_D_F"}
         <= {"SCK_F", "LED_LATCH_F"}}
ck.check("A.GND_D_F_parts", set(gd_kinds) <= {"HC595", "LED_RG", "SWLED", "C", "HDR9", "R"}
         and all(r in _pull for r in gd if kind_of[r] == "R")
         and not any(kind_of[r] in ("JACK", "POT", "MUX") for r in gd),
         f"design.md: GND_D_F = LEDs, buttons, shift registers and their clock pull-downs (+ C9, C10, H3); got "
         f"{dict(gd_kinds)}, pull-downs {sorted(_pull)}")
c_on = {c: set(PARTS["face"][c].nets.values()) for c in ("C8", "C9", "C10")}
ck.check("A.decoupler_grounds", c_on["C8"] == {"3V3A_F", "GND_F"} and c_on["C9"] == c_on["C10"] == {"3V3D_F", "GND_D_F"},
         f"C8 on 3V3A_F / GND_F (mux), C9 / C10 on 3V3D_F / GND_D_F (595s): {c_on}")

# ==========================================================================================================
# B  pin maps against the datasheets
sec_ds = {s: (TL074_DS[f"{s}OUT"], TL074_DS[f"{s}IN-"], TL074_DS[f"{s}IN+"]) for s in (1, 2, 3, 4)}
ck.check("B.TL074_SECTION", circuit.SECTION == sec_ds, f"expected {sec_ds}, got {circuit.SECTION}")
for u in ("U3", "U4"):
    n = PARTS["main"][u].nets
    ck.check(f"B.TL074_supply.{u}", n.get(TL074_DS["VCC+"]) == "+12V" and n.get(TL074_DS["VCC-"]) == "-12V",
             f"expected pin 4 +12V, pin 11 -12V; got 4={n.get('4')}, 11={n.get('11')}")
    ck.check(f"B.TL074_all_pins_used.{u}", set(n) == set(TL074_DS.values()), f"pins {sorted(n, key=int)}")
# every CV stage: Rin from CV_x to IN-, Rf IN- to OUT, Cf across, Rs OUT to ADC, IN+ on the bias
stage_bad = []
for name, label, u, s, rf, cf, bias in circuit.CV_CHANNELS:
    n = PARTS["main"][u].nets
    o, m, p = (TL074_DS[f"{s}OUT"], TL074_DS[f"{s}IN-"], TL074_DS[f"{s}IN+"])
    if (n[o], n[m], n[p]) != (f"OA_{name}", f"IN_{name}", bias):
        stage_bad.append((name, u, s, n[o], n[m], n[p]))
    r_in = [q for q in MB if q.kind == "R" and set(q.nets.values()) == {f"CV_{name}", f"IN_{name}"}]
    r_f = [q for q in MB if q.kind == "R" and set(q.nets.values()) == {f"IN_{name}", f"OA_{name}"}]
    c_f = [q for q in MB if q.kind == "C" and set(q.nets.values()) == {f"IN_{name}", f"OA_{name}"}]
    r_s = [q for q in MB if q.kind == "R" and set(q.nets.values()) == {f"OA_{name}", f"ADC_{name}"}]
    if not (len(r_in) == len(r_f) == len(c_f) == len(r_s) == 1 and r_f[0].value == rf and c_f[0].value == cf):
        stage_bad.append((name, [q.ref for q in r_in + r_f + c_f + r_s]))
ck.check("B.CV_stages_wired", not stage_bad, f"OUT = OA_x, IN- = IN_x, IN+ = bias, one Rin / Rf / Cf / Rs each: {stage_bad}")

# 74HC4051
mux = PARTS["face"]["U1"].nets
mux_want = {HC4051_DS["Z"]: "MUX_OUT_F", HC4051_DS["E"]: "GND_F", HC4051_DS["VEE"]: "GND_F",
            HC4051_DS["GND"]: "GND_F", HC4051_DS["S0"]: "MUX_S0_F", HC4051_DS["S1"]: "MUX_S1_F",
            HC4051_DS["S2"]: "MUX_S2_F", HC4051_DS["VCC"]: "3V3A_F"}
ck.check("B.HC4051_control_pins", all(mux.get(k) == v for k, v in mux_want.items()),
         f"Z 3 = MUX_OUT_F, E 6 low (GND_F: enabled), VEE 7 / GND 8 = GND_F, S0 11 / S1 10 / S2 9, VCC 16 = 3V3A_F; "
         f"got { {k: mux.get(k) for k in mux_want} }")
ch_bad = [(ref, mpin, ch, HC4051_CH[ch]) for ref, label, wiper, mpin, ch in circuit.POTS if HC4051_CH[ch] != mpin
          or mux.get(mpin) != wiper]
ck.check("B.HC4051_pot_channels", not ch_bad, f"POTS' (4051 pin, channel) against SCHS122O's channel pins: {ch_bad}")
used_ch = {ch for *_, ch in circuit.POTS}
spare = sorted(set(range(8)) - used_ch)
ck.check("B.HC4051_spare_channel_grounded", all(mux.get(HC4051_CH[c]) == "GND_F" for c in spare) and spare == [7],
         f"unused channel(s) {spare} on GND_F: { {c: mux.get(HC4051_CH[c]) for c in spare} }")
ck.check("B.HC4051_all_pins_tied", len(mux) == 16, f"{len(mux)} of 16 pins have a net (no floating input)")
mux_pins_once = collections.Counter(wiper for *_, wiper, mpin, ch in [(r, l, w, m, c) for r, l, w, m, c in circuit.POTS])
ck.check("B.HC4051_one_pot_per_channel", len({m for _, _, _, m, _ in circuit.POTS}) == len(circuit.POTS),
         f"4051 pins {[m for _, _, _, m, _ in circuit.POTS]}")

# 74HC595
ck.check("B.HC595_OUTS_QA_to_QH", circuit.HC595_OUTS == [HC595_DS[q] for q in HC595_Q],
         f"expected {[HC595_DS[q] for q in HC595_Q]} (QA..QH), got {circuit.HC595_OUTS}")
for u, ser in (("U9", "MOSI_F"), ("U10", "SR_CHAIN")):
    n = PARTS["face"][u].nets
    want = {"SRCLR": "3V3D_F", "OE": "GND_D_F", "SRCLK": "SCK_F", "RCLK": "LED_LATCH_F", "SER": ser,
            "VCC": "3V3D_F", "GND": "GND_D_F"}
    got = {k: n.get(HC595_DS[k]) for k in want}
    ck.check(f"B.HC595_control.{u}", got == want,
             f"SRCLR 10 high (3V3D_F), OE 13 low (GND_D_F), SRCLK 11 = SCK_F, RCLK 12 = LED_LATCH_F, SER 14 = {ser}; "
             f"got {got}")
    q_nets = [n.get(HC595_DS[q]) for q in HC595_Q]
    ck.check(f"B.HC595_outputs_drive_LED_lines.{u}", all(x and x.startswith("L_D") for x in q_nets),
             f"QA..QH all on L_D* lines: {q_nets}")
ck.check("B.HC595_chain", PARTS["face"]["U9"].nets.get(HC595_DS["QH'"]) == "SR_CHAIN"
         and PARTS["face"]["U10"].nets.get(HC595_DS["SER"]) == "SR_CHAIN" and HC595_DS["QH'"] not in PARTS["face"]["U10"].nets,
         "U9 QH' (9) -> U10 SER (14); U10 QH' open")
# red lines from U9, green from U10, through 470R to the LED anode pins
led_bad = []
for u, colour in (("U9", "R"), ("U10", "G")):
    for q in HC595_Q:
        line = PARTS["face"][u].nets[HC595_DS[q]]
        m = re.fullmatch(r"L_(D\d)_([RG])", line)
        if not m or m.group(2) != colour:
            led_bad.append((u, q, line))
            continue
        res = [p for p in FB if p.kind == "R" and set(p.nets.values()) == {line, f"LED_{m.group(1)}_{colour}"}]
        led = PARTS["face"][m.group(1)].nets
        pin = LED_DS["A_R"] if colour == "R" else LED_DS["A_G"]
        if len(res) != 1 or res[0].value != "470" or led.get(pin) != f"LED_{m.group(1)}_{colour}":
            led_bad.append((u, q, line, [r.ref for r in res], led))
ck.check("B.LED_lines_595_to_anodes", not led_bad, f"U9 -> reds, U10 -> greens, each through one 470R to the anode: {led_bad}")
ck.check("B.LED_cathodes", all(PARTS["face"][f"D{k}"].nets.get(LED_DS["K"]) == "GND_D_F" for k in range(1, 9)),
         "every LED's common cathode (pin 2) on GND_D_F")

# Thonkiconn: 1 sleeve, 2 switch (touches the tip unplugged), 3 tip
jack_bad = []
for ref, label, tip, tn in circuit.JACKS:
    n = PARTS["face"][ref].nets
    if n.get(JACK_DS["S"]) != "GND_F" or n.get(JACK_DS["T"]) != tip or n.get(JACK_DS["TN"]) != tn:
        jack_bad.append((ref, n))
ck.check("B.jacks_S_TN_T", not jack_bad, f"expected 1 = sleeve GND_F, 2 = switch lug, 3 = tip; bad {jack_bad}")


def unplugged(ref):
    """What the tip net sees with no plug in: the switch lug (pin 2) closes onto the tip (Thonk drawing)."""
    n = PARTS["face"][ref].nets
    lug = n.get(JACK_DS["TN"])
    if lug is None:
        return "open"
    if lug == "GND_F":
        return "ground"
    rs = [p for p in FB if p.kind == "R" and lug in p.nets.values()]
    if len(rs) == 1 and set(rs[0].nets.values()) == {lug, "PROBE_F"}:
        return f"probe via {rs[0].value}"
    return f"? {lug}"


norm = {label: unplugged(ref) for ref, label, tip, tn in circuit.JACKS}
want_norm = {"MODEL": "ground", "HARMO": "ground", "V/OCT": "ground", "TIMBRE": "probe via 10k", "FM": "probe via 10k",
             "MORPH": "probe via 10k", "TRIG": "probe via 10k", "LEVEL": "probe via 10k", "OUT": "open", "AUX": "open"}
ck.check("B.jack_normalling", norm == want_norm,
         f"design.md: MODEL / HARMONICS / V/OCT read 0 V unpatched, TIMBRE / FM / MORPH / TRIG / LEVEL get the probe "
         f"through 10k, OUT / AUX open; got {norm}")
probe_r = sorted(p.ref for p in FB if p.kind == "R" and "PROBE_F" in p.nets.values())
ck.check("B.probe_resistors_R9_R13", probe_r == ["R10", "R11", "R12", "R13", "R9"],
         f"design.md: R9-R13 from PROBE_F to the five switch lugs; got {probe_r}")

# Alpha pots: 1 = CCW end on GND_F, 2 = wiper, 3 = CW end on 3V3A_F, lugs 4 / 5 on GND_F
pot_bad = [(ref, PARTS["face"][ref].nets) for ref, *_ in circuit.POTS
           if PARTS["face"][ref].nets.get("1") != "GND_F" or PARTS["face"][ref].nets.get("3") != "3V3A_F"
           or PARTS["face"][ref].nets.get("4") != "GND_F" or PARTS["face"][ref].nets.get("5") != "GND_F"]
ck.check("B.pots_CCW_GND_CW_3V3A", not pot_bad, f"pin 1 (CCW) GND_F, pin 3 (CW) 3V3A_F: clockwise raises the reading; {pot_bad}")

# Thonk LED button
btn_bad = []
for ref, label, sw in circuit.BUTTONS:
    n = PARTS["face"][ref].nets
    a = {n.get(p) for p in BUTTON_DS["pair_a"]}
    b = {n.get(p) for p in BUTTON_DS["pair_b"]}
    if a != {"GND_D_F"} or b != {f"BTN_{sw}_F"} or n.get(BUTTON_DS["L2_cathode"]) != "GND_D_F" \
            or not str(n.get(BUTTON_DS["L1_anode"])).startswith("BTN_LED_"):
        btn_bad.append((ref, n))
ck.check("B.buttons_vs_Thonk_PB01_109TL", not btn_bad,
         f"1+2 one contact (GND_D_F), 3+4 the other (BTN_x_F), L1 anode 5 from the 470R, L2 cathode 6 GND_D_F; {btn_bad}")

# Daisy Seed: circuit.SEED's names against the datasheet
seed_bad = [(pin, name, SEED_DS.get(pin)) for pin, (name, net) in circuit.SEED.items()
            if not pin.startswith("J") and SEED_DS.get(pin) != name]
ck.check("B.Seed_pin_names_vs_datasheet", not seed_bad and len([p for p in circuit.SEED if not p.startswith("J")]) == 40,
         f"Seed datasheet v1.0.5 pin -> name; differences {seed_bad}")
power = {"20": "GND", "40": "GND", "21": "3V3A", "38": "3V3D"}
ck.check("B.Seed_power_pins", all(circuit.SEED[p][1] == n for p, n in power.items()) and circuit.SEED["39"][1] is None,
         f"AGND 20 / DGND 40 on GND, 3V3A 21, 3V3D 38, VIN 39 left to the breakout; got "
         f"{ {p: circuit.SEED[p] for p in ('20', '21', '38', '39', '40')} }")
ck.check("B.Seed_SPI1_pins", circuit.SEED[SEED_SPI["SCK"]][1] == "SPI_SCK" and circuit.SEED[SEED_SPI["MOSI"]][1] == "SPI_MOSI",
         f"datasheet: SPI1 SCK pin 9, MOSI pin 11; got 9={circuit.SEED['9']}, 11={circuit.SEED['11']}")
adc_pins = {n: p for p, (nm, n) in circuit.SEED.items() if n and n.startswith("ADC_")}
not_adc = [(n, p, SEED_DS[p]) for n, p in adc_pins.items() if "/A" not in SEED_DS[p]]
ck.check("B.Seed_ADC_nets_on_ADC_pins", not not_adc and "/A" in SEED_DS[[p for p, (nm, n) in circuit.SEED.items()
                                                                           if n == "MUX_OUT"][0]],
         f"every ADC_* net and MUX_OUT on an A pin; bad {not_adc}")
codec = [p for p in ("16", "17", "18", "19") if circuit.SEED[p][1]]
ck.check("B.Seed_codec_pins_left_to_breakout", not codec,
         f"the breakout's op-amps sit on pins 16-19 (its Gerbers); Plaitsy must not use them: {codec}")
other_used = sorted((set(BREAKOUT["seed_pins_used"]) - {"20", "40"}) & {p for p, (nm, n) in circuit.SEED.items() if n})
ck.check("B.Seed_pins_breakout_drives_unused", not other_used,
         f"pins the breakout drives (16-19 codec, 39 VIN) carry no Plaitsy net: {other_used}")

# libDaisy names -> STM32 pins (daisy_seed.h of libDaisy v9; the Seed datasheet's Table 2 gives the same pins)
# libDaisy v9.0.0 src/daisy_seed.h, namespace seed (constexpr Pin D0 = Pin(PORTB, 12) ...; A0 = D15 ... A11 = D28),
# copied here so the test does not depend on the download:
LIBDAISY_PINS = {"D0": "PB12", "D1": "PC11", "D2": "PC10", "D3": "PC9", "D4": "PC8", "D5": "PD2", "D6": "PC12",
                 "D7": "PG10", "D8": "PG11", "D9": "PB4", "D10": "PB5", "D11": "PB8", "D12": "PB9", "D13": "PB6",
                 "D14": "PB7", "D15": "PC0", "D16": "PA3", "D17": "PB1", "D18": "PA7", "D19": "PA6", "D20": "PC1",
                 "D21": "PC4", "D22": "PA5", "D23": "PA4", "D24": "PA1", "D25": "PA0", "D26": "PD11", "D27": "PG9",
                 "D28": "PA2", "D29": "PB14", "D30": "PB15"}
LIBDAISY_PINS.update({f"A{k}": LIBDAISY_PINS[f"D{d}"] for k, d in enumerate(list(range(15, 26)) + [28])})
lib_bad = []
for pin, (name, net) in circuit.SEED.items():
    if pin.startswith("J") or not net or net in ("GND", "3V3A", "3V3D"):
        continue
    names = name.split("/")
    want = SEED_STM32.get(pin)
    for nm in names:
        if nm in LIBDAISY_PINS and LIBDAISY_PINS[nm] != want:
            lib_bad.append((pin, nm, LIBDAISY_PINS[nm], want))
ck.check("B.libDaisy_names_vs_Seed_STM32_pins", not lib_bad,
         f"libDaisy seed::Dn / An port pins against the datasheet's Table 2 for every used pin: {lib_bad}")
# the breakout's header pin functions (Gerber trace + silkscreen) against circuit.SEED's names and nets
bk_bad = []
NAME_OF = {"GND": "GND", "-12V": "-12V", "+12V": "+12V", "AOUT1": "AOUT1", "AOUT2": "AOUT2", "AIN1": "AIN1", "AIN2": "AIN2"}
for pin, fn in BREAKOUT["nets"].items():
    name, net = circuit.SEED[pin]
    want_net = {"GND": "GND", "-12V": "-12V", "+12V": "+12V", "AOUT1": "OUT", "AOUT2": "AUX"}.get(fn)
    if name != NAME_OF[fn] or net != want_net:
        bk_bad.append((pin, "circuit", name, net, "breakout", fn, want_net))
ck.check("B.breakout_J1_J3_J4_J5_functions", not bk_bad,
         f"J1 GND + -12V x3, J3 GND + +12V x3, J4 AOUT1/GND/AOUT2/GND (OUT, AUX), J5 inputs unused: {bk_bad}")


# ==========================================================================================================
# Export parsing (records from harness.read_export; positions via harness.routed())
def doc_meta(doc):
    return next((p for h, p in doc["recs"] if h["type"] == "META"), {})


def rid(h):
    i = h.get("id")
    return json.loads(i) if isinstance(i, str) and i.startswith("[") else i


class Export:
    def __init__(self, path):
        self.path = path
        self.docs = harness.read_export(path)
        self.devices = {u: doc_meta(d).get("attributes", {}) for u, d in self.docs.items() if d["docType"] == "DEVICE"}
        self.boards = {u: doc_meta(d).get("title") for u, d in self.docs.items() if d["docType"] == "BOARD"}

    def board_title(self, ref_id):
        """BOARD title for a (possibly 16-character, truncated) board uuid."""
        if not ref_id:
            return None
        return next((t for u, t in self.boards.items() if u.startswith(ref_id) or ref_id.startswith(u)), None)

    def of_type(self, t):
        return {u: d for u, d in self.docs.items() if d["docType"] == t}

    def pcb(self, title):
        return next((d for d in self.of_type("PCB").values() if doc_meta(d).get("title") == title), None)

    def footprint_pads(self, uid):
        pads = {}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "PAD":
                pads[str(p["num"])] = (p["centerX"] * MIL, p["centerY"] * MIL, p["defaultPad"]["padType"],
                                       p.get("hole") and p["hole"]["width"] * MIL)
        return pads

    def symbol_pins(self, uid):
        pins, out = {}, {}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "PIN":
                pins[h["id"]] = {"x": p["x"], "y": p["y"], "part": p.get("partId")}
        for h, p in self.docs[uid]["recs"]:
            if h["type"] == "ATTR" and p.get("parentId") in pins:
                pins[p["parentId"]][p["key"]] = p["value"]
        for q in pins.values():
            out[q.get("Pin Number")] = (q.get("Pin Name"), q["x"], q["y"], q["part"])
        return out

    def symbol_polys(self, uid):
        return [[(pt["x"], pt["y"]) for pt in p["points"]] for h, p in self.docs[uid]["recs"]
                if h["type"] == "POLY" and "points" in p]


def pcb_components(doc):
    """{designator: {...}} with x, y (mm), angle, bottom, footprint, device, nets {pad num: net}; plus duplicates."""
    comps, attrs = {}, collections.defaultdict(dict)
    for h, p in doc["recs"]:
        if h["type"] == "COMPONENT":
            comps[h["id"]] = p
    for h, p in doc["recs"]:
        if h["type"] == "ATTR" and p.get("parentId") in comps:
            attrs[p["parentId"]][p["key"]] = p["value"]
    padnet = collections.defaultdict(dict)
    for h, p in doc["recs"]:
        if h["type"] == "PAD_NET":
            _, cid, num, _pid = rid(h)
            if p.get("padNet"):
                padnet[cid][str(num)] = p["padNet"]
    out, dups = {}, []
    for cid, p in comps.items():
        a = attrs[cid]
        ref = a.get("Designator")
        if not ref:
            continue
        if ref in out:
            dups.append(ref)
        out[ref] = {"id": cid, "x": p["x"] * MIL, "y": p["y"] * MIL, "angle": (p.get("angle") or 0) % 360,
                    "bottom": p.get("layerId") == 2, "footprint": a.get("Footprint"), "device": a.get("Device"),
                    "nets": padnet[cid]}
    return out, dups


def pad_xy(comp, local):
    """Board position of a footprint-local pad: a bottom-layer part mirrors y, then rotates (easyeda-format.md)."""
    px, py = local[0], local[1]
    if comp["bottom"]:
        py = -py
    a = math.radians(comp["angle"])
    return comp["x"] + px * math.cos(a) - py * math.sin(a), comp["y"] + px * math.sin(a) + py * math.cos(a)


ROUTED = Export(harness.ROUTED)
GEN = Export(harness.GENERATED)
TITLES = {"main": "Plaitsy Main PCB", "face": "Plaitsy Faceplate PCB"}
COMPS = {}
for label, ex in (("routed", ROUTED), ("generated", GEN)):
    for b, title in TITLES.items():
        doc = ex.pcb(title)
        ck.check(f"D.{label}.{b}.pcb_present", doc is not None, f"PCB doc '{title}' in {os.path.basename(ex.path)}")
        if doc is None:
            continue
        COMPS[(label, b)], dups = pcb_components(doc)
        ck.check(f"D.{label}.{b}.no_duplicate_designators", not dups, f"duplicates {dups}")
RC = {b: COMPS[("routed", b)] for b in ("main", "face")}


def fp(board, ref, ex=ROUTED, label="routed"):
    return ex.footprint_pads(COMPS[(label, board)][ref]["footprint"])


def board_pads(board, ref, ex=ROUTED, label="routed"):
    c = COMPS[(label, board)][ref]
    return {n: pad_xy(c, v[:2]) for n, v in ex.footprint_pads(c["footprint"]).items()}


W_BOARD = circuit.BOARD_W


def front(p):
    """PCB frame (top layer = the rear, x right) -> front view of the faceplate (x_front = W - x)."""
    return (W_BOARD - p[0], p[1])


# ----------------------------------------------------------------------------------------------------------
# B (footprints of the routed master)
jk = fp("face", "J1")
d12 = math.dist(jk[JACK_DS["S"]][:2], jk[JACK_DS["TN"]][:2])
d13 = math.dist(jk[JACK_DS["S"]][:2], jk[JACK_DS["T"]][:2])
d23 = math.dist(jk[JACK_DS["TN"]][:2], jk[JACK_DS["T"]][:2])
ck.check("B.jack_footprint_vs_Thonk_PJ398SM", abs(d12 - JACK_DS["S_TN"]) < 0.05 and abs(d13 - JACK_DS["S_T"]) < 0.05
         and abs(d12 + d23 - d13) < 0.01,
         f"Thonk drawing: sleeve -> switch {JACK_DS['S_TN']} mm, sleeve -> tip {JACK_DS['S_T']:.2f} mm, in one row; "
         f"footprint pad 1 -> 2 {d12:.2f}, 1 -> 3 {d13:.2f} (so 1 = sleeve, 2 = switch, 3 = tip)")
jk_fps = {RC["face"][ref]["footprint"] for ref, *_ in circuit.JACKS}
ck.check("B.all_jacks_one_footprint", len(jk_fps) == 1, f"footprints {jk_fps}")

# pots in the front view: pins 2.5 mm apart, 7.5 mm from the shaft, CW turns the wiper 1 -> 3
pot_bad, pot_geo = [], []
for ref, label, wiper, mpin, ch in circuit.POTS:
    c = RC["face"][ref]
    bp = {n: front(xy) for n, xy in board_pads("face", ref).items()}
    sx, sy = circuit.board_xy(*circuit.PANEL_XY[ref])
    p1, p2, p3 = bp["1"], bp["2"], bp["3"]
    mid = ((p1[0] + p3[0]) / 2, (p1[1] + p3[1]) / 2)
    d = (mid[0] - sx, mid[1] - sy)
    v = (p3[0] - p1[0], p3[1] - p1[1])
    cross = d[0] * v[1] - d[1] * v[0]
    row = math.hypot(*d)
    lugs = [math.dist(bp[n], (sx, sy)) for n in ("4", "5")]
    if not (c["bottom"] and cross > 0):
        pot_bad.append((ref, label, f"pins->{'x' if abs(d[0]) > abs(d[1]) else 'y'} {d[0]:+.1f},{d[1]:+.1f}", f"cross {cross:+.1f}"))
    if not (abs(math.dist(p1, p3) - 2 * ALPHA_DS["pitch"]) < 0.05 and abs(row - ALPHA_DS["row_to_shaft"]) < 0.05
            and all(abs(l - ALPHA_DS["lug_x"]) < 0.05 for l in lugs) and abs(math.dist(p1, p2) - ALPHA_DS["pitch"]) < 0.05):
        pot_geo.append((ref, round(math.dist(p1, p3), 2), round(row, 2), [round(l, 2) for l in lugs]))
ck.check("B.pots_CW_front_view", not pot_bad,
         f"on the panel side, and looking at the shaft with the pins below it pin 1 left, 3 right (Alpha SLH-211-414): "
         f"cross(shaft->pins, pin1->pin3) > 0 in the front view; bad {pot_bad}")
ck.check("B.pot_footprint_vs_Alpha_RD901F", not pot_geo,
         f"pins 2.5 mm apart, row {ALPHA_DS['row_to_shaft']} mm from the shaft (circuit.PANEL_XY), lugs "
         f"{ALPHA_DS['lug_x']} mm either side of it; bad (ref, 1-3, row, lugs) {pot_geo}")
hole = fp("face", "RV1")["1"][3]
ck.check("B.pot_pin_hole_vs_Alpha", hole is not None and hole >= ALPHA_DS["pin_hole"] - 0.01,
         f"Alpha: 3 x 1.0 mm holes; footprint {hole:.2f} mm")

# the Thonk button footprint against PB01-109TL
bt = {n: v[:2] for n, v in fp("face", "SW1").items()}
pa, pb = BUTTON_DS["pair_a"], BUTTON_DS["pair_b"]
same_edge = abs(bt[pa[0]][1] - bt[pa[1]][1]) < 0.01 and abs(bt[pb[0]][1] - bt[pb[1]][1]) < 0.01
spacing = abs(math.dist(bt[pa[0]], bt[pa[1]]) - BUTTON_DS["sw_pitch"]) < 0.02 and \
    abs(math.dist(bt[pa[0]], bt[pb[0]]) - BUTTON_DS["sw_pitch"]) < 0.02
above = abs(bt["1"][0] - bt["3"][0]) < 0.01 and abs(bt["2"][0] - bt["4"][0]) < 0.01
l1_side = (bt[BUTTON_DS["L1_anode"]][0] - bt["2"][0]) * (bt["1"][0] - bt["2"][0]) > 0 and \
    abs(bt[BUTTON_DS["L1_anode"]][0] - bt["1"][0]) < abs(bt[BUTTON_DS["L1_anode"]][0] - bt["2"][0])
led_p = abs(math.dist(bt["5"], bt["6"]) - BUTTON_DS["led_pitch"]) < 0.02
ck.check("B.button_footprint_vs_Thonk_PB01_109TL", same_edge and spacing and above and l1_side and led_p,
         f"1, 2 on one edge and 3, 4 on the other 5.08 mm apart, 1 over 3, L1 (pad 5) on the 1 / 3 side, LED legs "
         f"5.4 mm apart; footprint { {n: (round(x, 2), round(y, 2)) for n, (x, y) in sorted(bt.items())} }")

# LED: common cathode in the middle, red anode on the left in the front view (design.md)
led_fp = {n: v[:2] for n, v in fp("face", "D1").items()}
mid_k = abs(math.dist(led_fp["1"], led_fp["2"]) - math.dist(led_fp["3"], led_fp["2"])) < 0.01 and \
    abs(math.dist(led_fp["1"], led_fp["3"]) - 2 * math.dist(led_fp["1"], led_fp["2"])) < 0.01
ck.check("B.LED_footprint_cathode_middle", mid_k and LED_DS["K"] == "2",
         f"3-lead bicolour: cathode (pad 2) between the anodes; pads {led_fp}")
red_left = []
for k in range(1, 9):
    bp = {n: front(xy) for n, xy in board_pads("face", f"D{k}").items()}
    if not bp[LED_DS["A_R"]][0] < bp[LED_DS["A_G"]][0]:
        red_left.append((f"D{k}", round(bp["1"][0], 2), round(bp["3"][0], 2)))
ck.check("B.LED_red_anode_left_front", not red_left,
         f"design.md: every LED has its red anode on the left (front view); bad {red_left}")
ck.check("B.LED_pinout_vs_Tayda_A8599", LED_DS["confirmed"] and (LED_DS["A_R"], LED_DS["K"], LED_DS["A_G"]) == ("1", "2", "3")
         and all(PARTS["face"][f"D{k}"].nets.get("1", "").endswith("_R") and PARTS["face"][f"D{k}"].nets.get("3", "").endswith("_G")
                 for k in range(1, 9)),
         f"Tayda A-8599 drawing: outer lead A red anode, middle C cathode, outer B green anode {LED_DS['lead_order']}; "
         f"circuit.py: 1 red, 2 cathode, 3 green. Build note: the red anode is the medium-length lead, the green the "
         f"shortest; it goes in the square pad 1")
sq = sorted(n for n, v in fp("face", "D1").items() if v[2] == "RECT")
ck.check("B.LED_red_pad_marked", sq == [LED_DS["A_R"]],
         f"the only mark on LED-3MM-3P (silk is a plain circle) is the square pad: it must be the red anode; square {sq}")


# BAT85: the symbol's cathode pin and the footprint's band pad, in the routed master and the generated export
def cathode_pin_symbol(ex, sym):
    pins = ex.symbol_pins(sym)
    k = [n for n, (nm, *_r) in pins.items() if nm in ("C", "K", "Cathode", "CATHODE")]
    a = [n for n, (nm, *_r) in pins.items() if nm in ("A", "Anode", "ANODE")]
    bar = None
    for pts in ex.symbol_polys(sym):
        corners = sorted(set(pts))
        if len(corners) == 3:
            xs = [c[0] for c in corners]
            singles = [c for c in corners if xs.count(c[0]) == 1]
            doubles = [x for x in xs if xs.count(x) == 2]
            if len(singles) == 1 and doubles:
                side = 1 if singles[0][0] > doubles[0] else -1          # the apex points at the bar
                bar = max(pins, key=lambda n: side * pins[n][1])
    return (k[0] if len(k) == 1 else None), (a[0] if len(a) == 1 else None), bar


def band_pad(ex, fp_uid):
    """The pad on the band's side: a top-silk line across the body, strictly inside the body outline."""
    pads = ex.footprint_pads(fp_uid)
    xs = []
    for h, p in ex.docs[fp_uid]["recs"]:
        if h["type"] == "POLY" and p.get("layerId") == 3 and p["path"] and not isinstance(p["path"][0], str):
            path = p["path"]
            if len(path) == 5 and path[2] == "L" and abs(path[0] - path[3]) < 0.01 and abs(path[1] - path[4]) > 40:
                xs.append(round(path[0] * MIL, 3))
    ends = [x for x in xs if any(abs(x + y) < 0.02 for y in xs)]
    end = max(ends) if ends else 0
    inner = [x for x in xs if abs(x) < end - 0.05]
    if len(inner) != 1:
        return None, xs
    return min(pads, key=lambda n: abs(pads[n][0] - inner[0])), xs


for label, ex in (("routed", ROUTED), ("generated", GEN)):
    for ref in ("D21", "D22"):
        c = COMPS[(label, "main")][ref]
        dev = ex.devices.get(c["device"], {})
        k, a, bar = cathode_pin_symbol(ex, dev.get("Symbol"))
        band, xs = band_pad(ex, c["footprint"])
        ck.check(f"B.{label}.{ref}.symbol_cathode_pin_1", k == "1" and a == "2" and bar == "1",
                 f"{dev.get('Manufacturer Part')} symbol: pin named C = {k}, A = {a}, bar side = {bar}; circuit.py takes "
                 f"pin 1 as the cathode")
        ck.check(f"B.{label}.{ref}.footprint_band_on_pad_1", band == "1",
                 f"footprint band (silk across the body at x {xs} mm) beside pad {band}; expected pad 1 (the cathode)")
D = {ref: (PARTS["main"][ref].nets["2"], PARTS["main"][ref].nets["1"]) for ref in ("D21", "D22")}   # (anode, cathode)


def conducts(ref, v):
    a, k = D[ref]
    return v[a] - v[k] > 0.2


for case, vadc, want in (("ADC_VOCT above 3V3A", 3.6, {"D21"}), ("ADC_VOCT below GND", -0.3, {"D22"}),
                         ("ADC_VOCT in range (1.65 V)", 1.65, set()), ("ADC_VOCT at 3.3 V", 3.3, set()),
                         ("ADC_VOCT at 0 V", 0.0, set())):
    v = {"3V3A": 3.3, "GND": 0.0, "ADC_VOCT": vadc}
    on = {ref for ref in D if conducts(ref, v)}
    ck.check(f"B.clamps.{case.replace(' ', '_')}", on == want,
             f"D21 anode {D['D21'][0]} / cathode {D['D21'][1]}, D22 anode {D['D22'][0]} / cathode {D['D22'][1]}; "
             f"at {vadc} V conducting {sorted(on)}, expected {sorted(want)}")

# the breakout footprint against Rob Heel's board (Gerbers): rows, pitch, the Seed's CCW numbering seen from the
# rear (the Seed's top), J5 / J4 beyond pins 1 / 40, J1 / J3 beyond pins 20 / 21 after one empty position
U2 = board_pads("main", "U2")
row_a = [U2[str(n)] for n in range(1, 21)]
row_b = [U2[str(n)] for n in range(21, 41)]
pitch_ok = all(abs(math.dist(r[i], r[i + 1]) - BREAKOUT["pitch"]) < 0.01 for r in (row_a, row_b) for i in range(19))
gap_ok = abs(math.dist(U2["20"], U2["21"]) - BREAKOUT["row_gap"]) < 0.01 and abs(math.dist(U2["1"], U2["40"]) - BREAKOUT["row_gap"]) < 0.01
poly = [U2["1"], U2["20"], U2["21"], U2["40"]]
area = sum(poly[i][0] * poly[(i + 1) % 4][1] - poly[(i + 1) % 4][0] * poly[i][1] for i in range(4)) / 2
ck.check("B.breakout_seed_rows", pitch_ok and gap_ok, f"pins 1-20 and 21-40 in rows 2.54 mm pitch, 15.24 mm apart, "
                                                      f"20 across from 21 and 1 across from 40")
ck.check("B.breakout_seed_numbering_CCW_from_rear", area > 0,
         f"the Seed sits component side up on the breakout on the main board's rear: seen from the rear (the PCB "
         f"frame) 1 -> 20 -> 21 -> 40 must run counter-clockwise (Seed datasheet pinout, top view); signed area {area:.0f}")
off_bad = []
for hdr, end in (("J5", "1"), ("J4", "40"), ("J1", "20"), ("J3", "21")):
    inner = {"1": "2", "40": "39", "20": "19", "21": "22"}[end]
    ux = ((U2[end][0] - U2[inner][0]) / BREAKOUT["pitch"], (U2[end][1] - U2[inner][1]) / BREAKOUT["pitch"])
    for k, o in zip((4, 3, 2, 1) if hdr in ("J5", "J4") else (1, 2, 3, 4), BREAKOUT["offset"][hdr]):
        want = (U2[end][0] + ux[0] * o * BREAKOUT["pitch"], U2[end][1] + ux[1] * o * BREAKOUT["pitch"])
        got = U2[f"{hdr}-{k}"]
        if math.dist(want, got) > 0.02:
            off_bad.append((f"{hdr}-{k}", tuple(round(v, 2) for v in got), tuple(round(v, 2) for v in want)))
ck.check("B.breakout_header_positions_vs_Gerbers", not off_bad,
         f"J5 / J4 pin 4 one pitch beyond Seed pin 1 / 40, pin 1 outermost; J1 / J3 pin 1 two pitches beyond pin 20 / 21 "
         f"(one empty position), pin 4 outermost; bad {off_bad}")
ck.check("B.breakout_pad_count", len(U2) == 56, f"40 Seed pins + 4 x 1x4 = 56 pads (Gerber drill: 40 x 1.2 mm + 16 x "
                                                f"0.889 mm in the two rows); footprint {len(U2)}")

# ==========================================================================================================
# D  every pad's net in both exports against circuit.py
for label, ex in (("routed", ROUTED), ("generated", GEN)):
    for b, parts in (("main", MB), ("face", FB)):
        if (label, b) not in COMPS:
            continue
        got = COMPS[(label, b)]
        want = {p.ref: p for p in parts}
        missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
        ck.check(f"D.{label}.{b}.designators_complete", not missing and not extra,
                 f"{len(want)} parts in circuit.py, {len(got)} on the PCB; missing {missing}, extra {extra}")
        bad, fp_missing, npads = [], [], 0
        for ref, part in want.items():
            c = got.get(ref)
            if not c:
                continue
            if c["footprint"] not in ex.docs:
                fp_missing.append((ref, c["footprint"]))
                continue
            pads = ex.footprint_pads(c["footprint"])
            no_pad = sorted(set(part.nets) - set(pads))
            if no_pad:
                bad.append((ref, "circuit pins without a pad", no_pad))
            for num in pads:
                npads += 1
                if c["nets"].get(num) != part.nets.get(num):
                    bad.append((ref, num, "pcb", c["nets"].get(num), "circuit", part.nets.get(num)))
        ck.check(f"D.{label}.{b}.footprints_present", not fp_missing, f"components whose footprint doc is missing: {fp_missing}")
        ck.check(f"D.{label}.{b}.every_pad_net", not bad,
                 f"{npads} pads compared one by one; {len(bad)} differences: {bad[:15]}")
        pcb_nets = {n for c in got.values() for n in c["nets"].values()}
        circ = set(circuit.nets_of(parts))
        ck.check(f"D.{label}.{b}.no_stray_nets", pcb_nets == circ,
                 f"PCB minus circuit {sorted(pcb_nets - circ)}, circuit minus PCB {sorted(circ - pcb_nets)}")
    # the generated and the routed boards place the same footprints
    fp_diff = [(b, ref, ex.docs.get(COMPS[(label, b)][ref]["footprint"]) and doc_meta(ex.docs[COMPS[(label, b)][ref]["footprint"]]).get("title"),
                doc_meta(ROUTED.docs[RC[b][ref]["footprint"]]).get("title"))
               for b in ("main", "face") for ref in RC[b] if ref in COMPS.get((label, b), {})
               and doc_meta(ex.docs[COMPS[(label, b)][ref]["footprint"]]).get("title") !=
               doc_meta(ROUTED.docs[RC[b][ref]["footprint"]]).get("title")]
    if label == "generated":
        ck.check("D.generated_footprints_equal_routed", not fp_diff, f"footprint titles that differ: {fp_diff}")



# the library device behind each placed part against circuit.py's kind / value
def value_of_device(txt):
    m = re.fullmatch(r"([\d.]+)\s*([pnuµkM]?)(Ω|F)?", (txt or "").strip())
    if not m:
        return None
    mul = {"": 1, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "k": 1e3, "M": 1e6}[m.group(2)]
    return float(m.group(1)) * mul


KIND_MPN = {"TL074": "TL074", "MUX": "4051", "HC595": "74HC595", "BAT85": "BAT85", "JACK": "WQP518MA",
            "LED_RG": "bicolour", "SWLED": "LED button", "HDR8": "1x8", "HDR9": "1x9", "SEED": "Daisy Seed"}
for label, ex in (("routed", ROUTED), ("generated", GEN)):
    dev_bad, pot_mpn = [], set()
    for b, parts in (("main", MB), ("face", FB)):
        for p in parts:
            c = COMPS[(label, b)].get(p.ref)
            if not c:
                continue
            d = ex.devices.get(c["device"], {})
            if p.kind in ("R", "C", "POT"):
                want_v = harness.ohms(p.value) if p.kind in ("R", "POT") else harness.farads(p.value)
                got_v = value_of_device(d.get("Value"))
                if got_v is None or abs(got_v - want_v) > 1e-6 * want_v:
                    dev_bad.append((p.ref, p.value, d.get("Value"), d.get("Manufacturer Part")))
                if p.kind == "POT":
                    pot_mpn.add(d.get("Manufacturer Part"))
            elif KIND_MPN.get(p.kind, "?").lower() not in str(d.get("Manufacturer Part", "")).lower():
                dev_bad.append((p.ref, p.kind, d.get("Manufacturer Part")))
    ck.check(f"D.{label}.devices_match_values", not dev_bad, f"device Value / part against circuit.py: {dev_bad[:12]}")
    ck.check(f"D.{label}.pot_device_is_the_Alpha", all("RD901" in str(m) or "Alpha" in str(m) for m in pot_mpn),
             f"RV1-RV7 sit on POT-ALPHA-9MM-RD901F and bom.md orders Alpha pots from Thonk, but the EasyEDA device's "
             f"Manufacturer Part is {sorted(map(str, pot_mpn))} (Bourns; its lug slots sit 0.5 mm off the Alpha's, "
             f"design.md): an export BOM / LCSC order would name the wrong pot")

# DIP numbering (counter-clockwise from the top: 1..n/2 along one row, back along the other) and layers
for ref, b, n in (("U3", "main", 14), ("U4", "main", 14), ("U1", "face", 16), ("U9", "face", 16), ("U10", "face", 16)):
    pads = {k: v[:2] for k, v in fp(b, ref).items()}
    h = n // 2
    rows = all(abs(pads[str(i)][1] - pads["1"][1]) < 0.01 and abs(pads[str(n + 1 - i)][0] - pads[str(i)][0]) < 0.01
               for i in range(1, h + 1)) and all(pads[str(i + 1)][0] - pads[str(i)][0] > 2.5 for i in range(1, h))
    spacing = abs(abs(pads[str(n)][1] - pads["1"][1]) - 7.62) < 0.01
    ccw = pads[str(n)][1] > pads["1"][1]                      # pin n above pin 1 with 1..n/2 running to +x
    on_top = not RC[b][ref]["bottom"]
    ck.check(f"D.DIP{n}_numbering.{ref}", rows and spacing and ccw and on_top and len(pads) == n,
             f"pin 1..{h} along one row (+x), {h + 1}..{n} back along the other, 7.62 mm rows, counter-clockwise from the "
             f"top, placed on the top layer ({'top' if on_top else 'BOTTOM'}); pads 1 {pads['1']}, {n} {pads[str(n)]}")



def pin1_marked(fp_uid, first="1", last=None):
    """Pin 1 identifiable: the only square pad, or a top-silk dot / circle nearer pad 1 than any other pad."""
    pads = ROUTED.footprint_pads(fp_uid)
    rects = sorted(n for n, v in pads.items() if v[2] == "RECT")
    if rects == [first]:
        return True, "square pad 1"
    for h, p in ROUTED.docs[fp_uid]["recs"]:
        if h["type"] == "POLY" and p.get("layerId") == 3 and p["path"] and p["path"][0] == "CIRCLE":
            cx, cy, r = p["path"][1] * MIL, p["path"][2] * MIL, p["path"][3] * MIL
            if r < 1.0 and min(pads, key=lambda n: math.dist(pads[n][:2], (cx, cy))) == first:
                return True, f"silk dot at ({cx:.2f}, {cy:.2f}) beside pad 1"
    return False, f"square pads {rects}"


for b, ref in (("main", "U3"), ("face", "U1"), ("face", "U9"), ("main", "H1"), ("main", "H2"), ("face", "HF1"),
               ("face", "HF3")):
    ok, why = pin1_marked(RC[b][ref]["footprint"])
    ck.check(f"D.pin1_marked.{ref}", ok, f"{doc_meta(ROUTED.docs[RC[b][ref]['footprint']]).get('title')}: {why}")

# ==========================================================================================================
# E  header stacking, and the two faceplate grounds
R = harness.routed()
stack_bad, sides_bad, matched = [], [], 0
for ref, kind, pins in circuit.HEADERS:
    fref = circuit.fb_ref(ref)
    m, f = R.main.parts[ref], R.face.parts[fref]
    if f["bottom"] or not m["bottom"]:
        sides_bad.append((ref, "main bottom", m["bottom"], fref, "face bottom", f["bottom"]))
    for i, (a, bnet) in enumerate(pins):
        num = str(i + 1)
        mp, fpd = m["pads"][num], f["pads"][num]
        if math.hypot(mp.x - fpd.x, mp.y - fpd.y) > 0.05 or mp.net != a or fpd.net != bnet:
            stack_bad.append((ref, num, (round(mp.x, 2), round(mp.y, 2)), mp.net, (round(fpd.x, 2), round(fpd.y, 2)), fpd.net))
        else:
            matched += 1
        # nothing else of the other board's header lands there
        others = [p for p in R.face.pads if p.ref.startswith("HF") and (p.ref, p.num) != (fref, num)
                  and math.hypot(p.x - mp.x, p.y - mp.y) < 0.05]
        if others:
            stack_bad.append((ref, num, "also under", [(p.ref, p.num) for p in others]))
ck.check("E.header_sides", not sides_bad, f"sockets on the main board's bottom, male pins on the faceplate's top: {sides_bad}")
ck.check("E.stacked_pins_carry_pairs", not stack_bad and matched == npins,
         f"{matched} of {npins} HFn pins over their Hn pin (0.05 mm) with the circuit.HEADERS net pair; bad {stack_bad[:10]}")
ck.check("E.same_outline", all(abs(a - b) < 0.01 for a, b in zip(R.main.outline, R.face.outline)),
         f"main {R.main.outline}, faceplate {R.face.outline}")
ck.check("E.same_mounting_holes", sorted((round(x, 2), round(y, 2)) for x, y, d in R.main.holes) ==
         sorted((round(x, 2), round(y, 2)) for x, y, d in R.face.holes), f"main {R.main.holes}, face {R.face.holes}")

groups_f, contacts_f = R.face.connectivity()
gnd_meet = [c for c in contacts_f if {c[0], c[1]} == {"GND_F", "GND_D_F"}]
ck.check("E.faceplate_grounds_never_meet", not gnd_meet,
         f"design.md: GND_F and GND_D_F never touch on the faceplate; copper contacts {gnd_meet[:5]}")
for net in ("GND_F", "GND_D_F"):
    ck.check(f"E.faceplate_{net}_one_piece", len(groups_f.get(net, {})) == 1,
             f"{net} in {len(groups_f.get(net, {}))} copper pieces on the faceplate")
other_f = [c for c in contacts_f]
ck.check("E.faceplate_no_copper_shorts", not other_f, f"copper of different nets touching: {other_f[:5]}")
groups_m, contacts_m = R.main.connectivity()
gpieces = groups_m.get("GND", {})
h2g = ("pad", "H2", str([a for a, b in dict((r, p) for r, _, p in circuit.HEADERS)["H2"]].index("GND") + 1))
h3g = ("pad", "H3", str([a for a, b in dict((r, p) for r, _, p in circuit.HEADERS)["H3"]].index("GND") + 1))
together = any(h2g in keys and h3g in keys for keys in gpieces.values())
ck.check("E.grounds_meet_on_main_board", together and len(gpieces) == 1,
         f"H2's GND pin ({h2g[2]}, GND_F) and H3's ({h3g[2]}, GND_D_F) on one main-board GND piece; GND in {len(gpieces)} pieces")
ck.check("E.main_no_copper_shorts", not contacts_m, f"copper of different nets touching: {contacts_m[:5]}")


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


# every pin-placing convention is tried; the one that lands the most pins on named wires wins
CANDS = [(o, s, f) for o in ("mirror-first", "rotate-first") for s in (-1, 1) for f in (1, -1)]
NONPOLAR = ("R", "C")


def schematic_nets(ex):
    pages = collections.defaultdict(list)
    sch_board = {u: ex.board_title(doc_meta(d).get("board")) for u, d in ex.of_type("SCH").items()}
    for u, d in ex.of_type("SCH_PAGE").items():
        sid = doc_meta(d).get("schematic")
        pages[next((t for s, t in sch_board.items() if sid and (s.startswith(sid) or sid.startswith(s))), None)].append(d)
    sympins, result = {}, {}
    for board, docs in pages.items():
        page_data = []
        for d in docs:
            comps = {h["id"]: p for h, p in d["recs"] if h["type"] == "COMPONENT"}
            attrs = collections.defaultdict(dict)
            for h, p in d["recs"]:
                if h["type"] == "ATTR":
                    attrs[p.get("parentId")][p["key"]] = p["value"]
            wires = {h["id"]: [] for h, p in d["recs"] if h["type"] == "WIRE"}
            for h, p in d["recs"]:
                if h["type"] == "LINE" and p.get("lineGroup") in wires:
                    wires[p["lineGroup"]].append(((p["startX"], p["startY"]), (p["endX"], p["endY"])))
            named = {w: attrs[w].get("NET") for w in wires if attrs[w].get("NET")}
            page_data.append((comps, attrs, wires, named))
        best = None
        for cand in CANDS:
            score = 0
            for comps, attrs, wires, named in page_data:
                ptset = {(round(x, 3), round(y, 3)) for w in named for seg in wires[w] for x, y in seg}
                for cid, comp in comps.items():
                    sym = attrs[cid].get("Symbol")
                    if sym not in ex.docs or "Designator" not in attrs[cid]:
                        continue
                    sympins.setdefault(sym, ex.symbol_pins(sym))
                    for num, (name, px, py, part) in sympins[sym].items():
                        if part and part != comp.get("partId"):
                            continue
                        score += _xf(cand, comp, px, py) in ptset
            if best is None or score > best[0]:
                best = (score, cand)
        cand = best[1]
        pins_of, conflicts = collections.defaultdict(dict), []
        for comps, attrs, wires, named in page_data:
            segs = [(w, s) for w in named for s in wires[w]]
            flag_pts = []
            for cid, comp in comps.items():
                a = attrs[cid]
                sym = a.get("Symbol")
                if "Designator" in a or not a.get("Name") or sym not in ex.docs:
                    continue
                sympins.setdefault(sym, ex.symbol_pins(sym))
                for num, (name, px, py, part) in sympins[sym].items():
                    flag_pts.append((_xf(cand, comp, px, py), a["Name"]))
            for cid, comp in comps.items():
                a = attrs[cid]
                ref, sym = a.get("Designator"), a.get("Symbol")
                if not ref or sym not in ex.docs:
                    continue
                sympins.setdefault(sym, ex.symbol_pins(sym))
                for num, (name, px, py, part) in sympins[sym].items():
                    if part and part != comp.get("partId"):
                        continue
                    p = _xf(cand, comp, px, py)
                    nets = {named[w] for w, s in segs if _on_seg(p, *s)}
                    nets |= {n for q, n in flag_pts if abs(q[0] - p[0]) < 0.01 and abs(q[1] - p[1]) < 0.01}
                    if len(nets) > 1:
                        conflicts.append((ref, num, sorted(nets)))
                    net = next(iter(nets)) if len(nets) == 1 else None
                    prev = pins_of[ref].get(num)
                    if prev is not None and net is not None and prev != net:
                        conflicts.append((ref, num, prev, net))
                    if prev is None:
                        pins_of[ref][num] = net
        result[board] = (pins_of, {"transform": cand, "score": best[0], "conflicts": conflicts})
    return result


def compare_schematic(label, ex):
    res = schematic_nets(ex)
    for board, parts in (("Plaitsy Main", MB), ("Plaitsy Faceplate", FB)):
        if board not in res:
            ck.check(f"F.{label}.{board.split()[-1]}.pages_present", False, f"no schematic page for {board}")
            continue
        pins_of, st = res[board]
        want = {p.ref: p for p in parts}
        missing, extra = sorted(set(want) - set(pins_of)), sorted(set(pins_of) - set(want))
        tag = f"F.{label}.{board.split()[-1].lower()}"
        ck.check(f"{tag}.parts", not missing and not extra,
                 f"{len(want)} parts in circuit.py, {len(pins_of)} on the page; missing {missing}, extra {extra}")
        ck.check(f"{tag}.no_conflicting_labels", not st["conflicts"], f"pins on two named nets: {st['conflicts'][:10]}")
        diffs, swapped = [], []
        for ref, p in want.items():
            got = pins_of.get(ref, {})
            if p.kind in NONPOLAR and len(p.nets) == 2 and sorted(map(str, got.values())) == sorted(p.nets.values()) \
                    and got != p.nets:
                swapped.append(ref)
                continue
            for num in sorted(set(p.nets) | {n for n, v in got.items() if v}):
                if got.get(num) != p.nets.get(num):
                    diffs.append((ref, num, "page", got.get(num), "circuit", p.nets.get(num)))
        ck.check(f"{tag}.pin_nets", not diffs,
                 f"transform {st['transform']}, {st['score']} pins on named wires; {len(diffs)} pins differ: {diffs[:12]}")
        polar = [r for r in swapped if want[r].kind not in NONPOLAR]
        ck.check(f"{tag}.polar_parts_unambiguous", not polar,
                 f"{len(swapped)} R / C read pins 1 / 2 reversed under this convention (harmless); polar parts: {polar}")


compare_schematic("routed", ROUTED)
compare_schematic("generated", GEN)

# ==========================================================================================================
# G  design.md's tables and statements, and the firmware's board tables, against circuit.py
DESIGN = harness.text("docs", "design.md")


def md_table(after, nth=0):
    """Rows (cell lists) of the nth markdown table after the first line containing `after` (header row first)."""
    lines = DESIGN[DESIGN.index(after):].splitlines()
    tables, rows, started = [], [], False
    for ln in lines[1:]:
        if ln.startswith("|"):
            started = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif started:
            tables.append(rows)
            rows, started = [], False
            if len(tables) > nth:
                break
    if started:
        tables.append(rows)
    return tables[nth] if len(tables) > nth else []


def expand(cell):
    """'22..28' -> 22..28, 'A0..A6' -> A0..A6, 'MUX_S0..S2' -> MUX_S0..MUX_S2, '1, 2' -> 1, 2."""
    out = []
    for tok in [t.strip() for t in re.sub(r"\([^)]*\)", "", cell).split(",") if t.strip()]:
        m = re.fullmatch(r"(\D*?)(\d+)\.\.(\D*?)(\d+)", tok)
        if m:
            out += [f"{m.group(1)}{k}" for k in range(int(m.group(2)), int(m.group(4)) + 1)]
        else:
            out.append(tok)
    return out


# Seed pin map
seed_rows = md_table("### Daisy Seed pin map")
sp_bad, listed = [], set()
for r in seed_rows[1:]:
    pins, names, nets = expand(r[0]), expand(r[1]), expand(r[2])
    listed |= set(pins)
    if nets == ["—"]:
        bad = [p for p in pins if circuit.SEED.get(p, ("?", "?"))[1]]
        if bad:
            sp_bad.append(("free row lists used pins", bad))
        continue
    if len(nets) == 1 and len(pins) > 1:
        nets = nets * len(pins)
    if not (len(pins) == len(names) == len(nets)):
        sp_bad.append(("unparsed row", r[:3]))
        continue
    for p, nm, n in zip(pins, names, nets):
        cname, cnet = circuit.SEED.get(p, (None, None))
        if cname is None or nm not in cname.split("/") or cnet != n:
            sp_bad.append((p, "doc", nm, n, "circuit", cname, cnet))
used = {p for p, (nm, n) in circuit.SEED.items() if n and not p.startswith("J1") and not p.startswith("J3")
        and not p.startswith("J5") and p not in ("J4-2", "J4-4")}
free = {p for p, (nm, n) in circuit.SEED.items() if not n and not p.startswith("J")}
ck.check("G.design_seed_pin_map", not sp_bad and used <= listed and free <= listed,
         f"design.md's Seed pin map against circuit.SEED; bad {sp_bad[:8]}; used pins missing from the table "
         f"{sorted(used - listed)}; free pins missing {sorted(free - listed)}")

# CV input table
cv_rows = md_table("### CV inputs (8×)")
cv_bad = []
by_label = {label: (name, u, s, rf, cf, bias) for name, label, u, s, rf, cf, bias in circuit.CV_CHANNELS}
ALLP = {p.ref: p for p in ALL}
for r in cv_rows[1:]:
    label, sec, rin, rf_c, cf_c, rs, bias, adc = r[:8]
    if label not in by_label:
        cv_bad.append(("label", label))
        continue
    name, u, s, rf, cf, b = by_label[label]
    if sec != f"{u}{'ABCD'[s - 1]}":
        cv_bad.append((label, "section", sec, f"{u}{'ABCD'[s - 1]}"))
    rf_ref, rf_val = rf_c.split()
    cf_ref, cf_val = cf_c.split()
    checks = [(rin, {f"CV_{name}", f"IN_{name}"}, None), (rf_ref, {f"IN_{name}", f"OA_{name}"}, rf),
              (cf_ref, {f"IN_{name}", f"OA_{name}"}, cf), (rs, {f"OA_{name}", f"ADC_{name}"}, None)]
    for ref, nets, val in checks:
        p = ALLP.get(ref)
        if p is None or set(p.nets.values()) != nets or (val and p.value != val):
            cv_bad.append((label, ref, p and p.nets, p and p.value))
    if rf_val != rf or cf_val != cf:
        cv_bad.append((label, "values", rf_val, cf_val, rf, cf))
    if f"BIAS_{bias}" != b:
        cv_bad.append((label, "bias", bias, b))
    adc_pin = [p for p, (nm, n) in circuit.SEED.items() if n == f"ADC_{name}"]
    if len(adc_pin) != 1 or adc not in circuit.SEED[adc_pin[0]][0].split("/"):
        cv_bad.append((label, "adc", adc, adc_pin))
ck.check("G.design_cv_input_table", not cv_bad and len(cv_rows) == 9, f"design.md CV table against circuit.py: {cv_bad}")
# the bias and gain figures under the table
V33 = 3.3
pv = {r: ALLP[r] for r in ("R45", "R46", "R47", "R48", "C29", "C30")}
bias_a = V33 * harness.ohms(pv["R46"].value) / (harness.ohms(pv["R45"].value) + harness.ohms(pv["R46"].value))
bias_v = V33 * harness.ohms(pv["R48"].value) / (harness.ohms(pv["R47"].value) + harness.ohms(pv["R48"].value))
ck.check("G.design_bias_dividers_wired", set(pv["R45"].nets.values()) == {"3V3A", "BIAS_A"} and set(pv["R46"].nets.values())
         == {"BIAS_A", "GND"} and set(pv["R47"].nets.values()) == {"3V3A", "BIAS_V"} and set(pv["R48"].nets.values()) ==
         {"BIAS_V", "GND"} and pv["C29"].value == pv["C30"].value == "1u",
         "R45 3V3A-BIAS_A, R46 BIAS_A-GND, R47 3V3A-BIAS_V, R48 BIAS_V-GND, C29 / C30 1 u")
m_a = re.search(r"Bias A\*\* = 3V3A × (\S+) / \((\S+) \+ (\S+)\) = ([\d.]+) V", DESIGN)
m_v = re.search(r"Bias V\*\* = 3V3A × (\S+) / \((\S+) \+ (\S+)\) = ([\d.]+) V", DESIGN)
ck.check("G.design_bias_figures", bool(m_a and m_v) and abs(float(m_a.group(4)) - bias_a) < 0.0015
         and abs(float(m_v.group(4)) - bias_v) < 0.0015,
         f"design.md bias A {m_a and m_a.group(4)} V, V {m_v and m_v.group(4)} V; circuit.py 3.3 V x divider: "
         f"{bias_a:.4f} / {bias_v:.4f} V")
g_w = harness.ohms("13k") / harness.ohms("100k")
g_v = harness.ohms("33k") / harness.ohms("100k")
v0_w, v0_v = bias_a * (1 + g_w), bias_v * (1 + g_v)
lo, hi = v0_w - g_w * 12, v0_w + g_w * 12
ck.check("G.design_wide_channel_figures", abs(v0_w - 1.658) < 0.0015 and abs(hi - 3.22) < 0.006 and abs(lo - 0.10) < 0.006,
         f"design.md: V_adc = 1.658 - 0.13 V_in, +-12 V -> 3.22 ... 0.10 V; computed V0 {v0_w:.4f}, {hi:.3f} ... {lo:.3f} V")
ck.check("G.design_voct_figures", abs(v0_v - 2.351) < 0.0015 and abs((v0_v - V33) / g_v - (-2.9)) < 0.05
         and abs(v0_v / g_v - 7.1) < 0.05,
         f"design.md: V_adc = 2.351 - 0.33 V_in, usable -2.9 ... +7.1 V; computed V0 {v0_v:.4f}, "
         f"{(v0_v - V33) / g_v:.3f} ... {v0_v / g_v:.3f} V")
fc = 1 / (2 * math.pi * harness.ohms("13k") * harness.farads("1n"))
ck.check("G.design_corner_12k", abs(fc - 12e3) < 0.5e3, f"design.md: 12 kHz (13k || 1n); computed {fc / 1e3:.2f} kHz")
ck.check("G.design_C31_C34_decoupling", all(set(ALLP[f"C{k}"].nets.values()) in ({"+12V", "GND"}, {"GND", "-12V"})
                                            and ALLP[f"C{k}"].value == "100n" for k in range(31, 35)),
         "C31-C34 100 n on +-12 V")

# mux table
mx_rows = md_table("by these tables.")
pot_by_ch = {ch: (ref, mpin) for ref, label, wiper, mpin, ch in circuit.POTS}
mx_bad = []
for r in mx_rows[1:]:
    ch, pin, what = int(r[0]), r[1], r[2]
    if HC4051_CH[ch] != pin:
        mx_bad.append((ch, "pin", pin, HC4051_CH[ch]))
    if ch in pot_by_ch:
        if not what.startswith(pot_by_ch[ch][0] + " "):
            mx_bad.append((ch, what, pot_by_ch[ch]))
    elif "GND" not in what or mux.get(pin) != "GND_F":
        mx_bad.append((ch, what, mux.get(pin)))
ck.check("G.design_mux_table", not mx_bad and len(mx_rows) == 9, f"design.md mux table against POTS and SCHS122O: {mx_bad}")
# 595 table
sr_rows = md_table("by these tables.", nth=1)
sr_bad = []
for r in sr_rows[1:]:
    u = r[0].split()[0]
    colour = "R" if "red" in r[0] else "G"
    for q, cell in zip(HC595_Q, r[1:9]):
        line = PARTS["face"][u].nets[HC595_DS[q]]
        if line != f"L_{cell}_{colour}":
            sr_bad.append((u, q, cell, line))
ck.check("G.design_595_table", not sr_bad and len(sr_rows) == 3, f"design.md 595 table against circuit.py + SCLS041J: {sr_bad}")

# header table
ht = md_table("## Board-to-board headers")
ht_bad = []
for r in ht[1:]:
    ref, n, cell = r[0], int(r[1]), r[2]
    pins = dict((x, p) for x, _, p in circuit.HEADERS).get(ref)
    toks = [t.strip() for t in cell.split(",")]
    names = [re.sub(r"\s*\(.*\)", "", t) for t in toks]
    fnames = [re.search(r"\((\w+)\)", t).group(1) if "(" in t else None for t in toks]
    if pins is None or n != len(pins) or names != [a for a, b in pins]:
        ht_bad.append((ref, n, names, pins and [a for a, b in pins]))
        continue
    for (a, b), fn in zip(pins, fnames):
        if fn and fn != b:
            ht_bad.append((ref, a, "faceplate name", fn, b))
ck.check("G.design_header_table", not ht_bad and len(ht) == 4, f"design.md header table against circuit.HEADERS: {ht_bad}")
m = re.search(r"(\d+) pins in (\d+) headers", DESIGN)
ck.check("G.design_header_pin_count", bool(m) and (int(m.group(1)), int(m.group(2))) == (npins, len(circuit.HEADERS)),
         f"design.md '{m and m.group(0)}', circuit.HEADERS {npins} pins in {len(circuit.HEADERS)}")
# the architecture drawing's counts
kinds = collections.Counter(p.kind for p in FB)
led_r = [p for p in FB if p.kind == "R" and p.value == "470"]
arch = re.search(r"(\d+) Thonkiconn jacks, (\d+) Alpha pots, (\d+) LED buttons, (\d+) bicolour LEDs", DESIGN)
arch2 = re.search(r"(\d+) LED resistors, (\d+) probe resistors", DESIGN)
ck.check("G.design_architecture_counts", bool(arch and arch2) and tuple(map(int, arch.groups())) ==
         (kinds["JACK"], kinds["POT"], kinds["SWLED"], kinds["LED_RG"]) and tuple(map(int, arch2.groups())) ==
         (len(led_r), len(probe_r)),
         f"design.md {arch and arch.groups()} / {arch2 and arch2.groups()}; circuit.py {kinds['JACK']} jacks, "
         f"{kinds['POT']} pots, {kinds['SWLED']} buttons, {kinds['LED_RG']} LEDs, {len(led_r)} LED R, {len(probe_r)} probe R")
mb_kinds = collections.Counter(p.kind for p in MB)
ck.check("G.design_main_board_counts", mb_kinds["TL074"] == 2 and len(circuit.CV_CHANNELS) == 8 and
         sum(1 for p in MB if p.kind == "BAT85") == 2, f"design.md: 2 TL074 = 8 CV stages, V/OCT clamps; {dict(mb_kinds)}")
# the Faceplate circuits text
FC = DESIGN[DESIGN.index("## Faceplate circuits"):DESIGN.index("## Board-to-board headers")]
fc_claims = {
    "jack pads 1 = sleeve, 2 = switch, 3 = tip": bool(re.search(r"pads 1 = sleeve, 2 = switch, 3 = tip", FC))
    and (JACK_DS["S"], JACK_DS["TN"], JACK_DS["T"]) == ("1", "2", "3"),
    "R9-R13 to PROBE_F": "(R9–R13) to PROBE_F" in FC and probe_r == ["R10", "R11", "R12", "R13", "R9"],
    "pots CCW GND_F, CW 3V3A_F": "CCW end to GND_F, CW end to 3V3A_F" in FC and not pot_bad,
    "C8 100 n at U1 pin 16": "C8 100 n at U1 pin 16" in FC and ALLP["C8"].value == "100n"
    and mux[HC4051_DS["VCC"]] in ALLP["C8"].nets.values(),
    "channel 7 grounded": "Channel 7 is grounded" in FC and mux[HC4051_CH[7]] == "GND_F",
    "U9 QH' -> U10 SER": "U9 QH' → U10 SER" in FC and PARTS["face"]["U10"].nets[HC595_DS["SER"]] ==
    PARTS["face"]["U9"].nets[HC595_DS["QH'"]],
    "/OE low, /SRCLR high": "/OE low, /SRCLR high" in FC,
    "reds R80-R87, greens R88-R95": "(R80–R87)" in FC and "(R88–R95)" in FC
    and all(ALLP[f"R{k}"].nets["2"].endswith("_R") for k in range(80, 88))
    and all(ALLP[f"R{k}"].nets["2"].endswith("_G") for k in range(88, 96)),
    "common cathode to GND_D_F": "common cathode (middle lead) to\n  GND_D_F" in FC or "common cathode (middle lead) to GND_D_F" in FC,
    "buttons 1+2 GND_D_F, 3+4 BTN, LED 5 / 6": "contacts 1+2 to\n  GND_D_F, 3+4 to BTN_A_F / BTN_B_F" in FC and "(pin 5)" in FC
    and "(pin 6) to GND_D_F" in FC and not btn_bad,
    "C9, C10 100 n": "C9, C10 100 n" in FC and ALLP["C9"].value == ALLP["C10"].value == "100n",
}
ck.check("G.design_faceplate_circuits_text", all(fc_claims.values()),
         f"statements of design.md's Faceplate circuits found and true: {[k for k, v in fc_claims.items() if not v]} failed")
# the probe's swing at an unpatched normalized jack: PROBE (0 / 3.3 V) -> 10k -> switch -> tip -> 100k -> the
# stage's virtual ground at BIAS_A (design.md's Firmware section: "0.13 V / 3.13 V at the jack")
r_p, r_in = harness.ohms("10k"), harness.ohms("100k")
swing = [(vp * r_in + bias_a * r_p) / (r_in + r_p) for vp in (0.0, V33)]
msw = re.search(r"([\d.]+) V / ([\d.]+) V\s+at the jack", DESIGN)
ck.check("G.design_probe_swing", bool(msw) and abs(float(msw.group(1)) - swing[0]) < 0.006
         and abs(float(msw.group(2)) - swing[1]) < 0.006,
         f"design.md '{msw and msw.group(0)}'; 10k probe into 100k at BIAS_A {bias_a:.3f} V: {swing[0]:.3f} / {swing[1]:.3f} V")
bl = DESIGN[DESIGN.index("### Button LEDs"):DESIGN.index("## Faceplate circuits")]
ck.check("G.design_button_LED_text", "R60, R61 (470 Ω) from D2 / D3" in bl and ALLP["R60"].value == ALLP["R61"].value == "470"
         and set(ALLP["R60"].nets.values()) == {"BTN_LED_A_IO", "BTN_LED_A"} and circuit.SEED["3"] == ("D2", "BTN_LED_A_IO")
         and circuit.SEED["4"] == ("D3", "BTN_LED_B_IO"), "R60 / R61 470 R from D2 / D3 to the header")
mi = re.search(r"InitMux\((\w+), (\d+), (\w+), (\w+), (\w+)(?:,\s*SPEED_\d+CYCLES_5)?\)", " ".join(DESIGN.split()))
seed_by_net = {n: nm for p, (nm, n) in circuit.SEED.items() if n}
ck.check("G.design_InitMux_line", bool(mi) and mi.group(1) in seed_by_net["MUX_OUT"].split("/")
         and [mi.group(k) for k in (3, 4, 5)] == [seed_by_net[f"MUX_S{k}"].split("/")[0] for k in range(3)]
         and int(mi.group(2)) == len(circuit.POTS),
         f"design.md '{mi and mi.group(0)}': mux out {seed_by_net['MUX_OUT']}, S0..S2 "
         f"{[seed_by_net[f'MUX_S{k}'] for k in range(3)]}, {len(circuit.POTS)} pots (Y7 not scanned)")
# the HAL source: the same InitMux order
HAL = harness.text("firmware", "src", "hal_daisy.cc")
hm = re.search(r"InitMux\(\s*([\w:]+)\s*,\s*(\w+)\s*,\s*([\w:]+)\s*,\s*([\w:]+)\s*,\s*([\w:]+)\s*"
               r"(?:,\s*AdcChannelConfig::SPEED_\d+CYCLES_5\s*)?\)", HAL)        # [2026-11-14: + the speed]
def hal_pin(sym):
    """A HAL argument as a libDaisy name: kMuxS0 -> its 'constexpr Pin kMuxS0 = seed::D26;' -> D26."""
    sym = sym.split("::")[-1]
    m2 = re.search(r"constexpr Pin " + re.escape(sym) + r" = seed::(\w+);", HAL)
    return m2.group(1) if m2 else sym


hal_ok = bool(hm) and [hal_pin(hm.group(k)) for k in (3, 4, 5)] == ["D26", "D27", "D28"] \
    and hal_pin(hm.group(1)) in ("A10", "D25")
ck.check("G.firmware_InitMux_S0_S1_S2", hal_ok,
         f"hal_daisy.cc '{hm and ' '.join(hm.group(0).split())}': S0 / S1 / S2 must be D26 / D27 / D28 (MUX_S0..S2 on Seed pins 33-35)")

# firmware/test/board_tables.h (cheap cross-check with the datasheet tables, not with gen_board_tables.py's code)
BT = harness.text("firmware", "test", "board_tables.h")


def c_array(name):
    m = re.search(r"\b" + re.escape(name) + r"\[[^\]]*\]\s*=\s*\{([^}]*)\}", BT)
    return [t.strip().strip('"') for t in m.group(1).split(",") if t.strip()] if m else None


bits = {}
for u, base in (("U9", 0), ("U10", 8)):      # U9 -> U10 chain, U10's byte shifted first, MSB first
    for k, q in enumerate(HC595_Q):
        mm = re.fullmatch(r"L_(D\d)_([RG])", PARTS["face"][u].nets[HC595_DS[q]])
        bits[(mm.group(1), mm.group(2))] = base + k
red = [int(x) for x in c_array("kLedRedBit") or []]
grn = [int(x) for x in c_array("kLedGreenBit") or []]
refs = c_array("kLedRef") or []
want_r = [bits[(r, "R")] for r in refs]
want_g = [bits[(r, "G")] for r in refs]
ck.check("G.board_tables_LED_bits", red == want_r and grn == want_g and refs == [f"D{k}" for k in range(1, 9)],
         f"bit = 8 x (U10) + Q index (QA = 0), from SCLS041J's QA..QH pins; expected red {want_r} green {want_g}, "
         f"board_tables.h red {red} green {grn}")
pm = [int(x) for x in c_array("kPotMuxChannel") or []]
pr = c_array("kPotRef") or []
ch_of_pin = {v: k for k, v in HC4051_CH.items()}
want_pm = [ch_of_pin[dict((r, mp) for r, l, w, mp, c in circuit.POTS)[ref]] for ref in pr]
ck.check("G.board_tables_pot_channels", pm == want_pm and len(pr) == 7,
         f"channel of each pot's 4051 pin (SCHS122O); expected {want_pm}, board_tables.h {pm}")
rf_bt = [float(x) for x in c_array("kStageRf") or []]
ck.check("G.board_tables_stage_values", rf_bt == [harness.ohms(rf) for _, _, _, _, rf, _, _ in circuit.CV_CHANNELS],
         f"kStageRf {rf_bt}")
nproblems = re.search(r"kNumProblems = (\d+)", BT)
ck.check("G.board_tables_no_generator_problems", bool(nproblems) and nproblems.group(1) == "0",
         f"kNumProblems {nproblems and nproblems.group(1)}")
pinchecks = re.findall(r'\{ "([^"]+)", "(\w+)", "([^"]+)", (true|false) \}', BT)
ck.check("G.board_tables_pin_checks", len(pinchecks) == 20 and all(ok == "true" for *_, ok in pinchecks),
         f"{len(pinchecks)} HAL pin checks, failing: {[w for w, h, n, ok in pinchecks if ok != 'true']}")
# the board tables were generated from today's circuit.py: the ADC order, A pins
adc_bt = re.findall(r"Seed pin (\d+) (\S+)", BT)
adc_want = [(p, nm) for name, *_ in circuit.CV_CHANNELS for p, (nm, n) in circuit.SEED.items() if n == f"ADC_{name}"]
ck.check("G.board_tables_ADC_pins", adc_bt == adc_want, f"board_tables.h {adc_bt}, circuit.py {adc_want}")

ck.done()
