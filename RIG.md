# Rig overview

Two cases of DIY modules, a **drum case** and a **voice case**, plus the
firmware for the digital modules, which lives in this repo. Status as of
2026-09-28.

## Format and power

- **Format:** most modules are Kosmo format (20 cm panels) with Eurorack power
  headers on the boards. The Atari Punk Console is a Eurorack module.
- **Supply:** each case has its own power board, a custom PCB built on the
  MKI x ES.EDU PSU (manual: `instrukcija_2.pdf`). The reference design feeds
  12 V DC from a wall adapter into a Mornsun URA2412LD-30WR3 DC/DC converter
  (±12 V, rated 1.25 A per rail). A resettable fuse and a Schottky diode
  protect against a reversed plug. The board also has ±12 V indicator LEDs and
  keyed 16-pin bus sockets. +5 V is optional (a 78M05 footprint).
- **Budget:** the kit's adapter is 12 V / 1 A. If that is what feeds a case,
  the adapter is the ceiling rather than the converter: about 10 W of ±12 V
  after conversion losses. The digital modules draw the most, so measure the
  adapter current before adding modules to a case.

## At a glance

### Drum case

| Module | Based on | Status | Code / manual |
|---|---|---|---|
| Drum sequencer | Own design, NUCLEO-L476RG | 99 % | `DrumSequencer/` |
| Kick | MKI x ES.EDU Kick Drum | Working, feels low on impact | `KICKDRUM_MANUAL_5wVQsEK.pdf` |
| Snare | MKI x ES.EDU Snare Drum | Working | `SNARE_MANUAL_Q9zNEN3.pdf` |
| Hi-hat | MKI x ES.EDU Hi-Hat | Working | `HIHAT_MANUAL_1.pdf` |
| FM drum | MKI x ES.EDU FM Drum | Debugging | `FM_DRUM_MANUAL_v2.pdf` |
| Mixer | MKI x ES.EDU Output Mixer 2, widened to 10 channels | In use | `OUTPUT_MIXER2_MANUAL_v2.pdf`, `MIXER_MANUAL.pdf` |
| Output | MKI x ES.EDU output stage | In use | `OUTPUT_MIXER2_MANUAL_v2.pdf`, `DIY_EDU_Output_Manual.pdf` |
| Cowbell + rimshot | Roland drum-machine circuits | PCB designed, untested | `ROLAND_TR-909_SERVICE_NOTES.pdf`, `Roland TR-808 Service Manual.pdf`, `cow_bell_Manual.pdf` |
| Compressor | MKI x ES.EDU Compressor | PCB designed, untested | `EDU_COMP.pdf` |
| Clap | Roland TR-808 or TR-909 | PCB designed, untested | `Roland TR-808 Service Manual.pdf`, `ROLAND_TR-909_SERVICE_NOTES.pdf` |

### Voice case

