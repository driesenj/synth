"""Offset: three offset attenuverters in 10HP Eurorack, all analog, on one
PCB: Thonk panel parts on its front, everything else behind them.

Per channel k (1-3): OUT k = ATTEN k x IN k + OFFSET k (+ OUT k-1 when that
jack is unpatched).
  IN k      CV / audio in, 100k; unpatched it takes IN k-1, and IN 1 takes
            +1 V, so with nothing patched ATTEN is a fine +-1 V offset
  ATTEN k   B10k, -1 (CCW) .. 0 (noon) .. +1 (CW)
  OFFSET k  B10k, -5 V .. +5 V from two LM4040-5.0 references
  RANGE k   SPDT toggle: lever up = OFFSET -10 V .. +10 V
  OUT k     1k series; unpatched it adds into channel k+1 (OUT 3 = the sum)
  LED k     2-lead bicolour: green positive, red negative

One TL074 per channel, every signal stage inverting (no op-amp input moves
with the signal, so a -10 V input stays inside the TL07x's common-mode range):
  A  inverter               N_k = -IN_k         100k / 100k
  B  inverter               P_k = +IN_k         100k / 100k
     ATTEN between P_k (CCW, pin 1) and N_k (CW, pin 3), wiper -> 100k -> SUM_k
     OFFSET between REF_P (CCW) and REF_N (CW), wiper -> 100k -> SUM_k, and
     through RANGE k (common 2, lever up joins 2-3) -> a second 100k -> SUM_k:
     50k into the summer doubles the offset. The toggle carries the wiper,
     never the summing node.
  C  inverting summer       OA_k = -(SUM inputs), 100k || 22p
                            OA_k -> 1k -> OUT k;  OA_k -> 2k2 -> LED k -> GND
  D  cascade inverter       OUT k's switch lug -> 100k -> CAS_k+1 = -OUT_k
                            -> 100k -> SUM_k+1 (open lug: 0 V)
U3's D section has no channel after it and buffers NORM, the +1 V normal
(39k / 10k from REF_P, 1.02 V).

References: REF_P = +5 V (LM4040 cathode, 1k from +12 V), REF_N = -5 V
(LM4040 anode, cathode on GND, 1k to -12 V); 7 mA each, 3 mA of it through
the three OFFSET pots. Power: 16-pin Eurorack header, a 1N5819 in each rail
(+12 V: anode on the header; -12 V: cathode on the header), 10R + 10u per
rail, a 100n pair at each TL074.

`python circuit.py` prints the part counts, the netlist problems (single-pin
nets, designators used twice) and a DC check: an ideal-op-amp solve of this
netlist for patch cases with known answers, which catches sign and wiring
errors end to end.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  LED     3 mm, the lens centre between its two pads
  toggle  Dailywell 2MS1 sub-mini, the bushing centre (the middle pin); pins
          in a column, pin 3 at the bottom, so lever up joins 2-3
"""
import collections


class Part:
    def __init__(self, ref, kind, value="", nets=None, label=""):
        self.ref, self.kind, self.value, self.nets, self.label = ref, kind, value, dict(nets or {}), label

    def __repr__(self):
        return f"Part({self.ref} {self.kind} {self.value} {self.nets})"


def R(ref, value, a, b, label=""):
    return Part(ref, "R", value, {"1": a, "2": b}, label)


def C(ref, value, a, b, label=""):
    return Part(ref, "C", value, {"1": a, "2": b}, label)


CHANNELS = 3
CH = range(1, CHANNELS + 1)
GND, VP, VN = "GND", "+12V", "-12V"

# TL074 section pins: (out, in-, in+); A and B on the pin 1-7 side, C and D on the pin 8-14 side
SECTION = {"A": ("1", "2", "3"), "B": ("7", "6", "5"), "C": ("8", "9", "10"), "D": ("14", "13", "12")}

