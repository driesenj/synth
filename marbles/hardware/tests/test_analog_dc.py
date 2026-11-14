"""analog_dc: static behaviour of Marblesy's analog circuits, by nodal analysis of circuit.py's netlist.

Every stage is built from circuit.py's parts (resistors found by the nets they join, TL074 sections by
their pins; faceplate nets merged with the main-board nets they mate with), so a value change in
circuit.py changes the result. Rails: the +-12 V bus through the breakout's B5819W and 2.2 uH
(analog_solver.rails), typical and worst. 3V3A / 3V3D +-3 % (assumed), the ADC's VREF+ = 3V3A.

What it checks
  A  CV inputs (7x U3/U4): design.md's transfer (1.776 V - 0.13 Vin, +-5 V -> 1.13..2.43 V, BIAS 1.57 V);
     the worst case (1 % resistors, BIAS divider, 3V3A, TL074 offset) inside the ADC's 0..VREF+ with
     headroom; the firmware's constants against circuit.py; whether Marbles' calibration (offset at 0 V,
     1 V / 3 V scale on RATE and SPREAD) accepts the spread and keeps it after a reboot (FIX_OUTLIER
     +-10 %); the TL074's common-mode range and swing on the real rails
  B  over-range: +-10 V and +-12 V CVs against the STM32H750's absolute maximum input voltage per pin type
     (TT_a 4.0 V; FT VDD + 4 V; the Seed's own 0..5 V) and against the limit for a pin whose ADC input is
     active (min(VDDA, VREF+) + 0.3 V for FT_a and TT_a alike, AN4899), injected current per pin (-5 / +0 mA)
     and in total (25 mA), the functional-susceptibility table and the ADC's negative-injection note;
     design.md's "about 1.3 mA ... within the STM32H7's limit"
  C  pots and mux: B10k across 3V3A_F, 74HC4051 at VCC = 3V3A_F (supply range, analog range, address
     levels from the 3V3D GPIO), leakage loading at the worst source impedance, the reading span; the
     BOM's "CD4051B also works" at VDD = 3.3 V
  D  reference: LM4040-2.5 (grade C) current at the worst corners against its minimum / maximum operating
     current, with the DACs' VREF inputs buffered and unbuffered; design.md's 0.53 / 0.25 / 0.28 mA and
     60-65 uA; drift after calibration; the Power section's figure
  E  NEG_REF inverter: -VREF R43/R42, its tolerance (design.md's +-2 %) and load, its swing
  F  DAC output stages (4x U5): design.md's code 0 -> +5.32 V, 4095 -> -5.45 V, its worst case (-5.11 /
     -5.06 V) and Monte Carlo (-5.16 V in 99 %, none short of +-5 V) re-run with its assumptions; then the
     full worst case and Monte Carlo with the MCP4922's offset / gain error and the TL074 offsets, into
     100k and 10k through the 1k; the output calibrator's +-10 % plausibility window and the 12-bit code
     range left after calibration; the calibration points; the MCP4922's VREF / output ranges; INL in
     cents; design.md's 2.6 mV per step
  G  gate outputs (3x U6): gain 2.5 -> 8.25 V, the faceplate LED (3k3 + green LED) and a 10k / 100k load:
     design.md's 1.5 mA / 1.5 V / "stays above 6 V", worst case on the real rails; the low level; the
     stage while the GPIO is still high-impedance (reset, bootloader)
  H  clock inputs (Q1/Q2): the jack voltage where the collector crosses the GPIO's VIL / VIH (hFE min,
     VBE range, BAT85 leakage) against design.md's 0.7 V; +12 V and -12 V inputs (base current, BAT85
     current, VEBO); the normalization probe saturating the transistor with the worst hFE; the firmware's
     pin setup
  I  the spare section U6D

Run:  cd marbles/hardware/tests && python test_analog_dc.py
Only reads circuit.py, design.md, bom.md and the firmware sources; writes nothing.
"""
import math
import os
import re

import numpy as np

import harness
import analog_solver as S
from analog_solver import Mna, one, node, part, section_pins, seed_pin_of

ck = harness.Checks("analog_dc")
C = S.CIRCUIT

# ================================================================================================ constants
# Resistors: 1 % metal film (docs/bom.md, every resistor line). Capacitors don't matter at DC.
R_TOL = 0.01
# LM4040-N, TI SNOS633N (Dec 1991, rev. Aug 2025), 5.9 "2.5V ... Grades C, D, E; Temperature Grade I", the
# ordered LM4040CIZ-2.5 (bom.md): VR 2.500 V at IR = 100 uA
LM_VR = 2.5
LM_TOL = {"A": 0.001, "B": 0.002, "C": 0.005, "D": 0.01}   # initial tolerance at 25 C (A/B from table 5.8)
LM_TOL_FULL_C = 0.0115                                      # C grade over -40..85 C (note 3: 0.5 % + 100 ppm x 65)
LM_TC_MAX = 100e-6                                          # /C max, IR = 1 mA (typ 15 ppm)
LM_IRMIN_TYP, LM_IRMIN_25C, LM_IRMIN_FULL = 45e-6, 60e-6, 65e-6   # A: typ / max 25 C / max -40..85 C
LM_IR_MAX = 15e-3                                           # A, maximum operating current (5.3)
LM_DVR_MAX = 1.0e-3                                         # V, VR change IRMIN..1 mA, max over temperature
#   (The other TI datasheet, SLOS456Q's LM4040C25I, a different die, gives IZ,min max 75 / 80 uA; the /NOPB
#    part ordered is the LM4040-N.)
# MCP4922, Microchip DS21897B (2007), "3V AC/DC characteristics": VDD = 3 V, VREF = 2.048 V external,
# G = 1x, RL = 5k, CL = 100 pF, -40..85 C
MCP_VDD_RANGE = (2.7, 5.5)
MCP_INL_TYP, MCP_INL_MAX = 3.0, 12.0          # LSB (+-)
MCP_VOS_TYP, MCP_VOS_MAX = 0.0002, 0.01       # offset error at code 0x000, fraction of FSR: +-0.02 % typ, 1 % max
MCP_GE_TYP, MCP_GE_MAX = -0.0015, 0.01        # gain error at 0xFFF, fraction of FSR: -0.15 % typ, +-1 % max
MCP_VREF_BUF_MARGIN = 0.040                   # V, buffered VREF input range 0.040 .. VDD - 0.040
MCP_VOUT_LO, MCP_VOUT_HI_DROP = 0.010, 0.040  # V typ, output swing 0.010 .. VDD - 0.040
MCP_RVREF_UNBUF = 165e3                       # ohm typ, VREF input impedance, unbuffered (only typ given)
MCP_IVREF_BUF = 1e-6                          # A, buffered VREF input current: not given; assumption (generous)
# 74HC4051 (U1): TI CD74HC4051 SCHS122O (rev. Jan 2026): VCC 2..6 V; rON (VIS = VCC to VEE, IO = 1 mA) at
# VCC = 4.5 V: 90 typ, 180 max 25 C, 225 max -40..85 C; nothing below 4.5 V. onsemi MC74HC4051A Rev. 17
# (July 2026): rON max 190 / 240 ohm (25 / 85 C) at 4.5 V; VIH min 2.10 V at VCC 3.0, 3.15 at 4.5; VIL max
# 0.9 at 3.0, 1.35 at 4.5; on-channel leakage max 0.2 uA (25 C) / 2.0 uA (85 C) at 6 V.
HC_VCC_RANGE = (2.0, 6.0)
HC_VIH = ((3.0, 2.10), (4.5, 3.15))
HC_VIL = ((3.0, 0.90), (4.5, 1.35))
HC_RON_TYP_3V = 100.0       # ohm: onsemi Figure 1b (VCC - VEE = 3.0 V, 25 C) read approximately (curve)
HC_RON_WORST_3V3 = 1000.0   # ohm: no guaranteed figure below 4.5 V; assumption, 4x the 85 C maximum at 4.5 V
HC_ILKG_MAX = 2.0e-6        # A, onsemi, 85 C
# CD4051B, TI SCHS047O (rev. May 2026): supply 3 V to 20 V ("performance degrades for VDD < 3V"); rON
# (0 <= VIS <= VDD) at VDD = 5 V: 470 typ, 1050 max (25 C), 1200 (85 C); none at lower VDD. Control levels
# at VDD = 5 V: VIH min 3.5 V, VIL max 1.5 V (scaled as 0.7 / 0.3 VDD).
CD_VDD_MIN = 3.0
CD_RON_MAX_5V = 1050.0
CD_VIH_FRAC, CD_VIL_FRAC = 0.7, 0.3
# Alpha 9 mm B10k pots: the track only sets a ratio here (its +-20 % does not matter).
# 2N3904 (Q1, Q2): onsemi 2N3903/D Rev. 9 (Aug 2021), 25 C:
Q_HFE_MIN = ((0.1e-3, 40.0), (1e-3, 70.0), (10e-3, 100.0))   # (IC, hFE min) at VCE = 1 V
Q_HFE_MAX_10MA = 300.0      # max at 10 mA; no max given lower: used as the high bound
Q_HFE_TYP = 150.0           # assumption for "typical" (the datasheet gives min / max only)
Q_VCESAT_MAX = 0.2          # V, IC = 10 mA, IB = 1 mA
Q_VBESAT = (0.65, 0.85)     # V min / max, IC = 10 mA, IB = 1 mA
Q_VEBO = 6.0                # V, emitter-base breakdown min
Q_ICEX = 50e-9              # A max, collector cutoff
Q_VBE_SHIFT = 0.09          # V: VBE at 0.1-0.3 mA is about 1.5 decades below the 10 mA figure at 60 mV/decade:
#                             derived, gives VBE(on) 0.56..0.76 V at the operating point
# BAT85 (D22, D23): Vishay document 88146 (13-May-02), 25 C: VF max 0.24 V at 0.1 mA, 0.32 V at 1 mA,
# 0.40 V at 10 mA; IR max 2 uA at 25 V; IF max 200 mA; VR 30 V.
BAT_VF = ((0.1e-3, 0.24), (1e-3, 0.32), (10e-3, 0.40))
BAT_IR_MAX = 2e-6
BAT_IF_MAX, BAT_VR_MAX = 0.2, 30.0
# Faceplate gate LEDs D11-D13: "3 mm LED, green" from Thonk (bom.md) with no part number: VF at about
# 1.5 mA not confirmed; 1.8 V (low, a GaP green) .. 3.0 V (high, an InGaN green) assumed, 2.0 V typical.
LED_VF_LO, LED_VF_TYP, LED_VF_HI = 1.8, 2.0, 3.0
# STM32 pin clamp (ESD diode to VSS) under negative injection: not in DS12556; 0.3 V used for the largest
# current, 0.5 V as the typical drop.
CLAMP_VF_MIN, CLAMP_VF_TYP = 0.3, 0.5
# Loads: a Eurorack input is usually 100k; 10k is the worst case asked for.
R_EXT_TYP, R_EXT_WORST = 100e3, 10e3
# Criteria (first principles)
ADC_HEADROOM_MIN = 0.05     # V: the CV stage stays this far inside 0..VREF+ at +-5 V (the ADC's own offset
#                             and gain errors after calibration are about 1 mV)
POT_ERR_MAX = 1 / 256       # fraction of the span: Marbles reads its knobs no finer than 8 bits
CENT = 1 / 1200             # V per cent at 1 V/oct
TUNE_CENTS = 10.0           # a quantised pitch within 10 cents sounds in tune
WARMUP_K = 15.0             # K, a Eurorack case from cold to warm

