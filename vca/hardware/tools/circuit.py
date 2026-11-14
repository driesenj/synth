"""Veilsy: four VCAs on SSI2164 in 12HP Eurorack, all analog, Veils-style.
Single source of truth for the circuit and the panel.

Build: two through-hole boards (the user's choice, 2026-10-31). Faceplate:
the panel parts on its front, three male headers on its rear. Main board:
female sockets on its front, everything else on its rear; the two SSI2164s
are SOIC-16 (the only package), soldered by hand. Panel: RESPONSE knobs
(the user's choice), the draft in docs/design.md otherwise unchanged.

Per channel k (1-4), as Mutable's Veils (2020):
  IN k        signal in, DC-coupled, 100k; unpatched it takes IN k-1 (IN 1: 0 V)
  CV k        gain CV; unpatched it takes CV k-1 (CV 1: 0 V)
  LEVEL k     B10k from the +5 V reference: the offset
  CV AMT k    B100k on the CV jack: C = LEVEL + AMT x CV, and C = 5 V is unity
  RESPONSE k  B100k from Vc_lin (CCW) to Vc_exp (CW), continuous
  OUT k       G x IN k, 1k series; unpatched it adds into OUT k+1
  LED k       3 mm red, the channel's gain on a dB scale

Per channel, after the SSI2164 datasheet's application circuits (figures 1, 9
and 10; Sound Semiconductor, "Zero to 5V linear and exponential control"):
  audio   IN -> 100k -> audio cell (220R + 1n2 on its input) -> A: I-V summer
          (100k || 22p), which also takes OUT k-1's switch lug through 100k ->
          B: inverter -> 1k -> OUT k. Unity at Vc = 0.
  EXP     C: inverting summer of the LEVEL and CV AMT wipers and -5 V, 100k
          each, 49.9k || 100p: Vc_exp = 0.5 (5 V - C), 15 dB/V. A precision
          half-wave (two 1N4148) keeps it >= 0 V: EXP never goes above unity.
  LIN     D: the datasheet's figure 9 (Irwin's linearization). The two wipers
          into an integrator (100p) whose summing node also takes the servo
          cell's output; the servo cell's input takes 50 uA from -5 V. The
          integrator drives both the servo cell's VC and Vc_lin through 4k7,
          so the servo cell's gain is (C - 50 mV) / 4.95 V: 10M from -5 V into
          the summing node outweighs any TL074 offset, so C = 0 really closes
          the channel (101k on the reference keeps C = 5 V at unity); a BC557
          from Vc_lin to VCLAMP (2.77 V) then holds it at about -103 dB.
  E       follower on the RESPONSE wiper (B100k: its current stays below the
          EXP half-wave's, so that output stays driven) -> the audio cell's VC
  LED     +5 V (78L05, LEDs only) -> LED -> two 1N4148 -> 1k -> the follower:
          (2.0 V - Vc) / 1k, so the brightness is linear in dB from -60 dB up
U1 holds channels 1-2 (cells 1-2 audio, 3-4 their servos), U2 channels 3-4:
the datasheet wants a channel's two cells on one die. U3 / U4: A and B of
channels 1-2 / 3-4; U5 / U6: C and D of channels 1-2 / 3-4; U7: the four E.

Pin maps: TL074 sections (out, in-, in+), 4 V+, 11 V-; SSI2164 cells (IIN,
VC, IOUT), 1 MODE (open: class AB), 8 GND, 9 V-, 16 V+; jack 1 sleeve, 2
switch lug, 3 tip; Alpha pot 1 CCW, 2 wiper, 3 CW, 4 / 5 lugs; LED 1 anode,
2 cathode; diodes 1 cathode (the band), 2 anode; LM4040 (TO-92) 2 cathode,
1 and 3 both on the anode net (TI's tables disagree on which is the anode and
which NC, so wired this way it works either way round); 78L05 1 OUT, 2 GND,
3 IN; BC557 pins named by function (E,
B, C), so no footprint can swap them.

Net naming: nets that cross to the faceplate carry the same name on both
boards, with _F on the faceplate side (GND -> GND_F).

`python circuit.py` prints the part counts and the netlist problems;
`python sim.py` solves this netlist (DC laws, normals, chain, LEDs) and the
servo loop's step response.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it; sleeve pad 6.48 mm
          above the barrel, tip pad 4.92 mm below it, so jacks stacked in a
          column need 14.3 mm (Marblesy, Plaitsy, Side FXy)
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins down here)
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


def CP(ref, value, plus, minus, label=""):
    """Electrolytic: pin 1 +, pin 2 -."""
    return Part(ref, "CP", value, {"1": plus, "2": minus}, label)


def D(ref, kind, value, anode, cathode, label=""):
    """Diodes (DO-35 / DO-41): pin 1 = cathode (the band), pin 2 = anode."""
    return Part(ref, kind, value, {"1": cathode, "2": anode}, label)


def PNP(ref, e, b, c, label=""):
    """BC557B, TO-92, pins named by function."""
    return Part(ref, "PNP", "BC557B", {"E": e, "B": b, "C": c}, label)


CHANNELS = 4
CH = range(1, CHANNELS + 1)
GND, VP, VN = "GND", "+12V", "-12V"
P5, N5, P5L = "P5", "N5", "P5L"          # +-5 V references (LM4040), +5 V for the LEDs (78L05)

SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
CELL = {1: ("2", "3", "4"), 2: ("7", "6", "5"), 3: ("10", "11", "12"), 4: ("15", "14", "13")}
# (chip, cell) of each channel's audio and servo cell; (chip, section) of each op-amp stage
AUDIO_CELL = {k: (f"U{1 + (k - 1) // 2}", 1 + (k - 1) % 2) for k in CH}
SERVO_CELL = {k: (f"U{1 + (k - 1) // 2}", 3 + (k - 1) % 2) for k in CH}
STAGE = {}
for _k in CH:
    _pair, _odd = (_k - 1) // 2, (_k - 1) % 2
    STAGE[(_k, "A")] = (f"U{3 + _pair}", 1 + 2 * _odd)
    STAGE[(_k, "B")] = (f"U{3 + _pair}", 2 + 2 * _odd)
    STAGE[(_k, "C")] = (f"U{5 + _pair}", 1 + 2 * _odd)
    STAGE[(_k, "D")] = (f"U{5 + _pair}", 2 + 2 * _odd)
    STAGE[(_k, "E")] = ("U7", _k)
OPAMPS = ["U3", "U4", "U5", "U6", "U7"]
VCAS = ["U1", "U2"]


# ------------------------------------------------------------------ main board
def channel_parts(k):
    """One channel's passives, diodes and clamp transistor; the chips' pins are in chips()."""
    r = 100 * k
    parts = [
        # audio: IN -> audio cell -> A (I-V summer) -> B (inverter) -> 1k -> OUT
        R(f"R{r + 1}", "100k", f"IN{k}", f"CI{k}", "IN: the audio cell's input current"),
        R(f"R{r + 2}", "220R", f"CI{k}", f"CR{k}", "audio cell input network (datasheet)"),
        C(f"C{r + 1}", "1n2", f"CR{k}", GND, "audio cell input network (datasheet)"),
        R(f"R{r + 3}", "100k", f"SA{k}", f"AO{k}", "I-V feedback: unity at Vc = 0"),
        C(f"C{r + 2}", "22p", f"SA{k}", f"AO{k}", "I-V feedback, C0G"),
        R(f"R{r + 5}", "100k", f"AO{k}", f"SB{k}", "inverter in"),
        R(f"R{r + 6}", "100k", f"SB{k}", f"BO{k}", "inverter feedback"),
        R(f"R{r + 7}", "1k", f"BO{k}", f"OUT{k}", "output series"),
        # EXP: Vc_exp = 0.5 (5 V - C), clamped >= 0 V
        R(f"R{r + 8}", "100k", f"LW{k}", f"SE{k}", "EXP: LEVEL"),
        R(f"R{r + 9}", "100k", f"VW{k}", f"SE{k}", "EXP: CV"),
        R(f"R{r + 10}", "100k", N5, f"SE{k}", "EXP: +2.5 V offset, unity at C = 5 V"),
        R(f"R{r + 11}", "49k9", f"VCE{k}", f"SE{k}", "EXP feedback: 0.5 V/V = 15 dB/V"),
        C(f"C{r + 5}", "100p", f"VCE{k}", f"SE{k}", "EXP feedback, C0G"),
        D(f"D{r + 1}", "D4148", "1N4148", f"EO{k}", f"VCE{k}", "EXP half-wave: passes Vc_exp >= 0"),
        D(f"D{r + 2}", "D4148", "1N4148", f"SE{k}", f"EO{k}", "EXP half-wave: holds the summing node"),
        # LIN: the servo (datasheet figure 9)
        R(f"R{r + 12}", "100k", f"LW{k}", f"SL{k}", "LIN: LEVEL"),
        R(f"R{r + 13}", "100k", f"VW{k}", f"SL{k}", "LIN: CV"),
        R(f"R{r + 14}", "101k", N5, f"LI{k}", "LIN: the servo cell's -49.5 uA reference: unity at C = 5 V "
          "with the bias below"),
        R(f"R{r + 18}", "10M", N5, f"SL{k}", "LIN: -0.5 uA = C - 50 mV, so the channel closes at C = 0 "
          "whatever the op-amp's offset (TL074C: 10 mV, 20 mV of C)"),
        R(f"R{r + 15}", "220R", f"LI{k}", f"LR{k}", "servo cell input network (datasheet)"),
        C(f"C{r + 3}", "1n2", f"LR{k}", GND, "servo cell input network (datasheet)"),
        C(f"C{r + 4}", "100p", f"SL{k}", f"DO{k}", "LIN integrator, C0G"),
        R(f"R{r + 16}", "4k7", f"DO{k}", f"VCL{k}", "LIN: lets the clamp hold Vc_lin (datasheet: 1k; 4k7 "
          "keeps the clamp current at 1.5 mA)"),
        PNP(f"Q{k}", f"VCL{k}", "VCLAMP", GND, "LIN clamp: Vc_lin <= VCLAMP + 0.6 V, about -103 dB"),
        # LED: +5 V -> LED (faceplate) -> two 1N4148 -> 1k -> the follower's output
        D(f"D{r + 3}", "D4148", "1N4148", f"LK{k}", f"LM{k}", "LED: blocks the reverse voltage"),
        D(f"D{r + 4}", "D4148", "1N4148", f"LM{k}", f"LD{k}", "LED: dark below about -60 dB"),
        R(f"R{r + 17}", "1k", f"LD{k}", f"VC{k}", "LED: (2.0 V - Vc) / 1k"),
    ]
    if k > 1:
        parts.append(R(f"R{r + 4}", "100k", f"OSW{k - 1}", f"SA{k}", f"OUT {k - 1} unpatched: adds into channel {k}"))
    return parts


def chips():
    roles = {}            # (chip, section): (out, in-, in+)
    for k in CH:
        roles[STAGE[(k, "A")]] = (f"AO{k}", f"SA{k}", GND)
        roles[STAGE[(k, "B")]] = (f"BO{k}", f"SB{k}", GND)
        roles[STAGE[(k, "C")]] = (f"EO{k}", f"SE{k}", GND)
        roles[STAGE[(k, "D")]] = (f"DO{k}", f"SL{k}", GND)
        roles[STAGE[(k, "E")]] = (f"VC{k}", f"VC{k}", f"RW{k}")
    nets = {u: {"4": VP, "11": VN} for u in OPAMPS}
    for (u, s), role in roles.items():
        nets[u].update(dict(zip(SECTION[s], role)))
    parts = [Part(u, "TL074", "TL074", nets[u]) for u in OPAMPS]
    cells = {u: {"8": GND, "9": VN, "16": VP} for u in VCAS}       # pin 1 (MODE) open: class AB
    for k in CH:
        u, n = AUDIO_CELL[k]
        cells[u].update(dict(zip(CELL[n], (f"CI{k}", f"VC{k}", f"SA{k}"))))
        u, n = SERVO_CELL[k]
        cells[u].update(dict(zip(CELL[n], (f"LI{k}", f"VCL{k}", f"SL{k}"))))
    parts += [Part(u, "SSI2164", "SSI2164", cells[u], "channels 1-2" if u == "U1" else "channels 3-4")
              for u in VCAS]
    return parts


def reference_parts():
    return [
        Part("D901", "LM4040", "LM4040-5.0", {"1": GND, "2": P5, "3": GND},
             "+5 V: LEVEL (TO-92: cathode pin 2, anode pins 1 and 3)"),
        Part("D902", "LM4040", "LM4040-5.0", {"1": N5, "2": GND, "3": N5},
             "-5 V: EXP offsets, servo references (TO-92: cathode pin 2, anode pins 1 and 3)"),
        R("R901", "1k", VP, P5, "+5 V reference feed, 7 mA (LEVEL takes 2 mA)"),
        R("R902", "1k", N5, VN, "-5 V reference feed, 7 mA (under 1 mA used)"),
        C("C901", "100n", P5, GND, "+5 V reference"),
        C("C902", "100n", GND, N5, "-5 V reference"),
        Part("U8", "78L05", "78L05", {"3": VP, "2": GND, "1": P5L}, "+5 V for the LEDs, off the references"),
        C("C903", "100n", VP, GND, "78L05 in"),
        C("C904", "100n", P5L, GND, "78L05 out"),
        R("R903", "10k", VP, "VCLAMP", "LIN clamp: 3k / 10k from +12 V = 2.77 V (datasheet)"),
        R("R904", "3k", "VCLAMP", GND, "LIN clamp"),
        C("C905", "100n", "VCLAMP", GND, "LIN clamp"),
    ]


def power_parts():
    # Doepfer A-100 16-pin bus (doepfer.de/a100_man/a100t_e.htm), pin 1 = red stripe: 1-2 -12 V, 3-8 GND,
    # 9-10 +12 V, 11-12 +5 V, 13-14 CV, 15-16 Gate; +5 V, CV and Gate stay open. (Until 2026-11-14 this had GND
    # on 3-10 and +12 V on 11-12, which shorts the bus +12 V to GND; found by the 2026-11-13 test suites.)
    hdr = {"1": "N12_IN", "2": "N12_IN", "9": "P12_IN", "10": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 9)})                  # 11-16 (+5 V, CV, gate) open
    parts = [
        Part("J13", "HDR16", "16-pin Eurorack, 2.54 mm", hdr, "POWER (red stripe = -12 V = pin 1)"),
        D("D903", "D5819", "1N5819", "P12_IN", "P12_D", "+12 V reverse protection: anode on the header"),
        D("D904", "D5819", "1N5819", "N12_D", "N12_IN", "-12 V reverse protection: cathode on the header"),
        R("R905", "10R", "P12_D", VP, "+12 V filter"),
        R("R906", "10R", "N12_D", VN, "-12 V filter"),
        CP("C906", "10u", VP, GND, "+12 V bulk"),
        CP("C907", "10u", GND, VN, "-12 V bulk"),
    ]
    for i, u in enumerate(VCAS + OPAMPS):              # a pair beside every chip's supply pins
        parts.append(C(f"C{911 + 2 * i}", "100n", VP, GND, f"{u} +12 V"))
        parts.append(C(f"C{912 + 2 * i}", "100n", GND, VN, f"{u} -12 V"))
    return parts


def main_board_parts():
    parts = chips() + reference_parts() + power_parts()
    for k in CH:
        parts += channel_parts(k)
    for ref, kind, pins in HEADERS:                    # female sockets on this board's front
        parts.append(Part(ref, kind, "", {str(i + 1): m for i, (m, f) in enumerate(pins)}))
    return parts


# ------------------------------------------------------------------ the faceplate
def fp(net):
    return "GND_F" if net == GND else net + "_F"


# Board-to-board headers, male on the faceplate's rear, female on the main board's front. H1 and H2 are
# two rows in the strip above the LEVEL knobs (the only strip the panel parts leave free full width), and
# carry the knobs' nets; H3 is a row under the OUT jacks and carries the jacks' and LEDs' nets. Each
# channel's nets sit together, in column order; the pin order is tuned at placement (fewest crossings).
_H1, _H2, _H3 = [GND, P5], [GND], [GND]
for _k in CH:
    _H1 += [f"LW{_k}", f"VW{_k}"]
    _H2 += [f"VCL{_k}", f"RW{_k}", f"VCE{_k}"]
    _H3 += [f"IN{_k}", f"OUT{_k}"] + ([f"OSW{_k}"] if _k < CHANNELS else []) + [f"LK{_k}"]
_H1 += [GND]
_H2 += [GND]
_H3 += [P5L, GND]
HEADERS = [(f"H{i}", f"HDR{len(pins)}", [(n, fp(n)) for n in pins]) for i, pins in enumerate((_H1, _H2, _H3), 1)]
INTERFACE = sorted({m for _, _, pins in HEADERS for m, f in pins})


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1."""
    return "HF" + ref[1:]


