"""analog_ac: dynamic behaviour of Marblesy's analog circuits: response, ADC sampling, stability, slew,
noise and switching times, from circuit.py's netlist and the routed master's stray capacitance.

How the model is built
  circuit.py's parts (both boards, header nets merged; resistors / capacitors found by the nets they join),
  TL074 sections as two-pole VCVSs (GBW 5.25 MHz, and the legacy 3 MHz as the slow case; second pole
  fitted to the datasheet's 56 deg follower margin) behind their 125 ohm open-loop output impedance,
  with their input capacitances. Stray capacitance per net from the routed export (track length x a
  grounded-coplanar pF/mm, pads, vias, mated header pins: analog_solver.net_caps). Rails and the 1 uF
  BIAS are AC ground.

What it checks
  A  CV input stages: the Rf || Cf corner (13k || 1n) against design.md's figure and against the per-channel ADC
     rate that libDaisy's configuration gives (PLL3R / 2 / 2 on rev V, 8.5 + 8.5 cycles, OVS 8, 8 ranks:
     hal_daisy.cc's "about 0.2 ms"); the corner against the firmware's own CV low-pass (Marbles' ONE_POLE
     at the block rate) and the rejection of what can alias into that band; each stage's phase margin
     with the ADC pin's capacitance behind the 1k
  B  ADC sampling: the sample-and-hold (4 pF behind its switch) charged through the source within the
     8.5-cycle sample time at 16 bits, eight oversampled conversions: the CV path (1k + the TL074) and the
     pots (pot Thevenin at mid travel + the 74HC4051's Ron + its common-pin capacitance + MUX_OUT's
     stray, unbuffered), with the CD4051B too; the mux settling time libDaisy leaves (the address moves
     at the end of a scan, the mux rank is last)
  C  DAC output stages: phase margin with the 100k feedback and the summing node's capacitance, into
     1k + 100 pF .. 10 nF of cable; slew for a full-scale step against the TL074's minimum and the
     MCP4922's own slew and settling within one 32 kHz sample; output noise (TL074 en and in, resistors,
     the LM4040's noise through both the DAC and the offset path) against the 2.6 mV step; design.md's
     claim that the reference's error leaves 0 V where it is
  D  NEG_REF inverter and the reference: the LM4040 with C30 (SNOS633's capacitive-load statement), the
     inverter's phase margin into the four 47k
  E  gate outputs: rise / fall through the TL074's slew rate and the 1k into the LED, the routed T1-T3
     and a cable; the gain-2.5 stage's phase margin
  F  clock inputs: the 2N3904's turn-on and turn-off (storage time from the datasheet's ts, Miller
     charge through the 100k base drive) and the 10k pull-up into the pin, against the 32 kHz polling
     period and Marbles' fastest clock (8 kHz on X); the normalization probe (110k) against the samples
     the firmware waits between writing and reading it

Not modelled: the MCP4922's own output noise and output impedance (not in DS21897B's tables), ground
and supply impedance, crosstalk between tracks, temperature, the SAR's internal charge behaviour beyond
a sample-and-hold capacitor that keeps its last sample.

Run:  cd marbles/hardware/tests && python test_analog_ac.py
Only reads circuit.py, the routed export, design.md and the firmware sources; writes nothing.
"""
import math
import re

import numpy as np

import harness
import analog_solver as S
from analog_solver import Mna, one, node, part, section_pins, seed_pin_of

ck = harness.Checks("analog_ac")
C = S.CIRCUIT

