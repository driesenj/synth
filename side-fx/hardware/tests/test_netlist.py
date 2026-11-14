"""Netlist and pinout integrity of Side FXy (Moss).

What it checks
  A  circuit.py on its own: circuit.check(), unique designators, no single-pin nets, header kinds and pin
     counts, every header pin pair used on both boards, faceplate cross-board nets end in _F, no net name
     on both boards.
  B  circuit.py's pin maps against the manufacturers' pinouts (constants block below): TL074, 74HC165,
     74HC595 (every pin incl. /SRCLR, /OE, /CE, DS, Q7), H11L1, 2N3904, BAT85 / 1N4148, the SIP-9 bussed
     network, the Thonkiconn PJ398SM / WQP518MA and the PJ366ST, the EC11, the Thonk LED button, CN1
     against Waveshare's 1.9inch LCD Module, the Daisy Seed pinout, and the breakout's J1 / J3 / J4 / J5
     as traced in the breakout's own Gerbers (copper and bottom silk; results in the constants block): the
     header functions, and U5's footprint against the drill file under one rigid placement (mirrored: the
     breakout sits Seed side up); the traced ground / VIN / codec pins against circuit.py; the Seed's pin
     handedness in the routed footprint against the Seed datasheet's own pinout (the Seed faces the rear).
  C  The routed master's symbols and footprints: pin names in the symbols the routed parts were placed
     from, pad numbering and spacing of every footprint, and the silk polarity marks (diode bands, the
     TO-92 flat, DIP notch / dot and square pad, the SIP pin-1 bar).
  D  The routed master (SideFXy-routed.epro2) against circuit.py: every pad's net on both PCBs, designators
     complete, every PAD_NET record names a real pad of its footprint (by number and pad id), the pads
     left open are exactly design.md's "What EasyEDA's DRC will still say" list, the generator's two
     boards (copper_audit.generated_boards(), in memory) pad for pad against the routed ones, and each placed
     part's footprint pads, device (part number, value) and symbol pin names against the generated
     project's (EasyEDA keeps its own copy of a library part whose uuid it already holds on import).
  E  Connectivity on the routed copper (copper_audit.RoutedBoard.connectivity()): every net one piece, no
     other-net contacts, GND_F and GND_D_F never touch on the faceplate and meet only on the main board's
     GND through their own header pins.
  F  Header stacking: every HFn pad over its Hn pad within 0.01 mm, the X / X_F pairs of circuit.HEADERS on
     the stacked pads, the same pin counts, the same mounting holes on both boards, sides (male on the
     faceplate's top, sockets on the main board's bottom), nothing else under a header pin, and a ground
     pin in every header.
  G  The schematic pages of the routed and the generated exports against circuit.py (pin positions on
     named wires and net flags), and the pages design.md lists.
  H  design.md's tables (Seed pin map, CV stages, jacks, the chain, headers, DRC open pins) against
     circuit.py, and the netlist claims of the routing audit's "Clean" section.
  I  MIDI TRS type A (the MMA's 2018 TRS practice) and the MIDI 1.0 receiver circuit (CA-033); the jack
     normalling; design.md's J5 row against a three-pin PJ366ST.

Run from side-fx/hardware/tests:  python test_netlist.py
Only reads: imports circuit.py and copper_audit.py (generated_boards() builds the generator's boards in
memory and writes nothing), opens the two exports as zip files. Needs no downloads at run time.
"""
import collections
import math
import re

import harness

ck = harness.Checks("netlist")
circuit = harness.load("circuit")
MIL = harness.MIL

# ----------------------------------------------------------------------------------------------------------
# Datasheet pinouts and standards (pin numbers are exact facts: no min / typ / max)
#
# TI SLOS080W "TL07xx Low-Noise FET-Input Operational Amplifiers" (rev. July 2025), Figure / Table 4-6
# "Pin Functions: TL074x", D / N (PDIP-14) package:
TL074_DS = {"1OUT": "1", "1IN-": "2", "1IN+": "3", "VCC+": "4", "2IN+": "5", "2IN-": "6", "2OUT": "7",
            "3OUT": "8", "3IN-": "9", "3IN+": "10", "VCC-": "11", "4IN+": "12", "4IN-": "13", "4OUT": "14"}
# TI SCLS116H "SNx4HC165 8-Bit Parallel-Load Shift Registers" (rev. Dec 2015), Pin Functions, N package
# (TI names: SH/LD, CLK, E F G H, QH-bar, GND, QH, SER, A B C D, CLK INH, VCC); NXP 74HC165 rev. 5 names in
# brackets as circuit.py uses them: 1 /PL, 2 CP, 3..6 D4..D7, 7 /Q7, 8 GND, 9 Q7, 10 DS, 11..14 D0..D3,
# 15 /CE (clock enable, active LOW = TI's CLK INH: high = no change), 16 VCC. /PL low loads D0..D7.
HC165_DS = {"/PL": "1", "CP": "2", "D4": "3", "D5": "4", "D6": "5", "D7": "6", "/Q7": "7", "GND": "8",
            "Q7": "9", "DS": "10", "D0": "11", "D1": "12", "D2": "13", "D3": "14", "/CE": "15", "VCC": "16"}
# TI SCLS041 "SNx4HC595 8-Bit Shift Registers With 3-State Output Registers", Table 5-1 Pin Functions, N:
# QB 1, QC 2, QD 3, QE 4, QF 5, QG 6, QH 7, GND 8, QH' 9, /SRCLR 10 (active low clear), SRCLK 11, RCLK 12,
# /OE 13 (active low output enable), SER 14, QA 15, VCC 16.
HC595_DS = {"QA": "15", "QB": "1", "QC": "2", "QD": "3", "QE": "4", "QF": "5", "QG": "6", "QH": "7",
            "GND": "8", "QH'": "9", "/SRCLR": "10", "SRCLK": "11", "RCLK": "12", "/OE": "13", "SER": "14",
            "VCC": "16"}
# H11L1, Everlight H11LX series datasheet, pin configuration (read through a web search summary on
# 2026-11-13; the onsemi H11L1M / Vishay PDFs did not download): 1 anode, 2 cathode, 3 no connection, 4 output
# (Vo, open collector), 5 ground, 6 VCC. The same 6-pin DIP pinout as every H11L1 second source.
H11L1_DS = {"A": "1", "K": "2", "NC": "3", "VO": "4", "GND": "5", "VCC": "6"}
# onsemi 2N3903-D (2N3903 / 2N3904), TO-92 CASE 29 STYLE 1: pin 1 emitter, 2 base, 3 collector.
# CASE 29-11 outline: seen from the flat face with the leads down, pins 1-2-3 run left to right.
Q2N3904_DS = {"E": "1", "B": "2", "C": "3"}
# Vishay BAT85 (doc 85661) and Vishay / onsemi 1N4148 (DO-35): the coloured band marks the cathode.
# Bourns 4600X thick-film SIP networks, "-101" bussed circuit: pin 1 common, pins 2..n the resistors; pin 1
# marked on the body.
SIP_BUSSED_COMMON = "1"
# Thonkiconn PJ398SM / QingPu WQP518MA: KiCad Connector_Audio
# Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles.kicad_mod (fetched from gitlab.com/kicad/libraries/
# kicad-footprints, master, 2026-11-13): S (sleeve) at (0, 0), TN (tip switch) at (0, 3.1), T (tip) at
# (0, 11.4), the KEEPOUT (barrel) text at (0, 6.48), mm. TN touches the tip spring with no plug in.
# Thonk's own PJ398SM drawing not re-read (thonk.co.uk blocks fetches).
JACK_KICAD = {"S": 0.0, "TN": 3.1, "T": 11.4, "barrel": 6.48}
JACK_DS = {"S": "1", "TN": "2", "T": "3"}
# MIDI over TRS, type A: the MMA's 2018 recommended practice "Specification for use of TRS connectors with
# MIDI devices" (the brief calls it CA-033; CA-033 is the 2014 "MIDI 1.0 Electrical Specification Update"):
# tip = DIN pin 5 (current sink), ring = DIN pin 4 (current source), sleeve = DIN pin 2 (shield). Confirmed
# on 2026-11-13 through midi.org / cable-maker listings ("MIDI 5 (Sink) - TRS Tip, MIDI 4 (Source) - TRS
# Ring, MIDI 2 (Shield) - TRS Sleeve"); the PDF itself was not read. MIDI 1.0 electrical spec (CA-033): the
# receiver puts the opto LED between pin 4 (through 220 R) and pin 5, a reverse diode (1N914 / 1N4148)
# across the LED, and leaves the shield unconnected.
TRS_A = {"tip": "DIN5_sink", "ring": "DIN4_source", "sleeve": "DIN2_shield"}
# Daisy Seed datasheet v1.0.5, Pinout (page 1) and Table 3: pin number -> name.
SEED_DS = {1: "D0", 2: "D1", 3: "D2", 4: "D3", 5: "D4", 6: "D5", 7: "D6", 8: "D7", 9: "D8", 10: "D9",
           11: "D10", 12: "D11", 13: "D12", 14: "D13", 15: "D14", 16: "AUDIO IN 1", 17: "AUDIO IN 2",
           18: "AUDIO OUT 1", 19: "AUDIO OUT 2", 20: "AGND", 21: "3V3A", 22: "A0/D15", 23: "A1/D16",
           24: "A2/D17", 25: "A3/D18", 26: "A4/D19", 27: "A5/D20", 28: "A6/D21", 29: "A7/D22", 30: "A8/D23",
           31: "A9/D24", 32: "A10/D25", 33: "D26", 34: "D27", 35: "A11/D28", 36: "D29", 37: "D30", 38: "3V3D",
           39: "VIN", 40: "DGND"}
# Daisy Seed datasheet v1.0.5 pinout, peripheral column: D7 SPI1 CS, D8 SPI1 SCK, D9 SPI1 MISO, D10 SPI1
# MOSI, D14 USART1 Rx.
SEED_PERIPH_DS = {"D7": "SPI1 CS", "D8": "SPI1 SCK", "D9": "SPI1 MISO", "D10": "SPI1 MOSI", "D14": "USART1 Rx"}
# Waveshare "1.9inch LCD Module" wiki (www.waveshare.com/wiki/1.9inch_LCD_Module), Interface: the module's
# 8-pin cable, in order: VCC, GND, DIN (SPI MOSI), CLK (SPI SCK), CS (low active), DC (low = command),
# RST (low active), BL (backlight).
WAVESHARE_19_PINS = ["VCC", "GND", "DIN", "CLK", "CS", "DC", "RST", "BL"]
# Alps EC11E (EC11E15244G1 drawing) / Bourns PEC11R: the encoder row A, C (common), B with C in the middle,
# 2.5 mm pitch; the push switch's two terminals on the other side, 5.0 mm apart; two mounting tabs.
# KiCad RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm, relative to the shaft, KiCad y down: A (-7.5, -2.5),
# C (-7.5, 0), B (-7.5, +2.5), S1 (+7.0, +2.5), S2 (+7.0, -2.5), MP (0, -5.6) / (0, +5.6).
EC11_KICAD = {"A": (-7.5, -2.5), "C": (-7.5, 0.0), "B": (-7.5, 2.5), "S1": (7.0, 2.5), "S2": (7.0, -2.5),
              "MP1": (0.0, -5.6), "MP2": (0.0, 5.6)}
# Thonk low-profile LED button: the module-design skill's parts.md (Thonk's LowProfileButton.pdf /
# SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod as recorded there; not re-confirmed against Thonk: its site
# blocks fetches): contacts 1+2 and 3+4, LED anode 5, cathode 6, at (+-2.54, +-2.54) and (+-2.7, 0).
BUTTON_DS = {"contact_a": {"1", "2"}, "contact_b": {"3", "4"}, "LED_A": "5", "LED_K": "6"}
BUTTON_XY = {"1": (2.54, 2.54), "2": (-2.54, 2.54), "3": (2.54, -2.54), "4": (-2.54, -2.54), "5": (2.7, 0.0),
             "6": (-2.7, 0.0)}
# Rob Heel's seed_power_opamps breakout (github.com/rob-scape/daisy-seed-breakout-boards, daisy-seed-dcdc-opamps,
# Gerbers from EasyEDA v6.5.51, 2025-08-29, board v0.2). Traced on 2026-11-13 from Gerber_TopLayer / BottomLayer
# and Drill_PTH_Through (+ _Via): the copper rasterised at 0.025 mm, joined through every plated hole, the
# passives (0603 / 1206 / SOD-123 pad pairs) and the TL074 sections followed from the headers to the Seed's
# pins. Frame: the Gerbers' top view, mm. The bottom silkscreen (the Seed side) says the same in words: J1 "-12"
# with "GND" at pin 1, J3 "+12" with "GND", "IN 1 A, GND, IN 2 A, GND" and "OUT 1 A, GND, OUT 2 A, GND" by the
# audio headers, "3.3A" at pin 21, "3.3D" / "VIN" at pins 38 / 39, "USB SEED" at the pin 1 / 40 end, "RED STRIPE"
# at J2's pin 1.
#   Seed pins 1..20 in the row y -17.018 from x 85.09 (pin 1, square) to 36.83 (pin 20), 21..40 in the row
#   y -1.778 from x 36.83 (pin 21) to 85.09 (pin 40, square). Pin 20 and pin 40 are on the breakout's GND (J2
#   pins 3-8), pin 39 on the DC/DC's +5 V output; 16 / 17 are driven by the J5-1 / J5-3 stages, 18 / 19 drive
#   the J4-1 / J4-3 stages.
BREAKOUT_SEED_XY = {k: (85.09 - (k - 1) * 2.54, -17.018) for k in range(1, 21)}
BREAKOUT_SEED_XY.update({k: (36.83 + (k - 21) * 2.54, -1.778) for k in range(21, 41)})
BREAKOUT_SEED_NET = {20: "GND", 40: "GND", 39: "+5V"}
BREAKOUT_CODEC = {16: "J5-1", 17: "J5-3", 18: "J4-1", 19: "J4-3"}
#   J1 (row of pins 1-20, beyond pin 20, one empty position): pin 1 (square, x 31.75) GND, pins 2-4 (x 29.21,
#   26.67, 24.13) the -12 V rail (J2 pins 1-2 through D3 B5819W; C18 and both TL074s' middle pads). J3 the same
#   in the other row, +12 V (through D2). J5 (row of pins 1-20, beyond pin 1, no gap): pin 1 (square, x 95.25)
#   audio in 1, 2 GND, 3 audio in 2, 4 GND (x 87.63, next to the Seed). J4 the same in the other row, outputs.
BREAKOUT_HEADERS = {"J1": ["GND", "-12V", "-12V", "-12V"], "J3": ["GND", "+12V", "+12V", "+12V"],
                    "J4": ["AOUT1", "GND", "AOUT2", "GND"], "J5": ["AIN1", "GND", "AIN2", "GND"]}
