"""logic: the digital side at its real 3.3 V, against datasheet timing and levels.

What it checks:
  A. The chain's bit-bang in time: the edge order read from hal_daisy.cc's ShiftChain, each Settle() =
     kSettleCycles at the CPU clock (main.cc's seed.Init(true) = 480 MHz), laid on a timeline (other
     statements 0 cycles for the minimum widths, a bus-access allowance for the scan length); every
     interval against TI's SN74HC165 / SN74HC595 timing requirements, interpolated to 3.3 V between the
     2.0 V and 4.5 V columns (-40..85 C; linear interpolation over-states HC delays at 3.3 V, so it is
     conservative) and also reported against the 2.0 V bound: /PL low width, /PL high before CP, CP high /
     low, the 595's SER setup / hold, SRCLK before RCLK, the 165's DS setup after U2's Q7 changes, Q7's
     propagation back to SR_DIN before the next read, CP skew between the 165s against the hold time;
     one SR_LOAD edge loading the 165s and latching the 595 (legal per TI's note); the line lengths
     (routed boards, both sides of the header) as capacitance with the 74HC inputs, the STM32's LOW-speed
     tr/tf at that load (DS12556 Table 61), the flight time, and the edge rate the 74HC inputs accept;
     the comments' and design.md's figures (125 ns, ~2,300 cycles, ~5 us, 1.9 %, the scan rate).
  B. Logic levels: STM32 VOH / VOL against 74HC VIH / VIL at the rail's corners; the 165's Q7 against the
     STM32's VIH / VIL with the SR_DIN pull-up as load; the 10k networks with input leakage; switch
     current.
  C. LED drive: 74HC595 output (VOH from the 4.5 V figure, scaled to 3.3 V: an estimate) + 470R + the
     button's red LED; per-LED current typ / worst against design.md's "about 3 mA" and "about 15 mA",
     the 595's per-output and VCC / GND limits, the 16-level software PWM frequency at the scan rate and at the
     README's 85 % audio load (TIM3 updates swept over every phase against the audio callback).
  D. Encoders and buttons: EC11 / PEC11R pulses per revolution and bounce against the scan rate, the
     longest gap between scans (the audio interrupt holds the scan off), the quadrature decoder's rest
     rule and direction, and the switch debounce time against the bounce spec.
  E. The display (Waveshare 1.9inch LCD Module: every input through a TXS0108E, BL into an S8050 via 1k):
     SPI1 SCK from libDaisy's clock tree and display_daisy.cc's prescaler; the ST7789's serial write
     timing; the GPIO speed's Fmax (Table 61's rows, not interpolated) and edges at the SCK line's load (boards +
     header + cable + TXS), also for the SIDEFX_LCD_SPI_FAST build option;
     the TXS0108E's input levels (VIL 0.15 V), edge rate, data rate and reflection rule; RST and the init
     waits; the backlight input against the Seed pin's drive, the transistor's base drive, the TIM4 PWM
     frequency; LCD_BL / LCD_RST free of pull-downs, so the UPDATE screen stays lit in the bootloader.
  F. The Seed's GPIO drive: per-pin and total current for everything the Seed drives.

Run:  cd side-fx/hardware/tests && python test_logic.py
"""
import math
import re

import harness
import pins_fw as fw

ck = harness.Checks("logic")
circuit = harness.load("circuit")
R = harness.routed()
MB, FB = R.main, R.face

# ================================================================== constants (with sources)
# --- rails: the Seed's 3V3D. ASSUMED 3.3 V +-5 % (the Seed's datasheet v1.0.5 gives no tolerance for 3V3D).
VDD = {"min": 3.135, "typ": 3.3, "max": 3.465}
# --- STM32H750, DS12556 Rev 7 (March 2023)
# Table 58 (I/O static): VIL max 0.3 VDD, VIH min 0.7 VDD (CMOS requirement; the "simulation based" 0.4VDD-0.1 /
# 0.47VDD+0.25 are less strict); RPU 30 / 40 / 50 k (min / typ / max); CIO 5 pF typ; leakage +-250 nA max.
STM_VIL_K, STM_VIH_K = 0.3, 0.7
RPU = (30e3, 40e3, 50e3)
C_IO = 5e-12
STM_ILKG = 250e-9
# Table 59: CMOS port, IIO = +-8 mA, 2.7 V <= VDD <= 3.6 V: VOL max 0.4 V, VOH min VDD - 0.4 V; at +-20 mA: 1.3 V.
STM_VOL_8MA, STM_VOH_DROP_8MA = 0.4, 0.4
STM_VOL_20MA, STM_VOH_DROP_20MA = 1.3, 1.3
# Table 20 (absolute max): IIO 20 mA per pin, total sourced / sunk by all I/Os 140 mA.
STM_IIO_MAX, STM_IIO_TOTAL = 20e-3, 140e-3
# Table 61 (output timing, HSLV off), 2.7 V <= VDD <= 3.6 V, max: {speed: ({C: Fmax MHz}, {C: tr/tf ns})}.
STM_SPEED = {"LOW": ({10e-12: 16e6, 30e-12: 12e6, 50e-12: 12e6}, {10e-12: 10e-9, 30e-12: 13.3e-9, 50e-12: 16.6e-9}),
             "MEDIUM": ({10e-12: 110e6, 30e-12: 80e6, 50e-12: 60e6}, {10e-12: 2.8e-9, 30e-12: 4.2e-9, 50e-12: 5.2e-9})}