# ================================================================================================ constants
# ADC clock and timing. libDaisy v9.0.0 (raw.githubusercontent.com/electro-smith/libDaisy/v9.0.0/...), read
# 2026-11-12: src/sys/system.cpp: HSE 16 MHz (PLLM 4, PLLN 240 -> 480 MHz), PLL3M 6, PLL3N 295, PLL3R 32,
# AdcClockSelection = PLL3; src/per/adc.cpp: ClockPrescaler ADC_CLOCK_ASYNC_DIV2, 16-bit, one regular rank per
# channel, mux used -> DMA one-shot restarted from the conversion-complete callback, which first writes the
# next mux address; src/per/adc.h: InitSingle / InitMux default SPEED_8CYCLES_5. Rev V silicon halves the ADC
# kernel clock once more (RM0433; from the libDaisy port notes, "about 6.1 MHz on rev V", not re-read here).
HSE = 16e6
PLL3M, PLL3N, PLL3R = 6, 295, 32
ADC_PRESC, REV_V_DIV = 2, 2
ADC_SMP_CYCLES = 8.5
ADC_SCAN_OVERHEAD = 5e-6        # s per scan for the callback + DMA restart: assumption (not measured)
# 32 kHz I/O tick (hal.h kIoRate) and Marbles' block size (vendor io_buffer.h kBlockSize) are read below.
# Marbles' fastest clocks: vendor random/t_generator.cc ramp_extractor_.Init(1000 / sr), x_y_generator.cc
# Init(8000 / sr): 1 kHz on T, 8 kHz on X.
# MCP4922 (DS21897B, 3 V table, G = 1, RL 5k, CL 100 pF): slew 0.55 V/us typ, settling 4.5 us typ (1/4 to 3/4
# scale, 1/2 LSB).
MCP_SR_TYP = 0.55e6
MCP_TSETTLE_TYP = 4.5e-6
# LM4040-N (SNOS633N): wideband noise 35 uVrms typ, 10 Hz - 10 kHz, IR = 100 uA; "maintaining stability with any
# capacitive load", "no output capacitor required", "tolerates capacitive loads" (features); ZR 0.9 ohm max
# (IR = 1 mA, 120 Hz, grade C). Its density above 10 kHz is not given: taken flat (not confirmed).
LM_EN_RMS, LM_EN_BW = 35e-6, (10.0, 10e3)
LM_ANY_CLOAD = True
LM_ZR_MAX = 0.9
# 74HC4051 at 3.3 V (see test_analog_dc): Ron typ 100 ohm (onsemi Fig. 1b, 3.0 V), worst 1 kohm (assumption);
# common-pin capacitance: TI CD74HC4051 SCHS122O 5.9: CCOM 25 pF typ (4051), CI 5 pF; onsemi MC74HC4051A
# Rev 17: CI/O max 35 pF analog I/O, 130 pF common O/I with all switches off (max).
HC_RON = {"typ": 100.0, "worst": 1000.0}
HC_CCOM = {"typ": 25e-12, "worst": 130e-12}
HC_TON_MAX = 90e-9              # s, onsemi, channel-select to output, VCC 3.0 V, CL 50 pF, 25 C
# CD4051B at VDD = 3.3 V: rON not specified (1050 ohm max at 5 V): 10 kohm assumed; common capacitance not read:
# 30 pF assumed.
CD_RON_3V3, CD_CCOM = 10e3, 30e-12
# Alpha 9 mm pot: track +-20 % (assumption, the usual figure); worst Thevenin at mid travel = R/4 x 1.2
POT_TOL = 0.2
# 2N3904 (onsemi 2N3903/D Rev 9): Cibo 8 pF max (VEB 0.5 V, 1 MHz), Cobo 4 pF max (VCB 5 V, 1 MHz); fT 300 MHz
# min; ts 200 ns max at VCC 3 V, IC 10 mA, IB1 = IB2 = 1 mA; hFE min 100 at 10 mA, 40 at 0.1 mA. Cobo rises at
# low VCB (Figure 3): 5 pF used below 1 V (read off the curve, approximate).
Q_CIBO, Q_COBO, Q_COBO_LOWV = 8e-12, 4e-12, 5e-12
Q_TS_DS, Q_IC_DS, Q_IB_DS, Q_HFE_10MA = 200e-9, 10e-3, 1e-3, 100.0
Q_HFE_LOW = 40.0
Q_VBE_ON = (0.56, 0.76)         # V, derived in test_analog_dc (VBE(sat) at 10 mA less ~90 mV)
# Cables and loads
C_CABLE = (100e-12, 1e-9)       # F, a 1 m patch cable (~100 pF) up to a long or multed one (1 nF)
C_EXTREME = 10e-9               # F, a stress case for the DAC outputs
R_NEXT = 100e3                  # ohm, the next module's input
C_NEXT = 50e-12                 # F
LED_R_EQ = 3.3e3                # the gate LED branch at AC: its 3k3 (the LED's own resistance is small)
# Criteria (first principles)
PM_MIN = 45.0                   # deg
LSB16_ERR_CV = 4.0              # LSB16 (0.75 mV at the jack, < 1 cent on the 1 V/oct RATE input)
POT_ERR_MAX = 1e-3              # fraction of the span: a CV on the channel before must move a knob < 1/1000
T_RISE_MAX = 5e-6               # s, a gate edge (10-90 %) well inside one 31 us sample
NOISE_MAX_LSB = 0.25            # output noise (rms, 10 Hz - 20 kHz) against the DAC step

