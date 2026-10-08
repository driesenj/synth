"""The whole Plaitsy circuit as one netlist, with a schematic position for
every part. Board layouts (faceplate.py, mainboard.py) place these same parts
on stripboard; the schematic export draws them on the editor's canvas.

Net naming
  CV_*      jack tip of a CV input (faceplate)       -> main board op-amp
  IN_*      op-amp inverting input
  OA_*      op-amp output
  ADC_*     Seed ADC pin (after the series resistor)
  POT_*, ATT_*  pot wipers (faceplate, into the mux)
  LEDn_R/G  LED anodes (faceplate side of the LED resistor)
  D0..D14   Seed GPIOs driving the LEDs through 470R resistors
  TN_*      jack switch (normal) lugs, fed by the normalization probe
"""
from sb import (Part, PartDef, Pin, RESISTOR, CAPACITOR, DIODE, PUSHBUTTON, JACK, POT9,
                LED_BI, HC4051, TL074, G)

# --------------------------------------------------------------------------
# Daisy Seed plugged into Rob Heel's seed_power_opamps breakout, as it lands
# on the main board: two socket strips 6 holes apart, USB/audio end up.
# Left strip = Seed pins 1-20 side, right strip = Seed pins 21-40 side.
# Positions with no socket contact (unused breakout pins) are left out, so
# the copper strip under them is free for other signals.
# --------------------------------------------------------------------------
LEFT = {  # row: name   (Seed pin numbers in brackets)
    1: "GND (J5)", 3: "GND (J5)",
    4: "D0 [1]", 5: "D1 [2]", 6: "D2 [3]", 7: "D3 [4]", 8: "D4 [5]", 9: "D5 [6]",
    10: "D6 [7]", 11: "D7 [8]", 12: "D8 [9]", 13: "D9 [10]", 14: "D10 [11]",
    15: "D11 [12]", 16: "D12 [13]", 17: "D13 [14]", 18: "D14 [15]",
    23: "AGND [20]", 25: "GND (J1)", 26: "-12V (J1)",
}
RIGHT = {
    0: "AOUT1 (J4)", 1: "GND (J4)", 2: "AOUT2 (J4)", 3: "GND (J4)",
    4: "DGND [40]", 6: "3V3D [38]", 7: "D30 [37]", 8: "D29 [36]", 9: "A11 D28 [35]",
    10: "D27 [34]", 11: "D26 [33]", 12: "A10 D25 [32]", 13: "A9 D24 [31]",
    14: "A8 D23 [30]", 15: "A7 D22 [29]", 16: "A6 D21 [28]", 17: "A5 D20 [27]",
    18: "A4 D19 [26]", 19: "A3 D18 [25]", 20: "A2 D17 [24]", 21: "A1 D16 [23]",
    22: "A0 D15 [22]", 23: "3V3A [21]", 25: "GND (J3)", 26: "+12V (J3)",
}
SEED_PINS = [Pin(f"L{r}", n, r, 0) for r, n in sorted(LEFT.items())] + \
            [Pin(f"R{r}", n, r, 6) for r, n in sorted(RIGHT.items())]
SEED = PartDef("custom-plaitsy-seed-breakout",
               "Daisy Seed on seed_power_opamps breakout (socket strips)",
               "custom-footprint-custom-plaitsy-seed-breakout", "U", SEED_PINS,
               category="ic", custom=True, has_value=False, width=7, height=29,
               internal_groups=[["L1", "L3", "L23", "L25", "R1", "R3", "R4", "R25"]])

# Breakout orientation on the main board: left strip (Seed pins 1-20, GPIO
# side) in column 1, right strip (pins 21-40, ADC side) in column 7, USB/audio
# end at row 0. LEDk on faceplate rows 4+2k (green) / 5+2k (red) lines up
# with D0..D14 on main-board rows 4..18; the 16th LED line uses A3 (row 19).
LED_ORDER = [f"LED{k // 2 + 1}_{'GR'[k % 2]}" for k in range(16)]  # by board row 4..19

# Right-strip assignments (ADC side). CV channels get ADC pins; the rest are
# plain GPIOs. Edited together with mainboard.py.
ASSIGN = {
    # fixed by the faceplate routing (board-to-board pins on these rows)
    "R7": "BTN_A", "R8": "BTN_B", "R9": "MUX_S2", "R10": "MUX_S1", "R11": "MUX_S0",
    "R14": "MUX_OUT", "R19": "LED8_R_IO", "R22": "PROBE",
    # CV inputs: any of these ADC pins works; the firmware has a table for it
    "R12": "ADC_MODEL", "R13": "ADC_HARMO", "R15": "ADC_TIMBRE", "R16": "ADC_MORPH",
    "R17": "ADC_FM", "R18": "ADC_LEVEL", "R20": "ADC_TRIG", "R21": "ADC_VOCT",
}

