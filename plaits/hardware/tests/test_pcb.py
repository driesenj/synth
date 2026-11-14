"""PCB group: manufacturing, assembly and fit checks on the routed master (Plaits-routed.epro2) that
copper_audit.py does not do (its clearance / connectivity results are asserted, not redone).

  A footprints   Thonkiconn, Alpha RD901F, DIP-14 / DIP-16, LED-3MM-3P, DO-35, the standing and flat
                 resistors, the 5.08 mm capacitors, the 1x8 / 1x9 headers, the Thonk LED button against the
                 parts' drawings (pad positions, pitch, row spacing, pin-1 marks)
  B breakout     DAISY-SEED-POWER-OPAMPS-2.54 against Rob Heel's seed_power_opamps Gerbers / Excellon file:
                 every breakout pin over a Plaitsy pad, pitch, row spacing, which side faces the main board,
                 the breakout's own GND / -12 V / +12 V / VIN pins on Plaitsy's nets
  C drills       every pad hole against the lead or tail it takes (IPC-2222 fit), annular rings, plated
                 slots, vias, hole-to-hole and drill-to-track spacing against JLCPCB's capabilities page;
                 the panel's NPTH holes and slots
  D outline      both boards 59.4 x 108, the three M3 holes identical on both boards and at
                 pcb.HOLES_FRONT, copper to the edge and to the holes, nothing but ground under a standoff
                 or a screw head, no part body in a standoff's or a screw head's way
  E tracks       power tracks 0.6 mm (design.md), signal 0.3 mm, JLCPCB minimums; copper_audit's 0.152 mm
                 clearance and connectivity results
  F labels       the value labels value_labels.py added: text = circuit.py's value, nearest its own part by
                 0.3 mm (outline to outline), JLCPCB silkscreen minimums, not over pads / holes / labels,
                 which parts are left unlabelled
  G bodies       real body sizes at the largest the parts come in, overlaps per side, decouplers beside
                 their chips, rear-side bodies over the panel parts' solder joints and the reverse
  H stacking     the 11 mm header gap against the faceplate's tallest rear parts (a socketed DIP as its chip
                 at socket + A and its frame at the socket's height) and what the main board sticks into the
                 gap (the breakout's female-header tails and the DIP-socket tails, which are not clipped, and
                 clipped leads); the female sockets against the main board's other bottom-side joints; nothing
                 under the breakout
  I pours        ground islands per layer reached by a pad, slivers on one spoke, thermal spokes per pad

Run from plaits/hardware/tests:  python test_pcb.py
Read-only: imports the tools and opens the committed export as a zip. Every datasheet / fab number is in the
constants block with its source; "not confirmed" marks the ones that could not be read.
"""
import collections
import math
import re

import harness

ck = harness.Checks("pcb")
ca = harness.load("copper_audit")
circuit = harness.load("circuit")
pcbmod = harness.load("pcb")
vl = harness.load("value_labels")
R = harness.routed()
MB, FB = R.main, R.face
MIL = harness.MIL

# ====================================================================== constants (datasheets, fab)
# JLCPCB PCB capabilities, 2-layer 1 oz FR4 (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-11-12;
# re-read by the verifier 2026-11-13: every figure below as on the page)
JLC_PTH_MIN = 0.15          # min plated hole, 2-layer ("0.15 - 6.3 mm")
JLC_PTH_REC = 0.50          # "recommended PTH size >= 0.5 mm" (mask / tin in the hole)
JLC_TOL_PLUS, JLC_TOL_MINUS = 0.13, 0.08    # finished through-hole tolerance +0.13 / -0.08
JLC_VIA_DRILL_MIN = 0.15    # min via hole, 2-layer
JLC_VIA_DIA_MIN = 0.25      # min via diameter, 2-layer
JLC_RING_MIN = 0.18         # PTH annular ring, absolute minimum (2-layer 1 oz)
JLC_RING_REC = 0.25         # recommended 0.25 mm or above
JLC_NPTH_MIN = 0.50         # min non-plated hole
JLC_PSLOT_MIN = 0.50        # min plated slot width, 2-layer
JLC_NPSLOT_MIN = 1.00       # min non-plated slot width
JLC_HOLE_HOLE_PAD = 0.45    # pad hole to pad hole, different nets
JLC_HOLE_HOLE_VIA = 0.20    # via hole to via hole
JLC_PTH_TRACK = 0.28        # PTH to track, minimum (0.35 recommended)
JLC_PTH_TRACK_REC = 0.35
JLC_VIA_TRACK = 0.20        # "Via hole to Track 0.2mm" (its own row; the PTH figures are for pad holes). Verifier
                            # fix 2026-11-13: the vias were held to the PTH 0.28 / 0.35 rule
JLC_NPTH_TRACK = 0.20       # NPTH to track
JLC_EDGE = 0.20             # copper to a routed board edge
JLC_TRACK_MIN = 0.10        # min trace width / spacing, 1 oz 2-layer (4 / 4 mil)
JLC_SILK_W = 0.15           # min silkscreen line width
JLC_SILK_H = 1.00           # min text height (40 mil)
JLC_SILK_RATIO = 1 / 6      # character (line) width to height: "The preferred ratio of width to height is 1:6" (a
                            # preference on the page, not a minimum; the 0.15 line and 1.0 mm height are the minimums)
JLC_PAD_SILK = 0.15         # pad to silkscreen
# IPC-2222 table 9-3: hole minus maximum lead, level C (tightest) 0.15 on the nominal drill; and the smallest
# finished hole (drill - 0.08) must still pass the lead: round leads with 0.05 mm to spare, square / flat leads
# their diagonal (the mixer suite's rule). Level A's 0.70 maximum for a loose hole (nominal - minimum lead).
IPC_FIT_MIN, INSERT_MIN, IPC_FIT_MAX = 0.15, 0.05, 0.70

# Leads, (shape, max width, max thickness[, min width]) in mm; 'round' -> diameter.
DIP_LEAD = ("rect", 0.56, 0.36)
#   TI N package (PDIP-14, TL074): b 0.36-0.56, c 0.20-0.36 (the mixer suite's reading of TI's N0014A); TI MPDI003
#   (R-PDIP-T16, "falls within JEDEC MS-001"): lead width 0.381-0.533, thickness 0.25 nom. The chips sit in DIP
#   sockets (bom.md), whose tails are no bigger than a DIP lead: the DIP lead is the conservative case.
SQ_POST = ("rect", 0.64, 0.64)
#   2.54 mm header post / socket tail: 0.64 mm (0.025 in) square nominal. Amphenol FCI BergStik II drawing 67996
#   rev DH (the breakout's J2 family, LCSC C178292's PDF), sheet 1: post □0.025 [0.64] ±0.001 [0.03] (0.67 max,
#   diagonal 0.95), "RECOMMENDED HOLE PATTERN" Ø0.040 [1.02] ±0.003 [0.08]. A sharp-cornered 0.67 square would
#   not pass the maker's own 0.94 minimum hole, so the corners are radiused: for the posts the maker's recommended
#   hole range is the fit criterion (verifier change 2026-11-13; the 0.64 nominal diagonal used before is a typ
#   where the max applies).
POST_HOLE, POST_HOLE_TOL = 1.02, 0.08
POST_FPS = ("HDR-1x8-P2.54", "HDR-1x9-P2.54", "DAISY-SEED-POWER-OPAMPS-2.54")
LEADS = {
    "DIP-14-W7.62-P2.54": {"*": DIP_LEAD},
    "DIP-16_L20.0-W6.4-P2.54-LS7.6-BL": {"*": DIP_LEAD},
    "HDR-1x8-P2.54": {"*": SQ_POST},
    "HDR-1x9-P2.54": {"*": SQ_POST},
    "DAISY-SEED-POWER-OPAMPS-2.54": {"*": SQ_POST},      # the main board's 8.5 mm female strips (bom.md)
    # 1/4 W metal film (bom.md: Tayda 1/4 W 1 %): lead 0.6 mm max (brief; Yageo MFR-25 0.54 +-0.05), 0.5 min
    "RES-TH-VERTICAL-P2.54": {"*": ("round", 0.60, 0.60, 0.50)},
    "RES-TH_L6.2-W2.3-LR1F1K0": {"*": ("round", 0.60, 0.60, 0.50)},
    "RES-TH_BD2.3-L6.3-P10.30-D0.6": {"*": ("round", 0.60, 0.60, 0.50)},
    # BAT85, DO-35: lead 0.5 mm max (brief); JEDEC DO-35 allows 0.56 (Vishay 1N4148 0.46-0.56): 0.56 used
    "DO-35_BD2.0-L4.0-P8.0-D0.5-RD": {"*": ("round", 0.56, 0.56, 0.46)},
    # dipped 5.08 mm ceramics / 5 mm film (bom.md "5.08 mm leads"): 0.5 mm leads (TDK FG 0.5; WIMA FKS2 / MKS2
    # 0.5; KEMET C320 0.51): 0.55 max with tolerance, 0.45 min (not re-confirmed: the fg28 folder is empty)
    "CAP-TH_L3.0-W2.0-P5.08-D0.7": {"*": ("round", 0.55, 0.55, 0.45)},
    # 1 uF X7R, AVX SR30 class (footprint name): 0.508 mm (0.020 in) leads (not re-confirmed)
    "CAP-TH_L7.6-W3.8-P5.08-D0.51": {"*": ("round", 0.55, 0.55, 0.45)},
    # 3 mm 3-lead bicolour LED: Kingbright L-3WEGW (DSAA6458 V.18A, page 1 drawing, rendered from the vector
    # PDF by the verifier): leads □0.5 [0.02] (printed +0.25 / -0.1), dam bar 0.7 max, recommended holes 0.889
    "LED-3MM-3P": {"*": ("rect", 0.50, 0.50)},
    # Alpha RD901F terminals: Alpha's drawing is a scanned image (not read); assumed 0.8 x 0.4 flat
    # (diagonal 0.89, the mixer suite's assumption): not confirmed. The snap-in lugs: assumed 1.0 x 0.5 in the
    # 1.1 x 1.8 slot (KiCad RD901F-40-00D slot), not confirmed.
    "POT-ALPHA-9MM-RD901F": {"1": ("rect", 0.8, 0.4), "2": ("rect", 0.8, 0.4), "3": ("rect", 0.8, 0.4),
                             "4": ("rect", 1.0, 0.5), "5": ("rect", 1.0, 0.5)},
    # Thonkiconn PJ398SM / QingPu WQP518MA flat lugs: no dimensioned drawing (Thonk's site blocks fetches); assumed
    # 1.0 x 0.3 (the mixer suite's assumption), checked against the slots: not confirmed. The footprint is LCSC's
    # WQP518MA and the one the user's built boards carry.
    "CONN-TH_WQP-WQP518MA": {"*": ("rect", 1.0, 0.3)},
    # Thonk low-profile LED button: no dimensioned drawing in the repo (parts.md cites LowProfileButton.pdf and
    # Thonk's KiCad footprint, pins only): assumed 0.7 x 0.5, not confirmed
    "SW-TACT-LP-LED-THONK": {"*": ("rect", 0.7, 0.5)},
}

# Thonkiconn barrel centre to the lugs (Thonk's PJ398SM drawing as parts.md / copper_audit quote it: sleeve
# 6.48, switch 3.38 on the sleeve side, tip 4.92 on the other side): recalled figures, not re-confirmed.
THONK_SLEEVE, THONK_SWITCH, THONK_TIP = 6.48, 3.38, 4.92
# Alpha RD901F-40 (parts.md, KiCad Potentiometer_Alpha_RD901F-40-00D_Single_Vertical): pins 2.5 mm apart in a row,
# shaft 7.5 mm from the pin row, mounting lugs on the shaft line at +-4.8 mm; housing 9.5 mm wide.
ALPHA_PITCH, ALPHA_SHAFT, ALPHA_LUG_X = 2.5, 7.5, 4.8
# Thonk low-profile LED button (parts.md, Thonk's SW_Tact_Low_Profile_LED_ExtraHoles.kicad_mod): switch pins on a
# 5.08 mm square, LED pins at x +-2.7 on the centre line; 7.5 mm square body. No Thonk drawing confirms the pins.
BTN_SQ, BTN_LED_X, BTN_BODY = 5.08, 2.7, 7.5
# 3 mm bicolour LED, 3 leads. Verifier 2026-11-13: Kingbright L-3WEGW (DSAA6458 V.18A, page 1, the vector drawing
# rendered): the leads leave the body close together, kink out within "1.0 MAX" of the flange and run at
# 2.54 [0.1] pitch; "RECOMMENDED PCB LAYOUT" Ø0.889 x 3 at 2.54 [0.1]; 1 anode red, 2 common cathode, 3 anode
# green. JLCPCB files it as SIP-3-2.54mm. The writer took 1.27 from parts.md (the house's own note, not a part's
# datasheet), which only restated the footprint. Tayda's A-8599 page (the BOM's source) gives no pitch.
LED_PITCH = 2.54
LED_HOLE_REC = 0.889
# DO-35 BAT85 body (Vishay BAT85 / JEDEC DO-35: body 3.8-4.56 long, 2.0 max diameter, the mixer suite's 4.56 x
# 2.28 for the 1N4148): 4.56 max used; bend radius: a lead bent at least 1.0 mm (2 lead diameters) from the body
# (IPC-A-610 / J-STD-001 bend clearance, not re-confirmed): pitch >= 4.56 + 2 x (1.0 + 0.56)
BODY_DO35 = (4.56, 2.28)
LEAD_BEND_MIN = 1.0

