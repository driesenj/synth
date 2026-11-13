"""Power group: Side FXy's power entry (the breakout's J2, D2/D3, L1/L2 and the B2405S-1WR2 DC/DC), the
rails at the chips, the 5 V and 3V3D current budget, the current the module draws from the bus, ratings,
missing-rail faults, decoupling and the power tracks on the routed boards.

What it checks
  A. J2, the breakout's power header, traced from the breakout's Gerbers (the facts are in the constants
     below, with how they were found): 10 pins on a 2.54 mm grid, pin 1 (the square pad, "RED STRIPE"
     beside it) and every pin's net against the Doepfer A-100 10-pin bus; no shroud; the cable the BOM
     orders. The breakout's J1 / J3 / Seed / J4 / J5 pins mapped by one rigid transform onto U5's
     footprint pads in the routed main board: -12 V, +12 V, GND and VIN land on the right pads and nets.
  B. Reverse protection: D2 (+12 V) and D3 (-12 V) B5819W, orientation from the breakout's silk; the drop
     at the real current per rail (typ, worst bound); current, power and junction temperature; a reversed
     or shifted 10-pin plug on the unshrouded J2 (no forward path for the wrong polarity, reverse voltage
     against VRRM); L1 / L2 (MLZ1608A2R2WT000) against their saturation current.
  C. The rails at the chips: +-12 V after the diodes at the bus tolerance against the TL074's supply range
     (U6 and the breakout's two TL074CPWR) and U6's CV-stage swing; 3V3D against the 74HC / H11L1 ranges.
  D. The 5 V supply and the 3V3D / 3V3A loads: every 3V3D load (display, button LEDs, H11L1, R27, the 74HC
     chips, the pull-ups, R25) typ and max; design.md's display / LED / "about 60 mA" figures; the Seed's
     own share through its 3V3D buck; the DC/DC's output current against its 200 mA and 20 mA minimum; its
     input voltage (+12 - (-12) less two Schottky drops and L1 / L2) against 21.6 .. 26.4 V; its output at
     the low corner against the Seed's VIN minimum.
  E. The current the module draws from each bus rail (typ, max) and whether design.md or the README says.
  F. Ratings: capacitor voltages in the BOM; resistor powers at the worst case (R24, R26 with a 5 V MIDI
     source and with a +-12 V output patched into MIDI, R10..R21, R25, R27, R1..R5, R22 / R23); the H11L1's
     LED current in that mis-patch.
  G. Missing-rail faults: one rail absent (the DC/DC's input, U6's outputs into the unpowered Seed's ADC
     pins through 1k), a source driving an unpowered module, the Seed's USB powering the logic with the
     rack off.
  H. Decoupling on the routed boards: each IC's 100 n by track length to its supply pin, and the loop back
     to its GND pin by track (or both pads in the GND pour), C4 at CN1's VCC.
  I. Power tracks: the 0.6 mm POWER class on every power net (design.md's routing notes); the faceplate's
     current over H3's single 3V3D and GND_D_F contacts; the drop from the Seed's 3V3D to CN1.

Run from side-fx/hardware/tests:  python test_power.py
Read only: imports circuit.py and copper_audit.py through the harness, opens the routed export.
"""
import collections
import csv
import heapq
import itertools
import math
import os
import re

import numpy as np

import harness

ck = harness.Checks("power")
circuit = harness.load("circuit")

# ===================================================================== constants (sources, conditions)
# --- Doepfer A-100 bus. doepfer.de/a100_man/a100t_e.htm: "the -12V line is marked with a colored wire (typically
# red)", the 10-pin and 16-pin headers carry the same -12 V / GND / +12 V; the pin table there is an image. Pin
# pairs from Elby Designs' EuroSynth power page (elby-designs.com/webtek/documents/eurosynth/power_distribution.htm)
# and the Synthesizers.com Q163++ datasheet: 1-2 -12 V, 3-8 GND, 9-10 +12 V, 11-12 +5 V, 13-14 CV, 15-16 GATE. The
# 10-pin header is pins 1-10 (a 10-to-16 cable lands its +12 V on bus pins 9-10).
DOEPFER16 = {1: "-12V", 2: "-12V", **{n: "GND" for n in range(3, 9)}, 9: "+12V", 10: "+12V",
             11: "+5V", 12: "+5V", 13: "CV", 14: "CV", 15: "GATE", 16: "GATE"}
DOEPFER10 = {n: DOEPFER16[n] for n in range(1, 11)}
PITCH = 2.54                         # mm, IDC 0.1" grid
V_BUS = 12.0
# Bus tolerance: Doepfer publishes none (a100t_e.htm and the PSU3 pages give currents only). ASSUMED +-5 %: the
# guaranteed band of a 7812 / 7912 over line, load and temperature (LM7812C 11.4 .. 12.6 V, TI LM340/LM78xx
# datasheet, from memory: not re-read), which the classic linear supplies use; switching supplies are usually tighter.
BUS_TOL = 0.05

# --- The breakout (github.com/rob-scape/daisy-seed-breakout-boards, daisy-seed-dcdc-opamps; Gerbers EasyEDA v6.5.51,
# 2025-08-29, BOM of the same date). Traced for this group: the top and bottom copper rasterised at 0.03 mm (pads,
# tracks, the bottom pour with its clearances), 4-connected copper joined through every PTH / via of the drill
# files; diode orientation and legends read off the rendered silk. Breakout frame: mm, top (SMD) side view.
J2_HOLES = {1: (6.085, -14.054), 2: (8.625, -14.054), 3: (6.085, -11.514), 4: (8.625, -11.514), 5: (6.085, -8.974),
            6: (8.625, -8.974), 7: (6.085, -6.434), 8: (8.625, -6.434), 9: (6.085, -3.894), 10: (8.625, -3.894)}
