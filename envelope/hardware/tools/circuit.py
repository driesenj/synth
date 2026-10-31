"""Envy: four Moritz Klein envelopes (MKI x ES.EDU EG) in 16HP Eurorack, all
analog, on two stacked PCBs: a faceplate with the Thonk panel parts and four
board-to-board headers, and a main board with everything else (see "two
boards" below for why one board does not fit).

Per channel k (1-4), the kit's pseudo-ADSR (EG_MANUAL_v3.pdf):
  GATE k     comparator against VREF; unpatched it takes GATE k-1 (GATE 1: 0 V)
  ATTACK k   A1M, charge path: buffer -> 100R -> BAT85 -> ATTACK -> C_T
  DEC/REL k  A1M, discharge path: C_T -> DEC/REL -> BAT85 -> buffer (decay and
             release share it, as on the kit)
  SUSTAIN k  A100k divider on the gated comparator's output, 100k into the buffer
  MODE k     SPDT toggle: up LOOP (a Schmitt trigger on ENV re-fires the buffer
             between about 0.5 V and 7.5 V, gate ignored), down SINGLE
  OUT k      ENV, 0 .. about 9.7 V, 1k series
  INV k      AXIS x 2 - ENV = about 9.7 V .. 0 V, 1k series
  LED k      3 mm red, BC548 emitter follower on ENV, 1k5

Six op-amp sections per channel, 6 x TL074 (channels a, b = 1, 2 on U1-U3 and
3, 4 on U4-U6; the comparators' 20 V edges on their own chip):
  gate comparator   GIN_k (+) vs VREF (-) -> 1N4148 -> G_k (0 / ~10 V), 10k to GND
  burst comparator  HP_k (+) vs VREF (-) -> 1N4148 -> N_k; HP_k = G_k through 1u,
                    10k to GND, 1N4148 clamp: a ~14 ms full-level burst on every
                    rising gate, whatever the gate's level
  input buffer      MODE common BI_k (N_k or L_k) -> BUF_k -> 100R -> BO_k, the
                    steering diodes
  output buffer     CT_k (1u film, a second 1u footprint beside it, unfitted) -> ENV_k
  inverter          ENV_k -> 100k -> IV_k (-), AXIS (+), 100k feedback -> INVO_k -> 1k
  loop Schmitt      ENV_k (-), SP_k (+) = 100k to +12 V, 100k to GND, 100k from SC_k;
                    SC_k -> 1N4148 -> L_k, 100k to GND
Shared: VREF = 100k / 27k from +12 V (2.55 V, 100n), AXIS = 100k / 68k (4.86 V, 1u);
the kit uses 3.8 V and a 6 V axis (docs/design.md, changes from the kit).

Pin maps: TL074 sections (out, in-, in+); jack 1 sleeve, 2 switch lug, 3 tip;
Alpha pot 1 CCW, 2 wiper, 3 CW, 4/5 lugs (the time pots are rheostats between
pin 1 and the wiper, the wiper tied to pin 3: clockwise is slower, and a lifted
wiper leaves the full 1M rather than an open circuit); Dailywell 2MS1 SPDT, pins
in a column with pin 3 at the bottom, lever up joins 2-3; BC548 TO-92 1 C, 2 B,
3 E; 1N4148 / BAT85 / 1N5819 1 cathode, 2 anode; 3 mm LED 1 anode, 2 cathode;
electrolytic 1 -, 2 +.

`python circuit.py` prints the part counts and the netlist problems (single-pin
nets, designators used twice, TL074 pins left out); `python sim.py` runs the
netlist in time and checks the envelope against the numbers in docs/design.md.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  toggle  bushing centre (the middle pin row); pin 3 at the bottom
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


def D(ref, kind, anode, cathode, label=""):
    value = {"D4148": "1N4148", "DBAT85": "BAT85", "D5819": "1N5819"}[kind]
    return Part(ref, kind, value, {"1": cathode, "2": anode}, label)


CHANNELS = 4
CH = range(1, CHANNELS + 1)
GND, VP, VN = "GND", "+12V", "-12V"

# TL074 section pins: (out, in-, in+); A and B on the pin 1-7 side, C and D on the pin 8-14 side
SECTION = {"A": ("1", "2", "3"), "B": ("7", "6", "5"), "C": ("8", "9", "10"), "D": ("14", "13", "12")}

# ---------------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net (None = open). The lug touches the tip while nothing is patched.
JACKS = [(f"J{k}", f"GATE {k}", f"GATE{k}", GND if k == 1 else f"GATE{k - 1}") for k in CH]
JACKS += [(f"J{CHANNELS + k}", f"OUT {k}", f"OUT{k}", None) for k in CH]
JACKS += [(f"J{2 * CHANNELS + k}", f"INV {k}", f"INV{k}", None) for k in CH]
# ref, label, value, (CW end pin 3, wiper pin 2, CCW end pin 1). Fully CW puts the wiper on pin 3.
POTS = []
for k in CH:
    POTS += [(f"RV{3 * k - 2}", f"ATTACK {k}", "A1M", (f"CT{k}", f"CT{k}", f"AK{k}")),
             (f"RV{3 * k - 1}", f"DEC/REL {k}", "A1M", (f"CT{k}", f"CT{k}", f"RK{k}")),
             (f"RV{3 * k}", f"SUSTAIN {k}", "A100k", (f"G{k}", f"SUS{k}", GND))]
# ref, label, (pin 1, common, pin 3): lever up joins 2-3 = LOOP, down joins 2-1 = SINGLE
TOGGLES = [(f"SW{k}", f"MODE {k}", (f"N{k}", f"BI{k}", f"L{k}")) for k in CH]
LEDS = [(f"D{k}", f"ENV {k}", f"LE{k}") for k in CH]


def panel_parts():
    parts = []
    for ref, label, tip, lug in JACKS:
        nets = {"1": GND, "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, value, (cw, w, ccw) in POTS:
        parts.append(Part(ref, "POT", value, {"3": cw, "2": w, "1": ccw, "4": GND, "5": GND}, label))
    for ref, label, pins in TOGGLES:
        parts.append(Part(ref, "TOGGLE", "SPDT ON-ON", {str(i + 1): n for i, n in enumerate(pins)}, label))
    for ref, label, net in LEDS:
        parts.append(Part(ref, "LED", "3 mm red", {"1": net, "2": GND}, label))
    return parts


# ------------------------------------------------------------------ channels
def channel_parts(k):
    """Channel k's parts behind the panel: R / C / D k01.. and its LED driver Q k."""
    r = 100 * k
    return [
        # gate input and the gate comparator's output
        R(f"R{r + 1}", "10k", f"GATE{k}", f"GIN{k}", "gate input series"),
        R(f"R{r + 2}", "100k", f"GIN{k}", GND, "gate pull-down: a dangling cable reads 0 V"),
        D(f"D{r + 1}", "D4148", GND, f"GIN{k}", "clamps a negative gate (TL07x phase reversal)"),
        D(f"D{r + 2}", "D4148", f"GC{k}", f"G{k}", "gate comparator: passes the high state only"),
        R(f"R{r + 3}", "10k", f"G{k}", GND, "G low after the gate; resets the high-pass in ~10 ms"),
        R(f"R{r + 4}", "100k", f"SUS{k}", f"N{k}", "sustain level into the buffer node"),
        # the burst: high-pass on G, burst comparator, diode onto N
        C(f"C{r + 1}", "1u", f"G{k}", f"HP{k}", "burst high-pass, film"),
        R(f"R{r + 5}", "10k", f"HP{k}", GND, "burst high-pass"),
        D(f"D{r + 3}", "D4148", GND, f"HP{k}", "clamps the high-pass's negative spike"),
        D(f"D{r + 4}", "D4148", f"BC{k}", f"N{k}", "burst comparator: overrides the sustain level"),
        # input buffer, steering, timing cap
        R(f"R{r + 6}", "100R", f"BUF{k}", f"BO{k}", "softens the fastest edge"),
        D(f"D{r + 5}", "DBAT85", f"BO{k}", f"AK{k}", "attack steering"),
        D(f"D{r + 6}", "DBAT85", f"RK{k}", f"BO{k}", "decay / release steering"),
        C(f"C{r + 2}", "1u", f"CT{k}", GND, "timing, film"),
        C(f"C{r + 3}", "1u DNF", f"CT{k}", GND, "timing x2: fit for slower envelopes (the kit's C11)"),
        # outputs
        R(f"R{r + 7}", "1k", f"ENV{k}", f"OUT{k}", "OUT series"),
        R(f"R{r + 8}", "100k", f"ENV{k}", f"IV{k}", "inverter in"),
        R(f"R{r + 9}", "100k", f"IV{k}", f"INVO{k}", "inverter feedback"),
        R(f"R{r + 10}", "1k", f"INVO{k}", f"INV{k}", "INV series"),
        Part(f"Q{k}", "NPN", "BC548", {"1": VP, "2": f"ENV{k}", "3": f"QE{k}"}, "LED driver, emitter follower"),
        R(f"R{r + 11}", "1k5", f"QE{k}", f"LE{k}", "LED, about 5 mA at the peak"),
        # loop Schmitt trigger
        R(f"R{r + 12}", "100k", VP, f"SP{k}", "Schmitt threshold"),
        R(f"R{r + 13}", "100k", f"SP{k}", GND, "Schmitt threshold"),
        R(f"R{r + 14}", "100k", f"SC{k}", f"SP{k}", "Schmitt hysteresis"),
        D(f"D{r + 7}", "D4148", f"SC{k}", f"L{k}", "loop drive: passes the high state only"),
        R(f"R{r + 15}", "100k", f"L{k}", GND, "loop drive pull-down"),
    ]


