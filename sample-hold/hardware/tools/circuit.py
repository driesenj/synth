"""S&H: sample & hold, noise and random, after Moritz Klein's MKI x ES.EDU
S&H/Noise (SH_MANUAL_v1.pdf, production schematic EDUSH2 rev 2.0, p. 60).
10HP Eurorack, all analog, on one PCB: Thonk panel parts on its front,
everything else behind them.

Blocks (MKI designators in brackets):
  noise   Q1 BC548 base-emitter in breakdown, fed from +12 V through a
          4k7 / 47u filter and 100k (R14 C8 R15 VT1); 1u / 100k coupling into
          U1B, x148 (R21 / R20) = WN: white, about 10 V p-p
          U1C: WN through three series RC legs into 20k = +3 dB/oct, x1.33  BLUE
          U1A: WN through 100k into three shunt RC legs = -3 dB/oct, x5.5   PINK
  clock   U2A Schmitt relaxation oscillator: 1u from in- to GND, charged from
          the output through 2k + RATE (B500k rheostat, CW = 2k); 100k / 100k
          to in+. 0.9-227 Hz. Out -> 100k -> CLOCK's switch lug
  trigger CLOCK's tip -> 1n / 100k differentiator -> 1N4148 / 100k -> U2B
          in+, against 3 V (100k / 33k from +12 V) on in-: SAMP, a short
          +-11 V pulse per rising edge. CLOCK's tip also drives the LED:
          51k -> Q2 2N3904, collector through the LED and 2k to +12 V
  S&H     IN (normalled to WN) -> LEVEL (B100k) -> U2D buffer = SHI -> Q3
          J113 -> HOLD, 100n film to GND -> U2C buffer = SHB -> 1k -> S&H.
          1M from SHI to the gate, 1N4148 from the gate (anode) to SAMP:
          SAMP high = the JFET conducts (track), low = the gate at -10 V (hold)
  slew    SLEW IN (normalled to SHB) -> U3B buffer -> SLEW (A1M rheostat,
          CCW = 0) -> 470n film -> U3A buffer -> 1k -> SLEW
  gate    new, U1D (idle on the MKI board): SHB -> 10k -> in+, 1M from the
          output back to in+ (+-0.11 V hysteresis), in- on GND; out -> 1N4148
          -> 1k -> GATE, 100k to GND behind the diode: 0 V or about +10 V
  power   16-pin Eurorack header, a 1N5819 in each rail (+12 V: anode on the
          header; -12 V: cathode on the header), 10R + 47u per rail, a 100n
          pair at each op-amp

Changes from the MKI board: RATE B500k (MKI B250k), SLEW A1M (B100k), the
GATE output, SLEW IN normalled from SHB rather than the bare hold cap, the
house power entry. Test points left out.

`python circuit.py` prints the part counts, the netlist problems (single-pin
nets, designators used twice, op-amp pins left out) and a circuit check: an
ideal-op-amp nodal solve of this netlist, at DC and at audio frequencies,
for cases with known answers. The comparators (U2A, U2B, U1D) are given
their saturated output per case; the transistors that only make noise or
light the LED are left out.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  LED     3 mm, the lens centre between its two pads
"""
import collections
import math


class Part:
    def __init__(self, ref, kind, value="", nets=None, label=""):
        self.ref, self.kind, self.value, self.nets, self.label = ref, kind, value, dict(nets or {}), label

    def __repr__(self):
        return f"Part({self.ref} {self.kind} {self.value} {self.nets})"


def R(ref, value, a, b, label=""):
    return Part(ref, "R", value, {"1": a, "2": b}, label)


def C(ref, value, a, b, label=""):
    return Part(ref, "C", value, {"1": a, "2": b}, label)


def D4148(ref, anode, cathode, label=""):
    return Part(ref, "D4148", "1N4148", {"1": cathode, "2": anode}, label)      # 1 = cathode


GND, VP, VN = "GND", "+12V", "-12V"

