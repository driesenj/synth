# Offset — design notes

Four offset attenuverters in 12HP Eurorack, all analog. Each channel scales
a CV or audio signal between −1 and +1, adds a ±5 V offset, and shows the
result on a bicolour LED. The inputs normal down the column, so one
source can feed all four channels at different depths. The outputs add into
the next channel when unpatched, so the module also mixes modulation.
Reference designators match `hardware/tools/circuit.py`.

Status (2026-10-31): panel draft and circuit plan. The netlist, schematic
and PCBs follow once the panel and the [open choices](#open-choices) are
agreed.

---

## What it does

Per channel k:

```
OUT k = ATTEN k × IN k + OFFSET k  (+ OUT k−1, when OUT k−1 is unpatched)
```

| Control | Range | Notes |
|---|---|---|
| ATTEN k | −1 (CCW) … 0 (noon) … +1 (CW) | Linear. The ends are exact (1 % resistors); noon is 0 V whatever the input |
| OFFSET k | −5 V … +5 V | From two LM4040 5.0 V references, so the ends are ±5.00 V and do not move with the supply |
| IN k | ±10 V, 100 kΩ | Unpatched, IN k takes IN k−1; IN 1 takes +1 V |
| OUT k | 1 kΩ series | Unpatched, it adds into channel k+1. OUT 4 is the sum of every channel whose output is unpatched |
| LED k | green = positive, red = negative | Lights from about ±2 V; brightness follows the voltage |

### Normals, and what they are for

- **Fan-out (inputs).** Patch one LFO into IN 1 and all four channels get it.
  Each ATTEN then sets that destination's depth and polarity, and each
  OFFSET sets its centre. Patch IN 3 as well, and channels 3 and 4 follow
  that source instead.
- **Fine offsets (IN 1 normal).** With nothing patched, every input sits
  at +1 V. ATTEN then becomes a fine ±1 V offset beside the coarse ±5 V
  OFFSET. Use this to tune a pitch or to place a filter's cutoff exactly.
- **Mix (outputs).** Leave OUT 1 unpatched and take OUT 2: it carries
  channel 1 + channel 2. Use this to add an envelope to a slow LFO, or to
  add two LFOs into one cutoff. To use a channel alone, patch its output.
  Otherwise a channel whose output is unpatched still adds into the next
  channel, unless its ATTEN and OFFSET are both at noon.

---

## Circuit

One TL074 per channel. Every signal stage is inverting, so no op-amp input
moves with the signal: a follower fed −10 V would sit past the old TL07x's
common-mode range on ±12 V, where its output can flip. All resistors are 100 k 1 % unless noted.

```
            IN k-1 (IN 1: NORM, +1 V)
               │ switch lug
 IN k jack ────┴─ tip ── 100k ──┬─[A −]── N_k = −IN_k
                                └─ 100k feedback
 N_k ── 100k ── [B −] ── P_k = +IN_k            (100k feedback)

 ATTEN k (B10k):   P_k ─ pin 1 ┤wiper├ pin 3 ─ N_k
 OFFSET k (B10k): +5 V ─ pin 1 ┤wiper├ pin 3 ─ −5 V

 ATTEN wiper ── 100k ──┐
 OFFSET wiper ─ 100k ──┼── SUM_k ─[C −]── OA_k ── 1k ── OUT k tip
 CAS_k ──────── 100k ──┘    100k ∥ 22p feedback  │
                                                 └── 2k2 ── bicolour LED ── GND

 OUT k switch lug ── 100k ─[D −]── CAS_k+1 = −OUT_k   (100k feedback; open lug = 0 V)
```

- **A and B** give the ATTEN pot a low-impedance end at each polarity. A
  pot hung on the jack itself would load the source, and with the inputs
  normalled four deep, one source would drive four pots.
- **C** inverts. Turning ATTEN clockwise takes its wiper to N_k (−IN), and
  turning OFFSET clockwise takes its wiper to −5 V, so both come out of C
  positive.
- **D** turns the previous channel's output back into the sign the summer
  wants. When OUT k is patched, the jack's switch lug opens and D outputs 0 V.
- **Wiper loading.** A B10k wiper into 100k reads 1.8 % low at three
  quarters of the travel, under 1 % of full scale anywhere. The ends and
  noon are exact. That is why the pots are 10 k and not 100 k (100 k would
  read 16 % low at three quarters).
- Channel 1 has no CAS input, and OUT 4 has no D stage after it.
- **Headroom.** C swings about ±10.5 V on ±12 V. A full input plus a full
  offset clips; that is expected.

### Op-amp sections

| Chip | A | B | C | D |
|---|---|---|---|---|
| U1 | N_1 | P_1 | channel 1 summer | cascade 1 → 2 |
| U2 | N_2 | P_2 | channel 2 summer | cascade 2 → 3 |
| U3 | N_3 | P_3 | channel 3 summer | cascade 3 → 4 |
| U4 | N_4 | P_4 | channel 4 summer | NORM: follower for +1 V (39k / 10k from +5 V) |

### References and power

- **+5 V:** LM4040-5.0 (TO-92), cathode on the +5 V node, fed by 1k from
  +12 V. That gives 7 mA; the four OFFSET pots take 4 mA, which leaves 3 mA
  for the reference (its range is 0.06–15 mA).
- **−5 V:** a second LM4040-5.0, with its cathode on GND, fed by 1k to −12 V.
- **Power entry:** 16-pin Eurorack header (2.54 mm, shrouded). There is a
  1N5819 in each rail: the +12 V anode on the header, and the −12 V
  *cathode* on the header (the reversed −12 V diode on the older PCBs is the
  error to avoid). Each rail then has a 10 Ω and 10 µF, and each TL074 has a
  100 n pair at its supply pins.
- **Current, estimated:** TL074s about 22 mA per rail, references 7 mA each,
  LEDs up to 4 × 3.6 mA, ATTEN pots up to 2 mA each at full input. That
  comes to about 50 mA per rail at worst, 30 mA typical.

---

## Panel

12HP, in the house style. The channels are columns like the mixer's
strips, 13.3 mm apart (the mixer's are 13.5 mm). Each row's word stands
once in the left margin, on a bracket. The knobs are at the top and the jacks
at the bottom, so cables hang away from the hands. The outputs and their
LEDs sit on the gold band. Dotted lines between the inputs show the
fan-out; a + between the outputs shows the mix.

![panel](../hardware/panel/offset-panel-preview.png)

| Row | Panel y (mm) | Parts |
|---|---|---|
| Channel numbers | 16.0 | silk |
| ATTEN | 27.0 | RV1, RV3, RV5, RV7: Alpha 9 mm B10k |
| OFFSET | 48.5 | RV2, RV4, RV6, RV8: Alpha 9 mm B10k |
| IN | 76.5 | J1–J4: Thonkiconn |
| LEDs | 91.0 | D1–D4: 3 mm bicolour, 2 leads |
| OUT | 102.5 | J5–J8: Thonkiconn |

Channel x: 11.5, 24.8, 38.1, 51.4. `panel.py` reports 0.1 mm between
neighbouring knob scales. That figure includes its 0.6 mm safety margin;
the drawn arcs are 1.3 mm apart and the knob caps 3.3 mm. That is the
mixer's density, which has proved playable.

---

## Parts (estimate)

| Qty | Part | Where | Notes |
|---|---|---|---|
| 8 | Thonkiconn PJ398SM | Thonk | |
| 8 | Alpha 9 mm vertical B10k | Thonk | A centre-detent version would help find noon on both rows; check stock |
| 4 | 3 mm bicolour LED red/green, 2 leads | Tayda | Thonk if stocked |
| 4 | TL074 + DIP-14 sockets | Tayda | Use the 7.62 mm DIP footprint, not the library's 8.89 mm one |
| 2 | LM4040 5.0 V, TO-92 | Mouser | A or B grade (0.1 / 0.2 %) |
| 37 | 100k 1 % | | |
| 4 + 4 | 1k, 2k2 | | output series, LED |
| 2 + 1 + 1 | 1k, 39k, 10k | | reference feeds, +1 V divider |
| 2 | 10 Ω | | rail filters |
| 4 | 22 p C0G | | summer feedback |
| 10 | 100 n | | 8 decoupling, 2 at the references |
| 2 | 10 µ electrolytic | | rail bulk |
| 2 | 1N5819 | | reverse protection |
| 1 | 16-pin shrouded Eurorack header, 2.54 mm | Thonk | Not the 2.00 mm footprint the FM / Clap / Compressor boards got |

---

## Open choices

1. **Width and channel count.** In 12HP, four channels fit at the mixer's
   knob spacing. The 10HP in the voice-case list only fits three channels at
   that spacing, or four with 9 mm knobs at 11 mm pitch, which are
   hard to turn live.
2. **IN 1 normal.** +1 V (fine offset, as drawn), +5 V (ATTEN becomes a
   second coarse offset), or 0 V (unpatched channels are pure offsets). It
   is one resistor change.
3. **OFFSET range.** ±5 V as drawn, or ±10 V (50 k from the OFFSET
   wipers into the summer), which halves the knob's resolution.
4. **The free strip** between OFFSET and IN (about 20 mm). Leave it empty,
   or add a per-channel sub-mini toggle there: for example ATTEN ×1 / ×2
   (gain for small envelopes), or OFFSET ±5 V / ±1 V.
5. **One board or two.** The circuit is small (4 DIP-14, about 50
   resistors), so one PCB can carry the panel parts on its front and
   everything else behind them. That is cheaper and has no board-to-board
   headers. The two-board stack of the other modules also works, if you want
   it to match them.
