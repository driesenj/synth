# Marblesy — design notes

A Mutable Instruments Marbles clone for Eurorack, 18HP, on two stacked PCBs
behind an aluminium panel: a Daisy Seed on Rob Heel's `seed_power_opamps`
breakout does the work, Thonk supplies the panel parts. Every reference
designator matches `hardware/tools/circuit.py`, which generates the EasyEDA
Pro schematic (`hardware/easyeda/Marbles.epro2`) and the panel files.

Status: schematic done and checked, panel files and panel PCB generated, both
PCBs routed by hand in EasyEDA Pro (2026-10-29, the pots re-routed on
2026-10-30) and audited (`hardware/easyeda/Marblesy-routed.epro2`,
see [PCB placement](#pcb-placement) and [Routing](#routing)). `circuit.py`
matches the routed boards pin for pin; the exporter checks that on every run.
Firmware written ([firmware/README.md](../firmware/README.md)), not yet run on
hardware.

---

## What Marbles needs

From the Marbles firmware (`marbles/drivers/*` in Emilie Gillet's eurorack
repository) and its calibration constants:

| Function | Marbles hardware | Count |
|---|---|---|
| Pots | DEJA VU, LENGTH, T RATE, T BIAS, T JITTER, X SPREAD, X BIAS, X STEPS | 8 |
| CV inputs, ±5 V full scale, inverting | the same minus LENGTH | 7 |
| Clock inputs, read as gates (inverted) with a normalization probe | T CLOCK, X CLOCK | 2 |
| Gate outputs | T1, T2, T3 | 3 |
| CV outputs, about ±5.3 V (16-bit DAC, code 32768 = 0 V, −6213 codes/V) | X1, X2, X3, Y | 4 |
| Buttons | t deja vu, t mode, t range, X deja vu, X mode, X range, X ext | 7 |
| LEDs | t deja vu (green), t mode (R/G), t range (R/G), X deja vu (green), X mode (R/G), X range (R/G), X ext (green) | 7 inside the buttons (11 lines) + 7 output LEDs |

Marbles reads the X SPREAD CV through two ADC channels and averages them;
this design reads it once. The firmware port handles that.

---

## Architecture

```
 panel ─┬─ faceplate board (FB)   16 Thonkiconn jacks, 8 Alpha pots, 7 LED buttons, 7 output LEDs,
        │   90 x 108 mm            74HC4051 pot mux, 2x 74HC595 (LEDs), 74HC165 (buttons),
        │                          probe resistors, pull-ups, LED resistors
        │      34 pins in 7 headers, 33 used (male on the FB, female on the MB)
        └─ main board (MB)        Daisy Seed on the seed_power_opamps breakout,
            90 x 108 mm            7 TL074 CV input stages, 2 clock input stages,
                                   3 gate stages, 2x MCP4922 DAC + 4 output stages,
                                   LM4040 2.5 V reference
```

Both boards are the same size and stack in the same orientation (jacks and
pots on the FB's bottom side towards the panel, headers on the FB's top side
mating with sockets on the MB's bottom side, Seed and breakout on the MB's
top side). That is the arrangement the Plaitsy PCB uses, and it keeps every
header at the same x/y on both boards.

### Daisy Seed pin map

| Seed pin | libDaisy | Net | Use |
|---|---|---|---|
| 1, 2 | D0, D1 | T_CLK, X_CLK | clock inputs (after the transistor, active low) |
| 3, 4, 5 | D2, D3, D4 | GATE_T1..T3 | gate outputs (to the x2.5 stages) |
| 8 | D7 (SPI1 NSS) | DAC_CS1 | MCP4922 U7 chip select |
| 9 | D8 (SPI1 SCK) | SPI_SCK | DACs, 74HC595, 74HC165 |
| 10 | D9 (SPI1 MISO) | SPI_MISO | 74HC165 Q7 |
| 11 | D10 (SPI1 MOSI) | SPI_MOSI | DACs SDI, 74HC595 SER |
| 12 | D11 | DAC_CS2 | MCP4922 U8 chip select |
| 13 | D12 | DAC_LDAC | both DACs, pulse after writing all four channels |
| 14 | D13 | LED_LATCH | 74HC595 RCLK |
| 15 | D14 | BTN_LOAD | 74HC165 /PL |
| 20, 40 | AGND, DGND | GND | both on the main board's GND |
| 21 | 3V3A | 3V3A | pots, mux, bias, reference, DACs |
| 22 | D15/A0 | PROBE | normalization probe output to the clock jacks' switch lugs |
| 23..28 | A1..A6 | ADC_T_RATE, ADC_T_BIAS, ADC_T_JITTER, ADC_DEJAVU, ADC_X_SPREAD, ADC_X_BIAS | CV inputs |
| 31 | A9 | ADC_X_STEPS | CV input |
| 32 | A10 | MUX_OUT | pot mux |
| 33, 34, 35 | D26, D27, D28 | MUX_S0..S2 | pot mux address |
| 38 | 3V3D | 3V3D | pull-ups, shift registers |
| 6, 7, 29, 30, 36, 37, 39 | D5, D6, A7, A8, D29, D30, VIN | — | free (A7/A8 are the Seed's own DAC pins) |

The breakout's headers land on the same footprint: J1 (GND, −12 V ×3), J3
(GND, +12 V ×3), J4 (audio out, unused), J5 (audio in, unused). The
breakout ties Seed pins 20 and 40 to one GND and feeds VIN from its own
DC/DC converter.

---

## Main board circuits

### CV inputs (7×)

Inverting TL074 stage, biased from 3V3A, same topology as Plaitsy but with the
gain set for Marbles' ±5 V inputs:

```
jack tip ── 100k ──┬── (−) TL074 ──┬── 1k ── Seed ADC
                   ├── 27k ────────┤
                   └── 1n ─────────┘
BIAS 1.32 V ──────── (+)
```

V_adc = 1.676 V − 0.27·V_in. ±5 V lands on 0.33–3.03 V; a ±12 V input pushes
about 1.3 mA through the 1k into the Seed's protection diodes, which is
within the STM32H7's limit. BIAS is 3V3A × 10k/25k = 1.32 V (R45 15k, R46
10k, C29 1 µ). Corner frequency 5.9 kHz. The firmware calibrates offset and
scale per channel, as Marbles does.

| Input | Section | Rin | Rf | Cf | Rs | ADC |
|---|---|---|---|---|---|---|
| T RATE | U3A | R21 | R22 | C21 | R23 | A1 |
| T BIAS | U3B | R24 | R25 | C22 | R26 | A2 |
| T JITTER | U3C | R27 | R28 | C23 | R29 | A3 |
| DEJA VU | U3D | R30 | R31 | C24 | R32 | A4 |
| X SPREAD | U4A | R33 | R34 | C25 | R35 | A5 |
| X BIAS | U4B | R36 | R37 | C26 | R38 | A6 |
| X STEPS | U4C | R39 | R40 | C27 | R41 | A9 |

### Clock inputs (2×)

```
jack tip ── 100k (R50/R52) ── base 2N3904 (Q1/Q2), emitter to GND
            BAT85 (D22/D23) cathode on the base, anode to GND (clamps negative swings)
            collector ── 10k (R51/R53) to 3V3D, and to the Seed GPIO
```

High input = collector low. Marbles reads its clock inputs inverted too, so
the port needs no change there. Threshold about 0.7 V.

**Normalization probe.** PROBE (A0) drives R9 and R10 (10k, on the
faceplate) into the switch lugs of the T CLOCK and X CLOCK jacks, each through
its own header pin (H3.3 = PROBE_F_2 for T, H6.3 = PROBE_F_1 for X). With no
cable, the lug touches the tip and the probe pattern reaches the
transistor; a cable breaks the path. Marbles' `ClockInputs::ReadNormalization`
works unchanged with that.

### Gate outputs (3×)

Non-inverting TL074 stage, gain 2.5 (R 10k to GND, 15k feedback), 1k series
out: 0 V / 8.25 V from the 3.3 V GPIO. U6A–C; U6D is a grounded follower.

### CV outputs (4×)

Two MCP4922 (12-bit dual SPI DAC, DIP-14) on 3V3A, reference 2.5 V from an
LM4040-2.5 (D21, fed through R47 1.5k from 3V3A, C30 100 n). U4D inverts the
reference to −2.5 V (R42/R43 10k). Each output stage is an inverting summer:

```
V_out = −(100k/23.2k)·V_dac − (100k/47k)·(−2.5 V) = 5.32 V − 4.31·V_dac
```

code 0 → +5.32 V, code 4095 → −5.45 V, 1k series out. The polarity is the
same as Marbles' own DAC stage (its calibration scale is negative), so the
port keeps Marbles' calibration logic and only changes the resolution. The
reference feeds both the DAC and the offset, so the outputs scale with it:
a reference 1 % high makes every voltage 1 % larger and leaves 0 V where it
is, and the output calibration takes it out.

The range has room for 1 % parts: ±1 % on the stage's resistors and on
R42/R43 (±2 % on the −2.5 V) and 0.5 % on the reference move the negative
end by up to 0.35 V with every tolerance at its worst (−5.11 V), and the
1k into a 100k input takes 1 % more (−5.06 V). A Monte Carlo with uniform
tolerances agrees: with 23.2k no module had an output short of ±5 V into
100k, and the worst of the four still reaches −5.16 V in 99 % of modules;
the first design's 24k (−5.10 V nominal) left about two modules in three
with an output short of −5 V, 23.7k still one in fourteen.

| Output | DAC | Section | Rdac | Rref | Rf | Rs |
|---|---|---|---|---|---|---|
| X1 | U7 A | U5A | R70 23.2k | R71 47k | R72 100k | R73 1k |
| X2 | U7 B | U5B | R74 | R75 | R76 | R77 |
| X3 | U8 A | U5C | R78 | R79 | R80 | R81 |
| Y | U8 B | U5D | R82 | R83 | R84 | R85 |

**12-bit vs 16-bit.** 12 bits over 10.8 V is 2.6 mV per step, 1/32 of a
semitone, fine for the quantised outputs and for the Y output. If you want
Marbles' 16-bit resolution, a DAC8564/DAC8565 (TSSOP-16, internal 2.5 V
reference with REFOUT) drops into the same output stage; only U7/U8, the
footprint and the SPI driver change.

MCP4922 wiring: VDD and /SHDN to 3V3A, VREFA/VREFB to VREF, /CS to the Seed,
SCK/SDI on the shared SPI bus, /LDAC shared. 100 n at each VDD (C39, C40).

### Power

±12 V from the breakout's J1/J3 headers; 100 n per rail at each TL074
(C31–C38). 3V3A load: 8 pots (2.6 mA), reference (0.4 mA), DACs (about
1 mA), mux. 3V3D load: pull-ups and shift registers, a few mA, LEDs at most
33 mA.

---

## Faceplate circuits

- **Jacks J1–J16** (Thonkiconn, pads 1 = sleeve, 2 = switch, 3 = tip).
  Sleeves to GND_F. CV inputs: switch lug to GND_F (reads 0 V unpatched).
  Clock inputs: switch lug through 10k to PROBE_F_2 (T) / PROBE_F_1 (X).
  Outputs: lug open.
- **Pots RV1–RV8** (Alpha 9 mm B10k): CCW end to GND_F, CW end to 3V3A_F,
  wiper into U1 (74HC4051), channel order below. C8 100 n at U1 pin 16.
- **LEDs**: U9 and U10 (74HC595, chained, SER from MOSI_F, SRCLK from SCK_F,
  RCLK from LED_LATCH_F, /OE low, /SRCLR high) drive the 11 LED lines. Every
  LED is inside a Thonk low-profile LED button. The three green ones (deja vu
  t / X, EXT) take one line each through 470 Ω to ground. The four bipolar
  red/green ones (mode and range) sit between their two lines with one 470 Ω
  on the red line: red line high and green line low gives red, the reverse
  gives green, both equal is off, and orange is the two alternated at the
  1 ms LED update. About 2.5 mA per lit LED. R80–R86.
- **Output LEDs**: Y, X1, X2, X3 (D14–D17) on U10 QG, QF, QE, QC through
  470 Ω (R87, R88, R89, R1); the firmware sets their brightness by PWM at
  the LED update rate. t1, t2, t3 (D11–D13) are passive: jack net → 3.3 kΩ (R91–R93) →
  LED → GND_F, about 1.5 mA, which costs 1.5 V across the gate stage's 1 kΩ
  output resistor (the gate stays above 6 V). The CV outputs cannot be
  loaded that way: any LED current through their 1 kΩ would shift the
  pitch CV. U10 QD is the spare line.
- **Buttons**: U11 (74HC165, /PL from BTN_LOAD_F, CP from SCK_F, Q7 to
  MISO_F, DS and CE low). D0–D6 read the seven buttons, each with a 10k
  pull-up to 3V3D_F (R100–R106); D7 is tied low. A pressed button joins
  its pads 3+4 (the input) to pads 1+2 (GND_D_F).
- C9–C11 100 n at U9–U11.

The mux channels and the U10 outputs were reassigned during routing; the
firmware must use these tables, not the panel order.

| Mux channel (Y) | 4051 pin | Pot |
|---|---|---|
| 0 | 13 | RV1 RATE |
| 1 | 14 | RV3 JITTER |
| 2 | 15 | RV4 DEJA VU |
| 3 | 12 | RV2 BIAS (t) |
| 4 | 1 | RV8 STEPS |
| 5 | 5 | RV5 LENGTH |
| 6 | 2 | RV7 BIAS (X) |
| 7 | 4 | RV6 SPREAD |

| 595 output | LED line | | 165 input | Button |
|---|---|---|---|---|
| U9 QA | D1 t deja vu (G) | | D0 | SW1 t deja vu |
| U9 QB, QC | D2 t mode (R, G) | | D1 | SW2 t mode |
| U9 QD, QE | D3 t range (R, G) | | D2 | SW3 t range |
| U9 QF | D4 X deja vu (G) | | D3 | SW4 X deja vu |
| U9 QG, QH | D5 X mode (R, G) | | D4 | SW5 X mode |
| U10 QA, QB | D6 X range (R, G) | | D5 | SW6 X range |
| U10 QC | D17 X3 output LED | | D6 | SW7 X ext |
| U10 QD | spare | | D7 | tied low |
| U10 QE | D16 X2 output LED | | | |
| U10 QF | D15 X1 output LED | | | |
| U10 QG | D14 Y output LED | | | |
| U10 QH | D7 X ext (G) | | | |

The SPI bus is shared by the DACs and the shift registers. The 595s shift on
every clock, including DAC transfers, but only latch on LED_LATCH, and the
165 only loads on BTN_LOAD, so the three never interfere. The firmware runs
the bus at 6.25 MHz (four DAC words every 31 µs need it), within the
74HC595's and 74HC165's limits at 3.3 V.

---

## Board-to-board headers

As routed. Positions in the PCB frame (rear view, x from the left as
EasyEDA shows the boards; front view x = 90 − x).

| Header | Pins | Where | Main board nets, pin 1 first (faceplate: same name + `_F`) |
|---|---|---|---|
| H1 | 8 | x 88, y 16–34 | CV_T_BIAS, CV_DEJAVU, CV_T_JITTER, CV_T_RATE, T_CLK_IN, T3, T2, T1 |
| H2 | 8 | x 2, y 7–25 | CV_X_BIAS, CV_X_STEPS, CV_X_SPREAD, X_CLK_IN, Y, X1, X2, X3 |
| H3 | 3 | x 88, y 53–59 | 3V3A, GND (GND_F), PROBE (PROBE_F_2) |
| H4 | 4 | x 74.5, y 30–37 | MUX_OUT, MUX_S0, MUX_S1, MUX_S2 |
| H5 | 4 | x 88, y 97–105 | SPI_MISO (MISO_F), SPI_SCK (SCK_F), BTN_LOAD, GND (GND_D_F) |
| H6 | 3 | x 2, y 43–49 | 3V3D, GND (GND_F), PROBE (PROBE_F_1) |
| H7 | 4 | x 2, y 97–105 | SPI_MOSI (MOSI_F), LED_LATCH, open, GND (GND_F) |

Male pins on the faceplate (HF1–HF7), female sockets on the main board, each
pair at the same x/y on both boards. GND_F (jacks, pots, mux, gate LEDs) and
GND_D_F (LEDs, buttons, logic) are separate on the faceplate and meet on the
main board's GND: GND_F through H3.2, H6.2 and H7.4, GND_D_F through H5.4.
The two PROBE pins join on the main board.

---

## Faceplate placement and panel

The faceplate board is 90 × 108 mm; the panel is 91.3 × 128.5 mm (18HP),
centred on it. The footprint origins are in `PLACEMENT` in `circuit.py`;
`panel.py` turns them into `hardware/panel/marbles-panel-holes.csv`, the 1:1
drill template and the artwork, applying the offsets of the footprints (jack
barrel 0.78 mm below the WQP518MA origin; Alpha pot shaft 4.0 mm beyond the
PTV09A origin, away from the pins, since the footprint's pin row is 3.5 mm
from its origin and the Alpha's shaft 7.5 mm from its pins).

**Knobs on the drawn layout since the re-route.** Until 2026-10-30
`panel.py` put the pot holes at origin + 0.53 mm, and the first routing
placed the pots for that figure. The real shafts are at origin + 4.0, which
put every knob 3.47 mm right of the drawing. The 2026-10-30 re-route moved
the pots until their shafts landed on the symmetric layout below (see
"Re-route" under Routing), so the panel needs no change
(`hardware/panel/marbles-panel-preview.png`).

The arrangement follows Mutable's Marbles panel (board mm, y up):

```
   y     (knob shafts)
  100.7  [t]o              DEJA VU (45)                o[X]      deja vu LED buttons
   82.75         RATE (22.65)              SPREAD (67.35)
   78.25  o MODE                                       MODE o
   66.55  BIAS (8.85)        LENGTH (45)        BIAS (81.15)   (BIAS knobs at y 59.95)
   61.75          o RANGE (25)             RANGE (65) o          range buttons, labels inside
   51.45                      o EXT
   44.75        JITTER (31.05)               STEPS (58.95)
   36.25  BIAS jack                                  BIAS jack
   21.85  CLOCK  RATE  JITTER  DEJA VU  STEPS  SPREAD  CLOCK     x = 9 + 12 k
   13.0   *      *     *       *        *      *       *         output LEDs, 4.2 mm left of each jack
    7.25  t1     t2    t3      Y        X1     X2      X3        outputs, same pitch
```

Three large knobs (RATE, DEJA VU, SPREAD, Ø15 drawn), five small (Ø10).
All seven buttons are Thonk low-profile LED buttons (5.5 mm cap, 6.5 mm
hole): green for the deja vu pair and EXT, bipolar red/green for mode and
range. Thonk's footprint gives their three plastic feet 1.2 mm holes so they
sit at Thonkiconn height, but two of those holes overlap the 1.6 mm pads of
pins 1 and 2 (DRC errors), so the board has none: clip the feet off before
fitting the buttons, and the body sits on the board at the same height. Panel hole sizes: pots
7.5, jacks 6.5, buttons 6.5; mounting slots 5.5 × 3.2 mm with their centres
3 mm from the top and bottom edge and 7.5 / 83.8 mm from the left (Eurorack). Pads of neighbouring parts clear
each other by 0.25 mm or more on the board (checked by the exporter).

The stack depth is the same as Plaitsy's: about 45–50 mm from the panel.

### Panel artwork

`panel.py` also writes `hardware/panel/marbles-panel.svg`, the panel as a
PCB in the Marbles style: black solder mask, white silkscreen (title, serif
`t` / `X` beside the deja vu buttons, scale arcs with ticks, labels under
the knobs, dotted guides from each knob to its CV jack, the three-state
labels beside the mode and range buttons in press order green / orange /
red, LENGTH graduations 1 2 3 4 6 8 12 16, STEPS and JITTER end marks), a
bare copper band with an LED left of each output label and behind the seven outputs with their labels
knocked out, every hole, and a mockup layer with knobs, nuts, caps and LEDs
for the preview. Colours, radii and the
title are the `ART` dict at the top of the artwork section; the SVG groups
`#holes`, `#silk` and `#copper` are the three layers an EasyEDA panel PCB
needs (drill, top silkscreen, top solder-mask opening). Knobs are drawn at
Ø15 (RATE, DEJA VU, SPREAD) and Ø10; the scale arcs assume those. The
title (serif 5.2 at x 12, baseline 7.4), the subtitle (2.1, right end
12 mm from the edge, baseline 6.6), the dotted band (y 9.6 and 10.6), the
rule (y 118.6) and the gold mushroom mark under it (4.1 mm tall, 1.6 mm
below the rule, centred; it replaced the maker line on 2026-11-02) sit at
the same spots on every module's panel.

`panel_pcb.py` builds the same drawing as the project's third board,
`Marblesy Panel PCB`: 91.3 × 128.5 outline, every hole and the four
5.5 × 3.2 slots as non-plated drills, the silkscreen (titles, labels, arcs,
ticks, graduations, marks, dotted guides as 0.12 mm dashes, LED-colour dots
as small rings, button rings) and the output band as a copper fill on the top
layer under a solder-mask opening of the same shape, so it comes out as bare
ENIG gold; the output labels are silkscreen on top of it. The band
(2.6 mm from the panel sides, 86.1 × 15.2 mm) leaves a 0.4 mm ring of bare
board under black mask around each of the 14 holes through it (EasyEDA's DRC
wants copper 0.3 mm from a slot region): each ring is a counter-clockwise
circle in the fill's path list, which EasyEDA fills with the nonzero rule. Text uses the
default stroke font and estimated centring, so expect to nudge a few labels.
Order it as a 1.6 mm board, black mask, white silk, ENIG. The fab may ask
about silkscreen over bare copper (the band labels; some fabs drop it, in
which case put the labels on the solder-mask layer instead and they come out
gold on black).

`Marblesy-routed.epro2` carries the same drawing: its panel board's
holes, slots, silkscreen, copper and outline were replaced with the
generated ones on 2026-10-31, keeping that board's own rules and settings.
After a change to the panel, put the regenerated drawing in again the same
way, or the routed project's panel goes stale (it had kept the pot holes
0.53 mm right of the shafts from 2026-10-29 until then).

---

## PCB placement

The boards were placed by `hardware/tools/pcb.py`, then routed by hand in
EasyEDA Pro, which moved most rear-side parts and every header. The routed
project (`hardware/easyeda/Marblesy-routed.epro2`) is now the master for the
layout: `pcb.py` reads the rear sides and the headers from it, places the
panel parts from `PLACEMENT` as before, and `routed_check()` compares the two
pad by pad (position and net) on every run of the exporter, together with the
older checks (pads 0.25 mm apart, 0.5 mm from the edge, no bodies overlapping
on one side, nothing under a standoff, header pins coinciding on both boards,
panel parts exactly at `PLACEMENT`). Previews:
`hardware/easyeda/marbles-easyeda-pcb-*.png`.

**Frame.** Each PCB is drawn as EasyEDA shows it, looking at the top layer,
which on both boards is the rear of the stack: x to the right, y up, origin
at the bottom-left corner. The front view of the faceplate placement is its
mirror image, `x_front = 90 − x`. Both boards use this one frame, so the
seven header pairs have identical coordinates on both PCBs and the stack
lines up pin for pin. EasyEDA mirrors a bottom-layer footprint about its own
X axis (y → −y) before rotating it; `pcb.py` uses that rule and picks the
panel parts' angles by it (jack sleeve pad towards the top of the board,
pot pins in a column towards the left as seen from the front, button pads
1/4 on the left, LED button LED pins along x with pin 5 on the right).