# op-amp section pins: (out, in-, in+). TL074: A and B on the pin 1-7 side, C and D on the pin 8-14
# side, supply 4 / 11. TL072: A and B, supply 8 / 4.
SECTION = {"A": ("1", "2", "3"), "B": ("7", "6", "5"), "C": ("8", "9", "10"), "D": ("14", "13", "12")}
SUPPLY = {"TL074": {"4": VP, "11": VN}, "TL072": {"8": VP, "4": VN}}
# what each section does: (out, in-, in+); the sections the MKI board uses for the same jobs
OPAMPS = {
    ("U1", "A"): ("POUT", "PFB", "PKN"),       # pink, x5.5           (DA1A)
    ("U1", "B"): ("WN", "WFB", "NIN"),         # white, x148          (DA1B)
    ("U1", "C"): ("BOUT", "BFB", "BLN"),       # blue, x1.33          (DA1C)
    ("U1", "D"): ("GTO", GND, "GTP"),          # random gate          (idle on the MKI board)
    ("U2", "A"): ("OSC", "OSC_C", "OSC_P"),    # clock                (DA2A)
    ("U2", "B"): ("SAMP", "THR", "TRG"),       # trigger comparator   (DA2B)
    ("U2", "C"): ("SHB", "SHB", "HOLD"),       # hold buffer          (DA2C)
    ("U2", "D"): ("SHI", "SHI", "LV"),         # input buffer         (DA2D)
    ("U3", "A"): ("SLO", "SLO", "SLC"),        # slew out buffer      (DA3A)
    ("U3", "B"): ("SLB", "SLB", "SLI"),        # slew in buffer       (DA3B)
}
CHIPS = {"U1": "TL074", "U2": "TL074", "U3": "TL072"}
COMPARATORS = ("OSC", "SAMP", "GTO")           # outputs that swing rail to rail, never linear

# ---------------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net (None = open). The lug touches the tip while nothing is patched.
JACKS = [
    ("J1", "CLOCK", "CLK", "CLK_INT"),         # the internal clock, through R204
    ("J2", "IN", "IN", "WN"),                  # white noise, straight from U1B
    ("J3", "SLEW IN", "SLI", "SHB"),           # the S&H, from its buffer
    ("J4", "GATE", "GATE", None),
    ("J5", "WHITE", "WHITE", None),
    ("J6", "S&H", "SH_OUT", None),
    ("J7", "PINK", "PINK", None),
    ("J8", "BLUE", "BLUE", None),
    ("J9", "SLEW", "SLEW", None),
]
INPUTS = ("J1", "J2", "J3")
# ref, label, value (Alpha 9 mm), (CW end, wiper, CCW end). Pins 3 / 1 are the CW / CCW ends: fully CW
# puts the wiper on pin 3. RATE and SLEW are rheostats with the wiper tied to one end.
POTS = [
    ("RV1", "RATE", "B500k", ("RT", "OSC", "OSC")),     # CW: 0 ohm between RT and OSC = fastest
    ("RV2", "LEVEL", "B100k", ("IN", "LV", GND)),
    ("RV3", "SLEW", "A1M", ("SLC", "SLC", "SLB")),      # CCW: 0 ohm = no slew; the A taper grows slowly at first
]
# 3 mm red LED: 1 = anode, 2 = cathode
LEDS = [("D1", "CLOCK", ("LED_A", "LED_K"))]


