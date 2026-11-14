"""analog_ac: Plaitsy's analog front end in frequency and time, by complex nodal analysis and small
time-step simulations (numpy only).

What it checks
  A. the eight CV stages as circuit.py wires them (followed net by net from the Seed's ADC pin back to the
     jack): each stage's corner against design.md (12 kHz for 13k || 1n, TRIG's 100p, V/OCT 33k || 1n) with
     1 % resistors and C0G 5 %; the response at the ADC pin with the 1k, the pin, the ADC's sampling
     capacitor, the routed track and, on V/OCT, the two BAT85 junctions;
  B. stability: the loop gain of every TL074 section with Rin, Rf || Cf, the summing node's routed
     capacitance and the op-amp's input capacitance, the 1k + ADC-pin + clamp load, the source on the jack
     (unpatched lug, probe resistor or a patched module): phase margin >= 45 deg at GBW 3 and 5.25 MHz;
  C. sampling: the ADC clock libDaisy sets, the scan time at OVS_8 (hal_daisy.cc says near 0.2 ms), the
     audio block, how often each CV is read, and what the single-pole input filter leaves above the
     control-rate Nyquist (aliasing), against Plaits' own conversion;
  D. ADC settling: the STM32H750's sample-and-hold (4 pF, 8.5 cycles) behind 1k + the TL074 (with its
     recovery from the kick-back), and behind the pot mux (B10k wiper + 74HC4051 Ron, no series resistor,
     the header and track capacitance): time-step simulation of the 8-conversion burst, and the datasheet's
     minimum-sampling-time table; the mux address change after each scan (4051 tON at 2.0 V) and MUX_OUT's
     RC settling before the next sample of that channel;
  E. trigger timing: TRIG jack edge -> 100p stage -> ADC scan -> 12-sample block -> Plaits' trigger
     detection: latency, jitter and the shortest pulse always seen, against Plaits' own; the TL074's slew;
  F. the normalization probe in time: the jack node through 10k / 100k, the stage, the reading the
     detector compares (ui.cc's timing, the ADC scan): settled with margin; the probe's crosstalk from the
     routed PROBE_F copper into the unnormalized CV tracks (coupled microstrip) and the glitch at the ADC;
  G. noise: TL074 en / in and every resistor's Johnson noise at the ADC pin over each stage's bandwidth and
     the 8x oversampling window, in LSB and (V/OCT) cents, against the ADC's own noise (SNR at 16 bit, OVS_8);
     the pot path's noise;
  H. the LED shift registers: the 3V3D current step when all 16 LEDs switch together, 3V3D apart from 3V3A,
     and the voltage the LED return current drops in the main board's GND pour between the stages' ground
     (bias dividers, jack sleeves via H2) and the Seed (a resistive model of the routed pour).

How the model is built
  circuit.py's netlist; each stage is extracted by following nets, not by name. Each TL074 section is a
  two-pole VCVS (A0, GBW, a second pole fitted to the datasheet's 56 deg at G = +1 into 10k || 20 pF) with
  its open-loop output resistance and input capacitance. Stray capacitance per net = routed track length x
  pF/mm (grounded coplanar line, 0.3 mm on 1.6 mm FR4 with the pour beside it) + pads + vias + header pins.
  The ADC input is the datasheet's model: pin capacitance, a sampling switch RADC and CADC.

Not modelled: the TL074's large-signal behaviour (rails, slew) except where a check says so, the ADC's
  non-linearity, temperature drift (see analog_dc), EMI, the Seed's own internal filtering of 3V3A,
  inductance of the copper.

Run from plaits/hardware/tests:  python test_analog_ac.py
"""
import collections
import math
import os
import re

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # small matrices: BLAS threads only cost time
import numpy as np

import harness

ck = harness.Checks("analog_ac")
circuit = harness.load("circuit")

# ---------------------------------------------------------------------------------------------- constants
# TL074, TI SLOS080W (rev. July 2025). The DIP-14 TL074(C)N is one of "all other devices" in the TL07xC
# tables 5.8 / 5.9; the NS / PS packages and M grade (and older stock) have the legacy 3 MHz die.
GBW_NEW = 5.25e6        # Hz, typ, "all other devices" (table 5.8) and TL07xH (table 5.7)
GBW_OLD = 3.0e6         # Hz, typ, "all NS and PS packages, all TL07xM devices" (table 5.8): the brief's 3 MHz
AOL = 2e5               # V/V, 200 V/mV typ, TL07xC, RL >= 2k, VO = +-10 V (table 5.8)
PM_UNITY = 56.0         # deg, typ, phase margin, G = +1, RL = 10k, CL = 20 pF (tables 5.7 / 5.9)
ZO_OL = 125.0           # ohm, typ, open-loop output impedance, f = 1 MHz, IO = 0 (tables 5.7 / 5.9)
SR_MIN = 8e6            # V/s, MIN, TL07xC, VI = 10 V, RL = 2k, CL = 100 pF (typ 20 V/us; brief: 13 V/us)
EN_1K = 37e-9           # V/rtHz, typ, f = 1 kHz, "all other devices" (table 5.9; 18 nV for PS/NS only)
EN_10K = 21e-9          # V/rtHz, typ, f = 10 kHz (table 5.9)
IN_NOISE = 80e-15       # A/rtHz, typ, f = 1 kHz (table 5.7, TL07xH; the legacy table's 10 fA is lower)
C_ID = 2e-12            # F, typ, differential input capacitance (ZID = 100 M || 2 pF, table 5.7)
C_ICM = 1e-12           # F, typ, common-mode input capacitance per input (ZICM = 6 T || 1 pF, table 5.7)

# STM32H750, ST DS12556 Rev 7 (March 2023), "Electrical characteristics (rev V)", section 7.3.20
CADC = 4e-12            # F, typ, internal sample-and-hold capacitor (table 182; rev Y table 85: 4 pF too)
C_PIN = 5e-12           # F, typ, I/O pin capacitance CIO (table 155)
RAIN_MAX_16 = 170.0     # ohm, max, external input impedance at 16 bits, TJ = 125 C (table 182; the table
                        # gives no sampling time for it: it is the fastest-sampling figure)
RAIN_MAX_12 = 1150.0    # ohm, max, the same at 12 bits
SNR_ADC = 77.0          # dB, typ, single-ended, 16 bits, fADC = 25 MHz, VDDA = VREF+ = 3.3 V, BOOST = 11
ENOB_ADC = 12.2         # bits, typ, the same conditions (table 184)
T_SAR_HALF = 0.5        # tCONV = tS + 0.5 + N/2 cycles of fADC (table 182): 8.5 + 8.5 = 17 at 16 bits
# Table 183, minimum sampling time vs RAIN, rev V, "with a 47 pF PCB capacitor", up to 125 C: slow channels
# (every ADC input but PA0_C..PC3_C and the fast PF3/5/7/9, PA6, PC4, PB1, PF11, PF13), s
TS_TABLE_SLOW = {16: [(47, 1.72e-7)],
                 14: [(47, 1.55e-7), (68, 1.58e-7), (100, 1.62e-7), (150, 1.80e-7), (220, 2.01e-7)],
                 12: [(47, 1.29e-7), (68, 1.32e-7), (100, 1.40e-7), (150, 1.51e-7), (220, 1.73e-7),
                      (330, 2.14e-7), (470, 2.68e-7), (680, 3.54e-7)],
                 10: [(47, 1.08e-7), (68, 1.11e-7), (100, 1.16e-7), (150, 1.26e-7), (220, 1.40e-7),
                      (330, 1.71e-7), (470, 2.13e-7), (680, 2.80e-7), (1000, 3.84e-7), (1500, 5.48e-7),
                      (2200, 7.78e-7), (3300, 1.14e-6)],
                 8: [(47, 8.61e-8), (68, 8.83e-8), (100, 9.22e-8), (150, 9.95e-8), (220, 1.11e-7),
                     (330, 1.32e-7), (470, 1.63e-7), (680, 2.12e-7), (1000, 2.85e-7), (1500, 4.05e-7),
                     (2200, 5.75e-7), (3300, 8.38e-7), (4700, 1.18e-6), (6800, 1.68e-6), (10000, 2.45e-6),
                     (15000, 3.65e-6)]}
TS_TABLE_FAST_16 = 1.14e-7   # s, fast channels, 16 bits, RAIN = 47 ohm (table 183)
TS_TABLE_C = 47e-12     # F, the table's PCB capacitor
# RADC (the sampling switch) is not given for the H7. Bound from table 183: 172 ns at 16 bits and 47 ohm
# on a slow channel must settle CADC to 1/2 LSB, so RADC * CADC <= 172 ns / ln(2^17): RADC <= this.
RADC = 1.72e-7 / (17 * math.log(2)) / CADC - 47.0
# ADC clock in libDaisy 9.0.0: sys/system.cpp, AdcClockSelection = PLL3 (R output), HSE 16 MHz, PLL3M 6,
# PLL3N 295, PLL3R 32; per/adc.cpp: ClockPrescaler ADC_CLOCK_ASYNC_DIV2, 16 bits, SamplingTime 8.5 cycles
# (InitSingle / InitMux default SPEED_8CYCLES_5), OVS_8 = ratio 8, shift 3, regular continued mode.
# Rev V silicon divides the ADC kernel clock by 2 again (RM0433; the HAL's ADC_ConfigureBoostMode halves
# it for rev V) -- the Seed's STM32H750IBK6 is taken as rev V (not confirmed from a Seed BOM; the firmware
# comment's "near 0.2 ms" agrees with it). Rev Y figures are printed alongside.
# VERIFY 2026-11-13: confirmed. The firmware runs at 480 MHz (main.cc hw.Init(true)), which DS12556 Table 1
# note 3 allows on revision V only; ST's HAL at the commit libDaisy v9.0.0 pins (stm32h7xx_hal_driver 404a70d)
# ADC_ConfigureBoostMode(): "else /* STM32H7 silicon Rev.V */ { freq /= 2U; /* divider by 2 for Rev.V */".
HSE, PLL3M, PLL3N, PLL3R = 16e6, 6, 295, 32
ADC_PRESC = 2
REV_V_DIV = 2
SMP_CYCLES = 8.5        # libDaisy's default (adc.h: InitSingle / InitMux speed = SPEED_8CYCLES_5)
OVS = 8
N_BITS = 16
T_RESTART = 5e-6        # s, libDaisy's DMA restart in the ConvCplt interrupt between scans (estimate, upper)
VDDA = 3.3              # V, 3V3A = VREF+ on the Seed
LSB = VDDA / 2 ** N_BITS

# Audio: libDaisy's real rate (PLL3P 49.1667 MHz / 1024) and Plaits' block of 12 (src/plaits/dsp/dsp.h)
FS_AUDIO = 48014.32
BLOCK = 12
T_BLOCK = BLOCK / FS_AUDIO

# BAT85, Vishay doc 88146 (13-May-02): Ctot max 10 pF at VR = 1 V, f = 1 MHz. The typical CJ-VR curve
# (Fig. "Typical Junction Capacitance", axis to 14 pF) could not be read as numbers: a junction law
# C(VR) = CJ0 / (1 + VR / 0.35)^0.5 scaled to 10 pF at 1 V is used, which gives about 20 pF at 0 V (more
# than the curve's axis: conservative for loading).
BAT85_C1V = 10e-12
BAT85_PHI, BAT85_M = 0.35, 0.5

# 74HC4051 at VCC = 3.3 V. TI CD74HC4051 SCHS122O (Jan 2026): rON (VIS = VCC to VEE, IO = 1 mA) at
# VCC 4.5 V: 90 typ, 180 max (25 C), 225 max (-40..85 C); not specified at 2 or 3.3 V. onsemi MC74HC4051A
# Rev 17 (Jul 2026) Fig. 1b (VCC - VEE = 3.0 V): about 80-100 ohm typical at 25 C (read off the curve).
RON_TYP = 100.0         # ohm, typ at 3.3 V (onsemi Fig. 1b, approximate)
RON_MAX = 2 * 225.0     # ohm, assumption: twice the 4.5 V maximum at -40..85 C (not specified at 3.3 V)
                        # (VERIFY 2026-11-13: onsemi MC74HC4051A's max/typ at 4.5 V, 190 / ~68, on its Fig. 1b
                        # typical at 3.0 V, ~90, gives ~320 ohm at 85 C: 450 is conservative, kept)
