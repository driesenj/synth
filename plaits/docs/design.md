# Plaitsy (PCB) — design notes

A Mutable Instruments Plaits clone for Eurorack, 12HP, on two stacked PCBs
behind a PCB panel: a Daisy Seed on Rob Heel's `seed_power_opamps` breakout
does the DSP and the audio output, Thonk supplies the panel parts. Every
reference designator matches `hardware/tools/circuit.py`, which generates
the EasyEDA Pro project (`hardware/easyeda/Plaits.epro2`) and the panel
files.

Status: schematic done and checked, footprints assigned, both PCBs placed
and net-assigned (see [PCB placement](#pcb-placement)), the panel as the
third board. PCB routing and firmware not started.

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

---

## Architecture

```
 panel ─┬─ faceplate board (FB)   10 Thonkiconn jacks, 7 Alpha pots, 2 LED buttons, 8 bicolour LEDs,
        │   59.4 x 108 mm          74HC4051 pot mux, 2x 74HC595 (LEDs), 16 LED resistors, 5 probe resistors
        │      26 pins in 3 headers (male on the FB, female on the MB)
        └─ main board (MB)        Daisy Seed on the seed_power_opamps breakout (power, audio out),
            59.4 x 108 mm          2 TL074 = 8 CV input stages, two bias dividers, V/OCT clamps
```

Both boards are the same size and stack in the same orientation (jacks and
pots on the FB's bottom side towards the panel, headers on the FB's top side
mating with sockets on the MB's bottom side, Seed and breakout on the MB's
top side), the Marblesy arrangement; every header has the same x/y on both
boards.

### Daisy Seed pin map

| Seed pin | libDaisy | Net | Use |
|---|---|---|---|
| 1, 2 | D0, D1 | BTN_A, BTN_B | model buttons, internal pull-ups, active low |
| 3, 4 | D2, D3 | BTN_LED_A_IO, BTN_LED_B_IO | the LEDs inside the buttons, through 470 Ω |
| 9 | D8 (SPI1 SCK) | SPI_SCK | 74HC595 shift clock |
| 11 | D10 (SPI1 MOSI) | SPI_MOSI | 74HC595 data |
| 14 | D13 | LED_LATCH | 74HC595 RCLK |
| 15 | D14 | PROBE | normalization probe output |
| 20, 40 | AGND, DGND | GND | both on the main board's GND |
| 21 | 3V3A | 3V3A | pots, mux, bias |
| 22..28 | A0..A6 | ADC_MODEL, ADC_TIMBRE, ADC_FM, ADC_MORPH, ADC_HARMO, ADC_TRIG, ADC_LEVEL | CV inputs |
| 31 | A9 | ADC_VOCT | V/OCT |
| 32 | A10 | MUX_OUT | pot mux |
| 33, 34, 35 | D26, D27, D28 | MUX_S0..S2 | pot mux address |
| 38 | 3V3D | 3V3D | shift registers |
| J4-1, J4-3 | AOUT1, AOUT2 (buffered) | OUT, AUX | the breakout's output stage, to the jacks |
| 5..8, 10, 12, 13, 16..19, 29, 30, 36, 37, 39 | D4..D7, D9, D11, D12, AIN, AOUT, A7, A8, D29, D30, VIN | — | free |

The breakout's J1 (GND, −12 V ×3) and J3 (GND, +12 V ×3) feed the op-amps;
J5 (audio in) is unused. The breakout ties Seed pins 20 and 40 to one GND
and feeds VIN from its own DC/DC converter.

---

## Main board circuits

### CV inputs (8×)

Inverting TL074 stage biased from 3V3A, so no negative reference is needed
and the full ±12 V stays inside the ADC range without clamps:

```
jack tip ── 100k ──┬── (−) TL074 ──┬── 1k ── Seed ADC
                   ├── Rf ─────────┤
                   └── Cf ─────────┘
BIAS ─────────────── (+)
```

| Input | Section | Rin | Rf | Cf | Rs | Bias | ADC |
|---|---|---|---|---|---|---|---|
| MODEL | U3A | R21 | R22 13k | C21 1n | R23 | A | A0 |
| TIMBRE | U3B | R24 | R25 13k | C22 1n | R26 | A | A1 |
| FM | U3C | R27 | R28 13k | C23 1n | R29 | A | A2 |
| MORPH | U3D | R30 | R31 13k | C24 1n | R32 | A | A3 |
| HARMONICS | U4A | R33 | R34 13k | C25 1n | R35 | A | A4 |
| TRIG | U4B | R36 | R37 13k | C26 100p | R38 | A | A5 |
| LEVEL | U4C | R39 | R40 13k | C27 1n | R41 | A | A6 |
| V/OCT | U4D | R42 | R43 33k | C28 1n | R44 | V | A9 |

- **Bias A** = 3V3A × 12k / (15k + 12k) = 1.467 V (R45, R46, C29 1 µ).
  **Bias V** = 3V3A × 15k / (13k + 15k) = 1.768 V (R47, R48, C30 1 µ).
- **Wide channels** (gain −0.13): V_adc = 1.658 V − 0.13 · V_in; ±12 V
  lands on 3.22 … 0.10 V.
- **V/OCT** (gain −0.33): V_adc = 2.351 V − 0.33 · V_in; usable −2.9 …
  +7.1 V, which is 0.2 Plaits units per volt, Plaits' own pitch scaling.
  D21 and D22 (BAT85) clamp the ADC pin to 3V3A and GND beyond that.
- Corner frequency 12 kHz (13k ‖ 1n); TRIG uses 100p so edges stay sharp.
- C31–C34 (100 n) decouple ±12 V at each TL074.

**Firmware mapping:** V_in = (V0 − V_adc) / g with V0 / g = 1.658 / 0.13
for the wide channels and 2.351 / 0.33 for V/OCT; that voltage is then
turned into the number Plaits' own ADC would have read, and Plaits' code
and calibration apply unchanged.

### Button LEDs

R60, R61 (470 Ω) from D2 / D3 to the headers; the LED inside each Thonk
button returns to GND_D_F. Plaits has no button LEDs, so the firmware is
free to use them (the yellow bank, button feedback) or leave them dark.

---

## Faceplate circuits

- **Jacks J1–J10** (Thonkiconn, pads 1 = sleeve, 2 = switch, 3 = tip).
  Sleeves to GND_F. MODEL, HARMONICS and V/OCT: switch lug to GND_F (reads
  0 V unpatched). TIMBRE, FM, MORPH, TRIG, LEVEL: switch lug through 10k
  (R9–R13) to PROBE_F, Plaits' cable detection. OUT, AUX: lug open.
- **Pots RV1–RV7** (Alpha 9 mm B10k): CCW end to GND_F, CW end to 3V3A_F,
  wipers into U1 (74HC4051), channel order below. C8 100 n at U1 pin 16.
  Channel 7 is grounded. The attenuverters read 0…1 and the firmware maps
  that to −1…+1, as Plaits does.
- **LEDs D1–D8**: 3 mm red/green bicolour, common cathode (middle lead) to
  GND_D_F. U9 and U10 (74HC595, chained: U9 QH' → U10 SER; SER from
  MOSI_F, SRCLK from SCK_F, RCLK from LED_LATCH_F, /OE low, /SRCLR high)
  drive the 16 anodes through 470 Ω each (R80–R95): about 3 mA per colour,
  yellow is both on, brightness by PWM at the LED update rate. C9, C10
  100 n.
- **Buttons SW1, SW2**: Thonk low-profile LED buttons; contacts 1+2 to
  GND_D_F, 3+4 to BTN_A_F / BTN_B_F (Seed internal pull-ups); LED anode
  (pin 5) from the main board's 470 Ω, cathode (pin 6) to GND_D_F.

| Mux channel (Y) | 4051 pin | Pot |
|---|---|---|
| 0 | 13 | RV1 FREQUENCY |
| 1 | 14 | RV2 HARMONICS |
| 2 | 15 | RV3 TIMBRE |
| 3 | 12 | RV4 MORPH |
| 4 | 1 | RV5 TIMBRE attenuverter |
| 5 | 5 | RV6 FM attenuverter |
| 6 | 2 | RV7 MORPH attenuverter |
| 7 | 4 | GND_F |

| 595 output | LED line | | 595 output | LED line |
|---|---|---|---|---|
| U9 QA..QH | D1 R, D1 G, D2 R, D2 G, D3 R, D3 G, D4 R, D4 G | | U10 QA..QH | D5 R, D5 G, D6 R, D6 G, D7 R, D7 G, D8 R, D8 G |

libDaisy: `AdcChannelConfig::InitMux(A10, 8, D26, D27, D28)` for the pots;
SPI1 at about 1 MHz for the shift registers, 16 bits per update, latch on
D13.

---

## Board-to-board headers

| Header | Pins | Main board nets (faceplate: same name + `_F`) | Where (front view) |
|---|---|---|---|
| H1 | 8 | CV_MODEL, CV_TIMBRE, CV_FM, CV_MORPH, CV_HARMO, CV_TRIG, CV_LEVEL, CV_VOCT | horizontal, between the top jack row and the attenuverters |
| H2 | 9 | OUT, AUX, PROBE, GND (GND_F), 3V3A, MUX_OUT, MUX_S0, MUX_S1, MUX_S2 | vertical in the right margin, beside the attenuverter |
| H3 | 9 | SPI_SCK (SCK_F), SPI_MOSI (MOSI_F), LED_LATCH, 3V3D, GND (GND_D_F), BTN_A, BTN_B, BTN_LED_A, BTN_LED_B | vertical in the right margin, beside MORPH |

Male pins on the faceplate (HF1–HF3), female sockets on the main board, each
pair at the same x/y on both boards. GND_F (jacks, pots, mux) and GND_D_F
(LEDs, buttons, shift registers) are separate on the faceplate and meet on
the main board's GND.

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
| LEDs (×8) | 3.2 | 3 mm red/green bicolour, 3-lead common cathode |

Knobs as drawn: Ø15 for FREQUENCY and HARMONICS, Ø12 for TIMBRE and MORPH,
Ø10 for the attenuverters (Plaits: about 17 / 13.5 / 6.5 mm). The scale
arcs are sized for those; change `ART["knob"]` and `ART["scale"]` in
`panel.py` if you fit other knobs.

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
PCB needs. The glyphs are lists of path / circle / text primitives
(`GLYPHS`), shared with the panel PCB.

The preview is rendered with headless Edge at 5 px/mm from a one-line HTML
wrapper (`<img src="plaits-panel.svg" style="width:303px;height:642.5px">`):

```
msedge.exe --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2
  --window-size=303,643 --user-data-dir=<scratch> --screenshot=plaits-panel-preview.png file:///<wrapper>.html
```

`panel_pcb.py` builds the same drawing as the project's third board,
`Plaitsy Panel PCB`: 60.6 × 128.5 outline, every hole and the four
5.5 × 3.2 slots as non-plated drills, the silkscreen (titles, labels, arcs,
ticks, − / + marks, dotted guides as 0.12 mm dashes, the wrench outline,
the levels disc, the LPG icons, the sixteen model icons as rings with
their glyph flattened to short lines — a thick ring for the green bank, a
thin one for the red bank, since silk cannot knock a glyph out of a solid
disc) and the OUT / AUX band as a copper fill on the top layer under a
solder-mask opening of the same shape, so it comes out as bare ENIG gold;
OUT and AUX are silkscreen on top of it. Text uses the default stroke font
and estimated centring, so expect to nudge a few labels. Order it as a
1.6 mm board, black mask, white silk, ENIG. Two things the fab may ask
about: silkscreen over bare copper (the band labels; if they drop it, put
the labels on the solder-mask layer instead and they come out gold on
black) and non-plated holes through the copper band.

### Differences from Plaits

- Same controls in the same places; the knobs are 9 mm Alpha pots with
  whatever knobs you fit, not Mutable's.
- Black panel with white silk (the Marblesy look) instead of Plaits'
  aluminium. The model icons are redrawn, not Mutable's artwork.
- The buttons are Thonk LED buttons; Plaits' have no LED.
- CV inputs accept ±12 V without clipping in hardware; the firmware clips
  to Plaits' ranges, so the response is the same.
- Audio comes from the Seed's codec through the breakout's output stage;
  the output level is the breakout's.

---

## PCB placement

`hardware/tools/pcb.py` places every part of both boards, assigns each pad
its net and writes the two PCB documents into `Plaits.epro2`; the exporter
checks the result (pads 0.25 mm apart or more, 0.5 mm from the edge, no
bodies overlapping on one side, nothing under a standoff, header pins
coinciding on both boards, panel parts exactly at `PLACEMENT`, no rear-side
pad under a panel part's housing). Nothing is routed. Previews:
`hardware/easyeda/plaits-easyeda-pcb-*.png`.

**Frame.** Each PCB is drawn as EasyEDA shows it, looking at the top layer,
which on both boards is the rear of the stack: x to the right, y up, origin
at the bottom-left corner. The front view of the faceplate placement is its
mirror image, `x_front = 59.4 − x`. Both boards use this one frame, so the
three header pairs have identical coordinates on both PCBs. EasyEDA mirrors
a bottom-layer footprint about its own X axis (y → −y) before rotating it;
`pcb.py` uses that rule and picks the panel parts' angles by it (jack
sleeve pad towards the top of the board, pot pins in a column towards the
left as seen from the front, LED button LED pins along x with pin 5 on the
right, LED leads along x with the red anode on the left).

**Faceplate board.** Bottom layer: the 10 jacks, 7 pots, 2 LED buttons and
the 8 LEDs. Top (rear) layer, inside the header gap (front-view x, y):
H1 horizontal at (29.0, 31.2) between the top jack row and the
attenuverters; H2 (54.3, 42) and H3 (54.3, 65) vertical in the right
margin, outside the pots' lug pads; U1 at (14.5, 49.5) in the pocket left
of the centre hole with C8 at (3.5, 57); U9 at (15.4, 75) and U10 at
(43, 75) between the big knobs and TIMBRE / MORPH with C9 at (3.5, 70) and
C10 under U10 at (43, 69); the LED resistors as vertical parts in rows at
y 88 and y 62 either side of the LED column (R80–R87 left for U9, R88–R95
right for U10); the probe resistors R10–R13 vertical in the right pocket
(x 36–43.5, y 48.5) and R9 horizontal in the jack strip at (7.55, 31.2).
Rear pads never fall under a pot or jack housing, since those are soldered
on the panel side.

**Main board.** Bottom layer: the three female sockets at the same spots
(H2 / H3 land in the channel between the breakout's pad rows). Top (rear)
layer, PCB frame: the Seed breakout vertical along the left edge, centred
at (10, 64), power end (J1 / J3) down and USB end up; U3 (30, 86) and U4
(30, 62) vertical, each with its two 100 n beside it in the channel at
x 22.5; the channel resistors horizontal in one column at x 43.5, 2.5 mm
rows, U3's twelve from y 97.5 down, U4's from 67.5 down, then the bias
resistors and R60 / R61; the feedback capacitors vertical at x 52.5 in
7.5 mm steps (C28 at y 30), C29 / C30 below them; the V/OCT clamps D21 /
D22 vertical in the right margin at x 57.

**Mounting.** Four 3.2 mm holes, front-view (3.5, 104.5), (55.9, 104.5),
(3.5, 40) and (29.9, 48.5), identical on both boards: the top corners above
the big knobs, the left pocket beside the TIMBRE attenuverter, the centre
of the strip between the attenuverters and the lowest LED. M3 standoffs
between the boards, as long as the mated headers make the gap (a standard
8.5 mm socket plus the male header's 2.5 mm spacer, about 11 mm; measure
the mated pair). The breakout and Seed hang on the main board's rear. The
jack strip has no hole; the jacks' nuts hold the faceplate to the panel.

**What EasyEDA's DRC will still say.** Floating pins on the Seed's unused
pins (D4–D7, D9, D11, D12, AIN, AOUT, A7, A8, D29, D30, VIN, J5-1 / J5-3),
on the LED buttons' feet (pins 7–9) and on the jacks' open switch lugs
(J9, J10): all intentional.

---

## Routing notes

Plan: set the rules, route the few nets that matter by hand and lock them,
let the autorouter do the rest with the grounds excluded, clean up, pour.

**Rules first** (Design > Design Rules; the project carries the rules copied
from one of the MorrisSynth boards, whose clearance is a tight 0.1 mm).
For a hand-soldered 2-layer board: clearance 0.25 mm, default track 0.3 mm,
a POWER net class at 0.6 mm (+12V, −12V, 3V3A, 3V3D, 3V3A_F, 3V3D_F), vias
0.8 mm with a 0.4 mm hole, copper 0.5 mm from the edge.

**Keepouts before routing.** Faceplate, panel-side (bottom) layer: a 3 mm
circle at each jack barrel, 0.78 mm below the jack origin, where the metal
barrel sits (GND_F copper may stay). Both boards: 3.5 mm around the four
mounting holes on the standoff side (faceplate top, main board bottom).

**Autorouter** (Route > Auto Route). Layers top and bottom; preferred
direction vertical on top and horizontal on bottom; 45° corners; via
quantity "less"; "completion first" for the first pass, then re-run the
ugly nets selected with "quality first". Skip nets: GND, GND_F, GND_D_F
and the POWER class, which are poured or hand-routed. Hand-route and lock
before the run: the power buses, the SPI bundle, the summing nodes and the
bias trees. Afterwards: remove loops, DRC, then pours.

**Ground planes.**
- Main board: one GND net. Pour it on both layers; the bottom (socket) side
  is nearly empty and becomes the plane. It must reach the Seed's pins 20
  and 40 and the breakout's J1-1 / J3-1 / J4-2 / J4-4.
- Faceplate: GND_F (jacks, pots, mux) poured on the panel-side (bottom)
  layer under everything, which also shields the CV lines. GND_D_F (shift
  registers, LEDs, buttons) as a pour on the rear (top) layer confined to
  the area around U9, U10 and the LED column, or plain tracks. The two
  never touch on this board; they meet on the main board's GND through
  H2 pin 4 (GND_F) and H3 pin 5 (GND_D_F).

**Main board, by hand and with care.**
1. Summing nodes IN_* (op-amp pin −, R_in, R_fb, C_fb): one layer, short,
   over the pour, away from the SPI lines. The ADC_* lines from the 1 kΩ
   resistors to the Seed's right pin row (x 17.6) likewise, as a group;
   the Seed's ADC pins face the op-amps, so these are the short runs.
2. BIAS_A from C29 as a tree to the seven op-amp + inputs, BIAS_V from
   C30 to U4 pin 12; ADC_VOCT past the clamps D21 / D22 on its way to
   pin 31.
3. SPI (SCK, MOSI, LED_LATCH) and the button lines from the Seed's left
   pin row (x 2.4) to H3 right beside it: short, on the bottom layer in
   the channel.
4. OUT / AUX from J4 (top of the breakout, x 17.6) down the channel to H2
   on the bottom layer, with pour either side; PROBE from pin 15 to H2.
5. Power: +12 V and −12 V from J3 / J1 (bottom of the breakout) up the
   decoupling column at x 22.5 to U3 and U4 as 0.6 mm buses; 3V3A from
   pin 21 to the bias dividers and H2; 3V3D from pin 38 to H3.

**Faceplate.**
1. Pot wipers to U1 and the mux lines to H2 on the panel side under GND_F.
2. The eight CV_* lines from the jacks straight up to H1 (a few mm each).
   The probe: PROBE_F from H2 across the jack strip to R9–R13 and down
   to the switch lugs.
3. OUT_F / AUX_F from H2 down the right margin to J9 / J10.
4. SPI_F from H3 to U9 then the chain to U10, short on the rear; the
   sixteen LED lines from the 595 outputs to their resistors and on to the
   LED column, rear layer, away from the wipers; LED cathodes and the
   buttons to GND_D_F.
5. 3V3A_F from H2 to the pots' CW ends and U1 (0.6 mm); 3V3D_F from H3 to
   U9, U10 and C9 / C10.

---

## BOM

| Qty | Part | Value / note | Refs |
|---|---|---|---|
| 1 | Daisy Seed | | U2 |
| 1 | seed_power_opamps breakout (Rob Heel), built | power and audio-out stage | U2 |
| 2 | TL074 + DIP-14 socket | | U3, U4 |
| 1 | 74HC4051 + DIP-16 socket | CD4051B also works | U1 |
| 2 | 74HC595 + DIP-16 socket | | U9, U10 |
| 8 | 3 mm bicolour LED, red/green, common cathode, 3 lead | Tayda, Kingbright | D1–D8 |
| 2 | BAT85 | | D21, D22 |
| 18 | Resistor 470 Ω | | R60, R61, R80–R95 |
| 8 | Resistor 1k | | R23, R26, R29, R32, R35, R38, R41, R44 |
| 5 | Resistor 10k | | R9–R13 |
| 1 | Resistor 12k | | R46 |
| 8 | Resistor 13k | 1 % | R22, R25, R28, R31, R34, R37, R40, R47 |
| 2 | Resistor 15k | | R45, R48 |
| 1 | Resistor 33k | 1 % | R43 |
| 8 | Resistor 100k | 1 % | R21, R24, R27, R30, R33, R36, R39, R42 |
| 1 | Capacitor 100p | | C26 |
| 7 | Capacitor 1n | | C21–C25, C27, C28 |
| 7 | Capacitor 100n | 5.08 mm pitch | C8–C10, C31–C34 |
| 2 | Capacitor 1µ | | C29, C30 |
| 7 | Pot B10k, Alpha 9 mm vertical (Thonk) | | RV1–RV7 |
| 7 | Knobs | 2 large, 2 medium, 3 small | |
| 10 | Thonkiconn PJ398SM | | J1–J10 |
| 2 | Thonk low-profile LED button | colour to taste | SW1, SW2 |
| 3 | Male pin header 1×8, 1×9, 1×9 | Thonk male + female header bag | HF1–HF3 |
| 3 | Female socket 1×8, 1×9, 1×9 | | H1–H3 |
| 4 | M3 standoffs + screws | length = the mated headers' gap | |
| 2 | PCBs 59.4 × 108 mm, 2 layer | `Plaitsy Main PCB`, `Plaitsy Faceplate PCB` | |
| 1 | Panel PCB 60.6 × 128.5 mm | black mask, white silk, ENIG: `Plaitsy Panel PCB` | |

---

## Firmware (not started)

The plan is to port the Plaits 1.2 source to the Seed with libDaisy,
keeping all 24 engines:

- Audio at 48 kHz, block size 12, as on Plaits; OUT on channel 1, AUX on
  channel 2 of the Seed's codec.
- CV and pot handling as mapped above: eight ADC channels plus the mux on
  A10 (`InitMux(A10, 8, D26, D27, D28)`), each reading converted back to
  the jack voltage and then to Plaits' own ADC scale.
- The normalization probe on D14 into the TIMBRE, FM, MORPH, TRIG and
  LEVEL lugs, read back on their ADC channels, with thresholds set from
  the measured swing (about 0.4 V peak to peak after the −0.13 stage).
- The LEDs through the two 74HC595 on SPI1 (16 bits, latch on D13) at the
  1 ms UI rate, red / green / both; the buttons on D0 / D1 with pull-ups;
  `ui.cc` ported so the panel behaves as the manual describes.
- Settings and calibration in QSPI flash.

The Plaits firmware is © Emilie Gillet, MIT licence.
