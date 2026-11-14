# Side FXy — design notes

A RYK Modular SIDE FX clone for Eurorack, 14HP, on two stacked PCBs behind a
PCB panel. A Daisy Seed on Rob Heel's `seed_power_opamps` breakout does the
work, and Thonk supplies the panel parts where it can. Every reference designator
matches `hardware/tools/circuit.py`; `python circuit.py` prints the part
counts and runs the netlist checks.

Status (2026-10-31): panel approved; netlist written and checked (0
problems). The EasyEDA Pro project (`hardware/easyeda/SideFXy.epro2`) has the
schematic, checked against the netlist, plus both PCBs placed and
net-assigned (not routed), with every clearance check at 0, and the panel as
a third PCB. See [Schematic](#schematic) and [PCB placement](#pcb-placement).
Routed since (see [PCB placement](#pcb-placement)); the firmware is written but
not yet run on hardware (see [Firmware notes](#firmware-notes)).

Tested 2026-11-13: `hardware/tests/` checks the circuit, the boards, the
firmware's pins, the parts and the panel against each other and the
datasheets ([test report](test-report-2026-11-13.md)). Since then the CV
stages run at a lower gain, so that ±12 V stays inside the ADC pins' range
(below), and the [build notes](#build-notes) list what the boards can't show.

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
| Presets | on an internal SD card | in the Seed's 8 MB QSPI flash, no card (see [Presets](#presets)) |

---

## Architecture

```
 panel ─┬─ display module (Waveshare 1.9inch LCD) in the panel gap, glass to the window
        ├─ faceplate board (FB)   9 Thonkiconn + 1 stereo Thonkiconn, 4 EC11 encoders,
        │   69.6 x 108 mm          5 LED buttons, 2x 74HC165, 2 bussed 10k networks,
        │                          CN1 (right-angle) for the display cable, cutout for its plug
        │      30 pins in 4 headers (male on the FB, female on the MB)
        └─ main board (MB)        Daisy Seed on the seed_power_opamps breakout (audio in/out),
            69.6 x 108 mm          TL074 with 4 CV input stages, clock input stage,
                                   H11L1 MIDI input, 74HC595 + 470R for the button LEDs
```

The stack is Marblesy's: panel parts on the FB's front, logic and male
headers on its rear, sockets on the MB's front, the breakout and everything
else on the MB's rear. The display adds one rule: nothing with leads on the
faceplate behind the module (see [PCB placement](#pcb-placement)), which is
why the 74HC595 lives on the main board.

### Daisy Seed pin map

| Seed pin | libDaisy | Net | Use |
|---|---|---|---|
| 1 | D0 | CLK | clock input (after the transistor, active low) |
| 8, 9, 11 | D7, D8, D10 (SPI1 NSS, SCK, MOSI) | LCD_CS, LCD_SCK, LCD_MOSI | display |
| 12, 13, 14 | D11, D12 (TIM4_CH4), D13 | LCD_DC, LCD_BL, LCD_RST | display data/command, backlight PWM, reset |
| 15 | D14 (USART1 RX) | MIDI_RX | MIDI in, 31250 baud |
| 20, 40 | AGND, DGND | GND | both on the main board's GND |
| 21 | 3V3A | 3V3A | CV bias divider |
| 22–25 | A0–A3 | ADC_CV1..ADC_CV4 | CV inputs |
| 27 | D20 | BTN_SHIFT | SHIFT button, the Seed's internal pull-up |
| 33, 34 | D26, D27 | SR_CLK, SR_LOAD | shift-register chain clock; 165 /PL and 595 RCLK |
| 36, 37 | D29, D30 | SR_DOUT, SR_DIN | to the 595 SER (main board), from U1's Q7 (faceplate) |
| 38 | 3V3D | 3V3D | logic, display, MIDI pull-up |
| 2–7, 10, 26, 28–32, 35, 39 | D1–D6, D9, A4, A6–A10, A11, VIN | — | free (D1–D6 are SDMMC1 should a card ever come back; D9 is SPI1 MISO, and the display never talks back) |

The breakout's headers land on the same footprint: J1 (GND, −12 V ×3), J3
(GND, +12 V ×3), J4 (audio out: AOUT1 = OUT1, AOUT2 = OUT2), J5 (audio in:
AIN1 = IN1, AIN2 = IN2). Unlike Plaitsy and Marblesy, this module uses the
breakout's audio input op-amps, so J5's contacts stay in.

---

## Main board circuits

### CV inputs (4×)

Marblesy's stage, at half its gain since 2026-11-13:

```
jack tip ── 100k ──┬── (−) TL074 ──┬── 1k ── Seed ADC
                   ├── 13k ────────┤
                   └── 2n2 ────────┘
BIAS 1.47 V ──────── (+)
```

V_adc = 1.657 V − 0.13·V_in: ±5 V lands on 1.01–2.31 V, ±10 V on
0.36–2.96 V and ±12 V on 0.10–3.22 V (−0.02–3.35 V at the worst corner of
1 % parts, the 3V3A tolerance and the TL074's offset). BIAS = 3V3A ×
12k/27k (R22 15k, R23 12k, C14 1 µ). Cf keeps the corner at 5.6 kHz.

Why the low gain: nothing clamps the TL074's output, and A2 / A3 (PB1,
PA7) are the STM32's 3.3 V-tolerant TT pins, 4.0 V absolute maximum. With
Marblesy's 27k a −10 V CV put 4.4 V on them, and above +6 V every input went
below 0 V. An unplugged jack grounds its tip through the switch lug, so it
reads 0 V.

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
the tip when nothing is plugged in. D1's reverse leakage flows through R24
and raises the threshold, so D1 must leak little: an SD103A or BAT86 would
take the worst case to about 3.4 V when warm. The BOM gives D1 a line of its
own.

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

### Audio path (on the breakout)

Side FXy adds no audio parts. IN 1 / IN 2 go through H1 to the breakout's
J5 and two inverting TL074 stages per channel into the Seed's codec, and
back out through two more to J4 and the OUT jacks. This is the Daisy Patch
Rev 8 circuit, traced from the breakout's Gerbers:

- In: 100k / 100k ∥ 47p, then 100k / 10k ∥ 560p, then 1k (gain +0.1).
- Out: 10k / 100k ∥ 47p, then 100k / 100k ∥ 47p, then 1k (gain +10).

The path is non-inverting end to end. What that means here:

- **Treble:** the feedback caps put poles at 28–34 kHz: 5.8 dB down at
  20 kHz through the module, 1.6 dB at 10 kHz. Build the breakout with
  10 pF for its six 47 pF and 100 pF for its two 560 pF (0603 C0G). It is
  then 0.3 dB down, with at least 58° of phase margin.
- **Input level:** about 16 V p-p in the worst case (20 V typical) before
  the first stage clips. 10 V p-p Eurorack audio has room.
- **Output clip:** the output stage clips at about 16 V p-p in the worst
  case, which is 0.46–0.59 of the codec's full scale. The firmware's soft
  limiter (knee at 0.75 of full scale) never acts before that analog clip.
- **Gain:** OUT is about 0.9 dB below IN on a Seed Rev7 (PCM3060), where
  the Seed's 13.6k input loads the breakout's 1k, and 0.4 dB on a Rev5.
- **Load:** each input is 100k; with IN 2 normalled to IN 1, a source on
  IN 1 sees 49.5k.

### Button LEDs

U3 (74HC595) at the end of the chain drives the five LED-button anodes
through R1–R5 (470R, about 3 mA into a red LED) and H3. The cathodes go to
the faceplate's GND_D_F. QF–QH are spare. C3 100n at pin 16. It used to be
on the faceplate; the display's keep-out left no room for it there.

### Presets

No hardware: presets go in the Seed's 8 MB QSPI flash, next to the
firmware. A preset (algorithm, four blocks' settings, CV and LFO
assignments) is a few hundred bytes, so even a thousand presets take less
than 1 MB. SIDE FX's SD card is mainly for swapping preset files with
other owners, and RYK's files wouldn't load on this firmware anyway.
Backups, if wanted, can go over the Seed's USB later, with no hardware
change. Dropped on 2026-10-31: the Adafruit 4682 SDIO breakout, its socket and
C18, up to 100 mA on 3V3D, and seven Seed pins.

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
| J5 MIDI (stereo Thonkiconn PJ366ST) | MIDI_TIP_F, ring MIDI_RING_F | sleeve open (no switch contacts) |

### Encoders, buttons and LEDs on one chain

U1 and U2 (74HC165) read all 16 switch lines; U3 (74HC595, on the main
board) drives the five button LEDs. They share SR_CLK, and SR_LOAD goes to
both the 165s' /PL and the 595's RCLK. A scan: SR_LOAD low (the 165s load), SR_LOAD high (the 595
latches the LED byte shifted in by the previous scan), then 16 clocks that
read SR_DIN and shift the next LED byte out on SR_DOUT. Bit-banged from a
4 kHz timer, that's a few µs per scan, and fast enough to decode the
encoders' quadrature in software.

| Chip | D0..D7 |
|---|---|
| U1 (read first, Q7 = SR_DIN) | ENC1 A, B; ENC2 A, B; ENC3 A, B; ENC4 A, B |
| U2 (Q7 → U1 DS, DS to ground) | K1–K4 push, PITCH, DELAY, TEXTURE, REVERB |
| U3 74HC595 QA..QE (main board) | PITCH, DELAY, TEXTURE, REVERB, SHIFT LEDs (QF–QH spare) |

Every 165 input has its own 10k pull-up from a bussed network (RN1 for U1,
RN2 for U2; pin 1 common to 3V3D_F). Encoder common and switch go to
ground. SHIFT goes straight to its own Seed pin, which uses its internal
pull-up, because the two 165s are full. The LED-button anodes come from the
main board through H3. Decoupling C1 and C2 100n.

### Display

The Waveshare 1.9inch LCD Module (ST7789V2, 170 × 320, 3.3 V, 40 mA max)
comes with an MX1.25 cable that ends in 2.54 mm Dupont sockets. They plug
onto CN1, a right-angle header so the plug lies flat in the 11 mm gap
between the boards, in Waveshare's order: VCC, GND, DIN, CLK, CS, DC, RST,
BL. Alternatively, cut the Dupont ends off and solder the wires into CN1. C4
is a 10 µ ceramic on 5.08 mm, beside CN1; an electrolytic stands too tall
for the gap. BL takes the Seed's PWM directly; the module switches the
backlight itself (check the module schematic before relying on that).

Mounting: the module sits in the panel gap, glass against the panel's rear
(thin double-sided tape round the window). Its four M2 holes are under the
glass, so they can't take screws from the front. The cable connector on its
back stands about 3.5 mm proud; the faceplate has a 16.7 × 13.5 mm cutout
under it, and the cable runs through that to CN1 on the rear.

---

## Board-to-board headers

Split by function. The pin order is in `circuit.HEADERS`, shared by both
boards; the positions are the routed export's.

| Header | Where (front view) | Pins (MB net / FB net) |
|---|---|---|
| H1 / HF1 (5) | bottom-left corner beside IN 2, x 2.6, y 2.9–13.1, pins along y | IN1, IN2, GND/GND_F, OUT1, OUT2 |
| H2 / HF2 (8) | right edge beside the encoders | CV1, CV2, CV3, CV4, CLK_IN, GND/GND_F, MIDI_TIP, MIDI_RING |
| H3 / HF3 (11) | strip beside the display, upper | 3V3D, GND/GND_D_F, SR_CLK, SR_LOAD, SR_DIN, BTN_SHIFT, LED_PITCH, LED_DELAY, LED_TEXTURE, LED_REVERB, LED_SHIFT |
| H4 / HF4 (6) | strip beside the display, lower | LCD_SCK, LCD_MOSI, LCD_CS, LCD_DC, LCD_RST, LCD_BL |

The display's power comes from H3's 3V3D and GND_D_F on the faceplate.

The faceplate keeps two grounds: GND_F (jack sleeves and lugs, the audio
and CV return) and GND_D_F (logic, encoders, display). They join only on the
main board, through their own header pins.

---

## Schematic

`hardware/tools/easyeda_export.py` writes `hardware/easyeda/SideFXy.epro2`:
three boards (SideFXy Main, SideFXy Faceplate, SideFXy Panel), each with its
schematic and its PCB, and four A3 pages:

| Page | Holds |
|---|---|
| Main board | Seed, CV stages, clock, MIDI, bias, U6 decoupling, U3 + R1–R5 + C3, H1–H4 |
| Faceplate 1 | jacks, encoders, LED buttons |
| Faceplate 2 | U1/U2 + RN1/RN2, CN1, C1, C2, C4, HF1–HF4 |
| Panel | a note: the panel PCB has no parts |

Run `python easyeda_export.py` from `hardware/tools` (needs Pillow for
the previews). It reports the schematic problems (every pin of the netlist
drawn exactly once and on its net, with no T-junctions or pins in the middle
of a wire), any symbol pin without a footprint pad or the reverse, and any
missing device, symbol or footprint in the written file. All three are 0.

Parts come from your MorrisSynth library caches: the TL074ACN symbol, the
WQP518MA jack, LR1F resistors, FG28 / SR305 / 178MU0033 capacitors, the 1N4148
footprint with the 1N5819 symbol, the 74HC595N's DIP-16, net ports, ground
flags and the frame. Everything else is drawn in the same style:

- **Footprints:**
  - Taken over from Marblesy and the mixer: the Seed breakout, DIP-14 and
    DIP-6 on 7.62 mm rows, TO-92, the Thonk LED button, standing resistors,
    1×N headers.
  - New:
    - SIP-9 for the networks.
    - EC11 with its origin on the shaft (KiCad's Alps EC11E footprint).
    - PJ366ST in the library jack's frame (slots from a KiCad merge request
      that was never merged).
- **Symbols:** Seed, 74HC165, 74HC595, H11L1, 2N3904, LED button, EC11,
  bussed network, stereo jack, headers.
- **Resistors:** they stand up on the main board, like the mixer's and the
  re-routed Marblesy's. The faceplate has none: its pull-ups are the two
  SIP-9 networks.

**What EasyEDA's DRC will still say** (all intentional, floating-pin warnings):

| Where | Pins left open |
|---|---|
| U5 (Seed) | D1–D6, D9, D19, D21–D25, D28, VIN, and the four codec pins 16–19, which the breakout's op-amps take over |
| U7 (H11L1) | pin 3 (NC) |
| U1, U2 (74HC165) | /Q7 |
| U3 (74HC595) | QF–QH and QH' |
| J5 | the sleeve |
| J2, J7 (outputs) | the switch lugs |

**Check before ordering boards:**

- A PJ366ST's leads against the slots.

---

## PCB placement

**Routed, 2026-11-01.** The routed export `hardware/easyeda/SideFXy-routed.epro2`
is now the layout master. `pcb.py` reads the faceplate's rear side and the
whole main board from it; the panel parts still come from
`circuit.PLACEMENT`. `routed_check()` makes the exporter fail if the
generator and the routed boards disagree.

The audit is in [routing-audit-2026-11-01.md](routing-audit-2026-11-01.md).
The fourth export (2026-11-02) audits clean, and the exporter reports 0
problems. It is the state to order from, with the copper fixes of
2026-11-14 patched into it (the audit's first section): no-copper circles at
the barrels, the GND_F sliver gone, 0.25 mm rings on the EC11 tab slots and
the PJ366ST tip. Since 2026-11-15 the master is the user's own export of
that state, with EasyEDA's rebuilt pours, and with five library parts put
back under fresh IDs (the audit's first section). The user's next export
(2026-11-15) kept them, and it is now the master: **this is the state to
make Gerbers from.** EasyEDA keeps its own copy of a library part whose ID
it already holds, so a later edit to a footprint, device or symbol needs a
fresh ID to survive an import.

The tables below describe the placement that routing started from. The
audit's last section lists what moved while routing.

`pcb.py` places both boards (unrouted, net-assigned) and checks them; the
exporter writes them into the project and reports 0 problems on all of these:

- every part placed once;
- pads 0.25 mm apart, 0.5 mm from the edge, clear of the holes and the cutout;
- bodies not overlapping on one side;
- nothing under a standoff (the gap side) or a screw head (the other side);
- every header pin at the same spot on both boards;
- the panel parts exactly at their panel positions;
- no faceplate rear pad under a jack, encoder or button body or under the
  display module.

The written file is read back: every PAD_NET names a real pad of its
footprint and a net with a NET record. Previews:
`hardware/easyeda/side-fx-easyeda-pcb-{faceplate,main-board,panel}.png`.

**Faceplate** (front view coordinates):

| Area | Front side (panel side) | Rear side |
|---|---|---|
| y 0–26 | jack rows | — |
| y 29–40 | — | U1 (x 10.4) and U2 (x 44.0) at y 33.1, C1 and C2 beside them, H1 at the right end; hole at (30.0, 33.1) |
| x 2.75–30.05, y 38.7–89.9 | the display module | nothing with leads; the cable's cutout at x 8.0–24.7, y 43.5–57.0; CN1's plug lies over this area |
| x 32.4, y 39–81 | — | H4 (lower) and H3 (upper) |
| x 35–66, y 37–88 | encoders (phase pins below the shaft; ENC4's on its left), SW5 | RN1 and RN2 standing between the encoder columns at x 50.3; H2 at the right edge, x 67.6 |
| y 90–97 | — | CN1 (right-angle, pins along x at y 92.6) and C4 |
| y 98–106 | send buttons | holes at (34.8, 104.5) and (51.5, 104.5) |
| | | another hole between the encoder columns at (50.3, 49.0) |

**Main board** (rear view, as EasyEDA shows the top layer, so the front
view's right is on the left):

- **Breakout:** stands in the middle, pins 21–40 (3V3A, the ADC inputs,
  the chain, 3V3D) in its left row and pins 1–20 (clock, display, MIDI) in
  its right row. The USB end is at the bottom and J1 / J3 (±12 V) at the top.
- **Channel between its rows:** H3's and H4's sockets and two of the
  mounting holes, under the raised breakout.
- **Left side, top to bottom:**
  - the TL074 with its four CV stages clustered at its corners (Rf, then
    Rin / Rs, then Cf going outwards) and a 100 n per rail beside pins 4 / 11;
  - the bias divider and its 1 µ;
  - the H11L1 with its 220R, 1N4148, pull-up and 100 n;
  - the clock stage;
  - H1's sockets;
  - the 74HC595 with R1–R5 beside QA–QE and C3 at pin 16.
- **Right of the breakout:** left empty for routing.

### Routing notes

- **Rules:** clearance 0.25 mm, tracks 0.3 mm, a POWER class of 0.6 mm
  (±12 V, 3V3A, 3V3D and their _F twins), vias 0.61 / 0.305 mm, copper 0.35 mm
  from the edge, as routed. The placement asked for 0.8 / 0.4 mm vias and
  0.5 mm from the edge; both as routed are inside JLCPCB's limits (via
  0.3 mm drill, 0.2 mm to the edge).
- **Main board ground:** one GND, poured on both layers.
- **Main board, CV:**
  - The CV stages' summing nodes are short by placement. Keep them and the
    ADC lines (pins 22–25, left row) on one layer, over the pour.
  - The ADC lines cross from the TL074 to the breakout's left row; the CV
    inputs come in from H2 at the left edge.
- **Main board, right row (display, MIDI, clock):** pins 8–15 and 1 sit in
  the breakout's right row. Run these down the channel between the rows
  (free on both layers apart from the H3 / H4 sockets) and out through the
  gaps of the left row, or round the breakout's ends.
- **Main board, ±12 V:** from J3 (left row, +12 V) and J1 (right row,
  −12 V) at the top, as 0.6 mm tracks to C15 / C16.
- **Faceplate grounds:** GND_F poured on the panel side (front) under the
  jack, CV and audio lines; GND_D_F on the rear for the logic, encoders,
  buttons and display. They meet only on the main board.
- **Faceplate, under the display:** tracks may run under the module (only
  leads are kept out); the cutout needs its 0.3 mm copper clearance.
- **Faceplate, encoder and button lines:** they run down to U1 / U2 in the
  jack strip, the networks sitting on them between the encoder columns.
  Keep them off the audio lines (IN / OUT to H1).

---

## Power

±12 V from the breakout's J1/J3 feed only the TL074. Everything else runs
on the Seed's 3V3D: the display (40 mA max), the LEDs (about 15 mA), the
MIDI pull-up and the logic, about 60 mA on top of the Seed itself.

From the bus the module draws about 64 mA typical (106 mA max) from +12 V,
the same from −12 V, and nothing from +5 V. The breakout's B2405S-1WR2
(24 V in, 5 V 1 W out) carries the Seed and the 3V3D loads:

- 5 V load: 177 mA typical, 239 mA at worst case, against its 200 mA.
- Input: at a bus 5 % low and full load, after the breakout's two B5819W, it
  sees about 21.5 V, at the bottom of its 21.6–26.4 V range (the diodes' drop
  at this current isn't specified; it is unregulated, with no cut-off).

On the first build, measure the bus current with the backlight and LEDs at
full. If it is high, cap their brightness in the firmware, or fit a 2 W
converter in the breakout's U3 place (check its footprint, and that L1 / L2
carry about 115 mA). A separate regulator for the display only helps if it
runs from +12 V. The converter can't be hot-plugged (Mornsun).

---

## Build notes

From the 2026-11-13 [test report](test-report-2026-11-13.md); the BOM's notes
say the same.

- **The breakout's orientation.** It goes on with its SMD side (op-amps,
  diodes) towards the main board and the Seed on top, USB at the J4 / J5
  end.
  - It fits either way round, and turned over it puts ±12 V into U6
    reversed.
  - Solder its J1 / J3 / J4 / J5 male headers in from the SMD side, pins
    towards the main board. This is against the breakout's own silk, which
    draws them on the Seed's side.
  - Put the Seed's rows on long-tail stacking headers, whose tails go
    through into the main board's sockets.
  - With the Seed out, check +12 V at C15 and −12 V at C16 before the first
    power-up.
- **The breakout's audio caps:** 10 pF and 100 pF instead of its 47 pF and
  560 pF (see [Audio path](#audio-path-on-the-breakout)).
- **U1 and U2** go straight on the faceplate, without sockets: socketed,
  they reach the main board's solder tails in the 11 mm gap.
- **The panel gap.** The panel sits on the jack bodies, 9.0 mm above the
  faceplate on Thonk's drawing; the earlier notes assumed 7 mm.
  - Before soldering the panel parts, fit one Thonkiconn and one LED button
    (feet clipped) on the bare faceplate and lay the panel on them. Read off
    Thonk's drawing, the button's square base stands 9.85–10.2 mm tall, so
    it may hold the panel up.
- **The encoders** are Bourns PEC11R-4215F-S0024.
  - **No nut:** the 5 mm bushing ends 11.5 mm above the faceplate, only
    about 0.9 mm in front of the panel (0.45 mm at worst), too little for
    the nut. Leave the nut and washer off: the encoder hangs on its soldered
    pins and tabs, the bushing centres it in the panel hole, and a push on
    the knob goes into the faceplate. The 15 mm shaft still stands about
    11 mm in front of the panel for the knob.
  - **Tabs:** Bourns' layout asks for 1.8 × 2.6 mm tab holes 4.8–6.6 mm from
    the shaft; the footprint's MP1 / MP2 slots (KiCad's Alps EC11E) are
    1.5 mm along the tab line, 4.85–6.35 mm, and 2.7 mm across (Bourns:
    2.6), in 3.2 × 2.0 mm pads for a 0.25 mm ring. The encoders' tabs measure
    12.7 mm or less across their outer faces (2026-11-14), so they fit the
    slots as routed. The fit is close: squeeze the barbs if a tab binds, and
    solder both tabs.
- **Nylon washers** at the faceplate holes (19.3, 49.0) and (39.6, 33.1)
  (routed frame): ENC4's A pad and SR_CHAIN run under the standoff and the
  screw head there.
- **Q1** sits on 2.54 mm: a formed-lead 2N3904, or spread a bulk part's
  1.27 mm leads.

---

## BOM

Generated from `circuit.py` by `hardware/tools/bom.py`, with the Thonk parts in their own table:
[bom.md](bom.md), and as CSV in `hardware/bom/`. The Thonk parts of Spore, Orchid, Moss and
Mycelium are summed into one order in [bom/thonk-order.md](../../bom/thonk-order.md).

---

## Firmware notes

The firmware is in `firmware/`; [firmware/README.md](../firmware/README.md)
describes it. What it does with this hardware:

- libDaisy v9.0.0 with the Daisy bootloader, the program in SRAM
  (BOOT_SRAM), so writing presets to the QSPI flash never stalls the audio.
- **Display:** its own ST7789 driver (`src/display_daisy.cc`): SPI1 transmit
  only at 12.5 MHz with DMA, CS as a GPIO, a 170 × 320 RGB565 frame in
  SDRAM sent as dirty rows, column offset 35, backlight PWM on TIM4 CH4. The
  orientation and the init sequence are unverified until the first power-up.
- **Controls:** a 4 kHz timer (TIM3) bit-bangs the chain with ~125 ns settle
  waits per edge on the long SR_CLK / SR_LOAD lines (GPIO speed LOW);
  debouncing, EC11 quadrature decoding and 16-level LED PWM in software.
  `tools/check_pins.py` checks the pins and the chain's bit order against
  `circuit.py`.
- **MIDI:** USART1 receive only, set up on its registers (D13 stays the
  display's reset), one interrupt per byte with its arrival time.
- **Presets:** in the QSPI flash below the program (0x00000–0x3FFFF):
  settings and the live state in wear-levelled rings, 64 presets of 512
  bytes.
- **CV:** four ADC channels, offset calibration from the setup page
  (CV ZERO accepts 0.42–0.58 of full scale, about ±2 V), nominal scale
  −25.38 V per unit. 1 % parts and the 3V3A reference spread the real scale
  by up to about 6 % between modules.
- **Debounce:** a switch must hold for 24 scans (6 ms): the EC11's contacts
  bounce for up to 2 ms, tact switches up to about 5 ms.

