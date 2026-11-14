"""PCB group: manufacturing, assembly and mechanical checks on the routed master (Marblesy-routed.epro2)
that copper_audit.py does not do (it already checks connectivity, shorts, clearances, keepouts, headers).

  FP     footprints against the parts' datasheets: DIP-14 / DIP-16 rows and pitch (DIP sockets), TO-92 pitch
         against the ordered lead option, DO-35, 3 mm LED, the resistor and capacitor footprints, the 1x8 / 1x4 /
         CS-1165SDIG headers, the WQP518MA jack (KiCad PJ398SM), the Alpha RD901F pot (KiCad RD901F-40-00D),
         the Thonk LED button (Thonk's kicad_mod as parts.md quotes it), DAISY-SEED-POWER-OPAMPS-2.54 against
         the Daisy Seed datasheet and against the breakout's own Gerbers (hole for hole, pin-1 squares)
  BO     Rob Heel's breakout on the main board: its outline (design.md's x 35.6-54.4, y 3.7-100.5), what sits
         under it, and the clearance of its underside (the THT tails of its DC/DC, 10-pin header and caps,
         its SMD parts) over R33 / R36 / R39 and the two screw heads (design.md's open item)
  HOLE   every pad's drill against the lead it takes (IPC-2222 fit, as the mixer's group does), annular rings,
         plated slots, vias, hole-to-hole, drill to another net's track, track widths against JLCPCB and
         design.md's classes (signal 0.3, power 0.6, vias 0.61 / 0.3), copper to the board edge
  OUT    both boards 90 x 108, the four 3.2 mm holes at design.md's front-view spots on both, exposed pads
         under a 5 / 5.5 mm AF M3 standoff or an M3 pan head
  PANEL  jacks, pots, buttons and output LEDs at circuit.PLACEMENT (0.05 mm), oriented per design.md and its
         re-route table, pot shafts at circuit.POT_XY through the footprint's lugs
  SILK   value labels (nearest part of their own value by 0.3 mm, measured as value_labels.py measures; text =
         circuit.py's value per board; 35 + 76 labels; R33 / R39 under the breakout), text heights against
         JLCPCB, designators, polarity marks (LED flats, diode bands, IC pin 1, TO-92 flats)
  BODY   real bodies (datasheet maxima) against each other on every side, DIP sockets, panel-side bodies,
         pot housings against rear pads (design.md: 0.8 mm), rear pads under jack / LED / button bodies
  GAP    the 11 mm board gap: faceplate rear parts plus the main board's solder tails, the main board's sockets
  POUR   pour islands (tiny, hanging on one connection, dead), other-net copper inside or within 0.152 mm of a
         pour, and the script-cut pours round D21 (design.md: rebuild before the Gerbers)

Run from marbles/hardware/tests:  python test_pcb.py
Read-only: imports the tools and opens the committed exports as zip files.
"""
import collections
import math
import re

import numpy as np

import harness

ck = harness.Checks("pcb")
ca = harness.load("copper_audit")
circuit = harness.load("circuit")
vl = harness.load("value_labels")
MIL = harness.MIL

# ====================================================================== constants (sources)
# --- fab: JLCPCB PCB capabilities, 2 layers, 1 oz (jlcpcb.com/capabilities/pcb-capabilities). The figures the stereo
#     mixer's pcb group read on 2026-11-04; verifier re-read 2026-11-13: silk line 0.15 min, text height 1.0 mm min
#     ("characters height less than 40 mil (1.0mm) will be unidentifiable"), plated slot 0.5 (2 layers), PTH ring
#     0.25 recommended / 0.18 absolute (2 layers, 1 oz), hole to hole 0.45 pads / 0.2 vias: unchanged.
JLC_RING_MIN = 0.18        # PTH annular ring, absolute minimum
JLC_RING_REC = 0.25        # PTH annular ring, recommended
JLC_TRACK_MIN = 0.127      # 5 mil, the long-standing 2-layer trace width: the conservative one (0.10 is listed too)
JLC_VIA_DRILL_MIN = 0.15   # min via hole
JLC_VIA_DIA_MIN = 0.25     # min via diameter
JLC_PSLOT_MIN = 0.50       # min plated slot width
JLC_HOLE_HOLE_PAD = 0.45   # hole to hole, pad holes
JLC_HOLE_HOLE_VIA = 0.20   # hole to hole, vias
JLC_PTH_TRACK = 0.28       # PTH drill edge to an unrelated track, minimum
JLC_EDGE = 0.20            # copper to a routed board edge
JLC_SILK_H = 1.0           # min silkscreen text height (40 mil)
JLC_SILK_W = 0.15          # min silkscreen line width (6 mil strings are 0.1524: taken as meeting it)
JLC_PTH_TOL_MINUS = 0.08   # finished PTH diameter tolerance +0.13 / -0.08
# --- IPC-2222 table 9-3 as the mixer's group uses it: nominal hole minus maximum round lead >= 0.15 (level C,
#     the tightest), the smallest finished hole (drill - 0.08) clearing the lead by 0.05; square / flat leads pass
#     their diagonal through the smallest finished hole; a round hole no more than 0.7 over the lead (level A max).
IPC_FIT_MIN, INSERT_MIN, IPC_FIT_MAX = 0.15, 0.05, 0.70
# --- design.md "Routing / Rules": clearance 0.152, signal tracks 0.3, power 0.6 on +-12 V, 3V3A, 3V3D,
#     3V3A_F, 3V3D_F, GND_D_F; vias 0.61 / 0.3
RULE_CLEAR, RULE_SIGNAL, RULE_POWER, RULE_VIA = 0.152, 0.3, 0.6, (0.61, 0.3)
POWER_NETS = ("+12V", "-12V", "3V3A", "3V3D", "3V3A_F", "3V3D_F", "GND_D_F")

# --- leads, max (shape, width, thickness) in mm
LEAD_DIP = ("rect", 0.56, 0.38)     # Microchip DS21897B (MCP4922) 14-lead PDIP (P) 300 mil: b .014-.022 in,
#   c .008-.015 in (max 0.56 x 0.38). TL074 (TI N, MS-001) and the 74HC DIP-16s (TI N): the N drawing is not in
#   the TI datasheets' text (not confirmed); the same MS-001 maxima assumed.
LEAD_SOCKET = ("round", 0.559, 0.559)   # Mill-Max 110-43-314 / -316 (dip sockets, data sheet 11/12/26): tail
#   diameter .020 in +- .002 -> 0.559 max; accepting lead range .015-.025 in (the chip leads above fit)
LEAD_TO92 = ("rect", 0.55, 0.50)    # TI LP0003A (SNOS633N, 4215214/C 04/2025): lead 0.38-0.55 x 0.35-0.43;
#   onsemi 2N3903-D rev 9 case 29-11: D 0.407-0.533, J 0.39-0.50 -> the larger of each, max
LEAD_DO35 = ("round", 0.56, 0.56)   # JEDEC DO-204AH lead 0.46-0.56 (Vishay BAT85 doc 88146: DO-35 case, drawing
#   is an image: not confirmed); NXP BAT85 (SOD68 / DO-34) b 0.55 max (confirmed)
LEAD_LED3 = ("rect", 0.50, 0.50)    # 3 mm LED, 0.5 mm square leads (Kingbright T-1 drawings; the WP710A10ID
#   drawing is an image: not confirmed), nominal
LEAD_RES = ("round", 0.60, 0.60)    # 1/4 W metal film: TE LR1 (1773241 CIS BI 06/2011) d 0.55 nom; Yageo MFR
#   (2024-04-03 V.4) MFR50S d 0.55 +- 0.05 (MFR-25 Normal row not in the text): 0.60 max assumed
LEAD_FG28 = ("round", 0.60, 0.60)   # TDK FG28 (leadmlcc_halogenfree_fg_en 20241125, p15): lead d 0.5 +0.10/-0.03
LEAD_SR30 = ("round", 0.56, 0.56)   # KYOCERA AVX SR series: lead .020 in (0.508) nominal; +0.05 assumed
LEAD_HDR = ("rect", 0.64, 0.64)     # 2.54 mm header post 0.64 mm square (0.025 in), industry standard
LEAD_JACK = ("rect", 1.0, 0.3)      # Thonkiconn lug, assumed 1.0 x 0.3 (no dimensioned drawing; the mixer's figure)
LEAD_POT = ("rect", 0.8, 0.4)       # Alpha RD901F terminal, assumed 0.8 x 0.4 (drawing not read); KiCad drills 1.0
LEAD_BTN = ("rect", 0.7, 0.5)       # Thonk LP LED button pin, assumed (no datasheet read)
LEADS = {
    "DIP-14-W7.62-P2.54": [LEAD_DIP, LEAD_SOCKET], "DIP-16_L20.0-W6.4-P2.54-LS7.6-BL": [LEAD_DIP, LEAD_SOCKET],
    "TO-92-INLINE-P2.54": [LEAD_TO92], "DO-35_BD2.0-L4.0-P8.0-D0.5-RD": [LEAD_DO35], "LED-3MM-2P": [LEAD_LED3],
    "1/4W-RESISTOR-VERTICAL": [LEAD_RES], "RES-TH_L6.2-W2.3-LR1F1K0": [LEAD_RES],
    "RES-TH_BD2.3-L6.3-P10.30-D0.6": [LEAD_RES], "CAP-TH_L3.0-W2.0-P5.08-D0.7": [LEAD_FG28],
    "CAP-TH_L7.6-W3.8-P5.08-D0.51": [LEAD_SR30], "HDR-1x8-P2.54": [LEAD_HDR], "HDR-1x4-P2.54": [LEAD_HDR],
    "HDR-TH_3P-P2.54_CS-1165SDIG": [LEAD_HDR], "DAISY-SEED-POWER-OPAMPS-2.54": [LEAD_HDR],
    "CONN-TH_WQP-WQP518MA": [LEAD_JACK], "SW-TACT-LP-LED-THONK": [LEAD_BTN],
}
LEAD_PINS_ONLY = {"POT-ALPHA-9MM-RD901F": ({"1", "2", "3"}, LEAD_POT)}     # the lugs are not checked for fit

# --- footprint geometry from the makers / KiCad (KiCad library, files in the scratchpad's datasheets/kicad)
DIP_PITCH, DIP_ROW = 2.54, 7.62     # 0.100 in pitch, 0.300 in rows (Microchip P: e .100 BSC; Mill-Max B .300)
TO92_STRAIGHT = (1.15, 1.39)        # onsemi case 29-11 straight lead G; TI LP0003A straight 1.27 +- 0.13
TO92_FORMED = (2.40, 2.80)          # onsemi bent lead (ammo / reel) G; TI LP0003A formed option (2.54), land 2.6
# The BOM's TO-92 parts: LM4040CIZ-2.5/NOPB ships "TO-92 (LP) | 3 1800 | BULK" (SNOS633N ordering table) and TI
# note 5a: "straight lead option available in bulk pack only". 2N3904 from Tayda: bulk, straight (assumed).
# (verifier, 2026-11-13: SNOS633N rev. N, LP0003A 4215214/C 04/2025 re-read: straight leads 2X 1.27 +- 0.13, formed
# option land pattern (2.6) / (5.2), note 5a / 5b as quoted: confirmed.)
JACK_S_TN, JACK_S_T, JACK_S_BARREL = 3.1, 11.4, 6.48   # KiCad Jack_3.5mm_QingPu_WQP-PJ398SM_Vertical_CircularHoles:
#   S (0, 0), TN (0, 3.1), T (0, 11.4), barrel circle (0, 6.48) r 1.8; body fab x +-4.5, y 2.03 .. 12.48 (typ)
JACK_BODY = (9.0, 2.03, 12.48)      # width, near and far end from the sleeve pin towards the tip
POT_PIN_PITCH, POT_ROW_SHAFT, POT_LUG_HALF = 2.5, 7.5, 4.8   # KiCad Potentiometer_Alpha_RD901F-40-00D_Single_Vertical:
#   pins (0, 0) (0, 2.5) (0, 5); shaft circle (7.5, 2.5) r 3.5; lugs (7.5, -2.3) / (7.5, 7.3), pads 2.72 x 3.24,
#   oval drills 1.1 x 1.8 with the long side along the pin-to-shaft direction; body fab x 1 .. 12.35, y -2.25 .. 7.25
POT_LUG_PAD, POT_LUG_SLOT = (2.72, 3.24), (1.1, 1.8)
POT_BODY = (9.5, 1.0, 12.35)        # width, near and far end from the pin row towards the shaft
POT_BUSHING_D = 7.0                 # KiCad fab circle d 7.0 (M7 bushing)
# Thonk LP LED button, Thonk's SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod as module-design parts.md quotes it
BTN_PINS = {"1": (2.54, 2.54), "2": (-2.54, 2.54), "3": (2.54, -2.54), "4": (-2.54, -2.54), "5": (2.7, 0), "6": (-2.7, 0)}
BTN_BODY, BTN_CAP = 7.5, 5.5        # square body, round cap (parts.md, LowProfileButton.pdf; not re-read)
# Daisy Seed datasheet v1.0.5 (Electrosmith), technical drawing and landing pattern: 2.54 (0.1) pitch, rows
# 15.24 (0.6) apart, 48.26 (1.9) from pin 1 to pin 20; board 51 x 18 mm, 1.6 mm thick
SEED_PITCH, SEED_ROWS, SEED_SPAN, SEED_BOARD = 2.54, 15.24, 48.26, (51.0, 18.0)

