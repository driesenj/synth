# Atlasy — circuit

2026-10-31. The netlist is in `hardware/tools/circuit.py` (369 parts, its
`check()` at 0 problems); `hardware/tools/sim.py` computes the filter's and
the scanner's behaviour from those part values. Not yet drawn as a
schematic or placed: the board count is open (end of this page).

## What Atlas is

From Vostok's manual and the CDM interview with its designer, Jose Angel
Cabrera:

- Four filters on SSI2164 gain cells, "80s Japanese" (SH-101, Juno, Jupiter,
  TR) in spirit, with clean self-oscillation and a "super-accurate
  resonance compensation": no loss of bass in LP or of air in HP as
  resonance rises.
- Modes LP 4-pole (24 dB/oct), HP 2-pole (12 dB/oct), BP 4-pole (HP and LP
  in series).
- Per channel: IN, FREQ CV, FM2/RES CV (switch), OUT, FREQ and RES knobs,
  mode switch, a lit numeral. IN and FREQ are normalled to the next
  channel. All CV inputs take 10 Vpp. Inputs 100 kΩ, outputs 1 kΩ.
  Self-oscillation from about 2 o'clock on RES, a sine tracking about three
  octaves, not temperature compensated.
- The scanner: an interpolating crossfader from channel 1 to 4 (Haible's,
  then Tillman's design, reworked), a transistor "current line" driving
  AS3360 VCAs, set by a fader plus a CV.
- 16HP, 30 mm deep, 170 mA on ±12 V.

## One channel

After Sound Semiconductor's application note AN701, "Designing Voltage
Controlled Filters for Synthesizers with the SSI2164" (Jeroen Allaert).

```
IN ─100k─► input summer ─A─► pole ─B─► pole ─C─► pole ─D─► pole ─E─┬─► LP buffer  −2E
            (51k: ×0.51)                                           ├─► HP sum  −1.95 (A + 2B + C)
                 ▲                                                  └─► BP sum  −4.17 (C + 2D + E)
                 │ resonance current                                          │
                 └── U5 cell ◄─13k─ limiter ◄─11k────────────────────────────┘
        LP / HP / BP ─► mode toggle ─► SEL ─1k─► OUT       SEL ─47k─► scanner VCA
```

- **Poles:** one SSI2164 per channel, each cell in AN701's figure 1: 15k
  in, 15k local feedback, 220 pF C0G integrator on a TL074, 220 Ω + 1.2 nF
  on the cell input (the datasheet's network). 48 kHz with 0 V on the
  control pins; each pole inverts.
- **Input summer:** IN through 100 kΩ (Atlas's input impedance) into a
  51k / 22 pF summer, so the core runs at half the input level. That
  leaves 12 dB of headroom for resonant peaks inside the filter, and the
  outputs make it up.
- **Modes by pole mixing** (AN701 figure 35). With the inverting poles the
  weights are all positive, one inverting summer each:
  LP = −2E (×2 buffer), HP = (1 − H)²: 20k / 10k / 20k into 39k,
  BP = H²(1 − H)²: 24k / 12k / 24k into 100k.
  All three are in phase with the input in their passbands.
- **Resonance from the bandpass** (AN701 figure 32). The BP sum goes back
  through 11k, a limiter (two 1N4148 each way to ground) and 13k into one
  cell of U5, whose output current joins the input summer. The BP sum is
  real and positive at the cutoff, so with the inverting summer this is
  positive feedback exactly there and almost nothing elsewhere: no bass
  loss in LP, no air loss in HP, no shift of the slope. That is most
  likely Atlas's "accurate resonance compensation".
- **Levels** (`sim.py`): LP +0.2 dB in its passband, HP 0.0 dB, BP −5.5 dB at
  its peak with no resonance. The passbands do not move as resonance comes
  up. The loop gain at the cutoff is 2.21 × the resonance cell's gain, so
  oscillation starts at a cell gain of 0.45 (0.23 V on its control pin,
  about 2 o'clock on RES) and the knob's end gives 2.2 × the threshold.
  In oscillation the limiter holds about 6 V peak at A: LP about 6 Vpp,
  HP and BP about 12 Vpp. BP's peak is set 6 dB low so that it does not
  run into the rails when it oscillates.
- **Mode toggle** (Dailywell 2MD6, DPDT ON-ON-ON): positions 2-3 + 5-6,
  2-3 + 5-4, 2-1 + 5-4. SEL on 2, 5 tied to 3, LP on 6, HP on 4, BP on 1:
  up LP, middle HP, down BP. This rests on Dailywell's catalogue table;
  ring one switch out before soldering four.
- **Op-amps:** UA (U6, U8, U10, U12) are the four integrators of channel
  1-4; UB (U7, U9, U11, U13) the input summer, HP, BP and LP. FET inputs,
  as AN701 asks.

## Control voltages

Both summers are precision half-wave stages (two 1N4148 each), so their
outputs never go below 0 V: negative control would give the cells up to
+20 dB of gain, heat and drift (AN701). The control pins are 10 kΩ each,
four in parallel per channel: they need the op-amp drive.

- **FREQ** (U14 / U15): the knob (B100k between the filtered ±12 V rails)
  and an offset from −12 V, each 220k; the FREQ jack (normalled from the row
  above, grounded on row 1) and, with the switch on FM2, the FM2/RES jack,
  each 100k; 20k feedback. The cells want about −0.2 V per octave, so the
  jacks are 1 V/oct nominal. The knob spans 0 to 2.2 V on the pins: 48 kHz
  down to about 20 Hz. No trimmers, no temperature compensation, like
  Atlas.
- **RES** (U14 / U15): the knob (B100k, filtered +12 V to ground) and an
  offset, each 240k; the FM2/RES jack on RES, 100k; 20k feedback. Knob CW
  is 0 V (most feedback), CCW 1.0 V (−30 dB, no audible peak). The
  SSI2164 works in dB, so the knob sweeps the musical last 30 dB.
- **Knob rails:** +12 V and −12 V through 100 Ω into 22 µF each (`+12V_POT`,
  `-12V_POT`) for the knobs, the offsets and the scanner's ladder.

## Scanner

A current line built from three degenerated PNP pairs (BC557), stacked:

- **Scan voltage S1** (U16 section 1): the SCAN knob (B10k), the SCAN jack
  and an offset mixed passively on a non-inverting gain-of-2 stage:
  S1 = 5.3 V + 0.34 × knob + 0.42 × CV, i.e. 5.3–9.3 V over the knob and
  ±2 V from ±5 V CV.
- **Level shifts:** S2 = S1 − 2.8 V and S3 = S1 − 5.6 V, across two 2.7k
  carrying 1 mA from an NPN sink. They keep each stage's emitters below
  the stage above it.
- **The stack:** a 0.5 mA tail (PNP source from +12 V) feeds stage 1, which
  compares S1 with the ladder's R1 (6.0 V). Below R1 the current goes to
  channel 1; above, it goes on to stage 2 (S2 against R2, 4.6 V), and
  stage 2 hands on to stage 3 (S3 against R3, 3.1 V), whose two sides
  are channels 3 and 4. 1 kΩ in every emitter makes each hand-over a
  straight ramp over about 1 V, so transistor mismatch and temperature
  hardly matter. The four currents always add up to the tail: the four
  VCA gains always sum to one.
- **VCAs:** each current into 3.0k gives 0–1.5 V on an AS3360 linear
  control input, which is linear up to about 1.5 V (Alfa's figure 3). The
  log converters are bridged (pins 3-4, 11-12) and VREF has 4.7 nF to
  ground, as in Alfa's figure 1. Each channel's SEL drives a VCA through
  47k; the four output currents meet in one I-V stage (U16 section 2,
  51k ∥ 22 pF), then 1 kΩ to SCAN OUT. A 1N4148 from ground holds each
  control input above −0.6 V when a large negative CV pulls the stack's
  bases low.
- **Result** (`sim.py`): over the knob the shares always sum to 1.0000;
  each channel is alone (98–100 %) at its mark: 1 fully CCW, 2 at a third,
  3 at two thirds, 4 fully CW. Between the marks it is a straight
  crossfade between neighbours only.

## No LEDs

Atlas's lit numerals were dropped (2026-10-31): with the inputs chained
they would mostly light together, the ear says the same, and their
switching currents would run beside the filters. The numerals are gold
dots on the panel. If any LEDs come back, the four scanner currents are the
ones worth showing (where a CV-driven scan is), and they are already there.

## Parts

| Part | Count | Package |
|---|---|---|
| SSI2164 quad VCA | 5 | SOIC-16 only |
| AS3360 dual VCA | 2 | DIP-14 (or SOIC-14) |
| TL074 | 11 | DIP-14 (or SOIC-14) |
| BC557B / BC547B | 7 / 1 | TO-92, pins C B E |
| 1N4148 / 1N5819 | 36 / 2 | |
| Resistors | 186 | 1 %; the pole-mix and pole resistors set the response |
| Capacitors | 79 + 4 electrolytic | 220 pF C0G for the integrators |
| Panel | 18 jacks, 9 Alpha pots, 4 DPDT ON-ON-ON + 4 SPDT toggles | |

Supply: 11 TL074 (about 62 mA), 5 SSI2164 (6 mA each), 2 AS3360 (about
5 mA each) and the knob and scanner currents: about 110 mA on each rail
(Atlas: 170 mA). 16-pin power header with the reverse diodes the right way
round (`check()` asserts it).

## Board count

At the density the mixer's main board was laid out (37 % of the board
covered by through-hole parts and their spacing), the 334 parts behind the
panel need about 2.8 boards of 79.7 × 108 mm, on top of the faceplate
board, whose rear can take perhaps a third of a board between the panel
parts' bodies. Two ways:

| | Through-hole (as the other modules) | SMD (0805, SOIC, SOT-23), JLC-assembled |
|---|---|---|
| Boards | faceplate + 3 (filters 1-2, filters 3-4, scanner and power) | faceplate + 1 main board |
| Depth | about 45 mm | about 30 mm, like Atlas |
| Soldering | about 1100 joints by hand, plus 5 SSI2164 (SOIC anyway) | assembled except the panel parts; the SSI2164 and AS3360 by hand if JLC has no stock |
| Board-to-board headers | 3 sets | 1 set |
| Library | your THT EasyEDA parts | LCSC parts, which EasyEDA has natively |

## Lessons from the earlier boards, and where they land here

| Lesson | From | Here |
|---|---|---|
| Panel first, compared with the original, before any PCB | Marblesy's re-layout | Done first; nothing placed on a PCB yet |
| One panel frame on every module | Marblesy/mixer drift | Title, subtitle, band, rule and maker at the skill's numbers |
| Rows of identical controls labelled once | Mixer panel (option D) | Column words once above row 1, numerals name the rows, only switch positions per switch |
| Give a hole table, not just a picture | Marblesy panel-board confusion | `atlas-panel-holes.csv`: every hole in panel coordinates next to its footprint origin |
| Alpha shaft 4.0 mm from the PTV09A-frame origin; Alpha footprint, not PTV09A | Pot shaft fix (2026-10-30) | `POT_SHAFT = 4.0`; FREQ and RES pins down, SCAN pins up (it sits 7 mm from the board edge) |
| DIP-14 rows 7.62 mm, never the library TL074 footprint | Kick, Mixer, Output bent legs | `fp_dip(14, "DIP-14-W7.62-P2.54")` if through-hole |
| Eurorack header at 2.54 mm | Compressor, FM, Clap, CB/RM (2.00 mm) | The mixer's 2×8 2.54 mm box header |
| −12 V reverse diode the right way round | Every drum board | +12 V anode at the header, −12 V cathode at the header; `check()` fails otherwise |
| TO-92 pin order checked against the part | FM (VT13), Compressor (CBE) | BC547B / BC557B, pins 1 C, 2 B, 3 E, written into the netlist |
| A switch's contact table from its datasheet, not from habit | (new here) | The ON-ON-ON's table is in `circuit.py`; ring one out before soldering |
| Every jack switch lug goes somewhere on purpose | Kick ACCENT floating | IN and FREQ chained, ground on IN 1 / FREQ 1 / FM2-RES / SCAN, outputs open; `check()` flags any other open pin |
| Sensitive nodes away from switching edges | FM bleed | No LEDs or logic at all now; the integrators' summing nodes short in the layout |
| One unbroken ground pour | Compressor's six islands | Copper audit before ordering |
| Decoupling next to each chip | Marblesy routing | A 100 n pair per TL074, SSI2164 and AS3360 in the netlist, placed beside it |
| No ×2 stage that clips in dense patches | Mixer → output chain | Unity through every mode; the core runs at half level with 12 dB of headroom |
| Prove the circuit's numbers before the board | (new here) | `sim.py` from the netlist values: passbands, the resonance loop's sign, the scanner's sum |
