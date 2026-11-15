"""Power group: the stereo mixer's power entry, current budget, ratings,
decoupling and what happens when a rail is missing.

What it checks
  * J18 against the Doepfer A-100 16-pin bus, in circuit.py and in the
    footprint StereoMixer-routed.epro2 actually uses: pin -> net, the pad
    pitch and row spacing measured from the pads, the pin-1 triangle and the
    key notch in the footprint's silkscreen, a -12 V / stripe label on the
    board, pins 11-16 (+5 V, CV, Gate) touching no copper.
  * D901 / D902 / D904 (1N5819), D903 (BAT85): the cathode taken from the
    symbol's pin names AND from the band on the footprint's silkscreen;
    conduction with a correct cable, blocking with a reversed one; where the
    bus supplies land with a reversed cable.
  * C904 / C905 polarity from the footprint's "+" mark.
  * Rail voltages at the chips at min / typ / max load (1N5819 VF + 10 R).
  * The current budget per rail, typ and worst case, against design.md:
    16 TL074 amplifiers, 14 CMOS chips (2 CD4093B, 4 CD4013B, 8 CD4053B
    mute switches), the pull-ups, and per muted channel its button LED
    (CD4013B Q -> 1k5 -> LED).
  * Ratings: 10 R dissipation (normal and with a short downstream), the
    1N5819's current and reverse voltage, capacitor voltages in the BOM,
    the 10 R / 10 uF corner, power track widths.
  * Decoupling: a 100 n per TL074 rail and per CMOS chip (pin 14, pin 16 on
    the CD4053Bs) in circuit.py, and its track path in the routed copper
    (none to read while the routed master's main board is placed only).
  * Faults: one rail missing, power-off: what the op-amps and the CMOS chips
    see (supply reversed, inputs outside their rails), and with +12 V
    missing the CD4053Bs' signal pins, which sit at 0 V above their VDD.

Run from stereo-mixer/hardware/tests:  python test_power.py
Read only: imports circuit.py and copper_audit.py, opens the routed export.
"""
import csv
import math
import os
import re

import harness

ck = harness.Checks("power")
circuit = harness.load("circuit")
ca = harness.load("copper_audit")
MIL = ca.MIL

# ----------------------------------------------------------------- datasheet constants
# Doepfer A-100 bus (doepfer.de/a100_man/a100t_e.htm, its pinout image a100b_e.gif, read 2026-11-13): 16-pin
# 2x8 IDC at 2.54 mm (0.1"), pin 1 = red stripe; pairs from the stripe -12 V, GND, GND, GND, +12 V, +5 V, CV,
# Gate. Until 2026-11-14 this table had GND on 3-10 and +12 V on 11-12 (the design's own error, so it passed).
DOEPFER = {1: "-12V", 2: "-12V", **{n: "GND" for n in range(3, 9)}, 9: "+12V", 10: "+12V",
           11: "+5V", 12: "+5V", 13: "CV", 14: "CV", 15: "GATE", 16: "GATE"}
PITCH = 2.54                       # mm, IDC 0.1" grid, both along the row and between the rows
V_RAIL = 12.0                      # nominal bus rail (V)

# TI TL07x datasheet SLOS080W (rev. July 2025), 5.8 'DC for TL07xC': IQ per amplifier, VO = 0, no load, +-15 V,
# 25 C: 1.4 mA typ, 2.5 mA max (verified). The new-die TL074H: 0.94 mA typ, 1.13 mA max (same document).
# SLOS080W abs max (new die): inputs (VCC-) - 0.5 ... (VCC+) + 0.5 V, else limit input current to 10 mA.
TL074_IQ_TYP, TL074_IQ_MAX = 1.4e-3, 2.5e-3
# SLOS080W 5.1 note (2), verified: "Input pins are diode-clamped to both power-supply rails on all new die";
# inputs more than 0.5 V beyond the rails are allowed if their current is limited to 10 mA. The note covers the
# new die only; the old-die rows in the same table give (VCC-) - 0.3 V with no current note (uncertain which
# die a plain TL074 ships with, see SLOS080W 9.1.1).
TL074_IIN_MAX = 10e-3
# TI SLOS080W: VOM at RL = 10k, +-15 V: +-13.5 V typ, +-12 V min -> headroom 1.5 V typ, 3 V worst (verified).
TL074_HEAD_TYP, TL074_HEAD_MIN = 1.5, 3.0
# TI CD4013B SCHS023E: quiescent IDD max 4 uA at VDD = 15 V, 25 C (verified); CD4093B (SCHS115) taken the same.
CMOS_IDD_MAX = 4e-6
# TI CD4013B SCHS023E abs max: VDD -0.5 ... +20 V; inputs -0.5 ... VDD + 0.5 V; DC input current +-10 mA (verified).
CMOS_VDD_MIN, CMOS_VIN_MARGIN, CMOS_IIN_MAX = -0.5, 0.5, 10e-3
# TI CD4013B SCHS023E IOH (source) at VDD = 10 V, VO = 9.5 V: 1.3 mA min, 2.6 mA typ (25 C) -> Q output resistance
# about 0.5 V / 2.6 mA = 190 R typ, 0.5 / 1.3 = 385 R worst. 0 R bounds the LED current from above.
Q_R_TYP, Q_R_MAX = 190.0, 385.0
# TI CD4053B SCHS047O (rev. O, May 2026), read from `pdftotext -raw` (the -layout table is garbled):
# quiescent IDD (VIS = VEE = VSS = 0) 17 / 18 / 18 uA typ and 60 uA max at 25 C for VDD 5 / 10 / 15 V; 150 / 300 /
# 600 uA max at 85 C. (Its features list says "0.2 uW typical", which the table's typ contradicts; the table used.)
SW_IDD_TYP, SW_IDD_MAX = 18e-6, 60e-6
SW_IDD_MAX85 = {5: 150e-6, 10: 300e-6, 15: 600e-6}
# SCHS047O abs max: supply (VDD to VSS) -0.5 ... 20 V; DC input voltage -0.5 ... VDD + 0.5 V; DC input current
# +-10 mA any one input. 8.2.2: "Inputs cannot be pushed more than 0.5V above VDD or below VEE"; "Outputs cannot be
# pulled above VDD or below VEE" (the signal pins are both). VEE = VSS = GND here.
SW_VIN_MARGIN, SW_IIN_MAX = 0.5, 10e-3
# Thonk low-profile LED button, red LED: no datasheet found; a standard red LED, 1.8 / 2.0 / 2.2 V assumed.
LED_VF_MIN, LED_VF_TYP, LED_VF_MAX = 1.8, 2.0, 2.2
# onsemi 1N5817/D (1N5819 column, verified): VRRM 40 V, IF(AV) 1 A, IFSM 25 A, VF max 0.34 V @ 0.1 A,
# 0.60 V @ 1 A, 0.90 V @ 3 A; IR max 1 mA at 40 V, 25 C.
D5819_VRRM, D5819_IF, D5819_IFSM = 40.0, 1.0, 25.0
# Typical VF read from the typical forward curve (onsemi / Vishay, 25 C): about 0.30 V at 0.1 A, ~60 mV/decade
# below that. Approximate (read off a log plot).


