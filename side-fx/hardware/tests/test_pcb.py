"""PCB group: manufacturing, footprint and mechanical checks on Side FXy's routed master
(SideFXy-routed.epro2) that copper_audit.py does not do.

  A footprints    every footprint in the routed export: which parts use it, pad pitch / row spacing against
                  the parts' drawings (DIP-6/14/16 0.300 in rows, TO-92, SIP-9 = Bourns 4609X, standing
                  1/4 W resistor, DO-35, the ceramics, headers, CN1's right-angle header, WQP518MA / PJ366ST,
                  EC11E / PEC11R, the Thonk LED button), pin-1 cues
  B holes         every used pad's drill against the lead it takes (the socket's tail where the BOM puts the
                  chip in a socket): nominal clearance and the smallest finished hole at JLCPCB's -0.08 mm;
                  annular rings against JLCPCB's minimum and recommendation; plated slots; vias (and
                  design.md's 0.8 / 0.4 mm via rule); hole to hole; drill edge to track; track widths and the
                  POWER class
  C breakout      the DAISY-SEED-POWER-OPAMPS-2.54 footprint against the breakout's own Excellon drill file
                  and outline (rob-scape/daisy-seed-breakout-boards, numbers in the constants): best rigid
                  fit, worst offset, which tool each footprint hole lands on, the outline on the main board;
                  the fit with the pins named (from the breakout's copper), which face it puts towards the
                  main board, and that the breakout's tall through-hole parts are not on that face
  D outlines      both boards 69.6 x 108 mm, the four 3.2 mm holes at circuit.HOLES_FRONT on both, the board
                  inside the 14HP panel and clear of the rails, the display cable cutout (size, corner
                  radius, milling width)
  E value labels  value_labels.py's own rule and the mixer's M3: every value STRING nearer its own part than
                  any part of another value by >= 0.3 mm, its text circuit.py's value, legend lines naming
                  parts of that value near them, text height / stroke against JLCPCB, no label on a pad,
                  hole or the cutout
  F bodies        real body sizes (datasheet maxima, DIP sockets) against each other on each side, the
                  standing resistors, ceramics, TO-92, CN1 with the display cable's plug, C4
  G stacking      the 8.5 mm socket + 2.5 mm male plastic gap against design.md / the BOM, every faceplate
                  rear part's height (plus the main board's solder tails above it) against the gap, the
                  tails facing each other, what stands under the breakout on the main board
  H display       the panel gap from the jacks' height (Thonk's drawing: 9.0) and the encoders', the display module's
                  thickness + back connector + tape against it, the faceplate cutout under the connector
  I copper        dead pour islands and slivers, copper inside Thonk's 3 mm plug-tip circle under every
                  barrel on the panel side, exposed copper under the standoffs / screw heads, copper to the
                  board edge (JLCPCB and design.md's 0.5 mm) and to the cutout, the smallest gaps against
                  JLCPCB's 0.127 mm and the board's 0.152 mm rule

Run from side-fx/hardware/tests:  python test_pcb.py
Read-only: imports the tools and opens the committed export as a zip.
"""
import collections
import math
import re

import harness

class _Named:
    """harness.Checks with the claim split off the name: 'A.dip_rows.X: what it claims' -> name 'A.dip_rows.X',
    the claim in front of the detail, so the summary line lists short names."""

    def __init__(self, group):
        self.c = harness.Checks(group)

    @staticmethod
    def _split(name):
        n, _, claim = name.partition(": ")
        return n, claim

    def check(self, name, ok, detail=""):
        n, claim = self._split(name)
        return self.c.check(n, ok, f"{claim} -- {detail}" if claim and detail else claim or detail)

    def close(self, name, actual, expected, tol, unit=""):
        return self.check(name, abs(actual - expected) <= tol,
                          f"expected {expected:.4g}{unit} +- {tol:.3g}, got {actual:.4g}{unit}")

    def within(self, name, actual, lo, hi, unit="", why=""):
        ok = (lo is None or actual >= lo) and (hi is None or actual <= hi)
        rng = f"{'-inf' if lo is None else f'{lo:.4g}'} .. {'+inf' if hi is None else f'{hi:.4g}'}{unit}"
        return self.check(name, ok, f"expected {rng}, got {actual:.4g}{unit}" + (f" ({why})" if why else ""))

    def done(self):
        self.c.done()


ck = _Named("pcb")
ca = harness.load("copper_audit")
circuit = harness.load("circuit")
vl = harness.load("value_labels")
MIL = harness.MIL

# ====================================================================== constants (sources, conditions)
# --- JLCPCB PCB capabilities, 2-layer, 1 oz, 1.6 mm (https://jlcpcb.com/capabilities/pcb-capabilities,
#     read 2026-11-12). All are fab minimums unless marked "recommended".
JLC_PTH_MIN = 0.15          # min PTH drill (0.10 only for <= 1.0 mm boards)
JLC_PTH_TOL = (-0.08, 0.13)  # finished PTH diameter tolerance, mm
JLC_RING_MIN = 0.18         # PTH annular ring, minimum (1 oz)
JLC_RING_REC = 0.25         # PTH annular ring, "recommended 0.25 mm or above"
JLC_VIA_DRILL_MIN = 0.15    # min via hole (0.20 "preferred")
JLC_VIA_DIA_MIN = 0.25      # min via diameter
JLC_PSLOT_MIN = 0.50        # min plated slot width
JLC_NPSLOT_MIN = 1.00       # min non-plated slot width (the milled cutout is one)
JLC_HOLE_HOLE_PAD = 0.45    # hole to hole, pad holes of different nets
JLC_HOLE_HOLE_VIA = 0.20    # hole to hole, vias
JLC_PTH_TRACK = 0.28        # PTH (drill edge) to track, minimum (0.35 recommended)
JLC_NPTH_TRACK = 0.20       # NPTH to track (copper_audit still uses the older 0.254)
JLC_PAD_PAD = 0.15          # pad to pad, different nets
JLC_TRACK_MIN = 0.10        # trace width / spacing, 1 oz: 0.10 / 0.10 (4 / 4 mil)
JLC_SPACING = 0.127         # the long-standing 5 mil 2-layer figure the brief and copper_audit.FAB_SPACING use
JLC_EDGE = 0.20             # copper to a routed board edge
JLC_SILK_W = 0.15           # min silkscreen line width
JLC_SILK_H = 1.00           # min silkscreen text height (40 mil)
JLC_PAD_SILK = 0.15         # pad to silkscreen
JLC_OUTLINE_TOL = 0.20      # board outline tolerance, regular
# JLCPCB states no minimum copper island area. House rule (the mixer's): a pour piece under 1 mm2 that is
# nowhere wider than 0.25 mm is a sliver that can lift; dead copper of any size is a finding.
SLIVER_AREA, SLIVER_W = 1.0, 0.25

# --- the boards' own rules
BOARD_RULE = ca.CLEARANCE   # 0.152 mm: the rule the routed boards carry for pads and vias (copper_audit)
# design.md's routing notes, read from the file (2026-11-14: these were constants copied from it, so a
# corrected doc could never pass): "copper <x> mm from the edge" and "vias <diameter> / <drill> mm"
_rules = harness.text("docs", "design.md")
_m = re.search(r"copper ([\d.]+) mm\s+from the edge", _rules)
DESIGN_EDGE = float(_m.group(1)) if _m else float("inf")
DESIGN_TRACK, DESIGN_POWER = 0.3, 0.6       # design.md: tracks 0.3 mm, POWER class 0.6 mm
_m = re.search(r"vias ([\d.]+) / ([\d.]+) mm", _rules)
DESIGN_VIA = (float(_m.group(1)), float(_m.group(2))) if _m else (float("nan"), float("nan"))   # diameter, drill
POWER_NETS = ("+12V", "-12V", "3V3A", "3V3D", "3V3D_F")     # design.md's POWER class ("and their _F twins")
CUTOUT_EDGE = ca.CUTOUT_EDGE  # 0.3 mm copper to the milled cutout (copper_audit / generator; JLCPCB edge 0.2)
BOARD_W, BOARD_H = circuit.BOARD_W, circuit.BOARD_H

# --- Eurorack mechanics
# sdiy.info "Eurorack" / "Eurorack panel components" wiki (no Doepfer figure published; Doepfer a100m_e.htm only
# gives the 128.5 mm panel): "the maximum vertical PCB size can be from 108mm (4.25") to 110mm"; keep 10 mm
# clear behind the panel at top and bottom for the rails.
RAIL_PCB_MAX_H = 108.0      # the conservative end of 108..110
RAIL_CLEAR = 10.0           # mm from the panel's top / bottom edge

# --- M3 hardware at the mounting holes (bom.md: M3 x 6 pan head screws, female-female standoffs)
M3_PAN_HEAD_R = 5.6 / 2     # ISO 7045 / DIN 7985 pan head dk 5.6 max
M3_STANDOFF_R = 6.35 / 2    # 5.5 mm AF hex standoff: across corners 6.35 (round 5-6 mm standoffs are smaller)

# --- Thonkiconn (PJ398SM / QingPu WQP518MA) and the stereo PJ366ST
THONK_SLEEVE, THONK_SWITCH, THONK_TIP = 6.48, 3.38, 4.92   # barrel centre to the lugs, Thonk PJ398SM drawing as
#   copper_audit / circuit.py / the module-design skill quote it. VERIFY 2026-11-13: confirmed on Thonk's drawing
#   (PCB layout, top view: 6.48 sleeve to barrel, 3.38 switch to barrel, 4.92 barrel to tip, 3.10 sleeve to switch)
THONK_TIP_R = ca.THONK_TIP_R    # 1.75: Thonk's note asks for a 3 mm hole or no copper under the barrel (+0.25)

# --- leads, (shape, max width, max thickness, what) mm: 'round' -> (d, d); 'rect' -> width x thickness (its
#     diagonal must pass a round hole; both sides a slot). "what" names what really goes into the hole.
LEADS = {
    # the BOM puts U1/U2/U3/U6/U7 in DIP sockets, so the holes take the socket's tails. Stamped dual-wipe socket
    # tails: NOT CONFIRMED (On Shore SAXXX0X0.pdf is an outlined-text drawing we could not read); assumed
    # 0.51 x 0.30 max. The chip itself (soldered without a socket): LEADS_CHIP below.
    "DIP-6-W7.62-P2.54": ("rect", 0.51, 0.30, "DIP socket tail (assumed)"),
    "DIP-14-W7.62-P2.54": ("rect", 0.51, 0.30, "DIP socket tail (assumed)"),
    "DIP-16_L20.0-W6.4-P2.54-LS7.6-BL": ("rect", 0.51, 0.30, "DIP socket tail (assumed)"),
    # Bourns 4600X conformal SIP datasheet: lead 0.50 +-0.10 (max 0.60) x 0.254 +-0.050 (max 0.304)
    "SIP-9-P2.54": ("rect", 0.60, 0.304, "Bourns 4609X lead"),
    # onsemi 2N3903/2N3904 (2N3903-D), TO-92 case 29: D 0.407-0.533 (lead width), J 0.39-0.50 (thickness)
    "TO-92-INLINE-P2.54": ("rect", 0.533, 0.50, "2N3904 lead"),
    # standing 1/4 W metal film: Yageo MFR-25 lead 0.54 +-0.05 (the mixer's figure, not re-read: the local
    # mfr25 download is empty) -> 0.60 used
    "RES-TH-VERTICAL-P2.54": ("round", 0.60, 0.60, "1/4 W MF resistor lead"),
    # Vishay 1N4148 (doc 81857 rev 1.6, DO-35 drawing): lead 0.55 max. BAT85 in DO-35 (BOM): the same package;
    # its own drawing was not readable here (the local PDFs are damaged)
    "DO-35_BD2.0-L4.0-P8.0-D0.5-RD": ("round", 0.55, 0.55, "DO-35 lead (1N4148 / BAT85)"),
    # ceramics on 5.08 mm: TDK FG28 lead 0.5 (the mixer; 0.55 assumed max); KEMET 10 uF X7R lead 0.51 +0.025/-0.076
    # (C430C106K3R5TA spec sheet) -> 0.55 used
    "CAP-TH_L3.0-W2.0-P5.08-D0.7": ("round", 0.55, 0.55, "ceramic capacitor lead"),
    # 1 uF KYOCERA AVX SR30 (SR305C105KAR): lead 0.508 (0.020 in), 0.55 with tolerance (the mixer)
    "CAP-TH_L7.6-W3.8-P5.08-D0.51": ("round", 0.55, 0.55, "SR30 lead"),
    # 2.54 mm male header posts and female socket tails: 0.64 mm square (the 0.025 in industry post)
    "HDR-1x5-P2.54": ("rect", 0.64, 0.64, "header post / socket tail"),
    "HDR-1x6-P2.54": ("rect", 0.64, 0.64, "header post / socket tail"),
    "HDR-1x8-P2.54": ("rect", 0.64, 0.64, "header post / socket tail"),
    "HDR-1x11-P2.54": ("rect", 0.64, 0.64, "header post / socket tail"),
    "HDR-1x8-P2.54-RA": ("rect", 0.64, 0.64, "right-angle header post"),
    "DAISY-SEED-POWER-OPAMPS-2.54": ("rect", 0.64, 0.64, "female socket tail under the breakout"),
    # Thonkiconn / PJ366ST lugs: no dimensioned drawing readable (thonk.co.uk blocks fetches); assumed flat
    # 1.0 x 0.3 (the mixer's assumption, NOT CONFIRMED)
    "CONN-TH_WQP-WQP518MA": ("rect", 1.0, 0.3, "Thonkiconn lug (assumed)"),
    "JACK-PJ366ST-STEREO": ("rect", 1.0, 0.3, "PJ366ST lug (assumed)"),
    # Bourns PEC11R-4xxxF-S drawing: terminals 0.8 wide ("0.8 5 PLCS"); thickness NOT CONFIRMED, 0.3 assumed.
    # Mounting tabs: checked against PEC11R_TAB_HOLE instead.
    "ENC-EC11E-SW-VERTICAL": ("rect", 0.8, 0.3, "EC11 / PEC11R terminal"),
    # Thonk LED button pins: VERIFY 2026-11-13: Thonk's LowProfileButton.pdf (TACT SWITCH, rev A, X.X +-0.25, X.XX
    # +-0.1) gives the terminals 0.7 wide and 0.3 thick ("0.3t") and the PCB holes 7 x d1.0; 0.7 x 0.5 kept
    # (it is the larger, conservative section)
    "SW-TACT-LP-LED-THONK": ("rect", 0.7, 0.5, "LED button pin (Thonk 0.7 x 0.3t; 0.5 kept)"),
}
LEADS_CHIP = ("rect", 0.56, 0.36)      # JEDEC MS-001 / TI N package b 0.36-0.56, c 0.20-0.36: a chip soldered in
# IPC-2222 table 9-3: nominal hole minus maximum round lead >= 0.15 (level C, the tightest); the smallest
# finished hole (drill - 0.08) must still clear the lead's diagonal by 0.05 (round) / 0 (square or flat);
# hole minus minimum lead <= 0.70 (level A maximum: a looser hole wicks and tilts the part)
IPC_FIT_MIN, INSERT_MIN, IPC_FIT_MAX = 0.15, 0.05, 0.70
LEAD_MIN_FRACTION = 0.9                 # a round lead's minimum taken as 0.9 x its maximum for the looseness check

