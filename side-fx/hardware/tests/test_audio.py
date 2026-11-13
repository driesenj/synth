"""audio: Side FXy's stereo audio path through the breakout's op-amp stages (Rob Heel's seed_power_opamps).

The path: IN 1 / IN 2 jacks (faceplate; IN 2's switch lug normalled to IN1_F, IN 1's to GND_F) -> H1 / HF1 ->
the breakout's J5 (AIN1, GND, AIN2, GND) -> its input stages (U2, TL074CPWR) -> the Seed's codec inputs (pins
16 / 17) -> codec -> Seed pins 18 / 19 -> its output stages (U5, TL074CPWR) -> J4 (AOUT1, GND, AOUT2, GND) -> H1 ->
OUT 1 / OUT 2 (switch lugs open). Side FXy adds no audio parts of its own; the circuit is the breakout's, which
publishes no schematic. It was reconstructed outside the suite from the downloaded Gerbers and drill files (a
raster connectivity parse of the top and bottom copper joined at the drills); the top silkscreen gave the
designators and the breakout's BOM the values. The Daisy Patch Rev 8 schematic, which the breakout's README names
as its reference, is the topology expected. Each constant says where it comes from: COPPER (read off the
breakout's copper), SILK + BOM, PATCH (the Patch Rev 8 schematic), a datasheet, or "assumed".

What it checks
  A. the reconstruction: each stage against the Patch Rev 8 and the breakout's BOM; circuit.py's J4 / J5 nets and
     Seed pins 16-19; the routed U5 footprint's audio header pins against the breakout's copper (distances to
     Seed pins 1, 20, 21, 40, so a J4 / J5 swap or a header one pin off shows);
  B. levels, for each 40-pin Seed codec (Seed 1.1 = Rev5 WM8731, Seed 1.2 = Rev7 PCM3060): gain jack -> codec,
     the jack level at the codec's full scale, a 10 V p-p and a hot 20 V p-p input (which clips first, op-amp or
     codec), the codec input's absolute maximum; OUT at codec full scale, Eurorack's 10 V p-p, the firmware's soft
     limiter against the output stage's clip, the firmware README's "OUT should equal IN";
  C. headroom on the real rails (+-12 V through the breakout's B5819W), the TL074's input range, the codec pins;
  D. impedances: each input, IN 1 with IN 2 normalled, the 1k output resistors into 10k-100k, a shorted output;
  E. DC offset at OUT 1 / OUT 2 (TL074 Vos / Ib through each stage's DC gain, with the Seed's 47k behind its output
     cap; the codec's DC blocked);
  F. frequency response 20 Hz - 20 kHz of the input path, the output path and the whole path (the Seed's coupling
     caps and the ADC's digital high-pass included), the low end on its own, the codecs' passband against 20 kHz at
     the firmware's sample rate; the anti-alias and image attenuation the stages give;
  G. phase margin of all eight stages (TL074 GBW 5.25 / 3 MHz, input capacitance, the stage's R / C, its load);
  H. polarity of the whole path and the firmware's OUT POLARITY default;
  I. normalling: a mono patch into IN 1 reaches both channels alike; an unplugged IN 1 is grounded;
  J. the audio return: jack sleeves on GND_F, GND_F to the main board's GND through header GND pins, GND_F and
     GND_D_F apart on the faceplate, the breakout's audio GND pins on the main board's GND (routed copper);
  K. design.md's and the READMEs' audio claims.

Not modelled: the codecs' decimation / interpolation filter ripple (+-0.05 dB, inside the passband checked in F),
noise and gain error, ground and supply crosstalk on the breakout, the TL074's distortion, the Seed's analog front end
beyond the impedances and coupling given in the constants, the Rev4 (AK4556) and Seed 3 (TAC5242) codecs.
Verified 2026-11-13 by an independent pass (vector re-trace of the breakout's Gerbers, the Seed v1.0.5 schematic):
the [verifier] comments mark what changed.

Run from side-fx/hardware/tests:  python test_audio.py
"""
import math
import os
import re

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # small matrices: BLAS threads only cost time
import numpy as np

import harness

ck = harness.Checks("audio")
circuit = harness.load("circuit")
db = harness.db

# ============================================================================================== constants
# ---- the breakout's audio stages -------------------------------------------------------------------------
# Source: github.com/rob-scape/daisy-seed-breakout-boards, folder daisy-seed-dcdc-opamps: Gerber_TopLayer.GTL,
# Gerber_BottomLayer.GBL, Drill_PTH_Through.DRL, Drill_PTH_Through_Via.DRL, Gerber_TopSilkscreenLayer.GTO,
# Gerber_BottomSilkscreenLayer.GBO (EasyEDA v6.5.51, 2025-08-29) and BOM.csv (2025-08-29).
# COPPER facts (each read off the parsed copper, not assumed):
#   - two TL074CPWR: U2 (its sections' outputs reach Seed pins 16 / 17 through one 0603 each) and U5 (Seed pins
#     18 / 19 reach its inverting inputs through one 0603 each);
#   - pin 4 of both on +12 V after D2 (B5819W from the power header's +12 V pins), pin 11 on -12 V after D3;
#   - every non-inverting input (pins 3, 5, 10, 12) on GND: all eight sections are inverting stages;
#   - each section: two 0603 in parallel from output to inverting input (Rf || Cf), one 0603 from the previous node
#     into the inverting input (Rin); the second stage of each path drives its Seed pin or J4 through one 0603;
#   - Seed pin numbering: pins 20 (AGND) and 40 (DGND) on GND, pin 39 (VIN) on the DC/DC's +5 V output;
#   - the bottom silkscreen names the headers by function: "A IN 1, GND, A IN 2, GND" beside Seed pin 1,
#     "A OUT 1, GND, A OUT 2, GND" beside Seed pin 40 (no J4 / J5 designators printed).
BREAKOUT_BOM = {  # designator -> value, BOM.csv 2025-08-29 (0603WAF 1 % thick film, Samsung CL10C C0G 5 %)
    **{r: 100e3 for r in "R1 R3 R4 R6 R8 R9 R11 R14 R18 R22 R24 R26".split()},
    **{r: 10e3 for r in "R2 R7 R15 R25".split()},
    **{r: 1e3 for r in "R5 R10 R21 R27".split()},
    **{c: 47e-12 for c in "C1 C5 C10 C11 C16 C17".split()},
    **{c: 560e-12 for c in "C2 C6".split()},
    **{c: 100e-9 for c in "C3 C4 C13 C15".split()},
}
R_TOL = 0.01            # 0603WAF1003T5E etc.: F = 1 %
C_TOL = 0.05            # CL10C470JB8NNNC / CL10C561JB8NNNC: J = 5 %, C0G
# Each stage (section, Rin, Rf, Cf), then the series resistor: COPPER for where each part connects, SILK for
# which designator sits there (read off the top silkscreen beside each 0603).
PATH_IN = {             # jack side -> codec side
    1: dict(hdr="J5-1", stages=[("U2A", "R3", "R1", "C1"), ("U2B", "R4", "R2", "C2")], rs="R5", seed="16"),
    2: dict(hdr="J5-3", stages=[("U2C", "R8", "R6", "C5"), ("U2D", "R9", "R7", "C6")], rs="R10", seed="17"),
}
PATH_OUT = {            # codec side -> jack side
    1: dict(seed="18", stages=[("U5A", "R15", "R11", "C10"), ("U5B", "R18", "R14", "C11")], rs="R21", hdr="J4-1"),
    2: dict(seed="19", stages=[("U5C", "R25", "R22", "C16"), ("U5D", "R26", "R24", "C17")], rs="R27", hdr="J4-3"),
}
# PATCH: ES_Daisy_Patch_Rev8 (3/13/25), sheet 3 "Audio I/O", the Seed-codec path: in R55 100K, R56 100K || C46 47PF
# (U4A), R73 100K, R74 10K || C48 560PF (U4D), R82 1K to INT_AUDIO_IN_L; out R102 10K, R99 100K || C52 47PF (U11A),
# R101 100K, R66 100K || C27 47PF (U11D), R67 1K to AUDIO_OUT_1; + inputs on GND. Per stage (Rin, Rf, Cf), then Rs.
PATCH_IN = [(100e3, 100e3, 47e-12), (100e3, 10e3, 560e-12)], 1e3
PATCH_OUT = [(10e3, 100e3, 47e-12), (100e3, 100e3, 47e-12)], 1e3
# The header pins in the breakout's Gerber frame (top view, mm), COPPER (pad flashes and PTH drills):
BREAKOUT_XY = {
    "1": (85.09, -17.02), "20": (36.83, -17.02), "21": (36.83, -1.78), "40": (85.09, -1.78),
    "J5-1": (95.25, -17.02), "J5-2": (92.71, -17.02), "J5-3": (90.17, -17.02), "J5-4": (87.63, -17.02),
    "J4-1": (95.25, -1.78), "J4-2": (92.71, -1.78), "J4-3": (90.17, -1.78), "J4-4": (87.63, -1.78),
}
BREAKOUT_NET = {"J5-1": "AIN1 (-> U2A Rin R3)", "J5-3": "AIN2 (-> U2C Rin R8)", "J4-1": "AOUT1 (<- U5B via R21)",
                "J4-3": "AOUT2 (<- U5D via R27)", "J5-2": "GND", "J5-4": "GND", "J4-2": "GND", "J4-4": "GND"}

