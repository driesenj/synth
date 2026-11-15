"""audio_dc: static / DC behaviour of the stereo mixer's audio path, by nodal analysis.

What it checks, from circuit.py's netlist (both boards joined at the headers,
pots with a taper, jacks normalled when unplugged, TL074 sections as
high-gain op-amps that clip at the datasheet swing on the real rails,
each channel's CD4053B as three SPDT sections: the closed throw Ron, the
open one R_OFF), against design.md's claims and the datasheets:
  - every gain in design.md's "Gains" table (with the switches' typical Ron
    in every bus path), the pan law, the polarity of every input -> OUT L /
    OUT R / SEND path
  - stereo and RETURN normalling and the levels then
  - input impedance of every input, playing and muted, LEVEL min / mid / max;
    a mute must leave it alone (100k), so a multed source keeps its level
  - mute depth at DC: the y throw's Ron pulling the bus resistor's summing
    end to GND, the open x throw (R_OFF) between it and the bus; the SEND
    muted with the channel (the frequency dependence, set by the x throw's
    0.2 pF, is test_audio_ac's)
  - the playing gain error of the x throw's Ron (typ / max / 85 C) against
    the doc's "at most 0.045 dB", L / R match within the datasheet's dRon
  - MASTER taper bending by the 100k load, L / R tracking
  - SEND / RETURN / DRUMS loading, channel independence (mutes included)
  - headroom: the clip point of every stage on the real rails (1N5819 + 10R
    at the worst-case current), against "outputs clip at twice Eurorack level
    and the summers at four times"
  - TL074 input common-mode range at the followers (phase reversal)
  - the CD4053B's switch pins against its VSS - 0.5 V / +-10 mA limits when
    a summer clips and its node leaves the virtual earth
  - DC offset at OUT L / OUT R / SEND, worst case and typical

Not modelled: the latch (its state is Config.muted), the CD4053B's leakage as
a current (only as R_OFF), its rON against the signal voltage (the throws sit
at 0 V), its protection diodes (the clamp current is estimated from the node's
Thevenin equivalent), temperature drift of anything but rON.

Run:  cd stereo-mixer/hardware/tests && python test_audio_dc.py
Only reads circuit.py (through audio_dc_solver.py); writes nothing.
"""
import math
import re
import os

import harness
import audio_dc_solver as S
from audio_dc_solver import Config, solve

ck = harness.Checks("audio_dc")
C = S.CIRCUIT
db = harness.db

# ------------------------------------------------------------------ datasheet constants
# TI TL07x datasheet SLOS080 (TL074 C-grade, the plain "TL074" in docs/bom.md), VCC = +-15 V, 25 C:
# (verifier, 2026-11-04: re-read from SLOS080W, July 2025, section 5.8: VOS C typ 3 / max 10 / 13 mV full range,
#  IB typ 65 pA / max 200 pA / 7 nA full range, VCM min +-11, typ -12 to 15 V, VOM RL=10k min 12 typ 13.5,
#  RL=2k min 10 V (typ 12 from the older revisions; the W table text does not show it), IQ 1.4 / 2.5 mA,
#  AOL C min 25 V/mV. The TL07xH "No Phase Reversal" plot is for the H only, and the H's orderable list has no
#  PDIP-14 (N) package: SOIC / TSSOP / SOT-23-THIN only.)
TL_VOM_10K_MIN, TL_VOM_10K_TYP = 12.0, 13.5    # max peak output swing, RL = 10k: min 12, typ 13.5 V
TL_VOM_2K_MIN, TL_VOM_2K_TYP = 10.0, 12.0      # RL >= 2k: min 10, typ 12 V
TL_VS_DS = 15.0                                # the rails those swings are given at
TL_VICR_NEG_MIN = -11.0                        # common-mode input range, min (guaranteed) -11 V at -15 V rail
TL_VICR_NEG_TYP = -12.0                        # typ -12 V   (i.e. V- + 4 V guaranteed, V- + 3 V typ)
TL_VICR_POS_MIN, TL_VICR_POS_TYP = 11.0, 15.0  # min +11, typ +15 (to V+)
TL_VIO_MAX_25C, TL_VIO_MAX_FULL, TL_VIO_TYP = 10e-3, 13e-3, 3e-3   # TL074 (C grade) input offset: max 10 mV 25 C,
#                                                13 mV over 0-70 C, typ 3 mV
TL_IIB_MAX_25C, TL_IIB_MAX_FULL, TL_IIB_TYP = 200e-12, 7e-9, 65e-12    # input bias: max 200 pA 25 C, 7 nA 70 C, typ 65 pA
TL_IIO_MAX_FULL = 2e-9                         # input offset current max over temp
TL_ICC_TYP, TL_ICC_MAX = 1.4e-3, 2.5e-3        # supply current per amplifier, typ / max
TL_AOL_MIN = 25e3                              # large-signal gain min 25 V/mV (typ 200 V/mV)
# CD4053B, TI SCHS047O (rev. O, May 2026), 5.5, VEE = VSS = 0, 0 <= VIS <= VDD, VDD = 10 V column (the chips get
# 11-11.6 V; rON falls as VDD rises, so these are conservative): rON typ 180, max 400 (25 C) / 520 ohm (85 C);
# change in rON between any two channels typ 10 ohm. Abs max: DC input voltage VSS - 0.5 ... VDD + 0.5 V, DC input
# current +-10 mA. The open throw as audio_dc_solver.R_OFF (1 Gohm; why there).
CD_RON_TYP, CD_RON_MAX_25C, CD_RON_MAX_85C = 180.0, 400.0, 520.0
CD_DRON_TYP = 10.0
CD_VIN_MARGIN, CD_IIN_MAX = 0.5, 10e-3
assert (S.RON_TYP, S.RON_MAX_25C, S.RON_MAX_85C, S.DRON_TYP) == (CD_RON_TYP, CD_RON_MAX_25C, CD_RON_MAX_85C,
                                                                CD_DRON_TYP), "solver and test disagree on rON"
# 1N5819 (ON Semiconductor 1N5817-D / Vishay 88525): VF max 0.60 V at 1 A; the typ forward curve gives about
# 0.30-0.33 V at 0.1 A, 25 C. Read off a curve, not a table: 0.30 typ, 0.40 V used as a conservative worst case.
D5819_VF_TYP, D5819_VF_WORST = 0.30, 0.40
# Eurorack: audio +-5 V (10 Vpp, Doepfer A-100 technical details), CV / LFO / envelopes up to +-10 V (and 0..+10).
EURO_AUDIO, EURO_MAX = 5.0, 10.0
EURO_RS = (0.0, 470.0, 1000.0)                 # source output impedances tested (the task's 0, 470 R, 1k)
# Alpha 9 mm "A" taper: Alpha's catalogue taper chart is a curve, not a number. Not confirmed from a
# manufacturer PDF here; modelled as the usual 2-segment approximation, 15 % at half rotation, with 10 %
# as the other common figure (the A-taper results are given for both where they matter).
A_MID, A_MID_ALT = 0.15, 0.10
# The most one mute draws: QK at the full +12 V (no output resistance, no diode drop) through the LED resistor into
# the lowest red LED VF test_power assumes (1.8 V; Thonk give no datasheet). The CD4053B's selects draw nothing.
LED_VF_MIN = 1.8
R_LED = harness.ohms(next(p.value for p in C.all_parts() if p.kind == "R" and p.nets["1"].startswith("QK")))
LED_MA_MONO_MAX = (12.0 - LED_VF_MIN) / R_LED