BREAKOUT_HEADER_XY = {"J1": [(31.75 - i * 2.54, -17.018) for i in range(4)],
                      "J3": [(31.75 - i * 2.54, -1.778) for i in range(4)],
                      "J5": [(95.25 - i * 2.54, -17.018) for i in range(4)],
                      "J4": [(95.25 - i * 2.54, -1.778) for i in range(4)]}
# The Seed's pins run clockwise in the Gerbers' top view (counter-clockwise from the Seed's own top, as the
# Daisy datasheet's pinout shows): the Seed, H1 / H2, J1-J5 and the THT parts are on the bottom silk, the SMD
# op-amps on the top copper. Mounted Seed side up, the main board sees the mirror of the Gerbers' top view.
BREAKOUT_FOOTPRINT_MIRRORED = True
# QingPu WQP-PJ366ST (Thonkiconn stereo): pin positions relative to the sleeve pin, mm, EasyEDA frame (y up, the
# barrel towards +y). NOT CONFIRMED yet: placeholder from the footprint's own source (KiCad merge request 1073).
# The only pin data found: KiCad kicad-footprints merge requests 823 / 1073 (Rob Kam, 2018, closed, never
# merged; read through the GitLab API on 2026-11-13), Jack_3.5mm_QingPu_WQP-PJ366ST_Vertical: three pads,
# S (sleeve) at (0, 0), R (ring) at (0, 3.1), T (tip) at (0, 11.4), "suits symbol AudioJack3_Ground", no
# switch contacts. QingPu's product page has no PDF (and did not answer), Thonk's site blocks fetches: a
# community source, not a manufacturer drawing.
PJ366ST_SOURCE = "KiCad MR 1073 / 823 (community, unmerged; no manufacturer drawing found)"
PJ366ST_DS_DIST = {"2": 3.1, "3": 11.4}           # distance from the sleeve pin along the row, mm
PJ366ST_DS_FUNC = {"1": "sleeve", "2": "ring", "3": "tip"}

# ----------------------------------------------------------------------------------------------------------
MB, FB = circuit.main_board_parts(), circuit.faceplate_parts()
MBN, FBN = circuit.nets_of(MB), circuit.nets_of(FB)
PARTS = {"main": {p.ref: p for p in MB}, "face": {p.ref: p for p in FB}}
NETS = {"main": MBN, "face": FBN}


def pins_of(board, net):
    return sorted(NETS[board].get(net, []))


# ----------------------------------------------------------------------------------------------------------
# A  circuit.py on its own
ck.check("A.circuit_check_clean", circuit.check() == [], f"circuit.check() problems: {circuit.check()}")
for name, parts in (("main", MB), ("face", FB)):
    dup = [r for r, n in collections.Counter(p.ref for p in parts).items() if n > 1]
    ck.check(f"A.unique_refs.{name}", not dup, f"expected no duplicate designators, got {dup}")
    nets = circuit.nets_of(parts)
    single = {n: v for n, v in nets.items() if len(v) < 2}
    ck.check(f"A.no_single_pin_nets.{name}", not single, f"expected every net on >= 2 pins, got {single}")
    empty = [(p.ref, k) for p in parts for k, v in p.nets.items() if not v]
    ck.check(f"A.no_empty_net_names.{name}", not empty, f"pins with an empty net name: {empty}")

kind_bad = [(ref, kind, len(pins)) for ref, kind, pins in circuit.HEADERS if int(kind[3:]) != len(pins)]
ck.check("A.header_kind_matches_pin_count", not kind_bad, f"HDRn kind against len(pins): {kind_bad}")
bad_pairs = []
for ref, kind, pins in circuit.HEADERS:
    for i, (a, b) in enumerate(pins):
        want_b = {"GND": ("GND_F", "GND_D_F")}.get(a, (a + "_F",))
        if b not in want_b or len(MBN[a]) < 2 or len(FBN[b]) < 2:
            bad_pairs.append((ref, i + 1, a, b, len(MBN[a]), len(FBN[b])))
ck.check("A.header_pairs_used_both_boards", not bad_pairs,
         f"expected X on >= 2 main-board pins and X_F (GND -> GND_F or GND_D_F) on >= 2 faceplate pins; "
         f"bad {bad_pairs}")
hdr_fb = {b for _, _, pins in circuit.HEADERS for a, b in pins}
hdr_mb = {a for _, _, pins in circuit.HEADERS for a, b in pins}
cross_bad = sorted(n for n in hdr_fb if not n.endswith("_F"))
ck.check("A.cross_board_nets_end_in_F", not cross_bad, f"faceplate header nets without _F: {cross_bad}")
mb_bad = sorted(n for n in MBN if n.endswith("_F"))
ck.check("A.main_nets_never_F", not mb_bad, f"main-board nets ending in _F: {mb_bad}")
shared = sorted(set(MBN) & set(FBN))
ck.check("A.no_net_on_both_boards", not shared, f"net names on both boards: {shared}")
named_pairs = sorted(n[:-2] for n in FBN if n.endswith("_F") and n[:-2] in MBN and n[:-2] not in hdr_mb)
ck.check("A.cross_board_names_only_via_headers", not named_pairs,
         f"X / X_F pairs on the two boards with no header pin joining them: {named_pairs}")
fb_local = sorted(n for n in FBN if n not in hdr_fb)
ck.check("A.faceplate_local_nets", fb_local and all(not any(pin.startswith("HF") for pin in FBN[n]) for n in fb_local),
         f"faceplate-only nets (never on a header pin): {fb_local}")
hdr_ok = []
for ref, _, pins in circuit.HEADERS:
    m, f = PARTS["main"][ref].nets, PARTS["face"][circuit.fb_ref(ref)].nets
    for i, (a, b) in enumerate(pins):
        if m.get(str(i + 1)) != a or f.get(str(i + 1)) != b:
            hdr_ok.append((ref, i + 1, m.get(str(i + 1)), f.get(str(i + 1)), a, b))
    if len(m) != len(pins) or len(f) != len(pins):
        hdr_ok.append((ref, "pin count", len(m), len(f), len(pins)))
ck.check("A.header_parts_match_HEADERS", not hdr_ok, f"H<n> / HF<n> pin nets against circuit.HEADERS: {hdr_ok}")
# the two faceplate grounds: GND_F for the jacks (audio / CV return), GND_D_F for the logic
gf_pins = [(ref, i + 1) for ref, _, pins in circuit.HEADERS for i, (a, b) in enumerate(pins) if b == "GND_F"]
gd_pins = [(ref, i + 1) for ref, _, pins in circuit.HEADERS for i, (a, b) in enumerate(pins) if b == "GND_D_F"]
ck.check("A.both_faceplate_grounds_have_header_pins", gf_pins and gd_pins,
         f"design.md: GND_F and GND_D_F join only on the main board, each through its own header pins; "
         f"GND_F pins {gf_pins}, GND_D_F pins {gd_pins}")
jack_gnd = sorted({n for p in FB if p.kind in ("JACK", "JACK_TRS") for n in p.nets.values() if n.startswith("GND")})
logic_gnd = sorted({n for p in FB if p.kind in ("HC165", "RN9", "ENC", "SWLED", "HDR8RA") for n in p.nets.values()
                    if n.startswith("GND")})
ck.check("A.jacks_on_GND_F_logic_on_GND_D_F", jack_gnd == ["GND_F"] and logic_gnd == ["GND_D_F"],
         f"design.md: GND_F = jack sleeves and lugs, GND_D_F = logic, encoders, buttons, display; "
         f"jacks use {jack_gnd}, logic uses {logic_gnd}")

# ----------------------------------------------------------------------------------------------------------
# B  pin maps against the datasheets
sec_ds = {s: (TL074_DS[f"{s}OUT"], TL074_DS[f"{s}IN-"], TL074_DS[f"{s}IN+"]) for s in (1, 2, 3, 4)}
ck.check("B.TL074_SECTION", circuit.SECTION == sec_ds, f"expected {sec_ds}, got {circuit.SECTION}")
u6 = PARTS["main"]["U6"].nets
ck.check("B.TL074_supply.U6", u6.get(TL074_DS["VCC+"]) == "+12V" and u6.get(TL074_DS["VCC-"]) == "-12V",
         f"expected pin 4 +12V, pin 11 -12V; got 4={u6.get('4')}, 11={u6.get('11')}")
ck.check("B.TL074_all_pins_used.U6", set(u6) == set(TL074_DS.values()), f"pins tied {sorted(u6, key=int)}")
stage_bad = []
for name, s in circuit.CV_CHANNELS:
    o, m, p = (TL074_DS[f"{s}{k}"] for k in ("OUT", "IN-", "IN+"))
    if not (u6[o] == f"OA_{name}" and u6[m] == f"IN_{name}" and u6[p] == "BIAS"):
        stage_bad.append((name, s, u6[o], u6[m], u6[p]))
ck.check("B.TL074_sections_wired", not stage_bad,
         f"each CV stage: section OUT = OA_CVn, IN- = IN_CVn, IN+ = BIAS (inverting stage); bad {stage_bad}")

# 74HC165: circuit.py's map, then every pin of U1 and U2
ck.check("B.HC165_INPUTS_are_D0_D7", circuit.HC165_INPUTS == [HC165_DS[f"D{i}"] for i in range(8)],
         f"datasheet D0..D7 = {[HC165_DS[f'D{i}'] for i in range(8)]}, circuit.HC165_INPUTS {circuit.HC165_INPUTS}")
# Verifier fix (2026-11-13): this check compared a dict typed into the test with HC165_DS, i.e. two test constants,
# so it could not fail. It now reads the pin-map comment in circuit.py itself ("# 74HC165: 1 /PL, 2 CP, 3..6 D4..D7,
# ...") and compares every pin number it names with the datasheet. Names are compared without the "/" (the comment
# writes pin 15 "CE"; the missing active-low bar is C.symbol_74HC165's finding, not repeated here).
_c165 = re.search(r"^#\s*74HC165:\s*(.+)$", harness.text("hardware", "tools", "circuit.py"), re.M)
c165_bad, c165_seen = [], set()
for _tok in (_c165.group(1).split(",") if _c165 else []):
    _m = re.match(r"\s*(\d+)\.\.(\d+)\s+D(\d+)\.\.D(\d+)\s*$", _tok)
    if _m:
        _pins = range(int(_m.group(1)), int(_m.group(2)) + 1)
        _names = [f"D{k}" for k in range(int(_m.group(3)), int(_m.group(4)) + 1)]
    else:
        _m = re.match(r"\s*(\d+)\s+(\S+)\s*$", _tok)
        if not _m:
            c165_bad.append(("unparsed", _tok.strip()))
            continue
        _pins, _names = [int(_m.group(1))], [_m.group(2)]
    for _p, _n in zip(_pins, _names):
        _want = HC165_DS.get(_n, HC165_DS.get("/" + _n) if not _n.startswith("/") else None)
        c165_seen.add(str(_p))
        if _want != str(_p):
            c165_bad.append((_p, _n, "datasheet pin", _want))
ck.check("B.HC165_comment_map", bool(_c165) and not c165_bad and c165_seen == set(HC165_DS.values()),
         f"circuit.py '# 74HC165: {_c165.group(1) if _c165 else None}' against TI / NXP: differences {c165_bad}, "
         f"pins not named {sorted(set(HC165_DS.values()) - c165_seen, key=int)}")
want165 = {"U1": {"DS": "SR_CHAIN", "Q7": "SR_DIN_F"}, "U2": {"DS": "GND_D_F", "Q7": "SR_CHAIN"}}
for u in ("U1", "U2"):
    n = PARTS["face"][u].nets
    exp = {HC165_DS["/PL"]: "SR_LOAD_F", HC165_DS["CP"]: "SR_CLK_F", HC165_DS["GND"]: "GND_D_F",
           HC165_DS["VCC"]: "3V3D_F", HC165_DS["/CE"]: "GND_D_F", HC165_DS["DS"]: want165[u]["DS"],
           HC165_DS["Q7"]: want165[u]["Q7"]}
    for i, net in enumerate(circuit.SR_INPUTS[u]):
        exp[HC165_DS[f"D{i}"]] = net
    diff = {k: (n.get(k), v) for k, v in exp.items() if n.get(k) != v}
    ck.check(f"B.HC165_pins.{u}", not diff and HC165_DS["/Q7"] not in n and len(n) == 15,
             f"/PL=SR_LOAD_F, CP=SR_CLK_F, /CE low (GND_D_F: clock enabled), DS/Q7 chain {want165[u]}, "
             f"D0..D7 = SR_INPUTS, /Q7 (7) open; differences (got, want) {diff}, /Q7 = {n.get('7')}")