# Daisy Seed (Electro-Smith datasheet v1.0.5, "Landing pattern"): 2.54 mm pitch, rows 15.24 mm apart.
SEED_PITCH, SEED_ROWS = 2.54, 15.24
# Rob Heel's seed_power_opamps, Gerbers + Excellon of 2025-08-29 (github.com/rob-scape/daisy-seed-breakout-boards,
# folder daisy-seed-dcdc-opamps; copied in the Marblesy session's datasheets/breakout-gerbers):
#   Drill_PTH_Through.DRL (METRIC, 3:3): Seed sockets T05 1.200 mm at x 36.830 + 2.54 k (k = 0..19), y -1.778 and
#   -17.018; 1x4 headers T02 0.889 mm at x 24.130..31.750 and 87.630..95.250 on both rows; 2x5 power header T02
#   at x 6.085 / 8.625, y -3.894..-14.054. Outline 0.152..96.901 x 0..-18.796 (GKO). NPTH 3.000 at (2.159, -2.159)
#   and (2.159, -17.018).
BRK_SEED_X0, BRK_ROW_A, BRK_ROW_B = 36.830, -1.778, -17.018
BRK_SEED_D, BRK_HDR_D = 1.200, 0.889
BRK_HDR_X = (24.130, 26.670, 29.210, 31.750, 87.630, 90.170, 92.710, 95.250)
BRK_OUTLINE = (0.152, -18.796, 96.901, 0.0)
#   Which pins are what, traced from the copper (top + bottom layer rasterised at 0.02 mm, joined through every
#   PTH; scratch script, 2026-11-12):
#   - GND (the bottom pour, also 2x5 pins 3/5, DC/DC pin 3): Seed holes (36.83, -17.018) and (85.09, -1.778),
#     header holes x 31.75, 87.63 and 92.71 on both rows.
#   - -12 V side: header holes x 24.13 / 26.67 / 29.21 at y -17.018 (through the SOD-123 at y -16.89 to 2x5
#     pins 1 / 2, the square pin 1 = -12 V); +12 V: the same x at y -1.778 (through the SOD-123 at y -1.78 to
#     2x5 pins 9 / 10).
#   - VIN: Seed hole (82.55, -1.778), on the DC/DC (T03, 0.915 mm, x 27.559) pin 4, +Vo.
#   - square (pin 1) pads: x 31.75 on both rows (the power headers' GND), x 95.25 on both rows.
BRK_GND = [(36.83, -17.018), (85.09, -1.778)] + [(x, y) for x in (31.75, 87.63, 92.71) for y in (BRK_ROW_A, BRK_ROW_B)]
BRK_NEG12 = [(x, BRK_ROW_B) for x in (24.13, 26.67, 29.21)]
BRK_POS12 = [(x, BRK_ROW_A) for x in (24.13, 26.67, 29.21)]
BRK_VIN = (82.55, -1.778)
BRK_SQUARE = [(31.75, BRK_ROW_A), (31.75, BRK_ROW_B), (95.25, BRK_ROW_A), (95.25, BRK_ROW_B)]
#   Side: the paste layer is top only (every SMD part on the Gerber top), while the Seed's 51 x 18 outline, the
#   100 uF cans and the 1x4 headers' outlines are on the bottom silkscreen; the Seed pins traced above run
#   clockwise in the Gerber top view, i.e. the Seed's own counter-clockwise top view (datasheet pinout) seen
#   through the board. So the breakout mounts on Plaitsy SMD side down, the Seed on top facing up, and looking
#   down on the main board one sees the breakout's Gerber-bottom side: its drill pattern mirrored (y -> -y).
#   Verifier 2026-11-13, independently: the bottom silk reads right only mirrored and carries H1 / H2 + "SEED USB",
#   U3, C9 / C18 "100uF", J2 "RED STRIPE" and the J1 / J3 / J4 / J5 labels; its Seed pin labels (G, VIN, 3.3D at
#   x 85.09 / 82.55 / 80.01 on y -1.778, 3.3A at x 36.83 on y -1.778, G at x 36.83 on y -17.018) are pins 40, 39,
#   38, 21, 20 and land on the footprint's pads 40 GND, 39, 38 3V3D, 21 3V3A, 20 GND only mirrored. Rob Heel's
#   build photo (github README, seed_breadboard_01.jpg): Seed, DC/DC, both 100 uF cans and the IDC cable on top,
#   the long female-header tails and the 1x4 male headers (plastic under the board, pins down) below.
BRK_MIRRORED = True

# Bodies, mm (max). Every body is checked at the largest size the BOM's description allows.
BODY_R_STAND_D = 2.6         # 1/4 W metal film body diameter: Yageo MFR (Apr 2024 V.4) dimension table, MFR-25 =
                             # the MFR50S size: L 6.3 +-0.5, D 2.4 +-0.2, d 0.55 +-0.05 -> D 2.6 max. Verifier fix
                             # 2026-11-13 (was 2.5 / L 6.5, below the datasheet maximum)
BODY_R_FLAT = (6.8, 2.6)     # 1/4 W metal film lying flat, L x D max (the same table)
BODY_CER = (5.08, 3.18)      # dipped 5.08 mm MLCC, L x T max (KEMET C320 family, distributor listings, as in the
                             # mixer suite; bom.md names no body): 100 n / 100 p, and the 1 n's ceramic option
BODY_FG28 = (4.0, 2.5)       # TDK FG28 (the footprint's library part): W 4.0 x T 2.5 (x H 5.5), distributor listings
                             # as the mixer suite read them: the size the BOM would have to name
BODY_FILM = (7.2, 2.5)       # 1 n "or film": WIMA FKS2 / MKS2 5 mm pitch, 7.2 x 2.5 x 6.5 (recalled, not confirmed)
BODY_SR30 = (7.62, 3.81)     # 1 uF, AVX SR30: 0.300 x 0.150 in (the footprint's name; not re-confirmed)
BODY_DIP14 = (19.69, 7.11)   # TI N package max: D 0.775 in, E1 0.280 in (mixer suite)
BODY_DIP16 = (19.80, 6.60)   # TI MPDI003, 16 pins: A 0.780 in max, body 0.260 in max
SOCKET_DIP14 = (17.78, 10.16)    # 14-pin socket frame: Mill-Max 110-43-314-41-001000 A .700" x C .400" (verifier
                                 # re-read the Marblesy session's copy)
SOCKET_DIP16 = (20.32, 10.16)    # 16-pin: Mill-Max 110-43-316-41-001000 A .800" x C .400" (20.32 x 10.16, +-0.13);
                                 # Assmann WSW A 16-LC-TT (ASS 0810 CO rev04): A 20.32 +-0.20 x 10.16 +-0.20
BODY_HDR_W = 2.54            # 2.54 mm header / female socket plastic width (2.50-2.54)
# Heights above the board, mm. Verifier 2026-11-13: two named DIP-16 sockets re-read (bom.md names no type:
# "DIP-16 IC socket", Tayda), the writer's 4.5 mm (a Futurlec listing) and 3.5 mm "typical" were not sourced.
SOCKET_STAMPED_H = 5.10      # Assmann WSW A 16-LC-TT (stamped leaf contacts), side view: 5.10 +-0.15 above the board,
SOCKET_STAMPED_TOL = 0.15    #   including its 0.35 +-0.08 standoffs; tail 3.15 +-0.30
SOCKET_TURNED_H = 4.191      # Mill-Max 110-43-316-41-001000 (turned pin): "Above Board Height .165" (4,191mm)",
SOCKET_TURNED_TOL = 0.25     #   assembly tolerance +-.010" (.25); tail length .125" (3.175)
SOCKET_H = SOCKET_STAMPED_H + SOCKET_STAMPED_TOL    # worst: the taller (stamped) socket at its maximum
SOCKET_H_TYP = SOCKET_STAMPED_H                     # typical: a generic stamped socket at its nominal
DIP_A_MAX = 5.33             # PDIP seating plane to top: JEDEC MS-001 A max 0.210" (Intersil / Renesas E14.3, "JEDEC
                             # MS-001-AA ISSUE D": A max .210 / 5.33, A1 min .015 / 0.39, A2 .115-.195 / 2.93-4.95,
                             # E1 .240-.280); TI MPDI003 (16 pin): 0.200" = 5.08 max. Seated in a socket the lead
                             # shoulders (the seating plane) rest on the socket's top
DIP_A_TYP = 4.32             # no nominal A is published: A2's midpoint .155" + A1 min .015" = .170" (verifier; the
                             # writer's 4.06 "drawings' nominal" is not in either drawing)
H_R_FLAT = BODY_R_FLAT[1]    # a flat resistor: its diameter
H_CAP = 7.0                  # a dipped radial ceramic standing, incl. the lead kink (KEMET C320 H 5.6 + kink,
                             # assumed; TDK FG28 5.5)
MALE_PLASTIC = 2.54          # male header plastic: FCI BergStik II 67996 rev DH, 67997 row: total pin 11.43 = tail
                             # 3.05 + mating 5.84 + plastic 2.54 (verifier: was 2.5, not sourced)
FEMALE_BODY = 8.5            # bom.md: "Female header, 2.54 mm, 8.5 mm tall" (no datasheet read)
LEAD_PROTRUDE = 2.0          # a clipped lead + its fillet out of the far side of a 1.6 mm board: 1.5-2 mm
                             # (brief's assumption; the larger used; IPC-A-610 class 2 allows up to 2.5)
LEAD_PROTRUDE_TYP = 1.5
# Tails that are not clipped (socket and header contacts), out of the 1.6 mm board: the DIP sockets' tails
# (Assmann 3.15 +-0.30, Mill-Max 3.175) and the 8.5 mm female headers' tails (no datasheet read: 3.0 typical,
# 3.5 max assumed). Over U10 the main board's female headers for the breakout (U2 row x 17.6) stick out.
SOCKET_TAIL_MAX, SOCKET_TAIL_TYP = 3.45, 3.15
FEMALE_TAIL_MAX, FEMALE_TAIL_TYP = 3.5, 3.0
# M3 hardware round the mounting holes
M3_HEAD_R = 5.6 / 2          # ISO 7045 pan head M3: dk max 5.6 (bom.md: "M3 x 6 mm pan-head screw"); recalled
M3_STANDOFF_R = 6.35 / 2     # M3 hex standoff 5.5 mm across flats -> 6.35 across the corners (5.5 / cos 30)
HOLE_D = 3.2                 # M3 clearance hole (design.md)

BOARD_W, BOARD_H = circuit.BOARD_W, circuit.BOARD_H
POWER_NETS = ("+12V", "-12V", "3V3A", "3V3D", "3V3A_F", "3V3D_F", "GND_D_F")     # design.md: the 0.6 mm class
POWER_W, SIGNAL_W, CLEARANCE = 0.6, 0.3, 0.152                                    # design.md's rules

# ====================================================================== raw footprint data
FP = {}            # footprint title -> {pad num: dict(x, y, shape, w, h, hole, hw, hh, plated)}
for title, d in R.fp_docs.items():
    pads = {}
    for h, p in d["recs"]:
        if h["type"] == "PAD" and p:
            dp, ho = p["defaultPad"], p.get("hole") or {}
            pads[str(p["num"])] = {"x": p["centerX"] * MIL, "y": p["centerY"] * MIL, "shape": dp["padType"],
                                   "w": dp["width"] * MIL, "h": dp["height"] * MIL, "hole": ho.get("holeType"),
                                   "hw": ho.get("width", 0) * MIL, "hh": ho.get("height", 0) * MIL,
                                   "plated": p.get("plated"), "angle": p.get("padAngle") or 0}
    FP[title] = pads
USED = collections.defaultdict(list)
for b in (MB, FB):
    for ref, pl in b.parts.items():
        USED[pl["fp"]].append((b.title, ref))
BOARDS = (("main", MB), ("face", FB))


def name_of(b):
    return "main" if b is MB else "face"


