# Plaitsy — design and build notes

This document covers the circuit, the Seed pin map, the board-to-board
interconnect, how to build both boards and the panel, and the BOM. Every
reference designator matches `hardware/tools/circuit.py` and the editor
projects in `hardware/stripboard/`.

Coordinates are given as (row, column), counted from 0, exactly as the axis
labels in the PNG previews show them. On the faceplate board, row 0 is at the
top and column 0 is at the left, seen from the front.

---

## Architecture

```
 panel ─┬─ faceplate board (FB)     jacks, pots, LEDs, buttons, 74HC4051 pot mux,
        │   component side → panel   normalization-probe resistors, R1
        │   copper side ↓
        │      36 male pins  ⇅  36 female sockets      copper side to copper side
        │   copper side ↑
        └─ main board (MB)          2× TL074 CV input stages, bias, LED resistors,
            component side →        Daisy Seed on the seed_power_opamps breakout
            (rear of the case)      (Eurorack power and audio out via the breakout)
```

Both boards are 23 columns × 41 rows. A hole at FB (r, c) sits directly over
MB (r, 22 − c), because the main board faces the other way.

**Why a mux:** Plaits needs 8 CV inputs and 7 pots, but the Seed has only
12 ADC pins. A 74HC4051 on the faceplate reads the 7 pots through a single
ADC pin. This also uses up all 31 of the Seed's GPIOs.

---

## Seed pin map

The breakout lands on the main board in two socket strips. The left strip is
in column 1 and holds Seed pins 1–20. The right strip is in column 7 and
holds Seed pins 40–21. The USB/audio end is at row 0. The libDaisy names are
shown in brackets with the Seed pin number.

| MB row | Left strip (col 1) | Use | Right strip (col 7) | Use |
|---|---|---|---|---|
| 0 | J5 AIN1 | **leave contact out** | J4 AOUT1 | **OUT** jack |
| 1 | GND | GND | GND | GND |
| 2 | J5 AIN2 | **leave contact out** | J4 AOUT2 | **AUX** jack |
| 3 | GND | GND | GND | GND |
| 4 | D0 [1] | LED1 green | DGND [40] | GND |
| 5 | D1 [2] | LED1 red | VIN [39] | **leave contact out** |
| 6 | D2 [3] | LED2 green | 3V3D [38] | **leave contact out** |
| 7 | D3 [4] | LED2 red | D30 [37] | left button (BTN_A) |
| 8 | D4 [5] | LED3 green | D29 [36] | right button (BTN_B) |
| 9 | D5 [6] | LED3 red | D28 / A11 [35] | mux S2 |
| 10 | D6 [7] | LED4 green | D27 [34] | mux S1 |
| 11 | D7 [8] | LED4 red | D26 [33] | mux S0 |
| 12 | D8 [9] | LED5 green | D25 / A10 [32] | ADC: MODEL CV |
| 13 | D9 [10] | LED5 red | D24 / A9 [31] | ADC: HARMONICS CV |
| 14 | D10 [11] | LED6 green | D23 / A8 [30] | ADC: pot mux output |
| 15 | D11 [12] | LED6 red | D22 / A7 [29] | ADC: TIMBRE CV |
| 16 | D12 [13] | LED7 green | D21 / A6 [28] | ADC: MORPH CV |
| 17 | D13 [14] | LED7 red | D20 / A5 [27] | ADC: FM CV |
| 18 | D14 [15] | LED8 green | D19 / A4 [26] | ADC: LEVEL CV |
| 19 | Seed pin 16 | **leave contact out** | D18 / A3 [25] | LED8 red (via R1 on the FB) |
| 20 | Seed pin 17 | **leave contact out** | D17 / A2 [24] | ADC: TRIG CV |
| 21 | Seed pin 18 | **leave contact out** | D16 / A1 [23] | ADC: V/OCT CV |
| 22 | Seed pin 19 | **leave contact out** | D15 / A0 [22] | normalization probe out |
| 23 | AGND [20] | GND | 3V3A [21] | 3V3A (pots, mux, bias) |
| 24 | — | — | — | — |
| 25 | GND | GND | GND | GND |
| 26 | −12V | op-amps | +12V | op-amps |
| 27–28 | ±12V | **leave contacts out** | ±12V | **leave contacts out** |

