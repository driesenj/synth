# EasyEDA Pro project format (.epro2), as reverse-engineered here

Everything below was learned from the user's own exports
(`ProPrj_MorrisSynth_2026-10-01.epro2`, `ProDoc_Plaitsy_2026-10-27.epro2`) and
confirmed by importing generated projects into EasyEDA Pro 3.2. Writers live
in `plaitsy/hardware/tools/easyeda_export.py` (Doc, Symbol, Page, Project)
and `marbles/hardware/tools/{easyeda_export,pcb,panel_pcb}.py`.

## Container

- `.epro2` is a zip: `project2.json` (title, editorVersion "3.2.149",
  description, tags) + `<Name>.epru` + an empty `IMAGE/` entry.
- `.epru` is one record per line: `{head}||{payload}|` with compact JSON.
  The last line (the BLOB doc) has no trailing `|`.
- A document starts with a `DOCHEAD` line (`docType`, `client`, `uuid`,
  `updateTime`, `version`, `editVersion`, `user`) and ends with a `META`
  line. Doc types: FOOTPRINT, SYMBOL, DEVICE, BOARD, SCH, SCH_PAGE, PCB,
  CONFIG, BLOB. Order in the file: all FOOTPRINT, SYMBOL, DEVICE docs, then
  per board: BOARD, SCH, its SCH_PAGEs, its PCB; then CONFIG, then BLOB.
- Linking: `SCH.META.board` and `PCB.META.board` carry the BOARD uuid (16
  hex chars); `SCH_PAGE.META.schematic` carries the SCH uuid. One BOARD =
  one schematic + one PCB, so a multi-board module is several BOARD docs in
  one project (Marblesy: Main, Faceplate, Panel).
- `head.ticket` is a per-doc counter; `Doc.lines()` numbers them. Element
  ids are `e1, e2, ...`; record ids that are JSON arrays are written as a
  JSON *string* (`"[\"NET\",\"GND\"]"`), which is what the newer exports use.
- DEVICE META: `title`, `tags`, `source`, `attributes` with `Symbol`,
  `Footprint` (uuids), `Designator` prefix, `Manufacturer Part`, `Value`,
  `Add into BOM`, `Convert to PCB`, `Description`. New resistor/capacitor
  values clone a library device's attributes.

## Units and frames

- Schematic: 10-mil units; page y runs from −H (top) to 0 (bottom). A3 is
  1655 × 1170.
- Footprints and PCBs: mil (`mm / 0.0254`), y up. The board outline is
  `POLY` on layer 11, `path: ["R", 0, H, W, H, 0, 0]` = (x_left, y_top,
  width, height, rx, ry), so a rectangle's anchor is its top-left.
- Path grammar in `POLY`/`FILL` paths: `[x, y, "L", x, y, ...]`,
  `["CIRCLE", cx, cy, r]`, `["R", x, y, w, h, 0, 0]`, and arcs as
  `"ARC", sweepDeg, endX, endY` (negative sweep = clockwise in the y-up
  frame). `FILL.path` is a list of paths; `POLY.path` is one path. The
  "R" form's last two numbers are NOT corner radii: a nonzero value
  rotated the shape in EasyEDA (the Marblesy panel band came out at 55°).
  Keep them 0 and draw rounded rectangles and slots as L/ARC paths with
  clockwise −90° arcs at the corners, the way the library jack outline is
  drawn.
- Bottom-layer components: pad position = origin + rotate(angle)·(px, −py),
  i.e. mirror about the footprint's X axis, then rotate (angle in degrees,
  CCW positive). Top layer: rotate only. Verified against every routed
  track in 12 boards.

## Fills with holes, pours, routed exports

- A `FILL` (and a pour) path list is one complex polygon combined with the
  **nonzero** fill rule (EasyEDA Pro API, `IPCB_ComplexPolygon`). A hole is a
  contour wound opposite to the outline: `rounded()` in `panel_pcb.py` draws
  clockwise (−90 arcs), so its cutouts are counter-clockwise circles (four
  +90 arcs). A `CIRCLE` entry has no winding to rely on. A contour crossing
  the outline adds copper outside it, so keep cutouts inside.
- DRC wants copper 0.3 mm from a slot region (NPTH `FILL` on layer 12):
  a copper band with holes through it needs clearance rings in both the
  copper fill and its mask opening (mask stays on the ring: black, not bare
  laminate).
