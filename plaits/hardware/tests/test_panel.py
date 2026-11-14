"""Panel and mechanics of Plaitsy (Orchid, 12HP).

What it checks, from the parts' datasheet geometry and the Eurorack spec,
not from the numbers the generators happen to produce:

  A. Where the panel parts really are: the barrel / shaft / cap / LED centre
     of every panel part, worked out from the pads of the ROUTED faceplate
     (Plaits-routed.epro2) and the parts' own drawings (Thonkiconn PJ398SM:
     barrel 6.48 mm from the sleeve pin towards the tip; Alpha RD901F: shaft
     on the line of the two mounting lugs, 7.5 mm from the pin row; Thonk LED
     button: cap on the centre of its four switch pins; 3 mm LED: on its middle
     lead). The two footprint-origin offsets circuit.py uses (barrel 0.78 mm
     from the WQP518MA origin, shaft 4.0 mm from the RD901F origin) are derived
     again from the drawings plus the footprints, and the pot pin directions
     (circuit.POT_PINS) from the routed pads. Then every representation of the
     panel holes against those centres: circuit.PANEL_XY, circuit.PLACEMENT,
     panel.features(), the hole CSV, the drill SVG, the artwork SVG (#holes),
     panel_pcb.PanelBoard() and the panel PCB in the routed master, in the
     panel frame and in the faceplate's own (PCB) frame.
  B. Hole sizes against the parts (M6 jack thread, M7 pot bushing, 5.5 mm
     button cap and its 7.5 mm base, 3 mm LED body), design.md's hole table.
  C. Eurorack mechanics (Doepfer A-100): 128.5 mm, 12HP = 60.60 mm, the four
     mounting slots (3 mm from top / bottom, x 7.5 and 7.5 + 9 x 5.08), their
     size against the M3 screw head, the two 108 mm boards centred between
     the rails, nothing in the rail zone, everything within the 12HP width.
  D. Front clearances: knobs as drawn (15 / 12 / 10 mm), the pot washer and
     nut, the jack nut's corners, button caps, LEDs; jack pitch against a
     patch plug; LEDs and caps clear of the knob skirts.
  E. Heights behind the panel: Thonkiconn body, Alpha body to the bushing
     shoulder, the LED button's cap base, the 3 mm LEDs; thread left for the
     nuts; how high the LEDs must stand. Depth behind the panel through the
     faceplate, the header gap, the main board and the breakout + Seed stack
     (the tallest of the Seed, C9 / C18, U3 and J2's plug on the breakout's
     Seed side); the breakout's main-board side (SMD parts, solder tails) in
     its 11 mm socket gap.
  F. Labels: every jack, pot and button named on the panel (word, guide or
     mark) by the part's net on the routed faceplate, the same words in the
     artwork and the panel PCB, no word over a hole or under a knob / nut,
     silk sizes against JLCPCB's minimums, silk clear of the holes, the
     OUT / AUX band (copper + mask opening, the 0.4 mm masked rings round the
     two jack holes, the labels on it).
  G. The house frame (panel.md): title, subtitle, dotted band, rule, the
     gold mushroom mark (top copper + top mask, no net), the Garden name.
  H. design.md's panel figures and its "Differences from Plaits" about the
     panel; Plaits' own panel positions where they could be read.

Run from plaits/hardware/tests:  python test_panel.py
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
panel = harness.load("panel")              # pure functions only; main() is not called
panel_pcb = harness.load("panel_pcb")      # PanelBoard() collects in memory; doc() / render() are not called
mushroom = harness.load("mushroom")
ca = harness.load("copper_audit")
MIL = harness.MIL

# ================================================================ datasheet / spec constants
# --- Thonkiconn PJ398SM (Thonk drawing "Thonkiconn_Jack_Datasheet-new.jpg", model PJ398SM, unit mm,
#     general tolerance +-0.15; https://www.thonk.co.uk/wp-content/uploads/2018/07/Thonkiconn_Jack_Datasheet-new.jpg,
#     the older PJ301M-12 sheet Thonkiconn_Jack_Datasheet.pdf shows the same numbers). Typ unless noted.
JACK_TIP_FROM_BARREL = 4.92      # PCB layout (top view): pin 3 (tip) to the barrel centre
JACK_SW_FROM_BARREL = 3.38       # pin 2 (switch) to the barrel centre, on the sleeve side
JACK_SLEEVE_FROM_BARREL = 6.48   # pin 1 (sleeve) to the barrel centre
JACK_THREAD_D = 6.0              # side view: bushing "Ø6" (Thonk sells it as M6 x 0.5; pitch not on the drawing)
JACK_BUSHING_L = 5.5             # side view: bushing length beyond the body face
JACK_BODY_H = 9.0                # side view: body from its PCB face to its bushing face (= panel rear), +-0.15
                                 # (verifier re-read both Thonk sheets 2026-11-13: "5.5 | 9 | 3.5", drawn 3:1 and to
                                 # scale; a retailer's table for the QingPu PC-mount jack also gives "body depth 9 mm")
JACK_BODY_TOL = 0.15
JACK_BODY_H_MEASURED = 10.0      # a builder's measurement of the PJ301M-12 Thonkiconn, PCB to the top of the body
                                 # (l71.github.io/hardware_notes.html), and Alpha 9 mm pots 10 mm too: disagrees with
                                 # Thonk's drawing; not confirmed either way here
JACK_BODY_W = 9.0                # front view: body 9 wide, 6.0 to the tip side, 4.5 to the sleeve side of the barrel
JACK_BODY_TIP_SIDE, JACK_BODY_SLEEVE_SIDE = 6.0, 4.5
JACK_PIN_L = 3.5                 # pins below the body
# Not on the drawing (not confirmed): the hex nut Thonk supplies, "about 8 mm across" in the house parts.md;
# its corners (worst case for clearances) = AF / cos 30. Thickness assumed 2.0 mm.
JACK_NUT_AF = 8.0
JACK_NUT_AC = JACK_NUT_AF / math.cos(math.radians(30))
JACK_NUT_T = 2.0
# --- Alpha 9 mm vertical pot RD901F-40 (Taiwan Alpha drawing SLH-211-208 "RD901F-40-(L)K-XXX-0X57", the
#     datasheet Thonk links: Alpha-9mm-Vertical-T18-RD901F-40-15K-B50K-0057.pdf; tolerances unless stated:
#     < 10 mm +-0.3, 10-30 mm +-0.5). L = 15 / F = 7 / T = 6 / M = 1 is the T18 shaft Thonk sells.
POT_BODY_H = 10.0                # side view: seating plane (rear frame) to the bushing shoulder, +-0.5
POT_BODY_TOL = 0.5
POT_BUSHING_D = 7.0              # M7 x 0.75
POT_BUSHING_L = 5.0
POT_SHAFT_L = 15.0               # from the shoulder (L), +-0.5
POT_ROW_TO_SHAFT = 7.5           # side view 7.5 +-0.5 shaft axis to the pins; PCB hole detail 7.5 lug line to pin row
POT_LUG_SPAN, POT_LUG_SLOT = 11.4, 1.8      # PCB hole detail: lug slots 1.8 x 1.1, 11.4 over their outer ends
POT_LUG_HALF = (POT_LUG_SPAN - POT_LUG_SLOT) / 2   # 4.8: lug centres either side of the shaft
POT_PIN_PITCH = 2.5              # three 1.0 mm holes over 5.0
POT_HOUSING_W = 9.5              # front view 9.5 +-0.3; shaft 4.85 from the far edge, 6.5 from the pin edge
POT_NUT_AF, POT_NUT_T = 10.0, 2.0          # "NUT 1PC": M7 x 0.75 hex, 10.0 across flats, 2.0 thick
POT_NUT_AC = POT_NUT_AF / math.cos(math.radians(30))
POT_WASHER_OD, POT_WASHER_ID = 12.0, 7.1   # "WASHER 1PC"
POT_WASHER_T = 0.5               # not dimensioned on the drawing (not confirmed): assumed
# --- Thonk low-profile LED button (Thonk LowProfileButton.pdf, drawing of the PB01-109TL type; tolerances
#     X.X +-0.25, X.XX +-0.1; drawn 4:1). The feet below the body are not dimensioned: measured off the
#     drawing (scale 4:1), so treat them as +-0.1.
BTN_CAP_D = 5.5                  # top view Ø5.5
BTN_BASE = 7.5                   # top view □7.5: the square base the cap stands on (moves with it)
BTN_TOTAL_H = 14.0               # cap top to the bottom of the two side feet, +-0.25
BTN_CAP_TO_BASE_BOTTOM = 6.3     # cap top to the underside of the square base, +-0.2
BTN_BASE_T = 2.5                 # the square base's thickness, +-0.25
BTN_SIDE_FEET = 0.35             # measured: the two side feet below the body
BTN_CENTRE_FOOT = 0.71           # measured: the third (centre) foot below the body
BTN_PIN_L = 3.5
BTN_SW_PITCH, BTN_LED_PITCH = 5.08, 5.4    # switch pins on a 5.08 square, LED pins 5.4 apart through the centre
BTN_TRAVEL = 0.25                # tact travel: "see specification" on the drawing; typical, not confirmed
# --- 3 mm LED (Tayda 3-lead red/green common cathode per bom.md; no datasheet for that listing). Verifier
#     2026-11-13: Kingbright L-3WEGW (3-lead 3 mm bicolour, DSAA6458 V.18A page 1, vector drawing rendered; tolerance
#     +-0.25 unless noted): body Ø3 [0.118], flange Ø4 [0.157] x 1 [0.039], dome tip to the flange's back 5 [0.197],
#     leads 24.5 [0.965] min. The writer's generic figures were flange Ø3.8, 5.3 high, leads 25.
LED_BODY_D, LED_FLANGE_D, LED_FLANGE_T, LED_H = 3.0, 4.0, 1.0, 5.0
LED_LEAD_L = 24.5
# --- Eurorack, Doepfer A-100 mechanical details (doepfer.de/a100_man/a100m_e.htm and its figure A100FP.gif):
#     panel 128.5 high, HP 5.08, 12HP actual width 60.60 (Doepfer's table), holes d 3.2 at 3.0 mm from the
#     top / bottom edge, 7.5 mm from the left edge, N x 5.08 apart; screws M3 x 6 DIN 7985.
PANEL_H, HP_MM, W12 = 128.5, 5.08, 60.60
MOUNT_FROM_EDGE_Y, MOUNT_FROM_LEFT, MOUNT_HOLE_D = 3.0, 7.5, 3.2
SCREW_HEAD_D = 5.6               # DIN 7985 M3 pan head, d_k max (standard; not re-read here)
# SDIY wiki "Eurorack panel components" (sdiy.info): clear space between the rails 112.2 (Schroff, tightest)
# .. 115.1 mm; PCB height 108-110 mm max; keep panel components 10 mm from the top / bottom edges (rails);
# stacked boards on pin headers 11 mm. Doepfer's pages give no PCB keep-out figure.
RAIL_CLEAR_MIN, PCB_MAX_H, RAIL_ZONE, STACK_GAP = 112.2, 108.0, 10.0, 11.0
# --- JLCPCB silkscreen minimums. Verifier re-read jlcpcb.com/capabilities/pcb-capabilities 2026-11-13: "Minimum
#     Line Width >=0.15mm" (the writer had 0.153), "Minimum text height 40 mil (1.0mm)", "Pad To Silkscreen 0.15mm";
#     the page says nothing about silk on exposed copper. JLCPCB's blog (jlcpcb.com/blog/pcb-silkscreen): CAM runs
#     "an unconditional Silkscreen Clipping protocol based on the principle of Solder Mask Precedence", trimming
#     legend within a 0.15 mm buffer of mask openings.
SILK_MIN_W, SILK_MIN_TEXT_H, SILK_HOLE_CLEAR = 0.15, 1.0, 0.15
PCB_T = 1.6                      # every board and the panel: 1.6 mm FR4 (bom.md)
# --- patch cable plug (moulded 3.5 mm plugs: about 6-9 mm across the grip; not confirmed): worst case
PLUG_D = 9.0
# --- the main board's rear stack (sources: plaits/docs/bom.md; Rob Heel's breakout BOM 2025-08-29 and its
#     Gerbers; Daisy Seed datasheet v1.0.5 technical drawing)
SOCKET_H = 8.5                               # female header body (bom.md; no datasheet read)
MALE_PLASTIC = 2.54                          # male header plastic: FCI BergStik II 67996 rev DH, 67997 row: total 11.43 =
                                             # tail 3.05 + mating 5.84 + 2.54 (verifier: was 2.5, not sourced)
SEED_PCB_T = 1.6                             # Seed drawing "1.6mm"
SEED_TOP_H = 3.0                             # Seed drawing "3mm" above its board (USB jack, parts): meaning not confirmed
BRK_CAP_L = 12.0                             # breakout C9 / C18: 100 uF 50 V "8X12" (LCSC C2749, Chengxing KM: D 8, L 12;
BRK_CAP_L_TOL = 1.5                          #   L < 20: +1.5 max per its dimension table)
BRK_DCDC_H = 10.16                           # breakout U3 Mornsun B2405S-1WR2 SIP, 11.60 x 6.00 x 10.16 (datasheet)
# Which side those sit on (verifier 2026-11-13, settling the pcb / panel disagreement): the breakout's bottom
# silkscreen (H1 / H2 "SEED USB", U3, C9 / C18 "100uF", J2 "RED STRIPE") is its Seed side, and it faces AWAY from
# Plaitsy's main board: the footprint's nets only match the drill pattern mirrored (pcb B.breakout_*), and Rob
# Heel's build photo (seed_breadboard_01.jpg) has Seed, DC/DC, both cans and the IDC cable on top, only the long
# female-header tails and the 1x4 male headers (plastic under the board) below. On the side facing the main board:
# the SMD parts, tallest the 1206 10 uF CL31A106KBHNNNE (Samsung thickness code H 1.60 +-0.20), TSSOP-14 (TI PW
# 1.2 max), SOD-123; the through-hole parts' solder tails (J2: BergStik tail 3.05 through 1.6; U3 / C9 / C18 leads:
# not dimensioned, clipped like any lead, 2.5 mm = IPC-A-610 class 2's maximum protrusion used).
BRK_SMD_H = 1.6 + 0.2
BRK_TAIL_OUT = 2.5
IDC_PLUG_H = 9.0                             # a 2x5 IDC socket's body on J2's pins, plus a ~3 mm ribbon bend: assumed
RIBBON_BEND = 3.0
SKIFF_DEPTH = 45.5                           # Intellijel Palette 4U 62HP: max module depth 45.5 mm (37.4 at the 1HP
                                             # edges), retailer listings; taken as a typical skiff. The user's 2 x 150HP
                                             # case: depth unknown
# --- house rules for finger room (the stereo mixer's suite), mm between the outlines
MIN_GAP = {("pot", "pot"): 2.5, ("jack", "jack"): 2.0, ("ledbutton", "pot"): 3.0, ("jack", "pot"): 2.0,
           ("jack", "ledbutton"): 2.0, ("ledbutton", "ledbutton"): 3.0, ("led", "pot"): 0.5,
           ("led", "ledbutton"): 1.0, ("jack", "led"): 1.0, ("led", "led"): 0.5}
HEIGHT_AGREE = 0.3               # parts that touch the panel must agree this well, or one hangs or presses

# ================================================================ what the panel should be
W, H = circuit.PANEL_W, circuit.PANEL_H
BW, BH = circuit.BOARD_W, circuit.BOARD_H
X0, Y0 = (W - BW) / 2, (H - BH) / 2
R = harness.routed()
FB, MB, PANEL_DOC = R.face, R.main, R.panel
DESIGN = harness.text("docs", "design.md")
BOMMD = harness.text("docs", "bom.md")
KNOB_D_DRAWN = {"big": 15.0, "mid": 12.0, "small": 10.0}      # design.md "Knobs as drawn"


def front(x, y):
    """Routed faceplate (EasyEDA top-layer view = rear of the stack, y up) -> panel mm from the top-left."""
    return (BW - x) + X0, H - Y0 - y


def pcb_panel(x, y):
    """Panel PCB frame (front, y up, origin bottom-left) -> panel mm from the top-left."""
    return x, H - y


def kind_of(ref):
    return {"J": "jack", "R": "pot", "S": "ledbutton", "D": "led"}[ref[0]]


def unit(ax, ay, bx, by):
    d = math.hypot(bx - ax, by - ay)
    return (bx - ax) / d, (by - ay) / d, d


def fp_pads(title):
    """{num: (x, y)} of a footprint in its own frame (mm), from the routed export."""
    g = next(g for g in R.fp_geo.values() if g["title"] == title)
    return {n: (p["x"], p["y"]) for n, p in g["pads"].items()}


# ================================================================ A. where the parts are
def centre(pl):
    """Mechanical centre of a placed panel part (board frame), from its pads and the part drawing."""
    p, ref = pl["pads"], pl["ref"] if "ref" in pl else None
    first = next(iter(p.values())).ref
    if first.startswith("J"):
        s, t = p["1"], p["3"]
        ux, uy, _ = unit(s.x, s.y, t.x, t.y)
        return s.x + ux * JACK_SLEEVE_FROM_BARREL, s.y + uy * JACK_SLEEVE_FROM_BARREL
    if first.startswith("RV"):
        return (p["4"].x + p["5"].x) / 2, (p["4"].y + p["5"].y) / 2
    if first.startswith("SW"):
        return sum(p[n].x for n in "1234") / 4, sum(p[n].y for n in "1234") / 4
    return p["2"].x, p["2"].y


PANEL_REFS = sorted(circuit.PANEL_XY, key=lambda r: (r[0], int(re.sub(r"\D", "", r))))
real, real_board = {}, {}
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if not ck.check(f"A.on_panel_side.{ref}", pl is not None and pl["bottom"],
                    "on the faceplate's bottom (panel) side" if pl else "missing from the routed faceplate"):
        continue
    real_board[ref] = centre(pl)
    real[ref] = front(*real_board[ref])

# the footprints against the drawings, so centre() rests on the real geometry
WQP = fp_pads("CONN-TH_WQP-WQP518MA")
ALPHA = fp_pads("POT-ALPHA-9MM-RD901F")
ck.close("A.thonkiconn_tip_sleeve_spacing", math.hypot(WQP["3"][0] - WQP["1"][0], WQP["3"][1] - WQP["1"][1]),
         JACK_TIP_FROM_BARREL + JACK_SLEEVE_FROM_BARREL, 0.02, " mm")
ck.close("A.thonkiconn_switch_from_sleeve", math.hypot(WQP["2"][0] - WQP["1"][0], WQP["2"][1] - WQP["1"][1]),
         JACK_SLEEVE_FROM_BARREL - JACK_SW_FROM_BARREL, 0.02, " mm")
# the barrel offset from the WQP518MA origin, from the drawing: sleeve + 6.48 towards the tip
ux, uy, _ = unit(*WQP["1"], *WQP["3"])
bx, by = WQP["1"][0] + ux * JACK_SLEEVE_FROM_BARREL, WQP["1"][1] + uy * JACK_SLEEVE_FROM_BARREL
barrel_off = math.hypot(bx, by) * (1 if (bx * ux + by * uy) > 0 else -1)      # + = towards the tip
ck.close("A.barrel_offset_from_WQP518MA_origin (drawing)", barrel_off, 0.78, 0.005, " mm towards the tip")
# circuit.JACK_BARREL: the barrel 0.78 below the origin with the sleeve up (tip down)
ck.close("A.circuit_JACK_BARREL = drawing", circuit.JACK_BARREL, -barrel_off, 0.005, " mm (front view, sleeve up)")
# Alpha: pins in a row 2.5 apart, the lugs +-4.8 either side of the shaft line, the pin row 7.5 from it
row = [ALPHA[n] for n in "123"]
lug_mid = ((ALPHA["4"][0] + ALPHA["5"][0]) / 2, (ALPHA["4"][1] + ALPHA["5"][1]) / 2)
ck.close("A.alpha_pin_pitch", math.hypot(row[2][0] - row[0][0], row[2][1] - row[0][1]) / 2, POT_PIN_PITCH, 0.02, " mm")
ck.close("A.alpha_lug_half_spacing", math.hypot(ALPHA["5"][0] - ALPHA["4"][0], ALPHA["5"][1] - ALPHA["4"][1]) / 2,
         POT_LUG_HALF, 0.02, " mm")
ck.close("A.alpha_pin_row_to_shaft", math.hypot(row[1][0] - lug_mid[0], row[1][1] - lug_mid[1]), POT_ROW_TO_SHAFT,
         0.02, " mm")
row_from_origin = math.hypot(*row[1])
shaft_off = POT_ROW_TO_SHAFT - row_from_origin           # beyond the origin, away from the pins
ck.close("A.shaft_offset_from_RD901F_origin (drawing)", shaft_off, 4.0, 0.005, " mm")
ck.close("A.circuit_POT_SHAFT = drawing", circuit.POT_SHAFT, shaft_off, 0.005, " mm")
ck.close("A.shaft_on_the_lug_line (footprint origin to lug midpoint)", math.hypot(*lug_mid), shaft_off, 0.02, " mm")

for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    p = pl["pads"]
    if ref.startswith("J"):
        st = math.hypot(p["3"].x - p["1"].x, p["3"].y - p["1"].y)
        ck.close(f"A.jack_pad_spacing.{ref}", st, JACK_TIP_FROM_BARREL + JACK_SLEEVE_FROM_BARREL, 0.02, " mm")
        cx, cy = real_board[ref]
        off = math.hypot(cx - pl["x"], cy - pl["y"])
        ck.close(f"A.barrel_from_origin.{ref}", off, abs(circuit.JACK_BARREL), 0.02, " mm")
        # sleeve pad up (towards the top of the board) as circuit.py says
        ck.check(f"A.jack_sleeve_up.{ref}", p["1"].y > p["3"].y and abs(p["1"].x - p["3"].x) < 0.01,
                 f"sleeve ({p['1'].x:.2f}, {p['1'].y:.2f}), tip ({p['3'].x:.2f}, {p['3'].y:.2f})")
    elif ref.startswith("RV"):
        sx, sy = real_board[ref]
        ck.close(f"A.shaft_from_origin.{ref}", math.hypot(sx - pl["x"], sy - pl["y"]), circuit.POT_SHAFT, 0.02, " mm")
        # the pin row direction in the front view against circuit.POT_PINS
        fx, fy = front(p["2"].x, p["2"].y)
        cx, cy = real[ref]
        dxf, dyf = fx - cx, -(fy - cy)                    # front view, y up
        want = circuit.pot_pins(ref)
        d = math.hypot(dxf, dyf)
        ck.check(f"A.pot_pin_direction.{ref}", abs(dxf / d - want[0]) < 0.01 and abs(dyf / d - want[1]) < 0.01
                 and abs(d - POT_ROW_TO_SHAFT) < 0.02,
                 f"circuit.POT_PINS {want}; routed pins at ({dxf / d:+.2f}, {dyf / d:+.2f}), {d:.2f} mm from the shaft")
        # CW end: pin 3 on 3V3A_F, pin 1 on GND_F (Alpha: CW drives the wiper towards pin 3)
        ck.check(f"A.pot_ends.{ref}", pl["nets"].get("3") == "3V3A_F" and pl["nets"].get("1") == "GND_F",
                 f"pin 1 {pl['nets'].get('1')}, pin 3 {pl['nets'].get('3')}")
    elif ref.startswith("SW"):
        side = [math.hypot(p[a].x - p[b].x, p[a].y - p[b].y) for a, b in (("1", "2"), ("3", "4"), ("1", "3"), ("2", "4"))]
        cx, cy = real_board[ref]
        led = math.hypot(p["5"].x - p["6"].x, p["5"].y - p["6"].y)
        mid = math.hypot((p["5"].x + p["6"].x) / 2 - cx, (p["5"].y + p["6"].y) / 2 - cy)
        ck.check(f"A.button_pins.{ref}", all(abs(s - BTN_SW_PITCH) < 0.02 for s in side) and abs(led - BTN_LED_PITCH) < 0.02
                 and mid < 0.02, f"switch square {[round(s, 2) for s in side]}, LED pins {led:.2f} apart, "
                                 f"{mid:.2f} off the centre")
        ck.check(f"A.button_at_origin.{ref}", math.hypot(cx - pl["x"], cy - pl["y"]) < 0.02, "")
    else:
        a, b = p["1"], p["3"]
        ck.check(f"A.led_leads_symmetric.{ref}", abs(math.hypot(a.x - p["2"].x, a.y - p["2"].y)
                                                      - math.hypot(b.x - p["2"].x, b.y - p["2"].y)) < 0.01
                 and math.hypot(p["2"].x - pl["x"], p["2"].y - pl["y"]) < 0.02, "middle lead on the origin")

# the pad model (EasyEDA's bottom-side mirror) is right if the routed tracks end on the modelled pads
ends = [t["a"] for t in FB.tracks] + [t["b"] for t in FB.tracks] + [v["c"] for v in FB.vias]
missed = []
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    for num, pad in pl["pads"].items():
        if pad.net in (None, "", "GND_F"):
            continue                              # ground pads may sit in the pour without a track end
        if not any(pad.d_point(e) < 0.01 for e in ends):
            missed.append(f"{ref}.{num}")
ck.check("A.tracks_end_on_modelled_panel_pads", not missed, f"{len(missed)} signal pads without a track end: {missed[:8]}")

# intent: PANEL_XY is where the holes are meant to be
for ref in PANEL_REFS:
    if ref in real:
        want = circuit.PANEL_XY[ref]
        d = math.hypot(real[ref][0] - want[0], real[ref][1] - want[1])
        ck.check(f"A.routed_centre_at_PANEL_XY.{ref}", d < 0.05,
                 f"PANEL_XY {want}, routed ({real[ref][0]:.3f}, {real[ref][1]:.3f}), {d:.3f} mm off")
# the PCB frame: PLACEMENT (front view, board frame) against the routed footprint origins (rear frame, mirrored)
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    xf, yf, _ = circuit.PLACEMENT[ref]
    d = math.hypot((BW - pl["x"]) - xf, pl["y"] - yf)
    ck.check(f"A.PLACEMENT_at_routed_origin.{ref}", d < 0.02,
             f"PLACEMENT ({xf}, {yf}) front view; routed origin ({BW - pl['x']:.3f}, {pl['y']:.3f}), {d:.3f} mm off")
# design.md's frame conversion: board x = panel x - 0.6, panel y from the top = 118.25 - board y
m = re.search(r"board x = panel x − ([\d.]+); panel y from the top = ([\d.]+) − board y", DESIGN)
ck.check("A.design_md_frame_conversion", m is not None and abs(float(m.group(1)) - X0) < 1e-6
         and abs(float(m.group(2)) - (H - Y0)) < 1e-6, m.group(0) if m else "not found")


def match(name, got, tol, sizes=True):
    """got: [(x, y, d)] round holes in the panel frame. Every part has exactly one hole on its real centre of
    the size design.md's table gives, and there is no other round hole."""
    used = set()
    for ref in PANEL_REFS:
        if ref not in real:
            continue
        x, y = real[ref]
        dist, i, hd = min((math.hypot(hx - x, hy - y), i, hd) for i, (hx, hy, hd) in enumerate(got))
        used.add(i)
        want_d = HOLE_TABLE[kind_of(ref)]
        ok = dist <= tol and (not sizes or abs(hd - want_d) < 0.02)
        ck.check(f"A.hole.{name}.{ref}", ok, f"want d {want_d} at ({x:.2f}, {y:.2f}); nearest d {hd:.2f}, {dist:.3f} mm off")
    extra = [got[i] for i in range(len(got)) if i not in used]
    ck.check(f"A.no_extra_holes.{name}", not extra and len(got) == len(real),
             f"{len(real)} parts, {len(got)} holes; extra {extra[:4]}")