# Note 3 of Table 61: Fmax is defined with (tr + tf) <= 2/3 T and a 45..55 % duty cycle.
# --- TI SN74HC165, SCLS116H (Dec 2015), SN74HC165 columns, TA -40..85 C; {VCC: value}.
#     6.13 timing requirements (min): tw SH/LD low, tw CLK high or low, tsu SH/LD high before CLK, tsu SER before CLK.
HC165_TW_PL = {2.0: 100e-9, 4.5: 20e-9, 6.0: 17e-9}
HC165_TW_CLK = {2.0: 100e-9, 4.5: 20e-9, 6.0: 17e-9}
HC165_TSU_PL_CLK = {2.0: 100e-9, 4.5: 20e-9, 6.0: 17e-9}
HC165_TSU_SER = {2.0: 50e-9, 4.5: 10e-9, 6.0: 9e-9}
HC165_TH_SER = 5e-9                                         # th SER data after CLK, all VCC (-40..125 C)
HC165_FCLK = {2.0: 5e6, 4.5: 25e6, 6.0: 29e6}               # fclock max
#     6.10 switching (max, CL = 50 pF): tpd CLK -> QH, tpd SH/LD -> QH, tt output transition.
HC165_TPD_CLK = {2.0: 190e-9, 4.5: 38e-9, 6.0: 32e-9}
HC165_TPD_PL = {2.0: 190e-9, 4.5: 38e-9, 6.0: 32e-9}
HC165_TT = {2.0: 95e-9, 4.5: 19e-9, 6.0: 16e-9}
HC_CL_SPEC = 50e-12                                        # the load the switching figures are given at
#     6.3 recommended: VIH min / VIL max; input transition rise / fall time max (ns/V).
HC_VIH = {2.0: 1.5, 4.5: 3.15, 6.0: 4.2}
HC_VIL = {2.0: 0.5, 4.5: 1.35, 6.0: 1.8}
HC_DTDV = {2.0: 1000e-9, 4.5: 500e-9, 6.0: 400e-9}
#     6.5 / 6.7: Ci 10 pF max (3 typ); II +-1 uA max (-40..85, 6 V); VOH at IOH -20 uA: VCC - 0.1 (all VCC);
#     VOH at IOH -4 mA, 4.5 V: 3.84 V min (-40..85); VOL at 20 uA: 0.1 V max; at 4 mA, 4.5 V: 0.33 V max.
HC_CI = (3e-12, 10e-12)
HC_II = 1e-6
HC_VOH_DROP_20UA, HC_VOL_20UA = 0.1, 0.1
HC165_VOL_4MA_45 = 0.33
#     6.1 absolute max: IO 25 mA per output, VCC / GND 50 mA.
# --- TI SN74HC595, SCLS041J (Oct 2021), SN74HC595 columns, TA -40..85 C.
HC595_TW = {2.0: 100e-9, 4.5: 20e-9, 6.0: 17e-9}          # tw SRCLK or RCLK high or low
HC595_TSU_SER = {2.0: 125e-9, 4.5: 25e-9, 6.0: 21e-9}     # tsu SER before SRCLK
HC595_TSU_SR_RCLK = {2.0: 94e-9, 4.5: 19e-9, 6.0: 16e-9}  # tsu SRCLK before RCLK
HC595_TH_SER = 0.0                                         # th SER after SRCLK
HC595_FCLK = {2.0: 5e6, 4.5: 25e6, 6.0: 29e6}
# 6.5: QA..QH VOH min at 4.5 V, IOH -6 mA: 3.84 V (-40..85), 3.98 V (25 C); typ 4.3 V. VOL max 6 mA: 0.33 V.
HC595_VOH_45_6MA = {"min": 3.84, "typ": 4.3}
HC595_IO_MAX, HC595_ICC_MAX = 35e-3, 70e-3                 # 6.1 abs max: per output, through VCC or GND
# The 595's output at 3.3 V is not specified. ESTIMATE: its 4.5 V on-resistance (VCC - VOH) / 6 mA scaled by
# (4.5 - Vt) / (3.3 - Vt) with |Vt| = 1.0 V (an HC PMOS threshold, ASSUMED): linear-region MOSFET.
HC_VT_ASSUMED = 1.0
# --- PCB and wiring: ASSUMED 1 pF per cm of 0.3 mm track on 1.6 mm FR4 over a pour (microstrip ~0.5-0.7 pF/cm;
#     1 pF/cm is conservative); 1 pF per mated header pin pair; signal speed c / sqrt(3.3) (FR4 microstrip,
#     effective er ~3.3) -> 6.1 ns/m.
C_PER_M = 100e-12
C_HEADER = 1e-12
T_PER_M = 1 / (3e8 / math.sqrt(3.3))
# --- CPU: main.cc seed.Init(true) -> 480 MHz (libDaisy system.cpp: PLLN 240, PLLM 4, PLLP 2 on the 16 MHz HSE).
#     Statements between the Settle() waits: 0 cycles for minimum widths; ASSUMED up to 40 cycles each for the
#     scan's length (GPIO on AHB4: posted BSRR writes, IDR reads ~10-30 cycles).
OP_CYCLES_MAX = 40
# --- libDaisy v9.0.0 system.cpp clock tree: HSE 16 MHz (libDaisy builds with HSE_VALUE=16000000); PLL2 M 1,
#     N 12, FRACN 4096 (of 8192), P 8; SPI123 kernel clock = PLL2P; APB1 = sysclk / 2 / 2, TIM clocks 2 x APB1.
HSE = 16e6
PLL2 = {"M": 1, "N": 12, "FRACN": 4096, "P": 8}
SPI_PS = {"PS_2": 2, "PS_4": 4, "PS_8": 8, "PS_16": 16, "PS_32": 32, "PS_64": 64, "PS_128": 128, "PS_256": 256}
# --- the audio: engine/config.h kBlockSize at the Seed's 48 kHz (libDaisy default).
FS_AUDIO = 48e3
# --- LED: the Thonk low-profile LED button's LED has no published data (Thonk's drawing gives none). ASSUMED a
#     typical red LED: VF 1.8 / 2.0 / 2.2 V (min / typ / max) at 1-5 mA, no built-in resistor. A red indicator
#     LED is readable from ~1 mA (ASSUMED).
LED_VF = {"min": 1.8, "typ": 2.0, "max": 2.2}
LED_I_VISIBLE = 1e-3
# --- flicker: the eye's critical flicker-fusion frequency is ~60-90 Hz in direct view (ASSUMED threshold 100 Hz);
#     stroboscopic / phantom-array effects can show up to ~1-2 kHz with eye movement.
FLICKER_FREE = 100.0
# --- encoders: Bourns PEC11R datasheet (REV. D04/26), the BOM's first choice PEC11R-4215F-S0024:
#     "How To Order": detent option 2 = 24 detents (12, 24 pulses), resolution 0024 = 24 pulses per 360 deg ->
#     one quadrature cycle (4 transitions) per detent. Electrical: contact bounce (15 RPM) 2.0 ms max, measured
#     with Bourns' suggested filter (10k / 10k / 10 nF; Side FXy has the 10k pull-up only); RPM (operating) 60 max.
#     The push switch has no bounce figure. Tayda's EC11 (the alternative) not confirmed.
ENC_PPR, ENC_DETENTS = 24, 24
ENC_BOUNCE = 2.0e-3
ENC_RPM_MAX = 60.0
# The four quadrature states are not equally long; no phase tolerance is given. ASSUMED the shortest state lasts
# half of its nominal quarter cycle.
ENC_STATE_FRACTION = 0.5
TURN_FAST = 5.0             # rev/s: a fast flick of a detented knob (ASSUMED; the encoder is rated 1 rev/s)
# The Thonk LED button's switch: no bounce data. ASSUMED 5 ms max (a common tact-switch figure); the PEC11R push
# switch: no figure either, its rotary contacts' 2.0 ms is the only bounce number for the part.
SW_BOUNCE = 5e-3
# --- CPU load: firmware/README.md: "Over about 85 %: lower kMaxGrains" -> the audio callback may take 85 % of a block.
AUDIO_LOAD_MAX = 0.85
# --- the display module: Waveshare 1.9inch LCD Module schematic (files.waveshare.com/upload/7/7f/1.9inch_LCD_Module.pdf):
#     every input (RST, D/C, CS, SCL, SDA, BL) goes through a TI TXS0108E (B side = the header's VCC, A side =
#     the module's LCD_3V3); BL -> TXS A side -> R3 1k -> S8050 base, R2 10k base pull-down; LED from LCD_3V3 via R1 10R.
TXS = {"vih_drop": 0.4,        # TXS0108E SCES642L (Nov 2024) 6.3: B-port VIH min = VCCI - 0.4 V
       "vil": 0.15,            # VIL max 0.15 V (A and B ports)
       "dtdv": 10e-9,          # input transition rise / fall rate max, push-pull: 10 ns/V
       "rate": 100e6,          # 5.x VCCA 3.3 V, VCCB 3.3 V: data rate max 100 Mbps (push-pull)
       "tw": 10e-9,            # pulse duration min, push-pull
       "rpu_low": 40e3, "rpu_high": 4e3,   # 7.3.5: pull-ups 40k while passing a low, 4k while passing a high
       "r_pass": 500.0,        # 7.3.1: pass gate "on the order of 300 to 500 ohm" (max taken)
       "cio": 7e-12,           # Cio B port 5.5 pF typ (ASSUMED 7 pF max)
       "oneshot": 30e-9}       # 7.3.3: one-shot ~30 ns; reflections' round trip should be shorter
