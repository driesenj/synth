# Plaitsy routing audit, 2026-11-01

## Second export, `ProPrj_SI - Plaits_2026-11-01(1).epro2`

The fixes are in. LED_D3_G no longer touches D2's pad, the 3V3D_F track is
clear of D7, R12 moved 0.2 mm towards the edge (its 1.8 mm pads now end
0.30 mm from the board edge, exactly the fab's minimum; the generator's
edge rule is that 0.3 now, and the free strip above the buttons would be
a roomier home for R12), and the PROBE_F via left J5's barrel (the track
still passes 2.2 mm from it). Every net is still one
piece, no net touches another, the main board is unchanged, the headers
and the panel still match, and the generator agrees with this export pad
for pad (0 problems). This export is now `Plaitsy-routed.epro2`.

One thing before Gerbers: **the ground pours were not rebuilt.** The
`POURED` records are byte for byte those of the first export while 26
faceplate tracks moved (3V3D_F, LED_D3_G, PROBE_F), so the moved copper
now lies inside the old pour outline: the audit shows eleven "inside the
GND_F pour" items, all on those three nets. Rebuild all copper areas in
EasyEDA Pro, run DRC, export once more, and the audit should come back
with nothing under 0.152 mm. Still worth a look from the first pass: J1's
sleeve pad 2.66 mm from the (55.9, 30) standoff (a ground joint; use a
5 mm or nylon standoff), and the PROBE_F track within J5's barrel keepout
on the panel side.

## First export, `ProPrj_SI - Plaits_2026-11-01.epro2`

Audit of the first routed export of both Plaitsy boards (EasyEDA Pro
3.2.209). Run by
`hardware/tools/copper_audit.py`: it rebuilds every pad from the footprints
in the export, joins tracks, vias, pads and EasyEDA's computed pours
(thermal spokes included) into one copper graph per net, and compares the
pads and nets with `circuit.py` and the generator's boards. Pads are
checked as exact rectangles or capsules; EasyEDA's DRC is still the last
word.

Coordinates below are the PCB frame EasyEDA shows (mm, origin bottom-left,
looking at the top layer = the rear of the stack).

---

## Verdict

Both boards are complete: every net is one piece of copper, no net touches
another, the headers line up pin for pin, the panel board is the generated
one, the pot and DIP-14 footprints are the corrected ones. The faceplate
has one short and two gaps under the 0.152 mm rule to fix before ordering;
the main board is clean. Three small things to look at while you are in
there.

---

## Must fix (faceplate)

1. **LED_D3_G runs over D2's green pad.** The top-layer track from
   (21.8, 93.1) to (28.4, 86.5) crosses pad D2.3 (LED_D2_G) at
   (28.4, 87.7): 0.04 mm of overlap, so D2 and D3 would both light green
   together. Route it around the pad (it is the diagonal from R82's end
   down to D3).
2. **3V3D_F past D7.** The bottom-layer track along y = 60.0 from
   x 11.5 to 30.2 passes 0.10 mm from D7's cathode and green pads at
   y 61.2; the rule is 0.152 mm (and the D7.1 pass, at 0.152, is exactly
   on it). Drop the track 0.2 mm or route it under the LED row at y 59.6.

After the fix, re-export and run `python copper_audit.py <export>`; then
`python easyeda_export.py` must report 0 PCB problems (it now compares the
generator with the routed export, see below).

## Worth a look