# 74HC595 (main board)
ck.check("B.HC595_OUT_is_QA_QH", circuit.HC595_OUT == [HC595_DS[f"Q{c}"] for c in "ABCDEFGH"],
         f"datasheet QA..QH = {[HC595_DS[f'Q{c}'] for c in 'ABCDEFGH']}, circuit {circuit.HC595_OUT}")
u3 = PARTS["main"]["U3"].nets
exp = {HC595_DS["GND"]: "GND", HC595_DS["VCC"]: "3V3D", HC595_DS["/SRCLR"]: "3V3D", HC595_DS["/OE"]: "GND",
       HC595_DS["SRCLK"]: "SR_CLK", HC595_DS["RCLK"]: "SR_LOAD", HC595_DS["SER"]: "SR_DOUT"}
for k, ref in enumerate(circuit.LED_ORDER):
    exp[HC595_DS["Q" + "ABCDEFGH"[k]]] = f"L_{circuit.LED_WORD[ref]}"
diff = {k: (u3.get(k), v) for k, v in exp.items() if u3.get(k) != v}
spare = [HC595_DS[q] for q in ("QF", "QG", "QH", "QH'")]
ck.check("B.HC595_pins.U3", not diff and not any(p in u3 for p in spare),
         f"/SRCLR high (inactive), /OE low (outputs on), SER = SR_DOUT, SRCLK = SR_CLK, RCLK = SR_LOAD, QA..QE "
         f"the LEDs, QF-QH and QH' open; differences (got, want) {diff}, spare pins tied "
         f"{[p for p in spare if p in u3]}")
# LED resistors after the 595 outputs, to the buttons' anodes through H3
led_bad = []
for k, ref in enumerate(circuit.LED_ORDER):
    w = circuit.LED_WORD[ref]
    r = [p for p in MB if p.kind == "R" and set(p.nets.values()) == {f"L_{w}", f"LED_{w}"}]
    sw = PARTS["face"][ref].nets
    if len(r) != 1 or sw.get(BUTTON_DS["LED_A"]) != f"LED_{w}_F" or sw.get(BUTTON_DS["LED_K"]) != "GND_D_F":
        led_bad.append((ref, [p.ref for p in r], sw.get("5"), sw.get("6")))
ck.check("B.button_LED_chain", not led_bad,
         f"595 Q -> 470R -> LED_x -> H3 -> button pin 5 (anode), pin 6 (cathode) -> GND_D_F; bad {led_bad}")
btn_bad = []
for ref, label, net in circuit.BUTTONS:
    n = PARTS["face"][ref].nets
    a = {n.get(p) for p in BUTTON_DS["contact_a"]}
    b = {n.get(p) for p in BUTTON_DS["contact_b"]}
    if not (len(a) == 1 and len(b) == 1 and sorted([*a, *b]) == sorted(["GND_D_F", net])):
        btn_bad.append((ref, n))
ck.check("B.button_contacts", not btn_bad,
         f"contacts 1+2 one side, 3+4 the other (one GND_D_F, one the switch line); bad {btn_bad}")

# H11L1
u7 = PARTS["main"]["U7"].nets
exp = {H11L1_DS["A"]: "OPTO_A", H11L1_DS["K"]: "MIDI_TIP", H11L1_DS["VO"]: "MIDI_RX", H11L1_DS["GND"]: "GND",
       H11L1_DS["VCC"]: "3V3D"}
diff = {k: (u7.get(k), v) for k, v in exp.items() if u7.get(k) != v}
ck.check("B.H11L1_pins.U7", not diff and H11L1_DS["NC"] not in u7,
         f"1 anode OPTO_A, 2 cathode MIDI_TIP, 3 NC open, 4 Vo MIDI_RX, 5 GND, 6 VCC 3V3D; diff {diff}, "
         f"pin 3 = {u7.get('3')}")
# 2N3904
q1 = PARTS["main"]["Q1"].nets
ck.check("B.2N3904_EBC.Q1", q1.get(Q2N3904_DS["E"]) == "GND" and q1.get(Q2N3904_DS["B"]) == "B_CLK"
         and q1.get(Q2N3904_DS["C"]) == "CLK",
         f"onsemi TO-92 style 1: 1 E (GND), 2 B (B_CLK), 3 C (CLK); got {q1}")
# Diodes: circuit.py says pin 1 = cathode on both
d1, d2 = PARTS["main"]["D1"].nets, PARTS["main"]["D2"].nets
ck.check("B.BAT85_clamp_polarity.D1", d1 == {"1": "B_CLK", "2": "GND"},
         f"design.md: BAT85 cathode on the base, anode to GND (clamps negative swings); circuit pin 1 (cathode) "
         f"{d1.get('1')}, pin 2 (anode) {d1.get('2')}")
ck.check("B.1N4148_antiparallel.D2", d2.get("1") == u7.get(H11L1_DS["A"]) and d2.get("2") == u7.get(H11L1_DS["K"]),
         f"1N4148 cathode on the LED's anode, anode on its cathode (anti-parallel); D2 cathode {d2.get('1')}, "
         f"anode {d2.get('2')}, LED A {u7.get('1')}, K {u7.get('2')}")
# SIP-9 bussed: pin 1 common to 3V3D_F, pins 2..9 one per 165 input
rn_bad = []
for u, rn in circuit.PULLUPS.items():
    n = PARTS["face"][rn].nets
    if n.get(SIP_BUSSED_COMMON) != "3V3D_F" or sorted(n.get(str(i)) for i in range(2, 10)) != sorted(circuit.SR_INPUTS[u]):
        rn_bad.append((rn, n))
ck.check("B.SIP9_bussed_common_pin1", not rn_bad,
         f"Bourns 4600X -101: pin 1 common (3V3D_F), 2..9 one per input of its 165; bad {rn_bad}")
# Jacks: 1 sleeve, 2 switch lug (TN), 3 tip
jack_bad = []
for ref, label, tip, tn in circuit.JACKS:
    n = PARTS["face"][ref].nets
    if ref == "J5":
        continue
    if n.get(JACK_DS["S"]) != "GND_F" or n.get(JACK_DS["T"]) != tip or n.get(JACK_DS["TN"]) != tn:
        jack_bad.append((ref, label, n))
ck.check("B.jacks_S_TN_T", not jack_bad, f"expected 1 = sleeve GND_F, 2 = TN, 3 = tip; bad {jack_bad}")
# EC11: C common and the switch to GND_D_F, A / B / switch to the 165 lines; mounting tabs to GND_D_F
enc_bad = []
for k, (ref, label) in enumerate(circuit.ENCODERS):
    n = PARTS["face"][ref].nets
    sw = {n.get("S1"), n.get("S2")}
    if not (n.get("C") == "GND_D_F" and {n.get("A"), n.get("B")} == {f"ENC{k + 1}_A_F", f"ENC{k + 1}_B_F"}
            and sw == {"GND_D_F", f"BTN_K{k + 1}_F"} and n.get("MP1") == n.get("MP2") == "GND_D_F"):
        enc_bad.append((ref, n))
ck.check("B.EC11_pins", not enc_bad, f"C (middle pin) common to GND_D_F, A / B the phases, one switch pin GND_D_F "
                                     f"and the other BTN_Kn, tabs GND_D_F; bad {enc_bad}")
# CN1 against Waveshare's cable order
want_cn1 = {"VCC": "3V3D_F", "GND": "GND_D_F", "DIN": "LCD_MOSI_F", "CLK": "LCD_SCK_F", "CS": "LCD_CS_F",
            "DC": "LCD_DC_F", "RST": "LCD_RST_F", "BL": "LCD_BL_F"}
cn1 = PARTS["face"]["CN1"].nets
got_cn1 = [cn1.get(str(i + 1)) for i in range(8)]
ck.check("B.CN1_Waveshare_order", got_cn1 == [want_cn1[s] for s in WAVESHARE_19_PINS],
         f"Waveshare 1.9inch LCD Module: {WAVESHARE_19_PINS}; CN1 pins 1..8 {got_cn1}")
# Daisy Seed: circuit.SEED's names against the datasheet
seed_bad = []
for pin in range(1, 41):
    name = circuit.SEED[str(pin)][0]
    ds = SEED_DS[pin]
    norm = {"AIN1": "AUDIO IN 1", "AIN2": "AUDIO IN 2", "AOUT1": "AUDIO OUT 1", "AOUT2": "AUDIO OUT 2"}.get(name, name)
    if "/" in norm:                                   # circuit "D15/A0" vs datasheet "A0/D15"
        norm = "/".join(sorted(norm.split("/")))
        ds = "/".join(sorted(ds.split("/")))
    if norm != ds:
        seed_bad.append((pin, name, SEED_DS[pin]))
ck.check("B.Seed_pin_names", not seed_bad, f"circuit.SEED names against the Daisy Seed datasheet v1.0.5 pinout; "
                                           f"bad {seed_bad}")
u5 = PARTS["main"]["U5"].nets
pw_bad = [(p, u5.get(p), want) for p, want in (("20", "GND"), ("40", "GND"), ("21", "3V3A"), ("38", "3V3D"))
          if u5.get(p) != want]
ck.check("B.Seed_power_pins", not pw_bad and "39" not in u5,
         f"20 AGND and 40 DGND on GND, 21 3V3A, 38 3V3D, 39 VIN open (the breakout feeds VIN itself); bad "
         f"{pw_bad}, VIN = {u5.get('39')}")
ck.check("B.Seed_codec_pins_open", not any(str(p) in u5 for p in (16, 17, 18, 19)),
         f"design.md: pins 16-19 (codec) left to the breakout's op-amps; tied {[p for p in (16, 17, 18, 19) if str(p) in u5]}")
periph_bad = []
for pin, net, fn in (("8", "LCD_CS", "SPI1 CS"), ("9", "LCD_SCK", "SPI1 SCK"), ("11", "LCD_MOSI", "SPI1 MOSI"),
                     ("15", "MIDI_RX", "USART1 Rx")):
    if u5.get(pin) != net or SEED_PERIPH_DS.get(SEED_DS[int(pin)]) != fn:
        periph_bad.append((pin, SEED_DS[int(pin)], SEED_PERIPH_DS.get(SEED_DS[int(pin)]), u5.get(pin)))
ck.check("B.Seed_peripheral_pins", not periph_bad,
         f"display on SPI1 (CS D7, SCK D8, MOSI D10), MIDI on USART1 Rx (D14), per the datasheet's pinout; "
         f"bad {periph_bad}")
adc_bad = [(name, f"ADC_{name}", [p for p, (nm, n) in circuit.SEED.items() if n == f"ADC_{name}"]) for name, s in
           circuit.CV_CHANNELS]
adc_ok = all(len(v[2]) == 1 and SEED_DS[int(v[2][0])].startswith("A") for v in adc_bad)
ck.check("B.Seed_ADC_pins_are_analog", adc_ok, f"each ADC_CVn on one Seed pin with an ADC (An) function: {adc_bad}")
# The breakout's 1x4 headers, traced in its Gerbers (constants block, BREAKOUT_*): circuit.SEED's names per pin
seed_j_bad = []
for hdr, funcs in BREAKOUT_HEADERS.items():
    for i, fn in enumerate(funcs):
        key = f"{hdr}-{i + 1}"
        name, net = circuit.SEED.get(key, (None, None))
        want_net = {"GND": "GND", "-12V": "-12V", "+12V": "+12V", "AIN1": "IN1", "AIN2": "IN2", "AOUT1": "OUT1",
                    "AOUT2": "OUT2"}[fn]
        if name != fn or net != want_net:
            seed_j_bad.append((key, "traced", fn, "circuit.SEED", name, net))
ck.check("B.breakout_J1_J3_J4_J5_functions", not seed_j_bad,
         f"breakout Gerbers (copper traced + bottom silk): J1 GND -12 -12 -12, J3 GND +12 +12 +12, J4 AOUT1 GND AOUT2 "
         f"GND, J5 AIN1 GND AIN2 GND; differences {seed_j_bad}")
# Verifier fix (2026-11-13): this check only tested BREAKOUT_SEED_NET against itself (a constant against a
# constant). It now holds the traced breakout against circuit.py: every Seed pin the breakout grounds must be on the
# main board's GND, the pin the breakout drives from its DC/DC (VIN) and the codec pins its op-amps drive must be left
# open by the main board (two drivers on one pin otherwise).
seed_rows_bad = []
for k, bnet in BREAKOUT_SEED_NET.items():
    mnet = u5.get(str(k))
    if (bnet == "GND" and mnet != "GND") or (bnet == "+5V" and mnet is not None):
        seed_rows_bad.append((k, "breakout", bnet, "main board", mnet))
for k, stage in BREAKOUT_CODEC.items():
    if u5.get(str(k)) is not None:
        seed_rows_bad.append((k, "breakout", stage, "main board", u5.get(str(k))))
