"""Plaitsy: a Mutable Instruments Plaits clone on a Daisy Seed, built the
Marblesy way: two stacked PCBs behind a 12HP panel, Thonk panel parts. The
whole circuit as one netlist, split over the two boards.

Main board (MB): Daisy Seed on Rob Heel's seed_power_opamps breakout (power
and the audio output stage), eight TL074 CV input stages, two bias
dividers, Schottky clamps on the V/OCT ADC pin, series resistors for the
button LEDs.
Faceplate board (FB): 10 Thonkiconn jacks, 7 Alpha pots into a 74HC4051,
8 bicolour LEDs driven by two 74HC595, 2 Thonk LED buttons, the
normalization-probe resistors.

Net naming
  CV_*       jack tip of a CV input (FB: CV_*_F) -> MB input stage
  IN_*/OA_*  input stage summing node / op-amp output
  ADC_*      Seed ADC pin, after the 1k series resistor
  TN_*_F     jack switch lug fed by the probe through 10k (FB)
  OUT/AUX    breakout J4 outputs -> FB jacks (OUT_F, AUX_F)
  POT_*_F / ATT_*_F  pot wipers (FB) into the mux; MUX_OUT / MUX_S0..2 cross to the MB
  L_*        74HC595 outputs (before the 470R), LED_* after it
  BTN_*_F    buttons (Seed internal pull-ups), BTN_LED_* their LEDs
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
# The 8 CV inputs sit on A0..A6 and A9, the pot mux on A10 with its address
# on D26..D28, the two 74HC595 on SPI1's SCK / MOSI with D13 as the latch,
# the buttons on D0 / D1 (internal pull-ups), their LEDs on D2 / D3, the
# normalization probe on D14. Audio leaves through the breakout's J4.
SEED = {
    "1": ("D0", "BTN_A"), "2": ("D1", "BTN_B"), "3": ("D2", "BTN_LED_A_IO"), "4": ("D3", "BTN_LED_B_IO"),
    "5": ("D4", None), "6": ("D5", None), "7": ("D6", None), "8": ("D7", None),
    "9": ("D8", "SPI_SCK"), "10": ("D9", None), "11": ("D10", "SPI_MOSI"), "12": ("D11", None),
    "13": ("D12", None), "14": ("D13", "LED_LATCH"), "15": ("D14", "PROBE"),
    "16": ("AIN1", None), "17": ("AIN2", None), "18": ("AOUT1", None), "19": ("AOUT2", None),
    "20": ("AGND", "GND"), "21": ("3V3A", "3V3A"),
    "22": ("D15/A0", "ADC_MODEL"), "23": ("D16/A1", "ADC_TIMBRE"), "24": ("D17/A2", "ADC_FM"),
    "25": ("D18/A3", "ADC_MORPH"), "26": ("D19/A4", "ADC_HARMO"), "27": ("D20/A5", "ADC_TRIG"),
    "28": ("D21/A6", "ADC_LEVEL"), "29": ("D22/A7", None), "30": ("D23/A8", None),
    "31": ("D24/A9", "ADC_VOCT"), "32": ("D25/A10", "MUX_OUT"),
    "33": ("D26", "MUX_S0"), "34": ("D27", "MUX_S1"), "35": ("D28/A11", "MUX_S2"),
    "36": ("D29", None), "37": ("D30", None),
    "38": ("3V3D", "3V3D"), "39": ("VIN", None), "40": ("DGND", "GND"),
    # breakout headers, numbered as on Rob Heel's board; J4 is the buffered audio output
    "J1-1": ("GND", "GND"), "J1-2": ("-12V", "-12V"), "J1-3": ("-12V", "-12V"), "J1-4": ("-12V", "-12V"),
    "J3-1": ("GND", "GND"), "J3-2": ("+12V", "+12V"), "J3-3": ("+12V", "+12V"), "J3-4": ("+12V", "+12V"),
    "J4-1": ("AOUT1", "OUT"), "J4-2": ("GND", "GND"), "J4-3": ("AOUT2", "AUX"), "J4-4": ("GND", "GND"),
    "J5-1": ("AIN1", None), "J5-2": ("GND", "GND"), "J5-3": ("AIN2", None), "J5-4": ("GND", "GND"),
}

# ---------------------------------------------------------- CV input stages
# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
# name, label, op-amp, section, Rf, Cf, bias. Inverting stages biased from
# 3V3A: the wide channels (gain -0.13) put +-12 V on 0.10..3.22 V; V/OCT
# (gain -0.33, 2.351 V offset) reads -2.9..+7.1 V at 0.2 Plaits units per
# volt, the same pitch scaling as Plaits, with Schottky clamps beyond that.
CV_CHANNELS = [
    ("MODEL", "MODEL", "U3", 1, "13k", "1n", "BIAS_A"), ("TIMBRE", "TIMBRE", "U3", 2, "13k", "1n", "BIAS_A"),
    ("FM", "FM", "U3", 3, "13k", "1n", "BIAS_A"), ("MORPH", "MORPH", "U3", 4, "13k", "1n", "BIAS_A"),
    ("HARMO", "HARMONICS", "U4", 1, "13k", "1n", "BIAS_A"), ("TRIG", "TRIG", "U4", 2, "13k", "100p", "BIAS_A"),
    ("LEVEL", "LEVEL", "U4", 3, "13k", "1n", "BIAS_A"), ("VOCT", "V/OCT", "U4", 4, "33k", "1n", "BIAS_V"),
]


def main_board_parts():
    parts = []
    parts.append(Part("U2", "SEED", "Daisy Seed + seed_power_opamps",
                      {pin: net for pin, (name, net) in SEED.items() if net}))
    tl = {u: {"4": "+12V", "11": "-12V"} for u in ("U3", "U4")}
    for i, (name, label, u, s, rf, cf, bias) in enumerate(CV_CHANNELS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: bias})
        parts.append(R(f"R{21 + 3 * i}", "100k", f"CV_{name}", f"IN_{name}"))
        parts.append(R(f"R{22 + 3 * i}", rf, f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{23 + 3 * i}", "1k", f"OA_{name}", f"ADC_{name}"))
        parts.append(C(f"C{21 + i}", cf, f"IN_{name}", f"OA_{name}"))
    for u in ("U3", "U4"):
        parts.append(Part(u, "TL074", "TL074", tl[u]))
    # bias A = 3.3 V * 12 / 27 = 1.467 V (wide channels), bias V = 3.3 V * 15 / 28 = 1.768 V (V/OCT)
    parts.append(R("R45", "15k", "3V3A", "BIAS_A"))
    parts.append(R("R46", "12k", "BIAS_A", "GND"))
    parts.append(C("C29", "1u", "BIAS_A", "GND"))
    parts.append(R("R47", "13k", "3V3A", "BIAS_V"))
    parts.append(R("R48", "15k", "BIAS_V", "GND"))
    parts.append(C("C30", "1u", "BIAS_V", "GND"))
    # V/OCT clamps: the ADC pin held between GND and 3V3A for pitch CV outside -2.9..+7.1 V (pin 1 = cathode)
    parts.append(Part("D21", "BAT85", "BAT85", {"1": "3V3A", "2": "ADC_VOCT"}))
    parts.append(Part("D22", "BAT85", "BAT85", {"1": "ADC_VOCT", "2": "GND"}))
    # supply decoupling, one pair per TL074
    for k, u in enumerate(("U3", "U4")):
        parts.append(C(f"C{31 + 2 * k}", "100n", "+12V", "GND"))
        parts.append(C(f"C{32 + 2 * k}", "100n", "GND", "-12V"))
    # the button LEDs: Seed GPIO -> 470R -> header -> LED inside the button -> GND_D_F
    parts.append(R("R60", "470", "BTN_LED_A_IO", "BTN_LED_A"))
    parts.append(R("R61", "470", "BTN_LED_B_IO", "BTN_LED_B"))
    # board-to-board headers (female sockets on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ board-to-board pins
def _pair(net):
    return net, {"GND": "GND_F", "GND_D": "GND_D_F"}.get(net, net + "_F")


# Pin orders picked for the fewest crossing lines between the pins and what
# they connect to on both boards (the user reordered Marblesy's headers the
# same way while routing), each supply next to its ground.
HEADERS = [
    ("H1", "HDR8", [_pair(f"CV_{n}") for n in ("HARMO", "MORPH", "VOCT", "FM", "LEVEL", "TIMBRE", "TRIG", "MODEL")]),
    ("H2", "HDR9", [_pair(n) for n in ("AUX", "GND", "3V3A", "OUT", "MUX_OUT", "MUX_S0", "MUX_S1", "MUX_S2",
                                       "PROBE")]),
    ("H3", "HDR9", [("SPI_MOSI", "MOSI_F"), ("GND", "GND_D_F"), ("3V3D", "3V3D_F"), ("LED_LATCH", "LED_LATCH_F"),
                    ("SPI_SCK", "SCK_F"), ("BTN_A", "BTN_A_F"), ("BTN_LED_A", "BTN_LED_A_F"), ("BTN_B", "BTN_B_F"),
                    ("BTN_LED_B", "BTN_LED_B_F")]),
]


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ---------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net. Plaits probes TIMBRE, FM, MORPH,
# TRIG and LEVEL for a plugged cable: those lugs (TN_*) get the normalization
# probe through 10k. MODEL, HARMONICS and V/OCT read 0 V unpatched (lug to
# GND_F); the two outputs leave the lug open.
JACKS = [
    ("J1", "MODEL", "CV_MODEL_F", "GND_F"), ("J2", "TIMBRE", "CV_TIMBRE_F", "TN_TIMBRE_F"),
    ("J3", "FM", "CV_FM_F", "TN_FM_F"), ("J4", "MORPH", "CV_MORPH_F", "TN_MORPH_F"),
    ("J5", "HARMO", "CV_HARMO_F", "GND_F"),
    ("J6", "TRIG", "CV_TRIG_F", "TN_TRIG_F"), ("J7", "LEVEL", "CV_LEVEL_F", "TN_LEVEL_F"),
    ("J8", "V/OCT", "CV_VOCT_F", "GND_F"),
    ("J9", "OUT", "OUT_F", None), ("J10", "AUX", "AUX_F", None),
]
# ref, label, wiper net, 74HC4051 input pin, mux channel (channel 7, pin 4, is grounded). The channels
# are picked so no two wiper lines cross; the firmware reads them by this table, not in panel order.
POTS = [
    ("RV1", "FREQUENCY", "POT_FREQ_F", "13", 0), ("RV2", "HARMONICS", "POT_HARMO_F", "14", 1),
    ("RV3", "TIMBRE", "POT_TIMBRE_F", "12", 3), ("RV4", "MORPH", "POT_MORPH_F", "15", 2),
    ("RV5", "TIMBRE att.", "ATT_TIMBRE_F", "5", 5), ("RV6", "FM att.", "ATT_FM_F", "2", 6),
    ("RV7", "MORPH att.", "ATT_MORPH_F", "1", 4),
]
# ref, label, firmware switch. Thonk low-profile LED buttons, the Marblesy
# part (5.5 mm cap; clip its three feet, the board has no holes for them).
# Plaits' own buttons have no LED; these get a Seed GPIO each, for the
# firmware to use or not.
BUTTONS = [("SW1", "model, green bank", "A"), ("SW2", "model, red bank", "B")]
# ref, label, kind: eight 3 mm red/green bicolour LEDs (common cathode) in a
# column; each row shows one model of the green, red and (Plaits 1.2) yellow bank.
LEDS = [(f"D{k + 1}", f"model {k + 1} / {k + 9} / {k + 17}", "RG") for k in range(8)]
HC595_PINS = {"8": "GND_D_F", "10": "3V3D_F", "11": "SCK_F", "13": "GND_D_F", "16": "3V3D_F"}   # SRCLR high, OE low
HC595_OUTS = ["15", "1", "2", "3", "4", "5", "6", "7"]     # QA..QH
# the sixteen LED lines, each with its 470R (R80 + line), split by colour: every LED has its red anode
# on the left (front view) and its green one on the right, so U9 on the left drives the eight reds through
# the left resistor rows (R80-R87) and U10 on the right the eight greens (R88-R95), and no line crosses
# the LED column. Within each row of four resistors the LED order, and the 595 output pins below, are
# picked for the fewest crossing lines (one per 595).
LED_LINES = [(f"D{k}", "R") for k in (4, 3, 2, 1, 5, 6, 7, 8)] + [(f"D{k}", "G") for k in (1, 2, 3, 4, 8, 7, 6, 5)]
SR_OUTS = {"U9": ["7", "6", "4", "15", "5", "3", "2", "1"], "U10": ["4", "2", "1", "15", "7", "6", "5", "3"]}


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
    mux = {"16": "3V3A_F", "8": "GND_F", "7": "GND_F", "6": "GND_F", "4": "GND_F", "3": "MUX_OUT_F",
           "11": "MUX_S0_F", "10": "MUX_S1_F", "9": "MUX_S2_F"}
    for _, _, wiper, mpin, _ in POTS:
        mux[mpin] = wiper
    parts.append(Part("U1", "MUX", "74HC4051", mux))
    parts.append(C("C8", "100n", "3V3A_F", "GND_F"))
    # LEDs through the two 74HC595 (chained), one 470R per colour
    sr = {"U9": dict(HC595_PINS, **{"14": "MOSI_F", "12": "LED_LATCH_F", "9": "SR_CHAIN"}),
          "U10": dict(HC595_PINS, **{"14": "SR_CHAIN", "12": "LED_LATCH_F"})}
    led_nets = {ref: {"2": "GND_D_F"} for ref, *_ in LEDS}
    for i, (ref, colour) in enumerate(LED_LINES):
        u, pin = ("U9", SR_OUTS["U9"][i]) if i < 8 else ("U10", SR_OUTS["U10"][i - 8])
        sr[u][pin] = f"L_{ref}_{colour}"
        parts.append(R(f"R{80 + i}", "470", f"L_{ref}_{colour}", f"LED_{ref}_{colour}"))
        led_nets[ref]["1" if colour == "R" else "3"] = f"LED_{ref}_{colour}"
    for ref, label, kind in LEDS:
        parts.append(Part(ref, "LED_RG", "", led_nets[ref], label))
    for u in ("U9", "U10"):
        parts.append(Part(u, "HC595", "74HC595", sr[u]))
    parts.append(C("C9", "100n", "3V3D_F", "GND_D_F"))    # U9
    parts.append(C("C10", "100n", "3V3D_F", "GND_D_F"))   # U10
    # buttons: contacts 1+2 to GND_D_F, 3+4 to the Seed (internal pull-up); the LED on pins 5 / 6
    for (ref, label, sw), led in zip(BUTTONS, ("BTN_LED_A_F", "BTN_LED_B_F")):
        net = f"BTN_{sw}_F"
        parts.append(Part(ref, "SWLED", "", {"1": "GND_D_F", "2": "GND_D_F", "3": net, "4": net, "5": led,
                                             "6": "GND_D_F"}, label))
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ faceplate placement
# Panel: Eurorack 3U, 12HP. Faceplate board 59.4 x 108 mm, centred on it.
PANEL_W, PANEL_H = 60.6, 128.5
BOARD_W, BOARD_H = 59.4, 108.0
# Footprint origins are not the mechanical centres: the Thonkiconn barrel is
# 0.78 mm below the WQP518MA origin (sleeve pad up), the Alpha pot's shaft
# 4.0 mm beyond the PTV09A origin, away from the pins (+x at angle 90): the
# footprint's pin row is 3.5 mm from its origin, the shaft 7.5 mm from the pins.
JACK_BARREL, POT_SHAFT = -0.78, 4.0
# Which way a pot's pin row lies from its shaft (front view, unit vector); -x
# unless listed. HARMONICS turns its pins up and MORPH down: pointing at the
# LED column, they would take the strip the green LED resistors stand in.
POT_PINS = {"RV2": (0, 1), "RV4": (0, -1)}
POT_ANGLE = {(-1, 0): 90, (0, 1): 180, (0, -1): 0}   # PLACEMENT's angle: 90 = pins towards -x, as on Marblesy


def pot_pins(ref):
    return POT_PINS.get(ref, (-1, 0))

# What the user sees, in panel mm from the top-left corner (y down): the
# knob shafts, jack barrels, button caps and LED bodies. The arrangement is
# Plaits' own, measured off the panel (60.6 x 128.5): two model buttons top
# centre, FREQUENCY and HARMONICS large either side of the eight model
# LEDs, TIMBRE and MORPH below them, the three attenuverters in a row, the
# five CV inputs and the TRIG / LEVEL / V/OCT / OUT / AUX row at the bottom.
LED_PITCH = 5.3
JACK_PITCH = 11.5
PANEL_XY = {
    "SW1": (25.8, 17.8), "SW2": (34.8, 17.8),                       # model buttons, over the icon columns
    "RV1": (12.4, 30.2), "RV2": (48.2, 30.2),                       # FREQUENCY, HARMONICS
    "RV3": (12.4, 55.5), "RV4": (48.2, 55.5),                       # TIMBRE, MORPH
    "RV5": (11.3, 79.9), "RV6": (30.3, 79.9), "RV7": (49.3, 79.9),  # TIMBRE / FM / MORPH attenuverters
}
for k in range(8):
    PANEL_XY[f"D{k + 1}"] = (PANEL_W / 2, 25.2 + LED_PITCH * k)
for k, ref in enumerate(("J1", "J2", "J3", "J4", "J5")):             # MODEL, TIMBRE, FM, MORPH, HARMO
    PANEL_XY[ref] = (PANEL_W / 2 - 2 * JACK_PITCH + JACK_PITCH * k, 96.2)
for k, ref in enumerate(("J6", "J7", "J8", "J9", "J10")):            # TRIG, LEVEL, V/OCT, OUT, AUX
    PANEL_XY[ref] = (PANEL_W / 2 - 2 * JACK_PITCH + JACK_PITCH * k, 110.5)


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (from the bottom-left, y up)."""
    return px - (PANEL_W - BOARD_W) / 2, PANEL_H - (PANEL_H - BOARD_H) / 2 - py


# Footprint origins on the faceplate board (front view, x right, y up, origin
# bottom-left, mm) with the part's angle: what pcb.py places and panel.py
# measures from.
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
    mb, fb = nets_of(main_board_parts()), nets_of(faceplate_parts())
    for ref, kind, pins in HEADERS:
        for a, b in pins:
            if len(mb[a]) < 2 or len(fb[b]) < 2:
                print("  header net not used on both boards:", a, b)
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