# design.md's hole table is the size statement every representation must carry
HOLE_TABLE = {}
for kind, pat in (("pot", r"\| Pots \(×7\) \| ([\d.]+) \|"), ("jack", r"\| Jacks \(×10\) \| ([\d.]+) \|"),
                  ("ledbutton", r"\| Buttons \(×2\) \| ([\d.]+) \|"), ("led", r"\| LEDs \(×8\) \| ([\d.]+) \|")):
    mm = re.search(pat, DESIGN)
    HOLE_TABLE[kind] = float(mm.group(1)) if mm else float("nan")
ck.check("A.design_md_hole_table_read", all(v == v for v in HOLE_TABLE.values()), str(HOLE_TABLE))
ck.check("A.panel_py_HOLE = design.md table", all(abs(panel.HOLE[k] - v) < 1e-6 for k, v in HOLE_TABLE.items()),
         f"panel.HOLE {panel.HOLE}, design.md {HOLE_TABLE}")

# circuit.PANEL_XY itself and panel.features() (PLACEMENT + the offsets turned back into holes)
match("PANEL_XY", [(x, y, HOLE_TABLE[kind_of(r)]) for r, (x, y) in circuit.PANEL_XY.items()], 0.05)
feats = panel.features()
match("panel.features", [(*panel.panel_xy(hx, hy), panel.HOLE[k]) for k, r, lbl, ox, oy, hx, hy in feats], 0.01)
# hole CSV
rows = list(csv.DictReader(open(os.path.join(harness.PANEL, "plaits-panel-holes.csv"), encoding="utf-8")))
csv_holes = [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), float(r["hole_mm"]))
             for r in rows if r["kind"] != "mount"]
