"""Stereo mixer: the voice case's stereo master, built the Marblesy way: two
stacked PCBs behind a 28HP panel, Thonk panel parts. The whole circuit as
one netlist, split over the two boards.

Faceplate board (FB): 17 Thonkiconn jacks, 21 Alpha 9 mm pots, 4 Alpha
9 mm dual-gang pots, 8 Thonk LED buttons (the mutes), male headers.
Main board (MB): 4 TL074 (followers, bus summers, output stages), the mute
latch (2 CD4093 Schmitt NANDs, 4 CD4013 flip-flops), 10 AQY212EH PhotoMOS
mute switches, every resistor standing up, the Eurorack power entry,
female sockets.

Signal flow (unchanged from the 2026-10-07 design, mutes now electronic)
  mono k (1-6)   IN k -> LEVEL k (A100k) -> 10k -> follower -> CHk
                 PhotoMOS from the follower input to GND = mute (lit button)
                 CHk -> 10k -> PLk -> 100k -> SUM_L     PAN k (B10k) PLk..PRk,
                 CHk -> 10k -> PRk -> 100k -> SUM_R     wiper to GND
                 CHk -> SEND k (A100k) -> 100k -> SUM_S
  stereo c (7,8) IN c L/R (R takes L unpatched) -> LEVEL c (dual A100k) ->
                 10k -> followers -> 200k into each bus; 10k + 10k average
                 -> SEND c -> 100k -> SUM_S; one button mutes both sides
  RETURN L/R (R takes L) -> dual A100k -> 200k into each bus
  DRUMS -> A100k -> 300k into each bus (centred); FX IN -> 100k -> SUM_S
  SUM_L/R/S: inverting summers, 100k || 22p
  MASTER (dual A100k) -> x2 inverting stages -> 1k -> OUT L / OUT R
  SUM_S -> unity inverter -> 1k -> SEND

Mute latch, per channel
  button contacts to GND_F, 100k pull-up to +12 V -> 10k / 100n debounce ->
  CD4093 NAND (inputs tied: a Schmitt inverter) -> CD4013 clock, D = /Q
  (toggle). Q high = muted: Q -> 1.5k -> PhotoMOS LED(s) -> button LED ->
  GND_F, about 4-5 mA. RESET of every flip-flop from one power-on RC, so
  the mixer starts unmuted.

Net naming: nets that cross the board-to-board headers carry the same name
on both boards, with _F on the faceplate side (GND -> GND_F). The faceplate
has only panel parts, the main board everything else.
"""
import collections


class Part:
    def __init__(self, ref, kind, value="", nets=None, label=""):
        self.ref, self.kind, self.value, self.nets, self.label = ref, kind, value, dict(nets or {}), label

    def __repr__(self):
        return f"Part({self.ref} {self.kind} {self.value} {self.nets})"


def R(ref, value, a, b, label=""):
    return Part(ref, "R", value, {"1": a, "2": b}, label)


def C(ref, value, a, b, label=""):
    return Part(ref, "C", value, {"1": a, "2": b}, label)


MONO = [1, 2, 3, 4, 5, 6]
STEREO = [7, 8]
GND, VP, VN = "GND", "+12V", "-12V"

# TL074 section pins: (out, in-, in+)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
# What each section does, picked by where the chip sits on the main board
# (pcb.py, rear view: channel 1 on the right). Sections 1 / 2 are on the
# pin 1-7 column, which faces channel 1; 1 / 4 at the pin 1 end, nearer the
# headers. U1 serves channels 1-4, U2 5, 6 and 7, U3 channel 8 and the send
# bus, U4 in the master corner the L / R buses and outputs.
OPAMPS = {
    ("U1", 1): ("FOL", "2"), ("U1", 2): ("FOL", "1"), ("U1", 3): ("FOL", "4"), ("U1", 4): ("FOL", "3"),
    ("U2", 1): ("FOL", "6"), ("U2", 2): ("FOL", "5"), ("U2", 3): ("FOL", "7R"), ("U2", 4): ("FOL", "7L"),
    ("U3", 1): ("FOL", "8L"), ("U3", 2): ("FOL", "8R"), ("U3", 3): ("OUT", "S"), ("U3", 4): ("SUM", "S"),
    ("U4", 1): ("SUM", "L"), ("U4", 2): ("SUM", "R"), ("U4", 3): ("OUT", "R"), ("U4", 4): ("OUT", "L"),
}


