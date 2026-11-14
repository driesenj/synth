"""Shared model for Marblesy's two analog groups (helper of test_analog_dc.py and test_analog_ac.py).

What is here
  - the datasheet constants both groups use (TL074, the STM32H750 on the Daisy Seed, the rails), each
    with its source, conditions and min / typ / max; group-only constants sit at the top of each group
  - netlist helpers: circuit.py's parts with every faceplate net mapped onto the main-board net it mates
    with through the headers (GND_F / GND_D_F -> GND), resistors and capacitors found by the nets they join
  - Mna: a modified-nodal-analysis model of a part of the netlist. DC: TL074 sections as high-gain VCVSs
    with an input offset, solved batched over numpy arrays (corners, Monte Carlo). AC: each section a
    two-pole VCVS behind its open-loop output resistance with its input capacitances, solved at one
    frequency, with the loop gain of any section and the adjoint (output-referred) noise
  - rails(): the +-12 V the TL074s see behind the breakout's B5819W Schottkys and 2.2 uH inductors, and
    swing(): the TL074's output limits on those rails at a load

Only reads circuit.py (through harness); writes nothing.
"""
import math
import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # small matrices: threaded BLAS only costs time
import numpy as np  # noqa: E402

import harness  # noqa: E402

# =============================================================================================== constants
# --- TL074 (U3-U6), TI SLOS080W (Sept 1978, rev. July 2025), www.ti.com/lit/ds/symlink/tl074.pdf, read
# 2026-11-12. The DIP-14 TL074CN is a TL07xC and one of the "all other devices" (not PS / NS, not M).
# 5.8 DC table, VS = +-15 V, 25 C unless noted:
TL_VOS_TYP, TL_VOS_MAX_25C, TL_VOS_MAX_FULL = 3e-3, 10e-3, 13e-3   # V: typ / max 25 C / max 0-70 C (TL07xC)
TL_IB_TYP, TL_IB_MAX_25C, TL_IB_MAX_FULL = 65e-12, 200e-12, 7e-9   # A: typ / max 25 C / max 0-70 C
TL_VICR_MIN = 11.0          # V, common-mode range min (guaranteed) +-11 V at +-15 V: V- + 4 V .. V+ - 4 V
TL_VICR_NEG_TYP = -12.0     # V, typ -12 to +15 at +-15 V (V- + 3 V .. V+)
TL_VOM_10K_MIN, TL_VOM_10K_TYP = 12.0, 13.5     # V peak, RL = 10k, at +-15 V: min / typ
TL_VOM_2K_MIN, TL_VOM_2K_TYP = 10.0, 12.0       # V peak, RL = 2k: min 10 (W table); typ 12 from the older revisions
TL_VS_DS = 15.0                                 # the rails the VOM / VICR figures are given at
TL_AOL_MIN, TL_AOL_TYP = 25e3, 200e3            # V/V, VO = 0, RL >= 2k: min 25 V/mV, typ 200 V/mV (TL07xC)
TL_IQ_TYP, TL_IQ_MAX = 1.4e-3, 2.5e-3           # A per amplifier, no load
# 5.9 AC table, VS = +-15 V, 25 C:
TL_GBW_NEW = 5.25e6         # Hz typ, "all other devices" (the current die)
TL_GBW_OLD = 3.0e6          # Hz typ, PS / NS packages and M grade (the legacy figure, kept as the slow case)
TL_SR_MIN, TL_SR_TYP = 8e6, 20e6                # V/s, VI = 10 V, RL = 2k, CL = 100 pF, TL07xC: min / typ
TL_PM_UNITY = 56.0          # deg typ, G = +1, RL = 10k, CL = 20 pF
TL_ZO_OL = 125.0            # ohm typ, open-loop output impedance, f = 1 MHz, IO = 0
TL_EN_1K, TL_EN_10K = 37e-9, 21e-9              # V/rtHz typ, all other devices, f = 1 kHz / 10 kHz
TL_IN = 80e-15              # A/rtHz typ (TL07xH table; the legacy table's 10 fA is lower): the higher is used
TL_C_ID, TL_C_ICM = 2e-12, 1e-12                # F typ, differential / common-mode input capacitance (H table:
#                                                 ZID 100 M || 2 pF, ZICM 6 T || 1 pF; the C tables give none)

