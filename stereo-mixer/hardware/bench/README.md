# Mute test kit (test report M1)

**Status 2026-11-15: the mixer no longer has the AQY212EH.** The mutes are now
one CD4053B per channel at the buses' summing ends, where the switch carries
no signal voltage ([design.md](../../docs/design.md), "Channel inputs and
mutes"), so M1 is gone and the breadboard test below is no longer needed to
decide anything. The kit still works as it is: as a THD / intermodulation /
null-test bench for a built channel (record the channel against a straight
wire instead of without / with a part), or to compare switch parts on the
stand-in. What follows is the kit as it was built for the PhotoMOS.

An off AQY212EH is not an open switch. It is a capacitance from the
channel's FI node to GND, 79 pF at 0 V falling to 35 pF at 7.5 V, and
because it changes with the voltage it distorts. The suite's two models
of the part bracket how much. This kit measures it: record one channel
without the PhotoMOS, then with it, and compare the two. The test signals
come from the kit, and so does the analysis (THD, intermodulation, and a
null test on a loop of your own).

Everything runs on what is already installed here: Python, numpy and
Pillow (for the plots).

```bash
python mute_test.py selftest
```

That checks the analysis against signals with a known answer (injected
harmonics, intermodulation products, and a non-linear term hidden under a
delay and a filter). It should say `all passed`.

## What you need

- An audio interface with a line out and a line in, and a DAW or any
  recorder. Use 96 kHz if the interface does it: at 48 kHz the 10 kHz
  test cannot see its third harmonic (30 kHz).
- ±12 V: the Eurorack supply through a ribbon to a breadboard, or a bench
  supply.
- A TL074 (or two TL072s), an AQY212EH, 22k, 2 × 30k, 2 × 10k, 100k,
  2 × 100 nF (one from each rail to GND at the chip).
- A multimeter with AC volts.

## The stand-in

One channel as it is on the main board: a low-impedance source, then 22k
into the FI node, the PhotoMOS from FI to GND, and the follower. The 22k
stands for the 10k series resistor plus the LEVEL pot's own source
resistance. With the full 10 V p-p, it gives the distortion the report
predicts for the worst LEVEL setting.

```
                ×4: U1A                     the channel                       ÷4
 interface ──── + ┐                                                 
 OUT (tip)        U1A ──┬── 22k ──┬── FI ── + ┐                        
            ┌──── − ┘   │         │           U1B ──┬── OUT ── 30k ──┬── interface
            ├── 30k ────┘         │       ┌── − ┘   │                │   IN (tip)
            10k               AQY212EH    └─────────┘               10k
            │                 pins 3-4                               │
           GND                to GND                                GND
                         (pins 1-2 open)
```

- U1A, gain ×4: 30k from its output to its − input, 10k from − to GND.
  Interface outputs differ a lot, and the ×4 means it only has to give
  about 0.9 V rms. If yours gives 3.6 V rms cleanly, leave U1A out and
  drive the 22k directly.
- U1B is the follower, as on the board: output tied to its − input.
- The ÷4 divider brings 10 V p-p down to about 0.9 V rms for the line
  input.
- The AQY212EH goes in for the second set of takes. Pins 3 and 4 (the
  switch, either way round) go from FI to GND. Pins 1 and 2 (its LED) stay
  open, which is "not muted": the state in which it distorts.
- Use the tip and sleeve of the interface's jacks (a TS cable, or a TRS
  with its ring unconnected).

### Wiring by pin (TL074)

| Pin | Connect to |
|---|---|
| 4 | +12 V, with 100 nF to GND at the pin |
| 11 | −12 V, with 100 nF to GND at the pin |
| 3 (U1A +) | interface OUT tip, and 100k to GND so it never floats |
| 2 (U1A −) | 10k to GND, 30k to pin 1 |
| 1 (U1A out) | 22k to pin 5 |
| 5 (U1B +) | FI: the 22k, and later the AQY212EH's pin 3 |
| 6 (U1B −) | pin 7 |
| 7 (U1B out) | OUT: the meter, and 30k to the interface IN tip |
| interface IN tip | 10k to GND |
| 10, 12 | GND (the unused sections C and D) |
| 9, 13 | pin 8 and pin 14 (C and D as followers, so they keep quiet) |

Also:
- The AQY212EH, for the second set of takes: pin 3 to pin 5, pin 4 to
  GND, and pins 1 and 2 left empty.
- Keep the wire from pin 5 short, and leave everything else exactly in
  place between the two sets: the only change is the part going in.
- 33k in place of the 30ks works too. The levels are set on the meter
  anyway.

Before the first tone, turn the interface's output (or the DAW fader) well
down. A full-scale signal ×4 would clip U1A at the rails.

## The takes

