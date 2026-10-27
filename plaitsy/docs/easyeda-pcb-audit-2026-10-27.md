# Plaitsy EasyEDA project audit

Audit of `ProDoc_Plaitsy_2026-10-27.epro2` (EasyEDA Pro 3.2, two schematic
pages, one 120 × 110 mm PCB holding the faceplate board and the main board side
by side). The netlist was rebuilt from the PCB's pad-to-net records, every pad
position was recomputed from the footprint libraries and checked against the
routed tracks, and the result was compared with `design.md` and with the parts
Thonk sells.

Method notes: the uploaded project is newer than `hardware/easyeda/Plaitsy.epro2`
in this repo (it adds the PCB). Bottom-layer parts in EasyEDA Pro are mirrored
about the footprint's own X axis and then rotated; with that rule every routed
track lands on a pad, so the positions below are trustworthy. Thonk's site and
most datasheet hosts are not reachable from this session, so two items are
marked "verify" rather than decided.

---

## Verdict

The circuit is sound and the schematic matches the PCB netlist. The CV stages,
mux, probe, clamps, jack and pot pinouts and all 36 board-to-board pins check
out. Do not order the PCB yet: the Daisy Seed breakout footprint has the wrong
pin pitch, the Seed's digital ground is left floating on the main board, and the
button footprint's internal pin pairing has to be confirmed. The panel files in
the repo belong to the stripboard layout, not this PCB.

---

## Must fix before ordering

### 1. Seed breakout footprint has 2.0 mm pitch, the Seed has 2.54 mm

Footprint `daisy seed power board` (U2) places pins 1–20 and 21–40 at 2.0 mm
spacing. The routed tracks confirm it: D0 ends at (95.25, 91.95), D1 at
(95.25, 89.95), D2 at (95.25, 87.95). The row spacing is right (15.24 mm), the
pitch is not.

| | Footprint | Daisy Seed |
|---|---|---|
| Pin pitch | 2.00 mm | 2.54 mm |
| Span of 20 pins | 38.0 mm | 48.3 mm |
| Row spacing | 15.24 mm | 15.24 mm |

The breakout's J1–J16 pads have the same 2.0 mm error. Redraw the footprint at
2.54 mm (0.1 in) pitch, keep 15.24 mm between rows, then re-route everything
that touches U2. Check the J1–J16 positions and names against the real
`seed_power_opamps` board before trusting them; I could not reach its OSHWLab
page.

### 2. DGND is not joined to GND on the main board

Net DGND contains only U2 pin 40 and U17.3 (the faceplate LED and button
return, GND_D_F). Net GND holds AGND (pin 20), the breakout GND pins and
everything else. Electro-Smith says AGND and DGND are not joined inside the
Seed and must be joined outside it (the Pod does this on the carrier). Unless
the breakout ties pin 40 to its ground, the Seed's digital side and the whole
faceplate LED/button return have no path to ground. Add a track from DGND to
GND next to the Seed. Keep the faceplate's GND_D_F as its own pin if you like,
but land it on GND.

### 3. Button pin pairing: verify before soldering

Footprint `SW-TH_D6R40F1LFS` is a 5 × 5 mm square (pads 1 and 4 on the left,
2 and 3 on the right). This matches Thonk's "Highly Tactile Switches" (Highly
KS01-B, Ø12 mm body, 5 × 5 mm terminal pitch, the Radio Music switch). The
schematic ties pads 1 + 4 to GND_D_F and 2 + 3 to BTN_x_F. That is correct only
if the switch internally bridges the two left pins and the two right pins. If
it bridges top with top and bottom with bottom instead, each button is a
permanent short to ground. Put a meter on a real switch: the two pins that read
0 Ω unpressed must both sit on the same net. If they are the top pair, rotate
the footprint by 90° on the PCB (the nets stay as drawn).

### 4. Panel files in the repo do not match this PCB

`hardware/panel/plaitsy-panel-holes.csv` was generated from the stripboard
placement (pots at 12.4 / 48.2 mm from the left, jacks 10.2 mm apart). The PCB
puts the pots at 10 / 30 / 50 mm and the jacks 12.6 mm apart. Regenerate the
panel from the PCB. A hole table computed from the PCB is at the end of this
document; it also carries the three offsets from items 5 to 7 below.

---

## Should fix

### 5. LED body is 0.64 mm off the footprint origin

