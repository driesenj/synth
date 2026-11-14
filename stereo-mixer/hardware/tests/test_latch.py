"""latch: the mute latch in time, against datasheet thresholds.

What it checks, per channel, with every value taken from circuit.py (parts
found by their nets, not by designator) and D903's orientation read from
the routed export (StereoMixer-routed.epro2: symbol pin names + footprint
band + the board's pad nets):
  button contacts -> 100k pull-up to +12 V -> 10k / 100n debounce ->
  CD4093B (inputs tied: a Schmitt inverter) -> CD4013B CLK (D = /Q, SET to
  GND), RESET of every flip-flop from the power-on RC (C906 from +12 V,
  R920 to GND, D903).
  1. netlist: every part of the chain found, every CMOS input tied, D903's
     real orientation;
  2. button timing: clean press / release, contact bounce (random bursts
     and the worst single gap), short taps, a held button, with the CD4093B
     thresholds at the actual VDD (typ, min, max and the min-hysteresis
     corners of TI SCHS115D, inputs-tied column "b");
  3. power: +12 V ramping in 1 ... 200 ms (button open and held), quick
     power cycles (off 10 ms / 100 ms / 1 s, fast and slow rail decay), a
     brown-out: does every flip-flop start reset, is reset released only
     after DB / CK have settled, is C906 emptied and by what, do POR / DB
     stay inside 0 ... VDD;
  4. drive: the CD4013B Q output (P-channel fitted to the IOH table)
     through the LED resistor + one / two AQY212EH LEDs + the button LED, against the
     AQY212EH's operate current and recommended current, at the typical
     and the worst-case low rail;
  5. the doc's figures (1 ms / 11 ms, ~70 ms reset, ~6.8 mA, "3 mA at
     most", "about 1 ms on, 0.1 ms off"), clock edge rate.

Button timing is solved exactly (piecewise exponentials, threshold
crossings in closed form). Power scenarios are stepped (10 us) with the
CMOS input protection diodes as clamps; the logic is evaluated over every
threshold corner at once.

Run:  cd stereo-mixer/hardware/tests && python test_latch.py
"""
import math
import os
import random
import re

import harness

ck = harness.Checks("latch")
circuit = harness.load("circuit")

# ================================================================== datasheet constants
# --- CD4093B, TI SCHS115D (Harris data, scanned; read from the page images), static characteristics,
#     column "b" = both inputs of a gate tied (our case). Same limits at -55 ... +125 C.
#     {VDD: (min, typ, max)} in volts.
NAND_VP = {5: (2.6, 3.3, 4.0), 10: (5.6, 7.0, 8.2), 15: (6.3, 9.4, 12.7)}   # positive-going threshold
NAND_VN = {5: (1.4, 2.3, 3.2), 10: (3.4, 5.1, 6.6), 15: (4.8, 7.3, 9.6)}    # negative-going threshold
NAND_VH = {5: (0.3, 0.9, 1.6), 10: (1.2, 2.3, 3.4), 15: (1.6, 3.5, 5.0)}    # hysteresis VP - VN
NAND_TTRANS_MAX = {5: 200e-9, 10: 100e-9, 15: 80e-9}   # output transition time tTHL/tTLH, max (CL 50 pF)
# --- CD4013B, TI SCHS023E (Sep 2016)
FLOP_VIL_MAX = {5: 1.5, 10: 3.0, 15: 4.0}      # input low voltage, max (all temperatures)
FLOP_VIH_MIN = {5: 3.5, 10: 7.0, 15: 11.0}     # input high voltage, min
FLOP_TRCL_MAX = {5: 15e-6, 10: 10e-6, 15: 5e-6}   # clock input rise / fall time, max (recommended)
FLOP_TW_RESET_MIN = {5: 180e-9, 10: 80e-9, 15: 50e-9}   # set / reset pulse width, min
FLOP_VDD_MIN = 3.0                              # recommended supply, min
# IOH (source), mA, (VDD, VO) -> {"min25": 25 C min, "typ": 25 C typ, "min85": 85 C min}
FLOP_IOH = {(5, 4.6): {"min25": 0.51, "typ": 1.0, "min85": 0.42},
            (5, 2.5): {"min25": 1.6, "typ": 3.2, "min85": 1.3},
            (10, 9.5): {"min25": 1.3, "typ": 2.6, "min85": 1.1},
            (15, 13.5): {"min25": 3.4, "typ": 6.8, "min85": 2.8}}
CMOS_VIN_ABS = 0.5           # absolute max input voltage: VSS - 0.5 ... VDD + 0.5 (both datasheets)
CMOS_IIN_ABS = 10e-3         # absolute max DC input current, any one input (both datasheets)
CMOS_DIODE_VF = 0.6          # input protection diode drop at ~0.1-1 mA: ASSUMED (silicon junction; not in the datasheets)
CMOS_RETAIN_V = 1.5          # VDD below which a flip-flop's state is taken as lost: ASSUMED (not specified)
# --- Panasonic AQY21xEH (GU-E 1 Form A), ASCTB126E 2012-01, AQY212EH column, 25 C
AQY_IFON_MAX = 3.0e-3        # LED operate current, max (IL = max)
AQY_IFON_TYP = 1.2e-3        # LED operate current, typ
AQY_IFOFF_MIN = 0.4e-3       # LED turn-off current, min
AQY_VF_TYP_5MA = 1.14        # LED dropout voltage, typ at IF = 5 mA
AQY_VF_MAX_50MA = 1.5        # LED dropout voltage, max, at IF = 50 mA (typ 1.25 V there)
# Verifier: the 1.5 V max is specified at IF = 50 mA, not at the 2.5-5 mA this circuit runs. The datasheet gives
# no max at 5 mA; shift the 50 mA max down by the typical curve's drop from 50 mA to 5 mA (1.25 -> 1.14 V):
# 1.39 V, still a max-grade (not typical) figure. ESTIMATE, not a datasheet number.
AQY_VF_MAX = AQY_VF_MAX_50MA - (1.25 - AQY_VF_TYP_5MA)
AQY_IF_REC = (5e-3, 10e-3)   # recommended input LED current
AQY_IF_ABS = 50e-3           # LED forward current, abs max
AQY_TON = (1.0e-3, 4.0e-3)   # turn-on time typ / max at IF = 5 mA
AQY_TOFF = (0.05e-3, 1.0e-3)  # turn-off time typ / max at IF = 5 mA
# --- Thonk low-profile LED button, red (bom.py BUTTONS = red). Thonk's drawing (LowProfileButton.pdf) gives no
#     LED data. ASSUMED generic red LED: VF typ 2.0 V, max 2.5 V at 2-5 mA; no built-in resistor (the repo's
#     Marblesy notes drive it with 470R from a 3.3 V 74HC595 at ~2.5 mA, which implies VF ~ 2.1 V and no resistor).
BTN_LED_VF = {"typ": 2.0, "max": 2.5}
# --- power: Eurorack +12 V at the header: ASSUMED 12.0 V nominal, 11.4 V worst (-5 %); 1N5819 (onsemi
#     1N5817-D) VF ~0.32 V typ at 0.1 A, 0.4 V taken as worst near 75 mA (the 0.6 V max is at 1 A).
#     TI TL074 (SLOS080) supply current per amplifier: typ 1.4 mA, max 2.5 mA; 16 amplifiers.
RAIL = {"typ": 12.0, "low": 11.4}
D5819_VF = {"typ": 0.32, "low": 0.40}
TL074_ICC = {"typ": 16 * 1.4e-3, "low": 16 * 2.5e-3}
# --- contact bounce envelope (the task's): bursts 0.1 ... 5 ms, gaps tens of us ... ms
BOUNCE_BURST_MAX = 5e-3