S8050_VBE = (0.6, 0.8)        # ASSUMED base-emitter voltage range at 0.5-2 mA (no S8050 datasheet read)
S8050_HFE_MIN = 85            # ASSUMED lowest hFE class of common S8050 datasheets (not confirmed)
LCD_I_MAX = 40e-3             # design.md: the display module "40 mA max" (taken as the backlight's collector current)
# --- Sitronix ST7789V datasheet v1.3 (2014/03), 7.4.3 4-line serial interface characteristics (VDDI 1.65-3.3 V,
#     -30..70 C), min: the ST7789V2's own datasheet was not obtained (the V2 is taken to keep the V's serial timing:
#     NOT CONFIRMED). Note: input rise / fall time 15 ns or less.
ST_TSCYCW, ST_TSHW, ST_TSLW = 66e-9, 15e-9, 15e-9
ST_TCSS, ST_TCSH, ST_TCHW = 15e-9, 15e-9, 40e-9
ST_TDCS, ST_TSDS, ST_TSDH = 10e-9, 10e-9, 10e-9
ST_TR_MAX = 15e-9
# 7.4.5 reset timing: TRW reset pulse min 10 us; TRT reset cancel max 5 ms (120 ms when reset in Sleep Out).
ST_TRW, ST_TRT = 10e-6, 120e-3
LCD_CABLE = 0.20                        # m, the module's cable: ASSUMED (Waveshare gives no length)
C_CABLE_PER_M = 50e-12                  # a loose wire in a bundle: ASSUMED 0.5 pF/cm


def interp(table, v):
    """Linear interpolation over {VCC: value} (clamped to the table's range)."""
    ks = sorted(table)
    if v <= ks[0]:
        return table[ks[0]]
    for a, b in zip(ks, ks[1:]):
        if v <= b:
            return table[a] + (table[b] - table[a]) * (v - a) / (b - a)
    return table[ks[-1]]


def interp_c(table, c):
    """Over {C: value}, linear, extrapolated past the last point with the last slope."""
    ks = sorted(table)
    if c <= ks[0]:
        return table[ks[0]]
    for a, b in zip(ks, ks[1:]):
        if c <= b:
            return table[a] + (table[b] - table[a]) * (c - a) / (b - a)
    a, b = ks[-2], ks[-1]
    return table[b] + (table[b] - table[a]) * (c - b) / (b - a)


def hc(table):
    """A 74HC timing figure at 3.3 V (interpolated) and at the 2.0 V bound."""
    return interp(table, VDD["typ"]), table[2.0]


ns = 1e9

# ================================================================== the lines (routed boards)
MS, FS = MB.net_stats(), FB.net_stats()


def length(net):
    return MS.get(net, {}).get("length", 0.0) + FS.get(net + "_F", {}).get("length", 0.0)


def hc_inputs(net):
    """Number of 74HC inputs on a Seed net, both boards (by the chips' DIP-16 footprints)."""
    n = 0
    for board, nn in ((MB, net), (FB, net + "_F")):
        for ref, p in board.parts.items():
            if ref.startswith("U") and "DIP-16" in p["fp"]:
                n += sum(1 for pad in p["pads"].values() if pad.net == nn)
    return n


LINES = {}
for net in ("SR_CLK", "SR_LOAD", "SR_DOUT", "SR_DIN"):
    L = length(net)
    n_in = hc_inputs(net)
    crosses = net + "_F" in FS
    c = L * 1e-3 * C_PER_M + n_in * HC_CI[1] + C_IO + (C_HEADER if crosses else 0)
    LINES[net] = {"len": L, "c": c, "n_in": n_in, "td": L * 1e-3 * T_PER_M}
ck.within("A.line_length.SR_CLK", LINES["SR_CLK"]["len"], 150, 230, " mm", "hal_daisy.cc: 'about 19 cm over two boards'")
ck.within("A.line_length.SR_LOAD", LINES["SR_LOAD"]["len"], 150, 230, " mm", "hal_daisy.cc: 'about 19 cm over two boards'")
for net in ("SR_CLK", "SR_LOAD"):
    ck.check(f"A.line_inputs.{net}", LINES[net]["n_in"] == 3, f"{LINES[net]['n_in']} 74HC inputs (two 165s and the 595)")

# STM32 LOW-speed edge at each line's load
for net, ln in LINES.items():
    if net == "SR_DIN":
        continue
    ln["tr"] = interp_c(STM_SPEED["LOW"][1], ln["c"])
    ck.within(f"A.edge_rate_ok_for_74hc.{net}", ln["tr"] / (0.8 * VDD["typ"]), None, interp(HC_DTDV, VDD["typ"]), " s/V",
              f"LOW-speed tr/tf max {ln['tr'] * ns:.1f} ns at {ln['c'] * 1e12:.0f} pF ({ln['len']:.0f} mm, {ln['n_in']} inputs)")
    # lumped: the rated edge is much slower than the round trip (a rule of thumb, tr > 6 x one-way delay)
    ck.within(f"A.line_lumped.{net}", ln["tr"] / ln["td"], 6, None, "",
              f"tr {ln['tr'] * ns:.1f} ns against a one-way flight time of {ln['td'] * ns:.2f} ns")

# ================================================================== A. the timeline
main = fw.MAIN
f_cpu = 480e6 if re.search(r"seed\.Init\(\s*true\s*\)", main) else 400e6
kcyc = re.search(r"kCyclesPerSecond\s*=\s*([0-9.e]+)", fw.HAL_H)
ck.check("A.cpu_clock", kcyc is not None and abs(float(kcyc.group(1)) - f_cpu) < 1, f"seed.Init -> {f_cpu / 1e6:.0f} MHz; "
         f"hal.h kCyclesPerSecond {kcyc.group(1) if kcyc else '?'}")
settle_cycles = fw.int_const(fw.HAL, "kSettleCycles")
t_settle = settle_cycles / f_cpu
rate = fw.int_const(fw.HAL_H, "kControlRate")
pre, loop, nbits = fw.chain_ops()
ck.check("A.sequence", pre == ["LOAD_L", "SETTLE", "LOAD_H", "SETTLE"] and loop is not None and nbits == 16,
         f"pre {pre}, loop {loop}, {nbits} bits")


def timeline(op_cycles):
    t, ev = 0.0, []
    for op in list(pre) + list(loop) * nbits:
        if op == "SETTLE":
            t += t_settle
        else:
            ev.append((op, t))
            t += op_cycles / f_cpu
    return ev, t


ev, scan_min = timeline(0)
_, scan_len = timeline(OP_CYCLES_MAX)     # the longest scan the model allows (the hook comes on top)


def times(op):
    return [t for o, t in ev if o == op]