# --- pitches and patterns
DIP_PITCH, DIP_ROW = 2.54, 7.62          # JEDEC MS-001: e 2.54 BSC, eA 7.62 BSC (0.300 in rows)
SIP_PITCH, SIP_PITCH_TOL = 2.54, 0.07    # Bourns 4600X: 2.54 +-0.07 non-accumulative
SIP9_LEN_MAX = 22.81                     # Bourns 4600X: 9 pins, A maximum 22.81 (.898)
SIP_H_MAX, SIP_T_MAX = 5.08, 2.49        # Bourns 4600X (X = low profile): height 5.08 max, thickness 2.49 max
TO92_BULK_G = (1.15, 1.39)               # onsemi 2N3903-D: G, straight-lead bulk pack lead spacing
TO92_FORMED_P = 2.54                     # onsemi: bent-lead tape / ammo pack spacing 2.54 (P; H 2.42-2.66)
TO92_BODY = (5.33, 4.19)                 # onsemi: B 4.32-5.33 (width), C 3.18-4.19 (depth): maxima
DO35_BODY = (4.56, 2.28)                 # DO-35 max body (JEDEC DO-204AH; Vishay 1N4148 rev 1.6: 3.4 x 1.75)
DO35_BEND = 0.8                          # IPC-A-610: a lead bend no closer than ~1 lead diameter / 0.8 mm to the body
EC11_ROW_A, EC11_ROW_S = 7.5, 7.0        # Bourns PEC11R-4xxxF-S layout: shaft to the A-C-B row 7.5, to S1-S2 7.0
EC11_PITCH_ACB, EC11_PITCH_S = 2.5, 5.0  # PEC11R: A to B 5.0 with C between, S1 to S2 5.0; Alps EC11E the same
PEC11R_HOLE = 1.0                        # PEC11R layout: terminal holes 1.0 +0.1/-0
PEC11R_TAB_HOLE = (2.6, 1.8)             # PEC11R layout: mounting tab holes 2.6 (across the tab line) x 1.8 (along
#   it), +0.2/-0, 2 places. VERIFY 2026-11-13: the tab-to-tab "13.2 (.520)" was read off the drawing's vector
#   paths (REV. D04/26 page 2, PEC11R-4xxxF-Sxxxx): its arrow tips sit on the OUTER edges of the two hole
#   rectangles, and the "1.8" arrows span one hole along the tab line. So the hole centres are 13.2 - 1.8 =
#   11.4 mm apart, each hole 4.8 .. 6.6 mm from the shaft (nominal; the +0.2 only grows it). The front view's
#   14.0 is across the snap-in tabs' outward bends in their free state, not the tab pitch.
PEC11R_TAB_OUTER = 13.2
PEC11R_TAB_SPAN = ((PEC11R_TAB_OUTER - 2 * PEC11R_TAB_HOLE[1]) / 2, PEC11R_TAB_OUTER / 2)    # 4.8 .. 6.6 mm
# The user's own PEC11R-4215F-S0024, measured with calipers on 2026-11-14: "12.7 mm or less" across the
# outer faces of its two mounting tabs, just above the barbs (an upper bound). Bourns' layout above is the
# recommended hole, with clearance; this is the part that goes into the slots (the barbs flex through).
PEC11R_TAB_OUTER_MEASURED = 12.7     # mm, max
# Alps EC11E, catalogue "EC11 11mm Size Metal Shaft Type" (data as of April 2019), drawing 5 (EC11E vertical with
# push-on switch), PC board mounting hole dimensions, read off the vector paths: tab holes 1.5 along the tab
# line x 2.6 across, the "12.5" spanning their OUTER edges (as Bourns draws it) -> centres 11.0, each hole
# 4.75 .. 6.25 mm from the shaft. (VERIFY 2026-11-13: the writer's 11.2 was KiCad's
# RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm, MP at y -3.1 / 8.1 round the shaft at 2.5: the footprint's own
# source, not Alps'.) No tolerances are printed on that page.
EC11E_TAB_HOLE = (2.6, 1.5)              # across, along
EC11E_TAB_OUTER = 12.5
EC11E_TAB_SPAN = ((EC11E_TAB_OUTER - 2 * EC11E_TAB_HOLE[1]) / 2, EC11E_TAB_OUTER / 2)       # 4.75 .. 6.25 mm
PJ366_KICAD_MR = {"1": (0.0, 1.9, 0.68), "2": (3.1, 2.1, 0.68), "3": (11.4, 2.0, 0.57)}   # KiCad MR 1073 (closed,
#   never merged), as the module-design skill quotes it: lug distance from the sleeve, slot length x width
THONK_BTN_PINS = {"1": (2.54, 2.54), "2": (-2.54, 2.54), "3": (2.54, -2.54), "4": (-2.54, -2.54),
                  "5": (2.7, 0.0), "6": (-2.7, 0.0)}   # Thonk SW_Tact_Low_Profile_LED (module-design parts.md)

# --- real bodies (max), mm
R_STAND_D = 2.5          # 1/4 W metal film body diameter, standing (Yageo MFR-25: 2.3-2.5; the mixer)
CAP_FG28 = (4.0, 2.5, 5.5)    # TDK FG28 100 n / 1 n: W x T x H (distributor listings; the mixer)
CAP_10U = (5.08, 4.07, 5.84)  # KEMET C324C106K3R5TA, 10 uF 25 V X7R GoldMax: L x T x H max, S 2.54 +-0.78
#   (the KEMET spec sheet as a search result quoted it). VERIFY 2026-11-13: a 10 uF MLCC on 5 mm leads does
#   exist: TDK FG28X5R1E106MRT06, 10 uF 25 V X5R, lead spacing 5.0 mm, body 4.0 x 2.5, seated height 5.5 max
#   (DigiKey 7384817 / LCSC C1620216 / RS 2427606 listings). The larger KEMET envelope is kept for the body
#   and height checks (conservative); CAP_10U_FG28 is the part that fits the footprint as it is.
CAP_10U_FG28 = (4.0, 2.5, 5.5)
CAP_SR30 = (7.62, 3.81)  # AVX SR30: 0.300 x 0.150 in (as the footprint name says; the mixer, not re-confirmed)
CAP_STANDOFF = 1.0       # a dipped radial's lead kink / meniscus under the body, assumed
SOCKET_W = 10.16         # stamped 0.300 in DIP socket frame width (Oupiin / Winslow listings via the mixer)
SOCKET_PITCH_L = 2.54    # frame length = pins/2 x 2.54 (Oupiin 14-pin A 17.78)
SOCKET_H = 4.5           # dual-wipe socket body height (Futurlec ICS16 "4.5 mm"; NOT CONFIRMED as a maximum)
#   VERIFY 2026-11-13: On Shore SA series (drawing SAXXX0X0 rev C, "IC/SKT SA 7.43 mmL", turned-pin open frame,
#   read as rendered): pin 7.43 overall with 3.00 below the insulator -> the socket's top 4.43 above the board
#   (X.XX +-0.10); tail d 0.51; SA1630X0 20.32 x 10.16. 4.5 stays as the round, slightly conservative figure.
DIP_A_MAX = 5.33         # JEDEC MS-001 A max (0.210 in): seating plane to the top of the chip (TI's SN74HC165
#   datasheet text here carries no N-package drawing, so the JEDEC maximum stands)
FEMALE_TAIL = 3.2        # 8.5 mm female header tail below its body: 3.0 / 3.2 mm (LCSC "PM254" naming guide; JLCPCB
#   C27438 listing "3.2mm"): a part dimension, not a builder-trimmed lead. NOT CONFIRMED from a drawing.
SIP_SEAT = 0.5           # a SIP's body bottom above the board (lead shoulder), assumed

# --- stacking (bom.md / design.md / module-design parts.md)
FEMALE_H = 8.5           # bom.md: "Female header, 2.54 mm, 8.5 mm tall"
MALE_PLASTIC = 2.5       # standard 2.54 mm male header plastic
MALE_PIN = 6.0           # mating pin above the plastic (typ 5.8-6.1)
TAIL_MAX = 2.5           # lead protrusion on the far side, IPC-A-610 class 2 maximum (2.5 mm)
TAIL_TYP = 1.5
DUPONT = 2.54            # Dupont crimp housing cross-section
BOARD_T = 1.6            # bom.md: 1.6 mm FR4

# --- the panel gap and the display stack
# Thonkiconn PJ398SM: PCB to the jack's front face, where the panel rests. VERIFY 2026-11-13 (test bug fixed:
# this was "6.0 .. 7.0 assumed"): Thonk's drawing "'THONKICONN' 3.5mm switching jack socket", model PJ398SM,
# unit mm, tolerance +-0.15, ver 1 (Thonkiconn_Jack_Datasheet-new.jpg, a copy another session downloaded),
# side view: bushing d6 x 5.5, body 9 from the PCB face to the front face, terminals 3.5 behind it. So the
# panel sits 9.0 +-0.15 mm above the faceplate (test_panel uses the same figure); design.md / README / the
# skill's "about 7 mm" is the docs finding D.readme_panel_gap in test_panel.
JACK_BODY_H, JACK_TOL = 9.0, 0.15
JACK_SHOULDER = (JACK_BODY_H - JACK_TOL, JACK_BODY_H + JACK_TOL)
# Bourns PEC11R-4xxxF-S drawing (REV. D04/26 p.2, side view, vector-read): "6.5 (.256)" runs from the PCB seating
# face (Bourns labels it MOUNTING SURFACE) to the bushing base; the 7.0 / 7.5 are the switch / A-C-B rows' offsets
# from the shaft axis. Tolerance <10 mm: +-0.3. Alps EC11E (drawing 5): 4.5 from the PCB to the bushing base.
ENC_BODY_PEC11R, ENC_BODY_EC11E, ENC_TOL = 6.5, 4.5, 0.3
ENC_SHOULDER = (ENC_BODY_PEC11R - ENC_TOL, ENC_BODY_PEC11R + ENC_TOL)
# Waveshare 1.9inch LCD Module (wiki: 27.3 x 51.2 mm, MX1.25 8-pin; 3D model 1_9inch-lcd-module.stp from
# files.waveshare.com/upload/9/98/1.9inch_LCD_Module_3D.zip, parsed: PCB 1.6, glass + LCD 1.9 above it, the
# MX1.25 header 3.5 below the PCB, the flex's ZIF connector 2.0 below, the flex bend 1.1 below, M2 x 2.5
# studs at the corners 2.5 below; the header 34.48-38.68 mm from the flex end, 6.28-21.03 across)
LCD_GLASS, LCD_PCB = 1.9, 1.6
LCD_CONN, LCD_ZIF, LCD_FLEX, LCD_STUD = 3.5, 2.0, 1.1, 2.5
LCD_CONN_FROM_FLEX = (34.48, 38.68)
LCD_CONN_ACROSS = (6.28, 21.03)
LCD_W, LCD_L = 27.3, 51.2
LCD_ZIF_FROM_FLEX = (51.2 - 42.79, 51.2 - 36.29)   # the ZIF's span from the flex end (3D model)
TAPE = 0.2               # thin double-sided tape (design.md), assumed 0.2 max

# --- the breakout's own drill file and outline (rob-scape/daisy-seed-breakout-boards, daisy-seed-dcdc-opamps,
#     Drill_PTH_Through.DRL / Gerber_BoardOutlineLayer.GKO, EasyEDA v6.5.51 2025-08-29, METRIC 3:3, top view)
BO_OUTLINE = (0.15239, -18.796, 96.901, 0.0)          # x1, y1, x2, y2
BO_SEED = [(36.83 + 2.54 * k, y) for y in (-1.778, -17.018) for k in range(20)]   # T05 1.200 mm, two rows of 20
BO_HDR = [(x, y) for y in (-1.778, -17.018) for x in (24.13, 26.67, 29.21, 31.75, 87.63, 90.17, 92.71, 95.25)]
#   T02 0.889 mm: a 1x4 header at each end of each row
BO_PWR = [(x, -3.894 - 2.54 * k) for x in (6.085, 8.625) for k in range(5)]   # T02 0.889: the 2x5 power header
BO_SEED_D, BO_HDR_D = 1.200, 0.889
# Which breakout hole is which pin (Gerber top view). VERIFY 2026-11-13: the drill pattern alone is symmetric
# about the row axis, so the writer's unnamed fit could not tell the two faces apart. The pin identities come from
# the breakout's own copper and silk as the netlist verifier traced them (sidefx-tests-verify-netlist-pins-logic.md:
# the Seed-row end pads at x 85.09 are square; the one in row -1.778 is spoked into the bottom GND pour = pin 40
# DGND, the one in row -17.018 isolated = pin 1; pin 20 at (36.83, -17.018) spoked = AGND; J1 "-12" with GND at
# its pin nearest the Seed; J4 / J5 pin 1 square at the far end).
BO_PIN = {str(n): (85.09 - 2.54 * (n - 1), -17.018) for n in range(1, 21)}
BO_PIN.update({str(n): (36.83 + 2.54 * (n - 21), -1.778) for n in range(21, 41)})
for _j, _x0, _y in (("J1", 31.75, -17.018), ("J3", 31.75, -1.778), ("J5", 95.25, -17.018), ("J4", 95.25, -1.778)):
    BO_PIN.update({f"{_j}-{k}": (_x0 - 2.54 * (k - 1), _y) for k in range(1, 5)})
# The breakout's own BOM (2025-08-29) and silk: its tall parts are through-hole and drawn on the Gerber BOTTOM (THT)
# side with the Seed: C9 / C18 100 uF 50 V 8 x 12 mm cans, U3 B2405S-1WR2 (Mornsun B_S-1WR2: 11.60 x 6.00 x 10.16 mm),
# J2 the 2x5 power header. The Gerber TOP carries only SMD parts (TSSOP-14, SOD-123, 0603 / 1206, L1 / L2).
BO_THT_TALLEST = 12.0 + 1.0          # the 8 x 12 can plus its lead standoff (assumed 1 mm)
BREAKOUT_FIT_TOL = 0.05   # mm: a socket pin on its hole centre this close (well inside the hole's clearance)
BO_BOTTOM_PARTS = False   # the breakout's Gerbers have a top paste layer only: no SMD part on its bottom

# ====================================================================== load the routed master
R = harness.routed()
MB, FB = R.main, R.face
BOARDS = (("main", MB), ("face", FB))
DESIGN = harness.text("docs", "design.md")
BOMMD = harness.text("docs", "bom.md")

