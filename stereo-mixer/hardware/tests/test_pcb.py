"""PCB group: manufacturing and assembly checks on the routed master (StereoMixer-routed.epro2) that
copper_audit.py does not do.

  footprints    DIP-14 / DIP-16 / header / power-header / jack geometry against the datasheets; pin 1 square;
                every TL074 / CD4093B / CD4013B on the DIP-14, every CD4053B on the DIP-16
  holes         every pad's drill against the lead it takes (IPC-2222 fit), annular rings and plated slots
                against JLCPCB's 2-layer minimums, via drill / diameter, hole-to-hole and drill-to-track
                spacing, track widths (fab minimum and design.md's 0.6 mm POWER class), pads and pours to
                the board edge
  outline       both boards 140.4 x 108 mm, four 3.2 mm holes at circuit.HOLES_FRONT on both, nothing
                exposed under a standoff or screw head
  panel parts   the routed faceplate's jacks, pots and buttons at circuit.PLACEMENT (0.05 mm), oriented
                per design.md, their shafts / barrels / caps under the routed panel's holes
  silkscreen    every value label nearest a part of the value it states, every labelled part labelled,
                text heights, designators, polarity marks (diodes, electrolytics, DIP-14 / DIP-16 pin 1,
                power header pin 1 = -12 V)
  bodies        real body sizes (datasheets) against each other on the main board's top, the DIP-14 and
                DIP-16 sockets against their neighbours, top-side bodies over the bottom sockets' solder joints,
                each chip's 100 n beside its supply pin, what sits in the stacking gap, the standoff length
                against the header / socket heights
  pours         the small pour islands: what holds them to their net, which are dead copper

Since 2026-11-15 the master's main board is the generated placement (swap_main_board.py): placed, net-assigned,
not routed (no tracks, vias or pours) and without value labels. Every check that needs the main board's copper
or its value labels is skipped there (a SKIP line each, not counted) and two gate checks at the end fail instead,
naming what was skipped: "Main: routed (tracks, vias, pours)" and "Main: value labels placed" (the faceplate's
pass). Everything that reads the placement (footprints, drills and rings
of its pads, holes, outline, standoffs, bodies, sockets, pin-1 marks, designators, the stacking gap, J18) runs on
it as before; the faceplate's checks are unchanged. Once the main board is routed and labelled the gates pass and
the skipped checks run by themselves.

Run from stereo-mixer/hardware/tests:  python test_pcb.py
Read-only: imports the tools and opens the committed export as a zip.
"""
import collections
import json
import math
import re

import harness

ck = harness.Checks("pcb")
ca = harness.load("copper_audit")
circuit = harness.load("circuit")
vl = harness.load("value_labels")

MIL = 0.0254

# ------------------------------------------------------------------ datasheet / fab numbers
# JLCPCB PCB capabilities, 2-layer 1 oz (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-11-04)
JLC_RING_MIN = 0.18        # PTH annular ring, absolute minimum ("recommended 0.25 mm or above")
JLC_RING_REC = 0.25        # PTH annular ring, recommended
JLC_TRACK_MIN = 0.10       # min trace width, 1 oz (copper_audit uses 0.127 for spacing; we use the stricter 0.127 below)
JLC_TRACK_SAFE = 0.127     # 5 mil, the long-standing 2-layer figure: the conservative one
JLC_VIA_DRILL_MIN = 0.15   # min via hole
JLC_VIA_DIA_MIN = 0.25     # min via diameter
JLC_PSLOT_MIN = 0.50       # min plated slot width
JLC_HOLE_HOLE_PAD = 0.45   # hole to hole, pad holes (different nets)
JLC_HOLE_HOLE_VIA = 0.20   # hole to hole, vias
JLC_PTH_TRACK = 0.28       # PTH (drill edge) to an unrelated track: minimum (0.35 recommended)
JLC_EDGE = 0.20            # copper to a routed board edge
JLC_SILK_H = 1.0           # min silkscreen text height, mm (40 mil)
JLC_SILK_W = 0.15          # min silkscreen line width
JLC_PAD_SILK = 0.15        # pad to silkscreen
JLC_PTH_TOL_MINUS = 0.08   # finished PTH diameter tolerance +0.13 / -0.08
# IPC-2222 table 9-3: nominal hole minus maximum lead, minimum per producibility level (A 0.25, B 0.20, C 0.15);
# we demand level C (the tightest allowed) on the nominal drill, and that the smallest finished hole
# (drill - 0.08) still clears the lead's diagonal by 0.05 mm.
IPC_FIT_MIN = 0.15
INSERT_MIN = 0.05
IPC_FIT_MAX = 0.70         # nominal hole minus minimum lead, level A maximum (a looser hole wicks and tilts)

# Leads, (shape, max width, max thickness) in mm: 'round' -> (d, d); 'rect' -> width x thickness (diagonal used
# in a round hole, the two sides in a slot).
LEADS = {
    # TI TL074 / CD4093B / CD4013B, N (PDIP-14, MS-001) package drawing: b 0.36-0.56 (0.014-0.022 in),
    # c 0.20-0.36 (0.008-0.014 in): max values. Standard 0.300 in row pitch, 0.100 in pin pitch.
    "DIP-14-W7.62-P2.54": {"*": ("rect", 0.56, 0.36)},
    # TI CD4053BE, N (PDIP-16) package (SCHS047O, 2026-11-15): the same MS-001 lead frame as the 14-pin N package
    # (b 0.36-0.56, c 0.20-0.36 max). The package drawing is not in the datasheet's text extraction, so these are
    # the DIP-14 figures above, not re-read for 16 pins.
    "DIP-16-W7.62-P2.54": {"*": ("rect", 0.56, 0.36)},
    # 2.54 mm male header / female socket tails: 0.64 mm square post (industry standard 0.025 in).
    "HDR-1x8-P2.54": {"*": ("rect", 0.64, 0.64)},
    "HDR-1x12-P2.54": {"*": ("rect", 0.64, 0.64)},
    # 2x8 shrouded box header: 0.64 mm square posts.
    "IDC-TH_16P-P2.54_C3406": {"*": ("rect", 0.64, 0.64)},
    # Standing 1/4 W metal film resistors (Tayda, BOM): lead 0.6 mm max (Yageo MFR-25: 0.54 +-0.05 -> 0.59).
    "RES-TH-VERTICAL-P2.54": {"*": ("round", 0.60, 0.60)},
    # 1N5819, DO-41 (ON Semi / Vishay drawing): lead diameter 0.71-0.86 mm -> 0.864 max.
    "DO-41_BD2.4-L4.7-P8.70-D0.8-RD": {"*": ("round", 0.864, 0.864)},
    # 1N4148, DO-35 (Vishay / onsemi drawing): lead diameter 0.46-0.56 mm -> 0.56 max.
    "DO-35_BD2.0-L4.0-P8.0-D0.5-RD": {"*": ("round", 0.56, 0.56)},
    # 10 uF electrolytic, 5 mm can (BOM): lead 0.5 mm (Panasonic FC / Nichicon UPW 5 mm: 0.5 +-0.05).
    "CAP-TH_BD4.8-P2.50-D0.5-FD": {"*": ("round", 0.55, 0.55)},
    # 100 n / 22 p ceramics, TDK FG28 (5 mm leads): lead 0.5 mm (TDK FG series 0.5; NT00 variant not
    # confirmed, 0.55 assumed as the max).
    "CAP-TH_L3.0-W2.0-P5.08-D0.7": {"*": ("round", 0.55, 0.55)},
    # 1 uF KYOCERA AVX SR305C105KAR (SR30 series): lead 0.508 mm (0.020 in) -> 0.55 with tolerance.
    "CAP-TH_L7.6-W3.8-P5.08-D0.51": {"*": ("round", 0.55, 0.55)},
    # 4.7 / 10 pF KEMET C315 (Goldmax 300, 2.54 mm leads): lead 0.51 mm (0.020 in) -> 0.56 with tolerance (ASSUMED
    # the same allowance as the other 0.020 in leads; the catalogue gives the nominal only).
    "CAP-TH_P2.54-L4.0-W2.5": {"*": ("round", 0.56, 0.56)},
    # Alpha 9 mm vertical pots: terminal pins and snap-in legs. Alpha's drawing (RD901F) is an image we could
    # not read; KiCad's RD901F footprint (the source of these footprints) uses 1.0 mm drills for the pins.
    # Assumed pins 0.8 x 0.4 flat (diagonal 0.89), unconfirmed; the snap-in legs are not checked for fit.
    "POT-ALPHA-9MM-RD901F": {"1": ("rect", 0.8, 0.4), "2": ("rect", 0.8, 0.4), "3": ("rect", 0.8, 0.4)},
    "POT-ALPHA-9MM-RD902F-DUAL": {str(n): ("rect", 0.8, 0.4) for n in range(1, 7)},
    # Thonkiconn PJ398SM / QingPu WQP518MA: flat solder lugs. No dimensioned drawing found (Thonk's site
    # blocks fetches); the footprint is LCSC's for the WQP518MA, so its slots are the maker's. Assumed lug
    # cross-section 1.0 x 0.3 (unconfirmed): checked against the slots' length and width.
    "CONN-TH_WQP-WQP518MA": {"*": ("rect", 1.0, 0.3)},
    # Thonk low-profile LED button: pin size unknown (no datasheet); assumed 0.7 mm square-ish (unconfirmed).
    "SW-TACT-LP-LED-THONK": {"*": ("rect", 0.7, 0.5)},
}

