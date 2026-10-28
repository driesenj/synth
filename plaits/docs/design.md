# Plaitsy (PCB) — design notes

A Mutable Instruments Plaits clone for Eurorack, 12HP, on two stacked PCBs
behind a PCB panel: a Daisy Seed on Rob Heel's `seed_power_opamps` breakout
does the DSP and the audio output, Thonk supplies the panel parts. Every
reference designator matches `hardware/tools/circuit.py`, which generates
the panel files and, in the next steps, the EasyEDA Pro project.

Status: panel layout drafted. Netlist, schematic, PCBs and firmware follow
once the panel is agreed.

---

## What Plaits needs

From the Plaits firmware and panel:

| Function | Plaits hardware | Count |
|---|---|---|
| Pots | FREQUENCY, HARMONICS, TIMBRE, MORPH; TIMBRE, FM and MORPH attenuverters | 7 |
| CV inputs | MODEL, TIMBRE, FM, MORPH, HARMONICS, TRIG, LEVEL, V/OCT (five of them with a cable-detect probe) | 8 |
| Audio outputs | OUT, AUX | 2 |
| Buttons | two model buttons (left: green bank, right: red bank; hold for the hidden settings) | 2 |
| LEDs | eight red/green bicolour, one per model row; green bank 1–8, red bank 9–16, yellow bank 17–24 in 1.2 | 8 (16 lines) |

The circuit is the one worked out for the stripboard version
(`plaitsy/docs/design.md`): inverting TL074 CV stages biased from 3V3A so
the full ±12 V stays inside the ADC range, V/OCT at 0.33 gain with Schottky
clamps, a 74HC4051 reading the seven pots, the normalization probe on A0
into the switch lugs of TIMBRE, FM, MORPH, TRIG and LEVEL, audio from the
Seed's codec through the breakout's output stage. What changes is the
build: real PCBs, and the LEDs driven through two 74HC595 as on Marblesy
instead of sixteen Seed GPIOs.

---

## Panel

12HP: 60.6 × 128.5 mm. The faceplate board is 59.4 × 108 mm, centred on the
panel (board x = panel x − 0.6; panel y from the top = 118.25 − board y).
Mounting slots 5.5 × 3.2 mm with their centres 3 mm from the top and bottom
edge, 7.5 and 53.22 mm from the left (Eurorack).

The arrangement is Plaits' own, measured off the panel photo. `PANEL_XY` in
`circuit.py` holds what you see (knob shafts, jack barrels, button caps, LED
bodies, in panel mm from the top-left corner, y down); `PLACEMENT` derives
the footprint origins from it (jack barrel 0.78 mm below the WQP518MA
origin, pot shaft 0.53 mm beyond the PTV09A origin), and `panel.py` turns
those back into the hole table, so the panel and the faceplate PCB cannot
drift apart.

```
  y from top
   17.8   [wrench]  o  o  [levels]····┐     the two model buttons, x 25.8 / 34.8, 9 mm apart
   25.2        icon ● icon                  8 LEDs at x 30.3, pitch 5.3 (25.2 … 62.3), icons at ±4.5
   30.2   FREQUENCY (12.4)      HARMONICS (48.2)
   55.5   TIMBRE (12.4)         MORPH (48.2)
   79.9   att (11.3)   FM att (30.3)   att (49.3)
   96.2   MODEL  TIMBRE  FM  MORPH  HARMO       jacks x = 7.3 + 11.5 k
  110.5   TRIG   LEVEL  V/OCT  [OUT  AUX]       same pitch; OUT and AUX on the copper band
```

| Hole | Ø mm | Part |
|---|---|---|
| Pots (×7) | 7.5 | Alpha 9 mm vertical B10k (Thonk), M7 bushing |
| Jacks (×10) | 6.5 | Thonkiconn PJ398SM |
| Buttons (×2) | 6.5 | Thonk low-profile LED button, 5.5 mm cap; its three feet drop into 1.2 mm board holes so it sits at Thonkiconn height |
| LEDs (×8) | 3.2 | 3 mm red/green bicolour (3-lead common cathode, or 2-lead bipolar between two 74HC595 lines) |

Knobs as drawn: Ø15 for FREQUENCY and HARMONICS, Ø12 for TIMBRE and MORPH,
Ø10 for the attenuverters (Plaits: about 17 / 13.5 / 6.5 mm). The scale
arcs are sized for those; change `ART["knob"]` and `ART["scale"]` in
`panel.py` if you fit other knobs.

Room on the board (checked against the part housings, the exporter checks
pads later): pot housings 9.5 × 9.5 are 9 mm apart at their closest
(attenuverter row); the jack bodies have 2.5 mm between them in a row and
3.9 mm between the rows; the two buttons' 7.5 mm bodies have 1.5 mm between
them; the top LED clears the buttons' pins by 2 mm; the outer jacks are
2.2 mm from the board edge, 3.3 mm of panel between their nuts and the
module next door (as on Plaits).

### Panel artwork

`panel.py` writes `hardware/panel/plaits-panel.svg`, the panel as a PCB in
the Marblesy style: black solder mask, white silkscreen, bare copper for
the OUT / AUX band. From the top: serif title and the dotted band; the
wrench beside the left button and the "levels" disc beside the right one
with its dotted line to HARMONICS (hold the right button and turn
HARMONICS for the octave range; hold the left button for the LPG settings,
whose icons sit beside the TIMBRE and MORPH labels); a dotted line from
each button down to its bank of icons; the sixteen model icons, green bank
as solid discs with the glyph knocked out, red bank as rings (one silk
colour, so the banks differ by fill rather than by colour; the preview
tints the red column); scale arcs with ticks on all seven knobs, labels
under the four main ones, − and + beside the attenuverters; dotted guides
TIMBRE → attenuverter → jack, FM → jack, MORPH → attenuverter → jack;
jack labels, TRIG ·· LEVEL; the copper band with OUT and AUX knocked out;
a thin line and the maker name at the bottom.

Groups: `#tint` and `#mockup` are preview only (bank colour, knobs, nuts,
caps, LEDs); `#silk`, `#copper` and `#holes` are the three layers the panel
PCB will need (top silkscreen, top copper + mask opening, drills).

The preview is rendered with headless Edge at 5 px/mm from a one-line HTML
wrapper (`<img src="plaits-panel.svg" style="width:303px;height:642.5px">`):

```
msedge.exe --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2
  --window-size=303,643 --user-data-dir=<scratch> --screenshot=plaits-panel-preview.png file:///<wrapper>.html
```

### Differences from Plaits

- Same controls in the same places; the knobs are 9 mm Alpha pots with
  whatever knobs you fit, not Mutable's.
- Black panel with white silk (the Marblesy look) instead of Plaits'
  aluminium. The model icons are redrawn, not Mutable's artwork.
- The buttons are Thonk LED buttons; Plaits' have no LED. Theirs stay dark
  unless the firmware finds a use for them (the yellow bank, say).