`LED-TH_4P-L5.0-W2.5-P1.27_LED-RGB` is a 4-pad, 1.27 mm pitch footprint for a
5 mm RGB LED. A 3-lead 3 mm bicolour LED (1.27 mm lead pitch) goes in pads 1–3,
so its body is centred on pad 2, which is 0.64 mm from the origin. On the PCB
the LED centres are therefore at x = 30.64 mm, not 30.00 mm. A 3 mm LED in a
3.2 mm panel hole does not forgive 0.64 mm. Either drill the panel at the pad-2
positions or replace the footprint with a 3-pad one whose middle pad is the
origin (and whose silkscreen is a 3 mm circle, not the 5 mm box drawn now).
Pad 4 is unconnected on all eight LEDs, which is fine.

### 6. Jack footprint: slot holes and the barrel keep-out

The WQP518MA footprint (the Thonkiconn, also sold as PJ398SM and PJ301M-12,
all interchangeable) has pads S / TN / T at 0 / 3.1 / 11.4 mm, the same as the
KiCad PJ398SM footprint, and the schematic uses them as sleeve / switch / tip.
That is right. Two things to look at:

- The pad holes are 1.3 × 0.6, 1.5 × 0.6 and 1.5 × 0.5 mm slots. Most fabs
  want slots at least 0.65 mm wide. KiCad uses 1.22 / 1.42 / 1.43 mm round
  holes; those fit the flat lugs with margin.
- The jack has a metal tab under the barrel. KiCad marks the barrel centre
  (6.48 mm from the sleeve pad towards the tip) as a keep-out, and jack
  vendors advise no copper there. On this PCB the CV_TRIG_F track runs 1.8 mm
  from the barrel centre of both J1 and J6, on the jack side of the board. Move
  it, or add a 3 mm keep-out at each barrel. The GND_F pour under the barrels is
  harmless.

### 7. Pot shaft is 0.5 mm further from the pins than the footprint origin

`SW-TH_PTV09A-4015F-B502` puts the origin and the lug slots 6.97 mm behind the
pin row. KiCad's Bourns PTV09A footprint puts the lugs 7.0 mm behind the pins
and the shaft 7.5 mm behind them. Thonk's Alpha 9 mm vertical pots share this
geometry (2.5 mm pin pitch, lugs about 8.6–8.8 mm apart). So the shaft centre
is at origin + 0.5 mm away from the pins: x = 10.54 / 30.54 / 50.54 mm instead
of 10 / 30 / 50. Use those for the panel, or shift the footprints by 0.5 mm.
Verify the lug position on a real Alpha pot before ordering; the 2.2 × 2.0 mm
slots leave little room. CW rotation drives the wiper towards 3V3A_F, so the
pots read the right way round.

### 8. Board-to-board headers: both sides use the same footprint

All seven mating pairs use identical footprints on both boards (16P female for
U8 and U11, 7P female for U9 and U10, male for the rest). Position and pin
order are correct: with the main board stacked on the faceplate in the same
orientation, all 36 pins line up pin-for-pin (checked numerically; the
horizontal headers are not reversed). The BOM, not the layout, needs fixing:
one side male pin headers, the other side female sockets. Thonk's "Male +
Female Header Bag" covers it. Standard sockets give a board gap of about
8.5 mm; the only parts on the faceplate's rear are R9–R13 and the two sockets,
so that gap is enough.

### 9. Board outline and ordering as two boards

The outline is one 120 × 110 mm rectangle with a second, unlocked line on the
outline layer at x = 60 mm, and a stray outline-layer line from (0, 110) up to
(0, 153) outside the board. Delete the stray line. For the split, either order
two separate 60 × 110 mm boards (cleaner) or ask the fab for a V-score at
x = 60 mm; a bare line on the outline layer is ambiguous.

### 10. Mechanics

- Neither board has a mounting hole. The main board, the breakout and the Seed
  hang on the 36 header pins. Add two M3 holes at matching positions on both
  boards and use a standoff.
- 110 mm is tall for a 3U board. Many rails leave about 112 mm; most Eurorack
  PCBs stay at or below 108 mm. Check your case before fixing the height.
- Depth: panel + jack (about 9 mm) + faceplate + header gap + main board +
  breakout sockets + breakout + Seed sockets + Seed adds up to roughly 45–50 mm.
  Fine in a standard case, not in a skiff.
