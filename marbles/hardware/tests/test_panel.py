"""Panel group: the Spore panel (Marblesy, 18HP) and the mechanics in front of and behind it.

  HOLES   every representation of the panel holes - circuit.PLACEMENT through panel.py's hole list, the hole CSV,
          the drill SVG, the artwork SVG, panel_pcb.py and the routed master's panel PCB (round holes and the four
          slots) - against the routed faceplate's real parts: jack barrel 6.48 mm from the sleeve pin towards the
          tip (KiCad PJ398SM), pot shaft on the lugs' midpoint (KiCad RD901F), button cap on its four switch pins,
          LED between its two pins; through the frame in circuit.py's comment (panel x = 90 - x_pcb + 0.65,
          panel y from the top = 118.25 - y). Hole sizes against design.md and against the parts' bushings
  EURO    Doepfer A-100: 128.5 mm, 18HP width, the mounting slots (7.5 mm from the left, a multiple of 5.08 apart,
          3 mm from the edges), the 108 mm board between the rails, panel parts out of the rail zone, the screw
          heads at the board holes clear of the panel-side bodies
  FRONT   knobs (design.md 15 / 10 mm), jack nuts, button caps and rings, LEDs: edge gaps for fingers, plugs beside
          knobs, no word under a knob, nut or cap
  DEPTH   the stack behind the panel against design.md's "about 45-50 mm" and the EuroSynth nominal depth
  FRAME   the house frame (module-design panel.md / design.md "Panel artwork"): title, subtitle, dotted band, rule,
          mushroom mark, in the artwork and in the routed panel PCB's silk and copper; the panel name Spore
  LABELS  every word against the part under it by the routed faceplate's nets (pots, CLOCK / DEJA VU jacks, the
          output band, buttons, t / X, the three-state labels, the knob-to-jack dotted guides); silk text sizes and
          line widths against JLCPCB; the copper band's 0.4 mm bare ring round its 14 holes (EasyEDA wants 0.3)

Run from marbles/hardware/tests:  python test_panel.py
Only reads: imports the tools' pure functions (panel.py's main() is not called), opens the exports as zips.
"""
import csv
import math
import os
import re
import xml.etree.ElementTree as ET

import harness

ck = harness.Checks("panel")
circuit = harness.load("circuit")
panel = harness.load("panel")
panel_pcb = harness.load("panel_pcb")
ca = harness.load("copper_audit")
MIL = harness.MIL

# ====================================================================== constants (sources)
# Eurorack, Doepfer A-100 mechanical details (doepfer.de/a100_man/a100m_e.htm) as the stereo mixer's panel group
# quoted them: 3U panel 128.5 mm, HP 5.08 mm, the HP width table (18HP = 91.30 mm), mounting hole centres 3 mm from
# the top / bottom edge and 7.5 mm from the left edge, hole spacing a multiple of 5.08 mm.
# (verifier, re-read 2026-11-13: "the final height is 128.5 mm for all A-100 front panels"; 18 HP: calculated 91.44,
# actual 91.30; "The horizontal distance of the mounting holes has to be a multiple of the HP grid"; rail screws
# "M3x6 oval-head screws with cross recess (DIN7985)". The 7.5 / 3 mm hole positions are in the page's sketch
# (an image), not re-read.)
PANEL_H, HP_MM, W18, HP = 128.5, 5.08, 91.30, 18
MOUNT_Y, MOUNT_X0 = 3.0, 7.5
# SDIY wiki "Eurorack panel components" via the mixer's group: PCB max 108-110 mm, clear space between rails
# 112.2-115.1 mm, panel parts at least 10 mm from the top / bottom edges (the rails).
PCB_MAX_H, RAIL_CLEAR_MIN, RAIL_ZONE = 108.0, 112.2, 10.0
# design.md: panel 91.3 x 128.5, board 90 x 108 centred; holes pots 7.5, jacks 6.5, buttons 6.5; slots 5.5 x 3.2,
# centres 3 mm from the top / bottom, 7.5 / 83.8 mm from the left
DES_HOLE = {"pot": 7.5, "jack": 6.5, "ledbutton": 6.5}
DES_SLOT, DES_SLOT_X = (5.5, 3.2), (7.5, 83.70)    # design.md; 83.8 until L14 (2026-11-14)
LED_HOLE = 3.2                       # panel.py's LED hole (design.md gives none): a 3 mm LED's light through it
# parts
JACK_S_BARREL = 6.48                 # KiCad Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical: barrel circle (0, 6.48) from S
JACK_THREAD = 6.0                    # Thonkiconn M6 x 0.5 bushing (Thonk / QingPu drawing not re-read: nominal)
JACK_NUT_AF = 8.0                    # Thonkiconn hex nut across flats (module-design parts.md "about 8 mm"; unconfirmed)
JACK_NUT_AC = JACK_NUT_AF / math.cos(math.radians(30))     # 9.24 across the corners
JACK_BODY = (9.0, 2.03, 12.48)       # KiCad PJ398SM fab: width, near / far end from the sleeve pin (typ)
POT_BUSHING = 7.0                    # KiCad Potentiometer_Alpha_RD901F-40-00D fab circle d 7.0 (M7 bushing)
POT_BODY = (9.5, 1.0, 12.35)         # KiCad RD901F fab: width, from 1 mm off the pin row to 4.85 past the shaft
BTN_CAP, BTN_BODY = 5.5, 7.5         # Thonk LP LED button (parts.md, LowProfileButton.pdf; not re-read)
LED_FLANGE = 3.8                     # 3 mm LED flange (Kingbright T-1; not confirmed)
POS_TOL = 0.3                        # panel PCB drill +-0.1, faceplate drill +-0.1, a part's play ~0.1: summed
BUSH_PLAY = 0.1                      # per side round a threaded bushing (it centres itself under the nut)
PLUG_BODY_D = 9.0                    # a moulded 3.5 mm patch-cable plug body, max (mixer's figure; assumed)
# verifier change: 5.6 (ISO 7045) -> 6.0. The BOM's "M3 x 6 mm pan-head screw" names no standard; DIN 7985 M3 (still
# sold, and Doepfer's own rail screw) has dk 6.0, k 2.4 (Westfield Fasteners' DIN 7985 summary); ISO 7045 M3 dk 5.6.
SCREW_HEAD_D, SCREW_HEAD_K = 6.0, 2.4
# knobs: design.md "Three large knobs (RATE, DEJA VU, SPREAD, 15 drawn), five small (10)"; bom.md "about 15 / 10 mm"
KNOB_D = {"RV1": 15.0, "RV4": 15.0, "RV6": 15.0}
KNOB_D_SMALL = 10.0
# finger gaps between the edges (house thresholds the mixer's panel group used; judgement, not a standard)
MIN_GAP = {("pot", "pot"): 2.5, ("jack", "jack"): 2.0, ("ledbutton", "pot"): 3.0, ("jack", "pot"): 2.0,
           ("jack", "ledbutton"): 2.0, ("ledbutton", "ledbutton"): 3.0}