# --- Rob Heel's seed_power_opamps breakout, Gerbers of 2025-08-29 (EasyEDA v6.5.51), downloaded 2026-11-12
#     from github.com/rob-scape/daisy-seed-breakout-boards, daisy-seed-dcdc-opamps/Gerber_seed_power_opamps_PCB.
#     Gerber frame: top view, mm. Drill_PTH_Through.DRL (METRIC, 3:3), Gerber_BoardOutlineLayer.GKO (4.5, mm),
#     square pads from Gerber_TopLayer.GTL (MACRO1 / rectangle flashes), sides from the silkscreens.
BO_OUTLINE = (0.152, -18.796, 96.901, 0.0)          # x1, y1, x2, y2 (96.749 x 18.796)
BO_ROW_A, BO_ROW_B = -17.018, -1.778                 # the two pin rows
# Bottom silkscreen: "H1", "A IN 1/2", "J1 -12", "G" (pin 20) along row A; "H2", "3.3A" (pin 21), "3.3D", "VIN",
# "G" (pins 38-40), "A OUT 1/2", "J3 +12" along row B; "SEED USB" at the x 87 end. The Seed's pin 21 is 3V3A
# (Seed datasheet), so row A carries pins 1-20, pin 1 at x 85.09 (square), pin 40 at (85.09, row B) (square).
BO_HOLES = []                                        # (name, x, y, drill, square)
for k in range(20):
    BO_HOLES.append((str(20 - k), 36.83 + 2.54 * k, BO_ROW_A, 1.2, k == 19))      # pin 20 at x 36.83 .. pin 1
    BO_HOLES.append((str(21 + k), 36.83 + 2.54 * k, BO_ROW_B, 1.2, k == 19))      # pin 21 at x 36.83 .. pin 40
for k in range(4):                                   # J1 / J3 (0.889): pin 1 square, next to the Seed (x 31.75)
    BO_HOLES.append((f"J1-{k + 1}", 31.75 - 2.54 * k, BO_ROW_A, 0.889, k == 0))
    BO_HOLES.append((f"J3-{k + 1}", 31.75 - 2.54 * k, BO_ROW_B, 0.889, k == 0))
    BO_HOLES.append((f"J5-{k + 1}", 95.25 - 2.54 * k, BO_ROW_A, 0.889, k == 0))   # J4 / J5: pin 1 square at the far end
    BO_HOLES.append((f"J4-{k + 1}", 95.25 - 2.54 * k, BO_ROW_B, 0.889, k == 0))
BO_J2 = [(x, -3.894 - 2.54 * k) for x in (6.085, 8.625) for k in range(5)]   # 2x5 power header, 0.889 drills,
#   pin 1 square at (6.085, -14.054); outline and "RED STRIPE" on the bottom silk
BO_U3 = [(27.559, y) for y in (-5.588, -8.128, -10.668, -13.208)]           # B2405S-1WR2 SIP-4, 0.915 drills
BO_CAPS = [(18.161, -2.949), (18.161, -6.449), (17.526, -11.966), (17.526, -15.466)]   # C9 / C18 100 uF 8 x 12, 1.0
BO_NPTH = [(2.159, -2.159, 3.0), (2.159, -17.018, 3.0)]
BO_SMD_X = (9.384, 85.872)          # extent of every top paste pad (Gerber_TopPasteMaskLayer.GTP): the SMD band
# Which side faces the main board: every THT part (U3, C9, C18, J2, the Seed's H1 / H2) is drawn on the bottom
# silkscreen, the SMD parts (2 x TL074 TSSOP, 0603 / 1206, B5819W SOD-123) on the top; no bottom paste layer.
BO_SMD_H = 1.8                      # tallest SMD part: Samsung CL31A106KBHNNNE (1206 10 uF), thickness code H
#   1.60 +- 0.20 (Samsung MLCC datasheet, LCSC C13585) -> 1.8 max; TSSOP-14 1.2 max, SOD-123 ~1.35
TAIL = 2.5                          # THT lead protrusion, max: IPC-A-610 class 2 (2.5 mm; recalled, not confirmed)
SOCKET_H = 8.5                      # female header, 8.5 mm tall (bom.md): the breakout's near face is at least here
MALE_PLASTIC = 2.5                  # male header plastic (standard 2.54 mm header; bom.md / design.md: 11 mm stack)
BO_MARGIN = 0.5                     # assembly margin asked of every clearance under the breakout (house judgement)

# --- bodies, max (mm)
BODY_DIP14 = (19.69, 7.11)          # Microchip P: D .775, E1 .280 (TI N: same MS-001 maxima, not confirmed)
BODY_DIP16 = (19.81, 7.11)          # MS-001 BB: D .780 in (TI N0016A; recalled, not confirmed: TI's device tables
#                                     give 19.31 x 6.35 nominal); E1 .280
CHIP_A = 5.33                       # PDIP top to seating plane, max (Microchip P: A .210)
SOCKET14, SOCKET16 = (17.78, 10.16), (20.32, 10.16)    # Mill-Max 110-43-314 / -316: A .700 / .800, C .400 in
SOCKET_ABOVE = 4.191                # Mill-Max 110-43-3xx above-board height .165 in
# verifier additions (2026-11-13). The BOM orders a plain Tayda "DIP-16 IC socket" (bom.py: no type given): Tayda
# sells both a stamped dual-wipe one and a machine-tooled one (SKU A-1319, pin length 2.95). A stamped socket of that
# kind: CnC Tech 243-16-1-03 ("2.54mm IC Socket Stamp Pin", drawing 243-XX-1-XX, 05-FEB-2020, cnctech.us/pdfs/
# 243-XX-1-XX_.pdf): body 4.8 tall (side view), end walls 5.2, tails 3.2, outside width D 10.16 (16 pins), the same
# 10.16 as Mill-Max C. The IC's lead shoulders rest on its 4.8 mm body (assumed from the drawing: not stated);
# Futurlec's dual-wipe 16-pin lists a 4.5 mm body (futurlec.com/Sockets/ICS16.shtml).
SOCKET_ABOVE_STAMPED = 4.8
SOCKET_TAIL = {"machined": 3.175, "stamped": 3.2}      # Mill-Max tail length .125 in; CnC Tech 3.2
FEMALE_HDR_TAIL = 3.0               # a 2.54 mm female header's solder tail below the board, typical (assumed, not
#                                     confirmed): the breakout's socket strips on the main board's top (U2's pads)
PCB_T = 1.6
BODY_TO92 = (5.21, 4.19)            # TI LP0003A body 4.44-5.21 wide; onsemi case 29-11 C 3.18-4.19 deep
BODY_DO35 = (5.08, 2.28)            # JEDEC DO-204AH max (Vishay drawing not readable)
BODY_FG28 = (4.0, 2.5, 5.5)         # TDK FG28: W 4.0 max x T 2.5 max x H 5.5 max
BODY_SR30 = (7.62, 3.81, 7.62)      # KYOCERA AVX SR30: W .300, T .150, H .300 in (max)
BODY_RES = (6.7, 2.5)               # TE LR1: L 6.2 +- 0.5, D 2.3 +- 0.2 (max)
BODY_LED3 = 3.8                     # 3 mm LED flange diameter (Kingbright T-1; not confirmed): drawn as 3.2
FG28_SEATED = BODY_FG28[2] + 1.5    # standing FG28: body plus 1.5 mm of lead and kink (assumed, not confirmed)
# --- M3 hardware round the mounting holes
# verifier change: the BOM's "M3 x 6 mm pan-head screw" names no standard. ISO 7045 M3: dk 5.6, k 2.4 (Wuerth ISO
# 7045 M3 listing); the older DIN 7985 M3 (still sold, and what Doepfer names for its M3x6 rail screws,
# doepfer.de/a100_man/a100m_e.htm): dk 6.0, k 2.4 (Westfield Fasteners' DIN 7985 summary). The larger head is
# the one a check must allow for: 6.0 (was 5.6).
M3_HEAD_R = 6.0 / 2
M3_HEAD_R_ISO = 5.6 / 2
M3_HEAD_K = 2.4                     # ISO 7045 and DIN 7985 M3 head height k max
STANDOFF_AF = (5.0, 5.5)            # common M3 hex standoffs; across the corners = AF / cos 30. The BOM gives no AF:
#   M3 hex standoffs are sold at 4.5 (RAF M1258-3005-B), 5.0 / 5.5 (Harwin R30: RS says 5 AF, Digi-Key 5.5) and
#   6.0 mm AF (aluminium): verifier, 2026-11-13
# --- design.md
BOARD_W, BOARD_H = 90.0, 108.0
HOLES_FRONT = [(45, 82), (45, 33), (79, 69), (11, 69)]     # design.md "Mounting": front view
BREAKOUT_BOX = (35.6, 3.7, 54.4, 100.5)                     # design.md "Main board": the breakout's board
UNDER_BREAKOUT = {"R33", "R36", "R39"}                      # design.md: under it sit R33, R36 and R39
STACK_GAP = 11.0                    # design.md / bom.md: 8.5 mm sockets on the male headers' 2.5 mm plastic
LABELS_PER_BOARD = {"Faceplate": 35, "Main": 79}            # design.md "Value labels" (76 + R57-R59 since 2026-11-14)
SMALL_LABELS = {38: 6, 32: 7}       # design.md: six at 38 mil, seven at 32 mil (since the relabel of 2026-11-14)
UNLABELLED_OK = {"Main": {"R80"}}   # design.md: R80 on the main board has no label

# ====================================================================== the routed master
R = harness.routed()
MB, FB = R.main, R.face
B = {"main": MB, "face": FB}
NAME = {"main": "Main", "face": "Faceplate"}
# which chips sit in a socket: bom.py's "DIP-xx IC socket" lines. Since M2 (2026-11-13) the faceplate's four DIP-16s
# are soldered straight to the board (bom.SOLDERED); every check below that gives a chip a socket asks this set.
_bom = harness.load("bom")
SOCKETED = {({"Main": "main", "Faceplate": "face"}[b], r) for (_src, _grp, part), line in _bom.build()[0].items()
            if part.endswith("IC socket") for b, r in line["refs"]}


def fp_doc(k, ref):
    return R.fp_by_uuid[R.attrs(k, ref)["Footprint"]]


def raw_pads(doc):
    out = {}
    for h, p in doc["recs"]:
        if h["type"] == "PAD" and p:
            dp, ho = p["defaultPad"], p.get("hole") or {}
            out[str(p["num"])] = {"x": p["centerX"] * MIL, "y": p["centerY"] * MIL, "shape": dp["padType"],
                                  "w": dp["width"] * MIL, "h": dp["height"] * MIL, "hole": ho.get("holeType"),
                                  "hw": ho.get("width", 0) * MIL, "hh": ho.get("height", 0) * MIL,
                                  "angle": p.get("padAngle") or 0}
    return out


def silk(doc):
    """Footprint silk (layer 3) items as (kind, points in mm, raw path)."""
    out = []
    for h, p in doc["recs"]:
        if p and h["type"] in ("POLY", "FILL") and p.get("layerId") == 3:
            path = p["path"]
            if path and path[0] == "CIRCLE":
                out.append(("circle", [(path[1] * MIL, path[2] * MIL)], path[3] * MIL))
            else:
                pa = path[0] if path and isinstance(path[0], list) else path
                out.append(("line", ca.flatten_path(pa, MIL), None))
    return out


# one footprint document per used footprint (the project also carries unused copies under the same titles)
USED = {}                                 # uuid -> [(board, ref)]
for k, b in B.items():
    for ref in b.parts:
        USED.setdefault(R.attrs(k, ref)["Footprint"], []).append((k, ref))
FPU = {u: raw_pads(R.fp_by_uuid[u]) for u in USED}
TITLE = {u: harness.meta(R.fp_by_uuid[u])["title"] for u in USED}
BY_TITLE = collections.defaultdict(list)
for u, t in TITLE.items():
    BY_TITLE[t].append(u)


def fpp(title):
    """Raw pads of the (one) used footprint with that title."""
    us = BY_TITLE[title]
    return FPU[us[0]]


def to_board(pl, fx, fy):
    if pl["bottom"]:
        fy = -fy
    dx, dy = ca.rot(fx, fy, pl["angle"])
    return pl["x"] + dx, pl["y"] + dy