# ---------------------------------------------------------- panel parts (faceplate front)
# ref, panel label, tip net, switch-lug net (None = open). The lug touches the tip while nothing is patched.
JACKS = [(f"J{k}", f"IN {k}", fp(f"IN{k}"), "GND_F" if k == 1 else fp(f"IN{k - 1}")) for k in CH]
JACKS += [(f"J{CHANNELS + k}", f"CV {k}", f"CV{k}_F", "GND_F" if k == 1 else f"CV{k - 1}_F") for k in CH]
JACKS += [(f"J{2 * CHANNELS + k}", f"OUT {k}", fp(f"OUT{k}"), fp(f"OSW{k}") if k < CHANNELS else None) for k in CH]
# ref, label, value, (CW end, wiper, CCW end): fully CW puts the wiper on pin 3
POTS = []
for _k in CH:
    POTS += [(f"RV{3 * _k - 2}", f"LEVEL {_k}", "B10k", (fp(P5), fp(f"LW{_k}"), "GND_F")),
             (f"RV{3 * _k - 1}", f"CV AMT {_k}", "B100k", (f"CV{_k}_F", fp(f"VW{_k}"), "GND_F")),
             (f"RV{3 * _k}", f"RESPONSE {_k}", "B100k", (fp(f"VCE{_k}"), fp(f"RW{_k}"), fp(f"VCL{_k}")))]