ck.check("B.breakout_seed_ground_pins", not seed_rows_bad and set(BREAKOUT_SEED_NET) == {20, 39, 40},
         f"traced: Seed pins 20 and 40 on the breakout's GND (main board must ground them too), pin 39 (VIN) on the "
         f"DC/DC's +5 V and 16-19 driven by its op-amp stages (main board must leave them open); conflicts "
         f"{seed_rows_bad}")


# ----------------------------------------------------------------------------------------------------------
# Export parsing (own helpers on harness.read_export / harness.routed)
R = harness.routed()
BOARDS = {"main": R.main, "face": R.face}


def fp_doc(board, ref):
    return R.fp_by_uuid[R.attrs(board, ref)["Footprint"]]


def fp_pads(doc):
    """{num: (x mm, y mm, shape, pad record id)} of a FOOTPRINT doc (local frame, y up)."""
    out = {}
    for h, p in doc["recs"]:
        if h["type"] == "PAD" and p:
            out[str(p["num"])] = (p["centerX"] * MIL, p["centerY"] * MIL, p["defaultPad"]["padType"], h["id"])
    return out


def silk(doc, layers=(3,)):
    """Silk segments [(x1, y1, x2, y2)] and circles [(cx, cy, r)] of a footprint, mm (straight POLY paths only)."""
    segs, circles = [], []
    for h, p in doc["recs"]:
        if h["type"] != "POLY" or p.get("layerId") not in layers:
            continue
        path = p["path"]
        if path and path[0] == "CIRCLE":
            circles.append((path[1] * MIL, path[2] * MIL, path[3] * MIL))
            continue
        pts, i = [], 0
        while i < len(path):
            if path[i] == "L":
                i += 1
                continue
            if isinstance(path[i], str):        # ARC sweep x y: keep the end point
                pts.append((path[i + 2] * MIL, path[i + 3] * MIL))
                i += 4
                continue
            pts.append((path[i] * MIL, path[i + 1] * MIL))
            i += 2
        segs += [(*pts[k], *pts[k + 1]) for k in range(len(pts) - 1)]
    return segs, circles


def symbol_of(board, ref):
    return R.device(board, ref).get("Symbol")


# ----------------------------------------------------------------------------------------------------------
# B (cont.)  the breakout footprint against the Gerber trace: one rigid placement (mirror allowed) must put
# every traced hole on the footprint pad of the same name
u5fp = fp_pads(fp_doc("main", "U5"))
src = [BREAKOUT_SEED_XY[k] for k in (1, 20, 21)]
dst = [u5fp[str(k)][:2] for k in (1, 20, 21)]


def _fit(mirror):
    s = [(x, -y) if mirror else (x, y) for x, y in src]
    a = math.atan2(s[1][1] - s[0][1], s[1][0] - s[0][0])
    b = math.atan2(dst[1][1] - dst[0][1], dst[1][0] - dst[0][0])
    th = b - a

    def f(p):
        x, y = (p[0], -p[1]) if mirror else p
        x, y = x - s[0][0], y - s[0][1]
        return (dst[0][0] + x * math.cos(th) - y * math.sin(th), dst[0][1] + x * math.sin(th) + y * math.cos(th))
    return f, math.hypot(f(src[2])[0] - dst[2][0], f(src[2])[1] - dst[2][1])


fits = {m: _fit(m) for m in (False, True)}
mirror = min(fits, key=lambda m: fits[m][1])
xf = fits[mirror][0]
pos_bad = []
for k, xy in BREAKOUT_SEED_XY.items():
    q = xf(xy)
    if math.hypot(q[0] - u5fp[str(k)][0], q[1] - u5fp[str(k)][1]) > 0.05:
        pos_bad.append((k, tuple(round(v, 2) for v in q), tuple(round(v, 2) for v in u5fp[str(k)][:2])))
for hdr, holes in BREAKOUT_HEADER_XY.items():
    for i, xy in enumerate(holes):
        q, pad = xf(xy), u5fp.get(f"{hdr}-{i + 1}")
        if pad is None or math.hypot(q[0] - pad[0], q[1] - pad[1]) > 0.05:
            pos_bad.append((f"{hdr}-{i + 1}", tuple(round(v, 2) for v in q), pad and tuple(round(v, 2) for v in pad[:2])))
ck.check("B.breakout_footprint_vs_gerbers", not pos_bad and fits[mirror][1] < 0.05,
         f"40 Seed holes and the 16 J1/J3/J4/J5 holes of the breakout's drill file, placed by one rigid transform "
         f"({'mirrored' if mirror else 'not mirrored'}), against U5's footprint pads; off by > 0.05 mm: {pos_bad}")
ck.check("B.breakout_footprint_side", mirror == BREAKOUT_FOOTPRINT_MIRRORED,
         f"the Gerbers' bottom silk carries the Seed outline, H1/H2, J1-J5 and the THT parts, the SMD op-amps are on "
         f"the top copper: the breakout goes on the main board Seed side up, so the main board sees the mirror of the "
         f"Gerbers' top view; U5's footprint is {'the mirror' if mirror else 'NOT the mirror'} of that view")
# Verifier addition (2026-11-13), independent of the Gerber trace: the Daisy Seed datasheet v1.0.5's pinout (page 1,
# the component side, USB at the bottom) runs 1 bottom-right -> 20 top-right, 21 top-left -> 40 bottom-left:
# counter-clockwise. U5 sits on the main board's top layer (the stack's rear); the Seed is the outermost board, so
# seen from the rear (EasyEDA's top view) it shows its component side and its pins must run counter-clockwise there
# too. (The drill pattern alone also fits with the rows swapped, pin k on pad 41-k: only the names tell them apart.)
SEED_PINOUT_CCW_FROM_TOP = True
_ring = [u5fp[str(k)][:2] for k in range(1, 41)]
_area = sum(_ring[i][0] * _ring[(i + 1) % 40][1] - _ring[(i + 1) % 40][0] * _ring[i][1] for i in range(40)) / 2
ck.check("B.seed_pin_handedness_rear_view", (_area > 0) == SEED_PINOUT_CCW_FROM_TOP and not R.main.parts["U5"]["bottom"],
         f"U5 on the {'bottom' if R.main.parts['U5']['bottom'] else 'top'} layer, pins 1..40 run "
         f"{'counter-clockwise' if _area > 0 else 'clockwise'} in the top view (signed area {_area:.0f} mm2); the Seed's "
         f"own pinout is counter-clockwise from its component side, so the Seed faces the rear, away from the main board")
ck.check("B.breakout_pin1_square_pads", sorted(n for n, v in u5fp.items() if v[2] == "RECT")
         == sorted(["1", "40", "J1-1", "J3-1", "J4-1", "J5-1"]),
         f"breakout Gerbers: square pads on Seed pins 1 and 40 and on each J header's pin 1; footprint square pads "
         f"{sorted(n for n, v in u5fp.items() if v[2] == 'RECT')}")


# ----------------------------------------------------------------------------------------------------------
# C  symbols and footprints of the routed master
def sym_names(board, ref):
    return {num: v[0] for num, v in R.symbol_pins(symbol_of(board, ref)).items()}


def names_vs(ds, got, alias=None):
    alias = alias or {}
    return {num: (got.get(num), name) for name, num in ds.items() if alias.get(got.get(num), got.get(num)) != name}


tl = sym_names("main", "U6")
tl_sig = {k: v for k, v in TL074_DS.items() if not k.startswith("VCC")}
tl_alias = {f"OUT{s}": f"{s}OUT" for s in "1234"}
tl_alias.update({f"IN{s}{p}": f"{s}IN{p}" for s in "1234" for p in "+-"})
ck.check("C.symbol_TL074_signal_pins", not names_vs(tl_sig, tl, tl_alias),
         f"routed TL074ACN symbol, (symbol name, datasheet name) where they differ: {names_vs(tl_sig, tl, tl_alias)}")
ck.check("C.symbol_TL074_supply_names", tl.get("4") in ("VCC", "VCC+", "V+") and tl.get("11") in ("VCC-", "V-", "VEE"),
         f"TI: pin 4 VCC+, pin 11 VCC-; the routed symbol names pin 4 '{tl.get('4')}' and pin 11 '{tl.get('11')}' "
         f"(pin 11 sits on -12V in this circuit)")
ck.check("C.symbol_74HC595", not names_vs(HC595_DS, sym_names("main", "U3")),
         f"(symbol, datasheet) differences: {names_vs(HC595_DS, sym_names('main', 'U3'))}")
for u in ("U1", "U2"):
    d = names_vs(HC165_DS, sym_names("face", u))
    ck.check(f"C.symbol_74HC165.{u}", not d, f"(symbol, datasheet) differences: {d} (CE is active low: /CE)")
ck.check("C.symbol_H11L1", not names_vs(H11L1_DS, sym_names("main", "U7")),
         f"differences {names_vs(H11L1_DS, sym_names('main', 'U7'))}")
ck.check("C.symbol_2N3904", not names_vs(Q2N3904_DS, sym_names("main", "Q1")),
         f"differences {names_vs(Q2N3904_DS, sym_names('main', 'Q1'))}")
for ref in ("D1", "D2"):
    s = sym_names("main", ref)
    ck.check(f"C.symbol_diode_pins.{ref}", s.get("1") in ("C", "K") and s.get("2") == "A",
             f"circuit.py: pin 1 = cathode; symbol pin 1 '{s.get('1')}', pin 2 '{s.get('2')}'")
ck.check("C.symbol_SIP9_common", sym_names("face", "RN1").get(SIP_BUSSED_COMMON) == "COM",
         f"pin 1 named {sym_names('face', 'RN1').get('1')}")
ck.check("C.symbol_PJ366ST", sym_names("face", "J5") == {"1": "S", "2": "R", "3": "T"},
         f"circuit.MIDI_JACK: 1 sleeve, 2 ring, 3 tip; symbol {sym_names('face', 'J5')}")
ck.check("C.symbol_button", sym_names("face", "SW1").get("5") == "LED A" and sym_names("face", "SW1").get("6") == "LED K",
         f"pin 5 LED anode, 6 cathode; symbol {sym_names('face', 'SW1')}")
enc_s = sym_names("face", "ENC1")
ck.check("C.symbol_EC11", enc_s.get("C") == "C" and {enc_s.get("A"), enc_s.get("B")} == {"A", "B"}
         and enc_s.get("S1") == enc_s.get("S2") == "SW", f"symbol {enc_s}")
seed_s = sym_names("main", "U5")
seed_sym_bad = {k: (seed_s.get(k), v[0]) for k, v in circuit.SEED.items() if seed_s.get(k) != v[0]}
ck.check("C.symbol_Seed_names", not seed_sym_bad, f"routed Seed symbol names against circuit.SEED: {seed_sym_bad}")


def dip_ccw(pads, n):
    """Pin 1 .. n/2 along one row left to right, n/2+1 .. n back along the other (counter-clockwise, top view)."""
    half = n // 2
    row1 = [pads[str(i)] for i in range(1, half + 1)]
    row2 = [pads[str(n + 1 - i)] for i in range(1, half + 1)]
    ok = all(abs(a[1] - row1[0][1]) < 0.01 for a in row1) and all(abs(b[1] - row2[0][1]) < 0.01 for b in row2)
    ok = ok and all(abs(row1[i][0] - row2[i][0]) < 0.01 for i in range(half))
    ok = ok and all(abs(row1[i + 1][0] - row1[i][0] - 2.54) < 0.01 for i in range(half - 1))
    ok = ok and row2[0][1] > row1[0][1] and abs(row2[0][1] - row1[0][1] - 7.62) < 0.01
    return ok


for board, ref, n in (("main", "U6", 14), ("main", "U7", 6), ("main", "U3", 16), ("face", "U1", 16), ("face", "U2", 16)):
    doc = fp_doc(board, ref)
    pads = fp_pads(doc)
    ok = len(pads) == n and dip_ccw(pads, n)
    ck.check(f"C.DIP{n}_numbering.{ref}", ok,
             f"{harness.meta(doc).get('title')}: pin 1 bottom-left, 1..{n // 2} left to right, {n // 2 + 1}..{n} back "
             f"along the row 7.62 mm above (counter-clockwise from the top, JEDEC)")
    segs, circles = silk(doc)
    p1 = pads["1"]
    dot = [c for c in circles if math.hypot(c[0] - p1[0], c[1] - p1[1]) < 2.5 and c[2] < 0.6]
    square = [k for k, v in pads.items() if v[2] == "RECT"]
    ck.check(f"C.DIP_pin1_marked.{ref}", (square == ["1"] or not square) and (dot or square == ["1"]),
             f"pin 1 marked: square pads {square}, silk dot within 2.5 mm of pad 1 "
             f"{[(round(c[0], 2), round(c[1], 2)) for c in dot]}")

# TO-92: pads 1 2 3 on a line, 2.54 apart, the flat side's chord on the side that makes 1-2-3 run left to
# right seen from the flat face (onsemi CASE 29)
to92 = fp_doc("main", "Q1")
tp = fp_pads(to92)
segs, circles = silk(to92)
flat = [s for s in segs if abs(s[1] - s[3]) < 0.01 and abs(s[0] - s[2]) > 2.0]
ok_row = abs(tp["2"][0] - tp["1"][0] - 2.54) < 0.01 and abs(tp["3"][0] - tp["2"][0] - 2.54) < 0.01 and \
    abs(tp["1"][1]) < 0.01 and abs(tp["3"][1]) < 0.01
