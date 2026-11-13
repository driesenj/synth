"""cv: the four CV input stages (U6A-D) into the Daisy Seed's ADC A0-A3.

What it checks, from circuit.py's netlist, the routed master, design.md, the firmware sources and the
datasheets (constants block below):
  A. topology: each stage is Rin 100k / Rf 27k / Cf 1n / Rs 1k around a TL074 section with IN+ on BIAS,
     BIAS = 3V3A x R23 / (R22 + R23) with C14, the designators match design.md's table, each ADC net reaches
     the Seed pin design.md names (A0..A3), and in the routed copper the ADC nets carry only Rs and the Seed
     pin (no capacitor at the ADC pin);
  B. DC transfer, typical: design.md's "V_adc = 1.676 V - 0.27 V_in", "+-5 V lands on 0.33-3.03 V",
     BIAS 1.32 V, and the firmware's nominal calibration (offset 0.5079, scale -12.22 V) and ReadCv()'s
     "what 0 V reads";
  C. DC transfer, worst case (1 % resistors, the Seed's 3V3A tolerance, TL074 Vos / Ib max over temperature):
     +-5 V still inside the ADC's 0..VREF+ range; the usable input range before the ADC clips; the reading
     at 0 V against the firmware's offset-calibration window; the scale spread against the firmware's
     "scales hold across modules within a percent";
  D. overdrive: what +-10 V and +-12 V inputs do: TL074 output swing on the real rails (bus through the
     breakout's B5819W), its input common-mode range (phase reversal), the voltage on each ADC pin against
     its STM32H750 pin type (TT_a / FT_a: absolute maximum and operating VIN), the injected current per pin
     and summed against IINJ, the datasheet's note that negative injection spoils the other channels'
     conversions, PA7's functional-susceptibility row, the Seed datasheet's own GPIO limits;
  E. input impedance (100k, resistive), the stage's filter corner (27k || 1n) against the firmware's
     control rate (step settling within one audio block) and its Nyquist;
  F. ADC sampling: libDaisy's sample time (8.5 cycles at the real ADC clock) against the settling of
     Rs (1k) into the ADC's sample-and-hold plus the pin and track capacitance, with no capacitor at the pin;
  G. stability: loop gain of each section (two-pole TL074 model, its input capacitance, Cf, the 1k + pin
     load): phase margin;
  H. noise at the ADC pin (TL074 en / in, resistor noise, the BIAS divider) in LSB of the 16-bit reading
     the firmware uses and in mV at the jack, against the ADC's own noise;
  I. an unplugged jack reads 0 V (tip to GND_F through the switch lug, GND_F joined to GND on the main
     board through H2), and the GND_F vs GND reference error from the return currents in the header.

Not modelled: ground loops between modules, the TL074's 1/f noise below 10 Hz beyond the datasheet fit,
the STM32's internal ESD structure beyond its datasheet ratings, temperature drift of the resistors.

Run:  cd side-fx/hardware/tests && python test_cv.py
Only reads; writes nothing.
"""
import itertools
import math
import os
import re

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np

import harness

ck = harness.Checks("cv")
circuit = harness.load("circuit")

