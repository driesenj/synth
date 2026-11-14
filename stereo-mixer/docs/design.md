# Stereo mixer (PCB) — design notes

The voice case's stereo master, Eurorack 28HP, on two stacked PCBs behind a
PCB panel, built the way Marblesy and Plaitsy are: Thonk panel parts, every
main-board resistor standing up and clustered on its op-amp, the panel as
the project's third board. Every designator matches
`hardware/tools/circuit.py`, which generates the EasyEDA Pro project
(`hardware/easyeda/StereoMixer.epro2`) and the panel files.

Status: schematic done and checked (6 pages, 0 problems), footprints
assigned, both PCBs placed and net-assigned, header pin orders picked for
the fewest crossing lines, the panel as the third board. Both boards are
routed and audited (`StereoMixer-routed.epro2`, third export 2026-11-02,
patched 2026-11-04 for the LED resistors, value labels and a −12V mark);
nothing built yet.

What changed from the 2026-10-07 design: the mutes are Thonk LED buttons
with a latch instead of toggles (a lit button = muted, every channel starts
unmuted), MASTER is a dual A100k like the other dual pots, and everything
sits on two PCBs with Thonk parts. The audio path, gains and pan law are
the same.

---

## Architecture

```
 panel ─┬─ faceplate board (FB)  17 Thonkiconn jacks, 21 Alpha 9 mm pots, 4 Alpha 9 mm dual-gang pots,
        │   140.4 x 108 mm        8 Thonk LED buttons; nothing else
        │      76 pins in 9 headers (male on the FB, female on the MB)
        └─ main board (MB)       4 TL074 (10 followers, 3 summers, 3 output stages), 10 AQY212EH
            140.4 x 108 mm        PhotoMOS mutes, the latch (2 CD4093, 4 CD4013), power entry
```

The two boards stack like Marblesy's: jacks, pots and buttons on the FB's
bottom side towards the panel, the FB's headers on its top side mating with
sockets on the MB's bottom side, everything else on the MB's top (rear)
side. Every header has the same x/y on both boards.

---

## Signal flow

```
mono ch k (1-6)
  IN k ─ LEVEL k (A100k) ─ 10k ─┬─ follower ─ CHk ─┬─ 10k ─ PLk ─ 100k ─▶ SUM_L    PAN k (B10k) between
                                └─ PhotoMOS ─ GND  ├─ 10k ─ PRk ─ 100k ─▶ SUM_R    PLk and PRk, wiper to GND
                                   (= MUTE)        └─ SEND k (A100k) ─ 100k ─▶ SUM_S
stereo ch c (7, 8)
  IN c L ─┐ LEVEL c       10k + PhotoMOS   followers ┬─ 200k ─▶ SUM_L / SUM_R
  IN c R ─┘ (dual A100k)  per side                   └─ 10k + 10k = (L+R)/2 ─ SEND c ─ 100k ─▶ SUM_S
RETURN L/R ─ RETURN (dual A100k) ─ 200k ─▶ SUM_L / SUM_R
DRUMS ─ DRUMS (A100k) ─ 300k ─▶ SUM_L,  300k ─▶ SUM_R
FX IN ─ 100k ─▶ SUM_S

SUM_L ─ summer (100k ∥ 22p) ─ MIX_L ─ MASTER gang A (A100k) ─ MST_L ─ 100k ─ inverter ×2 (200k) ─ 1k ─ OUT L
SUM_R ─ summer (100k ∥ 22p) ─ MIX_R ─ MASTER gang B         ─ MST_R ─ 100k ─ inverter ×2 (200k) ─ 1k ─ OUT R
SUM_S ─ summer (100k ∥ 22p) ─ MIX_S ─ 100k ─ inverter ×1 (100k) ─ 1k ─ SEND
```

Every path inverts twice, so every output is in phase with every input:
Clouds' wet signal comes back in phase with the dry channel.

## Main board circuits

