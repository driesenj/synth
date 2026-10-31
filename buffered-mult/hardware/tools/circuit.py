"""Six: a buffered mult, two groups of 1 -> 3, in 4HP Eurorack, all analog,
all through-hole, built the Marblesy way: two stacked PCBs behind the
panel, Thonk panel parts. The whole circuit as one netlist, split over the
two boards.

Faceplate board (FB): 8 Thonkiconn jacks and 2 bicolour LEDs in one
column, two 1x6 male headers in the strips beside the jack bodies.
Main board (MB): 2 TL074, the resistors standing up, the Eurorack power
entry, the two female sockets. In 4HP the jack bodies take the middle 9 mm
of an 18.8 mm board, which leaves no room for a DIP TL074 beside them; that
is why this is two boards and not one.

Per group g (1, 2), one TL074 each:
  IN g      100k into an inverter (A): N_g = -IN_g, 100k || 10p.
            IN 1's switch lug is on GND (unpatched: 0 V), IN 2's on IN 1's
            tip, so with IN 2 unpatched all six outputs carry IN 1.
  OUT g x   x = a, b, c on sections B, C, D: an inverter from N_g, 100k in,
            with the 1k output resistor inside the loop: OA -> 1k -> the
            jack tip, 100k from the tip back to in-, 10p from OA to in-.
            The tip is exactly +IN_g whatever the load (until the op-amp
            runs out of swing), and each output has its own op-amp, so a
            shorted or overloaded output does not move the others.
  LED g     2-lead bicolour from N_g through 2k2: green while IN g is
            positive, red while negative.
Every signal stage is inverting, as on Offset: no op-amp input moves with
the signal, so a -10 V input stays inside the TL07x's common-mode range
(a follower would flip its output there). The price is that the gain is
set by resistor ratios: the 16 100k in the signal path are 0.1 %.

Power: 16-pin Eurorack header, a 1N5819 in each rail (+12 V: anode on the
header; -12 V: cathode on the header), 10R + 10u per rail, a 100n pair at
each TL074.

Net naming: nets that cross the board-to-board headers carry the same name
on both boards, with _F on the faceplate side (GND -> GND_F).

`python circuit.py` prints the part counts, the netlist problems
(single-pin nets, designators used twice, TL074 pins left out, header pins
unused on one side), a DC check (an ideal-op-amp solve of this netlist for
patch cases with known answers) and the worst-case gain error from the
resistor tolerance.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the faceplate board's bottom-left corner):
footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  LED     3 mm, the lens centre between its two pads
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


GROUPS = (1, 2)
OUTS = ("A", "B", "C")
GND, VP, VN = "GND", "+12V", "-12V"
PRECISE = "100k 0.1%"                    # the gain-setting resistors

# TL074 section pins: (out, in-, in+); A and B on the pin 1-7 side, C and D on the pin 8-14 side
SECTION = {"A": ("1", "2", "3"), "B": ("7", "6", "5"), "C": ("8", "9", "10"), "D": ("14", "13", "12")}
OUT_SECTION = dict(zip(OUTS, ("B", "C", "D")))


# ------------------------------------------------------------- main board
def group_main(g):
    """Input inverter, three output inverters with the 1k inside the loop, the LED resistor."""
    r = 100 * g
    parts = [
        R(f"R{r + 1}", PRECISE, f"IN{g}", f"NA{g}", "input"),
        R(f"R{r + 2}", PRECISE, f"NA{g}", f"N{g}", "input feedback"),
        C(f"C{r + 1}", "10p", f"NA{g}", f"N{g}", "input feedback"),
        R(f"R{r + 3}", "2k2", f"N{g}", f"LED{g}", "LED, about 3.6 mA at 10 V"),
    ]
    nets = {"4": VP, "11": VN}
    nets.update(dict(zip(SECTION["A"], (f"N{g}", f"NA{g}", GND))))
    for i, x in enumerate(OUTS, start=1):
        o, s, oa = f"OUT{g}{x}", f"S{g}{x}", f"OA{g}{x}"
        parts += [
            R(f"R{r + 10 * i + 1}", PRECISE, f"N{g}", s, f"out {g}{x.lower()} input"),
            R(f"R{r + 10 * i + 2}", PRECISE, o, s, f"out {g}{x.lower()} feedback, from the jack side of the 1k"),
            R(f"R{r + 10 * i + 3}", "1k", oa, o, f"out {g}{x.lower()} series, inside the loop"),
            C(f"C{r + 10 * i + 1}", "10p", oa, s, f"out {g}{x.lower()}: the loop closes here above ~160 kHz"),
        ]
        nets.update(dict(zip(SECTION[OUT_SECTION[x]], (oa, s, GND))))
    parts.append(Part(f"U{g}", "TL074", "TL074", nets, f"group {g}"))
    return parts


def power_main():
    hdr = {"1": "N12_IN", "2": "N12_IN", "11": "P12_IN", "12": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 11)})
    parts = [
        Part("J9", "HDR16", "16-pin Eurorack", hdr, "POWER"),
        Part("D3", "D5819", "1N5819", {"2": "P12_IN", "1": "P12_D"}, "+12 V reverse protection"),   # 1 = cathode
        Part("D4", "D5819", "1N5819", {"1": "N12_IN", "2": "N12_D"}, "-12 V reverse protection"),
        R("R901", "10R", "P12_D", VP, "+12 V filter"),
        R("R902", "10R", "N12_D", VN, "-12 V filter"),
        Part("C901", "CP", "10u", {"2": VP, "1": GND}, "+12 V bulk"),
        Part("C902", "CP", "10u", {"2": GND, "1": VN}, "-12 V bulk"),
    ]
    for g in GROUPS:                                    # one pair per TL074, beside its supply pins
        parts.append(C(f"C{901 + 2 * g}", "100n", VP, GND, f"U{g} +12 V"))
        parts.append(C(f"C{902 + 2 * g}", "100n", GND, VN, f"U{g} -12 V"))
    return parts


def main_board_parts():
    parts = power_main()
    for g in GROUPS:
        parts += group_main(g)
    for ref, kind, nets in HEADERS:                     # female sockets on this board
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ board-to-board pins
def _pair(net):
    return net, {"GND": "GND_F"}.get(net, net + "_F")


# One 1x6 per group, in the strips beside the jack bodies (see HEADERS_FRONT). Pin 1 at the top, the
# order following the jacks down the column; the order gets tuned for crossings when the boards are placed.
HEADERS = [(f"H{g}", "HDR6", [_pair(n) for n in (f"IN{g}", GND, f"LED{g}", f"OUT{g}A", f"OUT{g}B", f"OUT{g}C")])
           for g in GROUPS]


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ---------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net (None = open). The lug touches the tip while nothing is patched.
JACKS = [("J1", "IN 1", "IN1_F", "GND_F"), ("J2", "OUT 1a", "OUT1A_F", None), ("J3", "OUT 1b", "OUT1B_F", None),
         ("J4", "OUT 1c", "OUT1C_F", None),
         ("J5", "IN 2", "IN2_F", "IN1_F"), ("J6", "OUT 2a", "OUT2A_F", None), ("J7", "OUT 2b", "OUT2B_F", None),
         ("J8", "OUT 2c", "OUT2C_F", None)]
# 2-lead bicolour LED: current from pin 1 to pin 2 lights green, from 2 to 1 red. It hangs on N_g = -IN_g,
# so pin 1 goes to GND: a positive input pulls current from GND through pin 1 to pin 2 = green.
LEDS = [("D1", "group 1", "LED1_F"), ("D2", "group 2", "LED2_F")]


def faceplate_parts():
    parts = []
    for ref, label, tip, lug in JACKS:
        nets = {"1": "GND_F", "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, net in LEDS:
        parts.append(Part(ref, "LED_BI", "red/green", {"1": "GND_F", "2": net}, label))
    for ref, kind, nets in HEADERS:                     # male pins on this board
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets on either board, designators used twice, TL074s with a pin left
    out, header pins whose net is used on one board only."""
    bad = []
    boards = {"main board": main_board_parts(), "faceplate": faceplate_parts()}
    for name, parts in boards.items():
        nets = nets_of(parts)
        bad += [f"{name}: single-pin net {n} {nets[n]}" for n in sorted(nets) if len(nets[n]) < 2]
    refs = collections.Counter(p.ref for p in all_parts())
    bad += [f"{r} used {c} times" for r, c in refs.items() if c > 1]
    for p in all_parts():
        if p.kind == "TL074" and set(p.nets) != {str(i) for i in range(1, 15)}:
            bad.append(f"{p.ref}: pins {sorted(set(map(str, range(1, 15))) - set(p.nets), key=int)} unconnected")
    mb, fb = nets_of(boards["main board"]), nets_of(boards["faceplate"])
    for ref, kind, pins in HEADERS:
        for a, b in pins:
            if len(mb[a]) < 2 or len(fb[b]) < 2:
                bad.append(f"{ref}: header net not used on both boards: {a} / {b}")
    return bad


