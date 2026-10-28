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
- Previews: `marbles-easyeda-pcb-*.png`, rear view, red top / blue bottom /
  grey standoffs; look at them, the checker cannot see ugliness.

## Lessons

- Panel first. The first Marblesy placement passed every check and looked
  nothing like Marbles; the redo cost an hour.
- A footprint's origin is rarely the mechanical centre: jack barrel 0.78
  mm, pot shaft 0.53 mm, 3-lead LED on pad 2. Encode offsets once in
  `panel.py`.
- Keep decoupling next to the chip even when a tidy capacitor column looks
  neater.
- When a clearance report shows 0.05 mm overlaps between rows of parts,
  change the pitch (2.4 instead of 2.3) rather than nudging each part.
