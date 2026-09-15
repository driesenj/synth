# Hardware pinout — v2

Design reference for the v2 build: 4051 injection incl. the button board,
two CV/gate pairs plus an AUX CV, audio out, MIDI in, clock in, base-pitch
and tune knobs, looper LED. Built and verified so far: the muxes (`inject.cpp`, `muxtest`, `demo`),
the mapping tables, and the I²C board (§2) with the keybed and the button
board scanning through it. The rest is design only.

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
| D34   | 34   | **CV select**      | input-only, no internal pull-up: 10 k to 3.3 V, slide switch to GND. Level: open = channel A, closed = B. Panic moved to STOP |
| D35   | 35   | **Clock in**       | input-only. BC549 collector (transistor on the op-amp board, §7), 10 k to 3.3 V here. Falling edge = rising edge at the jack |
| D32   | 32   | Mux B S0           | → 1 k → 4051 B pin 11                                                                   |
| D33   | 33   | Mux B S1           | → 1 k → 4051 B pin 10                                                                   |
| D25   | 25   | **AUX out**        | DAC1 → 100 k → TL072 B2 in+ (§6). Loop phase for now; clock/reset or automation later    |
| D26   | 26   | **Gate 2 out**     | → 100 k → TL072 B1 in+ (§6). Digital use of DAC2                                        |
| D27   | 27   | Mux A S0           | → 1 k → 4051 A pin 11                                                                   |
| D14   | 14   | Mux A S1           | → 1 k → 4051 A pin 10                                                                   |
| D12   | 12   | **leave open**     | strapping: must be low at boot (flash voltage select)                                   |
| D13   | 13   | Mux A S2           | → 1 k → 4051 A pin 9                                                                    |
| GND   | —    | ground             |                                                                                         |
| VIN   | —    | +5 V in            | J1 5 V → 1N5818 → here, 10 µF to GND. The diode is on this board, not the power board   |

### Right header (top to bottom)

| Label | GPIO | Function                             | Wiring                                                                                                                      |
| ----- | ---- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| D23   | 23   | **Gate 1 out**                       | → 100 k → TL074 A2 in+ (pin 5). 1 M from that input to GND — not 100 k, that halves the gate (§6)                          |
| D22   | 22   | I²C SCL _(soldered)_                 | → I²C board J1 (§2). The 2.2 k pull-ups live on that board; none at this end                                               |
| TX0   | 1    | USB-UART TX                          | on-board bridge                                                                                                             |
| RX0   | 3    | USB-UART RX                          | on-board bridge                                                                                                             |
| D21   | 21   | I²C SDA _(soldered)_                 | → I²C board J1 (§2). The 2.2 k pull-ups live on that board; none at this end                                               |
| D19   | 19   | Mux INH (both 4051s)                 | → 1 k → pin 6 of both. 10 k from this GPIO to the DevKit's 3V3 pin (the mux board carries only 5 V): INH floats high during boot, so nothing is injected until firmware says so        |
| D18   | 18   | **Looper LED, blue**                 | 100 Ω → LED. Currently _(soldered)_ to MCP23017 INTB — remove, the firmware polls                                           |
| D5    | 5    | **Looper LED, green**                | 100 Ω → LED. Currently _(soldered)_ to MCP23017 INTA — remove. Strapping pin, but an LED to GND is fine (Lolin32 precedent) |
| TX2   | 17   | MIDI out                             | → 10 Ω → DIN pin 5. DIN pin 4 ← 33 Ω ← 3.3 V. DIN pin 2 = GND                                                               |
| RX2   | 16   | **MIDI in**                          | ← 4N35 collector (pin 5). 1 k to 3.3 V                                                                                      |
| D4    | 4    | Mux B S2                             | → 1 k → 4051 B pin 9                                                                                                        |
| D2    | 2    | **Looper LED, red**                  | 330 Ω → LED. Shares the on-board LED. Strapping pin: an LED to GND is fine                                                  |
| D15   | 15   | optional                             | strapping. 10 k to GND silences the ROM boot log on UART0; otherwise leave open                                             |
| GND   | —    | ground                               |                                                                                                                             |
| 3V3   | —    | 3.3 V out                            | I²C pull-ups, MCP23017, MCP4725, pots, input pull-ups, INH pull-up                                                          |

No spare GPIO: 25/26 went to gate 2 and AUX. GPIO15 (with its 10 k to GND)
is the last output-capable pin; the MCP23017 has two spare inputs on GPB (§3).

