"""Eight: the Kosmo 8-step sequencer (8-step-sequencer.ino) rebuilt as a
26HP Eurorack module, one PCB, with its own firmware (eight/eight.ino). The
Kosmo build's parts and pin map stay; new are a RESET input, the MODE knob
split into ROWS and DIRECTION, and the SQ-1's step settings (gate, skip and
slide kept per step at once, BUTTONS picks which the step buttons edit).

This file holds the panel parts, the Mega pin each one uses, their placement,
the Mega's socket footprint and the netlist (module-design skill: the panel
came first; approved without the mode LEDs on 2026-10-31, the split knobs on
2026-11-01).

  Mega 2560 Pro (Embed), on sockets on the board's rear. A0-A15 read the step
  pots; D22-D53 the step buttons and their LEDs; the ADS1115 (0x48) reads the
  ROWS, DIRECTION, BUTTONS and DUTY knobs; two MCP4725 (0x61 = CV A, 0x60 =
  CV B) feed the output amp; D15 / D17 the gates; D18 CLOCK (interrupt); D2
  RESET (interrupt; the Kosmo build's mode LED there is gone); D19 SHIFT.
  Step pots: wired as on the Kosmo build, CW end to GND (the sketch plays
  1 - reading), so clockwise is a higher voltage.
  LEDs and button LEDs: anode to +5 V through a resistor, cathode to the pin
  (the sketch's LED_ON is LOW).
  Step buttons: to +5 V, pull-down to GND (pressed reads HIGH); SHIFT to GND
  on the pin's internal pull-up.

Netlist (the defaults of the open choices in docs/design.md):
  power      Eurorack 2 x 5; 1N5819 per rail (on -12 V the cathode on the
             header); +12 V -> 10R -> +12V for the TL074 and the reference;
             the 5 V switcher (R-78E5.0-0.5) straight after the diode, into
             the Mega's 5V pins (bypassing its own regulator)
  VDAC       LM4040-5.0 from +12V through 820R: the two MCP4725 breakouts'
             supply, which is their reference (the LED current on +5V would
             otherwise move every CV)
  CV A / B   MCP4725 -> TL074 x2 (10k / 10k, 1 %) -> 1k -> jack; the
             feedback is taken at the jack, so the 1k drops nothing into a
             VCO's input; 100p from the op-amp output keeps it stable into a
             cable
  GATE A / B D17 / D15 -> 10k -> TL074 x2 -> 1k -> jack, about 10 V; 100k
             to GND at the pin holds the gate low while the Mega boots
  CLOCK,     tip -> 22k -> the pin, 100k and 1n to GND, BAT85 clamps to +5V
  RESET      and GND; unpatched the switch lug grounds the tip
  networks   two 10k bussed SIPs (button pull-downs, common GND), two 1k
             bussed SIPs (button LEDs, common +5V)

Pin maps: TL074 sections (out, in-, in+); jack 1 sleeve, 2 switch lug, 3 tip;
Alpha pot 1 CCW, 2 wiper, 3 CW, 4/5 lugs; Thonk LED button 1+2 one contact,
3+4 the other, 5 LED anode, 6 cathode; 9-pin bussed SIP pin 1 common;
LM4040 TO-92 2 cathode, 1 and 3 to GND (TI's LM4040: 3 anode, 1 tied to the
anode as TI suggests; LM4040-N: 1 anode, 3 NC), so either part fits; R-78E 1
in, 2 GND, 3 out; BAT85 / 1N5819 1 cathode, 2 anode; electrolytic 1 -, 2 +.
The breakouts and the Mega are wired by pin name: the breakouts' pin order
follows the boards picked (open choice 5), the Mega's comes from MEGA_PADS.

`python circuit.py` prints the placement checks, the netlist problems
(single-pin nets, designators used twice, TL074 pins left out, the Mega's
wiring against the sketch's own pin tables, panel parts against PLACEMENT)
and the numbers the values give (thresholds, gains, currents).

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  button  Thonk low-profile LED button, cap centred on the origin
"""
import collections
import math
import os
import re

HP = 26
PANEL_W, PANEL_H = HP * 5.08 - 0.3, 128.5      # 131.78 x 128.5
BOARD_W, BOARD_H = round(PANEL_W - 1.2, 2), 108.0     # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins
STEPS = 8

