"""The stereo mixer as one netlist: every part, its value and the net on each pin.

This file is the single source of truth; easyeda_export.py draws it.
Pin keys are the pin numbers of the EasyEDA library symbols, so the drawing
maps them one to one:
  resistors, caps    1, 2
  10 uF 178MU0033    1 = minus, 2 = plus (the symbol's + mark)
  1N5819             1 = cathode, 2 = anode
  pots (PTV09A)      1 = CCW end, 2 = wiper, 3 = CW end (4, 5 = mounting tabs)
  dual-gang pots     gang A 1/2/3, gang B 4/5/6 (same order)
  jack WQP518MA      1 = sleeve, 2 = switch (normal), 3 = tip
  ATE1D (SPDT)       2 = common; here 3 = ON, 1 = MUTE
  ATE2D (DPDT)       pole A 1/2/3, pole B 4/5/6 (2 and 5 common); 1, 4 = ON
  TL074              section 1: out 1, in- 2, in+ 3; 2: 7, 6, 5; 3: 8, 9, 10;
                     4: 14, 13, 12; V+ 4, V- 11

Signal flow
  Mono channel k (1-6):
    IN k -> LEVEL k (A100k) -> follower -> MUTE k -> CHk
    CHk -> 10k -> PLk -> 100k -> SUM_L     PAN k (B10k) from PLk to PRk,
    CHk -> 10k -> PRk -> 100k -> SUM_R     wiper to GND
    CHk -> SEND k (A100k) -> 100k -> SUM_S
  Stereo channels 7, 8: dual-gang LEVEL, two followers, DPDT MUTE,
    200k into each bus; 10k + 10k average -> SEND -> 100k -> SUM_S.
  Return (Clouds): dual-gang RETURN level -> 200k into each bus.
  Drums: DRUMS level -> 300k into each bus (centred, -3.5 dB per side).
  FX IN: 100k straight into SUM_S (the drum mixer's send).
  Buses: inverting summers, 100k feedback (22p across it).
  MASTER (dual A10k) -> output stages, gain -2 -> 1k -> OUT L / OUT R.
  Send: inverting summer -> inverter (gain -1) -> 1k -> SEND.
"""
from dataclasses import dataclass, field


@dataclass
class Part:
    ref: str
    kind: str          # R, C, CP, D, POT, POT2, JACK, SPDT, DPDT, TL074, HDR
    value: str
    nets: dict         # pin number -> net
    label: str = ""    # panel label or function
    tags: dict = field(default_factory=dict)


GND, VP, VN = "GND", "+12V", "-12V"

# TL074 sections: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}

# What each op-amp section does. Section 1 of every chip carries the supply
# pins in the library symbol, so the inverting stages (drawn on the bus page,
# next to the decoupling) take the section-1 slots.
OPAMPS = {
    ("U1", 1): ("SUM", "L"), ("U1", 2): ("FOL", "1"), ("U1", 3): ("FOL", "2"), ("U1", 4): ("FOL", "3"),
    ("U2", 1): ("SUM", "R"), ("U2", 2): ("FOL", "4"), ("U2", 3): ("FOL", "5"), ("U2", 4): ("FOL", "6"),
    ("U3", 1): ("SUM", "S"), ("U3", 2): ("FOL", "7L"), ("U3", 3): ("FOL", "7R"), ("U3", 4): ("FOL", "8L"),
    ("U4", 1): ("OUT", "L"), ("U4", 2): ("FOL", "8R"), ("U4", 3): ("OUT", "R"), ("U4", 4): ("OUT", "S"),
}


def opamp_of(kind, name):
    return next(k for k, v in OPAMPS.items() if v == (kind, name))


def _r(ref, value, n1, n2, label=""):
    return Part(ref, "R", value, {"1": n1, "2": n2}, label)


def _c(ref, value, n1, n2, label=""):
    return Part(ref, "C", value, {"1": n1, "2": n2}, label)


def _jack(ref, label, tip, normal=GND):
    nets = {"1": GND, "3": tip}
    if normal:
        nets["2"] = normal
    return Part(ref, "JACK", "", nets, label)


def _pot(ref, value, cw, wiper, ccw, label):
    return Part(ref, "POT", value, {"3": cw, "2": wiper, "1": ccw}, label)


