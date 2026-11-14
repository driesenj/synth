# Side FXy tests

Hardware design test groups, one script each, checking `circuit.py`, the
routed master `../easyeda/SideFXy-routed.epro2`, `docs/design.md`, the
firmware's pin tables and the manufacturers' datasheets against each other.
They only read: nothing in tools/, easyeda/, panel/, bom/, docs/ or
firmware/ is written.

```bash
python run_tests.py              # every group
python run_tests.py power pcb    # some
python test_cv.py                # one, every check printed
```

Python with numpy (no scipy, no SPICE). A failing check is a finding about
the design, the boards, the firmware or the docs, not a broken test: the
findings of the first run are in the dated `docs/test-report-*.md`.

| File | Checks |
|---|---|
| `harness.py` | shared: paths, `load()` for the tools, `ohms()`, `farads()`, `text()`, `read_export()`, `routed()`, `Checks` |
| `test_netlist.py` | pinouts and polarity, routed pad nets, routed library parts against the generator's, connectivity, stacked header pins, schematic, design.md's tables |
| `test_pins.py` | check_pins.py, the firmware's pin tables against circuit.py and the routed U5, the STM32's alternate functions, bit order |
| `test_logic.py` | the 74HC165/595 chain at 3.3 V against the firmware's bit-bang timing, logic levels, LED drive, encoders, the display's SPI |
| `test_audio.py` | the breakout's audio stages: levels, headroom, impedances, offset, response, phase margin, polarity, normalling |
| `test_cv.py` | the four CV stages into the ADC: transfer, worst case, overdrive and injection, impedance, settling, noise |
| `test_clock_midi.py` | the clock transistor stage and the H11L1 MIDI input: thresholds, currents, timing, ratings |
| `test_power.py` | the breakout's power header, reverse protection, rails, the 5 V DC/DC and 3V3D budget, ratings, faults, decoupling |
| `test_pcb.py` | footprints vs datasheets, drills and rings vs JLCPCB, the breakout's holes, value labels, bodies, stacking gap, display stack, copper |
| `test_panel.py` | holes in every representation vs the faceplate, the display window, Eurorack mechanics, clearances, labels, the panel frame |
| `test_bom.py` | bom.py vs circuit.py and the committed BOM, the Thonk order, part numbers, ratings, mechanics |

Datasheet numbers sit in a constants block at the top of each group, with
their source and whether they are min, typ or max.