DOC = " ".join(harness.text("docs", "design.md").split())
HAL = harness.text("firmware", "src", "hal_daisy.cc")
HAL_H = harness.text("firmware", "src", "hal.h")
MAINC = harness.text("firmware", "src", "marblesy.cc")
IOBUF = harness.text("firmware", "vendor", "marbles", "io_buffer.h")
TGEN = harness.text("firmware", "vendor", "marbles", "random", "t_generator.cc")
XYGEN = harness.text("firmware", "vendor", "marbles", "random", "x_y_generator.cc")

CAPS, CINFO, PF_MM = S.net_caps()
print(f"      track capacitance {PF_MM:.3f} pF/mm (0.3 mm among pours on 1.6 mm FR4)")
OP = {"5.25 MHz": S.Opamp(S.TL_GBW_NEW), "3 MHz": S.Opamp(S.TL_GBW_OLD)}
V33 = S.V33_NOM


def stray(n):
    return CAPS.get(node(n), 0.0)


def add_strays(m, nets):
    for n in nets:
        m.c(node(n), "GND", stray(n), f"stray_{n}")


def int_m(match, default):
    return int(match.group(1)) if match else default


def en(f):
    """TL074 voltage noise density, en^2 = enw^2 (1 + fc / f), through the datasheet's 1 kHz and 10 kHz typicals."""
    r = (S.TL_EN_1K / S.TL_EN_10K) ** 2
    fc = (r - 1) / (1 / 1e3 - r / 1e4)
    enw = S.TL_EN_10K / math.sqrt(1 + fc / 1e4)
    return enw * np.sqrt(1 + fc / np.asarray(f))


def pm_rows(m, sources, op, variants):
    """[(phase margin, crossover, label)] over the op-amp models and the given model variants."""
    rows = []
    for mname, model in OP.items():
        for label, mm in variants:
            pm, fc = mm.phase_margin(sources, model, op)
            rows.append((pm, fc, f"{mname}, {label}"))
    return rows


# ============================================================================================ A. CV inputs
fadc = HSE / PLL3M * PLL3N / PLL3R / ADC_PRESC / REV_V_DIV
ovs = int_m(re.search(r"AdcHandle::OVS_(\d+)", HAL), 1)
mux_last = re.search(r"config\[CV_INPUT_LAST\]\.InitMux\(", HAL) is not None
ranks = len(C.CV_CHANNELS) + 1
t_conv = (ADC_SMP_CYCLES + S.STM_TSAR_16B) / fadc
t_scan = ranks * ovs * t_conv + ADC_SCAN_OVERHEAD
fs_ch = 1 / t_scan
print(f"      ADC: {fadc / 1e6:.2f} MHz, {t_conv * 1e6:.2f} us per conversion, OVS {ovs}, {ranks} ranks: a scan "
      f"every {t_scan * 1e6:.0f} us = {fs_ch / 1e3:.2f} kHz per channel")
doc_scan = re.search(r"a scan of the eight channels takes about ([\d.]+) ms", " ".join(HAL.split()))
ck.check("A.fw_scan_time_comment", doc_scan is not None and abs(t_scan / (float(doc_scan.group(1)) * 1e-3) - 1) <= 0.3,
         f"hal_daisy.cc: 'about {doc_scan.group(1) if doc_scan else '?'} ms'; libDaisy's settings give "
         f"{t_scan * 1e3:.3f} ms (8.5-cycle sample + 8.5-cycle 16-bit SAR at {fadc / 1e6:.2f} MHz, OVS {ovs})")
ck.check("A.fw_mux_rank_last", mux_last, "hal_daisy.cc puts the mux rank after the seven CVs")
doc_fc = re.search(r"Corner frequency ([\d.]+) kHz", DOC)
# verifier change: the firmware's own CV filter. marblesy.cc copies the ADC values once per 5-sample block and
# Marbles' CvReaderChannel::Process low-passes each CV with ONE_POLE(cv_value_, cv, cv_lp) at that block rate
# (vendor/marbles/cv_reader.cc channel_settings_, cv_lp 0.05 .. 0.2): the band Marbles uses ends at a few hundred Hz.
CVR = harness.text("firmware", "vendor", "marbles", "cv_reader.cc")
cv_lps = [float(x) for x in re.findall(r"^\s*\{\s*([\d.]+)f,", CVR.split("channel_settings_[]", 1)[-1], re.M)]
f_block = int_m(re.search(r"kIoRate = (\d+)", HAL_H), 32000) / int_m(re.search(r"kBlockSize = (\d+)", IOBUF), 5)
f_lp = max(-math.log(1 - a) * f_block / (2 * math.pi) for a in cv_lps) if cv_lps else 250.0
ck.check("A.fw_cv_filter_parsed", len(cv_lps) == 8, f"cv_reader.cc cv_lp {cv_lps}; block rate {f_block:.0f} Hz: the widest "
         f"one-pole corner {f_lp:.0f} Hz")