def front(x):
    return BOARD_W - x


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def fp_silk(title, layers=(3,)):
    """Silk primitives of a footprint: [(type, points, raw path)]."""
    out = []
    for h, p in R.fp_docs[title]["recs"]:
        if h["type"] in ("POLY", "FILL") and p and p.get("layerId") in layers:
            path = p["path"]
            pts = []
            for pa in (path if path and isinstance(path[0], list) else [path]):
                if pa and pa[0] == "CIRCLE":
                    pts.append((pa[1] * MIL, pa[2] * MIL))
                elif pa and pa[0] == "R":
                    x, y, w, hh = pa[1:5]
                    pts += [(x * MIL, y * MIL), ((x + w) * MIL, (y - hh) * MIL)]
                else:
                    try:
                        pts += ca.flatten_path(pa, MIL)
                    except (ValueError, TypeError, IndexError):
                        pass
            out.append((h["type"], pts, path))
    return out


# ====================================================================== A. footprints
def dip_geometry(title, n):
    p = FP[title]
    xy = {i: (p[str(i)]["x"], p[str(i)]["y"]) for i in range(1, n + 1)}
    half = n // 2
    pitch = [dist(xy[i], xy[i + 1]) for i in list(range(1, half)) + list(range(half + 1, n))]
    across = [dist(xy[i], xy[n + 1 - i]) for i in range(1, half + 1)]
    ck.check(f"A.dip_pitch.{title}: 2.54 mm between pins", all(abs(v - 2.54) < 0.01 for v in pitch),
             f"expected 2.54, got {sorted({round(v, 3) for v in pitch})}")
    ck.check(f"A.dip_rows.{title}: rows 7.62 mm apart (a 0.300 in socket)", all(abs(v - 7.62) < 0.01 for v in across),
             f"expected 7.62, got {sorted({round(v, 3) for v in across})}")
    # counter-clockwise seen from the component side: pins 1..n/2 left to right on one row, back on the other
    r1 = {round(xy[i][1], 2) for i in range(1, half + 1)}
    r2 = {round(xy[i][1], 2) for i in range(half + 1, n + 1)}
    ccw = len(r1) == 1 and len(r2) == 1 and min(r1) < min(r2) and xy[half][0] > xy[1][0] and xy[n][0] < xy[half + 1][0]
    ck.check(f"A.dip_numbering.{title}: pins counted anticlockwise from the component side (pin 1 bottom-left)", ccw,
             f"row y of pins 1..{half}: {r1}, of the rest: {r2}")
    hole = {round(p[str(i)]["hw"], 3) for i in range(1, n + 1)}
    sq = [i for i in range(1, n + 1) if p[str(i)]["shape"] == "RECT"]
    dots = [pts for t, pts, raw in fp_silk(title) if pts and (raw and raw[0] == "CIRCLE" or t == "FILL")]
    mark = any(dist(pts[0], xy[1]) < dist(pts[0], xy[n]) and dist(pts[0], xy[1]) < dist(pts[0], xy[half]) for pts in dots)
    ck.check(f"A.dip_pin1.{title}: pin 1 marked, a square pad or a silk dot nearest pin 1 (the socket / chip "
             f"orientation cue)", sq == [1] or mark,
             f"square pads {sq}, silk dot nearest pin 1: {mark}; holes {hole}")
    return sq == [1], mark


sq14, dot14 = dip_geometry("DIP-14-W7.62-P2.54", 14)
sq16, dot16 = dip_geometry("DIP-16_L20.0-W6.4-P2.54-LS7.6-BL", 16)
ck.check("A.dip_pin1_pad.DIP-16: pin 1 a square pad like every other footprint on the boards (DIP-14, headers, "
         "pots, LEDs)", sq16, f"DIP-16 pad shapes {sorted({FP['DIP-16_L20.0-W6.4-P2.54-LS7.6-BL'][str(i)]['shape'] for i in range(1, 17)})}"
         f" (library footprint); silk dot at pin 1: {dot16}")
ck.check("A.dip_users: TL074s on the 7.62 mm DIP-14, the 4051 / 595s on a 7.62 mm DIP-16",
         sorted(r for t, r in USED["DIP-14-W7.62-P2.54"]) == ["U3", "U4"]
         and sorted(r for t, r in USED["DIP-16_L20.0-W6.4-P2.54-LS7.6-BL"]) == ["U1", "U10", "U9"],
         f"DIP-14 {USED['DIP-14-W7.62-P2.54']}, DIP-16 {USED['DIP-16_L20.0-W6.4-P2.54-LS7.6-BL']}")
bad = []
for b in (MB, FB):
    for ref, pl in b.parts.items():
        if pl["fp"].startswith("DIP-"):
            n = len(pl["pads"])
            d = dist((pl["pads"]["1"].x, pl["pads"]["1"].y), (pl["pads"][str(n)].x, pl["pads"][str(n)].y))
            if abs(d - 7.62) > 0.01 or pl["bottom"]:
                bad.append(f"{ref} {d:.3f}{' bottom' if pl['bottom'] else ''}")
ck.check("A.dip_placed: every DIP on its board's top (rear) side, pin 1 to pin n 7.62 mm", not bad, f"{bad}")

for title, n in (("HDR-1x8-P2.54", 8), ("HDR-1x9-P2.54", 9)):
    p = FP[title]
    gaps = [dist((p[str(i)]["x"], p[str(i)]["y"]), (p[str(i + 1)]["x"], p[str(i + 1)]["y"])) for i in range(1, n)]
    line = len({round(p[str(i)]["y"], 3) for i in range(1, n + 1)}) == 1
    ck.check(f"A.header.{title}: {n} pins at 2.54 mm in a line, pin 1 square", all(abs(g - 2.54) < 0.01 for g in gaps)
             and line and p["1"]["shape"] == "RECT" and all(p[str(i)]["shape"] != "RECT" for i in range(2, n + 1)),
             f"gaps {sorted({round(g, 3) for g in gaps})}, in line {line}, pin 1 {p['1']['shape']}")
hdr = []
for ref, kind, pins in circuit.HEADERS:
    a, m = FB.parts[circuit.fb_ref(ref)], MB.parts[ref]
    for num in a["pads"]:
        if dist((a["pads"][num].x, a["pads"][num].y), (m["pads"][num].x, m["pads"][num].y)) > 0.01:
            hdr.append(f"{ref}.{num}")
    if a["bottom"] or not m["bottom"]:
        hdr.append(f"{ref}: male on the {'bottom' if a['bottom'] else 'top'}, female on the {'bottom' if m['bottom'] else 'top'}")
ck.check("A.header_stack: every male pin (FB top) over its female socket contact (MB bottom), pin numbers matching",
         not hdr, f"{hdr}")

# Thonkiconn: lugs at Thonk's distances from the barrel
p = FP["CONN-TH_WQP-WQP518MA"]
barrel_y = p["1"]["y"] + THONK_SLEEVE * (1 if p["3"]["y"] > p["1"]["y"] else -1)
got = (abs(p["1"]["y"] - barrel_y), abs(p["2"]["y"] - barrel_y), abs(p["3"]["y"] - barrel_y))
same = (p["2"]["y"] - barrel_y) * (p["1"]["y"] - barrel_y) > 0 and (p["3"]["y"] - barrel_y) * (p["1"]["y"] - barrel_y) < 0
inline = all(abs(p[k]["x"]) < 0.01 for k in "123")
ck.check("A.jack_lugs: WQP518MA sleeve / switch / tip lugs in a line at 6.48 / 3.38 / 4.92 mm from the barrel "
         "(Thonk PJ398SM), switch on the sleeve side", same and inline and all(abs(g - w) < 0.02 for g, w in
                                                                                zip(got, (THONK_SLEEVE, THONK_SWITCH, THONK_TIP))),
         f"expected (6.48, 3.38, 4.92), got ({got[0]:.2f}, {got[1]:.2f}, {got[2]:.2f}); barrel at footprint y {barrel_y:.2f}")
ck.close("A.jack_barrel_offset: barrel 0.78 mm from the WQP518MA origin (circuit.JACK_BARREL)", abs(barrel_y),
         abs(circuit.JACK_BARREL), 0.02, " mm")

# Alpha RD901F
p = FP["POT-ALPHA-9MM-RD901F"]
pins = [(p[k]["x"], p[k]["y"]) for k in "123"]
lugs = [(p[k]["x"], p[k]["y"]) for k in "45"]
shaft = ((lugs[0][0] + lugs[1][0]) / 2, (lugs[0][1] + lugs[1][1]) / 2)
ck.check("A.pot_pitch: Alpha RD901F pins 2.5 mm apart in a row", abs(dist(pins[0], pins[1]) - ALPHA_PITCH) < 0.01
         and abs(dist(pins[1], pins[2]) - ALPHA_PITCH) < 0.01 and abs(pins[0][1] - pins[2][1]) < 0.01,
         f"{pins}")
ck.check("A.pot_lugs: mounting lugs on the shaft line at +-4.8 mm, the shaft 7.5 mm from the pin row, centred on pin 2",
         abs(lugs[0][1] - lugs[1][1]) < 0.01 and abs(abs(lugs[0][0] - shaft[0]) - ALPHA_LUG_X) < 0.01
         and abs(shaft[1] - pins[1][1] - ALPHA_SHAFT) < 0.01 and abs(shaft[0] - pins[1][0]) < 0.01,
         f"lugs {lugs}, shaft {shaft}, pin 2 {pins[1]}")
ck.close("A.pot_shaft_offset: shaft 4.0 mm from the footprint origin (circuit.POT_SHAFT)", math.hypot(*shaft),
         circuit.POT_SHAFT, 0.02, " mm")

# LED-3MM-3P
p = FP["LED-3MM-3P"]
gaps = [dist((p[str(i)]["x"], p[str(i)]["y"]), (p[str(i + 1)]["x"], p[str(i + 1)]["y"])) for i in (1, 2)]
ck.check("A.led_pitch: LED-3MM-3P takes a real 3-lead 3 mm bicolour LED: leads 2.54 mm apart, cathode (pad 2) in the "
         "middle, holes >= the 0.889 the maker recommends (Kingbright L-3WEGW DSAA6458)",
         all(abs(g - LED_PITCH) < 0.01 for g in gaps) and abs(p["2"]["x"]) < 0.01
         and all(p[k]["hw"] >= LED_HOLE_REC - 1e-3 for k in "123"),
         f"footprint pads {[round(g, 3) for g in gaps]} mm apart, holes {sorted({round(p[k]['hw'], 3) for k in '123'})}; "
         f"Kingbright: leads kinked out to {LED_PITCH} pitch, holes {LED_HOLE_REC}")
ck.within(f"A.led_gap: pad-to-pad gap of the LED's {p['1']['w']:.2f} mm wide pads at its lead pitch (design rule 0.152, "
          "JLCPCB 0.10)", min(gaps) - p["1"]["w"], CLEARANCE, None, " mm",
          f"pads {p['1']['w']:.2f} x {p['1']['h']:.2f}")      # [2026-11-14: sizes read from the footprint since M2]

# DO-35
p = FP["DO-35_BD2.0-L4.0-P8.0-D0.5-RD"]
pitch = dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"]))
need = BODY_DO35[0] + 2 * (LEAD_BEND_MIN + LEADS["DO-35_BD2.0-L4.0-P8.0-D0.5-RD"]["*"][1])
ck.within("A.do35_pitch: DO-35 pitch takes the BAT85's longest body plus a bend 1 mm off each end (+ lead dia)",
          pitch, need, None, " mm", f"body {BODY_DO35[0]} + 2 x (1.0 + 0.56)")
# standing resistor: pad 1 under the body, pad 2 one pitch away
p = FP["RES-TH-VERTICAL-P2.54"]
ck.close("A.res_vertical_pitch: RES-TH-VERTICAL-P2.54 pads 2.54 mm apart", dist((p["1"]["x"], p["1"]["y"]),
                                                                                  (p["2"]["x"], p["2"]["y"])), 2.54, 0.01, " mm")
ck.within("A.res_vertical_body: the standing body (D 2.5 max) over pad 1 leaves pad 2's lead room (pad pitch - body "
          "radius - pad 2's radius)", dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"])) - BODY_R_STAND_D / 2
          - p["2"]["w"] / 2, 0.0, None, " mm", "the bent lead goes down beside the body into pad 2")
for title in ("RES-TH_L6.2-W2.3-LR1F1K0", "RES-TH_BD2.3-L6.3-P10.30-D0.6"):
    p = FP[title]
    pitch = dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"]))
    ck.within(f"A.res_flat_pitch.{title}: 10.3 mm pitch takes a 1/4 W body (L {BODY_R_FLAT[0]} max) + a 1 mm bend "
              "each end", pitch, BODY_R_FLAT[0] + 2 * (LEAD_BEND_MIN + 0.6), None, " mm")