ch, cl, dout, rd = times("CLK_H"), times("CLK_L"), times("DOUT"), times("READ")
pl_l, pl_h = times("LOAD_L")[0], times("LOAD_H")[0]
tw_pl = pl_h - pl_l
tsu_pl = ch[0] - pl_h
tw_hi = min(b - a for a, b in zip(ch, cl))
tw_lo = min(b - a for a, b in zip(cl, ch[1:]))
period = min(b - a for a, b in zip(ch, ch[1:]))
tsu_ser = min(min(c - d for c in ch if c >= d) for d in dout)
th_ser = min(min((d - c for d in dout if d > c), default=1.0) for c in ch[:-1])
q7_avail = min(min(r_ - c for r_ in rd if r_ > c) for c in ch[:-1])
rclk_after_sr = 1.0 / rate - scan_len           # the next scan's SR_LOAD rise after this scan's last SRCLK rise

# edges at the receivers: a pulse loses up to 1.25 tr (10-90 % ramp) when one edge is slow and the other fast
tr_clk, tr_load, tr_dout = LINES["SR_CLK"]["tr"], LINES["SR_LOAD"]["tr"], LINES["SR_DOUT"]["tr"]
td_clk, td_load, td_dout = LINES["SR_CLK"]["td"], LINES["SR_LOAD"]["td"], LINES["SR_DOUT"]["td"]


def hc_check(name, got, table, why):
    v33, v2 = hc(table)
    ck.within(name, got * ns, v33 * ns, None, " ns", f"{why}; needs {v33 * ns:.0f} ns at 3.3 V (interpolated), "
              f"{v2 * ns:.0f} ns at the 2.0 V bound: margin {(got - v2) * ns:+.0f} ns there")


hc_check("A.165.tw_PL_low", tw_pl - 1.25 * tr_load, HC165_TW_PL, f"SR_LOAD low {tw_pl * ns:.0f} ns less a slow edge")
hc_check("A.165.tsu_PL_high_before_CP", tsu_pl - 1.25 * tr_load - td_load + td_clk, HC165_TSU_PL_CLK,
         f"SR_LOAD rise to the first SR_CLK rise {tsu_pl * ns:.0f} ns")
hc_check("A.165.tw_CP_high", tw_hi - 1.25 * tr_clk, HC165_TW_CLK, f"SR_CLK high {tw_hi * ns:.0f} ns")
hc_check("A.165.tw_CP_low", tw_lo - 1.25 * tr_clk, HC165_TW_CLK, f"SR_CLK low {tw_lo * ns:.0f} ns")
hc_check("A.595.tw_SRCLK", min(tw_hi, tw_lo) - 1.25 * tr_clk, HC595_TW, "SR_CLK high / low")
hc_check("A.595.tw_RCLK_low", tw_pl - 1.25 * tr_load, HC595_TW, "SR_LOAD low (RCLK)")
hc_check("A.595.tsu_SER_before_SRCLK", tsu_ser - 1.25 * tr_dout - td_dout, HC595_TSU_SER,
         f"SR_DOUT set to SR_CLK rise {tsu_ser * ns:.0f} ns")
ck.within("A.595.th_SER_after_SRCLK", th_ser * ns, HC595_TH_SER * ns + td_clk * ns + 1.25 * tr_clk * ns, None, " ns",
          f"SR_CLK rise to the next SR_DOUT change; needs th {HC595_TH_SER * ns:.0f} ns + the clock's late arrival")
hc_check("A.595.tsu_SRCLK_before_RCLK", rclk_after_sr, HC595_TSU_SR_RCLK,
         f"last SRCLK rise of a scan to the next scan's RCLK rise ({1e6 / rate:.0f} us period, scan {scan_len * 1e6:.1f} us)")
ck.within("A.clock_rate.165", 1 / period / 1e6, None, interp(HC165_FCLK, VDD["typ"]) / 1e6, " MHz",
          f"bit period {period * ns:.0f} ns; fclock max {HC165_FCLK[2.0] / 1e6:.0f} MHz at 2.0 V")
ck.within("A.clock_rate.595", 1 / period / 1e6, None, interp(HC595_FCLK, VDD["typ"]) / 1e6, " MHz", "")

# U2's Q7 -> U1's DS (SR_CHAIN, faceplate only): tpd(CLK->QH) + tsu(SER) inside one bit period
need33, need2 = [interp(HC165_TPD_CLK, v) + interp(HC165_TSU_SER, v) for v in (VDD["typ"], 2.0)]
ck.within("A.165.cascade_setup", period * ns, need33 * ns, None, " ns",
          f"U2 tpd CLK->QH + U1 tsu SER within one SR_CLK period: {need33 * ns:.0f} ns at 3.3 V (interpolated); "
          f"{need2 * ns:.0f} ns at the 2.0 V bound: margin {(period - need2) * ns:+.0f} ns there")
skew = FS.get("SR_CLK_F", {}).get("length", 0) * 1e-3 * T_PER_M
ck.within("A.165.cascade_hold_skew", skew * ns, None, HC165_TH_SER * ns, " ns",
          "SR_CLK skew between U1 and U2 (bounded by the whole faceplate SR_CLK_F track) against th SER 5 ns; "
          "tpd min is not specified, cascading is TI's own typical application")
# U1's Q7 -> SR_DIN, back to the Seed, before the next read
need33, need2 = [td_clk + 1.25 * tr_clk + interp(HC165_TPD_CLK, v) + 0.5 * interp(HC165_TT, v) + LINES["SR_DIN"]["td"]
                  for v in (VDD["typ"], 2.0)]
ck.within("A.q7_to_sr_din_before_read", q7_avail * ns, need33 * ns, None, " ns",
          f"SR_CLK rise to the next SR_DIN read {q7_avail * ns:.0f} ns; the clock's flight + slow edge, tpd CLK->QH, half "
          f"the output transition and SR_DIN's flight: {need33 * ns:.0f} ns at 3.3 V (interpolated); {need2 * ns:.0f} ns "
          f"at the 2.0 V bound: margin {(q7_avail - need2) * ns:+.0f} ns there (SR_DIN load "
          f"{LINES['SR_DIN']['c'] * 1e12:.0f} pF <= the 50 pF the tpd is given at)")
ck.within("A.sr_din_load_within_spec", LINES["SR_DIN"]["c"] * 1e12, None, HC_CL_SPEC * 1e12, " pF", "")
# the first bit: Q7 = D7 after /PL low (tpd SH/LD -> QH) before the first read
first_read = rd[0] - pl_l
ck.within("A.first_bit_after_load", first_read * ns, (interp(HC165_TPD_PL, VDD["typ"]) + td_load + 1.25 * tr_load) * ns,
          None, " ns", "SR_LOAD fall to the first SR_DIN read against tpd SH/LD->QH at 3.3 V")
# one SR_LOAD edge loads the 165s and latches the 595: legal when RCLK rises with SRCLK idle (TI SCLS041 6.6 note 1:
# the clocks may even be tied); the 165 shifts only with /PL high
ck.check("A.shared_load_edge_order", pre[0] == "LOAD_L" and pre[2] == "LOAD_H" and "CLK_H" not in pre,
         "SR_LOAD falls and rises with SR_CLK low and idle: the 165s load, then the 595 latches the previous scan's byte")