# ---- the Seed's codecs (the breakout takes the 40-pin Seed: Seed 1.1 = Rev5 or Seed 1.2 = Rev7; the Seed2 DFM is
# another footprint). libDaisy daisy_seed.h BoardVersion: Rev4 AK4556 (2020, not checked), Seed 1.1 (Rev5) WM8731,
# Seed 1.2 (Rev7) PCM3060. V p-p at the Seed pin.
# Rev5: Daisy Seed datasheet v1.0.5 (25 Jan 2023, "updated schematic to Rev5"): inputs "AC coupled ... approx.
#   1Vrms" (Table 1 note), outputs "0dBFs @ 1Vrms" (Table 2, pins 18 / 19), input impedance 30k typ (Fig. 1.2),
#   output impedance 100R (Fig. 1.7). WM8731 (Wolfson/Cirrus PD Rev 4.9, Oct 2012, AVDD 3.3 V, fs 48 kHz, 25 C):
#   ADC full scale 1.0 Vrms x AVDD/3.3 (line in, 0 dB gain), line input resistance 20k min / 30k typ; line out
#   0 dBFS 1.0 x AVDD/3.3 Vrms. The Seed's AVDD is +3V3_A (schematic 4 of 4).
#   [verifier 2026-11-13] Coupling read off the datasheet's schematic 4 of 4 (an image; extracted and read): input
#   AUDIO_IN_L -> R24 0R -> C33 2.2UF -> CODEC_LIN (C35 DNI); output CODEC_LOUT -> C64 2.2UF -> R29 47K to AGND ->
#   R30 100R -> AUDIO_OUT_L (right: R26 / C34, C65 / R28 / R31). The writer had assumed 4.7 uF both ways and no
#   resistor to ground; now 2.2 uF and the 47k (r_gnd) behind the output cap, in the order the schematic draws.
# Rev7: TI PCM3060 SLAS533B (Mar 2008), at VCC = 5 V: ADC full-scale input 0.6 VCC p-p typ, input impedance 10k
#   typ; DAC single-ended output 0.8 VCC p-p typ; gain error ADC +-2 % typ / +-8 % FSR max, DAC +-2 / +-6 %.
#   On the Seed: VCC "from a 4v5 LDO on the seed" (Electrosmith staff, shensley, 10 Mar 2026), a series resistor
#   on each input "for better gain matching" (same post); its value 3.6k and the 4.7 uF input caps are a user's
#   reading of the schematic in Seed datasheet v1.1.2 (kasettli, Nov 2024), both in community.daisy.audio thread
#   5987 "Seed audio input specs on data sheet (Rev. 7)": community figures, not confirmed. The Rev7 output network
#   is published nowhere found (the public Rev7 schematic is "a reduced schematic", staff, Feb 2024): assumed to be
#   Rev5's (2.2 uF, 47k to AGND, 100R; the smaller cap is the conservative choice for the low end). Not confirmed.
# Not covered: Rev4 (AK4556) and the Daisy Seed 3 (TAC5242), which libDaisy v9.0.0's CheckBoardVersion() also
#   detects as pin-compatible 40-pin Seeds.
PCM_VCC = 4.5
CODECS = {
    "Rev5 WM8731": dict(fs_in=2 * math.sqrt(2), r_ser=0.0, z_in=30e3, c_in=2.2e-6, fs_out=2 * math.sqrt(2),
                        z_out=100.0, c_out=2.2e-6, r_gnd=47e3, hpf=3.7),
    "Rev7 PCM3060": dict(fs_in=0.6 * PCM_VCC * (3.6e3 + 10e3) / 10e3, r_ser=3.6e3, z_in=10e3, c_in=4.7e-6,
                         fs_out=0.8 * PCM_VCC, z_out=100.0, c_out=2.2e-6, r_gnd=47e3, hpf=0.019 * 48e3 / 1000),
}
# hpf: the ADC's digital high-pass, -3 dB (Hz) at fs = 48 kHz, taken as first order: WM8731 3.7 Hz (-0.5 dB at
#   10.4 Hz, -0.1 dB at 21.6 Hz, Table 31); PCM3060 0.019 fs / 1000 = 0.91 Hz. Both codecs' decimation and
#   interpolation filters are flat to 0.4535 / 0.454 fs = 21.8 kHz within +-0.05 dB (ADC) and +-0.03 / +-0.04 dB
#   (DAC): the 20 kHz end is the analog stages' alone, at the firmware's sample rate (read from main.cc below).
CODEC_PASSBAND_FS = 0.4535      # the narrower of WM8731 (0.4535 fs) and PCM3060 (0.454 fs) passband edges
SEED_IN_ABSMAX = 1.8    # V peak at pins 16 / 17, Table 1 Absolute Maximum Ratings (both datasheets)
# The Seed's outputs are AC coupled on the Seed (Rev5 schematic: C64 / C65 2.2 uF; the Patch Rev 8 drives its x10
# output stage straight from the pin, and both codecs bias their outputs at half their analog supply). Behind the
# cap the pin sees R30 100R + R29 47K to AGND (Rev5 schematic): the output stage's first section has that DC path.
# [verifier 2026-11-13] The writer took the DC path as unknown and passed E on "open" (DC gain 1); the schematic
# gives 47k + 100R (DC noise gain 2.75); 0 R is kept only as a printed bound.
SEED_OUT_DC_PATH = 47e3                 # ohm to AGND behind the output cap (R29 / R28, Rev5; Rev7 assumed the same)

# ---- TL074 (TL074CPWR, TSSOP-14 = TL07xC "all other devices"), TI SLOS080W (July 2025), VS = +-15 V, 25 C -----
TL_VOM_10K_MIN, TL_VOM_10K_TYP = 12.0, 13.5    # V peak, RL = 10k (5.8): min / typ
TL_VOM_2K_MIN, TL_VOM_2K_TYP = 10.0, 12.0      # V peak, RL >= 2k: min 10 (5.8); typ 12 (older revisions)
TL_VS_DS = 15.0
TL_VI_FROM_NEG, TL_VI_FROM_POS = 4.0, 0.1      # 5.3 recommended input voltage, all other devices: V- + 4 .. V+ + 0.1
TL_VOS_TYP, TL_VOS_MAX, TL_VOS_MAX_FULL = 3e-3, 10e-3, 13e-3   # TL07xC: typ / max 25 C / max 0-70 C
TL_IB_MAX_FULL = 7e-9                           # TL07xC, max over 0-70 C (200 pA at 25 C)
GBW_NEW = 5.25e6        # Hz typ, 5.8 / 5.9 "all other devices" (the TSSOP C grade)
GBW_OLD = 3.0e6         # Hz typ, NS / PS packages and older stock: the worse of the two is checked too
AOL = 2e5               # V/V typ (200 V/mV)
PM_UNITY = 56.0         # deg typ, G = +1, RL = 10k, CL = 20 pF (5.9)
ZO_OL = 125.0           # ohm typ, open-loop output impedance, f = 1 MHz (5.9)
C_ID, C_ICM = 2e-12, 1e-12      # F typ: ZID 100 M || 2 pF, ZICM 6 T || 1 pF
# [verifier] those two are the TL07xH table's (5.7); 5.8 / 5.9 give no input capacitance for the TL07xC. A sweep of
# the inverting node's capacitance 3-15 pF moves no stage's phase margin below 60 deg (verifier's own two-pole model),
# so the estimate is not critical. TL_VOM_2K_TYP 12: Fig. 5-43 (VOM vs RL, +-15 V, 25 C) reads ~11.8 V at 2k.
C_STRAY = 2e-12         # F, an inverting node's 0603 pads and ~3 mm of track on the breakout (estimate)
C_PIN = 10e-12          # F, a Seed header pin, socket and the codec trace behind it (estimate)
SR_MIN = 8e6            # V/s min, TL07xC, RL = 2k, CL = 100 pF (5.9)

# ---- B5819W (CJ, LCSC C8598, "D, Mar, 2015"): VF max 0.6 V at IF = 1 A, 25 C; no low-current maximum. At the
# breakout's < 0.1 A the typical curve sits near 0.3 V; 0.45 V is used as the worst case (the 1 A maximum less
# ~0.15 V for a decade less current) and 0.25 V as the lowest. Read from a curve and assumed, not guaranteed.
VF_TYP, VF_WORST, VF_LOW = 0.30, 0.45, 0.25
# ---- Eurorack bus and levels
V_BUS = 12.0            # nominal
BUS_TOL = 0.03          # assumed: Eurorack has no standard tolerance; +-3 % covers common bus supplies
EURO_AUDIO_VPP = 10.0   # Doepfer A-100 technical details: audio signals typically +-5 V (10 V p-p)
HOT_VPP = 20.0          # a hot signal (some VCOs and +-10 V sources patched into an audio input)
R_SOURCE = 1e3          # a typical Eurorack output's series resistor
C_CABLE, C_NEXT = 100e-12, 50e-12     # 1 m patch cable (~100 pF/m) and the next module's input
LOAD_MIN, LOAD_MAX = 10e3, 100e3      # the input impedances a Eurorack output meets
P_0603 = 0.1            # W, 0603WAF thick-film rating at 70 C (UniOhm), the breakout's 1k output resistors