# ---------------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net (None = open). The lug touches the tip while nothing is patched.
JACKS = [(f"J{k}", f"IN {k}", f"IN{k}", "NORM" if k == 1 else f"IN{k - 1}") for k in CH]
JACKS += [(f"J{CHANNELS + k}", f"OUT {k}", f"OUT{k}", f"OSW{k}" if k < CHANNELS else None) for k in CH]
# ref, label, value, (CW end, wiper, CCW end). Pins 3 / 1 are the CW / CCW ends: fully CW puts the wiper on
# pin 3. Both pots' CW ends are the negative side, because the summer inverts.
POTS = []
for k in CH:
    POTS += [(f"RV{2 * k - 1}", f"ATTEN {k}", "B10k", (f"N{k}", f"AW{k}", f"P{k}")),
             (f"RV{2 * k}", f"OFFSET {k}", "B10k", ("REF_N", f"OW{k}", "REF_P"))]
# 2-lead bicolour LED: current from pin 1 to pin 2 lights green, from 2 to 1 red
LEDS = [(f"D{k}", f"OUT {k}", f"LED{k}") for k in CH]
# ref, label, (pin 1, common, pin 3): SPDT ON-ON sub-mini toggle, lever up joins 2-3 = +-10 V; pin 1 is open
TOGGLES = [(f"SW{k}", f"RANGE {k}", (None, f"OW{k}", f"OR{k}")) for k in CH]


def panel_parts():
    parts = []
    for ref, label, tip, lug in JACKS:
        nets = {"1": GND, "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, value, (cw, w, ccw) in POTS:
        parts.append(Part(ref, "POT", value, {"3": cw, "2": w, "1": ccw, "4": GND, "5": GND}, label))
    for ref, label, net in LEDS:
        parts.append(Part(ref, "LED_BI", "red/green", {"1": net, "2": GND}, label))
    for ref, label, pins in TOGGLES:
        parts.append(Part(ref, "TOGGLE", "SPDT ON-ON", {str(i + 1): n for i, n in enumerate(pins) if n}, label))
    return parts


# ------------------------------------------------------------------ channels
def channel_parts(k):
    r = 100 * k
    parts = [
        R(f"R{r + 1}", "100k", f"IN{k}", f"NA{k}", "A in"),
        R(f"R{r + 2}", "100k", f"NA{k}", f"N{k}", "A feedback"),
        R(f"R{r + 3}", "100k", f"N{k}", f"NB{k}", "B in"),
        R(f"R{r + 4}", "100k", f"NB{k}", f"P{k}", "B feedback"),
        R(f"R{r + 5}", "100k", f"AW{k}", f"SUM{k}", "ATTEN into the summer"),
        R(f"R{r + 6}", "100k", f"OW{k}", f"SUM{k}", "OFFSET into the summer"),
        R(f"R{r + 13}", "100k", f"OR{k}", f"SUM{k}", "OFFSET, +-10 V: beside R{r + 6} when RANGE is up"),
        R(f"R{r + 7}", "100k", f"SUM{k}", f"OA{k}", "summer feedback"),
        C(f"C{r + 1}", "22p", f"SUM{k}", f"OA{k}", "summer feedback"),
        R(f"R{r + 8}", "1k", f"OA{k}", f"OUT{k}", "output series"),
        R(f"R{r + 9}", "2k2", f"OA{k}", f"LED{k}", "LED, about 3.6 mA at 10 V"),
    ]
    if k > 1:
        parts.append(R(f"R{r + 10}", "100k", f"CAS{k}", f"SUM{k}", f"OUT {k - 1} into the summer"))
    if k < CHANNELS:
        parts += [R(f"R{r + 11}", "100k", f"OSW{k}", f"ND{k}", "cascade in"),
                  R(f"R{r + 12}", "100k", f"ND{k}", f"CAS{k + 1}", "cascade feedback")]
    nets = {"4": VP, "11": VN}
    for sec, (out, inm, inp) in (("A", (f"N{k}", f"NA{k}", GND)), ("B", (f"P{k}", f"NB{k}", GND)),
                                 ("C", (f"OA{k}", f"SUM{k}", GND))):
        nets.update(dict(zip(SECTION[sec], (out, inm, inp))))
    if k < CHANNELS:
        nets.update(dict(zip(SECTION["D"], (f"CAS{k + 1}", f"ND{k}", GND))))
    else:
        nets.update(dict(zip(SECTION["D"], ("NORM", "NORM", "NDIV"))))    # follower for the +1 V normal
    parts.append(Part(f"U{k}", "TL074", "TL074", nets, f"channel {k}"))
    return parts


def reference_parts():
    return [
        Part("D4", "LM4040", "LM4040-5.0", {"1": "REF_P", "2": GND}, "+5 V reference"),     # 1 = cathode, 2 = anode
        Part("D5", "LM4040", "LM4040-5.0", {"1": GND, "2": "REF_N"}, "-5 V reference"),
        R("R901", "1k", VP, "REF_P", "+5 V reference feed, 7 mA"),
        R("R902", "1k", "REF_N", VN, "-5 V reference feed, 7 mA"),
        C("C901", "100n", "REF_P", GND, "+5 V reference"),
        C("C902", "100n", GND, "REF_N", "-5 V reference"),
        R("R903", "39k", "REF_P", "NDIV", "+1 V normal divider"),
        R("R904", "10k", "NDIV", GND, "+1 V normal divider"),
    ]


def power_parts():
    hdr = {"1": "N12_IN", "2": "N12_IN", "11": "P12_IN", "12": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 11)})
    parts = [
        Part("J7", "HDR16", "16-pin Eurorack", hdr, "POWER"),
        Part("D6", "D5819", "1N5819", {"2": "P12_IN", "1": "P12_D"}, "+12 V reverse protection"),   # 1 = cathode
        Part("D7", "D5819", "1N5819", {"1": "N12_IN", "2": "N12_D"}, "-12 V reverse protection"),
        R("R905", "10R", "P12_D", VP, "+12 V filter"),
        R("R906", "10R", "N12_D", VN, "-12 V filter"),
        Part("C903", "CP", "10u", {"2": VP, "1": GND}, "+12 V bulk"),
        Part("C904", "CP", "10u", {"2": GND, "1": VN}, "-12 V bulk"),
    ]
    for k in CH:                                        # one pair per TL074, beside its supply pins
        parts.append(C(f"C{903 + 2 * k}", "100n", VP, GND, f"U{k} +12 V"))
        parts.append(C(f"C{904 + 2 * k}", "100n", GND, VN, f"U{k} -12 V"))
    return parts


