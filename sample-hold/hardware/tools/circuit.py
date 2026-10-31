"""S&H: sample & hold, noise and random, after Moritz Klein's MKI x ES.EDU
S&H/Noise (SH_MANUAL_v1.pdf, production schematic EDUSH2 rev 2.0, p. 60).
10HP Eurorack, like the original.

Panel first (module-design skill): this file holds the panel parts and
their placement; the netlist follows once the panel is agreed.

Panel parts:
  3 pots            RATE (internal clock), LEVEL (input attenuator), SLEW
  1 LED             the clock: lights on every trigger, internal or patched
  9 jacks           CLOCK, IN, SLEW IN; GATE, WHITE, S&H; PINK, BLUE, SLEW
Normals (switch lugs, as on the MKI board): CLOCK takes the internal clock,
IN takes white noise, SLEW IN takes the S&H output. GATE is new: the
TL074 section the MKI board leaves unused, as a comparator on the held
voltage, so each clock is a coin toss.

PLACEMENT: board frame, front view, x right, y up, origin at the board's
bottom-left corner, mm; footprint origins (jacks: the WQP518MA origin,
0.78 mm above the barrel; pots: the PTV09A origin, 4.0 mm below the
shaft; the LED: its body).
"""

HP = 10
PANEL_W, PANEL_H = 50.5, 128.5          # HP x 5.08 - 0.3
BOARD_W, BOARD_H = 49.3, 108.0          # 0.6 mm in from each side, like Plaitsy and Marblesy
JACK_BARREL, POT_SHAFT = -0.78, 4.0

# ref, panel label, role, normalled from (None = nothing / open)
JACKS = [
    ("J1", "CLOCK", "clock in", "internal clock"),
    ("J2", "IN", "S&H input", "white noise"),
    ("J3", "SLEW IN", "slew input", "S&H output"),
    ("J4", "GATE", "random gate out", None),
    ("J5", "WHITE", "white noise out", None),
    ("J6", "S&H", "S&H out", None),
    ("J7", "PINK", "pink noise out", None),
    ("J8", "BLUE", "blue noise out", None),
    ("J9", "SLEW", "slew out", None),
]
# ref, label, value (Alpha 9 mm)
POTS = [("RV1", "RATE", "B500k"), ("RV2", "LEVEL", "B100k"), ("RV3", "SLEW", "A1M")]
LEDS = [("D1", "CLOCK", "3 mm red")]

# What the user sees, in panel mm from the top-left corner (y down). Three
# columns, one per control: RATE over the clock LED and the CLOCK jack,
# LEVEL over IN, SLEW over SLEW IN. The outputs fill the two lower rows,
# which sit at Marblesy's and Side FXy's jack heights so the rows line up in
# the rack; the inputs are one row above them.
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
        PLACEMENT[ref] = (round(x, 2), round(y - JACK_BARREL, 2), 0)
    elif ref.startswith("RV"):
        PLACEMENT[ref] = (round(x, 2), round(y - POT_SHAFT, 2), 180)
    else:
        PLACEMENT[ref] = (round(x, 2), round(y, 2), 0)


if __name__ == "__main__":
    for ref, (x, y, a) in PLACEMENT.items():
        print(f"{ref:4} {x:7.2f} {y:7.2f} {a:4}")
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
