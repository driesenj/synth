"""Power group: how Plaitsy gets its power, what it draws, and what happens
when a rail is late, missing or reversed.

Plaitsy has no power header of its own: the Eurorack cable plugs into J2 on
Rob Heel's seed_power_opamps breakout (U2), which protects both rails with a
B5819W, feeds the Daisy Seed's VIN from an isolated Mornsun B2405S-1WR2
(24 V in: +12 V to -12 V, 5 V out) and hands +-12 V to Plaitsy's main board
on its J1 / J3 pins. The breakout's facts below were traced from its Gerbers
(rob-scape/daisy-seed-breakout-boards, daisy-seed-dcdc-opamps, 2025-08-29) by
rasterising both copper layers and following the copper through the drills;
they are constants here, the tests do not read any download.

What it checks
  A. Power entry: J2 against the Doepfer A-100 10-pin pinout (pin 1 square pad
     + RED STRIPE silk, -12 V / GND / +12 V rows), its shroud, the cable line
     in the BOM; the breakout's J1 / J3 / J4 pins in circuit.py and on the
     routed main board against the traced breakout copper and its hole
     positions; D2 / D3 orientation, conduction and blocking, every way a
     10- or 16-pin socket fits on the unshrouded 2x5; B5819W current and
     reverse-voltage ratings.
  B. The DC/DC: B2405S-1WR2 input range against +12 V - (-12 V) minus two
     B5819W drops with the bus at +-5 %; the 5 V it then gives the Seed.
  C. The 5 V budget: the Seed (measured, and with the STM32H750's max run
     current at the clock firmware/src/main.cc sets), Plaitsy's 3V3D loads
     (16 LED lines with Tayda A-8599's VF, button LEDs, 595s, probe)
     and 3V3A loads (pots, bias dividers, mux) through the Seed's regulators,
     against the DC/DC's 200 mA, its minimum load and capacitive load, and the
     Seed's TPS6217x (3V3D) / LP2985 (3V3A) limits; GPIO and 595 currents;
     the V/OCT clamp current pushed into 3V3A against the rail's own load.
  D. The +-12 V budget, typical and worst: Plaitsy's two TL074, the
     breakout's two TL074CPWR and their loads, the DC/DC input; whether any
     doc states it.
  E. Rails at the TL074 pins (diode + track drop) and the output range the
     stages need.
  F. Decoupling: C31-C34 at the TL074 supply pins (straight distance and
     track path on the routed MB), C8 / C9 / C10 at U1 / U9 / U10 pin 16 on
     the routed FB (path to pin 16 and the loop through pin 8).
  G. Power copper: track widths (design.md: 0.6 mm), resistance and drop on
     the path to every load; 3V3A_F / GND_F reaching every pot and mux pin;
     GND_F and GND_D_F apart on the FB and both on the MB's one GND with the
     Seed's AGND / DGND and the breakout's ground pins; header-pin currents.
  H. Ratings: capacitor voltages (BOM text and the breakout's parts), TL074
     supply abs max, BAT85 VR, 74HC VCC range at 3.3 V.
  I. Sequencing and missing rails: the power-up window (+-12 V up, 3V3A and
     3V3D still 0 V), -12 V missing, +12 V missing, power-down: injected
     current per ADC pin and in total against the STM32H750's limits, VDDA
     against VDD (the STM32's power-sequence rule), the clamp into 3V3A.

Run from plaits/hardware/tests:  python test_power.py
Read only: imports circuit.py / copper_audit.py through the harness, opens the
routed export and the docs; writes nothing.
"""
import csv
import heapq
import math
import os
import re

import harness

ck = harness.Checks("power")
circuit = harness.load("circuit")
ca = harness.load("copper_audit")

# =================================================================== datasheet / standard constants
# --- Doepfer A-100 bus (doepfer.de/a100_man/a100t_e.htm, image a100b_e.gif "bus connectors of A-100 modules",
#     fetched 2026-11-12). 16 pin: rows from the red stripe: -12V, GND, GND, GND, +12V, +5V, CV, Gate, i.e.
#     pins 1-2 -12 V, 3-8 GND, 9-10 +12 V, 11-12 +5 V, 13-14 CV, 15-16 Gate. The 10-pin version is the first five
#     rows (1-2 -12 V, 3-8 GND, 9-10 +12 V). Doepfer gives no voltage tolerance: +-5 % ASSUMED (brief's rule).
DOEPFER16 = {1: "-12V", 2: "-12V", 3: "GND", 4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND",
             9: "+12V", 10: "+12V", 11: "+5V", 12: "+5V", 13: "CV", 14: "CV", 15: "GATE", 16: "GATE"}
DOEPFER10 = {n: DOEPFER16[n] for n in range(1, 11)}
BUS_V, BUS_TOL = 12.0, 0.05
# Doepfer's same page: "it's not allowed to use bus boards with polarized pin headers"; the red stripe to the
# -12 V imprint "under all conditions" -- the bus side is unkeyed by Doepfer's own rule, so only the module
# header can key the cable.

# --- Breakout seed_power_opamps (Rob Heel), BOM_seed_power_opamps_2025-08-29.csv and the Gerbers of that date.
# J2: "HDR-M-2.54_2x5", LCSC C178292 = Amphenol 67997-210HLF (LCSC page title, fetched by the Marblesy session):
# BergStik II double-row straight header, UNSHROUDED (no box, no key).
BREAKOUT_J2_PART = "Amphenol 67997-210HLF (BergStik, unshrouded 2x5)"
BREAKOUT_J2_SHROUDED = False
# Gerber_BottomSilkscreenLayer: J2's outline is a plain 2-column rectangle (no box/notch drawn), the text
# "RED STRIPE" sits along the board edge at pin 1's end; pin 1 is the square pad (Gerber_TopLayer flash
# MACRO1 1.5748 square at X6.085 Y-14.054, the other nine round). J2, U3, C9, C18 are bottom-side parts.
BREAKOUT_J2_PIN1_SQUARE, BREAKOUT_J2_STRIPE_AT_PIN1 = True, True
# J2 pin -> what its copper reaches (Gerber trace, both layers + PTH/vias, 25 px/mm raster):
#   pins 1, 2 -> D3 cathode only;  pins 3..8 -> the GND pour;  pins 9, 10 -> D2 anode only.
BREAKOUT_J2 = {1: "D3_K", 2: "D3_K", 3: "GND", 4: "GND", 5: "GND", 6: "GND", 7: "GND", 8: "GND",
               9: "D2_A", 10: "D2_A"}
# Diodes (BOM: D2, D3 B5819W, LCSC C8598 CJ). Silk symbol (Gerber_TopSilkscreenLayer): D2 bar towards the
# circuit side, D3 bar towards J2 -> D2: A = J2 9-10, K = the breakout's +12 V net; D3: K = J2 1-2, A = -12 V net.
BREAKOUT_DIODES = {"D2": ("BUS_P", "P12"), "D3": ("N12", "BUS_N")}      # ref: (anode net, cathode net)
# Breakout nets (traced): P12 = D2 K, C9 +, C20, C24, L1 -> U3 pin 2 (+Vin), U2/U5 pin 4, J3 pins 2-4.
#                         N12 = D3 A, C18 -, C23, C24, L2 -> U3 pin 1 (-Vin / input GND), U2/U5 pin 11, J1 pins 2-4.
#                         GND = J2 3-8, J1-1, J3-1, J4-2, J4-4, J5-2, J5-4, Seed 20, Seed 40, U3 pin 3 (0V out).
#                         5V  = U3 pin 4 (+Vo), C7, C21, Seed 39 (VIN).    Seed 21 (3V3A): alone on the breakout.
BREAKOUT_PIN_NETS = {"J1-1": "GND", "J1-2": "N12", "J1-3": "N12", "J1-4": "N12",
                     "J3-1": "GND", "J3-2": "P12", "J3-3": "P12", "J3-4": "P12",
                     "J4-1": "OUT1", "J4-2": "GND", "J4-3": "OUT2", "J4-4": "GND",
                     "J5-1": "IN1", "J5-2": "GND", "J5-3": "IN2", "J5-4": "GND",
                     "20": "GND", "40": "GND", "39": "5V", "21": "3V3A"}
# Drill positions along the two pin rows (Drill_PTH_Through.DRL, mm along the board, Gerber x): the J1 / J3
# 1x4 at 24.13..31.75 (0.889 mm), the Seed rows at 36.83..85.09 (1.2 mm), J4 / J5 at 87.63..95.25 (0.889 mm).
# J1-1 / J3-1 (GND) are the holes nearest the Seed (31.75); J4-4 / J5-4 the ones nearest it at the USB end.
BREAKOUT_ROW_X = {"J1-4": 24.13, "J1-3": 26.67, "J1-2": 29.21, "J1-1": 31.75, "20": 36.83, "1": 85.09,
                  "J5-4": 87.63, "J5-3": 90.17, "J5-2": 92.71, "J5-1": 95.25}
BREAKOUT_ROW_PITCH = 15.24          # the two rows (Gerber y -1.778 / -17.018)
# Breakout capacitors (BOM): C9 / C18 100 uF 50 V (LCSC C2749, Chengx KM107M050F12RR0VH2FP0, 8x12, 105 C);
# C7 / C20 / C21 / C23 / C24 10 uF Samsung CL31A106KBHNNNE (rated-voltage code B = 50 V, LCSC C13585 datasheet
# "RATED VOLTAGE CODE ... B = 50V"); C24 sits across P12 / N12 (24 V); C7 / C21 on 5 V.
BREAKOUT_CAPS = {"C9": (100e-6, 50.0, ("P12", "GND")), "C18": (100e-6, 50.0, ("GND", "N12")),
                 "C20": (10e-6, 50.0, ("P12", "GND")), "C23": (10e-6, 50.0, ("GND", "N12")),
                 "C24": (10e-6, 50.0, ("P12", "N12")), "C7": (10e-6, 50.0, ("5V", "GND")),
                 "C21": (10e-6, 50.0, ("5V", "GND"))}
# L1 / L2: TDK MLZ1608A2R2WT000 (LCSC C76797 datasheet): 2.2 uH, DC resistance 0.25 ohm (max?), rated current
# 500 mA. The 0.25 ohm column is read from the table row; taken as the max.
L_DCR, L_IRATED = 0.25, 0.5
# Breakout op-amps: 2 x TL074CPWR (BOM; its "Name" column says TL084CPWR, the manufacturer-part column TL074CPWR:
# same supply current either way). One quad holds the two AOUT stages, the other the AIN stages (J5, unused).
BREAKOUT_TL074 = 2