# ================================================================================================ constants
# --- TL074, TI SLOS080W (rev. July 2025), www.ti.com/lit/ds/symlink/tl074.pdf, TL07xC "all other devices"
#     (DIP-14 TL074CN); figures at VCC = +-15 V, 25 C unless noted (the same numbers the stereo mixer's
#     suite re-read from section 5.8)
TL_VIO_MAX_25C, TL_VIO_MAX_FULL, TL_VIO_TYP = 10e-3, 13e-3, 3e-3   # input offset: max 10 mV 25 C, max 13 mV
#                                                                   0-70 C, typ 3 mV
TL_IIB_MAX_25C, TL_IIB_MAX_FULL = 200e-12, 7e-9                    # input bias: max 200 pA 25 C, 7 nA 70 C
TL_VOM_10K_MIN = 12.0                    # V, max peak output swing min, RL = 10k, at +-15 V (3 V headroom)
TL_VOM_2K_MIN = 10.0                     # V, RL = 2k, min, at +-15 V (5 V headroom)
TL_VS_DS = 15.0                          # the rails those are given at
TL_VICR_NEG_MIN, TL_VICR_POS_MIN = -11.0, 11.0   # common-mode input range, min (guaranteed), at +-15 V
GBW_NEW, GBW_OLD = 5.25e6, 3.0e6         # Hz typ: current die (5.7 / 5.9 tables) / legacy figure
AOL = 2e5                                # V/V typ (200 V/mV, RL >= 2k)
PM_UNITY = 56.0                          # deg typ, follower, RL = 10k, CL = 20 pF
ZO_OL = 125.0                            # ohm typ, open-loop output impedance, 1 MHz
C_ID, C_ICM = 2e-12, 1e-12               # F typ: differential / common-mode input capacitance
EN_1K, EN_10K = 37e-9, 21e-9             # V/rtHz typ at 1 kHz / 10 kHz ("all other devices")
IN_NOISE = 80e-15                        # A/rtHz typ, 1 kHz (H table; the legacy table says 10 fA)
# --- the bus and the breakout's reverse-protection Schottkys (Rob Heel's seed_power_opamps, BOM D2/D3 B5819W)
BUS_V_NOM, BUS_TOL = 12.0, 0.05          # Eurorack +-12 V; the 5 % tolerance is an assumption (Doepfer gives
#                                          no figure for every PSU): not confirmed
B5819W_VF_MAX = 0.60                     # V max at IF = 1 A, 25 C (TL-B5819W datasheet, electrical
#                                          characteristics); at the tens of mA here it is lower: conservative
# --- Daisy Seed (Electrosmith datasheet v1.0.5, 2023-01-25)
#     Table 1 (absolute maximum): GPIO 0 .. +5 V; "all GPIO pins are 5 V tolerant except pin 24 (A2, PB1) and
#     pin 25 (A3, PA7) ...", which are 3.3 V tolerant.  Table 2: A0 = PC0, A1 = PA3, A2 = PB1, A3 = PA7.
SEED_GPIO_ABS_MIN, SEED_GPIO_ABS_MAX = 0.0, 5.0
SEED_33V_ONLY_PINS = {"24", "25"}        # Seed pin numbers of A2, A3
SEED_ADC_PORT = {"22": "PC0", "23": "PA3", "24": "PB1", "25": "PA7"}   # also libDaisy daisy_seed.h D15..D18
#     Schematic (datasheet p. 16, rev 5): VREF+ (ball P1) tied to VDDA (B1) on +3V3_A; VREF- to AGND.
#     p. 15: +3V3_A = LP2985 (U4, 3v3) through FB1; +3V3_D = TPS6217x buck with 47k / 15k feedback.
#     (verify pass: both schematic pages re-read from the images embedded in the PDF: U4 is marked only "3v3
#     LP2985", fed from UNREGULATED_VCC through R1 5R1, so the grade is unknown and the standard grade is the bound;
#     the +3V3_A net with C19 / C20 / C53 / C6 goes to U2POWER's VREF+ and VDDA, so the ADC full scale is 3V3A.)
# --- LP2985-33 (TI SLVS522S, May 2025, 5.5 Electrical Characteristics, VOUT output voltage tolerance):
#     IL = 1 mA: +-1.5 % (legacy standard grade), +-1.0 % (A), +-0.5 % (new chip); 1-50 mA: +-2.5 / 1.5 / 0.5 %;
#     1-50 mA over TJ -40..125 C: +-3.5 % (standard), +-2.5 % (A), +-1 % (new chip). The Seed's grade is not on
#     its schematic ("LP2985 3v3"); 3V3A also feeds the codec and VDDA (tens of mA): the standard grade over
#     load and temperature is the worst case.
V3A_NOM, V3A_TOL = 3.30, 0.035
V3D_NOM, V3D_TOL = 3.30, 0.03            # VDD (3V3D): 0.8 V x (1 + 47k/15k) = 3.307 V; +-3 % assumed (TPS6217x
#                                          feedback accuracy plus the divider's resistors): NOT CONFIRMED
# --- STM32H750, ST DS12556 Rev 7 (www.st.com/resource/en/datasheet/stm32h750ib.pdf)
#     Table 7 (pin definitions): PC0 FT_a, PA3 FT_ha, PB1 TT_a, PA7 TT_a.
#     (verify pass 2026-11-13: re-read Table 7, UFBGA176+25 balls M2 / R2 / R3 / R4, no notes on these four; Table 6:
#     TT = "3.3 V tolerant I/O". The table numbers below are rev Y's; the Seed's rev V silicon has the same figures
#     in Tables 117 / 118 / 120 / 154. Table 117 note 2: "VIN maximum must always be respected" -- the TT limit is a
#     voltage limit that a series resistor does not relax, unlike the negative side, which is current-limited.)
PIN_TYPE = {"PC0": "FT", "PA3": "FT", "PB1": "TT", "PA7": "TT"}
TT_VIN_ABS_MAX = 4.0                     # V, Table 19: input voltage on TT_xx pins, max (absolute)
FT_VIN_ABS_OVER = 4.0                    # V, Table 19: FT_xxx max = Min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V
VIN_ABS_MIN = -0.3                       # V, Table 19: VSS - 0.3 on every pin
TT_VIN_OP_OVER = 0.3                     # V, Table 120: TT_xx I/O input voltage max VDD + 0.3 (operating)
FT_VIN_OP_OVER, FT_VIN_OP_CAP = 3.6, 5.5  # V, Table 120: other I/Os: Min(VDD, VDDA, VDD33USB) + 3.6 V < 5.5 V
IINJ_PIN_NEG, IINJ_PIN_POS = 5e-3, 0.0   # A, Table 20 (absolute maximum): -5 / +0 mA on FT_xxx, TT_xx pins;
#                                          note 3: "positive injection is not possible on these I/Os"
IINJ_SUM = 25e-3                         # A, Table 20: total injected current (absolute sum), max
#     Table 154 (rev V; Table 57 rev Y), I/O current injection susceptibility, functional, by characterisation:
#     row "PA7, PC5, PG1, PB14, ...": negative 5 mA / positive 0; row "PA2, PH2, PH3, PE8, PA6, PA7, PC4, ...":
#     negative 0 / positive NA (PA7 appears in both rows; the stricter is used); "All other I/Os": 5 / NA.
#     (verify pass: confirmed with pdftotext -table on page 233; the same two PA7 rows are in rev Y's Table 57. A
#     characterisation result, not a rating: a failure means an ADC error above 5 LSB TUE or induced leakage on
#     adjacent pins outside -5 / +0 uA while the current flows, not damage.)
SUSCEPT_NEG = {"PC0": 5e-3, "PA3": 5e-3, "PB1": 5e-3, "PA7": 0.0}
#     6.3.20 / 7.3.20 note: "injecting a negative current on any analog input pins should be avoided as this
#     significantly reduces the accuracy of the conversion being performed on another analog input. It is
#     recommended to add a Schottky diode (pin to ground) to analog pins which may potentially inject
#     negative currents."
#     Table 182 (rev V): VAIN 0 .. VREF+; CADC 4 pF typ; RAIN max 170 ohm at 16 bits (125 C) -- given with the
#     shortest sample times of Table 183 (16 bits: only 47 ohm listed, 172 ns on a slow channel), which
#     libDaisy does not use; tCONV = tS + 0.5 + N/2 cycles.
C_ADC = 4e-12                            # F typ, internal sample-and-hold capacitor
C_PIN = 5e-12                            # F typ, I/O pin capacitance CIO (Table 155, rev V)
ADC_BITS = 16
ADC_SNR_TYP = 77.0                       # dB typ, Table 184 (rev V): 16 bits, single ended, fADC 25 MHz,
#                                          VDDA = VREF+ = 3.3 V (ENOB 12.2, SINAD 75.2 dB); BGA, characterisation
# --- libDaisy v9.0.0 per/adc.cpp (downloaded copy): ADC_RESOLUTION_16B, ADC_CLOCK_ASYNC_DIV2 from PLL3R,
#     InitSingle(pin) default speed SPEED_8CYCLES_5; sys/system.cpp: PLL3 M 6, N 295, R 32 from the 16 MHz HSE
#     -> 24.58 MHz; DIV2 -> 12.29 MHz; rev V silicon halves it once more (RM0433; recorded by the Plaitsy port
#     session's check, not re-read here) -> 6.15 MHz.
F_ADC = 16e6 / 6 * 295 / 32 / 2 / 2
T_SAMPLE_CYCLES = 8.5
# --- board, estimates
PF_PER_MM = 0.12e-12                     # F/mm, a 0.3 mm track over / beside the pour on 1.6 mm FR4 (the
#                                          stereo mixer's grounded-coplanar figure ~0.10-0.12 pF/mm)
C_VIA = 0.3e-12                          # F per via (estimate)
R_HEADER_CONTACT = 20e-3                 # ohm max per mated 2.54 mm header contact (typical catalogue figure,
#                                          assumption, not confirmed for these parts)
T_K = 313.0                              # K, inside a warm case
KB = 1.380649e-23
R_SOURCE = 1e3                           # a typical Eurorack output's series resistor
# --- Eurorack signal levels
CV_DOC = 5.0                             # design.md: "CV 1-4, +-5 V"
CV_HOT, CV_BUS = 10.0, 12.0              # common +-10 V CVs; the bus rails a fault or a hot output reaches
# ================================================================================================== design
DOC = harness.text("docs", "design.md")
DOCF = " ".join(DOC.split())
_st = [re.search(p, DOC) for p in (r"jack tip ── (\w+) ──┬", r"├── (\w+) ─+┤", r"└── (\w+) ─+┘",
                                   r"──┬── (\w+) ── Seed ADC")]