INH pull-up: the README says 5 V. 3.3 V is enough — 74HCT inputs switch at
2.0 V — and it keeps 5 V off a GPIO while the ESP32 boots, when GPIO19 is a
floating input. It sits at the ESP32 end, GPIO19 to 3V3, since the mux
board has no 3.3 V; through the 1 k the mux still sees ~3.3 V.

### ESP32 board connectors

The DevKit's carrier. Its GND net is one node and J1's GND is its only wire
to the star (§8); every other cable either carries that ground or none.

| Conn | Pins                                                                        | On this board                                                                                                       |
| ---- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| J1   | 1 GND, 2 5 V in                                                             | 5 V → 1N5818 (band towards the DevKit) → VIN; 10 µF VIN to GND. Any of the power board's 5 V headers can feed it    |
| J2   | 1 D19 INH, 2 D13 A·S2, 3 D14 A·S1, 4 D27 A·S0                               | 10 k D19 → 3V3. The 1 k series resistors are on the mux board                                                       |
| J3   | 1 D33 B·S1, 2 D32 B·S0, 3 D4 B·S2                                           |                                                                                                                     |
| J4   | 1 D34, 2 GND                                                                | CV select slide switch, SPST to GND, read as a level. 10 k D34 → 3V3                                                |
| J5   | 1 VN, 2 GND, 3 3V3                                                          | tune pot. 100 nF VN → GND                                                                                           |
| J6   | 1 VP, 2 3V3, 3 GND                                                          | base pitch pot. Not J5's order, deliberately (stripboard); a swapped cable only reverses a pot. 100 nF VP → GND     |
| J7   | 1 D35 clock in, 2 D23 gate 1, 3 D26 gate 2, 4 D25 AUX                       | to the op-amp board, signal only, no ground. 10 k D35 → 3V3; the BC549 stage is on the op-amp board                 |
| J8   | 1 D21 SDA, 2 D22 SCL, 3 3V3, 4 GND                                          | to the I²C board. No pull-ups here                                                                                  |
| J9   | 1 GND, 2 D18 blue, 3 D5 green, 4 D2 red                                     | 100 Ω, 100 Ω, 330 Ω in series here. Pin↔colour is config.h's business; the 330 Ω stays on the red leg               |
| J10  | 1 GND (DIN 2 + chassis lug, joined at the socket), 2 D17 (DIN 5), 3 3V3 (DIN 4) | 10 Ω in the D17 leg, 33 Ω in the 3V3 leg. Three wires; the case is plastic, nothing else grounds the shell      |
| J11  | 1 4N35 pin 2 (DIN 5), 2 4N35 pin 1 (DIN 4)                                  | 220 Ω in the pin-1 leg; 1N4148 across 4N35 pins 1–2, cathode to pin 1; pin 4 → GND; pin 5 → D16 with 1 k → 3V3; pin 6 open |
| —    | D15                                                                         | optional 10 k → GND, silences the ROM boot log                                                                      |

---

## 2. I²C bus

| Device                                | Address            | Supply                     |
| ------------------------------------- | ------------------ | -------------------------- |
| MCP23017 — keybed + button board scan | 0x20 (A0–A2 = GND) | 3.3 V                      |
| MCP4725 #1 — CV1 DAC (SparkFun)       | 0x60 (ADDR open)   | 3.3 V through 10 Ω + 10 µF |
| MCP4725 #2 — CV2 DAC (SparkFun)       | 0x61 (ADDR closed) | 3.3 V through 10 Ω + 10 µF |

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

### The I²C board

Both chips, the pull-ups and nothing else, on one stripboard. Four wires to
the DevKit are the whole of its connection to the ESP32 — nothing on the
board needs a GPIO, so the INTA/INTB wires do not come along (they become
the LED wires, §7). The keybed, the button board and the CV pair are the
other cables; the matrix ones split by port, columns on one side of the chip
and rows on the other, which is how the strips fall.

| Conn | Pins                         | Goes to                                                                                                                                                                                                   |
| ---- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| J1   | 1 SDA, 2 SCL, 3 3V3, 4 GND   | ESP32 board J8, same order. Keyed so 3V3 and GND cannot swap. ≤ 30 cm: 2.2 k allows ~160 pF of bus at 400 kHz, ~80 pF is spoken for                                                                      |
| J2   | 1–8 = columns 0–7            | keybed strobes → GPA (pins 21–28), one column per bit in the order `COL_BIT` in config.h gives — as built, not in order (§3). The column numbers are `position_map.cpp`'s and stay put; the table follows the wires, `COLS_ON_PORT_A = 1` |
| J3   | 1–6 = rows 5, 4, 3, 2, 1, 0  | keybed returns → six bits of GPB (pins 1–8), `ROW_BIT` in config.h says which (§3); the two bits no row landed on are the spare inputs                                                                     |
| J4   | 7, one IDC on the flat cable | button board, pinned by the cable's own order. Each wire joins the MCP23017 pin that already carries the same keybed net — P3–P7 are keybed columns 5, 4, 3, 6, 7, P14/P15 are rows 2 and 0 — so the pins follow `COL_BIT` / `ROW_BIT`: the as-built list is in §5 |
| J5   | 1 CV1, 2 —, 3 CV2            | to the op-amp board, TL074 A1 and A4 (§6). Lies along the OUT strip, centre pin pulled, strip cut under it. Signal only: the 100 k and 1 nF sit at the TL074, no ground in this cable                    |