T_ON_MAX = 405e-9       # s, max, switch turn-on delay from S to output, VCC = 2.0 V, -40..85 C (TI table 5.8)
T_OFF_MAX = 340e-9      # s, max, switch turn-off delay, VCC = 2.0 V, -40..85 C (TI table 5.8)
C_COM_TYP = 25e-12      # F, typ, common output capacitance, 4051 (TI table 5.9)
C_COM_MAX = 130e-12     # F, max, common O/I capacitance, all switches off, HC4051A (onsemi AC table)
C_SW_IN = 5e-12         # F, typ, switch input capacitance (TI table 5.9)
R_POT = 10e3            # ohm, Alpha B10k track (design.md); worst source at mid-travel = R/4
PLAITS_POT_BITS = 12    # Plaits reads its pots with the STM32F373's 12-bit SAR ADC

# Board and wiring (estimates: see track_pf_per_mm())
ER_FR4 = 4.5            # the export's LAYER_PHYS: FR4, permittivity 4.5, core 59.4 mil
H_FR4 = 1.51e-3         # m, the export's core thickness (59.449 mil); 1.6 mm board
W_TRACK = 0.3e-3        # m, signal track width on both boards (copper_audit: 0.3 mm)
GAP_POUR = 0.254e-3     # m, track-to-pour gap (10 mil, the mixer's figure; conservative: more C)
C_PAD = 0.5e-12         # F, a THT pad among the pours (estimate, upper end)
C_VIA = 0.3e-12         # F, a 0.61 / 0.3 mm via (estimate)
C_HDR = 1.0e-12         # F, a mated 2.54 mm header pin pair to its neighbours (estimate)
CU_T = 35e-6            # m, copper thickness (the export's LAYER_PHYS: 1.38 mil = 1 oz)
RHO_CU = 1.72e-8        # ohm m
R_SRC_PATCH = 1e3       # ohm, a typical Eurorack output's series resistor
R_SRC_HIGHZ = 10e3      # ohm, a passive source (attenuator) as the worst patched case for crosstalk
C_CABLE = 100e-12       # F, 1 m patch cable
R_PROBE_PIN = 40.0      # ohm, the probe GPIO's output resistance (STM32 push-pull, estimate)
T_K = 313.0             # K, inside a warm case
KB = 1.380649e-23

# LEDs (design.md: "about 3 mA per colour"; 470 ohm from 3V3D_F through the 74HC595)
I_LED = 3e-3            # A per LED line, design.md's figure
N_LED_LINES = 16

# Criteria (first principles; the doc states the corners only)
PM_MIN = 45.0           # deg
TOL_R, TOL_C = 0.01, 0.05   # 1 % resistors, C0G (J) 5 %; film 1n is 5-10 % (bom.md allows film for 1n)
HALF_LSB = 0.5
CENTS_MAX = 1.0         # cents rms per V/OCT reading: well under audible pitch jitter

DOC = " ".join(harness.text("docs", "design.md").split())
HAL = harness.text("firmware", "src", "hal_daisy.cc")
UI = harness.text("firmware", "src", "plaits", "ui.cc")


# ---------------------------------------------------------------------------------- the stages, by nets
MAIN = circuit.main_board_parts()
FACE = circuit.faceplate_parts()
PARTS = {p.ref: p for p in MAIN + FACE}
NETS_MB = circuit.nets_of(MAIN)
NETS_FB = circuit.nets_of(FACE)
SEED = next(p for p in MAIN if p.kind == "SEED")


def parts_on(net, kind, parts=MAIN):
    return [p for p in parts if p.kind == kind and net in p.nets.values()]


def other(p, net):
    a, b = p.nets["1"], p.nets["2"]
    return b if a == net else a


def fb_net(mb):
    for ref, kind, pins in circuit.HEADERS:
        for a, b in pins:
            if a == mb:
                return b
    return None


def stage_of(adc_net):
    """Follow the nets from a Seed ADC pin back to the jack: {Rs, Rf, Cf, Rin, opamp, bias, ...}."""
    s = {"adc": adc_net}
    rs = [p for p in parts_on(adc_net, "R")]
    s["Rs"] = rs[0]
    s["oa"] = other(rs[0], adc_net)
    op = [p for p in MAIN if p.kind == "TL074" and s["oa"] in p.nets.values()][0]
    sec = next(k for k, (o, m, pl) in circuit.SECTION.items() if op.nets[o] == s["oa"])
    o, m, pl = circuit.SECTION[sec]
    s["op"], s["sec"], s["in"], s["bias"] = op.ref, sec, op.nets[m], op.nets[pl]
    s["Rf"] = next(p for p in parts_on(s["in"], "R") if other(p, s["in"]) == s["oa"])
    s["Cf"] = next(p for p in parts_on(s["in"], "C") if other(p, s["in"]) == s["oa"])
    s["Rin"] = next(p for p in parts_on(s["in"], "R") if p is not s["Rf"])
    s["cv"] = other(s["Rin"], s["in"])
    s["cv_f"] = fb_net(s["cv"])
    jack = next(p for p in FACE if p.kind == "JACK" and p.nets.get("3") == s["cv_f"])
    s["jack"], s["lug"] = jack.ref, jack.nets.get("2")
    s["probe_r"] = next((p for p in parts_on(s["lug"], "R", FACE)), None) if s["lug"] else None
    up = [p for p in parts_on(s["bias"], "R") if "3V3A" in p.nets.values()]
    dn = [p for p in parts_on(s["bias"], "R") if "GND" in p.nets.values()]
    s["Rb_up"], s["Rb_dn"] = up[0], dn[0]
    s["Cb"] = parts_on(s["bias"], "C")[0]
    s["clamps"] = [p for p in MAIN if p.kind == "BAT85" and adc_net in p.nets.values()]
    s["pin"] = next(pin for pin, n in SEED.nets.items() if n == adc_net)
    return s


ADC_NETS = [n for pin, (name, n) in sorted(circuit.SEED.items(), key=lambda kv: kv[0])
            if n and n.startswith("ADC_")]
STAGES = {n[4:]: stage_of(n) for n in ADC_NETS}
V = lambda p: harness.ohms(p.value) if p.kind == "R" else harness.farads(p.value)
ck.check("A.stages_found: eight CV stages traced from the Seed's ADC pins back to their jacks",
         len(STAGES) == 8 and all(s["jack"] for s in STAGES.values()),
         f"expected 8; got {len(STAGES)}: " + ", ".join(f"{k} {s['Rs'].ref}/{s['Rf'].ref}/{s['Cf'].ref}/"
                                                        f"{s['Rin'].ref} {s['op']}.{s['sec']} {s['jack']}"
                                                        for k, s in STAGES.items()))


# ----------------------------------------------------------------------------- routed stray capacitance
def _ellipk(k):
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(30):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def microstrip(w=W_TRACK, h=H_FR4, er=ER_FR4):
    """Hammerstad: (eeff, Z0, C per m) of a single microstrip."""
    c0 = 299792458.0
    u = w / h
    eeff = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 / u) ** -0.5 + (0.04 * (1 - u) ** 2 if u < 1 else 0))
    z0 = 60 / math.sqrt(eeff) * math.log(8 / u + u / 4) if u <= 1 else \
        120 * math.pi / math.sqrt(eeff) / (u + 1.393 + 0.667 * math.log(u + 1.444))
    return eeff, z0, math.sqrt(eeff) / (c0 * z0)


def track_pf_per_mm():
    """(microstrip, grounded coplanar with the pour GAP_POUR away) capacitance to ground, pF/mm."""
    e0 = 8.854e-12
    eeff, z0, ms = microstrip()
    w, h, er = W_TRACK, H_FR4, ER_FR4
    a, b = w / 2, w / 2 + GAP_POUR
    k, k1 = a / b, math.tanh(math.pi * a / (2 * h)) / math.tanh(math.pi * b / (2 * h))
    r = _ellipk(k) / _ellipk(math.sqrt(1 - k * k))
    r1 = _ellipk(k1) / _ellipk(math.sqrt(1 - k1 * k1))
    cpw = 2 * e0 * r + 2 * e0 * er * r1
    return ms * 1e12 / 1e3, cpw * 1e12 / 1e3


def coupled_mutual_pf_per_mm(s, w=W_TRACK, h=H_FR4, er=ER_FR4):
    """Mutual capacitance of two edge-coupled microstrips s apart (edge to edge), pF/mm: Garg & Bahl's
    even / odd mode capacitances (Gupta, Garg, Bahl, Microstrip lines and slotlines), Cm = (Co - Ce) / 2."""
    e0, c0 = 8.854e-12, 299792458.0
    eeff, z0, _ = microstrip(w, h, er)
    cp = e0 * er * w / h
    cf = 0.5 * (math.sqrt(eeff) / (c0 * z0) - cp)
    A = math.exp(-0.1 * math.exp(2.33 - 2.53 * w / h))
    cf2 = cf / (1 + A * (h / s) * math.tanh(8 * s / h)) * math.sqrt(er / eeff)
    ce = cp + cf + cf2
    k = (s / h) / (s / h + 2 * w / h)
    kp = math.sqrt(1 - k * k)
    cga = e0 * _ellipk(kp) / _ellipk(k)
    cgd = e0 * er / math.pi * math.log(1 / math.tanh(math.pi * s / (4 * h))) + \
        0.65 * cf * (0.02 * math.sqrt(er) / (s / h) + 1 - er ** -2)
    co = cp + cf + cga + cgd
    return (co - ce) / 2 * 1e12 / 1e3


ROUTED = harness.routed()
MS_PF, CPW_PF = track_pf_per_mm()
ck.check("A.track_capacitance: pF/mm of a 0.3 mm track on the export's 1.51 mm FR4 core in the textbook range",
         0.03 <= MS_PF <= 0.08 and MS_PF < CPW_PF <= 0.16,
         f"expected microstrip 0.03-0.08 pF/mm, grounded coplanar above it and <= 0.16; got {MS_PF:.3f} / "
         f"{CPW_PF:.3f} pF/mm (gap {GAP_POUR * 1e3:.2f} mm); the coplanar figure is used (worst)")


def base(net):
    if net in ("GND_F", "GND_D_F"):
        return "GND"
    return net[:-2] if net.endswith("_F") else net


def net_caps():
    """Stray capacitance per merged net (both boards), F, and the breakdown (track mm, pads, vias, header pins)."""
    caps, info = collections.defaultdict(float), collections.defaultdict(lambda: [0.0, 0, 0, 0])
    for b in (ROUTED.main, ROUTED.face):
        for n, s in b.net_stats().items():
            nb = base(n)
            caps[nb] += s["length"] * CPW_PF * 1e-12 + s["vias"] * C_VIA
            info[nb][0] += s["length"]
            info[nb][2] += s["vias"]
        for p in b.pads:
            if p.net:
                caps[base(p.net)] += C_PAD
                info[base(p.net)][1] += 1
    for ref, kind, pins in circuit.HEADERS:
        for mb, fb in pins:
            caps[mb] += C_HDR
            info[mb][3] += 1
    # MB nets named differently on the FB (SPI_MOSI / MOSI_F ...) merge by the header table
    return caps, info


CAPS, CAPINFO = net_caps()
for k, s in STAGES.items():
    for n in (s["in"], s["oa"], s["adc"], s["cv"]):
        L, pads, vias, hdr = CAPINFO[n]
        print(f"      stray {n:10}: {L:6.1f} mm track, {pads:2d} pads, {vias} vias, {hdr} header pins -> "
              f"{CAPS[n] * 1e12:5.1f} pF")
    break
ck.check("A.summing_nodes_routed: every IN_* summing node is short copper (design.md: 8.7 mm each)",
         all(abs(CAPINFO[s["in"]][0] - 8.7) < 0.5 for s in STAGES.values()) and "8.7 mm" in DOC,
         "expected 8.7 +- 0.5 mm per design.md; got " + ", ".join(f"{s['in']} {CAPINFO[s['in']][0]:.1f}"
                                                                  for s in STAGES.values()))


def bat85_c(vr):
    vr = max(vr, 0.0)
    cj0 = BAT85_C1V * (1 + 1 / BAT85_PHI) ** BAT85_M
    return cj0 / (1 + vr / BAT85_PHI) ** BAT85_M