**Faceplate board.** Bottom layer: the 16 jacks, 8 pots, 7 LED buttons and 7
output LEDs, unchanged. Top (rear) layer, PCB frame: the headers along both
side edges (table above) and H4 beside U1; U1 (mux) and U10 horizontal in
the strip above the CV jacks, U9 and U11 vertical either side of the centre
between the big knobs, each with its 100 n within 2.6–6.9 mm of pin 16; the
output-LED resistors R87–R89 and R1 standing beside the output LEDs, the
gate-LED resistors R91–R93 along the bottom edge between the output jacks,
the pull-ups and LED resistors wherever routing wanted them.

**Main board.** Bottom layer: the seven female sockets. Top (rear) layer: the
Seed breakout vertical in the middle, centred at (45, 64.5), pad rows at
x 37.4 and 52.6, power end (J1/J3, y 27–35) down, USB end up. The
breakout's board covers x 35.6–54.4, y 3.7–100.5: under it sit R33, R36 and
R39 (horizontal, 2.3 mm tall, under 8.5 mm sockets) and the two centre
mounting screws, so fit those before plugging the breakout in. Around it:
U6 (gate stages) top left, U7 and U8 (DACs) left of centre, U5 (DAC output
stages) bottom left, U3 (T CV stages) top right, U4 (X CV stages and the
−2.5 V inverter) bottom right, the clock stages (Q1/Q2, D22/D23, R50–R53)
along the top right, the reference D21 with C30 at (63, 30), the bias
divider R45/R46/C29 bottom right. 33 of the resistors stand up on a 2.54 mm
footprint (`1/4W-RESISTOR-VERTICAL`; the exporter gives them a vertical
device of the same value). Every TL074 supply pin has its 100 n within
3.2–4.3 mm, both DACs theirs within 3.8 mm.