# Thonkiconn barrel centre to the lugs (Thonk's PJ398SM drawing as copper_audit and circuit.py quote it:
# sleeve 6.48, switch 3.38 on the same side, tip 4.92 on the other side). Recalled figures, not re-confirmed.
THONK_SLEEVE, THONK_SWITCH, THONK_TIP = 6.48, 3.38, 4.92

# Real bodies (max) for the collision check, mm
BODY_R_STAND_D = 2.5       # 1/4 W metal film body diameter, standing (Yageo MFR-25 / generic Tayda: 2.3-2.5 max)
BODY_FG28 = (4.0, 2.5)     # TDK FG28: W 4.0 x T 2.5 (x H 5.5), distributor listings of FG28X7R1H104KNT00/NT06
# NOTE (verifier): bom.md does not name the 100 n / 22 p part ("100 nF ceramic (X7R), 5.08 mm leads", Tayda).
# The FG28 is a small-bodied choice; a generic dipped 0.2 in MLCC (KEMET C320-class body 5.08 x 3.18 max,
# distributor listings) would overlap the CMOS chips by ~0.54 mm instead of 0.2. Not modelled as the
# expectation here: the finding asks the BOM to name a <= 4.0 x 2.5 body.
BODY_SR30 = (7.62, 3.81)   # AVX SR30: 0.300 x 0.150 in (as the footprint name says; not re-confirmed)
BODY_DIP14 = (19.69, 7.11)  # TI N package max: D 0.775 in, E1 0.280 in
# TI CD4053BE, N (PDIP-16): SCHS047O's package table gives 19.3 x 9.4 mm, nominal, the width over the pins. TI's
# N-package drawing gives 16 pins the same 0.775 in (19.69 mm) maximum length as 14 and the same 0.280 in body
# width (recalled from that drawing, not in the datasheet's text extraction): taken as BODY_DIP14.
BODY_DIP16 = (19.69, 7.11)
BODY_DO41 = (5.2, 2.7)     # DO-41 max body: 5.21 x 2.72 (ON Semi 1N5819)
BODY_C315 = (3.81, 2.54)   # KEMET C315: 3.81 long (along the leads) x 2.54 deep x 5.33 tall, max (distributor listings)
BODY_DO35 = (4.56, 2.28)   # DO-35 max body (Vishay 1N4148: 3.9 typ, JEDEC 5.08 max length; 2.28 dia)
BODY_CP_D = 5.5            # 5 mm can + 0.5 tolerance and sleeve (Panasonic FC: D + 0.5 max)
# 0.3 in 14-pin socket frame, length x width: Oupiin dual-wipe 14-pin drawing A 17.78 / C 10.16 mm, Solo
# SL-STIC-14 17.73 x 9.95 mm, Winslow W3114 17.65 x 10.14 mm (distributor listings, 2026-11-04): the largest of
# these. (The first version assumed 19.3 x 10.16, longer than any listed socket.)
SOCKET_DIP14 = (17.78, 10.16)
# 0.3 in 16-pin socket frame: one pin pitch longer, 8 x 2.54 = 20.32 x 10.16 mm (the 14-pin frames above are
# 7 x 2.54 = 17.78 long); Mill-Max 110-44-316-41-001000 (Digi-Key / elcodis listing via a search summary,
# 2026-11-15: 20.32 x 10.16 mm, not opened). The CD4053Bs sit in these (bom.md: 8 DIP-16 IC sockets).
SOCKET_DIP16 = (20.32, 10.16)
SOCKETS = {"DIP-14-W7.62-P2.54": SOCKET_DIP14, "DIP-16-W7.62-P2.54": SOCKET_DIP16}

# Stacking: 2.54 mm headers
MALE_PLASTIC = 2.5         # standard male header plastic body height
MALE_PIN_ABOVE = 6.0       # mating pin length above the plastic (typ 5.8-6.1)
FEMALE_BODY = 8.5          # the BOM's female header height (8.5 mm tall)
LEAD_PROTRUDE = 2.0        # trimmed lead / socket tail sticking out of the far side of a 1.6 mm board (max)
# M3 hardware round the mounting holes
M3_HEAD_R = 5.7 / 2        # ISO 7380 button head dk 5.7 (DIN 912 5.5, ISO 7045 pan 5.6)
M3_STANDOFF_R = 6.35 / 2   # 5.5 mm AF hex standoff: across the corners 6.35

BOARD_W, BOARD_H = 140.4, 108.0

# ------------------------------------------------------------------ load the routed master
docs = harness.read_export()
fps = ca.footprints_of(docs)
boards = ca.boards_of(docs, fps)
MB = next(b for t, b in boards.items() if "Main" in t)
FB = next(b for t, b in boards.items() if "Faceplate" in t)
PANEL = next(d for t, d in boards.items() if "Panel" in t)
DOC = {}
for u, d in docs.items():
    if d["docType"] == "PCB":
        DOC[next(p["title"] for h, p in d["recs"] if h["type"] == "META")] = d

# raw footprint pads with their holes
FP = {}
FPDOC = {}
for u, d in docs.items():
    if d["docType"] != "FOOTPRINT":
        continue
    title = next(p["title"] for h, p in d["recs"] if h["type"] == "META")
    FPDOC[title] = d
    pads = {}
    for h, p in d["recs"]:
        if h["type"] == "PAD":
            dp, ho = p["defaultPad"], p["hole"] or {}
            pads[str(p["num"])] = {"x": p["centerX"] * MIL, "y": p["centerY"] * MIL, "shape": dp["padType"],
                                   "w": dp["width"] * MIL, "h": dp["height"] * MIL,
                                   "hole": ho.get("holeType"), "hw": ho.get("width", 0) * MIL,
                                   "hh": ho.get("height", 0) * MIL, "plated": p["plated"], "angle": p.get("padAngle") or 0}
    FP[title] = pads
USED = collections.defaultdict(list)
for b in (MB, FB):
    for ref, pl in b.parts.items():
        USED[pl["fp"]].append((b.title, ref))

# What the main board has to check (2026-11-15: placed, not routed, no value labels). A check that needs copper or
# labels the board does not have yet is skipped on it, never passed on nothing; the two gates at the end fail with
# the list of what was skipped.
VALUES = vl.values()
COPPER = {b.title: bool(b.tracks or b.vias or b.islands) for b in (MB, FB)}
LABELS = {b.title: any(h["type"] == "STRING" and p.get("layerId") in (3, 4) and p["text"] in set(VALUES[b.title.split()[1]].values())
                       for h, p in DOC[b.title]["recs"]) for b in (MB, FB)}
SKIPPED = {"routed": [], "labels": []}


def skip(gate, name, b):
    """Record and print a check that cannot run on board b yet (gate 'routed' or 'labels')."""
    SKIPPED[gate].append(name)
    why = ("not routed yet: 0 tracks, 0 vias, 0 pour islands" if gate == "routed" else
           "no value labels yet (value_labels.py runs on the routed export)")
    print(f"SKIP  {name}: {b.title} {why}", flush=True)


def runs(gate, name, b):
    """True when the check can run on board b; otherwise records the skip."""
    ok = COPPER[b.title] if gate == "routed" else LABELS[b.title]
    if not ok:
        skip(gate, name, b)
    return ok


def front(x):
    return BOARD_W - x


