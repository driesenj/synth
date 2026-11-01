"""Senay: a Vostok Instruments Sena clone. Four AS3340 oscillators, each
with one waveform and one voltage-controlled modifier, plus an analog noise
bank. 14HP Eurorack, built the Marblesy way (panel first, one netlist,
generated files). Single source of truth for the circuit and the panel.

Build: two boards, SMD (the user's choice, 2026-10-31). Faceplate board:
panel parts on its front, the four FREQ followers (U5) in 0603 on its rear.
Main board: everything else on its rear, 0603 / SOIC / SOT, except the four
AS3340s (DIP-16 in sockets: the SOIC version is not sold retail as far as
we could find) and the nine 3296W trimmers, which stay reachable on the
stack's rear. Headers: one 1xN column on each side edge; 10-pin power.
Through-hole on the main board only fits as a mix of THT and SMD, so it stays
SMD (checked 2026-11-01, docs/design.md).

Sena's panel (Vostok product photo and user manual, October 2026), one row
per channel, then the noise bank:
  jacks   FREQ (V/oct or linear FM, daisy-chained down the rows), the
          modifier's CV, OUT
  toggles V/O - FM, FINE (under the jacks), VCO / LFO (between the knobs)
  knobs   FREQ, the modifier (FOLD, SHAPE, PHASE, PWM)
  LED     the channel's rate
  noise   WHITE, PINK, BLUE, BROWN outputs
Sena uses slide switches; Senay uses Thonk-style sub-mini toggles.

Signal flow, channel k (U1-U4 = AS3340 for channels 1-4)
  FREQ jack -> 1k -> follower (U5) = BUFk. BUFk feeds the next channel's
    FREQ jack switch lug (the daisy chain) and the V/O - FM toggle:
    V/O: 100k into pin 15, the exponential summing node (1 V/oct with Rs)
    FM:  1u (AC) -> 3.3M into pin 13, the reference current: linear FM,
         about +/-50-70 % deviation at +/-5 V, the same ratio at every pitch
  FREQ pot (B10k across +/-5 V) -> FINE toggle:
    off: 160k into pin 15, about +/-3 octaves
    on:  3.0M into pin 15, about +/-2 semitones round the trimmed pitch
  pin 13: 1.2M + 2M trimmer from +5 V (PITCH: C2 = 65.4 Hz at 0 V, FINE on)
  pin 14: 1.5k + 500R trimmer to GND (SCALE: 1 V/oct)
  pin 11: 1n C0G; VCO / LFO toggle grounds a 47n in parallel (/48: about
          0.16-12 Hz over the pot)
  pin 9 (triangle top, about Vcc/3): 1u to GND, and the reference for the
          triangle's centre on channels 1, 2 and 4
  LED: triangle -> 2N3904 follower -> 470R -> LED, so it glows on the top
       of each cycle without loading the triangle

  1 SINE + FOLD   triangle -> LM13700 A without linearising diodes, driven
                  +/-67 mV (tanh: a sine, 1.5 % THD). FOLD sets its Iabc,
                  so the sine's amplitude: 0.32 V (no fold) to 2.1 V.
                  10k transimpedance -> diode folder: an inverting summer
                  with branches that subtract above 1 diode (8.2k, from
                  the inverted signal) and add back above 3 diodes (4.7k):
                  two even folds, the second complete at full FOLD.
  2 TRI + SHAPE   triangle -> LM13700 B at +/-15 mV (linear) -> 100k
                  transimpedance with back-to-back 4.7 V zeners: SHAPE
                  raises the gain from 1 (triangle, +/-3.6 V) to 6.5
                  (clipped at +/-5.3 V: trapezoid towards square)
  3 SAW + PHASE   saw + a second saw shifted in phase = 2 saw + A pulse -
                  2 PW, using the AS3340's own pulse (high while the saw is
                  below the PW level); PHASE sets PW (pin 5) 0..Vcc/3, so
                  both ends are in phase and the middle is an octave up.
                  The PW term keeps the output centred.
  4 PULSE + PWM   PW from Vcc/6 (50 %) up to about 96 %; with a cable in,
                  the PWM pot attenuates the CV (the jack's switch lug
                  feeds +5 V to the pot when nothing is patched)
  Control for FOLD and SHAPE: one op-amp per channel, pot (0..-5 V) on the
  inverting input, CV on the non-inverting one, output -8..+7 V into a
  resistor to the Iabc pin (about -10.8 V): Iabc rises with both.

Noise bank: a 2N3904 base-emitter junction in avalanche -> AC-coupled
non-inverting amp (gain set by the LEVEL trimmer) = WHITE. Pink: inverting
amp with a 4-section RC ladder in its feedback (-3 dB/oct, +/-0.7 dB,
20 Hz-20 kHz). Blue: the same ladder as the input element (+3 dB/oct).
Brown: leaky integrator (-6 dB/oct above 22 Hz). All four about the same
rms (white x 1.1 / 0.8 / 0.7).

Lessons carried over from the earlier boards (see docs/design.md):
2.54 mm 10-pin power header, both 1N5819s the right way round, DIP-14 at
7.62 mm rows, Alpha pot shaft 4.0 mm from the PTV09A origin, transistor
pins named by function, decoupling beside each chip, LED pins by function,
no square wave next to a summing node.

Net naming: nets that cross to the faceplate board carry the same name on
both boards, with _F on the faceplate side (GND -> GND_F). The faceplate
has only panel parts.
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


def CP(ref, value, plus, minus, label=""):
    """A bulk capacitor: ceramic on the SMD boards (1206 / 0805), so the polarity is only a habit."""
    return Part(ref, "C", value, {"1": plus, "2": minus}, label)


def D(ref, kind, value, anode, cathode, label=""):
    """Diodes, all SOD-123: pin 1 = cathode (the band), pin 2 = anode, as in the mixer's 1N5819."""
    return Part(ref, kind, value, {"1": cathode, "2": anode}, label)


