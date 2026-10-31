"""Veilsy: what the netlist in circuit.py does, computed from its part values.

Two parts:
  dc       a Newton solve of both boards' netlist (joined at the headers):
           resistors and pots, Shockley diodes and LEDs, the BC557 clamps, the
           TL074 sections as high-gain amplifiers that clip at +-10.5 V, the
           SSI2164 cells as the datasheet describes them (input pin at virtual
           ground, the same current out of the output pin times the gain, gain
           -33 mV/dB at a 10k control port), ideal references. Capacitors are
           open. It checks the LIN, EXP and blended laws, unity, the closed
           channel, the normals, the output chain, the LED current and the
           input loading against numbers worked out by hand.
  servo    the LIN servo loop in time: the integrator op-amp as a 3 MHz
           gain-bandwidth integrator, its 100p, 10 pF on the summing node,
           the 4k7, the two 10k control ports, the RESPONSE pot and the clamp.
           Steps of C show how fast a closed channel opens and how quickly
           the loop settles at low gain, and that it does not ring.
Run from vca/hardware/tools:  python sim.py
"""
import importlib.util
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("veilsy_circuit", os.path.join(HERE, "circuit.py"))
circuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(circuit)

VT = 0.02585                             # thermal voltage at 25 C
K_DB = 0.033                             # SSI2164: 33 mV per dB, positive attenuates
VC_NEPER = 20 * K_DB / math.log(10)      # 0.2866 V per neper of gain
VC_PORT = 10e3                           # control port input impedance
VSAT, A_OL = 10.5, 1e5                   # TL074 on +-12 V: output swing, open-loop gain
DIODES = {"D4148": (2.5e-9, 1.75), "LED": (1.5e-18, 2.0)}     # (Is, n): 0.58 V / 1.85 V at 1 / 2 mA
PNP_IS, PNP_BETA = 2.4e-14, 300                               # BC557B: 0.65 V at 2 mA
STEP = 0.3                               # volts per Newton iteration, at most
FIXED = {circuit.GND: 0.0, circuit.VP: 12.0, circuit.VN: -12.0, circuit.P5: 5.0, circuit.N5: -5.0,
         circuit.P5L: 5.0}
SKIP = {"HDR16", "D5819", "CP", "C", "LM4040", "78L05"}       # power entry, capacitors, ideal references
SKIP_REFS = {"R905", "R906"}


