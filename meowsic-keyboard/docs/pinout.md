# Hardware pinout — v2

Design reference for the v2 build: 4051 injection incl. the button board,
CV/gate out, audio out, MIDI in, clock in, base-pitch and tune knobs, looper
LED. Built and verified so far: the muxes (`inject.cpp`, `muxtest`, `demo`)
and the mapping tables. The rest is design only.

Board: ESP32 DevKit V1, 30-pin. Labels as printed on the board. _(soldered)_
marks connections that exist today; everything else is to be wired.

---

## 1. ESP32

### Left header (top to bottom, USB at the bottom)

| Label | GPIO | Function           | Wiring                                                                                  |
| ----- | ---- | ------------------ | --------------------------------------------------------------------------------------- |
| EN    | —    | reset              | on-board button                                                                         |
| VP    | 36   | **Base pitch pot** | ADC1_CH0, input-only. 10 k lin pot between 3.3 V and GND, wiper here, 100 nF to GND     |
| VN    | 39   | **Tune pot**       | ADC1_CH3, input-only. Same as above                                                     |
| D34   | 34   | Panic button       | input-only. 10 k to 3.3 V, switch to GND                                                |
| D35   | 35   | **Clock in**       | input-only. BC549 collector, 10 k to 3.3 V. Falling edge here = rising edge at the jack |
| D32   | 32   | Mux B S0           | → 1 k → 4051 B pin 11                                                                   |
| D33   | 33   | Mux B S1           | → 1 k → 4051 B pin 10                                                                   |
| D25   | 25   | reserved           | DAC1 — keep for a future trigger/CV (or LED, see §7)                                    |
| D26   | 26   | reserved           | DAC2                                                                                    |
| D27   | 27   | Mux A S0           | → 1 k → 4051 A pin 11                                                                   |
| D14   | 14   | Mux A S1           | → 1 k → 4051 A pin 10                                                                   |
| D12   | 12   | **leave open**     | strapping: must be low at boot (flash voltage select)                                   |
| D13   | 13   | Mux A S2           | → 1 k → 4051 A pin 9                                                                    |
| GND   | —    | ground             |                                                                                         |
| VIN   | —    | +5 V in            | from the 7805 through the SS14                                                          |

### Right header (top to bottom)

| Label | GPIO | Function                             | Wiring                                                                                                                      |
| ----- | ---- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| D23   | 23   | **Gate out**                         | → 100 k → TL074 A2 in+ (pin 5). 100 k from that input to GND                                                                |
| D22   | 22   | I²C SCL _(soldered)_                 | 2.2 k to 3.3 V                                                                                                              |
| TX0   | 1    | USB-UART TX                          | on-board bridge                                                                                                             |
| RX0   | 3    | USB-UART RX                          | on-board bridge                                                                                                             |
| D21   | 21   | I²C SDA _(soldered)_                 | 2.2 k to 3.3 V                                                                                                              |
| D19   | 19   | Mux INH (both 4051s)                 | → 1 k → pin 6 of both. 10 k from this GPIO to the DevKit's 3V3 pin (the mux board carries only 5 V): INH floats high during boot, so nothing is injected until firmware says so        |
| D18   | 18   | **Looper LED, green**                | 100 Ω → LED. Currently _(soldered)_ to MCP23017 INTB — remove, the firmware polls                                           |
| D5    | 5    | **Looper LED, blue** (RGB) or unused | 100 Ω → LED. Currently _(soldered)_ to MCP23017 INTA — remove. Strapping pin, but an LED to GND is fine (Lolin32 precedent) |
| TX2   | 17   | MIDI out                             | → 10 Ω → DIN pin 5. DIN pin 4 ← 33 Ω ← 3.3 V. DIN pin 2 = GND                                                               |
| RX2   | 16   | **MIDI in**                          | ← 4N35 collector (pin 5). 1 k to 3.3 V                                                                                      |
| D4    | 4    | Mux B S2                             | → 1 k → 4051 B pin 9                                                                                                        |
| D2    | 2    | **Looper LED, red**                  | 330 Ω → LED. Shares the on-board LED. Strapping pin: an LED to GND is fine                                                  |
| D15   | 15   | optional                             | strapping. 10 k to GND silences the ROM boot log on UART0; otherwise leave open                                             |
| GND   | —    | ground                               |                                                                                                                             |
| 3V3   | —    | 3.3 V out                            | I²C pull-ups, MCP23017, MCP4725, pots, input pull-ups, INH pull-up                                                          |