def TRIM(ref, value, end, wiper_end, label=""):
    """Bourns 3296W multi-turn as a rheostat: pin 1 to one end, wiper (2) and pin 3 tied."""
    return Part(ref, "TRIM", value, {"1": end, "2": wiper_end, "3": wiper_end}, label)


def NPN(ref, e, b, c, label=""):
    """MMBT3904 (SOT-23: 1 B, 2 E, 3 C). Pins named by function, and the footprint's pads carry the
    same names, so nothing can swap them (the Compressor's BC549C-order footprint did)."""
    nets = {"E": e, "B": b}
    if c:
        nets["C"] = c
    return Part(ref, "NPN", "MMBT3904", nets, label)


CHANNELS = [1, 2, 3, 4]
GND, VP, VN, P5, N5 = "GND", "+12V", "-12V", "+5V", "-5V"
WAVE = {1: "SINE", 2: "TRI", 3: "SAW", 4: "PULSE"}
MOD = {1: "FOLD", 2: "SHAPE", 3: "PHASE", 4: "PWM"}

# TL074 sections (out, in-, in+); LM13700 halves (Iabc, diode bias, in+, in-, out)
SECTION = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}
OTA = {"A": ("1", "2", "3", "4", "5"), "B": ("16", "15", "14", "13", "12")}
# What each op-amp section does: U5 the four FREQ followers, U6 channel 1's folder and control,
# U7 the outputs of channels 2-4 and channel 2's control, U8 the noise bank
OPAMPS = {
    ("U5", 1): "BUF1", ("U5", 2): "BUF2", ("U5", 3): "BUF3", ("U5", 4): "BUF4",
    ("U6", 1): "TIA1", ("U6", 2): "INV1", ("U6", 3): "SUM1", ("U6", 4): "CTL1",
    ("U7", 1): "TIA2", ("U7", 2): "CTL2", ("U7", 3): "SUM3", ("U7", 4): "SUM4",
    ("U8", 1): "WHITE", ("U8", 2): "PINK", ("U8", 3): "BLUE", ("U8", 4): "BROWN",
}
# (in+, in-, out) of each op-amp function
OPAMP_NETS = {
    **{f"BUF{k}": (f"FB{k}", f"BUF{k}", f"BUF{k}") for k in CHANNELS},
    "TIA1": (GND, "OTA1", "X1"), "INV1": (GND, "IV1", "NX1"), "SUM1": (GND, "S1", "Y1"), "CTL1": ("CP1", "CN1", "CT1"),
    "TIA2": (GND, "OTA2", "Y2"), "CTL2": ("CP2", "CN2", "CT2"), "SUM3": ("SP3", "SN3", "Y3"), "SUM4": (GND, "SN4", "Y4"),
    "WHITE": ("NZI", "NWN", "NWA"), "PINK": (GND, "PKN", "PKA"), "BLUE": (GND, "BLN", "BLA"), "BROWN": (GND, "BRN", "BRA"),
}


