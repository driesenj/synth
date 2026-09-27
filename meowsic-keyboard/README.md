# Meowsic MIDI — ESP32 firmware

Firmware for a circuit-bent Bontempi Meowsic cat piano. The toy's 8×6 key matrix
is cut away from its epoxy blob; the ESP32 owns the keybed and re-injects presses
into the blob, so the original meow voice survives while the keys become a real
MIDI controller.

The full firmware is designed in `docs/firmware.md` — feature set, what every
button does now, and the work list it was built from; `docs/tests.md` has
the acceptance run each stage has to pass on the instrument. **All four
stages are implemented.** See [Scope](#scope).

---

## Scope

| Stage | Feature | Status |
|---|---|---|
| — | Keybed scan via MCP23017 | Implemented |
| — | MIDI note/CC out on 5-pin DIN | Implemented |
| — | MIDI out on USB-UART (bridged) | Implemented — `tools/serial_midi_bridge.py` |
| — | Mapping sweep for `position_map.cpp` | Implemented — self-test `n`/`c`/`w` |
| — | Debounce, ghost rejection, panic, I²C recovery | Implemented |
| — | Injection into the blob (2× 74HCT4051) | Implemented — every press is tapped back into the blob from the scan loop through a non-blocking queue in `inject.cpp`; muxes mapped and verified end to end by `muxtest` and `demo` |
| 1 | Panel: the buttons' new functions, long presses, pots, CV select switch, LED | Implemented — `controls.cpp`, `led.cpp` |
| 1 | CV/gate A and B: 1 V/oct, note stack, base pitch and tune, retrigger / legato, glide | Implemented — `cv.cpp`, `router.cpp` |
| 2 | MIDI in, DIN and USB: ch 1 plays the toy and the keys' CV pair, ch 2 the other pair; CCs press the toy's buttons and change settings; bend, sustain, mod wheel | Implemented — `midi_in.cpp`; the bridge carries the DAW's output back to the keyboard |
| 3 | Clock: tap tempo, MIDI clock in and out, the jack; looper: record / overdub / undo / clear, quantise, layers; arpeggiator | Implemented — `clock.cpp`, `looper.cpp`, `arp.cpp` |
| 4 | AUX: eleven shapes on the clock; settings and tempo kept across power cycles | Implemented — `auxout.cpp`, `settings.cpp` |

The 14 matrix lines and the button board are cut from the blob, so the toy
only sounds through the injector: every press the scan sees is tapped back in.
Volume and tempo never left the blob and work as before.

---

## Repository layout

```
platformio.ini
src/
  config.h           pins, timing, MIDI settings — edit this first
  position_map.cpp   (col,row) → note/CC table — edit after the mapping sweep
  mcp23017.h/.cpp    register-level I/O expander driver
  mcp4725.h/.cpp     register-level DAC driver, one instance per CV channel
  keybed.h/.cpp      column strobe, debounce, ghost rejection, event queue
  midi_out.h/.cpp    3-byte MIDI sender, DIN + USB sinks
  midi_in.h/.cpp     both sockets in: two parsers, one handler into the router
  clock.h/.cpp       the tick everything time-based reads: tap tempo, MIDI clock, the jack
  looper.h/.cpp      record / overdub / play / undo / clear, in ticks, through the router
  arp.h/.cpp         the held keys played one at a time on the clock's grid
  router.h/.cpp      one path for every note: toy tap, MIDI out, CV/gate
  cv.h/.cpp          the two CV/gate pairs: note stack, glide, gate mode; AUX
  controls.h/.cpp    the panel: button short/long semantics, pots, switch
  led.h/.cpp         the record-button RGB LED, base colour + blink codes
  settings.h/.cpp    the player-changeable settings and the tempo, in NVS
  auxout.h/.cpp      the AUX output: one of eleven shapes on the clock.
                     Not aux.*: that is a reserved name on Windows
  main.cpp           setup, scan loop, event dispatch, panic
  selftest.cpp       I²C board bring-up diagnostic: expander, both DACs,
                     matrix monitor, CV calibration (env: selftest, not
                     built into the firmware)
  systest.cpp        panel test, every function from the outside: CV/gate/AUX
                     at the jacks, pots, switch, clock, both DIN sockets, LED,
                     keybed, the toy into the audio jack (env: systest)
  inject.h/.cpp      the injector: one virtual key through the two 4051s,
                     shared by the firmware and every test below
  muxtest.cpp        74HCT4051 injection diagnostic (env: muxtest, needs no
                     I²C - the expander can be unplugged)
  demo.cpp           loops a tune through the toy's voices (env: demo)
tools/
  serial_midi_bridge.py   UART0 MIDI <-> virtual ports, both directions, for a DAW
  midi_send.py            sends test messages to the keyboard through the bridge
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

### CV select switch, and where panic went

GPIO34 is input-only and has **no internal pull-up**. External 10 kΩ to 3.3 V,
slide switch to GND, read as a level: open = the keys drive CV/gate A, closed
= B. Without the resistor the pin floats and the keys hop between channels.

Panic is a **long press (≥ 1 s) of the toy's STOP button** now: note-offs for
everything sounding, both gates low, the tap queue flushed. It comes in
through the expander, so it cannot rescue a dead I²C bus — the driver's own
re-init (`I2C_FAIL_LIMIT`) covers that, and a full wedge with a mux latched
on is the power switch.

### MIDI DIN output — correction to the BOM

The 220 Ω figure in the design document's BOM is the classic **5 V** value. With
a 3.3 V UART TX the loop current falls to roughly 3 mA, below the 5 mA the
receiver's optocoupler expects. Use one of:

- the MIDI Association's 3.3 V values — **33 Ω on pin 4, 10 Ω on pin 5**, with
  pin 4 tied to **3.3 V**; or
- buffer TX up to 5 V through a spare HCT gate and keep 220 Ω / 220 Ω.

As built: **47 Ω on pin 4, 22 Ω on pin 5**. Against the receiver's own 220 Ω
that is (3.3 − 1.2) / 289 ≈ 7 mA, comfortably above the 5 mA the loop is
designed around, and the larger values are gentler on a shorted cable than
the spec's. The bigger resistor belongs in the 3.3 V leg, the one a short
would load.

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
| CV select switch | 34 (input-only, external pull-up) |
| Clock in | 35 (input-only, external pull-up) |
| Base pitch / tune pots | 39, 36 (ADC1; as built) |
| Gate 1 / gate 2 | 26, 23 (as built — the plan had them the other way) |
| AUX (8-bit DAC) | 25 |
| LED red / green / blue | 2, 18, 5 |

Avoided: **6–11** (flash) and **0 / 12 / 15** (strapping; 2 and 5 are strapping
pins too, but an LED to ground on them is fine). GPIO25 is one of the two
true DAC pins and is AUX; GPIO26, the other, is spent as gate 2. `docs/pinout.md`
is the reference for all of this.

---

## Building

### PlatformIO (recommended)

```bash
pio run                              # build every environment
pio run -e esp32dev -t upload        # flash the firmware (USB is MIDI)
pio run -e text -t upload            # the same firmware, USB is a text log
pio run -e selftest -t upload        # flash the expander diagnostic
pio run -e systest -t upload         # flash the panel test
pio run -e muxtest -t upload         # flash the injection-mux diagnostic
pio run -e demo -t upload            # flash the injection demo
pio device monitor -b 115200
```

Six environments. `esp32dev` is the firmware and `text` is the same firmware
built with `USB_MIDI 0` — UART0 logs every key, command and state change
instead of carrying MIDI, and `s` on the monitor dumps the state; it is what
the acceptance runs in `docs/tests.md` read. `selftest` is the expander
diagnostic in [step 1](#1-verify-the-i²c-board) (it shares `mcp23017.cpp` and
`mcp4725.cpp` with the firmware), `systest` the panel test in
[step 5](#5-panel-test--every-function-from-the-outside), `muxtest` the
injection-mux diagnostic in [step 4](#4-verify-the-injection-muxes), `demo`
the tune in [Demo](#demo). All of them drive the muxes through `inject.cpp`.
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

### 1. Verify the I²C board

Do this with **the I²C board on its four-wire cable and nothing else powered**
— no blob, no 12 V. USB alone powers the ESP32, the MCP23017 and both MCP4725s
(`docs/pinout.md` §2), so the whole of this step is a bench test with the toy
unplugged. The keybed and button board can stay plugged in.

```bash
pio run -e selftest -t upload && pio device monitor -b 115200
```

`selftest` is a separate firmware that shares `mcp23017.cpp` and `mcp4725.cpp`
with the real one, so a pass exercises the production drivers rather than
throwaways. It runs seven checks and prints a verdict for each:

| # | Check | What only this catches |
|---|---|---|
| 1 | SDA/SCL idle level before I²C starts | A line shorted to GND, or a slave left holding SDA by a corrupted transaction — which it then clocks out, since that state survives an ESP32 reset |
| 2 | Address sweep 0x03–0x77, expecting 0x20, 0x60 and 0x61 | A chip at the wrong address — A0–A2 not grounded, a breakout's ADDR jumper wrong. Two breakouts at one address show as "0x60 present, 0x61 absent" |
| 3 | Write and read back all 9 config registers | The read path; registers sitting at power-on defaults |
| 4 | Walking pattern through the unused output latch | Chip not retaining state — RESET floating or VDD dipping |
| 5 | 2000 reads per device at 100 kHz, then at 400 kHz | Marginal pull-ups. An ACK test passes without them; 400 kHz does not. Reported per device, so one dirty breakout is told apart from a weak bus |
| 6 | Strobe all 8 columns, time a frame | A column shorted to a return; a frame that overruns `SCAN_PERIOD_MS` |
| 7 | Each DAC's state, then four patterns through the fast-mode write | A breakout without VCC through its 10 Ω; an EEPROM that would put CV somewhere other than 0 V at power-up |

Check 5 is the one worth waiting for. Clean at 100 kHz but dirty at 400 kHz is
the specific signature of missing or too-weak pull-ups — a plain "does it ACK"
test passes on the ESP32's ~45 kΩ internals and tells you nothing.

The banner prints which port is strobes and which is returns, so check it
against your harness before reading anything else.

Then press `m` for the live matrix monitor. With nothing plugged in, **short a
strobe pin to a return pin with a jumper wire** — electrically a key press, so
the 8×6 grid lights exactly one cell. With the keybed and button board plugged
in, press keys: each lit cell is named from `position_map.cpp`, which is the
acceptance test for the button board — play must light (3,0), record (4,0),
and samba/blues/rock/techno/disco (3..7, 2):

```
        r0 r1 r2 r3 r4 r5      i2c errors: 0   cv select: A (high)
    c0   .  .  .  .  .  .
    c1   .  .  .  .  .  .
    c3   X  .  .  .  .  .    pos=18 cc29 play
```

This validates the entire open-drain-emulation scan path — the part that
actually matters. `p` is the same monitor with the tables taken away: it
drives each of the 16 pins low in turn and reads the other 15, so a key press
is reported as the two chip pins it joins (`GPA3 x GPB6`) plus what
`COLS_ON_PORT_A` / `COL_BIT` / `ROW_BIT` make of that pair. A wire that landed
on a bit the tables do not list, or on the wrong port, is invisible to `m`
and named by `p` — it is how those three settings are read off a new board.
Other commands are `r` re-run, `d` register dump, `s` bus
stress only, `l` re-run with every check at 100 kHz instead of 400 (passing
at 100 and dying at 400 is pull-ups, cable or an SCL joint, not the chip),
and for the analogue side: `v` steps both DACs through five
levels (0 to 4.95 V nominal at the CV jacks) for a meter; `o` alternates each
DAC between two codes 12 semitones apart — adjust `CV_CODES_PER_SEMITONE` /
`CV2_CODES_PER_SEMITONE` in `config.h` until the jack moves by exactly
1.000 V; `e` programs both EEPROMs to 0 so CV is 0 V from power-up, once.

If the cell that lights is the **transpose** of the one you jumpered, the
strobes and returns are on the opposite ports to `COLS_ON_PORT_A`. Flip the
flag rather than rewiring — see [Which port is which](#which-port-is-which).

The quick version, if you just want a pulse: flash as shipped (`USB_MIDI 0`)
and look for

```
Meowsic MIDI - the full firmware (docs/firmware.md)
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

**Flash the default build** (`pio run -e esp32dev -t upload`): UART0
carries raw MIDI at 115200 in both directions. The `text` environment is the
one with the log instead.

**Create two virtual MIDI ports.** Windows has no API for making one, so a
DAW cannot be reached without help: install [loopMIDI][loopmidi] and add
**two** ports, `Meowsic out` (keyboard → DAW) and `Meowsic in` (DAW →
keyboard). Two, because every writer on a loopMIDI port reaches every
reader: on a single port the bridge would read the keyboard's own notes
straight back and the toy would play everything twice. The bridge refuses
that arrangement. Name them with words, not numbers — rtmidi appends an
index to port names on Windows, so `loopMIDI Port 1` and `loopMIDI Port 0`
are one port. macOS and Linux can skip all this and use `--create Meowsic`
below, which makes both.

[loopmidi]: https://www.tobias-erichsen.de/software/loopmidi.html

**Run the bridge:**

```bash
pip install pyserial python-rtmidi
python tools/serial_midi_bridge.py --midi "Meowsic out" --midi-in "Meowsic in" --monitor
```

It finds the board by its USB-UART chip, or takes `--port COM5`. `--list`
shows what it can see; `--monitor` decodes every message as it passes,
`<-` marking the ones on their way to the keyboard:

```
ch1  note on  A3   ( 57) vel 100
ch1  note off A3   ( 57) vel   0
ch1  cc  20 = 127
  <- ch1  note on  C4   ( 60) vel 100
  <- ch1  cc 102 = 127
```

That is worth leaving on the first time — it tells you whether a silent DAW is
a firmware problem or a routing problem, which is otherwise a guess. Without
`--midi-in` the bridge is one-way, as before.

**Without a DAW**, `tools/midi_send.py` sends known messages to the keyboard
through the same return port — `note 57`, `cc 102 127`, `bend 8191`,
`sustain 57 60`, `panic` — which is how `docs/tests.md` checks MIDI in.

Octave names are a convention, not a fact: the bridge (like scientific pitch
notation and most DAWs) calls MIDI 60 C4, so the toy's lowest key, 57, is A3
— 220 Hz. FL Studio calls 60 C5 and shows the same key as A4. The number is
what both agree on.

**In FL Studio:** Options → MIDI settings. Under **Input**, select `Meowsic
out`, set Controller type to **Generic controller**, and click **Enable**;
arm an instrument and play. Under **Output**, select `Meowsic in`, enable it
and give it a port number; a channel's **MIDI Out** plugin set to that port
on MIDI channel 1 then plays the toy and the keys' CV pair from the piano
roll, on channel 2 the other CV pair. The ports have to exist before FL
starts, or use the Refresh button. Keep the DAW's MIDI echo / thru off for
the Meowsic ports: what it sends is played, not returned.

Two things that will look like faults:

- **The serial port is exclusive.** The bridge holds it open, so PlatformIO
  cannot flash while it runs. Stop the bridge first — an upload that hangs on
  `Connecting...` is usually this.
- **Junk at every reset.** The ROM bootloader logs to UART0 and
  `CORE_DEBUG_LEVEL=0` does not suppress it. The bridge drops it (it is ASCII,
  so it is all data bytes with no status byte) and reports the count on exit.
  Suppressing it properly needs GPIO15 strapped, which this design leaves free.

The DIN sockets carry the same MIDI both ways and need no host software.

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
in map order. `l` and `r` are for the firmware's timing constants: `l` closes
the lowest key for 10 … 150 ms, a second apart, and the shortest closure that
sounds is the blob's key debounce (`INJECT_NOTE_HOLD_MS`, plus margin); `r`
plays it twice with 5 … 100 ms open between, and the shortest gap heard as two
notes is `INJECT_NOTE_GAP_MS`. Both switch to meow first, whose retrigger cuts
the previous meow off, so one note or two is unmistakable.

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

### 5. Panel test — every function from the outside

For the finished instrument: every board cabled, the jacks, pots, CV-select
switch, DIN sockets and the record-button LED on the panel. Rails and toy
on, USB for the monitor. A meter, two 3.5 mm patch cables and a MIDI cable
cover everything; a VCO, a clock source and a MIDI keyboard or DAW make
three of the checks nicer but each of those has a self-contained loopback.

```bash
pio run -e systest -t upload && pio device monitor -b 115200
```

It runs on the production drivers. At boot (and on `r`) it lists the rail
points to meter, checks the expander and both DACs answer and that their
EEPROMs hold 0, scans eight keybed frames, reads the panel inputs at rest —
clock in and MIDI RX must be high through their pull-ups, the switch reports
its position — and cycles the LED in the record button. Then one key per
check:

| Key | Check | How |
|---|---|---|
| `c` | CV1 / CV2 level | both DACs to the next of 0 / 25 / 50 / 75 / 100 % per press; meter the jack tips: 0 → 4.95 V in 1.24 V steps |
| `v` | **1 V/oct calibration** | both CVs alternate 0 and 12 semitones every 4 s; meter one jack and adjust that channel's `CV_CODES_PER_SEMITONE` until the two readings differ by 1.000 V |
| `1`, `2` | gate 1 / gate 2 | toggle; 0 / 4.5 V at the jack |
| `a` | AUX level | next of five levels per press; 0 → 4.5 V within ~0.15 V |
| `g` | **CV/gate as an instrument** | an octave in semitones on CV1 with gate 1 pulsing, then the same on CV2 / gate 2, AUX ramping over each — patch a VCO and an envelope and hear the scale on channel A, then B |
| `s` | CV select switch | flip it within 10 s; the level must change and the new channel is named |
| `p` | pots | turn base pitch and tune each end to end; the range seen is tracked and judged when you stop it (whole travel, stuck wiper, or an end not reaching its rail) |
| `k` | clock in, loopback | patch cable from the **gate 1 jack to the clock-in jack**; gate 1 toggles ten times and GPIO35 must follow it inverted |
| `x` | clock in, external | counts pulses at the jack for 5 s and reports Hz and BPM; or leave the gate-1 patch in with `g` running for a known 4 Hz |
| `b` | keybed and buttons | press everything; each is named as it comes in, and stopping the check lists the mapped positions you missed |
| `m` | MIDI, loopback | a MIDI cable from the out socket to the in socket; twelve bytes out must come back through the opto. Names the slow-turn-off signature if the opto is the problem |
| `o` | MIDI out, real gear | a beacon: C4 on/off every 250 ms out of the DIN socket, for a synth or DAW |
| `n` | MIDI in, real gear | 20 s of whatever arrives at the in socket, decoded — notes, CCs, bend; clock and active sensing counted, not spammed |
| `j` | audio out | a five-note run through the injector: the toy plays it and the audio jack carries it |
| `i` | live inputs | switch, clock, MIDI RX levels and both pots, printed on change |
| `l` | LED | red, green, blue, all three |

Any other key stops whatever is running. `v` replaces `selftest`'s `o` for
calibration now that the jacks exist; both do the same thing.

### 6. Acceptance run

With the hardware proven, `docs/tests.md` checks the firmware's behaviour
stage by stage: the panel's button map, the pots, CV/gate at the jacks,
panic, MIDI out. The `text` environment is the logged part —

```bash
pio run -e text -t upload && pio device monitor -b 115200
```

— and the default build plus the bridge's `--monitor` is the MIDI part.

---

## Configuration

All in `src/config.h`.

| Constant | Default | Notes |
|---|---|---|
| `USB_MIDI` | `0` | `1` = raw MIDI on UART0, `0` = text log |
| `COLS_ON_PORT_A` | `1` | `1` = strobes on GPA, returns on GPB. `0` = swapped |
| `I2C_HZ` | `400000` | Needs the 2.2 kΩ pull-ups. Do not push to 1 MHz — see below |
| `SCAN_PERIOD_MS` | `2` | 500 Hz frame rate |
| `DEBOUNCE_US` | `5000` | Guard window after each accepted edge |
| `RELEASE_US` | `30000` | A key must read open this long, without a closed frame, before its release counts |
| `I2C_FAIL_LIMIT` | `10` | Failed frames before panic + re-init |
| `NOTE_CHANNEL` / `CTRL_CHANNEL` | `0` | 0–15 on the wire = 1–16 in a DAW |
| `NOTE_VELOCITY` | `100` | Fixed — one contact per key, no velocity to read |
| `MIDI_IN_FOLD` | `1` | Notes off the keybed's range are folded by octaves onto it for the toy (`0`: the toy stays silent for them). MIDI out and CV always get the real note |
| `LONG_PRESS_MS` | `1000` | One threshold for every long press: panic, undo, clear, the settings behind the rhythm buttons |
| `CV_ZERO_NOTE` | `45` | The note at 0 V (A2), so A3 — the lowest key — is 1 V with the base pitch pot centred |
| `BASE_PITCH_SEMIS` / `TUNE_SEMIS` | `12` / `0.5` | The pots' ranges, ± this. Base pitch moves MIDI out and CV; tune moves CV only |
| `GATE_RETRIG_MS` | `3` | How long the gate dips on a new note over a held one, in retrigger mode |
| `GLIDE_MS` | `{0, 50, 250}` | Off / short / long, the slew's time constant |
| `POT_ADC_LO` / `POT_ADC_HI` | `150` / `3950` | Where the pot's travel is taken to begin and end: the ESP32 ADC reads 0 and 4095 well before the rails |
| `POT_STEP_HYST` | `0.15` | How far past a semitone boundary the quantised base pitch must read before it steps |
| `POT_BASE_REVERSED` / `POT_TUNE_REVERSED` | `0` / `0` | Flip a pot that runs backwards here instead of rewiring it. Clockwise should raise the pitch on both |
| `LED_LEVEL_RED` / `GREEN` / `BLUE` | `255` / `140` / `140` | Full-scale duty per leg, for colour balance |
| `TICKS_PER_BEAT` / `BEATS_PER_BAR` | `96` / `4` | The clock's resolution, and the bar every source has to assume |
| `CLOCK_PPQN` | `4` | Jack pulses per beat — one per 16th |
| `BPM_MIN` / `BPM_MAX` | `40` / `300` | Tap tempo's range |
| `CLOCK_EXT_TIMEOUT_MS` | `2000` | Silence from an external clock before the internal one resumes at its tempo |
| `TAP_MIN_MS` / `TAP_MAX_MS` | `200` / `2000` | A tap closer than the first is bounce; one further than the second starts a new series |
| `MIDI_CLOCK_OUT` | `1` | MIDI clock, start and stop out whenever the master is not MIDI clock in |
| `LOOP_MAX_EVENTS` / `LOOP_MAX_BEATS` | `1024` / `64` | The store; a recording closes itself at the length limit |
| `LOOP_TAP_LATE_MS` | `40` | A loop tap the toy would play later than this is dropped, for the toy only |
| `ARP_HELD_MAX` / `ARP_GATE_PERCENT` | `16` / `50` | Keys the arp remembers; how much of a step its note lasts |
| `AUX_PULSE_MS` / `AUX_ENV_MS` | `10` / `300` | The clock and reset shapes' pulse; the envelope shape's decay |
| `SETTINGS_SAVE_DELAY_MS` | `2000` | Quiet time after the last change before the NVS write |
| `INJECT_NOTE_HOLD_MS` / `INJECT_NOTE_GAP_MS` | `60` / `40` | A key tap into the blob: closed, then open before the next tap. `muxtest` `l`/`r` find the floor by ear |
| `INJECT_BUTTON_HOLD_MS` / `INJECT_BUTTON_GAP_MS` | `60` / `60` | The same for buttons |
| `INJECT_QUEUE_LEN` | `8` | Taps waiting for the one switch; beyond it presses are dropped |

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
| `1` *(current)* | GPA | GPB |
| `0` | GPB | GPA |

Which *bit* of each port carries which column and row is a second pair of
tables, `COL_BIT` and `ROW_BIT` in `config.h`, so a header that landed one
strip off or a ribbon crimped backwards is also a table edit. As built the
columns are on GPA in no particular order (`COL_BIT = {3, 4, 2, 6, 1, 5, 0,
7}`) and the rows on six bits of GPB (`ROW_BIT = {3, 2, 4, 5, 6, 1}`), the
other two GPB bits spare; `docs/pinout.md` §3 has it as a pin table, with the
entries still to be confirmed marked. The self-test monitor prints the
physical pair behind every lit cell, so a wrong entry shows up as a key that
lights the wrong cell with the right pins named next to it; a wire the tables
miss altogether lights nothing, which is what `p` is for.

Nothing outside `mcp23017.h` names a lettered register or a physical bit, so the flag moves the
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

Asymmetric by construction: a press is emitted on the **first** frame that sees
it, then that key is frozen for `DEBOUNCE_US`. Press latency is one frame
(~2 ms); bounce inside the guard window is invisible. An N-of-M frame filter
would have cost four times the latency for no benefit.

A release is the slow side: it is accepted only after the contact has read
open for `RELEASE_US` (30 ms) with no closed frame in between. The membrane's
contacts are high-resistance — anything over ~25 kΩ against the 100 kΩ
pull-up lands in the MCP23017's undefined input band — so a held key reads
open for a frame now and then, and a tap passes through that band on the way
down and up. Without the filter each dropout is a release and a fresh press:
a note-off/on pair on MIDI, and since the injector taps on every press, a
repeated note from the blob while the key is held and a double from a light
tap. Note-off arrives 30 ms late, which nothing hears.

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

### Injection

Every press is **one-shot** to the blob: a held key does not sustain, and a
new press cuts the previous note off and starts the next (measured with the
demo). So the injector never needs a release — a key-down queues one tap,
key-up is MIDI's business only, and the blob's monophony is simply the truth
of what it hears.

A tap is the switch closed for `INJECT_*_HOLD_MS`, then open for
`INJECT_*_GAP_MS` before the next one. The hold has to outlast the blob's key
debounce, not just its 10–20 ms poll — 30 ms closures are ignored, 60 ms ones
play; the gap is what makes two taps of the same key two notes instead of one
long press. Notes get 60/40 (the demo's shortest note and its release), buttons
60/60. `muxtest`'s `l` and `r` sweeps play one key at ever longer holds and
ever longer gaps so the real floor of each can be heard and the constants
trimmed to it.

There is one switch, so taps queue (`inject::queueTap`) and `inject::service`
plays them out from the loop without blocking the 2 ms scan. A chord comes
out as a fast arpeggio in press order — the mono constraint made audible
rather than hidden by dropping notes. The queue holds eight; past that,
presses are dropped rather than arriving half a second late. Panic and I²C
recovery flush it and open the switch.

The voice buttons and catface are forwarded as before. The other buttons are
the firmware's now — `docs/firmware.md` section 2 has the map — and only
reach the toy when their function says so: the rhythm cycle taps the next
rhythm, STOP taps the toy's STOP, a long ♪ taps the demo song.

### The router

Every note, whoever plays it, goes through `router::noteOn` and gets the
same three things: a tap into the toy at the key's own pitch, a note on MIDI
out, and CV/gate — on the pair the CV select switch names for the keys, MIDI
channel 1 and the arpeggiator, on its own pair for a loop. MIDI channel 2
drives the other pair straight through `cv::`, without the pots.

The base pitch pot transposes MIDI out and CV by ±12 semitones — the toy
plays its own pitch regardless — in semitone steps with *quantise pitch* on
(samba), continuously with it off; the tune pot adds ±50 cents to CV only.
Both apply on both pairs, to everything except MIDI channel 2's direct
notes, so a loop keeps its pitch when the switch moves away from it.
Turning either while a key is held moves the CV under it, which is the point
of the continuous mode. The ESP32's ADC is noisy and dead at both ends, so
the pots are sampled at 100 Hz through a smoothing filter, the travel is
clipped at `POT_ADC_LO` / `POT_ADC_HI`, and the quantised pitch steps only
once the reading is `POT_STEP_HYST` of a semitone past the boundary.

### CV / gate

Each channel keeps its held notes in press order, last-note priority: the
newest sounds, release it and the one under it comes back with the gate
still high. Pitch is 1 V/oct from `CV_ZERO_NOTE` (A2 at 0 V), so the keybed
spans 1–3.25 V with the pot centred and the pot's octave either way stays
inside the DAC. *Gate mode* (blues, long) picks what a new note over a held
one does: retrigger dips the gate for `GATE_RETRIG_MS` so an envelope
restarts, legato leaves it high. *Glide* (samba, long) slews the pitch with a
time constant of `GLIDE_MS`, always — a note after a gap slides in from the
last pitch, portamento the SH-101 way. The DAC is only written when the code
changes.

### Buttons: short and long

Buttons with a long-press function act on release: the long function fires
the moment the hold reaches `LONG_PRESS_MS`, the short one on a release
before that, so a short press costs the release time. The voice buttons and
catface act on the press, as the toy did; catface alone also has a long
function — **toy notes on / off**, the toy falling silent for notes from
any source while its buttons still work, so the keys can drive the jacks
and MIDI without the cat — which costs it nothing, the tap having gone on
the press. Every
button still reports itself as its CC on MIDI out, so a DAW can record the
panel. Settings changes blink the LED blue: two pulses for on, one for off,
*n* + 1 pulses for the *n*-th entry of a cycle.

### MIDI in

Both sockets are read every loop: the DIN socket on UART2, and UART0 when it
is a MIDI port, which is the bridge's return path from the DAW. Each has its
own parser with its own running status; real-time bytes are taken wherever
they land, SysEx, system common and active sensing are dropped. One handler
takes what comes out (`docs/firmware.md` 3.4):

- **Channel 1 notes** go through the router like a key — the toy, the keys'
  CV/gate pair with the pots applied, and the active loop — but are not sent
  on to MIDI out: there is no thru, the DAW is hearing its own notes already.
  Notes off the keybed's range are folded by octaves onto it for the toy
  (`MIDI_IN_FOLD`); CV gets the real note.
- **Channel 2 notes** drive the other CV/gate pair directly, as sent — the
  pots do not apply to them, though they do to a loop playing on that pair.
- **CC 20–34** tap the toy's buttons, the same numbers the panel sends out;
  **35–38** tap tempo ± and volume ±, the four buttons the scan never sees;
  **program change 0–4** picks a voice.
- **CC 64** holds a channel's gate and last note until the pedal comes up;
  **pitch bend** moves a channel's CV by ±`MIDI_BEND_SEMIS`; **CC 1** is the
  AUX output when the *mod wheel* waveform is selected.
- **CC 102–111** change the settings as the buttons would, with the same
  blink; **120 / 123** end everything without echoing themselves back.

### The clock

One tick counter, 96 to the beat, that the looper, the arp and the LED read
(`clk::tick()`); nothing is delivered by callback. Three things drive it,
in priority order. **MIDI clock** from either socket: four ticks a clock,
interpolated between clocks from the last interval so a note played between
two of them lands where it was played. **The jack**: `CLOCK_PPQN` pulses a
beat on an interrupt, the same way. **Tap tempo** on ♪: three taps set it,
each further tap refines it, the tap that sets it is beat 1. An external
source takes over on its first tick and, after `CLOCK_EXT_TIMEOUT_MS`
without one, hands back to the internal clock at the tempo it was last
running — no jump in the count, no jump in the loop. Whenever the master is
not MIDI clock in, MIDI clock goes *out* — 24 a beat, start and stop with
the loop — so a DAW can follow the keyboard, and a modular clock at the jack
leaves the DIN socket as MIDI clock. A bar is `BEATS_PER_BAR` beats from
beat 1; no source knows the real one.

### The looper

There are two, one per CV/gate pair, and the CV select switch names the
active one: the keys record into it, record / play / STOP / undo / clear
and the LED belong to it, and the other keeps playing on its own pair. So a
loop stays on the jack it was built on: build one on A, flip to B, play
over it, build another. The router is the one place every sounding note
passes, so the loopers record there: keys, MIDI channel 1, the arp's steps,
the voice buttons and catface — everything but the loops' own playback.
Events are stored in ticks with the layer they belong to. Record arms; the
first note starts the loop and is beat 1 (the internal clock's grid moves to
it — unless another loop is already on the grid, or an external clock is,
in which case it snaps to that grid); record, play or STOP closes it, to
whole beats with quantise loop on. Record while playing overdubs — each
pass a layer — and a long record drops the newest layer. Play stops and
starts, on the next beat when quantised; a long play while stopped clears.
Panic and a DAW's start / stop act on both loops.

Quantise loop is applied at playback: the raw ticks stay, a play order is
rebuilt on the 16th grid, and the flip lands at the next pass. A note held
across the end of a pass is closed on its last tick and opened again on the
first tick of the next, and a key still down when a recording closes keeps
recording until it comes up — so every note-on has its note-off in its own
layer, and undo can never leave a note hanging. The toy, one switch and
100 ms a tap, is the loop's only bottleneck: a loop tap that would start
more than `LOOP_TAP_LATE_MS` late is dropped for the toy alone; MIDI and CV
play every note on time. A panic (STOP held) stops the loop too — the
alternative is notes that come straight back.

### The arpeggiator

Every key and MIDI-channel-1 note edge is told to the arp whether it is on
or not, so switching it on mid-chord works. On, the router lets those notes
go no further and the arp plays the held ones one per `ARP_DIV` step of the
clock's grid — up, down, up-down, or as played — as ordinary performance
events: a tap on the toy, a note on MIDI out, a step on the keys' CV pair,
and into the loop when it is recording. Switched off, keys already held stay
silent until re-pressed.

### AUX

The 8-bit DAC on GPIO25, 0–4.5 V at the jack, draws one of eleven shapes
(techno short cycles them, CC 104 picks one) over a period the *aux rate*
sets (techno long, CC 105): the active loop's pass — the other loop's if the
active one is stopped, a bar if none runs — the bar, or the beat. Saw up
and down, triangle, sine and square are LFOs at that period, phase-locked
to the clock so they land the same way every pass. *Random* is a new level
each period. *Clock* is a 10 ms pulse a beat — a 16th at the beat rate —
which is a clock output for a modular, and patched into the clock jack
proves that input. *Reset* is one pulse at the start of each period.
*Envelope* jumps to full scale on every note that lands on the keys' pair
and decays over `AUX_ENV_MS`. *Mod wheel* is MIDI CC 1. *Off* is 0 V.

### Settings that survive

Every setting the panel or CC 102–110 changes, and the tapped tempo, live in
one struct that is written to NVS `SETTINGS_SAVE_DELAY_MS` after the last
change — so cycling through a setting's options is one flash write, and the
write's few milliseconds of blocking never land on the change itself. At
boot the stored copy is used if its version matches and every field is in
range; otherwise the defaults. A change made and power-cycled within two
seconds is lost, which is the trade. A tempo measured from an external
clock is never stored; the tapped one is.

### Stuck-note protection

- The router records the MIDI note actually sent per key, so note-off always
  matches note-on even if the base pitch pot moves mid-press.
- A failed I²C transaction aborts the frame without updating any state — a read
  that silently returned `0xFF` would look like all six rows pressed, because
  `IPOLB` is inverted.
- `I2C_FAIL_LIMIT` consecutive failed frames trigger a panic and a re-init,
  and the DACs are written again afterwards.
- Panic — STOP held for a second — sends real note-offs for everything
  believed to be sounding, then CC 120 and CC 123 as a courtesy, and drops
  both gates. Receivers are inconsistent about honouring all-notes-off, which
  is why the explicit note-offs come first. Keys still held simply release
  later; their note-offs find nothing to do.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `MCP23017 not responding` at boot | RESET floating; missing I²C pull-ups; A0–A2 not grounded |
| Works on the bench, fails once the case is closed | RESET pull-up — the classic MCP23017 failure |
| Answers the scan, then NACKs ~30 ms into traffic; back after a minute idle; `0x27` with the DACs unplugged | A0–A2 floating. They sit on the strips next to SCL/SDA and get pumped high by bus activity. Ground them at the legs |
| `Error 263` after exactly 1 s on every DAC read, while writes ACK | A slave with no ground reference — the ESP32's I²C controller hangs on the levels it produces instead of erroring |
| Frequent `I2C recovery` messages | Marginal pull-ups, long unshielded SDA/SCL runs, or a flaky RESET |
| All six rows of one column read pressed | Column line shorted to a return, or a failed read leaking through (should be impossible — the driver checks status) |
| Some keys need a hard press | Contact resistance above ~25 kΩ. Clean the membrane; do **not** add external row pull-ups |
| A held key repeats, or a tap sounds twice | The same contact, flickering at the input threshold. `RELEASE_US` absorbs dropouts shorter than 30 ms; if a key still repeats, the self test's `m` shows its cell flicker — clean that key |
| A fourth note appears when three are held | Ghost rejection is off, or the three keys do not form an L (real 3-key chords on distinct rows and columns are fine) |
| Self-test grid lights the transposed cell | Strobes and returns are on the ports opposite to `COLS_ON_PORT_A`. Flip it — do not rewire |
| Cat meows on reset | Missing 10 kΩ `INH` pull-up to 5 V |
| Nothing on the DIN socket | 3.3 V drive with 220 Ω resistors — see the BOM correction above |
| Junk bytes at every boot | ROM bootloader log on UART0. Expected; the bridge drops them |
| Upload hangs on `Connecting...` | The bridge or a serial monitor still holds the port. Close it |
| DAW sees the port but no notes | Run the bridge with `--monitor`. Messages there but not in the DAW is a routing problem; nothing there is firmware |
| Notes arrive but are the wrong pitches | `position_map.cpp` is still the placeholder — run the sweep in step 2 |
| The toy plays every note twice, or notes from the DAW come straight back to it | One loopMIDI port for both directions. Make two and give the bridge `--midi` and `--midi-in` |
| The DAW's notes never reach the toy | The bridge is running without `--midi-in`, or the DAW's output is not routed to the `Meowsic in` port (FL: MIDI Out plugin, port number, channel 1) |
| A gate stays high after the DAW stops | The DAW sent no note-offs (a stopped transport, a crashed plugin). Stop the bridge — it sends all-notes-off on exit — or `midi_send.py panic` |
| No beat on the LED | There is no tempo yet: tap ♪ three times, or send a clock. The loop's first note also sets it |
| The loop drifts against the DAW | Two free-running clocks. Have the DAW send MIDI clock (the keyboard follows it) or follow the keyboard's clock out |
| The toy misses notes of a dense loop | By design: one switch, 100 ms a tap; late taps are dropped for the toy so it never lags. MIDI and CV have them all. Raise `LOOP_TAP_LATE_MS` to prefer late over missing |
| A loop's first note lands late under MIDI clock | It snapped to the clock's 16th grid, as it should; play a little ahead of the beat |
| Keys go silent when the arp is switched off | Expected: keys already held are not re-sounded. Press them again |
| The toy plays nothing for the keys, though the jacks and MIDI do | Toy notes are off — catface was held. Hold it again (2 blinks) |
| AUX sits at 0 V | The shape is *off*, or *envelope* with no note played yet, or *mod wheel* with the wheel down. Cycle techno |
| AUX steps rather than sweeps | The 8-bit DAC: 256 levels across the period. A bar at 120 BPM is a step every 8 ms; slow LFOs show it |
| A setting is back to its old value after a power cycle | It was changed less than two seconds before the power went — the write waits that long |
| Every setting is back to default after a reflash | The layout changed (`SETTINGS_VERSION`) or the NVS partition was erased; set them again once |
| A note hangs after stopping the bridge | Should not happen; it sends all-notes-off on exit. Hold STOP for a second, then check the DAW is not also latching |
| Notes stick after a crash | Hold STOP for a second. It comes in through the expander, so if the bus is what crashed, wait for `I2C recovery` or power-cycle |
| Keys land on the wrong CV jack, or hop between them | The CV select switch is read as a level on GPIO34: check its 10 kΩ to 3.3 V. Open = A, closed = B |
| CV wobbles or steps on its own with the pot still | ADC noise past the filter. Raise `POT_STEP_HYST` (quantised) or the smoothing in `controls.cpp`; check the 100 nF on the wiper |
| The pot does not reach its top or bottom semitone | `POT_ADC_LO` / `POT_ADC_HI` are wider than this ESP32's dead ends. Print the raw reading with `systest` `p` and tighten them |

---

## Next steps

The firmware in `docs/firmware.md` is built. What it deliberately leaves
for later is listed there under *Later, not now*: loop multiply, transposing
a loop from the keys, a scale mode for MIDI in and the arp, a deeper undo.
Two things on the hardware side would change it more than any of those:
working DIN sockets (the firmware already reads and writes them; the
acceptance runs go over USB until they do) and the resonator question at
the end of this section.

Two constraints fixed by the hardware, which the tap queue honours:

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
2. ~~One-shot vs sustained meow~~ — one-shot: holding a key does not sustain,
   and a fast re-press cuts the meow off and starts a new one. So the injector
   only taps, note-off handling exists for MIDI alone, and the looper records
   press times, not durations.
3. **Does an Rosc pin or ceramic resonator escape the blob?** If so, replacing it
   with an MCU PWM clock makes the whole toy pitch- and speed-controllable over
   MIDI CC. Biggest sonic win available, but reportedly unlikely on this toy.