def ohms(v):
    """'100k' -> 1e5, '49k9' -> 49900, '220R' -> 220."""
    for unit, mul in (("k", 1e3), ("R", 1.0), ("M", 1e6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


# both boards as one circuit: a faceplate net is its main-board net
CANON = {f: m for _, _, pins in circuit.HEADERS for m, f in pins}


def canon(n):
    return CANON.get(n, n)


PARTS = [p for p in circuit.all_parts() if p.kind not in SKIP and p.ref not in SKIP_REFS
         and not p.ref.startswith("H")]


def channel_of(label):
    return int(label.split()[-1])


# ------------------------------------------------------------------ DC solve
def elements(case):
    """The circuit for one patch: (resistors, diodes, pnps, opamps, cells, fixed). case: level / amt /
    resp {k: 0..1 from CCW}, ins / cvs {k: volts} on patched inputs (source_r ohms behind them), outs:
    patched OUT jacks (100k loads)."""
    res, dio, pnp, amps, cells = [], [], [], [], []
    fixed = dict(FIXED)
    src_r = case.get("source_r", 1.0)
    for p in PARTS:
        n = {pid: canon(x) for pid, x in p.nets.items()}
        if p.kind == "R":
            res.append((n["1"], n["2"], ohms(p.value)))
        elif p.kind == "POT":
            k = channel_of(p.label)
            t = case[{"LEVEL": "level", "CV": "amt", "RESPONSE": "resp"}[p.label.split()[0]]][k]
            rt = ohms(p.value[1:])
            res.append((n["1"], n["2"], max(t, 1e-6) * rt))
            res.append((n["2"], n["3"], max(1 - t, 1e-6) * rt))
        elif p.kind == "JACK":
            k, kind = channel_of(p.label), p.label.split()[0]
            tip, lug = n["3"], n.get("2")
            patched = {"IN": case.get("ins", {}), "CV": case.get("cvs", {}), "OUT": case.get("outs", ())}[kind]
            if k not in patched:
                if lug:
                    res.append((tip, lug, 1.0))         # 1 ohm against 100k: 1e-5
            elif kind == "OUT":
                res.append((tip, circuit.GND, 100e3))
            else:
                fixed[f"SRC_{p.ref}"] = patched[k]
                res.append((f"SRC_{p.ref}", tip, src_r))
        elif p.kind in ("D4148", "LED"):
            a, c = (n["2"], n["1"]) if p.kind == "D4148" else (n["1"], n["2"])
            dio.append((a, c, *DIODES[p.kind], p.ref))
        elif p.kind == "PNP":
            pnp.append((n["E"], n["B"], n["C"]))
        elif p.kind == "TL074":
            for out, inm, inp in circuit.SECTION.values():
                amps.append((n[out], n[inm], n[inp]))
        elif p.kind == "SSI2164":
            for iin, vc, iout in circuit.CELL.values():
                cells.append((n[iin], n[vc], n[iout]))
                res.append((n[vc], circuit.GND, VC_PORT))
        else:
            raise ValueError(f"no model for {p.ref} ({p.kind})")
    return res, dio, pnp, amps, cells, fixed


def _diode(v, i_s, n):
    """Current and conductance, linear past 40 n Vt so Newton cannot overflow."""
    x = v / (n * VT)
    if x > 40:
        e = math.exp(40)
        return i_s * (e * (1 + x - 40) - 1), i_s * e / (n * VT)
    e = math.exp(x)
    return i_s * (e - 1), i_s * e / (n * VT)


def solve(case, iters=300, debug=False):
    """Newton over the node voltages, the op-amp output currents and the cells' input currents, each
    node moving at most STEP volts per iteration (the cells' exponential law and the diodes need it;
    a line search did not help). The op-amps are linear (gain 1e5) until an output runs far past the
    rail; then it is held at the rail until its inputs ask to come back (an active set). That is how
    the LIN integrator behaves at C <= 0, the one place where an op-amp here saturates on purpose.
    (Ideal op-amps leave the EXP half-wave's output undetermined while both its diodes are off.)"""
    res, dio, pnp, amps, cells, fixed = elements(case)
    names = set()
    for a, b, _ in res:
        names |= {a, b}
    for a, c, *_ in dio:
        names |= {a, c}
    for e in pnp:
        names |= set(e)
    for e in amps + cells:
        names |= set(e)
    nodes = sorted(names - set(fixed))
    idx = {x: i for i, x in enumerate(nodes)}
    nv = len(nodes)
    n_amp, n_cell = len(amps), len(cells)
    size = nv + n_amp + n_cell
    sat = [0] * n_amp                             # 0 linear, +1 / -1 held at the positive / negative rail
    vos = case.get("vos", 0.0)                    # every section's input offset, volts

    def system(x):
        F = np.zeros(size)
        J = np.zeros((size, size))

        def volt(net):
            return fixed[net] if net in fixed else x[idx[net]]

        def flow(net, i, grads):
            """Current i leaves node net; grads: [(net or unknown index, d i / d it)]."""
            if net in fixed:
                return
            r = idx[net]
            F[r] += i
            for var, g in grads:
                c = idx.get(var) if isinstance(var, str) else var
                if c is not None:
                    J[r, c] += g

        def row_volts(row, terms, const):
            """Constraint row: sum(s * V(net)) + const = 0."""
            F[row] = const + sum(s * volt(n) for n, s in terms)
            for n, s in terms:
                if n in idx:
                    J[row, idx[n]] += s

        for i in range(nv):                          # gmin
            F[i] += 1e-12 * x[i]
            J[i, i] += 1e-12
        for a, b, r in res:
            g = 1.0 / r
            i = g * (volt(a) - volt(b))
            flow(a, i, [(a, g), (b, -g)])
            flow(b, -i, [(a, -g), (b, g)])
        for a, c, i_s, n, _ in dio:
            i, g = _diode(volt(a) - volt(c), i_s, n)
            flow(a, i, [(a, g), (c, -g)])
            flow(c, -i, [(a, -g), (c, g)])
        for e, b, c in pnp:                          # forward-active only: the clamp never saturates
            ie, g = _diode(volt(e) - volt(b), PNP_IS, 1.0)
            ib, gb = ie / (PNP_BETA + 1), g / (PNP_BETA + 1)
            flow(e, ie, [(e, g), (b, -g)])
            flow(b, -ib, [(e, -gb), (b, gb)])
            flow(c, -(ie - ib), [(e, -(g - gb)), (b, g - gb)])
        for j, (o, m, p) in enumerate(amps):
            row = nv + j
            flow(o, -x[row], [(row, -1.0)])
            if sat[j]:
                row_volts(row, [(o, 1.0)], -sat[j] * VSAT)
            else:                                  # V(o) = A (V+ - V- + Vos), scaled by 1 / A
                row_volts(row, [(p, 1.0), (m, -1.0), (o, -1.0 / A_OL)], vos)
        for j, (iin, vc, iout) in enumerate(cells):  # V(IIN) = 0; I into IIN comes out of IOUT times G
            row = nv + n_amp + j
            i_in = x[row]
            flow(iin, i_in, [(row, 1.0)])
            gain = math.exp(-max(volt(vc), -1.0) / VC_NEPER)
            dg = -gain / VC_NEPER if volt(vc) > -1.0 else 0.0
            flow(iout, -gain * i_in, [(row, -gain), (vc, -dg * i_in)])
            row_volts(row, [(iin, 1.0)], 0.0)
        return F, J

    def out_v(x, j):
        o = amps[j][0]
        return fixed[o] if o in fixed else x[idx[o]]

    x = np.zeros(size)
    for _round in range(20):
        for it in range(iters):
            F, J = system(x)
            dx = np.linalg.solve(J, -F)
            dx[:nv] = np.clip(dx[:nv], -STEP, STEP)  # limited Newton, as SPICE limits its junctions
            x = x + dx
            if debug:
                print(_round, it, f"residual {np.max(np.abs(F[:nv])):.3g} A, step {np.max(np.abs(dx[:nv])):.3g} V",
                      nodes[int(np.argmax(np.abs(dx[:nv])))], [amps[j][0] for j in range(n_amp) if sat[j]])
            # an output that runs far past the rail (the LIN integrator at C <= 0) is held at the rail
            railed = [j for j in range(n_amp) if not sat[j] and abs(out_v(x, j)) > 3 * VSAT]
            for j in railed:
                sat[j] = 1 if out_v(x, j) > 0 else -1
            if railed:
                continue
            if np.max(np.abs(dx[:nv])) < 1e-10 and np.max(np.abs(F[:nv])) < 1e-11:
                break
        else:
            raise RuntimeError(f"no convergence: {case}")
        released = False                           # a railed op-amp whose inputs now ask the other way
        for j, (o, m, p) in enumerate(amps):
            if sat[j]:
                vd = (fixed.get(p, x[idx[p]] if p in idx else 0.0) - fixed.get(m, x[idx[m]] if m in idx else 0.0))
                if vd * sat[j] < 0:
                    sat[j], released = 0, True
            elif abs(out_v(x, j)) > VSAT:
                sat[j], released = (1 if out_v(x, j) > 0 else -1), True
        if not released:
            break
    v = dict(fixed)
    v.update({n: x[i] for n, i in idx.items()})
    v["_led"] = {ref: _diode(v[a] - v[c], i_s, n)[0] for a, c, i_s, n, ref in dio if ref.startswith("D") and
                 len(ref) == 2}
    v["_railed"] = [amps[j][0] for j in range(n_amp) if sat[j]]
    return v


def case(level=0.0, amt=0.0, resp=0.0, **kw):
    """The same knob positions on all four channels, plus patches."""
    each = lambda t: {k: t for k in circuit.CH}
    return dict(level=each(level), amt=each(amt), resp=each(resp), **kw)


def gain_db(v, k):
    """Channel k's gain: the inverter's output over the voltage at its IN tip."""
    g = v[f"BO{k}"] / v[f"IN{k}"]
    return 20 * math.log10(abs(g)) if g else -999.0


ALL_OUT = tuple(circuit.CH)
LAW = {"LIN": 0.0, "noon": 0.5, "EXP": 1.0}


def c_offset():
    """The LIN servo's bias in volts of C: 5 V through the bias resistor against C through 100k."""
    p = {q.ref: q for q in circuit.main_board_parts()}
    return 5.0 * ohms(p["R112"].value) / ohms(p["R118"].value)


def lin_gain(c):
    """The LIN law from the netlist: (R114 / R112) (C - offset) / 5 V."""
    p = {q.ref: q for q in circuit.main_board_parts()}
    return max(ohms(p["R114"].value) / ohms(p["R112"].value) * (c - c_offset()) / 5, 0.0)


def expected_db(c, resp):
    lin = 20 * math.log10(lin_gain(c)) if lin_gain(c) > 0 else -999
    exp_ = -0.5 * (5 - c) / K_DB
    return {"LIN": lin, "EXP": exp_, "noon": (lin + exp_) / 2}[resp]


def dc_checks():
    bad, table = [], {}
    # the laws: C from CV 1 at full CV AMT (normalled to all four channels), LEVEL at zero, 1 V into IN 1
    for c in (0.5, 1, 2, 2.5, 3, 4, 5, 7.5, 10):
        for name, t in LAW.items():
            v = solve(case(0.0, 1.0, t, ins={1: 1.0}, cvs={1: float(c)}, outs=ALL_OUT))
            dbs = [gain_db(v, k) for k in circuit.CH]
            table[(c, name)] = dbs[0]
            if c <= 5:
                want = expected_db(c, name)
                for k, db in zip(circuit.CH, dbs):
                    if abs(db - want) > 0.15:
                        bad.append(f"C = {c} V, {name}, channel {k}: {db:+.2f} dB, expected {want:+.2f}")
            elif max(dbs) > 6.5 or min(dbs) < 0:
                bad.append(f"C = {c} V, {name}: {dbs}, expected 0 .. +6.5 dB")
    # LEVEL fully CW alone is unity, whatever RESPONSE says
    for name, t in LAW.items():
        v = solve(case(1.0, 0.0, t, ins={1: 1.0}, outs=ALL_OUT))
        for k in circuit.CH:
            if abs(gain_db(v, k)) > 0.05:
                bad.append(f"LEVEL CW, {name}, channel {k}: {gain_db(v, k):+.3f} dB, expected 0")
    # closed: LIN clamps at about -103 dB; EXP's floor is -76 dB; negative CV closes both further
    closed = {}
    for c in (0.0, -5.0):
        for name, t in LAW.items():
            v = solve(case(0.0, 1.0, t, ins={1: 1.0}, cvs={1: c}, outs=ALL_OUT))
            closed[(c, name)] = (gain_db(v, 1), v["VCL1"], v["VCE1"])
    if closed[(0.0, "LIN")][0] > -100:
        bad.append(f"LIN at C = 0: {closed[(0.0, 'LIN')][0]:.1f} dB, expected below -100")
    if abs(closed[(0.0, "EXP")][0] - expected_db(0.0, "EXP")) > 0.3:
        bad.append(f"EXP at C = 0: {closed[(0.0, 'EXP')][0]:.1f} dB, expected {expected_db(0.0, 'EXP'):.1f}")
    for vos in (-0.010, 0.010):                  # a TL074C's worst offset, either sign, on every section:
        vp, vn = (solve(case(0.0, 1.0, 0.0, ins={1: x}, cvs={1: 0.0}, outs=ALL_OUT, vos=vos)) for x in (1.0, -1.0))
        g = (vp["BO1"] - vn["BO1"]) / (vp["IN1"] - vn["IN1"])          # measured differentially: the
        db = 20 * math.log10(abs(g)) if g else -999.0                  # outputs' DC offset cancels
        closed[(0.0, f"LIN, Vos {vos * 1e3:+.0f} mV")] = (db, vp["VCL1"], vp["VCE1"])
        if db > -100:
            bad.append(f"LIN at C = 0 with {vos * 1e3:+.0f} mV offsets: {db:.1f} dB, expected below -100")
    if closed[(-5.0, "EXP")][0] > -100 or closed[(-5.0, "LIN")][0] > -100:
        bad.append(f"C = -5 V does not close the channel: {closed[(-5.0, 'LIN')][0]:.1f} / "
                   f"{closed[(-5.0, 'EXP')][0]:.1f} dB")
    # the CV normals: CV 1 feeds all four; CV 3 takes over channels 3 and 4
    v = solve(case(0.0, 1.0, 0.0, ins={1: 1.0}, cvs={1: 2.0, 3: 4.0}, outs=ALL_OUT))
    for k, want in zip(circuit.CH, [lin_gain(x) for x in (2.0, 2.0, 4.0, 4.0)]):
        if abs(v[f"BO{k}"] - want) > 1e-3:
            bad.append(f"CV normals: channel {k} gain {v[f'BO{k}']:.4f}, expected {want}")
    # the IN normals and the chain: 1 V into IN 1 only, every channel at unity
    h = 100 / 101                                # a hop: OUT k's tip (behind 1k) into 100k
    chain = [
        ("OUT 4 only: OUT 4 is the sum", (4,), {4: 1 + h * (1 + h * (1 + h))}),
        ("OUT 2 and OUT 4: two pairs", (2, 4), {2: 1 + h, 3: 1.0, 4: 1 + h}),
        ("every output patched: no chain", ALL_OUT, {k: 1.0 for k in circuit.CH}),
    ]
    for name, outs, want in chain:
        v = solve(case(1.0, 0.0, 0.0, ins={1: 1.0}, outs=outs))
        for k, w in want.items():
            if abs(v[f"BO{k}"] - w) > 2e-3:
                bad.append(f"{name}: BO{k} = {v[f'BO{k}']:.4f} V, expected {w:.4f}")
    v = solve(case(1.0, 0.0, 0.0, ins={1: 1.0, 2: -2.0}, outs=ALL_OUT))
    if abs(v["BO2"] + 2.0) > 2e-3 or abs(v["BO3"] + 2.0) > 2e-3:
        bad.append(f"IN 2 patched: BO2 {v['BO2']:.4f}, BO3 {v['BO3']:.4f}, expected -2 (IN 3 follows IN 2)")
    # the LEDs: current at unity, at -40 dB in LIN, at EXP's floor, closed in LIN
    leds = {}
    for name, cv, t in (("unity", 5.0, 0.0), ("-40 dB, LIN", 0.05 + c_offset(), 0.0),
                        ("-60 dB, LIN", 0.005 + c_offset(), 0.0), ("-38 dB, EXP", 2.5, 1.0),
                        ("EXP floor", 0.0, 1.0), ("LIN closed", 0.0, 0.0)):
        v = solve(case(0.0, 1.0, t, ins={1: 1.0}, cvs={1: cv}, outs=ALL_OUT))
        leds[name] = (v["_led"]["D1"] * 1e3, gain_db(v, 1), v["VC1"])
    # loading: a source with a 1k output impedance into IN 1, normalled on to all four inputs
    v = solve(case(1.0, 0.0, 0.0, ins={1: 1.0}, outs=ALL_OUT, source_r=1e3))
    fan = v["IN1"]
    return bad, table, closed, leds, fan


# ------------------------------------------------------------------ the servo in time
def servo_params():
    """The loop's part values, read from the netlist (channel 1)."""
    p = {q.ref: q for q in circuit.main_board_parts()}
    vclamp = 12.0 * ohms(p["R904"].value) / (ohms(p["R903"].value) + ohms(p["R904"].value))
    resp = {ref: v for ref, label, v, nets in circuit.POTS}["RV3"]
    return dict(r_in=ohms(p["R112"].value), r_ref=ohms(p["R114"].value), c_int=100e-12,
                r_ser=ohms(p["R116"].value), r_resp=ohms(resp[1:]), r_bias=ohms(p["R118"].value), vclamp=vclamp)


def servo_step(c0, c1, t_end=2e-3, dt=2e-9, gbw=3e6, c_par=10e-12):
    """The loop with RESPONSE at LIN (the pot from Vc_lin to Vc_exp, whose op-amp output follows C
    instantly), settled at C = c0, then stepped to c1. Returns [(t, servo gain)] every 2 us."""
    q = servo_params()
    wt = 2 * math.pi * gbw
    i_ref = 5.0 / q["r_ref"]

    def vcl_of(do, c):
        vce = max(0.5 * (5 - c), 0.0)
        g_sum = 1 / q["r_ser"] + 1 / VC_PORT + 1 / q["r_resp"]
        vcl = (do / q["r_ser"] + vce / q["r_resp"]) / g_sum
        return min(vcl, q["vclamp"] + 0.62)      # the BC557 holds it there

    def deriv(sl, do, c):
        gain = math.exp(-max(vcl_of(do, c), -1.0) / VC_NEPER)
        i = c / q["r_in"] - gain * i_ref - 5.0 / q["r_bias"]    # C / 100k from the wipers, the bias
        d_do = wt * (0.0 - sl)
        if (do >= VSAT and d_do > 0) or (do <= -VSAT and d_do < 0):
            d_do = 0.0
        d_sl = (i + q["c_int"] * d_do) / (q["c_int"] + c_par)
        return d_sl, d_do

    # settle at c0: the integrator's output where the servo gain is c0 / 5 (or the rail when closed)
    if lin_gain(c0) > 0:
        target = -VC_NEPER * math.log(lin_gain(c0))
        vce = max(0.5 * (5 - c0), 0.0)
        g_sum = 1 / q["r_ser"] + 1 / VC_PORT + 1 / q["r_resp"]
        do = (target * g_sum - vce / q["r_resp"]) * q["r_ser"]
    else:
        do = VSAT
    sl, t, out = 0.0, 0.0, []
    n = int(t_end / dt)
    every = max(1, int(2e-6 / dt))
    for s in range(n):
        k1 = deriv(sl, do, c1)
        k2 = deriv(sl + dt / 2 * k1[0], do + dt / 2 * k1[1], c1)
        k3 = deriv(sl + dt / 2 * k2[0], do + dt / 2 * k2[1], c1)
        k4 = deriv(sl + dt * k3[0], do + dt * k3[1], c1)
        sl += dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
        do = max(-VSAT, min(VSAT, do + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])))
        t += dt
        if s % every == 0:
            out.append((t, math.exp(-max(vcl_of(do, c1), -1.0) / VC_NEPER)))
    return out


