# Side FXy — design notes

A RYK Modular SIDE FX clone for Eurorack, 14HP, on two stacked PCBs behind a
PCB panel. A Daisy Seed on Rob Heel's `seed_power_opamps` breakout does the
work, and Thonk supplies the panel parts where it can. Every reference designator
matches `hardware/tools/circuit.py`; `python circuit.py` prints the part
counts and runs the netlist checks.

Status: panel drafted (2026-10-31), netlist written and checked (0
problems). The schematic export, PCB placement, panel PCB and firmware are not
started.

---

## What SIDE FX has

From RYK's product page and photos (no manual published yet):

| Function | SIDE FX | Here |
|---|---|---|
| Audio | IN1, IN2, OUT1, OUT2 (dual-mono chains possible) | the breakout's audio in and out, IN 2 normalled to IN 1 |
| FX send buttons, lit | PITCH, DELAY, TEXTURE, REVERB | Thonk LED buttons SW1–SW4 |
| Extra button | red, unlabelled | SHIFT, SW5 (LED button) |
| Knobs | 4, labelled by the screen | 4 EC11 encoders with push, ENC1–ENC4 |
| Screen | portrait, about 26 × 42 mm | 1.9" IPS 170 × 320, ST7789V2 |
| CV inputs | M1–M4, assignable | CV 1–4, ±5 V |
| Clock input | CLK | CLOCK |
| MIDI in | MIDI (3.5 mm) | TRS type A |
| Presets | on an internal SD card | microSD on Adafruit's SDIO breakout |

---

## Architecture

```
 panel ─┬─ faceplate board (FB)   9 Thonkiconn + 1 stereo Thonkiconn, 4 EC11 encoders,
        │   69.6 x 108 mm          5 LED buttons, 2x 74HC165 + 74HC595 on one chain,
        │                          2 bussed 10k networks, LED resistors, CN1 for the display cable
        │   display module (Waveshare 1.9inch LCD) behind the window, cable to CN1
        │      29 pins in 4 headers (male on the FB, female on the MB)
        └─ main board (MB)        Daisy Seed on the seed_power_opamps breakout (audio in/out),
            69.6 x 108 mm          TL074 with 4 CV input stages, clock input stage,
                                   H11L1 MIDI input, Adafruit 4682 microSD breakout on a socket
```

The stack is Marblesy's: panel parts on the FB's front, logic and male
headers on its rear, sockets on the MB's front, the breakout and everything
else on the MB's rear.

### Daisy Seed pin map

| Seed pin | libDaisy | Net | Use |
|---|---|---|---|
| 1 | D0 | CLK | clock input (after the transistor, active low) |
| 2–7 | D1–D6 (SDMMC1 DAT3, DAT2, DAT1, DAT0, CMD, CK) | SD_D3, SD_D2, SD_D1, SD_D0, SD_CMD, SD_CLK | microSD, 4-bit |
| 8, 9, 11 | D7, D8, D10 (SPI1 NSS, SCK, MOSI) | LCD_CS, LCD_SCK, LCD_MOSI | display |
| 12, 13, 14 | D11, D12 (TIM4_CH4), D13 | LCD_DC, LCD_BL, LCD_RST | display data/command, backlight PWM, reset |
| 15 | D14 (USART1 RX) | MIDI_RX | MIDI in, 31250 baud |
| 20, 40 | AGND, DGND | GND | both on the main board's GND |
| 21 | 3V3A | 3V3A | CV bias divider |
| 22–25 | A0–A3 | ADC_CV1..ADC_CV4 | CV inputs |
| 26 | D19 | SD_DET | card detect (high with a card) |
| 27 | D20 | BTN_SHIFT | SHIFT button, 10k pull-up on the FB |
| 33, 34 | D26, D27 | SR_CLK, SR_LOAD | shift-register chain clock; 165 /PL and 595 RCLK |
| 36, 37 | D29, D30 | SR_DOUT, SR_DIN | to the 595 SER, from U1's Q7 |
| 38 | 3V3D | 3V3D | logic, display, microSD, MIDI pull-up |
| 10, 28–32, 35, 39 | D9, A6–A10, A11, VIN | — | free (D9 is SPI1 MISO; the display never talks back) |

The breakout's headers land on the same footprint: J1 (GND, −12 V ×3), J3
(GND, +12 V ×3), J4 (audio out: AOUT1 = OUT1, AOUT2 = OUT2), J5 (audio in:
AIN1 = IN1, AIN2 = IN2). Unlike Plaitsy and Marblesy, this module uses the
breakout's audio input op-amps, so J5's contacts stay in.

---

## Main board circuits

### CV inputs (4×)

Marblesy's stage, unchanged:

```
jack tip ── 100k ──┬── (−) TL074 ──┬── 1k ── Seed ADC
                   ├── 27k ────────┤
                   └── 1n ─────────┘
BIAS 1.32 V ──────── (+)
```

