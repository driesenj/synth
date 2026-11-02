# Envy — quad envelope

Four Moritz Klein envelopes (the MKI x ES.EDU EG kit's circuit) in 16HP
Eurorack, all analog (6 × TL074). Each channel has ATTACK, a shared
DEC/REL, SUSTAIN, a LOOP / SINGLE toggle, OUT, an inverted INV and an LED.
The gates normal down the column, so one gate fires all four. A few
changes over the kit:

- the burst no longer depends on the gate's level;
- INV mirrors OUT instead of clipping;
- Schottky steering diodes give a cleaner floor.

Two stacked boards (faceplate + main board), built the Marblesy way, with
Thonk panel parts.

On the panel it is **Bloom**, one of the voice case's Garden names
(2026-11-02), with the gold mushroom mark at the foot.

![panel](hardware/panel/envy-panel-preview.png)

## Status

| Part | Status | Files |
|---|---|---|
| Panel layout, drill template, artwork | Agreed (defaults, 2026-10-31) | `hardware/tools/panel.py`, `hardware/panel/` |
| Netlist | Done: one board, 167 parts, 0 problems | `hardware/tools/circuit.py`, [docs/design.md](docs/design.md#netlist) |
| Simulation | Done: 28 checks pass (burst, peak, sustain, tails, times, LOOP, normals) | `hardware/tools/sim.py`, [docs/design.md](docs/design.md#simulation) |
| EasyEDA Pro project: schematic (6 pages), both PCBs placed, the panel as a PCB | Done, unrouted; 0 schematic / PCB / file problems | `hardware/tools/easyeda_export.py`, `pcb.py`, `panel_pcb.py`, `hardware/easyeda/Envy.epro2` |
| Routing | Yours, in EasyEDA Pro ([routing notes](docs/design.md#routing-notes)) | |

## Files

```
docs/design.md            behaviour, circuit, changes from the kit, netlist, simulation, boards, EasyEDA,
                          routing notes, panel, parts
hardware/
  tools/
    circuit.py            the netlist, its split over the two boards, its checks, the panel placement
    sim.py                the netlist run in time: envelope numbers checked against the design notes
    panel.py              hole list, drill template and the panel artwork from the placement
    easyeda_export.py     the EasyEDA Pro project: schematic pages, devices, footprints, checks
    pcb.py                both PCBs placed (unrouted), mounting holes, clearance and header checks
    panel_pcb.py          the panel as a PCB, from the same layout as the artwork
  easyeda/
    Envy.epro2            import into EasyEDA Pro; envy-easyeda-*.png previews of every page and PCB
  panel/
    envy-panel-holes.csv, envy-panel-drill.svg
    envy-panel.svg        panel artwork (groups: copper, silk, holes, mockup), envy-panel-preview.png
```

Regenerate from `hardware/tools`:

```bash
python circuit.py && python sim.py && python panel.py && python easyeda_export.py
```
