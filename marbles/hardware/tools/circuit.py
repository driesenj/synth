"""Marblesy: a Mutable Instruments Marbles clone on a Daisy Seed. The whole
circuit as one netlist, split over two boards.

Main board (MB): Daisy Seed on Rob Heel's seed_power_opamps breakout, seven
TL074 CV input stages, two transistor clock inputs, three gate output
stages, two MCP4922 DACs with their output stages, a 2.5 V reference.
Faceplate board (FB): 16 Thonkiconn jacks, 8 Alpha pots into a 74HC4051,
7 buttons read by a 74HC165, 7 LEDs (4 bicolour) driven by two 74HC595.

Net naming
  CV_*       jack tip of a CV input (FB: CV_*_F) -> MB input stage
  IN_*/OA_*  input stage summing node / op-amp output
  ADC_*      Seed ADC pin, after the 1k series resistor
  *_CLK_IN   clock jack tip (FB: *_CLK_F) -> transistor stage -> *_CLK (Seed GPIO)
  GATE_T1..3 Seed GPIO -> gate stage -> T1..T3 (FB: T1_F, jack tip)
  DAC_X1..Y  MCP4922 outputs -> output stage -> X1..Y (FB: X1_F, jack tip)
  POT_*_F    pot wipers (FB) into the mux; MUX_OUT / MUX_S0..2 cross to the MB
  L_*        74HC595 outputs (before the 470R), LED_* after it
  BTN_*_F    buttons into the 74HC165
  nets that cross the board-to-board headers carry the same name on both
  boards, with _F on the faceplate side (GND -> GND_F, GND_D -> GND_D_F).
"""
import collections


class Part:
    def __init__(self, ref, kind, value="", nets=None, label=""):
        self.ref, self.kind, self.value, self.nets, self.label = ref, kind, value, dict(nets or {}), label

    def __repr__(self):
        return f"Part({self.ref} {self.kind} {self.value} {self.nets})"


def R(ref, value, a, b):
    return Part(ref, "R", value, {"1": a, "2": b})


def C(ref, value, a, b):
    return Part(ref, "C", value, {"1": a, "2": b})


# --------------------------------------------------------------- Daisy Seed
# Seed pin number -> (libDaisy name, net). Pins with no net are left open.
# SPI1 is on D7..D10 (NSS, SCK, MISO, MOSI); the ADC-capable pins are 22..32
# and 35. 3V3D (pin 38) feeds the logic on the faceplate.
SEED = {
    "1": ("D0", "T_CLK"), "2": ("D1", "X_CLK"),
    "3": ("D2", "GATE_T1"), "4": ("D3", "GATE_T2"), "5": ("D4", "GATE_T3"),
    "6": ("D5", None), "7": ("D6", None),
    "8": ("D7", "DAC_CS1"), "9": ("D8", "SPI_SCK"), "10": ("D9", "SPI_MISO"), "11": ("D10", "SPI_MOSI"),
    "12": ("D11", "DAC_CS2"), "13": ("D12", "DAC_LDAC"), "14": ("D13", "LED_LATCH"), "15": ("D14", "BTN_LOAD"),
    "16": ("AIN1", None), "17": ("AIN2", None), "18": ("AOUT1", None), "19": ("AOUT2", None),
    "20": ("AGND", "GND"), "21": ("3V3A", "3V3A"),
    "22": ("D15/A0", "PROBE"),
    "23": ("D16/A1", "ADC_T_RATE"), "24": ("D17/A2", "ADC_T_BIAS"), "25": ("D18/A3", "ADC_T_JITTER"),
    "26": ("D19/A4", "ADC_DEJAVU"), "27": ("D20/A5", "ADC_X_SPREAD"), "28": ("D21/A6", "ADC_X_BIAS"),
    "29": ("D22/A7", None), "30": ("D23/A8", None),
    "31": ("D24/A9", "ADC_X_STEPS"), "32": ("D25/A10", "MUX_OUT"),
    "33": ("D26", "MUX_S0"), "34": ("D27", "MUX_S1"), "35": ("D28/A11", "MUX_S2"),
    "36": ("D29", None), "37": ("D30", None),
    "38": ("3V3D", "3V3D"), "39": ("VIN", None), "40": ("DGND", "GND"),
    # breakout headers, numbered as on Rob Heel's board
    "J1-1": ("GND", "GND"), "J1-2": ("-12V", "-12V"), "J1-3": ("-12V", "-12V"), "J1-4": ("-12V", "-12V"),
    "J3-1": ("GND", "GND"), "J3-2": ("+12V", "+12V"), "J3-3": ("+12V", "+12V"), "J3-4": ("+12V", "+12V"),
    "J4-1": ("AOUT1", None), "J4-2": ("GND", "GND"), "J4-3": ("AOUT2", None), "J4-4": ("GND", "GND"),
    "J5-1": ("AIN1", None), "J5-2": ("GND", "GND"), "J5-3": ("AIN2", None), "J5-4": ("GND", "GND"),
}