# depth (mm behind the panel's rear face)
PANEL_GAP = 7.0                      # module-design panel.md: "Panel-to-PCB gap with Thonkiconn and Alpha 9 mm pots
#                                      is about 7 mm" (house, unconfirmed); parts.md says the pots stand 9.5-10
PANEL_GAP_HIGH = 10.0
PCB_T = 1.6
STACK_GAP = 8.5 + 2.5                # female socket 8.5 (bom.md) on male plastic 2.5
BREAKOUT_GAP = (8.5, 8.5 + 2.5)      # main board to the breakout's near face: the 8.5 sockets, plus the J1-J5 male
#                                      headers' plastic if they sit under the breakout
SEED_STACK = 8.5 + 2.5 + 1.6 + 3.0   # breakout's far side: the Seed's 8.5 sockets (H1 / H2), its male headers'
#   plastic, the Seed 1.6 (Daisy Seed datasheet v1.0.5), its USB / parts ~3 (the drawing's "3mm"; not confirmed)
CAP_8X12 = 12.0 + 0.5                # the breakout's C9 / C18, 100 uF 8 x 12 (its BOM) plus a seating allowance
IDC_STACK = 2.5 + 9.0 + 3.0          # J2's plastic, an IDC socket (~9, assumed), the ribbon's bend (~3, assumed)
DESIGN_DEPTH = (45.0, 50.0)          # design.md "about 45-50 mm from the panel"
EUROSYNTH_DEPTH = 60.0               # EuroSynth mechanical spec, nominal module depth (mixer's figure; not re-read)
# fab / house frame
JLC_SILK_H, JLC_SILK_W = 1.0, 0.15   # JLCPCB min silk text height / line width (as read by the mixer, 2026-11-04)
SLOT_COPPER = 0.3                    # design.md: EasyEDA's DRC wants copper 0.3 mm from a slot region
BAND_CLEAR = 0.4                     # design.md: a 0.4 mm ring of bare board round each of the 14 band holes
FRAME = {"title": ("Spore", 5.2, 12.0, 7.4), "subtitle": ("Random sampler", 2.1, 12.0, 6.6),
         "band": (9.6, 10.6), "rule": (118.6, 0.3), "mark": (4.1, 1.6)}     # panel.md table + the garden names table

# ====================================================================== the parts as routed
R = harness.routed()
FB, MB = R.face, R.main
W, H = panel.PANEL_W, panel.PANEL_H
BW, BH = circuit.BOARD_W, circuit.BOARD_H
X0, Y0 = (W - BW) / 2, (H - BH) / 2


def to_panel(x, y):
    """Routed board frame (rear view, y up) -> panel mm from the top-left (circuit.py's comment)."""
    return (BW - x) + 0.65, 118.25 - y


ck.close("HOLES.frame_x_offset_is_the_centring", 0.65, X0, 1e-6, " mm")
ck.close("HOLES.frame_y_offset_is_the_centring", 118.25, H - Y0, 1e-6, " mm")


def kind_of(ref):
    return "jack" if ref.startswith("J") else "pot" if ref.startswith("RV") else "ledbutton" if ref.startswith("SW") else "led"


def centre(ref):
    pl = FB.parts[ref]
    p = pl["pads"]
    if ref.startswith("J"):
        s, t = p["1"], p["3"]
        d = math.hypot(t.x - s.x, t.y - s.y)
        return s.x + (t.x - s.x) / d * JACK_S_BARREL, s.y + (t.y - s.y) / d * JACK_S_BARREL
    if ref.startswith("RV"):
        return (p["4"].x + p["5"].x) / 2, (p["4"].y + p["5"].y) / 2
    if ref.startswith("SW"):
        return sum(p[n].x for n in "1234") / 4, sum(p[n].y for n in "1234") / 4
    return (p["1"].x + p["2"].x) / 2, (p["1"].y + p["2"].y) / 2


REFS = sorted(circuit.PLACEMENT)
real = {ref: to_panel(*centre(ref)) for ref in REFS}
want_d = {ref: (DES_HOLE.get(kind_of(ref), LED_HOLE)) for ref in REFS}
ck.check("HOLES.panel_parts_present", all(FB.parts[r]["bottom"] for r in REFS) and len(REFS) == 38,
         f"{len(REFS)} parts in PLACEMENT (16 jacks, 8 pots, 7 buttons, 7 LEDs)")


def match(name, got, tol=0.05):
    """got: [(x, y, d)] in the panel frame. One hole per real part, on it, of design.md's size; nothing else."""
    used, bad = set(), []
    for ref in REFS:
        x, y = real[ref]
        dd, i = min((math.hypot(hx - x, hy - y), i) for i, (hx, hy, hd) in enumerate(got))
        used.add(i)
        if dd > tol or abs(got[i][2] - want_d[ref]) > 0.02:
            bad.append(f"{ref}: {dd:.3f} mm off, d {got[i][2]:.2f} (want {want_d[ref]})")
    extra = [got[i] for i in range(len(got)) if i not in used]
    ck.check(f"HOLES.on_the_parts.{name}", not bad, f"{len(bad)}: {bad[:6]}")
    ck.check(f"HOLES.no_extra.{name}", not extra and len(got) == len(REFS), f"{len(got)} holes, extra {extra[:4]}")


# 1. panel.py's hole list (from PLACEMENT and its offsets)
feats = panel.features()
match("panel.py", [(*panel.panel_xy(hx, hy), panel.HOLE[k]) for k, ref, lbl, ox, oy, hx, hy in feats])
# 2. the hole CSV
rows = list(csv.DictReader(open(os.path.join(harness.PANEL, "marbles-panel-holes.csv"), encoding="utf-8")))
match("CSV", [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), float(r["hole_mm"])) for r in rows
              if r["kind"] != "mount"], tol=0.02)
csv_mounts = sorted((float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), r["hole_mm"]) for r in rows if r["kind"] == "mount")
SVG = "{http://www.w3.org/2000/svg}"
drill = ET.parse(os.path.join(harness.PANEL, "marbles-panel-drill.svg")).getroot()
match("drill SVG", [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in drill.iter(SVG + "circle")], tol=0.02)
drill_slots = sorted((float(r.get("x")) + float(r.get("width")) / 2, float(r.get("y")) + float(r.get("height")) / 2,
                      float(r.get("width")), float(r.get("height"))) for r in drill.iter(SVG + "rect") if r.get("rx"))