match("CSV", csv_holes, 0.01)
csv_mounts = [(float(r["panel_x_from_left"]), float(r["panel_y_from_top"]), r["hole_mm"]) for r in rows
              if r["kind"] == "mount"]
for r in rows:                               # the CSV's board origins against the routed origins
    if r["ref"] and r["ref"] in FB.parts:
        pl = FB.parts[r["ref"]]
        d = math.hypot(float(r["board_origin_x"]) - (BW - pl["x"]), float(r["board_origin_y"]) - pl["y"])
        ck.check(f"A.CSV_board_origin.{r['ref']}", d < 0.01, f"{d:.3f} mm from the routed origin (front view)")

SVG = "{http://www.w3.org/2000/svg}"


def svg_tree(name):
    return ET.parse(os.path.join(harness.PANEL, name)).getroot()


drill = svg_tree("plaits-panel-drill.svg")
match("drill_SVG", [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r"))) for c in drill.iter(SVG + "circle")],
      0.01)
art = svg_tree("plaits-panel.svg")
groups = {g.get("id"): g for g in art.iter(SVG + "g") if g.get("id")}
match("artwork_SVG", [(float(c.get("cx")), float(c.get("cy")), 2 * float(c.get("r")))
                      for c in groups["holes"].iter(SVG + "circle")], 0.01)
GEN = panel_pcb.PanelBoard()
match("panel_pcb_generator", [(*pcb_panel(x, y), d) for x, y, d in GEN.holes], 0.01)

# panel PCB in the routed master: round holes are layer-12 FILL circles, slots layer-12 FILL paths
pp_holes, pp_slots, pp_outline, pp_fills = [], [], None, {1: [], 5: []}
for h, p in PANEL_DOC["recs"]:
    if h["type"] == "FILL" and p["layerId"] == 12:
        if p["path"][0][0] == "CIRCLE":
            _, x, y, r = p["path"][0]
            pp_holes.append((*pcb_panel(x * MIL, y * MIL), 2 * r * MIL))
        else:
            pts = ca.flatten_path(p["path"][0] if isinstance(p["path"][0], list) else p["path"], MIL)
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            pp_slots.append(((min(xs) + max(xs)) / 2, H - (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)))
    elif h["type"] == "FILL" and p["layerId"] in (1, 5):
        pp_fills[p["layerId"]].append(p)
    elif h["type"] == "POLY" and p.get("polyType") == "BOARD_OUTLINE":
        pp_outline = p["path"]
match("routed_panel_PCB", pp_holes, 0.05)
# the same holes in the PCB frame (panel PCB: y up), straight from the routed faceplate's pads
pcb_frame = [(p["path"][0][1] * MIL, p["path"][0][2] * MIL) for h, p in PANEL_DOC["recs"]
             if h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] == "CIRCLE"]
worst = max(min(math.hypot(x - real[r][0], y - (H - real[r][1])) for x, y in pcb_frame) for r in real)
ck.check("A.routed_panel_PCB_frame (y up) = faceplate centres", worst < 0.05, f"worst {worst:.3f} mm")

# ================================================================ B. hole sizes against the parts
HT = HOLE_TABLE
ck.within("B.jack_hole_clears_thread", (HT["jack"] - JACK_THREAD_D) / 2, 0.1, 0.5, " mm a side",
          f"hole {HT['jack']} on the Ø{JACK_THREAD_D} bushing")
ck.check("B.jack_nut_covers_hole", JACK_NUT_AF >= HT["jack"] + 1.0, f"nut {JACK_NUT_AF} AF (not confirmed) vs hole {HT['jack']} + 1.0 bearing")
ck.within("B.pot_hole_clears_M7", (HT["pot"] - POT_BUSHING_D) / 2, 0.1, 0.4, " mm a side", f"hole {HT['pot']} on M7")
ck.check("B.pot_washer_covers_hole", POT_WASHER_OD >= HT["pot"] + 2.0 and POT_WASHER_ID < HT["pot"],
         f"washer Ø{POT_WASHER_ID}/{POT_WASHER_OD} on hole {HT['pot']}")
# the cap must pass freely: hole >= cap + 2 x (panel hole position +-0.1, faceplate drill +-0.1, the part's play ~0.1)
ck.within("B.button_cap_passes", (HT["ledbutton"] - BTN_CAP_D) / 2, 0.3, None, " mm a side",
          f"hole {HT['ledbutton']} round the Ø{BTN_CAP_D} cap")
ck.check("B.button_base_stays_behind", BTN_BASE > HT["ledbutton"] + 0.5,
         f"□{BTN_BASE} base (its sides {BTN_BASE}, corners {BTN_BASE * math.sqrt(2):.1f}) vs hole {HT['ledbutton']}")
ck.within("B.led_body_passes", (HT["led"] - LED_BODY_D) / 2, 0.05, None, " mm a side",
          f"hole {HT['led']} round the Ø{LED_BODY_D} body (the leads let it centre itself)")
ck.check("B.led_flange_stops_at_panel", LED_FLANGE_D > HT["led"], f"flange Ø{LED_FLANGE_D} vs hole {HT['led']}")
# the routed faceplate's own housing outline must cover the hole (else the footprint is not the part)
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None or ref.startswith("D"):
        continue
    x1, y1, x2, y2 = pl["body"]
    cx, cy = real_board[ref]
    r = HT[kind_of(ref)] / 2
    ck.check(f"B.hole_inside_housing.{ref}", x1 <= cx - r and cx + r <= x2 and y1 <= cy - r and cy + r <= y2,
             f"hole ({cx:.2f}, {cy:.2f}) r {r}; housing {tuple(round(v, 2) for v in pl['body'])}")
