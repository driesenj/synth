"""analog_dc: static / DC behaviour of Plaitsy's analog paths, by nodal analysis and datasheet limits.

What it checks, from circuit.py's netlist (both boards joined at the headers, solved by
analog_dc_solver.py, every circuit found by following nets from the Seed's pins) against
design.md's and the READMEs' figures and the datasheets in the constants block:
  A  the eight CV stages at nominal: bias A / bias V, gains, V0, the +-12 V landing points,
     the V/OCT usable range and "0.2 Plaits units per volt", against design.md
  B  worst-case corners (1 % resistors, 3V3A tolerance of the Seed's LP2985, TL074 Vos / Ib max at
     25 C, ADC pin leakage): +-10 V and +-12 V inside 0 .. 3V3A ("the full +-12 V stays inside the
     ADC range without clamps"), the V/OCT readable range at the corners
  C  the TL074 at the real rails (bus through the breakout's B5819W): output swing, input
     common-mode range and the TL07x phase-reversal limit at the bias, input abs max
  D  the ADC reference: VREF+ = 3V3A on the Seed (the bias is ratiometric, the jack signal is not);
     the firmware README's "most of a semitone off and the octaves ten cents or more out" (1 %
     resistors, uncalibrated) and the same with the 3V3A tolerance, Vos and Ib; "an unpatched MODEL
     input can select the model next to the one the buttons picked"
  E  over-range and protection: the V/OCT clamps D21 / D22 (BAT85) against the STM32's own ESD diode
     for jacks -12 .. +12 V and the TL074 at its rails; the STM32's pin window (-0.3 V; VDDA + 0.3 V on
     the wide channels, conservative; Min(VDD, VDDA) + 3.6 V on the FT_ha V/OCT pin), -5 mA injection,
     Table 57's 0 mA pins; the seven wide channels without clamps:
     where the pin leaves the window, the injection with a section at its rail; 3V3A back-feed
  F  leakage: BAT85 reverse current (25 C and 55 C, typ and max) through the 1k in V/OCT cents after
     a 25 C calibration; the STM32's input leakage through the 1k
  G  the normalization probe: D14 high / low -> 10k -> lug -> tip -> 100k -> the stage at its bias:
     jack and ADC voltages (design.md 0.13 / 3.13 V, Plaits' threshold about 0.83 V), the probe pin's
     current, the firmware's probe-low offset, a patched jack unaffected
  H  pots through the 74HC4051: Ron at 3.3 V (extrapolated), the ADC's and the 4051's leakage, the DC
     reading error, VEE = GND, the wiper range inside the mux supply, channel 7, the 3V3A_F drop
     over the routed tracks and the header, the mux address levels from 3V3D
  I  LEDs: 74HC595 at 3V3D, VOH at the current (extrapolated from the 4.5 / 6 V figures), 470R,
     red / green VF -> current per colour against design.md's "about 3 mA", per-595 and 3V3D totals
  J  button LEDs: D2 / D3 -> R60 / R61 -> the Thonk button's LED, for each possible LED colour
  K  the breakout's OUT / AUX: J4 pins to the jack tips through H2 (its output stage is not knowable
     from the sources here)
  L  ground: the LED return current on the main board's GND copper (routed pours, spokes, vias, a
     resistive-sheet solve) and the error it puts on the V/OCT and wide readings

Run:  cd plaits/hardware/tests && python test_analog_dc.py
Only reads circuit.py, the docs, the firmware sources and the routed export; writes nothing.
"""
import collections
import math
import re

import numpy as np

import harness
import analog_dc_solver as S
from analog_dc_solver import Config, Diode, solve

ck = harness.Checks("analog_dc")
C = S.CIRCUIT
PARTS = S.PARTS
BYREF = S.BYREF
DESIGN = harness.text("docs", "design.md")
FW_README = harness.text("firmware", "README.md")

# =========================================================================== datasheet constants
# TL074, TI SLOS080W (Sept 1978, revised July 2025), 5.8 "Electrical Characteristics (DC) for TL07xC ...",
# VS = +-15 V, TA = 25 C. Thonk's / Tayda's "TL074" is the C grade.
TL_VOS_MAX_25C = 10e-3          # VOS max, TL07xC, 25 C (13 mV over 0..70 C)
TL_IB_MAX_25C = 200e-12         # IB max, TL07xC, 25 C (7 nA over 0..70 C)
TL_VCM_MIN = 11.0               # VCM min +-11 V at +-15 V: the guaranteed range ends 4 V inside each rail
TL_VOM_10K_MIN = 12.0           # VOM min +-12 V, RL = 10k (3 V headroom)
TL_VOM_10K_TYP = 13.5           # VOM typ +-13.5 V, RL = 10k (1.5 V headroom)
TL_VS_DS = 15.0                 # the rails the figures above are given at
TL_ABS_CM_OVER = 0.5            # 5.1 abs max common-mode: (V-) - 0.5 .. (V+) + 0.5 V ("all other devices")
# Eurorack bus and the breakout's reverse-protection diodes
BUS_V = 12.0                    # nominal +-12 V
BUS_TOL = 0.05                  # ASSUMED +-5 % supply tolerance (common PSU spec; no standard figure)
B5819W_VF_MAX_1A = 0.60         # JSCJ B5817W-5819W datasheet (D, Mar 2015), B5819W VF max at IF = 1 A, 25 C
B5819W_VF_TYP = 0.30            # at the real 30..60 mA: read off a 1N5819-class curve (the JSCJ curve starts at
B5819W_VF_WORST = 0.45          #   0.1 A); 0.45 V is a conservative bound, not a datasheet figure
# Daisy Seed (datasheet v1.0.5, schematic rev 5, sheets 1 and 2, read off the PDF's schematic images):
#   3V3A = LP2985 "3v3" LDO (U4) -> FB1 -> +3V3_A; VREF+ (ball P1) and VDDA (R1) both on +3V3_A, VREF- / VSSA
#   on AGND: the ADC is ratiometric to 3V3A. 3V3D = TPS6217x buck (U3), R2 47k / R3 15k on FB.
V3A_NOM = 3.3
# LP2985, TI SLVS522S (rev. May 2025), 5.5 Electrical Characteristics, VOUT tolerance, legacy standard grade (the
# Seed's grade / chip are not known; the new chip is +-0.5 / +-1 %): IL = 1 mA, 25 C +-1.5 %; 1 mA <= IL <= 50 mA,
# 25 C +-2.5 %; 1 .. 50 mA, TJ -40..125 C +-3.5 %. The Seed's 3V3A load (STM32 VDDA + VREF+, the WM8731's AVDD /
# HPVDD, Plaitsy's pots and dividers) lies in 1 .. 50 mA.
# VERIFY 2026-11-13: were 0.015 (the IL = 1 mA row, which the load is above) and 0.025 labelled "over load and
# temperature" (it is the 25 C load row); now the datasheet's 1 .. 50 mA rows.
V3A_TOL_25C = 0.025             # max, 1 .. 50 mA, 25 C (the room-temperature figure: the README's uncalibrated case)
V3A_TOL = 0.035                 # max, 1 .. 50 mA, TJ -40..125 C (worst-case corners)
# TPS6217x, TI SLVSAT8E (May 2017), 7.5: VREF 0.8 V at FB; output voltage accuracy of the device -3 / +3 % (PWM
# mode, VIN >= VOUT + 1 V), -3.5 / +4 % (power-save mode), the divider not included (note 5); IOUT 0.5 A
TPS_VFB = 0.8                   # TPS6217x feedback voltage (adjustable version)
V3D_NOM = TPS_VFB * (1 + 47e3 / 15e3)
# VERIFY 2026-11-13: was 0.035 ("VFB +-2 %, from memory"); the device is +-3 % in PWM (the Seed's load is above half
# the ~0.2 A ripple current, so PWM is assumed), plus 47k / 15k at 1 % (assumed) +-1.5 %
V3D_TOL = 0.045
TPS_IOUT_MAX = 0.5              # TPS6217x: 500 mA output current (SLVSAT8E, Features / 7.3)
SEED_OWN_3V3D = 0.3             # ASSUMED upper bound of the Seed's own 3V3D draw (MCU at 480 MHz, SDRAM, QSPI);
                                # Electrosmith publishes no figure
# STM32H750, ST DS12556 Rev 7 (March 2023). The Seed runs at 480 MHz, so its H750 is rev V (Table 1 note 3): the
# rev V chapter's Tables 117 / 118 / 120 / 154 / 155 / 156 hold the same figures as the rev Y Tables 19 / 20 / 22 /
# 57 / 58 / 59 cited below.
STM_VIN_MIN = -0.3              # Table 19 abs max VIN min VSS - 0.3 V; Table 22 operating VIN min -0.3 V
STM_ANALOG_OVER = 0.3           # TT_xx operating VIN max VDD + 0.3 V (Table 22 / 120); used here as the conservative
                                # top of the window for every ADC pin (right for the TT_a ones)
# VERIFY 2026-11-13: FT_xxx pins (PA1 = V/OCT is FT_ha; "_a: analog option supplied by VDDA", Table 7 legend):
# Table 22 / 120 operating VIN max Min(VDD, VDDA, VDD33USB) + 3.6 V, and < 5.5 V; Table 19 / 117 abs max
# Min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V (note: the formula takes the supplies related to the I/O structure, so
# VDDA is in it); Table 20 / 118 note 3: positive injection does not occur below that maximum. An FT ADC pin
# above VDDA only clips the reading (VAIN 0 .. VREF+, Table 182). Was taken as VDDA + 0.3 V ("not confirmed").
STM_FT_VIN_OP_OVER = 3.6        # Table 22 / 120, FT_xxx: Min(VDD, VDDA, VDD33USB) + 3.6 V ...
STM_FT_VIN_OP_CAP = 5.5         # ... and below 5.5 V
STM_TT_VIN_ABS_MAX = 4.0        # Table 19, TT_xx pins
STM_FT_VIN_ABS_OVER = 4.0       # Table 19, FT_xxx pins: min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V
STM_IINJ_NEG_MAX = 5e-3         # Table 20, IINJ(PIN) on FT_xxx / TT_xx pins except PA4 / PA5: -5 / +0 mA
STM_IINJ_SUM_MAX = 25e-3        # Table 20, sum of all injected currents
STM_IINJ_FUNC_LEAK = 5e-6       # 6.3.14: functional failure criterion, induced leakage outside -5 uA / +0 uA
STM_ILKG_MAX = 250e-9           # Table 58, TT_xx and FT_xx input leakage, 0 < VIN <= VDD: +-250 nA (by design)
STM_VOH_DROP_8MA = 0.4          # Table 59, CMOS port, IIO = -8 mA, 2.7 V <= VDD <= 3.6 V: VOH >= VDD - 0.4 V
STM_VOL_8MA = 0.4               # Table 59, IIO = +8 mA: VOL <= 0.4 V
STM_IO_SPEC = 8e-3              # the current those two are given at
STM_IO_ABS_MAX = 20e-3          # Table 20, IIO per pin
STM_IO_SUM_MAX = 140e-3         # Table 20, total sourced by all I/Os
# Table 7 pin types (UFBGA176 rows, read off the PDF tables); the Seed's ports from libDaisy's daisy_seed.h
STM_PORT = {"A0": "PC0", "A1": "PA3", "A2": "PB1", "A3": "PA7", "A4": "PA6", "A5": "PC1", "A6": "PC4",
            "A9": "PA1", "A10": "PA0"}
STM_TYPE = {"PC0": "FT_a", "PA3": "FT_ha", "PB1": "TT_a", "PA7": "TT_a", "PA6": "FT_a", "PC1": "FT_ha",
            "PC4": "TT_a", "PA1": "FT_ha", "PA0": "FT_a"}