One GND net on the board — the GND rail — carrying U1 pin 10, pins 15–17,
C1–C3 and the breakouts' GND, and J1's GND is the only wire that leaves it,
to a DevKit GND pin. J2–J4 have no ground (the matrix is passive contacts)
and J5 carries none either: the CV wires' return is the star on the power
board (§8). A second ground path out of this board would give the ESP32's
return current a route through the analogue ground, the daisy-chain §8
forbids. The record-button LED wires (§7) go from the ESP32 board to the
button board directly; this board carries matrix nets only.

| Ref    | Part                       | From                           | To            | Watch                                                                                                                                                                       |
| ------ | -------------------------- | ------------------------------ | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| U1     | MCP23017, DIP-28           |                                |               | pinout in §3                                                                                                                                                                |
| U2, U3 | SparkFun MCP4725 breakouts |                                |               | standing on straight headers. I²C PU jumper cut on both (both traces). U2 ADDR open → 0x60 = CV1; U3 ADDR closed → 0x61 = CV2. Their own 100 nF is on the breakout      |
| R1, R2 | 2.2 k                      | SDA, SCL                       | 3V3 rail      | the only pull-ups on the bus. The ESP32 board carries none; two sets would make 1.1 k, 3 mA per line — the whole I²C sink budget                                        |
| R3     | 10 k                       | U1 pin 18 RESET                | 3V3 rail      | mandatory                                                                                                                                                                   |
| R4     | 10 Ω                       | 3V3 rail                       | VCC strip     | both breakouts share the VCC strip, so one RC serves both. Only that strip hangs behind it; R1–R3 pull to the rail in front, or bus current would modulate the DAC references |
| C1     | 100 nF                     | U1 pin 9 VDD                   | U1 pin 10 VSS | adjacent strips, straight across                                                                                                                                            |
| C2     | 10 µF                      | VCC strip (behind R4)          | GND rail      | electrolytic (+ to VCC) or MLCC. 1.6 kHz corner on the DAC supply, which is also the reference; the breakout's 100 nF covers HF                                             |
| C3     | 10 µF                      | 3V3 rail                       | GND rail      | across the adjacent rails next to J1. In front of R4, so it stiffens the rail the pull-ups switch against, not the DAC reference. Optional; first thing to add if CV shows scan-rate noise |
| links  | 9, insulated wire          |                                |               | listed under the strip map                                                                                                                                                  |
| open   |                            | U1 pins 11, 14, 19, 20, and two of 1 / 4 / 8 |               | NC, NC, INTB, INTA, and the two GPB bits no row landed on (§3). The firmware pulls the whole return port up internally (`ROW_GPPU = 0xFF`), so they do not float                |

**Stripboard.** Strips horizontal, numbered from the chip's top strip _r_.
U1 sits across them, notch up, pins 1–14 down the left, 15–28 up the right,
so pin _n_ shares its strip with pin 29 − _n_ until the cut under the body.
Everything that needs a rail is at the bottom of the chip, so the two rails
are the first two strips below it, uncut and full width. The breakouts stand
on the five strips below the rails, both on the same strips, turned so VCC
is nearest the rails; the order printed on the SparkFun board is
OUT GND SCL SDA VCC — if yours reads differently only the link targets
change. About 24 strips × 20 holes, corners free for standoffs.