# ---------------------------------------------------------------- panel parts and their Mega pins
# The Kosmo build's tables, step 1 first, as eight/eight.ino keeps them (sketch_check() compares).
# The Kosmo build's mode and transition LEDs are gone: the knobs' words show their positions.
POTS_A = ["A7", "A0", "A1", "A2", "A3", "A4", "A5", "A6"]
POTS_B = ["A8", "A9", "A10", "A11", "A12", "A13", "A14", "A15"]
STEPS_A = ["D52", "D50", "D48", "D46", "D44", "D42", "D40", "D38"]
STEPS_B = ["D53", "D51", "D49", "D47", "D45", "D43", "D41", "D39"]
LEDS_A = ["D35", "D37", "D33", "D25", "D27", "D31", "D23", "D29"]
LEDS_B = ["D36", "D34", "D22", "D24", "D26", "D28", "D30", "D32"]
# knob positions, counter-clockwise first: the words run round the knob in this order
ROWS_MODES = ["A→B", "ABAB", "A+B", "CV/DUTY", "CV/SLIDE"]
DIRECTIONS = ["FORWARD", "REVERSE", "PING-PONG", "RANDOM"]
BUTTON_MODES = ["GATE", "SKIP", "SLIDE", "JUMP"]
KNOB_TRAVEL = 300.0                     # Alpha 9 mm: 300 +- 5 degrees end to end
# the sketch's ADS1115 channel constants and the knob each one reads
ADS_KNOBS = {"ROWS_KNOB": "RV17", "DIRECTION_KNOB": "RV18", "BUTTONS_KNOB": "RV19", "DUTY_KNOB": "RV20"}

# ref, panel label, what it drives, description
POTS = ([(f"RV{k}", f"STEP A{k}", POTS_A[k - 1], "B10k, row A step pot, Mega ADC") for k in range(1, 9)]
        + [(f"RV{8 + k}", f"STEP B{k}", POTS_B[k - 1], "B10k, row B step pot, Mega ADC") for k in range(1, 9)]
        + [("RV17", "ROWS", "ADS A3", "B10k, 5 positions, ADS1115"),
           ("RV18", "DIRECTION", "ADS A0", "B10k, 4 positions, ADS1115"),
           ("RV19", "BUTTONS", "ADS A2", "B10k, 4 positions, ADS1115"),
           ("RV20", "DUTY", "ADS A1", "B10k, gate length, ADS1115")])
BUTTONS = ([(f"SW{k}", f"STEP A{k}", (STEPS_A[k - 1], LEDS_A[k - 1]), "Thonk LED button, row A") for k in range(1, 9)]
           + [(f"SW{8 + k}", f"STEP B{k}", (STEPS_B[k - 1], LEDS_B[k - 1]), "Thonk LED button, row B")
              for k in range(1, 9)]
           + [("SW17", "SHIFT", ("D19", None), "Thonk LED button, LED not fitted")])
JACKS =[("J1", "CLOCK", "D18", "clock in: a step per rising edge"),
         ("J2", "RESET", "D2", "reset in: the next clock plays step 1"),
         ("J3", "CV A", "DAC 0x61", "output amp"), ("J4", "GATE A", "D17", "gate buffer"),
         ("J5", "CV B", "DAC 0x60", "output amp"), ("J6", "GATE B", "D15", "gate buffer")]

# ---------------------------------------------------------------- Mega 2560 Pro footprint
# Pad centres of the Mega 2560 Pro (Embed) clone, in its own frame (top view, y down, mm, USB end at
# x = 0), from Clone_Mega2560_Pro_Socket.kicad_mod in Alarm-Siren/arduino-kicad-library (measured
# from a board; the two inner header rows are 1.20" apart). Check against the board you buy.
MEGA_W, MEGA_H = 54.61, 38.1
MEGA_PAD = 0.86                         # 1.73 mm pads
MEGA_PADS = {}
for k, (a, b) in enumerate([("VIN1", "VIN2"), ("GND1", "GND2"), ("5V1", "5V2"), ("3V31", "3V32"), ("AREF", "RST1")]
                           + [(f"D{2 * i}", f"D{2 * i + 1}") for i in range(16)]):
    MEGA_PADS[a], MEGA_PADS[b] = (1.905 + 2.54 * k, 34.29), (1.905 + 2.54 * k, 36.83)      # 2 x 21
for k in range(16):                                                                        # 2 x 16
    a, b = (f"A{2 * k}", f"A{2 * k + 1}") if k < 8 else (f"D{32 + 2 * (k - 8)}", f"D{33 + 2 * (k - 8)}")
    MEGA_PADS[a], MEGA_PADS[b] = (14.605 + 2.54 * k, 1.27), (14.605 + 2.54 * k, 3.81)
for k in range(3):                                                                         # 2 x 3, D48-D53
    MEGA_PADS[f"D{48 + 2 * k}"], MEGA_PADS[f"D{49 + 2 * k}"] = (52.705, 6.35 + 2.54 * k), (50.165, 6.35 + 2.54 * k)
# The ICSP pads (x 50.2 / 52.7, y 19.1-24.1) get no socket; nothing here uses them.