def panel_parts():
    parts = []
    for ref, label, tip, lug in JACKS:
        nets = {"1": GND, "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, value, (cw, w, ccw) in POTS:
        parts.append(Part(ref, "POT", value, {"3": cw, "2": w, "1": ccw, "4": GND, "5": GND}, label))
    for ref, label, (a, k) in LEDS:
        parts.append(Part(ref, "LED", "3 mm red", {"1": a, "2": k}, label))
    return parts


# ---------------------------------------------------------------- the circuit
def noise_parts():
    return [
        R("R101", "4k7", VP, "NSUP", "noise supply filter"),
        Part("C101", "CP", "47u", {"2": "NSUP", "1": GND}, "noise supply filter"),     # 2 = +
        R("R102", "100k", "NSUP", "NE", "noise junction current"),
        # BC548, 1 = C (left open), 2 = B, 3 = E: the base-emitter junction in reverse breakdown
        Part("Q1", "BC548", "BC548", {"2": GND, "3": "NE"}, "noise source"),
        C("C102", "1u", "NE", "NIN", "film, noise coupling"),
        R("R103", "100k", "NIN", GND, "noise coupling"),
        R("R104", "100k", "WN", "WFB", "white gain 148"),
        R("R105", "680", "WFB", GND, "white gain 148"),
        R("R106", "1k", "WN", "WHITE", "white output"),
        # blue: three series RC legs from WN into 20k
        C("C103", "5n6", "WN", "BL1", "blue"), R("R107", "1M", "BL1", "BLN", "blue"),
        C("C104", "2n2", "WN", "BL2", "blue"), R("R108", "470k", "BL2", "BLN", "blue"),
        C("C105", "680p", "WN", "BL3", "blue"), R("R109", "10k", "BL3", "BLN", "blue"),
        R("R110", "20k", "BLN", GND, "blue"),
        R("R111", "33k", "BOUT", "BFB", "blue gain 1.33"),
        R("R112", "100k", "BFB", GND, "blue gain 1.33"),
        R("R113", "1k", "BOUT", "BLUE", "blue output"),
        # pink: 100k from WN into three shunt RC legs
        R("R114", "100k", "WN", "PKN", "pink"),
        C("C106", "680p", "PKN", "PK1", "pink"), R("R115", "4k7", "PK1", GND, "pink"),
        C("C107", "2n2", "PKN", "PK2", "pink"), R("R116", "47k", "PK2", GND, "pink"),
        C("C108", "5n6", "PKN", "PK3", "pink"), R("R117", "470k", "PK3", GND, "pink"),
        R("R118", "100k", "POUT", "PFB", "pink gain 5.5"),
        R("R119", "22k", "PFB", GND, "pink gain 5.5"),
        R("R120", "1k", "POUT", "PINK", "pink output"),
    ]


def clock_parts():
    return [
        C("C201", "1u", "OSC_C", GND, "film, clock timing"),
        R("R201", "2k", "OSC_C", "RT", "clock, fastest rate"),
        R("R202", "100k", "OSC", "OSC_P", "clock hysteresis"),
        R("R203", "100k", "OSC_P", GND, "clock hysteresis"),
        R("R204", "100k", "OSC", "CLK_INT", "internal clock into CLOCK's lug"),
        # the clock LED: 2N3904, 1 = E, 2 = B, 3 = C
        R("R205", "51k", "CLK", "LED_B", "LED driver base"),
        Part("Q2", "2N3904", "2N3904", {"1": GND, "2": "LED_B", "3": "LED_K"}, "clock LED driver"),
        R("R206", "2k", VP, "LED_A", "clock LED, 5 mA"),
        # trigger shaping
        C("C202", "1n", "CLK", "DIFF", "trigger differentiator"),
        R("R207", "100k", "DIFF", GND, "trigger differentiator"),
        D4148("D201", "DIFF", "TRG", "positive edges only"),
        R("R208", "100k", "TRG", GND, "trigger"),
        R("R209", "100k", VP, "THR", "3 V trigger threshold"),
        R("R210", "33k", "THR", GND, "3 V trigger threshold"),
    ]


def sh_parts():
    return [
        # J113, 1 = D, 2 = S, 3 = G (onsemi TO-92); the channel conducts either way
        Part("Q3", "J113", "J113", {"1": "HOLD", "2": "SHI", "3": "JG"}, "S&H switch"),
        R("R301", "1M", "SHI", "JG", "JFET gate to the source"),
        D4148("D301", "JG", "SAMP", "SAMP low pulls the gate to -10 V"),
        C("C301", "100n", "HOLD", GND, "film, hold"),
        R("R302", "1k", "SHB", "SH_OUT", "S&H output"),
    ]


def slew_parts():
    return [
        C("C401", "470n", "SLC", GND, "film, slew"),
        R("R401", "1k", "SLO", "SLEW", "slew output"),
    ]


def gate_parts():
    return [
        R("R501", "10k", "SHB", "GTP", "gate comparator in"),
        R("R502", "1M", "GTO", "GTP", "gate hysteresis, +-0.11 V"),
        D4148("D501", "GTO", "GTD", "gate: positive half only"),
        R("R503", "100k", "GTD", GND, "gate low = 0 V"),
        R("R504", "1k", "GTD", "GATE", "gate output"),
    ]


def opamp_parts():
    nets = {u: dict(SUPPLY[kind]) for u, kind in CHIPS.items()}
    for (u, sec), pins in OPAMPS.items():
        nets[u].update(dict(zip(SECTION[sec], pins)))
    return [Part(u, CHIPS[u], CHIPS[u], nets[u]) for u in CHIPS]


def power_parts():
    hdr = {"1": "N12_IN", "2": "N12_IN", "11": "P12_IN", "12": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 11)})
    parts = [
        Part("J10", "HDR16", "16-pin Eurorack", hdr, "POWER"),
        Part("D901", "D5819", "1N5819", {"2": "P12_IN", "1": "P12_D"}, "+12 V reverse protection"),   # 1 = cathode
        Part("D902", "D5819", "1N5819", {"1": "N12_IN", "2": "N12_D"}, "-12 V reverse protection"),
        R("R901", "10R", "P12_D", VP, "+12 V filter"),
        R("R902", "10R", "N12_D", VN, "-12 V filter"),
        Part("C901", "CP", "47u", {"2": VP, "1": GND}, "+12 V bulk"),
        Part("C902", "CP", "47u", {"2": GND, "1": VN}, "-12 V bulk"),
    ]
    for i, u in enumerate(CHIPS):                       # one pair per op-amp, beside its supply pins
        parts.append(C(f"C{903 + 2 * i}", "100n", VP, GND, f"{u} +12 V"))
        parts.append(C(f"C{904 + 2 * i}", "100n", GND, VN, f"{u} -12 V"))
    return parts


