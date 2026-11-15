"""DC nodal solver for the stereo mixer's audio path (helper of test_audio_dc.py).

Builds a modified-nodal-analysis model straight from circuit.py's parts:
both boards joined through the headers (each faceplate net X_F becomes the
main-board net X it mates with, GND_F -> GND), pots as two resistors with a
taper, jacks with their normalling switch closed when nothing is plugged in,
TL074 sections as high-gain VCVSs with an input offset source and an
optional saturation at a supply- and load-dependent swing, and each
channel's CD4053B mute switch as three SPDT sections: common <-> x (the
bus's summing node) Ron while the channel plays and R_OFF while it is
muted, common <-> y (GND) the reverse. The latch (buttons, debounce,
flip-flops, LED resistors) is left out: it only drives the selects, which
are QK nets. Power and capacitors are left out too (DC).

Only reads circuit.py; writes nothing.
"""
import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # small matrices: threaded BLAS is 100x slower here
import numpy as np  # noqa: E402

import harness

CIRCUIT = harness.load("circuit")
PARTS = CIRCUIT.all_parts()

# nets that belong to the latch / power, not the audio path
NON_AUDIO = ("BTN", "DB", "QK", "LED", "POR", "CK", "QN", "+12V", "-12V", "P12", "N12")

R_CONTACT = 0.02        # closed jack switch contact / pot end resistance, ohm
G_LEAK = 1e-13          # tiny conductance to ground on every node, keeps floating nodes solvable

# CD4053B, TI SCHS047O (rev. O, May 2026), 5.5 Electrical Characteristics, VEE = VSS = 0, 0 <= VIS <= VDD.
# The chips get about 11-11.6 V; rON falls as VDD rises, so the VDD = 10 V column is the conservative one.
RON_TYP = 180.0         # ohm, typ, VDD 10 V, 25 C   (VDD 15 V: 125 typ)
RON_MAX_25C = 400.0     # ohm, max, VDD 10 V, 25 C   (VDD 15 V: 240)
RON_MAX_85C = 520.0     # ohm, max, VDD 10 V, 85 C   (VDD 15 V: 300)
DRON_TYP = 10.0         # ohm, typ, change in rON between any two channels, VDD 10 V (15 at 5 V, 5 at 15 V)
# The open throw. The datasheet gives OFF-channel leakage, not a resistance: +-100 nA max at 25 C and +-1000 nA
# at 85 C (VDD 18 V, "determined by minimum feasible leakage measurement for automatic testing", i.e. a tester
# limit), +-10 pA typical at VDD 15 V (features list). Read as a resistance at the test voltage those are
# 180 Mohm / 18 Mohm / 1.5 Tohm. Here both ends of an open throw sit at about 0 V (one on a virtual earth, the
# other on GND or on a closed throw to GND), so the leakage, which flows from the terminals to the wells (VDD /
# VEE), is not a conduction across the throw at all. R_OFF = 1 Gohm: three decades under the typical figure, still
# a conduction path the solver can see; at audio frequencies the 0.2 pF feedthrough (40 Mohm at 20 kHz) dominates
# it anyway. The tester limits as resistances are R_OFF_25C / R_OFF_85C, for sensitivity runs.
R_OFF = 1e9
R_OFF_25C, R_OFF_85C = 18.0 / 100e-9, 18.0 / 1000e-9


def taper(kind, rot, a_mid=0.15):
    """Fraction of the track between the CCW end (pin 1) and the wiper at rotation rot (0 = CCW .. 1 = CW).
    B = linear. A = two straight segments through a_mid at half rotation (the usual 'audio' approximation)."""
    rot = min(max(rot, 0.0), 1.0)
    if kind == "B":
        return rot
    if rot <= 0.5:
        return rot * a_mid / 0.5
    return a_mid + (rot - 0.5) * (1 - a_mid) / 0.5


def _node_map():
    fb2mb = {}
    for ref, kind, pins in CIRCUIT.HEADERS:
        for mb, fb in pins:
            fb2mb[fb] = mb
    return fb2mb


FB2MB = _node_map()


def node(net):
    return FB2MB.get(net, net)


def audio(net):
    return not any(net.startswith(p) for p in NON_AUDIO)


