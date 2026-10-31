"""Side FXy: a RYK Modular SIDE FX clone on a Daisy Seed. 14HP Eurorack.

Panel first (module-design skill): this file holds the panel parts and
their placement; the netlist follows once the panel is agreed.

Panel parts, as on SIDE FX (RYK product photos, October 2026):
  4 LED buttons     PITCH, DELAY, TEXTURE, REVERB: the four blocks' FX sends
  1 LED button      SHIFT (the red one beside the knob stack)
  4 encoders        soft knobs, each labelled by the display row beside it
  1 display         1.9" IPS, 170 x 320, ST7789V2 over SPI, portrait
  10 jacks          IN 1/2, OUT 1/2, CLOCK, MIDI (TRS, type A), CV 1-4
Behind the panel (main board, later): Seed on Rob Heel's breakout (audio
in/out through its op-amps), 4 CV input stages, clock input, MIDI opto,
microSD socket on SDMMC1 for presets.

PLACEMENT: board frame, front view, x right, y up, origin at the board's
bottom-left corner, mm; footprint origins (jacks: the WQP518MA origin,
0.78 mm above the barrel; buttons and encoders: the shaft; the display:
the centre of its active area).
"""

HP = 14
PANEL_W, PANEL_H = 70.8, 128.5          # Doepfer's 14HP width
BOARD_W, BOARD_H = 69.6, 108.0          # 0.6 mm in from each side, like Plaitsy and Marblesy
JACK_BARREL = -0.78                     # barrel centre below the WQP518MA origin

# ref, label, role
JACKS = [
    ("J1", "IN 1", "audio in"), ("J2", "OUT 1", "audio out"), ("J3", "CLOCK", "clock in"),
    ("J4", "CV 1", "cv in"), ("J5", "MIDI", "midi in"),
    ("J6", "IN 2", "audio in"), ("J7", "OUT 2", "audio out"), ("J8", "CV 2", "cv in"),
    ("J9", "CV 3", "cv in"), ("J10", "CV 4", "cv in"),
]
BUTTONS = [            # Thonk low-profile LED buttons
    ("SW1", "PITCH"), ("SW2", "DELAY"), ("SW3", "TEXTURE"), ("SW4", "REVERB"), ("SW5", "SHIFT"),
]
ENCODERS = [("ENC1", "K1"), ("ENC2", "K2"), ("ENC3", "K3"), ("ENC4", "K4")]   # EC11 with push
DISPLAY = ("DS1", "1.9in IPS 170x320")
DISPLAY_ACTIVE = (22.70, 42.72)         # active area, portrait, mm (Waveshare 1.9inch LCD Module)

# five jack columns 12.5 mm apart, centred; the rows at Marblesy's heights so the racks line up
JACK_X = [9.8 + 12.5 * k for k in range(5)]
JACK_ROW = (21.85, 7.25)
# the send buttons span the outer jack columns; SHIFT sits on the right column above the knob stack
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