1. Write the test signals:

   ```bash
   python mute_test.py tones
   ```

   That writes `tones/`: 96 kHz, 24-bit, peak −3 dBFS, 10 s each (`--rate
   48000` if the interface can't do 96 kHz). Set the DAW project to the
   same rate so nothing gets resampled.

   | File | What it shows |
   |---|---|
   | `cal-50hz.wav` | sets the level, and checks nothing moved between the runs |
   | `sine-1k.wav` | THD at 1 kHz |
   | `sine-10k.wav` | THD at 10 kHz (the harmonics are ultrasonic, so this one checks the model, not what you hear) |
   | `ccif-19k-20k.wav` | twin-tone intermodulation: products at 1, 17, 18, 21, 22 kHz |
   | `smpte-60-7k.wav` | bass modulating treble: sidebands round 7 kHz, 60 Hz apart |
   | `pink-noise.wav` | the null test on a full-band signal |

   Add a loop of your own as well: 10–60 s, bright, with bass under it
   (hats, noise, a bright pad over a bass line), normalised to a −3 dBFS
   peak. Name it, say, `loop.wav`. That is the test that tells you whether
   you will hear it.

2. **Level, without the PhotoMOS.** Play `cal-50hz.wav` on a loop and set
   the interface's output so the meter on OUT (U1B's output, AC volts)
   reads **3.54 V**, which is 10 V p-p. A meter is accurate at 50 Hz, not
   at 1 kHz; the PhotoMOS does nothing at 50 Hz. Set the input gain so the
   recording peaks well below 0 dBFS. **From here on do not touch either
   level** until all the takes are done.

3. **Record every file into `rec/without/`**, each recording under the
   same name as the file played (`rec/without/sine-1k.wav`, and so on,
   plus your loop). Start the recording a little before the playback. The
   alignment is found by the script, so the start doesn't need to be
   exact.

4. **Record `pink-noise.wav` and your loop again into `rec/without2/`.**
   Two takes without the part differ only by noise and hum: that is the
   floor of the null test.

5. **Power off, plug in the AQY212EH, power on**, and record everything
   again into `rec/with/`.

6. Compare:

   ```bash
   python mute_test.py report rec/without rec/with --floor rec/without2 --cal-vrms 3.54
   ```

   It prints a table for each test and writes spectra (`results/*.png`)
   and the residuals of the null test (`results/*-residual.wav`).

## Reading the result

- **The cal line** has to match within 0.05 dB between the two runs. If it
  doesn't, a level moved, and the comparison is off.
- **THD and intermodulation** tables give the "without" and "with"
  columns and the stand-in's predicted range. The low end of that range
  is the anti-series MOSFET model, the high end the single-varactor
  model.
  - In or below the range: the model holds, and M1 is as documented.
  - Well above it: look at the breadboard first (a long FI wire, a
    missing decoupler).

  Both models put nearly all of it in odd orders (H3, d3, f2 ± 2f1).

  | Test | Predicted for the stand-in, 10 V p-p |
  |---|---|
  | THD 1 kHz | 0.04–0.16 % (H3 −68 to −56 dB) |
  | THD 10 kHz | 0.39–1.55 % (H3 −48 to −37 dB) |
  | CCIF 19 + 20 kHz | 0.34–1.24 % (d3 at 18 / 21 kHz −53 to −41 dB) |
  | SMPTE 60 Hz + 7 kHz | 0.26–1.0 % (f2 ± 120 Hz −55 to −43 dB) |

- **What you can hear.** The 10 kHz harmonics are at 30 kHz and above.
  The CCIF products sit at 17–22 kHz, at the top of hearing. The tests
  that land in the audible band are SMPTE and the loop: bass swinging the
  capacitance while the treble passes through it.
- **The null test** subtracts the "with" take from the "without" take.
  - *Gain and delay matched* is every difference.
  - *After the best linear filter* also takes out the part's slight treble
    change (a few tenths of a dB at 20 kHz). What is left is the
    distortion, beside the floor's figure. The octave table shows where it
    is. Expect it to rise with frequency.
  - `results/loop-residual.wav` is that remainder, boosted by the amount
    printed. `loop-floor-residual.wav` has the same boost, so the two
    compare directly. Turn the monitors down first.
- **The decision is the listening test.** Load `rec/without/loop.wav` and
  `rec/with/loop.wav` on two tracks and play them at full level, blind:
  someone else solos one at random, or use an ABX comparator. If you can't
  tell them apart, keep the AQY212EH. The report's alternative, the
  G3VM-351AY1, can go through the same stand-in: record a `rec/g3vm/` set
  and run `report rec/without rec/g3vm`.

For reference, the kit's own simulation of these takes used the harsher
single-varactor model and interface noise at −105 dBFS. It gave:
- THD: 0.16 % at 1 kHz, 1.48 % at 10 kHz.
- Intermodulation: CCIF 1.25 %, SMPTE 1.01 %.
- Null test on pink noise: −47 dB re the signal after the linear filter,
  25 dB above the floor, and 29 dB above it in the 16 kHz octave.

The anti-series model gives about a quarter of those figures (−12 dB).

## On a built mixer

Fit one channel's AQY212EH in a socket: a DIP-4, or four contacts cut
from a turned-pin strip, fits the same holes. Pull the chip and that
channel plays without the PhotoMOS; it just cannot mute.

- **Into the channel's input:** the interface through U1A, as above.
- **Out:** OUT L to the line input through the ÷4 divider.
- **Settings:** PAN hard left, LEVEL at about three quarters, where the
  model has the most distortion; MASTER where it gives 10 V p-p at OUT L
  on the cal tone.

Take the same sets with and without the chip.

## Other commands

```bash
python mute_test.py analyse rec/with/sine-1k.wav --cal rec/without/cal-50hz.wav 3.54
```

```bash
python mute_test.py null rec/without/loop.wav rec/with/loop.wav --floor rec/without2/loop.wav
```

`--channel 1` reads the right channel of stereo recordings.
