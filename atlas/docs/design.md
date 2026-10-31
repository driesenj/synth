# Atlasy — circuit plan

Draft, 2026-10-31. Block level with the chips, the topology and the
scaling; resistor and capacitor values come with the netlist
(`hardware/tools/circuit.py`) once the panel and the open questions below
are settled.

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

All of this follows Sound Semiconductor's application note AN701,
"Designing Voltage Controlled Filters for Synthesizers with the SSI2164"
(Jeroen Allaert), which covers exactly this filter.

```
IN ─ 100k ─► input summer ─A─► LP ─B─► LP ─C─► LP ─D─► LP ─E─┬─► LP out (−E)
                 ▲                                            │
                 │ resonance current                          ├─► HP sum  A + 2B + C   (2-pole HP)
                 └── res VCA ◄── limiter ◄── BP sum  C + 2D + E (4-pole BP) ──► BP out
                                                                    mode toggle ─► 1k ─► OUT
                                                                                └──► scanner, LED
```

- **Four low-pass poles**, one SSI2164 per channel (AN701 figure 1, four
  times): each cell's current into a TL074 integrator, 15k in, 15k local
  feedback, 220 pF C0G, the 180 Ω + 1500 pF compensation at the cell's
  input. About 50 kHz at 0 V on the control pins. Each stage inverts.
- **Input summer** (one op-amp): IN through 100 kΩ (Atlas's input
  impedance) plus the resonance VCA's output current at its virtual ground.
  Its output, A, is a real node, which the HP mix needs.
- **Modes by pole mixing** (AN701 figure 35, the Xpander method). With the
  stage inversions the weights all come out positive, so each mix is one
  inverting summer with resistors R, R/2, R:
  - LP4 = E (an inverting buffer, so all three modes are in phase with the
    input in their passbands),
  - HP2 = (1 − H)² · A = A + 2B + C,
  - BP4 = H²(1 − H)² · A = C + 2D + E, times 4 for unity gain at the peak.