# and the housing outlines against the drawings (jack 9 wide, 6.0 / 4.5 round the barrel; pot 9.5 wide)
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    x1, y1, x2, y2 = pl["body"]
    cx, cy = real_board[ref]
    if ref.startswith("J"):
        ok = (abs((x2 - x1) - JACK_BODY_W) < 0.1 and abs((cy - y1) - JACK_BODY_TIP_SIDE) < 0.1
              and abs((y2 - cy) - JACK_BODY_SLEEVE_SIDE) < 0.1)
        ck.check(f"B.jack_outline = drawing.{ref}", ok,
                 f"width {x2 - x1:.2f}, tip side {cy - y1:.2f}, sleeve side {y2 - cy:.2f} (drawing 9 / 6.0 / 4.5)")
    elif ref.startswith("RV"):
        across = (y2 - y1) if circuit.pot_pins(ref)[0] else (x2 - x1)
        ck.close(f"B.pot_outline_width = drawing.{ref}", across, POT_HOUSING_W, 0.1, " mm")

# ================================================================ C. Eurorack mechanics
ck.close("C.panel_height", H, PANEL_H, 0.001, " mm")
ck.check("C.panel_width_12HP", abs(W - W12) < 0.01 and panel.HP == 12, f"Doepfer 12HP {W12}, got {W} ({panel.HP}HP)")
if pp_outline:
    _, ox_, oy_, ow, oh, *_ = pp_outline
    ck.check("C.panel_PCB_outline", abs(ow * MIL - W) < 0.01 and abs(oh * MIL - H) < 0.01 and abs(ox_) < 0.01
             and abs(oy_ * MIL - H) < 0.01, f"{ow * MIL:.3f} x {oh * MIL:.3f} from ({ox_ * MIL:.2f}, {oy_ * MIL:.2f})")
else:
    ck.check("C.panel_PCB_outline", False, "no BOARD_OUTLINE on the panel PCB")
want_mounts = sorted((x, y) for x in (MOUNT_FROM_LEFT, MOUNT_FROM_LEFT + (12 - 3) * HP_MM)
                     for y in (MOUNT_FROM_EDGE_Y, PANEL_H - MOUNT_FROM_EDGE_Y))
art_slots = [(float(r_.get("x")) + float(r_.get("width")) / 2, float(r_.get("y")) + float(r_.get("height")) / 2,
              float(r_.get("width")), float(r_.get("height"))) for r_ in groups["holes"].iter(SVG + "rect")]
drill_slots = [(float(r_.get("x")) + float(r_.get("width")) / 2, float(r_.get("y")) + float(r_.get("height")) / 2,
                float(r_.get("width")), float(r_.get("height"))) for r_ in drill.iter(SVG + "rect")
               if r_.get("stroke") == "#c00"]
gen_slots = [(x, H - y, w_, h_) for x, y, w_, h_ in GEN.slots]
for name, got in (("CSV", [(x, y) for x, y, _ in csv_mounts]), ("drill_SVG", [(x, y) for x, y, *_ in drill_slots]),
                  ("artwork_SVG", [(x, y) for x, y, *_ in art_slots]), ("panel_pcb_generator", [(x, y) for x, y, *_ in gen_slots]),
                  ("routed_panel_PCB", [(x, y) for x, y, *_ in pp_slots])):
    got = sorted((round(a, 2), round(b, 2)) for a, b in got)
    ok = len(got) == 4 and all(min(math.hypot(a[0] - b[0], a[1] - b[1]) for b in got) < 0.02 for a in want_mounts)
    ck.check(f"C.mounting_slots_at_Doepfer_positions.{name}", ok, f"want {want_mounts}, got {[(round(a, 2), round(b, 2)) for a, b in got]}")
for name, sl in (("drill_SVG", drill_slots), ("artwork_SVG", art_slots), ("routed_panel_PCB", pp_slots)):
    ok = len(sl) == 4 and all(abs(w_ - 5.5) < 0.02 and abs(h_ - 3.2) < 0.02 for *_, w_, h_ in sl)
    ck.check(f"C.slot_size_5.5x3.2_horizontal.{name}", ok, str([(round(w_, 2), round(h_, 2)) for *_, w_, h_ in sl]))
ck.check("C.slot_width = Doepfer hole d 3.2", abs(panel.SLOT_H - MOUNT_HOLE_D) < 0.01, f"{panel.SLOT_H}")
ck.check("C.screw_head_covers_slot", SCREW_HEAD_D >= panel.SLOT_H + 2 * 1.0,
         f"head Ø{SCREW_HEAD_D} on a {panel.SLOT_H} wide slot: {(SCREW_HEAD_D - panel.SLOT_H) / 2:.1f} mm bearing a side")
ck.close("C.right_slot_margin ~ left (centres symmetric within one slot play)", W - want_mounts[2][0],
         MOUNT_FROM_LEFT, (panel.SLOT_W - panel.SLOT_H) / 2, " mm")
for b in (FB, MB):
    x0_, y0_, x1_, y1_ = b.outline
    ck.check(f"C.board_size.{b.title}", abs(x1_ - x0_ - BW) < 0.01 and abs(y1_ - y0_ - BH) < 0.01,
             f"{x1_ - x0_:.2f} x {y1_ - y0_:.2f}")
ck.check("C.board_height <= 108 (max PCB 108-110)", BH <= PCB_MAX_H, f"{BH}")
ck.within("C.board_inside_tightest_rails (each side)", (RAIL_CLEAR_MIN - BH) / 2, 1.0, None, " mm",
          f"108 mm board centred in Schroff's {RAIL_CLEAR_MIN} mm")
ck.within("C.board_edge_from_panel_edge >= rail zone", Y0, RAIL_ZONE, None, " mm")
ck.within("C.board_width_inside_panel (each side)", X0, 0.3, None, " mm")
# where the boards really sit: the offset each routed panel part implies between its board position and its
# hole, which must be one offset for all and centre the board
offs = [(circuit.PANEL_XY[r][0] - (BW - real_board[r][0]), H - circuit.PANEL_XY[r][1] - real_board[r][1]) for r in real]
ox = sum(o[0] for o in offs) / len(offs)
oy = sum(o[1] for o in offs) / len(offs)
spread = max(math.hypot(o[0] - ox, o[1] - oy) for o in offs)
ck.check("C.boards_centred (offset implied by the routed panel parts)",
         spread < 0.05 and abs(ox - X0) < 0.05 and abs(oy - Y0) < 0.05,
         f"want ({X0:.2f}, {Y0:.2f}); got ({ox:.3f}, {oy:.3f}), spread {spread:.3f} mm")
for b in (FB, MB):
    worst = None
    for ref, pl in b.parts.items():
        x1, y1, x2, y2 = pl["body"]
        pads = pl["pads"].values()
        lo = min([x1] + [p.x - p.r for p in pads]), min([y1] + [p.y - p.r for p in pads])
        hi = max([x2] + [p.x + p.r for p in pads]), max([y2] + [p.y + p.r for p in pads])
        mgn = min(lo[0], lo[1], BW - hi[0], BH - hi[1])
        if worst is None or mgn < worst[0]:
            worst = (mgn, ref)
    ck.within(f"C.parts_within_board.{b.title}", worst[0], 0.0, None, " mm", f"tightest {worst[1]}")
# panel parts' housings clear of the rail zone (10 mm from the panel's top / bottom edge)
for ref in PANEL_REFS:
    pl = FB.parts.get(ref)
    if pl is None:
        continue
    x1, y1, x2, y2 = pl["body"]
    top, bot = H - Y0 - y2, H - Y0 - y1
    ck.check(f"C.housing_clear_of_rails.{ref}", top >= RAIL_ZONE and H - bot >= RAIL_ZONE, f"panel y {top:.2f} .. {bot:.2f}")
# board mounting holes: the same on both boards, = pcb.HOLES_FRONT, 3.2 mm
pcbmod = harness.load("pcb")
fh = sorted((round(x, 2), round(y, 2)) for x, y, d in FB.holes)
mh = sorted((round(x, 2), round(y, 2)) for x, y, d in MB.holes)
want_h = sorted((round(BW - x, 2), round(y, 2)) for x, y in pcbmod.HOLES_FRONT)
ck.check("C.board_holes_coincide = pcb.HOLES_FRONT", fh == mh == want_h, f"want {want_h}, faceplate {fh}, main {mh}")
ck.check("C.board_holes_3.2", all(abs(d - 3.2) < 0.02 for *_, d in FB.holes + MB.holes),
         str(sorted({round(d, 2) for *_, d in FB.holes + MB.holes})))
m = re.search(r"Three 3\.2 mm holes, front-view \(([\d.]+), ([\d.]+)\), \(([\d.]+), ([\d.]+)\)\s+and \(([\d.]+), ([\d.]+)\)", DESIGN)
dm = sorted((float(m.group(i)), float(m.group(i + 1))) for i in (1, 3, 5)) if m else None
ck.check("C.design_md_mounting_holes = boards", dm == sorted(pcbmod.HOLES_FRONT), f"design.md {dm}, pcb {sorted(pcbmod.HOLES_FRONT)}")
# 12HP width behind the panel: the boards and the breakout within the panel's width
u2 = MB.parts.get("U2")
if u2:
    x1, y1, x2, y2 = u2["body"]
    ck.check("C.breakout_within_main_board", x1 >= 0 and y1 >= 0 and x2 <= BW and y2 <= BH,
             f"U2 outline {tuple(round(v, 2) for v in u2['body'])}")

# ================================================================ D. front clearances
KS = panel.KNOB_SIZE
knob_r = {r: KNOB_D_DRAWN[KS[r]] / 2 for r in real if r.startswith("RV")}
ck.check("D.artwork_knobs = design.md 15 / 12 / 10",
         all(abs(panel.ART["knob"][s] * 2 - KNOB_D_DRAWN[s]) < 1e-6 for s in KNOB_D_DRAWN), str(panel.ART["knob"]))
bk = [(int(n), float(d)) for n, d in re.findall(r"\| (\d+) \| Knob for a T18 shaft, about ([\d.]+) mm across", BOMMD)]
want_bk = sorted((sum(1 for r in KS if KS[r] == s), KNOB_D_DRAWN[s]) for s in KNOB_D_DRAWN)
ck.check("D.bom_knobs = design.md sizes", sorted(bk) == want_bk, f"bom.md {sorted(bk)}, design.md {want_bk}")


def footprint_r(ref):
    """The front outline: knob or (wider) washer / nut corners on a pot; nut corners on a jack; cap; LED body."""
    k = kind_of(ref)
    if k == "pot":
        return max(knob_r[ref], POT_WASHER_OD / 2, POT_NUT_AC / 2)
    return {"jack": JACK_NUT_AC / 2, "ledbutton": BTN_CAP_D / 2, "led": LED_BODY_D / 2}[k]


worst = {}
for i, a in enumerate(PANEL_REFS):
    for b in PANEL_REFS[i + 1:]:
        if a not in real or b not in real:
            continue
        g = math.hypot(real[a][0] - real[b][0], real[a][1] - real[b][1]) - footprint_r(a) - footprint_r(b)
        key = tuple(sorted((kind_of(a), kind_of(b))))
        if key not in worst or g < worst[key][0]:
            worst[key] = (g, a, b)
for key, (g, a, b) in sorted(worst.items()):
    ck.within(f"D.edge_gap.{key[0]}-{key[1]}", g, MIN_GAP[key], None, " mm", f"tightest {a}-{b}")
small = [r for r in knob_r if KS[r] == "small"]
print(f"INFO  the Ø{POT_WASHER_OD:.0f} washer and the {POT_NUT_AC:.1f} mm nut corners stand out of the "
      f"Ø{KNOB_D_DRAWN['small']:.0f} knobs on {small}; the clearances above use the washer there")
