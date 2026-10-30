# VDJ controller panel

A4 (297 × 210 mm) top panel for a VirtualDJ MIDI controller: the skin's
decks A/B and mixer, folded into three columns.

| File | What |
|---|---|
| `vdj-panel.pdf` | p1 layout, p2 **1:1 drill template**, p3 hole table + parts/drilling notes |
| `vdj-panel.dxf` | outline, holes, slots in mm (layers OUTLINE / HOLES / SLOTS), for laser/CNC |
| `make_panel.py` | generates the two above; positions and part sizes are constants at the top |

## Parts

| Qty | Part | Hole |
|---|---|---|
| 12 | rotary pot, cheap 16 mm (WH148 type), M7 bushing | Ø7 |
| 3 | Bourns PTA4543-2015DPB103 slide pot, 45 mm travel | slot 3 × 50 + 2 × Ø2.4 (M2, 56 mm apart) |
| 16 | TinyTronics AB6Y-M-BLACK 16 mm **momentary** button | Ø16 |
| 6 | M3 panel fixing (optional) | Ø3.2 |

The AB6Y-**A** looks identical but latches, which breaks hold-to-preview CUE.

## Regenerate

```
python make_panel.py
msedge --headless=new --no-pdf-header-footer --print-to-pdf=vdj-panel.pdf vdj-panel.html
```

The script prints the tightest front and rear clearances and warns when two
parts get closer than 5 mm (front) or 1 mm (behind the panel), or a part comes
within 10 mm of the edge. Print page 2 at 100 % and check its 100 mm and
50 mm bars before drilling.
