"""Tempo: a clock and LFO module on a Daisy Seed, 12HP Eurorack. Eight
outputs, each a clock (divide/multiply, swing, euclidean, probability, gate
width) or a clock-synced wave (sine, triangle, saw, square, S&H, smooth
random, pump); CLOCK and RESET in, RUN and RESET out, three CV inputs. The
same idea as ALM's Pamela's PRO Workout, with its own firmware. The whole
circuit as one netlist, split over two boards.

Build (the user's choice, 2026-10-31): panel approved as drawn, main board
SMD (SOIC, SOT-23, SOD-123, 0603, 1206 for bulk), like Senay.
Main board (MB): Daisy Seed on Rob Heel's seed_power_opamps breakout
(through-hole sockets), four MCP4922 DACs with Marblesy's output stage on
two TL074s, the LM4040 2.5 V reference and its inverter, three CV input
stages, the CLOCK and RESET input transistors, the RUN and RESET gate
stages.
Faceplate board (FB): the panel parts on its front (15 Thonkiconn, 3 EC11,
3 Thonk LED buttons, 8 LEDs) and SMD logic on its rear: a 74HC165 for the
six switches, two 74HC595 for the eleven LEDs with their resistors, the
encoder pull-ups, and CN1 for the display cable. SMD parts have no leads
through the board, so they may sit behind the display module; through-hole
parts may not.

Net naming
  CLK_IN/RST_IN  jack tips of CLOCK / RESET -> transistor stage -> CLK / RST (Seed, active low)
  CV1..CV3   jack tip of a CV input -> MB input stage; IN_*/OA_* summing node / op-amp output;
             ADC_* the Seed pin after the 1k
  DAC_OUTk   MCP4922 output -> output stage (IN_OUTk, OA_OUTk) -> 1k -> OUTk (jack tip)
  VREF       LM4040 2.5 V; NREF its inverse (-2.5 V) for the output stages' offset
  GATE_RUN/GATE_RST  Seed GPIO -> x2.5 stage -> RUN_OUT / RST_OUT (jack tips)
  SR_*       the shift-register chain: SR_CLK, SR_LOAD (165 /PL and 595 RCLK together), SR_DIN
             (165 -> Seed), SR_DOUT (Seed -> 595s); SR_CHAIN_F between the two 595s
  ENCn_A/B   encoder phases, pulled up on the FB, straight to Seed pins
  BTN_*_F    switches into the 165; L_*_F 595 outputs; LED_*_F after the resistor, to the anodes
  LCD_*      Seed SPI1 and GPIO -> the display module's cable (Side FXy's pins)
  Nets that cross the board-to-board headers carry the same name on both
  boards, with _F on the faceplate side (GND -> GND_F for the jacks, GND ->
  GND_D_F for the logic). Every faceplate net ends in _F.

Panel placement (PLACEMENT, bottom of the file): board frame, front view, x
right, y up, origin at the board's bottom-left corner, mm; footprint origins
(jacks: the WQP518MA origin, 0.78 mm above the barrel; buttons and
encoders: the shaft; LEDs: the body; DS1: the centre of the display's
active area).

Run from clock/hardware/tools:  python circuit.py  (netlist checks and the circuit values)
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


def D(ref, kind, value, anode, cathode, label=""):
    """Diodes in SOD-123: pin 1 = cathode (the band), pin 2 = anode, as on Senay."""
    return Part(ref, kind, value, {"1": cathode, "2": anode}, label)


def NPN(ref, e, b, c, label=""):
    """MMBT3904 (SOT-23: 1 B, 2 E, 3 C). Pins named by function, and the footprint's pads carry the
    same names, so nothing can swap them (Senay's rule)."""
    return Part(ref, "NPN", "MMBT3904", {"E": e, "B": b, "C": c}, label)


GND, VP, VN = "GND", "+12V", "-12V"

# --------------------------------------------------------------- Daisy Seed
# Seed pin number -> (libDaisy name, net). Pins with no net are left open.
# Side FXy's pins for the display (SPI1 on D7/D8/D10, DC/BL/RST on D11-D13) and for the shift chain
# (D26, D27, D29, D30), so one driver serves both modules. The DACs get SPI3 on D2 (PC10, SCK) and D6
# (PC12, MOSI), with a chip select each and a shared LDAC. D9 (SPI1 MISO, unused by the display) takes
# the RESET input. The encoder phases go straight to D20-D25. Free: D28, VIN, the codec pins.
SEED = {
    "1": ("D0", "CLK"), "2": ("D1", "DAC_CS4"), "3": ("D2", "DAC_SCK"), "4": ("D3", "DAC_CS1"),
    "5": ("D4", "DAC_CS2"), "6": ("D5", "DAC_CS3"), "7": ("D6", "DAC_MOSI"),
    "8": ("D7", "LCD_CS"), "9": ("D8", "LCD_SCK"), "10": ("D9", "RST"), "11": ("D10", "LCD_MOSI"),
    "12": ("D11", "LCD_DC"), "13": ("D12", "LCD_BL"), "14": ("D13", "LCD_RST"), "15": ("D14", "DAC_LDAC"),
    "16": ("AIN1", None), "17": ("AIN2", None), "18": ("AOUT1", None), "19": ("AOUT2", None),
    "20": ("AGND", GND), "21": ("3V3A", "3V3A"),
    "22": ("D15/A0", "ADC_CV1"), "23": ("D16/A1", "ADC_CV2"), "24": ("D17/A2", "ADC_CV3"),
    "25": ("D18/A3", "GATE_RUN"), "26": ("D19/A4", "GATE_RST"),
    "27": ("D20/A5", "ENC1_A"), "28": ("D21/A6", "ENC1_B"), "29": ("D22/A7", "ENC2_A"),
    "30": ("D23/A8", "ENC2_B"), "31": ("D24/A9", "ENC3_A"), "32": ("D25/A10", "ENC3_B"),
    "33": ("D26", "SR_CLK"), "34": ("D27", "SR_LOAD"), "35": ("D28/A11", None),
    "36": ("D29", "SR_DOUT"), "37": ("D30", "SR_DIN"),
    "38": ("3V3D", "3V3D"), "39": ("VIN", None), "40": ("DGND", GND),
    # breakout headers, numbered as on Rob Heel's board; the audio headers' grounds tied as on Marblesy
    "J1-1": ("GND", GND), "J1-2": ("-12V", VN), "J1-3": ("-12V", VN), "J1-4": ("-12V", VN),
    "J3-1": ("GND", GND), "J3-2": ("+12V", VP), "J3-3": ("+12V", VP), "J3-4": ("+12V", VP),
    "J4-1": ("AOUT1", None), "J4-2": ("GND", GND), "J4-3": ("AOUT2", None), "J4-4": ("GND", GND),
    "J5-1": ("AIN1", None), "J5-2": ("GND", GND), "J5-3": ("AIN2", None), "J5-4": ("GND", GND),
}

# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
# MCP4922 (SOIC-14, the DIP's pinout): 1 VDD, 2 NC, 3 /CS, 4 SCK, 5 SDI, 6 NC, 7 NC, 8 /LDAC, 9 /SHDN,
# 10 VOUTB, 11 VREFB, 12 VSS, 13 VREFA, 14 VOUTA
DAC_CS = {"U2": "DAC_CS1", "U3": "DAC_CS2", "U4": "DAC_CS3", "U5": "DAC_CS4"}
DAC_PIN = {"A": "14", "B": "10"}
# output k: DAC, channel, op-amp, section. U6 takes outputs 1-4, U7 outputs 5-8.
OUTPUTS = [(f"OUT{k + 1}", f"U{2 + k // 2}", "AB"[k % 2], "U6" if k < 4 else "U7", k % 4 + 1) for k in range(8)]
# Marblesy's output stage: Vout = -(Rf/Rdac) Vdac - (Rf/Rref) NREF = 5.32 V - 4.17 Vdac
OUT_STAGE = {"Rdac": "24k", "Rref": "47k", "Rf": "100k", "Rs": "1k"}
# Marblesy's CV input stage, gain -0.27 round BIAS: +-5 V -> 0.33..3.03 V. name, op-amp, section, ADC net
CV_CHANNELS = [("CV1", "U8", 1), ("CV2", "U8", 2), ("CV3", "U8", 3)]
# Marblesy's gate stage, non-inverting x2.5 from a GPIO: 0 / 8.25 V. jack net, GPIO net, op-amp, section
GATES = [("RUN_OUT", "GATE_RUN", "U9", 1), ("RST_OUT", "GATE_RST", "U9", 2)]
# transistor inputs (Side FXy's clock stage): jack net, Seed net, transistor, clamp diode
TRANSISTOR_INPUTS = [("CLK_IN", "CLK", "Q1", "D9"), ("RST_IN", "RST", "Q2", "D10")]


def main_board_parts():
    parts = []
    parts.append(Part("U1", "SEED", "Daisy Seed + seed_power_opamps",
                      {pin: net for pin, (name, net) in SEED.items() if net}))
    tl = {u: {"4": VP, "11": VN} for u in ("U6", "U7", "U8", "U9")}
    # DACs: 3V3A supply, VREF on both reference inputs, SPI3, shared /LDAC; pins 2, 6, 7 not connected
    for u, cs in DAC_CS.items():
        nets = {"1": "3V3A", "3": cs, "4": "DAC_SCK", "5": "DAC_MOSI", "8": "DAC_LDAC", "9": "3V3A",
                "11": "VREF", "12": GND, "13": "VREF"}
        for name, dac, ch, *_ in OUTPUTS:
            if dac == u:
                nets[DAC_PIN[ch]] = f"DAC_{name}"
        parts.append(Part(u, "MCP4922", "MCP4922-E/SL", nets))
    # output stages, R30..R61: Rdac, Rref, Rf, Rs per output
    for i, (name, dac, ch, u, s) in enumerate(OUTPUTS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: GND})
        n = 30 + 4 * i
        parts.append(R(f"R{n}", OUT_STAGE["Rdac"], f"DAC_{name}", f"IN_{name}"))
        parts.append(R(f"R{n + 1}", OUT_STAGE["Rref"], "NREF", f"IN_{name}"))
        parts.append(R(f"R{n + 2}", OUT_STAGE["Rf"], f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{n + 3}", OUT_STAGE["Rs"], f"OA_{name}", name))
    # CV inputs, R62..R70 and C10..C12
    for i, (name, u, s) in enumerate(CV_CHANNELS):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: "BIAS"})
        n = 62 + 3 * i
        parts.append(R(f"R{n}", "100k", name, f"IN_{name}"))
        parts.append(R(f"R{n + 1}", "27k", f"IN_{name}", f"OA_{name}"))
        parts.append(R(f"R{n + 2}", "1k", f"OA_{name}", f"ADC_{name}"))
        parts.append(C(f"C{10 + i}", "1n", f"IN_{name}", f"OA_{name}"))
    # U8D: NREF = -VREF. 100k / 100k, not Marblesy's 10k: four DACs load VREF twice as much as two did
    out, inm, inp = SECTION[4]
    tl["U8"].update({out: "NREF", inm: "IN_NREF", inp: GND})
    parts.append(R("R71", "100k", "VREF", "IN_NREF"))
    parts.append(R("R72", "100k", "IN_NREF", "NREF"))
    # the 2.5 V reference, fed through 1k5 from 3V3A (not 2k2: see circuit_check); SOT-23 pin 3 is the
    # substrate and goes to the anode
    parts.append(Part("D11", "LM4040", "LM4040-2.5 (SOT-23)", {"1": "VREF", "2": GND, "3": GND}))
    parts.append(R("R73", "1k5", "3V3A", "VREF"))
    parts.append(C("C14", "100n", "VREF", GND))
    # bias for the CV inputs: 3.3 V * 10 / 25 = 1.32 V
    parts.append(R("R74", "15k", "3V3A", "BIAS"))
    parts.append(R("R75", "10k", "BIAS", GND))
    parts.append(C("C13", "1u", "BIAS", GND))
    # CLOCK and RESET in: 100k into an NPN inverter, 10k pull-up, Schottky clamp for negative swings
    for k, (jack, seed, q, d) in enumerate(TRANSISTOR_INPUTS):
        parts.append(R(f"R{76 + 2 * k}", "100k", jack, f"B_{seed}"))
        parts.append(R(f"R{77 + 2 * k}", "10k", "3V3D", seed))
        parts.append(NPN(q, GND, f"B_{seed}", seed))
        parts.append(D(d, "SCHOTTKY", "1N5819HW", GND, f"B_{seed}"))
    # RUN and RESET out: non-inverting x2.5 (10k to GND, 15k feedback), 1k out
    for i, (jack, gpio, u, s) in enumerate(GATES):
        out, inm, inp = SECTION[s]
        tl[u].update({out: f"OA_{jack}", inm: f"IN_{jack}", inp: gpio})
        n = 80 + 3 * i
        parts.append(R(f"R{n}", "10k", GND, f"IN_{jack}"))
        parts.append(R(f"R{n + 1}", "15k", f"IN_{jack}", f"OA_{jack}"))
        parts.append(R(f"R{n + 2}", "1k", f"OA_{jack}", jack))
    for s in (3, 4):                               # U9's spare sections as grounded followers
        out, inm, inp = SECTION[s]
        tl["U9"].update({out: f"U9_SPARE{s}", inm: f"U9_SPARE{s}", inp: GND})
    for u in ("U6", "U7", "U8", "U9"):
        parts.append(Part(u, "TL074", "TL074CDT", tl[u]))
    # decoupling: a pair per TL074 beside it, one per DAC; bulk on the rails by the breakout's J1 / J3
    nc = 15
    for u in ("U6", "U7", "U8", "U9"):
        parts.append(C(f"C{nc}", "100n", VP, GND)); nc += 1
        parts.append(C(f"C{nc}", "100n", GND, VN)); nc += 1
    for k, u in enumerate(DAC_CS):
        parts.append(C(f"C{23 + k}", "100n", "3V3A", GND))
    parts.append(C("C27", "10u", VP, GND))
    parts.append(C("C28", "10u", GND, VN))
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