art = ET.parse(os.path.join(harness.PANEL, "marbles-panel.svg")).getroot()
G = {g.get("id"): g for g in art.iter(SVG + "g")}
match("artwork SVG", [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in G["holes"].iter(SVG + "circle")], tol=0.02)
art_slots = sorted((float(r.get("x")) + float(r.get("width")) / 2, float(r.get("y")) + float(r.get("height")) / 2,
                    float(r.get("width")), float(r.get("height"))) for r in G["holes"].iter(SVG + "rect"))
PB = panel_pcb.PanelBoard()
match("panel_pcb.py", [(x, H - y, d) for x, y, d in PB.holes])
# the routed master's panel PCB
pp_holes, pp_slots, pp_outline, pp_fills = [], [], None, []
for h, p in R.panel["recs"]:
    if h["type"] == "FILL" and p:
        paths = p["path"] if isinstance(p["path"][0], list) else [p["path"]]
        if p["layerId"] == 12 and paths[0][0] == "CIRCLE":
            _, x, y, r = paths[0]
            pp_holes.append((x * MIL, H - y * MIL, 2 * r * MIL))
        elif p["layerId"] == 12:
            pts = ca.flatten_path(paths[0], MIL)
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            pp_slots.append(((min(xs) + max(xs)) / 2, H - (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)))
        else:
            pp_fills.append((p["layerId"], paths))
    elif h["type"] == "POLY" and p and p.get("polyType") == "BOARD_OUTLINE":
        pp_outline = p["path"]
match("routed panel PCB", pp_holes)
gen = sorted((round(x, 2), round(y, 2), round(d, 2)) for x, y, d in PB.holes)
got = sorted((round(x, 2), round(H - y, 2), round(d, 2)) for x, y, d in pp_holes)
ck.check("HOLES.routed_panel_equals_panel_pcb_py", gen == got, f"{len(gen)} generated, {len(got)} routed")
# slots in every representation
want_slots = sorted((x, y) for x in DES_SLOT_X for y in (MOUNT_Y, H - MOUNT_Y))
for name, got_s in (("panel.py", [(x, y, panel.SLOT_W, panel.SLOT_H) for x, y in panel.MOUNTS]),
                    ("CSV", [(x, y, *map(float, d.split(" slot")[0].split(" x "))) for x, y, d in csv_mounts]),
                    ("drill SVG", drill_slots), ("artwork SVG", art_slots),
                    ("panel_pcb.py", [(x, H - y, w, h_) for x, y, w, h_ in PB.slots]), ("routed panel PCB", pp_slots)):
    g = sorted(got_s)
    ok = len(g) == 4 and all(math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02 and abs(a[2] - DES_SLOT[0]) < 0.02
                             and abs(a[3] - DES_SLOT[1]) < 0.02 for a, b in zip(g, want_slots))
    ck.check(f"HOLES.slots_as_design_md.{name}", ok, f"expected 5.5 x 3.2 at {want_slots}, got "
             f"{[tuple(round(v, 2) for v in s) for s in g]}")
# hole sizes against the parts
ck.check("HOLES.jack_hole_clears_the_M6_thread", DES_HOLE["jack"] >= JACK_THREAD + 2 * BUSH_PLAY,
         f"{DES_HOLE['jack']} vs {JACK_THREAD} + 2 x {BUSH_PLAY}")
ck.check("HOLES.jack_nut_bears_on_the_panel", JACK_NUT_AF >= DES_HOLE["jack"] + 1.0, f"nut {JACK_NUT_AF} AF, hole {DES_HOLE['jack']}")
ck.within("HOLES.pot_hole_on_the_M7_bushing", DES_HOLE["pot"], POT_BUSHING + 2 * BUSH_PLAY, POT_BUSHING + 0.6, " mm",
          "clears the bushing, not loose")
ck.check("HOLES.button_cap_passes_with_position_tolerance", DES_HOLE["ledbutton"] >= BTN_CAP + 2 * POS_TOL
         and DES_HOLE["ledbutton"] < BTN_BODY, f"hole {DES_HOLE['ledbutton']}, cap {BTN_CAP} + 2 x {POS_TOL}, body {BTN_BODY}")
ck.check("HOLES.panel_py_sizes_as_design_md", all(panel.HOLE[k] == v for k, v in DES_HOLE.items()),
         f"{ {k: panel.HOLE[k] for k in DES_HOLE} }")

# ====================================================================== EURO: Eurorack mechanics
ck.close("EURO.height_128.5", H, PANEL_H, 0.001, " mm")
ck.close("EURO.width_18HP", W, W18, 0.005, " mm")
if pp_outline:
    _, x0, y0, ow, oh, *_ = pp_outline
    ck.check("EURO.routed_panel_outline", abs(ow * MIL - W) < 0.01 and abs(oh * MIL - H) < 0.01, f"{ow * MIL:.3f} x {oh * MIL:.3f}")
xs = sorted({round(x, 3) for x, y in panel.MOUNTS})
n_hp = (xs[1] - xs[0]) / HP_MM
ck.check("EURO.slot_spacing_a_multiple_of_HP", abs(n_hp - round(n_hp)) < 0.005 and abs(xs[0] - MOUNT_X0) < 0.01,
         f"x {xs}: {xs[1] - xs[0]:.2f} mm = {n_hp:.3f} HP; (HP - 3) x 5.08 puts the right one at "
         f"{MOUNT_X0 + (HP - 3) * HP_MM:.2f} (panel.md says 83.8)")
print(f"INFO  a 5.5 mm slot leaves +-{(DES_SLOT[0] - 3.2) / 2:.2f} mm of play for a 3.2 mm hole position on the rail")
ys = sorted({round(y, 3) for x, y in panel.MOUNTS})
ck.check("EURO.slot_rows_3mm_from_the_edges", abs(ys[0] - MOUNT_Y) < 0.01 and abs(H - ys[1] - MOUNT_Y) < 0.01, f"{ys}")
ck.check("EURO.board_height_fits_the_rails", BH <= PCB_MAX_H and (RAIL_CLEAR_MIN - BH) / 2 >= 1.0,
         f"{BH} mm board, {(RAIL_CLEAR_MIN - BH) / 2:.2f} mm each side inside the tightest rails")
