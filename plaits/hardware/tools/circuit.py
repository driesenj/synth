"""Plaitsy: a Mutable Instruments Plaits clone on a Daisy Seed, built the
Marblesy way: two stacked PCBs (faceplate board with the panel parts, main
board with the Seed on Rob Heel's seed_power_opamps breakout) behind a 12HP
panel, Thonk panel parts.

This file is the single source of truth for the panel-facing parts and
where they sit. panel.py derives the hole table, drill template and artwork
from PLACEMENT; pcb.py (next step) puts the same footprint origins on the
faceplate PCB. The netlist (main_board_parts / faceplate_parts, the
board-to-board headers) follows once the panel layout is agreed; the net
names in the tables below are the ones it will use, in the Marblesy
convention (*_F = faceplate side of a net that crosses the headers).
"""

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
# ref, label, wiper net, 74HC4051 input pin, mux channel (channel 7, pin 4, is grounded)
POTS = [
    ("RV1", "FREQUENCY", "POT_FREQ_F", "13", 0), ("RV2", "HARMONICS", "POT_HARMO_F", "14", 1),
    ("RV3", "TIMBRE", "POT_TIMBRE_F", "15", 2), ("RV4", "MORPH", "POT_MORPH_F", "12", 3),
    ("RV5", "TIMBRE att.", "ATT_TIMBRE_F", "1", 4), ("RV6", "FM att.", "ATT_FM_F", "5", 5),
    ("RV7", "MORPH att.", "ATT_MORPH_F", "2", 6),
]
# ref, label, firmware switch. Thonk low-profile LED buttons, the Marblesy
# part (Thonkiconn height, 5.5 mm cap). Plaits' own buttons have no LED;
# these stay dark unless the firmware finds a use for them.
BUTTONS = [("SW1", "model, green bank", "MODEL_A"), ("SW2", "model, red bank", "MODEL_B")]
# ref, label, kind: eight 3 mm red/green bicolour LEDs in a column; each row
# shows one model of the green, red and (Plaits 1.2) yellow bank.
LEDS = [(f"D{k + 1}", f"model {k + 1} / {k + 9} / {k + 17}", "RG") for k in range(8)]

# ------------------------------------------------------ faceplate placement
# Panel: Eurorack 3U, 12HP. Faceplate board 59.4 x 108 mm, centred on it.
PANEL_W, PANEL_H = 60.6, 128.5
BOARD_W, BOARD_H = 59.4, 108.0
# Footprint origins are not the mechanical centres: the Thonkiconn barrel is
# 0.78 mm below the WQP518MA origin (sleeve pad up), the Alpha pot's shaft
# 0.53 mm beyond the PTV09A origin, away from the pins (+x at angle 90).
JACK_BARREL, POT_SHAFT = -0.78, 0.53

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
        PLACEMENT[ref] = (round(x - POT_SHAFT, 2), round(y, 2), 90)
    else:
        PLACEMENT[ref] = (round(x, 2), round(y, 2), 0)


if __name__ == "__main__":
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
    for ref, (x, y, rot) in PLACEMENT.items():
        print(f"  {ref:4} origin ({x:6.2f}, {y:6.2f}) rot {rot:3}   panel ({PANEL_XY[ref][0]:5.2f}, {PANEL_XY[ref][1]:6.2f})")