# the docs' figures
ck.close("A.doc.settle_125ns", t_settle * ns, 125, 1, " ns")
m = re.search(r"~(\d+)\s*ns settle", harness.text("docs", "design.md"))
ck.check("A.doc.design_md_settle", m is not None and abs(int(m.group(1)) - t_settle * ns) < 2,
         f"design.md '~{m.group(1) if m else '?'} ns settle', firmware {t_settle * ns:.0f} ns")
m = re.search(r"the 165 and 595 need ~(\d+) ns at 3\.3 V", fw.HAL_RAW)
tw_need = max(interp(HC165_TW_CLK, 3.3), interp(HC595_TW, 3.3), interp(HC165_TW_PL, 3.3))
ck.within("A.doc.comment_need_at_3v3", float(m.group(1)) if m else 0, tw_need * ns * 0.8, None, " ns",
          f"hal_daisy.cc says the parts need ~{m.group(1) if m else '?'} ns at 3.3 V; interpolated TI minimum pulse "
          f"width {tw_need * ns:.0f} ns (20 ns is the 4.5 V figure)")
n_settle = (pre.count("SETTLE") + loop.count("SETTLE") * nbits)
m = re.search(r"about ([\d,]+) cycles\s*\n?//\s*\(~(\d+) us", fw.HAL_RAW)
cyc = n_settle * settle_cycles
ck.within("A.doc.scan_cycles", float(m.group(1).replace(",", "")) if m else 0, cyc, cyc + (len(pre) + len(loop) * nbits) * OP_CYCLES_MAX,
          " cycles", f"{n_settle} settles x {settle_cycles} = {cyc} cycles plus the statements")
ck.within("A.doc.scan_us", float(m.group(2)) if m else 0, scan_min * 1e6, scan_len * 1e6, " us",
          f"modelled scan {scan_min * 1e6:.1f} us (settles only) .. {scan_len * 1e6:.1f} us ({OP_CYCLES_MAX} cycles a statement)")
m = re.search(r"([\d.]+) % of the CPU at (\d+) kHz", fw.HAL_RAW)
ck.within("A.doc.cpu_share", float(m.group(1)) if m else 0, scan_min * rate * 100, scan_len * rate * 100, " %",
          f"modelled {scan_min * rate * 100:.2f} .. {scan_len * rate * 100:.2f} % at {rate} Hz")
m = re.search(r"Bit-banged from a\s+(\d+) kHz timer", harness.text("docs", "design.md"))
ck.check("A.doc.design_md_scan_rate", m is not None and int(m.group(1)) * 1000 == rate,
         f"design.md 'a {m.group(1) if m else '?'} kHz timer', firmware kControlRate {rate} Hz")
m = re.search(r"\b(\d+) kHz timer \(TIM3\)", harness.text("docs", "design.md"))
ck.check("A.doc.design_md_firmware_notes_rate", m is not None and int(m.group(1)) * 1000 == rate,
         f"design.md firmware notes '{m.group(1) if m else '?'} kHz timer (TIM3)', firmware {rate} Hz")

# ================================================================== B. logic levels
for corner in ("min", "max"):
    v = VDD[corner]
    vih, vil = interp(HC_VIH, v), interp(HC_VIL, v)
    ck.within(f"B.stm32_to_74hc.VOH.{corner}", v - STM_VOH_DROP_8MA, vih, None, " V",
              f"STM32 VOH min (8 mA) at VDD {v} V against 74HC VIH {vih:.2f} V (interpolated)")
    ck.within(f"B.stm32_to_74hc.VOL.{corner}", STM_VOL_8MA, None, vil, " V",
              f"STM32 VOL max (8 mA) against 74HC VIL {vil:.2f} V (interpolated)")
    # the 165's Q7 into SR_DIN, loaded by the STM32's pull-up (RPU min) when low, helped by it when high
    i_pu = v / RPU[0]
    r_on = HC165_VOL_4MA_45 / 4e-3 * (4.5 - HC_VT_ASSUMED) / (v - HC_VT_ASSUMED)
    vol_q7 = HC_VOL_20UA + i_pu * r_on
    ck.within(f"B.q7_to_stm32.VOH.{corner}", v - HC_VOH_DROP_20UA, STM_VIH_K * v, None, " V",
              f"165 Q7 VOH min (IOH 20 uA; the pull-up sources, so no load) against STM32 VIH {STM_VIH_K * v:.2f} V")
    ck.within(f"B.q7_to_stm32.VOL.{corner}", vol_q7, None, STM_VIL_K * v, " V",
              f"165 Q7 VOL: 0.1 V + {i_pu * 1e3:.2f} mA (RPU min) x {r_on:.0f} ohm (4.5 V figure scaled, estimate) "
              f"against STM32 VIL {STM_VIL_K * v:.2f} V")
    # the 10k networks: a released input sits below VCC by the input leakage only; a closed one at 0 V
    rn = 10e3
    ck.within(f"B.pullup_network_high.{corner}", v - HC_II * rn, vih, None, " V",
              f"10k pull-up with 74HC II max {HC_II * 1e6:.0f} uA against VIH {vih:.2f} V")
# SHIFT: the Seed's weak pull-up (RPU max) holds a long line next to SR_LOAD / SR_DIN on H3; an SR_LOAD edge couples
# through the neighbouring header pins and tracks (ASSUMED 1 pF) into SHIFT's own capacitance
c_couple = 1e-12
c_shift = (MS.get("BTN_SHIFT", {}).get("length", 0) + FS.get("BTN_SHIFT_F", {}).get("length", 0)) * 1e-3 * C_PER_M \
    + C_HEADER + C_IO
dv = c_couple / (c_couple + c_shift) * VDD["max"]
ck.within("B.shift_crosstalk", VDD["min"] - dv, STM_VIH_K * VDD["min"], None, " V",
          f"SHIFT released ({RPU[2] / 1e3:.0f}k pull-up, {c_shift * 1e12:.0f} pF) dips by {dv:.2f} V when SR_LOAD falls: "
          f"stays above VIH; it recovers in {5 * RPU[2] * c_shift * 1e6:.1f} us")
ck.within("B.switch_current", VDD["max"] / 10e3 * 1e3, None, 10.0, " mA",
          "a closed contact carries VDD / 10k; PEC11R contact rating 10 mA at 5 V")
ck.within("B.all_inputs_closed", 16 * VDD["max"] / 10e3 * 1e3, None, 20.0, " mA",
          "all 16 chain inputs closed at once, from 3V3D_F (informational bound 20 mA)")

# ================================================================== C. LED drive
MBP = {p.ref: p for p in circuit.main_board_parts()}
led_r = [p for p in circuit.main_board_parts() if p.kind == "R" and any(n.startswith("L_") for n in p.nets.values())]
ck.check("C.led_resistors", len(led_r) == 5, f"{[p.ref + ' ' + p.value for p in led_r]}")
r_led = harness.ohms(led_r[0].value) if led_r else 470.0
ron_typ = (4.5 - HC595_VOH_45_6MA["typ"]) / 6e-3 * (4.5 - HC_VT_ASSUMED) / (VDD["typ"] - HC_VT_ASSUMED)
ron_max = (4.5 - HC595_VOH_45_6MA["min"]) / 6e-3 * (4.5 - HC_VT_ASSUMED) / (VDD["min"] - HC_VT_ASSUMED)
i_typ = (VDD["typ"] - LED_VF["typ"]) / (r_led + ron_typ)
i_max = (VDD["max"] - LED_VF["min"]) / (r_led * 0.99)
i_min = (VDD["min"] - LED_VF["max"]) / (r_led * 1.01 + ron_max)
ck.within("C.led_current_typ_vs_doc", i_typ * 1e3, 3.0 * 0.75, 3.0 * 1.25, " mA",
          f"design.md 'about 3 mA': ({VDD['typ']} - VF {LED_VF['typ']}) / ({r_led:.0f} + {ron_typ:.0f} ohm 595 output, estimate)")