V_adc = 1.676 V − 0.27·V_in: ±5 V lands on 0.33–3.03 V. BIAS = 3V3A ×
10k/25k (R22 15k, R23 10k, C14 1 µ). An unplugged jack grounds its tip
through the switch lug, so it reads 0 V.

| Input | Section | Rin | Rf | Cf | Rs | ADC |
|---|---|---|---|---|---|---|
| CV 1 | U6A | R10 | R11 | C10 | R12 | A0 |
| CV 2 | U6B | R13 | R14 | C11 | R15 | A1 |
| CV 3 | U6C | R16 | R17 | C12 | R18 | A2 |
| CV 4 | U6D | R19 | R20 | C13 | R21 | A3 |

U6 decoupling: C15 (+12 V), C16 (−12 V).

### Clock input

```
jack tip ── 100k (R24) ── base 2N3904 (Q1), emitter to GND
            BAT85 (D1) cathode on the base, anode to GND
            collector ── 10k (R25) to 3V3D, and to D0
```

High input = D0 low; threshold about 0.7 V. The jack's switch lug grounds
the tip when nothing is plugged in.

### MIDI in (TRS type A)

```
ring (DIN 4, source) ── 220R (R26) ── H11L1 pin 1 (LED anode)
tip  (DIN 5, sink)   ───────────────── H11L1 pin 2 (LED cathode)
1N4148 (D2) across the LED, cathode on pin 1
H11L1 pin 4 ── 1k (R27) to 3V3D ── D14 (USART1 RX); pin 6 3V3D, pin 5 GND, C17 100n
```

The H11L1 runs from 3 V and its output idles high, as a UART wants. The
sleeve is left open (a MIDI input leaves the shield unconnected). Type B
gear (tip and ring swapped) needs a type B adapter cable.

### microSD

Adafruit 4682 (microSD SPI or SDIO breakout, 3 V only, pull-ups on every
line, 25.4 × 22.9 mm) in a 9-pin female socket, wired for 4-bit SDIO:
pins 1–9 = 3V, GND, CLK, D0, CMD, D3, D1, D2, DET. C18 10 µ at its supply.
The microSD socket itself is SMD only; the breakout keeps the build
through-hole.

---

## Faceplate circuits

### Jacks

| Jack | Tip | Switch lug |
|---|---|---|
| J1 IN 1 | IN1_F | GND_F |
| J6 IN 2 | IN2_F | IN1_F (normal: a mono source feeds both channels) |
| J2 OUT 1, J7 OUT 2 | OUT1_F, OUT2_F | open |
| J3 CLOCK | CLK_IN_F | GND_F |
| J4, J8, J9, J10 CV 1–4 | CV1_F..CV4_F | GND_F |
| J5 MIDI (stereo Thonkiconn PJ366ST) | MIDI_TIP_F, ring MIDI_RING_F | sleeve and lugs open |

### Encoders, buttons and LEDs on one chain

U1 and U2 (74HC165) read all 16 switch lines; U3 (74HC595) drives the five
button LEDs. They share SR_CLK, and SR_LOAD goes to both the 165s' /PL and
the 595's RCLK. A scan: SR_LOAD low (the 165s load), SR_LOAD high (the 595
latches the LED byte shifted in by the previous scan), then 16 clocks that
read SR_DIN and shift the next LED byte out on SR_DOUT. Bit-banged from a
2 kHz timer, that's a few µs per scan, and fast enough to decode the
encoders' quadrature in software.

| Chip | D0..D7 |
|---|---|
| U1 (read first, Q7 = SR_DIN) | ENC1 A, B; ENC2 A, B; ENC3 A, B; ENC4 A, B |
| U2 (Q7 → U1 DS, DS to ground) | K1–K4 push, PITCH, DELAY, TEXTURE, REVERB |
| U3 74HC595 QA..QE | PITCH, DELAY, TEXTURE, REVERB, SHIFT LEDs (QF–QH spare) |

Every 165 input has its own 10k pull-up from a bussed network (RN1 for U1,
RN2 for U2; pin 1 common to 3V3D_F). Encoder common and switch go to
ground. SHIFT has its own Seed pin and pull-up (R6 10k), because the two
165s are full. LED resistors R1–R5 are 470R, about 3 mA per red LED.
Decoupling C1–C3 100n.

### Display

The Waveshare 1.9inch LCD Module (ST7789V2, 170 × 320, 3.3 V, 40 mA max)
comes with an MX1.25 cable that ends in 2.54 mm Dupont sockets. They plug
onto CN1, in Waveshare's order: VCC, GND, DIN, CLK, CS, DC, RST, BL. C4
10 µ beside CN1. BL takes the Seed's PWM directly; the module switches the
backlight itself (check the module schematic before relying on that).