- The faceplate's rear carries R9–R13 as axial resistors lying flat. That is
  fine under an 8.5 mm header gap.

---

## Checked and found correct

- **Seed pin map.** Pins 1–15 are D0–D14 (LED lines), 22 is D15/A0 (probe
  out), 23–32 are A1–A10 as in `design.md`, 33–35 are D26/D27/D28 (mux S0/S1/
  S2), 36–37 are D29/D30 (buttons, external USB pins, usable as GPIO with
  pull-ups), 21 is 3V3A, 20 AGND, 40 DGND. Pins 16–19 (audio) and 38–39 (3V3D,
  VIN) are left open, which is right when the breakout feeds the Seed.
- **74HC4051.** Y0–Y7 on pins 13/14/15/12/1/5/2/4, Z on 3, S0/S1/S2 on
  11/10/9, E and VEE on 6 and 7 to GND, VCC 16 with C8. Channel 7 grounded.
  Matches the mux table in `design.md`. HC at 3.3 V is fine; a CD4051B works.
- **CV stages.** Rin 100 k, Rf 13 k, Cf 1 n gives −0.13 gain and a 12 kHz
  corner; 1.467 V bias gives V_adc = 1.658 − 0.13·V_in, so ±12 V stays inside
  0.1–3.2 V. V/OCT with Rf 33 k and 1.768 V bias gives 2.351 − 0.33·V_in and the
  BAT85 clamps are the right way round: D21 cathode (pin 1) to 3V3A, anode to
  ADC_VOCT; D22 cathode to ADC_VOCT, anode to GND. All eight non-inverting
  inputs are biased (seven on BIAS_A, V/OCT on BIAS_V). Both TL074s have
  +12 V on pin 4, −12 V on pin 11 and 100 n decoupling on each rail.
- **Probe.** A0 drives R9–R13 (10 k) into the switch lugs of TIMBRE, FM,
  MORPH, TRIG and LEVEL. MODEL, HARMONICS and V/OCT lugs go to ground, OUT and
  AUX lugs are open. Same scheme as Plaits.
- **LED drive.** 470 Ω from 3.3 V gives about 2.5–3 mA per colour. Common
  cathode on pad 2 (the middle lead), R on pad 1, G on pad 3.
- **Copper.** Every net is fully connected through tracks, vias or the two
  bottom-side pours (GND on the main board, GND_F on the faceplate). No split
  nets, 29 vias, all tracks 0.254 mm. Power tracks could be wider but carry
  little current.
- **Rails.** 3V3A feeds seven 10 k pots (2.3 mA), the mux and two dividers.
  The V/OCT clamp can push up to about 3 mA into 3V3A on a −12 V input; the
  Seed's own analog load absorbs that.

### Documentation drift (no circuit effect)

- `design.md` puts MODEL on U3A, TRIG on U4B and LEVEL on U4C. The schematic
  has MODEL on U4 pins 8/9/10, TRIG on U3 pins 8/9/10, LEVEL on U4 pins 5/6/7,
  MORPH on U3 pins 12/13/14 and V/OCT on U4 pins 12/13/14.
- `design.md` puts R1 (LED8 red) on the faceplate; on the PCB it sits on the
  main board next to R60–R74.

---

## Thonk parts against the footprints

| Part on the PCB | Footprint | Thonk part | Fit |
|---|---|---|---|
| J1–J10 | CONN-TH_WQP-WQP518MA | Thonkiconn PJ398SM (+ nuts) | Fits; pad order S/TN/T verified. See item 6. |
| RV1–RV7 | SW-TH_PTV09A-4015F-B502 | Alpha 9 mm vertical B10K (6.35 mm round, D or T18 shaft) | Fits; shaft 0.5 mm behind the origin, see item 7. Pick knobs for the shaft type you order. |
| SW1, SW2 | SW-TH_D6R40F1LFS | "Highly Tactile Switches" KS01-B, Ø12 mm, 5 × 5 mm pins | Fits the pad pattern; pin pairing to verify, item 3. Panel hole is about 11.5–12.5 mm for the round cap, not the 5.2 mm in the old CSV. Overall height about 12.8 mm, which suits a Thonkiconn-height panel; Thonk uses this pairing on Radio Music. |
| D1–D8 | LED-TH_4P 1.27 mm | not stocked | Thonk only lists a 2-lead bicolour (Hakai Labs CVD) and single-colour 3 mm LEDs. Buy 3 mm, 3-lead, common-cathode red/green LEDs elsewhere (Kingbright, Tayda). A 2-lead bicolour would need a different drive circuit (anti-parallel across two GPIOs). |
| U2 | daisy seed power board | Daisy Seed (£31 at Thonk) | Footprint pitch wrong, item 1. The breakout itself is not a Thonk part. |
| U3, U4 | PDIP-14 | TL074 DIP-14 | Stocked (check availability). |
| U1 | DIP-16 | — | 74HC4051 is not at Thonk. |
| Headers | 2.54 mm | Male + Female Header Bag | One gender per side, item 8. |
| D21, D22, R, C | DO-35, axial, radial | — | Not Thonk parts; Tayda, Mouser or LCSC. |
| Knobs | — | Mutable Instruments knobs, Davies 1900h clones | Match the shaft (T18 knurled vs 6.35 mm round vs D). |