DOC = " ".join(harness.text("docs", "design.md").split())
BOMDOC = " ".join(harness.text("docs", "bom.md").split())
FW = {name: harness.text("firmware", *path) for name, path in {
    "adc": ("src", "marbles", "drivers", "adc.cc"), "settings": ("src", "marbles", "settings.cc"),
    "cvr": ("vendor", "marbles", "cv_reader.h"), "dac_h": ("src", "marbles", "drivers", "dac.h"),
    "dac_cc": ("src", "marbles", "drivers", "dac.cc"), "cal": ("src", "output_calibrator.h"),
    "hal": ("src", "hal_daisy.cc"), "main": ("src", "marblesy.cc")}.items()}


def doc_num(pattern, text=DOC, n=1):
    """Numbers captured by a pattern in design.md (normalised whitespace), or None."""
    m = re.search(pattern, text)
    if not m:
        return None
    vals = tuple(float(g) for g in m.groups())
    return vals if n > 1 else vals[0]


def fw_float(name, src):
    """A float constant of the form `name = <number>f;` (or an expression of numbers) in a firmware file."""
    m = re.search(rf"\b{name}\s*=\s*([^;]+);", src)
    if not m:
        return None
    expr = re.sub(r"(\d)f\b", r"\1", m.group(1))
    if not re.fullmatch(r"[\d.eE+\-*/() ]+", expr):
        return None
    return float(eval(expr, {"__builtins__": {}}))


def corners(ranges):
    """{name: (lo, hi)} -> {name: array} over all 2^n corners."""
    names = list(ranges)
    grid = ((np.arange(2 ** len(names))[:, None] >> np.arange(len(names))) & 1).astype(bool)
    return {k: np.where(grid[:, i], ranges[k][1], ranges[k][0]) for i, k in enumerate(names)}


def interp_log(pts, x):
    xs, ys = zip(*pts)
    return float(np.interp(math.log10(x), [math.log10(v) for v in xs], ys))


V33_LO, V33_HI = S.V33_NOM * (1 - S.V33_TOL), S.V33_NOM * (1 + S.V33_TOL)
RAILS = {c: S.rails(c) for c in ("typ", "worst")}
for c, (vp, vn, ip, in_) in RAILS.items():
    print(f"      rails {c}: {vp:+.2f} / {vn:+.2f} V at {ip * 1e3:.0f} / {in_ * 1e3:.0f} mA")

# ============================================================================================ A. CV inputs
CHANNELS = [name for name, *_ in C.CV_CHANNELS]
CV = {}
for name, label, u, s in C.CV_CHANNELS:
    pins = section_pins(u, s)
    rin_ref, rin = one(f"CV_{name}", f"IN_{name}")
    rf_ref, rf = one(f"IN_{name}", f"OA_{name}")
    rs_ref, rs = one(f"OA_{name}", f"ADC_{name}")
    CV[name] = dict(u=(u, s), rin=rin_ref, rf=rf_ref, rs=rs_ref, Rin=rin, Rf=rf, Rs=rs,
                    model=Mna().add_netlist([f"IN_{name}", f"OA_{name}", "BIAS"], fixed=[f"CV_{name}", "3V3A"]))
    ck.check(f"A.topology.{name}", pins == {"out": f"OA_{name}", "m": f"IN_{name}", "p": "BIAS"},
             f"expected {u}.{s} out OA_{name}, - IN_{name}, + BIAS; got {pins}")
r45, R45 = one("3V3A", "BIAS")
r46, R46 = one("BIAS", "GND")


def cv_adc(name, vin, v33=S.V33_NOM, rmul=None, vos=0.0, B=None):
    """V at the ADC pin (no load on the 1k) for a CV vin, batched."""
    c = CV[name]
    B = B or np.broadcast(np.asarray(vin), np.asarray(v33), np.asarray(vos),
                          *[np.asarray(v) for v in (rmul or {}).values()]).size
    V, _ = c["model"].dc({f"CV_{name}": vin, "3V3A": v33}, rmul=rmul, vos={c["u"]: vos}, B=B)
    return V[f"OA_{name}"], V["BIAS"]


doc_lin = doc_num(r"V_adc = ([\d.]+) V − ([\d.]+)·V_in", n=2)
doc_rng = doc_num(r"±5 V lands on ([\d.]+)–([\d.]+) V", n=2)
doc_bias = doc_num(r"BIAS is 3V3A × 10k/\d+k = ([\d.]+) V")
ck.check("A.doc_figures_found", None not in (doc_lin, doc_rng, doc_bias),
         f"design.md's transfer {doc_lin}, range {doc_rng}, BIAS {doc_bias}")
doc_lin, doc_rng, doc_bias = doc_lin or (1.776, 0.13), doc_rng or (1.13, 2.43), doc_bias or 1.57
for name in CHANNELS:
    v, b = cv_adc(name, np.array([0.0, 1.0, 5.0, -5.0]))
    ck.close(f"A.bias_doc.{name}", b[0], doc_bias, 0.005, " V")
    ck.close(f"A.zero_doc.{name}", v[0], doc_lin[0], 0.002, " V")
    ck.close(f"A.slope_doc.{name}", v[1] - v[0], -doc_lin[1], 0.001, " V/V")
    ck.check(f"A.range_doc.{name}", abs(v[2] - doc_rng[0]) < 0.005 and abs(v[3] - doc_rng[1]) < 0.005,
             f"design.md +5 V -> {doc_rng[0]} V, -5 V -> {doc_rng[1]} V; got {v[2]:.3f} / {v[3]:.3f} V")

# worst case: 1 % on Rin, Rf, R45, R46; 3V3A (= VREF+) +-3 %; TL074 offset 0..70 C; bias current x Rf
WC = {}
for name in CHANNELS:
    c = CV[name]
    k = corners({c["rin"]: (1 - R_TOL, 1 + R_TOL), c["rf"]: (1 - R_TOL, 1 + R_TOL), r45: (1 - R_TOL, 1 + R_TOL),
                 r46: (1 - R_TOL, 1 + R_TOL), "v33": (V33_LO, V33_HI),
                 "vos": (-S.TL_VOS_MAX_FULL - S.TL_IB_MAX_FULL * c["Rf"], S.TL_VOS_MAX_FULL + S.TL_IB_MAX_FULL * c["Rf"])})
    rm = {t: k[t] for t in (c["rin"], c["rf"], r45, r46)}
    out = {}
    for vin in (-12.0, -10.0, -5.0, 0.0, 1.0, 3.0, 5.0, 10.0, 12.0):
        out[vin] = cv_adc(name, np.full(k["v33"].shape, vin), k["v33"], rm, k["vos"])[0]
    WC[name] = (k, out)
    lo_head = float(np.min(out[5.0]))
    hi_head = float(np.min(k["v33"] - out[-5.0]))
    ck.check(f"A.worst_inside_adc.{name}", lo_head >= ADC_HEADROOM_MIN and hi_head >= ADC_HEADROOM_MIN,
             f"expected +-5 V to stay >= {ADC_HEADROOM_MIN * 1e3:.0f} mV inside 0..VREF+; worst +5 V -> "
             f"{lo_head * 1e3:.0f} mV above 0, worst -5 V -> {hi_head * 1e3:.0f} mV below VREF+")

# the firmware's view of its own stage
kRin, kRf = fw_float("kRin", FW["adc"]), fw_float("kRf", FW["adc"])
kBias, kRef = fw_float("kBiasRatio", FW["adc"]), fw_float("kAdcReference", FW["adc"])
ck.check("A.fw_constants_parsed", None not in (kRin, kRf, kBias, kRef), f"adc.cc kRin {kRin}, kRf {kRf}, "
         f"kBiasRatio {kBias}, kAdcReference {kRef}")
kRin, kRf, kBias, kRef = kRin or 1e5, kRf or 13e3, kBias or 10 / 21, kRef or 3.3
for name in CHANNELS:
    c = CV[name]
    ck.check(f"A.fw_stage_matches_circuit.{name}",
             abs(kRin - c["Rin"]) < 1 and abs(kRf - c["Rf"]) < 1 and abs(kBias - R46 / (R45 + R46)) < 1e-6,
             f"adc.cc Rin {kRin:.0f} Rf {kRf:.0f} bias {kBias:.4f}; circuit.py {c['rin']} {c['Rin']:.0f}, "
             f"{c['rf']} {c['Rf']:.0f}, {r46}/({r45}+{r46}) {R46 / (R45 + R46):.4f}")