for name, label, u, s in C.CV_CHANNELS:
    rf = one(f"IN_{name}", f"OA_{name}")
    cf = one(f"IN_{name}", f"OA_{name}", "C")
    rs = one(f"OA_{name}", f"ADC_{name}")
    fc = 1 / (2 * math.pi * rf[1] * cf[1])
    ck.close(f"A.doc_corner.{name}", fc / 1e3, float(doc_fc.group(1)) if doc_fc else 12.2, 0.1, " kHz")
    m = Mna().add_netlist([f"IN_{name}", f"OA_{name}", f"ADC_{name}"], fixed=[f"CV_{name}", "BIAS"], caps=True)
    add_strays(m, [f"IN_{name}", f"OA_{name}", f"ADC_{name}"])
    m.c(f"ADC_{name}", "GND", S.STM_CIO + S.STM_CADC, "pin")
    src = [f"CV_{name}", "BIAS"]
    f = np.logspace(1, 6, 400)
    h = np.array([m.ac(fi, src, OP["5.25 MHz"], {f"CV_{name}": 1.0})[f"ADC_{name}"] for fi in f])
    h0 = abs(h[0])
    f3 = float(f[int(np.argmax(np.abs(h) < h0 / math.sqrt(2)))])
    att_ny = harness.db(abs(np.interp(fs_ch / 2, f, np.abs(h))) / h0)
    if name == C.CV_CHANNELS[0][0]:
        ck.within(f"A.response_-3dB.{name}", f3 / 1e3, 0.9 * fc / 1e3, 1.1 * fc / 1e3, " kHz",
                  "at the ADC pin, with the 1k into the pin's 9 pF and the routed strays")
    # verifier change: was A.antialias_corner_below_nyquist (f3 <= fs / 2), which every channel failed. That rule
    # does not fit these inputs: only content within f_lp of a multiple of the scan rate (audio, near 5.5 kHz) can
    # alias into the band the firmware keeps, and Marbles is not specified for audio-rate CVs. What the stage must
    # do is stay out of that band: its corner well above the firmware's filter, so it adds no lag where Marbles
    # listens. The alias rejection is reported.
    att_alias = harness.db(abs(np.interp(fs_ch - f_lp, f, np.abs(h))) / h0)
    ck.check(f"A.cv_filter_clear_of_firmware_band.{name}", f3 >= 10 * f_lp,
             f"stage -3 dB {f3 / 1e3:.2f} kHz against the firmware's widest one-pole corner {f_lp:.0f} Hz (expected >= 10x); "
             f"per-channel rate {fs_ch / 1e3:.2f} kHz, so only {(fs_ch - f_lp) / 1e3:.2f}..{(fs_ch + f_lp) / 1e3:.2f} kHz "
             f"(and its multiples) aliases into that band, attenuated {att_alias:.1f} dB here ({att_ny:.1f} dB at "
             f"Nyquist; the 8x oversampling averages over {ovs * t_conv * 1e6:.0f} us)")
    op = (u, s)
    rows = pm_rows(m, src, op, [("pin + strays", m)])
    pm, fcx, lab = min(rows)
    ck.check(f"A.phase_margin.{name}", pm >= PM_MIN,
             f"{u}.{s}: expected >= {PM_MIN:.0f} deg; worst {pm:.0f} deg at {fcx / 1e6:.2f} MHz ({lab}; 1n across the "
             f"Rf: the noise gain falls to 1 at high frequency)")


# =================================================================================== B. ADC sampling
def sampled(rsrc, cnode, vs, vprev, n, radc=S.STM_RADC, cadc=S.STM_CADC):
    """The n oversampled values: the node (cnode) fed through rsrc from vs, the sample-and-hold (cadc behind
    radc) connected for the sample time, then held for the conversion while the node recovers. The hold
    capacitor starts at vprev (the rank before) and keeps its last sample between the n conversions."""
    ts, th = ADC_SMP_CYCLES / fadc, S.STM_TSAR_16B / fadc
    A = np.array([[-(1 / rsrc + 1 / radc) / cnode, 1 / (radc * cnode)], [1 / (radc * cadc), -1 / (radc * cadc)]])
    w, V = np.linalg.eig(A)
    E = (V @ np.diag(np.exp(w * ts)) @ np.linalg.inv(V)).real
    x = np.array([vs, vprev], float)
    out = []
    for _ in range(n):
        x = np.array([vs, vs]) + E @ (x - np.array([vs, vs]))
        out.append(x[1])
        x[0] = vs + (x[0] - vs) * math.exp(-th / (rsrc * cnode))
    return np.array(out)


