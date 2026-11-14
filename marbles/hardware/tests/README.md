# Marblesy hardware tests

Eight test groups, one script each, checking `circuit.py`, the routed master
`../easyeda/Marblesy-routed.epro2`, `docs/design.md`, `docs/bom.md`, the
firmware in `firmware/src/` and the manufacturers' datasheets against each
other. They only read: nothing in tools/, easyeda/, panel/, bom/, docs/ or
firmware/ is written.

```bash
python run_tests.py                # every group
python run_tests.py power bom      # some
python test_analog_dc.py           # one, every check printed
```

Python with numpy (no scipy, no SPICE). About a minute for all of it
(test_pcb takes 25 s). A failing check is a finding about the design, the
boards, the firmware or the docs, not a broken test: the findings are in
[docs/test-report-2026-11-13.md](../../docs/test-report-2026-11-13.md)
(1289 checks, 90 failing after an independent verification pass; 1293 / 52
since M1 and M2 were applied the same day).

Whether a chip has a socket comes from bom.py (its "DIP-xx IC socket" lines,
`SOLDERED`), not from its footprint.

Take a part's footprint with `harness.routed().fp_doc(board, ref)`: the
project keeps several footprint copies under one title, so `fp_docs[title]`
can return the wrong one.

| File | Checks |
|---|---|
| `harness.py` | shared: paths, `load()` for the tools, `ohms()`, `farads()`, `text()`, `read_export()`, `routed()` (both routed boards with every pad's position and net), `Checks` |
| `test_netlist.py` | circuit.py on its own, pinouts and polarity against datasheets, every routed pad's net, header stacking, schematic pages, design.md's tables |
| `test_firmware.py` | the firmware's pin, LED, button, mux and DAC tables against the routed board and libDaisy; SPI frames and timing against the MCP4922 / 74HC595 / 74HC165 datasheets; logic polarity; calibration constants |
| `test_analog_dc.py` + `analog_solver.py` | CV inputs into the Seed's ADC, over-range injection, pots through the mux, the reference, the DAC output stages and their calibration range, gate outputs, clock inputs and the probe |
| `test_analog_ac.py` | CV input bandwidth and aliasing, ADC sampling and mux settling, output-stage phase margin, slew, noise, gate edges, clock-input delays |
| `test_power.py` | the breakout's power entry and reverse protection, rails, current budget per rail, the Seed's 3.3 V limits, decoupling, power tracks, sequencing and missing-rail faults |
| `test_pcb.py` | footprints against datasheets and the breakout's own Gerbers, drills and annular rings against JLCPCB, outlines and standoffs, panel parts, value labels, bodies, stacking gap, pours |
| `test_panel.py` | holes in every representation against the routed faceplate, Eurorack mechanics, front clearances, depth, labels, the house panel frame |
| `test_bom.py` | bom.py against circuit.py, the committed BOM files and the routed boards; part numbers, ratings, Thonk parts, headers, sockets, standoffs |

Datasheet numbers sit in a constants block at the top of each group, with
their source and whether they are min, typ or max.
