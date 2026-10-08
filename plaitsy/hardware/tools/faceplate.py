"""Faceplate board (FB): everything that goes through the panel, plus the pot
multiplexer, the cable-detection (normalization probe) resistors, the pot
smoothing caps and one LED resistor.

Seen from the front (component side towards the panel). 23 columns x 41 rows.
Column 11 is the panel's centre line, x = 30.31 mm; row r sits at
y = 13.95 + 2.54 r mm from the top of the 128.5 mm panel.

Interconnect: the main board sits behind this board, copper side to copper
side, so hole (r, c) here meets hole (r, 22 - c) on the main board. The
interconnect pins are one-pin parts named P<row>_<col>.
"""
import sb
from sb import Board, Part, PartDef, Pin, PITCH
from circuit import faceplate_parts, LED_ORDER

ROWS, COLS = 41, 23
X0, Y0 = 30.31 - 11 * PITCH, 13.95  # panel mm of hole (0, 0)

PIN = PartDef("custom-plaitsy-ic-pin", "Board-to-board pin", "connector-1", "P",
              [Pin("1", "1", 0, 0)], category="connector", custom=True, has_value=False)


def panel_xy(r, c):
    return X0 + c * PITCH, Y0 + r * PITCH


JACK_COLS = [2, 6, 11, 16, 20]
JACK_ROW1, JACK_ROW2 = 30, 36
LED_ROW0 = 4

# rigid parts: ref -> (pos, rot)
RIGID = {
    "SW1": ((0, 8), 90), "SW2": ((0, 12), 90),
    **{f"D{k + 1}": ((LED_ROW0 + 2 * k, 10), 180) for k in range(8)},
    "RV1": ((5, 1), 180),    # FREQUENCY  legs col 1,  shaft ~col 4
    "RV2": ((5, 17), 0),     # HARMONICS  legs col 21, shaft ~col 18
    "RV3": ((17, 0), 180),   # TIMBRE     legs col 0,  shaft ~col 3 (row 18)
    "RV4": ((17, 18), 0),    # MORPH      legs col 22, shaft ~col 19 (row 18)
    "RV5": ((25, 0), 180),   # TIMBRE att legs col 0,  shaft ~col 3
    "RV6": ((25, 8), 180),   # FM att     legs col 8,  shaft ~col 11
    "RV7": ((25, 18), 0),    # MORPH att  legs col 22, shaft ~col 19
    "U1": ((9, 4), 180),     # 74HC4051: left legs col 4, right legs col 7, rows 9..16
    **{ref: ((srow, col - 1), 0) for srow, refs in
       ((JACK_ROW1, ["J1", "J2", "J3", "J4", "J5"]), (JACK_ROW2, ["J6", "J7", "J8", "J9", "J10"]))
       for ref, col in zip(refs, JACK_COLS)},
}

# two-lead parts: ref -> (pin1 hole, pin2 hole)
FLEX = {
    "C8": ((16, 3), (17, 5)),    # mux decoupling: VCC row 16 / GND row 17 (diagonal)
    # normalization probe resistors: jack switch lug -> probe bus
    "R9": ((31, 8), (28, 8)),    # TIMBRE
    "R10": ((31, 13), (28, 13)), # FM
    "R11": ((31, 18), (28, 18)), # MORPH
    "R12": ((37, 4), (35, 4)),   # TRIG
    "R13": ((37, 8), (35, 8)),   # LEVEL
    # LED8 red resistor, in line on row 19
    "R1": ((19, 13), (19, 15)),  # 1/8 W, or a 1/4 W standing
}

# interconnect pins: (row, col) -> net
PINS = {
    **{(4 + i, 16): LED_ORDER[i] for i in range(15)},
    (19, 16): "LED8_R_IO",
    (7, 7): "BTN_A",
    (8, 9): "BTN_B",
    (9, 3): "MUX_S2", (10, 3): "MUX_S1", (11, 3): "MUX_S0",
    (14, 8): "MUX_OUT",
    (22, 9): "PROBE",
    (23, 9): "3V3A",
    (4, 5): "GND", (25, 6): "GND",
    # jack tips -> main-board op-amps / outputs
    (34, 0): "CV_MODEL", (34, 8): "CV_TIMBRE", (34, 13): "CV_FM", (34, 18): "CV_MORPH",
    (34, 22): "CV_HARMO", (40, 0): "CV_TRIG", (40, 8): "CV_LEVEL", (40, 13): "CV_VOCT",
    (40, 18): "OUT", (40, 22): "AUX",
}

# The board is built from two pieces of stripboard (24-strip boards): upper
# piece rows 0..21, lower piece rows 22..40. Links that cross this line are
# short flying wires between the pieces.
SPLIT = 21


# Cuts placed by hand before routing (the router keeps them)
MANUAL_CUTS = [
    (r, 8, "between") for r in (9, 11, 13, 15)  # mux right legs | LED cathode rows
]


# Links placed by hand before routing (the router keeps them): straight
# routes for the nets it would otherwise run diagonally across the board.
MANUAL_LINKS = [
    ((3, 15), (1, 15), "BTN_B"), ((1, 6), (8, 6), "BTN_B"),        # right button -> row 8
    ((26, 7), (20, 7), "ATT_FM"), ((20, 8), (16, 8), "ATT_FM"),    # FM att -> mux A4
    ((17, 17), (23, 17), "3V3A"),                                   # MORPH top leg
]


def build(pins=None, extra_links=(), extra_cuts=()):
    b = Board("faceplate", ROWS, COLS)
    for p in faceplate_parts():
        if p.ref in RIGID:
            p.pos, p.rot = RIGID[p.ref]
        elif p.ref in FLEX:
            p.p1, p.p2 = FLEX[p.ref]
        b.add(p)
    for i, ((r, c), net) in enumerate(sorted((pins or PINS).items())):
        b.add(Part(f"P{r}_{c}", PIN, nets={"1": net}, pos=(r, c), sch=(3400 + 240 * (i % 4), 100 + 80 * (i // 4))))
    for a, c, net in list(MANUAL_LINKS) + list(extra_links):
        b.link(a, c, net)
    for r, c, k in list(MANUAL_CUTS) + list(extra_cuts):
        b.cut(r, c, k)
    return b


if __name__ == "__main__":
    b = build()
    b.check()
    sb.render(b, "../stripboard/_fb_preview.png", title="Faceplate board - component side (front)")