### Channel inputs and mutes

- **LEVEL** (A100k, faceplate) is a divider from the jack to GND; the input
  impedance is 100k. Its wiper (LVk) comes down a header to a 10k series
  resistor into the follower's + input (FIk).
- **Mute:** an AQY212EH PhotoMOS from FIk to GND. On, it shorts FIk
  (0.85 Ω typical, 2.5 Ω max) behind 10k plus the wiper's own resistance:
  the channel drops by 82 dB typically, 72 dB at worst. Off, it is not
  quite an open switch: its output capacitance (79 pF at 0 V, 35 pF at
  7.5 V) sits on the high-impedance FI node behind 10k plus the wiper's
  resistance, up to 31k at about ¾ of LEVEL's travel. That costs up to
  0.6 dB at 20 kHz, and because the capacitance changes with the voltage it
  adds 0.05–0.18 % THD at 1 kHz and 0.3–1.7 % at 10 kHz to a 10 V p-p
  signal at those LEVEL settings. It falls fast with frequency and level:
  0.005–0.017 % at 100 Hz, 0.004–0.021 % for 2 V p-p at 1 kHz. No DIP-4
  PhotoMOS does better (test report M1): the low-capacitance ones are
  18–50 Ω parts that would cut the mute to about 50 dB. A respin with the
  shunt at a low-impedance node would cure it.
- **Loading:** muted, the 10k loads the LEVEL wiper. At full LEVEL a mono
  input falls from 100k to 9.1k (a stereo L input with R normalled to
  4.5k), so a source multed elsewhere drops by 0.4–1.5 dB while the channel
  is muted; at LEVEL noon or below the change is negligible.
- **Input impedance:** 100k on every channel input and on FX IN; a
  stereo L input with its R unpatched 50k; RETURN R 100k at RETURN off
  down to 67k at full, RETURN L with R normalled 50k down to 33k; DRUM IN
  60–100k.
- **Input range:** the followers' + inputs see the jack's voltage at full
  LEVEL. Below about −8.5 V (−7.1 V worst case) a TL074 leaves its
  common-mode range and can flip phase; Eurorack audio at ±5 V is far
  inside, and only a hot ±10 V source at nearly full LEVEL reaches it.
- **Follower** (TL074 section) drives CHk: the SEND pot's top (through the
  header), the two 10k pan feeds, or on the stereo channels the 200k bus
  resistor and the 10k send average.
- **Pan** (B10k, faceplate): CHk → 10k → PLk and PRk, the pot between them
  with its wiper to GND, each end → 100k into its bus. CW end on PL: fully
  CW grounds the left side, so the knob reads left to right.
- **Send** is post-fader and post-mute: the SEND pot hangs off CHk.

### Mute latch

Per channel: the button's 3+4 contacts pull BTNk to GND_F against a 100k
pull-up to +12 V; 10k / 100n debounce (1 ms on press, 11 ms on release)
into a CD4093 NAND with both inputs tied, i.e. a Schmitt inverter, so the
clock edge is clean and comes on press. The CD4013 half toggles (D = /Q).
Q high = muted: Q → 1k (820 Ω on a stereo channel) → the PhotoMOS LED
(two in series on a stereo channel) → header → the button's LED → GND_F,
about 6.8 mA typical on either kind with a red button LED, inside
Panasonic's recommended 5–10 mA. With a weak CD4013B output on a low rail
and high LED voltages it is still about 4 mA (3.9 mA on a stereo channel),
above the 3 mA the AQY212EH needs at most. Every flip-flop's RESET comes from one power-on RC
(1 µF from +12 V, 100k to GND): about 70 ms of reset at power-up
(R × C × ln 2; 35–125 ms over the CD4013B's thresholds), longer than the
debounce caps take to settle for any rail ramp from 1 to 200 ms, so the
mixer always starts with every channel open.

D903, a BAT85 beside R920 (cathode on POR, anode on GND), empties C906 at
power-off: the falling +12 V drags POR below GND through C906, and D903
holds it at about −0.3 to −0.4 V, inside the CD4013B's −0.5 V limit, so the
RESET inputs' own protection diodes carry next to nothing (up to about
15 mA flows through D903 when the rail collapses fast, against its 200 mA).
The next power-up resets as it should. Until 2026-11-14 D903 was a 1N4148
across C906 with its cathode on +12 V: it never conducted, and the RESET
inputs' diodes did the job at about −0.6 V. Each debounce cap still empties
into VDD through its CD4093B inputs' diodes (DB about 0.6 V above VDD,
0.13 mA), well inside their 10 mA rating.