# ================================================================== the netlist, from circuit.py
MB = circuit.main_board_parts()
FB = circuit.faceplate_parts()


def parts_between(a, b, kind=None, parts=MB):
    return [p for p in parts if (not kind or p.kind == kind) and len(p.nets) == 2 and set(p.nets.values()) == {a, b}]


def one(lst, what):
    ck.check(f"netlist: exactly one {what}", len(lst) == 1, f"found {[p.ref for p in lst]}")
    return lst[0] if lst else None


CH = circuit.MONO + circuit.STEREO
_design = open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
_m = re.search(r"about ([\d.]+) mA typical on either kind", _design)
DOC_LED_MA = float(_m.group(1)) * 1e-3 if _m else 0.0
_m = re.search(r"about (\d+) ms of reset", _design)
DOC_RESET_MS = float(_m.group(1)) if _m else 0.0
VP_NET, GND = circuit.VP, circuit.GND
CHAN = {}
for k in CH:
    c = {"pullup": one(parts_between(VP_NET, f"BTN{k}", "R"), f"pull-up BTN{k} to +12V"),
         "rdb": one(parts_between(f"BTN{k}", f"DB{k}", "R"), f"debounce R BTN{k}-DB{k}"),
         "cdb": one(parts_between(f"DB{k}", GND, "C"), f"debounce C DB{k}-GND"),
         "rled": one(parts_between(f"QK{k}", f"LA{k}", "R"), f"LED resistor QK{k}-LA{k}")}
    c["kmos"] = [p for p in MB if p.kind == "PHOTOMOS" and any(n.startswith(f"FI{k}") for n in p.nets.values())]
    c["nand_in"] = [(p.ref, pin) for p in MB if p.kind == "CD4093" for pin, n in p.nets.items() if n == f"DB{k}"]
    c["button"] = [p for p in FB if p.kind == "SWLED" and f"BTN{k}_F" in p.nets.values()]
    CHAN[k] = c

C906 = one(parts_between(VP_NET, "POR", "C"), "POR capacitor +12V-POR")
R920 = one(parts_between("POR", GND, "R"), "POR resistor POR-GND")
D903 = one([p for p in MB if p.kind.startswith("D") and "POR" in p.nets.values()], "diode on POR")
NANDS = [p for p in MB if p.kind == "CD4093"]
FLOPS = [p for p in MB if p.kind == "CD4013"]

# CMOS inputs: CD4093 pins 1 2 5 6 8 9 12 13; CD4013 CLK 3 11, RESET 4 10, D 5 9, SET 6 8
NAND_INPUTS = ["1", "2", "5", "6", "8", "9", "12", "13"]
FLOP_PINS = {"Q": ("1", "13"), "QN": ("2", "12"), "CLK": ("3", "11"), "RESET": ("4", "10"), "D": ("5", "9"),
             "SET": ("6", "8")}
mbnets = circuit.nets_of(MB)
for p in NANDS:
    missing = [pin for pin in NAND_INPUTS if pin not in p.nets]
    ck.check(f"unused inputs: {p.ref} (CD4093B) every input connected", not missing, f"unconnected: {missing}")
    for a, b, y in circuit.NAND.values():
        ck.check(f"Schmitt inverter: {p.ref} pins {a}+{b} tied", p.nets.get(a) == p.nets.get(b),
                 f"{p.nets.get(a)} / {p.nets.get(b)}")
for p in FLOPS:
    for h in (0, 1):
        q, qn, clk, rst, d, st = (FLOP_PINS[x][h] for x in ("Q", "QN", "CLK", "RESET", "D", "SET"))
        ck.check(f"toggle: {p.ref} half {h + 1} D = /Q, SET to GND, RESET on POR",
                 p.nets.get(d) == p.nets.get(qn) and p.nets.get(st) == GND and p.nets.get(rst) == "POR",
                 f"D {p.nets.get(d)}, /Q {p.nets.get(qn)}, SET {p.nets.get(st)}, RESET {p.nets.get(rst)}")
        loads = [x for x in mbnets.get(p.nets.get(qn), []) if x != f"{p.ref}.{qn}"]
        ck.check(f"toggle: {p.ref} half {h + 1} /Q drives only its own D", loads == [f"{p.ref}.{d}"], f"/Q net loads {loads}")
ck.check("POR drives the RESET of all 8 flip-flop halves",
         sorted(mbnets["POR"]) == sorted([f"{p.ref}.{FLOP_PINS['RESET'][h]}" for p in FLOPS for h in (0, 1)]
                                         + [f"{C906.ref}.{[k for k, v in C906.nets.items() if v == 'POR'][0]}",
                                            f"{R920.ref}.{[k for k, v in R920.nets.items() if v == 'POR'][0]}",
                                            f"{D903.ref}.{[k for k, v in D903.nets.items() if v == 'POR'][0]}"]),
         f"POR: {sorted(mbnets['POR'])}")
for k in CH:
    c = CHAN[k]
    ck.check(f"ch{k}: DB drives one Schmitt gate (both inputs) and nothing else CMOS", len(c["nand_in"]) == 2,
             f"{c['nand_in']}")
    ck.check(f"ch{k}: button contacts 3+4 on BTN, 1+2 on GND_F", len(c["button"]) == 1 and
             c["button"][0].nets["3"] == c["button"][0].nets["4"] == f"BTN{k}_F" and
             c["button"][0].nets["1"] == c["button"][0].nets["2"] == "GND_F",
             f"{c['button'][0].nets if c['button'] else None}")
    ck.check(f"ch{k}: {'1' if k in circuit.MONO else '2'} PhotoMOS LED(s) in series LA{k} -> LED{k}",
             len(c["kmos"]) == (1 if k in circuit.MONO else 2), f"{[p.ref for p in c['kmos']]}")

