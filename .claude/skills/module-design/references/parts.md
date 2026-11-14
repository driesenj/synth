# Parts: measured facts and gotchas

Prefer Thonk (the user orders there); Tayda, Mouser, LCSC for the rest.

BOM: `hardware/tools/bom.py` (in marbles/, plaits/, side-fx/, stereo-mixer/;
copy it for a new module and rewrite its MODULE / BUTTONS / RATING / knobs() /
EXTRA / NOTES block; RATING maps a ref to (source, rating text) for a resistor
that needs more than 1/4 W, empty it for a new module) writes `docs/bom.md` and `hardware/bom/*.csv` from circuit.py,
with the Thonk lines in their own table and file. It fails if a netlist part
is not in exactly one line or the refs differ from the routed master's.
`bom/thonk_order.py` sums the modules' Thonk files into one order.
Library parts come from the user's EasyEDA library (cached in
`plaitsy/hardware/easyeda/morrissynth-parts.epru`, uuids in
`plaitsy/hardware/tools/easyeda_export.py` DEV/SRC); draw only what is
missing, in the same style, with real pin numbers.

## Thonkiconn jack (WQP518MA / PJ398SM / PJ301M-12)

- Library footprint `CONN-TH_WQP-WQP518MA`: pads 1 = sleeve (0, −5.7),
  2 = switch lug (0, −2.6), 3 = tip (0, 5.7); body 9 × 10.5 mm, drawn from
  −3.7 to +6.7 in y. Hole slots 1.3–1.5 × 0.6 mm; KiCad uses 1.4 mm round.
- Barrel centre = sleeve pad + 6.48 mm towards the tip = 0.78 mm below the
  footprint origin when the sleeve points up. Panel hole 6.5 mm. Keep
  non-ground copper 3 mm clear of the barrel on the panel side.
- With the sleeve up (bottom layer, angle 0) the drawn body runs from
  6.78 mm below the origin to 3.73 mm above it: the sleeve lug sticks out
  of the back of the body, and the strip above a jack row is wider than it
  looks (a row at origin y 22.8 ends at 26.6).
- The sleeve pad (1.8 × 1.1) reaches 7.03 mm above the barrel, past the
  body's 6.5: a rear pad row above a jack row has to clear the pad, not the
  body. Eight's Mega socket row was 0.13 mm into J1's sleeve pad until
  `circuit.front_bodies()` modelled the jack pads (`JACK_PADS`).
- Place at 11–12 mm pitch side by side; nuts are about 8 mm across.
- In a column with the same orientation, keep the barrels at least 13 mm
  apart. The tip pad sits 4.92 mm below one barrel and the next jack's
  sleeve pad 6.48 mm above its own, so at 11 mm they overlap (Envy's draft:
  −0.65 mm). Envy's `pcb.panel_pad_check()` catches a panel part's pad
  under another panel part's body (a jack's sleeve lug under a toggle).
- Or lay the column's jacks on their sides (Six, 4HP, 11 mm): the three
  pads then sit in a row through the barrel (tip 4.92 mm one way, sleeve
  6.48 mm the other, outside the body), the body runs 6.0 mm towards the
  tip and 4.51 mm towards the sleeve, ±4.5 mm across, and the 9 mm width
  sets the pitch. The origin is 0.78 mm from the barrel towards the sleeve
  in that direction; `buffered-mult/hardware/tools/pcb.py` `barrel_check()`
  works each barrel out from the placed pads and compares it with the hole.
- One board vs the stack: a rear through-hole part's pads cannot sit under
  a jack, pot or toggle body, so a dense panel leaves only strips. On Envy
  (16HP, three knob rows at 15.5 mm), a DIP-14 fitted only above the top
  knob row. Probe the free strips before promising one board.
- Sleeve to the analog ground; CV inputs get the switch lug grounded, clock
  inputs get the normalization probe through 10 kΩ; outputs leave it open.

## Alpha 9 mm vertical pot (RD901F single, RD902F dual-gang; Thonk)