# --- STM32H750IB on the Daisy Seed: ST DS12556 Rev 7 (March 2023), copy at
# cdn.sparkfun.com/assets/b/6/0/6/b/stm32h750ib.pdf (st.com refused the download). Seeds ship rev V silicon:
# the section 7 (rev V) tables are used; the rev Y ones read the same for everything below.
STM_VIL_FRAC, STM_VIH_FRAC = 0.3, 0.7      # Table 155: VIL max 0.3 VDD, VIH min 0.7 VDD (CMOS), 1.62-3.6 V
STM_VHYS_TYP = 0.25                        # V typ, Table 155, TT_xx / FT_xxx input hysteresis
STM_VOH_DROP_8MA = 0.4                     # Table 156: VOH >= VDD - 0.4 V and VOL <= 0.4 V at IIO = 8 mA, 2.7-3.6 V
STM_IIO_TEST = 8e-3                        #   (the pins here source or sink nA-uA: 0.4 V / 8 mA = 50 ohm at most)
STM_IINJ_PIN = (-5e-3, 0.0)                # Table 118 (abs. max): FT_xxx, TT_xx: -5 / +0 mA; note 3: "positive
#                                            injection is not possible on these I/Os and does not occur for input
#                                            voltages lower than the specified maximum value"
STM_IINJ_SUM = 25e-3                       # Table 118: total injected current, all I/Os, +-25 mA
STM_VIN_FT_ABOVE_VDD = 4.0                 # Table 117 (abs. max): FT_xxx up to min(VDD, VDDA, VDD33USB, VBAT) + 4.0 V
STM_VIN_TT_MAX = 4.0                       # Table 117: TT_xx up to 4.0 V
STM_VIN_MIN = -0.3                         # Table 117: VSS - 0.3 V on every pin
# verifier change: the "_a" option means "analog option (supplied by VDDA)" (DS12556 Table 6), and DS12556 7.3.15
# sends GPIO configuration questions to AN4899. ST AN4899 Rev 3 (STM32 GPIO configuration), 5.2.1 / 5.2.2, read
# through manualslib's copy of Rev 3 pp. 17-18 and ST staff quoting it on community.st.com (st.com refused the PDF):
# "A GPIO is five-volt tolerant only if there is no analog function enabled on pin (for I/O structure FT_a, FT_fa,
# TT_a). If some analog input function is enabled on the GPIO (ADC input active, COMP input, OPAMP input)" the
# maximum operating voltage on the pin "cannot exceed min(VDDA, VREF+) + 0.3 V"; above it current flows into VDDA /
# VREF+. RM0433 11.3.13 (Analog configuration) gives no voltage figure. On the Seed VDDA = VREF+ = 3V3A, so every CV
# pin (FT_a, FT_ha, TT_a alike, all ADC inputs) is limited to 3V3A + 0.3 V while the firmware runs (libDaisy's
# AdcHandle::Init calls HAL_ADC_ConfigChannel per channel, which sets the channel's PCSEL preselection bit for good:
# ST stm32h7xx_hal_adc.c).
STM_VIN_ANALOG_ABOVE_VDDA = 0.3
# Table 154 (rev V; = Table 57 rev Y), functional susceptibility to injection (characterisation; failure = ADC
# error > 5 LSB TUE or leakage on neighbours): negative / positive mA. PA7 is listed in rows 1 and 2; the
# stricter row (0 mA) is used for it.
STM_SUSC_NEG_0 = {"PA2", "PH2", "PH3", "PE8", "PA6", "PA7", "PC4", "PE7", "PE10", "PE11",          # row 2
                  "PA0", "PA0_C", "PA1", "PA1_C", "PC2", "PC2_C", "PC3", "PC3_C", "PA4", "PA5", "PH4", "PH5"}