ck.within("C.led_current_min_visible", i_min * 1e3, LED_I_VISIBLE * 1e3, None, " mA",
          f"VDD {VDD['min']} V, VF {LED_VF['max']} V, R +1 %, 595 output {ron_max:.0f} ohm (estimate)")
ck.within("C.led_current_max_per_output", i_max * 1e3, None, HC595_IO_MAX * 1e3, " mA",
          f"VDD {VDD['max']} V, VF {LED_VF['min']} V, R -1 %, no output resistance; 595 IO abs max 35 mA")
n_leds = len([v for v in fw.enum_values(fw.HAL_H, "Led") if v != "NUM_LEDS"])
ck.within("C.leds_all_on_typ_vs_doc", n_leds * i_typ * 1e3, 15 * 0.75, 15 * 1.25, " mA", "design.md: the LEDs 'about 15 mA'")
ck.within("C.595_vcc_current", n_leds * i_max * 1e3, None, HC595_ICC_MAX * 1e3, " mA",
          "all LEDs on at the worst case against the 595's 70 mA through VCC / GND (abs max)")
voh_at_load = VDD["min"] - i_min * ron_max
ck.within("C.595_output_headroom", voh_at_load - LED_VF["max"], 0.3, None, " V",
          f"595 VOH at the LED current ({voh_at_load:.2f} V, estimate) above the LED's VF max: the resistor sets the current")
# software PWM: 16 levels over 16 scans
m = re.search(r"kLedFull\s*=\s*(\d+)", fw.CONTROLS)
lvl = int(m.group(1)) + 1 if m else 16
pwm_mask = re.search(r"pwm_phase_\s*\+\s*1\)\s*&\s*(\d+)", fw.CONTROLS)
phases = int(pwm_mask.group(1)) + 1 if pwm_mask else 16
ck.check("C.pwm_levels", lvl == 16 and phases == 16, f"kLedFull + 1 = {lvl} levels over {phases} scan phases")
f_pwm = rate / phases
ck.within("C.pwm_frequency_nominal", f_pwm, FLICKER_FREE, None, " Hz",
          f"{rate} Hz scans / {phases}: steady in direct view; a phantom array is possible when the eye sweeps")
block = 32 / FS_AUDIO
_cfg = harness.text("firmware", "src", "engine", "config.h")
mb = re.search(r"kBlockSize\s*=\s*(\d+)", _cfg)
_fs = re.search(r"kSampleRate\s*=\s*([0-9.]+)f?", _cfg)          # the Seed's real rate, 48014.32 Hz
if mb:
    block = int(mb.group(1)) / (float(_fs.group(1)) if _fs else FS_AUDIO)
isr = AUDIO_LOAD_MAX * block
# the control timer (priority 2) waits for the audio DMA interrupt (priority 1); its pending flag holds one event,
# so while the audio callback runs longer than a scan period, scans are lost, not queued.
# Verifier fix (2026-11-13): the first version took exactly one scan per block whenever the free part of a block
# (here 100 us) is shorter than the 250 us scan period, i.e. it dropped the TIM3 updates that land in that free
# window. TIM3 free-runs (its updates keep their 250 us grid whatever the ISR does), so the update times modulo the
# block (666.7 us) sit on a grid of ~83 us (250 = 3/8 of 666.7): a 100 us window always holds at least one of them
# every three blocks. Simulated here over every phase between the two clocks (they are asynchronous: SAI from PLL3,
# TIM3 from PLL1, so all phases occur): the PWM frequency is taken from the longest time any 16 consecutive scans
# span (one PWM cycle), the worst case over all phases.
def scan_times(phase, n_blocks=60):
    """Scan start times: TIM3 updates every 1/rate; one in an audio callback runs (once) when the callback ends."""
    out, k = [], 0
    t_end = n_blocks * block
    while k / rate < t_end:
        t = k / rate
        n = math.floor((t - phase) / block)
        s = phase + n * block                       # start of the callback this update may fall in
        out.append(s + isr if s <= t < s + isr else t)
        k += 1
    return sorted(set(round(x, 9) for x in out))


worst_span, worst_gap = 0.0, 0.0
for i in range(200):
    st = scan_times(block * i / 200)
    worst_span = max(worst_span, max(b - a for a, b in zip(st, st[phases:])))
    worst_gap = max(worst_gap, max(b - a for a, b in zip(st, st[1:])))
f_pwm_loaded = 1 / worst_span
ck.within("C.pwm_frequency_at_full_load", f_pwm_loaded, FLICKER_FREE, None, " Hz",
          f"audio callback {isr * 1e6:.0f} us of a {block * 1e6:.0f} us block ({AUDIO_LOAD_MAX * 100:.0f} % CPU, README); "
          f"TIM3 updates in a callback merge into one late scan, the others run on time: the longest {phases}-scan PWM "
          f"cycle over all phases is {worst_span * 1e3:.2f} ms ({phases / worst_span:.0f} scans/s at worst; the first "
          f"version's 1 scan per block = {1 / block:.0f}/s ignored the free window); longest scan gap {worst_gap * 1e6:.0f} us")

# ================================================================== D. encoders and buttons
spd = re.search(r"steps_per_detent_\s*=\s*(\d+)\s*;", fw.CONTROLS)
spd = int(spd.group(1)) if spd else None
ck.check("D.steps_per_detent_default", spd == 4 * ENC_PPR // ENC_DETENTS,
         f"firmware default {spd}; PEC11R-4215F-S0024: {ENC_PPR} pulses / {ENC_DETENTS} detents = "
         f"{4 * ENC_PPR // ENC_DETENTS} transitions per detent")
gap_max = isr + 1.0 / rate        # a scan just before the audio callback, the next one pending until it ends
t_state = lambda w: ENC_STATE_FRACTION / (4 * ENC_PPR * w)
w_max_nominal = ENC_STATE_FRACTION / (4 * ENC_PPR / rate)
w_max_loaded = ENC_STATE_FRACTION / (4 * ENC_PPR * gap_max)
ck.within("D.fastest_turn_rated", w_max_loaded, ENC_RPM_MAX / 60, None, " rev/s",
          f"no state missed while the shortest state ({ENC_STATE_FRACTION:.0%} of a quarter cycle, ASSUMED) outlasts the "
          f"longest scan gap {gap_max * 1e6:.0f} us; nominal scans allow {w_max_nominal:.1f} rev/s; PEC11R rated 60 RPM")
ck.within("D.fastest_turn_flick", w_max_loaded, TURN_FAST, None, " rev/s", "a fast flick (ASSUMED 5 rev/s)")
ck.within("D.bounce_inside_a_state", ENC_BOUNCE * 1e3, None, t_state(ENC_RPM_MAX / 60) * 1e3, " ms",
          f"PEC11R bounce 2.0 ms max against the shortest state at the rated 60 RPM ({t_state(1.0) * 1e3:.1f} ms): "
          "bounce settles before the other phase moves, so the Gray-code steps cancel")
