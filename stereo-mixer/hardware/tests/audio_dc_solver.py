"""DC nodal solver for the stereo mixer's audio path (helper of test_audio_dc.py).

Builds a modified-nodal-analysis model straight from circuit.py's parts:
both boards joined through the headers (each faceplate net X_F becomes the
main-board net X it mates with, GND_F -> GND), pots as two resistors with a
taper, jacks with their normalling switch closed when nothing is plugged in,
TL074 sections as high-gain VCVSs with an input offset source and an
optional saturation at a supply- and load-dependent swing, AQY212EH switch
side as Ron when muted and open (off-state leakage) when not. Logic, power
and capacitors are left out (DC).

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
NON_AUDIO = ("BTN", "DB", "QK", "LA", "LM", "LED", "POR", "CK", "QN", "+12V", "-12V", "P12", "N12")

R_CONTACT = 0.02        # closed jack switch contact / pot end resistance, ohm
R_OFF = 60e6            # AQY212EH off: 1 uA max leakage at 60 V -> >= 60 Mohm (Panasonic AQY21*EH datasheet)
G_LEAK = 1e-13          # tiny conductance to ground on every node, keeps floating nodes solvable


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
    muted: set of channels 1..8; ron: PhotoMOS on-resistance
    sources: {jack ref: (volts, source ohms) or (volts, ohms, 'name')}: jacks with the same name share one
             source (a mult): one EMF, one output resistance, the jacks in parallel behind it
    loads: {jack ref: ohms} on unswitched (output) jacks
    a_mid: A taper at half rotation"""

    def __init__(self, rot=None, muted=(), ron=0.83, sources=None, loads=None, a_mid=0.15, aol=2e5):
        self.rot = dict(rot or {})
        self.muted = set(muted)
        self.ron = ron
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
            elif p.kind == "PHOTOMOS":
                ch = int("".join(c for c in p.nets["3"][2:] if c.isdigit()))
                r = cfg.ron if ch in cfg.muted else R_OFF
                self.res.append((n["3"], n["4"], r, p.ref))
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