DOC_STAGE = [x.group(1) if x else "?" for x in _st]            # Rin, Rf, Cf, Rs as design.md draws them
DOC_STAGE_V = [harness.farads(v) if v[-1:] in "pnu" or (len(v) > 1 and v[1:2] in "pnu") else harness.ohms(v)
               for v in DOC_STAGE] if "?" not in DOC_STAGE else [float("nan")] * 4
_bm = re.search(r"\(R22 (\w+), R23 (\w+), C14", DOCF)
DOC_BIAS = (_bm.group(1), _bm.group(2)) if _bm else ("?", "?")
FW = {f: harness.text("firmware", *f.split("/")) for f in
      ("src/hal_daisy.cc", "src/app/mod_sources.cc", "src/app/mod_sources.h", "src/app/settings.cc",
       "src/ui/ui.cc", "src/engine/config.h", "src/hal.h")}

MAIN = circuit.main_board_parts()
BY_REF = {p.ref: p for p in MAIN}
CH = [name for name, _ in circuit.CV_CHANNELS]


def parts_between(a, b, kind):
    return [p for p in MAIN if p.kind == kind and set(p.nets.values()) == {a, b}]


def val(ref):
    p = BY_REF[ref]
    return harness.ohms(p.value) if p.kind == "R" else harness.farads(p.value)


# ------------------------------------------------------------------------------ A. topology
DOC_TABLE = {}
for m in re.finditer(r"\| CV (\d) \| U6([A-D]) \| (R\d+) \| (R\d+) \| (C\d+) \| (R\d+) \| (A\d) \|", DOC):
    DOC_TABLE[f"CV{m.group(1)}"] = dict(sec="ABCD".index(m.group(2)) + 1, rin=m.group(3), rf=m.group(4),
                                        cf=m.group(5), rs=m.group(6), adc=m.group(7))
ck.check("A.doc_table: design.md's CV table lists all four inputs", sorted(DOC_TABLE) == CH,
         f"expected {CH}, got {sorted(DOC_TABLE)}")
u6 = BY_REF["U6"].nets
STAGE = {}
for name, sec in circuit.CV_CHANNELS:
    out, inm, inp = circuit.SECTION[sec]
    rin = parts_between(name, f"IN_{name}", "R")
    rf = parts_between(f"IN_{name}", f"OA_{name}", "R")
    cf = parts_between(f"IN_{name}", f"OA_{name}", "C")
    rs = parts_between(f"OA_{name}", f"ADC_{name}", "R")
    ok = len(rin) == len(rf) == len(cf) == len(rs) == 1
    ck.check(f"A.stage_parts.{name}: one Rin, Rf, Cf, Rs", ok,
             f"Rin {[p.ref for p in rin]}, Rf {[p.ref for p in rf]}, Cf {[p.ref for p in cf]}, Rs {[p.ref for p in rs]}")
    if not ok:
        continue
    st = dict(rin=rin[0].ref, rf=rf[0].ref, cf=cf[0].ref, rs=rs[0].ref, sec=sec)
    STAGE[name] = st
    ck.check(f"A.opamp_pins.{name}: U6 section {sec} out/in-/in+ on OA/IN/BIAS",
             (u6.get(out), u6.get(inm), u6.get(inp)) == (f"OA_{name}", f"IN_{name}", "BIAS"),
             f"pins {out}/{inm}/{inp} = {u6.get(out)}/{u6.get(inm)}/{u6.get(inp)}")
    d = DOC_TABLE.get(name, {})
    ck.check(f"A.doc_refs.{name}: design.md's designators match circuit.py",
             d and (d["sec"], d["rin"], d["rf"], d["cf"], d["rs"]) == (sec, st["rin"], st["rf"], st["cf"], st["rs"]),
             f"doc {d}, circuit {st}")
    # 2026-11-14: design.md's stage diagram is read, not copied into the test (it said 27k / 1n until H1's fix)
    ck.check(f"A.values.{name}: {' / '.join(DOC_STAGE)} (design.md's stage)",
             all(abs(a - b) <= 1e-6 * b for a, b in zip((val(st["rin"]), val(st["rf"]), val(st["cf"]), val(st["rs"])),
                                                        DOC_STAGE_V)),
             f"{BY_REF[st['rin']].value} / {BY_REF[st['rf']].value} / {BY_REF[st['cf']].value} / {BY_REF[st['rs']].value}")
    seed_pin = [pin for pin, (lib, net) in circuit.SEED.items() if net == f"ADC_{name}"]
    lib = circuit.SEED[seed_pin[0]][0] if seed_pin else "?"
    ck.check(f"A.adc_pin.{name}: ADC_{name} on the Seed pin design.md names ({d.get('adc')})",
             len(seed_pin) == 1 and d.get("adc") in lib, f"Seed pin {seed_pin} = {lib}")
    st["seed_pin"] = seed_pin[0] if seed_pin else None
    st["port"] = SEED_ADC_PORT.get(st["seed_pin"])
ck.check(f"A.bias: R22 3V3A-BIAS, R23 BIAS-GND, C14 BIAS-GND (design.md: R22 {DOC_BIAS[0]}, R23 {DOC_BIAS[1]})",
         set(BY_REF["R22"].nets.values()) == {"3V3A", "BIAS"} and set(BY_REF["R23"].nets.values()) == {"BIAS", "GND"}
         and set(BY_REF["C14"].nets.values()) == {"BIAS", "GND"} and BY_REF["R22"].value == DOC_BIAS[0]
         and BY_REF["R23"].value == DOC_BIAS[1],
         f"R22 {BY_REF['R22'].value} {BY_REF['R22'].nets}, R23 {BY_REF['R23'].value}, C14 {BY_REF['C14'].value}")
ck.check("A.supply: U6 on +12V (pin 4) / -12V (pin 11) with C15 / C16",
         u6.get("4") == "+12V" and u6.get("11") == "-12V"
         and set(BY_REF["C15"].nets.values()) == {"+12V", "GND"} and set(BY_REF["C16"].nets.values()) == {"-12V", "GND"},
         f"pin 4 {u6.get('4')}, pin 11 {u6.get('11')}")

