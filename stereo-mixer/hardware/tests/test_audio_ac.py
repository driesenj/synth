"""audio_ac: AC behaviour, stability and noise of the stereo mixer (Mycelium) by complex nodal analysis.

What it checks
  - frequency response 20 Hz - 20 kHz of every input -> output path at the worst pot positions, with the
    summers' 22 p, the CD4053B mute switches (Ron, pin and feedthrough capacitances) on the summing nodes, the
    TL074's input capacitance, open-loop gain / output impedance, and PCB stray capacitance per net;
  - what the switches' capacitance costs at 20 kHz (with against without it), the summing node's capacitance
    against the doc's "about 125 pF with the lane";
  - the summing nodes' (the switches' x pins') own swing at 20 kHz with every channel up and the summers at
    their full swing, against the doc's "within about 30 mV", and from it a first-principles bound on the
    distortion the switch's Ron adds;
  - mute attenuation against frequency (20 Hz, 1 kHz, 20 kHz) of every channel, Ron typical and worst
    (85 C), against the doc's "drops by X dB typically, Y dB at worst"; the bleed of a stray 0.1 pF from a
    muted channel's track into a playing bus;
  - op-amp stability: the loop gain of every TL074 section in the whole circuit (followers with their
    pan / SEND / track load, summers with their summing-node capacitance and 22 p, playing and with every
    channel muted, output stages and the send inverter driving 1k + a patch cable): phase margin, and the
    doc's worst-case figures;
  - slew rate at full scale and 20 kHz;
  - output noise at OUT L / OUT R / SEND with every channel up and with every channel muted (TL074 en and
    in, Johnson noise of every resistor, pot track and closed switch), as dBu and SNR against 10 V p-p.

How the model is built
  circuit.py's netlist (both boards), header nets merged (X_F == X, GND_F == GND), power rails as AC
  ground, the latch left out (it only drives the switches' selects, QK nets; the mute state is a build()
  argument). Each TL074 section is a two-pole VCVS with its open-loop output resistance and input
  capacitance. Each CD4053B section: common <-> x Ron while its channel plays (R_OFF || 0.2 pF while muted),
  common <-> y the reverse, 5 pF from each x / y pin and 9 pF from the common to ground. Pots are two
  resistors at a wiper fraction a (0 = wiper on pin 1, the CCW end). Inputs are 1k sources (a typical
  Eurorack output); unpatched jacks take their switch-lug net. Stray capacitance per net = track length x
  pF/mm (computed below for 0.3 mm tracks on 1.6 mm FR4) + pads + vias + mated header pins. Track length is
  the routed length on a routed board; on a board that is only placed (the main board since the 2026-11-15
  re-placement) it is estimated from the pads (rectilinear minimum spanning tree x 1.3), and a check says so.

Not modelled: ground-impedance and supply crosstalk, capacitive coupling between tracks (crosstalk, a muted
  channel's tracks into a playing bus: the bleed check prices one 0.1 pF), the latch's switching transients
  and the CD4053B's select-to-signal spike (65 mV peak into 10k, SCHS047O), the CD4053B's rON against the
  signal voltage (estimated by hand, labelled), its leakage as a current, op-amp poles beyond the second,
  temperature drift, pot tolerance and wiper noise, EMI, the TL074's own distortion and its input
  capacitance's voltage dependence, the next module's input beyond 100k || 50 pF.

Run from stereo-mixer/hardware/tests:  python test_audio_ac.py
"""
import collections
import math
import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # small matrices: BLAS threads only cost time (100x here)
import numpy as np

import harness
from audio_dc_solver import R_OFF as CD_R_OFF, R_OFF_25C, R_OFF_85C       # the open throw: why 1 Gohm, there

ck = harness.Checks("audio_ac")
circuit = harness.load("circuit")

# ---------------------------------------------------------------------------------------------- constants
# TL074, TI SLOS080W (rev. July 2025), www.ti.com/lit/ds/symlink/tl074.pdf. The DIP-14 TL074CN is one of
# "all other devices" in the TL07xC/AC/BC/I tables (not a PS/NS package, not an M grade).
GBW_NEW = 5.25e6        # Hz, typ, TL07xH / current die, 5.7 / 5.9 tables
GBW_OLD = 3.0e6         # Hz, typ, the legacy figure (PS/NS packages, M grade, older stock)
AOL = 2e5               # V/V, 200 V/mV typ (TL07xC, RL >= 2k); 120 dB on the H tables: the lower is used
PM_UNITY = 56.0         # deg, typ, phase margin at G = +1, RL = 10k, CL = 20 pF
ZO_OL = 125.0           # ohm, typ, open-loop output impedance at 1 MHz, IO = 0
SR_MIN = 8e6            # V/s, MIN, TL07xC/AC/BC/I, VI = 10 V, RL = 2k, CL = 100 pF (typ 20 V/us)
EN_1K = 37e-9           # V/rtHz, typ at 1 kHz, "all other devices" (18 nV only for PS/NS packages)
EN_10K = 21e-9          # V/rtHz, typ at 10 kHz
IN_NOISE = 80e-15       # A/rtHz, typ at 1 kHz (H table; the legacy table gives 10 fA)
C_ID = 2e-12            # F, differential input capacitance, typ (ZID = 100 M || 2 pF)
C_ICM = 1e-12           # F, common-mode input capacitance per input, typ (ZICM = 6 T || 1 pF)
V_SWING = 10.5          # V peak, a TL074 swing on the chips' ~11.5 V rails (design.md: about +-10 V; the higher is used)

# CD4053B, TI SCHS047O (rev. O, May 2026), 5.5, VEE = VSS = 0. rON at VDD = 10 V, 0 <= VIS <= VDD (the chips
# get 11-11.6 V; rON falls as VDD rises, so the 10 V column is the conservative one): typ 180, max 400 at 25 C,
# max 520 at 85 C.
CD_RON_TYP, CD_RON_MAX_25C, CD_RON_MAX_85C = 180.0, 400.0, 520.0
# Capacitance, VDD = 10 V, 25 C, typ (no min / max given): CIS 5 pF on a channel pin (x or y), COS 9 pF on the
# common (CD4053), CIOS 0.2 pF feedthrough across an open throw.
CD_CIS, CD_COS, CD_CIOS = 5e-12, 9e-12, 0.2e-12
# rON against the signal voltage near VIS = 0: rev. O has no curve for it, so a first-principles bound. Near 0 V
# only the n-channel half of the transmission gate conducts (the p-channel's |VGS| is about VIS), and
# rON ~ 1 / (VDD - VIS - VT): with VDD 11 V and VT up to 3 V (metal-gate CD4000B) 1/8 per volt, doubled for the
# body effect: 0.25 / V. An estimate, used only for the distortion bound below.
CD_RON_SLOPE = 0.25

