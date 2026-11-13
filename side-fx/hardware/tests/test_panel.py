"""Panel and mechanics of Side FXy (Moss, 14HP).

What it checks, from the parts' drawings, the Eurorack spec and the house
rules, not from the numbers the generators happen to produce:

  1. Where the parts really are: the barrel / shaft / cap centre of every
     panel part, worked out from the pads of the ROUTED faceplate
     (SideFXy-routed.epro2) and the parts' drawings (Thonkiconn barrel 6.48
     mm from the sleeve pin towards the tip; EC11 shaft between its two
     mounting tabs and 7.5 mm from the A-C-B row; LED button cap on the centre
     of its four switch pins), mapped through the board-to-panel offset that
     circuit.py states, against every representation of the holes:
     circuit.PLACEMENT, panel.features(), the hole CSV, the drill SVG, the
     artwork SVG, the panel PCB the generator builds (panel_pcb) and the panel
     PCB in the routed master. The footprints' pin geometry is checked
     against the drawings, so the centres are the parts' and not the
     footprints' idea of them.
  2. Hole sizes against the parts (Thonkiconn 6 mm bushing, the EC11's M7
     bushing and whether it needs an anti-rotation hole, the LED button's
     cap and body), the display window against the active area and the
     module (glass covers the window, active area centred).
  3. Eurorack mechanics (Doepfer A-100): 128.5 mm, 14HP = 70.8 mm, the
     mounting slots 7.5 mm from the left edge and 3 mm from the top and
     bottom, slot size, the 69.6 x 108 boards between the rails and inside
     the panel's width, the PCB-free strips at the top and bottom.
  4. Knob and nut clearances: knobs from the BOM, encoder nuts (across the
     corners), jack nuts, button caps, the window, plugged cables; the
     encoder's thread through the panel at the panel gap the Thonkiconn body
     sets; the LED buttons' square base under the panel and their caps
     proud of it (Thonk's drawing); words clear of the encoders' washers.
  5. Labels: every jack and send button has its word (by circuit.py's labels
     and the routed faceplate's nets), the documented unlabelled controls,
     words clear of holes, nuts, knobs and each other, text height and
     stroke against the fab's minimum, the artwork and the panel PCB alike.
  6. The house frame (title, subtitle, band, rule, mark) against the skill's
     table and the other modules' committed artwork, and the gold mushroom
     mark in the routed master (7 polygons on copper and mask, closed).
  7. Depth behind the panel: panel gap + faceplate + 11 mm header gap + main
     board + the breakout on its sockets + the Seed on the breakout.

Run from side-fx/hardware/tests:  python test_panel.py
Only reads: imports the tools' pure functions, opens the exports as zips.
"""
import csv
import glob
import math
import os
import re
import xml.etree.ElementTree as ET

import sys

sys.dont_write_bytecode = True       # importing harness must not leave __pycache__ here
import harness  # noqa: E402

ck = harness.Checks("panel")
circuit = harness.load("circuit")
panel = harness.load("panel")             # pure functions only (features, layout, copper, check); main() not called
mushroom = harness.load("mushroom")
MIL = harness.MIL
REPO = harness.REPO

# ================================================================ datasheet / spec constants
# Thonkiconn PJ301M-12 (= PJ398SM / WQP518MA), Thonk drawing "'THONKICONN' 3.5mm switching jack socket",
# ver 1, tolerance +-0.15 (thonk.co.uk Thonkiconn_Jack_Datasheet.pdf, read as its drawing image):
#   PCB layout (top view): pin 1 sleeve, 3.10 to pin 2 (switch), 6.48 from pin 1 to the barrel centre,
#   4.92 from the barrel to pin 3 (tip): S-T 11.40.                                                  typ
#   bushing d 6 (thread length 5.5, 4.5 of it threaded); body 9 wide, 10.5 deep (4.5 from the barrel
#   to the sleeve side, 6.0 to the tip side), 9.0 tall from the PCB to the front face.              typ
JACK_S_TN, JACK_S_BARREL, JACK_BARREL_T = 3.10, 6.48, 4.92
JACK_S_T = JACK_S_BARREL + JACK_BARREL_T
JACK_BUSHING_D = 6.0
JACK_BUSHING_L = 5.5
JACK_BODY_H = 9.0          # PCB face to the jack's front face = the panel gap the jacks set (typ, +-0.15)
JACK_TOL = 0.15
# Thonkiconn nut: not on the drawing. House parts.md "nuts are about 8 mm across" (not confirmed): taken as a
# hex 8 AF, the corners (8 / cos 30 = 9.24) as the worst case.
JACK_NUT_AF = 8.0
JACK_NUT_AC = JACK_NUT_AF / math.cos(math.radians(30))
PLUG_BODY_D = 9.0          # moulded 3.5 mm patch-cable plug body, a common max (Tiptop / Doepfer ~6-9 mm)
# Stereo Thonkiconn PJ366ST: three pins in the mono jack's row (house parts.md, from KiCad merge request
# 1073, not merged); the same barrel offset and bushing as the mono. Not confirmed from a QingPu drawing.
# Bourns PEC11R-4xxxF-Sxxxx (PC pins rear facing, push switch), datasheet "PEC11R Series - 12 mm
# Incremental Encoder" REV. D04/26, product dimensions and recommended PCB layout (tolerance <10 mm +-0.3):
#   body 12.5 x 13.4; 6.5 from the PCB to the mounting surface (bushing base)                         typ
#   bushing M7 x 0.75, length LB = 5 (L 15 mm shaft) or 7 (L 20 / 25 / 30)                           typ
#   shaft d 6.0 +-0.1, flat 4.5 (+0/-0.05) over F = 7 (L 15) / 10 (L 20) / 12 (L 25, 30)             typ
#   PCB layout: A C B at 2.5 mm pitch on a row 7.5 from the shaft; switch pins 5.0 apart, 7.0 from the
#   shaft on the other side; pin holes d 1.0 (+0.1/-0); mounting tabs 13.2 apart (on the shaft line,
#   parallel to the rows), tab holes 2.6 x 1.8 (+0.2/-0); no anti-rotation lug on the bushing face.
#   hardware: one flat washer (0.5 thick, d 12.0 +-0.3, hole 7.1 +-0.3) and one M7 x 0.75 hex nut, 2.0 +-0.2
#   thick, 10.0 +-0.5 across. VERIFY 2026-11-13 (page 3 "Hardware", rendered): the nut is drawn corners up and down
#   and the 10.0 spans its two vertical FLATS: 10.0 across flats, 11.55 across the corners (+-0.58). The writer
#   took 10.0 as across the corners. (The 6.5 above was re-read on the side view's vector paths: it runs from the
#   PCB seating face, which Bourns labels MOUNTING SURFACE, to the bushing base; L and LB run from the bushing
#   base.)
ENC_BODY_H = 6.5
ENC_BODY_TOL = 0.3         # Bourns: <10 mm +-0.3
ENC_BODY = (12.5, 13.4)
ENC_BUSHING_D = 7.0        # M7
ENC_LB = {15: 5.0, 20: 7.0, 25: 7.0, 30: 7.0}
ENC_ROW, ENC_SW_ROW, ENC_PITCH, ENC_SW_PITCH = 7.5, 7.0, 2.5, 5.0
ENC_NUT_T, ENC_NUT_AF, ENC_WASHER_T, ENC_WASHER_D = 2.0, 10.0, 0.5, 12.0
ENC_NUT_AC = ENC_NUT_AF / math.cos(math.radians(30))
ENC_NUT_AC_MAX = (ENC_NUT_AF + 0.5) / math.cos(math.radians(30))
# Alps EC11E (catalogue "EC11 11mm Size Metal Shaft Type", April 2019, drawing 5, vertical with push switch, read
# on its vector paths): 4.5 from the PCB to the bushing base, bushing 7, shaft 20 from the bushing base. The
# footprint is KiCad's Alps EC11E, so this is the other part the board is drawn for.
EC11E_BODY_H, EC11E_LB = 4.5, 7.0
# Thonk low-profile LED button (Thonk LowProfileButton.pdf, "TACT SWITCH" rev A, X.X +-0.25, read as rendered at
# 5x): the 14.0 +-0.25 runs from the cap's top down to the underside of the housing's small feet; the 6.3 +-0.2
# from the cap's top down to the UNDERSIDE of the 7.5 mm square base, which is 2.5 thick; the round d5.5 cap is
# the 3.8 above it. So the square base's top is 14.0 - 6.3 + 2.5 = 10.2 above the board (9.85 with the feet
# clipped: the feet are not dimensioned, about 0.35 on the 4:1 drawing, as the Plaitsy suite measured them).
# The base can't pass the 6.5 mm panel hole, so it must sit under the panel. Terminals 3.5 below the board face,
# 0.7 x 0.3t. (Whether the square base moves with the cap or is a fixed cover is not clear from the drawing:
# between the base and the housing there is a ~1 mm gap bridged by two posts, which reads as travel room.)
BTN_TOP, BTN_CAP_H, BTN_BASE_T, BTN_TOL, BTN_FEET = 14.0, 6.3, 2.5, 0.25, 0.35
ENC_SHAFT_L = 15           # the BOM's PEC11R-4215F-S0024: "15" = 15 mm shaft from the mounting surface
# Thonk low-profile LED button (Thonk LowProfileButton.pdf as quoted in module-design parts.md; VERIFY 2026-11-13:
# re-read on the drawing: square 7.5, cap d 5.5, PCB layout 5.08 square and the LED pins 5.4 apart = +-2.7):
# 7.5 mm square body, 5.5 mm round cap; switch pins on a 5.08 mm square round the cap, LED pins +-2.7.
BTN_CAP_D, BTN_BODY, BTN_PIN_SQ, BTN_LED_X = 5.5, 7.5, 5.08, 2.7
# Position tolerance between a panel hole and the part in it (panel drill +-0.1, faceplate drill +-0.1, the
# part's own play in its holes ~0.1): worst-case sum. A hole must clear the part by this per side.
POS_TOL = 0.3
# Waveshare 1.9inch LCD Module (ST7789V2, 170 x 320), Waveshare's dimension drawing as circuit.py quotes it:
# module 51.2 x 27.3; active area 22.70 x 42.72, 6.25 from the flex end, 2.23 from the other end, 2.30 from
# the long sides. (Not re-read here: see the report.)
LCD_MODULE = (27.3, 51.2)
LCD_ACTIVE = (22.70, 42.72)
LCD_FLEX, LCD_FAR, LCD_SIDE = 6.25, 2.23, 2.30
# Eurorack, Doepfer A-100 (doepfer.de/a100_man/a100m_e.htm, "A-100 mechanical details"): 3U panel 128.5 mm;
# HP 5.08 mm; the width table gives 14HP = 70.8 mm; mounting holes 3 mm from the top / bottom edge (122.5 mm
# apart), the first 7.5 mm from the left edge, the others a multiple of 5.08 mm further; M3 screws (hole d
# 3.2); PCBs at most about 108-110 mm tall so they pass between the rails.
PANEL_H, HP_MM, W14 = 128.5, 5.08, 70.8
MOUNT_FROM_EDGE_Y, MOUNT_FROM_LEFT, RAIL_PITCH = 3.0, 7.5, 122.5
SLOT_W_MIN, SLOT_H_MIN = 3.2, 3.2          # the M3 clearance hole Doepfer gives; a slot is at least that
PCB_MAX_H = 108.0                          # the strict end of 108-110 (SDIY wiki "Eurorack": 108-110)
RAIL_CLEAR_MIN = 112.2                     # SDIY wiki: clear space between rails 112.2-115.1 mm, the tightest
SCREW_HEAD_D = 5.6                         # DIN 7985 / ISO 7045 M3 pan head, max
RAIL_ZONE = 10.0                           # SDIY wiki: keep panel-side parts 10 mm from the top / bottom edge
# JLCPCB PCB capabilities (jlcpcb.com/capabilities/pcb-capabilities, silkscreen): line width >= 0.153 mm,
# text height >= 1.0 mm (both min); NPTH milled slot / cutout inner corner radius >= 0.5 mm (1.0 mm bit).
SILK_W_MIN, SILK_H_MIN, MILL_R_MIN = 0.153, 1.0, 0.5
# Depth: standard 2.54 mm headers, female socket body 8.5 mm, male plastic 2.5 mm: a mated pair = 11.0 mm
# (the BOM's 11 mm standoffs). PCBs 1.6 mm (the BOM's PCB lines). The Daisy Seed (Electrosmith datasheet
# v1.0.5) is a 1.6 mm board with parts on top; its tallest is the micro-USB socket, about 3 mm (not
# confirmed: taken as 3.5 mm).
PCB_T, MATED = 1.6, 8.5 + 2.5
SEED_TALLEST = 3.5
# Case depth assumption: a powered 3U case, Doepfer A-100 LC / P6 / P9 style, has about 60 mm or more behind
# the panel (EuroSynth mechanical spec: nominal module depth 60 mm); shallow skiffs 40-50 mm. Not a standard.
CASE_DEPTH = 60.0
SKIFF_DEPTH = 40.0
# Knobs: docs/bom.md "Knob for a 6 mm D-shaft encoder, about 11 mm across" (4 of them).

