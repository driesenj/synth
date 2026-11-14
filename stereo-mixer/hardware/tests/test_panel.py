"""Panel and mechanics of the stereo mixer (Mycelium, 28HP).

What it checks, from the parts' datasheet geometry and the Eurorack spec,
not from the numbers the generators happen to produce:

  1. Where the parts really are: the shaft / barrel / cap centre of every
     panel part, worked out from the pads of the ROUTED faceplate
     (StereoMixer-routed.epro2) and the real parts' drawings (Thonkiconn
     barrel 6.48 mm from the sleeve pin towards the tip; Alpha 9 mm shaft
     7.5 mm from the pin row, on the line of the two mounting lugs; LED
     button cap on the centre of its four switch pins), against every
     representation of the panel holes: circuit.PANEL_XY (the intent), the
     hole CSV, the drill SVG, the artwork SVG and the panel PCB in the
     routed master. The offsets circuit.py states (barrel 0.78 mm below the
     WQP518MA origin, shaft 4.0 mm beyond the pot footprint origin) are
     checked against the footprints and the datasheet geometry.
  2. Hole sizes against the parts (jack thread, pot bushing, button cap).
  3. Eurorack mechanics (Doepfer A-100): 128.5 mm, 28HP width, mounting
     slots, the 108 mm boards between the rails, nothing in the rail zone.
  4. Ergonomics: knobs (the BOM's sizes) against the pitch, jack nuts,
     button caps, the master section.
  5. Depth behind the panel.
  6. Labels: every word on the artwork and the panel PCB names the part
     under it (by the routed faceplate's nets), PAN L / R the right way
     round, R-follows-L, the row words, the panel frame of the skill.

Run from stereo-mixer/hardware/tests:  python test_panel.py
Only reads: imports the tools' pure functions, opens the exports as zips.
"""
import csv
import math
import os
import re
import xml.etree.ElementTree as ET

import harness

ck = harness.Checks("panel")
circuit = harness.load("circuit")
panel = harness.load("panel")           # pure functions only (features, layout, bands, check); main() not called
ca = harness.load("copper_audit")
panel_pcb = harness.load("panel_pcb")    # EasyEDA's measured font: INK_*, ink_width (no board built)
MIL = ca.MIL

# ---------------------------------------------------------------- datasheet / spec constants
# Thonkiconn PJ398SM (QingPu WQP-PJ398SM). KiCad footprint
# Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical (descr links qingpu-electronics.com WQP-PJ398SM-362):
# S (0, 0), TN (0, 3.1), T (0, 11.4), barrel circle at (0, 6.48), r 1.8 (fab). typ.
JACK_S_TN, JACK_S_T, JACK_S_BARREL = 3.1, 11.4, 6.48
JACK_THREAD = 6.0          # M6 x 0.5 bushing (Thonk / QingPu drawing; not re-read here: unconfirmed, nominal)
JACK_NUT_AF = 8.0          # hex nut across flats (house parts.md "about 8 mm"; unconfirmed), corners = AF / cos 30
JACK_NUT_AC = JACK_NUT_AF / math.cos(math.radians(30))      # 9.24 mm worst case (the nut's corners)
JACK_BODY_H = 9.5          # PCB to panel with Thonkiconn + Alpha 9 mm (house parts.md "9.5-10 mm"; unconfirmed)
PLUG_BODY_D = 9.0          # a common moulded 3.5 mm patch-cable plug body (Tiptop / Doepfer cables ~6-9 mm), max
# Alpha 9 mm vertical pot. KiCad Potentiometer_Alpha_RD901F-40-00D_Single_Vertical / RD902F-40-00D_Dual
# (descr links taiwanalpha.com.tw products id=113): pins 2.5 mm apart in a row, shaft 7.5 mm from the row,
# mounting lugs on the shaft line at +-4.8 (single) / +-4.75 (dual), bushing circle d 7.0 (M7 x 0.75). typ.
POT_ROW_TO_SHAFT, POT_LUG_HALF, POT2_LUG_HALF, POT_PIN_PITCH = 7.5, 4.8, 4.75, 2.5
POT_BUSHING = 7.0
# Thonk low-profile LED button (Thonk LowProfileButton.pdf as quoted in module-design parts.md: 7.5 mm square
# body, 5.5 mm round cap; switch pins on a 5.08 mm square round the cap). Not re-read here: unconfirmed.
BTN_CAP_D, BTN_BODY = 5.5, 7.5
# Position tolerance between a panel hole and the part in it (panel PCB drill +-0.1, faceplate drill +-0.1,
# a part's own play in its holes ~0.1): worst case sum. A hole must clear the part by this per side.
POS_TOL = 0.3
# Eurorack, Doepfer A-100 (doepfer.de/a100_man/a100m_e.htm): 128.5 mm high; HP 5.08 mm; 28HP = 141.90 mm;
# hole spacing a multiple of 5.08; M3 screws (DIN 7985, head d 5.6 max).
# Hole centres 3 mm from top / bottom, 7.5 mm from the left edge (Doepfer drawing; SDIY wiki "Eurorack
# panel components": 7.45 mm); rail holes 122.5 mm apart.
# SDIY wiki: max PCB height 108-110 mm; clear space between rails 112.2-115.1 mm; keep panel components
# 10 mm from the top / bottom edges; stacked PCB header height 11 mm (2.5 mm male plastic + 8.5 socket).
PANEL_H, HP_MM, W28 = 128.5, 5.08, 141.90
MOUNT_FROM_EDGE_Y, MOUNT_FROM_LEFT = 3.0, 7.5
RAIL_PITCH = 122.5
PCB_MAX_H = 108.0          # the strict end of 108-110
RAIL_CLEAR_MIN = 112.2     # the tightest rails
RAIL_ZONE = 10.0           # panel parts at least this far from the top / bottom edges
SCREW_HEAD_D = 5.6         # DIN 7985 M3, max
STACK_GAP = 8.5 + 2.5      # female socket body + male header plastic, mated
EUROSYNTH_DEPTH = 60.0     # EuroSynth mechanical spec: nominal module depth, behind the panel
# depth stack behind the panel (mm), typical parts
PCB_T = 1.6
TALLEST_MAIN = {           # above the main board's top (rear) side
    "10 uF electrolytic 5 x 11 mm, standing": 11.0 + 0.5,
    "1/4 W resistor standing (6.3 mm body + bend)": 6.3 + 2.5 + 1.0,
    "DIP-14 in a socket": 4.2 + 3.3,
    "2x8 shrouded box header": 9.0,
    "box header + IDC plug + ribbon bend": 9.0 + 3.0 + 5.0,
}