# ------------------------------------------------------------- main board
def core(k):
    """One AS3340 with its pitch inputs, trims, timing caps, LED driver. Designators k01-k19."""
    r, c = 100 * k, 100 * k
    pins = {"16": VP, "12": GND, "3": f"VEE{k}", "1": f"S1{k}", "2": f"S2{k}", "15": f"EXP{k}", "14": f"RS{k}",
            "13": f"REF{k}", "11": f"TC{k}", "9": f"V9{k}", "10": f"TRI{k}", "7": GND}
    if k in (1, 2):
        pins["5"] = GND                       # pulse unused: PW at 0 % keeps pin 4 low
    if k in (3, 4):
        pins.update({"5": f"PW{k}", "4": f"PU{k}"})
    if k == 3:
        pins["8"] = f"SAW{k}"
    return [
        Part(f"U{k}", "AS3340", "AS3340", pins, f"oscillator {k}"),
        # the FREQ follower and the daisy chain are on the faceplate (buffers())
        R(f"R{r + 3}", "100k", f"VO{k}", f"EXP{k}", "1 V/oct into pin 15"),
        R(f"R{r + 4}", "1M", f"VO{k}", GND, "V/O throw idle"),
        C(f"C{c + 1}", "1u", f"FM{k}", f"FMC{k}", "linear FM coupling (film)"),
        R(f"R{r + 5}", "3.3M", f"FMC{k}", f"REF{k}", "linear FM depth"),
        R(f"R{r + 6}", "1M", f"FM{k}", GND, "FM throw idle, empties the coupling cap"),
        # FREQ pot through the FINE toggle
        R(f"R{r + 7}", "160k", f"CR{k}", f"EXP{k}", "coarse: +/-3 octaves"),
        R(f"R{r + 8}", "1M", f"CR{k}", GND, "coarse throw idle"),
        R(f"R{r + 9}", "3.0M", f"FN{k}", f"EXP{k}", "fine: +/-2 semitones"),
        R(f"R{r + 10}", "1M", f"FN{k}", GND, "fine throw idle"),
        # summing-node compensation (datasheet: 470R + 10n on pins 13 and 15)
        R(f"R{r + 11}", "470", f"EXP{k}", f"EXC{k}", "pin 15 compensation"),
        C(f"C{c + 2}", "10n", f"EXC{k}", GND, "pin 15 compensation"),
        R(f"R{r + 12}", "1.2M", P5, f"RR{k}", "reference current"),
        TRIM(f"TR{k + 4}", "2M", f"RR{k}", f"REF{k}", f"PITCH {k}: C2 at 0 V"),
        R(f"R{r + 13}", "470", f"REF{k}", f"RFC{k}", "pin 13 compensation"),
        C(f"C{c + 3}", "10n", f"RFC{k}", GND, "pin 13 compensation"),
        # scale and temperature compensation (Hordijk: Rt 5k6, Rz about 26k, both to pin 3)
        R(f"R{r + 14}", "1.5k", f"RS{k}", f"SC{k}", "Rs"),
        TRIM(f"TR{k}", "500", f"SC{k}", GND, f"SCALE {k}: 1 V/oct"),
        R(f"R{r + 15}", "5.6k", f"S2{k}", f"VEE{k}", "Rt"),
        R(f"R{r + 16}", "27k", f"S1{k}", f"VEE{k}", "Rz"),
        R(f"R{r + 17}", "560", f"VEE{k}", VN, "REE: (12 - 7.4) / 8 mA"),
        C(f"C{c + 4}", "100n", f"VEE{k}", GND, "VEE (internal zener)"),
        C(f"C{c + 5}", "100n", VP, GND, f"U{k} +12 V"),
        # timing
        C(f"C{c + 6}", "1n", f"TC{k}", GND, "timing, C0G or polystyrene"),
        C(f"C{c + 7}", "47n", f"TC{k}", f"LC{k}", "LFO range (film), grounded by the toggle"),
        C(f"C{c + 8}", "1u", f"V9{k}", GND, "pin 9: steadies the triangle's top"),
        # rate LED
        NPN(f"Q{k}", f"LE{k}", f"TRI{k}", VP, "LED follower"),
        R(f"R{r + 18}", "470", f"LE{k}", f"LED{k}", "LED current, up to ~3 mA"),
    ]


def fold1():
    """Channel 1: sine shaper and two-stage folder (U9 A, U6)."""
    return [
        R("R121", "27k", "TRI1", "OA1P", "OTA A in+: +/-67 mV"),
        R("R122", "1k", "OA1P", GND),
        R("R123", "110k", "V91", "OA1N", "OTA A in-: the triangle's centre, V9 / 2 at the same ratio"),
        R("R124", "2k", "OA1N", GND),
        R("R125", "10k", "X1", "OTA1", "transimpedance"),
        C("C121", "100p", "X1", "OTA1"),
        R("R126", "10k", "X1", "IV1", "inverter"),
        R("R127", "10k", "IV1", "NX1", "inverter"),
        R("R128", "20k", "X1", "S1", "folder input"),
        R("R129", "270k", "Y1", "S1", "folder feedback: +/-4.5 V out"),
        C("C122", "22p", "Y1", "S1"),
        D("D101", "D4148", "1N4148W", "S1", "F1A", "fold 1, positive"),
        R("R130", "8.2k", "F1A", "NX1"),
        R("R131", "8.2k", "NX1", "F1B", "fold 1, negative"),
        D("D102", "D4148", "1N4148W", "F1B", "S1"),
        R("R132", "4.7k", "X1", "F1C", "fold 2, positive"),
        D("D103", "D4148", "1N4148W", "F1C", "F1D"),
        D("D104", "D4148", "1N4148W", "F1D", "F1E"),
        D("D105", "D4148", "1N4148W", "F1E", "S1"),
        D("D106", "D4148", "1N4148W", "S1", "F1F", "fold 2, negative"),
        D("D107", "D4148", "1N4148W", "F1F", "F1G"),
        D("D108", "D4148", "1N4148W", "F1G", "F1H"),
        R("R133", "4.7k", "F1H", "X1"),
        R("R134", "1k", "Y1", "OUT1", "output"),
    ] + control(1, "75k")