R = harness.routed()
RSTAT = R.main.net_stats()
for name in CH:
    pads = sorted(f"{p.ref}.{p.num}" for p in R.main.pads if p.net == f"ADC_{name}")
    st = STAGE.get(name, {})
    want = sorted([f"{st.get('rs')}.2", f"U5.{st.get('seed_pin')}"]) if st else []
    want_alt = sorted([f"{st.get('rs')}.1", f"U5.{st.get('seed_pin')}"]) if st else []
    ck.check(f"A.routed_adc_net.{name}: ADC_{name} joins only Rs and the Seed pin (no capacitor at the pin)",
             pads in (want, want_alt), f"expected {want}, routed {pads}")
    for net in (name, f"IN_{name}", f"OA_{name}"):
        rp = sorted(f"{p.ref}.{p.num}" for p in R.main.pads if p.net == net)
        gp = sorted(f"{p.ref}.{pid}" for p in MAIN for pid, n in p.nets.items() if n == net)
        ck.check(f"A.routed_pads.{net}: routed pads = circuit.py's", rp == gp, f"circuit {gp}, routed {rp}")
for name in CH:
    port = STAGE.get(name, {}).get("port")
    print(f"      {name}: Seed pin {STAGE.get(name, {}).get('seed_pin')} = {port} ({PIN_TYPE.get(port)}_a), "
          f"ADC track {RSTAT.get('ADC_' + name, {}).get('length', 0):.1f} mm")

# ------------------------------------------------------------------------------ B. DC transfer, typical
RIN, RF, RS = val("R10"), val("R11"), val("R12")
CF = val("C10")
R22, R23 = val("R22"), val("R23")


def vbias(v3a, r22=R22, r23=R23):
    return v3a * r23 / (r22 + r23)


def vout(vin, v3a=V3A_NOM, rin=RIN, rf=RF, r22=R22, r23=R23, vos=0.0, ib=0.0):
    """TL074 output (the ADC pin while it is inside the rails and not clamped)."""
    g = rf / rin
    return (vbias(v3a, r22, r23) + vos) * (1 + g) - g * vin + ib * rf


m = re.search(r"V_adc = ([\d.]+) V − ([\d.]+)·V_in", DOCF)
doc_off, doc_gain = (float(m.group(1)), float(m.group(2))) if m else (float("nan"), float("nan"))
ck.check("B.doc_formula_found: design.md states V_adc = a - b V_in", bool(m), "")
ck.close("B.gain: Rf / Rin = design.md's 0.27", RF / RIN, doc_gain, 0.0005)
ck.close("B.offset: V_adc at 0 V = design.md's 1.676 V (typical)", vout(0.0), doc_off, 0.0015, " V")
m = re.search(r"±5 V lands on ([\d.]+)–([\d.]+) V", DOCF)
lo_doc, hi_doc = (float(m.group(1)), float(m.group(2))) if m else (float("nan"),) * 2
ck.close("B.plus5: +5 V -> design.md's low end", vout(5.0), lo_doc, 0.006, " V")
ck.close("B.minus5: -5 V -> design.md's high end", vout(-5.0), hi_doc, 0.006, " V")
m = re.search(r"BIAS ([\d.]+) V", DOCF)
ck.close(f"B.bias: BIAS = design.md's {m.group(1) if m else '?'} V (to its last digit)", vbias(V3A_NOM),
         float(m.group(1)) if m else float("nan"), 0.005, " V")
# the firmware's nominal calibration: volts = (raw - offset) * scale, raw = V_adc / VREF+ (VREF+ = 3V3A)
mo = re.search(r"offset\[i\] = ([\d.]+)f;", FW["src/app/mod_sources.cc"])
ms = re.search(r"scale\[i\] = (-?[\d.]+)f;", FW["src/app/mod_sources.cc"])
fw_off, fw_scale = float(mo.group(1)), float(ms.group(1))
ck.close("B.fw_offset: firmware nominal offset = V_adc(0 V) / VREF+ (typical)", fw_off, vout(0.0) / V3A_NOM, 0.0005)
ck.close("B.fw_scale: firmware nominal scale = -VREF+ / gain (V per full scale)", fw_scale, -V3A_NOM / (RF / RIN), 0.02,
         " V")
mr = re.search(r"return ([\d.]+)f;\s*// what 0 V reads", FW["src/hal_daisy.cc"])
ck.close("B.fw_readcv_default: ReadCv()'s 'what 0 V reads' = V_adc(0) / VREF+", float(mr.group(1)) if mr else -1,
         vout(0.0) / V3A_NOM, 0.001)


# ------------------------------------------------------------------------------ C. worst case
def corners(vin):
    """(V_adc, code = V_adc / VREF+) over every corner: R10/R11/R22/R23 +-1 %, 3V3A +-tol, Vos, Ib (full range)."""
    out = []
    for s in itertools.product((-1, 1), repeat=7):
        v3a = V3A_NOM * (1 + s[0] * V3A_TOL)
        v = vout(vin, v3a, RIN * (1 + 0.01 * s[1]), RF * (1 + 0.01 * s[2]), R22 * (1 + 0.01 * s[3]),
                 R23 * (1 + 0.01 * s[4]), s[5] * TL_VIO_MAX_FULL, s[6] * TL_IIB_MAX_FULL)
        out.append((v, v / v3a, v3a))
    return out


for vin in (CV_DOC, -CV_DOC):
    c = corners(vin)
    vmin, vmax = min(x[0] for x in c), max(x[0] for x in c)
    cmin, cmax = min(x[1] for x in c), max(x[1] for x in c)
    ck.within(f"C.range_{vin:+.0f}V: worst-case ADC reading inside 0..VREF+ (code 0..1)", cmin if vin > 0 else cmax,
              0.0 if vin > 0 else None, None if vin > 0 else 1.0, "",
              f"V_adc {vmin:.3f}..{vmax:.3f} V, code {cmin:.4f}..{cmax:.4f}")
# usable input range: where the worst corner reaches code 0 (V_adc = 0) or code 1 (V_adc = VREF+); bounded by
# the lowest 0 V reading over the steepest gain, and the smallest headroom to VREF+ over the steepest gain
use_pos = min(x[0] for x in corners(0.0)) / (RF * 1.01 / (RIN * 0.99))
use_neg = -min(x[2] - x[0] for x in corners(0.0)) / (RF * 1.01 / (RIN * 0.99))
typ_pos, typ_neg = vout(0.0) / (RF / RIN), -(V3A_NOM - vout(0.0)) / (RF / RIN)
print(f"      usable CV range before the ADC clips: typ {typ_neg:+.2f} .. {typ_pos:+.2f} V, worst {use_neg:+.2f} .. "
      f"{use_pos:+.2f} V")