STM_SUSC_NEG_OTHER = 5e-3                  # "all other I/Os": 5 mA negative, positive NA
# ADC notes (Table 184 note, rev V; same text rev Y): "injecting a negative current on any analog input pins
# should be avoided as this significantly reduces the accuracy of the conversion being performed on another
# analog input. It is recommended to add a Schottky diode (pin to ground) ..."; positive injection within
# IINJ does not affect accuracy.
STM_CADC = 4e-12                           # F typ, Table 182, internal sample-and-hold capacitor
STM_CIO = 5e-12                            # F typ, Table 155, I/O pin capacitance
STM_RADC = 500.0                           # ohm: the sampling switch's resistance is not given in DS12556
#                                            (Figure 38 names RADC only): an assumption, generous
STM_ILKG = 250e-9                          # A max, Table 155, FT_xx / TT_xx input leakage, 0 < VIN <= VDD
STM_TSAR_16B = 8.5                         # ADC cycles: tCONV = ts + 0.5 + N/2 (Table 182), N = 16
# Pin types, Table 7 (pin/ball definition) of DS12556, read with pdftotext -raw:
STM_PIN_TYPE = {"PC0": "FT_a", "PA3": "FT_ha", "PB1": "TT_a", "PA7": "TT_a", "PA6": "FT_a", "PC1": "FT_ha",
                "PC4": "TT_a", "PA5": "TT_ha", "PA4": "TT_a", "PA1": "FT_ha", "PA0": "FT_a", "PA2": "FT_a",
                "PB12": "FT", "PC11": "FT_h", "PC10": "FT_ha", "PC9": "FT_fh", "PC8": "FT_h"}
# libDaisy v9.0.0 src/daisy_seed.h (raw.githubusercontent.com/electro-smith/libDaisy/v9.0.0/...): seed pins
SEED_PORT_PIN = {"D0": "PB12", "D1": "PC11", "D2": "PC10", "D3": "PC9", "D4": "PC8",
                 "D15": "PC0", "D16": "PA3", "D17": "PB1", "D18": "PA7", "D19": "PA6", "D20": "PC1",
                 "D21": "PC4", "D22": "PA5", "D23": "PA4", "D24": "PA1", "D25": "PA0", "D28": "PA2"}
SEED_A_TO_D = {"A0": "D15", "A1": "D16", "A2": "D17", "A3": "D18", "A4": "D19", "A5": "D20", "A6": "D21",
               "A7": "D22", "A8": "D23", "A9": "D24", "A10": "D25", "A11": "D28"}
# Electrosmith Daisy Seed datasheet v1.0.5 (25 Jan 2023), Table 1: GPIO absolute range 0 .. +5 V; 3.3 V
# tolerant pins 24 (A2 PB1), 25 (A3 PA7), 28 (A6 PC4), 29 (A7 PA5), 30 (A8 PA4); all others 5 V tolerant.
SEED_GPIO_ABS = (0.0, 5.0)
SEED_TT_PINS = {"PB1", "PA7", "PC4", "PA5", "PA4"}
# 3V3A / 3V3D: the Seed datasheet gives no tolerance and its schematic pages are vector drawings without text,
# so the regulator could not be identified. Not confirmed: +-3 % assumed (a generous LDO figure over line,
# load and temperature). The firmware (adc.cc) and an Electrosmith forum thread take the ADC's VREF+ as 3V3A;
# not confirmed from the schematic, used as the model.
V33_NOM, V33_TOL = 3.3, 0.03

# --- Rails. The breakout (Rob Heel's seed_power_opamps, BOM 2025-08-29) feeds +-12 V through D2/D3 B5819W
# (series Schottkys) and L1/L2 MLZ1608A2R2WT000 (2.2 uH 0603).
BUS_NOM = 12.0
BUS_TOL = 0.05     # Doepfer gives no tolerance (doepfer.de/a100_man/a100t_e.htm lists nominal volts and amps
#                    only): not confirmed; +-5 % assumed as a conservative bound for a Eurorack PSU (linear
#                    78/79xx designs guarantee about +-4 %, switching ones +-1-2 %)
D5819_VF_1A_MAX = 0.60      # V max at IF = 1 A, 25 C: Yongyutai B5819W datasheet Rev 2.0 (0.5 V in TL-B5819W's);
#                             verifier change (comment only): confirmed in the breakout's own part, JSCJ B5817W-B5819W
#                             (LCSC C8598 PDF): B5819W VF max 0.6 V at IF = 1 A, 0.9 V at 3 A, 25 C; nothing lower
D5819_N = 1.1               # ideality used to carry the 1 A maximum down to the real current (-66 mV/decade;
#                             ignores the series resistance, so it overstates the drop: conservative)
D5819_VF_TYP_100MA = 0.33   # V typ near 0.1 A: assumption (no readable curve; 1 A SOD-123 Schottkys read 0.3-0.4 V)
L_DCR_MAX = 0.3             # ohm, MLZ1608A2R2W DC resistance: TDK's catalogue refused the download; assumption
BRK_TL074_AMPS = 8          # the breakout's two TL074CPWR (its audio stages) on the same rails
DCDC_IIN_TYP, DCDC_IIN_MAX = 35e-3, 57e-3   # A, B2405S-1WR2 (24 V in, 5 V 1 W out) input current; typ from the Seed's
#                             ~0.6 W at about 75 %. verifier change: max 55 -> 57 mA, Mornsun B_S-1WR2 2024.09.09-B/4
#                             Input Specifications: 24 V input, full load 57 mA typ (no-load 17 typ / 30 max); no full-load
#                             maximum is given, so the full-load typical is the bound
VT = 0.025852               # V, kT/q at 300 K
KB = 1.380649e-23