A rail dip to between 3 and 7 V (an overloaded bus) can leave channels
randomly muted or unmuted; dips that stay above 8 V keep every mute, and a
full power cycle opens them all.

| Channel | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| CD4093 gate | U5.1 | U5.2 | U5.3 | U5.4 | U6.1 | U6.2 | U6.3 | U6.4 |
| CD4013 half | U7.1 | U7.2 | U8.1 | U8.2 | U9.1 | U9.2 | U10.1 | U10.2 |
| PhotoMOS | K1 | K2 | K3 | K4 | K5 | K6 | K7 (L), K8 (R) | K9 (L), K10 (R) |
| Pull-up, debounce, LED resistor, debounce cap | R107–R109, C101 | R207–R209, C201 | R307–R309, C301 | R407–R409, C401 | R507–R509, C501 | R607–R609, C601 | R708–R710, C701 | R808–R810, C801 |

The switching is fast (about 1 ms on, 0.1 ms off), so muting a loud
signal can click, as with the toggles before. If it bothers you: a 22 µF
across the PhotoMOS LED and button LED chain, the 1k (820 Ω on a stereo
channel) already in series, turns the PhotoMOS on over about 20 ms, which
mutes more softly.

### Buses, master and outputs

- **Summers:** inverting, 100k feedback with 22 pF across it (a pole at
  72 kHz, for stability with ten inputs on the node).
- **MASTER:** dual A100k on the faceplate between the summer outputs
  (MIX_L / MIX_R) and the output stages' inputs (MST_L / MST_R). At full it
  passes the summers straight through; below that the wiper's source
  resistance adds a little to the output stage's 100k input, which only
  bends the taper slightly and is the same on both sides.