flat_side = (-1 if flat[0][1] < 0 else 1) if len(flat) == 1 else 0
# a viewer at the flat face looks towards the round side; with the flat at -y he looks along +y and has -x on his left
left_to_right = (tp["1"][0] < tp["3"][0]) if flat_side == -1 else (tp["1"][0] > tp["3"][0])
ck.check("C.TO92_flat_and_order.Q1", ok_row and flat_side != 0 and left_to_right,
         f"pads 1/2/3 at x {[round(tp[k][0], 2) for k in '123']}, flat chord at y {flat[0][1] if flat else None:.2f} "
         f"mm: seen from the flat face, 1-2-3 must run left to right (E B C)")
q1 = R.main.parts["Q1"]
ck.check("C.TO92_on_top_layer.Q1", not q1["bottom"], f"Q1 on the {'bottom' if q1['bottom'] else 'top'} layer "
                                                     f"(a mirrored TO-92 would swap E and C)")


def band_pad(doc):
    """The pad on the cathode-band side: a silk line across the body strictly between the body's two ends."""
    pads = fp_pads(doc)
    (n1, p1), (n2, p2) = sorted(pads.items())
    segs, _ = silk(doc)
    across = [s for s in segs if abs(s[0] - s[2]) < 0.01 and abs(s[1] - s[3]) > 1.0]
    xs = sorted({round(s[0], 2) for s in across})
    ends = [x for x in xs if x > 0 and any(abs(x + y) < 0.05 for y in xs)]
    end = max(ends) if ends else 0
    inner = [x for x in xs if abs(x) < end - 0.05 and not any(abs(x + y) < 0.05 for y in xs)]
    if len(inner) != 1:
        return None, xs
    return (n1 if abs(inner[0] - p1[0]) < abs(inner[0] - p2[0]) else n2), xs


for ref in ("D1", "D2"):
    doc = fp_doc("main", ref)
    band, xs = band_pad(doc)
    ck.check(f"C.diode_band_pad.{ref}", band == "1",
             f"{harness.meta(doc).get('title')}: silk band nearest pad {band} (silk lines across the body at x {xs}); "
             f"circuit.py and the symbol put the cathode on pin 1, so the band must sit at pad 1")
sip = fp_doc("face", "RN1")
sp = fp_pads(sip)
segs, _ = silk(sip)
bars = [s for s in segs if abs(s[0] - s[2]) < 0.01 and sp["1"][0] < s[0] < sp["2"][0]]
ck.check("C.SIP9_pin1_marked", [k for k, v in sp.items() if v[2] == "RECT"] == ["1"] and len(bars) == 1
         and all(abs(sp[str(i + 1)][0] - sp[str(i)][0] - 2.54) < 0.01 for i in range(1, 9)),
         f"pad 1 square, a silk bar between pads 1 and 2 (the body's pin-1 end), pads 2.54 mm apart in order")
jk = fp_pads(fp_doc("face", "J1"))
d12 = math.hypot(jk["2"][0] - jk["1"][0], jk["2"][1] - jk["1"][1])
d13 = math.hypot(jk["3"][0] - jk["1"][0], jk["3"][1] - jk["1"][1])
ck.check("C.jack_pads_vs_PJ398SM", abs(d12 - JACK_KICAD["TN"]) < 0.05 and abs(d13 - JACK_KICAD["T"]) < 0.05,
         f"PJ398SM: S->TN {JACK_KICAD['TN']} mm, S->T {JACK_KICAD['T']} mm; footprint pad 1->2 {d12:.2f}, 1->3 "
         f"{d13:.2f} (so 1 = S, 2 = TN, 3 = T)")
same_jack = sorted({R.face.parts[ref]["fp"] for ref, *_ in circuit.JACKS if ref != "J5"})
ck.check("C.mono_jacks_one_footprint", len(same_jack) == 1, f"footprints {same_jack}")
pj = fp_pads(fp_doc("face", "J5"))
pj_d = {k: round(math.hypot(v[0] - pj["1"][0], v[1] - pj["1"][1]), 2) for k, v in pj.items() if k != "1"}
pj_line = all(abs(v[0] - pj["1"][0]) < 0.01 for v in pj.values()) and     (pj["2"][1] - pj["1"][1]) * (pj["3"][1] - pj["1"][1]) > 0
pj_bad = {k: (pj_d.get(k), want) for k, want in PJ366ST_DS_DIST.items()
          if pj_d.get(k) is None or abs(pj_d[k] - want) > 0.05}
ck.check("C.PJ366ST_pads_vs_datasheet", not pj_bad and pj_line and len(pj) == 3,
         f"PJ366ST pins relative to the sleeve (constants, {PJ366ST_SOURCE}); footprint has {sorted(pj)}; "
         f"(footprint, datasheet) differences {pj_bad}")
ef = fp_pads(fp_doc("face", "ENC1"))
enc_bad = {k: (round(ef[k][0], 2), round(ef[k][1], 2), (x, -y)) for k, (x, y) in EC11_KICAD.items()
           if math.hypot(ef[k][0] - x, ef[k][1] + y) > 0.01}
ck.check("C.EC11_footprint_vs_KiCad", not enc_bad,
         f"KiCad EC11E (y down) mirrored into EasyEDA's y up: C between A and B on 2.5 mm, switch pins 5.0 mm apart "
         f"7.0 mm the other side of the shaft, tabs on the shaft line; differences (got x, y, want) {enc_bad}")
bt = fp_pads(fp_doc("face", "SW1"))
ck.check("C.button_footprint_vs_Thonk", all(abs(bt[n][0] - x) < 0.01 and abs(bt[n][1] - y) < 0.01
                                           for n, (x, y) in BUTTON_XY.items()),
         f"Thonk low-profile LED button (parts.md) {BUTTON_XY}; footprint "
         f"{ {n: (round(v[0], 2), round(v[1], 2)) for n, v in bt.items()} }")
hdr_fp_bad = []
for board, ref in [("main", r) for r, _, _ in circuit.HEADERS] + [("face", circuit.fb_ref(r)) for r, _, _ in circuit.HEADERS] \
        + [("face", "CN1")]:
    pads = fp_pads(fp_doc(board, ref))
    n = len(pads)
    if [k for k, v in pads.items() if v[2] == "RECT"] != ["1"] or not all(
            abs(pads[str(i + 1)][0] - pads[str(i)][0] - 2.54) < 0.01 and abs(pads[str(i + 1)][1] - pads[str(i)][1]) < 0.01
            for i in range(1, n)):
        hdr_fp_bad.append(ref)
ck.check("C.header_footprints_in_order", not hdr_fp_bad, f"1xN headers: pad 1 square, 2..N in order 2.54 mm apart; bad "
                                                         f"{hdr_fp_bad}")


# ----------------------------------------------------------------------------------------------------------
# D  the routed master against circuit.py: parts, every pad's net, PAD_NET records, open pads
def raw_padnets(board):
    """[(component id, pad num, pad id, net)] from the PCB doc's PAD_NET records."""
    out = []
    for h, p in R.pcb_docs[board]["recs"]:
        if h["type"] == "PAD_NET":
            _, cid, num, padid = harness.rid(h)
            out.append((cid, str(num), padid, p.get("padNet")))
    return out


OPEN = {}
for b, parts in (("main", MB), ("face", FB)):
    want = {p.ref: p for p in parts}
    got = BOARDS[b].parts
    missing, extra = sorted(set(want) - set(got)), sorted(set(got) - set(want))
    ck.check(f"D.designators_complete.{b}", not missing and not extra,
             f"{len(want)} parts in circuit.py, {len(got)} on the routed PCB; missing {missing}, extra {extra}")
    pad_bad, no_pad = [], []
    OPEN[b] = {}
    for ref, part in want.items():
        pl = got.get(ref)
        if not pl:
            continue
        pads = set(pl["pads"])
        if set(part.nets) - pads:
            no_pad.append((ref, sorted(set(part.nets) - pads)))
        for num in sorted(pads | set(pl["nets"])):
            if pl["nets"].get(num) != part.nets.get(num):
                pad_bad.append((ref, num, "routed", pl["nets"].get(num), "circuit", part.nets.get(num)))
        OPEN[b][ref] = sorted(n for n in pads if not pl["nets"].get(n))
    ck.check(f"D.every_pad_net.{b}", not pad_bad,
             f"every pad of every part against circuit.py; {len(pad_bad)} differences: {pad_bad[:20]}")
    ck.check(f"D.circuit_pins_have_pads.{b}", not no_pad, f"circuit.py pins with no footprint pad: {no_pad}")
    cid_ref = {pl["cid"]: ref for ref, pl in got.items()}
    pn_bad = []
    for cid, num, padid, net in raw_padnets(b):
        ref = cid_ref.get(cid)
        if ref is None:
            pn_bad.append(("no component", cid, num))
            continue
        pads = fp_pads(fp_doc(b, ref))
        if num not in pads or pads[num][3] != padid:
            pn_bad.append((ref, num, padid, "pad ids", {k: v[3] for k, v in pads.items()}.get(num)))
        if net and net not in NETS[b]:
            pn_bad.append((ref, num, "net not in circuit.py", net))
    ck.check(f"D.padnet_records_name_real_pads.{b}", not pn_bad,
             f"every PAD_NET names its component, a pad number of the footprint and that pad's record id, and a "
             f"circuit.py net: bad {pn_bad[:12]}")
    nets_rec = {p.get("net") or (harness.rid(h)[1] if isinstance(harness.rid(h), list) else None)
                for h, p in R.pcb_docs[b]["recs"] if h["type"] == "NET"}
    routed_nets = {n for pl in got.values() for n in pl["nets"].values()}
    ck.check(f"D.no_foreign_nets.{b}", routed_nets == set(NETS[b]),
             f"routed pad nets minus circuit: {sorted(routed_nets - set(NETS[b]))}, circuit minus routed: "
             f"{sorted(set(NETS[b]) - routed_nets)}")
    ck.check(f"D.net_records.{b}", set(NETS[b]) <= nets_rec,
             f"every circuit net has a NET record in the PCB doc; missing {sorted(set(NETS[b]) - nets_rec)}")


# design.md "What EasyEDA's DRC will still say": the pins left open
def md_section(text, start, stop="\n## "):
    i = text.index(start)
    j = text.find(stop, i + len(start))
    return text[i:j if j > 0 else None]


DESIGN = harness.text("docs", "design.md")


def md_table(text, after):
    """Rows (lists of cells) of the first markdown table after the first line containing `after`."""
    lines = text[text.index(after):].splitlines()
    rows, started = [], False
    for ln in lines[1:]:
        if ln.startswith("|"):
            started = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif started:
            break
    return rows


def seed_pins_named(words):
    """Seed pin numbers from design.md's D1–D6, D9, D19, D21–D25, D28, VIN, 16–19 style list."""
    by_d = {}
    for pin, (name, net) in circuit.SEED.items():
        for part in name.split("/"):
            by_d[part] = pin
    out = set()
    for tok in re.split(r",\s*|\s+and\s+", words):
        tok = tok.strip().replace("–", "-")
        m = re.match(r"^D(\d+)-D(\d+)$", tok)
        if m:
            out |= {by_d[f"D{k}"] for k in range(int(m.group(1)), int(m.group(2)) + 1)}
            continue
        m = re.search(r"(\d+)-(\d+)", tok)
        if m and "pins" in tok:
            out |= {str(k) for k in range(int(m.group(1)), int(m.group(2)) + 1)}
            continue
        if tok in by_d:
            out.add(by_d[tok])
    return out


drc = {r[0]: r[1] for r in md_table(DESIGN, "What EasyEDA's DRC will still say")}
want_open = collections.defaultdict(set)
for where, what in drc.items():
    if where.startswith("U5"):
        want_open[("main", "U5")] = seed_pins_named(what)
    elif where.startswith("U7"):
        want_open[("main", "U7")] = set(re.findall(r"pin (\d+)", what))
    elif where.startswith("U1, U2"):
        for u in ("U1", "U2"):
            want_open[("face", u)] = {HC165_DS["/Q7"]} if "/Q7" in what else set()
    elif where.startswith("U3"):
        want_open[("main", "U3")] = {HC595_DS[q] for q in ("QF", "QG", "QH")} | ({HC595_DS["QH'"]} if "QH'" in what else set())
    elif where == "J5":
        want_open[("face", "J5")] = {"1"} if "sleeve" in what else set()
    elif where.startswith("J2, J7"):
        for j in ("J2", "J7"):
            want_open[("face", j)] = {JACK_DS["TN"]} if "switch lug" in what else set()
got_open = {(b, ref): set(v) for b in OPEN for ref, v in OPEN[b].items() if v}
extra_open = {k: sorted(v - want_open.get(k, set())) for k, v in got_open.items() if v - want_open.get(k, set())}
missing_open = {k: sorted(v - got_open.get(k, set())) for k, v in want_open.items() if v - got_open.get(k, set())}
ck.check("D.open_pads_equal_design_md_list", not extra_open and not missing_open,
         f"design.md 'What EasyEDA's DRC will still say' against the routed pads without a net: open but not "
         f"listed {extra_open}; listed but tied {missing_open}")