**Leave contacts out:** the copper strip under each "leave out" position
carries another signal. With the contact in place, row 19 would, for example,
short a Seed audio pin to the LED8 line. Pull those contacts out of the
socket strip, or cut their tails off flush, so nothing reaches the copper.

The buttons use the Seed's internal pull-ups and close to GND. D29/D30 are
the external-USB pins, which this design does not use.

---

## CV inputs (main board)

Each CV input goes through an inverting TL074 stage that is biased from 3V3A,
so no −10 V reference is needed. The output feeds the Seed's ADC through a
1 kΩ series resistor.

```
jack tip ── Rin 100k ──┬── (−) TL074 ──┬── Rs 1k ── Seed ADC
                       ├── Rf ─────────┤
                       └── Cf ─────────┘
bias ───────────────────── (+)
```

| Input | Op-amp | Rin | Rf | Cf | Rs | Bias | ADC pin |
|---|---|---|---|---|---|---|---|
| MODEL | U3A | R21 | R22 13k | C21 1n | R23 | A | A10 |
| TIMBRE | U3B | R24 | R25 13k | C22 1n | R26 | A | A7 |
| FM | U3C | R27 | R28 13k | C23 1n | R29 | A | A5 |
| MORPH | U3D | R30 | R31 13k | C24 1n | R32 | A | A6 |
| HARMONICS | U4A | R33 | R34 13k | C25 1n | R35 | A | A9 |
| TRIG | U4B | R36 | R37 13k | C26 100p | R38 | A | A2 |
| LEVEL | U4C | R39 | R40 13k | C27 1n | R41 | A | A4 |
| V/OCT | U4D | R42 | R43 33k | C28 1n | R44 | V | A1 |

- **Bias A** comes from R45 15k and R46 12k off 3V3A, decoupled by C29 1µ:
  1.467 V. **Bias V** comes from R47 13k and R48 15k, with C30 1µ: 1.768 V.
- **Wide channels** (gain −0.13): V_adc = 1.657 V − 0.13 · V_in. ±12 V maps
  to 3.217 V…0.097 V, so even a rail-to-rail signal stays inside the ADC range
  and needs no clamp diodes.
- **V/OCT** (gain −0.33): V_adc = 2.351 V − 0.33 · V_in. The usable range is
  −2.9 V…+7.1 V. That gives 0.2 Plaits-units per volt, the same pitch scaling
  as Plaits itself. D21 and D22 (BAT85) clamp the ADC pin to 3V3A and GND for
  voltages outside that range.
- C31–C34 (100n) decouple ±12 V at each TL074.

**Firmware mapping (planned):** the firmware converts each reading back to
the jack voltage, V_in = (V0 − V_adc) / g. It then converts that voltage into
the number Plaits' own ADC would have read and clips it to Plaits' range.
After that step, Plaits' code and calibration constants apply unchanged. V0
and g are 1.657 / 0.13 for the wide channels and 2.351 / 0.33 for V/OCT.
Calibration trims both values against measured readings, and the V/OCT
calibration works the same way as on Plaits.

---

## Pots and the mux (faceplate)

All seven pots are B10k between GND and 3V3A. Their wipers go into U1, a
74HC4051 powered from 3V3A and decoupled by C8. The 74HC4051 is a
multiplexer: the Seed selects one wiper at a time with the S0–S2 lines and
reads it on A8. In libDaisy, set this up with `AdcChannelConfig::InitMux(A8,
8, D26, D27, D28)`.

| Mux channel | 4051 pin | Pot |
|---|---|---|
| 0 | 13 | RV2 HARMONICS |
| 1 | 14 | RV3 TIMBRE |
| 2 | 15 | RV4 MORPH |
| 3 | 12 | RV1 FREQUENCY |
| 4 | 1 | RV6 FM attenuverter |
| 5 | 5 | RV5 TIMBRE attenuverter |
| 6 | 2 | RV7 MORPH attenuverter |
| 7 | 4 | tied to GND (0 V reference) |

