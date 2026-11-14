"""audio_ac: AC behaviour, stability and noise of the stereo mixer (Mycelium) by complex nodal analysis.

What it checks
  - frequency response 20 Hz - 20 kHz of every input -> output path at the worst pot positions, with the
    summers' 22 p, the AQY212EH's off-state output capacitance on every FI node, the TL074's input
    capacitance, open-loop gain / output impedance, and PCB stray capacitance from the routed net lengths;
  - the distortion the PhotoMOS's voltage-dependent off capacitance adds (10 V p-p, 10 kHz, worst LEVEL),
    by a time-domain simulation of the LV / FI nodes;
  - mute attenuation against frequency (on-resistance, typical and maximum);
  - op-amp stability: the loop gain of every TL074 section in the whole circuit (followers with their
    pan / SEND / track load, summers with their summing-node capacitance and 22 p, output stages and the
    send inverter driving 1k + a patch cable): phase margin;
  - slew rate at full scale and 20 kHz;
  - output noise at OUT L / OUT R / SEND with every channel up and with every channel muted (TL074 en and
    in, Johnson noise of every resistor and pot track), as dBu and SNR against a 10 V p-p signal.

How the model is built
  circuit.py's netlist (both boards), header nets merged (X_F == X, GND_F == GND), power rails as AC
  ground, the latch left out (it does not touch the audio nets). Each TL074 section is a two-pole
  VCVS with its open-loop output resistance and input capacitance. Pots are two resistors at a wiper
  fraction a (0 = wiper on pin 1, the CCW end). Inputs are 1k sources (a typical Eurorack output);
  unpatched jacks take their switch-lug net. Stray capacitance per net = routed track length x pF/mm
  (computed below for 0.3 mm tracks on 1.6 mm FR4) + pads + vias + mated header pins.

Not modelled: ground-impedance and supply crosstalk, capacitive coupling between tracks (crosstalk,
  mute bleed round the PhotoMOS), the latch's switching transients, op-amp poles beyond the second,
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
V_SWING = 10.5          # V peak, the swing on +-12 V the design doc uses (datasheet: +-12 V min at +-15 V, 10k)

# AQY212EH, Panasonic GE 1 Form A (AQY21*EH) datasheet ASCTB126E 201404-T (Mouser copy)
RON_TYP, RON_MAX = 0.85, 2.5        # ohm, typ / max, IF = 5 mA
# Output capacitance between terminals 3 and 4 against applied voltage, f = 1 MHz, 25 C: graph 12-(2),
# read off the datasheet's vector curve (typical; no min / max given). Assumed symmetric in V (the two
# MOSFETs are anti-series, so either polarity reverse-biases one body diode).
COFF_CURVE = [(0.0, 78.8), (0.9, 69.0), (1.9, 58.5), (2.9, 49.4), (3.7, 43.5), (4.6, 40.2), (5.6, 37.3),
              (6.6, 35.2), (7.5, 34.1), (8.4, 33.6), (9.5, 33.2), (10.5, 32.7), (11.3, 31.7), (12.8, 29.6),
              (15.4, 26.3), (18.1, 23.2), (20.0, 21.5)]          # (V, pF)

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

# Criteria (first principles; the doc states no AC or noise figures)
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
_m = re.search(r"\(([\d.]+) Ω typical, ([\d.]+) Ω max\)", DOC)
DOC_RON_TYP, DOC_RON_MAX = (float(_m.group(1)), float(_m.group(2))) if _m else (float("nan"), float("nan"))
_m = re.search(r"drops by (\d+) dB typically, (\d+) dB at worst", DOC)
DOC_MUTE_TYP, DOC_MUTE_MAX = (float(_m.group(1)), float(_m.group(2))) if _m else (float("nan"), float("nan"))
_m = re.search(r"a pole at (\d+) kHz", DOC)
DOC_SUM_POLE_KHZ = float(_m.group(1)) if _m else float("nan")


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


def net_caps(pf_mm):
    """Stray capacitance to ground per (merged) net, F, and the per-net breakdown (track mm, pads, vias)."""
    main, face = routed_boards()
    caps, info = collections.defaultdict(float), collections.defaultdict(lambda: [0.0, 0, 0, 0])
    for b in (main, face):
        st = b.net_stats()
        for n, s in st.items():
            nb = base(n)
            caps[nb] += s["length"] * pf_mm * 1e-12 + s["vias"] * C_VIA
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
AUDIO_SKIP = ("BTN", "DB", "QK", "LA", "LM", "LED", "CK", "QN", "POR")
AC_GROUND = {"+12V", "-12V", "P12_IN", "N12_IN", "P12_D", "N12_D", "GND", "GND_F"}


def _node(net):
    return "GND" if net in AC_GROUND else base(net)


def build(model, caps, pots=None, patched=None, mutes=(), ron=RON_TYP, coff=None, load=True, src=R_SOURCE,
          extra_cable=0.0, extra_c=(), skip=()):
    """The whole mixer as a Net.

    pots: {ref or ref+'B' (dual gang B): wiper fraction a, 0 = wiper on pin 1 (pin 4 for gang B)}; default 1.
    patched: {jack ref: source name}; a patched jack gets a source V (name) behind src ohms. Others take their
    switch lug (or float, for the outputs). mutes: channel numbers muted (PhotoMOS on). coff: off capacitance
    (F) of every PhotoMOS that is off; default its 0 V value."""
    pots, patched = pots or {}, patched or {}
    coff = COFF_CURVE[0][1] * 1e-12 if coff is None else coff
    net = Net()
    for p in MAIN_PARTS:
        if p.ref in skip:
            continue                          # a part left out, to price it
        if p.kind != "PHOTOMOS" and any(_node(n).startswith(AUDIO_SKIP) for n in p.nets.values()):
            continue                          # the latch; a PhotoMOS's LED side is on latch nets, its switch is not
        if p.kind == "R":
            net.r(_node(p.nets["1"]), _node(p.nets["2"]), harness.ohms(p.value), tag=p.ref)
        elif p.kind == "C":
            net.c(_node(p.nets["1"]), _node(p.nets["2"]), harness.farads(p.value))
        elif p.kind == "PHOTOMOS":
            k = int("".join(ch for ch in p.label.split()[1] if ch.isdigit()))
            if k in mutes:
                net.r(_node(p.nets["3"]), _node(p.nets["4"]), ron, tag=p.ref)
            else:
                net.c(_node(p.nets["3"]), _node(p.nets["4"]), coff)
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
for n in ("SUM_L", "SUM_R", "SUM_S", "NO_L", "NO_S", "FI1", "LV5", "CH7L", "PL1", "OUT_R", "MIX_R"):
    L, pads, vias, hdr = info[n]
    print(f"      stray {n:6}: {L:6.1f} mm track, {pads:2d} pads, {vias} vias, {hdr} header pins -> "
          f"{caps[n] * 1e12:5.1f} pF")
ck.check("every summing node's stray capacitance is known from the routed export",
         all(info[n][0] > 0 for n in ("SUM_L", "SUM_R", "SUM_S", "NO_L", "NO_R", "NO_S")),
         "expected routed track on SUM_L/R/S and NO_L/R/S; got " +
         ", ".join(f"{n} {info[n][0]:.1f} mm" for n in ("SUM_L", "SUM_R", "SUM_S", "NO_L", "NO_R", "NO_S")))

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

# The PhotoMOS share: the same mono path with and without its off capacitance, at the worst LEVEL
k_worst = 5                       # the longest LV track (copper_audit: LV5 47.9 + 8.5 mm)
lvl = f"RV{3 * k_worst - 2}"
share = []
for a in LEVELS:
    pots = {lvl: a, f"RV{3 * k_worst - 1}": 0.0}
    with_c = response(build(OP_NEW, caps, pots=pots, patched={f"J{k_worst}": "in"}), "OUT_L")[-1]
    no_c = response(build(OP_NEW, caps, pots=pots, patched={f"J{k_worst}": "in"}, coff=0.0), "OUT_L")[-1]
    share.append((with_c - no_c, a, with_c, no_c))
s = min(share)
ck.check("the PhotoMOS off capacitance costs < 0.1 dB at 20 kHz at any LEVEL", s[0] > -0.1,
         f"expected > -0.1 dB; at LEVEL a = {s[1]} it costs {s[0]:+.2f} dB ({s[2]:+.2f} dB at 20 kHz with "
         f"the AQY212EH's {COFF_CURVE[0][1]:.0f} pF, {s[3]:+.2f} dB without)")
# The summers' 22 p alone: the pole the doc names (72 kHz) costs this much at 20 kHz
_pm = {p.ref: p for p in MAIN_PARTS}
fps = [1 / (2 * math.pi * harness.ohms(_pm[r].value) * harness.farads(_pm[c].value))
       for r, c in (("R901", "C901"), ("R902", "C902"), ("R903", "C903"))]
fp = max(fps)
ck.close(f"the summers' Rf || Cf pole frequency, circuit.py R901-R903 / C901-C903 (doc: {DOC_SUM_POLE_KHZ:.0f} kHz)",
         min(fps) / 1e3, DOC_SUM_POLE_KHZ, 1.0, " kHz")
print(f"      100k || 22p alone: {harness.db(1 / abs(1 + 1j * 20e3 / fp)):+.2f} dB at 20 kHz per summer stage")


# ------------------------------------------------------------- 2. distortion from the off capacitance
SMOOTH_V = 0.0


def coff_of(v):
    """The datasheet curve at |v|; with SMOOTH_V > 0 the kink at 0 V is rounded off over about +-SMOOTH_V
    (the curve is a 1 MHz small-signal measurement at DC bias, so its slope at 0 V is not resolved)."""
    u = np.sqrt(v * v + SMOOTH_V ** 2) - SMOOTH_V
    return np.interp(u, [p[0] for p in COFF_CURVE], [p[1] for p in COFF_CURVE]) * 1e-12


def fi_thd(levels, f0=10e3, vpk=5.0, k=k_worst, curve=True, steps=8000, cycles=10):
    """THD of the FI node (= the follower's output) for a vpk sine at the jack, by a semi-implicit
    integration of the LV and FI nodes; vectorised over LEVEL positions."""
    a = np.array(levels, float)
    R = 100e3
    gth = 1 / (a * R) + 1 / ((1 - a) * R + R_SOURCE)          # Thevenin of source + LEVEL pot at the wiper
    kth = (a * R) / (R + R_SOURCE)                             # open-circuit wiper voltage / source voltage
    kth = np.where(a >= 1, R / (R + R_SOURCE), kth)
    gth = np.where(a >= 1, 1 / (R * R_SOURCE / (R + R_SOURCE)), gth)
    g = 1 / 10e3
    c1 = caps[f"LV{k}"]
    cfix = caps[f"FI{k}"] + C_ICM
    dt = 1 / f0 / steps
    v1 = np.zeros_like(a)
    v2 = np.zeros_like(a)
    keep = []
    n_tot = steps * cycles
    for n in range(1, n_tot + 1):
        vs = vpk * math.sin(2 * math.pi * f0 * n * dt)
        c2 = cfix + (coff_of(v2) if curve else COFF_CURVE[0][1] * 1e-12)
        a11, a12, a22 = c1 / dt + gth + g, -g, c2 / dt + g
        b1, b2 = c1 / dt * v1 + gth * kth * vs, c2 / dt * v2
        det = a11 * a22 - a12 * a12
        v1, v2 = (b1 * a22 - a12 * b2) / det, (a11 * b2 - a12 * b1) / det
        if n > n_tot - 4 * steps:
            keep.append(v2.copy())
    x = np.array(keep)
    X = np.abs(np.fft.rfft(x, axis=0))
    fund = X[4]
    harm = np.sqrt(sum(X[4 * h] ** 2 for h in range(2, 11)))
    return harm / fund, fund


thd_lin, _ = fi_thd([0.3], curve=False)
ck.check("THD simulation: a constant capacitance gives no distortion (test of the test)", thd_lin[0] < 1e-6,
         f"expected < 1e-6; got {thd_lin[0]:.1e}")
lv_thd = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
thd_kink, _ = fi_thd(lv_thd)
SMOOTH_V = 0.5                    # the checks use the rounded curve: the less pessimistic of the two
thd, _ = fi_thd(lv_thd)
thd2, _ = fi_thd(lv_thd, steps=16000)
i = int(np.argmax(thd))
ck.check("THD simulation converged (step halved: same THD within 5 %)", abs(thd2[i] / thd[i] - 1) < 0.05,
         f"expected ratio 1 +- 0.05; got {thd2[i] / thd[i]:.3f}")
print("      THD at 10 kHz, 10 V p-p in, against LEVEL (wiper fraction), curve as read / rounded at 0 V: " +
      ", ".join(f"{a}: {t0 * 100:.2f} / {t * 100:.2f} %" for a, t0, t in zip(lv_thd, thd_kink, thd)))
ck.check(f"PhotoMOS off-capacitance THD, 10 V p-p 10 kHz, worst LEVEL <= {THD_MAX * 100:.2f} %", thd[i] <= THD_MAX,
         f"expected <= {THD_MAX * 100:.2f} %; got {thd[i] * 100:.2f} % ({harness.db(thd[i]):.0f} dB; "
         f"{thd_kink[i] * 100:.2f} % with the curve's kink at 0 V) at LEVEL a = {lv_thd[i]} (C_off "
         f"{COFF_CURVE[0][1]:.0f} pF at 0 V -> {float(coff_of(lv_thd[i] * 5)) * 1e12:.0f} pF at the "
         f"{lv_thd[i] * 5:.1f} V peak, behind {10 + 100 * lv_thd[i] * (1 - lv_thd[i]):.0f}k)")
thd1k, _ = fi_thd([lv_thd[i]], f0=1e3)
thd_low, _ = fi_thd([lv_thd[i]], vpk=1.0)
print(f"      the same at 1 kHz: {thd1k[0] * 100:.3f} %; at 10 kHz and 2 V p-p: {thd_low[0] * 100:.3f} %")
_curve = COFF_CURVE
for scale in (0.1, 0.02):
    COFF_CURVE = [(v, c * scale) for v, c in _curve]
    t_s, _ = fi_thd([lv_thd[i]])
    print(f"      with the off-capacitance curve x {scale} ({_curve[0][1] * scale:.1f} pF at 0 V): "
          f"{t_s[0] * 100:.3f} % at 10 kHz")
COFF_CURVE = _curve
ck.check(f"PhotoMOS off-capacitance THD, 10 V p-p 1 kHz, worst LEVEL <= {THD_MAX * 100:.2f} %", thd1k[0] <= THD_MAX,
         f"expected <= {THD_MAX * 100:.2f} %; got {thd1k[0] * 100:.4f} %")


# (verifier) The symmetric C(|v|) above treats the 3-4 capacitance as one two-terminal varactor. Inside, the
# AQY212EH is two MOSFETs in anti-series with a floating common-source node; under an AC swing that node is
# clamped by the body diodes and the two junctions see different biases. Second model: each MOSFET's
# junction Cj(u) is derived from the curve assuming the datasheet's DC measurement puts the full bias on one
# junction and ~0 V on the other (C_meas(V) = Cj(V) series Cj(0), so Cj(0) = 2 C_meas(0)); the common node
# floats (charge conserved) between ideal body-diode clamps at 0 V forward; leakage neglected (1 nA into
# ~60 pF moves it by < 2 mV per 10 kHz cycle). Single node: Thevenin source + 10k into FI with the fixed
# stray, explicit Euler at 5 ns. The truth should lie between the two models.
def fi_thd_pair(levels, f0=10e3, vpk=5.0, k=k_worst, curve=True, spc=20000, cycles=12):
    a = np.array(levels, float)
    R = 100e3
    rs = 1 / (1 / (a * R) + 1 / ((1 - a) * R + R_SOURCE)) + 10e3
    kth = a * R / (R + R_SOURCE)
    cfix = caps[f"FI{k}"] + C_ICM + caps[f"LV{k}"] * 0      # the LV node sits behind the 10k: left out here
    c00 = 2 * COFF_CURVE[0][1] * 1e-12
    vv, cc = [p[0] for p in COFF_CURVE], [p[1] * 1e-12 for p in COFF_CURVE]

    def cj(u):
        if not curve:
            return np.full_like(u, c00)
        return 1 / (1 / np.interp(np.maximum(u, 0), vv, cc) - 1 / c00)
    dt = 1 / f0 / spc
    v, s = np.zeros_like(a), np.zeros_like(a)
    keep = []
    for n in range(cycles * spc):
        vth = kth * vpk * math.sin(2 * math.pi * f0 * n * dt)
        ca, cb = cj(v - s), cj(-s)
        i = (vth - v) / rs
        dv = i / (cfix + ca * cb / (ca + cb)) * dt                   # both body diodes off: charge shared
        ds = dv * ca / (ca + cb)
        fa = v + dv - (s + ds) < 0                                   # A's body diode forward: s follows v
        dv = np.where(fa, i / (cfix + cb) * dt, dv)
        ds = np.where(fa, dv, ds)
        fb = ~fa & (s + ds > 0)                                      # B's body diode forward: s held at 0
        dv = np.where(fb, i / (cfix + ca) * dt, dv)
        ds = np.where(fb, -s, ds)
        v, s = v + dv, s + ds
        if n >= (cycles - 4) * spc:
            keep.append(v.copy())
    X = np.abs(np.fft.rfft(np.array(keep), axis=0))
    return np.sqrt(sum(X[4 * h] ** 2 for h in range(2, 11))) / X[4], s


lv_pair = [0.3, 0.5, 0.7, 0.8]
t_lin, _ = fi_thd_pair([0.7], curve=False, spc=4000)
ck.check("THD, anti-series model: constant junction capacitance gives no distortion once the node has settled "
         "(test of the test)", t_lin[0] < 1e-5, f"expected < 1e-5; got {t_lin[0]:.1e}")
t_pair, s_pair = fi_thd_pair(lv_pair)
t_pair1k, _ = fi_thd_pair(lv_pair, f0=1e3)
j = int(np.argmax(t_pair))
print("      THD, anti-series pair model, 10 V p-p, by LEVEL: " +
      ", ".join(f"{a}: {t * 100:.2f} % at 10 kHz / {t1 * 100:.3f} % at 1 kHz (node {s:+.1f} V)"
                for a, t, t1, s in zip(lv_pair, t_pair, t_pair1k, s_pair)))
ck.check(f"PhotoMOS off-capacitance THD, anti-series pair model, 10 V p-p 10 kHz, worst LEVEL <= {THD_MAX * 100:.2f} %",
         t_pair[j] <= THD_MAX, f"expected <= {THD_MAX * 100:.2f} %; got {t_pair[j] * 100:.2f} % at LEVEL a = "
         f"{lv_pair[j]} (the symmetric model gives {thd[i] * 100:.2f} %); at 1 kHz {max(t_pair1k) * 100:.3f} %")


# --------------------------------------------------------------------------- 3. mute attenuation
def mute_att(k, ron, a, jack, out, pots_extra):
    pots = dict(pots_extra)
    pots[{7: "RV19", 8: "RV21"}.get(k, f"RV{3 * k - 2}")] = a
    on = build(OP_NEW, caps, pots=pots, patched={jack: "in"}, mutes=(k,), ron=ron)
    off = build(OP_NEW, caps, pots=pots, patched={jack: "in"})
    return min(harness.db(abs(off.gain(f, out)) / abs(on.gain(f, out))) for f in (20.0, 1e3, 20e3))


for ron, claim, label in ((RON_TYP, DOC_MUTE_TYP, "typical"), (RON_MAX, DOC_MUTE_MAX, "maximum")):
    rows = []
    for k in circuit.MONO + circuit.STEREO:
        jack = {7: "J7", 8: "J9"}.get(k, f"J{k}")
        extra = {} if k in circuit.STEREO else {f"RV{3 * k - 1}": 0.0}
        for a in (0.1, 0.5, 1.0):
            rows.append((mute_att(k, ron, a, jack, "OUT_L", extra), k, a))
    m = min(rows)
    ck.check(f"mute attenuation 20 Hz-20 kHz with Ron {label} ({ron} ohm) >= the doc's {claim:.0f} dB - 1",
             m[0] >= claim - 1.0, f"expected >= {claim - 1:.0f} dB on every channel at every LEVEL; worst "
             f"{m[0]:.1f} dB (channel {m[1]}, LEVEL a = {m[2]})")
ck.check("the doc's typical AQY212EH on-resistance matches the datasheet", abs(DOC_RON_TYP - RON_TYP) < 0.005,
         f"expected the datasheet's {RON_TYP} ohm typ (IF = 5 mA; ASCTB126E 201201-T and 201404-T, and Panasonic's "
         f"product page); design.md says {DOC_RON_TYP} ohm")
ck.check("the doc's maximum AQY212EH on-resistance matches the datasheet", abs(DOC_RON_MAX - RON_MAX) < 0.005,
         f"expected the datasheet's {RON_MAX} ohm max; design.md says {DOC_RON_MAX} ohm")


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
    ("all pots at mid, PhotoMOS off-C at its 20 V value", dict(pots={r: 0.5 for r, *_ in circuit.POTS + circuit.POTS2},
                                                               coff=COFF_CURVE[-1][1] * 1e-12)),
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
    g_in = sum(1 / harness.ohms(p.value) for p in MAIN_PARTS if p.kind == "R" and bus in p.nets.values()
               and "feedback" not in p.label)
    print(f"      {bus} summer: {sum(1 for p in MAIN_PARTS if p.kind == 'R' and bus in p.nets.values()) - 1} inputs, "
          f"DC noise gain about 1 + 100k / {1 / g_in / 1e3:.1f}k = {1 + 100e3 * g_in:.1f}")
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
