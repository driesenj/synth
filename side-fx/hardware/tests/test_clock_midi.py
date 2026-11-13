"""clock_midi: the CLOCK input (Q1 2N3904 stage into D0) and the MIDI input (TRS type A, H11L1 into D14).

What it checks, from circuit.py's netlist, the routed master, design.md, the firmware and the datasheets
(constants block below):
  CLOCK
  A. topology: R24 100k jack -> base, D1 BAT85 cathode on the base / anode on GND, emitter on GND, R25 10k
     to 3V3D on the collector, collector on Seed pin 1 (D0 = PB12), jack switch lug on GND_F;
  B. threshold: the jack voltage at which D0 falls below the STM32's VIL, typical (design.md: "about
     0.7 V") and worst case (VBE over temperature, hFE min, the BAT85's reverse leakage stealing base
     current), against a 5 V trigger, also with the BOM's leakiest D1 alternates (SD103A, BAT86); noise
     immunity at the low end;
  C. drive: base current at +12 V and +5 V, saturation (forced beta), VCE(sat) against VIL; the
     BAT85 clamp on -12 V against the 2N3904's VEBO; input impedance;
  D. switching: turn-on (base charge through 100k, Miller plateau), storage time with a hard-saturated
     base and no speed-up capacitor, the collector's rise through 10k into the pin + routed track +
     Cob; the shortest trigger that registers; the firmware: EXTI on the falling edge of PB12 plus a
     4 kHz scan (hal_daisy.cc), rising-edge detection in controls.cc, a 1 ms and a 5 ms trigger, the
     shortest gap between pulses that still counts at the fastest supported clock (tempo.cc kMaxBpm x 24 PPQN);
  MIDI
  E. topology: TRS type A (ring = source = DIN 4, tip = sink = DIN 5), R26 220R into the LED anode, D2
     1N4148 across the LED (cathode on the anode), H11L1 pin 4 with R27 1k to 3V3D into Seed pin 15
     (D14 = PB7, USART1 RX), pin 6 3V3D, pin 5 GND, C17, the sleeve open;
  F. LED current for a 5 V sender (220R / 220R) and a 3.3 V sender (33R / 10R, the 2014 update) at worst
     case (supply and resistor tolerances, LED VF max / min, the sender's VOL) against the H11L1's turn-on
     threshold (at VCC 3.3 V) and its absolute maximum IF; reversed (type B) cables: the LED's reverse
     voltage and D2's ratings;
  G. the H11L1 at VCC = 3V3D: its VCC range against 3V3D's tolerance; VOL at the R27 sink current against
     the STM32's VIL, IOL; IOH leakage against VIH; idle high;
  H. timing: ton / toff / tr / tf against the 32 us bit at 31.25 kbaud and the MIDI spec's receiver rise /
     fall requirement; the bit distortion against the USART's receiver tolerance; the R27 rise into the
     routed MIDI_RX track;
  I. the firmware's USART1 setup (hal_daisy.cc): 31250 baud from PCLK2 (BRR, the baud error at 400 / 480
     MHz), oversampling 16, 8N1, RX on PB7 AF7, receive FIFO, errors dropped.

Run:  cd side-fx/hardware/tests && python test_clock_midi.py
Only reads; writes nothing.
"""
import csv
import math
import os
import re

import harness

ck = harness.Checks("clock_midi")
circuit = harness.load("circuit")