def vf_bat85(i, worst=False):
    """BAT85 forward voltage at current i (A). Worst: Vishay's max points (0.24 V at 0.1 mA, 0.32 V at 1 mA,
    0.40 V at 10 mA, 0.50 V at 30 mA, 0.80 V at 100 mA), interpolated in log(i). Typ: 0.08 V under them
    (ASSUMED from the datasheet's typical curve)."""
    pts = [(1e-4, 0.24), (1e-3, 0.32), (1e-2, 0.40), (3e-2, 0.50), (1e-1, 0.80)]
    i = min(max(i, 1e-4), 0.1)
    for (i0, v0), (i1, v1) in zip(pts, pts[1:]):
        if i <= i1:
            v = v0 + (v1 - v0) * math.log(i / i0) / math.log(i1 / i0)
            break
    return v if worst else v - 0.08


def vf_clamp(i, worst=False):
    """D904's forward voltage, by the part circuit.py fits there (BAT85 until 2026-11-15, now a 1N5819)."""
    return (vf5819 if MB["D904"].kind == "D5819" else vf_bat85)(i, worst)


def vf5819(i, worst=False):
    """1N5819 forward voltage at current i (A): typ from the curve, worst from the two max points."""
    i = max(i, 1e-5)
    if worst:                      # 0.34 V max at 0.1 A holds below it too (VF falls with current)
        return 0.34 if i <= 0.1 else 0.34 + 0.26 * math.log10(i / 0.1)
    return 0.30 + 0.06 * math.log10(i / 0.1)


# The 10 R filters' rating as bom.md orders them: "1/4 W" -> 0.25 W rated at 70 C (Royalohm / Yageo MFR-25
# class); "0.6 W in the 1/4 W (0207) body" -> 0.6 W (TE LR1F, Vishay MBB0207 datasheets, at 70 C).
_bom_r10 = re.search(r"\| Resistor 10 Ω, metal film 1 %, ([^|]+?) \| R918", open(
    os.path.join(harness.MODULE, "docs", "bom.md"), encoding="utf-8").read())
_w = _bom_r10 and re.match(r"(\d+(?:\.\d+)?|1/4|1/2) W", _bom_r10.group(1))
RES_P = {"1/4": 0.25, "1/2": 0.5}.get(_w.group(1), None) if _w else 0.25
RES_P = RES_P if RES_P is not None else float(_w.group(1))
# Silicon junction (CMOS substrate / ESD diodes) conducting noticeably from about 0.5-0.6 V.
SI_VF_ON = 0.55
# IPC-2221 external-layer trace current: I = 0.048 * dT^0.44 * A^0.725 (A in mil^2), 1 oz = 1.378 mil.
COPPER_MIL = 1.378
EXT_LOAD = 10e3                    # worst-case load on OUT L / OUT R / SEND (Eurorack inputs are >= 10k)

DOC = open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
BOM_MD = open(os.path.join(harness.MODULE, "docs", "bom.md"), encoding="utf-8").read()
BOM_CSV = list(csv.DictReader(open(os.path.join(harness.MODULE, "hardware", "bom", "stereo-mixer-bom.csv"),
                                   encoding="utf-8")))

MB = {p.ref: p for p in circuit.main_board_parts()}
FB = {p.ref: p for p in circuit.faceplate_parts()}
VP, VN, GND = circuit.VP, circuit.VN, circuit.GND

# ----------------------------------------------------------------- the routed export
docs = harness.read_export()
fps = ca.footprints_of(docs)
boards = ca.boards_of(docs, fps)
mbr = next(b for t, b in boards.items() if "Main" in t)
main_doc = next(d for d in docs.values() if d["docType"] == "PCB"
                and any(p.get("title") == mbr.title for h, p in d["recs"] if h["type"] == "META"))


def title_of(d):
    return next((p for h, p in d["recs"] if h["type"] == "META"), {}).get("title")


FP_DOCS = {title_of(d): d for d in docs.values() if d["docType"] == "FOOTPRINT"}
DEVICES = {u: d for u, d in docs.items() if d["docType"] == "DEVICE"}


def device_of(ref):
    """The DEVICE doc a routed component was placed from (its 'Device' attribute)."""
    cid = mbr.parts[ref]["cid"]
    for h, p in main_doc["recs"]:
        if h["type"] == "ATTR" and p.get("parentId") == cid and p["key"] == "Device":
            return docs[p["value"]]
    return None


def symbol_pins(dev):
    """{pin number: pin name} of a device's symbol."""
    attrs = next(p for h, p in dev["recs"] if h["type"] == "META")["attributes"]
    sym = docs[attrs["Symbol"]]
    names, nums = {}, {}
    for h, p in sym["recs"]:
        if h["type"] == "ATTR" and p.get("parentId"):
            if p["key"] == "Pin Name":
                names[p["parentId"]] = p["value"]
            elif p["key"] == "Pin Number":
                nums[p["parentId"]] = p["value"]
    return {nums[k]: names.get(k) for k in nums}


def fp_items(title, layer):
    """Silk segments (polylines split) and filled polygons of a footprint on one layer, footprint frame (mil)."""
    segs, fills = [], []
    for h, p in FP_DOCS[title]["recs"]:
        if p.get("layerId") != layer:
            continue
        if h["type"] == "POLY" and isinstance(p["path"], list) and p["path"] and p["path"][0] != "CIRCLE" \
                and "ARC" not in p["path"]:
            nums = [v for v in p["path"] if not isinstance(v, str)]
            pts = list(zip(nums[0::2], nums[1::2]))
            segs += list(zip(pts, pts[1:]))
        elif h["type"] == "FILL" and isinstance(p["path"][0], (int, float)):
            nums = [v for v in p["path"] if not isinstance(v, str)]
            fills.append(list(zip(nums[0::2], nums[1::2])))
    return segs, fills


def fp_pads(title):
    return {p["num"]: (p["centerX"], p["centerY"], p["hole"]["width"])
            for h, p in FP_DOCS[title]["recs"] if h["type"] == "PAD"}


# =================================================================== 1. J18 against the Doepfer bus
print("--- J18: Eurorack power header")
j18 = MB["J18"]
want = {"-12V": "N12_IN", "GND": GND, "+12V": "P12_IN"}
for n in range(1, 17):
    bus = DOEPFER[n]
    got = j18.nets.get(str(n))
    exp = want.get(bus)                      # +5 V, CV, GATE: nothing
    ck.check(f"J18.{n} ({bus}) in circuit.py", got == exp, f"expected {exp}, got {got}")
jr = mbr.parts["J18"]
ck.check("J18 routed footprint is the 2.54 mm box header", jr["fp"] == "IDC-TH_16P-P2.54_C3406",
         f"footprint {jr['fp']}")
for n in range(1, 17):
    exp = want.get(DOEPFER[n])
    got = jr["nets"].get(str(n))
    ck.check(f"J18.{n} ({DOEPFER[n]}) in the routed export", got == exp, f"expected {exp}, got {got}")
P = jr["pads"]
along = [math.hypot(P[str(n)].x - P[str(n + 2)].x, P[str(n)].y - P[str(n + 2)].y) for n in range(1, 15)]
across = [math.hypot(P[str(n)].x - P[str(n + 1)].x, P[str(n)].y - P[str(n + 1)].y) for n in range(1, 16, 2)]
ck.check("J18 pad pitch along the rows (measured)", all(abs(d - PITCH) < 0.02 for d in along),
         f"expected {PITCH} mm, got {min(along):.3f} ... {max(along):.3f} mm")
