# Plaitsy firmware — Plaits 1.2 on the Daisy Seed

Firmware for [Plaitsy](../README.md), the Plaits clone on a Daisy Seed. It is
a port of Mutable Instruments' own Plaits firmware, version 1.2: the final
release, out in December 2022, whose source Mutable published in May 2023
(MIT licence). The DSP code is Plaits' code, unchanged apart from the
sample-rate constant in `dsp/dsp.h`, and the front panel behaves as Plaits'
does. New are the hardware layer and the settings storage.

Version 1.2 is the 2022 update. It added eight models to the original
sixteen, in a third bank, and a two-button gesture that switches the
buttons between the original way of choosing models and one that reaches
all 24. The original sixteen models are 1.2's versions of them, with
Émilie Gillet's last fixes: more responsive TIMBRE and MORPH knobs, less
hysteresis when a CV picks a model or a chord, better band-limiting at the
top of the wavetable model and a speech-model envelope fix, plus the LFO
and octaves ranges of the FREQUENCY knob and the colour-blind mode (1.1
and 1.2).

> **Not yet run on hardware.** It builds and links for the Seed and passes
> the host tests (see [Testing](#testing)), but nothing here has been
> heard yet. Do the [first power-up checks](#first-power-up) before
> trusting it.

---

## Switching between the original models and the 2022 models

| Navigation | How the buttons work | Models | Button LEDs |
|---|---|---|---|
| **Original** (default) | Left button: the green bank. From a red or yellow model the first press keeps the row, then each press steps down. Right button: the same in the red bank. Plaits 1.0's button layout. | 16 | off |
| **2022** | Left button: previous model. Right button: next model. Steps through all 24: the yellow bank (new), then green, then red, round and round. | 24 | both lit |

**To switch: press either button and, within two seconds, tap the
other.** The switch happens when one button is let go while the other is
still held, so letting go of both at the same instant changes the model
instead. Holding the first button longer than two seconds shows its hidden
settings instead, and letting go of it then changes the model. Holding
both for two seconds starts the calibration, as on Plaits.

The choice is saved. If a yellow model was selected at power-down, the
module comes back in the 2022 navigation, because the original one cannot
reach it. The MODEL CV input reaches all 24 models in either navigation
(about 0.21 V per model). The LEDs in the two buttons are Plaitsy's own
(Plaits' buttons have none): lit means the 2022 navigation is on.

## Models

The LED column shows the model's row; the colour is its bank. The steady
LED is the model playing, a pulsing one the model the buttons selected
(they differ while a CV on MODEL moves it).

| Row | Green bank (original) | Red bank (original) | Yellow bank (2022) |
|---|---|---|---|
| 1 | Virtual analog, pair of classic waveforms | Granular cloud (swarm of 8 saws) | Classic waveshapes with filter |
| 2 | Waveshaping oscillator | Filtered noise | Phase distortion and modulation |
| 3 | 2-operator FM | Particle noise | 6-operator FM, preset bank 1 |
| 4 | Granular formant oscillator | Inharmonic string | 6-operator FM, preset bank 2 |
| 5 | Harmonic (additive) oscillator | Modal resonator | 6-operator FM, preset bank 3 |
| 6 | Wavetable oscillator | Analog bass drum | Wave terrain |
| 7 | Chords | Analog snare drum | String machine with chorus |
| 8 | Vowel and speech synthesis | Analog hi-hat | Chiptune: four square voices, arpeggiator |

What each knob and output does in each model is in the
[Plaits manual](https://pichenettes.github.io/mutable-instruments-documentation/modules/plaits/manual/)
(green and red banks) and the
[1.2 release notes](https://pichenettes.github.io/mutable-instruments-documentation/modules/plaits/firmware/)
(yellow bank). Both apply as written.

## Other button gestures

All of them are Plaits'.

| Gesture | What it does |
|---|---|
| Hold the **left** button, turn TIMBRE / MORPH | Low-pass gate response (VCFA to VCA) / ringing and decay time of the internal envelope. The LEDs show both, four each (TIMBRE's on top), as soon as a knob moves, or after 2 s if none does. |
| Hold the **right** button, turn HARMONICS | Range of the FREQUENCY knob: LFO (chasing lights), C0…C7 ± 7 semitones (one LED), octaves (alternate LEDs blink), or the full 8 octaves around C4 (all LEDs lit, the default). |
| Hold the **right** button, turn FREQUENCY | In the octaves range: the root note, ± 7 semitones, which FREQUENCY then transposes by octaves. |
| Hold **both** buttons for 2 s | V/OCT calibration, below. |
| Hold the **right** button while powering up | Colour-blind LED mode on/off (banks shown by brightness instead of colour). As on Plaits, it also sets the FREQUENCY range from the HARMONICS knob: turn HARMONICS fully clockwise first to keep the full range, or reset it afterwards (hold right, turn HARMONICS fully clockwise). |
| Hold the **left** button while powering up | On Plaits this starts its audio firmware updater; here it waits for a firmware upload, with the LED column alternating red and green (see [Flashing](#flashing)). |

The two power-up gestures are read when the firmware starts, which is
about two seconds after power-on (the bootloader runs first): keep the
button held until the LED column lights.

The hidden settings (low-pass gate response, decay, FREQUENCY range and
root note) are saved with the next model change or navigation switch, as
on Plaits; letting go of the button does not save them. The save happens
5 s after the last change and only if something changed, outside the
audio, so it no longer causes a gap in the sound, and a run through the
models costs one flash write.

## Calibration

Do it once after building the module, and again if you swap the Seed or
the op-amps. It is Plaits' procedure:

1. Patch a well-calibrated V/OCT source into V/OCT and **nothing else**:
   step 3 measures the zero of every other input, so a cable in TIMBRE,
   FM, MORPH, TRIG or LEVEL, even one at 0 V, shifts that input's zero
   (FM's by about a semitone).
2. Hold both buttons for 2 s. The top LED blinks green.
3. Send 1.000 V and press a button. The top LED blinks yellow.
4. Send 3.000 V and press a button. Done.

If all eight LEDs blink red, the second voltage was not between about 1
and 3 V above the first; press a button and start again. The check is
that loose, so send exactly 1.000 V and 3.000 V: any step in that range is
accepted and sets the V/OCT scale from it. Nothing from a failed
calibration is saved, but the zeros measured at step 3 stay in use until
power-off: switch the module off and on after a failed attempt.

Until the first calibration the firmware assumes nominal parts. With 1 %
resistors the pitch can be most of a semitone off and the octaves ten
cents or more out, and an unpatched MODEL input can select the model next
to the one the buttons picked.

## Loading DX7 patches, a wave terrain or wavetables

Plaits 1.2 can receive a block of custom data as audio on its TIMBRE
input: 32 DX7 patches for one of the 6-op FM models (yellow rows 3–5,
replacing that model's factory bank), a wave terrain (yellow row 6, added
as a ninth terrain at HARMONICS fully clockwise), or 15 waveforms and bank
D's map for the wavetable model (green row 6). Mutable's
[online editor](https://pichenettes.github.io/plaits-editor/) makes the
audio. Select the target model, patch the computer's output into TIMBRE
and play it: a green bar grows on the LED column, a green column with a
moving gap means done, blinking red an error. The block is stored in the
Seed's flash, for one model at a time as on Plaits: a new block of any
kind replaces the previous one.

---

## Flashing

The program is 253 kB, more than the Seed's 128 kB internal flash, so it
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
3. On the **File Upload** tab, upload `plaitsy.bin` from this folder (a
   build of these sources, so no toolchain is needed), or
   `build/plaitsy.bin` after building it yourself.

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

**Updating later**, with the module in the case: hold the left button
while powering up, until the LED column lights alternately red and green.
Plaitsy has then restarted into the bootloader, which waits until a new
`plaitsy.bin` arrives, so the Seed's own buttons are not needed. A USB
cable still has to reach the Seed's micro-USB port, at the top end of the
Seed on the back of the module.

The bootloader's grace period is why the module starts about two seconds
after power-on, and why the LED column may show a random pattern until
then (the 74HC595s have no reset; the firmware clears them first thing).
`make program-boot` installs the 2 s version. libDaisy also ships a
version that starts the module at once; with the Seed in DFU mode:

```bash
make program-boot BOOT_BIN=lib/libDaisy/core/dsy_bootloader_v6_4-intdfu-10ms.bin
```

With it, updates go through the left-button gesture, or, if a broken
build never gets that far, through BOOT + RESET and `make program-boot`
again.

Plaitsy keeps its settings, calibration and custom data in the first
128 kB of the QSPI flash, which the bootloader leaves alone (its notes
keep that space for possible future features); flashing a new version of
the firmware keeps them.

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
and builds it; `make` builds `build/plaitsy.bin`. After a change to the
sources, copy that over `plaitsy.bin` here so the two stay the same. Point `LIBDAISY_DIR` at
another libDaisy checkout to use that instead, and set `GCC_PATH` if the
compiler is not on the PATH: a forward-slash path ending in a slash, for
example Arduino's STM32 core, which ships a usable compiler:

```bash
make GCC_PATH=/c/Users/<you>/AppData/Local/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/
```

Memory use (libDaisy 9.0.0, GCC 14.2): 253 kB of the 480 kB the bootloader
allows in SRAM, 49 kB of the 128 kB DTCM.

---

## How the port works

```
src/
  main.cc                 replaces plaits/plaits.cc: audio callback, main loop
  hal.h, hal_daisy.cc     the board: pins, ADC + mux, buttons, probe, 74HC595s, QSPI, watchdog
  storage.h, storage.cc   wear-levelled settings records in the QSPI flash
  plaits/                 replace their namesakes in Plaits 1.2:
    ui.h, ui.cc             Plaits' UI, three marked changes
    settings.h, settings.cc Plaits' settings, saved from the main loop
    user_data.h, .cc        custom data in QSPI with a RAM copy
    dsp/dsp.h               the Seed's real sample rate
    drivers/                Plaits' driver interfaces on the Seed
vendor/                   Plaits 1.2, stmlib and the FSK decoder, unchanged (vendor/README.md)
test/                     host tests (WSL g++)
```

`src/` comes before `vendor/` on the include path, so a file in
`src/plaits/` replaces the upstream file of the same name. Everything else
is Mutable's code as published.

**Timing.** As on Plaits, everything happens in the audio interrupt:
48 kHz, 12 samples per block, so the UI is polled at 4 kHz and its tasks
(LEDs, buttons, hidden parameters, cable detection) each run at 1 kHz.
The two things that take time, shifting the LED frame out over SPI and
writing the flash, run in the main loop instead. As on Plaits, a watchdog
restarts the module if the audio stops for 2 s.

**CV inputs.** Plaits reads its CVs through MCP6004 stages of its own
(gains 0.2 to 0.56, offsets from a −10 V reference) with a 16-bit SDADC.
Plaitsy's TL074 stages have other gains (0.13; 0.33 on V/OCT). The CV
driver turns each Seed reading back into the jack voltage and then into the
number Plaits' SDADC would have read for that voltage, clipped where
Plaits' stages clip. Plaits' calibration, cable-detection thresholds and
UI code then apply unchanged, and every input has Plaits' range and
response: V/OCT −3…+7 V, MODEL and HARMONICS ±5 V, TIMBRE, FM and MORPH
±8 V, TRIG −0.9…+5 V, LEVEL −0.9…+9.1 V. One change: Plaits' factory zero
offsets are replaced by the ones its calibration measures on the nominal
circuit (0 V reads 0), since its own would put MODEL one model off here.

**Cable detection.** As on Plaits: D14 sends a pseudo-random bit pattern
through 10k into the switch lugs of TIMBRE, FM, MORPH, TRIG and LEVEL, and
an input that does not follow it has a cable in it. The ADC scans all nine
channels about every 0.2 ms (8× oversampling), so the reading compared with
each bit is taken well after the bit changed. During calibration Plaits
turns the probe pin into an input so the unpatched inputs read 0 V;
Plaitsy's stages would float at their bias that way, so the pin is held low
instead and the 0.13 V that leaves on those inputs is subtracted.

**Pots and LEDs.** The pots come through the 74HC4051 in the mux order of
`circuit.py`, the LEDs through the two 74HC595s in the bit order of
`circuit.py` (both chosen on the faceplate so no tracks cross).

**Tuning.** Plaits tunes its oscillators to the rate its DAC really runs
at (47,872 Hz). The Seed's "48 kHz" is 48,014 Hz (PLL3 at 49.17 MHz,
divided by 4 and 256); `src/plaits/dsp/dsp.h` uses that, which otherwise
would leave every model 5 cents sharp.

**Outputs.** OUT on the Seed's left audio output, AUX on the right. Plaits
writes its samples inverted for its inverting output stage; the port
undoes that, so a positive sample is a positive voltage if the breakout's
stage does not invert. `kOutputPolarity` in `src/main.cc` flips it. The
output level is the breakout's (Plaits: about ±8 V at full scale).

**Settings.** Calibration and state are Plaits' structures. They go into a
ring of 256-byte records in the first 64 kB of the QSPI flash: each save
takes the next slot, a 4 kB sector is erased only when the ring comes back
to it, and the newest valid record wins at power-up, so an interrupted
save falls back to the previous one. The calibration written is always the
last completed one (Plaits' own storage is a little looser: when its state
area fills, it rewrites whatever calibration is in RAM). Saves are kept
rare because libDaisy rewrites the flash chip's non-volatile status
register around every write, and the ring cannot spread that wear. The
custom-data block sits at 64 kB, with a copy in RAM that the engines read.

**Custom-data transfers** are decoded from the TIMBRE readings, one per
4 kHz poll. Plaits samples at a fixed point; the Seed's ADC runs freely,
so the age of each reading varies by up to one scan (0.2 ms). The host
tests decode a full 4 kB block across the timings libDaisy should give,
but this is the one feature whose margin depends on timing nobody has
measured on a real Seed yet: if transfers fail, report it.

## First power-up

Things to check, in this order, before the module goes in the case:

1. **LEDs**: the column may show a random pattern for the first two
   seconds (the bootloader). Then the top LED (D1) lights green: the
   first green model. Each press of the left button moves it one row down.
   If another LED lights, or the colours are swapped, the 74HC595 bit table
   in `src/plaits/drivers/leds.cc` disagrees with the board. If a second
   LED lights steadily next to a pulsing one, MODEL's zero is off: that is
   what calibration (step 4) fixes.
2. **Buttons**: the left button picks green models, the right one red
   models; holding one and tapping the other lights both button LEDs.
3. **Pots**: each knob turns the parameter printed above it, clockwise up.
4. **V/OCT**: calibrate, then check octaves with a tuner.
5. **Cable detection**: with TRIG unpatched the sound is steady (no
   low-pass gate); patch a trigger and it starts to ping. Patch an LFO
   into TIMBRE: the TIMBRE attenuverter now sets how much it moves.
6. **Audio**: OUT and AUX on the right jacks.

One difference from Plaits comes from the circuit, not the firmware: a
cable plugged into Plaitsy with its other end loose reads as about +1.5 V
(+1.8 V on V/OCT), where Plaits reads 0 V, because Plaitsy's input stages
sit at their bias voltage. It goes away as soon as the other end is
plugged into something.

## Testing

`test/` holds host tests, built with g++ under AddressSanitizer and UBSan.
They need WSL (or Linux) with g++, make and python3. From
`plaits/firmware`:

```bash
wsl.exe -e bash test/run_port_test.sh
```

```bash
wsl.exe -e bash test/run_voice_test.sh
```

- `run_port_test.sh` (about a minute; a group name such as `nav` runs one
  group): the UI, drivers and storage on a model of the board, 188 checks.
  CV scaling against Plaits' schematic, cable detection with ADC latency
  and noise, both navigations and the button gestures (not the knob turns
  for the hidden settings, nor the left-button power-up in `main.cc`),
  calibration with 1 % part errors, the LED and mux tables read from
  `../hardware/tools/circuit.py`, saving and power loss during saves,
  custom data, and a whole TIMBRE transfer through Plaits' own decoder.
- `run_voice_test.sh` (about two minutes, `--quick` 20 s): all 24 models
  rendered through the real DSP code at 82 settings each (no NaN, no stuck
  output), tuning (440.0000 Hz at the Seed's real rate), and the
  custom-data path.

## Licence

MIT; see [LICENSE](LICENSE). Plaits' code, stmlib and the FSK decoder are
© Emilie Gillet: the notice is at the top of each of those files, including
the ones `src/` adapts, and in `vendor/`. libDaisy is © Electrosmith, MIT.
The built firmware also contains STMicroelectronics' HAL drivers
(BSD-3-Clause) and parts of ST's USB libraries (SLA0044) from libDaisy, and
Gary S. Brown's CRC-32 table (free to use; `vendor/stmlib/utils/crc32.h`).
"Mutable Instruments" is a registered trademark and not used for this
module.