# Board and wiring (estimates, see track_pf_per_mm())
ER_FR4 = 4.5            # FR4 relative permittivity near 1 MHz (typ 4.2-4.7)
H_FR4 = 1.6e-3          # m, board thickness (standard; the export does not say otherwise)
W_TRACK = 0.3e-3        # m, signal track width on both boards (copper_audit: 0.3 mm)
GAP_POUR = 0.254e-3     # m, track-to-pour gap (the export's 10 mil rule entry; conservative: more C)
C_PAD = 0.5e-12         # F, a THT pad among the pours (estimate, upper end)
C_VIA = 0.3e-12         # F, a 0.61 / 0.3 mm via (estimate)
C_HDR = 1.0e-12         # F, a mated 2.54 mm header pin pair to its neighbours (estimate)
R_SOURCE = 1e3          # ohm, a typical Eurorack output's series resistor
C_CABLE = 100e-12       # F, 1 m patch cable (~100 pF/m)
C_NEXT, R_NEXT = 50e-12, 100e3      # the next module's input
T_K = 313.0             # K, inside a warm case (40 C)
KB = 1.380649e-23

# Criteria (first principles; the doc's own AC figures are read from design.md below)
FLAT_DB = 0.5           # every path flat within +-0.5 dB, 20 Hz - 20 kHz, at any pot position
PM_MIN = 45.0           # deg: the usual minimum for no ringing / peaking (the datasheet's follower is 56)
THD_MAX = 1e-4          # 0.01 %: a passive part must not add more than ~3x the TL07x's own 0.003 % THD+N
SNR_UP_MIN = 80.0       # dB re 10 V p-p, 20 Hz - 20 kHz unweighted, every channel up
SNR_MUTED_MIN = 90.0    # dB re 10 V p-p, every channel muted (the module's own floor)
V_REF_RMS = 10 / 2 / math.sqrt(2)   # 10 V p-p sine = 3.54 V rms = +13.2 dBu


def dbu(v):
    return 20 * math.log10(v / 0.7746)


# The doc's own figures, read from design.md (so the checks follow the doc, not a copy of it)
import re
with open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf8") as _f:
    DOC = " ".join(_f.read().split())
_m = re.search(r"the on-resistance \((\d+) Ω typical, (\d+) Ω max at VDD = 10 V and 25 °C, (\d+) Ω at 85 °C\)", DOC)
DOC_RON = tuple(float(x) for x in _m.groups()) if _m else (float("nan"),) * 3
_m = re.search(r"drops by (\d+) dB typically, (\d+) dB at worst", DOC)
DOC_MUTE_TYP, DOC_MUTE_MAX = (float(_m.group(1)), float(_m.group(2))) if _m else (float("nan"), float("nan"))
_m = re.search(r"a pole at (\d+) kHz", DOC)
DOC_SUM_POLE_KHZ = float(_m.group(1)) if _m else float("nan")
_m = re.search(r"hold their virtual earth within about (\d+) mV at (\d+) kHz", DOC)
DOC_VE_MV, DOC_VE_KHZ = (float(_m.group(1)), float(_m.group(2))) if _m else (float("nan"), 20.0)
_m = re.search(r"about (\d+) pF with the lane", DOC)
DOC_SUM_PF = float(_m.group(1)) if _m else float("nan")
_m = re.search(r"is (\d+)° on the send inverter and (\d+)° on OUT L / R", DOC)
DOC_PM_S, DOC_PM_LR = (float(_m.group(1)), float(_m.group(2))) if _m else (float("nan"), float("nan"))
_m = re.search(r"so ([\d.]+) pF from a muted channel's track into a playing bus is −(\d+) dB of bleed at (\d+) kHz", DOC)
DOC_BLEED = (float(_m.group(1)) * 1e-12, float(_m.group(2)), float(_m.group(3)) * 1e3) if _m else (0.1e-12, float("nan"), 1e4)


# ---------------------------------------------------------------------------- stray capacitance per net
def _ellipk(k):
    """Complete elliptic integral K(k) by the arithmetic-geometric mean."""
    a, b = 1.0, math.sqrt(1 - k * k)
    for _ in range(30):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return math.pi / (2 * a)


def track_pf_per_mm():
    """(microstrip, grounded coplanar) capacitance to ground of a 0.3 mm track on 1.6 mm FR4, pF/mm.

    Microstrip: Hammerstad (w/h < 1). Grounded coplanar with the pour GAP_POUR away on both sides and the
    other layer's pour below: the conformal-mapping formula (Wadell, Transmission Line Design Handbook)."""
    c0, e0 = 299792458.0, 8.854e-12
    w, h, er = W_TRACK, H_FR4, ER_FR4
    eeff = (er + 1) / 2 + (er - 1) / 2 * ((1 + 12 * h / w) ** -0.5 + 0.04 * (1 - w / h) ** 2)
    z0 = 60 / math.sqrt(eeff) * math.log(8 * h / w + w / (4 * h))
    ms = math.sqrt(eeff) / (c0 * z0) * 1e12 / 1e3
    a, b = w / 2, w / 2 + GAP_POUR
    k, k1 = a / b, math.tanh(math.pi * a / (2 * h)) / math.tanh(math.pi * b / (2 * h))
    r = _ellipk(k) / _ellipk(math.sqrt(1 - k * k))
    r1 = _ellipk(k1) / _ellipk(math.sqrt(1 - k1 * k1))
    # C = eeff (K(k)/K(k') + K(k1)/K(k1')) / (60 pi c) = 2 e0 (K(k)/K(k') + er K(k1)/K(k1'))
    cpw = 2 * e0 * r + 2 * e0 * er * r1          # F/m: air above (both gaps) + dielectric below (to the plane)
    return ms, cpw * 1e12 / 1e3


def routed_boards():
    ca = harness.load("copper_audit")
    docs = harness.read_export()
    fps = ca.footprints_of(docs)
    boards = ca.boards_of(docs, fps)
    main = next(b for t, b in boards.items() if "Main" in t)
    face = next(b for t, b in boards.items() if "Faceplate" in t)
    return main, face


def base(net):
    if net in ("GND_F",):
        return "GND"
    return net[:-2] if net.endswith("_F") else net


# Estimate: a routed net runs about 1.3 x its rectilinear minimum spanning tree (round parts, vias). For SUM_L / R /
# S the MST strings the eight x pins together along the switch row; the route the routing notes plan (a lane at
# y 63-66 above the switches, a tap down from each x pin under its chip) is longer still, so this is not an upper bound.
DETOUR = 1.3


def rmst(pts):
    """Length of the rectilinear (Manhattan) minimum spanning tree over the points, mm (Prim)."""
    if len(pts) < 2:
        return 0.0
    d = [float("inf")] * len(pts)
    d[0], todo, total = 0.0, set(range(len(pts))), 0.0
    while todo:
        i = min(todo, key=lambda j: d[j])
        todo.discard(i)
        total += d[i]
        for j in todo:
            d[j] = min(d[j], abs(pts[i][0] - pts[j][0]) + abs(pts[i][1] - pts[j][1]))
    return total