# the scale arcs must show outside whatever covers the pot (knob, washer, nut corners)
for size in KNOB_D_DRAWN:
    cover = max(KNOB_D_DRAWN[size] / 2, POT_WASHER_OD / 2, POT_NUT_AC / 2)
    ck.within(f"D.scale_arc_visible.{size}", panel.ART["scale"][size] - 0.15 - cover, 0.0, None, " mm",
              f"arc r {panel.ART['scale'][size]} (0.3 line) round knob / washer / nut r {cover:.2f}")
# jack pitch for patch plugs, and the plugs against the knobs
pitch = circuit.JACK_PITCH
ck.within("D.jack_pitch_for_plugs", pitch - PLUG_D, 2.0, None, " mm between Ø9 plug grips", f"pitch {pitch}")
for j in [r for r in real if r.startswith("J")]:
    for o in real:
        if o == j or not o.startswith("RV"):
            continue
        d = math.hypot(real[j][0] - real[o][0], real[j][1] - real[o][1])
        if d < PLUG_D / 2 + knob_r[o] + 1.5:
            ck.check(f"D.plug_clear_of_knob.{j}-{o}", False, f"centres {d:.2f} mm")
# front extents within the 12HP width (neighbours' knobs come right up to the edge)
ext = min(min(real[r][0] - footprint_r(r), W - real[r][0] - footprint_r(r)) for r in real)
ck.within("D.front_parts_within_width", ext, 0.5, None, " mm to the panel's side edge")
# everything on the front between the band (10.6) and the rule (118.6), screws clear of all of it
for ref in real:
    x, y = real[ref]
    r = footprint_r(ref)
    ck.check(f"D.between_band_and_rule.{ref}", y - r >= 10.6 and y + r <= 118.6, f"y {y - r:.2f} .. {y + r:.2f}")
for mx, my in want_mounts:
    near = min((math.hypot(mx - real[r][0], my - real[r][1]) - footprint_r(r) - SCREW_HEAD_D / 2, r) for r in real)
    ck.within(f"D.screw_head_clear.({mx:.2f}, {my})", near[0], 1.0, None, " mm", f"nearest {near[1]}")

# ================================================================ E. heights and depth
gap_jack = JACK_BODY_H                       # panel rear above the faceplate, as each part would set it
gap_pot = POT_BODY_H
base_top = BTN_TOTAL_H - (BTN_CAP_TO_BASE_BOTTOM - BTN_BASE_T) - BTN_SIDE_FEET   # cap base top, feet clipped
print(f"INFO  panel rear above the faceplate: Thonkiconn {gap_jack} (+-{JACK_BODY_TOL}), Alpha {gap_pot} "
      f"(+-{POT_BODY_TOL}); LED button cap base top {base_top:.2f} with the feet clipped, "
      f"{base_top + BTN_SIDE_FEET:.2f} on its side feet, {base_top + BTN_CENTRE_FOOT:.2f} on its centre foot")
print(f"INFO  Thonkiconn height: Thonk's drawing {JACK_BODY_H}, a builder measured {JACK_BODY_H_MEASURED} (PJ301M-12); "
      f"with {JACK_BODY_H_MEASURED} the jacks, pots and button bases would agree within "
      f"{max(abs(JACK_BODY_H_MEASURED - gap_pot), abs(JACK_BODY_H_MEASURED - base_top)):.2f} mm")
ck.within("E.jack_and_pot_heights_agree", abs(gap_pot - gap_jack), None, HEIGHT_AGREE, " mm",
          f"Thonkiconn body {gap_jack}, Alpha body to shoulder {gap_pot}: the panel rests on the pots and every "
          f"jack hangs {gap_pot - gap_jack:.1f} mm below it until its nut pulls it (and the board) up")
panel_rear = max(gap_jack, gap_pot)          # the panel rests on the tallest rigid shoulder
ck.within("E.button_base_below_panel (typ)", panel_rear - base_top, 0.0, None, " mm",
          "the panel must not push the cap's square base down")
lo_rear = max(gap_pot - POT_BODY_TOL, gap_jack - JACK_BODY_TOL)   # the panel sits on the tallest part
hi_base = base_top + 0.25 + 0.2 + 0.25 + 0.1   # 14.0, 6.3, 2.5 tolerances and the measured feet
ck.within("E.button_not_held_pressed (worst case)", lo_rear - hi_base, -BTN_TRAVEL / 2, None, " mm",
          f"panel rear as low as {lo_rear:.2f} (pots at their minimum), base top up to {hi_base:.2f}; "
          f"travel {BTN_TRAVEL} (not confirmed)")
ck.check("E.design_md_button_feet_clipped", "Clip" in DESIGN and "feet" in DESIGN, "design.md tells the builder to clip the feet")
# [2026-11-14: design.md's claim is read, not assumed: until then it said 'without the feet the body sits on the
# board at Thonkiconn height', which this check failed by 0.85 mm; it now states the cap base's height, which is
# held against Thonk's drawing instead.]
_flat = " ".join(DESIGN.split())
_m_base = re.search(r"cap's square base stands (\d+(?:\.\d+)?) mm above the board", _flat)
if "at Thonkiconn height" in _flat or not _m_base:
    ck.within("E.design_md_button_at_jack_height", abs(base_top - gap_jack), None, HEIGHT_AGREE, " mm",
              f"design.md: 'without the feet the body sits on the board at Thonkiconn height'; cap base top "
              f"{base_top:.2f} vs the Thonkiconn's {gap_jack}")
else:
    ck.within("E.design_md_button_at_jack_height", abs(float(_m_base.group(1)) - base_top), None, 0.1, " mm",
              f"design.md: the cap's base {_m_base.group(1)} mm above the board; Thonk's drawing gives {base_top:.2f} "
              f"(the Thonkiconn's body {gap_jack}: the panel-first build note covers the difference)")
cap_out = base_top + (BTN_CAP_TO_BASE_BOTTOM - BTN_BASE_T) - panel_rear - PCB_T
ck.within("E.button_cap_proud_of_panel", cap_out, 1.0, None, " mm")
shaft_out = POT_SHAFT_L - PCB_T - (panel_rear - gap_pot)
ck.within("E.pot_shaft_above_panel (T18 knob needs ~10)", shaft_out, 10.0, None, " mm")
ck.within("E.pot_thread_for_washer_and_nut", POT_BUSHING_L - PCB_T - POT_WASHER_T - POT_NUT_T, 0.5, None, " mm spare")
ck.within("E.jack_thread_for_nut (jack hanging)", JACK_BUSHING_L - PCB_T - (panel_rear - gap_jack) - JACK_NUT_T, 0.5, None,
          " mm spare")
ck.within("E.jack_pins_through_board_if_pulled_up", JACK_PIN_L - (panel_rear - gap_jack) - PCB_T, 0.5, None,
          " mm of pin beyond the board when the nut pulls the jack to the panel")
# 3 mm LEDs: flange stops at the panel's rear (Ø3.8 > 3.2 hole); the dome should end near the panel front
h_lo = panel_rear + PCB_T - LED_H              # flange bottom height for the dome flush with the panel front
h_hi = panel_rear - LED_FLANGE_T               # flange against the panel's rear
print(f"INFO  3 mm LEDs: flange bottom {h_lo:.1f} (dome flush with the panel front) .. {h_hi:.1f} mm (flange against "
      f"the panel, dome {LED_H - LED_FLANGE_T - PCB_T:.1f} mm proud) above the faceplate")
ck.within("E.led_leads_long_enough", LED_LEAD_L - (h_hi + PCB_T + 1.5), 3.0, None, " mm spare")
led_note = re.search(r"LED[^.]*(standoff|spacer|stand [^.]*mm|push(ed)? (up )?into|with the panel (on|fitted))", DESIGN + BOMMD)
ck.check("E.docs_say_how_high_the_LEDs_stand", led_note is not None,
         f"the LEDs need {h_lo:.1f}-{h_hi:.1f} mm under the flange (or soldering with the panel fitted); "
         f"design.md / bom.md say {'something' if led_note else 'nothing'}")
# depth behind the panel
stack_mb = SOCKET_H + MALE_PLASTIC                    # FB to MB (mated headers; design.md "about 11 mm")
brk = SOCKET_H + MALE_PLASTIC                         # MB to the breakout: 8.5 mm sockets, the 1x4 male plastic under it
seed = SOCKET_H + MALE_PLASTIC                        # breakout to the Seed (female headers, the Seed's male pins)
# the breakout's Seed side (away from the main board): the tallest of the Seed stack, C9 / C18, U3 and J2's plug
seed_side = {"Seed": seed + SEED_PCB_T + SEED_TOP_H, "C9 / C18": BRK_CAP_L + BRK_CAP_L_TOL + 0.5,
             "U3": BRK_DCDC_H, "J2 + IDC plug": MALE_PLASTIC + IDC_PLUG_H + RIBBON_BEND}
tallest = max(seed_side, key=seed_side.get)
behind = panel_rear + PCB_T + stack_mb + PCB_T + brk + PCB_T + seed_side[tallest]
print(f"INFO  depth behind the panel: {panel_rear} panel gap + {PCB_T} faceplate + {stack_mb:.2f} headers + {PCB_T} main "
      f"board + {brk:.2f} sockets + {PCB_T} breakout + {seed_side[tallest]:.2f} on its Seed side ({tallest}; "
      f"{ {k: round(v, 2) for k, v in seed_side.items()} }) = {behind:.1f} mm")
ck.within("E.depth_behind_panel (skiff: Intellijel Palette 45.5 mm)", behind, None, SKIFF_DEPTH, " mm")
# verifier 2026-11-13: was E.breakout_underside_caps_fit_socket_gap, which put C9 / C18 in the main-board gap. They
# are on the breakout's Seed side (see the constants). What faces the main board is low: the SMD parts and the
# through-hole parts' tails; nothing of the main board stands under the breakout (pcb H.under_breakout)
under_brk = [r for r, pl in MB.parts.items() if not pl["bottom"] and r != "U2"
             and not (pl["body"][2] < MB.parts["U2"]["body"][0] or pl["body"][0] > MB.parts["U2"]["body"][2]
                      or pl["body"][3] < MB.parts["U2"]["body"][1] or pl["body"][1] > MB.parts["U2"]["body"][3])]
ck.within("E.breakout_underside_fits_its_gap", brk - max(BRK_SMD_H, BRK_TAIL_OUT), 1.0, None, " mm",
          f"tallest on the breakout's main-board side {max(BRK_SMD_H, BRK_TAIL_OUT)} mm (SMD {BRK_SMD_H}, tails "
          f"{BRK_TAIL_OUT}) in the {brk:.2f} mm gap; main-board parts under it: {under_brk}; C9 / C18 "
          f"({BRK_CAP_L}+{BRK_CAP_L_TOL}), U3 ({BRK_DCDC_H}) and J2 are on the Seed side")

# ================================================================ F. labels
# routed panel PCB: silk POLYs (layer 3) and STRINGs, in the panel frame
silk_polys, strings = [], []
for h, p in PANEL_DOC["recs"]:
    if h["type"] == "POLY" and p.get("layerId") == 3:
        pts = [pcb_panel(x, y) for x, y in ca.flatten_path(p["path"], MIL)]
        silk_polys.append((pts, p["width"] * MIL))
    elif h["type"] == "STRING":
        size = p["fontSize"] * MIL / 0.9                 # panel_pcb.text(): fontSize = 0.9 x the artwork size
        F = p["fontSize"] * MIL
        # EasyEDA's measured font (panel_pcb.INK_*): the letters run 0.2 F .. 0.885 F above the origin, so "base" is
        # the letters' bottom and "h" their height; "w" the ink width (until 2026-11-14 the origin was taken as the
        # baseline, fontSize as the height and CHAR_W x len as the width)
        strings.append({"text": p["text"], "x0": p["x"] * MIL, "base": H - p["y"] * MIL - panel_pcb.INK_BOTTOM * F,
                        "h": (panel_pcb.INK_TOP - panel_pcb.INK_BOTTOM) * F,
                        "w": panel_pcb.ink_width(p["text"], size, p["strokeWidth"] * MIL), "stroke": p["strokeWidth"] * MIL,
                        "angle": p["angle"], "layer": p["layerId"], "size": size, "reverse": p.get("reverse", False),
                        "y_origin": H - p["y"] * MIL})