# Per-channel values (all channels share one set of values; simulate the distinct sets)
VALS = {}
for k in CH:
    c = CHAN[k]
    VALS[k] = (harness.ohms(c["pullup"].value), harness.ohms(c["rdb"].value), harness.farads(c["cdb"].value),
               harness.ohms(c["rled"].value), len(c["kmos"]))
R_POR, C_POR = harness.ohms(R920.value), harness.farads(C906.value)

# ---------------------------------------------------------------- D903's real orientation
docs = harness.read_export()
ca = harness.load("copper_audit")
_sym_pins = {}
_dev = next((d for d in docs.values() if d["docType"] == "DEVICE"
             and any(h["type"] == "META" and p.get("title") == D903.value for h, p in d["recs"])), None)
_meta = next(p for h, p in _dev["recs"] if h["type"] == "META") if _dev else {}
_symdoc = docs.get(_meta.get("attributes", {}).get("Symbol", ""))
if _symdoc:
    _attrs = {}
    for h, p in _symdoc["recs"]:
        if h["type"] == "ATTR" and p.get("parentId"):
            _attrs.setdefault(p["parentId"], {})[p["key"]] = p["value"]
    for h, p in _symdoc["recs"]:
        if h["type"] == "PIN":
            a = _attrs.get(h["id"], {})
            _sym_pins[a.get("Pin Number")] = a.get("Pin Name")
ck.check("D903 device symbol: pin 1 = C (cathode), pin 2 = A (anode)", _sym_pins == {"1": "C", "2": "A"},
         f"device {_meta.get('title')}: symbol pins {_sym_pins}")
# footprint: the cathode band (a silk line across the body) nearer pad 1
_fpdoc = docs.get(_meta.get("attributes", {}).get("Footprint", ""))
_band_ok, _band_detail = False, "footprint not found"
if _fpdoc:
    pads = {p["num"]: p["centerX"] for h, p in _fpdoc["recs"] if h["type"] == "PAD"}
    xs = [p["path"][0] for h, p in _fpdoc["recs"] if h["type"] == "POLY" and p["layerId"] == 3
          and len(p["path"]) == 5 and p["path"][2] == "L" and p["path"][0] == p["path"][3]]
    outline = max(abs(x) for x in xs) if xs else 0
    bands = [x for x in xs if 1 < abs(x) < outline - 1]       # inside the body outline
    _band_ok = bool(bands) and all((x < 0) == (pads["1"] < 0) for x in bands)
    _band_detail = f"pads x {pads}, band x {bands} (mil)"
ck.check("D903 footprint: the cathode band is on the pad-1 side", _band_ok, _band_detail)
_routed = ca.boards_of(docs, ca.footprints_of(docs))
_mainb = next(b for t, b in _routed.items() if "Main" in t)
_dnets = _mainb.parts.get(D903.ref, {}).get("nets", {})
D903_CATHODE = _dnets.get("1") if _sym_pins.get("1") == "C" else _dnets.get("2")
D903_ANODE = _dnets.get("2") if _sym_pins.get("2") == "A" else _dnets.get("1")
ck.check("D903 on the routed board matches circuit.py", _dnets == D903.nets, f"routed {_dnets}, circuit {D903.nets}")
print(f"INFO  D903 as built: anode on {D903_ANODE}, cathode on {D903_CATHODE}")
for ref in [p.ref for p in NANDS + FLOPS]:
    rn = _mainb.parts.get(ref, {}).get("nets", {})
    gn = next(p for p in MB if p.ref == ref).nets
    ck.check(f"routed {ref} pad nets match circuit.py (every input tied on the board too)", rn == gn,
             f"diff {[(n, rn.get(n), gn.get(n)) for n in set(rn) | set(gn) if rn.get(n) != gn.get(n)]}")


# ================================================================== models
def interp(table, vdd, idx=None):
    """Linear in VDD between the 5 / 10 / 15 V points; below 5 V, scaled with VDD (ratio of the 5 V point)."""
    get = (lambda v: table[v][idx]) if idx is not None else (lambda v: table[v])
    if vdd <= 5:
        return get(5) * vdd / 5
    lo, hi = (5, 10) if vdd <= 10 else (10, 15)
    return get(lo) + (get(hi) - get(lo)) * (min(vdd, 15) - lo) / (hi - lo)


# Schmitt corners: (name, VP(vdd), VN(vdd)); VP - VN kept inside the datasheet's VH range
def _corner(kind):
    def f(vdd):
        vpmin, vptyp, vpmax = (interp(NAND_VP, vdd, i) for i in range(3))
        vnmin, vntyp, vnmax = (interp(NAND_VN, vdd, i) for i in range(3))
        vhmin = interp(NAND_VH, vdd, 0)
        return {"typ": (vptyp, vntyp), "low": (vpmin, max(vnmin, vpmin - interp(NAND_VH, vdd, 2))),
                "high": (min(vpmax, vnmax + interp(NAND_VH, vdd, 2)), vnmax),
                "narrow-high": (min(vnmax + vhmin, vpmax), vnmax),   # VN as high as allowed, least hysteresis
                "narrow-low": (vpmin, max(vpmin - vhmin, vnmin))}[kind]
    return f


SCHMITT = {k: _corner(k) for k in ("typ", "low", "high", "narrow-high", "narrow-low")}


def reset_level(kind, vdd):
    """POR level above which RESET counts as active: the earliest-assert / latest-release corner is VIL max,
    the latest-assert / earliest-release corner VIH min, 'mid' VDD / 2."""
    return {"vil": interp(FLOP_VIL_MAX, vdd), "vih": interp(FLOP_VIH_MIN, vdd), "mid": vdd / 2}[kind]


def supply(case, muted_a=0.0):
    i = TL074_ICC[case] + muted_a
    return RAIL[case] - D5819_VF[case] - harness.ohms(next(p for p in MB if p.ref == "R918").value) * i