**Mounting.** Four 3.2 mm holes, front-view (45, 82), (45, 33), (79, 69),
(11, 69), identical on both boards; the side ones sit between the BIAS knob
and the mode button on the faceplate, the centre ones between the breakout's
pad rows on the main board. M3 standoffs between the boards (a screw head
needs 3 mm of free panel-side board around each hole, which these have).

**Pot housings.** The pots sit on the Alpha footprint
`POT-ALPHA-9MM-RD901F`, whose outline is the Alpha 9 mm housing (KiCad
RD901F): 9.5 mm wide, from 1 mm off the pin row to 4.85 mm past the shaft.
No routed rear-side pad comes within 0.8 mm of a pot housing, and no
rear-side body sits over a pot pin. Rear pads whose ring only touches a jack
or LED body edge (the centre stays 0.6–0.75 mm outside): R91–R93 at the
t1–t3 jacks, R87–R89 and R1 at the output LEDs.

**Assumptions to check.** The breakout's underside at its power end must
clear the three 2.3 mm resistors under it.

**Two library footprints that did not fit the parts, replaced in the
re-route.**
- The TL074ACN footprint (`PDIP-14_L19.3-W6.4-P2.54-LS9.0-BL`, used for
  U3–U8, the four TL074s and both MCP4922s) has its pin rows 8.89 mm apart
  instead of 7.62. No DIP socket fits, and a chip only goes in with its legs
  bent (the user had to on the Kick, Mixer and Output boards, which use the
  same footprint). U3–U8 are now on `DIP-14-W7.62-P2.54`.