# ================================================================================================ constants
# --- 2N3904, onsemi 2N3904/D Rev. 3 (October 2024), www.onsemi.com/download/data-sheet/pdf/2n3904-d.pdf,
#     25 C unless noted
Q_VEBO = 6.0                 # V, emitter-base voltage, absolute maximum (V(BR)EBO min 6.0 V at IE = 10 uA)
Q_HFE_MIN_01 = 40            # hFE min at IC = 0.1 mA, VCE = 1 V
Q_HFE_MIN_1 = 70             # hFE min at IC = 1 mA, VCE = 1 V
Q_HFE_MAX = 300              # hFE max at IC = 10 mA, VCE = 1 V (the only max given)
Q_HFE_TYP_LOW = 150          # typ at 0.1-1 mA, 25 C, VCE 5 V: Figure 1 (read off the curve)
Q_VCESAT_MAX = 0.2           # V max, IC = 10 mA, IB = 1 mA
Q_COBO_MAX = 4.0e-12         # F max, VCB = 5 V, IE = 0, 100 kHz
Q_CIBO_MAX = 8.0e-12         # F max, VEB = 0.5 V, IC = 0, 100 kHz
Q_TS_MAX = 200e-9            # s, storage time max, VCC 3 V, IC 10 mA, IB1 = IB2 = 1 mA
Q_TS_IC, Q_TS_IB = 10e-3, 1e-3
Q_HFE_10MA_MIN = 100         # hFE min at 10 mA (for the storage-time constant)
Q_TD_MAX, Q_TR_MAX, Q_TF_MAX = 35e-9, 35e-9, 50e-9
Q_ICEX_MAX = 50e-9           # A, collector cut-off, VCE 30 V, VEB 3 V
Q_VBESAT_MIN, Q_VBESAT_MAX = 0.65, 0.85   # V, VBE(sat) at IC = 10 mA, IB = 1 mA (min / max), 25 C
Q_VBE_IC_REF = 10e-3         # the current those are given at; moved to the stage's current by VT ln(IC / 10 mA)
Q_VBE_TC = -2.0e-3           # V/C, onsemi 2N3903-D Figure 18 (typical temperature coefficient of VBE at low
#                              current, read off the curve)
Q_HFE_COLD = 0.8             # hFE at 0 C relative to 25 C: Figure 1 (typical curves at -40 / 25 / 125 C, read off)
VT_25 = 0.025693
T_RANGE = (0.0, 25.0, 60.0)  # C: a cold case, room, a warm case (assumption)
# --- BAT85, Vishay BAT85S, doc. 85513 Rev. 2.2 (07-Nov-2024), www.vishay.com/docs/85513/bat85s.pdf, 25 C
D1_VR_MAX = 30.0             # V, reverse voltage, absolute maximum
D1_IR_MAX_25V = 2e-6         # A max, VR = 25 V, 25 C (the only leakage limit given)
D1_VF_01MA_MAX = 0.24        # V max at IF = 0.1 mA (320 mV at 1 mA, 400 mV at 10 mA)
D1_CD_MAX = 10e-12           # F max, VR = 1 V, 1 MHz
#     Fig. 2 (typical reverse current vs reverse voltage), read off the vector curves: at VR ~ 1 V: 0.046 uA
#     (25 C), 0.33 uA (50 C), 1.85 uA (75 C), 8.0 uA (100 C); at VR = 25 V, 25 C: 0.158 uA. The worst case at the
#     base (about 0.6 V reverse) is taken as the 25 V maximum scaled by the typical curve:
#     IR(1 V, T) max = 2 uA x typ(1 V, T) / typ(25 V, 25 C).
D1_IR_TYP_1V = {25.0: 0.046e-6, 50.0: 0.33e-6, 75.0: 1.85e-6, 100.0: 8.0e-6}
D1_IR_TYP_25V_25C = 0.158e-6
# --- 1N4148, Vishay doc. 81857 Rev. 1.6 (07-Nov-2024), www.vishay.com/docs/81857/1n4148.pdf, 25 C
D2_VRRM, D2_VR = 100.0, 75.0     # V, absolute maximum
D2_IF_MAX, D2_IFAV = 300e-3, 150e-3   # A, forward continuous / average
D2_VF_10MA_MAX = 1.0         # V max at 10 mA
D2_IR_20V = 25e-9            # A max at VR = 20 V (50 uA at 150 C)
# --- STM32H750, ST DS12556 Rev 7, Table 155 (rev V I/O static characteristics), 1.62 V < VDD < 3.6 V:
#     VIL max 0.3 VDD, VIH min 0.7 VDD (CMOS, guaranteed); simulation: VIL 0.4 VDD - 0.1, VIH 0.47 VDD + 0.25;
#     VHYS 250 mV typ; FT_u leakage +-350 nA max; RPU 30 / 40 / 50 k (min / typ / max); CIO 5 pF typ.
#     PB12 (D0) is FT_u, PB7 (D14) FT_fa (Table 7). Table 20: IIO 20 mA per pin (sink).
VIL_FRAC, VIH_FRAC = 0.3, 0.7
VIL_SIM = (0.4, -0.1)
VIH_SIM = (0.47, 0.25)
I_LKG_FTU = 350e-9
RPU_MIN = 30e3
C_PIN = 5e-12
V3D_NOM, V3D_TOL = 3.30, 0.03          # 3V3D: TPS6217x 0.8 V x (1 + 47k/15k) = 3.307 V (Seed datasheet v1.0.5
#                                        schematic p. 15); +-3 % assumed: NOT CONFIRMED
PF_PER_MM = 0.12e-12                   # F/mm, 0.3 mm track on 1.6 mm FR4 next to the pour (estimate)
# --- Eurorack triggers: 5 V is the usual trigger / gate high (Doepfer A-100 technical details: gates "typically
#     +5 V"; not re-read here); +12 V the most any output reaches
TRIG_V, TRIG_MAX = 5.0, 12.0
# --- H11L1: two makers' datasheets, the worse figure of the two (Tayda does not name its maker):
#     M = Motorola H11L1/D Rev 1 (1995, the Fairchild / onsemi H11L1M lineage), I = Isocom DB92224-AAS/A6
#     (20/10/09). 25 C unless noted.
H_IFON_MAX = 1.6e-3          # A, turn-on threshold max, RL = 270 ohm, VCC = 5 V (M, I)
H_IFOFF_MIN = 0.3e-3         # A, turn-off threshold min (M, I)
#     M Figure 3 (threshold vs supply voltage, normalised to IF(on) at VCC = 5 V, 25 C, typical), read off the
#     vector curve: turn-on 0.83 at VCC = 3.3 V, 0.79 at 3.0 V; Figure 4 (vs temperature, normalised at 25 C,
#     typical): 0.83 at 0 C, 1.18 at 50 C, 1.25 at 60 C, 1.33 at 70 C. No figure is guaranteed at 3.3 V.
H_IFON_VCC_33 = 0.83
H_IFON_TEMP = {0.0: 0.83, 25.0: 1.0, 50.0: 1.18, 60.0: 1.25, 70.0: 1.33}
H_VCC_MIN, H_VCC_MAX = 3.0, 15.0     # V, operating voltage (M, I)
H_IF_ABS = 50e-3             # A, LED forward current, absolute maximum (I 50 mA; M 60 mA)
H_VR_ABS = 6.0               # V, LED reverse voltage, absolute maximum (M, I)
H_VF_MAX = 1.5               # V max at IF = 10 mA (M, I)
H_VF_MIN = 0.75              # V min at IF = 0.3 mA (M, I): the lowest drop, used for the largest current
H_IR_LED = 10e-6             # A max at VR = 3 V
H_VOL_MAX = 0.4              # V max, RL = 270 ohm, VCC = 5 V, IF = IF(on): IOL = (5 - 0.4) / 270 = 17 mA
H_VOL_IOL = (5.0 - 0.4) / 270.0
H_IOH_MAX = 100e-6           # A max, IF = 0, VCC = VO = 15 V
H_IO_ABS = 50e-3             # A, output current, absolute maximum
H_TON_MAX, H_TOFF_MAX = 4e-6, 4e-6   # s max, RL 270, VCC 5 V, IF = IF(on) (M; "RL value effect on switching
#                                      time is negligible")
H_TPHL_MAX, H_TPLH_MAX = 3e-6, 6e-6  # s max (I: high-to-low 3 us, low-to-high 6 us)
H_TR_MAX, H_TF_MAX = 0.5e-6, 0.5e-6  # s max (I; M gives 0.1 us typ only)
H_C_OUT = 5e-12              # F, output capacitance (assumption: neither datasheet gives it)
# --- MIDI: MMA/AMEI CA-033 "MIDI 1.0 Electrical Specification Update [2014]" (approved 2014-01-20):
#     31.25 kbaud +-1 %, 8-N-1, start bit = current ON; "The receiver must require less than 5 mA to turn on.
#     Rise and fall times should be less than 2 microseconds."; MIDI OUT: VTX +5 V +-10 % with RA = RC = 220R 5 %,
#     or +3.3 V +-5 % with RA 33R 5 %, RC 10R 5 %; MIDI IN pin 2 and the jack shield: no DC path to ground.
#     TRS type A (MMA RP-054, 2018; members' PDF, not read): tip = DIN pin 5 (current sink), ring = DIN pin 4
#     (current source), sleeve = pin 2 -- as widely published: NOT CONFIRMED from the document itself.
SENDERS = {"5 V": (5.0, 0.10, 220.0, 220.0), "3.3 V": (3.3, 0.05, 33.0, 10.0)}   # VTX, its tolerance, RA, RC
SENDER_R_TOL = 0.05
SENDER_VOL_MAX = 0.4         # V, the sender's TX driver low at ~5 mA (assumption; CA-033 assumes an open-drain
#                              buffer with no drop)
MIDI_RX_TURN_ON = 5e-3       # A: the receiver must require less than this
MIDI_BAUD, MIDI_BAUD_TOL = 31250.0, 0.01
MIDI_TRISE_MAX = 2e-6
# --- STM32H7 USART receiver: oversampling by 16 takes three samples at the 8th, 9th and 10th sixteenth of a
#     bit, timed from the detected start edge (RM0433, "USART receiver"; not re-read here: NOT CONFIRMED)
# ================================================================================================== design
DOC = " ".join(harness.text("docs", "design.md").split())
HAL = harness.text("firmware", "src", "hal_daisy.cc")
HALH = harness.text("firmware", "src", "hal.h")
CTRL = harness.text("firmware", "src", "app", "controls.cc")
TEMPO = harness.text("firmware", "src", "app", "tempo.cc")
SETT = harness.text("firmware", "src", "app", "settings.cc")
MAIN = circuit.main_board_parts()
BY = {p.ref: p for p in MAIN}
R = harness.routed()
RST = R.main.net_stats()