```
strip   left of U1                       U1  L | R      right of U1
r+0     J2.1 col 0                      GPB0 | GPA7    —
r+1     J2.2 col 1                      GPB1 | GPA6    —
r+2     J2.3 col 2                      GPB2 | GPA5    J3.1 row 5
r+3     J2.4 col 3    J4 P5             GPB3 | GPA4    J3.2 row 4
r+4     J2.5 col 4    J4 P4             GPB4 | GPA3    J3.3 row 3
r+5     J2.6 col 5    J4 P3             GPB5 | GPA2    J3.4 row 2    J4 P14
r+6     J2.7 col 6    J4 P6             GPB6 | GPA1    J3.5 row 1
r+7     J2.8 col 7    J4 P7             GPB7 | GPA0    J3.6 row 0    J4 P15
r+8     C1 ┐  link → r+14               VDD  | INTA    —
r+9     C1 ┘  link → r+15               VSS  | INTB    —
r+10    —                               NC   | RESET   R3 → r+14
r+11    R2 → r+14,  link → r+13         SCL  | A2      link → r+15
r+12    J1.1 SDA,  R1 → r+14            SDA  | A1      link → r+15
r+13    J1.2 SCL  (link from r+11)      NC*  | A0      link → r+15
r+14    J1.3  ═══ 3V3 rail, uncut, full width ═══ C3 ═══════════════
r+15    J1.4  ═══ GND rail, uncut, full width ═══ C3 ═══════════════
r+16    U2 VCC  · R4 → r+14 · C2 → r+15 · · · · · · · · · · U3 VCC
r+17    U2 SDA  · link → r+12 (left)  · · · · · · · · · · · U3 SDA
r+18    U2 SCL  · link → r+13 (left)  · · · · · · · · · · · U3 SCL
r+19    U2 GND  · link → r+15 · · · · · · · · · · · · · · · U3 GND
r+20    U2 OUT ─── J5.1 CV1 ─╫cut╫─ J5.3 CV2 ─────────────── U3 OUT
```

As built, the keybed cable went on the other way round from this map: the
eight column wires are on the GPA side (pins 21–28) and the six row wires on
the GPB side, neither group in the map's order. The firmware follows —
`COLS_ON_PORT_A = 1`, `COL_BIT = {3, 4, 2, 6, 1, 5, 0, 7}`,
`ROW_BIT = {3, 2, 4, 5, 6, 1}` in config.h; §3 has the same as a pin table,
every entry confirmed by pressing its key. The self test's pin-pair mode `p`
names the two chip pins behind any key without assuming either table — it is
how a wire on an unexpected pin is found — and the monitor `m` prints the
physical pair behind each lit cell, which is how a table is checked. J4's
seven wires join the keybed nets where those now are, so the J4 links drawn
above are the map's, not the board's — §5 has the pins.

Cuts, 16: one under U1 on each of r+0 … r+13; a second on r+13 just left
of pin 14, so the NC pin sits on nothing (*); one on r+20 under J5's pulled
centre pin, between the two OUT pins. Nothing else — the rails and the
breakouts' VCC/SDA/SCL/GND strips run full width, shared.

Links, 9: r+8 L → r+14 (VDD), r+9 L → r+15 (VSS), r+11 L → r+13 L (SCL to
J1's strip, which puts J1 in J8's order), r+11 R / r+12 R / r+13 R → r+15
(A2, A1, A0), r+17 → r+12 L (breakout SDA), r+18 → r+13 L (breakout SCL),
r+19 → r+15 (breakout GND). Several hop a rail: insulated wire.

J4 is one IDC header, so its seven pins land wherever the header goes and
links carry them to the strips shown; the join with the keybed nets is
still free, it is the same strip. C1 spans pins 9/10 directly, R1/R2 reach
the 3V3 rail from pins 12/11 in two and three pitches, R3 in four, R4 in
two. Placement beyond this is the builder's; the map is one that works.

Acceptance, USB only, toy unplugged: `selftest` check 1 idle high (the
pull-ups are on the board now, so J1 must be plugged in), check 2 lists
0x20, 0x60 and 0x61 and says `ok`, check 5 clean at 400 kHz for all three,
check 7 ok for both DACs, and `m` lights the same cells as before the move,
named — plus (3,0) play, (4,0) record and (3..7, 2) samba, blues, rock,
techno, disco. Do not re-run the `n`/`c`/`w` sweep. With the op-amp board
on: `v` steps CV1/CV2 through 0–4.95 V for a meter, `o` is the octave
calibration of §6.

Bring-up lesson from this board: the expander answered the scan and went
silent ~30 ms into traffic, came back after a minute idle, and answered at
0x27 with the breakouts unplugged — A0–A2 were floating, pumped high by the
SCL/SDA halves of the same strips. VDD, VSS, RESET and the rail all metered
correctly throughout. The breakouts had no ground either, which is what
stalled the ESP32's I²C controller on their reads (error 263 after 1 s).
Every ground on this board is a deliberate link; check them by continuity
to the GND rail before anything else.

Program each MCP4725's EEPROM once to 0x000, normal mode — `e` in the self
test — so CV is 0 V from power-up instead of whatever the EEPROM holds while
the ESP32 boots. Check 7 says whether it has been done.