- The library pot footprint is Bourns' PTV09A: its lug slots (2.2 × 2.0 mm
  at ±4.3, 0.5 mm towards the pins from the shaft line) sit 0.5 mm off both
  ways from an Alpha pot's lugs (±4.8 on the shaft line, KiCad
  RD901F-40-00D), so a lug's outer corner overhangs the slot. The pots are
  now on `POT-ALPHA-9MM-RD901F`.

---

## Routing

Routed by hand in EasyEDA Pro on 2026-10-29, the pots re-routed on
2026-10-30 (below), and audited from the final export (tracks, vias,
pads and the computed pour islands with their thermal spokes):

- **Rules.** Clearance 0.152 mm (the project's rule), signal tracks 0.3 mm,
  power 0.6 mm (±12 V, 3V3A, 3V3D, 3V3A_F, 3V3D_F, GND_D_F), vias
  0.61 / 0.3 mm.
- **Grounds.** Main board: GND poured on both layers, 118 stitching vias.
  Faceplate: GND_F poured on both layers with 153 ground vias; GND_D_F as
  0.6 mm tracks to H5.4, never touching GND_F.
- **Connectivity.** Every net complete on both boards, no shorts, no stray
  copper, no pour island left without a pad. The closest gaps sit at the
  0.152 mm rule: LED_LATCH_F past a GND_F via at (10.5, 96.9), L_D6_G past
  SW6 pin 3, GND_D_F past R80 pin 2, T3_F past D11 pin 1 on the faceplate,
  ADC_X_STEPS past R29 pin 1 on the main board. Fine for the fab; keep the
  joints neat there.
- **Standoffs.** Within the standoffs' 3 mm radius on the standoff side lie
  ground vias, U11 pin 4 (2.9 mm from the (45, 82) hole's centre, as
  before) and BTN_X_MODE_F at 2.85 mm from it, both at the edge of a 5 mm
  standoff's corners. The STEPS wiper keeps 3.35 mm from the (45, 33) one.
- **Sensitive nets.** On the main board no summing node, ADC line, reference
  or pot wiper runs beside a switching line closer than 0.7 mm. The 0.7 mm
  cases (CV_X_BIAS beside T1 for 31 mm, MUX_OUT beside MUX_S0 for 33 mm,
  DAC_X2 beside PROBE for 22 mm, VREF and NEG_REF beside PROBE for 7–8 mm)
  all have a low-impedance victim. On the faceplate the re-routed wipers keep
  0.75 mm or more from every LED, button and logic line; the one closer run
  is 3V3A_F beside LED_D2_R for 3 mm (a supply). Tracks under the jack bodies
  on the panel side are fine: the Thonkiconn body is plastic and the copper
  is under mask.
- **Harmless leftovers.** A 2 mm dead-end stub on OA_T_JITTER at R29
  (60, 61.15). A NEG_REF via at (22.7, 35) and an ADC_T_BIAS via at (63, 49)
  have copper on the bottom layer only. T1–T3 run about 185 mm round the main
  board (U6 is top left, H1 bottom right); the TL074's edges are slow. 3V3D_F
  enters the faceplate at H6 while GND_D_F leaves at H5, so the LED current
  loop spans the board.

`hardware/tools/copper_audit.py <export>` (copied from Plaitsy) runs these
checks on any export: nets through tracks, vias, pads, pour islands and
spokes; shorts; gaps with exact pad shapes; standoff keepouts; pads against
the generator; header pins on both boards; panel holes against
`panel_pcb.py`. Its "barrel" lines are the CV and output tracks under the
jacks on the panel side, fine here as above. Its footprint differences are
names only: the routed boards use the library's `1/4W-RESISTOR-VERTICAL`
and `HDR-TH_3P-P2.54_CS-1165SDIG` where the generator writes its own, on
the same pads.

**Value labels.** Every resistor, capacitor and pot carries its value on the
silkscreen beside it, and the three diodes their part name (BAT85 at D22
and D23, LM4040-2.5 at D21): 35 labels on the faceplate (B10k on the pots,
on the panel-side silk; 470, 10k, 3k3 and 100n on the rear) and 76 on the
main board, all on its top. `hardware/tools/value_labels.py` (copied from
Plaitsy) put them in the first free spot beside each part where no other
labelled part is nearer; the values come per board, since R80–R85 exist on
both (100k / 1k / 23k2 / 47k on the main board, 470 on the faceplate). R33
and R39 have theirs under the Seed breakout (they are soldered before it
goes on). R80 on the main board has no label: its only free spot sat
against R78. R42 and R66 share a near-tie with R47 and R67, which have their
own labels right beside them. 98 labels are at the designators' 45 mil,
seven at 38 and six at 32 mil (0.8 mm, readable but under the 1 mm many fabs
recommend). When R70, R74, R78 and R82 went from 24k to 23k2 (2026-11-02)
their longer labels moved to the next free spot by the same rules, three
of them smaller; R47's 1k5 kept its place. Previews:
`hardware/easyeda/marbles-labels-*.png`. The labels
are in `Marblesy-routed.epro2`; run `value_labels.py` again only on an
export that does not carry them yet.

### Re-route: pots back on the drawn layout, standard footprints (2026-10-30)

The eight pots moved so their shafts land on the symmetric layout
(`POT_XY` in the diagram above), on the Alpha pot's own footprint. U3–U8 on
the main board got a 7.62 mm DIP-14 so sockets fit. Each pot's pin
direction was picked against the routed copper, as the one that needs no
other part moved and cuts the fewest foreign tracks. RATE, DEJA VU and
JITTER turn their pins up, SPREAD and BIAS t to the right (front view),
BIAS X, LENGTH and STEPS keep them to the left. Besides them C10 moved
0.75 mm, out from under DEJA VU's housing, and R104 1 mm (to 11.5, 48)
during routing.

| Part | Knob | Shaft (front) | Pins (front) | EasyEDA x, y (mm, top-layer view) | Rotation (bottom layer) |
|---|---|---|---|---|---|
| RV1 | RATE | 22.65, 82.75 | up | 67.35, 86.75 | 0 |
| RV6 | SPREAD | 67.35, 82.75 | right | 18.65, 82.75 | 90 |
| RV4 | DEJA VU | 45, 97.55 | up | 45.0, 101.55 | 0 |
| RV2 | BIAS t | 8.85, 59.95 | right | 77.15, 59.95 | 90 |
| RV7 | BIAS X | 81.15, 59.95 | left | 12.85, 59.95 | 270 |
| RV5 | LENGTH | 45, 66.55 | left | 49.0, 66.55 | 270 |
| RV3 | JITTER | 31.05, 44.75 | up | 58.95, 48.75 | 0 |
| RV8 | STEPS | 58.95, 44.75 | left | 35.05, 44.75 | 270 |
| C10 | | | | 53.25, 92.5 (was 52.5) | 0 |

The re-route started from the routed project with the parts in the table
moved, the copper in their way deleted (1.3 m of the faceplate's 3.2 m: the
wipers, most of 3V3A_F and the logic, button and LED stretches that ran over
a new pad) and the main board's track ends moved onto the new DIP pins. The
project's two footprint copies were edited in place, keeping every pad id:
`POT-ALPHA-9MM-RD901F` (lugs at ±4.8 on the shaft line, KiCad's
2.72 × 3.24 mm pads with 1.1 × 1.8 mm slots, the Alpha housing as its
outline) and `DIP-14-W7.62-P2.54` (rows ±3.81, 1.6 mm pads). The EasyEDA
library still has the old ones, so do not update these footprints from the
library in this project. The faceplate ends up with 3.2 m of track again,
the main board 4.4 m.

The sync: `circuit.POT_XY` holds the shafts of the routed pots and
`POT_PINS` their pin directions; the exporter takes the drawn 7.62 mm DIP-14
and Alpha footprints for the TL074, MCP4922 and pot devices because the
routed export carries them, and the rear side (R104 included) from the
export as before.

### Board fixes after the firmware review (2026-11-02)

Made in `Marblesy-routed.epro2` by a script, every other record kept as
EasyEDA wrote it, and in `circuit.py` / the exporter to match:

- **D21, the LM4040, now fits TO-92 parts.** The footprint had pad 1 =
  cathode (VREF), pad 2 = anode (GND), pad 3 open, the SOT-23 order. In
  TO-92 the cathode is pin 2, the middle lead; TI's drawing puts the anode
  on pin 3 and an older TI table on pin 1. Pads 1, 2, 3 are now GND, VREF,
  GND, so the part works whichever is right and whichever way round it
  goes in. VREF on the bottom layer now leaves its track from the left at
  x 61.5 for pad 2, and pad 2 feeds C30 down the right of pad 1 (x 64.5);
  the two segments into pad 1 are gone. The stale GND pours were cut
  around the new track (the old channel stays cut) and the thermal spokes
  moved from pad 2 to pads 1 and 3. The symbol's pins are renumbered
  (K 2, A 3, NC 1) in all three copies in the project, and the schematic
  ties pin 1 to GND. Boards made from the earlier export: put pin 2 in
  pad 1 and pin 3 in pad 2, and cut pin 1 off (NC in TI's current
  datasheet; check that your part has its anode on pin 3).
- **R47 2.2k → 1.5k**: 0.53 mA into the reference, 0.28 mA left for the
  LM4040 after the −2.5 V inverter's 0.25 mA (its minimum is 60–65 µA).
- **R70, R74, R78, R82 24k → 23.2k** for the outputs' range (see CV
  outputs above); `kDacInputResistor` in the firmware matches.