def val(ref):
    p = BY[ref]
    return harness.ohms(p.value) if p.kind == "R" else harness.farads(p.value)


# ================================================================================= CLOCK: A. topology
ck.check("A.r24: R24 100k from CLK_IN to the base (B_CLK)", set(BY["R24"].nets.values()) == {"CLK_IN", "B_CLK"}
         and val("R24") == 100e3, f"{BY['R24'].value} {BY['R24'].nets}")
ck.check("A.q1: Q1 2N3904 E = GND, B = B_CLK, C = CLK (TO-92 pins 1 E, 2 B, 3 C)",
         BY["Q1"].value == "2N3904" and BY["Q1"].nets == {"1": "GND", "2": "B_CLK", "3": "CLK"}, f"{BY['Q1'].nets}")
ck.check("A.d1: D1 BAT85 cathode (1) on the base, anode (2) on GND", BY["D1"].nets == {"1": "B_CLK", "2": "GND"},
         f"{BY['D1'].nets}")
ck.check("A.r25: R25 10k from 3V3D to CLK", set(BY["R25"].nets.values()) == {"3V3D", "CLK"} and val("R25") == 10e3,
         f"{BY['R25'].value} {BY['R25'].nets}")
seed_clk = [pin for pin, (lib, net) in circuit.SEED.items() if net == "CLK"]
ck.check("A.seed_pin: CLK on Seed pin 1 (D0, PB12)", seed_clk == ["1"] and circuit.SEED["1"][0] == "D0", f"{seed_clk}")
ck.check("A.firmware_pin: hal_daisy.cc reads the clock on D0", "kPinClock = daisy::seed::D0" in HAL, "")
jack = next((j for j in circuit.JACKS if j[2] == "CLK_IN_F"), None)
ck.check("A.jack_lug: the CLOCK jack's switch lug grounds the tip when unplugged (design.md)",
         jack is not None and jack[3] == "GND_F", f"{jack}")
for net in ("CLK", "B_CLK", "CLK_IN"):
    rp = sorted(f"{p.ref}.{p.num}" for p in R.main.pads if p.net == net)
    gp = sorted(f"{p.ref}.{pid}" for p in MAIN for pid, n in p.nets.items() if n == net)
    ck.check(f"A.routed.{net}: routed pads = circuit.py's", rp == gp, f"circuit {gp}, routed {rp}")