def opamp_of(kind, name):
    return next(k for k, v in OPAMPS.items() if v == (kind, name))


# CD4093 gates (inputs a, b tied, output) and CD4013 halves (Q, /Q, CLK, RESET, D, SET)
NAND = {1: ("1", "2", "3"), 2: ("5", "6", "4"), 3: ("8", "9", "10"), 4: ("12", "13", "11")}
FLOP = {1: ("1", "2", "3", "4", "5", "6"), 2: ("13", "12", "11", "10", "9", "8")}
NAND_OF = {1: ("U5", 1), 2: ("U5", 2), 3: ("U5", 3), 4: ("U5", 4),
           5: ("U6", 1), 6: ("U6", 2), 7: ("U6", 3), 8: ("U6", 4)}
FLOP_OF = {1: ("U7", 1), 2: ("U7", 2), 3: ("U8", 1), 4: ("U8", 2),
           5: ("U9", 1), 6: ("U9", 2), 7: ("U10", 1), 8: ("U10", 2)}
# PhotoMOS per channel side: AQY212EH, 1 = LED anode, 2 = cathode, 3 / 4 = the switch
PHOTOMOS = {1: ["K1"], 2: ["K2"], 3: ["K3"], 4: ["K4"], 5: ["K5"], 6: ["K6"], 7: ["K7", "K8"], 8: ["K9", "K10"]}


# ------------------------------------------------------------- main board
def _channel_side(k, side=""):
    """Names of one channel side's nets on the main board."""
    s = f"{k}{side}"
    return {"lv": f"LV{s}", "fi": f"FI{s}", "ch": f"CH{s}"}


def mono_main(k):
    n = _channel_side(k)
    r = 100 * k
    return [
        R(f"R{r + 1}", "10k", n["lv"], n["fi"], "mute series"),
        R(f"R{r + 2}", "10k", n["ch"], f"PL{k}", "pan feed L"),
        R(f"R{r + 3}", "10k", n["ch"], f"PR{k}", "pan feed R"),
        R(f"R{r + 4}", "100k", f"PL{k}", "SUM_L", "into L bus"),
        R(f"R{r + 5}", "100k", f"PR{k}", "SUM_R", "into R bus"),
        R(f"R{r + 6}", "100k", f"SD{k}", "SUM_S", "into send bus"),
    ] + latch_main(k, r + 7)


def stereo_main(c):
    L, Rt = _channel_side(c, "L"), _channel_side(c, "R")
    r = 100 * c
    return [
        R(f"R{r + 1}", "10k", L["lv"], L["fi"], "mute series L"),
        R(f"R{r + 2}", "10k", Rt["lv"], Rt["fi"], "mute series R"),
        R(f"R{r + 3}", "200k", L["ch"], "SUM_L", "into L bus"),
        R(f"R{r + 4}", "200k", Rt["ch"], "SUM_R", "into R bus"),
        R(f"R{r + 5}", "10k", L["ch"], f"AV{c}", "send average"),
        R(f"R{r + 6}", "10k", Rt["ch"], f"AV{c}", "send average"),
        R(f"R{r + 7}", "100k", f"SD{c}", "SUM_S", "into send bus"),
    ] + latch_main(c, r + 8)


def latch_main(k, r):
    """Button pull-up and debounce, LED series resistor, the PhotoMOS switch(es)."""
    parts = [
        R(f"R{r}", "100k", VP, f"BTN{k}", "button pull-up"),
        R(f"R{r + 1}", "10k", f"BTN{k}", f"DB{k}", "debounce"),
        C(f"C{100 * k + 1}", "100n", f"DB{k}", GND, "debounce"),
        R(f"R{r + 2}", "1k5", f"QK{k}", f"LA{k}", "LED / PhotoMOS current"),
    ]
    ks = PHOTOMOS[k]
    sides = [""] if len(ks) == 1 else ["L", "R"]
    chain = [f"LA{k}"] + ([f"LM{k}"] if len(ks) == 2 else []) + [f"LED{k}"]
    for i, (ref, side) in enumerate(zip(ks, sides)):
        parts.append(Part(ref, "PHOTOMOS", "AQY212EH", {"1": chain[i], "2": chain[i + 1], "3": f"FI{k}{side}",
                                                         "4": GND}, f"mute {k}{side}"))
    return parts


