# Stereo mixer routing audit, 2026-11-02

## Third export, `ProPrj_SI Mixer_2026-11-02(2).epro2`: clean, labelled; rebuild the faceplate pour

**What changed.** Only DRW_F and SEND_F, both re-routed on the panel side
round the barrels. The main board is identical to the second export.

- SEND_F no longer comes within 3 mm of J11's barrel.
- DRW_F's edge is now 1.60 mm from J14's barrel centre. That is outside
  Thonk's 3 mm circle (1.5 mm radius), though inside the 0.25 mm margin
  the audit adds, so the audit still lists it. It is fine as it is.

Both boards still have every net complete, no shorts and nothing under
0.152 mm. Headers, holes and the panel still match.

**Rebuild the faceplate's copper areas before making Gerbers.** The
faceplate's pour fills (POURED) are exactly the second export's: the same
six islands, with the same areas. The re-routed tracks therefore sit inside
the old GND_F fill on the panel side. These five segments are the ones
inside it:

- DRW_F (27.9, 47.1)–(25.0, 50.0) and (25.0, 50.0)–(18.9, 50.0);
- SEND_F (22.4, 77.5)–(19.0, 77.5), (19.0, 77.5)–(14.4, 82.1) and
  (14.4, 82.1)–(14.4, 91.3).

The fill also still has the cutouts where the old tracks ran. Rebuilding
all copper areas in EasyEDA clears both. The tracks themselves are clean;
only the stored fill is out of date.

**Value labels.** `hardware/tools/value_labels.py`, copied from Side FXy,
added 148 silkscreen strings. Every other record is byte for byte the
export's, and the audit gives the same result with or without them.

| Board | Labels |
|---|---|
| Main board | 119 on parts: every resistor and capacitor, plus 1N5819 ×2 and 1N4148. 6 parts share 4 legend lines: "10k: R301 R401" by U1, "10k: R701 R702" by U2, "100k: R304" and "100n: C918" by U4. |
| Faceplate | 25 pots on the panel side: 19 A100k and 6 B10k. The PAN pots are the B10k ones, so they cannot be swapped by accident. |

On the main board the six tightest labels sit as near another resistor as
their own: R204, R404, R608, R709, R901 and R916. Previews:
`hardware/easyeda/stereo-mixer-labels-main-top.png` and
`-faceplate-bottom.png`.

The labelled file is the committed `StereoMixer-routed.epro2`. Import it,
rebuild the copper areas, run DRC, then make the Gerbers.

## Second export, `ProPrj_SI Mixer_2026-11-02(1).epro2`: two tracks to move

This export is the whole project, with both boards routed. It is now
`hardware/easyeda/StereoMixer-routed.epro2`, the layout master, and
`copper_audit.py` audits it by default.

**Main board: U7 is fixed.** U7 moved 2.5 mm up, to (129.0, 14.5). Its
nearest pad is now 5.19 mm from the hole at (122.9, 4.8). Its tracks were
re-routed:

- CK1, CK2, QK1, QK2, QN1, QN2, POR and +12V;
- three GND vias under the chip are gone.

Nothing else moved. All 139 nets are still complete, with no shorts and
nothing under 0.152 mm. C923 stayed put, so it is now 4.3 mm of track from
U7's VDD pin; that is fine.

**Faceplate: routed and clean, except two plug-tip spots.**

| Check | Result |
|---|---|
| Netlist and placement | Identical to the generator: no part moved, no net changed. |
| Connectivity | All 79 nets are complete, with no shorts. The board has no vias: GND_F is poured on both layers, one piece on the rear and six on the panel side, all joined through the pot lugs, jack sleeves and header pins. |
| Clearance | Nothing is under the 0.152 mm rule; the nearest gaps are 0.154 mm. Copper is 2.65 mm from the edge. Nothing is within 3 mm of a mounting hole. |
| Headers | All nine headers line up pin for pin with the main board's sockets, and the holes are the same. |
| Crosstalk | The longest side-by-side run within 1 mm is MIX_L_F / MIX_R_F for 17 mm. Both are op-amp outputs, so it does nothing. |
| Panel board | All 50 holes and 4 slots match `panel_pcb.py`. |

**Move: DRW_F and SEND_F cross other jacks' plug-tip spots.** A fully
inserted plug's tip reaches the panel-side copper under the jack. Thonk
asks for a 3 mm hole there, or no copper.

- DRW_F, the DRUMS level wiper on its way to HF9.5, runs 0.20 mm from the
  centre of J14 (FX IN). A worn spot in the mask would put whatever is
  patched into FX IN onto the drums line.
- SEND_F, from J15 to HF9.1, passes 1.63 mm from J11 (RETURN L). Through a
  worn mask, the send output would feed straight into the return, a loop
  round the effect.

The fix is a few clicks in EasyEDA:

1. Select DRW_F's two segments and SEND_F's four, and put them on the top
   layer. Each net runs pad to pad with no via, so nothing else changes.
   On the top they keep at least 2.2 mm from every other track.
2. Rebuild the copper areas and export again.

The other tracks near a barrel are the jack's own tip or switch net: J12,
J13 and J17. A plug touching those is harmless.

The GND_F pour lies under the tip spot of the other 16 jacks. A worn spot
there would only short that plug's signal to ground, which damages
nothing. Leave it, or put a small no-copper circle at each spot if you
want to follow Thonk to the letter.

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