- **Output stages:** inverting, gain 2 (100k in, 200k feedback), 1k to the
  jack. The ×2 makes up the half gain in front of the summers (200k and
  300k inputs, the pan network's loss), so the summers keep 6 dB more
  headroom than the outputs.
- **Send output:** the send summer, a unity inverter (100k / 100k) and 1k.
  No level knob: Clouds' IN GAIN does that.
- **Phase margin:** the few pF on each output stage's inverting input,
  with Rin ∥ Rf behind them (67–77k on the output stages, 50k on the send
  inverter), put a pole inside the loop. C907 / C908 (4.7 pF C0G across
  R905 / R908) and C909 (10 pF across R911) cancel it (Cf Rf ≥ C Rin):
  the worst case the suite finds (TL074 GBW 3 MHz, the PhotoMOS off
  capacitance at its 20 V value) is now 66° on the send inverter and 72° on
  OUT L / R. Without them (until 2026-11-14) these stages had about
  18°, with peaking near 1 MHz. The caps are KEMET C315 parts with 2.54 mm
  leads; they cost under 0.1 dB at 20 kHz.

### Gains (unchanged)

| Source, at full LEVEL | Gain to OUT, MASTER at full |
|---|---|
| Mono, hard panned | 0.95 on that side (−0.4 dB) |
| Mono, centred | 0.65 per side (−3.8 dB) |
| Stereo channel | 1.0 per side |
| RETURN | 1.0 per side |
| DRUMS | 0.67 per side (−3.5 dB) |
| Any SEND (mono, stereo (L+R)/2, FX IN) to SEND OUT | 1.0 (stereo 0.91) |

Pan law, B10k from fully CCW: L −0.4 / −1.7 / −3.8 / −8.1 dB / off at 0,
¼, ½, ¾, 1; L² + R² stays within 0.4 dB. The TL074s swing about ±10 V on
the 11.0–11.5 V the chips get after the 1N5819s and 10 Ω (9.5 V on the
+ side with every channel muted; ±7 V guaranteed in the worst case at a
12 V bus, about ±6.8 V at 11.4 V), so
the outputs clip at about twice Eurorack level and the L / R summers at
about four times. The send summer
clips with the SEND output, at about twice. Set the output module's IN at
noon or below (its input stages have a gain of 2).

DC offset: everything is DC-coupled, so the TL074s' input offsets add up
at the outputs: about 53 mV typical at OUT L / R, 280 mV at worst at
25 °C and about 365 mV over 0–70 °C (SEND 31 mV typical, 200 / 260 mV),
and MASTER moves it as it turns. A TL074B (3 mV max) in U4,
which carries most of the offset gain, halves the worst case.

### Op-amps

| | Section 1 (1/2/3) | Section 2 (7/6/5) | Section 3 (8/9/10) | Section 4 (14/13/12) |
|---|---|---|---|---|
| U1 | follower 2 | follower 1 | follower 4 | follower 3 |
| U2 | follower 6 | follower 5 | follower 7 R | follower 7 L |
| U3 | follower 8 L | follower 8 R | SEND output | send summer |
| U4 | L summer | R summer | OUT R stage | OUT L stage |

Picked by where each chip sits on the main board (see placement).

### Power

- **J18:** 16-pin 2.54 mm box header (your C3406 footprint), pins 1–2
  −12 V (red stripe), 3–8 GND, 9–10 +12 V; 11–16 (+5 V, CV, Gate) unused.
  That is the Doepfer A-100 bus (doepfer.de a100t_e.htm, image
  a100b_e.gif). Until 2026-11-14 the design had GND on 3–10 and +12 V on
  11–12, which shorts the bus +12 V to GND; the routed master was
  re-netted and re-routed at J18 that day.
- **Reverse protection:** series 1N5819 per rail (−12 V: cathode on the
  header), then 10 Ω, 10 µF per rail.
- **Missing +12 V:** if the bus has −12 V but no +12 V, the op-amps' 20–40 mA
  pulls the +12 V net below GND. D904, a BAT85 from GND (anode) to +12 V
  (cathode), clamps it at about −0.4 V typically (22 mA), inside the
  CD4000B's −0.5 V limit for the CMOS chips' VDD. At the worst case (40 mA,
  the BAT85's maximum VF) it is about −0.55 V, a little past the limit
  but better than the −0.6 V the chips' substrate diodes held without it. A
  1N5819 in D904's place would hold about −0.34 V even then (2026-11-14).
- **J18 pads:** 1.7 mm round on the 1.1 mm holes, a 0.30 mm annular ring
  (the library footprint's 1.524 mm pads gave 0.212 mm; 2026-11-14).
- **Decoupling:** 100 n per TL074 per rail beside pins 4 and 11; 100 n per
  CMOS chip beside its pin 14.
- **Current:** about 25 mA on −12 V; on +12 V about 25 mA plus 6–7 mA per
  muted channel, 75 mA with all eight muted. At most, with the TL074s at
  their maximum supply current and full-swing loads: about 125 mA on +12 V
  (all muted) and 60 mA on −12 V. Budget the case's supply for those.

---

## Board-to-board headers

Pin 1 at the top (front view). Orders picked by brute force for the fewest
crossing straight lines between each pin and the nearest pad of its net on
both boards, length as the tie-break, GND pins left in place: 90 crossings
→ 59 over the nine headers.

| Header | Pins 1 → 8 (12) |
|---|---|
| H1 | PR1, CH1, PL1, LV1, LED1, GND, SD1, BTN1 |
| H2 | CH2, PR2, PL2, LV2, SD2, GND, LED2, BTN2 |
| H3 | CH3, PR3, PL3, LV3, LED3, GND, SD3, BTN3 |
| H4 | SD4, PR4, CH4, PL4, LV4, GND, LED4, BTN4 |
| H5 | PR5, CH5, PL5, LV5, SD5, GND, LED5, BTN5 |
| H6 | CH6, SD6, PR6, PL6, LV6, GND, LED6, BTN6 |
| H7 | SD7, AV7, GND, LV7L, LV7R, GND, LED7, BTN7 |
| H8 | SD8, AV8, GND, LV8L, LV8R, GND, LED8, BTN8 |
| H9 | SEND, RW_R, RW_L, GND, DRW, FXI, MIX_R, MIX_L, MST_L, MST_R, OUT_R, OUT_L |

The faceplate side of each net has `_F` added (GND → GND_F). Eleven GND pins
join the faceplate's ground to the main board's.

---

## Panel

28HP (141.9 × 128.5 mm), laid out in `circuit.py` (`PANEL_XY`) and drawn by
`panel.py`: hole list, 1:1 drill template and the artwork
(`hardware/panel/`), the same positions and label list as the panel PCB.

- **Channels:** columns 13.5 mm apart (x 11.5 … 106 from the left), like a
  console: SEND (y 24), PAN (40.5), LEVEL (57), MUTE button (72), jacks at
  the bottom so cables hang away from the knobs. Mono channels have their
  IN in the bottom row (103), stereo channels L at 88 and R at 103, with a
  dotted line for "R follows L". The stereo pair's empty PAN slot carries a
  STEREO bracket. All eight LEVEL knobs are in one row.
- **Master section** (columns at 120 and 133.5): SEND out at the top on a
  gold patch; RETURN L / R; the RETURN and DRUMS knobs; FX IN and DRUM IN
  (both from the drum mixer); MASTER; OUT L / R on the gold band.
- **Labels:** each channel row is labelled once, in the left margin: the
  word (SEND, PAN, LEVEL, MUTE, IN) turned 90° to read bottom to top, on a
  bracket as tall as the row with its serifs pointing at the controls, the
  STEREO bracket on its side. Nothing sits between the rows. The pans
  carry a small L and R at the ends of their scales, the stereo jacks
  their own L / R, the master section a word per knob and jack. On the
  panel PCB the words are STRINGs at angle 90; check after import that
  they read bottom to top (if not, the angle is 270).
- **Style:** the Marblesy / Plaitsy one: black mask, white silk, title
  "Mycelium" (was "Mixer") in serif italic, subtitle top right, dotted double rule, scale
  arcs on every knob, rings round the buttons, outputs on bare ENIG
  copper, the gold mushroom mark at the bottom (was "Seedable Instruments").
- **Holes:** 7.5 mm pots, 6.5 mm jacks and buttons, 5.5 × 3.2 mm mounting
  slots. Knobs: up to about 11 mm across in the channel strips (13.5 mm
  pitch), 12 mm for MASTER.
- **Offsets** (applied in `panel.py`): Thonkiconn barrel 0.78 mm below the
  WQP518MA origin; Alpha pot shaft 7.5 mm from its pin row, which is 4.0 mm
  beyond the pot footprint's origin.

Preview: `hardware/panel/stereo-mixer-panel-preview.png`.

---

## PCB placement

`hardware/tools/pcb.py` places every part of both boards, assigns each pad
its net and writes the two PCB documents into `StereoMixer.epro2`; the
exporter checks the result (pads 0.25 mm apart, 0.5 mm from the edge, no
bodies overlapping on one side, nothing within 3 mm of a standoff or screw
head, header pins coinciding on both boards, panel parts exactly at
`PLACEMENT`, no rear-side pad under a panel part's housing): 0 problems.
Routed since: see `StereoMixer-routed.epro2`. Placement previews: `hardware/easyeda/stereo-mixer-easyeda-pcb-*.png`.

**Frame.** As on Plaitsy: each PCB drawn as EasyEDA shows it, looking at
the top layer, which is the rear of the stack on both boards. The front
view is the mirror image, `x_front = 140.4 − x`, so in the PCB documents
channel 1 is on the right and the master section on the left.

**Footprints.** Generated where the library has none or a wrong one:
- **Alpha 9 mm pots**, single (RD901F) and dual-gang (RD902F), from KiCad's
  footprints. The shaft is 7.5 mm from the pin row and the lugs sit on the
  shaft line, 4.8 / 4.75 mm either side. Your library's PTV09A is Bourns'
  part: its lug slots are 0.5 mm off the Alpha's. Same frame as the PTV09A
  (pins 3.5 mm below the origin), so the shaft is 4.0 mm above it.
- **DIP-14** on the standard 7.62 mm row pitch for the TL074s and CMOS
  chips. The library TL074ACN footprint has its rows 8.89 mm apart, too
  wide for a DIP socket. **DIP-4** for the PhotoMOS.
- The Thonk LED button, standing resistors and 1×N headers are Plaitsy's.

**Faceplate.** Bottom layer: the panel parts at `PLACEMENT`, pots pins
down (pin 1 left, so CW turns towards pin 3), jacks sleeve up, buttons
with their LED pins along x. Top layer: the nine male headers, standing in
the strips between the columns, 6.75 mm left of each channel's column
(front view), from just under the LEVEL pots' pins (panel y 61) down to
above the jacks; H9 between channel 8 and the master columns. Nothing else
on this board.

**Main board.** Bottom layer: the nine sockets. Top layer:
- **Op-amps** standing vertical in a row at y 81 (PCB x): U4 13, U3 40,
  U2 70, U1 111.5. Each section's parts sit at its corner of the chip, the
  Plaitsy way:
  - **Follower:** the 10k mute resistor beside IN+ (its FI end on the chip
    side), the PhotoMOS switch pins under it, its LED pins facing outward,
    the pan feeds (or the stereo send average) beyond the chip's end. In
    the two corners where the PhotoMOS would face its LED side at the chip,
    it is turned over: there pin 4 (GND) comes first and FI runs under its
    body to pin 3.
  - **Summer:** Rf on IN− / OUT, Cf one column out, the ten bus resistors
    in a 2 × 5 block beyond the chip's end, their summing pads (2) in the
    two middle rows facing each other, inputs on the outer rows. The
    summing node is one 10 × 2.5 mm patch plus the few mm up to IN−.
  - **Output stage:** Rf on IN− / OUT, Rin and Rs one column out.
  - **Decoupling:** each rail's 100 n lies outward from its supply pin
    (pad 2.54 mm from pin 4 or 11).
- **Latch:** under each header's bottom pins (BTN, LED) the pull-up,
  debounce resistor and LED resistor standing in a row, the debounce cap
  beside them; CD4093s at y 25.5 (U5 under channels 1–4, U6 under 5–8),
  CD4013s at y 12 (one per two channels), each with its 100 n at the pin
  14 end; the power-on reset left of U10.
- **Power:** J18 standing along the left edge, pin 1 (−12 V) at the bottom,
  the diodes, 10 Ω and 10 µF between it and H9. D903 (POR clamp) at
  (28, 18–26) beside C906, cathode up; D904 (+12 V clamp) at x 25.4 just
  left of it, its cathode pad sitting on the +12 V trunk.
- **Phase-lead caps:** C907 at 45° under R906 (both tracks on the top
  layer, the NO_L one running up between the R904 / R906 and R905 columns),
  C908 at the board's left edge beside R907 / R909, C909 one column left
  of R910 / R912 (2026-11-14).

**Mounting.** Four 3.2 mm holes, the same on both boards: front view
(17.5, 103.75), (113.25, 103.75), (17.5, 4.75), (113.25, 4.75), in the
strip above the SEND row and below the jacks. M3 standoffs as long as the
mated headers make the gap (measure the pair, about 11 mm with standard
sockets and male headers).

**What EasyEDA's DRC will still say.** Floating pins on J18's pins 11–16
and on the output jacks' open switch lugs (J15–J17): intentional.

---

## Routing notes

Same plan as Plaitsy: rules, the few nets that matter by hand, the
autorouter for the rest with the grounds excluded, pours.

**Rules.** Clearance 0.25 mm where there is room (Marblesy passed with
0.152), 0.3 mm signal tracks, 0.6 mm for the POWER class (+12V, −12V,
P12_IN, N12_IN, P12_D, N12_D), vias 0.61 / 0.3 mm. Nothing but ground
within 3 mm of the mounting holes on either side.

**Autorouter.** Both layers, vertical on top and horizontal on the bottom,
45°, via quantity "less", "completion first" then "quality first" on the
ugly nets. Skip GND, GND_F and the POWER class.

**Ground.** Pour GND on both layers of the main board and GND_F on both
layers of the faceplate, stitched with vias. Each header has at least one
ground pin; the grounds meet there.

**Main board, by hand.**
1. Summing nodes: each 2 × 5 block's middle rows and the line to IN−, one
   layer, short, under the pour of the other layer. Rf and Cf straight
   onto IN− and OUT.
2. FI nodes (10k resistor, PhotoMOS pin 3, IN+): a few mm each, the
   highest impedance on the board. In the turned-over corners (U1 and U2
   top right and bottom left, U3 top right, see the preview) FI passes
   under the PhotoMOS body between its pin rows.
3. LV, CH, PL, PR, SD, AV from the headers up to the clusters; PL / PR /
   SD on to the bus blocks (U4 for L / R, U3 for the send): ordinary
   signal lines, a few cm, keep them off the CK lines.
4. Power: ±12 V from the protection parts at the bottom left along the
   board to the 100 n beside each chip, 0.6 mm; +12 V also to the pull-ups,
   the CMOS chips and C906.
5. Logic: DB from the debounce caps to the CD4093 inputs, CK from the
   CD4093 outputs to the CD4013 clocks, POR along all four CD4013s. QK from
   the CD4013s to the LED resistors, then LA up to the PhotoMOS LEDs at the
   op-amps and back down to the header's LED pin: DC, route them wherever
   there is room, away from the FI nodes.

**Faceplate.** Wipers and pot ends to the headers on the panel side under
GND_F; BTN and LED lines from the buttons to the header beside them;
OUT_L / OUT_R / SEND from H9 to the output jacks; ground every pot lug and
jack sleeve to the pour.

---

## BOM

Build notes (from the 2026-11-04 test suite):
- Before soldering, check one LED button with a meter: contacts 1+2 / 3+4, LED anode on 5. If 1 and 3
  were the joined pair instead, BTN would be shorted to GND_F.
- Fit the DIP sockets before the standing resistors: at the largest socket sizes R502, R706 (U2) and
  R405 (U4) lean on a socket corner. Lean the CMOS decoupling caps (C921–C926) slightly away from
  their chips.
- R918 carries up to about 125 mA (R919 about 60 mA): 0.6 W parts in the 1/4 W body (TE LR1F, Vishay
  MBB0207) for both.
- When rebuilding the copper areas, give the pours a minimum island area of about 2 mm²: that drops
  the 0.17 mm² wedge beside C913 that hangs on one spoke.

Generated from `circuit.py` by `hardware/tools/bom.py`, with the Thonk parts in their own table:
[bom.md](bom.md), and as CSV in `hardware/bom/`. The Thonk parts of Spore, Orchid, Moss and
Mycelium are summed into one order in [bom/thonk-order.md](../../bom/thonk-order.md).