# Table 57, functional susceptibility: negative injection 0 mA on these (PA0, PA1: 0 / 0; PA6, PA7, PC4: 0 / NA)
STM_NO_NEG_INJECTION = {"PA0", "PA1", "PA6", "PA7", "PC4"}
# the STM32's ESD diode to VSS is not characterised by ST: modelled as a silicon junction, 1 mA at 0.55 V
# (a low, i.e. pessimistic, turn-on for a pad diode), n = 1 -- an ASSUMPTION, not a datasheet figure
ESD_IS, ESD_N, ESD_RS = 1e-3 / math.exp(0.55 / S.VT_25C), 1.0, 5.0
# BAT85, Philips Semiconductors product specification, 2000 May 25 (supersedes 1996 Mar 20), Tamb = 25 C
BAT_VF_MAX = {0.1e-3: 0.240, 1e-3: 0.320, 10e-3: 0.400, 30e-3: 0.500, 100e-3: 0.800}   # VF max at IF
BAT_VF_TYP = {0.1e-3: 0.157, 1e-3: 0.220, 10e-3: 0.313}     # Fig. 3, 25 C curve, typ, read off the plot
BAT_IR_MAX_25V = 2e-6           # IR max at VR = 25 V, 25 C (no figure at low VR; Vishay BAT85S: the same 2 uA)
BAT_IR_TYP_5V_25C = 225e-9      # Fig. 4 typ, 25 C: about 225 nA at 5 V, 650 nA at 30 V (read off the plot)
BAT_IR_TYP_30V_25C = 650e-9
BAT_IR_TYP_5V_85C = 16e-6       # Fig. 4 typ, 85 C: about 16 uA at 5 V (re-read 2026-11-13: 14.5 uA)
BAT_IF_MAX = 200e-3             # IF continuous max
# VERIFY 2026-11-13: the Philips curves start at 5 V; the pins here see 0.1 .. 3.2 V. Vishay BAT85S, doc 85513
# rev 2.2 (07-Nov-2024), DO-35 like the BOM's part, Fig. 2 "Typical reverse leakage current vs reverse voltage"
# (typ, read off the rendered plot), uA at VR = 1 / 3 / 10 / 30 V, per Tj; IR(25 V, 25 C) typ 0.19 uA:
BAT_V_VR = (1.0, 3.0, 10.0, 30.0)
BAT_V_IR = {25.0: (0.048, 0.061, 0.094, 0.22), 50.0: (0.355, 0.445, 0.66, 1.28), 75.0: (1.94, 2.44, 3.4, 6.2)}
BAT_V_IR_25V_25C = 0.19e-6
# 74HC4051, TI CD74HC4051 SCHS122O (Nov 1997, rev. Jan 2026), 5.5, IO = 1 mA, VIS = VCC to VEE, VEE = 0
MUX_RON_45 = {"typ": 90.0, "max25": 180.0, "max85": 225.0}    # VCC = 4.5 V
MUX_RON_6 = {"typ": 80.0, "max25": 160.0, "max85": 200.0}     # VCC = 6 V
MUX_RON_VT = 0.9                # ASSUMED switch threshold for the extrapolation to 3.3 V (no 2 V / 3.3 V figure)
MUX_IIZ_25C = 0.2e-6            # IIZ, 8 channels, VCC = 6 V, VEE = 0: +-0.2 uA at 25 C
MUX_IIZ_85C = 2e-6              # +-2 uA, -55 .. 85 C
MUX_ICC_85C = 80e-6             # ICC max, VCC = 6 V, -55 .. 85 C
MUX_ABS_OVER = 0.5              # abs max: VI < VEE - 0.5 or > VCC + 0.5 V -> input / switch diode current
MUX_VIH_2V, MUX_VIH_45 = 1.5, 3.15      # VIH min at VCC = 2 V / 4.5 V (HC)
# 74HC595, TI SN74HC595 SCLS041J (Dec 1982, rev. Oct 2021), 6.5, QA..QH
HC595_VOH = {4.5: (6e-3, 3.98, 3.84, 4.30), 6.0: (7.8e-3, 5.48, 5.34, 5.80)}   # VCC: (IOH, min 25 C, min -40..85, typ)
HC595_PMOS_VT = 0.9             # ASSUMED for the extrapolation of the output resistance to 3.3 V
HC595_IO_MAX = 35e-3            # 6.1 abs max continuous output current
HC595_ICC_MAX = 70e-3           # 6.1 abs max continuous current through VCC or GND
# 3 mm red / green bicolour LED, common cathode (BOM: Tayda). VERIFY 2026-11-13: the only 3 mm R/G common-cathode
# 3-lead LED Tayda sells is SKU A-8599 (taydaelectronics.com product page, read by the bom group and the power/bom
# verifier 2026-11-13): "Forward Voltage Red: 1.8V - 2.2V", "Forward Voltage Green: 2.8V - 3.0V", "Forward
# Current: 20mA" (no datasheet). Was an assumed 1.7 / 1.9 / 2.6 V red and 1.8 / 2.0 / 2.6 V green from other makers'
# parts. At the 0.3 .. 4 mA here an LED's VF is below its 20 mA value, so the 20 mA maximum is an upper bound (the
# worst case), the 20 mA mid-range is used as the typical (high: conservative), and the 20 mA minimum less 0.2 V
# (ASSUMED) as the lowest VF for the best-case current.
LED_VF_TAYDA = {"R": (1.80 - 0.2, 2.00, 2.20), "G": (2.80 - 0.2, 2.90, 3.00)}  # (min, typ, max)
# [2026-11-14, the test report's M1 fix: bom.py names the Kingbright L-3WEGW. DSAA6458 V.18A, Electrical / Optical
# characteristics at 25 C, IF = 20 mA: VF High Efficiency Red (GaAsP/GaP) typ 2.0, max 2.5 V; Green (GaP) typ 2.2,
# max 2.5 V; note 2 "Forward Voltage: +/-0.1V" (measurement); no minimum given: typ - 0.1 - 0.2 V (ASSUMED, the
# lower VF at a few mA, as for the Tayda part). The part the BOM's D1 line names is used; Tayda's when it names none.]
LED_VF_L3WEGW = {"R": (2.0 - 0.3, 2.0, 2.5), "G": (2.2 - 0.3, 2.2, 2.5)}
_LED_LINE = next((ln for ln in harness.text("docs", "bom.md").splitlines() if "bicolour LED" in ln), "")
LED_PART = "Kingbright L-3WEGW" if "L-3WEGW" in _LED_LINE else "Tayda A-8599"
LED_VF = LED_VF_L3WEGW if "L-3WEGW" in _LED_LINE else LED_VF_TAYDA
LED_PARTS_NOTE = f"LED bom.md names: {LED_PART}"
# Thonk low-profile LED button: colour still open (known). Its drawing PB01-109TL rev A (read by the power/bom
# verifier 2026-11-13) lists the LED material as GaAsP / GaP (red, orange, yellow, green); blue, white and InGaN
# green are not on it. Typical VF per colour (ASSUMED):
BTN_LED_VF = {"red": (1.7, 1.9, 2.4), "yellow / orange": (1.8, 2.0, 2.4), "green (GaP, yellow-green)": (1.8, 2.0, 2.5),
              "green (InGaN, pure green)": (2.7, 3.0, 3.5), "blue": (2.7, 3.0, 3.5), "white": (2.7, 3.0, 3.5)}
# design.md's "about N mA per colour" (3 until 2026-11-14), read from design.md rather than copied here
_m_led = re.search(r"about (\d+(?:\.\d+)?) mA per colour", harness.text("docs", "design.md"))
LED_I_DESIGN = float(_m_led.group(1)) * 1e-3 if _m_led else float("nan")
LED_I_LIT = 1e-3                # a panel indicator wants about 1 mA typical to read as lit (judgement)
LED_I_VISIBLE = 0.5e-3          # below 0.5 mA in the worst case it is barely visible (judgement)
# passives
R_TOL = 0.01                    # every resistor is 1 % metal film (BOM)
POT_TOL = 0.20                  # Alpha 9 mm B10k total resistance +-20 % (usual Alpha figure, NOT CONFIRMED)
HDR_CONTACT_R = 0.02            # ASSUMED 20 mOhm per mated 2.54 mm header contact
CU_T, CU_RHO = 35e-6, 1.72e-8   # 1 oz outer copper (JLCPCB 2-layer default), annealed copper resistivity
VIA_G = 500.0                   # a GND via or THT pad between the layers, about 2 mOhm (ASSUMED)
ADC_LSB12 = V3A_NOM / 4096      # one 12-bit step at the pin, the "negligible" yardstick

# =========================================================================== the circuit, by following nets
SEED = BYREF["U2"]


def parts_on(net, kind=None):
    return [p for p in PARTS if net in [S.node(v) for v in p.nets.values()] and (kind is None or p.kind == kind)]


def other(p, net):
    a, b = S.node(p.nets["1"]), S.node(p.nets["2"])
    return b if a == net else a


def within(name, actual, lo, hi, unit="", why=""):
    return ck.within(name, actual, lo, hi, unit, why)


def close(name, actual, expected, tol, unit="", why=""):
    return ck.check(name, abs(actual - expected) <= tol, f"expected {expected:.4g}{unit} +- {tol:.3g}, got "
                                                         f"{actual:.4g}{unit}" + (f" ({why})" if why else ""))


SECTIONS = {o: (chip, s, m, pl) for chip, s, o, m, pl in S.sections()}
CH = {}          # channel name -> dict
for pin, (name, net) in C.SEED.items():
    if not net or not net.startswith("ADC_"):
        continue
    ch = net[4:]
    rs = parts_on(net, "R")
    assert len(rs) == 1, (net, rs)
    rs = rs[0]
    oa = other(rs, net)
    chip, s, inm, inp = SECTIONS[oa]
    rin_rf = parts_on(inm, "R")
    rf = next(p for p in rin_rf if oa in (S.node(p.nets["1"]), S.node(p.nets["2"])))
    rin = next(p for p in rin_rf if p is not rf)
    cv = other(rin, inm)
    bias_r = parts_on(inp, "R")
    rtop = next(p for p in bias_r if "3V3A" in (p.nets["1"], p.nets["2"]))
    rbot = next(p for p in bias_r if "GND" in (p.nets["1"], p.nets["2"]))
    jack = next(p for p in PARTS if p.kind == "JACK" and S.node(p.nets["3"]) == cv)
    ain = name.split("/")[-1]
    CH[ch] = dict(adc=net, seed_pin=pin, ain=ain, port=STM_PORT.get(ain), rs=rs, oa=oa, sec=(chip, s), inm=inm,
                  bias=inp, rin=rin, rf=rf, rtop=rtop, rbot=rbot, cv=cv, jack=jack.ref,
                  lug=S.node(jack.nets["2"]) if jack.nets.get("2") else None,
                  g=harness.ohms(rf.value) / harness.ohms(rin.value),
                  k=harness.ohms(rbot.value) / (harness.ohms(rtop.value) + harness.ohms(rbot.value)))
    CH[ch]["v0"] = V3A_NOM * CH[ch]["k"] * (1 + CH[ch]["g"])
WIDE = [c for c in CH if c != "VOCT"]
VOCT = CH["VOCT"]
BIAS_USERS = collections.defaultdict(list)
for c, d in CH.items():
    BIAS_USERS[d["bias"]].append(c)

ck.check("model.channels", len(CH) == 8, "eight CV channels by following the nets from the Seed's ADC pins: "
         + ", ".join(f"{c} {d['ain']}/{d['port']} {d['sec'][0]}{'ABCD'[d['sec'][1] - 1]} {d['jack']}"
                     for c, d in CH.items()))
ck.check("model.ports", all(d["port"] in STM_TYPE for d in CH.values()), "every ADC pin's STM32 port and pin type known")
V0_, _, _ = solve(Config())
ck.check("model.linear", all(abs(V0_[d["inm"]] - V0_[d["bias"]]) < 1e-3 for d in CH.values()),
         "nothing patched, probe open: every op-amp linear (IN- within 1 mV of IN+)")


def decode(ch, v_adc, v3a=V3A_NOM):
    """The firmware's jack voltage from a pin voltage: the ADC reads v_adc / VREF+ (VREF+ = 3V3A), the firmware
    takes full scale as 3.3 V and inverts the nominal stage (design.md 'Firmware mapping')."""
    d = CH[ch]
    return (d["v0"] - v_adc / v3a * V3A_NOM) / d["g"]


def run(sources=None, **kw):
    V, I, ID = solve(Config(sources=sources, **kw))
    return V


def adc_at(ch, vjack, **kw):
    d = CH[ch]
    return run({d["jack"]: (vjack, 0.0)}, **kw)[d["adc"]]


# =========================================================================== A: nominal stages vs design.md
def doc_num(pattern, cast=float):
    m = re.search(pattern, DESIGN, re.S)
    return cast(m.group(1)) if m else None