ck.check("F.routed_silk = generator (counts)", len(silk_polys) == len(GEN.silk_lines) + len(GEN.arcs)
         and len(strings) == len(GEN.strings),
         f"routed {len(silk_polys)} silk POLYs / {len(strings)} STRINGs, generator {len(GEN.silk_lines) + len(GEN.arcs)} / "
         f"{len(GEN.strings)}")
gen_str = sorted((s, round(x, 2), round(y, 2)) for x, y, s, size, w_ in GEN.strings)
rt_str = sorted((s["text"], round(s["x0"], 2), round(H - s["y_origin"], 2)) for s in strings)
ck.check("F.routed_strings = generator (text and place)", gen_str == rt_str,
         f"only routed {sorted(set(rt_str) - set(gen_str))[:4]}, only generator {sorted(set(gen_str) - set(rt_str))[:4]}")
# artwork texts (the icon glyph texts sit in translated groups: kept apart)
icon_texts = set()
for g in art.iter(SVG + "g"):
    if g.get("transform"):
        for t in g.iter(SVG + "text"):
            icon_texts.add(id(t))
art_texts = []
for gid in ("silk", "copper"):
    for t in groups[gid].iter(SVG + "text"):
        if id(t) in icon_texts:
            continue
        art_texts.append({"text": t.text.strip(), "x": float(t.get("x")), "base": float(t.get("y")),
                          "size": float(t.get("font-size")), "anchor": t.get("text-anchor"), "cls": t.get("class") or "",
                          "group": gid})
words_art = sorted(t["text"] for t in art_texts if t["text"] not in ("–", "+"))
words_pcb = sorted(s["text"] for s in strings if (s["text"], s["x0"]) not in
                   {(s2["text"], s2["x0"]) for s2 in strings if s2["h"] < 1.2})   # the FM glyph inside its icon ring
ck.check("F.artwork_and_PCB_same_words", words_art == words_pcb,
         f"only artwork {sorted(set(words_art) - set(words_pcb))}, only PCB {sorted(set(words_pcb) - set(words_art))}")
ck.check("F.artwork_minus_plus_are_PCB_lines", sum(1 for t in art_texts if t["text"] in ("–", "+")) == 6, "3 x '–' and '+'")


def pcb_word_at(x, y, dx=0.8, lo=-0.5, hi=0.5):
    """Routed panel words whose estimated centre is within dx of x and whose baseline is within lo..hi of y."""
    return [s for s in strings if abs(s["x0"] + s["w"] / 2 - x) < dx and lo <= s["base"] - y <= hi and s["h"] >= 1.2]


def art_word_at(x, y, dx=0.05, lo=-0.05, hi=0.05):
    return [t for t in art_texts if t["anchor"] == "middle" and abs(t["x"] - x) < dx and lo <= t["base"] - y <= hi]


labels = {r: lbl for r, lbl, *_ in circuit.JACKS}
labels.update({r: lbl for r, lbl, *_ in circuit.POTS})
TIP_WORD = {"CV_MODEL_F": "MODEL", "CV_HARMO_F": "HARMO", "CV_TRIG_F": "TRIG", "CV_LEVEL_F": "LEVEL", "CV_VOCT_F": "V/OCT",
            "OUT_F": "OUT", "AUX_F": "AUX"}
WIPER_WORD = {"POT_FREQ_F": "FREQUENCY", "POT_HARMO_F": "HARMONICS", "POT_TIMBRE_F": "TIMBRE", "POT_MORPH_F": "MORPH",
              "ATT_FM_F": "FM"}
GUIDED = {}                                   # jack / attenuverter -> what names it, through a dotted guide
for ref in [r for r in real if r.startswith("J")]:
    x, y = real[ref]
    tip = FB.parts[ref]["nets"].get("3")
    want = TIP_WORD.get(tip)
    above_pcb = pcb_word_at(x, y - panel.ART["nut"] - 1.6)
    above_art = art_word_at(x, y - panel.ART["nut"] - 1.6)
    if want:
        ok = ([s["text"] for s in above_pcb] == [want] and [t["text"] for t in above_art] == [want]
              and labels[ref] == want)
        ck.check(f"F.jack_word.{ref}", ok, f"tip {tip}: want '{want}' (circuit.JACKS '{labels[ref]}'); PCB "
                                          f"{[s['text'] for s in above_pcb]}, artwork {[t['text'] for t in above_art]}")
    else:
        GUIDED[ref] = tip
# the three CV jacks without a word (TIMBRE, FM, MORPH, as on Plaits): a dotted guide from the attenuverter
# whose wiper is that CV's attenuverter, down to the jack


def dash_count(pts, pitch=1.0):
    """How many dashes panel_pcb.dots() puts on the polyline pts (one per pitch, both ends included)."""
    return sum(max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / pitch)) + 1 for a, b in zip(pts, pts[1:]))


def dashes_along(pts, tol=0.15):
    """Routed silk dashes (short POLYs) whose middle lies on the polyline pts (panel frame)."""
    n = 0
    for poly, w_ in silk_polys:
        if len(poly) != 2 or math.hypot(poly[1][0] - poly[0][0], poly[1][1] - poly[0][1]) > 0.2:
            continue
        mx, my = (poly[0][0] + poly[1][0]) / 2, (poly[0][1] + poly[1][1]) / 2
        if any(ca.d_point_seg((mx, my), a, b) < tol for a, b in zip(pts, pts[1:])):
            n += 1
    return n


A_ = panel.ART
pos = {r: (kind_of(r), "", *real[r]) for r in real}
for att, jack in panel.ATT_TO_JACK.items():
    ax, ay = real[att]
    jx, jy = real[jack]
    y0, top = ay + A_["knob"]["small"] + 0.9, jy - A_["nut"] - 0.9
    path = [(ax, y0), (ax, top)] if abs(jx - ax) < 0.3 else [(ax, y0), (ax, y0 + 1.8), (jx, top - 1.6), (jx, top)]
    n = dashes_along(path)
    stem = FB.parts[att]["nets"].get("2", "").replace("ATT_", "CV_")
    ok = n >= 0.8 * dash_count(path) and FB.parts[jack]["nets"].get("3") == stem and GUIDED.pop(jack, None) is not None
    ck.check(f"F.guide_att_to_jack.{att}-{jack}", ok, f"{n} of {dash_count(path)} dashes; {att} wiper {FB.parts[att]['nets'].get('2')}, "
                                                    f"{jack} tip {FB.parts[jack]['nets'].get('3')}")
ck.check("F.every_jack_named (word or guide)", not GUIDED, f"unnamed: {GUIDED}")
# pots: the four main knobs' words under them, FM over its attenuverter, TIMBRE / MORPH guided to theirs
for ref in [r for r in real if r.startswith("RV")]:
    wiper = FB.parts[ref]["nets"].get("2")
    x, y = real[ref]
    if KS[ref] != "small":
        lx, ly = panel.label_xy(pos, ref)
        got_p = [s["text"] for s in pcb_word_at(lx, ly)]
        got_a = [t["text"] for t in art_word_at(lx, ly)]
        want = WIPER_WORD.get(wiper)
        ck.check(f"F.knob_word.{ref}", got_p == [want] and got_a == [want] and labels[ref] == want,
                 f"wiper {wiper}: want '{want}' (circuit.POTS '{labels[ref]}'); PCB {got_p}, artwork {got_a}")
    elif wiper == "ATT_FM_F":
        fy = y - A_["scale"]["small"] - 1.7
        got_p = [s["text"] for s in pcb_word_at(x, fy)]
        ck.check(f"F.knob_word.{ref}", got_p == ["FM"] and [t["text"] for t in art_word_at(x, fy)] == ["FM"],
                 f"wiper {wiper}: PCB {got_p}")
for knob, att in panel.KNOB_TO_ATT.items():
    lx, ly = panel.label_xy(pos, knob)
    ax, ay = real[att]
    gp = [(lx, ly + 1.2), (lx, ly + 3.2), (ax, ly + 5.0), (ax, ay - A_["scale"]["small"] - 1.0)]
    n = dashes_along(gp)
    a, b = FB.parts[knob]["nets"].get("2", ""), FB.parts[att]["nets"].get("2", "")
    ck.check(f"F.guide_knob_to_att.{knob}-{att}", n >= 0.8 * dash_count(gp) and a.split("_")[1] == b.split("_")[1],
             f"{n} dashes; {knob} {a}, {att} {b}")
# buttons: the left one (wrench, green bank) is BTN_A, the right one (levels disc, red bank) BTN_B; the icon
# columns stand under them, one icon row per LED
sw1, sw2 = real["SW1"], real["SW2"]
ck.check("F.buttons_left_A_right_B", sw1[0] < sw2[0] and FB.parts["SW1"]["nets"].get("3") == "BTN_A_F"
         and FB.parts["SW2"]["nets"].get("3") == "BTN_B_F" and "green" in circuit.BUTTONS[0][1],
         f"SW1 x {sw1[0]} {FB.parts['SW1']['nets'].get('3')}, SW2 x {sw2[0]} {FB.parts['SW2']['nets'].get('3')}")
rings = [(c[0], c[1], c[2], w_) for *_, w_, c in GEN.arcs]
for k in range(8):
    ref = f"D{k + 1}"
    y = real[ref][1]
    thick = [rg for rg in rings if abs(rg[0] - sw1[0]) < 0.01 and abs(rg[1] - y) < 0.01 and abs(rg[2] - A_["icon"]) < 0.01]
    thin = [rg for rg in rings if abs(rg[0] - sw2[0]) < 0.01 and abs(rg[1] - y) < 0.01 and abs(rg[2] - A_["icon"]) < 0.01]
    ok = thick and thin and min(w_ for *_, w_ in thick) > max(w_ for *_, w_ in thin)
    ck.check(f"F.icon_row_on_LED.{ref}", bool(ok), f"green ring {len(thick)}, red ring {len(thin)} pieces at y {y:.2f}")
# the CSV and the drill template carry circuit.py's labels
for r_ in rows:
    if r_["ref"]:
        want = {**labels, **{r: l for r, l, *_ in circuit.BUTTONS}, **{r: l for r, l, *_ in circuit.LEDS}}.get(r_["ref"])
        ck.check(f"F.CSV_label.{r_['ref']}", r_["label"] == want, f"'{r_['label']}' vs circuit '{want}'")


# no word over a hole or under a knob, washer, nut or cap (boxes: PCB from panel_pcb's estimate, artwork from
# Arial Bold / Georgia italic average widths)
def covers(box, what):
    out = []
    for ref in real:
        cx, cy = real[ref]
        r = footprint_r(ref)
        dxx = max(box[0] - cx, 0, cx - box[2])
        dyy = max(box[1] - cy, 0, cy - box[3])
        if math.hypot(dxx, dyy) < r + 0.2:
            out.append(f"'{what}' within {math.hypot(dxx, dyy):.2f} of {ref} (covered to r {r:.2f})")
    return out


bad = []
for s in strings:
    if s["h"] < 1.2:
        continue
    bad += covers((s["x0"], s["base"] - s["h"], s["x0"] + s["w"], s["base"]), s["text"])
