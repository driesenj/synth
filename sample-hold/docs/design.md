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
problems, 0 circuit check failures (`python circuit.py`). Schematic, PCB
placement and panel PCB are not started.

The p. 60 schematic is vector art that pdftotext and pypdf can't read;
it was rendered by turning the page's content stream into SVG.

---

## What the MKI module has, and what changes

| Function | MKI S&H/Noise | Here |
|---|---|---|
| Noise | white, pink, blue outputs | the same |
| S&H | JFET (J113) switch, 100 nF hold cap, CV IN with level pot, normalled to white noise | the same |
| Clock | internal square-wave clock (RATE), CLOCK IN normalled to it, LED | the same, RATE range halved at the slow end |
| Slew | SLEW IN normalled to the S&H, slew pot, SLEW OUT | the same, with a ten times longer slew |
| Random gate | — | **new**: GATE out, high when the held voltage is above 0 V |
| Jacks / pots | 8 / 3 | 9 / 3 |
| Width | 10HP, one PCB | 10HP, one PCB |

Changes from the MKI design, each easy to undo:

| Change | Why |
|---|---|
| RATE pot B250k → **B500k** (C201 stays 1 µF) | The internal clock runs 0.9–228 Hz instead of 1.8–228 Hz. A new random value every second or so is the dark-ambient speed; anything tighter comes from the clock module anyway |
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

A Schmitt-trigger relaxation oscillator. C201 1 µF (film; it sees ±5.5 V)
runs from the inverting input to ground. It charges from the output through
R201 2k and RATE (RV1, wired as a rheostat; fully CW = 0 Ω, the fastest).
R202 100k / R203 100k feed back to the non-inverting input, so the output
switches at ±5.5 V. f = 1 / (2.2 · R · C), with R = 2k + RATE.

| RATE | MKI (B250k) | Here (B500k) |
|---|---|---|
| fully CCW | 1.8 Hz | 0.9 Hz |
| noon | 3.6 Hz | 1.8 Hz |
| 90 % | 17 Hz | 8.7 Hz |
| fully CW | 228 Hz | 228 Hz |

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
| RV1 | RATE, B500k | RT (R201) | OSC | OSC |
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

## Board

One PCB, 49.3 × 108 mm, behind the 10HP panel. Panel parts on its front:
9 Thonkiconn, 3 Alpha 9 mm pots, the clock LED. Everything else on its
rear: 2 TL074 and a TL072, three TO-92s, 5 diodes, 39 resistors, 20
capacitors, the power header. The MKI fits the same circuit on one 10HP
board, so it fits here. Placement will show where.

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

- Thonk stock of Alpha 9 mm **B500k** and **A1M** (Thonk's site sat behind
  a bot check during the draft). Fallbacks: B1M for RATE (0.45–228 Hz,
  more travel at the slow end), B1M for SLEW (linear, fine glide crowded
  into the first 10 %).
- **J113**: onsemi's TO-92 part is getting scarce. J112 also works (pinch-off
  −1 to −5 V, so the clean input range shrinks to about −5 V); J111 does not.
- The LED has to reach the panel across the 7 mm between the board and
  the panel: a 3 mm LED on a spacer, or long legs set to height.
- Film capacitors: C102, C201 (1 µF), C301 (100 nF, the hold cap) and C401
  (470 nF). C201 and C102 see both polarities, so no electrolytics there.