# ---------------------------------------------------------------- button timing, exact
def button_run(events, vdd, corner, rpu, rdb, cdb, t_end, db0=None):
    """events: [(t, closed)] sorted. Returns (toggle times, CK rising-edge times)."""
    vpth, vnth = SCHMITT[corner](vdd)
    db = vdd if db0 is None else db0
    out_high = db < vnth          # settled
    t, closed = 0.0, False
    clocks = []
    evs = list(events) + [(t_end, None)]
    for te, nxt in evs:
        dt = te - t
        if dt > 0:
            vinf, tau = (0.0, rdb * cdb) if closed else (vdd, (rpu + rdb) * cdb)
            # threshold crossing inside this interval?
            target = vpth if out_high else vnth
            if (not out_high and vinf < vnth < db) or (out_high and db < vpth < vinf):
                tc = tau * math.log((db - vinf) / (target - vinf))
                if tc <= dt:
                    out_high = not out_high
                    if out_high:
                        clocks.append(t + tc)
            db = vinf + (db - vinf) * math.exp(-dt / tau)
        t = te
        if nxt is not None:
            closed = nxt
    return clocks, db


def bounce_burst(t0, length, final_closed, rng, gmin=20e-6, gmax=1e-3):
    """Alternating contact events from t0 for `length`, ending in the final state."""
    ev, t, state = [], t0, final_closed
    ev.append((t, final_closed))
    while True:
        g = math.exp(rng.uniform(math.log(gmin), math.log(gmax)))
        if t + g >= t0 + length:
            break
        t += g
        state = not state
        ev.append((t, state))
    if state != final_closed:
        ev.append((t0 + length, final_closed))
    return ev


# the CD4013B Q output's drive (used below for the LED currents and here for the rail they pull down)
PMOS_VT = 1.0   # ASSUMED P-channel threshold for the curve shape between the datasheet points (0.5-1.5 V changes
                # the currents below by < 2 %)


def pmos_k(col, vdd):
    """Square-law k = I / ((VDD - Vt) Vds - Vds^2 / 2), exact at each IOH table point (the small-Vds ones:
    5 V / 4.6 V, 10 V / 9.5 V, 15 V / 13.5 V), linear in VDD between them."""
    ks = {}
    for (v, vo), d in FLOP_IOH.items():
        if (v, vo) == (5, 2.5):
            continue
        vds = v - vo
        ks[v] = d[col] * 1e-3 / ((v - PMOS_VT) * vds - vds * vds / 2)
    return interp({v: ks[v] for v in (5, 10, 15)}, vdd) if vdd > 5 else ks[5]


def ioh(col, vdd, vds):
    k, vov = pmos_k(col, vdd), vdd - PMOS_VT
    return k * (vov * vds - vds * vds / 2) if vds < vov else k * vov * vov / 2


def drive(vdd, col, nled, vf_aqy, vf_btn, rled):
    lo, hi = 0.0, vdd
    for _ in range(60):
        vds = (lo + hi) / 2
        i_load = max(0.0, (vdd - vds - nled * vf_aqy - vf_btn) / rled)
        if ioh(col, vdd, vds) > i_load:
            hi = vds
        else:
            lo = vds
    return max(0.0, (vdd - vds - nled * vf_aqy - vf_btn) / rled), vds


def muted_rail(case, muted):
    """+12 V at the chips with the channels in `muted` lit: the LED currents (typical drive) and the rail settled
    together, so the rail follows whatever LED resistors circuit.py has."""
    v = supply(case)
    for _ in range(8):
        v = supply(case, sum(drive(v, "typ", VALS[k][4], AQY_VF_TYP_5MA, BTN_LED_VF["typ"], VALS[k][3])[0]
                             for k in muted))
    return v


VDDS = {"typ": muted_rail("typ", CH[:5]), "low": muted_rail("low", CH), "high": 12.6}   # typ: five muted
print(f"INFO  VDD (+12V after D901 + R918): typ {VDDS['typ']:.2f} V, worst low {VDDS['low']:.2f} V, high {VDDS['high']:.2f} V")

for key in sorted(set(VALS.values())):
    rpu, rdb, cdb, rled, nled = key
    chans = [k for k in CH if VALS[k] == key]
    tag = f"ch{','.join(map(str, chans))}"
    # --- doc's time constants
    ck.close(f"{tag}: press time constant (doc: 1 ms on press)", rdb * cdb * 1e3, 1.0, 0.1, " ms")
    ck.close(f"{tag}: release time constant (doc: 11 ms on release)", (rpu + rdb) * cdb * 1e3, 11.0, 1.1, " ms")
    worst_rearm, worst_rel, tap_min, tap_max = 1e9, 1e9, 1e9, 0
    for vname, vdd in VDDS.items():
        for corner in SCHMITT:
            vpth, vnth = SCHMITT[corner](vdd)
            # clean press: one toggle, on the press, within a few ms
            clocks, _ = button_run([(0.01, True), (0.30, False)], vdd, corner, rpu, rdb, cdb, 1.0)
            ok = len(clocks) == 1 and 0.01 < clocks[0] < 0.01 + 3e-3
            ck.check(f"{tag} VDD {vname} Schmitt {corner}: clean press toggles once, on the press", ok,
                     f"expected 1 clock 0..3 ms after press, got {[round((c - 0.01) * 1e3, 2) for c in clocks]} ms")
            # gap after the press edge that re-arms the Schmitt (DB from VN back up to VP while open)
            worst_rearm = min(worst_rearm, (rpu + rdb) * cdb * math.log((vdd - vnth) / (vdd - vpth)))
            # release bounce: DB from ~0 up to VP with the contact open the whole time
            worst_rel = min(worst_rel, (rpu + rdb) * cdb * math.log(vdd / (vdd - vpth)))
            t_tap = rdb * cdb * math.log(vdd / vnth)
            tap_min, tap_max = min(tap_min, t_tap), max(tap_max, t_tap)
            # held button: 10 s
            clocks, _ = button_run([(0.01, True), (10.01, False)], vdd, corner, rpu, rdb, cdb, 11.0)
            ck.check(f"{tag} VDD {vname} Schmitt {corner}: button held 10 s toggles once", len(clocks) == 1,
                     f"clocks {len(clocks)}")
            # short taps: 0.2 ms never toggles; 20 ms always once
            c1, _ = button_run([(0.01, True), (0.0102, False)], vdd, corner, rpu, rdb, cdb, 0.5)
            c2, _ = button_run([(0.01, True), (0.03, False)], vdd, corner, rpu, rdb, cdb, 0.5)
            ck.check(f"{tag} VDD {vname} Schmitt {corner}: 0.2 ms glitch ignored, 20 ms tap toggles once",
                     len(c1) == 0 and len(c2) == 1, f"0.2 ms: {len(c1)} clocks, 20 ms: {len(c2)} clocks")
            # random bounce, 300 presses
            rng = random.Random(4013 + sum(map(ord, corner + vname)))   # deterministic (str hash is salted)
            bad = []
            for n in range(300):
                bp, br = rng.uniform(0.1e-3, BOUNCE_BURST_MAX), rng.uniform(0.1e-3, BOUNCE_BURST_MAX)
                hold = rng.uniform(0.03, 0.5)
                ev = bounce_burst(0.01, bp, True, rng) + bounce_burst(0.01 + bp + hold, br, False, rng)
                clocks, _ = button_run(ev, vdd, corner, rpu, rdb, cdb, 0.01 + bp + hold + br + 0.3)
                if len(clocks) != 1 or not (0.01 <= clocks[0] <= 0.01 + bp + 3e-3):
                    bad.append((n, len(clocks)))
            ck.check(f"{tag} VDD {vname} Schmitt {corner}: 300 bouncy presses (bursts 0.1-5 ms, gaps 20 us-1 ms) "
                     "toggle exactly once each, on the press", not bad, f"bad presses (n, clocks): {bad[:5]}")
    ck.check(f"{tag}: worst-case re-arm gap after the press edge > longest bounce burst (5 ms): no double toggle "
             "from one long bounce", worst_rearm > BOUNCE_BURST_MAX,
             f"a single open gap of {worst_rearm * 1e3:.2f} ms right after DB crosses VN re-arms the Schmitt at the "
             f"worst corner (VP min, least hysteresis, VDD high); typ {((rpu + rdb) * cdb * math.log((VDDS['typ'] - SCHMITT['typ'](VDDS['typ'])[1]) / (VDDS['typ'] - SCHMITT['typ'](VDDS['typ'])[0]))) * 1e3:.2f} ms")
    ck.check(f"{tag}: release bounce cannot clock: DB needs longer than a 5 ms burst to reach VP",
             worst_rel > BOUNCE_BURST_MAX, f"fastest DB rise 0 -> VP {worst_rel * 1e3:.2f} ms")
    print(f"INFO  {tag}: press-to-toggle {tap_min * 1e3:.2f} ... {tap_max * 1e3:.2f} ms over the corners; "
          f"taps shorter than that are ignored")