def control(k, r_iabc):
    """FOLD / SHAPE: Vc = 5.64 x CV x 0.28 - 3.03 x pot - 1.61 x 5 V, about -8..+7 V -> Iabc."""
    r = 100 * k + 35 if k == 1 else 100 * k + 27
    return [
        R(f"R{r}", "100k", f"CT{k}", f"CN{k}", "control feedback"),
        R(f"R{r + 1}", "33k", f"MP{k}", f"CN{k}", "pot, 0..-5 V"),
        R(f"R{r + 2}", "62k", P5, f"CN{k}", "offset"),
        R(f"R{r + 3}", "100k", f"MCV{k}", f"CP{k}", "CV in"),
        R(f"R{r + 4}", "39k", f"CP{k}", GND, "CV divider"),
        R(f"R{r + 5}", r_iabc, f"CT{k}", f"IABC{k}", "into Iabc (about -10.8 V)"),
    ]


def shape2():
    """Channel 2: linear OTA gain into a zener-limited transimpedance (U9 B, U7)."""
    return [
        R("R221", "120k", "TRI2", "OB2P", "OTA B in+: +/-15 mV"),
        R("R222", "1k", "OB2P", GND),
        R("R223", "240k", "V92", "OB2N", "OTA B in-: V9 / 2 at the same ratio"),
        R("R224", "1k", "OB2N", GND),
        R("R225", "100k", "Y2", "OTA2", "transimpedance: +/-3.6 V triangle at SHAPE min"),
        C("C221", "100p", "Y2", "OTA2"),
        D("ZD201", "ZENER", "BZT52C4V7", "ZM2", "Y2", "clip at +/-5.3 V"),
        D("ZD202", "ZENER", "BZT52C4V7", "ZM2", "OTA2"),
        R("R226", "1k", "Y2", "OUT2", "output"),
    ] + control(2, "22k")


def phase3():
    """Channel 3: PHASE sets the PW level; the summer adds saw, pulse and -PW."""
    return [
        R("R321", "51k", "PU3", GND, "pulse pull-down (Alfa's value)"),
        R("R322", "91k", "MP3", "PW3", "pot 0..12 V -> 0..3.95 V"),
        R("R323", "75k", "MCV3", "PW3", "CV: 10 Vpp covers the range"),
        R("R324", "110k", "PW3", GND),
        D("D301", "D5819", "1N5819HW", GND, "PW3", "keeps pin 5 above -0.3 V"),
        R("R325", "180k", "MP3", "SP3", "PW copy for the summer's in+"),
        R("R326", "150k", "MCV3", "SP3"),
        R("R327", "27k", "SP3", GND),
        R("R328", "100k", "Y3", "SN3", "summer feedback"),
        R("R329", "75k", "SAW3", "SN3", "2 x saw"),
        R("R330", "200k", "PU3", "SN3", "pulse, one saw height"),
        R("R331", "100k", N5, "SN3", "centres the output"),
        C("C321", "22p", "Y3", "SN3"),
        R("R332", "1k", "Y3", "OUT3", "output"),
    ]


def pwm4():
    """Channel 4: PW = V9/2 + 0.37 x pot wiper (50 % .. 96 %), pulse output centred."""
    return [
        R("R421", "51k", "PU4", GND, "pulse pull-down"),
        R("R422", "51k", "V94", "PW4", "50 % point from pin 9"),
        R("R423", "68k", "MP4", "PW4", "PWM pot wiper"),
        R("R424", "180k", "PW4", GND),
        R("R425", "100k", "Y4", "SN4", "summer feedback"),
        R("R426", "100k", "PU4", "SN4", "pulse"),
        R("R427", "100k", N5, "SN4", "centres the output"),
        C("C421", "22p", "Y4", "SN4"),
        R("R428", "1k", "Y4", "OUT4", "output"),
    ]


