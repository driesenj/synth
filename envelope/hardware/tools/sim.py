"""Envy: the netlist in circuit.py run in time, so the envelope's numbers in
docs/design.md come from the parts and not from hand estimates.

A small transient solver: modified nodal analysis with backward-Euler
capacitors, Shockley diodes (Newton iteration with SPICE's junction limiting),
and TL074 sections that are either ideal followers / inverters with output
clipping and a current limit (a section whose in- sees its own output) or
comparators (the rest: an output at one rail or the other, current-limited).
Comparator decisions are re-checked until the step is self-consistent, so the
Schmitt trigger's hysteresis comes out of its own feedback. The step shrinks
round gate edges and comparator flips. The BC548 LED drivers and the power
entry are left out (ideal rails; the BC548 takes ~25 uA from an ideal buffer).

Run from envelope/hardware/tools:  python sim.py
"""
import importlib.util
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("envy_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

VT = 0.02585
DIODE = {"D4148": (2.52e-9, 1.752),     # 1N4148, the usual SPICE model
         "DBAT85": (1.0e-7, 1.35),      # BAT85 fitted to the datasheet's 0.24 V at 0.1 mA, 0.32 V at 1 mA
         "D5819": (3.3e-8, 1.0)}
V_OH, V_OL, I_LIM = 10.5, -10.5, 0.025  # TL074 on +-12 V into ~10k; its short-circuit current, about
FIXED = {circuit.GND: 0.0, circuit.VP: 12.0, circuit.VN: -12.0}
UNITS = {"R": 1, "k": 1e3, "M": 1e6, "p": 1e-12, "n": 1e-9, "u": 1e-6}


def value(s):
    """'2k2' -> 2200, '1u' -> 1e-6, '100R' -> 100, '1u DNF' -> 1e-6."""
    s = s.split()[0]
    for u, m in UNITS.items():
        if u in s:
            a, b = s.split(u)
            return float(f"{a or 0}.{b or 0}") * m
    return float(s)


def taper(t, kind):
    """Fraction of the track between pin 1 and the wiper at rotation t (0 = CCW .. 1 = CW). An 'A' pot
    is 15 % at half travel, as Alpha's audio taper."""
    if kind == "A":
        return (32.1 ** t - 1) / 31.1
    return t


class Circuit:
    """One patch of the module: knob positions, toggles, what is patched where, and part edits."""

    def __init__(self, channels=(1,), knobs=None, loop=(), gates=None, src_r=1e3, load=100e3,
                 edits=None, fit_dnf=False):
        knobs = knobs or {}
        self.loop = tuple(loop)
        gates = gates or {1: lambda t: 0.0}
        edits = edits or {}
        parts = circuit.panel_parts() + circuit.opamp_parts() + circuit.shared_parts()
        for k in channels:
            parts += circuit.channel_parts(k)
        keep = {str(k) for k in channels}
        self.res, self.caps, self.diodes, self.amps, self.sources = [], [], [], [], {}
        for p in parts:
            if p.ref in edits:
                e = edits[p.ref]
                p.nets.update(e.get("nets", {}))
                p.value, p.kind = e.get("value", p.value), e.get("kind", p.kind)
                if p.kind in DIODE:
                    p.value = p.kind
            if p.kind in ("JACK", "POT", "TOGGLE", "LED") and p.label.split()[-1] not in keep:
                continue
            if p.kind == "R":
                self.res.append((p.nets["1"], p.nets["2"], value(p.value)))
            elif p.kind == "C":
                if "DNF" in p.value and not fit_dnf:
                    continue
                self.caps.append((p.nets["1"], p.nets["2"], value(p.value)))
            elif p.kind in DIODE:
                self.diodes.append((p.ref, p.nets["2"], p.nets["1"], *DIODE[p.kind]))
            elif p.kind == "POT":
                t = knobs.get(p.label, 0.5)
                rt = value(p.value[1:])
                f = taper(t, p.value[0])
                for a, b, r in ((p.nets["1"], p.nets["2"], f * rt), (p.nets["2"], p.nets["3"], (1 - f) * rt)):
                    if a != b:
                        self.res.append((a, b, max(r, 20.0)))      # end resistance
            elif p.kind == "TOGGLE":
                k = int(p.label.split()[-1])
                self.res.append((p.nets["2"], p.nets["3" if k in loop else "1"], 1.0))
            elif p.kind == "JACK":
                k = int(p.label.split()[-1])
                tip, lug = p.nets["3"], p.nets.get("2")
                if p.label.startswith("GATE") and k in gates:
                    src = f"SRC{k}"
                    self.sources[src] = gates[k]
                    self.res.append((src, tip, src_r))
                elif p.label.startswith("GATE"):
                    self.res.append((tip, lug, 0.01))
                else:
                    self.res.append((tip, circuit.GND, load))
            elif p.kind == "TL074":
                for sec, (o, m, pl) in circuit.SECTION.items():
                    out, inm, inp = p.nets[o], p.nets[m], p.nets[pl]
                    self.amps.append([f"{p.ref}{sec}", out, inm, inp, None])
        nets = {n for a, b, _ in self.res for n in (a, b)} | {n for a, b, _ in self.caps for n in (a, b)}
        nets |= {n for d in self.diodes for n in d[1:3]}
        # keep only the op-amp sections whose nets all belong to the simulated channels
        self.amps = [a for a in self.amps if {a[1], a[2], a[3]} <= nets | set(FIXED)]
        for a in self.amps:
            out, inm = a[1], a[2]
            linear = inm == out or any({x, y} == {inm, out} for x, y, _ in self.res)
            a[4] = "lin" if linear else "cmp"
        self.nodes = sorted(nets - set(FIXED) - set(self.sources))
        self.idx = {n: i for i, n in enumerate(self.nodes)}

    # ------------------------------------------------------------ solver
    def _stamp(self, A, b, a, c, g):
        ia, ic = self.idx.get(a), self.idx.get(c)
        va = self.fixed.get(a)
        vc = self.fixed.get(c)
        if ia is not None:
            A[ia, ia] += g
            if ic is not None:
                A[ia, ic] -= g
            else:
                b[ia] += g * vc
        if ic is not None:
            A[ic, ic] += g
            if ia is not None:
                A[ic, ia] -= g
            else:
                b[ic] += g * va

    def _isrc(self, b, a, c, i):
        """Current i flowing from node a to node c through the element."""
        if a in self.idx:
            b[self.idx[a]] -= i
        if c in self.idx:
            b[self.idx[c]] += i

    def _v(self, v, n):
        return v[self.idx[n]] if n in self.idx else self.fixed[n]

    def step(self, v0, vd0, states, t, dt):
        """One backward-Euler step from node voltages v0. Returns v, diode voltages, op-amp states."""
        self.fixed = dict(FIXED)
        self.fixed.update({s: f(t) for s, f in self.sources.items()})
        n = len(self.nodes)
        A0, b0 = np.zeros((n, n)), np.zeros(n)
        for a, c, r in self.res:
            self._stamp(A0, b0, a, c, 1.0 / r)
        for a, c, cap in self.caps:
            g = cap / dt
            self._stamp(A0, b0, a, c, g)
            vprev = (v0[self.idx[a]] if a in self.idx else self.fixed[a]) - \
                    (v0[self.idx[c]] if c in self.idx else self.fixed[c])
            self._isrc(b0, a, c, -g * vprev)
        for i in range(n):
            A0[i, i] += 1e-12
        v, vd, st = v0.copy(), dict(vd0), dict(states)
        for it in range(200):
            A, b = A0.copy(), b0.copy()
            for ref, an, ca, isat, nn in self.diodes:
                nvt = nn * VT
                x = vd[ref]
                e = math.exp(min(x / nvt, 80))
                gd, idd = isat * e / nvt + 1e-12, isat * (e - 1)
                self._stamp(A, b, an, ca, gd)
                self._isrc(b, an, ca, idd - gd * x)
            Akcl, bkcl = A.copy(), b.copy()
            for name, out, inm, inp, kind in self.amps:
                o = self.idx[out]
                s = st[name]
                if s in ("hi", "lo"):
                    A[o, :] = 0.0
                    A[o, o] = 1.0
                    b[o] = V_OH if s == "hi" else V_OL
                elif s == "lin":
                    A[o, :] = 0.0
                    b[o] = 0.0
                    for node, sign in ((inp, 1.0), (inm, -1.0)):
                        if node in self.idx:
                            A[o, self.idx[node]] += sign
                        else:
                            b[o] -= sign * self.fixed[node]
                else:                                   # current limit: the section sources +-I_LIM
                    b[o] += I_LIM if s == "src" else -I_LIM
            vn = np.linalg.solve(A, b)
            # junction limiting, then convergence
            moved = False
            for ref, an, ca, isat, nn in self.diodes:
                nvt = nn * VT
                new = self._v(vn, an) - self._v(vn, ca)
                old = vd[ref]
                vcrit = nvt * math.log(nvt / (math.sqrt(2) * isat))
                if new > vcrit and abs(new - old) > 2 * nvt:
                    arg = 1 + (new - old) / nvt
                    if old <= 0:
                        new = nvt * math.log(new / nvt)
                    else:
                        new = old + nvt * math.log(arg) if arg > 0 else vcrit
                if abs(new - old) > 1e-7:
                    moved = True
                vd[ref] = new
            changed = False
            for name, out, inm, inp, kind in self.amps:
                err = self._v(vn, inp) - self._v(vn, inm)
                vo = self._v(vn, out)
                io = Akcl[self.idx[out]] @ vn - bkcl[self.idx[out]]     # current the section drives out
                s, new = st[name], st[name]
                if kind == "cmp":
                    want = "hi" if err > 0 else "lo"
                    if s in ("hi", "lo") and s != want:
                        new = want
                    elif s in ("hi", "lo") and abs(io) > I_LIM:
                        new = "src" if io > 0 else "snk"
                    elif s == "src" and (err < 0 or vo > V_OH):
                        new = "hi" if err > 0 else "lo"
                    elif s == "snk" and (err > 0 or vo < V_OL):
                        new = "lo" if err < 0 else "hi"
                else:
                    if s == "lin":
                        if vo > V_OH:
                            new = "hi"
                        elif vo < V_OL:
                            new = "lo"
                        elif abs(io) > I_LIM:
                            new = "src" if io > 0 else "snk"
                    elif s == "hi" and err < 0 or s == "lo" and err > 0:
                        new = "lin"
                    elif s == "src" and (err < 0 or vo > V_OH):
                        new = "lin"
                    elif s == "snk" and (err > 0 or vo < V_OL):
                        new = "lin"
                if new != s:
                    st[name] = new
                    changed = True
            done = not moved and not changed and np.max(np.abs(vn - v)) < 1e-6
            v = vn
            if done:
                return v, vd, st
        raise RuntimeError(f"no convergence at t = {t:.6f} s")

    def run(self, t_end, dt_max=1e-3, edges=(), probes=(), fine=2e-4, fine_for=0.04):
        """Simulate to t_end. edges: times where a source jumps (steps land on them). Returns the times,
        {probe: values} and the comparator flips [(t, section, state)]."""
        v = np.zeros(len(self.nodes))
        vd = {d[0]: 0.0 for d in self.diodes}
        st = {a[0]: ("lin" if a[4] == "lin" else "lo") for a in self.amps}
        cmp = {a[0] for a in self.amps if a[4] == "cmp"}
        # settle at t = 0 with the caps as they would be after a long rest (a looping channel has no rest)
        for _ in range(0 if self.loop else 30):
            v, vd, st = self.step(v, vd, st, 0.0, 1.0)
        ts, out, flips = [0.0], {p: [self._v(v, p)] for p in probes}, []
        t, dt, quiet_from = 0.0, 1e-5, 0.0
        edges = sorted(e for e in edges if 0 < e < t_end) + [t_end]
        while t < t_end - 1e-12:
            nxt = next(e for e in edges if e > t + 1e-12)
            lim = fine if t - quiet_from < fine_for else dt_max
            h = min(dt, lim, nxt - t)
            try:
                v1, vd1, st1 = self.step(v, vd, st, t + h, h)
            except RuntimeError:
                if h <= 1e-6:
                    raise
                dt = h / 4
                continue
            flipped = [a for a in cmp if st1[a] in ("hi", "lo") and st[a] in ("hi", "lo") and st1[a] != st[a]]
            if flipped and h > 2e-6:
                dt = max(h / 4, 1e-6)
                continue
            for a in flipped:
                flips.append((t + h, a, st1[a]))
            if flipped or any(abs(t + h - e) < 1e-12 for e in edges[:-1]):
                quiet_from, dt = t + h, 1e-5
            else:
                dt = min(h * 1.5, dt_max)
            t, v, vd, st = t + h, v1, vd1, st1
            ts.append(t)
            for p in probes:
                out[p].append(self._v(v, p))
        return np.array(ts), {p: np.array(x) for p, x in out.items()}, flips


# ---------------------------------------------------------------- measurements
def gate(on, off, level=10.0):
    return lambda t: level if on <= t < off else 0.0


def burst_ms(flips, sec):
    ups = [t for t, a, s in flips if a == sec and s == "hi"]
    downs = [t for t, a, s in flips if a == sec and s == "lo"]
    return (downs[0] - ups[0]) * 1e3 if ups and downs else float("nan")


def when_below(ts, x, level, after):
    i = np.where((ts > after) & (x < level))[0]
    return ts[i[0]] - after if len(i) else float("nan")


def at(ts, x, t):
    return float(np.interp(t, ts, x))


SEC = {"gate": "U1A", "burst": "U1B", "loop": "U3A"}       # channel 1's sections
CH1 = ["ENV1", "INVO1", "OUT1", "INV1", "G1", "N1", "HP1", "GIN1", "SC1", "BUF1"]


def main():
    rows = []

    def report(name, got, want, tol, unit=""):
        ok = abs(got - want) <= tol if want is not None else True
        w = f"{want:.3g} +- {tol:g}{unit}" if want is not None else ""
        rows.append((name, f"{got:.3g}{unit}", w, "" if ok else "  <-- off"))

    # 1. pluck: fast attack, no sustain, 10 V and 5 V gates: same burst, same peak
    for lvl in (10.0, 5.0):
        c = Circuit(knobs={"ATTACK 1": 0.0, "DEC/REL 1": 0.5, "SUSTAIN 1": 0.0}, gates={1: gate(0.01, 0.31, lvl)})
        ts, x, fl = c.run(0.6, dt_max=5e-4, edges=(0.01, 0.31), probes=CH1)
        report(f"burst, {lvl:.0f} V gate", burst_ms(fl, SEC["burst"]), 13.7, 1.0, " ms")
        report(f"peak ENV, {lvl:.0f} V gate, SUSTAIN at 0", x["ENV1"].max(), 9.9, 0.2, " V")
        if lvl == 10.0:
            report("G (the gate comparator through its diode)", at(ts, x["G1"], 0.2), 9.9, 0.3, " V")
            report("INV at rest", at(ts, x["INV1"], 0.005), 9.71 * 100 / 101, 0.1, " V")
            report("INV at the peak", x["INV1"].min(), -0.2, 0.2, " V")
    # the kit's high-pass on the jack and its 3.8 V threshold, for comparison
    for lvl in (10.0, 5.0):
        c = Circuit(knobs={"ATTACK 1": 0.0, "DEC/REL 1": 0.5, "SUSTAIN 1": 0.0}, gates={1: gate(0.01, 0.31, lvl)},
                    src_r=1.0, edits={"C101": {"nets": {"1": "GATE1"}}, "R902": {"value": "47k"}})
        ts, x, fl = c.run(0.1, dt_max=5e-4, edges=(0.01,), probes=CH1)
        report(f"kit's burst, {lvl:.0f} V gate", burst_ms(fl, SEC["burst"]), 9.6 if lvl == 10 else 2.6, 0.5, " ms")
    # the fastest edges, set by the TL074's current limit into C_T
    c = Circuit(knobs={"ATTACK 1": 0.0, "DEC/REL 1": 0.0, "SUSTAIN 1": 0.0}, gates={1: gate(0.01, 0.06)})
    ts, x, fl = c.run(0.04, dt_max=2e-6, fine=2e-6, edges=(0.01,), probes=CH1)
    e, pk = x["ENV1"], x["ENV1"].max()
    report("fastest attack, 10-90 %", (ts[np.argmax(e > 0.9 * pk)] - ts[np.argmax(e > 0.1 * pk)]) * 1e3, 0.4, 0.1, " ms")
    # past the burst a slow attack only rises towards the sustain level: with SUSTAIN at 0 it barely moves
    c = Circuit(knobs={"ATTACK 1": 0.2, "DEC/REL 1": 0.5, "SUSTAIN 1": 0.0}, gates={1: gate(0.01, 0.5)})
    ts, x, fl = c.run(0.1, dt_max=5e-4, edges=(0.01,), probes=CH1)
    report("ATTACK at 9 o'clock, SUSTAIN at 0: peak", x["ENV1"].max(), 3.4, 0.3, " V")
    # 2. ADSR: sustain, then release, and the tail it leaves (BAT85 here, the kit's 1N4148 for comparison)
    for steer in ("DBAT85", "D4148"):
        edits = {} if steer == "DBAT85" else {"D105": {"kind": "D4148"}, "D106": {"kind": "D4148"}}
        c = Circuit(knobs={"ATTACK 1": 0.0, "DEC/REL 1": 0.25, "SUSTAIN 1": 0.8}, gates={1: gate(0.01, 0.51)},
                    edits=edits)
        ts, x, fl = c.run(2.6, dt_max=2e-3, edges=(0.01, 0.51), probes=CH1)
        tag = "BAT85" if steer == "DBAT85" else "1N4148 (kit)"
        if steer == "DBAT85":
            s_want = at(ts, x["G1"], 0.4) * taper(0.8, "A")
            report("sustain level", at(ts, x["ENV1"], 0.5), s_want, 0.15, " V")
        report(f"tail 0.5 s after the gate, {tag}", at(ts, x["ENV1"], 1.01), None, 0, " V")
        report(f"tail 2 s after the gate, {tag}", at(ts, x["ENV1"], 2.51), None, 0, " V")
    # 3. slow: everything clockwise, 6 s gate
    c = Circuit(knobs={"ATTACK 1": 1.0, "DEC/REL 1": 1.0, "SUSTAIN 1": 1.0}, gates={1: gate(0.01, 6.01)})
    ts, x, fl = c.run(11.0, dt_max=5e-3, edges=(0.01, 6.01), probes=CH1)
    top = at(ts, x["ENV1"], 6.0)
    report("slow attack: top after 6 s", top, 9.9, 0.2, " V")
    report("slow attack: time to 95 %", when_below(ts, -x["ENV1"], -0.95 * top, 0.01), 3.0, 0.4, " s")
    report("slow release: time to 0.1 V", when_below(ts, x["ENV1"], 0.1, 6.01), 4.3, 0.4, " s")
    # 4. LOOP, slowest and fastest
    c = Circuit(knobs={"ATTACK 1": 1.0, "DEC/REL 1": 1.0}, loop=(1,))
    ts, x, fl = c.run(14.0, dt_max=5e-3, probes=CH1)
    ups = [t for t, a, s in fl if a == SEC["loop"] and s == "hi"]
    report("LOOP slowest: period", ups[-1] - ups[-2], 4.0, 0.4, " s")
    m = ts > ups[-2]
    report("LOOP: ENV top", x["ENV1"][m].max(), 7.5, 0.3, " V")
    report("LOOP: ENV bottom", x["ENV1"][m].min(), 0.5, 0.15, " V")
    c = Circuit(knobs={"ATTACK 1": 0.0, "DEC/REL 1": 0.0}, loop=(1,))
    ts, x, fl = c.run(0.01, dt_max=2e-6, fine=2e-6, probes=CH1)
    ups = [t for t, a, s in fl if a == SEC["loop"] and s == "hi"]
    report("LOOP fastest: frequency", 1.0 / np.mean(np.diff(ups[-6:])), None, 0, " Hz")
    # 5. a negative LFO into GATE 1 must not fire it
    c = Circuit(gates={1: lambda t: -10.0 if t > 0.005 else 0.0})
    ts, x, fl = c.run(0.05, dt_max=5e-4, edges=(0.005,), probes=CH1)
    report("-10 V into GATE: GIN", x["GIN1"].min(), -0.55, 0.15, " V")
    report("-10 V into GATE: comparator flips", len(fl), 0, 0)
    # 6. the normals: one gate into GATE 1 fires all four channels
    knobs = {f"{w} {k}": t for k in range(1, 5) for w, t in (("ATTACK", 0.0), ("SUSTAIN", 1.0))}
    c = Circuit(channels=(1, 2, 3, 4), knobs=knobs,
                gates={1: gate(0.005, 0.2, 5.0)})
    ts, x, fl = c.run(0.06, dt_max=5e-4, edges=(0.005,), probes=["GATE1", "GATE4"] + [f"ENV{k}" for k in range(1, 5)])
    report("5 V gate through 1k into four inputs: GATE 4", x["GATE4"].max(), 5.0 * 27.5 / 28.5, 0.05, " V")
    peaks = [x[f"ENV{k}"].max() for k in range(1, 5)]
    report("normals: lowest ENV peak of the four, SUSTAIN full", min(peaks), 10.1, 0.2, " V")
    report("normals: spread of the four peaks", max(peaks) - min(peaks), 0.0, 0.02, " V")

    w = max(len(r[0]) for r in rows)
    for name, got, want, flag in rows:
        print(f"  {name:<{w}}  {got:>10}   {want}{flag}")
    print(f"{sum(1 for r in rows if r[3])} off")


if __name__ == "__main__":
    main()
