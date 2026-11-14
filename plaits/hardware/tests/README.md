# Plaitsy hardware tests

Eight test groups checking `circuit.py`, the routed master
`../easyeda/Plaits-routed.epro2`, `docs/design.md`, `docs/bom.md`, the
firmware in `firmware/src/` and the manufacturers' datasheets against each
other. They only read: nothing in tools/, easyeda/, panel/, bom/, docs/ or
firmware/ is written.

```bash
python run_tests.py                # every group
python run_tests.py power bom      # some
python test_analog_dc.py           # one, every check printed
```

Python with numpy (no scipy, no SPICE). A failing check is a finding about
the design, the boards, the firmware or the docs, not a broken test: the
findings, by severity with a proposed fix each, are in
[docs/test-report-2026-11-13.md](../../docs/test-report-2026-11-13.md)
(1891 checks, 99 failing: 32 findings, 8 medium, none high; after the
no-copper fixes of 2026-11-14, 1889 checks and 59 failing, all of them
open items the report lists).

| File | Checks |
|---|---|
| `harness.py` | shared: paths, `load()` for the tools, `ohms()`, `farads()`, `text()`, `read_export()`, `routed()` (both routed boards with every pad's position and net), `Checks` |
| `test_netlist.py` | circuit.py on its own, pinouts and polarity against datasheets, every routed pad's net, header stacking, schematic pages, design.md's tables |
| `test_firmware.py` | the firmware's pin, ADC, LED, mux and button tables against the routed board and libDaisy; SPI to the 74HC595s against its datasheet; the CV conversion end to end against Plaits' own front end; thresholds as jack voltages |
| `test_analog_dc.py` + `analog_dc_solver.py` | the CV stages into the Seed's ADC at worst case, over-range and the V/OCT clamps, the normalization probe, pots through the mux, LED and button-LED currents |
| `test_analog_ac.py` | CV bandwidth and aliasing, stage phase margins, ADC settling and mux switching, trigger latency, the probe in time, noise in LSB and cents |
| `test_power.py` | the breakout's power entry and reverse protection, the DC/DC, rails and current budget, the Seed's 3V3 limits, decoupling, power tracks, sequencing and missing-rail faults |
| `test_pcb.py` | footprints against datasheets and the breakout's Gerbers, drills and annular rings against JLCPCB, outline and holes, value labels, bodies, stacking gap, pours, tracks |
| `test_panel.py` | holes in every representation against the routed faceplate, Eurorack mechanics, front clearances, heights and depth, labels, the house panel frame |
| `test_bom.py` | bom.py against circuit.py, the committed BOM files and the routed boards; quantities, part numbers, ratings, Thonk parts |

Datasheet numbers sit in a constants block at the top of each group, with
their source and whether they are min, typ or max.