No spare GPIO. 25/26 are the only reserve; the MCP23017's GPA6/GPA7 are spare
unless the button board needs them (§5).

INH pull-up: the README says 5 V. 3.3 V is enough — 74HCT inputs switch at
2.0 V — and it keeps 5 V off a GPIO while the ESP32 boots, when GPIO19 is a
floating input. It sits at the ESP32 end, GPIO19 to 3V3, since the mux
board has no 3.3 V; through the 1 k the mux still sees ~3.3 V.

---

## 2. I²C bus

| Device                                | Address            | Supply                     |
| ------------------------------------- | ------------------ | -------------------------- |
| MCP23017 — keybed + button board scan | 0x20 (A0–A2 = GND) | 3.3 V                      |
| MCP4725 — CV DAC (SparkFun breakout)  | 0x60               | 3.3 V through 10 Ω + 10 µF |

Pull-ups: one set for the whole bus, 2.2 k from SDA and from SCL to 3.3 V,
next to the MCP23017. Pull-ups only — the bus is open-drain — and only to
3.3 V. The SparkFun breakout carries its own 4.7 k pair behind the three-pad
solder jumper on its back: cut the two traces between the pads so the board
contributes nothing. (Leaving it closed gives 1.5 k net, which works; the
4.7 k alone is borderline at 400 kHz — self-test check 5 shows it.) Never
power the breakout from 5 V — its pull-ups would lift SDA/SCL above the
ESP32's 3.6 V limit, and its I²C threshold of 0.7·VDD would stop seeing
3.3 V as high. The MCP23017's RESET 10 k and the matrix return lines are
separate matters: RESET gets its own 10 k to 3.3 V; the returns get no
external pull-ups at all.

---

## 3. MCP23017 — scan

`COLS_ON_PORT_A = 0`.

| Pin     | Signal      | Connection                                                                                                                  |
| ------- | ----------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1–8     | GPB0–GPB7   | column strobes 0–7: keybed cable, keybed side of the cut. Button-board wires P3–P7 join the five matching columns here (§5) |
| 9 / 10  | VDD / VSS   | 3.3 V / GND                                                                                                                 |
| 12 / 13 | SCL / SDA   | bus                                                                                                                         |
| 15–17   | A0–A2       | GND → 0x20                                                                                                                  |
| 18      | RESET       | 10 k to 3.3 V (mandatory)                                                                                                   |
| 19 / 20 | INTB / INTA | unused — remove the wires to GPIO18/5                                                                                       |
| 21–26   | GPA0–GPA5   | row returns 0–5, keybed side of the cut                                                                                     |
| 27, 28  | GPA6, GPA7  | spare, or button-board rows P14/P15 if those are new rows (§5)                                                              |

---

## 4. Injection — 2× 74HCT4051 (DIP-16)

Both muxes share one COM node: mux A picks a column, mux B picks a row, and
together they are one switch between that column and that row — one virtual
key. Mono by construction, which matches the decision to treat the blob as a
single-note instrument.

Pinout (both chips): 13 Y0, 14 Y1, 15 Y2, 12 Y3, 1 Y4, 5 Y5, 2 Y6, 4 Y7,
3 Z (COM), 11 S0, 10 S1, 9 S2, 6 INH, 16 VCC, 7 VEE, 8 GND.

| Pin              | Mux A (columns)                                         | Mux B (rows)                                                                                            |
| ---------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Y0–Y7            | the eight blob-side column lines, any order             | Y1, Y2, Y4, Y5, Y6, Y7: the six blob-side row lines. Y0, Y3: tied to GND — never selected by the tables |
| Z (3)            | tied to mux B pin 3                                     | tied to mux A pin 3                                                                                     |
| S0 / S1 / S2     | GPIO27 / 14 / 13 via 1 k (as wired; `config.h` follows) | GPIO32 / 33 / 4 via 1 k (as wired)                                                                      |
| INH (6) | GPIO19 via 1 k; 10 k to 3.3 V at the ESP32 end | same net                                                                                                |
| VCC (16)         | 5 V, 100 nF                                             | 5 V, 100 nF                                                                                             |
| VEE (7), GND (8) | GND                                                     | GND                                                                                                     |

Channel order need not match the expander's: `MUX_COL_OF[c]` and
`MUX_ROW_OF[r]` in `config.h` give the channel that reaches the same blob line
as keybed column c / row r, found with the mapping walk in the README
(bring-up step 4). Only the kind must be right — all eight strobe lines on
mux A, all return lines on mux B.

