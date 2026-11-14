"""The Marblesy firmware (marbles/firmware/src) against the ROUTED boards and the datasheets.

firmware/test/gen_board_tables.py already checks the firmware's tables against circuit.py; this group
follows each pin, bit and channel through the routed master's pad nets (Marblesy-routed.epro2, both
boards, the header pins matched by position) to the part pin or panel jack it ends at, and checks the
bus timing and the analogue conversions against the manufacturers' figures.

What it checks
  A  Seed pins: hal_daisy.cc's pin constants against circuit.SEED, the routed U2 pads and the device pins
     they reach; the port/pin comments, static_asserts and GPIO masks (and which GPIO register each mask
     is used on) against libDaisy v9.0.0's Daisy Seed pin table and Electrosmith's datasheet; every CV /
     mux pin ADC-capable (DS12556 Table 7, libDaisy's ADC1 channel map) and its I/O type against the CV
     stage's swing; SPI1's alternate functions on PG11 / PB4 / PB5; the MISO pull-up register write.
  B  Channel and bit tables through the routed boards: CV inputs (hal.h order -> Seed pin -> stage ->
     header -> jack), pots (Pot enum -> 4051 channel -> pin -> wiper -> knob), gates (bit -> pin -> stage
     -> jack), DAC slots and words (Marbles channel -> MCP4922 pin -> stage -> jack), LED bits (a model of
     the 74HC595 chain built from the routed pads, 16 bits MSB first) and output LEDs, buttons (a model
     of the 74HC165 read, (Transfer(0) >> 8)), the mux address bits.
  C  The MCP4922 command word (DS21897B Register 5-1), the 12-bit rounding, the buffered VREF range.
  D  SPI timing at 6.25 MHz: the bus clock from libDaisy's clock tree, MCP4922 / 74HC595 / 74HC165 limits
     (HC figures: onsemi's 3.0 V guarantees, below the real 3V3D, see the constants), the STM32's MISO setup / hold, the
     firmware's Wait() loop as a lower bound, the bus time per sample against the 32 kHz period.
  E  Logic polarity: clock inputs and the normalization probe through the transistor, gates, pots,
     the CV input conversion against circuit.py's resistor values.
  F  The output calibration: nominal scale / offset against the stage formula with circuit.py's values,
     design.md's +5.32 / -5.45 V, the factory points, the load correction and the fit's arithmetic.
  G  design.md's and the README's firmware claims (32 kHz, 5-sample blocks, 595 every 4 samples, 165 every
     millisecond, mode 0, 6.25 MHz, yellow / PWM rates, DAC frame time).

Run from marbles/hardware/tests:  python test_firmware.py
Only reads: the firmware sources as text, circuit.py, the routed export.
"""
import collections
import math
import re

import harness

ck = harness.Checks("firmware")
_ASCII = {"排母": "female header ", "→": "->", "−": "-", "–": "-", "Ω": " ohm", "×": "x"}
_check = ck.check


def _check_cp1252(name, ok, detail=""):
    """Details printable on a cp1252 console (run_tests.py prints FAIL lines without forcing UTF-8)."""
    for a, b in _ASCII.items():
        detail = detail.replace(a, b)
    return _check(name, ok, detail.encode("cp1252", "replace").decode("cp1252"))


ck.check = _check_cp1252
circuit = harness.load("circuit")
R = harness.routed()

# ==========================================================================================================
# Constants: libDaisy, the Seed, the STM32H750 and the bus devices (sources and conditions per line)
#
# libDaisy v9.0.0 src/daisy_seed.h (github.com/electro-smith/libDaisy, tag v9.0.0, fetched 2026-11-12):
LIBDAISY_PINS = {"D0": ("B", 12), "D1": ("C", 11), "D2": ("C", 10), "D3": ("C", 9), "D4": ("C", 8),
                 "D5": ("D", 2), "D6": ("C", 12), "D7": ("G", 10), "D8": ("G", 11), "D9": ("B", 4),
                 "D10": ("B", 5), "D11": ("B", 8), "D12": ("B", 9), "D13": ("B", 6), "D14": ("B", 7),
                 "D15": ("C", 0), "D16": ("A", 3), "D17": ("B", 1), "D18": ("A", 7), "D19": ("A", 6),
                 "D20": ("C", 1), "D21": ("C", 4), "D22": ("A", 5), "D23": ("A", 4), "D24": ("A", 1),
                 "D25": ("A", 0), "D26": ("D", 11), "D27": ("G", 9), "D28": ("A", 2), "D29": ("B", 14),
                 "D30": ("B", 15)}
LIBDAISY_A = {"A0": "D15", "A1": "D16", "A2": "D17", "A3": "D18", "A4": "D19", "A5": "D20", "A6": "D21",
              "A7": "D22", "A8": "D23", "A9": "D24", "A10": "D25", "A11": "D28"}
# Electrosmith Daisy Seed datasheet v1.0.5, Table 2 (Pin Functions): Seed pin -> STM32 pin
SEED_STM32 = {"1": "PB12", "2": "PC11", "3": "PC10", "4": "PC9", "5": "PC8", "6": "PD2", "7": "PC12", "8": "PG10",
              "9": "PG11", "10": "PB4", "11": "PB5", "12": "PB8", "13": "PB9", "14": "PB6", "15": "PB7",
              "22": "PC0", "23": "PA3", "24": "PB1", "25": "PA7", "26": "PA6", "27": "PC1", "28": "PC4", "29": "PA5",
              "30": "PA4", "31": "PA1", "32": "PA0", "33": "PD11", "34": "PG9", "35": "PA2", "36": "PB14", "37": "PB15"}
# libDaisy v9.0.0 src/per/adc.cpp: pin -> ADC1 channel (dsy_adc_channel_map / adc_channel_from_pin)
LIBDAISY_ADC1 = {"PA6": 3, "PC4": 4, "PB1": 5, "PA7": 7, "PC5": 8, "PB0": 9, "PC0": 10, "PC1": 11, "PC2": 12,
                 "PC3": 13, "PA2": 14, "PA3": 15, "PA0": 16, "PA1": 17, "PA4": 18, "PA5": 19}
# libDaisy v9.0.0 src/per/adc.cpp write_mux_value(): mux_0 = idx & 1, mux_1 = idx & 2, mux_2 = idx & 4
# ST DS12556 Rev 7 (STM32H750xB, March 2023), Table 7 pin definitions: I/O structure and ADC inputs
DS_PIN = {"PA0": ("FT_a", "ADC1_INP16"), "PA1": ("FT_ha", "ADC1_INP17"), "PA2": ("FT_a", "ADC12_INP14"),
          "PA3": ("FT_ha", "ADC12_INP15"), "PA6": ("FT_a", "ADC12_INP3"), "PA7": ("TT_a", "ADC12_INP7"),
          "PB1": ("TT_a", "ADC12_INP5"), "PC0": ("FT_a", "ADC123_INP10"), "PC1": ("FT_ha", "ADC123_INP11"),
          "PC4": ("TT_a", "ADC12_INP4"), "PA4": ("TT_a", "ADC12_INP18"), "PA5": ("TT_ha", "ADC12_INP19")}
# DS12556 Rev 7 Table 19 (absolute maximum): VIN on TT_xx pins max 4.0 V; on FT_xxx pins min(VDD, VDDA, ...) + 4.0 V
# (pull-ups / pull-downs disabled above 4 V). Table 20: injected current on FT_xxx / TT_xx pins -5 / +0 mA, note 3
# "positive injection is not possible on these I/Os": no clamp to VDD, the pin voltage itself must stay in range.
VIN_MAX_TT = 4.0
VIN_MAX_FT_ABOVE_VDD = 4.0
IINJ_NEG_MAX = 5e-3
# verifier change: ST AN4899 Rev 3 5.2.1 / 5.2.2 (DS12556 7.3.15 points to it for GPIO configuration): a pin with an
# analog input function enabled (ADC input active) is not 5 V tolerant (FT_a, FT_fa, TT_a); its maximum operating
# voltage is min(VDDA, VREF+) + 0.3 V. The Seed's VDDA = VREF+ = 3V3A. The Seed's own GPIO maximum is 5 V (Table 1).
VIN_MAX_ANALOG_ABOVE_VDDA = 0.3
SEED_GPIO_MAX = 5.0
# Daisy Seed datasheet v1.0.5, Table 1 note: all GPIOs 5 V tolerant except pins 24, 25, 28, 29, 30 (3.3 V tolerant)
SEED_3V3_TOLERANT = {"24", "25", "28", "29", "30"}
# DS12556 Rev 7 alternate-function table (AF5 column): PG11 SPI1_SCK, PB4 SPI1_MISO, PB5 SPI1_MOSI; libDaisy v9.0.0
# src/per/spi.cpp spi1_pins_*: {PG11, PA5} SCK, {PB4, PA6, PG9} MISO, {PB5, PA7} MOSI, all GPIO_AF5_SPI1.
SPI1_AF5 = {"SCK": {"PG11", "PA5"}, "MISO": {"PB4", "PA6", "PG9"}, "MOSI": {"PB5", "PA7"}}
# libDaisy v9.0.0 spi.cpp: FirstBit MSB, MasterInterDataIdleness 0, SPI pins at GPIO_SPEED_FREQ_LOW (OSPEEDR 00);
# BaudPrescaler::PS_4 -> SPI_BAUDRATEPRESCALER_4.
SPI_PRESCALER = {"PS_2": 2, "PS_4": 4, "PS_8": 8, "PS_16": 16, "PS_32": 32}
# libDaisy v9.0.0 core/Makefile -DHSE_VALUE=16000000; src/sys/system.cpp ConfigureClocks(): PLL1 M 4, N 240 (FREQ_480MHZ,
# Boost(); DaisySeed::Init(true)), P 2; AHB /2, APB1 /2; PLL2 M 1, N 12, FRACN 4096 (of 8192), P 8 ("25MHz");
# Spi123ClockSelection = RCC_SPI123CLKSOURCE_PLL2 (pll2_p_ck). With a v6+ bootloader the app sets the clocks itself
# (daisy_seed.cpp: skip_clocks only for bootloaders < v6).
HSE = 16e6
PLL1 = {"M": 4, "N": 240, "P": 2}
AHB_DIV, APB1_DIV = 2, 2
PLL2 = {"M": 1, "N": 12, "FRACN": 4096, "P": 8}
# STM32H7 timer clock: with TIMPRE = 0 and the APB1 prescaler at /2, TIMx_CLK = 2 x PCLK1 (RM0433 RCC "timer clock"
# rule; RM0433 not fetched in this run, the firmware's own comment states the same: not confirmed independently).
TIMER_CLK_FACTOR = 2
# DS12556 Rev 7 Table 104 SPI dynamic characteristics (OSPEEDR = 11, C = 30 pF, 0.5 VDD, master mode):
TSU_MI = 2e-9           # min, data input setup
TH_MI = 1e-9            # min, data input hold
TV_MO = 3e-9            # max, data output valid
TH_MO = 0.0             # min, data output hold
T_SCK_DUTY = 2e-9       # SCK high / low time = TPLCK -+ 2 ns
# DS12556 Rev 7 Table 61 (HSLV off), OSPEEDR 00 (what libDaisy sets on the SPI pins): Fmax 12 MHz (C = 30 / 50 pF,
# 2.7-3.6 V); tr / tf max 13.3 ns at 30 pF (16.6 ns at 50 pF). The bus edges are taken at 30 pF.
F_MAX_SPEED00 = 12e6
T_EDGE_SPEED00 = 13.3e-9
# DS12556 Rev 7 Table 59 / 58: VOH min VDD - 0.4 V (CMOS port, 8 mA, 2.7-3.6 V); VIH min 0.7 VDD.
VOH_DROP = 0.4
# Microchip DS21897B (MCP4921/4922), AC characteristics (SPI timing, VDD 2.7-5.5 V, -40..125 C), all min unless max:
MCP_FCLK_MAX = 20e6
MCP_THI = MCP_TLO = 15e-9
MCP_TSU, MCP_THD = 15e-9, 10e-9      # data setup / hold to SCK rising
MCP_TCHS = 15e-9                     # SCK rise to CS rise hold
MCP_TCSH = 15e-9                     # CS high time
MCP_TLD = 100e-9                     # LDAC pulse width
MCP_TLS = 40e-9                      # LDAC setup (CS rise to LDAC fall)
MCP_TIDLE = 40e-9                    # SCK idle time before CS fall
MCP_VIH_FRAC = 0.7                   # VIH = 0.7 VDD (Schmitt inputs)
# DS21897B Register 5-1 (write command): bit 15 A/B (1 = DAC B), 14 BUF (1 = buffered VREF), 13 GA (1 = 1x,
# VOUT = VREF * D / 4096), 12 SHDN (1 = active), 11-0 D; 16 clocks then CS high latch; modes 0,0 and 1,1.
MCP_BIT = {"AB": 15, "BUF": 14, "GA": 13, "SHDN": 12}
# DS21897B 5 V / 2.7 V DC characteristics: VREF input range, buffered mode 0.040 .. VDD - 0.040 V; VDD 2.7..5.5 V.
MCP_VREF_BUF_MARGIN = 0.040
MCP_VDD_MIN = 2.7
# TI SCLS041J (SN74HC595), 6.6 Timing Requirements, SN74HC595 column (-40..85 C), at VCC 2 V / 4.5 V (min unless f):
HC595 = {"fclock": (5e6, 25e6),                 # max
         "tw": (100e-9, 20e-9),                 # SRCLK or RCLK high or low
         "tsu_ser": (125e-9, 25e-9),            # SER before SRCLK
         "tsu_rclk": (94e-9, 19e-9),            # SRCLK before RCLK
         "th_ser": (0.0, 0.0),                  # SER after SRCLK
         "tpd_qh": (200e-9, 40e-9)}             # 6.7, SRCLK -> QH', 50 pF, max