# ---------------------------------------------------------------- what the panel should be
W, H = circuit.PANEL_W, circuit.PANEL_H
BW, BH = circuit.BOARD_W, circuit.BOARD_H
X0, Y0 = (W - BW) / 2, (H - BH) / 2
KNOB_D = {"small": 10.0, "mid": 12.0}      # docs/bom.md: "about 10 mm across" x 24, "about 12 mm" MASTER
KNOB_D_MAX = {"small": 11.0, "mid": 12.0}  # docs/design.md: "up to about 11 mm" in the channel strips

docs = harness.read_export()
fps = ca.footprints_of(docs)
boards = ca.boards_of(docs, fps)
FB = next(b for t, b in boards.items() if "Faceplate" in t)
MB = next(b for t, b in boards.items() if "Main" in t)
PANEL_DOC = next(d for t, d in boards.items() if "Panel" in t)


def front(x, y):
    """Routed faceplate (EasyEDA top-layer view = rear of the stack, y up) -> panel mm from the top-left."""
    return (BW - x) + X0, H - Y0 - y


def pcb_panel(x, y):
    """Panel PCB frame (front, y up, origin bottom-left) -> panel mm from the top-left."""
    return x, H - y


def kind_of(ref):
    return "jack" if ref.startswith("J") else "pot" if ref.startswith("RV") else "ledbutton"


# ================================================================ 1. where the parts are
def centre(pl):
    """Mechanical centre of a placed panel part, from its pads and the datasheet geometry (board frame)."""
    p = pl["pads"]
    if pl["ref"].startswith("J"):
        s, t = p["1"], p["3"]
        d = math.hypot(t.x - s.x, t.y - s.y)
        return s.x + (t.x - s.x) / d * JACK_S_BARREL, s.y + (t.y - s.y) / d * JACK_S_BARREL
    if pl["ref"].startswith("RV"):
        a, b = (p["4"], p["5"]) if "7" not in p else (p["7"], p["8"])
        return (a.x + b.x) / 2, (a.y + b.y) / 2
    return sum(p[n].x for n in "1234") / 4, sum(p[n].y for n in "1234") / 4


PANEL_REFS = sorted(circuit.PANEL_XY)
real = {}
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if not ck.check(f"routed faceplate has {ref}", pl is not None and pl["bottom"],
                    "on the bottom (panel) side" if pl else "missing"):
        continue
    real[ref] = front(*centre(pl))

# the footprints against the datasheets (pad spacing), so centre() is computed from the real geometry
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    p = pl["pads"]
    if ref.startswith("J"):
        st = math.hypot(p["3"].x - p["1"].x, p["3"].y - p["1"].y)
        stn = math.hypot(p["2"].x - p["1"].x, p["2"].y - p["1"].y)
        ok = abs(st - JACK_S_T) < 0.02 and abs(stn - JACK_S_TN) < 0.02
        ck.check(f"{ref} footprint pin spacing = Thonkiconn", ok,
                 f"expected S-T {JACK_S_T}, S-TN {JACK_S_TN}; got {st:.3f}, {stn:.3f}")
        # circuit.JACK_BARREL: barrel 0.78 mm from the footprint origin (towards the tip)
        bx, by = centre(pl)
        off = math.hypot(bx - pl["x"], by - pl["y"])
        ck.close(f"{ref} barrel offset from the WQP518MA origin", off, abs(circuit.JACK_BARREL), 0.02, " mm")
    elif ref.startswith("RV"):
        dual = "7" in p
        a, b = (p["7"], p["8"]) if dual else (p["4"], p["5"])
        half = math.hypot(a.x - b.x, a.y - b.y) / 2
        sx, sy = (a.x + b.x) / 2, (a.y + b.y) / 2
        row = math.hypot(p["2"].x - sx, p["2"].y - sy)      # pin 2 is the middle of the first pin row
        pitch = math.hypot(p["3"].x - p["1"].x, p["3"].y - p["1"].y) / 2
        ok = (abs(half - (POT2_LUG_HALF if dual else POT_LUG_HALF)) < 0.02 and abs(row - POT_ROW_TO_SHAFT) < 0.02
              and abs(pitch - POT_PIN_PITCH) < 0.02)
        ck.check(f"{ref} footprint = Alpha RD90{'2' if dual else '1'}F", ok,
                 f"expected lugs +-{POT2_LUG_HALF if dual else POT_LUG_HALF}, row->shaft {POT_ROW_TO_SHAFT}, "
                 f"pitch {POT_PIN_PITCH}; got +-{half:.3f}, {row:.3f}, {pitch:.3f}")
        off = math.hypot(sx - pl["x"], sy - pl["y"])
        ck.close(f"{ref} shaft offset from the footprint origin", off, circuit.POT_SHAFT, 0.02, " mm")
        # the shaft must be on the side away from the pins (the pin row 7.5 mm one way, not the other)
        ck.check(f"{ref} shaft on the far side of the lugs from the pins",
                 math.hypot(p["2"].x - pl["x"], p["2"].y - pl["y"]) < row, "")

# the pad model (EasyEDA's bottom-side mirror) is right if the routed tracks end on the pads it puts there:
# every signal pad of a panel part has a track end or a via inside it
ends = [(t["a"], t["layer"]) for t in FB.tracks] + [(t["b"], t["layer"]) for t in FB.tracks]
missed = []
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    for num, pad in pl["pads"].items():
        if pad.net in (None, "", "GND_F"):
            continue                     # ground pads may sit in the pour without a track
        if not any(pad.d_point(e) < 0.01 for e, _ in ends):
            missed.append(f"{ref}.{num}")
ck.check("routed tracks end on the modelled panel-part pads (frame and mirror right)", not missed,
         f"{len(missed)} pads without a track end: {missed[:8]}")

# intent: PANEL_XY is where the user wants the holes; the routed parts must be there
for ref in PANEL_REFS:
    if ref in real:
        want = circuit.PANEL_XY[ref]
        d = math.hypot(real[ref][0] - want[0], real[ref][1] - want[1])
        ck.check(f"{ref} routed centre at PANEL_XY", d < 0.05,
                 f"expected {want}, got ({real[ref][0]:.3f}, {real[ref][1]:.3f}), off {d:.3f} mm")


def match(name, got, tol=0.05):
    """got: [(x, y, d)] panel holes (panel frame). Every real part has exactly one hole on its centre of the
    right size, and there is no other round hole."""
    used = set()
    for ref in PANEL_REFS:
        if ref not in real:
            continue
        x, y = real[ref]
        near = [(math.hypot(hx - x, hy - y), i, hd) for i, (hx, hy, hd) in enumerate(got)]
        dist, i, hd = min(near)
        used.add(i)
        want_d = panel.HOLE[kind_of(ref)]
        ck.check(f"{name}: hole over {ref}", dist <= tol and abs(hd - want_d) < 0.02,
                 f"expected d {want_d} at ({x:.2f}, {y:.2f}); nearest d {hd:.2f}, {dist:.3f} mm off")
    extra = [got[i] for i in range(len(got)) if i not in used]
    ck.check(f"{name}: no extra round holes", not extra and len(got) == len(real),
             f"expected {len(real)}, got {len(got)}; extra {extra[:4]}")