def clamp_c(s, v_adc=None):
    """Junction capacitance the clamps put on the ADC pin at v_adc (worst over 0..3.3 V when None)."""
    if not s["clamps"]:
        return 0.0
    vs = [v_adc] if v_adc is not None else list(np.linspace(0, VDDA, 34))
    best = 0.0
    for v in vs:
        c = 0.0
        for d in s["clamps"]:
            if d.nets["2"] == s["adc"]:          # anode on the pin, cathode on 3V3A: VR = 3V3A - v
                c += bat85_c(VDDA - v)
            else:                                # cathode on the pin, anode on GND: VR = v
                c += bat85_c(v)
        best = max(best, c)
    return best


# ---------------------------------------------------------------------------- the descriptor-form engine
class Opamp:
    """Two-pole TL074 section: A(s) = A0 / ((1 + s/w1)(1 + s/w2)), output through ZO."""

    def __init__(self, gbw, pm=PM_UNITY, a0=AOL, zo=ZO_OL):
        self.gbw, self.a0, self.zo = gbw, a0, zo
        self.w1 = 2 * math.pi * gbw / a0
        self.w2 = self._fit_w2(pm)

    def A(self, s, w2=None):
        return self.a0 / ((1 + s / self.w1) * (1 + s / (w2 or self.w2)))

    def _fit_w2(self, pm):
        def margin(w2):
            f = np.logspace(4, 9, 3000)
            s = 2j * np.pi * f
            zl = 1 / (1 / 10e3 + s * 20e-12)
            t = self.A(s, w2) * zl / (zl + self.zo)
            i = np.argmax(np.abs(t) < 1)
            return 180 + np.degrees(np.unwrap(np.angle(t)))[i]
        lo, hi = 2 * math.pi * 1e5, 2 * math.pi * 1e9
        for _ in range(60):
            mid = math.sqrt(lo * hi)
            lo, hi = (lo, mid) if margin(mid) > pm else (mid, hi)
        return math.sqrt(lo * hi)


class Sys:
    """Linear circuit in descriptor form (G + sC) x = b: node voltages, voltage-source currents and two
    states per op-amp (x1, x2 with x2 = A(s) (v+ - v-)). Works in the frequency and the time domain."""

    def __init__(self):
        self.nodes, self.R, self.C, self.V, self.ops, self.SW = {}, [], [], [], [], []

    def n(self, name):
        if name == "0":
            return -1
        return self.nodes.setdefault(name, len(self.nodes))

    def r(self, a, b, val, tag=""):
        self.R.append((self.n(a), self.n(b), float(val), tag))

    def c(self, a, b, val):
        if val > 0:
            self.C.append((self.n(a), self.n(b), float(val)))

    def v(self, node, name):
        self.V.append((self.n(node), name))

    def sw(self, a, b, val, name):
        """A switch: conductance 1/val while closed (time domain); open in the frequency domain."""
        self.SW.append((self.n(a), self.n(b), float(val), name))

    def opamp(self, name, inp, inm, out, model):
        self.ops.append((name, self.n(inp), self.n(inm), self.n(name + ".int"), model))
        self.r(name + ".int", out, model.zo, "ZO")
        self.c(inp, "0", C_ICM)
        self.c(inm, "0", C_ICM)
        self.c(inp, inm, C_ID)

    def size(self):
        return len(self.nodes) + len(self.V) + 3 * len(self.ops)

    def mats(self, closed=(), break_op=None):
        N = len(self.nodes)
        M = self.size()
        G, Cm = np.zeros((M, M)), np.zeros((M, M))

        def stamp(Z, a, b, y):
            if a >= 0:
                Z[a, a] += y
            if b >= 0:
                Z[b, b] += y
            if a >= 0 and b >= 0:
                Z[a, b] -= y
                Z[b, a] -= y
        for a, b, val, tag in self.R:
            stamp(G, a, b, 1 / val)
        for a, b, val, name in self.SW:
            if name in closed:
                stamp(G, a, b, 1 / val)
        for a, b, val in self.C:
            stamp(Cm, a, b, val)
        for i in range(N):
            G[i, i] += 1e-15                      # keeps floating nodes (open switches) solvable
        k = N
        for node, name in self.V:
            G[node, k] += 1
            G[k, node] += 1
            k += 1
        for name, p, m, o, model in self.ops:
            ib, x1, x2 = k, k + 1, k + 2
            G[o, ib] += 1                         # the int source's current leaves node o
            G[ib, o] += 1                         # v_int - x2 = 0 (or v_int = test 1 V when broken)
            if name != break_op:
                G[ib, x2] -= 1
            # x1 / A0 + (1/w1) x1' / A0 ... scaled: x1 + x1'/w1 = A0 (v+ - v-), divided by A0
            G[x1, x1] += 1 / model.a0
            Cm[x1, x1] += 1 / (model.a0 * model.w1)
            if p >= 0:
                G[x1, p] -= 1
            if m >= 0:
                G[x1, m] += 1
            G[x2, x2] += 1
            Cm[x2, x2] += 1 / model.w2
            G[x2, x1] -= 1
            k += 3
        return G, Cm

    def b_of(self, values):
        b = np.zeros(self.size(), complex)
        N = len(self.nodes)
        for i, (node, name) in enumerate(self.V):
            b[N + i] = values.get(name, 0.0)
        return b

    def solve(self, f, values):
        G, Cm = self.mats()
        return np.linalg.solve(G + 2j * math.pi * f * Cm, self.b_of(values))

    def gain(self, f, node, values):
        return self.solve(f, values)[self.nodes[node]]

    def loop_gain(self, f, opname):
        G, Cm = self.mats(break_op=opname)
        N = len(self.nodes)
        j = [o[0] for o in self.ops].index(opname)
        k = N + len(self.V) + 3 * j
        b = np.zeros(self.size(), complex)
        b[k] = 1.0
        x = np.linalg.solve(G + 2j * math.pi * f * Cm, b)
        return -x[k + 2]

    def op_index(self, opname):
        return len(self.nodes) + len(self.V) + 3 * [o[0] for o in self.ops].index(opname)


def phase_margin(sysm, op, freqs=np.logspace(4, 8.5, 160)):
    t = np.array([sysm.loop_gain(f, op) for f in freqs])
    mag, ph = np.abs(t), np.degrees(np.unwrap(np.angle(t)))
    i = int(np.argmax(mag < 1))
    if i == 0:
        return float("nan"), float("nan")
    w = math.log(mag[i - 1]) / (math.log(mag[i - 1]) - math.log(mag[i]))
    fc = freqs[i - 1] * (freqs[i] / freqs[i - 1]) ** w
    p = ph[i - 1] + w * (ph[i] - ph[i - 1])
    return 180 + p, fc


def stage_sys(s, model, src="unpatched", r_src=None, c_extra_adc=0.0, cadc=True, rs_scale=1.0,
              rf_scale=1.0, cf_scale=1.0, c_cv_coupling=None):
    """One CV stage from the jack to the ADC's sampling capacitor.

    src: 'unpatched' (the lug: GND_F, or the probe through its 10k from a pin of R_PROBE_PIN), 'patched'
    (a source V 'jack' behind r_src, default R_SRC_PATCH, with a 1 m cable). Sources: 'jack' (the jack's
    voltage), 'probe' (the probe pin), 'bias' (3V3A ac), 'xt' (a step coupled through c_cv_coupling)."""
    S = Sys()
    cv, inn, oa, adc = s["cv"], s["in"], s["oa"], s["adc"]
    if src == "patched":
        S.v("jsrc", "jack")
        S.r("jsrc", cv, r_src or R_SRC_PATCH, "src")
        S.c(cv, "0", C_CABLE)
    else:
        if s["probe_r"] is not None:
            S.v("ppin", "probe")
            S.r("ppin", "probe_f", R_PROBE_PIN, "pin")
            S.r("probe_f", cv, V(s["probe_r"]), s["probe_r"].ref)
            S.c("probe_f", "0", CAPS["PROBE"])
        else:
            S.r(cv, "0", 0.05, "lug")             # the switch lug to GND_F (contact + copper)
    if c_cv_coupling:
        S.v("xt_src", "xt")
        S.c("xt_src", cv, c_cv_coupling)
    S.c(cv, "0", CAPS[cv])
    S.r(cv, inn, V(s["Rin"]), s["Rin"].ref)
    S.c(inn, "0", CAPS[inn])
    S.r(inn, oa, V(s["Rf"]) * rf_scale, s["Rf"].ref)
    S.c(inn, oa, V(s["Cf"]) * cf_scale)
    S.c(oa, "0", CAPS[oa])
    S.r(oa, adc, V(s["Rs"]) * rs_scale, s["Rs"].ref)
    S.c(adc, "0", CAPS[adc] + C_PIN + clamp_c(s) + c_extra_adc)
    # bias divider: 3V3A (ac source 'bias') - Rb_up - BIAS - Rb_dn - GND, Cb to GND
    S.v("3v3a", "bias")
    S.r("3v3a", s["bias"], V(s["Rb_up"]), s["Rb_up"].ref)
    S.r(s["bias"], "0", V(s["Rb_dn"]), s["Rb_dn"].ref)
    S.c(s["bias"], "0", V(s["Cb"]) + CAPS[s["bias"]] / 7)
    S.opamp(f"{s['op']}.{s['sec']}", s["bias"], inn, oa, model)
    if cadc:
        S.sw(adc, "cadc", RADC, "sample")
        S.c("cadc", "0", CADC)
    return S


OP_NEW, OP_OLD = Opamp(GBW_NEW), Opamp(GBW_OLD)
print(f"      TL074 model: second pole {OP_NEW.w2 / 2 / math.pi / 1e6:.2f} MHz (GBW 5.25 MHz), "
      f"{OP_OLD.w2 / 2 / math.pi / 1e6:.2f} MHz (GBW 3 MHz) for {PM_UNITY:.0f} deg at G = +1; "
      f"RADC bound from table 183: {RADC:.0f} ohm")

# ================================================================================ A. corners, response
m = re.search(r"Corner frequency (\d+) kHz \((\d+k) ‖ (\d+n)\)", DOC)
DOC_CORNER_KHZ = float(m.group(1)) if m else float("nan")
ck.check("A.doc_corner_found: design.md states the CV corner (12 kHz, 13k || 1n)", m is not None,
         f"got {m.group(0) if m else 'no match'}")
for k, s in STAGES.items():
    rf, cf = V(s["Rf"]), V(s["Cf"])
    f0 = 1 / (2 * math.pi * rf * cf)
    lo = 1 / (2 * math.pi * rf * (1 + TOL_R) * cf * (1 + TOL_C))
    hi = 1 / (2 * math.pi * rf * (1 - TOL_R) * cf * (1 - TOL_C))
    if k == "TRIG":
        # "TRIG uses 100p so edges stay sharp": a 10 % - 90 % edge at the ADC well under one ADC burst
        tr = 2.2 * rf * cf * (1 + TOL_R) * (1 + TOL_C)
        ck.within(f"A.corner.{k}: TRIG's {s['Cf'].value} || {s['Rf'].value} edge (10-90 %) is sharp against "
                  f"one 8-conversion burst", tr * 1e6, None, 22.0 * 0.5, " us",
                  f"corner {f0 / 1e3:.0f} kHz ({lo / 1e3:.0f}-{hi / 1e3:.0f}); a burst is "
                  f"{OVS * (SMP_CYCLES + T_SAR_HALF + N_BITS / 2):.0f} ADC cycles, about 22 us")
    elif k == "VOCT":
        ck.within(f"A.corner.{k}: V/OCT's {s['Rf'].value} || {s['Cf'].value} corner stays above the 2 kHz "
                  f"control-rate Nyquist with tolerances", lo / 1e3, 1 / (2 * T_BLOCK) / 1e3, None, " kHz",
                  f"nominal {f0 / 1e3:.2f} kHz, {lo / 1e3:.2f}-{hi / 1e3:.2f} kHz at 1 % / 5 %")
    else:
        ck.check(f"A.corner.{k}: {s['Rf'].value} || {s['Cf'].value} corner matches design.md's "
                 f"{DOC_CORNER_KHZ:.0f} kHz within the parts' tolerance",
                 lo <= DOC_CORNER_KHZ * 1e3 * 1.025 and hi >= DOC_CORNER_KHZ * 1e3 * 0.975,
                 f"expected {DOC_CORNER_KHZ:.0f} kHz (+-2.5 % rounding) inside {lo / 1e3:.2f}-{hi / 1e3:.2f} kHz;"
                 f" nominal {f0 / 1e3:.2f} kHz")