Sequence, from the README: INH high → set both selects → INH low → hold
≥ 30 ms (the blob polls every 10–20 ms) → INH high before the next change.
Changing selects with INH low briefly connects wrong pairs and the blob may
latch them as presses.

The 1 k series resistors protect the unpowered 4051 inputs in the USB-only
state; 74HCT, not HC, so 3.3 V selects are valid highs.

---

## 5. Button board (the 7-wire cable)

Seven wires, all matrix nets: P3–P7 are five of the eight column lines, P14
and P15 are two row lines. Buttons at the crossings:

| Button | Column | Row |
| ------ | ------ | --- |
| rock   | P3     | P14 |
| blues  | P4     | P14 |
| samba  | P5     | P14 |
| techno | P6     | P14 |
| disco  | P7     | P14 |
| record | P4     | P15 |
| play   | P5     | P15 |

Today the cable lands on the blob PCB, i.e. the blob side of the cut, so the
blob still sees these buttons and the ESP32 does not. Intercepting means
moving the cable to the keybed side: each wire joins the MCP23017 pin that
already carries the same net. The five column wires are shared between the
rhythm buttons and record/play, so it is all seven or none.

Measured with the mapping walk, then the buttons identified by ear. Keybed
coordinates with the mux channel that reaches each line in parentheses; MIDI
numbers as in `position_map.cpp` (toy pitch, A3 = 57):

| keybed | c0 (6) | c1 (4) | c2 (1) | c3 (5) | c4 (0) | c5 (7) | c6 (3) | c7 (2) |
|---|---|---|---|---|---|---|---|---|
| r0 (1) | tempo + | tempo − | vol + | play cc29 | record cc28 | vol − | spare | STOP cc26 |
| r1 (6) | A5 81 | A#5 82 | B5 83 | bells cc21 | piano cc20 | C6 84 | meow cc22 | organ cc23 |
| r2 (2) | banjo cc24 | music cc25 | catface cc27 | samba cc32 | blues cc31 | rock cc30 | techno cc33 | disco cc34 |
| r3 (5) | C#5 73 | D5 74 | D#5 75 | F#5 78 | F5 77 | E5 76 | G5 79 | G#5 80 |
| r4 (7) | A3 57 | A#3 58 | B3 59 | D4 62 | C#4 61 | C4 60 | D#4 63 | E4 64 |
| r5 (4) | F4 65 | F#4 66 | G4 67 | A#4 70 | A4 69 | G#4 68 | B4 71 | C5 72 |

Rows 0 and 2 are where the keybed-side scan saw empty cells: they hold the
buttons whose contacts live on the blob side. Volume and tempo are matrix
positions after all — their traces just run to the main PCB — so they keep
working natively and are reachable by injection (`POS_VOL_UP` and friends in
`config.h`), but will never scan. The button-board seven are in
`position_map.cpp` already as cc28–34; they scan once the board is moved.

The rhythm and record/play cells fix which column each P-wire is, and the
record/play pair agrees with the rhythm pair (P4 = c4, P5 = c3 both times).
So the move is these seven joints, on the expander (`COLS_ON_PORT_A = 0`:
columns on GPB, rows on GPA):

| wire | net | MCP23017 pin |
|---|---|---|
| P3 | column 5 | GPB5, pin 6 |
| P4 | column 4 | GPB4, pin 5 |
| P5 | column 3 | GPB3, pin 4 |
| P6 | column 6 | GPB6, pin 7 |
| P7 | column 7 | GPB7, pin 8 |
| P14 | row 2 | GPA2, pin 23 |
| P15 | row 0 | GPA0, pin 21 |

GPA6/7 and mux B Y6/Y7 stay free. After the move, the matrix monitor must
light (3,0) for play, (4,0) for record, and (3..7, 2) for samba, blues, rock,
techno, disco.

After interception the blob only sees these buttons when the firmware injects
them: rhythm buttons are forwarded (40 ms one-shot) so the toy's patterns keep
working through the audio out; record and play are not forwarded — they
become looper controls.

**Record-button LED**: trace its two wires, disconnect them from the blob's
driver, and drive it from the ESP32 (§7). If it is replaced by an RGB LED, the
same holds with three resistors.

---

## 6. TL074 (DIP-14)