# ============================================================================================ the netlist
CIRCUIT = harness.load("circuit")
PARTS = CIRCUIT.all_parts()
MAIN = CIRCUIT.main_board_parts()
FACE = CIRCUIT.faceplate_parts()
BY_REF = {}                  # (board, ref) -> Part; R80-R85 exist on both boards
for _p in MAIN:
    BY_REF[("main", _p.ref)] = _p
for _p in FACE:
    BY_REF[("face", _p.ref)] = _p

FB2MB = {}
for _ref, _kind, _pins in CIRCUIT.HEADERS:
    for _mb, _fb in _pins:
        if _mb:
            FB2MB[_fb] = _mb
FB2MB.update({"GND_F": "GND", "GND_D_F": "GND"})


def node(net):
    """The merged net: a faceplate header net becomes the main-board net it mates with; grounds are GND."""
    return FB2MB.get(net, net)


def part(ref, board="main"):
    return BY_REF[(board, ref)]


def nets_of(p):
    return {k: node(v) for k, v in p.nets.items()}


def between(a, b, kind="R"):
    """Every part of `kind` (R / C) with one end on net a and the other on net b (merged nets)."""
    a, b = node(a), node(b)
    out = []
    for board, parts in (("main", MAIN), ("face", FACE)):
        for p in parts:
            if p.kind != kind:
                continue
            n1, n2 = node(p.nets["1"]), node(p.nets["2"])
            if {n1, n2} == {a, b}:
                out.append((board, p))
    return out


def one(a, b, kind="R"):
    """The one R / C between two nets: (ref, value in ohm / F). Raises if there is none or several."""
    found = between(a, b, kind)
    if len(found) != 1:
        raise LookupError(f"expected one {kind} between {a} and {b}, found {[p.ref for _, p in found]}")
    board, p = found[0]
    return p.ref, (harness.ohms(p.value) if kind == "R" else harness.farads(p.value))


def opamp_driving(net):
    """(chip, section) of the TL074 section whose output is on net."""
    for p in MAIN:
        if p.kind == "TL074":
            for s, (o, m, pp) in CIRCUIT.SECTION.items():
                if p.nets.get(o) == net:
                    return (p.ref, s)
    raise LookupError(f"no TL074 section drives {net}")


def section_pins(u, s):
    p = part(u)
    o, m, pp = CIRCUIT.SECTION[s]
    return {"out": node(p.nets[o]), "m": node(p.nets[m]), "p": node(p.nets[pp])}


def seed_pin_of(net):
    """(seed pin name, STM32 port pin, pin type) of the Seed pin on net (via circuit.SEED)."""
    for pin, (name, n) in CIRCUIT.SEED.items():
        if n == net and not pin.startswith("J"):
            nm = name.split("/")[-1]                  # "D16/A1" -> "A1", "D0" -> "D0"
            d = SEED_A_TO_D.get(nm, nm)
            port = SEED_PORT_PIN[d]
            return nm, port, STM_PIN_TYPE[port]
    raise LookupError(f"no Seed pin on {net}")


def tl074_count():
    return sum(1 for p in MAIN if p.kind == "TL074")