# hole CSV
rows = list(csv.DictReader(open(os.path.join(harness.PANEL, "stereo-mixer-panel-holes.csv"), encoding="utf-8")))
csv_holes = [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), float(r["hole_mm"]))
             for r in rows if r["kind"] != "mount"]
match("CSV", csv_holes, tol=0.01)
csv_labels = {r["ref"]: r["label"] for r in rows if r["ref"]}
csv_mounts = [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), r["hole_mm"]) for r in rows
              if r["kind"] == "mount"]

SVG_NS = "{http://www.w3.org/2000/svg}"


def svg_tree(name):
    return ET.parse(os.path.join(harness.PANEL, name)).getroot()


drill = svg_tree("stereo-mixer-panel-drill.svg")
drill_holes = [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in drill.iter(SVG_NS + "circle")]
match("drill SVG", drill_holes, tol=0.01)
art = svg_tree("stereo-mixer-panel.svg")
groups = {g.get("id"): g for g in art.iter(SVG_NS + "g")}
art_holes = [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in groups["holes"].iter(SVG_NS + "circle")]
match("artwork SVG", art_holes, tol=0.01)

# panel PCB in the routed master: round holes are layer-12 FILL circles, slots are layer-12 FILL paths
pp_holes, pp_slots, pp_outline = [], [], None
for h, p in PANEL_DOC["recs"]:
    if h["type"] == "FILL" and p["layerId"] == 12:
        if p["path"][0][0] == "CIRCLE":
            _, x, y, r = p["path"][0]
            pp_holes.append((*pcb_panel(x * MIL, y * MIL), 2 * r * MIL))
        else:
            pts = ca.flatten_path(p["path"][0] if isinstance(p["path"][0], list) else p["path"], MIL)
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            pp_slots.append(((min(xs) + max(xs)) / 2, H - (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)))
    elif h["type"] == "POLY" and p.get("polyType") == "BOARD_OUTLINE":
        pp_outline = p["path"]
match("panel PCB (routed master)", pp_holes, tol=0.05)

# ================================================================ 2. hole sizes vs the parts
HOLE = panel.HOLE
ck.check("jack hole clears the M6 thread", HOLE["jack"] >= JACK_THREAD + 2 * 0.1,
         f"hole {HOLE['jack']} vs thread {JACK_THREAD} + 0.2")
ck.check("jack nut covers the jack hole", JACK_NUT_AF >= HOLE["jack"] + 1.0,
         f"nut {JACK_NUT_AF} AF vs hole {HOLE['jack']} + 1.0 bearing")
ck.check("pot hole clears the M7 bushing", HOLE["pot"] >= POT_BUSHING + 2 * 0.1,
         f"hole {HOLE['pot']} vs bushing {POT_BUSHING} + 0.2")
ck.check("pot hole is not loose on the M7 bushing (<= +0.6)", HOLE["pot"] <= POT_BUSHING + 0.6,
         f"hole {HOLE['pot']}")
ck.check("button cap passes the hole with the position tolerance",
         HOLE["ledbutton"] >= BTN_CAP_D + 2 * POS_TOL,
         f"hole {HOLE['ledbutton']} vs cap {BTN_CAP_D} + 2 x {POS_TOL}")
ck.check("button body (7.5 square) stays behind the panel", HOLE["ledbutton"] < BTN_BODY,
         f"hole {HOLE['ledbutton']} vs body {BTN_BODY}")
ck.check("button ring is outside the hole (silk >= 0.3 mm off the hole edge)",
         panel.ART["ring"] - 0.15 >= HOLE["ledbutton"] / 2 + 0.3,
         f"ring r {panel.ART['ring']} (0.3 line) vs hole r {HOLE['ledbutton'] / 2}")
ck.close("button ring at cap + 1.6 (house style)", panel.ART["ring"], BTN_CAP_D / 2 + 1.6, 0.01, " mm")
for size in ("small", "mid"):
    ck.check(f"{size} pot scale arc (0.3 line) clears its knob ({KNOB_D_MAX[size]} mm)",
             panel.ART["scale"][size] - 0.15 >= KNOB_D_MAX[size] / 2,
             f"scale r {panel.ART['scale'][size]} vs knob r {KNOB_D_MAX[size] / 2}")
# the routed footprint's own body (the plastic housing) behind the hole: the hole must be inside the housing
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    x1, y1, x2, y2 = pl["body"]
    (cx, cy) = centre(pl)
    r = HOLE[kind_of(ref)] / 2
    ok = x1 <= cx - r and cx + r <= x2 and y1 <= cy - r and cy + r <= y2
    ck.check(f"{ref} hole inside the part's housing", ok,
             f"hole ({cx:.2f}, {cy:.2f}) r {r}; housing {tuple(round(v, 2) for v in pl['body'])}")

# ================================================================ 3. Eurorack mechanics
ck.close("panel height = 128.5 (Doepfer)", H, PANEL_H, 0.001, " mm")
ck.check("panel width = 28HP (Doepfer 141.90, i.e. 28 x 5.08 - 0.34)", abs(W - W28) < 0.01 and circuit.HP == 28,
         f"expected {W28}, got {W} ({28 * HP_MM:.2f} nominal, {28 * HP_MM - W:.2f} under)")
if pp_outline:
    _, x0, y0, ow, oh, *_ = pp_outline
    ck.check("panel PCB outline 141.9 x 128.5 (routed master)", abs(ow * MIL - W) < 0.01 and abs(oh * MIL - H) < 0.01,
             f"got {ow * MIL:.3f} x {oh * MIL:.3f}")
else:
    ck.check("panel PCB outline present", False, "no BOARD_OUTLINE")
want_mounts = sorted((x, y) for x in (MOUNT_FROM_LEFT, MOUNT_FROM_LEFT + (circuit.HP - 3) * HP_MM)
                     for y in (MOUNT_FROM_EDGE_Y, PANEL_H - MOUNT_FROM_EDGE_Y))
for name, got in (("CSV", [(x, y) for x, y, _ in csv_mounts]),
                  ("panel PCB", [(x, y) for x, y, w_, h_ in pp_slots])):
    got = sorted(got)
    ok = len(got) == 4 and all(math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02 for a, b in zip(got, want_mounts))
    ck.check(f"{name}: mounting slots at x 7.5 / 7.5 + 25 x 5.08, y 3 / 125.5", ok, f"expected {want_mounts}, got {got}")