# Split by function, as the user routed Marblesy: the inputs, the outputs, the chain with the encoders
# and the faceplate's 3V3D, the display. Pin order is a first guess; placement sorts it.
HEADERS = [
    ("H1", "HDR6", [_pair(n) for n in ("CLK_IN", "RST_IN", "GND", "CV1", "CV2", "CV3")]),
    ("H2", "HDR11", [_pair(n) for n in ("RUN_OUT", "OUT1", "OUT2", "OUT3", "OUT4", "GND", "RST_OUT", "OUT5",
                                        "OUT6", "OUT7", "OUT8")]),
    ("H3", "HDR12", [_logic(n) for n in ("3V3D", "GND", "SR_CLK", "SR_LOAD", "SR_DIN", "SR_DOUT", "ENC1_A",
                                         "ENC1_B", "ENC2_A", "ENC2_B", "ENC3_A", "ENC3_B")]),
    ("H4", "HDR7", [_logic(n) for n in ("LCD_SCK", "LCD_MOSI", "GND", "LCD_CS", "LCD_DC", "LCD_RST", "LCD_BL")]),
]


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ---------------------------------------------------------------- faceplate
HP = 12
PANEL_W, PANEL_H = 60.6, 128.5          # Doepfer's 12HP width, as Plaitsy
BOARD_W, BOARD_H = 59.4, 108.0          # 0.6 mm in from each side, like the other modules
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin

