"""DC nodal solver for Plaitsy's CV inputs (helper of test_analog_dc.py).

Builds a modified-nodal-analysis model straight from circuit.py's parts, both
boards joined at the headers (each faceplate net X_F becomes the main-board
net it mates with, GND_F -> GND, PROBE_F -> PROBE, CV_*_F -> CV_*):

  - every resistor on the CV / bias / probe nets (the LED and button-LED
    resistors are left out), each with an optional tolerance factor
  - the jacks: tip to switch lug closed when nothing is plugged in, a source
    (volts, ohms) on the tip and the lug open when something is
  - 3V3A as an ideal source (its tolerance is a parameter), the probe pin D14
    as a source behind its output resistance, or open (input mode)
  - TL074 sections as high-gain VCVSs with an input offset, bias currents as
    injections, or a section's output forced to a voltage (a section at its rail)
  - D21 / D22 and the STM32's ESD diodes as exponential diodes with a series
    resistance, solved by Newton iteration; every diode parameter comes from
    the caller (the test group's constants block)
  - current injections on any node (ADC pin leakage, diode leakage)

Only reads circuit.py; writes nothing.
"""
import math
import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")      # small matrices: threaded BLAS is slower here
import numpy as np  # noqa: E402

import harness  # noqa: E402

CIRCUIT = harness.load("circuit")
PARTS = CIRCUIT.all_parts()
BYREF = {p.ref: p for p in PARTS}

R_CONTACT = 0.02        # closed jack switch contact, ohm
G_LEAK = 1e-12          # tiny conductance to ground on every node, keeps floating nodes solvable
VT_25C = 0.025852       # kT/q at 25 C, volts

# nets that belong to the LEDs, the buttons and the logic, not the analog path
NON_ANALOG = ("L_", "LED_", "BTN", "SPI", "SCK", "MOSI", "SR_", "3V3D", "MUX_S")


def _fb2mb():
    m = {}
    for ref, kind, pins in CIRCUIT.HEADERS:
        for mb, fb in pins:
            m[fb] = mb
    return m


FB2MB = _fb2mb()


def node(net):
    return FB2MB.get(net, net)


def analog(net):
    return not any(net.startswith(p) for p in NON_ANALOG)


def sections():
    """[(chip, section, out net, in- net, in+ net)] of every TL074 section, from the parts."""
    out = []
    for p in PARTS:
        if p.kind == "TL074":
            for s, (o, m, pl) in CIRCUIT.SECTION.items():
                if o in p.nets:
                    out.append((p.ref, s, node(p.nets[o]), node(p.nets[m]), node(p.nets[pl])))
    return out


class Diode:
    """Exponential diode with series resistance: I = Is (exp(V / (n Vt)) - 1)."""

    def __init__(self, name, anode, cathode, i_s, n, rs, vt=VT_25C):
        self.name, self.a, self.k, self.i_s, self.n, self.rs, self.vt = name, anode, cathode, i_s, n, rs, vt
        self.mid = f"_{name}_mid"            # junction - series resistance node

    def current(self, v):
        x = min(v / (self.n * self.vt), 80.0)
        return self.i_s * (math.exp(x) - 1.0)

    def g(self, v):
        x = min(v / (self.n * self.vt), 80.0)
        return self.i_s * math.exp(x) / (self.n * self.vt)


class Config:
    """What the module sees.
    v3a           3V3A (= the ADC's VREF+ on the Seed) in volts
    sources       {jack ref: (volts, ohms)}: a cable in that jack (its switch opens)
    probe         None (pin as input, open) or (volts, output ohms)
    rtol          {resistor ref: factor} on the nominal value
    vos           {(chip, section): volts, + at IN+}
    inject        {node: amps into the node}
    force_out     {(chip, section): volts}: that section's output held at a voltage (a section at its rail)
    diodes        [Diode]: D21 / D22 / ESD diodes (empty: none)
    aol           op-amp DC gain"""

    def __init__(self, v3a=3.3, sources=None, probe=None, rtol=None, vos=None, inject=None, force_out=None,
                 diodes=None, aol=2e5):
        self.v3a = v3a
        self.sources = dict(sources or {})
        self.probe = probe
        self.rtol = dict(rtol or {})
        self.vos = dict(vos or {})
        self.inject = dict(inject or {})
        self.force_out = dict(force_out or {})
        self.diodes = list(diodes or [])
        self.aol = aol


