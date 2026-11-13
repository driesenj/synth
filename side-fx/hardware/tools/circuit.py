"""Side FXy: a RYK Modular SIDE FX clone on a Daisy Seed. 14HP Eurorack. The
whole circuit as one netlist, split over two boards.

Main board (MB): Daisy Seed on Rob Heel's seed_power_opamps breakout (audio
in and out through the breakout's op-amps), four TL074 CV input stages, a
transistor clock input, an H11L1 MIDI input, the 74HC595 and 470R for the
button LEDs. Presets live in the Seed's QSPI flash; there is no SD card.
Faceplate board (FB): 9 Thonkiconn jacks and a stereo Thonkiconn for MIDI,
4 EC11 encoders with push, 5 Thonk LED buttons, two 74HC165 (encoders and
buttons) on the chain the main board's 74HC595 ends, the header for the
display module's cable. The display (Waveshare 1.9inch LCD Module, ST7789V2)
sits behind the panel window, in the gap between panel and faceplate, and
nothing with leads may sit on the faceplate behind it.

Net naming
  IN1/IN2, OUT1/OUT2  audio jack tips <-> the breakout's audio headers (J5 in, J4 out)
  CV1..CV4   jack tip of a CV input (FB: CV1_F) -> MB input stage
  IN_*/OA_*  input stage summing node / op-amp output
  ADC_*      Seed ADC pin, after the 1k series resistor
  CLK_IN     clock jack tip -> transistor stage -> CLK (Seed GPIO, active low)
  MIDI_TIP/MIDI_RING  TRS MIDI (type A: ring = source, tip = sink) -> H11L1 -> MIDI_RX
  LCD_*      Seed SPI1 and GPIO -> the display module's cable
  SR_*       the shift-register chain: SR_CLK and SR_LOAD (74HC165 /PL and 74HC595
             RCLK together), SR_DIN (165 -> Seed), SR_DOUT (Seed -> 595, main board)
  ENCn_A/B, BTN_*  encoder phases and switches into the 74HC165s (FB)
  L_*        74HC595 outputs (before the 470R), LED_* after it, to the buttons' anodes
  nets that cross the board-to-board headers carry the same name on both
  boards, with _F on the faceplate side (GND -> GND_F, the logic ground
  GND -> GND_D_F).

Panel placement (PLACEMENT, bottom of the file): board frame, front view, x
right, y up, origin at the board's bottom-left corner, mm; footprint origins
(jacks: the WQP518MA origin, 0.78 mm above the barrel; buttons and
encoders: the shaft; DS1: the centre of the display's active area).
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
# Fixed by the STM32: SPI1 on D7/D8/D10 (D9 = MISO stays free: the display
# only listens), USART1 RX on D14, TIM4_CH4 on D12 (PB9) for the backlight
# PWM. The shift-register chain is bit-banged on the four pins without an
# ADC. Free: D1..D6 (SDMMC1, if an SD card is ever wanted), D9, D19,
# D21..D25 (A4, A6..A10), D28 (A11), VIN.
SEED = {
    "1": ("D0", "CLK"),
    "2": ("D1", None), "3": ("D2", None), "4": ("D3", None), "5": ("D4", None),
    "6": ("D5", None), "7": ("D6", None),
    "8": ("D7", "LCD_CS"), "9": ("D8", "LCD_SCK"), "10": ("D9", None), "11": ("D10", "LCD_MOSI"),
    "12": ("D11", "LCD_DC"), "13": ("D12", "LCD_BL"), "14": ("D13", "LCD_RST"), "15": ("D14", "MIDI_RX"),
    "16": ("AIN1", None), "17": ("AIN2", None), "18": ("AOUT1", None), "19": ("AOUT2", None),
    "20": ("AGND", "GND"), "21": ("3V3A", "3V3A"),
    "22": ("D15/A0", "ADC_CV1"), "23": ("D16/A1", "ADC_CV2"), "24": ("D17/A2", "ADC_CV3"),
    "25": ("D18/A3", "ADC_CV4"),
    "26": ("D19/A4", None), "27": ("D20/A5", "BTN_SHIFT"),
    "28": ("D21/A6", None), "29": ("D22/A7", None), "30": ("D23/A8", None),
    "31": ("D24/A9", None), "32": ("D25/A10", None),
    "33": ("D26", "SR_CLK"), "34": ("D27", "SR_LOAD"), "35": ("D28/A11", None),
    "36": ("D29", "SR_DOUT"), "37": ("D30", "SR_DIN"),
    "38": ("3V3D", "3V3D"), "39": ("VIN", None), "40": ("DGND", "GND"),
    # breakout headers, numbered as on Rob Heel's board
    "J1-1": ("GND", "GND"), "J1-2": ("-12V", "-12V"), "J1-3": ("-12V", "-12V"), "J1-4": ("-12V", "-12V"),
    "J3-1": ("GND", "GND"), "J3-2": ("+12V", "+12V"), "J3-3": ("+12V", "+12V"), "J3-4": ("+12V", "+12V"),
    "J4-1": ("AOUT1", "OUT1"), "J4-2": ("GND", "GND"), "J4-3": ("AOUT2", "OUT2"), "J4-4": ("GND", "GND"),
    "J5-1": ("AIN1", "IN1"), "J5-2": ("GND", "GND"), "J5-3": ("AIN2", "IN2"), "J5-4": ("GND", "GND"),
}

# ---------------------------------------------------------- CV input stages
# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
# Gain -0.13 (100k/13k) around BIAS: V_adc = 1.657 V - 0.13 * V_in, so +-12 V stays inside 0..3.3 V at
# the ADC pins (A2/A3 are 3.3 V-tolerant TT pins, 4.0 V absolute maximum). name, section
CV_CHANNELS = [("CV1", 1), ("CV2", 2), ("CV3", 3), ("CV4", 4)]


def main_board_parts():
    parts = []
    parts.append(Part("U5", "SEED", "Daisy Seed + seed_power_opamps",
                      {pin: net for pin, (name, net) in SEED.items() if net}))
    tl = {"4": "+12V", "11": "-12V"}
    for i, (name, s) in enumerate(CV_CHANNELS):
        out, inm, inp = SECTION[s]
        tl.update({out: f"OA_{name}", inm: f"IN_{name}", inp: "BIAS"})
        parts.append(R(f"R{10 + 3 * i}", "100k", name, f"IN_{name}"))
        parts.append(R(f"R{11 + 3 * i}", "13k", f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{12 + 3 * i}", "1k", f"OA_{name}", f"ADC_{name}"))
        parts.append(C(f"C{10 + i}", "2n2", f"IN_{name}", f"OA_{name}"))    # 13k || 2n2: 5.6 kHz
    parts.append(Part("U6", "TL074", "TL074", tl))
    parts.append(C("C15", "100n", "+12V", "GND"))
    parts.append(C("C16", "100n", "GND", "-12V"))
    # bias for the input stages: 3.3 V * 12 / 27 = 1.47 V -> 0 V at the jack reads 1.657 V (0.502 of full scale)
    parts.append(R("R22", "15k", "3V3A", "BIAS"))
    parts.append(R("R23", "12k", "BIAS", "GND"))
    parts.append(C("C14", "1u", "BIAS", "GND"))
    # clock input: 100k into an NPN inverter, 10k pull-up, Schottky clamp for negative swings
    parts.append(R("R24", "100k", "CLK_IN", "B_CLK"))
    parts.append(R("R25", "10k", "3V3D", "CLK"))
    parts.append(Part("Q1", "NPN", "2N3904", {"1": "GND", "2": "B_CLK", "3": "CLK"}))     # E B C
    parts.append(Part("D1", "BAT85", "BAT85", {"1": "B_CLK", "2": "GND"}))                # 1 = cathode
    # MIDI in, TRS type A: ring (DIN pin 4, source) -> 220R -> opto LED -> tip (DIN pin 5, sink);
    # 1N4148 across the LED against reverse voltage; the H11L1's open-collector output idles high
    parts.append(R("R26", "220", "MIDI_RING", "OPTO_A"))
    parts.append(Part("D2", "1N4148", "1N4148", {"1": "OPTO_A", "2": "MIDI_TIP"}))       # 1 = cathode
    parts.append(Part("U7", "H11L1", "H11L1", {"1": "OPTO_A", "2": "MIDI_TIP", "4": "MIDI_RX", "5": "GND",
                                               "6": "3V3D"}))                          # 1 A, 2 K, 4 Vo, 5 GND, 6 Vcc
    parts.append(R("R27", "1k", "3V3D", "MIDI_RX"))
    parts.append(C("C17", "100n", "3V3D", "GND"))
    # button LEDs: the 74HC595 at the end of the chain, 470R each (about 3 mA into a red LED at 3.3 V),
    # then through H3 to the buttons' anodes; it lives here because the faceplate has no room left for it
    sr = dict(HC595_PINS)
    for k, ref in enumerate(LED_ORDER):
        word = LED_WORD[ref]
        sr[HC595_OUT[k]] = f"L_{word}"
        parts.append(R(f"R{k + 1}", "470", f"L_{word}", f"LED_{word}"))
    parts.append(Part("U3", "HC595", "74HC595", sr))
    parts.append(C("C3", "100n", "3V3D", "GND"))
    # board-to-board headers (female sockets on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets) if mb}))
    return parts


# ------------------------------------------------------ board-to-board pins
def _pair(net):
    return net, {"GND": "GND_F"}.get(net, net + "_F")


def _logic(net):
    """A logic-side pin: the faceplate's digital ground is GND_D_F."""
    return (net, "GND_D_F") if net == "GND" else _pair(net)