HC595_25C = {"tsu_ser": (100e-9, 20e-9), "tpd_qh": (160e-9, 32e-9)}      # TA = 25 C columns (max / min)
HC595_TYP_TPD = (50e-9, 17e-9)                                           # 6.7 tpd SRCLK -> QH', typ, 25 C
# TI SCLS116H (SN74HC165), 6.13 / 6.10 (SN74HC165, -40..85 C), VCC 2 V / 4.5 V:
HC165 = {"fclock": (5e6, 25e6),                 # max
         "tw_pl": (100e-9, 20e-9),              # SH/LD low
         "tw_clk": (100e-9, 20e-9),             # CLK high or low
         "tsu_pl_clk": (100e-9, 20e-9),         # SH/LD high before CLK
         "tpd_clk_qh": (190e-9, 38e-9),         # CLK -> QH, 50 pF, max
         "tpd_pl_qh": (190e-9, 38e-9)}          # SH/LD -> QH, 50 pF, max
# verifier change: the 74HC figures at the real 3V3D. Interpolating a maker's 2.0 V and 4.5 V limits linearly is no
# guarantee either way: onsemi's own 3.0 V limits for the MC74HC595A lie ABOVE the line through its 2.0 / 4.5 V ones
# (tpd SRCLK->QH' 125 vs 119 ns, tsu 50 vs 44 ns, 85 C), while the line through TI's SN74HC595 limits gives a tsu of
# 77 ns at 3.2 V against onsemi's guaranteed 50 ns at 3.0 V, and for the 165 the TI line (117 ns) is twice onsemi's
# 3.0 V guarantee (63 ns). onsemi specifies its HC parts at VCC = 3.0 V, below the real 3V3D (3.2 V at -3 %), where the
# parts are faster: those guarantees are used. The BOM names no maker; a TI or Nexperia part is guaranteed at 3.3 V
# only by its 2.0 V column (quoted in the details).
# onsemi MC74HC595A/D Rev 27 (Feb 2025), AC characteristics and timing requirements, VCC 3.0 V, CL 50 pF, guaranteed
# limits, the -55..85 C column (and the -55..25 C column):
HC595_3V0 = {"fclock": 10e6,          # max (15 MHz at 25 C)
             "tw": 50e-9,             # SRCLK / RCLK pulse width min (40 ns at 25 C)
             "tsu_ser": 50e-9,        # SER before SRCLK min (40 ns at 25 C)
             "tsu_rclk": 70e-9,       # SRCLK before RCLK min (60 ns at 25 C)
             "th_ser": 5e-9,          # SER after SRCLK min
             "tpd_qh": 125e-9}        # SRCLK -> QH' max (100 ns at 25 C)
HC595_3V0_25C = {"tsu_ser": 40e-9, "tsu_rclk": 60e-9, "tpd_qh": 100e-9}
# onsemi MC74HC165A/D Rev 13 (Apr 2025), VCC 3.0 V, CL 50 pF, -55..85 C column:
HC165_3V0 = {"fclock": 17e6, "tw_clk": 32e-9, "tw_pl": 32e-9, "tsu_pl_clk": 40e-9,
             "tpd_clk_qh": 63e-9,     # CLK -> QH max
             "tpd_pl_qh": 70e-9}      # SH/LD -> QH max
HC165_TPD_MIN_ASSUMED = 5e-9   # no minimum is specified; a CMOS flip-flop's clock-to-output at 3.3 V is taken >= 5 ns
# TI SCLS041J / SCLS116H 6.3: VIH min 1.5 V at VCC 2 V, 3.15 V at 4.5 V
HC_VIH = (1.5, 3.15)
# HC limits at the real supply: linear interpolation in VCC between the 2.0 V and 4.5 V figures at VCC_HC. HC delays
# fall faster than linearly with VCC (roughly as VCC / (VCC - Vt)^2), so this over-estimates times at 3.3 V: a
# failure here means "not guaranteed by the datasheet", not "measured to fail".
# verifier change: interp() is now used only for the input levels (HC_VIH) and the typical tpd quoted in a detail;
# the timing checks use onsemi's 3.0 V guarantees (HC595_3V0 / HC165_3V0 above), since the guaranteed limits are not
# linear in VCC (onsemi's 3.0 V rows lie above the line through its own 2.0 / 4.5 V rows for the 595).
V3V3 = 3.3              # nominal 3V3D / 3V3A (Daisy Seed datasheet: +3V3 outputs)
V3V3_TOL = 0.03         # assumed regulator tolerance (not in the Seed's datasheet: not confirmed)
VCC_HC = V3V3 * (1 - V3V3_TOL)
# Cortex-M7 Wait() loop: `for (volatile uint32_t i = 0; i < n; ++i) {}` at -O2 compiles to ldr / adds / str (++i) and
# ldr / cmp / branch (i < n) on the stack slot: a chain ldr -> adds -> str -> ldr -> cmp -> branch in which each step
# needs the previous one's result. Even dual-issued, three of those steps are strictly sequential, so an iteration
# takes at least 3 core cycles (assumption from the instruction sequence; not measured).
WAIT_CYCLES_MIN = 3
# Marbles upstream (github.com/pichenettes/eurorack marbles/settings.cc, fetched 2026-11-12): default dac_scale
# -6212.8, dac_offset 32768 (its DAC8564 stage); adc_scale -2 / offset +1, T RATE -120 / +60.
MARBLES_DAC_SCALE, MARBLES_DAC_OFFSET = -6212.8, 32768.0
# 2N3904: hFE min 40 at IC 0.1 mA, VCE 1 V; VBE(on) taken as 0.65 V (onsemi 2N3903/D rev 9, ON characteristics)
HFE_MIN_01MA = 40
VBE_ON = 0.65
VCE_SAT = 0.2
# LM4040CIZ-2.5 (the BOM's grade): 2.500 V +-0.5 % (TI SNOS633N, C grade, 25 C)
VREF_NOM, VREF_TOL = 2.5, 0.005
# Daisy Seed: the ADC's VREF+ is the Seed's 3V3A (the firmware's assumption; the Seed schematic was not fetched: not
# confirmed). The CV conversion below is ratiometric in the bias and checked at nominal 3V3A.
TL074_SWING = 1.5       # V from each rail the TL074 output reaches into 10k (SLOS080: VOM +-13.5 V at +-15 V, 10k)

F_CPU = HSE / PLL1["M"] * PLL1["N"] / PLL1["P"]
PCLK1 = F_CPU / AHB_DIV / APB1_DIV
F_PLL2P = HSE / PLL2["M"] * (PLL2["N"] + PLL2["FRACN"] / 8192) / PLL2["P"]


def interp(pair, v=VCC_HC):
    """A 74HC limit given at 2.0 V and 4.5 V, linearly interpolated to v."""
    a, b = pair
    return a + (b - a) * (v - 2.0) / 2.5


# ==========================================================================================================
# Sources
def fw(*p):
    return harness.text("firmware", *p)


HAL = fw("src", "hal_daisy.cc")
HAL_H = fw("src", "hal.h")
MARB = fw("src", "marblesy.cc")
MAIN = fw("src", "main.cc")
CAL = fw("src", "output_calibrator.h")
SETTINGS = fw("src", "marbles", "settings.cc")
UI = fw("src", "marbles", "ui.cc")
LEDS = fw("src", "marbles", "drivers", "leds.cc")
LEDS_H = fw("src", "marbles", "drivers", "leds.h")
SW = fw("src", "marbles", "drivers", "switches.cc")
SW_H = fw("src", "marbles", "drivers", "switches.h")
DAC_CC = fw("src", "marbles", "drivers", "dac.cc")
DAC_H = fw("src", "marbles", "drivers", "dac.h")
ADC_CC = fw("src", "marbles", "drivers", "adc.cc")
CLK_CC = fw("src", "marbles", "drivers", "clock_inputs.cc")
GATE_H = fw("src", "marbles", "drivers", "gate_outputs.h")
IOBUF = fw("vendor", "marbles", "io_buffer.h")
XYGEN = fw("vendor", "marbles", "random", "x_y_generator.cc")
GATEFLAGS = fw("vendor", "stmlib", "utils", "gate_flags.h")
DESIGN = " ".join(harness.text("docs", "design.md").split())      # whitespace flattened for phrase searches
README = " ".join(fw("README.md").split())


def enum(source, name):
    body = re.search(r"enum " + name + r" \{([^}]*)\}", source).group(1)
    body = re.sub(r"//[^\n]*", "", body)
    names = [n.strip().split("=")[0].strip() for n in body.split(",")]
    return [n for n in names if n and not n.endswith("_LAST")]


def cfloat(source, name):
    """The value of `const float name = <literal>f;` (simple literals only)."""
    m = re.search(r"(?:const|constexpr)\s+(?:static\s+)?float\s+" + name + r"\s*=\s*([-+0-9.e]+)f?\s*;", source)
    return float(m.group(1)) if m else None


def cint(source, name):
    m = re.search(r"(?:const|constexpr)\s+(?:static\s+)?(?:uint\d+_t|int|size_t)\s+" + name + r"\s*=\s*(0x[0-9a-fA-F]+|\d+)", source)
    return int(m.group(1), 0) if m else None


PINS = {k: v for k, v in re.findall(r"constexpr Pin (k\w+) = seed::(\w+);", HAL)}
PIN_COMMENT = {k: c for k, c in re.findall(r"constexpr Pin (k\w+) = seed::\w+;\s*//\s*(P[A-K]\d+)", HAL)}
CV_PINS = re.findall(r"seed::(\w+)", re.search(r"kCvPins\[CV_INPUT_LAST\] = \{([^}]*)\}", HAL).group(1))
ASSERTS = {k: (p, int(n)) for k, p, n in re.findall(r"static_assert\((k\w+)\.port == PORT([A-K]) && \1\.pin == (\d+)", HAL)}
MASKS = {k: (int(b), port) for k, b, port in re.findall(r"const uint32_t (k\w+Mask) = 1 << (\d+);\s*//\s*GPIO([A-K])", HAL)}
gm = re.search(r"kGateMask\[3\] = \{\s*1 << (\d+), 1 << (\d+), 1 << (\d+) \};\s*//\s*GPIO([A-K])", HAL)
GATE_MASKS = [(int(gm.group(i)), gm.group(4)) for i in (1, 2, 3)]

# expected role of every pin constant (design.md's Seed pin map, "Use" column)
ROLE = {"kClockT": "T_CLK", "kClockX": "X_CLK", "kGate1": "GATE_T1", "kGate2": "GATE_T2", "kGate3": "GATE_T3",
        "kProbe": "PROBE", "kDacCs1": "DAC_CS1", "kSpiSck": "SPI_SCK", "kSpiMiso": "SPI_MISO", "kSpiMosi": "SPI_MOSI",
        "kDacCs2": "DAC_CS2", "kDacLdac": "DAC_LDAC", "kLedLatch": "LED_LATCH", "kButtonLoad": "BTN_LOAD",
        "kMuxOut": "MUX_OUT", "kMuxS0": "MUX_S0", "kMuxS1": "MUX_S1", "kMuxS2": "MUX_S2"}


def seed_pin(name):
    """Seed pin number of a libDaisy name (D7, A10 ...), from circuit.SEED's names."""
    d = LIBDAISY_A.get(name, name)
    for pin, (n, net) in circuit.SEED.items():
        parts = n.split("/")
        if name in parts or d in parts:
            return pin
    return None


def stm32(name):
    port, n = LIBDAISY_PINS[LIBDAISY_A.get(name, name)]
    return f"P{port}{n}"


# ==========================================================================================================
# The routed boards as a netlist: pads per net, the header pins joined by position
MB_PARTS, FB_PARTS = R.main.parts, R.face.parts
BOARDS = {"main": MB_PARTS, "face": FB_PARTS}


def pads_on(board, net):
    return [(ref, num) for ref, p in BOARDS[board].items() for num, pad in p["pads"].items() if net and pad.net == net]


def pad_net(board, ref, num):
    return BOARDS[board][ref]["pads"][num].net