# --- CJ B5819W (LCSC C8598, JSCJ datasheet rev D, Mar 2015), single diode, Ta = 25 C:
#     VRRM / VRM 40 V, VR(RMS) 28 V, IO 1 A, IFSM 9 A (8.3 ms), Pd 500 mW, VF max 0.60 V at 1 A, 0.90 V at 3 A,
#     IR max 1 mA at 40 V. Typical forward curve (Fig. "Forward Characteristics", 25 C, read off the log plot):
#     0.31 V at 0.1 A, 0.40 V at 0.5 A, 0.47 V at 1 A; 100 C curve about 0.09 V lower. Below 0.1 A not plotted:
#     extrapolated at 70 mV/decade (Schottky, n ~ 1.1) -- approximate. Max below 1 A: typ + 0.13 V (the 1 A gap
#     between max 0.60 and typ 0.47) -- ASSUMED, the datasheet gives max only at 1 A and 3 A.
D5819W_VRRM, D5819W_IO, D5819W_IFSM = 40.0, 1.0, 9.0


def vf_b5819w(i, corner="typ"):
    """B5819W forward voltage at i (A): 'typ', 'max' (typ + 0.13 V) or 'min' (100 C curve)."""
    i = max(i, 1e-4)
    if i <= 0.1:
        v = 0.31 + 0.07 * math.log10(i / 0.1)
    elif i <= 1.0:
        v = 0.31 + 0.16 * math.log10(i / 0.1)
    else:
        v = 0.47 + 0.43 * math.log10(i)
    return v + {"typ": 0.0, "max": 0.13, "min": -0.09}[corner]


# --- Mornsun B2405S-1WR2 (B_S-1WR2 & B_D-1WR2 series datasheet 2024.09.09-B/4):
#     input 24 V nominal, range 21.6-26.4 V (selection guide); output 5 V, 200 mA max / 20 mA min (the 10 %
#     minimum load, "Design Reference 3"); full-load efficiency 76 % min / 80 % typ; input current at 24 V:
#     57 mA typ full load / 17 mA typ, 30 mA max no load (that 57 mA implies 73 %, below the 76 % "min": the
#     datasheet disagrees with itself, the lower figure is the worst case here); surge -0.7 .. 30 V for 1 s;
#     capacitive load 220 uF max; line regulation +-1.2 % per 1 % input change (5 V output); load regulation
#     12 % typ for 10-100 % load (5 V output); short-circuit protection 1 s max for B24xxS (not continuous).
#     Start-up time: not given in the datasheet (not confirmed).
DCDC_VIN_NOM, DCDC_VIN_MIN, DCDC_VIN_MAX, DCDC_SURGE = 24.0, 21.6, 26.4, 30.0
DCDC_VOUT, DCDC_IOUT_MAX, DCDC_IOUT_MIN = 5.0, 0.200, 0.020
DCDC_ETA_TYP, DCDC_ETA_MIN, DCDC_ETA_WORST = 0.80, 0.76, 0.73
DCDC_INL_TYP, DCDC_INL_MAX = 0.017, 0.030
DCDC_LINE_REG = 1.2               # % output per % input
DCDC_CLOAD_MAX = 220e-6

# --- Daisy Seed (datasheet v1.0.5, Table 1): VIN 4 .. 17 V; GPIO 0 .. +5 V (5 V tolerant except pins 24, 25,
#     28, 29, 30: 3.3 V tolerant). Schematic 1 of 4 (rendered from the PDF): VIN -> NSR1020MW2T5G Schottky ->
#     UNREGULATED_VCC; 3V3_D from a TPS6217x buck (47k / 15k divider: 0.8 V x 4.13 = 3.31 V); 3V3_A from an
#     LP2985 3.3 V LDO fed from UNREGULATED_VCC through R1 5.1 ohm, then ferrite FB1; R6 (3V3_D -> 3V3_A) DNI.
#     No current consumption in the datasheet (none of its 21 pages gives an mA figure). [Verify pass 2026-11-13:
#     the regulators confirmed from TI's sheets:] the buck's 8-pin pinout + 47k / 15k divider = the adjustable
#     TPS62170 (SLVSAT8E, May 2017): VIN 3-17 V, 0.5 A, VUVLO 2.6 / 2.7 / 2.82 V (min / typ / max, 180 mV
#     hysteresis), Figure 12 (VOUT 3.3 V, 2.2 uH) about 91-93 % from VIN 5 V at 0.1-0.5 A (typical only; 90 % typ
#     / 85 % worst kept as the allowance for the Seed's own inductor and temperature, ASSUMED). LP2985 (SLVS522S,
#     May 2025): 150 mA; dropout 280 / 350 mV typ / max at 150 mA, 120 / 150 mV at 50 mA (25 C); output +-2.5 %
#     (legacy chip, 1-150 mA). NSR1020 VF about 0.4 V at 0.1-0.2 A (onsemi sheet not read: not confirmed).
#     3V3A on schematic rev 5 also feeds the STM32's VDDA + VREF+ (sheet 2) and the WM8731's AVDD + HPVDD (sheet 4):
#     Wolfson WM8731 PD rev 3.4 p.10, record + playback, external MCLK, typical: AVDD 13.1 mA, HPVDD 1.7 mA. Later
#     Seeds (rev 7 / Seed 2 DFM, PCM3060 codec) are not in this datasheet: their 3V3A load is not known here.
#     3V3A capacitance on rev 5: C1 22 uF (after FB1), C7 2.2 uF + C4 10 nF (LDO), C20 10 uF + C19 10 uF + C5 / C53
#     100 nF (VDDA / VREF+), C8 10 uF + C10 100 nF (codec AVDD): about 54 uF.
SEED_WM8731_3V3A_TYP = 13.1e-3 + 1.7e-3
SEED_3V3A_CAP_REV5 = 22e-6 + 2.2e-6 + 10e-9 + 10e-6 + 10e-6 + 0.2e-6 + 10e-6 + 0.1e-6
SEED_VIN_MIN, SEED_VIN_MAX = 4.0, 17.0
SEED_3V3D_MAX, SEED_3V3A_MAX = 0.500, 0.150
SEED_SCHOTTKY_VF = 0.40
BUCK_ETA_TYP, BUCK_ETA_MIN = 0.90, 0.85
BUCK_UVLO = 2.7
LDO_R_IN = 5.1
# Seed supply current, measured (community.daisy.audio/t/power-consumption/4521, "tele_player", 2025-02-20,
# USB power meter, 5 V): 140 mA at 480 MHz running two oscillators, 120 mA at 400 MHz. Taken as typical for
# Plaits at 480 MHz (not measured on Plaitsy). NOT a datasheet figure: Electrosmith publishes none.
SEED_I_TYP = 0.140
# STM32H750 DS12556 Rev 7, Table 127 (rev V silicon, Run mode, CoreMark from ITCM, LDO on, all I/O analog, "the
# cache has no influence"): 480 MHz VOS0, all peripherals disabled: IDD 148 mA typ, 226 mA max at Tj 25 C, 307 mA
# max at Tj 85 C; all peripherals enabled: 226 typ / 348 / 439 mA; 400 MHz VOS1, peripherals disabled: 110 typ.
# The worst Seed = the measured typical + (max - typ) of the MCU (peripherals-disabled row: the Seed enables only a
# few), fed through the buck. The max is a property of the part (a characterization maximum), so it can coincide
# with any display state; the firmware's clock is read from main.cc below.
MCU_IDD_TYP, MCU_IDD_MAX25, MCU_IDD_MAX85 = 0.148, 0.226, 0.307
MCU_IDD_TYP_400 = 0.110
# DS12556 Table 19 (abs max): VIN on FT_xxx pins VSS - 0.3 .. min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V; on TT_xx
# pins VSS - 0.3 .. 4.0 V. Table 20: IINJ(PIN) on FT / TT pins -5 / +0 mA (note 3: "Positive injection is not
# possible on these I/Os and does not occur for input voltages lower than the specified maximum value");
# PA4, PA5 -0 / 0 mA; sum of all |IINJ| 25 mA. IIO 20 mA per pin; sum sourced 140 mA.
# Section 3 (power supplies, p. 25): "When VDD is below 1 V, other power supplies (VDDA, ...) must remain
# below VDD + 300 mV"; during power-down VDD may be lower only if the energy to the MCU stays below 1 mJ.
MCU_VIN_ABS_MAX_UNPOWERED = 4.0                 # min(VDD..) = 0 -> 0 + 4.0 V; TT pins 4.0 V absolute
MCU_IINJ_NEG, MCU_IINJ_SUM, MCU_IIO = 5e-3, 25e-3, 20e-3
MCU_SEQ_MARGIN = 0.3
MCU_SILICON_VF = 0.5            # an I/O's VSS diode conducting the injected current (approximate)
# Seed pin -> STM32 port (libDaisy v9 daisy_seed.h: A0 PC0, A1 PA3, A2 PB1, A3 PA7, A4 PA6, A5 PC1, A6 PC4,
# A7 PA5, A8 PA4, A9 PA1, A10 PA0).
SEED_PORT = {"22": "PC0", "23": "PA3", "24": "PB1", "25": "PA7", "26": "PA6", "27": "PC1", "28": "PC4",
             "29": "PA5", "30": "PA4", "31": "PA1", "32": "PA0"}

# --- TI TL07x SLOS080 (as the stereo mixer's suite read it, rev W): IQ per amplifier 1.4 mA typ, 2.5 mA max
#     (TL07xC, +-15 V, 25 C, no load); supply abs max VCC+ - VCC- 36 V (+-18 V); VOM at RL 10k, +-15 V:
#     +-13.5 V typ, +-12 V min -> 1.5 V typ / 3 V worst headroom; VICR at +-15 V: -12 .. +15 V typ,
#     +-11 V min -> 4 V above VCC- worst. [Verify pass 2026-11-13, SLOS080W re-read:] section 5.8 (old die,
#     TL07xC / AC / BC, +-15 V) VCM -11 min / -12 typ; 5.3 recommended input voltage for "all other devices" (the
#     PDIP TL074ACN included) (VCC-) + 4 V .. (VCC+) + 0.1 V; section 5.7 (new die TL07xH) VCM (VCC-) + 1.5 ..
#     VCC+; Figure 5-26 "No Phase Reversal" (VS +-10 V, VIN = VOUT) is in 5.10, the TL07xH curves only: the sheet
#     promises nothing about phase reversal for the old die, and a TL074(A)C without H may be either die
#     (Table 9-1). Input clamp diodes to both rails "on all new die" (abs max note 2, 10 mA).
TL074_IQ_TYP, TL074_IQ_MAX = 1.4e-3, 2.5e-3
TL074_VSUP_ABS = 36.0
TL074_HEAD_TYP, TL074_HEAD_MIN = 1.5, 3.0
TL074_VICR_NEG = 4.0