# What every Seed pin does (net names)
SEED_NETS = {
    "L1": "GND", "L3": "GND", "L23": "GND", "L25": "GND", "L26": "-12V",
    "R1": "GND", "R3": "GND", "R4": "GND", "R25": "GND", "R26": "+12V",
    "R0": "OUT", "R2": "AUX", "R23": "3V3A",
    **{f"L{4 + i}": f"D{i}" for i in range(15)},
    **ASSIGN,
}

# CV input channels: (name, gain resistor, filter cap, bias, TL074 ref, section)
# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
CHANNELS = [
    ("MODEL", "13k", "1n", "BIAS_A", "U3", 1),
    ("TIMBRE", "13k", "1n", "BIAS_A", "U3", 2),
    ("FM", "13k", "1n", "BIAS_A", "U3", 3),
    ("MORPH", "13k", "1n", "BIAS_A", "U3", 4),
    ("HARMO", "13k", "1n", "BIAS_A", "U4", 1),
    ("TRIG", "13k", "100p", "BIAS_A", "U4", 2),
    ("LEVEL", "13k", "1n", "BIAS_A", "U4", 3),
    ("VOCT", "33k", "1n", "BIAS_V", "U4", 4),
]


def _r(ref, value, n1, n2, sch, rot=0):
    return Part(ref, RESISTOR, value=value, nets={"1": n1, "2": n2}, sch=sch, sch_rot=rot,
                package="r-mf-quarter")


def _c(ref, value, n1, n2, sch, rot=0):
    return Part(ref, CAPACITOR, value=value, nets={"1": n1, "2": n2}, sch=sch, sch_rot=rot,
                package="cap-ceramic")