# ---------------------------------------------------------------- panel grid (panel frame, y down)
# Eight step columns 14.5 mm apart, centred on the panel; the left margin holds the A / B brackets.
# Controls along the top, jacks along the bottom so cables hang away from the hands; outputs on the
# gold band.
STEP_PITCH = 14.5
STEP_X = [PANEL_W / 2 + STEP_PITCH * (i - 3.5) for i in range(STEPS)]

# The Mega stands on sockets on the rear, its header rows running across the board. Their pins come
# through to the front, where the panel parts' bodies sit flat on the board, so each socket row needs
# a strip clear of them. The rows are spaced to make two such strips, 33.02 mm apart (the Mega's row
# pitch): one between the A buttons and the B pots, one between the B buttons and the jacks.
CLEAR = 0.4                             # front-side gap between a socket pad and a part's body
SOCKET_HALF = 1.27 + MEGA_PAD           # a double row's pads reach this far from its centre line
POT_TOP, POT_BOTTOM = 4.85, 7.5 + 0.9   # Alpha housing above the shaft; its pin pads below it
BUTTON_HALF = 3.75                      # Thonk LED button body, 7.5 mm square
JACK_TOP = 6.5                          # the sleeve lug above the barrel (body 4.51)
# The WQP518MA's pads, front view, from the barrel: (centre above it, width, height). The sleeve pad
# reaches past the lug, so it sets how close the Mega's lower row may come (the PCB check found it).
JACK_PADS = [(6.48, 1.8, 1.1), (3.38, 2.0, 1.1), (-4.92, 2.0, 1.0)]       # sleeve, switch lug, tip
ROW = {"controls": 25.5, "pot_a": 50.0}
ROW["button_a"] = ROW["pot_a"] + POT_BOTTOM + CLEAR + BUTTON_HALF         # the pot's pins clear the cap's body
ROW["mega_1"] = ROW["button_a"] + BUTTON_HALF + CLEAR + SOCKET_HALF
ROW["pot_b"] = ROW["mega_1"] + SOCKET_HALF + CLEAR + POT_TOP
ROW["button_b"] = ROW["pot_b"] + POT_BOTTOM + CLEAR + BUTTON_HALF
ROW["mega_2"] = ROW["mega_1"] + (MEGA_PADS["D0"][1] + MEGA_PADS["D1"][1] - MEGA_PADS["A0"][1] - MEGA_PADS["A1"][1]) / 2
ROW["jacks"] = ROW["mega_2"] + SOCKET_HALF + CLEAR + JACK_PADS[0][2] / 2 + JACK_PADS[0][0]
ROW = {k: round(v, 2) for k, v in ROW.items()}
CONTROL_X = {"RV17": 15.5, "RV18": 51.5, "RV19": 84.0, "RV20": 105.5, "SW17": 121.0}
JACK_X = {"J1": STEP_X[0], "J2": STEP_X[1], "J3": STEP_X[4], "J4": STEP_X[5], "J5": STEP_X[6], "J6": STEP_X[7]}


def ring_angles(n):
    """Pointer angles (degrees clockwise from 12 o'clock) of an n-position knob's positions: the middle
    of each of the n equal parts of its travel, where the sketch's knobPosition() selects that position
    (it splits the reading evenly; the ends' few degrees of dead travel are ignored)."""
    return [KNOB_TRAVEL * ((i + 0.5) / n - 0.5) for i in range(n)]


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}


def _pot(ref, px, py):
    bx, by = board_xy(px, py)
    PLACEMENT[ref] = (bx, round(by - POT_SHAFT, 2), 0)          # pins down


for k, x in enumerate(STEP_X, start=1):
    _pot(f"RV{k}", x, ROW["pot_a"])
    _pot(f"RV{8 + k}", x, ROW["pot_b"])
    PLACEMENT[f"SW{k}"] = (*board_xy(x, ROW["button_a"]), 0)
    PLACEMENT[f"SW{8 + k}"] = (*board_xy(x, ROW["button_b"]), 0)
for ref in ("RV17", "RV18", "RV19", "RV20"):
    _pot(ref, CONTROL_X[ref], ROW["controls"])
PLACEMENT["SW17"] = (*board_xy(CONTROL_X["SW17"], ROW["controls"]), 0)
for ref, x in JACK_X.items():
    bx, by = board_xy(x, ROW["jacks"])
    PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)        # sleeve up

# The Mega on the rear, turned so its USB end meets the board's left edge (unplug the module and
# flash it from the side) and its D48-D53 stub points up into the strip under the B buttons, where
# the front is free. Seen from the front this puts footprint x along board x and footprint y along
# board y (up): the 2 x 16 row (A0-A15, D32-D47) in the lower strip, the 2 x 21 row in the upper.
MEGA_AT = (0.0, round(board_xy(0, ROW["mega_2"])[1] - (MEGA_PADS["A0"][1] + MEGA_PADS["A1"][1]) / 2, 2))