# --- 74HC (TI SN74HC595 SCLS041, CD74HC4051 SCHS122): VCC 2 .. 6 V recommended; ICC max 8 uA (595) / 8 uA
#     (4051) at VCC 6 V, 25 C; 595 abs max: output current +-35 mA per pin, VCC or GND current +-70 mA.
#     VOH at VCC 4.5 V, IOH -6 mA: 3.98 V min, 4.30 V typ -> output resistance 87 ohm worst, 33 ohm typ there;
#     at 3.3 V not given: 120 ohm worst / 50 ohm typ ASSUMED (HC drive weakens at low VCC).
HC_VCC_MIN, HC_VCC_MAX = 2.0, 6.0
HC_ICC_MAX = 8e-6
HC595_IO_MAX, HC595_ICC_ABS = 35e-3, 70e-3
HC595_ROUT_TYP, HC595_ROUT_MAX = 50.0, 120.0
# --- LEDs. D1-D8 = Tayda SKU A-8599 "Bi-color LED Red/Green 3mm Common Cathode" (OEM, no datasheet; product page
#     re-read 2026-11-13, the same figures the bom group uses): "Forward Voltage Red: 1.8V - 2.2V", "Forward Voltage
#     Green: 2.8V - 3.0V", "Forward Current: 20mA"; no test current given for VF, read as at 20 mA. Typical = the
#     middle of each range. At the 0.3-3.5 mA these lines run at, an LED's VF is below its 20 mA value, so the 20 mA
#     minimum is no lower bound for the maximum current: VF at a few mA taken as the 20 mA minimum less 0.2 V
#     (ASSUMED, no curve published). [Verify pass 2026-11-13: was red 1.8 / 2.0 / 2.4, green 1.9 / 2.1 / 2.5
#     "assumed" -- an unsourced GaP-like green that disagreed with the part the BOM orders.]
#     The Thonk button LED (drawing PB01-109TL: GaAsP / GaP, no VF given): 1.8 / 2.0 V min / typ ASSUMED (unused max).
#     STM32 GPIO output resistance about 40 ohm at 3.3 V (DS12556 VOH 2.9 V at 8 mA): 0 for the max current.
LED_VF_LOW_I_DROP = 0.2
LED_VF_TAYDA = {"R": (1.8 - LED_VF_LOW_I_DROP, 2.0, 2.2), "G": (2.8 - LED_VF_LOW_I_DROP, 2.9, 3.0), "BTN": (1.8, 2.0, 3.2)}
#     [2026-11-14, the test report's M1 fix: bom.py names the Kingbright L-3WEGW instead. DSAA6458 V.18A at 25 C,
#     IF = 20 mA: red (GaAsP/GaP) typ 2.0 / max 2.5 V, green (GaP) typ 2.2 / max 2.5 V, +-0.1 V measurement; no
#     minimum given: typ - 0.1 - LED_VF_LOW_I_DROP (ASSUMED). The part bom.md's D1 line names is used.]
LED_VF_L3WEGW = {"R": (2.0 - 0.1 - LED_VF_LOW_I_DROP, 2.0, 2.5), "G": (2.2 - 0.1 - LED_VF_LOW_I_DROP, 2.2, 2.5),
                 "BTN": LED_VF_TAYDA["BTN"]}
_LED_LINE = next((ln for ln in harness.text("docs", "bom.md").splitlines() if "bicolour LED" in ln), "")
LED_PART = "Kingbright L-3WEGW" if "L-3WEGW" in _LED_LINE else "Tayda A-8599"
LED_VF = LED_VF_L3WEGW if "L-3WEGW" in _LED_LINE else LED_VF_TAYDA
GPIO_ROUT = 40.0
# --- NXP BAT85 (rev 05): VR 30 V; VF max 0.24 V at 0.1 mA, 0.32 V at 1 mA, 0.40 V at 10 mA, 0.80 V at 100 mA.
BAT85_VR = 30.0


def vf_bat85(i):
    """BAT85 max forward voltage at i (A), log-interpolated between the datasheet's max points."""
    pts = [(1e-4, 0.24), (1e-3, 0.32), (1e-2, 0.40), (1e-1, 0.80)]
    i = min(max(i, 1e-5), 0.1)
    for (i0, v0), (i1, v1) in zip(pts, pts[1:]):
        if i <= i1:
            return v0 + (v1 - v0) * math.log10(max(i, i0 * 0.1) / i0) / math.log10(i1 / i0)
    return pts[-1][1]


# --- Pots: Alpha 9 mm B10k, +-20 % track (Alpha / Thonk listing). Resistors 1 %.
POT_TOL, R_TOL = 0.20, 0.01
# --- Rails of the Seed's regulators: 3.3 V +-3 % ASSUMED for the load sums (TPS6217x / LP2985 accuracy).
V33, V33_TOL = 3.3, 0.03
# --- Eurorack loads on the breakout's outputs: Eurorack inputs >= 10k (worst), 100k typical; level +-5 V typ
#     ("Eurorack level", the breakout readme), +-10 V worst; the stage's own feedback >= 10k (the breakout's BOM
#     has only 100k, 10k and 1k resistors) -- ASSUMED, the breakout's schematic is not published as a file.
OUT_SERIES, EXT_LOAD_MIN, EXT_LOAD_TYP, FB_MIN = 1e3, 10e3, 100e3, 10e3
OUT_SWING_TYP, OUT_SWING_MAX = 5.0, 10.0
# --- Copper: 1 oz (35 um) outer layers, rho 1.72e-8 ohm m at 20 C (JLCPCB standard 2-layer).
CU_T, CU_RHO = 35e-6, 1.72e-8
# --- 2.54 mm female header contact rating: 1 A or more for any common part (ASSUMED, conservative).
HDR_I_MAX = 1.0
# --- Jack CV range the stages must survive: design.md claims +-12 V; Eurorack signals mostly within +-10 V.
CV_MAX = 12.0

# =================================================================== sources
DOC = harness.text("docs", "design.md")
README = harness.text("README.md")
BOM_MD = harness.text("docs", "bom.md")
MAIN_CC = harness.text("firmware", "src", "main.cc")
UI_CC = harness.text("firmware", "src", "plaits", "ui.cc")
# libDaisy: DaisySeed::Init(bool boost) -- boost = true runs the CPU at 480 MHz, false at 400 MHz
_boost = re.search(r"\bhw\.Init\(\s*(true|false)?\s*\)", MAIN_CC)
FW_BOOST = bool(_boost) and _boost.group(1) == "true"
BOM_CSV = list(csv.DictReader(open(os.path.join(harness.BOM, "plaits-bom.csv"), encoding="utf-8")))
MB = {p.ref: p for p in circuit.main_board_parts()}
FB = {p.ref: p for p in circuit.faceplate_parts()}
R_ = harness.routed()
mb, fb = R_.main, R_.face


def bom_line(ref):
    for row in BOM_CSV:
        refs = [r.strip().split(": ")[-1] for r in re.split(r",|;", row["Refs"])]
        if ref in refs:
            return row["Part"]
    return ""


def par(*rs):
    return 1 / sum(1 / r for r in rs)


# =================================================================== A. power entry
print("--- A. power entry: the breakout's J2, its diodes, its J1 / J3 pins")
for n in range(1, 11):
    std = DOEPFER10[n]
    got = BREAKOUT_J2[n]
    exp = {"-12V": "D3_K", "GND": "GND", "+12V": "D2_A"}[std]
    ck.check(f"A.J2_pin.{n} ({std})", got == exp, f"Doepfer pin {n} = {std} -> expected {exp}, traced {got}")
ck.check("A.J2_pin1_marked", BREAKOUT_J2_PIN1_SQUARE and BREAKOUT_J2_STRIPE_AT_PIN1,
         "square pad 1 and 'RED STRIPE' silk at pin 1's end (bottom silk)")
ck.check("A.J2_shrouded (keys the cable, stops row offsets)", BREAKOUT_J2_SHROUDED,
         f"J2 is {BREAKOUT_J2_PART}: a 10-pin socket fits reversed or one row off, a 16-pin socket at 4 offsets "
         f"(see A.cable_*)")
# the cable line in the BOM: the header is a 10-pin 2x5, so the cable is a 10-to-16-pin Eurorack cable
cable = next((r for r in BOM_CSV if "power cable" in r["Part"].lower()), None)
txt = (cable["Part"] + " " + cable["Note"]) if cable else ""
ck.check("A.BOM_cable_names_10_pin", bool(cable) and re.search(r"10[- ]to[- ]16|10[- ]pin", txt) is not None
         and "or 16" not in txt, f"BOM: '{txt}' (J2 is a 2x5 = 10-pin header: a 10-to-16-pin cable)")

# circuit.py's breakout pins against the traced breakout copper (power and ground pins)
want = {"GND": "GND", "N12": "-12V", "P12": "+12V", "5V": None, "3V3A": "3V3A", "OUT1": "OUT", "OUT2": "AUX",
        "IN1": None, "IN2": None}
for pin, bnet in BREAKOUT_PIN_NETS.items():
    exp = want[bnet]
    got = circuit.SEED.get(pin, (None, None))[1]
    rgot = mb.parts["U2"]["nets"].get(pin)
    ck.check(f"A.breakout_pin.{pin} ({bnet})", got == exp and rgot == exp,
             f"breakout copper {bnet} -> expected {exp}; circuit.py {got}, routed MB {rgot}")
# hole positions: the routed footprint's pads against the breakout's drill file (one common offset)
pads = mb.parts["U2"]["pads"]
off = [pads[k].y - BREAKOUT_ROW_X[k] for k in BREAKOUT_ROW_X]
ck.check("A.breakout_holes_match_footprint (J1 / Seed / J5 row)", max(off) - min(off) < 0.05,
         f"footprint y - drill x per pin: {min(off):.3f} .. {max(off):.3f} mm")
dx = abs(pads["J1-1"].x - pads["J3-1"].x)
ck.close("A.breakout_row_spacing", dx, BREAKOUT_ROW_PITCH, 0.05, " mm")
# J1-1 / J3-1 are GND on the breakout and on circuit.py: a cable or a breakout turned round end-for-end would
# put -12 / +12 on Plaitsy's GND; the footprint's square pads mark pin 1 of each header on the board
for p1 in ("J1-1", "J3-1", "J4-1", "J5-1", "1", "40"):
    ck.check(f"A.footprint_square_pad.{p1}", pads[p1].shape == "RECT", f"pad shape {pads[p1].shape}")

# the diodes: conduction with a correct cable, blocking with a reversed one
print("    D2: anode J2 9-10, cathode +12 V;  D3: cathode J2 1-2, anode -12 V (silk bar, traced copper)")


def j2_bus(socket, offset, rev):
    """{J2 pin: bus signal} for a socket of 10 or 16 contacts on the 2x5 header, shifted by `offset` rows and
    turned round or not. Socket contact s sits on header pin s - 2*offset (stripe = contact 1)."""
    pins = {}
    n = socket
    for s in range(1, n + 1):
        sig = DOEPFER16[s] if n == 16 else DOEPFER10[s]
        # turned round: contact s lands where contact n+1-s would, mirrored across the two columns as well
        pos = (n + 1 - s) if rev else s
        h = pos - 2 * offset
        if 1 <= h <= 10:
            pins[h] = sig
    return pins