# ================================================================================= CLOCK: B. threshold
def vbe(ic, t_c=25.0, which="typ"):
    """VBE at collector current ic (A) and temperature t_c (C): the datasheet's VBE(sat) range at 10 mA moved
    to ic by VT ln(ic / 10 mA) and to t_c by the typical -2 mV/C."""
    vt = VT_25 * (t_c + 273.15) / 298.15
    v10 = {"min": Q_VBESAT_MIN, "max": Q_VBESAT_MAX, "typ": (Q_VBESAT_MIN + Q_VBESAT_MAX) / 2}[which]
    return v10 + vt * math.log(ic / Q_VBE_IC_REF) + Q_VBE_TC * (t_c - 25.0)


def ir_d1(t_c):
    """BAT85 reverse current at the base's ~0.6-0.8 V, worst case: the 25 V maximum scaled by the typical curves."""
    ts = sorted(D1_IR_TYP_1V)
    t_c = min(max(t_c, ts[0]), ts[-1])
    for a, b in zip(ts, ts[1:]):
        if a <= t_c <= b:
            la, lb = math.log10(D1_IR_TYP_1V[a]), math.log10(D1_IR_TYP_1V[b])
            typ = 10 ** (la + (lb - la) * (t_c - a) / (b - a))
            break
    return D1_IR_MAX_25V * typ / D1_IR_TYP_25V_25C


VDD_MIN, VDD_MAX = V3D_NOM * (1 - V3D_TOL), V3D_NOM * (1 + V3D_TOL)
R24, R25 = val("R24"), val("R25")


def threshold(case):
    """Jack voltage at which D0 just reads low.
    max: the pin switches at VIL max (0.3 VDD), hFE min (less when cold), VBE high, the BAT85's worst leakage,
    R24 +1 %, R25 -1 %; min: the pin switches at VIH min (0.7 VDD: least collector current), hFE max, VBE low,
    no leakage; typ: switching at the simulation midpoint, hFE typ, VBE mid-range, 25 C."""
    vals = []
    temps = (25.0,) if case == "typ" else T_RANGE
    vdds = (V3D_NOM,) if case == "typ" else (VDD_MIN, VDD_MAX)
    for t in temps:
        for vdd in vdds:
            if case == "typ":
                vsw = ((VIL_SIM[0] * vdd + VIL_SIM[1]) + (VIH_SIM[0] * vdd + VIH_SIM[1])) / 2
                ic = (vdd - vsw) / R25
                ib, lk, r24, which = ic / Q_HFE_TYP_LOW, 0.0, R24, "typ"
            elif case == "max":
                ic = (vdd - VIL_FRAC * vdd) / (R25 * 0.99) + I_LKG_FTU
                hfe = Q_HFE_MIN_01 * (Q_HFE_COLD if t < 25.0 else 1.0)
                ib, lk, r24, which = ic / hfe, ir_d1(t), R24 * 1.01, "max"
            else:
                ic = (vdd - VIH_FRAC * vdd) / (R25 * 1.01)
                ib, lk, r24, which = ic / Q_HFE_MAX, 0.0, R24 * 0.99, "min"
            vals.append(vbe(ic, t, which) + (ib + lk) * r24)
    return max(vals) if case == "max" else min(vals)


th_typ, th_max, th_min = threshold("typ"), threshold("max"), threshold("min")
m = re.search(r"threshold about ([\d.]+) V", DOC)
doc_th = float(m.group(1)) if m else float("nan")
ck.close("B.threshold_typ: typical threshold = design.md's 'about 0.7 V' (within 0.15 V)", th_typ, doc_th, 0.15, " V")
ck.within(f"B.threshold_max: worst-case threshold ({T_RANGE[0]:.0f}-{T_RANGE[-1]:.0f} C: hFE min, VBE high, BAT85 "
          f"leakage) leaves a 5 V trigger 2x margin", th_max, None, TRIG_V / 2, " V")
ck.within("B.threshold_min: worst-case threshold above 0.4 V (a grounded or 'low' source never triggers)", th_min, 0.4,
          None, " V")
print(f"      clock threshold: typ {th_typ:.2f} V, worst {th_min:.2f}..{th_max:.2f} V (BAT85 worst leakage at "
      f"{T_RANGE[-1]:.0f} C {ir_d1(T_RANGE[-1]) * 1e6:.1f} uA = {ir_d1(T_RANGE[-1]) * R24:.2f} V across R24; at 75 C "
      f"{ir_d1(75) * 1e6:.1f} uA = {ir_d1(75) * R24:.2f} V)")
# verify pass 2026-11-13: the BOM (side-fx-bom.csv line 21) lets "BAT86, BAT43, BAT42, BAT46, SD103A, 1N5711 or
# SD101" stand in for D1, so the threshold must hold for the leakiest of them, not only the BAT85. SD103A: Vishay
# doc. 85754 Rev. 2.2 (08-Nov-2024), leakage IR max 5 uA at VR = 30 V, 25 C (2.5x the BAT85's 2 uA at 25 V; BAT42 /
# BAT43 0.5 uA at 25 V, 1N5711 / SD101 0.2 uA at 50 V leak less). Its Fig. 2 (typical IR vs TJ) is a picture: the
# BAT85's normalised curves are reused for the shape, scaled by the ratio of the two maxima (an approximation; the
# SD103's lower barrier leaks relatively more at low VR, so this is not pessimistic). BAT86(S), Vishay doc. 85514
# Rev. 1.9: IR max 5 uA at VR = 40 V, the same class.
# 2026-11-14: the alternates are read from the BOM's D1 line (side-fx-bom.csv) instead of assumed, so the check
# follows the BOM: every part it offers for D1 (names after "no " are the ones it rules out) at its datasheet
# maximum leakage; a name not in this table counts as the leakiest known (5 uA).
ALT_IR_MAX = {"BAT85": D1_IR_MAX_25V, "SD103A": 5e-6, "BAT86": 5e-6, "BAT42": 0.5e-6, "BAT43": 0.5e-6,
              "1N5711": 0.2e-6, "SD101": 0.2e-6, "1N4148": D2_IR_20V}