---

## 3. MCP23017 — scan

`COLS_ON_PORT_A = 1`; which bit of each port carries which column and row is
`COL_BIT` / `ROW_BIT` in config.h. As built:

| Pin     | Signal      | Connection                                                                                                                  |
| ------- | ----------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1–8     | GPB0–GPB7   | row returns, keybed side of the cut, on six of the eight bits: GPB1 row 5, GPB2 row 1, GPB3 row 0, GPB4 row 2, GPB5 row 3, GPB6 row 4. GPB0 and GPB7 are spare inputs, pulled up by the firmware. Button-board rows P15 / P14 join rows 0 / 2 here (§5) |
| 9 / 10  | VDD / VSS   | 3.3 V / GND                                                                                                                 |
| 12 / 13 | SCL / SDA   | bus                                                                                                                         |
| 15–17   | A0–A2       | GND → 0x20                                                                                                                  |
| 18      | RESET       | 10 k to 3.3 V (mandatory)                                                                                                   |
| 19 / 20 | INTB / INTA | unused — remove the wires to GPIO18/5                                                                                       |
| 21–28   | GPA0–GPA7   | column strobes, keybed side of the cut: GPA1 column 4, GPA2 column 2, GPA3 column 0, GPA4 column 1, GPA5 column 5, GPA6 column 3, GPA0 column 6, GPA7 column 7. Button-board wires P3–P7 join the five matching columns here (§5) |

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

The cable used to land on the blob PCB, i.e. the blob side of the cut, so
the blob saw these buttons and the ESP32 did not. It is intercepted now: the
cable lands on the I²C board (J4), each wire on the MCP23017 pin that already
carries the same keybed net. The five column wires are shared between the
rhythm buttons and record/play, so it was all seven or none.

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
`position_map.cpp` as cc28–34, and scan like any other position.

The rhythm and record/play cells fix which column each P-wire is, and the
record/play pair agrees with the rhythm pair (P4 = c4, P5 = c3 both times).
So the move was these seven joints, on the expander — each wire onto the
pin that already carries the same keybed net, which as built
(`COLS_ON_PORT_A = 1`, columns on GPA, rows on GPB, bits per `COL_BIT` /
`ROW_BIT`, §3) is:

| wire | net | MCP23017 pin |
|---|---|---|
| P3 | column 5 | GPA5, pin 26 |
| P4 | column 4 | GPA1, pin 22 |
| P5 | column 3 | GPA6, pin 27 |
| P6 | column 6 | GPA0, pin 21 |
| P7 | column 7 | GPA7, pin 28 |
| P14 | row 2 | GPB4, pin 5 |
| P15 | row 0 | GPB3, pin 4 |

Verified with the self test's `p` mode, one button at a time, then `m`: it
lights (3,0) for play, (4,0) for record, and (3..7, 2) for samba, blues,
rock, techno, disco. The two spare GPB inputs and mux B Y6/Y7 stay free.

After interception the blob only sees these buttons when the firmware injects
them: rhythm buttons are forwarded (40 ms one-shot) so the toy's patterns keep
working through the audio out; record and play are not forwarded — they
become looper controls.

**Record-button LED**: trace its two wires, disconnect them from the blob's
driver, and drive it from the ESP32 (§7). If it is replaced by an RGB LED, the
same holds with three resistors.

---

## 6. Op-amps — TL074 + TL072

TL074 (DIP-14): V+ = pin 4 → +12 V (after the bead), V− = pin 11 → −12 V.
100 nF from each to GND at the chip.

| Amp | Pins out / in− / in+ | Role                           | Circuit                                                                                                                                                                                                 |
| --- | -------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1  | 1 / 2 / 3            | CV out, ×1.5                   | in+ ← 100 k ← MCP4725 OUT, 1 nF in+ to GND. in− ← 20 k to GND, 10 k from out. out → 1 k → CV jack tip                                                                                                   |
| A2  | 7 / 6 / 5            | Gate 1 out, ×1.5               | in+ ← 100 k ← GPIO23, **1 M** in+ to GND. in− ← 20 k to GND, 10 k from out. out → 1 k → gate 1 jack. 0 / 4.5 V                                                                                          |
| A3  | 8 / 9 / 10           | Audio out, difference amp ×1.5 | TDA2822 pin 1 (OUT1) → 10 µF → 100 k → in−; 150 k from out to in−, 100 pF across it. TDA2822 pin 3 (OUT2) → 10 µF → 100 k → in+; 150 k from in+ to GND. out → 10 k level pot → wiper → 1 k → audio jack |
| A4  | 14 / 13 / 12         | CV2 out, ×1.5                  | in+ ← 100 k ← MCP4725 #2 OUT (0x61), 1 nF in+ to GND. in− ← 20 k to GND, 10 k from out. out → 1 k → CV2 jack tip                                                                                        |