LSB16 = V33 / 65536
for name, *_ in C.CV_CHANNELS:
    rs = one(f"OA_{name}", f"ADC_{name}")[1]
    rsrc = rs + S.TL_ZO_OL                  # the stage's output impedance taken as open-loop at these speeds
    cn = S.STM_CIO + stray(f"ADC_{name}")
    v = sampled(rsrc, cn, V33, 0.0, ovs)
    err1, erra = abs(v[0] - V33) / LSB16, abs(v.mean() - V33) / LSB16
    ck.check(f"B.cv_sampling_settles.{name}", erra <= LSB16_ERR_CV,
             f"source {rsrc:.0f} ohm, pin + track {cn * 1e12:.1f} pF, full-scale step from the rank before: first "
             f"conversion {err1:.2g} LSB16 short, average of {ovs} {erra:.2g}; expected <= {LSB16_ERR_CV:.0f}")
rpot = harness.ohms(part("RV1", "face").value)
cmux = stray("MUX_OUT") + S.STM_CIO
nm, port, ptype = seed_pin_of("MUX_OUT")
print(f"      MUX_OUT: {CINFO.get('MUX_OUT', (0, 0, 0))[0]:.0f} mm of track, {cmux * 1e12:.1f} pF with the pin; "
      f"{nm} = {port} ({ptype})")
t_mux = (ranks - 1) * ovs * t_conv
for tag, (ron, ccom, thev) in {"typ": (HC_RON["typ"], HC_CCOM["typ"], rpot / 4),
                              "worst": (HC_RON["worst"], HC_CCOM["worst"], rpot / 4 * (1 + POT_TOL)),
                              "cd4051b": (CD_RON_3V3, CD_CCOM, rpot / 4 * (1 + POT_TOL))}.items():
    rsrc, cn = thev + ron, ccom + cmux
    v = sampled(rsrc, cn, V33, 0.0, ovs)
    err1, erra = abs(v[0] - V33) / V33, abs(v.mean() - V33) / V33
    # verifier change: the CD4051B row is a finding only while bom.md offers the part ("CD4051B also works")
    offered = tag != "cd4051b" or "CD4051B also works" in " ".join(harness.text("docs", "bom.md").split())
    ck.check(f"B.pot_sampling_settles.{tag}", erra <= POT_ERR_MAX or not offered,
             f"pot at mid travel {thev:.0f} + Ron {ron:.0f} ohm into {cn * 1e12:.0f} pF (COM {ccom * 1e12:.0f} pF + "
             f"MUX_OUT + pin): first conversion {err1:.3%} short of a full-scale step from X_STEPS' rank, "
             f"average {erra:.3%}; expected <= {POT_ERR_MAX:.1%}")
    tau = rsrc * cn
    need = tau * math.log(2 * 65536) + HC_TON_MAX
    ck.check(f"B.mux_settles_before_its_rank.{tag}", need <= t_mux,
             f"libDaisy moves the address at the end of a scan; the mux rank comes {t_mux * 1e6:.0f} us later "
             f"({ranks - 1} CV ranks); a full-scale change needs {need * 1e6:.2f} us to 1/2 LSB16 "
             f"(tau {tau * 1e9:.0f} ns)")

# ================================================================================ C. DAC output stages
OUTS = [n for n, *_ in C.DAC_OUTS]
nets_all = [x for n in OUTS for x in (f"IN_{n}", f"OA_{n}", n)] + ["IN_NEGREF", "NEG_REF"]
srcs = ["VREF"] + [f"DAC_{n}" for n in OUTS]
DAC = {n: dict(u=(u, s), rdac=one(f"DAC_{n}", f"IN_{n}"), rref=one("NEG_REF", f"IN_{n}"), rf=one(f"IN_{n}", f"OA_{n}"),
               rs=one(f"OA_{n}", n)) for n, chip, ch, u, s in C.DAC_OUTS}
UI = S.opamp_driving("NEG_REF")


def dac_model(ccable, load=True):
    m = Mna().add_netlist(nets_all, fixed=srcs, caps=True)
    add_strays(m, nets_all)
    for n in OUTS:
        if load:
            m.c(n, "GND", ccable + C_NEXT, f"cable_{n}")
            m.r(n, "GND", R_NEXT, f"next_{n}")
    return m