---

## Board-to-board headers

Split by function. The pin order is a first guess, and the PCB step sorts it
for the fewest crossings.

| Header | Pins (MB net / FB net) |
|---|---|
| H1 / HF1 (6) | IN1, GND/GND_F, IN2, OUT1, GND/GND_F, OUT2 |
| H2 / HF2 (8) | CV1, CV2, CV3, CV4, CLK_IN, GND/GND_F, MIDI_TIP, MIDI_RING |
| H3 / HF3 (7) | 3V3D, GND/GND_D_F, SR_CLK, SR_LOAD, SR_DIN, SR_DOUT, BTN_SHIFT |
| H4 / HF4 (8) | 3V3D, GND/GND_D_F, LCD_SCK, LCD_MOSI, LCD_CS, LCD_DC, LCD_RST, LCD_BL |

The faceplate keeps two grounds: GND_F (jack sleeves and lugs, the audio
and CV return) and GND_D_F (logic, encoders, display). They join only on the
main board, through their own header pins.

---

## Power

±12 V from the breakout's J1/J3 feed only the TL074. Everything else runs
on the Seed's 3V3D: the display (40 mA max), the microSD (up to about
100 mA while writing), the LEDs (about 15 mA) and the logic. Measure the
3V3D current on the first build. If the Seed's regulator runs hot, give the
display and the card their own 3.3 V regulator.

---

## BOM

| Qty | Part | Notes | Refs |
|---|---|---|---|
| 1 | Daisy Seed (Thonk) | | U5 |
| 1 | seed_power_opamps breakout (Rob Heel), built with its audio in and out | | U5 |
| 1 | Waveshare 1.9inch LCD Module (ST7789V2, 170 × 320, SPI) with its cable | | DS1, CN1 |
| 1 | Adafruit 4682 microSD SPI/SDIO breakout + a microSD card | | U8 |
| 9 | Thonkiconn PJ398SM (Thonk) | | J1–J4, J6–J10 |
| 1 | Thonkiconn stereo PJ366ST (Thonk) | MIDI | J5 |
| 5 | Thonk low-profile LED button, red | clip the three feet | SW1–SW5 |
| 4 | EC11-type encoder with push switch, vertical, M7 bushing, D shaft (e.g. Bourns PEC11R-4215F-S0024; Tayda) + small D-shaft knobs | check the datasheet and the height before ordering | ENC1–ENC4 |
| 1 | TL074 + DIP-14 socket | | U6 |
| 2 | 74HC165 + DIP-16 sockets | | U1, U2 |
| 1 | 74HC595 + DIP-16 socket | | U3 |
| 1 | H11L1 + DIP-6 socket | | U7 |
| 1 | 2N3904 | | Q1 |
| 1 | BAT85 | | D1 |
| 1 | 1N4148 | | D2 |
| 2 | 10k × 8 bussed resistor network, SIP-9 (Bourns 4609X-101-103LF, Tayda A103J) | | RN1, RN2 |
| 5 | 100k | | R10, R13, R16, R19, R24 |
| 4 | 27k | | R11, R14, R17, R20 |
| 5 | 1k | | R12, R15, R18, R21, R27 |
| 1 | 15k | | R22 |
| 3 | 10k | | R6, R23, R25 |
| 1 | 220R | | R26 |
| 5 | 470R | | R1–R5 |
| 4 | 1n film/C0G | | C10–C13 |
| 6 | 100n | | C1–C3, C15–C17 |
| 1 | 1 µ | | C14 |
| 2 | 10 µ electrolytic | | C4, C18 |
| — | Male + female 2.54 mm headers (Thonk header bag): 6, 7, 8, 8 pins per side; a 9-pin female for U8; sockets for the breakout | | H1–H4, HF1–HF4 |

---

## Firmware notes

- libDaisy with the Daisy bootloader, like the other Seed modules. Sixteen
  effect types plus a UI outgrow the H750's 128 KB of internal flash, so
  build for QSPI or SRAM.
- **Display:** libDaisy has no ST7789 driver, so write a small one: SPI1
  transmit-only with DMA, 16-bit colour, a frame of 170 × 320 × 2 = 109 KB,
  or a 4-bit frame expanded into line buffers. The 170-pixel panels sit at
  a column offset (35 on most 1.9" modules; check yours).
- **Controls:** a 2 kHz timer runs the shift chain; quadrature decoding with a
  state table and debouncing happen in software. The send LEDs can dim with
  software PWM in the same loop.
- **MIDI:** USART1, receive only (D13 is the display's reset, so no TX
  pin).
- **SD:** libDaisy's SDMMC handler in 4-bit mode with FatFS; SD_DET tells the
  UI whether a card is in.
- **CV:** four ADC channels, calibrated for offset and scale per channel
  like Marblesy's.