ck.check("J18 row spacing (measured)", all(abs(d - PITCH) < 0.02 for d in across),
         f"expected {PITCH} mm, got {min(across):.3f} ... {max(across):.3f} mm")
holes = {n: w * MIL for n, (x, y, w) in fp_pads(jr["fp"]).items()}
ck.check("J18 drill fits a 0.64 mm square pin (diagonal 0.91 mm)", min(holes.values()) >= 0.95,
         f"expected >= 0.95 mm, got {min(holes.values()):.2f} mm")
# pin 1 marking and the key notch in the footprint's own silkscreen (footprint frame, mil)
segs, _ = fp_items(jr["fp"], 3)
fpp = fp_pads(jr["fp"])
short = [s for s in segs if 5 < math.dist(*s) < 60                 # the pin-1 triangle's strokes, not the
         and not all(abs(p[0]) <= 110 for p in s)]                   # notch's corner stubs
mx = sum((a[0] + b[0]) / 2 for a, b in short) / max(len(short), 1)
my = sum((a[1] + b[1]) / 2 for a, b in short) / max(len(short), 1)
near = min(fpp, key=lambda n: math.hypot(fpp[n][0] - mx, fpp[n][1] - my))
ck.check("J18 silkscreen pin-1 triangle is beside pad 1", bool(short) and near == "1",
         f"marker at ({mx:.0f}, {my:.0f}) mil, nearest pad {near}")
notch = [s for s in segs if all(abs(p[0]) <= 110 for p in s) and any(abs(p[1]) > 85 for p in s)
         and math.dist(*s) >= 60]
ny = sum((a[1] + b[1]) / 2 for a, b in notch) / max(len(notch), 1)
odd_y = fpp["1"][1]
ck.check("J18 key notch on the pin-1 (odd) row's side (IDC box-header convention)",
         bool(notch) and ny * odd_y > 0, f"notch at y {ny:.0f} mil, odd row at y {odd_y:.0f} mil")
# a board-level label beside pin 1 (the footprint triangle sits inside the shroud, hidden by a plugged cable)
labels = []
for h, p in main_doc["recs"]:
    if h["type"] == "STRING" and p.get("layerId") in (3, 4):
        x, y = p["x"] * MIL, p["y"] * MIL
        if math.hypot(x - P["1"].x, y - P["1"].y) < 12:
            labels.append(p["text"])
ck.check("a -12V / RED / stripe label on the silkscreen beside J18 pin 1",
         any(re.search(r"-12|−12|RED|STRIPE", t, re.I) for t in labels), f"silk text within 12 mm of pin 1: {labels}")
# pins 11-16 (+5 V, CV, Gate): no net and no copper
for n in ("11", "12", "13", "14", "15", "16"):
    pad = P[n]
    touch = [t["net"] for t in mbr.tracks if pad.d_seg(t["a"], t["b"]) <= t["w"] / 2 + 0.001]
    touch += [v["net"] for v in mbr.vias if pad.d_circle(v["c"], v["r"]) <= 0.001]
    touch += [i.net for i in mbr.islands if i.contains((pad.x, pad.y))]
    ck.check(f"J18.{n} ({DOEPFER[int(n)]}) touches no copper", not touch and not jr["nets"].get(n),
             f"net {jr['nets'].get(n)}, copper {touch}")
ck.check("design.md: J18 pins 1-2 -12 V, 3-8 GND, 9-10 +12 V, 11-16 unused",
         re.search(r"pins 1–2\s+−12 V.*3–8 GND, 9–10 \+12 V; 11–16\s+\(\+5 V, CV, Gate\) unused", DOC, re.S)
         is not None, "power section")

# =================================================================== 2. the diodes and C904 / C905
print("--- D901 / D902 / D903 / D904: cathode from the symbol and from the footprint's band")


def silk_side(title, pads):
    """The pad on the side of a footprint's extra silkscreen ink (diode band, "+" mark): length-weighted x."""
    segs, fills = fp_items(title, 3)
    ink = [((a[0] + b[0]) / 2, math.dist(a, b)) for a, b in segs]
    ink += [(sum(p[0] for p in f) / len(f), 50.0) for f in fills]
    cx = sum(x * w for x, w in ink) / sum(w for x, w in ink)
    return min(pads, key=lambda n: abs(pads[n][0] - cx)), cx


CATHODE = {}
for ref in ("D901", "D902", "D903", "D904"):
    pl = mbr.parts[ref]
    dev = device_of(ref)
    pins = symbol_pins(dev)
    k_sym = next((n for n, nm in pins.items() if nm in ("C", "K", "Cathode", "KA")), None)
    k_band, cx = silk_side(pl["fp"], fp_pads(pl["fp"]))
    ck.check(f"{ref}: symbol cathode pin = footprint band pad", k_sym == k_band,
             f"symbol {title_of(dev)} pins {pins}, band at x {cx:.0f} mil -> pad {k_band}")
    CATHODE[ref] = k_sym
    a_sym = "2" if k_sym == "1" else "1"
    for src, nets in (("circuit.py", MB[ref].nets), ("routed", pl["nets"])):
        if ref == "D901":
            exp = ("P12_D", "P12_IN")           # cathode towards the circuit, anode on the header's +12 V
        elif ref == "D902":
            exp = ("N12_IN", "N12_D")           # cathode on the header's -12 V, anode towards the circuit
        elif ref == "D903":
            exp = ("POR", GND)                  # cathode on POR, anode on GND: empties C906 at power-off
        else:
            exp = (VP, GND)                     # D904: cathode on +12V, anode on GND: clamps a missing +12 V
        ck.check(f"{ref} cathode / anode nets ({src})", (nets.get(k_sym), nets.get(a_sym)) == exp,
                 f"expected K {exp[0]}, A {exp[1]}; got K {nets.get(k_sym)}, A {nets.get(a_sym)}")

for ref, plus_net, minus_net in (("C904", VP, GND), ("C905", GND, VN)):
    pl = mbr.parts[ref]
    plus, cx = silk_side(pl["fp"], fp_pads(pl["fp"]))
    minus = "1" if plus == "2" else "2"
    ck.check(f"{ref} '+' pad (footprint silk) on the more positive net", pl["nets"].get(plus) == plus_net
             and pl["nets"].get(minus) == minus_net and MB[ref].nets.get(plus) == plus_net,
             f"'+' mark near pad {plus}: + on {pl['nets'].get(plus)}, - on {pl['nets'].get(minus)} "
             f"(expected + {plus_net}, - {minus_net})")


def bus_on_module(reversed_cable):
    """{module J18 pin: bus signal} for a 16-pin cable plugged the right way or turned round (pin n <-> 17 - n)."""
    return {m: DOEPFER[17 - m if reversed_cable else m] for m in range(1, 17)}


BUS_V = {"-12V": -12.0, "GND": 0.0, "+12V": 12.0, "+5V": 5.0, "CV": (0.0, 12.0), "GATE": (0.0, 12.0)}


def net_voltage(net, bus):
    """Voltage range of a J18 net for a cable orientation (the circuit side of the diodes unpowered = 0 V)."""
    vs = []
    for m, sig in bus.items():
        if j18.nets.get(str(m)) == net:
            v = BUS_V[sig]
            vs += list(v) if isinstance(v, tuple) else [v]
    return (min(vs), max(vs)) if vs else (0.0, 0.0)