# ---- criteria (first principles; design.md states no audio figures)
FLAT_DB = 0.5           # a path flat within +-0.5 dB 20 Hz - 20 kHz (the mixer suite's criterion)
PM_MIN = 45.0           # deg
UNITY_DB = 0.5          # "OUT should equal IN" (firmware README, first power-up): within +-0.5 dB at 1 kHz
LOAD_LOSS_DB = 1.0      # level lost into the lowest Eurorack load
ZIN_LOSS_DB = 0.2       # level a 1k source may lose into an input
DC_WORST_MAX, DC_TYP_MAX = 0.100, 0.030   # V at OUT: a DC-coupled mixer / output stage downstream (as the mixer)

# ---- the firmware (read from the sources, so the checks follow the firmware)
_eng = harness.text("firmware", "src", "engine", "engine.cc")
_m = re.search(r"if \(a <= ([0-9.]+)f\)", _eng)
LIMIT_KNEE = float(_m.group(1)) if _m else float("nan")      # SoftLimit(): linear up to this fraction of FS
_m = re.search(r"const float y = ([0-9.]+)f \+ ([0-9.]+)f \* e / \(1\.0f \+ e\)", _eng)
LIMIT_CEIL = float(_m.group(1)) + float(_m.group(2)) if _m else float("nan")   # its asymptote
_set = harness.text("firmware", "src", "app", "settings.cc")
_m = re.search(r"s->invert_output = (\d+);", _set)
FW_INVERT_DEFAULT = int(_m.group(1)) if _m else -1
_gi = re.search(r"s->input_gain = (-?\d+);", _set)
_go = re.search(r"s->output_gain = (-?\d+);", _set)
FW_GAINS_DB = (int(_gi.group(1)) / 10 if _gi else float("nan"), int(_go.group(1)) / 10 if _go else float("nan"))
_m = re.search(r"SetAudioSampleRate\(SaiHandle::Config::SampleRate::SAI_(\d+)KHZ\)", harness.text("firmware", "src", "main.cc"))
FS_AUDIO = float(_m.group(1)) * 1e3 if _m else float("nan")


def val(ref):
    return BREAKOUT_BOM[ref]


# 2026-11-14: Side FXy's BOM notes tell the builder to fit other caps in the breakout's audio stages (finding M2).
# The electrical checks model the breakout as built that way; the identification checks (A.*) keep its own BOM.
_bom_notes = harness.text("docs", "bom.md")
BUILT = dict(BREAKOUT_BOM)
_mc1 = re.search(r"C1, C5, C10, C11, C16, C17 at (\d+) pF", _bom_notes)
_mc2 = re.search(r"C2, C6 at (\d+) pF", _bom_notes)
if _mc1:
    BUILT.update({c: float(_mc1.group(1)) * 1e-12 for c in "C1 C5 C10 C11 C16 C17".split()})
if _mc2:
    BUILT.update({c: float(_mc2.group(1)) * 1e-12 for c in "C2 C6".split()})
print(f"      the breakout as built (Side FXy's BOM notes): C1 {BUILT['C1'] * 1e12:g} p, C2 {BUILT['C2'] * 1e12:g} p "
      f"(its own BOM: {BREAKOUT_BOM['C1'] * 1e12:g} p, {BREAKOUT_BOM['C2'] * 1e12:g} p)")


def built(ref):
    return BUILT[ref]


# =========================================================================================== the AC engine
class Opamp:
    """Two-pole TL074: dominant pole from GBW / AOL, the second fitted so that a follower into 10k || 20 pF has the
    datasheet's phase margin."""

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


class Net:
    """Linear AC netlist: R, C, V sources, op-amp sections (VCVS + output resistance + input capacitance)."""

    def __init__(self):
        self.nodes, self.R, self.C, self.V, self.ops = {}, [], [], [], []

    def n(self, name):
        if name == "GND":
            return -1
        if name not in self.nodes:
            self.nodes[name] = len(self.nodes)
        return self.nodes[name]

    def r(self, a, b, v):
        self.R.append((self.n(a), self.n(b), float(v)))

    def c(self, a, b, v):
        if v > 0:
            self.C.append((self.n(a), self.n(b), float(v)))

    def v(self, node, name="in"):
        self.V.append((self.n(node), name))

    def opamp(self, name, inp, inm, out, model):
        self.ops.append((name, self.n(inp), self.n(inm), self.n(name + ".int"), model))
        self.r(name + ".int", out, model.zo)
        self.c(inp, "GND", C_ICM)
        self.c(inm, "GND", C_ICM + C_STRAY)
        self.c(inp, inm, C_ID)

    def matrix(self, f, break_op=None):
        s = 2j * math.pi * f
        N = len(self.nodes)
        Y = np.zeros((N + len(self.V) + len(self.ops),) * 2, complex)

        def stamp(a, b, y):
            if a >= 0:
                Y[a, a] += y
            if b >= 0:
                Y[b, b] += y
            if a >= 0 and b >= 0:
                Y[a, b] -= y
                Y[b, a] -= y
        for a, b, v in self.R:
            stamp(a, b, 1 / v)
        for a, b, v in self.C:
            stamp(a, b, s * v)
        k = N
        for node, name in self.V:
            Y[node, k] += 1
            Y[k, node] += 1
            k += 1
        for name, p, m, o, model in self.ops:
            Y[o, k] += 1
            Y[k, o] += 1
            if name != break_op:
                A = model.A(s)
                if p >= 0:
                    Y[k, p] -= A
                if m >= 0:
                    Y[k, m] += A
            k += 1
        return Y

    def gain(self, f, out, which="in"):
        Y = self.matrix(f)
        b = np.zeros(Y.shape[0], complex)
        for i, (node, name) in enumerate(self.V):
            if name == which:
                b[len(self.nodes) + i] = 1.0
        return np.linalg.solve(Y, b)[self.nodes[out]]

    def loop_gain(self, f, opname):
        Y = self.matrix(f, break_op=opname)
        N = len(self.nodes)
        k = N + len(self.V) + [o[0] for o in self.ops].index(opname)
        b = np.zeros(Y.shape[0], complex)
        b[k] = 1.0
        x = np.linalg.solve(Y, b)
        name, p, m, o, model = self.ops[k - N - len(self.V)]
        vd = (x[p] if p >= 0 else 0) - (x[m] if m >= 0 else 0)
        return -model.A(2j * math.pi * f) * vd


def stages(net, prev, path, model, vals):
    for sec, rin, rf, cf in path["stages"]:
        net.r(prev, f"{sec}-", vals(rin))
        net.r(f"{sec}-", f"{sec}o", vals(rf))
        net.c(f"{sec}-", f"{sec}o", vals(cf))
        net.opamp(sec, "GND", f"{sec}-", f"{sec}o", model)
        prev = f"{sec}o"
    return prev


def build_in(model, codec, ch=1, rs=R_SOURCE, normalled=False, vals=built):
    """Source (rs) -> jack -> input stages -> Seed pin -> the Seed's coupling, series R and codec input (node ADCn).
    normalled: IN 2 unplugged, so the same source drives both channels through J6's switch."""
    cd = CODECS[codec]
    net = Net()
    net.v("SRC")
    net.r("SRC", "TIP1" if (ch == 1 or normalled) else "TIP2", max(rs, 1e-3))
    if normalled:
        net.r("TIP1", "TIP2", 0.02)
    for c in ((1, 2) if normalled else (ch,)):
        p = PATH_IN[c]
        last = stages(net, f"TIP{c}", p, model, vals)
        pin = f"PIN{p['seed']}"
        net.r(last, pin, vals(p["rs"]))
        net.c(pin, "GND", C_PIN)
        net.c(pin, f"CC{c}", cd["c_in"])
        if cd["r_ser"]:
            net.r(f"CC{c}", f"ADC{c}", cd["r_ser"])
        else:
            net.r(f"CC{c}", f"ADC{c}", 1e-3)
        net.r(f"ADC{c}", "GND", cd["z_in"])
    return net


