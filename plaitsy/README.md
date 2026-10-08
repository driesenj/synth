# Plaitsy — a Plaits clone on stripboard

A Mutable Instruments Plaits clone for Eurorack: 3U, 12HP, built on
stripboard behind a hand-drilled aluminium panel. A Daisy Seed does the DSP.
It plugs into Rob Heel's
[seed_power_opamps](https://oshwlab.com/scape_rob/seed_power_opamps) breakout,
which provides power and the output amplifiers.

The aim is to match Plaits closely enough that the official
[Plaits manual](https://pichenettes.github.io/mutable-instruments-documentation/modules/plaits/manual/)
applies as written. The panel has the same controls in the same places. The
firmware will be a port of the Plaits 1.2 code with all 24 models.

The full design is in [docs/design.md](docs/design.md). It covers the
circuit, the Seed pin map, CV scaling, how to build the two boards and stack
them, the panel and the BOM.

---

## Status

| Part | Status | Files |
|---|---|---|
| Schematic | Done. 97 parts, 93 nets, checked | `hardware/stripboard/plaitsy-schematic.json` |
| EasyEDA Pro schematic | Done. Two A3 pages (Main board, Faceplate) built from your MorrisSynth library parts; every connection checked against the netlist | `hardware/easyeda/Plaitsy.epro2` |
| Faceplate board (jacks, pots, LEDs, buttons, pot mux) | Done. Routed and checked: 0 conflicts, 0 incomplete nets | `hardware/stripboard/plaitsy-faceplate-board.json` |
| Panel: drill template and labels | Done | `hardware/panel/` |
| Main board (Seed, CV input stages) | Starter project only. The Seed and every board-to-board socket are placed and locked; the remaining 46 parts are left for the editor's Auto-layout | `hardware/stripboard/plaitsy-main-board-starter.json` |
| Firmware | Not started | — |

---

## Repository layout

```
README.md
docs/
  design.md                          circuit, pin map, build notes, BOM
hardware/
  stripboard/                        import these into stripboard-editor.com
    plaitsy-schematic.json           the whole circuit (both boards)
    plaitsy-schematic-preview.png
    plaitsy-faceplate-board.json     faceplate board, routed (cuts + links)
    plaitsy-faceplate-board-front.png   component side, front view
    plaitsy-faceplate-board-copper.png  copper side, mirrored: cut and solder from this
    plaitsy-main-board-starter.json  main board: locked parts, rest for Auto-layout
    plaitsy-main-board-starter.png
    faceplate-interconnect.json      board-to-board pin table (faceplate hole -> main-board hole)
  easyeda/
    Plaitsy.epro2                    EasyEDA Pro 3.x project: the schematic on two pages
    plaitsy-easyeda-*.png            previews of the two pages
    morrissynth-parts.epru           library parts copied from the MorrisSynth export
  panel/
    plaitsy-panel-drill.svg          1:1 drill template, print at 100 %
    plaitsy-panel-artwork.svg        labels and lines to draw by hand
    plaitsy-panel-holes.csv          every hole: x/y in mm from the top-left corner, diameter
    plaitsy-panel-preview.png
  tools/                             Python that generates all of the above
    circuit.py                       the netlist, the single source of truth
    sb.py                            stripboard model, checker, editor JSON export, renderer
    faceplate.py                     faceplate placement
    finalize_faceplate.py            routes the faceplate (editor's own router) and exports it
    mainboard_starter.py             main-board starter project
    panel.py                         panel files, computed from the faceplate placement
    export_schematic.py              schematic project
    easyeda_export.py                EasyEDA Pro project from the same netlist
    route.py                         runs the editor's router and checker headless (Node)
```

The panel's hole positions come from the faceplate placement in
`faceplate.py`, so the panel and the board stay aligned. After changing
`circuit.py` or `faceplate.py`, regenerate everything from `hardware/tools`:

```bash
python export_schematic.py && python finalize_faceplate.py && python mainboard_starter.py && python panel.py && python easyeda_export.py
```

`finalize_faceplate.py` and `mainboard_starter.py` need a local clone of the
stripboard-editor repository plus Node. The paths are set at the top of
`route.py`. The other scripts need only Python and Pillow.

---

## Opening the projects

In [stripboard-editor.com](https://stripboard-editor.com), use **Import** and
pick a `.json` file from `hardware/stripboard/`. Each project's **notes**
contain its build notes. For the faceplate board, they include the full
board-to-board pin table.

To finish the main board, follow the steps under "Main board" in
[docs/design.md](docs/design.md#main-board-finishing-it-in-the-editor).

In EasyEDA Pro, import `hardware/easyeda/Plaitsy.epro2` as a project. Net
ports with the same name connect, also across the two pages; the ports for
nets that cross to the faceplate are the board-to-board pins.

Most parts are your MorrisSynth library parts. A few came out differently:

- **Devices with no LCSC part number.** The resistor and capacitor values
  that library lacks (470 Ω, 12k, 13k, 15k, 33k, 100k, 1 nF, 100 pF) and the
  BAT85 are new devices on the library symbols and footprints.
- **Four drawn symbols.** The Daisy Seed breakout, 74HC4051, bicolour LED
  and push button are drawn in the same style with their real pin numbers.
  Swap them for library parts with **Replace Component** if you like.
  Only the 74HC4051 has a footprint (DIP-16).