- The Alpha part (KiCad `Potentiometer_Alpha_RD901F-40-00D_Single_Vertical`
  and `RD902F-40-00D_Dual_Vertical`): pins 2.5 mm apart in a row, the shaft
  **7.5 mm** from the pin row, the two mounting lugs on the shaft line at
  ±4.8 mm (dual ±4.75), housing 9.5 mm wide from 1 mm off the pin row to
  4.85 mm past the shaft. The dual's second gang is a second pin row 2.5 mm
  further from the shaft; both stand 9.5–10 mm tall, Thonkiconn height.
- Library footprint `SW-TH_PTV09A-4015F-B502` is Bourns' PTV09A: pins at
  y = −3.5, lug slots at (±4.3, +3.5), its own silk shows the shaft at
  +3.5. Its pin row is **3.5 mm** from the origin, so an Alpha shaft sits
  at origin **+4.0 mm** away from the pins, not +0.53. The 0.53 / 6.97 mm
  figures Marblesy and Plaitsy used were wrong (panel holes ~3.5 mm off the
  shafts, `pcb.BODY`'s 4 mm housing too short); fixed on 2026-10-30
  (`POT_SHAFT = 4.0`, `BODY` = the Alpha housing −4.75, −2.5, 4.75, 8.85).
  Marblesy's pots were re-routed onto the drawn layout (2026-10-30);
  Plaitsy's panel stayed put and its pots moved. The
  library's 9 mm drawing was about right. Its lug slots (2.2 × 2.0 mm at
  ±4.3, 0.5 mm towards the pins from the shaft line) are not where the
  Alpha's lugs are (±4.8 on the shaft line, KiCad: 2.72 × 3.24 pads, slots
  1.1 × 1.8 long towards the shaft), so a lug's corner overhangs the slot.
  None of the user's built boards has Alpha pots. Use the Alpha footprint:
  Plaitsy and the mixer draw it, Marblesy's re-routed boards carry it.
- `stereo-mixer/hardware/tools/easyeda_export.py` `fp_alpha_pot()` generates
  Alpha single and dual footprints in the PTV09A's frame (lugs where the
  Alpha has them, real housing); use those. Panel hole 7.5 mm.
- CW rotation drives the wiper towards pin 3; put 3V3A on pin 3 and ground
  on pin 1 and the panel reads the right way round.
- Bring schematic wires into the lug pins 4/5 vertically or they cross a
  tab pin.