DOC_BIAS_A = doc_num(r"\*\*Bias A\*\* = .*?= ([\d.]+) V")
DOC_BIAS_V = doc_num(r"\*\*Bias V\*\* = .*?= ([\d.]+) V")
DOC_G_WIDE = doc_num(r"\*\*Wide channels\*\* \(gain −([\d.]+)\)")
DOC_V0_WIDE = doc_num(r"V_adc = ([\d.]+) V − [\d.]+ · V_in; ±12")
DOC_HI_WIDE = doc_num(r"±12 V\s+lands on ([\d.]+) …")
DOC_LO_WIDE = doc_num(r"lands on [\d.]+ … ([\d.]+) V")
DOC_G_VOCT = doc_num(r"\*\*V/OCT\*\* \(gain −([\d.]+)\)")
DOC_V0_VOCT = doc_num(r"V/OCT.*?V_adc = ([\d.]+) V − [\d.]+ · V_in; usable")
DOC_VOCT_LO = doc_num(r"usable −([\d.]+) …", cast=lambda s: -float(s))
DOC_VOCT_HI = doc_num(r"usable −[\d.]+ …\s*\+([\d.]+) V")
ck.check("A.doc_figures", None not in (DOC_BIAS_A, DOC_BIAS_V, DOC_G_WIDE, DOC_V0_WIDE, DOC_HI_WIDE, DOC_LO_WIDE,
                                       DOC_G_VOCT, DOC_V0_VOCT, DOC_VOCT_LO, DOC_VOCT_HI),
         f"design.md: bias {DOC_BIAS_A} / {DOC_BIAS_V} V, wide -{DOC_G_WIDE} V0 {DOC_V0_WIDE} (+-12 V -> {DOC_HI_WIDE} .. "
         f"{DOC_LO_WIDE}), V/OCT -{DOC_G_VOCT} V0 {DOC_V0_VOCT} usable {DOC_VOCT_LO} .. +{DOC_VOCT_HI}")
V = run()
for bias, users in sorted(BIAS_USERS.items()):
    doc = DOC_BIAS_V if users == ["VOCT"] else DOC_BIAS_A
    close(f"A.bias.{bias}", V[bias], doc, 0.0015, " V", f"design.md; used by {', '.join(users)}")
for c, d in CH.items():
    g_doc, v0_doc = (DOC_G_VOCT, DOC_V0_VOCT) if c == "VOCT" else (DOC_G_WIDE, DOC_V0_WIDE)
    a, b = adc_at(c, 0.0), adc_at(c, 1.0)
    close(f"A.gain.{c}", a - b, g_doc, 0.0015, "", "design.md gain magnitude")
    close(f"A.v0.{c}", a, v0_doc, 0.0015, " V", "design.md V0, the pin at 0 V in")
    if c != "VOCT":
        close(f"A.plus12.{c}", adc_at(c, 12.0), DOC_LO_WIDE, 0.006, " V", "design.md: +12 V lands on")
        close(f"A.minus12.{c}", adc_at(c, -12.0), DOC_HI_WIDE, 0.006, " V", "design.md: -12 V lands on")
close("A.voct_low_end", (VOCT["v0"] - V3A_NOM) / VOCT["g"], DOC_VOCT_LO, 0.05, " V", "design.md usable low end")
close("A.voct_high_end", VOCT["v0"] / VOCT["g"], DOC_VOCT_HI, 0.05, " V", "design.md usable high end")
# [2026-11-14: the claim is read from design.md. With R43 33k it said "0.2 Plaits units per volt"; with 30k the
# stage is 0.18 units per volt and the firmware rescales to Plaits' 0.2, so design.md no longer states it.]
_m_units = re.search(r"([\d.]+) Plaits units per volt", " ".join(DESIGN.split()))
if _m_units:
    close("A.voct_units", VOCT["g"] / V3A_NOM * 2.0, float(_m_units.group(1)), 0.002, " /V",
          f"design.md '{_m_units.group(1)} Plaits units per volt' (Plaits' CV units span 2.0 over the 3.3 V ADC range)")
else:
    print(f"    (info) A.voct_units: {VOCT['g'] / V3A_NOM * 2.0:.4f} Plaits units per volt (design.md states none; the "
          "firmware rescales to Plaits' own)")


# =========================================================================== B: worst-case corners
def n_inputs_on(net):
    return sum(1 for chip, s, o, m, pl in S.sections() if net in (pl, m))


def params(ch, vos=TL_VOS_MAX_25C, ib=TL_IB_MAX_25C, v3a_tol=V3A_TOL, ilkg=STM_ILKG_MAX, rtol=R_TOL):
    """The tolerances of one channel as (kind, target, low, high)."""
    d = CH[ch]
    ps = []
    if rtol:
        for r in (d["rin"], d["rf"], d["rs"], d["rtop"], d["rbot"]):
            ps.append(("r", r.ref, 1 - rtol, 1 + rtol))
    if v3a_tol:
        ps.append(("v3a", None, V3A_NOM * (1 - v3a_tol), V3A_NOM * (1 + v3a_tol)))
    if vos:
        ps.append(("vos", d["sec"], -vos, vos))
    if ib:
        ps.append(("inj", d["inm"], -ib, ib))
        ps.append(("inj", d["bias"], -ib * n_inputs_on(d["bias"]), ib * n_inputs_on(d["bias"])))
    if ilkg:
        ps.append(("inj", d["adc"], -ilkg, ilkg))
    return ps


def setting_kw(setting):
    kw = dict(rtol={}, vos={}, inject={}, v3a=V3A_NOM)
    for (kind, tgt, lo, hi), val in setting:
        if kind == "r":
            kw["rtol"][tgt] = val
        elif kind == "v3a":
            kw["v3a"] = val
        elif kind == "vos":
            kw["vos"][tgt] = val
        elif kind == "inj":
            kw["inject"][tgt] = kw["inject"].get(tgt, 0.0) + val
    return kw


def at(ch, vjack, setting, **extra):
    """(node voltages, 3V3A) with the jack at vjack (None: unpatched) and the given tolerances."""
    kw = setting_kw(setting)
    for k, v in extra.items():
        if k == "inject":
            for nd, i in v.items():
                kw["inject"][nd] = kw["inject"].get(nd, 0.0) + i
        else:
            kw[k] = v
    d = CH[ch]
    V = run({d["jack"]: (vjack, 0.0)} if vjack is not None else None, **kw)
    return V, kw["v3a"]


def extremes(ps, f):
    """(min, nominal, max) of f(setting) over the tolerance box: each parameter's direction from a one-at-a-time
    step, then f re-evaluated at the two vertices (f is close to linear in these small tolerances)."""
    nom = f([])
    ups = [f([(p, p[3])]) >= f([(p, p[2])]) for p in ps]
    fmax = f([(p, p[3] if u else p[2]) for p, u in zip(ps, ups)])
    fmin = f([(p, p[2] if u else p[3]) for p, u in zip(ps, ups)])
    return fmin, nom, fmax


# [2026-11-14: design.md said "the full ±12 V stays inside the ADC range without clamps", which the worst corner
# missed by 18 / 39 mV; it now says ±12 V at nominal parts and "about ±N V" at the worst corner. The claim is read
# from design.md: ±12 V is held at nominal when the doc gives a worst-case figure, and that figure at the worst
# corner.]
_m_w = re.search(r"worst corner,.{0,80}?about ±([\d.]+) V\s+does", DESIGN, re.S)
DOC_WIDE_WORST = float(_m_w.group(1)) if _m_w else 12.0
for vj in sorted({10.0, 12.0, DOC_WIDE_WORST}):
    lows, highs = {}, {}
    for c in WIDE:
        ps = params(c)
        lows[c] = extremes(ps, lambda s: at(c, vj, s)[0][CH[c]["adc"]])
        highs[c] = extremes(ps, lambda s: (lambda V, v3a: V[CH[c]["adc"]] - v3a)(*at(c, -vj, s)))
    wl = min(lows, key=lambda c: lows[c][0])
    wh = max(highs, key=lambda c: highs[c][2])
    nominal_only = vj == 12.0 and DOC_WIDE_WORST < 12.0
    k = 1 if nominal_only else None           # extremes(): (worst low, nominal, worst high)
    doc = ("; design.md: ±12 V inside at nominal parts" if nominal_only else
           f"; design.md: about ±{vj:g} V inside at the worst corner" if vj == DOC_WIDE_WORST else "")
    within(f"B.inside_low.+{vj:g}V", lows[wl][1 if nominal_only else 0], 0.0, None, " V",
           f"{'nominal' if nominal_only else 'worst-case'} pin voltage at +{vj:g} V in >= 0 V, the seven wide "
           f"channels (worst {wl}: nominal {lows[wl][1]:.3f}, worst corner {lows[wl][0]:.3f} V){doc}")
    within(f"B.inside_high.-{vj:g}V", highs[wh][1 if nominal_only else 2], None, 0.0, " V vs 3V3A",
           f"{'nominal' if nominal_only else 'worst-case'} pin voltage at -{vj:g} V in <= 3V3A, the seven wide "
           f"channels (worst {wh}: nominal {highs[wh][1]:+.3f}, worst corner {highs[wh][2]:+.3f} V){doc}")


def ends(ch, s):
    """Jack voltages where the pin reaches 3V3A (full scale) and 0 V."""
    V0, v3a = at(ch, 0.0, s)
    V1, _ = at(ch, 1.0, s)
    a, b = V0[CH[ch]["adc"]], V1[CH[ch]["adc"]]
    return (a - v3a) / (a - b), a / (a - b)


ps = params("VOCT")
lo_end = extremes(ps, lambda s: ends("VOCT", s)[0])
hi_end = extremes(ps, lambda s: ends("VOCT", s)[1])
print(f"      V/OCT readable range: low end {lo_end[0]:+.3f} .. {lo_end[2]:+.3f} V (nominal {lo_end[1]:+.3f}), "
      f"high end {hi_end[0]:+.3f} .. {hi_end[2]:+.3f} V (nominal {hi_end[1]:+.3f})")
# [2026-11-14: design.md now gives the worst-corner range beside the nominal one ("−3.0 … +7.2 V at the worst
# corner"); the worst corner is held to that figure when it is stated, to the nominal usable range when not.]
_m_vw = re.search(r"−([\d.]+) … \+([\d.]+) V at the worst corner", " ".join(DESIGN.split()))
VOCT_LO_W, VOCT_HI_W = (-float(_m_vw.group(1)), float(_m_vw.group(2))) if _m_vw else (DOC_VOCT_LO, DOC_VOCT_HI)
_which = "worst-corner" if _m_vw else "usable"
within("B.voct_low_end_worst", lo_end[2], None, VOCT_LO_W + 0.1, " V",
       f"the worst corner still reads down to design.md's {_which} low end {VOCT_LO_W:+.1f} V, 0.1 V allowed")
within("B.voct_high_end_worst", hi_end[0], VOCT_HI_W - 0.1, None, " V",
       f"the worst corner still reads up to design.md's {_which} high end {VOCT_HI_W:+.1f} V, 0.1 V allowed")
# the firmware README: 'every input has Plaits' range and response: ... MODEL and HARMONICS ±5 V, TIMBRE, FM and
# MORPH ±8 V, TRIG −0.9…+5 V, LEVEL −0.9…+9.1 V' -- the worst corner must still read that far
FWF = " ".join(FW_README.split())
PLAITS_RANGE = {}
m1 = re.search(r"MODEL and HARMONICS ±([\d.]+) V", FWF)
m2 = re.search(r"TIMBRE, FM and MORPH ±([\d.]+) V", FWF)
m3 = re.search(r"TRIG −([\d.]+)…\+([\d.]+) V", FWF)
m4 = re.search(r"LEVEL −([\d.]+)…\+([\d.]+) V", FWF)
if m1 and m2 and m3 and m4:
    for c in ("MODEL", "HARMO"):
        PLAITS_RANGE[c] = (-float(m1.group(1)), float(m1.group(1)))
    for c in ("TIMBRE", "FM", "MORPH"):
        PLAITS_RANGE[c] = (-float(m2.group(1)), float(m2.group(1)))
    PLAITS_RANGE["TRIG"] = (-float(m3.group(1)), float(m3.group(2)))
    PLAITS_RANGE["LEVEL"] = (-float(m4.group(1)), float(m4.group(2)))
ck.check("B.plaits_ranges_found", sorted(PLAITS_RANGE) == sorted(WIDE), "firmware/README.md: Plaits' input ranges")
for c, (rlo, rhi) in PLAITS_RANGE.items():
    ps = params(c)
    lo_e = extremes(ps, lambda s: ends(c, s)[0])[2]
    hi_e = extremes(ps, lambda s: ends(c, s)[1])[0]
    ck.check(f"B.plaits_range.{c}", lo_e <= rlo and hi_e >= rhi,
             f"worst corner reads {lo_e:+.2f} .. {hi_e:+.2f} V, Plaits' range {rlo:+.1f} .. {rhi:+.1f} V (README)")