with open(os.path.join(harness.MODULE, "hardware", "bom", "side-fx-bom.csv"), encoding="utf-8") as _f:
    _d1 = next((r["Part"] for r in csv.DictReader(_f) if "D1" in [x.strip() for x in r["Refs"].split(",")]), "")
_offered = re.split(r"\bno\b", _d1)[0]
_names = set(re.findall(r"\b(?:BAT\d+\w*|SD\d+\w*|1N\d+\w*)", _offered))
ALT_WORST = max(_names, key=lambda n: ALT_IR_MAX.get(n, 5e-6)) if _names else "BAT85"
ALT_IR_RATIO = ALT_IR_MAX.get(ALT_WORST, 5e-6) / D1_IR_MAX_25V
th_alt = max(threshold("max"), max(
    vbe((vdd - VIL_FRAC * vdd) / (R25 * 0.99) + I_LKG_FTU, t, "max")
    + (((vdd - VIL_FRAC * vdd) / (R25 * 0.99) + I_LKG_FTU) / (Q_HFE_MIN_01 * (Q_HFE_COLD if t < 25.0 else 1.0))
       + ALT_IR_RATIO * ir_d1(t)) * R24 * 1.01
    for t in T_RANGE for vdd in (VDD_MIN, VDD_MAX)))
ck.within(f"B.threshold_max_alternates: worst-case threshold with the leakiest part the BOM offers for D1 "
          f"({ALT_WORST}, {ALT_IR_MAX.get(ALT_WORST, 5e-6) * 1e6:.2f} uA max) leaves a 5 V trigger 2x margin",
          th_alt, None, TRIG_V / 2, " V",
          f"offered: {sorted(_names)}; {ALT_WORST} leakage at {T_RANGE[-1]:.0f} C "
          f"~{ALT_IR_RATIO * ir_d1(T_RANGE[-1]) * 1e6:.1f} uA = {ALT_IR_RATIO * ir_d1(T_RANGE[-1]) * R24:.2f} V across "
          f"R24; BAT85 alone {th_max:.2f} V")
# the BOM lets other DO-35 Schottkys stand in for D1; a 1N4148 would leak far less at the base's 0.6 V
print(f"      a 1N4148 in D1's place: {D2_IR_20V * 1e9:.0f} nA max at 20 V and 25 C ({D2_IR_20V * R24 * 1e3:.1f} mV); the "
      f"base then clamps at about -0.7 V on negative inputs, still far inside VEBO {Q_VEBO} V")

# ================================================================================= CLOCK: C. drive
for vin in (TRIG_V, TRIG_MAX):
    ib = (vin - vbe(1e-4)) / R24
    ic = V3D_NOM / R25
    beta_f = ic / ib
    ck.within(f"C.saturation_{vin:.0f}V: a {vin:.0f} V input saturates Q1 (forced beta < hFE min / 2)", beta_f, None,
              Q_HFE_MIN_01 / 2, "", f"IB {ib * 1e6:.0f} uA, IC {ic * 1e3:.2f} mA")
ck.within("C.vcesat_vs_vil: VCE(sat) max below VIL at the lowest VDD", Q_VCESAT_MAX, None, VIL_FRAC * VDD_MIN, " V")
ib12 = (TRIG_MAX - 0.6) / (R24 * 0.99)
ck.within("C.base_current_12V: base current at +12 V far below IC's 200 mA rating (no stress)", ib12 * 1e3, None, 1.0,
          " mA")
i_neg = (TRIG_MAX - 0.2) / (R24 * 0.99)
# VF max between the datasheet's 0.1 mA (240 mV) and 1 mA (320 mV) points, log-interpolated
v_base_neg = D1_VF_01MA_MAX + 0.08 * max(0.0, math.log10(i_neg / 1e-4))
ck.within("C.vebo_clamp: -12 V into the jack: BAT85 holds the base within the 2N3904's VEBO with a 10x margin",
          v_base_neg, None, Q_VEBO / 10, " V", f"{i_neg * 1e3:.2f} mA through D1; VEBO {Q_VEBO} V")
ck.within("C.d1_reverse: +12 V into the jack: D1 sees only VBE in reverse, inside its 30 V rating",
          vbe(V3D_NOM / R25, 0.0, "max"), None, D1_VR_MAX, " V")
zin_low = R24
ck.within("C.zin: input impedance >= 100k below the threshold (R24) and when driven (R24 into a diode)", zin_low / 1e3,
          99.0, None, "k")

# ================================================================================= CLOCK: D. switching
c_clk = RST.get("CLK", {}).get("length", 0.0) * PF_PER_MM + C_PIN + Q_COBO_MAX
t_rise = R25 * 1.01 * c_clk * math.log(1 / (1 - VIH_FRAC))
print(f"      CLK track {RST.get('CLK', {}).get('length', 0):.1f} mm: {c_clk * 1e12:.1f} pF; collector rise to VIH "
      f"{t_rise * 1e9:.0f} ns")