# ---------------------------------------------------------------- clock edge
for vname in ("typ", "low"):
    vdd = VDDS[vname]
    ck.check(f"CD4013B clock edge: CD4093B transition (max) << trCL max at VDD {vname}",
             interp(NAND_TTRANS_MAX, vdd) * 10 <= interp(FLOP_TRCL_MAX, vdd),
             f"edge {interp(NAND_TTRANS_MAX, vdd) * 1e9:.0f} ns, limit {interp(FLOP_TRCL_MAX, vdd) * 1e6:.1f} us")


# ---------------------------------------------------------------- power scenarios, stepped
DT = 10e-6
LSTEP = 10
VNOM = VDDS["typ"]


def run_power(vp_wave, t_end, contact=lambda t: False, q0=None, db0=0.0, por_q0=0.0, rpu=100e3, rdb=10e3, cdb=100e-9):
    """Step the analog nodes (DB, POR) once, then the logic over every corner.
    vp_wave(t) -> VP. Returns a dict of results."""
    n = int(t_end / DT)
    vp_prev = vp_wave(0.0)
    db = db0
    por = vp_prev - por_q0 / C_POR
    tau_por = R_POR * C_POR
    rec = {"vp": [], "db": [], "por": []}
    d903_max, por_min, por_max_over, db_over, i_por_clamp, i_db_clamp = -1e9, 1e9, -1e9, -1e9, 0.0, 0.0
    for i in range(n):
        t = (i + 1) * DT
        vp = vp_wave(t)
        # DB: through Rdb to 0 (closed) or through Rpu + Rdb to VP (open)
        vinf, tau = (0.0, rdb * cdb) if contact(t) else (vp, (rpu + rdb) * cdb)
        db = vinf + (db - vinf) * math.exp(-DT / tau)
        hi = vp + CMOS_DIODE_VF
        if db > hi:
            i_db_clamp = max(i_db_clamp, cdb * (db - hi) / DT / 2)       # two gate inputs share DB
            db = hi
        db_over = max(db_over, db - vp)
        # POR: C906 from VP, R920 to GND
        por = por * math.exp(-DT / tau_por) + (vp - vp_prev)
        if por < -CMOS_DIODE_VF:
            i_por_clamp = max(i_por_clamp, C_POR * (-CMOS_DIODE_VF - por) / DT / 8)   # 8 RESET inputs share it
            por = -CMOS_DIODE_VF
        # D903 as built: forward when anode - cathode > its drop
        va = por if D903_ANODE == "POR" else vp
        vc = vp if D903_CATHODE == VP_NET else por
        d903_max = max(d903_max, va - vc)
        if va - vc > CMOS_DIODE_VF:
            por = vp + CMOS_DIODE_VF if D903_ANODE == "POR" else vp - CMOS_DIODE_VF
        if por > vp + CMOS_DIODE_VF:
            por = vp + CMOS_DIODE_VF
        por_min, por_max_over = min(por_min, por), max(por_max_over, por - vp)
        vp_prev = vp
        rec["vp"].append(vp), rec["db"].append(db), rec["por"].append(por)
    res = {"d903_max": d903_max, "por_min": por_min, "por_over": por_max_over, "db_over": db_over,
           "i_por": i_por_clamp, "i_db": i_db_clamp, "rec": rec, "logic": {}}
    # logic, per corner, every LSTEP steps (DB / POR move on >= 1 ms scales); thresholds cached per 10 mV of VDD
    idx = range(LSTEP - 1, n, LSTEP)
    cache = {}

    def thr(sc, rk, v):
        key = (sc, rk, round(v, 2))
        if key not in cache:
            cache[key] = SCHMITT[sc](v) + (reset_level(rk, v),)
        return cache[key]
    for sc in SCHMITT:
        for init_high in (False, True):
            for rk in ("vil", "mid", "vih"):
                q = q0
                out = None
                reset_seen_func = False
                toggles_after_release = 0
                in_reset = False
                last_release = None
                for i in idx:
                    vp, dbv, porv = rec["vp"][i], rec["db"][i], rec["por"][i]
                    if vp < CMOS_RETAIN_V:
                        q, out = None, None
                        continue
                    vpth, vnth, rlev = thr(sc, rk, vp)
                    prev = out
                    if out is None:
                        out = init_high if vnth <= dbv <= vpth else dbv < vnth
                    elif dbv < vnth:
                        out = True
                    elif dbv > vpth:
                        out = False
                    edge = prev is False and out is True
                    rst = porv > rlev
                    if rst and vp >= FLOP_VDD_MIN:
                        q = 0
                        reset_seen_func = True
                        in_reset = True
                        toggles_after_release = 0       # a reset cancels every earlier clock edge
                        continue
                    if in_reset and not rst:
                        in_reset, last_release = False, (i + 1) * DT
                    if edge:
                        if vp >= FLOP_VDD_MIN and q is not None:
                            q = 1 - q
                        else:
                            q = None
                        # every clock edge that reaches a flip-flop out of reset and is not cancelled by a later
                        # reset counts: one after a reset release, or one in a brown-out / power cycle where reset
                        # never asserted at all (verifier fix: the edge used to be counted only after a release,
                        # so a toggle in a brown-out without reset was reported as 'reset' / 'no spurious clock')
                        toggles_after_release += 1
                res["logic"][(sc, init_high, rk)] = {"q": q, "reset": reset_seen_func,
                                                     "toggles": toggles_after_release, "release": last_release}
    return res