# =========================================================================== C: the TL074 at the real rails
def rails(case):
    v = (BUS_V - B5819W_VF_TYP) if case == "typ" else (BUS_V * (1 - BUS_TOL) - B5819W_VF_WORST)
    return v, -v


VP_W, VN_W = rails("worst")
VP_T, VN_T = rails("typ")
OUT_HEAD_MIN = TL_VS_DS - TL_VOM_10K_MIN            # 3 V from each rail guaranteed (RL >= 10k)
OUT_HEAD_TYP = TL_VS_DS - TL_VOM_10K_TYP            # 1.5 V typ
CM_HEAD_MIN = TL_VS_DS - TL_VCM_MIN                 # 4 V from each rail guaranteed
print(f"      rails: typ +-{VP_T:.2f} V, worst +-{VP_W:.2f} V (bus {BUS_V * (1 - BUS_TOL):.2f} V less the B5819W at "
      f"{B5819W_VF_WORST} V; its datasheet gives only {B5819W_VF_MAX_1A} V max at 1 A)")
for c, d in CH.items():
    rl = harness.ohms(d["rf"].value)
    within(f"C.load.{c}", rl, 10e3, None, " ohm",
           f"the output's load, Rf {d['rf'].value} to the virtual ground (the ADC pin behind 1k is high-Z), >= 10k "
           f"so the RL = 10k swing figure applies")
    ps = params(c)
    vmin, vmax, imin, imax = 1e9, -1e9, 1e9, -1e9
    for vj in (-12.0, 12.0):
        lo, _, hi = extremes(ps, lambda s: at(c, vj, s)[0][d["oa"]])
        vmin, vmax = min(vmin, lo), max(vmax, hi)
        for net in (d["inm"], d["bias"]):
            lo, _, hi = extremes(ps, lambda s: at(c, vj, s)[0][net])
            imin, imax = min(imin, lo), max(imax, hi)
    within(f"C.swing_low.{c}", vmin, VN_W + OUT_HEAD_MIN, None, " V",
           f"output over -12 .. +12 V in at the worst corners ({vmin:+.3f} .. {vmax:+.3f} V) above the guaranteed "
           f"swing at the worst rails")
    within(f"C.swing_high.{c}", vmax, None, VP_W - OUT_HEAD_MIN, " V", "output top below the guaranteed swing")
    within(f"C.common_mode.{c}", imin, VN_W + CM_HEAD_MIN, VP_W - CM_HEAD_MIN, " V",
           f"inputs {imin:+.3f} .. {imax:+.3f} V (bias {d['bias']}) inside the guaranteed common-mode range at the "
           f"worst rails; a TL07x reverses phase below V- + 4 V")
    within(f"C.input_abs_max.{c}", imax, VN_W - TL_ABS_CM_OVER, VP_W + TL_ABS_CM_OVER, " V",
           "inputs inside the rails +- 0.5 V")

# =========================================================================== D: the ADC reference, pitch before calibration
CVADC = harness.text("firmware", "src", "plaits", "drivers", "cv_adc.cc")
m = re.search(r"kVdd\s*=\s*([\d.]+)f", CVADC)
FW_VDD = float(m.group(1)) if m else None
ck.check("D.vref_full_scale", FW_VDD == V3A_NOM,
         f"the firmware's full scale (cv_adc.cc kVdd = {FW_VDD}) is 3V3A's nominal 3.3 V: the Seed ties VREF+ to "
         f"VDDA = 3V3A (schematic rev 5, sheet 2)")
V3A_P = ("v3a", None, 0.0, 0.0)


def decoded(ch, vjack, s, **extra):
    V, v3a = at(ch, vjack, s, **extra)
    return decode(ch, V[CH[ch]["adc"]], v3a)


for tol in (V3A_TOL_25C, V3A_TOL):
    off = max(abs(decoded("VOCT", 0.0, [(V3A_P, V3A_NOM * (1 + sg * tol))]) - decoded("VOCT", 0.0, []))
              for sg in (-1, 1))
    ck.check(f"D.ratiometric_bias.{tol:.1%}", off < 1e-3,
             f"3V3A {tol:.1%} off moves the decoded 0 V by {off * 1e3:.3f} mV (< 1 mV: bias and ADC share 3V3A)")
    sc = max(abs((decoded("VOCT", 3.0, [(V3A_P, V3A_NOM * (1 + sg * tol))]) -
                  decoded("VOCT", 1.0, [(V3A_P, V3A_NOM * (1 + sg * tol))])) / 2.0 - 1.0) for sg in (-1, 1))
    print(f"      3V3A {tol:.1%} off: the jack signal is not ratiometric: V/OCT scale {sc:.2%} off = "
          f"{1200 * sc:.0f} cents per octave before calibration")


def pitch_offset(s):
    return 1200 * decoded("VOCT", 0.0, s)                 # cents at 0 V in


def pitch_scale(s):
    return 1200 * ((decoded("VOCT", 3.0, s) - decoded("VOCT", 1.0, s)) / 2.0 - 1.0)   # cents per octave


ps_r = params("VOCT", vos=0, ib=0, v3a_tol=0, ilkg=0)
ps_all = params("VOCT", v3a_tol=V3A_TOL_25C)
off_r, scl_r = extremes(ps_r, pitch_offset), extremes(ps_r, pitch_scale)
off_a, scl_a = extremes(ps_all, pitch_offset), extremes(ps_all, pitch_scale)
worst_off_r, worst_scl_r = max(-off_r[0], off_r[2]), max(-scl_r[0], scl_r[2])
worst_off_a, worst_scl_a = max(-off_a[0], off_a[2]), max(-scl_a[0], scl_a[2])
print(f"      uncalibrated V/OCT, 1 % resistors only: offset {off_r[0]:+.0f} .. {off_r[2]:+.0f} cents, scale "
      f"{scl_r[0]:+.1f} .. {scl_r[2]:+.1f} cents per octave")
print(f"      uncalibrated V/OCT, resistors + 3V3A {V3A_TOL_25C:.1%} + Vos / Ib max + ADC leakage: offset "
      f"{off_a[0]:+.0f} .. {off_a[2]:+.0f} cents, scale {scl_a[0]:+.1f} .. {scl_a[2]:+.1f} cents per octave")
FW_FLAT = " ".join(FW_README.split())
# [2026-11-14: the README was reworded after the first run (it said "most of a semitone off and the octaves ten
# cents or more out", which these checks failed). The checks now read the stated figures from the README and
# hold them as "about" upper bounds: the worst case may not exceed a figure by more than 10 %, nor fall below 70 %
# of it (a figure that overstates the error by far is wrong too).]
m_r = re.search(r"With 1 % resistors the pitch can be up to about ([\d.]+) semitones off and the octaves up to about "
                r"(\d+) cents out", FW_FLAT)
m_a = re.search(r"at their tolerances too, up to about ([\d.]+) semitones and (\d+) cents per octave", FW_FLAT)
ck.check("D.readme_claim_found", bool(m_r and m_a),
         "firmware/README.md states the uncalibrated pitch error: 1 % resistors alone, and with 3V3A and the op-amp")


def stated(name, got, figure, unit, why):
    within(name, got, 0.7 * figure, 1.1 * figure, unit, f"README 'up to about {figure:g}{unit}': {why}")


if m_r and m_a:
    stated("D.readme_semitone", worst_off_r, 100 * float(m_r.group(1)), " cents", "1 % resistors alone, worst case")
    stated("D.readme_ten_cents", worst_scl_r, float(m_r.group(2)), " cents/oct", "1 % resistors alone, worst case")
    stated("D.readme_total_offset", worst_off_a, 100 * float(m_a.group(1)), " cents",
           f"resistors + 3V3A {V3A_TOL_25C:.1%} (25 C) + TL074 Vos / Ib max + ADC leakage")
    stated("D.readme_total_scale", worst_scl_a, float(m_a.group(2)), " cents/oct",
           f"resistors + 3V3A {V3A_TOL_25C:.1%}: the 3V3A tolerance alone is {1200 * V3A_TOL_25C:.0f} cents per "
           f"octave (VREF+ = 3V3A scales the jack signal, not the bias)")
# MODEL unpatched (lug to GND_F: 0 V in): Plaits' engine quantizer (voice.cc, HysteresisQuantizer2 over 24 engines,
# symmetric: 23 steps per Plaits unit, hysteresis 0.05); Plaits' MODEL stage is 0.2 units per volt, its default
# calibration scale from settings.cc
SETTINGS = harness.text("firmware", "src", "plaits", "settings.cc")
msc = re.search(r"CV_ADC_CHANNEL_MODEL\]\.scale = -?([\d.]+)f", SETTINGS)
model_scale = float(msc.group(1)) if msc else 1.0
next_model_v = (0.5 + 0.05) / (23 * 0.2 * model_scale)
moff = extremes(params("MODEL", v3a_tol=V3A_TOL_25C), lambda s: decoded("MODEL", 0.0, s))
ck.check("D.readme_model", max(-moff[0], moff[2]) > next_model_v,
         f"README: 'an unpatched MODEL input can select the model next to the one the buttons picked': MODEL reads "
         f"{moff[0]:+.3f} .. {moff[2]:+.3f} V unpatched (uncalibrated worst case), the next model is at "
         f"+-{next_model_v:.3f} V")


# =========================================================================== E: over-range, clamps, injection
def fit_diode(points, rs_from=None):
    """(Is, n, Rs) through the first two (IF, VF) points, Rs from the last one."""
    (i1, v1), (i2, v2) = sorted(points.items())[:2]
    n = (v2 - v1) / (math.log(i2 / i1) * S.VT_25C)
    i_s = i1 / math.exp(v1 / (n * S.VT_25C))
    i3, v3 = sorted(points.items())[-1]
    ideal = n * S.VT_25C * math.log(i3 / i_s)
    return i_s, n, max((v3 - ideal) / i3, 0.0)


BAT_MAX = fit_diode(BAT_VF_MAX)
BAT_TYP = fit_diode(BAT_VF_TYP)
print(f"      BAT85 model: max VF Is {BAT_MAX[0]:.2e} A n {BAT_MAX[1]:.2f} Rs {BAT_MAX[2]:.1f} ohm; typ Is "
      f"{BAT_TYP[0]:.2e} A n {BAT_TYP[1]:.2f} Rs {BAT_TYP[2]:.1f} ohm")
CLAMPS = [p for p in PARTS if p.kind == "BAT85"]
ck.check("E.clamps_found", sorted(S.node(p.nets["2"]) for p in CLAMPS if S.node(p.nets["1"]) == "3V3A") == [VOCT["adc"]]
         and sorted(S.node(p.nets["1"]) for p in CLAMPS if S.node(p.nets["2"]) == "GND") == [VOCT["adc"]],
         "one BAT85 from the V/OCT ADC pin to 3V3A (cathode, pin 1) and one from GND to it: "
         + ", ".join(f"{p.ref} K={p.nets['1']} A={p.nets['2']}" for p in CLAMPS))


def clamp_diodes(model=BAT_MAX):
    return [Diode(p.ref, S.node(p.nets["2"]), S.node(p.nets["1"]), *model) for p in CLAMPS]


def esd_diodes():
    return [Diode(f"ESD_{d['ain']}", "GND", d["adc"], ESD_IS, ESD_N, ESD_RS) for d in CH.values()]


def solve_full(ch, vjack, setting=(), model=BAT_MAX, force=None):
    kw = setting_kw(list(setting))
    d = CH[ch]
    cfg = Config(sources={d["jack"]: (vjack, 0.0)} if vjack is not None else None, diodes=clamp_diodes(model)
                 + esd_diodes(), force_out=force or {}, **kw)
    return solve(cfg) + (kw["v3a"],)


# the corner that drives the V/OCT output furthest: from the linear model, per sign
ps_v = params("VOCT", ib=0, ilkg=0)
far = {}
for sign in (-1, 1):
    ups = [at("VOCT", 12.0 * sign, [(p, p[3])])[0][VOCT["oa"]] >= at("VOCT", 12.0 * sign, [(p, p[2])])[0][VOCT["oa"]]
           for p in ps_v]
    far[sign] = [(p, (p[3] if u else p[2]) if sign < 0 else (p[2] if u else p[3])) for p, u in zip(ps_v, ups)]