---

## Panel holes computed from the PCB

Coordinates in mm from the faceplate PCB's bottom-left corner, x to the right,
y up, seen from the front. Add your own offset for the panel (a 60.6 × 128.5 mm
12HP blank has 0.3 mm spare each side and 18.5 mm spare in height; split that
as you prefer, keeping the rails in mind). Three offsets are applied as noted.

| Item | x | y | Hole | Note |
|---|---|---|---|---|
| J1 MODEL | 55.25 | 21.83 | 6.5 | barrel = sleeve pad + 6.48 mm towards tip (KiCad PJ398SM); `sb.py` used 5.86, measure one jack |
| J2 TIMBRE | 42.64 | 21.83 | 6.5 | |
| J3 FM | 30.04 | 21.83 | 6.5 | |
| J4 MORPH | 17.43 | 21.83 | 6.5 | |
| J5 HARMO | 4.83 | 21.83 | 6.5 | |
| J6 TRIG | 55.25 | 6.89 | 6.5 | |
| J7 LEVEL | 42.64 | 6.89 | 6.5 | |
| J8 V/OCT | 30.04 | 6.89 | 6.5 | |
| J9 OUT | 17.43 | 6.89 | 6.5 | |
| J10 AUX | 4.83 | 6.89 | 6.5 | |
| RV1 FREQUENCY | 50.54 | 86.19 | 7.5 | shaft = pin row + 7.5 mm |
| RV2 HARMONICS | 10.54 | 86.19 | 7.5 | |
| RV3 TIMBRE | 50.54 | 63.90 | 7.5 | |
| RV4 MORPH | 10.54 | 63.90 | 7.5 | |
| RV5 TIMBRE att. | 50.54 | 41.61 | 7.5 | |
| RV6 FM att. | 30.54 | 41.61 | 7.5 | |
| RV7 MORPH att. | 10.54 | 41.61 | 7.5 | |
| D1–D8 LEDs | 30.64 | 95.23, 89.23, 83.23, 77.23, 71.23, 65.23, 59.23, 53.23 | 3.2 | centre = pad 2 |
| SW1 left | 42.00 | 103.64 | per KS01-B datasheet | footprint origin |
| SW2 right | 18.00 | 103.64 | per KS01-B datasheet | |

The jack rows are 12.6 mm apart horizontally and 14.9 mm apart vertically; the
pot rows are 22.3 mm apart. Thonkiconn nuts (about 8 mm across) and 9 mm pot
bodies clear each other at these spacings.

---

## Addendum: the breakout's PCB file

Rob Heel's `seed_power_opamps` PCB (EasyEDA JSON) settles two items above:

- Its Seed sockets are 2.54 mm pitch, two rows 15.24 mm apart, so item 1
  stands: the footprint in the Plaitsy project is wrong, the breakout is not.
  The headers sit in line with the socket rows: J1 (GND, −12 V ×3) and J3
  (GND, +12 V ×3) beyond pins 20/21 with one empty position in between, J5
  (audio in) and J4 (audio out) directly beyond pins 1/40. A corrected
  footprint with all 56 pads is in `marbles/hardware/easyeda/Marbles.epro2`
  (`DAISY-SEED-POWER-OPAMPS-2.54`); copy it into the Plaitsy project.
- The breakout joins Seed pins 20 and 40 on its own GND net, so item 2 is
  covered as long as the breakout is fitted. A local DGND-to-GND track on
  the main board is still cheap insurance.
