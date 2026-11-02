# Offset — triple offset attenuverter

Three channels of `OUT = ATTEN × IN + OFFSET` in 10HP Eurorack, all analog,
on one PCB (2 × TL074, 2 × TL072, two LM4040 references). Each channel has an
attenuverter (−1 … +1), an offset of ±5 V or ±10 V (RANGE toggle), and a
bicolour LED on its output. The inputs normal down the column (IN 1
normals to +1 V), so one source feeds every channel at its own depth. An
unpatched output adds into the next channel, so OUT 3 can be a mix. Thonk
panel parts.

On the panel it is **Prune**, one of the voice case's Garden names
(2026-11-02), with the gold mushroom mark at the foot.

![panel](hardware/panel/offset-panel-preview.png)

## Status

| Part | Status | Files |
|---|---|---|
| Panel layout, drill template, artwork | Done (approved 2026-10-31) | `hardware/tools/panel.py`, `hardware/panel/` |
| Netlist | Done: one board, 84 parts, 0 problems, DC check passes | `hardware/tools/circuit.py`, [docs/design.md](docs/design.md#netlist) |
| EasyEDA Pro schematic | Done: 4 A3 pages, drawing checked against the netlist (0 problems); LM4040 TO-92 pinout fixed 2026-11-02 (pad 2 = cathode, pads 1 + 3 = anode's net); not yet imported | `hardware/easyeda/Offset.epro2`, previews `hardware/easyeda/offset-easyeda-*.png` |
| PCB placement, panel PCB | Done: all 84 parts placed on one board, unrouted, checks pass; the panel as a second PCB; [routing notes](docs/design.md#routing-notes) | `hardware/tools/pcb.py`, `hardware/tools/panel_pcb.py`, previews `hardware/easyeda/offset-easyeda-pcb*.png` |

## Files

```
docs/design.md            behaviour, circuit, netlist, op-amp map, references and power, BOM, choices
hardware/
  tools/
    circuit.py            the netlist with its checks and DC solve, and the panel placement
    easyeda_export.py     builds Offset.epro2 (reuses ../../../plaitsy/hardware/tools/easyeda_export.py)
    pcb.py                places the board (panel parts by PLACEMENT, the rest on a grid), checks, PCB writer
    panel_pcb.py          the panel as a PCB, from panel.py's layout
    panel.py              hole list, drill template and the panel artwork from the placement
  easyeda/
    Offset.epro2          schematic, the placed board and the panel PCB
    offset-parts.epru     TL072CN, cached from your MorrisSynth export
    offset-easyeda-*.png  page and PCB previews
  panel/
    offset-panel-holes.csv, offset-panel-drill.svg
    offset-panel.svg      panel artwork (groups: copper, silk, holes, mockup), offset-panel-preview.png
```

Regenerate from `hardware/tools`:

```bash
python circuit.py && python easyeda_export.py && python panel.py
```

Import with File > Import > EasyEDA (Professional) > `Offset.epro2`, then
run Design > Check DRC; [design.md](docs/design.md#schematic) lists the
floating-pin warnings to expect.
