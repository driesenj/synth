# Side FXy hardware test suite, 2026-11-13

A hardware design test suite for Side FXy (Moss), modelled on the stereo
mixer's: ten groups in `hardware/tests/`, each written and run by an agent,
then re-derived by an independent verifier. The verifier re-read the
datasheets and fixed the test bugs it found: checks that compared a
constant with itself, snapshots of the current design, and limits read at
the wrong conditions. Everything is checked against each other:
`circuit.py`, the routed master `SideFXy-routed.epro2`, `design.md`, the
routing audit, the firmware's pin tables, the breakout's own Gerbers and
BOM, and the manufacturers' datasheets. The suite only reads. **Nothing in
the design, the boards, the BOM or the firmware has been changed:** every fix
below is a proposal waiting for your OK.

```bash
cd side-fx/hardware/tests && python run_tests.py
```

| Group | Checks | Failing | What it covers |
|---|---|---|---|
| netlist | 168 | 6 | pinouts and polarity against the datasheets, every routed pad's net, connectivity, stacked header pins, the schematic, design.md's tables, the breakout's headers traced in its Gerbers |
| pins | 388 | 0 | check_pins.py folded in; the firmware's pins against circuit.py, the routed U5 and libDaisy v9; the STM32's alternate functions and ADC channels; the chain's bit order |
| logic | 104 | 7 | the 74HC165/595 chain at 3.3 V against the firmware's bit-bang timing, logic levels, LED drive, encoders and debounce, the display's SPI |
| audio | 95 | 9 | the breakout's audio stages (traced from its Gerbers): levels, headroom, impedances, offset, response, phase margin, polarity, normalling |
| cv | 96 | 7 | the four CV stages into the ADC: transfer, worst case, overdrive and injection, settling, noise, calibration |
| clock_midi | 66 | 1 | the clock transistor stage and the H11L1 MIDI input: thresholds, currents, timing, ratings |
| power | 103 | 10 | the breakout's J2, reverse protection, rails, the 5 V DC/DC and the 3V3D budget, ratings, missing-rail faults, decoupling |
| pcb | 178 | 18 | footprints against the datasheets, drills and rings against JLCPCB, the breakout's holes, value labels, bodies, the stacking gap, the display stack, copper |
| panel | 418 | 7 | holes in every representation against the faceplate, the display window, Eurorack mechanics, clearances, labels, the panel frame |
| bom | 139 | 4 | bom.py against circuit.py and the committed BOM, the Thonk order, part numbers, ratings, mechanics |
| **all** | **1755** | **69** | first run 1743 / 64; the verifiers fixed test bugs, added 12 checks and found 5 new failures |

The 69 failing checks are 37 findings: 1 high, 9 medium, 27 low. One finding
often fails several checks. Only one finding needs copper before ordering,
and only if you keep the Bourns encoder (M4). The high finding is a
value change.

## Applied 2026-11-14 (no copper changed)

After the fixes: **1755 checks, 33 failing** (with the encoder settled on 2026-11-14). The copper audit of the patched
master is identical to the committed one's, `easyeda_export.py` reports 0
problems everywhere, and all 23 firmware host test groups pass.

| Finding | What changed |
|---|---|
| H1 | R11 / R14 / R17 / R20 27k → 13k, C10–C13 1n → 2n2, R23 10k → 12k: in circuit.py, the exporter (new LR1F13K / LR1F12K / 2.2 nF devices, the schematic notes) and the routed master. The master's two 27k device docs are renamed to 13k and the 1 nF one to 2.2 nF; R23 points at a new LR1F12K. Firmware: nominal calibration 0.5022 / −25.38 V, kMinScale / kMaxScale −40 / −12, CV ZERO and the stored-offset window 0.42–0.58 (±2 V, as before in volts), the comments. design.md's CV section. The cv group now passes all 96 checks: ±12 V lands on −0.02…3.35 V at the worst corner. |
| M1 | design.md's new Build notes and bom.md's notes: SMD side down, J1 / J3 / J4 / J5 from the SMD side, the Seed on long-tail stacking headers (a new BOM line, 2 × 1×20), the ±12 V check before the first power-up. |
| M2 | bom.md and design.md tell the builder to fit 10 pF and 100 pF in the breakout. The audio model now uses the breakout as built that way: −0.2 dB at 20 kHz, phase margin 58° or more. |
| M3 | design.md and the README give the bus current and the DC/DC budget, with "measure on the first build". The DC/DC checks still fail: they need a measurement or a 2 W converter. |
| M7 | kDebounceScans 4 → 24 (6 ms; 20 would accept after 4.75 ms, under the 5 ms assumed for the buttons). The controls host test now uses 24 scans. |
| M8 | U1 and U2 are soldered without sockets: bom.py's SOLDERED, a BOM note, design.md. |
| Low | D1 has its own BOM line without the SD103A / BAT86. The ui.cc scale comment now says "up to about 6 %"; the hal_daisy.cc timing comment says "~60 ns". design.md: 4 kHz, the J5 cell, the faceplate resistors, the vias and edge as routed. The 74HC165 symbol's pin 15 is /CE (exporter and master). The power cable is 10-pin to 16-pin. The breakout line points at its own BOM. The bus current is in design.md and the README. R26 is 0.5 W or more. C4 is TDK FG28X5R1E106MRT06. Q1 has formed leads. Nylon washers are on the BOM. The README, firmware README, routing audit, panel.md and parts.md now give the 9 mm panel gap. The limiter and the "OUT = IN" claim are reworded. |
| Labels | side-fx's value_labels.py is the mixer's version, with its 0.3 mm MARGIN rule and 40 mil text. The old 37 labels were stripped and the master re-labelled: 5 on the faceplate; 33 on the main board, 9 of them legend lines for the CV cluster. Every label check passes. |