def mega_pad_xy(name):
    """Board mm (front view, y up) of a Mega socket pad."""
    x, y = MEGA_PADS[name]
    return round(MEGA_AT[0] + x, 3), round(MEGA_AT[1] + y, 3)


SOCKETED = [p for p in MEGA_PADS]       # every pad but the ICSP's (not in the table)


def front_bodies():
    """What sits flat on the front of the board, from the panel parts: [(ref, kind, (x0, y0, x1, y1))]
    boxes and [(ref, x, y, r)] pads, board mm, y up. Alpha pot: housing 9.5 wide, 4.85 above the shaft
    to 1 mm short of its pin row; pins 7.5 below the shaft, 1.8 mm pads; lugs on the shaft line at
    +-4.8, 2.72 x 3.24 pads. Thonk LED button: 7.5 square body. Jack: 9 wide, from 6.0 below the
    barrel to its sleeve lug 6.5 above."""
    boxes, pads = [], []
    for ref, (x, y, rot) in PLACEMENT.items():
        if ref.startswith("RV"):
            sy = y + POT_SHAFT
            boxes.append((ref, "pot", (x - 4.75, sy - 6.5, x + 4.75, sy + POT_TOP)))
            boxes += [(ref, "pot lug", (x + s * 4.8 - 1.36, sy - 1.62, x + s * 4.8 + 1.36, sy + 1.62)) for s in (-1, 1)]
            pads += [(ref, x + dx, sy - 7.5, 0.9) for dx in (-2.5, 0.0, 2.5)]
        elif ref.startswith("SW"):
            boxes.append((ref, "button", (x - BUTTON_HALF, y - BUTTON_HALF, x + BUTTON_HALF, y + BUTTON_HALF)))
        elif ref.startswith("J"):
            by = y + JACK_BARREL
            boxes.append((ref, "jack", (x - 4.5, by - 6.0, x + 4.5, by + JACK_TOP)))
            for dy, w, h in JACK_PADS:          # each oval pad as two circles along its long side
                pads += [(ref, x + s * (w - h) / 2, by + dy, h / 2) for s in (-1, 1)]
    return boxes, pads


def mega_check(clear=0.3):
    """Every socketed Mega pad clear of the panel parts on the front and of the board edge."""
    boxes, pads = front_bodies()
    bad = []
    for name in SOCKETED:
        px, py = mega_pad_xy(name)
        r = MEGA_PAD + clear
        for ref, kind, (x0, y0, x1, y1) in boxes:
            dx = max(x0 - px, 0.0, px - x1)
            dy = max(y0 - py, 0.0, py - y1)
            if math.hypot(dx, dy) < r:
                bad.append(f"Mega {name} under {ref} ({kind}): {math.hypot(dx, dy) - MEGA_PAD:.2f} mm")
        for ref, x, y, pr in pads:
            if math.hypot(px - x, py - y) < r + pr:
                bad.append(f"Mega {name} - {ref} pad: {math.hypot(px - x, py - y) - MEGA_PAD - pr:.2f} mm")
        if min(px, py, BOARD_W - px, BOARD_H - py) - MEGA_PAD < 0.5:
            bad.append(f"Mega {name}: closer than 0.5 mm to the board edge")
    return bad


def panel_pad_check(clear=0.3):
    """No panel part's pad (pot pins) under another panel part's body."""
    boxes, pads = front_bodies()
    bad = []
    for ref, px, py, pr in pads:
        for other, kind, (x0, y0, x1, y1) in boxes:
            if other == ref:
                continue
            gap = math.hypot(max(x0 - px, 0.0, px - x1), max(y0 - py, 0.0, py - y1)) - pr
            if gap < clear:
                bad.append(f"{ref} pad at ({px:.2f}, {py:.2f}) under {other} ({kind}): {gap:.2f} mm")
    return bad


def mega_margin():
    """Smallest front-side gap between a socket pad and a panel part's body or pad."""
    boxes, pads = front_bodies()
    gaps = []
    for name in SOCKETED:
        px, py = mega_pad_xy(name)
        gaps += [math.hypot(max(x0 - px, 0.0, px - x1), max(y0 - py, 0.0, py - y1)) - MEGA_PAD
                 for ref, kind, (x0, y0, x1, y1) in boxes]
        gaps += [math.hypot(px - x, py - y) - MEGA_PAD - pr for ref, x, y, pr in pads]
    return min(gaps)