# ref, panel label, signal name (the net it becomes, _F on this board), direction. The top row takes the
# inputs (switch lug to GND_F, so an open input reads 0 V); the two rows below them sit on the gold
# output band (switch lugs open): RUN and RESET out in the left column, outputs 1-8 in a 4 x 2 block.
JACKS = [
    ("J1", "CLOCK", "CLK_IN", "in"), ("J2", "RESET", "RST_IN", "in"), ("J3", "CV 1", "CV1", "in"),
    ("J4", "CV 2", "CV2", "in"), ("J5", "CV 3", "CV3", "in"),
    ("J6", "RUN", "RUN_OUT", "out"), ("J7", "1", "OUT1", "out"), ("J8", "2", "OUT2", "out"),
    ("J9", "3", "OUT3", "out"), ("J10", "4", "OUT4", "out"),
    ("J11", "RESET", "RST_OUT", "out"), ("J12", "5", "OUT5", "out"), ("J13", "6", "OUT6", "out"),
    ("J14", "7", "OUT7", "out"), ("J15", "8", "OUT8", "out"),
]
# ref, panel label, LED colour. Thonk low-profile LED buttons (5.5 mm caps), the feet clipped. Switch
# on pins 1+2 / 3+4, LED anode 5, cathode 6.
BUTTONS = [("SW1", "RUN", "green"), ("SW2", "TAP", "white"), ("SW3", "SHIFT", "red")]
# EC11 encoders with push, unlabelled: the screen names them (soft knobs, as on Side FXy). KiCad pad
# names A, B, C (common), S1, S2 (switch), MP1 / MP2 (mounting tabs).
ENCODERS = [("ENC1", "K1"), ("ENC2", "K2"), ("ENC3", "K3")]
# 3 mm red LEDs, one per output, left of the output's number (Marblesy's spot); pin 1 anode, 2 cathode
OUTPUT_LEDS = [(f"D{k + 1}", f"J{7 + k if k < 4 else 8 + k}") for k in range(8)]
# Side FXy's screen, turned landscape: Waveshare 1.9inch LCD Module (ST7789V2, 170 x 320)
DISPLAY = ("DS1", "1.9in IPS 320x170")
DISPLAY_ACTIVE = (42.72, 22.70)         # active area, landscape, mm
DISPLAY_SIZE = (51.2, 27.3)             # the module; active area 6.25 mm from the flex end, 2.23 from the
#                                         other end, 2.30 from the long sides
# the module's cable (MX1.25 to 2.54 mm Dupont) lands on CN1 in Waveshare's signal order
LCD_PINS = ["3V3D_F", "GND_D_F", "LCD_MOSI_F", "LCD_SCK_F", "LCD_CS_F", "LCD_DC_F", "LCD_RST_F", "LCD_BL_F"]

