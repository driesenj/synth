# Marblesy — a Marbles clone on a Daisy Seed

A Mutable Instruments Marbles clone for Eurorack, 18HP, two stacked PCBs,
Thonk panel parts. The Daisy Seed sits on Rob Heel's
[seed_power_opamps](https://oshwlab.com/scape_rob/seed_power_opamps)
breakout for power.

The full design is in [docs/design.md](docs/design.md): what Marbles needs,
the Seed pin map, every circuit, the board-to-board headers, the faceplate
placement, the BOM and the firmware plan.

## Status

| Part | Status | Files |
|---|---|---|
| Netlist | Done, 169 parts, matches the routed boards pin for pin | `hardware/tools/circuit.py` |
| EasyEDA Pro schematic | Done, four A3 pages (main board 2, faceplate 2), every footprint assigned, drawing checked against the netlist | `hardware/easyeda/Marbles.epro2` |
| Panel layout (Marbles arrangement), drill template, artwork, panel PCB | Done; the panel is the third board in the project | `hardware/panel/`, `hardware/tools/panel_pcb.py` |
| PCB placement | Done, then reworked during routing; the generator now takes it from the routed project | `hardware/tools/pcb.py`, previews `hardware/easyeda/marbles-easyeda-pcb-*.png` |
| PCB routing | Done by hand in EasyEDA Pro (2026-10-29), audited: every net complete, no shorts, 0.15 mm minimum clearance | `hardware/easyeda/Marblesy-routed.epro2` |
| Firmware | Not started | |

## Layout

```
README.md
docs/design.md
hardware/
  tools/
    circuit.py          the netlist and the faceplate placement
    easyeda_export.py   builds Marbles.epro2 (reuses ../../../plaitsy/hardware/tools/easyeda_export.py)
    pcb.py              the two PCBs: placement from the routed project, clearance checks, the PCB documents
    panel.py            hole list, drill template and the panel artwork from the placement
    panel_pcb.py        the panel as a PCB document (holes, slots, silk, copper band), same source as the artwork
  easyeda/
    Marblesy-routed.epro2   the routed project: order the boards from this one
    Marbles.epro2       the generated project (schematic, placed but unrouted PCBs, panel)
    marbles-easyeda-*.png   schematic page and PCB placement previews
    pcb-template.epru   canvas, layer and rule records copied from one of your own PCBs
  panel/
    marbles-panel-holes.csv, marbles-panel-drill.svg
    marbles-panel.svg       panel artwork (groups: holes, silk, copper, mockup), marbles-panel-preview.png
```

Regenerate everything from `hardware/tools`:

```bash
python easyeda_export.py && python panel.py
```

The exporter needs the MorrisSynth library cache in
`plaitsy/hardware/easyeda/morrissynth-parts.epru`, the routed project (it
reads the placement from it) and Pillow for the previews. It reports 0
problems only when `circuit.py`, the footprints and the panel placement still
describe the routed boards pad for pad; after editing the boards in EasyEDA,
export the project over `Marblesy-routed.epro2` and run it again.

## Importing into EasyEDA Pro

File > Import > EasyEDA (Professional) > `Marblesy-routed.epro2`. It holds
three boards, each with its schematic and its PCB:

- **Marblesy Main**: schematic pages 1 and 2, `Marblesy Main PCB`
- **Marblesy Faceplate**: the faceplate page, `Marblesy Faceplate PCB`
- **Marblesy Panel**: a note page and `Marblesy Panel PCB`, the front panel
  (no parts: outline, slots and holes, silkscreen, bare-copper output band)

Net ports with the same name connect within a board; the `_F` nets are the
faceplate side of the headers. `Marbles.epro2` is the same design as the
generator writes it: schematics (the faceplate's on two pages) and the boards
placed but without copper. The placement conventions are in
[docs/design.md](docs/design.md#pcb-placement).