# Split by function, as the user routed Marblesy: audio, CV + clock + MIDI,
# the shift-register chain with the button LEDs and the display's power, the
# display's signals. Pin order is a first guess; the routing may sort it.
HEADERS = [
    ("H1", "HDR5", [_pair(n) for n in ("IN1", "IN2", "GND", "OUT1", "OUT2")]),
    ("H2", "HDR8", [_pair(n) for n in ("CV1", "CV2", "CV3", "CV4", "CLK_IN", "GND", "MIDI_TIP", "MIDI_RING")]),
    ("H3", "HDR11", [_logic(n) for n in ("3V3D", "GND", "SR_CLK", "SR_LOAD", "SR_DIN", "BTN_SHIFT", "LED_PITCH",
                                         "LED_DELAY", "LED_TEXTURE", "LED_REVERB", "LED_SHIFT")]),
    ("H4", "HDR6", [_logic(n) for n in ("LCD_SCK", "LCD_MOSI", "LCD_CS", "LCD_DC", "LCD_RST", "LCD_BL")]),
]

# ---------------------------------------------------------------- faceplate
HP = 14
PANEL_W, PANEL_H = 70.8, 128.5          # Doepfer's 14HP width
BOARD_W, BOARD_H = 69.6, 108.0          # 0.6 mm in from each side, like Plaitsy and Marblesy
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin

# ref, panel label, tip net, switch-lug net (None = open). IN 2 is normalled to IN 1, so a mono
# source feeds both channels.
JACKS = [
    ("J1", "IN 1", "IN1_F", "GND_F"), ("J2", "OUT 1", "OUT1_F", None), ("J3", "CLOCK", "CLK_IN_F", "GND_F"),
    ("J4", "CV 1", "CV1_F", "GND_F"), ("J5", "MIDI", None, None),
    ("J6", "IN 2", "IN2_F", "IN1_F"), ("J7", "OUT 2", "OUT2_F", None), ("J8", "CV 2", "CV2_F", "GND_F"),
    ("J9", "CV 3", "CV3_F", "GND_F"), ("J10", "CV 4", "CV4_F", "GND_F"),
]
# J5 is a stereo Thonkiconn (PJ366ST): the mono jack's three-pin row with the ring where the switch lug
# was (1 sleeve, 2 ring, 3 tip; no switches). Tip and ring to the MIDI input, the sleeve left open (MIDI
# IN leaves the shield unconnected).
MIDI_JACK = {"3": "MIDI_TIP_F", "2": "MIDI_RING_F"}
# ref, panel label, switch net. Thonk low-profile LED buttons, red: switch on pins 1+2 / 3+4, LED on
# 5 (anode) and 6; the three plastic feet clipped off. The sends sit on a 74HC165, SHIFT on its own
# Seed pin with the Seed's internal pull-up (the two 165s are full).
BUTTONS = [
    ("SW1", "PITCH", "BTN_PITCH_F"), ("SW2", "DELAY", "BTN_DELAY_F"), ("SW3", "TEXTURE", "BTN_TEXTURE_F"),
    ("SW4", "REVERB", "BTN_REVERB_F"), ("SW5", "SHIFT", "BTN_SHIFT_F"),
]
LED_WORD = {ref: lbl for ref, lbl, _ in BUTTONS}
# EC11 encoders with push (KiCad pad names A, B, C, S1, S2; the two mounting tabs MP1 / MP2): common,
# switch and tabs to GND, the phases and the switch pulled up into the 165s
ENCODERS = [("ENC1", "K1"), ("ENC2", "K2"), ("ENC3", "K3"), ("ENC4", "K4")]
DISPLAY = ("DS1", "1.9in IPS 170x320")   # the module; CN1 below is the header for its cable
DISPLAY_ACTIVE = (22.70, 42.72)         # active area, portrait, mm (Waveshare 1.9inch LCD Module)
# the module's cable (MX1.25 to 2.54 mm Dupont) lands on CN1 in Waveshare's signal order
LCD_PINS = ["3V3D_F", "GND_D_F", "LCD_MOSI_F", "LCD_SCK_F", "LCD_CS_F", "LCD_DC_F", "LCD_RST_F", "LCD_BL_F"]
# 74HC165: 1 /PL, 2 CP, 3..6 D4..D7, 7 /Q7, 8 GND, 9 Q7, 10 DS, 11..14 D0..D3, 15 CE, 16 VCC
HC165_INPUTS = ["11", "12", "13", "14", "3", "4", "5", "6"]   # D0..D7
# U1 is read first (its Q7 is SR_DIN), U2 shifts into it
SR_INPUTS = {
    "U1": [f"ENC{k}_{p}_F" for k in range(1, 5) for p in "AB"],
    "U2": ["BTN_K1_F", "BTN_K2_F", "BTN_K3_F", "BTN_K4_F", "BTN_PITCH_F", "BTN_DELAY_F", "BTN_TEXTURE_F",
           "BTN_REVERB_F"],
}
PULLUPS = {"U1": "RN1", "U2": "RN2"}    # 8 x 10k bussed SIP-9, pin 1 common
# 74HC595 (main board) outputs QA..QH = pins 15, 1..7; SRCLR high, OE low
HC595_OUT = ["15", "1", "2", "3", "4", "5", "6", "7"]
HC595_PINS = {"8": "GND", "10": "3V3D", "11": "SR_CLK", "12": "SR_LOAD", "13": "GND", "14": "SR_DOUT", "16": "3V3D"}
LED_ORDER = ["SW1", "SW2", "SW3", "SW4", "SW5"]   # QA..QE; QF..QH spare