def ramp(T, v=VNOM, t0=0.0):
    return lambda t: 0.0 if t <= t0 else v * min((t - t0) / T, 1.0)


def summary(res):
    qs = sorted({str(r["q"]) for r in res["logic"].values()})
    rel = [r["release"] for r in res["logic"].values() if r["release"] is not None]
    return qs, rel


# --- power-up ramps, button open and button held
for T in (1e-3, 10e-3, 50e-3, 100e-3, 200e-3):
    res = run_power(ramp(T), T + 0.6)
    bad = {k: v for k, v in res["logic"].items() if v["q"] != 0 or not v["reset"] or v["toggles"]}
    qs, rel = summary(res)
    ck.check(f"power-up, +12 V ramp {T * 1e3:.0f} ms: every flip-flop reset while VDD >= 3 V, ends unmuted, "
             "no clock after reset release (all Schmitt / reset-threshold corners)", not bad,
             f"final Q {qs}; reset released {min(rel) * 1e3:.0f} ... {max(rel) * 1e3:.0f} ms; failing corners "
             f"{list(bad.items())[:3]}")
    # earliest release vs when DB has passed VP (CK settled low) at the slowest corner
    db = res["rec"]["db"]
    vp = res["rec"]["vp"]
    settle = None                                # last time DB was below VP max (CK may still rise after it)
    for i in range(len(db) - 1, -1, -10):
        if vp[i] >= FLOP_VDD_MIN and db[i] <= SCHMITT["high"](vp[i])[0]:
            settle = i * DT
            break
    settle = settle if settle is not None else 0.0
    ck.check(f"power-up ramp {T * 1e3:.0f} ms: reset (earliest release, VIH corner) outlasts the debounce settling",
             settle is not None and min(rel) > settle,
             f"DB above VP max from {settle * 1e3 if settle else float('nan'):.1f} ms, reset released at the earliest "
             f"{min(rel) * 1e3:.1f} ms")
    ck.check(f"power-up ramp {T * 1e3:.0f} ms: POR and DB stay inside 0 ... VDD", res["por_min"] >= -0.05 and
             res["db_over"] <= 0.05 and res["por_over"] <= 0.05,
             f"POR min {res['por_min']:.2f} V, POR - VDD max {res['por_over']:.2f} V, DB - VDD max {res['db_over']:.2f} V")
    held = run_power(ramp(T), T + 1.2, contact=lambda t: t < T + 0.5)
    bad = {k: v for k, v in held["logic"].items() if v["q"] != 0 or v["toggles"]}
    ck.check(f"power-up ramp {T * 1e3:.0f} ms with the button held 0.5 s past the ramp: ends unmuted, no toggle "
             "on release", not bad, f"final Q {summary(held)[0]}, failing corners {list(bad.items())[:2]}")

# doc: about 70 ms of reset at power-up (fast ramp)
res = run_power(ramp(1e-3), 0.5)
rel = {rk: [v["release"] for k, v in res["logic"].items() if k[2] == rk] for rk in ("vil", "mid", "vih")}
# verifier: "about 100 ms" read as +-25 % (the old +-35 ms was wide enough to pass the 70 ms the circuit gives);
# a CMOS input switches near VDD / 2, so the typical reset is R920 x C906 x ln 2, not R920 x C906
ck.close(f"doc: 'about {DOC_RESET_MS:g} ms of reset' vs the typical (VDD/2) release after a fast ramp",
         rel["mid"][0] * 1e3, DOC_RESET_MS, 0.25 * DOC_RESET_MS, " ms")
print(f"INFO  reset release after a 1 ms ramp: {min(rel['vih']) * 1e3:.0f} ms (VIH corner) ... "
      f"{max(rel['vil']) * 1e3:.0f} ms (VIL corner), {rel['mid'][0] * 1e3:.0f} ms at VDD / 2; R920 x C906 = "
      f"{R_POR * C_POR * 1e3:.0f} ms")
for rk in ("vil", "mid", "vih"):
    ck.check(f"reset pulse width ({rk}) >> CD4013B minimum", min(rel[rk]) > 1000 * interp(FLOP_TW_RESET_MIN, VNOM),
             f"{min(rel[rk]) * 1e3:.0f} ms vs {interp(FLOP_TW_RESET_MIN, VNOM) * 1e9:.0f} ns")


# --- power cycles: settled and running with the channel MUTED (Q = 1), then off for d, then back on
def cycle(d, tau_off, t_on=10e-3, settle=0.3):
    def w(t):
        if t < settle:
            return VNOM
        if t < settle + d:
            return VNOM * math.exp(-(t - settle) / tau_off)
        v_off = VNOM * math.exp(-d / tau_off)
        return min(VNOM, v_off + (VNOM - v_off) * (t - settle - d) / t_on)
    return w


# rail decay: the module's own load after D901 blocks the bus (C904 10 uF + 10 x 100 nF; the op-amps and
# every channel's mute lit, the fastest fall),
# or the bus decaying slowly with the PSU (tau 50 ms, ASSUMED)
C_RAIL = harness.farads("10u") + 10 * 100e-9
TAU_FAST = C_RAIL * VNOM / (TL074_ICC["typ"] + sum(drive(VNOM, "typ", VALS[k][4], AQY_VF_TYP_5MA,
                                                         BTN_LED_VF["typ"], VALS[k][3])[0] for k in CH))