for label, rev in (("correct cable", False), ("reversed cable", True)):
    bus = bus_on_module(rev)
    for ref in ("D901", "D902"):
        nets = MB[ref].nets
        k, a = nets[CATHODE[ref]], nets["2" if CATHODE[ref] == "1" else "1"]
        va = net_voltage(a, bus) if a.endswith("_IN") else (0.0, 0.0)
        vk = net_voltage(k, bus) if k.endswith("_IN") else (0.0, 0.0)
        vak_max = va[1] - vk[0]
        if rev:
            ck.check(f"{ref} blocks with a {label}", vak_max <= 0.0,
                     f"V(A) - V(K) at most {vak_max:+.1f} V (needs <= 0); reverse up to {vk[1] - va[0]:.1f} V "
                     f"of its {D5819_VRRM:.0f} V")
        else:
            ck.check(f"{ref} conducts with a {label}", vak_max >= 11.0, f"V(A) - V(K) = {vak_max:+.1f} V at power-up")
bus = bus_on_module(True)
onto_gnd = sorted({bus[m] for m in range(1, 17) if j18.nets.get(str(m)) == GND} - {"GND"})
# Verifier: a turned-round 16-pin cable shorts the bus +12 V / +5 V to GND through ANY Doepfer-pinout module
# (pins 3-8 GND is the standard). That is the bus's hazard, not this design's: at the module end the keyed
# shroud (checked above) stops it, and at the bus end a 2x5 header would not help either (a 10-to-16 cable
# reversed at the bus puts bus 7..14 on module pins 3..8, the same short). What the design must do is keep
# its own circuit unpowered and undamaged: both diodes block and the shroud is keyed.
print(f"    (info) reversed cable: module GND pins 3-8 get bus {onto_gnd} as well as GND: the PSU's current "
      f"limit handles it, as with every 16-pin module")
blocked = all(net_voltage(MB[r].nets["2" if CATHODE[r] == "1" else "1"], bus)[1]
              - net_voltage(MB[r].nets[CATHODE[r]], bus)[0] <= 0.0 for r in ("D901", "D902"))
ck.check("reversed 16-pin cable: the module's circuit stays unpowered (both diodes block, shroud keyed)",
         blocked and bool(notch), f"diodes block: {blocked}, key notch in the footprint: {bool(notch)}")

# =================================================================== 3. current budget
print("--- current budget")
val = lambda ref: harness.ohms(MB[ref].value) if ref in MB else harness.ohms(FB_POTS[ref])
FB_POTS = {r: v for r, _, v, _ in circuit.POTS} | {r: v for r, _, v, _, _ in circuit.POTS2}
POT_TOL = 0.8                                         # Alpha pots +-20 %: the low end loads hardest
n_amps = sum(1 for p in MB.values() if p.kind == "TL074") * 4
n_logic = sum(1 for p in MB.values() if p.kind in ("CD4093", "CD4013"))
n_sw = sum(1 for p in MB.values() if p.kind == "CD4053")
n_cmos = n_logic + n_sw
ck.check("16 TL074 amplifiers, 14 CMOS chips (2 CD4093B + 4 CD4013B + 8 CD4053B)",
         (n_amps, n_logic, n_sw) == (16, 6, 8), f"got {n_amps} amplifiers, {n_logic} CD4093B / CD4013B, {n_sw} CD4053B")
VSW = 10.5        # a full swing for the load currents: on the high side of design.md's "about +-10 V"


def par(*rs):
    return 1 / sum(1 / r for r in rs)


def mono_load(k):
    rf, rb = val(f"R{100 * k + 2}"), val(f"R{100 * k + 4}")
    pan, send = val(f"RV{3 * k - 1}") * POT_TOL, val(f"RV{3 * k}") * POT_TOL
    worst = min(par(send, rf + (par(a * pan, rb) if a else 0), rf + (par((1 - a) * pan, rb) if a < 1 else 0))
                for a in [i / 100 for i in range(101)])
    return worst


def stereo_load(c):
    return par(val(f"R{100 * c + 3}"), val(f"R{100 * c + 5}"))      # bus 200k || 10k to AV (other side antiphase)


loads = {f"follower {k}": mono_load(k) for k in circuit.MONO}
loads.update({f"follower {c}{s}": stereo_load(c) for c in circuit.STEREO for s in "LR"})
master = val("RV25")
loads.update({"summer L": par(val("R901"), master * POT_TOL, val("R904")),
              "summer R": par(val("R902"), master * POT_TOL, val("R907")),
              "summer S": par(val("R903"), val("R910")),
              "OUT L stage": par(val("R905"), val("R906") + EXT_LOAD),
              "OUT R stage": par(val("R908"), val("R909") + EXT_LOAD),
              "SEND stage": par(val("R911"), val("R912") + EXT_LOAD)})
for name, z in sorted(loads.items(), key=lambda kv: kv[1]):
    print(f"    {name:14} worst load {z / 1e3:6.2f} k -> {VSW / z * 1e3:5.2f} mA at {VSW} V")
ck.check("no op-amp load under 2 k (TL074 VOM spec'd to RL = 2 k)", min(loads.values()) >= 2e3,
         f"lowest {min(loads.values()) / 1e3:.2f} k")
# DC worst case on one rail: inputs all at one polarity -> followers and output stages on one rail, summers on the other
i_src = sum(VSW / z for n, z in loads.items() if not n.startswith("summer"))
i_sum = sum(VSW / z for n, z in loads.items() if n.startswith("summer"))
I_LOAD_WORST = max(i_src, i_sum)
i_short = sum(VSW / val(r) for r in ("R906", "R909", "R912"))      # the three outputs patched into a 0 V source
# latch: pull-ups (buttons held), LED chains


LED_R = {}
for k in circuit.MONO + circuit.STEREO:          # the LED resistor found by its nets: QKk -> LEDk
    rs = [p for p in MB.values() if p.kind == "R" and set(p.nets.values()) == {f"QK{k}", f"LED{k}"}]
    ck.check(f"ch{k}: one LED resistor QK{k} -> LED{k} (the button LED's whole chain on the main board)",
             len(rs) == 1, f"{[(p.ref, p.value) for p in rs]}")
    LED_R[k] = harness.ohms(rs[0].value) if rs else 1500.0


def led_current(k, vdd, worst_high):
    """A muted channel's LED current: Q (CD4013B, output resistance typ, or 0 for the most current) -> the LED
    resistor -> the red button LED (VF typ, or min for the most current). The three CD4053B selects on Q take
    under 1 uA each."""
    rq, vled = (0.0, LED_VF_MIN) if worst_high else (Q_R_TYP, LED_VF_TYP)
    return max(vdd - vled, 0) / (LED_R[k] + rq)


pullups = [p for p in MB.values() if p.kind == "R" and p.label == "button pull-up"]
ck.check("8 button pull-ups", len(pullups) == 8, f"got {len(pullups)}")