kZero = kBias * (1 + kRf / kRin)
kVPFS = kRef * kRin / kRf


def marbles_reading(vadc, v33):
    """What Marbles' code sees (0.5 - V/10), from Adc::JackVoltage / MarblesReading (clipped to 0..1)."""
    vest = (kZero - vadc / v33) * kVPFS
    return np.clip(0.5 - vest / 10.0, 0.0, 65535 / 65536), vest


fix = doc_num(r"fabsf\(destination / expected_value - 1\.0f\) > ([\d.]+)f", " ".join(FW["settings"].split()))
dwin = doc_num(r"delta > ([-\d.]+)f && delta < ([-\d.]+)f", " ".join(FW["cvr"].split()), n=2)
ck.check("A.fw_calibration_windows_parsed", fix is not None and dwin is not None,
         f"settings.cc FIX_OUTLIER window {fix}, cv_reader.h scale window {dwin}")
fix, dwin = fix or 0.1, dwin or (-0.3, -0.1)
for name in CHANNELS:
    k, out = WC[name]
    c0, o_est = marbles_reading(out[0.0], k["v33"])
    c1, _ = marbles_reading(out[1.0], k["v33"])
    c3, _ = marbles_reading(out[3.0], k["v33"])
    if name in ("T_RATE", "X_SPREAD"):
        delta = c3 - c1
        ts, to, es, eo = (24.0, 12.0, -120.0, 60.0) if name == "T_RATE" else (0.4, 0.2, -2.0, 1.0)
        scale = ts / delta
        offset = to - scale * c1
        ck.check(f"A.cal_scale_window.{name}", bool(np.all((delta > dwin[0]) & (delta < dwin[1]))),
                 f"expected c(3 V) - c(1 V) in ({dwin[0]}, {dwin[1]}) at every corner; got {delta.min():.4f} .. "
                 f"{delta.max():.4f} (nominal -0.2)")
        es_err = np.abs(scale / es - 1)
        eo_err = np.abs(offset / eo - 1)
        ck.check(f"A.cal_kept_after_reboot.{name}", bool(np.all(es_err <= fix) and np.all(eo_err <= fix)),
                 f"expected the calibrated scale and offset within +-{fix:.0%} of {es:g} / {eo:g} (FIX_OUTLIER); "
                 f"worst scale {es_err.max():.1%}, offset {eo_err.max():.1%} off")
    else:
        off = 2 * c0
        err = np.abs(off - 1.0)
        ck.check(f"A.cal_offset_kept.{name}", bool(np.all(err <= fix)),
                 f"expected the 0 V offset (2 x reading) within +-{fix:.0%} of 1.0; worst {err.max():.2%} "
                 f"({np.abs(o_est).max() * 1e3:.0f} mV at the jack; the window allows {fix * 5:.2f} V)")
g_err = []
for name in CHANNELS:
    k, out = WC[name]
    _, v1 = marbles_reading(out[1.0], k["v33"])
    _, v3 = marbles_reading(out[3.0], k["v33"])
    g_err.append(float(np.max(np.abs((v3 - v1) / 2 - 1))))
print(f"      CV scale error, uncalibrated (Marbles calibrates only RATE and SPREAD): up to {max(g_err):.1%}")

for case in ("typ", "worst"):
    vp, vn, *_ = RAILS[case]
    lo, hi = S.cm_range(case, vp, vn)
    b = np.array([R46 / (R45 * (1 + R_TOL) + R46 * (1 - R_TOL)) * V33_LO, R46 * (1 + R_TOL) / (R45 * (1 - R_TOL) + R46 * (1 + R_TOL)) * V33_HI])
    ck.check(f"A.tl074_common_mode.{case}", bool(lo < b.min() and b.max() < hi),
             f"expected BIAS {b.min():.2f}..{b.max():.2f} V inside the {'typ' if case == 'typ' else 'guaranteed'} "
             f"input range {lo:+.2f}..{hi:+.2f} V")
    worst_out = max(float(np.max(np.abs(WC[n][1][v]))) for n in CHANNELS for v in (-12.0, 12.0))
    sw_lo, sw_hi = S.swing(CV[CHANNELS[0]]["Rf"], case, vp, vn)
    ck.check(f"A.tl074_swing_linear_to_12V.{case}", -worst_out > sw_lo and worst_out < sw_hi,
             f"expected the stage outputs for +-12 V in ({worst_out:.2f} V at most) inside the swing "
             f"{sw_lo:+.2f}..{sw_hi:+.2f} V, so the over-range figures below are linear")

# ============================================================================================ B. over-range
# M1 (2026-11-13): design.md used to say "a +-12 V input pushes about 1.3 mA through the 1k into the Seed's
# protection diodes, which is within the STM32H7's limit" (checked here as B.doc_current_+12V); with the 13k stages it
# gives the +-12 V range and the worst-case margin under the analog-mode limit instead
doc_12 = doc_num(r"±12 V lands on ([\d.]+)–([\d.]+) V", n=2)
doc_margin = doc_num(r"−12 V stays ([\d.]+) V under that limit")
ck.check("B.doc_figure_found", None not in (doc_12, doc_margin),
         f"design.md's +-12 V range {doc_12} and worst-case margin at -12 V {doc_margin}")
doc_12, doc_margin = doc_12 or (0.22, 3.34), doc_margin or 0.15
inj_sum = 0.0
claim_bad = []
margin_12 = []
for name in CHANNELS:
    k, out = WC[name]
    nm, port, ptype = seed_pin_of(f"ADC_{name}")
    rs_min = CV[name]["Rs"] * (1 - R_TOL)
    tt = ptype.startswith("TT")
    vmax_stm = S.STM_VIN_TT_MAX if tt else V33_LO + S.STM_VIN_FT_ABOVE_VDD
    vmax = min(vmax_stm, S.SEED_GPIO_ABS[1])
    # verifier change: the stage is linear per corner, so the jack voltage at which a limit is first passed is
    # (limit - V(0 V)) / slope, the least negative over the corners
    slope = out[1.0] - out[0.0]
    x_abs = float(np.max((vmax - out[0.0]) / slope))
    lim_an = k["v33"] + S.STM_VIN_ANALOG_ABOVE_VDDA
    x_an = float(np.max((lim_an - out[0.0]) / slope))
    for vin in (-10.0, -12.0):
        vpin = float(np.max(out[vin]))
        ok = vpin <= vmax
        an_over = float(np.max(out[vin] - lim_an))
        if vin == -12.0:
            margin_12.append(-an_over)
        if (not ok or an_over > 0) and vin == -12.0:
            claim_bad.append(f"{name} {vpin:.2f} V")
        ck.check(f"B.vin_max.{name}.{vin:+.0f}V", ok,
                 f"{nm} = {port} ({ptype}{', 3.3 V tolerant on the Seed' if port in S.SEED_TT_PINS else ''}): "
                 f"no clamp to VDD ('positive injection is not possible'), so the pin follows the stage to "
                 f"{vpin:.2f} V; limit {vmax:.2f} V ({'TT_xx 4.0 V' if tt else 'FT VDD + 4 V, the Seed 5 V'}), "
                 f"passed from {x_abs:.1f} V at the jack")
        # verifier change: new check. With its ADC input active the pin (FT_a / FT_ha / TT_a) is no longer 5 V
        # tolerant: min(VDDA, VREF+) + 0.3 V (AN4899 Rev 3 5.2.1 / 5.2.2), above which it injects into VDDA / VREF+
        ck.check(f"B.vin_analog_mode.{name}.{vin:+.0f}V", an_over <= 0,
                 f"{nm} = {port} ({ptype}) is an active ADC input: limit 3V3A + 0.3 V = {float(lim_an.min()):.2f}.."
                 f"{float(lim_an.max()):.2f} V (AN4899); the stage reaches {vpin:.2f} V, {an_over * 1e3:+.0f} mV over at "
                 f"its worst corner; passed from {x_an:.1f} V at the jack (nominal stage: "
                 f"{(S.V33_NOM + S.STM_VIN_ANALOG_ABOVE_VDDA - doc_lin[0]) / -doc_lin[1]:.1f} V)")
    for vin in (10.0, 12.0):
        voa = float(np.min(out[vin]))
        i = max(-voa - CLAMP_VF_MIN, 0.0) / rs_min
        if vin == 12.0:
            inj_sum += i
            ck.check(f"B.iinj_abs_max.{name}.+12V", i <= -S.STM_IINJ_PIN[0],
                     f"expected <= {-S.STM_IINJ_PIN[0] * 1e3:.0f} mA negative injection (Table 118); stage at "
                     f"{voa:.2f} V through {rs_min:.0f} ohm: {i * 1e3:.2f} mA")
        else:
            susc = 0.0 if port in S.STM_SUSC_NEG_0 else S.STM_SUSC_NEG_OTHER
            vstart = None
            v0, _ = cv_adc(name, np.array([0.0, 1.0]))
            vstart = (v0[0] + CLAMP_VF_TYP) / (v0[0] - v0[1])
            ck.check(f"B.no_negative_injection.{name}.+10V", i == 0.0,
                     f"DS12556: negative injection on an analog input degrades the other channels' conversions "
                     f"(Schottky to ground recommended); {port} functional limit {susc * 1e3:.0f} mA (Table 154). "
                     f"Stage at {voa:.2f} V: {i * 1e3:.2f} mA; injection starts near +{vstart:.1f} V at the jack")
ck.check("B.iinj_total.+12V", inj_sum <= S.STM_IINJ_SUM,
         f"expected the sum over the 7 CV pins <= {S.STM_IINJ_SUM * 1e3:.0f} mA; got {inj_sum * 1e3:.1f} mA")
v12 = {n: cv_adc(n, np.array([12.0, -12.0]))[0] for n in CHANNELS}
ck.check("B.doc_range_12V", all(abs(v[0] - doc_12[0]) < 0.005 and abs(v[1] - doc_12[1]) < 0.005 for v in v12.values()),
         f"design.md: +-12 V lands on {doc_12[0]}..{doc_12[1]} V; nominal stages "
         f"{', '.join(f'{n} {v[0]:.3f}/{v[1]:.3f}' for n, v in v12.items())} V")