class Config:
    """What the panel and the patch look like.
    rot: {pot ref: rotation 0..1} (default 1.0 = full CW for LEVEL/SEND/RETURN/DRUMS/MASTER, 0.5 for PAN)
    muted: set of channels 1..8
    ron: the CD4053B's on-resistance, every closed throw; ron_sec: {(channel, bus 'L' / 'R' / 'S'): ohms}
         for single sections (switch-to-switch mismatch); r_off: an open throw
    sources: {jack ref: (volts, source ohms) or (volts, ohms, 'name')}: jacks with the same name share one
             source (a mult): one EMF, one output resistance, the jacks in parallel behind it
    loads: {jack ref: ohms} on unswitched (output) jacks
    a_mid: A taper at half rotation"""

    def __init__(self, rot=None, muted=(), ron=RON_TYP, sources=None, loads=None, a_mid=0.15, aol=2e5, ron_sec=None,
                 r_off=R_OFF):
        self.rot = dict(rot or {})
        self.muted = set(muted)
        self.ron = ron
        self.ron_sec = dict(ron_sec or {})
        self.r_off = r_off
        self.sources = dict(sources or {})
        self.loads = dict(loads or {})
        self.a_mid = a_mid
        self.aol = aol


class Model:
    def __init__(self, cfg, vos=None, ibias=None):
        """vos: {(chip, section): volts at IN+}; ibias: {node: amps injected}"""
        self.cfg = cfg
        self.res = []           # (a, b, ohms, label)
        self.vsrc = []          # (node+, volts, label) referenced to GND
        self.opamps = []        # dict(name, out, p, m, vos)
        self.inj = dict(ibias or {})
        vos = vos or {}
        for p in PARTS:
            n = {k: node(v) for k, v in p.nets.items()}
            if p.kind == "R":
                if audio(n["1"]) and audio(n["2"]):
                    self.res.append((n["1"], n["2"], harness.ohms(p.value), p.ref))
            elif p.kind == "POT":
                self._pot(p.ref, p.value, n["1"], n["2"], n["3"])
            elif p.kind == "POT2":
                self._pot(p.ref + "A", p.value, n["1"], n["2"], n["3"], rotref=p.ref)
                self._pot(p.ref + "B", p.value, n["4"], n["5"], n["6"], rotref=p.ref)
            elif p.kind == "JACK":
                self._jack(p.ref, n)
            elif p.kind == "CD4053":
                self._switch(p, n)
            elif p.kind == "TL074":
                for s, (o, im, ip) in CIRCUIT.SECTION.items():
                    self.opamps.append(dict(name=(p.ref, s), out=n[o], m=n[im], p=n[ip], vos=vos.get((p.ref, s), 0.0)))
        nodes = set()
        for a, b, _, _ in self.res:
            nodes |= {a, b}
        for o in self.opamps:
            nodes |= {o["out"], o["m"], o["p"]}
        for nd, _, _ in self.vsrc:
            nodes.add(nd)
        nodes |= set(self.inj)
        nodes.discard("GND")
        self.nodes = sorted(nodes)
        self.idx = {nd: i for i, nd in enumerate(self.nodes)}

    def _switch(self, p, n):
        """A channel's CD4053B: per section common <-> x (the bus) and common <-> y (GND). The channel comes from
        the selects' net (QKk): the latch is not in the model, the select's state is cfg.muted."""
        for bus, (com, x, y, sel) in CIRCUIT.MUX.items():
            k = int(p.nets[sel][2:]) if p.nets[sel].startswith("QK") else None
            if k is None:
                raise ValueError(f"{p.ref}.{sel}: select on {p.nets[sel]}, not a QK net")
            ron = self.cfg.ron_sec.get((k, bus), self.cfg.ron)
            on, off = (y, x) if k in self.cfg.muted else (x, y)
            self.res.append((n[com], n[on], ron, f"{p.ref}.{bus}.on"))
            self.res.append((n[com], n[off], self.cfg.r_off, f"{p.ref}.{bus}.off"))

    def _pot(self, name, value, ccw, wiper, cw, rotref=None):
        kind = value[0]
        rref = rotref or name
        default = 0.5 if kind == "B" else 1.0
        t = taper(kind, self.cfg.rot.get(rref, default), self.cfg.a_mid)
        rt = harness.ohms(value)
        self.res.append((ccw, wiper, rt * t + R_CONTACT, name + ".ccw"))
        self.res.append((wiper, cw, rt * (1 - t) + R_CONTACT, name + ".cw"))

    def _jack(self, ref, n):
        tip, lug = n["3"], n.get("2")
        src = self.cfg.sources.get(ref)
        if src is None:
            if lug:
                self.res.append((tip, lug, R_CONTACT, ref + ".switch"))
            if ref in self.cfg.loads:
                self.res.append((tip, "GND", self.cfg.loads[ref], ref + ".load"))
            return
        v, rs = src[0], src[1]
        name = src[2] if len(src) > 2 else ref
        emf = "SRC_" + name
        if not any(s[0] == emf for s in self.vsrc):
            self.vsrc.append((emf, v, name))
            self.res.append((emf, "SRCO_" + name, max(rs, R_CONTACT), name + ".rs"))
        self.res.append(("SRCO_" + name, tip, R_CONTACT, ref + ".plug"))

    def solve(self, limits=None, iters=60):
        """Node voltages {node: V} and op-amp output currents {name: A out of the pin}.
        limits: None (linear) or {opamp name: (vlo, vhi)} or a callable(name, load_ohms) -> (vlo, vhi)."""
        N = len(self.nodes)
        M = len(self.vsrc) + len(self.opamps)
        clamp = {}
        frozen = {}         # each section's swing, from its load in the first (linear) solve, then kept
        for _ in range(iters):
            A = np.zeros((N + M, N + M))
            z = np.zeros(N + M)
            for i in range(N):
                A[i, i] += G_LEAK
            for a, b, r, _ in self.res:
                g = 1.0 / r
                ia, ib = self.idx.get(a), self.idx.get(b)
                if ia is not None:
                    A[ia, ia] += g
                if ib is not None:
                    A[ib, ib] += g
                if ia is not None and ib is not None:
                    A[ia, ib] -= g
                    A[ib, ia] -= g
            for nd, I in self.inj.items():
                if nd in self.idx:
                    z[self.idx[nd]] += I
            k = N
            for nd, v, _ in self.vsrc:
                i = self.idx[nd]
                A[i, k] += 1
                A[k, i] += 1
                z[k] = v
                k += 1
            for o in self.opamps:
                io = self.idx[o["out"]]
                A[io, k] += 1
                A[k, io] += 1
                if o["name"] in clamp:
                    z[k] = clamp[o["name"]]
                else:
                    aol = self.cfg.aol
                    if o["p"] in self.idx:
                        A[k, self.idx[o["p"]]] -= aol
                    if o["m"] in self.idx:
                        A[k, self.idx[o["m"]]] += aol
                    z[k] = aol * o["vos"]
                k += 1
            x = np.linalg.solve(A, z)
            V = {nd: x[i] for nd, i in self.idx.items()}
            V["GND"] = 0.0
            I = {o["name"]: -x[N + len(self.vsrc) + j] for j, o in enumerate(self.opamps)}
            self.clamped = dict(clamp)
            if limits is None:
                return V, I
            changed = False
            for o in self.opamps:
                name = o["name"]
                vout = V[o["out"]]
                if name not in frozen:
                    # idle sections (|Vout| < 0.1 V) count as unloaded; the load floored at 1k
                    load = abs(vout / I[name]) if abs(vout) > 0.1 and abs(I[name]) > 1e-15 else 1e12
                    load = max(load, 1e3)
                    frozen[name] = limits(name, load) if callable(limits) else limits[name]
                lo, hi = frozen[name]
                want = self.cfg.aol * (V[o["p"]] + o["vos"] - V[o["m"]])
                if name in clamp:
                    # release when the input difference pulls the output back inside the swing
                    at_hi = clamp[name] > 0
                    diff = V[o["p"]] + o["vos"] - V[o["m"]]
                    if (at_hi and diff < 0) or (not at_hi and diff > 0):
                        del clamp[name]
                        changed = True
                elif vout > hi or vout < lo:
                    clamp[name] = hi if vout > hi else lo
                    changed = True
            if not changed:
                return V, I
        raise RuntimeError("saturation iteration did not settle")


def solve(cfg, **kw):
    lim = kw.pop("limits", None)
    return Model(cfg, **kw).solve(limits=lim)


def opamp_by_role(kind, name):
    return CIRCUIT.opamp_of(kind, name)