# the slots actually on the panel PCB (not the expectation built above): HP spacing, rail pitch, edge margin
act = sorted((x, y) for x, y, w_, h_ in pp_slots)
if ck.check("panel PCB has four mounting slots", len(act) == 4, f"{len(act)}"):
    dx = act[2][0] - act[0][0]
    ck.check("mounting slot spacing (panel PCB) is a multiple of 5.08", abs(dx / HP_MM - round(dx / HP_MM)) < 0.004,
             f"{dx:.3f} mm = {dx / HP_MM:.3f} HP")
    ck.close("vertical slot spacing (panel PCB) = rail pitch", act[1][1] - act[0][1], RAIL_PITCH, 0.02, " mm")
    ck.check("right slot inside the panel with >= 5 mm to the right edge (panel PCB)", W - act[2][0] >= 5.0,
             f"{W - act[2][0]:.2f} mm")
for x, y, sw, sh in pp_slots:
    ck.check(f"panel PCB slot at ({x:.1f}, {y:.1f}) is 5.5 x 3.2, horizontal", abs(sw - 5.5) < 0.02 and abs(sh - 3.2) < 0.02,
             f"got {sw:.2f} x {sh:.2f}")
ck.check("screw head (DIN 7985 d 5.6) covers the slot's 3.2 width", SCREW_HEAD_D > panel.SLOT_H + 1.0,
         f"head {SCREW_HEAD_D}, slot {panel.SLOT_W} x {panel.SLOT_H}")
# boards between the rails
for b in (FB, MB):
    x0, y0, x1, y1 = b.outline
    ck.check(f"{b.title}: {BW} x {BH} board", abs(x1 - x0 - BW) < 0.01 and abs(y1 - y0 - BH) < 0.01,
             f"got {x1 - x0:.2f} x {y1 - y0:.2f}")
ck.check("board height <= 108 mm (max PCB 108-110)", BH <= PCB_MAX_H, f"{BH}")
ck.check("board edge >= 1 mm inside the tightest rails (112.2 clear)", (RAIL_CLEAR_MIN - BH) / 2 >= 1.0,
         f"{(RAIL_CLEAR_MIN - BH) / 2:.2f} mm each side")
# where the boards really sit behind the panel: the offset each routed panel part implies between its board
# position and its hole (PANEL_XY), which must be one offset for all parts and centre the board
offs = []
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    bx, by = centre(pl)
    px, py = circuit.PANEL_XY[ref]
    offs.append((px - (BW - bx), H - py - by))
ox = sum(o[0] for o in offs) / len(offs)
oy = sum(o[1] for o in offs) / len(offs)
spread = max(math.hypot(o[0] - ox, o[1] - oy) for o in offs)
ck.check("boards centred on the panel (offset implied by the routed panel parts)",
         spread < 0.05 and abs(ox - (W - BW) / 2) < 0.05 and abs(oy - (H - BH) / 2) < 0.05 and ox >= 0.5,
         f"expected ({(W - BW) / 2:.2f}, {(H - BH) / 2:.2f}); got ({ox:.3f}, {oy:.3f}), spread {spread:.3f} mm")
for b in (FB, MB):
    worst = None
    for ref, pl in b.parts.items():
        x1, y1, x2, y2 = pl["body"]
        pads = pl["pads"].values()
        lo_y = min([y1] + [p.y - p.r for p in pads])
        hi_y = max([y2] + [p.y + p.r for p in pads])
        lo_x = min([x1] + [p.x - p.r for p in pads])
        hi_x = max([x2] + [p.x + p.r for p in pads])
        m = min(lo_y, BH - hi_y, lo_x, BW - hi_x)
        if worst is None or m < worst[0]:
            worst = (m, ref)
    ck.check(f"{b.title}: every part body / pad on the board", worst[0] >= 0, f"tightest {worst[1]}: {worst[0]:.2f} mm")
# panel parts 10 mm from the top / bottom edges (rails)
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    x1, y1, x2, y2 = pl["body"]
    top, bot = H - Y0 - y2, H - Y0 - y1           # panel y of the housing's ends
    ck.check(f"{ref} housing clear of the rails (>= {RAIL_ZONE} mm from the edges)",
             top >= RAIL_ZONE and H - bot >= RAIL_ZONE, f"panel y {top:.2f} .. {bot:.2f}")
# mounting holes of the two boards, the same everywhere
fh = sorted((round(x, 2), round(y, 2)) for x, y, d in FB.holes)
mh = sorted((round(x, 2), round(y, 2)) for x, y, d in MB.holes)
want_h = sorted((round(BW - x, 2), round(y, 2)) for x, y in circuit.HOLES_FRONT)   # rear frame
ck.check("faceplate and main board mounting holes coincide and = circuit.HOLES_FRONT", fh == mh == want_h,
         f"want {want_h}, faceplate {fh}, main {mh}")
ck.check("board mounting holes are 3.2 mm", all(abs(d - 3.2) < 0.02 for *_, d in FB.holes + MB.holes),
         str(sorted({round(d, 2) for *_, d in FB.holes + MB.holes})))
# a standoff / screw head at a board hole must not sit on a panel part (front view, panel frame)
for hx, hy in circuit.HOLES_FRONT:
    px, py = hx + X0, H - Y0 - hy
    for ref in PANEL_REFS:
        pl = FB.parts[ref]
        x1, y1, x2, y2 = pl["body"]
        fx1, fx2 = BW - x2 + X0, BW - x1 + X0
        fy1, fy2 = H - Y0 - y2, H - Y0 - y1
        dxx = max(fx1 - px, 0, px - fx2)
        dyy = max(fy1 - py, 0, py - fy2)
        if math.hypot(dxx, dyy) < 3.0:
            ck.check(f"standoff at panel ({px:.2f}, {py:.2f}) clear of {ref}", False,
                     f"{math.hypot(dxx, dyy):.2f} mm < 3.0")

# ================================================================ 4. ergonomics
pos = {ref: (kind_of(ref), "", *real[ref]) for ref in real}
knob_r = {ref: KNOB_D_MAX[panel.KNOB_SIZE[ref]] / 2 for ref in real if ref.startswith("RV")}
items = []
for ref in real:
    k = kind_of(ref)
    r = knob_r[ref] if k == "pot" else JACK_NUT_AC / 2 if k == "jack" else BTN_CAP_D / 2
    items.append((ref, k, *real[ref], r))
min_gap = {("pot", "pot"): 2.5, ("jack", "jack"): 2.0, ("ledbutton", "pot"): 3.0, ("jack", "pot"): 2.0,
           ("jack", "ledbutton"): 2.0, ("ledbutton", "ledbutton"): 3.0}
worst = {}
for i, (a, ka, xa, ya, ra) in enumerate(items):
    for b, kb, xb, yb, rb in items[i + 1:]:
        g = math.hypot(xa - xb, ya - yb) - ra - rb
        key = tuple(sorted((ka, kb)))
        if key not in worst or g < worst[key][0]:
            worst[key] = (g, a, b)