ck.check("F.PCB_words_clear_of_parts", not bad, "; ".join(bad[:4]))
bad = []
for t in art_texts:
    if t["text"] in ("Orchid", "Macro oscillator"):
        continue
    w_ = 0.68 * t["size"] * len(t["text"])
    x0_ = {"middle": t["x"] - w_ / 2, "start": t["x"], "end": t["x"] - w_}[t["anchor"]]
    bad += covers((x0_, t["base"] - 0.72 * t["size"], x0_ + w_, t["base"]), t["text"])
ck.check("F.artwork_words_clear_of_parts", not bad, "; ".join(bad[:4]))
# silk sizes against JLCPCB
small_txt = [(s["text"], round(s["h"], 2), round(s["stroke"], 3)) for s in strings
             if s["h"] < SILK_MIN_TEXT_H or s["stroke"] < SILK_MIN_W]
ck.check("F.silk_text_height_and_stroke >= JLCPCB minimum", not small_txt,
         f"min height {SILK_MIN_TEXT_H}, stroke {SILK_MIN_W}: {small_txt}")
thin_lines = sorted({round(w_, 3) for _, w_ in silk_polys if w_ < SILK_MIN_W})
ck.check("F.silk_line_width >= JLCPCB minimum", not thin_lines, f"{thin_lines}")
# silk clear of the holes and slots (the fab clips it, or it rides the hole edge)
hole_c = [(x, y, d / 2) for x, y, d in pp_holes]
near = []
for poly, w_ in silk_polys:
    for a, b in zip(poly, poly[1:]):
        for hx, hy, hr in hole_c:
            dd = ca.d_point_seg((hx, hy), a, b) - w_ / 2 - hr
            if dd < SILK_HOLE_CLEAR:
                near.append((round(dd, 2), round(hx, 1), round(hy, 1)))
for s in strings:
    for hx, hy, hr in hole_c:
        dxx = max(s["x0"] - hx, 0, hx - s["x0"] - s["w"])
        dyy = max(s["base"] - s["h"] - hy, 0, hy - s["base"])
        if math.hypot(dxx, dyy) - hr < SILK_HOLE_CLEAR:
            near.append((s["text"], round(hx, 1), round(hy, 1)))
ck.check("F.silk_clear_of_holes", not near, f"{len(near)} pieces: {sorted(set(near))[:5]}")
# the OUT / AUX band: one copper FILL and one mask-opening FILL of the same shape, cleared 0.4 mm round the holes
bands = {L: [p for p in pp_fills[L] if len(p["path"]) > 1 or
             min(q[1] for q in ca.flatten_path(p["path"][0], MIL)) > H - 118.6] for L in (1, 5)}
band_fill = {L: [p for p in pp_fills[L] if len(p["path"]) > 1] for L in (1, 5)}
# the mask opening is the copper's shape plus a hole round each knocked-out label (panel_pcb.knock_paths)
n_cu = len(band_fill[1][0]["path"]) if band_fill[1] else 0
ok = len(band_fill[1]) == 1 and len(band_fill[5]) == 1 and band_fill[1][0]["path"] == band_fill[5][0]["path"][:n_cu]
ck.check("F.band_copper = band mask opening (+ the knock-out holes)", ok,
         f"{len(band_fill[1])} copper, {len(band_fill[5])} mask band fills")
if band_fill[1]:
    paths = [ca.flatten_path(pth, MIL) for pth in band_fill[1][0]["path"]]
    outline = [pcb_panel(x, y) for x, y in paths[0]]
    (bx_, by_, bw_, bh_, brx), cuts = panel.band(pos)
    xs, ys = [q[0] for q in outline], [q[1] for q in outline]
    ck.check("F.band_outline = panel.band()", abs(min(xs) - bx_) < 0.02 and abs(max(xs) - bx_ - bw_) < 0.02
             and abs(min(ys) - by_) < 0.02 and abs(max(ys) - by_ - bh_) < 0.02,
             f"routed x {min(xs):.2f}..{max(xs):.2f} y {min(ys):.2f}..{max(ys):.2f}; panel.band {bx_:.2f}+{bw_:.2f}, "
             f"{by_:.2f}+{bh_}")

    def area(pts):
        return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2

    ck.check("F.band_winding (outline CW, cutouts CCW: nonzero rule leaves them empty)",
             area(paths[0]) < 0 and all(area(q) > 0 for q in paths[1:]),
             f"outline {area(paths[0]):.1f}, cutouts {[round(area(q), 1) for q in paths[1:]]} mm² (PCB frame, y up)")
    holes_in = []
    for q in paths[1:]:
        qx, qy = [p_[0] for p_ in q], [p_[1] for p_ in q]
        cx, cy = (min(qx) + max(qx)) / 2, (min(qy) + max(qy)) / 2
        rr = (max(qx) - min(qx) + max(qy) - min(qy)) / 4
        holes_in.append((*pcb_panel(cx, cy), rr))
    for ref in panel.OUTPUTS:
        x, y = real[ref]
        hit = [c for c in holes_in if math.hypot(c[0] - x, c[1] - y) < 0.05]
        ck.check(f"F.band_masked_ring_0.4.{ref}", len(hit) == 1 and abs(hit[0][2] - HT["jack"] / 2 - 0.4) < 0.02,
                 f"cutout {[(round(c[0], 2), round(c[1], 2), round(c[2], 3)) for c in hit]} round the Ø{HT['jack']} hole")
    ck.check("F.band_cutouts_only_for_its_jacks", len(holes_in) == len(panel.OUTPUTS), f"{len(holes_in)} cutouts")
    # every other hole 0.3 mm or more from the band copper (EasyEDA's copper-to-slot rule)
    gap = min(max(bx_ - (x + HT[kind_of(r)] / 2), x - HT[kind_of(r)] / 2 - (bx_ + bw_),
                  by_ - (y + HT[kind_of(r)] / 2), y - HT[kind_of(r)] / 2 - (by_ + bh_))
              for r, (x, y) in real.items() if r not in panel.OUTPUTS)
    ck.within("F.band_clear_of_other_holes", gap, 0.3, None, " mm")
    ck.within("F.band_clear_of_panel_edge", min(bx_, W - bx_ - bw_, by_, H - by_ - bh_), 0.3, None, " mm")
    # OUT / AUX: words over bare gold. JLCPCB clips silk over exposed copper (as over pads); the artwork knocks the
    # letters out of the copper instead (class cu-text): the PCB does not do what the artwork shows
    on_band = [s for s in strings if s["text"] in ("OUT", "AUX")]
    over_cu = [s["text"] for s in on_band if s["layer"] == 3 and bx_ < s["x0"] and s["x0"] + s["w"] < bx_ + bw_
               and by_ < s["base"] - s["h"] and s["base"] < by_ + bh_]
    ck.check("F.OUT_AUX_not_silk_on_bare_copper", not over_cu,
             f"{over_cu} are silk STRINGs on the bare-gold band (the artwork knocks them out of the copper)")
    # since 2026-11-14 they are knocked out of the band's mask: a reverse STRING on the mask layer over a hole in the
    # band's mask opening, the hole round the letters and inside the reverse box (panel_pcb.KNOCK_*)
    mask_holes = []
    if band_fill[5]:
        for q in band_fill[5][0]["path"][n_cu:]:
            pts = [pcb_panel(x, y) for x, y in ca.flatten_path(q, MIL)]
            mask_holes.append((min(a for a, _ in pts), min(b for _, b in pts), max(a for a, _ in pts), max(b for _, b in pts)))
    for s in on_band:
        box = (s["x0"], s["base"] - s["h"], s["x0"] + s["w"], s["base"])       # panel frame, y down
        hole = [hh for hh in mask_holes if hh[0] < box[0] and hh[1] < box[1] and box[2] < hh[2] and box[3] < hh[3]]
        exp = 0.0
        ck.check(f"F.{s['text']}_knocked_out_of_the_band_mask", s["layer"] == 5 and s["reverse"] and len(hole) == 1
                 and all(abs(v) < 0.37 for v in (hole[0][0] - box[0] + panel_pcb.KNOCK_MARGIN,
                                                  box[2] - hole[0][2] + panel_pcb.KNOCK_MARGIN)) if hole else False,
                 f"layer {s['layer']}, reverse {s['reverse']}, mask holes round it: {len(hole)}")
    ck.check("F.design_md_fab_note_silk_on_copper", "silkscreen over bare copper" in DESIGN.replace("\n", " "), "")

# ================================================================ G. the house frame (panel.md)
title = next((t for t in art_texts if t["text"] == A_["title"]), None)
sub = next((t for t in art_texts if t["text"] == A_["subtitle"]), None)
ck.check("G.Garden_name", A_["title"] == "Orchid" and A_["subtitle"] == "Macro oscillator",
         f"{A_['title']} / {A_['subtitle']} (panel.md: plaits -> Orchid, Macro oscillator)")
ck.check("G.artwork_title serif 5.2 start x 12.0 baseline 7.4", title is not None and title["anchor"] == "start"
         and abs(title["x"] - 12.0) < 0.01 and abs(title["base"] - 7.4) < 0.01 and title["size"] == 5.2
         and "serif" in title["cls"], str(title))
ck.check("G.artwork_subtitle 2.1 end x W-12 baseline 6.6", sub is not None and sub["anchor"] == "end"
         and abs(sub["x"] - (W - 12.0)) < 0.01 and abs(sub["base"] - 6.6) < 0.01 and sub["size"] == 2.1, str(sub))
silk_g = groups["silk"]
lines = [(ln, (float(ln.get("x1")), float(ln.get("y1")), float(ln.get("x2")), float(ln.get("y2")))) for ln in silk_g.iter(SVG + "line")]
for yb in (9.6, 10.6):
    ok = any(abs(c[1] - yb) < 0.01 and abs(c[3] - yb) < 0.01 and abs(c[0] - 3) < 0.01 and abs(c[2] - (W - 3)) < 0.01
             and "dots" in (ln.get("class") or "") for ln, c in lines)
    ck.check(f"G.artwork_dotted_band.y{yb}", ok, "")
ok = any(abs(c[1] - 118.6) < 0.01 and abs(c[3] - 118.6) < 0.01 and abs(c[0] - 3) < 0.01 and abs(c[2] - (W - 3)) < 0.01
         and ln.get("stroke-width") == "0.3" for ln, c in lines)
ck.check("G.artwork_rule 0.3 at y 118.6, x 3..W-3", ok, "")
# the frame is the house one: the same numbers in every module's panel generator
src = harness.text("hardware", "tools", "panel.py")
# (title, band, rule; the subtitle is checked against panel.md above: on 4HP it moves under the band). Only the
# generators of the house style count (the ones with ART titles; the old plaitsy/ stripboard project has none).
FRAME_TOKENS = (r"12\.0, 7\.4", r"\b9\.6\b", r"\b10\.6\b", r"\b118\.6\b")
others = []
for mod in sorted(os.listdir(harness.REPO)):
    fp_ = os.path.join(harness.REPO, mod, "hardware", "tools", "panel.py")
    if mod != "plaits" and os.path.exists(fp_):
        t_ = open(fp_, encoding="utf-8").read()
        if '"title"' in t_:
            others.append((mod, all(re.search(tok, t_) for tok in FRAME_TOKENS)))
ck.check("G.frame_numbers = the other modules' generators",
         all(re.search(tok, src) for tok in FRAME_TOKENS) and others and all(ok_ for _, ok_ in others),
         f"plaits + {len(others)} others; differing: {[m_ for m_, ok_ in others if not ok_]}")