# ----------------------------------------------------------------------------------------------------------
# E  connectivity of the routed copper
CONN = {}
for b in ("main", "face"):
    groups, contacts = BOARDS[b].connectivity()
    CONN[b] = (groups, contacts)
    split = {net: len(g) for net, g in groups.items() if len(g) > 1}
    small = []
    for net in split:
        pieces = sorted(groups[net].values(), key=len)
        for piece in pieces[:-1]:
            desc = []
            for k in sorted(piece, key=str):
                if k[0] == "island":
                    isl = BOARDS[b].islands[k[1]]
                    xs, ys = [q[0] for q in isl.outline], [q[1] for q in isl.outline]
                    desc.append(f"pour island on layer {isl.layer} at ({min(xs):.2f}..{max(xs):.2f}, "
                                f"{min(ys):.2f}..{max(ys):.2f})")
                else:
                    desc.append(str(k))
            small.append((net, desc[:4]))
    ck.check(f"E.every_net_one_piece.{b}", not split, f"nets in more than one copper piece: {split}; the smaller "
                                                       f"pieces: {small}")
    ck.check(f"E.no_other_net_contacts.{b}", not contacts, f"copper of two nets touching: {contacts[:10]}")
    copper_nets = set(groups)
    ck.check(f"E.copper_nets_equal_circuit.{b}", copper_nets == set(NETS[b]),
             f"nets with copper {len(copper_nets)}, circuit.py {len(NETS[b])}; only copper "
             f"{sorted(copper_nets - set(NETS[b]))}, only circuit {sorted(set(NETS[b]) - copper_nets)}")
groups, contacts = CONN["face"]
gd_touch = [c for c in contacts if {c[0], c[1]} == {"GND_F", "GND_D_F"}]
ck.check("E.GND_F_never_touches_GND_D_F", not gd_touch and "GND_F" in groups and "GND_D_F" in groups,
         f"design.md: the faceplate's two grounds meet only on the main board; contacts {gd_touch}")
# the grounds' header pins: on the faceplate each joins only its own ground, on the main board all are GND in one piece
gpins = [(ref, i + 1, b) for ref, _, pins in circuit.HEADERS for i, (a, b) in enumerate(pins) if a == "GND"]
mg, _ = CONN["main"]
gnd_piece = [k for root, keys in mg.get("GND", {}).items() for k in keys if k[0] == "pad"]
root_of = {k: root for root, keys in mg.get("GND", {}).items() for k in keys}
roots = {root_of.get(("pad", ref, str(i))) for ref, i, _ in gpins}
ck.check("E.grounds_join_on_main_GND", len(roots) == 1 and None not in roots,
         f"main-board pads of the faceplate grounds' header pins {[(r, i, b) for r, i, b in gpins]} in one GND piece: "
         f"{len(roots)} piece(s)")
fg, _ = CONN["face"]
face_keys = {net: {k for keys in fg.get(net, {}).values() for k in keys} for net in ("GND_F", "GND_D_F")}
gp_bad = [(circuit.fb_ref(ref), i, b) for ref, i, b in gpins if ("pad", circuit.fb_ref(ref), str(i)) not in face_keys.get(b, set())]
ck.check("E.faceplate_ground_pins_on_their_ground", not gp_bad,
         f"HF pins of GND_F (audio) and GND_D_F (logic) in their own ground's copper; bad {gp_bad}")


# ----------------------------------------------------------------------------------------------------------
# F  header stacking (both PCB docs are in the same frame, looking at the top layer)
stack_bad, net_bad, side_bad = [], [], []
for ref, kind, pins in circuit.HEADERS:
    m, f = R.main.parts[ref], R.face.parts[circuit.fb_ref(ref)]
    if not m["bottom"] or f["bottom"]:
        side_bad.append((ref, "main bottom", m["bottom"], circuit.fb_ref(ref), "face bottom", f["bottom"]))
    if set(m["pads"]) != set(f["pads"]) or len(m["pads"]) != len(pins):
        stack_bad.append((ref, "pad sets", sorted(m["pads"]), sorted(f["pads"])))
        continue
    for num, fp in f["pads"].items():
        mp = m["pads"][num]
        if math.hypot(fp.x - mp.x, fp.y - mp.y) > 0.01:
            stack_bad.append((ref, num, (round(mp.x, 2), round(mp.y, 2)), (round(fp.x, 2), round(fp.y, 2))))
        a, b = pins[int(num) - 1]
        if mp.net != a or fp.net != b:
            net_bad.append((ref, num, mp.net, fp.net, a, b))
ck.check("F.header_pads_stacked", not stack_bad, f"every HFn pad within 0.01 mm of its Hn pad: {stack_bad}")
ck.check("F.stacked_pads_carry_pairs", not net_bad, f"stacked pads carry circuit.HEADERS' (main, face) pair: {net_bad}")
ck.check("F.header_sides", not side_bad, f"male pins on the faceplate's top (rear), sockets on the main board's bottom "
                                         f"(front): {side_bad}")
# any other main-board pad under a faceplate header pin (a socket must face only its own pin)
allm = [(p.ref, p.num, p.x, p.y) for p in R.main.pads]
foreign = []
for ref, kind, pins in circuit.HEADERS:
    for num, fp in R.face.parts[circuit.fb_ref(ref)]["pads"].items():
        near = [(r, n) for r, n, x, y in allm if math.hypot(x - fp.x, y - fp.y) < 1.27 and r != ref]
        if near:
            foreign.append((circuit.fb_ref(ref), num, near))
ck.check("F.no_other_main_pad_under_a_pin", not foreign, f"main-board pads within 1.27 mm of a faceplate header pin "
                                                          f"that are not its socket: {foreign}")
hm = sorted((round(x, 2), round(y, 2), round(d, 2)) for x, y, d in R.main.holes)
hf = sorted((round(x, 2), round(y, 2), round(d, 2)) for x, y, d in R.face.holes)
ck.check("F.same_mounting_holes", hm == hf and len(hm) == len(circuit.HOLES_FRONT),
         f"main {hm}, faceplate {hf}, circuit.HOLES_FRONT has {len(circuit.HOLES_FRONT)}")
# every header has a ground pin of its own, so each group of signals has its return beside it
no_gnd = [r for r, _, p in circuit.HEADERS if not any(a == "GND" for a, _ in p)]
far = {}
for r in no_gnd:
    for num, pad in R.face.parts[circuit.fb_ref(r)]["pads"].items():
        gnds = [q for q in R.face.pads if q.ref.startswith("HF") and q.net in ("GND_F", "GND_D_F")]
        far[f"{circuit.fb_ref(r)}.{num} {pad.net}"] = round(min(math.hypot(q.x - pad.x, q.y - pad.y) for q in gnds), 1)
ck.check("F.every_header_has_ground", not no_gnd,
         f"headers without a GND pin: {no_gnd}; their signals' nearest board-to-board ground pin (mm): {far}")
W = R.face.outline[2]
front = sorted((round(W - x, 1), round(y, 1)) for x, y, d in R.face.holes)
ck.check("F.holes_at_HOLES_FRONT", front == sorted((round(x, 1), round(y, 1)) for x, y in circuit.HOLES_FRONT),
         f"front view (x = W - x): {front}, circuit.HOLES_FRONT {sorted(circuit.HOLES_FRONT)}")
ck.check("F.same_outline", all(abs(a - b) < 0.01 for a, b in zip(R.main.outline, R.face.outline)),
         f"main {R.main.outline}, faceplate {R.face.outline}")


# ----------------------------------------------------------------------------------------------------------
# G  schematic pages of the routed and the generated exports against circuit.py
def _on_seg(p, a, b, tol=0.01):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    if min(x1, x2) - tol <= x <= max(x1, x2) + tol and min(y1, y2) - tol <= y <= max(y1, y2) + tol:
        return abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) <= tol * max(1, math.hypot(x2 - x1, y2 - y1))
    return False


def _xf(cand, comp, px, py):
    order, sigma, phi = cand
    m = -1 if comp["isMirror"] else 1
    a = math.radians(sigma * (comp["rotation"] or 0))
    if order == "mirror-first":
        px = m * px
    x, y = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
    if order == "rotate-first":
        x = m * x
    return round(comp["x"] + x, 3), round(comp["y"] + phi * y, 3)


# every pin-placing convention is tried and the one that lands most pins on named wires wins (the stereo mixer's
# approach); two-pin R / C are then compared as unordered pairs, since a 180-degree turn cannot be told apart
CANDS = [(o, s, f) for o in ("mirror-first", "rotate-first") for s in (-1, 1) for f in (1, -1)]
NONPOLAR = ("R", "C")


def sym_pins(docs, uid, cache={}):
    key = (id(docs), uid)
    if key not in cache:
        pins, out = {}, {}
        for h, p in docs[uid]["recs"]:
            if h["type"] == "PIN" and p:
                pins[h["id"]] = {"x": p["x"], "y": p["y"], "part": p.get("partId")}
        for h, p in docs[uid]["recs"]:
            if h["type"] == "ATTR" and p and p.get("parentId") in pins:
                pins[p["parentId"]][p["key"]] = p["value"]
        for q in pins.values():
            out[q.get("Pin Number")] = (q.get("Pin Name"), q["x"], q["y"], q["part"])
        cache[key] = out
    return cache[key]


def schematic(path):
    """{board title: {page title: ({ref: {pin: net or None}}, stats)}} from the SCH_PAGE docs."""
    docs = harness.read_export(path)
    boards = {u: harness.meta(d).get("title") for u, d in docs.items() if d["docType"] == "BOARD"}
    sch_board = {u: boards.get(harness.meta(d).get("board")) for u, d in docs.items() if d["docType"] == "SCH"}
    pages = collections.defaultdict(dict)
    for u, d in docs.items():
        if d["docType"] == "SCH_PAGE":
            pages[sch_board.get(harness.meta(d).get("schematic"))][harness.meta(d).get("title")] = d
    result = {}
    for board, bpages in pages.items():
        page_data = []
        for title, d in bpages.items():
            comps = {h["id"]: p for h, p in d["recs"] if h["type"] == "COMPONENT"}
            attrs = collections.defaultdict(dict)
            for h, p in d["recs"]:
                if h["type"] == "ATTR" and p:
                    attrs[p.get("parentId")][p["key"]] = p["value"]
            wires = {h["id"]: [] for h, p in d["recs"] if h["type"] == "WIRE"}
            for h, p in d["recs"]:
                if h["type"] == "LINE" and p and p.get("lineGroup") in wires:
                    wires[p["lineGroup"]].append(((p["startX"], p["startY"]), (p["endX"], p["endY"])))
            named = {w: attrs[w].get("NET") for w in wires if attrs[w].get("NET")}
            page_data.append((title, comps, attrs, wires, named))
        best = None
        for cand in CANDS:
            score = 0
            for title, comps, attrs, wires, named in page_data:
                ptset = {(round(x, 3), round(y, 3)) for w in named for seg in wires[w] for x, y in seg}
                for cid, comp in comps.items():
                    sym = attrs[cid].get("Symbol")
                    if sym not in docs or "Designator" not in attrs[cid]:
                        continue
                    for num, (name, px, py, part) in sym_pins(docs, sym).items():
                        if part and part != comp["partId"]:
                            continue
                        score += _xf(cand, comp, px, py) in ptset
            if best is None or score > best[0]:
                best = (score, cand)
        cand = best[1]
        out = {}
        for title, comps, attrs, wires, named in page_data:
            pins_of, conflicts = collections.defaultdict(dict), []
            segs = [(w, s) for w in named for s in wires[w]]
            flag_pts = []
            for cid, comp in comps.items():
                a = attrs[cid]
                if "Designator" in a or not a.get("Name") or a.get("Symbol") not in docs:
                    continue
                for num, (name, px, py, part) in sym_pins(docs, a["Symbol"]).items():
                    flag_pts.append((_xf(cand, comp, px, py), a["Name"]))
            for cid, comp in comps.items():
                a = attrs[cid]
                ref, sym = a.get("Designator"), a.get("Symbol")
                if not ref or sym not in docs:
                    continue
                for num, (name, px, py, part) in sym_pins(docs, sym).items():
                    if part and part != comp["partId"]:
                        continue
                    p = _xf(cand, comp, px, py)
                    nets = {named[w] for w, s in segs if _on_seg(p, *s)}
                    nets |= {n for q, n in flag_pts if abs(q[0] - p[0]) < 0.01 and abs(q[1] - p[1]) < 0.01}
                    if len(nets) > 1:
                        conflicts.append((ref, num, sorted(nets)))
                    net = next(iter(nets)) if len(nets) == 1 else None
                    if pins_of[ref].get(num) is None:
                        pins_of[ref][num] = net
            out[title] = (pins_of, {"transform": cand, "score": best[0], "conflicts": conflicts})
        result[board] = out
    return result


# design.md's page table: which parts each page holds
PAGE_WANT = {
    "Main board": {p.ref for p in MB},
    "Faceplate 1": {p.ref for p in FB if p.kind in ("JACK", "JACK_TRS", "ENC", "SWLED")},
    "Faceplate 2": {"U1", "U2", "RN1", "RN2", "CN1", "C1", "C2", "C4"} | {circuit.fb_ref(r) for r, _, _ in circuit.HEADERS},
}
page_rows = {r[0]: r[1] for r in md_table(DESIGN, "| Page | Holds |")}
ck.check("G.design_md_page_table", set(page_rows) == {"Main board", "Faceplate 1", "Faceplate 2", "Panel"},
         f"design.md lists the pages {sorted(page_rows)}")