def _pot2(ref, value, a, b, label):
    """a, b = (cw, wiper, ccw) for gang A and gang B."""
    return Part(ref, "POT2", value, {"3": a[0], "2": a[1], "1": a[2], "6": b[0], "5": b[1], "4": b[2]}, label)


MONO = [1, 2, 3, 4, 5, 6]
STEREO = [7, 8]


def mono_channel(k):
    """Parts of mono channel k. Designators: J k; RV 3k-2 / 3k-1 / 3k; SW k; R 5k-4 .. 5k."""
    rv, r = 3 * k - 2, 5 * k - 4
    return [
        _jack(f"J{k}", f"IN {k}", f"IN{k}"),
        _pot(f"RV{rv}", "A100k", f"IN{k}", f"LV{k}", GND, f"LEVEL {k}"),
        _pot(f"RV{rv + 1}", "B10k", f"PL{k}", GND, f"PR{k}", f"PAN {k}"),
        _pot(f"RV{rv + 2}", "A100k", f"CH{k}", f"SD{k}", GND, f"SEND {k}"),
        Part(f"SW{k}", "SPDT", "ATE1D", {"3": f"BF{k}", "2": f"CH{k}", "1": GND}, f"MUTE {k}"),
        _r(f"R{r}", "10k", f"CH{k}", f"PL{k}", "pan feed L"),
        _r(f"R{r + 1}", "10k", f"CH{k}", f"PR{k}", "pan feed R"),
        _r(f"R{r + 2}", "100k", f"PL{k}", "SUM_L", "into L bus"),
        _r(f"R{r + 3}", "100k", f"PR{k}", "SUM_R", "into R bus"),
        _r(f"R{r + 4}", "100k", f"SD{k}", "SUM_S", "into send bus"),
    ]


def stereo_channel(c):
    """Stereo channel c (7 or 8). J 7/8 or 9/10, RV 19/20 or 21/22, SW c, R 31-35 or 36-40."""
    i = c - 7
    jl, jr, rv, r = 7 + 2 * i, 8 + 2 * i, 19 + 2 * i, 31 + 5 * i
    L, R = f"{c}L", f"{c}R"
    return [
        _jack(f"J{jl}", f"IN {c} L", f"IN{L}"),
        _jack(f"J{jr}", f"IN {c} R", f"IN{R}", normal=f"IN{L}"),   # R takes L when unpatched
        _pot2(f"RV{rv}", "A100k", (f"IN{L}", f"LV{L}", GND), (f"IN{R}", f"LV{R}", GND), f"LEVEL {c}"),
        _pot(f"RV{rv + 1}", "A100k", f"AV{c}", f"SD{c}", GND, f"SEND {c}"),
        Part(f"SW{c}", "DPDT", "ATE2D", {"1": f"BF{L}", "2": f"CH{L}", "3": GND,
                                          "4": f"BF{R}", "5": f"CH{R}", "6": GND}, f"MUTE {c}"),
        _r(f"R{r}", "200k", f"CH{L}", "SUM_L", "into L bus"),
        _r(f"R{r + 1}", "200k", f"CH{R}", "SUM_R", "into R bus"),
        _r(f"R{r + 2}", "10k", f"CH{L}", f"AV{c}", "send average"),
        _r(f"R{r + 3}", "10k", f"CH{R}", f"AV{c}", "send average"),
        _r(f"R{r + 4}", "100k", f"SD{c}", "SUM_S", "into send bus"),
    ]


def inputs_block():
    """Clouds return, drum mixer input and FX IN."""
    return [
        _jack("J11", "RETURN L", "RT_L"),
        _jack("J12", "RETURN R", "RT_R", normal="RT_L"),
        _pot2("RV23", "A100k", ("RT_L", "RW_L", GND), ("RT_R", "RW_R", GND), "RETURN"),
        _r("R41", "200k", "RW_L", "SUM_L", "return into L bus"),
        _r("R42", "200k", "RW_R", "SUM_R", "return into R bus"),
        _jack("J13", "DRUMS", "DRM"),
        _pot("RV24", "A100k", "DRM", "DRW", GND, "DRUMS"),
        _r("R43", "300k", "DRW", "SUM_L", "drums into L bus"),
        _r("R44", "300k", "DRW", "SUM_R", "drums into R bus"),
        _jack("J14", "FX IN", "FXI"),
        _r("R45", "100k", "FXI", "SUM_S", "FX IN into send bus"),
    ]