ck.close("B.doc_margin_-12V", min(margin_12), doc_margin, 0.02, " V")
ck.check("B.doc_claim_within_limit", not claim_bad,
         "design.md: '+-12 V lands on ... -12 V stays under that limit' (3V3A + 0.3 V for an active ADC input). "
         "DS12556 allows +0 mA positive injection on every FT/TT pin, 4.0 V on TT_a pins, and an active ADC input "
         "(FT_a or TT_a) only 3V3A + 0.3 V (AN4899); the negative side is inside -5 mA but against the ADC note "
         f"(B.no_negative_injection); at -12 V: {', '.join(claim_bad) or 'none over'}")
mux_nm, mux_port, mux_type = seed_pin_of("MUX_OUT")
ck.check("B.mux_out_in_range", node("3V3A_F") == "3V3A",
         f"MUX_OUT ({mux_nm} = {mux_port}, {mux_type}) only sees the pots' 0..3V3A_F, which is 3V3A through H3")

# ===================================================================================== C. pots and the mux
mux = part("U1", "face")
mn = {k: node(v) for k, v in mux.nets.items()}
ck.check("C.mux_supply_pins", mn.get("16") == "3V3A" and mn.get("7") == "GND" and mn.get("8") == "GND"
         and mn.get("6") == "GND" and mn.get("3") == "MUX_OUT",
         f"expected VCC 3V3A_F, VEE + GND + /E on GND_F, COM -> MUX_OUT; got 16 {mn.get('16')}, 7 {mn.get('7')}, "
         f"8 {mn.get('8')}, 6 {mn.get('6')}, 3 {mn.get('3')}")
pots_ok = []
for ref, label, wiper, mpin, ch in C.POTS:
    p = part(ref, "face")
    pn = nets_ = {k: node(v) for k, v in p.nets.items()}
    pots_ok.append((ref, pn["1"] == "GND" and pn["3"] == "3V3A" and mux.nets.get(mpin) == wiper))
ck.check("C.pots_across_3V3A_into_mux", all(o for _, o in pots_ok),
         f"expected every pot CCW on GND_F, CW on 3V3A_F, wiper on its 4051 input; bad: {[r for r, o in pots_ok if not o]}")
rpot = harness.ohms(part("RV1", "face").value)
ck.check("C.hc_supply_range", HC_VCC_RANGE[0] <= V33_LO and V33_HI <= HC_VCC_RANGE[1],
         f"74HC VCC {HC_VCC_RANGE[0]}..{HC_VCC_RANGE[1]} V; 3V3A_F {V33_LO:.2f}..{V33_HI:.2f} V")
# verifier change: was ck.check(..., True, ...), a check that could not fail; now it compares the nets: every
# pot's ends on the 4051's VEE (pin 7) and VCC (pin 16), so a wiper can never leave the switch's analog range
pot_ends = {(node(part(ref, "face").nets["1"]), node(part(ref, "face").nets["3"])) for ref, *_ in C.POTS}
ck.check("C.hc_analog_range", pot_ends == {(mn.get("7"), mn.get("16"))},
         f"pot ends (CCW, CW) {sorted(pot_ends)}; 4051 VEE / VCC ({mn.get('7')}, {mn.get('16')}): the wipers stay inside "
         f"VEE..VCC")
vih = float(np.interp(V33_HI, *zip(*HC_VIH)))
vil = float(np.interp(V33_LO, *zip(*HC_VIL)))
voh = V33_LO - S.STM_VOH_DROP_8MA
vol = S.STM_VOH_DROP_8MA
ck.check("C.hc_address_levels", voh >= vih and vol <= vil,
         f"74HC at VCC {V33_HI:.2f} V needs VIH {vih:.2f} V (onsemi, interpolated), at {V33_LO:.2f} V VIL {vil:.2f} V; "
         f"the Seed gives VOH >= {voh:.2f} V, VOL <= {vol:.2f} V (at 8 mA: conservative)")
for ron, tag in ((HC_RON_TYP_3V, "typ"), (HC_RON_WORST_3V3, "worst")):
    rsrc = rpot / 4 * (1.2 if tag == "worst" else 1.0) + ron
    ileak = (S.STM_ILKG + HC_ILKG_MAX) if tag == "worst" else (S.STM_ILKG + 0.2e-6) / 2
    err = ileak * rsrc / V33_LO
    ck.check(f"C.pot_loading_error.{tag}", err <= POT_ERR_MAX,
             f"source at mid travel {rsrc:.0f} ohm (pot / 4 + Ron {ron:.0f}), leakage {ileak * 1e6:.2f} uA: error "
             f"{err:.3%} of the span; expected <= {POT_ERR_MAX:.2%}")
i_pots = len(C.POTS) * V33_HI / (rpot * 0.8)
drop = i_pots * 0.2                    # H3 contact pair + ~100 mm of 0.6 mm track: about 0.2 ohm (estimate)
ck.check("C.pot_span_ratiometric", 1 - drop / V33_LO >= 0.995,
         f"pots and VREF+ both on 3V3A; {i_pots * 1e3:.1f} mA through H3 costs {drop * 1e3:.2f} mV: span "
         f"{1 - drop / V33_LO:.4%} of full scale")
cd_ok = "CD4051B also works" in BOMDOC
ck.check("C.cd4051b_supply_range", V33_LO >= CD_VDD_MIN,
         f"BOM {'says' if cd_ok else 'no longer says'} 'CD4051B also works'; CD4051B VDD >= {CD_VDD_MIN} V, "
         f"3V3A_F down to {V33_LO:.2f} V ({(V33_LO - CD_VDD_MIN) * 1e3:.0f} mV margin; 'performance degrades' below)")
ck.check("C.cd4051b_address_levels", voh >= CD_VIH_FRAC * V33_HI and vol <= CD_VIL_FRAC * V33_LO,
         f"needs VIH {CD_VIH_FRAC * V33_HI:.2f} V / VIL {CD_VIL_FRAC * V33_LO:.2f} V; GPIO {voh:.2f} / {vol:.2f} V")
# verifier change: was hard-wired False; it is a finding only while bom.md offers the CD4051B
ck.check("C.cd4051b_ron_specified_at_3V3", not cd_ok,
         f"bom.md {'says' if cd_ok else 'no longer says'} 'CD4051B also works'; "
         f"SCHS047O guarantees rON only at VDD >= 5 V ({CD_RON_MAX_5V:.0f} ohm max at 5 V, 25 C; it rises steeply "
         f"as VDD falls): at 3.3 V it is unspecified, so 'also works' is not backed by the datasheet "
         f"(test_analog_ac checks the ADC settling with an assumed figure)")

# ===================================================================================== D. the reference
r47, R47 = one("3V3A", "VREF")
r42, R42 = one("VREF", "IN_NEGREF")
r43, R43 = one("IN_NEGREF", "NEG_REF")
lm = part("D21")
ck.check("D.lm4040_pins", node(lm.nets.get("2")) == "VREF" and node(lm.nets.get("1")) == "GND"
         and node(lm.nets.get("3")) == "GND",
         f"expected TO-92 pin 2 (cathode) on VREF, pins 1 and 3 on GND; got {lm.nets}")
mcp_vref_pins = sum(1 for u in ("U7", "U8") for pin in ("11", "13") if part(u).nets.get(pin) == "VREF")
ck.check("D.dac_vref_inputs", mcp_vref_pins == 4, f"expected 4 MCP4922 VREF inputs on VREF; got {mcp_vref_pins}")
dac_buf = "kBuffered" in FW["dac_cc"] and "select | kBuffered" in FW["dac_cc"]
ck.check("D.fw_buffered_vref", dac_buf, "dac.cc sets the buffered VREF bit in every DAC word")
doc_ref = doc_num(r"([\d.]+) mA into the reference, ([\d.]+) mA left for the LM4040 after the −2\.5 V inverter's "
                  r"([\d.]+) mA \(its minimum is (\d+)–(\d+) µA\)", n=5)
ck.check("D.doc_figures_found", doc_ref is not None, f"design.md's reference figures: {doc_ref}")
doc_ref = doc_ref or (0.53, 0.28, 0.25, 60, 65)
i47 = (S.V33_NOM - LM_VR) / R47
i42 = LM_VR / R42
ck.close("D.doc_current_R47", i47 * 1e3, doc_ref[0], 0.01, " mA")
ck.close("D.doc_current_inverter", i42 * 1e3, doc_ref[2], 0.01, " mA")
ck.close("D.doc_current_lm4040", (i47 - i42 - 4 * MCP_IVREF_BUF) * 1e3, doc_ref[1], 0.01, " mA")
ck.check("D.doc_minimum_matches_datasheet", (doc_ref[3], doc_ref[4]) == (LM_IRMIN_25C * 1e6, LM_IRMIN_FULL * 1e6),
         f"design.md {doc_ref[3]:.0f}-{doc_ref[4]:.0f} uA; SNOS633N LM4040CIZ max {LM_IRMIN_25C * 1e6:.0f} (25 C) / "
         f"{LM_IRMIN_FULL * 1e6:.0f} uA (full range)")
vr_hi, vr_lo = LM_VR * (1 + LM_TOL_FULL_C), LM_VR * (1 - LM_TOL_FULL_C)
for mode, i_dac in (("buffered", 4 * MCP_IVREF_BUF), ("unbuffered (before the first write)", 4 * vr_hi / (MCP_RVREF_UNBUF * 0.7))):
    imin = (V33_LO - vr_hi) / (R47 * (1 + R_TOL)) - vr_hi / (R42 * (1 - R_TOL)) - i_dac
    ck.check(f"D.lm4040_min_current.{mode.split()[0]}", imin >= LM_IRMIN_FULL,
             f"3V3A {V33_LO:.2f} V, VR {vr_hi:.3f} V (C grade, -40..85 C), R47 +1 %, R42 -1 %, DAC VREF inputs "
             f"{i_dac * 1e6:.0f} uA ({mode}): {imin * 1e6:.0f} uA; expected >= {LM_IRMIN_FULL * 1e6:.0f} uA")
