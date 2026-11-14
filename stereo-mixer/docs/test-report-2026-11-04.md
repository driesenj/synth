# Stereo mixer test suite, 2026-11-04

An agentic test suite for Mycelium, the way the firmware of Plaitsy,
Marblesy and Side FXy was tested, but for an analog module: eight test
groups in `hardware/tests/`, each written and run by one agent, then
re-derived by an adversarial verifier that re-read the datasheets and fixed
the test bugs it found (checks that compared a constant with itself,
snapshots of the current design, datasheet limits read at the wrong
conditions). Everything is checked against
`circuit.py`, the routed master `StereoMixer-routed.epro2`, `design.md` and
the manufacturers' datasheets. The suite itself only reads; the fixes
further down changed tools/, easyeda/, panel/ and bom/.

```bash
cd stereo-mixer/hardware/tests && python run_tests.py
```

First run (before the fixes):

| Group | Checks | Failing | What it covers |
|---|---|---|---|
| netlist | 127 | 2 | pinouts against datasheets, diode / cap polarity from the real symbols and footprints, every routed pad's net, header pins stacked, schematic pages, design.md's tables |
| audio_dc | 331 | 43 | nodal solve of both boards: gains, pan law, phase, normalling, input impedances, mute depth, headroom at the real rails, TL074 common-mode range, DC offset |
| audio_ac | 76 | 32 | AC nodal analysis: response 20 Hz–20 kHz, the PhotoMOS off capacitance and its distortion, phase margins, slew rate, noise |
| latch | 277 | 11 | the mute latch in time: debounce, bounce, power-up at 1–200 ms ramps, power cycles, brown-out, LED / PhotoMOS current |
| power | 137 | 9 | J18 against the Doepfer standard and its footprint, reverse protection, rail voltages, current budget, ratings, missing-rail faults |
| pcb | 92 | 10 | footprints vs part datasheets, drills and annular rings vs JLCPCB, outlines and holes, value labels, real body sizes, stacking gap, pour islands |
| panel | 759 | 2 | holes in every representation vs the routed faceplate, Eurorack mechanics, knob / nut clearances, depth, labels, the house panel frame |
| bom | 128 | 10 | bom.py vs circuit.py and the committed BOM files, the Thonk order, part numbers, ratings, mechanics |
| **all** | **1927** | **119** | |

A failing check is a finding; 119 failing checks are 37 distinct findings
(some show up in several groups, and one finding fails many checks: one
per channel, or one per pot position). None is high severity: nothing
found needs the boards re-routed before ordering. **That was wrong: the
power group checked J18 against the design's own wrong pinout. See H1
below, found and fixed in copper on 2026-11-14.**

## H1, found 2026-11-13: J18 on the wrong bus pins (fixed 2026-11-14)

**What was wrong.** J18 had −12 V on 1–2, **GND on 3–10 and +12 V on
11–12**. The Doepfer A-100 bus is 1–2 −12 V, 3–8 GND, **9–10 +12 V, 11–12
+5 V**, 13–14 CV, 15–16 Gate (doepfer.de a100t_e.htm, pinout image
a100b_e.gif). On a real bus:
- the mixer's GND pins 9–10 sit on the bus +12 V, a dead short of the
  +12 V rail;
- the mixer's "+12 V" came from the bus +5 V.

The suite missed it because `test_power.py`'s `DOEPFER` table and
`test_netlist.py`'s `EURORACK_DS` copied the design's mapping instead of
Doepfer's, so the J18 checks passed against the error. The Plaitsy and
Marblesy suites found it on 2026-11-13 while checking their own power
entries. Five unrouted modules (Atlasy, Offset, Six, SampleHold, Veilsy)
had the same `power_main()` and were fixed in their generators on
2026-11-14.

**What changed (2026-11-14):**
- `circuit.py` and `easyeda_export.py`: J18 9–10 P12_IN, 3–8 GND, 11–16
  open. The schematic's GND bus is on 3/5/7 and 4/6/8 with its flag at
  5/6, and the P12_IN ports are on 9/10. Regenerated: 0 schematic and
  0 PCB problems.