# ================================================================ what the panel should be
W, H = circuit.PANEL_W, circuit.PANEL_H
BW, BH = circuit.BOARD_W, circuit.BOARD_H
_src = open(os.path.join(harness.TOOLS, "circuit.py"), encoding="utf-8").read()
_m = re.search(r"Panel = board \+ \(([\d.]+), ([\d.]+)\)", _src)
OFF = (float(_m.group(1)), float(_m.group(2))) if _m else None
ck.check("A.offset_stated: circuit.py states the board-to-panel offset", OFF is not None,
         "expected 'Panel = board + (x, y)' in circuit.py's placement comment")
OFF = OFF or ((W - BW) / 2, (H - BH) / 2)
X0, Y0 = OFF

R = harness.routed()
FB, MB = R.face, R.main
PANEL_DOC = R.panel
GEN = harness.read_export(harness.GENERATED)


def gen_panel_doc():
    for u, d in GEN.items():
        if d["docType"] == "PCB" and harness.meta(d).get("title") == harness.BOARD_TITLES["panel"]:
            return d
    return None


GEN_PANEL = gen_panel_doc()


def front(x, y):
    """Routed faceplate (EasyEDA top-layer view = rear of the stack) -> board front view, y up."""
    return BW - x, y


def to_panel(fx, fy):
    """Board front view (y up, origin bottom-left) -> panel mm from the top-left, y down."""
    return fx + X0, H - (fy + Y0)


def pcb_panel(x, y):
    """Panel PCB frame (front, y up, origin bottom-left) -> panel mm from the top-left."""
    return x, H - y


def kind_of(ref):
    return {"J": "jack", "S": "ledbutton", "E": "encoder", "D": "window"}[ref[0]]


PANEL_REFS = sorted(r for r in circuit.PLACEMENT if not r.startswith("DS"))
REFS = {k: [r for r in PANEL_REFS if kind_of(r) == k] for k in ("jack", "ledbutton", "encoder")}

# ================================================================ 1. where the parts are
ck.close("A.offset_x: board centred across the panel ((70.8 - 69.6) / 2)", X0, (W - BW) / 2, 0.005, " mm")
ck.close("A.offset_y: board centred on the panel's height ((128.5 - 108) / 2)", Y0, (H - BH) / 2, 0.005, " mm")
ck.check("A.offset_panel_py: panel.py's BOARD_X0 / Y0 = circuit.py's stated offset",
         abs(panel.BOARD_X0 - X0) < 1e-6 and abs(panel.BOARD_Y0 - Y0) < 1e-6,
         f"panel.py ({panel.BOARD_X0}, {panel.BOARD_Y0}), circuit.py ({X0}, {Y0})")


def centre(ref, pl):
    """Mechanical centre of a placed panel part, from its pads and the drawings (routed board frame)."""
    p = pl["pads"]
    if ref.startswith("J"):
        s, t = p["1"], p["3"]
        d = math.hypot(t.x - s.x, t.y - s.y)
        return s.x + (t.x - s.x) / d * JACK_S_BARREL, s.y + (t.y - s.y) / d * JACK_S_BARREL
    if ref.startswith("ENC"):
        return (p["MP1"].x + p["MP2"].x) / 2, (p["MP1"].y + p["MP2"].y) / 2
    return sum(p[n].x for n in "1234") / 4, sum(p[n].y for n in "1234") / 4


real = {}                 # ref -> panel (x, y) of the real part
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if not ck.check(f"A.on_faceplate.{ref}: on the routed faceplate's panel side", pl is not None and pl["bottom"],
                    "bottom layer" if pl else "missing"):
        continue
    real[ref] = to_panel(*front(*centre(ref, pl)))

# the footprints against the drawings, so centre() works from the real geometry
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    p = pl["pads"]
    cx, cy = centre(ref, pl)
    if ref.startswith("J"):
        st = math.hypot(p["3"].x - p["1"].x, p["3"].y - p["1"].y)
        stn = math.hypot(p["2"].x - p["1"].x, p["2"].y - p["1"].y)
        line = abs((p["2"].x - p["1"].x) * (p["3"].y - p["1"].y) - (p["2"].y - p["1"].y) * (p["3"].x - p["1"].x)) / st
        ck.check(f"A.jack_pins.{ref}: S-T {JACK_S_T:.2f}, S-TN {JACK_S_TN}, in one row (Thonk drawing)",
                 abs(st - JACK_S_T) < 0.02 and abs(stn - JACK_S_TN) < 0.02 and line < 0.02,
                 f"got S-T {st:.3f}, S-TN {stn:.3f}, pin 2 {line:.3f} off the row")
        off = math.hypot(cx - pl["x"], cy - pl["y"])
        ck.close(f"A.jack_origin.{ref}: barrel {abs(circuit.JACK_BARREL)} mm from the footprint origin (circuit.JACK_BARREL)",
                 off, abs(circuit.JACK_BARREL), 0.02, " mm")
        # the barrel is below the origin in the front view, as circuit.py says (negative offset = below)
        fyo, fyb = pl["y"], cy
        ck.check(f"A.jack_origin_side.{ref}: barrel on the origin's side circuit.JACK_BARREL says",
                 (fyb - fyo) * circuit.JACK_BARREL > 0, f"barrel y {fyb:.2f}, origin y {fyo:.2f}")
    elif ref.startswith("ENC"):
        a, c, b, s1, s2 = (p[k] for k in ("A", "C", "B", "S1", "S2"))
        pitch = (math.hypot(a.x - c.x, a.y - c.y), math.hypot(c.x - b.x, c.y - b.y))
        row = math.hypot(c.x - cx, c.y - cy)
        smid = ((s1.x + s2.x) / 2, (s1.y + s2.y) / 2)
        srow = math.hypot(smid[0] - cx, smid[1] - cy)
        spitch = math.hypot(s1.x - s2.x, s1.y - s2.y)
        opposite = (c.x - cx) * (smid[0] - cx) + (c.y - cy) * (smid[1] - cy) < 0
        ck.check(f"A.enc_pins.{ref}: A-C-B {ENC_PITCH} pitch {ENC_ROW} from the shaft, switch pins {ENC_SW_PITCH} "
                 f"apart {ENC_SW_ROW} on the other side (PEC11R layout)",
                 all(abs(q - ENC_PITCH) < 0.02 for q in pitch) and abs(row - ENC_ROW) < 0.02
                 and abs(srow - ENC_SW_ROW) < 0.02 and abs(spitch - ENC_SW_PITCH) < 0.02 and opposite,
                 f"got pitch {pitch[0]:.2f}/{pitch[1]:.2f}, row {row:.2f}, switch row {srow:.2f}, "
                 f"switch pitch {spitch:.2f}, opposite {opposite}")
        ck.check(f"A.enc_origin.{ref}: footprint origin on the shaft (circuit.py: 'encoders: the shaft')",
                 math.hypot(cx - pl["x"], cy - pl["y"]) < 0.02, f"{math.hypot(cx - pl['x'], cy - pl['y']):.3f} mm")
    else:
        xs = sorted(round(p[n].x - cx, 2) for n in "1234")
        ys = sorted(round(p[n].y - cy, 2) for n in "1234")
        sq = all(abs(abs(v) - BTN_PIN_SQ / 2) < 0.02 for v in xs + ys)
        led = (math.hypot(p["5"].x - cx, p["5"].y - cy), math.hypot(p["6"].x - cx, p["6"].y - cy))
        ck.check(f"A.btn_pins.{ref}: switch pins on a {BTN_PIN_SQ} mm square, LED pins {BTN_LED_X} from the cap",
                 sq and all(abs(v - BTN_LED_X) < 0.02 for v in led), f"pins x {xs}, y {ys}; LED {led}")
        ck.check(f"A.btn_origin.{ref}: footprint origin on the cap", math.hypot(cx - pl["x"], cy - pl["y"]) < 0.02,
                 f"{math.hypot(cx - pl['x'], cy - pl['y']):.3f} mm")

