"""Power group: Marblesy's power entry (on the Seed breakout), current budget, ratings, decoupling,
power tracks and what happens while rails are missing.

Marblesy has no power header of its own. Rob Heel's seed_power_opamps breakout (U2) carries the
Eurorack header J2, the reverse-protection Schottkys D2 / D3, the 2.2 uH filters L1 / L2 and the
B2405S-1WR2 DC/DC for the Seed's 5 V; Marblesy takes +-12 V from the breakout's J1 / J3 and 3V3A /
3V3D from the Seed's pins 21 / 38. The breakout's facts below come from its BOM CSV (2025-08-29) and
from its Gerbers (copper, silkscreen and drill files read into a connectivity map in a scratch
script; the EasyEDA project on OSHWLab shows no schematic to a fetch).

What it checks
  A  J2 against the Doepfer A-100 bus (10-pin variant), D2 / D3 orientation per rail, a correct /
     reversed / side-shifted 10-pin plug (blocks, never reverses a rail), the B5819W's worst reverse
     voltage, the hazard of a 16-pin plug on the unshrouded 2x5.
  B  The B5819W at the real current (VF, dissipation, IF, inrush), L1 / L2 (Isat, DCR) against the
     DC/DC's input current, the B2405S fed across +12 / -12 V: its input at the bus tolerance, its
     output current against the Seed + Marblesy's 3V3 loads, the Seed's VIN range.
  C  Marblesy's J1 / J3 on the U2 footprint: circuit.SEED, the routed pads, against the breakout's
     header order (GND next to the empty position, the -12 V row with Seed pins 1-20); J4 / J5 GND.
  D  Current budget per rail, typical and worst: +-12 V (TL074 IQ, output loads, NEG_REF, the
     breakout's TL074s, the DC/DC), 3V3A, 3V3D (LEDs through the 74HC595, pull-ups, logic), against
     design.md's Power figures and the Seed's assumed rail limits.
  E  74HC595 at 3.3 V: per-output and per-chip current, design.md's "about 2.5 mA per lit LED".
  F  Decoupling: a 100 n per TL074 rail, per MCP4922 and per faceplate chip, nearest in the routed
     copper, copper path from the cap to the chip's supply pin (<= 10 mm) and ground pin (<= 10 mm more than
     the straight line: a DIP-16's pins 8 and 16 are 19 mm apart), design.md's distances,
     circuit.py's "# Uxx" comments against the routed pairing.
  G  Power tracks: every routed track of the power nets at design.md's 0.6 mm, IPC-2221 capacity of the
     narrowest, GND_D_F as tracks only, in one piece, never touching GND_F, entering / leaving at H5 / H6.
  H  Faults and sequencing: +-12 V up while the Seed is unpowered (ADC pins through the 1k at BIAS = 0,
     gate stages, clock pull-ups, the faceplate's logic), the powered ADC pins' abs max (TT) and active-ADC-input limit
     (3V3A + 0.3 V, AN4899) with a +-10 / 12 V
     CV (design.md's "within the STM32H7's limit"), the gate outputs while the Seed boots, one bus rail
     at 0 V or open.
  I  Ratings: capacitor voltages (BOM text and the export's devices, the breakout's own capacitors).

Run from marbles/hardware/tests:  python test_power.py
Read only: imports circuit.py, opens the routed export (harness.routed()) and reads docs/*.md.
"""
import collections
import heapq
import math
import os
import re
import sys

import harness

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ck = harness.Checks("power")
circuit = harness.load("circuit")
ca = harness.load("copper_audit")

# ======================================================================== constants (datasheets etc.)
# --- Eurorack bus. Doepfer's own pages (a100t_e.htm, a100m_e.htm) give no pin table in text; the A-100 16-pin
# table as reproduced by Elby Designs (elby-designs.com/webtek/documents/eurosynth/power_distribution.htm,
# "The Doepfer A-100 system uses a 16-pin IDC connector"): 1-2 -12 V, 3-8 0 V, 9-10 +12 V, 11-12 +5 V,
# 13-14 CV, 15-16 Gate; the 10-pin variant is pins 1-10 of it. Coloured (red) stripe = pin 1 = -12 V.
DOEPFER16 = {1: "-12", 2: "-12", 3: "GND", 4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND", 9: "+12", 10: "+12",
             11: "+5", 12: "+5", 13: "CV", 14: "CV", 15: "GATE", 16: "GATE"}
DOEPFER10 = {n: DOEPFER16[n] for n in range(1, 11)}
BUS_V = {"-12": -12.0, "GND": 0.0, "+12": 12.0, "+5": 5.0, "CV": (-10.0, 10.0), "GATE": (0.0, 12.0)}
V_RAIL = 12.0
BUS_TOL = 0.05          # assumption: no Eurorack rail tolerance standard; +-5 % covers common supplies