def noise():
    """Noise bank: avalanche source, white amp, pink / blue ladders, brown integrator (U8, Q5)."""
    ladder = [("330k", "47n"), ("100k", "15n"), ("33k", "4.7n"), ("10k", "1.5n")]
    parts = [
        R("R501", "100k", VP, "NZE", "avalanche current"),
        NPN("Q5", "NZE", GND, None, "noise source: B-E junction reversed, collector open"),
        C("C501", "1u", "NZE", "NZI", "noise coupling"),
        R("R502", "100k", "NZI", GND),
        R("R503", "100k", "NWA", "NWN", "white amp feedback"),
        R("R504", "1k", "NWN", "NWT"),
        TRIM("TR9", "10k", "NWT", "NWG", "noise LEVEL: gain 10-100"),
        CP("C502", "10u", "NWG", GND, "DC gain 1"),
        R("R505", "1k", "NWA", "NWH", "WHITE out"),
        CP("C503", "10u", "NWA", "WAC", "into the colour filters"),
        R("R506", "10k", "WAC", "PKN", "pink input"),
        R("R507", "1M", "PKA", "PKN", "pink ladder: DC leg"),
        C("C508", "470p", "PKA", "PKN", "pink ladder: top"),
        R("R512", "1k", "PKA", "NPK", "PINK out"),
        R("R513", "1M", "WAC", "BLN", "blue ladder: DC leg"),
        R("R518", "10k", "BLA", "BLN", "blue feedback"),
        C("C513", "820p", "BLA", "BLN", "blue: roll-off above 20 kHz"),
        R("R519", "1k", "BLA", "NBL", "BLUE out"),
        R("R520", "10k", "WAC", "BRN", "brown input"),
        R("R521", "330k", "BRA", "BRN", "brown: x33 below 22 Hz"),
        C("C514", "22n", "BRA", "BRN"),
        R("R522", "1k", "BRA", "NBR", "BROWN out"),
    ]
    for i, (rv, cv) in enumerate(ladder):
        parts += [R(f"R{508 + i}", rv, "PKN", f"PK{i + 1}", "pink ladder"), C(f"C{504 + i}", cv, f"PK{i + 1}", "PKA"),
                  R(f"R{514 + i}", rv, "WAC", f"BL{i + 1}", "blue ladder"), C(f"C{509 + i}", cv, f"BL{i + 1}", "BLN")]
    return parts


def power():
    hdr = {"1": "N12_IN", "2": "N12_IN", "9": "P12_IN", "10": "P12_IN"}
    hdr.update({str(n): GND for n in range(3, 9)})
    parts = [
        Part("J17", "HDR10", "10-pin Eurorack, 2.54 mm", hdr, "POWER (red stripe = -12 V = pin 1)"),
        D("D901", "D5819", "1N5819HW", "P12_IN", "P12_D", "+12 V reverse protection: anode on the header"),
        D("D902", "D5819", "1N5819HW", "N12_D", "N12_IN", "-12 V reverse protection: cathode on the header"),
        R("R901", "10R", "P12_D", VP, "+12 V filter"),
        R("R902", "10R", "N12_D", VN, "-12 V filter"),
        CP("C901", "10u", VP, GND, "+12 V bulk"),
        CP("C902", "10u", GND, VN, "-12 V bulk"),
        # 78L05: 1 OUT, 2 GND, 3 IN.  79L05: 1 GND, 2 IN, 3 OUT (SOT-89, the same as TO-92)
        Part("U10", "78L05", "78L05", {"3": VP, "2": GND, "1": P5}, "+5 V reference for pots and pitch"),
        Part("U11", "79L05", "79L05", {"2": VN, "1": GND, "3": N5}, "-5 V reference for pots"),
        C("C903", "100n", VP, GND, "78L05 in"),
        CP("C904", "1u", P5, GND, "78L05 out"),
        C("C905", "100n", GND, VN, "79L05 in"),
        CP("C906", "1u", GND, N5, "79L05 out"),
    ]
    for i, u in enumerate(("U6", "U7", "U8", "U9")):       # one pair per op-amp chip, beside its supply pins
        parts.append(C(f"C{913 + 2 * i}", "100n", VP, GND, f"{u} +12 V"))
        parts.append(C(f"C{914 + 2 * i}", "100n", GND, VN, f"{u} -12 V"))
    return parts


def chips():
    nets = {u: {"4": VP, "11": VN} for u in ("U6", "U7", "U8")}
    for (u, s), fn in OPAMPS.items():
        if u == "U5":
            continue
        out, inm, inp = SECTION[s]
        p, m, o = OPAMP_NETS[fn]
        nets[u].update({inp: p, inm: m, out: o})
    parts = [Part(u, "TL074", "TL074", n) for u, n in nets.items()]
    ota = {"11": VP, "6": VN}
    for half, (iabc, inp, inm, out) in (("A", ("IABC1", "OA1P", "OA1N", "OTA1")),
                                         ("B", ("IABC2", "OB2P", "OB2N", "OTA2"))):
        pi, _diode, pp, pm, po = OTA[half]       # diode-bias pins 2 / 15 and the buffers (7-10) stay open
        ota.update({pi: iabc, pp: inp, pm: inm, po: out})
    parts.append(Part("U9", "LM13700", "LM13700", ota, "OTA A: sine + fold gain, B: shape gain"))
    return parts