def opamp_parts():
    """U1-U3 serve channels 1 and 2, U4-U6 channels 3 and 4: comparators, buffers, Schmitt + inverter."""
    parts = []
    for p, (a, b) in enumerate(((1, 2), (3, 4))):
        roles = [
            {"A": (f"GC{a}", "VREF", f"GIN{a}"), "B": (f"BC{a}", "VREF", f"HP{a}"),
             "C": (f"BC{b}", "VREF", f"HP{b}"), "D": (f"GC{b}", "VREF", f"GIN{b}")},
            {"A": (f"BUF{a}", f"BUF{a}", f"BI{a}"), "B": (f"ENV{a}", f"ENV{a}", f"CT{a}"),
             "C": (f"ENV{b}", f"ENV{b}", f"CT{b}"), "D": (f"BUF{b}", f"BUF{b}", f"BI{b}")},
            {"A": (f"SC{a}", f"ENV{a}", f"SP{a}"), "B": (f"INVO{a}", f"IV{a}", "AXIS"),
             "C": (f"INVO{b}", f"IV{b}", "AXIS"), "D": (f"SC{b}", f"ENV{b}", f"SP{b}")},
        ]
        what = ("comparators", "buffers", "loop Schmitt triggers and inverters")
        for i, role in enumerate(roles):
            nets = {"4": VP, "11": VN}
            for sec, trio in role.items():
                nets.update(dict(zip(SECTION[sec], trio)))
            parts.append(Part(f"U{3 * p + i + 1}", "TL074", "TL074", nets, f"channels {a}, {b}: {what[i]}"))
    return parts


