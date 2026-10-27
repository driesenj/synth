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
| Netlist | Done, 162 parts, checked | `hardware/tools/circuit.py` |
| EasyEDA Pro schematic | Done, three A3 pages, every footprint assigned, drawing checked against the netlist | `hardware/easyeda/Marbles.epro2` |
| Faceplate placement, panel template | Done | `hardware/panel/` |
| PCB placement | Done: both boards placed, outline, holes, headers aligned, every pad on its net; clearance-checked | `hardware/tools/pcb.py`, previews `hardware/easyeda/marbles-easyeda-pcb-*.png` |
| PCB routing | Not started (do it in EasyEDA Pro on the imported project) | |
| Firmware | Not started | |

## Layout

```
README.md
docs/design.md
hardware/
  tools/
    circuit.py          the netlist and the faceplate placement
    easyeda_export.py   builds Marbles.epro2 (reuses ../../../plaitsy/hardware/tools/easyeda_export.py)
    pcb.py              the two PCBs: placement tables, clearance checks, the PCB documents
    panel.py            hole list and drill template from the placement
  easyeda/
    Marbles.epro2       import this into EasyEDA Pro
    marbles-easyeda-*.png   schematic page and PCB placement previews
    pcb-template.epru   canvas, layer and rule records copied from one of your own PCBs
  panel/
    marbles-panel-holes.csv, marbles-panel-drill.svg
```

Regenerate everything from `hardware/tools`:

```bash
python easyeda_export.py && python panel.py
```

The exporter needs the MorrisSynth library cache in
`plaitsy/hardware/easyeda/morrissynth-parts.epru` and Pillow for the previews.

## Importing into EasyEDA Pro

File > Import > EasyEDA (Professional) > `Marbles.epro2`. The project carries
its own symbols and footprints, including a corrected `seed_power_opamps`
footprint at 2.54 mm pitch (the Plaitsy project's copy is at 2.0 mm). It
holds two boards, each with its schematic and its PCB:

- **Marblesy Main**: schematic pages 1 and 2, `Marblesy Main PCB`
- **Marblesy Faceplate**: the faceplate page, `Marblesy Faceplate PCB`

Net ports with the same name connect within a board; the `_F` nets are the
faceplate side of the headers. Both PCBs come placed and net-assigned but
unrouted: open a PCB, run Design > Check DRC and the netlist check, then
route. The placement conventions are in
[docs/design.md](docs/design.md#pcb-placement).
