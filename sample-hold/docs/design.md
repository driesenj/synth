# S&H — design notes

Sample & hold, noise and random for Eurorack, 10HP, after Moritz Klein's
MKI x ES.EDU S&H/Noise. The source is the build manual
(`SH_MANUAL_v1.pdf` in the Manuals folder): the breadboard chapters
(pp. 8–41) explain every stage, and the production schematic on p. 60
(EDUSH2 rev 2.0, 2021-10-25) gives the final values. The module is built
the Marblesy way on **one PCB**: Thonk panel parts on its front,
everything else behind them, a PCB panel, everything generated from
`hardware/tools/`. Every designator here matches `hardware/tools/circuit.py`.

Status (2026-10-31): panel agreed; netlist written, 84 parts, 0 netlist
problems, 0 circuit check failures (`python circuit.py`); EasyEDA Pro
schematic generated, 4 pages, 0 problems against the netlist
(`hardware/easyeda/SampleHold.epro2`, see [Schematic](#schematic)); the board
placed and the panel as a PCB in the same project (see [Board](#board)),
0 problems. Not yet opened in EasyEDA, not routed.

The p. 60 schematic is vector art that pdftotext and pypdf can't read;
it was rendered by turning the page's content stream into SVG.

---

## What the MKI module has, and what changes

| Function | MKI S&H/Noise | Here |
|---|---|---|
| Noise | white, pink, blue outputs | the same |
| S&H | JFET (J113) switch, 100 nF hold cap, CV IN with level pot, normalled to white noise | the same |
| Clock | internal square-wave clock (RATE), CLOCK IN normalled to it, LED | the same, slower: 0.8–103 Hz |
| Slew | SLEW IN normalled to the S&H, slew pot, SLEW OUT | the same, with a ten times longer slew |
| Random gate | — | **new**: GATE out, high when the held voltage is above 0 V |
| Jacks / pots | 8 / 3 | 9 / 3 |
| Width | 10HP, one PCB | 10HP, one PCB |

Changes from the MKI design, each easy to undo:

| Change | Why |
|---|---|
| Clock timing cap C201 1 µF → **2.2 µF** (RATE stays the MKI's B250k) | The internal clock runs 0.8–103 Hz instead of 1.8–228 Hz. A new random value every second or so is the dark-ambient speed; the top octave lived in the last 2–3 % of the travel, and anything tempo-locked comes from the clock module anyway. The first plan, B500k with 1 µF, played the same, but Thonk has no B500K |
| SLEW pot B100k → **A1M** | The MKI slew tops out at τ = 47 ms: enough for glide, but at slow rates the steps keep their corners. 1 MΩ gives τ up to 0.47 s, so stepped random becomes smooth random. The log taper keeps the MKI's whole range in the first half of the travel |
| **GATE output** from the TL074 section the MKI board leaves idle (U1D) | A comparator on the held voltage: one coin toss per clock, about 50 % high with noise at the input. Random hats and accents for techno with no extra chip. 5 parts and one jack |
| SLEW IN normalled from the S&H **buffer output**, not from the bare hold cap | On the MKI board the jack's switch lug hangs straight on the hold cap. From the buffer, nothing outside the module touches the hold node. Same voltage |
| Power entry as on the house modules: 16-pin shrouded header, 1N5819 pair, 10 Ω, 47 µF | House standard. The MKI uses a 10-pin header |
| Test points TP1–TP7 left out | The manual has no troubleshooting table that uses them |

---

## Circuit, block by block

Op-amps: U1 and U2 are TL074, U3 is TL072. Each section does the same job
as on the MKI board (DA1 = U1, DA2 = U2, DA3 = U3), plus U1D for the gate.

| Section | Job | Out, in−, in+ |
|---|---|---|
| U1A | pink, ×5.5 | POUT, PFB, PKN |
| U1B | white, ×148 | WN, WFB, NIN |
| U1C | blue, ×1.33 | BOUT, BFB, BLN |
| U1D | gate comparator (new) | GTO, GND, GTP |
| U2A | clock oscillator | OSC, OSC_C, OSC_P |
| U2B | trigger comparator | SAMP, THR, TRG |
| U2C | hold buffer | SHB, SHB, HOLD |
| U2D | input buffer | SHI, SHI, LV |
| U3A | slew out buffer | SLO, SLO, SLC |
| U3B | slew in buffer | SLB, SLB, SLI |

### Noise (R101–R120, C101–C108, Q1)

- **Source:** Q1 (BC548) has its base on ground and its collector open, so
  the base-emitter junction runs in reverse breakdown. Supply: +12 V →
  R101 4k7 → C101 47 µF to ground → R102 100k → emitter. Without that RC,
  rail ripple would be amplified 148 times along with the noise.
- **White:** C102 1 µF / R103 100k AC coupling into U1B, a non-inverting
  stage with R104 100k / R105 680, a gain of 148: about 10 V p-p. U1B → R106
  1k → WHITE. U1B's output (WN) also normals IN.
- **Blue:** three series-RC legs from WN (C103 5n6 + R107 1M, C104 2n2 +
  R108 470k, C105 680p + R109 10k) into R110 20k to ground, then U1C ×1.33
  (R111 33k / R112 100k) → R113 1k.
- **Pink:** R114 100k from WN into three shunt RC legs to ground (C106 680p
  + R115 4k7, C107 2n2 + R116 47k, C108 5n6 + R117 470k), then U1A ×5.5
  (R118 100k / R119 22k) → R120 1k.

Measured on the netlist (ideal op-amps, flat noise in, 20 Hz–20 kHz):

| Output | Slope | Level against white |
|---|---|---|
| PINK | −0.5 to −1 dB/oct below 300 Hz, −2 to −3 dB/oct from 300 Hz to 10 kHz | +2 dB |
| BLUE | +2 to +5 dB/oct, steepest 1–5 kHz | −4 dB |

These are approximations by design: three legs per filter. They are kept as
Klein drew them.

### Internal clock (R201–R204, C201, U2A)

A Schmitt-trigger relaxation oscillator. C201 2.2 µF (film; it sees ±5.5 V)
runs from the inverting input to ground. It charges from the output through
R201 2k and RATE (RV1, wired as a rheostat; fully CW = 0 Ω, the fastest).
R202 100k / R203 100k feed back to the non-inverting input, so the output
switches at ±5.5 V. f = 1 / (2.2 · R · C), with R = 2k + RATE.

| RATE (B250k) | MKI (C201 1 µF) | Here (2.2 µF) |
|---|---|---|
| fully CCW | 1.8 Hz | 0.8 Hz |
| noon | 3.6 Hz | 1.6 Hz |
| 90 % | 17 Hz | 7.7 Hz |
| fully CW | 228 Hz | 103 Hz |

The output (±11 V) goes through R204 100k to CLOCK's switch lug. The 100k
limits the ±22 V edges to about 8 V spikes at the differentiator.

### Trigger shaping and the clock LED (R205–R210, C202, D201, Q2, D1)

- **Differentiator:** CLOCK's tip (CLK) → C202 1 nF → R207 100k to ground,
  then D201 1N4148 (positive spikes only) and R208 100k to ground.
- **Comparator:** U2B, against THR = 3 V (R209 100k from +12 V, R210 33k to
  ground). Each rising edge gives a sampling pulse (SAMP) of about 50–100 µs
  at ±11 V. A 5 V gate is enough.
- **LED:** CLK → R205 51k → Q2 (2N3904) base, collector → D1 (red, 3 mm) →
  R206 2k → +12 V, about 5 mA. It lights for the high half of whatever clock
  is in use, internal or patched.

### Sample & hold (RV2, R301–R302, C301, D301, Q3, U2C/D)

- **Input:** IN (normalled to WN) → LEVEL (RV2, B100k divider) → U2D buffer
  (SHI) → Q3 J113 → HOLD, C301 100 nF film to ground → U2C buffer (SHB) →
  R302 1k → S&H. SHB also normals SLEW IN and feeds the gate.
- **Gate drive:** R301 1M from SHI to the JFET gate, D301 1N4148 from the
  gate (anode) to SAMP (cathode). When SAMP is high, D301 blocks, the gate
  floats to the source through R301, and the JFET conducts. When SAMP is
  low, the gate is pulled to about −10 V and the JFET is off: hold.
- **Tracking:** Q3's on-resistance (100 Ω at most) into C301 is a 16 kHz
  low-pass, τ = 10 µs; the 50–100 µs sampling pulse is 5–10 time
  constants, enough to settle.
- **Range:** the JFET can't switch off for inputs below about −7 V (J113
  pinch-off up to −3 V, gate at −10 V). Full white noise is ±5 V, so this
  only matters for hot external signals: turn LEVEL down.
- **Droop:** about 0.3 mV/s (TL074 bias current into 100 nF).

### Slew (RV3, C401, R401, U3)

SLEW IN (normalled to SHB) → U3B buffer (SLB) → SLEW (RV3, A1M rheostat,
fully CCW = 0 Ω) → SLC, C401 470 nF film to ground → U3A buffer → R401 1k →
SLEW. τ = 0–0.47 s (MKI 0–47 ms).

### Random gate (R501–R504, D501, U1D, new)

SHB → R501 10k into U1D's non-inverting input, with R502 1M from the output
back to it. The inverting input is grounded. The gate goes high above
+0.11 V and low below −0.11 V. U1D → D501 1N4148 → R504 1k → GATE, with R503
100k from the diode's cathode to ground: 0 V or about +10 V. The gate
changes only on a clock, because the voltage it watches is held. With noise
at IN it is a fair coin per clock; with an LFO at IN it marks the LFO's
positive half.

### Power (J10, D901/D902, R901/R902, C901–C908)

16-pin header J10. D901 1N5819 in +12 V (anode on the header), D902 in
−12 V (cathode on the header: the direction the house PCBs got wrong
before). R901/R902 10 Ω, C901/C902 47 µF, and a 100 nF pair at each
op-amp (C903–C908). Draw: about 25 mA on +12 V, 15 mA on −12 V.

---

## Jacks and pots

| Ref | Label | Tip | Switch lug (unpatched) |
|---|---|---|---|
| J1 | CLOCK | CLK | CLK_INT: the internal clock through R204 |
| J2 | IN | IN | WN: white noise |
| J3 | SLEW IN | SLI | SHB: the S&H |
| J4–J9 | GATE, WHITE, S&H, PINK, BLUE, SLEW | the outputs, after their 1k | open |

| Ref | Label | Pin 3 (CW) | Wiper | Pin 1 (CCW) |
|---|---|---|---|---|
| RV1 | RATE, B250k | RT (R201) | OSC | OSC |
| RV2 | LEVEL, B100k | IN | LV | GND |
| RV3 | SLEW, A1M | SLC | SLC | SLB |

Transistor pinouts used in the netlist, to check against the symbols at the
schematic step: BC548 1 C, 2 B, 3 E; 2N3904 1 E, 2 B, 3 C; J113 (onsemi
TO-92) 1 D, 2 S, 3 G.

---

## Circuit check

`python circuit.py` solves the netlist with ideal op-amps. Comparators get
their saturated output per case (±11 V); Q1 is replaced by a signal
injected at its emitter; Q2 and the LED are left out. Cases:

- the three comparator thresholds: THR = 2.98 V, the clock's ±5.5 V, and
  the gate's ±0.11 V hysteresis
- GATE high (+10.25 V into 100k) and low (0 V)
- tracking: 3 V into IN with LEVEL CW reaches S&H and, through the SLEW
  IN normal, SLEW; LEVEL at 1/4; a patched SLEW IN breaking the normal
- RATE fully CW leaves only R201's 2k
- AC: white ×148 at 1 kHz; IN's white-noise normal tracking through Q3 and
  C301; pink and blue slopes; SLEW −3 dB at 1 / (2π · 1M · 470n)

Four planted wiring errors each made it fail: the RATE pot reversed, the
SLEW pot reversed, IN normalled after the 1k instead of before it, and the
gate's 10k and 1M swapped.

---

## Schematic

`python easyeda_export.py` writes `hardware/easyeda/SampleHold.epro2`: one
board, four A3 pages, previews beside it (`sample-hold-easyeda-*.png`).

| Page | Holds |
|---|---|
| Noise | Q1 and its supply filter, U1B white, U1C blue, U1A pink; WHITE, PINK, BLUE jacks |
| Clock and trigger | U2A with RATE, R204 to CLOCK's lug, the differentiator and U2B, the LED driver; CLOCK jack |
| S&H, slew, gate | LEVEL, U2D, Q3 with its gate drive, C301, U2C; U3B, SLEW, C401, U3A; U1D gate; IN, SLEW IN, S&H, SLEW, GATE jacks |
| Power | J10, D901/D902, R901/R902, C901/C902, the three decoupling pairs |

Blocks end in net ports; ports with the same name connect across pages.
Library parts from your MorrisSynth export (TL074, Thonkiconn, pot symbol,
LR1F resistors, FG28 capacitors, 1N5819, the 1N4148's DO-35, the
electrolytic, the 2×8 header). Drawn here: a TL072 (the library TL074's
units 1–2, supply pins renumbered to 8 / 4), NPN symbols for the BC548
and the 2N3904 (pin numbers differ), the J113, a 3 mm LED; footprints for
DIP-14, DIP-8, TO-92, the LED, the Alpha pot, standing resistors and a 5 mm
film capacitor. The 1N4148 uses the 1N5819 symbol (1 = cathode = the band).

The exporter checks the drawing against `circuit.py` (every pin drawn
once, every net in one piece and touching no other, no T-junctions), every
footprint pad against a symbol pin, and every Device, Symbol and Footprint
in the written file. Eight planted swaps (diode and electrolytic polarity,
the TL072's supplies, the JFET's and 2N3904's pins, a jack lug, the SLEW
pot's ends) were each reported.

EasyEDA's own DRC will still warn about floating pins it can't know are
meant to be open: Q1's collector (pin 1) and the power header's pins 13–16
(the +5 V, CV and gate bus pins).

---

## Board

One PCB, 49.3 × 108 mm, behind the 10HP panel, placed, net-assigned and
unrouted in `SampleHold.epro2` (`pcb.py`; the panel is the project's
second PCB, `panel_pcb.py`). Preview: `sample-hold-easyeda-pcb.png`, rear
view (EasyEDA's top layer is the rear).

- **Front (bottom layer):** 9 Thonkiconn, 3 Alpha 9 mm pots, the clock LED,
  at their panel positions. Output rows at Marblesy's heights.
- **Rear (top layer):** everything else, every resistor standing. No rear
  pad sits under a jack or pot body (those leads are soldered on the
  front, where the bodies lie on the board).

Where things went, front view:

| Area | Holds |
|---|---|
| Strip above RATE and SLEW | J10 power header (pin 1, −12 V, red stripe, on the left); D902 / R902 left of it, D901 / R901 right; the 47 µF caps in the margins beside the pots |
| Between RATE and SLEW, above LEVEL | U2 (clock, trigger, S&H), its oscillator parts, the trigger chain, C201 |
| Left of LEVEL | U1 (noise, gate), turned so its noise input (pin 5) faces the middle, away from the clock LED; Q1, C102, R103 right beside it; the LED driver above, round D1 |
| Right of LEVEL, under SLEW | U3 (slew); Q3, C301, D301 for the S&H between U2 and SLEW |
| Between and beside the jacks | the blue and pink filters, the output resistors |

The op-amps and the header are placed by hand. `place_auto()` places every
other part where its pins are nearest the pads on their nets. It test-fits
each spot against the real footprint: 8 mm diodes, TO-92s and film caps up
to 8.5 mm thick all go through the same placer. An improvement pass then
lifts each part and re-places it until nothing moves (5 rounds), so the
result doesn't depend on placing order.

Clock-carrying pads pay a penalty within 8 mm of the noise amp's input.
The power entry is kept to the strip and margins at the top. The trigger
chain stays near U2.

Measured: decoupling caps 2.5–4.7 mm from their supply pins. Ratsnest
(minimum spanning tree per net, ground left out) 1194 mm with 98 crossings.

| Node | Ratsnest length |
|---|---|
| NIN (×148 input) | 7.6 mm |
| NE (noise emitter) | 5.1 mm |
| JG (JFET gate) | 7.3 mm |
| HOLD (hold cap) | 15.7 mm |

### Routing notes

- **Rules:**
  - Clearance 0.25 mm, track 0.3 mm.
  - POWER net class 0.6 mm: +12V, −12V, P12_IN, N12_IN, P12_D, N12_D.
  - Vias 0.8 / 0.4 mm; copper 0.5 mm from the edge.
- **Keepouts:** 3 mm round each jack barrel on the front layer. Ground copper may stay.
- **Hand-route and lock first:**
  - The noise front end, on one layer over ground: Q1 emitter, C102, R103, U1 pin 5, and R104 / R105 at pins 6 / 7.
  - The hold node (Q3 drain, C301, U2 pin 10) and the JFET gate (R301, Q3 gate, D301): short, with nothing switching beside them.
  - OSC_C (C201, R201, U2 pin 2).
  - The ±12 V buses from R901 / R902 across the top strip to the three chips.
- **CLK** (CLOCK jack tip to C202 and R205) runs the length of the left side. Take it up the left board edge, outside U1. Never run it between U1 and Q1 / C102, and keep it on the other layer from the noise front end.
- **Then autoroute:** both layers, 45° corners, few vias, skipping GND and the POWER class. Then pour GND on both layers and stitch the pours with vias between the jack rows.

---

## Panel

10HP, 50.5 × 128.5 mm, the house frame (title, band, rule, maker at the
same spots as on every module). One column per control: RATE over the
clock LED and CLOCK, LEVEL over IN, SLEW over SLEW IN, joined by dotted
guides. The six outputs share one gold block in the two lower rows, which
sit at Marblesy's and Side FXy's jack heights so the rows line up in the
rack. Short dotted lines from WHITE up to IN and from S&H up to SLEW IN mark
the normals.

---

## To verify before ordering

- Pots, checked against Thonk's list (2026-10-31): Alpha 9 mm vertical T18
  **B250K** (RATE), **B100K** (LEVEL) and **A1M** (SLEW) are all in stock.
- **J113**: onsemi's TO-92 part is getting scarce. J112 also works (pinch-off
  −1 to −5 V, so the clean input range shrinks to about −5 V); J111 does not.
- The LED has to reach the panel across the 7 mm between the board and
  the panel: a 3 mm LED on a spacer, or long legs set to height.
- Film capacitors: C102 (1 µF), C201 (2.2 µF), C301 (100 nF, the hold
  cap) and C401 (470 nF). C201 sees both polarities, so no electrolytic
  there. The film footprints assume a 7.2 mm long body on a 5 mm pitch,
  5.5 mm thick (8.5 mm for C201's 2.2 µF); check the parts bought.
- The 680p–5n6 filter and trigger caps are C0G ceramics (TDK FG28 C0G
  part numbers in the schematic; the MKI uses foil). Check that the 2n2 and
  5n6 exist in that series, or use any C0G or film part on 5 mm.
- The 47 µF electrolytics use the library 10 µF part's footprint (4.8 mm
  can, 2.5 mm pitch): a 47 µF 25 V in a 5 mm can fits it.