- **Resonance from the bandpass** (AN701, "Solving the passband
  attenuation problem", figure 32). Feeding back the 4-pole bandpass
  instead of the lowpass leaves the passband alone in every mode: no bass
  loss in LP, no air loss in HP, and no shift of the cutoff slope, which
  the usual Roland-style Q compensation (input added to the feedback)
  causes. That is what "accurate resonance compensation" most likely means
  on Atlas. The BP sum is in phase at the cutoff, so with the inverting
  input summer the loop is positive feedback there, as it should be.
  The BP summer is shared: its output is both the BP mode output and the
  resonance signal.
- **Resonance VCA:** one cell of a fifth SSI2164 per channel (the fifth
  chip serves all four channels). A diode string in the path to its input
  sets the self-oscillation amplitude (AN701's RES_LIM, fixed), aimed at
  about 8 Vpp so oscillation is clean and leaves headroom.
- **Mode toggle** (DPDT ON-ON-ON wired as a 3-way selector: up LP, middle
  HP, down BP) picks one of the three op-amp outputs. From there 1 kΩ to the
  OUT jack, and the same node unloaded to the scanner and the LED driver.
- **Op-amps per channel:** input summer, four integrators, HP sum, BP sum,
  LP buffer: 8, so two TL074 per channel. FET inputs, as AN701 asks.

## Control voltages

- **FREQ:** the FREQ knob, the FREQ jack (normalled from the row above,
  grounded on row 1) and, with the switch on FM2, the FM2/RES jack, summed
  in one inverting op-amp and clamped at 0 V so the control pins never go
  negative (AN701: negative control gives up to +20 dB per cell, heat,
  drift and instability). The pins want about −0.2 V/oct (0.18 V/oct cold,
  0.2 V/oct with self-heating), so the jacks come in at 1 V/oct nominal
  through 100k into 20k. No trimmers and no temperature compensation, like
  Atlas: tracking is "about three octaves" of usable pitch.
- **RES:** the RES knob and, with the switch on RES, the FM2/RES jack,
  summed into the resonance cell's control pin and clamped at 0 V, which is
  maximum feedback (just past oscillation). The SSI2164's control is in dB,
  so the knob sweeps feedback in dB: the musical part, the last 20 dB or so,
  gets most of the travel with a fixed offset.
- **Op-amps:** two per channel, eight in all, two TL074. These are the ones
  that can live on the faceplate board's rear, next to the pots.

## Scanner

- **Scan voltage:** the fader (20 mm, B10k across a reference) plus the
  SCAN jack (±5 V sweeps the whole range), one summer.
- **Current line:** a tail current steered by the scan voltage through a
  chain of transistor differential pairs, each comparing it with a
  threshold from a resistor ladder. Each pair hands what is left of the
  current to the next, so the four output currents are bumps that overlap
  only between neighbours, and they always add up to the tail current. The
  four VCA gains therefore always sum to one: no dip or bump in level as
  the scan passes between channels, the "homogeneous gain" Cabrera says
  took him longest. Emitter resistors set how wide each crossfade is
  (Atlas: "a very smooth fading slope"). Matched pairs (a dual NPN, or
  BC547s glued together) keep the four positions where the panel's 1–4
  marks are.
- **VCAs:** two AS3360 (Alfa's CEM3360, Atlas's own choice for its linear
  control), each channel's output into one VCA, the four VCA output
  currents summed in one op-amp to SCAN OUT through 1 kΩ. Pin-level control
  wiring from Alfa's datasheet in the netlist step.
- **Op-amps:** scan summer, output summer, the current-to-control
  conversion: one or two TL074.

## Indicators

A 3 mm red LED behind each numeral, driven by an NPN from the channel's
selected output (half-wave, about 2 mA at full level, a little glow at
modest levels). The numeral is 0.8 mm holes in gold rings, so it reads
unlit too.

## Power and parts

| Chip | Count | Package |
|---|---|---|
| SSI2164 quad VCA | 5 | SOIC-16 only (no DIP exists); hand-solderable at 1.27 mm |
| AS3360 dual VCA | 2 | DIP-14 |
| TL074 | 11–12 | DIP-14 |
| NPN, matched pairs | 6 | current line |
| NPN | 4 | LED drivers |

Expected draw about 120–150 mA on each rail (Atlas: 170 mA), to be totalled
from the datasheets with the netlist. With roughly 250 resistors and 60
capacitors this is more than one 80 × 108 mm main board takes in
through-hole the way Plaitsy was laid out; see the open questions.

## Lessons from the earlier boards, and where they land here

| Lesson | From | Here |
|---|---|---|
| Panel first, compared with the original, before any PCB | Marblesy's re-layout | Done first; nothing placed on a PCB yet |
| One panel frame on every module | Marblesy/mixer drift | Title, subtitle, band, rule and maker at the skill's numbers |
| Rows of identical controls labelled once | Mixer panel (option D) | Column words once above row 1, numerals name the rows, only switch positions per switch |
| Give a hole table, not just a picture | Marblesy panel-board confusion | `atlas-panel-holes.csv`: every hole in panel coordinates next to its footprint origin |
| Alpha shaft 4.0 mm from the PTV09A-frame origin; Alpha footprint, not PTV09A | Pot shaft fix (2026-10-30) | `POT_SHAFT = 4.0`, pins down; the generated Alpha footprint |
| DIP-14 rows 7.62 mm, never the library TL074 footprint | Kick, Mixer, Output bent legs | `fp_dip(14, "DIP-14-W7.62-P2.54")` for TL074 and AS3360 |
| Eurorack header at 2.54 mm | Compressor, FM, Clap, CB/RM (2.00 mm) | 2×5 2.54 mm shrouded; a netlist check on the footprint |
| −12 V reverse diode the right way round | Every drum board | +12 V: anode at the header; −12 V: cathode at the header. A netlist check asserts both |
| LED pin names must match the footprint's flat | Compressor | Generated LED footprint, pad 1 = anode, checked |
| TO-92 pin order checked against the part | FM (VT13), Compressor (CBE) | Footprint pin order printed in the BOM per transistor |
| Every jack switch lug goes somewhere on purpose | Kick ACCENT floating | Chains for IN and FREQ, ground on IN 1 / FREQ 1 / FM2-RES / SCAN, outputs open; check flags a lug with no net |
| Sensitive nodes away from switching edges | FM bleed | The integrators' summing nodes (cell output to op-amp input) short; LED drive and its return kept off the analog ground path |
| One unbroken ground pour | Compressor's six islands | Main board ground pour checked for islands in the copper audit |
| Decoupling next to each chip | Marblesy routing | 100 n pair per TL074, SSI2164 and AS3360 placed beside it before routing |
| No ×2 stage that clips in dense patches | Mixer → output chain | Unity gain through every mode; 10 Vpp in, 10 Vpp out; oscillation about 8 Vpp |

## Open questions

1. **Mode switch: toggle or LED button.** Drawn as a 3-way toggle (Atlas
   uses a slide switch). The Marbles-style alternative is one LED button
   per channel cycling LP → HP → BP with a bicolour LED showing the mode;
   it needs a counter and an analog switch per channel (CD4013 + DG/CD4052)
   and forgets the mode at power-up.
2. **Numerals: output (drawn) or input level** like Atlas.
3. **SCAN: fader (drawn) or a knob.** The fader needs a 20 mm slide pot
   from Mouser or Tayda with a lever tall enough for the 7 mm gap; a knob
   is an Alpha pot like the rest.
4. **A third board.** The likely fit is faceplate board (panel parts, CV
   summers, LED drivers), a filter board (five SSI2164 and eight TL074) and
   a scanner/power board, about 40 mm deep instead of Atlas's 30. To be
   confirmed when placing.