def budget(vdd_p, worst):
    """(+12 V mA unmuted, +12 V mA all muted, -12 V mA) at a rail voltage vdd_p at the chips."""
    iq = n_amps * (TL074_IQ_MAX if worst else TL074_IQ_TYP)
    il = I_LOAD_WORST if worst else 0.0
    # CMOS quiescent: the CD4093B / CD4013B 4 uA max (typ ~0), the CD4053B 18 uA typ / 60 uA max at 25 C
    cm = n_logic * CMOS_IDD_MAX + n_sw * SW_IDD_MAX if worst else n_sw * SW_IDD_TYP
    pu = sum(vdd_p / harness.ohms(p.value) for p in pullups) if worst else 0.0
    leds = sum(led_current(k, vdd_p, worst) for k in circuit.MONO + circuit.STEREO)
    return iq + il + cm + pu, iq + il + cm + pu + leds, iq + il, leds


def rail(i, worst):
    return V_RAIL - vf5819(i, worst) - harness.ohms(MB["R918"].value) * i


def solve(worst):
    v = V_RAIL
    for _ in range(30):
        pos_un, pos_mu, neg, leds = budget(v, worst)
        v = rail(pos_mu, worst)
    return pos_un, pos_mu, neg, leds


typ = solve(False)
wst = solve(True)
print(f"    typ: +12 V {typ[0] * 1e3:.1f} mA unmuted, {typ[1] * 1e3:.1f} mA all muted (LEDs {typ[3] * 1e3:.1f}); "
      f"-12 V {typ[2] * 1e3:.1f} mA")
print(f"    worst: +12 V {wst[0] * 1e3:.1f} mA unmuted, {wst[1] * 1e3:.1f} mA all muted (LEDs {wst[3] * 1e3:.1f}); "
      f"-12 V {wst[2] * 1e3:.1f} mA  (loads {I_LOAD_WORST * 1e3:.1f} mA at {VSW} V, 10k on the outputs)")
print(f"    with OUT L / OUT R / SEND shorted to 0 V: + {i_short * 1e3:.1f} mA on one rail")
_v85 = rail(wst[1], True)
_idd85 = SW_IDD_MAX85[10] + (SW_IDD_MAX85[15] - SW_IDD_MAX85[10]) * (_v85 - 10) / 5      # linear in VDD, 10 ... 15 V
print(f"    CMOS quiescent on +12 V: {n_sw * SW_IDD_TYP * 1e3:.2f} mA typ, "
      f"{(n_logic * CMOS_IDD_MAX + n_sw * SW_IDD_MAX) * 1e3:.2f} mA max at 25 C (in the budget); the {n_sw} CD4053Bs "
      f"alone {n_sw * _idd85 * 1e3:.1f} mA max at 85 C ({_v85:.1f} V), not in it")
# design.md, Power: "about 25 mA on -12 V; on +12 V about 25 mA plus about 6 mA per muted channel (its button LED),
# 70 mA with all eight muted"
m = re.search(r"about (\d+) mA on −12 V; on \+12 V about (\d+) mA plus about (\d+(?:\.\d+)?) mA\s+per\s+muted\s+"
              r"channel[^,]*, (\d+) mA with all eight muted", DOC)
ck.check("design.md states the current budget", m is not None, "Power: Current")
if m:
    d_neg, d_pos, d_per, d_all = (float(x) for x in m.groups())
    ck.close("doc -12 V 'about 25 mA' vs typical (mA)", typ[2] * 1e3, d_neg, 0.2 * d_neg)
    ck.close("doc +12 V unmuted 'about 25 mA' vs typical (mA)", typ[0] * 1e3, d_pos, 0.2 * d_pos)
    per = [led_current(k, rail(typ[1], False), False) * 1e3 for k in circuit.MONO + circuit.STEREO]
    # "about 6 mA": a whole-mA figure, so the typical per channel must round to it (+-0.5 mA)
    ck.check(f"doc 'about {d_per:g} mA per muted channel' vs typical (each channel, +-0.5 mA)",
             d_per - 0.5 <= min(per) and max(per) <= d_per + 0.5,
             f"typ {min(per):.2f} ... {max(per):.2f} mA per channel at {rail(typ[1], False):.2f} V (all muted)")
    ck.close(f"doc '{d_all:g} mA with all eight muted' vs typical (mA)", typ[1] * 1e3, d_all, 0.15 * d_all)
    # the figure a case's PSU budget needs: the doc's maximum must cover the worst case, without overstating it
    mx = re.search(r"about (\d+) mA on \+12 V\s+\(all muted\) and (\d+) mA on −12 V", DOC)
    d_max_pos, d_max_neg = (float(x) for x in mx.groups()) if mx else (d_all, d_neg)
    ck.check("doc budget covers the worst case (what a case's PSU budget needs), within 25 %",
             wst[1] * 1e3 <= d_max_pos <= 1.25 * wst[1] * 1e3 and wst[2] * 1e3 <= d_max_neg <= 1.25 * wst[2] * 1e3,
             f"doc max +12 V {d_max_pos:.0f} mA / -12 V {d_max_neg:.0f} mA; worst case +12 V {wst[1] * 1e3:.0f} mA, "
             f"-12 V {wst[2] * 1e3:.0f} mA (TL074 2.5 mA max per amp, full-swing DC loads, all muted, buttons held)")

# =================================================================== 4. rail voltages at the chips
print("--- rails at the chips (12.0 V at the bus)")
rails = {}
for name, i, worst in (("+12 V min load (typ, unmuted)", typ[0], False), ("+12 V typ (all muted)", typ[1], False),
                       ("+12 V max load (worst, all muted)", wst[1], True), ("-12 V typ", typ[2], False),
                       ("-12 V max load (worst)", wst[2], True)):
    v = rail(i, worst)
    rails[name] = v
    print(f"    {name:34} {i * 1e3:6.1f} mA: VF {vf5819(i, worst):.3f} V + 10R {10 * i:.3f} V -> {v:.2f} V")
# design.md's swing figures: typical, typical on the + side with every channel muted, guaranteed worst case
sw = re.search(r"swing about ±(\d+(?:\.\d+)?) V.*?\((\d+(?:\.\d+)?) V on the\s+\+ side with every channel muted; "
               r"±(\d+(?:\.\d+)?) V\s+guaranteed in the worst case[^)]*\)", DOC, re.S)
ck.check("design.md states the TL074 swing: typical, muted, worst case", sw is not None, "Gains section")
d_sw, d_sw_muted, d_sw_worst = (float(x) for x in sw.groups()) if sw else (10.5, 10.5, 10.5)
for name in ("+12 V max load (worst, all muted)", "-12 V max load (worst)"):
    ck.check(f"rail at the chips, {name}, holds the doc's worst-case swing ±{d_sw_worst} V with the TL074's "
             f"guaranteed {TL074_HEAD_MIN} V headroom", rails[name] - TL074_HEAD_MIN >= d_sw_worst - 0.05,
             f"{rails[name]:.2f} V -> {rails[name] - TL074_HEAD_MIN:.2f} V")
swing_typ = min(rails["+12 V typ (all muted)"], rails["-12 V typ"]) - TL074_HEAD_TYP
swing_open = min(rails["+12 V min load (typ, unmuted)"], rails["-12 V typ"]) - TL074_HEAD_TYP
swing_min = min(rails["+12 V max load (worst, all muted)"], rails["-12 V max load (worst)"]) - TL074_HEAD_MIN
print(f"    TL074 swing: typ +-{swing_open:.2f} V unmuted, {swing_typ:.2f} V all muted (1.5 V headroom), "
      f"worst +-{swing_min:.2f} V (3 V headroom)")