| Module | Based on | Status | Code / reference |
|---|---|---|---|
| Clock | Own design, Arduino | In use | `analog-clock/` |
| Sequencer | Own design, Arduino Mega | In use | `8-step-sequencer/` |
| VCO ×2 | AS3340 | In use | — |
| Bass VCO | Own design, Daisy Seed | Firmware reworked, [to test on the module](#firmware-rework-2026-09-28) | `baisy-seed/` |
| Dual VCF | MS-20 style with LM13700 | In use | [LMNC Simple Filter](https://www.lookmumnocomputer.com/simple-filter) |
| Dual VCA | LM13700 | In use | [sandelinos dual VCA](https://sandelinos.me/diy/LM13700-dual-VCA/) |
| Quad EG | Probably 4× MKI x ES.EDU EG | In use | `EG_MANUAL_v3.pdf` |
| Atari Punk Console | — | In use | — |

Manuals are in `C:\Users\joep\Code\synth\Manuals`, outside the repo. The PCB
designs are in EasyEDA and not exported here yet.

---

## Drum case

### Drum sequencer — `DrumSequencer/`

STM32 NUCLEO-L476RG, STM32CubeIDE project. 15 gate outputs.

- **Patterns:** per channel, two banks (A/B) of up to 64 steps, edited eight
  at a time. Each channel has its own length, swing, random amount (the chance
  a step's hit is dropped or an extra one added), ratchets (1–8 hits per step),
  mute and solo. A channel can also have its own BPM; it then free-runs on the
  internal timer, even when the rest follows an external clock.
- **Live / commit:** in commit mode, edits are staged and take effect together
  on ALT + RECORD, so the next pattern can be prepared while the current one
  plays.
- **Clock:** one jack, two directions. EXT: input, one step per pulse (16ths),
  tempo measured over the last 8 pulses. INT: 20–300 BPM from the encoder or
  tap tempo, and the jack outputs 16th-note pulses at 50 % duty.
- **Presets:** 8 slots in flash (steps, ratchets, lengths, BPMs, random, swing,
  mutes, banks).
- **Hardware:** 3 encoders on TIM1–3; step, ALT, FILL, RECORD and encoder push
  buttons on an MCP23017; 128×64 OLED on I²C with DMA; a 16×32 LED matrix from
  eight MAX7219s (row 0 is the current channel's 8-step window and playhead,
  rows 1–15 are the channels); step LEDs and gates on three 74HC595s.

| | Turn | Push | ALT + turn | ALT + push |
|---|---|---|---|---|
| **Encoder A** | Select channel | Solo | Channel random | Mute |
| **Encoder B** | Length | Ratchet mode | Channel swing | Realign channel to the master step |
| **Encoder C** | Scroll the 8-step window | Save/load menu | Channel BPM | Reset channel settings |

- **ALT + step 1** (held) is ALL: the ALT functions then act on every channel
  (global random and swing, internal BPM on encoder C, mute all, realign all,
  reset all settings, clear all, bank switch for all).
- **ALT + step 2** clears the channel, **3** toggles live/commit, **4**
  toggles INT/EXT clock, **5–8** roll the current channel at 1/16, 1/32, 1/64
  and 1/128 while held.
- **FILL** held: a hit on every step of the current channel. **ALT + FILL**:
  switch bank A/B.
- **RECORD**: set the current step and fire it. **ALT + RECORD**: commit (in
  commit mode) or tap tempo (in live mode).
- **Ratchet mode:** hold steps and turn B to set their hit count; C scrolls; a
  push on B leaves the mode.

Note: `HC595_clear()` writes 0xFF to the two gate registers, so all 15 gates go
high for a few microseconds at boot before `main()` clears them. If every drum
fires once at power-up, that is why.

### Kick — MKI x ES.EDU Kick Drum

808-style bridged-T oscillator with its own gate-to-trigger converter.
Controls: pitch, decay, pitch-envelope decay and depth, pitch CV amount, tone
(a low-pass for the click) and distortion. Inputs: trigger, pitch CV, accent CV.

**Open issue: feels low on impact.** Places the manual's design notes point to:

- **Accent.** Hit strength follows the ACCENT input: roughly a 2 V trigger at
  0 V accent, capped near 5 V at full accent. An unpatched input that *floats*
  plays at full accent. If the jack's switch grounds the input when nothing is
  patched, every hit plays at minimum accent. Test: patch a steady +5 V into
  ACCENT and compare.
- **Pitch envelope.** The punch is the pitch sweep. Its ceiling (about 250 Hz)
  is set by the 2 kΩ between the pitch-control transistor and ground. Its decay
  range is set by the 220 nF capacitor. The 5.6 nF smoothing capacitor rounds off the
  drop (bigger means smoother and less snap).
- **Tone.** A 50 kΩ / 15 nF low-pass that goes down to 220 Hz, where it removes
  the click completely. Open it fully before judging the punch.

### Snare — MKI x ES.EDU Snare Drum

The kick's bridged-T oscillator with a pitch envelope for the drum. White noise
goes through its own envelope and VCA and a steep high-pass for the snares.
Pitch CV and snappy CV inputs.

### Hi-hat — MKI x ES.EDU Hi-Hat

808/606 style: six square-wave oscillators on a 40106 feed a resonant
band-pass, then distortion, an envelope-controlled VCA and a resonant
high-pass. Tune works by lowering the 40106's supply voltage. A CV input opens
the hat (there is no separate open-hat trigger). Tune CV input.

### FM drum — MKI x ES.EDU FM Drum

909-derived. Two triangle VCOs reset on every trigger, and the FM switch lets
one modulate the other. The rest of the voice: a triangle-to-sine shaper, a
pitch envelope (tune decay and depth), a decay envelope, "impact" distortion,
an added click and a high-pass. An XOR of the two square waves gives a noisy
pulse voice, selected with the sine/pulse switch. Tune CV and decay CV inputs.

**Open issue: debugging.** The manual's troubleshooting appendix (pp. 76–82)
gives the expected signal at nine nodes, TP1–TP9 on the MKI board. If your PCB
doesn't label them, find the same nodes on the schematic. Work through them in
order:

| Node | What it is | Expect |
|---|---|---|
| TP1 | Trigger / pitch envelope | 0 V idle; about 7.6 V on a trigger, then falling (tune decay/depth knobs) |
| TP2, TP3 | VCO 2 (TUNE 2), triangle and square | Triangle about +5.4/−5 V, square about ±11 V; a glitch (reset) on each trigger |
| TP4, TP8 | VCO 1 (TUNE 1), triangle and square | Triangle about +4.6/−4.2 V with FM off; speeds up and slows down with FM on; pitch jumps on a trigger |
| TP5 | Sine shaper | TP4 with rounded tips, about ±0.5 V; louder and distorted on each hit |
| TP7 | Decay envelope | 0 V idle; about 8.5 V on a trigger, then falling (DECAY) |
| TP9, TP6 | XOR pulse, then high-passed | Irregular pulse about +10/−12 V; at TP6 strongly high-passed, about +13/−14.5 V |
| Output | Output stage | Test points fine but no sound: check the output transistor (VT12) and switch SW2 on the MKI schematic |

### Mixer — MKI x ES.EDU Output Mixer 2, 10 channels

The Output Mixer 2 design widened from four channels to ten. Each channel has
an FX send and a level to the main mix. There is an FX send output, a return
input and a drive knob. In the MKI design the drive knob blends the clean and
diode-clipped mix, so it changes the texture without changing the level.

### Output — MKI x ES.EDU output stage

L/R out with headphone and line outputs. In the Output Mixer 2 this stage is
AC coupling, then an NJM4556 headphone driver on both sides and an op-amp line
out, both at a gain of about 0.33 (±5 V modular level down to line level). The
older MKI Output Mixer (`DIY_EDU_Output_Manual.pdf`) is a two-input panning
mixer with a discrete headphone amp.

### Cowbell + rimshot — PCB designed, untested

Roland-derived. The TR-909 has a rimshot but no cowbell; the analog cowbell is
the TR-808's (two square-wave oscillators into a band-pass).
`cow_bell_Manual.pdf` is Erica Synths' cowbell module (tune, decay, tune CV with
attenuator, accent input, manual trigger), useful as a feature reference.

### Compressor — MKI x ES.EDU Compressor — PCB designed, untested

A diode-based VCA driven by a peak detector. Controls: threshold,
ratio, attack, release, input gain and make-up gain. It also has a side-chain
input, a gain-reduction LED and an LED VU meter. In the MKI drum system it sits
on the mixer's send/return or insert, which is where the mixer's FX out/in
would take it.

### Clap — PCB designed, untested

A TR-808 or TR-909 hand clap. Both service manuals are in the Manuals folder;
they are scans with no text layer.

---

## Voice case

### Clock — `analog-clock/`

Arduino (Uno/Nano pin map), TM1637 4-digit display.

- The encoder sets 20–300 BPM. Push it to choose one of 24 division sets
  (powers of two, integers, odd numbers, primes, Fibonacci, squares, cubes and
  more); the display scrolls the chosen set.
- 7 outputs, 15 ms pulses. Output 1 ticks every 16th note at the displayed
  BPM. Outputs 2–7 divide it by the chosen set (for example /2 /4 /8 /16 /32
  /64).
- A play/pause switch; pausing resets the dividers so they restart in phase. A
  switch sets the BPM LED to blink on every tick or every fourth.
- Each set's scrolling text lists eight numbers, but there are seven outputs:
  the last number of each set is never used.

### Sequencer — `8-step-sequencer/`

Arduino Mega. Two rows (A, B) of eight steps, each step with a pot, a button
and an LED. Outputs: CV A/B (MCP4725 DACs plus an output amp; the sketch
calibrates the gains) and gate A/B. Clock input: one step per rising edge, and
the gate length follows the measured clock period.

- **Mode knob** (8 positions): A then B · ping-pong · CV/duty (row A is pitch,
  row B is each step's gate length, SQ-1 style) · CV/duty random · random over
  all 16 steps · CV slide (row A glides across each step) · A-B-A-B alternating
  · A and B in parallel.
- **Transition knob** (4 positions): gate on/off (disabled steps are rests) ·
  active step (disabled steps are skipped) · slide (portamento over the gate) ·
  step jump (press a step to jump there on the next clock).
- **Duty knob:** gate length as a fraction of the clock period.
- **Step buttons:** a tap toggles the step. Holding one repeats it until
  released, then the sequence carries on from where it was.
- **Shift + step 1–4:** the row's range, 1, 2, 5 or 8 V. **Shift + step 5–8:**
  the row's quantizer: off, minor, major or chromatic.
- The mode, transition and duty knobs go through an ADS1115; the 16 step pots
  use the Mega's own ADC.

### VCO ×2 — AS3340

Two VCOs on the AS3340 (a CEM3340 clone).

### Bass VCO — `baisy-seed/`

Daisy Seed, built in the Arduino IDE (DaisyDuino on the STM32 core). Despite
the name it is a whole mono voice: oscillators, drive, filter and VCA, with its
own ADSR on the VCA, so it needs a gate to make a sound.

- **Oscillator:** sine, triangle, saw or square (WAVE knob); the saw and
  square are band-limited. Two detuned copies (up to ±50 cents) fade in with
  DETUNE. A sub an octave down (SUB knob) also frequency-modulates the main
  oscillator (FM knob).
- **Drive:** ×1–×31 into soft clip, hard clip or fold. In Bit mode the DRIVE
  knob sets the bit depth instead, from 16 bits down to 2.
- **Filter:** Moog ladder low-pass, or SVF low-pass, high-pass, band-pass or
  notch. Cutoff, resonance and envelope amount knobs.
- **LFO:** sine, triangle, saw or square to pitch, cutoff, amplitude or
  waveform. On pitch, its depth follows the rate knob.
- **Glide:** exponential, with a time constant of 0.5 s × Glide²: 0.30 is about
  45 ms, 0.50 about 125 ms, 1.00 half a second.
- **Inputs:** 1 V/oct, CV 1 and CV 2 (each assignable to pitch at 1 semitone
  per volt, cutoff, amplitude or FM), gate.
- **UI:** 9 pots, 2 encoders and a 128×64 OLED with three pages. Parameters:
  base note, ADSR, glide, LFO shape and target, filter mode, distortion, CV
  targets. A live view of every knob and input. Settings: two-point calibration
  (1 V and 5 V) of each CV input, brightness, save/load and factory reset.
  Settings are stored in the Seed's QSPI flash.
- **Build:** the board settings are in `baisy-seed/sketch.yaml` (Generic
  STM32H7 Series, Daisy Seed, USB CDC, upload over DFU), so
  `arduino-cli compile baisy-seed` needs no flags. The Arduino core runs the
  Seed at 400 MHz.

#### Firmware rework (2026-09-28)

Not yet tested on the module; the old sketch is kept as
`baisy-seed.ino.orig`. The issues found on 2026-09-28, and what changed:

1. **The display stalled everything else.** A full OLED redraw blocks I²C for
   about 25 ms, and the gate, CV inputs, knobs and encoders were read in
   `loop()`. Now they are read once per audio block (1 kHz) in the audio
   callback, and `loop()` only runs the menu, the display and the flash. The
   gate has an edge interrupt, so a trigger shorter than a millisecond still
   starts a note. The display sends only the rows that changed.
2. **Coarse pitch.** `analogRead()` gave 10 bits (about 9 cents per step) and
   powered the ADC up and down on every call. The ADC is now set up once, and
   1V/oct is the average of 16 16-bit conversions per block: a new note lands
   within a block, a held one is smoothed. With simulated ADC noise, pitch
   jitter went from 1–3 cents to under 1.
3. **Fold and bit-crush could silence the voice until a reboot.** Every drive
   type now ends within ±1: the fold folds any level back, and Bit mode no
   longer adds the ×31 gain. A filter that still blows up restarts instead of
   staying silent.
4. **The saved envelope wasn't applied at boot.** All settings are now applied
   every audio block from one live copy.
5. **Glide and LFO target weren't saved on their own.** Every save now writes.
   The comparison that decided left them out, and it read the flash through
   the data cache, which can be stale after a save.
6. **Factory Reset reset nothing.** It now restores the defaults, calibration
   included.
7. **Glide was nearly on/off.** See the curve above. The detuned copies now
   glide with the main oscillator, and LFO pitch modulation goes on top of the
   glide instead of through it.
8. **Aliasing.** The band-limited saw and square have about 16 dB less aliasing
   on a 1760 Hz note. The triangle stays plain: it barely aliases, and
   DaisySP's band-limited triangle is a rounded square.

Saved settings are converted on the first boot. The calibration carries over,
glide moves to the new curve, and an envelope that was never edited becomes
what the old firmware actually played (A 0.1 s, D 0.1 s, S 0.7, R 0.2 s).

Smaller fixes: the knobs page showed Sin for the WAVE knob at full, and
voltages between 0 and −1 V without the minus sign. With both CVs on FM, only
CV 2 counted. Save, Load and Factory Reset now show Done!. A calibration that
sees no change between 1 V and 5 V shows Failed and keeps the old values.
Pushing encoder 1 cancels a calibration; turning it no longer moves the cursor
behind the calibration screen.

To check on the module:

- All knobs and CV inputs respond (the ADC setup is new code).
- Short triggers (the drum sequencer's rolls) and fast encoder turns.
- Re-run Cal 1V/Oct: readings are 16-bit now, so a fresh calibration tracks
  better than the carried-over one.

### Dual VCF

Two MS-20-style filters with LM13700s, after the Look Mum No Computer
[Simple Filter](https://www.lookmumnocomputer.com/simple-filter).

### Dual VCA

Two LM13700 VCAs, after [sandelinos' dual VCA](https://sandelinos.me/diy/LM13700-dual-VCA/).

### Quad EG

Four envelopes, each with attack, sustain and release knobs. The design isn't
recorded, but the knob set matches the MKI x ES.EDU EG (`EG_MANUAL_v3.pdf`): a
"fake ADSR" whose decay and release share one knob, with a loop switch and an
inverted output.

### Atari Punk Console

A Eurorack APC.

---

## Clock and sync

- **Everything counts 16th-note pulses (4 PPQN):** the clock's output 1, the
  drum sequencer (one step per pulse; its BPM reading is a quarter of the pulse
  rate), the 8-step sequencer (one step per pulse) and the Meowsic keyboard's
  clock input.
- **Either case can be master:** the clock's output 1 into the drum sequencer
  on EXT, or the drum sequencer on INT, with its clock jack into the 8-step
  sequencer.
- **No reset or run line.** After a stop, both sequencers carry on from where
  they were; the clock's pause only realigns its own dividers. The drum
  sequencer's realign (ALT + encoder B push) lines channels up with its master
  step count, not with bar 1. A reset pulse from the clock on play, plus a reset
  input on both sequencers, would close this.
- **Spare drum channels as CV.** Fifteen gate channels outnumber the drum
  voices (seven once the planned modules are built). A spare channel into the
  kick's ACCENT or the hi-hat's open input gives per-step accents or open hats,
  at whatever level the gate outputs swing.

## Also in this repo

`meowsic-keyboard/` is a circuit-bent Bontempi Meowsic turned into an ESP32
MIDI/CV controller: two CV/gate pairs (1 V/oct), a clock input (16ths), an AUX
CV output, MIDI in/out, a looper and an arpeggiator. It isn't in either case,
but it can play and clock the voice case. See its README.

## Where things live

| What | Where |
|---|---|
| Firmware | This repo: `DrumSequencer/` (STM32CubeIDE), `analog-clock/`, `8-step-sequencer/` and `baisy-seed/` (Arduino IDE), `meowsic-keyboard/` (PlatformIO) |
| Manuals | `C:\Users\joep\Code\synth\Manuals`: MKI x ES.EDU build manuals, the PSU manual (`instrukcija_2.pdf`), Roland TR-808/909 service manuals |
| PCB designs | EasyEDA, not exported to the repo yet |

The Manuals folder also holds manuals with no module in the rig yet: the
MKI x ES.EDU VCO, VCF (diode ladder), VCA, 5-step sequencer, sample & hold,
wavefolder, BBD delay (the drum system's other send effect), drum sequencer and
the Labor prototyping board, plus a CCRMA paper on the TR-808 cymbal circuit.

## Open questions

Things the code and manuals don't settle:

1. Clap: TR-808 or TR-909?
2. Cowbell: the 909 has none, so is it 808-style or modelled on the Erica
   Synths / e-licktronic cowbell?
3. Quad EG: four MKI EGs? Does it have the loop switches and inverted outputs?
4. Output: the Output Mixer 2's output stage, or the original two-input Output
   Mixer?
5. Power: which adapter feeds each case, and is the +5 V regulator fitted?
6. Drum sequencer: what voltage do the gate outputs swing, and what is in the
   last 1 %?