rows = []
for vj in range(-12, 13):
    for corner in ("nom", "far"):
        setting = far[1 if vj > 0 else -1] if corner == "far" else []
        V, I, ID, v3a = solve_full("VOCT", float(vj), setting)
        # diode currents anode -> cathode: D21 pin -> 3V3A, D22 GND -> pin, ESD GND -> pin (all positive when on)
        rows.append((vj, corner, V[VOCT["adc"]], v3a, ID["D21"], ID["D22"], ID["ESD_A9"], V[VOCT["oa"]]))
BAT_TYP_ROWS = []
for vj in (-12.0, 12.0):
    V, I, ID, v3a = solve_full("VOCT", vj, far[1 if vj > 0 else -1], model=BAT_TYP)
    BAT_TYP_ROWS.append((vj, V[VOCT["adc"]] - (v3a if vj < 0 else 0.0)))
vpin_min = min(r[2] for r in rows)
vpin_max_rel = max(r[2] - r[3] for r in rows)
r_lo = min(rows, key=lambda r: r[2])
r_hi = max(rows, key=lambda r: r[2] - r[3])
print(f"      V/OCT -12 .. +12 V in: pin {vpin_min:+.3f} V (at {r_lo[0]:+d} V, {r_lo[1]}, D22 {r_lo[5] * 1e3:.2f} mA, "
      f"ESD {r_lo[6] * 1e6:.3f} uA) .. 3V3A {vpin_max_rel:+.3f} V (at {r_hi[0]:+d} V, D21 {r_hi[4] * 1e3:.2f} mA)")
within("E.voct_pin_low", vpin_min, STM_VIN_MIN, None, " V",
       f"V/OCT pin over -12 .. +12 V in (nominal and the corner driving furthest, BAT85 at max VF): D22 holds it "
       f"above -0.3 V (DS12556 Table 22 / 19)? {r_lo[5] * 1e3:.2f} mA in D22; a typical BAT85: "
       f"{BAT_TYP_ROWS[1][1]:+.3f} V")
# VERIFY 2026-11-13: the limit was VDDA + 0.3 V (the TT_xx figure); PA1 is FT_ha, whose operating maximum is
# Min(VDD, VDDA, VDD33USB) + 3.6 V, below 5.5 V (DS12556 Table 22 / 120). The worst case takes 3V3D and 3V3A at
# their low corners. The old VDDA + 0.3 V bound is printed for reference.
ft_op_max = min(min(V3D_NOM * (1 - V3D_TOL), V3A_NOM * (1 - V3A_TOL)) + STM_FT_VIN_OP_OVER, STM_FT_VIN_OP_CAP)
vpin_max_abs = max(r[2] for r in rows)
within("E.voct_pin_high", vpin_max_abs, None, ft_op_max, " V",
       f"V/OCT pin (PA1, FT_ha) at most Min(VDD, VDDA) + 3.6 V (< 5.5 V; DS12556 Table 22 / 120) with D21 a max-VF "
       f"BAT85: {r_hi[4] * 1e3:.2f} mA in D21, the pin {vpin_max_rel:+.3f} V above 3V3A (a typical BAT85: "
       f"{BAT_TYP_ROWS[0][1]:+.3f} V; above VREF+ the reading only clips); without D21 the stage would put "
       f"{max(r[7] for r in rows):.2f} V on it")
esd_max = max(r[6] for r in rows)
within("E.voct_esd_share", esd_max, None, STM_IINJ_FUNC_LEAK, " A",
       f"current the STM32's own ESD diode takes beside D22 (PA1: Table 57 functional susceptibility 0 mA; the -5 uA "
       f"leakage criterion): D22 carries {max(r[5] for r in rows) * 1e3:.2f} mA")
within("E.voct_injection_abs", esd_max, None, STM_IINJ_NEG_MAX, " A", "against IINJ(PIN) -5 mA (Table 20)")
# the TL074 section at its rails (only in a fault: a lost rail, a section latched)
sw_typ = VP_T - OUT_HEAD_TYP
for vrail in (sw_typ, -sw_typ):
    V, I, ID, v3a = solve_full("VOCT", None, force={VOCT["sec"]: vrail})
    tag = "pos" if vrail > 0 else "neg"
    clamp = "D21" if vrail > 0 else "D22"
    iclamp = abs(ID[clamp])
    within(f"E.voct_rail_{tag}.pin", V[VOCT["adc"]] - (v3a if vrail > 0 else 0.0),
           None if vrail > 0 else STM_VIN_MIN - 0.15, STM_ANALOG_OVER + 0.15 if vrail > 0 else None, " V",
           f"U4D output held at {vrail:+.1f} V (typ swing): {clamp} takes {iclamp * 1e3:.1f} mA, the pin within 0.15 V "
           f"of the window")
    within(f"E.voct_rail_{tag}.bat85_if", iclamp, None, BAT_IF_MAX, " A", f"{clamp} current against IF max 200 mA")
    if vrail < 0:
        within("E.voct_rail_neg.esd", ID["ESD_A9"], None, STM_IINJ_FUNC_LEAK, " A",
               "the STM32's own diode beside D22 with U4D at its negative rail (assumed ESD junction, see constants)")
    else:
        I3V3A_BACKFEED = iclamp
# the bias dividers and the pots are the only known loads on 3V3A; the LP2985 cannot sink: what D21 pushes into
# 3V3A at -12 V must be eaten by the load
pot_load = sum(V3A_NOM / (harness.ohms(p.value) * (1 + POT_TOL)) for p in PARTS if p.kind == "POT")
div_load = sum(V3A_NOM / (harness.ohms(d["rtop"].value) + harness.ohms(d["rbot"].value))
               for d in {d["bias"]: d for d in CH.values()}.values())
d21_m12 = max(r[4] for r in rows)
within("E.voct_3v3a_backfeed", d21_m12, None, pot_load + div_load, " A",
       f"D21 current at -12 V in (worst) into 3V3A, which the LP2985 cannot sink, against the board's own 3V3A load "
       f"(pots {pot_load * 1e3:.2f} mA at +20 % pot resistance, bias dividers {div_load * 1e3:.2f} mA); the Seed's "
       f"WM8731 AVDD / HPVDD and the STM32's VDDA are on 3V3A too (Seed schematic sheets 2 and 4), their current is "
       f"not confirmed here; with U4D at its rail it is {I3V3A_BACKFEED * 1e3:.1f} mA")


# the seven wide channels: no clamps
def thr(c, s, level):
    V0, v3a = at(c, 0.0, s)
    V1, _ = at(c, 1.0, s)
    a, b = V0[CH[c]["adc"]], V1[CH[c]["adc"]]
    target = STM_VIN_MIN if level == "low" else v3a + STM_ANALOG_OVER
    return (a - target) / (a - b)


win = {}
neg, pos = {}, {}
for c in WIDE:
    d = CH[c]
    ps = params(c)
    win[c] = (extremes(ps, lambda s: thr(c, s, "high"))[2], extremes(ps, lambda s: thr(c, s, "low"))[0])
    V, I, ID, v3a = solve_full(c, None, force={d["sec"]: -sw_typ})
    neg[c] = (ID[f"ESD_{d['ain']}"], V[d["adc"]])
    pos[c] = STM_TT_VIN_ABS_MAX if STM_TYPE[d["port"]].startswith("TT") else V3D_NOM + STM_FT_VIN_ABS_OVER
wc = min(win, key=lambda c: min(win[c][1], -win[c][0]))
within("E.wide_window", min(win[wc][1], -win[wc][0]), BUS_V * (1 + BUS_TOL), None, " V",
       "the jack voltage where a wide channel's pin leaves -0.3 .. VDDA + 0.3 V (worst corner, worst channel "
       f"{wc}: {win[wc][0]:+.1f} / {win[wc][1]:+.1f} V), against the most a +-12 V bus (+5 %) can deliver; the "
       f"injection there is the ESD diode's at -0.3 V, nil")
wn = max(neg, key=lambda c: neg[c][0])
within("E.wide_rail_neg", neg[wn][0], None, STM_IINJ_NEG_MAX, " A",
       f"a wide channel's section held at {-sw_typ:+.1f} V (a fault only: a ±12 V input cannot get it there): the "
       f"pin's ESD diode takes {neg[wn][0] * 1e3:.1f} mA through the 1k, pin at {neg[wn][1]:+.2f} V; "
       f"{', '.join(CH[c]['port'] for c in WIDE if CH[c]['port'] in STM_NO_NEG_INJECTION)} allow 0 mA (Table 57); "
       f"all seven at once {sum(v[0] for v in neg.values()) * 1e3:.0f} mA against the "
       f"{STM_IINJ_SUM_MAX * 1e3:.0f} mA sum")
wp = min(pos, key=lambda c: pos[c])
within("E.wide_rail_pos", sw_typ, None, pos[wp], " V",
       f"a wide channel's section held at +{sw_typ:.1f} V (a fault only): nothing clamps the pin; abs max "
       f"{pos[wp]:.1f} V on {CH[wp]['port']} ({STM_TYPE[CH[wp]['port']]}), "
       + ", ".join(f"{CH[c]['port']} {pos[c]:.1f}" for c in WIDE))


# =========================================================================== F: leakage
T_DOUBLE = 60.0 / math.log2(BAT_IR_TYP_5V_85C / BAT_IR_TYP_5V_25C)       # degrees per doubling, Fig. 4 typ
P_VR = math.log(BAT_IR_TYP_30V_25C / BAT_IR_TYP_5V_25C) / math.log(30 / 5)


def bat_ir_vishay_typ(vr, temp):
    """Vishay BAT85S Fig. 2 typical: log-interpolated in VR (1 .. 30 V) and in Tj (25 / 50 / 75 C); below 1 V the
    1 .. 3 V power law carried on (the barrier lowering keeps falling) times the junction's (1 - exp(-VR / VT))."""
    temps = sorted(BAT_V_IR)
    lv = [math.log(v) for v in BAT_V_VR]

    def at_t(t):
        row = [math.log(i * 1e-6) for i in BAT_V_IR[t]]
        if vr >= 1.0:
            return math.exp(float(np.interp(math.log(vr), lv, row)))
        s = (row[1] - row[0]) / (lv[1] - lv[0])
        return math.exp(row[0] + s * math.log(max(vr, 1e-3))) * (1 - math.exp(-vr / S.VT_25C))
    t = min(max(temp, temps[0]), temps[-1])
    k = next(i for i in range(len(temps) - 1) if temps[i] <= t <= temps[i + 1])
    a, b = math.log(at_t(temps[k])), math.log(at_t(temps[k + 1]))
    return math.exp(a + (b - a) * (t - temps[k]) / (temps[k + 1] - temps[k]))


def bat_ir(vr, temp, case, shape="philips"):
    """Reverse current at vr (> 0) and temp. 'philips': Fig. 4's 25 C magnitude and its doubling every T_DOUBLE;
    above 5 V Fig. 4's power law, below 5 V (where Fig. 4 has no data) the Vishay Fig. 2 VR shape scaled to it.
    'vishay': the Vishay BAT85S Fig. 2 surface. max: the 2 uA maximum at 25 V / 25 C carried to lower VR and
    higher temperature by the same typical shape.
    VERIFY 2026-11-13: the Philips power law VR^0.59 was carried down to 0.1 V; Vishay's curve, which reaches 1 V,
    flattens to about VR^0.2 below 3 V, so the old model overstated the D21 / D22 imbalance at the range ends."""
    if vr <= 0:
        return 0.0
    if shape == "vishay":
        typ = bat_ir_vishay_typ(vr, temp)
        return typ if case == "typ" else typ * BAT_IR_MAX_25V / BAT_V_IR_25V_25C
    tf = 2 ** ((temp - 25.0) / T_DOUBLE)
    if vr >= 5.0:
        shape25 = (vr / 5.0) ** P_VR
    else:
        shape25 = bat_ir_vishay_typ(vr, 25.0) / bat_ir_vishay_typ(5.0, 25.0)
    typ = BAT_IR_TYP_5V_25C * shape25 * tf
    if case == "typ":
        return typ
    return typ * BAT_IR_MAX_25V / (BAT_IR_TYP_5V_25C * (25.0 / 5.0) ** P_VR)