ck.close("design.md's typical TL074 swing vs the swing at the chips' rails, unmuted (V)", swing_open, d_sw, 0.3)
ck.close("design.md's typical swing with every channel muted vs the rails (V)", swing_typ, d_sw_muted, 0.3)
# a fixed requirement, not read from design.md: even in the worst case (12 V bus) the outputs pass a ±5 V
# Eurorack signal with 40 % to spare; lowering the rails below that needs a deliberate change here
WORST_SWING_MIN = 7.0
ck.check(f"worst-case TL074 swing at the chips' rails >= {WORST_SWING_MIN} V (fixed floor)", swing_min >= WORST_SWING_MIN,
         f"±{swing_min:.2f} V (rails {rails['+12 V max load (worst, all muted)']:.2f} / "
         f"{rails['-12 V max load (worst)']:.2f} V, {TL074_HEAD_MIN} V headroom)")
ck.check("design.md's guaranteed worst-case swing: the rails deliver it, and it understates them by 0.6 V at most",
         d_sw_worst - 0.05 <= swing_min <= d_sw_worst + 0.6, f"doc ±{d_sw_worst} V, rails give ±{swing_min:.2f} V")
step = led_current(1, rails["+12 V typ (all muted)"], False) * harness.ohms(MB["R918"].value)
print(f"    one mute toggling steps +12 V by {step * 1e3:.0f} mV (through the 10 R)")

# =================================================================== 5. ratings
print("--- ratings")
r10 = harness.ohms(MB["R918"].value)
for ref, i in (("R918", wst[1]), ("R919", wst[2])):
    p = i * i * r10
    ck.check(f"{ref} dissipation at the worst-case current <= half its {RES_P} W", p <= RES_P / 2,
             f"{i * 1e3:.0f} mA -> {p * 1e3:.0f} mW")
i_fault = (V_RAIL - 0.6) / r10                              # a short after the 10 R: VF 0.6 V at ~1 A
p_fault = i_fault ** 2 * r10
print(f"    short downstream of a 10 R: {i_fault:.2f} A, {p_fault:.1f} W in the 10 R (it fuses), "
      f"{i_fault:.2f} A in the 1N5819")
ck.check("downstream short: the 10 R is the weak link (fuses), the 1N5819 stays within its surge rating",
         p_fault > 4 * RES_P and i_fault < D5819_IFSM, f"{p_fault:.1f} W in a {RES_P} W resistor, "
         f"{i_fault:.2f} A vs IFSM {D5819_IFSM} A")
ck.check("1N5819 worst-case current <= half its 1 A rating", max(wst[1], wst[2]) <= D5819_IF / 2,
         f"{max(wst[1], wst[2]) * 1e3:.0f} mA")
# Worst reverse voltage, computed: the circuit side may still hold its rail (charged 10 uF) while the header
# side gets any bus voltage (correct, reversed, or shifted by one or more pin pairs).
v_circ = {"P12_D": (0.0, rail(typ[0], False)), "N12_D": (-rail(typ[2], False), 0.0)}
vr_max = 0.0
for shift in range(-14, 15, 2):
    for rev in (False, True):
        mp = {}
        for m in range(1, 17):
            b = (17 - m if rev else m) + shift
            if 1 <= b <= 16:
                mp[m] = DOEPFER[b]
        for r in ("D901", "D902"):
            kn, an = MB[r].nets[CATHODE[r]], MB[r].nets["2" if CATHODE[r] == "1" else "1"]
            vk = net_voltage(kn, mp) if kn.endswith("_IN") else v_circ[kn]
            va = net_voltage(an, mp) if an.endswith("_IN") else v_circ[an]
            vr_max = max(vr_max, vk[1] - va[0])
ck.check("1N5819 reverse voltage (reversed or shifted cable, charged circuit side) < VRRM 40 V",
         vr_max < D5819_VRRM, f"worst {vr_max:.1f} V of {D5819_VRRM:.0f} V")
# the routed master's main board may be placed but not routed yet (2026-11-15: every part with its pad nets, no
# copper): the copper checks then fail once each, saying so, instead of reading nothing
ROUTED_MAIN = bool(mbr.tracks)
print(f"    routed main board: {len(mbr.tracks)} tracks, {len(mbr.vias)} vias, {len(mbr.islands)} pour islands")
pw = [t["w"] for t in mbr.tracks if t["net"] in ("+12V", "-12V", "P12_IN", "N12_IN", "P12_D", "N12_D")]
if pw:
    wmin = min(pw)
    area = wmin / 0.0254 * COPPER_MIL
    i_trk = 0.048 * 10 ** 0.44 * area ** 0.725
    ck.check("power tracks carry the downstream-short current at 10 C rise (IPC-2221, 1 oz)", i_trk >= i_fault,
             f"narrowest power track {wmin:.2f} mm -> {i_trk:.2f} A vs {i_fault:.2f} A")
else:
    ck.check("power tracks carry the downstream-short current at 10 C rise (IPC-2221, 1 oz)", False,
             f"no power tracks on the routed main board ({len(mbr.tracks)} tracks: placed, not routed); "
             f"{i_fault:.2f} A to carry")
fc = 1 / (2 * math.pi * r10 * harness.farads(MB["C904"].value))
print(f"    10 R + 10 uF corner {fc:.0f} Hz: {20 * math.log10(100e3 / fc):.0f} dB down at 100 kHz (switching PSU noise)")
ck.check("10 R / 10 uF filter >= 20 dB down at 100 kHz", 20 * math.log10(100e3 / fc) >= 20, f"corner {fc:.0f} Hz")


def bom_line(ref):
    for row in BOM_CSV:
        if ref in [r.strip() for r in row["Refs"].split(",")]:
            return row["Part"]
    return ""


for ref in ("C904", "C905", "C911", "C906"):            # the rail / reset capacitors' BOM lines
    part = bom_line(ref)
    mv = re.search(r"(\d+)\s*V\b", part)
    ok = mv is not None and float(mv.group(1)) >= 25
    ck.check(f"BOM states a voltage rating >= 25 V for {ref} ({MB[ref].value}, on a 12 V net)", ok,
             f"'{part}'")
for ref in ("C911", "C906"):
    dev = title_of(device_of(ref))
    print(f"    {ref}: the export's device {dev}")
# every ceramic on a +-12 V net: TDK FG28 '1H' = 50 V; AVX/KYOCERA SkyCap SR30 '5' voltage code = 50 V
cer = {r: title_of(device_of(r)) for r, p in MB.items() if p.kind == "C" and p.value in ("100n", "1u")}
bad = {r: t for r, t in cer.items() if not ("1H" in t or t.startswith("SR305"))}
ck.check(f"the export's devices for all {len(cer)} 100 n / 1 u ceramics are 50 V parts", not bad,
         f"not 50 V: {bad}" if bad else f"{sorted(set(cer.values()))}")

# =================================================================== 6. decoupling
print("--- decoupling")
CHIPS = [f"U{n}" for n in range(1, 11)] + [p.ref for p in sorted(MB.values(), key=lambda p: int(p.ref[1:]))
                                           if p.kind == "CD4053"]
