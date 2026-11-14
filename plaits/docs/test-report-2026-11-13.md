# Plaitsy hardware test suite, 2026-11-13

A hardware design test suite for Orchid, modelled on the stereo mixer's of
2026-11-04: eight groups in `hardware/tests/`, each written and run by one
agent. Three independent verifiers then re-derived every failing check from
the datasheets. They fixed the test bugs they found: checks that compared a
constant with itself or could not fail, limits read at the wrong conditions,
unsourced constants. They also settled the points where groups disagreed.
Everything is checked against `circuit.py`, the routed master
`Plaits-routed.epro2`, the generated `Plaits.epro2`, `design.md`, `bom.md`,
the routing audit, the firmware in `firmware/src/`, Rob Heel's breakout
(its BOM, Gerbers and photo), libDaisy v9.0.0, Mutable's Plaits sources and
schematic, and the manufacturers' datasheets. The suite only reads: nothing
in tools/, easyeda/, panel/, bom/, docs/ or firmware/ was changed, and
nothing below has been fixed yet.

```bash
cd plaits/hardware/tests && python run_tests.py
```

| Group | Checks | First run | After verification | After the fixes (11-14) | What it covers |
|---|---|---|---|---|---|
| netlist | 172 | 2 | 2 | 0 | pinouts and polarity from datasheets and the real symbols and footprints, every routed pad's net, header stacking, schematic pages, design.md's tables, board_tables.h |
| firmware | 366 | 4 | 6 | 1 | pins through libDaisy and the Seed pinout to the routed copper, LED bits, mux channels, ADC timing, SPI to the 595s, the CV conversion end to end against Plaits' own front end, thresholds as jack voltages, flash and watchdog |
| analog_dc | 185 → 186 | 20 | 21 | 12 | MNA solve of both boards: the CV stages at worst case, over-range, the V/OCT clamps, the probe, pots through the mux, LED and button-LED currents, ground |
| analog_ac | 84 → 83 | 3 | 3 | 1 | CV bandwidth, phase margins, sampling and aliasing, ADC settling, mux switching, trigger latency, the probe in time, crosstalk, noise |
| power | 201 | 15 | 15 | 12 | the breakout's power entry (traced from its Gerbers), reverse protection, the DC/DC, current budget, the Seed's regulators, decoupling, power tracks, sequencing and missing-rail faults |
| pcb | 143 | 19 | 20 | 10 | footprints against datasheets and the breakout's drill file, drills and rings against JLCPCB, outline and holes, value labels, bodies, stacking gap, pours, tracks |
| panel | 676 → 678 | 22 | 23 | 21 | holes in nine representations, Eurorack mechanics, front clearances, heights and depth, labels and silk, the house frame, Mutable's own panel |
| bom | 63 → 60 | 9 | 9 | 2 | bom.py against circuit.py, the committed files and the routed boards, quantities, part numbers, ratings, clamp-diode alternatives, the Thonk order |
| **all** | **1891 → 1889** | **94** | **99** | **59** | |