def settle(trace, target_gain, db=1.0):
    """Time after which the gain stays within db of the target, and how far it overshoots the target
    in the step's direction, in dB."""
    lim = 10 ** (db / 20)
    last_out = 0.0
    for t, g in trace:
        if not (target_gain / lim <= g <= target_gain * lim):
            last_out = t
    up = trace[0][1] < target_gain
    over = max(20 * math.log10(g / target_gain) * (1 if up else -1) for _, g in trace)
    return last_out, over


def servo_checks():
    bad, rows = [], []
    z = c_offset()
    # (name, C before, C after, the most time it may take to stay within 1 dB): the loop's bandwidth
    # falls with the gain (the datasheet's circuit does the same), so the -60 dB end may take longer
    for name, c0, c1, t_max in (("closed -> unity (an attack from silence)", 0.0, 5.0, 100e-6),
                                ("unity -> -40 dB (a fast decay)", 5.0, z + 0.05, 500e-6),
                                ("-40 dB -> unity", z + 0.05, 5.0, 100e-6),
                                ("-20 dB -> -60 dB", z + 0.5, z + 0.005, 5e-3)):
        tr = servo_step(c0, c1, t_end=max(2e-3, 1.5 * t_max))
        t_set, over = settle(tr, lin_gain(c1))
        rows.append((name, t_set, over))
        if t_set > t_max:
            bad.append(f"servo {name}: not within 1 dB after {t_set * 1e3:.2f} ms")
        if over > 1.0:
            bad.append(f"servo {name}: {over:.1f} dB overshoot")
    return bad, rows