def bus_block():
    """Summers, master, output stages and the send output."""
    return [
        _r("R46", "100k", "SUM_L", "MIX_L", "L bus feedback"),
        _c("C1", "22p", "SUM_L", "MIX_L"),
        _r("R47", "100k", "SUM_R", "MIX_R", "R bus feedback"),
        _c("C2", "22p", "SUM_R", "MIX_R"),
        _r("R48", "100k", "SUM_S", "MIX_S", "send bus feedback"),
        _c("C3", "22p", "SUM_S", "MIX_S"),
        _pot2("RV25", "A10k", ("MIX_L", "MST_L", GND), ("MIX_R", "MST_R", GND), "MASTER"),
        _r("R49", "100k", "MST_L", "NO_L", "output L input"),
        _r("R50", "200k", "NO_L", "OA_L", "output L feedback (gain 2)"),
        _r("R51", "1k", "OA_L", "OUT_L", "output L series"),
        _r("R52", "100k", "MST_R", "NO_R", "output R input"),
        _r("R53", "200k", "NO_R", "OA_R", "output R feedback (gain 2)"),
        _r("R54", "1k", "OA_R", "OUT_R", "output R series"),
        _r("R55", "100k", "MIX_S", "NO_S", "send inverter input"),
        _r("R56", "100k", "NO_S", "OA_S", "send inverter feedback"),
        _r("R57", "1k", "OA_S", "SEND", "send series"),
        _jack("J15", "SEND", "SEND", normal=None),
        _jack("J16", "OUT L", "OUT_L", normal=None),
        _jack("J17", "OUT R", "OUT_R", normal=None),
    ]


def power_block():
    hdr = {"1": "N12_IN", "2": "N12_IN", "11": "P12_IN", "12": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 11)})
    parts = [
        Part("J18", "HDR", "16-pin Eurorack", hdr, "POWER"),
        Part("D1", "D", "1N5819", {"2": "P12_IN", "1": "P12_D"}, "+12 V reverse protection"),
        Part("D2", "D", "1N5819", {"1": "N12_IN", "2": "N12_D"}, "-12 V reverse protection"),
        _r("R58", "10R", "P12_D", VP, "+12 V filter"),
        _r("R59", "10R", "N12_D", VN, "-12 V filter"),
        Part("C4", "CP", "10u", {"2": VP, "1": GND}, "+12 V bulk"),
        Part("C5", "CP", "10u", {"2": GND, "1": VN}, "-12 V bulk"),
    ]
    for i in range(4):   # one pair per TL074
        parts.append(_c(f"C{6 + 2 * i}", "100n", VP, GND, f"U{i + 1} +12 V"))
        parts.append(_c(f"C{7 + 2 * i}", "100n", GND, VN, f"U{i + 1} -12 V"))
    return parts


def opamp_parts():
    nets = {u: {"4": VP, "11": VN} for u in ("U1", "U2", "U3", "U4")}
    for (u, s), (kind, name) in OPAMPS.items():
        out, inm, inp = SECTION[s]
        if kind == "FOL":
            nets[u].update({out: f"BF{name}", inm: f"BF{name}", inp: f"LV{name}"})
        elif kind == "SUM":
            nets[u].update({out: f"MIX_{name}", inm: f"SUM_{name}", inp: GND})
        else:
            nets[u].update({out: f"OA_{name}", inm: f"NO_{name}", inp: GND})
    return [Part(u, "TL074", "TL074", n) for u, n in nets.items()]


def all_parts():
    parts = []
    for k in MONO:
        parts += mono_channel(k)
    for c in STEREO:
        parts += stereo_channel(c)
    return parts + inputs_block() + bus_block() + power_block() + opamp_parts()


if __name__ == "__main__":
    import collections
    parts = all_parts()
    refs = collections.Counter(p.ref for p in parts)
    dup = [r for r, n in refs.items() if n > 1]
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    for n in sorted(nets):
        if len(nets[n]) < 2:
            print("single-pin net:", n, nets[n])
    print(len(parts), "parts,", len(nets), "nets", "duplicates:", dup or "none")
    kinds = collections.Counter((p.kind, p.value) for p in parts)
    for (k, v), n in sorted(kinds.items()):
        print(f"  {n:3d} x {k} {v}")