V+ = pin 4 → +12 V (after the bead), V− = pin 11 → −12 V. 100 nF from each
to GND at the chip.

| Amp | Pins out / in− / in+ | Role                           | Circuit                                                                                                                                                                                                 |
| --- | -------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1  | 1 / 2 / 3            | CV out, ×1.5                   | in+ ← 100 k ← MCP4725 OUT, 1 nF in+ to GND. in− ← 20 k to GND, 10 k from out. out → 1 k → CV jack tip                                                                                                   |
| A2  | 7 / 6 / 5            | Gate out, ×1.5                 | in+ ← 100 k ← GPIO23, 100 k in+ to GND. in− ← 20 k to GND, 10 k from out. out → 1 k → gate jack. 0 / 4.95 V                                                                                             |
| A3  | 8 / 9 / 10           | Audio out, difference amp ×1.5 | TDA2822 pin 1 (OUT1) → 10 µF → 100 k → in−; 150 k from out to in−, 100 pF across it. TDA2822 pin 3 (OUT2) → 10 µF → 100 k → in+; 150 k from in+ to GND. out → 10 k level pot → wiper → 1 k → audio jack |
| A4  | 14 / 13 / 12         | spare                          | in+ to GND, in− tied to out (parked as a follower)                                                                                                                                                      |

Audio tap: the **speaker terminals**, TDA2822 pins 1 and 3, taken
differentially. Everything the toy sends to the speaker is there — blob audio
and the microphone, at the toy's own balance, with the toy's volume applied —
however the toy mixes them internally, so nothing needs tracing. The ~2.5 V
DC on both terminals cancels in the difference and the coupling caps remove it
regardless. With the blob on 5 V the bridge delivers ~8 Vpp at full toy
volume, ×1.5 → ~12 Vpp, inside the TL074's swing. Keep the TDA2822 powered; the speaker may stay
connected or not; the mic stays wired to the toy exactly as it is.

If a separate mic level is wanted later: A4 as a mic preamp with its own pot,
summed into A3, and the blob tapped at the blob side of the coupling capacitor
into pin 7 (IN1+) instead.

CV scale is not trimmed in hardware. Gain is fixed at 1.5 with 1 % resistors
and the firmware constant `CV_CODES_PER_SEMITONE` absorbs the 3.3 V rail and
resistor tolerances: play two notes an octave apart, meter the CV, adjust until
the difference is 1.000 V. Residual: the TL074's ~3 mV input offset ≈ 4 cents.

---

## 7. Discrete blocks

**Clock in** — jack tip → 10 k → BC549 base; 100 k base to GND; 1N4148 base
to GND (cathode at the base) to clamp negative swings; emitter → GND;
collector → GPIO35 with 10 k to 3.3 V. 0–5 V or 0–10 V pulses both work; the
transistor inverts, firmware uses the falling edge. BC549 pinout, flat face
towards you, legs down: C B E.

**MIDI in** — DIN pin 4 → 220 Ω → 4N35 pin 1 (anode); DIN pin 5 → pin 2
(cathode); 1N4148 across pins 1–2, cathode to pin 1; pin 4 (emitter) → GND;
pin 5 (collector) → GPIO16 with 1 k to 3.3 V; pin 6 (base) open. DIN pin 2 is
_not_ connected at the input. The 4N35 is marginal at 31.25 kbaud; if notes go
missing, an H11L1 is the replacement (pinout differs — check).

**MIDI out** — DIN pin 4 ← 33 Ω ← 3.3 V; DIN pin 5 ← 10 Ω ← GPIO17; DIN
pin 2 ← GND.

**Looper LED** (in the record button) — common cathode to GND; one resistor
per colour, never a shared one: red ← 330 Ω ← GPIO2 (≈ 4 mA), green ← 100 Ω ←
GPIO18 (≈ 3 mA), blue ← 100 Ω ← GPIO5 (≈ 3 mA). Green and blue need the
smaller resistors because their forward voltage leaves only ~0.3 V of
headroom at 3.3 V; balance the colours with PWM in firmware. For a bicolour
LED drop blue. If green/blue stay too dim, use a common-anode LED with the
anode on 5 V and the ESP32 sinking through the resistors, logic inverted.
To keep the INTA/INTB wires instead, use 25/26 and give up the DAC
reservation.

**Pots** — base pitch and tune: 10 k linear, one end 3.3 V, other end GND,
wiper → GPIO36 / GPIO39 with 100 nF to GND. Level: 10 k in the A3 output path.