def all_parts():
    return (panel_parts() + noise_parts() + clock_parts() + sh_parts() + slew_parts() + gate_parts()
            + opamp_parts() + power_parts())


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets, designators used twice, op-amps with a pin left out."""
    parts = all_parts()
    nets = nets_of(parts)
    bad = [f"single-pin net {n} {nets[n]}" for n in sorted(nets) if len(nets[n]) < 2]
    refs = collections.Counter(p.ref for p in parts)
    bad += [f"{r} used {c} times" for r, c in refs.items() if c > 1]
    for p in parts:
        n = {"TL074": 14, "TL072": 8}.get(p.kind)
        if n and set(p.nets) != {str(i) for i in range(1, n + 1)}:
            bad.append(f"{p.ref}: pins {sorted(set(map(str, range(1, n + 1))) - set(p.nets), key=int)} unconnected")
    return bad


# ------------------------------------------------------------ circuit check
def value(v):
    """'100k' -> 1e5, '4k7' -> 4700, '10R' -> 10, '5n6' -> 5.6e-9, '47u' -> 4.7e-5, 'B500k' -> 5e5."""
    v = v.lstrip("AB")
    for unit, mul in (("k", 1e3), ("M", 1e6), ("R", 1.0), ("u", 1e-6), ("n", 1e-9), ("p", 1e-12)):
        if unit in v:
            a, b = v.split(unit)
            return float(f"{a or 0}.{b or 0}") * mul
    return float(v)


VSAT, VD = 11.0, 0.65         # TL07x output swing on +-12 V, 1N4148 drop
RON = 100.0                   # J113 on-resistance, datasheet maximum


def solve(f=0.0, inputs=None, loads=(), pots=None, jfet_on=True, sat=None, diode_on=(), inject=None,
          source_r=0.0):
    """Node voltages of the netlist (complex amplitudes when f > 0) with ideal op-amps.
    f: 0 = DC, supplies at +-12 V; f > 0: small-signal AC at f Hz, supplies at AC ground.
    inputs: {jack ref: volts} into patched input jacks, through source_r. loads: output jacks with a
    cable (100k to GND). pots: {ref: fraction of the track from pin 1 to the wiper}, default 0.5.
    jfet_on: Q3 conducting (100 ohm) or open. sat: {comparator output net: volts}; the comparators
    default to -VSAT. diode_on: diodes conducting, as shorts (fold the drop into sat). inject: {net:
    volts} forced (the noise junction). Left out: Q1 (replaced by inject), Q2 and the LED, and the
    diodes not in diode_on."""
    inputs, pots, inject = inputs or {}, pots or {}, inject or {}
    sat = {**{n: 0.0 if f else -VSAT for n in COMPARATORS}, **(sat or {})}
    w = 2 * math.pi * f
    fixed = {GND: 0.0, VP: 0.0 if f else 12.0, VN: 0.0 if f else -12.0, **sat, **inject}
    y, amps = [], []                         # (a, b, admittance); (out, in-, in+)
    for p in all_parts():
        n = p.nets
        if p.kind == "R":
            y.append((n["1"], n["2"], 1 / value(p.value)))
        elif p.kind in ("C", "CP"):
            y.append((n["1"], n["2"], 1j * w * value(p.value) + 1e-15))     # a leak keeps DC nodes defined
        elif p.kind == "POT":
            t, rt = pots.get(p.ref, 0.5), value(p.value)
            y.append((n["1"], n["2"], 1 / max(t * rt, 1e-3)))
            y.append((n["2"], n["3"], 1 / max((1 - t) * rt, 1e-3)))
        elif p.kind == "JACK":
            tip, lug = n["3"], n.get("2")
            if p.ref in inputs:
                fixed[f"SRC_{p.ref}"] = inputs[p.ref]
                y.append((f"SRC_{p.ref}", tip, 1 / max(source_r, 1e-3)))
            elif p.ref in loads:
                y.append((tip, GND, 1e-5))
            elif lug:
                y.append((tip, lug, 1e3))
        elif p.kind == "J113":
            if jfet_on:
                y.append((n["1"], n["2"], 1 / RON))
        elif p.kind in ("D4148", "D5819") and p.ref in diode_on:
            y.append((n["1"], n["2"], 1e3))
    amps = [pins for pins in OPAMPS.values() if pins[0] not in sat]
    y.append(("P12_IN", "P12_D", 1e3))      # the power diodes conduct
    y.append(("N12_D", "N12_IN", 1e3))
    nodes = sorted({x for a, b, _ in y for x in (a, b)} | {x for amp in amps for x in amp})
    nodes = [x for x in nodes if x not in fixed]
    idx = {x: i for i, x in enumerate(nodes)}
    size = len(nodes)
    m = [[0j] * (size + 1) for _ in range(size)]
    outs = {out for out, _, _ in amps}
    for a, b, g in y:                        # KCL rows, except at op-amp outputs
        for s, t in ((a, b), (b, a)):
            if s in idx and s not in outs:
                m[idx[s]][idx[s]] += g
                if t in idx:
                    m[idx[s]][idx[t]] -= g
                else:
                    m[idx[s]][size] += g * fixed[t]
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
                k = m[r][c] / m[c][c]
                m[r] = [x - k * z for x, z in zip(m[r], m[c])]
    v = dict(fixed)
    v.update({x: m[i][size] / m[i][i] for i, x in enumerate(nodes)})
    return v


def _db(x):
    return 20 * math.log10(abs(x))


def part(ref):
    return next(p for p in all_parts() if p.ref == ref)


def clock_range():
    """Internal clock (Hz) fully CCW and fully CW: f = 1 / (2 R C ln((1 + b) / (1 - b))), b the share of
    the output fed back to in+."""
    b = value(part("R203").value) / (value(part("R202").value) + value(part("R203").value))
    c = value(part("C201").value)
    r0, rv = value(part("R201").value), value(part("RV1").value)
    k = 2 * c * math.log((1 + b) / (1 - b))
    return 1 / (k * (r0 + rv)), 1 / (k * r0)


def circuit_check():
    """Cases with known answers. Returns the failures and a few measured figures for the docs."""
    hop = 100 / 101                          # a 1k output into a 100k load
    jacks_out = ("J4", "J5", "J6", "J7", "J8", "J9")
    bad, figs = [], {}

    def expect(name, v, want, tol=1e-6):
        for net, x in want.items():
            if abs(v[net] - x) > tol:
                got, exp = complex(v[net]), complex(x)
                bad.append(f"{name}: {net} = {got.real:+.4f}{got.imag:+.4f}j V, expected {exp.real:+.4f}{exp.imag:+.4f}j V")

    # DC: thresholds of the three comparators
    expect("trigger threshold, 100k / 33k from +12 V", solve(), {"THR": 12 * 33 / 133})
    expect("clock thresholds, half the output swing", solve(sat={"OSC": VSAT}), {"OSC_P": VSAT / 2})
    expect("clock thresholds, half the output swing", solve(sat={"OSC": -VSAT}), {"OSC_P": -VSAT / 2})
    th = -VSAT * 10 / 1000                   # SHB where GTP crosses 0 V with the gate high
    expect("gate hysteresis: high holds down to -0.11 V", solve(inputs={"J2": th}, pots={"RV2": 1.0},
           sat={"GTO": VSAT}), {"GTP": 0.0})
    expect("gate hysteresis: low holds up to +0.11 V", solve(inputs={"J2": -th}, pots={"RV2": 1.0},
           sat={"GTO": -VSAT}), {"GTP": 0.0})
    expect("gate high, D501 on", solve(inputs={"J2": 1.0}, pots={"RV2": 1.0}, sat={"GTO": VSAT - VD},
           diode_on=("D501",), loads=jacks_out), {"GATE": (VSAT - VD) * hop})
    expect("gate low, D501 off", solve(inputs={"J2": -1.0}, pots={"RV2": 1.0}, loads=jacks_out), {"GATE": 0.0})
    # DC: the S&H tracking (JFET on), LEVEL, the slew path and its normal
    expect("3 V into IN, LEVEL CW, tracking", solve(inputs={"J2": 3.0}, pots={"RV2": 1.0}, loads=jacks_out),
           {"SHI": 3.0, "HOLD": 3.0, "SH_OUT": 3 * hop, "SLEW": 3 * hop})
    expect("4 V into IN, LEVEL at 1/4", solve(inputs={"J2": 4.0}, pots={"RV2": 0.25}), {"SHB": 1.0})
    expect("SLEW IN patched breaks the normal", solve(inputs={"J2": 3.0, "J3": -2.0}, pots={"RV2": 1.0}),
           {"SHB": 3.0, "SLO": -2.0})
    expect("RATE CW: only R201's 2k between OSC and OSC_C", solve(pots={"RV1": 1.0}, sat={"OSC": VSAT},
           inject={"OSC_C": 0.0}), {"RT": VSAT}, tol=1e-4)
    # AC: white noise gain, IN's normal, the coloured outputs, the slew corner
    f = 1000.0
    nin = 1 / (1 + 1 / (1j * 2 * math.pi * f * 1e-6 * 1e5))      # C102 / R103 high-pass
    v = solve(f, inject={"NE": 1e-3}, pots={"RV2": 1.0, "RV3": 0.0}, loads=jacks_out)
    expect("white: x148 at 1 kHz", v, {"WN": 1e-3 * nin * (1 + 100e3 / 680)})
    track = 1 / (1 + 1j * 2 * math.pi * f * RON * value(part("C301").value))   # Q3's Ron into the hold cap
    expect("IN takes white noise, LEVEL CW, tracking", v, {"SHB": v["WN"] * track, "SLO": v["WN"] * track})
    for net, name in (("POUT", "pink"), ("BOUT", "blue")):
        lv = [_db(solve(fx, inject={"NE": 1e-3})[net]) for fx in (100, 1000, 10000)]
        slope = (lv[2] - lv[0]) / 2 / math.log2(10)     # dB per octave over 100 Hz - 10 kHz
        figs[name] = (slope, lv[1] - _db(v["WN"]))
        if not (2.0 < abs(slope) < 4.0 and (slope < 0) == (name == "pink")):
            bad.append(f"{name}: {slope:+.2f} dB/oct over 100 Hz - 10 kHz, expected about {'-' if name == 'pink' else '+'}3")
    tau = value(part("RV3").value) * value(part("C401").value)
    v = solve(1 / (2 * math.pi * tau), inputs={"J3": 1.0}, pots={"RV3": 1.0})
    expect("SLEW CW: -3 dB at 1 / (2 pi 1M 470n)", {"SLO": abs(v["SLO"])}, {"SLO": 1 / math.sqrt(2)})
    figs["tau"] = tau
    figs["clock"] = clock_range()
    return bad, figs


# ---------------------------------------------------------------- panel grid (panel frame, y down)
HP = 10
PANEL_W, PANEL_H = 50.5, 128.5          # HP x 5.08 - 0.3
BOARD_W, BOARD_H = 49.3, 108.0          # 0.6 mm in from each side, like the other modules
JACK_BARREL, POT_SHAFT = -0.78, 4.0

# Three columns, one per control: RATE over the clock LED and the CLOCK jack, LEVEL over IN, SLEW over
# SLEW IN. The outputs fill the two lower rows, which sit at Marblesy's and Side FXy's jack heights so
# the rows line up in the rack; the inputs are one row above them.
COL_X = (12.0, 25.25, 38.5)
JACK_Y = (80.0, 97.18, 111.78)
KNOB_Y, LEVEL_Y = 29.0, 52.0
PANEL_XY = {
    "RV1": (COL_X[0], KNOB_Y), "RV3": (COL_X[2], KNOB_Y), "RV2": (COL_X[1], LEVEL_Y), "D1": (COL_X[0], LEVEL_Y),
}
for k, (ref, *_) in enumerate(JACKS):
    PANEL_XY[ref] = (COL_X[k % 3], JACK_Y[k // 3])


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (from the bottom-left, y up)."""
    return px - (PANEL_W - BOARD_W) / 2, PANEL_H - (PANEL_H - BOARD_H) / 2 - py


PLACEMENT = {}
for ref, (px, py) in PANEL_XY.items():
    x, y = board_xy(px, py)
    if ref.startswith("J"):
        PLACEMENT[ref] = (round(x, 2), round(y - JACK_BARREL, 2), 0)        # sleeve up
    elif ref.startswith("RV"):
        PLACEMENT[ref] = (round(x, 2), round(y - POT_SHAFT, 2), 180)        # pins down
    else:
        PLACEMENT[ref] = (round(x, 2), round(y, 2), 0)


if __name__ == "__main__":
    parts = all_parts()
    print(f"{len(parts)} parts, {len(nets_of(parts))} nets")
    kinds = collections.Counter((p.kind, p.value) for p in parts)
    print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    problems = check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} netlist problems")
    bad, figs = circuit_check()
    for b in bad:
        print("  " + b)
    lo, hi = figs["clock"]
    print(f"{len(bad)} circuit check failures; clock {lo:.2f}-{hi:.0f} Hz, slew tau up to {figs['tau']:.2f} s, "
          + ", ".join(f"{k} {s:+.2f} dB/oct, {g:+.1f} dB vs white at 1 kHz" for k, (s, g) in
                      ((k, figs[k]) for k in ("pink", "blue"))))
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
