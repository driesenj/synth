"""Envy: four Moritz Klein envelopes (MKI x ES.EDU EG) in 16HP Eurorack, all analog.

Panel first (module-design skill): this file holds the panel parts and their
placement; the netlist follows once the panel and the open choices in
docs/design.md are agreed.

Per channel k (1-4), the kit's pseudo-ADSR (EG_MANUAL_v3.pdf):
  GATE k     comparator against VREF; unpatched it takes GATE k-1 (GATE 1: 0 V)
  ATTACK k   A1M, charge path: buffer -> 100R -> BAT85 -> ATTACK -> C_T
  DEC/REL k  A1M, discharge path: C_T -> DEC/REL -> BAT85 -> buffer (decay and
             release share it, as on the kit)
  SUSTAIN k  A100k divider on the gated comparator's output, 100k into the buffer
  MODE k     SPDT toggle: up LOOP (a Schmitt trigger on ENV re-fires the buffer
             between about 0.5 V and 7.5 V, gate ignored), down SINGLE
  OUT k      ENV, 0 .. about 9.7 V, 1k series
  INV k      AXIS x 2 - ENV = about 9.7 V .. 0 V, 1k series
  LED k      3 mm red, BC548 emitter follower on ENV, 1k5

Behind the panel (later), six op-amp sections per channel, 6 x TL074:
  gate comparator   GIN_k vs VREF -> 1N4148 -> G_k (0 / ~10 V), 10k to GND
  burst comparator  HP_k vs VREF -> 1N4148 -> N_k; HP_k = G_k through 1u, 10k to GND,
                    1N4148 clamp: a ~14 ms full-level burst on every rising gate
  input buffer      MODE common (N_k or L_k) -> 100R -> the two steering diodes
  output buffer     C_T (1u film) -> ENV_k -> 1k -> OUT k
  inverter          ENV_k -> 100k -> [-], AXIS on [+], 100k feedback -> 1k -> INV k
  loop Schmitt      ENV_k on [-], 100k / 100k / 100k divider with feedback on [+],
                    -> 1N4148 -> L_k, 100k to GND
Shared: VREF = 100k / 27k from +12 V (2.55 V), AXIS = 100k / 68k (4.86 V), each
with 100n; the kit uses 3.8 V and a 6 V axis (see docs/design.md, changes).

Coordinates: designed in the panel frame (from the top-left, y down, mm),
stored in PLACEMENT in the board frame the generators use (front view, x
right, y up, origin at the board's bottom-left corner): footprint origins.
  jack    WQP518MA origin, the barrel 0.78 mm below it
  pot     PTV09A-frame origin of the Alpha footprint; the shaft is 4.0 mm
          from it, away from the pins (pins point down here)
  toggle  bushing centre (the middle pin row)
  LED     3 mm, the lens centre between its two pads
"""

HP = 16
PANEL_W, PANEL_H = 80.9, 128.5          # 16HP, as Atlasy
BOARD_W, BOARD_H = 79.7, 108.0          # 0.6 mm in from each side, like the other modules
BOARD_X0, BOARD_Y0 = (PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin
POT_SHAFT = 4.0                         # Alpha shaft from the PTV09A-frame origin, away from the pins
CHANNELS = 4

# ref, label, role
JACKS, POTS, TOGGLES, LEDS = [], [], [], []
for k in range(1, CHANNELS + 1):
    JACKS.append((f"J{k}", f"GATE {k}", "gate in, normalled from GATE k-1 (GATE 1 from 0 V)"))
    POTS += [(f"RV{3 * k - 2}", f"ATTACK {k}", "A1M, charge resistance"),
             (f"RV{3 * k - 1}", f"DEC/REL {k}", "A1M, discharge resistance: decay and release"),
             (f"RV{3 * k}", f"SUSTAIN {k}", "A100k, sustain level")]
    TOGGLES.append((f"SW{k}", f"MODE {k}", "SPDT ON-ON sub-mini toggle: up LOOP, down SINGLE"))
    LEDS.append((f"D{k}", f"ENV {k}", "3 mm red, brightness follows ENV"))
for k in range(1, CHANNELS + 1):
    JACKS.append((f"J{CHANNELS + k}", f"OUT {k}", "envelope out, 0 .. ~9.7 V"))
for k in range(1, CHANNELS + 1):
    JACKS.append((f"J{2 * CHANNELS + k}", f"INV {k}", "inverted envelope, ~9.7 .. 0 V"))

# ---------------------------------------------------------------- panel grid (panel frame, y down)
# Channels are columns, as on Offset, 18 mm apart; the left margin holds the row words. Knobs at the
# top, jacks at the bottom so cables hang away from the hands; the outputs on the gold band.
CH_X = [14.0 + 18.0 * i for i in range(CHANNELS)]
ROW = {"attack": 25.5, "decay": 41.0, "sustain": 56.5, "mode": 70.0,
       "gate": 81.5, "led": 90.5, "out": 100.5, "inv": 111.5}
TOGGLE_DX = -2.5                        # the toggle left of the column line, its LOOP / SINGLE words right


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (front view, y up)."""
    return round(px - BOARD_X0, 2), round(PANEL_H - BOARD_Y0 - py, 2)


def panel_xy(bx, by):
    """Board mm (y up) -> panel mm from the top-left corner (y down)."""
    return bx + BOARD_X0, PANEL_H - BOARD_Y0 - by


PLACEMENT = {}
for k, x in enumerate(CH_X, start=1):
    for ref, row in ((f"RV{3 * k - 2}", "attack"), (f"RV{3 * k - 1}", "decay"), (f"RV{3 * k}", "sustain")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - POT_SHAFT, 2), 0)          # pins down
    for ref, row in ((f"J{k}", "gate"), (f"J{CHANNELS + k}", "out"), (f"J{2 * CHANNELS + k}", "inv")):
        bx, by = board_xy(x, ROW[row])
        PLACEMENT[ref] = (bx, round(by - JACK_BARREL, 2), 0)        # sleeve up
    PLACEMENT[f"SW{k}"] = (*board_xy(x + TOGGLE_DX, ROW["mode"]), 0)
    PLACEMENT[f"D{k}"] = (*board_xy(x, ROW["led"]), 0)


if __name__ == "__main__":
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