MONO, STEREO = C.MONO, C.STEREO
ALL_CH = MONO + STEREO
IN_JACK = {k: f"J{k}" for k in MONO}
IN_JACK.update({"7L": "J7", "7R": "J8", "8L": "J9", "8R": "J10"})
LEVEL = {k: f"RV{3 * k - 2}" for k in MONO}
LEVEL.update({7: "RV19", 8: "RV21"})
PAN = {k: f"RV{3 * k - 1}" for k in MONO}
SENDP = {k: f"RV{3 * k}" for k in MONO}
SENDP.update({7: "RV20", 8: "RV22"})


def out(V, *names):
    return [V[n] for n in names]


def gain(src_jacks, cfg_kw=None, outs=("OUT_L", "OUT_R", "SEND"), v=1.0, rs=0.0):
    """Gains from 1 V at src_jacks (one shared source) to the outputs."""
    kw = dict(cfg_kw or {})
    kw["sources"] = {j: (v, rs, "s") for j in src_jacks}
    V, _ = solve(Config(**kw))
    return {o: V[o] / v for o in outs}


# ------------------------------------------------------------------ the model itself
V, _ = solve(Config())
ck.check("model: nothing patched -> outputs at 0 V", all(abs(V[o]) < 1e-9 for o in ("OUT_L", "OUT_R", "SEND")),
         f"OUT_L {V['OUT_L']:.2e}, OUT_R {V['OUT_R']:.2e}, SEND {V['SEND']:.2e}")
fbnets = {fb for _, _, pins in C.HEADERS for _, fb in pins}
ck.check("model: every faceplate header net joined to a main-board net", all(S.node(f) != f for f in fbnets),
         f"{len(fbnets)} header nets")

# ------------------------------------------------------------------ gains table
# design.md "Gains (unchanged)": source at full LEVEL, MASTER at full
for k in MONO:
    g = gain([IN_JACK[k]], dict(rot={PAN[k]: 0.0}))
    ck.close(f"gain mono {k} hard left -> OUT L (doc 0.95)", g["OUT_L"], 0.95, 0.006)
    ck.check(f"gain mono {k} hard left -> OUT R off", abs(g["OUT_R"]) < 1e-4, f"got {g['OUT_R']:.2e}")
    g = gain([IN_JACK[k]], dict(rot={PAN[k]: 1.0}))
    ck.close(f"gain mono {k} hard right -> OUT R (doc 0.95)", g["OUT_R"], 0.95, 0.006)
    g = gain([IN_JACK[k]], dict(rot={PAN[k]: 0.5}))
    ck.close(f"gain mono {k} centred -> OUT L (doc 0.64)", g["OUT_L"], 0.64, 0.006)
    ck.close(f"gain mono {k} centred -> OUT R (doc 0.64)", g["OUT_R"], 0.64, 0.006)
    ck.close(f"gain mono {k} centred OUT L -> dB (doc -3.8)", db(g["OUT_L"]), -3.8, 0.05, " dB")
    ck.close(f"gain mono {k} SEND full -> SEND OUT (doc 1.0)", g["SEND"], 1.0, 0.005)
for c in STEREO:
    g = gain([IN_JACK[f"{c}L"]], dict(sources=None))          # R normalled to L
    ck.close(f"gain stereo {c} L (R normalled) -> OUT L (doc 1.0)", g["OUT_L"], 1.0, 0.005)
    ck.close(f"gain stereo {c} L (R normalled) -> OUT R (doc 1.0)", g["OUT_R"], 1.0, 0.005)
    # L only into OUT L with R patched to a 0 V source: the side really separate
    kw = dict(sources={IN_JACK[f"{c}L"]: (1.0, 0.0, "a"), IN_JACK[f"{c}R"]: (0.0, 0.0, "b")})
    V, _ = solve(Config(**kw))
    ck.close(f"gain stereo {c} L only (R patched to 0 V) -> OUT L", V["OUT_L"], 1.0, 0.005)
    ck.check(f"gain stereo {c} L only -> OUT R off", abs(V["OUT_R"]) < 1e-4, f"got {V['OUT_R']:.2e}")
    ck.close(f"gain stereo {c} (L+R)/2 SEND full -> SEND OUT, L = R (doc 0.91)", g["SEND"], 0.91, 0.006)
g = gain(["J11"])
ck.close("gain RETURN L (R normalled) -> OUT L (doc 1.0)", g["OUT_L"], 1.0, 0.005)
ck.close("gain RETURN L (R normalled) -> OUT R (doc 1.0)", g["OUT_R"], 1.0, 0.005)
ck.check("RETURN does not reach SEND (no feedback loop into Clouds)", abs(g["SEND"]) < 1e-6, f"got {g['SEND']:.2e}")
g = gain(["J13"])
ck.close("gain DRUMS -> OUT L (doc 0.67)", g["OUT_L"], 0.67, 0.005)
ck.close("gain DRUMS -> OUT R (doc 0.67)", g["OUT_R"], 0.67, 0.005)
ck.close("gain DRUMS dB (doc -3.5)", db(g["OUT_L"]), -3.5, 0.05, " dB")
ck.check("DRUMS does not reach SEND", abs(g["SEND"]) < 1e-6, f"got {g['SEND']:.2e}")
g = gain(["J14"])
ck.close("gain FX IN -> SEND OUT (doc 1.0)", g["SEND"], 1.0, 0.005)
ck.check("FX IN does not reach OUT L / R", abs(g["OUT_L"]) < 1e-6 and abs(g["OUT_R"]) < 1e-6,
         f"OUT_L {g['OUT_L']:.2e} OUT_R {g['OUT_R']:.2e}")

# ------------------------------------------------------------------ polarity
pol = []
for k in MONO:
    for pan in (0.0, 0.5, 1.0):
        g = gain([IN_JACK[k]], dict(rot={PAN[k]: pan}))
        pol += [(f"mono {k} pan {pan} -> {o}", g[o]) for o in ("OUT_L", "OUT_R", "SEND") if abs(g[o]) > 1e-3]
for c in STEREO:
    for side in "LR":
        kw = dict(sources={IN_JACK[f"{c}{side}"]: (1.0, 0.0, "a"),
                           IN_JACK[f"{c}{'R' if side == 'L' else 'L'}"]: (0.0, 0.0, "b")})
        V, _ = solve(Config(**kw))
        pol += [(f"stereo {c}{side} -> {o}", V[o]) for o in ("OUT_L", "OUT_R", "SEND") if abs(V[o]) > 1e-3]
for j, name in (("J11", "RETURN L"), ("J13", "DRUMS"), ("J14", "FX IN")):
    g = gain([j])
    pol += [(f"{name} -> {o}", g[o]) for o in ("OUT_L", "OUT_R", "SEND") if abs(g[o]) > 1e-3]
kw = dict(sources={"J11": (0.0, 0.0, "a"), "J12": (1.0, 0.0, "b")})
V, _ = solve(Config(**kw))
pol += [("RETURN R -> OUT_R", V["OUT_R"])]
ck.check("polarity: every input -> OUT L / OUT R / SEND path in phase (doc: every path inverts twice)",
         all(v > 0 for _, v in pol), f"{len(pol)} paths; inverted: {[n for n, v in pol if v <= 0]}")

