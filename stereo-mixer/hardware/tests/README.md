# Stereo mixer tests

Eight test groups, one script each, checking `circuit.py`, the routed
master `../easyeda/StereoMixer-routed.epro2`, `docs/design.md` and the
datasheets against each other. Since the 2026-11-15 mute redesign the
master's main board is placed but not routed: the checks that need its
copper say so, and the AC model estimates its track lengths from the
placement until it is routed. They only read: nothing in tools/, easyeda/,
panel/, bom/ or docs/ is written.

```bash
python run_tests.py              # every group
python run_tests.py latch power  # some
python test_audio_ac.py          # one, every check printed
```

Python with numpy (no scipy, no SPICE). A failing check is a finding about
the design, the boards or the docs, not a broken test: the findings of the
first run are in [docs/test-report-2026-11-04.md](../../docs/test-report-2026-11-04.md).

| File | Checks |
|---|---|
| `harness.py` | shared: `load()` for the tools, `ohms()`, `farads()`, `read_export()`, `Checks` |
| `test_netlist.py` | pinouts, polarity, routed pad nets, stacked header pins, schematic pages, design.md's tables |
| `test_audio_dc.py` + `audio_dc_solver.py` | gains, pan law, phase, normalling, impedances, mute depth, headroom, common-mode range, DC offset |
| `test_audio_ac.py` | frequency response, the mute switches' capacitance and depth, summing-node swing, phase margins, slew, noise |
| `test_latch.py` | debounce, bounce, power-up ramps, power cycles, brown-out, LED current and the switch selects' logic levels |
| `test_power.py` | J18, reverse protection, rails, current budget, ratings, missing rails |
| `test_pcb.py` | footprints, drills, annular rings, outlines, value labels, bodies, stacking gap, pour islands |
| `test_panel.py` | holes vs the faceplate, Eurorack mechanics, clearances, depth, labels, the panel frame |
| `test_bom.py` | bom.py vs circuit.py and the committed BOM, the Thonk order, part numbers, ratings |

Datasheet numbers sit in a constants block at the top of each group, with
their source and whether they are min, typ or max.