SIGV = {"-12V": (-BUS_V, -BUS_V), "GND": (0.0, 0.0), "+12V": (BUS_V, BUS_V), "+5V": (5.0, 5.0),
        "CV": (-10.0, 10.0), "GATE": (0.0, 10.0)}


def circuit_rails(pins):
    """(P12 range, N12 range, shorted bus signals onto GND) for a socket placement. D2 passes the most positive
    voltage on J2 9-10 into P12 (minus VF), D3 the most negative on J2 1-2 into N12."""
    a = [SIGV[pins[h]] for h in (9, 10) if h in pins]
    k = [SIGV[pins[h]] for h in (1, 2) if h in pins]
    p12 = max((v[1] for v in a), default=0.0) - 0.3
    n12 = min((v[0] for v in k), default=0.0) + 0.3
    shorts = sorted({pins[h] for h in range(3, 9) if h in pins and pins[h] != "GND"})
    return max(p12, 0.0), min(n12, 0.0), shorts


placements = []
for socket in (10, 16):
    for rev in (False, True):
        for off in range(-(socket // 2) + 1, 5):
            pins = j2_bus(socket, off, rev)
            if len(pins) < 2 or (socket == 16 and len(pins) < 10):     # a 16-pin socket covers all ten pins
                continue
            if socket == 10 and len(pins) < 8:                          # at most one row overhangs
                continue
            placements.append((socket, rev, off, pins))
ok_rev, info = True, []
for socket, rev, off, pins in placements:
    p12, n12, shorts = circuit_rails(pins)
    correct = (socket == 10 and off == 0 and not rev) or (socket == 16 and off == 0 and not rev)
    if correct:
        ck.check(f"A.cable_correct_{socket}_pin_powers_both_rails", p12 > 11 and n12 < -11,
                 f"P12 {p12:+.1f} V, N12 {n12:+.1f} V")
        continue
    # never a reversed rail on the circuit side (D2 only passes positive, D3 only negative)
    ok_rev &= p12 >= 0.0 and n12 <= 0.0
    if p12 > 0 or n12 < 0 or shorts:
        info.append(f"{socket}-pin {'turned' if rev else 'straight'} {off:+d} row(s): P12 {p12:+.1f} V, "
                    f"N12 {n12:+.1f} V, bus {shorts or 'nothing'} into GND")
for s in info:
    print("    (info) " + s)
ck.check("A.cable_misplaced_never_reverses_a_rail", ok_rev,
         f"{len(placements) - 2} wrong placements of a 10- or 16-pin socket on the unshrouded J2")
half = []
shorted = []
for socket, rev, off, pins in placements:
    p12, n12, shorts = circuit_rails(pins)
    if (socket, rev, off) in ((10, False, 0), (16, False, 0)):
        continue
    if (p12 > 0) != (n12 < 0):
        half.append(f"{socket}-pin {'turned' if rev else 'straight'} {off:+d}: P12 {p12:+.1f} / N12 {n12:+.1f} V")
    if shorts:
        shorted.append(f"{socket}-pin {'turned' if rev else 'straight'} {off:+d}: {'/'.join(shorts)}")
# one rail only: the TL074s and the DC/DC on a single supply (section I covers what that does)
ck.check("A.cable_misplaced_no_half_power", not half, "; ".join(half))
# a bus rail into the breakout's GND: the PSU's short-circuit current runs through J2 pins 3-8 and the GND
# plane until the PSU folds back -- the hazard a shrouded header removes
ck.check("A.cable_misplaced_no_bus_short", not shorted, f"{len(shorted)} placements: " + "; ".join(shorted))

# =================================================================== C. the 5 V budget
print("--- C. 5 V budget: the Seed and Plaitsy's 3V3 loads through the DC/DC")


def led_lines(v33, corner):
    """Current of the 16 LED lines and the two button LEDs at a 3V3D of v33 (A each)."""
    lines = []
    for ref, colour in circuit.LED_LINES:
        vf = LED_VF[colour][0 if corner == "max" else 1]
        rr = 470 * (1 - R_TOL) if corner == "max" else 470
        ro = 0.0 if corner == "max" else HC595_ROUT_TYP
        lines.append(max(v33 - vf, 0) / (rr + ro))
    btn = []
    for r in ("R60", "R61"):
        vf = LED_VF["BTN"][0 if corner == "max" else 1]
        rr = harness.ohms(MB[r].value) * (1 - R_TOL if corner == "max" else 1)
        btn.append(max(v33 - vf, 0) / (rr + (0 if corner == "max" else GPIO_ROUT)))
    return lines, btn


def loads_3v3(corner):
    """(3V3D A, 3V3A A, detail) of Plaitsy's own loads. typ: two LED lines lit (one model, yellow = both),
    one button LED; max: all sixteen lines and both button LEDs on (every display state), +3 % rail."""
    v = V33 * (1 + V33_TOL) if corner == "max" else V33
    lines, btn = led_lines(v, corner)
    n_on = 16 if corner == "max" else 2
    i_led = sum(sorted(lines, reverse=True)[:n_on]) if corner == "max" else sum(lines[:1]) + sum(lines[8:9])
    i_btn = sum(btn) if corner == "max" else btn[0]
    i_595 = 2 * HC_ICC_MAX if corner == "max" else 0.0
    # probe: D14 high -> 10k -> the switch lug -> (unpatched) the tip -> 100k -> the stage's summing node at BIAS_A
    bias_a = V33 * 12 / 27
    i_probe = 5 * (v - bias_a) / (10e3 + 100e3)
    i_3v3d = i_led + i_btn + i_595 + i_probe
    pot = 10e3 * (1 - POT_TOL if corner == "max" else 1)
    i_pots = 7 * v / pot
    i_bias = v / (27e3 * (1 - R_TOL if corner == "max" else 1)) + v / (28e3 * (1 - R_TOL if corner == "max" else 1))
    i_mux = HC_ICC_MAX if corner == "max" else 0.0
    i_3v3a = i_pots + i_bias + i_mux
    return i_3v3d, i_3v3a, dict(led=i_led, btn=i_btn, probe=i_probe, pots=i_pots, bias=i_bias)


# the Table 127 row for the clock the firmware sets (main.cc's hw.Init(boost)); the forum measured 140 mA at 480 MHz
# and 120 mA at 400 MHz. [Verify pass: the budget used the 480 MHz row without checking the firmware runs there.]
if FW_BOOST:
    SEED_BASE, MCU_TYP, MCU_MAX25, MCU_MAX85 = SEED_I_TYP, MCU_IDD_TYP, MCU_IDD_MAX25, MCU_IDD_MAX85
else:
    SEED_BASE, MCU_TYP, MCU_MAX25, MCU_MAX85 = 0.120, MCU_IDD_TYP_400, 0.168, 0.230
print(f"    firmware clock: {'480 MHz (hw.Init(true))' if FW_BOOST else '400 MHz'} -> Table 127 row "
      f"{MCU_TYP * 1e3:.0f} typ / {MCU_MAX25 * 1e3:.0f} max mA")


def seed_5v(corner, tj85=False):
    """Current the Seed draws from the DC/DC (A), with Plaitsy's loads through its regulators."""
    i_d, i_a, det = loads_3v3(corner)
    eta = BUCK_ETA_MIN if corner == "max" else BUCK_ETA_TYP
    v_unreg = DCDC_VOUT - SEED_SCHOTTKY_VF
    seed = SEED_BASE
    if corner == "max":
        extra = (MCU_MAX85 if tj85 else MCU_MAX25) - MCU_TYP
        seed += V33 * extra / (eta * v_unreg)
    i_buck = V33 * i_d / (eta * v_unreg)                # 3V3D loads through the buck
    i_ldo = i_a                                         # 3V3A loads through the LDO: same current
    return seed + i_buck + i_ldo, det, i_d, i_a


i5_typ, det_typ, d_typ, a_typ = seed_5v("typ")
i5_max, det_max, d_max, a_max = seed_5v("max")
i5_max85, *_ = seed_5v("max", tj85=True)
print(f"    3V3D typ {d_typ * 1e3:.1f} mA (LEDs {det_typ['led'] * 1e3:.1f}, button {det_typ['btn'] * 1e3:.1f}), "
      f"max {d_max * 1e3:.1f} mA (LEDs {det_max['led'] * 1e3:.1f}, buttons {det_max['btn'] * 1e3:.1f})")
print(f"    3V3A typ {a_typ * 1e3:.2f} mA (pots {det_typ['pots'] * 1e3:.2f}, bias {det_typ['bias'] * 1e3:.2f}), "
      f"max {a_max * 1e3:.2f} mA")
print(f"    5 V from the DC/DC: typ {i5_typ * 1e3:.0f} mA, worst {i5_max * 1e3:.0f} mA (MCU max at Tj 25 C), "
      f"{i5_max85 * 1e3:.0f} mA (Tj 85 C)")
ck.within("C.DCDC_load_typ <= 200 mA", i5_typ * 1e3, None, DCDC_IOUT_MAX * 1e3, " mA",
          "Seed 140 mA measured + Plaitsy's typical 3V3 loads")
all_yellow = "LED_COLOR_YELLOW" in UI_CC and "UI_MODE_DISPLAY_OCTAVE" in UI_CC
ck.within("C.DCDC_load_worst <= 200 mA", i5_max * 1e3, None, DCDC_IOUT_MAX * 1e3, " mA",
          f"the forum's {SEED_BASE * 1e3:.0f} mA Seed + the MCU's Tj 25 C max - typ (DS12556 Table 127), all 16 LED "
          f"lines + both button LEDs on ({'ui.cc lights all 8 LEDs yellow in UI_MODE_DISPLAY_OCTAVE at the top octave' if all_yellow else 'display state not found in ui.cc'}); "
          f"not stacked impossibles, but the 140 mA base is no datasheet figure: measure")
ck.within("C.DCDC_load_typ <= 80 % of rating (margin for an unmeasured Seed)", i5_typ / DCDC_IOUT_MAX * 100,
          None, 80, " %")
ck.within("C.DCDC_min_load (10 %)", i5_typ * 1e3, DCDC_IOUT_MIN * 1e3, None, " mA")
ck.within("C.3V3D_vs_TPS6217x_500mA", (d_max + MCU_MAX25 + 0.04) * 1e3, None, SEED_3V3D_MAX * 1e3, " mA",
          "Plaitsy's 3V3D max + the MCU's Tj 25 C max + 40 mA for the Seed's SDRAM / QSPI / codec (assumed)")
ck.within("C.3V3A_vs_LP2985_150mA", (a_max + 0.02) * 1e3, None, SEED_3V3A_MAX * 1e3, " mA",
          f"Plaitsy's 3V3A max + 20 mA for the Seed's own analog loads (rev 5: WM8731 AVDD + HPVDD "
          f"{SEED_WM8731_3V3A_TYP * 1e3:.1f} mA typ + VDDA; allowance)")
for r in ("R60", "R61"):
    i = led_lines(V33 * 1.03, "max")[1][0]
    ck.within(f"C.GPIO_button_LED.{r} <= 20 mA (IIO)", i * 1e3, None, MCU_IIO * 1e3, " mA")
lines_max = led_lines(V33 * 1.03, "max")[0]
for u, rng in (("U9", range(0, 8)), ("U10", range(8, 16))):
    tot = sum(lines_max[i] for i in rng)
    ck.within(f"C.{u}_VCC_current <= 70 mA abs max (8 outputs on)", tot * 1e3, None, HC595_ICC_ABS * 1e3, " mA")
    ck.within(f"C.{u}_per_output <= 35 mA", max(lines_max[i] for i in rng) * 1e3, None, HC595_IO_MAX * 1e3, " mA")
typ_led = [x * 1e3 for x in led_lines(V33, "typ")[0]]
m = re.search(r"about (\d+(?:\.\d+)?) mA per colour", DOC)
ck.check("C.design_md_LED_current_stated", m is not None, "LEDs paragraph")
if m:
    d = float(m.group(1))
    ck.check(f"C.design_md_LED_current 'about {d:g} mA' vs typical (within 20 %)",
             all(abs(x - d) <= 0.2 * d for x in typ_led),
             f"typ {min(typ_led):.2f} (green) .. {max(typ_led):.2f} (red) mA per line (470R, 595 ~50 ohm, {LED_PART} "
             f"VF typical red {LED_VF['R'][1]} / green {LED_VF['G'][1]} V at 20 mA; at the real current VF is a "
             f"little lower)")
c5 = sum(c[0] for c in BREAKOUT_CAPS.values() if "5V" in c[2]) + 10e-6 + 10e-6 + 10e-6 + 1e-6 + 0.1e-6
ck.within("C.DCDC_capacitive_load <= 220 uF", c5 * 1e6, None, DCDC_CLOAD_MAX * 1e6, " uF",
          "breakout C7 / C21 + the Seed's C3, C8, C21, C9, C30 (its schematic)")

# a 10-pin cable turned round on J2: both diodes must block (J2 1-2 then get +12 V, 9-10 get -12 V)
rev10 = j2_bus(10, 0, True)
p12r, n12r, sh = circuit_rails(rev10)
ck.check("A.cable_reversed_10_pin_both_diodes_block", p12r == 0.0 and n12r == 0.0 and not sh,
         f"J2 1-2 get {rev10[1]}, 9-10 get {rev10[9]}: D2 anode at -12 V, D3 cathode at +12 V -> "
         f"P12 {p12r:+.1f} V, N12 {n12r:+.1f} V, GND pins carry {sh or 'GND only'}")
# worst reverse voltage on a B5819W: a turned-round cable plugged while the circuit side still holds its charge
vr = 2 * BUS_V * (1 + BUS_TOL) - 0.3
ck.within("A.B5819W_reverse_voltage (turned cable, charged rail) < VRRM 40 V", vr, None, D5819W_VRRM, " V")


# =================================================================== D. the +-12 V budget (B needs it)
print("--- D. +-12 V budget (Plaitsy's TL074s, the breakout's TL074CPWRs, the DC/DC input)")
CH = {name: dict(rin=100e3, rf=harness.ohms(rf), bias=bias, u=u) for name, _, u, s, rf, cf, bias in circuit.CV_CHANNELS}
BIAS = {"BIAS_A": (15e3, 12e3), "BIAS_V": (13e3, 15e3)}          # (top to 3V3A, bottom to GND), circuit.py


def bias_v(net, v33a):
    top, bot = BIAS[net]
    return v33a * bot / (top + bot)


def stage_out(name, vin, v33a):
    """Ideal output of a CV stage (V) for a jack voltage vin and a 3V3A of v33a."""
    c = CH[name]
    vb = bias_v(c["bias"], v33a)
    return vb - c["rf"] / c["rin"] * (vin - vb)


def stage_load(name, v33a, cv=CV_MAX):
    """Worst DC output current of a CV stage (A) and the rail it comes from: the feedback resistor, plus the
    V/OCT clamp D21 / D22 through R44 when the output passes 3V3A + VF or GND - VF."""
    worst = (0.0, "+12V")
    for vin in (-cv, cv):
        vo = stage_out(name, vin, v33a)
        i = abs(vo - bias_v(CH[name]["bias"], v33a)) / CH[name]["rf"]
        if name == "VOCT":
            if vo > v33a + 0.3:
                i += (vo - v33a - vf_bat85(2e-3)) / 1e3
            elif vo < -0.3:
                i += (-vo - vf_bat85(2e-3)) / 1e3
        rail = "+12V" if vo > bias_v(CH[name]["bias"], v33a) else "-12V"
        worst = max(worst, (i, rail))
    return worst


loads = {n: stage_load(n, V33) for n in CH}
for n, (i, rl) in loads.items():
    print(f"    stage {n:7} worst DC load {i * 1e3:5.2f} mA from {rl}")
i_stage_p = sum(i for i, rl in loads.values() if rl == "+12V")
i_stage_n = sum(i for i, rl in loads.values() if rl == "-12V")
# the breakout's two output stages (OUT / AUX into the FB jacks and on into a module input)
i_out_typ = 2 * (OUT_SWING_TYP / (OUT_SERIES + EXT_LOAD_TYP) + OUT_SWING_TYP / 100e3)
i_out_max = 2 * (OUT_SWING_MAX / (OUT_SERIES + EXT_LOAD_MIN) + OUT_SWING_MAX / FB_MIN)
n_amps = 4 * (sum(1 for p in MB.values() if p.kind == "TL074") + BREAKOUT_TL074)
ck.check("D.amplifier_count (2 TL074 on the MB + 2 TL074CPWR on the breakout)", n_amps == 16, f"{n_amps}")


def dcdc_in(i5, vin, corner):
    """DC/DC input current (A) for a 5 V load i5 at an input of vin."""
    eta = DCDC_ETA_TYP if corner == "typ" else DCDC_ETA_WORST
    return max(DCDC_VOUT * i5 / (eta * vin), DCDC_INL_TYP if corner == "typ" else DCDC_INL_MAX)


def solve(corner, bus=BUS_V):
    """(I+12, I-12, I_dcdc, Vin_dcdc, V+ at the breakout, V- at the breakout) iterated to a fixed point."""
    i5 = i5_typ if corner == "typ" else i5_max
    iq = n_amps * (TL074_IQ_TYP if corner == "typ" else TL074_IQ_MAX)
    il_p = (0.0 if corner == "typ" else i_stage_p) + (i_out_typ if corner == "typ" else i_out_max)
    il_n = (0.0 if corner == "typ" else i_stage_n)
    vfc = "typ" if corner == "typ" else "max"
    vin = 2 * bus - 0.7
    for _ in range(40):
        idc = dcdc_in(i5, vin, corner)
        ip, in_ = iq + il_p + idc, iq + il_n + idc
        vp = bus - vf_b5819w(ip, vfc)
        vn = -bus + vf_b5819w(in_, vfc)
        vin = vp - vn - 2 * L_DCR * idc
    return ip, in_, idc, vin, vp, vn


typ = solve("typ")
wst = solve("max", BUS_V * (1 - BUS_TOL))
light = BUS_V * (1 + BUS_TOL) - vf_b5819w(typ[0], "min")
print(f"    rails left at the breakout's J3 / J1 after D2 / D3: typ +{typ[4]:.2f} / {typ[5]:.2f} V (12.0 V bus), "
      f"lowest +{wst[4]:.2f} / {wst[5]:.2f} V (11.4 V bus, VF max, worst load), highest +{light:.2f} V (12.6 V, VF min)")
print(f"    typ (12.0 V bus): +12 V {typ[0] * 1e3:.0f} mA, -12 V {typ[1] * 1e3:.0f} mA "
      f"(DC/DC {typ[2] * 1e3:.0f} mA of it, 16 x {TL074_IQ_TYP * 1e3:.1f} mA quiescent)")
print(f"    worst (11.4 V bus): +12 V {wst[0] * 1e3:.0f} mA, -12 V {wst[1] * 1e3:.0f} mA "
      f"(DC/DC {wst[2] * 1e3:.0f} mA, 16 x {TL074_IQ_MAX * 1e3:.1f} mA, stage loads + {i_stage_p * 1e3:.1f} / "
      f"- {i_stage_n * 1e3:.1f} mA, outputs {i_out_max * 1e3:.1f} mA)")
# a Eurorack builder budgets the case's PSU from the module's stated current
docs_all = {"README.md": README, "docs/design.md": DOC, "docs/bom.md": BOM_MD}
stated = {k: re.findall(r"(\d+)\s*mA[^.\n]{0,40}(?:\+12|−12|-12|±12|12 V)|(?:\+12|−12|-12|±12)\s*V[^.\n]{0,40}?(\d+)\s*mA", v)
          for k, v in docs_all.items()}
BREAKOUT_README_STATES_CURRENT = False        # the breakout's README (fetched 2025 copy): no mA figure at all
ck.check("D.doc_states_the_+-12V_current", any(stated.values()) or BREAKOUT_README_STATES_CURRENT,
         f"no current for +12 V / -12 V in README.md, design.md, bom.md or the breakout's readme; "
         f"computed: typ +{typ[0] * 1e3:.0f} / -{typ[1] * 1e3:.0f} mA, worst +{wst[0] * 1e3:.0f} / -{wst[1] * 1e3:.0f} mA")
ck.within("D.B5819W_current_worst <= half its 1 A", max(wst[0], wst[1]) * 1e3, None, D5819W_IO / 2 * 1e3, " mA")
ck.within("D.L1_L2_current <= rated 500 mA", wst[2] * 1e3, None, L_IRATED * 1e3, " mA")
p_d = max(wst[0], wst[1]) * vf_b5819w(max(wst[0], wst[1]), "max")
ck.within("D.B5819W_dissipation <= half its 500 mW", p_d * 1e3, None, 250, " mW")

# =================================================================== B. the DC/DC input
print("--- B. DC/DC input: +12 V to -12 V through two B5819W")
lo = solve("max", BUS_V * (1 - BUS_TOL))
hi_bus = BUS_V * (1 + BUS_TOL)
# light load, hot diodes: the highest input
vin_hi = hi_bus - vf_b5819w(typ[0], "min") + hi_bus - vf_b5819w(typ[1], "min")
print(f"    input {lo[3]:.2f} V (bus 11.4 V, VF max, worst load) .. {vin_hi:.2f} V (bus 12.6 V, VF min, typ load); "
      f"typ {typ[3]:.2f} V")
ck.within("B.DCDC_vin_min >= 21.6 V (bus -5 %, B5819W VF max, worst load)", lo[3], DCDC_VIN_MIN, None, " V")
ck.within("B.DCDC_vin_typ in 21.6 .. 26.4 V", typ[3], DCDC_VIN_MIN, DCDC_VIN_MAX, " V")
ck.within("B.DCDC_vin_max <= 26.4 V (bus +5 %, VF min)", vin_hi, None, DCDC_VIN_MAX, " V")
ck.within("B.DCDC_surge (both rails at +5 %, no diode drop) <= 30 V", 2 * hi_bus, None, DCDC_SURGE, " V")
# the 5 V the Seed then gets: an unregulated converter follows its input (line regulation 1.2 % per %)
v5_lo = DCDC_VOUT * (1 + DCDC_LINE_REG * (lo[3] / DCDC_VIN_NOM - 1))
ck.within("B.Seed_VIN at the lowest input >= 4.0 V (Seed Table 1)", v5_lo, SEED_VIN_MIN, None, " V",
          "5 V at 24 V and full load, line regulation 1.2 %/% (load regulation not counted)")
unreg = v5_lo - SEED_SCHOTTKY_VF
v_ldo_in = unreg - LDO_R_IN * (a_max + 0.02)
ck.within("B.LP2985_headroom at the lowest input (3.3 V + 0.28 V dropout)", v_ldo_in, V33 + 0.28, None, " V",
          f"UNREGULATED_VCC {unreg:.2f} V less 5.1 ohm x {(a_max + 0.02) * 1e3:.0f} mA")

# the V/OCT clamp pushes current into 3V3A; an LDO only sources, so the rail's own load must take it
print("--- C. 3V3A: the V/OCT clamp current against the rail's load")
i_pots_min = 7 * V33 / (10e3 * (1 + POT_TOL))
i_bias_min = V33 / (27e3 * (1 + R_TOL)) + V33 / (28e3 * (1 + R_TOL))
for cv in (10.0, CV_MAX):
    vo = stage_out("VOCT", -cv, V33)
    i_cl = max(vo - V33 - vf_bat85(2e-3), 0) / 1e3
    ck.within(f"C.3V3A_clamp_current_at_-{cv:g}V <= Plaitsy's own minimum 3V3A load", i_cl * 1e3, None,
              (i_pots_min + i_bias_min) * 1e3, " mA",
              f"V/OCT stage at {vo:.2f} V -> D21 -> 3V3A; pots +20 % {i_pots_min * 1e3:.2f} mA + dividers "
              f"{i_bias_min * 1e3:.2f} mA (only loads every Seed revision is known to have; a rev 5 Seed's WM8731 adds "
              f"{SEED_WM8731_3V3A_TYP * 1e3:.1f} mA typ while it runs and absorbs it, a later Seed's 3V3A load is not "
              f"documented: unclear until measured or the Seed revision is fixed)")


# =================================================================== routed-copper helpers
def _proj(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    s = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    q = (ax + s * dx, ay + s * dy)
    return s, q, math.hypot(p[0] - q[0], p[1] - q[1])


def _key(p):
    return (round(p[0], 4), round(p[1], 4))


class NetGraph:
    """The tracks of one net as a graph: nodes at track ends, junctions, pad and via centres; edges carry
    (length mm, resistance ohm). Pours are not in it (decoupling into a pour is judged by its spokes)."""

    def __init__(self, board, net):
        self.adj = {}
        tr = [t for t in board.tracks if t["net"] == net]
        vias = [v for v in board.vias if v["net"] == net]
        self.pads = {(p.ref, p.num): p for p in board.pads if p.net == net}
        splits = [{0.0: t["a"], 1.0: t["b"]} for t in tr]

        def link(p, q):
            self._edge(_key(p), _key(q), math.hypot(p[0] - q[0], p[1] - q[1]), 0.0)

        for i, t in enumerate(tr):
            for j, u in enumerate(tr):
                if i == j or t["layer"] != u["layer"]:
                    continue
                for e in (u["a"], u["b"]):
                    s, q, d = _proj(e, t["a"], t["b"])
                    if d <= (t["w"] + u["w"]) / 2 + 1e-3:
                        splits[i][s] = q
                        link(e, q)
            for v in vias:
                s, q, d = _proj(v["c"], t["a"], t["b"])
                if d <= t["w"] / 2 + v["r"] + 1e-3:
                    splits[i][s] = q
                    link(v["c"], q)
            for pad in self.pads.values():
                if pad.d_seg(t["a"], t["b"]) <= t["w"] / 2 + 1e-3:
                    s, q, d = _proj((pad.x, pad.y), t["a"], t["b"])
                    splits[i][s] = q
                    link((pad.x, pad.y), q)
        for i, t in enumerate(tr):
            pts = [splits[i][s] for s in sorted(splits[i])]
            for p, q in zip(pts, pts[1:]):
                d = math.hypot(p[0] - q[0], p[1] - q[1])
                self._edge(_key(p), _key(q), d, CU_RHO * d * 1e-3 / (t["w"] * 1e-3 * CU_T))

    def _edge(self, a, b, d, r):
        self.adj.setdefault(a, []).append((b, d, r))
        self.adj.setdefault(b, []).append((a, d, r))

    def path(self, a, b, weight="len"):
        """Shortest (length mm, resistance ohm) between two pads (ref, num); None if no track joins them."""
        pa, pb = self.pads.get(a), self.pads.get(b)
        if not pa or not pb:
            return None
        src, dst = _key((pa.x, pa.y)), _key((pb.x, pb.y))
        k = 0 if weight == "len" else 1
        best = {src: (0.0, 0.0)}
        q = [(0.0, 0.0, 0.0, src)]
        while q:
            w, L, R, n = heapq.heappop(q)
            if n == dst:
                return L, R
            if (L, R)[k] > best.get(n, (1e18, 1e18))[k]:
                continue
            for m, d, r in self.adj.get(n, []):
                nl, nr = L + d, R + r
                if (nl, nr)[k] < best.get(m, (1e18, 1e18))[k]:
                    best[m] = (nl, nr)
                    heapq.heappush(q, ((nl, nr)[k], nl, nr, m))
        return None


def spokes_at(board, pad, net):
    return sum(1 for p0, p1, layer, n in board.spokes if n == net and math.hypot(p0[0] - pad.x, p0[1] - pad.y) < 0.3)


# =================================================================== E. rails at the TL074 pins
print("--- E. rails at the TL074 supply pins")
G = {(b, n): NetGraph(brd, n) for b, brd in (("main", mb), ("face", fb))
     for n in (("+12V", "-12V", "3V3A", "3V3D") if b == "main" else ("3V3A_F", "3V3D_F", "GND_D_F"))}


def best_path(board, net, srcs, dst, weight="len"):
    res = [G[(board, net)].path(s, dst, weight) for s in srcs]
    res = [r for r in res if r]
    return min(res, key=lambda r: r[0] if weight == "len" else r[1]) if res else None


i_chip_max = 4 * TL074_IQ_MAX + max(i_stage_p, i_stage_n)
rails = {}
for net, srcs, pin in (("+12V", [("U2", f"J3-{k}") for k in (2, 3, 4)], "4"),
                       ("-12V", [("U2", f"J1-{k}") for k in (2, 3, 4)], "11")):
    for u in ("U3", "U4"):
        p = best_path("main", net, srcs, (u, pin), "res")
        ck.check(f"E.{net}_reaches_{u}.{pin}_by_track", p is not None,
                 f"track path from the breakout's pins: {None if p is None else (round(p[0], 1), round(p[1], 4))}")
        if not p:
            continue
        rv = (wst[4] if net == "+12V" else -wst[5]) - p[1] * 2 * i_chip_max
        rails[(net, u)] = rv
        print(f"    {net} -> {u}.{pin}: {p[0]:.1f} mm of track, {p[1] * 1e3:.1f} mohm, worst rail at the pin {rv:.2f} V")
vp_min = min(v for (n, u), v in rails.items() if n == "+12V")
vn_min = min(v for (n, u), v in rails.items() if n == "-12V")
# the output range the stages need, over a +-12 V jack and 3V3A +-3 %
need_hi = max(stage_out(n, -CV_MAX, V33 * (1 + V33_TOL)) for n in CH)
need_lo = min(stage_out(n, CV_MAX, V33 * (1 - V33_TOL)) for n in CH)
ck.within("E.TL074_output_high: V+ - 3 V (worst headroom) >= the highest stage output", vp_min - TL074_HEAD_MIN,
          need_hi, None, " V", f"V+ at the pins {vp_min:.2f} V (bus 11.4 V, B5819W VF max)")
ck.within("E.TL074_output_low: -(|V-| - 3 V) <= the lowest stage output", -(vn_min - TL074_HEAD_MIN), None, need_lo,
          " V", f"V- at the pins {-vn_min:.2f} V")
ck.within("E.TL074_input_common_mode: bias >= V- + 4 V", min(bias_v(b, V33 * 0.97) for b in BIAS),
          -vn_min + TL074_VICR_NEG, None, " V")

# =================================================================== F. decoupling
print("--- F. decoupling")
for cap, u, pin, net in (("C31", "U3", "4", "+12V"), ("C32", "U3", "11", "-12V"),
                         ("C33", "U4", "4", "+12V"), ("C34", "U4", "11", "-12V")):
    cp = next(n for n, v in mb.parts[cap]["nets"].items() if v == net)
    gp = next(n for n, v in mb.parts[cap]["nets"].items() if v == "GND")
    a, b = mb.parts[cap]["pads"][cp], mb.parts[u]["pads"][pin]
    d = math.hypot(a.x - b.x, a.y - b.y)
    p = G[("main", net)].path((cap, cp), (u, pin))
    sp = spokes_at(mb, mb.parts[cap]["pads"][gp], "GND")
    ck.check(f"F.{cap}_at_{u}.{pin}: track <= 6 mm, GND pad tied into the pour",
             p is not None and p[0] <= 6.0 and sp >= 2,
             f"pad {d:.1f} mm from the pin, track {None if p is None else round(p[0], 1)} mm, {sp} GND spokes")
    ck.close(f"F.{cap}_distance vs design.md 'every 100 n sits 3.6 mm from its supply pin'", d, 3.6, 0.4, " mm")
for cap, u, net, gnd in (("C8", "U1", "3V3A_F", "GND_F"), ("C9", "U9", "3V3D_F", "GND_D_F"),
                         ("C10", "U10", "3V3D_F", "GND_D_F")):
    cp = next(n for n, v in fb.parts[cap]["nets"].items() if v == net)
    gp = next(n for n, v in fb.parts[cap]["nets"].items() if v == gnd)
    a, b = fb.parts[cap]["pads"][cp], fb.parts[u]["pads"]["16"]
    d = math.hypot(a.x - b.x, a.y - b.y)
    p = G[("face", net)].path((cap, cp), (u, "16"))
    if gnd == "GND_F":
        sp = spokes_at(fb, fb.parts[cap]["pads"][gp], gnd)
        gl, g_ok, loop = f"GND pad: {sp} spokes into the GND_F pour", sp >= 2, (p[0] if p else None)
    else:
        g = G[("face", gnd)].path((cap, gp), (u, "8"))
        gl, g_ok = f"GND_D_F track to pin 8 {None if g is None else round(g[0], 1)} mm", g is not None
        loop = (p[0] + g[0]) if p and g else None
    ck.check(f"F.{cap}_at_{u}.16: track to pin 16 <= 10 mm", p is not None and p[0] <= 10.0 and g_ok,
             f"pad {d:.1f} mm from pin 16, track {None if p is None else round(p[0], 1)} mm; {gl}; "
             f"supply loop {None if loop is None else round(loop, 1)} mm")
# bulk capacitance on the rails: the breakout's C9 / C18 (100 uF) and C20 / C23 (10 uF) per rail
for net, caps in (("P12", ("C9", "C20")), ("N12", ("C18", "C23"))):
    c = sum(BREAKOUT_CAPS[k][0] for k in caps)
    ck.within(f"F.bulk_capacitance_{net} >= 10 uF", c * 1e6, 10, None, " uF", f"breakout {' + '.join(caps)}")

# =================================================================== G. power copper
print("--- G. power copper: widths, drops, ground nets")
PWR = {"main": ("+12V", "-12V", "3V3A", "3V3D"), "face": ("3V3A_F", "3V3D_F", "GND_D_F")}
m = re.search(r"(\d+(?:\.\d+)?) mm power tracks\s*\(([^)]*)\)", DOC)
ck.check("G.design_md_states_power_track_width", m is not None, "Routing notes, 'Rules first'")
w_doc = float(m.group(1)) if m else 0.6
for b, nets in PWR.items():
    brd = mb if b == "main" else fb
    for n in nets:
        ws = [t["w"] for t in brd.tracks if t["net"] == n]
        ck.check(f"G.track_width.{b}.{n} >= {w_doc} mm", bool(ws) and min(ws) >= w_doc - 0.005,
                 f"{len(ws)} tracks, {min(ws) if ws else 0:.3f} .. {max(ws) if ws else 0:.3f} mm")
# drops on the paths that carry current (worst-case currents)
i_led_max = det_max["led"]
drops = [  # (board, net, sources, loads, current A, limit V, why)
    ("main", "3V3A", [("U2", "21")], [("H2", "3"), ("R45", "1"), ("R47", "1"), ("D21", "1")], a_max + 2.7e-3, 3.3e-3,
     "the pots' top against the ADC reference (0.1 %)"),
    ("main", "3V3D", [("U2", "38")], [("H3", "3")], i_led_max, 33e-3, "1 % of 3V3D"),
    ("face", "3V3A_F", [("HF2", "3")], [(f"RV{k}", "3") for k in range(1, 8)] + [("U1", "16")], a_max, 3.3e-3,
     "the pots' top against the ADC reference (0.1 %)"),
    ("face", "3V3D_F", [("HF3", "3")], [("U9", "16"), ("U10", "16")], i_led_max, 33e-3, "1 % of 3V3D"),
    ("face", "GND_D_F", [("HF3", "2")], [("U9", "8"), ("U10", "8")] + [(f"D{k}", "2") for k in range(1, 9)]
     + [("SW1", "6"), ("SW2", "6")], det_max["led"] + det_max["btn"], 33e-3, "ground offset of the 595s / LEDs"),
]
for b, net, srcs, dsts, i, lim, why in drops:
    worst = (0.0, 0.0, None)
    for dst in dsts:
        p = best_path(b, net, srcs, dst, "res")
        ck.check(f"G.{net}_track_reaches_{dst[0]}.{dst[1]}", p is not None, f"{b} board, from {srcs[0][0]}.{srcs[0][1]}")
        if p and p[1] > worst[1]:
            worst = (p[0], p[1], dst)
    ck.within(f"G.{net}_drop (all {i * 1e3:.0f} mA over the longest path) <= {lim * 1e3:.1f} mV", worst[1] * i * 1e3,
              None, lim * 1e3, " mV", f"{worst[0]:.0f} mm, {worst[1] * 1e3:.0f} mohm to {worst[2]}; {why}")
# header pins: each supply / ground pin of the board-to-board headers carries its rail's whole current
for hdr, pin, i in (("H2", "3", a_max), ("H2", "2", a_max), ("H3", "3", i_led_max), ("H3", "2", det_max["led"] + det_max["btn"])):
    ck.within(f"G.header_current.{hdr}.{pin} ({MB[hdr].nets[pin]}) <= {HDR_I_MAX:g} A", i * 1e3, None, HDR_I_MAX * 1e3, " mA")
# connectivity: one copper group per power / ground net, holding every pin that needs it
grp_m, con_m = mb.connectivity()
grp_f, con_f = fb.connectivity()


def group_of(groups, net, key):
    for root, keys in groups.get(net, {}).items():
        if key in keys:
            return root
    return None


need = {
    ("main", "GND"): [("U2", "20"), ("U2", "40"), ("U2", "J1-1"), ("U2", "J3-1"), ("U2", "J4-2"), ("U2", "J4-4"),
                      ("H2", "2"), ("H3", "2"), ("R46", "2"), ("R48", "2"), ("D22", "2")]
                     + [(c, n) for c in ("C29", "C30", "C31", "C32", "C33", "C34") for n, v in MB[c].nets.items() if v == "GND"],
    ("face", "3V3A_F"): [(f"RV{k}", "3") for k in range(1, 8)] + [("U1", "16"), ("C8", "1"), ("HF2", "3")],
    ("face", "GND_F"): [(f"RV{k}", n) for k in range(1, 8) for n in ("1", "4", "5")]
                       + [("U1", n) for n in ("8", "7", "6", "4")] + [("C8", "2"), ("HF2", "2")]
                       + [(j, "1") for j, *_ in circuit.JACKS],
    ("face", "GND_D_F"): [("U9", "8"), ("U9", "13"), ("U10", "8"), ("U10", "13"), ("C9", "2"), ("C10", "2"), ("HF3", "2")]
                         + [(f"D{k}", "2") for k in range(1, 9)] + [(s, n) for s in ("SW1", "SW2") for n in ("1", "2", "6")],
    ("face", "3V3D_F"): [("U9", "16"), ("U9", "10"), ("U10", "16"), ("U10", "10"), ("C9", "1"), ("C10", "1"), ("HF3", "3")],
}
for (b, net), pins in need.items():
    groups = grp_m if b == "main" else grp_f
    roots = {group_of(groups, net, ("pad",) + p) for p in pins}
    ck.check(f"G.{net}_one_copper_group_holds_every_pin ({b})", len(groups.get(net, {})) == 1 and None not in roots
             and len(roots) == 1, f"{len(groups.get(net, {}))} group(s); pins not in it: "
             f"{[p for p in pins if group_of(groups, net, ('pad',) + p) is None]}")
# GND_F and GND_D_F never touch on the FB (no copper contact, no GND_D_F copper inside a GND_F pour)
touch = [c for c in con_f if {c[0], c[1]} == {"GND_F", "GND_D_F"}]
inside = []
for t in fb.tracks:
    if t["net"] == "GND_D_F":
        for isl in fb.islands:
            if isl.net == "GND_F" and isl.layer == t["layer"] and (isl.contains(t["a"]) or isl.contains(t["b"])):
                inside.append(("track", tuple(round(v, 1) for v in t["a"])))
for v in fb.vias:
    if v["net"] == "GND_D_F":
        inside += [("via", tuple(round(x, 1) for x in v["c"])) for isl in fb.islands if isl.net == "GND_F"
                   and isl.contains(v["c"])]
for pad in fb.pads:
    if pad.net == "GND_D_F":
        inside += [("pad", pad.ref, pad.num) for isl in fb.islands if isl.net == "GND_F" and isl.contains((pad.x, pad.y))]
ck.check("G.GND_F_and_GND_D_F_apart_on_the_FB", not touch and not inside, f"contacts {touch[:3]}, inside a pour {inside[:3]}")
ck.check("G.GND_F_and_GND_D_F_meet_on_the_MB_GND (H2.2, H3.2)",
         MB["H2"].nets["2"] == "GND" and MB["H3"].nets["2"] == "GND" and FB["HF2"].nets["2"] == "GND_F"
         and FB["HF3"].nets["2"] == "GND_D_F", f"H2.2 {MB['H2'].nets['2']}, H3.2 {MB['H3'].nets['2']}")

# =================================================================== H. ratings
print("--- H. ratings")
for ref, part in sorted(MB.items()):
    if part.kind != "C":
        continue
    rails_on = set(part.nets.values())
    hi = any(n in ("+12V", "-12V") for n in rails_on) or ref in [f"C{21 + i}" for i in range(8)]
    need_v = 25.0 if hi else 6.3
    mv = re.search(r"(\d+)\s*V\b", bom_line(ref))
    ck.check(f"H.cap_voltage_in_BOM.{ref} ({part.value}) >= {need_v:g} V", mv is not None and float(mv.group(1)) >= need_v,
             f"'{bom_line(ref)}'")
for ref in ("C8", "C9", "C10"):
    mv = re.search(r"(\d+)\s*V\b", bom_line(ref))
    ck.check(f"H.cap_voltage_in_BOM.{ref} >= 6.3 V", mv is not None and float(mv.group(1)) >= 6.3, f"'{bom_line(ref)}'")
for ref, (c, v, nets) in BREAKOUT_CAPS.items():
    span = {("P12", "GND"): BUS_V, ("GND", "N12"): BUS_V, ("P12", "N12"): 2 * BUS_V, ("5V", "GND"): DCDC_VOUT}[nets]
    ck.within(f"H.breakout_cap_voltage.{ref} ({nets[0]}-{nets[1]}): rating >= 1.5 x {span * (1 + BUS_TOL):.1f} V",
              v, 1.5 * span * (1 + BUS_TOL), None, " V")
ck.within("H.TL074_supply (bus +5 %) <= 36 V abs max", 2 * BUS_V * (1 + BUS_TOL), None, TL074_VSUP_ABS, " V")
vr21 = V33 * (1 + V33_TOL) + vf_bat85(3e-3)            # 3V3A against ADC_VOCT held at -VF by D22
ck.within("H.BAT85_reverse (D21 / D22) <= 30 V", vr21, None, BAT85_VR, " V")
for u, net in (("U1", "3V3A_F"), ("U9", "3V3D_F"), ("U10", "3V3D_F")):
    ck.within(f"H.74HC_VCC.{u} ({net}) within 2 .. 6 V", V33 * (1 - V33_TOL), HC_VCC_MIN, HC_VCC_MAX, " V")
    ck.within(f"H.74HC_VCC_max.{u}", V33 * (1 + V33_TOL), HC_VCC_MIN, HC_VCC_MAX, " V")
# [Verify pass 2026-11-13: this compared the constant 120 with 20 and could not fail.] The lowest load while the
# firmware runs: the MCU alone at its Table 127 typical for the clock main.cc sets, through the buck (typ efficiency).
i_min_run = V33 * MCU_TYP / (BUCK_ETA_TYP * (DCDC_VOUT - SEED_SCHOTTKY_VF))
ck.within("H.DCDC_output_load_min_while_the_firmware_runs >= 20 mA (B2405S 10 % minimum load)", i_min_run * 1e3,
          DCDC_IOUT_MIN * 1e3, None, " mA", f"MCU {MCU_TYP * 1e3:.0f} mA typ at {'480' if FW_BOOST else '400'} MHz "
          f"(main.cc) through the buck; the bootloader / reset state is not covered")

# =================================================================== I. sequencing and missing rails
print("--- I. sequencing and missing rails")
ADC_PIN = {n: next(pin for pin, (lib, net) in circuit.SEED.items() if net == f"ADC_{n}") for n in CH}
ck.check("I.no_CV_stage_on_PA4_PA5 (IINJ 0 mA on those pins)",
         not any(SEED_PORT.get(p) in ("PA4", "PA5") for p in ADC_PIN.values()),
         f"{ {n: SEED_PORT.get(p) for n, p in ADC_PIN.items()} }")
# Start-up: the Mornsun datasheet gives no start-up time; TPS6217x soft start about 1 ms and LP2985 turn-on about
# 1 ms with its 10 nF bypass (not confirmed, from memory). The window is milliseconds long; the injection currents
# are steady states (resistive), so those verdicts do not depend on its length; the 3V3A back-feed charges ~54 uF
# and does (see I.powerup_3V3A_back_fed_by_D21).
print("    power-up window: +-12 V up while the DC/DC and the Seed's regulators start (ms; not confirmed): "
      "3V3A = 3V3D = 0, both bias dividers at 0 V")
R_3V3A_UNPOWERED = par(*([10e3 * (1 + POT_TOL)] * 7), 27e3 * (1 + R_TOL), 28e3 * (1 + R_TOL))


def window(v33a, vplus, vminus, head):
    """Per-pin MCU injection (A, negative = out of the pin), the highest pin voltage, and D21's current into
    3V3A, for jack CVs of +-CV_MAX, a 3V3A of v33a and op-amp rails vplus / vminus (headroom head)."""
    inj, vmax, i21 = {}, 0.0, 0.0
    for n in CH:
        worst_i = 0.0
        for vin in (-CV_MAX, CV_MAX):
            vo = max(min(stage_out(n, vin, v33a), vplus - head), vminus + head)
            if vo >= 0:
                if n == "VOCT" and vo > v33a + 0.2:
                    i = (vo - vf_bat85(2e-3) - v33a) / (1e3 + (R_3V3A_UNPOWERED if v33a == 0 else 0))
                    i21 = max(i21, i)
                    vo = vo - i * 1e3
                vmax = max(vmax, vo)
            else:
                if n == "VOCT":          # D22 (Schottky) takes it before the pin's silicon diode
                    continue
                worst_i = max(worst_i, max(-vo - MCU_SILICON_VF, 0) / 1e3)
        inj[n] = worst_i
    return inj, vmax, i21


inj, vmax, i21 = window(0.0, wst[4], wst[5], TL074_HEAD_TYP)
for n, i in inj.items():
    ck.within(f"I.powerup_injection.{n} ({SEED_PORT[ADC_PIN[n]]}) <= 5 mA", i * 1e3, None, MCU_IINJ_NEG * 1e3, " mA",
              f"stage output -{CH[n]['rf'] / CH[n]['rin']:.2f} x jack at bias 0 V, through 1k")
ck.within("I.powerup_injection_sum (every jack at +12 V) <= 25 mA", sum(inj.values()) * 1e3, None,
          MCU_IINJ_SUM * 1e3, " mA")
ck.within("I.powerup_pin_voltage (unpowered MCU) <= 4.0 V", vmax, None, MCU_VIN_ABS_MAX_UNPOWERED, " V",
          "no positive injection path on FT / TT pins: the voltage is the limit")
v3a = i21 * R_3V3A_UNPOWERED
# [Verify pass 2026-11-13] v3a is the steady state. 3V3A holds about 54 uF on a rev 5 Seed (constants), so it gets
# there with tau = C x (1k || the loads): the time to pass VDD + 0.3 V says how long the window must last.
r_th = par(1e3, R_3V3A_UNPOWERED)
tau = SEED_3V3A_CAP_REV5 * r_th
t_03 = -tau * math.log(1 - MCU_SEQ_MARGIN / v3a) if v3a > MCU_SEQ_MARGIN else float("inf")
ck.within("I.powerup_3V3A_back_fed_by_D21 <= VDD + 0.3 V (STM32 power-up sequence rule)", v3a, None,
          MCU_SEQ_MARGIN, " V", f"V/OCT jack at -{CV_MAX:g} V: stage at +{stage_out('VOCT', -CV_MAX, 0):.2f} V -> R44 -> "
          f"D21 -> {i21 * 1e3:.2f} mA into Plaitsy's 3V3A loads ({R_3V3A_UNPOWERED:.0f} ohm; the Seed's own unpowered "
          f"load would lower it); steady state: with the rev 5 Seed's {SEED_3V3A_CAP_REV5 * 1e6:.0f} uF it passes 0.3 V "
          f"after {t_03 * 1e3:.1f} ms, so only a power-up window (bus ramp + Seed start-up, not confirmed) that long, a "
          f"hot-plug, or a CV source powered before the bus reaches it")


def brownout(vin_dcdc):
    """(Seed VIN, 3V3D, 3V3A) when the DC/DC gets vin_dcdc: an unregulated converter's output scales with its
    input; the buck stops below its UVLO, the LDO follows its input down (dropout ~0.1 V at a few mA)."""
    v5 = DCDC_VOUT * vin_dcdc / DCDC_VIN_NOM
    unreg = max(v5 - SEED_SCHOTTKY_VF + 0.1, 0)            # the Schottky drops less at the low current
    v3d = V33 if unreg >= V33 + 0.2 else (unreg if unreg >= BUCK_UVLO else 0.0)
    v3a = min(V33, max(unreg - 0.1, 0))
    return v5, v3d, v3a


for case, vp, vn in (("-12V_missing (bus -12 V at 0 V)", BUS_V - vf_b5819w(0.06), +vf_b5819w(0.06)),
                     ("+12V_missing (bus +12 V at 0 V)", -vf_b5819w(0.06), -BUS_V + vf_b5819w(0.06))):
    vin = vp - vn
    v5, v3d, v3a = brownout(vin)
    print(f"    {case}: TL074 rails {vp:+.1f} / {vn:+.1f} V, DC/DC input {vin:.1f} V -> Seed VIN {v5:.2f} V, "
          f"3V3D {v3d:.2f} V, 3V3A {v3a:.2f} V")
    ck.within(f"I.{case}: VDDA <= VDD + 0.3 V (STM32 sequence rule; the Seed browns out at VIN {v5:.1f} V)",
              v3a - v3d, None, MCU_SEQ_MARGIN, " V", f"Seed VIN {v5:.2f} V < its {SEED_VIN_MIN} V minimum: "
              f"the TPS62170 stops (VUVLO 2.6-2.82 V, SLVSAT8E), the LP2985 keeps following its input; unclear: "
              f"the B2405S at {vin:.1f} V in (below its 21.6 V range) and light load may give more than the "
              f"proportional {v5:.2f} V, and then the buck may still run (fault only, the Seed's own design)")
    bias = min(bias_v(b, v3a) for b in BIAS)
    if vn > 0:     # -12 V missing: the op-amps on +11.7 / +0.3 V, the inputs at the bias near their V-
        ck.within(f"I.{case}: TL074 inputs inside their common-mode range (bias >= V- + 4 V)", bias,
                  vn + TL074_VICR_NEG, None, " V", "SLOS080W 5.3: VI >= (VCC-) + 4 V; the new die (VCC-) + 1.5 V "
                  "is missed too; outside it the old die may phase-reverse (no-phase-reversal is shown for TL07xH only)")
        # an output that goes to its + rail lands on the ADC pins of an MCU whose VDD is 0
        vo_hi = vp - TL074_HEAD_TYP
        ck.within(f"I.{case}: a wide stage driven to its + rail: ADC pin <= 4.0 V (VDD = 0)", vo_hi, None,
                  MCU_VIN_ABS_MAX_UNPOWERED, " V", "if an old-die TL074 phase-reverses: output at V+ - 1.5 V (typ "
                  "headroom, not a datasheet figure) through 1k, no clamp on the 7 wide channels (V/OCT has D21); "
                  "DS12556 Table 19 with VDD = 0: FT and TT pins both 4.0 V, and FT / TT pins take no positive "
                  "injection (Table 20 note 3)")
        inj2, vmax2, _ = window(v3a, vp, vn, TL074_HEAD_TYP)
        ck.within(f"I.{case}: linear stages, highest ADC pin voltage <= 4.0 V", vmax2, None,
                  MCU_VIN_ABS_MAX_UNPOWERED, " V")
    else:          # +12 V missing: the op-amps on -0.3 / -11.7 V, the bias above V+: outputs at their highest
        vo_top = vp - TL074_HEAD_MIN
        per = max(-vo_top - MCU_SILICON_VF, 0) / 1e3
        wide = [n for n in CH if n != "VOCT"]
        ck.within(f"I.{case}: injection per wide ADC pin (output stuck at V+ - 3 V) <= 5 mA", per * 1e3, None,
                  MCU_IINJ_NEG * 1e3, " mA", f"output {vo_top:+.1f} V through 1k")
        ck.within(f"I.{case}: injection sum ({len(wide)} wide pins) <= 25 mA", per * len(wide) * 1e3, None,
                  MCU_IINJ_SUM * 1e3, " mA")
        i_in = max(bias - vp - 0.5, 0) / par(15e3, 12e3)
        ck.within(f"I.{case}: TL074 IN+ above V+ through the bias divider <= 10 mA (new-die input clamp)",
                  i_in * 1e3, None, 10, " mA")
# power-down: the Seed's regulators stop once the DC/DC's input falls below about 24 V x 4.0 / 5 = 19 V (bus
# about +-9.6 V); the TL074s still run on what C9 / C18 / C20 / C23 hold, 3V3A and the bias go to 0 V: the
# power-up window again, so the I.powerup checks cover it.
v_bus_off = DCDC_VIN_NOM * SEED_VIN_MIN / DCDC_VOUT / 2
ck.within("I.powerdown: TL074s still powered when the Seed stops (I.powerup applies)", v_bus_off - TL074_HEAD_TYP,
          stage_out("VOCT", -CV_MAX, 0.0), None, " V", f"bus about +-{v_bus_off:.1f} V when the Seed's VIN reaches "
          f"{SEED_VIN_MIN} V")
print("    (info) power-down inside the Seed: its LDO (3V3A) outlasts its buck (3V3D) below the buck's UVLO, so VDDA > "
      "VDD for a while; DS12556 allows that if the energy into the MCU stays under 1 mJ -- the Seed's own design, "
      "the same on every carrier board")
ck.done()