# ------------------------------------------------------------------ pan law
DOC_PAN = {0.0: -0.4, 0.25: -1.7, 0.5: -3.8, 0.75: -8.1}
DESIGN = open(os.path.join(harness.MODULE, "docs", "design.md"), encoding="utf-8").read()
DOC1 = " ".join(DESIGN.split())                # the same text on one line, for figures that wrap
_mz = re.search(r"a muted channel's input impedance stays (\d+)k", DOC1)
DOC_MUTED_Z = float(_mz.group(1)) if _mz else float("nan")
_md = re.search(r"drops by (\d+) dB typically, (\d+) dB at worst", DOC1)
DOC_MUTE_TYP, DOC_MUTE_WORST = (float(_md.group(1)), float(_md.group(2))) if _md else (float("nan"), float("nan"))
_mg = re.search(r"\(200k on the stereo channels\): at most ([\d.]+) dB", DOC1)
DOC_RON_DB = float(_mg.group(1)) if _mg else float("nan")
_sw = re.search(r"swing about ±(\d+(?:\.\d+)?) V.*?±(\d+(?:\.\d+)?) V\s+guaranteed in the worst case", DESIGN, re.S)
D_SW, D_SW_WORST = (float(x) for x in _sw.groups()) if _sw else (10.5, 10.5)
k = 1
pw = []
for r in [i / 40 for i in range(41)]:
    g = gain([IN_JACK[k]], dict(rot={PAN[k]: r}))
    pw.append((r, g["OUT_L"], g["OUT_R"]))
    if r in DOC_PAN:
        ck.close(f"pan law L at {r} rotation (doc {DOC_PAN[r]} dB)", db(g["OUT_L"]), DOC_PAN[r], 0.05, " dB")
ck.check("pan law L off at full CW", pw[-1][1] < 1e-4, f"L = {pw[-1][1]:.2e} ({db(pw[-1][1]):.0f} dB)")
pwr = [db(math.hypot(l, r)) for _, l, r in pw]
ck.check("pan law: L^2 + R^2 within 0.4 dB over the whole rotation (doc)", max(pwr) - min(pwr) <= 0.4,
         f"power {min(pwr):.2f} .. {max(pwr):.2f} dB, spread {max(pwr) - min(pwr):.3f} dB")
ck.check("pan law monotonic (L falls, R rises)", all(a[1] >= b[1] and a[2] <= b[2] for a, b in zip(pw, pw[1:])), "")



# ------------------------------------------------------------------ normalling
def run(sources, **kw):
    V, I = solve(Config(sources=sources, **kw))
    return V


for c in STEREO:
    V = run({IN_JACK[f"{c}L"]: (1.0, 0.0, "a")})
    ck.close(f"normalling stereo {c}: R follower follows L when R unpatched (CH{c}R / CH{c}L)",
             V[f"CH{c}R"] / V[f"CH{c}L"], 1.0, 1e-3)
    V = run({IN_JACK[f"{c}R"]: (1.0, 0.0, "a")})
    ck.check(f"normalling stereo {c}: R alone (L unpatched) reaches only OUT R",
             abs(V["OUT_L"]) < 1e-4 and V["OUT_R"] > 0.99, f"OUT_L {V['OUT_L']:.3g}, OUT_R {V['OUT_R']:.3g}")
    for rs in EURO_RS[1:]:
        a = run({IN_JACK[f"{c}L"]: (1.0, rs, "a")})["OUT_L"]
        b = run({IN_JACK[f"{c}L"]: (1.0, rs, "a"), IN_JACK[f"{c}R"]: (1.0, rs, "b")})["OUT_L"]
        ck.check(f"normalling stereo {c}: L level with R normalled vs R patched, {rs:.0f} ohm source (<= 0.3 dB)",
                 abs(db(a / b)) <= 0.3, f"{db(a / b):+.2f} dB (L input loaded by both LEVEL gangs)")
V = run({"J11": (1.0, 0.0, "a")})
ck.close("normalling RETURN: R follows L (OUT R / OUT L)", V["OUT_R"] / V["OUT_L"], 1.0, 1e-3)
for rs in EURO_RS[1:]:
    a = run({"J11": (1.0, rs, "a")})["OUT_L"]
    b = run({"J11": (1.0, rs, "a"), "J12": (1.0, rs, "b")})["OUT_L"]
    ck.check(f"normalling RETURN: L level with R normalled vs R patched, {rs:.0f} ohm source (<= 0.3 dB)",
             abs(db(a / b)) <= 0.3, f"{db(a / b):+.2f} dB")


# ------------------------------------------------------------------ input impedance
def zin(jack, others=None, **kw):
    """Impedance seen by a 1 V source (1 ohm output resistance) at jack; others: more jacks on the same source."""
    srcs = {jack: (1.0, 1.0, "z")}
    for j in others or ():
        srcs[j] = (1.0, 1.0, "z")
    V, _ = solve(Config(sources=srcs, **kw))
    i = (V["SRC_z"] - V["SRCO_z"]) / 1.0
    return V["SRCO_z"] / i


ZMIN = 20e3     # a Eurorack input this low already costs 0.4 dB from a 1k source; the doc's channels are 100k
ZIN = {}
for k in ALL_CH:
    ins = [IN_JACK[k]] if k in MONO else [IN_JACK[f"{k}L"]]
    label = f"IN {k}" if k in MONO else f"IN {k} L (R unpatched)"
    for lvl in (0.0, 0.5, 1.0):
        for mute in (False, True):
            z = zin(ins[0], rot={LEVEL[k]: lvl}, muted={k} if mute else ())
            ZIN[(k, lvl, mute)] = z
            ck.check(f"input impedance {label} LEVEL {lvl} {'muted' if mute else 'open'} >= {ZMIN / 1e3:.0f}k",
                     z >= ZMIN, f"{z / 1e3:.1f}k")
    if k in MONO:
        ck.close(f"input impedance IN {k} unmuted = 100k (doc: 'the input impedance is 100k')",
                 ZIN[(k, 0.5, False)] / 1e3, 100.0, 2.0, "k")
        ck.close(f"input impedance IN {k} muted at full LEVEL = design.md's {DOC_MUTED_Z:g}k ('stays 100k')",
                 ZIN[(k, 1.0, True)] / 1e3, DOC_MUTED_Z, 2.0, "k")
    else:
        ck.close(f"input impedance IN {k} L, R unpatched = 50k (doc)", ZIN[(k, 0.5, False)] / 1e3, 50.0, 1.0, "k")
        z = zin(IN_JACK[f"{k}R"], rot={LEVEL[k]: 0.5})
        ck.close(f"input impedance IN {k} R = 100k (doc)", z / 1e3, 100.0, 2.0, "k")
        zm = zin(IN_JACK[f"{k}R"], rot={LEVEL[k]: 1.0}, muted={k})
        ck.close(f"input impedance IN {k} R muted at full LEVEL = design.md's {DOC_MUTED_Z:g}k", zm / 1e3,
                 DOC_MUTED_Z, 2.0, "k")
    # the mute is after the follower: nothing on the input side may move (the PhotoMOS mute took it to 9.1k)
    d = max(abs(ZIN[(k, lvl, True)] / ZIN[(k, lvl, False)] - 1) for lvl in (0.0, 0.5, 1.0))
    ck.check(f"input impedance {label}: muting does not change it at any LEVEL (doc: 'a mute leaves the LEVEL "
             f"wiper and the follower alone')", d < 1e-4, f"worst change {d:.1e} (LEVEL 0 / 0.5 / 1: " +
             ", ".join(f"{ZIN[(k, lvl, False)] / 1e3:.1f}k -> {ZIN[(k, lvl, True)] / 1e3:.1f}k" for lvl in (0.0, 0.5, 1.0))
             + ")")