# the decoder: a CW turn (A closes first, then B: 0 -> 1 -> 3 -> 2 -> 0) counts +1 per transition, a full cycle = 4
q = fw.int_array(fw.CONTROLS, "kQuadrature")
seq = [0, 1, 3, 2, 0]
cw = sum(q[(a << 2) | b] for a, b in zip(seq, seq[1:])) if q else None
ccw = sum(q[(a << 2) | b] for a, b in zip(seq[::-1], seq[::-1][1:])) if q else None
both = [q[(a << 2) | (a ^ 3)] for a in range(4)] if q else []
ck.check("D.quadrature_table", cw == 4 and ccw == -4 and both == [0, 0, 0, 0],
         f"A-first cycle {cw}, reverse {ccw}, both phases at once {both}")
# bounce: a phase chattering back and forth between two states nets 0
bounce = [0, 1, 0, 1, 0, 1, 3, 1, 3, 2, 3, 2, 0]
ck.check("D.quadrature_bounce_cancels", q and sum(q[(a << 2) | b] for a, b in zip(bounce, bounce[1:]) if a != b) == 4,
         "a cycle with chatter on every edge still nets one cycle")
db = re.search(r"kDebounceScans\s*=\s*(\d+)", fw.CONTROLS_H)
dbn = int(db.group(1)) if db else 0
t_db = (dbn - 1) / rate          # the new level seen on scan 1, accepted on scan dbn
ck.within("D.debounce_vs_encoder_switch_bounce", t_db * 1e3, ENC_BOUNCE * 1e3, None, " ms",
          f"kDebounceScans {dbn} at {rate} Hz accepts a change after {t_db * 1e3:.2f} ms of agreeing scans; the only bounce "
          f"figure for the PEC11R is its rotary contacts' 2.0 ms (the push switch has none)")
ck.within("D.debounce_vs_button_bounce", t_db * 1e3, SW_BOUNCE * 1e3, None, " ms",
          "the Thonk LED buttons (no data; ASSUMED 5 ms tact-switch bounce): a bounce gap longer than the debounce "
          "time gives a second press")

# ================================================================== E. the display
vco2 = HSE / PLL2["M"] * (PLL2["N"] + PLL2["FRACN"] / 8192)
k_spi = vco2 / PLL2["P"]
fast = re.search(r"#define\s+SIDEFX_LCD_SPI_FAST\s+(\d)", fw.DISPLAY_RAW)
ps = re.search(r"\?\s*SpiHandle::Config::BaudPrescaler::(PS_\d+)\s*:\s*SpiHandle::Config::BaudPrescaler::(PS_\d+)", fw.DISPLAY)
ps_default = SPI_PS[ps.group(2)] if ps else None
f_sck = k_spi / ps_default if ps_default else 0
ck.close("E.spi_sck_vs_doc", f_sck / 1e6, 12.5, 0.01, " MHz")
ck.check("E.spi_default_not_fast", fast is not None and fast.group(1) == "0", "SIDEFX_LCD_SPI_FAST defaults to 0")
T = 1 / f_sck
ck.within("E.st7789_tSCYCW", T * ns, ST_TSCYCW * ns, None, " ns", "ST7789V serial clock cycle (write) min 66 ns")
# the SCK line: both boards, two header pairs (H4/HF4, CN1 + plug), the cable, the TXS0108E's B input
L_sck = length("LCD_SCK")
c_sck = L_sck * 1e-3 * C_PER_M + 2 * C_HEADER + LCD_CABLE * C_CABLE_PER_M + TXS["cio"] + C_IO
spi_speed = "LOW"    # libDaisy v9.0.0 spi.cpp InitPins: GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW for SCK / MOSI
tr_sck = interp_c(STM_SPEED[spi_speed][1], c_sck)


def fmax_rated(speed, c):
    """Verifier fix (2026-11-13): Table 61 gives Fmax only at 10 / 30 / 50 pF and says nothing between them, so the
    guaranteed figure for a load is the row at or above it (no interpolation); past 50 pF there is none (0)."""
    rows = sorted(STM_SPEED[speed][0])
    return next((STM_SPEED[speed][0][r] for r in rows if c <= r + 1e-15), 0.0)


fmax = fmax_rated(spi_speed, c_sck)
c_sck_fixed = 2 * C_HEADER + TXS["cio"] + C_IO          # without the tracks and the cable (the ASSUMED parts)
ck.within("E.sck_gpio_fmax", f_sck / 1e6, None, fmax / 1e6, " MHz",
          f"libDaisy v9.0.0 SpiHandle::InitPins sets GPIO_SPEED_FREQ_LOW for SCK / MOSI (and the firmware does not raise "
          f"it); DS12556 Table 61 Fmax at speed LOW: 12 MHz at 30 and 50 pF, 16 MHz only up to 10 pF. The line is "
          f"{c_sck * 1e12:.0f} pF ({L_sck:.0f} mm + {LCD_CABLE * 100:.0f} cm cable ASSUMED), and above 10 pF even without "
          f"tracks and cable ({c_sck_fixed * 1e12:.0f} pF): the verdict does not hang on the capacitance assumptions")
# Verifier addition: display_daisy.cc offers SIDEFX_LCD_SPI_FAST=1 ("try it once the screen works"): SPI1 from PLL1Q =
# 16 MHz / 4 x 240 / 5 = 192 MHz (libDaisy system.cpp PLLM 4, PLLN 240 boosted, PLLQ 5), PS_8 -> 24 MHz, pins still
# at speed LOW.
ps_fast = SPI_PS[ps.group(1)] if ps else None
f_sck_fast = HSE / 4 * 240 / 5 / ps_fast if ps_fast else 0
ck.within("E.fast_option.sck_gpio_fmax", f_sck_fast / 1e6, None, fmax / 1e6, " MHz",
          f"SIDEFX_LCD_SPI_FAST: {f_sck_fast / 1e6:.0f} MHz SCK at speed LOW (Fmax {fmax / 1e6:.0f} MHz at this load); the "
          f"option would need PG11 / PB5 at MEDIUM (60 MHz at 50 pF)")
ck.within("E.fast_option.st7789_tSCYCW", 1e9 / f_sck_fast if f_sck_fast else 0, ST_TSCYCW * ns, None, " ns",
          "ST7789V serial write cycle min 66 ns (V v1.3; V2 not confirmed) at the fast option's SCK")
ck.within("E.sck_edges_2_3_T", 2 * tr_sck * ns, None, 2 / 3 * T * ns, " ns",
          f"(tr + tf) <= 2/3 T, Table 61's own Fmax criterion: tr/tf max {tr_sck * ns:.1f} ns")
ck.within("E.st7789_tSHW", (T / 2 - 1.25 * tr_sck) * ns, ST_TSHW * ns, None, " ns", "SCL high, a slow edge taken off")
ck.within("E.st7789_tSLW", (T / 2 - 1.25 * tr_sck) * ns, ST_TSLW * ns, None, " ns", "SCL low, a slow edge taken off")
ck.within("E.txs_input_edge_rate", tr_sck / (0.8 * VDD["typ"]) * ns, None, TXS["dtdv"] * ns, " ns/V",
          "TXS0108E B-port input transition rate max 10 ns/V (push-pull)")