The shared `bom.py` catalogue changed in all four copies (marbles, plaits,
side-fx, stereo-mixer), so the code stays identical:
- a per-ref override (REF_PART);
- SOLDERED, which Marblesy already had;
- a 2n2 capacitor;
- the cable line and the breakout's parts-list pointer.

Marblesy's and Plaitsy's BOMs were regenerated; their only changes are the
cable and breakout lines. The mixer's BOM is unchanged.
`bom/thonk-order.*` and `bom/parts-order.*` were regenerated. The parts order
also picked up Marblesy's already-applied 13k / 11k and socket changes.

The firmware was rebuilt with libDaisy v9.0.0 and xpack gcc 14.2:
`sidefxy.bin` is 327,528 bytes, against 327,520 before.

Several checks were test bugs exposed by the fixes, now corrected:
- checks with design.md's old CV values (100k / 27k / 1n, 10k / 25k, 1.32 V) or ui.cc's "within a percent" copied in;
- via and edge checks with design.md's rule copied in;
- a BOM count that matched "1N4148" anywhere in a line;
- the D1 check, which always assumed an SD103A;
- the socket and stacking checks, which ignored the BOM's socketless chips;
- the R26 rating, fixed at 1/4 W.

They now read the source.

**Still open** (the 33 failing checks):
- **M4 / M5, the encoder:** the part is the Bourns PEC11R-4215F-S0024, the user's encoders (2026-11-14). The BOM and design.md name it.
  - **M5, accepted:** its 5 mm bushing reaches about 0.9 mm through the panel (0.45 mm at worst), so it goes in without the nut. It hangs on its soldered pins and tabs and centres in the panel hole. D.enc_thread_through_panel, D.enc_body_gap and D.knob_hides_nut keep failing on that.
  - **M4, settled by measurement:** the user's encoders measure 12.7 mm or less across the outer faces of their tabs (2026-11-14), so they fit the present slots (outer edges 12.7 mm apart) and no copper changes. A.ec11_tabs_pec11r and D.pec11r_tabs now check that measurement, and print Bourns' recommended holes (0.25 mm wider on the outside) as information. A.ec11_tabs_pitch checks Alps' holes only while the BOM offers an Alps part.
- **M6, the button height:** measure one.
- **M9, OUT 1 / OUT 2: done 2026-11-14.** They are knocked out of the band's mask, house-wide (see "Panel text" below).
- **M3, the DC/DC:** measure.
- **Not applied:**
  - the SPI pin speed (firmware code; low);
  - a per-board limiter ceiling (documented instead);
  - the panel text weight: not needed. Against the measured letter height (0.685 × fontSize), size / 9 is about 1:5.5, already bolder than 1:6. E.text_ratio now uses that height.
  - the TL074 library symbol's pin 11 name.
- **Copper, left as is:**
  - H4's missing ground;
  - the GND_F sliver;
  - the rings under 0.25 mm;
  - ground in the plug-tip circles;
  - C2's distance;
  - the pad and track under the two standoffs (nylon washers now on the BOM).
- **Low, as reported:** the hot-input and 20 Hz figures, the Rev7 gain, the one-rail fault.

---


## Panel text, 2026-11-14 (house-wide, no copper changed)