TL072 (DIP-8), same rails: V+ = pin 8, V− = pin 4, 100 nF each to GND.
Pinout: 1 out A, 2 in− A, 3 in+ A, 5 in+ B, 6 in− B, 7 out B.

| Amp | Pins out / in− / in+ | Role                    | Circuit                                                                                                                   |
| --- | -------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| B1  | 1 / 2 / 3            | Gate 2 out, ×1.5        | in+ ← 100 k ← GPIO26, 1 M in+ to GND. in− ← 20 k to GND, 10 k from out. out → 1 k → gate 2 jack. 0 / 4.5 V                 |
| B2  | 7 / 6 / 5            | AUX out, ×1.5           | in+ ← 100 k ← GPIO25 (DAC1), 1 M in+ to GND, 1 nF optional. Same feedback. out → 1 k → AUX jack. ~0.1–4.4 V from the 8-bit DAC |

The 1 M at each gate/AUX input holds the input at 0 V when the ESP32 board
is unplugged. Against the 100 k series it is ×0.91, hence 4.5 V rather than
4.95. The earlier 100 k there was a ÷2 — that circuit gives a 2.5 V gate.

Clock-in's BC549 stage (§7) lives on this board too, on its ground, with the
jack; only its collector line leaves, to GPIO35 on the ESP32 board's J7.

Audio tap: the **speaker terminals**, TDA2822 pins 1 and 3, taken
differentially. Everything the toy sends to the speaker is there — blob audio
and the microphone, at the toy's own balance, with the toy's volume applied —
however the toy mixes them internally, so nothing needs tracing. The ~2.5 V
DC on both terminals cancels in the difference and the coupling caps remove it
regardless. With the blob on 5 V the bridge delivers ~8 Vpp at full toy
volume, ×1.5 → ~12 Vpp, inside the TL074's swing. Keep the TDA2822 powered; the speaker may stay
connected or not; the mic stays wired to the toy exactly as it is.

If a separate mic level is wanted later: another TL072 as a mic preamp with
its own pot, summed into A3, and the blob tapped at the blob side of the
coupling capacitor into pin 7 (IN1+) instead. An envelope follower on A3's
output (peak detector, 1 µF, 100 k release) is the other candidate for that
chip: a 0–6 V CV that follows the toy and the mic.

CV scale is not trimmed in hardware. Gain is fixed at 1.5 with 1 % resistors
and the firmware constants `CV_CODES_PER_SEMITONE` / `CV2_CODES_PER_SEMITONE`
absorb the 3.3 V rail and resistor tolerances, one per channel: play two
notes an octave apart, meter the CV, adjust until the difference is 1.000 V. Residual: the TL074's ~3 mV input offset ≈ 4 cents.

---

## 7. Discrete blocks

**Clock in** — jack tip → 10 k → BC549 base; 100 k base to GND; 1N4148 base
to GND (cathode at the base) to clamp negative swings; emitter → GND;
collector → GPIO35 with 10 k to 3.3 V. The transistor and its base network
sit on the op-amp board with the jack, on that board's ground; the 10 k
pull-up sits on the ESP32 board, the only place with 3.3 V — the INH
arrangement again. 0–5 V or 0–10 V pulses both work; the transistor inverts,
firmware uses the falling edge. BC549 pinout, flat face
towards you, legs down: C B E.

**MIDI in** — DIN pin 4 → 220 Ω → 4N35 pin 1 (anode); DIN pin 5 → pin 2
(cathode); 1N4148 across pins 1–2, cathode to pin 1; pin 4 (emitter) → GND;
pin 5 (collector) → GPIO16 with 1 k to 3.3 V; pin 6 (base) open. 1 k, not
10 k: the load sets how hard the phototransistor saturates and so how fast it
turns off — at 10 k it takes tens of µs against 32 µs bits; 1 k asks 3.3 mA,
inside its CTR at ~5 mA LED current. DIN pin 2 is
_not_ connected at the input. The 4N35 is marginal at 31.25 kbaud; if notes go
missing, an H11L1 is the replacement (pinout differs — check).

**MIDI out** — DIN pin 4 ← 33 Ω ← 3.3 V; DIN pin 5 ← 10 Ω ← GPIO17; DIN
pin 2 ← GND.

