# Parts: measured facts and gotchas

Prefer Thonk (the user orders there); Tayda, Mouser, LCSC for the rest.
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
- Place at 11–12 mm pitch; nuts are about 8 mm across.
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
  figures in Marblesy's and Plaitsy's `panel.py` / `circuit.py` were wrong
  (their panel holes come out ~3.5 mm off the shafts, and `pcb.BODY`'s
  4 mm housing too short): fix those before ordering. The library's 9 mm
  drawing was about right.
- `stereo-mixer/hardware/tools/easyeda_export.py` `fp_alpha_pot()` generates
  Alpha single and dual footprints in the PTV09A's frame (lugs where the
  Alpha has them, real housing); use those. Panel hole 7.5 mm.
- CW rotation drives the wiper towards pin 3; put 3V3A on pin 3 and ground
  on pin 1 and the panel reads the right way round.
- Bring schematic wires into the lug pins 4/5 vertically or they cross a
  tab pin.

## Thonk low-profile LED button (datasheet LowProfileButton.pdf)

- 7.5 mm square body, 5.5 mm round cap, momentary; colours red, green,
  blue, yellow, orange, white and bipolar red/green (two leads, red one
  way, green the other). Used by Shakmat; sits at Thonkiconn height if the
  three plastic feet get holes.
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
that. Pick a height that puts the cap just proud of the panel (about 9.5 mm
for a 7 mm panel gap). The Thonk KS01-B "Highly Tactile" is 12 mm round and
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
- PDIP-14 (the TL074ACN library footprint) has its pad rows at ±4.445,
  8.89 mm apart: too wide for a 7.62 mm DIP socket. The mixer generates a
  standard 7.62 mm DIP-14 (`fp_dip`); Marblesy and Plaitsy still use the
  library one. DIP-16 pads 1.6 at ±3.81, body 20 × 6.6.
- DO-35: pads at ±4.0 (8 mm pitch), r 0.8.

## Chips

- TL074: pins 4 / 11 supply; one 100 n pair per chip placed beside it (not
  in a capacitor column 35 mm away).
- MCP4922 DIP-14: pins 2, 6, 7 unused; give the symbol NC pins or DRC
  complains about pads without pins. External 2.5 V reference (LM4040
  TO-92: 1 = +, 2 = −, 3 = NC) on VREFA/VREFB, shared LDAC.
- 74HC595 at 3.3 V: 2.5–3 mA per output into 470 Ω is fine; 74HC4051 for
  pots with channel 7 grounded if unused; 74HC165 for buttons with 10 kΩ
  pull-ups.
- Headers: 1×N 2.54 mm; one gender per side (male on the faceplate, female
  sockets on the main board); Thonk's "Male + Female Header Bag". Standard
  sockets give an 8.5 mm board gap: enough for DIPs and axial parts on the
  faceplate's rear, not for anything tall.