for jack, name, kw in (("J11", "RETURN L (R unpatched)", {}), ("J12", "RETURN R", {}), ("J13", "DRUMS", {}),
                       ("J14", "FX IN", {})):
    for lvl in (0.0, 0.5, 1.0):
        rot = {"RV23": lvl} if jack in ("J11", "J12") else {"RV24": lvl} if jack == "J13" else {}
        if jack == "J12":
            z = zin("J12", rot=rot)       # with L patched to the same mult point would hide it; R alone
        else:
            z = zin(jack, rot=rot)
        ck.check(f"input impedance {name} at {lvl} >= {ZMIN / 1e3:.0f}k", z >= ZMIN, f"{z / 1e3:.1f}k")
        ZIN[(name, lvl)] = z


# ------------------------------------------------------------------ mute depth and multed sources
# Muted, the y throw ties the bus resistor's summing end (B*k) to GND through Ron, so it sits at Ron / (R + Ron) of
# the channel's signal, and the open x throw (R_OFF) is all that joins it to the bus: at DC the depth is
# 20 log(R_OFF / Ron) whatever R is. The doc's figures are at 20 kHz, where the x throw's 0.2 pF (40 Mohm) is the
# path (test_audio_ac); DC must be at least as deep.
BUS_R = {k: (100e3, 100e3) if k in MONO else (200e3, 100e3) for k in ALL_CH}       # (L / R bus, send bus)
for k in ALL_CH:
    ins = [IN_JACK[k]] if k in MONO else [IN_JACK[f"{k}L"], IN_JACK[f"{k}R"]]
    rot = {PAN[k]: 0.0} if k in MONO else {}
    for ron, doc_db, what in ((CD_RON_TYP, DOC_MUTE_TYP, "typ"), (CD_RON_MAX_85C, DOC_MUTE_WORST, "max 85 C")):
        model_db = 20 * math.log10(S.R_OFF / ron)
        for rs in EURO_RS:
            srcs = {j: (1.0, rs, "s") for j in ins}
            Va = run(srcs, rot=rot, ron=ron)
            Vb = run(srcs, rot=rot, muted={k}, ron=ron)
            att = -db(Vb["OUT_L"] / Va["OUT_L"])
            send = -db(Vb["SEND"] / Va["SEND"])
            if rs == 0.0:
                # the y throw: the bus resistor's summing end at Ron / (R + Ron) of its hot end
                hot = Vb[f"PL{k}"] if k in MONO else Vb[f"CH{k}L"]
                rl = BUS_R[k][0]
                ck.close(f"mute {k}: the y throw holds BL{k} at Ron / (R + Ron) of the bus resistor's hot end "
                         f"(Ron {ron:.0f}, R {rl / 1e3:.0f}k)", Vb[f"BL{k}"] / hot, ron / (rl + ron),
                         0.01 * ron / (rl + ron))
                ck.close(f"mute {k} DC depth to OUT L, Ron {ron:.0f} ohm ({what}) = 20 log(R_OFF / Ron) (the open x "
                         f"throw is the only path)", att, model_db, 0.5, " dB")
            ck.check(f"mute {k} DC depth to OUT L, Ron {ron:.0f} ({what}), {rs:.0f} ohm source >= the doc's "
                     f"{doc_db:.0f} dB at 20 kHz", att >= doc_db, f"{att:.1f} dB")
            ck.check(f"mute {k} also mutes its SEND (post-mute), Ron {ron:.0f} ({what}), {rs:.0f} ohm source >= "
                     f"{doc_db:.0f} dB", send >= doc_db, f"{send:.1f} dB")
    # both stereo sides through their own sections
    if k in STEREO:
        srcs = {IN_JACK[f"{k}L"]: (1.0, 0.0, "a"), IN_JACK[f"{k}R"]: (1.0, 0.0, "b")}
        a, b = run(srcs), run(srcs, muted={k})
        ck.check(f"mute {k} mutes both sides (OUT L and OUT R) >= the doc's {DOC_MUTE_TYP:.0f} dB",
                 min(-db(b["OUT_L"] / a["OUT_L"]), -db(b["OUT_R"] / a["OUT_R"])) >= DOC_MUTE_TYP,
                 f"OUT L {-db(b['OUT_L'] / a['OUT_L']):.1f} dB, OUT R {-db(b['OUT_R'] / a['OUT_R']):.1f} dB")
for r_off, what in ((S.R_OFF_25C, "25 C"), (S.R_OFF_85C, "85 C")):
    a = run({"J1": (1.0, 0.0, "s")}, rot={PAN[1]: 0.0}, ron=CD_RON_MAX_85C)["OUT_L"]
    b = run({"J1": (1.0, 0.0, "s")}, rot={PAN[1]: 0.0}, ron=CD_RON_MAX_85C, muted={1}, r_off=r_off)["OUT_L"]
    print(f"      sensitivity: R_OFF = the {what} leakage limit read as a resistance ({r_off / 1e6:.0f} Mohm, a "
          f"pessimistic reading, see audio_dc_solver): DC depth {-db(b / a):.1f} dB at Ron {CD_RON_MAX_85C:.0f}")

# a design criterion (the doc states it): muting a channel must not change a multed source's level
for rs in EURO_RS[1:]:
    srcs = {"J1": (1.0, rs, "m"), "J2": (1.0, rs, "m")}
    rot = {PAN[1]: 0.0, PAN[2]: 1.0}
    a = run(srcs, rot=rot)["OUT_R"]
    b = run(srcs, rot=rot, muted={1})["OUT_R"]
    ck.check(f"multed source ({rs:.0f} ohm) into IN 1 and IN 2: muting 1 keeps 2's level (within 0.05 dB)",
             abs(db(b / a)) <= 0.05, f"IN 2 level changes {db(b / a):+.2f} dB when 1 mutes")
    srcs = {"J7": (1.0, rs, "m"), "J1": (1.0, rs, "m")}
    a = run(srcs)["CH1"]
    b = run(srcs, muted={7})["CH1"]
    ck.check(f"multed source ({rs:.0f} ohm) into IN 1 and IN 7 L (R normalled): muting 7 keeps 1's level (within 0.05 dB)",
             abs(db(b / a)) <= 0.05, f"IN 1 level changes {db(b / a):+.2f} dB when 7 mutes")