# =============================================================================================== the rails
def rails(case, i_load_p=0.0, i_load_n=0.0):
    """(V+, V-, I+, I-) at the TL074s: bus, minus the B5819W at its current, minus the inductor's DCR.
    case 'typ': nominal bus, typical currents and drop; 'worst': bus at -5 %, maximum currents, the
    extrapolated maximum drop."""
    amps = 4 * tl074_count() + BRK_TL074_AMPS
    if case == "typ":
        ip = amps * TL_IQ_TYP + DCDC_IIN_TYP + i_load_p
        in_ = amps * TL_IQ_TYP + DCDC_IIN_TYP + i_load_n
        bus = BUS_NOM
        vf = lambda i: D5819_VF_TYP_100MA + D5819_N * VT * math.log(max(i, 1e-6) / 0.1)
        rl = L_DCR_MAX / 2
    else:
        ip = amps * TL_IQ_MAX + DCDC_IIN_MAX + i_load_p
        in_ = amps * TL_IQ_MAX + DCDC_IIN_MAX + i_load_n
        bus = BUS_NOM * (1 - BUS_TOL)
        vf = lambda i: D5819_VF_1A_MAX - D5819_N * VT * math.log(1.0 / max(i, 1e-6))
        rl = L_DCR_MAX
    return bus - vf(ip) - rl * ip, -(bus - vf(in_) - rl * in_), ip, in_


def headroom(load, case):
    """Volts between a rail and the TL074's output at this load: the datasheet's VOM at +-15 V carried to the
    real rails as the same headroom, interpolated in 1/RL between the 10k and 2k figures (below 2k:
    extrapolated)."""
    h10 = TL_VS_DS - (TL_VOM_10K_TYP if case == "typ" else TL_VOM_10K_MIN)
    h2 = TL_VS_DS - (TL_VOM_2K_TYP if case == "typ" else TL_VOM_2K_MIN)
    if load >= 10e3:
        return h10
    return h10 + (h2 - h10) * (1 / load - 1 / 10e3) / (1 / 2e3 - 1 / 10e3)


def swing(load, case, vp, vn):
    h = headroom(load, case)
    return vn + h, vp - h


def cm_range(case, vp, vn):
    """The TL074's input common-mode range on these rails (guaranteed: V- + 4 .. V+ - 4; typ V- + 3 .. V+)."""
    if case == "typ":
        return vn + (TL_VS_DS + TL_VICR_NEG_TYP), vp
    return vn + (TL_VS_DS - TL_VICR_MIN), vp - (TL_VS_DS - TL_VICR_MIN)


# ============================================================================================ the MNA model
class Opamp:
    """TL074 small-signal model: A(s) = a0 / ((1 + s/w1)(1 + s/w2)) behind zo, w1 from the GBW, w2 fitted so
    a follower into 10k || 20 pF (the datasheet's condition) has the datasheet's phase margin."""

    def __init__(self, gbw, pm=TL_PM_UNITY, a0=TL_AOL_TYP, zo=TL_ZO_OL):
        self.gbw, self.a0, self.zo = gbw, a0, zo
        self.w1 = 2 * math.pi * gbw / a0
        self.w2 = self._fit_w2(pm)

    def A(self, s, w2=None):
        return self.a0 / ((1 + s / self.w1) * (1 + s / (w2 or self.w2)))

    def _fit_w2(self, pm):
        f = np.logspace(4, 9, 3000)
        s = 2j * np.pi * f
        zl = 1 / (1 / 10e3 + s * 20e-12)

        def margin(w2):
            t = self.A(s, w2) * zl / (zl + self.zo)
            i = int(np.argmax(np.abs(t) < 1))
            return 180 + np.degrees(np.unwrap(np.angle(t)))[i]
        lo, hi = 2 * math.pi * 1e5, 2 * math.pi * 1e9
        for _ in range(60):
            mid = math.sqrt(lo * hi)
            lo, hi = (lo, mid) if margin(mid) > pm else (mid, hi)
        return math.sqrt(lo * hi)


