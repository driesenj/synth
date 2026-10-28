# Plaitsy — a Plaits clone on a Daisy Seed (PCB version)

A Mutable Instruments Plaits clone for Eurorack, 12HP, built the way
[Marblesy](../marbles/README.md) is: two stacked PCBs behind a PCB panel,
Thonk panel parts, a Daisy Seed on Rob Heel's
[seed_power_opamps](https://oshwlab.com/scape_rob/seed_power_opamps)
breakout for power and the audio output stage. The firmware will be a port
of Plaits 1.2 with all 24 models, so the official
[Plaits manual](https://pichenettes.github.io/mutable-instruments-documentation/modules/plaits/manual/)
applies as written.

This supersedes the stripboard design in [`plaitsy/`](../plaitsy/README.md),
which keeps its circuit (the CV stages, pot mux and probe are carried over)
but not its boards.

The full design is in [docs/design.md](docs/design.md): what Plaits needs,
the Seed pin map, every circuit, the board-to-board headers, the panel, the
PCB placement, routing notes, the BOM and the firmware plan.

## Status

| Part | Status | Files |
|---|---|---|
| Netlist | Done, 109 parts, checked | `hardware/tools/circuit.py` |
| EasyEDA Pro schematic | Done, two A3 pages (main board, faceplate), every footprint assigned, drawing checked against the netlist | `hardware/easyeda/Plaits.epro2` |
| Panel layout (Plaits arrangement), drill template, artwork, panel PCB | Done; the panel is the third board in the project | `hardware/panel/`, `hardware/tools/panel_pcb.py` |
| PCB placement | Done: both boards placed, outline, holes, headers aligned, every pad on its net; clearance-checked | `hardware/tools/pcb.py`, previews `hardware/easyeda/plaits-easyeda-pcb-*.png` |
| PCB routing | Not started (do it in EasyEDA Pro on the imported project; notes in `docs/design.md`) | |
| Firmware | Not started | |

## Layout

```
README.md
docs/design.md
hardware/
  tools/
    circuit.py          the netlist and the panel placement (PANEL_XY -> PLACEMENT)
    easyeda_export.py   builds Plaits.epro2 (reuses ../../../plaitsy/hardware/tools/easyeda_export.py)
    pcb.py              the two PCBs: placement tables, clearance checks, the PCB documents
    panel.py            hole list, drill template and the panel artwork from the placement
    panel_pcb.py        the panel as a PCB document (holes, slots, silk, copper band), same source as the artwork
  easyeda/
    Plaits.epro2        import this into EasyEDA Pro
    plaits-easyeda-*.png    schematic page and PCB placement previews
  panel/
    plaits-panel-holes.csv, plaits-panel-drill.svg
    plaits-panel.svg        panel artwork (groups: tint, silk, copper, holes, mockup), plaits-panel-preview.png
```

Regenerate everything from `hardware/tools`:

```bash
python easyeda_export.py && python panel.py
```

The exporter needs the MorrisSynth library cache in
`plaitsy/hardware/easyeda/morrissynth-parts.epru`, the PCB preamble cache
in `marbles/hardware/easyeda/pcb-template.epru`, and Pillow for the
previews. The panel preview PNG is a headless-Edge screenshot of the SVG
(see `docs/design.md`).

## Importing into EasyEDA Pro

File > Import > EasyEDA (Professional) > `Plaits.epro2`. The project carries
its own symbols and footprints (the Marblesy set: the `seed_power_opamps`
footprint at 2.54 mm pitch, the 3-lead LED, the Thonk LED button, the
headers). It holds three boards, each with its schematic and its PCB:

- **Plaitsy Main**: the main-board page, `Plaitsy Main PCB`
- **Plaitsy Faceplate**: the faceplate page, `Plaitsy Faceplate PCB`
- **Plaitsy Panel**: a note page and `Plaitsy Panel PCB`, the front panel
  (no parts: outline, slots and holes, silkscreen, bare-copper OUT / AUX band)

Net ports with the same name connect within a board; the `_F` nets are the
faceplate side of the headers. Both PCBs come placed and net-assigned but
unrouted: open a PCB, run Design > Check DRC and the netlist check, then
route. The placement conventions and the routing plan are in
[docs/design.md](docs/design.md#pcb-placement).
