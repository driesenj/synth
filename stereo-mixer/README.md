# Stereo mixer: master mixer for the Eurorack voice case

The voice case's stereo master. It mixes six mono channels with pan, two
stereo channels, the Clouds return and the drum mixer's output. Clouds is fed
from one send. The L/R outputs go to the output module, so the whole rig ends
in stereo, with the drums and the low end in the centre.

Analog throughout: 4× TL074, DC-coupled, ±12 V.

The circuit, values and reasoning are in [docs/design.md](docs/design.md).

---

## Panel

| Section | Controls | Jacks |
|---|---|---|
| Channels 1–6 (mono) | LEVEL, PAN, SEND, MUTE toggle | IN |
| Channels 7–8 (stereo) | LEVEL (dual-gang), SEND, MUTE toggle (DPDT) | IN L, IN R (R takes L when unpatched) |
| Return | RETURN level (dual-gang) | RETURN L, RETURN R (R takes L when unpatched) |
| Drums | DRUMS level | DRUMS (drum mixer output, centred) |
| Send | — | FX IN (drum mixer send, adds into the send bus), SEND |
| Master | MASTER (dual-gang) | OUT L, OUT R |

That is 25 knobs (4 of them dual-gang), 8 toggles and 17 jacks, on a 28HP
panel. The proposed layout is in `hardware/panel/`:

- Channels are columns like on a mixing console: SEND, PAN, LEVEL and MUTE
  from the top, with the input jacks at the bottom so cables hang away from
  the knobs.
- On the right, the master section reads top to bottom: send and return,
  drums, MASTER, then the outputs.

## Hooking it up

- **OUT L / OUT R** go to the output module's IN 1 and IN 2, with their pans
  hard left and hard right and the IN knobs at noon or below. Those input
  stages have a gain of 2 and clip at about ±5.4 V in.
- **Mono check:** turn both of the output module's pan knobs to the centre.
  That replaces a MONO switch on this panel.
- **SEND** goes to Clouds IN L; IN R follows L when unpatched. Clouds OUT L/R
  go to **RETURN L/R**. Keep Clouds' own blend at full wet if you want the
  dry signal only from the channel strips.
- **Drum mixer:** its main output goes to **DRUMS** and its send to
  **FX IN**, so the drums share Clouds' reverb. The drum mixer's return stays
  free for the compressor.

---

## Status

| Part | Status | Files |
|---|---|---|
| Netlist | Done: 129 parts, 93 nets, no single-pin nets | `hardware/tools/netlist.py` |
| EasyEDA Pro schematic | Done: 3 A3 pages from your MorrisSynth library parts. The drawing was checked against the netlist: 0 problems. Not yet opened in EasyEDA itself | `hardware/easyeda/StereoMixer.epro2` |
| Panel | Proposed: 28HP, at least 2 mm between neighbouring knob and jack-nut edges. Layout, 1:1 drill template, hole list | `hardware/panel/`, `hardware/tools/panel.py` |
| Layout (stripboard or PCB) | Not started | — |

## Files

```
README.md
docs/design.md                       circuit, gains, pan law, op-amp map, power, BOM
hardware/
  tools/
    netlist.py                       the whole circuit; the single source of truth
    easyeda_export.py                draws netlist.py as an EasyEDA Pro project + previews
    panel.py                         the panel: layout, drill template and hole list
  panel/
    stereo-mixer-panel.svg           proposed 28HP layout, 1:1 in mm
    stereo-mixer-panel-drill.svg     drill template, print at 100 %
    stereo-mixer-panel-holes.csv     every hole: x/y in mm from the top-left, diameter, designator
  easyeda/
    StereoMixer.epro2                EasyEDA Pro 3.x project, 3 pages
    stereo-mixer-*.png               previews of the three pages
    stereo-mixer-parts.epru          library parts copied from the MorrisSynth export
```

In EasyEDA Pro, import `hardware/easyeda/StereoMixer.epro2` as a project.
Net ports with the same name connect across pages. The bus nets are SUM_L,
SUM_R and SUM_S; the stereo normals are IN7L, IN8L and RT_L.

To regenerate after editing `netlist.py`, run this from `hardware/tools`:

```bash
python easyeda_export.py
```

It imports Plaitsy's exporter (`plaitsy/hardware/tools/easyeda_export.py`)
for the file format, the connectivity check and the previews, and needs
Python with Pillow. The library cache is in the repo, so the MorrisSynth
export in Downloads is only read if `stereo-mixer-parts.epru` is missing.

### Parts not in your library

Most parts are your MorrisSynth library parts, including the A100K and B10K
9 mm pots, the ATE1D toggle and the 2×8 box header. Values the library lacks
(100k, 200k and 300k LR1F resistors, and a 22 pF C0G cap) are new devices on
the same symbols and footprints.

Two parts are drawn in the same style, one unit per gang or pole. They have
no footprint, so swap them with **Replace Component** before a PCB layout:

- **9 mm dual-gang pot**, A100k (×3) and A10k (×1). Gang A is pins 1-2-3,
  gang B pins 4-5-6.
- **ATE2D-2M3-10-Z** (LCSC C2921532), the DPDT version of your ATE1D. Poles
  are 1-2-3 and 4-5-6, with 2 and 5 as the commons. Check the datasheet
  pinout before wiring it.