def bus_main():
    return [
        R("R901", "100k", "SUM_L", "MIX_L", "L bus feedback"), C("C901", "22p", "SUM_L", "MIX_L"),
        R("R902", "100k", "SUM_R", "MIX_R", "R bus feedback"), C("C902", "22p", "SUM_R", "MIX_R"),
        R("R903", "100k", "SUM_S", "MIX_S", "send bus feedback"), C("C903", "22p", "SUM_S", "MIX_S"),
        R("R904", "100k", "MST_L", "NO_L", "output L input"),
        R("R905", "200k", "NO_L", "OA_L", "output L feedback (gain 2)"),
        R("R906", "1k", "OA_L", "OUT_L", "output L series"),
        R("R907", "100k", "MST_R", "NO_R", "output R input"),
        R("R908", "200k", "NO_R", "OA_R", "output R feedback (gain 2)"),
        R("R909", "1k", "OA_R", "OUT_R", "output R series"),
        R("R910", "100k", "MIX_S", "NO_S", "send inverter input"),
        R("R911", "100k", "NO_S", "OA_S", "send inverter feedback"),
        R("R912", "1k", "OA_S", "SEND", "send series"),
        R("R913", "200k", "RW_L", "SUM_L", "return into L bus"),
        R("R914", "200k", "RW_R", "SUM_R", "return into R bus"),
        R("R915", "300k", "DRW", "SUM_L", "drums into L bus"),
        R("R916", "300k", "DRW", "SUM_R", "drums into R bus"),
        R("R917", "100k", "FXI", "SUM_S", "FX IN into send bus"),
    ]


def power_main():
    hdr = {"1": "N12_IN", "2": "N12_IN", "11": "P12_IN", "12": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 11)})
    parts = [
        Part("J18", "HDR16", "16-pin Eurorack", hdr, "POWER"),
        Part("D901", "D5819", "1N5819", {"2": "P12_IN", "1": "P12_D"}, "+12 V reverse protection"),
        Part("D902", "D5819", "1N5819", {"1": "N12_IN", "2": "N12_D"}, "-12 V reverse protection"),
        R("R918", "10R", "P12_D", VP, "+12 V filter"),
        R("R919", "10R", "N12_D", VN, "-12 V filter"),
        Part("C904", "CP", "10u", {"2": VP, "1": GND}, "+12 V bulk"),
        Part("C905", "CP", "10u", {"2": GND, "1": VN}, "-12 V bulk"),
        # power-on reset for the flip-flops: high for ~100 ms after +12 V comes up; D903 empties C906 at power-off
        C("C906", "1u", VP, "POR", "power-on reset"),
        R("R920", "100k", "POR", GND, "power-on reset"),
        Part("D903", "D4148", "1N4148", {"1": VP, "2": "POR"}, "discharges C906"),
    ]
    for i, u in enumerate(("U1", "U2", "U3", "U4")):      # one pair per TL074, beside its supply pins
        parts.append(C(f"C{911 + 2 * i}", "100n", VP, GND, f"{u} +12 V"))
        parts.append(C(f"C{912 + 2 * i}", "100n", GND, VN, f"{u} -12 V"))
    for i, u in enumerate(("U5", "U6", "U7", "U8", "U9", "U10")):
        parts.append(C(f"C{921 + i}", "100n", VP, GND, f"{u} VDD"))
    return parts


def opamp_parts():
    nets = {u: {"4": VP, "11": VN} for u in ("U1", "U2", "U3", "U4")}
    for (u, s), (kind, name) in OPAMPS.items():
        out, inm, inp = SECTION[s]
        if kind == "FOL":
            nets[u].update({out: f"CH{name}", inm: f"CH{name}", inp: f"FI{name}"})
        elif kind == "SUM":
            nets[u].update({out: f"MIX_{name}", inm: f"SUM_{name}", inp: GND})
        else:
            nets[u].update({out: f"OA_{name}", inm: f"NO_{name}", inp: GND})
    return [Part(u, "TL074", "TL074", n) for u, n in nets.items()]