def build_out(model, codec, ch=1, load=LOAD_MAX, cable=True, vals=built):
    """DAC (1 V) -> the Seed's coupling cap -> its 47k to AGND -> its 100R -> Seed pin -> output stages -> 1k -> OUT
    into load || cable (the order of the Rev5 schematic: C64, R29 to AGND, R30)."""
    cd = CODECS[codec]
    p = PATH_OUT[ch]
    net = Net()
    net.v("DAC")
    pin = f"PIN{p['seed']}"
    net.c("DAC", "DACC", cd["c_out"])
    net.r("DACC", "GND", cd["r_gnd"])
    net.r("DACC", pin, cd["z_out"])
    net.c(pin, "GND", C_PIN)
    last = stages(net, pin, p, model, vals)
    net.r(last, "OUT", vals(p["rs"]))
    if load:
        net.r("OUT", "GND", load)
    if cable:
        net.c("OUT", "GND", C_CABLE + C_NEXT)
    return net


OP_NEW, OP_OLD = Opamp(GBW_NEW), Opamp(GBW_OLD)
F_MID = 1e3


def g_in(codec, ch=1, rs=R_SOURCE, normalled=False, at="ADC"):
    """Mid-band (1 kHz) gain from the source EMF to the codec input (at='ADC') or the Seed pin (at='PIN'): the
    magnitude, signed by the real part. [verifier] Was `.real`, which also took the cosine of the stages' 1 kHz phase
    (Rf || Cf, coupling caps: ~0.3 % over the chain) as a level loss."""
    net = build_in(OP_NEW, codec, ch, rs, normalled)
    node = f"ADC{ch}" if at == "ADC" else f"PIN{PATH_IN[ch]['seed']}"
    g = net.gain(F_MID, node)
    return math.copysign(abs(g), g.real)


def g_out(codec, ch=1, load=LOAD_MAX):
    g = build_out(OP_NEW, codec, ch, load).gain(F_MID, "OUT")
    return math.copysign(abs(g), g.real)


def hpf_db(codec, f):
    """The ADC's digital high-pass (first order at its -3 dB corner), dB re 1 kHz."""
    fc = CODECS[codec]["hpf"]
    return db(1 / math.sqrt(1 + (fc / f) ** 2)) - db(1 / math.sqrt(1 + (fc / F_MID) ** 2))


def fs_pin_in(codec):
    """The Seed-pin level (V p-p) that reaches the ADC's full scale."""
    cd = CODECS[codec]
    return cd["fs_in"]


# ------------------------------------------------------------------------- rails and the TL074's swing
def rail(case):
    """The breakout's rail magnitude after its B5819W: 'worst' (bus -3 %, VF worst), 'typ', 'max' (bus +3 %, VF low)."""
    return {"worst": V_BUS * (1 - BUS_TOL) - VF_WORST, "typ": V_BUS - VF_TYP,
            "max": V_BUS * (1 + BUS_TOL) - VF_LOW}[case]


def headroom(load, case):
    """Volts between the rail and the TL074's peak output at this load: the datasheet's VOM at +-15 V taken as a
    rail headroom, interpolated in 1 / RL between its 10k and 2k figures (min for 'worst', typ otherwise)."""
    h10 = TL_VS_DS - (TL_VOM_10K_MIN if case == "worst" else TL_VOM_10K_TYP)
    h2 = TL_VS_DS - (TL_VOM_2K_MIN if case == "worst" else TL_VOM_2K_TYP)
    if load >= 10e3:
        return h10
    return h10 + (h2 - h10) * (1 / load - 1 / 10e3) / (1 / 2e3 - 1 / 10e3)


def swing(load, case):
    return rail(case) - headroom(load, case)


def par(*rs):
    return 1 / sum(1 / r for r in rs)


# ================================================================================================= checks
# ------------------------------------------------------------------------------ A. the reconstruction
for name, paths, patch in (("in", PATH_IN, PATCH_IN), ("out", PATH_OUT, PATCH_OUT)):
    for ch, p in paths.items():
        got = [(val(rin), val(rf), val(cf)) for _, rin, rf, cf in p["stages"]]
        ok = all(abs(a - b) <= 1e-6 * b for g, w in zip(got, patch[0]) for a, b in zip(g, w))
        fmt = lambda t: "(" + ", ".join(f"{x:g}" for x in t) + ")"
        ck.check(f"A.patch_topology.{name}{ch}", ok and abs(val(p["rs"]) - patch[1]) < 1e-6,
                 f"expected the Patch Rev 8 stages (Rin, Rf, Cf) {', '.join(fmt(t) for t in patch[0])} and Rs "
                 f"{patch[1]:g}; the breakout's copper + silk + BOM give {', '.join(fmt(t) for t in got)} "
                 f"({', '.join('/'.join(s[1:]) for s in p['stages'])}) and Rs {val(p['rs']):g} ({p['rs']})")
used = [r for paths in (PATH_IN, PATH_OUT) for p in paths.values() for st in p["stages"] for r in st[1:]] + \
       [p["rs"] for paths in (PATH_IN, PATH_OUT) for p in paths.values()]
audio_bom = [r for r, v in BREAKOUT_BOM.items() if v != 100e-9]
ck.check("A.breakout_bom_parts_placed", sorted(used) == sorted(audio_bom) and len(set(used)) == len(used),
         f"expected each of the BOM's {len(audio_bom)} audio R / C in exactly one stage; the stage map uses "
         f"{len(used)} ({len(set(used))} distinct); missing {sorted(set(audio_bom) - set(used))}, "
         f"extra {sorted(set(used) - set(audio_bom))}")

want = {"J5-1": "IN1", "J5-2": "GND", "J5-3": "IN2", "J5-4": "GND",
        "J4-1": "OUT1", "J4-2": "GND", "J4-3": "OUT2", "J4-4": "GND"}
got = {k: circuit.SEED[k][1] for k in want}
ck.check("A.circuit.J4_J5_nets", got == want,
         f"expected {want} (breakout: {BREAKOUT_NET}); circuit.SEED has {got}")
ck.check("A.circuit.seed_16_19_open", all(circuit.SEED[k][1] is None for k in ("16", "17", "18", "19")),
         "expected Seed pins 16-19 without a net on Side FXy's board (the breakout's stages drive and take them; "
         "COPPER: they run to U2 / U5 on the breakout); got " + str({k: circuit.SEED[k][1] for k in ("16", "17", "18", "19")}))

R = harness.routed()
U5 = R.main.parts["U5"]["pads"]
for k in ("J5-1", "J5-3", "J4-1", "J4-3"):
    n = U5[k].net
    ck.check(f"A.routed.U5.{k}_net", n == want[k], f"expected {want[k]} on the routed U5 pad {k}; got {n}")
ck.check("A.routed.U5.seed_16_19_open", all(U5[k].net is None for k in ("16", "17", "18", "19")),
         "expected no copper net on the routed U5 pads 16-19; got " + str({k: U5[k].net for k in ("16", "17", "18", "19")}))
ref_pts = ("1", "20", "21", "40")
worst = (0.0, "")
for k in ("J5-1", "J5-2", "J5-3", "J5-4", "J4-1", "J4-2", "J4-3", "J4-4"):
    for r in ref_pts:
        d_fp = math.hypot(U5[k].x - U5[r].x, U5[k].y - U5[r].y)
        d_bo = math.hypot(BREAKOUT_XY[k][0] - BREAKOUT_XY[r][0], BREAKOUT_XY[k][1] - BREAKOUT_XY[r][1])
        if abs(d_fp - d_bo) > worst[0]:
            worst = (abs(d_fp - d_bo), f"{k} to Seed pin {r}: footprint {d_fp:.2f} mm, breakout {d_bo:.2f} mm")
ck.check("A.routed.U5.audio_headers_where_the_breakout_has_them", worst[0] < 0.05,
         f"expected every J4 / J5 pad at the breakout's distances (COPPER) from Seed pins 1, 20, 21, 40 within 0.05 mm; "
         f"worst {worst[0]:.3f} mm ({worst[1] or 'all equal'})")
# handedness (information): the breakout's SMD side faces the main board, so the footprint is its top copper mirrored
v = lambda a, b, P: (P[b][0] - P[a][0], P[b][1] - P[a][1])
fp = {k: (U5[k].x, U5[k].y) for k in ref_pts}
cr = lambda P: v("1", "20", P)[0] * v("1", "40", P)[1] - v("1", "20", P)[1] * v("1", "40", P)[0]
print(f"      U5 footprint handedness vs the breakout's top view: {'mirrored' if cr(fp) * cr(BREAKOUT_XY) < 0 else 'same'} "
      f"(the breakout's THT parts and Seed sit on its bottom side, as its bottom silkscreen shows, so its top / SMD "
      f"side faces the main board: mirrored is expected)")