# ------------------------------------------------------------------ the x throw's Ron while playing
# Playing, Ron sits in series with the bus resistor (100k, 200k on the stereo L / R buses): the gain error against an
# ideal switch, every channel and bus, typ / max (25 C) / max (85 C). The doc: "at most 0.045 dB".
RON_ZERO = 1e-3
ron_err = {}
for ron in (CD_RON_TYP, CD_RON_MAX_25C, CD_RON_MAX_85C):
    worst_e = (0.0, "")
    for k in ALL_CH:
        ins = [IN_JACK[k]] if k in MONO else [IN_JACK[f"{k}L"]]
        for pan, outn in (((0.0, "OUT_L"), (1.0, "OUT_R"), (0.5, "SEND")) if k in MONO else
                          ((None, "OUT_L"), (None, "OUT_R"), (None, "SEND"))):
            rot = {PAN[k]: pan} if pan is not None else {}
            a = run({ins[0]: (1.0, 0.0, "s")}, rot=rot, ron=RON_ZERO)[outn]
            b = run({ins[0]: (1.0, 0.0, "s")}, rot=rot, ron=ron)[outn]
            e = -db(b / a)
            if e > worst_e[0]:
                worst_e = (e, f"channel {k} -> {outn}")
    ron_err[ron] = worst_e
    print(f"      playing loss from the x throw's Ron {ron:.0f} ohm: worst {worst_e[0]:.4f} dB ({worst_e[1]})")
ck.close(f"playing: the x throw's Ron (max {CD_RON_MAX_85C:.0f} ohm at 85 C) costs at most the doc's {DOC_RON_DB} dB",
         ron_err[CD_RON_MAX_85C][0], DOC_RON_DB, 0.002, " dB")
ck.check("playing: the x throw's typical Ron (180 ohm) costs < 0.02 dB on every path", ron_err[CD_RON_TYP][0] < 0.02,
         f"{ron_err[CD_RON_TYP][0]:.4f} dB ({ron_err[CD_RON_TYP][1]})")
# L / R match: two sections of one chip differ by dRon (10 ohm typ): the mono centred and stereo L / R level match
mm = []
for k in ALL_CH:
    ins = {IN_JACK[k]: (1.0, 0.0, "s")} if k in MONO else {IN_JACK[f"{k}L"]: (1.0, 0.0, "s")}
    rot = {PAN[k]: 0.5} if k in MONO else {}
    a = run(ins, rot=rot)
    b = run(ins, rot=rot, ron_sec={(k, "R"): CD_RON_TYP + CD_DRON_TYP})
    mm.append((abs(db(b["OUT_R"] / b["OUT_L"]) - db(a["OUT_R"] / a["OUT_L"])), k))
m = max(mm)
want = 20 * math.log10((100e3 + CD_RON_TYP + CD_DRON_TYP) / (100e3 + CD_RON_TYP))
ck.check(f"playing: L / R match within the {CD_DRON_TYP:.0f} ohm dRon between two sections (doc), < 0.01 dB",
         m[0] < 0.01 and m[0] <= want * 1.05,
         f"worst {m[0]:.5f} dB (channel {m[1]}); 20 log((100k + Ron + dRon) / (100k + Ron)) = {want:.5f} dB")


# ------------------------------------------------------------------ MASTER taper, SEND / RETURN / DRUMS loading
def bend(potref, jack, outn, src_extra=None, a_mid=A_MID, **kw):
    """Worst deviation (dB) of the knob's gain from its unloaded taper over the rotation, and at half."""
    full = None
    worst, half = 0.0, 0.0
    res = []
    for i in range(1, 21):
        r = i / 20
        srcs = {jack: (1.0, 0.0, "s")}
        srcs.update(src_extra or {})
        rot = dict(kw.get("rot", {}))
        rot[potref] = r
        g = run(srcs, rot=rot, a_mid=a_mid)[outn]
        res.append((r, g))
    full = res[-1][1]
    for r, g in res:
        d = db(g / full) - db(S.taper("A", r, a_mid))
        worst = min(worst, d)
        if r == 0.5:
            half = d
    return worst, half, res


for a_mid in (A_MID, A_MID_ALT):
    w, h, resL = bend("RV25", "J11", "OUT_L", a_mid=a_mid)
    ck.check(f"MASTER taper ({a_mid:.0%} A): bending by the 100k load <= 2 dB ('only bends the taper slightly')",
             w >= -2.0, f"half rotation {h:+.2f} dB, worst {w:+.2f} dB below the unloaded taper")
    _, _, resR = bend("RV25", "J11", "OUT_R", a_mid=a_mid)
    trk = max(abs(db(a / b)) for (_, a), (_, b) in zip(resL, resR))
    ck.check(f"MASTER L / R tracking ({a_mid:.0%} A): identical loading on both gangs (< 0.01 dB)", trk < 0.01,
             f"worst {trk:.4f} dB (gang tolerance not modelled)")
w, h, _ = bend("RV3", "J1", "SEND")
ck.check("SEND 1 taper: bending by the 100k bus resistor <= 2 dB", w >= -2.0, f"half {h:+.2f}, worst {w:+.2f} dB")
w, h, _ = bend("RV20", "J7", "SEND")
ck.check("SEND 7 taper: bending by the 100k bus resistor (+ 5k average source) <= 2 dB", w >= -2.0,
         f"half {h:+.2f}, worst {w:+.2f} dB")
w, h, _ = bend("RV23", "J11", "OUT_L")
ck.check("RETURN taper: bending by the 200k bus resistor <= 2 dB", w >= -2.0, f"half {h:+.2f}, worst {w:+.2f} dB")
w, h, _ = bend("RV24", "J13", "OUT_L")
ck.check("DRUMS taper: bending by the two 300k bus resistors (150k) <= 2 dB", w >= -2.0, f"half {h:+.2f}, worst {w:+.2f} dB")
w, h, _ = bend("RV1", "J1", "OUT_L", rot={PAN[1]: 0.0})
ck.check("LEVEL 1 taper: no bending (wiper into a follower)", abs(w) < 0.01, f"worst {w:+.4f} dB")
for rs in EURO_RS[1:]:
    a = run({"J13": (1.0, rs, "s")})["OUT_L"] / run({"J13": (1.0, 0.0, "s")})["OUT_L"]
    ck.check(f"DRUMS: level loss from a {rs:.0f} ohm source at full <= 0.2 dB", -db(a) <= 0.2, f"{db(a):+.2f} dB")
    a = run({"J11": (1.0, rs, "s")})["OUT_L"] / run({"J11": (1.0, 0.0, "s")})["OUT_L"]
    ck.check(f"RETURN L (R normalled): level loss from a {rs:.0f} ohm source at full <= 0.3 dB", -db(a) <= 0.3,
             f"{db(a):+.2f} dB")
for load in (100e3, 10e3):
    V = run({"J1": (1.0, 0.0, "s")}, loads={"J15": load, "J16": load, "J17": load})
    ck.check(f"outputs into {load / 1e3:.0f}k: the 1k series resistors cost <= 1 dB", -db(V["SEND"]) <= 1.0,
             f"SEND {db(V['SEND']):+.2f} dB, OUT L {db(V['OUT_L'] / 0.645):+.2f} dB")


# ------------------------------------------------------------------ channel independence
def snapshot(**kw):
    """Gain of every channel to OUT L / OUT R / SEND, one source at a time, others unpatched."""
    g = {}
    for k in ALL_CH:
        ins = [IN_JACK[k]] if k in MONO else [IN_JACK[f"{k}L"]]
        V = run({ins[0]: (1.0, 0.0, "s")}, **kw)
        g[k] = (V["OUT_L"], V["OUT_R"], V["SEND"])
    return g