EasyEDA Pro's default font was measured on its own Gerbers (the user's March boards against their project). A LEFT_BOTTOM string's letters stand 0.2 × fontSize above the origin and are 0.685 × fontSize tall; the advance is 0.64 × fontSize. Every `panel_pcb.py` now places text with these numbers (`INK_*`, `ink_width`), so panel text sits where the artwork has it. Before, it sat 0.2 × fontSize high, 0.4–0.9 mm. Labels on gold are knocked out of the mask: a hole in the mask opening round the letters, filled by a reverse string on the mask layer, so they read dark on the gold. The stroke has a 0.16 mm floor. The routed master's panel board was replaced by the regenerated one after checking that it equalled the old generated one, and the panel tests now use the measured font.

## High

**H1. A −10 V CV overvoltages CV 3 and CV 4's ADC pins** (cv
D.tt_overvoltage_-10V.CV3, .CV4; also D.seed_gpio_abs_-12V.CV1, .CV2,
D.no_neg_injection_+10V, D.inj_susceptibility_+10V.CV4).
- **What happens:** the stage maps about ±6 V onto 0..3.3 V (V_adc = 1.676 − 0.27·V_in), and nothing limits the TL074's output, which drives the pins through 1k.
- **The pins:** A2 = D17 = PB1 and A3 = D18 = PA7 (libDaisy v9) are TT_a pins: DS12556 Rev 7, Table 7.
- **The limits:**
  - 4.0 V absolute maximum on TT pins: the Table 19 / 117 voltage limit ("VIN maximum must always be respected").
  - +0 mA positive injection allowed: Table 118.
  - The Seed datasheet calls pins 24 and 25 "3.3 V tolerant".
- **The numbers:** −10 V at the jack gives 4.22–4.54 V at the pin over every corner (typical 4.38), and −12 V gives 5.09 V. The limit is crossed below about −8.1 V. A −10 V LFO or an inverted envelope is an ordinary CV.

The same stage causes four lesser failures:
- CV 1 / CV 2 (FT_a) reach 5.09 V at −12 V, against the Seed's 5 V GPIO maximum. They stay inside the STM32's own limit.
- Above about +5.7 V every pin goes below 0 V: up to 0.88 mA of negative injection at +10 V. That is inside the 5 mA rating, but DS12556 7.3.20 says it "significantly reduces the accuracy" of the other channels.
- PA7 has a 0 mA row in Table 154.

**Fix (values only, no copper):**
- Rf R11 / R14 / R17 / R20 27k → 13k, Cf C10–C13 1n → 2n2 (the corner stays near 5.6 kHz), and R23 10k → 12k (BIAS 1.47 V).
- Worst case at the pin: ±10 V lands on 0.24–3.08 V, ±12 V on −0.02–3.35 V.
- The firmware moves with it: the nominal offset becomes 0.5022 and the scale −25.38 V (the ReadCv default and the calibration nominal). settings.cc's `kMinScale` (−20) must widen, or a stored calibration is rejected on load.
- Update design.md's figures.
- The alternative is Schottky clamps at the ADC nodes, which needs copper.

Marblesy has the same stage on three TT pins (PB1, PA7, PC4): its own report's M1.

## Medium

**M1. The breakout plugs in either way round, and no doc says which**
(power A.U5_build_doc). The netlist, power, audio and pcb verifiers all
re-derived it from the breakout's Gerbers:
- **What the footprint is:** the routed U5 footprint is the breakout mirrored.
- **Which side faces which way:** the breakout's SMD side (op-amps, D2/D3, the passives: the only paste layer) faces the main board. The Seed, J2, the DC/DC and C9/C18 face the case.
- **Pin 1:** confirmed by copper, not only silk. Pin 40's square pad is spoked into the GND pour; pin 1's is isolated.
- **Why the fit misled:** the drill pattern is symmetric, so an unmirrored fit also lands holes on holes.
- **Turned over:** ±12 V goes reversed into U6 and pin 40 (GND) lands on CLK.
- **The breakout's own silk:** it draws J1 / J3 / J4 / J5 on the Seed's side. Built that way, U6 gets no ±12 V and the audio headers don't connect.

**Fix (docs + BOM text):**
- In design.md, bom.md and the README:
  - SMD side towards the main board.
  - J1 / J3 / J4 / J5 male headers fitted from the SMD side, pins pointing at the main board (against the breakout's silk).
  - The Seed's rows on long-tail (stackable) female headers from the Seed side.
  - Seed USB at the J4 / J5 end.
  - Before the first power-up, with the Seed out, +12 V at C15 and −12 V at C16.
- Name the stackable headers in the BOM line that now says "male pins under the breakout".
- Optional silk-only legend at U5: "SMD side down, USB ↓".

**M2. The breakout's audio filters cut the top octave** (audio
F.flat_20Hz_20kHz.input_path, .output_path, .whole_path).
- **The traced circuit:** two inverting TL074 stages per path, the Daisy Patch Rev 8 circuit part for part. Every section's + input is on GND, and each cap sits across its feedback resistor.
- **The poles:**
  - 100k ∥ 47p is a pole at 33.9 kHz in six stages (−1.30 dB each at 20 kHz).
  - 10k ∥ 560p is a pole at 28.4 kHz in the other two (−1.74 dB each).
