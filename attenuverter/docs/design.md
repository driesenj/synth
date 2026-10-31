# Offset — design notes

Three offset attenuverters in 10HP Eurorack, all analog, on one PCB. Each
channel scales a CV or audio signal between −1 and +1, adds an offset of
±5 V or ±10 V (a toggle per channel), and shows the result on a bicolour
LED. The inputs normal down the column, so one source can feed all three
channels at different depths. The outputs add into the next channel when
unpatched, so the module also mixes modulation. Reference designators
match `hardware/tools/circuit.py`.

Status (2026-10-31): panel approved; netlist for one board (84 parts, 0
problems, DC check passing, see [Netlist](#netlist)); EasyEDA Pro
schematic, the placed PCB and the panel PCB generated and checked (see
[Schematic](#schematic) and [PCB](#pcb)), not yet imported. Routing is
yours.

---

## What it does

Per channel k:

```
OUT k = ATTEN k × IN k + OFFSET k  (+ OUT k−1, when OUT k−1 is unpatched)
```

| Control | Range | Notes |
|---|---|---|
| ATTEN k | −1 (CCW) … 0 (noon) … +1 (CW) | Linear. The ends are exact (1 % resistors); noon is 0 V whatever the input |
| OFFSET k | −5 V … +5 V, or −10 V … +10 V | From two LM4040 5.0 V references, so the ends do not move with the supply |
| RANGE k | lever down 5V, up 10V | Sets OFFSET k's range only |
| IN k | ±10 V, 100 kΩ | Unpatched, IN k takes IN k−1; IN 1 takes +1 V |
| OUT k | 1 kΩ series | Unpatched, it adds into channel k+1. OUT 3 is the sum of every channel whose output is unpatched |
| LED k | green = positive, red = negative | Lights from about ±2 V; brightness follows the voltage |

### Normals, and what they are for

- **Fan-out (inputs).** Patch one LFO into IN 1 and all three channels get
  it. Each ATTEN then sets that destination's depth and polarity, and each
  OFFSET sets its centre. Patch IN 2 as well, and channels 2 and 3 follow
  that source instead.
- **Fine offsets (IN 1 normal).** With nothing patched, every input sits
  at +1 V. ATTEN then becomes a fine ±1 V offset beside the coarse
  OFFSET. Use this to tune a pitch or to place a filter's cutoff exactly.
- **Mix (outputs).** Leave OUT 1 unpatched and take OUT 2: it carries
  channel 1 + channel 2. Use this to add an envelope to a slow LFO, or to
  add two LFOs into one cutoff. To use a channel alone, patch its output.
  Otherwise a channel whose output is unpatched still adds into the next
  channel, unless its ATTEN and OFFSET are both at noon.

---

## Circuit

Four op-amp sections per channel: a TL074 each for channels 1 and 2, two
TL072s for channel 3. A third DIP-14 does not fit behind the 10HP panel's
parts (see [PCB](#pcb)). Every signal stage is inverting, so no op-amp input
moves with the signal: a follower fed −10 V would sit past the old TL07x's
common-mode range on ±12 V, where its output can flip. All resistors are
100 k 1 % unless noted.

```
            IN k-1 (IN 1: NORM, +1 V)
               │ switch lug
 IN k jack ────┴─ tip ── 100k ──┬─[A −]── N_k = −IN_k
                                └─ 100k feedback
 N_k ── 100k ── [B −] ── P_k = +IN_k            (100k feedback)

 ATTEN k (B10k):   P_k ─ pin 1 ┤wiper├ pin 3 ─ N_k
 OFFSET k (B10k): +5 V ─ pin 1 ┤wiper├ pin 3 ─ −5 V

 ATTEN wiper ── 100k ─────────────────┐
 OFFSET wiper ─ 100k ─────────────────┤
 OFFSET wiper ─ RANGE k (up) ─ 100k ──┼── SUM_k ─[C −]── OA_k ── 1k ── OUT k tip
 CAS_k ──────── 100k ─────────────────┘   100k ∥ 22p      │
                                                          └── 2k2 ── bicolour LED ── GND

 OUT k switch lug ── 100k ─[D −]── CAS_k+1 = −OUT_k   (100k feedback; open lug = 0 V)
```

- **A and B** give the ATTEN pot a low-impedance end at each polarity. A
  pot hung on the jack itself would load the source, and with the inputs
  normalled three deep, one source would drive three pots.
- **C** inverts. Turning ATTEN clockwise takes its wiper to N_k (−IN), and
  turning OFFSET clockwise takes its wiper to −5 V, so both come out of C
  positive.
- **RANGE** puts a second 100k beside the OFFSET resistor: 50 k into the
  100 k feedback doubles the offset. The toggle sits in the wiper's path,
  so the summing node (virtual ground, the sensitive one) never runs to
  the panel. It is a Dailywell 2MS1 SPDT ON-ON with common on pin 2.
  Mounted with pin 3 at the bottom, lever up joins 2–3; pin 1 stays open.
  Toggles join the throw *opposite* the lever. That is standard, but ring
  one out before soldering three.
- **D** turns the previous channel's output back into the sign the summer
  wants. When OUT k is patched, the jack's switch lug opens and D outputs 0 V.
- **Wiper loading.** A B10k wiper into 100k reads 1.8 % low at three
  quarters of the travel; into the 50 k of the 10 V range, 3.6 %. The
  ends and noon are exact. That is why the pots are 10 k and not 100 k
  (100 k would read 16 % low at three quarters).
- Channel 1 has no CAS input, and OUT 3 has no D stage after it.
- **Headroom.** C swings about ±10.5 V on ±12 V. A full ±10 V offset sits
  just inside that; anything added to it clips, as expected.

### Op-amp sections

| Chip | Sections |
|---|---|
| U1 (TL074) | A: N_1, B: P_1, C: channel 1 summer, D: cascade 1 → 2 |
| U2 (TL074) | A: N_2, B: P_2, C: channel 2 summer, D: cascade 2 → 3 |
| U3 (TL072) | A: N_3, B: P_3 |
| U4 (TL072) | A: channel 3 summer, B: NORM, the follower for +1 V (39k / 10k from +5 V) |

### References and power

- **+5 V:** LM4040-5.0 (TO-92), cathode on the +5 V node, fed by 1k from
  +12 V. That gives 7 mA; the three OFFSET pots take 3 mA, which leaves 4 mA
  for the reference (its range is 0.06–15 mA).
- **−5 V:** a second LM4040-5.0, with its cathode on GND, fed by 1k to −12 V.
- **Power entry:** 16-pin Eurorack header (2.54 mm, shrouded). There is a
  1N5819 in each rail: the +12 V anode on the header, and the −12 V
  *cathode* on the header (the reversed −12 V diode on the older PCBs is the
  error to avoid). Each rail then has a 10 Ω and 10 µF, and each op-amp has a
  100 n pair at its supply pins (TL074: 4 = V+, 11 = V−; TL072: 8 = V+,
  4 = V−).
- **Current, estimated:** op-amps about 17 mA per rail, references 7 mA each,
  LEDs up to 3 × 3.6 mA, ATTEN pots up to 2 mA each at full input. That
  comes to about 40 mA per rail at worst, 25 mA typical.

---

## Netlist

`hardware/tools/circuit.py`, one board. `python circuit.py` prints the part
counts, the netlist problems (single-pin nets, designators used twice,
TL074 pins left out) and a DC check.

| Designators | What |
|---|---|
| J1–J3, J4–J6 | IN 1–3, OUT 1–3 (Thonkiconn: 1 sleeve, 2 switch lug, 3 tip) |
| RV1, RV3, RV5 / RV2, RV4, RV6 | ATTEN / OFFSET (pin 3 = CW end, both on the negative side; lugs 4, 5 on GND) |
| SW1–SW3 | RANGE toggles (2 common, 3 = lever up = 10 V, 1 open) |
| D1–D3 | output LEDs, 2-lead bicolour: current from pin 1 to pin 2 = green |
| U1, U2 | TL074 for channels 1 and 2, sections A (pins 1–3), B (5–7), C (8–10), D (12–14) |
| U3, U4 | TL072 for channel 3, sections A (1–3), B (5–7); `circuit.stage()` maps them |
| R*k*01–R*k*13, C*k*01 | channel *k*'s resistors and summer cap (R101 … R313) |
| D4, D5, R901–R904, C901, C902 | ±5 V references, the +1 V divider |
| J7, D6, D7, R905, R906, C903–C912 | power entry, bulk and decoupling (C905 … C912: a pair per op-amp) |

Net names say what they carry: `IN1`, `N1` (−IN), `P1` (+IN), `AW1` / `OW1`
(the wipers), `OR1` (the RANGE throw), `SUM1`, `OA1` (summer out), `OUT1`
(tip), `OSW1` (its switch lug), `CAS2` (OUT 1 inverted, into channel 2),
`NORM`, `REF_P`, `REF_N`.

**DC check.** `solve()` builds the netlist's nodal equations with ideal
op-amps and ideal references. It takes pot positions, RANGE levers and a
patch state: patched inputs as sources, patched outputs as 100k loads, and
an unpatched jack's lug shorted to its tip. It returns every node voltage.
`dc_check()` runs ten patch cases whose answers were worked out by hand:
- noon is 0 V
- the +1 V normal
- the offset ends at 5 V and at 10 V
- 3/4 OFFSET on the 10 V range, with its wiper loading
- fan-out
- a patched IN 2 breaking the chain
- cascades to OUT 2 and OUT 3

All pass to 1 µV. Two results worth knowing:

- Each cascade step reads the previous channel 1 % low: D takes OUT k's
  tip, which sits behind the 1k output resistor, into 100k.
- One source with a 1k output impedance, fanned out to all three inputs
  (3 × 100k), arrives at 97 %.

---

## Schematic

`hardware/easyeda/Offset.epro2`, written by `hardware/tools/easyeda_export.py`:
one board, four A3 pages, previews in `hardware/easyeda/offset-easyeda-*.png`.

| Page | Holds |
|---|---|
| Channel 1–3 | IN jack; A and B; ATTEN and OFFSET pots; the summer with the output resistor and the LED; OUT jack; RANGE toggle; the cascade inverter D (channels 1 and 2). Channel 3 draws its stages' networks with the junctions on ports, and the two TL072s (your library's one-unit symbol) with every pin on a port |
| References, +1 V normal, power | both LM4040s, the 39k / 10k divider (NDIV, to U4 B), the 16-pin header with its diodes, 10 Ω and 10 µF, the four decoupling pairs |
| Panel (its own board) | a note; the panel PCB itself |

Each block ends in net ports, and ports with the same name connect across
the pages.

**Parts.** They come from your library where it has them: the TL074ACN and
TL072CN symbols (the TL072CN cached from your MorrisSynth export in
`hardware/easyeda/offset-parts.epru`), the WQP518MA jack, the PTV09A pot
symbol, LR1F resistors, FG28 capacitors, 1N5819, the 10 µF and the 2×8 box
header. The rest is drawn here in the same style:
- **footprints:** the DIP-14 and DIP-8 on the 7.62 mm row pitch (the
  library ones have 9.0 / 9.1 mm rows), the Alpha 9 mm pot (the mixer's),
  TO-92, and a 2-lead 3 mm LED. The Dailywell 2MS1
  toggle has three pins at 2.54 mm and a 6 mm bushing, from Dailywell's
  2MS sheet.
- **symbols:** the LM4040 (Marblesy's, labelled 5.0 V), the bicolour LED
  as two LEDs back to back (green from pin 1 to pin 2), and the SPDT
  toggle.

All resistors are standing (the 2.54 mm footprint).

**Checks** (`python easyeda_export.py`):
- The drawing's connectivity matches the netlist on every page, with no
  T-junctions.
- Every pin with a net is drawn exactly once.
- Every symbol pin has a pad and every pad a pin.
- Every Device, Symbol and Footprint in the written file resolves, and on
  the PCBs every PAD_NET names a real pad of its part's footprint and a net
  with a NET record.
- Result: 0 problems, 90 part units.

**What EasyEDA's DRC will still report** (all intended):
- floating pins: SW1–SW3 pin 1 (the open throw), D4 / D5 pin 3 (the TO-92's
  NC lead), J6 pin 2 (OUT 3's switch lug: nothing after it), J7 pins 13–16
  (+5 V and the CV / gate bus, unused).

Import with File > Import > EasyEDA (Professional) > `Offset.epro2`, then
Design > Check DRC.

---

## PCB

One board, 49.3 × 108 mm, placed and net-assigned, unrouted, in
`Offset.epro2` beside the panel PCB. `hardware/tools/pcb.py` places it;
the preview is `hardware/easyeda/offset-easyeda-pcb.png` (rear view, as
EasyEDA shows the top layer: channel 1 on the right).

- **Front (bottom layer):** the jacks, pots, LEDs and RANGE toggles at their
  panel positions. The orientations are set by rule: jack sleeves up, pot
  pins down with pin 1 on the left, LED pad 1 (green anode) on the left,
  toggle pin 3 at the bottom.
- **Rear (top layer):** everything else, every resistor standing. A rear
  part's leads are soldered on the front, so no rear pad may sit under a
  front part's body. In 10HP those bodies cover most of the board, and what
  is left decides the layout:

| Where (front view) | What |
|---|---|
| strip above the ATTEN pots | U1, U2 (TL074) side by side; a third DIP-14 would need 50.5 mm of the 49.3 |
| between the IN and OUT jacks | U3, U4 (TL072), one between each pair of LEDs (0.5 mm to spare each side) |
| between the OFFSET and ATTEN pots | D4, D5 (LM4040), between the pot columns |
| under the OUT jacks | J7, the power header, pin 1 (−12 V, red stripe) on the left |
| side margins beside J7 | D7 and C904 (−12 V) on the left, D6 and C903 (+12 V) on the right |
| everything else | resistors and capacitors on a 2.54 mm grid in the margins, the channels between the pot columns and the strips between the rows |

`place_grid()` puts each small part on the free grid spot nearest to the
pads it connects to. Each part costs the distance from its pins to the nets
they join. Summing nodes count three times so they stay short, and GND a
fifth. The decoupling pairs go down first, each drawn to its own chip's
supply pins. There are no mounting holes: the jack, pot and toggle nuts
hold the board to the panel.

**Checks** (in `python easyeda_export.py`), all 0 problems:
- pads 0.25 mm apart and 0.5 mm from the edge
- no bodies overlapping on one side or reaching past the edge
- panel parts exactly at `PLACEMENT`
- no rear pad under a front body
- the PAD_NET parse

**Panel PCB:** 50.5 × 128.5 mm, from the same `panel.layout()` and
`panel.bands()` as the SVG. Holes and slots are non-plated, the artwork is
on silk, and the output band is bare ENIG copper with 0.4 mm clearance
rings. Order it on 1.6 mm FR4, black mask, white silk, ENIG. EasyEDA's
stroke font differs from the SVG's, so nudge labels after the import.

### Routing notes

- **Rules:** the project inherits an older board's rules (0.1 mm clearance).
  For hand soldering set:
  - clearance 0.25 mm and track 0.3 mm
  - a POWER class at 0.6 mm for +12V, −12V, P12_IN / N12_IN and P12_D / N12_D
  - REF_P, REF_N at 0.4 mm
  - vias 0.8 / 0.4 mm
  - copper 0.5 mm from the edge
- **Keepouts:** 3 mm round each jack barrel on the front layer (ground may
  stay).
- **Hand-route and lock first:**
  - the power buses: J7 → D6 / D7 → R905 / R906 → the four chips' supply
    pins, each beside its 100 n pair
  - REF_P and REF_N, as two trees from D4 / C901 and D5 / C902 to the
    three OFFSET pots' outer pins
  - the summing nodes NA, NB, SUM, ND at each op-amp: one layer, short
- **Then autoroute the rest:** both layers, vertical on top and horizontal
  on bottom. Skip GND and the POWER class.
- **Long runs:** IN and OUT run from the bottom jacks to U1 / U2 at the
  top, and channel 3's pots run down to U3 / U4. All of them are
  low-impedance (driven by an op-amp or a module output), so length doesn't
  matter. Keep them off the summing nodes and the wipers.
- **Ground:** one GND, poured on both layers. The front layer, between the
  panel parts, is the better plane: it shields the long CV runs on the
  rear.
- **LEDs:** the LED lines (OA → 2k2 → LED) carry up to 3.6 mA DC. Stand the
  3 mm LEDs on their leads or a spacer, so the lens reaches the 3.2 mm hole
  in the band.

---

## Panel

10HP, in the house style. The channels are columns like the mixer's
strips, 14.3 mm apart (the mixer's are 13.5 mm). Each row's word stands
once in the left margin, on a bracket. The knobs are at the top, the RANGE
toggles under the OFFSET knobs they belong to, and the jacks at the
bottom, so cables hang away from the hands. Each toggle's two positions
are stacked beside its lever, as on Atlas. The outputs and their LEDs sit
on the gold band. Dotted lines between the inputs show the fan-out; a +
between the outputs shows the mix.

![panel](../hardware/panel/offset-panel-preview.png)

| Row | Panel y (mm) | Parts |
|---|---|---|
| Channel numbers | 16.0 | silk |
| ATTEN | 27.0 | RV1, RV3, RV5: Alpha 9 mm B10k |
| OFFSET | 48.5 | RV2, RV4, RV6: Alpha 9 mm B10k |
| RANGE | 64.5 | SW1–SW3: sub-mini toggle, 6.5 mm hole |
| IN | 79.0 | J1–J3: Thonkiconn |
| LEDs | 92.5 | D1–D3: 3 mm bicolour, 2 leads |
| OUT | 104.0 | J4–J6: Thonkiconn |

Channel x: 12.0, 26.3, 40.6. `panel.py` reports no gaps under 1 mm. The
subtitle is "3× atten": in 10HP the title "Offset" ends at x 26, which
leaves room for about ten characters before the frame's right edge at
x 38.5.

---

## Parts (estimate)

| Qty | Part | Where | Notes |
|---|---|---|---|
| 6 | Thonkiconn PJ398SM | Thonk | |
| 6 | Alpha 9 mm vertical B10k | Thonk | A centre-detent version would help find noon on both rows; check stock |
| 3 | Sub-mini toggle SPDT ON-ON, PCB mount (Dailywell 2MS1 type) | Thonk / Tayda | |
| 3 | 3 mm bicolour LED red/green, 2 leads | Tayda | Thonk if stocked |
| 2 + 2 | TL074 + DIP-14 sockets, TL072 + DIP-8 sockets | Tayda | The footprints use 7.62 mm rows, not the library's 9 mm ones |
| 2 | LM4040 5.0 V, TO-92 | Mouser | A or B grade (0.1 / 0.2 %) |
| 30 | 100k 1 % | | |
| 3 + 3 | 1k, 2k2 | | output series, LED |
| 2 + 1 + 1 | 1k, 39k, 10k | | reference feeds, +1 V divider |
| 2 | 10 Ω | | rail filters |
| 3 | 22 p C0G | | summer feedback |
| 10 | 100 n | | 8 decoupling, 2 at the references |
| 2 | 10 µ electrolytic | | rail bulk |
| 2 | 1N5819 | | reverse protection |
| 1 | 16-pin shrouded Eurorack header, 2.54 mm | Thonk | Not the 2.00 mm footprint the FM / Clap / Compressor boards got |

---

## Choices

Settled on 2026-10-31:

1. **Width and channel count:** 10HP, three channels (the voice-case
   list's slot).
2. **IN 1 normal:** +1 V, a fine offset. +5 V (ATTEN becomes a second
   coarse offset) or 0 V (unpatched channels are pure offsets) is one
   resistor change: R903 / R904.
3. **OFFSET range:** ±5 V, with ±10 V on the toggle.
4. **The free strip:** the RANGE toggles.
5. **One board:** the panel parts on its front, everything else on its
   rear. The generators for the next steps are a one-board cut of the
   mixer's.