# the response at the ADC pin (and on CADC) against the stage alone: the 1k + pin + track + clamps
for k, s in STAGES.items():
    S = stage_sys(s, OP_NEW, src="patched", r_src=1e-3, cadc=False)    # an ideal source on the jack
    S.c(s["adc"], "0", CADC)                         # sampling capacitor connected (worst loading)
    rf, cf = V(s["Rf"]), V(s["Cf"])
    f0 = 1 / (2 * math.pi * rf * cf)
    h0 = abs(S.gain(1.0, s["adc"], {"jack": 1.0}))
    dev = []
    for f in (f0 / 10, f0 / 2, f0, 2 * f0):
        h = abs(S.gain(f, s["adc"], {"jack": 1.0})) / h0
        ideal = 1 / abs(1 + 1j * f / f0)
        dev.append(harness.db(h / ideal))
    c_adc = CAPS[s["adc"]] + C_PIN + clamp_c(s) + CADC
    fp = 1 / (2 * math.pi * V(s["Rs"]) * c_adc)
    g_dc = -V(s["Rf"]) / V(s["Rin"])
    ck.check(f"A.response.{k}: at the ADC pin the response is the stage's single pole (1k + {c_adc * 1e12:.0f} pF "
             f"pin/track/CADC{'/BAT85' if s['clamps'] else ''} adds < 0.1 dB up to 2 x the corner)",
             max(abs(d) for d in dev) < 0.1 and abs(h0 - abs(g_dc)) / abs(g_dc) < 1e-3,
             f"expected |dev| < 0.1 dB and DC gain {g_dc:.3f}; got {', '.join(f'{d:+.3f}' for d in dev)} dB at "
             f"f0/10, f0/2, f0, 2 f0 (f0 {f0 / 1e3:.1f} kHz), DC {h0:.4f}; Rs || C_adc pole {fp / 1e6:.1f} MHz")

# ================================================================================ B. stability
PM_ROWS = collections.defaultdict(list)
for k, s in STAGES.items():
    cases = [("unpatched", {})]
    cases.append(("patched, 1k + 1 m cable", dict(src="patched")))
    cases.append(("patched, 0 ohm (a hard source)", dict(src="patched", r_src=1.0)))
    cases.append(("unpatched, 100 pF extra on the ADC pin", dict(c_extra_adc=100e-12)))
    for model, mname in ((OP_NEW, "GBW 5.25 MHz"), (OP_OLD, "GBW 3 MHz")):
        for cname, kw in cases:
            S = stage_sys(s, model, cadc=False, **kw)
            S.c(s["adc"], "0", CADC)
            pm, fc = phase_margin(S, f"{s['op']}.{s['sec']}")
            PM_ROWS[k].append((pm, fc, mname, cname))
for k, rows in PM_ROWS.items():
    pm, fc, mname, cname = min(rows)
    s = STAGES[k]
    ck.check(f"B.phase_margin.{k}: {s['op']}.{s['sec']} with Rin {s['Rin'].value}, {s['Rf'].value} || "
             f"{s['Cf'].value}, 1k + ADC pin load >= {PM_MIN:.0f} deg", pm >= PM_MIN,
             f"expected >= {PM_MIN:.0f} deg in every case; worst {pm:.1f} deg at {fc / 1e6:.2f} MHz ({mname}, {cname});"
             f" best {max(rows)[0]:.1f} deg")
# what Cf buys: the same stage with no Cf (the mixer's 17 deg case had a big Rin || Rf and no Cf)
s = STAGES["VOCT"]
S = stage_sys(s, OP_OLD, cadc=False, cf_scale=1e-9)
pm_nocf, fc_nocf = phase_margin(S, f"{s['op']}.{s['sec']}")
print(f"      without Cf, V/OCT's stage would have {pm_nocf:.1f} deg at {fc_nocf / 1e6:.2f} MHz (GBW 3 MHz)")

# ================================================================================ C. sampling
F_PLL3R = HSE / PLL3M * PLL3N / PLL3R
F_ADC_V = F_PLL3R / ADC_PRESC / REV_V_DIV
F_ADC_Y = F_PLL3R / ADC_PRESC
N_CH = len(ADC_NETS) + 1
# [2026-11-14: the sampling times are read from hal_daisy.cc (the speed argument of InitSingle / InitMux, libDaisy's
# default when there is none) instead of taking 8.5 cycles for every channel, so the pot fix shows here.]
_SPEED = {f"SPEED_{c}CYCLES_5": c + 0.5 for c in (1, 2, 8, 16, 32, 64, 387, 810)}


def _speed_of(call):
    m = re.search(r"\b" + call + r"\(([^;]*?)\);", " ".join(HAL.split()))
    s = re.search(r"SPEED_\d+CYCLES_5", m.group(1)) if m else None
    return _SPEED[s.group(0)] if s else SMP_CYCLES


SMP_CV, SMP_MUX = _speed_of("InitSingle"), _speed_of("InitMux")
CYC_CONV = SMP_CV + T_SAR_HALF + N_BITS / 2
CYC_CONV_MUX = SMP_MUX + T_SAR_HALF + N_BITS / 2
CYC_BURST = OVS * CYC_CONV
CYC_SCAN = (N_CH - 1) * CYC_BURST + OVS * CYC_CONV_MUX
T_SCAN_V = CYC_SCAN / F_ADC_V + T_RESTART
T_SCAN_Y = CYC_SCAN / F_ADC_Y + T_RESTART
T_S_V, T_S_Y = SMP_CV / F_ADC_V, SMP_CV / F_ADC_Y
T_S_MUX_V = SMP_MUX / F_ADC_V
T_CONV_MUX_V = CYC_CONV_MUX / F_ADC_V
print(f"      hal_daisy.cc: CV channels sampled {SMP_CV} cycles, the pot mux {SMP_MUX} cycles")
print(f"      ADC: PLL3R {F_PLL3R / 1e6:.3f} MHz -> fADC {F_ADC_V / 1e6:.3f} MHz (rev V) / {F_ADC_Y / 1e6:.3f} MHz "
      f"(rev Y); {CYC_CONV:.0f} cycles per conversion, burst {CYC_BURST:.0f} cycles = {CYC_BURST / F_ADC_V * 1e6:.1f} us; "
      f"scan of {N_CH} channels {T_SCAN_V * 1e6:.0f} us (rev V) / {T_SCAN_Y * 1e6:.0f} us (rev Y); "
      f"tS {T_S_V * 1e9:.0f} / {T_S_Y * 1e9:.0f} ns; block {T_BLOCK * 1e6:.1f} us")
m_cfg = re.search(r"OverSampling kOversampling = AdcHandle::(OVS_\d+)", HAL)
ck.check("C.firmware_ovs: hal_daisy.cc runs the ADC at OVS_8 with the mux last in the sequence",
         m_cfg is not None and m_cfg.group(1) == f"OVS_{OVS}" and "config[ADC_INPUT_LAST].InitMux(" in HAL,
         f"expected OVS_{OVS} and InitMux on the last entry; got {m_cfg.group(1) if m_cfg else 'none'}")
m_doc = re.search(r"full scan of the nine channels near ([\d.]+) ms", " ".join(HAL.split()))
claim = float(m_doc.group(1)) if m_doc else float("nan")
ck.within(f"C.scan_time: a {N_CH}-channel scan at OVS_{OVS} (rev V clock) matches hal_daisy.cc's 'near {claim} ms'",
          T_SCAN_V * 1e3, claim * 0.8, claim * 1.2, " ms", f"rev Y silicon would take {T_SCAN_Y * 1e3:.3f} ms")
ck.within("C.fresh_every_block: every CV gets a new sample between two audio blocks (scan < block)",
          T_SCAN_V * 1e6, None, T_BLOCK * 1e6, " us", f"block {T_BLOCK * 1e6:.1f} us = {BLOCK} samples at "
          f"{FS_AUDIO:.2f} Hz; Plaits reads its CVs once per block too")

# aliasing: the reading is one 8-conversion burst average per block: the CV is sampled at 1 / T_BLOCK
FN = 1 / (2 * T_BLOCK)
T_CONV_V = CYC_CONV / F_ADC_V


def h_burst(f, tc=T_CONV_V, n=OVS):
    x = math.pi * f * tc
    return abs(math.sin(n * x) / (n * math.sin(x))) if x else 1.0


alias_rows = []
for k in ("MODEL", "VOCT", "TRIG"):
    s = STAGES[k]
    f0 = 1 / (2 * math.pi * V(s["Rf"]) * V(s["Cf"]))
    row = []
    for f in (FN, 2 * FN, 5e3, 10e3, 20e3):
        h = 1 / abs(1 + 1j * f / f0) * h_burst(f)
        row.append((f, harness.db(h)))
    # white CV noise / modulation 0..20 kHz: share of its power that lands above Nyquist and folds back
    ff = np.linspace(1, 20e3, 20000)
    p = 1 / (1 + (ff / f0) ** 2) * np.array([h_burst(x) ** 2 for x in ff])
    alias_rows.append((k, f0, row, float(p[ff > FN].sum() / p.sum())))
for k, f0, row, share in alias_rows:
    print(f"      aliasing {k:5s} (corner {f0 / 1e3:5.1f} kHz): " + ", ".join(f"{f / 1e3:.1f} kHz {d:+.1f} dB"
                                                                           for f, d in row)
          + f"; a flat 0-20 kHz modulation folds {share * 100:.0f} % of its power below {FN / 1e3:.2f} kHz")
# Plaits: SDADC1-3 at SYSCLK / 12 = 6 MHz, one injected conversion per channel started at the end of each
# Poll() and read in the next: also one reading per block, its own sinc window the only filter beyond the
# stage (Plaits' CV filter capacitors could not be confirmed: its schematic was not read).
ck.check("C.alias_like_plaits: both read each CV once per 12-sample block; Plaitsy's 22 us burst average does "
         "not narrow the CV band below Nyquist (< 0.1 dB at 2 kHz)", h_burst(FN) > 10 ** (-0.1 / 20),
         f"expected > -0.1 dB; got {harness.db(h_burst(FN)):+.3f} dB; the {DOC_CORNER_KHZ:.0f} kHz pole is no "
         f"anti-alias filter for a {1 / T_BLOCK / 1e3:.0f} kHz control rate (-0.1 dB at Nyquist), as on Plaits")
# the sequence order the timing below assumes: hal_daisy.cc's kAdcPins, then the mux
m_pins = re.search(r"kAdcPins\[ADC_INPUT_LAST\] = \{([^}]*)\}", HAL)
fw_order = [x.strip().split("::")[-1] for x in m_pins.group(1).split(",")] if m_pins else []
seed_by_a = {name.split("/")[-1]: net for pin, (name, net) in circuit.SEED.items() if "/A" in name}
RANKS = [seed_by_a.get(a) for a in fw_order] + ["MUX_OUT"]
ck.check("C.rank_order: the ADC sequence (hal_daisy.cc kAdcPins + the mux) maps onto circuit.py's ADC nets",
         RANKS[:-1] == ADC_NETS, f"expected {ADC_NETS}; got {RANKS[:-1]} from {fw_order}")
T_BURST_V = CYC_BURST / F_ADC_V


# ---------------------------------------------------------------------------------- time-domain engine
class Tsim:
    """Backward-Euler time stepping of a Sys, with its switches open or closed per segment."""

    def __init__(self, S, values=None):
        self.S, self.cache = S, {}
        self.values = values or {}

    def _m(self, closed, dt):
        key = (tuple(sorted(closed)), dt)
        if key not in self.cache:
            G, Cm = self.S.mats(closed=closed)
            A = G + Cm / dt
            Ainv = np.linalg.inv(A)
            self.cache[key] = (Ainv @ (Cm / dt), Ainv)
        return self.cache[key]

    def run(self, x, duration, dt, closed=(), values=None, record=None):
        M, Ainv = self._m(closed, dt)
        b = self.S.b_of(dict(self.values, **(values or {}))).real
        u = Ainv @ b
        n = max(1, int(round(duration / dt)))
        trace = []
        for _ in range(n):
            x = M @ x + u
            if record is not None:
                trace.append(x[record])
        return (x, np.array(trace)) if record is not None else x