- Routed master `StereoMixer-routed.epro2`, patched by script:
  - Pad nets: J18 9–10 → P12_IN, 11–12 → no net.
  - Tracks: the 12–11 link is moved to 10–9. A new 0.6 mm track runs from
    pad 9 at 45° to (9.42, 24.32) mm, then straight to (9.42, 26.86), where
    it joins the old diagonal to D901. Gaps: 0.74 mm to pad 11 on the
    angled part, 0.49 mm to pad 11 and to the GND via at (10.52, 25.76).
  - Pours: the GND thermal spokes on pads 9–10 are removed on both
    layers. On top, the pad 9 / pad 10 cutouts and the new track's 0.358 mm
    clearance are merged into the old P12_IN cutout.
  - Schematic: the master's power page is re-wired to match the
    generator's.
- The suite's two tables, its design.md pattern and the pins-open checks
  (now 11–16) use Doepfer's pinout.

**Checks after the change:**
- Copper audit: 0 differences against circuit.py (there were 4 at J18),
  0 split nets, 0 other-net contacts, and no new clearance entries. The
  faceplate and panel are unchanged.
- Suite: **1931 checks, 68 failing**, down from 77 failing on 2026-11-14
  before the patch. The 9 J18 failures are fixed and none are new; the two
  extra checks are pins 11–12 touching no copper.
- Rebuild the copper areas in EasyEDA before the Gerbers: the stored top
  pour keeps the old 11–12 link's void and a few thin fill necks around
  J18. EasyEDA's rebuild clears them.

## Fixed the same day (no copper changed)

The copper audit of the patched master is identical to the one before.
After the fixes and their review: **1929 checks, 68 failing**, all of them the open
findings below.

| Finding | What changed |
|---|---|
| M2 stereo mute current | R109–R609 1k5 → 1k, R710 / R810 1k5 → 820 Ω, in circuit.py, the generated project and the routed master (device swap, labels). About 6.8 mA typical, 3.9 mA worst. +12 V draw: 75 mA typical with all muted, 125 mA at most; the worst-case TL074 swing drops from about ±7.7 to ±7.4 V (design.md quotes ±7 V at a 12 V bus). |
| M3 value labels | value_labels.py: a label must sit 0.3 mm nearer its own part than any part of another value (no near-tie fallback), 45 / 40 mil text (each spot tried at both sizes before the next), legend lines within 12 mm of each of their parts. The master was re-labelled: 109 labels + 13 legend lines on the main board, 25 on the faceplate; 0 traps, 0 ties, none under 1.0 mm. |
| M4 standoffs | 11 mm M3 F-F standoffs and a separate M3 × 6 mm screw line in all four bom.py copies (Spore, Orchid, Moss, Mycelium), the combined parts order, the module-design skill (parts.md, placement.md) and Side FXy's design.md. |
| PCB-8 / POWER-7 | "-12V" beside J18's pin 1 on the main board's top silk. |
| BOM-2…7, POWER-6 | 50 V on the ceramic lines, DIP sockets on lines of their own (10 × DIP-14 here), a line per PCB, the 10 µF text (dipped tantalum, or a 5 mm can with its leads spread), R918 / R919 as 0.6 W in the 1/4 W body (about 150 mW worst case), the dual-gang stock note. |
| PANEL-3 | J13 is "DRUM IN" in circuit.JACKS, the hole CSV, the drill template and the schematics. |
| Docs | Every figure in the "Docs" list below, the PhotoMOS off capacitance, the muted input loading, the input range, D903, the brown-out, the phase margin, the DC offset and the worst-case current are now in design.md; build notes for the LED button pinout, socket order, decouplers and pour islands. |

Still open, and still failing their checks: M1 (the PhotoMOS off
capacitance: no drop-in part does better, see M1; a respin would cure it), D903, the output stages'
phase margin, the mute loading its input, the DC offset, the TL074's
common-mode limit, the latch's bounce / brown-out / abs-max margins, a
missing +12 V, J18's annular ring, the body / socket overlaps and the pour
wedge.

---

## Medium