CROSS, CROSS_BACK = {}, {}           # main net -> faceplate net through coincident header pads, and back
CROSS_PIN = {}                       # (main net) -> (H ref, pin)
for ref, _, _ in circuit.HEADERS:
    for num, mp in MB_PARTS[ref]["pads"].items():
        fp = [p for p in FB_PARTS[circuit.fb_ref(ref)]["pads"].values() if math.hypot(p.x - mp.x, p.y - mp.y) < 0.05]
        if len(fp) == 1 and mp.net and fp[0].net:
            CROSS.setdefault(mp.net, set()).add(fp[0].net)
            CROSS_BACK.setdefault(fp[0].net, set()).add(mp.net)
            CROSS_PIN.setdefault(mp.net, set()).add((ref, num))


def reach(main_net):
    """Every (board, ref, pad) on a main-board net and on the faceplate nets it crosses to."""
    out = {("main", r, n) for r, n in pads_on("main", main_net)}
    for f in CROSS.get(main_net, ()):
        out |= {("face", r, n) for r, n in pads_on("face", f)}
    return out


def two_pin(board):
    return {ref: (p["pads"]["1"].net, p["pads"]["2"].net) for ref, p in BOARDS[board].items()
            if ref.startswith("R") and set(p["pads"]) == {"1", "2"}}


RES = {"main": two_pin("main"), "face": two_pin("face")}
TL_SECTIONS = {1: ("1", "2", "3"), 2: ("7", "6", "5"), 3: ("8", "9", "10"), 4: ("14", "13", "12")}  # SLOS080: out, in-, in+
OPAMPS = [(u, s) for u in ("U3", "U4", "U5", "U6") for s in TL_SECTIONS]


def section_with(pin_idx, net):
    """(u, s) of the TL074 section whose pin (0 out, 1 in-, 2 in+) is on `net`."""
    hits = [(u, s) for u, s in OPAMPS if pad_net("main", u, TL_SECTIONS[s][pin_idx]) == net]
    return hits[0] if len(hits) == 1 else None


def resistor_between(board, a, b_pred):
    """Resistors with one pin on net a and the other satisfying b_pred."""
    out = []
    for ref, (n1, n2) in RES[board].items():
        if n1 == a and b_pred(n2):
            out.append((ref, n2))
        elif n2 == a and b_pred(n1):
            out.append((ref, n1))
    return out


JACK_LABEL = {ref: label for ref, label, tip, tn in circuit.JACKS}
W = R.face.outline[2]


def jack_of_face_net(net):
    j = [ref for ref in JACK_LABEL if pad_net("face", ref, "3") == net]
    return j[0] if len(j) == 1 else None


def jack_side(ref):
    """'t' or 'X' half of the panel, front view (x_front = W - x)."""
    x_front = W - FB_PARTS[ref]["x"]
    return "t" if x_front < W / 2 else "X"


def out_to_jack(oa_net):
    """Op-amp output net -> series resistor -> header -> faceplate jack tip (ref)."""
    for ref, other in resistor_between("main", oa_net, lambda n: n in CROSS):
        for f in CROSS[other]:
            j = jack_of_face_net(f)
            if j:
                return j, ref, other
    return None, None, None


# ==========================================================================================================
# A  Seed pins
pin_bad, route_bad, port_bad, mask_bad = [], [], [], []
for const, role in ROLE.items():
    name = PINS.get(const)
    sp = seed_pin(name) if name else None
    if sp is None or circuit.SEED[sp][1] != role:
        pin_bad.append((const, name, sp, sp and circuit.SEED[sp][1], role))
        continue
    if pad_net("main", "U2", sp) != role:
        route_bad.append((const, name, sp, pad_net("main", "U2", sp), role))
    st = stm32(name)
    if SEED_STM32.get(sp) != st or (const in PIN_COMMENT and PIN_COMMENT[const] != st) \
            or (const in ASSERTS and f"P{ASSERTS[const][0]}{ASSERTS[const][1]}" != st):
        port_bad.append((const, name, "libDaisy", st, "datasheet", SEED_STM32.get(sp), "comment", PIN_COMMENT.get(const),
                         "assert", ASSERTS.get(const)))
ck.check("A.pin_constants_vs_circuit", not pin_bad,
         f"each hal_daisy.cc pin constant on the Seed pin circuit.SEED gives its role (design.md's pin map); bad {pin_bad}")
ck.check("A.pin_constants_vs_routed_U2", not route_bad,
         f"the routed U2 pad of each constant's Seed pin carries the role's net; bad {route_bad}")
ck.check("A.ports_vs_libDaisy_and_datasheet", not port_bad and len(ASSERTS) >= 11,
         f"libDaisy v9.0.0 port/pin = Daisy datasheet Table 2 = the '// Pxn' comment = the static_assert; "
         f"{len(ASSERTS)} asserts; bad {port_bad}")
for const in ASSERTS:
    if const not in PINS:
        port_bad.append((const, "asserted but not a pin constant"))
# masks: bit and port of each register mask against the pin it stands for, and the register it is used on
MASK_PIN = {"kClockTMask": "kClockT", "kClockXMask": "kClockX", "kProbeMask": "kProbe", "kCs1Mask": "kDacCs1",
            "kCs2Mask": "kDacCs2", "kLdacMask": "kDacLdac", "kLatchMask": "kLedLatch", "kLoadMask": "kButtonLoad"}
for mask, const in MASK_PIN.items():
    bit, port = MASKS.get(mask, (None, None))
    want = stm32(PINS[const])
    if f"P{port}{bit}" != want:
        mask_bad.append((mask, f"P{port}{bit}", want))
for i, (bit, port) in enumerate(GATE_MASKS):
    want = stm32(PINS[f"kGate{i + 1}"])
    if f"P{port}{bit}" != want:
        mask_bad.append((f"kGateMask[{i}]", f"P{port}{bit}", want))
uses = re.findall(r"GPIO([A-K])->(IDR|BSRR)\s*(?:=|&)\s*(?:high \? )?(k\w+Mask)", HAL)
for port, reg, mask in uses:
    if MASKS.get(mask, (None, port))[1] != port:
        mask_bad.append((mask, "used on GPIO" + port, "declared for GPIO" + str(MASKS.get(mask, (0, '?'))[1])))
dacs = re.search(r"i < 2 \? &GPIO([A-K])->BSRR : &GPIO([A-K])->BSRR;\s*const uint32_t cs = i < 2 \? (k\w+) : (k\w+);", HAL)
if not dacs or (MASKS[dacs.group(3)][1], MASKS[dacs.group(4)][1]) != (dacs.group(1), dacs.group(2)):
    mask_bad.append(("WriteDacs CS ports", dacs and dacs.groups()))
if not re.search(r"bsrr \|= \(gates & \(1 << i\)\) \? kGateMask\[i\] : kGateMask\[i\] << 16;\s*\}\s*GPIO" + GATE_MASKS[0][1] + r"->BSRR = bsrr;", HAL):
    mask_bad.append(("WriteGates", "not GPIO" + GATE_MASKS[0][1]))
ck.check("A.register_masks", not mask_bad and len(uses) >= 8,
         f"each '1 << n  // GPIOx' mask is its pin's port and bit (libDaisy v9.0.0) and is only used on that port's IDR / "
         f"BSRR; {len(uses)} uses; bad {mask_bad}")
pupd = re.search(r"GPIO([A-K])->PUPDR = \(GPIO\1->PUPDR & ~\(3u << \((\d+) \* 2\)\)\) \| \((\d)u << \(\2 \* 2\)\);", HAL)
ck.check("A.MISO_pull_up", bool(pupd) and f"P{pupd.group(1)}{pupd.group(2)}" == stm32(PINS["kSpiMiso"]) and pupd.group(3) == "1",
         f"GPIOx_PUPDR field of the MISO pin set to 01 (pull-up, STM32 GPIO convention; RM0433 not fetched); got "
         f"{pupd.groups() if pupd else None}, MISO is {stm32(PINS['kSpiMiso'])}")
used = list(PINS.values()) + CV_PINS
dups = [n for n, c in collections.Counter(LIBDAISY_A.get(n, n) for n in used).items() if c > 1]
ck.check("A.no_pin_used_twice", not dups, f"pin constants and kCvPins on distinct Seed pins; repeated {dups}")
# ADC-capable: every CV pin and the mux output
adc_bad = []
for name in CV_PINS + [PINS["kMuxOut"]]:
    st = stm32(name)
    ch = LIBDAISY_ADC1.get(st)
    ds = DS_PIN.get(st, (None, ""))[1]
    m = re.match(r"ADC1\d*_INP(\d+)", ds)
    if ch is None or not m or int(m.group(1)) != ch:
        adc_bad.append((name, st, "libDaisy ADC1 ch", ch, "DS12556", ds))
ck.check("A.adc_capable_pins", not adc_bad and len(CV_PINS) == 7,
         f"kCvPins {CV_PINS} and kMuxOut {PINS['kMuxOut']}: each in libDaisy's ADC1 channel map with the same ADC1 input "
         f"DS12556 Table 7 lists; bad {adc_bad}")
# the CV stage's swing into those pins: V_adc = Vb (1 + Rf/Rin) - (Rf/Rin) V_in, limited by the TL074's swing
mbp = {p.ref: p for p in circuit.main_board_parts()}
rin, rf = harness.ohms(mbp["R21"].value), harness.ohms(mbp["R22"].value)
vb = V3V3 * harness.ohms(mbp["R46"].value) / (harness.ohms(mbp["R45"].value) + harness.ohms(mbp["R46"].value))
# M1 (2026-11-13): design.md used to say "a ±12 V input pushes about 1.3 mA ... into the protection diodes"; it now
# gives the range "±12 V lands on a–b V" and says +12 V stays above ground
m = max(re.finditer(r"±(\d+) V lands on ([\d.]+)–([\d.]+) V", DESIGN), key=lambda x: float(x.group(1)), default=None)
v_spec = float(m.group(1)) if m else 12.0
swing_bad = []
for k, (name, *_r) in enumerate(circuit.CV_CHANNELS):
    pin = seed_pin(CV_PINS[k])
    st = stm32(CV_PINS[k])
    v_hi = min(vb * (1 + rf / rin) + rf / rin * v_spec, 12.0 - TL074_SWING)
    v_max = VIN_MAX_TT if DS_PIN[st][0].startswith("TT") else V3V3 + VIN_MAX_FT_ABOVE_VDD
    # verifier change: the FT limit is also capped by the Seed's 5 V (datasheet Table 1), and every CV pin is an
    # active ADC input, limited to 3V3A + 0.3 V (AN4899) whatever its I/O structure
    v_max = min(v_max, SEED_GPIO_MAX, V3V3 + VIN_MAX_ANALOG_ABOVE_VDDA)
    if v_hi > v_max or (pin in SEED_3V3_TOLERANT) != DS_PIN[st][0].startswith("TT"):
        swing_bad.append((name, CV_PINS[k], f"Seed pin {pin}", st, DS_PIN[st][0], f"stage reaches {v_hi:.2f} V",
                          f"limit {v_max:.1f} V"))
v_lim = (vb * (1 + rf / rin) - VIN_MAX_TT) / (rf / rin)
ck.check("A.cv_pins_survive_stage_swing", not swing_bad,
         f"design.md: a ±{v_spec:.0f} V input is safe; the stage drives {vb * (1 + rf / rin) + rf / rin * v_spec:.2f} V "
         f"into the ADC pin for -{v_spec:.0f} V in, and the STM32 has no clamp to VDD on FT / TT pins (DS12556 Table 20: "
         f"+0 mA injection), so the 1k does not help; TT pins (3.3 V tolerant, Daisy datasheet pins 24/25/28/29/30) are "
         f"rated 4.0 V absolute (Table 19), reached at {v_lim:.1f} V in; as active ADC inputs all seven pins, FT_a or "
         f"TT_a, are limited to 3V3A + 0.3 V (AN4899), reached at "
         f"{(vb * (1 + rf / rin) - V3V3 - VIN_MAX_ANALOG_ABOVE_VDDA) / (rf / rin):.1f} V in; bad {swing_bad}")
# verifier change (M1): the old form took abs() of the pin voltage, so a pin above ground read as conducting
v_lo = vb * (1 + rf / rin) - rf / rin * v_spec
neg_i = max(-v_lo - 0.3, 0.0) / harness.ohms(mbp["R23"].value)
doc_gnd = re.search(r"\+12 V stays\s+above ground", DESIGN)
ck.check("A.cv_pins_negative_injection", neg_i <= IINJ_NEG_MAX and v_lo >= 0 and doc_gnd is not None
         and m is not None and abs(float(m.group(2)) - v_lo) < 0.005,
         f"+{v_spec:.0f} V in: the nominal stage holds the pin at {v_lo:.3f} V, {neg_i * 1e3:.2f} mA into the VSS clamp "
         f"(0.3 V taken), DS12556 limit -5 mA; design.md: '{m.group(0) if m else None}', '+12 V stays above ground' "
         f"{'found' if doc_gnd else 'missing'} (the worst corners are test_analog_dc's B.no_negative_injection and "
         f"B.iinj_abs_max)")