# board centred: one offset for every part (real centre in the board frame vs its hole)
# verifier change: the offsets were taken from real[] = to_panel(centre), so they were to_panel's own constants
# (0.65, 10.25) for every part by construction: the check could not fail. They now come from the routed panel
# PCB's holes (the nearest one to each part), which no part of to_panel() produced.
offs = []
for ref in REFS:
    bx, by = centre(ref)
    hx, hy, _ = min(pp_holes, key=lambda q: math.hypot(q[0] - real[ref][0], q[1] - real[ref][1]))
    offs.append((hx - (BW - bx), H - hy - by))
mean = (sum(o[0] for o in offs) / len(offs), sum(o[1] for o in offs) / len(offs))
spread = max(math.hypot(o[0] - mean[0], o[1] - mean[1]) for o in offs)
ck.check("EURO.boards_centred", spread < 0.1 and abs(mean[0] - X0) < 0.05 and abs(mean[1] - Y0) < 0.05,
         f"panel PCB hole minus mirrored part centre: mean ({mean[0]:.3f}, {mean[1]:.3f}) against the centring "
         f"({X0:.3f}, {Y0:.3f}), spread {spread:.3f} mm")


def body_panel(ref):
    """The part's real body as a panel-frame polygon (or circle)."""
    pl = FB.parts[ref]

    def to_b(fx, fy):
        fy = -fy if pl["bottom"] else fy
        dx, dy = ca.rot(fx, fy, pl["angle"])
        return to_panel(pl["x"] + dx, pl["y"] + dy)
    if ref.startswith("J"):
        s0 = -5.7
        y1, y2 = s0 + JACK_BODY[1], s0 + JACK_BODY[2]
        return ("poly", [to_b(sx * JACK_BODY[0] / 2, y) for sx, y in ((-1, y1), (1, y1), (1, y2), (-1, y2))])
    if ref.startswith("RV"):
        r0 = -3.5
        y1, y2 = r0 + POT_BODY[1], r0 + POT_BODY[2]
        return ("poly", [to_b(sx * POT_BODY[0] / 2, y) for sx, y in ((-1, y1), (1, y1), (1, y2), (-1, y2))])
    if ref.startswith("SW"):
        return ("poly", [to_b(sx * BTN_BODY / 2, sy * BTN_BODY / 2) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return ("circle", real[ref], LED_FLANGE / 2)


def extent_y(b):
    pts = b[1] if b[0] == "poly" else [(b[1][0], b[1][1] - b[2]), (b[1][0], b[1][1] + b[2])]
    return min(q[1] for q in pts), max(q[1] for q in pts)


bad = []
for ref in REFS:
    y1, y2 = extent_y(body_panel(ref))
    if y1 < RAIL_ZONE or H - y2 < RAIL_ZONE:
        bad.append(f"{ref} y {y1:.2f}-{y2:.2f}")
ck.check("EURO.panel_parts_out_of_the_rail_zone", not bad, f"{bad} (>= {RAIL_ZONE} mm from the edges)")


def poly_circle_gap(poly, c, r):
    inside = ca.point_in_poly(c, poly)
    d = min(ca.d_point_seg(c, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))
    return -d - r if inside else d - r


# screw heads on the faceplate's panel side, at the board holes
bad = []
for x, y, d in FB.holes:
    c = to_panel(x, y)
    for ref in REFS:
        b = body_panel(ref)
        g = (poly_circle_gap(b[1], c, SCREW_HEAD_D / 2) if b[0] == "poly"
             else math.hypot(b[1][0] - c[0], b[1][1] - c[1]) - b[2] - SCREW_HEAD_D / 2)
        if g < 0:
            bad.append(f"head at panel ({c[0]:.1f}, {c[1]:.1f}) into {ref} by {-g:.2f}")
ck.check("EURO.screw_heads_clear_the_panel_side_bodies", not bad, f"{bad}")

# ====================================================================== FRONT: knobs, nuts, caps
def radius(ref):
    k = kind_of(ref)
    if k == "pot":
        return KNOB_D.get(ref, KNOB_D_SMALL) / 2
    if k == "jack":
        return JACK_NUT_AC / 2
    if k == "ledbutton":
        return BTN_CAP / 2
    return LED_HOLE / 2


items = [(ref, kind_of(ref), *real[ref], radius(ref)) for ref in REFS if kind_of(ref) != "led"]
worst = {}
for i, (a, ka, xa, ya, ra) in enumerate(items):
    for b, kb, xb, yb, rb in items[i + 1:]:
        g = math.hypot(xa - xb, ya - yb) - ra - rb
        key = tuple(sorted((ka, kb)))
        if key not in worst or g < worst[key][0]:
            worst[key] = (g, a, b)
for key, (g, a, b) in sorted(worst.items()):
    ck.check(f"FRONT.gap.{key[0]}-{key[1]}", g >= MIN_GAP[key] - 0.005,
             f"tightest {a}-{b}: {g:.2f} mm (house minimum {MIN_GAP[key]}; knobs 15 / 10, nut corners {JACK_NUT_AC:.2f})")
# the output LEDs' holes stay visible: clear of the nuts' corners, knobs and caps by 0.5 mm
led_gap = min((math.hypot(real[l][0] - x, real[l][1] - y) - LED_HOLE / 2 - r, l, ref)
              for l in REFS if kind_of(l) == "led" for ref, k, x, y, r in items)
ck.check("FRONT.led_holes_clear_of_nuts_knobs_caps", led_gap[0] >= 0.5, f"tightest {led_gap[1]}-{led_gap[2]}: {led_gap[0]:.2f} mm")
# the drawn knobs in the artwork mock-up are the sizes design.md states
ck.check("FRONT.artwork_knobs_as_design_md", abs(2 * panel.ART["knob_big"] - 15) < 0.01 and abs(2 * panel.ART["knob_small"] - 10) < 0.01
         and panel.BIG_POTS == set(KNOB_D), f"big {2 * panel.ART['knob_big']}, small {2 * panel.ART['knob_small']}, {sorted(panel.BIG_POTS)}")
bom = harness.text("docs", "bom.md")
kn = [(int(n), float(d)) for n, d in re.findall(r"\| (\d+) \| Knob for a T18 shaft, about ([\d.]+) mm across", bom)]
ck.check("FRONT.bom_knobs_as_design_md", sorted(kn) == sorted([(3, 15.0), (5, 10.0)]), f"bom.md {kn}")
# plugs: a patch cable's moulded body beside a knob or another plug
bad = []
for ref, k, x, y, r in items:
    if k != "jack":
        continue
    for o, ko, xo, yo, ro in items:
        if o == ref or ko == "ledbutton":
            continue
        d = math.hypot(x - xo, y - yo)
        need = PLUG_BODY_D / 2 + (PLUG_BODY_D / 2 if ko == "jack" else ro) + (0.5 if ko == "jack" else 1.5)
        if d < need:
            bad.append(f"{ref}-{o} {d:.2f} < {need:.2f}")
ck.check("FRONT.plugs_clear_knobs_and_plugs", not bad, f"{sorted(set(bad))[:8]}")
# rings round the deja vu buttons, outside their holes
ring_r = panel.ART["cap_led"] + 1.6
ck.check("FRONT.button_ring_outside_the_hole", ring_r - 0.35 / 2 >= DES_HOLE["ledbutton"] / 2 + 0.3,
         f"ring r {ring_r} (0.35 line), hole r {DES_HOLE['ledbutton'] / 2}")
ck.close("FRONT.button_ring_at_cap_plus_1.6", ring_r, BTN_CAP / 2 + 1.6, 0.01, " mm")
for ref in ("RV1", "RV4", "RV6"):
    ck.check(f"FRONT.scale_arc_clears_the_knob.{ref}", panel.ART["scale_big"] - 0.15 >= KNOB_D[ref] / 2,
             f"arc r {panel.ART['scale_big']}, knob r {KNOB_D[ref] / 2}")
ck.check("FRONT.scale_arc_clears_the_small_knobs", panel.ART["scale_small"] - 0.15 >= KNOB_D_SMALL / 2,
         f"arc r {panel.ART['scale_small']}, knob r {KNOB_D_SMALL / 2}")


def svg_texts(root):
    out = []
    for t in root.iter(SVG + "text"):
        s = (t.text or "") + "".join((c.text or "") for c in t)
        out.append((s.strip(), float(t.get("x")), float(t.get("y")), float(t.get("font-size")), t.get("text-anchor"),
                    t.get("class") or ""))
    return out


A = svg_texts(G["silk"]) + svg_texts(G["copper"])
covered = []
for s, x, y, size, anchor, cls in A:
    w_ = (0.55 if "serif" in cls else 0.68) * size * len(s)
    x0 = {"middle": x - w_ / 2, "start": x, "end": x - w_}[anchor]
    box = (x0, y - 0.72 * size, x0 + w_, y)
    for ref in REFS:
        cx, cy = real[ref]
        r = radius(ref) if kind_of(ref) != "led" else LED_HOLE / 2
        dx = max(box[0] - cx, 0, cx - box[2])
        dy = max(box[1] - cy, 0, cy - box[3])
        if math.hypot(dx, dy) < r + 0.2:
            covered.append(f"'{s}' at ({x:.1f}, {y:.1f}) under {ref} ({math.hypot(dx, dy):.2f} < {r + 0.2:.2f})")
ck.check("FRONT.no_word_under_a_knob_nut_cap_or_hole", not covered, f"{covered}")

# ====================================================================== DEPTH
front_stack = PANEL_GAP + PCB_T + STACK_GAP + PCB_T
far = max(SEED_STACK, CAP_8X12, IDC_STACK)
depths = {f"{PANEL_GAP} gap, breakout on {g} mm": front_stack + g + PCB_T + far for g in BREAKOUT_GAP}
lo, hi = min(depths.values()), max(depths.values())
print(f"INFO  depth behind the panel: {PANEL_GAP} panel gap + {PCB_T} faceplate + {STACK_GAP} board gap + {PCB_T} main board"
      f" + {BREAKOUT_GAP[0]}-{BREAKOUT_GAP[1]} to the breakout + {PCB_T} breakout + {far:.1f} (Seed on its sockets "
      f"{SEED_STACK:.1f}, C9 / C18 {CAP_8X12}, J2 with a cable {IDC_STACK}) = {lo:.1f}-{hi:.1f} mm; with a "
      f"{PANEL_GAP_HIGH} mm panel gap {hi + PANEL_GAP_HIGH - PANEL_GAP:.1f}")
ck.within("DEPTH.as_design_md", hi, DESIGN_DEPTH[0] - 1.0, DESIGN_DEPTH[1] + 1.0, " mm", "design.md about 45-50")
ck.within("DEPTH.fits_a_eurosynth_depth_case", hi + PANEL_GAP_HIGH - PANEL_GAP, None, EUROSYNTH_DEPTH, " mm",
          "the deepest reading of the stack")

# ====================================================================== FRAME: the house frame
T = {}
for s, x, y, size, anchor, cls in svg_texts(art):
    T.setdefault(s, (x, y, size, anchor, cls))
ttl, sub = FRAME["title"], FRAME["subtitle"]
t = T.get(ttl[0])
ck.check("FRAME.title_artwork", t is not None and t[3] == "start" and abs(t[0] - ttl[2]) < 0.01 and abs(t[1] - ttl[3]) < 0.01
         and abs(t[2] - ttl[1]) < 0.001 and "serif" in t[4], f"{t}")
t = T.get(sub[0])
ck.check("FRAME.subtitle_artwork", t is not None and t[3] == "end" and abs(t[0] - (W - sub[2])) < 0.01
         and abs(t[1] - sub[3]) < 0.01 and abs(t[2] - sub[1]) < 0.001, f"{t}")
ck.check("FRAME.panel_name_spore", panel.ART["title"] == "Spore" and panel.ART["subtitle"] == "Random sampler",
         f"{panel.ART['title']} / {panel.ART['subtitle']} (panel.md garden names: marbles -> Spore, Random sampler)")
silk = G["silk"]
lines = [(float(l.get("x1")), float(l.get("y1")), float(l.get("x2")), float(l.get("y2")), l.get("class") or "",
          l.get("stroke-width")) for l in silk.iter(SVG + "line")]
for yb in FRAME["band"]:
    ok = any(abs(l[1] - yb) < 0.01 and abs(l[3] - yb) < 0.01 and abs(l[0] - 3) < 0.01 and abs(l[2] - (W - 3)) < 0.01
             and "dots" in l[4] for l in lines)
    ck.check(f"FRAME.dotted_band_artwork.y{yb}", ok, "")
ok = any(abs(l[1] - FRAME["rule"][0]) < 0.01 and abs(l[3] - FRAME["rule"][0]) < 0.01 and abs(l[0] - 3) < 0.01
         and abs(l[2] - (W - 3)) < 0.01 and "dots" not in l[4] and float(l[5] or 0) == FRAME["rule"][1] for l in lines)
ck.check("FRAME.rule_artwork", ok, "")
mark = [pth for pth in silk.iter(SVG + "path") if (pth.get("class") or "") == "copper"]
if ck.check("FRAME.mark_artwork_present", len(mark) == 1, f"{len(mark)}"):
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", mark[0].get("d"))]
    mx, my = nums[0::2], nums[1::2]
    rule_low = FRAME["rule"][0] + FRAME["rule"][1] / 2
    ck.close("FRAME.mark_artwork_height", max(my) - min(my), FRAME["mark"][0], 0.1, " mm")
    ck.close("FRAME.mark_artwork_top", min(my), rule_low + FRAME["mark"][1], 0.1, " mm")
    ck.close("FRAME.mark_artwork_centred", (min(mx) + max(mx)) / 2, W / 2, 0.1, " mm")
# the routed panel PCB
PS = [p for h, p in R.panel["recs"] if h["type"] == "STRING" and p]
pt = next((p for p in PS if p["text"] == ttl[0]), None)
# EasyEDA's measured font (panel_pcb.INK_*, 2026-11-14): a STRING's letters stand INK_BOTTOM x fontSize above its
# origin and are ink_width() wide, so the baseline is H - y - INK_BOTTOM x F (panel frame)


def base_of(p):
    return H - p["y"] * MIL - panel_pcb.INK_BOTTOM * p["fontSize"] * MIL


def ink_w(p):
    return panel_pcb.ink_width(p["text"], p["fontSize"] * MIL / 0.9, p["strokeWidth"] * MIL)


ck.check("FRAME.title_panel_pcb", pt is not None and abs(pt["x"] * MIL - ttl[2]) < 0.02 and abs(base_of(pt) - ttl[3]) < 0.02
         and abs(pt["fontSize"] * MIL / 0.9 - ttl[1]) < 0.02, f"{pt and (pt['x'] * MIL, base_of(pt), pt['fontSize'] * MIL)}")
ps = next((p for p in PS if p["text"] == sub[0]), None)
end = ps and ps["x"] * MIL + ink_w(ps)
ck.check("FRAME.subtitle_panel_pcb", ps is not None and abs(end - (W - sub[2])) < 0.05 and abs(base_of(ps) - sub[3]) < 0.02,
         f"end {end}, baseline {ps and base_of(ps)}")
if pt and ps:
    t_end = pt["x"] * MIL + ink_w(pt)
    ck.check("FRAME.title_ends_1.5mm_before_the_subtitle", ps["x"] * MIL - t_end >= 1.5,
             f"title to {t_end:.2f}, subtitle from {ps['x'] * MIL:.2f} (panel.md; lower case taken as wide as capitals)")
POLYS = [(p["layerId"], p.get("width", 0) * MIL, ca.flatten_path(p["path"], MIL)) for h, p in R.panel["recs"]
         if h["type"] == "POLY" and p and p.get("polyType") == "NORMAL"]
for yb in FRAME["band"]:
    dashes = [pts for L, w, pts in POLYS if L == 3 and len(pts) == 2 and all(abs(H - q[1] - yb) < 0.01 for q in pts)]
    xs_ = sorted(q[0] for pts in dashes for q in pts)
    ck.check(f"FRAME.dotted_band_panel_pcb.y{yb}", len(dashes) > 50 and abs(xs_[0] - 3) < 0.2 and abs(xs_[-1] - (W - 3)) < 0.2,
             f"{len(dashes)} dashes from x {xs_[0] if xs_ else None} to {xs_[-1] if xs_ else None}")
rule = [(w, pts) for L, w, pts in POLYS if L == 3 and len(pts) == 2 and all(abs(H - q[1] - FRAME["rule"][0]) < 0.01 for q in pts)
        and abs(pts[1][0] - pts[0][0]) > 50]
ck.check("FRAME.rule_panel_pcb", len(rule) == 1 and abs(rule[0][0] - FRAME["rule"][1]) < 0.01 and
         abs(min(q[0] for q in rule[0][1]) - 3) < 0.01 and abs(max(q[0] for q in rule[0][1]) - (W - 3)) < 0.01, f"{rule}")
gold = [(L, paths) for L, paths in pp_fills if L in (1, 5)]
markf = []
for L, paths in gold:
    pts = ca.flatten_path(paths[0], MIL)
    if min(H - q[1] for q in pts) > FRAME["rule"][0]:
        markf.append((L, pts, paths))
top = [q for L, pts, pa in markf if L == 1 for q in pts]
if ck.check("FRAME.mark_panel_pcb_copper_and_mask", top and sum(1 for m in markf if m[0] == 1) == sum(1 for m in markf if m[0] == 5),
            f"{sum(1 for m in markf if m[0] == 1)} copper, {sum(1 for m in markf if m[0] == 5)} mask fills"):
    ys_ = [H - q[1] for q in top]
    xs_ = [q[0] for q in top]
    ck.close("FRAME.mark_panel_pcb_top", min(ys_), FRAME["rule"][0] + FRAME["rule"][1] / 2 + FRAME["mark"][1], 0.1, " mm")
    ck.close("FRAME.mark_panel_pcb_height", max(ys_) - min(ys_), FRAME["mark"][0], 0.1, " mm")
    ck.close("FRAME.mark_panel_pcb_centred", (min(xs_) + max(xs_)) / 2, W / 2, 0.1, " mm")


def closed(path):
    nums = [v for v in path if not isinstance(v, str)]
    return len(nums) >= 4 and abs(nums[0] - nums[-2]) < 1e-3 and abs(nums[1] - nums[-1]) < 1e-3


open_paths = [L for L, pts, pa in markf if not all(closed(p) for p in pa)]
ck.check("FRAME.mark_fill_paths_closed", not open_paths, f"open FILL paths (panel.md: EasyEDA drew no mark): {len(open_paths)}")

# ====================================================================== LABELS
fnet = {ref: FB.parts[ref]["nets"] for ref in REFS}
POT_LABEL = {ref: lbl for ref, lbl, wiper, mp, ch in circuit.POTS}
POT_WIPER = {lbl: wiper for ref, lbl, wiper, mp, ch in circuit.POTS}
JACK_LABEL = {ref: lbl for ref, lbl, tip, tn in circuit.JACKS}
JACK_TIP = {lbl: tip for ref, lbl, tip, tn in circuit.JACKS}
BTN = {ref: (lbl, sw) for ref, lbl, sw in circuit.BUTTONS}


def pcb_texts():
    out = []
    for p in PS:
        size = p["fontSize"] * MIL / 0.9
        x = p["x"] * MIL + ink_w(p) / 2
        out.append((p["text"], x, base_of(p), size, "middle", ""))
    return out


def side(x):
    return "t" if x < W / 2 else "X"


def label_checks(name, texts):
    words = [t for t in texts if t[0]]
    # pot words under their knob: the routed wiper net is the one circuit.POTS gives that label (BIAS: t left, X right)
    pots = [r for r in REFS if r.startswith("RV")]
    seen = set()
    for s, x, y, size, anchor, cls in words:
        under = [r for r in pots if abs(real[r][0] - x) < 0.6 and 0 < y - real[r][1] < 14]
        if not under or s not in {POT_LABEL[r].split(" (")[0] for r in pots}:
            continue
        r = min(under, key=lambda r: y - real[r][1])
        lbl = s if s != "BIAS" else f"BIAS ({side(x)})"
        ok = fnet[r].get("2") == POT_WIPER.get(lbl)
        seen.add(r)
        ck.check(f"LABELS.{name}.pot_word.{r}", ok, f"'{s}' under {r} at x {x:.1f}: wiper {fnet[r].get('2')}, "
                 f"{lbl} is {POT_WIPER.get(lbl)}")
    ck.check(f"LABELS.{name}.every_pot_has_its_word", seen == set(pots), f"without: {sorted(set(pots) - seen)}")
    # CLOCK / DEJA VU over their jacks
    for s, x, y, size, anchor, cls in words:
        if s not in ("CLOCK", "DEJA VU"):
            continue
        below = [r for r in REFS if r.startswith("J") and abs(real[r][0] - x) < 0.6 and 0 < real[r][1] - y < 8]
        if not below and s == "DEJA VU":
            continue                              # the DEJA VU knob's own word
        r = below[0] if below else None
        want = {"CLOCK": f"{side(x)} CLOCK".replace("t CLOCK", "T CLOCK"), "DEJA VU": "DEJA VU"}[s]
        ok = r is not None and fnet[r].get("3") == JACK_TIP.get(want)
        ck.check(f"LABELS.{name}.jack_word.{s}" + (f".{side(x)}" if s == "CLOCK" else ""), ok, f"over {r}: tip {r and fnet[r].get('3')}, {want} is {JACK_TIP.get(want)}")
    # the output band: t1 t2 t3 Y X1 X2 X3, each 2.6 mm right of its jack, over it
    outs = [r for r in REFS if r.startswith("J") and abs(real[r][1] - real["J9"][1]) < 0.1]
    got = {}
    for s, x, y, size, anchor, cls in words:
        if re.fullmatch(r"[tX][123]|Y", s):
            r = next((r for r in outs if abs(real[r][0] + 2.6 - x) < 1.2 and 0 < real[r][1] - y < 8), None)
            if r:
                got[r] = s
                ok = fnet[r].get("3") == JACK_TIP.get(s.upper())
                ck.check(f"LABELS.{name}.output_word.{r}", ok, f"'{s}': tip {fnet[r].get('3')}, {s.upper()} is {JACK_TIP.get(s.upper())}")
    ck.check(f"LABELS.{name}.every_output_has_its_word", set(got) == set(outs), f"without: {sorted(set(outs) - set(got))}")
    # buttons: MODE / RANGE / EXT under their buttons, t / X beside the deja vu pair
    for s, x, y, size, anchor, cls in words:
        if s in ("MODE", "RANGE", "EXT"):
            above = [r for r in REFS if r.startswith("SW") and abs(real[r][0] - x) < 0.6 and 0 < y - real[r][1] < 7]
            r = above[0] if above else None
            lbl = BTN.get(r, ("", ""))[0]
            ok = r is not None and s.lower() in lbl.lower() and fnet[r].get("3") == f"BTN_{BTN[r][1]}_F" \
                and (s == "EXT" or lbl.startswith(side(x)))
            ck.check(f"LABELS.{name}.button_word.{s}" + (f".{side(x)}" if s != "EXT" else ""), ok, f"under {r} ({lbl}), net {r and fnet[r].get('3')}")
        if s in ("t", "X") and size >= 6:
            r = min((r for r in REFS if r.startswith("SW")), key=lambda r: math.hypot(real[r][0] - x, real[r][1] - y))
            ck.check(f"LABELS.{name}.section_letter.{s}", BTN[r][0] == f"{s} deja vu" and fnet[r].get("3") == f"BTN_{s.upper()}_DEJAVU_F",
                     f"nearest button {r} ({BTN[r][0]}), net {fnet[r].get('3')}")
    # three-state labels beside their buttons
    for sw, triple in panel.MODE_LABELS.items():
        hits = [t for t in words if t[0] in triple]
        nearest = {min((r for r in REFS if r.startswith("SW")), key=lambda r: math.hypot(real[r][0] - t[1], real[r][1] - t[2]))
                   for t in hits}
        ck.check(f"LABELS.{name}.three_state.{sw}", len(hits) == 3 and nearest == {sw},
                 f"{[t[0] for t in hits]} nearest {sorted(nearest)} ({BTN[sw][0]})")
    # LENGTH graduations round RV5 (POT_LENGTH_F)
    nums = [t for t in words if t[0] in panel.LENGTHS and t[3] < 2.0]
    near5 = all(math.hypot(real["RV5"][0] - t[1], real["RV5"][1] - t[2]) < 10 for t in nums)
    ck.check(f"LABELS.{name}.length_graduations_on_RV5", len(nums) == 8 and near5 and fnet["RV5"].get("2") == "POT_LENGTH_F", f"{len(nums)}")


label_checks("artwork", svg_texts(art))
label_checks("panel_pcb", pcb_texts())
aw = sorted(t[0] for t in svg_texts(art))
pw = sorted(t[0] for t in pcb_texts())
ck.check("LABELS.artwork_and_panel_pcb_same_words", aw == pw, f"only artwork {sorted(set(aw) - set(pw))}, only PCB {sorted(set(pw) - set(aw))}")
# the knob-to-jack dotted guides: a CV jack's tip is its knob's parameter (POT_x_F <-> CV_x_F)
dots = [[tuple(map(float, q.split(","))) for q in pl.get("points").split()] for pl in G["silk"].iter(SVG + "polyline")
        if "dots" in (pl.get("class") or "")]
pairs = []
for pts in dots:
    a, z = pts[0], pts[-1]
    pot = min((r for r in REFS if r.startswith("RV")), key=lambda r: math.hypot(real[r][0] - a[0], real[r][1] - a[1]))
    jack = min((r for r in REFS if r.startswith("J")), key=lambda r: math.hypot(real[r][0] - z[0], real[r][1] - z[1]))
    pairs.append((pot, jack))
    wiper, tip = fnet[pot].get("2", ""), fnet[jack].get("3", "")
    ck.check(f"LABELS.guide.{pot}-{jack}", wiper.replace("POT_", "CV_") == tip, f"wiper {wiper}, tip {tip}")
ck.check("LABELS.guides_as_panel_py", sorted(pairs) == sorted(panel.KNOB_TO_JACK.items()), f"{sorted(pairs)}")
cv_jacks = {r for r in REFS if r.startswith("J") and fnet[r].get("3", "").startswith("CV_")}
named = {j for p, j in pairs} | {r for r in REFS if r.startswith("J") and fnet[r].get("3") == "CV_DEJAVU_F"}
ck.check("LABELS.every_cv_jack_named", cv_jacks == named, f"CV jacks without a guide or word: {sorted(cv_jacks - named)}")
# output LEDs: the LED left of each output label is that output's
bad = []
for led, jack in circuit.OUTPUT_LEDS.items():
    lbl = next((l for r, l, k, s in circuit.LEDS if r == led), None) or next((l for r, l, n in circuit.GATE_LEDS if r == led), None)
    lx, ly = real[led]
    jx, jy = real[jack]
    if (lbl or "").upper() != JACK_LABEL[jack] or not (abs(jx - lx - 4.2) < 0.05):
        bad.append(f"{led} ({lbl}) by {jack} ({JACK_LABEL[jack]}) at dx {jx - lx:.2f}")
    if led in ("D11", "D12", "D13"):
        res = [p for p in FB.parts if p.startswith("R") and set(FB.parts[p]["nets"].values()) ==
               {fnet[jack].get("3"), fnet[led].get("1")}]
        if not res:
            bad.append(f"{led}: no resistor from {fnet[jack].get('3')} to its anode {fnet[led].get('1')}")
ck.check("LABELS.output_leds_belong_to_their_jacks", not bad, f"{bad}")
# silk sizes on the panel PCB
# the letters' real height is (INK_TOP - INK_BOTTOM) x fontSize (measured), not the font size
INK_H = panel_pcb.INK_TOP - panel_pcb.INK_BOTTOM
small = sorted({(p["text"], round(INK_H * p["fontSize"] * MIL, 2)) for p in PS
                if INK_H * p["fontSize"] * MIL < JLC_SILK_H - 1e-6})
thin = sorted({(p["text"], round(p["strokeWidth"] * MIL, 3)) for p in PS if p["strokeWidth"] * MIL < JLC_SILK_W - 1e-3})
ck.check("LABELS.panel_pcb_text_height", not small, f"{small}; smallest {min(INK_H * p['fontSize'] * MIL for p in PS):.2f} mm")
ck.check("LABELS.panel_pcb_text_stroke", not thin, f"{thin}; thinnest {min(p['strokeWidth'] * MIL for p in PS):.3f} mm")
lw = sorted({round(w, 3) for L, w, pts in POLYS if L == 3})
ck.check("LABELS.panel_pcb_silk_lines", min(lw) >= JLC_SILK_W - 1e-3, f"widths {lw}")
# the copper band: copper (layer 1) and mask opening (layer 5) alike, a ring of bare board round each hole
band = [(L, paths) for L, paths in pp_fills if L in (1, 5) and len(paths) > 1]
# the mask opening is the copper's shape plus a hole round each knocked-out label (panel_pcb.knock_paths)
bandL = dict(band)
ck.check("LABELS.band_copper_and_mask", sorted(bandL) == [1, 5] and bandL[5][:len(bandL[1])] == bandL[1],
         f"{len(band)} band fills; {len(bandL.get(5, [])) - len(bandL.get(1, []))} knock-out holes in the mask")
# the X / Y / t outputs' words on the band: reverse STRINGs on the mask layer, each over a hole in the band's mask
knocked = [p for p in PS if p.get("layerId") == 5]
ck.check("LABELS.band_words_knocked_out", len(knocked) == len(bandL.get(5, [])) - len(bandL.get(1, []))
         and all(p.get("reverse") for p in knocked) and not any(p.get("layerId") == 3 and p["text"] in {q["text"] for q in knocked}
                                                               for p in PS),
         f"{sorted(p['text'] for p in knocked)} on the mask layer (reverse), "
         f"{len(bandL.get(5, [])) - len(bandL.get(1, []))} holes")
if band:
    paths = band[0][1]
    outline = ca.flatten_path(paths[0], MIL)
    bx = (min(q[0] for q in outline), max(q[0] for q in outline))
    by = (min(H - q[1] for q in outline), max(H - q[1] for q in outline))
    ck.check("LABELS.band_as_design_md", abs(bx[0] - 2.6) < 0.01 and abs(W - bx[1] - 2.6) < 0.01 and abs(bx[1] - bx[0] - 86.1) < 0.01
             and abs(by[1] - by[0] - 15.2) < 0.01, f"x {bx[0]:.2f}-{bx[1]:.2f}, y {by[0]:.2f}-{by[1]:.2f}")
    cuts = []
    for c in paths[1:]:
        pts = ca.flatten_path(c, MIL)
        cx_ = (min(q[0] for q in pts) + max(q[0] for q in pts)) / 2
        cy_ = H - (min(q[1] for q in pts) + max(q[1] for q in pts)) / 2
        cuts.append((cx_, cy_, (max(q[0] for q in pts) - min(q[0] for q in pts)) / 2))
    through = [r for r in REFS if bx[0] < real[r][0] < bx[1] and by[0] - want_d[r] / 2 < real[r][1] < by[1] + want_d[r] / 2]
    bad = []
    for r in through:
        c = min(cuts, key=lambda c: math.hypot(c[0] - real[r][0], c[1] - real[r][1]))
        ring = c[2] - want_d[r] / 2
        off = math.hypot(c[0] - real[r][0], c[1] - real[r][1])
        if off > 0.05 or abs(ring - BAND_CLEAR) > 0.01 or ring - off < SLOT_COPPER:
            bad.append(f"{r}: cut r {c[2]:.2f}, ring {ring:.2f}, off {off:.2f}")
        if not (bx[0] + c[2] <= real[r][0] <= bx[1] - c[2] and by[0] + c[2] <= real[r][1] <= by[1] - c[2]):
            bad.append(f"{r}: its clearance crosses the band edge")
    ck.check("LABELS.band_rings_round_its_14_holes", len(through) == 14 and len(cuts) == 14 and not bad,
             f"{len(through)} holes in the band, {len(cuts)} cuts; {bad}")
    others = [r for r in REFS if r not in through]
    gap = min((max(abs(real[r][0] - (bx[0] + bx[1]) / 2) - (bx[1] - bx[0]) / 2, abs(real[r][1] - (by[0] + by[1]) / 2) - (by[1] - by[0]) / 2)
               - want_d[r] / 2, r) for r in others)
    ck.check("LABELS.band_copper_0.3_from_other_holes", gap[0] >= SLOT_COPPER, f"nearest other hole {gap[1]} {gap[0]:.2f} mm")
    ck.check("LABELS.band_fill_paths_closed", all(closed(p) for p in paths[:1]), "outline path")

ck.done()