# 74HC165 (SOIC-16): 1 /PL, 2 CP, 3..6 D4..D7, 7 /Q7, 8 GND, 9 Q7, 10 DS, 11..14 D0..D3, 15 /CE, 16 VCC.
# The six switches on D0..D5, D6 / D7 tied high (read as released).
HC165_INPUTS = ["11", "12", "13", "14", "3", "4", "5", "6"]   # D0..D7
SWITCHES = ["BTN_K1_F", "BTN_K2_F", "BTN_K3_F", "BTN_RUN_F", "BTN_TAP_F", "BTN_SHIFT_F"]
# 74HC595 (SOIC-16): outputs QA..QH = pins 15, 1..7, QH' 9; /SRCLR high, /OE low. U11 (first in the
# chain) drives the output LEDs, U12 the button LEDs (QD..QH spare).
HC595_OUT = ["15", "1", "2", "3", "4", "5", "6", "7"]
HC595_PINS = {"8": "GND_D_F", "10": "3V3D_F", "11": "SR_CLK_F", "12": "SR_LOAD_F", "13": "GND_D_F",
              "16": "3V3D_F"}
# LED resistors at 3.3 V: 470R puts about 3 mA in a red LED. White (TAP) and, if it is InGaN, green (RUN)
# drop close to 3 V, so they get 150R (2-5 mA over their Vf spread). Measure the buttons when they arrive.
BUTTON_LED_R = {"SW1": "150", "SW2": "150", "SW3": "470"}