imax = (V33_HI - vr_lo) / (R47 * (1 - R_TOL))
ck.check("D.lm4040_max_current", imax <= LM_IR_MAX, f"no load at all: {imax * 1e3:.2f} mA <= {LM_IR_MAX * 1e3:.0f} mA")
dvr = LM_DVR_MAX * (V33_HI - V33_LO) / R47 / 1e-3
print(f"      VREF moves {dvr * 1e3:.2f} mV at most as 3V3A goes over its +-3 % (SNOS633N dVR/dIR)")
drift = LM_TC_MAX * WARMUP_K * 5.0
ck.check("D.drift_after_calibration", drift / CENT <= TUNE_CENTS,
         f"VREF at {LM_TC_MAX * 1e6:.0f} ppm/C (max, every grade) over a {WARMUP_K:.0f} K warm-up moves a 5 V "
         f"output by {drift * 1e3:.1f} mV = {drift / CENT:.1f} cents; expected <= {TUNE_CENTS:.0f}")
for g, t in LM_TOL.items():
    print(f"      LM4040 grade {g}: +-{t:.1%} at 25 C -> +-{t * 5.45 * 1e3:.0f} mV at -5.45 V before calibration")
ck.check("D.bom_grade", "LM4040CIZ-2.5" in BOMDOC, "bom.md orders the LM4040CIZ-2.5 (grade C, the one modelled)")
doc_pw = doc_num(r"reference \(([\d.]+) mA\)")
ck.check("D.doc_power_section_current", doc_pw is not None and abs(doc_pw - i47 * 1e3) <= 0.05,
         f"design.md Power: 'reference ({doc_pw} mA)'; R47 {R47:.0f} ohm feeds {i47 * 1e3:.2f} mA "
         f"(0.36 mA was R47 = 2.2k)")

# ============================================================================================ E. NEG_REF
ui = S.opamp_driving("NEG_REF")
pins = section_pins(*ui)
ck.check("E.topology", pins == {"out": "NEG_REF", "m": "IN_NEGREF", "p": "GND"}, f"{ui}: {pins}")
inv = Mna().add_netlist(["IN_NEGREF", "NEG_REF"], fixed=["VREF"])
V, _ = inv.dc({"VREF": LM_VR})
ck.close("E.nominal", float(V["NEG_REF"][0]), -2.5, 0.005, " V")
k = corners({r42: (1 - R_TOL, 1 + R_TOL), r43: (1 - R_TOL, 1 + R_TOL)})
V, _ = inv.dc({"VREF": LM_VR}, rmul=k, B=4)
e = float(np.max(np.abs(V["NEG_REF"] / -2.5 - 1)))
doc_neg = doc_num(r"R42/R43 \(±(\d+) % on the −2\.5 V\)")
ck.close("E.doc_tolerance", e * 100, doc_neg or 2.0, 0.05, " %")
vos_err = S.TL_VOS_MAX_FULL * (1 + R43 / R42)
print(f"      NEG_REF: +-{e:.2%} from R42/R43, +-{vos_err * 1e3:.0f} mV ({vos_err / 2.5:.1%}) more from U4D's offset")
loads = [one("NEG_REF", f"IN_{n}")[1] for n, *_ in C.DAC_OUTS]
i_out = 2.5 / R43 + sum(2.5 / r for r in loads)
for case in ("typ", "worst"):
    vp, vn, *_ = RAILS[case]
    lo, hi = S.swing(2.5 / i_out, case, vp, vn)
    ck.check(f"E.swing.{case}", lo < -2.5 * 1.03 - vos_err,
             f"NEG_REF drives {i_out * 1e3:.2f} mA (R43 + {len(loads)} x 47k): {2.5 / i_out / 1e3:.1f}k; swing down "
             f"to {lo:+.2f} V")

# ====================================================================================== F. DAC output stages
OUTS = [n for n, *_ in C.DAC_OUTS]
DACN = {}
for name, chip, ch, u, s in C.DAC_OUTS:
    pins = section_pins(u, s)
    DACN[name] = dict(u=(u, s), rdac=one(f"DAC_{name}", f"IN_{name}"), rref=one("NEG_REF", f"IN_{name}"),
                      rf=one(f"IN_{name}", f"OA_{name}"), rs=one(f"OA_{name}", name), chip=chip, ch=ch)
    pin = "14" if ch == "A" else "10"
    ck.check(f"F.topology.{name}", pins == {"out": f"OA_{name}", "m": f"IN_{name}", "p": "GND"}
             and part(chip).nets.get(pin) == f"DAC_{name}",
             f"{u}.{s}: {pins}; {chip} pin {pin} -> {part(chip).nets.get(pin)}")
nets_all = [x for n in OUTS for x in (f"IN_{n}", f"OA_{n}", n)] + ["IN_NEGREF", "NEG_REF"]
fixed_all = ["VREF"] + [f"DAC_{n}" for n in OUTS]
d0 = DACN[OUTS[0]]
kDr = {k: fw_float(k, FW["dac_h"]) for k in ("kDacReference", "kDacInputResistor", "kDacOffsetResistor",
                                              "kDacFeedbackResistor")}
ck.check("F.fw_constants_match_circuit",
         all(v is not None for v in kDr.values()) and all(
             abs(kDr["kDacInputResistor"] - DACN[n]["rdac"][1]) < 1 and abs(kDr["kDacOffsetResistor"] - DACN[n]["rref"][1]) < 1
             and abs(kDr["kDacFeedbackResistor"] - DACN[n]["rf"][1]) < 1 for n in OUTS)
         and abs((kDr["kDacReference"] or 0) - LM_VR) < 1e-6,
         f"dac.h {kDr}; circuit.py {[(DACN[n]['rdac'], DACN[n]['rref'], DACN[n]['rf']) for n in OUTS]}")
VDD_DAC = (V33_LO, V33_HI)


def dac_volts(code, vref, ge=0.0, vos_frac=0.0, vdd=S.V33_NOM, ideal=False):
    """MCP4922 output (G = 1, buffered VREF): offset + VREF code/4096 (1 + gain error), inside its swing
    (0.010 V .. VDD - 0.040 V typ) unless ideal (design.md's own figures use the ideal transfer)."""
    v = vos_frac * vref + vref * code / 4096.0 * (1 + ge)
    if ideal:
        return v
    return np.clip(v, MCP_VOUT_LO, np.asarray(vdd) - MCP_VOUT_HI_DROP)


def dac_model(load):
    m = Mna().add_netlist(nets_all, fixed=fixed_all)
    if load:
        for n in OUTS:
            m.r(n, "GND", load, f"load_{n}")
    return m


MODELS = {load: dac_model(load) for load in (None, R_EXT_TYP, R_EXT_WORST)}


def dac_out(load, codes, p, B):
    """Jack voltages {out: array} for codes {out: code}; p: parameter arrays (resistor multipliers by ref,
    'vref', 'ge_<out>', 'vos_<out>' (DAC offset, fraction of FSR), 'os_<out>' (TL074 offset), 'os_inv')."""
    vref = np.broadcast_to(np.asarray(p.get("vref", LM_VR), float), (B,))
    fixed = {"VREF": vref}
    for n in OUTS:
        fixed[f"DAC_{n}"] = dac_volts(codes[n], vref, p.get(f"ge_{n}", 0.0), p.get(f"vos_{n}", 0.0),
                                      p.get("vdd", S.V33_NOM), p.get("ideal", False))
    rm = {k: v for k, v in p.items() if k.startswith("R")}           # resistor multipliers by ref
    vos = {DACN[n]["u"]: p.get(f"os_{n}", 0.0) for n in OUTS}
    vos[ui] = p.get("os_inv", 0.0)
    V, I = MODELS[load].dc(fixed, rmul=rm, vos=vos, B=B)
    return {n: V[n] for n in OUTS}, {n: V[f"OA_{n}"] for n in OUTS}


doc_codes = doc_num(r"code 0 → \+([\d.]+) V, code 4095 → −([\d.]+) V", n=2)
ck.check("F.doc_figures_found", doc_codes is not None, f"design.md: {doc_codes}")
doc_codes = doc_codes or (5.32, 5.45)
IDEAL = {"ideal": True}
j0, _ = dac_out(None, {n: 0 for n in OUTS}, IDEAL, 1)
j1, _ = dac_out(None, {n: 4095 for n in OUTS}, IDEAL, 1)
for n in OUTS:
    ck.close(f"F.doc_code0.{n}", float(j0[n][0]), doc_codes[0], 0.006, " V")
    ck.close(f"F.doc_code4095.{n}", float(j1[n][0]), -doc_codes[1], 0.006, " V")
doc_lsb = doc_num(r"is ([\d.]+) mV per step, 1/(\d+) of a semitone", n=2)
lsb = (float(j0[OUTS[0]][0]) - float(j1[OUTS[0]][0])) / 4095
ck.check("F.doc_lsb", doc_lsb is not None and abs(lsb * 1e3 - doc_lsb[0]) < 0.05 and abs(1 / 12 / lsb - doc_lsb[1]) < 1.5,
         f"design.md {doc_lsb}; got {lsb * 1e3:.2f} mV = 1/{1 / 12 / lsb:.1f} semitone")

# design.md's own worst case and Monte Carlo: 1 % on every stage resistor and R42/R43, 0.5 % on the reference
doc_wc = doc_num(r"at its worst \(−([\d.]+) V\), and the 1k into a 100k input takes 1 % more \(−([\d.]+) V\)", n=2)
doc_p99 = doc_num(r"still reaches −([\d.]+) V in 99 % of modules")
ck.check("F.doc_mc_figures_found", doc_wc is not None and doc_p99 is not None, f"design.md: {doc_wc}, {doc_p99}")
doc_wc, doc_p99 = doc_wc or (5.11, 5.06), doc_p99 or 5.16
for load, want, tag in ((None, -doc_wc[0], "open"), (R_EXT_TYP, -doc_wc[1], "100k")):
    rng = {r42: (1 - R_TOL, 1 + R_TOL), r43: (1 - R_TOL, 1 + R_TOL), "vref": (LM_VR * 0.995, LM_VR * 1.005)}
    for x in ("rdac", "rref", "rf"):
        rng[d0[x][0]] = (1 - R_TOL, 1 + R_TOL)
    if load:
        rng[d0["rs"][0]] = (1 - R_TOL, 1 + R_TOL)
    kk = corners(rng)
    B = kk["vref"].size
    j, _ = dac_out(load, {n: 4095 for n in OUTS}, dict(kk, ideal=True), B)
    ck.close(f"F.doc_worst_negative_end.{tag}", float(np.max(j[OUTS[0]])), want, 0.02, " V")