# ref, label, anode, cathode
LEDS = [(f"D{k}", f"GAIN {k}", fp(P5L), fp(f"LK{k}")) for k in CH]


def faceplate_parts():
    parts = []
    for ref, label, tip, lug in JACKS:
        nets = {"1": "GND_F", "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, value, (cw, w, ccw) in POTS:
        parts.append(Part(ref, "POT", value, {"3": cw, "2": w, "1": ccw, "4": "GND_F", "5": "GND_F"}, label))
    for ref, label, anode, cathode in LEDS:
        parts.append(Part(ref, "LED", "3 mm red", {"1": anode, "2": cathode}, label))
    for ref, kind, pins in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): f for i, (m, f) in enumerate(pins)}))
    return parts


def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


NO_CONNECT = {"SSI2164": {"1"}}                        # MODE open = class AB
PINS = {"TL074": 14, "SSI2164": 16, "LM4040": 3, "JACK": 3, "POT": 5, "HDR16": 16, "78L05": 3}


def check():
    """Single-pin nets, duplicate designators, chip pins left out, interface nets on one side only, header
    pins used on one side only, and the reverse diodes' orientation."""
    problems = []
    mb, fb = nets_of(main_board_parts()), nets_of(faceplate_parts())
    crossing = {"main": set(INTERFACE), "faceplate": {fp(n) for n in INTERFACE}}
    for name, parts, nets in (("main", main_board_parts(), mb), ("faceplate", faceplate_parts(), fb)):
        refs = collections.Counter(p.ref for p in parts)
        problems += [f"{name}: {r} used {n} times" for r, n in refs.items() if n > 1]
        for n, pins in nets.items():
            if len(pins) < 2 and n not in crossing[name]:
                problems.append(f"{name}: single-pin net {n} {pins}")
        for p in parts:
            n = PINS.get(p.kind)
            if n is None:
                continue
            want = {str(i) for i in range(1, n + 1)} - NO_CONNECT.get(p.kind, set())
            if p.kind == "JACK" and p.label.startswith("OUT 4"):
                want -= {"2"}                          # OUT 4's lug: nothing after it
            if p.kind == "HDR16":
                want -= {"11", "12", "13", "14", "15", "16"}       # +5 V, CV, gate: unused
            if set(p.nets) != want:
                problems.append(f"{name}: {p.ref} pins {sorted(want ^ set(p.nets), key=int)} wrong")
    for ref, kind, pins in HEADERS:
        for m, f in pins:
            if len(mb[m]) < 2 or len(fb[f]) < 2:
                problems.append(f"{ref}: {m} / {f} used on one side only")
    allp = {p.ref: p for p in main_board_parts()}
    if allp["D903"].nets != {"1": "P12_D", "2": "P12_IN"}:
        problems.append("D903: the +12 V diode's anode must be on the header")
    if allp["D904"].nets != {"1": "N12_IN", "2": "N12_D"}:
        problems.append("D904: the -12 V diode's cathode must be on the header")
    if allp["D901"].nets != {"1": GND, "2": P5, "3": GND}:
        problems.append("D901: the TO-92 LM4040's cathode (pin 2) must be on +5 V, pins 1 and 3 on GND")
    if allp["D902"].nets != {"1": N5, "2": GND, "3": N5}:
        problems.append("D902: the TO-92 LM4040's cathode (pin 2) must be on GND, pins 1 and 3 on -5 V")
    return problems