3. **R12 touches J6's housing outline.** R12 (the probe resistor you moved
   to the left margin) has pad 1 at (58.0, 4.85), 0.01 mm inside the drawn
   outline of J6's body on the panel side. The jack body is plastic and the
   pad is soldered on that side, so a solder blob could sit against the
   jack. 0.5 mm towards the edge clears it (the pad is 0.55 mm from the
   edge; 0.3 is the fab's minimum).
4. **PROBE_F under J5's barrel.** On the panel side a PROBE_F track passes
   2.2 mm from the centre of J5's barrel and its via sits 2.1 mm from it,
   inside the 3 mm the design notes keep free for the jack's metal barrel.
   The via is tented and the track is under mask; if the Thonkiconn's
   underside is bare plastic there, as it usually is, this is fine. Check
   one jack.
5. **J1's sleeve pad and the (55.9, 30) standoff.** The sleeve pad (GND_F,
   soldered on the rear) is 2.66 mm from the hole centre; a 5.5 mm M3
   standoff reaches 2.75 mm. The standoff would rest on a ground solder
   joint, which is harmless; a nylon standoff or a 5 mm one avoids the
   question.
6. **Copper 0.35 mm from the main board's edge** (the design notes said
   0.5; JLC accepts 0.3). Fine, just know it.

## Clean

- **Netlist.** All 423 pad nets match `circuit.py`; no channel or pin swaps
  were made while routing (the mux, 595 and header tables in `design.md`
  stand).
- **Connectivity.** Faceplate: 71 nets, 387 tracks, 29 vias, GND_F poured
  on both layers (two islands, both reached), GND_D_F as tracks and never
  touching GND_F on this board. Main board: 55 nets, 378 tracks, 46 vias,
  one GND pour per layer.
- **Headers.** HF1–HF3 over H1–H3: 26 pins, all within 0.01 mm.
- **Panel.** The export's 27 round holes equal `panel_pcb.py`'s to 0.01 mm
  (pot holes at the +4.0 mm shaft offset).
- **Footprints.** `POT-ALPHA-9MM-RD901F`, `DIP-14-W7.62-P2.54`,
  `RES-TH-VERTICAL-P2.54` on the main board, the library LR1F (10.3 mm)
  on the faceplate and for R60 / R61.
- **Keepouts.** Nothing but the two items above near a barrel or a
  standoff; no copper under a standoff on either board.
- **The nets that matter.** Every summing node IN_* is 8.7 mm on one
  layer, no vias. SPI_SCK 3 mm, SPI_MOSI 11 mm, LED_LATCH 11 mm, PROBE
  2 mm on the main board. ADC lines 15–76 mm with 0–3 vias (ADC_TRIG the
  longest at 76 mm). BIAS_A 84 mm as a tree with one via, BIAS_V 69 mm.
  OUT / AUX 69–70 mm. On the faceplate PROBE_F 86 mm (one via), the SPI
  lines 65–78 mm, the mux lines 40–52 mm.

---

## What you changed while routing (now the generator's layout)

The routed export is the placement master from here, as for Marblesy:
`pcb.py` reads the rear sides and the whole main board from
`Plaitsy-routed.epro2`, keeps the panel parts on `circuit.PLACEMENT`, and
`routed_check()` fails the exporter if they ever disagree.

- **Mounting holes: three, not four.** The centre hole at front (29.9, 48.5)
  is gone; C8 stands there now. Left: the two top corners and front
  (3.5, 30). The boards hang on three standoffs plus the jack nuts.
- **Faceplate:** C8 to (33.0, 50.5) vertical, C9 to (55.5, 76.5) vertical,
  the probe resistors R9–R13 down into the jack strip between the jack
  columns (R9 at x 47, R10 at 24, R11 at 12.5, R13 at 35.5, R12 in the
  left margin at x 58).
- **Main board:** the bias dividers 2.5 mm right and 1 mm down (R45–R48,
  C29, C30), the V/OCT clamps D21 / D22 vertical beside the breakout at
  x 25.5 (y 57–87), and R60 / R61 lying flat on the library footprint
  above the breakout at (10.4–20.7, 103.5 / 106.5) instead of standing.
  The exporter now stands up only the resistors the routed board stands
  up (`STANDING`), so R60 / R61 keep their flat footprint.

The generator's own checks on this placement: 0 problems except item 3
(R12 against J6's outline), which the fix list covers.