ck.check("C.usable_range: worst case still reads the doc's full +-5 V without clipping",
         use_pos >= CV_DOC and use_neg <= -CV_DOC, f"worst {use_neg:+.2f} .. {use_pos:+.2f} V")
# the firmware's offset calibration window (ui.cc DoCalibrate, settings.cc kMinOffset / kMaxOffset)
mw = re.search(r"raw >= ([\d.]+)f && raw <= ([\d.]+)f", FW["src/ui/ui.cc"])
cal_lo, cal_hi = (float(mw.group(1)), float(mw.group(2))) if mw else (float("nan"),) * 2
c0 = [x[1] for x in corners(0.0)]
ck.within("C.cal_window: worst-case reading at 0 V inside the setup page's calibration window (ui.cc)", min(c0),
          cal_lo, cal_hi, "", f"0 V reads {min(c0):.4f}..{max(c0):.4f}")
ck.within("C.cal_window_hi: ... upper corner", max(c0), cal_lo, cal_hi)
mb = re.search(r"kMinOffset = ([\d.]+)f;.*?kMaxOffset = ([\d.]+)f;.*?kMinScale = (-?[\d.]+)f;.*?kMaxScale = (-?[\d.]+)f;",
               FW["src/app/settings.cc"], re.S)
smin, smax = float(mb.group(3)), float(mb.group(4))
scales = []
for s in itertools.product((-1, 1), repeat=3):
    v3a = V3A_NOM * (1 + s[0] * V3A_TOL)
    g = RF * (1 + 0.01 * s[1]) / (RIN * (1 + 0.01 * s[2]))
    scales.append(-v3a / g)
ck.check("C.scale_bounds: worst-case true scale inside settings.cc's kMinScale..kMaxScale",
         smin <= min(scales) and max(scales) <= smax, f"{min(scales):.2f}..{max(scales):.2f} V vs {smin}..{smax}")
spread = max(abs(s / fw_scale - 1) for s in scales)
# 2026-11-14: ui.cc's claim is read ('within a percent' until the comment was corrected)
_mc = re.search(r"within a percent|up to about (\d+(?:\.\d+)?) %", FW["src/ui/ui.cc"])
claim = (0.01 if _mc.group(1) is None else float(_mc.group(1)) / 100) if _mc else 0.0
ck.check(f"C.scale_spread: worst-case scale within ui.cc's stated spread ({claim * 100:.0f} %; DoCalibrate keeps the "
         "nominal scale)", spread <= claim,
         f"worst {spread * 100:.2f} % (1 % resistors on Rf / Rin: 2 %, 3V3A {V3A_TOL * 100:.1f} %); at 5 V that is "
         f"{spread * 5e3:.0f} mV")
off_mv = max(abs(x[1] - fw_off) for x in corners(0.0)) * abs(fw_scale) * 1e3
print(f"      uncalibrated offset at the jack, worst case: {off_mv:.0f} mV (the setup page zeroes it)")

# ------------------------------------------------------------------------------ D. overdrive
RAIL_MIN = BUS_V_NOM * (1 - BUS_TOL) - B5819W_VF_MAX
SWING = RAIL_MIN - (TL_VS_DS - TL_VOM_10K_MIN)          # guaranteed swing at the low rails, RL >= 10k
VDD_MIN = V3D_NOM * (1 - V3D_TOL)
V3A_MIN = V3A_NOM * (1 - V3A_TOL)


def vout_extremes(vin):
    c = corners(vin)
    return min(x[0] for x in c), max(x[0] for x in c)


for vin in (CV_HOT, -CV_HOT, CV_BUS, -CV_BUS):
    lo, hi = vout_extremes(vin)
    ck.within(f"D.swing_{vin:+.0f}V: TL074 output stays linear on the real rails (+-{SWING:.1f} V guaranteed)",
              hi if vin < 0 else lo, -SWING if vin > 0 else None, SWING if vin < 0 else None, " V",
              f"output {lo:+.2f}..{hi:+.2f} V; rails {RAIL_MIN:.2f} V worst")
# inputs: both op-amp inputs sit at BIAS (virtual ground) as long as the output is linear
ck.within("D.common_mode: TL074 inputs at BIAS inside the guaranteed common-mode range at the low rails (no phase "
          "reversal while the output is linear)", vbias(V3A_NOM * 1.03), -RAIL_MIN + (TL_VS_DS + TL_VICR_NEG_MIN),
          RAIL_MIN - (TL_VS_DS - TL_VICR_POS_MIN), " V")


def pin_state(v_oa, port):
    """(pin voltage, injected current; - = out of the pin) for an op-amp output v_oa behind Rs.
    Negative side: the pin's diode to VSS, taken to clamp at VIN_ABS_MIN (-0.3 V; a silicon ESD diode at
    these currents sits nearer -0.6 V, so the current here is an upper bound). Positive side: an FT pin has
    no path to VDD (it just follows); a TT pin is taken to clamp at 4.0 V, its absolute maximum."""
    rs_min = RS * 0.99
    if v_oa < VIN_ABS_MIN:
        return VIN_ABS_MIN, (v_oa - VIN_ABS_MIN) / rs_min
    if PIN_TYPE[port] == "TT" and v_oa > TT_VIN_ABS_MAX:
        return TT_VIN_ABS_MAX, (v_oa - TT_VIN_ABS_MAX) / rs_min
    return v_oa, 0.0