- `POURED` (EasyEDA's computed pour) uses 10 mil units. Each `pourFill`
  item with `fill: true` is one island (outline first, then holes); items
  with `fill: false` and `strokeWidth` are thermal spokes, lines from a pad
  centre to the edge of its cutout. A pad joins the pour when a spoke's far
  end (stepped 0.15 mm on) lies in an island.
- Routed exports keep deleted records with an empty payload (`...||` with
  no JSON); a parser must skip them (`pcb.routed_boards()` does,
  `ee.parse` does not). Stale `POURED` records outlive their `POUR`: match
  them by id.

## PCB document records (what a placed, unrouted PCB needs)

Copy the preamble from a real PCB (cached in
`marbles/hardware/easyeda/pcb-template.epru`): CANVAS, 119 LAYER records,
ACTIVE_LAYER, RULE_TEMPLATE, 37 PRIMITIVE, 2 SILK_OPTS, PREFERENCE, 9
LAYER_PHYS, 16 RULE, PANELIZE. Then:

- `NET` per net: id `["NET", name]`, payload with netType/specialColor null,
  `retLine: false`. And `RULE_SELECTOR` per net: id
  `["RULE_SELECTOR", ["NET", name]]`, payload `{"ruleOrder": 4,
  "ruleKeyValue": {}, "copperValue": {"COPPER": "Copper_copperRegion"},
  "innerPlaneValue": {"PLANE": "Plane_innerPlane"}}`.
- Holes: `FILL` on layer 12 with a CIRCLE path (non-plated); slots as an
  `"R"` path with rx = ry = half the height. Your boards use exactly this.
- Copper region: `FILL` on layer 1 (top copper); a solder-mask opening of
  the same shape is a `FILL` on layer 5 (top solder mask). Text on the
  mask layer comes out as bare copper letters.
- Silk: `POLY` on layer 3 (width in mil, `polyType: "NORMAL"`); `STRING`
  on layer 3 with `fontFamily: "default"`, `fontSize` (mil, roughly 0.9 ×
  the mm cap height × 39.37), `strokeWidth`, `origin: "LEFT_BOTTOM"`
  (centring must be estimated: ~0.62 × size per character). No dashed
  lines: draw dots as 0.12 mm segments.
- `COMPONENT`: `layerId` 1 (top) or 2 (bottom), `x`, `y` (mil), `angle`,
  `attrs: {"Unique ID": <schematic Unique ID>, "Reuse Block": "",
  "Group ID": "", "Channel ID": "$" + pageNo + schematic component id}`.
  Then `ATTR` records with `parentId` = the component id, ids
  `"<cid>-e<n>"`, keys `Footprint` (uuid), `Designator` (visible, with x/y),
  `Device` (uuid); font 45 mil / stroke 6 on layer 3 (4 for bottom).
- `PAD_NET`: id `["PAD_NET", componentId, padNumber, padIdInFootprintDoc]`,
  payload `{"partitionId": "", "padNet": net, "padLen": 0}`. Only for pads
  that have a net. The pad id is the `PAD` record id inside the FOOTPRINT
  doc, so parse the footprint docs to get them.
- META: `{"title", "parent": "", "board": boardUuid, "zIndex": null}`.

## Footprint docs

LAYER list, ACTIVE_LAYER, CANVAS (mm, grid 10), `POLY` silk on layer 3,
`PAD` records (`num`, `centerX/Y`, `hole {holeType, width, height}`,
`defaultPad {padType ELLIPSE|RECT|OVAL, width, height}`, `plated`, layer
12), `ATTR` Footprint and Designator, an empty `NET`. Library footprints also
carry courtyard (layer 48), 3D (49–51) and document (13) layers; the drawn
housing is the union of layers 3 and 13 and is what the overlap check uses.
The PTV09A pot's drawing runs 9 mm beyond its origin, which matches an Alpha
pot's housing (4.85 mm past a shaft at +4.0); the 4 mm `pcb.BODY` override
Marblesy and Plaitsy use is too short. See parts.md.

## Schematic facts

- Wires connect only at endpoints; a wire's net is its `NET` ATTR. Net ports
  (Netport-IN/OUT) and ground flags are components named by their `Name`
  ATTR; same name = same net within a schematic. T-junctions and pins on
  the middle of a wire are not connections; `check()` flags them.
- Pins: `PIN` record + `Pin Number`, `Pin Name`, `Pin Type` ATTRs. Pin
  position = component + rotated symbol offset with (x, y) → (x·cos +
  y·sin, −x·sin + y·cos). Multi-unit parts (TL074) share one Unique ID.
- Schematic DRC in EasyEDA (Design > Check DRC) reports: designators must
  be letters then digits (H1F fails, HF1 passes); every footprint pad must
  have a symbol pin (give DIP-14 MCP4922 its NC pins 2, 6, 7; LM4040 TO-92
  its pin 3); floating pins are warnings. No-Connect flags: none of the
  user's projects contain one, format unknown, leave them.

## Validation snippet

After writing, unzip and parse: for every PCB doc, map component → Footprint
ATTR → the FOOTPRINT doc's PAD ids, and confirm each PAD_NET's pad id is in
that set, each padNet has a NET record, each component's Device uuid exists.
`marbles` ran exactly this before every handover; a mismatch here means
EasyEDA will drop the net silently.
