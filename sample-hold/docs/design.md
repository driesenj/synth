# S&H — design notes

Sample & hold, noise and random for Eurorack, 10HP, after Moritz Klein's
MKI x ES.EDU S&H/Noise. The source is the build manual
(`SH_MANUAL_v1.pdf` in the Manuals folder): the breadboard chapters
(pp. 8–41) explain every stage, and the production schematic on p. 60
(EDUSH2 rev 2.0, 2021-10-25) gives the final values and designators. The
module is built the Marblesy way: two stacked PCBs behind a PCB panel,
Thonk panel parts, everything generated from `hardware/tools/`.

Status (2026-10-31): panel draft and this circuit plan, both waiting for
review. Netlist, schematic, PCBs and panel PCB are not started.

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
| Width | 10HP, one PCB | 10HP, two PCBs |

Changes from the MKI design, each easy to undo:

| Change | Why |
|---|---|
| RATE pot B250k → **B500k** (C7 stays 1 µF) | The internal clock runs 0.9–227 Hz instead of 1.8–227 Hz. A new random value every second or so is the dark-ambient speed; anything tighter comes from the clock module anyway |
| SLEW pot B100k → **A1M** | The MKI slew tops out at τ = 47 ms: enough for glide, but at slow rates the steps keep their corners. 1 MΩ gives τ up to 0.47 s, so stepped random becomes smooth random. The log taper keeps the MKI's whole range in the first half of the travel |
| **GATE output** from the spare TL074 section (DA1D, wired as an idle follower on the MKI board) | A comparator on the held voltage: one coin toss per clock, about 50 % high with noise at the input. Random hats and accents for techno with no extra chip. 7 parts and one jack |
| SLEW IN normalled from the S&H **buffer output**, not from the bare hold cap | On the MKI board the jack's switch lug hangs straight on C21. From the buffer, nothing outside the module touches the hold node. Same voltage |
| Power entry as on the house mixer: 16-pin shrouded header, 1N5819 pair, 10 Ω, bulk caps | House standard. The MKI uses a 10-pin header. Check the −12 V diode's direction (the house's known error) |

---

## Circuit, block by block

Designators are the MKI's (DA = op-amp, VT = transistor, VD = diode, XS =
jack). They become house designators in `circuit.py` at the netlist step.

### Noise (DA1A–C)

- **Source:** VT1 (BC548), base-emitter junction reverse-biased into
  breakdown, collector open. Its supply is +12 V → R14 4k7 → C8 47 µF to
  ground → R15 100k → emitter. Without that RC, rail ripple would be
  amplified 148 times along with the noise.
- **Amplifier:** C9 1 µF / R18 100k AC coupling into DA1B, a non-inverting
  stage with R21 100k / R20 680, a gain of 148: about 10 V p-p white noise.
- **WHITE:** DA1B → R9 1k → WHITE. DA1B's output also normals IN.
- **BLUE:** three series-RC branches in parallel (C15 5n6 + R28 1M, C16
  2n2 + R29 470k, C17 680p + R30 10k) into R34 20k to ground: a high
  shelf of about +3 dB/oct. DA1C ×1.33 (R37 33k / R35 100k) → R7 1k.
- **PINK:** R24 100k into three shunt RC legs to ground (C18 680p + R26
  4k7, C19 2n2 + R32 47k, C20 5n6 + R33 470k): about −3 dB/oct. DA1A ×5.5
  (R38 100k / R36 22k) → R8 1k.

### Internal clock (DA2A)

A Schmitt-trigger relaxation oscillator. C7 1 µF from the inverting input
to ground, charged from the output through R11 2k + RATE (wired as a
rheostat; fully CW = 2k = fastest). R12 100k / R10 100k feed back to the
non-inverting input, so it switches at half the output swing.
f = 1 / (2.2 · R · C), with R = 2k + RATE.

| RATE | MKI (B250k) | Here (B500k) |
|---|---|---|
| fully CCW | 1.8 Hz | 0.9 Hz |
| noon | 3.6 Hz | 1.8 Hz |
| 90 % | 17 Hz | 8.7 Hz |
| fully CW | 227 Hz | 227 Hz |

The output (±11 V) goes through R13 100k to CLOCK's switch lug. The 100k
limits the ±23 V edges to about 8 V spikes at the differentiator.

