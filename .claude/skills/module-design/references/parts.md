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
- Place at 11–12 mm pitch; nuts are about 8 mm across.
- Sleeve to the analog ground; CV inputs get the switch lug grounded, clock
  inputs get the normalization probe through 10 kΩ; outputs leave it open.

## Alpha 9 mm vertical pot (PTV09A, Thonk B10K etc.)

- Footprint `SW-TH_PTV09A-4015F-B502`: pins 1/2/3 at x = −2.5/0/+2.5,
  y = −3.5; lugs 4/5 at (±4.3, +3.5), pads 2.8 × 3.0. Origin 6.97 mm behind
  the pin row; the shaft is 7.5 mm behind it, so shaft = origin + 0.53 mm
  away from the pins. Panel hole 7.5 mm.
- Housing: 9.5 mm wide, ends about 4 mm beyond the origin (KiCad RD901F);
  the library drawing's 9 mm is far too long, override it.
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
  `SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod`). Generated footprint
  `SW-TACT-LP-LED-THONK`, feet as plated pads 7–9 so DRC sees pins for them.
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