# ================================================================== 1. footprint geometry
def dip_geometry(title, n):
    pads = FP[title]
    rows = {}
    for i in range(1, n + 1):
        rows[i] = (pads[str(i)]["x"], pads[str(i)]["y"])
    pitch = [math.hypot(rows[i + 1][0] - rows[i][0], rows[i + 1][1] - rows[i][1]) for i in range(1, n // 2)]
    pitch += [math.hypot(rows[i + 1][0] - rows[i][0], rows[i + 1][1] - rows[i][1]) for i in range(n // 2 + 1, n)]
    across = [math.hypot(rows[i][0] - rows[n + 1 - i][0], rows[i][1] - rows[n + 1 - i][1]) for i in range(1, n // 2 + 1)]
    ck.check(f"{title}: pin pitch 2.54 mm", all(abs(p - 2.54) < 0.01 for p in pitch),
             f"expected 2.54, got {sorted(set(round(p, 3) for p in pitch))}")
    ck.check(f"{title}: row spacing 7.62 mm (pin i opposite pin {n + 1}-i)", all(abs(a - 7.62) < 0.01 for a in across),
             f"expected 7.62 (a DIP socket's 0.300 in), got {sorted(set(round(a, 3) for a in across))}")
    # counter-clockwise numbering: pin 1..n/2 on one row, n/2+1..n back along the other
    r1 = {round(rows[i][1], 2) for i in range(1, n // 2 + 1)}
    r2 = {round(rows[i][1], 2) for i in range(n // 2 + 1, n + 1)}
    ck.check(f"{title}: pins 1-{n // 2} on one row, {n // 2 + 1}-{n} on the other", len(r1) == 1 and len(r2) == 1 and r1 != r2,
             f"row y of pins 1..{n // 2}: {r1}, of the rest: {r2}")
    ck.check(f"{title}: pin 1 pad is square (the assembly pin-1 cue)", pads["1"]["shape"] == "RECT" and
             all(pads[str(i)]["shape"] != "RECT" for i in range(2, n + 1)), f"pin 1 {pads['1']['shape']}")


dip_geometry("DIP-14-W7.62-P2.54", 14)
dip_geometry("DIP-16-W7.62-P2.54", 16)
ck.check("every TL074 / CD4093B / CD4013B uses the 7.62 mm DIP-14, none the library's 8.89 mm PDIP-14",
         sorted(r for t, r in USED["DIP-14-W7.62-P2.54"]) == sorted(f"U{i}" for i in range(1, 11))
         and not USED.get("PDIP-14_L19.3-W6.4-P2.54-LS9.0-BL"),
         f"DIP-14-W7.62 on {sorted(r for t, r in USED['DIP-14-W7.62-P2.54'])}, "
         f"PDIP-14 LS9.0 on {USED.get('PDIP-14_L19.3-W6.4-P2.54-LS9.0-BL', [])}")
cd4053 = sorted(p.ref for p in circuit.main_board_parts() if p.kind == "CD4053")
ck.check("every CD4053B uses DIP-16-W7.62, and nothing else does",
         sorted(r for t, r in USED["DIP-16-W7.62-P2.54"]) == cd4053 == sorted(circuit.SWITCH.values()),
         f"DIP-16-W7.62 on {sorted(r for t, r in USED['DIP-16-W7.62-P2.54'])}, CD4053B in circuit.py {cd4053}")
ck.check("no AQY212EH / DIP-4 left on the boards (2026-11-15)", not any(t.startswith("DIP-4") for t in USED)
         and not any(r.startswith("K") for t, r in sum(USED.values(), [])),
         f"DIP-4 footprints used: {[t for t in USED if t.startswith('DIP-4')]}")
# the placed parts: pin 1 to pin 14 etc. on the routed board itself (the mirror of a wrong flip would show here)
bad = []
for ref, pl in MB.parts.items():
    if pl["fp"].startswith("DIP-"):
        n = len(pl["pads"])
        d = math.hypot(pl["pads"]["1"].x - pl["pads"][str(n)].x, pl["pads"]["1"].y - pl["pads"][str(n)].y)
        if abs(d - 7.62) > 0.01 or pl["bottom"]:
            bad.append(f"{ref} {d:.3f}{' bottom' if pl['bottom'] else ''}")
ck.check("placed DIPs: pin 1 to pin n 7.62 mm, all on the top (rear) side", not bad, f"bad: {bad}")

for title, n in (("HDR-1x8-P2.54", 8), ("HDR-1x12-P2.54", 12)):
    p = FP[title]
    gaps = [math.hypot(p[str(i + 1)]["x"] - p[str(i)]["x"], p[str(i + 1)]["y"] - p[str(i)]["y"]) for i in range(1, n)]
    ck.check(f"{title}: {n} pins at 2.54 mm in a line, pin 1 square", all(abs(g - 2.54) < 0.01 for g in gaps)
             and len({round(p[str(i)]["y"], 3) for i in range(1, n + 1)}) == 1 and p["1"]["shape"] == "RECT",
             f"gaps {sorted(set(round(g, 3) for g in gaps))}, pin 1 {p['1']['shape']}")
p = FP["IDC-TH_16P-P2.54_C3406"]
ok = all(abs(abs(p[str(2 * k + 1)]["y"] - p[str(2 * k + 2)]["y"]) - 2.54) < 0.01 and
         abs(p[str(2 * k + 1)]["x"] - p[str(2 * k + 2)]["x"]) < 0.01 for k in range(8)) and \
    all(abs(p[str(2 * k + 3)]["x"] - p[str(2 * k + 1)]["x"] - 2.54) < 0.01 for k in range(7))
ck.check("J18 2x8 box header: odd / even pins across the rows 2.54 apart, columns 2.54 apart (IDC numbering)", ok)

# Thonkiconn: lugs at Thonk's distances from the barrel (barrel = origin + JACK_BARREL along the sleeve axis)
p = FP["CONN-TH_WQP-WQP518MA"]
sx = p["1"]["y"]
sign = -1 if sx < 0 else 1             # the sleeve side
barrel = -sign * abs(circuit.JACK_BARREL)
got = (abs(p["1"]["y"] - barrel), abs(p["2"]["y"] - barrel), abs(p["3"]["y"] - barrel))
same_side = (p["2"]["y"] - barrel) * (p["1"]["y"] - barrel) > 0 and (p["3"]["y"] - barrel) * (p["1"]["y"] - barrel) < 0
ck.check("WQP518MA footprint: sleeve / switch / tip lugs at Thonk's 6.48 / 3.38 / 4.92 mm from the barrel, "
         "switch on the sleeve side", same_side and all(abs(g - w) < 0.02 for g, w in zip(got, (THONK_SLEEVE, THONK_SWITCH, THONK_TIP))),
         f"expected (6.48, 3.38, 4.92), got ({got[0]:.2f}, {got[1]:.2f}, {got[2]:.2f}), switch on the sleeve side: {same_side}")

# ================================================================== 2. holes, rings, tracks, edges
fit_bad, loose, ring_min_bad, ring_rec_bad, slot_bad = [], [], [], [], []
for title, pads in sorted(FP.items()):
    if title not in USED:
        continue
    leads = LEADS.get(title)
    for num, pd in sorted(pads.items()):
        if not pd["hole"]:
            continue
        # annular ring: per axis for slots / ovals
        if pd["hole"] == "ROUND":
            ring = (min(pd["w"], pd["h"]) - pd["hw"]) / 2
        else:
            # slot and pad long axes are both the larger dimension in the footprint's frame
            ring = min((max(pd["w"], pd["h"]) - max(pd["hw"], pd["hh"])) / 2,
                       (min(pd["w"], pd["h"]) - min(pd["hw"], pd["hh"])) / 2)
            if min(pd["hw"], pd["hh"]) < JLC_PSLOT_MIN - 1e-6:
                slot_bad.append(f"{title}.{num} slot {pd['hw']:.2f} x {pd['hh']:.2f}")
        if ring < JLC_RING_MIN - 1e-3:
            ring_min_bad.append(f"{title}.{num} {ring:.3f}")
        elif ring < JLC_RING_REC - 1e-3:
            ring_rec_bad.append(f"{title}.{num} {ring:.3f}")
        if not leads:
            continue
        lead = leads.get(num, leads.get("*"))
        if lead is None:
            continue
        shape, lw, lt = lead
        if pd["hole"] == "ROUND":
            diag = lw if shape == "round" else math.hypot(lw, lt)
            margin = pd["hw"] - diag
            insert = pd["hw"] - JLC_PTH_TOL_MINUS - diag
            # IPC-2222's hole-minus-lead figures are for round leads; a square / flat lead only has to pass
            # its diagonal through the smallest finished hole (1.0 mm for a 0.64 mm post is the standard)
            if (shape == "round" and margin < IPC_FIT_MIN - 1e-6) or insert < (INSERT_MIN if shape == "round" else 0):
                fit_bad.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {diag:.2f} lead (nominal clearance {margin:.2f}, "
                               f"smallest finished hole {insert:.2f})")
            if pd["hw"] - min(lw, lt) * (0.9 if shape == "round" else 1) > IPC_FIT_MAX and shape == "round":
                loose.append(f"{title}.{num}: drill {pd['hw']:.2f} for a {lw:.2f} lead")
        else:
            L, Wd = max(pd["hw"], pd["hh"]), min(pd["hw"], pd["hh"])
            if L - JLC_PTH_TOL_MINUS - lw < INSERT_MIN or Wd - JLC_PTH_TOL_MINUS - lt < INSERT_MIN:
                fit_bad.append(f"{title}.{num}: slot {L:.2f} x {Wd:.2f} for a {lw:.2f} x {lt:.2f} lug")
ck.check("every lead fits its hole (round: IPC-2222 level C 0.15 on the nominal drill and 0.05 at the fab's -0.08; "
         "square / flat: the diagonal through the smallest finished hole)",
         not fit_bad, f"{len(fit_bad)} tight: {fit_bad}")
ck.check("no round hole more than 0.7 mm over its lead (IPC-2222 level A maximum)", not loose, f"loose: {loose}")
ck.check(f"annular rings >= JLCPCB's absolute minimum {JLC_RING_MIN} mm", not ring_min_bad, f"under: {ring_min_bad}")
ck.check(f"annular rings >= JLCPCB's recommended {JLC_RING_REC} mm", not ring_rec_bad, f"under the recommendation: {ring_rec_bad}")
ck.check(f"plated slots >= JLCPCB's {JLC_PSLOT_MIN} mm minimum width", not slot_bad, f"narrow: {slot_bad}")

for b in (MB, FB):
    name = b.title.split()[1]
    vd = sorted({(round(v["drill"], 3), round(2 * v["r"], 3)) for v in b.vias})
    title = f"{name}: vias drill >= {JLC_VIA_DRILL_MIN}, diameter >= {JLC_VIA_DIA_MIN}, ring >= 0.1"
    if runs("routed", title, b):
        ck.check(title, all(d >= JLC_VIA_DRILL_MIN and D >= JLC_VIA_DIA_MIN and (D - d) / 2 >= 0.1 for d, D in vd),
                 f"(drill, diameter) used: {vd}")
    tw = sorted({round(t["w"], 3) for t in b.tracks})
    title = f"{name}: track widths >= {JLC_TRACK_SAFE} mm"
    if runs("routed", title, b):
        ck.check(title, all(w >= JLC_TRACK_SAFE for w in tw), f"widths {tw}")
POWER = ("+12V", "-12V", "P12_IN", "N12_IN", "P12_D", "N12_D")
title = "main: every POWER-class track (+12V, -12V, P12_IN, N12_IN, P12_D, N12_D) is 0.6 mm (design.md rule)"
if runs("routed", title, MB):
    thin = sorted({(t["net"], round(t["w"], 3)) for t in MB.tracks if t["net"] in POWER and t["w"] < 0.6 - 1e-3})
    ck.check(title, not thin, f"thinner: {thin}")


hole_bad = []
for b in (MB, FB):
    name = b.title.split()[1]
    drills = []           # (x, y, r, kind, label, net)
    for pad in b.pads:
        raw = FP[b.parts[pad.ref]["fp"]][pad.num]
        if raw["hole"]:
            # slots as their circumscribed... use the half-width for the round part, the long half for the reach
            drills.append((pad.x, pad.y, min(raw["hw"], raw["hh"]) / 2, max(raw["hw"], raw["hh"]) / 2, "pad",
                           f"{pad.ref}.{pad.num}", pad.net, raw, pad))
    for i, v in enumerate(b.vias):
        drills.append((v["c"][0], v["c"][1], v["drill"] / 2, v["drill"] / 2, "via", f"via {v['net']} ({v['c'][0]:.1f}, {v['c'][1]:.1f})",
                       v["net"], None, None))
    worst = []
    for i in range(len(drills)):
        for j in range(i + 1, len(drills)):
            a, c = drills[i], drills[j]
            if a[5].split(".")[0] == c[5].split(".")[0] and a[4] == c[4] == "pad":
                continue          # pins of one part: the footprint's own spacing
            dd = math.hypot(a[0] - c[0], a[1] - c[1])
            if dd > 6:
                continue
            gap = dd - a[3] - c[3]          # conservative: slots by their long half-length
            # JLCPCB: 0.45 between pad holes, 0.2 for vias (taken for a via beside a pad hole too)
            need = JLC_HOLE_HOLE_VIA if "via" in (a[4], c[4]) else JLC_HOLE_HOLE_PAD
            if gap < need:
                worst.append((round(gap, 3), a[5], c[5], need))
    worst.sort()
    ck.check(f"{name}: hole-to-hole >= JLCPCB's {JLC_HOLE_HOLE_PAD} (pad holes) / {JLC_HOLE_HOLE_VIA} (vias)", not worst,
             f"{len(worst)} under: {worst[:8]} ({sum(1 for d in drills if d[4] == 'pad')} pad holes, {len(b.vias)} vias)")
    # drill edge to other-net tracks
    near = []
    title = f"{name}: drill edge to another net's track >= JLCPCB's {JLC_PTH_TRACK} mm"
    routed = runs("routed", title, b)
    for x, y, r, R, kind, label, net, raw, pad in (drills if routed else ()):
        for t in b.tracks:
            if t["net"] == net:
                continue
            if not ca._near((x - R, y - R, x + R, y + R), t["bb"], 1.0):
                continue
            if raw is not None and raw["hole"] != "ROUND":      # a slot: its capsule, in the pad's own angle
                s0, s1, rr = ca.Pad("", "", x, y, raw["hw"], raw["hh"], "ELLIPSE", pad.angle, None).axis()
                g = ca.d_seg_seg(s0, s1, t["a"], t["b"]) - rr - t["w"] / 2
            else:
                g = ca.d_point_seg((x, y), t["a"], t["b"]) - t["w"] / 2 - r
            if g < JLC_PTH_TRACK:
                near.append((round(g, 3), label, t["net"]))
    near.sort()
    if routed:
        ck.check(title, not near, f"{len(near)} under: {near[:8]}")
    # pads and pours to the board edge
    x1, y1, x2, y2 = b.outline
    pe = min(min(p.x - p.r - x1, x2 - p.x - p.r, p.y - p.r - y1, y2 - p.y - p.r) for p in b.pads)
    ck.check(f"{name}: pads >= {JLC_EDGE} mm from the routed edge", pe >= JLC_EDGE, f"nearest pad copper {pe:.2f} mm")
    title = f"{name}: pour fill >= {JLC_EDGE} mm from the routed edge"
    if runs("routed", title, b):
        pour_e = min(min(q[0] - x1, x2 - q[0], q[1] - y1, y2 - q[1]) for isl in b.islands for q in isl.outline)
        ck.check(title, pour_e >= JLC_EDGE - 1e-3, f"nearest pour point {pour_e:.2f} mm")

# ================================================================== 3. outlines, mounting holes, hardware
want_holes = sorted((round(front(xf), 2), round(y, 2)) for xf, y in circuit.HOLES_FRONT)
for b in (MB, FB):
    name = b.title.split()[1]
    x1, y1, x2, y2 = b.outline
    ck.check(f"{name}: outline 140.4 x 108.0 mm at the origin", abs(x2 - x1 - BOARD_W) < 0.01 and abs(y2 - y1 - BOARD_H) < 0.01
             and abs(x1) < 0.01 and abs(y1) < 0.01, f"got ({x1:.2f}, {y1:.2f})-({x2:.2f}, {y2:.2f})")
    got = sorted((round(hx, 2), round(hy, 2)) for hx, hy, hd in b.holes)
    ck.check(f"{name}: four 3.2 mm holes", len(b.holes) == 4 and all(abs(hd - 3.2) < 0.01 for _, _, hd in b.holes),
             f"{[(round(hx, 2), round(hy, 2), round(hd, 2)) for hx, hy, hd in b.holes]}")
    ck.check(f"{name}: holes at circuit.HOLES_FRONT (mirrored to the PCB frame, 0.05 mm)",
             len(got) == 4 and all(math.hypot(a[0] - w[0], a[1] - w[1]) < 0.05 for a, w in zip(got, want_holes)),
             f"expected {want_holes}, got {got}")
ck.check("the two boards' holes coincide", sorted((round(h[0], 2), round(h[1], 2)) for h in MB.holes) ==
         sorted((round(h[0], 2), round(h[1], 2)) for h in FB.holes))
# exposed copper of another net under the standoff (gap side) or screw head (outer side)
for b, gap_bottom in ((MB, True), (FB, False)):
    name = b.title.split()[1]
    ground = "GND" if b is MB else "GND_F"
    under = []
    for hx, hy, hd in b.holes:
        for p in b.pads:
            R = max(M3_HEAD_R, M3_STANDOFF_R)
            d = p.d_point((hx, hy))
            if d < R + 0.2:
                under.append(f"{p.ref}.{p.num} ({p.net}) {d:.2f} mm from the hole centre")
        for v in b.vias:
            d = math.hypot(v["c"][0] - hx, v["c"][1] - hy) - v["r"]
            if d < max(M3_HEAD_R, M3_STANDOFF_R) and v["net"] != ground:
                under.append(f"via {v['net']} {d:.2f} mm")
    ck.check(f"{name}: no pad, and no via but ground, under an M3 standoff (hex 5.5 AF, r {M3_STANDOFF_R:.2f}) or "
             f"button head (r {M3_HEAD_R:.2f}) + 0.2", not under, f"{under} ({len(b.pads)} pads, {len(b.vias)} vias on the board)")

# ================================================================== 4. panel parts on the routed faceplate
pos_bad, rot_bad = [], []
for ref, (xf, y, _) in circuit.PLACEMENT.items():
    pl = FB.parts[ref]
    if math.hypot(front(pl["x"]) - xf, pl["y"] - y) > 0.05 or not pl["bottom"]:
        pos_bad.append(f"{ref}: ({front(pl['x']):.3f}, {pl['y']:.3f}){' top' if not pl['bottom'] else ''} vs ({xf}, {y})")
    rel = {n: (pl["x"] - p.x, p.y - pl["y"]) for n, p in pl["pads"].items()}     # front view, from the origin
    if ref.startswith("J"):
        ok = abs(rel["1"][0] - rel["3"][0]) < 0.01 and rel["1"][1] > rel["3"][1]
        what = "sleeve above tip"
    elif ref.startswith("RV"):
        ok = rel["1"][1] < 0 and abs(rel["1"][1] - rel["3"][1]) < 0.01 and rel["1"][0] < rel["3"][0]
        what = "pins below the shaft, pin 1 left"
    else:
        # design.md only asks for the LED pins (5 anode, 6 cathode: circuit.py) along x; which way round is free
        ok = abs(rel["5"][1] - rel["6"][1]) < 0.01 and abs(rel["5"][0] - rel["6"][0]) > 1.0
        what = "LED pins along x"
    if not ok:
        rot_bad.append(f"{ref} ({what}): {pl['angle']}")
ck.check("faceplate: every panel part at circuit.PLACEMENT (0.05 mm), on the bottom (panel) side", not pos_bad,
         f"{len(pos_bad)} off: {pos_bad[:6]}")
ck.check("faceplate: rotations per design.md (pots pins down + pin 1 left, jacks sleeve up, buttons LED pins along x)",
         not rot_bad, f"{rot_bad}")
# the mechanical centre of each part from its pads, against the routed panel's holes (panel PCB frame =
# front view board mm + ((PANEL_W - BOARD_W) / 2, (PANEL_H - BOARD_H) / 2))
panel_holes = [(p["path"][0][1] * MIL, p["path"][0][2] * MIL, 2 * p["path"][0][3] * MIL)
               for h, p in PANEL["recs"] if h["type"] == "FILL" and p["layerId"] == 12 and p["path"][0][0] == "CIRCLE"]
dx0, dy0 = (circuit.PANEL_W - BOARD_W) / 2, (circuit.PANEL_H - BOARD_H) / 2
HOLE_FOR = {"J": 6.5, "R": 7.5, "S": 6.5}
mis = []
for ref in circuit.PLACEMENT:
    pl = FB.parts[ref]
    P = {n: (front(p.x), p.y) for n, p in pl["pads"].items()}
    if ref.startswith("J"):
        s, t = P["1"], P["3"]
        d = math.hypot(t[0] - s[0], t[1] - s[1])
        c = (s[0] + (t[0] - s[0]) / d * THONK_SLEEVE, s[1] + (t[1] - s[1]) / d * THONK_SLEEVE)
    elif ref.startswith("RV"):
        a, z = P["1"], P["3"]           # pin row; the shaft 7.5 mm above it (Alpha / KiCad RD901F, design.md)
        c = ((a[0] + z[0]) / 2, (a[1] + z[1]) / 2 + 7.5)
    else:
        c = (sum(P[n][0] for n in "1234") / 4, sum(P[n][1] for n in "1234") / 4)
    cp = (c[0] + dx0, c[1] + dy0)
    hx, hy, hd = min(panel_holes, key=lambda h: math.hypot(h[0] - cp[0], h[1] - cp[1]))
    off = math.hypot(hx - cp[0], hy - cp[1])
    if off > 0.1 or abs(hd - HOLE_FOR[ref[0]]) > 0.01:
        mis.append(f"{ref}: {off:.2f} mm from the {hd:.1f} mm hole")
ck.check("panel: every shaft / barrel / button centre (from the routed pads) under its panel hole (0.1 mm), "
         "7.5 mm for pots, 6.5 for jacks and buttons", not mis, f"{mis}")
hdr_bad = []
for ref, (xf, y, a) in circuit.HEADERS_FRONT.items():
    pl = FB.parts[circuit.fb_ref(ref)]
    n = len(pl["pads"])
    mid = ((pl["pads"]["1"].x + pl["pads"][str(n)].x) / 2, (pl["pads"]["1"].y + pl["pads"][str(n)].y) / 2)
    top = pl["pads"]["1"].y > pl["pads"][str(n)].y
    if math.hypot(front(mid[0]) - xf, mid[1] - y) > 0.05 or not top or pl["bottom"]:
        hdr_bad.append(f"{ref}: mid ({front(mid[0]):.2f}, {mid[1]:.2f}) vs ({xf}, {y}), pin 1 on top {top}")
ck.check("faceplate: male headers at circuit.HEADERS_FRONT, pin 1 at the top, on the top (rear) side", not hdr_bad, f"{hdr_bad}")

# ================================================================== 5. silkscreen
KIND = {p.ref: p.kind for p in circuit.all_parts()}
LEGEND = re.compile(r"^(\S+): ((?:[A-Z]+\d+ ?)+)$")


def strings(title):
    out = []
    for h, p in DOC[title]["recs"]:
        if h["type"] == "STRING" and p.get("layerId") in (3, 4):
            out.append(p)
    return out


def lcheck(b, name, ok, detail=""):
    """A value-label check: run on a board that has its value labels, skipped (and gated) on one that has none."""
    if runs("labels", name, b):
        ck.check(name, ok, detail)


for b in (MB, FB):
    name = b.title.split()[1]
    vals = VALUES[name]
    labelled = {r for r in vals if r in b.parts}
    seen, seen_leg = collections.Counter(), collections.Counter()
    traps, ties, wrong_side, wrong_text, small, on_pad, thin = [], [], [], [], [], [], []
    texts = set(vals.values())
    for p in strings(b.title):
        txt = p["text"]
        bottom = p["layerId"] == 4
        rect = vl.text_box(p["x"] * MIL, p["y"] * MIL, txt, p["fontSize"], p.get("mirror", False))
        m = LEGEND.match(txt)
        if m:
            refs = m.group(2).split()
            for r in refs:
                seen_leg[r] += 1
                if vals.get(r) != m.group(1):
                    wrong_text.append(f"legend '{txt}': {r} is {vals.get(r)}")
            continue
        if txt not in texts:
            if re.fullmatch(r"[AB]?\d+[RkKMpnuµ]\d*|1N\d+", txt):
                wrong_text.append(f"'{txt}' looks like a value but is none of this board's values")
            continue                                   # a title or other text, not a value label
        if bool(p.get("mirror")) != bottom:
            wrong_side.append(f"'{txt}' mirror {p.get('mirror')} on layer {p['layerId']}")
        if p["fontSize"] * MIL < JLC_SILK_H - 1e-6:
            small.append(f"{txt} {p['fontSize']} mil")
        if p.get("strokeWidth", 6) * MIL < JLC_SILK_W - 1e-6:
            thin.append(txt)
        for pad in b.pads:
            if vl.circle_hits(rect, (pad.x, pad.y), pad.r + JLC_PAD_SILK - 0.001):
                on_pad.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f}) on {pad.ref}.{pad.num}")
                break
        cands = sorted(((vl.rect_dist(rect, vl.extent(b.parts[r])), r) for r in labelled
                        if b.parts[r]["bottom"] == bottom))
        same = [c for c in cands if vals[c[1]] == txt]
        other = [c for c in cands if vals[c[1]] != txt]
        if not same:
            wrong_text.append(f"'{txt}' near no part of that value")
            continue
        own_d, own = same[0]
        seen[own] += 1
        if b.parts[own]["bottom"] != bottom:
            wrong_side.append(own)
        if other and other[0][0] < own_d - 0.02:
            traps.append(f"'{txt}' at ({rect[0]:.1f}, {rect[1]:.1f}): {other[0][1]} ({vals[other[0][1]]}) {other[0][0]:.2f} mm "
                         f"nearer than {own} {own_d:.2f} mm")
        elif other and other[0][0] < own_d + 0.3:
            ties.append(f"'{txt}' {own} {own_d:.2f} / {other[0][1]} ({vals[other[0][1]]}) {other[0][0]:.2f}")
    lcheck(b, f"{name}: no value label sits nearer a part of a different value (assembly trap)", not traps,
             f"{len(traps)}: {traps}")
    lcheck(b, f"{name}: no value label within 0.3 mm of a tie with a part of a different value", not ties,
             f"{len(ties)}: {ties[:10]}")
    lcheck(b, f"{name}: every label states a value circuit.py gives the part", not wrong_text, f"{wrong_text}")
    # coverage: a label of the part's value within 3 mm of it (several parts of one value may share the
    # nearest label, which is harmless), or a legend line naming it
    boxes = [(p["text"], p["layerId"] == 4, vl.text_box(p["x"] * MIL, p["y"] * MIL, p["text"], p["fontSize"], p.get("mirror", False)))
             for p in strings(b.title)]
    missing = []
    for r in sorted(labelled):
        if seen_leg[r]:
            continue
        pl = b.parts[r]
        d = min((vl.rect_dist(rect, vl.extent(pl)) for t, bot, rect in boxes if t == vals[r] and bot == pl["bottom"]), default=99)
        if d > 3.0:
            missing.append(f"{r} ({vals[r]}, nearest {d:.1f} mm)")
    lcheck(b, f"{name}: every R / C / diode / pot has a value label within 3 mm, or a legend line", not missing,
             f"{len(labelled)} parts, unlabelled: {missing}")
    lcheck(b, f"{name}: value labels at least JLCPCB's {JLC_SILK_H} mm (40 mil) text height", not small,
             f"{len(small)} smaller: {collections.Counter(s.split()[-2] + ' mil' for s in small)}")
    lcheck(b, f"{name}: value labels' stroke >= {JLC_SILK_W} mm", not thin, f"{thin[:5]}")
    lcheck(b, f"{name}: each label on its part's side, mirrored on the bottom so it reads from that side", not wrong_side,
             f"{wrong_side[:5]}")
    lcheck(b, f"{name}: value labels >= {JLC_PAD_SILK} mm off every pad", not on_pad, f"{on_pad[:5]}")
    # designators
    des = {}
    for h, p in DOC[b.title]["recs"]:
        if h["type"] == "ATTR" and p.get("key") == "Designator" and p.get("parentId"):
            des[p["value"]] = p
    hidden = sorted(r for r in b.parts if r not in des or not des[r].get("valueVisible"))
    ck.check(f"{name}: every part's designator is visible on the silk", not hidden, f"hidden or missing: {hidden}")
    dsmall = collections.Counter(round(p["fontSize"]) for r, p in des.items() if r in b.parts and p.get("valueVisible")
                                 and p["fontSize"] * MIL < JLC_SILK_H - 1e-6)
    ck.check(f"{name}: designators at least {JLC_SILK_H} mm tall", not dsmall, f"smaller (mil: count): {dict(dsmall)}")

# polarity marks in the footprints: the mark must sit on the pad the circuit wants marked
def silk_items(title):
    out = []
    for h, p in FPDOC[title]["recs"]:
        if h["type"] in ("POLY", "FILL") and p.get("layerId") == 3:
            pts = []
            path = p["path"]
            for pa in (path if path and isinstance(path[0], list) else [path]):
                pts += ca.flatten_path(pa, MIL) if not (pa and pa[0] == "CIRCLE") else [(pa[1] * MIL, pa[2] * MIL)]
            out.append((h["type"], pts, path))
    return out


def nearer(pt, title, a, b):
    pa, pb = FP[title][a], FP[title][b]
    return math.hypot(pt[0] - pa["x"], pt[1] - pa["y"]) < math.hypot(pt[0] - pb["x"], pt[1] - pb["y"])


# diodes: the band is the short silk line across the body nearest one pad; the cathode is the pad the
# circuit puts on the more positive end in reverse (D901: P12_D, D902: N12_IN, D903: POR, D904: +12V)
CATHODE = {"D901": "P12_D", "D902": "N12_IN", "D903": "POR", "D904": "+12V"}
for ref, cat in CATHODE.items():
    pl = MB.parts[ref]
    title = pl["fp"]
    pad_c = next(n for n, v in pl["nets"].items() if v == cat)
    pad_a = next(n for n in pl["nets"] if n != pad_c)
    bands = [pts for t, pts, raw in silk_items(title) if t == "POLY" and len(pts) == 2 and abs(pts[0][0] - pts[1][0]) < 0.01
             and abs(pts[0][1] - pts[1][1]) > 1.5 and abs(pts[0][0]) > 0.5]
    xs = [round(pts[0][0], 2) for pts in bands]
    inner = [pts for pts in bands if -round(pts[0][0], 2) not in xs]     # the body outline comes in mirrored pairs
    ok = bool(inner) and all(nearer(pts[0], title, pad_c, pad_a) for pts in inner)
    ck.check(f"{ref}: the silk cathode band is at the pad on {cat} (pad {pad_c})", ok,
             f"band x {[round(p[0][0], 2) for p in inner]}, pad {pad_c} at x {FP[title][pad_c]['x']:.2f}")
# the series protection diodes conduct in normal use: anode on the more positive side
ck.check("D901 / D902 forward in normal use (D901 anode P12_IN -> P12_D, D902 anode N12_D -> N12_IN at the header)",
         MB.parts["D901"]["nets"] == {"1": "P12_D", "2": "P12_IN"} and MB.parts["D902"]["nets"] == {"1": "N12_IN", "2": "N12_D"},
         f"D901 {MB.parts['D901']['nets']}, D902 {MB.parts['D902']['nets']} (pad 1 = cathode, the banded end)")
for ref, plus, minus in (("C904", "+12V", "GND"), ("C905", "GND", "-12V")):
    pl = MB.parts[ref]
    title = pl["fp"]
    pp = next(n for n, v in pl["nets"].items() if v == plus)
    pm = next(n for n, v in pl["nets"].items() if v == minus)
    fills = [pts for t, pts, raw in silk_items(title) if t == "FILL"]
    mark = None
    if fills:
        xs = [q[0] for pts in fills for q in pts]
        ys = [q[1] for pts in fills for q in pts]
        mark = (sum(xs) / len(xs), sum(ys) / len(ys))          # the "+" sign's centre
    ck.check(f"{ref}: the silk '+' marks the pad on {plus} (pad {pp}), the more positive rail",
             mark is not None and nearer(mark, title, pp, pm),
             f"'+' at {None if mark is None else (round(mark[0], 2), round(mark[1], 2))}, pad {pp} at x {FP[title][pp]['x']:.2f}")
for title in ("DIP-14-W7.62-P2.54", "DIP-16-W7.62-P2.54"):
    dots = [raw for t, pts, raw in silk_items(title) if t == "POLY" and raw and raw[0] == "CIRCLE"]
    n = len(FP[title])
    ok = bool(dots) and all(nearer((d[1] * MIL, d[2] * MIL), title, "1", str(n)) and
                            nearer((d[1] * MIL, d[2] * MIL), title, "1", str(n // 2)) for d in dots)
    ck.check(f"{title}: a pin-1 dot on the silk, nearest pin 1", ok, f"dots {[(round(d[1] * MIL, 2), round(d[2] * MIL, 2)) for d in dots]}")
# J18: pin 1 carries -12 V, and the footprint marks pin 1 (a triangle outside the shroud)
pl = MB.parts["J18"]
ck.check("J18: pins 1-2 on N12_IN (the -12 V red stripe end)", pl["nets"].get("1") == "N12_IN" and pl["nets"].get("2") == "N12_IN",
         f"pin 1 {pl['nets'].get('1')}, pin 2 {pl['nets'].get('2')}")
tri = [pts for t, pts, raw in silk_items("IDC-TH_16P-P2.54_C3406") if t == "POLY" and len(pts) == 2 and
       abs(pts[0][0] - pts[1][0]) > 0.3 and abs(pts[0][1] - pts[1][1]) > 0.3]
mid = (sum(q[0] for pts in tri for q in pts) / max(1, 2 * len(tri)), sum(q[1] for pts in tri for q in pts) / max(1, 2 * len(tri)))
ck.check("J18 footprint: the pin-1 triangle is nearest pin 1 (not pin 15 / 16)", bool(tri) and
         nearer(mid, "IDC-TH_16P-P2.54_C3406", "1", "15") and nearer(mid, "IDC-TH_16P-P2.54_C3406", "1", "2"),
         f"triangle at ({mid[0]:.2f}, {mid[1]:.2f})")
pin15 = MB.parts["J18"]["pads"]["15"]
ck.check("J18: pin 1 (-12 V) at the bottom, front view (design.md 'pin 1 (-12 V) at the bottom')",
         pl["pads"]["1"].y < pin15.y - 5, f"pin 1 y {pl['pads']['1'].y:.2f}, pin 15 y {pin15.y:.2f}")
neg = [p["text"] for p in strings(MB.title) if re.search(r"-12|−12|RED|STRIPE", p["text"], re.I)]
j18 = MB.parts["J18"]["pads"]["1"]
near_neg = [p["text"] for p in strings(MB.title) if re.search(r"-12|−12|RED|STRIPE", p["text"], re.I)
            and math.hypot(p["x"] * MIL - j18.x, p["y"] * MIL - j18.y) < 15]
# value_labels.py puts the '-12V' beside pin 1 together with the value labels, so it waits for them too
lcheck(MB, "main: a '-12V' / 'red stripe' word on the silk beside J18's pin 1 (the shroud key alone does not say which end)",
       bool(near_neg), f"-12 V texts on the board: {neg}, near pin 1: {near_neg}")

# ================================================================== 6. bodies
def rect_poly(cx, cy, L, W, ang):
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = ca.rot(sx * L / 2, sy * W / 2, ang)
        out.append((cx + dx, cy + dy))
    return out


def real_body(ref, pl):
    """('circle', (cx, cy), r) or ('poly', corners): the part's real body on its side, max dimensions."""
    fp = pl["fp"]
    P = pl["pads"]
    if fp == "RES-TH-VERTICAL-P2.54":
        return ("circle", (P["1"].x, P["1"].y), BODY_R_STAND_D / 2)
    if fp == "CAP-TH_BD4.8-P2.50-D0.5-FD":
        return ("circle", ((P["1"].x + P["2"].x) / 2, (P["1"].y + P["2"].y) / 2), BODY_CP_D / 2)
    two = {"CAP-TH_L3.0-W2.0-P5.08-D0.7": BODY_FG28, "CAP-TH_L7.6-W3.8-P5.08-D0.51": BODY_SR30,
           "DO-41_BD2.4-L4.7-P8.70-D0.8-RD": BODY_DO41, "DO-35_BD2.0-L4.0-P8.0-D0.5-RD": BODY_DO35,
           "CAP-TH_P2.54-L4.0-W2.5": BODY_C315}
    if fp in two:
        L, W = two[fp]
        a = math.degrees(math.atan2(P["2"].y - P["1"].y, P["2"].x - P["1"].x))
        return ("poly", rect_poly((P["1"].x + P["2"].x) / 2, (P["1"].y + P["2"].y) / 2, L, W, a))
    if fp.startswith("DIP-"):
        n = len(P)
        L, W = {14: BODY_DIP14, 16: BODY_DIP16}[n]
        cx = sum(p.x for p in P.values()) / n
        cy = sum(p.y for p in P.values()) / n
        a = math.degrees(math.atan2(P["2"].y - P["1"].y, P["2"].x - P["1"].x))
        return ("poly", rect_poly(cx, cy, L, W, a))
    x1, y1, x2, y2 = pl["body"]
    return ("poly", [(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def _proj(poly, ax):
    v = [q[0] * ax[0] + q[1] * ax[1] for q in poly]
    return min(v), max(v)


def separation(a, b):
    """Positive: gap (approximate for poly-poly: the SAT separation); negative: overlap depth."""
    if a[0] == "circle" and b[0] == "circle":
        return math.hypot(a[1][0] - b[1][0], a[1][1] - b[1][1]) - a[2] - b[2]
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


bodies = {ref: real_body(ref, pl) for ref, pl in MB.parts.items() if not pl["bottom"]}
hits = []
refs = sorted(bodies)
for i, ra in enumerate(refs):
    for rb in refs[i + 1:]:
        a, b = bodies[ra], bodies[rb]
        ca_ = a[1] if a[0] == "circle" else a[1][0]
        cb_ = b[1] if b[0] == "circle" else b[1][0]
        if math.hypot(ca_[0] - cb_[0], ca_[1] - cb_[1]) > 25:
            continue
        s = separation(a, b)
        if s < 0:
            hits.append((round(s, 2), ra, rb))
hits.sort()
ck.check("main top: no two real bodies (datasheet max sizes) overlap", not hits, f"{len(hits)} overlaps (mm, a, b): {hits[:12]}")
# (The R805 / C903 pair, a 0.10 mm footprint-outline overlap on the 2026-11-02 placement, is gone: the 2026-11-15
# placement puts them 15 mm apart, and the overlap check above covers every pair.)
# DIP sockets (bom.md: every DIP-14 and DIP-16 chip in a socket): the socket's frame against its neighbours, a
# neighbouring socketed chip by its own socket frame
sockets = {}
for ref, pl in MB.parts.items():
    if pl["fp"] not in SOCKETS or pl["bottom"]:
        continue
    P = pl["pads"]
    n = len(P)
    cx, cy = sum(p.x for p in P.values()) / n, sum(p.y for p in P.values()) / n
    a = math.degrees(math.atan2(P["2"].y - P["1"].y, P["2"].x - P["1"].x))
    sockets[ref] = ("poly", rect_poly(cx, cy, *SOCKETS[pl["fp"]], a))
for fp, (L, W) in SOCKETS.items():
    sock_hits = []
    mine = [r for r in sockets if MB.parts[r]["fp"] == fp]
    for ref in mine:
        for rb, bb in bodies.items():
            if rb == ref:
                continue
            s = separation(sockets[ref], sockets.get(rb, bb))
            if s < 0:
                sock_hits.append((round(s, 2), ref, rb))
    ck.check(f"main top: an assumed {L} x {W} {fp[:6]} socket clears its neighbours (their real bodies, or their own "
             f"sockets)", bool(mine) and not sock_hits, f"{len(mine)} sockets, {len(sock_hits)} overlaps: {sorted(sock_hits)[:10]}")
# The M3 screws go in from the main board's top (rear), so their heads sit on that side among the parts: a button
# head (ISO 7380, dk 5.7) must clear every top body and socket frame. (Section 3 checks the pads under the head and
# the standoff; this is the plastic.)
head_hits = []
for hx, hy, hd in MB.holes:
    for ref, bb in bodies.items():
        s = separation(("circle", (hx, hy), M3_HEAD_R), sockets.get(ref, bb))
        if s < 0:
            head_hits.append((round(s, 2), ref, f"hole ({hx:.2f}, {hy:.2f})"))
ck.check(f"main top: no body or socket frame under an M3 button head (r {M3_HEAD_R:.2f})", not head_hits,
         f"{len(head_hits)} overlaps (mm, part, hole): {sorted(head_hits)}")
# The female sockets H1-H9 stand on the bottom; their solder joints come through on the top, where the CD4053B
# strips sit between them (design.md: 'in the 11 mm between two header sockets'). A socket frame or a body that
# sits on a joint stands crooked: every top-side outline (socket frames for the socketed chips) must clear the
# bottom parts' pads (their copper, the joint's footprint).
joints = [p for p in MB.pads if MB.parts[p.ref]["bottom"]]
on_joint = []
for ref, bb in bodies.items():
    shape = sockets.get(ref, bb)
    for p in joints:
        s = separation(shape, ("circle", (p.x, p.y), p.r))
        if s < 0:
            on_joint.append((round(s, 2), ref, f"{p.ref}.{p.num}"))
ck.check("main top: no body or socket frame over a bottom socket's solder joint", not on_joint,
         f"{len(joints)} joints; {len(on_joint)} overlaps (mm, top part, joint): {sorted(on_joint)[:10]}")
# design.md, Power: '100 n per TL074 per rail beside pins 4 and 11; 100 n per CMOS chip beside its VDD pin (14; 16
# on the CD4053Bs)'. 'Beside': the cap's pad on that rail within 5 mm of the supply pin (a house figure: one cap
# length, no track longer than the chip is wide).
DECOUPLE_MAX = 5.0
far_caps = []
for p in circuit.main_board_parts():
    if p.kind != "C" or p.value != "100n" or not p.label.endswith((" VDD", " +12 V", " -12 V")):
        continue
    u = p.label.split()[0]
    chip = MB.parts[u]
    rail = "-12V" if p.label.endswith("-12 V") else "+12V"
    pin = {"TL074": "11" if rail == "-12V" else "4", "CD4053": "16"}.get(KIND[u], "14")
    cpad = next(n for n, v in MB.parts[p.ref]["nets"].items() if v == rail)
    d = math.hypot(MB.parts[p.ref]["pads"][cpad].x - chip["pads"][pin].x, MB.parts[p.ref]["pads"][cpad].y - chip["pads"][pin].y)
    if d > DECOUPLE_MAX or chip["pads"][pin].net != rail:
        far_caps.append(f"{p.ref} ({u} pin {pin} {rail}) {d:.1f} mm")
n_dec = sum(1 for p in circuit.main_board_parts() if p.kind == "C" and p.value == "100n"
            and p.label.endswith((" VDD", " +12 V", " -12 V")))
ck.check(f"main: every chip's 100 n within {DECOUPLE_MAX} mm of its supply pin (design.md)", n_dec == 22 and not far_caps,
         f"{n_dec} decoupling caps (4 TL074 x 2 + 6 CD40xx + 8 CD4053B = 22); further: {far_caps}")
# stacking gap
mb_bottom = sorted(r for r, pl in MB.parts.items() if pl["bottom"])
fb_top = sorted(r for r, pl in FB.parts.items() if not pl["bottom"])
ck.check("main board bottom (gap side): only the nine female sockets", mb_bottom == sorted(f"H{i}" for i in range(1, 10)), f"{mb_bottom}")
ck.check("faceplate top (gap side): only the nine male headers", fb_top == sorted(f"HF{i}" for i in range(1, 10)), f"{fb_top}")
mated = MALE_PLASTIC + FEMALE_BODY
ck.check("stacking gap (mated male plastic + female body) leaves room for the lead stubs of both boards",
         mated > 2 * LEAD_PROTRUDE + 1.0, f"gap {mated:.1f} mm, stubs {2 * LEAD_PROTRUDE:.1f} mm")
design = open(harness.os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
bom = open(harness.os.path.join(harness.MODULE, "docs", "bom.md"), encoding="utf-8").read()
# (verifier) the first version compared two constants here (6.0 <= 8.5 - 0.5), which tested nothing about the
# design; tie the stacking model to what the BOM actually orders instead
m = re.search(r"Female header, 2\.54 mm, (\d+(?:\.\d+)?) mm tall", bom)
ck.check("bom.md orders the female header height the stacking model uses (8.5 mm), deep enough for the 6 mm male pin",
         m is not None and abs(float(m.group(1)) - FEMALE_BODY) < 0.01 and MALE_PIN_ABOVE <= float(m.group(1)) - 0.5,
         f"bom.md female header {m and m.group(1)} mm, model {FEMALE_BODY}, male pin {MALE_PIN_ABOVE}")
m = re.search(r"about (\d+(?:\.\d+)?) mm with standard", design)
ck.check("design.md's standoff length equals the mated header height (female 8.5 + male plastic 2.5)",
         m is not None and abs(float(m.group(1)) - mated) <= 0.5, f"design.md 'about {m and m.group(1)} mm', mated {mated:.1f} mm")
m = re.search(r"M3 standoff, female-female, (?:about )?(\d+(?:\.\d+)?) mm", bom)
ck.check("bom.md's standoff length equals the mated header height", m is not None and abs(float(m.group(1)) - mated) <= 0.5,
         f"bom.md '{m and m.group(1)} mm', mated {mated:.1f} mm")
# bom.md's rows describe one unit and the Qty column multiplies it; the screws have a line of their own
m = re.search(r"\| (\d+) \| M3 standoff, female-female", bom)
sc = re.search(r"\| (\d+) \| M3 ?[×x] ?[\d.]+ ?mm[^|]*screw", bom)
ck.check("bom.md: two M3 screws per female-female standoff, one standoff per mounting hole",
         m is not None and sc is not None and int(sc.group(1)) >= 2 * int(m.group(1)) and int(m.group(1)) == len(circuit.HOLES_FRONT),
         f"standoffs {m and m.group(1)}, screws {sc and sc.group(1)}, holes {len(circuit.HOLES_FRONT)}")

# ================================================================== 7. pour islands
SMALL = 30.0     # mm2: an island this small is a sliver, not a ground plane
# A pour piece under 1 mm2 that is nowhere wider than 0.25 mm: a house judgement (thinner than the board's
# 0.3 mm signal tracks, so a loose wedge that can lift), NOT a fab rule: JLCPCB's minimum feature is 0.10 mm.
SLIVER_W = 0.25


def inscribed_r(poly, step=0.01):
    import numpy as np
    P = np.array(poly, float)
    x0, y0 = P.min(0)
    x1, y1 = P.max(0)
    gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    pts = np.stack([gx.ravel(), gy.ravel()], 1)
    A, B = P, np.roll(P, -1, 0)
    inside = np.zeros(len(pts), bool)
    for (ax, ay), (bx, by) in zip(A, B):              # even-odd ray cast
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

for b in (MB, FB):
    name = b.title.split()[1]
    t_dead = f"{name}: no dead pour islands (copper joined to nothing), any size"
    t_sliver = f"{name}: no pour piece under 1 mm2 narrower than {SLIVER_W} mm at its widest, hanging on a spoke"
    if not runs("routed", t_dead, b):
        skip("routed", t_sliver, b)
        continue
    groups, _ = b.connectivity()
    key_of = {}
    for i, isl in enumerate(b.islands):
        key_of[i] = ("island", i)
    dead, held, slivers = [], [], []

    def far(sp):       # copper_audit's rule: the spoke's far end, 0.15 mm on
        dx, dy = sp[1][0] - sp[0][0], sp[1][1] - sp[0][1]
        d = math.hypot(dx, dy) or 1
        return sp[1][0] + dx / d * 0.15, sp[1][1] + dy / d * 0.15

    for i, isl in enumerate(b.islands):
        grp = next((g for g in groups.get(isl.net, {}).values() if ("island", i) in g), set())
        if isl.area >= SMALL:
            if not any(k[0] == "pad" for k in grp):     # (verifier) big islands can be dead too: check every one
                dead.append(f"{isl.net} layer {isl.layer} {isl.area:.1f} mm2 at ({isl.bb[0]:.1f}, {isl.bb[1]:.1f})")
            continue
        vias =[v for v in b.vias if v["net"] == isl.net and isl.contains(v["c"])]
        spokes = [s for s in b.spokes if s[2] == isl.layer and s[3] == isl.net and isl.contains(far(s))]
        tracks = [t for t in b.tracks if t["net"] == isl.net and t["layer"] == isl.layer and (isl.contains(t["a"]) or isl.contains(t["b"]))]
        # group membership: does the island share a root with any pad?
        grp = next((g for g in groups.get(isl.net, {}).values() if ("island", i) in g), set())
        pads = [k for k in grp if k[0] == "pad"]
        desc = (f"{isl.net} layer {isl.layer} {isl.area:.1f} mm2 at ({isl.bb[0]:.1f}, {isl.bb[1]:.1f})-({isl.bb[2]:.1f}, "
                f"{isl.bb[3]:.1f}): {len(vias)} vias, {len(spokes)} spokes, {len(tracks)} track ends inside")
        (held if pads else dead).append(desc)
        # (verifier) the widest point of the piece: twice the largest inscribed circle, from a 0.01 mm grid of
        # interior points and their distance to the outline. The first version used 2 * area / perimeter, a mean
        # that halves a wedge's width (it reported the 0.22 mm wedge as 0.13 mm).
        if isl.area < 1.0:
            width = 2 * inscribed_r(isl.outline)
            if width < SLIVER_W:
                slivers.append(f"{isl.net} layer {isl.layer} {isl.area:.2f} mm2, at most {width:.2f} mm wide, at "
                               f"({isl.bb[0]:.1f}, {isl.bb[1]:.1f}), held by {len(spokes)} spoke(s)")
    ck.check(t_dead, bool(b.islands) and not dead, f"{len(b.islands)} islands; dead: {dead}")
    print(f"      {name}: small islands held to their net: {held}")
    ck.check(t_sliver, not slivers, f"{slivers}")

# ================================================================== 8. gates: what the main board cannot be checked for yet
for gate, what in (("routed", "routed (tracks, vias, pours)"), ("labels", "value labels placed (value_labels.py)")):
    for b in (MB, FB):
        name = b.title.split()[1]
        mine = [n for n in SKIPPED[gate] if n.lower().startswith(name.lower() + ":")]
        ok = (COPPER if gate == "routed" else LABELS)[b.title] and not mine
        ck.check(f"{name}: {what}", ok,
                 f"{b.title} in StereoMixer-routed.epro2: {len(b.tracks)} tracks, {len(b.vias)} vias, "
                 f"{len(b.islands)} pour islands, value labels {'yes' if LABELS[b.title] else 'none'}; "
                 f"{len(mine)} checks skipped until it is: {mine}")

ck.done()