# SPI1 alternate functions and the bus configuration
spi_bad = []
for const, func in (("kSpiSck", "SCK"), ("kSpiMiso", "MISO"), ("kSpiMosi", "MOSI")):
    if stm32(PINS[const]) not in SPI1_AF5[func]:
        spi_bad.append((const, stm32(PINS[const]), func))
cfg = dict(re.findall(r"config\.(\w+(?:\.\w+)?) = ([^;]+);", HAL))
ok = (cfg.get("periph", "").endswith("SPI_1") and cfg.get("pin_config.sclk") == "kSpiSck"
      and cfg.get("pin_config.miso") == "kSpiMiso" and cfg.get("pin_config.mosi") == "kSpiMosi"
      and cfg.get("nss", "").endswith("SOFT") and cfg.get("pin_config.nss") == "Pin()" and cfg.get("datasize") == "16"
      and cfg.get("mode", "").endswith("MASTER") and cfg.get("direction", "").endswith("TWO_LINES"))
ck.check("A.spi1_pins_and_config", not spi_bad and ok,
         f"SCK / MISO / MOSI on SPI1's AF5 pins (DS12556 AF table, libDaisy spi1 pin tables), SPI_1 master, two lines, "
         f"16-bit, soft NSS with no NSS pin (D7 / PG10 is SPI1_NSS but a GPIO chip select here); bad {spi_bad}, config {cfg}")

# ==========================================================================================================
# B  channels and bits through the routed boards
# device pins each control pin must reach (main board and, across the headers, the faceplate)
REACH = {"kClockT": {("main", "Q1", "3")}, "kClockX": {("main", "Q2", "3")},
         "kDacCs1": {("main", "U7", "3")}, "kDacCs2": {("main", "U8", "3")},
         "kSpiSck": {("main", "U7", "4"), ("main", "U8", "4"), ("face", "U9", "11"), ("face", "U10", "11"), ("face", "U11", "2")},
         "kSpiMosi": {("main", "U7", "5"), ("main", "U8", "5"), ("face", "U9", "14")},
         "kSpiMiso": {("face", "U11", "9")}, "kDacLdac": {("main", "U7", "8"), ("main", "U8", "8")},
         "kLedLatch": {("face", "U9", "12"), ("face", "U10", "12")}, "kButtonLoad": {("face", "U11", "1")},
         "kMuxOut": {("face", "U1", "3")}, "kMuxS0": {("face", "U1", "11")}, "kMuxS1": {("face", "U1", "10")},
         "kMuxS2": {("face", "U1", "9")}, "kProbe": {("face", "R9", "2"), ("face", "R10", "2")}}
reach_bad = []
for const, want in REACH.items():
    got = reach(pad_net("main", "U2", seed_pin(PINS[const])))
    if not want <= got:
        reach_bad.append((const, sorted(want - got)))
ck.check("A.pins_reach_their_device_pins", not reach_bad,
         f"each control pin's routed net (across the header pads by position) reaches the device pins it drives / reads "
         f"(Q collector, MCP4922 CS/SCK/SDI/LDAC, 595 SRCLK/SER/RCLK, 165 CLK/QH/SH-LD, 4051 COM/S0-S2, R9/R10); "
         f"missing {reach_bad}")

# CV inputs: hal.h CvInput order -> kCvPins -> Seed pin -> 1k -> op-amp out -> section in- -> 100k -> header -> jack
CV_WANT = {"CV_T_RATE": ("RATE", None), "CV_T_BIAS": ("BIAS", "t"), "CV_T_JITTER": ("JITTER", None),
           "CV_DEJA_VU": ("DEJA VU", None), "CV_X_SPREAD": ("SPREAD", None), "CV_X_BIAS": ("BIAS", "X"),
           "CV_X_STEPS": ("STEPS", None)}
cv_names = enum(HAL_H, "CvInput")
cv_bad = []
for k, name in enumerate(cv_names):
    net = pad_net("main", "U2", seed_pin(CV_PINS[k]))
    path = [net]
    jack = None
    for r1, oa in resistor_between("main", net, lambda n: section_with(0, n) is not None):
        u, s = section_with(0, oa)
        inm = pad_net("main", u, TL_SECTIONS[s][1])
        for r2, cv in resistor_between("main", inm, lambda n: n in CROSS):
            for f in CROSS[cv]:
                jack = jack_of_face_net(f) or jack
            path += [r1, f"{u}.{s}", r2, cv]
    label, side = CV_WANT.get(name, (None, None))
    if not jack or JACK_LABEL[jack] != label or (side and jack_side(jack) != side):
        cv_bad.append((name, CV_PINS[k], path, jack, jack and JACK_LABEL[jack]))
ck.check("B.cv_inputs_to_jacks", not cv_bad and len(cv_names) == 7,
         f"hal.h CvInput i -> kCvPins[i] -> routed stage -> header -> the jack of that name (BIAS by panel half); "
         f"bad {cv_bad}")
kcv = re.findall(r"hal::(CV_\w+),\s*//\s*(ADC_CHANNEL_\w+)", ADC_CC)
want_cv = {"ADC_CHANNEL_DEJA_VU_AMOUNT": "CV_DEJA_VU", "ADC_CHANNEL_X_SPREAD_2": "CV_X_SPREAD", "ADC_CHANNEL_T_RATE": "CV_T_RATE",
           "ADC_CHANNEL_T_BIAS": "CV_T_BIAS", "ADC_CHANNEL_T_JITTER": "CV_T_JITTER", "ADC_CHANNEL_X_SPREAD": "CV_X_SPREAD",
           "ADC_CHANNEL_X_BIAS": "CV_X_BIAS", "ADC_CHANNEL_X_STEPS": "CV_X_STEPS"}
ck.check("B.adc_cc_cv_map", dict((b, a) for a, b in kcv) == want_cv,
         f"adc.cc kCv: Marbles' ADC channel -> the Marblesy CV input of the same parameter (X SPREAD in both of its slots, "
         f"LENGTH has no CV); got {kcv}")

# pots: Pot enum i = mux channel i (libDaisy writes idx bit 0 to mux_0 = kMuxS0) -> 4051 pin -> wiper -> knob
HC4051_PIN = {0: "13", 1: "14", 2: "15", 3: "12", 4: "1", 5: "5", 6: "2", 7: "4"}    # TI SCHS122O, A0..A7
POT_WANT = {"POT_T_RATE": "RATE", "POT_T_JITTER": "JITTER", "POT_DEJA_VU": "DEJA VU", "POT_T_BIAS": "BIAS (t)",
            "POT_X_STEPS": "STEPS", "POT_DEJA_VU_LENGTH": "LENGTH", "POT_X_BIAS": "BIAS (X)", "POT_X_SPREAD": "SPREAD"}
POT_LABEL = {ref: label for ref, label, *_ in circuit.POTS}
pot_names = enum(HAL_H, "Pot")
pot_bad = []
for ch, name in enumerate(pot_names):
    net = pad_net("face", "U1", HC4051_PIN[ch])
    rv = [r for r in POT_LABEL if pad_net("face", r, "2") == net]
    if len(rv) != 1 or POT_LABEL[rv[0]] != POT_WANT.get(name):
        pot_bad.append((ch, name, HC4051_PIN[ch], net, rv and POT_LABEL[rv[0]]))
mux_call = re.search(r"InitMux\((k\w+), POT_LAST, (k\w+), (k\w+), (k\w+)\)", HAL)
addr_ok = bool(mux_call) and mux_call.groups() == ("kMuxOut", "kMuxS0", "kMuxS1", "kMuxS2")
ck.check("B.pots_mux_order", not pot_bad and len(pot_names) == 8 and addr_ok,
         f"hal.h Pot i -> 74HC4051 channel Y<i> (InitMux(kMuxOut, ..., kMuxS0, kMuxS1, kMuxS2): idx bit 0 on S0) -> its "
         f"pin (SCHS122O) on the routed U1 -> the wiper of the knob of that name; bad {pot_bad}, InitMux "
         f"{mux_call.groups() if mux_call else None}")
kpot = re.findall(r"hal::(POT_\w+),\s*//\s*(ADC_CHANNEL_\w+)", ADC_CC)
want_pot = {"ADC_CHANNEL_DEJA_VU_AMOUNT": "POT_DEJA_VU", "ADC_CHANNEL_DEJA_VU_LENGTH": "POT_DEJA_VU_LENGTH",
            "ADC_CHANNEL_T_RATE": "POT_T_RATE", "ADC_CHANNEL_T_BIAS": "POT_T_BIAS", "ADC_CHANNEL_T_JITTER": "POT_T_JITTER",
            "ADC_CHANNEL_X_SPREAD": "POT_X_SPREAD", "ADC_CHANNEL_X_BIAS": "POT_X_BIAS", "ADC_CHANNEL_X_STEPS": "POT_X_STEPS"}
ck.check("B.adc_cc_pot_map", dict((b, a) for a, b in kpot) == want_pot, f"adc.cc kPot: Marbles' channel -> the pot of the "
                                                                         f"same parameter; got {kpot}")

# gates: WriteGates bit i -> kGateMask[i] (GPIO) -> Seed pin -> section in+ -> out -> 1k -> header -> jack T(i+1)
gate_bad = []
for i in range(3):
    bit, port = GATE_MASKS[i]
    lib = [n for n, pp in LIBDAISY_PINS.items() if pp == (port, bit)]
    sp = seed_pin(lib[0]) if lib else None
    net = pad_net("main", "U2", sp) if sp else None
    sec = section_with(2, net)
    jack = out_to_jack(pad_net("main", sec[0], TL_SECTIONS[sec[1]][0]))[0] if sec else None
    if not jack or JACK_LABEL[jack] != f"T{i + 1}":
        gate_bad.append((i, f"P{port}{bit}", lib, sp, net, sec, jack))
gw = re.search(r"gate_output\[i\]\[s\.frame_index\]\)\s*\{\s*gates \|= 1 << i;", GATE_H)
ck.check("B.gates_to_jacks", not gate_bad and bool(gw),
         f"GateOutputs: bit i = Marbles' gate_output[i] (t1, t2, t3) -> kGateMask[i] -> its Seed pin -> the x2.5 stage "
         f"-> jack T{{i+1}}; bad {gate_bad}")

# DAC: Marbles channel -> kSlot -> WriteDacs slot (CS1 for 0/1, CS2 for 2/3) + the word's A/B bit -> VOUT pin -> jack
order = [int(c) for c in re.findall(r"^\s*block->cv_output\[(\d)\]\[i\] = DacCode\(\1, \*v\+\+\);", MARB, re.M)]
xy = bool(re.search(r"i < kNumXChannels \? x_settings : y_settings", XYGEN))
CHANNEL_JACK = {ch: ["X1", "X2", "X3", "Y"][k] for k, ch in enumerate(order)} if xy and len(order) == 4 else {}
kslot = [int(v) for v in re.search(r"kSlot\[kNumDacChannels\] = \{([^}]*)\}", DAC_CC).group(1).split(",")]
consts = {n: int(v, 0) for n, v in re.findall(r"const uint16_t (k\w+) = (0x[0-9a-fA-F]+);", DAC_CC)}


def word(channel, code):
    """dac.cc's Word() from its parsed constants (the structure is checked in C below)."""
    c12 = min((code + 8) >> 4, 4095)
    sel = consts["kDacB"] if kslot[channel] & 1 else 0
    return sel | consts["kBuffered"] | consts["kGain1"] | consts["kActive"] | c12


cs_of_slot = lambda s: "kDacCs1" if s < 2 else "kDacCs2"          # WriteDacs: i < 2 -> CS1
dac_bad = []
for ch in range(4):
    s = kslot[ch]
    cs_net = pad_net("main", "U2", seed_pin(PINS[cs_of_slot(s)]))
    chip = [u for u in ("U7", "U8") if pad_net("main", u, "3") == cs_net]
    b = (word(ch, 0x8000) >> MCP_BIT["AB"]) & 1
    vout = "10" if b else "14"                                   # DS21897B: VOUTB 10, VOUTA 14
    jack = None
    if len(chip) == 1:
        dnet = pad_net("main", chip[0], vout)
        for r1, inn in resistor_between("main", dnet, lambda n: section_with(1, n) is not None):
            u, sec = section_with(1, inn)
            jack = out_to_jack(pad_net("main", u, TL_SECTIONS[sec][0]))[0]
    if not jack or JACK_LABEL[jack] != CHANNEL_JACK.get(ch):
        dac_bad.append((ch, CHANNEL_JACK.get(ch), "slot", s, chip, "VOUT" + ("B" if b else "A"), jack and JACK_LABEL[jack]))
