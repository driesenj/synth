"""Atlasy: a Vostok Instruments Atlas clone. 16HP Eurorack, all analog.

The whole circuit as one netlist; the split over the boards comes with the
placement. docs/design.md explains the blocks and the numbers.

Per channel k (1-4), after Sound Semiconductor's AN701:
  IN k -> 100k -> input summer (51k: A = -0.51 IN, plus the resonance current)
  A -> four SSI2164 low-pass poles (15k in, 15k local feedback, 220p C0G,
       220R + 1n2 on each cell input; 48 kHz at 0 V) -> B, C, D, E
  LP = -2 E (buffer), HP = -1.95 (A + 2B + C), BP = -4.17 (C + 2D + E)
  resonance: BP -> 11k -> diode limiter -> 13k -> resonance cell (U5) ->
       the input summer; positive feedback at the cutoff, flat passbands
  mode toggle (DPDT ON-ON-ON): up LP, middle HP, down BP -> SEL k
  SEL k -> 1k -> OUT k; SEL k -> 47k -> the scanner's VCA
  FREQ: knob (between the filtered rails) and offset 220k, FREQ jack and FM2
       100k, 20k feedback, precision clamp at 0 V -> the four pole cells' VC
       (about -0.2 V per octave: 1 V/oct at the jacks)
  RES: knob (filtered +12 V to GND) and offset 240k, RES jack 100k, 20k,
       clamp -> the resonance cell's VC (0 V = most feedback, 2.2x the
       oscillation threshold, which falls near 2 o'clock)
Scanner: SCAN knob and jack -> non-inverting summer (S1, 5.3 .. 9.3 V) ->
  level shifts S2 = S1 - 2.8 V, S3 = S1 - 5.6 V (2.7k + 2.7k and a 1 mA
  sink) -> three degenerated PNP pairs stacked as a current line, against a
  ladder R1 / R2 / R3: the 0.5 mA tail ends up in W1 .. W4 and always adds
  up to 0.5 mA -> 3.0k loads (0 .. 1.5 V) on the AS3360 linear control
  inputs -> the four VCA currents summed into one I-V stage -> 1k -> SCAN
  OUT.

Pin maps: TL074 sections (out, in-, in+); SSI2164 cells (IIN, VC, IOUT),
pin 1 MODE open = class AB, 8 GND, 9 V-, 16 V+; AS3360 (Alfa datasheet):
1 GND, 2 IO1, 3 VE1, 4 VO1, 5 VC1, 6 II1, 7 VEE, 8 VREF, 9 II2, 10 VC2,
11 VO2, 12 VE2, 13 IO2, 14 VCC (log converters bridged 3-4 and 11-12 for
linear control, VREF 4n7 to ground, as in Alfa's figure 1); BC547 / BC557
TO-92 pins 1 C, 2 B, 3 E; jack 1 sleeve, 2 switch lug, 3 tip; Alpha pot
1 CCW, 2 wiper, 3 CW, 4/5 lugs; Dailywell 2M toggles: SPDT 2MS1 position
1 = 2-3, position 3 = 2-1; DPDT 2MD6 (ON-ON-ON) 2-3 + 5-6, 2-3 + 5-4,
2-1 + 5-4 (Dailywell catalogue; ring it out before soldering).

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins down, SCAN's up: it sits 7 mm
          from the bottom edge)
  toggle  bushing centre (the middle pin row)
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


def D(ref, anode, cathode, label="", kind="D4148"):
    """Diode: pin 1 cathode, pin 2 anode (the library 1N4148 / 1N5819)."""
    return Part(ref, kind, {"D4148": "1N4148", "D5819": "1N5819"}[kind], {"1": cathode, "2": anode}, label)


def Q(ref, kind, c, b, e, label=""):
    return Part(ref, kind, {"NPN": "BC547B", "PNP": "BC557B"}[kind], {"1": c, "2": b, "3": e}, label)


GND, VP, VN = "GND", "+12V", "-12V"
P12F, N12F = "+12V_POT", "-12V_POT"         # RC-filtered rails for the knobs, offsets and the scan ladder
CHANNELS = 4
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
CELL = {1: ("2", "3", "4"), 2: ("7", "6", "5"), 3: ("10", "11", "12"), 4: ("15", "14", "13")}
# Chips: U1-U4 the poles of channels 1-4, U5 the resonance cells (cell k = channel k); per channel two
# TL074: UA (the four integrators, section n = pole n) and UB (1 input summer, 2 HP, 3 BP, 4 LP);
# U14 / U15 the FREQ and RES summers (U14: ch 1 FREQ, RES, ch 2 FREQ, RES; U15 channels 3, 4); U16 the
# scanner (1 S1 summer, 2 output I-V, 3 / 4 spare); U17 / U18 the AS3360 VCAs (channels 1, 2 / 3, 4).
UA = {k: f"U{4 + 2 * k}" for k in range(1, CHANNELS + 1)}     # U6, U8, U10, U12
UB = {k: f"U{5 + 2 * k}" for k in range(1, CHANNELS + 1)}     # U7, U9, U11, U13
CV_AMP = {(k, "F"): (f"U{14 + (k - 1) // 2}", 1 + 2 * ((k - 1) % 2)) for k in range(1, CHANNELS + 1)}
CV_AMP.update({(k, "R"): (f"U{14 + (k - 1) // 2}", 2 + 2 * ((k - 1) % 2)) for k in range(1, CHANNELS + 1)})
VCA = {1: ("U17", 1), 2: ("U17", 2), 3: ("U18", 1), 4: ("U18", 2)}
AS_PINS = {1: {"io": "2", "vc": "5", "ii": "6"}, 2: {"io": "13", "vc": "10", "ii": "9"}}


# ------------------------------------------------------------ one channel
def filter_parts(k):
    """Input summer, four poles, the HP / BP / LP outputs, the resonance path, output resistors."""
    r, c, d = 100 * k, 100 * k, 100 * k
    A, P = f"A{k}", [f"A{k}", f"B{k}", f"C{k}", f"D{k}", f"E{k}"]
    parts = [
        R(f"R{r + 1}", "100k", f"IN{k}", f"S{k}", "input"),
        R(f"R{r + 2}", "51k", f"S{k}", A, "input summer feedback (x0.51)"),
        C(f"C{c + 1}", "22p", f"S{k}", A, "input summer"),
    ]
    for n in range(1, 5):          # pole n: P[n-1] -> cell n -> integrator -> P[n]
        i, rc, g = f"I{k}{n}", f"K{k}{n}", f"G{k}{n}"
        parts += [R(f"R{r + 2 + 3 * n}", "15k", P[n - 1], i, f"pole {n} in"),
                  R(f"R{r + 3 + 3 * n}", "15k", P[n], i, f"pole {n} feedback"),
                  R(f"R{r + 4 + 3 * n}", "220R", i, rc, f"pole {n} cell input network"),
                  C(f"C{c + 1 + n}", "1n2", rc, GND, f"pole {n} cell input network"),
                  C(f"C{c + 5 + n}", "220p", g, P[n], f"pole {n} integrator, C0G")]
    parts += [
        R(f"R{r + 20}", "20k", A, f"H{k}", "HP: A"), R(f"R{r + 21}", "10k", f"B{k}", f"H{k}", "HP: 2B"),
        R(f"R{r + 22}", "20k", f"C{k}", f"H{k}", "HP: C"), R(f"R{r + 23}", "39k", f"H{k}", f"HP{k}", "HP feedback"),
        R(f"R{r + 24}", "24k", f"C{k}", f"J{k}", "BP: C"), R(f"R{r + 25}", "12k", f"D{k}", f"J{k}", "BP: 2D"),
        R(f"R{r + 26}", "24k", f"E{k}", f"J{k}", "BP: E"), R(f"R{r + 27}", "100k", f"J{k}", f"BP{k}", "BP feedback"),
        R(f"R{r + 28}", "10k", f"E{k}", f"L{k}", "LP buffer in"), R(f"R{r + 29}", "20k", f"L{k}", f"LP{k}", "LP buffer feedback"),
        # resonance: BP -> 11k -> limiter (two diodes each way) -> 13k -> cell k of U5
        R(f"R{r + 30}", "11k", f"BP{k}", f"M{k}", "resonance"),
        R(f"R{r + 31}", "13k", f"M{k}", f"Q{k}", "resonance, into the cell"),
        R(f"R{r + 32}", "220R", f"Q{k}", f"QK{k}", "resonance cell input network"),
        C(f"C{c + 10}", "1n2", f"QK{k}", GND, "resonance cell input network"),
        D(f"D{d + 1}", f"M{k}", f"MA{k}", "limiter +"), D(f"D{d + 2}", f"MA{k}", GND, "limiter +"),
        D(f"D{d + 3}", GND, f"MB{k}", "limiter -"), D(f"D{d + 4}", f"MB{k}", f"M{k}", "limiter -"),
        R(f"R{r + 33}", "1k", f"SEL{k}", f"OUT{k}", "output"),
        R(f"R{r + 34}", "47k", f"SEL{k}", f"VI{k}", "into the scanner VCA"),
    ]
    return parts


def cv_parts(k):
    """FREQ and RES summers with their precision clamps (output never below 0 V)."""
    r, d = 100 * k + 40, 100 * k + 4
    return [
        R(f"R{r + 1}", "220k", f"FW{k}", f"FS{k}", "FREQ knob"),
        R(f"R{r + 2}", "220k", N12F, f"FS{k}", "FREQ offset"),
        R(f"R{r + 3}", "100k", f"FRQ{k}", f"FS{k}", "FREQ jack, 1 V/oct"),
        R(f"R{r + 4}", "100k", f"FM{k}", f"FS{k}", "FM2"),
        R(f"R{r + 5}", "20k", f"VF{k}", f"FS{k}", "FREQ feedback"),
        D(f"D{d + 1}", f"FO{k}", f"VF{k}", "FREQ clamp"), D(f"D{d + 2}", f"FS{k}", f"FO{k}", "FREQ clamp"),
        R(f"R{r + 6}", "240k", f"RW{k}", f"RS{k}", "RES knob"),
        R(f"R{r + 7}", "240k", N12F, f"RS{k}", "RES offset"),
        R(f"R{r + 8}", "100k", f"RC{k}", f"RS{k}", "RES CV"),
        R(f"R{r + 9}", "20k", f"VR{k}", f"RS{k}", "RES feedback"),
        D(f"D{d + 3}", f"RO{k}", f"VR{k}", "RES clamp"), D(f"D{d + 4}", f"RS{k}", f"RO{k}", "RES clamp"),
    ]


# ------------------------------------------------------------ scanner
def scanner_parts():
    parts = [
        # S1 = 5.3 + 0.34 * knob + 0.42 * CV: passive mix on the + input, gain 2
        R("R501", "100k", "SCW", "SP", "SCAN knob"), R("R502", "82k", "SCV", "SP", "SCAN CV"),
        R("R503", "75k", P12F, "SP", "SCAN offset"), R("R504", "43k", "SP", GND, "SCAN mix"),
        R("R505", "10k", "S1", "SN", "S1 gain 2"), R("R506", "10k", "SN", GND, "S1 gain 2"),
        # level shifts: a 1 mA sink pulls 2.7 V across each 2.7k
        R("R507", "2.7k", "S1", "S2", "level shift"), R("R508", "2.7k", "S2", "S3", "level shift"),
        Q("Q508", "NPN", "S3", "VBN", "SE", "level shift sink, 1 mA"),
        R("R509", "9.1k", "SE", VN, "sink"), R("R510", "2k", GND, "VBN", "sink bias -2 V"),
        R("R511", "10k", "VBN", VN, "sink bias -2 V"),
        # the ladder: R1 6.05 V, R2 4.56 V, R3 3.07 V
        R("R512", "12k", P12F, "R1", "ladder"), R("R513", "3k", "R1", "R2", "ladder"),
        R("R514", "3k", "R2", "R3", "ladder"), R("R515", "6.2k", "R3", GND, "ladder"),
        # tail: 0.5 mA from +12 V
        Q("Q501", "PNP", "T1", "VBP", "TE", "tail source 0.5 mA"),
        R("R516", "2.7k", VP, "TE", "tail"), R("R517", "2k", VP, "VBP", "tail bias 10 V"),
        R("R518", "10k", "VBP", GND, "tail bias 10 V"),
        # three stacked pairs: the scan side wins while its base is lower (PNP)
        Q("Q502", "PNP", "W1", "S1", "E1A", "stage 1 scan side -> channel 1"),
        Q("Q503", "PNP", "T2", "R1", "E1B", "stage 1 ladder side -> stage 2"),
        Q("Q504", "PNP", "W2", "S2", "E2A", "stage 2 scan side -> channel 2"),
        Q("Q505", "PNP", "T3", "R2", "E2B", "stage 2 ladder side -> stage 3"),
        Q("Q506", "PNP", "W3", "S3", "E3A", "stage 3 scan side -> channel 3"),
        Q("Q507", "PNP", "W4", "R3", "E3B", "stage 3 ladder side -> channel 4"),
    ]
    for i, (s, t) in enumerate((("E1A", "T1"), ("E1B", "T1"), ("E2A", "T2"), ("E2B", "T2"), ("E3A", "T3"),
                                ("E3B", "T3"))):
        parts.append(R(f"R{519 + i}", "1k", s, t, "emitter degeneration"))
    for k in range(1, CHANNELS + 1):
        parts.append(R(f"R{524 + k}", "3k", f"W{k}", GND, f"VCA {k} control, 0-1.5 V"))
        parts.append(D(f"D{500 + k}", GND, f"W{k}", f"VCA {k} control clamp"))
    parts += [R("R529", "51k", "SO", "SCO", "scanner output"), C("C501", "22p", "SO", "SCO", "scanner output"),
              R("R530", "1k", "SCO", "SCAN_OUT", "scanner output"),
              C("C502", "4n7", "VREF1", GND, "AS3360 reference"), C("C503", "4n7", "VREF2", GND, "AS3360 reference")]
    return parts


# ------------------------------------------------------------ chips
def opamp_parts():
    nets = {u: {"4": VP, "11": VN} for u in list(UA.values()) + list(UB.values()) + ["U14", "U15", "U16"]}

    def sec(u, s, out, inm, inp):
        o, m, p = SECTION[s]
        nets[u].update({o: out, m: inm, p: inp})

    for k in range(1, CHANNELS + 1):
        for n in range(1, 5):
            sec(UA[k], n, ["B", "C", "D", "E"][n - 1] + str(k), f"G{k}{n}", GND)
        sec(UB[k], 1, f"A{k}", f"S{k}", GND)
        sec(UB[k], 2, f"HP{k}", f"H{k}", GND)
        sec(UB[k], 3, f"BP{k}", f"J{k}", GND)
        sec(UB[k], 4, f"LP{k}", f"L{k}", GND)
        u, s = CV_AMP[(k, "F")]
        sec(u, s, f"FO{k}", f"FS{k}", GND)
        u, s = CV_AMP[(k, "R")]
        sec(u, s, f"RO{k}", f"RS{k}", GND)
    sec("U16", 1, "S1", "SN", "SP")
    sec("U16", 2, "SCO", "SO", GND)
    sec("U16", 3, "U16_3", "U16_3", GND)        # spare: follower on ground
    sec("U16", 4, "U16_4", "U16_4", GND)
    return [Part(u, "TL074", "TL074", n) for u, n in nets.items()]


def vca_parts():
    parts = []
    for k in range(1, CHANNELS + 1):            # the poles
        nets = {"8": GND, "9": VN, "16": VP}
        for n in range(1, 5):
            iin, vc, iout = CELL[n]
            nets.update({iin: f"I{k}{n}", vc: f"VF{k}", iout: f"G{k}{n}"})
        parts.append(Part(f"U{k}", "SSI2164", "SSI2164", nets, f"channel {k} poles"))
    nets = {"8": GND, "9": VN, "16": VP}        # the resonance cells
    for k in range(1, CHANNELS + 1):
        iin, vc, iout = CELL[k]
        nets.update({iin: f"Q{k}", vc: f"VR{k}", iout: f"S{k}"})
    parts.append(Part("U5", "SSI2164", "SSI2164", nets, "resonance"))
    for u, ref in (("U17", "VREF1"), ("U18", "VREF2")):
        nets = {"1": GND, "7": VN, "14": VP, "8": ref, "3": f"{u}_L1", "4": f"{u}_L1", "11": f"{u}_L2",
                "12": f"{u}_L2"}
        parts.append(Part(u, "AS3360", "AS3360", nets, "scanner VCAs"))
    by_ref = {p.ref: p for p in parts}
    for k, (u, half) in VCA.items():
        pins = AS_PINS[half]
        by_ref[u].nets.update({pins["ii"]: f"VI{k}", pins["vc"]: f"W{k}", pins["io"]: "SO"})
    return parts


NO_CONNECT = {"SSI2164": {"1"}}      # MODE open: class AB (datasheet)


def power_parts():
    hdr = {"1": "N12_IN", "2": "N12_IN", "11": "P12_IN", "12": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 11)})
    hdr.update({str(n): f"HDR_{n}" for n in range(13, 17)})        # +5 V and CV / gate: not used
    parts = [
        Part("J19", "HDR16", "16-pin Eurorack", hdr, "POWER"),
        D("D901", "P12_IN", "P12_D", "+12 V reverse protection", "D5819"),    # anode at the header
        D("D902", "N12_D", "N12_IN", "-12 V reverse protection", "D5819"),    # cathode at the header
        R("R901", "10R", "P12_D", VP, "+12 V filter"), R("R902", "10R", "N12_D", VN, "-12 V filter"),
        Part("C901", "CP", "22u", {"2": VP, "1": GND}, "+12 V bulk"),        # CP: pin 2 +, pin 1 -
        Part("C902", "CP", "22u", {"2": GND, "1": VN}, "-12 V bulk"),
        R("R903", "100R", VP, P12F, "knob rail filter"), R("R904", "100R", VN, N12F, "knob rail filter"),
        Part("C903", "CP", "22u", {"2": P12F, "1": GND}, "knob rail filter"),
        Part("C904", "CP", "22u", {"2": GND, "1": N12F}, "knob rail filter"),
    ]
    chips = [p.ref for p in opamp_parts() + vca_parts()]
    for i, u in enumerate(sorted(chips, key=lambda s: int(s[1:]))):      # a pair beside every chip
        parts.append(C(f"C{911 + 2 * i}", "100n", VP, GND, f"{u} +12 V"))
        parts.append(C(f"C{912 + 2 * i}", "100n", GND, VN, f"{u} -12 V"))
    return parts


# ------------------------------------------------------------ panel parts
JACKS, POTS, TOGGLES = [], [], []      # (ref, label, nets)
for k in range(1, CHANNELS + 1):
    n = 4 * (k - 1)
    prev_in, prev_f = (f"IN{k - 1}", f"FRQ{k - 1}") if k > 1 else (GND, GND)
    JACKS += [(f"J{n + 1}", f"IN {k}", {"1": GND, "2": prev_in, "3": f"IN{k}"}),
              (f"J{n + 2}", f"FREQ {k}", {"1": GND, "2": prev_f, "3": f"FRQ{k}"}),
              (f"J{n + 3}", f"FM2/RES {k}", {"1": GND, "2": GND, "3": f"X{k}"}),
              (f"J{n + 4}", f"OUT {k}", {"1": GND, "3": f"OUT{k}"})]          # output: switch lug open
    POTS += [(f"RV{2 * k - 1}", f"FREQ {k}", "B100k", {"1": N12F, "2": f"FW{k}", "3": P12F}),
             (f"RV{2 * k}", f"RES {k}", "B100k", {"1": GND, "2": f"RW{k}", "3": P12F})]
    # mode: SEL on A's common (2); B's common (5) feeds A's contact 3; 6 = LP, 4 = HP, 1 = BP
    TOGGLES += [(f"SW{k}", f"MODE {k}", "DPDT", {"2": f"SEL{k}", "3": f"MS{k}", "5": f"MS{k}", "6": f"LP{k}",
                                                 "4": f"HP{k}", "1": f"BP{k}"}),
                (f"SW{k + 4}", f"FM2/RES {k}", "SPDT", {"2": f"X{k}", "3": f"FM{k}", "1": f"RC{k}"})]
JACKS += [("J17", "SCAN", {"1": GND, "2": GND, "3": "SCV"}), ("J18", "SCAN OUT", {"1": GND, "3": "SCAN_OUT"})]
POTS += [("RV9", "SCAN", "B10k", {"1": GND, "2": "SCW", "3": P12F})]


def panel_parts():
    parts = [Part(ref, "JACK", "", nets, label) for ref, label, nets in JACKS]
    parts += [Part(ref, "POT", value, dict(nets, **{"4": GND, "5": GND}), label) for ref, label, value, nets in POTS]
    parts += [Part(ref, "TOGGLE_" + kind, {"DPDT": "2MD6T1B1M2QES", "SPDT": "2MS1T1B1M2QES"}[kind], nets, label)
              for ref, label, kind, nets in TOGGLES]
    return parts


def all_parts():
    parts = []
    for k in range(1, CHANNELS + 1):
        parts += filter_parts(k) + cv_parts(k)
    return parts + scanner_parts() + opamp_parts() + vca_parts() + power_parts() + panel_parts()


PINS = {"TL074": 14, "SSI2164": 16, "AS3360": 14, "HDR16": 16, "JACK": 3, "POT": 5, "TOGGLE_DPDT": 6,
        "TOGGLE_SPDT": 3, "R": 2, "C": 2, "CP": 2, "D4148": 2, "D5819": 2, "NPN": 3, "PNP": 3}
OPEN_OK = {"JACK": {"2"}}            # an output jack's switch lug stays open


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check(parts):
    """Netlist rules from the earlier boards: every pin on a net or deliberately open, no net with one
    pin, both reverse-protection diodes the right way round, no duplicate designators."""
    bad = []
    refs = collections.Counter(p.ref for p in parts)
    bad += [f"duplicate designator {r}" for r, n in refs.items() if n > 1]
    for p in parts:
        want = {str(i) for i in range(1, PINS[p.kind] + 1)}
        missing = want - set(p.nets) - NO_CONNECT.get(p.kind, set()) - OPEN_OK.get(p.kind, set())
        if missing:
            bad.append(f"{p.ref}: pins {sorted(missing, key=int)} on no net")
        if set(p.nets) - want:
            bad.append(f"{p.ref}: pins {sorted(set(p.nets) - want)} do not exist")
    for n, pins in nets_of(parts).items():
        if len(pins) < 2 and not n.startswith("HDR_"):
            bad.append(f"single-pin net {n}: {pins}")
    by = {p.ref: p for p in parts}
    if by["D901"].nets != {"1": "P12_D", "2": "P12_IN"}:
        bad.append("D901: the +12 V diode needs its anode (pin 2) on the header")
    if by["D902"].nets != {"1": "N12_IN", "2": "N12_D"}:
        bad.append("D902: the -12 V diode needs its cathode (pin 1) on the header")
    return bad


# ---------------------------------------------------------------- panel geometry
HP = 16
PANEL_W, PANEL_H = 80.9, 128.5          # Doepfer-style 16HP: 16 x 5.08 less 0.4
BOARD_W, BOARD_H = 79.7, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins
POT_PINS_UP = {"RV9"}                   # the rest point their pins down (towards -y, front view)

JACK_X = [7.0, 17.0, 27.0, 37.0]        # IN, FREQ, FM2/RES, OUT: 10 mm apart (Atlas: about 9.3)
KNOB_X = (52.5, 72.5)                   # FREQ, RES
ROW_Y = [21.0 + 22.0 * r for r in range(CHANNELS)]   # jacks and knobs of a channel on one line
MODE_XY = (23.0, 10.0)                  # mode toggle: under the FREQ / FM2-RES jacks, row + 10
FMRES_XY = (62.5, 10.0)                 # FM2/RES toggle: between the knobs, row + 10
NUMERAL_XY = (44.6, 7.0)                # numeral centre: between the jacks and FREQ, row + 7 (artwork only)
SCAN_Y = 111.6                          # scanner row
SCAN_JACK_X = (27.0, 37.0)              # SCAN CV under FM2/RES, scanner OUT under the OUTs
SCAN_KNOB_X = 62.5                      # SCAN knob under the FM2/RES toggles


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


def pot_pins(ref):
    """Unit vector from the shaft towards the pin row, board frame."""
    return (0, 1) if ref in POT_PINS_UP else (0, -1)


PLACEMENT = {}


def _pot(ref, px, py):
    bx, by = board_xy(px, py)
    ux, uy = pot_pins(ref)
    PLACEMENT[ref] = (round(bx + POT_SHAFT * ux, 2), round(by + POT_SHAFT * uy, 2), 0)


for r, y in enumerate(ROW_Y):
    for c, x in enumerate(JACK_X):
        bx, by = board_xy(x, y)
        PLACEMENT[f"J{4 * r + c + 1}"] = (bx, round(by - JACK_BARREL, 2), 0)
    for c, x in enumerate(KNOB_X):
        _pot(f"RV{2 * r + c + 1}", x, y)
    PLACEMENT[f"SW{r + 1}"] = (*board_xy(MODE_XY[0], y + MODE_XY[1]), 0)
    PLACEMENT[f"SW{r + 5}"] = (*board_xy(FMRES_XY[0], y + FMRES_XY[1]), 0)
for ref, x in zip(("J17", "J18"), SCAN_JACK_X):
    bx, by = board_xy(x, SCAN_Y)
    PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)
_pot("RV9", SCAN_KNOB_X, SCAN_Y)


# ---------------------------------------------------------------- how much board this is
# Rough through-hole areas (mm^2) per part with its share of the space round it, from the Plaitsy and
# mixer main boards (standing resistors, 2.54 mm): used to judge the board count before placing.
AREA = {"R": 16, "C": 22, "CP": 40, "D4148": 16, "D5819": 30, "NPN": 26, "PNP": 26, "TL074": 190,
        "SSI2164": 90, "AS3360": 190, "HDR16": 230}


if __name__ == "__main__":
    parts = all_parts()
    problems = check(parts)
    for b in problems:
        print("problem:", b)
    nets = nets_of(parts)
    kinds = collections.Counter((p.kind, p.value) for p in parts)
    print(f"{len(parts)} parts, {len(nets)} nets, {len(problems)} problems")
    print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    rear = [p for p in parts if p.kind in AREA]
    area = sum(AREA[p.kind] for p in rear)
    print(f"behind-panel parts: {len(rear)}, about {area:.0f} mm^2 of through-hole board "
          f"({area / (BOARD_W * BOARD_H):.2f} boards of {BOARD_W} x {BOARD_H})")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