for title, body in (("CAP-TH_L3.0-W2.0-P5.08-D0.7", BODY_CER), ("CAP-TH_L7.6-W3.8-P5.08-D0.51", BODY_SR30)):
    p = FP[title]
    ck.close(f"A.cap_pitch.{title}: 5.08 mm lead spacing (bom.md '5.08 mm leads')",
             dist((p["1"]["x"], p["1"]["y"]), (p["2"]["x"], p["2"]["y"])), 5.08, 0.01, " mm")

# Thonk LED button
p = FP["SW-TACT-LP-LED-THONK"]
sw = [(p[k]["x"], p[k]["y"]) for k in "1234"]
ok = all(abs(abs(x) - BTN_SQ / 2) < 0.01 and abs(abs(y) - BTN_SQ / 2) < 0.01 for x, y in sw) and \
    abs(abs(p["5"]["x"]) - BTN_LED_X) < 0.01 and abs(p["5"]["y"]) < 0.01 and abs(p["6"]["x"] + p["5"]["x"]) < 0.01
ck.check("A.button_pins: Thonk LED button pins 1-4 on a 5.08 mm square, LED 5 / 6 at x +-2.7 (parts.md, Thonk's KiCad "
         "footprint; no Thonk drawing: not confirmed)", ok, f"switch {sw}, LED {p['5']['x']:.2f} / {p['6']['x']:.2f}")
# contacts 1+2 and 3+4 (parts.md): 1 and 2 share a y (top pair), 3 and 4 the other
ck.check("A.button_contacts: pins 1+2 one contact, 3+4 the other (parts.md), and circuit.py ties 1+2 to GND_D_F, "
         "3+4 to the switch net", abs(p["1"]["y"] - p["2"]["y"]) < 0.01 and abs(p["3"]["y"] - p["4"]["y"]) < 0.01
         and all(FB.parts[r]["nets"].get("1") == FB.parts[r]["nets"].get("2") == "GND_D_F" and
                 FB.parts[r]["nets"].get("3") == FB.parts[r]["nets"].get("4") != "GND_D_F" for r in ("SW1", "SW2")),
         f"SW1 nets {FB.parts['SW1']['nets']}")

# ====================================================================== B. the breakout's pins
fp = FP["DAISY-SEED-POWER-OPAMPS-2.54"]
brk = []           # (x, y, drill, kind)
for k in range(20):
    for y in (BRK_ROW_A, BRK_ROW_B):
        brk.append((BRK_SEED_X0 + 2.54 * k, y, BRK_SEED_D, "seed"))
for x in BRK_HDR_X:
    for y in (BRK_ROW_A, BRK_ROW_B):
        brk.append((x, y, BRK_HDR_D, "hdr"))
cx = (BRK_SEED_X0 + BRK_SEED_X0 + 19 * 2.54) / 2
cy = (BRK_ROW_A + BRK_ROW_B) / 2


def brk_to_fp(x, y):
    """A breakout drill (Gerber top view) in the footprint's frame: centred on the Seed's pin field, mirrored when the
    breakout sits Gerber-bottom up."""
    return x - cx, (-(y - cy) if BRK_MIRRORED else (y - cy))


fp_xy = {n: (q["x"], q["y"]) for n, q in fp.items()}
unmatched, matched = [], {}
for x, y, d, kind in brk:
    u = brk_to_fp(x, y)
    n = min(fp_xy, key=lambda k: dist(fp_xy[k], u))
    if dist(fp_xy[n], u) > 0.01:
        unmatched.append(f"breakout ({x:.2f}, {y:.3f}) -> ({u[0]:.2f}, {u[1]:.2f}), nearest pad {n} {dist(fp_xy[n], u):.2f} mm")
    else:
        matched[n] = (x, y, kind)
ck.check(f"B.breakout_pins: all {len(brk)} of the breakout's Seed / 1x4 header holes (its Excellon file, mirrored: it "
         "mounts SMD side down) land on a footprint pad within 0.01 mm", not unmatched, f"{len(unmatched)} off: {unmatched[:4]}")
ck.check("B.breakout_no_extra: the footprint has no pad the breakout has no pin for", sorted(set(fp) - set(matched)) == [],
         f"extra pads {sorted(set(fp) - set(matched))}")
rows = sorted({round(q["y"], 3) for q in fp.values()})
ck.check("B.breakout_rows: two rows 15.24 mm apart (Daisy Seed landing pattern), 2.54 mm pitch along each",
         len(rows) == 2 and abs(rows[1] - rows[0] - SEED_ROWS) < 0.01 and
         all(abs(abs(fp_xy[str(k)][0] - fp_xy[str(k + 1)][0]) - SEED_PITCH) < 0.01 for k in range(1, 20)),
         f"rows {rows}")
# the opposite orientation would also put every hole on a pad (the pattern is symmetric about its centre line) but
# swap the rows: the nets decide
U2 = MB.parts["U2"]


def fp_net_at(bx, by):
    u = brk_to_fp(bx, by)
    n = min(fp_xy, key=lambda k: dist(fp_xy[k], u))
    return n, U2["nets"].get(n)


gnd_bad = [f"{fp_net_at(*q)[0]}={fp_net_at(*q)[1]}" for q in BRK_GND if fp_net_at(*q)[1] != "GND"]
ck.check("B.breakout_gnd: every pin the breakout has on its GND (Seed 20 / 40, the headers' ground pins) is GND on "
         "Plaitsy's U2", not gnd_bad, f"not GND: {gnd_bad}")
neg = [fp_net_at(*q) for q in BRK_NEG12]
pos = [fp_net_at(*q) for q in BRK_POS12]
ck.check("B.breakout_neg12: the breakout's -12 V header pins (behind its -12 V Schottky) on Plaitsy's -12V (J1-2..4)",
         all(n == "-12V" for _, n in neg), f"{neg}")
ck.check("B.breakout_pos12: the breakout's +12 V header pins on Plaitsy's +12V (J3-2..4)", all(n == "+12V" for _, n in pos),
         f"{pos}")
vin = fp_net_at(*BRK_VIN)
ck.check("B.breakout_vin: the breakout's DC/DC output (Seed VIN, pin 39) is the footprint's pin 39 and Plaitsy leaves it "
         "unconnected", vin[0] == "39" and vin[1] is None, f"lands on pad {vin[0]}, net {vin[1]}")
sqp = []
for q in BRK_SQUARE:
    n, _ = fp_net_at(*q)
    sqp.append((n, fp[n]["shape"]))
ck.check("B.breakout_pin1: the breakout's square pads (its 1x4 headers' pin 1) are square on the footprint too",
         all(s == "RECT" for n, s in sqp), f"{sqp}")
# the breakout's outline as the footprint draws it
geo = next(g for g in R.fp_geo.values() if g["title"] == "DAISY-SEED-POWER-OPAMPS-2.54")
o = [brk_to_fp(BRK_OUTLINE[0], BRK_OUTLINE[1]), brk_to_fp(BRK_OUTLINE[2], BRK_OUTLINE[3])]
want = (min(o[0][0], o[1][0]), min(o[0][1], o[1][1]), max(o[0][0], o[1][0]), max(o[0][1], o[1][1]))
ck.check("B.breakout_outline: the footprint's drawn body is the breakout's 96.75 x 18.80 mm outline (0.1 mm)",
         all(abs(a - b) < 0.1 for a, b in zip(geo["bbox"], want)),
         f"drawn {tuple(round(v, 2) for v in geo['bbox'])}, breakout {tuple(round(v, 2) for v in want)}")
x1, y1, x2, y2 = U2["body"]
# verifier 2026-11-13: against the pin maker's recommended hole (FCI BergStik II 67996: 1.02 +-0.08), not the
# 0.64 nominal diagonal
ck.check("B.breakout_header_holes: the breakout's own 1x4 / 2x5 header holes (0.889 mm) within the recommended hole for "
         "a 0.64 mm square post (FCI BergStik II 67996: 1.02 +-0.08)",
         POST_HOLE - POST_HOLE_TOL - 1e-6 <= BRK_HDR_D <= POST_HOLE + POST_HOLE_TOL,
         f"drill {BRK_HDR_D}, recommended {POST_HOLE - POST_HOLE_TOL:.2f}-{POST_HOLE + POST_HOLE_TOL:.2f}; post diagonal "
         f"{math.hypot(*SQ_POST[1:3]):.3f} nominal, {math.hypot(0.67, 0.67):.3f} max (Rob Heel's build photo shows "
         "the headers fitted: a tight fit, not a blocker)")
docs = harness.text("docs", "design.md") + harness.text("docs", "bom.md") + harness.text("README.md")
said = re.findall(r"[^.\n]*(?:SMD side|op-amp side|stacking header|long-tail|long tail|upside down|Seed side)[^.\n]*", docs, re.I)
ck.check("B.breakout_orientation_doc: design.md / bom.md / README tell the builder which side of the breakout faces the main "
         "board (SMD side down, Seed up) and how the Seed's 40 pins reach the sockets (long-tail female headers); its own "
         "silk puts the 1x4 headers on the Seed side, and the other way up every pin lands on its mirror (+12 V on -12 V)",
         bool(said), f"found: {said[:3]}; bom.md only says 'male pins under the breakout'. Rob Heel's build photo "
         "(seed_breadboard_01.jpg) shows the stack that works: 1x4 male headers fitted from the SMD side, plastic under "
         "the board, long-tail female headers for the Seed whose tails end level with the male pins' tips (so they reach "
         f"~5.8 mm into Plaitsy's 8.5 mm sockets); gap {FEMALE_BODY} + {MALE_PLASTIC} mm")
seed_pts = [q for t, pts, raw in fp_silk("DAISY-SEED-POWER-OPAMPS-2.54") for q in pts]
sx = sorted({round(abs(q[0]), 2) for q in seed_pts})
sy = sorted({round(abs(q[1]), 2) for q in seed_pts})
ck.check("B.seed_outline: the footprint draws the Seed as 51 x 18 mm (Seed datasheet technical drawing) round its pin field",
         25.5 in sx and 9.0 in sy, f"|x| {sx}, |y| {sy}")
ck.check("B.breakout_on_board: the breakout's outline inside the main board", x1 >= 0 and y1 >= 0 and x2 <= BOARD_W
         and y2 <= BOARD_H, f"({x1:.2f}, {y1:.2f})-({x2:.2f}, {y2:.2f})")

# ====================================================================== C. drills, rings, slots, vias
fit_bad, loose, ring_min_bad, ring_rec_bad, slot_bad, small_hole = [], [], [], [], [], []
for title, pads in sorted(FP.items()):
    if title not in USED:
        continue
    leads = LEADS.get(title, {})
    for num, pd in sorted(pads.items()):
        if not pd["hole"]:
            continue
        L, Wd = max(pd["hw"], pd["hh"]), min(pd["hw"], pd["hh"])
        if pd["hole"] == "ROUND":
            ring = (min(pd["w"], pd["h"]) - pd["hw"]) / 2
        else:
            ring = min((max(pd["w"], pd["h"]) - L) / 2, (min(pd["w"], pd["h"]) - Wd) / 2)
            if Wd < JLC_PSLOT_MIN - 1e-6:
                slot_bad.append(f"{title}.{num} slot {L:.2f} x {Wd:.2f}")
        if Wd < JLC_PTH_REC - 1e-6:
            small_hole.append(f"{title}.{num} {Wd:.2f}")
        if ring < JLC_RING_MIN - 1e-3:
            ring_min_bad.append(f"{title}.{num} {ring:.3f}")
        elif ring < JLC_RING_REC - 1e-3:
            ring_rec_bad.append(f"{title}.{num} {ring:.3f}")
        lead = leads.get(num, leads.get("*"))
        if lead is None:
            fit_bad.append(f"{title}.{num}: no lead size in the constants")
            continue
        shape, lw, lt = lead[:3]
        lmin = lead[3] if len(lead) > 3 else min(lw, lt)
        if title in POST_FPS and pd["hole"] == "ROUND":
            # header posts / socket tails: the maker's recommended hole (FCI BergStik II 1.02 +-0.08)
            if not (POST_HOLE - POST_HOLE_TOL - 1e-6 <= pd["hw"] <= POST_HOLE + POST_HOLE_TOL + 1e-6):
                fit_bad.append(f"{title}.{num}: drill {pd['hw']:.2f} outside the post's recommended "
                               f"{POST_HOLE - POST_HOLE_TOL:.2f}-{POST_HOLE + POST_HOLE_TOL:.2f}")
            continue
        if pd["hole"] == "ROUND":
            diag = lw if shape == "round" else math.hypot(lw, lt)
            margin = pd["hw"] - diag
            insert = pd["hw"] - JLC_TOL_MINUS - diag
            if (shape == "round" and margin < IPC_FIT_MIN - 1e-6) or insert < (INSERT_MIN if shape == "round" else 0):
                fit_bad.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {diag:.2f} lead (nominal clearance "
                               f"{margin:.2f}, smallest finished hole {pd['hw'] - JLC_TOL_MINUS:.2f})")
            if shape == "round" and pd["hw"] - lmin > IPC_FIT_MAX + 1e-6:
                loose.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {lmin:.2f} lead")
        else:
            if L - JLC_TOL_MINUS - lw < INSERT_MIN or Wd - JLC_TOL_MINUS - lt < INSERT_MIN:
                fit_bad.append(f"{title}.{num}: slot {L:.2f} x {Wd:.2f} for a {lw:.2f} x {lt:.2f} lug (smallest "
                               f"finished {L - JLC_TOL_MINUS:.2f} x {Wd - JLC_TOL_MINUS:.2f})")