def net_caps(pf_mm):
    """Stray capacitance to ground per (merged) net, F, and the per-net breakdown
    [routed track mm, pads, vias, header pins, estimated track mm]. A board with tracks gives its routed lengths;
    a board with none (placed, not routed) gets DETOUR x the rectilinear MST over each net's pads, no vias."""
    main, face = routed_boards()
    caps, info = collections.defaultdict(float), collections.defaultdict(lambda: [0.0, 0, 0, 0, 0.0])
    for b in (main, face):
        if b.tracks:
            for n, s in b.net_stats().items():
                nb = base(n)
                caps[nb] += s["length"] * pf_mm * 1e-12 + s["vias"] * C_VIA
                info[nb][0] += s["length"]
                info[nb][2] += s["vias"]
        else:
            pts = collections.defaultdict(list)
            for p in b.pads:
                if p.net:
                    pts[p.net].append((p.x, p.y))
            for n, xy in pts.items():
                est = DETOUR * rmst(xy)
                caps[base(n)] += est * pf_mm * 1e-12
                info[base(n)][4] += est
        for p in b.pads:
            if p.net:
                caps[base(p.net)] += C_PAD
                info[base(p.net)][1] += 1
    for ref, kind, pins in circuit.HEADERS:
        for mb, fb in pins:
            caps[mb] += C_HDR
            info[mb][3] += 1
    return caps, info


# ---------------------------------------------------------------------------------------- the MNA engine
class Opamp:
    def __init__(self, gbw, pm=PM_UNITY, a0=AOL, zo=ZO_OL):
        self.gbw, self.a0, self.zo = gbw, a0, zo
        self.w1 = 2 * math.pi * gbw / a0
        self.w2 = self._fit_w2(pm)

    def A(self, s, w2=None):
        return self.a0 / ((1 + s / self.w1) * (1 + s / (w2 or self.w2)))

    def _fit_w2(self, pm):
        """Second pole so that a follower into 10k || 20 pF (the datasheet's condition) has phase margin pm."""
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
    """A linear AC netlist: R, C, independent V sources, op-amp sections (VCVS + output R + input C)."""

    def __init__(self):
        self.nodes = {}
        self.R, self.C, self.V, self.ops = [], [], [], []

    def n(self, name):
        if name == "GND":
            return -1
        if name not in self.nodes:
            self.nodes[name] = len(self.nodes)
        return self.nodes[name]

    def r(self, a, b, val, tag=""):
        if a != b and not (a == "GND" and b == "GND"):
            self.R.append((self.n(a), self.n(b), float(val), tag))

    def c(self, a, b, val):
        if a != b and val > 0:
            self.C.append((self.n(a), self.n(b), float(val)))

    def v(self, node, val=1.0, name=""):
        self.V.append((self.n(node), val, name))

    def opamp(self, name, inp, inm, out, model):
        internal = name + ".int"
        self.ops.append((name, self.n(inp), self.n(inm), self.n(internal), model))
        self.r(internal, out, model.zo, tag="ZO")
        self.c(inp, "GND", C_ICM)
        self.c(inm, "GND", C_ICM)
        self.c(inp, inm, C_ID)

    def matrix(self, f, break_op=None):
        """MNA matrix at frequency f. break_op: the op-amp whose VCVS becomes an independent 1 V source."""
        s = 2j * math.pi * f
        N, M = len(self.nodes), len(self.V) + len(self.ops)
        if getattr(self, "_gc", None) is None or self._gc[0].shape[0] != N + M:
            G, Cm = np.zeros((N + M, N + M)), np.zeros((N + M, N + M))

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
            for a, b, val in self.C:
                stamp(Cm, a, b, val)
            self._gc = (G, Cm)
        Y = self._gc[0] + s * self._gc[1]
        k = N
        for node, val, name in self.V:
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

    def rhs(self, which=None):
        N = len(self.nodes)
        b = np.zeros(N + len(self.V) + len(self.ops), complex)
        for i, (node, val, name) in enumerate(self.V):
            if which is None or name == which:
                b[N + i] = val
        return b

    def solve(self, f, which=None):
        return np.linalg.solve(self.matrix(f), self.rhs(which))

    def gain(self, f, out, which=None):
        x = self.solve(f, which)
        return x[self.nodes[out]]

    def loop_gain(self, f, opname):
        """T = -A (V+ - V-) with the op-amp's VCVS replaced by a 1 V source (every other source at 0)."""
        Y = self.matrix(f, break_op=opname)
        N = len(self.nodes)
        b = np.zeros(Y.shape[0], complex)
        k = N + len(self.V) + [o[0] for o in self.ops].index(opname)
        b[k] = 1.0
        x = np.linalg.solve(Y, b)
        name, p, m, o, model = self.ops[k - N - len(self.V)]
        vd = (x[p] if p >= 0 else 0) - (x[m] if m >= 0 else 0)
        return -model.A(2j * math.pi * f) * vd


# --------------------------------------------------------------------------------- the circuit as a Net
MAIN_PARTS = circuit.main_board_parts()
AUDIO_SKIP = ("BTN", "DB", "QK", "LED", "CK", "QN", "POR")
AC_GROUND = {"+12V", "-12V", "P12_IN", "N12_IN", "P12_D", "N12_D", "GND", "GND_F"}


def _node(net):
    return "GND" if net in AC_GROUND else base(net)


