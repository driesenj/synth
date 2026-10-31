# Tempo — design notes

A clock and LFO module for the Eurorack voice case, 12HP, on a Daisy Seed.
It works like ALM's Pamela's PRO Workout but runs its own firmware (ALM's
is closed): eight outputs, each either a clock or a clock-synced wave. It
replaces the Kosmo case's Arduino clock (`analog-clock/`) and the planned
separate LFO module. It also adds the reset line the rig never had (RIG.md,
"Clock and sync").

The hardware reuses Side FXy's parts and Marblesy's circuits:

- **From Side FXy:** the 1.9" ST7789 screen, the EC11 encoders, the
  shift-register chain and the Seed on Rob Heel's `seed_power_opamps`
  breakout.
- **From Marblesy:** the MCP4922 DACs with their output stage, the CV
  inputs and the gate outputs.

Every reference designator matches `hardware/tools/circuit.py`. Run
`python circuit.py` to print the part counts, the netlist checks and the
circuit values.

**Status (2026-10-31):**

- **Panel:** approved as drawn.
- **Main board:** SMD (your choice).
- **Netlist:** written. It passes its checks (0 netlist problems, 0 circuit
  problems; see [Checks](#checks)).
- **Not yet:** the EasyEDA schematic, PCB placement and firmware.

"Tempo" is still a working title.

---

## What it does

| Function | Here |
|---|---|
| Tempo | Internal, 20–300 BPM, with tap tempo; or it follows CLOCK in (4 PPQN, the rig's 16ths, by default) |
| Transport | RUN button. RESET in. RUN out (high while running). RESET out (a pulse at every start and every reset) |
| Outputs | 8, each a **clock** or a **wave** |
| Clock outputs | ×/÷ ratio, swing, euclidean, probability, gate width, phase, level |
| Wave outputs | sine, triangle, saw, ramp, square, pump, S&H, smooth random, each with tempo ratio, level, offset, phase and shape |
| CV inputs | CV 1–3, each assignable to any output parameter with an amount |
| UI | 320 × 170 screen, three soft encoders named by the screen, RUN, TAP and SHIFT buttons, an LED for each output |

---

## Panel

![panel](../hardware/panel/tempo-panel-preview.png)

| Control | Part | Notes |
|---|---|---|
| Screen | Waveshare 1.9inch LCD Module (ST7789V2, IPS 170 × 320, SPI), as in Side FXy | Landscape here. Window 43.7 × 23.7 mm, the active area plus 0.5 mm all round |
| ENC1–ENC3, three soft knobs | EC11 encoder with push, M7 bushing, D shaft (Tayda / Mouser) | Unlabelled: the screen names each knob in the cell just above it. Short dotted guides join the screen to the knobs |
| SW1 RUN, SW2 TAP, SW3 SHIFT | Thonk low-profile LED button: green, white, red | RUN is lit while running, TAP flashes on the beat, SHIFT is red as on Side FXy |
| J1 CLOCK, J2 RESET, J3–J5 CV 1–3 | Thonkiconn | The input row |
| J6 RUN, J11 RESET, J7–J10 and J12–J15 outputs 1–8 | Thonkiconn | On the gold output band. Transport outputs in the left column, outputs 1–8 in a 4 × 2 block |
| D1–D8 output LEDs | 3 mm, red | Left of each output's number, where Marblesy has them. Brightness follows the output |

**Layout:**

- **Grid:** the jack grid is Plaitsy's, five columns 11.5 mm apart, with
  the rows 14.6 mm apart. The lowest row is at Side FXy's height, so the
  jack rows of the case line up.
- **Controls:** the encoders and buttons stand on the midpoints between
  jack columns 1–2 and 4–5 and on the centre column.
- **Frame:** title, subtitle, band, rule and maker are at the house spots.
- `python panel.py` reports no gap under 1 mm between knobs, nuts, rings,
  LEDs, the window and the edges.

**What the layout leaves for the boards (front view, board mm):**

- **Behind the screen (y 78.4–105.7):** the module sits in the panel gap
  with its glass on the panel. No part with leads may sit there on the
  faceplate, but SMD parts on the rear may.
- **The encoder bodies (y 63.5–75.1):** the encoders' mounting tabs end
  about 2 mm below the module.
- **The buttons at y 57:** they leave a strip for rear parts above the top
  jack row's sleeve lugs (y 44.2–52.6).
- **The LEDs:** they sit between the jack rows. They clear the jack bodies
  by 0.1–0.2 mm, the same fit as Marblesy's, which is built and routed.

---

## Architecture

```
 panel ─┬─ display module in the panel gap, glass to the window
        ├─ faceplate board (FB) 59.4 x 108, 64 parts
        │     front: 15 Thonkiconn, 3 EC11, 3 LED buttons, 8 LEDs
        │     rear (SMD): 74HC165 (switches), 2x 74HC595 (LEDs), 12 pull-ups, 11 LED resistors;
        │                 CN1 (right-angle, through-hole) for the display cable
        │      36 pins in 4 headers (male on the FB, female on the MB)
        └─ main board (MB) 59.4 x 108, 93 parts, SMD
              Daisy Seed on seed_power_opamps (through-hole sockets), 4x MCP4922 + LM4040,
              4x TL074 (8 output stages, -2.5 V reference, 3 CV inputs, RUN/RESET gate outputs),
              CLOCK and RESET input transistors
```

**Why two boards:** the user prefers one board where possible, but it
doesn't work here, for the same reasons as on Side FXy:

- The breakout is 96.7 mm long, so it can only stand vertically. Its socket
  leads would then come through behind the screen.
- 15 jacks, three encoders and three buttons fill the faceplate's front.

**Why SMD:** a through-hole main board would carry about 1.7 times
Marblesy's part density. In SMD (SOIC, SOT-23, SOD-123, 0603, 1206 for the
bulk caps) it takes about a third of the area, the way Senay solved the
same problem.

**The faceplate's rear goes SMD too, as on Senay:**

- **The rear can hold all the LED logic.** SMD parts have no leads through
  the board, so they may sit behind the screen. The two 74HC595s and their
  eleven resistors therefore move from the main board to the faceplate,
  next to the LEDs.
- **That shortens the headers.** It takes eleven LED lines off them for one
  data line (SR_DOUT).

---

## Daisy Seed pin map

| Seed pin | libDaisy (STM32) | Net | Use |
|---|---|---|---|
| 1 | D0 (PB12) | CLK | clock input after Q1, active low; EXTI12, timestamped |
| 2 | D1 (PC11) | DAC_CS4 | U5 chip select |
| 3 | D2 (PC10, SPI3 SCK) | DAC_SCK | the four DACs |
| 4, 5, 6 | D3 (PC9), D4 (PC8), D5 (PD2) | DAC_CS1..3 | U2–U4 chip selects |
| 7 | D6 (PC12, SPI3 MOSI) | DAC_MOSI | the four DACs |
| 8, 9, 11 | D7, D8, D10 (SPI1 NSS, SCK, MOSI) | LCD_CS, LCD_SCK, LCD_MOSI | display, **Side FXy's pins** |
| 12, 13, 14 | D11, D12 (TIM4_CH4), D13 | LCD_DC, LCD_BL, LCD_RST | display, **Side FXy's pins** |
| 10 | D9 (PB4) | RST | reset input after Q2, active low; EXTI4 |
| 15 | D14 (PB7) | DAC_LDAC | all four DACs: pulse after the eight writes, so the outputs change together |
| 16–19 | codec | — | unused (no audio) |
| 20, 40 | AGND, DGND | GND | |
| 21 | 3V3A | 3V3A | DACs, reference, CV bias |
| 22, 23, 24 | A0, A1, A2 | ADC_CV1..3 | CV inputs |
| 25, 26 | D18 (PA7), D19 (PA6) | GATE_RUN, GATE_RST | to the RUN and RESET out stages |
| 27–32 | D20–D25 | ENC1_A, ENC1_B, ENC2_A, ENC2_B, ENC3_A, ENC3_B | encoder phases (pulled up on the faceplate), polled at 4 kHz |
| 33, 34 | D26, D27 | SR_CLK, SR_LOAD | the chain: 165 /PL and 595 RCLK, **Side FXy's pins** |
| 36, 37 | D29, D30 | SR_DOUT, SR_DIN | to the 595s, from the 165, **Side FXy's pins** |
| 38 | 3V3D | 3V3D | the faceplate's logic, LEDs and display |
| 35, 39 | D28 (A11), VIN | — | free |

The breakout's J1 (GND, −12 V ×3) and J3 (GND, +12 V ×3) feed the
op-amps. The ground pins of J4 and J5 are tied to GND, as on Marblesy; the
audio pins stay open.

**Pin notes:**

- **The display and the chain:** they are on Side FXy's pins, so one driver
  and one configuration serve both modules.
- **The DACs:** they get SPI3 on D2/D6, which are SDMMC pins that are free
  on both modules. The DAC traffic therefore never waits for a display DMA
  transfer on SPI1. Check PC10/PC12 against libDaisy's SPI3 pin table before
  the schematic.
- **D9:** the display never reads, so D9 (SPI1 MISO) carries the reset
  input. CLK on PB12 and RST on PB4 use different EXTI lines.

---

## Main board circuits

### Outputs (8×): MCP4922 + Marblesy's output stage

Four MCP4922-E/SL (12-bit dual, SOIC-14, the DIP's pinout) run on 3V3A,
with VREFA and VREFB from VREF. Each output is Marblesy's inverting summer:

```
V_out = −(100k/24k)·V_dac − (100k/47k)·NREF = 5.32 V − 4.17·V_dac
```

- **Range:** code 0 gives +5.32 V and code 4095 gives −5.09 V, in steps of
  2.54 mV.
- **Output:** 1k series resistor.
- **Clocks:** a clock is two DAC codes; +5 V is the default high.
- **Calibration:** each output gets an offset and scale from the firmware.

| Output | DAC | Op-amp | Rdac 24k | Rref 47k | Rf 100k | Rs 1k |
|---|---|---|---|---|---|---|
| 1 | U2 A | U6A | R30 | R31 | R32 | R33 |
| 2 | U2 B | U6B | R34 | R35 | R36 | R37 |
| 3 | U3 A | U6C | R38 | R39 | R40 | R41 |
| 4 | U3 B | U6D | R42 | R43 | R44 | R45 |
| 5 | U4 A | U7A | R46 | R47 | R48 | R49 |
| 6 | U4 B | U7B | R50 | R51 | R52 | R53 |
| 7 | U5 A | U7C | R54 | R55 | R56 | R57 |
| 8 | U5 B | U7D | R58 | R59 | R60 | R61 |

Per DAC:

- VDD and /SHDN go to 3V3A, both VREF pins to VREF, VSS to GND.
- /CS goes to its own Seed pin; SCK and SDI are on SPI3; /LDAC is shared.
- Pins 2, 6 and 7 are not connected.
- 100 n at VDD (C23–C26).

### Reference

| Part | What |
|---|---|
| D11 | LM4040-2.5 in SOT-23: 1 = cathode (VREF), 2 = anode, 3 = substrate, tied to the anode as TI asks |
| R73 | 1k5 feed from 3V3A |
| C14 | 100 n |
| U8D, R71, R72 | inverter, 100k / 100k: NREF = −2.50 V |

Changed from Marblesy (2.2k feed, 10k inverter): four DACs load VREF twice
as much as two. With the new values:

- 0.53 mA comes in through R73.
- The eight DAC reference inputs (about 165k each) and the inverter take
  0.15 mA.
- That leaves 0.39 mA in the LM4040, well above its 45 µA minimum.

### CV inputs (3×)

Marblesy's stage, unchanged:

```
jack tip ── 100k ──┬── (−) TL074 ──┬── 1k ── Seed ADC
                   ├── 27k ────────┤
                   └── 1n ─────────┘
BIAS 1.32 V ──────── (+)
```

- **Range:** +5 V reads 0.33 V and −5 V reads 3.03 V.
- **BIAS:** R74 15k / R75 10k from 3V3A, with C13 1 µ.
- **Unplugged:** the switch lug grounds the tip, so the input reads 0 V.

| Input | Section | Rin | Rf | Cf | Rs | ADC |
|---|---|---|---|---|---|---|
| CV 1 | U8A | R62 | R63 | C10 | R64 | A0 |
| CV 2 | U8B | R65 | R66 | C11 | R67 | A1 |
| CV 3 | U8C | R68 | R69 | C12 | R70 | A2 |

### CLOCK and RESET inputs (2×)

Side FXy's clock stage, twice, in SMD:

```
jack tip ── 100k ── base MMBT3904, emitter to GND
            1N5819HW cathode on the base, anode to GND
            collector ── 10k to 3V3D, and to the Seed
```

| Input | 100k | 10k | Transistor | Clamp | Seed |
|---|---|---|---|---|---|
| CLOCK | R76 | R77 | Q1 | D9 | D0 |
| RESET | R78 | R79 | Q2 | D10 | D9 |

- **Threshold:** about 0.7 V.
- **Drive:** a 5 V clock gives 43 µA of base current against 0.33 mA of
  collector current, so the transistor needs a gain above 8.
- **Unplugged:** the switch lug grounds the tip. The firmware follows CLOCK
  whenever pulses arrive.

### RUN and RESET outputs (2×)

Marblesy's gate stage: a TL074 section, non-inverting ×2.5, then 1k out,
giving 0 V / 8.25 V. U9A (RUN: R80 10k to GND, R81 15k feedback, R82 1k)
and U9B (RESET: R83, R84, R85), driven from D18 and D19. U9C and U9D are
grounded followers.

### Power

| Rail | Load | Estimate |
|---|---|---|
| ±12 V | the four TL074s | about 22 mA per rail |
| +12 V | the Seed, through the breakout's DC/DC | about 60 mA more, so about 85 mA in all |
| −12 V | the TL074s only | about 25 mA |
| 3V3D | the display (40 mA max), the LEDs (up to about 35 mA), logic | about 80 mA on top of the Seed |
| 3V3A | the DACs, reference and bias | 2.1 mA |

- **Decoupling:** 100 n per rail beside each TL074 (C15–C22) and 10 µ bulk
  on each rail by the breakout's J1 / J3 (C27, C28, 1206).
- **Measure on the first build:** the 3V3D current. Side FXy has the same
  open point.

---

## Faceplate circuits

### Jacks

| Jack | Tip | Switch lug |
|---|---|---|
| J1 CLOCK, J2 RESET | CLK_IN_F, RST_IN_F | GND_F |
| J3–J5 CV 1–3 | CV1_F..CV3_F | GND_F |
| J6 RUN, J11 RESET (outputs) | RUN_OUT_F, RST_OUT_F | open |
| J7–J10, J12–J15 outputs 1–8 | OUT1_F..OUT8_F | open |

### Encoders and buttons

- **Encoder phases:** pulled up by R1–R6 (10k to 3V3D_F), straight through
  H3 to D20–D25. The firmware decodes them in the 4 kHz tick.
- **Encoder pins:** common C, switch S1 and both mounting tabs go to
  GND_D_F.
- **Switches:** the encoder pushes and the RUN, TAP and SHIFT buttons go
  into U10 (74HC165D) on D0–D5, each pulled up by R7–R12 (10k). D6 and D7
  are tied high and read as released. DS and /CE are grounded, and Q7 is
  SR_DIN.

| U10 input | D0 | D1 | D2 | D3 | D4 | D5 | D6, D7 |
|---|---|---|---|---|---|---|---|
| Switch | K1 push | K2 push | K3 push | RUN | TAP | SHIFT | spare (high) |

### LEDs

- **U11 (74HC595D):** first in the chain, SER = SR_DOUT. QA–QH drive the
  output LEDs D1–D8 through R13–R20 (470R, 2.7 mA into red). Its QH' feeds
  U12.
- **U12:** QA–QC drive the RUN, TAP and SHIFT button LEDs through R21–R23;
  QD–QH are spare.
- **Cathodes:** all to GND_D_F.
- **Resistor values:** RUN and TAP get 150R, SHIFT 470R. A white LED, and a
  green one if Thonk's is InGaN, drops close to 3 V, so a 470R at 3.3 V
  would give it under 1 mA. With 150R that is 2.5 mA (white) to 6 mA (an
  old-style green). Measure the buttons when they arrive; the brightness is
  balanced in software anyway.

### The chain

Side FXy's order, with SR_LOAD on the 165's /PL and both 595s' RCLK, and
SR_CLK on all three:

1. SR_LOAD goes low and the 165 loads.
2. SR_LOAD goes high and the 595s latch the previous scan's bytes.
3. 16 clocks read the 165's byte (the first 8) and shift two LED bytes
   out. The first byte shifted ends in U12, the second in U11.

The scan runs in the 4 kHz tick. Brightness comes from binary-code
modulation over the scans.

### Display

The same module and cable as Side FXy: the Waveshare MX1.25 cable plugs
onto CN1, a right-angle 1×8 header, in Waveshare's order (VCC, GND, DIN,
CLK, CS, DC, RST, BL). C4 (10 µ, 1206) sits beside it.

- **Orientation:** landscape. With the flex end on the left, the module
  covers board x 2.1–53.3, y 78.4–105.7 (front view).
- **The cable:** its connector sits 34.3–38.5 mm from the flex end, centred
  in height. The cable goes through a cutout in the faceplate to CN1, which
  stands in the 6 mm right margin beside the module.
- **Mounting:** tape round the window. The M2 holes are under the glass, as
  on Side FXy.

Decoupling: C1–C3 (100 n) at U10–U12.

The faceplate keeps two grounds, as Side FXy does: GND_F (jacks) and
GND_D_F (logic, LEDs, display). They join only on the main board.

---

## Board-to-board headers

From `circuit.HEADERS`: male pins on the faceplate (HF1–HF4), sockets on
the main board (H1–H4). The pin order is a first guess; placement sorts it
for the fewest crossings.

| Header | Pins | Nets (MB name; the faceplate adds _F) |
|---|---|---|
| H1 / HF1 | 6 | CLK_IN, RST_IN, GND, CV1, CV2, CV3 |
| H2 / HF2 | 11 | RUN_OUT, OUT1, OUT2, OUT3, OUT4, GND, RST_OUT, OUT5, OUT6, OUT7, OUT8 |
| H3 / HF3 | 12 | 3V3D, GND (GND_D_F), SR_CLK, SR_LOAD, SR_DIN, SR_DOUT, ENC1_A, ENC1_B, ENC2_A, ENC2_B, ENC3_A, ENC3_B |
| H4 / HF4 | 7 | LCD_SCK, LCD_MOSI, GND (GND_D_F), LCD_CS, LCD_DC, LCD_RST, LCD_BL |

---

## Checks

`python circuit.py` runs two sets of checks.

**`check()`, the netlist:**

- no single-pin nets;
- no designator used twice on a board;
- every header pin used on both boards;
- no net name on both boards;
- every faceplate net ends in _F;
- every panel part has a PLACEMENT entry, and the reverse.

**`circuit_check()`, the numbers:**

- **How it works:** it looks up the resistors by the nets they join. A
  resistor on the wrong net makes the lookup fail, so the numbers below
  come from the netlist as wired.
- **What it reports:** the reference (NREF, the LM4040's current), every
  output's range and step, the CV inputs' ADC range, the gate height, the
  transistor inputs' drive, the LED currents and the 3V3A load.

Both report 0 problems. Tested both ways: moving R31 to VREF and dropping
the Seed's SR_DIN pin each get caught.

---

## BOM

**Main board** (SMD unless noted):

| Qty | Part | Package / notes | Refs |
|---|---|---|---|
| 1 | Daisy Seed (Thonk) | | U1 |
| 1 | seed_power_opamps breakout (Rob Heel), built; its audio op-amps unused | on its sockets, through-hole | U1 |
| 4 | MCP4922-E/SL | SOIC-14 | U2–U5 |
| 4 | TL074CDT | SOIC-14 | U6–U9 |
| 1 | LM4040-2.5, 1 % (e.g. LM4040D25IDBZR) | SOT-23 | D11 |
| 2 | MMBT3904 | SOT-23 | Q1, Q2 |
| 2 | 1N5819HW | SOD-123 | D9, D10 |
| 15 | 100k 1 % | 0603 | R32, R36, R40, R44, R48, R52, R56, R60, R62, R65, R68, R71, R72, R76, R78 |
| 8 | 47k 1 % | 0603 | R31, R35, R39, R43, R47, R51, R55, R59 |
| 8 | 24k 1 % | 0603 | R30, R34, R38, R42, R46, R50, R54, R58 |
| 3 | 27k 1 % | 0603 | R63, R66, R69 |
| 3 | 15k | 0603 | R74, R81, R84 |
| 5 | 10k | 0603 | R75, R77, R79, R80, R83 |
| 13 | 1k | 0603 | R33, R37, R41, R45, R49, R53, R57, R61, R64, R67, R70, R82, R85 |
| 1 | 1k5 | 0603 | R73 |
| 3 | 1 n C0G | 0603 | C10–C12 |
| 13 | 100 n X7R | 0603 | C14–C26 |
| 1 | 1 µ X7R | 0805 | C13 |
| 2 | 10 µ 25 V X7R | 1206 | C27, C28 |
| 4 | female sockets 1×6, 1×11, 1×12, 1×7, 2.54 mm | through-hole | H1–H4 |

**Faceplate:**

| Qty | Part | Notes | Refs |
|---|---|---|---|
| 15 | Thonkiconn PJ398SM (Thonk) | | J1–J15 |
| 3 | EC11-type encoder with push, vertical, M7 bushing, D shaft (e.g. Bourns PEC11R-4215F-S0024; Tayda) + small knobs | check the datasheet and the height | ENC1–ENC3 |
| 3 | Thonk low-profile LED button: green, white, red; clip the feet | | SW1–SW3 |
| 8 | 3 mm red LED (Thonk) | | D1–D8 |
| 1 | 74HC165D | SOIC-16, rear | U10 |
| 2 | 74HC595D | SOIC-16, rear | U11, U12 |
| 12 | 10k, 0603 | rear | R1–R12 |
| 9 | 470R, 0603 | rear | R13–R20, R23 |
| 2 | 150R, 0603 | rear | R21, R22 |
| 3 | 100 n X7R, 0603 | rear | C1–C3 |
| 1 | 10 µ X7R, 1206 | rear, beside CN1 | C4 |
| 1 | 1×8 right-angle male header, 2.54 mm | the display cable's Dupont plug lies flat on it | CN1 |
| 1 | Waveshare 1.9inch LCD Module (ST7789V2) with its cable | glass taped to the panel's rear | DS1 |
| 4 | male headers 1×6, 1×11, 1×12, 1×7, 2.54 mm | | HF1–HF4 |

Plus a 12HP panel PCB and 4 M3 standoffs for the 8.5 mm gap, with screws.

---

## Firmware plan

libDaisy with the Daisy bootloader (BOOT_SRAM), like the other Seed modules.
No audio callback: a 4 kHz timer runs the engine.

### Shared with Side FXy, written once

Keep this code in one folder that both firmware projects use:

- **ST7789 driver:** SPI1 transmit-only with DMA, same pins.
  - Side FXy uses the screen in portrait; here it runs landscape through
    the MADCTL rotation.
  - The 170-pixel panels' 35 px offset moves to the other axis when the
    screen is rotated.
  - The frame is 320 × 170 × 2 = 109 KB. Under BOOT_SRAM the program lives
    in the 512 KB AXI SRAM, so the frame goes in D2 SRAM or SDRAM, or is
    kept as a 4-bit frame (27 KB) expanded into line buffers.
- **Shift chain:** the 165/595 chain driver (here 8 bits in, 16 out), the
  encoder decoding (a state table) and debouncing.
- **UI:** the soft-knob widgets (a parameter cell named by the screen beside
  or above its knob) and a small bitmap font.
- **Storage:** presets and calibration in QSPI.

### Engine (4 kHz tick)

- **Tempo:** a phase accumulator in 1/96 notes.
- **External clock:**
  - Each CLOCK edge is timestamped with the cycle counter, and the period is
    averaged over the last pulses, like the drum sequencer's 8.
  - Divisions count input pulses directly, so they add no jitter.
  - Multiplications and waves follow a smoothed phase, so they track tempo
    changes without jumps.
- **Each tick:**
  1. Compute eight output values.
  2. Write them with eight SPI3 frames (about 12 µs at 12.5 MHz) and pulse
     LDAC.
  3. Read the encoders and run the chain scan.
- **Latency:** an output edge lags its cause by less than 250 µs. If that
  shows on a scope against the drum sequencer, go to 8 kHz.
- **Output polarity:** the stage inverts (code 0 = +5.32 V), so the
  firmware writes `code = (5.32 − V) / 4.17 / 2.5 × 4096`, corrected by each
  output's calibration.
- **Run, stop and reset:**
  - All counters are bar-aligned.
  - RESET in and SHIFT + TAP restart at bar 1 on the next clock and fire
    RESET out.
  - RUN out is high while running.

### Features

**Global:**

- BPM 20–300 in 0.1 steps; tap tempo (average of the last 4 taps, forgotten
  after 2 s).
- Clock source auto (EXT while pulses arrive, else INT) or forced.
- CLOCK in PPQN 1, 2, **4**, 8, 24, 48.
- RESET in as a trigger (restart) or a gate (run while high), the two ways
  Pam's-style modules read it.
- Bar length (default 16 steps).
- Live changes of ratio, mute and preset take effect on the next beat or
  bar, so outputs stay in phase.

**Per output, clock mode:**

- **Ratio:** ×16 to ÷64 including triplets and dotted values, shown as note
  values (1/16 = ×4, 1/8T = ×3).
- **Gate:** width 1–99 % or a fixed 2 / 10 ms trigger.
- **Swing:** 50–75 %.
- **Euclidean:** length 1–32, hits, rotation.
- **Probability** 0–100 % with a LOOP length: the random choices repeat
  every n steps, so a pattern mutates slowly instead of churning (as in
  Marbles' déjà vu).
- **Also:** phase/delay, level (gate height), mute.

**Per output, wave mode:**

- **Shape:**
  - Sine, triangle, saw, ramp, square (with pulse width).
  - **Pump:** an exponential recovery from each beat, for sidechain-style
    ducking through a VCA.
  - S&H (one value per cycle, with slew) and smooth random (interpolated).
  - S&H and random have the same LOOP for repeating random lines.
- **Rate:** the clock ratios up to 64 bars, for slow drifts.
- **Shaping:** level, offset, phase (0–360°), a shape parameter (pulse
  width, curve, skew).
- **Reset:** the phase restarts on reset and at bar 1.

**CV:**

- CV 1–3, each with up to four destinations (any output parameter, amount
  ±100 %).
- Rate and ratio destinations step through the ratio list, so the outputs
  stay tempo-locked.

**System:**

- Presets in QSPI, recalled on the bar.
- Calibration (per output offset/scale, per CV input) in QSPI.

**For the style** (wobbles and pumping, slowly mutating repetition):

- **Already in the list:** the pump shape, triplet and dotted rates for
  wobble basses, LOOPed randomness, bar-quantised changes.
- **Later:**
  - A per-bar rate sequence on one output (e.g. 1/8, 1/8T, 1/16, 1/4) for
    US-bass wobbles.
  - Outputs modulating each other.

### UI (proposal)

| | Turn | Push | With SHIFT |
|---|---|---|---|
| K1 | home: select output 1–8, or the CLOCK lane left of 1; in a page: the parameter shown above it | home: open the selected output's pages; in a page: back home | — |
| K2 | home: the selected output's main value (ratio or rate); CLOCK lane: BPM | next page | fine steps |
| K3 | home: the second value (width or shape); CLOCK lane: source and PPQN | previous page; home: mute on the next bar | fine steps |
| RUN | | start / stop | presets page |
| TAP | | tap tempo | reset to bar 1 (fires RESET out) |

**The home page** (as on the panel preview) has three parts:

- **Top:** tempo, source and position.
- **Middle:** eight tiles laid out like the output jacks, each showing its
  mode, a wave or pulse icon and its value.
- **Bottom:** the three knobs' cells, centred over the knobs.

**Size:** an estimated 60–100 KB of code (no DSP library, one font). It
would fit the H750's 128 KB of internal flash, but BOOT_SRAM keeps QSPI
writes (preset saves) from stalling the program, as on Side FXy.

---

## Decided, and still open

**Decided (2026-10-31):**

- **Panel:** approved as drawn. That includes CV 3 in the fifth input
  spot, the output LEDs, the landscape screen and the colours.
- **Main board:** SMD at 12HP.

**Still open:**

1. **Output range.** The netlist keeps Marblesy's ±5.3 V: clocks up to
   +5 V, the same calibration code. For −5…+8 V (taller clocks, 0–8 V
   envelopes for VCAs), set `OUT_STAGE` to Rdac 18k, Rref 30k; that gives
   3.4 mV steps.
2. **Name.** "Tempo" is a working title.
3. **Parts to check on arrival:**
   - The button LEDs' forward voltage (R21, R22).
   - The EC11's height and pins against the footprint.
   - The 3V3D current.
4. **libDaisy:** SPI3 on PC10/PC12, checked before the schematic.

**Not included:**

- **MIDI clock in:** Side FXy has the TRS input circuit, should this ever
  want it.
- **A dedicated CLOCK out:** any output can be the 16th-note clock, and
  output 1 defaults to it, as the Arduino clock's output 1 did.
- **Reset inputs on the rig's sequencers:** neither sequencer has one yet
  (RIG.md), so RESET out waits for them. The 8-step's Eurorack rebuild
  advice already adds one on pin 2.