def burst_error(S, t_s, t_conv, kick=VDDA, carry=False, dt_s=1e-9, dt_c=5e-9):
    """Errors (V) of the 8 conversions of one burst on CADC, all sources at 0 (small signal): CADC starts
    every conversion 'kick' away from the input (carry=False: the conservative 'reset' model) or only the
    first one (carry=True: CADC keeps what it sampled, the charge-redistribution behaviour)."""
    sim = Tsim(S)
    x = np.zeros(S.size())
    nc = S.nodes["cadc"]
    errs = []
    for i in range(OVS):
        if i == 0 or not carry:
            x[nc] = kick
        x = sim.run(x, t_s, dt_s, closed=("sample",))
        errs.append(x[nc])
        x = sim.run(x, t_conv - t_s, dt_c)
    return np.array(errs)


T183_TOL_LSB = {16: 10, 14: 4, 12: 2, 10: 2, 8: 2}   # Table 182 note 6: the tolerance behind the RAIN / ts figures


def ts_table_extrapolated(bits, r):
    """Table 183's minimum sampling time (slow channels) at RAIN = r, extrapolated linearly in r beyond the
    table's last row; for 16 bits (one row) with the per-ohm slope of a single RC settling to the table's
    tolerance: slope = C x ln(2^N / tol), C fitted from the 10- and 12-bit rows' high-RAIN slopes (52.8 / 53.7 pF,
    the 47 pF PCB capacitor plus CADC and the pin).
    VERIFY 2026-11-13: the 16-bit slope was a straight-line fit of the 8 / 10 / 12-bit slopes against N, which
    ignores note 6's larger 16-bit tolerance (10 LSB, not 2) and gave 1.86 us at 2950 ohm instead of 1.53 us."""
    rows = TS_TABLE_SLOW[bits]
    if len(rows) >= 2:
        (r1, t1), (r2, t2) = rows[-2], rows[-1]
        if r <= r2:
            return float(np.interp(r, [a for a, b in rows], [b for a, b in rows]))
        return t2 + (t2 - t1) / (r2 - r1) * (r - r2)
    cs = []
    for b in (10, 12):
        (r1, t1), (r2, t2) = TS_TABLE_SLOW[b][-2], TS_TABLE_SLOW[b][-1]
        cs.append((t2 - t1) / (r2 - r1) / math.log(2 ** b / T183_TOL_LSB[b]))
    slope = float(np.mean(cs)) * math.log(2 ** bits / T183_TOL_LSB[bits])
    return rows[0][1] + slope * (r - rows[0][0])


# ================================================================================ D. ADC settling
T_CONV_Y = CYC_CONV / F_ADC_Y
print(f"      table 183 extrapolated, 16 bits, slow channel: {ts_table_extrapolated(16, 1000) * 1e9:.0f} ns at 1k, "
      f"{ts_table_extrapolated(16, 2600) * 1e9:.0f} ns at 2.6k; 12 bits: {ts_table_extrapolated(12, 2600) * 1e9:.0f} ns at 2.6k")
for k, s in STAGES.items():
    rows = []
    for model, mname in ((OP_OLD, "GBW 3 MHz"), (OP_NEW, "GBW 5.25 MHz")):
        S = stage_sys(s, model)
        e_reset = burst_error(S, T_S_V, T_CONV_V)
        e_carry = burst_error(S, T_S_V, T_CONV_V, carry=True)
        rows.append((abs(e_reset.mean()), abs(e_carry.mean()), abs(e_reset[0]), mname))
    w = max(rows)
    S = stage_sys(s, OP_OLD)
    e_y = burst_error(S, T_S_Y, T_CONV_Y)
    ck.within(f"D.sample_hold.{k}: the 8-conversion burst behind {s['Rs'].value} + the TL074 settles CADC to 1/2 LSB "
              f"(16 bit, rev V clock, CADC {VDDA} V off at every conversion)", w[0] / LSB, None, HALF_LSB, " LSB",
              f"worst {w[3]}; first conversion {w[2] / LSB:.3f} LSB; with CADC kept between conversions "
              f"{w[1] / LSB:.3f} LSB; at the rev Y clock (tS {T_S_Y * 1e9:.0f} ns) {abs(e_y.mean()) / LSB:.3f} LSB")
    r_ain = V(s["Rs"]) + ZO_OL
    need = ts_table_extrapolated(16, r_ain)
    ck.within(f"D.table183.{k}: table 183's minimum sampling time at RAIN = {r_ain:.0f} ohm (1k + TL074 ZO, 16 bit, "
              f"slow-channel figures extrapolated) fits libDaisy's {SMP_CYCLES} cycles", need * 1e9, None, T_S_V * 1e9,
              " ns", f"tS {T_S_V * 1e9:.0f} ns at {F_ADC_V / 1e6:.2f} MHz; the table's own RAIN max at 16 bits is "
              f"{RAIN_MAX_16:.0f} ohm (fastest sampling); rev Y clock tS {T_S_Y * 1e9:.0f} ns")

# the pot path: wiper (R/4 at mid) -> 74HC4051 Ron -> MUX_OUT (4051 common + both boards' copper + header +
# Seed pin) -> CADC; no series resistor
C_MUXNODE = CAPS["MUX_OUT"] + C_PIN
print(f"      MUX_OUT copper: {CAPINFO['MUX_OUT'][0]:.1f} mm, {CAPINFO['MUX_OUT'][1]} pads, {CAPINFO['MUX_OUT'][2]} vias, "
      f"{CAPINFO['MUX_OUT'][3]} header pin -> {CAPS['MUX_OUT'] * 1e12:.1f} pF + pin {C_PIN * 1e12:.0f} pF")


def pot_sys(r_thev, ron, c_com):
    S = Sys()
    S.v("src", "pot")
    S.r("src", "w", r_thev, "wiper")
    S.c("w", "0", C_SW_IN + 2e-12)
    S.r("w", "m", ron, "ron")
    S.c("m", "0", c_com + C_MUXNODE)
    S.sw("m", "cadc", RADC, "sample")
    S.c("cadc", "0", CADC)
    return S


R_WIPER = R_POT / 4
pot_rows = []
for ron, rname in ((RON_TYP, "typ"), (RON_MAX, "max (assumed)")):
    for c_com, cname in ((C_COM_TYP, "CCOM typ 25 pF"), (0.0, "CCOM 0 (lightest node)"), (C_COM_MAX, "130 pF max")):
        S = pot_sys(R_WIPER, ron, c_com)
        e = burst_error(S, T_S_MUX_V, T_CONV_MUX_V, dt_s=2e-9, dt_c=10e-9)
        ec = burst_error(S, T_S_MUX_V, T_CONV_MUX_V, carry=True, dt_s=2e-9, dt_c=10e-9)
        pot_rows.append((abs(e.mean()) / LSB, abs(ec.mean()) / LSB, rname, cname))
w = max(pot_rows)
# VERIFY 2026-11-13: what the firmware uses: libDaisy's 16-bit OVS_8 value (pots_adc.h float_value = value / 65536)
# into PotController's one-pole (lp 0.005 .. 0.01 per 4 kHz poll), which does not remove a systematic settling
# error; Plaits reads its pots at 12 bits (STM32F373, 239.5 cycles). The 16-bit criterion is kept; the detail
# gives the error in Plaits' 12-bit steps and in FREQUENCY cents (ui.cc: 96 semitones over the travel).
ck.within(f"D.sample_hold.pots: the pot burst behind B10k at mid (2.5k) + 74HC4051 Ron, no series resistor, settles CADC "
          f"to 1/2 LSB at 16 bit in the mux channel's {SMP_MUX} cycles (rev V clock, CADC 3.3 V off every conversion)",
          w[0], None, HALF_LSB, " LSB",
          f"worst Ron {w[2]}, {w[3]}; = {w[0] / 16:.2f} LSB at Plaits' 12 bits, {w[0] / 65536 * 96 * 100:.1f} cents "
          f"on FREQUENCY, a shift of the pot curve (not tracking); CADC kept between conversions {w[1]:.3f} LSB; all: " +
          "; ".join(f"Ron {a}, {b}: {x:.3f}/{y:.3f}" for x, y, a, b in pot_rows))
for bits in (16, PLAITS_POT_BITS):
    r_ain = R_WIPER + RON_MAX
    need = ts_table_extrapolated(bits, r_ain)
    ck.within(f"D.table183.pots_{bits}bit: table 183's minimum sampling time at RAIN = {r_ain:.0f} ohm (2.5k wiper + "
              f"Ron max, slow channel PA0, {bits} bit) fits the mux channel's {SMP_MUX} cycles", need * 1e9, None,
              T_S_MUX_V * 1e9, " ns",
              f"tS {T_S_MUX_V * 1e9:.0f} ns; with Ron typ {ts_table_extrapolated(bits, R_WIPER + RON_TYP) * 1e9:.0f} ns; "
              f"the table's RAIN max at {bits} bits is {RAIN_MAX_16 if bits == 16 else RAIN_MAX_12:.0f} ohm; "
              f"the table assumes 47 pF on the pin, MUX_OUT has {(C_COM_TYP + C_MUXNODE) * 1e12:.0f} pF typ")
# bom.md offers the CD4051B: TI SCHS047O rON at VDD 5 V: 470 typ, 1050 max (25 C), 1200 (85 C); 3.3 V is
# outside the table (VDD >= 3 V): assume 3x the 5 V maximum (not confirmed)
# (VERIFY 2026-11-13: SCHS047O rev May 2026 re-read: 5 V 470 / 1050 / 1200, 10 V 180 / 400 / 520 ohm; single supply
# 3 .. 20 V, "performance degrades for VDD < 3V". rON ~ 1 / (VDD - 1.9 V) through the 5 and 10 V rows gives x2.2
# at 3.3 V, about 2.6k max at 85 C: the 3.6k assumed here is on the high side, but 2.6k still leaves ~20 LSB)
BOM_MD = harness.text("docs", "bom.md")
if "CD4051B" in BOM_MD:
    S = pot_sys(R_WIPER, 3 * 1200.0, 30e-12)
    e = burst_error(S, T_S_MUX_V, T_CONV_MUX_V, dt_s=2e-9, dt_c=10e-9)
    ck.within("D.sample_hold.pots_CD4051B: with the CD4051B bom.md allows (Ron at 3.3 V assumed 3 x its 1.2k max at 5 V), "
              "the pot burst still settles to 1/2 LSB at 16 bit", abs(e.mean()) / LSB, None, HALF_LSB, " LSB",
              f"COS 30 pF typ (SCHS047O); first conversion {abs(e[0]) / LSB:.2f} LSB")

# mux address change: libDaisy writes S0..S2 in the ConvCplt interrupt, then restarts the scan; the mux is
# last, so the new address has eight bursts before its first sample
T_AVAIL_MUX = (N_CH - 1) * T_BURST_V
tau_m = (R_WIPER + RON_MAX) * (C_COM_MAX + C_MUXNODE + CADC)
t_need = T_ON_MAX + tau_m * math.log(VDDA / (HALF_LSB * LSB))
ck.within("D.mux_switch: 4051 turn-on (2.0 V max) + MUX_OUT's RC settling of a full-scale step to 1/2 LSB at 16 bit, "
          "10x inside the eight bursts before the mux is sampled", t_need * 1e6, None, T_AVAIL_MUX * 1e6 / 10, " us",
          f"tON {T_ON_MAX * 1e9:.0f} ns, tau {tau_m * 1e9:.0f} ns (2.5k + Ron {RON_MAX:.0f}, {(C_COM_MAX + C_MUXNODE + CADC) * 1e12:.0f} pF), "
          f"available {T_AVAIL_MUX * 1e6:.0f} us; hal_daisy.cc: 'the pot being read has a whole scan to settle'")
ck.check("D.mux_switch_comment: libDaisy (per/adc.cpp) moves the mux address in the ConvCplt callback and restarts "
         "the scan, and hal_daisy.cc puts the mux last, as the comment says",
         "libDaisy moves the mux address when a scan ends" in " ".join(HAL.split()) and RANKS[-1] == "MUX_OUT",
         "expected the comment and the mux last in the sequence")