def main_board_parts():
    """Everything on the main board except the interconnect sockets."""
    parts = []
    parts.append(Part("U2", SEED, value="Daisy Seed + seed_power_opamps",
                      nets=dict(SEED_NETS), sch=(300, 420)))
    # op-amps
    tl_nets = {"U3": {"4": "+12V", "11": "-12V"}, "U4": {"4": "+12V", "11": "-12V"}}
    for name, _, _, bias, u, s in CHANNELS:
        out, inm, inp = SECTION[s]
        tl_nets[u].update({out: f"OA_{name}", inm: f"IN_{name}", inp: bias})
    parts.append(Part("U3", TL074, value="TL074", nets=tl_nets["U3"], sch=(860, 240)))
    parts.append(Part("U4", TL074, value="TL074", nets=tl_nets["U4"], sch=(860, 620)))
    # channels: one row each
    n = 21
    for i, (name, rf, cf, bias, u, s) in enumerate(CHANNELS):
        y = 80 + i * 180
        x = 1200
        rs = "1k"
        parts.append(_r(f"R{n}", "100k", f"CV_{name}", f"IN_{name}", (x, y))); n += 1
        parts.append(_r(f"R{n}", rf, f"IN_{name}", f"OA_{name}", (x + 160, y))); n += 1
        parts.append(_r(f"R{n}", rs, f"OA_{name}", f"ADC_{name}", (x + 320, y))); n += 1
    nc = 21
    for i, (name, rf, cf, bias, u, s) in enumerate(CHANNELS):
        y = 80 + i * 180
        parts.append(_c(f"C{nc}", cf, f"IN_{name}", f"OA_{name}", (1680, y))); nc += 1
    # V/OCT clamps: keep the ADC pin inside 0..3.3 V for out-of-range pitch CV
    yv = 80 + 7 * 180
    parts.append(Part("D21", DIODE, value="BAT85", nets={"1": "ADC_VOCT", "2": "3V3A"},
                      sch=(1940, yv - 60), package="do35"))
    parts.append(Part("D22", DIODE, value="BAT85", nets={"1": "GND", "2": "ADC_VOCT"},
                      sch=(1940, yv + 80), package="do35"))
    # bias dividers (below the Seed)
    parts.append(_r(f"R{n}", "15k", "3V3A", "BIAS_A", (200, 980))); n += 1
    parts.append(_r(f"R{n}", "12k", "BIAS_A", "GND", (200, 1140))); n += 1
    parts.append(_c(f"C{nc}", "1u", "BIAS_A", "GND", (360, 1060))); nc += 1
    parts.append(_r(f"R{n}", "13k", "3V3A", "BIAS_V", (540, 980))); n += 1
    parts.append(_r(f"R{n}", "15k", "BIAS_V", "GND", (540, 1140))); n += 1
    parts.append(_c(f"C{nc}", "1u", "BIAS_V", "GND", (700, 1060))); nc += 1
    # LED resistors: Seed GPIO -> LED anode line on the faceplate
    for i in range(15):
        parts.append(_r(f"R{60 + i}", "470", f"D{i}", LED_ORDER[i], (2200 + (i % 5) * 160, 80 + (i // 5) * 180)))
    # supply decoupling, one pair per TL074
    for k, x in enumerate((880, 1040)):
        parts.append(_c(f"C{nc}", "100n", "+12V", "GND", (x, 980))); nc += 1
        parts.append(_c(f"C{nc}", "100n", "GND", "-12V", (x, 1140))); nc += 1
    return parts


# ------------------------------------------------------------------ faceplate
JACKS = [  # ref, panel label, tip net, normal (switch) net
    ("J1", "MODEL", "CV_MODEL", "GND"),
    ("J2", "TIMBRE", "CV_TIMBRE", "TN_TIMBRE"),
    ("J3", "FM", "CV_FM", "TN_FM"),
    ("J4", "MORPH", "CV_MORPH", "TN_MORPH"),
    ("J5", "HARMO", "CV_HARMO", "GND"),
    ("J6", "TRIG", "CV_TRIG", "TN_TRIG"),
    ("J7", "LEVEL", "CV_LEVEL", "TN_LEVEL"),
    ("J8", "V/OCT", "CV_VOCT", "GND"),
    ("J9", "OUT", "OUT", None),
    ("J10", "AUX", "AUX", None),
]
POTS = [  # ref, label, wiper net, mux input pin (74HC4051 pin number)
    ("RV1", "FREQUENCY", "POT_FREQ", "12"),   # A3
    ("RV2", "HARMONICS", "POT_HARM", "13"),   # A0
    ("RV3", "TIMBRE", "POT_TIMBRE", "14"),    # A1
    ("RV4", "MORPH", "POT_MORPH", "15"),      # A2
    ("RV5", "TIMBRE att.", "ATT_TIMBRE", "5"),  # A5
    ("RV6", "FM att.", "ATT_FM", "1"),        # A4
    ("RV7", "MORPH att.", "ATT_MORPH", "2"),  # A6
]
MUX_ADDR = {"12": 3, "13": 0, "14": 1, "15": 2, "1": 4, "5": 5, "2": 6, "4": 7}  # 4051 pin -> channel number


def faceplate_parts():
    parts = []
    # jacks + probe resistors
    nr = 9
    for i, (ref, label, tip, tn) in enumerate(JACKS):
        x = 200 + (i % 5) * 260
        y = 1500 + (i // 5) * 360
        nets = {"1": "GND", "3": tip}
        if tn:
            nets["2"] = tn
        else:
            nets["2"] = f"NC_TN_{label}"  # isolated on the board; drawn unconnected
        parts.append(Part(ref, JACK, value=label, nets=nets, sch=(x, y)))
        if tn and tn.startswith("TN_"):
            parts.append(_r(f"R{nr}", "10k", tn, "PROBE", (x + 100, y + 160))); nr += 1
    # pots, wiper caps, mux
    for i, (ref, label, wiper, _) in enumerate(POTS):
        x = 1700 + (i % 4) * 260
        y = 1500 + (i // 4) * 360
        parts.append(Part(ref, POT9, value=f"B10k {label}", nets={"1": "GND", "2": wiper, "3": "3V3A"},
                          sch=(x, y)))
    mux_nets = {"16": "3V3A", "8": "GND", "7": "GND", "6": "GND", "3": "MUX_OUT",
                "11": "MUX_S0", "10": "MUX_S1", "9": "MUX_S2", "4": "GND"}  # A7 unused
    for _, _, wiper, mpin in POTS:
        mux_nets[mpin] = wiper
    parts.append(Part("U1", HC4051, value="74HC4051 (or CD4051B)", nets=mux_nets, sch=(2720, 1860)))
    parts.append(_c("C8", "100n", "3V3A", "GND", (2720, 2120)))
    # LEDs: cathodes to GND; the anodes are driven through resistors on the
    # main board, except LED8 red whose resistor sits on this board.
    for k in range(8):
        x = 200 + (k % 4) * 420
        y = 2400 + (k // 4) * 360
        parts.append(Part(f"D{k + 1}", LED_BI, value="3mm R/G CC",
                          nets={"1": f"LED{k + 1}_R", "3": f"LED{k + 1}_G", "2": "GND"},
                          sch=(x, y)))
    parts.append(_r("R1", "470", "LED8_R", "LED8_R_IO", (1460, 2560)))
    # buttons
    parts.append(Part("SW1", PUSHBUTTON, value="left: bank A / settings",
                      nets={"2": "BTN_A", "1": "GND"}, sch=(1900, 2400)))
    parts.append(Part("SW2", PUSHBUTTON, value="right: bank B / octave",
                      nets={"2": "GND", "1": "BTN_B"}, sch=(2200, 2400)))
    return parts


def all_parts():
    return main_board_parts() + faceplate_parts()


if __name__ == "__main__":
    import collections
    parts = all_parts()
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    for n in sorted(nets):
        if len(nets[n]) < 2 and not n.startswith("NC_"):
            print("single-pin net:", n, nets[n])
    print(len(parts), "parts,", len(nets), "nets")