# ------------------------------------------------------------------ DC check
def _ohms(v):
    """'100k 0.1%' -> 1e5, '2k2' -> 2200, '10R' -> 10."""
    v = v.split()[0]
    for unit, mul in (("k", 1e3), ("R", 1.0), ("M", 1e6)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


def solve(inputs=None, loads=None, source_r=0.0, tol=None):
    """DC node voltages of the netlist with ideal op-amps, both boards joined at the headers.
    inputs: {group: volts} for the patched IN jacks, driven through source_r. loads: {OUT net (e.g.
    "OUT1A"): ohms to GND} for the patched outputs. tol: {ref: factor} scales single resistors.
    LEDs and capacitors are left out (the op-amps are ideal and drive them from their outputs)."""
    inputs, loads, tol = inputs or {}, loads or {}, tol or {}
    fixed = {GND: 0.0, VP: 12.0, VN: -12.0}
    join = {fb: mb for _, _, pins in HEADERS for mb, fb in pins}     # faceplate net -> main board net
    res, amps = [], []                                              # (a, b, ohms); (out, in-, in+)
    for p in all_parts():
        n = {k: join.get(v, v) for k, v in p.nets.items()}
        if p.kind == "R":
            res.append((n["1"], n["2"], _ohms(p.value) * tol.get(p.ref, 1.0)))
        elif p.kind == "JACK":
            tip, lug = n["3"], n.get("2")
            g = int(p.label.split()[1][0])
            if p.label.startswith("IN") and g in inputs:
                fixed[f"SRC{g}"] = inputs[g]
                res.append((f"SRC{g}", tip, max(source_r, 1e-3)))
            elif p.label.startswith("IN") and lug:
                res.append((tip, lug, 1e-3))
            elif tip.replace("_F", "") in loads:
                res.append((tip, GND, loads[tip.replace("_F", "")]))
        elif p.kind == "TL074":
            for out, inm, inp in SECTION.values():
                amps.append((n[out], n[inm], n[inp]))
    nodes = sorted(({a for a, b, _ in res} | {b for a, b, _ in res} | {x for amp in amps for x in amp}) - set(fixed))
    idx = {x: i for i, x in enumerate(nodes)}
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
        for x, s in ((inp, 1.0), (inm, -1.0)):
            if x in idx:
                row[idx[x]] += s
            else:
                row[size] -= s * fixed[x]
    for c in range(size):                    # Gaussian elimination, partial pivoting
        piv = max(range(c, size), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(size):
            if r != c and m[r][c]:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    v = dict(fixed)
    v.update({x: m[i][size] / m[i][i] for i, x in enumerate(nodes)})
    return v


ALL_OUT = [f"OUT{g}{x}" for g in GROUPS for x in OUTS]


def dc_check():
    """Patch cases with known answers, read at the jack tips. Returns the failures."""
    cases = [   # name, expected {net: volts}, solve arguments
        ("nothing patched", {o: 0.0 for o in ALL_OUT}, {}),
        ("+5 V into IN 1: all six outputs (IN 2 normalled)", {o: 5.0 for o in ALL_OUT}, {"inputs": {1: 5.0}}),
        ("-10 V into IN 1", {o: -10.0 for o in ALL_OUT}, {"inputs": {1: -10.0}}),
        ("IN 1 +3 V, IN 2 -2 V: the groups apart", {**{f"OUT1{x}": 3.0 for x in OUTS},
                                                    **{f"OUT2{x}": -2.0 for x in OUTS}},
         {"inputs": {1: 3.0, 2: -2.0}}),
        ("only IN 2 patched: group 1 at 0 V", {**{f"OUT1{x}": 0.0 for x in OUTS}, **{f"OUT2{x}": 4.0 for x in OUTS}},
         {"inputs": {2: 4.0}}),
        ("loaded outputs keep their level (1k inside the loop)", {o: 2.0 for o in ALL_OUT},
         {"inputs": {1: 2.0}, "loads": {"OUT1A": 100e3, "OUT1B": 10e3, "OUT2C": 1e3}}),
        ("a shorted output leaves the others alone", {o: 6.0 for o in ALL_OUT if o != "OUT1B"},
         {"inputs": {1: 6.0}, "loads": {"OUT1B": 1e-3, "OUT1A": 100e3}}),
    ]
    bad = []
    for name, want, kw in cases:
        v = solve(**kw)
        for net, x in want.items():
            if abs(v[net] - x) > 1e-6:
                bad.append(f"{name}: {net} = {v[net]:+.4f} V, expected {x:+.4f} V")
    return bad


def loading():
    """What a source with a 1k output impedance delivers into IN 1: alone, and normalled into IN 2 too."""
    one = solve({1: 1.0, 2: 0.0}, source_r=1e3)["OUT1A"]
    both = solve({1: 1.0}, source_r=1e3)["OUT1A"]
    return one, both


def worst_gain(tol):
    """Worst-case output / input with every 0.1 % resistor of one path at the tolerance edge that hurts:
    (lowest, highest) over the six outputs. Each path has four: R_in and R_f of both stages."""
    lo, hi = 1.0, 1.0
    for g in GROUPS:
        r = 100 * g
        for i, x in enumerate(OUTS, start=1):
            path = {"in": [f"R{r + 1}", f"R{r + 10 * i + 1}"], "fb": [f"R{r + 2}", f"R{r + 10 * i + 2}"]}
            for sign in (1, -1):
                t = {ref: 1 - sign * tol for ref in path["in"]}
                t.update({ref: 1 + sign * tol for ref in path["fb"]})
                gain = solve({g: 1.0, 3 - g: 0.0}, tol=t)[f"OUT{g}{x}"]
                lo, hi = min(lo, gain), max(hi, gain)
    return lo, hi


# ---------------------------------------------------------------- panel grid (panel frame, y down)
HP = 4
PANEL_W, PANEL_H = 20.0, 128.5          # HP x 5.08 - 0.3 = 20.02, Doepfer rounds 4HP to 20.0
BOARD_W, BOARD_H = 18.8, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin

# One column, 1 mm right of centre so the left margin holds the row words on their brackets. Per group,
# from the top: the IN jack on black, then a gold band with the LED and the three outputs. What sets the
# spacing (sleeve up, the Thonkiconn body runs 7.48 mm above its barrel and 2.92 mm below):
#   IN -> LED  8.0   the LED ring 1 mm clear of the IN nut on the panel
#   LED -> OUT 9.9   the jack body above the barrel clears the LED's 3.8 mm flange on the board
#   OUT pitch 11.0   bodies 0.6 mm apart (10.4 mm long)
#   band       5.0 below the IN barrel (1 mm under its nut) to 5.4 below the last OUT
#   next IN    10.9 below the last OUT: the bodies 0.5 mm apart (its nut is then 1.5 mm under the band)
COL_X = 11.0
IN_Y = (20.6, 71.4)
LED_DY, OUT_DY, OUT_PITCH = 8.0, 17.9, 11.0
PANEL_XY = {}
for g, y in zip(GROUPS, IN_Y):
    j = 4 * (g - 1)
    PANEL_XY[f"J{j + 1}"] = (COL_X, y)
    PANEL_XY[f"D{g}"] = (COL_X, y + LED_DY)
    for i in range(3):
        PANEL_XY[f"J{j + 2 + i}"] = (COL_X, round(y + OUT_DY + OUT_PITCH * i, 2))


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for ref, (px, py) in PANEL_XY.items():
    bx, by = board_xy(px, py)
    if ref.startswith("J"):
        PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)        # sleeve up
    else:
        PLACEMENT[ref] = (bx, by, 0)

# Headers (front view, faceplate board mm): x, y of the middle of the pin row, angle 270 = pins along y, pin
# 1 at the top. The jack bodies cover x 5.9-14.9; H1 stands in the left strip beside group 1's outputs, H2
# in the right strip beside group 2's, so the two hold the boards together at opposite corners.
HEADERS_FRONT = {
    "H1": (2.9, round(board_xy(0, PANEL_XY["J3"][1])[1], 2), 270),
    "H2": (16.85, round(board_xy(0, PANEL_XY["J7"][1])[1], 2), 270),
}


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        print(f"{name}: {len(parts)} parts, {len(nets_of(parts))} nets")
        kinds = collections.Counter((p.kind, p.value) for p in parts)
        print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    problems = check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} netlist problems")
    dc = dc_check()
    for b in dc:
        print("  " + b)
    print(f"{len(dc)} DC check failures")
    one, both = loading()
    print(f"a 1k source into IN 1 delivers {one:.4f} of itself, {both:.4f} when IN 2 is normalled to it")
    for t in (0.001, 0.01):
        lo, hi = worst_gain(t)
        print(f"worst-case gain with {t:.1%} resistors: {lo:.4f} .. {hi:.4f} "
              f"({(hi - 1) * 1200:+.1f} cents per volt-octave at most)")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