def main_board_parts():
    parts = []
    for k in CHANNELS:
        parts += core(k)
    parts += fold1() + shape2() + phase3() + pwm4() + noise() + power() + chips()
    for ref, kind, pins in HEADERS:                 # female sockets on this board
        parts.append(Part(ref, kind, "", {str(i + 1): m for i, (m, f) in enumerate(pins)}))
    return parts


# ------------------------------------------------- the faceplate's nets
def fp(net):
    return {"GND": "GND_F", VP: "P12_F", VN: "N12_F", P5: "P5_F", N5: "N5_F"}.get(net, net + "_F")


# Nets that cross between the boards (main name). FREQ k and the followers' outputs stay on the
# faceplate, where the jacks, the chain and the V/O - FM toggles are.
INTERFACE = [GND, VP, VN, P5, N5, "NWH", "NPK", "NBL", "NBR"]
for _k in CHANNELS:
    INTERFACE += [f"VO{_k}", f"FM{_k}", f"CR{_k}", f"FN{_k}", f"LC{_k}", f"MP{_k}", f"OUT{_k}", f"LED{_k}"] + \
        ([f"MCV{_k}"] if _k != 4 else [])


def buffers():
    """Faceplate rear: FREQ k -> 1k -> TL074 follower (U5) = BUF k; 100k sets the input impedance."""
    nets = {"4": fp(VP), "11": fp(VN)}
    parts = []
    for k in CHANNELS:
        out, inm, inp = SECTION[k]
        nets.update({inp: f"FB{k}_F", inm: f"BUF{k}_F", out: f"BUF{k}_F"})
        parts += [R(f"R{100 * k + 1}", "1k", f"FREQ{k}_F", f"FB{k}_F", "follower input"),
                  R(f"R{100 * k + 2}", "100k", f"FREQ{k}_F", "GND_F", "FREQ input impedance")]
    return [Part("U5", "TL074", "TL074", nets, "FREQ followers")] + parts + [
        C("C911", "100n", fp(VP), "GND_F", "U5 +12 V"), C("C912", "100n", "GND_F", fp(VN), "U5 -12 V")]


# Board-to-board headers: one column on each side edge (front view), male on the faceplate's rear, female
# on the main board's front. Pin 1 at the top, each channel's group from the top down, a GND between the
# groups, the noise outputs and the supplies at the bottom.
#   H1, left edge (panel x 2.6, clear of the jacks' bodies from x 6.5): the nets of the jacks and the
#       V/O - FM and FINE toggles, WHITE and PINK, +-12 V for U5.
#   H2, right edge (panel x 68.7): the nets of the pots, the VCO / LFO toggles and the LEDs, BLUE and
#       BROWN, +-5 V and +12 V for the pots. The modifier pots' mounting lugs end at panel x 67.4, so
#       the pads clear them by 0.45 mm.
HEADER_X = (2.6, 68.7)                    # panel mm from the left
HEADER_TOP = (104.0, 104.0)               # board y of pin 1
_COL_A, _COL_B = [], []
for _k in CHANNELS:                       # seven pins per channel on both, so the groups line up
    _COL_A += [GND, f"VO{_k}", f"FM{_k}", f"CR{_k}", f"FN{_k}", f"MCV{_k}" if _k != 4 else GND, f"OUT{_k}"]
    _COL_B += [GND, f"LC{_k}", GND, f"MP{_k}", GND, f"LED{_k}", GND]
_COL_A += [GND, "NWH", "NPK", GND, VP, VN, GND]
_COL_B += [GND, "NBL", "NBR", GND, P5, N5, VP, GND]
HEADERS = [("H1", f"HDR{len(_COL_A)}", [(n, fp(n)) for n in _COL_A]),
           ("H2", f"HDR{len(_COL_B)}", [(n, fp(n)) for n in _COL_B])]


def header_xy(i):
    """Front-view board position of pin 1 of header i (0 = H1) and the step to the next pin."""
    return HEADER_X[i] - (PANEL_W - BOARD_W) / 2, HEADER_TOP[i], -2.54


def fb_ref(ref):
    """Faceplate-side designator of a header: H1 -> HF1 (EasyEDA wants letters, then digits)."""
    return "HF" + ref[1:]