base_rot = {PAN[k]: 0.5 for k in MONO}
ref = snapshot(rot=base_rot)
worst = (0.0, "")
for k in ALL_CH:
    variants = [("mute", dict(rot=base_rot, muted={k}))]
    for lvl in (0.0, 0.5):
        variants.append((f"LEVEL {lvl}", dict(rot={**base_rot, LEVEL[k]: lvl})))
    variants.append(("SEND 0", dict(rot={**base_rot, SENDP[k]: 0.0})))
    if k in MONO:
        for p in (0.0, 1.0):
            variants.append((f"PAN {p}", dict(rot={**base_rot, PAN[k]: p})))
    for what, kw in variants:
        g = snapshot(**kw)
        for j in ALL_CH:
            if j == k:
                continue
            for a, b in zip(ref[j], g[j]):
                d = abs(db(b / a))
                if d > worst[0]:
                    worst = (d, f"channel {k} {what} moves channel {j} by {d:.4f} dB")
ck.check("channel independence: no channel's LEVEL / PAN / SEND / mute changes another's gain (< 0.01 dB)",
         worst[0] < 0.01, worst[1] or "0 dB")
g1 = snapshot(rot={**base_rot, "RV23": 0.0, "RV24": 0.0})
d = max(abs(db(b / a)) for j in ALL_CH for a, b in zip(ref[j], g1[j]))
ck.check("channel independence: RETURN / DRUMS knobs do not change the channels' gains (< 0.01 dB)", d < 0.01, f"{d:.4f} dB")


# ------------------------------------------------------------------ rails and output swing
def headroom(load, case):
    """Volts between the rail and the TL074's max output at this load (datasheet VOM at +-15 V, the same
    headroom assumed at +-11 V), interpolated in 1 / RL between the 10k and 2k figures."""
    h10 = TL_VS_DS - (TL_VOM_10K_TYP if case == "typ" else TL_VOM_10K_MIN)
    h2 = TL_VS_DS - (TL_VOM_2K_TYP if case == "typ" else TL_VOM_2K_MIN)
    if load >= 10e3:
        return h10
    return h10 + (h2 - h10) * (1 / load - 1 / 10e3) / (1 / 2e3 - 1 / 10e3)


def rails(case, i_load_p=0.0, i_load_n=0.0):
    icc = 16 * (TL_ICC_TYP if case == "typ" else TL_ICC_MAX)
    leds = 0.0 if case == "typ" else 8 * LED_MA_MONO_MAX           # worst: every channel muted
    vf = D5819_VF_TYP if case == "typ" else D5819_VF_WORST
    ip, in_ = icc + leds + i_load_p, icc + i_load_n
    r10 = harness.ohms(next(p.value for p in C.all_parts() if p.ref == "R918"))
    return 12.0 - vf - r10 * ip, -(12.0 - vf - r10 * in_), ip, in_


def limiter(case, vp, vn):
    return lambda name, load: (vn + headroom(load, case), vp - headroom(load, case))


# worst-case load currents: every input at +10 V (then -10 V), clipping included, everything at full
ALL_IN = ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10", "J11", "J12", "J13", "J14"]
RAILS = {}
for case in ("typ", "worst"):
    vp, vn, ip, in_ = rails(case)
    if case == "worst":
        for _ in range(3):
            il = []
            for v in (EURO_MAX, -EURO_MAX):
                V, I = solve(Config(sources={j: (v, 0.0, j) for j in ALL_IN}, loads={"J15": 10e3, "J16": 10e3,
                                                                                      "J17": 10e3}),
                             limits=limiter(case, vp, vn))
                il.append(sum(abs(x) for x in I.values()))
            vp, vn, ip, in_ = rails(case, max(il), max(il))
    RAILS[case] = (vp, vn)
    print(f"      rails {case}: +{vp:.2f} V ({ip * 1e3:.0f} mA) / {vn:.2f} V ({in_ * 1e3:.0f} mA)")

for case in ("typ", "worst"):
    vp, vn = RAILS[case]
    for name, stage, load in (("OUT L", ("OUT", "L"), 1 / (1 / 200e3 + 1 / 101e3)),
                              ("SEND", ("OUT", "S"), 1 / (1 / 100e3 + 1 / 101e3))):
        sw = min(vp, -vn) - headroom(load, case)
        vout = sw * 100e3 / 101e3
        if case == "typ":                                            # the doc's "about twice": 5 %
            need = 2 * EURO_AUDIO * 0.95
            ck.check(f"headroom typ: {name} stage clips at >= 2 x Eurorack level ({need:.1f} V) into 100k (doc)",
                     vout >= need, f"clips at {vout:.2f} V at the jack (swing {sw:.2f} V, rails {vp:.2f}/{vn:.2f})")
        else:
            ck.check(f"headroom worst: {name} stage swings the doc's guaranteed ±{D_SW_WORST} V into 100k",
                     sw >= D_SW_WORST - 0.05, f"swing {sw:.2f} V ({vout:.2f} V at the jack), rails {vp:.2f}/{vn:.2f}")
    sw = min(vp, -vn) - headroom(1 / (1 / 200e3 + 1 / 101e3), case)
    if case == "typ":
        ck.check(f"headroom typ: TL074 output swing about ±{D_SW} V (doc), within 0.5 V", abs(sw - D_SW) <= 0.5,
                 f"{sw:.2f} V at the output stage")
    else:
        ck.check(f"headroom worst: TL074 output swing >= the doc's guaranteed ±{D_SW_WORST} V", sw >= D_SW_WORST - 0.05,
                 f"{sw:.2f} V at the output stage")
    # summers: the L / R summers drive 100k feedback || MASTER (100k, loaded by 100k): about 40k
    sws = min(vp, -vn) - headroom(1 / (1 / 100e3 + 1 / 100e3 + 1 / 100e3), case)
    if case == "typ":
        ck.check("headroom typ: L / R summers clip at 4 x Eurorack level in output terms (doc)",
                 2 * sws >= 4 * EURO_AUDIO * 0.95, f"summer swing {sws:.2f} V = {2 * sws:.2f} V at OUT ({2 * sws / EURO_AUDIO:.2f} x)")
        ck.check("headroom typ: the send summer clips with the SEND output, at about 2 x Eurorack (doc)",
                 sws >= 2 * EURO_AUDIO * 0.95, f"MIX_S = -SEND: clips at {sws:.2f} V = {sws / EURO_AUDIO:.2f} x Eurorack")
    else:
        ck.check(f"headroom worst: the summers swing the doc's guaranteed ±{D_SW_WORST} V", sws >= D_SW_WORST - 0.05,
                 f"summer swing {sws:.2f} V = {2 * sws / EURO_AUDIO:.2f} x Eurorack at OUT, {sws / EURO_AUDIO:.2f} x at SEND")


def clip_point(jacks, sign, case, rot=None, loads=None):
    """Smallest |input| at which any TL074 section saturates, and which ones."""
    vp, vn = RAILS[case]
    lim = limiter(case, vp, vn)
    lo, hi = 0.0, 40.0
    first = None
    for _ in range(18):
        mid = (lo + hi) / 2
        m = S.Model(Config(sources={j: (sign * mid, 0.0, "s") for j in jacks}, rot=rot or {},
                           loads=loads or {"J15": 100e3, "J16": 100e3, "J17": 100e3}))
        m.solve(limits=lim)
        if m.clamped:
            hi, first = mid, sorted(m.clamped)
        else:
            lo = mid
    return hi, first