def mc_params(B, rng, full):
    p = {}
    refs = {DACN[n][x][0] for n in OUTS for x in ("rdac", "rref", "rf", "rs")} | {r42, r43}
    for r in refs:
        p[r] = 1 + rng.uniform(-R_TOL, R_TOL, B)
    p["vref"] = LM_VR * (1 + rng.uniform(-LM_TOL["C"], LM_TOL["C"], B))
    if full:
        for n in OUTS:
            p[f"ge_{n}"] = np.clip(rng.normal(MCP_GE_TYP, (MCP_GE_MAX - abs(MCP_GE_TYP)) / 3, B), -MCP_GE_MAX, MCP_GE_MAX)
            p[f"vos_{n}"] = np.clip(np.abs(rng.normal(MCP_VOS_TYP, (MCP_VOS_MAX - MCP_VOS_TYP) / 3, B)), 0, MCP_VOS_MAX)
            p[f"os_{n}"] = np.clip(rng.normal(0, S.TL_VOS_MAX_25C / 3, B), -S.TL_VOS_MAX_25C, S.TL_VOS_MAX_25C)
        p["os_inv"] = np.clip(rng.normal(0, S.TL_VOS_MAX_25C / 3, B), -S.TL_VOS_MAX_25C, S.TL_VOS_MAX_25C)
    return p


NMC = 20000
for full in (False, True):
    rng = np.random.default_rng(20261102 + full)
    p = mc_params(NMC, rng, full)
    p["ideal"] = not full                     # design.md's run: ideal DAC; the full one: its 10 mV floor too
    hi, _ = dac_out(R_EXT_TYP, {n: 0 for n in OUTS}, p, NMC)
    lo, _ = dac_out(R_EXT_TYP, {n: 4095 for n in OUTS}, p, NMC)
    worst_neg = np.max(np.stack([lo[n] for n in OUTS]), axis=0)
    worst_pos = np.min(np.stack([hi[n] for n in OUTS]), axis=0)
    short = np.mean((worst_neg > -5.0) | (worst_pos < 5.0))
    p99 = float(np.percentile(worst_neg, 99))
    if not full:
        ck.check("F.doc_mc_none_short", short == 0.0,
                 f"design.md: 'no module had an output short of +-5 V into 100k'; {NMC} modules (its tolerances): "
                 f"{short:.2%} short")
        ck.close("F.doc_mc_p99", p99, -doc_p99, 0.02, " V")
    else:
        ck.check("F.mc_full_yield_100k", short <= 0.01,
                 f"with the MCP4922's offset / gain error (normal around typ, max at 3 sigma) and the TL074 offsets "
                 f"(sigma = 25 C max / 3): {short:.2%} of {NMC} modules have an output short of +-5 V into 100k; "
                 f"expected <= 1 %. Worst of four at 99 %: {p99:+.2f} V; +end 1 %: "
                 f"{float(np.percentile(worst_pos, 1)):+.2f} V")

# full worst case per output: every tolerance at its corner, TL074 offsets over 0-70 C
for name in OUTS:
    d = DACN[name]
    rng_ = {r42: (1 - R_TOL, 1 + R_TOL), r43: (1 - R_TOL, 1 + R_TOL), "vref": (LM_VR * (1 - LM_TOL_FULL_C), LM_VR * (1 + LM_TOL_FULL_C)),
            d["rdac"][0]: (1 - R_TOL, 1 + R_TOL), d["rref"][0]: (1 - R_TOL, 1 + R_TOL), d["rf"][0]: (1 - R_TOL, 1 + R_TOL),
            d["rs"][0]: (1 - R_TOL, 1 + R_TOL), f"ge_{name}": (-MCP_GE_MAX, MCP_GE_MAX),
            f"vos_{name}": (0.0, MCP_VOS_MAX), f"os_{name}": (-S.TL_VOS_MAX_FULL, S.TL_VOS_MAX_FULL),
            "os_inv": (-S.TL_VOS_MAX_FULL, S.TL_VOS_MAX_FULL)}
    kk = corners(rng_)
    B = kk["vref"].size
    for load, tag in ((R_EXT_TYP, "100k"), (R_EXT_WORST, "10k")):
        hi, oa_hi = dac_out(load, {n: 0 for n in OUTS}, kk, B)
        lo, oa_lo = dac_out(load, {n: 4095 for n in OUTS}, kk, B)
        vpos, vneg = float(np.min(hi[name])), float(np.max(lo[name]))
        nom_hi = float(dac_out(load, {n: 0 for n in OUTS}, {}, 1)[0][name][0])
        nom_lo = float(dac_out(load, {n: 4095 for n in OUTS}, {}, 1)[0][name][0])
        if tag == "100k":
            ck.check(f"F.worst_reaches_5V.{name}.{tag}", vpos >= 5.0 and vneg <= -5.0,
                     f"expected after calibration +-5 V inside codes 0..4095 at every corner; the stage reaches "
                     f"{vpos:+.2f} / {vneg:+.2f} V into {tag} (nominal {nom_hi:+.2f} / {nom_lo:+.2f})")
        else:
            # verifier change: the 10k variant was a check; no source claims +-5 V into 10k (design.md: 'into 100k';
            # output_calibrator.h fits the outputs for a 100k input), and behind the 1k even the nominal stage cannot
            # do it. Kept as information: what a 10k input gets.
            print(f"      (info) {name} into 10k: {vpos:+.2f} / {vneg:+.2f} V at the worst corner (nominal {nom_hi:+.2f} / "
                  f"{nom_lo:+.2f}); the 100k calibration reads {100 * (1 - 101e3 / 100e3 * 10e3 / 11e3):.1f} % narrow there")
        if tag == "10k":
            for case in ("typ", "worst"):
                vp, vn, *_ = RAILS[case]
                rl = 1 / (1 / (load + d["rs"][1]) + 1 / d["rf"][1])
                slo, shi = S.swing(rl, case, vp, vn)
                m = max(float(np.max(oa_hi[name])), -float(np.min(oa_lo[name])))
                ck.check(f"F.tl074_swing.{name}.{case}", m < min(shi, -slo),
                         f"stage output up to {m:.2f} V into {rl / 1e3:.1f}k; swing {slo:+.2f}..{shi:+.2f} V")

# the output calibrator: its +-10 % window and the codes it measures at
plaus = doc_num(r"fabsf\(scale / marbles::kDacScale - 1\.0f\) <= ([\d.]+)f", " ".join(FW["cal"].split()))
hc = re.search(r"kHighCode = (0x[0-9a-fA-F]+)", FW["cal"])
lc = re.search(r"kLowCode = (0x[0-9a-fA-F]+)", FW["cal"])
ck.check("F.fw_calibrator_parsed", plaus is not None and hc and lc, f"window {plaus}, codes {hc and hc.group(1)}, "
         f"{lc and lc.group(1)}")
plaus = plaus or 0.1
hc, lc = int(hc.group(1), 16) if hc else 0x1d90, int(lc.group(1), 16) if lc else 0xaf30
kScale = -65536 * kDr["kDacInputResistor"] / (kDr["kDacFeedbackResistor"] * kDr["kDacReference"])
kOffset = 65536 * kDr["kDacInputResistor"] / kDr["kDacOffsetResistor"]
for name in OUTS:
    d = DACN[name]
    rng_ = {r42: (1 - R_TOL, 1 + R_TOL), r43: (1 - R_TOL, 1 + R_TOL), "vref": (LM_VR * (1 - LM_TOL_FULL_C), LM_VR * (1 + LM_TOL_FULL_C)),
            d["rdac"][0]: (1 - R_TOL, 1 + R_TOL), d["rref"][0]: (1 - R_TOL, 1 + R_TOL), d["rf"][0]: (1 - R_TOL, 1 + R_TOL),
            d["rs"][0]: (1 - R_TOL, 1 + R_TOL), f"ge_{name}": (-MCP_GE_MAX, MCP_GE_MAX),
            f"vos_{name}": (0.0, MCP_VOS_MAX), f"os_{name}": (-S.TL_VOS_MAX_FULL, S.TL_VOS_MAX_FULL),
            "os_inv": (-S.TL_VOS_MAX_FULL, S.TL_VOS_MAX_FULL)}
    kk = corners(rng_)
    B = kk["vref"].size
    vh, _ = dac_out(R_EXT_TYP, {n: (hc + 8) >> 4 for n in OUTS}, kk, B)
    vl, _ = dac_out(R_EXT_TYP, {n: (lc + 8) >> 4 for n in OUTS}, kk, B)
    scale = (lc - hc) / (vl[name] - vh[name])
    offset = hc - scale * vh[name]
    es, eo = np.abs(scale / kScale - 1), np.abs(offset / kOffset - 1)
    ck.check(f"F.calibrator_accepts_spread.{name}", bool(np.all(es <= plaus) and np.all(eo <= plaus)),
             f"expected the fit within +-{plaus:.0%} of the nominal stage at every corner; worst scale {es.max():.1%}, "
             f"offset {eo.max():.1%} off")
    inside = bool(np.all((vh[name] < 5.0) & (vl[name] > -5.0)))
    ck.check(f"F.calibration_points_inside_spread_range.{name}", inside,
             f"X SPREAD reads +-5 V (MarblesReading clips there): points {vh[name].min():+.2f}..{vh[name].max():+.2f} / "
             f"{vl[name].min():+.2f}..{vl[name].max():+.2f} V")