for name in CH:
    port = STAGE.get(name, {}).get("port")
    lo10, hi10 = vout_extremes(-CV_HOT)
    lo12, hi12 = vout_extremes(-CV_BUS)
    if PIN_TYPE.get(port) == "TT":
        # one check per pin: a -10 V CV (common: an inverted envelope, a +-10 V LFO) against the TT pin's
        # absolute maximum; the operating limit and the -12 V figure go in the detail
        ck.within(f"D.tt_overvoltage_-10V.{name}: {port} (TT_a, Seed pin {STAGE[name]['seed_pin']}, 3.3 V tolerant) "
                  f"stays below its {TT_VIN_ABS_MAX} V absolute maximum with -10 V at the jack", hi10, None,
                  TT_VIN_ABS_MAX, " V",
                  f"the TL074 drives it through {RS:.0f} ohm with nothing to clamp it; {hi12:.2f} V at -12 V; the "
                  f"operating limit VDD + 0.3 = {VDD_MIN + TT_VIN_OP_OVER:.2f} V; TT pins allow +0 mA injection "
                  f"({max(0.0, (hi10 - TT_VIN_ABS_MAX) / (RS * 0.99)) * 1e3:.2f} mA if an internal clamp took it)")
    else:
        # verify pass 2026-11-13: Table 120 caps the FT operating limit, "Min(VDD, VDDA, VDD33USB) + 3.6 V < 5.5 V";
        # the check used 6.8 V (the sum without the cap). Now min(sum, 5.5 V).
        ck.within(f"D.ft_overvoltage_-12V.{name}: {port} (FT_a) below Min(VDD, VDDA) + 3.6 V, capped at 5.5 V "
                  f"(operating) with -12 V at the jack", hi12, None,
                  min(min(VDD_MIN, V3A_MIN) + FT_VIN_OP_OVER, FT_VIN_OP_CAP), " V")
        ck.within(f"D.seed_gpio_abs_-12V.{name}: below the Seed datasheet's +5 V GPIO absolute maximum (Table 1) "
                  f"with -12 V at the jack", hi12, None, SEED_GPIO_ABS_MAX, " V",
                  f"{hi10:.2f} V at -10 V; the STM32's own FT limit is VDD + 4.0 V")
# where the limits are crossed
g_hi = RF * 1.01 / (RIN * 0.99)
x_tt = -(TT_VIN_ABS_MAX - max(x[0] for x in corners(0.0))) / g_hi
x_op = -(VDD_MIN + TT_VIN_OP_OVER - max(x[0] for x in corners(0.0))) / g_hi
x_neg = (min(x[0] for x in corners(0.0)) - SEED_GPIO_ABS_MIN) / g_hi
x_inj = (min(x[0] for x in corners(0.0)) - VIN_ABS_MIN) / g_hi
print(f"      worst case: A2/A3 pass VDD+0.3 V below {x_op:+.2f} V and 4.0 V below {x_tt:+.2f} V at the jack; every "
      f"ADC pin goes below 0 V above {x_neg:+.2f} V and below -0.3 V above {x_inj:+.2f} V")
# negative side: the pin clamps to VSS
inj = {}
for vin in (CV_HOT, CV_BUS):
    lo, hi = vout_extremes(vin)
    for name in CH:
        inj[(vin, name)] = pin_state(lo, STAGE.get(name, {}).get("port"))[1]
lo12 = vout_extremes(CV_BUS)[0]
for name in CH:
    port = STAGE.get(name, {}).get("port")
    i12 = inj[(CV_BUS, name)]
    ck.within(f"D.inj_abs_+12V.{name}: +12 V at the jack: injected current within the -5 mA absolute maximum ({port})",
              -i12 * 1e3, None, IINJ_PIN_NEG * 1e3, " mA", f"TL074 output {lo12:+.2f} V behind {RS:.0f} ohm, pin "
                                                          f"clamp taken at {VIN_ABS_MIN} V (an upper bound)")
    i10 = inj[(CV_HOT, name)]
    ck.within(f"D.inj_susceptibility_+10V.{name}: +10 V at the jack: injection within {port}'s functional-"
              f"susceptibility row (Table 154: {SUSCEPT_NEG[port] * 1e3:.0f} mA)", -i10 * 1e3, None,
              SUSCEPT_NEG[port] * 1e3, " mA")
tot12 = sum(abs(inj[(CV_BUS, n)]) for n in CH)
ck.within("D.inj_sum_+12V: all four inputs at +12 V: summed injection within the 25 mA absolute maximum", tot12 * 1e3,
          None, IINJ_SUM * 1e3, " mA")
lo10 = vout_extremes(CV_HOT)[0]
ck.check(f"D.no_neg_injection_+10V: a +10 V CV keeps its ADC pin at or above 0 V: no negative injection (DS12556: it "
         f"'significantly reduces the accuracy' of the conversions on the other analog inputs; the Seed datasheet's "
         f"GPIO minimum is 0 V)", lo10 >= SEED_GPIO_ABS_MIN,
         f"TL074 output {lo10:+.2f} V behind {RS:.0f} ohm: up to {max(-inj[(CV_HOT, n)] for n in CH) * 1e3:.2f} mA per "
         f"pin; every channel goes below 0 V above {x_neg:+.1f} V at the jack (worst case), below -0.3 V above "
         f"{x_inj:+.1f} V. ST recommends a Schottky from each such pin to ground. (ST's hard limits, VSS - 0.3 V or "
         f"-5 mA when the current is limited, are met: this is the accuracy note, and a 0..+8 V envelope already "
         f"crosses it)")

# Value-only fixes to try (printed, not checked): a smaller Rf and a higher BIAS put +-10 V inside 0..VREF+ and
# keep +-12 V off the TT pins' limits; Cf scaled up keeps the corner near 5.9 kHz (Rf 13k: 2n2; 15k: 1n8).
for rf_fix, r23_fix in ((15e3, 12e3), (13e3, 12e3)):
    _fix = []
    for vin in (CV_HOT, -CV_HOT, CV_BUS, -CV_BUS):
        vals = [vout(vin, V3A_NOM * (1 + s0 * V3A_TOL), RIN * (1 + 0.01 * s1), rf_fix * (1 + 0.01 * s2),
                     R22 * (1 + 0.01 * s3), r23_fix * (1 + 0.01 * s4), s5 * TL_VIO_MAX_FULL, 0.0)
                for s0, s1, s2, s3, s4, s5 in itertools.product((-1, 1), repeat=6)]
        _fix.append(f"{vin:+.0f} V -> {min(vals):+.2f}..{max(vals):+.2f} V")
    print(f"      fix to try, Rf {rf_fix / 1e3:.0f}k + R23 {r23_fix / 1e3:.0f}k (worst case at the ADC pin): "
          + "; ".join(_fix))

# ------------------------------------------------------------------------------ E. input impedance, filter
zin = RIN  # the summing node is a virtual ground (loop gain >> 1 at CV frequencies)
ck.close("E.zin: input impedance = Rin = 100k (resistive: Cf sits in the feedback)", zin / 1e3, 100.0, 1.0, "k")
fc = 1 / (2 * math.pi * RF * CF)
m = re.search(r"kBlockSize = (\d+)", FW["src/engine/config.h"])
block = int(m.group(1))
fs_audio = 48e3
t_block = block / fs_audio
tau = RF * CF
t_settle = tau * math.log(2 ** (ADC_BITS + 1))
print(f"      filter corner 1 / (2 pi 27k 1n) = {fc / 1e3:.2f} kHz; tau {tau * 1e6:.0f} us; the firmware reads every "
      f"{t_block * 1e3:.2f} ms (Nyquist {0.5 / t_block:.0f} Hz)")