def voct_err_cents(vjack, temp, case, which=("D21", "D22"), shape="philips"):
    """V/OCT error in cents from the clamp leakage alone at one jack voltage."""
    V = run({VOCT["jack"]: (vjack, 0.0)})
    vp = V[VOCT["adc"]]
    inj = 0.0
    if "D21" in which:
        inj += bat_ir(V3A_NOM - vp, temp, case, shape)        # reverse current from 3V3A into the pin
    if "D22" in which:
        inj -= bat_ir(vp, temp, case, shape)                  # out of the pin to GND
    V2 = run({VOCT["jack"]: (vjack, 0.0)}, inject={VOCT["adc"]: inj})
    return 1200 * (decode("VOCT", V2[VOCT["adc"]]) - decode("VOCT", vp))


grid = [v / 2 for v in range(-5, 14)]          # -2.5 .. +6.5 V
print(f"      BAT85 reverse current model: Philips x2 every {T_DOUBLE:.1f} C, VR^{P_VR:.2f} above 5 V (Vishay shape below); Vishay BAT85S Fig. 2 "
      f"surface; each check takes the worse of the two makers' typical shapes (the BOM's Tayda part: maker unknown)")
for temp in (25.0, 55.0):
    worst = (-1.0, None)
    for shape in ("philips", "vishay"):
        e = [voct_err_cents(v, temp, "typ", shape=shape) for v in grid]
        e25 = [voct_err_cents(v, 25.0, "typ", shape=shape) for v in grid]
        # a two-point calibration at 1 V and 3 V, done at 25 C, removes offset and scale at 25 C
        i1, i3 = grid.index(1.0), grid.index(3.0)
        slope = (e25[i3] - e25[i1]) / 2.0
        resid = [ei - (e25[i1] + slope * (v - 1.0)) for v, ei in zip(grid, e)]
        print(f"      BAT85 typ leakage ({shape}) at {temp:.0f} C: error {min(e):+.2f} .. {max(e):+.2f} cents over "
              f"-2.5 .. +6.5 V; after a 25 C calibration {min(resid):+.2f} .. {max(resid):+.2f} cents")
        worst = max(worst, (max(abs(x) for x in resid), shape))
    within(f"F.bat85_typ_{temp:.0f}C", worst[0], None, 2.0, " cents",
           f"V/OCT tracking error from the D21 / D22 typical leakage through the 1k, after a two-point calibration "
           f"at 25 C, -2.5 .. +6.5 V (2 cents allowed); worse shape: {worst[1]}")
for one in ("D21", "D22"):
    drifts = {shape: max(abs(voct_err_cents(v, 55.0, "max", (one,), shape) - voct_err_cents(v, 25.0, "max", (one,), shape))
                         for v in grid) for shape in ("philips", "vishay")}
    within(f"F.bat85_max_drift.{one}", max(drifts.values()), None, 5.0, " cents",
           f"{one} at the datasheet maximum (2 uA at 25 V, 25 C, carried to the 0..3.3 V here and to 55 C by the "
           f"typical curves), the other clamp at 0: the change of the V/OCT error from 25 to 55 C, which no 25 C "
           f"calibration removes (5 cents allowed): Philips shape {drifts['philips']:.1f}, Vishay BAT85S shape "
           f"{drifts['vishay']:.1f} cents")
e_lkg = abs(1200 * (decode("VOCT", adc_at("VOCT", 0.0, inject={VOCT["adc"]: STM_ILKG_MAX})) -
                    decode("VOCT", adc_at("VOCT", 0.0))))
within("F.stm_leak_voct", e_lkg, None, 1.0, " cents", "the STM32's +-250 nA pin leakage through the 1k, V/OCT")
w_lkg = abs(decode("MODEL", adc_at("MODEL", 0.0, inject={CH["MODEL"]["adc"]: STM_ILKG_MAX})) -
            decode("MODEL", adc_at("MODEL", 0.0)))
within("F.stm_leak_wide", w_lkg, None, ADC_LSB12 / CH["MODEL"]["g"], " V",
       "the same on a wide channel, in jack volts, against one 12-bit step at the jack")


# =========================================================================== G: the normalization probe
PROBE_PIN = next(pin for pin, (n, net) in C.SEED.items() if net == "PROBE")
PROBE_R = [p for p in PARTS if p.kind == "R" and "PROBE_F" in p.nets.values()]
NORM = [c for c, d in CH.items() if d["lug"] and d["lug"].startswith("TN_")]
ck.check("G.probe_network", sorted(NORM) == sorted(["TIMBRE", "FM", "MORPH", "TRIG", "LEVEL"])
         and len(PROBE_R) == len(NORM),
         f"D14 (Seed pin {PROBE_PIN}) through {', '.join(p.ref for p in PROBE_R)} to the lugs of {', '.join(NORM)} "
         f"(design.md: TIMBRE, FM, MORPH, TRIG, LEVEL)")
ROUT_STM = STM_VOH_DROP_8MA / STM_IO_SPEC         # a bound on the pin's output resistance from Table 59


def probe_run(level, v3d, rtol=None, v3a=V3A_NOM, rout=ROUT_STM):
    V, I, ID = solve(Config(probe=(v3d if level else 0.0, rout), rtol=rtol or {}, v3a=v3a))
    ip = sum((V["PROBE"] - V[S.node(p.nets["1"])]) / (harness.ohms(p.value) * (rtol or {}).get(p.ref, 1.0))
             for p in PROBE_R)
    return V, ip


DOC_PROBE = re.search(r"probe's swing on Plaitsy, ([\d.]+) V / ([\d.]+) V\s+at the jack, straddles Plaits' thresholds "
                      r"at about ([\d.]+) V", " ".join(DESIGN.split()))
ck.check("G.doc_found", DOC_PROBE is not None, "design.md: the probe's swing and Plaits' threshold")
P_LO, P_HI, P_TH = (float(x) for x in DOC_PROBE.groups()) if DOC_PROBE else (0.13, 3.13, 0.83)
Vh, iph = probe_run(True, V3D_NOM, rout=0.0)
Vl, ipl = probe_run(False, V3D_NOM, rout=0.0)
for c in NORM:
    d = CH[c]
    close(f"G.jack_high.{c}", Vh[d["cv"]], P_HI, 0.015, " V",
          f"design.md: probe high at the jack (3V3D {V3D_NOM:.3f} V, an ideal pin)")
    close(f"G.jack_low.{c}", Vl[d["cv"]], P_LO, 0.005, " V", "design.md: probe low at the jack (an ideal pin)")
    within(f"G.adc_inside.{c}", min(Vh[d["adc"]], Vl[d["adc"]]), 0.0, V3A_NOM, " V",
           f"ADC pin {Vl[d['adc']]:.3f} V (probe low) / {Vh[d['adc']]:.3f} V (probe high) inside the range")
# worst case: 3V3D low / high, resistors to the corners that pull the jack voltage towards the threshold
rk = [p.ref for p in PROBE_R] + [CH[c]["rin"].ref for c in NORM] + [CH["MODEL"]["rtop"].ref, CH["MODEL"]["rbot"].ref]
hi_min, lo_max = 1e9, -1e9
for v3d in (V3D_NOM * (1 - V3D_TOL), V3D_NOM * (1 + V3D_TOL)):
    for v3a in (V3A_NOM * (1 - V3A_TOL), V3A_NOM * (1 + V3A_TOL)):
        for sg in (-1, 1):
            rt = {}
            for ref in rk:
                rt[ref] = 1 + sg * R_TOL if ref.startswith("R") and BYREF[ref] in PROBE_R else 1 - sg * R_TOL
            Vh2, _ = probe_run(True, v3d, rt, v3a)
            Vl2, _ = probe_run(False, v3d, rt, v3a)
            hi_min = min(hi_min, min(Vh2[CH[c]["cv"]] for c in NORM))
            lo_max = max(lo_max, max(Vl2[CH[c]["cv"]] for c in NORM))
within("G.margin_high", hi_min - P_TH, 0.5, None, " V", f"worst-case probe-high jack voltage {hi_min:.3f} V above "
       f"Plaits' {P_TH} V threshold")
within("G.margin_low", P_TH - lo_max, 0.5, None, " V", f"worst-case probe-low jack voltage {lo_max:.3f} V below it")
_, ip_max = probe_run(True, V3D_NOM * (1 + V3D_TOL), {p.ref: 1 - R_TOL for p in PROBE_R}, V3A_NOM * (1 - V3A_TOL), 0.0)
within("G.probe_current", ip_max, None, STM_IO_SPEC, " A",
       f"D14 sources {iph * 1e6:.0f} uA nominal into the five lugs ({ip_max * 1e6:.0f} uA worst), inside the "
       f"8 mA its VOH is specified at")
# the firmware subtracts kProbeLowJackVoltage = bias A * 10 / 110 from the normalized inputs' zeros
mk = re.search(r"kProbeLowJackVoltage = kBiasWide \* ([\d.]+)f / \(([\d.]+)f \+ ([\d.]+)f\)", CVADC)
fw_plow = (V3A_NOM * CH["MODEL"]["k"]) * float(mk.group(1)) / (float(mk.group(2)) + float(mk.group(3))) if mk else None
ck.check("G.fw_probe_low_found", fw_plow is not None, "cv_adc.cc kProbeLowJackVoltage")
worst = 0.0
for c in NORM:
    d = CH[c]
    for v3a in (V3A_NOM * (1 - V3A_TOL), V3A_NOM, V3A_NOM * (1 + V3A_TOL)):
        for sg in (-1, 1):
            rt = {d["rin"].ref: 1 + sg * R_TOL, d["rtop"].ref: 1 + sg * R_TOL, d["rbot"].ref: 1 - sg * R_TOL}
            for p in PROBE_R:
                rt[p.ref] = 1 - sg * R_TOL
            V, I, ID = solve(Config(probe=(0.0, ROUT_STM), rtol=rt, v3a=v3a))
            Vz, _, _ = solve(Config(sources={d["jack"]: (0.0, 0.0)}, rtol=rt, v3a=v3a))
            seen = decode(c, V[d["adc"]], v3a) - decode(c, Vz[d["adc"]], v3a)
            worst = max(worst, abs(seen - (fw_plow or 0.0)))
within("G.fw_probe_low_residual", worst, None, ADC_LSB12 / CH["MODEL"]["g"], " V",
       f"unpatched with the probe held low the inputs read the probe-low divider above a patched 0 V; the firmware "
       f"subtracts {fw_plow:.4f} V from the zeros it measures: the rest at the corners (pin at 50 ohm), against one "
       f"12-bit step at the jack")
dv = max(abs(run({CH[c]["jack"]: (2.0, 0.0)}, probe=(V3D_NOM, ROUT_STM))[CH[c]["adc"]]
             - run({CH[c]["jack"]: (2.0, 0.0)}, probe=(0.0, ROUT_STM))[CH[c]["adc"]]) for c in NORM)
within("G.patched_unaffected", dv, None, 1e-6, " V", "a patched normalized jack (switch open) does not see the probe")

# =========================================================================== H: pots through the 74HC4051
MUX = next(p for p in PARTS if p.kind == "MUX")
POTS = [p for p in PARTS if p.kind == "POT"]
mux_pins = {S.node(v): k for k, v in MUX.nets.items()}
ck.check("H.mux_supply", S.node(MUX.nets["16"]) == "3V3A" and S.node(MUX.nets["7"]) == "GND"
         and S.node(MUX.nets["8"]) == "GND" and S.node(MUX.nets["6"]) == "GND",
         f"U1 VCC (16) {MUX.nets['16']}, VEE (7) {MUX.nets['7']}, GND (8) {MUX.nets['8']}, /E (6) {MUX.nets['6']}: "
         f"single supply 0 .. 3V3A, always enabled")
ck.check("H.wiper_range", all(S.node(p.nets["1"]) == "GND" and S.node(p.nets["3"]) == "3V3A" for p in POTS),
         "every pot between GND_F and 3V3A_F, the mux's own rails: the wipers stay inside VEE .. VCC")
ck.check("H.channel7", S.node(MUX.nets["4"]) == "GND" and all(m[4] != 7 for m in C.POTS),
         "Y7 (pin 4) on GND_F, no pot on it (InitMux scans 7 channels)")
ck.check("H.mux_out", S.node(MUX.nets["3"]) == "MUX_OUT" and parts_on("MUX_OUT", "R") == [],
         "Z (pin 3) straight to the Seed's A10 (MUX_OUT), no series resistor")


def ron_33(v):
    return v * (4.5 / 2 - MUX_RON_VT) / (V3A_NOM / 2 - MUX_RON_VT)


