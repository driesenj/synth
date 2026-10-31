"""Atlasy: the filter's and the scanner's behaviour computed from the part
values in circuit.py, so a value change that breaks a sign or a level shows
up before a board does.

Filter (channel 1, ideal op-amps and cells): passband and peak levels of LP,
HP and BP for a few resonance-cell gains, and the loop gain at the cutoff
(it must be real and positive: the oscillation threshold is where it is 1).
Scanner: the PNP current line with Ebers-Moll transistors and the emitter
resistors, swept over the SCAN knob; the four VCA shares must add up to 1
and each channel must have its knob position where it is (nearly) alone.

Run from atlas/hardware/tools:  python sim.py
"""
import importlib.util
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("atlas_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

UNITS = {"R": 1, "k": 1e3, "M": 1e6, "p": 1e-12, "n": 1e-9, "u": 1e-6}


def value(s):
    """'2.7k' -> 2700, '1n2' -> 1.2e-9, '220R' -> 220."""
    for u, m in UNITS.items():
        if u in s:
            a, b = s.split(u)
            return float(f"{a or 0}.{b}" if b and "." not in a else (a or "0")) * m
    return float(s)


V = {p.ref: value(p.value) for p in circuit.all_parts() if p.kind in ("R", "C")}


def filter_response(f, fc, gr):
    """LP, HP, BP (relative to IN) and the resonance loop gain of channel 1 at frequency f."""
    h = 1 / (1 + 1j * f / fc)
    rf, rin, rres = V["R102"], V["R101"], V["R130"] + V["R131"]
    bp_of_a = -V["R127"] * (h ** 2 / V["R124"] - h ** 3 / V["R125"] + h ** 4 / V["R126"])
    loop = -(rf / rres) * gr * bp_of_a              # A = -(rf / rin) IN + loop * A
    a = -(rf / rin) / (1 - loop)
    lp = -(V["R129"] / V["R128"]) * h ** 4 * a
    hp = -V["R123"] * (a / V["R120"] - h * a / V["R121"] + h ** 2 * a / V["R122"])
    return lp, hp, bp_of_a * a, loop


# ---------------------------------------------------------------- scanner
IS, VT = 1e-14, 0.0259
P12F = 12.0 - 3.4e-3 * V["R903"]                    # about 3.4 mA of knobs, offsets and ladder on the filter


def _branch(vdrop, re):
    """Current through an emitter resistor and an emitter-base junction with vdrop across both."""
    if vdrop <= 0:
        return 0.0
    lo, hi = 0.0, vdrop / re + 1e-9
    for _ in range(80):
        m = (lo + hi) / 2
        if m * re + VT * math.log(m / IS + 1) > vdrop:
            hi = m
        else:
            lo = m
    return lo


def _pair(it, va, vb, re):
    """Split of tail current it between two PNPs with bases va, vb (the lower base takes more)."""
    if it <= 0:
        return 0.0, 0.0
    lo, hi = min(va, vb), max(va, vb) + 2.0
    for _ in range(80):
        e = (lo + hi) / 2
        if _branch(e - va, re) + _branch(e - vb, re) > it:
            hi = e
        else:
            lo = e
    return _branch(e - va, re), _branch(e - vb, re)


def scanner(p, cv=0.0):
    """Shares of the tail current in W1..W4 at knob position p (0..1) and SCAN CV cv."""
    y = 1 / V["R501"] + 1 / V["R502"] + 1 / V["R503"] + 1 / V["R504"]
    gain = 1 + V["R505"] / V["R506"]
    s1 = gain * (P12F * p / V["R501"] + cv / V["R502"] + P12F / V["R503"]) / y
    vbn = -12.0 * V["R510"] / (V["R510"] + V["R511"])
    shift = (vbn - 0.65 + 12.0) / V["R509"] * V["R507"]
    lad = V["R512"] + V["R513"] + V["R514"] + V["R515"]
    r1 = P12F * (V["R513"] + V["R514"] + V["R515"]) / lad
    r2 = P12F * (V["R514"] + V["R515"]) / lad
    r3 = P12F * V["R515"] / lad
    vbp = 12.0 * V["R518"] / (V["R517"] + V["R518"])
    i0 = (12.0 - vbp - 0.65) / V["R516"]
    re = V["R519"]
    w1, t2 = _pair(i0, s1, r1, re)
    w2, t3 = _pair(t2, s1 - shift, r2, re)
    w3, w4 = _pair(t3, s1 - 2 * shift, r3, re)
    return s1, i0, [w / i0 for w in (w1, w2, w3, w4)]


def main():
    fc = 1000.0
    print("filter, channel 1 (dB re IN): 10 Hz / cutoff / 100 kHz")
    for gr in (0.0, 0.2, 0.4):
        row = []
        for name, i in (("LP", 0), ("HP", 1), ("BP", 2)):
            lv = [20 * math.log10(abs(filter_response(f, fc, gr)[i]) + 1e-12) for f in (10, fc, 1e5)]
            row.append(f"{name} {lv[0]:6.1f} {lv[1]:6.1f} {lv[2]:6.1f}")
        print(f"  cell gain {gr:.1f}: " + " | ".join(row))
    loop = filter_response(fc, fc, 1.0)[3]
    print(f"  loop gain at the cutoff per unit cell gain: {loop.real:.2f} {loop.imag:+.2f}j "
          f"-> oscillation from cell gain {1 / loop.real:.2f} ({-0.66 * math.log10(1 / loop.real):.2f} V on VC)")
    print("scanner: knob, S1, shares of W1..W4, sum")
    best = [(0, 0.0)] * 4
    for i in range(25):
        p = i / 24
        s1, i0, w = scanner(p)
        for k in range(4):
            if w[k] > best[k][1]:
                best[k] = (p, w[k])
        if i % 2 == 0:
            print(f"  {p:4.2f} {s1:5.2f}  " + " ".join(f"{x:5.3f}" for x in w) + f"  {sum(w):.4f}")
    print(f"  tail {i0 * 1e3:.3f} mA; each channel's best spot: "
          + ", ".join(f"{k + 1} at {p:.2f} ({x:.3f})" for k, (p, x) in enumerate(best)))


if __name__ == "__main__":
    main()