class Mna:
    """A linear model of part of the netlist.

    r(a, b, ohms, tag), c(a, b, farads, tag), opamp(name, p, m, out). Nets are merged names (node()).
    dc(fixed, ...): fixed {net: volts} are ideal sources to ground; everything is numpy-batched.
    ac(...): the fixed nets are AC sources (amplitude per net, default 0 = AC ground)."""

    def __init__(self):
        self.R, self.C, self.ops = [], [], []

    def r(self, a, b, ohms, tag=""):
        if a != b:
            self.R.append((a, b, float(ohms), tag))

    def c(self, a, b, farads, tag=""):
        if a != b and farads > 0:
            self.C.append((a, b, float(farads), tag))

    def opamp(self, name, p, m, out):
        self.ops.append({"name": name, "p": p, "m": m, "out": out})

    def add_netlist(self, nets, fixed=(), caps=False, skip=()):
        """Every resistor (and capacitor if caps) of circuit.py with both ends in nets | fixed | {GND} and at
        least one end in nets, and every TL074 section whose output is in nets. Returns self."""
        nets = {node(n) for n in nets}
        known = nets | {node(n) for n in fixed} | {"GND"}
        for board, parts in (("main", MAIN), ("face", FACE)):
            for p in parts:
                if p.ref in skip:
                    continue
                if p.kind in ("R", "C") and (p.kind == "R" or caps):
                    a, b = node(p.nets["1"]), node(p.nets["2"])
                    if a in known and b in known and (a in nets or b in nets):
                        tag = p.ref if board == "main" else p.ref + "_F"
                        if p.kind == "R":
                            self.r(a, b, harness.ohms(p.value), tag)
                        else:
                            self.c(a, b, harness.farads(p.value), tag)
                elif p.kind == "TL074":
                    for s in CIRCUIT.SECTION:
                        pins = section_pins(p.ref, s)
                        if pins["out"] in nets:
                            self.opamp((p.ref, s), pins["p"], pins["m"], pins["out"])
        return self

    # ------------------------------------------------------------------------------------------- DC
    def dc(self, fixed, rmul=None, vos=None, aol=TL_AOL_TYP, B=1, inject=None):
        """Node voltages {net: array(B)} and op-amp output currents {name: array(B)} (out of the pin).
        fixed: {net: volts or array}; rmul: {tag: multiplier or array}; vos: {op name: volts at IN+};
        inject: {net: amps or array into the node}."""
        rmul, vos, inject = rmul or {}, vos or {}, inject or {}
        fv = {k: np.broadcast_to(np.asarray(v, float), (B,)) for k, v in dict(fixed, GND=0.0).items()}
        nets = set()
        for a, b, _, _ in self.R:
            nets |= {a, b}
        for o in self.ops:
            nets |= {o["p"], o["m"], o["out"]}
        nodes = sorted(n for n in nets if n not in fv)
        idx = {n: i for i, n in enumerate(nodes)}
        N, M = len(nodes), len(self.ops)
        A = np.zeros((B, N + M, N + M))
        z = np.zeros((B, N + M))
        for i in range(N):
            A[:, i, i] += 1e-15                   # keeps a node with only op-amp inputs on it solvable
        for a, b, ohm, tag in self.R:
            g = 1.0 / (ohm * np.broadcast_to(np.asarray(rmul.get(tag, 1.0), float), (B,)))
            ia, ib = idx.get(a), idx.get(b)
            if ia is not None:
                A[:, ia, ia] += g
                if ib is not None:
                    A[:, ia, ib] -= g
                else:
                    z[:, ia] += g * fv[b]
            if ib is not None:
                A[:, ib, ib] += g
                if ia is not None:
                    A[:, ib, ia] -= g
                else:
                    z[:, ib] += g * fv[a]
        for n, cur in inject.items():
            z[:, idx[n]] += cur
        for j, o in enumerate(self.ops):
            k = N + j
            io = idx[o["out"]]
            A[:, io, k] -= 1.0
            A[:, k, io] += 1.0
            rhs = aol * np.broadcast_to(np.asarray(vos.get(o["name"], 0.0), float), (B,))
            for pin, sgn in (("p", -aol), ("m", aol)):
                nd = o[pin]
                if nd in idx:
                    A[:, k, idx[nd]] += sgn
                else:
                    rhs = rhs - sgn * fv[nd]
            z[:, k] = rhs
        x = np.linalg.solve(A, z[..., None])[..., 0]
        V = {n: x[:, i] for n, i in idx.items()}
        V.update(fv)
        I = {o["name"]: x[:, N + j] for j, o in enumerate(self.ops)}
        return V, I

    # ------------------------------------------------------------------------------------------- AC
    def _ac_index(self, sources):
        nets = {"GND"}
        for a, b, _, _ in self.R:
            nets |= {a, b}
        for a, b, _, _ in self.C:
            nets |= {a, b}
        for o in self.ops:
            nets |= {o["p"], o["m"], o["out"], f"{o['name']}.int"}
        nets |= set(sources)
        nodes = sorted(n for n in nets if n != "GND")
        return nodes, {n: i for i, n in enumerate(nodes)}

    def ac_matrix(self, f, sources, model, break_op=None):
        """Y x = b at frequency f. sources: the fixed nets (ideal V sources to ground). break_op: that op-amp's
        VCVS becomes an independent source (for the loop gain)."""
        nodes, idx = self._ac_index(sources)
        src = list(sources)
        N, S, M = len(nodes), len(src), len(self.ops)
        s = 2j * math.pi * f
        Y = np.zeros((N + S + M, N + S + M), complex)

        def stamp(a, b, y):
            ia, ib = idx.get(a), idx.get(b)
            if ia is not None:
                Y[ia, ia] += y
            if ib is not None:
                Y[ib, ib] += y
            if ia is not None and ib is not None:
                Y[ia, ib] -= y
                Y[ib, ia] -= y
        for a, b, ohm, _ in self.R:
            stamp(a, b, 1 / ohm)
        for a, b, cap, _ in self.C:
            stamp(a, b, s * cap)
        for o in self.ops:
            stamp(f"{o['name']}.int", o["out"], 1 / model.zo)
            stamp(o["p"], "GND", s * TL_C_ICM)
            stamp(o["m"], "GND", s * TL_C_ICM)
            stamp(o["p"], o["m"], s * TL_C_ID)
        for k, n in enumerate(src):
            if n in idx:
                Y[idx[n], N + k] += 1
                Y[N + k, idx[n]] += 1
        for j, o in enumerate(self.ops):
            k = N + S + j
            ii = idx[f"{o['name']}.int"]
            Y[ii, k] += 1
            Y[k, ii] += 1
            if o["name"] != break_op:
                a = model.A(s)
                if o["p"] in idx:
                    Y[k, idx[o["p"]]] -= a
                if o["m"] in idx:
                    Y[k, idx[o["m"]]] += a
        return Y, nodes, idx, src

    def ac(self, f, sources, model, excite=None):
        """Node voltages {net: complex} at f with excite {source net: amplitude} (others 0)."""
        Y, nodes, idx, src = self.ac_matrix(f, sources, model)
        b = np.zeros(Y.shape[0], complex)
        for k, n in enumerate(src):
            b[len(nodes) + k] = (excite or {}).get(n, 0.0)
        x = np.linalg.solve(Y, b)
        V = {n: x[i] for n, i in idx.items()}
        V["GND"] = 0.0
        return V

    def loop_gain(self, f, sources, model, op):
        """T = -A (V+ - V-) with op's VCVS replaced by a 1 V source, every other source at 0."""
        Y, nodes, idx, src = self.ac_matrix(f, sources, model, break_op=op)
        N, S = len(nodes), len(src)
        j = [o["name"] for o in self.ops].index(op)
        b = np.zeros(Y.shape[0], complex)
        b[N + S + j] = 1.0
        x = np.linalg.solve(Y, b)
        o = self.ops[j]
        vp = x[idx[o["p"]]] if o["p"] in idx else 0.0
        vm = x[idx[o["m"]]] if o["m"] in idx else 0.0
        return -model.A(2j * math.pi * f) * (vp - vm)

    def phase_margin(self, sources, model, op, f=None):
        """(phase margin in degrees, crossover frequency) of op's loop."""
        f = np.logspace(3, 8.5, 220) if f is None else f
        t = np.array([self.loop_gain(fi, sources, model, op) for fi in f])
        mag, ph = np.abs(t), np.degrees(np.unwrap(np.angle(t)))
        i = int(np.argmax(mag < 1))
        if i == 0:
            return float("nan"), float("nan")
        w = math.log(mag[i - 1]) / (math.log(mag[i - 1]) - math.log(mag[i]))
        fc = f[i - 1] * (f[i] / f[i - 1]) ** w
        return 180 + ph[i - 1] + w * (ph[i] - ph[i - 1]), fc

    def noise_psd(self, f, sources, model, out, en, temp_k=313.0, src_noise=None):
        """Output noise PSD (V^2/Hz) at net out and its parts: resistors, op-amps (en, in), sources
        (src_noise {source net: V/rtHz})."""
        Y, nodes, idx, src = self.ac_matrix(f, sources, model)
        N, S = len(nodes), len(src)
        e = np.zeros(Y.shape[0], complex)
        e[idx[out]] = 1
        x = np.linalg.solve(Y.T, e)
        xv = lambda n: x[idx[n]] if n in idx else 0.0
        parts = {"resistors": 0.0, "op-amps": 0.0, "sources": 0.0}
        for a, b, ohm, _ in self.R:
            parts["resistors"] += abs(xv(a) - xv(b)) ** 2 * 4 * KB * temp_k / ohm
        s = 2j * math.pi * f
        for j, o in enumerate(self.ops):
            parts["op-amps"] += abs(x[N + S + j] * model.A(s)) ** 2 * en ** 2
            parts["op-amps"] += (abs(xv(o["p"])) ** 2 + abs(xv(o["m"])) ** 2) * TL_IN ** 2
        for k, n in enumerate(src):
            if src_noise and n in src_noise:
                parts["sources"] += abs(x[N + k]) ** 2 * src_noise[n] ** 2
        return sum(parts.values()), parts