# --- The breakout (rob-scape/daisy-seed-breakout-boards, daisy-seed-dcdc-opamps):
# BOM_seed_power_opamps_2025-08-29.csv: J2 HDR-M-2.54_2x5 (LCSC C178292 = Amphenol 67997-210HLF, a plain
# unshrouded 2x5 male header), D2 D3 B5819W (CJ, C8598), L1 L2 MLZ1608A2R2WT000 (TDK), U3 B2405S-1WR2
# (Mornsun; the board's silkscreen says B2405S-1WR3), C9 C18 100 uF 50 V (ValuePro), C7 C20 C21 C23 C24 10 uF
# CL31A106KBHNNNE (Samsung: X5R, 'B' = 50 V), U2 U5 "TL084CPWR" named, TL074CPWR as the part number.
BREAKOUT_OPAMPS = 8                     # 2 x quad
BREAKOUT_CAP_V = {"C9/C18 100 uF": 50.0, "C7/C20/C21/C23/C24 10 uF": 50.0}
BREAKOUT_CAP_ACROSS = {"C9/C18 100 uF": V_RAIL, "C7/C20/C21/C23/C24 10 uF": 2 * V_RAIL}   # C24 sits +12 to -12
# From the Gerbers (Gerber_TopLayer.GTL, Gerber_BottomLayer.GBL, Drill_PTH_Through*.DRL, silkscreen GTO / GBO,
# EasyEDA v6.5.51 export 2025-08-29), traced in a scratch script (copper rasterised, joined through the plated
# holes): J2 square pad = pin 1, odd pins in one column. Nets found:
BRK_J2 = {1: "N_IN", 2: "N_IN", 3: "GND", 4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND", 9: "P_IN", 10: "P_IN"}
BRK_D2 = {"A": "P_IN", "K": "P12"}      # silk symbol: triangle towards the pad on the +12 node, bar there
BRK_D3 = {"K": "N_IN", "A": "N12"}      # silk symbol: bar on the J2 side
BRK_U3 = {1: "N12 via L2", 2: "P12 via L1", 3: "GND", 4: "Seed pin 39 (VIN)"}   # pad 1 square
BRK_STRIPE_PINS = (1, 2)                # bottom silk "RED STRIPE" beside J2 pins 1-2
# Breakout headers (pin 1 = the square pad next to the empty position / next to the Seed pins):
BRK_J1 = ("GND", "N12", "N12", "N12")   # on the Seed pin 1-20 row, beside pin 20, one empty position between
BRK_J3 = ("GND", "P12", "P12", "P12")   # on the pin 21-40 row, beside pin 21
BRK_AUDIO_GND_ORDER = ("GND", "sig", "GND", "sig")   # J4 / J5 from the Seed end outwards (beside pins 40 / 1)
BRK_SEED_GND = (20, 40)                 # Seed pins on the breakout's GND
# Mornsun B2405S-1WR2 pinout (SIP-4): 1 = GND (input -), 2 = Vin, 3 = 0V, 4 = +Vo. The datasheet's pin drawing is
# a graphic (not readable as text); the Gerber trace above agrees with it (pin 2 from +12, pin 1 from -12).
DCDC_PIN_IN_MINUS, DCDC_PIN_IN_PLUS, DCDC_PIN_0V, DCDC_PIN_OUT = 1, 2, 3, 4

# --- JSCJ B5817W-B5819W (www.cj-elec.com, rev D Mar 2015), B5819W column, Ta 25 C:
D_VRRM = 40.0           # V, repetitive peak reverse voltage
D_IO = 1.0              # A, average rectified
D_IFSM = 9.0            # A, 8.3 ms half sine
D_PD = 0.5              # W, power dissipation (RthJA 200 C/W)
D_VF_MAX = 0.60         # V max at IF = 1 A (JSCJ C8598 PDF, 25 C; also 0.9 V at 3 A, nothing lower)
D_VT_25C = 0.0257       # V, kT/q at 25 C: the bound below 1 A is D_VF_MAX - VT ln(1 A / i) (see vf())
D_VF_TYP_01A = 0.30     # V typ at 0.1 A: not readable from CJ's curve as text; the 1N5819-class typical curve
D_VF_SLOPE = 0.06       # V per decade, same source (assumption, read off a log plot)
D_IR_MAX = 1e-3         # A at VR = 40 V, 25 C

# --- TDK MLZ1608 series (inductor_commercial_decoupling_mlz1608_en, 20201224), MLZ1608A2R2WT000:
L_ISAT = 0.130          # A max, inductance down 50 %
L_ITEMP = 0.500         # A typ, +20 C
L_DCR_MAX = 0.25 * 1.3  # ohm, 0.25 +-30 %

# --- Mornsun B_S-1WR2 (2024.09.09-B/4), B2405S-1WR2:
DCDC_VIN_MIN, DCDC_VIN_MAX = 21.6, 26.4     # V input range (24 V nominal)
DCDC_SURGE_MIN = -0.7                        # V, surge voltage (1 s max), min
DCDC_IOUT_MAX, DCDC_IOUT_MIN = 0.200, 0.020  # A at 5 V (min load 10 %)
DCDC_EFF_MIN, DCDC_EFF_TYP = 0.76, 0.80      # full load, min / typ
DCDC_LINE_REG = 1.2                          # % output per % input change, max
DCDC_LOAD_REG = 0.12                         # 10 %-100 % load, typ (5 V output)
DCDC_ISO = 1500.0                            # VDC, input-output, 1 minute
# 24 V input: full load 57 mA typ, no load max 30 mA (text-extracted table; column alignment uncertain)
DCDC_NOLOAD_MAX = 0.030

# --- Electrosmith Daisy Seed datasheet v1.0.5: VIN 4..17 V (Table 1); GPIO 0..5 V abs max; 3.3 V-tolerant pins
# 24 (PB1), 25 (PA7), 28 (PC4), 29 (PA5), 30 (PA4); all other GPIO 5 V tolerant. Pin table: 23 PA3, 24 PB1,
# 25 PA7, 26 PA6, 27 PC1, 28 PC4, 31 PA1, 32 PA0. No current figures for the 3V3A / 3V3D pins.
SEED_VIN_MIN, SEED_VIN_MAX = 4.0, 17.0
SEED_GPIO_MAX = 5.0
SEED_TT_PINS = {"24", "25", "28", "29", "30"}
# Seed's own 5 V draw: not in the datasheet. community.daisy.audio/t/power-consumption/4521 (2025-02-20,
# measured with a USB meter): 120 mA at 400 MHz, 140 mA at 480 MHz, "about 100 mA at 5 V". Used: 120 typ,
# 140 worst (not confirmed).
SEED_I5_TYP, SEED_I5_MAX = 0.120, 0.140
# Seed rails (not confirmed: Electrosmith forum reading of the schematic): 3V3D from a TPS62177 buck (0.5 A),
# 3V3A from an LP2985 LDO (150 mA). Assumed: the LDO is fed from VIN (5 V current = 3V3A current), the buck at
# 85 %, and room for external loads of 100 mA (3V3A) and 300 mA (3V3D) after the Seed's own use; rails +-3 %.
SEED_3V3A_EXT_MAX, SEED_3V3D_EXT_MAX = 0.100, 0.300
BUCK_EFF = 0.85
V33, V33_TOL = 3.3, 0.03

# --- ST STM32H750 DS12556 Rev 7, Table 19: VIN on FT_xxx pins VSS-0.3 .. min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V;
# on TT_xx pins VSS-0.3 .. 4.0 V. Table 20: IINJ(PIN) on FT / TT pins -5 / +0 mA (PA4, PA5: -0 / 0), sum
# +-25 mA; note 3: "positive injection is not possible on these I/Os and does not occur for input voltages
# lower than the specified maximum value". Pin types (DS12556 pin table): PB1, PA7, PC4 TT_a; PA3, PA6 FT_(h)a.
STM_FT_ABOVE = 4.0
STM_TT_MAX = 4.0
# verifier change: ST AN4899 Rev 3 5.2.1 / 5.2.2 (DS12556 7.3.15 refers to it): with an analog input function enabled
# (ADC input active) FT_a / FT_fa / TT_a pins are not 5 V tolerant; maximum operating voltage min(VDDA, VREF+) + 0.3 V.
STM_ANALOG_ABOVE_VDDA = 0.3
STM_IINJ_NEG = 5e-3
STM_IINJ_SUM = 25e-3
SI_DIODE = 0.6          # V, a silicon clamp conducting

# --- TI TL07x SLOS080W (rev. July 2025), 5.8 (TL07xC, +-15 V, 25 C): IQ per amplifier 1.4 mA typ, 2.5 mA max;
# VOM RL >= 10k +-13.5 typ, +-12 min (headroom 1.5 / 3 V); new die: ISC +-26 mA typ; abs max note 2: inputs are
# diode-clamped to both rails (new die), inputs beyond the rails by > 0.5 V limited to 10 mA; old die rated
# (VCC-) - 0.3 V with no current allowance.
TL_IQ_TYP, TL_IQ_MAX = 1.4e-3, 2.5e-3
TL_HEAD_TYP, TL_HEAD_MIN = 1.5, 3.0
TL_IIN_MAX = 10e-3
TL_IN_BEYOND_OLD, TL_IN_BEYOND_NEW = 0.3, 0.5

# --- Microchip MCP4922 DS21897B, 3 V AC/DC characteristics: IDD 250 uA typ, 500 uA max (both channels,
# unbuffered, digital inputs grounded, output unloaded).
DAC_IDD_TYP, DAC_IDD_MAX = 250e-6, 500e-6

# --- TI SN74HC595 SCLS041J: abs max IO +-35 mA per output, +-70 mA through VCC or GND; VOH at 4.5 V,
# IOH -6 mA: 3.98 min (25 C), 3.84 min (-40..85 C), 4.3 typ; VOL at 4.5 V, IOL 6 mA: 0.17 typ, 0.26 max (25 C),
# 0.33 (-40..85); ICC (6 V) 8 uA max at 25 C, 80 uA -40..85; Cpd 400 pF typ.
HC595_IO_MAX, HC595_ICC_PIN_MAX = 35e-3, 70e-3
HC595_RH_45 = {"typ": (4.5 - 4.3) / 6e-3, "max": (4.5 - 3.84) / 6e-3}      # ohm at VCC 4.5 V
HC595_RL_45 = {"typ": 0.17 / 6e-3, "max": 0.33 / 6e-3}
HC_ICC_MAX = 80e-6
HC595_CPD = 400e-12
# TI SN74HC165 SCLS116H: ICC 8 / 80 uA (6 V); Cpd 75 pF typ. TI CD74HC4051 SCHS122O: ICC 8 / 80 uA (6 V).
HC165_CPD = 75e-12
# Output resistance at 3.3 V: the datasheet's figures are at 4.5 V (2.0 V gives only a 20 uA point). Scaled by
# (4.5 - Vt) / (3.3 - Vt) with Vt = 1.0 V (assumption: MOSFET on-resistance against gate overdrive): x 1.52.
HC_R_SCALE = (4.5 - 1.0) / (3.3 - 1.0)

# --- LEDs: no datasheet for Thonk's 3 mm LEDs or the LED buttons' LEDs (Thonk's site blocks fetches).
# Assumption for a standard diffused GaP / AlGaInP 3 mm LED at 2-4 mA: green 1.8 / 1.95 / 2.2 V, red 1.65 / 1.8 /
# 2.0 V (min / typ / max). Not confirmed.
LED_VF = {"G": (1.8, 1.95, 2.2), "R": (1.65, 1.8, 2.0)}

# --- Alpha 9 mm pots: total resistance +-20 % (assumption, Alpha's usual tolerance; not confirmed).
POT_TOL = 0.20
RES_TOL = 0.01          # the BOM's 1 % metal film

# --- IPC-2221 external conductor: I = 0.048 dT^0.44 A^0.725 (A in mil^2), 1 oz = 1.378 mil.
COPPER_MIL = 1.378
# --- Decoupling copper: a path of at most 10 mm (about 10 nH at ~1 nH/mm) from the cap to the pin it serves.
DECOUPLE_PATH_MAX = 10.0

# --- Firmware's SPI traffic (design.md Firmware; hal_daisy.cc): 6.25 MHz, 4 x 16 DAC bits every 32 kHz sample,
# a 16-bit LED frame every 4 samples, 8 button bits every ms.
SPI_HZ = 6.25e6
SPI_BITS_PER_SAMPLE = 64 + 16 / 4 + 8 / 32
FS = 32e3

DOC = harness.text("docs", "design.md")
BOM_MD = harness.text("docs", "bom.md")
MB = {p.ref: p for p in circuit.main_board_parts()}
FB = {p.ref: p for p in circuit.faceplate_parts()}
R = harness.routed()


def ohm(ref, parts=MB):
    return harness.ohms(parts[ref].value)


def par(*rs):
    return 1 / sum(1 / r for r in rs)


def vf(i, worst=False):
    """B5819W forward voltage at i (A)."""
    if worst:
        # verifier change: was D_VF_MAX (the 1 A figure) at every current. JSCJ gives VF max only at 1 A (0.6 V) and
        # 3 A; any Schottky's VF falls at least n VT ln(1 A / i) below its 1 A value (n >= 1; the series-resistance
        # drop falls too), so the 1 A maximum carried down with n = 1 and no resistance is still an upper bound.
        return D_VF_MAX - D_VT_25C * math.log(1.0 / min(max(i, 1e-5), 1.0))
    return D_VF_TYP_01A + D_VF_SLOPE * math.log10(max(i, 1e-5) / 0.1)


# ======================================================================== A. power entry on the breakout
print("--- A. J2 and the reverse protection (the breakout)")
for n in range(1, 11):
    bus = DOEPFER10[n]
    want = {"-12": "N_IN", "GND": "GND", "+12": "P_IN"}[bus]
    ck.check(f"A.J2_pin.{n}", BRK_J2[n] == want,
             f"Doepfer 10-pin pin {n} = {bus}: expected the breakout's {want} net, Gerbers show {BRK_J2[n]}")
ck.check("A.J2_stripe_mark", set(BRK_STRIPE_PINS) == {n for n, b in DOEPFER10.items() if b == "-12"},
         f"'RED STRIPE' silk beside pins {BRK_STRIPE_PINS}; Doepfer -12 V on pins "
         f"{[n for n, b in DOEPFER10.items() if b == '-12']}")
ck.check("A.D2_orientation", BRK_D2 == {"A": "P_IN", "K": "P12"},
         f"+12 V series diode: expected anode on J2 9-10, cathode on the +12 V node; got {BRK_D2}")
ck.check("A.D3_orientation", BRK_D3 == {"K": "N_IN", "A": "N12"},
         f"-12 V series diode: expected cathode on J2 1-2, anode on the -12 V node; got {BRK_D3}")


def plug(pins_cable, reverse, along, side):
    """{module J2 pin: bus signal} for a cable socket on the unshrouded 2x5 (pins 1..10 = rows of 2).
    reverse: socket turned round; along: rows shifted along the header; side: one column across (a pair swaps
    over, the other column hangs off)."""
    out = {}
    rows = pins_cable // 2
    for m in range(1, 11):
        row, col = (m - 1) // 2, (m - 1) % 2
        if reverse:
            row, col = 4 - row, 1 - col
        c_row, c_col = row + along, col + side
        if not (0 <= c_row < rows and 0 <= c_col < 2):
            continue
        out[m] = DOEPFER16[2 * c_row + c_col + 1]
    return out


def v_of(sig, hi):
    v = BUS_V[sig]
    return (max(v) if hi else min(v)) if isinstance(v, tuple) else v


def entry_state(bus):
    """(module GND pins' signals, worst diode reverse V, the +12 node's / -12 node's polarity) for a plug."""
    gnd_sig = {bus[m] for m in range(3, 9) if m in bus}
    p_in = [bus[m] for m in (9, 10) if m in bus]
    n_in = [bus[m] for m in (1, 2) if m in bus]
    ref = 0.0 if gnd_sig <= {"GND"} else None                  # module GND = bus GND only if 3-8 all on GND
    vr = 0.0
    if ref is not None:
        # circuit side charged to its rail (the worst for the reverse voltage)
        for s in p_in:
            vr = max(vr, (V_RAIL - D_VF_MAX) - v_of(s, False))
        for s in n_in:
            vr = max(vr, v_of(s, True) - (-V_RAIL + D_VF_MAX))
    # the circuit's nodes behind the diodes: D2 passes only a positive J2 9-10, D3 only a negative J2 1-2
    # (never the wrong polarity, as long as the reverse voltage stays under VRRM)
    pos = max([0.0] + [v_of(s, True) - D_VF_MAX for s in p_in])
    neg = min([0.0] + [v_of(s, False) + D_VF_MAX for s in n_in])
    return gnd_sig, vr, pos, neg


safe10, vr10, offset10 = [], 0.0, []
for reverse in (False, True):
    for side in (0, 1, -1):
        for along in range(-4, 5):
            bus = plug(10, reverse, along, side)
            gnd_sig, vr, pos, neg = entry_state(bus)
            vr10 = max(vr10, vr)
            # the circuit gets a rail of the right sign or nothing: +12 node >= 0, -12 node <= 0
            ok = gnd_sig <= {"GND"} and vr < D_VRRM
            if along == 0:
                state = "powered" if pos > 0 and neg < 0 else "unpowered" if pos == 0 and neg == 0 else "one rail"
                safe10.append((("rev" if reverse else "fwd") + (f" {side:+d} col" if side else "") + f" ({state})", ok))
            elif not ok:
                offset10.append(("rev " if reverse else "") + f"{along:+d} rows" + (f" {side:+d} col" if side else ""))
ck.check("A.10pin_plug_flush_any_way_safe", all(ok for _, ok in safe10),
         f"10-pin socket seated over all five rows, either way round, or one column across: GND pins stay on bus "
         f"GND and the diodes pass only the right polarity: {safe10}")
print(f"    (info) a 10-pin socket pushed on a row or more off the end (visible overhang): {len(offset10)} such "
      f"positions put a bus rail on the module's GND pins")
ck.check("A.B5819W_reverse_voltage", vr10 < D_VRRM,
         f"worst reverse voltage with a reversed 10-pin plug and the circuit side still charged: {vr10:.1f} V "
         f"against VRRM {D_VRRM:.0f} V")
bad16 = []
for reverse in (False, True):
    for along in range(-4, 4):
        bus = plug(16, reverse, along, 0)
        if len(bus) < 10:
            continue                                     # the 2x8 socket must cover the 2x5 to seat
        gnd_sig = {bus[m] for m in range(3, 9)}
        if gnd_sig - {"GND"}:
            bad16.append((("rev " if reverse else "") + f"{along} rows", sorted(gnd_sig - {"GND"})))
n16 = sum(1 for reverse in (False, True) for along in range(-4, 4) if len(plug(16, reverse, along, 0)) == 10)
print(f"    (info) a 16-pin socket covers the unshrouded 2x5 J2 in {n16} positions (it always overhangs, so a flush "
      f"fit is no cue); {len(bad16)} of them put a bus supply on the module's GND pins: {bad16}. test_bom checks "
      f"that the BOM names a 10-pin plug at the module end")

# ======================================================================== B. currents in the power entry
print("--- B. D2 / D3, L1 / L2 and the B2405S at the real currents")
# ---- the 3V3 loads first (section D computes them in detail; needed here for the DC/DC)


def led_current(kind, corner, v33=V33):
    """One lit LED: (3V3D - VF - 595 drops) / (470 + 595 output resistance(s)). corner 'typ' or 'max' current."""
    vmin, vtyp, vmax = LED_VF[kind]
    r470 = 470.0
    if corner == "max":                          # most current: VF min, rail high, drops 0, resistor -1 %
        return (v33 * (1 + V33_TOL) - vmin) / (r470 * (1 - RES_TOL))
    if corner == "min":                          # least current: VF max, rail low, 595 at its worst
        rh, rl = HC595_RH_45["max"] * HC_R_SCALE, HC595_RL_45["max"] * HC_R_SCALE
        return (v33 * (1 - V33_TOL) - vmax) / (r470 * (1 + RES_TOL) + rh + rl)
    rh, rl = HC595_RH_45["typ"] * HC_R_SCALE, HC595_RL_45["typ"] * HC_R_SCALE
    return (v33 - vtyp) / (r470 + rh + rl)


LEDS_SINGLE = [(ref, kind) for ref, _, kind, _ in circuit.LEDS if kind == "G"]          # one line each
LEDS_BIPOLAR = [ref for ref, _, kind, _ in circuit.LEDS if kind == "RG"]                 # one colour at a time
n_led_lines = sum(1 for _, _, kind, (r, g) in circuit.LEDS for s in (r, g) if s)


def leds_total(corner):
    tot = sum(led_current("G", corner) for _ in LEDS_SINGLE)
    # a bipolar LED lights red or green, never both; the larger of the two for 'max', red for 'typ'
    tot += sum(max(led_current("R", corner), led_current("G", corner)) if corner == "max"
               else led_current("R", corner) for _ in LEDS_BIPOLAR)
    return tot


f_spi = SPI_HZ * min(1.0, SPI_BITS_PER_SAMPLE / (SPI_HZ / FS))
logic_dyn = (2 * HC595_CPD + HC165_CPD) * V33 * f_spi
pullups_btn = [p for p in FB.values() if p.kind == "R" and "3V3D_F" in p.nets.values()]
pullups_clk = [MB["R51"], MB["R53"]]
I3D = {"typ": leds_total("typ") + logic_dyn + 1 * V33 / ohm("R51"),         # one clock input high
       "max": leds_total("max") + logic_dyn + 3 * HC_ICC_MAX
       + sum(V33 * (1 + V33_TOL) / (harness.ohms(p.value) * (1 - RES_TOL)) for p in pullups_btn + pullups_clk)}
pots = [p for p in FB.values() if p.kind == "POT"]
v_ref = 2.5
I_R47 = {"typ": (V33 - v_ref) / ohm("R47"),
         "max": (V33 * (1 + V33_TOL) - v_ref * (1 - 0.005)) / (ohm("R47") * (1 - RES_TOL))}
I_BIAS = {"typ": V33 / (ohm("R45") + ohm("R46")),
          "max": V33 * (1 + V33_TOL) / ((ohm("R45") + ohm("R46")) * (1 - RES_TOL))}
I_POTS = {"typ": sum(V33 / harness.ohms(p.value) for p in pots),
          "max": sum(V33 * (1 + V33_TOL) / (harness.ohms(p.value) * (1 - POT_TOL)) for p in pots)}
n_dac = sum(1 for p in MB.values() if p.kind == "MCP4922")
I_DAC = {"typ": n_dac * DAC_IDD_TYP, "max": n_dac * DAC_IDD_MAX}
I3A = {c: I_POTS[c] + I_BIAS[c] + I_R47[c] + I_DAC[c] + (HC_ICC_MAX if c == "max" else 0.0) for c in ("typ", "max")}
I5 = {"typ": SEED_I5_TYP + I3A["typ"] + I3D["typ"] * V33 / (5.0 * BUCK_EFF),
      "max": SEED_I5_MAX + I3A["max"] + I3D["max"] * V33 * (1 + V33_TOL) / (5.0 * BUCK_EFF)}
print(f"    3V3A {I3A['typ'] * 1e3:.1f} / {I3A['max'] * 1e3:.1f} mA, 3V3D {I3D['typ'] * 1e3:.1f} / {I3D['max'] * 1e3:.1f} mA "
      f"(typ / worst); Seed VIN {I5['typ'] * 1e3:.0f} / {I5['max'] * 1e3:.0f} mA at 5 V")

# ---- the DC/DC: input across the two rails after D2 / D3 and L1 / L2
ck.check("B.DCDC_fed_across_rails", BRK_U3[DCDC_PIN_IN_PLUS].startswith("P12") and
         BRK_U3[DCDC_PIN_IN_MINUS].startswith("N12") and BRK_U3[DCDC_PIN_0V] == "GND",
         f"Gerbers: Vin (pin {DCDC_PIN_IN_PLUS}) {BRK_U3[DCDC_PIN_IN_PLUS]}, input GND (pin {DCDC_PIN_IN_MINUS}) "
         f"{BRK_U3[DCDC_PIN_IN_MINUS]}, 0V (pin {DCDC_PIN_0V}) {BRK_U3[DCDC_PIN_0V]}: a 24 V converter across +12 / -12 V")


def dcdc_input(i5, bus, worst):
    """(input voltage, input current) of the B2405S for a 5 V load i5 and bus rails +-bus (fixed point)."""
    i_in = 0.05
    for _ in range(40):
        p_in = 5.0 * i5 / (DCDC_EFF_MIN if worst else DCDC_EFF_TYP)
        v_in = 2 * (bus - vf(i_in + 0.06, worst) - L_DCR_MAX * i_in)
        i_in = p_in / v_in
    return v_in, i_in


vin_typ, iin_typ = dcdc_input(I5["typ"], V_RAIL, False)
vin_lo_typvf, _ = dcdc_input(I5["max"], V_RAIL * (1 - BUS_TOL), False)
vin_nom_maxvf, _ = dcdc_input(I5["max"], V_RAIL, True)
vin_lo, iin_max = dcdc_input(I5["max"], V_RAIL * (1 - BUS_TOL), True)
vin_hi = 2 * (V_RAIL * (1 + BUS_TOL) - vf(0.03, False))              # light load, VF typ
print(f"    DC/DC input: {vin_typ:.2f} V typ ({iin_typ * 1e3:.0f} mA), {vin_lo:.2f} V at -5 % bus with VF max "
      f"({iin_max * 1e3:.0f} mA), {vin_hi:.2f} V at +5 % light load")
ck.within("B.DCDC_vin.nominal_bus_VF_max", vin_nom_maxvf, DCDC_VIN_MIN, DCDC_VIN_MAX, " V",
          "12.0 V bus, both B5819W at their maximum (the 1 A 0.6 V carried down to the real current), L DCR max")
ck.within("B.DCDC_vin.bus_minus5pct_VF_typ", vin_lo_typvf, DCDC_VIN_MIN, DCDC_VIN_MAX, " V", "11.4 V bus, VF typ")
ck.within("B.DCDC_vin.bus_minus5pct_VF_max", vin_lo, DCDC_VIN_MIN, DCDC_VIN_MAX, " V",
          "11.4 V bus and both diodes at VF max (the 1 A figure carried down to the real current): the corner; the Seed still gets its 4 V (below)")
ck.within("B.DCDC_vin.bus_plus5pct", vin_hi, DCDC_VIN_MIN, DCDC_VIN_MAX, " V", "12.6 V bus, light load")
ck.within("B.DCDC_iout_typ", I5["typ"], DCDC_IOUT_MIN, DCDC_IOUT_MAX, " A", "Seed 120 mA (forum) + Marblesy's 3V3 loads")
ck.within("B.DCDC_iout_worst", I5["max"], DCDC_IOUT_MIN, DCDC_IOUT_MAX, " A",
          "Seed 140 mA at 480 MHz (forum) + Marblesy's worst 3V3 loads through the LDO / 85 % buck")
# the Seed's VIN: unregulated output, 5 V at nominal input and full load; line regulation 1.2 % per 1 %
v_out_lo = 5.0 * (1 + DCDC_LINE_REG * (vin_lo / 24.0 - 1))
v_out_hi = 5.0 * (1 + DCDC_LINE_REG * (vin_hi / 24.0 - 1)) * (1 + DCDC_LOAD_REG)
ck.within("B.Seed_VIN_low", v_out_lo, SEED_VIN_MIN, SEED_VIN_MAX, " V", f"DC/DC at {vin_lo:.2f} V in, full load")
ck.within("B.Seed_VIN_high", v_out_hi, SEED_VIN_MIN, SEED_VIN_MAX, " V", f"DC/DC at {vin_hi:.2f} V in, light load")
ck.check("B.DCDC_isolation", 2 * V_RAIL * (1 + BUS_TOL) <= DCDC_ISO,
         f"input GND (pin 1) at -12 V, output 0V at GND: {V_RAIL * (1 + BUS_TOL):.1f} V across the barrier, "
         f"rated {DCDC_ISO:.0f} VDC")
# ---- L1 / L2 carry the DC/DC's input current only (Marblesy's +-12 V leaves at J1 / J3, before them)
ck.within("B.L1_L2_current_vs_Isat", iin_max, 0, L_ISAT, " A", f"worst DC/DC input current; Itemp {L_ITEMP} A")
print(f"    L1 / L2 drop {L_DCR_MAX * iin_max * 1e3:.0f} mV each at {iin_max * 1e3:.0f} mA")


# ======================================================================== D. current budget (+-12 V)
print("--- D. current budget per rail")
n_amps = 4 * sum(1 for p in MB.values() if p.kind == "TL074")
ck.check("D.TL074_count", n_amps == 16, f"expected 16 amplifiers (4 x TL074), got {n_amps}")
EXT_TYP, EXT_MIN = 100e3, 10e3            # a Eurorack input: 100k typical, 10k worst


def gate_load(v_oa, r_ext):
    """Op-amp output current of one gate stage at v_oa: feedback (R60 + R61 to GND), 1k into ext || (3k3 + LED)."""
    r_fb = ohm("R60") + ohm("R61")
    r_led = ohm("R91", FB)
    vled = LED_VF["G"][0]
    # node T: (v_oa - T)/1k = T/r_ext + max(T - vled, 0)/r_led
    t = v_oa * r_ext / (1e3 + r_ext)
    for _ in range(50):
        t = (v_oa / 1e3 + (vled / r_led if t > vled else 0)) / (1 / 1e3 + 1 / r_ext + (1 / r_led if t > vled else 0))
    return (v_oa - t) / 1e3 + v_oa / r_fb, t


v_gate = 3.3 * (1 + ohm("R61") / ohm("R60"))
i_gate_w, t_gate = gate_load(v_gate, EXT_MIN)
v_cv_pos, v_cv_neg = 5.32, 5.45                    # design.md's output range
i_cvout = lambda v, r: v / (1e3 + r) + v / ohm("R72")
i_cvin = 12.0 / ohm("R21")                          # a +-12 V source into the 100k (op-amp output carries it)
i_negref = 2.5 / ohm("R43") + 4 * 2.5 / ohm("R71")
loads_p_worst = 3 * i_gate_w + 4 * i_cvout(v_cv_pos, EXT_MIN) + 7 * i_cvin
loads_n_worst = 4 * i_cvout(v_cv_neg, EXT_MIN) + 7 * i_cvin + i_negref
mods = {}
for c, iq, worst in (("typ", TL_IQ_TYP, False), ("max", TL_IQ_MAX, True)):
    own_p = n_amps * iq + (loads_p_worst if worst else 0.0)
    own_n = n_amps * iq + (loads_n_worst if worst else i_negref)
    _, i_dc = dcdc_input(I5[c], V_RAIL * (1 - BUS_TOL) if worst else V_RAIL, worst)
    brk = BREAKOUT_OPAMPS * iq
    mods[c] = {"own+": own_p, "own-": own_n, "dcdc": i_dc, "brk": brk,
               "bus+": own_p + brk + i_dc, "bus-": own_n + brk + i_dc}
for c in ("typ", "max"):
    m = mods[c]
    print(f"    {c}: Marblesy +12 {m['own+'] * 1e3:.1f} / -12 {m['own-'] * 1e3:.1f} mA; breakout op-amps "
          f"{m['brk'] * 1e3:.1f}, DC/DC {m['dcdc'] * 1e3:.1f} mA -> bus +12 V {m['bus+'] * 1e3:.0f} mA, "
          f"-12 V {m['bus-'] * 1e3:.0f} mA")
print(f"    worst loads: 3 gates at {v_gate:.2f} V into 10k + LED ({i_gate_w * 1e3:.2f} mA each, jack {t_gate:.2f} V), "
      f"4 CV outputs into 10k, 7 CV inputs at 12 V; NEG_REF {i_negref * 1e3:.2f} mA")
POWER_SEC = DOC.split("### Power", 1)[1].split("\n---", 1)[0] if "### Power" in DOC else ""
ck.check("D.design_states_bus_current", re.search(r"12 ?V[^.]*?\d+ ?mA|\d+ ?mA[^.]*?12 ?V", POWER_SEC) is not None,
         f"design.md gives no +-12 V draw for a case's PSU budget; computed: +12 V {mods['typ']['bus+'] * 1e3:.0f} mA "
         f"typ / {mods['max']['bus+'] * 1e3:.0f} mA worst, -12 V {mods['typ']['bus-'] * 1e3:.0f} / "
         f"{mods['max']['bus-'] * 1e3:.0f} mA (breakout and DC/DC included)")
# ---- the B5819W at that current
for d, key in (("D2", "bus+"), ("D3", "bus-")):
    i = mods["max"][key]
    ck.within(f"B.{d}_current_vs_IO", i, 0, D_IO / 2, " A", "half the 1 A rating at the worst-case load")
    ck.within(f"B.{d}_dissipation", i * D_VF_MAX, 0, D_PD / 4, " W", f"{i * 1e3:.0f} mA x VF max {D_VF_MAX} V, "
              f"a quarter of the {D_PD} W rating (ambient inside a case)")
    print(f"    {d}: {i * 1e3:.0f} mA worst, VF {vf(mods['typ'][key]):.2f} V typ / {D_VF_MAX} V max")
c_brk = 2 * 100e-6 + 4 * 10e-6
c_mb = sum(harness.farads(p.value) for p in MB.values() if p.kind == "C" and set(p.nets.values()) & {"+12V", "-12V"})
q_inrush = (c_brk + c_mb) * V_RAIL
ck.check("B.inrush_charge_vs_IFSM", q_inrush < D_IFSM * 8.3e-3 * 2 / math.pi,
         f"charging {c_brk * 1e6 + c_mb * 1e6:.0f} uF to 12 V takes {q_inrush * 1e3:.2f} mC; one IFSM half sine "
         f"carries {D_IFSM * 8.3e-3 * 2 / math.pi * 1e3:.0f} mC")
rail_typ = V_RAIL - vf(mods["typ"]["bus+"])
rail_min = V_RAIL * (1 - BUS_TOL) - D_VF_MAX
print(f"    +-12 V at Marblesy's chips: {rail_typ:.2f} V typ, {rail_min:.2f} V worst (11.4 V bus, VF max)")
ck.check("D.CV_out_swing_at_worst_rail", rail_min - TL_HEAD_MIN >= v_cv_neg,
         f"rail {rail_min:.2f} V - TL074 worst headroom {TL_HEAD_MIN} V = {rail_min - TL_HEAD_MIN:.2f} V against the "
         f"CV outputs' {v_cv_neg} V")

# ======================================================================== C. J1 / J3 on the U2 footprint
print("--- C. Marblesy's J1 / J3 on the U2 footprint")
u2 = R.main.parts["U2"]
seed_nets = {pin: net for pin, (name, net) in circuit.SEED.items()}
want_net = {"GND": "GND", "N12": "-12V", "P12": "+12V"}
for hdr, brk in (("J1", BRK_J1), ("J3", BRK_J3)):
    for k, b in enumerate(brk):
        pin = f"{hdr}-{k + 1}"
        exp = want_net[b]
        ck.check(f"C.{pin}.circuit", seed_nets.get(pin) == exp, f"breakout {b}: expected {exp}, circuit.SEED {seed_nets.get(pin)}")
        ck.check(f"C.{pin}.routed", u2["pads"][pin].net == exp, f"expected {exp}, routed pad {u2['pads'][pin].net}")
P = u2["pads"]


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


for hdr, seedpin in (("J1", "20"), ("J3", "21")):
    same_row = all(abs(P[f"{hdr}-{k}"].x - P[seedpin].x) < 0.01 for k in range(1, 5))
    d = [dist(P[f"{hdr}-{k}"], P[seedpin]) for k in range(1, 5)]
    ck.check(f"C.{hdr}_beside_pin{seedpin}", same_row and abs(d[0] - 2 * 2.54) < 0.02 and
             all(abs(d[k] - (k + 2) * 2.54) < 0.02 for k in range(4)),
             f"pin 1 (GND) one empty position from Seed pin {seedpin}, pins 2-4 beyond it on the same row: "
             f"distances {[round(x, 2) for x in d]} mm, same row {same_row}")
for hdr, seedpin in (("J4", "40"), ("J5", "1")):
    order = sorted(range(1, 5), key=lambda k: dist(P[f"{hdr}-{k}"], P[seedpin]))
    got = tuple("GND" if seed_nets.get(f"{hdr}-{k}") == "GND" else "sig" for k in order)
    ck.check(f"C.{hdr}_gnd_positions", got == BRK_AUDIO_GND_ORDER,
             f"from the Seed end outwards the breakout has {BRK_AUDIO_GND_ORDER}; circuit.SEED gives {got}")
for pin in BRK_SEED_GND:
    ck.check(f"C.Seed_pin{pin}_GND", seed_nets.get(str(pin)) == "GND" and P[str(pin)].net == "GND",
             f"the breakout ties it to GND; circuit {seed_nets.get(str(pin))}, routed {P[str(pin)].net}")
ck.check("C.VIN_left_open", seed_nets.get("39") is None and P["39"].net is None,
         f"pin 39 (VIN) is fed by the breakout's DC/DC; Marblesy must leave it open: circuit "
         f"{seed_nets.get('39')}, routed {P['39'].net}")
for pin, net in (("21", "3V3A"), ("38", "3V3D")):
    ck.check(f"C.Seed_pin{pin}_{net}", seed_nets.get(pin) == net and P[pin].net == net,
             f"circuit {seed_nets.get(pin)}, routed {P[pin].net}")

# ======================================================================== D. 3V3 budgets against design.md
print("--- D. 3V3A / 3V3D against design.md")
m = re.search(r"3V3A load: 8 pots \(([\d.]+) mA\), reference \(([\d.]+) mA\), DACs \(about\s+([\d.]+)\s*mA\)", DOC)
ck.check("D.design_3V3A_sentence", m is not None, "Power: '3V3A load: 8 pots (x mA), reference (x mA), DACs (about x mA)'")
if m:
    d_pots, d_ref, d_dac = (float(x) * 1e-3 for x in m.groups())
    ck.close("D.design_pots_mA", I_POTS["typ"] * 1e3, d_pots * 1e3, 0.1 * d_pots * 1e3, " mA")
    ck.close("D.design_reference_mA", I_R47["typ"] * 1e3, d_ref * 1e3, 0.1 * d_ref * 1e3, " mA")
    ck.within("D.design_DACs_mA", d_dac * 1e3, I_DAC["typ"] * 1e3, 1.1 * I_DAC["max"] * 1e3, " mA",
              "the doc's figure between the typical and maximum IDD (DS21897B at 3 V)")
m = re.search(r"3V3D load: pull-ups and shift registers, a few mA, LEDs at most\s+(\d+)\s*mA", DOC)
ck.check("D.design_3V3D_sentence", m is not None, "Power: '3V3D load: ... LEDs at most x mA'")
pu_logic = I3D["max"] - leds_total("max")
ck.within("D.design_3V3D_few_mA", pu_logic * 1e3, 0, 10, " mA",
          "pull-ups (all buttons held, both clock transistors on) + 74HC ICC + Cpd at the SPI traffic: 'a few mA'")
if m:
    ck.within("D.design_LEDs_at_most", leds_total("max") * 1e3, 0, float(m.group(1)), " mA",
              f"{len(LEDS_SINGLE)} green + {len(LEDS_BIPOLAR)} bipolar lit at once, VF min, 3V3D +3 %, 470R -1 %, "
              f"595 drop 0 (typ {leds_total('typ') * 1e3:.1f} mA)")
ck.within("D.Seed_3V3A_external", I3A["max"], 0, SEED_3V3A_EXT_MAX, " A", "assumed LP2985 room (not confirmed)")
ck.within("D.Seed_3V3D_external", I3D["max"], 0, SEED_3V3D_EXT_MAX, " A", "assumed TPS62177 room (not confirmed)")

# ======================================================================== E. 74HC595 driving the LEDs
print("--- E. 74HC595 outputs at 3.3 V")
m = re.search(r"About ([\d.]+) mA per lit LED", DOC)
ck.check("E.design_per_LED_sentence", m is not None, "'About x mA per lit LED'")
if m:
    per = [led_current("G", "typ"), led_current("R", "typ")]
    ck.check("E.design_per_LED_mA", all(abs(x * 1e3 - float(m.group(1))) <= 0.25 * float(m.group(1)) for x in per),
             f"doc {m.group(1)} mA; typ green {per[0] * 1e3:.2f}, red {per[1] * 1e3:.2f} mA (595 at 3.3 V: output "
             f"resistance scaled from 4.5 V)")
lo = min(led_current("G", "min"), led_current("R", "min"))
print(f"    least current per lit LED {lo * 1e3:.2f} mA (VF max, 3V3D -3 %, 595 at its worst)")
ck.within("E.per_output_current", max(led_current("G", "max"), led_current("R", "max")), 0, HC595_IO_MAX, " A",
          "abs max per output")
for u in ("U9", "U10"):
    lines = [(ref, kind) for ref, _, kind, (r, g) in circuit.LEDS for s in (r, g) if s and s.startswith(u + ":")]
    leds_here = sorted({ref for ref, _ in lines})
    kind_of = {ref: kind for ref, _, kind, _ in circuit.LEDS}
    i_chip = sum(led_current("R" if kind_of[ref] == "RG" else "G", "max") for ref in leds_here)
    ck.within(f"E.{u}_VCC_GND_current", i_chip, 0, HC595_ICC_PIN_MAX, " A",
              f"{len(leds_here)} LEDs fed by {u} ({', '.join(leds_here)}), all lit, worst current")

# ======================================================================== F. decoupling
print("--- F. decoupling")


def track_path(board, net, src, dst):
    """Shortest copper path (mm) along tracks and vias of one net from pad src to pad dst (('pad', ref, num))."""
    nodes = collections.defaultdict(list)

    def edge(u, v, w):
        nodes[u].append((v, w))
        nodes[v].append((u, w))

    ts = [t for t in board.tracks if t["net"] == net]
    pads = [p for p in board.pads if p.net == net]
    vias = [(i, v) for i, v in enumerate(board.vias) if v["net"] == net]

    def pt(e, layer):
        return ("pt", round(e[0], 3), round(e[1], 3), layer)

    for i, t in enumerate(ts):
        edge(pt(t["a"], t["layer"]), pt(t["b"], t["layer"]), math.hypot(t["b"][0] - t["a"][0], t["b"][1] - t["a"][1]))
        for e in (t["a"], t["b"]):
            for p in pads:
                if p.d_point(e) <= t["w"] / 2 + 0.001:
                    edge(pt(e, t["layer"]), ("pad", p.ref, p.num), math.hypot(e[0] - p.x, e[1] - p.y))
            for vi, v in vias:
                dv = math.hypot(e[0] - v["c"][0], e[1] - v["c"][1])
                if dv <= v["r"] + t["w"] / 2 + 0.001:
                    edge(pt(e, t["layer"]), ("via", vi), dv)
            for j, o in enumerate(ts):
                if j != i and o["layer"] == t["layer"] and ca.d_point_seg(e, o["a"], o["b"]) <= (o["w"] + t["w"]) / 2:
                    for q in (o["a"], o["b"]):
                        edge(pt(e, t["layer"]), pt(q, o["layer"]), math.hypot(q[0] - e[0], q[1] - e[1]))
    best = {src: 0.0}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            return d
        if d > best.get(u, 1e18):
            continue
        for v, w in nodes[u]:
            if d + w < best.get(v, 1e18):
                best[v] = d + w
                heapq.heappush(heap, (d + w, v))
    return None


def poured(board, pad):
    """The pad is tied into a pour of its own net: thermal spokes from it."""
    return sum(1 for p0, p1, layer, n in board.spokes if n == pad.net and math.hypot(p0[0] - pad.x, p0[1] - pad.y) < 0.3)


# chip -> [(supply pin, supply net, gnd net, chip's own GND pin or None)]
SUPPLY = {}
for u, p in MB.items():
    if p.kind == "TL074":
        SUPPLY[("main", u)] = [("4", "+12V", "GND", None), ("11", "-12V", "GND", None)]
    elif p.kind == "MCP4922":
        SUPPLY[("main", u)] = [("1", "3V3A", "GND", "12")]
for u, p in FB.items():                       # 74HC4051 / 595 / 165: VCC pin 16, GND pin 8
    if p.kind == "MUX":
        SUPPLY[("face", u)] = [("16", "3V3A_F", "GND_F", "8")]
    elif p.kind in ("HC595", "HC165"):
        SUPPLY[("face", u)] = [("16", "3V3D_F", "GND_D_F", "8")]
for (bk, u), pins in SUPPLY.items():
    for pin, net, gnd, gpin in pins:
        parts = MB if bk == "main" else FB
        ck.check(f"F.{u}.{pin}_supply_net", parts[u].nets.get(pin) == net, f"expected {net}, got {parts[u].nets.get(pin)}")
        if gpin:
            ck.check(f"F.{u}.{gpin}_ground_net", parts[u].nets.get(gpin) == gnd,
                     f"expected {gnd}, got {parts[u].nets.get(gpin)}")
assigned = {}
for (bk, u), pins in sorted(SUPPLY.items()):
    board = R.board(bk)
    parts = MB if bk == "main" else FB
    for pin, net, gnd, gpin in pins:
        chip_pad = board.parts[u]["pads"][pin]
        caps = [c for c in parts.values() if c.kind == "C" and set(c.nets.values()) == {net, gnd}]
        best = None
        for c in caps:
            cp = next(n for n, v in c.nets.items() if v == net)
            pad = board.parts[c.ref]["pads"][cp]
            d = math.hypot(pad.x - chip_pad.x, pad.y - chip_pad.y)
            if best is None or d < best[0]:
                best = (d, c.ref, cp)
        if best is None:
            ck.check(f"F.{u}.{pin}_has_100n", False, f"no capacitor {net} - {gnd} in circuit.py")
            continue
        d, c, cp = best
        assigned.setdefault((bk, c), []).append(f"{u}.{pin}")
        ck.check(f"F.{u}.{pin}_100n", parts[c].value == "100n", f"nearest {net} cap {c} is {parts[c].value}")
        L = track_path(board, net, ("pad", c, cp), ("pad", u, pin))
        ck.check(f"F.{c}_to_{u}.{pin}_supply_path", L is not None and L <= DECOUPLE_PATH_MAX,
                 f"{net} copper path {None if L is None else round(L, 1)} mm (straight {d:.2f} mm), limit "
                 f"{DECOUPLE_PATH_MAX} mm")
        gp = next(n for n, v in parts[c].nets.items() if v == gnd)
        gpad = board.parts[c]["pads"][gp]
        if gpin is not None and not any(i.net == gnd for i in board.islands):
            Lg = track_path(board, gnd, ("pad", c, gp), ("pad", u, gpin))
            # verifier change: was Lg <= 10 mm. A DIP-16's GND (pin 8) and VCC (pin 16) are diagonal, 19.3 mm apart,
            # so with the cap at pin 16 the ground return can never be 10 mm; the criterion is now the detour: the
            # track path at most DECOUPLE_PATH_MAX longer than the straight line from the cap's GND pad to the pin.
            # (Re-measured independently with a densely sampled path finder: C9 -> U9.8 126 mm, C10 -> U11.8 28.5 mm,
            # C11 -> U10.8 25.4 mm.)
            gch = board.parts[u]["pads"][gpin]
            dg = math.hypot(gpad.x - gch.x, gpad.y - gch.y)
            ck.check(f"F.{c}_to_{u}.{gpin}_ground_path", Lg is not None and Lg <= dg + DECOUPLE_PATH_MAX,
                     f"{gnd} tracks (no pour on this net) {None if Lg is None else round(Lg, 1)} mm from {c} to {u}.{gpin}; "
                     f"straight {dg:.1f} mm, expected at most {dg + DECOUPLE_PATH_MAX:.1f} mm")
        else:
            sp = poured(board, gpad)
            extra = ""
            if gpin is not None:
                gch = board.parts[u]["pads"][gpin]
                extra = f"; {u}.{gpin} has {poured(board, gch)} spokes"
                sp = min(sp, poured(board, gch))
            ck.check(f"F.{c}.ground_in_pour", sp >= 2, f"{c} {gnd} pad thermal spokes {poured(board, gpad)}{extra}")
        print(f"    {u}.{pin} ({net}): {c}, {d:.2f} mm straight, {L if L is None else round(L, 1)} mm of track")
for (bk, c), users in sorted(assigned.items()):
    ck.check(f"F.{c}_serves_one_pin", len(users) == 1, f"{c} is the nearest cap of {users}")
n_tl_caps = sum(1 for p in MB.values() if p.kind == "C" and p.value == "100n" and set(p.nets.values()) & {"+12V", "-12V"})
ck.check("F.one_100n_per_TL074_rail", n_tl_caps == 2 * sum(1 for p in MB.values() if p.kind == "TL074"),
         f"{n_tl_caps} caps on +-12 V for {sum(1 for p in MB.values() if p.kind == 'TL074')} TL074s")
# design.md's distances (pad centre to pin centre)
dist_of = {}
for (bk, c), users in assigned.items():
    u, pin = users[0].split(".")
    board = R.board(bk)
    parts = MB if bk == "main" else FB
    net = (parts[u].nets[pin])
    cp = next(n for n, v in parts[c].nets.items() if v == net)
    a, b = board.parts[c]["pads"][cp], board.parts[u]["pads"][pin]
    dist_of[(bk, u, pin)] = math.hypot(a.x - b.x, a.y - b.y)
tl = [v for (bk, u, pin), v in dist_of.items() if MB.get(u) and MB[u].kind == "TL074"]
dac = [v for (bk, u, pin), v in dist_of.items() if MB.get(u) and MB[u].kind == "MCP4922"]
face = [v for (bk, u, pin), v in dist_of.items() if bk == "face"]
m = re.search(r"Every TL074 supply pin has its 100 n within\s+([\d.]+)–([\d.]+) mm, both DACs theirs within ([\d.]+) mm",
              DOC)
ck.check("D.design_decoupling_sentence", m is not None, "PCB placement: 'Every TL074 supply pin has its 100 n within ...'")
if m:
    lo_, hi_, dmax = (float(x) for x in m.groups())
    ck.check("F.design_TL074_distances", lo_ - 0.06 <= min(tl) and max(tl) <= hi_ + 0.05,
             f"doc {lo_}-{hi_} mm; routed {min(tl):.2f}-{max(tl):.2f} mm")
    ck.check("F.design_DAC_distances", max(dac) <= dmax + 0.05, f"doc within {dmax} mm; routed {[round(x, 2) for x in dac]}")
m = re.search(r"each with its 100 n within ([\d.]+)–([\d.]+) mm of pin 16", DOC)
if m:
    lo_, hi_ = float(m.group(1)), float(m.group(2))
    ck.check("F.design_faceplate_distances", lo_ - 0.06 <= min(face) and max(face) <= hi_ + 0.05,
             f"doc {lo_}-{hi_} mm; routed {sorted(round(x, 2) for x in face)} (the 6.9 predates C10's 0.75 mm move)")
# circuit.py's "# Uxx" comments against the routed pairing
src = open(os.path.join(harness.TOOLS, "circuit.py"), encoding="utf-8").read()
for ref, chip in re.findall(r'C\("(C\d+)", "100n", "3V3[AD](?:_F)?", "GND(?:_D_F)?"\)\)\s+#\s*(U\d+)', src):
    bk = "main" if ref in MB and ref not in FB else "face"
    users = assigned.get((bk, ref), [])
    ck.check(f"F.circuit_comment.{ref}", any(x.startswith(chip + ".") for x in users),
             f"circuit.py says '# {chip}'; in the routed copper {ref} is the nearest cap of {users}")

# ======================================================================== G. power tracks
print("--- G. power tracks")
POWER = {"main": ("+12V", "-12V", "3V3A", "3V3D"), "face": ("3V3A_F", "3V3D_F", "GND_D_F")}
m = re.search(r"power ([\d.]+) mm \(([^)]*)\)", DOC)
ck.check("G.design_power_width_sentence", m is not None, "Routing: 'power 0.6 mm (...)'")
w_doc = float(m.group(1)) if m else 0.6
doc_nets = set(re.sub(r"±12 V", "+12V, -12V", m.group(2)).replace(" ", "").split(",")) if m else set()
ck.check("G.design_power_nets", doc_nets == {"+12V", "-12V", "3V3A", "3V3D", "3V3A_F", "3V3D_F", "GND_D_F"},
         f"design.md lists {sorted(doc_nets)}")
I_NET = {"+12V": mods["max"]["own+"], "-12V": mods["max"]["own-"], "3V3A": I3A["max"], "3V3D": I3D["max"],
         "3V3A_F": I_POTS["max"] + HC_ICC_MAX, "3V3D_F": I3D["max"] - 2 * V33 / ohm("R51"), "GND_D_F": I3D["max"]}
for bk, nets in POWER.items():
    board = R.board(bk)
    for net in nets:
        ts = [t for t in board.tracks if t["net"] == net]
        thin = [t for t in ts if t["w"] < w_doc - 0.005]
        where = "; ".join(f"{t['w']:.2f} mm ({t['a'][0]:.2f}, {t['a'][1]:.2f})-({t['b'][0]:.2f}, {t['b'][1]:.2f}) "
                          f"{math.hypot(t['b'][0] - t['a'][0], t['b'][1] - t['a'][1]):.2f} mm long" for t in thin)
        ck.check(f"G.width.{net}", bool(ts) and not thin,
                 f"{len(ts)} tracks, {len(thin)} under {w_doc} mm" + (f": {where}" if thin else ""))
        wmin = min(t["w"] for t in ts)
        area = wmin / harness.MIL * COPPER_MIL
        i_cap = 0.048 * 10 ** 0.44 * area ** 0.725
        ck.check(f"G.IPC2221.{net}", i_cap >= 2 * I_NET[net],
                 f"narrowest {wmin:.2f} mm carries {i_cap:.2f} A at 10 C rise (1 oz); the net's worst current "
                 f"{I_NET[net] * 1e3:.0f} mA (x2 margin)")
face = R.face
groups, contacts = face.connectivity()
ck.check("G.GND_D_F_one_piece", len(groups["GND_D_F"]) == 1, f"{len(groups['GND_D_F'])} copper pieces")
gd = [c for c in contacts if {"GND_D_F", "GND_F"} == {c[0], c[1]}]
ck.check("G.GND_D_F_never_touches_GND_F", not gd, f"{len(gd)} contacts: {gd[:3]}")
ck.check("G.GND_D_F_tracks_only", not any(i.net == "GND_D_F" for i in face.islands)
         and all(abs(t["w"] - w_doc) < 0.01 for t in face.tracks if t["net"] == "GND_D_F"),
         "no GND_D_F pour; every GND_D_F track at the doc's width")
hdr_gd = sorted(f"{p.ref}.{p.num}" for p in face.pads if p.net == "GND_D_F" and p.ref.startswith("HF"))
hdr_3d = sorted(f"{p.ref}.{p.num}" for p in face.pads if p.net == "3V3D_F" and p.ref.startswith("HF"))
ck.check("G.GND_D_F_leaves_at_H5.4", hdr_gd == ["HF5.4"], f"GND_D_F header pins {hdr_gd}")
ck.check("G.3V3D_F_enters_at_H6.1", hdr_3d == ["HF6.1"], f"3V3D_F header pins {hdr_3d}")
a, b = face.parts["HF5"]["pads"]["4"], face.parts["HF6"]["pads"]["1"]
print(f"    LED / logic supply loop: in at HF6.1 ({b.x:.1f}, {b.y:.1f}), out at HF5.4 ({a.x:.1f}, {a.y:.1f}), "
      f"{math.hypot(a.x - b.x, a.y - b.y):.0f} mm apart (design.md: 'the LED current loop spans the board')")
ck.check("G.design_loop_sentence", re.search(r"3V3D_F\s+enters the faceplate at H6 while GND_D_F leaves at H5", DOC)
         is not None, "Routing: 'enters at H6 ... leaves at H5'")

# ======================================================================== H. faults and sequencing
print("--- H. faults: the Seed unpowered while +-12 V is up, one rail missing")
gain = ohm("R22") / ohm("R21")
cv_pins = {}
for name, label, u, s in circuit.CV_CHANNELS:
    pin = next(p for p, (nm, net) in circuit.SEED.items() if net == f"ADC_{name}")
    cv_pins[name] = pin
rs = ohm("R23")
# (1) the Seed unpowered: VDD = 0, BIAS = 0 (3V3A off) -> V_adc = -gain * Vin; FT and TT limit 4.0 V
for vin in (5.0, 10.0, 12.0):
    v_pos = gain * vin                                       # a -vin input
    ck.within(f"H.unpowered_ADC_pin_max.{vin:.0f}V", v_pos, None, STM_TT_MAX, " V",
              f"-{vin:.0f} V into the 100k at BIAS = 0: FT pins min(VDD..)+4 = 4.0 V and TT pins 4.0 V with VDD = 0; "
              f"below it no positive injection, so nothing back-powers the Seed (DS12556 Table 20 note 3)")
    i_neg = max(gain * vin - SI_DIODE, 0) / rs
    ck.within(f"H.unpowered_ADC_neg_injection.{vin:.0f}V", i_neg, None, STM_IINJ_NEG, " A",
              f"+{vin:.0f} V in: {-gain * vin:.2f} V behind the 1k, per pin")
    ck.within(f"H.unpowered_ADC_injection_sum.{vin:.0f}V", 7 * i_neg, None, STM_IINJ_SUM, " A", "all seven CV inputs")
# (2) the Seed powered: BIAS from R45 / R46, a -10 / -12 V CV
bias = V33 * ohm("R46") / (ohm("R45") + ohm("R46"))
for vin in (10.0, 12.0):
    v_adc = bias * (1 + gain) + gain * vin
    tt = sorted(n for n, p in cv_pins.items() if p in SEED_TT_PINS)
    ft = sorted(n for n, p in cv_pins.items() if p not in SEED_TT_PINS)
    ck.within(f"H.powered_TT_ADC_pins.-{vin:.0f}V", v_adc, None, STM_TT_MAX, " V",
              f"{', '.join(f'{n} (pin {cv_pins[n]})' for n in tt)} are TT pins (Seed datasheet: 3.3 V tolerant; "
              f"DS12556 VIN max 4.0 V, no positive injection allowed); breaks it from {-(STM_TT_MAX - bias * (1 + gain)) / gain:.1f} V in")
    # verifier change: was min(VDD + 4 V, the Seed's 5 V), the FT limit of a digital input. These pins are active ADC
    # inputs while the Seed runs, and then FT_a / FT_ha pins are not 5 V tolerant: min(VDDA, VREF+) + 0.3 V (AN4899
    # Rev 3 5.2.2), VDDA = VREF+ = 3V3A on the Seed
    ck.within(f"H.powered_FT_ADC_pins.-{vin:.0f}V", v_adc, None, V33 + STM_ANALOG_ABOVE_VDDA, " V",
              f"{', '.join(ft)}: FT_a / FT_ha pins in ADC mode, limit 3V3A + 0.3 V (AN4899; the 5 V FT figure applies "
              f"to digital inputs only); breaks it from {-(V33 + STM_ANALOG_ABOVE_VDDA - bias * (1 + gain)) / gain:.1f} V in")
m = re.search(r"a ±12 V input pushes\s+about ([\d.]+) mA through the 1k into the Seed's protection diodes, which is\s+within "
              r"the STM32H7's limit", DOC)
ck.check("H.design_injection_claim", m is None,
         f"design.md: '±12 V pushes about {m.group(1) if m else '?'} mA ... into the protection diodes, within the STM32H7's "
         f"limit'; DS12556 Table 20 allows -5 / +0 mA on FT and TT pins (positive injection not possible), the "
         f"TT pins' 4.0 V maximum is passed at {bias * (1 + gain) + gain * 12:.2f} V, and every CV pin, as an active ADC "
         f"input, is limited to 3V3A + 0.3 V (AN4899)" if m else "design.md no longer makes that claim (M1, 2026-11-13)")
# (3) gate stages: the Seed pin drives a TL074 IN+ and, since 2026-11-14 (L3), a 100k pull-down to GND: nothing that
# can drive current into the Seed, and 33 uA out of it when high
for name, u, s in circuit.GATES:
    net = f"GATE_{name}"
    users = [f"{p.ref}.{k}" for p in MB.values() for k, v in p.nets.items() if v == net]
    downs = [p for p in MB.values() if p.kind == "R" and net in p.nets.values() and set(p.nets.values()) == {net, "GND"}]
    expect = [f"U2.{next(p for p, (_, n) in circuit.SEED.items() if n == net)}", f"{u}.{circuit.SECTION[s][2]}"] +         [f"{p.ref}.{k}" for p in downs for k, v in p.nets.items() if v == net]
    i_load = sum(V33 / ohm(p.ref) for p in downs)
    ck.check(f"H.gate_input_only_opamp.{name}", sorted(users) == sorted(expect) and i_load < 1e-3,
             f"{net} on {users}: TL074 IN+ (pA bias), the Seed pin and {[p.ref for p in downs]} to GND "
             f"({i_load * 1e6:.0f} uA from the pin when high): nothing that can drive current into the Seed")
    pulled = [p.ref for p in MB.values() if p.kind == "R" and net in p.nets.values()]
    ck.check(f"H.gate_defined_while_Seed_boots.{name}", bool(pulled),
             f"no pull-down on {net}: while the Seed is unpowered, in reset or in its bootloader the STM32 pin floats "
             f"(DS12556: floating input during and after reset) and the x2.5 stage's output is undefined (0 to "
             f"{v_gate:.2f} V or the rail): spurious gates on {name}")
# (4) clock inputs: the collector pull-up goes to 3V3D only
for k, name in enumerate(("T", "X")):
    net = f"{name}_CLK"
    users = sorted(f"{p.ref}.{n}" for p in MB.values() for n, v in p.nets.items() if v == net)
    ck.check(f"H.clock_pullup_to_3V3D.{name}", set(MB[f"R{51 + 2 * k}"].nets.values()) == {"3V3D", net}
             and len(users) == 3, f"{net}: {users} (collector, 10k to 3V3D, Seed pin): no +-12 V path into the pin")
# (5) the faceplate's logic: no 74HC pin on a jack tip or op-amp output net
tips = {tip for _, _, tip, _ in circuit.JACKS}
logic_nets = {v for u in ("U1", "U9", "U10", "U11") for v in FB[u].nets.values()}
ck.check("H.faceplate_logic_off_the_jacks", not (logic_nets & tips),
         f"74HC nets on a jack tip: {sorted(logic_nets & tips)}")
# (6) one bus rail missing
gnd_inp = sorted(f"{u}.{circuit.SECTION[s][2]}" for u, p in MB.items() if p.kind == "TL074" for s in (1, 2, 3, 4)
                 if p.nets.get(circuit.SECTION[s][2]) == "GND")
for c, iq, worst in (("typ", TL_IQ_TYP, False), ("max", TL_IQ_MAX, True)):
    # the DC/DC then sees one rail plus a diode drop: below its range, its output falls in proportion
    v_half = V_RAIL - 2 * vf(0.05, worst)               # live rail after its diode, dead node a diode the wrong way
    v5 = 5.0 * v_half / 24.0
    i_dc = 0.5 * mods[c]["dcdc"]                         # estimate: about half the output voltage, half the power
    i_ret = (n_amps + BREAKOUT_OPAMPS) * iq + i_dc
    # (a) the missing rail at 0 V: the B5819W of that rail clamps the node at about VF the wrong side of GND
    v_node = vf(i_ret, worst)
    lim = TL_IN_BEYOND_OLD if worst else TL_IN_BEYOND_NEW
    ck.within(f"H.rail_at_0V.{c}", v_node, None, lim, " V",
              f"node held by D2 / D3 at {v_node:.2f} V beyond GND carrying {i_ret * 1e3:.0f} mA; TL074 inputs on GND "
              f"then sit that far beyond the dead rail (abs max {TL_IN_BEYOND_OLD} V old die, {TL_IN_BEYOND_NEW} V new)")
    ck.within(f"H.rail_missing_Seed_VIN.{c}", v5, None, SEED_VIN_MIN, " V",
              f"DC/DC at about {v_half:.1f} V in: {v5:.2f} V out, under the Seed's {SEED_VIN_MIN} V: the module stays "
              f"off rather than half-running (the DC/DC's input stays above its {DCDC_SURGE_MIN} V)")
    # (b) the missing rail open: the supply current returns through the TL074 inputs tied to GND
    per_pin = i_ret / len(gnd_inp)
    ck.within(f"H.rail_open_input_clamps.{c}", per_pin, None, TL_IIN_MAX, " A",
              f"{n_amps} + {BREAKOUT_OPAMPS} op-amps' IQ and ~{i_dc * 1e3:.0f} mA of DC/DC current return through "
              f"the clamp diodes of {len(gnd_inp)} grounded IN+ pins ({', '.join(gnd_inp)}); the breakout's own "
              f"op-amps share some of it (not counted)")
print("    (info) power-up: the DC/DC and the Seed's regulators start after the +-12 V; during that time the cases "
      "above (Seed unpowered) apply")

# ======================================================================== I. ratings
print("--- I. capacitor ratings")
for r in (r for r in re.findall(r"\| \d+ \| (Capacitor [^|]+) \|", BOM_MD)):
    mv = re.search(r"(\d+) V\b", r)
    ck.check(f"I.BOM_cap_voltage.{r[:28]}", mv is not None and float(mv.group(1)) >= 1.5 * V_RAIL * (1 + BUS_TOL),
             f"'{r}': expected >= {1.5 * V_RAIL * (1 + BUS_TOL):.0f} V (1.5 x a +5 % rail)")
LIB_V = {"FG28X7R1H104KNT00": 50, "FG28C0G1H102JNT00": 50, "SR305C105KAR": 50}   # TDK '1H' = 50 V; AVX SR30 '5' = 50 V
devs = collections.Counter()
for bk, parts in (("main", MB), ("face", FB)):
    for ref, p in parts.items():
        if p.kind == "C":
            devs[R.device(bk, ref).get("Manufacturer Part")] += 1
for mpn, n in sorted(devs.items()):
    ck.check(f"I.export_cap_device.{mpn}", mpn in LIB_V and LIB_V[mpn] >= 1.5 * V_RAIL * (1 + BUS_TOL),
             f"{n} capacitors placed from {mpn}: {LIB_V.get(mpn, 'unknown')} V")
for name, rated in BREAKOUT_CAP_V.items():
    ck.check(f"I.breakout_cap.{name}", rated >= 1.5 * BREAKOUT_CAP_ACROSS[name] * (1 + BUS_TOL),
             f"{rated:.0f} V across up to {BREAKOUT_CAP_ACROSS[name] * (1 + BUS_TOL):.1f} V")
ck.done()