cyc = []
for tau_name, tau_off in (("fast", TAU_FAST), ("slow", 50e-3)):
    for d in (10e-3, 100e-3, 1.0):
        res = run_power(cycle(d, tau_off), 0.3 + d + 0.6, q0=1, db0=VNOM, por_q0=C_POR * VNOM)
        vmin = VNOM * math.exp(-d / tau_off)
        outcomes = sorted({str(v["q"]) for v in res["logic"].values()})
        lost = vmin < CMOS_RETAIN_V
        good = outcomes == ["0"] if lost else (set(outcomes) <= {"0", "1"} and
                                                 all(v["toggles"] == 0 for v in res["logic"].values()))
        i_end = int((0.3 + d) / DT) - 1
        vc_left = res["rec"]["vp"][i_end] - res["rec"]["por"][i_end]
        ck.check(f"power cycle off {d * 1e3:.0f} ms ({tau_name} rail decay, VP down to {vmin:.2f} V), muted before: "
                 f"{'must come back reset' if lost else 'state kept or reset, never toggled'}", good,
                 f"final Q over corners {outcomes}; C906 holds {vc_left:.2f} V at the end of the off time "
                 f"(emptied down to VP + the clamp drop)")
        cyc.append((f"{d * 1e3:.0f} ms {tau_name}", res))
d903 = max(r["d903_max"] for _, r in cyc)
ck.check("D903 empties C906 at power-off (what a diode at C906 is for)", d903 > 0.3,
         f"D903 as built (anode {D903_ANODE}, cathode {D903_CATHODE}) is never forward biased: max "
         f"{d903:.2f} V over all power cycles. C906 is emptied instead through the CD4013B RESET input "
         f"protection diodes: POR pulled to {min(r['por_min'] for _, r in cyc):.2f} V, up to "
         f"{max(r['i_por'] for _, r in cyc) * 1e3:.2f} mA per input (fast rail decay, tau {TAU_FAST * 1e3:.1f} ms)")
ck.check(f"power-off: POR stays inside the CD4013B input range (VSS - {CMOS_VIN_ABS} V)",
         min(r["por_min"] for _, r in cyc) >= -CMOS_VIN_ABS,
         f"POR min {min(r['por_min'] for _, r in cyc):.2f} V (held only by the input diodes, ASSUMED drop "
         f"{CMOS_DIODE_VF} V)")
ck.check(f"power-off: DB stays inside the CD4093B input range (VDD + {CMOS_VIN_ABS} V)",
         max(r["db_over"] for _, r in cyc) <= CMOS_VIN_ABS,
         f"DB - VDD max {max(r['db_over'] for _, r in cyc):.2f} V: each 100 nF debounce cap discharges into VDD "
         f"through its gate's input diodes, {max(r['i_db'] for _, r in cyc) * 1e3:.2f} mA per input")
ck.check("power-off: clamp currents under the 10 mA abs max DC input current per input",
         max(max(r["i_por"], r["i_db"]) for _, r in cyc) < CMOS_IIN_ABS,
         f"RESET {max(r['i_por'] for _, r in cyc) * 1e3:.2f} mA, CD4093 {max(r['i_db'] for _, r in cyc) * 1e3:.2f} mA")
# with a diode across R920 (cathode POR, anode GND) instead, a BAT85-class Schottky (VF ~0.3 V at 1 mA, ASSUMED)
# would hold POR at about -0.3 V: inside the -0.5 V limit, the CMOS diodes then carry almost nothing.

# --- brown-out: muted channel, rail dips to v_dip for 20 ms (0.5 ms down, 1 ms back)
def dip(v_dip, d=20e-3, t0=0.3):
    def w(t):
        if t < t0:
            return VNOM
        if t < t0 + 0.5e-3:
            return VNOM + (v_dip - VNOM) * (t - t0) / 0.5e-3
        if t < t0 + 0.5e-3 + d:
            return v_dip
        return min(VNOM, v_dip + (VNOM - v_dip) * (t - t0 - 0.5e-3 - d) / 1e-3)
    return w


bo = {}
for v_dip in (10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0):
    res = run_power(dip(v_dip), 0.9, q0=1, db0=VNOM, por_q0=C_POR * VNOM)
    vals = res["logic"].values()
    n_tog = sum(1 for v in vals if v["toggles"])
    bo[v_dip] = ("kept" if all(v["q"] == 1 and not v["toggles"] for v in vals) else
                 "reset" if all(v["q"] == 0 and not v["toggles"] for v in vals) else
                 f"random (Q {','.join(sorted({str(v['q']) for v in vals}))} over the corners: "
                 f"{sum(1 for v in vals if v['q'] == 0)} reset, {sum(1 for v in vals if v['q'] == 1)} kept, "
                 f"{n_tog} with a spurious clock)")
print("INFO  brown-out (20 ms dip, muted channel) outcome by dip voltage: " +
      ", ".join(f"{v:g} V {o}" for v, o in bo.items()))
ck.check("brown-out: every dip depth ends either all-kept or all-reset (no random mutes / unmutes)",
         all(o in ("kept", "reset") for o in bo.values()),
         "random over the threshold corners at " + ", ".join(f"{v:g} V" for v, o in bo.items() if o.startswith("random")))
# verifier addition: the same dips with the channel UNMUTED before. A reset can only unmute, so any channel
# that ends muted here was clocked by the rail itself (DB left near the dip voltage while the Schmitt
# thresholds come back up with VDD: DB < VN -> CK rises).
bo_open = {}
for v_dip in (10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0):
    res = run_power(dip(v_dip), 0.9, q0=0, db0=VNOM, por_q0=C_POR * VNOM)
    vals = list(res["logic"].values())
    bo_open[v_dip] = (sum(1 for v in vals if v["q"] == 1), sum(1 for v in vals if v["toggles"]), len(vals))
print("INFO  brown-out (20 ms dip, UNMUTED channel): corners ending muted / with a clock edge out of reset: " +
      ", ".join(f"{v:g} V {m}/{n} ({t} clocked)" for v, (m, t, n) in bo_open.items()))
ck.check("brown-out: an unmuted channel is never muted by the rail dip itself (no spurious CK edge out of reset)",
         all(m == 0 for m, t, n in bo_open.values()),
         "spuriously muted at " + (", ".join(f"{v:g} V ({m} of {n} corners)" for v, (m, t, n) in bo_open.items() if m)
                                   or "no dip depth"))


