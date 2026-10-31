# Envy — design notes

Four Moritz Klein envelopes in 16HP Eurorack, all analog. Each channel is the
MKI x ES.EDU EG (`EG_MANUAL_v3.pdf` in the Manuals folder): a pseudo-ADSR with
attack, a shared decay/release, sustain, a LOOP mode, an output and an
inverted output, and an LED. The gates normal down the column, so one gate
can fire all four. Reference designators match `hardware/tools/circuit.py`.

Status (2026-10-31):

- **Panel:** agreed, with the drawn defaults: 16HP, four channels, a 2.55 V
  threshold, unfitted footprints for a second timing cap, the name Envy.
- **Netlist:** written for one board, 167 parts, 0 problems.
- **Simulation:** `sim.py` runs the netlist in time; all 28 checks pass. The
  numbers below come from it.
- **Next:** the EasyEDA schematic, then the placement. The placement decides
  whether one board holds it (see [Board](#board)).

---

## What it does

Per channel k:

| Control | Range | Notes |
|---|---|---|
| GATE k | trips at 2.55 V | Unpatched, GATE k takes GATE k−1; GATE 1 sits at 0 V |
| ATTACK k | fastest 0.4 ms (10–90 %), slowest a 1 s time constant | A1M, clockwise = slower. Past about 9 o'clock it rises towards the sustain level, not the peak (below) |
| DEC/REL k | fastest 0.25 ms, slowest a 1 s time constant | One knob for decay *and* release, as on the kit |
| SUSTAIN k | 0 … peak | A100k. At full, the decay disappears |
| MODE k | LOOP (up) / SINGLE (down) | LOOP ignores the gate |
| OUT k | 0 … about 10 V | 1 kΩ series. The peak is 9.9 V with SUSTAIN at 0 and 10.1 V with it full |
| INV k | 9.7 V … about −0.2 V | Mirrors OUT: rests high and dips during the envelope |
| LED k | brightness follows OUT | Starts glowing at about 2.5 V |

### How the kit's envelope works

The gate drives two comparators.

- **Gate comparator.** Its output, through a diode, is 0 V or 9.9 V for as
  long as the gate is high. SUSTAIN divides it down; that level feeds the
  input buffer through 100k.
- **Burst comparator.** It sees a high-passed copy of the gate, so it
  outputs a full burst of 13.7 ms on each rising edge. The burst reaches
  the buffer through a diode alone, so it wins over the sustain level.

The buffer charges the 1 µF timing cap through ATTACK, and the cap
discharges through DEC/REL. Each pot has its own steering diode. So:

1. The burst pulls the cap towards the peak (attack).
2. When the burst ends, the cap falls back to the sustain level through
   DEC/REL (decay).
3. When the gate ends, it falls to 0 V through DEC/REL (release).

A second buffer copies the cap to OUT. The kit's two caveats stay, because
they are what makes the circuit this small:

- **Decay and release share one knob.**
- **Slow attacks rise towards SUSTAIN, not the peak.** Past the 13.7 ms
  burst, the cap only climbs to the sustain level. With SUSTAIN at 0,
  ATTACK at 9 o'clock reaches just 3.4 V, and at noon 0.9 V. For a slow
  swell, turn SUSTAIN up: SUSTAIN sets the height and ATTACK the time.

**LOOP** switches the buffer's input from the gate side to a Schmitt
trigger that watches OUT. The trigger drives the buffer high until OUT
passes 7.5 V, then low until OUT falls below 0.5 V, then high again. The
result is an attack/release LFO between 0.5 and 7.5 V.

- With both knobs fully clockwise, a cycle takes 4.0 s.
- With both fully counter-clockwise, it runs at about 1.2 kHz.
- SUSTAIN and the gate do nothing in LOOP.

---

## Circuit

Per channel; all 1 % metal film, 100k unless marked.

```
GATE k tip ──10k──┬── GIN_k ─[+ gate comp]─ 1N4148 ─► G_k ──┬── 10k ── GND
 (lug: GATE k-1)  ├─100k─ GND        VREF ─[-]              ├── SUSTAIN A100k ─ GND
                  └─1N4148 to GND (clamps negative)         │     wiper ─ 100k ─► N_k
                                                             └── 1µ ── HP_k ─┬─ 10k ─ GND
                                                                            └─ 1N4148 to GND
HP_k ─[+ burst comp]─ 1N4148 ─► N_k        VREF ─[-]

MODE k (SPDT): SINGLE = N_k, LOOP = L_k ──► [+ input buffer] ── 100R ─┬─ BAT85 ─► ATTACK A1M ─┐
                                                                      └─ BAT85 ◄─ DEC/REL A1M ─┼─ C_T 1µ ─ GND
                                                                                               │
                         ENV_k ◄─ [output buffer +] ◄──────────────────────────────────────────┘
ENV_k ── 1k ── OUT k
ENV_k ── 100k ─[- inverter]─ 1k ── INV k          AXIS ─[+], 100k feedback
ENV_k ── BC548 base; collector +12 V; emitter ── 1k5 ── red LED ── GND
ENV_k ─[- loop Schmitt]─ 1N4148 ─► L_k ── 100k ── GND
        [+] = 100k to +12 V, 100k to GND, 100k from its output
```

Shared by all channels:

- **VREF** is 100k / 27k from +12 V, which gives 2.55 V, with 100 n. It
  feeds the − input of all eight comparators.
- **AXIS** is 100k / 68k from +12 V, which gives 4.86 V, with 1 µ. It feeds
  the + input of all four inverters, so INV = 9.71 V − ENV.

### Changes from the kit, and why

The kit figures in this table come from `sim.py` too, run with the kit's
values swapped in.

| # | Kit | Here | Why |
|---|---|---|---|
| 1 | One channel | GATE k normalled from GATE k−1 | One gate fires all four, each with its own shape (VCA, filter, pitch, FX send) |
| 2 | The high-pass takes the gate jack | The high-pass takes G_k, the gate comparator's output | The burst is 13.7 ms for both 5 V and 10 V gates. The kit gives 9.7 ms with a 10 V gate and 2.7 ms with a 5 V one. The source also sees one 110k per input instead of four 1 µF / 10k high-passes on its edges |
| 3 | Jack straight to the comparators | 10k series, 100k pull-down, clamp diode | A −10 V LFO into GATE holds the input at −0.58 V, inside the TL074's range, so there is no phase reversal and no false trigger. A dangling cable reads 0 V |
| 4 | Threshold 3.8 V (100k / 47k) | 2.55 V (100k / 27k) | A 5 V gate through a 1 kΩ output into all four normalled inputs still arrives at 4.82 V, with a wide margin. It stays far above noise |
| 5 | 1N4148 steering diodes | BAT85 Schottky | The kit's release leaves a tail: 0.21 V half a second after the gate and still 0.11 V after 2 s, which a linear VCA lets through as bleed. BAT85: 0.03 V after half a second |
| 6 | Inverter axis 6 V | 4.86 V | Kit: INV = 12 V − ENV, so it rests clipped at the op-amp's ~10.5 V and only reaches about 2.5 V. Here it mirrors OUT, 9.7 V at rest and −0.2 V at the peak, with 0.8 V of headroom below the op-amp's swing |
| 7 | 470 Ω LED resistor | 1k5 | About 5 mA at the peak instead of 16 mA, times four, on +12 V |
| 8 | 3 × TL072 per channel | 6 × TL074 for all four | Fewer sockets; comparators on their own chips (below) |

Everything else is the kit's values.

### Op-amp sections

Comparators sit on their own chips (U1, U4), away from the buffers and the
timing caps. Their 20 V edges are the module's only fast signals; the FM
drum's noise came from square waves running beside an op-amp.

| Chip | A | B | C | D |
|---|---|---|---|---|
| U1 | gate comp 1 | burst comp 1 | burst comp 2 | gate comp 2 |
| U2 | input buffer 1 | output buffer 1 | output buffer 2 | input buffer 2 |
| U3 | loop Schmitt 1 | inverter 1 | inverter 2 | loop Schmitt 2 |
| U4–U6 | the same for channels 3 and 4 | | | |

### Power

- **Header:** 2 × 5, 2.54 mm, shrouded. No +5 V is needed.
- **Reverse protection:** a 1N5819 in each rail. On +12 V the anode goes to
  the header; on −12 V the *cathode* goes to the header (the reversed −12 V
  diode on the older PCBs is the error to avoid).
- **Filtering:** 10 Ω and 47 µF per rail, and a 100 n pair beside every TL074.
- **Current, estimated:**
  - +12 V: about 45 mA typical and 80 mA at worst. The TL074s draw about
    34 mA (60 mA at their datasheet maximum), four LEDs at full add 19 mA,
    and each gate comparator sourcing G_k adds 1 mA.
  - −12 V: about 35 mA typical and 60 mA at worst.

### Times

- **Single mode:** C_T is 1 µF and the pots go to 1 MΩ, so each time
  constant runs to about 1 s.
  - With everything clockwise, the attack reaches 95 % in 3.0 s, and the
    release falls to 0.1 V in 4.3 s.
- **Fast settings:** the fastest edges take 0.25–0.4 ms, so a filter does
  not click. The 100 Ω after the buffer and the TL074's output current limit
  (about 25 mA into 1 µF) set them.
- **Longer times:** each channel has a second 1 µF footprint beside C_T
  (C*k*03, the kit's C11), unfitted. Fit it to double that channel's times,
  for pads and slow swells; channels 3 and 4 are the natural pair.

---

## Netlist

`hardware/tools/circuit.py`. `python circuit.py` prints the part counts and
the netlist problems: single-pin nets, designators used twice, TL074 pins
left out, and two op-amp outputs on one net.

| Designators | What |
|---|---|
| J1–J4, J5–J8, J9–J12 | GATE 1–4, OUT 1–4, INV 1–4 (Thonkiconn: 1 sleeve, 2 switch lug, 3 tip) |
| RV1, RV4, RV7, RV10 / RV2, RV5, RV8, RV11 | ATTACK / DEC/REL: rheostats between pin 1 and the wiper, the wiper tied to pin 3 (clockwise is slower; a lifted wiper leaves 1M, not an open circuit) |
| RV3, RV6, RV9, RV12 | SUSTAIN: pin 3 on G_k, pin 1 on GND, the wiper into 100k |
| SW1–SW4 | MODE: Dailywell 2MS1, pin 3 at the bottom; lever up joins 2–3 (LOOP: L_k), down joins 2–1 (SINGLE: N_k) |
| D1–D4, Q1–Q4 | LEDs and their BC548 emitter followers (TO-92: 1 C, 2 B, 3 E) |
| U1–U6 | TL074s, as in the op-amp table |
| R*k*01–R*k*15, C*k*01–C*k*03, D*k*01–D*k*07 | channel *k*'s resistors, caps and diodes (R101 … R415). C*k*03 is the unfitted second timing cap |
| R901–R904, C901, C902 | VREF and AXIS |
| J13, D901, D902, R905, R906, C903–C916 | power entry, bulk and decoupling |

Net names say what they carry:

- **Gate side:** `GATE1` (tip), `GIN1` (comparator input), `GC1` / `G1`
  (gate comparator out, before and after its diode), `SUS1` (sustain
  wiper), `HP1` (the burst high-pass), `BC1` (burst comparator out).
- **Buffer and timing:** `N1` (the buffer node in SINGLE), `L1` (the loop
  drive), `BI1` (the toggle's common, the buffer input), `BUF1` / `BO1`
  (buffer out, before and after the 100 Ω), `AK1` / `RK1` (between a
  steering diode and its pot), `CT1` (the timing cap).
- **Outputs:** `ENV1`, `OUT1`, `IV1` / `INVO1` / `INV1` (inverter in, out,
  tip), `QE1` / `LE1` (LED driver).
- **Loop:** `SP1` / `SC1` (Schmitt + input and output).
- **Shared:** `VREF`, `AXIS`.

---

## Simulation

`hardware/tools/sim.py` runs the netlist in time. It is a small transient
solver:

- **Analysis:** nodal analysis with backward-Euler capacitors.
- **Diodes:** Shockley models. 1N4148 uses its usual SPICE values. BAT85
  is fitted to the datasheet's 0.24 V at 0.1 mA and 0.32 V at 1 mA.
- **Op-amps:** a TL074 section with its own output on its − input is an
  ideal follower or inverter, clipped at ±10.5 V and current-limited at
  25 mA. Every other section is a comparator. Comparator decisions are
  re-checked until each step is self-consistent, so the Schmitt trigger's
  hysteresis comes out of its own feedback.
- **Pots:** Alpha's A taper (15 % at half travel).
- **Patching:** gates come from a 1 kΩ source; OUT and INV drive 100k loads.
- **Left out:** the LED drivers and the power entry.

`python sim.py` runs 28 checks against the numbers in this file; all pass
in about 15 s.

| Case | Result |
|---|---|
| Burst, 10 V and 5 V gate | 13.7 ms both (kit: 9.7 and 2.7 ms) |
| Peak, SUSTAIN at 0 / full | 9.9 / 10.1 V |
| INV at rest / at the peak | 9.62 V (into 100k) / −0.19 V |
| Sustain level, knob at 0.8 | 4.82 V (the A taper of 9.9 V) |
| Fastest attack, 10–90 % | 0.4 ms |
| ATTACK at 9 o'clock, SUSTAIN 0 | peaks at 3.4 V |
| Tail after the gate, BAT85 / 1N4148 | 0.03 / 0.21 V at 0.5 s; 0.00 / 0.11 V at 2 s |
| Everything clockwise | 95 % in 3.0 s, release to 0.1 V in 4.3 s |
| LOOP, slowest / fastest | 4.0 s period between 0.5 and 7.5 V / 1.2 kHz |
| −10 V into GATE | GIN held at −0.58 V, no comparator moves |
| 5 V gate into GATE 1, the rest normalled | 4.82 V on GATE 4; all four peaks equal |

---

## Board

One board: Thonk panel parts on its front, everything else on its rear,
as on Offset ("one board is always simpler and cheaper if possible").

- **Count:** 131 fitted parts and 4 unfitted footprints sit behind the
  panel, on 79.7 × 108 mm (8,600 mm²). That is about 65 mm² per part,
  the same density as Offset's board.
- **Area:** the rear footprints themselves (courtyards, horizontal
  resistors) come to about 5,600 mm², or 65 %. That is dense for a hand
  route, but it fits. Standing some resistors up, as the kit does, frees
  more.
- **If it doesn't fit:** if the placement shows it cannot be routed on
  one board, the split is a faceplate board (panel parts, LED drivers,
  output and inverter stages) and a main board. The netlist stays the
  same apart from the header nets.

---

## Panel

16HP, in the house style: Offset's columns, frame and bracket labels.

- The channels are columns 18 mm apart, with their numbers on top.
- Knobs are at the top and jacks at the bottom, so cables hang away from
  the hands.
- Each row's word stands once in the left margin, on a bracket.
- The MODE toggles carry LOOP / SINGLE beside the lever.
- Dotted lines between the GATE jacks show the normal.
- The outputs (LED, OUT, INV) sit on the gold band.

![panel](../hardware/panel/envy-panel-preview.png)

| Row | Panel y (mm) | Parts |
|---|---|---|
| Channel numbers | 16.0 | silk |
| ATTACK | 25.5 | RV1, RV4, RV7, RV10: Alpha 9 mm A1M |
| DEC/REL | 41.0 | RV2, RV5, RV8, RV11: Alpha 9 mm A1M |
| SUSTAIN | 56.5 | RV3, RV6, RV9, RV12: Alpha 9 mm A100k |
| MODE | 70.0 | SW1–SW4: sub-mini SPDT ON-ON, 2.5 mm left of the column |
| GATE | 81.5 | J1–J4: Thonkiconn |
| LEDs | 90.5 | D1–D4: 3 mm red |
| OUT | 100.5 | J5–J8: Thonkiconn |
| INV | 111.5 | J9–J12: Thonkiconn |

- **Columns:** channel x is 14, 32, 50 and 68 mm.
- **Clearances:** `panel.py` reports no gap under 1 mm (knob scales with a
  0.6 mm margin, nuts, and the toggle levers thrown both ways). The
  tightest gap is 1.02 mm, between a lever thrown up and the SUSTAIN
  scale above it.
- **Spacing against Offset:** the knob rows are 15.5 mm apart, against
  Offset's 21.5 mm. The knobs are the same 10 mm, so 5.5 mm of panel lies
  between caps.

---

## Lessons from the earlier boards

| Lesson | From | Here |
|---|---|---|
| 2.54 mm power header | Compressor, FM, Clap, CB/RM had 2.00 mm | 2 × 5 2.54 mm shrouded |
| −12 V protection diode the right way round | every module PCB so far | D902's cathode on the header pin |
| DIP-14 rows 7.62 mm apart | Kick, Mixer, Output (8.89 mm, legs bent) | `fp_dip(14, "DIP-14-W7.62-P2.54")` |
| Alpha pot shaft 4.0 mm from the PTV09A origin | Marblesy, Plaitsy | `POT_SHAFT = 4.0` in `circuit.py` |
| Decoupling next to each chip | Marblesy routing | a 100 n pair per TL074, placed before routing |
| One unbroken ground pour | Compressor's six islands | checked in the copper audit |
| Fast edges away from quiet nodes | FM drum noise | comparators on U1 / U4; timing caps and buffers on U2 / U5 |

---

## Parts

From the netlist.

| Qty | Part | Notes |
|---|---|---|
| 12 | Thonkiconn PJ398SM | GATE, OUT, INV |
| 8 | Alpha 9 mm A1M | ATTACK, DEC/REL. Check Thonk has A1M before ordering |
| 4 | Alpha 9 mm A100k | SUSTAIN |
| 4 | Dailywell 2MS1 sub-mini toggle, SPDT ON-ON, PCB pins | the kit's part is 2MS1T1B5M2RE |
| 4 | 3 mm red LED | |
| 4 | BC548 | LED drivers |
| 6 | TL074 + DIP-14 sockets | |
| 20 | 1N4148 | five per channel |
| 8 | BAT85 | steering, two per channel |
| 2 | 1N5819 | power |
| 8 | 1 µF film, 5.08 mm | C_T and the high-pass, two per channel; +4 for the C*k*03 footprints if fitted |
| 1 | 1 µF ceramic | AXIS |
| 13 | 100 n ceramic | a pair per TL074, VREF |
| 2 | 47 µF 25 V | bulk |
| 66 | resistors | 100k ×34, 10k ×12, 1k ×8, 1k5 ×4, 100 Ω ×4, 27k, 68k, 10 Ω ×2 |
| 1 | 2 × 5 shrouded header, 2.54 mm | |