def turn_on_time(vin):
    """Time from the jack edge to D0 < VIL: the base charges Cibo through R24 to VBE, then the collector falls
    through the Miller plateau with the base current."""
    vb = vbe(0.3e-3)
    if vin <= vb + 1e-3:
        return float("inf")
    t1 = R24 * (Q_CIBO_MAX + Q_COBO_MAX) * math.log(vin / (vin - vb))
    ib = (vin - vb) / R24
    t2 = Q_COBO_MAX * (V3D_NOM - VIL_FRAC * V3D_NOM) / ib
    return t1 + t2


def turn_off_time(vin):
    """Time from the jack falling to 0 V until D0 > VIH: storage (charge control) then the Miller plateau with
    only VBE / R24 pulling the base, then the RC rise."""
    tau_s = Q_TS_MAX / math.log((Q_TS_IB + Q_TS_IB) / (Q_TS_IC / Q_HFE_10MA_MIN + Q_TS_IB))
    ib1 = (vin - vbe(0.3e-3)) / R24
    ib2 = vbe(0.3e-3) / R24
    ic = V3D_NOM / R25
    ts = tau_s * math.log((ib1 + ib2) / (ic / Q_HFE_10MA_MIN + ib2))
    t_m = Q_COBO_MAX * VIH_FRAC * V3D_NOM / ib2
    return ts, t_m


for vin in (TRIG_V, TRIG_MAX):
    ts, tm = turn_off_time(vin)
    print(f"      {vin:.0f} V trigger: D0 falls {turn_on_time(vin) * 1e6:.2f} us after the jack rises; after it falls, "
          f"storage {ts * 1e6:.2f} us + Miller {tm * 1e6:.2f} us + rise {t_rise * 1e6:.2f} us")
ts12, tm12 = turn_off_time(TRIG_MAX)
ck.within("D.release: after a +12 V trigger ends, D0 is back above VIH (storage with no speed-up capacitor, the Miller "
          "plateau on VBE / 100k, the 10k rise) well within one scan period", (ts12 + tm12 + t_rise) * 1e6, None,
          0.1e6 / 4000, " us", "criterion: under a tenth of the 250 us scan")
# the firmware: EXTI on the falling edge of PB12 counts edges; the 4 kHz scan reads the level and the count
ck.check("D.fw_exti_falling: PB12 has an EXTI on its falling edge (the jack rising)", "GPIO_MODE_IT_FALLING" in HAL
         and "InstallVector(EXTI15_10_IRQn" in HAL, "")
ck.check("D.fw_active_low: the scan takes D0 low as the clock high", "scan.clock = !(clock_port->IDR & clock_mask)" in HAL,
         "")
ck.check("D.fw_no_pull: PB12 without the internal pull (R25 is the pull-up)", re.search(
    r"InitClock\(\).*?gpio\.Pull = GPIO_NOPULL", HAL, re.S) is not None, "")
mr = re.search(r"kControlRate = (\d+);", HALH)
rate = int(mr.group(1)) if mr else 0
ck.check("D.fw_rising_edge: controls.cc pushes a clock edge on a false -> true transition of scan.clock",
         "scan.clock && !clock_previous_" in CTRL, "")
t_min_pulse = turn_on_time(TRIG_V) + 20e-9          # plus a couple of EXTI clock cycles (not specified)
for w in (1e-3, 5e-3):
    ck.within(f"D.trigger_{w * 1e3:.0f}ms: a {w * 1e3:.0f} ms, 5 V trigger produces a falling edge on D0 (EXTI) and "
              f"is counted", t_min_pulse * 1e6, None, w * 1e6, " us", f"needs {t_min_pulse * 1e6:.2f} us")
th_short = None
for v in [x / 100 for x in range(60, 1201)]:
    if turn_on_time(v) < 10e-6:
        th_short = v
        break
print(f"      shortest trigger: {t_min_pulse * 1e6:.2f} us at 5 V; a 10 us pulse needs >= {th_short:.2f} V (typ)")
# two pulses closer than one scan are seen as one: the shortest gap at the fastest supported clock
mb = re.search(r"kMaxBpm = ([\d.]+)f;", TEMPO)
max_bpm = float(mb.group(1))
mp = re.search(r"kClockPpqnValues\[kNumClockPpqn\] = \{([^}]*)\}", SETT)
ppqn_max = max(int(x) for x in mp.group(1).split(","))
period = 60.0 / (max_bpm * ppqn_max)
gap_need = 1 / rate + 32 / 48e3                      # one scan period plus one audio block holding the scan off
gap_5ms = period - 5e-3
ck.within(f"D.fastest_clock_5ms: at {max_bpm:.0f} BPM x {ppqn_max} PPQN with 5 ms triggers the gap still spans a scan "
          f"(+ an audio block)", gap_need * 1e3, None, gap_5ms * 1e3, " ms",
          f"period {period * 1e3:.2f} ms, gap {gap_5ms * 1e3:.2f} ms")

# ================================================================================= MIDI: E. topology
ck.check("E.r26: R26 220R from MIDI_RING (source, DIN 4) to the LED anode (OPTO_A)",
         set(BY["R26"].nets.values()) == {"MIDI_RING", "OPTO_A"} and val("R26") == 220.0, f"{BY['R26'].nets}")