def all_parts():
    parts = panel_parts() + reference_parts() + power_parts()
    for k in CH:
        parts += channel_parts(k)
    return parts


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets, designators used twice, TL074s with a pin left out."""
    parts = all_parts()
    nets = nets_of(parts)
    bad = [f"single-pin net {n} {nets[n]}" for n in sorted(nets) if len(nets[n]) < 2]
    refs = collections.Counter(p.ref for p in parts)
    bad += [f"{r} used {c} times" for r, c in refs.items() if c > 1]
    for p in parts:
        if p.kind == "TL074" and set(p.nets) != {str(i) for i in range(1, 15)}:
            bad.append(f"{p.ref}: pins {sorted(set(map(str, range(1, 15))) - set(p.nets), key=int)} unconnected")
    return bad


# ------------------------------------------------------------------ DC check
def _ohms(v):
    """'100k' -> 1e5, '2k2' -> 2200, '10R' -> 10."""
    for unit, mul in (("k", 1e3), ("R", 1.0), ("M", 1e6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


def solve(atten, offset, inputs=None, patched_outs=(), source_r=0.0, ten_volt=()):
    """DC node voltages of the netlist with ideal op-amps and ideal references.
    atten, offset: pot positions per channel, 0 = fully CCW .. 1 = fully CW. inputs: {k: volts} for the
    patched IN jacks, driven through source_r. patched_outs: OUT jacks with a cable (100k load); an
    unpatched jack's lug touches its tip. ten_volt: channels whose RANGE lever is up (pins 2-3 joined).
    LEDs and capacitors are left out (the op-amps are ideal)."""
    inputs = inputs or {}
    fixed = {GND: 0.0, VP: 12.0, VN: -12.0, "REF_P": 5.0, "REF_N": -5.0}
    res, amps = [], []                       # (a, b, ohms); (out, in-, in+)
    for p in all_parts():
        if p.kind == "R":
            res.append((p.nets["1"], p.nets["2"], _ohms(p.value)))
        elif p.kind == "POT":
            k = int(p.label.split()[-1])
            t = (atten if p.label.startswith("ATTEN") else offset)[k - 1]
            rt = _ohms(p.value[1:])
            res.append((p.nets["1"], p.nets["2"], max(t, 1e-9) * rt))
            res.append((p.nets["2"], p.nets["3"], max(1 - t, 1e-9) * rt))
        elif p.kind == "JACK":
            k = int(p.label.split()[-1])
            tip, lug = p.nets["3"], p.nets.get("2")
            patched = (k in inputs) if p.label.startswith("IN") else (k in patched_outs)
            if not patched and lug:
                res.append((tip, lug, 1e-3))
            elif patched and p.label.startswith("IN"):
                src = f"SRC{k}"
                fixed[src] = inputs[k]
                res.append((src, tip, max(source_r, 1e-3)))
            elif patched:
                res.append((tip, GND, 100e3))
        elif p.kind == "TOGGLE":
            if int(p.label.split()[-1]) in ten_volt:
                res.append((p.nets["2"], p.nets["3"], 1e-3))
        elif p.kind == "TL074":
            for out, inm, inp in SECTION.values():
                amps.append((p.nets[out], p.nets[inm], p.nets[inp]))
    for p in all_parts():                    # a toggle's open throw leaves its resistor dangling: tie it down
        if p.kind == "TOGGLE" and int(p.label.split()[-1]) not in ten_volt:
            res.append((p.nets["3"], GND, 1e12))
    nodes = sorted({n for a, b, _ in res for n in (a, b)} | {n for amp in amps for n in amp} - set(fixed))
    nodes = [n for n in nodes if n not in fixed]
    idx = {n: i for i, n in enumerate(nodes)}
    size = len(nodes)
    m = [[0.0] * (size + 1) for _ in range(size)]
    outs = {out for out, _, _ in amps}
    for a, b, ohm in res:                    # KCL rows, except at op-amp outputs
        g = 1.0 / ohm
        for x, y in ((a, b), (b, a)):
            if x in idx and x not in outs:
                m[idx[x]][idx[x]] += g
                if y in idx:
                    m[idx[x]][idx[y]] -= g
                else:
                    m[idx[x]][size] += g * fixed[y]
    for out, inm, inp in amps:               # the output's row: V(in+) - V(in-) = 0
        row = m[idx[out]]
        for n, s in ((inp, 1.0), (inm, -1.0)):
            if n in idx:
                row[idx[n]] += s
            else:
                row[size] -= s * fixed[n]
    for c in range(size):                    # Gaussian elimination, partial pivoting
        piv = max(range(c, size), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(size):
            if r != c and m[r][c]:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    v = dict(fixed)
    v.update({n: m[i][size] / m[i][i] for i, n in enumerate(nodes)})
    return v


NOON = [0.5] * CHANNELS
NORM_V = 5.0 * 10 / 49                   # the 39k / 10k divider
HOP = 100 / 101                          # a cascade reads OUT k's tip: OA_k through 1k into D's 100k


def dc_check():
    """Patch cases with known answers, read at the op-amp outputs OA_k (a patched jack's tip carries
    OA_k x 100/101 into the 100k load the solve puts on it). Returns the failures and the fraction of a
    1k-impedance source that reaches IN 1 when it feeds all three inputs."""
    all_out = tuple(CH)
    # a B10k wiper at 3/4 is 1.875k (0.75 x 0.25 x 10k) behind its open-circuit voltage
    cases = [   # name, expected {net: volts}, solve arguments
        ("all at noon, nothing patched", {f"OA{k}": 0.0 for k in CH}, (NOON, NOON)),
        ("ATTEN 1 CW, nothing patched: +1 V normal", {"OA1": NORM_V}, ([1, .5, .5], NOON, None, (1,))),
        ("ATTEN 1 CCW, nothing patched", {"OA1": -NORM_V}, ([0, .5, .5], NOON, None, (1,))),
        ("OFFSET CW / CCW, 5 V range", {"OA1": 5.0, "OA2": -5.0}, (NOON, [1, 0, .5], None, all_out)),
        ("OFFSET CW / CCW, 10 V range", {"OA1": 10.0, "OA2": -10.0},
         (NOON, [1, 0, .5], None, all_out, 0.0, (1, 2))),
        ("OFFSET 3/4, 10 V range", {"OA3": 2.5 * 100 / (50 + 1.875)},
         (NOON, [.5, .5, .75], None, all_out, 0.0, (3,))),
        ("3 V into IN 1, fanned out: ATTEN CW, CCW, 3/4",
         {"OA1": 3.0, "OA2": -3.0, "OA3": 1.5 * 100 / (100 + 1.875)}, ([1, 0, .75], NOON, {1: 3.0}, all_out)),
        ("IN 2 patched breaks the chain", {"OA1": 0.0, "OA2": -1.0, "OA3": -1.0},
         ([.5, 1, 1], NOON, {1: 2.0, 2: -1.0}, all_out)),
        ("OUT 1 unpatched adds into OUT 2", {"OA2": 2.0 * HOP + 5.0},
         ([1, .5, .5], [.5, 1, .5], {1: 2.0}, (2, 3))),
        ("OUT 1-2 unpatched: OUT 3 is the sum", {"OA3": (1.0 * HOP + 5.0) * HOP - 5.0},
         ([1, .5, .5], [.5, 1, 0], {1: 1.0}, (3,))),
    ]
    bad = []
    for name, want, args in cases:
        v = solve(*args)
        for net, x in want.items():
            if abs(v[net] - x) > 1e-6:
                bad.append(f"{name}: {net} = {v[net]:+.4f} V, expected {x:+.4f} V")
    # loading: one source with a 1k output impedance into IN 1, fanned out to all three inputs
    v = solve([1] * CHANNELS, NOON, {1: 1.0}, all_out, source_r=1e3)
    return bad, v["IN1"]


# ---------------------------------------------------------------- panel grid (panel frame, y down)
HP = 10
PANEL_W, PANEL_H = 50.5, 128.5          # HP x 5.08 - 0.3, as the S&H
BOARD_W, BOARD_H = 49.3, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins

# Channels are columns like the mixer's strips, 14.3 mm apart (the mixer: 13.5); the left margin
# holds the row words. Knobs at the top, the RANGE toggles under OFFSET, jacks at the bottom so
# cables hang away from the hands.
CH_X = [12.0 + 14.3 * i for i in range(CHANNELS)]
ROW = {"atten": 27.0, "offset": 48.5, "range": 64.5, "in": 79.0, "led": 92.5, "out": 104.0}


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for k, x in enumerate(CH_X, start=1):
    for ref, row in ((f"RV{2 * k - 1}", "atten"), (f"RV{2 * k}", "offset")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - POT_SHAFT, 2), 0)          # pins down
    for ref, row in ((f"J{k}", "in"), (f"J{CHANNELS + k}", "out")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)        # sleeve up
    PLACEMENT[f"D{k}"] = (*board_xy(x, ROW["led"]), 0)
    PLACEMENT[f"SW{k}"] = (*board_xy(x, ROW["range"]), 0)          # pin 3 at the bottom


if __name__ == "__main__":
    parts = all_parts()
    print(f"{len(parts)} parts, {len(nets_of(parts))} nets")
    kinds = collections.Counter((p.kind, p.value) for p in parts)
    print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    problems = check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} netlist problems")
    dc, in1 = dc_check()
    for b in dc:
        print("  " + b)
    print(f"{len(dc)} DC check failures; a 1k source into IN 1, fanned out to all three inputs, reads {in1:.3f} of itself")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
