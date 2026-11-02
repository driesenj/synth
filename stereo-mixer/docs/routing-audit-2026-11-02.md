# Stereo mixer routing audit, 2026-11-02

## Main board, `ProDoc_Mixer Main PCB_2026-11-02.epro2`: one thing to fix

The export holds the main board only; the faceplate is not routed yet.
`hardware/tools/copper_audit.py` (copied from Side FXy, with mixer
checks added) audited it against `circuit.py` and the generator's boards.
Coordinates below are EasyEDA's: the top layer (the rear) seen from above,
mm from the bottom-left corner.

**Fix: U7 pins 1 and 2 sit where the standoff goes.** Their pad edges are
2.74 and 2.79 mm from the centre of the mounting hole at (122.9, 4.8).
That is under the 3 mm keepout the routing notes ask for. The standoff sits
on this board's front, where U7's solder joints are:

- a 5 mm M3 hex reaches 2.89 mm at its corners, and a 5.5 mm hex 3.18 mm;
- the screw head on the rear is 2.75 mm.

A metal standoff would rest on both joints. That shorts QK1 to QN1 (Q and
/Q of channel 1's flip-flop), and the stack would not sit flat.

The cause was in the generated placement: U7 at (129.0, 12.0) was never
moved. `pcb.py` checked bodies against the standoff, and pads only against
the hole itself.

There are two ways out:

- Move U7 and C923 at least 0.7 mm up, away from the hole (1 mm to be
  safe), and re-route the few tracks to U7. There are 5.9 mm between U7's
  top pin row and U5's bottom one. QN1's bottom-layer track from pin 2 also
  passes 3.0 mm from the hole centre; it would move with the chip.
- Use a nylon standoff and a nylon washer at that corner.

**Everything else is clean.**

| Check | Result |
|---|---|
| Netlist | Every pad's net matches `circuit.py`. 133 of 155 parts moved while routing, but no net or footprint changed. |
| Connectivity | All 139 nets are complete. No shorts, and no track end that touches nothing. |
| Pours | GND on both layers: one island on the bottom, five on the top (four of them under 4 mm²). All of them are tied into one GND net. There are 220 stitching vias. No other net's copper lies inside a pour, so the fills are current. |
| Clearance | Nothing is under the 0.152 mm rule; the fab's minimum is 0.127. Four spots sit exactly on the rule and pass: −12V by PR5 at (21.7, 102.8), CH8L by H9.1, PR2 by the PR3 via at (99.0, 96.0), and LA8 by K9.4. Copper is at least 0.66 mm from the board edge. |
| Sizes | Signal tracks 0.3 mm; ±12 V and the protection nets 0.6 mm; all vias 0.3 / 0.61 mm. |
| Headers | H1–H9 were not moved. Every socket pin lies under the generator's faceplate pin, and the mounting holes are the same on both boards. Only sockets are on the front. |
| Power entry | D901 and D902 are the right way round: the 1N5819's pin 1 is the banded cathode, and D902's cathode is on the header's −12 V. C904 and C905 have + on pad 2, on +12V and GND. Both caps were turned while routing; their pad nets followed. |
| Decoupling | Each 100 n's rail pad has 2.5 mm of track to its TL074 supply pin, or 3.3 mm to its CD40xx VDD. Every GND pad is spoked into the pour. |

**Audio.** The routing follows the notes:

- **Summing nodes** (SUM_L 45 mm, SUM_R 61 mm, SUM_S 49 mm of track): the
  bus resistors stay grouped round U4 and U3. The only same-layer
  neighbours within 1 mm are PR1 and PR3, which feed SUM_R anyway (5 mm
  each). The NO nodes are 5 mm each.
- **FI nodes:** 5–9 mm each, with nothing beside them.
- **Side-by-side runs:** none between different nets within 0.6 mm.
  - At the 1.27 mm bus pitch there are long parallel runs, for example
    PR1/PR2 for 89 mm and PL2/PL4 for 68 mm. These are pan feeds heading
    for the same bus, so the coupling lands where the signal goes anyway.
  - Latch lines run next to their own channel's level line, for example
    LED5/LV5 for 34 mm. The latch is static: no clock on the board. Those
    lines only change when that button is pressed, and that press mutes
    the channel anyway.
  - The pairs with a real consequence are the stereo channels' L/R level
    wipers: LV8L/LV8R for 33 mm and LV7L/LV7R for 25 mm. At about
    0.025 pF/mm into a wiper of 25k at most, that is roughly −50 dB
    L/R crosstalk at 20 kHz and less lower down. Fine for this use.

**Harmless leftovers.**
- A tented GND via sits 1.96 mm from the hole at (27.1, 103.8), under that
  standoff. It is ground, so the standoff can touch it.
- R805's and C903's outlines overlap by 0.1 mm at one corner. The resistor
  body and the ceramic do not touch.

**Next.**
1. Fix U7: move it, or use nylon hardware at that corner.
2. Route the faceplate.
3. Export the whole project. It becomes the routed master, as with
   Marblesy and Plaitsy:
   - `pcb.py` then reads the main board's placement from it, since the
     generator's main board is now far from the routed one;
   - `copper_audit.py` re-runs on both boards.