# ---------------------------------------------------------- CV input stages
# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
# name, label, op-amp, section. Gain -0.27 (100k/27k) puts +-5 V on 0.33..3.03 V.
CV_CHANNELS = [
    ("T_RATE", "RATE", "U3", 1), ("T_BIAS", "BIAS (t)", "U3", 2), ("T_JITTER", "JITTER", "U3", 3),
    ("DEJAVU", "DEJA VU", "U3", 4),
    ("X_SPREAD", "SPREAD", "U4", 1), ("X_BIAS", "BIAS (X)", "U4", 2), ("X_STEPS", "STEPS", "U4", 3),
]
GATES = [("T1", "U6", 1), ("T2", "U6", 2), ("T3", "U6", 3)]
# DAC outputs: name, chip, channel (A = VOUTA pin 14, B = VOUTB pin 10), output op-amp section
DAC_OUTS = [("X1", "U7", "A", "U5", 1), ("X2", "U7", "B", "U5", 2), ("X3", "U8", "A", "U5", 3),
            ("Y", "U8", "B", "U5", 4)]


def main_board_parts():
    parts = []
    parts.append(Part("U2", "SEED", "Daisy Seed + seed_power_opamps",
                      {pin: net for pin, (name, net) in SEED.items() if net}))
    # op-amps: supply pins
    tl = {u: {"4": "+12V", "11": "-12V"} for u in ("U3", "U4", "U5", "U6")}
    n = 21
    # CV input stages
    for i, (name, label, u, s) in enumerate(CV_CHANNELS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: "BIAS"})
        parts.append(R(f"R{n}", "100k", f"CV_{name}", f"IN_{name}")); n += 1
        parts.append(R(f"R{n}", "27k", f"IN_{name}", f"OA_{name}")); n += 1
        parts.append(R(f"R{n}", "1k", f"OA_{name}", f"ADC_{name}")); n += 1
        parts.append(C(f"C{21 + i}", "1n", f"IN_{name}", f"OA_{name}"))
    # U4 section 4: -2.5 V from the reference (inverter), for the DAC output stages
    out, inm, inp = SECTION[4]
    tl["U4"].update({out: "NEG_REF", inm: "IN_NEGREF", inp: "GND"})
    parts.append(R("R42", "10k", "VREF", "IN_NEGREF"))
    parts.append(R("R43", "10k", "IN_NEGREF", "NEG_REF"))
    # bias for the input stages: 3.3 V * 10 / 25 = 1.32 V -> ADC mid-scale 1.68 V
    parts.append(R("R45", "15k", "3V3A", "BIAS"))
    parts.append(R("R46", "10k", "BIAS", "GND"))
    parts.append(C("C29", "1u", "BIAS", "GND"))
    # 2.5 V reference for the DACs and the output stages
    parts.append(Part("D21", "LM4040", "LM4040-2.5", {"1": "VREF", "2": "GND"}))   # 1 = cathode (+), 2 = anode
    parts.append(R("R47", "2k2", "3V3A", "VREF"))
    parts.append(C("C30", "100n", "VREF", "GND"))
    # clock inputs: 100k into an NPN inverter, 10k pull-up, Schottky clamp for negative swings
    for k, name in enumerate(("T", "X")):
        parts.append(R(f"R{50 + 2 * k}", "100k", f"{name}_CLK_IN", f"B_{name}_CLK"))
        parts.append(R(f"R{51 + 2 * k}", "10k", "3V3D", f"{name}_CLK"))
        parts.append(Part(f"Q{k + 1}", "NPN", "2N3904", {"1": "GND", "2": f"B_{name}_CLK", "3": f"{name}_CLK"}))  # E B C
        parts.append(Part(f"D{22 + k}", "BAT85", "BAT85", {"1": f"B_{name}_CLK", "2": "GND"}))  # 1 = cathode
    # gate outputs: non-inverting x2.5 (0 / 8.25 V), 1k out
    for i, (name, u, s) in enumerate(GATES):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: f"GATE_{name}"})
        parts.append(R(f"R{60 + 3 * i}", "10k", "GND", f"IN_{name}"))
        parts.append(R(f"R{61 + 3 * i}", "15k", f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{62 + 3 * i}", "1k", f"OA_{name}", name))
    out, inm, inp = SECTION[4]                     # spare section as a grounded follower
    tl["U6"].update({out: "U6_SPARE", inm: "U6_SPARE", inp: "GND"})
    # DACs: MCP4922, 3V3A supply, external 2.5 V reference, shared SCK/MOSI/LDAC
    for u, cs, a, b in (("U7", "DAC_CS1", "DAC_X1", "DAC_X2"), ("U8", "DAC_CS2", "DAC_X3", "DAC_Y")):
        parts.append(Part(u, "MCP4922", "MCP4922", {
            "1": "3V3A", "3": cs, "4": "SPI_SCK", "5": "SPI_MOSI", "8": "DAC_LDAC", "9": "3V3A",
            "10": b, "11": "VREF", "12": "GND", "13": "VREF", "14": a}))
    # DAC output stages: Vout = -(100k/24k) Vdac - (100k/47k)(-2.5 V) = 5.3 V ... -5.1 V
    for i, (name, dac, ch, u, s) in enumerate(DAC_OUTS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: "GND"})
        parts.append(R(f"R{70 + 4 * i}", "24k", f"DAC_{name}", f"IN_{name}"))
        parts.append(R(f"R{71 + 4 * i}", "47k", "NEG_REF", f"IN_{name}"))
        parts.append(R(f"R{72 + 4 * i}", "100k", f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{73 + 4 * i}", "1k", f"OA_{name}", name))
    for u in ("U3", "U4", "U5", "U6"):
        parts.append(Part(u, "TL074", "TL074", tl[u]))
    # decoupling: one pair per TL074, one per DAC
    nc = 31
    for u in ("U3", "U4", "U5", "U6"):
        parts.append(C(f"C{nc}", "100n", "+12V", "GND")); nc += 1
        parts.append(C(f"C{nc}", "100n", "GND", "-12V")); nc += 1
    parts.append(C("C39", "100n", "3V3A", "GND"))   # U7
    parts.append(C("C40", "100n", "3V3A", "GND"))   # U8
    # board-to-board headers (female sockets on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ board-to-board pins
def _pair(net):
    return net, {"GND": "GND_F", "GND_D": "GND_D_F"}.get(net, net + "_F")


HEADERS = [
    ("H1", "HDR8", [_pair(n) for n in ("CV_T_RATE", "CV_T_BIAS", "CV_T_JITTER", "CV_DEJAVU", "CV_X_SPREAD",
                                       "CV_X_BIAS", "CV_X_STEPS", "PROBE")]),
    ("H2", "HDR6", [_pair(n) for n in ("T_CLK_IN", "X_CLK_IN", "T1", "T2", "T3", "GND")]),
    ("H3", "HDR6", [_pair(n) for n in ("X1", "X2", "X3", "Y", "GND", "3V3A")]),
    ("H4", "HDR4", [_pair(n) for n in ("MUX_OUT", "MUX_S0", "MUX_S1", "MUX_S2")]),
    ("H5", "HDR7", [("SPI_SCK", "SCK_F"), ("SPI_MOSI", "MOSI_F"), ("SPI_MISO", "MISO_F"),
                    ("LED_LATCH", "LED_LATCH_F"), ("BTN_LOAD", "BTN_LOAD_F"), ("3V3D", "3V3D_F"),
                    ("GND", "GND_D_F")]),
]

# ---------------------------------------------------------------- faceplate
# ref, panel label, tip net, switch-lug net (None = left open)
JACKS = [
    ("J1", "T CLOCK", "T_CLK_IN_F", "TN_TCLK"), ("J2", "RATE", "CV_T_RATE_F", "GND_F"),
    ("J3", "BIAS", "CV_T_BIAS_F", "GND_F"), ("J4", "JITTER", "CV_T_JITTER_F", "GND_F"),
    ("J5", "DEJA VU", "CV_DEJAVU_F", "GND_F"), ("J6", "SPREAD", "CV_X_SPREAD_F", "GND_F"),
    ("J7", "BIAS", "CV_X_BIAS_F", "GND_F"), ("J8", "STEPS", "CV_X_STEPS_F", "GND_F"),
    ("J9", "T1", "T1_F", None), ("J10", "T2", "T2_F", None), ("J11", "T3", "T3_F", None),
    ("J12", "X CLOCK", "X_CLK_IN_F", "TN_XCLK"),
    ("J13", "X1", "X1_F", None), ("J14", "X2", "X2_F", None), ("J15", "X3", "X3_F", None), ("J16", "Y", "Y_F", None),
]
# ref, label, wiper net, 74HC4051 input pin, mux channel
POTS = [
    ("RV1", "RATE", "POT_T_RATE_F", "13", 0), ("RV2", "BIAS (t)", "POT_T_BIAS_F", "14", 1),
    ("RV3", "JITTER", "POT_T_JITTER_F", "15", 2), ("RV4", "DEJA VU", "POT_DEJAVU_F", "12", 3),
    ("RV5", "LENGTH", "POT_LENGTH_F", "1", 4), ("RV6", "SPREAD", "POT_X_SPREAD_F", "5", 5),
    ("RV7", "BIAS (X)", "POT_X_BIAS_F", "2", 6), ("RV8", "STEPS", "POT_X_STEPS_F", "4", 7),
]
# ref, label, firmware switch. Every button is a Thonk low-profile LED button
# (switch on pins 1+2 / 3+4, LED on pins 5 and 6, three feet on pins 7-9):
# green ones for deja vu and EXT, bipolar red/green ones for mode and range.
# The LED inside takes the place of the D1..D7 of the LEDS table; a bipolar
# LED sits between two 74HC595 lines (one 470R), red one way, green the
# other, orange by alternating them quickly.
LED_BUTTONS = {"SW1": "D1", "SW2": "D2", "SW3": "D3", "SW4": "D4", "SW5": "D5", "SW6": "D6", "SW7": "D7"}
BUTTONS = [
    ("SW1", "t deja vu", "T_DEJAVU"), ("SW2", "t mode", "T_MODE"), ("SW3", "t range", "T_RANGE"),
    ("SW4", "X deja vu", "X_DEJAVU"), ("SW5", "X mode", "X_MODE"), ("SW6", "X range", "X_RANGE"),
    ("SW7", "X ext / scale", "X_EXT"),
]
# ref, label, kind ("RG" bicolour common cathode, "G" single green), 74HC595 outputs (red, green)
LEDS = [
    ("D1", "t deja vu", "G", (None, "U9:15")), ("D2", "t mode", "RG", ("U9:1", "U9:2")),
    ("D3", "t range", "RG", ("U9:3", "U9:4")), ("D4", "X deja vu", "G", (None, "U9:5")),
    ("D5", "X mode", "RG", ("U9:6", "U9:7")), ("D6", "X range", "RG", ("U10:15", "U10:1")),
    ("D7", "X ext", "G", (None, "U10:2")),
]
HC595_PINS = {"8": "GND_D_F", "10": "3V3D_F", "11": "SCK_F", "13": "GND_D_F", "16": "3V3D_F"}   # SRCLR high, OE low
# 74HC165: 1 /PL, 2 CP, 3..6 D4..D7, 7 /Q7, 8 GND, 9 Q7, 10 DS, 11..14 D0..D3, 15 CE, 16 VCC
HC165_INPUTS = ["11", "12", "13", "14", "3", "4", "5", "6"]   # D0..D7


def faceplate_parts():
    parts = []
    nr = 9
    for ref, label, tip, tn in JACKS:
        nets = {"1": "GND_F", "3": tip}
        if tn:
            nets["2"] = tn
        parts.append(Part(ref, "JACK", "", nets, label))
        if tn and tn.startswith("TN_"):
            parts.append(R(f"R{nr}", "10k", tn, "PROBE_F")); nr += 1
    for ref, label, wiper, mpin, ch in POTS:
        parts.append(Part(ref, "POT", "B10k", {"1": "GND_F", "2": wiper, "3": "3V3A_F", "4": "GND_F", "5": "GND_F"},
                          label))
    mux = {"16": "3V3A_F", "8": "GND_F", "7": "GND_F", "6": "GND_F", "3": "MUX_OUT_F",
           "11": "MUX_S0_F", "10": "MUX_S1_F", "9": "MUX_S2_F"}
    for _, _, wiper, mpin, _ in POTS:
        mux[mpin] = wiper
    parts.append(Part("U1", "MUX", "74HC4051", mux))
    parts.append(C("C8", "100n", "3V3A_F", "GND_F"))
    # LEDs through the two 74HC595
    sr = {"U9": dict(HC595_PINS, **{"14": "MOSI_F", "12": "LED_LATCH_F", "9": "SR_CHAIN"}),
          "U10": dict(HC595_PINS, **{"14": "SR_CHAIN", "12": "LED_LATCH_F"})}
    nl = 80
    in_button = {led: sw for sw, led in LED_BUTTONS.items()}
    button_led = {}                      # SW ref -> (pin 5 net, pin 6 net) of its built-in LED
    for ref, label, kind, (red, green) in LEDS:
        nets = {"2": "GND_D_F"}
        bipolar = ref in in_button and kind == "RG"
        for colour, pin_of_led, src in (("R", "1", red), ("G", "3" if kind == "RG" else "1", green)):
            if src is None:
                continue
            u, pin = src.split(":")
            lnet = f"L_{ref}_{colour}"
            sr[u][pin] = lnet
            if bipolar and colour == "G":    # the one 470R on the red line limits both directions
                nets[pin_of_led] = lnet
                continue
            parts.append(R(f"R{nl}", "470", lnet, f"LED_{ref}_{colour}")); nl += 1
            nets[pin_of_led] = f"LED_{ref}_{colour}"
        if ref in in_button:             # the LED sits inside the button
            button_led[in_button[ref]] = (nets["1"], nets["3"]) if bipolar else (nets["1"], "GND_D_F")
        else:
            parts.append(Part(ref, "LED_RG" if kind == "RG" else "LED_G", "", nets, label))
    for u in ("U9", "U10"):
        parts.append(Part(u, "HC595", "74HC595", sr[u]))
    # buttons through the 74HC165, 10k pull-ups to 3V3D
    hc165 = {"1": "BTN_LOAD_F", "2": "SCK_F", "8": "GND_D_F", "9": "MISO_F", "10": "GND_D_F", "15": "GND_D_F",
             "16": "3V3D_F"}
    for i, (ref, label, sw) in enumerate(BUTTONS):
        net = f"BTN_{sw}_F"
        if ref in LED_BUTTONS:
            a, k = button_led[ref]
            parts.append(Part(ref, "SWLED" if k == "GND_D_F" else "SWLED_RG", "",
                              {"1": "GND_D_F", "2": "GND_D_F", "3": net, "4": net, "5": a, "6": k}, label))
        else:
            parts.append(Part(ref, "SW", "", {"1": "GND_D_F", "4": "GND_D_F", "2": net, "3": net}, label))
        parts.append(R(f"R{100 + i}", "10k", "3V3D_F", net))
        hc165[HC165_INPUTS[i]] = net
    hc165[HC165_INPUTS[7]] = "GND_D_F"
    parts.append(Part("U11", "HC165", "74HC165", hc165))
    parts.append(C("C9", "100n", "3V3D_F", "GND_D_F"))    # U9
    parts.append(C("C10", "100n", "3V3D_F", "GND_D_F"))   # U10
    parts.append(C("C11", "100n", "3V3D_F", "GND_D_F"))   # U11
    # board-to-board headers (male pins on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ------------------------------------------------------ faceplate placement
# Faceplate board: 90 x 108 mm, seen from the front, x to the right, y up,
# origin at the bottom-left corner. The 91.3 x 128.5 panel is centred on it
# (panel x = x + 0.65, panel y from the top = 118.25 - y). The arrangement
# follows Mutable's Marbles panel: DEJA VU knob top centre with RATE and
# SPREAD large beside it, BIAS knobs at the sides, LENGTH centre, JITTER
# and STEPS below, the two deja vu buttons in the top corners with their
# LEDs, small mode and range buttons with an LED each, the EXT button under
# LENGTH, CLOCK and BIAS jacks at the sides, five CV inputs in a row and
# the seven outputs (t1 t2 t3 Y X1 X2 X3) in the bottom row. These are
# footprint origins for the PCB; panel.py derives the panel holes from them.
BOARD_W, BOARD_H = 90.0, 108.0
JACK_PITCH = 12.0
PLACEMENT = {}
for k, ref in enumerate(("J9", "J10", "J11", "J16", "J13", "J14", "J15")):        # outputs
    PLACEMENT[ref] = (9 + k * JACK_PITCH, 7.25, 0)
for k, ref in enumerate(("J1", "J2", "J4", "J5", "J8", "J6", "J12")):           # clocks and CV inputs
    PLACEMENT[ref] = (9 + k * JACK_PITCH, 21.85, 0)
PLACEMENT["J3"], PLACEMENT["J7"] = (9, 36.25, 0), (81, 36.25, 0)              # BIAS CV inputs
POT_XY = {"RV1": (22.65, 82.75), "RV6": (67.35, 82.75), "RV4": (45, 97.55),    # RATE, SPREAD, DEJA VU
          "RV2": (8.85, 59.95), "RV7": (81.15, 59.95), "RV5": (45, 66.55),     # BIAS t, BIAS X, LENGTH
          "RV3": (31.05, 44.75), "RV8": (58.95, 44.75)}                        # JITTER, STEPS
for ref, (x, y) in POT_XY.items():
    PLACEMENT[ref] = (x, y, 90)
BUTTON_XY = {"SW1": (15.85, 100.65), "SW4": (74.15, 100.65),                   # t / X deja vu (green)
             "SW2": (6.85, 78.25), "SW5": (83.15, 78.25),                      # t / X mode (bipolar)
             "SW3": (25.95, 58.25), "SW6": (64.05, 58.25),                     # t / X range (bipolar)
             "SW7": (45, 51.45)}                                               # X ext (green)
for ref, (x, y) in BUTTON_XY.items():
    PLACEMENT[ref] = (x, y, 0)
# every LED is inside its button, so no LED placements


def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        nets = nets_of(parts)
        print(f"{name}: {len(parts)} parts, {len(nets)} nets")
        for n in sorted(nets):
            if len(nets[n]) < 2:
                print("  single-pin net:", n, nets[n])
    # every header pin must land on a real net on both sides
    mb, fb = nets_of(main_board_parts()), nets_of(faceplate_parts())
    for ref, kind, pins in HEADERS:
        for a, b in pins:
            if len(mb[a]) < 2 or len(fb[b]) < 2:
                print("  header net not used on both boards:", a, b)