**Looper LED** (in the record button) — common cathode to GND; one resistor
per colour, never a shared one: 330 Ω on red (≈ 4 mA), 100 Ω on green and on
blue (≈ 3 mA). As wired: red on GPIO2, green on GPIO5, blue on GPIO18;
`config.h` follows the wiring, only the 330 Ω is colour-bound. Green and blue need the
smaller resistors because their forward voltage leaves only ~0.3 V of
headroom at 3.3 V; balance the colours with PWM in firmware. For a bicolour
LED drop blue. If green/blue stay too dim, use a common-anode LED with the
anode on 5 V and the ESP32 sinking through the resistors, logic inverted.
To keep the INTA/INTB wires instead, use 25/26 and give up the DAC
reservation.

**Pots** — base pitch and tune: 10 k linear, one end 3.3 V, other end GND,
wiper → GPIO36 / GPIO39 with 100 nF to GND. Level: 10 k in the A3 output path.

**CV select** — GPIO34, 10 k to 3.3 V, SPST slide switch to GND, so the
knob position shows where the keys go: open = channel A (CV1/gate 1),
closed = B (CV2/gate 2). Firmware reads it as a level, at boot and on change.
Was the panic button.

**Panic** — a long press (≥ 1 s) of the toy's STOP button, keybed position
(7, 0), cc26 in `position_map.cpp`; a short press keeps its toy function and
stops the looper. It arrives through the expander, so it cannot rescue a dead
I²C bus — the driver's own re-init (`I2C_FAIL_LIMIT`) covers that, and a full
wedge is the power switch.

**MCP4725 breakouts** — VCC ← 3.3 V through 10 Ω, 10 µF at the board; GND;
SDA/SCL on the bus. #1: ADDR open → 0x60, OUT → 100 k → TL074 pin 3 (CV1).
#2: ADDR closed → 0x61, OUT → 100 k → TL074 pin 12 (CV2). Both live on the
I²C board, §2; the 100 k and the 1 nF belong at the TL074.

---

## 8. Power

A separate power board. Nets in **bold**.