unrouted = []
for u in CHIPS:
    chip = MB[u]
    sup = ([("4", VP), ("11", VN)] if chip.kind == "TL074" else [("16", VP)] if chip.kind == "CD4053"
           else [("14", VP)])
    for pin, net in sup:
        ck.check(f"{u}.{pin} on {net}", chip.nets.get(pin) == net, f"got {chip.nets.get(pin)}")
        caps = [c for c in MB.values() if c.kind == "C" and set(c.nets.values()) == {net, GND}
                and c.label.split()[0] == u]
        ck.check(f"{u}: a 100 n for {net} in circuit.py", len(caps) == 1 and caps[0].value == "100n",
                 f"{[(c.ref, c.value) for c in caps]}")
        if not caps:
            continue
        c = caps[0].ref
        if not ROUTED_MAIN:
            unrouted.append(f"{c}->{u}.{pin}")
            continue
        cp = next(n for n, v in mbr.parts[c]["nets"].items() if v == net)
        L = mbr.track_path(net, ("pad", c, cp), ("pad", u, pin))
        g = mbr.parts[c]["pads"][next(n for n, v in mbr.parts[c]["nets"].items() if v == GND)]
        spokes = sum(1 for p0, p1, layer, n in mbr.spokes if n == GND and math.hypot(p0[0] - g.x, p0[1] - g.y) < 0.3)
        gvia = min((math.hypot(v["c"][0] - g.x, v["c"][1] - g.y) for v in mbr.vias if v["net"] == GND), default=99)
        ck.check(f"{c} -> {u}.{pin}: track <= 6 mm, GND pad tied into the pour", L is not None and L <= 6.0
                 and spokes >= 2, f"track {L if L is None else round(L, 1)} mm, {spokes} spokes, "
                 f"nearest GND via {gvia:.1f} mm")
if unrouted:
    ck.check(f"decoupler -> supply pin: track <= 6 mm, GND pad tied into the pour ({len(unrouted)} pairs)", False,
             f"the routed main board has no copper (placed, not routed): none of {', '.join(unrouted)} can be "
             f"checked")

def clamp(net_k, net_a):
    """Diodes in circuit.py with the cathode on net_k and the anode on net_a."""
    out = []
    for p in MB.values():
        if p.ref in CATHODE:
            kk = p.nets[CATHODE[p.ref]]
            aa = p.nets["2" if CATHODE[p.ref] == "1" else "1"]
            if (kk, aa) == (net_k, net_a):
                out.append(p.ref)
    return out


# =================================================================== 7. faults
print("--- faults: one rail missing, power-off")
iq_typ, iq_max = n_amps * TL074_IQ_TYP, n_amps * TL074_IQ_MAX
V_MISS = {}                                # how far the +12V net sits below GND with +12 V missing
for name, iq, worst in (("typ", iq_typ, False), ("max", iq_max, True)):
    v = vf5819(iq, worst) + r10 * iq
    if clamp(VP, GND):                     # D904 straight from GND, in parallel with D901 + R918
        v = min(v, vf_clamp(iq, worst))
    V_MISS[name] = min(v, SI_VF_ON + 0.05)
    print(f"    +12 V at 0 V, -12 V on: the op-amps' {iq * 1e3:.0f} mA ({name}) returns through D901 + R918"
          f"{' and D904' if clamp(VP, GND) else ''} -> +12V net at {-v:+.2f} V (CMOS VDD), unless the CMOS "
          f"substrate diodes take it from ~{SI_VF_ON} V")
    ck.check(f"+12 V missing (rail at 0 V), {name} IQ: VDD of all {n_cmos} CMOS chips >= {CMOS_VDD_MIN} V "
             f"(CD4000B / CD4053B abs max)", -V_MISS[name] >= CMOS_VDD_MIN, f"+12V net at {-V_MISS[name]:+.2f} V")

# +12 V missing, the CD4053Bs: VEE = VSS = GND, VDD = the +12V net below GND. Their throws sit at 0 V by design (y on
# GND, x on a summer's virtual earth), so with VDD below GND every signal pin is ABOVE VDD, against "inputs cannot
# be pushed more than 0.5 V above VDD" (SCHS047O 8.2.2; abs max DC input voltage VDD + 0.5 V).
def si_junction(v):
    """A CMOS pin's diode to its rail: 1 mA at SI_VF_ON + 0.05 V and 60 mV per decade. ASSUMED (no datasheet gives
    it); only the order of magnitude is used."""
    return 1e-3 * 10 ** ((v - (SI_VF_ON + 0.05)) / 0.06)


SWS = [p for p in MB.values() if p.kind == "CD4053"]
# pins 7 (VEE) and 8 (VSS) are supplies; every other pin on GND is a y throw or INH: 0 V hard, no series resistance
sw_gnd = [f"{p.ref}.{pin}" for p in SWS for pin, n in sorted(p.nets.items()) if n == GND and pin not in ("7", "8")]
for name in ("typ", "max"):
    v = V_MISS[name]
    i_j = si_junction(v)
    ck.check(f"+12 V missing, {name} IQ: the CD4053B pins on GND ({len(sw_gnd)}: y throws + INH) within VDD + "
             f"{SW_VIN_MARGIN} V", v <= SW_VIN_MARGIN,
             f"pins at 0 V, VDD (+12V net) at {-v:+.2f} V: {v:.2f} V above it")
    ck.check(f"+12 V missing, {name} IQ: current from GND into each of those pins (its diode to VDD) under the "
             f"{SW_IIN_MAX * 1e3:.0f} mA DC input current", i_j <= SW_IIN_MAX,
             f"about {i_j * 1e3:.3f} mA per pin at {v:.2f} V forward (junction ASSUMED 1 mA at {SI_VF_ON + 0.05:.2f} V, "
             f"60 mV/decade), {len(sw_gnd) * i_j * 1e3:.2f} mA over all {len(sw_gnd)}: GND -> pin -> VDD -> the "
             f"TL074s' V+ pins, i.e. a share of the op-amps' {iq_typ * 1e3:.0f}-{iq_max * 1e3:.0f} mA that D904 "
             f"carries in parallel (without D904, spread over these pins alone: "
             f"{(iq_typ if name == 'typ' else iq_max) / len(sw_gnd) * 1e3:.2f} mA each)")
# x throws (SUM_L / SUM_R / SUM_S) and commons (BLk / BRk / BSk): no longer held at 0 V. The summers' and followers'
# TL074s run between -12 V and the +12V net (about -0.4 V), so their outputs sit at about -2 V or lower and cannot
# hold a virtual earth at the GND on their IN+; these nets are reached only through >= 100k (feedback, return,
# drums, FX IN, bus resistors) from those outputs or from whatever is patched into the jacks. Bound: every
# resistor on the net (and, for a SUM net, every bus resistor too, as if every switch conducted) from 12 V, less a
# clamp drop: the most current a pin's diode (to VDD above, to VEE = GND below) could ever see.
sig = {}
for p in SWS:
    for pin, n in p.nets.items():
        if n not in (GND, VP) and not n.startswith("QK"):
            sig.setdefault(n, []).append(f"{p.ref}.{pin}")


def r_on(net):
    return [(p.ref, harness.ohms(p.value)) for p in MB.values() if p.kind == "R" and net in p.nets.values()]