# ------------------------------------------------------------------------------ B. levels
CODEC_NAMES = list(CODECS)
for codec in CODEC_NAMES:
    cd = CODECS[codec]
    gi = g_in(codec, 1, rs=0.0, at="PIN")       # jack (stiff source) -> Seed pin
    gadc = g_in(codec, 1, rs=0.0)               # jack -> codec input
    fs_jack = fs_pin_in(codec) / gi
    print(f"      {codec}: jack -> Seed pin {gi:+.4f} ({db(gi):.1f} dB), ADC full scale {cd['fs_in']:.2f} V p-p at the pin "
          f"= {fs_jack:.1f} V p-p at the jack; DAC full scale {cd['fs_out']:.2f} V p-p")
    ck.within(f"B.jack_level_at_codec_full_scale.{codec}", fs_jack, EURO_AUDIO_VPP, None, " V p-p",
              "a 10 V p-p Eurorack signal must not reach the ADC's full scale")
    # which clips first: stage 1 (gain -Rf/Rin into Rf || next Rin) or the codec
    (s1, rin1, rf1, _), (s2, rin2, rf2, _) = PATH_IN[1]["stages"]
    g1 = val(rf1) / val(rin1)
    load1 = par(val(rf1), val(rin2))
    clip_op_worst = 2 * swing(load1, "worst") / g1
    clip_op_typ = 2 * swing(load1, "typ") / g1
    clip_first = "op-amp stage 1" if clip_op_worst < fs_jack else "codec"
    for lvl, label in ((EURO_AUDIO_VPP, "10Vpp"), (HOT_VPP, "20Vpp_hot")):
        ck.within(f"B.input_{label}_fits.{codec}", min(clip_op_worst, fs_jack), lvl, None, " V p-p",
                  f"the input clip point at the worst corner (op-amp stage 1 {clip_op_worst:.1f} V p-p on "
                  f"+-{rail('worst'):.2f} V rails, typ {clip_op_typ:.1f}; codec {fs_jack:.1f}): {clip_first} clips first")
    # the codec input's absolute maximum: stage 1 saturated at the highest rail, x the second stage's gain
    g2 = val(rf2) / val(rin2)
    # [verifier] TI gives VOM only as min / typ, so the highest stage-1 output is bounded by its rail, not by the
    # typical headroom the writer subtracted (10.61 V): the rail itself is used.
    vpk = rail("max") * g2 * gi / (g1 * g2)       # Seed pin peak with stage 1 at its rail
    ck.within(f"B.seed_input_absmax.{codec}", vpk, None, SEED_IN_ABSMAX, " V peak",
              f"stage 1 saturated at no more than its rail {rail('max'):.2f} V (typ {swing(load1, 'max'):.2f} V) gives "
              f"this at the Seed pin; the Seed's absolute maximum is +-{SEED_IN_ABSMAX} V")
    # output: OUT at DAC full scale, Eurorack's 10 V p-p, the stage's clip
    go = g_out(codec, 1, load=None)
    out_fs = cd["fs_out"] * abs(go)
    (o1, orin1, orf1, _), (o2, orin2, orf2, _) = PATH_OUT[1]["stages"]
    loadA = par(val(orf1), val(orin2))
    loadB = par(val(orf2), val(PATH_OUT[1]["rs"]) + LOAD_MIN)
    clip_out_worst = 2 * min(swing(loadA, "worst") * val(orf2) / val(orin2), swing(loadB, "worst"))
    clip_out_typ = 2 * min(swing(loadA, "typ") * val(orf2) / val(orin2), swing(loadB, "typ"))
    print(f"      {codec}: DAC -> OUT (unloaded) {go:+.3f}; OUT at DAC full scale {out_fs:.1f} V p-p; the output stage "
          f"clips at {clip_out_worst:.1f} V p-p worst / {clip_out_typ:.1f} typ = {db(clip_out_worst / out_fs):+.1f} / "
          f"{db(clip_out_typ / out_fs):+.1f} dBFS")
    ck.within(f"B.output_reaches_10Vpp.{codec}", min(out_fs, clip_out_worst), EURO_AUDIO_VPP, None, " V p-p",
              f"the most OUT can give: DAC full scale x {abs(go):.2f} = {out_fs:.1f} V p-p, the output stage's worst-case "
              f"clip {clip_out_worst:.1f} V p-p into {LOAD_MIN / 1e3:.0f}k + 1k")
    # the firmware's soft limiter: its ceiling should sit inside the analog swing, or the op-amp clips hard first
    ceil_out = LIMIT_CEIL * out_fs
    knee_out = LIMIT_KNEE * out_fs
    ck.within(f"B.firmware_limiter_ceiling_inside_output_swing.{codec}", ceil_out, None, clip_out_worst, " V p-p",
              f"SoftLimit() (engine.cc) is linear to {LIMIT_KNEE:.2f} FS ({knee_out:.1f} V p-p at OUT) and never passes "
              f"{LIMIT_CEIL:.2f} FS ({ceil_out:.1f} V p-p); the output stage clips hard at {clip_out_worst:.1f} V p-p "
              f"worst ({clip_out_typ:.1f} typ), i.e. at {clip_out_worst / out_fs:.2f} FS: the limiter's knee "
              f"{'is never reached before the hard clip' if knee_out > clip_out_worst else 'comes first'}")
    # "OUT should equal IN" (firmware README, first power-up 6: a signal through with every send off, looked at on a
    # scope, so OUT unloaded), the firmware's IN / OUT GAIN at their defaults
    codec_gain = cd["fs_out"] / (cd["fs_in"] * (cd["z_in"] / (cd["z_in"] + cd["r_ser"])))
    fw = 10 ** ((FW_GAINS_DB[0] + FW_GAINS_DB[1]) / 20)
    gtot = gadc * codec_gain * g_out(codec, 1, None) * fw
    g100 = gadc * codec_gain * g_out(codec, 1, LOAD_MAX) * fw
    ck.within(f"B.unity_OUT_equals_IN.{codec}", db(gtot), -UNITY_DB, UNITY_DB, " dB",
              f"jack -> OUT at 1 kHz, stiff source, OUT unloaded, IN / OUT GAIN at their defaults ({FW_GAINS_DB[0]:+.1f} / "
              f"{FW_GAINS_DB[1]:+.1f} dB): x{gtot:.3f} (x{g100:.3f} = {db(g100):+.2f} dB into {LOAD_MAX / 1e3:.0f}k); the "
              f"codec's typical full scales {cd['fs_in']:.2f} in / {cd['fs_out']:.2f} out V p-p at the pins, the Seed's "
              f"input {(cd['z_in'] + cd['r_ser']) / 1e3:.1f}k behind the breakout's 1k, its 100R into the 10k")

# ------------------------------------------------------------------------------ C. headroom and ranges
print(f"      rails after the B5819W: worst {rail('worst'):.2f} V, typ {rail('typ'):.2f} V, max {rail('max'):.2f} V")
for case in ("worst", "typ"):
    sw = swing(50e3, case)
    ck.within(f"C.stage_swing_covers_10Vpp.{case}", 2 * sw, EURO_AUDIO_VPP, None, " V p-p",
              f"a unity-gain stage (U2A / U2C / U5B / U5D) into 50k on +-{rail(case):.2f} V: +-{sw:.2f} V")
# the inverting inputs sit at 0 V while the stage is linear; with stage 1 saturated by a +-12 V source the
# summing node moves to (Vin Rf + Vsat Rin) / (Rin + Rf); it must stay inside V- + 4 .. V+ + 0.1
(s1, rin1, rf1, _) = PATH_IN[1]["stages"][0]
vsat = swing(par(val(rf1), val(PATH_IN[1]["stages"][1][1])), "worst")
vin = 12.0
vsum = (vin * val(rf1) - vsat * val(rin1)) / (val(rin1) + val(rf1))
lo_ok = -rail("worst") + TL_VI_FROM_NEG
ck.within("C.summing_node_inside_input_range.overdriven", abs(vsum), None, rail("worst") - TL_VI_FROM_NEG, " V",
          f"a +-{vin:.0f} V source into IN with stage 1 saturated at {vsat:.2f} V puts the summing node at {vsum:+.2f} V; "
          f"the TL074 input range is {lo_ok:.2f} .. {rail('worst') + TL_VI_FROM_POS:.2f} V (V- + 4)")
print("      common mode: COPPER puts pins 3, 5, 10, 12 of U2 and U5 on GND, so every stage works at 0 V common "
      "mode, inside V- + 4 .. V+ + 0.1 at any rail above 4 V")
# slew rate at 20 kHz full swing
need = 2 * math.pi * 20e3 * swing(50e3, "typ")
ck.within("C.slew_rate_full_swing_20kHz", need, None, SR_MIN / 2, " V/s",
          f"{need / 1e6:.2f} V/us needed for a {swing(50e3, 'typ'):.1f} V peak 20 kHz sine; TL07xC minimum {SR_MIN / 1e6:.0f} V/us")

# ------------------------------------------------------------------------------ D. impedances
for ch in (1, 2):
    rin = val(PATH_IN[ch]["stages"][0][1])
    lo = rin * (1 - R_TOL)
    loss = -db(lo / (lo + R_SOURCE))
    ck.within(f"D.input_impedance.IN{ch}", loss, None, ZIN_LOSS_DB, " dB",
              f"IN {ch} alone (the other input patched): Rin {PATH_IN[ch]['stages'][0][1]} = {rin / 1e3:.0f}k into a "
              f"virtual ground ({lo / 1e3:.1f}k at -1 %); a {R_SOURCE / 1e3:.0f}k source loses {loss:.2f} dB")