- Values Thonk stocks (the user's paste of the shop list, 2026-10-31).
  Vertical T18:
  - B5K, B10K, B25K, B50K, B100K (also with a centre detent), B250K, B1M
  - A50K, A100K, A1M (A10K out of stock)
  - no B500K, no C tapers
  
  Alpha TALL trimmers: B10K, B100K, B1M, A10K, A50K, A100K, A1M, and
  centre-detent B10K, B50K, B100K. Pick from these before drawing a value,
  or scale the part beside the pot. The S&H wanted B500K for RATE and
  got B250K with its timing cap doubled instead.

## Thonk low-profile LED button (datasheet LowProfileButton.pdf)

- 7.5 mm square body, 5.5 mm round cap, momentary; colours red, green,
  blue, yellow, orange, white and bipolar red/green (two leads, red one
  way, green the other). Used by Shakmat; sits at Thonkiconn height if the
  three plastic feet get holes. Not confirmed: read off Thonk's drawing, the
  square base tops out 9.85–10.2 mm above the board, above the Thonkiconn's
  9.0 mm body, and the panel would rest on the buttons. Fit one beside a jack
  and lay the panel on them before soldering a module (Side FXy test report
  2026-11-13, M6).
- Pins (top view, EasyEDA y up): switch 1 (2.54, 2.54), 2 (−2.54, 2.54),
  3 (2.54, −2.54), 4 (−2.54, −2.54); contacts are 1+2 and 3+4. LED anode
  L1 = pin 5 (2.7, 0), cathode L2 = pin 6 (−2.7, 0). Feet: (−1.25, 1.75),
  (1.25, 1.75), (0, −2.25), 1.2 mm holes (Thonk's
  `SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod`). The two upper feet sit
  1.51 mm from pins 1 and 2: with 1.6 mm pads and 1.2 mm holes they overlap
  (EasyEDA DRC errors on Marblesy). Generated footprint
  `SW-TACT-LP-LED-THONK` now has pins 1–6 only and the build note says clip
  the feet (the body then sits on the board, at Thonkiconn height). Feet
  holes would only clear as NPTH with pins 1–4 shrunk to 1.3 mm round pads
  (0.26 mm), and tracks between pins 1 and 2 must then go round the feet.
- Panel hole 6.5 mm; a silk ring at r = cap + 1.6 looks like Marbles.
- Bipolar version between two 74HC595 lines with one 470 Ω on the red
  line: red = R high/G low, green = reverse, off = equal, orange = alternate
  the two at the 1 ms LED update. About 2.5 mA per lit LED.

## 6 × 6 mm tactile (TL1105 pattern)

Pins on a 4.5 × 6.5 mm rectangle; the two pins 6.5 mm apart are one
contact. Number pads so the pairs are 1+4 and 2+3 if the netlist expects
that. Pick a height that puts the cap just proud of the panel (its front is
about 10.6 mm above the board: the 9 mm Thonkiconn body plus a 1.6 mm panel). The Thonk KS01-B "Highly Tactile" is 12 mm round and
too big for a dense panel.

## LEDs

- 3 mm LEDs: 2-lead 2.54 pitch (pad 1 anode, pad 2 cathode, flat on the
  cathode side); 3-lead bicolour common cathode is 1.27 mm pitch with the
  cathode in the middle; Thonk does not stock the 3-lead ones (Tayda,
  Kingbright). A 2-lead bipolar needs the two-line drive above.
- Output indicators: gate outputs can drive an LED passively from the jack
  net through 3.3 kΩ (1.5 V lost across the 1 kΩ output resistor, gate
  still > 6 V). CV outputs must not be loaded that way (pitch error across
  the 1 kΩ); drive their LEDs from spare shift-register lines with PWM.
- Marbles puts an LED left of each output label, between the jack rows,
  4.2 mm left of the jack: that is the one strip the jacks leave free.

## Daisy Seed on Rob Heel's seed_power_opamps breakout

- Seed sockets 2.54 mm pitch, two rows 15.24 mm apart; the Plaitsy project's
  footprint had 2.0 mm pitch, wrong. The corrected 56-pad footprint
  `DAISY-SEED-POWER-OPAMPS-2.54` is in `marbles/hardware/easyeda/Marbles.epro2`.
- Breakout headers in line with the socket rows: J1 (GND, −12 V × 3) and J3
  (GND, +12 V × 3) beyond pins 20/21 with one empty position; J5 (audio
  in) and J4 (audio out) beyond pins 1/40. The breakout ties AGND and DGND
  and feeds VIN from its DC/DC; the module boards take ±12 V from J1/J3.
- Breakout board 96.7 × 18.8 mm, longer than a 90 mm board is wide: mount
  it vertically, power end down, pin field centred where the pads clear
  the sockets and holes.
- Pin map used by Marblesy: D0/D1 clocks, D2–D4 gates, D7–D10 SPI1 (NSS,
  SCK, MISO, MOSI), D11–D14 CS2/LDAC/LED latch/button load, 20 AGND, 21
  3V3A, 22 A0 probe, 23–28 and 31 ADC, 32 A10 mux out, 33–35 mux S0–S2, 38
  3V3D, 40 DGND.

## Library passives (measured from the footprints)

- LR1F resistor: pads at ±5.15 (r 0.76), body 6.2 × 2.3. Vertical, 2.4 mm
  pitch, gives 0.88 mm between pads.
- FG28 100 n / 1 n / 100 p (`CAP-TH_L3.0-W2.0-P5.08`): 5.08 mm pitch, not
  2.5; pads 1.8, body 6.9 × 2.3. Vertical caps in a column need 7.5 mm
  steps.
- SR305 1 µ: 5.08 mm pitch, body 7.6 × 3.8.
- PDIP-14 (the TL074ACN library footprint, `...LS9.0-BL`) has its pad rows
  at ±4.445, 8.89 mm apart: no DIP socket fits, and the user had to bend
  the chips' legs on the Kick, Mixer and Output boards. The MorrisSynth
  project also has `PDIP-14_..._LS7.6` (rows 7.62, on FM, Snare, Tom, Hi-hat),
  but it is not in the cached library. Use `fp_dip(14, "DIP-14-W7.62-P2.54")`
  (mixer, Plaitsy, Marblesy after its re-route). DIP-16 pads 1.6 at ±3.81,
  body 20 × 6.6.
- DO-35: pads at ±4.0 (8 mm pitch), r 0.8.

## Chips

- TL074: pins 4 / 11 supply; one 100 n pair per chip placed beside it (not
  in a capacitor column 35 mm away).
- MCP4922 DIP-14: pins 2, 6, 7 unused; give the symbol NC pins or DRC
  complains about pads without pins. External 2.5 V reference (LM4040)
  on VREFA/VREFB, shared LDAC.
- LM4040 in TO-92: the middle lead (pin 2) is the cathode (+). TI's tables
  disagree on whether the anode is pin 1 or pin 3 (the other NC), so wire
  pins 1 and 3 both to the anode net; then either table, and either way
  round, works. SOT-23 is different: 1 cathode, 2 anode, 3 NC or anode.
  Two modules got the SOT-23 order on a TO-92 and had to be fixed.
- 74HC595 at 3.3 V: 2.5–3 mA per output into 470 Ω is fine; 74HC4051 for
  pots with channel 7 grounded if unused; 74HC165 for buttons with 10 kΩ
  pull-ups.
- Headers: 1×N 2.54 mm; one gender per side (male on the faceplate, female
  sockets on the main board); Thonk's "Male + Female Header Bag". Standard
  8.5 mm sockets on the male headers' 2.5 mm plastic give an 11 mm board
  gap (order 11 mm standoffs), less the main board's solder tails: enough
  for DIPs and axial parts on the faceplate's rear, not for anything tall.
- Eurorack power header (Doepfer A-100, 2.54 mm IDC, pin 1 = red stripe,
  odd pins one row, even the other): 1–2 −12 V, 3–8 GND, **9–10 +12 V**,
  11–12 +5 V, 13–14 CV, 15–16 Gate. A 10-pin cable carries pins 1–10 only,
  which works on a 16-pin header because +12 V is on 9–10. On a 16-pin
  header leave 11–16 open unless the module uses +5 V, CV or Gate, and say
  so on the schematic. Until 2026-11-14 six generators had GND on 3–10 and
  +12 V on 11–12, which shorts the bus's +12 V to ground; copy this table,
  not an older `power_main()`.
- H11L1 (MIDI in at 3.3 V; works from 3 V): DIP-6, 1 anode, 2 cathode, 3 NC,
  4 open-collector output (idles high), 5 GND, 6 VCC. Give the symbol pin 3.

## EC11 encoder with switch (Side FXy)

KiCad `RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm`, in its own frame (y
down, origin on pad A): A (0, 0), C (0, 2.5), B (0, 5), S2 (14.5, 0), S1
(14.5, 5), mounting tabs MP (7.5, −3.1) and (7.5, 8.1), 3.2 × 2 pads with
2.8 × 1.5 oval slots; shaft at (7.5, 2.5); body 12 × 11.6. The phase pins
sit 7.5 mm from the shaft, the switch pins 7.0 mm on the other side.
`side-fx/hardware/tools/easyeda_export.py` `fp_ec11()` moves the origin onto the shaft and names
the tabs MP1 / MP2 (EasyEDA wants unique pad numbers). Thonk doesn't sell
EC11s; Tayda and Mouser do. Bourns PEC11R: the same pins, but not the same
tabs. Its layout asks for 1.8 × 2.6 mm tab holes 4.8–6.6 mm from the shaft
(centres 11.4 apart; the drawing's 13.2 is across the outer edges), past
KiCad's 1.5 mm slots at 4.85–6.35 (Alps EC11E: 1.5 × 2.6 at 4.75–6.25).
Slots 2.0 mm along the tab line, centred 5.65 mm from the shaft, take both.
Height: the EC11E and the PEC11R-4215F (5 mm bushing) reach 11.5 mm above
the board, under 1 mm of thread in front of a 1.6 mm panel at the 9 mm
Thonkiconn gap, too short for the nut; a 7 mm bushing (PEC11R-4220F, read
off Bourns' drawing) leaves about 2.9 mm (Side FXy test report 2026-11-13).

## Stereo Thonkiconn (QingPu PJ366ST)

Three pins in the mono jack's row, no switches: sleeve, ring where the mono's
switch lug is, tip (KiCad frame 0 / 3.1 / 11.4 mm). In the library
WQP518MA's frame: 1 sleeve (0, −5.7), 2 ring (0, −2.6), 3 tip (0, 5.7), so
the barrel offset (0.78 mm) and the panel hole are the mono jack's. Slots
from KiCad merge request 1073 (closed, not merged): S 1.9 × 0.68, R 2.1 ×
0.68, T 2.0 × 0.57, slightly longer than the mono's. `fp_pj366st()` in the
Side FXy exporter.

## Dailywell 2MS sub-mini toggle (Thonk; Atlas, Offset)

Dailywell's 2MS sheet: SPDT 2MS1 (ON-ON) and 2MS3 (ON-OFF-ON), DPDT 2MD.
- **Mounting:** 6.00 mm bushing, panel hole 6.5 mm (nut and washer on
  the panel).
- **Pins:** PC terminals (M2) at 2.54 mm in one row, 0.51 mm thick; body
  about 8.1 × 9.4 mm.
- **Positions:** 2MS1 joins 2-3 in position 1 and 2-1 in the other; DPDT
  2-3 + 5-6, then 2-1 + 5-4. Ring one out before soldering a set.
- **Footprint:** `fp_toggle()` in `attenuverter/hardware/tools/easyeda_export.py`
  puts the three pins in a column at 2.54 mm, 1.1 mm holes, common under
  the bushing. Mounted with pin 3 at the bottom, lever up joins 2-3.
- **Library:** the user's library holds only the Nidec ATE1D, which has no
  panel nut.

## SMD (first used on Atlasy, 2026-10-31)

- When a module's rear circuitry needs more than one through-hole main
  board (Atlasy: about 2.8 boards at the mixer's density), SMD on the rear
  of each board, assembled by JLC, keeps it to faceplate + main board.
  Panel parts and headers stay through-hole and hand-soldered.
- Packages and pad geometry (copied from the LCSC footprints in the user's
  MorrisSynth export): SOIC-16 narrow pads 0.60 × 1.97 oval, rows at
  ±2.736, 1.27 pitch, pin 1 bottom-left; SOIC-14 the same with 7 per side;
  SOT-23 pins 1 / 2 at (+1.15, ∓0.95), pin 3 at (−1.15, 0), pads 1.0 × 0.8;
  0603 pads 0.8 × 0.95 at ±0.8; 1206 pads 1.0 × 1.75 at ±1.5; SOD-123 pads
  0.91 × 1.22 at ±1.635, pin 1 = cathode (band). Generators:
  `atlas/hardware/tools/easyeda_export.py` (`fp_chip`, `fp_soic`,
  `fp_sot23`, `fp_sod123`).
- **SOT-23 transistors number their pins 1 B, 2 E, 3 C**, not the TO-92
  C B E of the library footprint. Write the netlist in the package's
  numbering.
- Device attributes: clone the LR1F / FG28 attribute sets, set
  `Manufacturer Part` (UNI-ROYAL `0603WAF{code}T5E`, the code following
  from the value; Samsung CL10… / CL31…) and leave `Supplier Part` empty
  for JLC's BOM matcher unless the LCSC number is known for certain.
- Dailywell 2M sub-mini toggles (2MS1 SPDT ON-ON, 2MD6 DPDT ON-ON-ON):
  catalogue contact table 2MS1 2-3 / 2-1; 2MD6 2-3 + 5-6, 2-3 + 5-4,
  2-1 + 5-4; lever up joins the lower pins. PC terminals .110 in apart,
  poles .200 in; 6 mm bushing, 6.5 mm panel hole. Not yet checked against
  a real part.