for key, (g, a, b) in sorted(worst.items()):
    ck.check(f"edge gap {key[0]}-{key[1]} >= {min_gap[key]} mm (11 mm knobs, nut corners {JACK_NUT_AC:.2f})",
             g >= min_gap[key] - 0.005, f"tightest {a}-{b}: {g:.2f} mm")
# a plugged cable's moulded plug body next to a knob or another plug
for ref, k, x, y, r in items:
    if k != "jack":
        continue
    for o, ko, xo, yo, ro in items:
        if o == ref or ko == "ledbutton":
            continue
        d = math.hypot(x - xo, y - yo)
        need = PLUG_BODY_D / 2 + (PLUG_BODY_D / 2 if ko == "jack" else ro) + (0.5 if ko == "jack" else 1.5)
        if d < need:
            ck.check(f"plug in {ref} clear of {o}", False, f"centres {d:.2f} mm, need {need:.2f}")
ck.check("channel column pitch 13.5 leaves >= 2.5 mm between 11 mm knobs",
         circuit.CH_X[1] - circuit.CH_X[0] - KNOB_D_MAX["small"] >= 2.5,
         f"pitch {circuit.CH_X[1] - circuit.CH_X[0]}, gap {circuit.CH_X[1] - circuit.CH_X[0] - KNOB_D_MAX['small']:.2f}")
rows_y = sorted(circuit.ROW.values())
knob_rows = sorted(circuit.ROW[k] for k in ("send", "pan", "level"))
row_gap = min(b - a for a, b in zip(knob_rows, knob_rows[1:]))
ck.check("knob rows leave room for the fingers (>= 4 mm between 11 mm knobs)", row_gap - KNOB_D_MAX["small"] >= 4.0,
         f"tightest row pitch {row_gap} - {KNOB_D_MAX['small']} = {row_gap - KNOB_D_MAX['small']:.2f}")
# the knobs the BOM actually orders (docs/bom.md), against design.md's limit and the KNOB_D used above
_bom = open(os.path.join(harness.MODULE, "docs", "bom.md"), encoding="utf-8").read()
_kn = [(int(n), float(d)) for n, d in re.findall(r"\| (\d+) \| Knob for a T18 shaft, about ([\d.]+) mm across", _bom)]
_dm = re.search(r"Knobs: up to about ([\d.]+) mm across", open(os.path.join(harness.MODULE, "docs", "design.md"),
                                                               encoding="utf-8").read().replace("\n", " "))
n_pots = sum(1 for r in circuit.PANEL_XY if r.startswith("RV"))
ck.check("BOM knobs: one per pot, channel knobs within design.md's limit, MASTER the bigger one",
         sum(n for n, _ in _kn) == n_pots and _dm is not None and len(_kn) == 2
         and min(d for _, d in _kn) <= float(_dm.group(1)) and max(d for _, d in _kn) <= KNOB_D_MAX["mid"],
         f"BOM {_kn} for {n_pots} pots; design.md limit {_dm.group(1) if _dm else None} mm")
# screw heads vs the panel's own content: title, subtitle, the mark, holes
for mx, my in want_mounts:
    for ref in real:
        x, y = real[ref]
        r = knob_r.get(ref, JACK_NUT_AC / 2 if ref.startswith("J") else BTN_CAP_D / 2)
        if math.hypot(mx - x, my - y) - r - SCREW_HEAD_D / 2 < 1.0:
            ck.check(f"screw head at ({mx}, {my}) clear of {ref}", False, "")

# ================================================================ 5. depth
tallest = max(TALLEST_MAIN.items(), key=lambda kv: kv[1])
depth = JACK_BODY_H + PCB_T + STACK_GAP + PCB_T + tallest[1]
print(f"INFO  depth behind the panel: {JACK_BODY_H} panel gap + {PCB_T} faceplate + {STACK_GAP} mated headers + "
      f"{PCB_T} main board + {tallest[1]:.1f} ({tallest[0]}) = {depth:.1f} mm; panel itself {PCB_T} mm in front")
ck.check(f"depth <= 45 mm (skiff-friendly; EuroSynth nominal {EUROSYNTH_DEPTH})", depth <= 45.0,
         f"{depth:.1f} mm")
# the gap between the boards: only headers on the facing sides (faceplate top, main board bottom)
on_fb_top = sorted(r for r, pl in FB.parts.items() if not pl["bottom"] and not r.startswith("HF"))
on_mb_bot = sorted(r for r, pl in MB.parts.items() if pl["bottom"] and not re.match(r"^H\d+$", r))
ck.check("nothing but headers in the 11 mm gap between the boards", not on_fb_top and not on_mb_bot,
         f"faceplate top {on_fb_top[:6]}, main bottom {on_mb_bot[:6]}")
# standoffs: the mated headers make an 11 mm gap; the BOM and the design must ask for that
bom = open(os.path.join(harness.MODULE, "docs", "bom.md"), encoding="utf-8").read()
design = open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
m = re.search(r"\| (\d+) \| M3 standoff[^|]*?(?:about )?([\d.]+) mm[^|]*\|", bom)
sc = re.search(r"\| (\d+) \| M3 ?[×x] ?[\d.]+ ?mm[^|]*screw", bom)
if ck.check("BOM has the standoff line", m is not None, ""):
    n_st, st_len = int(m.group(1)), float(m.group(2))
    n_scr = int(sc.group(1)) if sc else 0
    ck.close("BOM standoff length = mated header height (8.5 socket + 2.5 male plastic)", st_len, STACK_GAP, 0.3, " mm")
    female = "female-female" in m.group(0)
    # a female-female standoff needs one screw at each end: the BOM's screw line must cover two per standoff
    ck.check("BOM screws: two per female-female standoff", n_scr >= (2 if female else 1) * n_st,
             f"{n_st} standoffs ({'F-F' if female else '?'}), {n_scr} screws; need {2 * n_st if female else n_st}")
    ck.check("BOM standoff count = board mounting holes", n_st == len(circuit.HOLES_FRONT),
             f"{n_st} standoffs, {len(circuit.HOLES_FRONT)} holes")
md = re.search(r"about ([\d.]+) mm with standard\s+sockets", design)
ck.check("design.md standoff gap = 11 mm", md is not None and abs(float(md.group(1)) - STACK_GAP) < 0.3,
         md.group(0) if md else "not found")

# ================================================================ 6. labels
# tip / switch nets on the routed faceplate, by part
fnet = {ref: FB.parts[ref]["nets"] for ref in real}


def jack_word_ok(ref, word):
    tip = fnet[ref].get("3")
    want = {"OUT_L_F": "OUT L", "OUT_R_F": "OUT R", "SEND_F": "SEND", "FXI_F": "FX IN", "DRM_F": "DRUM IN",
            "RT_L_F": "L", "RT_R_F": "R"}
    if tip in want:
        return word == want[tip], tip
    m = re.match(r"^IN(\d)([LR])_F$", tip or "")
    if m:
        return word == m.group(2), tip
    return word == "IN", tip