bias_err = 0.4 * (V33_HI - S.V33_NOM) * 1e3 / 101e3       # kSpreadBias assumes 3.3 V
ck.check("F.calibrator_load_offset", abs(bias_err) * 1e3 <= 1.0,
         f"output_calibrator.h's 13.07 mV load offset takes the bias at 3.3 V; at 3V3A +3 % it is off by "
         f"{bias_err * 1e3:.2f} mV; expected <= 1 mV")
vref_max = LM_VR * (1 + LM_TOL_FULL_C)
ck.check("F.mcp_vref_input_range", MCP_VREF_BUF_MARGIN <= LM_VR * (1 - LM_TOL_FULL_C)
         and vref_max <= V33_LO - MCP_VREF_BUF_MARGIN,
         f"buffered VREF {MCP_VREF_BUF_MARGIN}..VDD - {MCP_VREF_BUF_MARGIN} = {V33_LO - MCP_VREF_BUF_MARGIN:.2f} V; "
         f"VREF up to {vref_max:.3f} V")
ck.check("F.mcp_output_range", vref_max * (1 + MCP_GE_MAX + MCP_VOS_MAX) <= V33_LO - MCP_VOUT_HI_DROP,
         f"code 4095 up to {vref_max * (1 + MCP_GE_MAX + MCP_VOS_MAX):.3f} V; output swing to "
         f"{V33_LO - MCP_VOUT_HI_DROP:.2f} V")
ck.check("F.mcp_supply_range", MCP_VDD_RANGE[0] <= V33_LO and V33_HI <= MCP_VDD_RANGE[1],
         f"VDD 3V3A {V33_LO:.2f}..{V33_HI:.2f} V in {MCP_VDD_RANGE}")
for tag, inl in (("typ", MCP_INL_TYP), ("max", MCP_INL_MAX)):
    err = inl * lsb
    ck.check(f"F.inl_in_tune.{tag}", err / CENT <= TUNE_CENTS,
             f"MCP4922 INL {inl:.0f} LSB ({tag}) x {lsb * 1e3:.2f} mV = {err * 1e3:.1f} mV = {err / CENT:.0f} cents "
             f"after calibration (a two-point fit cannot take INL out); expected <= {TUNE_CENTS:.0f} cents")

# ========================================================================================= G. gate outputs
doc_gate = doc_num(r"0 V / ([\d.]+) V from the 3\.3 V GPIO")
doc_led = doc_num(r"about ([\d.]+) mA, which costs ([\d.]+) V across the gate stage's 1 kΩ output resistor "
                  r"\(the gate stays above (\d+) V\)", n=3)
ck.check("G.doc_figures_found", doc_gate is not None and doc_led is not None, f"design.md: {doc_gate}, {doc_led}")
doc_gate, doc_led = doc_gate or 8.25, doc_led or (1.5, 1.5, 6.0)
GATES = {}
for name, u, s in C.GATES:
    pins = section_pins(u, s)
    rg = one("GND", f"IN_{name}")
    rfb = one(f"IN_{name}", f"OA_{name}")
    rs = one(f"OA_{name}", name)
    led = next(ref for ref, lab, net in C.GATE_LEDS if net == f"{name}_F")
    rl = one(name, f"LED_{led}")
    lp = part(led, "face")
    GATES[name] = dict(u=(u, s), rg=rg, rf=rfb, rs=rs, rl=rl, led=led)
    nm, port, ptype = seed_pin_of(f"GATE_{name}")
    ck.check(f"G.topology.{name}", pins == {"out": f"OA_{name}", "m": f"IN_{name}", "p": f"GATE_{name}"}
             and node(lp.nets["1"]) == f"LED_{led}" and node(lp.nets["2"]) == "GND",
             f"{u}.{s} {pins}; LED {led} {lp.nets}; GPIO {nm} = {port}")
g0 = GATES["T1"]
gain = 1 + g0["rf"][1] / g0["rg"][1]
ck.close("G.doc_high_level", gain * S.V33_NOM, doc_gate, 0.01, " V")


def gate_jack(name, voa, vf, rext, rmul=None, B=1):
    g = GATES[name]
    m = Mna().add_netlist([name], fixed=[f"OA_{name}", f"LED_{g['led']}"])
    m.r(name, "GND", rext, "ext")
    V, _ = m.dc({f"OA_{name}": voa, f"LED_{g['led']}": vf}, rmul=rmul, B=B)
    vj = V[name]
    rl = g["rl"][1] * (np.asarray((rmul or {}).get(g["rl"][0], 1.0)))
    iled = np.maximum((vj - vf) / rl, 0)
    # LED off: re-solve without it where it would conduct backwards
    if np.any(vj < vf):
        m2 = Mna()
        m2.r(f"OA_{name}", name, g["rs"][1], g["rs"][0])
        m2.r(name, "GND", rext, "ext")
        V2, _ = m2.dc({f"OA_{name}": voa}, rmul=rmul, B=B)
        vj = np.where(vj < vf, V2[name], vj)
    iout = (np.asarray(voa) - vj) / (g["rs"][1] * np.asarray((rmul or {}).get(g["rs"][0], 1.0)))
    return vj, iled, iout


vj, iled, iout = gate_jack("T1", gain * S.V33_NOM, LED_VF_TYP, R_EXT_TYP)
ck.close("G.doc_led_current", float(iled[0]) * 1e3, doc_led[0], 0.15, " mA")
ck.close("G.doc_drop_1k", float(iout[0]) * g0["rs"][1], doc_led[1], 0.15, " V")
for name in GATES:
    g = GATES[name]
    # verifier change: design.md's "stays above 6 V" is checked at its own load (a 100k input) with every other
    # tolerance at its worst ("worst100k"); the 10k load ("worst") is kept for the must-work check (a valid gate)
    for case in ("typ", "worst100k", "worst"):
        vp, vn, *_ = RAILS["typ" if case == "typ" else "worst"]
        if case == "typ":
            kk = {"v33": np.array([S.V33_NOM]), "vf": np.array([LED_VF_TYP]), "rext": np.array([R_EXT_TYP])}
            rm = {}
        else:
            rx = R_EXT_TYP if case == "worst100k" else R_EXT_WORST
            kk = corners({"v33": (V33_LO, V33_HI), "vf": (LED_VF_LO, LED_VF_HI), g["rg"][0]: (1 - R_TOL, 1 + R_TOL),
                          g["rf"][0]: (1 - R_TOL, 1 + R_TOL), g["rs"][0]: (1 - R_TOL, 1 + R_TOL),
                          g["rl"][0]: (1 - R_TOL, 1 + R_TOL), "rext": (rx, rx)})
            rm = {k2: kk[k2] for k2 in (g["rs"][0], g["rl"][0])}
        B = kk["v33"].size
        gn = 1 + g["rf"][1] * kk.get(g["rf"][0], 1.0) / (g["rg"][1] * kk.get(g["rg"][0], 1.0))
        voa_lin = gn * kk["v33"]                               # VOH = VDD at the pA the TL074 input takes
        vj, iled, iout = gate_jack(name, voa_lin, kk["vf"], kk["rext"][0], rm, B)
        rload = voa_lin / (iout + voa_lin / (g["rf"][1] + g["rg"][1]))
        lim = np.array([S.swing(float(r), case, vp, vn)[1] for r in rload])
        voa = np.minimum(voa_lin, lim)
        vj, iled, iout = gate_jack(name, voa, kk["vf"], kk["rext"][0], rm, B)
        clipped = bool(np.any(voa < voa_lin))
        if case == "typ":
            ck.check(f"G.doc_above_6V.typ.{name}", float(vj.min()) >= doc_led[2],
                     f"VOH 3.3 V, LED {LED_VF_TYP} V, 100k load: jack {float(vj.min()):.2f} V"
                     f"{' (clipped at the swing)' if clipped else ''}; design.md: above {doc_led[2]:.0f} V")
        elif case == "worst100k":
            ck.check(f"G.doc_above_6V.worst.{name}", float(vj.min()) >= doc_led[2],
                     f"3V3D -3 %, LED {LED_VF_LO} V, 1 % resistors, 100k load, rails {vp:.2f} V, TL074 VOM min: jack "
                     f"{float(vj.min()):.2f} V (stage clips at {float(lim.min()):.2f} V into "
                     f"{float(rload.min()) / 1e3:.1f}k); design.md: above {doc_led[2]:.0f} V")
        else:
            print(f"      gate {name} into 10k at the worst corner: {float(vj.min()):.2f} V")
            ck.check(f"G.high_is_a_gate.worst.{name}", float(vj.min()) >= 2.5,
                     f"expected a high >= 2.5 V (above any Eurorack gate threshold); got {float(vj.min()):.2f} V")
            dim = float(iled[kk["vf"] == LED_VF_HI].min()) if np.any(kk["vf"] == LED_VF_HI) else 0.0
            print(f"      gate {name}: LED current {float(iled.min()) * 1e3:.2f}..{float(iled.max()) * 1e3:.2f} mA "
                  f"(a 3.0 V LED: {dim * 1e3:.2f} mA)")
    low = gain * S.TL_VOS_MAX_FULL
    vj, iled, _ = gate_jack(name, np.array([low, -low]), LED_VF_LO, R_EXT_TYP, None, 2)
    ck.check(f"G.low_level.{name}", float(np.max(np.abs(vj))) <= 0.1 and float(np.max(iled)) == 0.0,
             f"GPIO low (VOL ~ 0 V at pA): stage offset x {gain:.1f} = +-{low * 1e3:.0f} mV, LED dark; expected |V| <= 0.1 V")
    gnet = f"GATE_{name}"
    path = [p.ref for p in S.MAIN if p.kind in ("R", "C") and gnet in p.nets.values()]
    ck.check(f"G.defined_while_gpio_hiz.{name}", bool(path),
             f"after reset every STM32 GPIO is analog / high-Z (DS12556 3.x), and the Daisy bootloader runs first (2 s "
             f"grace version): {gnet} has no resistor ({path or 'nothing but the TL074 input'}), so the stage "
             f"output can sit anywhere up to its positive swing until InitGpio()")