zn = par(val(PATH_IN[1]["stages"][0][1]), val(PATH_IN[2]["stages"][0][1])) * (1 - R_TOL)
loss = -db(zn / (zn + R_SOURCE))
ck.within("D.input_impedance.IN1_with_IN2_normalled", loss, None, ZIN_LOSS_DB, " dB",
          f"IN 2 unplugged: a source on IN 1 drives R3 || R8 = {zn / 1e3:.1f}k (-1 %); a {R_SOURCE / 1e3:.0f}k source "
          f"loses {loss:.2f} dB, and {db((100 / 101) / (zn / (zn + R_SOURCE))):.2f} dB more than with IN 2 patched")
for ch in (1, 2):
    rs = val(PATH_OUT[ch]["rs"]) * (1 + R_TOL)
    for load in (LOAD_MIN, LOAD_MAX):
        loss = -db(load / (load + rs))
        ck.within(f"D.output_into_{load / 1e3:.0f}k.OUT{ch}", loss, None, LOAD_LOSS_DB, " dB",
                  f"{PATH_OUT[ch]['rs']} {rs:.0f} R (+1 %) in series, closed-loop output impedance ~0: {loss:.2f} dB lost")
    vmax = swing(par(val(PATH_OUT[ch]["stages"][1][2]), val(PATH_OUT[ch]["rs"]) + LOAD_MIN), "worst") * \
        LOAD_MIN / (LOAD_MIN + rs)
    ck.within(f"D.output_swing_into_10k.OUT{ch}", 2 * vmax, EURO_AUDIO_VPP, None, " V p-p",
              f"worst-case swing behind {rs:.0f} R into {LOAD_MIN / 1e3:.0f}k")
# a shorted output (a cable into another output, or tip on sleeve while patching) with the stage clipped at DC
rs = val(PATH_OUT[1]["rs"]) * (1 - R_TOL)
vs = rail("max") - headroom(2e3, "typ")
p_short = vs ** 2 / rs
ck.within("D.output_resistor_shorted_output_dissipation", p_short, None, P_0603, " W",
          f"{PATH_OUT[1]['rs']} / {PATH_OUT[2]['rs']} (0603, {P_0603} W) with OUT shorted and the stage at "
          f"{vs:.1f} V (highest rail, 2k-load typical headroom): {vs ** 2 / rs * 1e3:.0f} mW, {vs / rs * 1e3:.1f} mA")

# ------------------------------------------------------------------------------ E. DC offset at OUT
for ch in (1, 2):
    (a, arin, arf, _), (b, brin, brf, _) = PATH_OUT[ch]["stages"]
    rows = []
    for rdc in (None, SEED_OUT_DC_PATH, 0.0):        # open (the writer's pass case), the Seed's 47k, grounded
        ng_a = 1.0 if rdc is None else 1 + val(arf) / (val(arin) + CODECS["Rev5 WM8731"]["z_out"] + rdc)
        ng_b = 1 + val(brf) / val(brin)
        gb = val(brf) / val(brin)
        ib = TL_IB_MAX_FULL * (val(arf) * gb + val(brf))
        worst_dc = TL_VOS_MAX_FULL * (ng_a * gb + ng_b) + ib
        typ_dc = math.hypot(TL_VOS_TYP * ng_a * gb, TL_VOS_TYP * ng_b)
        rows.append((rdc, ng_a, worst_dc, typ_dc))
    open_, seed, gnd = rows
    ck.within(f"E.dc_offset_worst.OUT{ch}", seed[2], None, DC_WORST_MAX, " V",
              f"the Seed's pin side has R30 100R + R29 47K to AGND behind its 2.2 uF (Rev5 schematic): stage {a} DC "
              f"noise gain {seed[1]:.2f}, {b} 2; TL074C Vos 13 mV max (0-70 C) + 7 nA bias: {seed[2] * 1e3:.0f} mV "
              f"(open {open_[2] * 1e3:.0f} mV, grounded {gnd[2] * 1e3:.0f} mV as bounds)")
    ck.within(f"E.dc_offset_typ.OUT{ch}", seed[3], None, DC_TYP_MAX, " V",
              f"RSS of 3 mV typ per section with the Seed's 47k: {seed[3] * 1e3:.1f} mV (open {open_[3] * 1e3:.1f}, "
              f"grounded {gnd[3] * 1e3:.1f} mV)")
print("      the codecs' mid-supply bias (WM8731 ~1.65 V, PCM3060 0.5 VCC) is blocked by the Seed's output capacitor "
      "(C64 / C65 2.2 uF, Rev5 schematic); DC-coupled it would rail OUT")

# ------------------------------------------------------------------------------ F. frequency response
F_CHECK = [20.0, 100.0, 1e3, 5e3, 10e3, 15e3, 20e3]


def resp(net, out, codec=None):
    """dB re 1 kHz at F_CHECK; with codec, the ADC's digital high-pass is added (the input path)."""
    h0 = abs(net.gain(F_MID, out))
    return [db(abs(net.gain(f, out)) / h0) + (hpf_db(codec, f) if codec else 0.0) for f in F_CHECK]


def worst_dev(d):
    return max(d, key=abs)


rows = {"input_path": [], "output_path": [], "whole_path": []}
for codec in CODEC_NAMES:
    for ch in (1, 2):
        din = resp(build_in(OP_NEW, codec, ch), f"ADC{ch}", codec)
        dout = resp(build_out(OP_NEW, codec, ch), "OUT")
        dtot = [a + b for a, b in zip(din, dout)]
        for label, d in (("input_path", din), ("output_path", dout), ("whole_path", dtot)):
            rows[label].append((abs(worst_dev(d)), d, f"{codec}, channel {ch}"))
def tol_vals(ref):
    """Every Rf and Cf at the top of its tolerance: the stages' poles at their lowest."""
    v = built(ref)
    return v * (1 + C_TOL) if v < 1e-6 else v * (1 + R_TOL)


d_tol = [a + b for a, b in zip(resp(build_in(OP_NEW, CODEC_NAMES[0], 1, vals=tol_vals), "ADC1", CODEC_NAMES[0]),
                               resp(build_out(OP_NEW, CODEC_NAMES[0], 1, vals=tol_vals), "OUT"))]
for label, r in rows.items():
    w, d, where = max(r, key=lambda t: t[0])
    ck.within(f"F.flat_20Hz_20kHz.{label}", w, None, FLAT_DB, " dB",
              f"worst over both channels and both Seed codecs ({where}): {worst_dev(d):+.2f} dB re 1 kHz; at 20 Hz "
              f"{d[0]:+.2f}, 10 kHz {d[4]:+.2f}, 15 kHz {d[5]:+.2f}, 20 kHz {d[6]:+.2f} dB" +
              (f"; with every Rf / Cf at +1 % / +5 %: {d_tol[6]:+.2f} dB at 20 kHz" if label == "whole_path" else ""))
# [verifier] the low end on its own (a different cause and fix from the 20 kHz roll-off): the Seed's 2.2 uF output
# cap (Rev5 schematic) works into its own 47k || (100R + the breakout's R15 / R25 10k): fc 8.7 Hz
lo = []
for codec in CODEC_NAMES:
    din = resp(build_in(OP_NEW, codec, 1), "ADC1", codec)
    dout = resp(build_out(OP_NEW, codec, 1), "OUT")
    lo.append((abs(din[0] + dout[0]), din[0], dout[0], codec))
w, a, b, where = max(lo)
ck.within("F.low_end_20Hz.whole_path", w, None, FLAT_DB, " dB",
          f"worst {where}: {-(w):+.2f} dB at 20 Hz re 1 kHz = input {a:+.2f} (the Seed's input cap, the ADC's digital "
          f"high-pass) + output {b:+.2f} (the Seed's 2.2 uF into its 47k || the breakout's 10k + 100R: "
          f"{1 / (2 * math.pi * CODECS[where]['c_out'] * par(CODECS[where]['r_gnd'], val(PATH_OUT[1]['stages'][0][1]) + CODECS[where]['z_out'])):.1f} Hz)")
ck.within("F.codec_passband_covers_20kHz", CODEC_PASSBAND_FS * FS_AUDIO, 20e3, None, " Hz",
          f"the codecs' digital filters are flat (+-0.05 dB) to {CODEC_PASSBAND_FS} fs; main.cc runs the codec at "
          f"{FS_AUDIO / 1e3:g} kHz, so the 20 kHz loss above is the analog stages' alone")
poles = []
for label, paths in (("in", PATH_IN), ("out", PATH_OUT)):
    for sec, rin, rf, cf in paths[1]["stages"]:
        poles.append((label, sec, 1 / (2 * math.pi * built(rf) * built(cf))))
print("      the stages' Rf || Cf poles: " + ", ".join(f"{s} {f / 1e3:.1f} kHz" for _, s, f in poles))


def fix_vals(ref):
    """A proposed fix to try: 47 p -> 10 p, 560 p -> 100 p."""
    v = val(ref)
    return {47e-12: 10e-12, 560e-12: 100e-12}.get(v, v)