def faceplate_parts():
    parts = []
    for ref, label, sig, d in JACKS:
        nets = {"1": "GND_F", "3": f"{sig}_F"}
        if d == "in":
            nets["2"] = "GND_F"
        parts.append(Part(ref, "JACK", "", nets, label))
    for k, (ref, label) in enumerate(ENCODERS):
        parts.append(Part(ref, "ENC", "EC11", {"A": f"ENC{k + 1}_A_F", "B": f"ENC{k + 1}_B_F", "C": "GND_D_F",
                                               "S1": "GND_D_F", "S2": f"BTN_K{k + 1}_F", "MP1": "GND_D_F",
                                               "MP2": "GND_D_F"}, label))
    words = {ref: label for ref, label, colour in BUTTONS}
    for ref, label, colour in BUTTONS:
        parts.append(Part(ref, "SWLED", colour, {"1": "GND_D_F", "2": "GND_D_F", "3": f"BTN_{label}_F",
                                                 "4": f"BTN_{label}_F", "5": f"LED_{label}_F", "6": "GND_D_F"},
                          label))
    for k, (ref, jack) in enumerate(OUTPUT_LEDS):
        parts.append(Part(ref, "LED", "red 3 mm", {"1": f"LED_OUT{k + 1}_F", "2": "GND_D_F"}))
    # pull-ups, 10k 0603: R1..R6 the encoder phases (they go to Seed pins), R7..R12 the six switches
    phases = [f"ENC{k}_{p}_F" for k in (1, 2, 3) for p in "AB"]
    for i, net in enumerate(phases + SWITCHES):
        parts.append(R(f"R{i + 1}", "10k", "3V3D_F", net))
    # U10: the switches -> SR_DIN
    sr = {"1": "SR_LOAD_F", "2": "SR_CLK_F", "8": "GND_D_F", "9": "SR_DIN_F", "10": "GND_D_F", "15": "GND_D_F",
          "16": "3V3D_F"}
    for pin, net in zip(HC165_INPUTS, SWITCHES + ["3V3D_F", "3V3D_F"]):
        sr[pin] = net
    parts.append(Part("U10", "HC165", "74HC165D", sr))
    # U11 (SR_DOUT in, QH' on to U12): output LEDs through R13..R20 (470R)
    u11 = dict(HC595_PINS, **{"14": "SR_DOUT_F", "9": "SR_CHAIN_F"})
    for k in range(8):
        u11[HC595_OUT[k]] = f"L_OUT{k + 1}_F"
        parts.append(R(f"R{13 + k}", "470", f"L_OUT{k + 1}_F", f"LED_OUT{k + 1}_F"))
    parts.append(Part("U11", "HC595", "74HC595D", u11))
    # U12: button LEDs through R21..R23
    u12 = dict(HC595_PINS, **{"14": "SR_CHAIN_F"})
    for k, (ref, label, colour) in enumerate(BUTTONS):
        u12[HC595_OUT[k]] = f"L_{label}_F"
        parts.append(R(f"R{21 + k}", BUTTON_LED_R[ref], f"L_{label}_F", f"LED_{label}_F"))
    parts.append(Part("U12", "HC595", "74HC595D", u12))
    # CN1: a right-angle header, so the cable's Dupont plug lies flat in the 8.5 mm gap between the boards
    parts.append(Part("CN1", "HDR8RA", "LCD", {str(i + 1): n for i, n in enumerate(LCD_PINS)}, "display cable"))
    for k, u in enumerate(("U10", "U11", "U12")):
        parts.append(C(f"C{k + 1}", "100n", "3V3D_F", "GND_D_F"))
    parts.append(C("C4", "10u", "3V3D_F", "GND_D_F"))      # the display module, beside CN1 (1206 MLCC)
    # board-to-board headers (male pins on this board)
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ faceplate placement
# Five jack columns 11.5 mm apart, centred (Plaitsy's grid); the rows 14.6 mm apart with the bottom one
# at Side FXy's height. The encoders and the buttons above them sit on the midpoints between jack
# columns 1-2 and 4-5 and on the centre column. Panel = board + (0.6, 10.25).
JACK_PITCH = 11.5
JACK_X = [round(BOARD_W / 2 + JACK_PITCH * (k - 2), 2) for k in range(5)]
JACK_ROW = (36.45, 21.85, 7.25)         # origins, top row first
CONTROL_X = [round((JACK_X[0] + JACK_X[1]) / 2, 2), JACK_X[2], round((JACK_X[3] + JACK_X[4]) / 2, 2)]
ENCODER_Y = 69.25                       # panel y 49.0
BUTTON_Y = 57.0                         # panel y 61.25: leaves a strip above the top jack row's sleeve
#                                         lugs for rear parts (y 44.2-52.6) and clears the encoder bodies
LED_DX, LED_DY = -4.2, 5.75             # output LED from its jack's origin: Marblesy's spot
DISPLAY_Y = 92.05                       # centre of the active area, panel y 26.2