# ================================================================================================== misc
def track_pf_per_mm(w=0.3e-3, h=1.6e-3, er=4.5, gap=0.254e-3):
    """Capacitance to ground of a track among ground pours (grounded coplanar, conformal mapping; Wadell,
    Transmission Line Design Handbook), pF/mm. The stereo mixer suite's formula, the worst of its two models."""
    def ellipk(k):
        a, b = 1.0, math.sqrt(1 - k * k)
        for _ in range(30):
            a, b = (a + b) / 2, math.sqrt(a * b)
        return math.pi / (2 * a)
    e0 = 8.854e-12
    a, b = w / 2, w / 2 + gap
    k, k1 = a / b, math.tanh(math.pi * a / (2 * h)) / math.tanh(math.pi * b / (2 * h))
    r = ellipk(k) / ellipk(math.sqrt(1 - k * k))
    r1 = ellipk(k1) / ellipk(math.sqrt(1 - k1 * k1))
    return (2 * e0 * r + 2 * e0 * er * r1) * 1e12 / 1e3


C_PAD = 0.5e-12          # F, a THT pad among pours (estimate, upper end; the stereo mixer suite's figure)
C_VIA = 0.3e-12          # F, a 0.61 / 0.3 mm via (estimate)
C_HDR = 1.0e-12          # F, a mated 2.54 mm header pin pair (estimate)
_caps = None


def net_caps():
    """Stray capacitance to ground per merged net from the routed master (track length x pF/mm + pads + vias
    + mated header pins), F; and {net: (mm, pads, vias)}."""
    global _caps
    if _caps is None:
        pf = track_pf_per_mm()
        R = harness.routed()
        caps, info = {}, {}
        for b in (R.main, R.face):
            for n, st in b.net_stats().items():
                m = node(n)
                caps[m] = caps.get(m, 0.0) + st["length"] * pf * 1e-12 + st["vias"] * C_VIA
                L, pads, vias = info.get(m, (0.0, 0, 0))
                info[m] = (L + st["length"], pads, vias + st["vias"])
            for p in b.pads:
                if p.net:
                    m = node(p.net)
                    caps[m] = caps.get(m, 0.0) + C_PAD
                    L, pads, vias = info.get(m, (0.0, 0, 0))
                    info[m] = (L, pads + 1, vias)
        for ref, kind, pins in CIRCUIT.HEADERS:
            for mb, fb in pins:
                if mb:
                    caps[mb] = caps.get(mb, 0.0) + C_HDR
        _caps = (caps, info, pf)
    return _caps
