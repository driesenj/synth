# Ringsy — design notes

A Mutable Instruments Rings clone for Eurorack, 14HP, built the way
[Plaitsy](../../plaits/README.md) and [Marblesy](../../marbles/README.md)
are: Thonk panel parts, a PCB panel in the house style, and a Daisy Seed on
Rob Heel's `seed_power_opamps` breakout. The firmware will be a port of
Mutable's open-source Rings code (pichenettes/eurorack `rings/`, MIT) to
libDaisy with the Daisy bootloader, so the
[Rings manual](https://pichenettes.github.io/mutable-instruments-documentation/modules/rings/manual/)
applies as written.

In the rig it serves as a resonator for Plaitsy, noise and drums, and its
ODD / EVEN outputs go to the stereo mixer as a real stereo pair.

Status: **panel approved (2026-10-31); netlist, EasyEDA Pro schematic,
both PCBs placed and the panel as a PCB done (2026-11-01); LED footprint
moved to the measured 2.54 mm lead pitch (2026-11-14): re-import before
routing.**
`hardware/tools/circuit.py` holds the whole circuit as one netlist over the
two boards, the panel placement, and three checks (netlist, circuit values,
faceplate front). `easyeda_export.py` writes `hardware/easyeda/Ringsy.epro2`:
the schematic ("Schematic" below), both boards placed with `pcb.py`, and the
panel from `panel_pcb.py` ("PCBs" below). All checks are at 0 problems.
Next: you import it into EasyEDA Pro and route (routing notes below).

Sources used for the original (all in pichenettes/eurorack, checked
2026-10-31):

- `rings/hardware_design/panel/rings.ai`: the panel, 70.80 × 128.50 mm. Its
  CAD layer has every hole; `PANEL_XY` in `circuit.py` takes the rows from
  it unchanged.
- `rings_v30.pdf` (the v3.0 schematic, five sheets, from the documentation
  site): CV scaling, normalization probe, STRUM, IN, the output stage.
- The firmware: `rings.cc`, `cv_scaler.cc` / `.h` (scaling, the three
  normalization detectors and their calibration), `drivers/*`, `dsp/dsp.h`,
  `dsp/part.h`, `dsp/string.h`, `ui.cc`, `resources.cc`.

---

## What Rings needs

| Function | Rings hardware (v3.0) | Count |
|---|---|---|
| Pots | FREQUENCY, STRUCTURE (big); BRIGHTNESS, DAMPING, POSITION (medium); one attenuverter per CV input | 10 |
| CV inputs | FREQUENCY (FM, normalled to +0.1 V), STRUCTURE, BRIGHTNESS, DAMPING, POSITION; V/OCT | 6 |
| Trigger input | STRUM, through an NPN to a GPIO | 1 |
| Audio input | IN, mono, into the codec's right line input | 1 |
| Audio outputs | ODD, EVEN; an unpatched EVEN is mixed into ODD in the analog stage | 2 |
| Buttons | polyphony (1 / 2 / 4 voices), resonator model; held together for calibration and the "Disastrous Peace" easter egg | 2 |
| LEDs | two red/green bicolour, green / yellow / red, software PWM at 1 kHz | 2 (4 lines) |
| Normalization probe | one GPIO, a random bit per audio block, into the STRUM, V/OCT and IN switch lugs | 1 |

Rings reads 16 analog values: the six CVs and the FREQUENCY and STRUCTURE
pots directly, the other three pots and the five attenuverters through a
4051. The CV stages are inverting (the firmware computes `offset − adc`),
on MCP6004s from a single 3.3 V supply with a −10 V reference offset.

---

## Panel

Approved as drawn. 14HP: 70.8 × 128.5 mm, the same as Rings. The faceplate
board is 69.6 × 108 mm, centred (board x = panel x − 0.6; board y = 118.25 −
panel y). Mounting slots 5.5 × 3.2 mm at x 7.5 and 63.38, 3 mm from the top
and bottom edges.

The arrangement is Rings' own. The rows are taken from `rings.ai`'s CAD
layer to the hundredth; the five columns are 13.0 mm apart and centred
(Rings: 13.005), and the rest is symmetric about the centre line.

```
  y from top
   16.12   [poly] D1 ●  ⓵ ⓶ ⓸            ◎ ⦀ ⌇  ● D2 [model]   buttons x 7.5 / 63.3, LEDs 13.8 / 57.0, icons 4 mm apart
   33.43        FREQUENCY (18.9)      STRUCTURE (51.9)          big knobs, two dotted rings round each
   60.63   BRIGHTNESS (11.6)   DAMPING (35.4)   POSITION (59.2)
   80.63   att      att      att      att      att             x = 9.4 + 13 k: BRIGHT, FREQ (FM), DAMP, STRUCT, POS
   96.48   cv       cv       cv       cv       cv              unlabelled, a dotted line up to each attenuverter
  111.08   STRUM    V/OCT    IN      [ODD ··· EVEN]            ODD / EVEN on the gold band
```

`PANEL_XY` in `circuit.py` holds what you see (knob shafts, jack barrels,
button caps, LED lenses, in panel mm from the top-left corner);
`PLACEMENT` derives the footprint origins from it (jack barrel 0.78 mm
below the WQP518MA origin, Alpha shaft 4.0 mm from the PTV09A origin away
from the pins), and `panel.py` turns those back into the hole table, so the
panel and the faceplate PCB cannot drift apart.

Pot pins: the big and medium knobs point theirs left, as on Marblesy. The
attenuverters point theirs **up**: at 13 mm pitch their housings (9.5 mm
across the pins) only fit side by side with the pins up or down; pointing
down, the pins land 1.9 mm from the CV jacks' sleeve pads, and the leftmost
one's pins would sit 1.3 mm from the board edge pointing left.
`python circuit.py` runs a first front-side check (bodies, pads under other
parts' bodies, pads near the edge): 0 problems.

| Hole | Ø mm | Part |
|---|---|---|
| Pots (×10) | 7.5 | Alpha 9 mm vertical B10k (Thonk) |
| Jacks (×10) | 6.5 | Thonkiconn PJ398SM |
| Buttons (×2) | 6.5 | Thonk low-profile LED button, 5.5 mm cap, feet clipped |
| LEDs (×2) | 3.2 | 3 mm red/green bicolour, 3-lead common cathode |

Knobs as drawn: Ø15 FREQUENCY and STRUCTURE, Ø12 BRIGHTNESS, DAMPING and
POSITION, Ø10 attenuverters, the Plaitsy set. Rings' attenuverters are small
trimmers with 6.8 mm holes; at 13 mm pitch Ø10 knobs leave 3 mm between them.

### Artwork

`panel.py` writes `hardware/panel/rings-panel.svg`: black mask, white silk,
bare ENIG copper for the ODD / EVEN band (Rings' dark box). From the top:
the house frame (serif title, "Resonator", the dotted band); the two
buttons with their LEDs and Rings' six icons (1, 2, 4 voices; modal,
sympathetic strings, string), each group green, yellow, red from left to
right as on Rings, drawn as silk rings with the glyph inside (silk cannot
knock a glyph out of a disc; the colours are a preview-only tint); scale
arcs with ticks on the five big and medium knobs and, round the two big
ones, two dotted rings in place of Rings' mandalas; labels under them;
a noon tick between − and + over each attenuverter; dotted guides from the
FREQUENCY and STRUCTURE labels down to their attenuverters (the medium
knobs' sit right under their labels) and from each attenuverter to its CV
jack; STRUM, V/OCT and IN over their jacks; ODD and EVEN knocked out of the
copper band with a dotted line between the jacks for the normal; the rule
and the gold mushroom mark (the maker line until 2026-11-02).

`hardware/panel/rings-panel-vs-original.png` puts the draft beside a
render of `rings.ai` (cc-by-sa 3.0, Mutable Instruments), with the six rows
marked. The preview is a headless-Edge screenshot of the SVG at 3× (268 ×
486 window), scaled to 708 × 1285.

`panel.py` also prints a clearance check (knob scales and rings, nuts,
caps, LEDs, icons and the knob labels; gaps under 1 mm): nothing flagged.

### Differences from Rings

- Same controls in the same places; Alpha pots everywhere (Rings uses
  trimmers for the attenuverters) with whatever knobs you fit.
- The buttons are Thonk LED buttons, the house part, in 6.5 mm holes (Rings:
  plain tactiles, 5.2 mm holes). There was no room left for Rings' short
  dashes between button and LED.
- Black panel, white silk, gold output band, the house title band and
  mushroom mark; Rings' mandalas around the big knobs became two dotted rings,
  and the icons are redrawn.
- Mounting slots instead of round holes.

---

## Choices taken

The user approved the panel as drawn (2026-10-31). The other four choices
the draft left open are taken at the proposed defaults:

1. **Buttons:** Thonk LED buttons, white; their LEDs get a Seed GPIO each
   (Rings has none, so the port decides what they show, or leaves them
   dark). The cap colour is the builder's.
2. **Outputs:** Rings' own ODD / EVEN stage with the analog EVEN → ODD
   normal, from the Seed's audio pins; the breakout's J4 outputs stay
   unused.
3. **Seed:** one with the PCM3060 codec (rev 7 or Seed 2 DFM, what
   Electro-Smith sells now; libDaisy detects the revision). It sets only
   the output stage's input resistor, a through-hole part picked at the
   build (below), so the boards do not depend on it.
4. **Stack:** two boards; the breakout cannot share the faceplate.

---

## Architecture

```
 panel ─┬─ faceplate board (FB)  10 Thonkiconn jacks, 10 Alpha pots, 2 LED buttons, 2 bicolour LEDs,
        │   69.6 x 108 mm         74HC4051 pot mux, the jack-lug networks (FM normal, probe resistors, IN load)
        │      30 pins in 4 headers (male on the FB, female on the MB)
        └─ main board (MB)       Daisy Seed on the seed_power_opamps breakout (power, audio in),
            69.6 x 108 mm         2 TL074 = 6 CV stages + Rings' ODD/EVEN output stage, STRUM NPN,
                                  probe clamps, two bias dividers, LED resistors
```

**Why two boards, when one is the default:** the breakout is 96.7 mm long,
so it has to stand along the board's height, and its two pin rows (15.24 mm
apart, the full length) would have to cross the attenuverter row. There the
five housings, 9.5 mm wide at 13 mm pitch, leave 3.5 mm gaps 13 mm apart;
two rows 15.24 mm apart cannot both land in gaps, and socket pins soldered
under a pot body lift it.

---

## Circuit (as in `circuit.py`)

### CV inputs (6×): Plaitsy's stage

Plaitsy's inverting TL074 stage on ±12 V, biased from 3V3A, so the full
±12 V stays inside the ADC range without clamps:

```
jack tip ── 100k ──┬── (−) TL074 ──┬── 1k ── Seed ADC
                   ├── Rf ─────────┤
                   └── 1n ─────────┘
BIAS ─────────────── (+)
```

| Input | Rf | Bias | V_adc | Reads | Rings (MCP6004, 3.3 V, −10 V ref) |
|---|---|---|---|---|---|
| FREQUENCY (FM), STRUCTURE, BRIGHTNESS, DAMPING, POSITION | 13k | A 1.467 V (15k / 12k) | 1.657 − 0.130 V_in | −12.6 … +12.7 V | 1.667 − 0.2 V_in, ±8 V |
| V/OCT | 33k | V 1.768 V (13k / 15k) | 2.351 − 0.330 V_in | −2.9 … +7.1 V, BAT85 clamps beyond | 2.611 − 0.47 V_in, −1.5 … +5.6 V |

V/OCT resolves 0.18 cents per 16-bit step. The firmware turns V_adc back
into volts and then into the number Rings' own ADC would have read, so
Rings' code, its offset calibration and its C1 / C3 pitch calibration
apply unchanged.

### The jack normals (on the faceplate, next to their jacks)

| Jack | Lug | Unpatched | Rings |
|---|---|---|---|
| FREQUENCY CV (J2) | 6k8 to GND | tip +0.093 V: the attenuverter is a ±0.96 semitone fine tune | 3.3M to 3V3A, +0.097 V, ±1 semitone |
| STRUM (J6) | probe through 100k | the probe pulls the STRUM pin low when high | the same |
| V/OCT (J7) | probe through 470k | tip 1.458 / 2.037 V with the probe low / high, swing 0.579 V | 0 / 0.579 V |
| IN (J8) | probe through 1M, and 43k to GND | 224–421 counts (below) | 1M into 36k + 6.8k, 419 counts |
| BRIGHTNESS, DAMPING, STRUCTURE, POSITION CV | GND | 0 V | the same |
| ODD (J9) | open | | SJ1, open: not copied |
| EVEN (J10) | to ODD's summing node (below) | EVEN mixed into ODD | the same |

- **FM normal:** Rings' summing node sits at 0 V, so 3.3M from 3V3A sets
  the tip at +0.097 V. Here the summing node sits at BIAS_A (1.467 V), and
  through any large resistor the tip would follow it to about +1.5 V (the
  panel draft's 2.2M was wrong for that reason). Tied to GND through 6k8,
  the lug divides BIAS_A against the stage's 100k down to +0.093 V.
- **V/OCT:** the same 0.579 V swing as Rings, on a 1.46 V offset. Rings'
  detector compares the reading with a threshold that its calibration sets
  half-way between the probe-low and probe-high readings, and accepts only
  inside 0.70…0.80 of its ADC range (`CvScaler::CalibrateHigh`). Mapped
  into Rings' units, Ringsy's threshold is 0.542, so the port moves that
  window to about 0.50…0.60 (one constant). When the detector says
  unpatched, Rings sets the note to 0 and ignores the reading, so the
  offset does nothing else.
- **IN:** Rings' detector counts the samples between 50 and 1500 (of 32768)
  that follow the previous block's probe bit. The 43k to ground stands in
  for Rings' input divider, so the level hardly depends on the breakout's
  input impedance, which is not documented: 224, 298 and 421 counts with
  47k, 100k and an open input there (Rings: 419). The sign depends on
  whether the breakout's stage inverts; the port flips it once at bring-up
  if the detector never locks.

### STRUM: Rings' transistor

J6 tip → 100k → 2N3904 base, emitter to GND, collector to D9 with 10k to
3V3D. A 5 V gate gives 43 µA of base current (needs hFE > 8), the probe
13 µA (hFE > 25; the 2N3904 has over 100 there). **One addition:** a 1N4148
from emitter to base, so a negative input cannot reverse-break the
base-emitter junction (Rings lets it, through the 100k).

### IN: the breakout's audio input

J8 → H2 → the breakout's J5-1, its input op-amp, Seed AIN1. Rings divides
IN by 36k / 6.8k into the WM8731 at −1.5 dB: ±10.6 V at the jack is full
scale. The port scales so ±10.6 V is again 1.0 (one constant, measured
with a known level), which keeps Rings' input gate (−45 dB), its level
response and the detector's counts.

### ODD / EVEN: Rings' output stage

Rings' sheet 4, with every resistor scaled up 2.1× so the stage loads the
Seed's audio pins by only 16.7k: the breakouts are built with their own
output op-amps on the same pins (unused here, fitted anyway).

```
Seed AOUT ── 10µ NP ──┬── Rin 20k ──┬── (−) TL074 ──┬── 1k ── ODD / EVEN tip
                      100k          ├── 100k ───────┤
                      GND           └── 10p ────────┘
                                        (+) GND
EVEN switch lug ── 100k ── ODD's (−)          (an unpatched EVEN is mixed into ODD)
```

| | Ringsy | Rings |
|---|---|---|
| Gain | −5.00 (100k / 20k) | −6.91 (47k / 6.8k) |
| Full scale out | ±9.0 V (PCM3060, 1.8 Vpk assumed); ±7.0 V with a WM8731 | ±9.7 V (WM8731) |
| EVEN → ODD | 0.990 of EVEN's jack voltage | 0.979 |
| Roll-off | 159 kHz | 188 kHz |
| Load on the codec | 16.7k | 5.9k |

The PCM3060's full scale at the Seed's pins is not in Electro-Smith's
datasheet: 1.8 Vpk is the Seed's stated 3.6 Vpp audio level (and the
PCM3060's single-ended 0.8 VCC at 4.5 V). **Before fitting Rin:** play a
full-scale sine from the Seed, measure pin 18's peak V_fs, and fit
Rin = 100k × V_fs / 9.8 V (20k for 1.8 V; 15k for a rev 5 Seed's WM8731).
The stage is copied with its signs as they are: the firmware's ODD and EVEN
polarity is what makes the normal a mix, so nothing here gets "corrected".
Rings' SJ1 (the reverse normal, ODD into EVEN, open on Rings) is not
copied: closed together with the EVEN normal it would make a loop.

### Normalization probe

D14 → PROBE, clamped to 3V3D and GND by two BAT85 at the Seed (Rings: a
BAT54S), across H2 to the three lug resistors. libDaisy toggles it once per
audio block from a random bit, as Rings does.

### Pots

Ten B10k Alpha pots, CCW end to GND, CW end to 3V3A. FREQUENCY and
STRUCTURE go straight to A6 and A9, the other eight through a 74HC4051 on
the faceplate (Rings' own split; all eight channels used). The channels are
the assignment with the fewest crossing ratsnest lines on the placed
faceplate (all 40 320 tried), and the firmware reads by `MUX_CHANNEL`:

| Channel (pin) | 0 (13) | 1 (14) | 2 (15) | 3 (12) | 4 (1) | 5 (5) | 6 (2) | 7 (4) |
|---|---|---|---|---|---|---|---|---|
| Pot | BRIGHTNESS att. | STRUCTURE att. | POSITION | BRIGHTNESS | POSITION att. | DAMPING | DAMPING att. | FREQUENCY att. |

### Buttons and LEDs

- Buttons: contacts to GND_D_F, the Seed's internal pull-ups. The white LEDs
  inside get D2 / D3 through 150 Ω (2.6 mA).
- Bicolour LEDs: D4–D7 through 330 Ω, red 3.8 mA, green 3.2 mA (Rings:
  180 Ω); yellow is both, PWM-balanced in firmware as on Rings.
- The resistors sit on the main board, at the Seed; the LED lines cross H4.

### Power

±12 V from the breakout's J1 / J3 for the two TL074s (100 n at each supply
pin). 3V3A from the Seed for the pots, the mux and the two bias dividers
(3.5 mA); 3V3D for the STRUM pull-up and the probe clamp. Roughly
Plaitsy's draw.

---

## Daisy Seed pin map

| Seed pin | libDaisy | Net | Use |
|---|---|---|---|
| 1, 2 | D0, D1 | BTN_POLY, BTN_MODEL | buttons, internal pull-ups, active low |
| 3, 4 | D2, D3 | BTN_LED_POLY_IO, BTN_LED_MODEL_IO | the LEDs inside the buttons, through 150 Ω |
| 5, 6 | D4, D5 | LED_POLY_R_IO, LED_POLY_G_IO | D1, polyphony, through 330 Ω |
| 7, 8 | D6, D7 | LED_MODEL_R_IO, LED_MODEL_G_IO | D2, resonator model, through 330 Ω |
| 10 | D9 | STRUM | from the NPN's collector, active low |
| 15 | D14 | PROBE | normalization probe |
| 18, 19 | AOUT 1, AOUT 2 | AOUT_ODD, AOUT_EVEN | to the output stage (Rings: L = ODD, R = EVEN) |
| 20, 40 | AGND, DGND | GND | joined on the breakout |
| 21 | 3V3A | 3V3A | pots, mux, bias, V/OCT clamp |
| 22–26 | A0–A4 | ADC_FM, ADC_STRUCTURE, ADC_BRIGHTNESS, ADC_DAMPING, ADC_POSITION | CV inputs |
| 27 | A5 | ADC_VOCT | V/OCT |
| 28, 31 | A6, A9 | POT_FREQUENCY, POT_STRUCTURE | the two direct pots |
| 32 | A10 | MUX_OUT | 74HC4051 |
| 33, 34, 35 | D26, D27, D28 | MUX_S0..S2 | mux address |
| 38 | 3V3D | 3V3D | STRUM pull-up, probe clamp |
| J5-1 | AIN 1 (buffered) | IN | the breakout's input stage |
| J1, J3 | −12 V, +12 V | | the TL074s |
| 16 | AIN 1 | — | driven by the breakout's input stage from J5 |
| 9, 11–14, 17, 29, 30, 36, 37, 39 | D8, D10–D13, AIN 2, A7, A8, D29, D30, VIN | — | free |

Nothing in Rings needs SPI, I2C or the DACs; D1–D6 are SDMMC1, unused.

---

## Board-to-board headers

Male on the faceplate (HF1–HF4), female sockets on the main board (H1–H4),
2.54 mm, at the same spot on both boards. Grouped by what they carry. The
pin order is the one with the fewest crossing ratsnest lines on both
placed boards (every order tried, as on Plaitsy), with two rules: the probe
never next to IN, ODD, EVEN or EVEN's lug, and 3V3A next to a ground.
Positions are front view (pin 1, then the way the pins run).

| Header | Where | Pins, from pin 1 |
|---|---|---|
| H1 (6) | (53.6, 31.0) → +x: lying between the CV jacks and the attenuverters, right of centre | CV_BRIGHTNESS, CV_VOCT, CV_FM, CV_STRUCTURE, CV_POSITION, CV_DAMPING |
| H2 (7) | (54.3, 18.2) → down: standing in the gap between ODD's and EVEN's columns | TN_EVEN, GND, PROBE, STRUM_IN, IN, ODD, EVEN |
| H3 (8) | (3.0, 68.7) → +x: lying between the medium knobs and FREQUENCY | POT_FREQUENCY, GND, 3V3A, MUX_S2, MUX_S1, MUX_S0, MUX_OUT, POT_STRUCTURE |
| H4 (9) | (3.0, 95.0) → +x: lying under the polyphony button and LED | BTN_POLY, BTN_MODEL, GND (GND_D_F), BTN_LED_POLY, LED_POLY_R, LED_POLY_G, LED_MODEL_G, BTN_LED_MODEL, LED_MODEL_R |

---

## Checks

`python circuit.py` (from `hardware/tools`) prints the part counts and three
checks, all at 0 problems:

- **Netlist:** no single-pin nets, no designator twice, every header pin
  used on both boards, no net on both boards, every faceplate net ending in
  `_F`, the panel parts and `PLACEMENT` in step.
- **Circuit values,** from the resistors the netlist actually has (a
  mis-wired resistor makes the lookup fail): each CV stage's range, the V/OCT
  range against Rings', the FM normal (within 10 % of Rings'), the V/OCT
  probe swing and detection threshold, the IN probe counts over the
  breakout's possible input impedance (inside half the detector's window),
  STRUM's base current and the hFE it needs, both outputs' gain, full scale
  (inside the TL074's swing), load and roll-off, the EVEN → ODD normal, the
  LED currents and the 3V3A load.
- **Front:** the panel parts' bodies and pads on the faceplate's front.

---

## Schematic (EasyEDA Pro)

`python easyeda_export.py` (from `hardware/tools`) writes
`hardware/easyeda/Ringsy.epro2` and a preview PNG per page
(`rings-easyeda-*.png`). Two boards, each with its own schematic:

| Page | Holds |
|---|---|
| Main board 1: Seed, CV inputs | U2 with a port on every used pin, the six CV stages drawn with wires, BIAS_A / BIAS_V, the V/OCT clamps, the TL074 decoupling |
| Main board 2: outputs, STRUM, probe, headers | ODD and EVEN output stages (R52, the EVEN → ODD normal, into ODD's summing node), STRUM's 2N3904, the probe clamps, the six LED resistors, H1–H4 |
| Faceplate: panel parts, normals, mux | J1–J10 with their lugs, the lug networks R1–R5 with what each normal does, RV1–RV10, U1 + C1, D1 / D2, SW1 / SW2, HF1–HF4 |

Parts are your MorrisSynth library parts where it has them (LR1F
resistors, FG28 / SR305 capacitors, TL074ACN, WQP518MA, the PTV09A symbol,
the 1N5819 symbol, the 1N4148's DO-35, the 74HC595N's DIP-16), new values
on the same symbols and footprints. Drawn or generated here, as on Plaitsy:
the Seed on seed_power_opamps, DIP-14 on 7.62 mm rows for the TL074, the
Alpha 9 mm pot, the Thonk LED button (no foot holes), the 3 mm bicolour
LED (3 leads at 2.54 mm, measured on the bought ones; 0.9 mm holes, 1.5 mm
pads, pad 1 square = red anode, body centred on the middle lead), 1×N
headers, every main-board resistor standing up (Plaitsy's 2.54 mm
footprint). New for Ringsy: the 2N3904 with its symbol pins and TO-92 pads
both named E / B / C, so they cannot be swapped, and a 6.3 mm radial can on
2.5 mm leads for the bipolar 10 µ.

The exporter's checks, all at 0 problems:

- every netlist pin exists on its device's symbol;
- every part is drawn, every netlist pin exactly once on its board's pages;
- per page, the drawing's connectivity (wires, ports, flags) against the
  netlist: no net split, no two nets touching, no pin connected that the
  netlist leaves open, no junction in the middle of a wire. Tried with
  deliberate errors (a swapped feedback resistor, a reversed clamp, two mux
  inputs swapped): each is reported;
- every symbol pin has a footprint pad and the reverse;
- the written file resolves: every component's device, symbol and
  footprint is in it.

EasyEDA's own schematic DRC will still list the pins left open on purpose:
the Seed's free pins (D8, D10–D13, A7, A8, D29, D30, AIN2, VIN) and the
breakout's J4 / J5 pins the netlist does not use, and ODD's switch lug
(J9 pin 2).

---

## PCBs (placed, not routed)

`Ringsy.epro2` holds three boards: Main and Faceplate, each with its
schematic and its PCB placed and net-assigned (the ratsnest is live), and
the Panel. `pcb.py` places the two boards, `panel_pcb.py` draws the panel.
Previews: `rings-easyeda-pcb-*.png`, rear view (EasyEDA's top layer).

**Faceplate** (top layer = rear; front-view coordinates below):
- **Panel parts:** on the bottom layer at `PLACEMENT`, oriented by rule.
  - Jacks: sleeve above the tip.
  - Pots: pins on the side `pot_pins` gives.
  - LED buttons: LED pins along x, anode right.
  - LEDs: leads in a column, red anode at the bottom. On 2.54 mm pitch a
    row along x would put the outer pads on the buttons' LED pins (6.3 mm
    away); in a column the nearest pad is 2.05 mm off. D1's red anode sits
    straight above H4 pin 5 (LED_POLY_R).
- **Rear parts:** only in the strips the panel parts leave free.
  - The 74HC4051 lies at (33, 71), between the medium knobs and
    FREQUENCY / STRUCTURE, with C1 beside pin 16.
  - The five lug resistors stand upright in the 3.9 mm gaps between the jack
    columns, at x 2.4, 15.3, 28.3 and 41.3. Each sits beside its jack's lug:
    STRUM, V/OCT and IN on the bottom row, FM in the upper row.
  - The headers are as in the table above.
- No rear pad sits under a pot, jack or button body, which `front_housing_check`
  confirms.

**Main board** (PCB frame, rear view):
- **Breakout:** stands on its sockets near the centre (x 25.6–44.4), USB
  end down. That puts:
  - J5 (IN) at the bottom, 27 mm from H2's IN pin.
  - Pins 21–40 (A0–A5, A6, A9, A10, the mux address, 3V3A) facing the
    op-amps on the left.
  - Pins 1–20 (buttons, LEDs, STRUM, probe, AOUT) facing the logic on the
    right.

  This follows the move you made on Marblesy. Nothing is placed between
  its pad rows: the breakout's underside is unknown.
- **TL074s:** both stand left of the breakout, each with its four stages
  as Plaitsy's clusters (Rf against IN− and OUT, Rin and Rs one column out,
  Cf the next, each 100 n 3.6 mm from its supply pin).
  - U4 sits low, between H1 and the ADC pins: POSITION, V/OCT, ODD, EVEN.
  - U3 sits above it, level with A0–A3: FM, STRUCTURE, BRIGHTNESS, DAMPING.
- **Everything else** goes through the greedy placer, each block in its own
  area:
  - Below U4: the output coupling caps and DC resistors, the EVEN → ODD
    normal and the V/OCT clamps.
  - Above U3: the bias dividers.
  - Right of the breakout: STRUM, the probe clamps and the LED resistors.

**Standoffs:** four M3, the same on both boards, where both have room. The
jacks and attenuverters fill the faceplate's lower corners, so the four go
here (front view):
- (5.0, 49.4) and (21.8, 49.4), in the strip between the attenuverters'
  pins and the medium knobs. On the main board both land right of the
  breakout.
- (22.0, 100.0) and (48.0, 100.0), in the top strip either side of H4.

The main board's front-right corner below y 49 has no standoff; H1 and H2
hold it there.

**Checks** (in the exporter's output, all at 0):
- pads ≥ 0.25 mm apart and ≥ 0.5 mm from the edge;
- no two bodies overlapping on one side;
- nothing under a standoff or screw head;
- every header pin at the same spot on both boards;
- panel parts exactly at `PLACEMENT`;
- no rear pad under a panel part's body, and no panel part's pad under
  another's body;
- every PAD_NET on a real pad and a declared net.

**Ratsnest crossings** (each net as a minimum spanning tree, grounds left
out): faceplate 22, main board 202. Most of the main board's are the
3V3A and ±12 V buses and the CV lines entering the clusters; Plaitsy's
main board ended at 120.

### Routing notes

- **Rules:** clearance 0.25 mm, track 0.3 mm, POWER class 0.6 mm (±12 V,
  3V3A, 3V3D, 3V3A_F), via 0.8 / 0.4 mm, copper 0.5 mm from the edge.
  Keep out 3.5 mm round each standoff on its side.
- **Lock by hand first:**
  - the six CV and two output summing nodes (already a few mm each);
  - BIAS_A and BIAS_V as short trees from C27 and C28;
  - ADC_VOCT to pin 27 with its clamps;
  - the power buses up the decoupling columns.
  Then autoroute the rest: both layers, vertical on top, horizontal
  underneath, grounds and the POWER class skipped.
- **Main board ground:** one GND, poured on both layers. The socket side is
  nearly empty and is the plane. It must reach Seed pins 20 and 40 and the
  breakout's GND pins.
- **Faceplate grounds:**
  - GND_F (jacks, pots, mux) poured on the panel side.
  - GND_D_F (buttons, LEDs) as tracks on the rear.
  - They meet only on the main board, through their own header pins.
- **IN:** H2 → J5-1 along the bottom on the bottom layer, under the pour,
  away from the probe and STRUM.
- **AOUT_ODD / AOUT_EVEN:** from pins 18 / 19 across to C29 / C30. Keep them
  off the LED lines.
- **PROBE** (a 1 kHz square at 3.3 V): along the board edge, never beside
  a summing node or IN. On the faceplate it runs along the bottom past R4,
  R3 and R2.
- **Faceplate signal layers:** pot wipers and mux lines on the panel side
  under GND_F. LED and button lines on the rear, away from the wipers.

---

## Board estimate

| Board | Parts | Fits? |
|---|---|---|
| Faceplate 69.6 × 108 | 24 panel parts, 74HC4051 + 100 n, 5 lug resistors, 4 male headers (30 pins): 35 | Placed, 0 problems |
| Main board 69.6 × 108 | breakout on sockets, 2 TL074, 39 resistors, 16 capacitors, 2N3904, 5 diodes, 4 socket strips: 68 | Placed, 0 problems; the right of the breakout is half empty |

103 parts in all (Plaitsy: 109). Through-hole, hand-soldered, the Plaitsy
way; the stack depth is Plaitsy's.

---

## BOM

**Main board** (through-hole):

| Qty | Part | Notes | Refs |
|---|---|---|---|
| 1 | Daisy Seed (rev 7 / Seed 2 DFM, PCM3060) | | U2 |
| 1 | seed_power_opamps breakout (Rob Heel), built | on its sockets; its output op-amps unused | U2 |
| 2 | TL074 | DIP-14, rows 7.62 mm | U3, U4 |
| 1 | 2N3904 | TO-92, EBC | Q1 |
| 4 | BAT85 | DO-35 | D3, D4, D6, D7 |
| 1 | 1N4148 | DO-35 | D5 |
| 12 | 100k 1 % | | R21, R24, R27, R30, R33, R36, R44, R46, R48, R50, R52, R53 |
| 6 | 13k 1 % | | R22, R25, R28, R31, R34, R42 |
| 1 | 33k 1 % | | R37 |
| 2 | 15k 1 % | | R40, R43 |
| 1 | 12k 1 % | | R41 |
| 2 | 20k 1 % (Rin: 100k × V_fs / 9.8 V, measured) | fit after measuring | R45, R49 |
| 8 | 1k | | R23, R26, R29, R32, R35, R38, R47, R51 |
| 1 | 10k | | R54 |
| 2 | 150R | | R55, R56 |
| 4 | 330R | | R57–R60 |
| 6 | 1 n C0G / film | | C21–C26 |
| 2 | 1 µ | | C27, C28 |
| 2 | 10 µ bipolar (NP) electrolytic, 25 V or more | 6.3 mm can, 2.5 mm leads (Nichicon UES1H100MPM) | C29, C30 |
| 2 | 10 p C0G | | C31, C32 |
| 4 | 100 n | | C33–C36 |
| 4 | female sockets 1×6, 1×7, 1×8, 1×9, 2.54 mm | | H1–H4 |

**Faceplate:**

| Qty | Part | Notes | Refs |
|---|---|---|---|
| 10 | Thonkiconn PJ398SM (Thonk) | | J1–J10 |
| 10 | Alpha 9 mm vertical B10k (Thonk) + knobs Ø15 ×2, Ø12 ×3, Ø10 ×5 | | RV1–RV10 |
| 2 | Thonk low-profile LED button, white; clip the feet | | SW1, SW2 |
| 2 | 3 mm red/green bicolour LED, 3 leads at 2.54 mm, common cathode in the middle | lead pitch measured on the bought ones | D1, D2 |
| 1 | 74HC4051 | DIP-16, rear | U1 |
| 1 | 100 n | rear | C1 |
| 1 | 6k8 1 % | FM normal | R1 |
| 1 | 100k | STRUM probe | R2 |
| 1 | 470k | V/OCT probe | R3 |
| 1 | 1M | IN probe | R4 |
| 1 | 43k | IN lug load | R5 |
| 4 | male headers 1×6, 1×7, 1×8, 1×9, 2.54 mm | | HF1–HF4 |

Plus a 14HP panel PCB and 4 M3 standoffs for the 11 mm gap (8.5 mm sockets + 2.5 mm male plastic), with screws.

---

## Firmware plan: Rings on the Seed

The DSP is portable C++ (VCV Rack's Audible Instruments "Resonator" runs
the same code on a PC); what changes is the driver layer. Where the Seed
differs from Rings' hardware:

| | Rings | Seed | What the port does |
|---|---|---|---|
| MCU | STM32F405, Cortex-M4F at 168 MHz | STM32H750, Cortex-M7 at 480 MHz with caches | Nothing; at least 2.5× headroom. Rings' modal resonator gets 64 / voices − 4 modes per voice (60, 28, 12) to fit the F4; keep that (faithful); more modes at 2 and 4 voices is a possible later option |
| Sample rate | 48 kHz, 24-sample blocks (`dsp.h`: `kSampleRate`, `kMaxBlockSize`) | libDaisy's default 48 kHz; `SetAudioBlockSize(24)` | Nothing to retune, unlike Clouds (32 kHz inside, where Nimbus's 48 kHz shortened the buffers and the reverb) |
| Codec | WM8731, 16-bit I2S, IN on the right channel at −1.5 dB line gain | PCM3060 (rev 7 / Seed 2 DFM) through libDaisy's float callback, IN through the breakout's input stage | Drop the 16-bit conversions; scale IN so ±10.6 V = 1.0 and OUT so 1.0 = full scale; the IN detector's 50…1500 counts become 0.0015…0.046, its sign checked once |
| RAM | 128 KB SRAM + 64 KB CCM: the 64 KB reverb buffer in CCM, 8 strings × 12 KB of delay lines, 4 resonators × 64 filters, the easter egg's string synth sharing the reverb buffer: about 170 KB | 512 KB AXI SRAM, 128 KB DTCM, 288 KB D2 SRAM, 64 MB SDRAM | Fits. Under BOOT_SRAM the program itself runs from the AXI SRAM; if the linker puts .bss in the 128 KB DTCM, move the reverb buffer and the string delay lines to D2 SRAM or SDRAM with a section attribute |
| Flash | 1 MB; the app at 0x08008000, above Rings' 32 KB bootloader; lookup tables 24 KB | 128 KB internal, 8 MB QSPI | With libDaisy it will not fit the 128 KB comfortably: build for the Daisy bootloader (BOOT_SRAM), like the other Seed modules |
| Settings | calibration and state in internal flash (stmlib `Storage`) | QSPI | libDaisy `PersistentStorage` |
| ADC | 8 direct + 8 through a 4051, read sequentially | `AdcHandle` with 8 direct channels and `InitMux(A10, 8, D26, D27, D28)` | Map each reading through the CV stage above into Rings' 0…1 units, then `CvScaler` as is; the V/OCT detection threshold's accepted window moves from 0.70…0.80 to about 0.50…0.60 |
| STRUM, probe, LEDs, buttons | GPIOs: STRUM polled per block, probe written per block, LEDs PWM'd from the 1 kHz SysTick, 3 s long press | libDaisy `GPIO`, `Switch`, a 1 kHz timer callback | Same logic, new drivers; the button LEDs are new |

Calibration, the hidden modes (Rings 1.1's three extra models, the
easter egg) and the factory-test hooks stay as in Rings' `ui.cc`; the
factory-test serial port goes.

Licences: Rings' code is MIT (stmlib too); the hardware files, the panel
art included, are cc-by-sa 3.0. Ringsy's panel is redrawn and carries no
Mutable name or logo.

---

## Still open

- **Rin** on both outputs: measure the Seed's full scale first (above).
- **Routing** in EasyEDA Pro (yours). After routing, the routed export becomes
  the master, as on Marblesy: bring `circuit.py` to any pin, channel or part
  you swap, since the firmware's tables follow it.
- **The breakout's underside:** nothing is placed between its pad rows on
  the main board. Check how tall the parts on the underside of Rob Heel's
  board are before moving any part there.
- **Button LEDs:** what the port shows on them, if anything.