# ---------------------------------------------------------------- netlist
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
    return Part(ref, "CP", value, {"2": plus, "1": minus}, label)


def D(ref, kind, anode, cathode, label=""):
    value = {"DBAT85": "BAT85", "D5819": "1N5819"}[kind]
    return Part(ref, kind, value, {"1": cathode, "2": anode}, label)


GND, VP, VN, V5, VDAC = "GND", "+12V", "-12V", "+5V", "VDAC"
# TL074 section pins: (out, in-, in+); A and B on the pin 1-7 side, C and D on the pin 8-14 side
SECTION = {"A": ("1", "2", "3"), "B": ("7", "6", "5"), "C": ("8", "9", "10"), "D": ("14", "13", "12")}
ROWS = {"A": (POTS_A, STEPS_A, LEDS_A), "B": (POTS_B, STEPS_B, LEDS_B)}
LED_COLOUR = {"A": "red", "B": "green"}                 # the preview's colours (open choice 1)
KNOB_NETS = {ref: name for name, ref in ADS_KNOBS.items()}
# (CCW pin 1, CW pin 3): DUTY like the step pots CW to GND (the sketch inverts both), ROWS, DIRECTION
# and BUTTONS CW to +5 V (their first position is fully counter-clockwise)
POT_ENDS = {"RV17": (GND, V5), "RV18": (GND, V5), "RV19": (GND, V5), "RV20": (V5, GND)}
ADS_INPUT = {"RV17": "A3", "RV18": "A0", "RV19": "A2", "RV20": "A1"}
# The breakouts' header pins, pin 1 first. The ADS1115 order is the same on Adafruit's 1085 and the
# generic boards; the MCP4725's follows Adafruit's 935 and has to be checked against the boards you use
# (open choice 5): only the footprint's pin numbers change.
BREAKOUT_PINS = {"ADS1115_MOD": ["VDD", "GND", "SCL", "SDA", "ADDR", "ALRT", "A0", "A1", "A2", "A3"],
                 "MCP4725_MOD": ["VCC", "GND", "SCL", "SDA", "A0", "OUT"]}
# tip net, switch-lug net (None = open): an unpatched input reads 0 V
JACK_NETS = {"J1": ("CLOCK_IN", GND), "J2": ("RESET_IN", GND), "J3": ("CV_A", None), "J4": ("GATE_A", None),
             "J5": ("CV_B", None), "J6": ("GATE_B", None)}


def step_of(ref):
    """(row, step) of RV1-RV16 / SW1-SW16."""
    n = int(ref[2:])
    return ("A" if n <= STEPS else "B"), (n - 1) % STEPS + 1