- **The loss at 20 kHz:** −3.05 dB in, −2.75 dB out, −5.8 dB through the whole path including the dry sound (−6.4 dB at tolerance). The whole path is −1.6 dB at 10 kHz.
- **The codecs:** they add nothing. Both are flat to 21.8 kHz at 48 kHz.

**Fix:** values in the breakout's assembly BOM, no copper. C1, C5, C10, C11, C16, C17 47p → 10p and C2, C6 560p → 100p (0603 C0G). The whole path is then −0.32 dB at 20 kHz, and the phase margin stays at least 57.9° (60.5° in the verifier's own model). The caps cannot simply be removed: without them the 100k stages drop to about 25° of phase margin.

**M3. The 1 W DC/DC is at or over its rating** (power D.dcdc_max, D.dcdc_typ;
D.dcdc_vin.low_worst is low).
- **The rating:** the breakout's B2405S-1WR2 gives 200 mA at 5 V. Mornsun datasheet 2024.09.09-B/4: input 21.6–26.4 V, 76 / 80 % efficient.
- **The load:** worst case 239 mA, typical 177 mA, which is 88 % of the rating.
  - The Seed: Electrosmith publishes no current. DS12556 Table 127 gives the MCU alone 148 mA typical and 226 mA max at 480 MHz. The forum's 140 mA at 5 V is a fair typical.
  - Every 3V3D load at its maximum: 76 mA through the Seed's buck. That includes the display's backlight (Waveshare's 40 mA covers it) and the BL pin's 3 mA into the module's S8050.
- **The input at the worst corner:** at a −5 % bus, full load and the B5819W's bound, the DC/DC sees 21.56 V, just under its 21.6 V minimum. It is unregulated with no undervoltage cutoff.

**Fix:** cap the backlight and LED PWM in firmware, and measure the bus current on the first build. If it is high, fit a 2 W converter in U3's place. Check its footprint first, and that L1 / L2 (TDK MLZ1608, Isat 130 mA) carry about 115 mA. design.md's fallback, a separate display regulator, only helps if it is fed from +12 V.

**M4. The encoder footprint's tab slots don't fit the Bourns PEC11R** (pcb
A.ec11_tabs_pec11r, A.ec11_tabs_pitch; bom D.pec11r_tabs).
- **The footprint:** KiCad's Alps EC11E: MP1 / MP2 slots at ±5.6 mm, 1.5 mm along the tab line, covering 4.85–6.35 mm from the shaft.
- **Bourns' PEC11R layout:** 1.8 × 2.6 mm holes covering 4.8–6.6 mm. The "13.2" on the drawing is across the holes' outer edges; the centres are 11.4 mm apart.
- **The result:**
  - The slot is 0.3 mm short of Bourns' hole along the tab line, and 0.25 mm short on the outside.
  - The PEC11R, the BOM's first-named part, will not go in.
  - Alps' own holes (4.75–6.25) sit 0.1 mm inside the slot.

**Fix:**
- Either widen MP1 / MP2 to 2.0 mm along the tab line, centred 5.65 mm from the shaft. That covers both Bourns' and Alps' holes, and is a small faceplate copper change.
- Or name the Alps EC11E (or another Alps-pattern EC11) in the BOM and drop the PEC11R.
- Correct parts.md's "Bourns PEC11R uses the same pattern" either way.

**M5. The encoder bushing barely reaches through the panel** (panel
D.enc_thread_through_panel, D.enc_body_gap; D.readme_panel_gap and
D.knob_hides_nut are low).
- **The gap:** the panel sits on the jack bodies, 9.0 ± 0.15 mm above the faceplate (Thonk's PJ398SM drawing: "5.5 | 9 | 3.5"). It is not the 7 mm that the README, the skill's panel.md and the routing audit assume.
- **The thread:** both the PEC11R-4215F and the Alps EC11E reach 11.5 mm. That leaves 0.9 mm of thread in front of a 1.6 mm panel (0.45 worst case), while the washer and nut need 2.5 mm.
- **The air gap:** there is 2.5 mm of air between the encoder body and the panel, so a tightened nut pulls the encoder and the faceplate towards the panel.
- **The knob:** the PEC11R's nut is 10.0 mm across flats and 11.55 across corners, larger than the BOM's 11 mm knob (cosmetic).

**Fix:**
- PEC11R-4220F-S0024 (7 mm bushing), which gives 2.9 mm of thread, or an Alps EC11 with a 7 mm bushing. Combine it with the slot change in M4.
- A spacer nut (M7 × 0.75) plus washer behind the panel, or leave the nuts finger-tight.
- Correct the 7 mm in the README, panel.md and the audit to 9 mm.

**M6. The LED buttons may stand taller than the jacks: measure one first**
(panel D.btn_base_under_panel; not confirmed).
- **The drawing reading:** Thonk's LowProfileButton drawing, read from its vector paths, puts the 7.5 mm square base at 10.2 mm above the board, or 9.85 mm with the feet clipped. That is above the jacks' 9.0 mm.
- **What would follow:** the panel would rest on the five buttons, which might then be held pressed.
- **The disagreement:** the module-design skill's parts.md says the button "sits at Thonkiconn height if the three plastic feet get holes". A builder measured a Thonkiconn at 10 mm, not 9.
- **Not settled:** whether the base moves with the cap.
- **Reach:** the same pair of parts is on Marblesy, Plaitsy and the mixer.

**Fix:** before soldering, fit one jack and one button on a bare board and lay the panel on them. If the button is taller, clip its feet and solder the jacks about 1 mm proud with the panel fitted, or choose a lower button. Add the result to parts.md.

**M7. The debounce is 0.75 ms against 2–5 ms of bounce** (logic
D.debounce_vs_encoder_switch_bounce, D.debounce_vs_button_bounce).
- **The firmware:** `kDebounceScans` = 4 at the 4 kHz scan accepts any level held for 0.75–1 ms. It was probably sized for design.md's old 2 kHz.
- **The encoders:** Bourns gives 2.0 ms max contact bounce for the PEC11R's rotary contacts (REV. D04/26), measured with its RC filter, which this board doesn't have. The push switch has no figure.
- **The Thonk buttons:** no data published; 5 ms of tact-switch bounce is assumed.
- **The effect:** a bounce gap longer than 0.75 ms gives a spurious release and press.

**Fix (firmware):** `kDebounceScans` 20 (5 ms), and correct the "(1 ms)" comment.

**M8. Socketed 74HC165s on the faceplate don't fit under the main board**
(pcb G.faceplate_rear_height).
- **U1:** the On Shore SA socket stands 4.43 mm and the chip up to 5.33 mm (JEDEC MS-001 max). Over it sit U5's socket-strip tails (1.6 mm): 11.43 mm in the 11.0 mm gap.
- **U2:** it sits under D1's and R24's leads, up to 2.5 mm (IPC-A-610 class 2): 12.33 mm.
- **Typical parts:** they fit by about 0.4 mm.

**Fix:** solder U1 and U2 without sockets (drop the faceplate's two DIP-16 sockets from the BOM), or clip D1 / R24's leads to 1.2 mm or less and use low sockets. Marblesy has the same problem (its report's M2).

**M9. OUT 1 / OUT 2 may not print** (panel E.output_words_as_drawn).
- **The artwork:** it shows the words as dark letters knocked out of the gold band.
- **The panel PCB:** it has them as white silk on layer 3, inside the band's solder-mask opening.
- **The fab:** fabs usually clip silk from mask openings (JLCPCB's silkscreen guide, Altium's docs; JLCPCB's capabilities page states only pad-to-silk 0.15 mm).

**Fix (the panel PCB's mask, no copper):** leave a mask-covered plate under each word, or cut the letters out of the layer-5 opening so they read as black on gold, or move the words onto black.

## Low

| Finding (failing checks) | What | Fix |
|---|---|---|
| Hot inputs (audio B.input_20Vpp_hot_fits.Rev5, .Rev7) | Input stage 1 (gain −1) clips at 16.4 V p-p worst case (20.4 typical) on the breakout's ±11.2 V rails; 10 V p-p passes. 20 V p-p is not a standard requirement, and the Patch clips at the same point. | Document "IN up to about 16 V p-p"; or R1 / R6 47k + C1 / C5 22p and R2 / R7 22k + C2 / C6 47–100p (about 35 V p-p). |
| The limiter never acts (audio B.firmware_limiter_ceiling_inside_output_swing.Rev5, .Rev7) | SoftLimit() is linear to 0.75 of full scale; the ×10 output stage clips hard at 0.59 FS (Rev5) / 0.46 FS (Rev7) worst case, so the README's "protects the outputs" doesn't hold. Nothing is damaged. | Scale the limiter per board (`CheckBoardVersion()`): ceiling about 0.55 FS on Rev5 and 0.43 FS on Rev7, knee at 0.75 of that; or reword the README. |
| OUT is 0.9 dB below IN on a Seed Rev7 (audio B.unity_OUT_equals_IN.Rev7) | The Seed's 13.6k input loads the breakout's 1k (−0.62 dB), plus the PCM3060's full-scale ratio (−0.17) and the 100R into 10k (−0.09). Rev5 is −0.39 dB and passes. | README's first power-up step: "OUT ≈ IN within about 1 dB"; or default IN GAIN +0.9 dB on Rev7. |
| Low end (audio F.low_end_20Hz.whole_path, new) | −0.94 dB at 20 Hz on a Rev5 Seed: its 2.2 µF output cap into 47k ∥ (100R + R15 10k), plus the WM8731's 3.7 Hz high-pass. −0.13 dB at 50 Hz. | Accept; or R15 / R25 22k, R11 / R22 220k, C10 / C16 4.7p (−0.24 dB at 20 Hz). |
| CV scale spread (cv C.scale_spread) | Worst case 5.6 % (1 % resistors, the LP2985's ±3.5 % on 3V3A = VREF+ = VDDA), against ui.cc's "within a percent", so calibration fixes only the offset. | Correct the comment, or add a scale step to the setup page. |
| D1 alternates (clock_midi B.threshold_max_alternates, new) | The BOM allows SD103A and BAT86 (5 µA max leakage, against the BAT85's 2 µA): the clock threshold reaches 3.38 V at 60 °C, so a 5 V trigger keeps only 1.48× margin. | Drop SD103A and BAT86 from D1's line; BAT42 / BAT43, 1N5711, SD101 or a 1N4148 are fine (the 1N4148 leaks 25 nA). |
| SPI pin speed (logic E.sck_gpio_fmax, E.fast_option.sck_gpio_fmax, E.fast_option.st7789_tSCYCW) | libDaisy's SpiHandle sets SCK / MOSI to speed LOW, rated 12 MHz above 10 pF (DS12556 Table 61); SCK runs at 12.5 MHz. The SIDEFX_LCD_SPI_FAST option gives 24 MHz, also beyond the ST7789's 66 ns write cycle. | Set PG11 / PB5 to MEDIUM after `spi.Init`; say in the option's comment that it exceeds the ST7789's rating. |
| Firmware comment (logic A.doc.comment_need_at_3v3) | hal_daisy.cc says the 165 / 595 need ~20 ns at 3.3 V; that is TI's 4.5 V figure. Interpolated it is about 58 ns (100 ns at 2.0 V). The 125 ns settle covers it; at the 2.0 V bound three margins go to −15…+3 ns. | Say "~60 ns at 3.3 V"; raise `kSettleCycles` to about 90 if the chain ever misbehaves. |
| design.md's scan rate (logic A.doc.design_md_scan_rate) | The chain section says a 2 kHz timer; `kControlRate` is 4000. | 4 kHz. |
| H4 has no ground pin (netlist F.every_header_has_ground) | The six display lines (12.5 MHz SCK) return through GND_D_F tracks to HF3.2, 26–38 mm away, with no pour. | On a respin, a GND_D_F pin beside LCD_SCK; until then, lower the SPI clock if the display glitches. |
| GND_F sliver (netlist E.every_net_one_piece.face; pcb I.dead_copper.face, I.slivers.face) | The routing audit's floating piece, 0.012 mm² and at most 0.07–0.09 mm wide, at (64.1, 40.3) on the bottom layer; it can lift. | A no-copper area there (or island removal), then rebuild the pours. |
| Symbol pin names (netlist C.symbol_TL074_supply_names, C.symbol_74HC165.U1, .U2) | The TL074ACN symbol names pin 11 "GND" (it is VCC−, on −12V); the 74HC165 symbol names pin 15 "CE" (active low). The pads are right. | Rename to VCC− and /CE (easyeda_export.hc165_symbol() and circuit.py's comment). |
| J5's switch lugs (netlist I.design_md_J5_has_no_lugs; pcb A.pj366st_open_item) | design.md says "sleeve and lugs open"; the 3-pad footprint, circuit.py and the DRC list say no switch contacts. No PJ366ST maker drawing was found, so the slots (from an unmerged KiCad MR) are still unverified. If a real PJ366ST has switch legs, the footprint lacks holes. | "Sleeve open (no switch contacts)"; keep design.md's "check a PJ366ST against the slots" until one is measured. |
| Power cable (power A.cable; bom F.power_cable, F.power_cable_order) | The BOM still says "check the header's pin count (10 or 16)"; the breakout's J2 is a 2×5 (10-pin), confirmed by its BOM (LCSC C178292) and copper (pin 1 square, "RED STRIPE"). | A 10-pin (module) to 16-pin (bus) cable; regenerate thonk-order.md. |
| The breakout's own parts (bom F.breakout_built) | The line doesn't say where its parts list is. Its BOM has THT parts (the DC/DC, the 100 µF caps, the headers), and its Name column says TL084CPWR, though LCSC C96507 is a TL074CPWR. | Point the line at the rob-scape GitHub BOM, with M2's cap values. |
| Bus current undocumented (power E.doc_bus_current) | design.md and the README give no figure for a case's budget. | +12 V 64 mA typical / 106 mA max, −12 V the same, +5 V none. |
| R26 dissipation (power F.res_power) | A ±12 V op-amp output patched into MIDI puts 0.149 W into R26 (TL07x short-circuit 26 mA, typical): over half its 1/4 W. An unlimited source would give 0.58 W. The H11L1 stays within its 60 mA. | R26 as a 0.5–0.6 W part in the same body. |
| One rail missing (power G.one_rail.adc_injection) | With −12 V missing, a phase-reversing TL07x can push about 9.6 mA through 1k into an unpowered Seed's ADC pin (0 mA positive allowed). | Accept (rare fault), or clamps (copper). |
| C2 far from U2 (power H.decoupling.C2->U2.16, H.loop.C2-U2) | C2 is 14.3 mm (17 mm of track) from U2 pin 16; the loop back to U2's GND is 33.6 mm, with no GND_D_F pour. | Move C2 beside U2's pins 16 / 8 on a respin; a GND_D_F pour around U1 / U2. |
| C4's part (pcb A.c4_part) | bom.md names no part for "10 µF ceramic, 5.08 mm leads". | TDK FG28X5R1E106MRT06 (10 µF 25 V X5R, 5.0 mm leads, 5.5 mm tall). |
| TO-92 leads (pcb A.to92_leads.Q1) | The footprint is 2.54 mm pitch; a bulk 2N3904's leads are 1.27 mm apart. | BOM: a formed-lead part, or "spread the legs". |
| Value labels near a tie (pcb E.label_margin.main) | Six main-board labels are within 0.3 mm of a tie with a part of another value: "27k" in all four CV stages (0.35 / 0.38 mm to the 1k), "10k" R23 (0.35 / 0.38 to R22 15k), "1n" C12 (1.65 / 1.90 to R18). None is nearer the wrong part. | Legend lines, or re-run value_labels.py with the mixer's 0.3 mm margin. These labels change anyway if H1's values are applied. |
| Annular rings (pcb B.ring_rec) | EC11 tab slots 0.20 mm and the PJ366ST tip 0.245 mm, under JLCPCB's recommended 0.25 (above its minimum). | Grow those pads; the M4 change covers the EC11 slots. |
| design.md's routing rules (pcb B.via_design_md.main, .face, I.edge_design.main, .face, A.design_md_flat_resistors) | Vias are 0.61 / 0.305 mm, not 0.8 / 0.4. Copper is 0.35–0.36 mm from the edge (JLCPCB's 0.2 is met), not 0.5. The faceplate has no resistors to lie flat. | Correct design.md, or set the pour edge clearance to 0.5 and nudge CV3 at x 0.5. |
| Copper under the standoffs (pcb I.pads_under_hardware.face, I.tracks_under_hardware.face) | ENC4's A pad copper is 2.93 mm from the (19.3, 49.0) hole centre, inside a 5.5 mm hex standoff's corner radius. SR_CHAIN runs 1.15 mm from the (39.6, 33.1) hole's edge under the screw head. Both are under mask. | Nylon washers at those two holes (bom.md note), or a round standoff of 5 mm or less. |
| Ground under the plug tips (pcb I.tip_circle_ground) | The GND_F pour and stitching vias lie inside Thonk's 3 mm plug-tip circle under all ten barrels; no signal copper is there. | Optional: no-copper circles at the barrel centres. |
| Panel text weight (panel E.text_ratio) | Every panel string's stroke is 1:8.1 of its height; JLCPCB prefers 1:6. Its hard minimums are met. | A house-wide setting in panel_pcb (stroke about size / 6.5). |

## Docs

design.md, README and code-comment figures that the design does not match.
They are all in the tables above; this list collects them.

- The panel gap is 9 mm, not "about 7 mm" (README, the skill's panel.md, the routing audit): M5.
- "A 2 kHz timer" in design.md's chain section: the firmware runs at 4 kHz.
- Vias 0.8 / 0.4 mm and copper 0.5 mm from the edge (design.md's routing notes): 0.61 / 0.305 mm and 0.35 mm as routed.
- "On the faceplate they lie flat": the faceplate has no resistors.
- J5 "sleeve and lugs open": the PJ366ST footprint has no lugs.
- No bus current anywhere; no breakout orientation (M1); no note on clipping the button feet (M6).
- hal_daisy.cc's "~20 ns at 3.3 V"; ui.cc's "the scales hold within a percent"; the README's "OUT should equal IN" and "the limiter protects the outputs".
- parts.md: "Bourns PEC11R uses the same pattern" (M4).

## Outside Side FXy

- **Six modules wire the 16-pin power header off the standard** (found by the
  power group, confirmed by hand). stereo-mixer, attenuverter, atlas, vca,
  sample-hold and buffered-mult map 1–2 −12 V, 3–10 GND, 11–12 +12 V.
  - **Doepfer's bus:** 1–2 −12 V, 3–8 GND, 9–10 +12 V, 11–12 +5 V.
  - **The mixer's copper:** its routed J18 carries the wrong map in standard zigzag numbering.
  - **On a real bus:** the bus +12 V is shorted to the module's GND.
  - **Detail:** `URGENT-16pin-power-header.md` in the side-session notes.
  - **Side FXy:** not affected. Its power comes through the breakout's J2, traced correct: 1–2 −12 V, 3–8 GND, 9–10 +12 V. D2 / D3 face the right way.
- **Marblesy** has the same CV stage and the same overvoltage (H1), and the same faceplate socket stack (M8). Its own report lists them as M1 and M2.
- **The LED button height (M6)** concerns every module that puts Thonk LED buttons beside Thonkiconns.

## What the verifiers fixed in the tests

Twenty-odd test bugs, each marked in its file ([verifier] / VERIFY 2026-11-13). Main ones:

- **pcb:** the panel gap was 6–7 mm instead of Thonk's 9.0 mm. The encoder heights are now measured from the bushing base.
- **pcb:** U5's "no mirror" fit used the drill pattern's symmetry. It is now a fit with the pins named from the breakout's copper: 0.000 mm mirrored, 15.24 mm as drawn.
- **pcb and panel:** checks that could not fail now work from the boards. These were the tail lengths, the facing parts, and the EC11 slots against their own source.
- **bom and pcb:** the PEC11R's 13.2 mm was read as the tab pitch; it is the outer-edge span. The nut's 10 mm is across flats.
- **audio:** the Seed's coupling parts were assumed (4.7 µF, open). They are now the Seed's real 2.2 µF / 47k. That moved the DC offset (63 mV worst, still passing) and the low end.
- **audio:** gains used the real part instead of the magnitude. The ADC's digital high-pass was added.
- **cv:** the FT pins' cap was 6.8 V; Table 120 gives 5.5 V.
- **power:** the display's BL drive current (3 mA through 1k into the module's S8050) was missing from the 3V3D load.
- **clock_midi:** only the BAT85 was checked, not the BOM's leakier alternates.
- **logic:** the LED-PWM model dropped every TIM3 update during the audio callback; it now passes at 125 Hz worst case. Fmax is now read from the datasheet row, not interpolated.
- **netlist and pins:** a 74HC165 pin map compared with another test constant, a breakout ground check compared with itself, and a `check(True)` for check_pins.py. All now read the sources.

## What the suite could not check

- **Thonk parts.** Thonk blocks fetches:
  - The LED button's pinout (pins 1–6 from parts.md) and its height (M6).
  - The Thonkiconn's shoulder and lug sizes; a builder measured 10 mm where the drawing says 9.
  - The PJ366ST's pins and lugs: there is no maker drawing at all.
- **The Seed.**
  - Its supply current: Electrosmith publishes none.
  - Rev7's audio levels: a forum thread and a user's reading of the schematic; the output network is assumed equal to Rev5's.
  - The LP2985's grade, and the TPS6217x's accuracy and efficiency.
  - Which Seed revisions libDaisy v9 detects beyond Rev5 / Rev7 (AK4556 Rev4, a Daisy Seed 3).
- **Other parts.**
  - The H11L1 at 3.3 V: guaranteed 3–15 V, thresholds from Motorola's typical curves.
  - The B5819W's VF below 1 A.
  - The ST7789V2's own timing table (the ST7789V's is used).
  - The PEC11R push switch's bounce.
  - The Waveshare module's stud height.
- **Assumed.** The bus tolerance (±5 %; Doepfer publishes none), the 5.5 mm hex standoff, header contact ratings, track and cable capacitance, 60 °C inside the case, and a 60 mm case depth. The module is about 52 mm deep with the Seed in sockets on the breakout: too deep for a 40 mm skiff.
- **Not modelled.** Noise, crosstalk and ground loops between modules; the power-up thump through the ×10 output stage; Gerber-level mask and silk clipping; the TXS0108E's one-shots on the display module; the real CPU load (85 % is the README's estimate).