T_POT = len(circuit.POTS) * T_SCAN_V          # libDaisy steps the mux by one channel per scan, 7 channels
print(f"      each pot is converted once per {len(circuit.POTS)} scans: every {T_POT * 1e3:.2f} ms "
      f"({1 / T_POT:.0f} Hz); the CVs every {T_SCAN_V * 1e6:.0f} us")

# ================================================================================ E. trigger timing
SETTINGS = harness.text("firmware", "src", "plaits", "settings.cc")
VOICE = harness.text("firmware", "vendor", "plaits", "dsp", "voice.cc")
VOICE_H = harness.text("firmware", "vendor", "plaits", "dsp", "voice.h")
CVADC = harness.text("firmware", "src", "plaits", "drivers", "cv_adc.cc")
m_sc = re.search(r"c\[CV_ADC_CHANNEL_TRIGGER\]\.scale = (-?[\d.]+)f", SETTINGS)
m_on = re.search(r"trigger_value > ([\d.]+)f", VOICE)
m_off = re.search(r"trigger_value < ([\d.]+)f", VOICE)
m_rf = re.search(r"\{ hal::ADC_TRIGGER, false, ([\d.]+)f, ([\d.]+)f", CVADC)
m_dl = re.search(r"const int kTriggerDelay = (\d+);", VOICE_H)
ck.check("E.sources_parsed: trigger scale (settings.cc), thresholds (voice.cc), Plaits' TRIG stage (cv_adc.cc), "
         "kTriggerDelay (voice.h)", all((m_sc, m_on, m_off, m_rf, m_dl)), "")
TRIG_SCALE = float(m_sc.group(1))
TRIG_ON, TRIG_OFF = float(m_on.group(1)), float(m_off.group(1))
P_RF, P_RREF = float(m_rf.group(1)), float(m_rf.group(2))
K_DELAY = int(m_dl.group(1))
UNITS_PER_V = -TRIG_SCALE * (P_RF / 100) * 2 / VDDA            # trigger_value per jack volt (Plaits' stage)
V_ON, V_OFF = TRIG_ON / UNITS_PER_V, TRIG_OFF / UNITS_PER_V
print(f"      trigger: {UNITS_PER_V:.4f} per jack volt -> on above {V_ON:.2f} V, off below {V_OFF:.2f} V; "
      f"delay line {K_DELAY - 1} blocks = {(K_DELAY - 1) * T_BLOCK * 1e3:.2f} ms (same on Plaits)")
s_tr = STAGES["TRIG"]
TAU_TRIG = V(s_tr["Rf"]) * V(s_tr["Cf"])
R_TRIG = RANKS.index(s_tr["adc"])
DELTA_READ = 2e-6           # s, from the audio interrupt to Convert() reading the DMA buffer (estimate)
PLAITS_SD_START = 10e-6     # s, Plaits starts its SDADC conversions at the end of Poll() (estimate)
PLAITS_SD_CONV = 60e-6      # s, an SDADC injected conversion at 6 MHz (estimate, not confirmed)


def trigger_mc(width, amp=5.0, n=20000, seed=1, t_scan=T_SCAN_V, t_burst=T_BURST_V, t_conv=T_CONV_V, t_s=T_S_V):
    """Latency (s, edge -> the poll whose reading crosses the threshold; NaN if never) for random edges and
    scan phases; the stage's RC, the 8-conversion average, the poll reading the latest completed burst."""
    rng = np.random.default_rng(seed)
    t0 = rng.uniform(5e-3, 6e-3, n)
    phi = rng.uniform(0, t_scan, n)
    lat = np.full(n, np.nan)
    j0 = np.floor((t0 - phi) / t_scan).astype(int) - 2
    polls0 = np.floor(t0 / T_BLOCK).astype(int)

    def y(t):
        a = np.clip(t - t0, 0, None)
        on = amp * (1 - np.exp(-a / TAU_TRIG))
        b = np.clip(t - t0 - width, 0, None)
        off_start = amp * (1 - np.exp(-width / TAU_TRIG))
        return np.where(t < t0 + width, on, off_start * np.exp(-b / TAU_TRIG))
    readings, comps = [], []
    for dj in range(0, 12):
        sj = phi + (j0 + dj) * t_scan
        acc = np.zeros(n)
        for i in range(OVS):
            acc += y(sj + R_TRIG * t_burst + i * t_conv + t_s)
        readings.append(acc / OVS * UNITS_PER_V)
        comps.append(sj + (R_TRIG + 1) * t_burst)
    readings, comps = np.array(readings), np.array(comps)
    for dn in range(0, 10):
        p = (polls0 + dn) * T_BLOCK + DELTA_READ
        done = comps <= p
        idx = np.where(done.any(axis=0), done.shape[0] - 1 - np.argmax(done[::-1], axis=0), -1)
        val = readings[np.clip(idx, 0, None), np.arange(n)]
        hit = (val > TRIG_ON) & np.isnan(lat) & (idx >= 0)
        lat[hit] = p[hit] - t0[hit]
    return lat


def plaits_latency(n=20000, seed=1):
    rng = np.random.default_rng(seed)
    t0 = rng.uniform(5e-3, 6e-3, n)
    k = np.ceil((t0 - PLAITS_SD_START - PLAITS_SD_CONV / 2) / T_BLOCK)       # first conversion after the edge
    return (k + 1) * T_BLOCK - t0


lat = trigger_mc(10e-3)
lat_p = plaits_latency()
jit = np.nanpercentile(lat, 99.9) - np.nanpercentile(lat, 0.1)
jit_p = lat_p.max() - lat_p.min()
extra = (K_DELAY - 1) * T_BLOCK + T_BLOCK
print(f"      TRIG edge -> detecting poll: Plaitsy {np.nanmin(lat) * 1e6:.0f}-{np.nanmax(lat) * 1e6:.0f} us (mean "
      f"{np.nanmean(lat) * 1e6:.0f}), Plaits {lat_p.min() * 1e6:.0f}-{lat_p.max() * 1e6:.0f} us (mean {lat_p.mean() * 1e6:.0f}); "
      f"both then add the {(K_DELAY - 1) * T_BLOCK * 1e3:.1f} ms delay line and one output block: total about "
      f"{(np.nanmean(lat) + extra) * 1e3:.2f} ms")
ck.within("E.trigger_jitter: TRIG edge-to-detection jitter (p-p) within two audio blocks", jit * 1e6, None, 2 * T_BLOCK * 1e6,
          " us", f"Plaits' own {jit_p * 1e6:.0f} us (one block: its conversion is locked to the block); Plaitsy adds the "
          f"free-running scan ({T_SCAN_V * 1e6:.0f} us)")
ck.within("E.trigger_latency: mean edge-to-detection latency within one block of Plaits'", np.nanmean(lat) * 1e6, None,
          (lat_p.mean() + T_BLOCK) * 1e6, " us", f"Plaits about {lat_p.mean() * 1e6:.0f} us (SDADC timing estimated)")
widths = [0.1e-3, 0.2e-3, 0.3e-3, 0.4e-3, 0.5e-3, 0.6e-3, 0.8e-3, 1e-3]
seen = []
for wd in widths:
    l = trigger_mc(wd, n=8000, seed=3)
    seen.append((wd, float(np.mean(~np.isnan(l)))))
w_all = min((wd for wd, f in seen if f == 1.0), default=float("inf"))
print("      share of 5 V trigger pulses seen, by width: " + ", ".join(f"{wd * 1e3:.1f} ms {f * 100:.1f} %" for wd, f in seen))
ck.within("E.trigger_min_pulse: the shortest 5 V pulse always detected is at most 1 ms (the shortest common Eurorack trigger)",
          w_all * 1e3, None, 1.0, " ms", f"Plaits needs about {T_BLOCK * 1e3:.2f} ms (one block); Plaitsy about one block "
          f"+ one scan ({(T_BLOCK + T_SCAN_V) * 1e3:.2f} ms)")
slope = 10.0 * V(s_tr["Rf"]) / V(s_tr["Rin"]) / TAU_TRIG
ck.within("E.trigger_slew: a 10 V edge through the 100p stage asks less than the TL074's minimum slew rate", slope / 1e6,
          None, SR_MIN / 1e6, " V/us", f"{10 * V(s_tr['Rf']) / V(s_tr['Rin']):.2f} V step, tau {TAU_TRIG * 1e6:.1f} us; "
          f"slew is irrelevant to the timing")
# the proposed fix for D's pot failures, priced here: a longer sampling time on the mux channel only
for cyc in (16.5, 32.5):
    t_s2 = cyc / F_ADC_V
    t_c2 = (cyc + T_SAR_HALF + N_BITS / 2) / F_ADC_V
    e = burst_error(pot_sys(R_WIPER, RON_MAX, C_COM_MAX), t_s2, t_c2, dt_s=2e-9, dt_c=10e-9)
    scan2 = T_SCAN_V + OVS * (cyc - SMP_MUX) / F_ADC_V
    print(f"      mux channel at {cyc} cycles (libDaisy SPEED_{int(cyc)}CYCLES_5 in InitMux): worst pot error "
          f"{abs(e.mean()) / LSB:.3f} LSB, scan {scan2 * 1e6:.0f} us (block {T_BLOCK * 1e6:.0f} us)")

# ================================================================================ F. the probe in time
DELTA_WRITE = 20e-6         # s, from the audio interrupt to DetectNormalization()'s probe write (estimate, upper)
m_task = re.search(r"ui_task_ = \(ui_task_ \+ 1\) % (\d+);", UI)
poll_src = UI[UI.index("void Ui::Poll()"):UI.index("void Ui::StartCalibration()")]
convert_first = poll_src.index("cv_adc_.Convert();") < poll_src.index("ui_task_ = (ui_task_ + 1)")
n_task = int(m_task.group(1)) if m_task else 0
ck.check("F.probe_schedule: ui.cc reads the ADC at the start of Poll() and runs DetectNormalization() every "
         f"{n_task}th poll (once per ms), writing the next probe bit after the comparison",
         m_task is not None and convert_first and n_task == 4 and
         UI.index("normalization_probe_.Write(") > UI.index("bool read_value = cv_adc_.value(channel)"),
         f"got every {n_task} polls, Convert() first: {convert_first}")
T_PROBE = n_task * T_BLOCK
T_AVAIL_PROBE = T_PROBE - DELTA_WRITE - T_SCAN_V - T_BURST_V
probe_rows = []
for k, s in STAGES.items():
    if s["probe_r"] is None:
        continue
    S = stage_sys(s, OP_OLD)
    G, Cm = S.mats()
    xdc = np.linalg.solve(G, S.b_of({"probe": VDDA}).real)
    final = xdc[S.nodes[s["adc"]]]
    sim = Tsim(S, {"probe": VDDA})
    x = np.zeros(S.size())
    x, tr1 = sim.run(x, 20e-6, 10e-9, record=S.nodes[s["adc"]])
    x, tr2 = sim.run(x, 980e-6, 0.25e-6, record=S.nodes[s["adc"]])
    t = np.concatenate([np.arange(1, len(tr1) + 1) * 10e-9, 20e-6 + np.arange(1, len(tr2) + 1) * 0.25e-6])
    v = np.concatenate([tr1, tr2])
    bad = np.nonzero(np.abs(v - final) > HALF_LSB * LSB)[0]
    t_set = t[bad[-1]] if len(bad) else 0.0
    probe_rows.append((k, t_set, final))
    ck.within(f"F.probe_settled.{k}: after a probe edge the {k} reading settles to 1/2 LSB (16 bit) within a third of the "
              f"time ui.cc leaves before comparing", t_set * 1e6, None, T_AVAIL_PROBE / 3 * 1e6, " us",
              f"{s['probe_r'].ref} {s['probe_r'].value} into {s['Rin'].value}, {s['Rf'].value} || {s['Cf'].value}; swing at the "
              f"ADC {abs(final) * 1e3:.0f} mV; available {T_AVAIL_PROBE * 1e6:.0f} us = "
              f"{n_task} blocks - write {DELTA_WRITE * 1e6:.0f} us - scan {T_SCAN_V * 1e6:.0f} us - burst {T_BURST_V * 1e6:.0f} us")