# Georgia italic / Arial Bold advance widths (font metrics, em): the title must end 1.5 mm before the function line
GEORGIA_I = {"O": 0.74, "r": 0.43, "c": 0.45, "h": 0.57, "i": 0.30, "d": 0.56}          # approximate
ARIAL_B = {"M": 0.833, "a": 0.556, "c": 0.556, "r": 0.389, "o": 0.611, " ": 0.278, "s": 0.556, "i": 0.278,
           "l": 0.278, "t": 0.333}
t_end = 12.0 + 5.2 * sum(GEORGIA_I.get(ch, 0.6) for ch in A_["title"])
s_start = W - 12.0 - 2.1 * sum(ARIAL_B.get(ch, 0.6) for ch in A_["subtitle"])
ck.within("G.artwork_title_ends_1.5_before_subtitle", s_start - t_end, 1.5, None, " mm",
          f"title to {t_end:.1f}, subtitle from {s_start:.1f}")
pt = next((s for s in strings if s["text"] == A_["title"]), None)
ps = next((s for s in strings if s["text"] == A_["subtitle"]), None)
ck.check("G.PCB_title at x 12.0 baseline 7.4", pt is not None and abs(pt["x0"] - 12.0) < 0.02 and abs(pt["base"] - 7.4) < 0.02,
         f"{(pt['x0'], pt['base']) if pt else None}")
ck.check("G.PCB_subtitle ends x W-12 (estimated) baseline 6.6", ps is not None and abs(ps["x0"] + ps["w"] - (W - 12)) < 0.05
         and abs(ps["base"] - 6.6) < 0.02, f"{(round(ps['x0'] + ps['w'], 2), ps['base']) if ps else None}")
if pt and ps:
    # every lower-case letter taken as wide as a capital (0.64 F, measured on capitals and digits only): an upper
    # bound on the widths, so this asks only that they cannot overlap; the artwork's 1.5 mm is checked above
    ck.within("G.PCB_title_clear_of_subtitle (EasyEDA's measured font)", ps["x0"] - (pt["x0"] + pt["w"]), 0.0, None,
              " mm", f"title STRING to {pt['x0'] + pt['w']:.1f}, subtitle STRING from {ps['x0']:.1f}; same line "
                     f"(baselines {pt['base']:.2f} / {ps['base']:.2f}); lower case is measured as 0.64 F, an upper bound")
for yb in (9.6, 10.6):
    n = dashes_along([(3, yb), (W - 3, yb)], 0.05)
    ck.within(f"G.PCB_dotted_band.y{yb}", n, 50, None, " dashes")
rule = [w_ for poly, w_ in silk_polys if len(poly) == 2 and all(abs(q[1] - 118.6) < 0.01 for q in poly)
        and abs(min(q[0] for q in poly) - 3) < 0.01 and abs(max(q[0] for q in poly) - (W - 3)) < 0.01]
ck.check("G.PCB_rule 0.3 at y 118.6", len(rule) == 1 and abs(rule[0] - 0.3) < 0.005, f"{rule}")
# the gold mark: the art's copper path and the panel PCB's FILLs (layer 1 + 5, each closed, no net)
mk = [pth for pth in silk_g.iter(SVG + "path") if (pth.get("class") or "") == "copper"]
if ck.check("G.artwork_mark_present", len(mk) == 1, f"{len(mk)} copper paths in #silk"):
    nums = [float(v) for v in re.findall(r"-?\d+\.?\d*", mk[0].get("d"))]
    xs, ys = nums[0::2], nums[1::2]
    ck.close("G.artwork_mark_height", max(ys) - min(ys), 4.1, 0.1, " mm")
    ck.close("G.artwork_mark_top (1.6 under the rule's lower edge 118.75)", min(ys), 118.75 + 1.6, 0.1, " mm")
    ck.close("G.artwork_mark_centred", (min(xs) + max(xs)) / 2, W / 2, 0.1, " mm")
marks = {L: [p for p in pp_fills[L] if len(p["path"]) == 1] for L in (1, 5)}
polys_m = mushroom.polygons(W)
ok = (len(marks[1]) == len(marks[5]) == len(polys_m)
      and sorted(str(p["path"]) for p in marks[1]) == sorted(str(p["path"]) for p in marks[5]))
ck.check("G.PCB_mark copper = mask opening, one FILL per polygon", ok,
         f"{len(marks[1])} copper, {len(marks[5])} mask, mushroom.py {len(polys_m)} polygons")
ck.check("G.PCB_mark_no_net", all(p.get("netName", "") == "" for L in (1, 5) for p in marks[L]), "")
ck.check("G.PCB_mark_paths_closed", all(p["path"][0][:2] == p["path"][0][-2:] for L in (1, 5) for p in marks[L]),
         "every FILL path ends on its first point (panel.md)")
if marks[1]:
    pts = [pcb_panel(x, y) for p in marks[1] for x, y in ca.flatten_path(p["path"][0], MIL)]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    ck.close("G.PCB_mark_top", min(ys), 118.75 + 1.6, 0.1, " mm")
    ck.close("G.PCB_mark_height", max(ys) - min(ys), 4.1, 0.1, " mm")
    ck.close("G.PCB_mark_centred", (min(xs) + max(xs)) / 2, W / 2, 0.1, " mm")
    ck.within("G.PCB_mark_clear_of_bottom_screws", min(abs(x - mx) for x in xs for mx, my in want_mounts if my > 100)
              - SCREW_HEAD_D / 2, 1.0, None, " mm")

# ================================================================ H. design.md figures, Plaits
D_ = DESIGN
m = re.search(r"x ([\d.]+) / ([\d.]+), ([\d.]+) mm apart", D_)
ck.check("H.design_md_buttons", m is not None and abs(float(m.group(1)) - sw1[0]) < 0.05 and abs(float(m.group(2)) - sw2[0]) < 0.05
         and abs(float(m.group(3)) - (sw2[0] - sw1[0])) < 0.05, m.group(0) if m else "not found")
m = re.search(r"8 LEDs at x ([\d.]+), pitch ([\d.]+) \(([\d.]+) … ([\d.]+)\), icons at ±([\d.]+)", D_)
leds = [real[f"D{k + 1}"] for k in range(8)]
ok = m is not None and all(abs(x - float(m.group(1))) < 0.05 for x, _ in leds) \
    and all(abs((leds[k + 1][1] - leds[k][1]) - float(m.group(2))) < 0.05 for k in range(7)) \
    and abs(leds[0][1] - float(m.group(3))) < 0.05 and abs(leds[7][1] - float(m.group(4))) < 0.05 \
    and abs(sw2[0] - leds[0][0] - float(m.group(5))) < 0.05 and abs(leds[0][0] - sw1[0] - float(m.group(5))) < 0.05
ck.check("H.design_md_LED_column_and_icons", ok, m.group(0) if m else "not found")
for pat, refs in ((r"([\d.]+)   FREQUENCY \(([\d.]+)\)\s+HARMONICS \(([\d.]+)\)", ("RV1", "RV2")),
                  (r"([\d.]+)   TIMBRE \(([\d.]+)\)\s+MORPH \(([\d.]+)\)", ("RV3", "RV4"))):
    m = re.search(pat, D_)
    ok = m is not None and all(abs(real[r][1] - float(m.group(1))) < 0.05 for r in refs) \
        and abs(real[refs[0]][0] - float(m.group(2))) < 0.05 and abs(real[refs[1]][0] - float(m.group(3))) < 0.05
    ck.check(f"H.design_md_row.{refs[0]}-{refs[1]}", ok, m.group(0) if m else "not found")
m = re.search(r"([\d.]+)   att \(([\d.]+)\)   FM att \(([\d.]+)\)   att \(([\d.]+)\)", D_)
ok = m is not None and all(abs(real[r][1] - float(m.group(1))) < 0.05 for r in ("RV5", "RV6", "RV7")) \
    and all(abs(real[r][0] - float(m.group(i))) < 0.05 for r, i in (("RV5", 2), ("RV6", 3), ("RV7", 4)))
ck.check("H.design_md_row.attenuverters", ok, m.group(0) if m else "not found")
m = re.search(r"([\d.]+)   MODEL  TIMBRE  FM  MORPH  HARMO\s+jacks x = ([\d.]+) \+ ([\d.]+) k", D_)
m2 = re.search(r"([\d.]+)   TRIG   LEVEL  V/OCT  \[OUT  AUX\]", D_)
ok = m is not None and m2 is not None and all(
    abs(real[f"J{i + 1}"][0] - (float(m.group(2)) + float(m.group(3)) * (i % 5))) < 0.05
    and abs(real[f"J{i + 1}"][1] - float((m if i < 5 else m2).group(1))) < 0.05 for i in range(10))
ck.check("H.design_md_jack_rows", ok, f"{m.group(0) if m else None} / {m2.group(0) if m2 else None}")
ck.check("H.design_md_jack_pitch = circuit", m is not None and abs(float(m.group(3)) - circuit.JACK_PITCH) < 1e-6
         and abs(circuit.LED_PITCH - 5.3) < 1e-6, "")
m = re.search(r"centres 3 mm from the top and bottom\s+edge, ([\d.]+) and ([\d.]+) mm from the left", D_)
ok = m is not None and abs(float(m.group(1)) - want_mounts[0][0]) < 0.01 and abs(float(m.group(2)) - want_mounts[2][0]) < 0.01
ck.check("H.design_md_mounting_slots", ok and "5.5 × 3.2" in D_, m.group(0).replace(chr(10), " ") if m else "not found")
ck.check("H.design_md_panel_and_board_size", "60.6 × 128.5" in D_ and "59.4 × 108" in D_, "")
ck.check("H.differences_black_panel_white_silk", re.search(r"black mask, white silk, ENIG", BOMMD) is not None
         and "Black panel with white silk" in D_, "design.md 'Black panel with white silk' and bom.md's panel line")
ck.check("H.differences_thonk_LED_buttons", "Thonk low-profile LED button" in BOMMD and "Thonk LED buttons" in D_, "")
# Plaits' own panel (Mutable Instruments, github.com/pichenettes/eurorack plaits/hardware_design/panel/plaits_v50.ai,
# a PDF; read 2026-11-13): hole circles' centres in panel mm from the top-left (the drawing's page is 60.60 x 128.50).
# Verifier 2026-11-13: re-listed the circles with pdfcircles.py; OUT / AUX ARE drawn as circles there, Ø6.51 / 6.50
# at (41.76, 111.09) and (53.21, 111.09), and now compared too.
PLAITS = {
    "SW1": (25.86, 17.09), "SW2": (34.76, 17.09),
    "RV1": (12.23, 29.19), "RV2": (48.41, 29.19), "RV3": (10.97, 56.49), "RV4": (49.65, 56.49),
    "RV5": (10.97, 80.59), "RV6": (30.30, 80.59), "RV7": (49.64, 80.59),
    "J1": (7.42, 96.49), "J2": (18.87, 96.49), "J3": (30.31, 96.49), "J4": (41.76, 96.49), "J5": (53.21, 96.49),
    "J6": (7.42, 111.09), "J7": (18.87, 111.09), "J8": (30.31, 111.09), "J9": (41.76, 111.09), "J10": (53.21, 111.09),
}
PLAITS.update({f"D{k + 1}": (30.31, 24.74 + 5.40 * k) for k in range(8)})     # LED column, pitch 5.40
PLAITS_MOUNT_X = 7.54                                                           # its round 3.2 mm holes
for ref, (px, py) in PLAITS.items():
    if ref in real:
        d = math.hypot(real[ref][0] - px, real[ref][1] - py)
        ck.within(f"H.plaits_position.{ref}", d, None, 0.5, " mm off Plaits",
                  f"Plaits ({px}, {py}), Plaitsy ({real[ref][0]:.2f}, {real[ref][1]:.2f}): "
                  f"dx {real[ref][0] - px:+.2f}, dy {real[ref][1] - py:+.2f}")

ck.done()