FP = {}           # raw footprint pads with holes, footprint frame (mm)
for title, d in R.fp_docs.items():
    pads = {}
    for h, p in d["recs"]:
        if h["type"] == "PAD" and p:
            dp, ho = p["defaultPad"], p.get("hole") or {}
            pads[str(p["num"])] = {"x": p["centerX"] * MIL, "y": p["centerY"] * MIL, "shape": dp["padType"],
                                   "w": dp["width"] * MIL, "h": dp["height"] * MIL, "hole": ho.get("holeType"),
                                   "hw": ho.get("width", 0) * MIL, "hh": ho.get("height", 0) * MIL,
                                   "plated": p.get("plated")}
    FP[title] = pads
USED = collections.defaultdict(list)
for k, b in BOARDS:
    for ref, pl in b.parts.items():
        USED[pl["fp"]].append(f"{k}:{ref}")
VIAS = {}         # raw vias per board: x, y, drill, diameter, net
for k, _ in BOARDS:
    VIAS[k] = [(p["centerX"] * MIL, p["centerY"] * MIL, p["holeDiameter"] * MIL, p["viaDiameter"] * MIL, p["netName"])
               for h, p in R.pcb_docs[k]["recs"] if h["type"] == "VIA"]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def front(x):
    return BOARD_W - x


def poly_area(pts):
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2


def island_area(isl):
    return poly_area(isl.outline) - sum(poly_area(h) for h in isl.holes)


def bbox(pts):
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return min(xs), min(ys), max(xs), max(ys)


def fp_bbox(title):
    return R.fp_geo[next(u for u, d in R.fp_by_uuid.items() if d is R.fp_docs[title])]["bbox"]


print("footprints in the routed export (title: used by):")
for t in sorted(R.fp_docs):
    print(f"      {t}: {', '.join(sorted(USED.get(t, []))) or 'UNUSED'}")

# ====================================================================== A. footprints
ck.check("A.fp_count: 24 footprint documents in the routed export, every placed part's footprint among them",
         len(R.fp_docs) == 24 and all(pl["fp"] in R.fp_docs for _, b in BOARDS for pl in b.parts.values()),
         f"{len(R.fp_docs)} footprints")
ck.check("A.no_part_on.DO-41: no part uses the DO-41 footprint (1.05 mm holes for a 0.86 mm lead; BOM D1 / D2 are DO-35)",
         not USED.get("DO-41_BD2.4-L4.7-P8.70-D0.8-RD"), f"used by {USED.get('DO-41_BD2.4-L4.7-P8.70-D0.8-RD')}")
ck.check("A.no_part_on.PDIP-14_LS9.0: no part uses the 8.89 mm-row PDIP-14 (no DIP socket fits it)",
         not USED.get("PDIP-14_L19.3-W6.4-P2.54-LS9.0-BL"), f"used by {USED.get('PDIP-14_L19.3-W6.4-P2.54-LS9.0-BL')}")
_do35 = FP["DO-35_BD2.0-L4.0-P8.0-D0.5-RD"]
ck.check("A.diodes_on_DO-35: D1 (BAT85) and D2 (1N4148) on the DO-35 footprint, 0.8 mm holes as bom.md says "
         "(the name's D0.5 is the lead, not the drill)",
         sorted(USED.get("DO-35_BD2.0-L4.0-P8.0-D0.5-RD", [])) == ["main:D1", "main:D2"]
         and all(abs(_do35[n]["hw"] - 0.8) < 0.01 for n in "12") and "holes are 0.8 mm" in BOMMD,
         f"{USED.get('DO-35_BD2.0-L4.0-P8.0-D0.5-RD')}, drills {[round(_do35[n]['hw'], 3) for n in '12']}")


def silk_marks(title):
    out = []
    for h, p in R.fp_docs[title]["recs"]:
        if h["type"] in ("POLY", "FILL") and p and p.get("layerId") == 3:
            out.append(p["path"])
    return out