for codec in CODEC_NAMES:
    din = resp(build_in(OP_NEW, codec, 1, vals=fix_vals), "ADC1", codec)
    dout = resp(build_out(OP_NEW, codec, 1, vals=fix_vals), "OUT")
    print(f"      {codec}, with 47 p -> 10 p and 560 p -> 100 p: whole path at 20 kHz {din[6] + dout[6]:+.2f} dB, at "
          f"10 kHz {din[4] + dout[4]:+.2f} dB, at 20 Hz {din[0] + dout[0]:+.2f} dB (input {din[0]:+.2f}, output "
          f"{dout[0]:+.2f}: the Seed's 2.2 uF output cap into its 47k || the breakout's R15 10k + 100R)")
# anti-alias / images (information: both codecs' digital filters do the work below the modulator rate)
net = build_in(OP_NEW, CODEC_NAMES[0], 1)
h0 = abs(net.gain(F_MID, "ADC1"))
a28 = db(abs(net.gain(28e3, "ADC1")) / h0)
a3m = db(abs(net.gain(3.05e6, "ADC1")) / h0)
net = build_out(OP_NEW, CODEC_NAMES[0], 1)
h0 = abs(net.gain(F_MID, "OUT"))
i28 = db(abs(net.gain(28e3, "OUT")) / h0)
print(f"      analog anti-alias: {a28:+.1f} dB at 28 kHz (fs - 20 kHz), {a3m:+.1f} dB at 3.05 MHz (64 fs - 20 kHz); "
      f"image of a 20 kHz tone at 28 kHz: {i28:+.1f} dB at OUT (the codecs' digital filters add >= 50-65 dB)")

# ------------------------------------------------------------------------------ G. stability
F_LOOP = np.logspace(4, 8.3, 160)


def phase_margin(net, op):
    t = np.array([net.loop_gain(f, op) for f in F_LOOP])
    mag, ph = np.abs(t), np.degrees(np.unwrap(np.angle(t)))
    i = int(np.argmax(mag < 1))
    if i == 0:
        return float("nan"), float("nan")
    w = math.log(mag[i - 1]) / (math.log(mag[i - 1]) - math.log(mag[i]))
    fc = F_LOOP[i - 1] * (F_LOOP[i] / F_LOOP[i - 1]) ** w
    return 180 + ph[i - 1] + w * (ph[i] - ph[i - 1]), fc


pm_rows = {}
for model, mname in ((OP_NEW, "GBW 5.25 MHz"), (OP_OLD, "GBW 3 MHz")):
    for codec in CODEC_NAMES:
        for ch in (1, 2):
            for rs in (0.0, R_SOURCE, 10e3):
                net = build_in(model, codec, ch, rs=rs + 1e-3)
                for op in [o[0] for o in net.ops]:
                    pm_rows.setdefault(op, []).append(phase_margin(net, op) + (mname, f"{codec}, source {rs:g} R"))
            for load, cab in ((LOAD_MAX, True), (LOAD_MIN, True), (None, False)):
                net = build_out(model, codec, ch, load=load, cable=cab)
                if load == LOAD_MIN:
                    net.c("OUT", "GND", 10e-9)          # a long cable / a capacitive input: 10 nF extra
                for op in [o[0] for o in net.ops]:
                    pm_rows.setdefault(op, []).append(phase_margin(net, op) + (mname, f"{codec}, load {load}"))
for op in sorted(pm_rows):
    pm, fc, mname, cname = min(pm_rows[op], key=lambda r: r[0])
    ck.within(f"G.phase_margin.{op}", pm, PM_MIN, None, " deg", f"worst at {fc / 1e6:.2f} MHz ({mname}, {cname})")
# the flatness fix proposed in F keeps the stages stable?
pm_fix = []
for codec in CODEC_NAMES:
    for ch in (1, 2):
        for net in (build_in(OP_OLD, codec, ch, rs=1e-3, vals=fix_vals), build_out(OP_OLD, codec, ch, vals=fix_vals)):
            pm_fix += [phase_margin(net, o[0]) + (o[0],) for o in net.ops]
p = min(pm_fix, key=lambda r: r[0])
print(f"      with 47 p -> 10 p and 560 p -> 100 p: worst phase margin {p[0]:.1f} deg ({p[2]}, GBW 3 MHz)")

# ------------------------------------------------------------------------------ H. polarity
for codec in CODEC_NAMES:
    gi = g_in(codec, 1)
    go = g_out(codec, 1)
    ck.check(f"H.analog_path_non_inverting.{codec}", gi > 0 and go > 0,
             f"expected jack -> codec and DAC -> OUT both positive (two inverting stages each, COPPER); got "
             f"{gi:+.4f} and {go:+.3f}")
ck.check("H.firmware_out_polarity_default", FW_INVERT_DEFAULT == 0,
         f"expected settings.cc's default invert_output 0 (OUT in phase with IN, so a dry / wet mix against a parallel "
         f"dry patch adds); got {FW_INVERT_DEFAULT}. The codecs' own polarity (WM8731; PCM3060 VOUT+, DREV1/2 = 0 by "
         f"default) is assumed non-inverting")

# ------------------------------------------------------------------------------ I. normalling
J = {ref: (tip, lug) for ref, label, tip, lug in circuit.JACKS}
ck.check("I.circuit.IN2_normalled_to_IN1", J["J6"] == ("IN2_F", "IN1_F"),
         f"expected J6 (IN 2) tip IN2_F, switch lug IN1_F; circuit.JACKS has {J['J6']}")
ck.check("I.circuit.IN1_unplugged_grounded", J["J1"] == ("IN1_F", "GND_F"),
         f"expected J1 (IN 1) tip IN1_F, switch lug GND_F; got {J['J1']}")
ck.check("I.circuit.outputs_lugs_open", J["J2"] == ("OUT1_F", None) and J["J7"] == ("OUT2_F", None),
         f"expected J2 / J7 tips OUT1_F / OUT2_F, lugs open; got {J['J2']}, {J['J7']}")
F = R.face.parts
want_f = {("J6", "3"): "IN2_F", ("J6", "2"): "IN1_F", ("J1", "3"): "IN1_F", ("J1", "2"): "GND_F",
          ("J2", "3"): "OUT1_F", ("J7", "3"): "OUT2_F", ("J2", "2"): None, ("J7", "2"): None}
got_f = {k: F[k[0]]["pads"][k[1]].net for k in want_f}
ck.check("I.routed.jack_pads", got_f == want_f, f"expected {want_f}; the routed faceplate has {got_f}")
for codec in CODEC_NAMES:
    g1 = g_in(codec, 1, normalled=True)
    net = build_in(OP_NEW, codec, 1, normalled=True)
    g2 = abs(net.gain(F_MID, "ADC2"))         # [verifier] magnitude, as g_in now returns
    ck.within(f"I.mono_into_IN1_reaches_both.{codec}", abs(db(g2 / g1)), None, 0.05, " dB",
              f"IN 2 unplugged, a 1k source on IN 1: codec ch1 {g1:+.4f}, ch2 {g2:+.4f} ({db(g2 / g1):+.3f} dB apart)")

# ------------------------------------------------------------------------------ J. the audio return
for ref in ("J1", "J2", "J6", "J7"):
    n = F[ref]["pads"]["1"].net
    ck.check(f"J.sleeve_on_GND_F.{ref}", n == "GND_F", f"expected the sleeve (pad 1) on GND_F; got {n}")
hdr_gnd = [(ref, i + 1) for ref, kind, pins in circuit.HEADERS for i, (mb, fb) in enumerate(pins) if fb == "GND_F"]
h1_gnd = [h for h in hdr_gnd if h[0] == "H1"]
ck.check("J.H1_carries_GND_F", len(h1_gnd) == 1 and R.face.parts["HF1"]["pads"][str(h1_gnd[0][1])].net == "GND_F"
         and R.main.parts["H1"]["pads"][str(h1_gnd[0][1])].net == "GND",
         f"expected one GND pin in H1 (GND / GND_F) beside the audio lines; GND_F crosses at {hdr_gnd} "
         f"(H2's carries the CV, clock and MIDI return too)")
gf, contacts = R.face.connectivity()
groups = [k for k in gf["GND_F"].values() if any(x[0] == "pad" for x in k)]
sleeves = {("pad", r, "1") for r in ("J1", "J2", "J6", "J7")} | {("pad", "J1", "2")}
hf = {("pad", "HF" + h[1:], str(i)) for h, i in hdr_gnd}
ok = all(any(s in g for g in groups) and any((s in g) and (g & hf) for g in groups) for s in sleeves)
ck.check("J.faceplate_sleeves_reach_a_header_GND", ok,
         f"expected each audio sleeve (and IN 1's lug) in a GND_F copper group with a header GND_F pin; "
         f"{len(groups)} GND_F group(s) with pads")
