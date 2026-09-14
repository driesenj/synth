# Meowsic MIDI — ESP32 firmware

Firmware for a circuit-bent Bontempi Meowsic cat piano. The toy's 8×6 key matrix
is cut away from its epoxy blob; the ESP32 owns the keybed and re-injects presses
into the blob, so the original meow voice survives while the keys become a real
MIDI controller.

This repository currently implements **build-order step 4 only**: keybed scan →
MIDI out. See [Scope](#scope).

---

## Scope

| Stage | Feature | Status |
|---|---|---|
| 4 | Keybed scan via MCP23017 | Implemented |
| 4 | MIDI note/CC out on 5-pin DIN | Implemented |
| 4 | MIDI out on USB-UART (bridged) | Implemented — `tools/serial_midi_bridge.py` |
| 4 | Mapping sweep for `position_map.cpp` | Implemented — self-test `n`/`c`/`w` |
| 4 | Debounce, ghost rejection, panic, I²C recovery | Implemented |
| 5 | Injection into the blob (2× 74HCT4051) | Injector done (`inject.cpp`), muxes mapped and verified end to end by `muxtest` and `demo`. Not yet called from the scan loop — the firmware still only parks it |
| 6 | MIDI in | Not implemented — UART2 RX is opened but unread |
| 7 | Looper | Not implemented |
| 8 | Transpose / octave / scale quantise | `TRANSPOSE` constant only |

The toy is **silent** in this stage. That is expected: the 14 matrix lines are
cut and nothing is driving the blob yet.

---

## Repository layout

```
platformio.ini
src/
  config.h           pins, timing, MIDI settings — edit this first
  position_map.cpp   (col,row) → note/CC table — edit after the mapping sweep
  mcp23017.h/.cpp    register-level I/O expander driver
  keybed.h/.cpp      column strobe, debounce, ghost rejection, event queue
  midi_out.h/.cpp    3-byte MIDI sender, DIN + USB sinks
  main.cpp           setup, scan loop, event dispatch, panic
  selftest.cpp       MCP23017 bring-up diagnostic (env: selftest, not built
                     into the firmware)
  inject.h/.cpp      the injector: one virtual key through the two 4051s,
                     shared by the firmware and every test below
  muxtest.cpp        74HCT4051 injection diagnostic (env: muxtest, needs no
                     I²C - the expander can be unplugged)
  demo.cpp           loops a tune through the toy's voices (env: demo)
tools/
  serial_midi_bridge.py   forwards UART0 MIDI to a virtual port, for a DAW
  test_bridge.py          regression tests for the bridge's MIDI parser
```

---

## Hardware prerequisites

The firmware assumes the wiring in the design document. Six of those details
will make working firmware look broken if they are wrong.

- **MCP23017 RESET (pin 18) pulled to 3.3 V through 10 kΩ.** Active low, no
  internal pull-up. This is the single most common MCP23017 failure — it works
  on the bench and fails intermittently once the case is closed and the wiring
  moves. The firmware detects the resulting bus loss and re-initialises, but it
  will glitch audibly.
- **2.2 kΩ pull-ups on SDA and SCL to 3.3 V.** The ESP32's internal ~45 kΩ
  pull-ups do not work at the 400 kHz this firmware uses.
- **No external pull-ups on the six return lines.** The MCP23017's 100 kΩ
  internals tolerate up to ~25 kΩ of contact resistance; adding 10 kΩ externals
  drops that to ~2.5 kΩ and makes marginal keys worse.
- **No capacitors on the return lines.** Against 100 kΩ, even 1 nF gives a
  100 µs time constant and the scan samples a rising edge. Debounce is done in
  firmware.
- **10 kΩ from mux `INH` to 3.3 V, and 1 kΩ in series on all seven mux control
  lines.** During the ~300 ms of ESP32 boot every GPIO floats. Without the
  pull-up the cat meows on every reset. The 1 kΩ series resistors also protect
  the unpowered 4051 inputs in the USB-only power state (see below).
- **74HCT4051, not HC.** Plain HC needs 3.5 V V<sub>IH</sub> and will not
  reliably accept 3.3 V selects.

### Panic button

GPIO34 is input-only and has **no internal pull-up**. External 10 kΩ to 3.3 V,
switch to GND, active low. Without the resistor the pin floats and the firmware
fires spurious all-notes-off.

It is on a dedicated GPIO deliberately: if firmware wedges with a mux latched on,
the cat holds a meow indefinitely and matrix controls cannot reach you.

### MIDI DIN output — correction to the BOM

The 220 Ω figure in the design document's BOM is the classic **5 V** value. With
a 3.3 V UART TX the loop current falls to roughly 3 mA, below the 5 mA the
receiver's optocoupler expects. Use one of:

- the MIDI Association's 3.3 V values — **33 Ω on pin 4, 10 Ω on pin 5**, with
  pin 4 tied to **3.3 V**; or
- buffer TX up to 5 V through a spare HCT gate and keep 220 Ω / 220 Ω.

Tying the DIN circuit to **3.3 V rather than the 7805's 5 V** is preferable
here, because it makes the entire scan stage testable on USB power alone.

### Power notes that matter to firmware

With the SS14 fitted, **USB alone powers the ESP32 and the MCP23017 but not the
blob or the muxes.** Since the keybed is passive contacts, the whole of step 4
— scan, debounce, MIDI out — can be developed and flashed with the toy fully
unpowered. Only injection (step 5) needs the 12 V supply up.

Never power the board through an audio jack: TRS shorts ring to sleeve on
insertion.

---

## Pin assignment

| Function | GPIO |
|---|---|
| I²C SDA / SCL | 21, 22 |
| MIDI DIN TX / RX (UART2) | 17, 16 |
| USB-UART TX / RX (UART0) | 1, 3 (via the onboard bridge) |
| Mux A select S0 / S1 / S2 | 13, 14, 27 |
| Mux B select S0 / S1 / S2 | 4, 32, 33 |
| Mux INH (both chips) | 19 |
| Panic button | 34 (input-only, external pull-up) |
| *Reserved:* MCP4922 SCK / MOSI / CS | 18, 23, 5 |
| *Reserved:* internal DAC, modulation CV | 25, 26 |

Avoided: **6–11** (flash) and **0 / 2 / 12 / 15** (strapping). GPIO 25/26 are the
only true DAC pins — do not spend them elsewhere.

---

## Building

### PlatformIO (recommended)

```bash
pio run                              # build both environments
pio run -e esp32dev -t upload        # flash the firmware
pio run -e selftest -t upload        # flash the expander diagnostic
pio run -e muxtest -t upload         # flash the injection-mux diagnostic
pio run -e demo -t upload            # flash the injection demo
pio device monitor -b 115200
```

Four environments: `esp32dev` is the firmware, `selftest` the expander
diagnostic in [step 1](#1-verify-the-expander) (it shares `mcp23017.cpp` with
the firmware), `muxtest` the injection-mux diagnostic in
[step 4](#4-verify-the-injection-muxes), `demo` the tune in
[Demo](#demo). All of them drive the muxes through `inject.cpp`.
`build_src_filter` keeps each one's `setup()`/`loop()` out of the others.

Board is `esp32dev` (ESP32-WROOM-32 DevKitC). WiFi and Bluetooth are never
initialised, so both radios stay powered down; nothing further is needed.

`-DCORE_DEBUG_LEVEL=0` is set because UART0 doubles as a MIDI port.

### Arduino IDE

Copy `src/*.cpp` and `src/*.h` into a sketch folder, rename `main.cpp` to
`<foldername>.ino`, select **ESP32 Dev Module**, and set **Core Debug Level** to
*None*.

---

## Bring-up

### 1. Verify the expander

Do this with **only the MCP23017 wired** — no keybed, no blob, no 12 V. USB
alone powers the ESP32 and the expander, so the whole of this step is a bench
test with the toy unplugged.

```bash
pio run -e selftest -t upload && pio device monitor -b 115200
```

`selftest` is a separate firmware that shares `mcp23017.cpp` with the real one,
so a pass exercises the production driver rather than a throwaway. It runs six
checks and prints a verdict for each:

| # | Check | What only this catches |
|---|---|---|
| 1 | SDA/SCL idle level before I²C starts | A line shorted to GND, or a wedged device |
| 2 | Address sweep 0x03–0x77 | Chip present at the wrong address — A0–A2 not grounded |
| 3 | Write and read back all 9 config registers | The read path; registers sitting at power-on defaults |
| 4 | Walking pattern through the unused output latch | Chip not retaining state — RESET floating or VDD dipping |
| 5 | 2000 reads at 100 kHz, then at 400 kHz | Marginal pull-ups. An ACK test passes without them; 400 kHz does not |
| 6 | Strobe all 8 columns, time a frame | A column shorted to a return; a frame that overruns `SCAN_PERIOD_MS` |

Check 5 is the one worth waiting for. Clean at 100 kHz but dirty at 400 kHz is
the specific signature of missing or too-weak pull-ups — a plain "does it ACK"
test passes on the ESP32's ~45 kΩ internals and tells you nothing.

The banner prints which port is strobes and which is returns, so check it
against your harness before reading anything else.

Then press `m` for the live matrix monitor and **short a strobe pin to a return
pin with a jumper wire**. That is electrically a key press, so the 8×6 grid
should light exactly one cell:

```
        r0 r1 r2 r3 r4 r5      i2c errors: 0
    c0   .  .  .  .  .  .
    c1   .  .  .  .  .  .
    c2   .  X  .  .  .  .    pos=13
```

This validates the entire open-drain-emulation scan path — the part that
actually matters — before a single keybed line is soldered. Other commands are
`r` re-run, `d` register dump, `s` bus stress only.

If the cell that lights is the **transpose** of the one you jumpered, the
strobes and returns are on the opposite ports to `COLS_ON_PORT_A`. Flip the
flag rather than rewiring — see [Which port is which](#which-port-is-which).

The quick version, if you just want a pulse: flash as shipped (`USB_MIDI 0`)
and look for

```
Meowsic MIDI - keybed scan stage
MCP23017 up. Frame period 2 ms.
```

If that loops on `MCP23017 not responding at 0x20`, check RESET, the I²C
pull-ups, and that A0–A2 are grounded — or run the self-test, which will tell
you which of the three it is.

### 2. Map the 48 positions

The shipped `position_map.cpp` is a **placeholder**. It guesses that the 28
piano keys sit on positions 0–27 in pitch order, which the design document
itself calls almost certainly wrong. Until it is replaced, keys produce
arbitrary notes and the 20 buttons produce nothing.

The self-test records the table for you rather than making you transcribe 48
col/row pairs out of a scrolling log. With the keybed connected:

```bash
pio run -e selftest -t upload && pio device monitor -b 115200
```

1. Press `n`, then play the **piano keys one at a time, lowest pitch first**.
   Each press is confirmed as it lands:

   ```
     1: pos 13 (col 2 row 1) -> note 45
     2: pos  7 (col 1 row 1) -> note 46
   ```

2. Press `c`, then press the **buttons** — toe buttons, treble clef, nose,
   face, record, play, volume ±, tempo ±. They become CCs from 20 up.
3. Press `w`. It prints a complete `position_map.cpp` between two markers.
   Paste that over `src/position_map.cpp`.

`z` clears the recording if you lose your place; pressing an already-recorded
position is reported and ignored, so a double-tap cannot shift everything after
it. The sweep runs through `keybed::scan()`, so presses are debounced and
ghost-filtered exactly as the firmware will see them.

Note assignment is **chromatic ascending** from `SWEEP_BASE_NOTE` — A3, the
toy's measured lowest key. If this keybed skips
accidentals, fix the note column afterwards — the col/row half is the part that
is tedious to get right, and that part is now exact.

### 3. Play it into a DAW

The WROOM-32 has no native USB, so it cannot enumerate as a class-compliant
MIDI device. The route is: raw MIDI on UART0 → a bridge on the PC → a virtual
MIDI port → the DAW. An ESP32-S2/S3 would remove every one of those steps.

**Set `USB_MIDI 1`** in `config.h` and reflash the firmware (not the
self-test). UART0 now carries raw MIDI at 115200 instead of text.

**Create a virtual MIDI port.** Windows has no API for making one, so a DAW
cannot be fed without help: install [loopMIDI][loopmidi] and add a port —
naming it `Meowsic` is convenient. macOS and Linux can skip this and use
`--create Meowsic` below.

[loopmidi]: https://www.tobias-erichsen.de/software/loopmidi.html

**Run the bridge:**

```bash
pip install pyserial python-rtmidi
python tools/serial_midi_bridge.py --midi loopMIDI --monitor
```

It finds the board by its USB-UART chip, or takes `--port COM5`. `--list`
shows what it can see; `--monitor` decodes every message as it passes:

```
ch1  note on  A2   ( 45) vel 100
ch1  note off A2   ( 45) vel   0
ch1  cc  64 = 127
```

That is worth leaving on the first time — it tells you whether a silent DAW is
a firmware problem or a routing problem, which is otherwise a guess.

**In FL Studio:** Options → MIDI settings. Under **Input**, select the loopMIDI
port, set Controller type to **Generic controller**, and click **Enable**. The
port has to exist before FL starts, or use the Refresh button. Arm an
instrument and play.

Two things that will look like faults:

- **The serial port is exclusive.** The bridge holds it open, so PlatformIO
  cannot flash while it runs. Stop the bridge first — an upload that hangs on
  `Connecting...` is usually this.
- **Junk at every reset.** The ROM bootloader logs to UART0 and
  `CORE_DEBUG_LEVEL=0` does not suppress it. The bridge drops it (it is ASCII,
  so it is all data bytes with no status byte) and reports the count on exit.
  Suppressing it properly needs GPIO15 strapped, which this design leaves free.

The DIN socket carries the same MIDI either way and needs no host software.

### 4. Verify the injection muxes

Independent of everything above: no I²C, so the expander and the DAC can be
unplugged. The two 4051s do need their 5 V, which USB does not supply — bring
the power board up, or jumper VIN to both VCC pins for the duration.

```bash
pio run -e muxtest -t upload && pio device monitor -b 115200
```

The ESP32 drives the six selects and INH; the result is read one of two ways.

**Blob unpowered, multimeter on the blob-side pads.** Pick a pair — `3` then
`c` selects column 3, row 2 — and `o` closes it. The chosen column pad to the
chosen row pad reads the two on-resistances in series, ~100–300 Ω; any other
pair reads open, and `x` opens everything. Stepping the digits and letters with
the meter attached keeps the pair closed, so walking the channels takes a
minute. This is the check that the eight column channels and six row channels
are on the pads the position map thinks they are.

**Blob powered, listen.** `k` sweeps the piano keys in ascending note order, so
a correctly wired pair of muxes plays a scale from the lowest key up; a wrong
note is a channel on the wrong pad, and the log names the position it was
sent to. `v` presses each button in turn and plays the lowest key after it, so
the instrument buttons are heard changing the voice. `s` walks all 48 positions
in map order.

Two failure signatures worth knowing:

- **`i` makes the toy sound.** It cycles every channel with INH held high for
  three seconds; nothing may sound. If it does, INH is not holding — the 10 kΩ
  pull-up on the INH net is missing, or a select wire and the INH wire are
  swapped.
- **The cat meows on reset.** Same cause: INH must be held high by the pull-up
  while the ESP32 boots and its GPIOs float. Power-cycle with the blob on and
  listen; silence is the pass.

#### Mapping the blob side

Step 2 mapped the keybed side of the cut through the expander. The blob side
went onto the mux channels in whatever order the wires fell, so keybed column
3 and mux A channel 3 are most likely different blob lines. `MUX_COL_OF` and
`MUX_ROW_OF` in `config.h` translate keybed column/row → mux channel, and this
is how they are filled in. It needs a tuner — a phone app held near the
speaker is enough — and takes about fifteen notes.

The digit and letter commands are *raw* mux channels; the sweeps are keybed
positions put through the tables. The log always says which.

1. Blob powered, `muxtest` running. Type `t`: the keybed map as a grid of
   note names, which is what you will look things up in.
2. Type `0` `a` `o`: mux A channel 0 joined to mux B channel 0. Read the
   pitch off the tuner and find it in the grid. Say it is D4, at column 1,
   row 3. Then mux A channel 0 reaches keybed column 1 — `MUX_COL_OF[1] = 0` —
   and mux B channel 0 reaches keybed row 3 — `MUX_ROW_OF[3] = 0`.
3. Type `1` (the row stays `a`), read the pitch, look it up: that names the
   keybed column for channel 1, and its row must again be 3. Continue through
   `7`. A channel that is silent or changes the voice has landed on a button
   or an unmapped cell for this row; try it against another row.
4. Type `0`, then `b`, `c`, `d`, `e`, `f`: the six row channels the same way;
   the column must stay the one found for channel 0.
5. Enter both tables in `config.h`, reflash `muxtest`, type `k`. A clean
   chromatic scale from A2 up means both tables are right, and every sweep
   and the firmware's injector go through them from now on.

If the row does not stay constant while stepping columns (or vice versa), a
blob strobe line is on the row mux or a return on the column mux; that one
wire does need moving. Piano is a fine voice for a tuner; if it struggles
with the decay, re-trigger with `x` `o`.

### Demo

Once `k` plays a scale, this is the reward: Korobeiniki looped through the
toy's voices, one pass each, meow on every other pass. Same hardware as the
mux test — muxes and blob powered, no I²C — and it starts by itself two
seconds after boot.

```bash
pio run -e demo -t upload && pio device monitor -b 115200
```

Space pauses, `s` stops, `+`/`-` change the tempo, `m` locks it to meow, `n`
or `1`–`5` change the voice from the next note, `c` presses the catface,
`t` the toy's STOP. It runs on `inject.cpp` and the tables in `config.h`,
nothing else — which makes it the acceptance test for stage 5: if the tune
is right, the injector, the mux wiring and both mapping tables are right.

Two things it will tell you about the blob that the firmware needs to know:
whether a held key sustains (the long notes of the B section) or every
press is one-shot, and how the meow copes with being retriggered every
200 ms.

---

## Configuration

All in `src/config.h`.

| Constant | Default | Notes |
|---|---|---|
| `USB_MIDI` | `0` | `1` = raw MIDI on UART0, `0` = text log |
| `COLS_ON_PORT_A` | `0` | `1` = strobes on GPA, returns on GPB. `0` = swapped |
| `I2C_HZ` | `400000` | Needs the 2.2 kΩ pull-ups. Do not push to 1 MHz — see below |
| `SCAN_PERIOD_MS` | `2` | 500 Hz frame rate |
| `DEBOUNCE_US` | `5000` | Guard window after each accepted edge |
| `I2C_FAIL_LIMIT` | `10` | Failed frames before panic + re-init |
| `NOTE_CHANNEL` / `CTRL_CHANNEL` | `0` | 0–15 on the wire = 1–16 in a DAW |
| `NOTE_VELOCITY` | `100` | Fixed — one contact per key, no velocity to read |
| `TRANSPOSE` | `0` | Semitones, applied at note-on |

---

## How the firmware works

### Open-drain emulation

MCP23017 outputs are push-pull with no open-drain mode. Driving one column low
and the rest high would short a high driver into a low driver through the
membrane whenever two keys share a row. The driver emulates open-drain with the
**direction register**:

```
COL_OLAT  = 0x00   // written BEFORE COL_IODIR, never changed after
COL_IODIR = 0xFF   // all columns Hi-Z
COL_GPPU  = 0x00   // no pull-ups on columns
ROW_IODIR = 0xFF   // rows are inputs
ROW_GPPU  = 0xFF   // 100k pull-ups on rows
ROW_IPOL  = 0xFF   // a closed contact reads as 1
```

Column *n* is asserted by writing `COL_IODIR = ~(1<<n)`: the pin becomes an
output and, since the latch is already 0, drives low. **The active column is
selected by writing the direction register, not the port register.** Writing
the latch after the direction register glitches the first column assertion.

### Which port is which

`COL_IODIR` and friends are aliases, resolved at compile time by
**`COLS_ON_PORT_A`** in `config.h`. The two ports are electrically identical —
both have the 100 kΩ pull-ups and the input inversion the returns need — so
this follows the harness instead of forcing a rewire:

| `COLS_ON_PORT_A` | 8 strobes | 6 returns |
|---|---|---|
| `1` | GPA0–GPA7 | GPB0–GPB5 |
| `0` *(current)* | GPB0–GPB7 | GPA0–GPA5 |

Nothing outside `mcp23017.h` names a lettered register, so the flag moves the
whole scanner. `static_assert`s in that header fail the build if the two roles
ever land on the same port.

Worth having in front of you when tracing the wiring, because it is the
opposite of what most people assume — **port B is the end nearest pin 1**:

| Pins | Signal | Pins | Signal |
|---|---|---|---|
| 1–8 | GPB0–GPB7 | 21–28 | GPA0–GPA7 |
| 9 / 10 | VDD / VSS | 15–17 | A0–A2 |
| 12 / 13 | SCL / SDA | 18 | RESET |

### Scan timing

Per column: one `COL_IODIR` write plus one `ROW_GPIO` read. On the wire at
400 kHz that is 27 and 36 bit-times, so ≈ 68 µs + 90 µs, and eight columns
≈ 1.26 ms. `COL_IODIR` is released to `0xFF` at the end of each frame.

**That arithmetic is a floor, not a prediction.** It counts only the wire. The
Arduino `Wire` driver adds a semaphore, a command-link allocation and an
`i2c_master_cmd_begin` per transaction, and there are sixteen of them per frame.
Measured on real hardware a frame takes **≈ 2.6 ms**, roughly double the bus
time. Step 6 of the self-test reports the write and read costs separately
against their bus-time floor, so you can see which you are paying for — and a
faster `I2C_HZ` does not help with the half that is driver overhead.

The consequence is that `SCAN_PERIOD_MS = 2` does not describe reality: the
real rate is **≈ 280 Hz, not 500 Hz**. This is a labelling problem rather than
a fault. The scan loop ends in

```c
delay(dt >= SCAN_PERIOD_MS ? 1 : SCAN_PERIOD_MS - dt);
```

so it yields at least 1 ms however long the frame ran, and the FreeRTOS idle
task and task watchdog are fed either way. Setting `SCAN_PERIOD_MS = 3` changes
no timing at all — it only stops the constant lying, and silences the self-test
warning. Raising it further just makes the scan slower. 280 Hz is still several
times the blob's own poll rate.

Row settling is ~30 µs (100 kΩ × ~100 pF), comfortably shorter than the I²C
transaction — **that margin disappears if you raise `I2C_HZ` to 1 MHz.**

### Debounce

Asymmetric by construction: an edge is emitted on the **first** frame that sees
it, then that key is frozen for `DEBOUNCE_US`. Press latency is one frame
(~2 ms); bounce inside the guard window is invisible. An N-of-M frame filter
would have cost four times the latency for no benefit.

### Ghost rejection

The membrane has no diodes, so it has **2-key rollover**. Three closed contacts
forming an L produce a phantom fourth at the corner that completes the
rectangle.

`isGhost()` rejects a new closure at (c, r) when some other column c2 holds both
row r *and* some row that column c also holds — the exact rectangle condition.
This is stricter than the rule in §9.3 of the design document, which rejects any
new press sharing a column with one held key and a row with another; that
version also rejects legitimate presses.

A rejected ghost does **not** stamp the debounce timestamp, so the position is
re-tested every frame and appears the instant one leg of the L is lifted.

This matters most in the looper, where overdubs stack presses that were never
simultaneous.

### Stuck-note protection

- `sounding[48]` records the note number actually sent per position, so note-off
  always matches note-on even if `TRANSPOSE` changes mid-press.
- A failed I²C transaction aborts the frame without updating any state — a read
  that silently returned `0xFF` would look like all six rows pressed, because
  `IPOLB` is inverted.
- `I2C_FAIL_LIMIT` consecutive failed frames trigger a panic and a re-init.
- The panic button sends real note-offs for everything believed to be sounding,
  then CC 120 and CC 123 as a courtesy. Receivers are inconsistent about
  honouring all-notes-off, which is why the explicit note-offs come first.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `MCP23017 not responding` at boot | RESET floating; missing I²C pull-ups; A0–A2 not grounded |
| Works on the bench, fails once the case is closed | RESET pull-up — the classic MCP23017 failure |
| Frequent `I2C recovery` messages | Marginal pull-ups, long unshielded SDA/SCL runs, or a flaky RESET |
| All six rows of one column read pressed | Column line shorted to a return, or a failed read leaking through (should be impossible — the driver checks status) |
| Some keys need a hard press | Contact resistance above ~25 kΩ. Clean the membrane; do **not** add external row pull-ups |
| A fourth note appears when three are held | Ghost rejection is off, or the three keys do not form an L (real 3-key chords on distinct rows and columns are fine) |
| Self-test grid lights the transposed cell | Strobes and returns are on the ports opposite to `COLS_ON_PORT_A`. Flip it — do not rewire |
| Cat meows on reset | Missing 10 kΩ `INH` pull-up to 5 V |
| Nothing on the DIN socket | 3.3 V drive with 220 Ω resistors — see the BOM correction above |
| Junk bytes at every boot | ROM bootloader log on UART0. Expected; the bridge drops them |
| Upload hangs on `Connecting...` | The bridge or a serial monitor still holds the port. Close it |
| DAW sees the port but no notes | Run the bridge with `--monitor`. Messages there but not in the DAW is a routing problem; nothing there is firmware |
| Notes arrive but are the wrong pitches | `position_map.cpp` is still the placeholder — run the sweep in step 2 |
| A note hangs after stopping the bridge | Should not happen; it sends all-notes-off on exit. Press panic, then check the DAW is not also latching |
| Notes stick after a crash | Press panic. If it does not respond, check the 10 kΩ on GPIO34 |

---

## Next steps

Step 5 (injection) is the one to validate in isolation — everything after it is
built on top of working injection.

Two constraints already fixed by the hardware:

- The blob polls each key every 10–20 ms, so **every injected press must be held
  for ≥30 ms.** Time-multiplexed pseudo-polyphony is not viable: treat the blob
  as strictly monophonic, last-note priority.
- The two 4051s share a COM node, so only one virtual press can exist at a time.
  Raise `INH` **before** changing the selects — changing them with the switches
  closed briefly connects wrong row/column pairs, which the blob may latch as
  spurious notes.

Open questions from the design document that affect firmware:

1. ~~Full 48-position map~~ — done, measured by injection; see
   `docs/pinout.md` section 5 and the names in `position_map.cpp`.
2. **One-shot vs sustained meow.** If holding a key does not sustain, the
   injector only needs a 30 ms assert and note-off handling disappears entirely.
   Test this early; it changes the shape of both the injector and the looper.
3. **Does an Rosc pin or ceramic resonator escape the blob?** If so, replacing it
   with an MCU PWM clock makes the whole toy pitch- and speed-controllable over
   MIDI CC. Biggest sonic win available, but reportedly unlikely on this toy.