# ---------------------------------------------------------- panel parts
# ref, panel label, tip net, switch-lug net (None = open)
JACKS = []
for _k in CHANNELS:
    JACKS += [(f"J{3 * _k - 2}", f"FREQ {_k}", fp(f"FREQ{_k}"), "GND_F" if _k == 1 else fp(f"BUF{_k - 1}")),
              (f"J{3 * _k - 1}", f"{MOD[_k]} CV", "PWT4_F" if _k == 4 else fp(f"MCV{_k}"),
               "P5_F" if _k == 4 else "GND_F"),
              (f"J{3 * _k}", f"OUT {_k}", fp(f"OUT{_k}"), None)]
JACKS += [("J13", "WHITE", "NWH_F", None), ("J14", "PINK", "NPK_F", None),
          ("J15", "BLUE", "NBL_F", None), ("J16", "BROWN", "NBR_F", None)]
# ref, label, value, (CW end, wiper, CCW end): fully CW puts the wiper on pin 3
POTS = []
for _k in CHANNELS:
    POTS.append((f"RV{2 * _k - 1}", f"FREQ {_k}", "B10k", ("P5_F", f"FP{_k}_F", "N5_F")))
    POTS.append((f"RV{2 * _k}", MOD[_k], "B100k" if _k == 4 else "B10k",
                 {1: ("N5_F", "MP1_F", "GND_F"), 2: ("N5_F", "MP2_F", "GND_F"), 3: ("P12_F", "MP3_F", "GND_F"),
                  4: ("PWT4_F", "MP4_F", "GND_F")}[_k]))
# Sub-mini SPDT on-on toggles. Pins 1-2-3 in a row, 2 = common; the lever points away from the
# connected throw. Horizontal ones have pin 1 on the left (front view): lever left = 2-3, right = 2-1.
# VCO / LFO stands vertical with pin 1 at the top: lever up (VCO) = 2-3 (open), down (LFO) = 2-1.
# ref, label, "h" / "v", {pin: net}
TOGGLES = []
for _k in CHANNELS:
    TOGGLES += [(f"SW{3 * _k - 2}", "V/O - FM", "h", {"1": fp(f"FM{_k}"), "2": fp(f"BUF{_k}"), "3": fp(f"VO{_k}")}),
                (f"SW{3 * _k - 1}", "FINE", "h", {"1": fp(f"FN{_k}"), "2": f"FP{_k}_F", "3": fp(f"CR{_k}")}),
                (f"SW{3 * _k}", "VCO / LFO", "v", {"1": "GND_F", "2": fp(f"LC{_k}")})]
LEDS = [(f"LED{_k}", f"RATE {_k}", fp(f"LED{_k}")) for _k in CHANNELS]


def faceplate_parts():
    parts = []
    for ref, label, tip, lug in JACKS:
        nets = {"1": "GND_F", "3": tip}
        if lug:
            nets["2"] = lug
        parts.append(Part(ref, "JACK", "", nets, label))
    for ref, label, value, (cw, w, ccw) in POTS:
        parts.append(Part(ref, "POT", value, {"3": cw, "2": w, "1": ccw, "4": "GND_F", "5": "GND_F"}, label))
    for ref, label, orient, nets in TOGGLES:
        parts.append(Part(ref, "TOGGLE", "SPDT on-on", nets, label))
    for ref, label, anode in LEDS:
        parts.append(Part(ref, "LED", "3 mm", {"1": anode, "2": "GND_F"}, label))
    parts += buffers()
    for ref, kind, pins in HEADERS:
        parts.append(Part(fb_ref(ref), kind, "", {str(i + 1): f for i, (m, f) in enumerate(pins)}))
    return parts


# ------------------------------------------------------- panel placement
# Panel: Eurorack 3U, 14HP (70.8 x 128.5). Faceplate board 69.6 x 108, centred on it (as Side FXy).
HP = 14
PANEL_W, PANEL_H = 70.8, 128.5
BOARD_W, BOARD_H = 69.6, 108.0
# Footprint origins are not the mechanical centres: the Thonkiconn barrel is 0.78 mm below the
# WQP518MA origin (sleeve pad up); the Alpha shaft is 4.0 mm beyond the PTV09A origin, away from
# the pins. Toggles and LEDs: the origin is the bushing / the lens.
JACK_BARREL, POT_SHAFT = -0.78, 4.0

# What the user sees, panel mm from the top-left (y down). Sena's arrangement: per channel row the
# three jacks on the left with the V/O - FM and FINE toggles under them (centred between the jack
# columns), the FREQ and modifier knobs on the right with VCO / LFO between and below them, the
# LED after the FINE toggle; the noise bank's four jacks in a row at the bottom.
JACK_X = (11.0, 22.0, 33.0)
TOGGLE_X = (16.5, 27.5)
KNOB_X = (46.75, 61.25)
RANGE_X = 54.0            # VCO / LFO
LED_X = 40.75
ROW_Y = (20.8, 42.8, 64.8, 86.8)          # jack row of each channel; 22 mm pitch
TOGGLE_DY, KNOB_DY = 11.0, -1.0
NOISE_X, NOISE_Y = (11.0, 27.75, 44.5, 61.25), 111.0    # from the jack column to the modifier knobs