ck.check("E.d2: D2 1N4148 cathode on OPTO_A, anode on MIDI_TIP (across the LED, reversed)",
         BY["D2"].nets == {"1": "OPTO_A", "2": "MIDI_TIP"}, f"{BY['D2'].nets}")
ck.check("E.u7: H11L1 1 anode OPTO_A, 2 cathode MIDI_TIP, 4 Vo MIDI_RX, 5 GND, 6 VCC 3V3D",
         BY["U7"].nets == {"1": "OPTO_A", "2": "MIDI_TIP", "4": "MIDI_RX", "5": "GND", "6": "3V3D"}, f"{BY['U7'].nets}")
ck.check("E.r27: R27 1k from 3V3D to MIDI_RX", set(BY["R27"].nets.values()) == {"3V3D", "MIDI_RX"}
         and val("R27") == 1e3, f"{BY['R27'].nets}")
ck.check("E.c17: C17 100n across U7's supply", set(BY["C17"].nets.values()) == {"3V3D", "GND"}, f"{BY['C17'].nets}")
seed_rx = [pin for pin, (lib, net) in circuit.SEED.items() if net == "MIDI_RX"]
ck.check("E.seed_pin: MIDI_RX on Seed pin 15 (D14, PB7, USART1 RX)", seed_rx == ["15"] and circuit.SEED["15"][0] == "D14",
         f"{seed_rx}")
ck.check("E.trs_type_a: tip = sink (LED cathode side), ring = source (LED anode side) on the jack",
         circuit.MIDI_JACK.get("3") == "MIDI_TIP_F" and circuit.MIDI_JACK.get("2") == "MIDI_RING_F", f"{circuit.MIDI_JACK}")
ck.check("E.sleeve_open: the MIDI jack's sleeve is not connected (MIDI IN shield open)", "1" not in circuit.MIDI_JACK,
         f"{circuit.MIDI_JACK}")
for net in ("OPTO_A", "MIDI_TIP", "MIDI_RING", "MIDI_RX"):
    rp = sorted(f"{p.ref}.{p.num}" for p in R.main.pads if p.net == net)
    gp = sorted(f"{p.ref}.{pid}" for p in MAIN for pid, n in p.nets.items() if n == net)
    ck.check(f"E.routed.{net}: routed pads = circuit.py's", rp == gp, f"circuit {gp}, routed {rp}")

# ================================================================================= MIDI: F. LED current
R26 = val("R26")
# the H11L1's turn-on threshold at this board's VCC and a warm case: the 5 V / 25 C maximum scaled by the typical
# normalisation curves (no guaranteed figure exists at 3.3 V)
H_IFON_WORST = H_IFON_MAX * H_IFON_VCC_33 * H_IFON_TEMP[T_RANGE[-1]]
H_IFON_WORST_5V = H_IFON_MAX * H_IFON_TEMP[T_RANGE[-1]]          # no credit for the lower supply
ck.within("F.receiver_turn_on: the H11L1 needs less than CA-033's 5 mA to turn on (worst, 60 C, even without the "
          "3.3 V credit)", H_IFON_WORST_5V * 1e3, None, MIDI_RX_TURN_ON * 1e3, " mA",
          f"{H_IFON_WORST * 1e3:.2f} mA with the typical 3.3 V normalisation")
for name, (vs, vtol, ra, rc) in SENDERS.items():
    i_lo = (vs * (1 - vtol) - H_VF_MAX - SENDER_VOL_MAX) / ((ra + rc) * (1 + SENDER_R_TOL) + R26 * 1.01)
    i_hi = (vs * (1 + vtol) - H_VF_MIN) / ((ra + rc) * (1 - SENDER_R_TOL) + R26 * 0.99)
    ck.within(f"F.turn_on.{name}: worst-case LED current from a CA-033 {name} sender above the H11L1's worst turn-on "
              f"threshold", i_lo * 1e3, H_IFON_WORST_5V * 1e3, None, " mA",
              f"VTX -{vtol * 100:.0f} %, resistors +5 % / +1 %, VF {H_VF_MAX} V, sender VOL {SENDER_VOL_MAX} V; margin "
              f"{i_lo / H_IFON_WORST_5V:.2f}x on {H_IFON_WORST_5V * 1e3:.2f} mA (60 C, threshold at 5 V), "
              f"{i_lo / H_IFON_WORST:.2f}x with the 3.3 V curve")
    ck.within(f"F.abs_max.{name}: largest LED current (VTX +{vtol * 100:.0f} %, resistors -5 % / -1 %, VF min) within the "
              f"absolute maximum IF", i_hi * 1e3, None, H_IF_ABS * 1e3, " mA")
    i_rev = (vs * (1 + vtol) - 0.6) / ((ra + rc) * (1 - SENDER_R_TOL) + R26 * 0.99)
    ck.within(f"F.reversed.{name}: a type B cable (tip and ring swapped): D2 carries the loop current within its "
              f"average rating", i_rev * 1e3, None, D2_IFAV * 1e3, " mA")
ck.within("F.led_reverse: reversed, the LED sees at most D2's forward drop (1.0 V max at 10 mA), under its 6 V VR",
          D2_VF_10MA_MAX, None, H_VR_ABS, " V")
ck.within("F.d2_reverse: in normal use D2 sees the LED's VF in reverse, far under its 75 V VR", H_VF_MAX, None, D2_VR,
          " V")