PLACEMENT = {}
for k, (ref, *_) in enumerate(JACKS):
    PLACEMENT[ref] = (JACK_X[k % 5], JACK_ROW[k // 5], 0)
for k, (ref, *_) in enumerate(BUTTONS):
    PLACEMENT[ref] = (CONTROL_X[k], BUTTON_Y, 0)
for k, (ref, _) in enumerate(ENCODERS):
    PLACEMENT[ref] = (CONTROL_X[k], ENCODER_Y, 0)
for ref, jack in OUTPUT_LEDS:
    jx, jy, _ = PLACEMENT[jack]
    PLACEMENT[ref] = (round(jx + LED_DX, 2), round(jy + LED_DY, 2), 0)
PLACEMENT["DS1"] = (BOARD_W / 2, DISPLAY_Y, 0)

# The display module in the panel gap, glass against the panel; nothing with leads may sit on the
# faceplate behind it (SMD on the rear is fine). Flex end on the left for now (the cable connector on its
# back then sits 34.3-38.5 mm from the left end, and the cable leaves to the right); placement may flip it.
_ax, _ay = PLACEMENT["DS1"][:2]
DISPLAY_MODULE = (round(_ax - DISPLAY_ACTIVE[0] / 2 - 6.25, 2), round(_ay - DISPLAY_ACTIVE[1] / 2 - 2.30, 2),
                  round(_ax + DISPLAY_ACTIVE[0] / 2 + 2.23, 2), round(_ay + DISPLAY_ACTIVE[1] / 2 + 2.30, 2))


# ------------------------------------------------------------------- checks
def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets, designators used twice on a board, header pins not used on both
    boards, nets on both boards, faceplate nets without _F, panel parts and PLACEMENT out of step."""
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
            if len(mbn[a]) < 2 or len(fbn[b]) < 2:
                bad.append(f"{ref}: header net not used on both boards: {a} / {b}")
    bad += [f"net {n} on both boards" for n in set(mbn) & set(fbn)]
    bad += [f"faceplate net {n} lacks the _F suffix" for n in fbn if not n.endswith("_F")]
    panel = {p.ref for p in fb if p.kind in ("JACK", "ENC", "SWLED", "LED")}
    bad += [f"{r} has no PLACEMENT" for r in sorted(panel - set(PLACEMENT))]
    bad += [f"PLACEMENT {r} is not a faceplate part" for r in sorted(set(PLACEMENT) - panel - {DISPLAY[0]})]
    return bad


# ------------------------------------------------------------ circuit values
# Datasheet figures the checks use (typical values unless noted)
V3A = 3.3                    # 3V3A, 3V3D
VREF_NOM = 2.5               # LM4040-2.5
LM4040_IMIN = 45e-6          # minimum operating current (TI, 2.5 V part)
DAC_VREF_R = 165e3           # MCP4922 VREF input impedance per channel
DAC_IDD = 350e-6             # MCP4922 supply current per device
TL074_SWING = 10.0           # TL074 output swing on +-12 V into 10k and more, both ways (conservative)
LED_VF = {"red": 1.9, "green": 2.1, "white": 2.8}     # at a few mA; InGaN green would be about 2.9
HC595_RON = 50.0             # 74HC595 output resistance at 3.3 V, roughly


def value(v):
    """'24k' -> 24000.0, '1k5' -> 1500.0, '100n' -> 1e-7."""
    mult = {"R": 1, "k": 1e3, "M": 1e6, "u": 1e-6, "n": 1e-9, "p": 1e-12}
    for m, f in mult.items():
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


def circuit_check():
    """Each stage's numbers, from the resistor values the netlist actually has (a mis-wired resistor
    makes the lookup fail). Returns (report lines, problems)."""
    mb, fb = main_board_parts(), faceplate_parts()
    lines, bad = [], []
    # reference: NREF and the LM4040's current
    nref = -VREF_NOM * r_between(mb, "IN_NREF", "NREF") / r_between(mb, "VREF", "IN_NREF")
    feed = (V3A - VREF_NOM) / r_between(mb, "3V3A", "VREF")
    n_dac_inputs = sum(1 for p in mb if p.kind == "MCP4922" for pin in ("11", "13") if p.nets.get(pin) == "VREF")
    load = n_dac_inputs * VREF_NOM / DAC_VREF_R + VREF_NOM / r_between(mb, "VREF", "IN_NREF")
    i_ref = feed - load
    lines.append(f"VREF 2.50 V, NREF {nref:+.2f} V; feed {feed * 1e3:.2f} mA, loads {load * 1e3:.2f} mA "
                 f"({n_dac_inputs} DAC inputs + inverter), LM4040 {i_ref * 1e3:.2f} mA")
    if i_ref < 2 * LM4040_IMIN:
        bad.append(f"LM4040 current {i_ref * 1e6:.0f} uA, below twice its minimum")
    # outputs: code 0 and code 4095 through each stage
    for name, dac, ch, u, s in OUTPUTS:
        rdac, rref = r_between(mb, f"DAC_{name}", f"IN_{name}"), r_between(mb, "NREF", f"IN_{name}")
        rf, rs = r_between(mb, f"IN_{name}", f"OA_{name}"), r_between(mb, f"OA_{name}", name)
        op = next(p for p in mb if p.ref == u)
        o, m, pl = SECTION[s]
        if (op.nets[o], op.nets[m], op.nets[pl]) != (f"OA_{name}", f"IN_{name}", GND):
            bad.append(f"{name}: {u} section {s} is not wired as the output stage")
        v = [-rf / rdac * VREF_NOM * code / 4096 - rf / rref * nref for code in (0, 4095)]
        step = rf / rdac * VREF_NOM / 4096
        lines.append(f"{name}: {dac}{ch} -> {u}{'ABCD'[s - 1]}, code 0 {v[0]:+.2f} V, code 4095 {v[1]:+.2f} V, "
                     f"{step * 1e3:.2f} mV/step, {rs:.0f} R out")
        if max(abs(x) for x in v) > TL074_SWING:
            bad.append(f"{name}: {max(abs(x) for x in v):.1f} V is past the TL074's swing")
    # CV inputs: what +-5 V reads at the ADC
    bias = V3A * r_between(mb, "BIAS", GND) / (r_between(mb, "3V3A", "BIAS") + r_between(mb, "BIAS", GND))
    for name, u, s in CV_CHANNELS:
        g = r_between(mb, f"IN_{name}", f"OA_{name}") / r_between(mb, name, f"IN_{name}")
        adc = [bias * (1 + g) - g * vin for vin in (5.0, -5.0)]
        lines.append(f"{name}: +5 V -> {adc[0]:.2f} V, -5 V -> {adc[1]:.2f} V at the ADC (BIAS {bias:.2f} V)")
        if not (0.1 < min(adc) and max(adc) < V3A - 0.1):
            bad.append(f"{name}: +-5 V does not stay inside the ADC range")
    # gate outputs
    for jack, gpio, u, s in GATES:
        high = V3A * (1 + r_between(mb, f"IN_{jack}", f"OA_{jack}") / r_between(mb, GND, f"IN_{jack}"))
        lines.append(f"{jack}: high {high:.2f} V")
        if not 5.0 <= high <= TL074_SWING:
            bad.append(f"{jack}: gate high {high:.2f} V")
    # transistor inputs: base current at a 5 V clock, the gain the transistor needs to pull the pin low
    for jack, seed, q, d in TRANSISTOR_INPUTS:
        ib = (5.0 - 0.7) / r_between(mb, jack, f"B_{seed}")
        ic = V3A / r_between(mb, "3V3D", seed)
        lines.append(f"{jack}: 5 V in -> Ib {ib * 1e6:.0f} uA, Ic {ic * 1e3:.2f} mA, needs hFE > {ic / ib:.0f}")
        if ic / ib > 30:
            bad.append(f"{jack}: needs hFE {ic / ib:.0f}")
    # LEDs
    colour = {f"LED_{lbl}_F": c for ref, lbl, c in BUTTONS}
    colour.update({f"LED_OUT{k + 1}_F": "red" for k in range(8)})
    for net, c in colour.items():
        r = next(value(p.value) for p in fb if p.kind == "R" and net in p.nets.values())
        i = (V3A - LED_VF[c]) / (r + HC595_RON)
        if net in ("LED_OUT1_F", "LED_RUN_F", "LED_TAP_F", "LED_SHIFT_F"):
            lines.append(f"{net} ({c}): {r:.0f} R, {i * 1e3:.1f} mA")
        if not 1e-3 < i < 8e-3:
            bad.append(f"{net}: {i * 1e3:.1f} mA")
    # 3V3A load
    i3a = 4 * DAC_IDD + feed + V3A / (r_between(mb, "3V3A", "BIAS") + r_between(mb, "BIAS", GND))
    lines.append(f"3V3A load {i3a * 1e3:.1f} mA (DACs, reference feed, bias)")
    return lines, bad


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