def knob_word_ok(ref, word):
    n = set(fnet[ref].values())
    if "RW_L_F" in n and "RW_R_F" in n:
        return word == "RETURN", "RW_L/R"
    if "DRW_F" in n:
        return word == "DRUMS", "DRW"
    if "MST_L_F" in n and "MST_R_F" in n:
        return word == "MASTER", "MST_L/R"
    return False, str(sorted(n))


def svg_texts(root):
    out = []
    for t in root.iter(SVG_NS + "text"):
        tr = t.get("transform") or ""
        out.append((t.text.strip(), float(t.get("x")), float(t.get("y")), float(t.get("font-size")),
                    t.get("text-anchor"), "rotate(-90" in tr, t.get("class") or ""))
    return out


def pcb_texts():
    """STRINGs of the routed panel PCB as (text, centre-x / x, baseline y, size, anchor-free, vertical) in the
    panel frame. EasyEDA's measured font (panel_pcb.INK_*, 2026-11-14): the letters stand INK_BOTTOM x fontSize
    above (angle 90: left of) the origin and are ink_width() long; fontSize = 0.9 size. (Until then the origin was
    taken as the baseline and 0.62 size per character as the width.)"""
    out = []
    for h, p in PANEL_DOC["recs"]:
        if h["type"] != "STRING":
            continue
        size, F = p["fontSize"] * MIL / 0.9, p["fontSize"] * MIL
        width = panel_pcb.ink_width(p["text"], size, p["strokeWidth"] * MIL)
        x, y = p["x"] * MIL, p["y"] * MIL
        if p["angle"] % 360 == 0:
            out.append((p["text"], x + width / 2, H - y - panel_pcb.INK_BOTTOM * F, size, "pcb", False, ""))
        else:
            out.append((p["text"], x - panel_pcb.INK_BOTTOM * F, H - (y + width / 2), size, "pcb", True,
                        f"angle {p['angle']}"))
    return out


def label_checks(name, texts):
    words = [t for t in texts if not t[5]]
    # jack words: the word sits ~5.6 mm above a jack (nut + 1.6)
    labelled = {}
    for s, x, y, size, anchor, vert, cls in words:
        for ref in real:
            if not ref.startswith("J"):
                continue
            jx, jy = real[ref]
            if abs(x - jx) < 0.6 and 4.5 < jy - y < 7.0:
                labelled[ref] = s
                ok, tip = jack_word_ok(ref, s)
                ck.check(f"{name}: '{s}' over {ref} names its signal", ok, f"tip net {tip}")
    for ref in real:
        if ref.startswith("J") and not re.match(r"^IN\d_F$", fnet[ref].get("3", "")):
            ck.check(f"{name}: {ref} ({fnet[ref].get('3')}) has its own word", ref in labelled, "")
    # master knob words, under their knob
    for ref in ("RV23", "RV24", "RV25"):
        x, y = real[ref]
        under = [t for t in words if abs(t[1] - x) < 0.6 and 6.0 < t[2] - y < 11.0]
        ok = len(under) == 1 and knob_word_ok(ref, under[0][0])[0]
        ck.check(f"{name}: word under {ref}", ok, f"{[u[0] for u in under]} for {knob_word_ok(ref, '')[1]}")
    # channel numbers over the columns: the column's parts carry that channel's nets
    for k in range(1, 9):
        x = circuit.CH_X[k - 1]
        num = [t for t in words if t[0] == str(k) and abs(t[1] - x) < 0.6 and t[2] < circuit.ROW["send"] - 5]
        col = [ref for ref in real if abs(real[ref][0] - x) < 0.6]
        nets = set(n for ref in col for n in fnet[ref].values()) - {"GND_F"}
        bad = [n for n in nets if not re.search(rf"^[A-Z]+{k}[LR]?_F$", n)]
        ck.check(f"{name}: column '{k}' over channel {k}'s parts", len(num) == 1 and not bad and len(col) >= 5,
                 f"number {len(num)}, {len(col)} parts, foreign nets {bad[:4]}")
    # PAN L / R: the mark at the CW (right) end names the side the sound goes to when turned fully CW
    for k in circuit.MONO:
        ref = f"RV{3 * k - 1}"
        x, y = real[ref]
        pl = FB.parts[ref]
        p1, p3 = front(pl["pads"]["1"].x, pl["pads"]["1"].y), front(pl["pads"]["3"].x, pl["pads"]["3"].y)
        pins_down = p1[1] > y and p3[1] > y
        cw_right = pins_down and p3[0] > p1[0]          # from the shaft side, pins down: 1 left, CW towards 3
        cw_net = pl["nets"].get("3")                    # fully CW: the wiper (GND) on pin 3 grounds this side
        silent = "L" if cw_net == f"PL{k}_F" else "R" if cw_net == f"PR{k}_F" else "?"
        heard_cw = {"L": "R", "R": "L"}.get(silent, "?")
        marks = {t[0]: t[1] for t in words if t[0] in ("L", "R") and abs(t[1] - x) < 6 and 3 < t[2] - y < 9}
        right_mark = max(marks, key=marks.get) if len(marks) == 2 else None
        ok = pl["nets"].get("2") == "GND_F" and cw_right and right_mark == heard_cw
        ck.check(f"{name}: PAN {k} marks (CW -> {heard_cw})", ok,
                 f"pin 3 on the right: {cw_right}, pin 3 net {cw_net}, mark on the right {right_mark}")
    # row words: vertical, in the left margin, one per row, on the row's centre
    vwords = {t[0]: t for t in texts if t[5]}
    rows = {"SEND": ("send", r"^SD\d_F$"), "PAN": ("pan", r"^P[LR]\d_F$"), "LEVEL": ("level", r"^LV\d[LR]?_F$"),
            "MUTE": ("mute", r"^BTN\d_F$"), "IN": ("jack2", r"^IN\d[LR]?_F$")}
    ck.check(f"{name}: the five row words and nothing else vertical", set(vwords) == set(rows), str(sorted(vwords)))
    for word, (row, pat) in rows.items():
        t = vwords.get(word)
        if t is None:
            continue
        y = circuit.ROW[row]
        in_row = [ref for ref in real if abs(real[ref][1] - y) < 0.1 and real[ref][0] < circuit.M1 - 5]
        good = [ref for ref in in_row if any(re.match(pat, n) for n in fnet[ref].values())]
        ck.check(f"{name}: row word {word} at y {y}, left margin, its row's parts match",
                 abs(t[2] - y) < 0.3 and t[1] < 6.0 and len(good) == len(in_row) and len(in_row) >= 6,
                 f"word at ({t[1]:.2f}, {t[2]:.2f}) {t[6]}; {len(good)}/{len(in_row)} parts match")