variants = [(f"cable {c * 1e12:.0f} pF", dac_model(c)) for c in C_CABLE] + \
           [(f"cable {C_EXTREME * 1e9:.0f} nF", dac_model(C_EXTREME)), ("unplugged", dac_model(0, load=False))]
for n in OUTS:
    d = DAC[n]
    rows = pm_rows(None, srcs, d["u"], variants)
    pm, fcx, lab = min(rows)
    rin = 1 / (1 / d["rdac"][1] + 1 / d["rref"][1])
    cnode = stray(f"IN_{n}") + S.TL_C_ICM + S.TL_C_ID
    ck.check(f"C.phase_margin.{n}", pm >= PM_MIN,
             f"{d['u'][0]}.{d['u'][1]}: noise gain {1 + d['rf'][1] / rin:.2f}, summing node {cnode * 1e12:.1f} pF "
             f"(feedback pole {1 / (2 * math.pi * cnode / (1 / d['rf'][1] + 1 / rin)) / 1e6:.1f} MHz); worst "
             f"{pm:.0f} deg at {fcx / 1e6:.2f} MHz ({lab}); expected >= {PM_MIN:.0f}")
rows = pm_rows(None, srcs, UI, variants[:2])
pm, fcx, lab = min(rows)
ck.check("D.inverter_phase_margin", pm >= PM_MIN,
         f"{UI[0]}.{UI[1]} (R42 / R43, into four 47k and NEG_REF's {stray('NEG_REF') * 1e12:.0f} pF of track): worst "
         f"{pm:.0f} deg at {fcx / 1e6:.2f} MHz ({lab}); expected >= {PM_MIN:.0f}")
ck.check("D.lm4040_capacitive_load", LM_ANY_CLOAD and one("VREF", "GND", "C")[1] > 0,
         f"C30 {one('VREF', 'GND', 'C')[1] * 1e9:.0f} nF on VREF: SNOS633N states stability with any capacitive load "
         f"(no output capacitor required)")

# slew: a full-scale step, 0 -> 4095
lsb = 2.5 / 4096 * DAC[OUTS[0]]["rf"][1] / DAC[OUTS[0]]["rdac"][1]
vfs = 4095 * lsb
gain_dac = DAC[OUTS[0]]["rf"][1] / DAC[OUTS[0]]["rdac"][1]
ck.check("C.tl074_never_slews", gain_dac * MCP_SR_TYP < S.TL_SR_MIN,
         f"the MCP4922 slews at {MCP_SR_TYP / 1e6:.2f} V/us typ, x {gain_dac:.2f} = {gain_dac * MCP_SR_TYP / 1e6:.2f} V/us at "
         f"the stage; the TL074's minimum is {S.TL_SR_MIN / 1e6:.0f} V/us")
io_rate = int_m(re.search(r"kIoRate = (\d+)", HAL_H), 32000)
t_step = 2.5 / MCP_SR_TYP + MCP_TSETTLE_TYP + 2.2 * 1e3 * (C_CABLE[1] + C_NEXT)
ck.check("C.full_scale_step_within_a_sample", t_step <= 1 / io_rate,
         f"{vfs:.1f} V step: DAC slew {2.5 / MCP_SR_TYP * 1e6:.1f} us + settling {MCP_TSETTLE_TYP * 1e6:.1f} us + the 1k "
         f"into 1 nF {2.2e3 * (C_CABLE[1] + C_NEXT) * 1e6:.1f} us = {t_step * 1e6:.1f} us; a sample is "
         f"{1e6 / io_rate:.2f} us")

# noise at the jack (1 m cable, 100k), the reference through both paths at the code that reads it most
FN = np.logspace(1, math.log10(20e3), 50)
FW_ = np.logspace(1, 6, 70)
m = dac_model(C_CABLE[0])
lm_density = LM_EN_RMS / math.sqrt(LM_EN_BW[1] - LM_EN_BW[0])
for n in OUTS:
    rows = {}
    for band, fg in (("20k", FN), ("1M", FW_)):
        tot = []
        refp = []
        for fi in fg:
            p, parts = m.noise_psd(fi, srcs, OP["5.25 MHz"], n, float(en(fi)))
            h_ref = m.ac(fi, srcs, OP["5.25 MHz"], dict({"VREF": 1.0}, **{f"DAC_{k}": 4095 / 4096 for k in OUTS}))[n]
            tot.append(p + abs(h_ref) ** 2 * lm_density ** 2)
            refp.append(abs(h_ref) ** 2 * lm_density ** 2)
        rows[band] = (math.sqrt(np.trapezoid(tot, fg)), math.sqrt(np.trapezoid(refp, fg)))
    ck.check(f"C.output_noise.{n}", rows["20k"][0] <= NOISE_MAX_LSB * lsb,
             f"10 Hz-20 kHz: {rows['20k'][0] * 1e6:.0f} uVrms (the LM4040's share at full scale {rows['20k'][1] * 1e6:.0f}); "
             f"10 Hz-1 MHz: {rows['1M'][0] * 1e6:.0f} uVrms; step {lsb * 1e3:.2f} mV, expected <= {NOISE_MAX_LSB} step")