The attenuverters read 0…1, and the firmware maps that to −1…+1, the same as
Plaits.

---

## LEDs and buttons

There are eight 3 mm red/green bicolour LEDs with a common cathode (the
middle lead) to GND. Each anode is driven from a Seed GPIO through 470 Ω,
which gives roughly 2.5–3 mA per colour. Yellow means both colours on, which
is how Plaits shows yellow too.

- LED1 green … LED8 green and LED1 red … LED7 red go through R60–R74. These
  resistors sit on the main board, under the breakout.
- LED8 red goes through R1 on the faceplate. Its GPIO (A3) is on the other
  side of the breakout.
- If yellow looks orange or lime, lower the green resistors to about 330 Ω,
  or adjust the balance in firmware PWM.

SW1 (left) and SW2 (right) are 6×6 mm tactile switches. Pick a type with an
actuator long enough to reach through the panel.

---

## Normalization probe

Plaits detects whether a cable is plugged into FM, TIMBRE, MORPH, TRIG and
LEVEL. It does this by sending a known pattern into each jack's switch lug
and checking whether that pattern reaches the ADC.

Plaitsy works the same way. The probe output (A0) feeds R9–R13 (10k each),
which go to the switch lugs of TIMBRE, FM, MORPH, TRIG and LEVEL. With no
cable plugged in, the lug touches the tip, so the pattern reaches the op-amp.
It shows up at the ADC as about 0.39 V peak-to-peak. A plugged cable breaks
that path. The detection thresholds will be set in firmware from the measured
swing.

MODEL, HARMONICS and V/OCT have their switch lugs tied to GND, so they read
0 V when nothing is plugged in. OUT and AUX have their lugs left unconnected.

---

## Board-to-board pins

There are 36 pins. Each faceplate pin is a male pin that sticks out of the
FB copper side. It mates with a female socket on the MB copper side at (row,
22 − col).

| FB hole | MB hole | Signal |
|---|---|---|
| (4..18, 16) | (4..18, 6) | LED lines, D0…D14 order (LED1 G, LED1 R, … LED8 G) |
| (19, 16) | (19, 6) | LED8 red (to A3) |
| (4, 5) | (4, 17) | GND |
| (7, 7) | (7, 15) | BTN_A |
| (8, 9) | (8, 13) | BTN_B |
| (9, 3) / (10, 3) / (11, 3) | (9..11, 19) | mux S2 / S1 / S0 |
| (14, 8) | (14, 14) | mux output |
| (22, 9) | (22, 13) | probe |
| (23, 9) | (23, 13) | 3V3A |
| (25, 6) | (25, 16) | GND |
| (34, 0) / (34, 8) / (34, 13) / (34, 18) / (34, 22) | (34, 22) / (34, 14) / (34, 9) / (34, 4) / (34, 0) | CV: MODEL / TIMBRE / FM / MORPH / HARMONICS |
| (40, 0) / (40, 8) / (40, 13) | (40, 22) / (40, 14) / (40, 9) | CV: TRIG / LEVEL / V/OCT |
| (40, 18) / (40, 22) | (40, 4) / (40, 0) | OUT / AUX |

The same table, machine-readable, is in
`hardware/stripboard/faceplate-interconnect.json`.

**Mounting the headers.** Both boards are single-sided, so every joint has to
be soldered on the copper side, and once the boards are mated their copper
sides face each other. Solder each half on its own board before mating. The
holes position the pins, so no jig is needed.

- **Faceplate:** use male header pins. Push the short end into the hole from
  the copper side, slide the plastic carrier up the pins to clear room for
  the iron, solder, then slide the carrier back down. The long ends point to
  the main board.
