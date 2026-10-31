# Placement: frames, stack, checks

## The stack and its frames

```
 panel (91.3 x 128.5 for 18HP)  front
   faceplate board (FB)         bottom layer = panel parts; top layer = logic, male headers
   8.5 mm gap, M3 standoffs
   main board (MB)              bottom layer = female sockets only; top layer = everything else
   Seed breakout on the MB's rear, on sockets
```

- `PLACEMENT` in `circuit.py`: board frame, front view, x right, y up,
  origin bottom-left, mm. Footprint origins. `panel.py` turns these into
  panel holes (panel frame: from the top-left, y down; board centred on
  the panel: panel_x = x + (PANEL_W − BOARD_W)/2, panel_y = PANEL_H −
  ((PANEL_H − BOARD_H)/2 + y)).
- PCB frame (both boards): rear view, x_pcb = BOARD_W − x_front, y the
  same. Both PCBs share this frame, so a header pair has identical
  coordinates on both boards and `header_check()` confirms pin by pin.
- A part's angle on the bottom layer is found by `Board.orient(ref, rule)`:
  try 0/90/180/270 with EasyEDA's mirror rule and keep the first whose
  front-view pad positions satisfy the rule (jack sleeve above the tip;
  pot pins in a column towards −x; LED pads along x with pad 1 left; LED
  button LED pins along x, anode right).

## Where things go (what worked on 90 × 108 with a Marbles layout)

Faceplate rear (top layer), pads-only keepouts because the panel parts'
housings are on the other side:
- The strip between the CV jack row and the lowest knobs (y 29–40): two
  DIP-16 horizontal plus their caps and vertical headers.
- Pockets either side of the centre knob: DIP-16 vertical.
- Rows beside the big knobs and columns beside the small buttons:
  resistors (10.3 mm pitch axial = 12.1 mm pad span, 2.3 mm body).
- The strip above the top knobs: horizontal headers.
- Margins are 8 mm wide once the pots' lug pads (x ± 5.7) are respected.

Main board top (rear):
- Breakout vertical along one edge (x 1.6–20.4), pad rows at x 3.4 and
  18.6; the channel between the rows is free on both layers (sockets,
  standoff holes, SPI highway).
- TL074 column vertical at x 29, 20 mm pitch, decoupling pairs in the
  channel at x 22, resistors in horizontal columns at 13 mm pitch (41.5,
  54.5, 67.5), six rows of 2.54 mm per block, feedback caps vertical beside
  them (3 mm column pitch), DACs bottom right, clock stages in the right
  strip, reference parts next to the DACs.
- Sockets wherever the faceplate's headers landed; check them against the
  resistor columns (a vertical socket at x 74 collided with column c).

Mounting holes: four, identical on both boards, each needing 3 mm of free
board on the standoff side and a screw head's room on the other side. Good
spots were the centre line between knobs and the gap between a BIAS knob
and a mode button; a hole in the breakout's pad row is impossible, between
its rows is fine.

## Checks (in `pcb.py`)

- Pads of different parts ≥ 0.25 mm apart (circle approximation), pads ≥
  0.5 mm from the edge, pads ≥ 0.25 mm from holes.
- Housings on the same side must not overlap (drawn body = silk + document
  layers, pads excluded; override `BODY` for footprints whose drawing is
  wrong). Panel-part housings vs rear parts do not interact.
- Nothing on the standoff side within 3 mm of a mounting hole.
- Every part placed once; every pin's pad exists in the footprint.
- Rear-side pads of the faceplate must not fall inside a panel part's
  housing box (`front_housing_check` in `plaits/hardware/tools/pcb.py`):
  they are soldered on the panel side, where the pot and jack bodies lie
  flat. Headers in particular: a vertical header beside a pot column has
  to clear the lug pads (2.8 × 3.0, so r 1.5 in the circle check) and the
  housing, which on a 12HP board leaves only the outer 1.7 mm of margin.
- Previews: `marbles-easyeda-pcb-*.png`, rear view, red top / blue bottom /
  grey standoffs; look at them, the checker cannot see ugliness.