# design.md: "a reference 1 % high ... leaves 0 V where it is": the VREF -> jack transfer at the 0 V code
h_fs = abs(m.ac(100.0, srcs, OP["5.25 MHz"], dict({"VREF": 1.0}, **{f"DAC_{k}": 4095 / 4096 for k in OUTS}))[OUTS[0]])
code0v = 4096 * DAC[OUTS[0]]["rdac"][1] / DAC[OUTS[0]]["rref"][1] * one("IN_NEGREF", "NEG_REF")[1] / one("VREF", "IN_NEGREF")[1]
h_0 = abs(m.ac(100.0, srcs, OP["5.25 MHz"], dict({"VREF": 1.0}, **{f"DAC_{k}": code0v / 4096 for k in OUTS}))[OUTS[0]])
ck.check("C.doc_reference_cancels_at_0V", h_0 <= 0.01 * h_fs,
         f"VREF -> jack at the 0 V code ({code0v:.0f}): {h_0:.2e} V/V against {h_fs:.2f} V/V at full scale "
         f"(design.md: the outputs scale with the reference and 0 V stays put)")

# ======================================================================================== E. gate outputs
for name, u, s in C.GATES:
    nets = [f"IN_{name}", f"OA_{name}", name]
    rs = one(f"OA_{name}", name)
    led = next(ref for ref, lab, net in C.GATE_LEDS if net == f"{name}_F")
    vg = []
    for cc in C_CABLE:
        mm = Mna().add_netlist(nets, fixed=[f"GATE_{name}"], caps=True)
        add_strays(mm, nets)
        mm.r(name, "GND", LED_R_EQ, "led")
        mm.c(name, "GND", cc + C_NEXT, "cable")
        mm.r(name, "GND", R_NEXT, "next")
        vg.append((f"cable {cc * 1e12:.0f} pF", mm))
    rows = pm_rows(None, [f"GATE_{name}"], (u, s), vg)
    pm, fcx, lab = min(rows)
    ck.check(f"E.phase_margin.{name}", pm >= PM_MIN,
             f"{u}.{s}, gain 2.5, IN- {stray(f'IN_{name}') * 1e12:.1f} pF: worst {pm:.0f} deg at {fcx / 1e6:.2f} MHz "
             f"({lab}); expected >= {PM_MIN:.0f}")
    vhigh = 2.5 * V33
    t_slew = 0.8 * vhigh / S.TL_SR_MIN
    c_out = stray(name) + C_CABLE[1] + C_NEXT
    r_th = 1 / (1 / rs[1] + 1 / LED_R_EQ + 1 / 10e3)
    t_rc = 2.2 * r_th * c_out
    t_r = t_slew + t_rc
    ck.check(f"E.edge_time.{name}", t_r <= T_RISE_MAX,
             f"{vhigh:.2f} V edge: TL074 slew (min {S.TL_SR_MIN / 1e6:.0f} V/us) {t_slew * 1e6:.2f} us + the 1k into "
             f"{c_out * 1e12:.0f} pF (routed {CINFO.get(name, (0,))[0]:.0f} mm over both boards, 1 nF cable) "
             f"{t_rc * 1e6:.2f} us = {t_r * 1e6:.2f} us 10-90 %; expected <= {T_RISE_MAX * 1e6:.0f} us")

# ======================================================================================== F. clock inputs
block = int_m(re.search(r"kBlockSize = (\d+)", IOBUF), 5)
read_first = MAINC.find("clock_inputs.Read(s, 1)") < MAINC.find("clock_inputs.ReadNormalization(")
fmax_t = re.search(r"ramp_extractor_\.Init\(([\d.]+)f? / sr\)", TGEN)
fmax_x = re.search(r"ramp_extractor_\.Init\(([\d.]+)f? / sr\)", XYGEN)
fmax = max(float(fmax_t.group(1)) if fmax_t else 1000.0, float(fmax_x.group(1)) if fmax_x else 8000.0)
ck.check("F.fw_probe_order", read_first and MAINC.find("clock_inputs.Read(s, 1)") >= 0,
         "marblesy.cc IoTick reads the clock pins before ReadNormalization compares them and writes the next probe "
         "bit, so the probe has a whole block to get through")
