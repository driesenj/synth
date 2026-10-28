# Marblesy — design notes

A Mutable Instruments Marbles clone for Eurorack, 18HP, on two stacked PCBs
behind an aluminium panel: a Daisy Seed on Rob Heel's `seed_power_opamps`
breakout does the work, Thonk supplies the panel parts. Every reference
designator matches `hardware/tools/circuit.py`, which generates the EasyEDA
Pro schematic (`hardware/easyeda/Marbles.epro2`) and the panel files.

Status: schematic done and checked, footprints assigned, faceplate placement
defined, panel template generated, both PCBs placed and net-assigned (see
[PCB placement](#pcb-placement)). PCB routing and firmware not started.

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
| LEDs | t deja vu (green), t mode (R/G), t range (R/G), X deja vu (green), X mode (R/G), X range (R/G), X ext (green) | 7, 11 lines |

Marbles reads the X SPREAD CV through two ADC channels and averages them;
this design reads it once. The firmware port handles that.

---

## Architecture

```
 panel ─┬─ faceplate board (FB)   16 Thonkiconn jacks, 8 Alpha pots, 7 buttons, 7 LEDs,
        │   90 x 108 mm            74HC4051 pot mux, 2x 74HC595 (LEDs), 74HC165 (buttons),
        │                          probe resistors, pull-ups, LED resistors
        │      31 pins in 5 headers (male on the FB, female on the MB)
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
faceplate) into the switch lugs of the T CLOCK and X CLOCK jacks. With no
cable, the lug touches the tip and the probe pattern reaches the
transistor; a cable breaks the path. Marbles' `ClockInputs::ReadNormalization`
works unchanged with that.

### Gate outputs (3×)

Non-inverting TL074 stage, gain 2.5 (R 10k to GND, 15k feedback), 1k series
out: 0 V / 8.25 V from the 3.3 V GPIO. U6A–C; U6D is a grounded follower.

### CV outputs (4×)

Two MCP4922 (12-bit dual SPI DAC, DIP-14) on 3V3A, reference 2.5 V from an
LM4040-2.5 (D21, fed through R47 2.2k from 3V3A, C30 100 n). U4D inverts the
reference to −2.5 V (R42/R43 10k). Each output stage is an inverting summer:

```
V_out = −(100k/24k)·V_dac − (100k/47k)·(−2.5 V) = 5.32 V − 4.17·V_dac
```

code 0 → +5.3 V, code 4095 → −5.1 V, 1k series out. The polarity is the same
as Marbles' own DAC stage (its calibration scale is negative), so the port
keeps Marbles' calibration logic and only changes the resolution. The
reference feeds both the DAC and the offset, so reference drift cancels.

| Output | DAC | Section | Rdac | Rref | Rf | Rs |
|---|---|---|---|---|---|---|
| X1 | U7 A | U5A | R70 24k | R71 47k | R72 100k | R73 1k |
| X2 | U7 B | U5B | R74 | R75 | R76 | R77 |
| X3 | U8 A | U5C | R78 | R79 | R80 | R81 |
| Y | U8 B | U5D | R82 | R83 | R84 | R85 |

**12-bit vs 16-bit.** 12 bits over 10.4 V is 2.5 mV per step, 1/40 of a
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
  Clock inputs: switch lug through 10k to PROBE_F. Outputs: lug open.
- **Pots RV1–RV8** (Alpha 9 mm B10k): CCW end to GND_F, CW end to 3V3A_F,
  wiper into U1 (74HC4051), channel order below. C8 100 n at U1 pin 16.
- **LEDs**: U9 and U10 (74HC595, chained, SER from MOSI_F, SRCLK from SCK_F,
  RCLK from LED_LATCH_F, /OE low, /SRCLR high) drive the 11 LED lines through
  470 Ω (R80–R90). U10 QD–QH are spare.
- **Buttons**: U11 (74HC165, /PL from BTN_LOAD_F, CP from SCK_F, Q7 to
  MISO_F, DS and CE low). D0–D6 read the seven buttons, each with a 10k
  pull-up to 3V3D_F (R100–R106); D7 is tied low. Buttons connect pads 2+3 to
  pads 1+4 (GND_D_F).
- C9–C11 100 n at U9–U11.

| Mux channel (Y) | 4051 pin | Pot |
|---|---|---|
| 0 | 13 | RV1 RATE |
| 1 | 14 | RV2 BIAS (t) |
| 2 | 15 | RV3 JITTER |
| 3 | 12 | RV4 DEJA VU |
| 4 | 1 | RV5 LENGTH |
| 5 | 5 | RV6 SPREAD |
| 6 | 2 | RV7 BIAS (X) |
| 7 | 4 | RV8 STEPS |

| 595 output | LED line | | 165 input | Button |
|---|---|---|---|---|
| U9 QA | D1 t deja vu (G) | | D0 | SW1 t deja vu |
| U9 QB, QC | D2 t mode (R, G) | | D1 | SW2 t mode |
| U9 QD, QE | D3 t range (R, G) | | D2 | SW3 t range |
| U9 QF | D4 X deja vu (G) | | D3 | SW4 X deja vu |
| U9 QG, QH | D5 X mode (R, G) | | D4 | SW5 X mode |
| U10 QA, QB | D6 X range (R, G) | | D5 | SW6 X range |
| U10 QC | D7 X ext (G) | | D6 | SW7 X ext |

The SPI bus is shared by the DACs and the shift registers. The 595s shift on
every clock, including DAC transfers, but only latch on LED_LATCH, and the
165 only loads on BTN_LOAD, so the three never interfere. Keep the bus at
1 MHz or so over the header.

---

## Board-to-board headers

| Header | Pins | Main board nets (faceplate: same name + `_F`) |
|---|---|---|
| H1 | 8 | CV_T_RATE, CV_T_BIAS, CV_T_JITTER, CV_DEJAVU, CV_X_SPREAD, CV_X_BIAS, CV_X_STEPS, PROBE |
| H2 | 6 | T_CLK_IN, X_CLK_IN, T1, T2, T3, GND (GND_F) |
| H3 | 6 | X1, X2, X3, Y, GND (GND_F), 3V3A |
| H4 | 4 | MUX_OUT, MUX_S0, MUX_S1, MUX_S2 |
| H5 | 7 | SPI_SCK, SPI_MOSI, SPI_MISO, LED_LATCH, BTN_LOAD, 3V3D, GND (GND_D_F) |

Male pins on the faceplate (HF1–HF5), female sockets on the main board.
Place each pair at the same x/y on both boards. GND_F (jacks, pots, mux) and
GND_D_F (LEDs, buttons, logic) are separate on the faceplate and meet on the
main board's GND.

---

## Faceplate placement and panel

The faceplate board is 90 × 108 mm; the panel is 91.3 × 128.5 mm (18HP). The
footprint origins are in `PLACEMENT` in `circuit.py`; `panel.py` turns them
into `hardware/panel/marbles-panel-holes.csv` and the 1:1 drill template,
applying the offsets measured on the Plaitsy PCB audit (jack barrel 0.78 mm
below the WQP518MA origin, pot shaft 0.53 mm beyond the PTV09A origin).

```
   y (mm)
   97   [t mode]  RATE          DEJA VU          SPREAD  [X mode]
   92              o              o                o
   80   [t range]                                          [X range]
   68            BIAS (t)       LENGTH          BIAS (X)
   59              [t deja vu]      [X deja vu]
   46            JITTER                          STEPS
   36                        [X ext]
   22.6  T CLK  RATE  BIAS  JITTER  DEJA VU  SPREAD  BIAS  STEPS   (jack row, 11 mm pitch)
    7.7  T1     T2    T3    X CLK   X1       X2      X3    Y
```

Pots at x = 14 / 45 / 76, buttons at 30 / 60 (top) and 36 / 54 / 45,
bicolour LEDs 8 mm beside their buttons. A clearance check in the repo's
history found no overlapping bodies at these positions. Panel hole sizes:
pots 7.5, jacks 6.5, LEDs 3.2, buttons 12.5 (for the 12 mm round cap; check
your switch), mounting 3.2.

The stack depth is the same as Plaitsy's: about 45–50 mm from the panel.

### Panel artwork

`panel.py` also writes `hardware/panel/marbles-panel.svg`, a draft of the
panel as a PCB: black solder mask, white silkscreen (title, `t` / `X`
section letters, scale arcs with ticks, labels, dotted LED-to-button
ticks), bare copper pills for the seven outputs, every hole, and a mockup
layer with knobs, nuts, caps and LEDs for the preview. Colours, radii and the
title are the `ART` dict at the top of the artwork section; the SVG groups
`#holes`, `#silk` and `#copper` are the three layers an EasyEDA panel PCB
needs (drill, top silkscreen, top solder-mask opening). Knobs are drawn at
Ø15 (RATE, DEJA VU, SPREAD) and Ø10; the scale arcs assume those.

---

## PCB placement

`hardware/tools/pcb.py` places every part of both boards, assigns each pad
its net and writes the two PCB documents into `Marbles.epro2`; the exporter
checks the result (pads 0.25 mm apart or more, 0.5 mm from the edge, no
bodies overlapping on one side, nothing under a standoff, header pins
coinciding on both boards, panel parts exactly at `PLACEMENT`). Nothing is
routed. Previews: `hardware/easyeda/marbles-easyeda-pcb-*.png`.

**Frame.** Each PCB is drawn as EasyEDA shows it, looking at the top layer,
which on both boards is the rear of the stack: x to the right, y up, origin
at the bottom-left corner. The front view of the faceplate placement is its
mirror image, `x_front = 90 − x`. Both boards use this one frame, so the
five header pairs have identical coordinates on both PCBs and the stack
lines up pin for pin. EasyEDA mirrors a bottom-layer footprint about its own
X axis (y → −y) before rotating it; `pcb.py` uses that rule and picks the
panel parts' angles by it (jack sleeve pad towards the top of the board,
pot pins in a column towards the left as seen from the front, button pads
1/4 on the left, LED pad 1 on the left).

**Faceplate board.** Bottom layer: the 16 jacks, 8 pots, 7 buttons, 7 LEDs.
Top (rear) layer, inside the 8.5 mm header gap: U1 and U11 in the strip
between the top jack row and the lowest pots (y 29–42), U9 and U10 in the
pockets between the pot rows at the left and right edges (y 52–62), the
button pull-ups in the right margin, the LED resistors in the left margin
and the pockets at y 74–87, the probe resistors beside U1, one 100 n per IC.
The male headers (front-view x, y): H1 (20, 104), H3 (45, 104), H2
(70, 104), H4 (33, 41), H5 (56, 41); pin 1 towards +x in the front view.

**Main board.** Bottom layer: the five female sockets at the same spots.
Top (rear) layer: the Seed breakout vertical along the left edge, centred at
(11, 64) in the PCB frame, power end (J1/J3) down and USB end up; the four
TL074s vertical at x = 28 (U3 top, U6 bottom), each with its resistors in
horizontal columns at x = 41.5 / 54.5 (/ 67.5) and its capacitors beside
them; the two MCP4922 at the bottom right with C39/C40, R47, D21 and C30
above them; the clock input stages in the right strip. Every main-board
part except the sockets is on the rear side, so the front side carries
only sockets and standoffs.

**Mounting.** Four 3.2 mm holes, front-view (4.5, 33), (4.5, 104),
(85.5, 104), (79, 84), identical on both boards; the odd one sits between
the breakout's two pad rows on the main board. M3 standoffs between the
boards; the breakout and Seed hang on the main board's rear.

**Assumptions to check.** The library PTV09A footprint draws the pot body
9 mm beyond its origin; the checks use 4 mm (the Alpha 9 mm housing ends
about 3.3 mm beyond the shaft, as in KiCad's RD901F footprint). If your
pots are deeper than that, the LEDs 8 mm from the pot origins (D2, D3,
D5, D6) are the parts to watch. The 5 × 5 button pairing (item 3 of the
Plaitsy audit) still has to be verified on a real switch.

---

## BOM

| Qty | Part | Refs | Source |
|---|---|---|---|
| 1 | Daisy Seed | U2 | Thonk |
| 1 | seed_power_opamps breakout, built | U2 | OSHWLab (Rob Heel) |
| 16 | Thonkiconn PJ398SM + nut | J1–J16 | Thonk |
| 8 | Alpha 9 mm vertical B10K (pick the shaft to match your knobs) | RV1–RV8 | Thonk |
| 7 | Highly Tactile switch KS01-B, Ø12, 5×5 mm pins | SW1–SW7 | Thonk |
| 3 | 3 mm green LED | D1, D4, D7 | Thonk |
| 4 | 3 mm bicolour R/G, common cathode, 3 leads, 1.27 mm pitch | D2, D3, D5, D6 | Tayda / Kingbright (not at Thonk) |
| 8 | Knobs: 3 large (RATE, DEJA VU, SPREAD), 5 small | | Thonk |
| 4 | TL074 + DIP-14 socket | U3–U6 | Thonk |
| 2 | MCP4922 + DIP-14 socket | U7, U8 | Mouser / Farnell |
| 1 | 74HC4051 + DIP-16 socket | U1 | Tayda / Mouser |
| 2 | 74HC595 + DIP-16 socket | U9, U10 | Tayda / Mouser |
| 1 | 74HC165 + DIP-16 socket | U11 | Tayda / Mouser |
| 2 | 2N3904 | Q1, Q2 | Tayda |
| 1 | LM4040-2.5 (TO-92) | D21 | Mouser |
| 2 | BAT85 | D22, D23 | Tayda |
| 7 | 100k 1 % | R21, R24, R27, R30, R33, R36, R39 | |
| 7 | 27k 1 % | R22, R25, R28, R31, R34, R37, R40 | |
| 4 | 24k 1 % | R70, R74, R78, R82 | |
| 4 | 47k 1 % | R71, R75, R79, R83 | |
| 4 | 100k 1 % | R72, R76, R80, R84 | |
| 2 | 100k | R50, R52 | |
| 4 | 15k | R45, R61, R64, R67 | |
| 15 | 10k | R42, R43, R46, R51, R53, R60, R63, R66, R9, R10, R100–R106 | |
| 14 | 1k | R23, R26, R29, R32, R35, R38, R41, R62, R65, R68, R73, R77, R81, R85 | |
| 1 | 2.2k | R47 | |
| 11 | 470 Ω | R80–R90 (faceplate) | |
| 7 | 1 n C0G | C21–C27 | |
| 1 | 1 µ | C29 | |
| 15 | 100 n | C8–C11, C30–C40 | |
| 5 + 5 | 1×8, 1×6, 1×6, 1×4, 1×7 male pins / female sockets | H1–H5 | Thonk header bag |
| 1 | 18HP aluminium panel, 4× M3 | | |

Everything on the main board is through-hole.

---

## Firmware (not started)

Port the Marbles sources to libDaisy, as planned for Plaitsy:

- `Adc`: 7 CV channels direct, 8 pots through `AdcChannelConfig::InitMux(A10, 8, D26, D27, D28)`.
  Marbles' `CvReader` expects inverted, calibrated readings; keep its
  calibration routine (C1/C3 for RATE and SPREAD, offsets for the rest).
- `ClockInputs`: GPIO D0/D1, active low; probe on D15.
- `GateOutputs`: D2–D4.
- `Dac`: SPI1, two MCP4922 (16-bit frames: A/B select, BUF, GA, SHDN, 12
  data bits), write four channels then pulse LDAC once per block. Marbles'
  16-bit DAC codes map to 12-bit by dropping the low four bits; keep
  `dac_offset`/`dac_scale` in 16-bit units so the calibration code stays.
- `Leds`/`Switches`: shift 16 bits into the 595s and latch; load the 165 and
  read 8 bits, every millisecond.
- Audio callback at 48 kHz, block size 8, as Marbles (`kBlockSize`).
- Settings and scales in QSPI.

The Marbles firmware is © Emilie Gillet, MIT licence.

---

## Open items

- Verify the KS01-B switch's internal pin pairing before soldering (same
  note as in the Plaitsy audit).
- Verify the LM4040 TO-92 pinout for the exact part you buy; the footprint
  leaves pad 3 open.
- Route the two PCBs: import `Marbles.epro2`, run DRC and the netlist check
  on each placed PCB, then route (GND / GND_F pours on the bottom layers as
  on Plaitsy; keep copper off the jack barrels, 3 mm around the point
  0.78 mm below each jack origin on the panel side).