for label, path in (("routed", harness.ROUTED), ("generated", harness.GENERATED)):
    res = schematic(path)
    for board, parts in (("SideFXy Main", MB), ("SideFXy Faceplate", FB)):
        if board not in res:
            ck.check(f"G.{label}.{board}.pages_present", False, f"no schematic pages for {board}")
            continue
        merged, conflicts, stats = {}, [], None
        for title, (pins_of, st) in res[board].items():
            stats = st
            conflicts += st["conflicts"]
            short = next((k for k in PAGE_WANT if title.startswith(k)), None)
            if short:
                got_refs = set(pins_of)
                ck.check(f"G.{label}.page_parts.{short}", got_refs == PAGE_WANT[short],
                         f"design.md: '{short}' holds {page_rows.get(short)}; page '{title}' has extra "
                         f"{sorted(got_refs - PAGE_WANT[short])}, missing {sorted(PAGE_WANT[short] - got_refs)}")
            for ref, pins in pins_of.items():
                if ref in merged:
                    conflicts.append((ref, "on two pages"))
                merged[ref] = pins
        want = {p.ref: p for p in parts}
        ck.check(f"G.{label}.{board}.no_conflicting_labels", not conflicts,
                 f"pins touching two differently named nets, or parts on two pages: {conflicts[:10]}")
        diffs, swapped = [], []
        for ref, p in want.items():
            got = merged.get(ref, {})
            if p.kind in NONPOLAR and len(p.nets) == 2 and sorted(map(str, got.values())) == sorted(p.nets.values()) \
                    and got != p.nets:
                swapped.append(ref)
                continue
            for num in sorted(set(p.nets) | {n for n, v in got.items() if v}, key=str):
                if got.get(num) != p.nets.get(num):
                    diffs.append((ref, num, "page", got.get(num), "circuit", p.nets.get(num)))
        ck.check(f"G.{label}.{board}.pin_nets", not diffs and set(merged) == set(want),
                 f"transform {stats['transform']}, {stats['score']} pins on named wires; parts missing "
                 f"{sorted(set(want) - set(merged))}; {len(diffs)} pins differ from circuit.py: {diffs[:12]}")
        polar = [r for r in swapped if want[r].kind not in NONPOLAR]
        ck.check(f"G.{label}.{board}.polar_parts_unambiguous", not polar,
                 f"{len(swapped)} R / C read with pins 1 / 2 the other way round (harmless); polar parts: {polar}")


# ----------------------------------------------------------------------------------------------------------
# H  design.md's tables and the routing audit's "Clean" claims against circuit.py and the routed boards
ALL = {p.ref: p for p in MB + FB}
# Seed pin map
seed_tab = md_table(DESIGN, "### Daisy Seed pin map")
sm_bad = []
for pins_cell, lib, net_cell, use in seed_tab[1:]:
    pins = []
    for tok in re.split(r",\s*", pins_cell):
        tok = tok.replace("–", "-")
        m = re.match(r"^(\d+)-(\d+)$", tok)
        pins += [str(k) for k in range(int(m.group(1)), int(m.group(2)) + 1)] if m else [tok]
    nets = [n.strip() for n in re.split(r",\s*", net_cell)]
    if net_cell.strip() in ("—", "-"):
        for pin in pins:
            if circuit.SEED[pin][1] is not None:
                sm_bad.append((pin, "free in design.md", circuit.SEED[pin][1]))
        continue
    if "ADC_CV1..ADC_CV4" in net_cell:
        nets = [f"ADC_CV{k}" for k in range(1, 5)]
    if len(nets) == 1:
        nets = nets * len(pins)
    for pin, net in zip(pins, nets):
        if circuit.SEED.get(pin, (None, None))[1] != net:
            sm_bad.append((pin, net, circuit.SEED.get(pin)))
    if len(nets) != len(pins):
        sm_bad.append((pins_cell, "pins / nets count", net_cell))
listed = set()
for row in seed_tab[1:]:
    for tok in re.split(r",\s*", row[0]):
        tok = tok.replace("–", "-")
        m = re.match(r"^(\d+)-(\d+)$", tok)
        listed |= {str(k) for k in range(int(m.group(1)), int(m.group(2)) + 1)} if m else {tok}
unlisted = sorted((p for p in circuit.SEED if p.isdigit() and p not in listed and p not in ("16", "17", "18", "19")), key=int)
ck.check("H.seed_pin_map_table", not sm_bad and not unlisted,
         f"design.md Daisy Seed pin map against circuit.SEED: {sm_bad}; Seed pins in no row (16-19 are the codec's): "
         f"{unlisted}")
lib_bad = []
for pins_cell, lib, net_cell, use in seed_tab[1:]:
    for d in re.findall(r"\bD\d+\b", lib.split("(")[0]):
        if not any(d in circuit.SEED[p][0].split("/") for p in circuit.SEED if p in listed):
            lib_bad.append(d)
ck.check("H.seed_pin_map_libdaisy_names", not lib_bad, f"libDaisy names in the table that circuit.SEED does not "
                                                       f"have on the listed pins: {lib_bad}")
spi_row = next(r for r in seed_tab if r[0].startswith("8, 9, 11"))
ck.check("H.seed_pin_map_SPI1_roles", "SPI1 NSS, SCK, MOSI" in spi_row[1]
         and [SEED_PERIPH_DS[d] for d in ("D7", "D8", "D10")] == ["SPI1 CS", "SPI1 SCK", "SPI1 MOSI"],
         f"design.md '{spi_row[1]}' against the datasheet: D7 SPI1 CS, D8 SCK, D10 MOSI")
# CV stage table
cv_tab = md_table(DESIGN, "| Input | Section |")
cv_bad = []
for row in cv_tab:
    k = int(row[0].split()[-1])
    name = f"CV{k}"
    s = dict(circuit.CV_CHANNELS)[name]
    if row[1] != "U6" + "ABCD"[s - 1]:
        cv_bad.append((name, "section", row[1], s))
    for col, a, b, kind in ((2, name, f"IN_{name}", "R"), (3, f"IN_{name}", f"OA_{name}", "R"),
                            (4, f"IN_{name}", f"OA_{name}", "C"), (5, f"OA_{name}", f"ADC_{name}", "R")):
        p = ALL.get(row[col])
        if not p or p.kind != kind or set(p.nets.values()) != {a, b}:
            cv_bad.append((name, row[col], p and p.nets, (a, b)))
    pin = next(p for p, (nm, n) in circuit.SEED.items() if n == f"ADC_{name}")
    if row[6] not in circuit.SEED[pin][0].split("/"):
        cv_bad.append((name, "ADC", row[6], circuit.SEED[pin][0]))
vals = {ALL[r].value for r in ("R10", "R11", "C10", "R12", "R22", "R23", "C14")}
ck.check("H.cv_stage_table", not cv_bad and len(cv_tab) == 4, f"design.md CV table against circuit.py: {cv_bad}")
# 2026-11-14: design.md's stage diagram and bias sentence are read (the check had 27k / 1n / 10k copied in)
_st = [re.search(p, DESIGN) for p in (r"jack tip ── (\w+) ──┬", r"├── (\w+) ─+┤", r"└── (\w+) ─+┘",
                                      r"──┬── (\w+) ── Seed ADC")]
_bm = re.search(r"\(R22 (\w+), R23 (\w+), C14 (\w+)", " ".join(DESIGN.split()))
doc_cv = tuple(x.group(1) if x else "?" for x in _st) + (_bm.groups() if _bm else ("?",) * 3)
ck.check("H.cv_stage_values_text", (ALL["R10"].value, ALL["R11"].value, ALL["C10"].value, ALL["R12"].value,
                                    ALL["R22"].value, ALL["R23"].value, ALL["C14"].value)
         == tuple(v.replace(" ", "") for v in doc_cv[:6]) + ((doc_cv[6] + "u").replace("uu", "u")[:2],),
         f"design.md: {doc_cv}; got "
         f"{[(r, ALL[r].value) for r in ('R10', 'R11', 'C10', 'R12', 'R22', 'R23', 'C14')]}")
dec = {ALL["C15"].nets["1"], ALL["C15"].nets["2"]}, {ALL["C16"].nets["1"], ALL["C16"].nets["2"]}
ck.check("H.U6_decoupling_text", dec == ({"+12V", "GND"}, {"GND", "-12V"}),
         f"design.md: C15 on +12 V, C16 on -12 V; got {dec}")
# jack table
jt = md_table(DESIGN, "| Jack | Tip | Switch lug |")
jt_bad = []
jacks = {ref: (label, tip, tn) for ref, label, tip, tn in circuit.JACKS}
for cell_j, cell_tip, cell_lug in jt:
    refs = re.findall(r"\bJ\d+\b", cell_j)
    tips = re.findall(r"\w+_F", cell_tip)
    if "CV1_F..CV4_F" in cell_tip:
        tips = [f"CV{k}_F" for k in range(1, 5)]
    lug = re.findall(r"\w+_F", cell_lug)
    for i, ref in enumerate(refs):
        if ref == "J5":
            n = PARTS["face"]["J5"].nets
            if not (n.get("3") == "MIDI_TIP_F" and n.get("2") == "MIDI_RING_F" and "1" not in n
                    and "sleeve" in cell_lug and "open" in cell_lug):
                jt_bad.append((ref, n, cell_tip, cell_lug))
            continue
        label, tip, tn = jacks[ref]
        want_tip = tips[i] if len(tips) == len(refs) else tips[0]
        want_lug = None if cell_lug.startswith("open") else lug[0]
        if tip != want_tip or tn != want_lug or label.split()[0] not in cell_j:
            jt_bad.append((ref, label, tip, tn, cell_j, want_tip, want_lug))
ck.check("H.jack_table", not jt_bad and sum(len(re.findall(r"\bJ\d+\b", r[0])) for r in jt) == len(circuit.JACKS),
         f"design.md jack table against circuit.JACKS / MIDI_JACK: {jt_bad}")
# the chain table
ct = {r[0].split()[0]: r[1] for r in md_table(DESIGN, "| Chip | D0..D7 |")}
want_u1 = [f"ENC{k}_{p}_F" for k in range(1, 5) for p in "AB"]
words = {"PITCH": "BTN_PITCH_F", "DELAY": "BTN_DELAY_F", "TEXTURE": "BTN_TEXTURE_F", "REVERB": "BTN_REVERB_F"}
u2_doc = [f"BTN_K{k}_F" for k in range(1, 5)] + [words[w] for w in re.findall(r"PITCH|DELAY|TEXTURE|REVERB", ct.get("U2", ""))]
u1_doc = [f"ENC{a}_{b}_F" for a, bs in re.findall(r"ENC(\d) ([AB](?:, [AB])*)", ct.get("U1", "")) for b in bs.split(", ")]
u3_doc = re.findall(r"PITCH|DELAY|TEXTURE|REVERB|SHIFT", ct.get("U3", ""))
ck.check("H.chain_table_U1", u1_doc == want_u1 == circuit.SR_INPUTS["U1"] and "K1–K4" in ct.get("U2", ""),
         f"design.md U1 D0..D7 {u1_doc}, circuit {circuit.SR_INPUTS['U1']}")
ck.check("H.chain_table_U2", u2_doc == circuit.SR_INPUTS["U2"], f"design.md U2 D0..D7 {u2_doc}, circuit "
                                                                  f"{circuit.SR_INPUTS['U2']}")
ck.check("H.chain_table_U3", u3_doc == [circuit.LED_WORD[r] for r in circuit.LED_ORDER],
         f"design.md QA..QE {u3_doc}, circuit LED_ORDER {[circuit.LED_WORD[r] for r in circuit.LED_ORDER]}")
ck.check("H.chain_text_U1_first", "U1 (read first, Q7 = SR_DIN)" in DESIGN and PARTS["face"]["U1"].nets[HC165_DS["Q7"]] ==
         "SR_DIN_F" and PARTS["face"]["U2"].nets[HC165_DS["Q7"]] == PARTS["face"]["U1"].nets[HC165_DS["DS"]],
         "design.md: U1's Q7 = SR_DIN, U2's Q7 into U1's DS, U2's DS to ground")
ck.check("H.chain_text_SR_LOAD_both", PARTS["face"]["U1"].nets[HC165_DS["/PL"]] == "SR_LOAD_F"
         and PARTS["main"]["U3"].nets[HC595_DS["RCLK"]] == "SR_LOAD"
         and PARTS["face"]["U1"].nets[HC165_DS["CP"]] == "SR_CLK_F" and PARTS["main"]["U3"].nets[HC595_DS["SRCLK"]] == "SR_CLK",
         "design.md: SR_LOAD to the 165s' /PL and the 595's RCLK, SR_CLK shared")
# header table
ht = [r for r in md_table(DESIGN, "| Header | Where") if not r[0].startswith("Header")]
ht_bad = []
for r in ht:
    ref = r[0].split()[0]
    n = int(re.search(r"\((\d+)\)", r[0]).group(1))
    pins = next(p for h, _, p in circuit.HEADERS if h == ref)
    doc = [c.strip() for c in r[2].split(",")]
    want = [a if a != "GND" else ("GND/" + b) for a, b in pins]
    if doc != want or n != len(pins):
        ht_bad.append((ref, n, doc, want))
ck.check("H.header_table", not ht_bad and len(ht) == len(circuit.HEADERS),
         f"design.md header table against circuit.HEADERS: {ht_bad}")
m = re.search(r"(\d+) pins in (\d+) headers", DESIGN)
ck.check("H.header_pin_count_text", bool(m) and (int(m.group(1)), int(m.group(2))) ==
         (sum(len(p) for _, _, p in circuit.HEADERS), len(circuit.HEADERS)),
         f"design.md '{m.group(0) if m else None}', circuit.HEADERS {sum(len(p) for _, _, p in circuit.HEADERS)} pins "
         f"in {len(circuit.HEADERS)}")