### Trigger shaping (DA2B) and the clock LED

- **Differentiator:** CLOCK's tip → C12 1 nF → R22 100k to ground, then
  VD4 1N4148 (positive spikes only) and R23 100k to ground.
- **Comparator:** DA2B. The threshold on its inverting input is R27 100k
  from +12 V and R25 33k to ground, about 3 V. Each rising edge gives a
  sampling pulse of about 50–100 µs at ±11 V. A 5 V gate is enough.
- **LED:** CLOCK's tip → R17 51k → VT2 (2N3904) base, collector → VD1 (red
  3 mm) → R16 2k → +12 V, about 5 mA. It lights for the high half of
  whatever clock is in use, internal or patched.

### Sample & hold (DA2D, VT3, DA2C)

- **Input:** IN (normalled to white noise) → LEVEL (B100k divider) → DA2D
  buffer → VT3 J113 source/drain → C21 100 nF film, the hold cap.
- **Gate drive:** R31 1M from the buffered input to the JFET gate, VD5
  1N4148 from the gate (anode) to DA2B's output (cathode). When DA2B's
  output is high, VD5 blocks, the gate floats to the source through R31,
  and the JFET conducts. When it is low, the gate is pulled to about −10 V
  and the JFET is off: hold.
- **Output:** DA2C buffer → R6 1k → S&H. DA2C's output also normals SLEW
  IN (changed, see above).
- **Range:** the JFET can't switch off for inputs below about −7 V (J113
  pinch-off up to −3 V, gate at −10 V). Full white noise is ±5 V, so this
  only matters for hot external signals: turn LEVEL down.
- **Droop:** about 0.3 mV/s (TL074 bias current into 100 nF).

### Slew (DA3A/B)

SLEW IN → DA3B buffer → SLEW (A1M rheostat, fully CCW = 0 Ω) → C22
470 nF to ground → DA3A buffer → R39 1k → SLEW. τ = 0–0.47 s (MKI 0–47 ms).

### Random gate (DA1D, new)

DA2C's output (the held voltage) → 10k into DA1D's non-inverting input,
1M from the output back to it (±0.1 V of hysteresis). The inverting input
is grounded. Output → 1N4148 → 1k → GATE, with 100k from the diode's
cathode to ground: 0 V or about +10 V. The gate changes only on a clock,
because the voltage it watches is held. With noise at IN it is a fair coin
per clock; with an LFO at IN it marks the LFO's positive half.

### Power

16-pin header, 1N5819 on each rail (for −12 V the cathode faces the
header), 10 Ω, 47 µF + 100 nF per rail, 100 nF at each op-amp's supply
pins. Draw: about 25 mA on +12 V and 15 mA on −12 V (three TL07x, the LED).

---

## Boards

```
 panel ─┬─ faceplate board (FB)   9 Thonkiconn, 3 Alpha 9 mm pots, the clock LED,
        │   49.3 x 108 mm          male headers; nothing else
        │  8.5 mm gap, M3 standoffs
        └─ main board (MB)         2x TL074, TL072, J113, BC548, 2N3904, all passives,
            49.3 x 108 mm          power header, female sockets
```

About 20 nets cross between the boards: CLOCK's tip and its switch lug, IN's
switch lug (white noise) and LEVEL's wiper, SLEW IN's tip and its switch
lug, the six outputs (after their 1k), both ends of the RATE and SLEW
rheostats, the LED's two leads, and ground. That is two 1×10 headers, one at
each side edge beside the jack columns (where Marblesy's user moved them
when routing). Pin orders are brute-forced for the fewest crossings at the
netlist step.

The MKI fits on one board with the jacks and pots soldered to it. Two boards
keep the house tooling (header and clearance checks, the generated panel
PCB) and give the circuit a whole board for hand routing.

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
  a bot check during this draft). Fallbacks: B1M for RATE (0.45–227 Hz,
  more travel at the slow end), B1M for SLEW (linear, fine glide crowded
  into the first 10 %).
- **J113**: onsemi's TO-92 part is getting scarce. J112 also works (pinch-off
  −1 to −5 V, so the clean input range shrinks to about −5 V); J111 does not.
- The LED has to reach the panel across the 7 mm between the faceplate
  board and the panel: a 3 mm LED on a spacer, or long legs set to height.
