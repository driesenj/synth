# Atlasy — a Vostok Instruments Atlas clone

A clone of Vostok Instruments' Atlas (2024): four analog multimode filters
in 16HP, each with LP / HP / BP, CV over cutoff and resonance, and a fifth
section, the interpolating scanner, that morphs from filter 1 to filter 4
under a knob and a CV. The IN and FREQ jacks are normalled down the rows,
so one input and one CV can feed all four filters. Atlas builds its filters
from SSI2164 gain cells "inspired by 80s Japanese synths", and its scanner
from AS3360 VCAs after Haible's and Tillman's scanners. The clone uses the
same chips and Sound Semiconductor's own filter app note (AN701). It is
built the Marblesy way: generated panel, netlist and EasyEDA project, Thonk
parts where Thonk has them.

On the panel it is **Hedge**, one of the voice case's Garden names
(2026-11-02), with the gold mushroom mark at the foot.

![panel](hardware/panel/atlas-panel-preview.png)

## Status

| Part | Status | Files |
|---|---|---|
| Panel layout, hole table, drill template, artwork | Agreed 2026-10-31 (toggles, no LEDs, SCAN knob) | `hardware/tools/panel.py`, `hardware/panel/` |
| Netlist | Done, `check()` and `board_check()` at 0; levels and the scanner checked by `sim.py` | `hardware/tools/circuit.py`, `hardware/tools/sim.py` |
| Schematic (6 pages), both PCBs placed, panel PCB | Generated, every check at 0; not yet opened in EasyEDA, not routed | `hardware/easyeda/Atlasy.epro2`, `hardware/tools/{easyeda_export,pcb,panel_pcb}.py` |
| Circuit and board description, routing notes | Done | `docs/design.md` |

Two boards, SMD on the rear of each for JLC's assembly; the panel parts and
the headers are through-hole.

## Panel

The original's arrangement (Vostok's manual, figure "Atlas_Ref"): per row the
four jacks on the left with the mode switch under them, the channel numeral,
then FREQ and RES with the FM2/RES switch between them; the scanner below a
dotted divider. House style otherwise: the same title band, rule and mushroom
mark as every other module, outputs on gold.

| Control | Part | Notes |
|---|---|---|
| IN 1–4 | Thonkiconn | Each normalled from the row above (IN 1 from ground) |
| FREQ 1–4 (jacks) | Thonkiconn | Cutoff CV, 1 V/oct nominal, normalled from the row above like IN |
| FM2/RES 1–4 | Thonkiconn | A second cutoff CV or a resonance CV, by the switch |
| OUT 1–4, scanner OUT | Thonkiconn | 1 kΩ out, on the gold column / patch |
| SCAN (jack) | Thonkiconn | Adds to the knob; ±5 V moves about 1.6 channels |
| FREQ, RES 1–4 (knobs) | Alpha 9 mm B100k, 10 mm caps | |
| SCAN (knob) | Alpha 9 mm B10k | Marks 1–4 where each channel is alone |
| Mode 1–4 | Dailywell 2M sub-mini toggle, DPDT ON-ON-ON (2MD6-T1-B1-M2-Q-E-S; Tayda) | Up LP, middle HP, down BP. Atlas has a 3-way slide switch |
| FM2/RES 1–4 | Dailywell 2M sub-mini toggle, SPDT ON-ON (2MS1T1B1M2QES; Thonk) | Up FM2, down RES. Atlas has a slide switch |
| Channel numerals | 3 × 5 gold dots | Artwork only |

Differences from Atlas, all on purpose:

- **Labels once per column.** Atlas repeats IN / FREQ / FM2/RES / OUT and
  FREQ / RES over every row. Here each column is named once above row 1,
  the numerals name the rows, and only the switch positions are labelled
  per switch (like the L / R marks on the mixer's pans). The dotted lines
  down the IN and FREQ columns show the normals.
- **Toggles instead of slide switches.** Panel slide switches with a long
  enough actuator are hard to get; sub-mini toggles are not. Same places,
  same positions.
- **No LEDs.** Atlas lights its numerals with the input; here they are gold
  dots (see `docs/design.md`).
- **A knob instead of the SCAN fader.**
- **Jacks 10 mm apart** instead of about 9.3, the most 16HP allows next to
  two knob columns.

`hardware/panel/atlas-panel-holes.csv` lists every hole in panel
coordinates (from the top-left, y down) next to its footprint origin on the
faceplate board.

## Circuit

`docs/design.md` has the whole circuit: four SSI2164 poles per channel,
LP / HP / BP by pole mixing, resonance fed back from the 4-pole bandpass so
no mode loses its passband, a fifth SSI2164 for the four resonance VCAs,
precision-clamped CV summers, and a scanner whose stacked PNP current line
keeps the four VCA gains summing to one. Run from `hardware/tools`:

```
python circuit.py         # netlist and board-split checks, part counts
python sim.py             # filter levels, resonance loop, scanner crossfade
python panel.py           # hole table, drill template, artwork
python easyeda_export.py  # Atlasy.epro2: schematic, both PCBs placed, panel PCB, previews
```