def faceplate_parts():
    parts = []
    for ref, label, tip, tn in JACKS:
        if ref == "J5":
            parts.append(Part(ref, "JACK_TRS", "", MIDI_JACK, label))
            continue
        nets = {"1": "GND_F", "3": tip}
        if tn:
            nets["2"] = tn
        parts.append(Part(ref, "JACK", "", nets, label))
    # the LEDs' anodes come from the main board's 74HC595 and 470R through H3
    for ref, label, net in BUTTONS:
        parts.append(Part(ref, "SWLED", "", {"1": "GND_D_F", "2": "GND_D_F", "3": net, "4": net,
                                             "5": f"LED_{LED_WORD[ref]}_F", "6": "GND_D_F"}, label))
    for k, (ref, label) in enumerate(ENCODERS):
        parts.append(Part(ref, "ENC", "EC11", {"A": f"ENC{k + 1}_A_F", "B": f"ENC{k + 1}_B_F", "C": "GND_D_F",
                                               "S1": "GND_D_F", "S2": f"BTN_K{k + 1}_F", "MP1": "GND_D_F",
                                               "MP2": "GND_D_F"}, label))
    # the two 74HC165s: U2.Q7 -> U1.DS, U1.Q7 -> SR_DIN; every input pulled up by its network
    for u, ds, q7 in (("U1", "SR_CHAIN", "SR_DIN_F"), ("U2", "GND_D_F", "SR_CHAIN")):
        pins = {"1": "SR_LOAD_F", "2": "SR_CLK_F", "8": "GND_D_F", "9": q7, "10": ds, "15": "GND_D_F",
                "16": "3V3D_F"}
        rn = {"1": "3V3D_F"}
        for i, net in enumerate(SR_INPUTS[u]):
            pins[HC165_INPUTS[i]] = net
            rn[str(i + 2)] = net
        parts.append(Part(u, "HC165", "74HC165", pins))
        parts.append(Part(PULLUPS[u], "RN9", "10k x8 bussed", rn))
    # CN1: a right-angle header, so the cable's Dupont plug lies flat in the 11 mm gap between the boards
    parts.append(Part("CN1", "HDR8RA", "LCD", {str(i + 1): n for i, n in enumerate(LCD_PINS)}, "display cable"))
    parts.append(C("C1", "100n", "3V3D_F", "GND_D_F"))    # U1
    parts.append(C("C2", "100n", "3V3D_F", "GND_D_F"))    # U2
    parts.append(C("C4", "10u", "3V3D_F", "GND_D_F"))     # the display module, beside CN1: an MLCC on 5.08 mm,
    #                                                       an electrolytic stands too tall for the 11 mm gap
    # board-to-board headers (male pins on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets) if fb}))
    return parts


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ------------------------------------------------------ faceplate placement
# Five jack columns 12.5 mm apart, centred; the rows at Marblesy's heights so
# the racks line up. The send buttons span the outer jack columns; SHIFT sits
# on the right column above the knob stack. Panel = board + (0.6, 10.25).
JACK_X = [9.8 + 12.5 * k for k in range(5)]
JACK_ROW = (21.85, 7.25)
BUTTON_X = [JACK_X[0] + (JACK_X[4] - JACK_X[0]) * k / 3 for k in range(4)]
BUTTON_Y = 101.6
KNOB_X = (40.8, JACK_X[4])              # left and right column of the zigzag
KNOB_Y = (81.75, 68.75, 55.75, 42.75)   # 13 mm apart, K1 at the top

