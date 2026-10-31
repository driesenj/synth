"""Ringsy: a Mutable Instruments Rings clone on a Daisy Seed, 14HP Eurorack. The whole circuit as one
netlist, split over two boards, and the panel placement the panel files are drawn from.

Panel approved as drawn (2026-10-31). The other choices the draft left open are taken at the proposed
defaults: Thonk LED buttons, Rings' own ODD / EVEN output stage (its analog EVEN -> ODD normal), two
boards, and a Seed with the PCM3060 codec (rev 7 / Seed 2 DFM, what Electro-Smith sells now), which
only sets one resistor per output (OUT_STAGE["Rin"]).

Main board (MB): Daisy Seed on Rob Heel's seed_power_opamps breakout (power; its audio input stage takes
IN through J5; its output op-amps stay fitted and unused), two TL074: six CV input stages (Plaitsy's)
and Rings' output stage for ODD and EVEN, the STRUM transistor, the probe clamps, two bias dividers,
the LED resistors.
Faceplate board (FB): 10 Thonkiconn jacks, 10 Alpha pots (FREQUENCY and STRUCTURE straight to the
Seed, the other eight through a 74HC4051), 2 Thonk LED buttons, 2 bicolour LEDs, the jack-lug
networks (FM normal, probe resistors, the IN lug load).

Sources: pichenettes/eurorack rings/ (hardware_design/panel/rings.ai, the rings_v30 schematic, the
firmware). Designators follow Rings' where it has them: J1-J10 are its jacks in its order.

Net naming
  CV_*        jack tip of a CV input (FB: CV_*_F) -> MB input stage; IN_*/OA_* summing node / op-amp
              output; ADC_* the Seed pin after the 1k
  TN_*_F      jack switch lugs (the normals): TN_FM_F 6k8 to GND_F (Rings' +0.1 V), TN_STRUM_F /
              TN_VOCT_F / TN_IN_F the probe through 100k / 470k / 1M (TN_IN_F also 43k to GND_F),
              TN_EVEN the EVEN lug, into ODD's summing node on the MB
  PROBE       Seed D14, the normalization probe, clamped on the MB, out to the lug resistors
  STRUM_IN    STRUM jack tip -> 100k -> B_STRUM (2N3904 base); STRUM the collector, Seed D9, active low
  IN          IN jack tip -> the breakout's J5 input stage -> Seed AIN1
  AOUT_*      Seed AOUT1 / AOUT2 -> 10u -> AC_* -> Rin -> IN_* (inverting) -> OA_* -> 1k -> ODD / EVEN
  POT_*       FREQUENCY and STRUCTURE wipers, straight to ADC pins; the other eight (POT_*_F, ATT_*_F)
              into the mux, MUX_OUT / MUX_S0..2 cross to the MB
  BTN_*       buttons (Seed internal pull-ups); BTN_LED_* their LEDs, LED_POLY_R/G and LED_MODEL_R/G
              the bicolour LEDs' anodes; *_IO the Seed side of each LED resistor
  Nets that cross the board-to-board headers carry the same name on both boards, with _F on the
  faceplate side (GND -> GND_F for the jacks and pots, GND -> GND_D_F for the buttons and LEDs).
  Every faceplate net ends in _F.

Panel placement: designed in the panel frame (from the top-left, y down, mm) as PANEL_XY, the rows
measured off rings.ai; stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it (sleeve pad up)
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm from it, away from the pins
  button  Thonk low-profile LED button, the cap centre
  LED     3 mm, the lens centre

Run from rings/hardware/tools:  python circuit.py  (netlist check, circuit values, front check)
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


def D(ref, kind, value, anode, cathode, label=""):
    """Through-hole diodes (DO-35): pin 1 = cathode (the band), pin 2 = anode, as on Plaitsy."""
    return Part(ref, kind, value, {"1": cathode, "2": anode}, label)


def NPN(ref, e, b, c, label=""):
    """2N3904 (TO-92). Pins named by function, and the footprint's pads carry the same names, so
    nothing can swap them (Senay's rule)."""
    return Part(ref, "NPN", "2N3904", {"E": e, "B": b, "C": c}, label)


GND, VP, VN = "GND", "+12V", "-12V"

# --------------------------------------------------------------- Daisy Seed
# Seed pin number -> (libDaisy name, net). Pins with no net are left open.
# The six CV inputs on A0-A5, the two direct pots on A6 / A9, the pot mux on A10 with its address on
# D26-D28 (Plaitsy's pins), the buttons on D0 / D1 (internal pull-ups) and their LEDs on D2 / D3, the
# bicolour LEDs on D4-D7, STRUM on D9, the probe on D14. ODD and EVEN leave from the Seed's own audio
# outputs into Rings' output stage; IN arrives through the breakout's J5 input stage.
SEED = {
    "1": ("D0", "BTN_POLY"), "2": ("D1", "BTN_MODEL"), "3": ("D2", "BTN_LED_POLY_IO"),
    "4": ("D3", "BTN_LED_MODEL_IO"), "5": ("D4", "LED_POLY_R_IO"), "6": ("D5", "LED_POLY_G_IO"),
    "7": ("D6", "LED_MODEL_R_IO"), "8": ("D7", "LED_MODEL_G_IO"),
    "9": ("D8", None), "10": ("D9", "STRUM"), "11": ("D10", None), "12": ("D11", None),
    "13": ("D12", None), "14": ("D13", None), "15": ("D14", "PROBE"),
    "16": ("AIN1", None), "17": ("AIN2", None), "18": ("AOUT1", "AOUT_ODD"), "19": ("AOUT2", "AOUT_EVEN"),
    "20": ("AGND", GND), "21": ("3V3A", "3V3A"),
    "22": ("D15/A0", "ADC_FM"), "23": ("D16/A1", "ADC_STRUCTURE"), "24": ("D17/A2", "ADC_BRIGHTNESS"),
    "25": ("D18/A3", "ADC_DAMPING"), "26": ("D19/A4", "ADC_POSITION"), "27": ("D20/A5", "ADC_VOCT"),
    "28": ("D21/A6", "POT_FREQUENCY"), "29": ("D22/A7", None), "30": ("D23/A8", None),
    "31": ("D24/A9", "POT_STRUCTURE"), "32": ("D25/A10", "MUX_OUT"),
    "33": ("D26", "MUX_S0"), "34": ("D27", "MUX_S1"), "35": ("D28/A11", "MUX_S2"),
    "36": ("D29", None), "37": ("D30", None),
    "38": ("3V3D", "3V3D"), "39": ("VIN", None), "40": ("DGND", GND),
    # breakout headers, numbered as on Rob Heel's board; J5 is the buffered audio input (Side FXy's use)
    "J1-1": ("GND", GND), "J1-2": ("-12V", VN), "J1-3": ("-12V", VN), "J1-4": ("-12V", VN),
    "J3-1": ("GND", GND), "J3-2": ("+12V", VP), "J3-3": ("+12V", VP), "J3-4": ("+12V", VP),
    "J4-1": ("AOUT1", None), "J4-2": ("GND", GND), "J4-3": ("AOUT2", None), "J4-4": ("GND", GND),
    "J5-1": ("AIN1", "IN"), "J5-2": ("GND", GND), "J5-3": ("AIN2", None), "J5-4": ("GND", GND),
}

# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
# Plaitsy's CV input stage, inverting round a bias from 3V3A: the wide channels (gain -0.13) put +-12 V
# on 0.10..3.22 V, V/OCT (gain -0.33) reads -2.9..+7.1 V with Schottky clamps beyond that.
# name, op-amp, section, Rf, Cf, bias
CV_CHANNELS = [
    ("FM", "U3", 1, "13k", "1n", "BIAS_A"), ("STRUCTURE", "U3", 2, "13k", "1n", "BIAS_A"),
    ("BRIGHTNESS", "U3", 3, "13k", "1n", "BIAS_A"), ("DAMPING", "U3", 4, "13k", "1n", "BIAS_A"),
    ("POSITION", "U4", 1, "13k", "1n", "BIAS_A"), ("VOCT", "U4", 2, "33k", "1n", "BIAS_V"),
]
# Rings' output stage (sheet 4: 10u, 47k to GND, 6.8k, 47k || 18p, 1k; EVEN's lug through 47k into
# ODD's summing node), every resistor scaled up about 2x so the stage loads the Seed's outputs by
# 17k: the breakout's own output op-amps hang on the same pins. Rin sets the gain: 20k for the
# PCM3060 (about 1.8 Vpk full scale -> +-9.0 V), 15k for a rev 5 Seed's WM8731 (1.41 Vpk -> +-9.4 V);
# Rings: +-9.8 V. Through-hole, so it is picked at the build, after measuring (docs/design.md).
OUTPUTS = [("ODD", "U4", 3), ("EVEN", "U4", 4)]
OUT_STAGE = {"Cin": "10u NP", "Rdc": "100k", "Rin": "20k", "Rf": "100k", "Cf": "10p", "Rs": "1k", "Rnorm": "100k"}
# LED resistors (MB, Seed side): Thonk LED buttons and the 3 mm red/green bicolour LEDs
BUTTON_COLOUR = "white"
LED_R = {"button": "150", "bicolour": "330"}


def main_board_parts():
    parts = [Part("U2", "SEED", "Daisy Seed + seed_power_opamps",
                  {pin: net for pin, (name, net) in SEED.items() if net})]
    tl = {u: {"4": VP, "11": VN} for u in ("U3", "U4")}
    for i, (name, u, s, rf, cf, bias) in enumerate(CV_CHANNELS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: bias})
        parts.append(R(f"R{21 + 3 * i}", "100k", f"CV_{name}", f"IN_{name}"))
        parts.append(R(f"R{22 + 3 * i}", rf, f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{23 + 3 * i}", "1k", f"OA_{name}", f"ADC_{name}"))
        parts.append(C(f"C{21 + i}", cf, f"IN_{name}", f"OA_{name}"))
    # bias A = 3.3 V * 12 / 27 = 1.467 V (wide channels), bias V = 3.3 V * 15 / 28 = 1.768 V (V/OCT)
    parts.append(R("R40", "15k", "3V3A", "BIAS_A"))
    parts.append(R("R41", "12k", "BIAS_A", GND))
    parts.append(C("C27", "1u", "BIAS_A", GND))
    parts.append(R("R42", "13k", "3V3A", "BIAS_V"))
    parts.append(R("R43", "15k", "BIAS_V", GND))
    parts.append(C("C28", "1u", "BIAS_V", GND))
    # V/OCT clamps: the ADC pin held between GND and 3V3A for pitch CV outside -2.9..+7.1 V
    parts.append(D("D3", "BAT85", "BAT85", "ADC_VOCT", "3V3A"))
    parts.append(D("D4", "BAT85", "BAT85", GND, "ADC_VOCT"))
    # ODD and EVEN: AC-coupled, inverting, 1k out; an unpatched EVEN jack's lug feeds EVEN into ODD
    o = OUT_STAGE
    for k, (name, u, s) in enumerate(OUTPUTS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: GND})
        parts.append(C(f"C{29 + k}", o["Cin"], f"AOUT_{name}", f"AC_{name}"))
        parts.append(R(f"R{44 + 4 * k}", o["Rdc"], f"AC_{name}", GND))
        parts.append(R(f"R{45 + 4 * k}", o["Rin"], f"AC_{name}", f"IN_{name}"))
        parts.append(R(f"R{46 + 4 * k}", o["Rf"], f"IN_{name}", f"OA_{name}"))
        parts.append(C(f"C{31 + k}", o["Cf"], f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{47 + 4 * k}", o["Rs"], f"OA_{name}", name))
    parts.append(R("R52", o["Rnorm"], "TN_EVEN", "IN_ODD"))
    for u in ("U3", "U4"):
        parts.append(Part(u, "TL074", "TL074", tl[u]))
    # STRUM: Rings' transistor (a gate or the probe pulls the pin low), plus a 1N4148 so a negative
    # input cannot reverse-break the base-emitter junction
    parts.append(R("R53", "100k", "STRUM_IN", "B_STRUM"))
    parts.append(NPN("Q1", GND, "B_STRUM", "STRUM"))
    parts.append(D("D5", "1N4148", "1N4148", GND, "B_STRUM"))
    parts.append(R("R54", "10k", "3V3D", "STRUM"))
    # the probe, clamped to the rails at the Seed pin (Rings: a BAT54S)
    parts.append(D("D6", "BAT85", "BAT85", "PROBE", "3V3D"))
    parts.append(D("D7", "BAT85", "BAT85", GND, "PROBE"))
    # LEDs: Seed GPIO -> resistor -> header -> LED on the faceplate -> GND_D_F
    for i, net in enumerate(("BTN_LED_POLY", "BTN_LED_MODEL", "LED_POLY_R", "LED_POLY_G", "LED_MODEL_R",
                             "LED_MODEL_G")):
        parts.append(R(f"R{55 + i}", LED_R["button" if net.startswith("BTN") else "bicolour"], f"{net}_IO", net))
    # supply decoupling, one pair per TL074
    for k, u in enumerate(("U3", "U4")):
        parts.append(C(f"C{33 + 2 * k}", "100n", VP, GND))
        parts.append(C(f"C{34 + 2 * k}", "100n", GND, VN))
    # board-to-board headers (female sockets on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ board-to-board pins
def _pair(net):
    return net, {"GND": "GND_F"}.get(net, net + "_F")


def _logic(net):
    """A logic-side pin: the faceplate's digital ground is GND_D_F."""
    return (net, "GND_D_F") if net == "GND" else _pair(net)


# Split by what they carry: the six CV inputs, the other jacks with the probe, the pots, the buttons
# and LEDs. The probe sits two pins away from IN, with a ground between. Pin order is a first guess;
# placement sorts it.
HEADERS = [
    ("H1", "HDR6", [_pair(f"CV_{n}") for n in ("BRIGHTNESS", "FM", "DAMPING", "STRUCTURE", "POSITION", "VOCT")]),
    ("H2", "HDR7", [_pair(n) for n in ("PROBE", "STRUM_IN", GND, "IN", "ODD", "TN_EVEN", "EVEN")]),
    ("H3", "HDR8", [_pair(n) for n in ("3V3A", GND, "POT_FREQUENCY", "POT_STRUCTURE", "MUX_OUT", "MUX_S0",
                                       "MUX_S1", "MUX_S2")]),
    ("H4", "HDR9", [_logic(n) for n in (GND, "BTN_POLY", "BTN_LED_POLY", "LED_POLY_R", "LED_POLY_G",
                                        "LED_MODEL_G", "LED_MODEL_R", "BTN_LED_MODEL", "BTN_MODEL")]),
]


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ---------------------------------------------------------------- faceplate
HP = 14
PANEL_W, PANEL_H = 70.8, 128.5          # 14HP; Rings' own panel is 70.80 x 128.50
BOARD_W, BOARD_H = 69.6, 108.0          # 0.6 mm in from each side, like Side FXy
BOARD_X0 = (PANEL_W - BOARD_W) / 2
BOARD_Y0 = (PANEL_H - BOARD_H) / 2
JACK_BARREL, POT_SHAFT = -0.78, 4.0

# ref, panel label, role, tip net, switch-lug net. Rings' order: J1-J5 the CV inputs as their columns
# run left to right. Rings' normals: FREQUENCY reads +0.1 V unpatched (the attenuverter becomes a
# +-1 semitone fine tune), the probe goes into STRUM, V/OCT and IN, the other CV lugs are grounded,
# and EVEN's lug feeds ODD (in the output stage); ODD's lug stays open (Rings' SJ1, open, not copied).
JACKS = [
    ("J1", "BRIGHTNESS CV", "cv in", "CV_BRIGHTNESS_F", "GND_F"),
    ("J2", "FREQUENCY CV", "cv in, FM", "CV_FM_F", "TN_FM_F"),
    ("J3", "DAMPING CV", "cv in", "CV_DAMPING_F", "GND_F"),
    ("J4", "STRUCTURE CV", "cv in", "CV_STRUCTURE_F", "GND_F"),
    ("J5", "POSITION CV", "cv in", "CV_POSITION_F", "GND_F"),
    ("J6", "STRUM", "trigger in", "STRUM_IN_F", "TN_STRUM_F"),
    ("J7", "V/OCT", "cv in, pitch", "CV_VOCT_F", "TN_VOCT_F"),
    ("J8", "IN", "audio in", "IN_F", "TN_IN_F"),
    ("J9", "ODD", "audio out", "ODD_F", None),
    ("J10", "EVEN", "audio out", "EVEN_F", "TN_EVEN_F"),
]
# The lug networks, next to their jacks: ref, value, net a, net b.
# - FM: Rings ties the lug to 3V3A through 3.3M into a summing node at 0 V, so the tip sits at +0.097 V.
#   Here the summing node sits at BIAS_A (1.467 V), and the tip would follow it to +1.5 V through any
#   large resistor; tied to GND through 6k8 instead, it divides BIAS_A down to +0.093 V.
# - STRUM, V/OCT: Rings' probe resistors. IN: Rings' 1M, and 43k to ground in place of Rings' 36k + 6.8k
#   input divider, so the probe's level does not hang on the breakout's input impedance.
LUG_PARTS = [
    ("R1", "6k8", "TN_FM_F", "GND_F"),
    ("R2", "100k", "TN_STRUM_F", "PROBE_F"),
    ("R3", "470k", "TN_VOCT_F", "PROBE_F"),
    ("R4", "1M", "TN_IN_F", "PROBE_F"),
    ("R5", "43k", "TN_IN_F", "GND_F"),
]
# ref, label, size (big / mid / att). Alpha 9 mm B10k throughout.
POTS = [
    ("RV1", "FREQUENCY", "big"), ("RV2", "STRUCTURE", "big"),
    ("RV3", "BRIGHTNESS", "mid"), ("RV4", "DAMPING", "mid"), ("RV5", "POSITION", "mid"),
    ("RV6", "BRIGHTNESS att.", "att"), ("RV7", "FREQUENCY att.", "att"), ("RV8", "DAMPING att.", "att"),
    ("RV9", "STRUCTURE att.", "att"), ("RV10", "POSITION att.", "att"),
]
# wiper nets; FREQUENCY and STRUCTURE go straight to the Seed (as on Rings), the rest into the mux
POT_WIPER = {
    "RV1": "POT_FREQUENCY_F", "RV2": "POT_STRUCTURE_F",
    "RV3": "POT_BRIGHTNESS_F", "RV4": "POT_DAMPING_F", "RV5": "POT_POSITION_F",
    "RV6": "ATT_BRIGHTNESS_F", "RV7": "ATT_FM_F", "RV8": "ATT_DAMPING_F", "RV9": "ATT_STRUCTURE_F",
    "RV10": "ATT_POSITION_F",
}
# 74HC4051 channel -> pin; the channel of each muxed pot (a first guess: placement sorts it, and the
# firmware reads the pots by this table, not in panel order)
MUX_PIN = {0: "13", 1: "14", 2: "15", 3: "12", 4: "1", 5: "5", 6: "2", 7: "4"}
MUX_CHANNEL = {"RV3": 0, "RV4": 1, "RV5": 2, "RV6": 3, "RV7": 4, "RV8": 5, "RV9": 6, "RV10": 7}
# ref, label, the firmware's name. Thonk low-profile LED buttons (5.5 mm cap; clip their three feet);
# Rings' own buttons have no LED, these get a Seed GPIO each for the firmware to use or not.
BUTTONS = [("SW1", "polyphony", "POLY"), ("SW2", "resonator model", "MODEL")]
# ref, label, name: 3 mm red/green bicolour, common cathode (1 red anode, 2 cathode, 3 green anode);
# green / yellow (both) / red as on Rings, which PWMs them from its 1 kHz tick
LEDS = [("D1", "polyphony 1 / 2 / 4", "POLY"), ("D2", "model", "MODEL")]


def faceplate_parts():
    parts = []
    for ref, label, role, tip, lug in JACKS:
        nets = {"1": "GND_F", "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, value, a, b in LUG_PARTS:
        parts.append(R(ref, value, a, b))
    for ref, label, size in POTS:
        parts.append(Part(ref, "POT", "B10k", {"1": "GND_F", "2": POT_WIPER[ref], "3": "3V3A_F", "4": "GND_F",
                                               "5": "GND_F"}, label))
    mux = {"16": "3V3A_F", "8": "GND_F", "7": "GND_F", "6": "GND_F", "3": "MUX_OUT_F",
           "11": "MUX_S0_F", "10": "MUX_S1_F", "9": "MUX_S2_F"}
    for ref, ch in MUX_CHANNEL.items():
        mux[MUX_PIN[ch]] = POT_WIPER[ref]
    parts.append(Part("U1", "MUX", "74HC4051", mux))
    parts.append(C("C1", "100n", "3V3A_F", "GND_F"))
    # buttons: contacts 1+2 to GND_D_F, 3+4 to the Seed (internal pull-up); the LED on pins 5 / 6
    for ref, label, name in BUTTONS:
        parts.append(Part(ref, "SWLED", BUTTON_COLOUR, {"1": "GND_D_F", "2": "GND_D_F", "3": f"BTN_{name}_F",
                                                        "4": f"BTN_{name}_F", "5": f"BTN_LED_{name}_F",
                                                        "6": "GND_D_F"}, label))
    for ref, label, name in LEDS:
        parts.append(Part(ref, "LED_RG", "", {"1": f"LED_{name}_R_F", "2": "GND_D_F", "3": f"LED_{name}_G_F"},
                          label))
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ faceplate placement
# What the user sees, panel mm from the top-left (y down). Rings' rows exactly; the five columns 13 mm
# apart, centred (Rings: 9.41 ... 61.43, 13.005 apart), the rest symmetric about the centre line.
CX = PANEL_W / 2
COL_X = [round(CX + 13.0 * k, 2) for k in (-2, -1, 0, 1, 2)]
ROW_Y = {"buttons": 16.12, "big": 33.43, "mid": 60.63, "att": 80.63, "cv": 96.48, "bottom": 111.08}
PANEL_XY = {
    "SW1": (7.5, ROW_Y["buttons"]), "SW2": (PANEL_W - 7.5, ROW_Y["buttons"]),
    "D1": (round(CX - 21.6, 2), ROW_Y["buttons"]), "D2": (round(CX + 21.6, 2), ROW_Y["buttons"]),
    "RV1": (round(CX - 16.5, 2), ROW_Y["big"]), "RV2": (round(CX + 16.5, 2), ROW_Y["big"]),
    "RV3": (round(CX - 23.8, 2), ROW_Y["mid"]), "RV4": (CX, ROW_Y["mid"]), "RV5": (round(CX + 23.8, 2), ROW_Y["mid"]),
}
for k, ref in enumerate(("RV6", "RV7", "RV8", "RV9", "RV10")):
    PANEL_XY[ref] = (COL_X[k], ROW_Y["att"])
for k, ref in enumerate(("J1", "J2", "J3", "J4", "J5")):
    PANEL_XY[ref] = (COL_X[k], ROW_Y["cv"])
for k, ref in enumerate(("J6", "J7", "J8", "J9", "J10")):
    PANEL_XY[ref] = (COL_X[k], ROW_Y["bottom"])

# Which way a pot's pin row lies from its shaft (front view, unit vector). The big and medium knobs
# point theirs left (-x), as on Marblesy; the attenuverters up, towards the medium knobs: at 13 mm pitch
# their housings (9.5 mm wide across the pins) only fit side by side with the pins up or down, the
# leftmost one's pins would sit 1.3 mm from the board edge pointing left, and pointing down they land
# 1.9 mm from the CV jacks' sleeve pads.
POT_PINS = {ref: (0, 1) for ref in ("RV6", "RV7", "RV8", "RV9", "RV10")}
POT_ANGLE = {(-1, 0): 90, (0, 1): 180, (0, -1): 0}   # PLACEMENT's angle: 90 = pins towards -x


def pot_pins(ref):
    return POT_PINS.get(ref, (-1, 0))


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (from the bottom-left, y up)."""
    return px - BOARD_X0, PANEL_H - BOARD_Y0 - py


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return BOARD_X0 + bx, PANEL_H - (BOARD_Y0 + by)


PLACEMENT = {}
for ref, (px, py) in PANEL_XY.items():
    x, y = board_xy(px, py)
    if ref.startswith("J"):
        PLACEMENT[ref] = (round(x, 2), round(y - JACK_BARREL, 2), 0)
    elif ref.startswith("RV"):
        ux, uy = pot_pins(ref)
        PLACEMENT[ref] = (round(x + POT_SHAFT * ux, 2), round(y + POT_SHAFT * uy, 2), POT_ANGLE[(ux, uy)])
    else:
        PLACEMENT[ref] = (round(x, 2), round(y, 2), 0)


# ------------------------------------------------------------ netlist check
def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets, designators used twice, header pins not used on both boards,
    nets on both boards, faceplate nets without _F, panel parts and PLACEMENT out of step."""
    bad = []
    mb, fb = main_board_parts(), faceplate_parts()
    for name, parts in (("main board", mb), ("faceplate", fb)):
        nets = nets_of(parts)
        for n in sorted(nets):
            if len(nets[n]) < 2:
                bad.append(f"{name}: single-pin net {n} {nets[n]}")
    refs = collections.Counter(p.ref for p in mb + fb)
    bad += [f"{r} used {c} times" for r, c in refs.items() if c > 1]
    mbn, fbn = nets_of(mb), nets_of(fb)
    for ref, kind, pins in HEADERS:
        if len(pins) != int(kind[3:]):
            bad.append(f"{ref}: {len(pins)} pins on a {kind}")
        for a, b in pins:
            if len(mbn[a]) < 2 or len(fbn[b]) < 2:
                bad.append(f"{ref}: header net not used on both boards: {a} / {b}")
    bad += [f"net {n} on both boards" for n in set(mbn) & set(fbn)]
    bad += [f"faceplate net {n} lacks the _F suffix" for n in fbn if not n.endswith("_F")]
    panel = {p.ref for p in fb if p.kind in ("JACK", "POT", "SWLED", "LED_RG")}
    bad += [f"{r} has no PLACEMENT" for r in sorted(panel - set(PLACEMENT))]
    bad += [f"PLACEMENT {r} is not a faceplate part" for r in sorted(set(PLACEMENT) - panel)]
    return bad


# ------------------------------------------------------------ circuit values
# Datasheet figures the checks use (typical values unless noted)
V3A = 3.3                    # 3V3A, 3V3D
VBE = 0.65                   # 2N3904 base-emitter at tens of uA
TL074_SWING = 10.0           # TL074 output swing on +-12 V into 10k and more, both ways (conservative)
ADC_MARGIN = 0.05            # keep readings this far inside 0..3V3A
LED_VF = {"red": 1.9, "green": 2.1, "white": 2.8}     # at a few mA
GPIO_RON = 40.0              # STM32H7 push-pull output at 3.3 V, a few mA, roughly
# Codec full scale at the Seed's audio output pins, volts peak. The PCM3060's is not in Electro-Smith's
# datasheet: 3.6 Vpp is the Seed's stated audio level and the PCM3060's single-ended 0.8 VCC at 4.5 V;
# measure it on the actual Seed before fitting Rin.
CODEC_FS = {"PCM3060 (rev 7, Seed 2 DFM)": 1.8, "WM8731 (rev 5)": 1.41}
CODEC = "PCM3060 (rev 7, Seed 2 DFM)"
# The breakout's input impedance at J5 is not documented; the probe level is checked over this range.
BREAKOUT_IN_Z = (47e3, 100e3, 1e9)
# Rings v3.0, for comparison (rings_v30 sheets 2-4)
RINGS = {
    "fm_normal": 3.3 * 100e3 / (3.3e6 + 100e3),            # tip voltage, unpatched FREQUENCY CV
    "voct_probe": 3.3 * 100e3 / (470e3 + 100e3),           # tip swing, unpatched V/OCT
    "in_fs": 10.58,                                       # IN: 36k / 6.8k into the WM8731 at -1.5 dB
    "in_probe": 3.3 * 42.8e3 / (1e6 + 42.8e3),             # tip swing, unpatched IN
    "out_fs": 47 / 6.8 * 1.41,                             # ODD / EVEN at codec full scale
    "out_norm": 47 / (47 + 1),                             # EVEN -> ODD, relative to ODD's own gain
    "voct_range": (-1.47, 5.56),
    "voct_stage": (2.611, 0.47),                           # V_adc = 2.611 - 0.47 V_in (47k, 180k from -10 V)
    "voct_threshold": (0.70, 0.80),                        # CalibrateHigh() accepts the probe threshold here
}
DETECT = (50, 1500)          # Rings' IN detector: probe-following samples between these (of 32768)


def value(v):
    """'24k' -> 24000.0, '6k8' -> 6800.0, '100n' -> 1e-7, '10u NP' -> 1e-5."""
    v = v.split()[0]
    for m, f in {"R": 1, "k": 1e3, "M": 1e6, "u": 1e-6, "n": 1e-9, "p": 1e-12}.items():
        if m in v:
            a, _, b = v.partition(m)
            return float(f"{a or 0}.{b or 0}") * f
    return float(v)


def r_between(parts, a, b):
    """The value of the one resistor joining nets a and b (raises if there is none or more than one)."""
    found = [p for p in parts if p.kind == "R" and set(p.nets.values()) == {a, b}]
    if len(found) != 1:
        raise LookupError(f"{len(found)} resistors between {a} and {b}")
    return value(found[0].value)


def _par(*rs):
    return 1 / sum(1 / r for r in rs)


def circuit_check():
    """Each stage's numbers, from the resistor values the netlist actually has (a mis-wired resistor
    makes the lookup fail). Returns (report lines, problems)."""
    mb, fb = main_board_parts(), faceplate_parts()
    lines, bad = [], []
    bias = {b: V3A * r_between(mb, b, GND) / (r_between(mb, "3V3A", b) + r_between(mb, b, GND))
            for b in ("BIAS_A", "BIAS_V")}
    stage = {}
    for name, u, s, rf, cf, b in CV_CHANNELS:
        rin = r_between(mb, f"CV_{name}", f"IN_{name}")
        g = r_between(mb, f"IN_{name}", f"OA_{name}") / rin
        stage[name] = (g, bias[b], rin)
        lo, hi = (bias[b] * (1 + g) - V3A) / g, bias[b] * (1 + g) / g
        lines.append(f"CV {name}: V_adc = {bias[b] * (1 + g):.3f} - {g:.3f} V_in, reads {lo:+.1f} .. {hi:+.1f} V")
        if name != "VOCT" and not (lo < -12 + ADC_MARGIN / g and hi > 12 - ADC_MARGIN / g):
            bad.append(f"CV {name}: +-12 V does not stay inside the ADC range")
    lo, hi = (bias["BIAS_V"] * (1 + stage["VOCT"][0]) - V3A) / stage["VOCT"][0], \
        bias["BIAS_V"] * (1 + stage["VOCT"][0]) / stage["VOCT"][0]
    r_lo, r_hi = RINGS["voct_range"]
    lines.append(f"V/OCT: {V3A / 65536 / stage['VOCT'][0] * 1200:.2f} cents per 16-bit step; Rings reads "
                 f"{r_lo:+.1f} .. {r_hi:+.1f} V")
    if not (lo < r_lo and hi > r_hi):
        bad.append("V/OCT: the range does not cover Rings'")

    def tip(name, lug_to):
        """Unpatched tip voltage of a CV input whose lug has resistors to the given sources {V: R}."""
        g, b, rin = stage[name]
        num = b / rin + sum(v / r for v, r in lug_to.items())
        return num / (1 / rin + sum(1 / r for r in lug_to.values()))

    # FREQUENCY CV normal: the fine tune
    fm = tip("FM", {0.0: r_between(fb, "TN_FM_F", "GND_F")})
    lines.append(f"FM normal: tip {fm:+.4f} V unpatched (Rings {RINGS['fm_normal']:+.4f} V): the attenuverter "
                 f"spans +-{fm / RINGS['fm_normal']:.2f} of Rings' fine-tune range")
    if abs(fm / RINGS["fm_normal"] - 1) > 0.1:
        bad.append(f"FM normal {fm:.3f} V, more than 10 % off Rings'")
    # V/OCT probe: Rings' detector looks at the swing only
    rp = r_between(fb, "TN_VOCT_F", "PROBE_F")
    v0, v1 = tip("VOCT", {0.0: rp}), tip("VOCT", {V3A: rp})
    g, b, _ = stage["VOCT"]
    lines.append(f"V/OCT unpatched: tip {v0:+.3f} / {v1:+.3f} V with the probe low / high, swing {v1 - v0:.3f} V "
                 f"(Rings {RINGS['voct_probe']:.3f} V); ADC {b * (1 + g) - g * v0:.2f} / {b * (1 + g) - g * v1:.2f} V")
    if abs((v1 - v0) / RINGS["voct_probe"] - 1) > 0.1:
        bad.append("V/OCT probe swing more than 10 % off Rings'")
    # Rings' detector compares the reading, in its own ADC units, with a threshold its calibration sets
    # half-way between the probe-low and probe-high readings and accepts only inside a window
    off, gr = RINGS["voct_stage"]
    th = ((off - gr * v0) + (off - gr * v1)) / 2 / V3A
    t_lo, t_hi = RINGS["voct_threshold"]
    lines.append(f"V/OCT detection threshold {th:.3f} in Rings' units (Rings: {(off - gr * RINGS['voct_probe'] / 2) / V3A:.3f};"
                 f" its calibration accepts {t_lo:.2f}..{t_hi:.2f}: the port moves that window)")
    if not ADC_MARGIN < b * (1 + g) - g * v1 < b * (1 + g) - g * v0 < V3A - ADC_MARGIN:
        bad.append("V/OCT unpatched reading outside the ADC range")
    # IN probe: what Rings' detector would count, over the breakout's possible input impedance
    rp, rl = r_between(fb, "TN_IN_F", "PROBE_F"), r_between(fb, "TN_IN_F", "GND_F")
    counts = []
    for z in BREAKOUT_IN_Z:
        load = _par(rl, z)
        v = V3A * load / (rp + load)
        counts.append(v / RINGS["in_fs"] * 32768)
    lines.append("IN probe: " + ", ".join(f"{c:.0f}" for c in counts) + " counts with the breakout's input at "
                 + ", ".join("open" if z > 1e8 else f"{z / 1e3:.0f}k" for z in BREAKOUT_IN_Z)
                 + f" (Rings {RINGS['in_probe'] / RINGS['in_fs'] * 32768:.0f}; detector {DETECT[0]}..{DETECT[1]})")
    if not all(DETECT[0] * 2 < c < DETECT[1] / 2 for c in counts):
        bad.append("IN probe level too close to the detector's limits")
    # STRUM: the base current the probe gives, and a 5 V gate
    rb, rp, rc = r_between(mb, "STRUM_IN", "B_STRUM"), r_between(fb, "TN_STRUM_F", "PROBE_F"), \
        r_between(mb, "3V3D", "STRUM")
    ic = V3A / rc
    for what, ib in (("probe high", (V3A - VBE) / (rb + rp)), ("5 V gate", (5.0 - VBE) / rb)):
        lines.append(f"STRUM, {what}: Ib {ib * 1e6:.1f} uA, Ic {ic * 1e3:.2f} mA, needs hFE > {ic / ib:.0f}")
        if ic / ib > 30:
            bad.append(f"STRUM, {what}: needs hFE {ic / ib:.0f}")
    # outputs
    o = {k: value(v) for k, v in OUT_STAGE.items()}
    for name, u, s in OUTPUTS:
        g = r_between(mb, f"IN_{name}", f"OA_{name}") / r_between(mb, f"AC_{name}", f"IN_{name}")
        load = _par(r_between(mb, f"AC_{name}", f"IN_{name}"), r_between(mb, f"AC_{name}", GND))
        fc = 1 / (2 * math.pi * r_between(mb, f"IN_{name}", f"OA_{name}") * o["Cf"])
        lines.append(f"{name}: gain -{g:.2f}, " + ", ".join(f"{c} +-{g * fs:.1f} V" for c, fs in CODEC_FS.items())
                     + f" at full scale (Rings +-{RINGS['out_fs']:.1f} V); loads the Seed by {load / 1e3:.1f}k; "
                     f"rolls off at {fc / 1e3:.0f} kHz")
        if g * CODEC_FS[CODEC] > TL074_SWING:
            bad.append(f"{name}: {g * CODEC_FS[CODEC]:.1f} V is past the TL074's swing")
    norm = r_between(mb, "IN_ODD", "OA_ODD") / (r_between(mb, "OA_EVEN", "EVEN") + r_between(mb, "TN_EVEN", "IN_ODD"))
    lines.append(f"EVEN -> ODD normal: {norm:.3f} of EVEN's jack voltage into ODD (Rings {RINGS['out_norm']:.3f})")
    if abs(norm / RINGS["out_norm"] - 1) > 0.05:
        bad.append("EVEN -> ODD normal off Rings'")
    # LEDs
    for net, colours in (("BTN_LED_POLY", (BUTTON_COLOUR,)), ("LED_POLY_R", ("red",)), ("LED_POLY_G", ("green",))):
        r = r_between(mb, f"{net}_IO", net)
        for c in colours:
            i = (V3A - LED_VF[c]) / (r + GPIO_RON)
            lines.append(f"{net} ({c}): {r:.0f} R, {i * 1e3:.1f} mA")
            if not 1e-3 < i < 8e-3:
                bad.append(f"{net}: {i * 1e3:.1f} mA")
    # 3V3A load
    pots = sum(1 for p in fb if p.kind == "POT")
    i3a = pots * V3A / 10e3 + sum(V3A / (r_between(mb, "3V3A", b) + r_between(mb, b, GND)) for b in bias)
    lines.append(f"3V3A load {i3a * 1e3:.1f} mA ({pots} pots, two bias dividers)")
    return lines, bad


# ------------------------------------------------- is the panel buildable?
# A first look at the faceplate's front (panel side) before any PCB work: the panel parts' bodies must
# not overlap, and every pad must clear the other parts' bodies (their leads are soldered on the
# panel side, where the bodies lie flat) and the board edge. Board frame, mm; pads as circles.
PAD_R = {"jack": 0.9, "pot": 0.9, "lug": 1.5, "button": 0.8, "led": 0.6}
EDGE = 0.5


def front_shapes():
    """{ref: (body rect (x0, y0, x1, y1), [pads (x, y, r)])} in the board frame, front view."""
    out = {}
    for ref, (x, y, rot) in PLACEMENT.items():
        if ref.startswith("J"):         # sleeve up: sleeve +5.7, switch lug +2.6, tip -5.7; body -6.78..+3.73
            out[ref] = ((x - 4.5, y - 6.78, x + 4.5, y + 3.73),
                        [(x, y + 5.7, PAD_R["jack"]), (x, y + 2.6, PAD_R["jack"]), (x, y - 5.7, PAD_R["jack"])])
        elif ref.startswith("RV"):      # Alpha 9 mm: pins 7.5 mm from the shaft, 2.5 apart; lugs on the shaft line
            ux, uy = pot_pins(ref)
            sx, sy = x - POT_SHAFT * ux, y - POT_SHAFT * uy
            vx, vy = -uy, ux
            pads = [(sx + 7.5 * ux + d * vx, sy + 7.5 * uy + d * vy, PAD_R["pot"]) for d in (-2.5, 0, 2.5)]
            pads += [(sx + d * vx, sy + d * vy, PAD_R["lug"]) for d in (-4.8, 4.8)]
            corners = [(sx + a * ux + b * vx, sy + a * uy + b * vy) for a in (-4.85, 6.5) for b in (-4.75, 4.75)]
            xs, ys = [c[0] for c in corners], [c[1] for c in corners]
            out[ref] = ((min(xs), min(ys), max(xs), max(ys)), pads)
        elif ref.startswith("SW"):      # Thonk LED button: 7.5 mm body, switch pins at +-2.54, LED pins at +-2.7
            pads = [(x + dx, y + dy, PAD_R["button"]) for dx in (-2.54, 2.54) for dy in (-2.54, 2.54)]
            pads += [(x - 2.7, y, PAD_R["button"]), (x + 2.7, y, PAD_R["button"])]
            out[ref] = ((x - 3.75, y - 3.75, x + 3.75, y + 3.75), pads)
        elif ref.startswith("D"):       # 3 mm, 3 leads at 1.27 mm; flange 3.8 mm
            out[ref] = ((x - 1.9, y - 1.9, x + 1.9, y + 1.9), [(x + d, y, PAD_R["led"]) for d in (-1.27, 0, 1.27)])
    return out


def front_check():
    """Problems as strings: bodies overlapping, pads under another part's body, pads near the edge."""
    shapes = front_shapes()
    bad = []
    refs = list(shapes)
    for i, a in enumerate(refs):
        (ax0, ay0, ax1, ay1), apads = shapes[a]
        for px, py, r in apads:
            if min(px - r, py - r, BOARD_W - px - r, BOARD_H - py - r) < EDGE:
                bad.append(f"{a}: pad at ({px:.2f}, {py:.2f}) within {EDGE} mm of the board edge")
        for b in refs[i + 1:]:
            (bx0, by0, bx1, by1), bpads = shapes[b]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                bad.append(f"{a} / {b}: bodies overlap")
            for (p, q, pads, (x0, y0, x1, y1)) in ((a, b, apads, shapes[b][0]), (b, a, bpads, shapes[a][0])):
                for px, py, r in pads:
                    if x0 - r < px < x1 + r and y0 - r < py < y1 + r:
                        bad.append(f"{p}: pad at ({px:.2f}, {py:.2f}) under {q}'s body")
            for px, py, r in apads:
                for qx, qy, s in bpads:
                    if math.hypot(px - qx, py - qy) < r + s + 0.25:
                        bad.append(f"{a} / {b}: pads at ({px:.2f}, {py:.2f}) and ({qx:.2f}, {qy:.2f}) too close")
    return bad


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        nets = nets_of(parts)
        print(f"{name}: {len(parts)} parts, {len(nets)} nets")
        kinds = collections.Counter((p.kind, p.value) for p in parts if p.kind not in ("R", "C"))
        print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
        rc = collections.Counter((p.kind, p.value) for p in parts if p.kind in ("R", "C"))
        print("  " + ", ".join(f"{n} x {v}" for (k, v), n in sorted(rc.items())))
    print(f"{sum(len(p) for _, _, p in HEADERS)} pins in {len(HEADERS)} headers")
    problems = check()
    for b in problems:
        print("  problem:", b)
    print(f"{len(problems)} netlist problems")
    report, bad = circuit_check()
    for line in report:
        print("  " + line)
    for b in bad:
        print("  problem:", b)
    print(f"{len(bad)} circuit problems")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
    problems = front_check()
    for p in problems:
        print("  ", p)
    print(f"front check: {len(problems)} problems")