RON_TYP, RON_25, RON_85 = ron_33(MUX_RON_45["typ"]), ron_33(MUX_RON_45["max25"]), ron_33(MUX_RON_45["max85"])
print(f"      74HC4051 Ron at 3.3 V (extrapolated from 4.5 V, mid-rail conductance ~ VCC/2 - {MUX_RON_VT} V): typ "
      f"{RON_TYP:.0f}, max {RON_25:.0f} (25 C) / {RON_85:.0f} ohm (85 C); 6 V figures {MUX_RON_6['max25']:.0f} / "
      f"{MUX_RON_6['max85']:.0f} ohm")
rth = max(harness.ohms(p.value) for p in POTS) * (1 + POT_TOL) / 4          # mid rotation
for temp, iiz, ron in (("25C", MUX_IIZ_25C, RON_25), ("85C", MUX_IIZ_85C, RON_85)):
    err = (STM_ILKG_MAX + iiz) * (rth + ron)
    within(f"H.leak_error_{temp}", err / V3A_NOM, None, 0.001 if temp == "25C" else 0.0025, "",
           f"(ADC {STM_ILKG_MAX * 1e9:.0f} nA + 4051 IIZ {iiz * 1e6:.1f} uA) x (pot {rth / 1e3:.1f}k at mid + Ron "
           f"{ron:.0f}) = {err * 1e3:.2f} mV of full scale ({'0.1' if temp == '25C' else '0.25'} % allowed: a "
           f"fraction of a semitone on FREQUENCY's 8 octaves)")


def track_net_resistance(board, net, src, loads):
    """Voltage drops (V) from pad src to each load pad on the tracks of one net, loads {pad: amps drawn}.
    Nodes are track ends (both layers meet at shared ends: vias), pads join the ends inside them, a track end
    landing on another track splits it."""
    tr = [t for t in board.tracks if t["net"] == net]
    pts = []
    for t in tr:
        pts += [t["a"], t["b"]]
    key = {}

    def nid(p):
        k = (round(p[0], 2), round(p[1], 2))
        return key.setdefault(k, len(key))

    edges = []
    for t in tr:
        on = [t["a"], t["b"]]
        ax, ay = t["a"]
        bx, by = t["b"]
        L = math.hypot(bx - ax, by - ay)
        for p in pts:
            if p in on or L < 1e-9:
                continue
            u = ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L ** 2
            if 0 < u < 1 and math.hypot(ax + u * (bx - ax) - p[0], ay + u * (by - ay) - p[1]) < t["w"] / 2:
                on.append(p)
        on.sort(key=lambda p: (p[0] - ax) ** 2 + (p[1] - ay) ** 2)
        for p, q in zip(on, on[1:]):
            r = CU_RHO * math.hypot(q[0] - p[0], q[1] - p[1]) * 1e-3 / (t["w"] * 1e-3 * CU_T)
            edges.append((nid(p), nid(q), max(r, 1e-6)))
    pads = {}
    for ref, num in [src] + list(loads):
        pad = board.parts[ref]["pads"][num]
        pid = len(key) + len(pads)
        pads[(ref, num)] = pid
        for k, i in list(key.items()):
            if pad.d_point(k) <= 0.05:
                edges.append((pid, i, 1e-4))
    n = len(key) + len(pads)
    G = np.zeros((n, n))
    for a, b, r in edges:
        G[a, a] += 1 / r
        G[b, b] += 1 / r
        G[a, b] -= 1 / r
        G[b, a] -= 1 / r
    G += np.eye(n) * 1e-9
    s = pads[src]
    I = np.zeros(n)
    for pd, amps in loads.items():
        I[pads[pd]] -= amps
    I[s] += sum(loads.values())
    keep = [i for i in range(n) if i != s]
    v = np.zeros(n)
    v[keep] = np.linalg.solve(G[np.ix_(keep, keep)], I[keep])
    return {pd: -(v[pads[pd]] - v[s]) for pd in loads}, len(edges)


R = harness.routed()
pot_i = {p.ref: V3A_NOM / (harness.ohms(p.value) * (1 - POT_TOL)) for p in POTS}
i_fb = sum(pot_i.values()) + MUX_ICC_85C
loads_fb = {(p.ref, "3"): pot_i[p.ref] for p in POTS}
loads_fb[("U1", "16")] = MUX_ICC_85C
drop_fb, nfb = track_net_resistance(R.face, "3V3A_F", ("HF2", "3"), loads_fb)
i_mb = {("H2", "3"): i_fb}
for d in {d["bias"]: d for d in CH.values()}.values():
    i_mb[(d["rtop"].ref, "1")] = V3A_NOM / (harness.ohms(d["rtop"].value) + harness.ohms(d["rbot"].value))
drop_mb, nmb = track_net_resistance(R.main, "3V3A", ("U2", "21"), i_mb)
worst_pot = max((drop_mb[("H2", "3")] + i_fb * HDR_CONTACT_R + drop_fb[(p.ref, "3")], p.ref) for p in POTS)
print(f"      3V3A: {i_fb * 1e3:.2f} mA to the faceplate (pots at -20 %, mux ICC max); drop Seed pin 21 -> H2.3 "
      f"{drop_mb[('H2', '3')] * 1e6:.0f} uV, header {i_fb * HDR_CONTACT_R * 1e6:.0f} uV, HF2.3 -> pots "
      f"{min(drop_fb.values()) * 1e6:.0f} .. {max(drop_fb.values()) * 1e6:.0f} uV ({nmb} / {nfb} track pieces)")
within("H.pot_cw_drop", worst_pot[0] / V3A_NOM, None, 0.001, "",
       f"3V3A_F at {worst_pot[1]}'s CW end below the ADC's VREF+ (3V3A at the Seed): {worst_pot[0] * 1e3:.3f} mV of "
       f"full scale over the routed tracks and the header (0.1 % allowed)")
bias_drop = max(v for k, v in drop_mb.items() if k[0] != "H2")
within("H.bias_feed_drop", bias_drop * CH["MODEL"]["k"] * (1 + CH["MODEL"]["g"]) / CH["MODEL"]["g"], None,
       ADC_LSB12 / CH["MODEL"]["g"], " V",
       f"the bias dividers' 3V3A {bias_drop * 1e6:.1f} uV below the Seed's pin (the faceplate current shares the "
       f"track) in jack volts, against one 12-bit step")
def vih_at(vcc):
    return MUX_VIH_2V + (vcc - 2.0) * (MUX_VIH_45 - MUX_VIH_2V) / 2.5     # linear between the 2 V and 4.5 V rows


vih = vih_at(V3A_NOM * (1 + V3A_TOL))
voh = V3D_NOM * (1 - V3D_TOL) - STM_VOH_DROP_8MA * 0.01         # the address lines draw < 0.1 mA
within("H.addr_vih", voh - vih, 0.3, None, " V",
       f"MUX_S0..2 high {voh:.2f} V (3V3D min) against the 4051's VIH {vih:.2f} V at 3V3A max (interpolated between "
       f"its 2 V and 4.5 V figures), 0.3 V margin wanted")
within("H.addr_over_vcc", V3D_NOM * (1 + V3D_TOL) - V3A_NOM * (1 - V3A_TOL), None, MUX_ABS_OVER - 0.2, " V",
       "3V3D-driven address lines above the 3V3A-powered mux's VCC (max 3V3D - min 3V3A), against the 0.5 V where "
       "its input diodes conduct (abs max), 0.2 V margin; the recommended VI <= VCC is not met in that corner")

# =========================================================================== I: LEDs through the 74HC595s
SR = {p.ref: p for p in PARTS if p.kind == "HC595"}
LEDS = {p.ref: p for p in PARTS if p.kind == "LED_RG"}
lines = []
for ref, p in SR.items():
    ck.check(f"I.supply.{ref}", p.nets["16"] == "3V3D_F" and S.node(p.nets["16"]) == "3V3D"
             and p.nets["8"] == "GND_D_F" and S.node(p.nets["8"]) == "GND",
             f"{ref} VCC {p.nets['16']} (the Seed's 3V3D through H3), GND {p.nets['8']} (the main board's GND "
             f"through H3)")
    for pin in C.HC595_OUTS:
        net = p.nets.get(pin)
        if not net:
            continue
        r = next(q for q in PARTS if q.kind == "R" and net in q.nets.values())
        led_net = r.nets["2"] if r.nets["1"] == net else r.nets["1"]
        led, lpin = next((q, k) for q in LEDS.values() for k, v in q.nets.items() if v == led_net)
        colour = "R" if lpin == "1" else "G"
        lines.append((ref, pin, r, led.ref, colour, led.nets["2"]))
ck.check("I.lines", len(lines) == 16 and all(x[5] == "GND_D_F" for x in lines),
         f"{len(lines)} LED lines from the 595 outputs through a resistor to an anode, cathodes on GND_D_F")


def rout_595(case):
    i, vmin25, vminfull, vtyp = HC595_VOH[4.5]
    v = {"typ": vtyp, "25": vmin25, "full": vminfull}[case]
    return (4.5 - v) / i * (4.5 - HC595_PMOS_VT) / (V3A_NOM - HC595_PMOS_VT)


R595 = {c: rout_595(c) for c in ("typ", "25", "full")}
print(f"      74HC595 output resistance at 3.3 V (extrapolated from VOH at 4.5 V / 6 mA, x (4.5 - {HC595_PMOS_VT}) / "
      f"(3.3 - {HC595_PMOS_VT})): typ {R595['typ']:.0f}, max {R595['25']:.0f} (25 C) / {R595['full']:.0f} ohm "
      f"(-40..85 C)")
cur = {}
for col in ("R", "G"):
    vmin, vtyp, vmax = LED_VF[col]
    rr = harness.ohms(next(x[2] for x in lines if x[4] == col).value)
    nom = (V3D_NOM - vtyp) / (rr + R595["typ"])
    lo = (V3D_NOM * (1 - V3D_TOL) - vmax) / (rr * (1 + R_TOL) + R595["full"])
    hi = (V3D_NOM * (1 + V3D_TOL) - vmin) / (rr * (1 - R_TOL))
    cur[col] = (lo, nom, hi)
    within(f"I.current_typ.{col}", nom, 0.75 * LED_I_DESIGN, 1.25 * LED_I_DESIGN, " A",
           f"{'red' if col == 'R' else 'green'}: (3V3D - VF typ {vtyp} V) / ({rr:.0f} + {R595['typ']:.0f} ohm) against "
           f"design.md's 'about {LED_I_DESIGN * 1e3:g} mA per colour' (+-25 %), the {LED_PARTS_NOTE}")
    within(f"I.current_min.{col}", lo, LED_I_VISIBLE, None, " A",
           f"worst case: 3V3D -{V3D_TOL:.1%}, VF max {vmax} V ({LED_PART}, at 20 mA), R +1 %, the 595's VOH at 85 C")
    within(f"I.current_max.{col}", hi, None, HC595_VOH[4.5][0], " A",
           "best case (VF min, 3V3D high, no output drop) inside the 6 mA the 595's VOH is specified at")
per595 = max(8 * cur[c][2] for c in cur)
within("I.per_595_total", per595, None, HC595_ICC_MAX, " A",
       "all eight outputs of one 595 lit at the best-case current, against 70 mA through VCC / GND (abs max)")
within("I.per_output", max(cur[c][2] for c in cur), None, HC595_IO_MAX, " A", "per output, against 35 mA (abs max)")
btn_i_max = 2 * (V3D_NOM * (1 + V3D_TOL) - 1.7) / (harness.ohms(BYREF["R60"].value) * (1 - R_TOL))
led_total = 8 * (cur["R"][2] + cur["G"][2]) + btn_i_max + ip_max
within("I.3v3d_load", led_total, None, TPS_IOUT_MAX - SEED_OWN_3V3D, " A",
       f"16 LEDs + 2 button LEDs + the probe at best-case current ({led_total * 1e3:.0f} mA) on the Seed's 3V3D, "
       f"against the TPS6217x's 0.5 A less an assumed {SEED_OWN_3V3D * 1e3:.0f} mA for the Seed itself")

# =========================================================================== J: button LEDs
BTN_R = []
for io_pin, (lname, io_net) in ((k, v) for k, v in C.SEED.items() if v[1] and v[1].startswith("BTN_LED")):
    r = next(p for p in PARTS if p.kind == "R" and io_net in p.nets.values())
    far_net = r.nets["2"] if r.nets["1"] == io_net else r.nets["1"]
    fb = next(fbn for _, _, pins in C.HEADERS for mb, fbn in pins if mb == far_net)
    sw = next(p for p in PARTS if p.kind == "SWLED" and p.nets.get("5") == fb)
    ok = sw.nets["6"] == "GND_D_F"
    ck.check(f"J.path.{lname}", ok, f"{lname} (Seed pin {io_pin}) -> {r.ref} {r.value} -> {far_net} -> header -> {fb} "
                                    f"-> {sw.ref} pin 5 (anode), pin 6 {sw.nets['6']}")
    BTN_R.append((lname, r))
    hi = (V3D_NOM * (1 + V3D_TOL) - 1.7) / (harness.ohms(r.value) * (1 - R_TOL))
    within(f"J.gpio_current.{lname}", hi, None, STM_IO_SPEC, " A", "the GPIO's current at most, inside the 8 mA "
                                                                    "its VOH is specified at")