tight = []
for title, pads in sorted(FP.items()):
    if title in USED and title in LEADS:
        for num, pd in sorted(pads.items()):
            lead = LEADS[title].get(num, LEADS[title].get("*"))
            if pd["hole"] == "ROUND" and lead:
                diag = lead[1] if lead[0] == "round" else math.hypot(lead[1], lead[2])
                tight.append((round(pd["hw"] - JLC_TOL_MINUS - diag, 3), title, num, round(pd["hw"], 3), round(diag, 3)))
tight = sorted(set((a, t, round(h, 2), d) for a, t, n, h, d in tight))
print(f"      tightest round fits (smallest finished hole - lead diagonal, footprint, drill, lead): {tight[:6]}")
ck.check("C.lead_fit: every lead fits its hole (round: IPC-2222 level C 0.15 on the drill and 0.05 at the fab's -0.08; "
         "square / flat: the diagonal through the smallest finished hole; header posts: the maker's recommended hole; "
         "slots: 0.05 each way)", not fit_bad,
         f"{len(fit_bad)} tight: {fit_bad}")
ck.check("C.lead_loose: no round hole more than 0.70 mm over its thinnest lead (IPC-2222 level A maximum)", not loose,
         f"{loose}")
ck.check(f"C.ring_min: annular rings >= JLCPCB's absolute minimum {JLC_RING_MIN} mm", not ring_min_bad, f"{ring_min_bad}")
ck.check(f"C.ring_rec: annular rings >= JLCPCB's recommended {JLC_RING_REC} mm", not ring_rec_bad, f"{ring_rec_bad}")
ck.check(f"C.slot_width: plated slots >= JLCPCB's {JLC_PSLOT_MIN} mm", not slot_bad, f"{slot_bad}")
ck.check(f"C.pth_size: every pad hole >= JLCPCB's recommended {JLC_PTH_REC} mm (and its {JLC_PTH_MIN} minimum)",
         not small_hole, f"{small_hole}")
slots = sorted({(t, n, round(min(q['hw'], q['hh']), 2)) for t, ps in FP.items() if t in USED for n, q in ps.items()
                if q["hole"] == "SLOT"})
print(f"      plated slots in use (footprint, pad, width): {slots}")
VIAS = {}
for k, b in BOARDS:
    VIAS[k] = [{"c": (p["centerX"] * MIL, p["centerY"] * MIL), "drill": p["holeDiameter"] * MIL,
                "d": p["viaDiameter"] * MIL, "net": p["netName"]} for h, p in R.pcb_docs[k]["recs"] if h["type"] == "VIA" and p]
    vd = sorted({(round(v["drill"], 3), round(v["d"], 3)) for v in VIAS[k]})
    ck.check(f"C.vias.{k}: via drill >= {JLC_VIA_DRILL_MIN}, diameter >= {JLC_VIA_DIA_MIN} (JLCPCB 2-layer), "
             f"0.61 / 0.3 as design.md's rule", all(d >= JLC_VIA_DRILL_MIN and D >= JLC_VIA_DIA_MIN and D - d >= 0.2
                                                    for d, D in vd) and len(VIAS[k]) == len(b.vias),
             f"{len(VIAS[k])} vias, (drill, diameter) {vd}")

# hole-to-hole and drill-to-track per board
DRILLS = {}
for k, b in BOARDS:
    drills = []
    for pad in b.pads:
        raw = FP[b.parts[pad.ref]["fp"]][pad.num]
        if raw["hole"]:
            drills.append({"c": (pad.x, pad.y), "r": min(raw["hw"], raw["hh"]) / 2, "R": max(raw["hw"], raw["hh"]) / 2,
                           "kind": "pad", "label": f"{pad.ref}.{pad.num}", "net": pad.net, "raw": raw, "pad": pad})
    for v in VIAS[k]:
        drills.append({"c": v["c"], "r": v["drill"] / 2, "R": v["drill"] / 2, "kind": "via",
                       "label": f"via {v['net']} ({v['c'][0]:.1f}, {v['c'][1]:.1f})", "net": v["net"], "raw": None, "pad": None})
    DRILLS[k] = drills
    worst = []
    for i in range(len(drills)):
        a = drills[i]
        for c in drills[i + 1:]:
            if a["kind"] == c["kind"] == "pad" and a["label"].split(".")[0] == c["label"].split(".")[0]:
                continue                     # one part's own pins: its footprint's spacing
            dd = dist(a["c"], c["c"])
            if dd > 6:
                continue
            gap = dd - a["R"] - c["R"]
            same = a["net"] == c["net"] and a["net"]
            need = JLC_HOLE_HOLE_VIA if "via" in (a["kind"], c["kind"]) else JLC_HOLE_HOLE_PAD
            if gap < need and not (same and gap >= JLC_HOLE_HOLE_VIA):
                worst.append((round(gap, 3), a["label"], c["label"]))
    worst.sort()
    ck.check(f"C.hole_to_hole.{k}: >= {JLC_HOLE_HOLE_PAD} mm between pad holes of different nets, {JLC_HOLE_HOLE_VIA} "
             "where a via is involved (JLCPCB)", not worst, f"{len(worst)} under: {worst[:8]}")
    near, near_rec = [], []
    for dr in drills:
        x, y = dr["c"]
        for t in b.tracks:
            if t["net"] == dr["net"]:
                continue
            if min(t["a"][0], t["b"][0]) > x + dr["R"] + 1.5 or max(t["a"][0], t["b"][0]) < x - dr["R"] - 1.5 or \
                    min(t["a"][1], t["b"][1]) > y + dr["R"] + 1.5 or max(t["a"][1], t["b"][1]) < y - dr["R"] - 1.5:
                continue
            if dr["raw"] is not None and dr["raw"]["hole"] != "ROUND":
                s0, s1, rr = ca.Pad("", "", x, y, dr["raw"]["hw"], dr["raw"]["hh"], "ELLIPSE", dr["pad"].angle, None).axis()
                g = ca.d_seg_seg(s0, s1, t["a"], t["b"]) - rr - t["w"] / 2
            else:
                g = ca.d_point_seg((x, y), t["a"], t["b"]) - t["w"] / 2 - dr["r"]
            if dr["kind"] == "via":          # JLCPCB's own via row: 0.2 mm, no "recommended" figure
                if g < JLC_VIA_TRACK:
                    near.append((round(g, 3), dr["label"], t["net"]))
            elif g < JLC_PTH_TRACK:
                near.append((round(g, 3), dr["label"], t["net"]))
            elif g < JLC_PTH_TRACK_REC:
                near_rec.append((round(g, 3), dr["label"], t["net"]))
    near.sort()
    near_rec.sort()
    ck.check(f"C.drill_to_track.{k}: drill edge to another net's track >= JLCPCB's {JLC_PTH_TRACK} mm (pad holes), "
             f"{JLC_VIA_TRACK} mm (vias)", not near, f"{len(near)} under: {near[:8]}")
    ck.check(f"C.drill_to_track_rec.{k}: pad-hole edge to another net's track >= JLCPCB's recommended {JLC_PTH_TRACK_REC} mm",
             not near_rec, f"{len(near_rec)} between {JLC_PTH_TRACK} and {JLC_PTH_TRACK_REC}: {near_rec[:8]}")

# the panel board: NPTH holes and slots
PANEL_HOLES, PANEL_SLOTS = [], []
for h, p in R.panel["recs"]:
    if h["type"] == "FILL" and p and p["layerId"] == 12:
        path = p["path"][0] if isinstance(p["path"][0], list) else p["path"]
        if path[0] == "CIRCLE":
            PANEL_HOLES.append((path[1] * MIL, path[2] * MIL, 2 * path[3] * MIL))
        else:
            pts = ca.flatten_path(path, MIL)
            PANEL_SLOTS.append((pts, p.get("width", 0) * MIL))
panel_outline = next(p["path"] for h, p in R.panel["recs"] if h["type"] == "POLY" and p and p.get("polyType") == "BOARD_OUTLINE")
PW, PH = panel_outline[3] * MIL, panel_outline[2] * MIL
ck.check(f"C.panel_npth: every panel hole >= JLCPCB's {JLC_NPTH_MIN} mm NPTH minimum", all(d >= JLC_NPTH_MIN for *_, d in PANEL_HOLES),
         f"{len(PANEL_HOLES)} holes, sizes {sorted({round(d, 2) for *_, d in PANEL_HOLES})}")
sl = []
for pts, w in PANEL_SLOTS:            # a FILL region: its outline is the slot (the stroke is EasyEDA's hairline)
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    a, c = max(xs) - min(xs), max(ys) - min(ys)
    sl.append((round(max(a, c), 2), round(min(a, c), 2)))
ck.check(f"C.panel_slots: four mounting slots 5.5 x 3.2 mm (design.md), width >= JLCPCB's {JLC_NPSLOT_MIN} mm non-plated "
         "slot minimum", len(sl) == 4 and all(abs(a - 5.5) < 0.05 and abs(c - 3.2) < 0.05 and c >= JLC_NPSLOT_MIN for a, c in sl),
         f"slots (length, width) {sl}")
pe = []
for x, y, d in PANEL_HOLES:
    pe.append(min(x, y, PW - x, PH - y) - d / 2)
for pts, w in PANEL_SLOTS:
    for x, y in pts:
        pe.append(min(x, y, PW - x, PH - y) - w / 2)
ck.within("C.panel_hole_edge: panel holes / slots to the panel edge (no JLCPCB rule; 1 mm the castellation figure)",
          min(pe), 1.0, None, " mm")

# ====================================================================== D. outlines, mounting holes, hardware
want_holes = sorted((round(front(xf), 2), round(y, 2)) for xf, y in pcbmod.HOLES_FRONT)
for k, b in BOARDS:
    x1, y1, x2, y2 = b.outline
    ck.check(f"D.outline.{k}: 59.4 x 108.0 mm at the origin", abs(x2 - x1 - BOARD_W) < 0.01 and abs(y2 - y1 - BOARD_H) < 0.01
             and abs(x1) < 0.01 and abs(y1) < 0.01, f"({x1:.2f}, {y1:.2f})-({x2:.2f}, {y2:.2f})")
    got = sorted((round(hx, 2), round(hy, 2)) for hx, hy, hd in b.holes)
    ck.check(f"D.holes.{k}: three 3.2 mm holes at pcb.HOLES_FRONT (front (3.5, 104.5), (55.9, 104.5), (3.5, 30)), 0.05 mm",
             len(b.holes) == 3 and all(abs(hd - HOLE_D) < 0.01 for *_, hd in b.holes)
             and all(dist(a, w) < 0.05 for a, w in zip(got, want_holes)), f"expected {want_holes}, got {got}")
    he = min(min(hx - x1, x2 - hx, hy - y1, y2 - hy) - hd / 2 for hx, hy, hd in b.holes)
    ck.within(f"D.hole_edge.{k}: mounting hole edge to the board edge", he, JLC_EDGE, None, " mm")
ck.check("D.holes_match: the two boards' holes coincide", sorted((round(h[0], 2), round(h[1], 2)) for h in MB.holes) ==
         sorted((round(h[0], 2), round(h[1], 2)) for h in FB.holes))
DESIGN = harness.text("docs", "design.md")
m = re.search(r"Three 3\.2 mm holes, front-view \(([\d.]+), ([\d.]+)\), \(([\d.]+), ([\d.]+)\)\s+and \(([\d.]+), ([\d.]+)\)", DESIGN)
doc_holes = sorted((float(m.group(i)), float(m.group(i + 1))) for i in (1, 3, 5)) if m else []
ck.check("D.holes_design_md: design.md's three holes (front view, 'Mounting') are the boards' holes", bool(doc_holes) and
         all(dist(a, w) < 0.05 for a, w in zip(doc_holes, sorted((front(x), y) for x, y in want_holes))),
         f"design.md {doc_holes}, boards (front) {sorted((round(front(x), 2), y) for x, y in want_holes)}")