ck.check("G.fw_gates_low_at_init", re.search(r"gate_pins\[2\]\.Init\(.*?\);\s*.*?WriteGates\(0\)", FW["hal"], re.S) is not None,
         "hal_daisy.cc InitGpio() configures the gate pins as outputs and writes them low")

# ======================================================================================== H. clock inputs
doc_thr = doc_num(r"Threshold about ([\d.]+) V")
ck.check("H.doc_figure_found", doc_thr is not None, f"design.md: {doc_thr}")
doc_thr = doc_thr or 0.7
CLK = {}
for k_, name in enumerate(("T", "X")):
    rb = one(f"{name}_CLK_IN", f"B_{name}_CLK")
    rc = one("3V3D", f"{name}_CLK")
    q = next(p for p in S.MAIN if p.kind == "NPN" and p.nets.get("3") == f"{name}_CLK")
    d = next(p for p in S.MAIN if p.kind == "BAT85" and p.nets.get("1") == f"B_{name}_CLK")
    nm, port, ptype = seed_pin_of(f"{name}_CLK")
    CLK[name] = dict(rb=rb, rc=rc, q=q.ref, d=d.ref, pin=(nm, port, ptype))
    ck.check(f"H.topology.{name}", q.nets == {"1": "GND", "2": f"B_{name}_CLK", "3": f"{name}_CLK"}
             and d.nets == {"1": f"B_{name}_CLK", "2": "GND"},
             f"{q.ref} E/B/C {q.nets}; {d.ref} cathode on the base, anode on GND {d.nets}; read by {nm} = {port}")


def hfe_min(ic):
    return interp_log(Q_HFE_MIN, max(ic, Q_HFE_MIN[0][0]))


def threshold(name, which, case):
    """Jack voltage at which the collector crosses the GPIO's VIL (which = 'on') or VIH ('off')."""
    c = CLK[name]
    rb, rc = c["rb"][1], c["rc"][1]
    if case == "typ":
        vdd, vbe, hfe, leak, rbm, rcm = S.V33_NOM, Q_VBESAT[0] - Q_VBE_SHIFT + 0.03, Q_HFE_TYP, 0.0, 1, 1
    elif case == "hi":       # hardest to switch: everything against it
        vdd, vbe, leak, rbm, rcm = V33_HI, Q_VBESAT[1] - Q_VBE_SHIFT, BAT_IR_MAX, 1 + R_TOL, 1 - R_TOL
        hfe = None
    else:                    # easiest: the lowest jack voltage that could change the reading
        vdd, vbe, leak, rbm, rcm = V33_LO, Q_VBESAT[0] - Q_VBE_SHIFT, 0.0, 1 - R_TOL, 1 + R_TOL
        hfe = Q_HFE_MAX_10MA
    vth = (S.STM_VIL_FRAC if which == "on" else S.STM_VIH_FRAC) * vdd
    ic = (vdd - vth) / (rc * rcm)
    if hfe is None:
        hfe = hfe_min(ic)
    return vbe + (ic / hfe + leak) * rb * rbm, ic, hfe


for name in CLK:
    on_t, _, _ = threshold(name, "on", "typ")
    off_t, _, _ = threshold(name, "off", "typ")
    ck.close(f"H.doc_threshold.typ.{name}", (on_t + off_t) / 2, doc_thr, 0.15, " V")
    hi, ic_hi, hfe_hi = threshold(name, "on", "hi")
    lo, ic_lo, _ = threshold(name, "off", "lo")
    ck.check(f"H.threshold_worst_high.{name}", hi <= 2.5,
             f"worst case (hFE {hfe_hi:.0f} at {ic_hi * 1e3:.2f} mA, VBE {Q_VBESAT[1] - Q_VBE_SHIFT:.2f} V, BAT85 "
             f"{BAT_IR_MAX * 1e6:.0f} uA leakage, 3V3D +3 %): reads high from {hi:.2f} V; expected <= 2.5 V "
             f"(3.3 V-logic and 5 V clocks trigger)")
    ck.check(f"H.threshold_worst_low.{name}", lo >= 0.4,
             f"best case (hFE {Q_HFE_MAX_10MA:.0f}, VBE {Q_VBESAT[0] - Q_VBE_SHIFT:.2f} V): reading can change from "
             f"{lo:.2f} V; expected >= 0.4 V (a clock's low level and noise do not trigger)")
    c = CLK[name]
    rb, rc = c["rb"][1], c["rc"][1]
    for vin in (5.0, 12.0):
        ib = (vin - (Q_VBESAT[1] - Q_VBE_SHIFT)) / (rb * (1 + R_TOL)) - BAT_IR_MAX
        icsat = V33_HI / (rc * (1 - R_TOL))
        ck.check(f"H.saturates.{name}.+{vin:.0f}V", ib * hfe_min(icsat) >= 2 * icsat,
                 f"IB {ib * 1e6:.0f} uA x hFE {hfe_min(icsat):.0f} = {ib * hfe_min(icsat) * 1e3:.2f} mA against "
                 f"{icsat * 1e3:.2f} mA through {c['rc'][0]}; expected >= 2x (VCE(sat) <= {Q_VCESAT_MAX} V < VIL)")
    i_d = (12.0 - BAT_VF[0][1]) / (rb * (1 - R_TOL))
    vf = interp_log(BAT_VF, i_d)
    ck.check(f"H.minus12V.{name}", i_d <= BAT_IF_MAX and vf <= 0.5 * Q_VEBO,
             f"-12 V: {c['d']} carries {i_d * 1e3:.3f} mA (max {BAT_IF_MAX * 1e3:.0f}), holds the base at "
             f"-{vf:.2f} V against VEBO {Q_VEBO:.0f} V (without it the base would see -12 V)")
    ck.check(f"H.bat85_reverse.{name}", 12.0 * 0 + (Q_VBESAT[1]) <= BAT_VR_MAX,
             f"with the input high the BAT85 sees VBE ({Q_VBESAT[1]:.2f} V max) in reverse; VR {BAT_VR_MAX:.0f} V")
# the normalization probe: PROBE -> R9/R10 -> the jack's lug -> tip -> header -> R50/R52 -> base
for jack, name in (("J1", "T"), ("J12", "X")):
    j = next(x for x in C.JACKS if x[0] == jack)
    lug, tip = j[3], j[2]
    rp = one(lug, C.PROBE_NETS[lug])
    probe_mb = node(C.PROBE_NETS[lug])
    pnm, pport, ptype = seed_pin_of(probe_mb)
    ck.check(f"H.probe_path.{name}", node(tip) == f"{name}_CLK_IN" and probe_mb == "PROBE",
             f"{jack} lug {lug} -> {rp[0]} {rp[1]:.0f} -> {C.PROBE_NETS[lug]} = {probe_mb} ({pnm} = {pport}); "
             f"tip {tip} = {node(tip)}; a cable lifts the lug off the tip")
    c = CLK[name]
    rtot = (rp[1] + c["rb"][1]) * (1 + R_TOL)
    voh = V33_LO - S.STM_VOH_DROP_8MA * 30e-6 / S.STM_IIO_TEST     # at the ~30 uA it sources
    ib = (voh - (Q_VBESAT[1] - Q_VBE_SHIFT)) / rtot - BAT_IR_MAX
    icsat = V33_HI / (c["rc"][1] * (1 - R_TOL))
    ck.check(f"H.probe_saturates.{name}", ib * hfe_min(icsat) >= icsat,
             f"probe high (VOH {voh:.2f} V) through {rtot / 1e3:.0f}k: IB {ib * 1e6:.1f} uA x hFE min "
             f"{hfe_min(icsat):.0f} = {ib * hfe_min(icsat) * 1e3:.2f} mA >= {icsat * 1e3:.2f} mA needed: the pin "
             f"reads low as the firmware expects")
    vb = S.STM_VOH_DROP_8MA * 1e-6 / S.STM_IIO_TEST * c["rb"][1] / rtot
    ck.check(f"H.probe_low_off.{name}", vb < Q_VBESAT[0] - Q_VBE_SHIFT - 0.3,
             f"probe low: base at {vb * 1e3:.2f} mV; collector leakage {Q_ICEX * 1e9:.0f} nA x 10k = "
             f"{Q_ICEX * c['rc'][1] * 1e3:.1f} mV below 3V3D: reads high")
ck.check("H.fw_clock_pins_no_pull",
         re.search(r"clock_t_pin\.Init\(kClockT, GPIO::Mode::INPUT, GPIO::Pull::NOPULL\)", FW["hal"]) is not None
         and re.search(r"clock_x_pin\.Init\(kClockX, GPIO::Mode::INPUT, GPIO::Pull::NOPULL\)", FW["hal"]) is not None,
         "hal_daisy.cc reads D0 / D1 as inputs without the internal pull (the 10k pull-ups are on the board)")

# ============================================================================================ I. spare U6D
spare = [(p.ref, s) for p in S.MAIN if p.kind == "TL074" for s in C.SECTION
         if section_pins(p.ref, s)["out"].endswith("SPARE")]
for u, s in spare:
    pins = section_pins(u, s)
    others = [p.ref for p in S.MAIN if p.ref != u and pins["out"] in p.nets.values()]
    ck.check(f"I.spare_follower.{u}.{s}", pins["out"] == pins["m"] and pins["p"] == "GND" and not others,
             f"{u}.{s}: out = IN- ({pins['out']}), IN+ GND, nothing else on it ({others}); output = its offset, "
             f"+-{S.TL_VOS_MAX_FULL * 1e3:.0f} mV, no load")
ck.check("I.every_section_used", sum(1 for p in S.MAIN if p.kind == "TL074") * 4 ==
         len(CV) + 1 + len(DACN) + len(GATES) + len(spare),
         f"{len(CV)} CV + 1 inverter + {len(DACN)} DAC + {len(GATES)} gate + {len(spare)} spare sections")

ck.done()