def build(model, caps, pots=None, patched=None, mutes=(), ron=CD_RON_TYP, switch_c=True, r_off=CD_R_OFF, load=True,
          src=R_SOURCE, extra_cable=0.0, extra_c=(), skip=()):
    """The whole mixer as a Net.

    pots: {ref or ref+'B' (dual gang B): wiper fraction a, 0 = wiper on pin 1 (pin 4 for gang B)}; default 1.
    patched: {jack ref: source name}; a patched jack gets a source V (name) behind src ohms. Others take their
    switch lug (or float, for the outputs). mutes: channel numbers muted (their CD4053B's y throws closed).
    ron: every closed throw; switch_c: the CD4053B's pin and feedthrough capacitances in or out; r_off: an
    open throw's conduction."""
    pots, patched = pots or {}, patched or {}
    net = Net()
    for p in MAIN_PARTS:
        if p.ref in skip:
            continue                          # a part left out, to price it
        if p.kind == "CD4053":
            # the selects are on QKk (the latch); the switch sections are audio
            for bus, (com, x, y, sel) in circuit.MUX.items():
                k = int(p.nets[sel][2:])
                c_, x_, y_ = _node(p.nets[com]), _node(p.nets[x]), _node(p.nets[y])
                on, off = (y_, x_) if k in mutes else (x_, y_)
                net.r(c_, on, ron, tag=f"{p.ref}.{bus}")
                net.r(c_, off, r_off, tag=f"{p.ref}.{bus}.off")
                if switch_c:
                    net.c(c_, off, CD_CIOS)
                    net.c(x_, "GND", CD_CIS)
                    net.c(y_, "GND", CD_CIS)
                    net.c(c_, "GND", CD_COS)
            continue
        if any(_node(n).startswith(AUDIO_SKIP) for n in p.nets.values()):
            continue                          # the latch
        if p.kind == "R":
            net.r(_node(p.nets["1"]), _node(p.nets["2"]), harness.ohms(p.value), tag=p.ref)
        elif p.kind == "C":
            net.c(_node(p.nets["1"]), _node(p.nets["2"]), harness.farads(p.value))
    for (u, s), (kind, name) in circuit.OPAMPS.items():
        out, inm, inp = circuit.SECTION[s]
        nets = next(p for p in MAIN_PARTS if p.ref == u).nets
        net.opamp(f"{u}.{s}", _node(nets[inp]), _node(nets[inm]), _node(nets[out]), model)
    # faceplate: pots, jacks
    def pot(ref, cw, w, ccw, a, R):
        a = min(max(a, 0.0), 1.0)
        net.r(_node(ccw), _node(w), max(a * R, 0.5), tag=ref)
        net.r(_node(w), _node(cw), max((1 - a) * R, 0.5), tag=ref)
    for ref, label, value, (cw, w, ccw) in circuit.POTS:
        pot(ref, cw, w, ccw, pots.get(ref, 1.0), harness.ohms(value))
    for ref, label, value, ga, gb in circuit.POTS2:
        pot(ref, ga[0], ga[1], ga[2], pots.get(ref, 1.0), harness.ohms(value))
        pot(ref + "B", gb[0], gb[1], gb[2], pots.get(ref + "B", pots.get(ref, 1.0)), harness.ohms(value))
    for ref, label, tip, lug in circuit.JACKS:
        t = _node(tip)
        if ref in patched:
            net.v(ref + ".src", 1.0, patched[ref])
            net.r(ref + ".src", t, src, tag=ref + ".src")
        elif ref in ("J15", "J16", "J17"):
            if load:                                  # 1 m patch cable into the next module
                net.c(t, "GND", C_CABLE + C_NEXT + extra_cable)
                net.r(t, "GND", R_NEXT, tag=ref + ".load")
        elif lug:
            net.r(t, _node(lug), 1e-3, tag=ref + ".lug")
    for a, b, val in extra_c:               # (net, net, F): a proposed fix
        net.c(a, b, val)
    for name in list(net.nodes):
        if name in caps:
            net.c(name, "GND", caps[name])
    return net


# ================================================================================================= checks
ms, cpw = track_pf_per_mm()
ck.check("track capacitance per mm is in the textbook range for 0.3 mm on 1.6 mm FR4",
         0.03 <= ms <= 0.07 and ms < cpw <= 0.15,
         f"expected microstrip 0.03-0.07 pF/mm and coplanar-with-pour above it, <= 0.15; got microstrip "
         f"{ms:.3f}, grounded coplanar (gap {GAP_POUR * 1e3:.2f} mm) {cpw:.3f} pF/mm; using {cpw:.3f} (worst)")
PF_MM = cpw
caps, info = net_caps(PF_MM)
for n in ("SUM_L", "SUM_R", "SUM_S", "NO_L", "NO_S", "BL1", "BS8", "FI1", "LV5", "CH1", "CH7L", "PL1", "OUT_R", "MIX_R"):
    L, pads, vias, hdr, est = info[n]
    print(f"      stray {n:6}: {L:6.1f} mm routed + {est:6.1f} mm estimated track, {pads:2d} pads, {vias} vias, "
          f"{hdr} header pins -> {caps[n] * 1e12:5.1f} pF")
SUMN = ("SUM_L", "SUM_R", "SUM_S", "NO_L", "NO_R", "NO_S")
ck.check("every summing node's stray capacitance comes from routed tracks, not a placement estimate",
         all(info[n][0] > 0 and info[n][4] == 0 for n in SUMN),
         "expected routed track on SUM_L/R/S and NO_L/R/S; got " +
         ", ".join(f"{n} {info[n][0]:.0f} mm routed / {info[n][4]:.0f} mm estimated" for n in SUMN) +
         " (the main board in the routed master is placed, not routed: its lengths are rectilinear MST x "
         f"{DETOUR} estimates)")

OP_NEW, OP_OLD = Opamp(GBW_NEW), Opamp(GBW_OLD)
print(f"      TL074 model: second pole {OP_NEW.w2 / 2 / math.pi / 1e6:.2f} MHz (GBW 5.25 MHz), "
      f"{OP_OLD.w2 / 2 / math.pi / 1e6:.2f} MHz (GBW 3 MHz), for {PM_UNITY:.0f} deg at G = +1")