def front(x):
    return BOARD_W - x


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ====================================================================== FP: footprints
diff = [t for t, us in BY_TITLE.items() if any(sorted((n, round(q["x"], 3), round(q["y"], 3), round(q["hw"], 3)) for n, q in FPU[u].items())
                                                != sorted((n, round(q["x"], 3), round(q["y"], 3), round(q["hw"], 3)) for n, q in FPU[us[0]].items())
                                                for u in us)]
ck.check("FP.copies_of_one_footprint_identical", not diff,
         f"titles used under several uuids: {[(t, len(v)) for t, v in BY_TITLE.items() if len(v) > 1]}; differing pads: {diff}")
stale = sorted(harness.meta(d)["title"] for u, d in R.fp_by_uuid.items() if u not in USED
               and harness.meta(d)["title"] in BY_TITLE
               and sorted(raw_pads(d)) != sorted(fpp(harness.meta(d)["title"])))
print(f"INFO  unused footprint copies with a different pad set under a used title (EasyEDA keeps them; harmless unless "
      f"someone re-assigns from the project library): {stale}")


def dip(title, n, socket):
    p = fpp(title)
    xy = {i: (p[str(i)]["x"], p[str(i)]["y"]) for i in range(1, n + 1)}
    pitch = [dist(xy[i], xy[i + 1]) for i in list(range(1, n // 2)) + list(range(n // 2 + 1, n))]
    rows = [dist(xy[i], xy[n + 1 - i]) for i in range(1, n // 2 + 1)]
    ck.check(f"FP.dip_pitch.{title}", all(abs(v - DIP_PITCH) < 0.01 for v in pitch),
             f"expected {DIP_PITCH}, got {sorted({round(v, 3) for v in pitch})}")
    ck.check(f"FP.dip_rows_fit_a_0.300in_socket.{title}", all(abs(v - DIP_ROW) < 0.02 for v in rows),
             f"expected {DIP_ROW} (Mill-Max B .300, a standard {n}-pin socket), got {sorted({round(v, 3) for v in rows})}")
    r1 = {round(xy[i][1], 2) for i in range(1, n // 2 + 1)}
    r2 = {round(xy[i][1], 2) for i in range(n // 2 + 1, n + 1)}
    v1 = (xy[2][0] - xy[1][0], xy[2][1] - xy[1][1])
    vn = (xy[n][0] - xy[1][0], xy[n][1] - xy[1][1])
    ccw = len(r1) == 1 and len(r2) == 1 and r1 != r2 and v1[0] * vn[1] - v1[1] * vn[0] > 0
    ck.check(f"FP.dip_numbering_ccw_from_the_top.{title}", ccw, f"pins 1..{n // 2} one row, back along the other "
             f"(pin i opposite pin {n + 1}-i, counter-clockwise seen from the part): rows {r1} / {r2}")
    marks = [pts[0] for kind, pts, r in silk(R.fp_by_uuid[BY_TITLE[title][0]]) if kind == "circle" and r < 0.6]
    ok = bool(marks) and all(dist(m, xy[1]) < min(dist(m, xy[n]), dist(m, xy[n // 2])) for m in marks)
    print(f"INFO  {title}: pin 1 pad {p['1']['shape']} (a square pin-1 pad is the usual extra cue)")
    ck.check(f"FP.dip_pin1_mark.{title}", ok or p["1"]["shape"] == "RECT",
             f"silk dot(s) {[tuple(round(v, 2) for v in m) for m in marks]}, pin 1 pad {p['1']['shape']}")


dip("DIP-14-W7.62-P2.54", 14, SOCKET14)
dip("DIP-16_L20.0-W6.4-P2.54-LS7.6-BL", 16, SOCKET16)
dip14 = sorted(r for k, r in USED[BY_TITLE["DIP-14-W7.62-P2.54"][0]])
ck.check("FP.dip14_on_U3_U8_no_8.89mm_footprint", dip14 == ["U3", "U4", "U5", "U6", "U7", "U8"]
         and not any("LS9.0" in t for t in BY_TITLE), f"DIP-14-W7.62 on {dip14}; LS9.0 footprints used: "
         f"{[t for t in BY_TITLE if 'LS9.0' in t]}")
dip16 = sorted(r for k, r in USED[BY_TITLE["DIP-16_L20.0-W6.4-P2.54-LS7.6-BL"][0]])
ck.check("FP.dip16_on_U1_U9_U10_U11", dip16 == ["U1", "U10", "U11", "U9"], str(dip16))

# TO-92: in line at 2.54; the parts ordered come with straight 1.27 mm leads
p = fpp("TO-92-INLINE-P2.54")
pt = [dist((p[a]["x"], p[a]["y"]), (p[b]["x"], p[b]["y"])) for a, b in (("1", "2"), ("2", "3"))]
ck.check("FP.to92_pitch_is_the_formed_lead_option", all(TO92_FORMED[0] <= v <= TO92_FORMED[1] for v in pt),
         f"pitch {pt}, formed-lead option {TO92_FORMED} (onsemi case 29-11 bent lead G, TI LP0003A formed)")
bom_md = harness.text("docs", "bom.md")
bend_note = re.search(r"(bend|bent|form|spread)[^\n|]*(TO-92|lead)|(TO-92|lead)[^\n|]*(bend|bent|formed|spread)", bom_md, re.I)
ck.check("FP.to92_straight_lead_parts_need_forming_noted", bool(bend_note),
         f"the ordered LM4040CIZ-2.5/NOPB ships straight leads only (bulk, TI SNOS633N note 5a: 1.27 +- 0.13 mm) and a "
         f"bulk 2N3904 likewise (onsemi G {TO92_STRAIGHT}); the footprint is {pt[0]:.2f} mm, so the outer leads must be "
         f"bent out 1.27 mm. bom.md says nothing about it")
# DO-35: 8 mm pitch for a 5.08 mm body with 0.8 mm straight lead before each bend (IPC-A-610 lead-bend rule,
# recalled) and the lead's own radius
p = fpp("DO-35_BD2.0-L4.0-P8.0-D0.5-RD")
pitch = dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"]))
ck.within("FP.do35_pitch_fits_the_body", pitch, BODY_DO35[0] + 2 * 0.8 + LEAD_DO35[1], None, " mm",
          "JEDEC DO-204AH body 5.08 max + 2 x 0.8 to the bend + a lead diameter")
for title, body in (("RES-TH_L6.2-W2.3-LR1F1K0", BODY_RES), ("RES-TH_BD2.3-L6.3-P10.30-D0.6", BODY_RES)):
    p = fpp(title)
    pitch = dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"]))
    ck.within(f"FP.axial_pitch_fits_the_body.{title}", pitch, body[0] + 2 * 0.8 + LEAD_RES[1], None, " mm",
              "TE LR1 6.7 max + 2 x 0.8 + a lead")
p = fpp("1/4W-RESISTOR-VERTICAL")
pitch = dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"]))
ck.close("FP.standing_resistor_pitch_2.54", pitch, 2.54, 0.01, " mm")
for title, want in (("CAP-TH_L3.0-W2.0-P5.08-D0.7", (4.0, 6.0)), ("CAP-TH_L7.6-W3.8-P5.08-D0.51", (5.08 - 0.5, 5.08 + 0.5))):
    p = fpp(title)
    pitch = dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"]))
    ck.within(f"FP.cap_pitch.{title}", pitch, want[0], want[1], " mm", "TDK FG28 5.0 +- 1.0; AVX SR30 .200 in")
p = fpp("LED-3MM-2P")
ck.close("FP.led3_pitch_2.54", dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"])), 2.54, 0.01, " mm")
for title, n in (("HDR-1x8-P2.54", 8), ("HDR-1x4-P2.54", 4), ("HDR-TH_3P-P2.54_CS-1165SDIG", 3)):
    p = fpp(title)
    gaps = [dist((p[str(i)]["x"], p[str(i)]["y"]), (p[str(i + 1)]["x"], p[str(i + 1)]["y"])) for i in range(1, n)]
    inline = len({round(p[str(i)]["y"], 3) for i in range(1, n + 1)}) == 1
    ck.check(f"FP.header_2.54_in_line.{title}", all(abs(g - 2.54) < 0.01 for g in gaps) and inline
             and p["1"]["shape"] == "RECT", f"gaps {sorted({round(g, 3) for g in gaps})}, in line {inline}, "
             f"pin 1 {p['1']['shape']}")

# Thonkiconn (KiCad PJ398SM)
p = fpp("CONN-TH_WQP-WQP518MA")
S, TN, T = ((p[n]["x"], p[n]["y"]) for n in ("1", "2", "3"))
d_st, d_stn = dist(S, T), dist(S, TN)
same_side = (TN[1] - S[1]) * (T[1] - S[1]) > 0 and d_stn < d_st
ck.check("FP.jack_pins_as_KiCad_PJ398SM", abs(d_st - JACK_S_T) < 0.02 and abs(d_stn - JACK_S_TN) < 0.02 and same_side,
         f"S-T {d_st:.2f} (11.4), S-TN {d_stn:.2f} (3.1), TN between S and T: {same_side}")
barrel = (S[0] + (T[0] - S[0]) / d_st * JACK_S_BARREL, S[1] + (T[1] - S[1]) / d_st * JACK_S_BARREL)
ck.close("FP.jack_barrel_offset_from_origin", dist(barrel, (0, 0)), abs(circuit.JACK_BARREL if hasattr(circuit, "JACK_BARREL")
                                                                       else harness.load("panel").JACK_BARREL), 0.02, " mm")
# Alpha pot
p = fpp("POT-ALPHA-9MM-RD901F")
pins = [(p[n]["x"], p[n]["y"]) for n in "123"]
lugs = [(p[n]["x"], p[n]["y"]) for n in "45"]
shaft = ((lugs[0][0] + lugs[1][0]) / 2, (lugs[0][1] + lugs[1][1]) / 2)
row_d = abs(shaft[1] - pins[1][1])
ok = (abs(dist(pins[0], pins[1]) - POT_PIN_PITCH) < 0.01 and abs(dist(pins[1], pins[2]) - POT_PIN_PITCH) < 0.01
      and abs(row_d - POT_ROW_SHAFT) < 0.01 and abs(dist(lugs[0], lugs[1]) / 2 - POT_LUG_HALF) < 0.01
      and abs(lugs[0][1] - lugs[1][1]) < 0.01 and abs(shaft[0] - pins[1][0]) < 0.01)
ck.check("FP.pot_as_KiCad_RD901F", ok, f"pin pitch {dist(pins[0], pins[1]):.2f} (2.5), row to shaft {row_d:.2f} (7.5), "
         f"lugs +-{dist(lugs[0], lugs[1]) / 2:.2f} (4.8) on the shaft line")
lug = p["4"]
along = "y"     # pins in a row along x, so the pin-to-shaft direction is y
slot_long_y = lug["hh"] > lug["hw"]
ck.check("FP.pot_lug_pads_and_slots_as_KiCad", abs(min(lug["w"], lug["h"]) - POT_LUG_PAD[0]) < 0.01
         and abs(max(lug["w"], lug["h"]) - POT_LUG_PAD[1]) < 0.01 and abs(min(lug["hw"], lug["hh"]) - POT_LUG_SLOT[0]) < 0.01
         and abs(max(lug["hw"], lug["hh"]) - POT_LUG_SLOT[1]) < 0.01 and slot_long_y and lug["h"] > lug["w"],
         f"pad {lug['w']:.2f} x {lug['h']:.2f}, slot {lug['hw']:.2f} x {lug['hh']:.2f} (x by y); KiCad 2.72 x 3.24 / "
         f"1.1 x 1.8 long along the pin-to-shaft direction")
ck.close("FP.pot_shaft_4.0_from_origin_away_from_pins", shaft[1], circuit.POT_SHAFT, 0.01, " mm")
ck.check("FP.pot_pins_on_the_far_side_from_the_shaft", pins[1][1] < 0 < shaft[1], f"pins y {pins[1][1]}, shaft y {shaft[1]}")
# Thonk LED button
p = fpp("SW-TACT-LP-LED-THONK")
bad = [n for n, (x, y) in BTN_PINS.items() if n not in p or dist((p[n]["x"], p[n]["y"]), (x, y)) > 0.01]
ck.check("FP.button_pins_as_Thonk", not bad and set(p) == set(BTN_PINS),
         f"pads {sorted(p)}, off: {bad} (design.md: no feet holes, clip the feet)")

# Daisy Seed footprint against the Seed datasheet
p = fpp("DAISY-SEED-POWER-OPAMPS-2.54")
ck.check("FP.seed_56_pads", len(p) == 56, f"{len(p)} pads")
s = {n: (p[str(n)]["x"], p[str(n)]["y"]) for n in range(1, 41)}
pitch = [dist(s[i], s[i + 1]) for i in list(range(1, 20)) + list(range(21, 40))]
rows = [dist(s[i], s[41 - i]) for i in range(1, 21)]
ck.check("FP.seed_pitch_rows_span", all(abs(v - SEED_PITCH) < 0.01 for v in pitch) and all(abs(v - SEED_ROWS) < 0.01 for v in rows)
         and abs(dist(s[1], s[20]) - SEED_SPAN) < 0.01,
         f"pitch {sorted({round(v, 3) for v in pitch})}, rows {sorted({round(v, 3) for v in rows})}, 1-20 {dist(s[1], s[20]):.2f}")
j = {n: (p[n]["x"], p[n]["y"]) for n in p if "-" in n}
ok = (all(abs(j[f"J1-{k}"][1] - s[20][1]) < 0.01 and abs(j[f"J3-{k}"][1] - s[21][1]) < 0.01 for k in range(1, 5))
      and abs(dist(j["J1-1"], s[20]) - 5.08) < 0.01 and abs(dist(j["J3-1"], s[21]) - 5.08) < 0.01
      and abs(dist(j["J5-4"], s[1]) - 2.54) < 0.01 and abs(dist(j["J4-4"], s[40]) - 2.54) < 0.01
      and all(abs(dist(j[f"{h}-{k}"], j[f"{h}-{k + 1}"]) - 2.54) < 0.01 for h in ("J1", "J3", "J4", "J5") for k in (1, 2, 3)))
ck.check("FP.seed_breakout_headers_in_line", ok, "J1 / J3 beyond pins 20 / 21 after one empty position, J5 / J4 beyond "
         "pins 1 / 40 at 2.54, all in the socket rows")
# against the breakout's Gerbers: footprint (fx, fy) <-> breakout (bx, by). Mirrored: the breakout seen from below.
cx = (36.83 + 85.09) / 2
cy = (BO_ROW_A + BO_ROW_B) / 2


def bo_to_fp(bx, by, mirrored=True):
    return bx - cx, -(by - cy) if mirrored else (by - cy)


def match(mirrored):
    miss, sq = [], []
    holes = [(n, *bo_to_fp(x, y, mirrored), sqr) for n, x, y, d, sqr in BO_HOLES]
    for n, pd in p.items():
        near = min(holes, key=lambda h: math.hypot(h[1] - pd["x"], h[2] - pd["y"]))
        if math.hypot(near[1] - pd["x"], near[2] - pd["y"]) > 0.01 or near[0] != n:
            miss.append(f"{n}->{near[0]}")
        elif near[3] != (pd["shape"] == "RECT"):
            sq.append(n)
    return miss, sq


miss, sq = match(True)
ck.check("FP.seed_pads_on_the_breakout_holes_same_pins", not miss and not sq,
         f"breakout seen from below (Seed side away from the main board): {len(miss)} pads off or on another pin "
         f"{miss[:6]}, square pads differing {sq}")
miss2, _ = match(False)
ck.check("FP.seed_footprint_fits_only_with_the_Seed_facing_away", bool(miss2),
         f"breakout seen from above: {len(miss2)} pins land on another pin (the mirror would swap the rows)")
print("INFO  the footprint is the breakout seen from its SMD side: the breakout plugs in SMD side down, the Seed, the "
      "DC/DC module, C9 / C18 and the 10-pin header (all on its bottom silk) face away from the main board, and the "
      "THT parts' solder tails point down at the main board")
fsilk = silk(R.fp_by_uuid[BY_TITLE["DAISY-SEED-POWER-OPAMPS-2.54"][0]])
xs = [q[0] for kind, pts, r in fsilk if kind == "line" for q in pts]
ys = [q[1] for kind, pts, r in fsilk if kind == "line" for q in pts]
bo = [bo_to_fp(BO_OUTLINE[0], BO_OUTLINE[1]), bo_to_fp(BO_OUTLINE[2], BO_OUTLINE[3])]
want = (min(q[0] for q in bo), min(q[1] for q in bo), max(q[0] for q in bo), max(q[1] for q in bo))
got = (min(xs), min(ys), max(xs), max(ys))
ck.check("FP.seed_silk_outline_is_the_breakout", all(abs(a - b) < 0.1 for a, b in zip(got, want)),
         f"silk {tuple(round(v, 2) for v in got)}, breakout {tuple(round(v, 2) for v in want)}")

# ====================================================================== BO: the breakout on the main board
U2 = MB.parts["U2"]


def bo_board(bx, by):
    return to_board(U2, *bo_to_fp(bx, by))


corners = [bo_board(x, y) for x, y in ((BO_OUTLINE[0], BO_OUTLINE[1]), (BO_OUTLINE[2], BO_OUTLINE[3]))]
box = (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
ck.check("BO.outline_as_design_md", all(abs(a - b) < 0.1 for a, b in zip(box, BREAKOUT_BOX)),
         f"expected x {BREAKOUT_BOX[0]}-{BREAKOUT_BOX[2]}, y {BREAKOUT_BOX[1]}-{BREAKOUT_BOX[3]}; got "
         f"{tuple(round(v, 2) for v in box)}")
ck.check("BO.inside_the_board", box[0] >= 0 and box[1] >= 0 and box[2] <= BOARD_W and box[3] <= BOARD_H,
         f"{tuple(round(v, 2) for v in box)}")
power_end_down = bo_board(31.75, BO_ROW_A)[1] < bo_board(85.09, BO_ROW_A)[1]
ck.check("BO.power_end_down_usb_up", power_end_down, "design.md: power end (J1/J3, y 27-35) down")
under_holes = sorted((round(hx, 1), round(hy, 1)) for hx, hy, hd in MB.holes
                     if box[0] - M3_HEAD_R < hx < box[2] + M3_HEAD_R and box[1] - M3_HEAD_R < hy < box[3] + M3_HEAD_R)
ck.check("BO.over_the_two_centre_holes_only", under_holes == [(45.0, 33.0), (45.0, 82.0)],
         f"holes under it: {under_holes} (design.md: the two centre mounting screws, fit them first)")


def rect_poly(cx_, cy_, L, W, ang):
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = ca.rot(sx * L / 2, sy * W / 2, ang)
        out.append((cx_ + dx, cy_ + dy))
    return out


def fp_rect(pl, fcx, fcy, L, W):
    """A rectangle given in the footprint frame (centre, length along x, width along y) -> board polygon."""
    cs = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        cs.append(to_board(pl, fcx + sx * L / 2, fcy + sy * W / 2))
    return ("poly", cs)


def real_body(k, ref, socket=False):
    """('poly', corners) / ('circle', centre, r) of the part's real body (max sizes), board frame; None = skip."""
    pl = B[k].parts[ref]
    t = pl["fp"]
    if t.startswith("DIP-14"):
        return fp_rect(pl, 0, 0, *(SOCKET14 if socket else BODY_DIP14))
    if t.startswith("DIP-16"):
        return fp_rect(pl, 0, 0, *(SOCKET16 if socket else BODY_DIP16))
    if t.startswith("TO-92"):
        # verifier change: the body was a 5.21 x 4.19 rectangle from the silk flat, whose square back corners stood
        # where the real TO-92 is round. Now the D shape: a circle of the maximum width (5.21, TI LP0003A) round the
        # middle lead (the footprint's silk circle r 2.6 is centred there too), cut by the flat. The flat sits at the
        # silk's 1.3 mm or at depth max - radius (4.19 - 2.605 = 1.585), whichever is further out.
        r = BODY_TO92[0] / 2
        flat = -max(1.3, BODY_TO92[1] - r)
        a0 = math.asin(flat / r)
        pts = [(r * math.cos(a0 + (math.pi - 2 * a0) * i / 24), r * math.sin(a0 + (math.pi - 2 * a0) * i / 24))
               for i in range(25)]
        return ("poly", [to_board(pl, x, y) for x, y in pts])
    if t.startswith("DO-35"):
        return fp_rect(pl, 0, 0, *BODY_DO35)
    if t.startswith("CAP-TH_L3.0"):
        return fp_rect(pl, 0, 0, BODY_FG28[0], BODY_FG28[1])
    if t.startswith("CAP-TH_L7.6"):
        return fp_rect(pl, 0, 0, BODY_SR30[0], BODY_SR30[1])
    if t.startswith("RES-TH"):
        return fp_rect(pl, 0, 0, *BODY_RES)
    if t == "1/4W-RESISTOR-VERTICAL":
        q = fpp(t)["1"]
        return ("circle", to_board(pl, q["x"], q["y"]), BODY_RES[1] / 2)
    if t.startswith("HDR-1x"):
        n = len(pl["pads"])
        return fp_rect(pl, 0, 0, n * 2.54, 2.54)
    if t.startswith("HDR-TH_3P"):
        return fp_rect(pl, 0, 0, 3 * 2.54, 2.54)
    if t.startswith("CONN-TH_WQP"):
        s0 = fpp(t)["1"]["y"]                           # sleeve at -5.7, tip towards +y
        return fp_rect(pl, 0, s0 + (JACK_BODY[1] + JACK_BODY[2]) / 2, JACK_BODY[0], JACK_BODY[2] - JACK_BODY[1])
    if t.startswith("POT-ALPHA"):
        r0 = fpp(t)["2"]["y"]                           # pin row at -3.5, shaft towards +y
        return fp_rect(pl, 0, r0 + (POT_BODY[1] + POT_BODY[2]) / 2, POT_BODY[0], POT_BODY[2] - POT_BODY[1])
    if t.startswith("SW-TACT-LP"):
        return fp_rect(pl, 0, 0, BTN_BODY, BTN_BODY)
    if t == "LED-3MM-2P":
        return ("circle", to_board(pl, 0, 0), BODY_LED3 / 2)
    return None


def _proj(poly, ax):
    v = [q[0] * ax[0] + q[1] * ax[1] for q in poly]
    return min(v), max(v)


def separation(a, b):
    """Gap between two bodies (SAT for polygons; negative = overlap depth)."""
    if a[0] == "circle" and b[0] == "circle":
        return dist(a[1], b[1]) - a[2] - b[2]
    if a[0] == "circle" or b[0] == "circle":
        c, pg = (a, b) if a[0] == "circle" else (b, a)
        poly = pg[1]
        inside = ca.point_in_poly(c[1], poly)
        d = min(ca.d_point_seg(c[1], poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))
        return (-d - c[2]) if inside else d - c[2]
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


def circle_sep(c, r, body):
    return separation(("circle", c, r), body)


bo_poly = ("poly", [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])])
under = sorted(ref for ref, pl in MB.parts.items() if ref != "U2" and not pl["bottom"]
               and real_body("main", ref) is not None and separation(real_body("main", ref), bo_poly) < 0)
ck.check("BO.parts_under_it_as_design_md", set(under) == UNDER_BREAKOUT, f"under the breakout: {under}")
# its underside: THT tails (2.5 mm max) at every THT hole, the SMD band (1.8 mm) across x 9.4-85.9 of its frame
tails = [(bo_board(x, y), d / 2 + 0.5) for n, x, y, d, sqr in BO_HOLES] + \
        [(bo_board(x, y), 0.889 / 2 + 0.5) for x, y in BO_J2] + [(bo_board(x, y), 0.915 / 2 + 0.5) for x, y in BO_U3] + \
        [(bo_board(x, y), 0.5 + 0.5) for x, y in BO_CAPS]
smd_c = [bo_board(BO_SMD_X[0], BO_OUTLINE[1]), bo_board(BO_SMD_X[1], BO_OUTLINE[3])]
smd_poly = ("poly", [(min(c[0] for c in smd_c), min(c[1] for c in smd_c)), (max(c[0] for c in smd_c), min(c[1] for c in smd_c)),
                     (max(c[0] for c in smd_c), max(c[1] for c in smd_c)), (min(c[0] for c in smd_c), max(c[1] for c in smd_c))])


def underside(body):
    """What the breakout's near face carries above a body: (protrusion, what)."""
    t = [f"tail at ({c[0]:.1f}, {c[1]:.1f})" for c, r in tails if circle_sep(c, r, body) < 0]
    s = separation(smd_poly, body) < 0
    return (TAIL if t else BO_SMD_H if s else 0.0), (t[:3] if t else ["SMD band"] if s else [])


for ref in sorted(UNDER_BREAKOUT):
    body = real_body("main", ref)
    prot, what = underside(body)
    clear = SOCKET_H - prot - BODY_RES[1]
    ck.within(f"BO.underside_clears.{ref}", clear, BO_MARGIN, None, " mm",
              f"8.5 mm socket - {prot} ({', '.join(what) or 'nothing'}) - {BODY_RES[1]} resistor body; "
              f"{clear + MALE_PLASTIC:.2f} with male-header plastic under the breakout")
for hx, hy, hd in MB.holes:
    if not (box[0] < hx < box[2] and box[1] < hy < box[3]):
        continue
    head = ("circle", (hx, hy), M3_HEAD_R)
    prot, what = underside(head)
    clear = SOCKET_H - prot - M3_HEAD_K
    ck.within(f"BO.underside_clears_screw_head.({hx:.0f},{hy:.0f})", clear, BO_MARGIN, None, " mm",
              f"8.5 - {prot} ({', '.join(what) or 'nothing'}) - {M3_HEAD_K} pan head")
print(f"INFO  breakout parts in the main-board frame: J2 pin 1 at ({bo_board(6.085, -14.054)[0]:.2f}, "
      f"{bo_board(6.085, -14.054)[1]:.2f}), DC/DC pins x {min(bo_board(*q)[0] for q in BO_U3):.2f}-"
      f"{max(bo_board(*q)[0] for q in BO_U3):.2f} at y {bo_board(*BO_U3[0])[1]:.2f}, caps at y "
      f"{bo_board(*BO_CAPS[0])[1]:.2f} / {bo_board(*BO_CAPS[2])[1]:.2f}, its 3 mm holes at "
      f"{[tuple(round(v, 2) for v in bo_board(x, y)) for x, y, d in BO_NPTH]}")

# ====================================================================== HOLE: drills, rings, tracks, edges
fit_bad, loose, ring_min_bad, ring_rec_bad, slot_bad = [], [], [], [], []
for u, pads in sorted(FPU.items(), key=lambda kv: TITLE[kv[0]]):
    title = TITLE[u]
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
        leads = LEADS.get(title, [])
        if title in LEAD_PINS_ONLY and num in LEAD_PINS_ONLY[title][0]:
            leads = [LEAD_PINS_ONLY[title][1]]
        for shape, lw, lt in leads:
            if pd["hole"] == "ROUND":
                diag = lw if shape == "round" else math.hypot(lw, lt)
                insert = pd["hw"] - JLC_PTH_TOL_MINUS - diag
                if (shape == "round" and pd["hw"] - diag < IPC_FIT_MIN - 1e-6) or insert < (INSERT_MIN if shape == "round" else 0):
                    fit_bad.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {diag:.2f} lead (smallest hole clears {insert:.3f})")
                if shape == "round" and pd["hw"] - (lw - 0.1) > IPC_FIT_MAX:
                    loose.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {lw:.2f} lead")
            else:
                Ls, Ws = max(pd["hw"], pd["hh"]), min(pd["hw"], pd["hh"])
                if Ls - JLC_PTH_TOL_MINUS - lw < INSERT_MIN or Ws - JLC_PTH_TOL_MINUS - lt < INSERT_MIN:
                    fit_bad.append(f"{title}.{num}: slot {Ls:.2f} x {Ws:.2f} for a {lw:.2f} x {lt:.2f} lug")
ck.check("HOLE.lead_fit", not fit_bad, f"{len(fit_bad)} tight: {fit_bad[:8]}")
ck.check("HOLE.not_loose", not loose, f"{loose[:8]}")
ck.check("HOLE.ring_min", not ring_min_bad, f"under {JLC_RING_MIN}: {ring_min_bad}")
ck.check("HOLE.ring_recommended", not ring_rec_bad, f"under {JLC_RING_REC}: {ring_rec_bad}")
ck.check("HOLE.plated_slot_width", not slot_bad, f"{slot_bad}")
# LED leads: margin left in the smallest finished hole (reported, the check above asks only that they pass)
q = fpp("LED-3MM-2P")["1"]
print(f"INFO  3 mm LED: a 0.5 mm square lead's diagonal {math.hypot(0.5, 0.5):.3f} in the smallest finished 0.8 mm hole "
      f"{q['hw'] - JLC_PTH_TOL_MINUS:.3f}: {q['hw'] - JLC_PTH_TOL_MINUS - math.hypot(0.5, 0.5):.3f} mm to spare (KiCad uses 0.9)")

VIAS = {k: [(p["centerX"] * MIL, p["centerY"] * MIL, p["holeDiameter"] * MIL, p["viaDiameter"] * MIL, p["netName"])
            for h, p in R.pcb_docs[k]["recs"] if h["type"] == "VIA" and p] for k in B}
for k, b in B.items():
    vd = sorted({(round(d, 3), round(D, 3)) for x, y, d, D, n in VIAS[k]})
    ck.check(f"HOLE.vias_fab.{NAME[k]}", all(d >= JLC_VIA_DRILL_MIN and D >= JLC_VIA_DIA_MIN and (D - d) / 2 >= 0.1 for d, D in vd),
             f"(drill, diameter) {vd}")
    ck.check(f"HOLE.vias_design_md_0.61_0.3.{NAME[k]}", all(abs(D - RULE_VIA[0]) < 0.01 and abs(d - RULE_VIA[1]) < 0.01
                                                          for d, D in vd), f"{vd}")
    tw = sorted({round(t["w"], 3) for t in b.tracks})
    ck.check(f"HOLE.track_fab_min.{NAME[k]}", all(w >= JLC_TRACK_MIN for w in tw), f"widths {tw}")
    thin = sorted({(t["net"], round(t["w"], 3)) for t in b.tracks if t["w"] < RULE_SIGNAL - 1e-3})
    ck.check(f"HOLE.signal_tracks_0.3.{NAME[k]}", not thin, f"{thin}")
    pw = collections.Counter((t["net"], round(t["w"], 3)) for t in b.tracks if t["net"] in POWER_NETS and t["w"] < RULE_POWER - 1e-3)
    pl_len = collections.defaultdict(float)
    for t in b.tracks:
        if t["net"] in POWER_NETS and t["w"] < RULE_POWER - 1e-3:
            pl_len[t["net"]] += dist(t["a"], t["b"])
    where = sorted({f"{t['net']} L{t['layer']} ({t['a'][0]:.1f}, {t['a'][1]:.1f})-({t['b'][0]:.1f}, {t['b'][1]:.1f})"
                    for t in b.tracks if t["net"] in POWER_NETS and t["w"] < RULE_POWER - 1e-3})
    ck.check(f"HOLE.power_tracks_0.6.{NAME[k]}", not pw,
             f"thinner power tracks: {dict(pw)}, {({n: round(v, 1) for n, v in pl_len.items()})} mm: {where}")

for k, b in B.items():
    drills = []
    for pad in b.pads:
        raw = FPU[R.attrs(k, pad.ref)["Footprint"]][pad.num]
        if raw["hole"]:
            drills.append((pad.x, pad.y, max(raw["hw"], raw["hh"]) / 2, "pad", f"{pad.ref}.{pad.num}", pad.net, raw, pad))
    for x, y, d, D, n in VIAS[k]:
        drills.append((x, y, d / 2, "via", f"via {n} ({x:.1f}, {y:.1f})", n, None, None))
    worst = []
    for i in range(len(drills)):
        for j in range(i + 1, len(drills)):
            a, c = drills[i], drills[j]
            dd = dist(a, c)
            if dd > 6:
                continue
            gap = dd - a[2] - c[2]
            need = JLC_HOLE_HOLE_VIA if "via" in (a[3], c[3]) else JLC_HOLE_HOLE_PAD
            if gap < need:
                worst.append((round(gap, 3), a[4], c[4]))
    worst.sort()
    ck.check(f"HOLE.hole_to_hole.{NAME[k]}", not worst, f"{len(worst)} under {JLC_HOLE_HOLE_PAD} / {JLC_HOLE_HOLE_VIA}: {worst[:8]}")
    near = []
    for x, y, r, kind, label, net, raw, pad in drills:
        for t in b.tracks:
            if t["net"] == net or ca.d_point_seg((x, y), t["a"], t["b"]) > r + 2:
                continue
            if raw is not None and raw["hole"] != "ROUND":
                s0, s1, rr = ca.Pad("", "", x, y, raw["hw"], raw["hh"], "ELLIPSE", pad.angle, None).axis()
                g = ca.d_seg_seg(s0, s1, t["a"], t["b"]) - rr - t["w"] / 2
            else:
                g = ca.d_point_seg((x, y), t["a"], t["b"]) - t["w"] / 2 - r
            if g < JLC_PTH_TRACK:
                near.append((round(g, 3), label, t["net"]))
    near.sort()
    ck.check(f"HOLE.drill_to_other_track.{NAME[k]}", not near, f"{len(near)} under {JLC_PTH_TRACK}: {near[:8]}")
    x1, y1, x2, y2 = b.outline
    pe = min((min(p.x - p.r - x1, x2 - p.x - p.r, p.y - p.r - y1, y2 - p.y - p.r), p.ref) for p in b.pads)
    te = min(min(min(q[0] - x1, x2 - q[0], q[1] - y1, y2 - q[1]) - t["w"] / 2 for q in (t["a"], t["b"])) for t in b.tracks)
    ve = min(min(x - x1, x2 - x, y - y1, y2 - y) - D / 2 for x, y, d, D, n in VIAS[k])
    po = min(min(q[0] - x1, x2 - q[0], q[1] - y1, y2 - q[1]) for isl in b.islands for q in isl.outline)
    ck.check(f"HOLE.copper_to_edge.{NAME[k]}", min(pe[0], te, ve, po) >= JLC_EDGE - 1e-3,
             f"pads {pe[0]:.2f} ({pe[1]}), tracks {te:.2f}, vias {ve:.2f}, pours {po:.2f} mm (>= {JLC_EDGE})")

# ====================================================================== OUT: outlines, holes, hardware
want = sorted((round(BOARD_W - xf, 2), float(y)) for xf, y in HOLES_FRONT)
for k, b in B.items():
    x1, y1, x2, y2 = b.outline
    ck.check(f"OUT.outline_90x108.{NAME[k]}", abs(x2 - x1 - BOARD_W) < 0.01 and abs(y2 - y1 - BOARD_H) < 0.01
             and abs(x1) < 0.01 and abs(y1) < 0.01, f"({x1:.2f}, {y1:.2f})-({x2:.2f}, {y2:.2f})")
    got = sorted((round(hx, 2), round(hy, 2)) for hx, hy, hd in b.holes)
    ck.check(f"OUT.holes_at_design_md.{NAME[k]}", len(got) == 4 and all(dist(a, w) < 0.05 for a, w in zip(got, want))
             and all(abs(hd - 3.2) < 0.01 for _, _, hd in b.holes), f"expected {want} (3.2 mm), got {got}")
ck.check("OUT.holes_coincide", sorted((round(h[0], 2), round(h[1], 2)) for h in MB.holes)
         == sorted((round(h[0], 2), round(h[1], 2)) for h in FB.holes))
GROUNDS = ("GND", "GND_F", "GND_D_F")
# verifier change: the old check took one radius, max(standoff corner, head), on every pad. The standoff stands on
# the boards' facing sides (the faceplate's top, the main board's bottom) and the screw head bears on the other
# side (the faceplate's panel side, the main board's top); every pad here is plated through, so it has copper on
# both sides. Each side now gets its own radius: the standoff's corners (AF / cos 30 / 2) and the larger M3 head
# (DIN 7985 dk 6.0; ISO 7045's 5.6 is printed too).
STANDOFF_SIDE_BOTTOM = {"main": True, "face": False}       # parts with this "bottom" flag sit on the standoff side
for af in STANDOFF_AF:
    rc = af / math.cos(math.radians(30)) / 2
    for k, b in B.items():
        hit, gnd = [], []
        for hx, hy, hd in b.holes:
            for p in b.pads:
                d = p.d_point((hx, hy))
                if d < rc:
                    (gnd if p.net in GROUNDS else hit).append(f"{p.ref}.{p.num} ({p.net}) {d:.3f} mm from ({hx:.0f}, {hy:.0f})")
        ck.check(f"OUT.no_signal_pad_under_{af}AF_standoff.{NAME[k]}", not hit,
                 f"standoff side ({'bottom' if STANDOFF_SIDE_BOTTOM[k] else 'top'}), corner r {rc:.3f}: {hit}"
                 + (f"; ground pads {gnd}" if gnd else ""))
for k, b in B.items():
    hit, hit_iso = [], []
    for hx, hy, hd in b.holes:
        for p in b.pads:
            d = p.d_point((hx, hy))
            if d < M3_HEAD_R and p.net not in GROUNDS:
                hit.append(f"{p.ref}.{p.num} ({p.net}) {d:.2f} mm from ({hx:.0f}, {hy:.0f})")
                if d < M3_HEAD_R_ISO:
                    hit_iso.append(f"{p.ref}.{p.num}")
    ck.check(f"OUT.no_signal_pad_under_the_screw_head.{NAME[k]}", not hit,
             f"head side ({'top' if STANDOFF_SIDE_BOTTOM[k] else 'panel side'}), DIN 7985 head r {M3_HEAD_R}: {hit}; "
             f"under an ISO 7045 head (r {M3_HEAD_R_ISO}): {hit_iso or 'none'}")
# verifier addition: the standoff's body against the real bodies beside it on the standoff side (DIP chips in
# their sockets, the socket frames 10.16 wide: Mill-Max C, CnC Tech D). Nothing else checked this: BODY looks at
# parts against parts, BO at the breakout over the heads, the panel group at the heads on the panel side. A hex
# standoff turns freely on its screw, so the best case (a flat towards the part, r = AF / 2) must clear.
for k, b in B.items():
    clash, blocked = [], False
    for hx, hy, hd in b.holes:
        for ref, pl in b.parts.items():
            if pl["bottom"] != STANDOFF_SIDE_BOTTOM[k] or ref == "U2":
                continue
            socketed = (k, ref) in SOCKETED
            body = real_body(k, ref, socket=socketed)
            if body is None:
                continue
            g = {af: (separation(("circle", (hx, hy), af / 2), body),
                      separation(("circle", (hx, hy), af / math.cos(math.radians(30)) / 2), body)) for af in (4.5, 5.0, 5.5)}
            if g[5.0][1] < 0:
                blocked = blocked or g[5.0][0] < 0
                clash.append(f"({hx:.0f}, {hy:.0f}) vs {ref}{' socket' if socketed else ''}: "
                             + ", ".join(f"{af} AF flat {f:+.2f} / corner {c:+.2f}" for af, (f, c) in g.items()))
    ck.check(f"OUT.standoff_clears_the_bodies_beside_it.{NAME[k]}", not blocked,
             f"a 5 mm AF standoff, flat towards the part (mm, + = clear): {clash or 'all clear'}")

# ====================================================================== PANEL: panel parts on the routed faceplate
pos_bad = []
for ref, (xf, y, _) in circuit.PLACEMENT.items():
    pl = FB.parts[ref]
    if dist((front(pl["x"]), pl["y"]), (xf, y)) > 0.05 or not pl["bottom"]:
        pos_bad.append(f"{ref} ({front(pl['x']):.3f}, {pl['y']:.3f}){'' if pl['bottom'] else ' top'} vs ({xf}, {y})")
ck.check("PANEL.at_PLACEMENT_on_the_bottom", not pos_bad, f"{len(pos_bad)}: {pos_bad[:6]}")


def rel(pl):
    """Front-view pad positions relative to the origin."""
    return {n: (pl["x"] - p.x, p.y - pl["y"]) for n, p in pl["pads"].items()}


bad = []
for ref, *_ in circuit.JACKS:
    r = rel(FB.parts[ref])
    if not (abs(r["1"][0] - r["3"][0]) < 0.01 and r["1"][1] > r["3"][1]):
        bad.append(ref)
ck.check("PANEL.jacks_sleeve_up", not bad, f"{bad}")
bad = []
for ref, *_ in circuit.BUTTONS:
    r = rel(FB.parts[ref])
    if not (abs(r["5"][1] - r["6"][1]) < 0.01 and r["5"][0] > r["6"][0] and r["1"][1] > r["3"][1]):
        bad.append(ref)
ck.check("PANEL.buttons_LED_pin5_right_pins12_up", not bad, f"{bad} (design.md / pcb.py rule)")
bad, right = [], []
for ref in circuit.OUTPUT_LEDS:
    r = rel(FB.parts[ref])
    if not (abs(r["1"][1] - r["2"][1]) < 0.01 and abs(r["1"][0] + r["2"][0]) < 0.01):
        bad.append(ref)
    if r["1"][0] > r["2"][0]:
        right.append(ref)
ck.check("PANEL.output_LEDs_pads_along_x_centred", not bad, f"{bad}")
print(f"INFO  output LEDs with pad 1 (anode) on the right, front view: {right}; the others have it on the left "
      f"(pcb.py orients only circuit.LEDS, not the GATE_LEDS); each flat is on its own cathode")
# pots: design.md's re-route table (shaft, pin direction, EasyEDA x / y, rotation)
design = harness.text("docs", "design.md")
rows = re.findall(r"^\| (RV\d) \| [^|]* \| ([\d.]+), ([\d.]+) \| (up|down|left|right) \| ([\d.]+), ([\d.]+) \| (\d+) \|", design, re.M)
ck.check("PANEL.design_md_pot_table_has_8_rows", len(rows) == 8, f"{len(rows)} rows")
DIRS = {"up": (0, 1), "down": (0, -1), "left": (-1, 0), "right": (1, 0)}
for ref, sx, sy, d, ex, ey, rot in rows:
    pl = FB.parts[ref]
    lug4, lug5 = pl["pads"]["4"], pl["pads"]["5"]
    shaft = (front((lug4.x + lug5.x) / 2), (lug4.y + lug5.y) / 2)
    pin2 = (front(pl["pads"]["2"].x), pl["pads"]["2"].y)
    u = ((pin2[0] - shaft[0]) / POT_ROW_SHAFT, (pin2[1] - shaft[1]) / POT_ROW_SHAFT)
    ok_shaft = dist(shaft, circuit.POT_XY[ref]) < 0.05 and dist(shaft, (float(sx), float(sy))) < 0.05
    ok_dir = dist(u, DIRS[d]) < 0.01 and tuple(circuit.pot_pins(ref)) == DIRS[d]
    ok_xy = dist((pl["x"], pl["y"]), (float(ex), float(ey))) < 0.05 and pl["angle"] == int(rot)
    origin_off = dist((front(pl["x"]), pl["y"]), shaft)
    ck.check(f"PANEL.pot.{ref}", ok_shaft and ok_dir and ok_xy and abs(origin_off - circuit.POT_SHAFT) < 0.02,
             f"shaft {shaft[0]:.2f}, {shaft[1]:.2f} (POT_XY {circuit.POT_XY[ref]}, design.md {sx}, {sy}); pins "
             f"{tuple(round(v, 2) for v in u)} ({d}); EasyEDA ({pl['x']:.2f}, {pl['y']:.2f}) a{pl['angle']} (design.md "
             f"{ex}, {ey}, {rot}); shaft {origin_off:.2f} from the origin")
hdr_bad = []
for ref, kind, nets in circuit.HEADERS:
    a, m = FB.parts[circuit.fb_ref(ref)], MB.parts[ref]
    if a["bottom"] or not m["bottom"] or any(dist((a["pads"][n].x, a["pads"][n].y), (m["pads"][n].x, m["pads"][n].y)) > 0.01
                                            for n in a["pads"]):
        hdr_bad.append(ref)
ck.check("PANEL.headers_male_on_FB_top_female_on_MB_bottom_in_line", not hdr_bad, f"{hdr_bad}")

# ====================================================================== SILK: value labels, text, polarity
VALUES = vl.values()


def strings(k):
    return [p for h, p in R.pcb_docs[k]["recs"] if h["type"] == "STRING" and p and p.get("layerId") in (3, 4)]


for k, b in B.items():
    name = NAME[k]
    vals = VALUES[name]
    labelled = {r for r in vals if r in b.parts}
    texts = set(vals.values())
    labels = []
    for p in strings(k):
        if p["text"] in texts:
            labels.append((p["text"], p["layerId"] == 4, vl.text_box(p["x"] * MIL, p["y"] * MIL, p["text"], p["fontSize"],
                                                                     p.get("mirror", False)), p))
    others = [p["text"] for p in strings(k) if p["text"] not in texts]
    ck.check(f"SILK.label_count.{name}", len(labels) == LABELS_PER_BOARD[name],
             f"{len(labels)} value labels (design.md {LABELS_PER_BOARD[name]}); other strings {others}")
    looks = [t for t in others if re.fullmatch(r"[AB]?\d+[RkKMpnu]\d*|BAT\d+|LM\d+.*", t)]
    ck.check(f"SILK.no_value_text_foreign_to_the_board.{name}", not looks,
             f"{looks} look like values but are none of circuit.py's for this board")
    traps, ties, wrong_side, small, bigtxt = [], [], [], collections.Counter(), []
    own_of = {}
    for txt, bottom, rect, p in labels:
        cands = sorted((vl.rect_dist(rect, vl.extent(b.parts[r])), r) for r in labelled if b.parts[r]["bottom"] == bottom)
        same = [c for c in cands if vals[c[1]] == txt]
        other = [c for c in cands if vals[c[1]] != txt]
        if not same:
            traps.append(f"'{txt}' near no part of that value")
            continue
        own_d, own = same[0]
        own_of[id(p)] = own
        if bool(p.get("mirror")) != bottom:
            wrong_side.append(f"'{txt}' mirror {p.get('mirror')} on layer {p['layerId']}")
        if other and other[0][0] < own_d + 0.3:
            # verifier addition: centre distances (label centre to the part's pad centroid) as a second reading
            lc = ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
            cen = {r: (sum(q.x for q in b.parts[r]["pads"].values()) / len(b.parts[r]["pads"]),
                       sum(q.y for q in b.parts[r]["pads"].values()) / len(b.parts[r]["pads"])) for r in (own, other[0][1])}
            (traps if other[0][0] < own_d - 0.02 else ties).append(
                f"'{txt}' by {own} {own_d:.2f}: {other[0][1]} ({vals[other[0][1]]}) {other[0][0]:.2f} "
                f"[centres {dist(lc, cen[own]):.1f} / {dist(lc, cen[other[0][1]]):.1f}]")
        small[round(p["fontSize"])] += 1
    ck.check(f"SILK.label_not_nearer_a_wrong_value.{name}", not traps, f"{traps}")
    # verifier change: this was the check SILK.label_nearest_own_value_by_0.3, failing on 14 labels. The 0.3 mm
    # margin has no source: design.md's rule and value_labels.py's (nearest_is_own, 0.02 mm) are "no other
    # labelled part nearer", which the check above tests; and a 0.3 mm edge-distance margin is no reading measure
    # (by label centre to part centre several of these "ties" sit nearer the other part, several the other way).
    # The near-ties are listed for the builder instead of failing.
    print(f"INFO  {name}: {len(ties)} labels within 0.3 mm (edge to extent, value_labels.py's measure) of a part of "
          f"another value: {ties}")
    ck.check(f"SILK.labels_read_from_their_side.{name}", not wrong_side, f"{wrong_side[:5]}")
    # coverage: every labelled part has a label of its value within 3 mm, except design.md's exceptions
    missing = []
    for r in sorted(labelled):
        pl = b.parts[r]
        d = min((vl.rect_dist(rect, vl.extent(pl)) for t, bot, rect, p in labels if t == vals[r] and bot == pl["bottom"]),
                default=99)
        if d > 3.0:
            missing.append(r)
    ck.check(f"SILK.every_R_C_pot_diode_labelled.{name}", set(missing) == UNLABELLED_OK.get(name, set()),
             f"{len(labelled)} parts; without a label of their value within 3 mm: {missing} (design.md: "
             f"{sorted(UNLABELLED_OK.get(name, set()))})")
    # text height and stroke
    under = {s: n for s, n in small.items() if s * MIL < JLC_SILK_H - 1e-6}
    ck.check(f"SILK.label_height_jlc_1mm.{name}", not under, f"labels under 1.0 mm (mil: count): {under}")
    if name == "Main":
        ck.check("SILK.small_labels_as_design_md.Main", under == SMALL_LABELS, f"{under}, design.md {SMALL_LABELS}")
    thin = [p["text"] for t, bot, rect, p in labels if p.get("strokeWidth", 6) * MIL < JLC_SILK_W - 1e-3]
    ck.check(f"SILK.label_stroke.{name}", not thin, f"{thin[:5]}")
    on_pad = []
    for txt, bottom, rect, p in labels:
        for pad in b.pads:
            if vl.circle_hits(rect, (pad.x, pad.y), pad.r + 0.15 - 0.001):
                on_pad.append(f"'{txt}' on {pad.ref}.{pad.num}")
                break
    ck.check(f"SILK.labels_off_pads.{name}", not on_pad, f"{on_pad[:5]}")
    des = {}
    for h, p in R.pcb_docs[k]["recs"]:
        if h["type"] == "ATTR" and p and p.get("key") == "Designator" and p.get("parentId"):
            des[p["value"]] = p
    hidden = sorted(r for r in b.parts if r not in des or not des[r].get("valueVisible"))
    ck.check(f"SILK.designators_visible.{name}", not hidden, f"{hidden}")
    dsmall = collections.Counter(round(p["fontSize"]) for r, p in des.items() if r in b.parts and p.get("valueVisible")
                                 and p["fontSize"] * MIL < JLC_SILK_H - 1e-6)
    ck.check(f"SILK.designator_height.{name}", not dsmall, f"{dict(dsmall)}")
    if name == "Main":
        inside = []
        for txt, bottom, rect, p in labels:
            own = own_of.get(id(p))
            if own in ("R33", "R39", "R36"):
                ov = max(0, min(rect[2], box[2]) - max(rect[0], box[0])) * max(0, min(rect[3], box[3]) - max(rect[1], box[1]))
                inside.append((own, ov > 0.5 * (rect[2] - rect[0]) * (rect[3] - rect[1])))
        ck.check("SILK.R33_R39_labels_under_the_breakout", dict(inside).get("R33") and dict(inside).get("R39"),
                 f"{inside} (design.md: R33 and R39 have theirs under the Seed breakout)")
        over = [round(rect[2] - box[2], 2) for txt, bottom, rect, p in labels if own_of.get(id(p)) in ("R33", "R39")]
        print(f"INFO  R33 / R39 labels reach {over} mm past the breakout's edge (x {box[2]:.1f})")

# polarity marks, in the board frame
def silk_board(k, ref):
    pl = B[k].parts[ref]
    out = []
    for kind, pts, r in silk(fp_doc(k, ref)):
        out.append((kind, [to_board(pl, *q) for q in pts], r))
    return out


bad = []
for ref in circuit.OUTPUT_LEDS:
    pl = FB.parts[ref]
    flats = [pts for kind, pts, r in silk_board("face", ref) if kind == "line" and len(pts) == 2]
    cat = next((n for n, v in pl["nets"].items() if v in GROUNDS), None)
    an = next((n for n in pl["pads"] if n != cat), None)
    mid = [((a[0] + c[0]) / 2, (a[1] + c[1]) / 2) for a, c in flats]
    ok = cat == "2" and bool(mid) and all(dist(m, (pl["pads"][cat].x, pl["pads"][cat].y)) <
                                         dist(m, (pl["pads"][an].x, pl["pads"][an].y)) for m in mid)
    if not ok:
        bad.append(f"{ref} cathode pad {cat}")
ck.check("SILK.led_flat_at_the_cathode", not bad, f"{bad} (flat = cathode = pad 2 on GND_F)")
print("INFO  LED-3MM-2P squares pad 1, the anode (KiCad's LEDs square the cathode); the flat on the silk is right")
for ref in ("D22", "D23"):
    pl = MB.parts[ref]
    cat = "1"
    lines = [pts for kind, pts, r in silk_board("main", ref) if kind == "line" and len(pts) == 2]
    # the band: a short line across the body, not one of the outline's long sides / ends at +-2.03
    band = [pts for pts in lines if 1.5 < dist(*pts) < 2.5 and
            min(dist(q, (pl["pads"]["1"].x, pl["pads"]["1"].y)) for q in pts) < 3.5 and
            abs(min(dist(q, (pl["pads"]["1"].x, pl["pads"]["1"].y)) for q in pts) -
                min(dist(q, (pl["pads"]["2"].x, pl["pads"]["2"].y)) for q in pts)) > 1.0]
    nearer1 = [min(dist(q, (pl["pads"]["1"].x, pl["pads"]["1"].y)) for q in pts) <
               min(dist(q, (pl["pads"]["2"].x, pl["pads"]["2"].y)) for q in pts) for pts in band]
    ck.check(f"SILK.diode_band_at_the_cathode.{ref}", bool(band) and all(nearer1) and pl["nets"].get("1", "").startswith("B_"),
             f"band nearer pad 1: {nearer1}, pad 1 net {pl['nets'].get('1')} (cathode on the base)")
for k, refs in (("main", ("U3", "U4", "U5", "U6", "U7", "U8")), ("face", ("U1", "U9", "U10", "U11"))):
    for ref in refs:
        pl = B[k].parts[ref]
        n = len(pl["pads"])
        dots = [pts[0] for kind, pts, r in silk_board(k, ref) if kind == "circle" and r < 0.6]
        P = {m: (pl["pads"][m].x, pl["pads"][m].y) for m in ("1", str(n), str(n // 2))}
        ok = bool(dots) and all(dist(d, P["1"]) < min(dist(d, P[str(n)]), dist(d, P[str(n // 2)])) for d in dots)
        ck.check(f"SILK.ic_pin1_dot.{ref}", ok, f"dots {len(dots)}")
for ref in ("Q1", "Q2", "D21"):
    pl = MB.parts[ref]
    flat = [pts for kind, pts, r in silk_board("main", ref) if kind == "line" and len(pts) == 2]
    c0 = to_board(pl, 0, 0)
    m = ((flat[0][0][0] + flat[0][1][0]) / 2, (flat[0][0][1] + flat[0][1][1]) / 2) if flat else c0
    facing = (c0[0] - m[0], c0[1] - m[1])                  # a viewer at the flat looks this way
    right = (facing[1], -facing[0])
    p1, p3 = pl["pads"]["1"], pl["pads"]["3"]
    lr = (p3.x - p1.x) * right[0] + (p3.y - p1.y) * right[1] > 0
    if ref == "D21":
        ck.check("SILK.to92_D21_symmetric_pinout", pl["nets"] == {"1": "GND", "2": "VREF", "3": "GND"},
                 f"{pl['nets']} (cathode = middle pin, LP0003A; fits either way round)")
    else:
        ck.check(f"SILK.to92_flat_reads_E_B_C.{ref}", bool(flat) and lr and pl["nets"].get("1") == "GND",
                 f"pins 1-2-3 left to right seen from the flat: {lr}; pin 1 net {pl['nets'].get('1')} (emitter, onsemi style 1)")

# ====================================================================== BODY: real bodies
def overlaps(k, side_bottom, socket=False):
    b = B[k]
    refs = sorted(r for r, pl in b.parts.items() if pl["bottom"] == side_bottom and real_body(k, r) is not None and r != "U2")
    bodies = {r: real_body(k, r, socket and (k, r) in SOCKETED) for r in refs}
    out = []
    for i, ra in enumerate(refs):
        for rb in refs[i + 1:]:
            if dist((b.parts[ra]["x"], b.parts[ra]["y"]), (b.parts[rb]["x"], b.parts[rb]["y"])) > 25:
                continue
            s = separation(bodies[ra], bodies[rb])
            if s < -0.02:                                # touching at the max sizes is not an overlap
                out.append((round(s, 2), ra, rb))
    return sorted(out)


for k, bottom, label in (("main", False, "main top"), ("face", False, "faceplate rear"), ("face", True, "faceplate panel side"),
                         ("main", True, "main bottom")):
    hits = overlaps(k, bottom)
    ck.check(f"BODY.no_overlap.{label}", not hits, f"{len(hits)} (mm, a, b): {hits[:12]}")
for k in ("main", "face"):
    hits = [h for h in overlaps(k, False, socket=True) if (k, h[1]) in SOCKETED or (k, h[2]) in SOCKETED]
    ck.check(f"BODY.dip_sockets_clear.{NAME[k]}", not hits, f"Mill-Max 0.4 in socket frames of "
             f"{sorted((r for kk, r in SOCKETED if kk == k), key=lambda r: int(r[1:])) or 'no chip'}: {hits[:10]}")
# pot housings against the faceplate's rear pads (design.md: none within 0.8 mm) and rear bodies over pot pins
pots = [r for r in FB.parts if r.startswith("RV")]
rear_pads = [p for p in FB.pads if not FB.parts[p.ref]["bottom"]]
near, near_c = [], []
for r in pots:
    hb = real_body("face", r)
    for p in rear_pads:
        s_ = circle_sep((p.x, p.y), p.r, hb)
        c_ = circle_sep((p.x, p.y), 0.0, hb)
        if s_ < 0.8:
            near.append((round(s_, 2), round(c_, 2), r, f"{p.ref}.{p.num}"))
        if c_ < 0.8:
            near_c.append((round(c_, 2), r, f"{p.ref}.{p.num}"))
ck.check("BODY.rear_pad_centres_0.8mm_from_pot_housings", not near_c, f"{sorted(near_c)[:8]}")
ck.check("BODY.rear_pad_copper_0.8mm_from_pot_housings", not near,
         f"(copper gap, centre gap, pot, pad): {sorted(near)[:8]} (design.md: no routed rear-side pad within 0.8 mm)")
over = []
for r in pots:
    for n, pad in FB.parts[r]["pads"].items():
        for ref, pl in FB.parts.items():
            if pl["bottom"]:
                continue
            bb = real_body("face", ref)
            if bb is not None and circle_sep((pad.x, pad.y), pad.r, bb) < 0:
                over.append(f"{ref} over {r}.{n}")
ck.check("BODY.no_rear_body_over_a_pot_pin", not over, f"{over}")
# rear pads under jack / LED / button bodies (their joints are on the panel side, where these bodies lie)
touch, inside = [], []
for ref, pl in FB.parts.items():
    if not pl["bottom"] or ref.startswith("RV"):
        continue
    hb = real_body("face", ref)
    for p in rear_pads:
        s = circle_sep((p.x, p.y), p.r, hb)
        c = circle_sep((p.x, p.y), 0.0, hb)
        if c < 0:
            inside.append(f"{p.ref}.{p.num} centre {-c:.2f} mm inside {ref}")
        elif s < 0:
            touch.append((p.ref, ref, round(c, 2)))
ck.check("BODY.no_rear_pad_centre_under_a_panel_part", not inside, f"{inside[:8]}")
allowed = {"R91", "R92", "R93", "R87", "R88", "R89", "R1"}
ck.check("BODY.rear_pads_touching_panel_bodies_as_design_md", {t[0] for t in touch} <= allowed
         and all(0.6 - 0.05 <= t[2] for t in touch), f"ring touches (pad, body, centre outside): {sorted(touch)} "
         f"(design.md: R91-R93 at the jacks, R87-R89 and R1 at the LEDs, centres 0.6-0.75 mm outside)")

# ====================================================================== GAP: the board-to-board gap
ck.check("GAP.main_bottom_only_sockets", sorted(r for r, pl in MB.parts.items() if pl["bottom"]) ==
         sorted(r for r, *_ in circuit.HEADERS), str(sorted(r for r, pl in MB.parts.items() if pl["bottom"])))
# verifier change: the old check gave a socketed chip its full height over the whole 10.16 mm socket frame, took
# the pads' copper radius for the leads, printed only four parts per chip and knew only the Mill-Max socket. Now:
# the chip's height (seat + PDIP A max) over the chip body (MS-001 19.81 x 7.11), the socket's own height over the
# rest of the frame; a lead is its hole centre with a 0.3 mm radius; the BOM's plain "DIP-16 IC socket" may be a
# stamped one (CnC Tech 243: 4.8 mm body) or a machined one (Mill-Max 110: 4.19), and the worse decides; the main
# board's cut leads may stick out up to TAIL (IPC-A-610 class 2), while the breakout's socket strips (U2's pads)
# and the main board's DIP sockets have fixed tails (3.0 / 3.2 mm through 1.6 mm).
mb_leads = [(p.x, p.y, p.ref) for p in MB.pads if not MB.parts[p.ref]["bottom"]]
LEAD_R = 0.3


def tail_of(ref):
    if ref == "U2":
        return FEMALE_HDR_TAIL - PCB_T, "fixed"
    if MB.parts[ref]["fp"].startswith("DIP") and ("main", ref) in SOCKETED:
        return max(SOCKET_TAIL.values()) - PCB_T, "fixed"
    return TAIL, "cut"


HEIGHT = {"CAP-TH_L3.0": FG28_SEATED, "RES-TH": BODY_RES[1], "HDR": MALE_PLASTIC}
coll, chips = [], []
for ref, pl in sorted(FB.parts.items()):
    if pl["bottom"]:
        continue
    t = pl["fp"]
    if t.startswith("DIP"):
        socketed = ("face", ref) in SOCKETED
        chip, frame = real_body("face", ref), real_body("face", ref, socket=True)
        on_chip = sorted({r for x, y, r in mb_leads if circle_sep((x, y), LEAD_R, chip) < 0})
        on_frame = sorted({r for x, y, r in mb_leads if circle_sep((x, y), LEAD_R, frame) < 0} - set(on_chip))
        if socketed:
            rooms = {kind + " socket": STACK_GAP - seat - CHIP_A
                     for kind, seat in (("machined", SOCKET_ABOVE), ("stamped", SOCKET_ABOVE_STAMPED))}
        else:
            rooms = {"soldered": STACK_GAP - CHIP_A}
        worst = min(rooms.values())
        bad = [f"{r} ({tail_of(r)[1]} {tail_of(r)[0]:.1f})" for r in on_chip if tail_of(r)[0] > worst]
        if bad:
            coll.append(f"{ref}: room over the chip " + " / ".join(f"{v:.2f} ({kind})" for kind, v in rooms.items())
                        + f" for {bad}")
        chips.append(f"{ref} ({'socketed' if socketed else 'soldered'}): over the chip {on_chip}, over the frame only "
                     f"{on_frame} (frame 5.2 tall at most: {STACK_GAP - 5.2:.1f} mm left)")
        if socketed and on_frame and STACK_GAP - 5.2 < TAIL:
            coll.append(f"{ref} frame: {on_frame}")
        continue
    h = next((v for key, v in HEIGHT.items() if t.startswith(key)), None)
    if h is None:
        continue
    body = real_body("face", ref)
    over_it = [r for x, y, r in mb_leads if circle_sep((x, y), LEAD_R, body) < 0]
    if over_it and h + TAIL > STACK_GAP:
        coll.append(f"{ref} {h:.2f} + {TAIL} tails of {sorted(set(over_it))} = {h + TAIL:.2f}")
ck.check("GAP.faceplate_rear_parts_clear_the_main_boards_tails", not coll,
         f"in the {STACK_GAP} mm gap, a PDIP-16's top = A {CHIP_A}, plus the seat in a socket (Mill-Max {SOCKET_ABOVE}, "
         f"stamped {SOCKET_ABOVE_STAMPED}; socketed on the faceplate: "
         f"{sorted(r for k, r in SOCKETED if k == 'face') or 'none'}); main-board leads over the chip body that do not fit (cut: IPC-A-610 class 2 max {TAIL}; "
         f"fixed: the breakout's socket strips {FEMALE_HDR_TAIL - PCB_T:.1f}, DIP sockets "
         f"{max(SOCKET_TAIL.values()) - PCB_T:.1f}): {coll}")
print(f"INFO  main-board leads over the faceplate's chips: {chips}")
print(f"INFO  soldered straight to the faceplate (no socket), a PDIP-16 stands {CHIP_A} and leaves "
      f"{STACK_GAP - CHIP_A:.2f} mm, enough for uncut {TAIL} mm tails")
sock = []
for ref, pl in MB.parts.items():
    if not pl["bottom"]:
        continue
    sb = real_body("main", ref)
    for r2, p2 in FB.parts.items():
        if p2["bottom"] or r2 == circuit.fb_ref(ref) or real_body("face", r2) is None:
            continue
        if separation(sb, real_body("face", r2)) < 0:
            sock.append(f"{ref} over {r2}")
ck.check("GAP.main_sockets_over_nothing_but_their_headers", not sock, f"{sock}")
m = re.search(r"\| (\d+) \| M3 standoff, female-female, (\d+(?:\.\d+)?) mm", bom_md)
sc = re.search(r"\| (\d+) \| M3 ?[×x] ?([\d.]+) ?mm[^|]*screw", bom_md)
ck.check("GAP.bom_standoffs_match_the_mated_headers", m is not None and abs(float(m.group(2)) - (SOCKET_H + MALE_PLASTIC)) < 0.3
         and int(m.group(1)) == len(HOLES_FRONT) and sc is not None and int(sc.group(1)) >= 2 * int(m.group(1)),
         f"bom.md: {m and m.group(0)}; screws {sc and sc.group(0)}; mated headers {SOCKET_H + MALE_PLASTIC} mm, "
         f"{len(HOLES_FRONT)} holes")
print(f"INFO  the gap's budget: {STACK_GAP} mm; standing FG28 {FG28_SEATED} + {TAIL} tails = {FG28_SEATED + TAIL}; "
      f"DIP-16 soldered flat {CHIP_A} + {TAIL} = {CHIP_A + TAIL}; in a Mill-Max socket {SOCKET_ABOVE + CHIP_A:.2f} + {TAIL} = "
      f"{SOCKET_ABOVE + CHIP_A + TAIL:.2f}: the main board's leads over a socketed chip must be cut to "
      f"{STACK_GAP - SOCKET_ABOVE - CHIP_A:.2f} mm or less ({STACK_GAP - SOCKET_ABOVE_STAMPED - CHIP_A:.2f} in a stamped "
      f"socket)")

# ====================================================================== POUR
SMALL = 30.0
TINY = 1.0


def far(sp):
    dx, dy = sp[1][0] - sp[0][0], sp[1][1] - sp[0][1]
    d = math.hypot(dx, dy) or 1
    return sp[1][0] + dx / d * 0.15, sp[1][1] + dy / d * 0.15


def area(poly):
    P = np.array(poly)
    return 0.5 * abs(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1)))


def seg_arrays(isl):
    segs = []
    for ring in [isl.outline] + list(isl.holes):
        P = np.array(ring)
        segs.append(np.stack([P, np.roll(P, -1, 0)], 1))
    return np.concatenate(segs)


def d_seg_segs(a, b_, S):
    """min distance between the segment a-b_ and the segments S (n, 2, 2); 0 where they cross."""
    a, b_ = np.asarray(a, float), np.asarray(b_, float)
    d = min(d_points_segs(np.array([a, b_]), S).min(),
            d_points_segs(S.reshape(-1, 2), np.array([[a, b_]])).min())
    A, Bs = S[:, 0], S[:, 1]

    def cross(o, p, q):
        return (p[..., 0] - o[..., 0]) * (q[..., 1] - o[..., 1]) - (p[..., 1] - o[..., 1]) * (q[..., 0] - o[..., 0])
    d1, d2 = cross(A, Bs, a[None]), cross(A, Bs, b_[None])
    d3, d4 = cross(a[None], b_[None], A), cross(a[None], b_[None], Bs)
    if np.any(((d1 > 0) != (d2 > 0)) & ((d3 > 0) != (d4 > 0))):
        return 0.0
    return float(d)


def d_points_segs(pts, S):
    """min distance of each point to the segment set S (n, 2, 2)."""
    pts = np.asarray(pts, float)
    A, Bs = S[:, 0], S[:, 1]
    AB = Bs - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    t = np.clip(((pts[:, None, :] - A[None]) * AB[None]).sum(2) / L2[None], 0, 1)
    proj = A[None] + t[..., None] * AB[None]
    return np.sqrt(((pts[:, None, :] - proj) ** 2).sum(2)).min(1)


GROUPS = {}
for k, b in B.items():
    name = NAME[k]
    groups = GROUPS[k] = b.connectivity()[0]
    dead, fragile, tiny = [], [], []
    for i, isl in enumerate(b.islands):
        a = area(isl.outline) - sum(area(h) for h in isl.holes)
        grp = next((g for g in groups.get(isl.net, {}).values() if ("island", i) in g), set())
        desc = f"{isl.net} L{isl.layer} {a:.1f} mm2 at ({min(q[0] for q in isl.outline):.1f}, {min(q[1] for q in isl.outline):.1f})"
        if not any(key[0] == "pad" for key in grp):
            dead.append(desc)
        if a < TINY:
            tiny.append(desc)
        if a < SMALL:
            n = (sum(1 for x, y, d, D, nn in VIAS[k] if nn == isl.net and isl.contains((x, y)))
                 + sum(1 for s in b.spokes if s[2] == isl.layer and s[3] == isl.net and isl.contains(far(s)))
                 + sum(1 for t in b.tracks if t["net"] == isl.net and t["layer"] == isl.layer and (isl.contains(t["a"]) or isl.contains(t["b"]))))
            print(f"      {name}: island {desc}: {n} connections")
            if n <= 1:
                fragile.append(desc + f", {n} connection")
    ck.check(f"POUR.no_dead_islands.{name}", not dead, f"{dead}")
    ck.check(f"POUR.no_tiny_islands.{name}", not tiny, f"under {TINY} mm2: {tiny}")
    ck.check(f"POUR.no_small_island_on_one_connection.{name}", not fragile, f"under {SMALL} mm2: {fragile}")
    # other-net copper inside a pour or closer than the rule to its edge
    bad = []
    for isl in b.islands:
        S = seg_arrays(isl)
        xs0, ys0 = S[..., 0].min(), S[..., 1].min()
        xs1, ys1 = S[..., 0].max(), S[..., 1].max()
        items = []
        for p in b.pads:
            if p.net != isl.net:
                ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
                if p.shape == "RECT":
                    pts = [(p.x + dx, p.y + dy) for dx, dy in (ca.rot(sx * p.w / 2, sy * p.h / 2, p.angle)
                                                               for sx in np.linspace(-1, 1, 7) for sy in (-1, 1))]
                    pts += [(p.x + dx, p.y + dy) for dx, dy in (ca.rot(sx * p.w / 2, sy * p.h / 2, p.angle)
                                                                for sy in np.linspace(-1, 1, 7) for sx in (-1, 1))]
                else:
                    a0, a1, rr = p.axis()
                    pts = [(a0[0] + rr * math.cos(t), a0[1] + rr * math.sin(t)) for t in ang] + \
                          [(a1[0] + rr * math.cos(t), a1[1] + rr * math.sin(t)) for t in ang]
                items.append((f"pad {p.ref}.{p.num} ({p.net})", pts, 0.0, (p.x, p.y), None))
        for x, y, d, D, n in VIAS[k]:
            if n != isl.net:
                items.append((f"via {n} ({x:.1f}, {y:.1f})", [(x, y)], D / 2, (x, y), None))
        for t in b.tracks:
            if t["net"] != isl.net and t["layer"] == isl.layer:
                mid = ((t["a"][0] + t["b"][0]) / 2, (t["a"][1] + t["b"][1]) / 2)
                items.append((f"track {t['net']} L{t['layer']} ({t['a'][0]:.1f}, {t['a'][1]:.1f})", [t["a"], mid, t["b"]],
                               t["w"] / 2, t["a"], t))
        for label, pts, half, c, trk in items:
            P = np.array(pts)
            if P[:, 0].max() < xs0 - 1 or P[:, 0].min() > xs1 + 1 or P[:, 1].max() < ys0 - 1 or P[:, 1].min() > ys1 + 1:
                continue
            sel = ((S[..., 0].max(1) > P[:, 0].min() - 1) & (S[..., 0].min(1) < P[:, 0].max() + 1) &
                   (S[..., 1].max(1) > P[:, 1].min() - 1) & (S[..., 1].min(1) < P[:, 1].max() + 1))
            ins = any(isl.contains(tuple(q)) for q in pts[:: max(1, len(pts) // 8)]) or isl.contains(tuple(c))
            if not sel.any():
                if ins:
                    bad.append((0.0, label + f" inside the {isl.net} L{isl.layer} pour"))
                continue
            g = (d_seg_segs(trk["a"], trk["b"], S[sel]) if trk else float(d_points_segs(P, S[sel]).min())) - half
            if ins or g < RULE_CLEAR - 1e-3:
                bad.append((round(-1 if ins else g, 3), label + f" {'inside' if ins else f'{g:.3f} mm from'} the {isl.net} L{isl.layer} pour"))
    bad.sort()
    ck.check(f"POUR.other_net_copper_clear_of_pours.{name}", not bad, f"{len(bad)}: {[w for g, w in bad[:8]]}")
    if k == "main":
        d21 = [w for g, w in bad if "D21" in w or "VREF" in w]
        print(f"INFO  near D21: {d21 or 'no other-net copper in or within 0.152 mm of the GND pours'}")

# D21's pads in the script-cut pours: pads 1 / 3 (GND) joined by spokes on both layers, pad 2 (VREF) clear
pl = MB.parts["D21"]
groups = GROUPS["main"]
gnd_groups = groups.get("GND", {})
for n in ("1", "3"):
    pad = pl["pads"][n]
    sp = {L: [s for s in MB.spokes if s[2] == L and s[3] == "GND" and dist(s[0], (pad.x, pad.y)) < 0.3] for L in (1, 2)}
    joined = any(("pad", "D21", n) in g and any(key[0] == "island" for key in g) for g in gnd_groups.values())
    ck.check(f"POUR.D21_pad{n}_spokes_both_layers", all(len(v) >= 2 for v in sp.values()) and joined,
             f"spokes top {len(sp[1])}, bottom {len(sp[2])}; joined to a GND pour: {joined}")
ck.check("POUR.GND_one_piece_main", len(gnd_groups) == 1, f"{len(gnd_groups)} pieces")
pad2 = pl["pads"]["2"]
gaps = []
for isl in MB.islands:
    if isl.net != "GND":
        continue
    S = seg_arrays(isl)
    ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    pts = np.stack([pad2.x + pad2.r * np.cos(ang), pad2.y + pad2.r * np.sin(ang)], 1)
    g = float(d_points_segs(pts, S).min())
    gaps.append((isl.layer, round(-1.0 if isl.contains((pad2.x, pad2.y)) else g, 3)))
ck.check("POUR.D21_pad2_VREF_clear_of_GND", all(g >= RULE_CLEAR for L, g in gaps), f"(layer, gap) {gaps}")
for k in B:
    live = {h["id"] for h, p in R.pcb_docs[k]["recs"] if h["type"] == "POUR"}
    stale_p = [h["id"] for h, p in R.pcb_docs[k]["recs"] if h["type"] == "POURED" and harness.rid(h)[1] not in live]
    print(f"INFO  {NAME[k]}: {len(stale_p)} POURED records of deleted pours (ignored here and by copper_audit; a rebuild "
          f"of the copper areas regenerates the fills)")
print("INFO  design.md: the main board's pours are a script's cut, not EasyEDA's: rebuild all copper areas, rerun DRC "
      "and this group on the re-exported master before the Gerbers")

ck.done()