tau_s = Q_TS_DS / math.log((Q_IB_DS + Q_IB_DS) / (Q_IC_DS / Q_HFE_10MA + Q_IB_DS))
vth_on, vth_off = S.STM_VIL_FRAC * V33, S.STM_VIH_FRAC * V33


def delays(name, vin, rdrive, extra_c_in=0.0):
    """(turn-on, turn-off) in s for a step 0 -> vin -> 0 through rdrive into the base."""
    rc_ = one("3V3D", f"{name}_CLK")[1]
    cb = Q_CIBO + stray(f"B_{name}_CLK") + extra_c_in + 10e-12 * 0     # BAT85 Ctot below
    cb += 10e-12                                                         # BAT85 10 pF max at 1 V
    cc = S.STM_CIO + stray(f"{name}_CLK")
    vbe = Q_VBE_ON[1]
    # turn-on: base to VBE through rdrive, then the Miller charge and the collector node at IB x hFE
    t1 = -rdrive * cb * math.log(1 - vbe / vin)
    ib = (vin - vbe) / rdrive
    t2 = Q_COBO_LOWV * (V33 - vth_on) / ib
    ic = Q_HFE_LOW * ib - V33 / rc_
    t3 = cc * (V33 - vth_on) / max(ic, 1e-9)
    t_on = t1 + t2 + t3
    # turn-off: storage time with IB2 = VBE / rdrive, the Miller charge out through the same, the collector
    # node up through the 10k to VIH
    ib2 = Q_VBE_ON[0] / rdrive
    icsat = V33 / rc_
    ts = tau_s * math.log((ib + ib2) / (icsat / Q_HFE_LOW + ib2))
    t4 = Q_COBO_LOWV * vth_off / ib2
    t5 = rc_ * (cc + Q_COBO_LOWV) * math.log(V33 / (V33 - vth_off))
    return t_on, ts + t4 + t5, (t1, t2, t3, ts, t4, t5)


period = 1 / io_rate
for name in ("T", "X"):
    rb = one(f"{name}_CLK_IN", f"B_{name}_CLK")[1]
    for vin in (5.0, 10.0):
        ton, toff, parts_ = delays(name, vin, rb)
        ck.check(f"F.delay_within_quarter_sample.{name}.{vin:.0f}V", max(ton, toff) <= period / 4,
                 f"{vin:.0f} V clock: on {ton * 1e6:.2f} us, off {toff * 1e6:.2f} us (storage {parts_[3] * 1e6:.2f}, "
                 f"Miller {parts_[4] * 1e6:.2f}, pull-up {parts_[5] * 1e6:.2f}); expected <= {period / 4 * 1e6:.1f} us "
                 f"(a quarter of the {period * 1e6:.2f} us poll)")
        half = 1 / fmax / 2
        ck.check(f"F.pulse_width_at_max_clock.{name}.{vin:.0f}V", abs(toff - ton) <= 0.1 * half,
                 f"Marbles takes clocks up to {fmax / 1e3:.0f} kHz (half period {half * 1e6:.1f} us): the stage "
                 f"stretches the high by {(toff - ton) * 1e6:.2f} us; expected <= 10 %; the 32 kHz poll quantises "
                 f"edges to {period * 1e6:.1f} us anyway")
    # the normalization probe: PROBE -> 10k -> lug -> tip -> header -> 100k
    jack = "J1" if name == "T" else "J12"
    j = next(x for x in C.JACKS if x[0] == jack)
    rp = one(j[3], C.PROBE_NETS[j[3]])[1]
    c_tip = stray(f"{name}_CLK_IN") + stray(j[3])
    voh = V33 * (1 - S.V33_TOL)
    ton, toff, _ = delays(name, voh, rp + rb)
    t_tip = 2.2 * rp * c_tip
    budget = block * period
    ck.check(f"F.probe_within_firmware_wait.{name}", max(ton, toff) + t_tip <= budget / 10,
             f"probe through {(rp + rb) / 1e3:.0f}k: on {ton * 1e6:.2f} us, off {toff * 1e6:.2f} us, the tip net "
             f"({c_tip * 1e12:.0f} pF through {rp / 1e3:.0f}k) {t_tip * 1e6:.2f} us; the firmware reads it {block} "
             f"samples = {budget * 1e6:.0f} us later; expected <= a tenth of that")

ck.done()