# H1 where design.md puts it: front view x 2.6, y 2.9-13.1, pins along y
h1 = R.main.parts["H1"]["pads"]
fx = sorted({round(W - p.x, 1) for p in h1.values()})
fy = sorted(round(p.y, 1) for p in h1.values())
ck.check("H.H1_position_text", fx == [2.6] and abs(fy[0] - 2.9) < 0.06 and abs(fy[-1] - 13.1) < 0.06,
         f"design.md: H1 / HF1 at front x 2.6, y 2.9-13.1; routed front x {fx}, y {fy}")
# the routing audit's Clean section and the fourth export's claims
AUDIT = harness.text("docs", "routing-audit-2026-11-01.md")
clean = md_section(AUDIT, "## Clean", "\n---")
m = re.search(r"Connectivity, main board\.\*\* (\d+) nets, each one piece", clean)
mg, mc = CONN["main"]
ck.check("H.audit_main_nets_one_piece", bool(m) and int(m.group(1)) == len(mg) == len(MBN)
         and all(len(g) == 1 for g in mg.values()) and not mc,
         f"audit: '{m.group(0) if m else None}'; routed: {len(mg)} nets, split "
         f"{[n for n, g in mg.items() if len(g) > 1]}, contacts {len(mc)}")
m = re.search(r"(\d+) of (\d+) nets are one piece", clean)
fg, fc = CONN["face"]
ck.check("H.audit_face_net_count", bool(m) and int(m.group(2)) == len(fg) == len(FBN),
         f"audit: '{m.group(0) if m else None}' (first export); routed faceplate {len(fg)} nets, circuit {len(FBN)}")
gf = fg.get("GND_F", {})
biggest = max(gf.values(), key=len) if gf else set()
gf_pads = {k for k in biggest if k[0] == "pad"}
want_gf = {("pad", ref, num) for ref, pl in R.face.parts.items() for num, net in pl["nets"].items() if net == "GND_F"}
ck.check("H.audit_GND_F_pads_one_piece", want_gf <= gf_pads and ("pad", "HF1", "3") in gf_pads
         and ("pad", "HF2", "6") in gf_pads,
         f"fourth export: 'Every GND_F pad, HF1.3 and HF2.6 are in one connected piece'; GND_F pads outside the main "
         f"piece: {sorted(want_gf - gf_pads)}")
ck.check("H.audit_netlist_matches", "Every pad net on both boards matches" in clean and
         all(ck_name not in ck.failed for ck_name in ("D.every_pad_net.main", "D.every_pad_net.face")),
         "audit: every pad net on both boards matches circuit.py (section D)")
ck.check("H.audit_headers_line_up", "H2, H3 and H4 line up pin for pin" in clean and "F.header_pads_stacked" not in ck.failed,
         "audit: the headers line up pin for pin (H1 since the second export; section F)")
gdf = [t for t in R.face.tracks if t["net"] == "GND_D_F"]
ck.check("H.audit_GND_D_F_tracks", "GND_D_F runs as 0.6 mm tracks and never touches GND_F" in clean and gdf
         and all(abs(t["w"] - 0.6) < 0.01 for t in gdf) and not [i for i in R.face.islands if i.net == "GND_D_F"],
         f"audit: GND_D_F as 0.6 mm tracks (no pour); widths {sorted({round(t['w'], 3) for t in gdf})}, GND_D_F pour "
         f"islands {len([i for i in R.face.islands if i.net == 'GND_D_F'])}")


# ----------------------------------------------------------------------------------------------------------
# I  MIDI TRS type A and the jack normalling
j5 = PARTS["face"]["J5"].nets
pj_names = sym_names("face", "J5")
tip_pin = next(k for k, v in pj_names.items() if v == "T")
ring_pin = next(k for k, v in pj_names.items() if v == "R")
ck.check("I.MIDI_jack_tip_ring", j5.get(tip_pin) == "MIDI_TIP_F" and j5.get(ring_pin) == "MIDI_RING_F",
         f"J5 tip (pin {tip_pin}) MIDI_TIP_F, ring (pin {ring_pin}) MIDI_RING_F; got {j5}")
h2 = dict(next(p for r, _, p in circuit.HEADERS if r == "H2"))
ck.check("I.MIDI_through_H2", h2.get("MIDI_TIP") == "MIDI_TIP_F" and h2.get("MIDI_RING") == "MIDI_RING_F",
         f"H2 carries MIDI_TIP / MIDI_RING to the main board: {h2}")
r26 = PARTS["main"]["R26"]
# CA-033 type A: ring = DIN 4 = current source (the sender's +V through its 220 R) -> into the opto's anode;
# tip = DIN 5 = current sink (the sender's UART through 220 R) <- from the opto's cathode
ring_to_anode = set(r26.nets.values()) == {"MIDI_RING", u7.get(H11L1_DS["A"])}
tip_to_cathode = u7.get(H11L1_DS["K"]) == "MIDI_TIP"
ck.check("I.TRS_type_A_ring_source_to_anode", ring_to_anode and TRS_A["ring"] == "DIN4_source",
         f"CA-033 type A: ring = DIN 4 (source) -> 220 R -> LED anode (H11L1 pin 1); R26 {r26.nets}, U7 pin 1 "
         f"{u7.get('1')}")
ck.check("I.TRS_type_A_tip_sink_to_cathode", tip_to_cathode and TRS_A["tip"] == "DIN5_sink",
         f"CA-033 type A: tip = DIN 5 (sink) <- LED cathode (H11L1 pin 2); U7 pin 2 {u7.get('2')}")
ck.check("I.MIDI_receiver_series_220R", harness.ohms(r26.value) == 220.0,
         f"MIDI 1.0 receiver: 220 R in series with the opto LED from DIN 4; R26 = {r26.value}")
ck.check("I.MIDI_shield_open", "1" not in j5 and pj_names.get("1") == "S",
         f"MIDI 1.0: the receiver leaves DIN 2 (shield) unconnected; J5 sleeve (pin 1) net {j5.get('1')}")
# the reverse diode: conducts only when the tip is above the opto anode, i.e. when the LED is reverse biased
d2a, d2k = PARTS["main"]["D2"].nets["2"], PARTS["main"]["D2"].nets["1"]
fwd = {"MIDI_RING": 5.0, "OPTO_A": 1.2 + 0.0, "MIDI_TIP": 0.0}           # LED lit: anode ~1.2 V above the tip
rev = {"MIDI_RING": 0.0, "OPTO_A": 0.0, "MIDI_TIP": 5.0}                  # a type-B cable: the tip driven high
ck.check("I.D2_off_when_LED_lit", fwd[d2a] - fwd[d2k] < 0.3,
         f"normal MIDI: D2 anode {d2a} {fwd[d2a]:+.1f} V, cathode {d2k} {fwd[d2k]:+.1f} V: must not steal the LED current")
ck.check("I.D2_clamps_reverse", rev[d2a] - rev[d2k] > 0.3,
         f"swapped tip / ring: D2 anode {d2a} {rev[d2a]:+.1f} V, cathode {d2k} {rev[d2k]:+.1f} V: must conduct and "
         f"hold the LED's reverse voltage at one diode drop")
# normalling
tn = {ref: t for ref, _, _, t in circuit.JACKS}
lab = {ref: label for ref, label, _, _ in circuit.JACKS}
ck.check("I.IN2_normalled_to_IN1", tn["J6"] == "IN1_F" and lab["J6"] == "IN 2" and
         dict((r, t) for r, _, t, _ in circuit.JACKS)["J1"] == "IN1_F",
         f"README / design.md: IN 2's switch lug on IN 1's tip (a mono source feeds both); J6 lug {tn['J6']}")
gnd_lugs = [ref for ref, label, _, t in circuit.JACKS if label.startswith(("IN 1", "CLOCK", "CV")) and t != "GND_F"]
ck.check("I.inputs_lugs_grounded", not gnd_lugs,
         f"IN 1, CLOCK and CV 1-4 read 0 V unpatched (switch lug to GND_F); not grounded: {gnd_lugs}")
out_lugs = [(ref, t) for ref, label, _, t in circuit.JACKS if label.startswith("OUT") and t is not None]
ck.check("I.outputs_lugs_open", not out_lugs, f"outputs leave the switch lug open; tied {out_lugs}")
# the routed J5 pads: the pad circuit.py calls ring must be the PJ366ST's ring contact by position
ck.check("I.PJ366ST_ring_pad_position", PJ366ST_DS_FUNC.get(ring_pin) == "ring" and PJ366ST_DS_FUNC.get(tip_pin) == "tip"
         and PJ366ST_DS_FUNC.get("1") == "sleeve",
         f"PJ366ST pin functions by position ({PJ366ST_SOURCE}): {PJ366ST_DS_FUNC}; circuit.py ring = pad {ring_pin}, "
         f"tip = pad {tip_pin}")

j5_row = next((r for r in jt if "J5" in r[0]), None)
ck.check("I.design_md_J5_has_no_lugs", j5_row is not None and "lug" not in j5_row[2] and len(pj) == 3,
         f"the PJ366ST has three pins (S, R, T) and no switch contacts ({PJ366ST_SOURCE}; circuit.py: 'no "
         f"switches'); design.md's jack table says '{j5_row[2] if j5_row else None}'")

# ----------------------------------------------------------------------------------------------------------
# D (cont.)  the generator's boards (copper_audit.generated_boards(), in memory) against the routed master
ca = harness.load("copper_audit")
fb_gen, mb_gen, _ex = ca.generated_boards()
for b, gen in (("main", mb_gen), ("face", fb_gen)):
    diffs = ca.compare(BOARDS[b], gen)
    ck.check(f"D.generator_matches_routed.{b}", not diffs,
             f"easyeda_export's {b} board against the routed one, pad for pad and net for net: {diffs[:10]}")

# ----------------------------------------------------------------------------------------------------------
# D (cont.)  the routed master's library parts against the generated project's, part by part, following each
# placed part's own references (its Footprint and Device ATTRs, the device's Symbol). EasyEDA keeps its own
# copy of a footprint, device or symbol whose uuid it already holds when the user imports a project, so an edit
# made in place under an old uuid comes back undone in the user's next export (2026-11-14: the EC11 slots, the
# PJ366ST pad, R11/R14/R17/R20 as 27k, C10-C13 as 1 nF, the 74HC165's /CE). Copper checks miss it: the tracks
# are right, the pads and EasyEDA's BOM are not.
GEN = harness.routed(harness.GENERATED)
DEV_KEYS = ("Manufacturer Part", "Value")          # which part, not the wording of its description
TOL = 0.02                                          # mil


def pad_rows(X, fp_uuid):
    rows = {}
    for h, p in X.fp_by_uuid[fp_uuid]["recs"]:
        if h["type"] == "PAD" and p:
            hole = p.get("hole") or {}
            rows[str(p["num"])] = (p["centerX"], p["centerY"], p["defaultPad"]["padType"], p["defaultPad"]["width"],
                                   p["defaultPad"]["height"], hole.get("holeType"), hole.get("width") or 0,
                                   hole.get("height") or 0, p.get("plated"), p["layerId"])
    return rows


def same_pad(a, b):
    """Two pad rows alike, numbers within TOL (mm values written to 4 places round either way in mil)."""
    if a is None or b is None:
        return a is b
    return all(abs(x - y) <= TOL if isinstance(x, float) or isinstance(y, float) else x == y for x, y in zip(a, b))


def show(row):
    return row and tuple(round(v, 2) if isinstance(v, float) else v for v in row)


for b in ("main", "face"):
    dev_bad, fp_bad, sym_bad = [], {}, {}
    for ref in sorted(GEN.board(b).parts):
        if ref not in BOARDS[b].parts:
            continue                                    # D.parts_* reports a missing part
        gd, rd = GEN.device(b, ref), R.device(b, ref)
        diff = {k: (rd.get(k), gd.get(k)) for k in DEV_KEYS if rd.get(k) != gd.get(k)}
        if diff:
            dev_bad.append((ref, diff))
        title = BOARDS[b].parts[ref]["fp"]
        gp = pad_rows(GEN, GEN.attrs(b, ref)["Footprint"])
        rp = pad_rows(R, R.attrs(b, ref)["Footprint"])
        pad_diff = {n: (show(rp.get(n)), show(gp.get(n))) for n in sorted(set(gp) | set(rp))
                    if not same_pad(rp.get(n), gp.get(n))}
        if pad_diff and title not in fp_bad:
            fp_bad[title] = pad_diff
        gs = {n: v[0] for n, v in GEN.symbol_pins(gd["Symbol"]).items()} if gd.get("Symbol") in GEN.docs else {}
        rs = {n: v[0] for n, v in R.symbol_pins(rd["Symbol"]).items()} if rd.get("Symbol") in R.docs else {}
        if gs != rs and gd.get("Manufacturer Part") not in sym_bad:
            sym_bad[gd.get("Manufacturer Part")] = {n: (rs.get(n), gs.get(n)) for n in sorted(set(gs) | set(rs))
                                                     if gs.get(n) != rs.get(n)}
    ck.check(f"D.library_devices.{b}", not dev_bad,
             f"each placed part's device ({', '.join(DEV_KEYS)}) in the routed master as in the generated project "
             f"(routed, generated): {dev_bad[:8]}")
    ck.check(f"D.library_footprints.{b}", not fp_bad,
             "each placed part's footprint pads (centre, shape, size, hole, plating; mil, within 0.02) in the routed "
             f"master as in the generated project (routed, generated): {dict(list(fp_bad.items())[:4])}")
    ck.check(f"D.library_symbols.{b}", not sym_bad,
             f"each placed part's symbol pin names in the routed master as in the generated project "
             f"(routed, generated): {dict(list(sym_bad.items())[:4])}")

ck.done()
