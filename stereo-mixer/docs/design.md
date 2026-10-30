# Stereo mixer (PCB) — design notes

The voice case's stereo master, Eurorack 28HP, on two stacked PCBs behind a
PCB panel, built the way Marblesy and Plaitsy are: Thonk panel parts, every
main-board resistor standing up and clustered on its op-amp, the panel as
the project's third board. Every designator matches
`hardware/tools/circuit.py`, which generates the EasyEDA Pro project
(`hardware/easyeda/StereoMixer.epro2`) and the panel files.

Status: schematic done and checked (6 pages, 0 problems), footprints
assigned, both PCBs placed and net-assigned, header pin orders picked for
the fewest crossing lines, the panel as the third board. Nothing routed or
built.

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
- **Mute:** an AQY212EH PhotoMOS from FIk to GND. Off, it is an open switch
  on a high-impedance node, so the follower sees the wiper and the channel's
  gain is unchanged. On, it shorts FIk (0.83 Ω typical, 2.5 Ω max) behind
  10k plus the wiper's own resistance: the channel drops by 82 dB typically,
  72 dB at worst. The source is never loaded by the mute, so a multed
  signal keeps its level elsewhere.
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
Q high = muted: Q → 1k5 → the PhotoMOS LED (two in series on a stereo
channel) → header → the button's LED → GND_F, about 5 mA on a mono channel
and 4.3 mA on a stereo one with a red button LED (the AQY212EH needs 3 mA
at most). Every flip-flop's RESET comes from one power-on RC (1 µF from
+12 V, 100k to GND, a 1N4148 to empty it at power-off): about 100 ms of
reset at power-up, longer than the debounce caps take to settle, so the
mixer always starts with every channel open.

| Channel | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| CD4093 gate | U5.1 | U5.2 | U5.3 | U5.4 | U6.1 | U6.2 | U6.3 | U6.4 |
| CD4013 half | U7.1 | U7.2 | U8.1 | U8.2 | U9.1 | U9.2 | U10.1 | U10.2 |
| PhotoMOS | K1 | K2 | K3 | K4 | K5 | K6 | K7 (L), K8 (R) | K9 (L), K10 (R) |
| Pull-up, debounce, LED resistor, debounce cap | R107–R109, C101 | R207–R209, C201 | R307–R309, C301 | R407–R409, C401 | R507–R509, C501 | R607–R609, C601 | R708–R710, C701 | R808–R810, C801 |

The switching is fast (about 1 ms on, 0.1 ms off), so muting a loud
signal can click, as with the toggles before. If it bothers you: a 22 µF
across the PhotoMOS LED and button LED chain, the 1k5 already in series,
turns the PhotoMOS on over about 30 ms, which mutes more softly.

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

### Gains (unchanged)

| Source, at full LEVEL | Gain to OUT, MASTER at full |
|---|---|
| Mono, hard panned | 0.95 on that side (−0.4 dB) |
| Mono, centred | 0.65 per side (−3.8 dB) |
| Stereo channel | 1.0 per side |
| RETURN | 1.0 per side |
| DRUMS | 0.67 per side (−3.5 dB) |
| Any SEND (mono, stereo (L+R)/2, FX IN) to SEND OUT | 1.0 (stereo 0.95) |

Pan law, B10k from fully CCW: L −0.4 / −1.7 / −3.8 / −8.1 dB / off at 0,
¼, ½, ¾, 1; L² + R² stays within 0.4 dB. The TL074s swing about ±10.5 V,
so the outputs clip at twice Eurorack level and the summers at four times.
Set the output module's IN at noon or below (its input stages have a gain
of 2).

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
  −12 V (red stripe), 3–10 GND, 11–12 +12 V; 13–16 unused.
- **Reverse protection:** series 1N5819 per rail (−12 V: cathode on the
  header), then 10 Ω, 10 µF per rail.
- **Decoupling:** 100 n per TL074 per rail beside pins 4 and 11; 100 n per
  CMOS chip beside its pin 14.
- **Current:** about 25 mA on −12 V; on +12 V about 25 mA plus 4–5 mA per
  muted channel, 65 mA with all eight muted.

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