label_checks("artwork", svg_texts(art))
label_checks("panel PCB", pcb_texts())
# the same words in both
aw = sorted(t[0] for t in svg_texts(art))
pw = sorted(t[0] for t in pcb_texts())
ck.check("artwork and panel PCB carry the same words", aw == pw,
         f"only artwork {sorted(set(aw) - set(pw))}, only PCB {sorted(set(pw) - set(aw))}")
# vertical STRINGs: angle 90 reads bottom to top only if EasyEDA turns text CCW (not confirmed in an import)
angles = sorted({t[6] for t in pcb_texts() if t[5]})
ck.check("panel PCB row words at one angle (90 = bottom to top if EasyEDA turns CCW)", angles == ["angle 90"],
         str(angles))

# R follows L: the switch lug of each R jack is wired to its L jack's tip, and the artwork draws a dotted link
for l, r in (("J7", "J8"), ("J9", "J10"), ("J11", "J12")):
    ok = fnet[r].get("2") == fnet[l].get("3") and fnet[l].get("2") == "GND_F"
    ck.check(f"{r} normalled to {l} (R follows L)", ok, f"{r}.TN {fnet[r].get('2')}, {l}.tip {fnet[l].get('3')}")
others = [ref for ref in real if ref.startswith("J") and ref not in ("J8", "J10", "J12")
          and fnet[ref].get("2") not in (None, "GND_F")]
ck.check("no other jack normalled to a signal", not others, str(others))
dots = [it for it in panel.layout({ref: (kind_of(ref), "", *real[ref]) for ref in real}) if it[0] == "dots"]
for l, r in (("J7", "J8"), ("J9", "J10"), ("J11", "J12")):
    (lx, ly), (rx, ry) = real[l], real[r]
    hit = [d for d in dots if all(min(math.hypot(px - qx, py - qy) for qx, qy in ((lx, ly), (rx, ry))) < 12
                                  for px, py in d[1]) and len(d[1]) == 2]
    ck.check(f"dotted R-follows-L link between {l} and {r}", len(hit) == 1, f"{len(hit)} dotted lines")

# row-word brackets: two pieces per row word (line broken round the word), at the left margin, each piece
# assigned to the row word nearest its middle, serifs pointing right (at the controls)
lines = [it for it in panel.layout({ref: (kind_of(ref), "", *real[ref]) for ref in real}) if it[0] == "line"]
margin = [ln for ln in lines if all(q[0] < 5.0 for q in ln[1])]
row_y = {"SEND": circuit.ROW["send"], "PAN": circuit.ROW["pan"], "LEVEL": circuit.ROW["level"],
         "MUTE": circuit.ROW["mute"], "IN": circuit.ROW["jack2"]}
pieces = {w: [] for w in row_y}
for ln in margin:
    ys = [q[1] for q in ln[1]]
    mid = (min(ys) + max(ys)) / 2
    pieces[min(row_y, key=lambda w: abs(row_y[w] - mid))].append(ln)
for word, y in row_y.items():
    br = pieces[word]
    serif_right = all(max(q[0] for q in ln[1]) > min(q[0] for q in ln[1]) + 1.0 for ln in br)
    spans = sorted((min(q[1] for q in ln[1]), max(q[1] for q in ln[1])) for ln in br)
    ok = len(br) == 2 and serif_right and spans[0][0] < y < spans[1][1] and spans[0][1] < y < spans[1][0]
    ck.check(f"bracket for {word}: two pieces round the word, serifs pointing right", ok, f"{len(br)} pieces {spans}")
ck.check("no other silk in the left margin", len(margin) == 2 * len(row_y), f"{len(margin)} pieces")
# brackets of neighbouring rows must not touch (a bracket reads as one row)
ends = sorted((min(q[1] for ln in pieces[w] for q in ln[1]), max(q[1] for ln in pieces[w] for q in ln[1]), w)
              for w in row_y)
for (a0, a1, wa), (b0, b1, wb) in zip(ends, ends[1:]):
    ck.check(f"brackets {wa} / {wb} apart (>= 1 mm)", b0 - a1 >= 1.0, f"{wa} ends {a1:.2f}, {wb} starts {b0:.2f}")

# no word under a knob, nut or cap, or over a hole (artwork text boxes: bold sans ~0.68 em per letter,
# caps 0.72 em tall above the baseline)
n_cover = 0
for s_, x, y, size, anchor, vert, cls in svg_texts(art):
    if vert:
        continue
    n_cover += 1
    w_ = (0.55 if "serif" in cls else 0.68) * size * len(s_)
    x0 = {"middle": x - w_ / 2, "start": x, "end": x - w_}[anchor]
    box = (x0, y - 0.72 * size, x0 + w_, y)
    for ref in real:
        cx, cy = real[ref]
        k = kind_of(ref)
        r = (KNOB_D_MAX["mid"] / 2 if ref == "RV25" else knob_r.get(ref, 0)) if k == "pot" else             JACK_NUT_AC / 2 if k == "jack" else BTN_CAP_D / 2
        dxx = max(box[0] - cx, 0, cx - box[2])
        dyy = max(box[1] - cy, 0, cy - box[3])
        if math.hypot(dxx, dyy) < r + 0.2:
            ck.check(f"'{s_}' at ({x:.1f}, {y:.1f}) visible next to {ref}", False,
                     f"{math.hypot(dxx, dyy):.2f} mm from its centre, covered to r {r:.2f}")
ck.check("every horizontal artwork word checked for cover", n_cover == sum(1 for t in svg_texts(art) if not t[5])
         and n_cover > 0, f"{n_cover} words")

# the frame: panel.md's table, in the artwork and the panel PCB
A = {t[0]: t for t in svg_texts(art)}
title, sub = A.get(panel.ART["title"]), A.get(panel.ART["subtitle"])
ck.check("artwork title 'Mycelium' serif 5.2, start at x 12.0, baseline 7.4",
         title is not None and title[4] == "start" and abs(title[1] - 12.0) < 0.01 and abs(title[2] - 7.4) < 0.01
         and title[3] == 5.2 and "serif" in title[6], str(title))
ck.check("artwork subtitle 'Stereo mixer' 2.1, end at x W-12, baseline 6.6",
         sub is not None and sub[4] == "end" and abs(sub[1] - (W - 12.0)) < 0.01 and abs(sub[2] - 6.6) < 0.01
         and sub[3] == 2.1, str(sub))
ck.check("panel names (skill table): Mycelium / Stereo mixer",
         panel.ART["title"] == "Mycelium" and panel.ART["subtitle"] == "Stereo mixer", "")
silk = groups["silk"]
polys = [[tuple(map(float, q.split(","))) for q in pl.get("points").split()] for pl in silk.iter(SVG_NS + "polyline")]
dotted = [pts for pl, pts in zip(silk.iter(SVG_NS + "polyline"), polys) if "dots" in (pl.get("class") or "")]
for yb in (9.6, 10.6):
    ok = any(abs(p[0][1] - yb) < 0.01 and abs(p[-1][1] - yb) < 0.01 and abs(p[0][0] - 3) < 0.01
             and abs(p[-1][0] - (W - 3)) < 0.01 for p in dotted)
    ck.check(f"artwork dotted band line at y {yb}, x 3 .. W-3", ok, "")