## Lessons

- A placer for any footprint, with no order dependence. It is in
  `sample-hold/hardware/tools/pcb.py`; copy it, don't import it, because
  other sessions edit sibling modules.
  - The Offset's grid placer assumes two-pin parts on 2.54 or 5.08 mm.
    `place_auto()` test-fits each candidate spot on the real footprint
    (pads vs pads, edge and front bodies; body vs rear bodies), so 8 mm
    DO-35s, DO-41s, TO-92s and fat film caps go through it too.
  - `improve()` then lifts each part and re-places it until a round moves
    nothing. Greedy order otherwise decides who gets the good spots: on
    the S&H the trigger chain took the corner by the header and pushed the
    power entry and a decoupling cap away.
  - Keep a block in its area with `REGION` boxes (power entry beside the
    header).
  - Keep clock pads away from a sensitive input with a distance penalty
    (`NOISY` / `QUIET`).
  - Measure the result: ratsnest length, crossings, decoupling distance.
    Look at a front view with ratsnest; the rear-view preview hides
    connections.

- Do the user's routing moves before handing over (done on Plaitsy,
  `plaits/hardware/tools/pcb.py` `_stage()` and `circuit.py`):
  - Main board: every resistor standing (2.54 mm, `fp_res_vertical`), each
    inverting stage a cluster at its corner of a vertical TL074 (Rf on
    IN−/OUT, Rin and Rs one column out, Cf the next), the 100 n between two
    stages' Rf, 3.6 mm from the supply pin. Summing nodes went from
    23–48 mm to 8.7 mm.
  - Order header pins, mux channels and 595 outputs by brute force for the
    fewest crossing straight lines (pin to nearest pad of the net, both
    boards for headers), length as tie-break, each supply pin beside its
    ground: 8! or 9! orders run in seconds. Plaitsy's faceplate went from
    197 ratsnest crossings to 95, the main board from 368 to 120.
  - Bicolour LEDs in a column have red and green anodes on opposite sides:
    give one 595 all the reds on its side and the other all the greens, and
    point each resistor's 595 end at its chip.
  - Measure before and after (crossings, summing-node span, decoupling
    distance); the scripts lived in the session scratchpad, rebuild them
    from this description.

- What the user changed when routing Marblesy (worth proposing up front next
  time): headers moved to the side edges beside the jack rows (CV runs a
  few cm instead of the board's height), split by function (7 short headers
  instead of 5 long ones); the breakout centred on the main board with the
  op-amps at the four corners; 33 resistors stood up on a 2.54 mm footprint;
  mux channels and 595 outputs swapped to untangle the faceplate.
- Designators can repeat across boards (Marblesy has R80–R85 on both).
  Keep part info per board: the exporter once gave the faceplate's 470 R
  the main board's 100k devices.

- A display module behind the panel (Side FXy, `side-fx/hardware/tools/pcb.py`):
  it lives in the panel gap, glass against the panel, and nothing with leads
  may sit on the faceplate behind it (the soldered ends press into its back).
  Model it as a front-side keep-out (`Board.keepout_front`, checked by
  `front_housing_check`), mill a cutout under its rear connector
  (`cutout_front`, a layer-12 region) and land the cable on a right-angle
  header so the Dupont plug lies flat in the 8.5 mm board gap. The keep-out
  ate so much faceplate that the 74HC595 moved to the main board. A Waveshare
  module's M2 holes sit under the glass: tape it, don't screw it.
- The breakout stands on its sockets: screw heads may sit under it (Side
  FXy puts two holes and two header sockets in the channel between its rows),
  so the screw-head check skips its body.
- Jack sleeve lugs reach 2 mm above the jack body: a DIP strip above a jack
  row needs its pins at least ~7.5 mm above the jack origins' row.
- Panel first. The first Marblesy placement passed every check and looked
  nothing like Marbles; the redo cost an hour.
- A footprint's origin is rarely the mechanical centre: jack barrel 0.78
  mm, Alpha pot shaft 4.0 mm from the PTV09A origin (Marblesy's 0.53 was
  wrong), 3-lead LED on pad 2. Encode offsets once in `panel.py`, and check
  them against the part's KiCad footprint or datasheet, not a footprint
  drawing alone.