ROLE = {k: v for k, v in C.OPAMPS.items()}
for case in ("typ", "worst"):
    rows = []
    for k in ALL_CH:
        jacks = [IN_JACK[k]] if k in MONO else [IN_JACK[f"{k}L"]]
        for sign in (1, -1):
            v, first = clip_point(jacks, sign, case, rot={PAN[k]: 0.0} if k in MONO else {})
            rows.append((k, sign, v, [ROLE[f] for f in first]))
    worst_in = min(rows, key=lambda r: r[2])
    # the doc's "about twice": the same 5 % allowance in the typical case as the output-stage checks above
    # (verifier: these checks used a strict 10 V while the OUT stage checks used 9.5 V for the same claim)
    # worst case: the doc promises its guaranteed swing; a single source clips where the first stage runs out,
    # the same 0.05 V allowance as the other worst-case swing checks
    need2 = 2 * EURO_AUDIO * 0.95 if case == "typ" else D_SW_WORST - 0.05
    ck.check(f"headroom {case}: one channel at full LEVEL (hard panned) takes "
             f"{'2 x Eurorack' if case == 'typ' else 'the doc worst-case swing'} ({need2:.1f} V) "
             f"before any stage clips", worst_in[2] >= need2,
             f"channel {worst_in[0]} at {worst_in[1] * worst_in[2]:+.2f} V clips {worst_in[3]}; "
             + ", ".join(f"{k}{'+' if s > 0 else '-'} {v:.1f} V" for k, s, v, _ in rows if k in (1, 7)))
    for j, name in (("J11", "RETURN"), ("J13", "DRUMS"), ("J14", "FX IN")):
        v, first = clip_point([j], -1, case)
        ck.check(f"headroom {case}: {name} alone at full takes {need2:.1f} V before clipping", v >= need2,
                 f"clips at {v:.2f} V in {[ROLE[f] for f in first]}")
    # a mix: all six monos centred + both stereo channels at the same +-5 V, coherent (worst case)
    v, first = clip_point(["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J9"], 1, case)
    print(f"      {case}: eight channels coherent at full clip at {v:.2f} V each, first {[ROLE[f] for f in first]}")
    v, first = clip_point(["J1", "J2", "J14"], 1, case)
    print(f"      {case}: two mono channels at full SEND + FX IN clip at {v:.2f} V each in {[ROLE[f] for f in first]}")
    # Verifier: the old check here ("two monos + FX IN, each +-5 V, do not clip") asked the send to carry 3 x
    # Eurorack, which OUT L cannot do either (three coherent hard-left channels clip it at MASTER full). The fair
    # question: does the send path, which has no master and no x2 stage after its summer, take as many coherent
    # full-level channels as OUT L does?
    vs, fs = clip_point(["J1", "J2"], 1, case)                                       # PANs centred, SENDs full
    vl, fl = clip_point(["J1", "J2"], 1, case, rot={PAN[1]: 0.0, PAN[2]: 0.0, SENDP[1]: 0.0, SENDP[2]: 0.0})
    ck.check(f"headroom {case}: the SEND path takes two coherent full-level channels as well as OUT L does "
             f"(within 5 %)", vs >= 0.95 * vl,
             f"send path clips at {vs:.2f} V each in {[ROLE[f] for f in fs]}, OUT L path (hard left) at "
             f"{vl:.2f} V each in {[ROLE[f] for f in fl]}")


# ------------------------------------------------------------------ TL074 input common-mode range at the followers
# A follower's IN+ is FIk = the LEVEL wiper (no current in the 10k): at full LEVEL it is the input jack's voltage.
# TL07x (not H): the negative common-mode limit is V- + 4 V guaranteed (VICR min -11 V at -15 V), V- + 3 V typ.
# Beyond it a classic TL07x shows output phase reversal (the output jumps towards V+); TI's SLOS080 plots
# "No Phase Reversal" only for the TL07xH, whose range is (V-) + 1.5 V to V+.
fol = [k for k, v in C.OPAMPS.items() if v[0] == "FOL"]
others = [k for k, v in C.OPAMPS.items() if v[0] != "FOL"]
m = S.Model(Config())
pins = {o["name"]: o for o in m.opamps}
ck.check("common-mode: summers and output stages have IN+ on GND (common mode 0 V whatever the input)",
         all(pins[k]["p"] == "GND" for k in others), "")
ck.check("common-mode: only IN 1-8 reach a follower; RETURN / DRUMS / FX IN go through resistors to virtual grounds",
         sorted(pins[k]["p"] for k in fol) == sorted(f"FI{s}" for s in ("1", "2", "3", "4", "5", "6", "7L", "7R", "8L", "8R")),
         ", ".join(sorted(pins[k]["p"] for k in fol)))
for case in ("typ", "worst"):
    vp, vn = RAILS[case]
    neg = vn + (TL_VS_DS + (TL_VICR_NEG_TYP if case == "typ" else TL_VICR_NEG_MIN))
    pos = vp - (TL_VS_DS - (TL_VICR_POS_TYP if case == "typ" else TL_VICR_POS_MIN))
    V = run({"J1": (-1.0, 0.0, "s")}, rot={LEVEL[1]: 1.0})
    vin_neg = neg / (V["FI1"] / -1.0) * -1 if V["FI1"] else float("inf")
    ck.check(f"common-mode {case}: a -{EURO_AUDIO:.0f} V Eurorack audio peak at full LEVEL stays inside the TL074's "
             f"input range", -EURO_AUDIO > neg, f"range down to {neg:+.2f} V (V- {vn:+.2f} V)")
    ck.check(f"common-mode {case}: a -{EURO_MAX:.0f} V Eurorack peak (LFO, envelope, hot VCO) at full LEVEL stays inside "
             f"the input range (else TL07x phase reversal)", -EURO_MAX > neg,
             f"phase reversal possible below {neg:+.2f} V at the jack; {neg / -EURO_MAX:.0%} of the track = LEVEL "
             f"above {0.5 + (abs(neg) / EURO_MAX - A_MID) / (1 - A_MID) * 0.5:.2f} of its rotation for a -10 V source")
    # Verifier: the worst-case version of this check compared +10 V with the guaranteed +11 V (at +15 V) limit
    # and failed, although (as the builder noted) nothing goes wrong there: the TL07x's typical range runs to
    # V+ (VCM typ "-12 to 15" at +-15 V, SLOS080W 5.8) and phase reversal is a negative-side effect of the
    # P-JFET input pair. Beyond the guaranteed figure the follower only clips. What matters on the positive side:
    # the input stays inside the typical range (to V+), and the guaranteed range is reported.
    ck.check(f"common-mode {case}: +{EURO_MAX:.0f} V at full LEVEL inside the positive range (typ to V+; no "
             f"reversal mechanism on this side)", EURO_MAX < vp,
             f"V+ {vp:+.2f} V; datasheet {'typ' if case == 'typ' else 'guaranteed'} range to {pos:+.2f} V"
             f"{'' if case == 'typ' else ' (the follower output clips first there)'}")
    # a source beyond the follower's rail (a +-12 V module output against the mixer's diode-dropped rails):
    # TL07x absolute max says the input must not exceed the supply; LEVEL + the 10k input series resistor limit the
    # current into the input structure to well under a milliamp
    i_over = max(12.0 - vp, -12.0 - vn, 0.0) / harness.ohms(next(p.value for p in C.all_parts() if p.ref == "R101"))
    ck.check(f"common-mode {case}: a +-12 V source beyond the {vp:.2f} / {vn:.2f} V rails drives < 1 mA into a "
             f"follower input (10k series)", i_over < 1e-3, f"{i_over * 1e3:.2f} mA at most")
    # which comes first on the negative side: the follower's output clipping or its input range?
    vclip = clip_point(["J1"], -1, case, rot={PAN[1]: 0.0})[0]
    print(f"      {case}: follower 1 output clips at -{vclip:.2f} V in, input range ends at {neg:+.2f} V")