# ---------------------------------------------------------------- panel grid (panel frame, y down)
HP = 12
PANEL_W, PANEL_H = 60.6, 128.5          # 12HP, as Plaitsy
BOARD_W, BOARD_H = 59.4, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins

# Channels are columns, as on Offset and Envy, 13.3 mm apart: column 1 leaves the left margin to the row
# words, column 4 keeps LEVEL's scale 2 mm off the right edge. LEVEL is the big knob (the one played as
# a mixer fader); CV AMT and RESPONSE are small. The rows are spaced by the rear: a pot's pins sit 7.5 mm
# below its shaft, a jack's sleeve pad 6.48 mm above its barrel and its tip pad 4.92 mm below, so the
# last knob row needs 17 mm to the IN row, stacked jacks 14.3 mm, and CV -> OUT 18 mm for the LED
# between them (its body clear of the CV jack's body, its pads 1 mm clear of the OUT jack's sleeve pad,
# and the copper band 1.6 mm under the CV nuts, as on Envy); panel.py board_check() proves it.
CH_X = [12.0 + 13.3 * i for i in range(CHANNELS)]
ROW = {"level": 26.5, "amt": 42.5, "response": 58.5, "in": 75.5, "cv": 90.0, "led": 99.0, "out": 108.0}


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for _k, _x in enumerate(CH_X, start=1):
    for _ref, _row in ((f"RV{3 * _k - 2}", "level"), (f"RV{3 * _k - 1}", "amt"), (f"RV{3 * _k}", "response")):
        _bx, _by = board_xy(_x, ROW[_row])
        PLACEMENT[_ref] = (_bx, round(_by - POT_SHAFT, 2), 0)          # pins down
    for _ref, _row in ((f"J{_k}", "in"), (f"J{CHANNELS + _k}", "cv"), (f"J{2 * CHANNELS + _k}", "out")):
        _bx, _by = board_xy(_x, ROW[_row])
        PLACEMENT[_ref] = (_bx, round(_by - JACK_BARREL, 2), 0)        # sleeve up
    PLACEMENT[f"D{_k}"] = (*board_xy(_x, ROW["led"]), 0)


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        nets = nets_of(parts)
        print(f"{name}: {len(parts)} parts, {len(nets)} nets")
        kinds = collections.Counter((p.kind, p.value) for p in parts)
        print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    print(f"{len(INTERFACE)} nets cross between the boards on "
          f"{sum(len(p) for _, _, p in HEADERS)} header pins ({', '.join(f'{r}: {len(p)}' for r, _, p in HEADERS)})")
    problems = check()
    for b in problems:
        print("  problem:", b)
    print(f"{len(problems)} netlist problems")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