PANEL_XY = {}
for _k in CHANNELS:
    y = ROW_Y[_k - 1]
    for i in range(3):
        PANEL_XY[f"J{3 * _k - 2 + i}"] = (JACK_X[i], y)
    PANEL_XY[f"SW{3 * _k - 2}"] = (TOGGLE_X[0], y + TOGGLE_DY)
    PANEL_XY[f"SW{3 * _k - 1}"] = (TOGGLE_X[1], y + TOGGLE_DY)
    PANEL_XY[f"SW{3 * _k}"] = (RANGE_X, y + TOGGLE_DY)
    PANEL_XY[f"RV{2 * _k - 1}"] = (KNOB_X[0], y + KNOB_DY)
    PANEL_XY[f"RV{2 * _k}"] = (KNOB_X[1], y + KNOB_DY)
    PANEL_XY[f"LED{_k}"] = (LED_X, y + TOGGLE_DY)
for i, x in enumerate(NOISE_X):
    PANEL_XY[f"J{13 + i}"] = (x, NOISE_Y)


def board_xy(px, py):
    """Panel mm (from the top-left, y down) -> board mm (from the bottom-left, y up)."""
    return px - (PANEL_W - BOARD_W) / 2, PANEL_H - (PANEL_H - BOARD_H) / 2 - py


def panel_of(bx, by):
    return bx + (PANEL_W - BOARD_W) / 2, PANEL_H - (PANEL_H - BOARD_H) / 2 - by


# Footprint origins on the faceplate board (front view, x right, y up, origin bottom-left, mm). The
# angle is informational; pcb.py will orient each part by a rule on its pads.
PLACEMENT = {}
for _ref, (_px, _py) in PANEL_XY.items():
    _x, _y = board_xy(_px, _py)
    if _ref.startswith("J"):
        PLACEMENT[_ref] = (round(_x, 2), round(_y - JACK_BARREL, 2), 0)
    elif _ref.startswith("RV"):
        PLACEMENT[_ref] = (round(_x, 2), round(_y - POT_SHAFT, 2), 180)
    else:
        PLACEMENT[_ref] = (round(_x, 2), round(_y, 2), 0)


def all_parts():
    return main_board_parts() + faceplate_parts()


def nets_of(parts):
    nets = collections.defaultdict(list)
    for p in parts:
        for pid, n in p.nets.items():
            nets[n].append(f"{p.ref}.{pid}")
    return nets


def check():
    """Single-pin nets, duplicate designators, interface nets used on both sides."""
    problems = []
    mb, fb = nets_of(main_board_parts()), nets_of(faceplate_parts())
    for name, parts, nets in (("main", main_board_parts(), mb), ("faceplate", faceplate_parts(), fb)):
        refs = collections.Counter(p.ref for p in parts)
        problems += [f"{name}: duplicate {r}" for r, n in refs.items() if n > 1]
        for n, pins in nets.items():
            crossing = n in INTERFACE if name == "main" else n in {fp(i) for i in INTERFACE}
            if len(pins) < 2 and not crossing:
                problems.append(f"{name}: single-pin net {n} {pins}")
    for n in INTERFACE:
        if not mb.get(n) or not fb.get(fp(n)):
            problems.append(f"interface net {n} missing on one side")
    in_headers = {m for _, _, pins in HEADERS for m, f in pins}
    problems += [f"interface net {n} has no header pin" for n in INTERFACE if n not in in_headers]
    problems += [f"header net {n} is not an interface net" for n in in_headers if n not in INTERFACE]
    for ref, kind, pins in HEADERS:
        for m, f in pins:
            if len(mb[m]) < 2 or len(fb[f]) < 2:
                problems.append(f"{ref}: {m} / {f} used on one side only")
    for n in fb:
        if n not in {fp(i) for i in INTERFACE} and len(fb[n]) < 2:
            problems.append(f"faceplate: {n} is neither local nor crossing")
    return problems


if __name__ == "__main__":
    for name, parts in (("main board", main_board_parts()), ("faceplate", faceplate_parts())):
        nets = nets_of(parts)
        print(f"{name}: {len(parts)} parts, {len(nets)} nets")
        kinds = collections.Counter((p.kind, p.value) for p in parts)
        print("  " + ", ".join(f"{n} x {k} {v}".strip() for (k, v), n in sorted(kinds.items())))
    print(f"{len(INTERFACE)} nets cross between the boards")
    for p in check():
        print("  problem:", p)
    print(f"board {BOARD_W} x {BOARD_H} on a {PANEL_W} x {PANEL_H} panel; {len(PLACEMENT)} panel parts")
