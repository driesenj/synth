# Plaitsy — a Plaits clone on a Daisy Seed (PCB version)

A Mutable Instruments Plaits clone for Eurorack, 12HP, built the way
[Marblesy](../marbles/README.md) is: two stacked PCBs behind a PCB panel,
Thonk panel parts, a Daisy Seed on Rob Heel's
[seed_power_opamps](https://oshwlab.com/scape_rob/seed_power_opamps)
breakout for power and the audio output stage. The firmware
([`firmware/`](firmware/README.md)) is a port of Plaits 1.2 with all 24
models, so the official
[Plaits manual](https://pichenettes.github.io/mutable-instruments-documentation/modules/plaits/manual/)
applies as written.

On the panel it is **Orchid**, one of the voice case's Garden names
(2026-11-02), with the gold mushroom mark at the foot.

This supersedes the stripboard design in [`plaitsy/`](../plaitsy/README.md),
which keeps its circuit (the CV stages, pot mux and probe are carried over)
but not its boards.

Power: a 10-pin Eurorack cable on the breakout; about +62 / −62 mA
typical on ±12 V, up to +129 / −122 mA at worst. Before building, read the
[Building](docs/design.md#building) notes and the
[hardware test report](docs/test-report-2026-11-13.md).

The full design is in [docs/design.md](docs/design.md): what Plaits needs,
the Seed pin map, every circuit, the board-to-board headers, the panel, the
PCB placement, routing notes and the firmware plan. The BOM, with the Thonk
parts in their own table, is [docs/bom.md](docs/bom.md).

## Status

| Part | Status | Files |
|---|---|---|
| Netlist | Done, 109 parts, checked | `hardware/tools/circuit.py` |
| EasyEDA Pro schematic | Done, two A3 pages (main board, faceplate), every footprint assigned, drawing checked against the netlist | `hardware/easyeda/Plaits.epro2` |
| Panel layout (Plaits arrangement), drill template, artwork, panel PCB | Done; the panel is the third board in the project | `hardware/panel/`, `hardware/tools/panel_pcb.py` |
| PCB placement | Done: both boards placed, outline, holes, headers aligned, every pad on its net; clearance-checked. Reworked with what routing Marblesy taught: standing resistors clustered on the op-amps (summing nodes 8.7 mm), 100 n at every supply pin, header pins, mux channels and 595 outputs ordered for the fewest crossings, no LED-button foot holes, a DRC-clean copper band | `hardware/tools/pcb.py`, previews `hardware/easyeda/plaits-easyeda-pcb-*.png` |
| PCB routing | Done by hand in EasyEDA Pro (2026-11-01, third export: pours rebuilt, stitching vias); the export is the layout master and `routed_check()` keeps the generator on it. Audited clean: every net complete, no shorts between nets, nothing under the clearance rule, headers aligned. Value labels added to the silkscreen by `value_labels.py`, redone 2026-11-14 by its stricter copy (with R43 30k and the Alpha pot device patched in; copper unchanged). 2026-11-14: the faceplate rework (C9 / C10 at their chips, R14 / R15 clock pull-downs, square DIP-16 pin 1) is patched in by script and waits for routing in EasyEDA (design.md, "Faceplate rework, 2026-11-14"); M7 accepted. The LED footprint stays at 1.27 mm; the LEDs' 2.54 mm leads are jogged at assembly (design.md, Building) | `hardware/easyeda/Plaits-routed.epro2`, `hardware/tools/copper_audit.py`, `hardware/tools/value_labels.py`, `docs/routing-audit-2026-11-01.md` |
| Hardware tests | 8 groups, 1889 checks (2026-11-13); after the no-copper fixes of 2026-11-14, 59 failing, all open items of the report | `hardware/tests/`, [docs/test-report-2026-11-13.md](docs/test-report-2026-11-13.md) |
| Firmware | Written (2026-11-01): Plaits 1.2 with all 24 models and its two-button switch to the 2022 bank, on libDaisy 9.0.0 and the Daisy bootloader. Builds (253 kB of the bootloader's 480 kB), passes the host tests; not yet run on hardware | `firmware/`, see [firmware/README.md](firmware/README.md) |

## Layout

```
README.md
docs/design.md
firmware/               the Plaits 1.2 port for the Seed (firmware/README.md)
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