rule = [(pl, pts) for pl, pts in zip(silk.iter(SVG_NS + "polyline"), polys)
        if abs(pts[0][1] - 118.6) < 0.01 and abs(pts[-1][1] - 118.6) < 0.01 and "dots" not in (pl.get("class") or "")]
ck.check("artwork bottom rule 0.3 at y 118.6, x 3 .. W-3",
         len(rule) == 1 and float(rule[0][0].get("stroke-width")) == 0.3 and abs(rule[0][1][0][0] - 3) < 0.01
         and abs(rule[0][1][-1][0] - (W - 3)) < 0.01, str(len(rule)))
mark = [pth for pth in silk.iter(SVG_NS + "path") if (pth.get("class") or "") == "copper"]
if ck.check("artwork has the gold mushroom mark", len(mark) == 1, f"{len(mark)} copper paths in #silk"):
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", mark[0].get("d"))]
    xs, ys = nums[0::2], nums[1::2]
    ck.close("mark 4.1 mm tall", max(ys) - min(ys), 4.1, 0.1, " mm")
    ck.close("mark top 1.6 mm under the rule's lower edge (118.75 + 1.6)", min(ys), 118.75 + 1.6, 0.1, " mm")
    ck.close("mark centred", (min(xs) + max(xs)) / 2, W / 2, 0.1, " mm")
# panel PCB frame
P = {t[0]: t for t in pcb_texts()}
pt = next((p for h, p in PANEL_DOC["recs"] if h["type"] == "STRING" and p["text"] == panel.ART["title"]), None)
pt_base = pt and H - pt["y"] * MIL - panel_pcb.INK_BOTTOM * pt["fontSize"] * MIL     # the letters' bottom
ck.check("panel PCB title STRING starts at x 12.0, baseline 7.4", pt is not None and abs(pt["x"] * MIL - 12.0) < 0.02
         and abs(pt_base - 7.4) < 0.02, f"{(pt['x'] * MIL, pt_base) if pt else None}")
ps = P.get(panel.ART["subtitle"])
ck.check("panel PCB subtitle ends at x W-12 (estimated width), baseline 6.6",
         ps is not None and abs(ps[1] + panel_pcb.ink_width(ps[0], ps[3], max(ps[3] / 9, panel_pcb.MIN_STROKE)) / 2
                                - (W - 12)) < 0.05 and abs(ps[2] - 6.6) < 0.02,
         str(ps))
gold = []
for h, p in PANEL_DOC["recs"]:
    if h["type"] == "FILL" and p["layerId"] in (1, 5):
        pts = ca.flatten_path(p["path"][0] if isinstance(p["path"][0], list) else p["path"], MIL)
        if min(q[1] for q in pts) < H - 118.6 and max(q[1] for q in pts) < H - 118.6:
            gold.append((p["layerId"], pts))
if ck.check("panel PCB mark as copper + mask-opening FILLs under the rule",
            any(l == 1 for l, _ in gold) and any(l == 5 for l, _ in gold), f"{len(gold)} fills"):
    ys = [H - q[1] for _, pts in gold for q in pts]
    xs = [q[0] for _, pts in gold for q in pts]
    ck.close("panel PCB mark top at 120.35", min(ys), 120.35, 0.1, " mm")
    ck.close("panel PCB mark 4.1 tall", max(ys) - min(ys), 4.1, 0.1, " mm")
    ck.close("panel PCB mark centred", (min(xs) + max(xs)) / 2, W / 2, 0.1, " mm")
# the words on the gold (OUT L, OUT R, SEND): fabs clip silk inside a mask opening, so since 2026-11-14 they are
# knocked out of the mask: reverse STRINGs on layer 5, each over a hole in its gold area's mask opening
# (panel_pcb.knock_paths), the copper whole: dark letters on the gold, as the artwork draws them
cu_paths = sum(len(p["path"]) for h, p in PANEL_DOC["recs"] if h["type"] == "FILL" and p["layerId"] == 1 and len(p["path"]) > 1)
mask_paths = sum(len(p["path"]) for h, p in PANEL_DOC["recs"] if h["type"] == "FILL" and p["layerId"] == 5 and len(p["path"]) > 1)
knocked = sorted(p["text"] for h, p in PANEL_DOC["recs"] if h["type"] == "STRING" and p["layerId"] == 5 and p.get("reverse"))
on_gold_silk = sorted(p["text"] for h, p in PANEL_DOC["recs"] if h["type"] == "STRING" and p["layerId"] == 3
                      and p["text"] in ("OUT L", "OUT R", "SEND") and p["angle"] % 360 == 0)   # not the SEND row word
ck.check("panel PCB words on the gold knocked out of the mask (reverse, one mask hole each), none as silk",
         knocked == ["OUT L", "OUT R", "SEND"] and mask_paths - cu_paths == 3 and not on_gold_silk,
         f"knocked {knocked}, {mask_paths - cu_paths} mask holes, silk on gold {on_gold_silk}")
# panel content between the band and the rule (holes plus nut / knob extents)
for ref in real:
    x, y = real[ref]
    r = knob_r.get(ref, JACK_NUT_AC / 2 if ref.startswith("J") else BTN_CAP_D / 2)
    ck.check(f"{ref} (with knob / nut) between the band and the rule", y - r >= 10.6 and y + r <= 118.6,
             f"y {y - r:.2f} .. {y + r:.2f}")
# title / subtitle clear of the screw heads (Georgia italic cap height ~0.7 em)
for (mx, my) in want_mounts[:: 1]:
    if my > 10:
        continue
    head = SCREW_HEAD_D / 2
    t_x0 = 12.0
    s_x1 = W - 12.0
    ck.check(f"screw head at x {mx} clear of the title / subtitle (>= 1 mm)",
             (mx + head <= t_x0 - 1.0) if mx < W / 2 else (mx - head >= s_x1 + 1.0),
             f"head {mx - head:.2f} .. {mx + head:.2f}; title from {t_x0}, subtitle to {s_x1}")
# the hole CSV's labels: the CSV is what a hand driller reads
for ref, lbl in csv_labels.items():
    if ref.startswith("J"):
        circ = next(j[1] for j in circuit.JACKS if j[0] == ref)
        ck.check(f"CSV label of {ref} = circuit label", lbl == circ, f"{lbl} vs {circ}")
ck.check("CSV / circuit label of J13 matches the panel word (DRUM IN)",
         csv_labels.get("J13") == panel.JACK_WORD["J13"], f"CSV '{csv_labels.get('J13')}', panel '{panel.JACK_WORD['J13']}'")

ck.done()