# copper to the edge
for k, b in BOARDS:
    x1, y1, x2, y2 = b.outline
    pe = min(min(p.x - p.r - x1, x2 - p.x - p.r, p.y - p.r - y1, y2 - p.y - p.r) for p in b.pads)
    _, te = b.keepouts()
    pour_e = min(min(q[0] - x1, x2 - q[0], q[1] - y1, y2 - q[1]) for isl in b.islands for q in isl.outline)
    ck.within(f"D.edge_pads.{k}: pad copper to the routed edge (JLCPCB {JLC_EDGE})", pe, JLC_EDGE, None, " mm")
    ck.within(f"D.edge_tracks.{k}: tracks and vias to the routed edge (JLCPCB {JLC_EDGE}; the audit's known 0.35 on the "
              "main board)", te, JLC_EDGE, None, " mm")
    ck.within(f"D.edge_pours.{k}: pour fill to the routed edge (JLCPCB {JLC_EDGE})", pour_e, JLC_EDGE - 1e-3, None, " mm")


def seg_dist_to_island(c, isl):
    best = 1e9
    for poly in [isl.outline] + list(isl.holes):
        for i in range(len(poly)):
            best = min(best, ca.d_point_seg(c, poly[i], poly[(i + 1) % len(poly)]))
    return best


# copper to the NPTH mounting holes
for k, b in BOARDS:
    worst = []
    for hx, hy, hd in b.holes:
        r = hd / 2
        for p in b.pads:
            worst.append((p.d_point((hx, hy)) - r, f"pad {p.ref}.{p.num}"))
        for t in b.tracks:
            worst.append((ca.d_point_seg((hx, hy), t["a"], t["b"]) - t["w"] / 2 - r, f"track {t['net']}"))
        for v in VIAS[k]:
            worst.append((dist(v["c"], (hx, hy)) - v["d"] / 2 - r, f"via {v['net']}"))
        for isl in b.islands:
            g = seg_dist_to_island((hx, hy), isl) - r
            worst.append((-1.0 if isl.contains((hx, hy)) else g, f"{isl.net} pour, layer {isl.layer}"))
    worst.sort()
    ck.within(f"D.hole_copper.{k}: copper to a mounting hole's edge (JLCPCB NPTH-to-track {JLC_NPTH_TRACK}); nearest: "
              f"{worst[0][1]}", worst[0][0], JLC_NPTH_TRACK, None, " mm")

# nothing but ground under a standoff (gap side) or a screw head (outer side); FB gap side = top, MB gap side = bottom
GROUND = {"main": ("GND",), "face": ("GND_F", "GND_D_F")}
for k, b in BOARDS:
    gap_layer = 1 if k == "face" else 2
    for side, layer, rad, what in (("gap", gap_layer, M3_STANDOFF_R, "standoff"), ("outer", 3 - gap_layer, M3_HEAD_R, "screw head")):
        exposed, other = [], []
        for hx, hy, hd in b.holes:
            for p in b.pads:
                d = p.d_point((hx, hy))
                if d < rad:
                    (other if p.net not in GROUND[k] else exposed).append(f"{p.ref}.{p.num} ({p.net}) {d:.2f} mm")
            for v in VIAS[k]:
                d = dist(v["c"], (hx, hy)) - v["d"] / 2
                if d < rad and v["net"] not in GROUND[k]:
                    other.append(f"via {v['net']} {d:.2f} mm")
            for t in b.tracks:
                d = ca.d_point_seg((hx, hy), t["a"], t["b"]) - t["w"] / 2
                if t["layer"] == layer and d < rad and t["net"] not in GROUND[k]:
                    other.append(f"track {t['net']} {d:.2f} mm")
        ck.check(f"D.under_{what.replace(' ', '_')}.{k}: nothing but ground within the M3 {what}'s r {rad:.2f} mm "
                 f"({'hex 5.5 AF across the corners' if what == 'standoff' else 'ISO 7045 pan head 5.6'}) on the "
                 f"{side} side", not other, f"{other}")
        news = [e for e in exposed if not e.startswith("J1.1 ")]
        ck.check(f"D.pads_under_{what.replace(' ', '_')}.{k}: no pad (a solder joint the {what} would sit on) within "
                 f"r {rad:.2f} mm but the audit's known J1 sleeve", not news,
                 f"ground pads: {exposed}" + (" (J1.1 2.66 mm from the (55.9, 30) hole: known)" if len(news) < len(exposed) else ""))

# ====================================================================== E. tracks
for k, b in BOARDS:
    thin_p = sorted({(t["net"], round(t["w"], 3)) for t in b.tracks if t["net"] in POWER_NETS and t["w"] < POWER_W - 1e-3})
    thin_s = sorted({(t["net"], round(t["w"], 3)) for t in b.tracks if t["w"] < SIGNAL_W - 1e-3})
    ck.check(f"E.power_tracks.{k}: every power-class track ({', '.join(n for n in POWER_NETS if any(t['net'] == n for t in b.tracks))}) "
             f"is {POWER_W} mm (design.md)", not thin_p, f"thinner: {thin_p}")
    ck.check(f"E.signal_tracks.{k}: every track >= {SIGNAL_W} mm (design.md's signal rule) and >= JLCPCB's {JLC_TRACK_MIN}",
             not thin_s and all(t["w"] >= JLC_TRACK_MIN for t in b.tracks),
             f"widths {sorted({round(t['w'], 3) for t in b.tracks})}, under {SIGNAL_W}: {thin_s}")
    nets = {t["net"] for t in b.tracks}
    pw = {n for n in nets if ("12V" in n or "3V3" in n)}
    ck.check(f"E.power_class_complete.{k}: every supply net routed is in design.md's 0.6 mm class", pw <= set(POWER_NETS),
             f"supply nets {sorted(pw)}")
CONN = {}
for k, b in BOARDS:
    groups, contacts = b.connectivity()
    CONN[k] = groups
    split = {n: len(g) for n, g in groups.items() if len(g) > 1}
    ck.check(f"E.connectivity.{k}: every net one piece of copper, no two nets touching (copper_audit)", not split and not contacts,
             f"split {split}, contacts {contacts[:4]}")
    under = [c for c in b.clearances(CLEARANCE) if c[0] < CLEARANCE]
    ck.check(f"E.clearance.{k}: nothing under the {CLEARANCE} mm rule (copper_audit's clearances; JLCPCB's minimum is "
             f"{JLC_TRACK_MIN})", not under, f"{len(under)}: {under[:5]}")

# ====================================================================== F. value labels
VALUES = vl.values()


def extent(pl):
    """A part's housing box grown to cover its own pads (the mixer suite's measure)."""
    x1, y1, x2, y2 = pl["body"]
    for pad in pl["pads"].values():
        x1, y1 = min(x1, pad.x - pad.r), min(y1, pad.y - pad.r)
        x2, y2 = max(x2, pad.x + pad.r), max(y2, pad.y + pad.r)
    return x1, y1, x2, y2


def rect_dist(a, b):
    return math.hypot(max(b[0] - a[2], a[0] - b[2], 0), max(b[1] - a[3], a[1] - b[3], 0))


def strings(k):
    return [p for h, p in R.pcb_docs[k]["recs"] if h["type"] == "STRING" and p and p.get("layerId") in (3, 4)]


def designators(k):
    out = []
    for h, p in R.pcb_docs[k]["recs"]:
        if h["type"] == "ATTR" and p and p.get("key") == "Designator" and p.get("valueVisible") and p.get("x") is not None:
            out.append((p["value"], p["layerId"] == 4, vl.text_box(p["x"] * MIL, p["y"] * MIL, p["value"], p["fontSize"],
                                                                   p.get("mirror", False)), p))
    return out


LABELS = {}
for k, b in BOARDS:
    vals = {r: v for r, v in VALUES.items() if r in b.parts}
    texts = set(vals.values())
    labs = []
    for p in strings(k):
        if p["text"] in texts:
            labs.append((p["text"], p["layerId"] == 4, vl.text_box(p["x"] * MIL, p["y"] * MIL, p["text"], p["fontSize"],
                                                                     p.get("mirror", False)), p))
    LABELS[k] = labs
    traps, ties, wrong_side, small, thin, ratio, on_pad, on_hole, on_text, seen = [], [], [], [], [], [], [], [], [], {}
    others = [(t, bot, rect) for t, bot, rect, p in labs] + [(t, bot, rect) for t, bot, rect, p in designators(k)]
    for i, (txt, bottom, rect, p) in enumerate(labs):
        if bool(p.get("mirror")) != bottom:
            wrong_side.append(f"'{txt}' mirror {p.get('mirror')} on layer {p['layerId']}")
        hgt, sw = p["fontSize"] * MIL, p.get("strokeWidth", 6) * MIL
        if hgt < JLC_SILK_H - 1e-6:
            small.append(f"'{txt}' {p['fontSize']:g} mil at ({rect[0]:.1f}, {rect[1]:.1f})")
        if sw < JLC_SILK_W - 1e-6:
            thin.append(f"'{txt}' {sw:.3f}")
        if sw / hgt < JLC_SILK_RATIO - 1e-6:
            ratio.append(round(hgt / sw, 1))
        for pad in b.pads:
            if vl.circle_hits(rect, (pad.x, pad.y), pad.r + JLC_PAD_SILK - 1e-3):
                on_pad.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f}) on {pad.ref}.{pad.num}")
                break
        for hx, hy, hd in b.holes:
            if vl.circle_hits(rect, (hx, hy), hd / 2 + JLC_PAD_SILK):
                on_hole.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f})")
        for j, (t2, bot2, r2) in enumerate(others):
            if j != i and bot2 == bottom and vl.overlaps(rect, r2):
                on_text.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f}) / '{t2}'")
        cands = sorted((rect_dist(rect, extent(b.parts[r])), r) for r in vals if b.parts[r]["bottom"] == bottom)
        same = [c for c in cands if vals[c[1]] == txt]
        other = [c for c in cands if vals[c[1]] != txt]
        own_d, own = same[0]
        seen.setdefault(own, []).append(own_d)
        if other and other[0][0] < own_d - 1e-6:
            traps.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f}): {other[0][1]} ({vals[other[0][1]]}) {other[0][0]:.2f} mm, "
                         f"nearer than {own} {own_d:.2f} mm")
        elif other and other[0][0] < own_d + 0.3:
            ties.append(f"'{txt}' {own} {own_d:.2f} / {other[0][1]} ({vals[other[0][1]]}) {other[0][0]:.2f}")
    ck.check(f"F.label_traps.{k}: no value label nearer a part of a different value than its own (outline to outline)",
             not traps, f"{len(traps)} of {len(labs)}: {traps}")
    ck.check(f"F.label_ties.{k}: every label at least 0.3 mm nearer its own part than any part of another value "
             "(the mixer's M3)", not ties, f"{len(ties)} of {len(labs)}: {ties}")
    ck.check(f"F.label_height.{k}: value labels >= JLCPCB's {JLC_SILK_H} mm text height", not small, f"{len(small)}: {small}")
    ck.check(f"F.label_stroke.{k}: value labels' line >= JLCPCB's {JLC_SILK_W} mm", not thin, f"{thin}")
    ck.check(f"F.label_ratio.{k}: line width / height >= JLCPCB's preferred 1:6 (a preference; the 0.15 line minimum "
             "is F.label_stroke)", not ratio,
             f"{len(ratio)} labels at 1:{sorted(set(ratio))} (6 mil line; the designators are the same 45 / 6 mil)")
    ck.check(f"F.label_mirror.{k}: each label on its part's side, mirrored on the bottom so it reads from that side",
             not wrong_side, f"{wrong_side}")
    ck.check(f"F.label_pads.{k}: no label within JLCPCB's {JLC_PAD_SILK} mm of a pad", not on_pad, f"{on_pad[:6]}")
    ck.check(f"F.label_holes.{k}: no label over a mounting hole", not on_hole, f"{on_hole}")
    ck.check(f"F.label_overlap.{k}: no label over another label or a designator", not on_text, f"{on_text[:6]}")
    # coverage: a label of the part's value within 3 mm of it, on its side
    missing = []
    for r in sorted(vals, key=lambda r: (r[0], int(re.sub(r"\D", "", r)))):
        pl = b.parts[r]
        d = min((rect_dist(rect, extent(pl)) for t, bot, rect, p in labs if t == vals[r] and bot == pl["bottom"]), default=99)
        if d > 3.0:
            missing.append(r)
    known = ["C31", "C32", "C33", "C34"] if k == "main" else []
    ck.check(f"F.label_coverage.{k}: every R / C / pot has its value within 3 mm, but the audit's known C31-C34",
             [r for r in missing if r not in known] == [], f"{len(labs)} labels; unlabelled: {missing}")
    two = {r: v for r, v in seen.items() if len(v) > 1}
    print(f"      {k}: {len(labs)} labels; parts that are the nearest same-value part of more than one label: {two}")

# ====================================================================== G. bodies
def rect_poly(cx, cy, L, W, ang):
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = ca.rot(sx * L / 2, sy * W / 2, ang)
        out.append((cx + dx, cy + dy))
    return out


def axis_angle(P, a="1", b="2"):
    return math.degrees(math.atan2(P[b].y - P[a].y, P[b].x - P[a].x))