ck.check("B.dac_channels_to_jacks", not dac_bad and len(CHANNEL_JACK) == 4,
         f"Marbles' cv_output[c] (Process(): X1, X2, X3 -> 1, 2, 3, Y -> 0) -> kSlot -> the chip on that chip select "
         f"(routed U7 / U8 pin 3) and the word's A/B bit -> VOUTA 14 / VOUTB 10 -> output stage -> the jack of that name; "
         f"bad {dac_bad}")
ldac_after = re.search(r"for \(int i = 0; i < 4; \+\+i\) \{[^}]*Transfer\(words\[i\]\);[^}]*\}\s*//[^\n]*\n\s*GPIOB->BSRR = kLdacMask << 16;", HAL)
ck.check("B.dac_ldac_after_four_frames", bool(ldac_after),
         "design.md: the four channels written, then one LDAC pulse for both DACs (LDAC low after the loop)")

# LEDs: a model of the routed 74HC595 chain, 16 bits shifted in MSB first, then the stage -> line -> LED it lights
mosi_f = sorted(CROSS[pad_net("main", "U2", seed_pin(PINS["kSpiMosi"]))])[0]
first = [u for u in ("U9", "U10") if pad_net("face", u, "14") == mosi_f]
second = [u for u in ("U9", "U10") if first and u != first[0] and pad_net("face", u, "14") == pad_net("face", first[0], "9")]
Q595 = ["15", "1", "2", "3", "4", "5", "6", "7"]                 # SCLS041J: QA..QH
chain = [(first[0], q) for q in Q595] + [(second[0], q) for q in Q595] if first and second else []


def shift_out(word16):
    stages = [None] * 16
    for k in range(15, -1, -1):                                  # MSB first (libDaisy FirstBit MSB)
        stages = [(word16 >> k) & 1] + stages[:-1]               # SRCLK rising: SER -> QA, QA -> QB ... QH -> next SER
    return stages


ck.check("B.595_chain_from_routed", len(chain) == 16 and shift_out(1 << 15)[15] == 1 and first == ["U9"],
         f"routed: SER (14) of {first} on the faceplate side of SPI_MOSI, its QH' (9) into SER of {second}; 16 bits MSB "
         f"first leave bit 15 in the last stage ({second[0] if second else None} QH), as hal.h says")
pin_name = {}
for ref in ("SW1", "SW2", "D14"):
    s = R.device("face", ref).get("Symbol")
    pin_name[ref] = {n: v[0] for n, v in R.symbol_pins(s).items()}


def line_end(net):
    """Where a 595 line ends: (part, pad) of an LED or button LED pad, through at most one resistor."""
    ends = [(r, n) for r, n in pads_on("face", net) if r.startswith(("SW", "D"))]
    if ends:
        return ends[0], None
    for ref, other in resistor_between("face", net, lambda n: True):
        ends = [(r, n) for r, n in pads_on("face", other) if r.startswith(("SW", "D"))]
        if ends:
            return ends[0], ref
    return None, None


LED_ENUM = enum(LEDS_H, "Led")
LED_LABEL = {"LED_T_DEJA_VU": "t deja vu", "LED_T_MODEL": "t mode", "LED_T_RANGE": "t range", "LED_X_DEJA_VU": "X deja vu",
             "LED_X_CONTROL_MODE": "X mode", "LED_X_RANGE": "X range", "LED_X_EXT": "X ext / scale"}
BTN_OF_LABEL = {label: ref for ref, label, sw in circuit.BUTTONS}
defs = [(int(a), int(b), n) for a, b, n in re.findall(r"\{\s*(-?\d+),\s*(-?\d+)\s*\},?\s*//\s*(LED_\w+)", LEDS)]
led_bad = []
for (red, green, name), enum_name in zip(defs, LED_ENUM):
    sw = BTN_OF_LABEL.get(LED_LABEL.get(enum_name))
    if name != enum_name or not sw:
        led_bad.append((name, enum_name, sw))
        continue
    bipolar = red >= 0
    for colour, bit in (("R", red), ("G", green)):
        if bit < 0:
            continue
        chip, q = chain[bit]
        end, via = line_end(pad_net("face", chip, q))
        names = pin_name["SW2" if bipolar else "SW1"]
        want = ("LED R" if colour == "R" else "LED G") if bipolar else "LED A"
        if not end or end[0] != sw or names.get(end[1]) != want:
            led_bad.append((enum_name, colour, bit, f"{chip}.{q}", end, via, "want", sw, want))
    if not bipolar and pad_net("face", sw, "6") != "GND_D_F":
        led_bad.append((enum_name, "cathode", pad_net("face", sw, "6")))
ck.check("B.led_bits_to_buttons", not led_bad and len(defs) == 7,
         f"leds.cc: each Led's red / green bit -> chain stage of the routed 595s -> line -> (470) -> the button of that "
         f"name, red line on its 'LED R' pin, green on 'LED G' (bipolar) or 'LED A' with the cathode on GND_D_F; bad {led_bad}")
red_logic = (re.search(r"\} else if \(red\) \{\s*bits \|= 1 << d\.red;", LEDS) and
             re.search(r"\} else if \(green\) \{\s*bits \|= 1 << d\.green;", LEDS) and
             re.search(r"bits \|= 1 << \(\(phase & 1\) \? d\.red : d\.green\);", LEDS))
ck.check("B.led_bipolar_drive", bool(red_logic),
         "Leds::Bits: red = the red line high alone (green line low, so current flows R -> G through the button's LED R "
         "pin: the symbol's and the firmware's assumption, the die orientation unconfirmed), green = the green line alone, "
         "yellow = the two alternated per refresh")
out_bits = [int(v) for v in re.search(r"output_led_bit\[kNumOutputLeds\] = \{([^}]*)\}", LEDS).group(1).split(",")]
oled_bad = []
for ch, bit in enumerate(out_bits):
    chip, q = chain[bit]
    end, via = line_end(pad_net("face", chip, q))
    if not end or not end[0].startswith("D") or pin_name["D14"].get(end[1]) != "A":
        oled_bad.append((ch, bit, end))
        continue
    led = FB_PARTS[end[0]]
    jack = min(JACK_LABEL, key=lambda j: math.hypot(FB_PARTS[j]["x"] - led["x"], FB_PARTS[j]["y"] - led["y"]))
    if JACK_LABEL[jack] != CHANNEL_JACK.get(ch):
        oled_bad.append((ch, CHANNEL_JACK.get(ch), bit, f"{chip}.{q}", end[0], "nearest jack", JACK_LABEL[jack]))
spare = [k for k in range(16) if k not in [d[0] for d in defs] + [d[1] for d in defs] + out_bits]
spare_ok = all(pad_net("face", *chain[k]) is None for k in spare)
ck.check("B.output_led_bits", not oled_bad and spare_ok and len(spare) == 1,
         f"output_led_bit[c] -> stage -> 470 -> the anode of the LED beside the jack of channel c (Y, X1, X2, X3); the "
         f"one unused bit {spare} is the routed spare output; bad {oled_bad}")

# buttons: a model of the routed 74HC165 read: /PL loads A..H, then 16 rising edges, MISO sampled before each shift
miso_f = sorted(CROSS[pad_net("main", "U2", seed_pin(PINS["kSpiMiso"]))])[0]
sr165 = [u for u in ("U11",) if pad_net("face", u, "9") == miso_f]
IN165 = ["11", "12", "13", "14", "3", "4", "5", "6"]              # SCLS116H: A..H
SW_ENUM = enum(SW_H, "Switch")
SW_LABEL = {"SWITCH_T_DEJA_VU": "t deja vu", "SWITCH_T_MODEL": "t mode", "SWITCH_T_RANGE": "t range",
            "SWITCH_X_DEJA_VU": "X deja vu", "SWITCH_X_MODE": "X mode", "SWITCH_X_RANGE": "X range", "SWITCH_X_EXT": "X ext / scale"}
sw_input = [int(v) for v in re.findall(r"^\s*(\d),?\s*//\s*SWITCH_\w+", SW, re.M)]
sw_names = re.findall(r"^\s*\d,?\s*//\s*(SWITCH_\w+)", SW, re.M)


def read_buttons(pressed):
    """The byte ReadButtons() returns with the given buttons held, from the routed U11 pads."""
    level = []
    for p in IN165:
        net = pad_net("face", "U11", p)
        if net == "GND_D_F":
            level.append(0)
            continue
        btn = [r for r, n in pads_on("face", net) if r.startswith("SW")]
        pull = resistor_between("face", net, lambda n: n == "3V3D_F")
        level.append(0 if (btn and btn[0] in pressed) or not pull else 1)
    reg = level[:]                                                # reg[7] = H drives QH after the load
    ser = 0 if pad_net("face", "U11", "10") == "GND_D_F" else 1
    word16 = 0
    for edge in range(16):
        word16 = (word16 << 1) | reg[7]                           # sampled at the rising edge (mode 0)
        reg = [ser] + reg[:-1]                                    # then the 165 shifts towards QH
    return (word16 >> 8) & 0xFF


btn_bad = []
if not (sr165 and len(sw_input) == 7 == len(SW_ENUM) and re.search(r"Transfer\(0\) >> 8", HAL)):
    btn_bad.append(("structure", sr165, sw_input, sw_names))
else:
    idle = read_buttons(set())
    if not all((idle >> sw_input[s]) & 1 for s in range(7)) or (idle & 0x7F) == 0:
        btn_bad.append(("idle reading", hex(idle)))
    for ref, label, sw in circuit.BUTTONS:
        r = read_buttons({ref})
        got = [SW_ENUM[s] for s in range(7) if not (r >> sw_input[s]) & 1]
        want = [n for n in SW_ENUM if SW_LABEL[n] == label]
        if got != want:
            btn_bad.append((ref, label, hex(r), got))
ck.check("B.buttons_through_165", not btn_bad,
         f"pressing each button alone (routed U11: inputs A..H pins, pull-ups, H tied low, SER low, QH -> MISO) gives a "
         f"ReadButtons() byte in which exactly the Switch of that name reads pressed (switches.cc switch_input); idle "
         f"0x{read_buttons(set()):02x}; bad {btn_bad}")
# the host tests' board model (firmware/test/build/board_tables.h, generated from circuit.py by gen_board_tables.py;
# a build output, checked only when present) against the same tables derived here from the routed pads
red_r, green_r = [-1] * 7, [-1] * 7
for k in range(16):
    end, via = line_end(pad_net("face", *chain[k])) if chain else (None, None)
    if not end or not end[0].startswith("SW"):
        continue
    label = [lb for r, lb, s in circuit.BUTTONS if r == end[0]][0]
    i = [n for n in LED_ENUM if LED_LABEL[n] == label]
    nm = pin_name["SW2" if pad_net("face", end[0], "6") != "GND_D_F" else "SW1"].get(end[1])
    if i and nm in ("LED R", "LED G", "LED A"):
        (red_r if nm == "LED R" else green_r)[LED_ENUM.index(i[0])] = k
out_r = [-1] * 4
for k in range(16):
    end, via = line_end(pad_net("face", *chain[k])) if chain else (None, None)
    if end and end[0].startswith("D"):
        led = FB_PARTS[end[0]]
        jack = min(JACK_LABEL, key=lambda j: math.hypot(FB_PARTS[j]["x"] - led["x"], FB_PARTS[j]["y"] - led["y"]))
        ch = [c for c, lb in CHANNEL_JACK.items() if lb == JACK_LABEL[jack]]
        if ch:
            out_r[ch[0]] = k
sw_r = []
for n in SW_ENUM:
    ref = BTN_OF_LABEL[SW_LABEL[n]]
    net = pad_net("face", ref, "3")
    sw_r.append([i for i, p in enumerate(IN165) if pad_net("face", "U11", p) == net][0])
routed_tables = {"kLedRedBit": red_r, "kLedGreenBit": green_r, "kOutputLedBit": out_r, "kSwitchInput": sw_r,
                 "kDacSlotOfChannel": kslot if not dac_bad else None}
try:
    BT = fw("test", "build", "board_tables.h")
except OSError:
    BT = None
if BT is not None:
    bt = {n: [int(v) for v in vals.split(",")] for n, vals in re.findall(r"const int (k\w+)\[\d\] = \{([^}]*)\};", BT)}
    diff = {n: (bt.get(n), v) for n, v in routed_tables.items() if bt.get(n) != v}
    ck.check("B.board_tables_h_vs_routed", not diff,
             f"firmware/test/build/board_tables.h (the host tests' board model, built from circuit.py) against the tables "
             f"read off the routed pads here; differences (header file, routed) {diff}")
else:
    print("note  B.board_tables_h_vs_routed: firmware/test/build/board_tables.h not built, not compared")
pl_seq = re.search(r"GPIOB->BSRR = kLoadMask << 16;\s*Wait\((\d+)\);\s*GPIOB->BSRR = kLoadMask;\s*Wait\((\d+)\);\s*return static_cast<uint8_t>\(Transfer\(0\) >> 8\);", HAL)
ck.check("B.buttons_load_then_shift", bool(pl_seq), "ReadButtons: /PL low, wait, /PL high, wait, then one 16-bit frame")