Checked after the change: `easyeda_export.py` (0 schematic and 0 PCB
problems against the routed project), `copper_audit.py` (every net in one
piece, no shorts, no new clearance notes) and the routed schematic's own
wiring against `circuit.py` (only the wires drawn in EasyEDA without a net
name differ, as before). The pours are the script's, not EasyEDA's: rebuild
them before the Gerbers (open items).

---

## BOM

Generated from `circuit.py` by `hardware/tools/bom.py`, with the Thonk parts in their own table:
[bom.md](bom.md), and as CSV in `hardware/bom/`. The Thonk parts of Spore, Orchid, Moss and
Mycelium are summed into one order in [bom/thonk-order.md](../../bom/thonk-order.md).

---

## Firmware

`firmware/` ports Marbles' final firmware to libDaisy; its README has the
details. Where it ended up against the plan that stood here:

- The I/O runs from a 32 kHz timer interrupt, as Marbles' DAC interrupt,
  not from the audio callback: Marbles' code counts in 32 kHz samples and
  5-sample blocks (not 8). The rendering runs in a low-priority interrupt,
  so the QSPI writes in the main loop cannot stall it.
- `Adc` as planned (7 CVs direct, the pots through the mux in the mux
  table's order); each CV reading is converted to the value Marbles' own
  input stage would give, so Marbles' calibration runs unchanged.
- `Dac`: both MCP4922s every sample, then one LDAC pulse; Marbles' 16-bit
  codes rounded to 12 bits, the nominal calibration from the output stage
  above. The DACs use their buffered VREF input (see the board fixes of
  2026-11-02).
- `Leds`/`Switches`: the 595 frame every 4 samples (yellow alternates
  red and green; the output LEDs get 16 brightness levels by PWM), the 165
  every millisecond. SPI1 runs at 6.25 MHz in mode 0 for all of it.
- Added: a calibration of the CV outputs through the X SPREAD input (hold
  t range, press X range), since Marbles calibrates its DAC on the factory
  rig only.

The Marbles firmware is © Emilie Gillet, MIT licence.

---

## Open items

- Measure 2.50 V at C30 before calibrating the outputs (the LM4040; see
  the board fixes of 2026-11-02).
- Optional: nothing holds the SPI bus while the Seed is in its bootloader,
  so the LEDs (and the DACs) can change at random meanwhile. 100k pull-downs
  on SPI_SCK and LED_LATCH and pull-ups on DAC_CS1, DAC_CS2 and DAC_LDAC
  would hold them; cosmetic only.
- Check the LED buttons' switch pairing before fitting all seven: the
  netlist assumes pins 1+2 and 3+4 are joined inside (continuity 1-2 and
  3-4 at rest, 1-3 only when pressed). Also see which way the bipolar ones
  light red: the firmware assumes the red line high and the green line low
  gives red (its table can be swapped).
- Clip the three plastic feet off each LED button, so its body sits on the
  board at Thonkiconn height.
- Check that the underside of the breakout's power end clears R33, R36 and
  R39 (2.3 mm) before soldering them flat under it.
- Import `Marblesy-routed.epro2` again (the corrected panel board, the
  value labels, the D21 / R47 / 23.2k fixes and, since 2026-11-02, the
  panel name **Spore** with the gold mushroom mark in place of the maker
  line are in it), rebuild all
  copper areas on the main board (its pours around D21 were cut by a
  script), run DRC on all three boards, and make the Gerbers from that
  import. Export it back over `Marblesy-routed.epro2` and rerun
  `easyeda_export.py` and `copper_audit.py`.
