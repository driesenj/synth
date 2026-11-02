# Side FXy firmware — four effect blocks on the Daisy Seed

Firmware for [Side FXy](../README.md), the RYK Modular SIDE FX clone on a
Daisy Seed. Like the original it runs four effect blocks, one per slot —
PITCH, DELAY, TEXTURE and REVERB — in seven serial and parallel
algorithms, with a send button per block, four assignable CV inputs, a
clock input, MIDI, two LFOs, a random source, an envelope follower and
presets. RYK publishes no manual and no code, so everything here is its
own design: the seventeen block types, how sends and mixes behave, the
screen and what the knobs do.

**BEADSY** is the Clouds/Beads-like effect: Mutable Instruments Beads'
own granular engine (MIT, from Émilie Gillet's eurorack repository),
ported as a fifth TEXTURE type. Its send button freezes it rather than
starving it, so its grains keep playing the last thing it heard.

> **Not yet run on hardware.** It builds and links for the Seed and passes
> the host tests (see [Testing](#testing)), but nothing here has been heard
> or seen on a module yet. Do the [first power-up checks](#first-power-up)
> before trusting it.

---

## The front panel

| Control | Does |
|---|---|
| PITCH, DELAY, TEXTURE, REVERB | Toggle that block's send (lit = on). Instant, even while the screen is busy. |
| SHIFT + a send button | Open that block's page; again: its next parameter page. |
| SHIFT, tapped alone | HOME > MOD 1 > MOD 2 > SENDS > SETUP 1 > SETUP 2 > SETUP 3 > HOME; from a block page, back to HOME. |
| K1..K4 | Each edits the screen row beside it. Turn slowly for fine steps (one semitone on a pitch, one step on a list), fast for big ones. |
| Push a knob (block page) | That row's modulation: K1 picks the source, K2 the depth, any push closes it. |
| SHIFT + push (block page) | Sync on or off for a time or a rate (a note symbol shows it). |
| SHIFT + turn K1 (block page) | The block type (it changes a quarter second after you stop turning). |
| Hold SHIFT at power-up | Firmware update (the Daisy bootloader). |

The screen's four rows sit beside the four knobs (K1 at the top). The
LED in SHIFT flashes on every beat of the tempo.

| Page | K1 | K2 | K3 | K4 |
|---|---|---|---|---|
| HOME | PRESET (turn: browse, push: load; SHIFT + push: save) | ALGORITHM | WET (push: its modulation) | TEMPO (push: tap; SHIFT + turn: 0.1 BPM) |
| block pages | the block's parameters, four per page, MIX the last row of the last page | | | |
| MOD 1 | LFO 1 RATE (push: sync) | LFO 1 SHAPE | LFO 2 RATE | LFO 2 SHAPE |
| MOD 2 | RND RATE | RND SMOOTH | ENV ATTACK | ENV RELEASE (push: ENV GAIN) |
| SENDS | PITCH gate source | DELAY gate | TEXTURE gate | REVERB gate (push: the send on / off) |
| SETUP 1 | DRY | IN GAIN | OUT GAIN | OUT POLARITY |
| SETUP 2 | MIDI CHANNEL | CC A | CC B | CLOCK PPQN |
| SETUP 3 | BRIGHTNESS | FLIP | ENCODER direction | TOOLS: CV ZERO or FACTORY (push, then confirm) |

HOME also shows the input and output meters, the CPU load, a MIDI
activity dot, the algorithm as a diagram (a block is filled while its send
is on, and fills with its output level) and the four blocks' names.

## The blocks

Each block has up to seven parameters (BEADSY eleven), plus the slot's
MIX. Times and rates marked ♪ can follow the tempo.

### PITCH

| Block | Parameters | What it does |
|---|---|---|
| DUAL SHIFT | PITCH A, PITCH B, DETUNE, DELAY ♪, FEEDBACK, WINDOW, WIDTH | Two pitch shifters (±24 semitones), each behind its own delay, A on the left and B on the right: harmonies, octave doubling, micro-detuned width. FEEDBACK sends each voice back through itself, so echoes climb or fall in pitch each time round. WINDOW is the splice length: 10 ms grainy and metallic, 150 ms smooth. |
| GRANULATOR | PITCH, SPREAD, DENSITY ♪, SIZE ♪, DELAY ♪, FEEDBACK, WIDTH | A "crowd" granulator: up to 24 grains of the last 5 s, each at PITCH plus a random offset within SPREAD and panned at random. Synced, the grains land on the tempo grid. FEEDBACK re-granulates its own output into clouds. |

### DELAY

| Block | Parameters | What it does |
|---|---|---|
| DUAL DELAY | TIME L ♪, TIME R ♪, FEEDBACK, CROSS, TONE, MOD, WIDTH | Two delays up to 10 s. CROSS goes from separate lines to ping-pong; TONE darkens or thins the repeats in the loop; above ~87 % FEEDBACK it runs away into (bounded) dub self-oscillation. Slow time changes bend like a BBD, big jumps crossfade. |
| BAND DELAY | TIME ♪, SPREAD, FEEDBACK, FREQ, Q, TILT, WIDTH | The input split into four resonant bands around FREQ, each with its own delay (SPREAD makes high or low bands later) and its own feedback through its band: echoes that come apart in pitch. |
| TAP DELAY | TIME ♪, PATTERN, TAPS, DECAY, FEEDBACK, SPREAD, TONE | Up to eight taps across a span (one bar when synced) in eight rhythms: EVEN, DOTTED, SWING, TRIPLET, CLAVE, ACCEL, DECEL, SCATTER. |
| TAPE DELAY | TIME ♪, FEEDBACK, HEADS, WOBBLE, DRIVE, AGE, WIDTH | A tape loop with three playback heads (1×, 2×, 3×) in seven combinations, wow and flutter, saturation, repeats that get darker and thinner with AGE. Turning TIME bends the pitch of the repeats like a real varispeed tape. |
| GLITCH | SLICE ♪, CHANCE, REPEATS, REVERSE, PITCH, CRUSH, SHUFFLE | A beat repeater: on each SLICE step, with probability CHANCE, it repeats the last slice 1–16 times, maybe reversed, bending in pitch (tape stops and speed-ups), crushed, or an older slice. Between glitches it passes the input, so at its default MIX of 100 % it is an insert. |
| MOD COMBS | FREQ, FEEDBACK, RATE ♪, DEPTH, VOICES, SPREAD, DAMP | One to four modulated combs per side: chorus, flanger, ensemble, or tuned Karplus-like resonance (FREQ 20 Hz–2 kHz, negative FEEDBACK for hollow odd harmonics). |

### TEXTURE

| Block | Parameters | What it does |
|---|---|---|
| PHASER | RATE ♪, DEPTH, CENTER, FEEDBACK, STAGES, SPREAD, SHAPE | 2–12 allpass stages swept by a sine, triangle or random LFO; SPREAD offsets left and right. At 50 % MIX the classic notches. |
| RESONATOR | PITCH, CHORD, DECAY ♪, DAMP, DETUNE, SPREAD, DRIVE | Four tuned resonators (C3 in the middle, ±24 semitones, 1 V/oct from a CV) in ten voicings: unison, octaves, fifths, major, minor, sus4, maj7, min7, add9, cluster. |
| WAVESHAPER | MODE, DRIVE, BIAS, TONE, BITS, RATE, LEVEL | SOFT, HARD, FOLD, RECTIFY, FUZZ or SINE shaping, oversampled, level-compensated, with bit and sample-rate crushing after it. |
| TAPE SIM | DRIVE, WOW, FLUTTER, AGE, HISS, DROPOUT, BUMP | Tape character without the echo: saturation, wow, flutter, treble loss, hiss (it follows the input, so silence stays silent), dropouts and the low head bump. |
| BEADSY | TIME, SIZE, SHAPE, PITCH, DENSITY ♪, FEEDBACK, REVERB, QUALITY, T RAND, P RAND, FREEZE | Beads' granular engine; see [BEADSY](#beadsy). |

### REVERB

| Block | Parameters | What it does |
|---|---|---|
| PLATE | DECAY, SIZE, PREDELAY ♪, DAMP, DIFFUSE, MOD, LOWCUT | A Dattorro figure-eight plate; DECAY reaches an endless hold at the top. |
| FDN VERB | DECAY, SIZE, PREDELAY ♪, DAMP, WIDTH, MOD, LOWCUT | An eight-line feedback delay network, RT60 0.2–60 s, FREEZE at the top of DECAY: the dub-techno wash. |
| MODAL | PITCH, STRUCT, DECAY ♪, BRIGHT, DENSITY, WIDTH, DRIFT | A tuned resonant body of 8–32 modes, from a harmonic string through bell to plate; PITCH follows 1 V/oct. |
| APF CHAIN | LENGTH ♪, STAGES, DIFFUSE, FEEDBACK, DAMP, MOD, WIDTH | 2–16 allpasses in a feedback loop: long dense smears and pads, or with short LENGTH metallic, springy chirps. |

### BEADSY

Beads' DSP, unchanged where it could be (`vendor/beads/`), with its
changed files in `src/beads/` (each lists its changes at the top):

- TIME, SIZE, SHAPE, PITCH, DENSITY, FEEDBACK and REVERB are Beads' knobs.
  DENSITY's centre is no grains; one side regular, the other random. SIZE
  at the very top is Beads' delay mode, where TIME becomes a ×1–×16
  multiplier.
- QUALITY: Beads' four media, DIRTY TAPE, CLEAN TAPE, LOFI 12BIT and HIFI
  16BIT. Changing it clears the buffer (about 40 ms of silence).
- T RAND and P RAND are what Beads' attenuverters do with nothing
  patched: clockwise spreads every grain's time or pitch evenly ("SPRD"),
  anticlockwise makes some grains jump far ("JUMP"). CV modulation comes
  from Side FXy's own sources on top.
- Synced, DENSITY feeds Beads' SEED input with sixteenths from the tempo:
  left of centre divides them (1/16 up to a bar), right of centre drops
  them at random.
- FREEZE, or the TEXTURE send off, stops the recording; the grains keep
  playing the buffer. Beads' own crossfade smooths the join when it starts
  again.

Differences from Beads, because of the hardware: the codec runs at
48 kHz throughout, so LOFI 12BIT (32 kHz on Beads) runs at 48 kHz, with
5.3 s of buffer instead of 8; at most 10 grains sound at once (Beads: 32),
to keep it within its share of the CPU until it has been measured
(`kMaxGrains` in `src/beads/dsp/delay_granular_player.h`). Beads always
fades out the four oldest grains when a new one starts, so with 10 a grain
lives about 7.5 trigger intervals: at high DENSITY long grains end sooner
than SIZE says (at 20 grains per second, about 0.4 s). Raise `kMaxGrains`
to 16–24 once the CPU load has been measured. Beads' reverb
stops computing after REVERB has been at zero for 5 s. Beads' wavetable
synth mode and its automatic gain control are not ported: Side FXy's IN
GAIN does the latter's job.

---

## Algorithms

The four slots always meet the signal in the order P(itch), D(elay),
T(exture), R(everb); the algorithm decides which run in series (`>`) and
which in parallel (`|`).

| # | Name | Chain | Good for |
|---|---|---|---|
| 1 | SERIAL | P > D > T > R | one long insert chain |
| 2 | P\|D>T>R | (P \| D) > T > R | pitch and delay side by side, both through texture and reverb |
| 3 | P>D\|T>R | P > (D \| T) > R | delay and texture as alternatives after the pitch block |
| 4 | P\|D\|T>R | (P \| D \| T) > R | three effects into one reverb |
| 5 | PD\|TR | (P > D) \| (T > R) | two stereo chains side by side |
| 6 | PARALLEL | P \| D \| T \| R | four separate send effects |
| 7 | DUAL MONO | IN 1 > P > D > OUT 1, IN 2 > T > R > OUT 2 | two mono chains; IN 2 is normalled to IN 1, so one mono source gives two different outputs |

Changing the algorithm dips the output for 5 ms each way; the blocks keep
running through it, so their tails survive.

## Sends, MIX, DRY and WET

Each slot mixes its block's wet signal with what reaches it, by its MIX
(equal power: at 50 % both are at -3 dB). The send button decides what
the block hears:

- **send on** (button lit): the slot mixes as its MIX says;
- **send off**: the block hears nothing new and the signal passes it
  untouched, while whatever the block still holds — echoes, a reverb tail,
  BEADSY's frozen grains — rings out on top. A send button is a dub throw:
  tap it on for a beat and the echoes keep going after it is off.

The buttons toggle the sends inside the control interrupt, so a throw lands
within a quarter of a millisecond whatever the screen is doing. A send can
also follow a CV, an LFO, the random source, the envelope or MIDI (SENDS
page): the source inverts the button while it is above about 1 V.

Parallel branches would each pass the dry signal, so the engine counts it
once: each stage takes out every branch's unprocessed part and adds the
input back once. The engine tracks that unprocessed part through the
whole chain, which gives two separate levels at the output:

- **DRY** (setup, global): the unprocessed signal. 100 % for an insert;
  0 % turns the module into a pure return for a mixer's send, so the
  stereo mixer's dry path and Side FXy's return never double up.
- **WET** (HOME page, per preset, modulatable): everything processed.

A soft limiter (linear to 0.75 of full scale, then a smooth knee that
never passes it) protects the outputs.

## Modulation

Any parameter, MIX included, and the preset's WET can follow one
modulation source at a depth of -100..+100 %:

| Source | Value |
|---|---|
| CV 1..4 | the jack, ±5 V. At +100 % depth a ±24-semitone pitch parameter tracks 1 V/oct |
| LFO 1, LFO 2 | sine, triangle, ramp up, ramp down, square, steps (S&H); 0.02..20 Hz or a note value from 4 bars to 1/64, locked to the bar |
| RND | a random value at its rate, stepped or gliding (SMOOTH) |
| ENV | the input's envelope: attack 1..500 ms, release 10 ms..5 s, gain 0..+24 dB |
| CC A, CC B | two MIDI controllers (numbers in the setup, default 1 and 11) |
| NOTE | the last MIDI note: one semitone per note on a ±24-semitone parameter at +100 % |
| GATE | 1 while a MIDI note is held |

## Tempo and clock

Every time and rate parameter can follow the tempo (SHIFT + push its
knob: a note symbol shows it is synced). The tempo comes from the first of:

1. **CLOCK** jack, at the PPQN set in the setup (1, 2, 4, 8, 12 or 24 per
   quarter note; default 4, sixteenth notes), while pulses keep coming;
2. **MIDI clock**, while it runs (START resets the bar);
3. the preset's own tempo (HOME page; push K4 to tap it).

Pulses are counted into 4/4 bars, so synced LFOs and GLITCH's slices stay
on the grid.

## MIDI

TRS type A, receive only, on the channel in the setup (or omni):

| Message | Does |
|---|---|
| Note on / off | NOTE and GATE sources (last note wins) |
| CC A, CC B (setup) | the CC A / CC B sources |
| CC 80..83 | sends PITCH, DELAY, TEXTURE, REVERB (64 and up: on) |
| CC 85 | WET |
| CC 120, 123 | all notes off |
| Program change *n* | preset *n* + 1 |
| Clock, start, continue, stop | the tempo (any channel) |

## Presets and the live state

64 presets live in the Seed's QSPI flash. Whatever is being played, edits
included, is saved on its own 5 s after the last change, so the module
powers up where it was; a preset only changes when it is saved over. On
the very first power-up the factory presets fill the first slots and INIT
presets the rest.

| Flash (from the chip's start) | Holds |
|---|---|
| 0x00000–0x0FFFF | settings: a wear-levelled ring of records |
| 0x10000–0x1FFFF | the live state: a wear-levelled ring of 512-byte presets |
| 0x20000–0x27FFF | the 64 presets, 512 bytes each |
| 0x28000–0x29FFF | the bank's journal: a sector being saved is written here first, so a power cut mid-save loses nothing |
| 0x2A000–0x3FFFF | free |
| 0x40000– | the program (the Daisy bootloader's QSPI area) |

Flashing a new firmware keeps all of it. A preset is 512 bytes with a
version and a CRC (`src/engine/preset.h`); anything that fails the check
loads as INIT.

---

## Flashing

The program is larger than the Seed's 128 kB internal flash, so it runs
with the **Daisy bootloader**, as Plaitsy and Marblesy do: the bootloader
lives in the internal flash, keeps the program in the 8 MB QSPI flash and
copies it to RAM at power-up. Flash the bootloader once, then the
firmware.

The simplest way is the [Daisy Web Programmer](https://flash.daisy.audio)
in Chrome:

1. Put the Seed in DFU mode: hold BOOT, press and release RESET, release
   BOOT. On the **Bootloader** tab, flash the bootloader.
2. Reset the Seed. Its LED now pulses for a couple of seconds at every
   power-up: the bootloader waiting for an upload. Press BOOT while it
   pulses to make it wait for good.
3. On the **File Upload** tab, upload `sidefxy.bin` from this folder (a
   build of these sources, so no toolchain is needed), or
   `build/sidefxy.bin` after building it yourself.

On Windows, the browser and `dfu-util` need the WinUSB driver for the
Seed's DFU device: see Electrosmith's "Zadig driver reset" page.

With the Daisy toolchain installed, the same from here:

```bash
make program-boot
```

```bash
make program-dfu
```

**Updating later**, with the module in the case: hold SHIFT while
powering up. Side FXy restarts into the bootloader, which waits until a new
`sidefxy.bin` arrives, so the Seed's own buttons are not needed (a USB
cable still has to reach the Seed's micro-USB port).

## Building

Needs the ARM GCC toolchain and GNU make (Electrosmith's Daisy toolchain
has both, plus `dfu-util`), and git. On Windows, run make from Git Bash,
with the compiler and `dfu-util` on its PATH.

```bash
make setup
```

```bash
make
```

`make setup` clones libDaisy v9.0.0 into `lib/libDaisy` (ignored by git)
and builds it; `make` builds `build/sidefxy.bin`. After a change to the
sources, copy that over `sidefxy.bin` here so the two stay the same. Point
`LIBDAISY_DIR` at another libDaisy checkout to use that instead, and set
`GCC_PATH` if the compiler is not on the PATH (a forward-slash path ending
in a slash), for example Arduino's STM32 core, which ships a usable
compiler:

```bash
make GCC_PATH=/c/Users/<you>/AppData/Local/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/
```

Memory use (libDaisy 9.0.0, GCC 14.2): 328 kB of the 480 kB the
bootloader allows in SRAM, 33 kB of the 128 kB DTCM, about 12 kB of the
200 kB block pool in D2 RAM, and about 18 MB of the 64 MB SDRAM for the
blocks' buffers.

---

## How it works

```
src/
  main.cc                 start-up, the audio callback, the main loop
  hal.h                   what the portable code needs from the board
  hal_daisy.cc            the board: chain scan, ADC, MIDI UART, QSPI, time, watchdog
  display_daisy.cc        the ST7789 over SPI1 with DMA, backlight PWM
  engine/                 slots, sends, mixes, algorithms, presets, parameters
  fx/                     the 17 blocks (dsp_util.h: small shared DSP pieces)
  beads/                  Beads' files this port had to change
  app/                    controls, tempo, modulation sources, MIDI, settings, preset bank
  gfx/                    frame drawing and the fonts
  ui/                     pages, rows, the algorithm diagram
vendor/                   Beads (pichenettes/eurorack f4cfa76) and stmlib (e3bd7c9), unchanged
test/                     host tests (WSL g++), with fakes for the board and the blocks
tools/                    make_fonts.py, check_pins.py
```

**Threads.** Two tiny interrupts come first (priority 0): MIDI bytes
(USART1, its 8-byte FIFO drained per interrupt, each byte stamped on
arrival) and CLOCK jack edges (an edge interrupt, so a trigger shorter than
a scan still counts). The audio interrupt (SAI DMA, priority 1) runs every
32 samples (0.67 ms): CV readings, tempo, the modulation sources, then the
engine and the four blocks. A 4 kHz timer interrupt (priority 2) scans the
shift-register chain — encoders, buttons, the five LEDs — and toggles sends
straight away. The main loop does everything slow: parsing MIDI, the UI and
its drawing, preset loads and saves, the stores, and the blocks' Reset()
when a type changes (clearing megabytes of SDRAM never happens in an
interrupt). Changes cross between them through 16-bit fields
the audio reads once per block, small lock-free rings, and the engine's
fade-detach-swap-attach handshake for anything structural.

**Memory.** Every block type exists all the time, created at boot; a slot
just points at the one it runs, so switching costs a fade and a Reset, never
an allocation. Block objects and their small hot state live in a 200 kB
pool in D2 RAM; delay lines, grain buffers and reverb tanks in SDRAM.
DTCM keeps the stack, the engine and the app.

**CPU.** The budget is 10,000 cycles per sample at 480 MHz. The blocks'
estimates (not yet measured) run from about 250 (PHASER) to 2650 cycles
(BEADSY at its worst); the heaviest block of each slot together come to
about 6,500, so even the heaviest combination should stay under about 70 %
with the engine and the interrupts. HOME shows the audio callback's load; each block page shows its
block's share. Times above about 90 % would mean dropouts: measure on the
first power-up.

**The screen.** The UI draws into a 170 × 320 frame in SDRAM and marks
the rows it changed; the main loop sends those rows to the ST7789 by SPI
DMA (12.5 MHz) whenever the previous transfer is done, so a full redraw
takes about 70 ms but a value change a few milliseconds. The fonts are
DejaVu Sans, pre-rendered with 4-bit anti-aliasing (`tools/make_fonts.py`).

**Flash writes** (preset saves, the live state, settings) happen in the
main loop; the audio and the control scan keep running because the
program runs from SRAM, not from the QSPI flash being written. They go
through Side FXy's own short QSPI routine rather than libDaisy's
`QSPIHandle::Write`/`Erase`: libDaisy rewrites the flash chip's
non-volatile status register on every call, which a live state saved
every few seconds would wear out, and it does not report failed page
writes. Every write is read back. A preset save takes up to about 0.8 s
(two sector erases); MIDI bytes arriving meanwhile wait in a 256-byte
buffer.

## First power-up

1. **Power and current.** Check ±12 V and 3V3 before the Seed goes in;
   remember the reversed −12 V diode on these boards. With everything
   running, measure the 3V3D current (display, LEDs, logic: about 60 mA on
   top of the Seed).
2. **The screen.** It should show HOME. Upside down: set
   `kPanelRotated180` in `src/display_daisy.cc` (or use SETUP 3 FLIP).
   Red and blue swapped: set MADCTL bit 3 there. Shifted by a band of noise
   at one edge: the column offset (35) differs on this module. Garbage or
   nothing: try a slower SPI or check the cable order (VCC, GND, DIN, CLK,
   CS, DC, RST, BL).
3. **Buttons and LEDs.** Each send button lights its own LED and nothing
   else; SHIFT's LED flashes on the beat. Wrong LED or button: the chain's
   bit order (see `tools/check_pins.py`, which checks the firmware against
   `circuit.py`).
4. **Encoders.** One step per detent, clockwise up. Two steps per click or
   every other click ignored: SETUP 3 ENCODER (and `steps_per_detent`). A
   few random steps when not turning: raise `kSettleCycles` in
   `src/hal_daisy.cc` (the chain's lines are long).
5. **CV.** With nothing patched, SETUP 3 TOOLS > CV ZERO. Then patch a
   known voltage and check the CV pages show it.
6. **Audio.** Send a signal through with all sends off: OUT should equal
   IN. Check the polarity against the dry signal (SETUP 1 OUT POLARITY).
7. **CPU.** Load the heaviest presets (the BEADSY ones) and watch HOME's
   CPU figure. Over about 85 %: lower `kMaxGrains` for BEADSY, or report
   which blocks are heavy.
8. **Clock and MIDI.** Patch a clock: TEMPO shows CLOCK and the right BPM
   at the PPQN set in SETUP 2. Send MIDI notes and program changes: the
   MIDI dot on HOME lights.

## Testing

Host tests run under WSL (or any Linux with g++), with AddressSanitizer
and UndefinedBehaviorSanitizer:

```bash
test/run_tests.sh
```

Each group in `test/groups/` links its own binary: `engine` (the engine on
fake blocks), one `fx_*` group per block, `app` (controls, tempo,
modulation, MIDI, storage and the whole App on a model of the board),
`gfx`, `ui` (which also writes a screenshot of every page to
`test/build/ui_screens/`), `factory_presets`, and `integration` (every
real block in every slot under every algorithm, with parameters jumping
and a loud input: no faults, nothing non-finite, the output bounded).

The board code (`hal_daisy.cc`, `display_daisy.cc`, `main.cc`) only runs
on the Seed; `python -B tools/check_pins.py` checks its pins and the
chain's bit order against `circuit.py`.

## Licence

MIT, see [LICENSE](LICENSE). Beads and stmlib are Émilie Gillet's (MIT);
the fonts are rendered from DejaVu Sans (Bitstream Vera licence, quoted
at the top of `src/gfx/fonts.cc`). "Mutable Instruments" is a registered
trademark and is not used for this module; SIDE FX is RYK Modular's, and
this firmware is an independent design, not RYK's.