# ------------------------------------------------------------------------------- 1. frequency response
F_CHECK = [20.0, 100.0, 1e3, 5e3, 10e3, 15e3, 20e3]
LEVELS = [0.03, 0.06, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


def response(net, out, which=None):
    """dB of |H(f)| / |H(1 Hz)| at F_CHECK (DC-coupled: 1 Hz is the flat reference)."""
    h0 = abs(net.gain(1.0, out, which))
    return [harness.db(abs(net.gain(f, out, which)) / h0) for f in F_CHECK]


def worst(devs):
    return max(devs, key=abs)


PATHS = []          # (name, patched jacks, output node, pot to sweep, fixed pots)
for k in circuit.MONO:
    lvl, pan, snd = f"RV{3 * k - 2}", f"RV{3 * k - 1}", f"RV{3 * k}"
    PATHS += [(f"IN {k} -> OUT L (pan hard L)", [f"J{k}"], "OUT_L", lvl, {pan: 0.0}),
              (f"IN {k} -> OUT R (pan centre)", [f"J{k}"], "OUT_R", lvl, {pan: 0.5}),
              (f"IN {k} -> SEND (SEND full)", [f"J{k}"], "SEND", lvl, {pan: 0.5, snd: 1.0}),
              (f"IN {k} -> SEND (SEND swept, LEVEL full)", [f"J{k}"], "SEND", snd, {pan: 0.5})]
for c, (lvl, snd, jl, jr) in ((7, ("RV19", "RV20", "J7", "J8")), (8, ("RV21", "RV22", "J9", "J10"))):
    PATHS += [(f"IN {c} L -> OUT L", [jl], "OUT_L", lvl, {}), (f"IN {c} R -> OUT R", [jr], "OUT_R", lvl + "B", {}),
              (f"IN {c} L -> SEND", [jl], "SEND", lvl, {}), (f"IN {c} L -> SEND (SEND swept)", [jl], "SEND", snd, {})]
PATHS += [("RETURN L -> OUT L", ["J11"], "OUT_L", "RV23", {}), ("RETURN R -> OUT R", ["J12"], "OUT_R", "RV23B", {}),
          ("DRUMS -> OUT L", ["J13"], "OUT_L", "RV24", {}), ("DRUMS -> OUT R", ["J13"], "OUT_R", "RV24", {}),
          ("FX IN -> SEND", ["J14"], "SEND", None, {}),
          ("IN 1 -> OUT L, MASTER swept", ["J1"], "OUT_L", "RV25", {"RV2": 0.0}),
          ("IN 7 R -> OUT R, MASTER swept", ["J8"], "OUT_R", "RV25B", {})]

flat_rows = []
for name, jacks, out, sweep, fixed in PATHS:
    rows = []
    for a in (LEVELS if sweep else [None]):
        pots = dict(fixed)
        if sweep:
            pots[sweep] = a
        net = build(OP_NEW, caps, pots=pots, patched={j: "in" for j in jacks})
        d = response(net, out)
        rows.append((abs(worst(d)), worst(d), d[-1], a))
    m = max(rows)
    flat_rows.append((name, m))
    ck.check(f"flat 20 Hz-20 kHz within {FLAT_DB} dB: {name}", m[0] <= FLAT_DB,
             f"expected |deviation| <= {FLAT_DB} dB at every position; worst {m[1]:+.2f} dB "
             f"(at 20 kHz {m[2]:+.2f} dB) with the swept pot at a = {m[3]}")

# The CD4053Bs' share: the same paths with and without the switches' capacitances (every channel playing, so
# every common's 9 pF sits on its bus beside the eight x pins' 5 pF), both TL074 models
share = []
for name, jacks, out, fixed in (("IN 1 -> OUT L (pan hard L)", ["J1"], "OUT_L", {"RV2": 0.0}),
                                ("IN 5 -> OUT R (pan centre)", ["J5"], "OUT_R", {"RV14": 0.5}),
                                ("IN 7 L -> OUT L", ["J7"], "OUT_L", {}),
                                ("IN 1 -> SEND", ["J1"], "SEND", {"RV2": 0.5}),
                                ("FX IN -> SEND", ["J14"], "SEND", {}),
                                ("RETURN L -> OUT L", ["J11"], "OUT_L", {})):
    for model, mname in ((OP_NEW, "GBW 5.25 MHz"), (OP_OLD, "GBW 3 MHz")):
        w = response(build(model, caps, pots=fixed, patched={j: "in" for j in jacks}), out)[-1]
        wo = response(build(model, caps, pots=fixed, patched={j: "in" for j in jacks}, switch_c=False), out)[-1]
        share.append((abs(w - wo), w - wo, name, mname, w, wo))
s = max(share)
ck.check("the CD4053Bs' capacitance on the summing nodes costs < 0.1 dB at 20 kHz", s[0] < 0.1,
         f"expected |with - without| < 0.1 dB; worst {s[1]:+.3f} dB on {s[2]} ({s[3]}: {s[4]:+.3f} dB at 20 kHz "
         f"with CIS {CD_CIS * 1e12:.0f} / COS {CD_COS * 1e12:.0f} / CIOS {CD_CIOS * 1e12:.1f} pF, {s[5]:+.3f} dB "
         f"without)")
# The summing node's capacitance to ground, every channel playing: its own stray (the lane), the op-amp's input
# C (IN- to GND, and to IN+ = GND), each switch's x pin, and each playing common (9 pF) with its B net's stray,
# which Ron (180 ohm) ties to the node far beyond 20 kHz
CH_ALL = circuit.MONO + circuit.STEREO
for bus in ("L", "R", "S"):
    sw_x = len(CH_ALL) * CD_CIS
    sw_c = len(CH_ALL) * CD_COS
    bnets = sum(caps[f"B{bus}{k}"] for k in CH_ALL)
    lane = caps[f"SUM_{bus}"]
    tot = lane + C_ICM + C_ID + sw_x + sw_c + bnets
    print(f"      SUM_{bus} to ground, every channel playing: {tot * 1e12:.0f} pF = lane + pads {lane * 1e12:.1f} "
          f"({info[f'SUM_{bus}'][4]:.0f} mm estimated) + x pins {sw_x * 1e12:.0f} + commons {sw_c * 1e12:.0f} + "
          f"B nets {bnets * 1e12:.1f} + TL074 {(C_ICM + C_ID) * 1e12:.0f}; every channel muted "
          f"{(lane + C_ICM + C_ID + sw_x) * 1e12:.0f} pF")
    if bus == "L":
        ck.close(f"the summing node's capacitance, every channel playing (doc: 'about {DOC_SUM_PF:.0f} pF with the "
                 f"lane'), SUM_L, within 10 %", tot * 1e12, DOC_SUM_PF, 0.1 * DOC_SUM_PF, " pF")
# The summers' 22 p alone: the pole the doc names (72 kHz) costs this much at 20 kHz
_pm = {p.ref: p for p in MAIN_PARTS}
fps = [1 / (2 * math.pi * harness.ohms(_pm[r].value) * harness.farads(_pm[c].value))
       for r, c in (("R901", "C901"), ("R902", "C902"), ("R903", "C903"))]
fp = max(fps)
ck.close(f"the summers' Rf || Cf pole frequency, circuit.py R901-R903 / C901-C903 (doc: {DOC_SUM_POLE_KHZ:.0f} kHz)",
         min(fps) / 1e3, DOC_SUM_POLE_KHZ, 1.0, " kHz")
print(f"      100k || 22p alone: {harness.db(1 / abs(1 + 1j * 20e3 / fp)):+.2f} dB at 20 kHz per summer stage")


# ---------------------------------------------- 2. the switches' x pins: virtual-earth swing and Ron distortion
# Every channel up (one source into every input, pans centred, every pot full): the summing node's voltage against
# its summer's output at the doc's frequency. An op-amp holds its inverting input at Vout / A(f), so this is about
# the summer's swing / 262 (GBW 5.25 MHz) or / 150 (3 MHz) at 20 kHz. "Full output" taken as the summer's own
# clip level (V_SWING peak, the worst case and what the doc's sentence is about); the same at 10 V p-p at OUT L / R
# (MIX_L / R at 2.5 V peak, MASTER full) and at SEND (MIX_S 5 V peak) is printed.
f_ve = DOC_VE_KHZ * 1e3
inputs = [j for j, *_ in circuit.JACKS if j not in ("J15", "J16", "J17")]
pans_c = {f"RV{3 * k - 1}": 0.5 for k in circuit.MONO}
ve = []
for model, mname in ((OP_NEW, "GBW 5.25 MHz"), (OP_OLD, "GBW 3 MHz")):
    net = build(model, caps, pots=pans_c, patched={j: "in" for j in inputs})
    x = net.solve(f_ve)
    for bus, nominal in (("L", 2.5), ("R", 2.5), ("S", 5.0)):
        r = abs(x[net.nodes[f"SUM_{bus}"]]) / abs(x[net.nodes[f"MIX_{bus}"]])
        ve.append((r * V_SWING, r * nominal, bus, mname, r))
vw = max(ve)
print("      summing node at " + f"{f_ve / 1e3:.0f} kHz, every channel up: " +
      ", ".join(f"SUM_{b} {mn}: {v * 1e3:.1f} mV pk at the summer's {V_SWING} V pk, {vn * 1e3:.1f} mV pk at 10 V p-p "
                f"out" for v, vn, b, mn, r in ve))
ck.check(f"the summers hold their virtual earth within the doc's {DOC_VE_MV:.0f} mV at {f_ve / 1e3:.0f} kHz and full "
         f"output (the summer at its {V_SWING} V peak, every channel up)", vw[0] * 1e3 <= DOC_VE_MV,
         f"expected <= {DOC_VE_MV:.0f} mV; got {vw[0] * 1e3:.1f} mV peak on SUM_{vw[2]} ({vw[3]}; "
         f"{min(v[0] for v in ve) * 1e3:.1f} mV with GBW 5.25 MHz); at 10 V p-p at the outputs "
         f"{max(v[1] for v in ve) * 1e3:.1f} mV peak at worst")
# The switch's own distortion, a first-principles bound (labelled as an estimate: the datasheet's 0.2 % THD is for
# a signal through the switch at mid-supply, which this circuit never does). The closed x throw's Ron sits in
# series with the bus resistor R; its terminals swing by the summing node's v_s plus half the drop across it,
# I Ron / 2, and Ron(v) = Ron (1 + CD_RON_SLOPE v). The gain Rf / (R + Ron(v)) then moves by Ron SLOPE v / R, and a
# gain moving in step with the signal makes a second harmonic of half that: H2 <= SLOPE Ron (v_s + I Ron / 2) / 2R.
# Worst throw: a mono channel's follower at the full V_SWING into its 100k, the summer at full swing (the largest
# v_s above), Ron 520 ohm (85 C).
R_BUS = 100e3
i_pk = V_SWING / R_BUS
h2 = {}
for ron in (CD_RON_TYP, CD_RON_MAX_85C):
    for f, vs in ((f_ve, vw[0]), (10e3, vw[0] * 10e3 / f_ve), (1e3, vw[0] * 1e3 / f_ve)):
        h2[(ron, f)] = CD_RON_SLOPE * ron * (vs + i_pk * ron / 2) / (2 * R_BUS)
print("      switch distortion bound (estimate), H2 at full swing: " +
      ", ".join(f"Ron {ron:.0f}: {h2[(ron, f)] * 100:.4f} % at {f / 1e3:.0f} kHz" for ron, f in h2))
ck.check(f"the CD4053B's Ron adds <= {THD_MAX * 100:.2f} % distortion at {f_ve / 1e3:.0f} kHz and full swing, Ron "
         f"{CD_RON_MAX_85C:.0f} ohm (first-principles bound, rON slope {CD_RON_SLOPE} / V assumed)",
         h2[(CD_RON_MAX_85C, f_ve)] <= THD_MAX,
         f"expected <= {THD_MAX * 100:.2f} %; bound {h2[(CD_RON_MAX_85C, f_ve)] * 100:.4f} % "
         f"({harness.db(h2[(CD_RON_MAX_85C, f_ve)]):.0f} dB), from v_s {vw[0] * 1e3:.0f} mV pk + I Ron / 2 "
         f"{i_pk * CD_RON_MAX_85C / 2 * 1e3:.0f} mV; {h2[(CD_RON_TYP, f_ve)] * 100:.4f} % at Ron {CD_RON_TYP:.0f}")


# --------------------------------------------------------------------------- 3. mute attenuation
# Muted, the y throw ties the bus resistor's summing end to GND through Ron and the open x throw (R_OFF || CIOS)
# is the only path into the bus: depth about 1 / (2 pi f CIOS Ron) at 20 kHz, independent of the bus resistor.
F_MUTE = (20.0, 1e3, 20e3)
LEVEL_OF = {7: "RV19", 8: "RV21"}


def mute_att(k, ron, a, jack, pots_extra, r_off=CD_R_OFF, outs=("OUT_L", "SEND")):
    """{(out, f): dB} the channel drops by when it mutes, at LEVEL a; the playing reference has the same Ron."""
    pots = dict(pots_extra)
    pots[LEVEL_OF.get(k, f"RV{3 * k - 2}")] = a
    muted = build(OP_NEW, caps, pots=pots, patched={jack: "in"}, mutes=(k,), ron=ron, r_off=r_off)
    playing = build(OP_NEW, caps, pots=pots, patched={jack: "in"}, ron=ron, r_off=r_off)
    res = {}
    for f in F_MUTE:
        xm, xp = muted.solve(f), playing.solve(f)
        for o in outs:
            res[(o, f)] = harness.db(abs(xp[playing.nodes[o]]) / abs(xm[muted.nodes[o]]))
    return res


for ron, claim, label in ((CD_RON_TYP, DOC_MUTE_TYP, "typical"), (CD_RON_MAX_85C, DOC_MUTE_MAX, "worst (85 C)")):
    rows = []
    for k in circuit.MONO + circuit.STEREO:
        jack = {7: "J7", 8: "J9"}.get(k, f"J{k}")
        extra = {} if k in circuit.STEREO else {f"RV{3 * k - 1}": 0.0}
        for a in (0.1, 0.5, 1.0):
            for (o, f), d in mute_att(k, ron, a, jack, extra).items():
                rows.append((d, k, a, o, f))
    m = min(rows)
    per_f = {f: min(r[0] for r in rows if r[4] == f) for f in F_MUTE}
    hand = 20 * math.log10(1 / (2 * math.pi * 20e3 * CD_CIOS * ron))
    ck.close(f"mute attenuation 20 Hz-20 kHz, Ron {label} ({ron:.0f} ohm), every channel, OUT L and SEND = the doc's "
             f"'{claim:.0f} dB'", m[0], claim, 1.0, " dB")
    print(f"      mute depth, Ron {ron:.0f}: worst {m[0]:.1f} dB (channel {m[1]}, LEVEL a = {m[2]}, {m[3]}, "
          f"{m[4]:.0f} Hz); per frequency " + ", ".join(f"{f:.0f} Hz {d:.1f} dB" for f, d in per_f.items()) +
          f"; by hand 1 / (2 pi 20 kHz CIOS Ron) = {hand:.1f} dB")
for r_off, what in ((R_OFF_25C, "25 C"), (R_OFF_85C, "85 C")):
    d = mute_att(1, CD_RON_MAX_85C, 1.0, "J1", {"RV2": 0.0}, r_off=r_off, outs=("OUT_L",))
    print(f"      sensitivity: R_OFF = the {what} leakage limit read as a resistance ({r_off / 1e6:.0f} Mohm, "
          f"pessimistic): mute depth at Ron {CD_RON_MAX_85C:.0f} " + ", ".join(f"{f:.0f} Hz {d[('OUT_L', f)]:.1f} dB"
                                                                           for f in F_MUTE))
ck.check("the doc's CD4053B rON figures match the datasheet (VDD 10 V: typ, max 25 C, max 85 C)",
         DOC_RON == (CD_RON_TYP, CD_RON_MAX_25C, CD_RON_MAX_85C),
         f"expected {CD_RON_TYP:.0f} / {CD_RON_MAX_25C:.0f} / {CD_RON_MAX_85C:.0f} ohm (SCHS047O 5.5); design.md says "
         + " / ".join(f"{x:.0f}" for x in DOC_RON))
# The doc's routing note: a stray capacitance from a muted channel's track into a playing bus. Channel 1 muted
# (hard left, so PL1 carries its signal) with the doc's 0.1 pF from PL1 to SUM_L, against channel 1 playing.
cb, claim_b, fb = DOC_BLEED
pots_b = {"RV2": 0.0}
playing = build(OP_NEW, caps, pots=pots_b, patched={"J1": "in"})
bleed = build(OP_NEW, caps, pots=pots_b, patched={"J1": "in"}, mutes=(1,), extra_c=[("PL1", "SUM_L", cb)])
quiet = build(OP_NEW, caps, pots=pots_b, patched={"J1": "in"}, mutes=(1,))
b_db = harness.db(abs(bleed.gain(fb, "OUT_L")) / abs(playing.gain(fb, "OUT_L")))
q_db = harness.db(abs(quiet.gain(fb, "OUT_L")) / abs(playing.gain(fb, "OUT_L")))
ck.close(f"bleed: {cb * 1e12:.1f} pF from a muted channel's track (PL1) into a playing bus (SUM_L) at {fb / 1e3:.0f} kHz "
         f"(doc -{claim_b:.0f} dB)", b_db, -claim_b, 1.0, " dB")
print(f"      the same channel muted without that stray: {q_db:.1f} dB at {fb / 1e3:.0f} kHz: a single 0.1 pF of "
      f"layout sets the mute depth, as the doc says")


# ------------------------------------------------------------------------------------ 4. stability
F_LOOP = np.logspace(4, 8.3, 140)


def phase_margin(net, op):
    t = np.array([net.loop_gain(f, op) for f in F_LOOP])
    mag, ph = np.abs(t), np.degrees(np.unwrap(np.angle(t)))
    i = int(np.argmax(mag < 1))
    if i == 0:
        return float("nan"), float("nan")
    w = math.log(mag[i - 1]) / (math.log(mag[i - 1]) - math.log(mag[i]))      # log-interpolate the crossing
    fc = F_LOOP[i - 1] * (F_LOOP[i] / F_LOOP[i - 1]) ** w
    p = ph[i - 1] + w * (ph[i] - ph[i - 1])
    return 180 + p, fc


ROLE = {f"{u}.{s}": f"{kind} {name}" for (u, s), (kind, name) in circuit.OPAMPS.items()}
all_patched = {j: f"s{j}" for j, *_ in circuit.JACKS if j not in ("J15", "J16", "J17")}
CONFIGS = [
    ("all pots full, 1 m cable on the outputs", dict(pots={}, patched=all_patched)),
    ("all pots at mid, pans centred, nothing patched", dict(pots={r: 0.5 for r, *_ in circuit.POTS + circuit.POTS2})),
    ("all pots full, 10 nF extra on every output", dict(pots={}, patched=all_patched, extra_cable=10e-9)),
    ("all pots at mid, every channel muted (the summers see only RETURN / DRUMS / FX IN and the open x pins)",
     dict(pots={r: 0.5 for r, *_ in circuit.POTS + circuit.POTS2}, mutes=tuple(CH_ALL))),
    ("all pots full, every channel muted", dict(pots={}, patched=all_patched, mutes=tuple(CH_ALL))),
]
pm_rows = collections.defaultdict(list)
for model, mname in ((OP_NEW, "GBW 5.25 MHz"), (OP_OLD, "GBW 3 MHz")):
    for cname, kw in CONFIGS:
        net = build(model, caps, **kw)
        for op in [o[0] for o in net.ops]:
            pm, fc = phase_margin(net, op)
            pm_rows[op].append((pm, fc, mname, cname))
for op in sorted(pm_rows, key=lambda o: (o.split(".")[0], int(o.split(".")[1]))):
    pm, fc, mname, cname = min(pm_rows[op])
    ck.check(f"phase margin >= {PM_MIN:.0f} deg: {op} ({ROLE[op]})", pm >= PM_MIN,
             f"expected >= {PM_MIN:.0f} deg; worst {pm:.1f} deg at {fc / 1e6:.2f} MHz ({mname}, {cname})")
# The followers' IN+ (FI) hangs on the 10k input resistor (plus the LEVEL wiper's source resistance) with only its
# pads and the TL074's 1 pF to ground, so the TL074's 2 pF differential input capacitance feeds the output back onto
# IN+ and eats about 12 deg of the follower's margin (the AQY212EH's 20-80 pF off capacitance used to hold FI down).
# What a small C0G from each FI to GND would give, in the followers' worst configuration (a proposed fix, not in
# circuit.py):
FOL = [o for o in pm_rows if ROLE[o].startswith("FOL")]
fw = min(min(pm_rows[o]) + (o,) for o in FOL)
FIX_C = 10e-12
_, fkw = next(c for c in CONFIGS if c[0] == fw[3])
fnet = build(OP_NEW if fw[2] == "GBW 5.25 MHz" else OP_OLD, caps,
             extra_c=[(f"FI{name}", "GND", FIX_C) for (kind, name) in circuit.OPAMPS.values() if kind == "FOL"], **fkw)
pm_fix = min(phase_margin(fnet, o)[0] for o in FOL)
print(f"      followers: worst {fw[0]:.1f} deg ({fw[4]}, {fw[2]}, {fw[3]}); with {FIX_C * 1e12:.0f} pF from each FI to "
      f"GND {pm_fix:.1f} deg, its pole with the 10k + LEVEL wiper (35k at most) at "
      f"{1 / (2 * math.pi * 35e3 * FIX_C) / 1e3:.0f} kHz")

# The output stages' phase-lead caps (C907 / C908 4.7 pF across R905 / R908, C909 10 pF across R911; added
# 2026-11-14 for AUDIO_AC-2, where these stages had 17-18 deg): their worst margin as built, and what they cost at
# 20 kHz against the same board without them.
CF = [p.ref for p in MAIN_PARTS if p.kind == "C" and {_node(n) for n in p.nets.values()} in
      ({"NO_L", "OA_L"}, {"NO_R", "OA_R"}, {"NO_S", "OA_S"})]
outs = [o for o in pm_rows if ROLE[o].startswith("OUT")]
pm_out = min(min(pm_rows[o]) + (o,) for o in outs)
ck.check("the output stages carry their phase-lead caps (C across Rf on L, R and SEND)", len(CF) == 3, f"{CF}")
loss = []
for name, jacks, out in (("IN 7 L -> OUT L", ["J7"], "OUT_L"), ("FX IN -> SEND", ["J14"], "SEND")):
    a1 = response(build(OP_NEW, caps, patched={j: "in" for j in jacks}), out)[-1]
    a0 = response(build(OP_NEW, caps, patched={j: "in" for j in jacks}, skip=CF), out)[-1]
    loss.append(a1 - a0)
print(f"      output stages as built ({', '.join(CF)}): worst phase margin {pm_out[0]:.1f} deg ({pm_out[4]}, "
      f"{pm_out[2]}, {pm_out[3]}); the caps cost {min(loss):+.3f} dB at 20 kHz")
ck.check("the phase-lead caps cost under 0.1 dB at 20 kHz", min(loss) > -0.1, f"{min(loss):+.3f} dB")
# The doc's worst-case margins for the output stages
u, s_ = circuit.opamp_of("OUT", "S")
pm_s = min(pm_rows[f"{u}.{s_}"])
pm_lr = min(min(pm_rows[f"{u}.{s_}"]) for u, s_ in (circuit.opamp_of("OUT", "L"), circuit.opamp_of("OUT", "R")))
ck.close(f"phase margin, send inverter, worst case (doc {DOC_PM_S:.0f} deg)", pm_s[0], DOC_PM_S, 2.0, " deg")
ck.close(f"phase margin, OUT L / R stages, worst case (doc {DOC_PM_LR:.0f} deg)", pm_lr[0], DOC_PM_LR, 2.0, " deg")
print(f"      worst margins: send inverter {pm_s[0]:.1f} deg ({pm_s[2]}, {pm_s[3]}), OUT L / R {pm_lr[0]:.1f} deg "
      f"({pm_lr[2]}, {pm_lr[3]})")


# ------------------------------------------------------------------------------------ 5. slew rate
need = 2 * math.pi * 20e3 * V_SWING
ck.check("slew rate: a full-swing 20 kHz sine needs less than the TL074's minimum", need < SR_MIN / 2,
         f"expected need < half of {SR_MIN / 1e6:.0f} V/us (min); need {need / 1e6:.2f} V/us for {V_SWING} V peak; "
         f"full-power bandwidth at the minimum slew rate {SR_MIN / (2 * math.pi * V_SWING) / 1e3:.0f} kHz")

# ------------------------------------------------------------------------------------- 6. noise
FN = np.logspace(math.log10(20), math.log10(20e3), 60)
# en^2(f) = enw^2 (1 + fc / f), fitted through the datasheet's 1 kHz and 10 kHz typicals
_r = (EN_1K / EN_10K) ** 2
FC_1F = (_r - 1) / (1 / 1e3 - _r / 1e4)
ENW = EN_10K / math.sqrt(1 + FC_1F / 1e4)


def en(f):
    return ENW * np.sqrt(1 + FC_1F / f)


def noise(net, out):
    """Output noise, V rms over 20 Hz - 20 kHz, and the share of each source class."""
    o = net.nodes[out]
    N, nv = len(net.nodes), len(net.V)
    psd, parts = np.zeros(len(FN)), collections.defaultdict(lambda: np.zeros(len(FN)))
    for i, f in enumerate(FN):
        Y = net.matrix(f)
        e = np.zeros(Y.shape[0], complex)
        e[o] = 1
        x = np.linalg.solve(Y.T, e)
        xv = lambda n: x[n] if n >= 0 else 0
        for a, b, val, tag in net.R:
            if tag == "ZO":
                continue
            p = abs(xv(a) - xv(b)) ** 2 * 4 * KB * T_K / val
            psd[i] += p
            parts["resistors"][i] += p
        s = 2j * math.pi * f
        for j, (name, pp, m, oo, model) in enumerate(net.ops):
            p = abs(x[N + nv + j] * model.A(s)) ** 2 * en(f) ** 2
            p += (abs(xv(pp)) ** 2 + abs(xv(m)) ** 2) * IN_NOISE ** 2
            psd[i] += p
            parts["op-amps"][i] += p
    integ = lambda y: float(np.sqrt(np.trapezoid(y, FN)))
    return integ(psd), {k: integ(v) for k, v in parts.items()}


for bus in ("SUM_L", "SUM_S"):
    direct = [harness.ohms(p.value) for p in MAIN_PARTS if p.kind == "R" and bus in p.nets.values()
              and "feedback" not in p.label]
    switched = [harness.ohms(p.value) + CD_RON_TYP for p in MAIN_PARTS if p.kind == "R"
                and any(n.startswith("B" + bus[-1]) and n[2:].isdigit() for n in p.nets.values())]
    for what, rs in (("every channel playing", direct + switched), ("every channel muted", direct)):
        g_in = sum(1 / r for r in rs)
        print(f"      {bus} summer, {what}: {len(rs)} inputs, DC noise gain about 1 + 100k / {1 / g_in / 1e3:.1f}k = "
              f"{1 + 100e3 * g_in:.1f}")
print(f"      TL074 en model: {ENW * 1e9:.1f} nV/rtHz white, 1/f corner {FC_1F:.0f} Hz "
      f"({en(1e3) * 1e9:.0f} nV at 1 kHz, {en(1e4) * 1e9:.0f} at 10 kHz, {en(20.0) * 1e9:.0f} at 20 Hz)")
up_pots = {}
for k in circuit.MONO:
    up_pots[f"RV{3 * k - 1}"] = 0.5
muted_pots = dict(up_pots, RV23=0.0, RV23B=0.0, RV24=0.0)
for cname, kw, lim in (("every channel up", dict(pots=up_pots, patched=all_patched), SNR_UP_MIN),
                       ("every channel muted, RETURN and DRUMS down",
                        dict(pots=muted_pots, patched=all_patched, mutes=tuple(circuit.MONO + circuit.STEREO)),
                        SNR_MUTED_MIN)):
    net = build(OP_NEW, caps, **kw)
    for out in ("OUT_L", "OUT_R", "SEND"):
        vn, parts = noise(net, out)
        snr = 20 * math.log10(V_REF_RMS / vn)
        ck.check(f"noise at {out}, {cname}: SNR >= {lim:.0f} dB re 10 V p-p", snr >= lim,
                 f"expected >= {lim:.0f} dB; got {vn * 1e6:.1f} uV rms = {dbu(vn):.1f} dBu, SNR {snr:.1f} dB "
                 f"(op-amps {parts['op-amps'] * 1e6:.1f} uV, resistors {parts['resistors'] * 1e6:.1f} uV)")

ck.done()
