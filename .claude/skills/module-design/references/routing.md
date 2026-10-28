# Routing notes (hand-routing in EasyEDA Pro with autorouter help)

The user routes in EasyEDA Pro: autoroute first, then fix the nets that
matter. Give them this, adapted to the module, before they start; the
Marblesy version is in `marbles/docs/design.md`.

## Before the autorouter

- Rules: the generated project inherits the rules of one of the user's
  older boards (0.1 mm clearance). For hand soldering: clearance 0.25 mm,
  track 0.3 mm, POWER net class 0.6 mm (±12 V, 3V3A, 3V3D and their _F
  twins), via 0.8 / 0.4 mm, copper 0.5 mm from the edge.
- Keepouts: 3 mm at each jack barrel on the panel-side layer (ground copper
  may stay); 3.5 mm around mounting holes on the standoff side.
- Hand-route and lock: power buses, the SPI bundle, summing nodes and
  references. Then autoroute the rest.

## Autorouter settings

Both layers; preferred direction vertical on top, horizontal on bottom
(tall boards, long vertical runs); 45° corners; via quantity "less";
"completion first", then re-run ugly nets selected with "quality first".
Skip nets: all grounds and the POWER class. Afterwards remove loops, DRC,
pour.

## Ground planes

- Main board: one GND, poured on both layers; the socket side is nearly
  empty and is the plane. Must reach Seed pins 20 and 40 and the breakout's
  GND pins; the breakout joins AGND and DGND, no split.
- Faceplate: analog GND_F (jacks, pots, mux, passive gate LEDs) poured on
  the panel-side layer under everything, shielding the CV lines; digital
  GND_D_F (logic, LED buttons, PWM LEDs) as a small rear-layer pour or
  tracks. They never touch on the faceplate; they meet on the main board's
  GND through separate header pins.

## Nets that need care

Main board: op-amp summing nodes and ADC lines (one layer, short, over the
pour, away from digital); BIAS / VREF / NEG_REF as short trees from their
capacitors; the SPI bundle down the channel between the breakout's pad rows
and east along a free corridor to the DACs, picking up the faceplate header;
clock in/out along the top edge with pour between them and the top op-amp's
summing nodes; gates on the bottom layer with pour around; power as 0.6 mm
buses up the decoupling column; DAC outputs kept off SCK.

Faceplate: pot wipers and mux lines on the panel side under GND_F; the CV
inputs' long runs to the top header on the panel side in the centre and left
corridors, never alongside LED lines; external clock inputs in the outer
margins; SPI and the shift-register chain short on the rear; LED lines (PWM,
2.5 mA) on the rear, bipolar pairs together, away from wipers and CV; output
lines down the margins; LED buttons and PWM LEDs to GND_D_F, passive gate
LEDs to GND_F.