ck.check("F.probe_comment: hal_daisy.cc's claim 'the reading ... is always taken well after the probe last changed' "
         "holds: the oldest sample in the compared burst is more than half the probe period after the change",
         T_AVAIL_PROBE > T_PROBE / 2, f"expected > {T_PROBE / 2 * 1e6:.0f} us; got {T_AVAIL_PROBE * 1e6:.0f} us")


# the probe's crosstalk: PROBE_F's routed copper against the CV_*_F tracks on the faceplate
def seg_len(t):
    return math.hypot(t["b"][0] - t["a"][0], t["b"][1] - t["a"][1])


def _segs_cross(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return (orient(a, b, c) * orient(a, b, d) < 0) and (orient(c, d, a) * orient(c, d, b) < 0)


def coupling(board, net_a, nets_b, gnd, max_gap=3e-3, max_angle=10.0):
    """{net: [(overlap mm, edge gap mm, shielded)], crossings} of two nets' parallel runs on one layer."""
    runs, cross = collections.defaultdict(list), collections.Counter()
    ta_all = [t for t in board.tracks if t["net"] == net_a]
    tb_all = [t for t in board.tracks if t["net"] in nets_b]
    isl = [i for i in board.islands if i.net == gnd]
    for ta in ta_all:
        la = seg_len(ta)
        if la < 1e-6:
            continue
        ux, uy = (ta["b"][0] - ta["a"][0]) / la, (ta["b"][1] - ta["a"][1]) / la
        for tb in tb_all:
            if tb["layer"] != ta["layer"]:
                if _segs_cross(ta["a"], ta["b"], tb["a"], tb["b"]):
                    cross[tb["net"]] += 1
                continue
            lb = seg_len(tb)
            if lb < 1e-6:
                continue
            vx, vy = (tb["b"][0] - tb["a"][0]) / lb, (tb["b"][1] - tb["a"][1]) / lb
            if abs(ux * vy - uy * vx) > math.sin(math.radians(max_angle)):
                continue
            p = [((q[0] - ta["a"][0]) * ux + (q[1] - ta["a"][1]) * uy) for q in (tb["a"], tb["b"])]
            lo, hi = max(0.0, min(p)), min(la, max(p))
            if hi - lo <= 0.05:
                continue
            mid_t = (lo + hi) / 2
            pa = (ta["a"][0] + ux * mid_t, ta["a"][1] + uy * mid_t)
            # the point of tb nearest pa
            q = (tb["a"][0] + vx * ((pa[0] - tb["a"][0]) * vx + (pa[1] - tb["a"][1]) * vy),
                 tb["a"][1] + vy * ((pa[0] - tb["a"][0]) * vx + (pa[1] - tb["a"][1]) * vy))
            d = math.hypot(q[0] - pa[0], q[1] - pa[1])
            gap = d - (ta["w"] + tb["w"]) / 2
            if gap > max_gap * 1e3 or gap <= 0:
                continue
            midp = ((pa[0] + q[0]) / 2, (pa[1] + q[1]) / 2)
            shielded = any(i.layer == ta["layer"] and i.contains(midp) for i in isl)
            runs[tb["net"]].append((hi - lo, gap, shielded))
    return runs, cross


CV_F = [s["cv_f"] for s in STAGES.values()]
runs, crosses = coupling(ROUTED.face, "PROBE_F", CV_F, "GND_F")
C_CROSS = 8.854e-12 * ER_FR4 * (W_TRACK + H_FR4 / 2) ** 2 / H_FR4     # a crossing on the other layer (rough)
SHIELD = 0.25               # a GND_F pour strip between the two tracks: a quarter of the open coupling (rough)
CM = {}
for k, s in STAGES.items():
    n = s["cv_f"]
    open_c = sum(L * coupled_mutual_pf_per_mm(g * 1e-3) for L, g, sh in runs.get(n, []) if not sh) * 1e-12
    sh_c = sum(L * coupled_mutual_pf_per_mm(g * 1e-3) for L, g, sh in runs.get(n, []) if sh) * 1e-12 * SHIELD
    CM[k] = open_c + sh_c + crosses.get(n, 0) * C_CROSS
    if runs.get(n) or crosses.get(n):
        print(f"      PROBE_F -> {n:12s}: " + ", ".join(f"{L:.1f} mm at {g:.2f} mm{' (pour between)' if sh else ''}"
                                                      for L, g, sh in runs.get(n, [])) +
              f"; {crosses.get(n, 0)} crossings -> about {CM[k] * 1e15:.0f} fF")
print(f"      PROBE_F: {sum(seg_len(t) for t in ROUTED.face.tracks if t['net'] == 'PROBE_F'):.1f} mm on the faceplate "
      f"(the brief's 86 mm); coupled microstrip Cm at 0.3 mm gap {coupled_mutual_pf_per_mm(0.3e-3) * 1e3:.1f} fF/mm, "
      f"1 mm {coupled_mutual_pf_per_mm(1e-3) * 1e3:.1f} fF/mm; crossing {C_CROSS * 1e15:.0f} fF")


def glitch(s, cm, r_src):
    """Worst 8-conversion average at the ADC (V) after a 3.3 V probe edge coupled through cm into a patched CV."""
    S = stage_sys(s, OP_OLD, src="patched", r_src=r_src, c_cv_coupling=cm)
    sim = Tsim(S, {"xt": VDDA})
    x = np.zeros(S.size())
    # the coupling cap: the edge is a jump of the source, so start with the source's node at 3.3 V
    x[S.nodes["xt_src"]] = 0.0
    dt = 20e-9
    x, tr = sim.run(x, 150e-6, dt, record=S.nodes[s["adc"]])
    step = max(1, int(round(T_CONV_V / dt)))
    best = 0.0
    for off in range(0, len(tr) - OVS * step, 5):
        best = max(best, abs(tr[off:off + OVS * step:step].mean()))
    return best, float(np.max(np.abs(tr)))


for k, s in STAGES.items():
    if s["probe_r"] is not None or CM[k] == 0:
        continue
    g_hi, pk_hi = glitch(s, CM[k], R_SRC_HIGHZ)
    g_lo, pk_lo = glitch(s, CM[k], R_SRC_PATCH)
    extra = f"; {g_hi / (V(s['Rf']) / V(s['Rin'])) * 1200:.2f} cents" if k == "VOCT" else ""
    ck.within(f"F.probe_crosstalk.{k}: the probe edge coupled from PROBE_F ({CM[k] * 1e15:.0f} fF) into a patched {k} "
              f"(10k source) moves a reading by under 1/2 LSB", g_hi / LSB, None, HALF_LSB, " LSB",
              f"peak at the pin {pk_hi / LSB:.2f} LSB; from a 1k source {g_lo / LSB:.3f} LSB{extra}; rough: coupled-"
              f"microstrip formula, pour between counted as x{SHIELD}, crossings {C_CROSS * 1e15:.0f} fF each")

# ================================================================================ G. noise
_r = (EN_1K / EN_10K) ** 2
FC_1F = (_r - 1) / (1 / 1e3 - _r / 1e4)
ENW = EN_10K / math.sqrt(1 + FC_1F / 1e4)
F_SH = 1 / (2 * math.pi * RADC * CADC)
FREQS = np.concatenate([np.logspace(0, 4, 160), np.linspace(1e4 + 50, 4e6, 4000)])


def en(f):
    return ENW * np.sqrt(1 + FC_1F / f)


def noise_at(S, out):
    """Output noise (V rms) of one burst-average reading at node out, and the share by source class."""
    o = S.nodes[out]
    N, nv = len(S.nodes), len(S.V)
    G, Cm = S.mats()
    psd = collections.defaultdict(lambda: np.zeros(len(FREQS)))
    for i, f in enumerate(FREQS):
        Y = G + 2j * math.pi * f * Cm
        e = np.zeros(Y.shape[0])
        e[o] = 1
        y = np.linalg.solve(Y.T, e)
        yv = lambda n: y[n] if n >= 0 else 0
        w = h_burst(f) ** 2 / (1 + (f / F_SH) ** 2)
        for a, b, val, tag in S.R:
            if tag in ("ZO", "pin", "lug"):
                continue
            psd["resistors"][i] += abs(yv(a) - yv(b)) ** 2 * 4 * KB * T_K / val * w
        for j, (name, p, m, oo, model) in enumerate(S.ops):
            x1 = N + nv + 3 * j + 1
            psd["op-amp en"][i] += abs(y[x1]) ** 2 * en(f) ** 2 * w
            psd["op-amp in"][i] += (abs(yv(p)) ** 2 + abs(yv(m)) ** 2) * IN_NOISE ** 2 * w
    parts = {kk: float(np.sqrt(np.trapezoid(v, FREQS))) for kk, v in psd.items()}
    return math.sqrt(sum(v ** 2 for v in parts.values())), parts


SIG_CONV = VDDA / (2 * math.sqrt(2)) / 10 ** (SNR_ADC / 20)       # one conversion, from the SNR
SIG_READ = SIG_CONV / math.sqrt(OVS)
print(f"      ADC's own noise: SNR {SNR_ADC} dB -> {SIG_CONV * 1e6:.0f} uV = {SIG_CONV / LSB:.2f} LSB rms per conversion, "
      f"{SIG_READ / LSB:.2f} LSB per OVS_{OVS} reading (ENOB {ENOB_ADC} bits); TL074 en {ENW * 1e9:.1f} nV white, "
      f"1/f corner {FC_1F:.0f} Hz")
for k, s in STAGES.items():
    src = "patched" if s["probe_r"] is None else "unpatched"
    S = stage_sys(s, OP_NEW, src=src, r_src=R_SRC_PATCH, cadc=False)
    S.c(s["adc"], "0", CADC)
    vn, parts = noise_at(S, s["adc"])
    detail = (f"{vn * 1e6:.1f} uV rms ({', '.join(f'{a} {b * 1e6:.1f}' for a, b in parts.items())} uV); "
              f"ADC {SIG_READ / LSB:.2f} LSB per reading")
    ck.within(f"G.noise.{k}: front-end noise per reading at the ADC pin stays under the ADC's own noise", vn / LSB, None,
              SIG_READ / LSB, " LSB", detail)
    if k == "VOCT":
        g = V(s["Rf"]) / V(s["Rin"])
        tot = math.sqrt(vn ** 2 + SIG_READ ** 2)
        ck.within(f"G.noise_cents.{k}: V/OCT reading noise (front end + ADC) at the jack, 1 V/oct", tot / g * 1200, None,
                  CENTS_MAX, " cents rms", f"front end {vn / g * 1200:.3f}, ADC {SIG_READ / g * 1200:.3f} cents; one "
                  f"16-bit LSB is {LSB / g * 1200:.3f} cents; ui.cc smooths the note further (ONE_POLE 0.7)")
# the pot path: Johnson noise of 2.5k + Ron into MUX_OUT's capacitance (kT/C) and the 4051
c_pot = C_COM_TYP + C_MUXNODE
vn_pot = math.sqrt(KB * T_K / c_pot) / math.sqrt(OVS)
ck.within("G.noise.pots: the pot path's kT/C noise on MUX_OUT per reading stays under the ADC's own noise", vn_pot / LSB,
          None, SIG_READ / LSB, " LSB", f"sqrt(kT/C) with C = {c_pot * 1e12:.0f} pF, averaged over {OVS} (the RC of "
          f"{(R_WIPER + RON_TYP) * c_pot * 1e9:.0f} ns is far shorter than the {T_CONV_V * 1e6:.1f} us conversion spacing)")

# a patched normalized input: the open jack switch couples the probe-driven lug into the tip. The Thonkiconn's
# open-contact capacitance is not in any datasheet read here: 1 pF assumed (rough), print only.
s = STAGES["TIMBRE"]
g1, _ = glitch(s, 1e-12, R_SRC_PATCH)
g2, _ = glitch(s, 1e-12, R_SRC_HIGHZ)
print(f"      a patched normalized input (TIMBRE), probe edge through an assumed 1 pF lug-to-tip: {g1 / LSB:.2f} LSB from "
      f"a 1k source, {g2 / LSB:.2f} LSB from 10k (worst 8-conversion average)")

# ================================================================================ H. LEDs, 3V3D, ground
LED_PARTS = [p for p in FACE if p.kind == "HC595"]
three3d = {"3V3D", "3V3D_F"}
three3a = {"3V3A", "3V3A_F"}
both = [p.ref for p in MAIN + FACE if three3d & set(p.nets.values()) and three3a & set(p.nets.values())
        and p.kind not in ("SEED",) and not p.ref.startswith(("H", "HF"))]
ck.check("H.rails_apart: no part takes both 3V3D and 3V3A; the 74HC595s are on 3V3D_F, the mux, pots and bias "
         "dividers on 3V3A", not both and all("3V3D_F" in p.nets.values() for p in LED_PARTS) and
         all("3V3A_F" in p.nets.values() for p in FACE if p.kind in ("MUX", "POT")) and
         all("3V3A" in s["Rb_up"].nets.values() for s in STAGES.values()), f"parts on both: {both}")
gd = set(n for p in FACE for n in p.nets.values() if n == "GND_D_F")
gf_parts = {p.ref for p in FACE if "GND_F" in p.nets.values()}
gd_parts = {p.ref for p in FACE if "GND_D_F" in p.nets.values()}
ck.check("H.grounds_apart: on the faceplate the LED / button / 595 ground (GND_D_F) shares no part with the jack, pot "
         "and mux ground (GND_F); they meet only on the main board (H3 pin 2, H2 pin 2)",
         not ({r for r in gf_parts & gd_parts if not r.startswith("HF")}) and bool(gd),
         f"parts on both: {sorted(gf_parts & gd_parts)}")
I_STEP = N_LED_LINES * I_LED
m_pwm = re.search(r"int pwm_counter = pwm_counter_ & (\d+);", UI)
pwm_steps = int(m_pwm.group(1)) + 1 if m_pwm else 0
print(f"      LED frame: UpdateLEDs() once per {n_task} polls ({T_PROBE * 1e3:.1f} ms), {pwm_steps}-step PWM -> "
      f"{1 / (pwm_steps * T_PROBE):.1f} Hz; all {N_LED_LINES} lines switching together: {I_STEP * 1e3:.0f} mA step on "
      f"3V3D (design.md: about {I_LED * 1e3:.0f} mA per colour); Service() shifts it out from the main loop, "
      f"asynchronous to the ADC")


def pip(poly, px, py):
    """Even-odd point-in-polygon for arrays of points (vectorized over points, looped over edges)."""
    xs, ys = np.array([p[0] for p in poly]), np.array([p[1] for p in poly])
    inside = np.zeros(px.shape, bool)
    j = len(xs) - 1
    for i in range(len(xs)):
        xi, yi, xj, yj = xs[i], ys[i], xs[j], ys[j]
        cond = (yi > py) != (yj > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = (xj - xi) * (py - yi) / (yj - yi) + xi
        inside ^= cond & (px < xc)
        j = i
    return inside


def ground_drop(board, net, i_in_pads, ground_pads, probe_pads, dx=0.4, current=1.0):
    """Potential (V) at probe_pads with `current` entering at i_in_pads and leaving at ground_pads (held at 0 V,
    the breakout's own GND plane), through the routed pour on both layers, the pads and the vias."""
    x1, y1, x2, y2 = board.outline
    xs = np.arange(x1 + dx / 2, x2, dx)
    ys = np.arange(y1 + dx / 2, y2, dx)
    X, Y = np.meshgrid(xs, ys)
    masks = {}
    for L in (1, 2):
        m = np.zeros(X.shape, bool)
        for isl in board.islands:
            if isl.net != net or isl.layer != L:
                continue
            ox = [p[0] for p in isl.outline]
            oy = [p[1] for p in isl.outline]
            box = (X >= min(ox)) & (X <= max(ox)) & (Y >= min(oy)) & (Y <= max(oy))
            inside = np.zeros(X.shape, bool)
            inside[box] = pip(isl.outline, X[box], Y[box])
            for h in isl.holes:
                hx = [p[0] for p in h]
                hy = [p[1] for p in h]
                hb = inside & (X >= min(hx)) & (X <= max(hx)) & (Y >= min(hy)) & (Y <= max(hy))
                if hb.any():
                    inside[hb] &= ~pip(h, X[hb], Y[hb])
            m |= inside
        for a, b, layer, n in board.spokes:
            if n != net or layer != L:
                continue
            for t in np.linspace(0, 1, 12):
                px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                ix, iy = int((px - x1) / dx), int((py - y1) / dx)
                if 0 <= iy < X.shape[0] and 0 <= ix < X.shape[1]:
                    m[iy, ix] = True
        masks[L] = m
    vert = []                                   # (cell index iy, ix, conductance) for the layer-to-layer joins
    pad_cells = {}
    for p in board.pads:
        if p.net != net:
            continue
        near = (np.abs(X - p.x) <= p.r + dx) & (np.abs(Y - p.y) <= p.r + dx)
        cells = [(iy, ix) for iy, ix in zip(*np.nonzero(near)) if p.d_point((X[iy, ix], Y[iy, ix])) <= dx / 2]
        if not cells:
            cells = [(int((p.y - y1) / dx), int((p.x - x1) / dx))]
        pad_cells[(p.ref, p.num)] = cells
        for iy, ix in cells:
            masks[1][iy, ix] = masks[2][iy, ix] = True
            vert.append((iy, ix, 1 / 1e-3 / len(cells)))        # a plated pad: about 1 mOhm barrel
    r_via = RHO_CU * 1.6e-3 / (math.pi * 0.3e-3 * 25e-6)       # 0.3 mm drill, 25 um plating
    for v in board.vias:
        if v["net"] != net:
            continue
        iy, ix = int((v["c"][1] - y1) / dx), int((v["c"][0] - x1) / dx)
        masks[1][iy, ix] = masks[2][iy, ix] = True
        vert.append((iy, ix, 1 / r_via))
    ny, nx = X.shape
    idx = -np.ones((2, ny, nx), int)
    count = 0
    for li, L in enumerate((1, 2)):
        k = np.nonzero(masks[L].ravel())[0]
        idx[li].ravel()[k] = np.arange(count, count + len(k))
        count += len(k)
    gs = CU_T / RHO_CU                          # sheet conductance, S per square
    ea, eb, eg = [], [], []
    for li in (0, 1):
        a, b = idx[li][:, :-1], idx[li][:, 1:]
        ok = (a >= 0) & (b >= 0)
        ea.append(a[ok]); eb.append(b[ok]); eg.append(np.full(ok.sum(), gs))
        a, b = idx[li][:-1, :], idx[li][1:, :]
        ok = (a >= 0) & (b >= 0)
        ea.append(a[ok]); eb.append(b[ok]); eg.append(np.full(ok.sum(), gs))
    for iy, ix, g in vert:
        ea.append(np.array([idx[0][iy, ix]])); eb.append(np.array([idx[1][iy, ix]])); eg.append(np.array([g]))
    ea, eb, eg = np.concatenate(ea), np.concatenate(eb), np.concatenate(eg)
    fixed = np.zeros(count, bool)
    for key in ground_pads:
        for iy, ix in pad_cells.get(key, []):
            fixed[idx[0][iy, ix]] = fixed[idx[1][iy, ix]] = True
    rhs = np.zeros(count)
    cells = [c for key in i_in_pads for c in pad_cells.get(key, [])]
    for iy, ix in cells:
        rhs[idx[0][iy, ix]] += current / len(cells) / 2
        rhs[idx[1][iy, ix]] += current / len(cells) / 2
    diag = np.bincount(ea, eg, count) + np.bincount(eb, eg, count) + 1e-9 * gs

    def lap(v):
        d = eg * (v[ea] - v[eb])
        out = np.bincount(ea, d, count) - np.bincount(eb, d, count) + 1e-9 * gs * v
        out[fixed] = v[fixed]
        return out
    b = rhs.copy()
    b[fixed] = 0.0
    dinv = np.where(fixed, 1.0, 1 / diag)
    v = np.zeros(count)
    r = b - lap(v)
    z = dinv * r
    p = z.copy()
    rz = r @ z
    for it in range(30000):
        Ap = lap(p)
        alpha = rz / (p @ Ap)
        v += alpha * p
        r -= alpha * Ap
        if np.sqrt(r @ r) < 1e-12 * max(np.sqrt(b @ b), 1e-30):
            break
        z = dinv * r
        rz2 = r @ z
        p = z + rz2 / rz * p
        rz = rz2
    out = {}
    for key in probe_pads:
        cs = pad_cells.get(key, [])
        out[key] = float(np.mean([v[idx[0][iy, ix]] for iy, ix in cs])) if cs else float("nan")
    return out, it, count


MB = ROUTED.main
u2_gnd = [("U2", num) for num, pad in MB.parts["U2"]["pads"].items() if pad.net == "GND"]
h3_gnd = [("H3", num) for num, pad in MB.parts["H3"]["pads"].items() if pad.net == "GND"]
h2_gnd = [("H2", num) for num, pad in MB.parts["H2"]["pads"].items() if pad.net == "GND"]
sa, sv = STAGES["MODEL"], STAGES["VOCT"]
gpad = lambda p: (p.ref, next(k for k, n in p.nets.items() if n == "GND"))
probes = h2_gnd + [gpad(sa["Rb_dn"]), gpad(sa["Cb"]), gpad(sv["Rb_dn"]), gpad(sv["Cb"])]
vd, iters, ncells = ground_drop(MB, "GND", h3_gnd, u2_gnd, probes, current=I_STEP)
print(f"      MB GND pour model: {ncells} cells (0.4 mm, both layers), {iters} CG iterations; {I_STEP * 1e3:.0f} mA in at "
      f"{h3_gnd[0][0]}.{h3_gnd[0][1]}, out at the breakout's {len(u2_gnd)} GND pins: " +
      ", ".join(f"{a}.{b} {v * 1e6:.1f} uV" for (a, b), v in vd.items()))


def led_error(s, v_sleeve, v_div, v_cap):
    """Reading change (V at the ADC) for ground offsets at the sleeves (via H2), the divider's and the bias
    capacitor's ground ends: the larger of the slow (divider) and the fast (capacitor) case."""
    g = V(s["Rf"]) / V(s["Rin"])
    k_up = V(s["Rb_up"]) / (V(s["Rb_up"]) + V(s["Rb_dn"]))
    slow = (1 + g) * k_up * v_div - g * v_sleeve
    fast = (1 + g) * v_cap - g * v_sleeve
    return max(abs(slow), abs(fast))


v_sl = vd[h2_gnd[0]]
for k, s in (("MODEL", sa), ("VOCT", sv)):
    e = led_error(s, v_sl, vd[gpad(s["Rb_dn"])], vd[gpad(s["Cb"])])
    extra = (f"; {e / (V(s['Rf']) / V(s['Rin'])) * 1200:.3f} cents" if k == "VOCT" else "")
    ck.within(f"H.led_ground.{k}: the {I_STEP * 1e3:.0f} mA LED step's drop in the main board's GND pour moves a "
              f"{'wide-channel' if k == 'MODEL' else 'V/OCT'} reading by under 1/2 LSB", e / LSB, None, HALF_LSB, " LSB",
              f"sleeves (H2.2) {v_sl * 1e6:.1f} uV, {s['Rb_dn'].ref} {vd[gpad(s['Rb_dn'])] * 1e6:.1f} uV, {s['Cb'].ref} "
              f"{vd[gpad(s['Cb'])] * 1e6:.1f} uV re the breakout's GND{extra}; rough: resistive sheet model, 1 oz, "
              f"no inductance, the breakout's plane taken as ideal")
# the other path, through the Seed: 3V3A (= VREF+) is not 3V3D, but both come from the Seed's own regulator.
# A step on 3V3A is not ratiometric for the jack term: reading = (1 + g) k - g V_jack / VDDA.
g = V(sv["Rf"]) / V(sv["Rin"])
sens = g * 7.0 / VDDA ** 2 * VDDA / g * 1200 * 1e-3       # cents per mV of 3V3A at 7 V on V/OCT
print(f"      3V3A sensitivity (not checked: the Seed's regulator and 3V3A filter were not read): V/OCT at 7 V moves "
      f"{sens:.2f} cents per mV of 3V3A, a wide channel at 10 V {0.13 * 10 / VDDA ** 2 * 1e-3 / LSB:.1f} LSB per mV; "
      f"the LED step's load regulation on 3V3D reaches 3V3A through the Seed's filter")

ck.done()