SOLDERED_REFS = {ref for board, ref in harness.load("bom").SOLDERED}     # chips bom.py solders without a socket


def real_body(ref, pl, small_caps=False):
    """('circle', (cx, cy), r) or ('poly', corners): the part's body on its side at its largest (small_caps: the
    5.08 mm capacitors at TDK FG28 size, the 1 nF as a 2.5 mm thick film)."""
    fpn, P = pl["fp"], pl["pads"]
    mid = ((P["1"].x + P["2"].x) / 2, (P["1"].y + P["2"].y) / 2) if "2" in P else None
    if fpn == "RES-TH-VERTICAL-P2.54":
        return ("circle", (P["1"].x, P["1"].y), BODY_R_STAND_D / 2)
    if fpn in ("RES-TH_L6.2-W2.3-LR1F1K0", "RES-TH_BD2.3-L6.3-P10.30-D0.6"):
        return ("poly", rect_poly(*mid, *BODY_R_FLAT, axis_angle(P)))
    if fpn == "CAP-TH_L3.0-W2.0-P5.08-D0.7":
        L, W = (max(BODY_FILM[0], BODY_CER[0]), max(BODY_FILM[1], BODY_CER[1])) if VALUES.get(ref) == "1n" else BODY_CER
        if small_caps:
            L, W = (BODY_FILM[0], BODY_FILM[1]) if VALUES.get(ref) == "1n" else BODY_FG28
        return ("poly", rect_poly(*mid, L, W, axis_angle(P)))
    if fpn == "CAP-TH_L7.6-W3.8-P5.08-D0.51":
        return ("poly", rect_poly(*mid, *BODY_SR30, axis_angle(P)))
    if fpn.startswith("DO-35"):
        return ("poly", rect_poly(*mid, *BODY_DO35, axis_angle(P)))
    if fpn.startswith("DIP-"):
        n = len(P)
        c = (sum(p.x for p in P.values()) / n, sum(p.y for p in P.values()) / n)
        L, W = SOCKET_DIP14 if n == 14 else SOCKET_DIP16
        if ref in SOLDERED_REFS:       # [2026-11-14] soldered without a socket (bom.py SOLDERED): the chip's own body
            L, W = BODY_DIP14 if n == 14 else BODY_DIP16
        return ("poly", rect_poly(*c, L, W, axis_angle(P, "1", "2")))
    if fpn.startswith("HDR-"):
        n = len(P)
        c = (sum(p.x for p in P.values()) / n, sum(p.y for p in P.values()) / n)
        return ("poly", rect_poly(*c, n * 2.54, BODY_HDR_W, axis_angle(P, "1", "2")))
    x1, y1, x2, y2 = pl["body"]                # panel parts and the breakout: the drawn housing
    return ("poly", [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def _proj(poly, ax):
    v = [q[0] * ax[0] + q[1] * ax[1] for q in poly]
    return min(v), max(v)


def separation(a, b):
    """Positive: gap (SAT for two polygons); negative: overlap depth."""
    if a[0] == "circle" and b[0] == "circle":
        return dist(a[1], b[1]) - a[2] - b[2]
    if a[0] == "circle" or b[0] == "circle":
        c, p = (a, b) if a[0] == "circle" else (b, a)
        poly = p[1]
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
            best = max(best, max(b0 - a1, a0 - b1))
    return best


def pad_outline(pad, n=24):
    """Points round a pad's real outline (rectangle or stadium) in the board frame."""
    if pad.shape == "RECT":
        cs = pad.corners()
        out = []
        for i in range(4):
            a, c = cs[i], cs[(i + 1) % 4]
            out += [(a[0] + (c[0] - a[0]) * t / 6, a[1] + (c[1] - a[1]) * t / 6) for t in range(6)]
        return out
    a, c, r = pad.axis()
    ux, uy = (c[0] - a[0], c[1] - a[1])
    out = []
    for k in range(n):
        th = 2 * math.pi * k / n
        dx, dy = r * math.cos(th), r * math.sin(th)
        base = c if (dx * ux + dy * uy) >= 0 else a
        out.append((base[0] + dx, base[1] + dy))
    return out


def body_pad_sep(body, pad):
    """Gap between a body and a pad's real copper (negative: the body covers the pad by that much)."""
    pts = pad_outline(pad)
    if body[0] == "circle":
        return min(dist(q, body[1]) for q in pts) - body[2] if pad.d_point(body[1]) > 0 else -body[2]
    poly = body[1]
    depth = 0.0
    for q in pts + [(pad.x, pad.y)]:
        if ca.point_in_poly(q, poly):
            depth = max(depth, min(ca.d_point_seg(q, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))))
    if depth > 0:
        return -depth
    if any(pad.d_point(v) == 0 for v in poly):
        return -0.01
    return min(pad.d_seg(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def centre(body):
    return body[1] if body[0] == "circle" else (sum(q[0] for q in body[1]) / len(body[1]), sum(q[1] for q in body[1]) / len(body[1]))


BODIES = {k: {ref: real_body(ref, pl) for ref, pl in b.parts.items()} for k, b in BOARDS}
DECOUPLE_PAIRS = [("face", "C8", "U1", "16", "8"), ("face", "C9", "U9", "16", "8"), ("face", "C10", "U10", "16", "8"),
                  ("main", "C31", "U3", "4", "11"), ("main", "C32", "U3", "11", "4"), ("main", "C33", "U4", "4", "11"),
                  ("main", "C34", "U4", "11", "4")]
for k, b, bottom, skip in (("main", MB, False, {"U2"}), ("face", FB, False, set())):
    refs = sorted(r for r, pl in b.parts.items() if pl["bottom"] == bottom and r not in skip)
    hits = []
    for i, ra in enumerate(refs):
        for rb in refs[i + 1:]:
            A, B = BODIES[k][ra], BODIES[k][rb]
            if dist(centre(A), centre(B)) > 30:
                continue
            s = separation(A, B)
            if s < -1e-6:
                hits.append((round(s, 2), ra, rb))
    hits.sort()
    dec = {(c, u) for _, c, u, _, _ in DECOUPLE_PAIRS}
    socket = [h for h in hits if (h[1].startswith("U") or h[2].startswith("U")) and (h[1], h[2]) not in dec and (h[2], h[1]) not in dec]
    rest = [h for h in hits if not (h[1].startswith("U") or h[2].startswith("U"))]
    ck.check(f"G.bodies.{k}: no two real bodies (largest sizes) overlap on the {('top' if not bottom else 'bottom')} "
             "(rear) side, sockets aside", not rest, f"{len(rest)} overlaps (mm, a, b): {rest[:30]}")
    small = {r: real_body(r, b.parts[r], True) for r in refs}
    alt = sorted((round(separation(small[ra], small[rb]), 2), ra, rb) for i, ra in enumerate(refs) for rb in refs[i + 1:]
                 if dist(centre(small[ra]), centre(small[rb])) < 30 and separation(small[ra], small[rb]) < -1e-6
                 and ra[0] == "C" and not rb.startswith("U"))
    ck.check(f"G.bodies_small_caps.{k}: ... and with the capacitors at TDK FG28 size (4.0 x 2.5) and the 1 nF as a 2.5 mm "
             "film, no capacitor overlaps (what the BOM would have to name)", not alt, f"{alt}")
    ck.check(f"G.sockets.{k}: the DIP sockets' frames ({SOCKET_DIP14[0]} / {SOCKET_DIP16[0]} x 10.16) clear their "
             "neighbours' bodies", not socket, f"{len(socket)}: {socket}")
# the decouplers: beside their chips (supply pin to the cap's pad) and clear of the socket frames
DECOUPLE = DECOUPLE_PAIRS
far, lean = [], []
for k, c, u, vpin, gpin in DECOUPLE:
    b = MB if k == "main" else FB
    C, U = b.parts[c], b.parts[u]
    vnet = U["nets"][vpin]
    vp = next(p for n, p in C["pads"].items() if p.net == vnet)
    d = dist((vp.x, vp.y), (U["pads"][vpin].x, U["pads"][vpin].y))
    far.append((c, u, f"pin {vpin} {vnet}", round(d, 1)))
    s = separation(BODIES[k][c], BODIES[k][u])
    if s < 0:
        lean.append((c, u, round(s, 2)))
mb_far = [f for f in far if f[0] in ("C31", "C32", "C33", "C34")]
ck.check("G.decouple_mb: every TL074 100 n 3.6 mm from its supply pin (design.md 'every 100 n sits 3.6 mm from its supply "
         "pin'), 0.2 mm", all(abs(f[3] - 3.6) <= 0.2 for f in mb_far), f"{mb_far}")
fb_far = [f for f in far if f[0] in ("C8", "C9", "C10")]
ck.check("G.decouple_fb: every 4051 / 595 100 n within 5 mm of its chip's VCC pin 16 (design.md: 'decoupling at the "
         "supply pins', 'C8 100 n at U1 pin 16')", all(f[3] <= 5.0 for f in fb_far), f"{fb_far}")
ck.check("G.decouple_lean: no decoupler's body (dipped MLCC, 5.08 x 3.18 max) over its chip's socket frame", not lean,
         f"{lean}; with a TDK FG28-size body (2.5 thick): {[(c, u, round(s + (BODY_CER[1] - 2.5) / 2, 2)) for c, u, s in lean]}")
# rear-side bodies over the panel parts' solder joints (FB: panel parts on the bottom, soldered on the top)
on_joint, under_housing = [], []
for ref, pl in FB.parts.items():
    if pl["bottom"]:
        continue
    for r2, p2 in FB.parts.items():
        if not p2["bottom"]:
            continue
        for pad in p2["pads"].values():
            s = body_pad_sep(BODIES["face"][ref], pad)
            if s < 0:
                on_joint.append((round(s, 2), ref, f"{pad.ref}.{pad.num}"))
ck.check("G.rear_over_joints: no faceplate rear body (real size) over a panel part's pin, which is soldered on the rear",
         not on_joint, f"{len(on_joint)}: {sorted(on_joint)[:10]}")
for r2, p2 in FB.parts.items():
    if not p2["bottom"] or p2["fp"] == "LED-3MM-3P":      # the LEDs stand off the board at panel height
        continue
    x1, y1, x2, y2 = p2["body"]
    for ref, pl in FB.parts.items():
        if pl["bottom"]:
            continue
        for pad in pl["pads"].values():
            s = body_pad_sep(("poly", [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]), pad)
            if s < 0:
                under_housing.append((round(s, 2), f"{pad.ref}.{pad.num}", r2))
ck.check("G.joints_under_housings: no rear part's joint (soldered on the panel side) under a pot / jack / button housing",
         not under_housing, f"{len(under_housing)}: {sorted(under_housing)[:10]}")
# the screw heads and standoffs against bodies (panel side: drawn housings; rear and gap sides: real bodies)
hw = []
for k, b in BOARDS:
    for hx, hy, hd in b.holes:
        for ref, pl in b.parts.items():
            gap_side = (not pl["bottom"]) if k == "face" else pl["bottom"]
            rad = M3_STANDOFF_R if gap_side else M3_HEAD_R
            if pl["fp"] == "LED-3MM-3P":
                continue
            s = separation(BODIES[k][ref], ("circle", (hx, hy), rad))
            if s < 0:
                hw.append(f"{k} {ref} {'standoff' if gap_side else 'screw head'} at ({hx:.1f}, {hy:.1f}) {s:.2f}")
ck.check("G.hardware_room: no body inside a standoff's (r 3.18) or a screw head's (r 2.8) circle on either side of either "
         "board", not hw, f"{hw}")

m = re.search(r"The main board's resistors \(([^)]*)\) stand up", BOMMD := harness.text("docs", "bom.md"))
named = set()
if m:
    for part in re.findall(r"R(\d+)(?:–R(\d+))?", m.group(1)):
        a, z = int(part[0]), int(part[1] or part[0])
        named |= {f"R{i}" for i in range(a, z + 1) if f"R{i}" in MB.parts}
flat = sorted(r for r in named if MB.parts[r]["fp"] != "RES-TH-VERTICAL-P2.54")
ck.check("G.bom_standing_note: bom.md's note on the standing main-board resistors names only resistors the routed board "
         "stands up", bool(m) and not flat, f"named {len(named)}, lying flat on the routed board: "
         f"{[(r, MB.parts[r]['fp']) for r in flat]}")

# ====================================================================== H. stacking
GAP = MALE_PLASTIC + FEMALE_BODY
m = re.search(r"about (\d+(?:\.\d+)?) mm;\s*measure", DESIGN) or re.search(r"male header's 2\.5 mm spacer, about (\d+(?:\.\d+)?) mm", DESIGN)
ck.check(f"H.gap_design_md: design.md's header gap equals the mated header stack ({FEMALE_BODY} female + {MALE_PLASTIC} "
         "male plastic)",
         m is not None and abs(float(m.group(1)) - GAP) < 0.05, f"design.md {m and m.group(1)} mm, stack {GAP} mm")
m = re.search(r"M3 standoff, female-female, (\d+(?:\.\d+)?) mm", BOMMD)
ck.check("H.standoff_bom: bom.md's standoff length equals the header gap", m is not None and abs(float(m.group(1)) - GAP) < 0.05,
         f"bom.md {m and m.group(1)} mm, gap {GAP} mm")
# verifier 2026-11-13: FEMALE_BODY is itself bom.md's figure, so the old comparison could not fail; compare bom.md
# with design.md's own statement of the socket the gap is built on instead
m = re.search(r"Female header, 2\.54 mm, (\d+(?:\.\d+)?) mm tall", BOMMD)
m2 = re.search(r"standard\s+(\d+(?:\.\d+)?)\s+mm\s+socket", DESIGN)
ck.check("H.socket_bom: bom.md orders the female header design.md builds the gap on ('a standard 8.5 mm socket')",
         m is not None and m2 is not None and abs(float(m.group(1)) - float(m2.group(1))) < 0.01,
         f"bom.md {m and m.group(1)} mm, design.md {m2 and m2.group(1)} mm")


PCB_T = 1.6                  # every board 1.6 mm (bom.md)


def protrusion(p, typical):
    """How far a main-board top part's joint sticks out of the main board's bottom (into the header gap): the
    breakout's female headers and the DIP sockets have tails that are not clipped; other leads are clipped."""
    f = MB.parts[p.ref]["fp"]
    if f == "DAISY-SEED-POWER-OPAMPS-2.54":
        return (FEMALE_TAIL_TYP if typical else FEMALE_TAIL_MAX) - PCB_T
    if f.startswith("DIP-"):
        return (SOCKET_TAIL_TYP if typical else SOCKET_TAIL_MAX) - PCB_T
    return LEAD_PROTRUDE_TYP if typical else LEAD_PROTRUDE


# [2026-11-14: which faceplate chips sit in a socket is bom.py's SOLDERED (the test report's M3 fix solders
# U1 / U9 / U10 straight in); the turned-pin alternative below still prices a socket explicitly.]
SOLDERED_FB = {ref for board, ref in harness.load("bom").SOLDERED if board == "Faceplate"}


def pieces(ref, pl, typical, sock_h=None):
    """[(body, height)] of a faceplate rear part. A socketed DIP is two pieces (verifier 2026-11-13: the writer used
    the socket frame at the chip's height): the chip (TI body max) at socket + A, and the socket frame at its own
    height. A DIP bom.py solders without a socket is the chip alone, seated on the board."""
    f = pl["fp"]
    if f.startswith("DIP-"):
        P = pl["pads"]
        n = len(P)
        c = (sum(q.x for q in P.values()) / n, sum(q.y for q in P.values()) / n)
        L, W = BODY_DIP14 if n == 14 else BODY_DIP16
        chip = ("poly", rect_poly(*c, L, W, axis_angle(P, "1", "2")))
        if sock_h is None and ref in SOLDERED_FB:
            return [(chip, DIP_A_TYP if typical else DIP_A_MAX)]
        sh = sock_h if sock_h is not None else (SOCKET_H_TYP if typical else SOCKET_H)
        return [(chip, sh + (DIP_A_TYP if typical else DIP_A_MAX)), (BODIES["face"][ref], sh)]
    if f.startswith("RES-TH_"):
        return [(BODIES["face"][ref], H_R_FLAT)]
    if f.startswith("CAP-TH"):
        return [(BODIES["face"][ref], H_CAP)]
    return []


mb_tails = [p for p in MB.pads if not MB.parts[p.ref]["bottom"]]      # MB top parts' joints, out of the MB bottom
rows = []
for ref, pl in FB.parts.items():
    if pl["bottom"] or pl["fp"].startswith("HDR-"):
        continue
    for typical in (False, True):
        for body, h in pieces(ref, pl, typical):
            above = [p for p in mb_tails if body_pad_sep(body, p) < 0]
            prot = max((protrusion(p, typical) for p in above), default=0.0)
            top = max(above, key=lambda p: protrusion(p, typical)) if above else None
            rows.append((round(GAP - h - prot, 2), typical, ref, round(h, 2), len(above),
                         f"{top.ref}.{top.num} {prot:.2f}" if top else ""))
rows.sort()
wc = [r for r in rows if not r[1]]
ty = [r for r in rows if r[1]]
_dip16 = (f"DIP-16 soldered (bom.py: {sorted(SOLDERED_FB)}), A {DIP_A_MAX}" if {"U1", "U9", "U10"} <= SOLDERED_FB
          else f"DIP-16 in a stamped socket {SOCKET_H:.2f} + A {DIP_A_MAX}")
ck.check(f"H.gap_worst: the faceplate's rear parts clear the main board's tails and clipped leads in the {GAP:.2f} mm "
         f"gap at the largest sizes ({_dip16}; female-header tails "
         f"{FEMALE_TAIL_MAX - PCB_T:.2f}, socket tails {SOCKET_TAIL_MAX - PCB_T:.2f}, clipped leads {LEAD_PROTRUDE} out)",
         wc[0][0] >= 0, "tightest (margin, -, part, height, MB joints over it, the tallest): "
         + str([r for r in wc if r[0] < 1.0][:6]))
ck.check(f"H.gap_typical: ... and with 0.5 mm to spare at typical sizes (stamped socket {SOCKET_H_TYP} + A {DIP_A_TYP}, "
         f"tails {FEMALE_TAIL_TYP - PCB_T:.2f} / {SOCKET_TAIL_TYP - PCB_T:.2f}, leads {LEAD_PROTRUDE_TYP})",
         ty[0][0] >= 0.5, str(ty[:4]))
alt = []
for ref in ("U1", "U9", "U10"):
    for body, h in pieces(ref, FB.parts[ref], True, sock_h=SOCKET_TURNED_H)[:1]:
        above = [p for p in mb_tails if body_pad_sep(body, p) < 0]
        prot = max(((protrusion(p, True) if not MB.parts[p.ref]["fp"].startswith("RES") and
                     not MB.parts[p.ref]["fp"].startswith(("CAP", "DO-")) else 1.0) for p in above), default=0.0)
        alt.append((ref, round(GAP - h - prot, 2)))
print(f"      the same with turned-pin sockets (Mill-Max 110-43-316, {SOCKET_TURNED_H} above the board), A {DIP_A_TYP}, "
      f"nominal tails and the clippable leads cut to 1.0: margins {alt}; soldered without sockets the chips stand "
      f"{DIP_A_MAX} max")
# panel parts' joints on the FB top under the MB bottom's female sockets (whose underside is MALE_PLASTIC above the FB)
fem = []
for ref in ("H1", "H2", "H3"):
    body = BODIES["main"][ref]
    for p in FB.pads:
        if FB.parts[p.ref]["bottom"] and body_pad_sep(body, p) < 0:
            fem.append((ref, f"{p.ref}.{p.num}"))
ck.within("H.female_over_fb_joints: a panel-part joint on the faceplate's rear under a female socket body clears it (the "
          f"socket hangs {MALE_PLASTIC} mm above the faceplate, the joint {LEAD_PROTRUDE} mm high)",
          MALE_PLASTIC - LEAD_PROTRUDE if fem else 99, 0.0, None, " mm", f"joints under a socket: {fem}")
# the female sockets on the MB bottom against the MB's other bottom-side joints
sit = []
for ref in ("H1", "H2", "H3"):
    body = BODIES["main"][ref]
    for p in MB.pads:
        if p.ref == ref:
            continue
        s = body_pad_sep(body, p)
        if s < 0:
            sit.append((round(s, 2), ref, f"{p.ref}.{p.num}"))
sit.sort()
ck.check(f"H.female_on_joints: the main board's female sockets ({BODY_HDR_W} mm plastic) sit clear of the other parts' "
         "solder joints on the main board's bottom", not sit, f"{len(sit)}: {sit[:8]}")
# the breakout: nothing on the MB top under its outline (it stands about GAP above the main board)
under = [r for r, pl in MB.parts.items() if not pl["bottom"] and r != "U2" and separation(BODIES["main"]["U2"], BODIES["main"][r]) < 0]
ck.check("H.under_breakout: no main-board part under the breakout (SMD side down, about 11 mm up on its sockets)", not under,
         f"{under}")

# ====================================================================== I. pours
def poly_area(P):
    return abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2


def inscribed_r(poly, step=0.01):
    import numpy as np
    P = np.array(poly, float)
    x0, y0 = P.min(0)
    x1, y1 = P.max(0)
    gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    A, B = P, np.roll(P, -1, 0)
    inside = np.zeros(len(pts), bool)
    for (ax, ay), (bx, by) in zip(A, B):
        cond = (ay > pts[:, 1]) != (by > pts[:, 1])
        xs = ax + (pts[:, 1] - ay) * (bx - ax) / ((by - ay) or 1e-12)
        inside ^= cond & (pts[:, 0] < xs)
    pts = pts[inside]
    if not len(pts):
        return 0.0
    best = np.full(len(pts), np.inf)
    for (ax, ay), (bx, by) in zip(A, B):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1e-12
        t = np.clip(((pts[:, 0] - ax) * dx + (pts[:, 1] - ay) * dy) / L2, 0, 1)
        best = np.minimum(best, np.hypot(pts[:, 0] - ax - t * dx, pts[:, 1] - ay - t * dy))
    return float(best.max())


SLIVER_W = 0.25    # house judgement (the mixer's PCB-9): a pour piece under 1 mm2 nowhere wider than this


def far_end(sp):
    dx, dy = sp[1][0] - sp[0][0], sp[1][1] - sp[0][1]
    d = math.hypot(dx, dy) or 1
    return sp[1][0] + dx / d * 0.15, sp[1][1] + dy / d * 0.15


for k, b in BOARDS:
    groups = CONN[k]
    desc, dead, slivers = [], [], []
    for i, isl in enumerate(b.islands):
        area = poly_area(isl.outline) - sum(poly_area(h) for h in isl.holes)
        grp = next((g for g in groups.get(isl.net, {}).values() if ("island", i) in g), set())
        pads = [x for x in grp if x[0] == "pad"]
        spokes = [s for s in b.spokes if s[2] == isl.layer and s[3] == isl.net and isl.contains(far_end(s))]
        xs, ys = [q[0] for q in isl.outline], [q[1] for q in isl.outline]
        desc.append(f"{isl.net} L{isl.layer} {area:.1f} mm2 ({min(xs):.1f}, {min(ys):.1f})-({max(xs):.1f}, {max(ys):.1f}), "
                    f"{len(spokes)} spokes")
        if not pads:
            dead.append(desc[-1])
        if area < 1.0:
            w = 2 * inscribed_r(isl.outline)
            if w < SLIVER_W:
                slivers.append(f"{desc[-1]}, at most {w:.2f} mm wide")
    print(f"      {k} pour islands: {desc}")
    ck.check(f"I.pours_reached.{k}: every pour island joined to a pad of its net (no dead copper)", not dead, f"dead: {dead}")
    ck.check(f"I.pour_slivers.{k}: no pour piece under 1 mm2 narrower than {SLIVER_W} mm", not slivers, f"{slivers}")
    want = {"main": ("GND",), "face": ("GND_F",)}[k]
    layers = sorted({(i.net, i.layer) for i in b.islands})
    ck.check(f"I.pour_layers.{k}: {'/'.join(want)} poured on both layers (design.md 'pour the ground on both layers')",
             all((n, l) in layers for n in want for l in (1, 2)), f"{layers}")
    # thermal spokes on the ground pads that sit in a pour
    weak, spread = [], collections.Counter()
    for pad in b.pads:
        if pad.net not in want:
            continue
        n_sp, in_pour = 0, False
        for layer in (1, 2):
            isl = [i for i in b.islands if i.layer == layer and i.net == pad.net and ca.point_in_poly((pad.x, pad.y), i.outline)]
            if not isl:
                continue
            in_pour = True
            n_sp += sum(1 for s in b.spokes if s[2] == layer and s[3] == pad.net and dist(s[0], (pad.x, pad.y)) < 0.3)
        tracks = sum(1 for t in b.tracks if t["net"] == pad.net and pad.d_seg(t["a"], t["b"]) <= t["w"] / 2 + 1e-3)
        if in_pour:
            spread[n_sp] += 1
        if in_pour and n_sp < 2 and tracks == 0:
            weak.append(f"{pad.ref}.{pad.num} {n_sp} spoke(s)")
    ck.check(f"I.spokes.{k}: every {'/'.join(want)} pad inside a pour held by at least 2 thermal spokes or a track", not weak,
             f"{weak}; pads by spokes over both layers {dict(sorted(spread.items()))}")

ck.done()