if __name__ == "__main__":
    bad, table, closed, leds, fan = dc_checks()
    print("gain (dB) over C, channel 1:")
    print("  C (V)  " + "".join(f"{c:>8}" for c in (0.5, 1, 2, 2.5, 3, 4, 5, 7.5, 10)))
    for name in LAW:
        print(f"  {name:6} " + "".join(f"{table[(c, name)]:8.1f}" for c in (0.5, 1, 2, 2.5, 3, 4, 5, 7.5, 10)))
    for (c, name), (db, vcl, vce) in closed.items():
        print(f"  C = {c:+.0f} V, {name:4}: {db:7.1f} dB  (Vc_lin {vcl:+.2f} V, Vc_exp {vce:+.2f} V)")
    print("LED 1:")
    for name, (ma, db, vc) in leds.items():
        print(f"  {name:12} {ma:5.2f} mA  (gain {db:7.1f} dB, Vc {vc:+.2f} V)")
    print(f"a 1k source into IN 1, normalled on to all four inputs, reads {fan:.3f} of itself")
    sbad, rows = servo_checks()
    print("servo steps (RESPONSE at LIN):")
    for name, t_set, over in rows:
        print(f"  {name:42} within 1 dB after {t_set * 1e6:6.1f} us, overshoot {over:+.2f} dB")
    for b in bad + sbad:
        print("  FAIL:", b)
    print(f"{len(bad)} DC failures, {len(sbad)} servo failures")