def panel_parts():
    parts = []
    for ref, label, _, _ in POTS:
        if ref in KNOB_NETS:
            (ccw, cw), wiper = POT_ENDS[ref], KNOB_NETS[ref]
        else:
            row, k = step_of(ref)
            ccw, cw, wiper = V5, GND, f"POT_{row}{k}"
        parts.append(Part(ref, "POT", "B10k", {"1": ccw, "2": wiper, "3": cw, "4": GND, "5": GND}, label))
    for ref, label, _, _ in BUTTONS:
        if ref == "SW17":                   # SHIFT: to GND on the pin's pull-up; its LED is left open
            parts.append(Part(ref, "SWLED", "Thonk LED button", {"1": GND, "2": GND, "3": "SHIFT", "4": "SHIFT"},
                              label))
            continue
        row, k = step_of(ref)
        parts.append(Part(ref, "SWLED", f"Thonk LED button, {LED_COLOUR[row]}",
                          {"1": V5, "2": V5, "3": f"BTN_{row}{k}", "4": f"BTN_{row}{k}",
                           "5": f"LEDA_{row}{k}", "6": f"LED_{row}{k}"}, label))
    for ref, label, _, _ in JACKS:
        tip, lug = JACK_NETS[ref]
        nets = {"1": GND, "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "PJ398SM", nets, label))
    return parts


def mega_wiring():
    """[(Mega pad, net)]: the sketch's pins, as circuit.py's tables copy them."""
    pins = [("GND1", GND), ("GND2", GND), ("5V1", V5), ("5V2", V5), ("D20", "SDA"), ("D21", "SCL"),
            ("D18", "CLOCK"), ("D2", "RESET"), ("D19", "SHIFT"), ("D17", "GATE_A_PIN"), ("D15", "GATE_B_PIN")]
    for row, (pots, steps, leds) in ROWS.items():
        for k in range(1, STEPS + 1):
            pins += [(pots[k - 1], f"POT_{row}{k}"), (steps[k - 1], f"BTN_{row}{k}"), (leds[k - 1], f"LED_{row}{k}")]
    return pins


def logic_parts():
    """The Mega and the three breakouts, wired by pin name."""
    ads = {"VDD": V5, "GND": GND, "SCL": "SCL", "SDA": "SDA", "ADDR": GND}     # ALRT open
    ads.update({ADS_INPUT[ref]: net for ref, net in KNOB_NETS.items()})
    return [
        Part("U1", "MEGA2560PRO", "Mega 2560 Pro (Embed)", dict(mega_wiring()), "on 2 x 21, 2 x 16, 2 x 3 sockets"),
        Part("U2", "ADS1115_MOD", "ADS1115 breakout", ads, "0x48: ROWS, DIRECTION, BUTTONS, DUTY"),
        Part("U3", "MCP4725_MOD", "MCP4725 breakout (A0 part)",
             {"VCC": VDAC, "GND": GND, "SCL": "SCL", "SDA": "SDA", "A0": VDAC, "OUT": "DAC_A"}, "0x61: CV A"),
        Part("U4", "MCP4725_MOD", "MCP4725 breakout (A0 part)",
             {"VCC": VDAC, "GND": GND, "SCL": "SCL", "SDA": "SDA", "A0": GND, "OUT": "DAC_B"}, "0x60: CV B"),
    ]


def output_parts():
    """U5: CV A on section A, GATE A on B, CV B on C, GATE B on D."""
    roles = {}
    parts = []
    for i, (ch, cv, gate) in enumerate((("A", "A", "B"), ("B", "C", "D"))):
        roles[cv] = (f"CV_{ch}_O", f"CV_{ch}_N", f"DAC_{ch}")
        roles[gate] = (f"GATE_{ch}_O", f"GATE_{ch}_N", f"GATE_{ch}_P")
        r = 201 + 8 * i
        parts += [
            R(f"R{r}", "10k 1%", f"CV_{ch}_N", GND, f"CV {ch}: gain x2"),
            R(f"R{r + 1}", "10k 1%", f"CV_{ch}", f"CV_{ch}_N", f"CV {ch}: feedback from the jack side of the 1k"),
            R(f"R{r + 2}", "1k", f"CV_{ch}_O", f"CV_{ch}", f"CV {ch}: series"),
            C(f"C{201 + i}", "100p", f"CV_{ch}_O", f"CV_{ch}_N", f"CV {ch}: stable into a cable"),
            R(f"R{r + 3}", "100k", f"GATE_{ch}_PIN", GND, f"GATE {ch}: low while the Mega boots"),
            R(f"R{r + 4}", "10k", f"GATE_{ch}_PIN", f"GATE_{ch}_P", f"GATE {ch}: limits the current with the rails off"),
            R(f"R{r + 5}", "10k", f"GATE_{ch}_N", GND, f"GATE {ch}: gain x2"),
            R(f"R{r + 6}", "10k", f"GATE_{ch}_O", f"GATE_{ch}_N", f"GATE {ch}: feedback"),
            R(f"R{r + 7}", "1k", f"GATE_{ch}_O", f"GATE_{ch}", f"GATE {ch}: series"),
        ]
    nets = {"4": VP, "11": VN}
    for sec, trio in roles.items():
        nets.update(dict(zip(SECTION[sec], trio)))
    parts += [Part("U5", "TL074", "TL074", nets, "CV and gate outputs"),
              C("C203", "100n", VP, GND, "U5 +12 V"), C("C204", "100n", GND, VN, "U5 -12 V")]
    return parts


def input_parts():
    parts = []
    for i, (tip, pin) in enumerate((("CLOCK_IN", "CLOCK"), ("RESET_IN", "RESET"))):
        r = 101 + 2 * i
        parts += [
            R(f"R{r}", "22k", tip, pin, f"{pin}: series"),
            R(f"R{r + 1}", "100k", pin, GND, f"{pin}: divider with the 22k, about 3.7 V threshold"),
            C(f"C{101 + i}", "1n", pin, GND, f"{pin}: against crosstalk spikes, 18 us"),
            D(f"D{r}", "DBAT85", pin, V5, f"{pin}: clamp to +5 V"),
            D(f"D{r + 1}", "DBAT85", GND, pin, f"{pin}: clamp to GND"),
        ]
    return parts


def network_parts():
    """Bussed 9-pin SIPs, pin 1 common: button pull-downs and button LED resistors."""
    parts = []
    for i, row in enumerate(ROWS):
        parts.append(Part(f"RN{1 + i}", "RN9", "10k bussed",
                          {"1": GND, **{str(k + 1): f"BTN_{row}{k}" for k in range(1, STEPS + 1)}},
                          f"row {row} button pull-downs"))
        parts.append(Part(f"RN{3 + i}", "RN9", "1k bussed",
                          {"1": V5, **{str(k + 1): f"LEDA_{row}{k}" for k in range(1, STEPS + 1)}},
                          f"row {row} button LEDs, about 3 mA"))
    return parts


def power_parts():
    hdr = {"1": "N12_IN", "2": "N12_IN", "9": "P12_IN", "10": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 9)})
    return [
        Part("J7", "HDR10", "2 x 5 shrouded, 2.54 mm", hdr, "POWER"),
        D("D901", "D5819", "P12_IN", "P12_D", "+12 V reverse protection"),
        D("D902", "D5819", "N12_D", "N12_IN", "-12 V reverse protection: cathode on the header"),
        R("R901", "10R", "P12_D", VP, "+12 V filter: the TL074 and the reference, not the switcher"),
        R("R902", "10R", "N12_D", VN, "-12 V filter"),
        CP("C901", "47u", VP, GND, "+12 V bulk"),
        CP("C902", "47u", GND, VN, "-12 V bulk"),
        Part("U7", "R78E", "R-78E5.0-0.5", {"1": "P12_D", "2": GND, "3": V5}, "5 V for the Mega's 5V pins"),
        CP("C903", "10u", "P12_D", GND, "switcher input"),
        CP("C904", "10u", V5, GND, "switcher output"),
        R("R903", "820R", VP, VDAC, "reference feed, about 7 mA"),
        Part("U6", "LM4040", "LM4040-5.0", {"1": GND, "2": VDAC, "3": GND}, "the DACs' supply and reference, 5.000 V"),
        CP("C905", "10u", VDAC, GND, "DAC supply"),
    ]


