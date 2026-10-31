"""Atlasy: a Vostok Instruments Atlas clone. 16HP Eurorack, all analog.

Panel first (module-design skill): this file holds the panel parts and their
placement; the netlist follows once the panel and the open choices in
docs/design.md are agreed.

Panel parts, as on Atlas (Vostok's manual and product photo, October 2026):
  4 channel rows   IN, FREQ, FM2/RES and OUT jacks; FREQ and RES knobs; a
                   LP / HP / BP mode switch; an FM2 / RES switch for the third
                   jack; a lit channel numeral (signal LED)
  scanner          SCAN CV jack, scanner OUT jack, SCAN fader (1 -> 4)
IN and FREQ are normalled down the rows (1 -> 2 -> 3 -> 4).
Behind the panel (later): per channel one SSI2164 as the four poles, the
pole-mix mode outputs and bandpass-fed resonance of Sound Semiconductor's
AN701, and a fifth SSI2164 for the four resonance VCAs; the scanner is a
transistor current line feeding two AS3360 dual VCAs.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  toggle  bushing centre (the middle pin row)
  fader   centre of the slide travel
  LED     3 mm LED behind the centre of the channel numeral
"""

HP = 16
PANEL_W, PANEL_H = 80.9, 128.5          # Doepfer-style 16HP: 16 x 5.08 less 0.4
BOARD_W, BOARD_H = 79.7, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins
CHANNELS = 4

# ref, label, role
JACKS, POTS, TOGGLES, LEDS = [], [], [], []
for k in range(1, CHANNELS + 1):
    n = 4 * (k - 1)
    JACKS += [(f"J{n + 1}", f"IN {k}", "audio in, normalled from the row above"),
              (f"J{n + 2}", f"FREQ {k}", "cutoff CV, normalled from the row above"),
              (f"J{n + 3}", f"FM2/RES {k}", "second CV: cutoff or resonance, by the switch"),
              (f"J{n + 4}", f"OUT {k}", "filter out, the selected mode")]
    POTS += [(f"RV{2 * k - 1}", f"FREQ {k}", "B100k, cutoff"), (f"RV{2 * k}", f"RES {k}", "B100k, resonance")]
    TOGGLES += [(f"SW{k}", f"MODE {k}", "DPDT ON-ON-ON sub-mini toggle: LP / HP / BP"),
                (f"SW{k + 4}", f"FM2/RES {k}", "SPDT ON-ON sub-mini toggle: FM2 / RES")]
    LEDS += [(f"D{k}", f"CH {k}", "3 mm LED behind the numeral's dots: channel output level")]
JACKS += [("J17", "SCAN", "scan CV, sums with the fader"), ("J18", "SCAN OUT", "scanner out")]
POTS += [("RV9", "SCAN", "B10k slide pot, 20 mm travel")]

# ---------------------------------------------------------------- panel grid (panel frame, y down)
JACK_X = [7.0, 17.0, 27.0, 37.0]        # IN, FREQ, FM2/RES, OUT: 10 mm apart (Atlas: about 9.3)
KNOB_X = (52.5, 72.5)                   # FREQ, RES
ROW_Y = [21.0 + 22.0 * r for r in range(CHANNELS)]   # jacks and knobs of a channel on one line
MODE_XY = (23.0, 10.0)                  # mode toggle: under the FREQ / FM2-RES jacks, row + 10
FMRES_XY = (62.5, 10.0)                 # FM2/RES toggle: between the knobs, row + 10
NUMERAL_XY = (44.6, 7.0)                # numeral centre: between the jacks and FREQ, row + 7
SCAN_Y = 111.8                          # scanner row
SCAN_JACK_X = (27.0, 37.0)              # SCAN CV under FM2/RES, scanner OUT under the OUTs
FADER_X, FADER_TRAVEL = 61.5, 20.0      # slot centre and travel; 1 at the left, 4 at the right


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for r, y in enumerate(ROW_Y):
    for c, x in enumerate(JACK_X):
        bx, by = board_xy(x, y)
        PLACEMENT[f"J{4 * r + c + 1}"] = (bx, round(by - JACK_BARREL, 2), 0)
    for c, x in enumerate(KNOB_X):
        bx, by = board_xy(x, y)
        PLACEMENT[f"RV{2 * r + c + 1}"] = (bx, round(by - POT_SHAFT, 2), 0)   # pins down
    PLACEMENT[f"SW{r + 1}"] = (*board_xy(MODE_XY[0], y + MODE_XY[1]), 0)
    PLACEMENT[f"SW{r + 5}"] = (*board_xy(FMRES_XY[0], y + FMRES_XY[1]), 0)
    PLACEMENT[f"D{r + 1}"] = (*board_xy(NUMERAL_XY[0], y + NUMERAL_XY[1]), 0)
for ref, x in zip(("J17", "J18"), SCAN_JACK_X):
    bx, by = board_xy(x, SCAN_Y)
    PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)
PLACEMENT["RV9"] = (*board_xy(FADER_X, SCAN_Y), 0)


if __name__ == "__main__":
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
