# Offset — quad offset attenuverter

Four channels of `OUT = ATTEN × IN + OFFSET` in 12HP Eurorack, all analog
(4 × TL074, two LM4040 references). Each channel has an attenuverter
(−1 … +1), a ±5 V offset, and a bicolour LED on its output. The inputs
normal down the column (IN 1 normals to +1 V), so one source feeds every
channel at its own depth. An unpatched output adds into the next channel,
so OUT 4 can be a mix. Built the Marblesy way, with Thonk panel parts.

![panel](hardware/panel/offset-panel-preview.png)

## Status

| Part | Status | Files |
|---|---|---|
| Panel layout, drill template, artwork | Draft (2026-10-31), not yet approved | `hardware/tools/panel.py`, `hardware/panel/` |
| Circuit plan | Written; [open choices](docs/design.md#open-choices) to settle | [docs/design.md](docs/design.md) |
| Netlist, EasyEDA schematic, PCBs, panel PCB | Not started | |

## Files

```
docs/design.md            behaviour, circuit, op-amp map, references and power, BOM, open choices
hardware/
  tools/
    circuit.py            panel parts and their placement (the netlist goes here next)
    panel.py              hole list, drill template and the panel artwork from the placement
  panel/
    offset-panel-holes.csv, offset-panel-drill.svg
    offset-panel.svg      panel artwork (groups: copper, silk, holes, mockup), offset-panel-preview.png
```

Regenerate from `hardware/tools`:

```bash
python panel.py
```