- **Main board:** use long-tail ("stackable") female headers. Push the tails
  in from the copper side, raise the body about 2 mm on a spacer, and solder
  in the gap under the body. Trim the tails flush on the component side.
  Cutting a female header costs one contact per cut, so buy extra.
- Runs: FB column 16, rows 4–19 is one 16-pin strip. Column 3, rows 9–11 is
  3 pins, and column 9, rows 22–23 is 2 pins. The other 15 pins are singles.

---

## Building the boards from 24 × 56 stripboard

Each board is 41 strips long, but your boards have 24 strips. So each board is
made from two pieces, with the strips running across the module:

| Board | Upper piece | Lower piece |
|---|---|---|
| Faceplate | rows 0–21 (22 strips) | rows 22–40 (19 strips) |
| Main board | rows 0–23 (24 strips) | rows 24–40 (17 strips) |

All four pieces are 23 holes wide, so two 24 × 56 boards are enough. Cut
each board into two 23-hole pieces across the strips.

- **Keep the 2.54 mm pitch across the joint.** The panel holes and the 36
  board-to-board pins assume one continuous grid. Cut along the gap between
  two strips, not along a row of holes. Score deeply on both sides, snap, and
  sand the edge flat. Before soldering anything across the joint, check it by
  pushing a header strip through both pieces. The main board's upper piece
  uses all 24 strips, so its joint edge is the factory edge. Sand that edge
  too if the header test fails.
- On the faceplate, no part sits across the joint. Ten link wires cross it,
  and those, together with the panel, hold the two pieces together.
- On the main board, the breakout bridges the joint, which helps hold it.
  Use a 24-contact socket strip per side for rows 0–23, and a 4-contact strip
  per side for rows 25–28 with the contacts at rows 27–28 removed.

### Faceplate board

Open `plaitsy-faceplate-board.json`. Cut and solder from
`plaitsy-faceplate-board-copper.png`, which is mirrored so it matches the
board when you turn it over. The board has 63 cuts (54 drilled, 9 knife cuts
between holes), 50 links and 71 parts.

- Mount every jack, pot, LED and button in the panel first. Then lower the
  board over their legs and solder. This sets all their heights correctly.
- Eight links are long or diagonal. Use insulated wire for these, routed
  around the parts. You can also re-route them in the editor if you prefer:

| From | To | Net | |
|---|---|---|---|
| (18, 17) | (15, 3) | MORPH pot wiper | diagonal |
| (7, 0) | (16, 1) | 3V3A | diagonal |
| (17, 17) | (5, 22) | 3V3A | diagonal |
| (4, 8) | (3, 11) | GND | diagonal |
| (19, 17) | (7, 22) | GND | diagonal |
| (21, 9) | (12, 9) | TIMBRE att. wiper | long |
| (24, 8) | (15, 8) | MORPH att. wiper | long |
| (2, 0) | (13, 0) | HARMONICS wiper | long |

### Main board: finishing it in the editor

`plaitsy-main-board-starter.json` has the breakout (U2), the 36 sockets
(S<row>_<col>) and the 15 LED resistors placed and locked. The board size,
23 × 41, is locked too. Those positions are fixed by the faceplate, so don't
move them.

1. **Import** the starter, then run **Auto-layout** to place the remaining
   46 parts. Those are U3 and U4, the 24 channel resistors, 8 filter caps, 2
   clamp diodes, the bias dividers and the decoupling caps.
2. Check that no part has legs on both sides of the line between rows 23 and
   24. That is the joint between the two pieces; link wires may cross it. If
   a part does, drag it and complete again.
3. OUT (row 0) has to reach socket S40_4, and AUX (row 2) socket S40_0. These
   are about 100 mm long; use insulated wire along the board edge.
4. The editor should report no conflicts and no incomplete nets. Then build
   it the same way as the faceplate board. Leave out the socket contacts
   marked in the pin map.

The op-amps should end up near the ADC strips on rows 12–21. The breakout is
at the left edge so those strips run out into the free area.

---

## Panel

The panel is a 12HP aluminium blank, 60.6 × 128.5 mm. The files are in
`hardware/panel/`:

- `plaitsy-panel-drill.svg` is a 1:1 drill template. Print it at 100 % and
  check the 50 mm scale bar with a ruler. Tape it on, centre-punch the
  crosses, drill a 2 mm pilot hole, then step up to the size shown.
- `plaitsy-panel-artwork.svg` is a guide for drawing the labels by hand
  after spray painting. Green model names go left of the LEDs, red names to
  the right. For the yellow bank, see the Plaits manual.
- `plaitsy-panel-holes.csv` lists every hole as x/y in mm from the top-left
  corner, with its diameter.

| Hole | Ø mm |
|---|---|
| Pots (Alpha 9 mm, M7 bushing) | 7.5 |
| Jacks (Thonkiconn) | 6.5 |
| LEDs (3 mm) | 3.2 |
| Buttons | 5.2 |
| Mounting (×4) | 3.2 |

The hole positions are computed from the faceplate placement, so they match
the board as long as the board's pitch is kept, including across the joint.

---

## BOM

| Qty | Part | Value / note | Refs |
|---|---|---|---|
| 1 | Daisy Seed | | U2 |
| 1 | seed_power_opamps breakout (Rob Heel), built | power and audio-out stage | U2 |
| 2 | TL074 + DIP-14 socket | | U3, U4 |
| 1 | 74HC4051 + DIP-16 socket | CD4051B also works | U1 |
| 8 | 3 mm bicolour LED, red/green, common cathode, 3 lead | | D1–D8 |
| 2 | BAT85 | | D21, D22 |
| 16 | Resistor 470 Ω | | R1, R60–R74 |
| 8 | Resistor 1k | | R23, R26, R29, R32, R35, R38, R41, R44 |
| 5 | Resistor 10k | | R9–R13 |
| 1 | Resistor 12k | | R46 |
| 8 | Resistor 13k | 1 % | R22, R25, R28, R31, R34, R37, R40, R47 |
| 2 | Resistor 15k | | R45, R48 |
| 1 | Resistor 33k | 1 % | R43 |
| 8 | Resistor 100k | 1 % | R21, R24, R27, R30, R33, R36, R39, R42 |
| 1 | Capacitor 100p | | C26 |
| 7 | Capacitor 1n | | C21–C25, C27, C28 |
| 5 | Capacitor 100n | | C8, C31–C34 |
| 2 | Capacitor 1µ | | C29, C30 |
| 7 | Pot B10k, Alpha 9 mm vertical | | RV1–RV7 |
| 7 | Knobs | 2 large, 2 medium, 3 small | |
| 10 | Thonkiconn PJ398SM | | J1–J10 |
| 2 | Tactile switch 6×6 mm, long actuator | | SW1, SW2 |
| 36 | Male header pins | one 40-pin strip | FB |
| ~60 | Long-tail female header contacts | 36 used, plus cutting losses | MB |
| 2+2 | Female socket strips for the breakout | 24-pin and 4-pin | MB |
| 2 | Stripboard 24 × 56 | | |
| 1 | 12HP aluminium panel blank, 4× M3 screws | | |
| | Solid-core wire for links, insulated wire for the long ones | | |

---

## Firmware (not started)

The plan is to port the Plaits 1.2 source to the Seed with libDaisy, keeping
all 24 engines. The details:

- Audio runs at 48 kHz with a block size of 12, as on Plaits.
- The CV and pot handling follows the mapping above, with the mux on A8.
- `ui.cc` is ported for the buttons, LEDs and settings, so the panel behaves
  exactly as the manual describes.
- Settings and calibration are stored in QSPI flash.

The Plaits firmware is © Emilie Gillet, MIT licence.

## Differences from Plaits

- CV inputs accept the full ±12 V without clipping in hardware. The firmware
  clips to Plaits' ranges, so the response is the same.
- Audio comes from the Seed's codec through the breakout's output stage. The
  output level is set by the breakout.
- All seven pots are 9 mm Alpha pots read through a mux. The panel layout
  and functions are the same, but the knob sizes differ.