# ================================================================== drive: Q -> LED resistor -> PhotoMOS LED(s) -> button LED
for col in ("typ", "min25", "min85"):
    print(f"INFO  CD4013B P-channel ({col}): k {pmos_k(col, 10) * 1e3:.3f} mA/V^2 at 10 V, "
          f"{pmos_k(col, 15) * 1e3:.3f} at 15 V; check point 5 V / VO 2.5 V: table {FLOP_IOH[(5, 2.5)][col]} mA, "
          f"model {ioh(col, 5, 2.5) * 1e3:.2f} mA")

totals = {}
for key in sorted(set(VALS.values())):
    rpu, rdb, cdb, rled, nled = key
    chans = [k for k in CH if VALS[k] == key]
    tag = f"ch{','.join(map(str, chans))} ({'mono' if nled == 1 else 'stereo'}, {nled} PhotoMOS LED)"
    i_typ, vds_typ = drive(VDDS["typ"], "typ", nled, AQY_VF_TYP_5MA, BTN_LED_VF["typ"], rled)
    i_w, vds_w = drive(VDDS["low"], "min25", nled, AQY_VF_MAX, BTN_LED_VF["max"], rled)
    i_w85, _ = drive(VDDS["low"], "min85", nled, AQY_VF_MAX, BTN_LED_VF["max"], rled)
    i_w_typvf, _ = drive(VDDS["low"], "min25", nled, AQY_VF_TYP_5MA, BTN_LED_VF["typ"], rled)
    totals[nled] = i_typ
    print(f"INFO  {tag}: typical {i_typ * 1e3:.2f} mA (Q drops {vds_typ:.2f} V); worst rail + min IOH 25 C + typ VF "
          f"{i_w_typvf * 1e3:.2f} mA; + max VF {i_w * 1e3:.2f} mA (Q drops {vds_w:.2f} V); at 85 C IOH {i_w85 * 1e3:.2f} mA")
    doc = DOC_LED_MA
    ck.close(f"{tag}: doc's figure ({doc * 1e3:.1f} mA) vs the typical current", i_typ * 1e3, doc * 1e3, 0.5, " mA")
    ck.check(f"{tag}: worst case (VDD {VDDS['low']:.2f} V, IOH min 25 C, max VFs) above the AQY212EH's max "
             f"operate current {AQY_IFON_MAX * 1e3:.1f} mA", i_w >= AQY_IFON_MAX,
             f"{i_w * 1e3:.2f} mA (with typ VFs {i_w_typvf * 1e3:.2f} mA)")
    ck.check(f"{tag}: typical current inside the AQY212EH's recommended {AQY_IF_REC[0] * 1e3:.0f}-"
             f"{AQY_IF_REC[1] * 1e3:.0f} mA", AQY_IF_REC[0] <= i_typ <= AQY_IF_REC[1], f"{i_typ * 1e3:.2f} mA")
    ck.check(f"{tag}: current below the AQY212EH LED abs max and the CD4013B's 100 mW per output transistor",
             i_typ < AQY_IF_ABS and vds_w * i_w < 0.1 and vds_typ * i_typ < 0.1,
             f"{i_typ * 1e3:.2f} mA, {vds_typ * i_typ * 1e3:.1f} mW")
    ck.check(f"{tag}: button LED lit at a sensible current (1-20 mA)", 1e-3 <= i_w and i_typ <= 20e-3,
             f"{i_w * 1e3:.2f} ... {i_typ * 1e3:.2f} mA")
    # turn-on / off at the actual current: ton roughly inversely proportional to IF (ASSUMED from the datasheet's
    # 'turn on time vs LED forward current' curve shape; the datasheet's figures are at IF = 5 mA)
    ton_typ = AQY_TON[0] * 5e-3 / i_typ
    ton_max = AQY_TON[1] * 5e-3 / max(i_w, 1e-6)
    ck.check(f"{tag}: doc 'about 1 ms on' vs turn-on at {i_typ * 1e3:.1f} mA", 0.5e-3 <= ton_typ <= 2e-3,
             f"typ ~{ton_typ * 1e3:.2f} ms, worst ~{ton_max * 1e3:.1f} ms (datasheet {AQY_TON[0] * 1e3:.0f} / "
             f"{AQY_TON[1] * 1e3:.0f} ms at 5 mA)")
    ck.check(f"{tag}: doc 'about 0.1 ms off' vs the datasheet turn-off", AQY_TOFF[0] <= 0.1e-3 <= AQY_TOFF[1],
             f"typ {AQY_TOFF[0] * 1e3:.2f} ms, max {AQY_TOFF[1] * 1e3:.1f} ms")
ck.check("mono and stereo button LEDs about equally bright (current ratio > 0.7)",
         min(totals.values()) / max(totals.values()) > 0.7,
         f"stereo / mono {min(totals.values()) / max(totals.values()):.2f}")
ck.check("doc: 'the AQY212EH needs 3 mA at most' = datasheet LED operate current max", AQY_IFON_MAX == 3.0e-3,
         f"datasheet IFon max {AQY_IFON_MAX * 1e3:.1f} mA (typ {AQY_IFON_TYP * 1e3:.1f}) at 25 C; recommended IF "
         f"{AQY_IF_REC[0] * 1e3:.0f}-{AQY_IF_REC[1] * 1e3:.0f} mA")

# what LED resistor would give >= 5 mA typical on a stereo channel and >= 3 mA at the worst case
for r in (1500, 1200, 1000, 820, 680):
    it, _ = drive(VDDS["typ"], "typ", 2, AQY_VF_TYP_5MA, BTN_LED_VF["typ"], r)
    iw, _ = drive(VDDS["low"], "min25", 2, AQY_VF_MAX, BTN_LED_VF["max"], r)
    im, _ = drive(VDDS["typ"], "typ", 1, AQY_VF_TYP_5MA, BTN_LED_VF["typ"], r)
    imw, _ = drive(VDDS["low"], "min25", 1, AQY_VF_MAX, BTN_LED_VF["max"], r)
    print(f"INFO  LED resistor {r} R: stereo typ {it * 1e3:.2f} mA, worst {iw * 1e3:.2f} mA; mono typ {im * 1e3:.2f} "
          f"mA, worst {imw * 1e3:.2f} mA")

# ESD note: BTN reaches the panel; the CMOS input sits behind 10k + 100n, the Q output behind the LED resistor
print("INFO  ESD: BTN_F runs to the panel button; the CD4093B input sees it only through the 10k / 100n debounce "
      "(a finger's ESD pulse is absorbed by the 100 nF), the CD4013B Q only through its LED resistor + LEDs: no extra parts needed")

ck.done()
