"""Offset: four offset attenuverters in 12HP Eurorack, all analog.

Panel first (module-design skill): this file holds the panel parts and their
placement; the netlist follows once the panel and the open choices in
docs/design.md are agreed.

Per channel k (1-4): OUT k = ATTEN k x IN k + OFFSET k (+ OUT k-1 when that
jack is unpatched).
  IN k      CV / audio in; unpatched it takes IN k-1, and IN 1 takes +1 V,
            so with nothing patched ATTEN is a fine +-1 V offset
  ATTEN k   B10k, -1 (CCW) .. 0 (noon) .. +1 (CW)
  OFFSET k  B10k, -5 V .. +5 V from LM4040 references
  OUT k     1k series; unpatched it adds into channel k+1 (OUT 4 = the sum)
  LED k     2-lead bicolour: green positive, red negative

Behind the panel (later), one TL074 per channel:
  A  inverter               N_k = -IN_k         (100k in: fan-out friendly)
  B  inverter               P_k = +IN_k         (both pot ends driven low-Z)
     ATTEN between P_k (CCW) and N_k (CW), wiper -> 100k -> SUM_k
     OFFSET between +5 V (CCW) and -5 V (CW), wiper -> 100k -> SUM_k
  C  inverting summer       OA_k = -(SUM inputs), 100k || 22p -> 1k -> OUT k
  D  cascade inverter       OUT k's switch lug -> 100k -> -OUT_k -> 100k -> SUM_k+1
U4's D section is free (OUT 4 has nothing after it) and buffers the +1 V
normal from a divider on the +5 V reference.

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  LED     3 mm, the lens centre between its two pads
"""

HP = 12
PANEL_W, PANEL_H = 60.6, 128.5          # 12 x 5.08 less 0.36, as Plaitsy
BOARD_W, BOARD_H = 59.4, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins
CHANNELS = 4

# ref, label, role
JACKS, POTS, LEDS = [], [], []
for k in range(1, CHANNELS + 1):
    JACKS.append((f"J{k}", f"IN {k}", "input, normalled from IN k-1 (IN 1 from +1 V)"))
    POTS += [(f"RV{2 * k - 1}", f"ATTEN {k}", "B10k, -1 .. +1"), (f"RV{2 * k}", f"OFFSET {k}", "B10k, -5 V .. +5 V")]
    LEDS.append((f"D{k}", f"OUT {k}", "3 mm bicolour red/green, 2 leads"))
for k in range(1, CHANNELS + 1):
    JACKS.append((f"J{CHANNELS + k}", f"OUT {k}", "output; unpatched it adds into the next channel"))

# ---------------------------------------------------------------- panel grid (panel frame, y down)
# Channels are columns like the mixer's strips, 13.3 mm apart (the mixer: 13.5); the left margin
# holds the row words. Knobs at the top, jacks at the bottom so cables hang away from the hands.
CH_X = [11.5 + 13.3 * i for i in range(CHANNELS)]
ROW = {"atten": 27.0, "offset": 48.5, "in": 76.5, "led": 91.0, "out": 102.5}


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for k, x in enumerate(CH_X, start=1):
    for ref, row in ((f"RV{2 * k - 1}", "atten"), (f"RV{2 * k}", "offset")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - POT_SHAFT, 2), 0)          # pins down
    for ref, row in ((f"J{k}", "in"), (f"J{CHANNELS + k}", "out")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)        # sleeve up
    PLACEMENT[f"D{k}"] = (*board_xy(x, ROW["led"]), 0)


if __name__ == "__main__":
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