ck.within("E.txs_data_rate", 2 * f_sck / 1e6, None, TXS["rate"] / 1e6, " Mbps", "TXS0108E 3.3 V / 3.3 V push-pull")
rt = 2 * (L_sck * 1e-3 * T_PER_M + LCD_CABLE * 5e-9)
ck.within("E.txs_reflection_round_trip", rt * ns, None, TXS["oneshot"] * ns, " ns",
          "TI: the round trip of a reflection should be shorter than the ~30 ns one-shot (cable ASSUMED 5 ns/m)")
# levels into the TXS0108E B port (VCCB = the module's VCC = 3V3D_F, the Seed's own rail)
i_low = VDD["max"] / TXS["rpu_low"] * 2          # B-port pull-up plus the A side's through the pass gate
vol = STM_VOL_8MA * i_low / 8e-3
ck.within("E.txs_VIL", vol, None, TXS["vil"], " V",
          f"STM32 VOL at {i_low * 1e3:.2f} mA (the 8 mA figure scaled linearly: estimate) against TXS0108E VIL max 0.15 V")
i_bl = (VDD["max"] - S8050_VBE[0]) / (TXS["r_pass"] * 0.6 + 1e3)      # pass gate at its low end (300 ohm)
for net, i_load in (("LCD_SCK", 0.0), ("LCD_BL", i_bl)):
    voh = VDD["min"] - STM_VOH_DROP_8MA * i_load / 8e-3
    ck.within(f"E.txs_VIH.{net}", voh, VDD["min"] - TXS["vih_drop"], None, " V",
              f"STM32 VOH at {i_load * 1e3:.1f} mA (scaled, estimate) against VCCB - 0.4 V")
# reset and the init sequence's waits
init = fw.function_body(fw.DISPLAY, "InitDisplay") or ""
dl = [int(x) for x in re.findall(r"System::Delay\((\d+)\)", init)]
rst_seq = re.search(r"rst\.Write\(false\);\s*System::Delay\((\d+)\);\s*rst\.Write\(true\);\s*System::Delay\((\d+)\)", init)
ck.check("E.reset_pulse", rst_seq is not None and int(rst_seq.group(1)) * 1e-3 >= ST_TRW,
         f"RST low {rst_seq.group(1) if rst_seq else '?'} ms, TRW min 10 us")
ck.check("E.reset_recovery", rst_seq is not None and int(rst_seq.group(2)) * 1e-3 >= ST_TRT,
         f"wait after RST high {rst_seq.group(2) if rst_seq else '?'} ms, TRT up to 120 ms")
sl = re.search(r"kSleepOut.*?System::Delay\((\d+)\)", init, re.S)
ck.check("E.sleep_out_wait", sl is not None and int(sl.group(1)) >= 5, f"after Sleep Out {sl.group(1) if sl else '?'} ms "
         "(ST7789: 5 ms before the next command)")
# SPI mode 0 (CPOL low, first edge): the ST7789 samples SDA on SCL's rising edge
ck.check("E.spi_mode0", "ClockPolarity::LOW" in fw.DISPLAY and "ClockPhase::ONE_EDGE" in fw.DISPLAY, "CPOL 0, CPHA 0")
# backlight: TIM4 at 2 x APB1 = sysclk / 2, period kBacklightPeriod + 1
per = fw.int_const(fw.DISPLAY, "kBacklightPeriod")
f_bl = f_cpu / 2 / (per + 1) if per else 0
ck.within("E.backlight_pwm_frequency", f_bl / 1e3, 20.0, None, " kHz",
          f"240 MHz / {per + 1 if per else '?'}: above hearing (display_daisy.cc: 25 kHz)")
ck.within("E.backlight_seed_current", i_bl * 1e3, None, 8.0, " mA",
          f"Seed pin -> TXS pass gate -> 1k -> S8050 base: within the 8 mA the VOH/VOL figures are given at")
ib_min = (VDD["min"] - 0.1 - S8050_VBE[1]) / (TXS["r_pass"] + 1e3) - S8050_VBE[1] / 10e3
ck.within("E.backlight_transistor_saturates", ib_min * S8050_HFE_MIN * 1e3, LCD_I_MAX * 1e3, None, " mA",
          f"base current {ib_min * 1e3:.2f} mA x hFE {S8050_HFE_MIN} (ASSUMED) against the module's 40 mA")
# main.cc's EnterBootloader draws "UPDATE" and resets into the Daisy bootloader: from then on LCD_BL and LCD_RST are
# unconfigured pins (floating inputs after reset, DS12556). The TXS0108E's B-port pull-up (40k while low) lifts them,
# so the ST7789 keeps its frame (no reset) and the backlight stays on - the UPDATE screen stays readable - unless
# the main board pulls one of them below VIL 0.15 V: a pull-down of at most 0.15 V x 40k / (VCCB - 0.15 V) would.
# (The same pull-up lights the backlight from power-up until InitDisplay, over a panel still in Display Off: black.)
r_pd_need = TXS["vil"] * TXS["rpu_low"] / (VDD["min"] - TXS["vil"])
for net in ("LCD_BL", "LCD_RST"):
    pds = [ref for ref, p in MB.parts.items() if ref.startswith("R")
           and sorted(pd.net for pd in p["pads"].values()) == sorted(["GND", net])]
    strong = [r_ for r_ in pds if r_ in MBP and harness.ohms(MBP[r_].value) <= r_pd_need]
    ck.check(f"E.update_screen_kept.{net}", not strong,
             f"pull-downs {net}-GND on the routed main board: {pds} (any <= {r_pd_need / 1e3:.1f}k would "
             f"{'darken the backlight' if net == 'LCD_BL' else 'reset the ST7789'} in the bootloader)")
ck.check("E.update_drawn_before_reset", re.search(r"DrawCentredScreen\([^;]*\);\s*sidefx::hal::ResetToBootloader", fw.MAIN)
         is not None, "main.cc EnterBootloader draws the UPDATE screen, then resets into the bootloader")

# ================================================================== F. the Seed's drive
dc = {"SR_CLK": 3 * HC_II, "SR_LOAD": 3 * HC_II, "SR_DOUT": HC_II,
      "LCD_SCK": i_low, "LCD_MOSI": i_low, "LCD_CS": i_low, "LCD_DC": i_low, "LCD_RST": i_low, "LCD_BL": i_bl}
for net, i in dc.items():
    ck.within(f"F.pin_dc_current.{net}", i * 1e3, None, 8.0, " mA",
              "DC load per Seed output, within the 8 mA the VOH / VOL limits are given at (abs max 20 mA)")
ck.within("F.total_dc_current", sum(dc.values()) * 1e3, None, STM_IIO_TOTAL * 1e3, " mA",
          "all Seed outputs together against the 140 mA total (abs max)")
c_pk = max(LINES[n]["c"] for n in ("SR_CLK", "SR_LOAD"))
peak = c_pk * VDD["max"] / (0.8 * interp_c(STM_SPEED["LOW"][1], c_pk))
ck.within("F.edge_charging_current", peak * 1e3, None, STM_IIO_MAX * 1e3, " mA",
          "peak current charging SR_CLK's line at the LOW-speed edge (C dV/dt), against IIO 20 mA")

ck.done()