bad = [c for c in contacts if {"GND_F", "GND_D_F"} <= {c[0], c[1]}]
# [verifier] dropped a second clause that tested membership in an always-empty list (it could not fail)
ck.check("J.faceplate_GND_F_apart_from_GND_D_F", not bad,
         f"expected no copper contact between GND_F and GND_D_F on the faceplate (design.md: they join only on the main "
         f"board); got {bad[:3]}")
gm, _ = R.main.connectivity()
need = {("pad", "H1", str(h1_gnd[0][1]))} | {("pad", "U5", k) for k in ("J4-2", "J4-4", "J5-2", "J5-4", "20")}
ok = any(need <= g for g in gm["GND"].values())
ck.check("J.main_board_audio_grounds_joined", ok,
         "expected H1's GND pin, the breakout's audio GND pins (J4-2, J4-4, J5-2, J5-4) and the Seed's AGND (20) in "
         "one GND copper group on the main board")

# the audio lines themselves: jack tip -> HF1 on the faceplate, H1 -> the breakout's header on the main board, each
# one copper piece; H1 and HF1 mate pin for pin (the routing audit's item 1 once had them reversed)
for board, groups_, pads in (("face", gf, {"IN1_F": [("J1", "3"), ("J6", "2"), ("HF1", "1")], "IN2_F": [("J6", "3"), ("HF1", "2")],
                                          "OUT1_F": [("J2", "3"), ("HF1", "4")], "OUT2_F": [("J7", "3"), ("HF1", "5")]}),
                             ("main", gm, {"IN1": [("H1", "1"), ("U5", "J5-1")], "IN2": [("H1", "2"), ("U5", "J5-3")],
                                           "OUT1": [("H1", "4"), ("U5", "J4-1")], "OUT2": [("H1", "5"), ("U5", "J4-3")]})):
    for net, members in pads.items():
        keys = {("pad", r, k) for r, k in members}
        ok = any(keys <= g for g in groups_[net].values())
        ck.check(f"J.routed_audio_line_one_piece.{net}", ok,
                 f"expected {', '.join(f'{r}.{k}' for r, k in members)} joined by copper on the {board} board; "
                 f"{len(groups_[net])} copper group(s) on {net}")
mis = []
for i in range(1, 6):
    a, b = R.main.parts["H1"]["pads"][str(i)], R.face.parts["HF1"]["pads"][str(i)]
    if math.hypot(a.x - b.x, a.y - b.y) > 0.05:
        mis.append(f"pin {i}: H1 ({a.x:.2f}, {a.y:.2f}) / HF1 ({b.x:.2f}, {b.y:.2f})")
ck.check("J.H1_HF1_mate_pin_for_pin", not mis,
         "expected each H1 pin on its HF1 pin (both boards' top-layer frames are the stack's rear view); " +
         ("; ".join(mis) if mis else "all five within 0.05 mm"))

# crosstalk exposure: audio lines against digital / pulse lines on the same layer (design.md: keep the encoder and
# button lines off IN / OUT to H1; the routing audit's own spacing for analog lines is 0.8 mm)
ca = harness.load("copper_audit")
AUDIO = ("IN1", "IN2", "OUT1", "OUT2", "IN1_F", "IN2_F", "OUT1_F", "OUT2_F")
AGGR = ("SR_", "LCD_", "ENC", "BTN_", "LED_", "L_", "CLK", "MIDI", "3V3D", "SR_CHAIN")
for bname, brd in (("main", R.main), ("face", R.face)):
    best = (1e9, "")
    for t in brd.tracks:
        if t["net"] not in AUDIO:
            continue
        for u in brd.tracks:
            if u["layer"] != t["layer"] or not u["net"] or not u["net"].startswith(AGGR):
                continue
            d = ca.d_seg_seg(t["a"], t["b"], u["a"], u["b"]) - (t["w"] + u["w"]) / 2
            if d < best[0]:
                best = (d, f"{t['net']} / {u['net']} on layer {t['layer']} near ({t['a'][0]:.1f}, {t['a'][1]:.1f})")
    ck.within(f"J.audio_lines_apart_from_digital.{bname}", best[0], 0.8, None, " mm", best[1])

# ------------------------------------------------------------------------------ K. the docs' claims
D = " ".join(harness.text("docs", "design.md").split())
ck.check("K.design.IN2_normalled_claim", "IN 2 normalled to IN 1" in D and J["J6"][1] == "IN1_F",
         "design.md: 'the breakout's audio in and out, IN 2 normalled to IN 1' against circuit.JACKS J6's lug")
rows = {r: re.search(rf"\| {re.escape(r)} \| ([^|]+) \| ([^|]+) \|", D) for r in ("J1 IN 1", "J6 IN 2", "J2 OUT 1, J7 OUT 2")}
doc_rows = {r: (m.group(1).strip(), m.group(2).strip()) if m else None for r, m in rows.items()}
ok = (doc_rows["J1 IN 1"] == ("IN1_F", "GND_F") and doc_rows["J6 IN 2"] and doc_rows["J6 IN 2"][0] == "IN2_F"
      and doc_rows["J6 IN 2"][1].startswith("IN1_F") and doc_rows["J2 OUT 1, J7 OUT 2"] == ("OUT1_F, OUT2_F", "open"))
ck.check("K.design.jack_table", ok, f"expected the jack table to match circuit.JACKS; design.md has {doc_rows}")
m = re.search(r"J4 \(audio out: AOUT1 = OUT1, AOUT2 = OUT2\), J5 \(audio in: AIN1 = IN1, AIN2 = IN2\)", D)
ck.check("K.design.J4_out_J5_in", bool(m) and circuit.SEED["J5-1"][1] == "IN1" and circuit.SEED["J4-1"][1] == "OUT1",
         "design.md: 'J4 (audio out ...), J5 (audio in ...)': COPPER puts the input header (A IN 1 / A IN 2 on the "
         "bottom silk, into U2) beside Seed pin 1 and the output header beside pin 40, as the routed U5's J5 / J4")
ck.check("K.design.codec_pins_taken_by_breakout", "the four codec pins 16–19, which the breakout's op-amps take over" in D,
         "design.md's DRC table: pins 16-19 left open because the breakout's op-amps take them (COPPER: Seed 16 / 17 "
         "<- U2 via R5 / R10, Seed 18 / 19 -> U5 via R15 / R25)")
hrow = re.search(r"\| H1 / HF1 \(5\) \|[^|]+\| ([^|]+) \|", D)
ck.check("K.design.H1_pins", bool(hrow) and hrow.group(1).strip() == "IN1, IN2, GND/GND_F, OUT1, OUT2"
         and [p[0] for p in circuit.HEADERS[0][2]] == ["IN1", "IN2", "GND", "OUT1", "OUT2"],
         f"expected design.md's H1 row and circuit.HEADERS H1 = IN1, IN2, GND, OUT1, OUT2; doc "
         f"{hrow.group(1).strip() if hrow else None}, circuit {[p[0] for p in circuit.HEADERS[0][2]]}")
m = re.search(r"\| H1 / HF1 \(5\) \| bottom-left corner beside IN 2, x ([\d.]+), y ([\d.]+)–([\d.]+), pins along y \|", D)
hx = [R.main.outline[2] - R.main.parts["H1"]["pads"][str(i)].x for i in range(1, 6)]     # front view x
hy = [R.main.parts["H1"]["pads"][str(i)].y for i in range(1, 6)]
ok = bool(m) and all(abs(x - float(m.group(1))) < 0.06 for x in hx) and abs(min(hy) - float(m.group(2))) < 0.06 \
    and abs(max(hy) - float(m.group(3))) < 0.06
ck.check("K.design.H1_position", ok,
         f"design.md: H1 at x {m.group(1) if m else '?'}, y {m.group(2) if m else '?'}-{m.group(3) if m else '?'} (front "
         f"view); routed: x {min(hx):.2f}-{max(hx):.2f}, y {min(hy):.2f}-{max(hy):.2f}")
ck.check("K.design.J5_contacts_stay_in", all(U5[k].net for k in ("J5-1", "J5-2", "J5-3", "J5-4"))
         and "so J5's contacts stay in" in D,
         "design.md: 'this module uses the breakout's audio input op-amps, so J5's contacts stay in': the routed U5 has "
         f"J5-1..4 on {[U5[k].net for k in ('J5-1', 'J5-2', 'J5-3', 'J5-4')]}")
FW = " ".join(harness.text("firmware", "README.md").split())
ck.check("K.firmware_readme.limiter_claim_matches_source", "linear to 0.75 of full scale" in FW and LIMIT_KNEE == 0.75
         and abs(LIMIT_CEIL - 1.0) < 1e-6,
         f"README: 'A soft limiter (linear to 0.75 of full scale, then a smooth knee that never passes it)'; engine.cc: "
         f"knee {LIMIT_KNEE}, ceiling {LIMIT_CEIL}")
ck.check("K.firmware_readme.dual_mono_normal", "IN 2 is normalled to IN 1" in FW and J["J6"][1] == "IN1_F",
         "README DUAL MONO: 'IN 2 is normalled to IN 1, so one mono source gives two different outputs'")

ck.done()