ck.within("E.step_settles_in_a_block: a CV step settles to 16 bits within one audio block (the read rate)",
          t_settle * 1e3, None, t_block * 1e3, " ms", f"{t_settle * 1e6:.0f} us = ln(2^17) tau")
att_nyq = 1 / math.sqrt(1 + (0.5 / t_block / fc) ** 2)
print(f"      the 1n pole passes {harness.db(att_nyq):+.2f} dB at the read rate's Nyquist ({0.5 / t_block:.0f} Hz): it "
      f"does not anti-alias the per-block read; CV content above that folds")

# ------------------------------------------------------------------------------ F. ADC sampling
t_s = T_SAMPLE_CYCLES / F_ADC
for name in CH:
    L = RSTAT.get(f"ADC_{name}", {}).get("length", 0.0)
    nv = RSTAT.get(f"ADC_{name}", {}).get("vias", 0)
    c_ext = L * PF_PER_MM + nv * C_VIA + C_PIN
    # worst case: the sample cap starts at the other rail (the previous channel at 0 V, this one at VREF+):
    # charge sharing with c_ext first, then Rs (+1 %) recharges both, tau = Rs (C_ADC + c_ext)
    tau_s = RS * 1.01 * (C_ADC + c_ext)
    need = tau_s * math.log(2 ** (ADC_BITS + 1) * C_ADC / (C_ADC + c_ext))
    ck.within(f"F.settling.{name}: Rs into the sample cap + {c_ext * 1e12:.1f} pF settles to 1/2 LSB at 16 bits within "
              f"libDaisy's {T_SAMPLE_CYCLES} cycles", need * 1e9, None, t_s * 1e9, " ns",
              f"tau {tau_s * 1e9:.1f} ns, sample time {t_s * 1e9:.0f} ns at fADC {F_ADC / 1e6:.2f} MHz")
t_conv = (T_SAMPLE_CYCLES + 0.5 + ADC_BITS / 2) / F_ADC
mo = re.search(r"OverSampling kOversampling = AdcHandle::OVS_(\d+);", FW["src/hal_daisy.cc"])
ovs = int(mo.group(1))
mc = re.search(r"at ~([\d.]+) us per conversion", FW["src/hal_daisy.cc"])
ck.close("F.conversion_time: hal_daisy.cc's '~2.8 us per conversion' = (tS + 0.5 + N/2) / fADC",
         t_conv * 1e6, float(mc.group(1)) if mc else -1, 0.15, " us")
t_set = len(CH) * ovs * t_conv
ck.within("F.scan_period: a full oversampled 4-channel set within one audio block (hal_daisy.cc: 'several per block')",
          t_set * 1e3, None, t_block * 1e3 / 2, " ms", f"{len(CH)} x {ovs} x {t_conv * 1e6:.2f} us")

# ------------------------------------------------------------------------------ G. stability (loop gain)


class Opamp:
    """Two-pole TL074 section: A(s) = A0 / ((1 + s/w1)(1 + s/w2)), w2 fitted so that a follower into 10k || 20 pF
    (the datasheet's condition) has the datasheet's phase margin; open-loop output resistance ZO."""

    def __init__(self, gbw, pm=PM_UNITY, a0=AOL, zo=ZO_OL):
        self.gbw, self.a0, self.zo = gbw, a0, zo
        self.w1 = 2 * math.pi * gbw / a0
        lo, hi = 2 * math.pi * 1e5, 2 * math.pi * 1e9
        for _ in range(60):
            mid = math.sqrt(lo * hi)
            lo, hi = (lo, mid) if self._pm_follower(mid) > pm else (mid, hi)
        self.w2 = math.sqrt(lo * hi)

    def A(self, s, w2=None):
        return self.a0 / ((1 + s / self.w1) * (1 + s / (w2 or self.w2)))

    def _pm_follower(self, w2):
        f = np.logspace(4, 9, 3000)
        s = 2j * np.pi * f
        zl = 1 / (1 / 10e3 + s * 20e-12)
        t = self.A(s, w2) * zl / (zl + self.zo)
        i = int(np.argmax(np.abs(t) < 1))
        return 180 + np.degrees(np.unwrap(np.angle(t)))[i]


def stage_loop(op, f, c_adc_node, c_in_node, src_r):
    """Loop gain of one inverting stage at f (array). Nodes: IN (summing), OUT (after ZO), ADC (after Rs).
    BIAS is AC ground (C14 1 uF); the jack is a source of src_r ohm (0 = unplugged, tip on GND_F)."""
    s = 2j * np.pi * f
    T = np.zeros(len(f), complex)
    for k, sk in enumerate(s):
        # unknowns: v_in, v_out, v_adc; the VCVS broken: internal node = 1 V
        y_in = 1 / (RIN + src_r) + 1 / RF + sk * CF + sk * (c_in_node + C_ID + C_ICM)
        y_out = 1 / op.zo + 1 / RF + sk * CF + 1 / RS
        y_adc = 1 / RS + sk * c_adc_node
        Y = np.array([[y_in, -(1 / RF + sk * CF), 0],
                      [-(1 / RF + sk * CF), y_out, -1 / RS],
                      [0, -1 / RS, y_adc]], complex)
        b = np.array([0, 1 / op.zo, 0], complex)
        v = np.linalg.solve(Y, b)
        T[k] = -op.A(sk) * (0 - v[0])            # IN+ is AC ground
    return T


F_LOOP = np.logspace(4, 8.3, 300)


def phase_margin(T):
    mag, ph = np.abs(T), np.degrees(np.unwrap(np.angle(T)))
    i = int(np.argmax(mag < 1))
    if i == 0:
        return float("nan"), float("nan")
    w = math.log(mag[i - 1]) / (math.log(mag[i - 1]) - math.log(mag[i]))
    fcx = F_LOOP[i - 1] * (F_LOOP[i] / F_LOOP[i - 1]) ** w
    return 180 + (ph[i - 1] + w * (ph[i] - ph[i - 1])), fcx


# the loop gain's sign convention: at low frequency T must be +large (negative feedback)
for name in CH:
    L = RSTAT.get(f"ADC_{name}", {}).get("length", 0.0)
    c_adc = L * PF_PER_MM + C_PIN + C_ADC
    c_in = RSTAT.get(f"IN_{name}", {}).get("length", 0.0) * PF_PER_MM + 3 * 0.5e-12   # track + three pads
    rows = []
    for op, oname in ((Opamp(GBW_NEW), "GBW 5.25 MHz"), (Opamp(GBW_OLD), "GBW 3 MHz")):
        for src in (0.0, R_SOURCE):
            T = stage_loop(op, F_LOOP, c_adc, c_in, src)
            pm, fx = phase_margin(T)
            rows.append((pm, fx, oname, src, T[0].real > 0))
    pm, fx, oname, src, sign_ok = min(rows)
    ck.check(f"G.phase_margin.{name}: >= 45 deg with Cf, the input capacitance and the 1k + pin load", pm >= 45 and sign_ok,
             f"worst {pm:.1f} deg at {fx / 1e6:.2f} MHz ({oname}, source {src:.0f} ohm)")