def logic_parts():
    nets = {u: {"14": VP, "7": GND} for u in ("U5", "U6", "U7", "U8", "U9", "U10")}
    for k in MONO + STEREO:
        u, g = NAND_OF[k]
        a, b, y = NAND[g]
        nets[u].update({a: f"DB{k}", b: f"DB{k}", y: f"CK{k}"})
        u, h = FLOP_OF[k]
        q, qn, clk, rst, d, st = FLOP[h]
        nets[u].update({q: f"QK{k}", qn: f"QN{k}", clk: f"CK{k}", rst: "POR", d: f"QN{k}", st: GND})
    return ([Part(u, "CD4093", "CD4093B", nets[u]) for u in ("U5", "U6")] +
            [Part(u, "CD4013", "CD4013B", nets[u]) for u in ("U7", "U8", "U9", "U10")])


def main_board_parts():
    parts = []
    for k in MONO:
        parts += mono_main(k)
    for c in STEREO:
        parts += stereo_main(c)
    parts += bus_main() + power_main() + opamp_parts() + logic_parts()
    for ref, kind, nets in HEADERS:          # female sockets on this board
        parts.append(Part(ref, kind, "", {str(i + 1): mb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ board-to-board pins
def _pair(net):
    return net, {"GND": "GND_F"}.get(net, net + "_F")


# One 1x8 header per channel, standing left of its column (front view)
# between the LEVEL pot and the input jacks, and a 1x12 for the master
# section between channel 8 and the master columns. Pin 1 at the top. Pin
# orders picked for the fewest crossing lines between the pins and what they
# connect to on both boards (the way Plaitsy's were; GND pins kept in place):
# 90 crossings -> 59 over the nine headers.
_ORDERS = {
    1: ("PR", "CH", "PL", "LV", "LED", "GND", "SD", "BTN"), 2: ("CH", "PR", "PL", "LV", "SD", "GND", "LED", "BTN"),
    3: ("CH", "PR", "PL", "LV", "LED", "GND", "SD", "BTN"), 4: ("SD", "PR", "CH", "PL", "LV", "GND", "LED", "BTN"),
    5: ("PR", "CH", "PL", "LV", "SD", "GND", "LED", "BTN"), 6: ("CH", "SD", "PR", "PL", "LV", "GND", "LED", "BTN"),
    7: ("SD", "AV", "GND", "LVL", "LVR", "GND", "LED", "BTN"), 8: ("SD", "AV", "GND", "LVL", "LVR", "GND", "LED", "BTN"),
}


def _chan_net(k, n):
    if n == "GND":
        return n
    if n in ("LVL", "LVR"):
        return f"LV{k}{n[2]}"
    return f"{n}{k}"


HEADERS = [(f"H{k}", "HDR8", [_pair(_chan_net(k, n)) for n in _ORDERS[k]]) for k in MONO + STEREO]
HEADERS += [("H9", "HDR12", [_pair(n) for n in ("SEND", "RW_R", "RW_L", "GND", "DRW", "FXI", "MIX_R", "MIX_L",
                                                "MST_L", "MST_R", "OUT_R", "OUT_L")])]


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]


# ---------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net (None = open)
JACKS = [(f"J{k}", f"IN {k}", f"IN{k}_F", "GND_F") for k in MONO]
JACKS += [("J7", "IN 7 L", "IN7L_F", "GND_F"), ("J8", "IN 7 R", "IN7R_F", "IN7L_F"),
          ("J9", "IN 8 L", "IN8L_F", "GND_F"), ("J10", "IN 8 R", "IN8R_F", "IN8L_F"),
          ("J11", "RETURN L", "RT_L_F", "GND_F"), ("J12", "RETURN R", "RT_R_F", "RT_L_F"),
          ("J13", "DRUMS", "DRM_F", "GND_F"), ("J14", "FX IN", "FXI_F", "GND_F"),
          ("J15", "SEND", "SEND_F", None), ("J16", "OUT L", "OUT_L_F", None), ("J17", "OUT R", "OUT_R_F", None)]
# ref, label, value, (CW end, wiper, CCW end). Pins 1 / 3 are the CCW / CW ends: fully CW puts the wiper on
# pin 3. PAN: CW end on PL, so turning right grounds more of the left side.
POTS = []
for k in MONO:
    POTS += [(f"RV{3 * k - 2}", f"LEVEL {k}", "A100k", (f"IN{k}_F", f"LV{k}_F", "GND_F")),
             (f"RV{3 * k - 1}", f"PAN {k}", "B10k", (f"PL{k}_F", "GND_F", f"PR{k}_F")),
             (f"RV{3 * k}", f"SEND {k}", "A100k", (f"CH{k}_F", f"SD{k}_F", "GND_F"))]
POTS += [("RV20", "SEND 7", "A100k", ("AV7_F", "SD7_F", "GND_F")),
         ("RV22", "SEND 8", "A100k", ("AV8_F", "SD8_F", "GND_F")),
         ("RV24", "DRUMS", "A100k", ("DRM_F", "DRW_F", "GND_F"))]
# dual-gang: gang A (pins 1-3, the row nearer the shaft) left, gang B (4-6) right
POTS2 = [("RV19", "LEVEL 7", "A100k", ("IN7L_F", "LV7L_F", "GND_F"), ("IN7R_F", "LV7R_F", "GND_F")),
         ("RV21", "LEVEL 8", "A100k", ("IN8L_F", "LV8L_F", "GND_F"), ("IN8R_F", "LV8R_F", "GND_F")),
         ("RV23", "RETURN", "A100k", ("RT_L_F", "RW_L_F", "GND_F"), ("RT_R_F", "RW_R_F", "GND_F")),
         ("RV25", "MASTER", "A100k", ("MIX_L_F", "MST_L_F", "GND_F"), ("MIX_R_F", "MST_R_F", "GND_F"))]
# Thonk low-profile LED buttons, lit = muted
BUTTONS = [(f"SW{k}", f"MUTE {k}", k) for k in MONO + STEREO]


def faceplate_parts():
    parts = []
    for ref, label, tip, tn in JACKS:
        nets = {"1": "GND_F", "3": tip}
        if tn:
            nets["2"] = tn
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, value, (cw, w, ccw) in POTS:
        parts.append(Part(ref, "POT", value, {"3": cw, "2": w, "1": ccw, "4": "GND_F", "5": "GND_F"}, label))
    for ref, label, value, a, b in POTS2:
        parts.append(Part(ref, "POT2", value, {"3": a[0], "2": a[1], "1": a[2], "6": b[0], "5": b[1], "4": b[2],
                                               "7": "GND_F", "8": "GND_F"}, label))
    for ref, label, k in BUTTONS:     # contacts 1+2 to GND_F, 3+4 to the pull-up; LED on 5 / 6
        parts.append(Part(ref, "SWLED", "", {"1": "GND_F", "2": "GND_F", "3": f"BTN{k}_F", "4": f"BTN{k}_F",
                                             "5": f"LED{k}_F", "6": "GND_F"}, label))
    for ref, kind, nets in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): fb for i, (mb, fb) in enumerate(nets)}))
    return parts