**Panic** — GPIO34, 10 k to 3.3 V, switch to GND.

**MCP4725 breakout** — VCC ← 3.3 V through 10 Ω, 10 µF at the board; GND;
SDA/SCL on the bus; OUT → 100 k → TL074 pin 3. ADDR jumper open → 0x60.

---

## 8. Power

A separate power board. Nets in **bold**.

```
XLR 2 (+12IN) ── FB1 ──┬── +12A ── C1 47 µF + C2 100 nF ──────────────── J5 → TL074 pin 4
                       └── R1 10 Ω ── VREG ── C3 470 µF + C4 100 nF ── 7805 IN
                                                                      7805 OUT = 5V ──┬── J3 → 4051 VCC
                                                        C5 10 µF + C6 100 nF          ├── J4 → blob (battery contacts)
                                                                                      └── D2 SS14 → 5V_ESP ── J2 → ESP32 VIN
XLR 3 (−12IN) ── C9 47 µF + C10 100 nF ───────────────────────────────── J5 → TL074 pin 11
XLR 1 (GND)   ── ground bus = star; J2–J5 each have their own GND pin
```

| Ref                    | Part                            | From                                                                       | To             | Watch                                                                                 |
| ---------------------- | ------------------------------- | -------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------- |
| J1                     | 3-pin in                        | XLR 1 → GND, XLR 2 → +12IN, XLR 3 → −12IN                                  |                |                                                                                       |
| FB1                    | WE-CBF 600 Ω / 4 A bead         | +12IN                                                                      | +12A           |                                                                                       |
| C1                     | 47 µF/25 V                      | +12A (+)                                                                   | GND (−)        |                                                                                       |
| C2                     | 100 nF                          | +12A                                                                       | GND            |                                                                                       |
| R1                     | 10 Ω 0.5 W                      | +12A                                                                       | VREG           |                                                                                       |
| C3                     | 470 µF/25 V                     | VREG (+)                                                                   | GND (−)        |                                                                                       |
| C4                     | 100 nF                          | VREG                                                                       | GND            | at 7805 pin 1                                                                         |
| U1                     | 7805                            | pin 1 IN = VREG, pin 2 GND, pin 3 OUT = 5V                                 |                | heatsink                                                                              |
| D1                     | 1N4007                          | anode 5V                                                                   | cathode VREG   | band towards VREG; protects the regulator when the input discharges first             |
| C5                     | 10 µF/16 V                      | 5V (+)                                                                     | GND (−)        |                                                                                       |
| C6                     | 100 nF                          | 5V                                                                         | GND            | at 7805 pin 3                                                                         |
| D2                     | SS14                            | anode 5V                                                                   | cathode 5V_ESP | band towards the ESP32                                                                |
| C7                     | 100 µF/16 V                     | 5V (+)                                                                     | GND (−)        | at J4, bulk for the blob's audio peaks; optional if the toy PCB has its own           |
| C9                     | 47 µF/25 V                      | **GND (+)**                                                                | **−12IN (−)**  | positive leg to ground                                                                |
| C10                    | 100 nF                          | −12IN                                                                      | GND            |                                                                                       |
| LED1a, LED1b + R2      | 2 LEDs in series, 3.3 k         | +12A → R2 → LED1a anode; LED1a cathode → LED1b anode; LED1b cathode → GND  |                | optional, ≈ 2 mA through both                                                         |
| LED2a, LED2b + R3      | 2 LEDs in series, 3.3 k         | GND → LED2a anode; LED2a cathode → LED2b anode; LED2b cathode → R3 → −12IN |                | optional, ≈ 2 mA. Chain reversed: first anode on ground                               |
| LED3a + R4, LED3b + R5 | 2 separate branches, 1.5 k each | 5V (raw) → R → LED anode; cathode → GND, twice                             |                | optional, ≈ 2 mA each. 1 k for blue/white. No series pair on 5 V: not enough headroom |

| Header      | Pins             | Goes to                                                                                                                                         |
| ----------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| J2 ESP32    | 5V_ESP, GND      | DevKit VIN, GND                                                                                                                                 |
| J3 muxes    | 5V, GND          | both 4051 VCC (16), GND (7, 8) — raw side, so USB never powers them                                                                             |
| J4 blob     | 5V, GND          | the toy's battery contacts, upstream of its power switch so the switch still works as a toy mute. Never fit batteries again with this connected |
| J5 analogue | +12A, GND, −12IN | TL074 pins 4 / — / 11, jack sleeves                                                                                                             |

