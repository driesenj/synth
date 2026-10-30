# Panels

## Eurorack geometry

- Height 128.5 mm; width = HP × 5.08 − 0.3 (18HP = 91.3). Mounting slots
  5.5 × 3.2 mm, centres 3 mm from the top and bottom edge, 7.5 mm from the
  left edge and (HP − 3) × 5.08 further right (18HP: 7.5 and 83.8). Round
  3.2 mm holes also work but give no play. Rails sit behind the panel;
  nothing covers the front. Most boards stay ≤ 108 mm tall for the rails.
- Kosmo (the user's other format): 200 mm panels, Eurorack power headers
  (see RIG.md). Ask which format before laying out.
- Panel-to-PCB gap with Thonkiconn and Alpha 9 mm pots is about 7 mm; parts
  on the panel side must be lower than that; Thonk's LED button is made for
  it.

## Layout, Marbles style (what the user liked)

Big knobs for the main parameters in a triangle at the top, small knobs
below, the two "section" buttons in the top corners with big italic serif
letters beside them, small mode/range buttons close to their knobs with
their three-state labels stacked beside them in LED colour order, CV jacks
in a row with dotted guides down from each knob's label, the clock and bias
jacks at the sides, outputs in a bottom row on a contrasting band with an
LED left of each label, title top-left, function name top-right, maker
bottom centre. Compare the draft with a photo of the original before
touching the PCB.

## Rows of identical controls (the stereo mixer)

Do not repeat a word under every knob of a row. Label each row once in the
left margin: the word turned 90° (reading bottom to top) on a bracket as
tall as the row, serifs pointing at the controls, the line broken round the
word (`row_words` and the `vtext` item in `stereo-mixer/.../panel.py`). The
user picked this from five drawn options (side rail, strips, gold tabs,
brackets, column 1 only) over the first fix, a word under column 1 with a
dotted line along the row: a word between two rows reads as belonging to
either, and the dotted lines looked like dividers. Small per-knob scale
marks (L / R on pans) stay. When the label placement is in doubt, draw
the options side by side as SVG before reworking the generator.

## Artwork SVG (`panel.py write_artwork`)

Groups `#silk`, `#copper`, `#holes`, `#mockup` (knobs, nuts, caps, LEDs
for the preview only). Constants in `ART` (colours, knob and scale radii,
cap radii, title strings, fonts). Colours set by CSS on `text` override a
`fill` attribute, so pass colours as inline `style`, and keep a coloured
dot beside each colour-coded label because the real silk has one colour.
Text sizes in mm; labels under knobs at scale radius + 3; jack labels at
nut radius + 1.6 above the jack; outputs' labels shifted right when an LED
sits left of them.

View it in the browser pane (`file:///…/marbles-panel.svg`, screenshot) and
crop the screenshot into `marbles-panel-preview.png` for the repo. Common
findings: titles under the screw heads, labels on dotted guides, labels
touching scale graduations; move the parts (PLACEMENT) when the labels
fight for room, not just the text.

## Panel as a PCB (`panel_pcb.py`)

The method from "Creating front panels in EasyEDA" (My Modular Journey) and
the user's own started "Mixer Front" board: a PCB with the outline, every
hole as a non-plated drill, silkscreen artwork, and bare-copper accents.
Generated from the same positions and label tables as the SVG, as the
project's own BOARD with a note page and a PCB.

- Outline rectangle; holes as layer-12 FILL circles; slots as rounded
  rectangles.
- Silk: STRING (default stroke font, estimated centring), POLY lines, arcs
  as ≤ 90° ARC pieces, dotted guides as 0.12 mm dashes, colour dots as
  rings. Vertical words: STRING `angle` 90 with the LEFT_BOTTOM origin at
  the bottom end of the baseline (`panel_pcb.vtext`), assuming text turns
  CCW like component angles; not yet confirmed in an EasyEDA import.
- Copper band: FILL on layer 1 plus the same FILL on layer 5 (mask
  opening) = ENIG gold. Labels on it as silk; if the fab refuses silk on
  bare copper, put the labels on the mask layer instead (gold letters on
  black). Non-plated holes through the band may draw a DFM remark; add
  clearance rings if so.
- Order: 1.6 mm FR4, black mask, white silk, ENIG.
- Serif italics and exact fonts do not exist in EasyEDA's stroke font;
  tell the user to expect to nudge labels after import.
