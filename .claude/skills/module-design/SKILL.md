---
name: module-design
description: How to design a Eurorack or Kosmo synth module in this repo end to end, the way Marblesy was done - panel layout first, netlist in Python, generated EasyEDA Pro project (schematic + placed PCBs + panel PCB), Thonk parts, clearance checks, routing notes. Use this skill whenever the user wants a new module, a clone of a Mutable/other module, a faceplate or panel, a PCB placement, an EasyEDA export, a Daisy Seed board, or asks about jacks, pots, buttons, LEDs, headers, standoffs, panel holes or routing for any of the modules in this repo, even if they only mention one part of that chain.
---

# Designing a module (the Marblesy way)

The repo's modules are designed as code: one Python netlist, one placement
table, and generators that write everything else (EasyEDA Pro project with
schematic pages and placed PCBs, panel hole table, drill template, panel
artwork, panel PCB). The Marblesy clone in `marbles/` is the reference
implementation; copy its tools rather than starting fresh. The reasons this
matters: EasyEDA Pro has no scripting, the user does the routing by hand in
it, and every time the panel changed during Marblesy the whole chain
regenerated in seconds with zero drift between panel, faceplate board and
docs. Hand-maintained copies would have gone out of sync on the first
change.

## Order of work (panel first)

Marblesy was first placed, then re-laid out when the panel turned out to
look nothing like the original. Do it in this order:

1. **Panel layout first.** Decide knob, button, jack and LED positions on
   the panel, as the user will see it, before any PCB work. Compare with the
   original module if it is a clone. Write the positions into `PLACEMENT`
   in `circuit.py` (board frame, front view, y up, origin bottom-left) and
   render the artwork SVG; iterate with the user on that picture. Button
   and knob sizes drive the layout: the Thonk LED button is 5.5 mm, a 12 mm
   KS01-B eats a knob's worth of panel.
2. **Netlist** in `circuit.py`: parts with pin-to-net dicts, headers as
   pin lists shared by both boards, net names that say what they are
   (`CV_X_F` = faceplate side of `CV_X`). Keep it checkable: single-pin
   nets and header pins unused on one side are bugs.
3. **Schematic** via `easyeda_export.py`: library parts from the user's
   EasyEDA library cache, new symbols drawn in the same style with real pin
   numbers, generated footprints, every block ending in net ports. The
   exporter's `check()` proves the drawing matches the netlist; do not ship
   a page with problems.
4. **PCB placement** via `pcb.py`: both boards placed and net-assigned,
   unrouted, with the clearance checks passing. Headers at identical
   coordinates on both boards.
5. **Panel files** via `panel.py` and `panel_pcb.py`: hole table, 1:1 drill
   SVG, artwork SVG, and the panel as the project's third PCB.
6. **Import into EasyEDA Pro** (user does this): schematic DRC, PCB DRC and
   netlist check, then routing by hand with autorouter help. Give the user
   routing notes (see `references/routing.md`).
7. **Docs and BOM** in `docs/design.md` and `README.md`, updated with every
   change; the BOM lists real purchasable parts (Thonk first).

Commit after each coherent step with a message that says what changed in
the design, not just in the code. Push only when asked.

## Frames and conventions that bit us

Read `references/placement.md` before placing anything. The short version:

- Panel and faceplate placement: front view, x right, y up, origin at the
  board's bottom-left corner. Panel coordinates for the hole table are from
  the panel's top-left, y down; the board is centred on the panel.
- PCBs are drawn as EasyEDA shows them, looking at the top layer, and on
  both boards the top layer is the rear of the stack. So PCB x = BOARD_W −
  x_front, and both boards share one frame, which is what makes header
  pairs line up by construction.
- EasyEDA mirrors a bottom-layer footprint about its own X axis (y → −y)
  and then rotates it. Verified on every routed MorrisSynth board. Pick
  panel-part angles by a rule on the resulting pad positions, never by
  hand.
- Panel-facing parts on the faceplate's bottom layer, logic and male
  headers on its top; sockets on the main board's bottom, everything else
  on its top. Nothing but sockets and standoffs on the main board's front.
- Jack barrel = sleeve pad + 6.48 mm towards the tip = 0.78 mm below the
  WQP518MA origin; Alpha pot shaft = PTV09A origin + 0.53 mm away from the
  pins. The panel hole table applies these; the artwork and the panel PCB
  use the same functions.

## The generators, and what to copy

| File | Does | Copy from |
|---|---|---|
| `circuit.py` | netlist, headers, PLACEMENT, part tables | `marbles/hardware/tools/circuit.py` |
| `easyeda_export.py` | schematic pages, symbols, footprints, devices, project writer | `marbles/...` (imports `plaitsy/hardware/tools/easyeda_export.py` for the library and primitives) |
| `pcb.py` | placement tables, clearance checks, PCB documents, previews | `marbles/hardware/tools/pcb.py` |
| `panel.py` | hole table, drill SVG, artwork SVG | `marbles/hardware/tools/panel.py` |
| `panel_pcb.py` | the panel as a PCB document | `marbles/hardware/tools/panel_pcb.py` |

Run from the module's `hardware/tools`: `python easyeda_export.py && python
panel.py`. Needs Pillow for the previews, the MorrisSynth library cache
`plaitsy/hardware/easyeda/morrissynth-parts.epru`, and the PCB preamble
cache `marbles/hardware/easyeda/pcb-template.epru` (both derive from the
user's `ProPrj_MorrisSynth_2026-10-01.epro2` export in Downloads, which may
be gone; the caches are committed).

The file-format facts the generators rely on are in
`references/easyeda-format.md`. Read it before touching the writers or
adding a record type; most of it was reverse-engineered from the user's own
exports and is not documented anywhere else.

## Parts

`references/parts.md` holds the measured facts for the parts the rig uses:
Thonkiconn jacks, Alpha 9 mm pots, the Thonk low-profile LED button (with
its foot holes and pinout), 6 × 6 tactiles, LEDs and how to drive bipolar
ones from a shift register, the Daisy Seed on Rob Heel's breakout, DIP
chips with unused pins. Prefer Thonk parts because the user orders there;
Tayda and Mouser for what Thonk lacks.

## Checks before handing over

The generators report problems; a handover with any of these open is not
done:

- `check()` on every schematic page: 0 problems.
- `Board.check()` on both PCBs: 0 problems (pad clearance 0.25 mm, 0.5 mm
  to the edge, no housing overlap per side, nothing under a standoff).
- `header_check()`: every header pin at the same spot on both boards.
- `placement_check()`: panel parts exactly at PLACEMENT.
- A parse of the written `.epru`: every PAD_NET names a real pad of the
  component's footprint, every net has a NET record (see the validation
  snippet in `references/easyeda-format.md`).
- The artwork SVG opened in the browser pane and looked at. Text labels
  overlapping knobs or guides are the usual finding.

Then tell the user what EasyEDA's own DRC will still say (floating pins on
intentionally open pins, foot pins of LED buttons) so they do not chase it.

## What the user decides

Layout taste, part choices, panel wording and colours, which fab, when to
push. Bring the picture and the trade-off; do not ask for permission to
regenerate files or to commit on the branch they are working on. The user
routes the PCBs themselves in EasyEDA Pro; give them the routing notes and
move critical parts (decoupling next to its IC) before they start.

For stripboard builds the opposite holds: the user lays those out
themselves and wants only nets, connectors and parts (see the memory note
"Stripboard layout is the builder's").
