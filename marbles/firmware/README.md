# Marblesy firmware — Marbles on the Daisy Seed

Firmware for [Marblesy](../README.md), the Marbles clone on a Daisy Seed. It
is a port of Mutable Instruments' own Marbles firmware in its final
version: the update of January 2023, which added the reset input mode
(MIT licence). The random generators and the CV processing are Marbles'
code, unchanged apart from one marked fix, and the front panel behaves as
Marbles' does, with two more fixes and a few marked additions. New are the hardware layer, the settings storage, the
brightness of the four CV output LEDs and a calibration of the CV outputs,
which Marbles leaves to its factory test rig.

> **Not yet run on hardware.** It builds and links for the Seed and passes
> the host tests (see [Testing](#testing)), but nothing here has run on a
> Marblesy yet. Do the [first power-up checks](#first-power-up) before
> trusting it.

---

## The front panel

Everything is Marbles' except the last two rows. A long press is 2 s.

| Control | What it does |
|---|---|
| **t deja vu** | Deja vu on or off for the t section; the LED breathes slowly while the DEJA VU knob sits in its notch at noon. A long press locks the loop whatever the knob says (fast breathing); a press then unlocks it. Off and on again replaces as many loop steps as clock ticks passed while it was off. |
| **X deja vu** | The same for the X section. |
| **DEJA VU** knob | From fully CCW to noon, more and more past values come back; at noon the loop repeats exactly; past noon, more and more random jumps within the loop. **LENGTH** sets the loop from 1 to 16 steps. |
| **t mode** | The t model, steady LED: green = complementary coin toss (t1 or t3), yellow = clusters, red = drums. A long press switches to the second bank, LED blinking: independent coin tosses, divider, three states. |
| **t range** | Clock range: green ¼×, yellow 1×, red 4×. |
| **X mode** | How X1..X3 share SPREAD, BIAS and STEPS: green identical, yellow bump, red tilt. |
| **X range** | Voltage range of X: green 0–2 V, yellow 0–5 V, red ±5 V. A long press selects the scale (the LED blinks its colour, slow for scales 1–3, fast for 4–6; each press moves on). |
| **X ext** | The X SPREAD input is sampled and quantised instead of the random voltages (LED on). A long press records a scale from the notes played into X SPREAD, gated by X CLOCK; X ext again ends it (a long press there restores the preset scale). |
| Hold **t mode**, turn **BIAS** / **JITTER** | Pulse width of the t gates: its mean / its randomness. |
| Hold **X mode**, turn **RATE** / **SPREAD** / **BIAS** / **STEPS** | The Y output: its clock divider / spread / bias / steps. |
| **t mode** and **X mode** together | The reset input mode on or off: t JITTER's and X STEPS' CV inputs then reset the t and X sequences on a rising edge (about 1 V) instead of modulating. Both LEDs blink yellow for 4 s if it is on, stay dark if off. |
| Hold **X mode** while powering up | Colour-blind LED mode on/off. Nothing else: a button held at power-up does nothing until it has been let go (on Marbles, X mode also stepped, and the Y settings could change). |
| Hold **X range**, press **t range** | Calibration of the CV inputs, below. |
| Hold **t range**, press **X range** | *Marblesy:* calibration of the CV outputs, below. |
| Hold **t deja vu** while powering up | *Marblesy:* on Marbles this starts its audio firmware updater; here it waits for a firmware upload, with the four mode and range LEDs red, green, red, green (see [Flashing](#flashing)). |

Press the second button of a pair within 2 s of the first, or the first one
counts as a long press. The two power-up gestures are read when the
firmware starts, about two seconds after power-on (the bootloader runs
first): keep the button held until the LEDs light.

The red/green buttons cannot show both colours at once, so their yellow is
red and green alternating 4000 times a second; it may look more orange
than on Marbles. The four LEDs beside the CV outputs (Y, X1, X2, X3) glow
in proportion to the voltage, whatever its sign: Marbles' bicolour LEDs
show negative voltages in red, these single green ones cannot. The t1..t3
LEDs are lit by the gates themselves.

Settings are saved once nothing has changed for 30 s, or for 5 s after a
calibration or a scale recording, and only if something changed, so a set's
worth of button presses costs a few flash writes. That includes deja vu, the
reset mode and the hidden settings, which Marbles only saves along with some
later change. Wait that long before switching off. (Saves are kept rare
because each one also rewrites the flash chip's status register, which wears
like any flash cell; a failed save is retried a few times.)

## Calibration

### CV inputs (Marbles' procedure)

Do it once after building the module, and again if you swap the Seed or
the op-amps. Use a well-calibrated, low-impedance voltage source (a bench
supply or a precision reference; or set the voltages measured at the jack
with the cable in, since a source with 1 kΩ output resistance reads about
1 % off through the 100 kΩ input) and patch nothing else: step 1 measures
the zero of every other CV input.

1. Hold X range and press t range. The t range LED blinks green.
2. Send exactly 1.000 V into t RATE and press t range. The LED blinks yellow.
3. Send exactly 3.000 V into t RATE and press t range. The X range LED blinks green.
4. Send exactly 1.000 V into X SPREAD and press X range. It blinks yellow.
5. Send exactly 3.000 V into X SPREAD and press X range. Done.

If the four mode and range LEDs blink red, a step was more than about
±50 % off: nothing was saved and the previous calibration stays in use
(Marbles keeps the steps that passed until power-off); start again. Leaving
half way (the reset-mode chord, X ext) also keeps the previous calibration.
Before the first calibration the firmware assumes nominal parts: within a
few percent.

### CV outputs (Marblesy)

Marbles' outputs are calibrated at the factory by a test rig. Marblesy
measures its own, with the X SPREAD input, so calibrate the inputs first.
The outputs go one at a time, in panel order: Y, X1, X2, X3.

1. Hold t range and press X range. The X range LED blinks green and the Y
   output LED blinks: the output waiting to be measured.
2. Patch that output into X SPREAD and press X range (or t range). The
   LEDs stop blinking while it is measured (under a second): the output
   goes to about +4.1 V, then about −2.1 V.
3. The next output's LED blinks: move the cable and press again, until X3
   is done. The module then goes back to normal and saves.

The other outputs sit at 0 V and the gates stay low meanwhile. To give up,
press any other button, or leave it a minute: the outputs keep their
previous calibration and play on. If a measurement is more than 10 % from
the nominal output stage (an unpatched input does that), the panic LEDs
blink red, the outputs keep their previous calibration and nothing is
saved.

The calibration is made for a usual 1V/oct input, 100 kΩ to ground: the
measurement goes through the output's 1 kΩ resistor into X SPREAD's input,
and the firmware takes that load into account. Into such an input the
outputs are then right to within the MCP4922's linearity (typically a few
mV, ±30 mV at worst) and its 2.6 mV steps; into a high-impedance input,
such as a meter, they read about 1 % wide, as any output behind 1 kΩ.
Uncalibrated, expect up to a few percent off, which is a semitone or more
over five octaves on X when it drives pitch. The output stage reaches
+5.32 V and −5.45 V nominally, with 23.2 kΩ for R70, R74, R78 and R82
(`kDacInputResistor` in `src/marbles/drivers/dac.h` matches it), which
leaves every output room for ±5 V into a 100k load with 1 % resistors.
The first design's 24 kΩ stopped at −5.10 V, which 1 % parts and the load
often pulled short of −5 V.

---

## Flashing

The program is 182 kB, more than the Seed's 128 kB internal flash, so it
runs with the **Daisy bootloader**: the bootloader lives in the internal
flash, keeps the program in the Seed's 8 MB QSPI flash and copies it to
RAM at power-up. Flash the bootloader once, then the firmware.

The simplest way is the [Daisy Web Programmer](https://flash.daisy.audio)
in Chrome:

1. Put the Seed in DFU mode: hold BOOT, press and release RESET, release
   BOOT. On the **Bootloader** tab, flash the bootloader.
2. Reset the Seed. Its LED now pulses for a couple of seconds at every
   power-up: that is the bootloader waiting for an upload. Press BOOT while
   it pulses to make it wait for good.
3. On the **File Upload** tab, upload `marblesy.bin` from this folder (a
   build of these sources, so no toolchain is needed), or
   `build/marblesy.bin` after building it yourself.

On Windows, the browser and `dfu-util` need the WinUSB driver for the Seed's
DFU device: see Electrosmith's "Zadig driver reset" page.

With the Daisy toolchain installed, the same from here:

```bash
make program-boot
```

```bash
make program-dfu
```

(`program-boot` needs the Seed in DFU mode as in step 1, `program-dfu` the
bootloader's pulsing LED as in step 2.)

**Updating later**, with the module in the case: hold t deja vu (and no
other button) while powering up, until the mode and range LEDs light red,
green, red, green; the pattern may drift while the bootloader waits, which
does not affect the upload.
Marblesy has then restarted into the bootloader, which waits until a new
`marblesy.bin` arrives, so the Seed's own buttons are not needed. A USB
cable still has to reach the Seed's micro-USB port, at the top end of the
Seed on the back of the module.

The bootloader's grace period is why the module starts about two seconds
after power-on. Until then the LEDs may show a random pattern (the
74HC595s have no reset), the CV outputs sit at about +5.3 V (the MCP4922s
power up at code 0) and the gate outputs float; the
firmware sets all of them first thing. `make program-boot` installs the
2 s version; libDaisy also ships one that starts the module at once. With
the Seed in DFU mode:

```bash
make program-boot BOOT_BIN=lib/libDaisy/core/dsy_bootloader_v6_4-intdfu-10ms.bin
```

With it, updates go through the t deja vu gesture, or, if a broken build
never gets that far, through BOOT + RESET and `make program-boot` again.

Marblesy keeps its settings, calibration and scales in the first 64 kB of
the QSPI flash, which the bootloader leaves alone; flashing a new version
of the firmware keeps them.

## Building

Needs the ARM GCC toolchain and GNU make (Electrosmith's Daisy toolchain
has both, plus `dfu-util`), and git. On Windows, run make from Git Bash
(or another POSIX shell), with the compiler and `dfu-util` on its PATH.

```bash
make setup
```

```bash
make
```

`make setup` clones libDaisy v9.0.0 into `lib/libDaisy` (ignored by git)
and builds it; `make` builds `build/marblesy.bin`. After a change to the
sources, copy that over `marblesy.bin` here so the two stay the same.
Point `LIBDAISY_DIR` at another libDaisy checkout to use that instead, and
set `GCC_PATH` if the compiler is not on the PATH: a forward-slash path
ending in a slash, for example Arduino's STM32 core, which ships a usable
compiler:

```bash
make GCC_PATH=/c/Users/<you>/AppData/Local/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/
```

Memory use (libDaisy 9.0.0, GCC 14.2): 182 kB of the 480 kB the bootloader
allows in SRAM, 30 kB of the 128 kB DTCM.

---

## How the port works

```
src/
  main.cc                 the Seed's start-up, the bootloader gesture, the main loop
  marblesy.h, marblesy.cc replaces marbles/marbles.cc: the I/O and DSP interrupts, Process()
  hal.h, hal_daisy.cc     the board: pins, ADC + mux, SPI bus (DACs, 74HC595, 74HC165), timer, RNG, QSPI, watchdog
  storage.h, storage.cc   wear-levelled settings records in the QSPI flash
  output_calibrator.h     the output calibration (new)
  marbles/                replace their namesakes in Marbles:
    ui.h, ui.cc             Marbles' UI with two marked additions
    settings.h, settings.cc Marbles' settings, saved from the main loop
    drivers/                Marbles' driver interfaces on the Seed
    random/lag_processor.cc Marbles' file with one marked fix
vendor/                   Marbles and stmlib, unchanged (vendor/README.md)
test/                     host tests (WSL g++)
```

`src/` comes before `vendor/` on the include path, so a header in
`src/marbles/` replaces the upstream one of the same name.

**Timing.** Marbles runs at 32 kHz: an interrupt writes the gates, reads
the clock inputs and feeds the DAC every sample, and every 5 samples hands
a block, with the ADC readings, to the main loop, which renders it. The
port keeps exactly that rate and block size (parts of Marbles' code count
in them): a timer interrupt at 32 kHz (TIM7, the highest priority) does
the sample's I/O, including the SPI writes to the two DACs, and at every
block it pends a low-priority interrupt (PendSV) that runs what Marbles'
main loop does, the UI's event handling and the rendering. That leaves the
main loop to the flash writes, which take tens of milliseconds on the
Seed's QSPI chip and so cannot hold up the outputs. The UI is polled every
32 samples (1 kHz), as Marbles' SysTick does, and a watchdog restarts the
module if the rendering stops for 2 s.

**CV inputs.** Marbles reads ±5 V as the full range of its ADC (0.5 − V/10
of full scale). Marblesy's TL074 stages have another gain and offset
(1.676 V − 0.27 V_in into the Seed's ADC); the CV driver turns each reading
back into the jack voltage through the nominal stage and then into the
number Marbles would have read, so Marbles' calibration, its checks, the
reset-mode gate thresholds and every parameter's range apply unchanged.
Marbles reads X SPREAD twice and averages; here it is read once into both
slots. The ADC scans the seven CV inputs and the pot mux every 0.2 ms (8×
oversampling); the pots come through the 74HC4051 in the mux order of
`circuit.py`, not the panel order.

**CV outputs.** Two 12-bit MCP4922s instead of Marbles' 16-bit DAC8564.
The firmware still computes Marbles' 16-bit codes, with Marbles'
calibration format, and rounds them to 12 bits (2.6 mV steps, a
thirty-second of a semitone). The defaults are Marblesy's nominal output stage
(5.32 V − 4.31 · V_dac), not Marbles'. The four outputs are written every
sample and updated together by LDAC; the gates follow 2 samples later, as
on Marbles, so a CV is always out before its gate. The DACs use their
buffered reference input, which takes nothing from the LM4040: R47 (1.5 kΩ)
feeds it 0.53 mA, the −2.5 V inverter takes 0.25 mA of that, and the
0.28 mA left is well above the reference's 60–65 µA minimum (the unbuffered
inputs would take another 60 µA).

**SPI bus.** The DACs, the 74HC595s and the 74HC165 share SPI1 at
6.25 MHz, mode 0, 16-bit frames, driven from the I/O interrupt only: the
four DAC frames every sample (about 11.5 µs), the LED frame every 4
samples, the buttons every 32: the I/O interrupt takes 40-48 % of the CPU,
and the rendering about a fifth. The bus is set up once, as an endless
transfer, so no frame needs any reconfiguring; a frame that ever timed out
restarts it.

**LEDs and buttons.** The LEDs are refreshed every 4 samples (8 kHz) from
the frame Marbles' UI sets every millisecond, in the 74HC595 bit order of
`circuit.py`. Yellow on the red/green buttons alternates the two colours
at every refresh; the output LEDs get 16 brightness levels by PWM over 16
refreshes (500 Hz). The buttons come through the 74HC165, read once per
millisecond for Marbles' debouncing. A reading with all seven held, which
is what a 74HC165 that does not answer gives (MISO is pulled up, so an
unplugged faceplate reads all released), is ignored: a bad joint on the
button lines then costs the buttons, not the whole module.

**Clock inputs.** As on Marbles: inverting transistor stages, read every
sample, and a pseudo-random pattern from D15 through 10k into both jacks'
switch lugs, so an input that does not follow it has a cable in it.

**Settings.** Calibration, scales and state are Marbles' structures. They
go into a ring of 1 kB records in the first 64 kB of the QSPI flash: each
save takes the next slot, a 4 kB sector is erased only when the ring comes
back to it, and the newest valid record wins at power-up, so an interrupted
save falls back to the previous one. Each save is read back; one that
fails is tried in the next slot, and later again. The calibration and scales
written are always the last ones Marbles' UI asked to save, so an abandoned
calibration never sticks. Saves are kept rare because libDaisy rewrites the
flash chip's non-volatile status register around every write and erase
(about 2.5 times per save), which the ring cannot spread.

**Three fixes to Marbles' code**, all found by the host tests' sanitizers:

- In `lag_processor.cc`, a ramp phase of exactly 1.0 makes the
  raised-cosine lookup read the element after its table. On Marbles that
  is the next table in flash and only ever gets multiplied by zero; here
  it could be any data, and a NaN would stick in the STEPS lag filter. The
  fix returns the table's last entry, which is what Marbles computes.
- In `ui.cc`, holding t deja vu while DEJA VU or LENGTH turns writes the
  knob's value through a null pointer (those two knobs have an empty
  hidden-setting slot). On the H750 that address is RAM. The write is
  skipped now; the knob still freezes until the button is let go, and
  that release still does nothing, as on Marbles.
- In `marbles.cc` (here `marblesy.cc`), the scales reach X1..X3 but never
  Y, although Y is given the selected scale: Y's quantizers keep a one-note
  placeholder, and Y STEPS past about 60 % (hold X mode, turn STEPS) reads
  the 256th entry of a 16-entry table, so on Marbles Y then lands on
  whatever memory holds. Y now gets the scales and quantizes to the
  selected one, as the manual describes for STEPS.

## First power-up

Things to check, in this order, before the module goes in the case:

1. **LEDs**: after the bootloader's two seconds, t mode and X mode light
   green, t range yellow (it may look orange), X range red. If an LED
   lights that should not, the 74HC595 bit table in
   `src/marbles/drivers/leds.cc` disagrees with the board. If the red/green
   buttons show red where green is expected (t mode, X mode), swap the
   `red` and `green` columns of that table: which way round the Thonk
   button's two dies sit is the one thing the netlist cannot say.
2. **Buttons**: t mode steps green, yellow, red; X range steps its
   colours. A button that does nothing or the wrong thing points at the
   74HC165 table in `src/marbles/drivers/switches.cc`.
3. **Outputs**: hold t range and press X range (the output calibration
   waits): X1..X3 and Y sit at 0 V, within about 0.1 V before calibration.
   Press another button to leave. (At rest they play random voltages.)
4. **Pots**: each knob turns the parameter printed above it, clockwise up.
   RATE at noon: t2 ticks at 2 Hz.
5. **Calibrate** the inputs. Before calibrating the outputs, measure the
   2.5 V reference at C30: it must read 2.50 V. A TO-92 LM4040 fits
   either way round (pads 1 and 3 are both GND); anything else means a
   part with another pinout or a bad joint (see `../docs/design.md`). Then
   calibrate the outputs and check the octaves of X1 into a VCO with a
   tuner.
6. **Clock inputs**: patch a clock into t CLOCK: t2 follows it. Patch one
   into X CLOCK: X1..X3 change on its edges.

## Testing

`test/` holds host tests, built with g++ under AddressSanitizer and UBSan.
They need WSL (or Linux) with g++ and python3. From `marbles/firmware`:

```bash
wsl.exe -e bash test/run_port_test.sh
```

About half a minute, 3118 checks; a group name (`cv`, `dac`, `outcal`,
`leds`, `buttons`, `io`, `storage`, `settings`, `dsp`) runs one group. The
firmware runs on a model of the board in `test/hal_fake.cc`, with jack
voltages in and out and 1 % part tolerances. `test/gen_board_tables.py`
reads the LED, button and DAC wiring and the resistor values the model is
built from out of `../hardware/tools/circuit.py`, from the parts' pins, and
checks `hal.h`'s pot and CV orders and the pin constants in
`src/hal_daisy.cc` against it:

- **cv**: every input's scaling, Marbles' calibration with 1 % parts (t RATE
  within 2 cents over ±4 V), the zeros, saving.
- **dac**: the MCP4922 words, the channel wiring, the nominal output stage.
- **outcal**: the output calibration end to end with 1 % parts, through
  the output resistor into X SPREAD's input (within 2.5 mV into a 100k load
  over −5..+5 V afterwards), a failed one, giving up, saving.
- **leds**, **buttons**: the bit tables against `circuit.py`, yellow, the
  output LED levels, Marbles' button gestures, the null-pointer guard,
  buttons held at power-up, a 74HC165 that does not answer, the update
  gesture.
- **io**: interrupt rates, the internal clock (2 Hz at noon, an octave per
  volt on RATE), following an external clock, CV before gate.
- **storage**, **settings**: the record ring with power cuts in every flash
  operation, failed saves retried, the save delays, calibrations abandoned
  every way, Marbles' outlier checks, deja vu and the reset mode kept, a
  recorded scale.
- **dsp**: Marbles' generators over all six t models, three X modes and
  three clock set-ups: no NaN, outputs within ±5 V, gates moving.

Not covered: anything in `hal_daisy.cc` and `main.cc` (the registers, the
timer, interrupt timing), which only the hardware can check, and the
MCP4922's own non-linearity (the model's DAC is ideal).

## Licence

MIT; see [LICENSE](LICENSE). Marbles' code and stmlib are © Emilie Gillet:
the notice is at the top of each of those files, including the ones `src/`
adapts, and in `vendor/`. libDaisy is © Electrosmith, MIT. The built
firmware also contains STMicroelectronics' HAL drivers (BSD-3-Clause) and
parts of ST's USB libraries (SLA0044) from libDaisy. "Mutable Instruments"
is a registered trademark and not used for this module.