# ================================================================================= MIDI: G. H11L1 at 3.3 V
ck.within("G.vcc_range: 3V3D's minimum inside the H11L1's VCC range", VDD_MIN, H_VCC_MIN, H_VCC_MAX, " V")
i_sink = VDD_MAX / (val("R27") * 0.99) + VDD_MAX / RPU_MIN     # R27 plus the STM32's internal pull-up (30k min)
ck.within("G.iol: R27's sink current (plus the PB7 pull-up) within the H11L1's VOL test current (17 mA)", i_sink * 1e3,
          None, H_VOL_IOL * 1e3, " mA")
print("      note: the H11L1's thresholds, VOL and switching times are specified at VCC = 5 V only (both datasheets); "
      "at 3.3 V only Motorola's typical Figure 3 applies")
ck.within("G.vol_vs_vil: VOL max below the STM32's VIL", H_VOL_MAX, None, VIL_FRAC * VDD_MIN, " V")
ck.within("G.voh: output high with the H11L1's IOH leakage through R27 stays above VIH", VDD_MIN - H_IOH_MAX * val("R27") * 1.01,
          VIH_FRAC * VDD_MAX, None, " V")
ck.check("G.idle_high: no current into the LED -> output off -> MIDI_RX pulled high (UART idle)",
         set(BY["R27"].nets.values()) == {"3V3D", "MIDI_RX"}, "")

# ================================================================================= MIDI: H. timing
bit = 1 / MIDI_BAUD
c_rx = RST.get("MIDI_RX", {}).get("length", 0.0) * PF_PER_MM + C_PIN + H_C_OUT
t_rx_rise = val("R27") * 1.01 * c_rx * math.log((1 - 0.1) / (1 - 0.9))
print(f"      MIDI_RX track {RST.get('MIDI_RX', {}).get('length', 0):.1f} mm, {c_rx * 1e12:.1f} pF: 10-90 % rise through "
      f"R27 {t_rx_rise * 1e9:.0f} ns")
ck.within("H.rise: MIDI_RX 10-90 % rise (the H11L1's tr max + R27 into the track) under CA-033's 2 us",
          (H_TR_MAX + t_rx_rise) * 1e6, None, MIDI_TRISE_MAX * 1e6, " us")
ck.within("H.fall: MIDI_RX fall (the H11L1's tf max; it sinks actively) under CA-033's 2 us", H_TF_MAX * 1e6, None,
          MIDI_TRISE_MAX * 1e6, " us")
# Bit timing. The H11L1 delays falling edges (LED on: start and 0 bits) by tPHL and rising edges by tPLH. Every
# sample is timed from the start bit's falling edge, so only the difference counts. The USART takes three samples
# at 8/16..10/16 of each bit, 0..1/16 bit after the true start edge; the sender's baud may be 1 % off, which adds
# up to 9.5 % of a bit by the stop bit. Rising edges late (tPLH > tPHL): a 1 after a 0 starts late, so the skew
# must stay under 8/16 - 9.5 % of a bit. Falling edges late: a 0 after a 1 ends early, so the skew must stay
# under 1 - 11/16 - 9.5 % of a bit.
drift = 9.5 * MIDI_BAUD_TOL
late_ok = bit * (8 / 16 - drift)
early_ok = bit * (1 - 11 / 16 - drift)
skew_rise = max(H_TPLH_MAX, H_TOFF_MAX)          # tPLH (I) / toff (M) max against a zero-delay falling edge
skew_fall = max(H_TPHL_MAX, H_TON_MAX)
ck.within("H.skew_rising_late: the H11L1's worst rising-edge lag (tPLH / toff max) inside the USART's sampling margin",
          skew_rise * 1e6, None, late_ok * 1e6, " us", f"bit {bit * 1e6:.1f} us, sender at -1 %")
ck.within("H.skew_falling_late: the H11L1's worst falling-edge lag (tPHL / ton max) inside the USART's sampling margin",
          skew_fall * 1e6, None, early_ok * 1e6, " us", f"bit {bit * 1e6:.1f} us, sender at +1 %")

# ================================================================================= MIDI: I. firmware
m = re.search(r"kMidiBaud = (\d+);", HAL)
fw_baud = int(m.group(1)) if m else 0
ck.close("I.baud: kMidiBaud = 31250", fw_baud, MIDI_BAUD, 0.5)
for pclk2 in (120e6, 100e6):
    brr = (pclk2 + fw_baud // 2) // fw_baud
    err = pclk2 / brr / MIDI_BAUD - 1
    ck.within(f"I.baud_error_{pclk2 / 1e6:.0f}MHz: BRR {brr:.0f} gives the baud within the MIDI spec's 1 %", abs(err) * 100,
              None, MIDI_BAUD_TOL * 100, " %")
ck.check("I.oversampling16: OVER8 not set (oversampling by 16, the larger receiver tolerance)", "OVER8" not in HAL, "")
ck.check("I.8n1: CR2 = 0 (1 stop bit), no parity (PCE), 8 data bits (no M0/M1)",
         "USART1->CR2 = 0;" in HAL and "PCE" not in HAL and "CR1_M" not in HAL, "")
ck.check("I.pin_af: PB7 as USART1 RX (AF7) with the pull-up", "GPIO_AF7_USART1" in HAL and "kPinMidiRx = daisy::seed::D14"
         in HAL and re.search(r"InitMidi\(\).*?GPIO_PULLUP", HAL, re.S) is not None, "")
ck.check("I.errors_dropped: framing / noise / parity errors drop the byte", "if (isr & errors)" in HAL
         and "continue;" in HAL, "")

ck.done()