```
XLR 2 (+12IN) ── FB1 ──┬── +12A ── C1 47 µF + C2 100 nF ──────────────── J5 → TL074 pin 4
                       └── R1 10 Ω ── VREG ── C3 470 µF + C4 100 nF ── 7805 IN
                                                                      7805 OUT = 5V ──┬── J3 → 4051 VCC
                                                        C5 10 µF + C6 100 nF          ├── J4 → blob (battery contacts)
                                                                                      └── J2 → ESP32 board J1 → D2 1N5818 → VIN
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
| D2                     | 1N5818, **on the ESP32 board**  | anode: its J1 5 V                                                          | cathode: DevKit VIN | band towards the DevKit. Not on the power board, so any 5 V header can feed the ESP32 |
| C7                     | 100 µF/16 V                     | 5V (+)                                                                     | GND (−)        | at J4, bulk for the blob's audio peaks; optional if the toy PCB has its own           |
| C9                     | 47 µF/25 V                      | **GND (+)**                                                                | **−12IN (−)**  | positive leg to ground                                                                |
| C10                    | 100 nF                          | −12IN                                                                      | GND            |                                                                                       |
| LED1a, LED1b + R2      | 2 LEDs in series, 3.3 k         | +12A → R2 → LED1a anode; LED1a cathode → LED1b anode; LED1b cathode → GND  |                | optional, ≈ 2 mA through both                                                         |
| LED2a, LED2b + R3      | 2 LEDs in series, 3.3 k         | GND → LED2a anode; LED2a cathode → LED2b anode; LED2b cathode → R3 → −12IN |                | optional, ≈ 2 mA. Chain reversed: first anode on ground                               |
| LED3a + R4, LED3b + R5 | 2 separate branches, 1.5 k each | 5V (raw) → R → LED anode; cathode → GND, twice                             |                | optional, ≈ 2 mA each. 1 k for blue/white. No series pair on 5 V: not enough headroom |

| Header      | Pins             | Goes to                                                                                                                                         |
| ----------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| J2 ESP32    | 5V, GND          | ESP32 board J1 → 1N5818 → DevKit VIN, GND                                                                                                       |
| J3 muxes    | 5V, GND          | both 4051 VCC (16), GND (7, 8) — raw side, so USB never powers them                                                                             |
| J4 blob     | 5V, GND          | the toy's battery contacts, upstream of its power switch so the switch still works as a toy mute. Never fit batteries again with this connected |
| J5 analogue | +12A, GND, −12IN | TL074 pins 4 / — / 11, jack sleeves                                                                                                             |

Never daisy-chain ground between boards; the analogue ground meets the
digital ground only through J5. Everything at 3.3 V (MCP23017, MCP4725, opto
pull-up, clock transistor, pots, LED) hangs off the DevKit's 3V3 pin.

The ground net is a tree with the star at the root: J2–J5 are its four
branches and every other board or part is a leaf off one of them, with one
ground wire to its parent. Two ground paths out of any board make a loop, and
the current that circulates in it lands on whatever signal shares the wire.
The ESP32 board is one node — every GND pin on it is the same net and J2 is
its only wire to the star — so the question per cable leaving it is only
whether the cable carries a ground conductor at all: yes when the far end has
no ground of its own, no when it already has one.

| Cable from the ESP32 board | Ground conductor | Why                                                                                                                                     |
| -------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| I²C board                  | yes              | the board's only ground (§2)                                                                                                            |
| CV select switch           | yes              | the switch returns to the ground its 10 k pull-up references                                                                            |
| Base pitch and tune pots   | yes              | dividers across the ADC's own 3V3 and GND                                                                                               |
| Looper LED                 | yes              | common cathode returns to the ground of the GPIOs driving it                                                                            |
| MIDI out                   | yes              | DIN pin 2 and the chassis lug, joined at the socket. Plastic case, so nothing else grounds the shell                                     |
| MIDI in                    | none             | isolated by the 4N35; the receiver never grounds the shield                                                                             |
| Clock in                   | none, tip only   | the jack sleeve is on J5 with the other three (§9). The transistor stage grounds on the ESP32 board, its own reference                 |
| Gate 1, gate 2, AUX        | none             | the op-amp board grounds at J5 and the 1 M to GND at each input is its reference. A ground here is a second ESP32↔analogue path        |

The case is plastic, so there is no panel ground: the jack sleeves meet only
at J5. (A metal panel would join every sleeve and DIN shell into one node,
which would then have to reach the star at exactly one point.)

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
the 7805 through the 1N5818 on the ESP32 board. Both land at ≈ 4.7 V, neither can push into the
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
| DIN-5 MIDI out                                                                | 2 → GND; 4 → 33 Ω → 3V3; 5 → 10 Ω → GPIO17; 1, 3 open; chassis lug → pin 2. Resistors on the ESP32 board (J10), three wires |
| DIN-5 MIDI in                                                                 | 4 → 220 Ω → 4N35 pin 1; 5 → 4N35 pin 2; 1, 2, 3 and chassis lug open — the receiver never grounds the shield. Two wires |
| 3.5 mm mono ×4                                                                | tip = signal, sleeve = GND: CV, gate, clock in, audio out                                                               |

DIN pin numbers are stamped on the solder side: 2 is the centre lug, 4 and 5
flank it, 1 and 3 are the outer pair. Swapping 4 and 5 on either socket is
silent, not destructive — swap the wires back.

---

## 10. `config.h` delta (not applied yet)

```c
// unchanged: PIN_SDA/SCL, PIN_MIDI_TX/RX, PIN_MUX_*, MCP_ADDR
// PIN_PANIC goes away: GPIO34 becomes PIN_CV_SELECT, a slide switch read as
// a level. Panic = long press of STOP (cc26), through the scan.

static constexpr int     PIN_GATE        = 23;    // channel A
static constexpr int     PIN_GATE2       = 26;    // channel B, DAC2 used as GPIO
static constexpr int     PIN_AUX         = 25;    // DAC1: loop phase; clock/reset or automation later
static constexpr int     PIN_CV_SELECT   = 34;    // input-only, external 10 k; low = channel B
static constexpr int     PIN_CLOCK_IN    = 35;    // input-only, falling edge
static constexpr int     PIN_POT_BASE    = 36;    // ADC1_CH0
static constexpr int     PIN_POT_TUNE    = 39;    // ADC1_CH3
static constexpr int     PIN_LED_RED     = 2;
static constexpr int     PIN_LED_GREEN   = 5;     // as wired on J9
static constexpr int     PIN_LED_BLUE    = 18;
static constexpr uint8_t DAC_ADDR        = 0x60;  // MCP4725 #1, CV1
static constexpr uint8_t DAC2_ADDR       = 0x61;  // MCP4725 #2, CV2 (ADDR jumper closed)

// N_ROWS becomes 8 only if the button board's P14/P15 turn out to be new rows.

// 3.3 V / 4096 = 0.806 mV per code, x1.5 = 1.209 mV; 83.33 mV per semitone.
// Nominal 68.96. Calibrate each channel against a meter, see section 6.
static constexpr float   CV_CODES_PER_SEMITONE  = 68.96f;
static constexpr float   CV2_CODES_PER_SEMITONE = 68.96f;
```