# the pad model (EasyEDA's bottom-side mirror) is right if the routed tracks end on the pads it puts there
ends = [t["a"] for t in FB.tracks] + [t["b"] for t in FB.tracks]
missed = []
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    for num, pad in pl["pads"].items():
        if pad.net in (None, "", "GND_F", "GND_D_F"):
            continue                     # ground pads may sit in a pour without a track
        if not any(pad.d_point(e) < 0.01 for e in ends) and not any(
                math.hypot(v["c"][0] - pad.x, v["c"][1] - pad.y) < 0.01 for v in FB.vias):
            missed.append(f"{ref}.{num}")
ck.check("A.pad_model: routed tracks end on the modelled panel-part pads (frame and mirror right)", not missed,
         f"{len(missed)} signal pads without a track end: {missed[:8]}")

# intent: circuit.PLACEMENT (jacks: origin + JACK_BARREL) is where the user wants the holes
for ref in PANEL_REFS:
    if ref not in real:
        continue
    x, y, _ = circuit.PLACEMENT[ref]
    want = to_panel(x, y + (circuit.JACK_BARREL if ref.startswith("J") else 0.0))
    d = math.hypot(real[ref][0] - want[0], real[ref][1] - want[1])
    ck.check(f"A.placement.{ref}: routed part at circuit.PLACEMENT", d < 0.05,
             f"expected ({want[0]:.3f}, {want[1]:.3f}), got ({real[ref][0]:.3f}, {real[ref][1]:.3f}), off {d:.3f} mm")
# the offset each routed part implies between its board position and panel.features()' hole: one for all
feats = panel.features()
fpos = {ref: (kind, *panel.panel_xy(hx, hy)) for kind, ref, label, ox, oy, hx, hy in feats}
offs = []
for ref in real:
    pl = FB.parts[ref]
    bx, by = front(*centre(ref, pl))
    offs.append((fpos[ref][1] - bx, H - fpos[ref][2] - by))
if offs:
    ox = sum(o[0] for o in offs) / len(offs)
    oy = sum(o[1] for o in offs) / len(offs)
    spread = max(math.hypot(o[0] - ox, o[1] - oy) for o in offs)
    ck.check("A.one_offset: every routed part sits at the same offset from its panel hole, the stated one",
             spread < 0.05 and abs(ox - X0) < 0.05 and abs(oy - Y0) < 0.05,
             f"expected ({X0}, {Y0}); got ({ox:.3f}, {oy:.3f}), spread {spread:.3f} mm")

HOLE_D = {"jack": panel.HOLE["jack"], "ledbutton": panel.HOLE["ledbutton"], "encoder": panel.HOLE["encoder"]}


def match(name, got, tol=0.05):
    """got: [(x, y, d)] round panel holes (panel frame). Every real part has exactly one hole on its centre,
    of panel.HOLE's size for its kind, and there is no other round hole."""
    used = set()
    for ref in PANEL_REFS:
        if ref not in real:
            continue
        x, y = real[ref]
        if not got:
            ck.check(f"{name}: hole over {ref}", False, "no holes")
            continue
        dist, i, hd = min((math.hypot(hx - x, hy - y), i, hd) for i, (hx, hy, hd) in enumerate(got))
        used.add(i)
        want_d = HOLE_D[kind_of(ref)]
        ck.check(f"{name}: hole over {ref}", dist <= tol and abs(hd - want_d) < 0.02,
                 f"expected d {want_d} at ({x:.2f}, {y:.2f}); nearest d {hd:.2f}, {dist:.3f} mm off")
    extra = [got[i] for i in range(len(got)) if i not in used]
    ck.check(f"{name}: no other round holes", not extra and len(got) == len(real),
             f"expected {len(real)}, got {len(got)}; extra {extra[:4]}")


rows = list(csv.DictReader(open(os.path.join(harness.PANEL, "side-fx-panel-holes.csv"), encoding="utf-8")))
csv_holes = [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), float(r["hole_mm"]))
             for r in rows if r["kind"] in ("jack", "ledbutton", "encoder")]