def shared_parts():
    return [
        R("R901", "100k", VP, "VREF", "gate and burst threshold"),
        R("R902", "27k", "VREF", GND, "gate and burst threshold, 2.55 V"),
        C("C901", "100n", "VREF", GND, "threshold"),
        R("R903", "100k", VP, "AXIS", "inverter axis"),
        R("R904", "68k", "AXIS", GND, "inverter axis, 4.86 V"),
        C("C902", "1u", "AXIS", GND, "inverter axis: its ripple reaches INV twice"),
    ]


def power_parts():
    hdr = {"1": "N12_IN", "2": "N12_IN", "9": "P12_IN", "10": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 9)})
    parts = [
        Part("J13", "HDR10", "10-pin Eurorack", hdr, "POWER"),
        D("D901", "D5819", "P12_IN", "P12_D", "+12 V reverse protection"),
        D("D902", "D5819", "N12_D", "N12_IN", "-12 V reverse protection: cathode on the header"),
        R("R905", "10R", "P12_D", VP, "+12 V filter"),
        R("R906", "10R", "N12_D", VN, "-12 V filter"),
        Part("C903", "CP", "47u", {"2": VP, "1": GND}, "+12 V bulk"),
        Part("C904", "CP", "47u", {"2": GND, "1": VN}, "-12 V bulk"),
    ]
    for u in range(1, 7):                               # one pair per TL074, beside its supply pins
        parts.append(C(f"C{903 + 2 * u}", "100n", VP, GND, f"U{u} +12 V"))
        parts.append(C(f"C{904 + 2 * u}", "100n", GND, VN, f"U{u} -12 V"))
    return parts


def all_parts():
    parts = panel_parts() + opamp_parts() + shared_parts() + power_parts()
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
    """Netlist problems: single-pin nets, designators used twice, TL074s with a pin left out, and an
    op-amp output that drives another output's net."""
    parts = all_parts()
    nets = nets_of(parts)
    bad = [f"single-pin net {n} {nets[n]}" for n in sorted(nets) if len(nets[n]) < 2]
    refs = collections.Counter(p.ref for p in parts)
    bad += [f"{r} used {c} times" for r, c in refs.items() if c > 1]
    outs = collections.Counter()
    for p in parts:
        if p.kind == "TL074":
            if set(p.nets) != {str(i) for i in range(1, 15)}:
                bad.append(f"{p.ref}: pins {sorted(set(map(str, range(1, 15))) - set(p.nets), key=int)} unconnected")
            outs.update(p.nets[out] for out, _, _ in SECTION.values())
    bad += [f"{n} driven by {c} op-amp outputs" for n, c in outs.items() if c > 1]
    return bad


# ---------------------------------------------------------------- panel grid (panel frame, y down)
HP = 16
PANEL_W, PANEL_H = 80.9, 128.5          # 16HP, as Atlasy
BOARD_W, BOARD_H = 79.7, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins

# Channels are columns, as on Offset, 18 mm apart; the left margin holds the row words. Knobs at the
# top, jacks at the bottom so cables hang away from the hands; the outputs on the gold band. Jacks in a
# column need 13 mm: the tip pad of one sits 4.9 mm below its barrel, the sleeve pad of the next 6.5 mm
# above its own (11 mm put OUT's tip pad on INV's sleeve pad). So the LED sits right of its OUT jack,
# between the columns, and GATE clears the toggle bodies above it.
CH_X = [13.0 + 18.0 * i for i in range(CHANNELS)]
ROW = {"attack": 25.5, "decay": 41.0, "sustain": 56.5, "mode": 70.0, "gate": 82.5, "out": 96.0, "inv": 109.0}
TOGGLE_DX = -2.5                        # the toggle left of the column line, its LOOP / SINGLE words right
LED_DX = 7.2                            # the LED right of its OUT jack


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for k, x in enumerate(CH_X, start=1):
    for ref, row in ((f"RV{3 * k - 2}", "attack"), (f"RV{3 * k - 1}", "decay"), (f"RV{3 * k}", "sustain")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - POT_SHAFT, 2), 0)          # pins down
    for ref, row in ((f"J{k}", "gate"), (f"J{CHANNELS + k}", "out"), (f"J{2 * CHANNELS + k}", "inv")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)        # sleeve up
    PLACEMENT[f"SW{k}"] = (*board_xy(x + TOGGLE_DX, ROW["mode"]), 0)   # pin 3 at the bottom
    PLACEMENT[f"D{k}"] = (*board_xy(x + LED_DX, ROW["out"]), 0)


# ------------------------------------------------------------- two boards
# A DIP-14's pads cannot sit under a jack, pot or toggle body on the faceplate (they are soldered on the
# panel side, where those bodies lie), and the only strip wide enough for one is above the ATTACK row:
# four fit, Envy has six. So the stack: the faceplate carries the panel parts and nothing else behind
# them but four 1 x 13 male headers, one per channel in the gap right of its column; the main board
# carries everything else and the female sockets at the same spots. Faceplate nets end in _F (GND stays GND:
# the boards are separate EasyEDA boards, and the header carries it).
HEADER_NETS = ["AK", "CT", "RK", "G", "SUS", "N", "BI", "L", "GND", "GATE", "LE", "OUT", "INV"]
HEADER_DX = 9.0                         # header column right of the channel's column (panel x), in the gap
HEADER_TOP = 21.0                       # panel y of pin 1; 13 pins reach down to 51.5, between the pots


def _faceplate(net):
    return net if net == GND else net + "_F"            # each board has its own GND net


def _hnet(name, k):
    return GND if name == "GND" else f"{name}{k}"


HEADERS = [(f"H{k}", "HDR13", [(_hnet(n, k), _faceplate(_hnet(n, k))) for n in HEADER_NETS]) for k in CH]


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


def header_xy(i):
    """Front-view board position of pin 1 of header i (0 = H1) and the step to the next pin (y up)."""
    bx, by = board_xy(CH_X[i] + HEADER_DX, HEADER_TOP)
    return bx, by, -2.54


def faceplate_parts():
    """The panel parts with faceplate net names, and the male headers."""
    parts = []
    for p in panel_parts():
        parts.append(Part(p.ref, p.kind, p.value, {pid: _faceplate(n) for pid, n in p.nets.items()}, p.label))
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


def main_board_parts():
    panel = {p.ref for p in panel_parts()}
    parts = [p for p in all_parts() if p.ref not in panel]
    for ref, kind, nets in HEADERS:
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets)}))
    return parts


def split_check():
    """Every net the panel parts share with the rest crosses on a header pin, and nothing else does."""
    panel = {n for p in panel_parts() for n in p.nets.values()}
    rest = {n for p in all_parts() if p.ref not in {q.ref for q in panel_parts()} for n in p.nets.values()}
    crossing = {mb for _, _, nets in HEADERS for mb, fb in nets}
    bad = [f"{n} joins the boards but is on no header" for n in sorted((panel & rest) - crossing)]
    bad += [f"{n} is on a header but does not join the boards" for n in sorted(crossing - (panel & rest))]
    for parts in (faceplate_parts(), main_board_parts()):
        nets = nets_of(parts)
        bad += [f"single-pin net {n} {nets[n]}" for n in sorted(nets) if len(nets[n]) < 2]
    return bad


if __name__ == "__main__":
    parts = all_parts()
    print(f"{len(parts)} parts, {len(nets_of(parts))} nets")
    kinds = collections.Counter((p.kind, p.value) for p in parts)
    print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    problems = check() + split_check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} netlist problems; faceplate {len(faceplate_parts())} parts, "
          f"main board {len(main_board_parts())} parts, {len(HEADERS)} x 13 header pins")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