The faceplate side of each net has `_F` added (GND → GND_F). Ten GND pins
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
  "Mixer" in serif italic, subtitle top right, dotted double rule, scale
  arcs on every knob, rings round the buttons, outputs on bare ENIG
  copper, "Seedable Instruments" at the bottom.
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
Nothing is routed. Previews: `hardware/easyeda/stereo-mixer-easyeda-pcb-*.png`.

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
  the diodes, 10 Ω and 10 µF between it and H9.

**Mounting.** Four 3.2 mm holes, the same on both boards: front view
(17.5, 103.75), (113.25, 103.75), (17.5, 4.75), (113.25, 4.75), in the
strip above the SEND row and below the jacks. M3 standoffs as long as the
mated headers make the gap (measure the pair, about 11 mm with standard
sockets and male headers).

**What EasyEDA's DRC will still say.** Floating pins on J18's pins 13–16
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
   the CD4013s to the 1k5s, then LA up to the PhotoMOS LEDs at the
   op-amps and back down to the header's LED pin: DC, route them wherever
   there is room, away from the FI nodes.

**Faceplate.** Wipers and pot ends to the headers on the panel side under
GND_F; BTN and LED lines from the buttons to the header beside them;
OUT_L / OUT_R / SEND from H9 to the output jacks; ground every pot lug and
jack sleeve to the pour.

---

## BOM

| Qty | Part | Value / note | Refs |
|---|---|---|---|
| 4 | TL074 + DIP-14 socket | | U1–U4 |
| 2 | CD4093B + DIP-14 socket | quad Schmitt NAND | U5, U6 |
| 4 | CD4013B + DIP-14 socket | dual D flip-flop | U7–U10 |
| 10 | AQY212EH (Panasonic PhotoMOS, DIP-4) | Mouser / Farnell / LCSC | K1–K10 |
| 2 | 1N5819 | | D901, D902 |
| 1 | 1N4148 | | D903 |
| 37 | Resistor 100k | 1 % | bus feeds, sends, pull-ups, summer and inverter resistors, R920 |
| 34 | Resistor 10k | 1 % | mute series, pan feeds, send averages, debounce |
| 8 | Resistor 200k | 1 % | stereo and return bus feeds, output feedback |
| 2 | Resistor 300k | 1 % | R915, R916 |
| 8 | Resistor 1k5 | | LED / PhotoMOS current: R109 … R810 |
| 3 | Resistor 1k | | R906, R909, R912 |
| 2 | Resistor 10 Ω | | R918, R919 |
| 3 | Capacitor 22 pF C0G | | C901–C903 |
| 22 | Capacitor 100 nF | 5.08 mm pitch | decoupling C911–C918, C921–C926; debounce C101 … C801 |
| 1 | Capacitor 1 µF | 5.08 mm pitch | C906 |
| 2 | Electrolytic 10 µF 35 V | 2.5 mm pitch, 5 mm | C904, C905 |
| 1 | 2×8 box header, 2.54 mm + Eurorack ribbon | | J18 |
| 17 | Thonkiconn PJ398SM | Thonk | J1–J17 |
| 15 | Alpha 9 mm vertical pot A100K | Thonk | LEVEL 1–6, SEND 1–8, DRUMS |
| 6 | Alpha 9 mm vertical pot B10K | Thonk | PAN 1–6 |
| 4 | Alpha 9 mm vertical dual-gang pot A100K (RD902F) | check stock: dual-gang Alpha pots are mostly sold linear | LEVEL 7, LEVEL 8, RETURN, MASTER |
| 8 | Thonk low-profile LED button | red reads as "muted"; clip the three feet | SW1–SW8 |
| 25 | Knobs | ≤ 11 mm for the channels, ~12 mm for MASTER | |
| 9 | Male pin headers 1×8 (8×), 1×12 | Thonk male + female header bag | HF1–HF9 |
| 9 | Female sockets 1×8 (8×), 1×12 | | H1–H9 |
| 4 | M3 standoffs + screws | length = the mated headers' gap | |
| 2 | PCBs 140.4 × 108 mm, 2 layer | `Mixer Main PCB`, `Mixer Faceplate PCB` | |
| 1 | Panel PCB 141.9 × 128.5 mm | black mask, white silk, ENIG: `Mixer Panel PCB` | |

If no A-taper dual-gang pot can be had, B100K duals work with a 22k from
each wiper to GND on the stereo LEVEL and RETURN pots, which bends a linear
pot close to an audio taper; ask and I'll put the resistors in the
netlist.