PLACEMENT = {}
for k, (ref, *_) in enumerate(JACKS):
    PLACEMENT[ref] = (JACK_X[k % 5], JACK_ROW[k // 5], 0)
for k in range(4):
    PLACEMENT[f"SW{k + 1}"] = (round(BUTTON_X[k], 2), BUTTON_Y, 0)
PLACEMENT["SW5"] = (JACK_X[4], 85.25, 0)
for k, (ref, _) in enumerate(ENCODERS):
    PLACEMENT[ref] = (KNOB_X[k % 2], KNOB_Y[k], 0)
PLACEMENT["DS1"] = (16.4, (KNOB_Y[0] + KNOB_Y[3]) / 2, 0)   # centred on the knob stack

# The display module (Waveshare drawing): 51.2 x 27.3 mm, the active area 6.25 mm from the flex end,
# 2.23 from the other end and 2.30 from the long sides; the 8-pin cable connector on its back 34.3-38.5 mm
# from the flex end, centred across, the cable leaving towards the other end. Portrait, flex end up, so
# the strip under it is tall enough for the 74HC165s. It sits in the panel gap with its glass against the
# panel; nothing with leads may sit on the faceplate behind it (their soldered ends would press into the
# module's back), and the faceplate has a cutout under the connector for the cable.
_ax, _ay = PLACEMENT["DS1"][:2]
DISPLAY_MODULE = (round(_ax - 13.65, 2), round(_ay - DISPLAY_ACTIVE[1] / 2 - 2.23, 2),
                  round(_ax + 13.65, 2), round(_ay + DISPLAY_ACTIVE[1] / 2 + 6.25, 2))   # x1, y1, x2, y2 front view
_top = DISPLAY_MODULE[3]
DISPLAY_CONNECTOR = (round(_ax - 7.8, 2), round(_top - 38.5, 2), round(_ax + 7.8, 2), round(_top - 34.3, 2))
DISPLAY_CUTOUT = (8.0, 43.5, 24.7, 57.0, 1.0)     # x1, y1, x2, y2, corner radius: connector, plug and the bend

# The headers, the rear-side parts and the whole main board sit where the routed export has them
# (pcb.routed_boards()). Mounting holes, the same four on both boards (front view): one in the jack strip
# between U1 and U2, one between the encoder columns, two between the send buttons.
HOLES_FRONT = [(30.0, 33.1), (50.3, 49.0), (34.8, 104.5), (51.5, 104.5)]
# Encoders: which side of the shaft the phase pins (A, C, B) go, so the right column clears H2 and the
# bottom strip: ENC1..3 phase row below the shaft, ENC4 (above U2 and H1) phase row on its left.
ENC_PINS = {"ENC1": "below", "ENC2": "below", "ENC3": "below", "ENC4": "left"}


def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets, header pins not used on both boards, designators used twice,
    nets that cross between boards without a header."""
    bad = []
    mb, fb = main_board_parts(), faceplate_parts()
    for name, parts in (("main board", mb), ("faceplate", fb)):
        nets = nets_of(parts)
        for n in sorted(nets):
            if len(nets[n]) < 2:
                bad.append(f"{name}: single-pin net {n} {nets[n]}")
        refs = collections.Counter(p.ref for p in parts)
        bad += [f"{name}: {r} used {c} times" for r, c in refs.items() if c > 1]
    mbn, fbn = nets_of(mb), nets_of(fb)
    for ref, kind, pins in HEADERS:
        if len(pins) != int(kind[3:]):
            bad.append(f"{ref}: {len(pins)} pins on a {kind}")
        for a, b in pins:
            if a and (len(mbn[a]) < 2 or len(fbn[b]) < 2):
                bad.append(f"{ref}: header net not used on both boards: {a} / {b}")
    for n in set(mbn) & set(fbn):
        bad.append(f"net {n} on both boards (faceplate nets end in _F)")
    for n in fbn:
        if not n.endswith("_F") and n not in ("SR_CHAIN",) and not n.startswith(("L_", "LED_")):
            bad.append(f"faceplate net {n} lacks the _F suffix")
    return bad


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        print(f"{name}: {len(parts)} parts, {len(nets_of(parts))} nets")
    problems = check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} problems")