# ------------------------------------------------------ faceplate placement
# Panel: Eurorack 3U, 28HP (141.9 x 128.5). Faceplate board 140.4 x 108, centred on it.
HP = 28
PANEL_W, PANEL_H = 141.9, 128.5
BOARD_W, BOARD_H = 140.4, 108.0
# Footprint origins are not the mechanical centres. Thonkiconn: the barrel is 0.78 mm below the
# WQP518MA origin (sleeve pad up). Alpha 9 mm pot: the shaft is 7.5 mm from the pin row (KiCad
# RD901F / RD902F), and the PTV09A footprint's origin is 3.5 mm from its pin row, so the shaft is
# 4.0 mm beyond the origin, away from the pins. The generated dual-gang footprint uses the same frame.
JACK_BARREL, POT_SHAFT = -0.78, 4.0

# What the user sees, in panel mm from the top-left corner (y down). Channels
# are columns like on a console: SEND, PAN, LEVEL, MUTE from the top, the
# input jacks at the bottom so cables hang away from the knobs; the stereo
# channels have LEVEL in the LEVEL row and their L / R jacks in the two jack
# rows. The master section on the right: SEND out at the top, the Clouds
# return, RETURN and DRUMS levels, FX IN and DRUMS in, MASTER, OUT L / R.
CH_X = [11.5 + 13.5 * i for i in range(8)]
M1, M2 = 120.0, 133.5
MC = (M1 + M2) / 2
ROW = {"send": 24.0, "pan": 40.5, "level": 57.0, "mute": 72.0, "jack1": 88.0, "jack2": 103.0}
PANEL_XY = {}
for k in MONO:
    x = CH_X[k - 1]
    PANEL_XY.update({f"RV{3 * k}": (x, ROW["send"]), f"RV{3 * k - 1}": (x, ROW["pan"]),
                     f"RV{3 * k - 2}": (x, ROW["level"]), f"SW{k}": (x, ROW["mute"]), f"J{k}": (x, ROW["jack2"])})