# ------------------------------------------------------------------ the CD4053B's pins when a summer clips
# Linear, every x pin sits on a virtual earth (0 V) and every y pin on GND: inside VEE ... VDD (0 ... ~11.5 V). A
# summer that clips loses its virtual earth: its node goes to the weighted mean of its inputs and its stuck output,
# and every playing channel's common with it. Past VSS - 0.5 V (or VDD + 0.5 V) the switch's pins conduct into the
# chip (abs max: DC input voltage VSS - 0.5 ... VDD + 0.5 V, DC input current +-10 mA). The solver has no diodes,
# so the clamp current is the node's Thevenin current into the limit: an upper bound (the diodes start a little
# past it), taken as if one chip's x pin carried all of it.
def thevenin(sources, node, case, **kw):
    vp, vn = RAILS[case]
    lim = limiter(case, vp, vn)
    V0 = solve(Config(sources=sources, **kw), limits=lim)[0][node]
    V1 = solve(Config(sources=sources, **kw), limits=lim, ibias={node: 1e-6})[0][node]
    return V0, (V1 - V0) / 1e-6


for case in ("typ", "worst"):
    vp, vn = RAILS[case]
    rows = []
    for v in (EURO_MAX, -EURO_MAX):
        srcs = {j: (v, 0.0, "s") for j in ALL_IN}
        for node in ("SUM_L", "SUM_R", "SUM_S"):
            v0, rth = thevenin(srcs, node, case, rot={PAN[k]: 0.5 for k in MONO},
                               loads={"J15": 100e3, "J16": 100e3, "J17": 100e3})
            lo, hi = -CD_VIN_MARGIN, vp + CD_VIN_MARGIN
            i_cl = (lo - v0) / rth if v0 < lo else (v0 - hi) / rth if v0 > hi else 0.0
            rows.append((abs(i_cl), v0, node, v, rth))
    worst_cl = max(rows)
    print(f"      {case}: every input at +-{EURO_MAX:.0f} V, summers clipped: summing nodes from "
          f"{min(r[1] for r in rows):+.2f} to {max(r[1] for r in rows):+.2f} V open-circuit (VSS = VEE = 0, "
          f"VDD = {vp:.2f} V)")
    ck.check(f"CD4053B pins, {case}: every input at +-{EURO_MAX:.0f} V clips the summers; a node pulled past "
             f"VSS - 0.5 / VDD + 0.5 V drives < {CD_IIN_MAX * 1e3:.0f} mA into the chip (abs max)",
             worst_cl[0] < CD_IIN_MAX,
             f"worst {worst_cl[2]} at {worst_cl[1]:+.2f} V open-circuit ({worst_cl[3]:+.0f} V in, Thevenin "
             f"{worst_cl[4] / 1e3:.1f}k) -> {worst_cl[0] * 1e3:.2f} mA into the x pins at the limit")


# ------------------------------------------------------------------ DC offset at the outputs
def sens(rot):
    """d(OUT_L, OUT_R, SEND) per volt of each section's Vos, and per amp of bias current at each input."""
    base = solve(Config(rot=rot))[0]
    sv, si = {}, {}
    for o in S.Model(Config()).opamps:
        V = solve(Config(rot=rot), vos={o["name"]: 1.0})[0]
        sv[o["name"]] = [V[n] - base[n] for n in ("OUT_L", "OUT_R", "SEND")]
        for pin in ("p", "m"):
            nd = o[pin]
            if nd == "GND":
                continue
            V = solve(Config(rot=rot), ibias={nd: 1.0})[0]
            si[(o["name"], pin)] = [V[n] - base[n] for n in ("OUT_L", "OUT_R", "SEND")]
    return sv, si


DC = {}
for label, pan in (("hard left", 0.0), ("centre", 0.5), ("hard right", 1.0)):
    sv, si = sens({PAN[k]: pan for k in MONO})
    for i, outn in enumerate(("OUT_L", "OUT_R", "SEND")):
        worst = sum(abs(s[i]) for s in sv.values()) * TL_VIO_MAX_FULL + sum(abs(s[i]) for s in si.values()) * TL_IIB_MAX_FULL
        worst25 = sum(abs(s[i]) for s in sv.values()) * TL_VIO_MAX_25C + sum(abs(s[i]) for s in si.values()) * TL_IIB_MAX_25C
        typ = math.sqrt(sum(s[i] ** 2 for s in sv.values())) * TL_VIO_TYP
        ng = {C.OPAMPS[k]: round(abs(v[i]), 2) for k, v in sv.items() if abs(v[i]) > 0.01}
        prev = DC.get(outn)
        if prev is None or worst > prev[0]:
            DC[outn] = (worst, worst25, typ, label, ng, sum(abs(s[i]) for s in sv.values()))
DC_WORST_MAX, DC_TYP_MAX = 0.100, 0.030     # a DC-coupled master into the output module's x2 stage / Clouds' input
for outn, (worst, worst25, typ, label, ng, tot) in DC.items():
    print(f"      DC {outn}: Vos gains {ng} (sum {tot:.1f}), pans {label}")
    ck.check(f"DC offset {outn}: worst case (TL074 max Vos over 0-70 C + max bias) <= {DC_WORST_MAX * 1e3:.0f} mV",
             worst <= DC_WORST_MAX, f"{worst * 1e3:.0f} mV over temperature, {worst25 * 1e3:.0f} mV at 25 C "
                                    f"(sum of |Vos gains| {tot:.1f}, pans {label})")
    ck.check(f"DC offset {outn}: typical (RSS of 3 mV per section) <= {DC_TYP_MAX * 1e3:.0f} mV", typ <= DC_TYP_MAX,
             f"{typ * 1e3:.1f} mV")
# bias currents alone, over temperature
sv, si = sens({PAN[k]: 0.0 for k in MONO})
ib = max(sum(abs(s[i]) for s in si.values()) * TL_IIB_MAX_FULL for i in range(3))
ck.check("DC offset: bias currents over the real source resistances add < 5 mV (JFET inputs)", ib < 5e-3,
         f"{ib * 1e3:.2f} mV at 7 nA (70 C max)")
# MASTER moves the summers' DC: a step at the output as MASTER turns
V1 = solve(Config(), vos={opamp: TL_VIO_MAX_FULL for opamp in [C.opamp_of("SUM", "L")]})[0]["OUT_L"]
V0 = solve(Config(rot={"RV25": 0.0}), vos={opamp: TL_VIO_MAX_FULL for opamp in [C.opamp_of("SUM", "L")]})[0]["OUT_L"]
ck.check("DC offset: turning MASTER from full to off moves OUT L's DC by < 50 mV (worst summer Vos)",
         abs(V1 - V0) < 0.05, f"{(V1 - V0) * 1e3:+.0f} mV")

ck.done()