bound = {}
for n, pins in sig.items():
    rs = r_on(n)
    if n.startswith("SUM_"):
        rs += [r for k in circuit.MONO + circuit.STEREO for r in r_on(f"B{n[4]}{k}")]
    bound[n] = sum((V_RAIL - SI_VF_ON) / r for _, r in rs)
    if n.startswith("SUM_"):
        print(f"    +12 V missing: {n} ({len(pins)} x throws) reached through {len(rs)} resistors "
              f"(>= {min(r for _, r in rs) / 1e3:.0f}k): at most {bound[n] * 1e3:.2f} mA into the whole net")
worst_net = max(bound, key=bound.get)
ck.check(f"+12 V missing: the CD4053B x throws and commons (SUM_*, B*) can only be driven through >= 100k: at most "
         f"{SW_IIN_MAX * 1e3:.0f} mA into any one pin", bound[worst_net] <= SW_IIN_MAX,
         f"worst {worst_net} at {bound[worst_net] * 1e3:.2f} mA even if one pin took the whole net with every source "
         f"at 12 V (commons: {max(v for n, v in bound.items() if not n.startswith('SUM_')) * 1e3:.2f} mA at most); "
         f"pulled below GND they clamp to VEE, above VDD + 0.5 V to VDD, at that current")
gnd_inp = [f"{u}.{pin}" for u in ("U1", "U2", "U3", "U4") for s, (o, im, ip) in circuit.SECTION.items()
           for pin in (ip,) if MB[u].nets.get(pin) == GND]
print(f"    TL074 IN+ pins hard on GND: {gnd_inp}")
for name, iq, worst in (("typ", iq_typ, False), ("max", iq_max, True)):
    v = min(vf5819(iq, worst) + r10 * iq, SI_VF_ON + 0.05)
    # upper bound per pin: the whole supply current returning through the GND-tied inputs' clamp diodes
    i_pin = iq / len(gnd_inp)
    ck.check(f"-12 V missing (rail at 0 V), {name} IQ: TL074 IN+ pins on GND within the abs max "
             f"(<= 0.5 V beyond V-, or <= 10 mA per pin, SLOS080W note 2)",
             v <= 0.5 or i_pin <= TL074_IIN_MAX,
             f"-12V net at {v:+.2f} V, at most {i_pin * 1e3:.1f} mA per pin ({len(gnd_inp)} pins)")


# A rail open (not connected) rather than at 0 V: the op-amps' supply current has no diode path back, so the
# parasitic paths carry all of it. Verifier: judged against the datasheets' abs max, not "a clamp must exist".
cl_p = clamp(VP, GND)
for name, iq, worst in (("typ", iq_typ, False), ("max", iq_max, True)):
    v_p = min(vf_clamp(iq, worst), SI_VF_ON) if cl_p else SI_VF_ON
    print(f"    +12V open, {name} IQ {iq * 1e3:.0f} mA: +12V net at {-v_p:+.2f} V")
ck.check(f"+12V open (not connected): CMOS VDD >= {CMOS_VDD_MIN} V (CD4000B abs max)",
         -v_p >= CMOS_VDD_MIN,
         f"clamps (K +12V, A GND): {cl_p}; {iq_typ * 1e3:.0f}-{iq_max * 1e3:.0f} mA returns through "
         + (f"D904 ({MB['D904'].value}): +12V net at {-v_p:+.2f} V at the max IQ and its max VF "
            f"({-min(vf_clamp(iq_typ), SI_VF_ON):+.2f} V typical); the CMOS chips' VSS->VDD diodes share it from "
            f"~{SI_VF_ON} V" if cl_p else
            f"the VSS->VDD diodes of {n_cmos} CMOS chips and the {len(gnd_inp)} TL074 IN+ pins on GND: +12V net near "
            f"-{SI_VF_ON}..-0.6 V"))
cl_n = clamp(GND, VN)
i_pin = iq_max / len(gnd_inp)
ck.check(f"-12V open (not connected): TL074 IN+ pins on GND carry the supply current within 10 mA per pin",
         bool(cl_n) or i_pin <= TL074_IIN_MAX,
         f"clamps (K GND, A -12V): {cl_n}; {iq_max * 1e3:.0f} mA over {len(gnd_inp)} pins = "
         f"{i_pin * 1e3:.1f} mA per pin (new die; old die rated -0.3 V with no current allowance)")

# CMOS input nets: any capacitor from the net to a rail other than GND pushes it outside 0 .. VDD at power-off
cmos_in = {}
for u in [f"U{n}" for n in range(5, 11)] + [p.ref for p in SWS]:
    chip = MB[u]
    # outputs and supplies; the CD4053B has none but its supplies (every signal pin is an input / output both ways)
    outs = ({"3", "4", "10", "11", "7", "14"} if chip.kind == "CD4093" else
            {"1", "2", "12", "13", "7", "14"} if chip.kind == "CD4013" else {"7", "8", "16"})
    for pin, net in chip.nets.items():
        if pin not in outs and net != GND:
            cmos_in.setdefault(net, []).append(f"{u}.{pin}")
c_rail = sum(harness.farads(p.value) for p in MB.values() if p.kind in ("C", "CP") and set(p.nets.values()) == {VP, GND})
dvdt = typ[0] / c_rail                                     # V/s when the bus disappears (cable pulled, PSU off fast)
print(f"    +12 V net: {c_rail * 1e6:.1f} uF; with {typ[0] * 1e3:.0f} mA it falls {dvdt / 1e3:.1f} V/ms at power-off")
for net, pins in sorted(cmos_in.items()):
    coupled = [p for p in MB.values() if p.kind == "C" and net in p.nets.values() and VP in p.nets.values()]
    if not coupled:
        continue
    c = sum(harness.farads(p.value) for p in coupled)
    i_cl = c * dvdt
    print(f"    {net}: {[p.ref for p in coupled]} from +12 V -> {len(pins)} CMOS inputs {pins}; at power-off it is pushed "
          f"to about -12 V and clamped at ~-{SI_VF_ON} V by their input diodes, {i_cl * 1e3:.1f} mA in all")
    cl = clamp(net, GND)
    ck.check(f"{net} stays >= -0.5 V at power-off (CD4000B input abs max): a clamp diode from GND", bool(cl),
             f"clamps (K {net}, A GND): {cl}; " + (f"{', '.join(cl)} holds it at about -0.3..-0.4 V" if cl else
                                                    f"the CMOS inputs' own diodes hold it at about -{SI_VF_ON} V"))
    ck.check(f"{net} clamp current at power-off within {CMOS_IIN_MAX * 1e3:.0f} mA per input",
             i_cl / len(pins) <= CMOS_IIN_MAX, f"{i_cl / len(pins) * 1e3:.2f} mA per input")
d903 = MB["D903"]
k = d903.nets[CATHODE["D903"]]
a = d903.nets["2" if CATHODE["D903"] == "1" else "1"]
# C906 from +12V to POR: V(POR) = V(+12V) - Vc with Vc >= 0 always, so V(A) - V(K) = -Vc <= 0 if A = POR, K = +12V
never = (a == "POR" and k == VP)
ck.check("D903 is forward-biased at power-off, so it empties C906", not never and (a, k) == (GND, "POR"),
         f"D903 anode {a}, cathode {k}: " + ("POR falls below GND at power-off and D903 conducts from GND"
                                            if (a, k) == (GND, "POR") else
                                            "V(POR) - V(+12V) = -V(C906) <= 0 in every state, it never conducts; a "
                                            "diode with its anode on GND and cathode on POR would clamp and empty it"))
ck.done()