class Model:
    def __init__(self, cfg):
        self.cfg = cfg
        self.res = []           # (a, b, ohms, label)
        self.vsrc = []          # (node, volts, label), referenced to GND
        self.opamps = []        # dict(name, out, m, p, vos)
        for p in PARTS:
            n = {k: node(v) for k, v in p.nets.items()}
            if p.kind == "R":
                if analog(n["1"]) and analog(n["2"]):
                    self.res.append((n["1"], n["2"], harness.ohms(p.value) * cfg.rtol.get(p.ref, 1.0), p.ref))
            elif p.kind == "JACK":
                tip, lug = n["3"], n.get("2")
                if p.ref in cfg.sources:
                    v, rs = cfg.sources[p.ref]
                    emf = "SRC_" + p.ref
                    self.vsrc.append((emf, v, p.ref))
                    self.res.append((emf, tip, max(rs, R_CONTACT), p.ref + ".src"))
                elif lug:
                    self.res.append((tip, lug, R_CONTACT, p.ref + ".switch"))
        for chip, s, o, m, pl in sections():
            self.opamps.append(dict(name=(chip, s), out=o, m=m, p=pl, vos=cfg.vos.get((chip, s), 0.0)))
        self.vsrc.append(("3V3A", cfg.v3a, "3V3A"))
        if cfg.probe is not None:
            v, rout = cfg.probe
            self.vsrc.append(("_PROBE_EMF", v, "probe"))
            self.res.append(("_PROBE_EMF", "PROBE", max(rout, R_CONTACT), "probe.rout"))
        for d in cfg.diodes:
            self.res.append((d.mid, d.k, max(d.rs, 1e-3), d.name + ".rs"))
        nodes = set()
        for a, b, _, _ in self.res:
            nodes |= {a, b}
        for o in self.opamps:
            nodes |= {o["out"], o["m"], o["p"]}
        for nd, _, _ in self.vsrc:
            nodes.add(nd)
        for d in cfg.diodes:
            nodes |= {d.a, d.mid, d.k}
        nodes |= set(cfg.inject)
        nodes.discard("GND")
        self.nodes = sorted(nodes)
        self.idx = {nd: i for i, nd in enumerate(self.nodes)}

    def _stamp_g(self, A, a, b, g):
        ia, ib = self.idx.get(a), self.idx.get(b)
        if ia is not None:
            A[ia, ia] += g
        if ib is not None:
            A[ib, ib] += g
        if ia is not None and ib is not None:
            A[ia, ib] -= g
            A[ib, ia] -= g

    def _stamp_i(self, z, a, b, i):
        """Current i flowing from a to b through the element."""
        ia, ib = self.idx.get(a), self.idx.get(b)
        if ia is not None:
            z[ia] -= i
        if ib is not None:
            z[ib] += i

    def solve(self, iters=200):
        """Node voltages {node: V}, op-amp output currents {name: A out of the pin}, diode currents {name: A}."""
        cfg = self.cfg
        N = len(self.nodes)
        M = len(self.vsrc) + len(self.opamps)
        vd = {d.name: 0.0 for d in cfg.diodes}
        for it in range(iters):
            A = np.zeros((N + M, N + M))
            z = np.zeros(N + M)
            for i in range(N):
                A[i, i] += G_LEAK
            for a, b, r, _ in self.res:
                self._stamp_g(A, a, b, 1.0 / r)
            for nd, I in cfg.inject.items():
                if nd in self.idx:
                    z[self.idx[nd]] += I
            for d in cfg.diodes:                      # companion model at the present junction voltage
                v = vd[d.name]
                g = d.g(v)
                ieq = d.current(v) - g * v
                self._stamp_g(A, d.a, d.mid, g)
                self._stamp_i(z, d.a, d.mid, ieq)
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
                if o["name"] in cfg.force_out:
                    z[k] = cfg.force_out[o["name"]]
                else:
                    if o["p"] in self.idx:
                        A[k, self.idx[o["p"]]] -= cfg.aol
                    if o["m"] in self.idx:
                        A[k, self.idx[o["m"]]] += cfg.aol
                    z[k] = cfg.aol * o["vos"]
                k += 1
            x = np.linalg.solve(A, z)
            V = {nd: x[i] for nd, i in self.idx.items()}
            V["GND"] = 0.0
            if not cfg.diodes:
                break
            done = True
            for d in cfg.diodes:
                new = V[d.a] - V[d.mid]
                old = vd[d.name]
                lim = 2 * d.n * d.vt                  # step limiting on the exponential
                if new > old + lim:
                    new = old + lim
                if abs(new - old) > 1e-9:
                    done = False
                vd[d.name] = new
            if done:
                break
        else:
            raise RuntimeError("diode iteration did not settle")
        I = {o["name"]: -x[N + len(self.vsrc) + j] for j, o in enumerate(self.opamps)}
        ID = {d.name: d.current(vd[d.name]) for d in cfg.diodes}
        self.V, self.I, self.ID = V, I, ID
        return V, I, ID


def solve(cfg):
    return Model(cfg).solve()