# ==========================================================================================================
# C  the MCP4922 word
bits_ok = (consts.get("kDacB") == 1 << MCP_BIT["AB"] and consts.get("kBuffered") == 1 << MCP_BIT["BUF"]
           and consts.get("kGain1") == 1 << MCP_BIT["GA"] and consts.get("kActive") == 1 << MCP_BIT["SHDN"])
ck.check("C.mcp4922_command_bits", bits_ok,
         f"DS21897B Register 5-1: A/B bit 15 (1 = B), BUF 14 (1 = buffered), GA 13 (1 = 1x), SHDN 12 (1 = active); "
         f"dac.cc {{ {', '.join(f'{k} 0x{v:04x}' for k, v in consts.items())} }}")
struct = (re.search(r"code_12 = \(static_cast<uint32_t>\(code\) \+ 8\) >> 4;\s*if \(code_12 > 4095\) \{\s*code_12 = 4095;", DAC_CC)
          and re.search(r"select = \(kSlot\[channel\] & 1\) \? kDacB : 0;\s*return select \| kBuffered \| kGain1 \| kActive \| code_12;", DAC_CC)
          and re.search(r"words\[kSlot\[i\]\] = Word\(i, codes\[i\]\);", DAC_CC))
q_err = max(abs(((c + 8) >> 4) * 16 - c) for c in range(0, 65536 - 8, 7))
ck.check("C.mcp4922_word_layout", bool(struct) and q_err <= 8 and word(0, 65535) & 0xFFF == 4095 and word(0, 0) & 0xFFF == 0,
         f"Word(): 16-bit code rounded to 12 bits ((code + 8) >> 4, clamped at 4095; worst rounding {q_err} of 16), data in "
         f"bits 11-0, A/B from the slot's parity, the word placed in its slot; VOUT = VREF * D / 4096 at gain 1")
mb = {p.ref: p for p in circuit.main_board_parts()}
vdd_net = {mb["U7"].nets["1"], mb["U8"].nets["1"]}
vref_max = VREF_NOM * (1 + VREF_TOL)
vdd_min = V3V3 * (1 - V3V3_TOL)
ck.check("C.mcp4922_buffered_vref_range", vdd_net == {"3V3A"} and vref_max <= vdd_min - MCP_VREF_BUF_MARGIN
         and vdd_min >= MCP_VDD_MIN and consts.get("kBuffered"),
         f"buffered VREF input 0.040 .. VDD - 0.040 V (DS21897B) at VDD = 3V3A min {vdd_min:.2f} V: LM4040 up to "
         f"{vref_max:.4f} V fits under {vdd_min - MCP_VREF_BUF_MARGIN:.2f} V; VDD >= {MCP_VDD_MIN} V")

# ==========================================================================================================
# D  SPI timing
presc = SPI_PRESCALER.get(re.search(r"BaudPrescaler::(PS_\d+)", HAL).group(1))
F_SCK = F_PLL2P / presc
T_SCK = 1 / F_SCK
T_HALF = T_SCK / 2 - T_SCK_DUTY
mode0 = "ClockPolarity::LOW" in HAL and "ClockPhase::ONE_EDGE" in HAL
ck.close("D.spi_clock", F_SCK / 1e6, 6.25, 0.005, " MHz")
ck.check("D.spi_clock_tree", abs(F_CPU - 480e6) < 1 and abs(F_PLL2P - 25e6) < 1 and "hw.Init(true)" in MAIN,
         f"libDaisy v9.0.0: HSE 16 MHz / {PLL1['M']} x {PLL1['N']} / {PLL1['P']} = {F_CPU / 1e6:.0f} MHz (Init(true) = Boost); "
         f"PLL2 16 MHz / {PLL2['M']} x ({PLL2['N']} + {PLL2['FRACN']}/8192) / {PLL2['P']} = {F_PLL2P / 1e6:.2f} MHz -> SPI1 "
         f"(SPI123 from PLL2P) / {presc}")
WAITS = {int(n) for n in re.findall(r"Wait\((\d+)\);", HAL)}
wait_loop = re.search(r"for \(volatile uint32_t i = 0; i < \(ns \+ 4\) / 5; \+\+i\) \{ \}", HAL)