def all_parts():
    return panel_parts() + logic_parts() + output_parts() + input_parts() + network_parts() + power_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Netlist problems: single-pin nets, designators used twice, TL074s with a pin left out, an op-amp
    output that drives another output's net, a Mega pad wired twice or not in the footprint, and the
    panel parts against PLACEMENT."""
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
    pads = collections.Counter(pad for pad, _ in mega_wiring())
    bad += [f"Mega {pad} wired {c} times" for pad, c in pads.items() if c > 1]
    bad += [f"Mega {pad} is not a socketed pad" for pad in pads if pad not in SOCKETED]
    panel = {p.ref for p in parts if p.kind in ("POT", "SWLED", "JACK")}
    bad += [f"{ref} on the panel but not in the netlist" for ref in sorted(set(PLACEMENT) - panel)]
    bad += [f"{ref} in the netlist but not placed" for ref in sorted(panel - set(PLACEMENT))]
    return bad


SKETCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "eight", "eight.ino")


def sketch_constants():
    """The sketch's `const int` constants and tables, as written: {'CLOCK_IN': '18', 'POTS_A': ['A7', ..]}."""
    src = open(SKETCH, encoding="utf-8").read()
    consts = {m.group(1): [t.strip() for t in m.group(2).split(",")]
              for m in re.finditer(r"const int (\w+)\s*\[\]\s*=\s*\{([^}]*)\}", src)}
    consts.update({m.group(1): m.group(2) for m in re.finditer(r"const int (\w+)\s*=\s*(A?\d+);", src)})
    return consts


def sketch_check():
    """The netlist is built from circuit.py's copies of the sketch's pins: compare them with the sketch
    itself (Mega pins and the ADS1115 channel of each knob), and look for a pin the sketch drives as an
    output that the board wires to an input."""
    s = sketch_constants()
    pad = lambda tok: tok if tok.startswith("A") else f"D{tok}"
    pins = {name: [pad(t) for t in v] if isinstance(v, list) else pad(v) for name, v in s.items()}
    ours = {"POTS_A": POTS_A, "POTS_B": POTS_B, "STEPS_A": STEPS_A, "STEPS_B": STEPS_B, "LEDS_A": LEDS_A,
            "LEDS_B": LEDS_B, "SHIFT_BUTTON": "D19", "CLOCK_IN": "D18", "RESET_IN": "D2", "GATE_A": "D17",
            "GATE_B": "D15"}
    bad = [f"{name}: the sketch has {pins.get(name)}, circuit.py {p}" for name, p in ours.items() if pins.get(name) != p]
    bad += [f"{name}: the sketch reads ADS A{s.get(name)}, the board wires {ref} to {ADS_INPUT[ref]}"
            for name, ref in ADS_KNOBS.items() if f"A{s.get(name)}" != ADS_INPUT[ref]]
    wired = dict(mega_wiring())
    inputs = {"CLOCK", "RESET", "SHIFT", "SDA", "SCL"} | {n for n in wired.values() if n.startswith(("POT_", "BTN_"))}
    driven = set(pins.get("LEDS_A", []) + pins.get("LEDS_B", []) + [pins.get("GATE_A"), pins.get("GATE_B")])
    bad += [f"the sketch drives {pin} as an output; the board wires it to {wired[pin]}"
            for pin in sorted(driven) if wired.get(pin) in inputs]
    return bad