match("A.csv", csv_holes, tol=0.01)
csv_mounts = [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"])) for r in rows if r["kind"] == "mount"]
csv_win = [r for r in rows if r["kind"] == "window"]

SVG_NS = "{http://www.w3.org/2000/svg}"


def svg_root(name):
    return ET.parse(os.path.join(harness.PANEL, name)).getroot()


def rects(root):
    """[(cx, cy, w, h, rx)] of an SVG's rect elements."""
    out = []
    for r in root.iter(SVG_NS + "rect"):
        x, y, w_, h_ = (float(r.get(k)) for k in ("x", "y", "width", "height"))
        out.append((x + w_ / 2, y + h_ / 2, w_, h_, float(r.get("rx") or 0)))
    return out


drill = svg_root("side-fx-panel-drill.svg")
drill_holes = [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in drill.iter(SVG_NS + "circle")]
match("A.drill_svg", drill_holes, tol=0.01)
drill_rects = [r for r in rects(drill) if r[4] > 0]            # slots and the window (rounded); frame rects have rx 0
art = svg_root("side-fx-panel.svg")
groups = {g.get("id"): g for g in art.iter(SVG_NS + "g")}
art_holes = [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in groups["holes"].iter(SVG_NS + "circle")]
match("A.artwork_svg", art_holes, tol=0.01)
art_rects = rects(groups["holes"])


def pcb_holes(doc):
    """(round holes [(x, y, d)], rounded cut-outs [(cx, cy, w, h)], outline) of a panel PCB doc, panel frame."""
    ca = harness.load("copper_audit")
    holes, cuts, outline = [], [], None
    for h, p in doc["recs"]:
        if h["type"] == "FILL" and p["layerId"] == 12:
            if p["path"][0][0] == "CIRCLE":
                _, x, y, r = p["path"][0]
                holes.append((*pcb_panel(x * MIL, y * MIL), 2 * r * MIL))
            else:
                pts = ca.flatten_path(p["path"][0] if isinstance(p["path"][0], list) else p["path"], MIL)
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                cuts.append(((min(xs) + max(xs)) / 2, H - (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)))
        elif h["type"] == "POLY" and p.get("polyType") == "BOARD_OUTLINE":
            outline = p["path"]
    return holes, cuts, outline


pp_holes, pp_cuts, pp_outline = pcb_holes(PANEL_DOC)
match("A.panel_pcb_routed", pp_holes, tol=0.05)
if GEN_PANEL is not None:
    g_holes, g_cuts, g_outline = pcb_holes(GEN_PANEL)
    match("A.panel_pcb_generated", g_holes, tol=0.05)
else:
    ck.check("A.panel_pcb_generated: SideFXy.epro2 has the panel PCB", False, "not found")
    g_cuts, g_outline = [], None
# the generator's in-memory panel PCB (panel_pcb.PanelBoard: builds, writes nothing)
try:
    panel_pcb = harness.load("panel_pcb")
    PB = panel_pcb.PanelBoard()
    match("A.panel_pcb_builder", [(*pcb_panel(x, y), d) for x, y, d in PB.holes], tol=0.01)
except Exception as e:                       # noqa: BLE001  (an import problem is a finding, not a crash)
    ck.check("A.panel_pcb_builder: panel_pcb.PanelBoard() builds", False, f"{type(e).__name__}: {e}")
    PB = None

# ================================================================ 2. hole sizes vs the parts, the display window
# JLCPCB (capabilities page): holes >= 6.3 mm are CNC routed; non-plated routed tolerance +-0.2 mm
HOLE_TOL = 0.2
ALIGN = 0.1               # per side: faceplate drill + panel hole position, the part seated in its holes
hj, hb, he = HOLE_D["jack"], HOLE_D["ledbutton"], HOLE_D["encoder"]
ck.check("B.jack_hole: smallest jack hole clears the 6 mm bushing (+0.1 per side)",
         hj - HOLE_TOL >= JACK_BUSHING_D + 2 * ALIGN, f"hole {hj} - {HOLE_TOL} vs bushing {JACK_BUSHING_D} + {2 * ALIGN}")
ck.check("B.jack_nut_bearing: the 8 mm nut covers the largest jack hole with >= 0.5 mm per side",
         JACK_NUT_AF >= hj + HOLE_TOL + 1.0, f"nut {JACK_NUT_AF} AF vs hole {hj} + {HOLE_TOL} + 1.0")
ck.check("B.enc_hole: smallest encoder hole clears the M7 bushing (+0.1 per side)",
         he - HOLE_TOL >= ENC_BUSHING_D + 2 * ALIGN, f"hole {he} - {HOLE_TOL} vs M7 + {2 * ALIGN}")
ck.check("B.enc_hole_washer: the PEC11R washer (d 12.0) bears >= 1.5 mm round the largest encoder hole",
         (ENC_WASHER_D - 0.3 - (he + HOLE_TOL)) / 2 >= 1.5, f"washer {ENC_WASHER_D} - 0.3, hole {he} + {HOLE_TOL}")
ck.check("B.enc_antirotation: no anti-rotation hole needed (PEC11R has no lug) and none drilled",
         len(pp_holes) == len(real) and not any(abs(d - 3.2) < 0.4 for *_, d in pp_holes),
         f"{len(pp_holes)} round holes on the routed panel")
ck.check("B.btn_hole: smallest button hole passes the 5.5 mm cap with the position tolerance",
         hb - HOLE_TOL >= BTN_CAP_D + 2 * POS_TOL, f"hole {hb} - {HOLE_TOL} vs cap {BTN_CAP_D} + 2 x {POS_TOL}")
ck.check("B.btn_body: the 7.5 mm body stays behind the largest button hole", hb + HOLE_TOL < BTN_BODY,
         f"hole {hb} + {HOLE_TOL} vs body {BTN_BODY}")
ck.check("B.btn_ring: send-button silk ring clear of the hole (ring - 0.175 >= hole r + tol + 0.15)",
         panel.ART["ring"] - 0.175 >= hb / 2 + HOLE_TOL + 0.15, f"ring r {panel.ART['ring']}, hole r {hb / 2}")

# the display: the active area against the window and the module
ck.check("B.lcd_active_area: circuit.DISPLAY_ACTIVE = Waveshare's 22.70 x 42.72",
         all(abs(a - b) < 0.005 for a, b in zip(circuit.DISPLAY_ACTIVE, LCD_ACTIVE)), str(circuit.DISPLAY_ACTIVE))
ck.check("B.lcd_drawing_sums: the active area's offsets add up to the 27.3 x 51.2 module",
         abs(LCD_SIDE * 2 + LCD_ACTIVE[0] - LCD_MODULE[0]) < 0.01
         and abs(LCD_FLEX + LCD_FAR + LCD_ACTIVE[1] - LCD_MODULE[1]) < 0.01, "")
ax, ay = circuit.PLACEMENT["DS1"][:2]
mx1, my1, mx2, my2 = circuit.DISPLAY_MODULE
ck.check("B.lcd_module_outline: circuit.DISPLAY_MODULE = the module round the active area (flex end up)",
         abs(ax - mx1 - (LCD_SIDE + LCD_ACTIVE[0] / 2)) < 0.01 and abs(mx2 - ax - (LCD_SIDE + LCD_ACTIVE[0] / 2)) < 0.01
         and abs(ay - my1 - (LCD_FAR + LCD_ACTIVE[1] / 2)) < 0.01 and abs(my2 - ay - (LCD_FLEX + LCD_ACTIVE[1] / 2)) < 0.01,
         f"module {circuit.DISPLAY_MODULE}, active centre ({ax}, {ay})")
WIN = panel.WINDOW
wx, wy = to_panel(ax, ay)
ck.close("B.readme_window_w: README's window width (23.7)", WIN[0], 23.7, 0.05, " mm")
ck.close("B.readme_window_h: README's window height (43.7)", WIN[1], 43.7, 0.05, " mm")
mw = min(WIN[0] - LCD_ACTIVE[0], WIN[1] - LCD_ACTIVE[1]) / 2
ck.check("B.window_shows_active: window >= active area + the position tolerance on each side", mw >= POS_TOL,
         f"margin {mw:.2f} mm per side, tolerance {POS_TOL}")
# module edges (panel frame) round the window: the glass and its black border must cover the window
pm = (mx1 + X0, H - (my2 + Y0), mx2 + X0, H - (my1 + Y0))           # x1, y1 (top), x2, y2 (bottom)
wn = (wx - WIN[0] / 2, wy - WIN[1] / 2, wx + WIN[0] / 2, wy + WIN[1] / 2)
cover = min(wn[0] - pm[0], wn[1] - pm[1], pm[2] - wn[2], pm[3] - wn[3])
ck.check("B.module_covers_window: the module overlaps the window by >= 1 mm on every side", cover >= 1.0,
         f"tightest {cover:.2f} mm (module {tuple(round(v, 2) for v in pm)}, window {tuple(round(v, 2) for v in wn)})")
ck.check("B.window_corner: window corner radius >= the mill's 0.5 mm", panel.WINDOW_R >= MILL_R_MIN, f"r {panel.WINDOW_R}")
# every representation of the window and the slots
def check_window(name, rects_):
    near = [r for r in rects_ if abs(r[0] - wx) < 0.05 and abs(r[1] - wy) < 0.05]
    ck.check(f"B.window.{name}: one {WIN[0]:.2f} x {WIN[1]:.2f} window on the active area's centre",
             len(near) == 1 and abs(near[0][2] - WIN[0]) < 0.02 and abs(near[0][3] - WIN[1]) < 0.02,
             f"expected centre ({wx:.2f}, {wy:.2f}); got {[tuple(round(v, 2) for v in r[:4]) for r in near] or 'none'}")


check_window("drill_svg", drill_rects)
check_window("artwork_svg", art_rects)
check_window("panel_pcb_routed", pp_cuts)
check_window("panel_pcb_generated", g_cuts)
cw = csv_win[0] if csv_win else None
ck.check("B.window.csv: the CSV gives the window's centre and size", cw is not None
         and abs(float(cw["panel_x_from_left"]) - wx) < 0.01 and abs(float(cw["panel_y_from_top"]) - wy) < 0.01
         and f"{WIN[0]:.2f} x {WIN[1]:.2f}" in cw["hole_mm"], str(cw and dict(cw)))
# the module in the panel gap must not sit on another panel-gap part (housings of jacks, encoders, buttons)
worst = None
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    x1, y1, x2, y2 = pl["body"]
    fx1, fx2 = BW - x2, BW - x1                         # front view
    g = max(mx1 - fx2, fx1 - mx2, my1 - y2, y1 - my2)    # > 0: apart
    if worst is None or g < worst[0]:
        worst = (g, ref)
ck.check("B.module_clear_of_parts: display module clear of every panel part's housing (>= 0.5 mm)",
         worst is not None and worst[0] >= 0.5, f"tightest {worst[1]}: {worst[0]:.2f} mm" if worst else "")

# ================================================================ 3. Eurorack mechanics
ck.close("C.height: panel 128.5 mm (Doepfer)", H, PANEL_H, 0.001, " mm")
ck.check("C.width: 14HP = 70.8 mm (Doepfer's table)", circuit.HP == 14 and abs(W - W14) < 0.005,
         f"HP {circuit.HP}, W {W}")
for name, outl in (("routed", pp_outline), ("generated", g_outline)):
    if outl and outl[0] == "R":
        ow, oh = outl[3] * MIL, outl[4] * MIL
        ck.check(f"C.outline.{name}: panel PCB 70.8 x 128.5", abs(ow - W14) < 0.01 and abs(oh - PANEL_H) < 0.01,
                 f"got {ow:.3f} x {oh:.3f}")
    else:
        ck.check(f"C.outline.{name}: panel PCB has a rectangular outline", False, str(outl)[:80])
want_m = sorted((x, y) for x in (MOUNT_FROM_LEFT, MOUNT_FROM_LEFT + (circuit.HP - 3) * HP_MM)
                for y in (MOUNT_FROM_EDGE_Y, PANEL_H - MOUNT_FROM_EDGE_Y))
slots = {"csv": [(x, y, None, None) for x, y in csv_mounts],
         "drill_svg": [r[:4] for r in drill_rects if abs(r[2] - WIN[0]) > 1],
         "artwork_svg": [r[:4] for r in art_rects if abs(r[2] - WIN[0]) > 1],
         "panel_pcb_routed": [c for c in pp_cuts if abs(c[2] - WIN[0]) > 1],
         "panel_pcb_generated": [c for c in g_cuts if abs(c[2] - WIN[0]) > 1]}
for name, got in slots.items():
    pos = sorted((round(x, 3), round(y, 3)) for x, y, *_ in got)
    ok = len(pos) == 4 and all(math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02 for a, b in zip(pos, want_m))
    ck.check(f"C.mounts.{name}: four mounting holes 7.5 from the left, 3 from top / bottom, 11 x 5.08 apart", ok,
             f"expected {want_m}, got {pos}")
    if pos and len(pos) == 4:
        dx = pos[2][0] - pos[0][0]
        ck.check(f"C.mount_grid.{name}: horizontal spacing a multiple of 5.08 (Doepfer)",
                 abs(dx / HP_MM - round(dx / HP_MM)) < 0.004, f"{dx:.3f} mm = {dx / HP_MM:.3f} HP")
        ck.close(f"C.mount_rails.{name}: vertical spacing 122.5 (the rails)", pos[1][1] - pos[0][1], RAIL_PITCH, 0.02, " mm")
    for x, y, sw, sh in got:
        if sw is None:
            continue
        ck.check(f"C.slot_size.{name}.({x:.1f},{y:.1f}): slot >= the 3.2 mm M3 hole both ways, horizontal",
                 sh >= SLOT_H_MIN - 0.01 and sw >= sh and abs(sw - panel.SLOT_W) < 0.02 and abs(sh - panel.SLOT_H) < 0.02,
                 f"got {sw:.2f} x {sh:.2f}")
ck.check("C.screw_head: the M3 head (d 5.6 max) covers the slot's 3.2 width with >= 1 mm per side",
         SCREW_HEAD_D >= panel.SLOT_H + 2 * 1.0, f"head {SCREW_HEAD_D}, slot {panel.SLOT_W} x {panel.SLOT_H}")
ck.check("C.right_mount_margin: right slot >= 5 mm inside the right edge",
         W - (MOUNT_FROM_LEFT + (circuit.HP - 3) * HP_MM) - panel.SLOT_W / 2 >= 3.5,
         f"{W - (MOUNT_FROM_LEFT + (circuit.HP - 3) * HP_MM):.2f} mm to the slot centre")
for b in (FB, MB):
    x1, y1, x2, y2 = b.outline
    ck.check(f"C.board_size.{b.title}: {BW} x {BH}", abs(x2 - x1 - BW) < 0.01 and abs(y2 - y1 - BH) < 0.01,
             f"got {x2 - x1:.2f} x {y2 - y1:.2f}")
ck.check("C.board_height: <= 108 mm (passes between the rails)", BH <= PCB_MAX_H, f"{BH}")
ck.check("C.rail_clearance: >= 1 mm from the board edge to the tightest rails (112.2 clear)",
         (RAIL_CLEAR_MIN - BH) / 2 >= 1.0, f"{(RAIL_CLEAR_MIN - BH) / 2:.2f} mm")
ck.check("C.neighbours: board inside the panel's width (neighbours' boards butt at the panel edges)",
         X0 >= 0.3 and BW + 2 * X0 <= W + 1e-6, f"{X0:.2f} mm each side")
for b in (FB, MB):
    worst = None
    for ref, pl in b.parts.items():
        x1, y1, x2, y2 = pl["body"]
        pads = pl["pads"].values()
        lo_x = min([x1] + [p.x - p.w / 2 for p in pads])
        hi_x = max([x2] + [p.x + p.w / 2 for p in pads])
        lo_y = min([y1] + [p.y - p.h / 2 for p in pads])
        hi_y = max([y2] + [p.y + p.h / 2 for p in pads])
        m = min(lo_x, BW - hi_x, lo_y, BH - hi_y)
        if worst is None or m < worst[0]:
            worst = (m, ref)
    ck.check(f"C.parts_on_board.{b.title}: every part's housing and pads inside the outline", worst[0] >= -0.01,
             f"tightest {worst[1]}: {worst[0]:.2f} mm")
# panel-gap parts and the module clear of the rail strips (>= 10 mm from the top / bottom edge)
gap_items = []
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is not None:
        x1, y1, x2, y2 = pl["body"]
        gap_items.append((ref, H - Y0 - y2, H - Y0 - y1))
gap_items.append(("DS1 module", pm[1], pm[3]))
for ref, top, bot in gap_items:
    ck.check(f"C.rail_zone.{ref}: >= {RAIL_ZONE} mm from the top and bottom edges",
             top >= RAIL_ZONE and H - bot >= RAIL_ZONE, f"panel y {top:.2f} .. {bot:.2f}")
ck.check("C.module_in_width: display module inside the panel's width", pm[0] >= 0.5 and pm[2] <= W - 0.5,
         f"x {pm[0]:.2f} .. {pm[2]:.2f}")

# ================================================================ 4. knobs, nuts, fingers
bom_md = open(os.path.join(harness.DOCS, "bom.md"), encoding="utf-8").read()
_k = re.search(r"\| (\d+) \| Knob for a 6 mm D-shaft encoder, about ([\d.]+) mm across", bom_md)
KNOB_D = float(_k.group(2)) if _k else 2 * panel.ART["knob"]
ck.check("D.bom_knobs: bom.md orders one knob per encoder and gives its size", _k is not None
         and int(_k.group(1)) == len(REFS["encoder"]), f"{_k.group(0) if _k else 'no knob line'}")
ck.check("D.art_knob: the artwork's knob is the BOM's size (+-0.5 mm)", abs(2 * panel.ART["knob"] - KNOB_D) <= 0.5,
         f"artwork d {2 * panel.ART['knob']}, BOM {KNOB_D}")
# VERIFY 2026-11-13: the nut's 10.0 is across flats (see the constants): the corners are 11.55 (12.13 max)
ck.check("D.knob_hides_nut: the knob (BOM size) covers the encoder nut's corners (PEC11R nut 10.0 +-0.5 across flats)",
         KNOB_D >= ENC_NUT_AC_MAX, f"knob {KNOB_D} vs nut corners {ENC_NUT_AC:.2f} ({ENC_NUT_AC_MAX:.2f} max)")
# VERIFY 2026-11-13: an encoder's footprint on the panel is the larger of its knob and the nut's corners (the
# washer under the nut, d 12.0 +-0.3, is flat; it covers words but no finger needs room round it)
R_PHYS = {"encoder": max(KNOB_D, ENC_NUT_AC_MAX) / 2, "jack": JACK_NUT_AC / 2, "ledbutton": BTN_CAP_D / 2}
items = [(ref, kind_of(ref), *real[ref], R_PHYS[kind_of(ref)]) for ref in real]
min_gap = {("encoder", "encoder"): 4.0, ("jack", "jack"): 2.0, ("encoder", "ledbutton"): 3.0, ("encoder", "jack"): 2.0,
           ("jack", "ledbutton"): 2.0, ("ledbutton", "ledbutton"): 3.0}
worst = {}
for i, (a, ka, xa, ya, ra) in enumerate(items):
    for b, kb, xb, yb, rb in items[i + 1:]:
        g = math.hypot(xa - xb, ya - yb) - ra - rb
        key = tuple(sorted((ka, kb)))
        if key not in worst or g < worst[key][0]:
            worst[key] = (g, a, b)
for key, (g, a, b) in sorted(worst.items()):
    ck.check(f"D.edge_gap.{key[0]}-{key[1]}: >= {min_gap[key]} mm ({KNOB_D:g} mm knobs, nut corners {JACK_NUT_AC:.2f}, "
             f"caps {BTN_CAP_D})", g >= min_gap[key] - 0.005, f"tightest {a}-{b}: {g:.2f} mm")
for ref, k, x, y, r in items:
    gx = max(wn[0] - x, 0, x - wn[2])
    gy = max(wn[1] - y, 0, y - wn[3])
    g = math.hypot(gx, gy) - r
    if g < 1.0:
        ck.check(f"D.window_gap.{ref}: knob / nut / cap >= 1 mm from the window", False, f"{g:.2f} mm")
ck.check("D.window_gap: every knob, nut and cap >= 1 mm from the window",
         all(math.hypot(max(wn[0] - x, 0, x - wn[2]), max(wn[1] - y, 0, y - wn[3])) - r >= 1.0 for _, _, x, y, r in items), "")
for ref, k, x, y, r in items:
    e = min(x, W - x) - r
    if e < 2.0:
        ck.check(f"D.edge.{ref}: >= 2 mm to the panel's side edge (a neighbour's knob)", False, f"{e:.2f} mm")
ck.check("D.edges: every knob, nut and cap >= 2 mm from the panel's side edges",
         all(min(x, W - x) - r >= 2.0 for _, _, x, y, r in items), "")
# plugged cables: a 9 mm plug body next to another plug or a knob
for ref, k, x, y, r in items:
    if k != "jack":
        continue
    for o, ko, xo, yo, ro in items:
        if o == ref or ko == "ledbutton":
            continue
        d = math.hypot(x - xo, y - yo)
        need = PLUG_BODY_D / 2 + (PLUG_BODY_D / 2 + 0.5 if ko == "jack" else ro + 1.5)
        if d < need:
            ck.check(f"D.plug.{ref}-{o}: a plug in {ref} clear of {o}", False, f"centres {d:.2f} mm, need {need:.2f}")
ck.check("D.plugs: 9 mm plug bodies clear of each other (0.5 mm) and of the knobs (1.5 mm)",
         all(math.hypot(x - xo, y - yo) >= PLUG_BODY_D / 2 + (PLUG_BODY_D / 2 + 0.5 if ko == "jack" else ro + 1.5)
             for ref, k, x, y, r in items if k == "jack" for o, ko, xo, yo, ro in items
             if o != ref and ko != "ledbutton"), "")
# screw heads against the panel's parts
for mx, my in want_m:
    for ref, k, x, y, r in items:
        if math.hypot(mx - x, my - y) - r - SCREW_HEAD_D / 2 < 1.0:
            ck.check(f"D.screw_head.{ref}: screw head at ({mx}, {my}) clear of {ref}", False, "")
# the encoder in the panel gap the jacks set: its thread must come through the panel for the washer and nut
PANEL_T = 1.6
LB = ENC_LB[ENC_SHAFT_L]
proud = ENC_BODY_H + LB - (JACK_BODY_H + PANEL_T)
print(f"INFO  panel gap = Thonkiconn body {JACK_BODY_H} mm; PEC11R-42{ENC_SHAFT_L}F: mounting surface {ENC_BODY_H} mm, "
      f"bushing {LB} mm -> thread {proud:.2f} mm in front of a {PANEL_T} mm panel; "
      f"{ENC_BODY_H + ENC_LB[20] - JACK_BODY_H - PANEL_T:.2f} mm with the 20 mm shaft (7 mm bushing)")
ck.check(f"D.enc_thread_through_panel: the {ENC_SHAFT_L} mm-shaft PEC11R's bushing reaches through the panel far "
         f"enough for its washer and nut ({ENC_WASHER_T} + {ENC_NUT_T} mm)",
         proud - JACK_TOL - 0.3 >= ENC_WASHER_T + ENC_NUT_T,
         f"thread in front of the panel {proud:.2f} mm (worst {proud - JACK_TOL - 0.3:.2f}) at the {JACK_BODY_H} mm gap; "
         f"need {ENC_WASHER_T + ENC_NUT_T}")
ck.check("D.enc_body_gap: the encoder body sits under the panel with <= 1 mm air (a nut can pull it up)",
         JACK_BODY_H - ENC_BODY_H <= 1.0, f"body top {ENC_BODY_H} mm, panel rear {JACK_BODY_H} mm: "
                                          f"{JACK_BODY_H - ENC_BODY_H:.1f} mm of air under the panel")
print(f"INFO  the footprint's Alps EC11E: body {EC11E_BODY_H} + bushing {EC11E_LB} -> "
      f"{EC11E_BODY_H + EC11E_LB - JACK_BODY_H - PANEL_T:.2f} mm of thread in front of the panel, "
      f"{JACK_BODY_H - EC11E_BODY_H:.1f} mm of air under it (the same problem as the 15 mm PEC11R)")
# VERIFY 2026-11-13 (new): the LED buttons in the same gap (Thonk's drawing): the square body must stay behind
# the panel, the cap stand proud of it
btn_base_top = BTN_TOP - BTN_CAP_H + BTN_BASE_T
ck.check("D.btn_base_under_panel: the LED button's 7.5 mm square base (top 14.0 - 6.3 + 2.5 = 10.2 above the board, "
         "Thonk drawing; 9.85 with its feet clipped) sits under the panel's rear, which the jacks set at 9.0 "
         "(nominal figures: it fails without the tolerances)",
         btn_base_top - BTN_FEET <= JACK_BODY_H,
         f"base top {btn_base_top:.2f} ({btn_base_top - BTN_FEET:.2f} feet clipped) vs panel rear {JACK_BODY_H:.2f} mm: "
         f"the panel rests on the five buttons {btn_base_top - BTN_FEET - JACK_BODY_H:.2f}-{btn_base_top - JACK_BODY_H:.2f} "
         "mm above the jacks' faces")
cap_proud = BTN_TOP - BTN_TOL - (JACK_BODY_H + JACK_TOL + PANEL_T)
ck.check("D.btn_cap_proud: the button cap stands >= 1 mm proud of the panel's front (worst case)", cap_proud >= 1.0,
         f"cap top {BTN_TOP} -{BTN_TOL}, panel front {JACK_BODY_H + JACK_TOL + PANEL_T:.2f}: {cap_proud:.2f} mm proud")
shaft_out = ENC_BODY_H + ENC_SHAFT_L - JACK_BODY_H - PANEL_T
ck.check("D.enc_shaft_for_knob: the shaft's D flat stands fully in front of the panel and the nut",
         shaft_out - max(0.0, ENC_NUT_T + ENC_WASHER_T - max(proud, 0)) >= {15: 7.0, 20: 10.0}[ENC_SHAFT_L],
         f"shaft {shaft_out:.1f} mm in front of the panel")
readme = open(os.path.join(harness.MODULE, "README.md"), encoding="utf-8").read()
_g = re.search(r"assumes about ([\d.]+) mm between panel and\s+faceplate", readme)
ck.check("D.readme_panel_gap: README's assumed panel gap = the Thonkiconn's 9 mm body (Thonk drawing)",
         _g is not None and abs(float(_g.group(1)) - JACK_BODY_H) <= 0.5,
         f"README {_g.group(1) if _g else '?'} mm, Thonk drawing body {JACK_BODY_H} mm")
_d = re.search(r"module is about ([\d.]+) mm plus ([\d.]+) mm of parts", readme)
if _d:
    ck.check("D.module_in_gap: the display module (README: body + rear parts) fits the panel gap",
             float(_d.group(1)) + float(_d.group(2)) <= JACK_BODY_H - 1.0,
             f"{_d.group(1)} + {_d.group(2)} mm vs gap {JACK_BODY_H} - 1 mm for the rear solder tails")

# ================================================================ 5. labels
JACK_WORD = {"IN1_F": "IN 1", "IN2_F": "IN 2", "OUT1_F": "OUT 1", "OUT2_F": "OUT 2", "CLK_IN_F": "CLOCK",
             "CV1_F": "CV 1", "CV2_F": "CV 2", "CV3_F": "CV 3", "CV4_F": "CV 4", "MIDI_TIP_F": "MIDI"}   # design.md
fnet = {ref: FB.parts[ref]["nets"] for ref in real}


def jack_word(ref):
    return JACK_WORD.get(fnet[ref].get("3"))


def button_word(ref):
    n = fnet[ref]
    m3, m5 = re.match(r"^BTN_([A-Z]+)_F$", n.get("3", "")), re.match(r"^LED_([A-Z]+)_F$", n.get("5", ""))
    return m3.group(1) if m3 and m5 and m3.group(1) == m5.group(1) and n.get("4") == n.get("3") else None


def svg_words():
    """Artwork words outside #mockup: (text, x, baseline y, size, anchor, class)."""
    out = []
    for gid in ("silk", "copper"):
        for t in groups[gid].iter(SVG_NS + "text"):
            out.append((t.text.strip(), float(t.get("x")), float(t.get("y")), float(t.get("font-size")),
                        t.get("text-anchor") or "start", t.get("class") or ""))
    return out


def pcb_words(doc):
    """STRINGs of a panel PCB: (text, centre x, baseline y, size (panel_pcb's), stroke, height, angle)."""
    out = []
    for h, p in doc["recs"]:
        if h["type"] == "STRING":
            size = p["fontSize"] * MIL / 0.9
            width = 0.62 * size * len(p["text"])
            out.append((p["text"], p["x"] * MIL + width / 2, H - p["y"] * MIL, size, p["strokeWidth"] * MIL,
                        p["fontSize"] * MIL, p["angle"], p["layerId"]))
    return out


AW = svg_words()
want_words = sorted([circuit_lbl for _, circuit_lbl, *_ in circuit.JACKS]
                    + [lbl for ref, lbl, _ in circuit.BUTTONS if ref != "SW5"] + [panel.ART["title"], panel.ART["subtitle"]])
design = open(os.path.join(harness.DOCS, "design.md"), encoding="utf-8").read()
ck.check("E.unlabelled_documented: SHIFT unlabelled and the knobs named by the screen, as design.md says",
         "| Extra button | red, unlabelled |" in design and "| Knobs | 4, labelled by the screen |" in design,
         "design.md's SIDE FX table")
for name, words in (("artwork", sorted(w[0] for w in AW)),
                    ("panel_pcb_routed", sorted(w[0] for w in pcb_words(PANEL_DOC))),
                    ("panel_pcb_generated", sorted(w[0] for w in pcb_words(GEN_PANEL)) if GEN_PANEL else [])):
    ck.check(f"E.words.{name}: the jacks' and send buttons' labels (circuit.py) + title + subtitle, nothing else",
             words == want_words, f"only panel {sorted(set(words) - set(want_words))}, "
                                  f"missing {sorted(set(want_words) - set(words))}")
for name, words in (("artwork", [(w[0], w[1] if w[4] == "middle" else None, w[2]) for w in AW]),
                    ("panel_pcb_routed", [(w[0], w[1], w[2]) for w in pcb_words(PANEL_DOC)])):
    for ref in REFS["jack"]:
        x, y = real[ref]
        over = [w for w, wx_, wy_ in words if wx_ is not None and abs(wx_ - x) < 0.6 and 4.5 < y - wy_ < 7.0]
        want = jack_word(ref)
        ck.check(f"E.jack_word.{name}.{ref}: one word over the jack, naming its tip net ({fnet[ref].get('3')})",
                 len(over) == 1 and want is not None and over[0] == want, f"expected {want!r}, got {over}")
    for ref in REFS["ledbutton"]:
        x, y = real[ref]
        under = [w for w, wx_, wy_ in words if wx_ is not None and abs(wx_ - x) < 0.6 and 0 < wy_ - y < 9.0]
        want = button_word(ref)
        if ref == "SW5":
            ck.check(f"E.button_word.{name}.SW5: SHIFT carries no word (documented)", not under, str(under))
            continue
        ck.check(f"E.button_word.{name}.{ref}: one word under the button, naming its switch and LED nets",
                 len(under) == 1 and want is not None and under[0] == want, f"expected {want!r}, got {under}")
# the circuit's own labels name the same signals as the nets (circuit.JACKS label vs its tip net)
for ref, lbl, tip, tn in circuit.JACKS:
    ck.check(f"E.circuit_label.{ref}: circuit.py's label '{lbl}' = the routed tip net's word", ref in fnet
             and jack_word(ref) == lbl, f"tip {fnet.get(ref, {}).get('3')} -> {jack_word(ref) if ref in fnet else None}")
# the fab's text limits (panel PCB STRINGs, routed master)
PW = pcb_words(PANEL_DOC)
small = [(w[0], round(w[5], 2)) for w in PW if w[5] < SILK_H_MIN]
thin = [(w[0], round(w[4], 3)) for w in PW if w[4] < SILK_W_MIN]
ck.check("E.text_height: every panel string >= JLCPCB's 1.0 mm text height", not small, f"{small or len(PW)}")
ck.check("E.text_stroke: every panel string's stroke >= JLCPCB's 0.15 mm", not thin, f"{thin or len(PW)}")
ratio = [(w[0], f"1:{w[5] / w[4]:.1f}") for w in PW if w[5] / w[4] > 6.0 + 0.05]
ck.check("E.text_ratio: stroke to height at JLCPCB's preferred 1:6 or bolder", not ratio,
         f"{len(ratio)} strings thinner, e.g. {ratio[:3]}")
# words clear of holes, nuts, knobs, caps, the window and each other (artwork estimates: Arial bold ~0.68 em
# per letter, Georgia italic ~0.55, caps 0.72 em tall above the baseline)
boxes = []
for s, x, y, size, anchor, cls in AW:
    w_ = (0.55 if "serif" in cls else 0.68) * size * len(s)
    x0 = {"middle": x - w_ / 2, "start": x, "end": x - w_}[anchor]
    boxes.append((s, (x0, y - 0.72 * size, x0 + w_, y)))
for s, (bx1, by1, bx2, by2) in boxes:
    for ref, k, x, y, r in items:
        rr = r + (0 if k != "ledbutton" else (panel.ART["ring"] + 0.175 - r if ref != "SW5" else 0))
        d = math.hypot(max(bx1 - x, 0, x - bx2), max(by1 - y, 0, y - by2))
        if d < rr + 0.3:
            ck.check(f"E.word_clear.{s}.{ref}: '{s}' clear of {ref}'s {'knob' if k == 'encoder' else 'nut' if k == 'jack' else 'ring'}",
                     False, f"{d:.2f} mm from its centre, covered to r {rr:.2f} + 0.3")
    if not (bx2 < wn[0] - 0.5 or bx1 > wn[2] + 0.5 or by2 < wn[1] - 0.5 or by1 > wn[3] + 0.5):
        ck.check(f"E.word_window.{s}: '{s}' clear of the window", False, "")
ck.check("E.words_clear: every artwork word clear of the knobs, nuts, caps, rings and the window (0.3 mm)",
         all(math.hypot(max(b[0] - x, 0, x - b[2]), max(b[1] - y, 0, y - b[3]))
             >= r + (panel.ART["ring"] + 0.175 - r if k == "ledbutton" and ref != "SW5" else 0) + 0.3
             for _, b in boxes for ref, k, x, y, r in items), f"{len(boxes)} words")
over = []
for i, (sa, a) in enumerate(boxes):
    for sb, b in boxes[i + 1:]:
        if not (a[2] + 0.3 <= b[0] or b[2] + 0.3 <= a[0] or a[3] + 0.3 <= b[1] or b[3] + 0.3 <= a[1]):
            over.append((sa, sb))
ck.check("E.words_apart: no two artwork words within 0.3 mm of each other", not over, str(over[:4]))
# VERIFY 2026-11-13 (new): the PEC11R's flat washer (d 12.0 +-0.3, supplied) lies on the panel under the nut
under_washer = [(s, ref) for s, (bx1, by1, bx2, by2) in boxes for ref, k, x, y, r in items if k == "encoder"
                and math.hypot(max(bx1 - x, 0, x - bx2), max(by1 - y, 0, y - by2)) < (ENC_WASHER_D + 0.3) / 2 + 0.3]
ck.check("E.words_clear_washer: no artwork word under an encoder's washer (r 6.15) + 0.3", not under_washer,
         f"{under_washer}")
# the outputs' words on the gold band: the approved artwork knocks them out of the copper (dark letters); the
# panel PCB prints them as white silkscreen over a solder-mask opening, which a fab may clip from bare copper.
# VERIFY 2026-11-13: JLCPCB's capabilities page states only "pad to silkscreen 0.15 mm"; JLCPCB's silkscreen blog
# says it removes silkscreen over pads / exposed copper, and Altium's docs note many fabs clip silk to the mask
# opening, not just the pad. Not a stated JLCPCB rule for a large mask opening, but the likely outcome.
cu_words = [w[0] for w in AW if "cu-text" in w[5]]
band = [f for f in panel.copper({ref: (kind, "", *panel.panel_xy(hx, hy)) for kind, ref, _, ox, oy, hx, hy in feats})]
on_band = []
for s, x, y, size, *_ in [(w[0], w[1], w[2], w[3]) for w in PW]:
    for (bx, by, bw_, bh_, _), cuts in band:
        if bx <= x <= bx + bw_ and by <= y - 0.4 * size <= by + bh_:
            on_band.append(s)
ck.check("E.output_words_as_drawn: the PCB's OUT 1 / OUT 2 look like the artwork's (dark letters knocked out of "
         "the gold), not silkscreen inside a mask opening", not on_band,
         f"artwork knocks out {cu_words}; the panel PCB has {on_band} as layer-3 silk on the bare-gold band")
# IN 2 normalled to IN 1: J6's switch lug carries J1's tip, and the panel draws the dotted link
ck.check("E.normal_net: J6 (IN 2) switch lug on IN 1's tip net, J1's lug on GND_F",
         fnet.get("J6", {}).get("2") == fnet.get("J1", {}).get("3") == "IN1_F" and fnet.get("J1", {}).get("2") == "GND_F",
         f"J6.2 {fnet.get('J6', {}).get('2')}, J1.3 {fnet.get('J1', {}).get('3')}, J1.2 {fnet.get('J1', {}).get('2')}")
dots = [it for it in panel.layout({ref: (kind, "", *panel.panel_xy(hx, hy)) for kind, ref, _, ox, oy, hx, hy in feats})
        if it[0] == "dots" and abs(it[1][0][1] - it[1][-1][1]) > 0.5]
(jx1, jy1), (jx6, jy6) = real["J1"], real["J6"]
ok = [d for d in dots if all(abs(px - jx1) < 0.05 and jy1 < py < jy6 for px, py in d[1])]
ck.check("E.normal_dots: a dotted line from IN 1 down to IN 2", len(ok) == 1, f"{len(ok)} vertical dotted lines between them")

# ================================================================ 6. the house frame and the mark
TITLE = (12.0, 7.4, 5.2)          # panel.md: serif italic 5.2, anchor start at x 12.0, baseline 7.4
SUB = (12.0, 6.6, 2.1)            # 2.1, anchor end at x W - 12.0, baseline 6.6
BAND = (9.6, 10.6)                # two dotted lines, x 3 to W - 3
RULE = (118.6, 0.3)               # 0.3 mm line, x 3 to W - 3
MARK_H, MARK_GAP, RULE_LOW = 4.1, 1.6, 118.75
skill = open(os.path.join(REPO, ".claude", "skills", "module-design", "references", "panel.md"), encoding="utf-8").read()
_n = re.search(r"\| side-fx \| (\w+) \| ([^|]+?) \|", skill)
ck.check("F.names: panel name and function line = the skill's table (side-fx -> Moss / Quad effects)",
         _n is not None and panel.ART["title"] == _n.group(1) and panel.ART["subtitle"] == _n.group(2).strip(),
         f"skill {_n.groups() if _n else None}, panel.py ({panel.ART['title']}, {panel.ART['subtitle']})")
A = {w[0]: w for w in AW}
t, s_ = A.get(panel.ART["title"]), A.get(panel.ART["subtitle"])
ck.check("F.art_title: serif 5.2, start at x 12.0, baseline 7.4", t is not None and t[4] == "start"
         and abs(t[1] - TITLE[0]) < 0.01 and abs(t[2] - TITLE[1]) < 0.01 and t[3] == TITLE[2] and "serif" in t[5], str(t))
ck.check("F.art_subtitle: 2.1, end at x W-12, baseline 6.6", s_ is not None and s_[4] == "end"
         and abs(s_[1] - (W - SUB[0])) < 0.01 and abs(s_[2] - SUB[1]) < 0.01 and s_[3] == SUB[2], str(s_))
t_end = TITLE[0] + 0.55 * TITLE[2] * len(panel.ART["title"])
s_start = W - SUB[0] - 0.6 * SUB[2] * len(panel.ART["subtitle"])
ck.check("F.title_fits: the title ends >= 1.5 mm before the function line (panel.md)", s_start - t_end >= 1.5,
         f"title to ~{t_end:.1f}, function line from ~{s_start:.1f}")
silk = groups["silk"]
polys = []
for pl in silk.iter(SVG_NS + "polyline"):
    pts = [tuple(map(float, q.split(","))) for q in pl.get("points").split()]
    polys.append((pl.get("class") or "", float(pl.get("stroke-width") or 0), pts))
for yb in BAND:
    ok = any("dots" in c and abs(p[0][1] - yb) < 0.01 and abs(p[-1][1] - yb) < 0.01 and abs(p[0][0] - 3) < 0.01
             and abs(p[-1][0] - (W - 3)) < 0.01 for c, w_, p in polys)
    ck.check(f"F.art_band.{yb}: dotted line at y {yb}, x 3 .. W-3", ok, "")
rule = [(c, w_, p) for c, w_, p in polys if "dots" not in c and all(abs(q[1] - RULE[0]) < 0.01 for q in p)]
ck.check("F.art_rule: 0.3 rule at y 118.6, x 3 .. W-3", len(rule) == 1 and abs(rule[0][1] - RULE[1]) < 0.001
         and abs(rule[0][2][0][0] - 3) < 0.01 and abs(rule[0][2][-1][0] - (W - 3)) < 0.01, str(len(rule)))
mk = [pth for pth in silk.iter(SVG_NS + "path") if (pth.get("class") or "") == "copper"]
if ck.check("F.art_mark: the gold mushroom mark (one copper path in #silk)", len(mk) == 1, f"{len(mk)}"):
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", mk[0].get("d"))]
    xs, ys = nums[0::2], nums[1::2]
    ck.close("F.art_mark_h: mark 4.1 mm tall", max(ys) - min(ys), MARK_H, 0.05, " mm")
    ck.close("F.art_mark_top: mark top 1.6 under the rule's lower edge", min(ys), RULE_LOW + MARK_GAP, 0.05, " mm")
    ck.close("F.art_mark_centre: mark centred", (min(xs) + max(xs)) / 2, W / 2, 0.05, " mm")
# the other modules' committed artwork: the same frame (title, subtitle, band, rule) everywhere
others = []
for f in sorted(glob.glob(os.path.join(REPO, "*", "hardware", "panel", "*-panel.svg"))):
    if os.path.normpath(f).startswith(os.path.normpath(harness.MODULE) + os.sep):
        continue
    try:
        root = ET.parse(f).getroot()
        ow = float(root.get("viewBox").split()[2])
        texts = [(t.text or "").strip() for t in root.iter(SVG_NS + "text")]
        tt = [t for t in root.iter(SVG_NS + "text") if (t.get("class") or "") == "serif"]
        st = [t for t in root.iter(SVG_NS + "text") if t.get("text-anchor") == "end" and abs(float(t.get("y")) - SUB[1]) < 0.01]
        pls = [[tuple(map(float, q.split(","))) for q in p.get("points").split()] for p in root.iter(SVG_NS + "polyline")]
        pls += [[(float(p.get("x1")), float(p.get("y1"))), (float(p.get("x2")), float(p.get("y2")))]
                for p in root.iter(SVG_NS + "line")]
        narrow = ow < 25.0                   # 4HP: the function line cannot sit at W - 12 (panel.md's 4HP note)
        frame = (tt and abs(float(tt[0].get("x")) - TITLE[0]) < 0.01 and abs(float(tt[0].get("y")) - TITLE[1]) < 0.01
                 and float(tt[0].get("font-size")) == TITLE[2]
                 and (narrow or (st and abs(float(st[0].get("x")) - (ow - SUB[0])) < 0.01
                                 and float(st[0].get("font-size")) == SUB[2]))
                 and all(any(abs(p[0][1] - yb) < 0.01 and abs(p[-1][1] - yb) < 0.01 and abs(p[0][0] - 3) < 0.01
                             and abs(p[-1][0] - (ow - 3)) < 0.01 for p in pls) for yb in BAND + (RULE[0],)))
        others.append((os.path.relpath(f, REPO).split(os.sep)[0], bool(frame)))
    except Exception as e:                   # noqa: BLE001  (another module's file: report, don't crash)
        others.append((os.path.relpath(f, REPO).split(os.sep)[0], f"unreadable: {e}"))
bad = [o for o in others if o[1] is not True]
ck.check("F.same_frame_as_others: the other modules' artwork has the same title / subtitle / band / rule spots",
         bool(others) and not bad, f"{len(others) - len(bad)} of {len(others)} match; differ: {bad}")
# the routed panel PCB's frame
P = {w[0]: w for w in PW}
pt = next((p for h, p in PANEL_DOC["recs"] if h["type"] == "STRING" and p["text"] == panel.ART["title"]), None)
ck.check("F.pcb_title: title STRING starts at x 12.0, baseline 7.4, size 5.2", pt is not None
         and abs(pt["x"] * MIL - TITLE[0]) < 0.02 and abs(H - pt["y"] * MIL - TITLE[1]) < 0.02
         and abs(pt["fontSize"] * MIL / 0.9 - TITLE[2]) < 0.02, f"{(pt['x'] * MIL, H - pt['y'] * MIL) if pt else None}")
ps = P.get(panel.ART["subtitle"])
ck.check("F.pcb_subtitle: ends at x W-12 (estimated width), baseline 6.6, size 2.1", ps is not None
         and abs(ps[1] + 0.62 * ps[3] * len(ps[0]) / 2 - (W - SUB[0])) < 0.05 and abs(ps[2] - SUB[1]) < 0.02
         and abs(ps[3] - SUB[2]) < 0.02, str(ps and ps[:4]))
ca = harness.load("copper_audit")
silk_polys = []
for h, p in PANEL_DOC["recs"]:
    if h["type"] == "POLY" and p.get("layerId") == 3 and "ARC" not in p["path"]:
        pts = ca.flatten_path(p["path"], MIL)
        silk_polys.append((p["width"] * MIL, [(q[0], H - q[1]) for q in pts]))
for yb in BAND:
    dashes = [pts for w_, pts in silk_polys if all(abs(q[1] - yb) < 0.01 for q in pts)]
    xs = [q[0] for pts in dashes for q in pts]
    ck.check(f"F.pcb_band.{yb}: dashes along y {yb} from x 3 to W-3", len(dashes) > 20 and xs
             and abs(min(xs) - 3) < 0.1 and abs(max(xs) - (W - 3)) < 0.1, f"{len(dashes)} dashes")
rl = [(w_, pts) for w_, pts in silk_polys if all(abs(q[1] - RULE[0]) < 0.01 for q in pts) and abs(w_ - RULE[1]) < 0.01]
ck.check("F.pcb_rule: one 0.3 line at y 118.6 from x 3 to W-3", len(rl) == 1
         and abs(min(q[0] for q in rl[0][1]) - 3) < 0.01 and abs(max(q[0] for q in rl[0][1]) - (W - 3)) < 0.01,
         f"{len(rl)}")
# the mark: 7 polygons, each a closed FILL on top copper (1) and the same on the top mask (5), = mushroom.py's
want_rings = [[(x, H - y) for x, y in ring] for ring in mushroom.polygons(W)]
fills = {1: [], 5: []}
for h, p in PANEL_DOC["recs"]:
    if h["type"] == "FILL" and p["layerId"] in (1, 5):
        path = p["path"][0] if isinstance(p["path"][0], list) else p["path"]
        if any(v == "ARC" for v in path):
            continue                          # the copper blocks' cutouts use arcs; the mark is straight lines
        pts = [(path[0] * MIL, path[1] * MIL)] + [(path[i + 1] * MIL, path[i + 2] * MIL)
                                                 for i in range(2, len(path) - 2, 3) if path[i] == "L"]
        if max(q[1] for q in pts) < H - RULE_LOW:
            fills[p["layerId"]].append(pts)


def same_ring(a, b):
    return len(a) == len(b) and all(math.hypot(p[0] - q[0], p[1] - q[1]) < 0.01 for p, q in zip(a, b))


for layer in (1, 5):
    got = fills[layer]
    matched = sum(1 for wr in want_rings if any(same_ring(wr, g) for g in got))
    ck.check(f"F.mark_layer{layer}: the mushroom's {len(want_rings)} polygons on layer {layer}, = mushroom.py's",
             len(got) == len(want_rings) == 7 and matched == 7, f"{len(got)} fills under the rule, {matched} match")
    ck.check(f"F.mark_closed{layer}: every mark FILL ends on its first point (EasyEDA drops open ones)",
             all(math.hypot(g[0][0] - g[-1][0], g[0][1] - g[-1][1]) < 1e-3 for g in got), "")
allm = [q for g in fills[1] for q in g]
if allm:
    ck.close("F.mark_top: routed mark top 1.6 under the rule's lower edge", H - max(q[1] for q in allm), RULE_LOW + MARK_GAP, 0.05, " mm")
    ck.close("F.mark_centre: routed mark centred", (min(q[0] for q in allm) + max(q[0] for q in allm)) / 2, W / 2, 0.05, " mm")
# content between the band and the rule; screw heads clear of the title and subtitle
for ref, k, x, y, r in items:
    rr = panel.ART["ring"] + 0.175 if k == "ledbutton" and ref != "SW5" else r
    ck.check(f"F.content.{ref}: between the band (10.6) and the rule (118.6) with its knob / nut / ring",
             y - rr >= BAND[1] and y + rr <= RULE[0], f"y {y - rr:.2f} .. {y + rr:.2f}")
ck.check("F.content.window: window between the band and the rule", wn[1] >= BAND[1] and wn[3] <= RULE[0],
         f"y {wn[1]:.2f} .. {wn[3]:.2f}")
for s, (bx1, by1, bx2, by2) in boxes:
    if s in (panel.ART["title"], panel.ART["subtitle"]):
        continue
    if by1 < BAND[1] or by2 > RULE[0]:
        ck.check(f"F.content.{s}: word between the band and the rule", False, f"y {by1:.2f} .. {by2:.2f}")
for mx, my in want_m:
    if my > 10:
        continue
    head = SCREW_HEAD_D / 2
    ok = (mx + head <= TITLE[0] - 1.0) if mx < W / 2 else (mx - head >= W - SUB[0] + 1.0)
    ck.check(f"F.screw_vs_title.{mx}: screw head >= 1 mm clear of the title / subtitle", ok,
             f"head {mx - head:.2f} .. {mx + head:.2f}; title from {TITLE[0]}, subtitle to {W - SUB[0]}")

# ================================================================ 7. depth behind the panel
stack = [("panel gap (Thonkiconn body)", JACK_BODY_H), ("faceplate", PCB_T), ("mated headers", MATED),
         ("main board", PCB_T), ("breakout on its sockets (8.5 female + 2.5 male plastic)", MATED),
         ("breakout PCB", PCB_T), ("Seed on the breakout (sockets, assumed 8.5 + 2.5)", MATED), ("Seed PCB", PCB_T),
         ("the Seed's tallest part", SEED_TALLEST)]
depth = sum(v for _, v in stack)
print("INFO  depth behind the panel: " + " + ".join(f"{v:g} ({k})" for k, v in stack) + f" = {depth:.1f} mm")
ck.check(f"G.depth: <= {CASE_DEPTH:g} mm (a powered case; assumption, see the constants)", depth <= CASE_DEPTH,
         f"{depth:.1f} mm")
print(f"INFO  {'deeper' if depth > SKIFF_DEPTH else 'within'} a {SKIFF_DEPTH:g} mm skiff ({depth:.1f} mm); "
      "the breakout's power cable plug adds to this where it leaves the breakout")
on_fb_top = sorted(r for r, pl in FB.parts.items() if not pl["bottom"] and r[0] not in "JSE")
on_mb_bot = sorted(r for r, pl in MB.parts.items() if pl["bottom"] and not re.match(r"^H\d+$", r))
ck.check("G.gap_sides: only sockets on the main board's front (nothing else faces the faceplate)", not on_mb_bot,
         f"main bottom {on_mb_bot}")

ck.done()