for c, (send, level, jl, jr) in ((7, ("RV20", "RV19", "J7", "J8")), (8, ("RV22", "RV21", "J9", "J10"))):
    x = CH_X[c - 1]
    PANEL_XY.update({send: (x, ROW["send"]), level: (x, ROW["level"]), f"SW{c}": (x, ROW["mute"]),
                     jl: (x, ROW["jack1"]), jr: (x, ROW["jack2"])})
PANEL_XY.update({
    "J15": (MC, 22.0),                                   # SEND out
    "J11": (M1, 37.0), "J12": (M2, 37.0),                # RETURN L / R
    "RV23": (M1, 49.5), "RV24": (M2, 49.5),              # RETURN, DRUMS levels
    "J14": (M1, 70.0), "J13": (M2, 70.0),                # FX IN, DRUMS in
    "RV25": (MC, 83.5),                                  # MASTER
    "J16": (M1, ROW["jack2"]), "J17": (M2, ROW["jack2"]),  # OUT L / R
})


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (from the bottom-left, y up)."""
    return px - (PANEL_W - BOARD_W) / 2, PANEL_H - (PANEL_H - BOARD_H) / 2 - py


def panel_of(bx, by):
    return bx + (PANEL_W - BOARD_W) / 2, PANEL_H - (PANEL_H - BOARD_H) / 2 - by


# Footprint origins on the faceplate board (front view, x right, y up, origin
# bottom-left, mm): what pcb.py places and panel.py measures from. The angle
# is informational; pcb.py orients each part by a rule on its pads (pots
# pins down, jacks sleeve up, buttons LED pins along x).
PLACEMENT = {}
for ref, (px, py) in PANEL_XY.items():
    x, y = board_xy(px, py)
    if ref.startswith("J"):
        PLACEMENT[ref] = (round(x, 2), round(y - JACK_BARREL, 2), 0)
    elif ref.startswith("RV"):
        PLACEMENT[ref] = (round(x, 2), round(y - POT_SHAFT, 2), 180)
    else:
        PLACEMENT[ref] = (round(x, 2), round(y, 2), 0)

# Headers (front view, board mm): x, y of the middle of the pin row, angle 270 = pins along y, pin 1 at the
# top. The channel headers stand 6.75 mm left of their column, in the strip between two columns, from just
# under the LEVEL pots' pins to above the jacks; the master header between channel 8 and the master columns.
HEADER_TOP = board_xy(0, 61.0)[1]
HEADERS_FRONT = {}
for k in MONO + STEREO:
    HEADERS_FRONT[f"H{k}"] = (round(board_xy(CH_X[k - 1] - 6.75, 0)[0], 2), round(HEADER_TOP - 3.5 * 2.54, 3), 270)
HEADERS_FRONT["H9"] = (112.5, round(HEADER_TOP - 5.5 * 2.54, 3), 270)

# Mounting holes, the same four on both boards (front view, board mm): in the strips above the SEND row and
# below the jacks, clear of the panel parts on the faceplate and of the master section's SEND jack.
HOLES_FRONT = [board_xy(18.25, 14.5), board_xy(114.0, 14.5), board_xy(18.25, 113.5), board_xy(114.0, 113.5)]


def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        nets = nets_of(parts)
        refs = collections.Counter(p.ref for p in parts)
        print(f"{name}: {len(parts)} parts, {len(nets)} nets, duplicates: {[r for r, n in refs.items() if n > 1]}")
        for n in sorted(nets):
            if len(nets[n]) < 2:
                print("  single-pin net:", n, nets[n])
        kinds = collections.Counter((p.kind, p.value) for p in parts)
        print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    mb, fb = nets_of(main_board_parts()), nets_of(faceplate_parts())
    for ref, kind, pins in HEADERS:
        for a, b in pins:
            if len(mb[a]) < 2 or len(fb[b]) < 2:
                print("  header net not used on both boards:", ref, a, b)
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