def value(v):
    """'22k' -> 22000.0, '820R' -> 820.0, '10k 1%' -> 10000.0, '1n' -> 1e-9."""
    m = re.match(r"([\d.]+)([RkMpnu]?)", v)
    return float(m.group(1)) * {"": 1, "R": 1, "k": 1e3, "M": 1e6, "p": 1e-12, "n": 1e-9, "u": 1e-6}[m.group(2)]


BUS = (11.4, 12.6)                      # Eurorack +12 V, +-5 %
DIODE, LED_VF = 0.35, {"red": 2.0, "green": 3.0}


def numbers():
    """What the part values give, against the targets in docs/design.md: [(what, value, ok)]."""
    p = {x.ref: x for x in all_parts()}
    v = lambda ref: value(p[ref].value)
    out = []
    for name, rs, rp, c in (("CLOCK", "R101", "R102", "C101"), ("RESET", "R103", "R104", "C102")):
        k = (v(rs) + v(rp)) / v(rp)     # the ATmega reads high above 0.6 VCC at most, low below 0.3 VCC at least
        tau = v(rs) * v(rp) / (v(rs) + v(rp)) * v(c)
        out.append((f"{name} trips at the jack", f"{0.3 * 5 * k:.1f} .. {0.6 * 5 * k:.1f} V, edge filter {tau * 1e6:.0f} us",
                    0.3 * 5 * k > 1.0 and 0.6 * 5 * k < 4.5 and tau < 50e-6))
    for ch, rg, rf in (("A", "R201", "R202"), ("B", "R209", "R210")):
        g = 1 + v(rf) / v(rg)
        out.append((f"CV {ch} gain", f"x{g:.2f}: the 8 V range needs {8 / g:.2f} V of the DAC's 5.00", 8 / g < 4.5))
    for ch, rg, rf in (("A", "R206", "R207"), ("B", "R214", "R215")):
        hi = 5.0 * (1 + v(rf) / v(rg))
        out.append((f"GATE {ch} high", f"{min(hi, BUS[0] - DIODE - 1.5):.1f} V (x2 of 5 V, the TL074 tops out "
                    f"about 1.5 V under its rail)", hi >= 8.0))
    dac_load = 2 * 0.4e-3 + 4 * 5.0 / 10e3          # two MCP4725s, both boards' 10k I2C pull-ups held low
    i_lo = (BUS[0] - DIODE - 0.15 - 5.0) / v("R903") - dac_load
    i_hi = (BUS[1] - DIODE - 5.0) / v("R903")
    out.append(("LM4040 current", f"{i_lo * 1e3:.1f} .. {i_hi * 1e3:.1f} mA (it needs 0.1, takes 15 at most)",
                0.5e-3 < i_lo and i_hi < 15e-3))
    leds = {row: (5.0 - LED_VF[c] - 0.1) / value("1k") for row, c in LED_COLOUR.items()}
    out.append(("button LEDs", ", ".join(f"row {r} {i * 1e3:.1f} mA" for r, i in leds.items()), all(1e-3 < i < 5e-3 for i in leds.values())))
    load = 0.050 + STEPS * sum(leds.values()) + len(POTS) * 5.0 / 10e3 + 0.5e-3   # Mega, LEDs, pots, ADS1115
    out.append(("+5 V load", f"{load * 1e3:.0f} mA of the switcher's 500; from +12 V about "
                f"{5.0 * load / 0.8 / (BUS[0] - DIODE) * 1e3:.0f} mA", load < 0.4))
    return out


if __name__ == "__main__":
    print(f"{HP}HP: board {BOARD_W} x {BOARD_H} on a {PANEL_W:.2f} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
    print("rows (panel y): " + ", ".join(f"{k} {v}" for k, v in ROW.items()))
    print(f"Mega at board {MEGA_AT}, socket rows at panel y {ROW['mega_1']} and {ROW['mega_2']}")
    problems = mega_check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} socket clearance problems; smallest gap {mega_margin():.2f} mm")
    problems = panel_pad_check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} panel parts with a pad under another's body")
    parts = all_parts()
    kinds = collections.Counter(p.kind for p in parts)
    print(f"netlist: {len(parts)} parts, {len(nets_of(parts))} nets; " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    problems = check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} netlist problems")
    problems = sketch_check()
    for b in problems:
        print("  " + b)
    print(f"{len(problems)} differences from the sketch's pins")
    for what, val, ok in numbers():
        print(f"  {'ok ' if ok else 'BAD'} {what}: {val}")