**M1. The PhotoMOS off capacitance distorts every channel** (AUDIO_AC-1, -3).
An off AQY212EH is not an open switch: it is a voltage-dependent
capacitance from FI*k* to GND, 79 pF at 0 V falling to 35 pF at 7.5 V
(Panasonic ASCTB126E, graph 12-(2), read from the PDF's vector path). It
sits behind R*k*01 (10k) plus the LEVEL wiper's source resistance, up to
31k at about ¾ of the knob's travel. With 10 V p-p in:

- 0.05–0.18 % THD at 1 kHz and 0.3–1.7 % at 10 kHz, against 0.003 % for
  the TL074 itself. The two numbers bracket two models of the part (one
  varactor, or two anti-series MOSFETs with a floating source).
- −1 dB at 20 kHz on every channel path at mid-high LEVEL, and the
  roll-off moves with the knob. RETURN, DRUMS and FX IN have no PhotoMOS
  and stay within −0.4 dB.

design.md's "Off, it is an open switch … the channel's gain is unchanged"
is not true.

A search for a drop-in part (DIP-4, THT, the same pins; three agents,
manufacturer catalogues and distributor listings, each candidate run through
this suite's models) found none that does better:

| Part | Off C at 0 V | On resistance | Mute at 10k (typ / worst) | THD 1 kHz / 10 kHz, 10 V p-p | Verdict |
|---|---|---|---|---|---|
| AQY212EH (fitted) | 79 pF, gentle slope | 0.85 / 2.5 Ω | 82 / 73 dB | 0.05–0.17 % / 0.46–1.55 % | keep |
| Omron G3VM-351AY1 | 30 pF typ, no C(V) curve published | 25–35 / 35–50 Ω | 53 / 47–50 dB | about 0.01–0.12 % / 0.10–1.2 % (curve shape assumed) | best alternative, unproven; DigiKey Z12319-ND |
| Toshiba TLP240G(F | 30 pF typ, no curve | as the G3VM | as the G3VM | as the G3VM | THT version out of stock until 2027 |
| Panasonic AQY210EH | 47 pF, steep below 1 V | 18 / 25 Ω | 56 / 53 dB | 0.016–0.19 % / 0.16–1.8 % | worse in one model |
| AQY214EH / AQY216EH, CPC1390G, CPC1343G | — | — | — | — | higher Ron, steeper C(V), or biased-only figures |

The few-pF C×R photorelays exist only in SMD packages. Raising R*k*01 to
win back mute depth raises the distortion with it. So the AQY212EH stays
and M1 is a documented limit. At 100 Hz it is 0.005–0.017 %, and at
2 V p-p, 1 kHz, 0.004–0.021 %. A respin with the shunt at a
low-impedance node (or another mute element) would cure it. If you want
to try the G3VM-351AY1, buy two and measure one channel's THD against an
AQY212EH first.

**M2. A stereo mute is not guaranteed to switch** (LATCH-1, -2). Q drives
1k5 + the PhotoMOS LED(s) + the red button LED. Typical: 4.8 mA mono,
4.1 mA stereo, as design.md says. Worst case (+12 V at −5 %, TL074 supply
current at max, all eight muted: 10.2 V at the CD4013B, its IOH min, LED
VF max) a stereo channel gets 2.6 mA, under the AQY212EH's 3.0 mA maximum
operate current; turn-on is then about 8 ms. Both channel types run under
Panasonic's recommended 5–10 mA. Fix, a value swap with no copper change:
R710 / R810 → 820R (6.8 mA typ, 4.0 mA worst) and R109–R609 → 1k (6.8 mA
typ, 4.5 mA worst); +12 V draw rises by about 17 mA with all muted.

**M3. Fifteen main-board value labels point at the wrong part** (PCB-1,
-6). Measured the way value_labels.py measures, five labels sit nearer a
part of a different value than their own: R204's "100k" by R703 (200k),
R608's "10k" by R609 (1k5), R709's "10k" by R708 (100k), R901's "100k" by
C901 (22p), R916's "300k" by R909 (1k). Ten more are ties within 0.3 mm
(R104/R803, R205/R804, R505/R704, R902/C902, R903/C903, R905/R906,
R908/R907 …). The 2026-11-02 audit called them "as near another resistor
as their own"; they are nearer the wrong one. Also 15 labels are 32–38 mil,
under JLCPCB's 1.0 mm minimum text height. Every label's text matches
circuit.py. Fix: legend lines for those parts and 40 mil text
(value_labels.py: no near-tie fallback, a 0.3 mm margin, SIZES (45, 40)),
then re-label the master. Silkscreen only.

**M4. The BOM's standoffs are 2.5 mm short** (PCB-2, PANEL-1, BOM-1).
The 8.5 mm female sockets on the main board plus the male headers' 2.5 mm
plastic on the faceplate make an 11.0 mm gap, as design.md says, but
bom.md asks for "about 8.5 mm". The same line is in marbles/, plaits/ and
side-fx/'s bom.py and in `bom/parts-order.md` (15 standoffs for the four
modules); it comes from the module-design skill (parts.md, placement.md:
"8.5 mm gap"). Plaitsy's design.md already says 11 mm. Fix: 11 mm M3 F-F
standoffs (or 10 mm + a washer), in all four BOMs and the skill.

## Low

| Id | Finding | Fix |
|---|---|---|
| D903 (NETLIST-1, LATCH-3, -4, POWER-1) | D903 (anode POR, cathode +12V) sits across C906 and can never conduct. C906 empties through the CD4013B RESET inputs' protection diodes instead: POR goes to about −0.6 V at every power-off (abs max −0.5 V), 0.25–0.33 mA per input typically and about 3.6 mA at worst with the new LED currents, against the 10 mA rating. The debounce caps do the same into VDD (DB 0.6 V above VDD, 0.13 mA). The reset still works every time. | Leave it (harmless) and correct design.md, or on a respin put a BAT85 from GND (anode) to POR (cathode). Don't just flip D903: on +12V that holds every flip-flop in reset, cathode on GND removes the reset. |
| AUDIO_AC-2 | The OUT L/R stages and the SEND inverter have 17–18° phase margin: the ~5 pF on each inverting input with Rin ∥ Rf (67–77k on the output stages, 50k on the send inverter) puts a pole inside the loop. +9 / +11 dB closed-loop peaking near 1 MHz; nothing in the audio band, no oscillation predicted. | 4.7 pF C0G across R905 and R908, 10 pF across R911, soldered on the standing resistors' legs (66° worst). |
| AUDIO_DC-4 | Muting loads the input: at full LEVEL a muted mono input is 9.1k (stereo L with R normalled 4.5k); a source multed elsewhere drops 0.4–1.5 dB. design.md says the source is never loaded. | Doc; raising R*k*01 to 100k would fix it but makes M1 worse unless the PhotoMOS changes. |
| AUDIO_DC-2 | The followers leave the TL074's common-mode range below −8.5 V typ / −7.1 V worst at the jack (LEVEL near full), where a TL07x can reverse phase. ±5 V audio is always inside. | Note it in the docs. |
| AUDIO_DC-3 | DC offset at OUT L/R: 53 mV typical, 278 mV worst at 25 °C (TL074 Vos max through an offset gain of 28, 20 of it in U4); SEND 31 / 197 mV. MASTER moves it by up to 225 mV. | A TL074B in U4 halves the worst case; or AC-couple the outputs. |
| LATCH-5 | A contact-bounce gap of 2.1 ms or more right after the press edge can re-arm the Schmitt (worst threshold corner; 4.7 ms typical). 300 random bouncy presses per corner toggle exactly once. | Accept; or a 220k pull-up (4.4 ms). |
| LATCH-6, V1 | A rail dip to 3–7 V for 20 ms leaves channels randomly reset, kept or toggled, and can mute an unmuted one. Dips to 8 V or more keep everything; 2 V or less resets everything. | Accept (overloaded bus only). |
| POWER-2 | With +12 V missing, the 6 CMOS chips' VDD is pulled to about −0.55…−0.6 V through their substrate diodes (abs max −0.5 V). | Accept; or a BAT85 from GND to +12V by C904. |
| PCB-4, -5 | At the largest socket and body sizes, DIP-14 socket frames touch R502, R706, R405 by 0.14–0.21 mm, and the CMOS decouplers lean on their chips. R805 / C903 do not collide (copper_audit's 0.10 mm is the outline). | Fit sockets first; bend the decouplers away. |
| PCB-7 | J18's annular ring is 0.212 mm: above JLCPCB's 0.20 mm minimum, under its recommended 0.25 mm. | Optional: 1.7 mm pads. |
| PCB-8, POWER-7 | No "−12V" text beside J18 (the triangle and key notch are the only marks), as on every house board. | Optional silk string. |
| PCB-9 | A 0.17 mm² pour wedge hangs on one spoke beside C913; no dead copper anywhere. | Minimum island area when the pours are rebuilt. |
| BOM-2…6, POWER-6 | No voltage on the 22 p / 100 n / 1 µ lines (the library parts are 50 V); no screw length; the 10 µF line's "5 mm can, 2.5 mm leads" is not a stock combination (the library part is a dipped tantalum); the 10 DIP-14 sockets are spread over three chip lines; one PCB line covers two designs. | bom.py text. |
| PANEL-3 | circuit.JACKS, the hole CSV and the drill template call J13 "DRUMS", the knob's name; the panel says DRUM IN. | Rename in circuit.JACKS, regenerate. |

## Docs

design.md / README figures that the design did not match on the first run (all corrected since; the
TL074 figures changed again with the new LED resistors: ±10 V typical, ±7 V worst at a 12 V bus):

- "the summers at four times": true for the L/R summers; the send summer clips with the SEND output, at about twice (AUDIO_DC-1).
- Stereo send gain 0.91 (−0.8 dB), not 0.95 (AUDIO_DC-5).
- TL074 swing about ±10 V at the chips' 11.1–11.5 V rails, not ±10.5; 7.7 V guaranteed worst (AUDIO_DC-6, POWER-4).
- Input impedances: stereo L 50k with R unpatched, RETURN L 33–50k with R normalled, DRUMS 60–100k (AUDIO_DC-7).
- AQY212EH on-resistance 0.85 Ω typical, not 0.83; the 82 / 72 dB mute depths hold (AUDIO_AC-4).
- Eleven GND pins join the grounds, not ten (NETLIST-2).
- About 70 ms of reset (R·C·ln 2), not 100; it still outlasts the debounce settling for every ramp (LATCH-V2).
- Current: worst case about 100 mA on +12 V (all muted) and 58 mA on −12 V; only typical figures are given (POWER-5).
- The off PhotoMOS is "an open switch" and "the source is never loaded by the mute" (M1, AUDIO_DC-4); D903 "empties" C906 (D903).
- bom.md's note that the dual-gang A100K's stock is uncertain: Thonk lists it in stock (BOM-7).

## Refuted

- A reversed 16-pin cable shorting the bus through the module (POWER-3):
  both diodes block and the shroud is keyed; the bus-side short is
  Doepfer's pinout, not this design.
- The standoff screws being two in total (PCB-3, PANEL-2): the line is per
  standoff, 8 screws.

## What the suite could not check

- **The Thonk LED button's pinout** (contacts 1+2 / 3+4, LED anode 5,
  cathode 6) is checked only against the skill's parts.md: Thonk's site
  blocks fetches and no copy of its drawing was found. If 1 and 3 were the
  joined pair, BTN would be shorted to GND_F. Check one button with a meter
  before soldering. Its LED VF (2.0 V typ, 2.5 max) and the absence of a
  built-in resistor are assumed too.
- Alpha's 9 mm A-taper curve (no published curve found; a 15 % / 10 % at
  half rotation model is used), the RD901F drawing (scanned), Thonkiconn
  lug sizes and the real header / socket heights.
- Ground and supply crosstalk, track-to-track coupling, latch edges into
  audio; Gerber-level checks (mask slivers, silk clipped by pads); whether
  EasyEDA's angle-90 STRINGs read bottom to top; the output module's input
  impedance and coupling.