def dip(title, n):
    P = FP[title]
    xy = {i: (P[str(i)]["x"], P[str(i)]["y"]) for i in range(1, n + 1)}
    pitch = [dist(xy[i], xy[i + 1]) for i in range(1, n // 2)] + [dist(xy[i], xy[i + 1]) for i in range(n // 2 + 1, n)]
    across = [dist(xy[i], xy[n + 1 - i]) for i in range(1, n // 2 + 1)]
    ck.check(f"A.dip_pitch.{title}: pin pitch {DIP_PITCH} (MS-001 e)", all(abs(p - DIP_PITCH) < 0.01 for p in pitch),
             f"got {sorted(set(round(p, 3) for p in pitch))}")
    ck.check(f"A.dip_rows.{title}: pin i opposite pin {n + 1}-i at {DIP_ROW} (MS-001 eA, a 0.300 in socket)",
             all(abs(a - DIP_ROW) < 0.01 for a in across), f"got {sorted(set(round(a, 3) for a in across))}")
    r1 = {round(xy[i][1], 2) for i in range(1, n // 2 + 1)}
    r2 = {round(xy[i][1], 2) for i in range(n // 2 + 1, n + 1)}
    ccw = len(r1) == 1 and len(r2) == 1 and r1 != r2 and xy[1][0] < xy[n // 2][0] and xy[n // 2 + 1][0] > xy[n][0]
    ck.check(f"A.dip_numbering.{title}: 1..{n // 2} along one row, {n // 2 + 1}..{n} back along the other",
             ccw, f"rows {r1} / {r2}")
    square = P["1"]["shape"] == "RECT" and all(P[str(i)]["shape"] != "RECT" for i in range(2, n + 1))
    dots = [pa for pa in silk_marks(title) if pa and pa[0] == "CIRCLE"]
    dot_ok = any(dist((d[1] * MIL, d[2] * MIL), xy[1]) < min(dist((d[1] * MIL, d[2] * MIL), xy[i]) for i in range(2, n + 1))
                 for d in dots)
    ck.check(f"A.dip_pin1_cue.{title}: pin 1 marked (a square pad, or a silk dot nearest pin 1)", square or dot_ok,
             f"pin 1 pad {P['1']['shape']}, silk dots {[(round(d[1] * MIL, 2), round(d[2] * MIL, 2)) for d in dots]}")


dip("DIP-6-W7.62-P2.54", 6)
dip("DIP-14-W7.62-P2.54", 14)
dip("DIP-16_L20.0-W6.4-P2.54-LS7.6-BL", 16)
_m = re.search(r"LS(\d+\.\d+)", "DIP-16_L20.0-W6.4-P2.54-LS7.6-BL")
ck.close("A.dip16_name: the DIP-16 footprint's LS7.6 is its 7.62 mm row spacing", float(_m.group(1)), DIP_ROW, 0.03, " mm")
placed_bad = []
for k, b in BOARDS:
    for ref, pl in b.parts.items():
        if pl["fp"].startswith("DIP-"):
            n = len(pl["pads"])
            d = dist((pl["pads"]["1"].x, pl["pads"]["1"].y), (pl["pads"][str(n)].x, pl["pads"][str(n)].y))
            if abs(d - DIP_ROW) > 0.01 or pl["bottom"]:
                placed_bad.append(f"{ref} {d:.3f}")
ck.check("A.dip_placed: every placed DIP has pin 1 to pin n 7.62 mm and sits on its board's rear (top) layer",
         not placed_bad, f"{placed_bad}")

# TO-92: 2.54 mm pitch in line, pin 1 square; a bulk 2N3904's leads are 1.27 mm apart
P = FP["TO-92-INLINE-P2.54"]
pitch = [dist((P[a]["x"], P[a]["y"]), (P[b]["x"], P[b]["y"])) for a, b in (("1", "2"), ("2", "3"))]
ck.check("A.to92_pitch: TO-92 pads 1-2-3 in line at 2.54 mm (onsemi formed-lead spacing), pin 1 square",
         all(abs(p - TO92_FORMED_P) < 0.01 for p in pitch) and P["1"]["shape"] == "RECT", f"pitch {pitch}")
q1 = re.search(r"\|[^|\n]*2N3904[^|\n]*\|", BOMMD)
ck.check("A.to92_leads.Q1: the BOM asks for a formed-lead 2N3904 (2.54 mm) or says to spread a bulk part's 1.27 mm "
         "leads (onsemi G 1.15-1.39) onto the 2.54 mm footprint",
         bool(q1) and re.search(r"formed|bent|spread|2\.54|ammo|TA\b|TF\b", q1.group(0), re.I) is not None,
         f"bom.md: {q1.group(0).strip() if q1 else None}")
ck.check("A.to92_pinout.Q1: pads 1-2-3 = E-B-C (onsemi TO-92: 1 emitter, 2 base, 3 collector) on GND / B_CLK / CLK",
         MB.parts["Q1"]["nets"] == {"1": "GND", "2": "B_CLK", "3": "CLK"}, f"{MB.parts['Q1']['nets']}")

# SIP-9 against the Bourns 4609X
P = FP["SIP-9-P2.54"]
xs = [P[str(i)]["x"] for i in range(1, 10)]
gaps = [xs[i + 1] - xs[i] for i in range(8)]
ck.check(f"A.sip9_pitch: SIP-9 nine pads in a row at 2.54 +- {SIP_PITCH_TOL} (Bourns 4600X), pin 1 square",
         all(abs(g - SIP_PITCH) <= SIP_PITCH_TOL for g in gaps) and len({round(P[str(i)]["y"], 3) for i in range(1, 10)}) == 1
         and P["1"]["shape"] == "RECT", f"gaps {sorted(set(round(g, 3) for g in gaps))}")
x1, y1, x2, y2 = fp_bbox("SIP-9-P2.54")
ck.check(f"A.sip9_outline: the SIP-9 outline holds the 4609X's {SIP9_LEN_MAX} x {SIP_T_MAX} max body",
         x2 - x1 >= SIP9_LEN_MAX - 0.01 and y2 - y1 >= SIP_T_MAX - 0.01, f"outline {x2 - x1:.2f} x {y2 - y1:.2f}")
for ref in ("RN1", "RN2"):
    ck.check(f"A.sip9_pin1.{ref}: pin 1 (the bussed common) on 3V3D_F", FB.parts[ref]["nets"].get("1") == "3V3D_F",
             f"{FB.parts[ref]['nets'].get('1')}")

# standing resistor: 2.54 mm between the leads, the body over pad 1, the bent lead over pad 2
P = FP["RES-TH-VERTICAL-P2.54"]
p12 = dist((P["1"]["x"], P["1"]["y"]), (P["2"]["x"], P["2"]["y"]))
ck.close("A.res_stand_pitch: standing resistor pads 2.54 mm apart", p12, 2.54, 0.01, " mm")
ck.check(f"A.res_stand_bend: the pitch takes a {R_STAND_D} mm body plus the folded lead (body radius + lead + 0.3 mm bend)",
         p12 >= R_STAND_D / 2 + LEADS["RES-TH-VERTICAL-P2.54"][1] + 0.3, f"pitch {p12:.3f}")
ck.check("A.no_flat_resistors: no resistor uses a flat footprint (RES-TH_BD2.3 / LR1F unused; design.md: they stand "
         "on the main board)", not USED.get("RES-TH_BD2.3-L6.3-P10.30-D0.6") and not USED.get("RES-TH_L6.2-W2.3-LR1F1K0"),
         f"{USED.get('RES-TH_BD2.3-L6.3-P10.30-D0.6')} {USED.get('RES-TH_L6.2-W2.3-LR1F1K0')}")
fb_r = sorted(r for r in FB.parts if re.fullmatch(r"R\d+", r))
ck.check("A.design_md_flat_resistors: design.md's 'On the faceplate they lie flat' describes resistors the faceplate has",
         bool(fb_r) or "On the faceplate they lie flat" not in DESIGN,
         f"faceplate resistors: {fb_r}; design.md still says the faceplate's resistors lie flat")

# DO-35: 8.0 mm takes the body plus a bend each side
P = FP["DO-35_BD2.0-L4.0-P8.0-D0.5-RD"]
p12 = dist((P["1"]["x"], P["1"]["y"]), (P["2"]["x"], P["2"]["y"]))
need = DO35_BODY[0] + 2 * (DO35_BEND + LEADS["DO-35_BD2.0-L4.0-P8.0-D0.5-RD"][1])
ck.check(f"A.do35_pitch: DO-35 pads {p12:.2f} mm apart take the {DO35_BODY[0]} mm max body + two bends",
         p12 >= need, f"need {need:.2f}")
band = [pa for pa in silk_marks("DO-35_BD2.0-L4.0-P8.0-D0.5-RD") if len(pa) == 5 and abs(pa[0] - pa[3]) < 1e-3
        and abs(pa[0]) * MIL < 1.9]
ck.check("A.do35_band: the DO-35 cathode band is nearer pad 1 (circuit.py: pad 1 = cathode)",
         bool(band) and all(abs(pa[0] * MIL - P["1"]["x"]) < abs(pa[0] * MIL - P["2"]["x"]) for pa in band),
         f"band x {[round(pa[0] * MIL, 2) for pa in band]}")
ck.check("A.diode_cathodes: D1 cathode (pad 1) on B_CLK (design.md 'cathode on the base'), D2 cathode on OPTO_A "
         "('cathode on pin 1')", MB.parts["D1"]["nets"].get("1") == "B_CLK" and MB.parts["D2"]["nets"].get("1") == "OPTO_A",
         f"D1 {MB.parts['D1']['nets']}, D2 {MB.parts['D2']['nets']}")

# ceramics: 5.08 mm
for t in ("CAP-TH_L3.0-W2.0-P5.08-D0.7", "CAP-TH_L7.6-W3.8-P5.08-D0.51"):
    P = FP[t]
    ck.close(f"A.cap_pitch.{t}: 5.08 mm between the leads (bom.md '5.08 mm leads')",
             dist((P["1"]["x"], P["1"]["y"]), (P["2"]["x"], P["2"]["y"])), 5.08, 0.01, " mm")
c4 = re.search(r"\|[^\n]*10 µF ceramic[^\n]*\| C4 \|", BOMMD)
# VERIFY 2026-11-13: such a part exists (TDK FG28X5R1E106MRT06, 10 uF 25 V X5R, 5.0 mm leads, 4.0 x 2.5 x 5.5 max);
# the writer's detail said none had been found. The check (bom.md names one) is unchanged.
ck.check("A.c4_part: bom.md names a 10 uF through-hole MLCC part number for C4's 5.08 mm footprint (one exists: TDK "
         "FG28X5R1E106MRT06, 25 V X5R, 5.0 mm leads, H 5.5 max)",
         bool(c4) and re.search(r"[A-Z]{1,3}\d{2,3}[A-Z0-9]{3,}", c4.group(0).split("|")[2] if c4 else "") is not None,
         f"bom.md: {c4.group(0)[:120] if c4 else None} (no part number)")

# headers
for t in ("HDR-1x5-P2.54", "HDR-1x6-P2.54", "HDR-1x8-P2.54", "HDR-1x11-P2.54", "HDR-1x8-P2.54-RA"):
    P = FP[t]
    n = len(P)
    gaps = [dist((P[str(i)]["x"], P[str(i)]["y"]), (P[str(i + 1)]["x"], P[str(i + 1)]["y"])) for i in range(1, n)]
    ck.check(f"A.header.{t}: {n} pins in a line at 2.54, pin 1 square", all(abs(g - 2.54) < 0.01 for g in gaps)
             and len({round(P[str(i)]["y"], 3) for i in range(1, n + 1)}) == 1 and P["1"]["shape"] == "RECT",
             f"gaps {sorted(set(round(g, 3) for g in gaps))}")
for ref, kind, nets in circuit.HEADERS:
    n = int(kind[3:])
    ck.check(f"A.header_size.{ref}: H / HF footprints have the {n} pins circuit.HEADERS gives",
             len(MB.parts[ref]["pads"]) == n and len(FB.parts[circuit.fb_ref(ref)]["pads"]) == n,
             f"{len(MB.parts[ref]['pads'])} / {len(FB.parts[circuit.fb_ref(ref)]['pads'])}")
ck.check("A.cn1: CN1 is the 1x8 right-angle header with 8 pins (the display cable's 8 Dupont sockets)",
         FB.parts["CN1"]["fp"] == "HDR-1x8-P2.54-RA" and len(FB.parts["CN1"]["pads"]) == len(circuit.LCD_PINS) == 8)

# Thonkiconn
P = FP["CONN-TH_WQP-WQP518MA"]
barrel = P["1"]["y"] + THONK_SLEEVE * (1 if P["3"]["y"] > P["1"]["y"] else -1)
got = tuple(abs(P[n]["y"] - barrel) for n in "123")
same = (P["2"]["y"] - barrel) * (P["1"]["y"] - barrel) > 0 and (P["3"]["y"] - barrel) * (P["1"]["y"] - barrel) < 0
ck.check("A.wqp518ma_lugs: sleeve / switch / tip lugs 6.48 / 3.38 / 4.92 mm from the barrel (Thonk PJ398SM), switch "
         "on the sleeve side, all on one line",
         same and all(abs(g - w) < 0.02 for g, w in zip(got, (THONK_SLEEVE, THONK_SWITCH, THONK_TIP)))
         and len({round(P[n]["x"], 3) for n in "123"}) == 1, f"got {tuple(round(g, 2) for g in got)}")
ck.close("A.wqp518ma_barrel: the barrel 0.78 mm from the footprint origin (circuit.JACK_BARREL)", abs(barrel),
         abs(circuit.JACK_BARREL), 0.01, " mm")
# VERIFY 2026-11-13 (new): Thonk's PJ398SM drawing, PCB layout (top view), gives the slots: 1 (sleeve) 0.6 x 1.3,
# 2 (switch) 0.6 x 1.5, 3 (tip) 0.5 x 1.5; pins 3.10 / 6.48 / 4.92 as in the constants
THONK_SLOTS = {"1": (1.3, 0.6), "2": (1.5, 0.6), "3": (1.5, 0.5)}
bad = [f"{n}: {max(P[n]['hw'], P[n]['hh']):.2f} x {min(P[n]['hw'], P[n]['hh']):.2f}" for n, (L, W) in THONK_SLOTS.items()
       if P[n]["hole"] != "SLOT" or max(P[n]["hw"], P[n]["hh"]) < L - 0.01 or min(P[n]["hw"], P[n]["hh"]) < W - 0.01]
ck.check("A.wqp518ma_slots: the jack's slots are at least Thonk's drawing's (S 1.3 x 0.6, TN 1.5 x 0.6, T 1.5 x 0.5)",
         not bad, f"{bad}")
P2 = FP["JACK-PJ366ST-STEREO"]
bad = []
for n, (d0, L, W) in PJ366_KICAD_MR.items():
    d_got = abs(P2[n]["y"] - P2["1"]["y"])
    if abs(d_got - d0) > 0.02 or abs(max(P2[n]["hw"], P2[n]["hh"]) - L) > 0.01 or abs(min(P2[n]["hw"], P2[n]["hh"]) - W) > 0.01:
        bad.append(f"{n}: {d_got:.2f} from the sleeve, slot {P2[n]['hw']:.2f} x {P2[n]['hh']:.2f}")
ck.check("A.pj366st_mr1073: PJ366ST lugs 0 / 3.1 / 11.4 mm from the sleeve with slots S 1.9 x 0.68, R 2.1 x 0.68, "
         "T 2.0 x 0.57 (KiCad MR 1073)", not bad, f"{bad}")
ck.check("A.pj366st_vs_mono: the stereo slots are no smaller than the mono WQP518MA's",
         all(max(P2[n]["hw"], P2[n]["hh"]) >= max(P[n]["hw"], P[n]["hh"]) - 1e-6 and
             min(P2[n]["hw"], P2[n]["hh"]) >= min(P[n]["hw"], P[n]["hh"]) - 1e-6 for n in "123"),
         f"stereo {[(round(P2[n]['hw'], 2), round(P2[n]['hh'], 2)) for n in '123']}, mono "
         f"{[(round(P[n]['hw'], 2), round(P[n]['hh'], 2)) for n in '123']}")
ck.check("A.pj366st_same_barrel: J5's sleeve and tip lugs lie where a mono jack's do, so its barrel is under the same "
         "6.5 mm panel hole", abs(P2["1"]["y"] - P["1"]["y"]) < 0.01 and abs(P2["3"]["y"] - P["3"]["y"]) < 0.01)
ck.check("A.pj366st_open_item: design.md's 'check a PJ366ST's leads against the slots' is closed (no PJ366ST drawing "
         "was readable here either)", "A PJ366ST's leads against the slots" not in DESIGN,
         "design.md still lists it under 'Check before ordering boards'")

# EC11E / PEC11R
P = FP["ENC-EC11E-SW-VERTICAL"]
acb = [P[n] for n in "ACB"]
ck.check(f"A.ec11_acb: A-C-B in a row {EC11_ROW_A} mm from the shaft, {EC11_PITCH_ACB} mm apart (PEC11R / EC11E)",
         all(abs(abs(q["x"]) - EC11_ROW_A) < 0.01 for q in acb) and abs(abs(acb[0]["y"] - acb[1]["y"]) - EC11_PITCH_ACB) < 0.01
         and abs(abs(acb[1]["y"] - acb[2]["y"]) - EC11_PITCH_ACB) < 0.01, f"{[(q['x'], round(q['y'], 2)) for q in acb]}")
ck.check(f"A.ec11_switch: S1 / S2 {EC11_ROW_S} mm from the shaft on the other side, {EC11_PITCH_S} mm apart",
         all(abs(abs(P[n]["x"]) - EC11_ROW_S) < 0.01 for n in ("S1", "S2")) and P["S1"]["x"] * P["A"]["x"] < 0
         and abs(abs(P["S1"]["y"] - P["S2"]["y"]) - EC11_PITCH_S) < 0.01,
         f"S1 ({P['S1']['x']:.2f}, {P['S1']['y']:.2f}), S2 ({P['S2']['x']:.2f}, {P['S2']['y']:.2f})")
ck.check(f"A.ec11_holes: terminal holes {PEC11R_HOLE} mm (PEC11R layout 1.0 +0.1/-0)",
         all(abs(P[n]["hw"] - PEC11R_HOLE) < 0.01 for n in ("A", "B", "C", "S1", "S2")),
         f"{[round(P[n]['hw'], 3) for n in ('A', 'B', 'C', 'S1', 'S2')]}")
# VERIFY 2026-11-13: A.ec11_tabs_pitch compared the footprint with KiCad's 11.2 (the footprint's own source, a
# check that could not fail); it now asks whether each slot covers the hole Alps' drawing asks for, and
# A.ec11_tabs_pec11r whether it covers Bourns' (size AND position: the writer could not read the PEC11R's tab
# pitch; it is 11.4 between centres, see the constants).
tab_pitch = dist((P["MP1"]["x"], P["MP1"]["y"]), (P["MP2"]["x"], P["MP2"]["y"]))
tab = (max(P["MP1"]["hw"], P["MP1"]["hh"]), min(P["MP1"]["hw"], P["MP1"]["hh"]))      # (across, along the tab line)
slot_span = (tab_pitch / 2 - tab[1] / 2, tab_pitch / 2 + tab[1] / 2)
# 2026-11-14: the BOM names only the PEC11R-4215F (the user's parts); Alps' holes are checked only while the
# BOM offers an Alps EC11E
_enc_line = next((l for l in BOMMD.splitlines() if "ENC1" in l), "")
_alps = "Alps" in _enc_line or "EC11E" in _enc_line
if not _alps:
    print(f"      (info) Alps EC11E holes {EC11E_TAB_SPAN[0]:.2f}..{EC11E_TAB_SPAN[1]:.2f} mm from the shaft, slots "
          f"{slot_span[0]:.2f}..{slot_span[1]:.2f}: not checked, the BOM names no Alps part")
ck.check(f"A.ec11_tabs_pitch: the MP slots ({tab_pitch:.1f} apart) cover Alps EC11E's recommended tab holes "
         f"(drawing 5: {EC11E_TAB_HOLE[1]} x {EC11E_TAB_HOLE[0]}, outer edges {EC11E_TAB_OUTER} -> "
         f"{EC11E_TAB_SPAN[0]:.2f}..{EC11E_TAB_SPAN[1]:.2f} mm from the shaft)",
         not _alps or (slot_span[0] <= EC11E_TAB_SPAN[0] + 1e-6 and slot_span[1] >= EC11E_TAB_SPAN[1] - 1e-6
                       and tab[0] >= EC11E_TAB_HOLE[0] - 1e-6),
         f"slot {tab[0]:.2f} x {tab[1]:.2f} at {slot_span[0]:.2f}..{slot_span[1]:.2f} mm from the shaft "
         f"(KiCad's EC11E pattern, 0.1 mm per side outside Alps' holes)")
print(f"      (info) Bourns' recommended PEC11R tab holes: {PEC11R_TAB_HOLE[1]} along x {PEC11R_TAB_HOLE[0]} across, "
      f"{PEC11R_TAB_SPAN[0]:.2f}..{PEC11R_TAB_SPAN[1]:.2f} mm from the shaft; the slots are "
      f"{PEC11R_TAB_SPAN[1] - slot_span[1]:.2f} mm short of them on the outside")
ck.check(f"A.ec11_tabs_pec11r: the user's PEC11R-4215F (tabs {PEC11R_TAB_OUTER_MEASURED} mm or less across their outer "
         f"faces, measured) fits the MP slots, as wide as the tab ({PEC11R_TAB_HOLE[0]} across)",
         tab[0] >= PEC11R_TAB_HOLE[0] - 1e-6 and PEC11R_TAB_OUTER_MEASURED / 2 <= slot_span[1] + 0.01,   # mil rounding
         f"slot {tab[0]:.2f} x {tab[1]:.2f} at {slot_span[0]:.2f}..{slot_span[1]:.2f} mm from the shaft; tabs' outer "
         f"faces at {PEC11R_TAB_OUTER_MEASURED / 2:.2f} mm or less")
# LED button
P = FP["SW-TACT-LP-LED-THONK"]
bad = [n for n, (x, y) in THONK_BTN_PINS.items() if abs(P[n]["x"] - x) > 0.01 or abs(P[n]["y"] - y) > 0.01]
ck.check("A.thonk_button: LED button pins 1-6 at Thonk's positions (switch 2.54 square, LED +-2.7), no feet holes",
         not bad and len(P) == 6, f"off: {bad}, {len(P)} pads")
ga = min(dist((P[a]["x"], P[a]["y"]), (P[b]["x"], P[b]["y"])) - (P[a]["w"] + P[b]["w"]) / 2
         for a in P for b in P if a < b)
ck.within("A.thonk_button_gap: smallest pad-to-pad gap inside the button footprint (JLCPCB 0.15)", ga, JLC_PAD_PAD, None, " mm")

# ====================================================================== B. holes, rings, vias, tracks
fit_bad, loose, ring_min_bad, ring_rec_bad, slot_bad, chip_bad = [], [], [], [], [], []
for title, pads in sorted(FP.items()):
    if title not in USED:
        continue
    lead = LEADS.get(title)
    for num, pd in sorted(pads.items()):
        if not pd["hole"]:
            continue
        if pd["hole"] == "ROUND":
            ring = (min(pd["w"], pd["h"]) - pd["hw"]) / 2
        else:
            ring = min((max(pd["w"], pd["h"]) - max(pd["hw"], pd["hh"])) / 2,
                       (min(pd["w"], pd["h"]) - min(pd["hw"], pd["hh"])) / 2)
            if min(pd["hw"], pd["hh"]) < JLC_PSLOT_MIN - 1e-6:
                slot_bad.append(f"{title}.{num} slot {pd['hw']:.2f} x {pd['hh']:.2f}")
        if ring < JLC_RING_MIN - 1e-3:
            ring_min_bad.append(f"{title}.{num} {ring:.3f}")
        elif ring < JLC_RING_REC - 1e-3:
            ring_rec_bad.append(f"{title}.{num} {ring:.3f}")
        if lead is None or num.startswith("MP"):
            continue                       # EC11 tabs: against the PEC11R's recommended holes in section A
        shape, lw, lt, what = lead
        if pd["hole"] == "ROUND":
            diag = lw if shape == "round" else math.hypot(lw, lt)
            margin = pd["hw"] - diag
            insert = pd["hw"] + JLC_PTH_TOL[0] - diag
            if (shape == "round" and margin < IPC_FIT_MIN - 1e-6) or insert < (INSERT_MIN if shape == "round" else 0):
                fit_bad.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {diag:.2f} {what} (nominal clearance "
                               f"{margin:.2f}, smallest finished hole {insert:.2f})")
            if shape == "round" and pd["hw"] - lw * LEAD_MIN_FRACTION > IPC_FIT_MAX:
                loose.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {lw:.2f} lead")
            if title.startswith("DIP-"):
                cd = math.hypot(LEADS_CHIP[1], LEADS_CHIP[2])
                if pd["hw"] + JLC_PTH_TOL[0] - cd < 0:
                    chip_bad.append(f"{title}.{num}")
        else:
            L, Wd = max(pd["hw"], pd["hh"]), min(pd["hw"], pd["hh"])
            if L + JLC_PTH_TOL[0] - lw < INSERT_MIN or Wd + JLC_PTH_TOL[0] - lt < INSERT_MIN:
                fit_bad.append(f"{title}.{num}: slot {L:.2f} x {Wd:.2f} for a {lw:.2f} x {lt:.2f} {what}")
ck.check("B.lead_fit: every lead (socket tail where the BOM puts a socket) fits its hole: round leads IPC-2222 level C "
         "0.15 on the nominal drill and 0.05 at JLCPCB's -0.08; square / flat ones their diagonal through the smallest "
         "finished hole; slots 0.05 each way", not fit_bad, f"{len(fit_bad)} tight: {fit_bad}")
ck.check("B.lead_loose: no round hole more than 0.7 mm over its lead (IPC-2222 level A maximum)", not loose, f"{loose}")
ck.check("B.chip_without_socket: a DIP chip soldered without its socket also fits (MS-001 lead 0.56 x 0.36, diagonal "
         "0.67 through the smallest finished hole)", not chip_bad, f"{chip_bad}")
ck.check(f"B.ring_min: every used pad's annular ring >= JLCPCB's minimum {JLC_RING_MIN} mm", not ring_min_bad,
         f"under: {ring_min_bad}")
ck.check(f"B.ring_rec: every used pad's annular ring >= JLCPCB's recommended {JLC_RING_REC} mm", not ring_rec_bad,
         f"under the recommendation: {ring_rec_bad}")
ck.check(f"B.slot_width: plated slots >= JLCPCB's {JLC_PSLOT_MIN} mm", not slot_bad, f"{slot_bad}")
ck.check(f"B.pth_drill: every plated hole >= JLCPCB's {JLC_PTH_MIN} mm",
         all(min(pd["hw"], pd["hh"] or pd["hw"]) >= JLC_PTH_MIN for t in USED for pd in FP[t].values() if pd["hole"]))

for k, b in BOARDS:
    vd = sorted({(round(d, 3), round(D, 3)) for x, y, d, D, n in VIAS[k]})
    ck.check(f"B.via_fab.{k}: vias drill >= {JLC_VIA_DRILL_MIN} (preferred 0.20), diameter >= {JLC_VIA_DIA_MIN}",
             all(d >= JLC_VIA_DRILL_MIN and D >= JLC_VIA_DIA_MIN and D > d for d, D in vd), f"(drill, diameter): {vd}")
    ck.check(f"B.via_design_md.{k}: vias as design.md's routing rule says, {DESIGN_VIA[0]} / {DESIGN_VIA[1]} mm",
             all(abs(D - DESIGN_VIA[0]) < 0.01 and abs(d - DESIGN_VIA[1]) < 0.01 for d, D in vd),
             f"the board has (drill, diameter) {vd}; design.md says {DESIGN_VIA[0]} / {DESIGN_VIA[1]} mm")
    tw = sorted({round(t["w"], 3) for t in b.tracks})
    ck.check(f"B.track_fab.{k}: track widths >= {JLC_SPACING} mm", all(w >= JLC_SPACING for w in tw), f"widths {tw}")
    ck.check(f"B.track_design.{k}: tracks at least design.md's {DESIGN_TRACK} mm", all(w >= DESIGN_TRACK - 1e-3 for w in tw),
             f"widths {tw}")
    thin = sorted({(t["net"], round(t["w"], 3)) for t in b.tracks if t["net"] in POWER_NETS and t["w"] < DESIGN_POWER - 1e-3})
    ck.check(f"B.power_class.{k}: every POWER-class track ({', '.join(POWER_NETS)}) {DESIGN_POWER} mm (design.md)",
             not thin, f"thinner: {thin}")

for k, b in BOARDS:
    drills = []          # (x, y, r_round, r_long, kind, label, net, raw, pad)
    for pad in b.pads:
        raw = FP[b.parts[pad.ref]["fp"]][pad.num]
        if raw["hole"]:
            drills.append((pad.x, pad.y, min(raw["hw"], raw["hh"] or raw["hw"]) / 2, max(raw["hw"], raw["hh"]) / 2, "pad",
                           f"{pad.ref}.{pad.num}", pad.net, raw, pad))
    for x, y, d, D, n in VIAS[k]:
        drills.append((x, y, d / 2, d / 2, "via", f"via {n} ({x:.1f}, {y:.1f})", n, None, None))
    worst = []
    for i in range(len(drills)):
        for j in range(i + 1, len(drills)):
            a, c = drills[i], drills[j]
            if a[4] == c[4] == "pad" and a[5].split(".")[0] == c[5].split(".")[0]:
                continue                    # pins of one part: the footprint's own spacing
            dd = dist(a, c)
            if dd > 6:
                continue
            gap = dd - a[3] - c[3]
            if a[6] and a[6] == c[6]:
                need = JLC_HOLE_HOLE_VIA    # same net: only the drill web matters
            else:
                need = JLC_HOLE_HOLE_VIA if "via" in (a[4], c[4]) else JLC_HOLE_HOLE_PAD
            if gap < need:
                worst.append((round(gap, 3), a[5], c[5], need))
    worst.sort()
    ck.check(f"B.hole_hole.{k}: hole to hole >= JLCPCB's {JLC_HOLE_HOLE_PAD} (pad holes, other nets) / "
             f"{JLC_HOLE_HOLE_VIA} (vias)", not worst, f"{len(worst)} under: {worst[:8]}")
    near = []
    for x, y, r, Rl, kind, label, net, raw, pad in drills:
        for t in b.tracks:
            if t["net"] == net:
                continue
            if min(t["a"][0], t["b"][0]) - Rl - 1 > x or max(t["a"][0], t["b"][0]) + Rl + 1 < x or \
               min(t["a"][1], t["b"][1]) - Rl - 1 > y or max(t["a"][1], t["b"][1]) + Rl + 1 < y:
                continue
            if raw is not None and raw["hole"] != "ROUND":
                s0, s1, rr = ca.Pad("", "", x, y, raw["hw"], raw["hh"], "ELLIPSE", pad.angle, None).axis()
                g = ca.d_seg_seg(s0, s1, t["a"], t["b"]) - rr - t["w"] / 2
            else:
                g = ca.d_point_seg((x, y), t["a"], t["b"]) - t["w"] / 2 - r
            lim = JLC_PTH_TRACK if kind == "pad" else 0.0
            if kind == "pad" and g < lim:
                near.append((round(g, 3), label, t["net"]))
    near.sort()
    ck.check(f"B.pth_track.{k}: plated drill edge to another net's track >= JLCPCB's {JLC_PTH_TRACK} mm", not near,
             f"{len(near)} under: {near[:8]}")
    npth = []
    for hx, hy, hd in b.holes:
        for t in b.tracks:
            g = ca.d_point_seg((hx, hy), t["a"], t["b"]) - t["w"] / 2 - hd / 2
            if g < ca.NPTH_TRACK:
                npth.append((round(g, 3), t["net"], (round(hx, 1), round(hy, 1))))
    ck.check(f"B.npth_track.{k}: mounting hole edge to a track >= {ca.NPTH_TRACK} mm (copper_audit; JLCPCB now says "
             f"{JLC_NPTH_TRACK})", not npth, f"{sorted(npth)[:6]}")

# ====================================================================== C. the breakout against its drill file
try:
    import numpy as np
except ImportError:            # numpy is the suite's one allowed dependency
    np = None
u5 = MB.parts["U5"]
fp_pts = {n: (p.x, p.y) for n, p in u5["pads"].items()}
seed_nums = [str(i) for i in range(1, 41)]
hdr_nums = [n for n in fp_pts if n.startswith("J")]
targets = [(x, y, "seed") for x, y in BO_SEED] + [(x, y, "hdr") for x, y in BO_HDR]


def fit(mirror, theta):
    """Rotate (and mirror) the breakout's holes, then solve the rigid fit to the footprint's pads (Kabsch on
    nearest-neighbour pairs, a few rounds). Returns (worst, rms, transform, pairs)."""
    c, s = math.cos(math.radians(theta)), math.sin(math.radians(theta))

    def pre(x, y):
        y = -y if mirror else y
        return c * x - s * y, s * x + c * y
    T = [pre(x, y) + (kind,) for x, y, kind in targets]
    names = seed_nums + hdr_nums
    A = np.array([fp_pts[n] for n in names])
    B = np.array([(x, y) for x, y, _ in T])
    off = A.mean(0) - B.mean(0)
    Bt = B + off
    rot = np.eye(2)
    for _ in range(6):
        idx = [int(np.argmin(((Bt - a) ** 2).sum(1))) for a in A]
        Q = Bt[idx]
        ma, mq = A.mean(0), Q.mean(0)
        H = (Q - mq).T @ (A - ma)
        U, S, Vt = np.linalg.svd(H)
        Rm = Vt.T @ U.T
        if np.linalg.det(Rm) < 0:
            Vt[1] *= -1
            Rm = Vt.T @ U.T
        Bt = (Bt - mq) @ Rm.T + ma
        rot = Rm @ rot
    idx = [int(np.argmin(((Bt - a) ** 2).sum(1))) for a in A]
    d = np.sqrt(((Bt[idx] - A) ** 2).sum(1))
    pairs = {n: (T[i][2], float(d[k])) for k, (n, i) in enumerate(zip(names, idx))}
    ok_kind = all(pairs[n][0] == ("seed" if n in seed_nums else "hdr") for n in names) and len(set(idx)) == len(idx)
    ang = math.degrees(math.atan2(rot[1, 0], rot[0, 0]))
    return float(d.max()), float(np.sqrt((d ** 2).mean())), ok_kind, ang, Bt, pre, rot, idx


if np is not None:
    fits = {(m, th): fit(m, th) for m in (False, True) for th in (0, 90, 180, 270)}
    best = min(((v[0], k) for k, v in fits.items() if not k[0]))
    worst, rms, ok_kind, ang, Bt, pre, rot, idx = fits[best[1]]
    print(f"      breakout fit: rotation {best[1][1]} + {ang:.4f} deg, worst {worst:.4f} mm, rms {rms:.4f} mm; "
          f"mirrored best {min(v[0] for k, v in fits.items() if k[0]):.4f} mm")
    ck.within("C.breakout_holes: every hole of the footprint's two rows and its J1/J3/J4/J5 lands on a hole of the "
              "breakout's own drill file (best rigid fit, pins unnamed: the pattern is symmetric, so this alone cannot "
              "tell which face is down); worst offset", worst, None, BREAKOUT_FIT_TOL, " mm")

    # VERIFY 2026-11-13: the named fit. The writer's C.breakout_fit claimed "no mirror: the breakout's top faces
    # up" from the unnamed fit above, which maps pin k onto pad 41-k (and J1 onto J3); with the pins named only
    # one face fits.
    def named_fit(mirror):
        names = sorted(BO_PIN)
        A = np.array([fp_pts[n] for n in names])
        B = np.array([(x, -y if mirror else y) for x, y in (BO_PIN[n] for n in names)])
        ma, mb = A.mean(0), B.mean(0)
        U, S, Vt = np.linalg.svd((B - mb).T @ (A - ma))
        Rm = Vt.T @ U.T
        if np.linalg.det(Rm) < 0:                 # a proper rotation only: the mirror is chosen above
            Vt[1] *= -1
            Rm = Vt.T @ U.T
        return float(np.sqrt((((B - mb) @ Rm.T + ma - A) ** 2).sum(1)).max())
    named = {m: named_fit(m) for m in (False, True)}
    side_down = "SMD (Gerber top)" if named[True] < named[False] else "THT (Gerber bottom)"
    print(f"      breakout named fit: as drawn {named[False]:.3f} mm, mirrored {named[True]:.3f} mm -> its "
          f"{side_down} side faces the main board")
    ck.within("C.breakout_fit: every footprint pad lands on the breakout's hole of the same pin (pins 1-40, J1/J3/J4/J5 "
              "named from the breakout's copper; either face down); worst offset", min(named.values()), None,
              BREAKOUT_FIT_TOL, " mm")
    under_room = FEMALE_H + MALE_PLASTIC - TAIL_MAX
    ck.check("C.breakout_tall_side: the face of the breakout the footprint puts towards the main board carries no part "
             f"taller than the room under it ({FEMALE_H} socket + {MALE_PLASTIC} male plastic - {TAIL_MAX} tails = "
             f"{under_room:.1f} mm; its THT side has the 8 x 12 mm cans, the 10.2 mm DC/DC and J2)",
             named[True] < named[False] or BO_THT_TALLEST <= under_room,
             f"{side_down} side down: the THT parts ({BO_THT_TALLEST:.0f} mm) face "
             f"{'the case' if named[True] < named[False] else 'the main board'}")
    ck.check("C.breakout_tools: the 40 Seed positions land on the breakout's 1.2 mm Seed-row holes and the 16 J pins "
             "on its 0.889 mm 1x4 header holes, each on its own hole", ok_kind,
             "a pin landed on the wrong kind of hole or two pins on one")
    # J1/J3 at the end with the empty position: the breakout's 2x5 power header sits beyond that end
    names = seed_nums + hdr_nums
    j13 = [names.index(n) for n in hdr_nums if n[:2] in ("J1", "J3")]
    pw = np.array([pre(x, y) for x, y in BO_PWR])
    # carry the power header holes through the same transform as the fitted holes
    raw_all = np.array([pre(x, y) for x, y, _ in targets])
    # affine from raw_all -> Bt (rigid): solve with the first two non-collinear points
    M = np.linalg.lstsq(np.hstack([raw_all, np.ones((len(raw_all), 1))]), Bt, rcond=None)[0]

    def to_board(pts):
        P = np.array(pts)
        return np.hstack([P, np.ones((len(P), 1))]) @ M
    pw_b = to_board([pre(x, y) for x, y in BO_PWR])
    j13_c = np.array([fp_pts[n] for n in hdr_nums if n[:2] in ("J1", "J3")]).mean(0)
    j45_c = np.array([fp_pts[n] for n in hdr_nums if n[:2] in ("J4", "J5")]).mean(0)
    pwc = pw_b.mean(0)
    ck.check("C.breakout_power_end: the breakout's 2x5 Eurorack header is at the J1 / J3 (+-12 V) end of the footprint",
             np.linalg.norm(pwc - j13_c) < np.linalg.norm(pwc - j45_c),
             f"power header centre ({pwc[0]:.1f}, {pwc[1]:.1f}), J1/J3 ({j13_c[0]:.1f}, {j13_c[1]:.1f}), "
             f"J4/J5 ({j45_c[0]:.1f}, {j45_c[1]:.1f})")
    ol = to_board([pre(BO_OUTLINE[0], BO_OUTLINE[1]), pre(BO_OUTLINE[2], BO_OUTLINE[1]),
                   pre(BO_OUTLINE[2], BO_OUTLINE[3]), pre(BO_OUTLINE[0], BO_OUTLINE[3])])
    bo_box = (float(ol[:, 0].min()), float(ol[:, 1].min()), float(ol[:, 0].max()), float(ol[:, 1].max()))
    x1, y1, x2, y2 = MB.outline
    ck.check("C.breakout_outline_on_board: the breakout's real outline (its GKO, 96.75 x 18.8 mm) lies inside the main "
             "board", bo_box[0] >= x1 and bo_box[1] >= y1 and bo_box[2] <= x2 and bo_box[3] <= y2,
             f"outline ({bo_box[0]:.2f}, {bo_box[1]:.2f})-({bo_box[2]:.2f}, {bo_box[3]:.2f}); footprint housing "
             f"{tuple(round(v, 2) for v in u5['body'])}")
    ck.check("C.breakout_housing: the footprint's drawn housing covers the breakout's real outline (0.2 mm)",
             u5["body"][0] <= bo_box[0] + 0.2 and u5["body"][1] <= bo_box[1] + 0.2 and u5["body"][2] >= bo_box[2] - 0.2
             and u5["body"][3] >= bo_box[3] - 0.2, f"housing {tuple(round(v, 2) for v in u5['body'])}, real "
             f"{tuple(round(v, 2) for v in bo_box)}")
    BREAKOUT_BOX = bo_box
else:
    ck.check("C.breakout_fit: numpy available for the fit", False, "numpy missing")
    BREAKOUT_BOX = u5["body"]

# ====================================================================== D. outlines, holes, panel, cutout
want_holes = sorted((round(front(xf), 2), round(y, 2)) for xf, y in circuit.HOLES_FRONT)
for k, b in BOARDS:
    x1, y1, x2, y2 = b.outline
    ck.check(f"D.outline.{k}: {BOARD_W} x {BOARD_H} mm at the origin (circuit.py / bom.md)",
             abs(x2 - x1 - BOARD_W) < 0.01 and abs(y2 - y1 - BOARD_H) < 0.01 and abs(x1) < 0.01 and abs(y1) < 0.01,
             f"({x1:.2f}, {y1:.2f})-({x2:.2f}, {y2:.2f})")
    ck.check(f"D.bom_size.{k}: bom.md orders the board at 69.6 x 108.0 mm", "69.6 × 108.0 mm" in BOMMD)
    got = sorted((round(hx, 2), round(hy, 2)) for hx, hy, hd in b.holes)
    ck.check(f"D.holes.{k}: four 3.2 mm holes (M3 clearance)", len(b.holes) == 4 and all(abs(hd - 3.2) < 0.01 for *_, hd in b.holes),
             f"{[(round(hx, 2), round(hy, 2), round(hd, 2)) for hx, hy, hd in b.holes]}")
    ck.check(f"D.holes_at.{k}: holes at circuit.HOLES_FRONT mirrored into the PCB frame (0.05 mm)",
             len(got) == 4 and all(dist(a, w) < 0.05 for a, w in zip(got, want_holes)), f"expected {want_holes}, got {got}")
ck.check("D.holes_coincide: the two boards' holes coincide (one standoff each)",
         sorted((round(h[0], 2), round(h[1], 2)) for h in MB.holes) == sorted((round(h[0], 2), round(h[1], 2)) for h in FB.holes))
panel = harness.load("panel")
top_m = panel.PANEL_H - panel.BOARD_Y0 - BOARD_H
ck.within("D.rails_bottom: board edge to the panel's bottom edge (sdiy.info: keep 10 mm clear for the rails)",
          panel.BOARD_Y0, RAIL_CLEAR, None, " mm")
ck.within("D.rails_top: board edge to the panel's top edge (10 mm for the rails)", top_m, RAIL_CLEAR, None, " mm")
ck.within("D.rails_height: board height against the 108-110 mm between the rails (the conservative end)",
          BOARD_H, None, RAIL_PCB_MAX_H, " mm")
ck.check("D.panel_width: the board inside the 14HP panel's width (70.8 mm)", panel.BOARD_X0 >= 0 and
         panel.BOARD_X0 + BOARD_W <= panel.PANEL_W + 1e-6, f"x0 {panel.BOARD_X0:.2f}, panel {panel.PANEL_W}")
# the display cable cutout
ck.check("D.cutout_count: the faceplate has one milled cutout, the main board none", len(FB.cutouts) == 1 and not MB.cutouts,
         f"{len(FB.cutouts)} / {len(MB.cutouts)}")
cx1, cy1, cx2, cy2 = bbox(FB.cutouts[0])
m = re.search(r"(\d+(?:\.\d+)?) × (\d+(?:\.\d+)?) mm\s+cutout", DESIGN)
ck.check("D.cutout_size: the cutout is design.md's 16.7 x 13.5 mm", m is not None and abs(cx2 - cx1 - float(m.group(1))) < 0.02
         and abs(cy2 - cy1 - float(m.group(2))) < 0.02, f"design.md {m and m.groups()}, board {cx2 - cx1:.2f} x {cy2 - cy1:.2f}")
dc = circuit.DISPLAY_CUTOUT
ck.check("D.cutout_at: the cutout where circuit.DISPLAY_CUTOUT puts it (front x 8.0-24.7, y 43.5-57.0, mirrored)",
         abs(cx1 - front(dc[2])) < 0.02 and abs(cx2 - front(dc[0])) < 0.02 and abs(cy1 - dc[1]) < 0.02 and abs(cy2 - dc[3]) < 0.02,
         f"({cx1:.2f}, {cy1:.2f})-({cx2:.2f}, {cy2:.2f})")
raw = next(p for h, p in R.pcb_docs["face"]["recs"] if h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] != "CIRCLE")
path = raw["path"][0]
radii = []
for i, t in enumerate(path):
    if t == "ARC":
        x0, y0 = path[i - 2] * MIL, path[i - 1] * MIL
        xe, ye = path[i + 2] * MIL, path[i + 3] * MIL
        sweep = abs(path[i + 1])
        radii.append(math.hypot(xe - x0, ye - y0) / (2 * math.sin(math.radians(sweep) / 2)))
ck.check("D.cutout_radius: four rounded corners of circuit.DISPLAY_CUTOUT's 1.0 mm (JLCPCB: no square-cornered cutouts; "
         "a 1.0 mm mill leaves r 0.5, assumed)", len(radii) == 4 and all(abs(r - dc[4]) < 0.01 and r >= 0.5 for r in radii),
         f"radii {[round(r, 3) for r in radii]}")
ck.within("D.cutout_width: the cutout's narrow side against JLCPCB's 1.0 mm non-plated slot minimum",
          min(cx2 - cx1, cy2 - cy1), JLC_NPSLOT_MIN, None, " mm")
ck.check("D.cutout_inside: the cutout lies inside the board, 1 mm from its edges",
         cx1 > 1 and cy1 > 1 and cx2 < BOARD_W - 1 and cy2 < BOARD_H - 1)

# ====================================================================== E. value labels
VALUES = vl.values()                 # {'Main' | 'Faceplate': {ref: label text}} from circuit.py
CIRCUIT_VALUE = {p.ref: p.value for p in circuit.all_parts()}
LEGEND = re.compile(r"^(\S+(?: x\d+)?): ((?:[A-Z]+\d+ ?)+)$")
LABEL_MARGIN = 0.3                   # the mixer's M3: own part nearer than any other value's part by 0.3 mm


def strings(k):
    return [p for h, p in R.pcb_docs[k]["recs"] if h["type"] == "STRING" and p.get("layerId") in (3, 4)]


for k, b in BOARDS:
    vals = VALUES["Main" if k == "main" else "Faceplate"]
    labelled = {r for r in vals if r in b.parts}
    texts = set(vals.values())
    traps, ties, wrong_text, small, thin, on_pad, on_hole, legend_bad, wrong_side = [], [], [], [], [], [], [], [], []
    seen, seen_leg, n_labels = collections.Counter(), collections.Counter(), 0
    for p in strings(k):
        txt = p["text"]
        bottom = p["layerId"] == 4
        rect = vl.text_box(p["x"] * MIL, p["y"] * MIL, txt, p["fontSize"], p.get("mirror", False))
        mm = LEGEND.match(txt)
        is_label = txt in texts or bool(mm)
        if not is_label:
            if re.fullmatch(r"[AB]?\d+[RkKMpnuµ]?\d*(?: x\d+)?|1N\d+|BAT\d+|2N\d+", txt):
                wrong_text.append(f"'{txt}' looks like a value but is none of this board's")
            continue
        n_labels += 1
        if p["fontSize"] * MIL < JLC_SILK_H - 1e-6:
            small.append(f"'{txt}' {p['fontSize'] * MIL:.2f} mm")
        if p.get("strokeWidth", 0) * MIL < JLC_SILK_W - 1e-6:
            thin.append(f"'{txt}' {p.get('strokeWidth', 0) * MIL:.3f} mm")
        if bool(p.get("mirror")) != bottom:
            wrong_side.append(f"'{txt}' mirror {p.get('mirror')} on layer {p['layerId']}")
        for pad in b.pads:
            if vl.circle_hits(rect, (pad.x, pad.y), pad.r + JLC_PAD_SILK - 1e-3):
                on_pad.append(f"'{txt}' on {pad.ref}.{pad.num}")
                break
        for hx, hy, hd in b.holes:
            if vl.circle_hits(rect, (hx, hy), hd / 2 + JLC_PAD_SILK):
                on_hole.append(f"'{txt}' on the hole at ({hx:.1f}, {hy:.1f})")
        for poly in b.cutouts:
            if vl.overlaps(rect, bbox(poly), JLC_PAD_SILK):
                on_hole.append(f"'{txt}' on the cutout")
        if mm:
            refs = mm.group(2).split()
            for r in refs:
                seen_leg[r] += 1
                if vals.get(r) != mm.group(1):
                    legend_bad.append(f"'{txt}': {r} is {vals.get(r)}")
                elif vl.rect_dist(rect, vl.extent(b.parts[r])) > vl.REACH:
                    legend_bad.append(f"'{txt}': {r} {vl.rect_dist(rect, vl.extent(b.parts[r])):.1f} mm away")
            continue
        cands = sorted((vl.rect_dist(rect, vl.extent(b.parts[r])), r) for r in labelled if b.parts[r]["bottom"] == bottom)
        same = [c for c in cands if vals[c[1]] == txt]
        other = [c for c in cands if vals[c[1]] != txt]
        if not same:
            wrong_text.append(f"'{txt}' near no part of that value")
            continue
        own_d, own = same[0]
        seen[own] += 1
        if CIRCUIT_VALUE[own].replace(" bussed", "") != txt:
            wrong_text.append(f"'{txt}' on {own}, circuit.py says {CIRCUIT_VALUE[own]}")
        if other and other[0][0] < own_d - 0.02:
            traps.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f}): {other[0][1]} ({vals[other[0][1]]}) "
                         f"{other[0][0]:.2f} mm, {own} {own_d:.2f} mm")
        elif other and other[0][0] < own_d + LABEL_MARGIN:
            ties.append(f"'{txt}' {own} {own_d:.2f} / {other[0][1]} ({vals[other[0][1]]}) {other[0][0]:.2f}")
    ck.check(f"E.label_trap.{k}: no value label nearer a part of another value than its own (value_labels.py's rule, "
             "measured as it measures: text box to the part's housing + pads)", not traps, f"{len(traps)}: {traps}")
    ck.check(f"E.label_margin.{k}: every value label >= {LABEL_MARGIN} mm nearer its own part than any part of another "
             "value (the mixer's M3)", not ties, f"{len(ties)} of {n_labels}: {ties}")
    ck.check(f"E.label_text.{k}: every label states the value circuit.py gives its part", not wrong_text, f"{wrong_text}")
    ck.check(f"E.legend.{k}: legend lines name parts of their value, each within value_labels.REACH ({vl.REACH} mm)",
             not legend_bad, f"{legend_bad}")
    missing = []
    boxes = [(p["text"], p["layerId"] == 4, vl.text_box(p["x"] * MIL, p["y"] * MIL, p["text"], p["fontSize"], p.get("mirror", False)))
             for p in strings(k)]
    for r in sorted(labelled):
        if seen_leg[r]:
            continue
        pl = b.parts[r]
        d = min((vl.rect_dist(rect, vl.extent(pl)) for t, bot, rect in boxes if t == vals[r] and bot == pl["bottom"]), default=99)
        if d > 3.0:
            missing.append(f"{r} ({vals[r]}, nearest {d:.1f} mm)")
    ck.check(f"E.label_cover.{k}: every R / C / network / diode / transistor has a label of its value within 3 mm or a "
             "legend line", not missing, f"{len(labelled)} parts, unlabelled: {missing}")
    ck.check(f"E.label_height.{k}: label text >= JLCPCB's {JLC_SILK_H} mm", not small, f"{small[:6]}")
    ck.check(f"E.label_stroke.{k}: label stroke >= JLCPCB's {JLC_SILK_W} mm", not thin, f"{thin[:6]}")
    ck.check(f"E.label_side.{k}: each label mirrored exactly when it is on the bottom silk", not wrong_side, f"{wrong_side}")
    ck.check(f"E.label_pad.{k}: no label within {JLC_PAD_SILK} mm of a pad (JLCPCB pad to silk)", not on_pad, f"{on_pad[:6]}")
    ck.check(f"E.label_hole.{k}: no label over a mounting hole or the cutout", not on_hole, f"{on_hole}")
    des_small = []
    for h, p in R.pcb_docs[k]["recs"]:
        if h["type"] == "ATTR" and p.get("key") == "Designator" and p.get("valueVisible") and p.get("fontSize"):
            if p["fontSize"] * MIL < JLC_SILK_H - 1e-6 or (p.get("strokeWidth") or 99) * MIL < JLC_SILK_W - 1e-6:
                des_small.append(f"{p['value']} {p['fontSize'] * MIL:.2f} mm / {(p.get('strokeWidth') or 0) * MIL:.3f}")
    ck.check(f"E.designators.{k}: visible designators >= {JLC_SILK_H} mm tall, stroke >= {JLC_SILK_W}", not des_small,
             f"{des_small[:6]}")

# ====================================================================== F. real bodies
def rect_poly(cx, cy, L, W, ang):
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = ca.rot(sx * L / 2, sy * W / 2, ang)
        out.append((cx + dx, cy + dy))
    return out


def axis_angle(P, a, b):
    return math.degrees(math.atan2(P[b].y - P[a].y, P[b].x - P[a].x))


def real_body(k, ref, pl):
    """('circle', (cx, cy), r) or ('poly', corners): the part's real outline on its side (maxima), and its height."""
    fp, P = pl["fp"], pl["pads"]
    mid = lambda a, b: ((P[a].x + P[b].x) / 2, (P[a].y + P[b].y) / 2)
    if fp == "RES-TH-VERTICAL-P2.54":
        return ("circle", (P["1"].x, P["1"].y), R_STAND_D / 2), 6.5 + 2.0
    if fp == "CAP-TH_L3.0-W2.0-P5.08-D0.7":
        L, W, H = CAP_10U if ref == "C4" else CAP_FG28
        return ("poly", rect_poly(*mid("1", "2"), L, W, axis_angle(P, "1", "2"))), H + CAP_STANDOFF
    if fp == "CAP-TH_L7.6-W3.8-P5.08-D0.51":
        return ("poly", rect_poly(*mid("1", "2"), CAP_SR30[0], CAP_SR30[1], axis_angle(P, "1", "2"))), 7.0
    if fp.startswith("DO-35"):
        return ("poly", rect_poly(*mid("1", "2"), DO35_BODY[0], DO35_BODY[1], axis_angle(P, "1", "2"))), DO35_BODY[1]
    if fp.startswith("TO-92"):
        a = axis_angle(P, "1", "3")
        cx, cy = P["2"].x, P["2"].y
        # flat face 1.3 mm from the lead line (footprint silk), the round side opposite: the depth C from the flat
        dx, dy = ca.rot(0, -1.45 + TO92_BODY[1] / 2, a)
        return ("poly", rect_poly(cx + dx, cy + dy, TO92_BODY[0], TO92_BODY[1], a)), 5.2 + 2.0
    if fp.startswith("DIP-"):
        n = len(P)
        cx, cy = sum(p.x for p in P.values()) / n, sum(p.y for p in P.values()) / n
        return ("poly", rect_poly(cx, cy, n / 2 * SOCKET_PITCH_L, SOCKET_W, axis_angle(P, "1", "2"))), SOCKET_H + DIP_A_MAX
    if fp == "SIP-9-P2.54":
        cx, cy = sum(p.x for p in P.values()) / 9, sum(p.y for p in P.values()) / 9
        return ("poly", rect_poly(cx, cy, SIP9_LEN_MAX, SIP_T_MAX, axis_angle(P, "1", "9"))), SIP_H_MAX + SIP_SEAT
    if fp == "DAISY-SEED-POWER-OPAMPS-2.54":
        return ("poly", [(BREAKOUT_BOX[0], BREAKOUT_BOX[1]), (BREAKOUT_BOX[2], BREAKOUT_BOX[1]),
                         (BREAKOUT_BOX[2], BREAKOUT_BOX[3]), (BREAKOUT_BOX[0], BREAKOUT_BOX[3])]), None
    x1, y1, x2, y2 = pl["body"]
    return ("poly", [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]), None


def _proj(poly, ax):
    v = [q[0] * ax[0] + q[1] * ax[1] for q in poly]
    return min(v), max(v)


def separation(a, b):
    """Gap between two outlines (SAT for polygons), negative = overlap depth."""
    if a[0] == "circle" and b[0] == "circle":
        return dist(a[1], b[1]) - a[2] - b[2]
    if a[0] == "circle" or b[0] == "circle":
        c, p = (a, b) if a[0] == "circle" else (b, a)
        poly = p[1]
        d = min(ca.d_point_seg(c[1], poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))
        return (-d - c[2]) if ca.point_in_poly(c[1], poly) else d - c[2]
    best = -1e9
    for poly in (a[1], b[1]):
        for i in range(len(poly)):
            ex, ey = poly[(i + 1) % len(poly)][0] - poly[i][0], poly[(i + 1) % len(poly)][1] - poly[i][1]
            L = math.hypot(ex, ey) or 1
            ax = (-ey / L, ex / L)
            a0, a1 = _proj(a[1], ax)
            b0, b1 = _proj(b[1], ax)
            best = max(best, b0 - a1, a0 - b1)
    return best


def centre(o):
    return o[1] if o[0] == "circle" else (sum(q[0] for q in o[1]) / len(o[1]), sum(q[1] for q in o[1]) / len(o[1]))


BODIES = {}
for k, b in BOARDS:
    for ref, pl in b.parts.items():
        BODIES[(k, ref)] = real_body(k, ref, pl)
for k, b in BOARDS:
    for side in (False, True):
        refs = sorted(r for r, pl in b.parts.items() if pl["bottom"] == side)
        hits = []
        for i, ra in enumerate(refs):
            for rb in refs[i + 1:]:
                A, B = BODIES[(k, ra)][0], BODIES[(k, rb)][0]
                if k == "main" and "U5" in (ra, rb):
                    continue        # the breakout stands 11 mm up on its sockets: its sockets are checked below
                if dist(centre(A), centre(B)) > 30:
                    continue
                s = separation(A, B)
                if s < 0:
                    hits.append((round(s, 2), ra, rb))
        hits.sort()
        ck.check(f"F.bodies.{k}.{'bottom' if side else 'top'}: no two real bodies overlap (datasheet maxima, DIPs in "
                 "their sockets, the 10 uF C4 as a KEMET C324)", not hits, f"{len(hits)} (overlap mm, a, b): {hits[:10]}")
# the breakout's two socket strips on the main board's rear against the parts beside them
u5p = MB.parts["U5"]["pads"]
strips = []                          # one 2.54 mm wide socket strip per pin row (bom.md: 1x24 + 1x4 per row)
for xr in sorted({round(p.x, 2) for p in u5p.values()}):
    col = [p for p in u5p.values() if abs(p.x - xr) < 0.01]
    y0, y1 = min(p.y for p in col) - 1.27, max(p.y for p in col) + 1.27
    strips.append(("poly", [(xr - 1.27, y0), (xr + 1.27, y0), (xr + 1.27, y1), (xr - 1.27, y1)]))
sh = []
for ref, pl in MB.parts.items():
    if ref == "U5" or pl["bottom"]:
        continue
    for st in strips:
        s = separation(st, BODIES[("main", ref)][0])
        if s < 0:
            sh.append((round(s, 2), ref))
ck.check("F.breakout_sockets: the breakout's socket strips on the main board's rear clear every other rear part",
         not sh, f"{sh}")
under = []
for ref, pl in MB.parts.items():
    if ref == "U5" or pl["bottom"]:
        continue
    s = separation(BODIES[("main", "U5")][0], BODIES[("main", ref)][0])
    if s < 0:
        under.append((ref, BODIES[("main", ref)][1]))
clear_under = FEMALE_H + MALE_PLASTIC - TAIL_MAX
ck.check(f"F.under_breakout: what stands under the raised breakout is lower than its underside ({FEMALE_H} socket + "
         f"{MALE_PLASTIC} male plastic - {TAIL_MAX} of its own solder tails = {clear_under:.1f} mm)",
         all(h is not None and h < clear_under for r, h in under), f"under it: {under or 'nothing'}")
holes_under = [h for h in MB.holes if BREAKOUT_BOX[0] - M3_PAN_HEAD_R < h[0] < BREAKOUT_BOX[2] + M3_PAN_HEAD_R
               and BREAKOUT_BOX[1] - M3_PAN_HEAD_R < h[1] < BREAKOUT_BOX[3] + M3_PAN_HEAD_R]
ck.check("F.screws_reachable: no mounting screw head on the main board's rear lies under the breakout (a screwdriver "
         "reaches every screw with the breakout fitted)", not holes_under, f"{holes_under}")

# ====================================================================== G. the stacking gap
gap = FEMALE_H + MALE_PLASTIC
m = re.search(r"(\d+(?:\.\d+)?) mm gap", DESIGN)
ck.close("G.gap_design_md: design.md's board gap equals the 8.5 mm socket on the 2.5 mm male plastic",
         float(m.group(1)) if m else -1, gap, 0.05, " mm")
m = re.search(r"M3 standoff, female-female, (\d+(?:\.\d+)?) mm", BOMMD)
ck.close("G.gap_bom: bom.md's standoff length equals the mated header height", float(m.group(1)) if m else -1, gap, 0.05, " mm")
m = re.search(r"Female header, 2\.54 mm, (\d+(?:\.\d+)?) mm tall", BOMMD)
ck.check("G.female_depth: bom.md's female header is the 8.5 mm the model uses, deep enough for the 6 mm male pin",
         m is not None and abs(float(m.group(1)) - FEMALE_H) < 0.01 and MALE_PIN <= FEMALE_H - 0.5,
         f"bom.md {m and m.group(1)} mm")
ck.check("G.gap_sides: main board bottom = only the female sockets H1-H4; faceplate top holds the male headers and the "
         "logic side", sorted(r for r, pl in MB.parts.items() if pl["bottom"]) == ["H1", "H2", "H3", "H4"]
         and all(not FB.parts[circuit.fb_ref(h)]["bottom"] for h in ("H1", "H2", "H3", "H4")),
         f"main bottom {sorted(r for r, pl in MB.parts.items() if pl['bottom'])}")
DIP_BODY = {16: (19.69, 7.11), 14: (19.69, 7.11), 6: (8.89, 7.11)}   # JEDEC MS-001 D / E1 maxima (16-pin BB 0.775 in,
#   14-pin AA 0.775 in, 6-pin H11L1 package taken at 0.350 in; E1 0.280 in)


def chip_body(pl):
    P = pl["pads"]
    n = len(P)
    cx, cy = sum(p.x for p in P.values()) / n, sum(p.y for p in P.values()) / n
    L, W = DIP_BODY[n]
    return rect_poly(cx, cy, L, W, axis_angle(P, "1", "2"))


# every faceplate rear part's height, plus any main-board solder tail that hangs over it, against the gap
mb_tails = [p for p in MB.pads if not MB.parts[p.ref]["bottom"]]      # rear parts: their tails come out at the gap
# VERIFY 2026-11-13: the tails were all taken at IPC-A-610's 2.5 mm maximum. A part's own fixed tail is what
# protrudes where the builder cannot trim it: the breakout's female socket strips (FEMALE_TAIL 3.2 - 1.6) and the
# main board's DIP sockets (On Shore SA 3.00 - 1.6). Leads the builder trims (diodes, resistors, caps, TO-92)
# keep the IPC-A-610 class 2 maximum, 2.5 mm, since nothing in the docs says to cut them shorter.
SOCKET_TAIL = 3.00       # On Shore SA (SAXXX0X0 rev C): tail below the insulator


def tail_of(ref):
    fp_ = MB.parts[ref]["fp"]
    if fp_ == "DAISY-SEED-POWER-OPAMPS-2.54" or fp_.startswith("HDR-"):
        return FEMALE_TAIL - BOARD_T
    if fp_.startswith("DIP-"):
        return SOCKET_TAIL - BOARD_T
    return TAIL_MAX


over = []
report = []
for ref, pl in sorted(FB.parts.items()):
    if pl["bottom"] or ref.startswith("HF"):
        continue
    body, h = BODIES[("face", ref)]
    if ref == "CN1":
        h = DUPONT + 0.3         # the right-angle header's plastic and the cable's plug lying flat: 2.54 + a little
    if h is None:
        continue
    tails = [p for p in mb_tails if (ca.point_in_poly((p.x, p.y), body[1]) if body[0] == "poly" else dist((p.x, p.y), body[1]) < body[2])]
    if pl["fp"].startswith("DIP-") and ("Faceplate", ref) in harness.load("bom").SOLDERED:
        # 2026-11-14: the BOM solders this chip without a socket: the chip's seated height, tails over the chip only
        chip = chip_body(pl)
        h, tails = DIP_A_MAX, [p for p in tails if ca.point_in_poly((p.x, p.y), chip)]
    elif pl["fp"].startswith("DIP-"):        # over the socket frame only the socket counts; over the chip, both
        chip = chip_body(pl)
        on_chip = [p for p in tails if ca.point_in_poly((p.x, p.y), chip)]
        if not on_chip:
            h = SOCKET_H
        tails = on_chip or tails
    t = max((tail_of(p.ref) for p in tails), default=0.0)
    report.append(f"{ref} {h:.1f}+{t:.1f}")
    if h + t > gap:
        over.append(f"{ref}: {h:.2f} mm tall + {t:.2f} mm tails of {sorted({p.ref for p in tails})} = {h + t:.2f} > {gap:.1f}")
print(f"      faceplate rear heights + main tails over them (mm): {', '.join(report)}")
ck.check(f"G.faceplate_rear_height: every faceplate rear part, plus the main board's solder tails above it (socket-strip "
         f"tails {FEMALE_TAIL - BOARD_T:.1f}, DIP-socket tails {SOCKET_TAIL - BOARD_T:.1f}, trimmed leads {TAIL_MAX} max "
         f"IPC-A-610 class 2), fits the {gap:.1f} mm gap (socket {SOCKET_H} + chip {DIP_A_MAX} MS-001 max)", not over,
         f"{over}")
typ_over = []
for ref in ("U1", "U2"):
    tails = [p for p in mb_tails if ca.point_in_poly((p.x, p.y), chip_body(FB.parts[ref]))]
    if tails:
        t = max(tail_of(p.ref) if tail_of(p.ref) < TAIL_MAX else TAIL_TYP for p in tails)
        typ_over.append((ref, round(4.43 + 4.57 + t, 2), sorted({p.ref for p in tails})))
# 4.43 = On Shore SA nominal; 4.57 (0.180 in) a typical PDIP seated height: NOT SOURCED (no maker gives a typical A)
ck.check("G.dip_under_tails_typ: U1 / U2 in their sockets under main-board tails still fit at typical heights (On Shore "
         "SA 4.43 + chip 4.57 typ + the tail: socket strip 1.6 / trimmed lead 1.5)", all(h <= gap for _, h, _ in typ_over),
         f"{typ_over}")
# tails facing tails: faceplate panel-side parts' leads come out on its rear, the main board's on its front.
# VERIFY 2026-11-13: this compared 2 x TAIL_MAX with the gap, constants only, so it could not fail; it now adds the
# real tails pair by pair: panel-side terminals behind the bodies (Thonk PJ398SM drawing 3.5, Bourns PEC11R side
# view 3.7, Thonk LED button 3.5) less the 1.6 mm board, and the main board's tail_of().
FB_TERMINAL = {"CONN-TH_WQP-WQP518MA": 3.5, "JACK-PJ366ST-STEREO": 3.5, "ENC-EC11E-SW-VERTICAL": 3.7,
               "SW-TACT-LP-LED-THONK": 3.5}
fb_tails = [p for p in FB.pads if FB.parts[p.ref]["bottom"]]
facing, worst_pair = 0, (0.0, "")
for p in fb_tails:
    for q in mb_tails:
        if dist((p.x, p.y), (q.x, q.y)) < (p.r + q.r):
            facing += 1
            s = FB_TERMINAL.get(FB.parts[p.ref]["fp"], BOARD_T + TAIL_MAX) - BOARD_T + tail_of(q.ref)
            if s > worst_pair[0]:
                worst_pair = (s, f"{p.ref}.{p.num} / {q.ref}.{q.num}")
ck.check(f"G.tails_facing: where faceplate and main-board solder tails face each other, the two tails leave >= 1 mm "
         f"in the {gap:.1f} mm gap", worst_pair[0] <= gap - 1.0,
         f"{facing} tail pairs face each other; the longest pair {worst_pair[0]:.2f} mm ({worst_pair[1] or 'none'})")
c4 = FB.parts["C4"]
ck.check("G.c4_height: C4 (10 uF ceramic, KEMET C324 H 5.84 max + 1 mm lead kink) stands below the gap; an electrolytic "
         "(5 x 11 mm) would not, as design.md says", CAP_10U[2] + CAP_STANDOFF < gap and 11.0 + 0.5 > gap,
         f"{CAP_10U[2] + CAP_STANDOFF:.2f} mm")

# ====================================================================== H. the display stack in the panel gap
panel_gap = min(JACK_SHOULDER)
# VERIFY 2026-11-13: the gap is now Thonk's drawing (9.0 +-0.15), the encoder body Bourns' (6.5 +-0.3). The panel
# rests on the jacks; the encoders stand below it (test_panel's D.enc_body_gap / D.enc_thread_through_panel
# take up what that means for their nuts).
ck.check("H.panel_gap_parts: the encoders' bushing base is not above the jacks' front face (the panel rests on the jacks)",
         max(ENC_SHOULDER) <= min(JACK_SHOULDER), f"jacks {JACK_SHOULDER} (Thonk), encoders {ENC_SHOULDER} (Bourns)")
stack = TAPE + LCD_GLASS + LCD_PCB
ck.within("H.module_fits: the module's glass + PCB + tape fit the smallest panel gap", stack, None, panel_gap, " mm")
back = max(LCD_ZIF, LCD_FLEX)
ck.within("H.module_back_parts: glass + PCB + tape + the ZIF / flex bend on the module's back (outside the cutout) fit "
          "the panel gap", stack + back, None, panel_gap, " mm")
ck.within("H.module_studs: with the 3D model's M2 x 2.5 studs fitted the module still fits (else design.md should say "
          "to remove them)", stack + LCD_STUD, None, panel_gap, " mm")
m = re.search(r"stands about (\d+(?:\.\d+)?) mm\s+proud", DESIGN)
ck.close("H.connector_proud: design.md's 'stands about 3.5 mm proud' matches the 3D model's MX1.25 header",
         float(m.group(1)) if m else -1, LCD_CONN, 0.2, " mm")
reach = stack + LCD_CONN - panel_gap
ck.within("H.connector_in_cutout: the connector reaches into the faceplate cutout by no more than the board's 1.6 mm "
          "plus the plug's room (it ends inside the 11 mm gap)", reach, None, BOARD_T + gap, " mm")
dm = circuit.DISPLAY_MODULE
top = dm[3]
ax = (dm[0] + dm[2]) / 2
conn = (dm[0] + LCD_CONN_ACROSS[0], top - LCD_CONN_FROM_FLEX[1], dm[0] + LCD_CONN_ACROSS[1], top - LCD_CONN_FROM_FLEX[0])
conn_m = (dm[2] - LCD_CONN_ACROSS[1], conn[1], dm[2] - LCD_CONN_ACROSS[0], conn[3])
cut = (front(cx2), cy1, front(cx1), cy2)
inside = lambda r: r[0] >= cut[0] + 0.3 and r[2] <= cut[2] - 0.3 and r[1] >= cut[1] + 0.3 and r[3] <= cut[3] - 0.3
ck.check("H.cutout_under_connector: the 3D model's connector footprint (front view, either way across) lies inside "
         "the faceplate cutout with 0.3 mm to spare", inside(conn) and inside(conn_m),
         f"connector {tuple(round(v, 2) for v in conn)}, cutout {tuple(round(v, 2) for v in cut)}")
ck.check("H.connector_model_vs_circuit: circuit.DISPLAY_CONNECTOR (34.3-38.5 mm from the flex end, +-7.8 across) covers "
         "the 3D model's header (0.25 mm)", circuit.DISPLAY_CONNECTOR[0] <= conn[0] + 0.25 and circuit.DISPLAY_CONNECTOR[2] >= conn[2] - 0.25
         and circuit.DISPLAY_CONNECTOR[1] <= conn[1] + 0.25 and circuit.DISPLAY_CONNECTOR[3] >= conn[3] - 0.25,
         f"circuit {circuit.DISPLAY_CONNECTOR}, model {tuple(round(v, 2) for v in conn)}")
ck.close("H.module_size: circuit.DISPLAY_MODULE is the Waveshare 27.3 x 51.2 mm module (wiki)",
         (dm[2] - dm[0]) + (dm[3] - dm[1]), LCD_W + LCD_L, 0.05, " mm")
zif = (top - LCD_ZIF_FROM_FLEX[1], top - LCD_ZIF_FROM_FLEX[0])
# VERIFY 2026-11-13: wording only: at the 9 mm gap the ZIF (2.0 proud) ends 3.15 mm short of the faceplate; it
# would only bear on it in a gap under 5.7 mm
ck.check("H.zif_outside_cutout: the module's ZIF connector (2.0 mm proud) is outside the cutout, so it lies over the "
         "faceplate and counts in H.module_back_parts", zif[0] > cut[3] or zif[1] < cut[1], f"ZIF y {zif[0]:.1f}-{zif[1]:.1f}")
cn = FB.parts["CN1"]["body"]
run = (max(cn[0], cx1), cy2, min(cn[2], cx2), cn[1])          # PCB frame: plug end down to the cutout's top edge
in_run = [r for r, pl in FB.parts.items() if not pl["bottom"] and r != "CN1"
          and separation(("poly", [(run[0], run[1]), (run[2], run[1]), (run[2], run[3]), (run[0], run[3])]), BODIES[("face", r)][0]) < 0]
tails_run = [f"{p.ref}.{p.num}" for p in FB.pads if run[0] < p.x < run[2] and run[1] < p.y < run[3]]
ck.check("H.cable_run: nothing stands or sticks out on the faceplate's rear between CN1's plug and the cutout, where the "
         "display cable lies", not in_run and not tails_run and run[3] > run[1],
         f"run ({run[0]:.1f}, {run[1]:.1f})-({run[2]:.1f}, {run[3]:.1f}); parts {in_run}, pads {tails_run}")
leads_behind = [f"{p.ref}.{p.num}" for p in FB.pads if dm[0] - p.r < front(p.x) < dm[2] + p.r and dm[1] - p.r < p.y < dm[3] + p.r]
ck.check("H.nothing_behind_module: no pad (no lead) on the faceplate behind the module", not leads_behind, f"{leads_behind}")

# ====================================================================== I. copper
def barrels():
    out = []
    for ref, *_ in circuit.JACKS:
        pl = FB.parts[ref]
        s, t = pl["pads"]["1"], pl["pads"]["3"]
        d = dist((s.x, s.y), (t.x, t.y))
        out.append((s.x + (t.x - s.x) / d * THONK_SLEEVE, s.y + (t.y - s.y) / d * THONK_SLEEVE, ref))
    return out


def disc_points(c, r, step=0.1):
    pts = []
    n = int(r / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if (i * step) ** 2 + (j * step) ** 2 <= r * r:
                pts.append((c[0] + i * step, c[1] + j * step))
    return pts


sig, gnd = [], []
for bx, by, ref in barrels():
    for t in FB.tracks:
        if t["layer"] == 2 and ca.d_point_seg((bx, by), t["a"], t["b"]) - t["w"] / 2 < THONK_TIP_R:
            (gnd if t["net"].startswith("GND") else sig).append(f"{ref}: track {t['net']}")
    for x, y, d, D, n in VIAS["face"]:
        if dist((x, y), (bx, by)) - D / 2 < THONK_TIP_R:
            (gnd if n.startswith("GND") else sig).append(f"{ref}: via {n} {dist((x, y), (bx, by)):.2f} mm")
    for p in FB.pads:
        if p.ref != ref and p.d_point((bx, by)) < THONK_TIP_R:
            (gnd if (p.net or "").startswith("GND") else sig).append(f"{ref}: pad {p.ref}.{p.num}")
    pts = disc_points((bx, by), THONK_TIP_R)
    for isl in FB.islands:
        if isl.layer == 2 and any(isl.contains(q) for q in pts):
            (gnd if isl.net.startswith("GND") else sig).append(f"{ref}: {isl.net} pour")
ck.check(f"I.tip_circle_signal: no signal copper on the panel side within {THONK_TIP_R} mm of a barrel centre (Thonk: "
         "a 3 mm hole or no copper under the barrel, where a plug tip reaches)", not sig, f"{sig}")
ck.check(f"I.tip_circle_ground: no copper at all on the panel side within {THONK_TIP_R} mm of a barrel centre (Thonk's "
         "note asks for none; ground there only grounds a plug tip through its source's output resistor)", not gnd,
         f"{len(gnd)}: {sorted(set(g.split(': ')[1].split(' ')[0] + ' ' + g.split(': ')[1].split(' ')[1] for g in gnd))} "
         f"at {sorted(set(g.split(':')[0] for g in gnd))}")

for k, b in BOARDS:
    ground = "GND" if k == "main" else ("GND_F", "GND_D_F")
    pads_u, vias_u, tracks_u = [], [], []
    for hx, hy, hd in b.holes:
        Rr = max(M3_STANDOFF_R, M3_PAN_HEAD_R)
        for p in b.pads:
            if p.d_point((hx, hy)) < Rr + 0.2:
                # VERIFY 2026-11-13: say where the lead itself is (the pad centre): a hex corner over a pad's edge
                # touches flat copper, over the lead it would sit on the solder tail
                pads_u.append(f"{p.ref}.{p.num} ({p.net}) pad edge {p.d_point((hx, hy)):.2f} mm, lead "
                              f"{dist((p.x, p.y), (hx, hy)):.2f} mm from the hole centre")
        for x, y, d, D, n in VIAS[k]:
            if dist((x, y), (hx, hy)) - D / 2 < Rr and not n.startswith(ground):
                vias_u.append(f"via {n} at ({hx:.1f}, {hy:.1f})")
        for t in b.tracks:
            g = ca.d_point_seg((hx, hy), t["a"], t["b"]) - t["w"] / 2
            if g < Rr and not t["net"].startswith(ground):
                tracks_u.append(f"{t['net']} layer {t['layer']} {g - hd / 2:.2f} mm from the hole edge at ({hx:.1f}, {hy:.1f})")
    ck.check(f"I.pads_under_hardware.{k}: no pad under an M3 standoff (hex, r {M3_STANDOFF_R:.2f}) or pan head "
             f"(r {M3_PAN_HEAD_R:.2f}) + 0.2", not pads_u, f"{pads_u}")
    ck.check(f"I.vias_under_hardware.{k}: no via but ground under a standoff or screw head", not vias_u, f"{vias_u}")
    ck.check(f"I.tracks_under_hardware.{k}: no signal track under a standoff or screw head (masked, but a metal "
             "standoff that scratches through shorts it)", not tracks_u, f"{len(tracks_u)}: {sorted(set(tracks_u))[:8]}")
    x1, y1, x2, y2 = b.outline
    e_tr = min(min(min(q[0] - x1, x2 - q[0], q[1] - y1, y2 - q[1]) - t["w"] / 2 for q in (t["a"], t["b"])) for t in b.tracks)
    e_via = min(min(x - x1, x2 - x, y - y1, y2 - y) - D / 2 for x, y, d, D, n in VIAS[k])
    e_pad = min(min(p.x - p.r - x1, x2 - p.x - p.r, p.y - p.r - y1, y2 - p.y - p.r) for p in b.pads)
    e_pour = min(min(q[0] - x1, x2 - q[0], q[1] - y1, y2 - q[1]) for isl in b.islands for q in isl.outline)
    e = min(e_tr, e_via, e_pad, e_pour)
    ck.within(f"I.edge_fab.{k}: copper (tracks, vias, pads, pours) to the board edge against JLCPCB's {JLC_EDGE} mm",
              e, JLC_EDGE, None, " mm")
    ck.within(f"I.edge_design.{k}: copper to the board edge against design.md's {DESIGN_EDGE} mm rule", e, DESIGN_EDGE - 1e-3,
              None, " mm", f"tracks {e_tr:.2f}, vias {e_via:.2f}, pads {e_pad:.2f}, pours {e_pour:.2f}")
    cl = b.clearances(0.3)
    md = min((c[0] for c in cl), default=0.3)
    ck.within(f"I.gap_fab.{k}: smallest gap between copper of different nets against {JLC_SPACING} mm", md, JLC_SPACING,
              None, " mm", cl[0][1] if cl else "nothing under 0.3 mm")
    under = [f"{c[0]:.3f} {c[1]}" for c in cl if c[0] < BOARD_RULE - 1e-3]
    ck.check(f"I.gap_rule.{k}: no gap under the board's {BOARD_RULE} mm rule (1 um rounding allowed)", not under,
             f"{under[:6]}")
# copper at the cutout, pours included
poly = FB.cutouts[0]
edges = list(zip(poly, poly[1:] + poly[:1]))
cu = []
for t in FB.tracks:
    g = min(ca.d_seg_seg(t["a"], t["b"], e0, e1) for e0, e1 in edges) - t["w"] / 2
    if g < CUTOUT_EDGE or ca.point_in_poly(t["a"], poly):
        cu.append(f"track {t['net']} {g:.2f}")
for x, y, d, D, n in VIAS["face"]:
    g = min(ca.d_point_seg((x, y), e0, e1) for e0, e1 in edges) - D / 2
    if g < CUTOUT_EDGE:
        cu.append(f"via {n} {g:.2f}")
for isl in FB.islands:
    g = min(ca.d_point_seg(q, e0, e1) for q in isl.outline for e0, e1 in edges)
    inside_c = any(ca.point_in_poly(q, poly) for q in isl.outline)
    if inside_c or (g < CUTOUT_EDGE - 1e-3 and not any(isl.contains(q) for q in poly)):
        cu.append(f"{isl.net} pour layer {isl.layer} {g:.2f}{' inside' if inside_c else ''}")
ck.check(f"I.cutout_copper: copper (pours included) >= {CUTOUT_EDGE} mm from the milled cutout", not cu, f"{cu}")
# pour islands: dead copper and slivers
try:
    import numpy as np
except ImportError:
    np = None


def inscribed_r(poly, step=0.01):
    P = np.array(poly, float)
    x0, y0 = P.min(0)
    x1, y1 = P.max(0)
    gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    A, B = P, np.roll(P, -1, 0)
    inside = np.zeros(len(pts), bool)
    for (ax_, ay), (bx_, by) in zip(A, B):
        cond = (ay > pts[:, 1]) != (by > pts[:, 1])
        xs_ = ax_ + (pts[:, 1] - ay) * (bx_ - ax_) / ((by - ay) or 1e-12)
        inside ^= cond & (pts[:, 0] < xs_)
    pts = pts[inside]
    if not len(pts):
        return 0.0
    best = np.full(len(pts), np.inf)
    for (ax_, ay), (bx_, by) in zip(A, B):
        dx, dy = bx_ - ax_, by - ay
        L2 = dx * dx + dy * dy or 1e-12
        t = np.clip(((pts[:, 0] - ax_) * dx + (pts[:, 1] - ay) * dy) / L2, 0, 1)
        best = np.minimum(best, np.hypot(pts[:, 0] - ax_ - t * dx, pts[:, 1] - ay - t * dy))
    return float(best.max())


for k, b in BOARDS:
    groups, _ = b.connectivity()
    dead, slivers, held = [], [], []
    for i, isl in enumerate(b.islands):
        grp = next((g for g in groups.get(isl.net, {}).values() if ("island", i) in g), set())
        a = island_area(isl)
        x1, y1, x2, y2 = bbox(isl.outline)
        desc = f"{isl.net} layer {isl.layer} {a:.3f} mm2 at ({x1:.1f}, {y1:.1f})-({x2:.1f}, {y2:.1f})"
        if not any(q[0] == "pad" for q in grp):
            dead.append(desc)
        elif a < 30:
            held.append(desc)
        if a < SLIVER_AREA and np is not None:
            w = 2 * inscribed_r(isl.outline)
            if w < SLIVER_W:
                slivers.append(f"{desc}, at most {w:.2f} mm wide")
    print(f"      {k}: {len(b.islands)} pour islands; small ones held to their net: {held}")
    ck.check(f"I.dead_copper.{k}: no pour island joined to no pad (dead copper, any size)", not dead, f"{dead}")
    ck.check(f"I.slivers.{k}: no pour piece under {SLIVER_AREA} mm2 narrower than {SLIVER_W} mm (lifts in etching; JLCPCB "
             "states no minimum area, house rule)", not slivers, f"{slivers}")

ck.done()
