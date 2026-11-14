# Marblesy hardware test suite, 2026-11-13

A hardware design test suite for Spore (Marblesy), modelled on the stereo
mixer's of 2026-11-04. It has eight test groups in `hardware/tests/`, which
four agents wrote and ran, two groups each. Two independent verifiers then
re-derived every failing check from the primary sources. They fixed the
test bugs they found: checks that compared a constant with itself, checks
that could not fail, limits read at the wrong conditions, and figures
interpolated where a datasheet gives the real one.

Everything is checked against each other: `circuit.py`, the routed master
`Marblesy-routed.epro2`, `design.md`, `bom.md`, the firmware in
`firmware/src/`, the Daisy Seed breakout's own BOM and Gerbers, and the
manufacturers' datasheets. The suite only reads. **M1 and M2 were applied
on 2026-11-13, see [Applied](#applied-m1-and-m2); L3, L8, L14 and part of L17
on 2026-11-14, with L7 left as a route for you, see
[Copper rework](#copper-rework-2026-11-14). Your re-routed export of the same day
is the master now, with three library fixes EasyEDA had undone put back, see
[Re-import](#re-import-2026-11-14).**

```bash
cd marbles/hardware/tests && python run_tests.py
```

| Group | First run (checks / failing) | After verification | After M1 + M2 | After the copper rework | After the re-import | Second re-import (2026-11-15) | What it covers |
|---|---|---|---|---|---|---|---|
| netlist | 146 / 5 | 146 / 5 | 146 / 5 | 146 / 4 | 146 / 4 | 146 / 4 | circuit.py on its own, pinouts and polarity against datasheets, every routed pad's net, header stacking, both projects' schematic pages, design.md's tables |
| firmware | 66 / 4 | 66 / 4 | 66 / 3 | 66 / 3 | 66 / 3 | 66 / 3 | pin, LED, button, mux and DAC tables traced through the routed copper and libDaisy v9.0.0; MCP4922 command words; SPI timing at 3.3 V; logic polarity; calibration constants |
| analog_dc | 229 / 35 | 239 / 45 | 240 / 13 | 240 / 10 | 240 / 10 | 240 / 10 | CV inputs into the Seed's ADC and over-range, pots through the 4051, the LM4040 and the −2.5 V inverter, the DAC stages (worst case and Monte Carlo) and the output calibrator, gate outputs, clock inputs and the probe |
| analog_ac | 67 / 8 | 68 / 1 | 68 / 1 | 68 / 1 | 68 / 1 | 68 / 1 | CV input bandwidth against the firmware's filters, ADC sampling and mux settling, output-stage phase margin, slew, noise, gate edges, clock-input delays |
| power | 218 / 20 | 218 / 19 | 218 / 14 | 218 / 6 | 218 / 6 | 218 / 5 | the breakout's power entry (traced from its Gerbers), reverse protection, the DC/DC, current per rail, decoupling paths, power tracks, sequencing and missing-rail faults |
| pcb | 157 / 11 | 159 / 12 | 159 / 10 | 159 / 12 | 159 / 13 | 159 / 10 | footprints against datasheets and the breakout's Gerbers, drills and rings against JLCPCB, outlines and standoffs, panel parts, value labels, real bodies, the stacking gap, pours |
| panel | 156 / 1 | 156 / 1 | 156 / 1 | 157 / 0 | 157 / 0 | 157 / 0 | holes in every representation against the routed faceplate, Eurorack mechanics, front clearances, depth, labels, the house panel frame |
| bom | 237 / 3 | 237 / 3 | 240 / 5 | 243 / 5 | 243 / 3 | 243 / 3 | bom.py against circuit.py, the committed BOM files and the routed boards; part numbers, ratings, Thonk parts, headers, sockets, standoffs |
| **all** | **1276 / 87** | **1289 / 90** | **1293 / 52** | **1297 / 41** | **1297 / 40** | **1297 / 36** | |

After verification, 90 failing checks make 22 findings below: two medium,
17 low (L16 and L17 each bundle several small ones) and three docs-only.
One cause can fail one check per channel or per input voltage: M1 alone
fails 38.

**None is high severity for Marblesy: nothing found needs copper changed
before ordering.** Two findings are medium and must be settled before the
boards are built: a value swap for the CV inputs, and leaving the faceplate's
four DIP-16 sockets out. The copper audit is clean, as before: no splits, no
shorts, nothing under 0.152 mm.

What holds, in short:
- **Pads and pinouts:** every routed pad on both boards matches circuit.py.
  Every IC pinout matches its datasheet, the LM4040 fits either TI pinout,
  and the pots turn clockwise.
- **Headers:** the stacking carries all 33 used pins.
- **Firmware:** its tables reach the right jack, knob, button and LED through
  the routed copper.
- **The breakout:** all 56 footprint pads land on its holes. Its 10-pin header
  is Doepfer's and both B5819Ws face the right way. It clears R33, R36 and R39
  by 3.5 mm or more, which closes design.md's open item.
- **Panel:** every panel hole sits within 0.05 mm of its part.

## Applied: M1 and M2

On your OK (2026-11-13), with no copper moved:

- **M1, the CV inputs.**
  - Values: R22, R25, R28, R31, R34, R37, R40 27k → 13k and R45 15k → 11k. C21–C27 stay 1n: the corner moves from 5.9 to 12.2 kHz, still 54 times the firmware's widest CV filter, and no new part or wider silk label is needed.
  - Changed in `circuit.py` and the exporter, so `Marbles.epro2` and its page-1 preview are regenerated (0 problems).
  - In the routed master, by script:
    - the LR1F27K device (all three copies, used by the seven Rf only) renamed to LR1F13K, as the 24k → 23.2k fix did;
    - a new LR1F11K device for R45;
    - the eight silk value labels;
    - the two page-1 schematic notes.
  - The routed master's copper audit is identical to before, and the label preview `marbles-labels-main-top.png` is re-rendered.
  - Firmware: `adc.cc` kRf 13e3, kBiasRatio 10/21; `output_calibrator.h` kSpreadBias 3.3 × 10/21 (kLoadOffset 15.56 mV).
  - Docs: design.md's CV section; the firmware README's transfer.
  - Result: ±12 V now lands on 0.22–3.34 V. At the worst corner −12 V stays 0.150 V under 3V3A + 0.3 V and +12 V stays at or above +0.10 V, so all 38 M1 checks pass.
- **M2, the faceplate's DIP-16s.** bom.py has a module setting, `SOLDERED`, for U1, U9, U10 and U11. Their socket line is gone, and a note says to solder them straight to the board. design.md says the same. Both M2 checks pass.

What it cost, and what changed in the tests:

- **ADC resolution.** One code of the Seed's ADC is now 0.39 mV at the jack, against 0.19 mV before.
- **Firmware host tests: all 3118 checks pass, after two test changes.**
  - The `cv` group's fixed 2-code tolerance had silently assumed the 27k gain. It is now derived from the board tables: one Seed code, plus one of Marbles' own codes.
  - The `outcal` limit is 3 mV instead of 2.5. In a model with no ADC noise, one seed's worst output came to 2.87 mV: half a 12-bit DAC step (1.3 mV) plus X SPREAD's quantization carried through both calibrations. Real ADC noise dithers this down, since the calibrator averages 2048 readings.
- **The hardware suite's own checks.**
  - The tests that quoted design.md's old CV figures now check its new ones: the ±12 V range, the −12 V margin and the 12.2 kHz corner.
  - The firmware group's A.cv_pins_negative_injection took abs() of the pin voltage. It is fixed: at +12 V the pin sits above ground and draws nothing.
  - The pcb and bom groups now take each chip's socket from bom.py instead of assuming every DIP has one.
- **`marblesy.bin` is rebuilt.**
  - Toolchain: libDaisy v9.0.0 (a fresh pinned clone) and the xpack arm-none-eabi-gcc 14.2.1, with the firmware Makefile's own commands.
  - A rebuild of the committed sources first came out byte-identical to the committed `marblesy.bin`.
  - The new build is the same 182 052 bytes, and differs in 9 bytes only: the three float constants kZeroReading (0.508 → 0.5381), kVoltsPerFullScale (12.22 → 25.38) and kLoadOffset (13.07 → 15.56 mV).
- **Two new failures, outside marbles/.** The four-module parts order (`bom/parts-order.md` and `.csv`, generated by `bom/parts_order.py` from each module's bom.md) still lists Spore's old resistors and the four DIP-16 sockets. Rerun `python bom/parts_order.py`. The Thonk order is unchanged.

The other 50 failing checks are the low and docs findings below, unchanged.

## Copper rework, 2026-11-14

On your go-ahead ("Do all recommended fixes and optional fixes", relayed by the parent session), the copper items
were scripted into `Marblesy-routed.epro2`. `circuit.py`, the generator and `panel.py` came first, and
`Marbles.epro2` was regenerated (0 schematic and 0 PCB problems against the master). design.md's "Copper rework,
2026-11-14" has the positions; `hardware/easyeda/marbles-rework-2026-11-14.png` shows them.

- **L3, gate pull-downs.** R57, R58 and R59 are 100k from GATE_T1–T3 to GND on the main board.
  - R58 and R59 stand with pad 1 right on their GATE track. R57 lies flat beside U6, with a 0.3 mm top-layer track to U6 pin 3. No spot took a standing GATE_T1 resistor: pad 2 always landed on other copper.
  - Every new pad clears other copper by 0.46 mm or more.
  - On the schematic, page 2 got the three from the regenerated project, each on a T in its GATE port's stub.
  - Silkscreen: R57's flat body crowded R60's, R61's and C37's labels. All four were placed again by value_labels.py's rules and a finer scan, and none sits nearer another part.
  - BOM: three more 100k, 16 in all.
- **L8.** The two 0.3 mm 3V3A_F pieces at (61.5, 51.5–52.0) are 0.6 mm.
- **L14.** `panel.py` puts the right slots at 7.5 + (HP − 3) × 5.08 = 83.70. The panel files and the master's panel board were regenerated; the master's old panel drawing equalled the old generated one, so nothing drawn by hand was lost.
- **L17, partly.**
  - The DIP-16 footprint's pad 1 is square, in the generator and in the master.
  - circuit.py's C39 / C40 and C10 / C11 comments now follow the routed pairing.
  - The TL074 symbol's pin name, the header and pot device names and the LED pad squares are as they were.
- **L7 is yours to route:** GND_D_F, 0.6 mm, from C9's ground side to U9 pin 8 (36.31, 90.89) on the faceplate. The channel between U9's rows is busy on both layers, so it wants a hand route.

Suite, HEAD before the rework against after: 1293 checks / 50 failing → 1297 / 41. 14 checks were fixed:
- L3: G.defined_while_gpio_hiz ×3 and H.gate_defined_while_Seed_boots ×3
- L8: G.width.3V3A_F and HOLE.power_tracks_0.6.Faceplate
- L14: EURO.slot_spacing_a_multiple_of_HP
- L17: D.pin1_square_pad and F.circuit_comment ×4

Five fail newly, none of them a design fault:
- **POUR.GND_one_piece_main, POUR.other_net_copper_clear_of_pours.Main / .Faceplate.** The pours are the old ones:
  - The new GATE pads and R57's track sit in GND fill, and the new GND pads have no thermals yet.
  - On the faceplate, the square pin-1 corners come within 0.02 mm of the old round GND_F cutouts.
  - `copper_audit.py` says the same, with "rebuild all copper areas". Rebuilding them in EasyEDA clears all three.
- **C.parts-order.md / .csv.** The four-module order at the repository root still has Spore's 13 × 100k. Rerun `python bom/parts_order.py`.

The test changes that follow design.md's new figures:
- test_power's gate-input check allows the pull-down, 33 µA from the pin.
- test_panel's slot position.
- test_pcb's label counts: 79 on the main board; six at 38 mil and seven at 32.

Not new: U10 pin 1's square corner comes 0.19 mm from L_D17_G's track, over the 0.152 mm minimum (copper_audit's notes).

## Re-import, 2026-11-14

You imported the reworked master into the existing EasyEDA project, re-routed and exported it
(`ProPrj_SI - Marbles_2026-11-14.epro2`). The export could not become the master as it was. EasyEDA had kept the
project's older copy of every library item that a script had changed under the same id:
- **DIP-16 pin 1** was round again, which undid the L17 fix.
- **D21** came back VREF / GND / GND from the LM4040 symbols' old pin numbers, with VREF re-routed into pad 1. That
  is the SOT-23 order design.md's board fixes of 2026-11-02 removed. In TO-92 it leaves the cathode on GND: VREF
  would sit near 3.3 V or 0.7 V, depending on which TI pinout the part has, instead of 2.5 V.
- **Resistor devices:** R47, R70/R74/R78/R82 and the seven 13k Rf were the old LR1F2K2, LR1F24K and LR1F27K
  devices. The values stayed right; only a BOM taken from EasyEDA would have been wrong.

`copper_audit.py` on the export flagged D21.1 and D21.2 against circuit.py; nothing else in it was new. The new
master is that export with the three fixes put back by script:
- The 25 library items involved (the DIP-16 footprint, three LM4040 symbols and devices, nine resistor devices, and
  the nine 74HC devices that use the footprint) carry new ids and new sources, so the stale copies cannot replace
  them on the next import.
- D21's pads and VREF's five segments into pad 2 are as before.
- Kept from the export: GATE_T1 and 3V3D re-routed beside R58, and the main board's rebuilt pours. Those took in
  R57–R59, and the main board's GND is down from four pieces to two.

Against the old master (39 failing today, the parts order having been regenerated): one new failure,
**POUR.D21_pad1_spokes_both_layers**. The main board's pour was rebuilt around the swapped D21, so pad 1 (GND) has
no thermals and VREF's restored track runs through GND fill. POUR.GND_one_piece_main and
POUR.other_net_copper_clear_of_pours.Main now fail for that alone. The faceplate's pours were not rebuilt, and L7
is not routed yet (F.C9_to_U9.8_ground_path). One more pour rebuild on both boards clears every POUR failure but
the two small-island notes.

---


## Second re-import, 2026-11-15

You imported the rebuilt master, routed L7, rebuilt the pours on both boards and exported again
(`ProPrj_SI - Marbles_2026-11-14(1).epro2`). That export is now the master, unchanged:
- **The library fixes held.** U1/U9/U10/U11 use the square-pin-1 footprint, D21 is GND / VREF / GND on the
  pin-2-cathode symbol, and R47, R70–R82 and the 13k Rf use the 1k5 / 23k2 / 13k devices. EasyEDA kept its old
  copies too, unused by any part.
- **L7:** C9 to U9.8 is 24.1 mm of copper (126 mm before), through two vias at x 32.0, so F.C9_to_U9.8_ground_path
  passes.
- **Pours:** every net is in one piece, with no other-net copper in a pour and nothing under 0.152 mm. All four
  rebuild failures pass, and so does POUR.D21_pad1_spokes_both_layers.
- `easyeda_export.py`: 0 schematic and 0 PCB problems.

Suite: 1297 checks, 36 failing (40 before). One new failure, **POUR.no_tiny_islands.Main**: a 0.3 mm² GND fleck on
the bottom layer between D21's pad 1 and VREF's track, at (62.3–63.7, 31.1–31.4). It is 0.22–0.29 mm thick and held
by pad 1's spoke, so it is not a loose sliver and is over JLCPCB's 0.1 mm minimum: accepted. A no-copper area
there would remove it on a later rebuild. The other 35 are the low and docs findings below.
## Medium

**M1 (applied 2026-11-13). The CV inputs drive the Seed's ADC pins past their ratings from about
−7 V** (analog_dc B.vin_max.\* ×10, B.vin_analog_mode.\* ×14,
B.no_negative_injection.\* ×7, B.doc_claim_within_limit; power
H.powered_TT_ADC_pins ×2, H.powered_FT_ADC_pins ×2, H.design_injection_claim;
firmware A.cv_pins_survive_stage_swing: 38 checks).

The inverting stage puts V = 1.676 − 0.27·Vin on the ADC pin. That is
4.38 V at −10 V in and 4.92 V at −12 V. The STM32H750's pins have no clamp
to VDD, so the 1k limits nothing: ST DS12556 allows +0 mA of positive
injection on FT and TT pins.

| Limit | Applies to | Source | Crossed below (jack) |
|---|---|---|---|
| min(VDDA, VREF+) + 0.3 V | every FT_a / TT_a pin with its ADC input active | AN4899 Rev 3 §5.2.1–5.2.2, via a secondary copy and ST staff quotes: st.com refused the PDF | −6.65 V worst corner, −7.1 V nominal; all seven CV pins |
| 4.0 V absolute maximum | the three TT_a pins: Seed pins 24, 25, 28 = PB1 T BIAS, PA7 T JITTER, PC4 X BIAS | DS12556 pin table, Tables 19 / 20 | −8.1 V |
| 5 V | the other four (FT_a) pins as digital inputs, the Seed's rating | DS12556 | −11.7 V |

The HAL keeps every configured channel's PCSEL bit set, so the pins stay
ADC inputs while the firmware runs. MUX_OUT is safe because the pots cannot
exceed 3V3A.

The other polarity fails too. Above about +8 V the stage pulls each pin
below ground and injects 0.5–0.9 mA at +10 V. The note under DS12556
Table 184 says that disturbs conversions on the other channels, and
Table 154 gives 0 mA for PA6, PA7, PC4 and PA1. An envelope at +10 V into
any CV input would then disturb the pots and the other CVs.

design.md's "a ±12 V input pushes about 1.3 mA into the Seed's protection
diodes, which is within the STM32H7's limit" is wrong both ways. Marbles
specifies ±5 V, and ±5 V is safe, but Eurorack sources reach ±10 V.

**Proposed fix (no copper):**
- R22, R25, R28, R31, R34, R37, R40 27k → **13.0k**, and R45 15k → **11.0k**.
  - At the worst corner −12 V then stays 0.15 V under the 3V3A + 0.3 V limit, and +12 V stays at or above +0.10 V.
  - The cost: ±5 V spans 39 % of the ADC range instead of 82 %, about 26k codes, plenty for Marbles.
- Optional: C21–C27 1n → 2.2n, which keeps the corner near 5.6 kHz.
- Firmware: `adc.cc` kRf = 13e3 and kBiasRatio = 10/21; `output_calibrator.h` kSpreadBias (kLoadOffset becomes 15.6 mV).
- design.md's CV input section to match.

Rejected alternatives:
- **Rf 20k:** still 0.52 V over at the worst corner.
- **Moving inputs to FT pins:** no help under AN4899, and the free ADC pins are TT anyway.
- **A Schottky to 3V3A:** it injects into an LDO rail that cannot sink current.

Keeping the full ±5 V span would need clamps with copper of their own,
which would make this high.

**M2 (applied 2026-11-13). The faceplate's socketed DIP-16 chips don't fit under the main board,
and U11's socket collides with a standoff** (pcb
GAP.faceplate_rear_parts_clear_the_main_boards_tails,
OUT.standoff_clears_the_bodies_beside_it.Faceplate).

The mated headers give an 11 mm gap, but a socketed chip on the faceplate's
rear leaves little of it:

| Socket | Chip top | Left under the main board |
|---|---|---|
| Stamped (CnC Tech 243 drawing: 4.8 mm seat) | 4.8 + 5.33 = 10.13 mm | 0.87 mm |
| Machined (Mill-Max 110-43-316) | 9.52 mm | 1.48 mm |

The BOM's Tayda "DIP-16 IC socket" may be either kind. The PDIP-16 height
is 5.33 mm max (MS-001).

Directly above the chips, the main board's bottom carries the tails of the
breakout's socket strips. They are about 1.4 mm long and cannot be trimmed.
Cut leads add to that:

| Chip | Socket-strip tails over it | Cut leads over it |
|---|---|---|
| U1 | J3-1..3 | C30, D21, R42 |
| U10 | J1-1..3 | C32, R78, R79, R82, R83 |
| U11 | U2 pins 33–40, J4-4 | — |
| U9 | none, only items over the socket frame (fine) | — |

U11 also sits too close to the (45, 82) standoff. Its socket frame (10.16 mm
wide) comes within 2.42 mm of the hole centre, on the same side as the
standoff:

| Standoff (across flats) | Flat towards the socket | Corner towards it |
|---|---|---|
| 5 mm | overlaps by 0.08 mm | overlaps by 0.47 mm |
| 5.5 mm | overlaps by 0.33 mm | overlaps by 0.76 mm |
| 4.5 mm | clears by 0.17 mm | |

**Proposed fix (no copper):** solder U1, U9, U10 and U11 straight to the
faceplate, without sockets. That leaves about 5.7 mm over each chip, and
U11's leads sit 3.37 mm from the hole. In bom.py, drop the "4 × DIP-16 IC
socket" line and add a build note.

---

## Panel text, 2026-11-14 (house-wide, no copper changed)

EasyEDA Pro's default font was measured on its own Gerbers (the user's March boards against their project). A LEFT_BOTTOM string's letters stand 0.2 × fontSize above the origin and are 0.685 × fontSize tall; the advance is 0.64 × fontSize. Every `panel_pcb.py` now places text with these numbers (`INK_*`, `ink_width`), so panel text sits where the artwork has it. Before, it sat 0.2 × fontSize high, 0.4–0.9 mm. Labels on gold are knocked out of the mask: a hole in the mask opening round the letters, filled by a reverse string on the mask layer, so they read dark on the gold. The stroke has a 0.16 mm floor. The routed master's panel board was replaced by the regenerated one after checking that it equalled the old generated one, and the panel tests now use the measured font.

Marblesy's LENGTH numbers went from 1.5 to 1.65 in the artwork and the PCB. With the real metrics their letters were 0.92 mm, under JLCPCB's 1.0; LABELS.panel_pcb_text_height now uses the letter height.

## Low

| Id | Finding | Failing checks | Proposed fix |
|---|---|---|---|
| L1 | **The CV outputs can fall just short of ±5 V into 100k.** With every datasheet maximum stacked (1 % resistors, LM4040 C grade, MCP4922 offset and gain error from DS21897, TL074 offset at 0–70 °C), the range is +4.75 / −4.77 V; +4.81 / −4.84 V with 25 °C limits. The writer's Monte Carlo puts 0.08 % of modules short, but its distributions are assumptions. design.md's own figures (−5.107 / −5.056 V) reproduce: they leave out the DAC's errors. | analog_dc F.worst_reaches_5V.{X1,X2,X3,Y}.100k | R71/R75/R79/R83 47k → 44.2k and R70/R74/R78/R82 23.2k → 21.5k (E96), plus `dac.h` kDacInputResistor / kDacOffsetResistor: +5.05 / −5.23 V worst, 2.81 mV per step. Or accept. |
| L2 | **MCP4922 INL limits pitch accuracy.** INL is ±12 LSB max (±3 typ) in the 3 V table, which is 31.6 mV = 38 cents at the jack after calibration; a two-point fit cannot take it out. Typical is about 9 cents. design.md's "1/32 of a semitone" is the resolution, not the accuracy. | analog_dc F.inl_in_tune.max | Say so in design.md. The cure is design.md's 16-bit DAC8564 option. |
| L3 | **Applied 2026-11-14 (R57–R59).** **The gate outputs float while the Seed boots.** GATE_T1..3 have nothing but the TL074's + input on them. In reset, in the Daisy bootloader (2 s) or with the Seed unpowered, T1–T3 can sit anywhere up to the stage's positive swing. | analog_dc G.defined_while_gpio_hiz.T1–T3; power H.gate_defined_while_Seed_boots.T1–T3 | 100k pull-downs on a respin; an open item in design.md now. |
| L4 | **The gate level is below design.md's "above 6 V" at the worst corner.** Into the doc's own 100k load, the TL074's minimum output swing on a 10.83 V worst-case rail clips the stage, so the jack gets 5.87 V. Typical is 6.74 V, still a valid gate. | analog_dc G.doc_above_6V.worst.T1–T3 | Docs: "6.7 V typical, above 5.5 V worst". |
| L5 | **SPI timing margins at 3.3 V.** These use onsemi MC74HC595A's guaranteed 3.0 V figures; linear interpolation between 2.0 and 4.5 V was the writer's model and is wrong. The 595 cascade needs 175 ns against the 160 ns clock period at 85 °C; it passes at 25 °C and affects only the LEDs. The latch pulse gets 62.5 ns against 70 ns. The CS rise comes about 7.5 ns after SCK idles against the MCP4922's 40 ns tIDLE, if RXP is set at the last sampling edge; RM0433 gives no figure. | firmware D.hc595_cascade_U9_to_U10, D.hc595_latch, D.mcp4922_sck_idle_before_cs | `WriteLeds` Wait(50) → Wait(90), `WriteDacs` CS hold Wait(20) → Wait(60) (about +0.2 µs per sample); accept the cascade. |
| L6 | **"CD4051B also works" is not backed by its datasheet.** TI SCHS047O guarantees rON only at VDD ≥ 5 V. With about 10k assumed at 3.3 V, a pot reading picks up 0.12 % from the channel sampled before it. | analog_dc C.cd4051b_ron_specified_at_3V3; analog_ac B.pot_sampling_settles.cd4051b | Drop the alternative from bom.py's 74HC4051 line. |
| L7 | **Done: routed by you, second re-import of 2026-11-15 (24.1 mm now).** ~~**A route for you (design.md, 2026-11-14).** **U9's decoupler reaches its ground pin the long way round.** GND_D_F is tracks only, and the copper path from C9's ground pad to U9 pin 8 is 126 mm (20.5 mm straight); re-measured independently. It will probably work, with some ground bounce when the LEDs switch.~~ | power F.C9_to_U9.8_ground_path | A short GND_D_F track from C9.2 to U9.8 if the faceplate's copper is opened again. |
| L8 | **Applied 2026-11-14.** **A thin 3V3A_F stretch.** Two 0.3 mm pieces (0.5 mm in total) of 3V3A_F at (61.5, 51.5–52.0) on the faceplate, against design.md's 0.6 mm power rule. They carry about 3 mA. | power G.width.3V3A_F; pcb HOLE.power_tracks_0.6.Faceplate | Widen them if the copper is touched. |
| L9 | **Two main-board value labels sit nearer the wrong part, and 13 are under 1.0 mm.** R42's "10k" is nearer R47 (1k5), centre distance 7.4 against 3.5 mm. R66's "10k" is nearer R67 (15k), 4.0 against 2.5 mm. Thirteen labels are at 38 or 32 mil, under JLCPCB's 1.0 mm minimum ("unidentifiable" below it); design.md admits these. | pcb SILK.label_not_nearer_a_wrong_value.Main, SILK.label_height_jlc_1mm.Main | Silkscreen only: legend lines and 40 mil text, as the mixer did. |
| L10 | **Two body clearances.** At maximum sizes C40 overlaps U7's PDIP by 0.09 mm. design.md's "no rear pad within 0.8 mm of a pot housing" holds for pad centres only: U11.8's copper is 0.01 mm from RV5's housing, C10.1's 0.08 mm from RV4's. | pcb BODY.no_overlap.main top, BODY.rear_pad_copper_0.8mm_from_pot_housings | Lean C40 at assembly. Keep those joints low. Reword design.md. |
| L11 | **U11 pin 4 is close to the (45, 82) standoff and screw.** U11.4's copper (BTN_X_RANGE_F) is 2.90 mm from the hole. A 5.5 mm across-flats standoff's corners reach 3.175 mm; a 5 mm one clears by 0.01 mm. A DIN 7985 head (dk 6.0) rides 0.1 mm onto the joint; an ISO 7045 head (dk 5.6) clears it. The BOM names neither. | pcb OUT.no_signal_pad_under_5.5AF_standoff.Faceplate, OUT.no_signal_pad_under_the_screw_head.Faceplate | BOM: 5 mm AF (or nylon) standoffs and ISO 7045 M3 × 6 screws, or a nylon washer at that hole. |
| L12 | **The TO-92 parts need their leads formed.** LM4040CIZ-2.5/NOPB ships bulk only, with straight 1.27 mm leads (SNOS633N, LP0003A note 5a); a bulk 2N3904 is the same. The footprint is 2.54 mm. | pcb FP.to92_straight_lead_parts_need_forming_noted | bom.md note: bend the outer leads out to 2.54 mm. |
| L13 | **Two pour islands hang on one connection.** A 19 mm² GND island on the main board's top at (28.9, 67.6) and a 2.1 mm² GND_F island on the faceplate's bottom at (34, 26.9). No dead copper and no pour problem at D21. | pcb POUR.no_small_island_on_one_connection.Main / .Faceplate | Re-run after the pour rebuild (already an open item). |
| L14 | **Applied 2026-11-14.** **The right mounting slot is 0.1 mm off the HP grid.** It sits at 83.8 mm; Doepfer's rule (a multiple of the HP grid) gives 7.5 + 15 × 5.08 = 83.70. The slot's play absorbs it. | panel EURO.slot_spacing_a_multiple_of_HP | panel.py: right slot at `7.5 + (HP − 3) * 5.08`, then regenerate and re-insert the panel drawing. |
| L15 | **The power cable line is unresolved.** bom.md still says "check the header's pin count (10 or 16)". The breakout's J2 is an unshrouded 2×5 (Amphenol 67997-210HLF), wired to Doepfer's 10-pin pinout. A flush 10-pin plug is safe either way round. A 16-pin socket can sit on the bare 2×5 in 8 places, and 6 of them short the bus. | bom E.power_cable_10pin_module_end | bom.py: "16-to-10-pin cable, red stripe to J2's RED STRIPE mark". The same text is in Plaitsy's and Side FXy's bom.py and in `bom/thonk-order.md`. |
| L16 | **Abuse cases.** An output patched into another module's output at the opposite rail puts 439 mW in the gate outputs' 1k and 329 mW in the CV outputs'. If that output has its own 1k, ours sees at most 109 mW. A gate jack driven to −12 V puts 12.6 V reverse across D11–D13 (Kingbright WP710A10ID: 5 V max). With one bus rail at 0 V, the dead node sits up to 0.6 V the wrong side of GND, against the old TL074 die's 0.3 V input rating. With one rail open, about 15 mA flows per input through the six TL074 inputs tied to GND, against 10 mA. | bom D.resistor_dissipation_quarter_watt, D.gate_LED_reverse_voltage; power H.rail_at_0V.max, H.rail_open_input_clamps.max | Accept. Optionally LR1F 0.6 W for R62/R65/R68/R73/R77/R81/R85. |
| L17 | **Square pin 1 and circuit.py's comments applied 2026-11-14.** **EasyEDA names and marks.** The TL074 symbol calls pin 11 "GND", though it is wired to −12 V. On D11–D17 the square pad is the anode while the flat marks the cathode; KiCad squares the cathode. H1/H2/H4/H5/H7 carry male devices and HF3/HF6 the female one (bom.py is right). The pots carry Bourns' PTV09A part number on the Alpha footprint. The DIP-16 footprint has no square pin-1 pad, though the silk notch and dot are right. circuit.py's comments swap C39/C40 and C10/C11 against the routed pairing. | netlist B.TL074_symbol_pin_names, C.LED_square_pad_on_cathode, D.header_device_gender, D.pot_device_is_Alpha, D.pin1_square_pad; power F.circuit_comment.C10, .C11, .C39, .C40 | Cosmetic. A build note for the LED pads; fix the rest when the project is next edited. |

## Docs

design.md figures the design does not match:

- **The ±12 V input claim** is false both ways (M1).
- **The reference current** is 0.53 mA, not 0.4 mA (R47 is 1.5k since 2026-11-02). Fails analog_dc D.doc_power_section_current and power D.design_reference_mA.
- **"LEDs at most 33 mA"** is 39 mA at worst case, 27 mA typical. Fails power D.design_LEDs_at_most.
- **No ±12 V draw is given.** With the breakout's op-amps and the DC/DC: +12 V about 74 mA typical, 126 mA worst; −12 V 74 / 120 mA. Fails power D.design_states_bus_current.
- **The gate "above 6 V"** (L4), **"1/32 of a semitone"** (L2) and **the 0.8 mm pot-housing clearance** (L10).
- **Two notes, no failing check:** the outputs are calibrated for 100k inputs (into 10k they read 8.2 % narrow), and the breakout plugs in SMD side down, with its DC/DC and J2 tails pointing at the main board.

## Outside Marblesy

- **Six modules wire the 16-pin power header off the standard.** In `circuit.py` `power_main()`, stereo-mixer, atlas, attenuverter, buffered-mult, sample-hold and vca put GND on pins 3–10 and +12 V on 11–12. The standard is −12 V on 1–2, GND on 3–8, +12 V on 9–10 and +5 V on 11–12. With a standard cable the module's GND pins 9–10 short the bus's +12 V, and its +12 V input gets +5 V. The stereo mixer's suite encodes the same wrong table (test_netlist EURORACK_DS, test_power DOEPFER). This is **high** for those modules (copper on the mixer's routed master) and was reported on 2026-11-13. The details are in the shared notes, `URGENT-16pin-power-header-pinout.md`. Marblesy is not affected.
- **The module-design skill's `parts.md` (line 176) still says "LM4040 TO-92: 1 = +, 2 = −, 3 = NC".** The cathode is pin 2 (SNOS633N), as D21 has been since 2026-11-02.
- **The "10 or 16" cable text** is also in Plaitsy's and Side FXy's bom.py and in `bom/thonk-order.md` (L15).
- **Plaitsy's report flags 1N5711 and SD101 as clamping too late.** That applies to ADC-pin clamps. In Marblesy the BAT85 line clamps the 2N3904's base, where 0.5 V is fine (VEBO 6 V), so it does not apply here.

## Test bugs the verifiers fixed, and refuted claims

- **Anti-aliasing (7 checks): refuted, check rewritten.**
  - The 5.49 kHz per-channel rate is right: rev V's ADC clock is 6.146 MHz, 17 cycles per conversion, eight in a row per rank.
  - But Marbles low-passes every CV at 52–227 Hz in firmware, so the stage's 5.9 kHz corner only has to sit well above that. The new check asks for at least 10× and passes; the alias rejection (−2.5 dB) is printed.
- **CV outputs into 10k: refuted, now printed as information.** No source claims ±5 V into 10k (4 checks).
- **Value labels within 0.3 mm of a tie: refuted, now printed as information.** No source sets a 0.3 mm margin.
- **The DC/DC input voltage: test bug, now passes at 21.67 V.** The test applied the B5819W's 0.6 V maximum (at 1 A) at 60 mA; it now carries that maximum down with the diode law, which is still a bound. The Mornsun 21.6–26.4 V range is confirmed.
- **The C10 / C11 ground paths: test bug, now pass.** A DIP-16's pins 8 and 16 are 19.3 mm apart, so the 10 mm criterion could never be met; it is now the straight-line distance + 10 mm.
- **74HC595 SER setup: test bug, now passes** on onsemi's 3.0 V figures (62 ns available against 50 needed).
- **C30 against D21: test bug, now passes.** The TO-92 body was a rectangle; with the real D shape it clears by 0.145 mm.
- **Checks that could not fail, now real checks:**
  - panel EURO.boards_centred compared to_panel()'s own constants;
  - analog_dc C.hc_analog_range was `True`;
  - three BOM checks (gate LED reverse voltage, MCP4922 VDD/VREF, 2N3904 VCEO) compared constants only;
  - the netlist's BAT85 clamp check counted the diode however it was wired.
- **One passing check that should have failed:** power H.powered_FT_ADC_pins used the 5 V digital-input limit; it now uses 3V3A + 0.3 V.
- **The output calibrator:** passes, with the offset 9.7 % off against its 10 % window at the fully stacked corner. Thin, but settings.cc's boot-time outlier check uses the same nominal constants, so a calibration that passes is not thrown away at the next boot.

## What the suite could not check

- **AN4899** (the analog-mode limit behind M1): read from a Rev 3 copy and ST staff quotes, not the primary PDF.
- **The STM32H7 SPI's RXP timing** after the last SCK edge: RM0433 gives none.
- **The Seed's rails:**
  - its 3V3A / 3V3D current limits and tolerance are unpublished;
  - the rev 7 schematic is not public;
  - TPS62177 / LP2985, ±3 % and 100 / 300 mA are assumptions;
  - the Seed's own draw (120 / 140 mA) is a forum measurement, and the DC/DC's margin (184 mA worst against 200) rests on it.
- **Assumed figures:**
  - the bus tolerance (±5 %; Eurorack has no standard);
  - the LED forward and reverse voltages;
  - the 74HC4051's rON below 4.5 V;
  - the STM32 ADC's switch resistance;
  - which die a generic DIP TL074 has.
- **Not confirmed:**
  - Whether the Daisy bootloader drives PC8–PC12 (SD card lines, which include the gate pins and the X clock).
  - Tayda's socket type and height. Thonk blocks fetches, so the Thonk LED button's pinout (parts.md only) is unconfirmed, and so are the parts' heights. The header tails' length, the mated header height, and the standoff across-flats and screw standard the BOM means are unconfirmed too.
- **Not modelled:**
  - ground and supply crosstalk, track coupling;
  - Gerber-level checks (mask slivers, silk clipped by pads);
  - interrupt latency and CPU load beyond the bus time.