- Dense console-style panels (the stereo mixer, 13.5 mm columns): pots pins
  down, headers standing in the strips between the columns, label each row
  once with a dotted line along it rather than every knob (the user's call).
- Keep decoupling next to the chip even when a tidy capacitor column looks
  neater.
- When a clearance report shows 0.05 mm overlaps between rows of parts,
  change the pitch (2.4 instead of 2.3) rather than nudging each part.
- Count resistor slots before promising a layout. On the 12HP Plaitsy
  faceplate the 16 LED resistors plus 5 probe resistors only fit as
  vertical parts (12.1 mm pad span, 2.4 mm pitch) in rows either side of
  the LED column, and the two button-LED resistors had to move to the main
  board. Three DIP-16s do not fit side by side in 59.4 mm.
- A 59.4 mm main board holds the breakout (18.8 wide) plus one TL074
  column and one horizontal resistor column (x 43.5) and one capacitor
  column (x 52.5); the second resistor column of the 18HP layout is gone,
  so everything else goes in 2.5 mm rows of that one column.

## SMD placement (Atlasy)

`atlas/hardware/tools/pcb.py` has `Placer`: a 0.25 mm occupancy grid per
board side, edges, standoffs (3 mm) and through-hole pads (+0.6 mm for the
iron) taken; each part goes to the nearest free spot round the centroid of
the placed pads it shares a signal net with, two-pin parts turned to point
along their nets. Place panel parts, headers, holes and chips by hand,
decoupling pairs at the supply pins (`place_decoupling`), then the rest in
netlist order (`place_all`). `Board.check()` also flags an SMD body over a
through-hole pad; `front_housing_check()` only looks at through-hole pads.

## One board (Offset, the user's default since 2026-10-31)

"One board is always simpler and cheaper if possible." Panel parts go on
the front (bottom layer), everything else on the rear (top layer). There
are no headers or standoffs: the panel nuts hold the board.
`attenuverter/hardware/tools/pcb.py` is the template.
- **The binding rule:** no rear pad under a front part's body, because rear
  leads are soldered on the front. Pot, jack and toggle bodies cover most of
  a 10HP board. Only full-width strips between rows of front parts can take
  a DIP, which needs about 9.2 mm of height free of bodies.
- **Count DIPs per strip before promising a chip count:** on Offset, two
  DIP-14s in the top strip, and only DIP-8s between the LEDs. That is why
  channel 3 has two TL072s.
- **Small parts:** `place_grid()` puts standing resistors and 5.08 mm caps
  on a 2.54 mm grid of the free points nearest the pads they connect to:
  - decoupling pairs first, anchored to their own chip's supply pins
  - summing nodes weighted ×3, GND ×0.2
  - grid points kept 1.2 mm from rear bodies, since a standing resistor's
    body reaches 1.1 mm past its pad
- **DO-41 diodes:** the library footprint's drawing reaches 2.84 mm to one
  side. In a narrow margin, pick the side by the diode's polarity, or the
  body pokes off the board.

## Narrow modules (Six, 4HP)

`buffered-mult/hardware/tools/pcb.py` is the template for a stack on an
18.8 mm board.
- **One column of jacks, on their sides** (parts.md): 11 mm pitch, the tip
  pads in a line on one side of the bodies, the sleeve pads on the other.
- **No standoffs:** a 6 mm standoff circle does not fit beside a 10.5 mm
  jack body. Instead, four headers hold the main board: per group, the
  tips on a 1×4 by the tip pads, and GND plus the LED on a 1×2 between two
  sleeve pads.
- **Main board, 18.8 × 108:** the following fit with Envy's greedy placer:
  - two DIP-14s down the middle (pin rows at x ±3.81)
  - a standing 16-pin box header at the bottom (9 × 28.6 mm)
  - 26 standing resistors and 12 caps
  It only fit once the 10 p caps moved to a 2.54 mm footprint. Place the
  power entry before the groups, each group in its own band.