Never daisy-chain ground between boards; the analogue ground meets the
digital ground only through J5. Everything at 3.3 V (MCP23017, MCP4725, opto
pull-up, clock transistor, pots, LED) hangs off the DevKit's 3V3 pin.

FB1 handles RF from the ESP32's clocks; R1 + C3 (34 Hz) is what keeps
scan-rate and I²C-burst current off the synth's cable, and is the part that
matters. No bead on −12 V: only the TL074 draws from it. Drop across R1
≈ 1.1 V at 110 mA; the 7805 sees ≈ 10.9 V, delivers ≈ 110 mA → 0.65 W.

The toy ran on 4×AA — 6 V nominal, ~4.4 V when it considers them flat — so
the 7805's 5 V is inside its normal window and needs no dropping or a second
regulator. Keep it at 5 V rather than 6 V: the 74HCT4051 channels cannot pass
signals above their own VCC, so a 6 V blob would need 6 V muxes and
level-shifted selects. If the blob's pitch is supply-dependent it will sit a
few percent below fresh-battery pitch, and stay there.

Two 5 V sources, diode-ORed at VIN: USB through the DevKit's own Schottky,
the 7805 through the SS14. Both land at ≈ 4.7 V, neither can push into the
other, USB cannot reach the blob or the 4051s, and the 7805 cannot reach the
PC. Check the board diode once: USB only, measure VIN — ≈ 4.7 V means it is
there; 5.0 V means the clone omitted it, in which case unplug USB when the PC
is off (it would back-feed the port) but nothing else changes.

USB-only state (synth unplugged): the ESP32, MCP23017 and MCP4725 run; the
blob and the 4051s are dark. Keybed scan, MIDI out and the CV DAC stay
testable on USB alone. Injection, audio and the ±12 V stages need the synth.
With USB unplugged the CP2102 is dark and RX0 sits low — harmless.

USB plugged in while the synth is connected joins the PC ground to the synth
ground through the keyboard. Expect hum on that path, not damage; unplug USB
when not flashing or bridging, or put an ADuM3160-type USB isolator in the
cable.

---

## 9. Connectors

| Connector                                                                     | Pins                                                                                                                    |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| XLR-3, male panel on the keyboard, female panel on the synth, plain mic cable | 1 GND, 2 +12 V, 3 −12 V                                                                                                 |
| DIN-5 MIDI out                                                                | 2 → GND; 4 → 33 Ω → 3V3; 5 → 10 Ω → GPIO17; 1, 3 open; chassis lug → GND. Resistors on the lugs, three wires            |
| DIN-5 MIDI in                                                                 | 4 → 220 Ω → 4N35 pin 1; 5 → 4N35 pin 2; 1, 2, 3 and chassis lug open — the receiver never grounds the shield. Two wires |
| 3.5 mm mono ×4                                                                | tip = signal, sleeve = GND: CV, gate, clock in, audio out                                                               |

DIN pin numbers are stamped on the solder side: 2 is the centre lug, 4 and 5
flank it, 1 and 3 are the outer pair. Swapping 4 and 5 on either socket is
silent, not destructive — swap the wires back.

---

## 10. `config.h` delta (not applied yet)

```c
// unchanged: PIN_SDA/SCL, PIN_MIDI_TX/RX, PIN_MUX_*, PIN_PANIC, MCP_ADDR

static constexpr int     PIN_GATE        = 23;
static constexpr int     PIN_CLOCK_IN    = 35;    // input-only, falling edge
static constexpr int     PIN_POT_BASE    = 36;    // ADC1_CH0
static constexpr int     PIN_POT_TUNE    = 39;    // ADC1_CH3
static constexpr int     PIN_LED_RED     = 2;
static constexpr int     PIN_LED_GREEN   = 18;
static constexpr int     PIN_LED_BLUE    = 5;     // omit for a bicolour LED
static constexpr uint8_t DAC_ADDR        = 0x60;  // MCP4725

// N_ROWS becomes 8 only if the button board's P14/P15 turn out to be new rows.

// 3.3 V / 4096 = 0.806 mV per code, x1.5 = 1.209 mV; 83.33 mV per semitone.
// Nominal 68.96. Calibrate against a meter, see section 6.
static constexpr float   CV_CODES_PER_SEMITONE = 68.96f;
```