gpio_sum = sum((V3D_NOM * (1 + V3D_TOL) - 1.7) / (harness.ohms(r.value) * (1 - R_TOL)) for _, r in BTN_R) + ip_max
within("J.gpio_total", gpio_sum, None, STM_IO_SUM_MAX, " A",
       f"button LEDs + probe sourced by the STM32 at most, against {STM_IO_SUM_MAX * 1e3:.0f} mA for all I/Os "
       f"(Table 20; {STM_IO_ABS_MAX * 1e3:.0f} mA per pin; VOL at {STM_IO_SPEC * 1e3:.0f} mA <= {STM_VOL_8MA} V)")
for colour, (vmin, vtyp, vmax) in BTN_LED_VF.items():
    rr = max(harness.ohms(r.value) for _, r in BTN_R)
    typ = max(V3D_NOM - vtyp, 0.0) / (rr + ROUT_STM / 2)
    lo = max(V3D_NOM * (1 - V3D_TOL) - vmax, 0.0) / (rr * (1 + R_TOL) + ROUT_STM)
    tag = colour.split(" (")[0].split(" /")[0] + ("_InGaN" if "InGaN" in colour else "_GaP" if "GaP" in colour else "")
    ck.check(f"J.current.{tag}", typ >= LED_I_LIT and lo >= LED_I_VISIBLE,
             f"{colour} button LED (VF {vmin} / {vtyp} / {vmax} V assumed) through "
             f"{' / '.join(r.ref for _, r in BTN_R)} {rr:.0f} ohm: {typ * 1e3:.2f} mA typical (>= 1 mA wanted), "
             f"{lo * 1e3:.2f} mA worst (>= 0.5 mA wanted)"
             + ("" if "GaP" in colour or colour in ("red", "yellow / orange") else
                "; not a GaAsP / GaP colour, which is all Thonk's drawing PB01-109TL lists"))

# =========================================================================== K: the breakout's outputs
for j4, net in (("J4-1", "OUT"), ("J4-3", "AUX")):
    fb = next(fbn for _, _, pins in C.HEADERS for mb, fbn in pins if mb == net)
    hdr = next((ref, i + 1) for ref, _, pins in C.HEADERS for i, (mb, fbn) in enumerate(pins) if mb == net)
    jack = next(p for p in PARTS if p.kind == "JACK" and p.nets.get("3") == fb)
    mbpad = R.main.parts["U2"]["pads"][j4].net
    hpad = R.main.parts[hdr[0]]["pads"][str(hdr[1])].net
    fpad = R.face.parts[C.fb_ref(hdr[0])]["pads"][str(hdr[1])].net
    jpad = R.face.parts[jack.ref]["pads"]["3"].net
    spad = R.face.parts[jack.ref]["pads"]["1"].net
    ck.check(f"K.path.{net}", C.SEED[j4][1] == net and mbpad == net and hpad == net and fpad == fb and jpad == fb
             and spad == "GND_F",
             f"breakout {j4} ({C.SEED[j4][0]}) -> {net} -> {hdr[0]}.{hdr[1]} -> {fb} -> {jack.ref} tip ({jack.label}), "
             f"sleeve GND_F; routed pads: {mbpad} / {hpad} / {fpad} / {jpad} / {spad}")
print("      the breakout's output stage (2 x TL074CPWR, 100k / 10k / 1k, 47p / 560p in its BOM): no schematic in the "
      "sources here (oshwlab not readable), so its gain and DC offset are not checked")


# =========================================================================== L: ground currents on the main board
def poly_mask(px, py, poly):
    """Even-odd point-in-polygon for many points (vectorised over the points, looped over the edges)."""
    xs = np.array([p[0] for p in poly])
    ys = np.array([p[1] for p in poly])
    inside = np.zeros(px.shape, bool)
    sel = (px >= xs.min()) & (px <= xs.max()) & (py >= ys.min()) & (py <= ys.max())
    qx, qy = px[sel], py[sel]
    ins = np.zeros(qx.shape, bool)
    x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    for i in range(len(xs)):
        y1, yb = ys[i], y2[i]
        if y1 == yb:
            continue
        cross = (y1 > qy) != (yb > qy)
        xint = xs[i] + (qy - y1) * (x2[i] - xs[i]) / (yb - y1)
        ins ^= cross & (qx < xint)
    inside[sel] = ins
    return inside


def seg_mask(px, py, a, b, half):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1) if L2 > 0 else np.zeros(px.shape)
    return (px - ax - u * dx) ** 2 + (py - ay - u * dy) ** 2 <= half * half


class Sheet:
    """The GND copper of one board on a square grid, both layers, solved for a current in and out."""

    def __init__(self, board, net, h=0.4):
        x1, y1, x2, y2 = board.outline
        self.h = h
        xs = np.arange(x1 + h / 2, x2, h)
        ys = np.arange(y1 + h / 2, y2, h)
        self.nx, self.ny = len(xs), len(ys)
        PX, PY = np.meshgrid(xs, ys, indexing="ij")
        self.PX, self.PY = PX, PY
        masks = {}
        for layer in (1, 2):
            m = np.zeros(PX.shape, bool)
            for isl in board.islands:
                if isl.net == net and isl.layer == layer:
                    a = poly_mask(PX, PY, isl.outline)
                    for hole in isl.holes:
                        a &= ~poly_mask(PX, PY, hole)
                    m |= a
            for t in board.tracks:
                if t["net"] == net and t["layer"] == layer:
                    m |= seg_mask(PX, PY, t["a"], t["b"], max(t["w"] / 2, h / 2))
            for p0, p1, lay, nn in board.spokes:
                if nn == net and lay == layer:
                    m |= seg_mask(PX, PY, p0, p1, h / 2)
            masks[layer] = m
        self.link = np.zeros(PX.shape, bool)
        self.pad_cells = {}
        for pad in board.pads:
            if pad.net != net:
                continue
            cells = seg_mask(PX, PY, (pad.x, pad.y), (pad.x, pad.y), max(pad.r * 0.8, h * 0.75))
            self.pad_cells[(pad.ref, pad.num)] = cells
            self.link |= cells
            for layer in (1, 2):
                masks[layer] |= cells
        for v in board.vias:
            if v["net"] == net:
                cells = seg_mask(PX, PY, v["c"], v["c"], max(v["r"], h * 0.75))
                self.link |= cells
                for layer in (1, 2):
                    masks[layer] |= cells
        self.masks = masks
        idx = -np.ones((2,) + PX.shape, int)
        n = 0
        for li, layer in enumerate((1, 2)):
            k = int(masks[layer].sum())
            idx[li][masks[layer]] = np.arange(n, n + k)
            n += k
        self.idx, self.n = idx, n
        gs = CU_T / CU_RHO                  # sheet conductance between two adjacent square cells
        ei, ej, eg = [], [], []
        for li in range(2):
            a = idx[li]
            for sl0, sl1 in (((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                             ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
                p, q = a[sl0], a[sl1]
                ok = (p >= 0) & (q >= 0)
                ei.append(p[ok])
                ej.append(q[ok])
                eg.append(np.full(int(ok.sum()), gs))
        both = (idx[0] >= 0) & (idx[1] >= 0) & self.link
        ei.append(idx[0][both])
        ej.append(idx[1][both])
        eg.append(np.full(int(both.sum()), VIA_G))
        self.ei, self.ej, self.eg = np.concatenate(ei), np.concatenate(ej), np.concatenate(eg)

    def nodes_of(self, pad):
        c = self.pad_cells[pad]
        return np.concatenate([self.idx[0][c & (self.idx[0] >= 0)], self.idx[1][c & (self.idx[1] >= 0)]])

    def solve(self, src, sinks, amps=1.0, tol=1e-12, maxit=40000):
        """Potentials with amps into pad src and every pad in sinks held at 0 V; preconditioned CG."""
        fixed = np.zeros(self.n, bool)
        for s in sinks:
            fixed[self.nodes_of(s)] = True
        b = np.zeros(self.n)
        sn = self.nodes_of(src)
        b[sn] = amps / len(sn)
        diag = np.bincount(self.ei, self.eg, self.n) + np.bincount(self.ej, self.eg, self.n) + 1e-9
        ei, ej, eg = self.ei, self.ej, self.eg

        def A(x):
            x = np.where(fixed, 0.0, x)
            y = diag * x - np.bincount(ei, eg * x[ej], self.n) - np.bincount(ej, eg * x[ei], self.n)
            return np.where(fixed, 0.0, y)

        b = np.where(fixed, 0.0, b)
        Minv = 1.0 / diag
        x = np.zeros(self.n)
        r = b - A(x)
        z = Minv * r
        p = z.copy()
        rz = r @ z
        bn = math.sqrt(b @ b)
        for it in range(maxit):
            Ap = A(p)
            alpha = rz / (p @ Ap)
            x += alpha * p
            r -= alpha * Ap
            if math.sqrt(r @ r) < tol * bn:
                break
            z = Minv * r
            rz2 = r @ z
            p = z + (rz2 / rz) * p
            rz = rz2
        self.iters = it
        return x

    def at(self, x, pad):
        return float(np.mean(x[self.nodes_of(pad)]))


SHEET = Sheet(R.main, "GND")
GND_PADS = [k for k in SHEET.pad_cells if k[0] == "U2"]
ck.check("L.sheet", ("H3", "2") in SHEET.pad_cells and ("U2", "20") in SHEET.pad_cells and ("U2", "40") in SHEET.pad_cells,
         f"main-board GND copper on a {SHEET.h} mm grid: {SHEET.n} cells on two layers, {len(SHEET.pad_cells)} GND pads; "
         f"the breakout's GND pins {', '.join(n for _, n in GND_PADS)}")
i_led = 8 * (cur["R"][2] + cur["G"][2])          # all 16 lit, best-case current
refs = {"bias V divider (R48.2)": (CH["VOCT"]["rbot"].ref, "2"), "bias A divider (R46.2)": (CH["MODEL"]["rbot"].ref, "2"),
        "jack sleeves / GND_F (H2.2)": ("H2", "2")}
results = {}
for case, sinks in (("all breakout GND pins", GND_PADS), ("DGND pin 40 only", [("U2", "40")])):
    x = SHEET.solve(("H3", "2"), sinks, 1.0)
    ref0 = SHEET.at(x, ("U2", "20"))
    rel = {k: SHEET.at(x, pad) - ref0 for k, pad in refs.items()}
    results[case] = rel
    rtot = SHEET.at(x, ("H3", "2")) - ref0
    dv_div = rel["bias V divider (R48.2)"] * i_led
    dv_jack = rel["jack sleeves / GND_F (H2.2)"] * i_led
    g, k = VOCT["g"], VOCT["k"]
    dv_adc = (1 + g) * (1 - k) * dv_div - g * dv_jack
    cents = abs(1200 * dv_adc / g)
    gw, kw_ = CH["MODEL"]["g"], CH["MODEL"]["k"]
    dvw = (1 + gw) * (1 - kw_) * rel["bias A divider (R46.2)"] * i_led - gw * dv_jack
    print(f"      GND sheet, LED return {i_led * 1e3:.0f} mA into H3.2, out at {case} ({SHEET.iters} CG steps): "
          f"H3.2 {rtot * 1e3:.2f} mOhm from AGND pin 20; "
          + ", ".join(f"{k} {v * 1e3:+.3f} mOhm" for k, v in rel.items()))
    within(f"L.voct_cents.{'all' if 'all' in case else 'pin40'}", cents, None, 1.0, " cents",
           f"the LED current ({i_led * 1e3:.0f} mA, all 16 lit) on the shared GND copper, out at {case}: "
           f"V/OCT error {cents:.3f} cents (it switches with the LED PWM)")
    within(f"L.wide.{'all' if 'all' in case else 'pin40'}", abs(dvw / gw), None, ADC_LSB12 / gw, " V",
           "the same on a wide channel, jack volts, against one 12-bit step")

ck.done()