def wait_min(ns):
    """The shortest time Wait(ns) can take: (ns + 4) / 5 iterations of >= WAIT_CYCLES_MIN cycles."""
    return ((ns + 4) // 5) * WAIT_CYCLES_MIN / F_CPU


wbad = [(ns, round(wait_min(ns) * 1e9, 1)) for ns in sorted(WAITS) if wait_min(ns) < ns * 1e-9]
ck.check("D.wait_loop_lower_bound", bool(wait_loop) and not wbad and 5e-9 * F_CPU <= WAIT_CYCLES_MIN,
         f"Wait(ns) runs (ns + 4) / 5 iterations; at {F_CPU / 1e6:.0f} MHz it lasts >= ns if an iteration takes >= "
         f"{5e-9 * F_CPU:.1f} cycles (assumed >= {WAIT_CYCLES_MIN}, the volatile load / add / store / load / compare chain); "
         f"calls {sorted(WAITS)}; too short {wbad}")


def waits_in(func):
    body = re.search(r"\n[^\n]*\b" + func + r"\([^)]*\) \{(.*?)\n\}", HAL, re.S).group(1)
    return [int(n) for n in re.findall(r"Wait\((\d+)\)", body)]


wd, wl, wb = waits_in("WriteDacs"), waits_in("WriteLeds"), waits_in("ReadButtons")
# The SPI's RXP (polled by Transfer) is taken as set at the earliest at the frame's last sampling edge (the 16th rising
# SCK edge in mode 0, as the STM32 reference manuals describe RXNE / RXP); polling and the RXDR read are not counted.
# verifier note (no change): RM0433's SPI chapter (read through docs.dirba.io's copy) says only that RXP "is set by
# hardware when at least one complete data packet" is in the RxFIFO, that with CPHA = 0 "the first edge on the SCK pin
# captures the first data bit", and that "all the control and status signals between these domains are strictly
# synchronized" (kernel clock -> APB): a real but unquantified latency. No document bounds it, so the bound above
# stays the earliest case; DS21897B Rev B AC table: tIDLE >= 40 ns, tCSH >= 15 ns, tCHS >= 15 ns, "by design and
# characterization".
ck.check("D.mcp4922_clock", mode0 and F_SCK <= MCP_FCLK_MAX and T_HALF >= MCP_THI,
         f"mode 0 (CPOL 0, CPHA 0, a mode the MCP4922 supports); fSCK {F_SCK / 1e6:.2f} MHz <= 20 MHz; SCK high / low "
         f">= {T_HALF * 1e9:.0f} ns >= 15 ns (DS21897B)")
setup_avail = T_HALF - TV_MO - T_EDGE_SPEED00
ck.check("D.mcp4922_data_setup_hold", setup_avail >= MCP_TSU and T_HALF + TH_MO >= MCP_THD,
         f"MOSI changes after SCK falls (tv(MO) <= 3 ns, slow GPIO edges {T_EDGE_SPEED00 * 1e9:.1f} ns), so it is stable "
         f"{setup_avail * 1e9:.0f} ns before the rising edge (tSU >= 15 ns) and {T_HALF * 1e9:.0f} ns after (tHD >= 10 ns)")
ck.check("D.mcp4922_cs_timing", len(wd) == 3 and wait_min(wd[0]) >= MCP_TCHS and wait_min(wd[1]) >= MCP_TCSH
         and wait_min(wd[1]) >= MCP_TLS and wait_min(wd[2]) >= MCP_TLD,
         f"WriteDacs waits {wd} ns: CS hold after the last rising edge >= {wait_min(wd[0]) * 1e9:.1f} ns (tCHS 15), CS high "
         f">= {wait_min(wd[1]) * 1e9:.1f} ns (tCSH 15), CS to LDAC >= {wait_min(wd[1]) * 1e9:.1f} ns (tLS 40), LDAC low >= "
         f"{wait_min(wd[2]) * 1e9:.1f} ns (tLD 100)")
idle = wait_min(wd[0]) + wait_min(wd[1]) - T_SCK / 2
ck.check("D.mcp4922_sck_idle_before_cs", idle >= MCP_TIDLE,
         f"between two DAC frames the last SCK falling edge comes T/2 = {T_SCK / 2 * 1e9:.0f} ns after the last rising edge; "
         f"if RXP is set at that rising edge, CS falls again Wait({wd[0]}) + Wait({wd[1]}) >= "
         f"{(wait_min(wd[0]) + wait_min(wd[1])) * 1e9:.1f} ns later, i.e. {idle * 1e9:.1f} ns after SCK went idle, against "
         f"tIDLE >= 40 ns (DS21897B); the RXP latency and the RXDR read add an unknown few tens of ns")
# verifier change (all 74HC checks below): onsemi's 3.0 V guarantees in place of the TI 2.0 / 4.5 V interpolation
f595 = HC595_3V0["fclock"]
ck.check("D.hc595_clock", F_SCK <= f595 and T_HALF >= HC595_3V0["tw"],
         f"74HC595 at 3V3D >= {VCC_HC:.2f} V (onsemi MC74HC595A, 3.0 V, -55..85 C): fclock <= {f595 / 1e6:.0f} MHz, tw >= "
         f"{HC595_3V0['tw'] * 1e9:.0f} ns; bus {F_SCK / 1e6:.2f} MHz, high / low {T_HALF * 1e9:.0f} ns (TI SN74HC595 at its 2.0 V "
         f"figures: {HC595['fclock'][0] / 1e6:.0f} MHz, {HC595['tw'][0] * 1e9:.0f} ns)")
need = HC595_3V0["tsu_ser"]
ck.check("D.hc595_ser_setup_U9", setup_avail >= need,
         f"U9 SER (MOSI) stable {setup_avail * 1e9:.0f} ns before SRCLK rises (T/2 - tv(MO) - one slow edge); needs "
         f"{need * 1e9:.0f} ns (onsemi, 3.0 V, -55..85 C; {HC595_3V0_25C['tsu_ser'] * 1e9:.0f} ns at 25 C; TI's 2.0 V figure "
         f"{HC595['tsu_ser'][0] * 1e9:.0f} ns, its 2.0 / 4.5 V line {interp(HC595['tsu_ser']) * 1e9:.0f} ns)")
casc = HC595_3V0["tpd_qh"] + HC595_3V0["tsu_ser"]
casc25 = HC595_3V0_25C["tpd_qh"] + HC595_3V0_25C["tsu_ser"]
ck.check("D.hc595_cascade_U9_to_U10", casc <= T_SCK,
         f"U10 SER = U9 QH', which changes tpd(SRCLK->QH') after each rising edge and must be set up tsu before the next: "
         f"{HC595_3V0['tpd_qh'] * 1e9:.0f} + {HC595_3V0['tsu_ser'] * 1e9:.0f} = {casc * 1e9:.0f} ns against the "
         f"{T_SCK * 1e9:.0f} ns period (onsemi, 3.0 V, -55..85 C, 50 pF; {casc25 * 1e9:.0f} ns with the 25 C limits; TI's "
         f"typical tpd {interp(HC595_TYP_TPD) * 1e9:.0f} ns); hold {HC595_3V0['th_ser'] * 1e9:.0f} ns: QH' moves tpd after "
         f"the edge (no minimum tpd is specified)")
ck.check("D.hc595_latch", len(wl) == 2 and wait_min(wl[0]) >= HC595_3V0["tsu_rclk"] and wait_min(wl[1]) >= HC595_3V0["tw"],
         f"WriteLeds: RCLK rises >= {wait_min(wl[0]) * 1e9:.1f} ns after the last SRCLK edge if RXP is set at that edge "
         f"(Wait({wl[0]}) only; the RXP latency and the RXDR read are not documented), against tsu SRCLK->RCLK "
         f"{HC595_3V0['tsu_rclk'] * 1e9:.0f} ns (onsemi, 3.0 V, -55..85 C; {HC595_3V0_25C['tsu_rclk'] * 1e9:.0f} ns at 25 C, "
         f"TI {HC595['tsu_rclk'][0] * 1e9:.0f} ns at 2.0 V); stays high >= {wait_min(wl[1]) * 1e9:.1f} ns (tw "
         f"{HC595_3V0['tw'] * 1e9:.0f} ns)")
f165 = HC165_3V0["fclock"]
ck.check("D.hc165_clock_and_load", F_SCK <= f165 and T_HALF >= HC165_3V0["tw_clk"] and len(wb) == 2
         and wait_min(wb[0]) >= HC165["tw_pl"][0] and wait_min(wb[1]) + T_SCK / 2 >= HC165["tsu_pl_clk"][0],
         f"74HC165 at 3V3D (onsemi MC74HC165A, 3.0 V, -55..85 C): fclock <= {f165 / 1e6:.0f} MHz, CLK high / low >= "
         f"{HC165_3V0['tw_clk'] * 1e9:.0f} ns; "
         f"/PL low >= {wait_min(wb[0]) * 1e9:.0f} ns (tw >= 100 ns even at 2.0 V), /PL high to the first rising edge >= "
         f"{(wait_min(wb[1]) + T_SCK / 2) * 1e9:.0f} ns (tsu >= 100 ns at 2.0 V)")
miso_t = T_EDGE_SPEED00 + HC165_3V0["tpd_clk_qh"] + TSU_MI
first_bit = wait_min(wb[0]) + wait_min(wb[1]) + T_SCK / 2 - HC165_3V0["tpd_pl_qh"] - TSU_MI
ck.check("D.hc165_to_stm32_setup_hold", miso_t <= T_SCK and first_bit >= 0 and HC165_TPD_MIN_ASSUMED >= TH_MI,
         f"QH moves tpd(CLK->QH) <= {HC165_3V0['tpd_clk_qh'] * 1e9:.0f} ns (onsemi, 3.0 V, 85 C; with TI's 2.0 V figure, "
         f"{HC165['tpd_clk_qh'][0] * 1e9:.0f} ns, it would not fit: a TI part is not guaranteed here) after the 165 sees SCK rise "
         f"(<= {T_EDGE_SPEED00 * 1e9:.1f} ns slow edge), the STM32 needs it tsu(MI) 2 ns before the next edge: "
         f"{miso_t * 1e9:.0f} ns of {T_SCK * 1e9:.0f}; D7 is out {first_bit * 1e9:.0f} ns before the first sample; hold: "
         f"th(MI) 1 ns <= the 165's (unspecified, assumed >= 5 ns) minimum delay")
vih_hc = interp(HC_VIH, V3V3 * (1 + V3V3_TOL))
voh = V3V3 * (1 - V3V3_TOL) - VOH_DROP
ck.check("D.logic_levels", voh >= MCP_VIH_FRAC * V3V3 * (1 + V3V3_TOL) and voh >= vih_hc,
         f"Seed outputs VOH >= {voh:.2f} V (VDD - 0.4 V at 8 mA, 3V3D -3 %) against the MCP4922's VIH 0.7 x 3V3A "
         f"(+3 %) = {MCP_VIH_FRAC * V3V3 * (1 + V3V3_TOL):.2f} V and the HC parts' VIH {vih_hc:.2f} V (interpolated at "
         f"3V3D +3 %)")
ck.check("D.spi_pin_speed", F_SCK <= F_MAX_SPEED00,
         f"libDaisy leaves the SPI pins at the low GPIO speed: Fmax 12 MHz at 30-50 pF (DS12556 Table 61) >= "
         f"{F_SCK / 1e6:.2f} MHz")
T_SAMPLE = 1 / cint(HAL_H, "kIoRate")
frame = 16 * T_SCK
t_dac = 4 * frame + 4 * (wait_min(wd[0]) + wait_min(wd[1])) + wait_min(wd[2])
t_led = frame + sum(wait_min(n) for n in wl)
t_btn = frame + sum(wait_min(n) for n in wb)
led_p, ui_p, ui_ph = cint(MARB, "kLedRefreshPeriod"), cint(MARB, "kUiPollPeriod"), cint(MARB, "kUiPollPhase")
apart = ui_p % led_p == 0 and ui_ph % led_p != 0
worst = t_dac + max(t_led, t_btn) if apart else t_dac + t_led + t_btn
ck.check("D.bus_time_per_sample", worst < 0.5 * T_SAMPLE and apart,
         f"per 32 kHz sample ({T_SAMPLE * 1e6:.2f} us): four DAC frames >= {t_dac * 1e6:.2f} us, plus the LED frame "
         f"({t_led * 1e6:.2f} us) every {led_p} or the buttons ({t_btn * 1e6:.2f} us) at phase {ui_ph} of {ui_p}, never "
         f"together: {worst * 1e6:.2f} us of bus time, {worst / T_SAMPLE:.0%} of the period")

# ==========================================================================================================
# E  logic polarity
fp = {p.ref: p for p in circuit.faceplate_parts()}
r_b, r_pu = harness.ohms(mb["R50"].value), harness.ohms(mb["R51"].value)
ib_clk = (5.0 - VBE_ON) / r_b
ic_need = (V3V3 - VCE_SAT) / r_pu
ib_probe = (V3V3 * (1 - V3V3_TOL) - VBE_ON) / (harness.ohms(fp["R9"].value) + r_b)
read_inv = re.search(r"ExtractGateFlags\(\s*previous_flags_\[i\],\s*!\(pins & \(1 << i\)\)\)", CLK_CC)
rcp = re.search(r"if \(GPIOB->IDR & kClockTMask\) \{\s*pins \|= 1;\s*\}\s*if \(GPIOC->IDR & kClockXMask\) \{\s*pins \|= 2;", HAL)
ck.check("E.clock_inputs_inverted", bool(read_inv) and bool(rcp) and ib_clk * HFE_MIN_01MA >= ic_need
         and MB_PARTS["Q1"]["pads"]["3"].net == pad_net("main", "U2", seed_pin(PINS["kClockT"])),
         f"a 5 V clock gives {ib_clk * 1e6:.0f} uA base current, {ib_clk * HFE_MIN_01MA * 1e3:.2f} mA at hFE min 40 >= the "
         f"{ic_need * 1e3:.2f} mA that pulls the 10k collector low: jack high = GPIO low; ReadClockPins() sets bit 0 for "
         f"PB12 high (T), bit 1 for PC11 (X), and ClockInputs::Read() takes !(pins & bit) as the gate, so a high jack reads high")
norm = re.search(r"int expected_value = normalization_probe_state_ >> 31;.*?int read_value = previous_flags_\[i\] & GATE_FLAG_HIGH;"
                 r".*?normalization_mismatch_count_\[i\] \+= read_value \^ expected_value;.*?WriteProbe\(normalization_probe_state_ >> 31\);",
                 CLK_CC, re.S)
flag_high = re.search(r"GATE_FLAG_HIGH = (\d+)", GATEFLAGS)
order_ok = MARB.index("clock_inputs.Read(s, 1);") < MARB.index("clock_inputs.ReadNormalization(s.block);")
probe_path = ({("face", "R9", "2"), ("face", "R10", "2")} <= reach("PROBE")
              and pad_net("face", "R9", "1") == pad_net("face", "J1", "2") and pad_net("face", "R10", "1") == pad_net("face", "J12", "2"))
ck.check("E.probe_polarity", bool(norm) and flag_high and flag_high.group(1) == "1" and order_ok and probe_path
         and ib_probe * HFE_MIN_01MA >= ic_need,
         f"PROBE high -> 10k + the unpatched lug + 100k -> {ib_probe * 1e6:.0f} uA base, {ib_probe * HFE_MIN_01MA * 1e3:.2f} mA "
         f"at hFE 40 >= {ic_need * 1e3:.2f} mA: the GPIO reads low and the gate flag HIGH (= 1), which ReadNormalization "
         f"compares with the bit it wrote to the probe (state >> 31) last block, reading the pins first; routed: PROBE "
         f"reaches R9 (T CLOCK J1 lug) and R10 (X CLOCK J12 lug) {probe_path}")
ck.check("E.gate_polarity", bool(re.search(r"\(gates & \(1 << i\)\) \? kGateMask\[i\] : kGateMask\[i\] << 16", HAL))
         and all(mb[u].nets[TL_SECTIONS[s][2]] == f"GATE_{n}" for n, u, s in circuit.GATES),
         "WriteGates: bit set -> BSRR set (pin high) -> the non-inverting x2.5 stage's + input -> the jack goes high")
cw = all(fp[r].nets["3"] == "3V3A_F" and fp[r].nets["1"] == "GND_F" for r, *_ in circuit.POTS)
noinv = re.search(r"values_\[ADC_GROUP_POT \+ i\] = hal::ReadPot\(kPot\[i\]\);", ADC_CC)
ck.check("E.pot_polarity", cw and bool(noinv) and "pot_scale" in fw("vendor", "marbles", "cv_reader.cc"),
         "pots: clockwise = wiper towards pin 3 = 3V3A_F = a higher reading, passed to Marbles uninverted (adc.cc), whose "
         "CvReaderChannel maps it with a positive pot_scale: clockwise raises the parameter as on Marbles")
# CV conversion: an ideal inverting stage with circuit.py's parts (bias from R45 / R46, ADC reference 3V3A) against
# the firmware's JackVoltage(), then MarblesReading() against Marbles' default calibration (0.2 per volt)
kRin, kRf, kAdcRef = cfloat(ADC_CC, "kRin"), cfloat(ADC_CC, "kRf"), cfloat(ADC_CC, "kAdcReference")
kb = re.search(r"kBiasRatio = ([\d.e]+)f / \(([\d.e]+)f \+ ([\d.e]+)f\);", ADC_CC)
kBias = float(kb.group(1)) / (float(kb.group(2)) + float(kb.group(3))) if kb else None
k_zero = kBias * (1 + kRf / kRin) if None not in (kBias, kRf, kRin) else 0
k_vpfs = kAdcRef * kRin / kRf if None not in (kAdcRef, kRf, kRin) else 1
conv_bad = []
for name, label, u, s in circuit.CV_CHANNELS:
    ri = harness.ohms([p for p in mb.values() if p.kind == "R" and set(p.nets.values()) == {f"CV_{name}", f"IN_{name}"}][0].value)
    rff = harness.ohms([p for p in mb.values() if p.kind == "R" and set(p.nets.values()) == {f"IN_{name}", f"OA_{name}"}][0].value)
    top = harness.ohms([p for p in mb.values() if p.kind == "R" and set(p.nets.values()) == {"3V3A", "BIAS"}][0].value)
    bot = harness.ohms([p for p in mb.values() if p.kind == "R" and set(p.nets.values()) == {"BIAS", "GND"}][0].value)
    for v in (-5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 5.0):
        vbias = V3V3 * bot / (top + bot)
        # node equation at the inverting input (ideal op-amp: IN at vbias): (v - vbias)/Rin + (oa - vbias)/Rf = 0
        oa = vbias - rff / ri * (v - vbias)
        reading = oa / V3V3
        jack = (k_zero - reading) * k_vpfs
        if abs(jack - v) > 1e-3:
            conv_bad.append((name, v, round(jack, 4)))
ck.check("E.cv_conversion_vs_circuit", not conv_bad and None not in (kRin, kRf, kBias, kAdcRef),
         f"adc.cc JackVoltage() with kRin {kRin}, kRf {kRf}, bias {kBias}, ref {kAdcRef} inverts each channel's stage built "
         f"from circuit.py's resistors (V_adc = BIAS (1 + Rf / Rin) - V_in Rf / Rin, ADC on 3V3A) to within 1 mV over "
         f"+-5 V; bad {conv_bad}")
mz, mv = cfloat(ADC_CC, "kMarblesZeroReading"), cfloat(ADC_CC, "kMarblesVoltsPerFullScale")
sc = re.search(r"fill\(&c\.adc_scale\[0\], &c\.adc_scale\[ADC_CHANNEL_LAST\], ([-\d.]+)f\);\s*fill\(&c\.adc_offset\[0\], &c\.adc_offset\[ADC_CHANNEL_LAST\], \+?([-\d.]+)f\);", SETTINGS)
per_volt = [(float(sc.group(1)) * (mz - v / mv) + float(sc.group(2))) / v for v in (-4.0, 1.0, 3.0)] if sc else []
ck.check("E.marbles_reading_scale", sc is not None and all(abs(p - 0.2) < 1e-6 for p in per_volt) and mz == 0.5 and mv == 10.0,
         f"MarblesReading(V) = {mz} - V / {mv} with Marbles' default calibration (scale, offset) "
         f"{sc.groups() if sc else None} gives {per_volt} per volt: the 0.2 / V that output_calibrator.h's "
         f"kVoltsPerSpreadUnit = 5 assumes")

# ==========================================================================================================
# F  the output calibration
r_dac = harness.ohms(mb["R70"].value)
r_ref = harness.ohms(mb["R71"].value)
r_f = harness.ohms(mb["R72"].value)
r_inv_in, r_inv_fb = harness.ohms(mb["R42"].value), harness.ohms(mb["R43"].value)
ref_v = float(re.search(r"(\d+\.\d+)", mb["D21"].value).group(1))
dac_vals = {name: {k: harness.ohms(mb[f"R{70 + 4 * i + k}"].value) for k in range(4)} for i, (name, *_r) in enumerate(circuit.DAC_OUTS)}
same = len({tuple(v.values()) for v in dac_vals.values()}) == 1


def v_out(code16, vref=ref_v):
    """The output stage with circuit.py's values: -(Rf/Rdac) VREF D/4096 - (Rf/Rref) (-VREF Rfb/Rin), D the 12-bit code."""
    d = min((int(code16) + 8) >> 4, 4095)
    neg = -vref * r_inv_fb / r_inv_in
    return -(r_f / r_dac) * vref * d / 4096 - (r_f / r_ref) * neg


scale_c = -65536 * r_dac * r_inv_in / (r_f * ref_v * r_inv_in)          # codes per volt, 16-bit
offset_c = 65536 * r_dac / r_ref * r_inv_fb / r_inv_in                  # the 16-bit code for 0 V
fs, fo = cfloat(DAC_H, "kDacReference"), None
kdi, kdo, kdf = cfloat(DAC_H, "kDacInputResistor"), cfloat(DAC_H, "kDacOffsetResistor"), cfloat(DAC_H, "kDacFeedbackResistor")
fw_scale = -65536.0 * kdi / (kdf * fs) if None not in (kdi, kdf, fs) else 0
fw_offset = 65536.0 * kdi / kdo if None not in (kdi, kdo) else 0
cmt = re.search(r"codes per volt, (-[\d.]+)", DAC_H), re.search(r"// 0 V, ([\d.]+)", DAC_H)
ck.check("F.nominal_scale_offset_vs_stage", same and abs(fw_scale - scale_c) < 0.5 and abs(fw_offset - offset_c) < 0.5
         and abs(float(cmt[0].group(1)) - scale_c) < 0.1 and abs(float(cmt[1].group(1)) - offset_c) < 0.1,
         f"circuit.py's stage (R70 {r_dac:.0f}, R71 {r_ref:.0f}, R72 {r_f:.0f}, R42/R43, {ref_v} V; all four outputs alike "
         f"{same}): {scale_c:.1f} codes/V, 0 V at code {offset_c:.1f}; dac.h kDacScale {fw_scale:.1f}, kDacOffset "
         f"{fw_offset:.1f} (comments {cmt[0].group(1) if cmt[0] else None}, {cmt[1].group(1) if cmt[1] else None})")
v0, v4095 = v_out(0), v_out(65535)
m = re.search(r"code 0 → \+([\d.]+) V, code 4095 → −([\d.]+) V", DESIGN)
ck.check("F.design_md_output_range", bool(m) and abs(v0 - float(m.group(1))) < 0.005 and abs(v4095 + float(m.group(2))) < 0.005,
         f"design.md '{m.group(0) if m else None}'; the stage with circuit.py's values gives {v0:+.3f} V at code 0 and "
         f"{v4095:+.3f} V at 4095")
mrow = re.search(r"code 32768 = 0 V, −(\d+) codes/V", DESIGN)
ck.check("F.marbles_6213_is_marbles_not_marblesy", bool(mrow) and abs(-float(mrow.group(1)) - MARBLES_DAC_SCALE) < 0.5
         and "kDacScale" in re.search(r"fill\(&c\.dac_scale[^;]*;", SETTINGS).group(0)
         and abs(scale_c - MARBLES_DAC_SCALE) / abs(MARBLES_DAC_SCALE) > 0.01,
         f"design.md's '-{mrow.group(1) if mrow else '?'} codes/V, code 32768 = 0 V' is Marbles' own default ({MARBLES_DAC_SCALE}, "
         f"{MARBLES_DAC_OFFSET:.0f}, upstream settings.cc), in the 'What Marbles needs' table; Marblesy's stage is "
         f"{scale_c:.1f} codes/V, 0 V at {offset_c:.1f}, and settings.cc starts from kDacScale / kDacOffset, not Marbles' figures")
boot = re.search(r"codes\[i\] = static_cast<uint16_t>\(kDacOffset\);", MAIN)
ck.check("F.startup_code_is_0V", bool(boot) and abs(v_out(int(offset_c))) < 2.5 / 4096 * r_f / r_dac,
         f"main.cc writes kDacOffset ({int(offset_c)}) first: {v_out(int(offset_c)) * 1e3:+.2f} mV, within one 12-bit step")
hi, lo = cint(CAL, "kHighCode"), cint(CAL, "kLowCode")
ui_pts = [int(v, 16) for v in re.findall(r"output_test_forced_dac_code_\[channel\] = (0x[0-9a-f]+);", UI)]
ck.check("F.factory_points", hi % 16 == 0 and lo % 16 == 0 and len(ui_pts) == 2 and min(abs(hi - p) for p in ui_pts) < 16
         and min(abs(lo - p) for p in ui_pts) < 16 and abs(v_out(hi) - 4.1) < 0.05 and abs(v_out(lo) + 2.1) < 0.06,
         f"kHighCode 0x{hi:04x} / kLowCode 0x{lo:04x}: Marbles' test points {[hex(p) for p in ui_pts]} on the 12-bit grid, "
         f"{v_out(hi):+.3f} V / {v_out(lo):+.3f} V (README: about +4.1 V and -2.1 V)")
r_out = harness.ohms(mb["R73"].value)
r_spread = harness.ohms([p for p in mb.values() if p.kind == "R" and set(p.nets.values()) == {"CV_X_SPREAD", "IN_X_SPREAD"}][0].value)
bias_c = V3V3 * harness.ohms(mb["R46"].value) / (harness.ohms(mb["R45"].value) + harness.ohms(mb["R46"].value))
k_out, k_in = cfloat(CAL, "kOutputResistor"), cfloat(CAL, "kSpreadInputResistor")
kb2 = re.search(r"kSpreadBias = ([\d.]+)f \* ([\d.e]+)f / ([\d.e]+)f;", CAL)
k_bias = float(kb2.group(1)) * float(kb2.group(2)) / float(kb2.group(3)) if kb2 else None
load_c = bias_c * r_out / (r_out + r_spread)
all_1k = all(harness.ohms(mb[f"R{73 + 4 * i}"].value) == r_out for i in range(4))
ck.check("F.load_offset_vs_circuit", all_1k and k_out == r_out and k_in == r_spread and k_bias is not None
         and abs(k_bias - bias_c) < 1e-6 and abs(k_bias * k_out / (k_out + k_in) - load_c) < 1e-6,
         f"circuit.py: output resistors {r_out:.0f} (R73/R77/R81/R85 all alike {all_1k}), X SPREAD Rin {r_spread:.0f}, bias "
         f"{bias_c:.3f} V -> {load_c * 1e3:.2f} mV; output_calibrator.h {k_out}, {k_in}, {k_bias}")
# the fit end to end with ideal parts: the jack reads (Rin V_out + Rout V_bias) / (Rin + Rout) through the calibrated
# X SPREAD input (V/5 per unit), the calibrator removes kLoadOffset and fits; the result must put V into a 100k load
volts = []
for code in (hi, lo):
    vj = (r_spread * v_out(code) + r_out * bias_c) / (r_spread + r_out)
    volts.append((vj / 5.0) * cfloat(CAL, "kVoltsPerSpreadUnit") - load_c)
f_scale = (lo - hi) / (volts[1] - volts[0])
f_offset = hi - f_scale * volts[0]
err = []
for v in (-5.0, -2.0, 0.0, 2.0, 5.0):
    code = v * f_scale + f_offset
    # continuous (unrounded) code through the stage, into 100k to ground behind the 1k
    vo = -(r_f / r_dac) * ref_v * code / 65536 + (r_f / r_ref) * ref_v * r_inv_fb / r_inv_in
    err.append(abs(vo * 100e3 / (100e3 + r_out) - v))
plaus = abs(f_scale / fw_scale - 1) <= 0.1 and abs(f_offset / fw_offset - 1) <= 0.1
ck.check("F.calibration_fit_arithmetic", max(err) < 1e-4 and plaus and "fabsf(scale / marbles::kDacScale - 1.0f) <= 0.1f" in CAL,
         f"the calibrator's two-point fit through the loaded X SPREAD reading gives {f_scale:.1f} codes/V, offset "
         f"{f_offset:.1f} ({f_scale / fw_scale - 1:+.1%} / {f_offset / fw_offset - 1:+.2%} from nominal, inside its 10 % "
         f"window), and those put -5..+5 V into a 100k load to within {max(err) * 1e3:.3f} mV")
codes5 = [5 * f_scale + f_offset, -5 * f_scale + f_offset, 5 * fw_scale + fw_offset, -5 * fw_scale + fw_offset]
ck.check("F.five_volts_inside_code_range", all(0 < c < 65535 for c in codes5) and "CONSTRAIN(voltage, -5.0f, 5.0f);" in MARB,
         f"DacCode clamps to +-5 V; +-5 V need codes {[round(c) for c in codes5]} (fitted, nominal), all inside 0..65535 "
         f"so nothing clips at ClipU16")

# ==========================================================================================================
# G  design.md / README claims
arr = re.search(r"TIM7->ARR = timer_clock / kIoRate - 1;", HAL) and re.search(r"timer_clock = 2 \* HAL_RCC_GetPCLK1Freq\(\);", HAL)
tclk = TIMER_CLK_FACTOR * PCLK1
ck.check("G.io_rate_32kHz", bool(arr) and cint(HAL_H, "kIoRate") == 32000 and abs(tclk / 32000 - round(tclk / 32000)) < 1e-9
         and "32 kHz timer interrupt" in DESIGN,
         f"design.md '32 kHz timer interrupt': TIM7 at 2 x PCLK1 = {tclk / 1e6:.0f} MHz, ARR {tclk / 32000 - 1:.0f}, exactly "
         f"{tclk / round(tclk / 32000):.1f} Hz")
bs = cint(IOBUF, "kBlockSize")
ck.check("G.five_sample_blocks", bs == 5 and "5-sample blocks" in DESIGN, f"design.md '5-sample blocks': io_buffer.h kBlockSize {bs}")
ck.check("G.led_frame_every_4_samples", led_p == 4 and "595 frame every 4 samples" in DESIGN
         and re.search(r"if \(n % kLedRefreshPeriod == 0\) \{\s*hal::WriteLeds", MARB) is not None,
         f"design.md 'the 595 frame every 4 samples': kLedRefreshPeriod {led_p} ({32000 / led_p:.0f} Hz)")
poll = re.search(r"if \(n % kUiPollPeriod == kUiPollPhase\) \{\s*ui\.Poll\(\);", MARB) and "switches_.Debounce();" in UI
ck.check("G.buttons_every_millisecond", bool(poll) and 32000 / ui_p == 1000 and "the 165 every millisecond" in DESIGN,
         f"design.md 'the 165 every millisecond': Ui::Poll() (-> Switches::Debounce() -> ReadButtons) every {ui_p} samples = "
         f"{32000 / ui_p:.0f} Hz")
m6 = re.search(r"SPI1 runs at ([\d.]+) MHz in mode (\d)", DESIGN)
ck.check("G.spi_6_25MHz_mode0", bool(m6) and abs(float(m6.group(1)) * 1e6 - F_SCK) < 1e3 and m6.group(2) == "0" and mode0,
         f"design.md '{m6.group(0) if m6 else None}': {F_SCK / 1e6:.2f} MHz, CPOL LOW + CPHA ONE_EDGE = mode 0")
yl = re.search(r"red and green alternating (\d+) times a second", README)
pw = re.search(r"16 brightness levels by PWM over 16 refreshes \((\d+) Hz\)", README)
lv = cint(LEDS_H, "kOutputLedLevels")
ck.check("G.readme_led_rates", bool(yl) and int(yl.group(1)) == 32000 / led_p / 2 and bool(pw) and lv == 16
         and int(pw.group(1)) == 32000 / led_p / lv,
         f"README: yellow alternates {yl.group(1) if yl else None} times a second, output LED PWM {pw.group(1) if pw else None} "
         f"Hz; refreshes at {32000 / led_p:.0f} Hz, alternating per refresh -> {32000 / led_p / 2:.0f}/s, {lv} levels -> "
         f"{32000 / led_p / lv:.0f} Hz")
rd = re.search(r"four DAC frames every sample \(about ([\d.]+) µs\)", README)
hd = re.search(r"four DAC frames take\s*//\s*about (\d+) us per sample", HAL)
ck.check("G.dac_frame_time_claims", bool(rd) and bool(hd) and abs(float(rd.group(1)) * 1e-6 - t_dac) < 1.5e-6
         and abs(float(hd.group(1)) * 1e-6 - t_dac) < 1.5e-6,
         f"README 'about {rd.group(1) if rd else None} us', hal_daisy.cc 'about {hd.group(1) if hd else None} us'; the four "
         f"frames take at least {t_dac * 1e6:.2f} us (bits {4 * frame * 1e6:.2f} us + the waits, polling not counted)")
dneed = re.search(r"\(four DAC words every (\d+) µs need it\)", DESIGN)
ck.check("G.design_md_dac_words_fit", bool(dneed) and t_dac < float(dneed.group(1)) * 1e-6 and abs(float(dneed.group(1)) * 1e-6 - T_SAMPLE) < 1e-6,
         f"design.md 'four DAC words every {dneed.group(1) if dneed else None} us': the sample period is {T_SAMPLE * 1e6:.2f} us, "
         f"the four frames take {t_dac * 1e6:.2f} us at 6.25 MHz ({2 * 4 * frame * 1e6:.1f} us of bits at the next slower "
         f"prescaler)")

ck.done()