**2026-11-14: the no-copper fixes are applied** (the user's OK). The
section [Fixed 2026-11-14](#fixed-2026-11-14-no-copper-changed) lists what
changed and [Still open](#still-open) what is left. In short: M1, M3, M4,
M8 and most low findings are done in the BOM, the docs, the firmware and
the routed master's silkscreen and part data. **M2 is now confirmed**:
the user measured their 3-lead LEDs at 2.54 mm (Ringsy, 2026-11-14), and
Plaitsy's LED footprint was 1.27 mm. The user first chose to jog the leads,
then (later on 2026-11-14) to re-pitch the footprint to 2.54 mm. That was
scripted into the routed master like M6 / L10 / L17, and the user routed
all of it the same day. The re-import and the rebuilt pours were synced on
2026-11-15 (47 failing, all open or accepted). M7 is accepted as documented.

The verifiers' fixes cleared 4 first-run failures: the panel's
caps-in-the-gap check, the pcb's two via-to-track checks and analog_dc's
V/OCT high-pin limit. They turned up 9 more. Seven of those are checks
that had passed only through a test bug: the green LED at Tayda's real VF
(×2), the LED pitch, the typical stacking gap, a body overlap at FG28
size, the README pitch window and the V/OCT low end. Two are new panel
checks of OUT / AUX against Plaits. The 99 failing checks are **32
distinct findings**, none high. Eight are
medium. Four of them, M2, M6, M7 and possibly M3, are worth deciding
**before the boards are ordered**, because their fix touches copper or
the parts to buy.

The routed copper itself holds up. Every one of the 425 pad nets matches
circuit.py on both exports. All 26 header pins stack with the right net
pairs. The breakout footprint lands on all 56 holes of Rob Heel's drill
file, and the nets agree with his Gerbers. The firmware's 20 pins, 16 LED
bits and 7 mux channels reach the right parts through the copper.

---

## Before ordering

| | Decide | Why now |
|---|---|---|
| M2 | **Decided 2026-11-14: re-pitch to 2.54 mm** (first "jog the leads", then "do all recommended fixes", option A: keep the 1/4 W resistors). `LED-3MM-3P` is Ringsy's footprint now, and R88 / R92 moved. The user routed it on 2026-11-14. The import reverted the footprint, and a script restored it on the user's routing (see "Faceplate copper" below) | **confirmed 2026-11-14**: the user's own 3-lead LEDs measure 2.54 mm (Ringsy's footprint was changed to that the same day), Kingbright's L-3WEGW is 2.54 mm too, the footprint is 1.27 mm |
| M1 | Which bicolour LED to buy | Tayda's only one has a 2.8–3.0 V green, which is nearly dark at 3.3 V. The replacement's pitch feeds M2 |
| M6 | A short 3V3D_F track from C10 to U10 pin 16 (and C9 to U9 pin 16) | U10 has no decoupler within 49 mm of track |
| M7 | Schottky clamps on the seven wide ADC lines, or a TL074H | a fault-only risk, but the fix is copper |
| M3 | Sockets or not for U1 / U9 / U10 | no copper; it changes what you buy |

---

## Medium

**M1. The green LEDs are nearly dark** (bom 4.LED_green_lit_at_3V3,
4.design_md_LED_current_typ; analog_dc I.current_typ.G, I.current_min.G;
power C.design_md_LED_current; firmware A.led_part_named).
- The part: Tayda sells one 3 mm red/green common-cathode 3-lead LED, A-8599. Its page gives red VF 1.8–2.2 V and green 2.8–3.0 V (an InGaN-class green, at 20 mA; two verifiers re-read it).
- The current: from a 74HC595 at 3V3D through 470 Ω, green gets 0.77 mA typical and 0.25–0.31 mA worst, red 2.5 mA.
- What you see: the green bank is dim, and "yellow" (both on) comes out red-orange.
- The docs: design.md says "about 3 mA per colour", and bom.md names no part, so nothing fixes lead 1 as the red anode, which the firmware's bit tables assume.

Fix: a bicolour with a GaP green (VF about 2.1 V typ, 2.5 V max), e.g. a
Kingbright L-3WEGW / WP937EGW-class part. Name it in bom.py with its lead
order (lead 1 red anode, cathode in the middle), check its pitch (M2), and
correct design.md to the real currents. Raising the green resistors'
current instead (R88–R95 to 100 Ω) cannot work at worst case (VF 3.0 V
against 3V3D at −4.5 %).

**M2. The LED footprint's pitch is 1.27 mm; the LEDs it should take are
2.54 mm** (pcb A.led_pitch, C.ring_min).
- The footprint: `LED-3MM-3P` (easyeda_export.py, "1.27 mm pitch (Tayda, Kingbright)") has 0.8 mm holes in 1.1 mm pads at 1.27 mm.
- The LED: Kingbright's L-3WEGW drawing, rendered from its vector PDF, kinks the leads out to 2.54 mm and recommends 0.889 mm holes. Tayda's listing gives no pitch.
- The pads: they leave a 0.15 mm ring across the pitch, under JLCPCB's 0.18 mm absolute minimum. The 1.7 mm oval still carries the copper.

**Confirmed 2026-11-14:** the user measured their 3-lead LEDs at 2.54 mm
while placing Ringsy, whose footprint was re-pitched the same day. Fix:
**the first way, re-pitching the footprint** (the user's go-ahead for all
recommended fixes, 2026-11-14, after first choosing to jog the leads); see
"Faceplate copper" below. The two ways were: re-pitch `LED-3MM-3P` to 2.54 mm with 0.9–1.0 mm holes and 1.5 mm
pads (a faceplate copper change around the eight LEDs, which also cures
the ring), or bend the outer leads 1.27 mm inward at assembly (build
note). This would be high if the LEDs are 2.54 mm and leads are not to be
bent. Rings' exporter and Marblesy's panel.py name the same footprint;
worth the same look there.

**M3. The faceplate's three DIP-16s in sockets don't fit under the main
board** (pcb H.gap_worst −1.54 mm, H.gap_typical +0.07 mm against 0.5
wanted).
- The gap: 11.04 mm, from 8.5 mm sockets plus the male headers' 2.54 mm plastic (FCI BergStik).
- What sits above each chip, on the main board's underside:
  - over U10, the female-header tails for the breakout (U2.34–36), which are not clipped;
  - over U9, U3's socket tails and standing-resistor leads;
  - over U1, R45 / R47.
- The stack under them:
  - A stamped DIP-16 socket is 5.10 ±0.15 mm (Assmann A 16-LC-TT). A turned-pin one is 4.19 ±0.25 mm (Mill-Max 110-43-316).
  - A PDIP-16 is 5.33 mm max seated (JEDEC MS-001); TI's own MPDI003 says 5.08.

Fix (no copper): solder U1, U9, U10 straight in (5.33 mm max, 3.8 mm to
spare) and drop the three DIP-16 sockets from the BOM. Or name turned-pin
sockets and add a build note to clip the main board's leads and U2's tails
flush over them (+0.98 to +1.53 mm).

**M4. Nothing says which way up the breakout goes** (pcb
B.breakout_orientation_doc).
- How it mounts: SMD side towards Plaitsy's main board, with the Seed, the DC/DC, both 100 µF caps and J2 on top. The breakout's Gerbers show it (paste only on the Gerber top; the bottom silk reads mirrored and carries every through-hole part), and so does Rob Heel's photo.
- What the Seed needs: long-tail female headers whose tails reach about 5.8 mm into Plaitsy's sockets. The 1x4 male headers sit under the breakout.
- The other way up: the drill pattern mirrors, every pin lands on its mirror image, and ±12 V reaches the op-amps reversed.

Neither design.md, bom.md nor the README says this, and the breakout's
own silkscreen points the 1x4 headers the other way. Fix: a build section
in design.md and the U2 header line in bom.py (long-tail female headers
for the Seed; the 1x4 male under the breakout).

**M5. The 5 V DC/DC can run past its 1 W** (power C.DCDC_load_worst:
253 mA against 200 mA).
- The supply: the breakout's Mornsun B2405S-1WR2, 200 mA max.
- Typical load: 148 mA (74 %), with the Seed at a forum-measured 140 mA. The Seed's datasheet gives no supply current.
- Worst case: the STM32H750's Tj 25 °C maximum at the 480 MHz main.cc sets (DS12556 Table 127: 226 against 148 mA typical), plus all 16 LED lines and both button LEDs (ui.cc lights all eight yellow in the octave display), through the Seed's TPS62170 buck.
- At 85 °C: worse.

Not stacked impossibilities, but the base figure is unsourced. Fix: measure
the 5 V current at bring-up with the firmware running and all LEDs lit; if
it is above about 180 mA, cap the LED duty in the firmware or fit a 2 W
converter on the breakout.

**M6. C10 doesn't decouple U10, and C9 is far from U9** (power
F.C10_at_U10.16, F.C9_at_U9.16; pcb G.decouple_fb, G.decouple_lean).
- C10: on the routed faceplate it hangs on the HF3 3V3D_F feed at (12.66, 69). Its track to U10's VCC pin 16 is 80.9 mm though the parts are 11.1 mm apart, a supply loop of 89 mm.
- U10: has no capacitor within 49 mm of track.
- C9: 25.1 mm of track from U9 pin 16, because it stands at the pin-8 end.
- C8: 3.0 mm from U1, as design.md says.
- The body: C10 also leans 0.67 mm over U10's socket frame.

The 595s switch 16 LED lines and clock at 1.56 MHz; with no local
decoupling, ground bounce can corrupt a frame (LED flicker). Fix (copper,
faceplate): a 3V3D_F track from C10 pad 1 (12.66, 69.0) to U10 pin 16
(7.51, 78.81), or move C10 there; the same for C9 at U9 pin 16. Or accept
it and watch for flicker.

**M7. With −12 V missing, the seven wide channels can put +10 V on
unpowered ADC pins** (power I.-12V_missing … TL074 inputs, … ADC pin
≤ 4.0 V; analog_dc E.wide_rail_neg, E.wide_rail_pos,
E.voct_rail_neg.esd).
- The op-amps: if the −12 V rail is lost (a cable half on, a failed bus), the TL074s run on +11.7 / +0.3 V, with their inputs far below the common-mode range (TI SLOS080W: V− + 4 V for the old die, V− + 1.5 V for the TL07xH).
- The worst case: an old-die TL074 that phase-reverses drives its output to about V+ − 1.5 V (a typical headroom, not a datasheet figure).
- The pins: that goes through only 1 kΩ into ADC pins rated 4.0 V absolute with VDD = 0 and no positive injection (DS12556 rev V Tables 117/118). Only V/OCT has clamps.
- Linear stages: the highest pin is 2.55 V, inside the limit.
- A stuck output: a section held at a rail injects 9.5 mA, against 5 mA.

A ±12 V input alone cannot cause this. Fix: BAT85 / BAT54S clamps on the
seven wide ADC lines as on V/OCT (copper), or order TL074H (new die, no
phase reversal) and note it in the BOM; or accept it as fault-only.

**M8. The jacks, pots and buttons sit at three different heights**
(panel E.jack_and_pot_heights_agree, E.button_not_held_pressed,
E.design_md_button_at_jack_height).
- The heights:
  - Thonk's PJ398SM drawings both give a 9.0 ±0.15 mm body.
  - Alpha's RD901F drawing gives 10 ±0.5 mm to the bushing shoulder.
  - The low-profile button's cap base sits 9.85 mm up with the feet clipped (Thonk LowProfileButton.pdf).
- What happens: the panel rests on the pots and every jack hangs 1.0 mm below it until its nut pulls it up.
- The buttons: they clear the panel by 0.15 mm typical, and at the tolerance corners the panel holds them pressed (−1.15 mm).
- The docs: design.md's "the body sits on the board at Thonkiconn height" is 0.85 mm out, and parts.md's "9.5–10" and panel.md's "about 7 mm" disagree with the drawings.

Fix (build note, no copper): fit the panel with every nut tight before
soldering jacks, pots and buttons; check both buttons click and spring back
with the panel on. Measure one jack and one pot to settle the parts.md
figures.

---

## Low

| Id | Finding | Failing checks | Fix |
|---|---|---|---|
| L1 | **V/OCT has no margin at either end.** Plaitsy reads −2.875…+7.125 V nominal against Plaits' −2.857…+7.143 V, the same 10.00 V span, and clips 18 mV earlier at the top. At the worst corner (1 % parts, LP2985 3V3A ±3.5 %) it reads only −2.58…+6.67 V, so a +7 V pitch CV can clip, which calibration cannot fix. design.md's "−2.9 … +7.1 V" is nominal only. | firmware F.voct_reach_high, F.voct_reach_worst.high, F.voct_reach_worst.low; analog_dc B.voct_low_end_worst, B.voct_high_end_worst | R43 33k → 30k (E24) and `kPlaitsyVOct` g = 0.30 in cv_adc.cc: worst case −3.06…+7.21 V. A value swap plus a firmware constant; update design.md. |
| L2 | **The pot mux gets too little ADC sampling time.** libDaisy v9's default 8.5 cycles is 1.38 µs. The pot path (2.5k wiper, the 4051's Ron at 3.3 V, which no maker specifies, and onsemi's 130 pF max common capacitance, with no series resistor) needs about 1.5 µs (ST's DS12556 table 183, 16 bit). The firmware uses the 16-bit value. Worst-case error 86 LSB16 = 5 LSB at Plaits' 12 bits = about 13 cents on FREQUENCY; typical 0.16 LSB16. With a CD4051B (bom.md: "also works") it is 59 LSB16, and TI specifies its Ron only from 5 V up. | analog_ac D.sample_hold.pots, D.table183.pots_16bit, D.sample_hold.pots_CD4051B; bom 4.CD4051B_specified_at_3V3 | Firmware: `InitMux(..., AdcChannelConfig::SPEED_32CYCLES_5)` in hal_daisy.cc (0.015 LSB16; the scan grows 204 → 235 µs, still inside the 250 µs block). bom.py: drop "CD4051B also works". |
| L3 | **V/OCT tracking drifts with the clamps' leakage.** D21 / D22 leak through R44 (1k). After a 25 °C calibration, typical drift to 55 °C is 1.1–2.8 cents (Vishay BAT85S Fig. 2 to 1 V, Philips Fig. 4). One diode at the datasheet maximum, carried down from 2 µA at 25 V, gives 22 cents. | analog_dc F.bat85_typ_55C, F.bat85_max_drift.D21, F.bat85_max_drift.D22 | BAT43 for D22 (0.5 µA max at 25 V, VF 0.33 V at 2 mA); a low-leakage diode for D21 (PA1 is FT_ha, so VF matters less there); or a "calibrate warm" line in the README. |
| L4 | **The breakout's power header is unshrouded and the cable is unnamed.** J2 is Amphenol 67997-210HLF (FCI BergStik II, 2×5, no shroud). It matches the Doepfer 10-pin pinout and both B5819Ws face the right way, so a reversed 10-pin cable is safe. But a socket one row off can short a bus rail to the breakout's GND (10 placements), and 4 placements of a 16-pin socket power one rail only. bom.md still says "check the header's pin count (10 or 16)": it is 10, which closes that open question. | power A.J2_shrouded, A.cable_misplaced_no_half_power, A.cable_misplaced_no_bus_short, A.BOM_cable_names_10_pin; bom 3.power_cable_10_pin | bom.py (all three copies that carry the breakout) and bom/thonk-order: a 10-to-16-pin cable. Build note: red stripe at J2 pin 1 (square pad, "RED STRIPE" on the breakout's silk). A shrouded 2×5 box header if its ~20.3 mm fits the 18.8 mm breakout. |
| L5 | **No document gives the ±12 V current.** Computed: typical +62 / −62 mA, worst +127 / −119 mA, with the DC/DC drawing 40 mA typ / 81 mA worst on both rails. | power D.doc_states_the_+-12V_current | Add it to the README and design.md. |
| L6 | **D21 pushes current into 3V3A, which comes from an LDO that cannot sink.** At −12 V on V/OCT, D21 carries 2.7 mA into 3V3A, against 2.2 mA of Plaitsy's own 3V3A load. On a rev 5 Seed the WM8731 (13.1 + 1.7 mA typ) and VDDA absorb it; later Seeds (PCM3060) are not covered by any source. At power-up, before the Seed's regulators run, the same path lifts 3V3A to about 2.2 V while VDD is 0, which breaks DS12556's sequencing rule (the Seed's ~55 µF delays it 4.9 ms). | power C.3V3A_clamp_current_at_-12V, I.powerup_3V3A_back_fed_by_D21; analog_dc E.voct_3v3a_backfeed | At bring-up, measure 3V3A with −12 V into V/OCT. If it rises: a 3.3k bleeder from 3V3A to GND, or a larger R44 (see L2's sampling time for the CV side). |
| L7 | **D22 lets PA1 reach −0.34 V.** At the worst negative clamp current (1.8 mA), a maximum-VF BAT85 (0.341 V) holds V/OCT's pin below DS12556's VSS − 0.3 V. The STM32's own diode carries about 0.3 µA, so it is harmless. | bom 4.D22_holds_PA1_within_VSS-0.3V; analog_dc E.voct_pin_low | Note it in design.md, or BAT43 for D22 (L3). |
| L8 | **Two of the BOM's clamp alternatives clamp too late.** 1N5711 and SD101 are 0.41 V at 1 mA and about 0.46–0.54 V at the clamp currents (ST / Microsemi LDS-0040, Vishay 85629), so the STM32's own diode would share the current. BAT86, BAT43, BAT42, BAT46 and SD103A pass. | bom 4.clamp_diode.1N5711, 4.clamp_diode.SD101 | Drop both from bom.py's BAT85 line. |
| L9 | **A missing rail browns the Seed out with VDDA above VDD.** With one bus rail at 0 V the DC/DC gets 11.4 V and the Seed's VIN about 2.4 V: its TPS62170 buck stops (UVLO 2.6–2.82 V) while its LP2985 keeps VDDA near 2 V. This comes from the breakout's own design. | power I.-12V_missing … VDDA, I.+12V_missing … VDDA | Build note. |
| L10 | **The 595s' inputs float while the Seed is in reset.** No pull resistors on SER, SRCLK or RCLK. STM32 GPIOs reset to analog mode, so they float for the ~2 s of bootloader at every power-up, for as long as it waits for an upload, and in any reset. main.cc's "the 74HC595s hold it while the bootloader waits" is true only if no edge arrives; the LEDs may show garbage. | firmware C.595_inputs_defined_while_seed_in_reset | 100k pull-downs from SCK_F and LED_LATCH_F to GND_D_F (copper), or reword main.cc and the README. |
| L11 | **The README understates the uncalibrated pitch error.** "Most of a semitone off, the octaves ten cents or more out". 1 % resistors alone give up to 122 cents of offset; with TL074 Vos and the ADC's leakage, 173 cents. The scale error is 24 cents per octave from the resistors and 54–66 cents with 3V3A's ±2.5 % (VREF+ = 3V3A scales the jack signal, not the ratiometric bias). | analog_dc D.readme_semitone, D.readme_total_offset, D.readme_total_scale; firmware F.readme_uncal_pitch_offset | README: "more than a semitone off (up to about 1.7) and the octaves up to about half a semitone out". |
| L12 | **design.md's "the full ±12 V stays inside the ADC range" holds at nominal only.** At the worst corner (LP2985 ±3.5 %) the pin goes 18 mV below 0 V and 39 mV above 3V3A. Every Plaits input range still fits. | analog_dc B.inside_low.+12V, B.inside_high.-12V | design.md: "±12 V nominal, about ±11.7 V worst case". |
| L13 | **The firmware's probe-low subtraction is good to ±8.4 mV.** That is 5.2 mV from 1 % resistors and 3.0 mV from the probe pin's VOL carrying five lugs, against one 12-bit step (6.2 mV at the jack). It stays in the calibrated zeros of the five normalized inputs: at most about 6 cents of FM at full attenuverter. | analog_dc G.fw_probe_low_residual | Accept, or note it in the firmware README. |
| L14 | **The button LED colour must be a GaAsP / GaP one.** Known open item; this narrows it. From a 3.3 V GPIO through R60 / R61 (470 Ω), red, orange, yellow or yellow-green get 2.6–2.8 mA. Blue, white or pure green get 0.6 mA typical and nothing at worst. Thonk's drawing PB01-109TL lists only GaAsP / GaP LEDs. | analog_dc J.current.green_InGaN, J.current.blue, J.current.white; bom 4.button_LED_colour_named | Name red, orange, yellow or green in bom.py's BUTTONS. |
| L15 | **Main-board value labels point at the wrong part** (the mixer's M3, not yet ported here). 8 traps: six "100k" labels sit 0.38 mm from a 1 nF Cf and 2.95 mm from their resistor; two lie between C32 / C34 and R27 / R39. 9 ties within 0.3 mm ("13k" against the neighbouring 1k ×7, "33k" / 1k, "15k" / 12k). Two labels are 38 mil (0.97 mm), under JLCPCB's 1.0 mm. All labels and designators are a 6 mil line on 45 mil text (1:7.5; JLCPCB prefers 1:6). The 31 faceplate labels are clean apart from the ratio. | pcb F.label_traps.main, F.label_ties.main, F.label_height.main, F.label_ratio.main, F.label_ratio.face | Copy the mixer's value_labels.py (0.3 mm margin, 45 / 40 mil, legend lines) and re-label the main board of the master. Silkscreen only. Optionally an 8 mil line. |
| L16 | **Bodies touch at the largest part sizes.** With the largest dipped MLCC (5.08 × 3.18 mm), C21–C28 / C31–C34 touch the standing resistors (Yageo MFR max D 2.6 mm) by up to 0.35 mm, and C24 / C28 touch D21 / D22. At TDK FG28 size it is 0.01 mm. The flat faceplate LED resistors at 2.4 mm pitch touch by 0.2 mm at D 2.6 mm. Hairlines: U1's socket over RV5's lug pad (0.09 mm), HF3 over RV4's (0.03, known), R88 / R92 over D2 / D7 pads (0.02). H2 / H3's plastic covers the outer 0.10 mm of 17 U2 pad rings. | pcb G.bodies.main, G.bodies_small_caps.main, G.bodies.face, G.rear_over_joints, H.female_on_joints | bom.py: name FG28-size (≤ 4.0 × 2.5 mm) ceramics and a ≤ 2.5 mm thick 1 nF film. Build note: keep the U2 fillets under H2 / H3 flat. |
| L17 | **The library DIP-16 has a round pin-1 pad** (every other footprint here has a square one; the silk dot is there). | pcb A.dip_pin1_pad.DIP-16 | Optional. |
| L18 | **The breakout's own header holes are tight.** Its 1x4 / 2x5 holes are 0.889 mm, under FCI's recommended 1.02 ±0.08 mm for a 0.64 mm square post. Rob Heel's own build has headers in them. | pcb B.breakout_header_holes | Build note. |
| L19 | **bom.md says R60 / R61 stand up;** on the routed board they lie flat on the 10.3 mm footprint, as design.md says. | bom 4.note_standing_resistors; pcb G.bom_standing_note | bom.py NOTES: "R21–R48". |
| L20 | **The EasyEDA pot device names the wrong part.** Both exports put Bourns PTV09A-4025F-B103 (LCSC C7262626) on RV1–RV7, whose lugs don't fit the Alpha footprint they sit on. An LCSC BOM export would order the wrong pot. No copper effect. | netlist D.routed.pot_device_is_the_Alpha, D.generated.pot_device_is_the_Alpha | The POT device's part to the Alpha (or none) in easyeda_export.py, and the attribute patched in the routed master. |
| L21 | **Nothing says how high the LEDs stand.** Their Ø4 flange can't pass the 3.2 mm hole (Kingbright), so the flange back must sit 6.6–9.0 mm above the faceplate. | panel E.docs_say_how_high_the_LEDs_stand | Build note: solder the LEDs pushed into their holes with the panel fitted, or 7 mm spacers. |
| L22 | **52.5 mm behind the panel.** That is 10 mm (the panel to the faceplate board) + 3 boards + two 11 mm header gaps + the Seed's parts; an Intellijel Palette gives 45.5 mm. The user's case depth is unknown. | panel E.depth_behind_panel | Check the case. If it is too shallow, solder the Seed straight onto the breakout (−11 mm). |
| L23 | **Panel silk.** The "FM" icon glyph has a 0.133 mm stroke, under JLCPCB's 0.15. The dotted lines from the two buttons start 0.08 mm inside their Ø6.5 holes. OUT / AUX are white silk on the bare-gold band, and JLCPCB's CAM clips silk at mask openings (its blog), so they would vanish; design.md already names the fallback. "Orchid" may run into "Macro oscillator" by panel_pcb's own width estimate (unclear; the artwork is fine). | panel F.silk_text_height_and_stroke, F.silk_clear_of_holes, F.OUT_AUX_not_silk_on_bare_copper, G.PCB_title_clear_of_subtitle | panel_pcb.py / panel.py: glyph strokes ≥ 0.16 mm; start the button dots at hole radius + 0.5; knock OUT / AUX out of the band's copper and mask (or put them on the mask layer); check the title after import. |
| L24 | **Not quite "the same places" as Plaits.** Against Mutable's `plaits_v50.ai`: the buttons are 0.71 mm off, FREQUENCY / HARMONICS 1.0 mm, TIMBRE / MORPH 1.75 mm, the attenuverters 0.7, the bottom jack row 0.6. The top jack row and the LEDs are within 0.5 mm. Plaits' LED pitch is 5.40, not 5.3. | panel H.plaits_position.* (14 checks) | None needed (knobs and labels are Plaitsy's own); soften design.md's "same controls in the same places". |

---

## Fixed 2026-11-14, no copper changed

The routed master's copper audit is identical before and after, and
`easyeda_export.py` reports 0 schematic and 0 PCB problems against it. The
user re-imports `Plaits-routed.epro2` before making Gerbers.

| Finding | What changed |
|---|---|
| M1 green LEDs | bom.py names the Kingbright L-3WEGW (Mouser): red GaAsP/GaP 2.0 / 2.5 V, green GaP 2.2 / 2.5 V, lead 1 red anode, cathode in the middle, 2.54 mm leads. About 2.5 mA red and 2.1 mA green typical, 1.1 mA green at worst. design.md says "about 2.3 mA per colour" and why not Tayda's A-8599. |
| M3 stacking gap | bom.py `SOLDERED`: U1, U9, U10 without sockets (no DIP-16 sockets in the BOM), a BOM note and a design.md build note. The gap check now passes with 2.6 mm to spare at typical sizes. |
| M4 breakout orientation | A new [Building](design.md#building) section in design.md and a BOM note: SMD side down, the Seed on top, long-tail female headers, the 1×4 male headers pointing down. |
| M5 DC/DC load | A bring-up measurement in design.md (the 5 V current with all LEDs lit; what to do above 180 mA). The check still fails: 261 mA at the datasheet maxima now that the green LEDs draw their share. |
| M8 heights | Build notes: fit the panel before soldering the jacks, pots and buttons, and check that the buttons click. design.md's "at Thonkiconn height" is replaced by Thonk's 9.85 mm. |
| L1 V/OCT range | R43 33k → 30k in circuit.py, the generated project and the routed master (the LR1F33K device docs renamed LR1F30K, the schematic text, the silk label). `kPlaitsyVOct` g = 0.30 in cv_adc.cc. It now reads −3.3 … +7.7 V nominal and −3.0 … +7.2 V at the worst corner, so Plaits' range always fits. |
| L2 pot sampling | hal_daisy.cc: `InitMux(..., SPEED_16CYCLES_5)`. The worst-case pot error falls from 86 to 4.8 LSB16 (0.3 of Plaits' 12-bit step) and the scan from 0.20 to 0.21 ms. 32.5 cycles would settle fully but bring the scan to about 0.23 ms; the firmware's own host test loses a TIMBRE data transfer at a 0.245 ms sequence, so 16.5 it is. "CD4051B also works" is gone. |
| L3 / L8 clamp diodes | The BAT85 line prefers BAT43 for its lower leakage and drops 1N5711 and SD101. The firmware README says to calibrate the module warm. |
| L4 power cable | The BOM's cable is a 10-to-16-pin one with the red stripe to J2's RED STRIPE (another session's catalogue change, now in the regenerated BOM); a build note about the unshrouded header. |
| L5 current | README and design.md: about +62 / −62 mA typical, +129 / −122 mA worst on ±12 V. |
| L6, L7, L9, L10 | design.md bring-up and fault notes; the main.cc comment and the firmware README on the 595s' floating clocks. |
| L11 uncalibrated pitch | The firmware README now says up to about 1.3 semitones and 25 cents per octave from 1 % resistors, and about 1.9 semitones and 60 cents with 3V3A and the op-amp. |
| L12, L13 | design.md: ±12 V nominal, about ±11.7 V at the worst corner; the firmware README: the probe-low residual of up to about 8 mV. |
| L14 button LED | BOM: red, orange, yellow or green (GaAsP / GaP); design.md says why. |
| L15 value labels | value_labels.py ported from the mixer (0.3 mm margin, 45 / 40 mil text, legend lines, 8 mil stroke), with a step that first takes out an earlier run's labels. The master was re-labelled: 31 labels on the faceplate, 24 labels and 16 legend lines on the main board (C31–C34 now carry "100n"). No traps, ties, short text or thin strokes are left. |
| L16, L18, L19, L21, L22, L24 | BOM and design.md: small capacitor bodies, flat fillets under H2 / H3, the breakout's tight header holes, R60 / R61 lying flat, LED height, depth, "about the same places" as Plaits. |
| L20 pot device | easyeda_export.py and the routed master's device: Alpha RD901F B10K (Thonk) instead of Bourns' PTV09A. |

Firmware: `plaitsy.bin` rebuilt with libDaisy v9.0.0 and xpack gcc
14.2.1. A build of the committed sources first came out byte-identical to
the committed bin. The new one differs only in the V/OCT constants and the
mux sampling time, and the 188 host checks pass. Not yet run on hardware.

The tests were updated where they had pinned the old design or the old
wording. They now read the LED part the BOM names, the sockets from
bom.py's `SOLDERED`, the ADC sampling times from hal_daisy.cc, and the
figures design.md and the READMEs state. Each such change is marked
`[2026-11-14: …]` in the test files. No check was loosened past its
source.

## Faceplate copper, 2026-11-14: scripted, waiting for routing

The user chose to fix M6, L10 and L17 in copper ("I script, you finish")
and to accept M7 as documented. `Plaits-routed.epro2` is patched by
script; no other net's copper changed (checked pad group by pad group),
and there are no contacts and no clearance items beyond stale pours.
- **M6:** C10 and C9 moved between their 595's VCC pin 16 and OE pin 13 (3.3 / 3.7 mm and 3.9 / 2.1 mm from the pins). A GND_D_F via replaces C10's old ground pad, through which HF3's ground reached U10.8.
- **L10:** R14 / R15, 100k from SCK_F / LED_LATCH_F to GND_D_F, added to circuit.py, both schematics and the PCB. They are placed clear of every panel-side housing; the generator's checks give 0 problems.
- **L17:** the DIP-16 footprint's pad 1 is square, in the generator and the master.
- **Left for the user:** nine ratlines (L_D4_G and L_D2_R ripped, U9's 3V3D_F tie, the caps' and pull-downs' ends), then rebuild the pours and export. Coordinates are in design.md, "Faceplate rework, 2026-11-14", with a picture in `hardware/easyeda/plaits-faceplate-rework-2026-11-14.png`.
- **Until then the suite shows 66 failing:** 9 more than below. All 9 come from the open ratlines and the stale pours: pcb E.connectivity.face, E.clearance.face, the one-copper-group checks, firmware A.led_bit.4 / .8, A.sr.SRCLR_high_OE_low.U9.
- **After the export:** the check-up is the copper audit, the labels, `easyeda_export.py` and the suite. power F.C9 / F.C10 and firmware C.595_inputs… should then pass, leaving 54 at the time (the panel text fixes and M2 since: see below for the current count).

**M2, the same day: the LED footprint to 2.54 mm.** The user's go-ahead for
all recommended fixes reached M2 too, with option A: keep the 1/4 W LED
resistors. The same file is patched again by script:
- **Footprint:** `LED-3MM-3P` is Ringsy's (pads at ±2.54 mm, 0.9 mm holes, 1.5 mm pads, pad 1 square), in the generator and the master.
- **R88 / R92:** the new green pads land where they stood, and four 1/4 W columns no longer fit between the LED pads and the HARMONICS / MORPH lugs. R88 lies flat above D1 and R92 below D8. Option B, 1/8 W (0204) resistors in tighter columns, would have left six short ratlines; the user kept the parts.
- **Ripped:** R88 / R92's nets, POT_HARMO_F (it ran where R88 lies now), LED_D4_R, LED_D5_G and the 3V3D_F trunk up x 32.5. Every other LED track end follows its pad.
- **Left for the user:** eight more ratlines, numbered 7–14 in design.md's "Faceplate rework" with the same picture. A grid router found a route for each.
- **Checks:** copper_audit finds no contacts and nothing under the rule but stale pours; the generator gives 0 problems. The generator's no-pad-under-a-housing rule no longer counts the LEDs, which stand 6.6–9 mm off the board, as test_pcb already had it.
- **The suite, 1891 checks:** 61 failing before M2 (12 of them from the M6 ratlines and stale pours), 68 after. Now passing: pcb A.led_pitch and C.ring_min; R88 / R92's hairlines over D2 / D7 are gone from G.rear_over_joints, and G.bodies.face has 10 touches, not 12. Newly failing, all from the new ratlines: firmware A.led_bit.7 / .11 / .12 / .15, A.pot_mux_channel.Y1, A.sr.SRCLR_high_OE_low.U10; pcb A.tracks_end_on_modelled_panel_pads; power G.3V3D_F_track_reaches_U9.16 / U10.16. 21 failing checks in all come from open ratlines and stale pours, so **47 are expected after the export**.

**Routed, then restored, the same day.** The user routed all 14 ratlines,
but the export came back with the library parts the scripts had changed
in place as they were before. EasyEDA's import keeps its own copy of a
part with the same uuid and updateTime. So `LED-3MM-3P` was back at
1.27 mm, the DIP-16's pin 1 round, and the 30k and Alpha pot devices had
their old text. The LED tracks had been routed to the 1.27 mm pads.

A script put the parts back under new uuids, moved the LED track ends with
their pads and nudged the five tracks that then crossed a pad: LED_D3_G,
L_D1_G, LED_D5_G (with L_D8_G), U9's 3V3D_F riser and LED_D4_R. One
stitching via went. design.md's "Faceplate rework" lists them with a
picture.
- **Checks:** the copper audit finds every net whole, no contacts and nothing under 0.152 mm except at the stale pours. The tightest new gap is 0.173 mm (LED_D4_R between D3.1 and R83.1). The generator gives 0 problems.
- **The suite, 1891 checks: 48 failing**, from 68. The routing cleared the 20 ratline failures (firmware A.led_bit ×6, A.pot_mux_channel.Y1, A.sr ×2, C.595_inputs…; power F.C9 / F.C10 and the 3V3D_F / GND_D_F group checks; pcb E.connectivity.face; panel A.tracks_end_on_modelled_panel_pads; netlist E.faceplate_GND_D_F_one_piece). Nothing newly fails.
- **Still to do:** pcb E.clearance.face fails on the stale pours only. **47 are expected once the user has rebuilt the pours and exported.**
- **Re-keyed again:** the user's re-import of that file still showed 1.27 mm LEDs. A new uuid is not enough while the part's `source` still names the old library part. The six parts, and the three devices naming the DIP-16, now carry a fresh `source` prefix as well. The audit is unchanged and the suite still has 48 failing. Import it as a new project, and check D1's pad spacing (5.08 mm from pad 1 to 3) before rebuilding the pours.
- **Synced 2026-11-15:** the user re-imported it, and the pads came in at 2.54 mm with the DIP-16 pin 1 square. They rebuilt the pours and exported. Tracks and vias are unchanged, the audit is clean (nothing under 0.152 mm) and the generator gives 0 problems. **The suite has 47 failing**: E.clearance.face passes now.

## Still open

47 failing checks (2026-11-15), by what they need:

- **Copper on the faceplate:**
  - M6, L10, L17 and M2: done. Scripted and routed 2026-11-14, pours rebuilt and synced 2026-11-15; see above.
  - M7: accepted by the user on 2026-11-14 (fault-only; documented in design.md). Its checks stay failing: power I.-12V_missing ×2, analog_dc E.wide_rail_neg / _pos, E.voct_rail_neg.esd.
- **L23, done 2026-11-14** (see "Panel text" below):
  - OUT / AUX are knocked out of the band's mask, and the button dots start 0.5 mm outside their holes.
  - The FM glyph is now 1.65 (letters 1.0 mm tall, 0.16 mm stroke). With the real metrics it was 0.74 mm tall, under JLCPCB's 1.0.
  - The title against the subtitle is checked with the measured font, with lower case taken as wide as capitals (an upper bound). They don't overlap, by 0.17 mm at that bound.
- **Measured or accepted, now documented in design.md:**
  - M5 (power C.DCDC_load_worst) and M8 (panel E.jack_and_pot_heights_agree, E.button_not_held_pressed): their checks test the parts, and the build notes deal with them.
  - L2's residual (analog_ac D.sample_hold.pots, 4.8 LSB16).
  - L3's drift (analog_dc F.bat85_* ×3: with BAT85s, calibrate warm).
  - L4 (power A.J2_shrouded, A.cable_misplaced ×2).
  - L6 (power C.3V3A_clamp, I.powerup_3V3A; analog_dc E.voct_3v3a_backfeed).
  - L7 (analog_dc E.voct_pin_low; bom 4.D22_holds_PA1).
  - L9 (power I.-12V_missing / I.+12V_missing VDDA).
  - L13 (analog_dc G.fw_probe_low_residual).
  - L14's colours not to pick (analog_dc J.current.green_InGaN / blue / white).
  - L16 (pcb G.bodies.main / .face, G.rear_over_joints, H.female_on_joints; since M2 only HF3 over RV4's lug is left in G.rear_over_joints).
  - L18 (pcb B.breakout_header_holes).
  - L22 (panel E.depth_behind_panel).
  - L24 (panel H.plaits_position ×14).
- **Outside plaits/:** the repo's combined `bom/thonk-order.*` and `bom/parts-order.*` still carry the old button line (bom 5.thonk_order_Orchid_column). Rerun `bom/thonk_order.py` and `bom/parts_order.py`; other sessions edit those files, so this session left them alone. The shared catalogue in the other three bom.py copies still lists 1N5711 / SD101 and "CD4051B also works". The module-design skill's parts.md ("9.5–10" mm Thonkiconn) and panel.md ("about 7 mm") disagree with Thonk's drawing.

## Panel text, 2026-11-14 (house-wide, no copper changed)

EasyEDA Pro's default font was measured on its own Gerbers (the user's March boards against their project). A LEFT_BOTTOM string's letters stand 0.2 × fontSize above the origin and are 0.685 × fontSize tall; the advance is 0.64 × fontSize. Every `panel_pcb.py` now places text with these numbers (`INK_*`, `ink_width`), so panel text sits where the artwork has it. Before, it sat 0.2 × fontSize high, 0.4–0.9 mm. Labels on gold are knocked out of the mask: a hole in the mask opening round the letters, filled by a reverse string on the mask layer, so they read dark on the gold. The stroke has a 0.16 mm floor. The routed master's panel board was replaced by the regenerated one after checking that it equalled the old generated one, and the panel tests now use the measured font.

## Settled while verifying

- **The Thonk LED button's pinout**, which the mixer's suite could not check, is confirmed by Thonk's own drawing PB01-109TL: contacts 1+2 and 3+4, LED anode pad 5, cathode pad 6. The footprint matches.
- **The 3-lead LED's lead order** per Tayda's product drawing: cathode the longest, in the middle; red the medium; green the shortest. That matches circuit.py with red in the square pad 1. Check it again on whatever part replaces A-8599 (M1).
- **The Thonkiconn** (sleeve / switch / tip, the switch touching the tip unplugged) and **the Alpha pot** (clockwise from pin 1 to pin 3; all seven read the right way in the front view), from their makers' drawings.
- **The breakout:**
  - J2 is a Doepfer 10-pin pinout (pins 1–2 only to D3's cathode, 9–10 only to D2's anode, 3–8 GND).
  - The DC/DC input stays inside the B2405S's 21.6–26.4 V (21.85–24.79 V); the Seed's VIN is 4.46 V at the lowest input.
  - The rails at the breakout are ±11.70 V typical, 10.94 V at the bus's −5 %.
- **Firmware against the board:** SPI1 at 1.5625 MHz, mode 0, MSB and high byte first, RCLK 417 ns, every 74HC595 timing met at the 2 V bounds. The scan is 0.199 ms (rev V ADC clock 6.146 MHz). The probe reading comes at least 0.79 ms after a change. The normalization threshold is 0.825 V at the jack, against a 0.133 / 3.133 V swing. TRIG fires at 1.47 V rising. MODEL is 0.211 V per model.
- **The CV conversion:**
  - The firmware's Plaits constants match Plaits' own schematic, plaits_v50.sch decoded from its part records.
  - End to end, Plaitsy reads within truncation of Plaits on every channel.
- **AC:** the CV corners are 12.2 kHz (11.5–13.0), TRIG 122 kHz, V/OCT 4.8 kHz. Every TL074 stage has a phase margin of at least 55° (Cf does it; without it V/OCT would have 20°). Noise is 0.26–0.29 LSB per reading against the ADC's own 1.16, and V/OCT reads 0.22 cents rms of noise. The 48 mA LED step moves readings by about 0.2 LSB.
- **Copper:** every power track is 0.6 mm, each power and ground net is one piece, GND_F and GND_D_F never touch on the faceplate. All drills, slots, vias and spacings meet JLCPCB. The pours have no dead copper.
- **Panel:** every part's centre agrees within 0.05 mm across nine representations. The barrel (0.78 mm) and shaft (4.0 mm) offsets, re-derived from the drawings, match circuit.py. 12HP, the slots and the rail zone meet Doepfer's figures.

## Refuted or corrected by the verifiers (test bugs, now fixed)

- **The breakout's 100 µF caps in the main-board gap** (panel): they sit on the Seed's side. What is under the breakout is at most about 2.5 mm, 8.5 mm to spare.
- **Two vias "too close" to a track** (pcb): JLCPCB's via rule is 0.2 mm, not the PTH rule.
- **Checks that could not fail:**
  - power H.DCDC_output_load_min compared two constants;
  - bom 4.note_TL074_grade was `check(…, True)`;
  - pcb H.socket_bom compared bom.md with a copy of bom.md;
  - bom 4.alternatives_listed snapshotted today's eight diode names.
- **Limits at the wrong conditions:**
  - 3V3A at ±1.5 % (the LP2985's 1 mA row; ±2.5 / ±3.5 % applies), 3V3D at ±3 % (±4.5 % with the divider);
  - VDDA + 0.3 V applied to FT pins;
  - the 74HC4051's 200 Ω (its 6 V figure);
  - an STM32 table read for the wrong silicon revision (same values).
- **Unsourced or unsupported numbers:**
  - LED VFs with no source in two groups;
  - a BAT85 leakage extrapolation below 5 V with no data;
  - the 16-bit sampling-time extrapolation without table 183's 10-LSB note;
  - the socket height taken from a retailer listing;
  - resistor bodies under the Yageo maximum.
- **A snapshot of the design passing as a source:** the LED pitch (1.27 mm from parts.md, which restates the footprint) now expects the maker's 2.54 mm. The README pitch window was widened to fit.

## Outside Plaitsy

**The stereo mixer's power header J18 is wired to the wrong pins.** The
power group found it while reading Doepfer's pinout, and the coordinator
confirmed it on the routed master. J18 has GND on pins 3–10 and +12 V on
11–12. On a Doepfer bus, 9–10 are +12 V and 11–12 are +5 V. So on a real
bus the mixer would short the bus +12 V to GND and run its +12 V rail from
+5 V. The mixer's own suite carries the same table. A separate session
handles it.

## What the suite could not check

- **The Seed's supply current**: no datasheet figure, a forum measurement only (M5). Also what loads 3V3A on Seeds after rev 5 (L6).
- **74HC4051 and 74HC595 at 3.3 V**: no maker specifies the 4051's Ron or the 595's output resistance there. Both are interpolated or bounded, and the groups use slightly different 595 figures.
- **The LEDs**: the real part's lead pitch (M2), and its VF at a few mA instead of 20 mA.
- **The breakout's output stage**: no schematic was found, so its gain, output level and DC offset at OUT / AUX are unknown.
- **Mechanical figures**:
  - the Thonkiconn's height (drawing 9.0 mm, one builder measured 10);
  - the button's travel;
  - the female sockets' tail lengths and the long-tail headers' tails (from the photo);
  - the M3 hardware;
  - the case depth.
- **Fault and model figures**:
  - B5819W maximum VF below 1 A;
  - Doepfer's rail tolerance (none published; ±5 % assumed);
  - the TL074's real phase-reversal voltage;
  - whether the STM32's sampling capacitor keeps its charge between conversions;
  - its ESD diode curve.
- **Not modelled**: Gerber-level mask and silk, how EasyEDA renders the band's fill rule, crosstalk beyond the probe's rough estimate.