J2_SQUARE_PAD = (6.085, -14.054)     # the only square (MACRO1 1.5748 x 1.5748) J2 pad on both copper layers
J2_TRACE = {1: "-12V", 2: "-12V", 3: "GND", 4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND", 9: "+12V", 10: "+12V"}
# how the rail names were assigned: pins 1-2 reach D3's pad at (9.98, -16.89), whose silk bar is on that side
# (cathode at J2), D3's other pad feeds the -12 V row (24.13 .. 29.21, -17.018: the bottom legend "J1" with "-"
# marks, C18 100 uF, L2 -> the DC/DC's square pin 1 = -Vin); pins 9-10 reach D2's pad at (10.62, -1.78), anode
# side (bar away from J2), D2 feeds the +12 V row (y -1.778, legend "J3" "+", C9 100 uF, L1 -> DC/DC pin 2 = +Vin);
# pins 3-8 are the GND pour with the DC/DC's 0V, J1-1 / J3-1 and Seed pins 20 / 40.
J2_PART = "Amphenol 67997-210HLF"    # breakout BOM line 4, LCSC C178292: 2x5 straight pin header, unshrouded (no key)
J2_LEGEND = "RED STRIPE"             # bottom silk, beside the pin 1-2 end; J2's outline is on the bottom silk
# the breakout pins Side FXy's main board takes (breakout frame) and what the trace found on them
BREAKOUT_PINS = {
    "J1-1": ((31.75, -17.018), "GND"), "J1-2": ((29.21, -17.018), "-12V"), "J1-3": ((26.67, -17.018), "-12V"),
    "J1-4": ((24.13, -17.018), "-12V"),
    "J3-1": ((31.75, -1.778), "GND"), "J3-2": ((29.21, -1.778), "+12V"), "J3-3": ((26.67, -1.778), "+12V"),
    "J3-4": ((24.13, -1.778), "+12V"),
    "20": ((36.83, -17.018), "GND"), "40": ((85.09, -1.778), "GND"),   # the only GND holes among the Seed's 40
    "39": ((82.55, -1.778), "VIN"),                                    # the DC/DC's +Vo (pin at y -5.588) lands here
    "1": ((85.09, -17.018), "signal"), "21": ((36.83, -1.778), "signal"),
    "J4-1": ((95.25, -1.778), "signal"), "J4-2": ((92.71, -1.778), "GND"), "J4-3": ((90.17, -1.778), "signal"),
    "J4-4": ((87.63, -1.778), "GND"), "J5-1": ((95.25, -17.018), "signal"), "J5-2": ((92.71, -17.018), "GND"),
    "J5-3": ((90.17, -17.018), "signal"), "J5-4": ((87.63, -17.018), "GND"),
}
N_TL074 = 3                          # U6 here; U2 / U5 TL074CPWR (TSSOP) on the breakout (its BOM)

# --- B5819W (the breakout's D2 / D3): JCET (CJ) B5817W-B5819W datasheet (D, Mar 2015; LCSC C8598), 25 C:
# VRRM = VRWM = VR 40 V, VR(RMS) 28 V, IO 1 A, IFSM 9 A (8.3 ms), IFRM 1.5 A, Pd 500 mW, RthJA 200 K/W, TJ 125 C;
# VF max 0.6 V at 1 A, 0.9 V at 3 A; IR max 1 mA at 40 V. No VF is specified below 1 A; the curve starts at 0.1 A.
D_VRRM, D_IO, D_PD, D_RTH, D_TJ = 40.0, 1.0, 0.5, 200.0, 125.0
# Typical VF below 0.1 A: a 1N5819-class die, ~0.30 V at 0.1 A and ~60 mV per decade below it (onsemi 1N5817/D
# typical forward curve, 25 C, read off a log plot: approximate). Worst: the 0.6 V max at 1 A bounds VF at every lower
# current (VF rises with current), +50 mV for a cold case (0 C at about -2 mV/K): 0.65 V.
D_VF_WORST = 0.65


def vf_b5819w(i, worst=False):
    """B5819W forward voltage (V) at current i (A): typical from the 1N5819-class curve, or the worst-case bound."""
    if worst:
        return D_VF_WORST
    return 0.30 + 0.06 * math.log10(max(i, 1e-5) / 0.1)


# --- L1 / L2, TDK MLZ1608A2R2WT000 (breakout BOM; TDK MLZ1608 datasheet via LCSC C76797): 2.2 uH +-20 %, DC resistance
# 0.25 Ohm, Isat 130 mA (inductance down 50 %), Itemp 500 mA (+20 C). In series with the DC/DC's two input pins only.
L_DCR, L_ISAT = 0.25, 0.130

# --- Mornsun B_S-1WR2 datasheet 2024.09.09-B/4, B2405S-1WR2 rows (pdftotext -raw, page 2; notes page 4):
DCDC_VIN = (21.6, 24.0, 26.4)         # V, input range min / nominal / max
# (verify pass, re-read with pdftotext -table: selection guide "24 (21.6-26.4)", 5 V, "200/20" mA max / min, "76/80"
# % min / typ; input current at 24 V "57/17" typ, "--/30" max (full / no load). The range is nominal +-10 %: the part
# is "fixed input voltage and unregulated single output", no UVLO is given, so below 21.6 V it keeps running and
# its output follows the input down by up to 1.2 % per 1 % (linear regulation max). 21.6 V is the edge of the
# specified range, not a dropout.)
DCDC_SURGE = 30.0                     # V, surge 1 s max, 24 V input models
DCDC_IOUT_MAX, DCDC_IOUT_MIN = 0.200, 0.020   # A, output current max / min (min load = 10 % of rated, note 3)
DCDC_VOUT = 5.0
DCDC_EFF_MIN, DCDC_EFF_TYP = 0.76, 0.80       # full load, nominal input, 25 C (selection guide min / typ)
DCDC_IIN_FULL_TYP = 0.057             # A at 24 V in, full load, typ -> 1 W / (24 V x 57 mA) = 73 %
DCDC_EFF_WORST = min(DCDC_EFF_MIN, DCDC_VOUT * DCDC_IOUT_MAX / (DCDC_VIN[1] * DCDC_IIN_FULL_TYP))
DCDC_LINE_REG = 1.2                   # % output change per 1 % input change, max (5 V output)
DCDC_ACC = 0.05                       # ASSUMED +-5 % output at full load, nominal input (Fig. 1 curves are an image)
DCDC_DERATE = 0.8                     # design practice: a converter run at <= 80 % of its rating
# Also on the datasheet, not checked numerically: short-circuit protection 1 s max for B24xxS (then the input must
# be removed); 'Hot Plug: Unavailable'; case temperature rise 25 C typ at full load; derating above 85 C ambient.

# --- Daisy Seed. Datasheet v1.0.5, Table 1: VIN +4 .. +17 V; "safe to power the Daisy Seed from both the VIN inputs
# and the USB port simultaneously". It gives no supply current and no limit for external loads on 3V3D / 3V3A.
SEED_VIN = (4.0, 17.0)
# Supply current, NOT in the datasheet: 140 mA at 5 V at 480 MHz, 120 mA at 400 MHz (a USB meter, two oscillators, no
# LEDs or pots: community.daisy.audio/t/power-consumption/4521); 100 mA in another post there. Side FXy runs a reverb,
# a granular engine and delays out of SDRAM: ASSUMED 180 mA max (+30 %).
# Verify pass 2026-11-13: no Electrosmith figure exists (Seed datasheet v1.0.5 and the Seed2 DFM datasheet give none;
# the forum thread's posts are users': tele_player 120 mA at 400 MHz / 140 mA at 480 MHz, two oscillators, USB
# meter; TallMike ~100 mA). The MCU's own figure, DS12556 Rev 7 Table 127 (rev V, Run mode from ITCM, LDO on, VDD
# 3.3 V): 480 MHz VOS0, all peripherals disabled 148 mA typ / 226 mA max (TJ 25 C) / 307 mA (85 C); all peripherals
# enabled 226 typ / 348 max (25 C). 148 mA at 3.3 V through a 90 % buck is 108 mA at 5 V for the MCU alone, so the
# forum's 140 mA (MCU + SDRAM + codec + power LED) is a fair typical, but 180 mA is NOT a bound: the MCU's 25 C
# maximum alone is 166 mA at 5 V before the SDRAM (AS4C16M32, on 3V3D) and the codec (on 3V3A, linear from 5 V).
# Kept as the writer's assumption; a measured figure on the first build settles it (see D.dcdc_max).
# Electrosmith's own patch.Init() (Patch SM: the same MCU, SDRAM and codec) is rated +12 V 90 mA, firmware dependent.
SEED_I5_TYP, SEED_I5_MAX = 0.140, 0.180
# The Seed's 3V3D comes from a TPS6217x step-down (3 .. 17 V in, 0.5 A: TI TPS62170 family, SLVSAT8, from memory) and
# 3V3A from an LP2985 LDO (150 mA): a forum post (community.daisy.audio/t/seed-power-supply/292, July 2020), not
# Electrosmith's documents: NOT CONFIRMED. VBUS and VIN are diode-OR'd onto the regulators (same thread).
# Verify pass: CONFIRMED from the Seed datasheet v1.0.5's power schematic (the page image embedded in the PDF):
# "TPS6217?N" buck with R2 47K / R3 15K on FB -> +3V3_D; U4 "3v3 LP2985" from UNREGULATED_VCC through R1 5R1 ->
# FB1 -> +3V3_A (so 3V3A is linear from the 5 V: its current is 5 V current one for one); D1 / D2 NSR1020MW2T3G
# OR VBUS and V_IN onto UNREGULATED_VCC; a power LED (R14 1K) on +3V3_D. The TPS6217x family is the 0.5 A one
# (TPS62170/2/3/7, 3 .. 17 V in, TI SLVSAT8, not re-read); the efficiency figures stay from memory.
SEED_BUCK_IMAX = 0.500
SEED_BUCK_EFF_TYP, SEED_BUCK_EFF_MIN = 0.90, 0.85   # 5 V -> 3.3 V at 50-300 mA (TPS62170 curves, from memory)
SEED_3V3_TOL = 0.03                                 # ASSUMED +-3 % on 3V3D (feedback accuracy plus ripple)
LP2985_IMAX = 0.150
USB_IMAX = 0.500                                    # USB 2.0 port

# --- Waveshare 1.9inch LCD Module (waveshare.com/wiki/1.9inch_LCD_Module, FAQ): "3.3V 40mA" max; whether that includes
# the backlight at full PWM is not stated (the module schematic was not read). Typical ASSUMED 30 mA at full backlight.
# Verify pass: the module schematic (waveshare.com 1.9inch LCD Module schematic PDF, this session's scratchpad) has an
# RT9193-33 LDO from VCC to LCD_3V3, a TXS0108E level shifter, and the backlight LED_A on LCD_3V3 through R1 10R with
# LED_K switched by an S8050 whose base takes BL through R3 1K (R2 10K base-emitter). The backlight therefore runs from
# the module's own VCC, and the FAQ's "maximum power consumption: 3.3V 40mA" is the whole module's figure, backlight
# included. The BL pin's base current comes from the Seed's GPIO instead, i.e. from 3V3D, and was missing below.
LCD_I_MAX, LCD_I_TYP = 0.040, 0.030
LCD_BL_R, LCD_BL_RBE, LCD_BL_VBE = 1e3, 10e3, 0.7   # R3, R2, the S8050's VBE (assumed 0.7 V)

# --- Button LEDs. Thonk low-profile LED button, red: no datasheet; a red LED at ~3 mA ASSUMED VF 1.7 / 1.85 / 2.1 V.
LED_VF_MIN, LED_VF_TYP, LED_VF_MAX = 1.7, 1.85, 2.1
# TI SN74HC595 (SCLS041): VOH at VCC 4.5 V, IOH -6 mA: 4.3 V typ, 3.98 V min (25 C), 3.84 V min (-40..85 C) -> output
# resistance 33 R typ, 110 R worst at 4.5 V; scaled by the gate overdrive (4.5-0.9)/(3.3-0.9) = 1.5 to 3.3 V:
# 50 R typ, 165 R worst (interpolated). 0 R bounds the LED current from above.
HC_ROUT_TYP_33 = 50.0
# TI SN74HC165 (SCLS116) / SN74HC595 (SCLS041): ICC max 8 uA at VCC 6 V, IO 0, 25 C; 160 uA over -40..125 C.
HC_ICC_MAX = 160e-6
HC_CPD = 100e-12                      # ASSUMED power-dissipation capacitance per chip (HC shift registers ~50-400 pF)
HC_SUPPLY = (2.0, 6.0)                # V, recommended VCC
F_SR = 64e3                           # SR_CLK edges per second: 16 clocks per scan at the 4 kHz scan (design.md)
# --- H11L1: Motorola H11L1/D Rev 1 (text in this session's scratchpad, datasheets/h11l1m-a): VCC 3 .. 15 V operating
# (3 .. 16 V abs max); ICC(on) 1.2 typ / 5 max mA and ICC(off) 5 max mA at VCC 5 V; LED IF 60 mA continuous abs max,
# VR 6 V; VF 1.5 V max at 10 mA.
H11L1_VCC_MIN = 3.0
H11L1_ICC_TYP, H11L1_ICC_MAX = 1.2e-3, 5.0e-3
H11L1_IF_MAX = 0.060
# --- STM32H750 DS12556 Rev 7: weak pull-up RPU 30 / 40 / 50 kOhm (Table 58); Table 19: injected current per pin on
# FT / TT pins -5 / +0 mA ("positive injection is not possible"), total +-25 mA.
RPU_MIN = 30e3
IINJ_NEG_MAX = 5e-3
# --- TI TL07x SLOS080W (July 2025): IQ per amplifier 1.4 mA typ, 2.5 mA max (TL07xC, +-15 V, 25 C; verified by the
# mixer's suite). Supply (V+) - (V-): recommended 10 .. 30 V for NS / PS packages and TL07xM, 4.5 .. 40 V for all
# other devices; abs max 36 V (NS / PS / M), 42 V (others): the narrower pair is used. VOM at RL 10k: rails less 1.5 V
# typ, 3 V worst. ISC +-26 mA typ (short-circuit current, 6.x electrical characteristics). Input current 10 mA max
# when an input goes beyond the rails (abs max note 2, new die).
TL074_IQ_TYP, TL074_IQ_MAX = 1.4e-3, 2.5e-3
TL074_VS_MIN, TL074_VS_MAX, TL074_VS_ABSMAX = 10.0, 30.0, 36.0
TL074_HEAD_TYP, TL074_HEAD_MIN = 1.5, 3.0
TL074_ISC = 0.026
TL074_IIN_MAX = 10e-3
# --- Resistors: metal film 1/4 W (bom.md), rated at 70 C; judged at half the rating.
RES_P = 0.25
# --- Header contacts: generic 2.54 mm pin and socket (Thonk's header bag): ASSUMED 1 A per contact (branded: Harwin
# M20 3 A, Samtec 3+ A). Copper: 1 oz (35 um), 1.72e-8 Ohm m at 20 C; 20 mOhm per mated contact ASSUMED.
HDR_IMAX, HDR_R = 1.0, 0.020
CU_T, CU_RHO = 35e-6, 1.72e-8
# --- A Eurorack output patched where it should not go: up to the rails; a hard output current-limits at the TL07x's
# ISC (an op-amp output with no series resistor); most outputs have 1k or so in series.
V_EURO_MAX = 12.0
# --- Decoupling: the 100 n sits within 10 mm of track of the supply pin (~1 nH/mm, twice the cap's own lead ESL); the
# loop cap -> supply pin plus cap -> GND pin stays within 25 mm (~25 nH: a DIP-16 decoupled without a ground pour
# needs about 20 mm for the diagonal GND return; 25 nH x 20 mA / 5 ns = 0.1 V of ground bounce at 3.3 V logic).
DECOUPLE_MAX, LOOP_MAX = 10.0, 25.0

DOC = harness.text("docs", "design.md")
README = harness.text("README.md")
with open(os.path.join(harness.BOM, "side-fx-bom.csv"), encoding="utf-8") as f:
    BOM_CSV = list(csv.DictReader(f))

MB = {p.ref: p for p in circuit.main_board_parts()}
FB = {p.ref: p for p in circuit.faceplate_parts()}
ROUTED = harness.routed()
RB = {"main": ROUTED.main, "face": ROUTED.face}
r = lambda ref: harness.ohms((MB.get(ref) or FB.get(ref)).value)
V33 = 3.3


def bom_row(ref=None, text=None):
    for row in BOM_CSV:
        refs = re.split(r"[,:;]\s*|\s+", row["Refs"])
        if (ref and ref in refs) or (text and text.lower() in row["Part"].lower()):
            return row
    return None


# ===================================================================== A. J2 and the bus
print("--- A. J2 (the breakout's power header) against the Doepfer bus; U5's pads against the breakout")
pts = list(J2_HOLES.values())
ck.check("A.J2_pins: the breakout's J2 has 10 holes (a 10-pin bus header)", len(pts) == 10, f"{len(pts)} holes")
xs = sorted({x for x, y in pts})
ys = sorted({y for x, y in pts})
ck.check("A.J2_pitch: 2 columns and 5 rows at 2.54 mm (drill file)",
         len(xs) == 2 and abs(xs[1] - xs[0] - PITCH) < 0.02 and len(ys) == 5
         and all(abs(b - a - PITCH) < 0.02 for a, b in zip(ys, ys[1:])), f"columns {xs}, rows {ys}")
# pin numbering of a 2x5 header: pin 1 square, its row partner pin 2, then along the columns
one = J2_HOLES[1]
ck.check("A.J2_pin1: pin 1 is the square pad", one == J2_SQUARE_PAD, f"square pad at {J2_SQUARE_PAD}, pin 1 at {one}")
ck.check("A.J2_numbering: pins 1-2 at one end, 9-10 at the other, odd pins in one column",
         J2_HOLES[1][1] == J2_HOLES[2][1] and J2_HOLES[9][1] == J2_HOLES[10][1]
         and len({J2_HOLES[n][0] for n in (1, 3, 5, 7, 9)}) == 1, "")
for n in range(1, 11):
    ck.check(f"A.J2_pin.{n}: breakout J2 pin {n} = Doepfer {DOEPFER10[n]}", J2_TRACE[n] == DOEPFER10[n],
             f"expected {DOEPFER10[n]}, traced {J2_TRACE[n]}")
ck.check("A.J2_marking: the 'RED STRIPE' legend and the square pad mark the -12 V end", J2_TRACE[1] == "-12V"
         and "RED" in J2_LEGEND, f"{J2_LEGEND}, pin 1 {J2_TRACE[1]}")
print(f"    (info) J2 is a {J2_PART}: no shroud, no key: a turned-round or shifted plug fits (section B)")
cable = bom_row(text="power cable")
txt = (cable["Part"] + " / " + cable["Note"]) if cable else ""
ck.check("A.cable: the BOM orders a 10-pin to 16-pin (or 10-to-10) Eurorack cable for J2, not '10 or 16'",
         cable is not None and re.search(r"\b10[- ]?(pin )?(to|→|-)\s?(16|10)\b", txt) is not None and "10 or 16" not in txt,
         f"BOM: '{txt}'; the breakout's J2 is a 2x5 (10-pin) header")

# U5: the breakout's pins onto the footprint's pads, one rigid transform (rotation, translation, maybe a mirror)
u5 = RB["main"].parts["U5"]
src = np.array([BREAKOUT_PINS[k][0] for k in BREAKOUT_PINS])
dst = np.array([[u5["pads"][k].x, u5["pads"][k].y] for k in BREAKOUT_PINS])
A1 = np.c_[src, np.ones(len(src))]
sol, *_ = np.linalg.lstsq(A1, dst, rcond=None)
M = sol[:2].T
res = np.abs(A1 @ sol - dst).max()
orth = np.abs(M.T @ M - np.eye(2)).max()
ck.check("A.U5_map: the breakout's J1 / J3 / Seed / J4 / J5 pins fit U5's footprint pads by one rigid transform",
         res < 0.1 and orth < 1e-3, f"largest residual {res:.3f} mm, |M'M - I| {orth:.1e}, det {np.linalg.det(M):+.2f}")
# the breakout's SMD side faces the main board (det -1); the Seed sits on its other side, top outwards: the footprint
# must show the Seed counterclockwise (1 -> 20 -> 21 -> 40) seen from the main board's rear, as a DIP from its top
quad = [u5["pads"][k] for k in ("1", "20", "21", "40")]
area = sum(a.x * b.y - b.x * a.y for a, b in zip(quad, quad[1:] + quad[:1])) / 2
ck.check("A.U5_seed_handedness: Seed pins 1 -> 20 -> 21 -> 40 run counterclockwise seen from the rear (the Seed's "
         "top faces out), and the breakout is then seen from its bottom (mirror)", area > 0 and np.linalg.det(M) < 0,
         f"signed area {area:+.0f} mm^2, det {np.linalg.det(M):+.2f}")
# so the breakout's pins reach the main board out of its SMD side, while its own silk puts J1 / J3 / J4 / J5's header
# bodies (and J2, U3, C9, C18) on the other side, the Seed's: the build notes must say which way they go
DOCS_ALL = DOC + harness.text("docs", "bom.md") + README
said = re.search(r"breakout[^.]{0,200}(SMD|surface-mount|op-amp) side|(SMD|surface-mount|op-amp) side[^.]{0,200}breakout",
                 DOCS_ALL, re.I)
ck.check("A.U5_build_doc: the docs say the breakout's SMD side faces the main board, so its J1 / J3 / J4 / J5 male pins "
         "are soldered to stick out of the SMD side (against its silk, which draws them on the Seed's side)",
         said is not None, "design.md / bom.md / README say only 'male pins under the breakout'; mounted per the "
         "breakout's silk, J1 / J3 point away from the main board and U6 gets no +-12 V")
want = {"GND": "GND", "-12V": "-12V", "+12V": "+12V", "VIN": None}
for src_name, nets in (("circuit.py", MB["U5"].nets), ("routed", u5["nets"])):
    bad = {}
    for k, (_, cls) in BREAKOUT_PINS.items():
        got = nets.get(k)
        ok = (got == want[cls]) if cls in want else (got != "GND")
        if not ok:
            bad[k] = (cls, got)
    ck.check(f"A.U5_nets ({src_name}): every breakout rail / GND / VIN pin on U5's matching net (VIN left open)",
             not bad, f"mismatches {bad}" if bad else f"{len(BREAKOUT_PINS)} pins agree")

# ===================================================================== D. the loads (B, C, E use them)
print("--- D. the 3V3D, 3V3A and 5 V loads")


def led_current(v33, worst_high):
    rr = r("R1")
    if worst_high:
        return max(v33 - LED_VF_MIN, 0) / (rr * 0.99)
    return max(v33 - LED_VF_TYP, 0) / (rr + HC_ROUT_TYP_33)


n_leds = sum(1 for p in MB.values() if p.kind == "R" and p.nets.get("2", "").startswith("LED_"))
ck.check("D.led_count: one 470R per button LED", n_leds == len(circuit.BUTTONS),
         f"{n_leds} resistors to LED_*, {len(circuit.BUTTONS)} buttons")
i_led_typ, i_led_max = led_current(V33, False), led_current(V33 * (1 + SEED_3V3_TOL), True)
n_pull = sum(1 for p in FB.values() if p.kind == "RN9") * 8
V33_HI = V33 * (1 + SEED_3V3_TOL)
loads_typ = {
    "display (full backlight)": LCD_I_TYP,
    # verify pass: the BL pin drives the module's S8050 base through R3 1k (module schematic): a 3V3D load the
    # writer's list missed
    "BL pin into the module's S8050 base (R3 1k)": (V33 - LCD_BL_VBE) / LCD_BL_R - LCD_BL_VBE / LCD_BL_RBE,
    "button LEDs (all lit)": n_leds * i_led_typ,
    "H11L1 ICC": H11L1_ICC_TYP,
    "R27 MIDI pull-up (half the time low)": 0.5 * V33 / r("R27"),
    "74HC165 x2 + 74HC595": 3 * HC_CPD * V33 * F_SR,
    "RN1/RN2 pull-ups (one button held)": V33 / 10e3,
    "R25 clock pull-up (clock high half the time)": 0.5 * V33 / r("R25"),
    "SHIFT: the Seed's internal pull-up": 0.0,
}
loads_max = {
    "display (full backlight)": LCD_I_MAX,
    "BL pin into the module's S8050 base (R3 1k)": (V33 * (1 + SEED_3V3_TOL) - 0.6) / (LCD_BL_R * 0.95),
    "button LEDs (all lit)": n_leds * i_led_max,
    "H11L1 ICC": H11L1_ICC_MAX,
    "R27 MIDI pull-up (half the time low)": V33_HI / (r("R27") * 0.99),
    "74HC165 x2 + 74HC595": 3 * (HC_ICC_MAX + HC_CPD * V33 * F_SR),
    "RN1/RN2 pull-ups (one button held)": n_pull * V33_HI / (10e3 * 0.98),
    "R25 clock pull-up (clock high half the time)": V33_HI / (r("R25") * 0.99),
    "SHIFT: the Seed's internal pull-up": V33_HI / RPU_MIN,
}
I3D_TYP, I3D_MAX = sum(loads_typ.values()), sum(loads_max.values())
for k in loads_max:
    print(f"    3V3D {k:46} typ {loads_typ[k] * 1e3:6.2f} mA   max {loads_max[k] * 1e3:6.2f} mA")
print("    (max column: all 16 pull-ups low, R27 output low, Q1 on, SHIFT held, 3V3D +3 %)")
I3A = V33 / (r("R22") + r("R23"))
print(f"    3V3D external total: typ {I3D_TYP * 1e3:.1f} mA, max {I3D_MAX * 1e3:.1f} mA;  3V3A divider {I3A * 1e3:.3f} mA;"
      f"  per LED typ {i_led_typ * 1e3:.2f} mA, max {i_led_max * 1e3:.2f} mA")

m = re.search(r"display \((\d+) mA max\)", DOC)
ck.check("D.doc_display: design.md's display figure = Waveshare's '3.3V 40mA'", m is not None
         and abs(float(m.group(1)) * 1e-3 - LCD_I_MAX) < 1e-4, f"design.md: {m.group(0) if m else None}")
m = re.search(r"the LEDs \(about (\d+) mA\)", DOC)
ck.check("D.doc_leds: design.md's 'the LEDs (about N mA)' within 25 % of the typical five-LED current",
         m is not None and abs(float(m.group(1)) * 1e-3 - n_leds * i_led_typ) <= 0.25 * n_leds * i_led_typ,
         f"design.md {m.group(1) if m else None} mA, computed {n_leds * i_led_typ * 1e3:.1f} mA typ "
         f"({n_leds * i_led_max * 1e3:.1f} max)")
m = re.search(r"\(470R, about (\d+) mA into a red LED\)", DOC)
ck.check("D.doc_led_each: design.md's 'about 3 mA' per LED within 25 % of typical", m is not None
         and abs(float(m.group(1)) * 1e-3 - i_led_typ) <= 0.25 * i_led_typ,
         f"design.md {m.group(1) if m else None} mA, computed {i_led_typ * 1e3:.2f} mA typ")
m = re.search(r"about (\d+) mA on top of the Seed", DOC)
ck.check("D.doc_total: design.md's 'about 60 mA on top of the Seed' lies between the typical and the max 3V3D load",
         m is not None and I3D_TYP <= float(m.group(1)) * 1e-3 <= I3D_MAX,
         f"design.md {m.group(1) if m else None} mA, computed {I3D_TYP * 1e3:.1f} mA typ, {I3D_MAX * 1e3:.1f} mA max")

seed33_max = SEED_I5_MAX * DCDC_VOUT * SEED_BUCK_EFF_TYP / V33
ck.within("D.buck: the Seed's own 3V3 load + every external 3V3D load within its 3V3D buck's 0.5 A",
          seed33_max + I3D_MAX, None, SEED_BUCK_IMAX, " A",
          f"Seed ~{seed33_max * 1e3:.0f} mA (from {SEED_I5_MAX * 1e3:.0f} mA at 5 V), external {I3D_MAX * 1e3:.0f} mA; "
          f"buck part not confirmed")
ck.check("D.3V3A: the bias divider's load is a fraction of the LP2985's 150 mA", I3A < 0.01 * LP2985_IMAX,
         f"{I3A * 1e3:.2f} mA")


def i5(seed, ext, eff):
    """The DC/DC's output current (A) at 5 V: the Seed plus the external 3V3D load through the Seed's buck."""
    return seed + ext * V33 / (DCDC_VOUT * eff)


I5_TYP = i5(SEED_I5_TYP, I3D_TYP, SEED_BUCK_EFF_TYP)
I5_MAX = i5(SEED_I5_MAX, I3D_MAX, SEED_BUCK_EFF_MIN)
I5_SEEDTYP_EXTMAX = i5(SEED_I5_TYP, I3D_MAX, SEED_BUCK_EFF_MIN)
print(f"    5 V (DC/DC output): typ {I5_TYP * 1e3:.0f} mA ({I5_TYP * DCDC_VOUT:.2f} W); Seed typ + externals max "
      f"{I5_SEEDTYP_EXTMAX * 1e3:.0f} mA; worst {I5_MAX * 1e3:.0f} mA ({I5_MAX * DCDC_VOUT:.2f} W) of "
      f"{DCDC_IOUT_MAX * 1e3:.0f} mA")
ck.within(f"D.dcdc_typ: the typical 5 V load within {DCDC_DERATE:.0%} of the B2405S-1WR2's 200 mA",
          I5_TYP, DCDC_IOUT_MIN, DCDC_DERATE * DCDC_IOUT_MAX, " A",
          f"Seed {SEED_I5_TYP * 1e3:.0f} mA (a forum measurement) + 3V3D {I3D_TYP * 1e3:.0f} mA through the buck")
ck.within("D.dcdc_max: the worst-case 5 V load within the B2405S-1WR2's 200 mA (1 W)", I5_MAX, DCDC_IOUT_MIN,
          DCDC_IOUT_MAX, " A", f"Seed {SEED_I5_MAX * 1e3:.0f} mA (assumed) + 3V3D {I3D_MAX * 1e3:.0f} mA at "
          f"{SEED_BUCK_EFF_MIN:.0%} buck efficiency")
ck.check("D.dcdc_min_load: the Seed alone keeps the DC/DC above its 10 % minimum load (20 mA)",
         0.7 * SEED_I5_TYP >= DCDC_IOUT_MIN, f"{SEED_I5_TYP * 1e3:.0f} mA typ (100 mA in another measurement)")

# ===================================================================== B. reverse protection
print("--- B. D2 / D3 (B5819W) and L1 / L2 on the breakout")
I_TL = N_TL074 * 4 * TL074_IQ_TYP
I_TL_MAX = N_TL074 * 4 * TL074_IQ_MAX


def bus_currents(vbus, worst):
    """(current per bus rail, DC/DC input voltage, DC/DC input current): the DC/DC takes constant power."""
    p_out = DCDC_VOUT * (I5_MAX if worst else I5_TYP)
    eff = DCDC_EFF_WORST if worst else DCDC_EFF_TYP
    i_tl = I_TL_MAX if worst else I_TL
    i_in = p_out / (eff * 2 * vbus)
    for _ in range(30):
        vin = 2 * vbus - 2 * vf_b5819w(i_in + i_tl, worst) - 2 * L_DCR * i_in
        i_in = p_out / (eff * vin)
    return i_in + i_tl, vin, i_in


i_rail_t, vin_t, idc_t = bus_currents(V_BUS, False)
i_rail_w, vin_w, idc_w = bus_currents(V_BUS * (1 - BUS_TOL), True)
print(f"    typ (12.0 V bus): DC/DC in {idc_t * 1e3:.1f} mA at {vin_t:.2f} V; each rail {i_rail_t * 1e3:.1f} mA "
      f"(TL074s {I_TL * 1e3:.1f}); B5819W VF {vf_b5819w(i_rail_t):.3f} V")
print(f"    worst ({V_BUS * (1 - BUS_TOL):.1f} V bus): DC/DC in {idc_w * 1e3:.1f} mA at {vin_w:.2f} V; each rail "
      f"{i_rail_w * 1e3:.1f} mA (TL074s {I_TL_MAX * 1e3:.1f}); VF bound {D_VF_WORST} V")
for name, i, worst in (("typ", i_rail_t, False), ("max", i_rail_w, True)):
    ck.within(f"B.diode_current.{name}: the current through D2 / D3 within half the B5819W's 1 A", i, None, D_IO / 2,
              " A")
    p = i * vf_b5819w(i, worst)
    ck.within(f"B.diode_tj.{name}: B5819W junction at 50 C inside the case below 125 C", 50 + p * D_RTH, None, D_TJ,
              " C", f"{p * 1e3:.0f} mW x {D_RTH:.0f} K/W")
ck.within("B.L1_L2_isat: the DC/DC's input current through L1 / L2 below their 130 mA saturation current", idc_w,
          None, L_ISAT, " A", "MLZ1608A2R2WT000")
# J2 has no shroud: a 10-pin plug (bus pins 1..10 on it) may sit turned round and / or shifted by whole rows.
# D2 (anode on J2's +12 V pins) only lets a positive voltage onto the +12 V rail; D3 (cathode on J2's -12 V pins) only
# a negative one onto the -12 V rail; the rail side may still hold its charge (100 uF) when the plug is moved.
pins_of = collections.defaultdict(list)
for n, s in J2_TRACE.items():
    pins_of[s].append(n)
bus_v = {"-12V": -V_BUS * (1 + BUS_TOL), "GND": 0.0, "+12V": V_BUS * (1 + BUS_TOL)}
vr_max, wrong_pol, shorts = 0.0, [], set()
for rev in (False, True):
    for shift in range(-8, 9, 2):
        on = {}
        for m in range(1, 11):
            b = (11 - m if rev else m) + shift
            if 1 <= b <= 10:
                on[m] = DOEPFER10[b]
        if not rev and shift == 0:
            continue
        vp = [bus_v[on[n]] for n in pins_of["+12V"] if n in on]
        vn = [bus_v[on[n]] for n in pins_of["-12V"] if n in on]
        # forward conduction with the wrong polarity is impossible by the diodes' direction; record what conducts
        if vp and max(vp) < 0 or vn and min(vn) > 0:
            pass
        vr_max = max(vr_max, (V_BUS * (1 + BUS_TOL) - min(vp)) if vp else 0, (max(vn) + V_BUS * (1 + BUS_TOL)) if vn else 0)
        for n in pins_of["GND"]:
            if n in on and on[n] != "GND":
                shorts.add(on[n])
ck.check("B.reversed_plug: a turned-round 10-pin plug reverse-biases both diodes (D2's anode gets -12 V, D3's cathode "
         "+12 V)", True if all(DOEPFER10[11 - n] == "-12V" for n in pins_of["+12V"])
         and all(DOEPFER10[11 - n] == "+12V" for n in pins_of["-12V"]) else False,
         f"+12 V pins {pins_of['+12V']} get {[DOEPFER10[11 - n] for n in pins_of['+12V']]}, -12 V pins "
         f"{pins_of['-12V']} get {[DOEPFER10[11 - n] for n in pins_of['-12V']]}")
ck.within("B.reverse_voltage: worst reverse voltage over every turned / shifted plug position, rail side still "
          "charged, below the B5819W's 40 V", vr_max, None, D_VRRM, " V")
print(f"    (info) a shifted plug on the unshrouded J2 puts bus {sorted(shorts)} on the GND pins: the bus supply's "
      f"current limit takes it, as with any unkeyed header; the module's rails stay unpowered or single")

# ===================================================================== C. rails at the chips
print("--- C. rails at the chips")
v_hi = V_BUS * (1 + BUS_TOL) - vf_b5819w(0.02)      # light load, high bus
v_lo = V_BUS * (1 - BUS_TOL) - D_VF_WORST
print(f"    +-12 V at the chips: {v_lo:.2f} .. {v_hi:.2f} V")
ck.within("C.TL074_supply.max: (V+) - (V-) at the high corner within the TL074's 30 V recommended maximum", 2 * v_hi,
          None, TL074_VS_MAX, " V", f"abs max {TL074_VS_ABSMAX:g} V")
ck.within("C.TL074_supply.min: (V+) - (V-) at the low corner above the 10 V recommended minimum", 2 * v_lo,
          TL074_VS_MIN, None, " V")
need = 1.676 + 0.27 * V_EURO_MAX
ck.within("C.TL074_swing: U6's CV stages (out 1.68 -+ 0.27 x 12 V) within the guaranteed swing at the low corner",
          v_lo - TL074_HEAD_MIN, need, None, " V")
v33_lo = V33 * (1 - SEED_3V3_TOL)
ck.within("C.H11L1_supply: 3V3D at its low corner above the H11L1's 3.0 V minimum", v33_lo, H11L1_VCC_MIN, None, " V")
ck.within("C.HC_supply: 3V3D within the 74HC's 2 .. 6 V", v33_lo, HC_SUPPLY[0], HC_SUPPLY[1], " V")

# ===================================================================== D (cont.): the DC/DC's input and output
print("--- D. the DC/DC's input and output")
vin_hi = 2 * V_BUS * (1 + BUS_TOL) - 2 * vf_b5819w(0.03)
vin_lo_typvf = bus_currents(V_BUS * (1 - BUS_TOL), False)[1]
print(f"    DC/DC input: {vin_w:.2f} V (bus -5 %, max load, VF bound) / {vin_lo_typvf:.2f} V (bus -5 %, typ) / "
      f"{vin_t:.2f} V (12.0 V bus) / {vin_hi:.2f} V (bus +5 %, light load)")
ck.within("D.dcdc_vin.typ: DC/DC input at a 12.0 V bus within 21.6 .. 26.4 V", vin_t, DCDC_VIN[0], DCDC_VIN[2], " V")
ck.within("D.dcdc_vin.low_typ: DC/DC input at the -5 % bus, typical load and VF, within 21.6 .. 26.4 V",
          vin_lo_typvf, DCDC_VIN[0], DCDC_VIN[2], " V")
ck.within("D.dcdc_vin.low_worst: DC/DC input at the -5 % bus, max load, the B5819W's VF bound, within 21.6 .. 26.4 V",
          vin_w, DCDC_VIN[0], DCDC_VIN[2], " V", "the B5819W has no VF max below 1 A: 0.6 V + cold bound used")
ck.within("D.dcdc_vin.high: DC/DC input at the +5 % bus, light load, within 21.6 .. 26.4 V", vin_hi, DCDC_VIN[0],
          DCDC_VIN[2], " V")
dv_line = (vin_w / DCDC_VIN[1] - 1) * DCDC_LINE_REG
vout_lo = DCDC_VOUT * (1 + dv_line) * (1 - DCDC_ACC)
print(f"    DC/DC output at the low corner: about {vout_lo:.2f} V (line {dv_line * 100:+.1f} %, -{DCDC_ACC:.0%} accuracy)")
ck.within("D.dcdc_vout: the unregulated 5 V at the low corner stays inside the Seed's VIN 4 .. 17 V", vout_lo,
          SEED_VIN[0], SEED_VIN[1], " V", "Fig. 1 not read: from the 1.2 %/% line regulation and an assumed 5 %")

# ===================================================================== E. bus current per rail
print("--- E. the current the module draws from the bus")
print(f"    +12 V: {i_rail_t * 1e3:.0f} mA typ, {i_rail_w * 1e3:.0f} mA max;  -12 V: the same (the DC/DC sits across "
      f"both rails, the TL074s too);  +5 V: none (10-pin header)")
stated = re.search(r"\d+\s*mA[^.\n]{0,40}\+12\s*V|\+12\s*V[^.\n]{0,40}\d+\s*mA", DOC + README)
ck.check("E.doc_bus_current: design.md or the README states the current per bus rail for a case's power budget",
         stated is not None, f"not stated (design.md's Power section gives only 3V3D loads); computed +12 V "
         f"{i_rail_t * 1e3:.0f} mA typ / {i_rail_w * 1e3:.0f} mA max, -12 V the same, +5 V none")

# ===================================================================== F. ratings
print("--- F. ratings")
for ref, vmax in (("C15", v_hi), ("C16", v_hi), ("C14", V33), ("C4", V33_HI), ("C3", V33_HI), ("C17", V33_HI),
                  ("C1", V33_HI), ("C2", V33_HI), ("C10", V33)):
    row = bom_row(ref)
    mv = re.findall(r"(\d+)\s*V\b", row["Part"]) if row else []
    rating = min(float(v) for v in mv) if mv else None
    ck.check(f"F.cap_voltage.{ref}: the BOM's rating >= 2x the net's max ({vmax:.1f} V)", rating is not None
             and rating >= 2 * vmax, f"BOM '{row['Part'] if row else None}'")
pw = {}
pw["R24, +-12 V on CLOCK"] = V_EURO_MAX ** 2 / r("R24")
i26_hard = min((V_EURO_MAX - 0.7) / r("R26"), TL074_ISC)
i26_0r = (V_EURO_MAX - 0.7) / r("R26")
pw["R26, a 5 V MIDI source (220R at the sender)"] = ((5 - 1.2) / (220 + r("R26"))) ** 2 * r("R26")
pw["R26, a +-12 V op-amp output (ISC 26 mA) patched into MIDI"] = i26_hard ** 2 * r("R26")
_vbias = 3.3 * r("R23") / (r("R22") + r("R23"))      # BIAS from circuit.py (was a copied 1.32 V)
pw[f"R10/R13/R16/R19, +-12 V CV (node at BIAS {_vbias:.2f} V)"] = (V_EURO_MAX + _vbias) ** 2 / r("R10")
pw["R11/R14/R17/R20, output at the rail"] = v_hi ** 2 / r("R11")
pw["R12/R15/R18/R21, output at the rail into a clamped ADC pin"] = (v_hi - 3.3 - 0.6) ** 2 / r("R12")
pw["R25, Q1 on"] = V33_HI ** 2 / r("R25")
pw["R27, H11L1 output low"] = V33_HI ** 2 / r("R27")
pw["R1..R5, LED at max current"] = i_led_max ** 2 * r("R1")
pw["R22 + R23, bias divider"] = V33_HI ** 2 / (r("R22") + r("R23"))
# 2026-11-14: a resistor the BOM gives a higher rating (RATING in bom.py: "0.5 W or more in the 1/4 W body")
# is held to that rating, read from its BOM line; every other one to 1/4 W
def rating(ref):
    row = bom_row(ref)
    m = re.search(r"(?<![/\d.])(\d+(?:\.\d+)?)\s*W\b", row["Part"]) if row else None
    return float(m.group(1)) if m else RES_P


for k, p in pw.items():
    rr = rating(re.match(r"R\d+", k).group(0))
    ck.within(f"F.res_power: {k} <= half its {rr:g} W (BOM)", p, None, rr / 2, " W")
print(f"    (info) R26 with a 0R +-12 V source (a rail, no current limit): {i26_0r * 1e3:.0f} mA, "
      f"{i26_0r ** 2 * r('R26'):.2f} W")
ck.within("F.H11L1_led: the opto LED (or D2, the other polarity) with a +-12 V op-amp output in the MIDI jack, within "
          "the H11L1's 60 mA", i26_hard, None, H11L1_IF_MAX, " A")

# ===================================================================== G. faults
print("--- G. missing-rail faults")
v_dc_one = V_BUS - vf_b5819w(0.05) - 0.3           # one rail at 0 V: the dead side's diode holds about 0.3 V
ck.check("G.one_rail.dcdc_input: with +12 V or -12 V absent the DC/DC sees about 12 V, under its 21.6 V minimum; its "
         "output then falls below the Seed's 4 V, so the Seed stays off (not damaged)", v_dc_one < DCDC_VIN[0]
         and DCDC_VOUT * v_dc_one / DCDC_VIN[1] < SEED_VIN[0],
         f"{v_dc_one:.1f} V in, about {DCDC_VOUT * v_dc_one / DCDC_VIN[1]:.1f} V out")
# U6 with one rail missing: the dead rail sits a diode from GND; BIAS and the jack inputs are at 0 V, at or beyond the
# dead rail, where the classic TL07x die's output can reverse to either limit: up to the live rail less 1.5 V,
# through the 1k into the Seed's ADC pin (unpowered: the -12 V-only case drives it negative)
v_out_fault = V_BUS - TL074_HEAD_TYP
i_inj = (v_out_fault - 0.6) / r("R12")
ck.within("G.one_rail.adc_injection: U6's output with one rail missing, through the 1k into the ADC pin, within the "
          "STM32's 5 mA negative injection (positive: none allowed)", i_inj, None, IINJ_NEG_MAX, " A",
          f"output up to +-{v_out_fault:.1f} V, pin clamped near -0.6 V, R12 {r('R12'):.0f} R")
i_cv = (V_EURO_MAX - 0.6) / r("R10")
ck.within("G.unpowered.cv: a +-12 V CV into an unpowered module (100k into U6's input clamps) within 10 mA", i_cv,
          None, TL074_IIN_MAX, " A")
ck.within("G.unpowered.clock: +12 V into CLOCK unpowered (R24 into Q1's base-emitter) within 10 mA",
          (V_EURO_MAX - 0.7) / r("R24"), None, 10e-3, " A")
i_usb = SEED_I5_MAX + I3D_MAX * V33 / (5.0 * SEED_BUCK_EFF_MIN)
ck.within("G.usb: the Seed's USB powering the Seed and every 3V3D load with the rack off within a USB 2.0 port's "
          "500 mA", i_usb, None, USB_IMAX, " A", "VBUS and VIN are diode-OR'd on the Seed (datasheet: both at once is "
          "safe), so nothing back-feeds the DC/DC's output")
th = r("R22") * r("R23") / (r("R22") + r("R23"))
i_bias = max(V33 * r("R23") / (r("R22") + r("R23")) - 0.6, 0) / th
ck.within("G.usb.bias: BIAS into the unpowered U6's input clamps (rack off, USB on) within 10 mA", i_bias, None,
          TL074_IIN_MAX, " A")


# ===================================================================== H. decoupling on the routed boards
print("--- H. decoupling (routed boards)")


def track_graph(board, net):
    """Nodes: track ends (rounded to 1 um) per layer, vias, pads; edges: tracks (split where an end lands
    mid-track), via-to-track and pad-to-track joins."""
    ca = harness.load("copper_audit")
    ts = [t for t in board.tracks if t["net"] == net]
    adj = collections.defaultdict(list)
    key = lambda p, layer: (round(p[0], 3), round(p[1], 3), layer)
    ends = [(t["a"], t["layer"]) for t in ts] + [(t["b"], t["layer"]) for t in ts]

    def join(a, b, d):
        adj[a].append((b, d))
        adj[b].append((a, d))

    for t in ts:
        on = [t["a"], t["b"]]
        for p, layer in ends:
            if layer == t["layer"] and ca.d_point_seg(p, t["a"], t["b"]) <= t["w"] / 2 and p not in on:
                on.append(p)
        on.sort(key=lambda p: math.dist(p, t["a"]))
        for p, q in zip(on, on[1:]):
            join(key(p, t["layer"]), key(q, t["layer"]), math.dist(p, q))
    for v in board.vias:
        if v["net"] != net:
            continue
        vk = ("via", round(v["c"][0], 3), round(v["c"][1], 3))
        for t in ts:
            for p in (t["a"], t["b"]):
                if math.dist(p, v["c"]) <= v["r"] + t["w"] / 2:
                    join(vk, key(p, t["layer"]), math.dist(p, v["c"]))
    for pad in board.pads:
        if pad.net != net:
            continue
        pk = ("pad", pad.ref, pad.num)
        for t in ts:
            for p in (t["a"], t["b"]):
                if pad.d_point(p) <= t["w"] / 2 + 0.001:
                    join(pk, key(p, t["layer"]), math.dist(p, (pad.x, pad.y)))
        for v in board.vias:
            if v["net"] == net and pad.d_circle(v["c"], v["r"]) <= 0.001:
                join(pk, ("via", round(v["c"][0], 3), round(v["c"][1], 3)), math.dist(v["c"], (pad.x, pad.y)))
    return adj


def track_len(board, net, pa, pb):
    """Shortest copper path (mm) along the net's tracks, vias and pads from pad pa's centre to pad pb's, or None."""
    adj = track_graph(board, net)
    src, dst = ("pad", pa.ref, pa.num), ("pad", pb.ref, pb.num)
    dist, pq, tick = {}, [(0.0, 0, src)], itertools.count(1)
    while pq:
        d, _, n = heapq.heappop(pq)
        if n in dist:
            continue
        dist[n] = d
        if n == dst:
            return d
        for m, w in adj[n]:
            if m not in dist:
                heapq.heappush(pq, (d + w, next(tick), m))
    return None


def poured(board, pad):
    """Thermal spokes tying a pad into a pour of its own net."""
    return sum(1 for p0, p1, layer, n in board.spokes if n == pad.net and math.hypot(p0[0] - pad.x, p0[1] - pad.y) < 0.3)


DECOUPLING = [("main", "C15", "U6", "4", "+12V", "GND", None), ("main", "C16", "U6", "11", "-12V", "GND", None),
              ("main", "C3", "U3", "16", "3V3D", "GND", "8"), ("main", "C17", "U7", "6", "3V3D", "GND", "5"),
              ("face", "C1", "U1", "16", "3V3D_F", "GND_D_F", "8"), ("face", "C2", "U2", "16", "3V3D_F", "GND_D_F", "8"),
              ("face", "C4", "CN1", "1", "3V3D_F", "GND_D_F", "2")]
for bk, c, u, pin, net, gnd, gpin in DECOUPLING:
    b = RB[bk]
    parts = MB if bk == "main" else FB
    ck.check(f"H.netlist.{c}: {c} between {net} and {gnd}, {u}.{pin} on {net}" + (f", {u}.{gpin} on {gnd}" if gpin else ""),
             set(parts[c].nets.values()) == {net, gnd} and parts[u].nets.get(pin) == net
             and (gpin is None or parts[u].nets.get(gpin) == gnd), f"{c} {parts[c].nets}")
    cp = next(p for p in b.parts[c]["pads"].values() if p.net == net)
    cg = next(p for p in b.parts[c]["pads"].values() if p.net == gnd)
    up = b.parts[u]["pads"][pin]
    L = track_len(b, net, cp, up)
    straight = math.dist((cp.x, cp.y), (up.x, up.y))
    ck.check(f"H.decoupling.{c}->{u}.{pin}: supply track <= {DECOUPLE_MAX:g} mm", L is not None and L <= DECOUPLE_MAX,
             f"track {None if L is None else round(L, 1)} mm (straight {straight:.1f} mm)")
    if gpin:
        ug = b.parts[u]["pads"][gpin]
        sp_c, sp_u = poured(b, cg), poured(b, ug)
        if sp_c >= 2 and sp_u >= 2:
            ck.check(f"H.loop.{c}-{u}: both GND pads ({c}, {u}.{gpin}) tied into the GND pour", True,
                     f"spokes {sp_c} / {sp_u}")
        else:
            Lg = track_len(b, gnd, cg, ug)
            loop = (L or 99) + (Lg if Lg is not None else 99)
            ck.check(f"H.loop.{c}-{u}: supply track + GND track ({c} -> {u}.{gpin}) <= {LOOP_MAX:g} mm (no pour)",
                     loop <= LOOP_MAX, f"{None if L is None else round(L, 1)} + {None if Lg is None else round(Lg, 1)} "
                     f"= {loop:.1f} mm; spokes {sp_c} / {sp_u}")
    else:
        sp = poured(b, cg)
        ck.check(f"H.loop.{c}: its GND pad tied into the GND pour (>= 2 spokes)", sp >= 2, f"{sp} spokes")

# ===================================================================== I. power tracks
print("--- I. power tracks and H3")
POWER = {"main": ["+12V", "-12V", "3V3A", "3V3D"], "face": ["3V3D_F"]}
for bk, nets in POWER.items():
    for net in nets:
        ws = [t["w"] for t in RB[bk].tracks if t["net"] == net]
        ck.check(f"I.power_class.{net}: every {net} track >= 0.6 mm ({bk} board)", bool(ws) and min(ws) >= 0.6 - 1e-3,
                 f"{len(ws)} tracks, narrowest {min(ws) if ws else 0:.3f} mm")
h3_nets = next(n for ref, kind, n in circuit.HEADERS if ref == "H3")
n_vcc = sum(1 for mbn, fbn in h3_nets if mbn == "3V3D")
n_gnd = sum(1 for mbn, fbn in h3_nets if fbn == "GND_D_F")
i_face = LCD_I_MAX + n_leds * i_led_max + loads_max["RN1/RN2 pull-ups (one button held)"] + 2 * HC_ICC_MAX
ck.within(f"I.H3_current: the faceplate's whole 3V3D current over H3's {n_vcc} 3V3D and {n_gnd} GND_D_F contact(s) "
          f"within half a contact's {HDR_IMAX:g} A", i_face / max(min(n_vcc, n_gnd), 1), None, HDR_IMAX / 2, " A")
mb, fb = RB["main"], RB["face"]
h3_vcc = str(1 + [i for i, (a, b) in enumerate(h3_nets) if a == "3V3D"][0])
h3_gnd = str(1 + [i for i, (a, b) in enumerate(h3_nets) if b == "GND_D_F"][0])
L_mb = track_len(mb, "3V3D", mb.parts["U5"]["pads"]["38"], mb.parts["H3"]["pads"][h3_vcc])
L_fb = track_len(fb, "3V3D_F", fb.parts["HF3"]["pads"][h3_vcc], fb.parts["CN1"]["pads"]["1"])
L_g = track_len(fb, "GND_D_F", fb.parts["CN1"]["pads"]["2"], fb.parts["HF3"]["pads"][h3_gnd])
r_mm = CU_RHO / (0.6e-3 * CU_T) * 1e-3          # Ohm per mm of 0.6 mm, 1 oz track
if None in (L_mb, L_fb, L_g):
    ck.check("I.lcd_path: a track path U5.38 -> H3 -> CN1.1 and CN1.2 -> HF3's GND_D_F", False,
             f"main {L_mb}, face {L_fb}, gnd {L_g}")
else:
    drop = r_mm * (L_mb + L_fb + L_g) * i_face + 2 * HDR_R * i_face
    ck.within("I.lcd_drop: drop from the Seed's 3V3D to CN1 (both tracks, both H3 contacts; main-board GND poured) at "
              "the faceplate's max current <= 50 mV", drop, None, 0.050, " V",
              f"3V3D {L_mb:.0f} + {L_fb:.0f} mm, GND_D_F {L_g:.0f} mm of 0.6 mm track at {i_face * 1e3:.0f} mA")

ck.done()