# ------------------------------------------------------------------------------ H. noise
_r = (EN_1K / EN_10K) ** 2
FC_1F = (_r - 1) / (1 / 1e3 - _r / 1e4)
ENW = EN_10K / math.sqrt(1 + FC_1F / 1e4)
FN = np.logspace(0, 8, 600)


def noise_at_adc(name, op, src_r):
    """rms noise at the ADC pin, 1 Hz .. 100 MHz (the sample-and-hold's own bandwidth is higher; the pin node's
    Rs x C pole limits it): TL074 en and in, Johnson noise of Rin, Rf, Rs and the source resistance, the BIAS
    divider's noise through C14."""
    L = RSTAT.get(f"ADC_{name}", {}).get("length", 0.0)
    c_adc = L * PF_PER_MM + C_PIN + C_ADC
    psd = np.zeros(len(FN))
    rb = R22 * R23 / (R22 + R23)
    cb = val("C14")
    for k, f in enumerate(FN):
        s = 2j * math.pi * f
        a = op.A(s)
        zf = 1 / (1 / RF + s * CF)
        zg = RIN + src_r
        # closed-loop transfer from an input-referred source at IN+ (en, BIAS noise) to OUT: NG / (1 + NG / A)
        ng = 1 + zf / zg
        h_p = ng / (1 + ng / a)
        # from a current at the summing node (in, Rf / Rin Johnson currents) to OUT: -zf / (1 + ng / a)
        h_i = zf / (1 + ng / a)
        h_pin = 1 / (1 + s * RS * c_adc)                     # OUT -> ADC pin (ZO << Rs)
        e_bias2 = 4 * KB * T_K * rb / abs(1 + s * rb * cb) ** 2
        en2 = ENW ** 2 * (1 + FC_1F / f)
        i2 = 4 * KB * T_K / RF + 4 * KB * T_K / zg + 2 * IN_NOISE ** 2
        e_rs2 = 4 * KB * T_K * RS * abs(1 / (1 + s * RS * c_adc)) ** 2      # Rs's own noise, filtered at the pin
        psd[k] = (abs(h_p) ** 2 * (en2 + e_bias2) + abs(h_i) ** 2 * i2) * abs(h_pin) ** 2 + e_rs2
    return float(np.sqrt(np.trapezoid(psd, FN)))


LSB = V3A_NOM / 2 ** ADC_BITS
worst_n = max((noise_at_adc(n, Opamp(GBW_NEW), src), n, src) for n in CH for src in (0.0, R_SOURCE))
vn, nname, nsrc = worst_n
print(f"      16-bit LSB = {LSB * 1e6:.1f} uV at the ADC = {LSB / (RF / RIN) * 1e3:.3f} mV at the jack; "
      f"front-end noise {vn * 1e6:.1f} uV rms ({vn / LSB:.2f} LSB) per conversion, {vn / math.sqrt(ovs) * 1e6:.1f} uV "
      f"after OVS_{ovs}, = {vn / (RF / RIN) * 1e3:.3f} / {vn / math.sqrt(ovs) / (RF / RIN) * 1e3:.3f} mV rms at the jack")
ADC_NOISE = V3A_NOM / (2 * math.sqrt(2)) / 10 ** (ADC_SNR_TYP / 20)    # rms, from the typical SNR
ck.within("H.noise_below_adc: the front end's noise per conversion below the ADC's own (Table 184: SNR 77 dB typ "
          "= that many LSB rms)", vn / LSB, None, ADC_NOISE / LSB, " LSB", f"{nname}, source {nsrc:.0f} ohm; together "
          f"{math.hypot(vn, ADC_NOISE) / LSB:.2f} LSB rms per conversion")
ck.within("H.noise_at_jack: front-end noise after the firmware's oversampling <= 1 mV rms at the jack scale (-80 dB "
          "re 10 V; criterion, no doc figure)",
          vn / math.sqrt(ovs) / (RF / RIN) * 1e3, None, 1.0, " mV")

# ------------------------------------------------------------------------------ I. unplugged jack, GND_F
JACKS = {ref: (lbl, tip, lug) for ref, lbl, tip, lug in circuit.JACKS}
for name in CH:
    jref = next((r for r, (lbl, tip, lug) in JACKS.items() if tip == f"{name}_F"), None)
    lbl, tip, lug = JACKS.get(jref, (None, None, None))
    ck.check(f"I.unplugged.{name}: the CV jack's switch lug grounds the tip (GND_F) when unplugged (design.md)",
             lug == "GND_F", f"{jref} lug {lug}")
fb = {p.ref: p for p in circuit.faceplate_parts()}
gnd_pins = [(ref, i + 1) for ref, kind, pins in circuit.HEADERS for i, (mb, f) in enumerate(pins) if f == "GND_F"]
ck.check("I.gnd_f_header: GND_F reaches the main board's GND through at least one header pin",
         len(gnd_pins) >= 1 and all(circuit.HEADERS[[h[0] for h in circuit.HEADERS].index(r)][2][n - 1][0] == "GND"
                                    for r, n in gnd_pins), f"{gnd_pins}")
# a CV reads (V_tip - V_GNDF) + (V_GNDF - V_GND): the second term is the header's drop. Worst-case current
# through the GND_F pins: both audio outputs returning 10 V peak into 10k loads, four CVs at +12 V into 100k,
# the clock at +12 V into 100k, both audio inputs (breakout input ~ 30k assumed: +-10 V)
i_ret = 2 * 10 / 10e3 + 4 * 12 / 100e3 + 12 / 100e3 + 2 * 10 / 30e3
r_ret = R_HEADER_CONTACT / len(gnd_pins) if gnd_pins else float("inf")
v_err = i_ret * r_ret
ck.within("I.gnd_f_error: GND_F - GND drop from the faceplate's return currents < 1 LSB at the jack scale",
          v_err * 1e3, None, LSB / (RF / RIN) * 1e3, " mV",
          f"{i_ret * 1e3:.1f} mA through {len(gnd_pins)} pin(s) at {R_HEADER_CONTACT * 1e3:.0f} mOhm (header only; the "
          f"pours add little)")

ck.done()
