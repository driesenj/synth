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

The design notes are in [docs/design.md](docs/design.md).

## Status

| Part | Status | Files |
|---|---|---|
| Panel layout (Plaits arrangement), hole table, drill template, artwork | Drafted, for review | `hardware/tools/circuit.py` (PLACEMENT), `hardware/panel/` |
| Netlist | Not started (follows the panel) | |
| EasyEDA Pro schematic, PCB placement, panel PCB | Not started | |
| Firmware | Not started | |

## Layout

```
README.md
docs/design.md
hardware/
  tools/
    circuit.py          the panel parts and their placement (the netlist joins them next)
    panel.py            hole list, drill template and the panel artwork from the placement
  panel/
    plaits-panel-holes.csv      every hole: panel x/y in mm from the top-left corner, diameter
    plaits-panel-drill.svg      1:1 drill template, print at 100 %
    plaits-panel.svg            panel artwork (groups: tint, silk, copper, holes, mockup)
    plaits-panel-preview.png
```

Regenerate from `hardware/tools`:

```bash
python panel.py
```

The preview PNG is a headless-Edge screenshot of the SVG at 5 px/mm
(see `docs/design.md`).
