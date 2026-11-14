"""firmware: the firmware's hardware tables and assumptions against the routed board, libDaisy and the datasheets.

The firmware's own host test (firmware/test, board_tables.h from gen_board_tables.py) compares the
firmware tables with circuit.py. This group goes further: it reads the C++ sources as text (nothing
is built) and follows each pin and table entry through libDaisy v9.0.0, the Daisy Seed datasheet and
the STM32H750 datasheet to the copper of the routed master (Plaits-routed.epro2: pad nets plus
copper_audit's connectivity, so "reaches" means joined by tracks, vias and pours, across the
header pairs by pad number), and checks the timing and scaling the firmware assumes against the
datasheets. Values of the routed parts come from the routed export's device attributes, not from
circuit.py; circuit.py only names the panel label of a jack or pot.

  A. pins: every hal_daisy.cc pin constant -> libDaisy's GPIO -> the Seed's physical pin (datasheet)
     -> circuit.SEED -> the routed U2 pad -> the copper to what it drives (ADC stage Rs, mux COM and
     S0..S2, 595 SER / SRCLK / RCLK, button contacts, button LED through R60 / R61, the probe
     resistors and the jack lugs they reach); the 595 chain order and every LED bit against
     leds.cc's kRedBit / kGreenBit (U9/U10 pin -> 470R -> LED pad -> the LED symbol's anode name);
     every 74HC4051 channel input pad against pots_adc.cc's kMuxChannel; the LED and button order
     on the board against the firmware's.
  B. ADC: each ADC GPIO's ADC1 channel (DS12556 pin table) against libDaisy's channel map; ADC1;
     the mux address bit order (libDaisy write_mux_value) against S0/S1/S2 on the routed FB; the
     ADC kernel clock, sample time and OVS_8 -> the scan time against the firmware's "near 0.2 ms",
     README's "about every 0.2 ms" and the probe's 1 ms; the source impedance each channel's
     sampling time allows (DS12556 Table 183).
  C. SPI to the 74HC595s: AF5 SPI1 on PG11 / PB5 (datasheet AF table, libDaisy's pin map); the SPI
     kernel clock (PLL2P) and PS_16 -> the SCK rate against hal_daisy.cc's "1.6 MHz, 10 us" and
     design.md's "1.56 MHz (PLL2P 25 MHz / 16)"; SCK against the 595's fmax, tw, tsu, th and the
     U9 QH' -> U10 SER hop at 3.3 V; mode 0; MSB first; byte order; the RCLK pulse from
     DelayTicks(100) (TIM2 at 2 x PCLK1); RCLK idle low; what the 595 inputs do before the first
     frame (bootloader time) and while the bootloader waits.
  D. buttons and button LEDs: pull-ups (RPU), contacts to ground, active low, settle time before
     main.cc reads the left button; GPIO current of D2 / D3 and the probe against DS12556's limits.
  E. CV conversion (cv_adc.cc): the Plaitsy stage constants against the routed stages (Rin, Rf,
     bias divider found by following nets); the Plaits stage constants against Plaits' own
     schematic (plaits_v50.sch, decoded) and Plaits' settings.cc / ui.cc; end to end, a jack voltage
     through Plaitsy (nominal parts) and the firmware against what Plaits' own front end reads.
  F. thresholds as jack voltages: the probe's swing on Plaitsy (nominal and with 1 % parts and
     3V3A / 3V3D tolerance) against the normalization thresholds; probe_low_offset; the TRIG
     threshold; MODEL's "about 0.21 V per model"; the V/OCT reach against Plaits'; the README's
     loose-cable, calibration-window and uncalibrated-error figures.
  G. flash, bootloader, watchdog: program size, QSPI offsets, the IWDG timeout from LSI min / max.

Run:  cd plaits/hardware/tests && python test_firmware.py
"""
import itertools
import math
import os
import re

import harness

ck = harness.Checks("firmware")
circuit = harness.load("circuit")

# ================================================================== constants (sources, conditions)
# --- libDaisy v9.0.0 (github.com/electro-smith/libDaisy, tag v9.0.0), read 2026-11-12 ------------
# src/daisy_seed.h, namespace seed: pin name -> GPIO
LIBDAISY_SEED = {
    "D0": "PB12", "D1": "PC11", "D2": "PC10", "D3": "PC9", "D4": "PC8", "D5": "PD2", "D6": "PC12", "D7": "PG10",
    "D8": "PG11", "D9": "PB4", "D10": "PB5", "D11": "PB8", "D12": "PB9", "D13": "PB6", "D14": "PB7", "D15": "PC0",
    "D16": "PA3", "D17": "PB1", "D18": "PA7", "D19": "PA6", "D20": "PC1", "D21": "PC4", "D22": "PA5", "D23": "PA4",
    "D24": "PA1", "D25": "PA0", "D26": "PD11", "D27": "PG9", "D28": "PA2", "D29": "PB14", "D30": "PB15"}
LIBDAISY_ALIAS = {f"A{k}": f"D{15 + k}" for k in range(11)}
LIBDAISY_ALIAS["A11"] = "D28"
# src/per/adc.cpp: PIN_CHN_x constants (ADC channel -> GPIO), hadc1.Instance = ADC1
LIBDAISY_ADC_CHANNEL = {3: "PA6", 4: "PC4", 5: "PB1", 7: "PA7", 8: "PC5", 9: "PB0", 10: "PC0", 11: "PC1", 12: "PC2",
                        13: "PC3", 14: "PA2", 15: "PA3", 16: "PA0", 17: "PA1", 18: "PA4", 19: "PA5"}
LIBDAISY_ADC_INSTANCE = "ADC1"
LIBDAISY_ADC_MAX_CHANNELS = 16                 # DSY_ADC_MAX_CHANNELS
LIBDAISY_ADC_MAX_MUX = 8                       # DSY_ADC_MAX_MUX_CHANNELS
LIBDAISY_MUX_PINS = lambda n: 3 if n > 4 else 2 if n > 2 else 1 if n > 1 else 0   # get_num_mux_pins_required
LIBDAISY_MUX_BIT = {0: 0x01, 1: 0x02, 2: 0x04}  # write_mux_value: mux_pin_[k] gets (idx & bit)
LIBDAISY_ADC_DEFAULT_SMP = 8.5                 # adc.h: InitSingle / InitMux speed = SPEED_8CYCLES_5 by default
LIBDAISY_ADC_PRESCALER = 2                     # adc.cpp: ClockPrescaler = ADC_CLOCK_ASYNC_DIV2
LIBDAISY_OVS = {"OVS_4": 4, "OVS_8": 8, "OVS_16": 16, "OVS_32": 32}   # adc.cpp: Ratio per OverSampling
# src/sys/system.cpp ConfigureClocks(): HSE 16 MHz (src/sys/stm32h7xx_hal_conf.h HSE_VALUE)
HSE = 16e6
PLL1 = dict(M=4, N={"480": 240, "400": 200}, P=2)          # SYSCLK; HCLK = SYSCLK / 2, PCLK1 = HCLK / 2
PLL2 = dict(M=1, N=12, FRACN=4096, P=8, Q=2, R=1)          # Spi123ClockSelection = RCC_SPI123CLKSOURCE_PLL2 (pll2_p)
PLL3 = dict(M=6, N=295, FRACN=0, P=16, Q=4, R=32)          # AdcClockSelection = RCC_ADCCLKSOURCE_PLL3 (pll3_r)
AHB_DIV, APB1_DIV = 2, 2
# src/per/tim.cpp: TIM2 prescaler 0, GetFreq() = PCLK1 * 2 / (PSC + 1); DelayTick() busy-waits on TIM2->CNT
# src/per/spi.cpp: FirstBit = SPI_FIRSTBIT_MSB (fixed), MasterKeepIOState = ENABLE, pins: SPI1 SCLK {PG11, PA5},
#   MOSI {PB5, PA7}, all AF5; MISO only initialised for TWO_LINES / RX directions; BlockingTransmit = HAL_SPI_Transmit
LIBDAISY_SPI1_SCLK = {"PG11": 5, "PA5": 5}
LIBDAISY_SPI1_MOSI = {"PB5": 5, "PA7": 5}
LIBDAISY_SPI_FIRSTBIT = "MSB"
# Rev V of the STM32H750 divides the ADC kernel clock by 2 once more (ST's HAL ADC_ConfigureBoostMode: "freq /= 2
# for Rev.V"; recorded in the Plaitsy porting notes, reference-libdaisy-port-facts). NOT re-read in RM0433 here:
# the scan time is checked for rev V (all Seeds since 2020) and the probe margin also without the /2.
# VERIFY 2026-11-13: the HAL line read at the commit libDaisy v9.0.0 pins (stm32h7xx_hal_driver 404a70d):
# ADC_ConfigureBoostMode() "else /* STM32H7 silicon Rev.V */ { freq /= 2U; /* divider by 2 for Rev.V */"; and
# the firmware runs at 480 MHz (main.cc hw.Init(true)), which DS12556 Table 1 note 3 allows on revision V only.
ADC_REV_V_DIV = 2

# --- Daisy Seed datasheet v1.0.5 (Electrosmith, 2021), "Pinout" figure + Table 2 "Pin Functions" ----------
SEED_DS = {1: ("D0", "PB12"), 2: ("D1", "PC11"), 3: ("D2", "PC10"), 4: ("D3", "PC9"), 5: ("D4", "PC8"),
           6: ("D5", "PD2"), 7: ("D6", "PC12"), 8: ("D7", "PG10"), 9: ("D8", "PG11"), 10: ("D9", "PB4"),
           11: ("D10", "PB5"), 12: ("D11", "PB8"), 13: ("D12", "PB9"), 14: ("D13", "PB6"), 15: ("D14", "PB7"),
           22: ("D15", "PC0"), 23: ("D16", "PA3"), 24: ("D17", "PB1"), 25: ("D18", "PA7"), 26: ("D19", "PA6"),
           27: ("D20", "PC1"), 28: ("D21", "PC4"), 29: ("D22", "PA5"), 30: ("D23", "PA4"), 31: ("D24", "PA1"),
           32: ("D25", "PA0"), 33: ("D26", "PD11"), 34: ("D27", "PG9"), 35: ("D28", "PA2"), 36: ("D29", "PB14"),
           37: ("D30", "PB15")}
SEED_DS_POWER = {20: "AGND", 21: "3V3A", 38: "3V3D", 39: "VIN", 40: "DGND"}
SEED_DS_SPI1 = {9: "SPI1 SCK", 11: "SPI1 MOSI"}     # the pinout figure's peripheral column
SEED_TT_PINS = {24, 25, 28, 29, 30}                  # Table 1: 3.3 V tolerant only (all other GPIO 5 V tolerant)
SEED_ROW_SPACING = 15.24                             # landing pattern: rows 15.24 mm apart, 2.54 mm pitch, 48.26 long
# libDaisy v9.0.0 src/daisy_seed.cpp: pins the Seed itself uses (SAI1 to the codec, QSPI, codec I2C, LED, test point)
LIBDAISY_SEED_INTERNAL = {"PE2", "PE3", "PE4", "PE5", "PE6", "PF6", "PF7", "PF8", "PF9", "PF10", "PG6", "PH4", "PB11",
                          "PC7", "PG14"}

# --- STM32H750 datasheet DS12556 Rev 7 (rev V electrical characteristics) --------------------------------
# Table 7 pin definitions, "additional functions": the ADC input of each pin (ADCx_INPn: ADC1 is among x)
STM32_ADC_INP = {"PC0": ("ADC123", 10), "PA3": ("ADC12", 15), "PB1": ("ADC12", 5), "PA7": ("ADC12", 7),
                 "PA6": ("ADC12", 3), "PC1": ("ADC123", 11), "PC4": ("ADC12", 4), "PA1": ("ADC1", 17),
                 "PA0": ("ADC1", 16)}
STM32_FAST_CH = {"PA6", "PC4", "PB1"}           # Table 183 note 4 (fast channels); PA0/PA1 here are not PA0_C/PA1_C
STM32_AF5 = {"PG11": "SPI1_SCK/I2S1_CK", "PB5": "SPI1_MOSI/I2S1_SDO"}   # Tables 9 (port B) / 14 (port G), AF5
STM32_RPU = (30e3, 40e3, 50e3)                  # Table 155: weak pull-up, VIN = VSS: min / typ / max
STM32_VIL_MAX, STM32_VIH_MIN = 0.3, 0.7         # Figure 71, CMOS requirement, x VDD (all I/Os except BOOT0)
STM32_VOH_DROP_8MA = 0.4                        # Table 156: VOH >= VDD - 0.4 V at IIO = -8 mA, CMOS port, 2.7..3.6 V
STM32_IIO_8MA = 8e-3
STM32_IIO_ABS, STM32_IIO_SUM_ABS = 20e-3, 140e-3   # Table 118: per I/O (sunk), sum of all I/Os sourced / sunk, max
STM32_GPIO_FMAX_LOW = 12e6                      # Table 158: speed 00 (libDaisy's LOW), C = 50 pF, VDD 2.7..3.6 V, max
STM32_GPIO_TRF_LOW = 16.6e-9                    # Table 158: speed 00, tr / tf, C = 50 pF, VDD 2.7..3.6 V, max
STM32_ADC_TCONV_EXTRA = 0.5 + 16 / 2            # Table 182: tCONV = tS + 0.5 + N/2 cycles (N = 16 bits)
STM32_ADC_FMAX = 50e6                           # Table 182: fADC max (BOOST = 11)
STM32_ADC_SMP = (1.5, 2.5, 8.5, 16.5, 32.5, 64.5, 387.5, 810.5)   # SMP settings (tS 1.5 .. 810.5 cycles)
# Table 183: minimum sampling time vs RAIN, slow channels (TJ <= 125 C, 47 pF PCB capacitor, VDDA = 1.6 V)
STM32_T183_SLOW = {12: {47: 1.29e-7, 68: 1.32e-7, 100: 1.40e-7, 150: 1.51e-7, 220: 1.73e-7, 330: 2.14e-7,
                        470: 2.68e-7, 680: 3.54e-7},
                   10: {47: 1.08e-7, 68: 1.11e-7, 100: 1.16e-7, 150: 1.26e-7, 220: 1.40e-7, 330: 1.71e-7,
                        470: 2.13e-7, 680: 2.80e-7, 1000: 3.84e-7, 1500: 5.48e-7, 2200: 7.78e-7, 3300: 1.14e-6},
                   16: {47: 1.72e-7}}
STM32_T183_TOL_LSB = {16: 10, 14: 4, 12: 2, 10: 2}   # Table 182 note 6: the tolerance behind the RAIN figures
STM32_LSI_25C = (31.4e3, 32.0e3, 32.6e3)        # LSI oscillator, VDD 3.3 V, TJ 25 C: min / typ / max
STM32_LSI_FULL = (29.4e3, 33.6e3)               # LSI, TJ -40..125 C, VDD 1.62..3.6 V: min / max
IWDG_RLR_MAX = 0xFFF                            # IWDG reload is 12 bits (RM0433; not re-read here)

# --- TI SN74HC595, SCLS041J (Oct 2021), 6.6 Timing Requirements, SN74HC595 column (TA -40..85 C) ----------
# {VCC: value}; 3.3 V lies between 2 V and 4.5 V: the 2 V figure is the bound used for "must work".
HC595_FCLK_MAX = {2.0: 5e6, 4.5: 25e6, 6.0: 29e6}
HC595_TW_MIN = {2.0: 100e-9, 4.5: 20e-9, 6.0: 17e-9}       # SRCLK or RCLK high or low
HC595_TW_MIN_25C = {2.0: 80e-9, 4.5: 16e-9}                # TA 25 C column
HC595_TSU_SER = {2.0: 125e-9, 4.5: 25e-9, 6.0: 21e-9}      # SER before SRCLK rising
HC595_TSU_SRCLK_RCLK = {2.0: 94e-9, 4.5: 19e-9, 6.0: 16e-9}  # SRCLK rising before RCLK rising
HC595_TH_SER = {2.0: 0.0, 4.5: 0.0, 6.0: 0.0}              # SER after SRCLK rising
HC595_TPD_QH_MAX = {2.0: 200e-9}                           # 6.7: SRCLK -> QH', CL 50 pF, SN74HC595 max
HC595_TPD_QH_MIN = 0.0                                     # no minimum given: taken as 0 (worst case for hold)
# Table 5-1 pin functions (16-pin packages)
HC595_PIN = {"QA": "15", "QB": "1", "QC": "2", "QD": "3", "QE": "4", "QF": "5", "QG": "6", "QH": "7", "QH'": "9",
             "SER": "14", "SRCLK": "11", "RCLK": "12", "SRCLR": "10", "OE": "13", "VCC": "16", "GND": "8"}
HC595_Q = ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH"]
# 6.3 Recommended Operating Conditions (SN74HC595); CD74HC4051 SCHS122O gives the same HC input levels
HC_VIH_MIN = {2.0: 1.5, 4.5: 3.15, 6.0: 4.2}
HC_VIL_MAX = {2.0: 0.5, 4.5: 1.35, 6.0: 1.8}
HC_INPUT_TT_MAX = {2.0: 1000e-9, 4.5: 500e-9, 6.0: 400e-9}   # input transition rise / fall time, max

# --- TI CD74HC4051, SCHS122O (Jan 2026): Table 4-1 pin functions, Table 7-1 function table ----------------
HC4051_Y = {0: "13", 1: "14", 2: "15", 3: "12", 4: "1", 5: "5", 6: "2", 7: "4"}
HC4051_PIN = {"COM": "3", "E": "6", "VEE": "7", "GND": "8", "S2": "9", "S1": "10", "S0": "11", "VCC": "16"}
HC4051_SEL_WEIGHT = {"S0": 1, "S1": 2, "S2": 4}            # channel = 4*S2 + 2*S1 + S0 (Table 7-1)
# VERIFY 2026-11-13: was 200, which is SCHS122O's VCC 6 V, -40..85 C figure; at VCC 4.5 V the table gives 90 typ /
# 180 max (25 C) / 225 max (-40..85 C)
HC4051_RON_45V_MAX = 225.0     # rON, VCC 4.5 V, VEE 0, IO 1 mA, -40..85 C, max. At 3.3 V it is not given:
HC4051_RON_33V = 2 * HC4051_RON_45V_MAX   # ASSUMED twice the 4.5 V max (rON rises as VCC falls), not confirmed

# --- TI TL074 (SLOS080): pinout, section (out, in-, in+) ---------------------------------------------------
TL074_SECTION = {"1": ("2", "3"), "7": ("6", "5"), "8": ("9", "10"), "14": ("13", "12")}

# --- repo part knowledge (.claude/skills/module-design/references/parts.md, from the makers' drawings) ----
JACK_TIP, JACK_LUG, JACK_SLEEVE = "3", "2", "1"     # Thonkiconn WQP518MA: tip, switch (normalling) lug, sleeve
BUTTON_CONTACTS = (("1", "2"), ("3", "4"))           # Thonk low-profile LED button: contacts 1+2 and 3+4
BUTTON_LED_A, BUTTON_LED_K = "5", "6"
POT_CCW, POT_WIPER, POT_CW = "1", "2", "3"           # Alpha 9 mm: pin 3 = clockwise end (front view, pins down)

# --- Mutable Instruments Plaits (github.com/pichenettes/eurorack, master, read 2026-11-12) -----------------
# plaits/hardware_design/pcb/plaits_v50.sch (binary Eagle 5 file: part records + sheet 3 "CV inputs" nets
# decoded): each CV input is jack tip -> Rin 100k -> MCP6004 (-) with Rf and an offset resistor Rref from the
# AREF_-10 net (-10 V); (+) at GND; MCP6004 on +3V3_A. Channel by the jack (J1..J8) and its input net
# (MODEL_IN, FM_IN, MORPH_IN, V_OCT_IN, ADC_TRIG, ADC_GATE = LEVEL), TIMBRE = the other probed 20k/120k
# stage (J2), HARMONICS = the other grounded 33k/200k stage (J5).
PLAITS_STAGE = {   # channel: (jack, Rin, Rf, Rref, Cf, lug)
    "MODEL": ("J1 R40/R31/R30", 100e3, 33e3, 200e3, 100e-12, "GND"),
    "TIMBRE": ("J2 R41/R32/R33", 100e3, 20e3, 120e3, 1e-9, "probe R48"),
    "FM": ("J3 R15/R19/R23", 100e3, 20e3, 120e3, 1e-9, "probe R49"),
    "MORPH": ("J4 R39/R35/R36", 100e3, 20e3, 120e3, 1e-9, "probe R45"),
    "HARMONICS": ("J5 R13/R20/R27", 100e3, 33e3, 200e3, 1e-9, "GND"),
    "TRIGGER": ("J6 R24/R17/R25", 100e3, 56e3, 200e3, 100e-12, "probe R50"),
    "LEVEL": ("J7 R14/R18/R26", 100e3, 33e3, 110e3, 1e-9, "probe R51"),
    "V_OCT": ("J8 R38/R34/R29", 100e3, 33e3, 140e3, 1e-9, "GND"),
}
PLAITS_REF = 10.0          # |AREF_-10|, V
PLAITS_VREF = 3.3          # SDADC range 0..VREF (SE zero-reference mode, gain 1): VREFSD+ taken as +3V3_A, 3.3 V
PLAITS_PROBE_R = 10e3      # R45, R48..R51 between the probe net and the switch lugs
PLAITS_PROBE_HIGH = 3.3    # the probe pin (PA9, push-pull) high level
# plaits/ui.cc CalibrateC3 comment: "(-33/100.0*1 + -33/140.0 * -10.0) / 3.3 * 2.0 - 1 = 0.228" (V/OCT stage at 1 V)
PLAITS_UI_VOCT_1V = 0.228
# plaits/settings.cc Settings::Init() (Plaits 1.2): (offset, scale, normalization_detection_threshold)
PLAITS_DEFAULTS = {"MODEL": (0.025, -1.03, 0), "V_OCT": (25.71, -60.0, 0), "FM": (0.0, -60.0, -2945),
                   "HARMONICS": (0.0, -1.0, 0), "TIMBRE": (0.0, -1.6, -2945), "MORPH": (0.0, -1.6, -2945),
                   "TRIGGER": (0.4, -0.6, 13663), "LEVEL": (0.49, -0.6, 21403)}
PLAITS_NORMALIZED = ["FM", "TIMBRE", "MORPH", "TRIGGER", "LEVEL"]   # ui.cc normalized_channels_
PLAITS_PROBE_SEQ, PLAITS_PROBE_MISMATCH = 32, 2                     # ui.h kProbeSequenceDuration, ui.cc ">= 2"
PLAITS_CAL_WINDOW = (-0.6, -0.2)                                    # ui.cc CalibrateC3: delta accepted
# plaits/dsp/voice.cc (vendored): trigger on at > 0.3, off at < 0.1; engine_quantizer_.Init(24, 0.05, true)
PLAITS_TRIG_ON, PLAITS_TRIG_OFF = 0.3, 0.1
PLAITS_ENGINES, PLAITS_ENGINE_HYST = 24, 0.05
# plaits/plaits.cc: IWDG prescaler 16, reload left at its reset value 0xFFF; STM32F373 LSI 40 kHz typ
PLAITS_WDG_S = 0xFFF / (40e3 / 16)

# --- Daisy bootloader (libDaisy v9 docs / the porting notes): program in SRAM up to 480 kB, QSPI 0x0..0x3FFFF free
BOOT_SRAM_LIMIT = 480 * 1024
BOOT_QSPI_FREE = (0x0, 0x40000)
BOOT_GRACE_S = 2.0          # README: "about two seconds after power-on (the bootloader runs first)"

# --- assumptions (not datasheet numbers) ----------------------------------------------------------------
RES_TOL = 0.01              # every resistor 1 % (the routed device attributes say "±1%")
# VERIFY 2026-11-13: was RAIL_TOL = 0.03 for both rails (assumed). The Seed (schematic rev 5, sheet 1) makes 3V3A
# with an LP2985 and 3V3D with a TPS6217x and 47k / 15k:
#   LP2985, TI SLVS522S (May 2025) 5.5, legacy standard grade (grade not known), 1 mA <= IL <= 50 mA:
#   +-2.5 % at 25 C, +-3.5 % at TJ -40..125 C (the new chip: +-0.5 / +-1 %)
#   TPS6217x, TI SLVSAT8E (May 2017): output accuracy -3 / +3 % in PWM mode (divider not included), plus
#   47k / 15k at 1 % (assumed) +-1.5 % -> +-4.5 % (power-save mode -3.5 / +4 %: -5 / +5.5 % with the divider)
RAIL_TOL_A = 0.035          # 3V3A, max, over temperature
RAIL_TOL_A_25C = 0.025      # 3V3A, max, 25 C (the README's uncalibrated figures)
RAIL_TOL_D = 0.045          # 3V3D, max, PWM mode
BTN_LINE_C = 50e-12         # button line incl. header and switch: ASSUMED
BTN_LED_VF = (1.6, 3.2)     # LED inside a Thonk button, any colour, 1..4 mA: ASSUMED range
JACK_NODE_C = 30e-12        # jack lug / tip node incl. tracks and header: ASSUMED
AUDIO_FS, POLL_DIV = 48014.32, 4    # libDaisy "48 kHz" (dsp.h kCorrectedSampleRate); UI tasks every 4th poll


# ================================================================== helpers
def src(*p):
    return harness.text("firmware", "src", *p)


HAL = src("hal_daisy.cc")
HAL_H = src("hal.h")
CV = src("plaits", "drivers", "cv_adc.cc")
LEDS = src("plaits", "drivers", "leds.cc")
POTS = src("plaits", "drivers", "pots_adc.cc")
SETTINGS = src("plaits", "settings.cc")
UI = src("plaits", "ui.cc")
UI_H = src("plaits", "ui.h")
MAIN = src("main.cc")
USER_DATA = src("plaits", "user_data.cc")
USER_DATA_H = src("plaits", "user_data.h")
DSP_H = src("plaits", "dsp", "dsp.h")
CV_H = src("plaits", "drivers", "cv_adc.h")
POTS_H = src("plaits", "drivers", "pots_adc.h")
README = " ".join(harness.text("firmware", "README.md").split())      # whitespace-flattened for phrase checks
DESIGN = " ".join(harness.text("docs", "design.md").split())


def strip_comments(t):
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", t, flags=re.S))


def cnum(expr, names=None):
    """A C++ arithmetic expression ('kVdd * 12.0f / (15.0f + 12.0f)') with the named constants filled in."""
    e = expr
    for k, v in sorted((names or {}).items(), key=lambda kv: -len(kv[0])):
        e = re.sub(rf"\b{k}\b", f"({v!r})", e)
    e = re.sub(r"(\d+\.?\d*(?:[eE][-+]?\d+)?)[fF]\b", r"\1", e)
    e = re.sub(r"\b0x([0-9a-fA-F]+)\b", lambda m: str(int(m.group(1), 16)), e)
    if not re.fullmatch(r"[\d\s.+\-*/()eE]+", e):
        raise ValueError(f"not plain arithmetic: {expr!r} -> {e!r}")
    return eval(e, {"__builtins__": {}}, {})


def c_enum(text, name):
    body = re.search(rf"enum\s+{name}\s*{{(.*?)}}", strip_comments(text), re.S).group(1)
    return [x.strip().split("=")[0].strip() for x in body.split(",") if x.strip()]


def c_array(text, name):
    m = re.search(rf"{name}\s*\[[^\]]*\]\s*=\s*{{(.*?)}};", strip_comments(text), re.S)
    return [x.strip() for x in m.group(1).split(",") if x.strip()] if m else None


def seed_gpio(name):
    name = LIBDAISY_ALIAS.get(name, name)
    return LIBDAISY_SEED.get(name)


def seed_pin_of_gpio(gpio):
    return next((p for p, (n, g) in SEED_DS.items() if g == gpio), None)


def seed_name_of_pin(pin):
    return SEED_DS[pin][0]


def interp_vcc(table, vcc=3.3):
    """Linear interpolation between the 2 V and 4.5 V columns (for typical-style comparisons only)."""
    return table[2.0] + (table[4.5] - table[2.0]) * (vcc - 2.0) / 2.5


def parse_value(v):
    """'100kΩ' -> 1e5, '1nF' -> 1e-9, '470Ω' -> 470, '1µF' -> 1e-6, '10kΩ' -> 1e4."""
    if not v:
        return None
    v = v.replace("Ω", "").replace("µ", "u").replace("μ", "u").replace(" ", "")
    m = re.fullmatch(r"([\d.]+)([pnumkM]?)(F|R)?", v)
    if not m:
        return None
    mul = {"": 1, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "M": 1e6}[m.group(2)]
    return float(m.group(1)) * mul


R = harness.routed()
_copper = {}


def copper(board):
    """{(ref, pad): (net, frozenset of (ref, pad) joined to it by copper)} from copper_audit's connectivity."""
    if board not in _copper:
        groups, contacts = R.board(board).connectivity()
        m = {}
        for net, roots in groups.items():
            for keys in roots.values():
                pads = frozenset((k[1], k[2]) for k in keys if k[0] == "pad")
                for p in pads:
                    m[p] = (net, pads)
        _copper[board] = (m, contacts)
    return _copper[board][0]


def reach(board, ref, pad):
    """(net, set of (ref, pad)) the pad's copper reaches on its board; (None, {itself}) for an unconnected pad."""
    return copper(board).get((ref, str(pad)), (None, frozenset({(ref, str(pad))})))


HEADER_PAIR = {"H1": "HF1", "H2": "HF2", "H3": "HF3"}
HEADER_PAIR_R = {v: k for k, v in HEADER_PAIR.items()}


def reach_both(board, ref, pad, seen=None):
    """Follow copper on one board, then across every header pin it touches to the same pin of the mating
    header on the other board, and on. Returns {(board, ref, pad)} and the nets passed."""
    seen = set() if seen is None else seen
    nets = set()
    todo = [(board, ref, str(pad))]
    while todo:
        b, r_, p = todo.pop()
        if (b, r_, p) in seen:
            continue
        net, pads = reach(b, r_, p)
        if net:
            nets.add((b, net))
        for (rr, pp) in pads:
            seen.add((b, rr, pp))
            other = HEADER_PAIR.get(rr) if b == "main" else HEADER_PAIR_R.get(rr)
            if other:
                ob = "face" if b == "main" else "main"
                if (ob, other, pp) not in seen and other in R.board(ob).parts:
                    todo.append((ob, other, pp))
        seen.add((b, r_, p))
    return seen, nets


def val(board, ref):
    return parse_value(R.device(board, ref).get("Value"))


def other_pad(board, ref, pad):
    pads = [n for n in R.board(board).parts[ref]["pads"] if n != str(pad)]
    return pads[0] if len(pads) == 1 else None


def two_pin(board, ref):
    return len(R.board(board).parts[ref]["pads"]) == 2


def on(board, pads, prefix, exclude=()):
    return sorted({(r_, p) for (r_, p) in pads if r_.startswith(prefix) and r_ not in exclude})


# ---- firmware facts parsed from the sources
pin_consts = dict(re.findall(r"constexpr\s+Pin\s+(k\w+)\s*=\s*seed::(\w+)\s*;", HAL))
adc_pins = [x.replace("seed::", "") for x in c_array(HAL, "kAdcPins")]
btn_pins = [x.replace("seed::", "") for x in c_array(HAL, "kButtonPins")]
adc_enum = c_enum(HAL_H, "AdcInput")
btn_enum = c_enum(HAL_H, "Button")
num_mux = int(re.search(r"kNumMuxChannels\s*=\s*(\d+)", HAL_H).group(1))
ck.check("A.parse.hal_pins", all(k in pin_consts for k in ("kMuxOut", "kMuxS0", "kMuxS1", "kMuxS2", "kButtonLedA",
                                                             "kButtonLedB", "kSpiSck", "kSpiMosi", "kLedLatch",
                                                             "kProbe"))
         and len(adc_pins) == 8 and len(btn_pins) == 2, f"pins {pin_consts}, adc {adc_pins}, buttons {btn_pins}")

# ================================================================== A. pins: firmware -> libDaisy -> Seed pin -> copper
U2 = R.main.parts["U2"]
roles = {f"ADC[{adc_enum[i]}]": n for i, n in enumerate(adc_pins)}
roles.update({k: v for k, v in pin_consts.items()})
roles.update({f"Button[{btn_enum[i]}]": n for i, n in enumerate(btn_pins)})
role_pin = {}
for role, name in sorted(roles.items()):
    gpio = seed_gpio(name)
    pin = seed_pin_of_gpio(gpio) if gpio else None
    dsname = SEED_DS[pin][0] if pin else None
    ok = gpio is not None and pin is not None and LIBDAISY_ALIAS.get(name, name) == dsname
    ck.check(f"A.libdaisy_vs_seed_datasheet.{role}", ok,
             f"seed::{name} -> {gpio} (libDaisy) -> Seed pin {pin} '{dsname}' (datasheet v1.0.5)")
    role_pin[role] = pin
    if pin is None:
        continue
    cname, cnet = circuit.SEED.get(str(pin), (None, None))
    ck.check(f"A.circuit_seed_name.{role}", cname is not None and (LIBDAISY_ALIAS.get(name, name) in cname.split("/")
                                                                    or name in cname.split("/")),
             f"Seed pin {pin}: circuit.SEED says {cname!r} ({cnet}), firmware uses seed::{name}")
    rnet = U2["pads"][str(pin)].net
    ck.check(f"A.routed_pad_net.{role}", rnet is not None and rnet == cnet,
             f"routed U2 pad {pin} net {rnet!r}, circuit.SEED {cnet!r}")

pin_of = lambda role: role_pin.get(role)
used = [seed_gpio(n) for n in roles.values()]
ck.check("A.pins_distinct", len(set(used)) == len(used), f"{len(used)} roles on {len(set(used))} GPIOs")
ck.check("A.pins_not_seed_internal", not set(used) & LIBDAISY_SEED_INTERNAL,
         f"the Seed's own SAI1 / QSPI / codec I2C / LED / test point pins (daisy_seed.cpp) are not among {sorted(used)}")
ck.check("A.no_tt_pin_overdriven", all(seed_pin_of_gpio(g) not in SEED_TT_PINS or role.startswith("ADC")
                                       for role, g in zip(roles, used)),
         "the 3.3 V-tolerant-only pins (Seed 24, 25, 28, 29, 30) carry only ADC inputs (stage outputs 0.10..3.22 V "
         "for +-12 V)")
# the Seed footprint on the routed MB: the Seed's 2 x 20 landing pattern, pin k opposite 41 - k
pads = {int(n): (p.x, p.y) for n, p in U2["pads"].items() if n.isdigit()}
row1 = [pads[k] for k in range(1, 21)]
row2 = [pads[41 - k] for k in range(1, 21)]
pitch_ok = all(abs(math.dist(row1[i], row1[i + 1]) - 2.54) < 0.02 and abs(math.dist(row2[i], row2[i + 1]) - 2.54) < 0.02
               for i in range(19))
across_ok = all(abs(math.dist(row1[i], row2[i]) - SEED_ROW_SPACING) < 0.02 for i in range(20))
ck.check("A.seed_landing_pattern", pitch_ok and across_ok and abs(math.dist(row1[0], row1[-1]) - 19 * 2.54) < 0.05,
         f"U2 pads 1..20 and 40..21 in two rows, 2.54 mm pitch, {SEED_ROW_SPACING} mm apart, pin k opposite 41 - k "
         "(Seed datasheet landing pattern 15.24 / 2.54 / 48.26 mm)")
ck.check("A.seed_pin1_at_usb_end", pads[1][1] > pads[20][1] and pads[40][1] > pads[21][1] and pads[1][0] < pads[40][0],
         f"pin 1 {tuple(round(c, 2) for c in pads[1])}, 20 {tuple(round(c, 2) for c in pads[20])}, 40 "
         f"{tuple(round(c, 2) for c in pads[40])}: pins 1 / 36..40 (USB D-/D+, 3V3D, VIN, DGND) at the top end, where "
         "design.md puts the Seed's USB; pin 1 left seen from the rear, as the Seed's top view rotated USB-up")


def reach_from_seed(pin):
    seen, nets = reach_both("main", "U2", str(pin))
    return seen, nets


# --- the ADC inputs: Seed pin -> 1k -> TL074 output (and the stage found by following nets, section E uses it)
STAGES = {}
for i, name in enumerate(adc_enum[:8]):
    role = f"ADC[{name}]"
    pin = pin_of(role)
    net, pads = reach("main", "U2", str(pin))
    rs = [(r_, p) for (r_, p) in pads if r_.startswith("R") and two_pin("main", r_)]
    diodes = on("main", pads, "D")
    st = {"pin": pin, "adc_net": net, "diodes": diodes}
    ok = len(rs) == 1
    if ok:
        rsr, rsp = rs[0]
        st["Rs"] = (rsr, val("main", rsr))
        oa_net, oa_pads = reach("main", rsr, other_pad("main", rsr, rsp))
        outs = [(r_, p) for (r_, p) in oa_pads if r_ in ("U3", "U4") and p in TL074_SECTION]
        ok = len(outs) == 1
        if ok:
            u, out = outs[0]
            inm, inp = TL074_SECTION[out]
            in_net, in_pads = reach("main", u, inm)
            b_net, b_pads = reach("main", u, inp)
            rf = [r_ for (r_, p) in in_pads if r_.startswith("R") and two_pin("main", r_)
                  and reach("main", r_, other_pad("main", r_, p))[0] == oa_net]
            cf = [r_ for (r_, p) in in_pads if r_.startswith("C") and two_pin("main", r_)
                  and reach("main", r_, other_pad("main", r_, p))[0] == oa_net]
            rin = [(r_, p) for (r_, p) in in_pads if r_.startswith("R") and r_ not in rf and two_pin("main", r_)]
            bias_r = [(r_, p) for (r_, p) in b_pads if r_.startswith("R") and two_pin("main", r_)]
            st.update(u=u, out=out, oa_net=oa_net, in_net=in_net, bias_net=b_net, Rf=[(r_, val("main", r_)) for r_ in rf],
                      Cf=[(c, val("main", c)) for c in cf], Rin=[(r_, val("main", r_)) for r_, _ in rin])
            top = bot = None
            for r_, p in bias_r:
                onet = reach("main", r_, other_pad("main", r_, p))[0]
                if onet == "3V3A":
                    top = (r_, val("main", r_))
                elif onet == "GND":
                    bot = (r_, val("main", r_))
            st.update(Rtop=top, Rbot=bot)
            if len(rin) == 1:
                rr, rp = rin[0]
                seen, nets = reach_both("main", rr, other_pad("main", rr, rp))
                jacks = sorted((r_, p) for (b, r_, p) in seen if b == "face" and r_.startswith("J") and p == JACK_TIP)
                st["jack"] = jacks
    ck.check(f"A.adc_stage_found.{name}", ok and len(st.get("Rf", [])) == 1 and len(st.get("Rin", [])) == 1
             and st.get("Rtop") and st.get("Rbot") and len(st.get("jack", [])) == 1,
             f"Seed pin {pin} ({net}): Rs {st.get('Rs')}, TL074 {st.get('u')} pin {st.get('out')}, Rf {st.get('Rf')}, "
             f"Rin {st.get('Rin')}, bias {st.get('Rtop')} / {st.get('Rbot')}, jack tip {st.get('jack')}")
    STAGES[name] = st
    if st.get("Rs"):
        ck.close(f"A.adc_series_R.{name}", st["Rs"][1] or 0, 1e3, 1, "Ω")

JACK_LABEL = {ref: label for ref, label, tip, tn in circuit.JACKS}
LABEL_TO_CV = {"MODEL": "CV_ADC_CHANNEL_MODEL", "TIMBRE": "CV_ADC_CHANNEL_TIMBRE", "FM": "CV_ADC_CHANNEL_FM",
               "MORPH": "CV_ADC_CHANNEL_MORPH", "HARMO": "CV_ADC_CHANNEL_HARMONICS", "TRIG": "CV_ADC_CHANNEL_TRIGGER",
               "LEVEL": "CV_ADC_CHANNEL_LEVEL", "V/OCT": "CV_ADC_CHANNEL_V_OCT"}

# cv_adc.cc kChannels: in CvAdcChannel order, each with its hal::AdcInput
cv_enum = c_enum(CV_H, "CvAdcChannel")
kch_body = re.search(r"kChannels\[CV_ADC_CHANNEL_LAST\]\s*=\s*{(.*?)};", CV, re.S).group(1)
KCH = []
for m in re.finditer(r"{\s*hal::(\w+)\s*,\s*(true|false)\s*,\s*([\d.]+)f\s*,\s*([\d.]+)f\s*,\s*(true|false)\s*}", kch_body):
    KCH.append({"input": m.group(1), "voct": m.group(2) == "true", "rf": float(m.group(3)) * 1e3,
                "rref": float(m.group(4)) * 1e3, "normalized": m.group(5) == "true"})
ck.check("E.parse.kChannels", len(KCH) == len(cv_enum) - 1 == 8, f"{len(KCH)} entries, CvAdcChannel {cv_enum}")
CH_NAME = [c.replace("CV_ADC_CHANNEL_", "") for c in cv_enum[:8]]       # MODEL, V_OCT, FM, ...
for ci, cname_ in enumerate(CH_NAME):
    d = KCH[ci] if ci < len(KCH) else None
    if not d:
        continue
    st = STAGES.get(d["input"], {})
    jack = st.get("jack", [])
    label = JACK_LABEL.get(jack[0][0]) if jack else None
    ck.check(f"A.cv_channel_reaches_jack.{cname_}", label is not None and LABEL_TO_CV.get(label) == cv_enum[ci],
             f"kChannels[{cv_enum[ci]}] reads hal::{d['input']} = seed::{adc_pins[adc_enum.index(d['input'])]} "
             f"(Seed pin {st.get('pin')}) whose stage's Rin reaches {jack} = panel {label!r}")
    # normalized flag against the routed lug: probe resistor or ground
    if jack:
        jref = jack[0][0]
        lug_net, lug_pads = reach("face", jref, JACK_LUG)
        probed = any(r_.startswith("R") and two_pin("face", r_) for r_, _ in lug_pads if r_ != jref)
        ck.check(f"A.normalized_flag.{cname_}", probed == d["normalized"],
                 f"{jref} lug net {lug_net}: probed {probed}; kChannels normalized = {d['normalized']}")

# --- mux: COM and the address lines
mux_args = re.search(r"InitMux\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)\s*"
                     r"(?:,\s*AdcChannelConfig::SPEED_\d+CYCLES_5\s*)?\)", HAL)      # [2026-11-14: + the speed]
ck.check("A.mux.initmux_args", mux_args is not None and mux_args.groups() == ("kMuxOut", "kNumMuxChannels", "kMuxS0",
                                                                              "kMuxS1", "kMuxS2"),
         f"InitMux{mux_args.groups() if mux_args else None}: libDaisy InitMux(adc_pin, mux_channels, mux_0, mux_1, mux_2)")
seen, _ = reach_both("main", "U2", str(pin_of("kMuxOut")))
ck.check("A.mux.com", ("face", "U1", HC4051_PIN["COM"]) in seen,
         f"seed::{pin_consts['kMuxOut']} (pin {pin_of('kMuxOut')}) reaches U1 COM (pad 3): "
         f"{sorted((r_, p) for b, r_, p in seen if b == 'face')}")
MUX_BIT_OF_SEL = {}
for k, sel in enumerate(("kMuxS0", "kMuxS1", "kMuxS2")):
    seen, _ = reach_both("main", "U2", str(pin_of(sel)))
    u1 = [p for b, r_, p in seen if b == "face" and r_ == "U1"]
    selname = next((s for s, pn in HC4051_PIN.items() if pn in u1 and s.startswith("S")), None)
    MUX_BIT_OF_SEL[k] = selname
    ck.check(f"A.mux.address_line.{sel}", len(u1) == 1 and selname is not None,
             f"seed::{pin_consts[sel]} (pin {pin_of(sel)}) = libDaisy mux_pin_[{k}] reaches U1 pads {u1} ({selname})")
for nm in ("E", "VEE", "GND"):
    net = reach("face", "U1", HC4051_PIN[nm])[0]
    ck.check(f"A.mux.{nm}_low", net in ("GND_F",), f"U1 {nm} (pad {HC4051_PIN[nm]}) net {net}: must be low "
                                                   "for the channels to conduct (E active low)")
ck.check("A.mux.y7_grounded", reach("face", "U1", HC4051_Y[7])[0] == "GND_F" and num_mux == 7,
         f"U1 Y7 net {reach('face', 'U1', HC4051_Y[7])[0]}, kNumMuxChannels {num_mux} (Y7 never selected)")

# --- pots: channel -> 4051 pin (datasheet) -> wiper -> pot -> panel label -> PotsAdcChannel
pots_enum = c_enum(POTS_H, "PotsAdcChannel")
kmux = [int(x) for x in c_array(POTS, "kMuxChannel")]
POT_LABEL = {ref: label for ref, label, wiper, mpin, ch in circuit.POTS}
LABEL_TO_POT = {"FREQUENCY": "POTS_ADC_CHANNEL_FREQUENCY_POT", "HARMONICS": "POTS_ADC_CHANNEL_HARMONICS_POT",
                "TIMBRE": "POTS_ADC_CHANNEL_TIMBRE_POT", "MORPH": "POTS_ADC_CHANNEL_MORPH_POT",
                "TIMBRE att.": "POTS_ADC_CHANNEL_TIMBRE_ATTENUVERTER", "FM att.": "POTS_ADC_CHANNEL_FM_ATTENUVERTER",
                "MORPH att.": "POTS_ADC_CHANNEL_MORPH_ATTENUVERTER"}
for c in range(7):
    net, pads = reach("face", "U1", HC4051_Y[c])
    rv = [r_ for r_, p in pads if r_.startswith("RV") and p == POT_WIPER]
    label = POT_LABEL.get(rv[0]) if len(rv) == 1 else None
    want = LABEL_TO_POT.get(label)
    fw = [pots_enum[i] for i, ch in enumerate(kmux) if ch == c]
    ck.check(f"A.pot_mux_channel.Y{c}", want is not None and fw == [want],
             f"U1 Y{c} (pad {HC4051_Y[c]}, datasheet) reaches wiper of {rv} = {label!r}; pots_adc.cc reads "
             f"channel {c} as {fw}")
for ref, label, *_ in circuit.POTS:
    cw, ccw = reach_both("face", ref, POT_CW)[1], reach_both("face", ref, POT_CCW)[1]
    ck.check(f"A.pot_ends.{ref}", ("main", "3V3A") in cw and ("main", "GND") in ccw,
             f"{ref} {label}: CW end (pad 3) reaches {sorted(cw)}, CCW end reaches {sorted(ccw)}; the firmware "
             "takes clockwise = up (3V3A)")

# --- 74HC595 chain: SER, SRCLK, RCLK, the hop, SRCLR / OE
seen, _ = reach_both("main", "U2", str(pin_of("kSpiMosi")))
first = [r_ for b, r_, p in seen if b == "face" and r_ in ("U9", "U10") and p == HC595_PIN["SER"]]
ck.check("A.sr.mosi_to_first_SER", first == ["U9"], f"seed::{pin_consts['kSpiMosi']} reaches SER of {first} "
                                                    "(hal.h: bits 0..7 = U9)")
chain = list(first)
if first:
    net, pads = reach("face", first[0], HC595_PIN["QH'"])
    nxt = [r_ for r_, p in pads if r_ in ("U9", "U10") and p == HC595_PIN["SER"] and r_ != first[0]]
    ck.check("A.sr.chain_hop", len(nxt) == 1, f"{first[0]} QH' (pad 9) reaches SER of {nxt}")
    chain += nxt
    if nxt:
        lastq = reach("face", nxt[0], HC595_PIN["QH'"])
        ck.check("A.sr.chain_end_open", len(lastq[1]) <= 1, f"{nxt[0]} QH' reaches {sorted(lastq[1])}")
for sig, role in (("SRCLK", "kSpiSck"), ("RCLK", "kLedLatch")):
    seen, _ = reach_both("main", "U2", str(pin_of(role)))
    got = sorted(r_ for b, r_, p in seen if b == "face" and r_ in ("U9", "U10") and p == HC595_PIN[sig])
    ck.check(f"A.sr.{sig}", got == ["U10", "U9"], f"seed::{pin_consts[role]} (pin {pin_of(role)}) reaches {sig} of {got}")
for u in ("U9", "U10"):
    srclr = reach_both("face", u, HC595_PIN["SRCLR"])[1]
    oe = reach_both("face", u, HC595_PIN["OE"])[1]
    ck.check(f"A.sr.SRCLR_high_OE_low.{u}", ("main", "3V3D") in srclr and ("main", "GND") in oe,
             f"{u} /SRCLR reaches {sorted(srclr)}, /OE reaches {sorted(oe)}")

# --- every LED bit: chain position -> Q pin -> 470R -> LED pad -> anode colour (symbol pin name)
red_bits = [int(x) for x in c_array(LEDS, "kRedBit")]
green_bits = [int(x) for x in c_array(LEDS, "kGreenBit")]
fw_bit = {}
for i, b in enumerate(red_bits):
    fw_bit[b] = (f"D{i + 1}", "R")
for i, b in enumerate(green_bits):
    fw_bit[b] = (f"D{i + 1}", "G")
ck.check("A.led_bits.all_16_distinct", sorted(fw_bit) == list(range(16)), f"bits used {sorted(fw_bit)}")
sym_colour = {}
for k in range(1, 9):
    sym = R.device("face", f"D{k}").get("Symbol")
    pins = R.symbol_pins(sym) if sym in R.docs else {}
    sym_colour[f"D{k}"] = {num: ("R" if nm.endswith("R") else "G" if nm.endswith("G") else nm) for num, (nm, *_) in
                           pins.items()}
for n in range(16):
    if len(chain) < 2:
        break
    u, q = chain[n // 8], HC595_Q[n % 8]
    net, pads = reach("face", u, HC595_PIN[q])
    rs = [(r_, p) for r_, p in pads if r_.startswith("R") and two_pin("face", r_)]
    got = None
    if len(rs) == 1:
        rr, rp = rs[0]
        _, lp = reach("face", rr, other_pad("face", rr, rp))
        leds = [(r_, p) for r_, p in lp if re.fullmatch(r"D\d", r_)]
        if len(leds) == 1:
            got = (leds[0][0], sym_colour[leds[0][0]].get(leds[0][1]))
    ck.check(f"A.led_bit.{n}", got is not None and got == fw_bit.get(n),
             f"bit {n} = {u} {q} (pad {HC595_PIN[q]}) -> {rs} -> {got}; leds.cc: {fw_bit.get(n)}")
for k in range(1, 9):
    ck.check(f"A.led_symbol_pins.D{k}", sym_colour[f"D{k}"].get("1") == "R" and sym_colour[f"D{k}"].get("3") == "G"
             and R.face.parts[f"D{k}"]["pads"]["2"].net == "GND_D_F",
             f"D{k} symbol pins {sym_colour[f'D{k}']}, cathode pad 2 net {R.face.parts[f'D{k}']['pads']['2'].net}")
ys = [R.face.parts[f"D{k}"]["y"] for k in range(1, 9)]
ck.check("A.led_order.D1_top", all(ys[i] > ys[i + 1] for i in range(7)),
         f"LED y on the FB (y up = towards the top of the panel): {[round(y, 2) for y in ys]}; leds.cc: LED 0 = D1 "
         "at the top, Plaits' row 0 = the first model of a bank")
# the LED part: which outer lead is red is the bought part's, not the symbol's
bom = harness.text("docs", "bom.md")
led_line = next((ln for ln in bom.splitlines() if "bicolour LED" in ln), "")
ck.check("A.led_part_named", bool(re.search(r"\b(WP|L-)\w*\d|Kingbright|MPN|part number", led_line)),
         f"bom.md D1-D8 line: {led_line.strip()[:120]!r}: names no part, so nothing fixes that lead 1 is the red anode "
         "(kRedBit / kGreenBit assume pad 1 = red, pad 3 = green)")

# --- buttons and their LEDs
for i, (role_btn, sw) in enumerate((("Button[BUTTON_A]", "SW1"), ("Button[BUTTON_B]", "SW2"))):
    seen, _ = reach_both("main", "U2", str(pin_of(role_btn)))
    got = sorted(p for b, r_, p in seen if b == "face" and r_ == sw)
    ck.check(f"A.button.{sw}", got == ["3", "4"], f"{role_btn} = seed::{btn_pins[i]} (pin {pin_of(role_btn)}) reaches "
                                                   f"{sw} pads {got} (one contact = 3+4)")
    g = reach_both("face", sw, "1")[1]
    ck.check(f"A.button_other_contact_gnd.{sw}", ("main", "GND") in g and reach("face", sw, "2")[0] == reach("face", sw, "1")[0],
             f"{sw} pads 1+2 reach {sorted(g)}")
    led_role = ("kButtonLedA", "kButtonLedB")[i]
    seen, _ = reach_both("main", "U2", str(pin_of(led_role)))
    sers = sorted({r_ for b, r_, p in seen if b == "main" and r_.startswith("R")})
    got = sorted(p for b, r_, p in seen if b == "face" and r_ == sw)
    # through a series resistor: follow it
    reach_led = []
    for rr in sers:
        rp = next(p for b, r_, p in seen if b == "main" and r_ == rr)
        s2, _ = reach_both("main", rr, other_pad("main", rr, rp))
        reach_led += [(r_, p, val("main", rr)) for b, r_, p in s2 if b == "face" and r_ == sw]
    ck.check(f"A.button_led.{sw}", len(sers) == 1 and [x[:2] for x in reach_led] == [(sw, BUTTON_LED_A)],
             f"{led_role} = seed::{pin_consts[led_role]} (pin {pin_of(led_role)}) -> {sers} -> {reach_led}")
    k = reach_both("face", sw, BUTTON_LED_K)[1]
    ck.check(f"A.button_led_cathode.{sw}", ("main", "GND") in k, f"{sw} LED K (pad 6) reaches {sorted(k)}")
xf = {sw: 59.4 - R.face.parts[sw]["x"] for sw in ("SW1", "SW2")}
ck.check("A.button_order", xf["SW1"] < xf["SW2"] and btn_enum[:2] == ["BUTTON_A", "BUTTON_B"],
         f"front-view x SW1 {xf['SW1']:.1f}, SW2 {xf['SW2']:.1f}: BUTTON_A (Switch 0, Plaits' left = green bank) "
         "must be the left one")
ck.check("A.button_bank", re.search(r"new_bank\s*=\s*button\s*\+\s*1", UI) is not None
         and re.search(r"colors\[3\]\s*=\s*{\s*LED_COLOR_YELLOW\s*,\s*LED_COLOR_GREEN\s*,\s*LED_COLOR_RED", UI) is not None,
         "ui.cc: button 0 -> bank 1 = green, button 1 -> bank 2 = red (README: left = green bank)")

# --- the probe: D14 -> PROBE -> five 10k -> the lugs of the normalized jacks
seen, _ = reach_both("main", "U2", str(pin_of("kProbe")))
probe_rs = sorted({r_ for b, r_, p in seen if b == "face" and r_.startswith("R")})
probed = {}
for rr in probe_rs:
    rp = next(p for b, r_, p in seen if b == "face" and r_ == rr)
    _, lp = reach("face", rr, other_pad("face", rr, rp))
    js = [r_ for r_, p in lp if r_.startswith("J") and p == JACK_LUG]
    probed[rr] = (js, val("face", rr))
labels = sorted(JACK_LABEL[j] for js, v in probed.values() for j in js)
want = sorted({"TIMBRE", "FM", "MORPH", "TRIG", "LEVEL"})
fw_norm = sorted(CH_NAME[i] for i, d in enumerate(KCH) if d["normalized"])
ck.check("A.probe.lugs", labels == want and all(len(js) == 1 for js, v in probed.values()),
         f"seed::{pin_consts['kProbe']} (pin {pin_of('kProbe')}) -> {probed} -> lugs of {labels}; Plaits probes "
         f"{PLAITS_NORMALIZED}")
ck.check("A.probe.firmware_set", fw_norm == sorted(PLAITS_NORMALIZED), f"kChannels normalized: {fw_norm}")
ck.check("A.probe.resistors", all(v == PLAITS_PROBE_R for js, v in probed.values()) and len(probed) == 5,
         f"{ {k: v for k, (js, v) in probed.items()} } (Plaits: 10k, kProbeLowJackVoltage assumes 10k)")

# ================================================================== B. ADC
for i, name in enumerate(adc_pins + [pin_consts["kMuxOut"]]):
    gpio = seed_gpio(name)
    inst, ch = STM32_ADC_INP.get(gpio, (None, None))
    ld = [c for c, g in LIBDAISY_ADC_CHANNEL.items() if g == gpio]
    ck.check(f"B.adc1_channel.{name}", inst is not None and "1" in inst[3:] and ld == [ch],
             f"{name} = {gpio}: datasheet {inst}_INP{ch}; libDaisy ADC_CHANNEL_{ld} on {LIBDAISY_ADC_INSTANCE}")
ck.check("B.adc_channels_fit", len(adc_pins) + 1 <= LIBDAISY_ADC_MAX_CHANNELS and num_mux <= LIBDAISY_ADC_MAX_MUX
         and LIBDAISY_MUX_PINS(num_mux) == 3,
         f"{len(adc_pins) + 1} ADC channels (max {LIBDAISY_ADC_MAX_CHANNELS}), {num_mux} mux channels "
         f"-> {LIBDAISY_MUX_PINS(num_mux)} address pins written")
for k, bit in LIBDAISY_MUX_BIT.items():
    sel = MUX_BIT_OF_SEL.get(k)
    ck.check(f"B.mux_bit_order.mux_pin_{k}", sel is not None and HC4051_SEL_WEIGHT[sel] == bit,
             f"libDaisy writes (idx & {bit:#x}) to mux_pin_[{k}], which reaches 4051 {sel} "
             f"(weight {HC4051_SEL_WEIGHT.get(sel)})")
init_single = re.findall(r"InitSingle\(([^)]*)\)", HAL)
# [2026-11-14: the sampling times are read from hal_daisy.cc (InitMux now passes SPEED_32CYCLES_5 for the pot mux,
# the test report's L2 fix) instead of assuming libDaisy's default for every channel.]
m_mux = re.search(r"InitMux\(\s*kMuxOut\s*,\s*kNumMuxChannels\s*,\s*kMuxS0\s*,\s*kMuxS1\s*,\s*kMuxS2\s*"
                  r"(?:,\s*AdcChannelConfig::SPEED_(\d+)CYCLES_5\s*)?\)", HAL)
SMP_CV = LIBDAISY_ADC_DEFAULT_SMP
SMP_MUX = (int(m_mux.group(1)) + 0.5) if m_mux and m_mux.group(1) else LIBDAISY_ADC_DEFAULT_SMP
ck.check("B.sample_time", init_single and all("," not in a for a in init_single) and m_mux is not None
         and SMP_MUX in STM32_ADC_SMP,
         f"InitSingle({init_single}) without a speed: libDaisy's default {SMP_CV} cycles for the CVs; InitMux: "
         f"{SMP_MUX} cycles for the pots")
ovs_name = re.search(r"kOversampling\s*=\s*AdcHandle::(OVS_\w+)", HAL).group(1)
ovs = LIBDAISY_OVS[ovs_name]
pll3_vco = HSE / PLL3["M"] * (PLL3["N"] + PLL3["FRACN"] / 8192)
adc_ker = pll3_vco / PLL3["R"]
f_adc = adc_ker / LIBDAISY_ADC_PRESCALER / ADC_REV_V_DIV
f_adc_y = adc_ker / LIBDAISY_ADC_PRESCALER
ck.within("B.adc_clock", f_adc, 0.12e6, 6.25e6, " Hz",
          f"PLL3R {adc_ker / 1e6:.3f} MHz / {LIBDAISY_ADC_PRESCALER} / {ADC_REV_V_DIV} (rev V); BOOST 00 range up to "
          "6.25 MHz, any BOOST setting the HAL picks is fine")
n_ch = len(adc_pins) + 1
t_conv = (SMP_CV + STM32_ADC_TCONV_EXTRA) / f_adc
cyc_scan = ovs * ((n_ch - 1) * (SMP_CV + STM32_ADC_TCONV_EXTRA) + (SMP_MUX + STM32_ADC_TCONV_EXTRA))
t_scan = cyc_scan / f_adc
t_scan_y = cyc_scan / f_adc_y
# [2026-11-14: the stated figures are read from the comment and the README (they moved from 0.2 to 0.24 ms with
# the longer mux sampling) and the computed scan must lie within 20 % of each.]
m_hal = re.search(r"full scan of the nine channels near ([\d.]+) ms", " ".join(HAL.split()))
m_rd = re.search(r"scans all nine channels about every ([\d.]+) ms", README)
stated_scan = [float(m.group(1)) * 1e-3 for m in (m_hal, m_rd) if m]
ck.check("B.scan_comment_present", len(stated_scan) == 2, "hal_daisy.cc 'near ... ms' and the README 'about every ... ms'")
ck.within("B.scan_time_vs_comment", t_scan, 0.8 * max(stated_scan or [0]), 1.2 * min(stated_scan or [0]), " s",
          f"{ovs_name} x ({n_ch - 1} ch x ({SMP_CV} + {STM32_ADC_TCONV_EXTRA}) + mux ({SMP_MUX} + "
          f"{STM32_ADC_TCONV_EXTRA})) cycles / {f_adc / 1e6:.3f} MHz = {t_scan * 1e3:.3f} ms; stated "
          f"{[round(s * 1e3, 3) for s in stated_scan]} ms (without rev V's /2: {t_scan_y * 1e3:.3f} ms)")
# The probe changes at the end of DetectNormalization (every 4th poll, 1 ms); the next one compares readings
# Convert() took at the start of that poll, each at most one scan (+ the restart from the interrupt) old.
t_poll = 12 / AUDIO_FS
t_probe = POLL_DIV * t_poll
restart = 10e-6        # ISR + DMA re-init + HAL_ADC_Start_DMA: ASSUMED <= 10 us
age_max = max(t_scan, t_scan_y) + restart            # the slower (rev V) scan is the bound
settle_after_change = t_probe - age_max
# what has to settle: the jack node (10k || 100k with JACK_NODE_C) and the stage (Rf Cf, largest 13k x 1n)
tau = max(9.09e3 * JACK_NODE_C, 13e3 * 1e-9)
ck.check("B.convert_at_poll_start", re.search(r"void Ui::Poll\(\) {\s*(//[^\n]*\n\s*)*cv_adc_\.Convert\(\);", UI)
         is not None and UI.find("normalization_probe_.Write(normalization_probe_state_ >> 31)") > 0,
         "ui.cc: readings taken at the start of Poll(); the probe written at the end of DetectNormalization")
ck.within("B.probe_settle_margin", settle_after_change, 12 * tau, None, " s",
          f"probe period {t_probe * 1e3:.3f} ms - reading age <= {age_max * 1e3:.3f} ms = "
          f"{settle_after_change * 1e3:.3f} ms after the change, against 12 tau ({tau * 1e6:.1f} us) to 16 bits")
ck.within("B.scan_vs_probe_period", t_scan + restart, None, t_probe / 2, " s",
          f"a scan must be well inside the probe period ({t_probe * 1e3:.3f} ms)")
# the mux moves when a scan ends; A10 is last in the sequence, so the new pot has 8 channels' conversions to settle
t_mux_settle = (n_ch - 1) * ovs * t_conv
c_com = 60e-12           # 74HC4051 COM + Seed pin + header + tracks: ASSUMED (TI gives no COM capacitance at 3.3 V)
ck.check("B.mux_last_in_sequence", re.search(r"config\[ADC_INPUT_LAST\]\.InitMux", HAL) is not None,
         "the mux channel is the last of the sequence (hal_daisy.cc)")
ck.within("B.mux_settle", t_mux_settle, 16 * rain_mux_pre * c_com if (rain_mux_pre := 10e3 / 4 + HC4051_RON_33V) else 0,
          None, " s", f"{n_ch - 1} channels x {ovs_name} before A10 = {t_mux_settle * 1e6:.0f} us; the wiper "
                      f"({rain_mux_pre:.0f} Ω with {c_com * 1e12:.0f} pF) needs 16 tau = "
                      f"{16 * rain_mux_pre * c_com * 1e6:.2f} us")
# sampling time against the source impedance (Table 183 model: ts = (RAIN + R0) * C * ln(2^N / tol))
def t183_fit(bits):
    pts = sorted(STM32_T183_SLOW[bits].items())
    (r1, t1), (r2, t2) = pts[-2], pts[-1]
    k = math.log(2 ** bits / STM32_T183_TOL_LSB[bits])
    c = (t2 - t1) / (r2 - r1) / k
    r0 = t2 / (c * k) - r2
    return c, r0
c10, r010 = t183_fit(10)
c12, r012 = t183_fit(12)
ck.close("B.t183_model_consistent", c12, c10, 0.15 * c10, " F")
C_EFF, R0_EFF = (c10 + c12) / 2, (r010 + r012) / 2
ts = SMP_CV / f_adc
ts_mux = SMP_MUX / f_adc


def ts_needed(rain, bits):
    return (rain + R0_EFF) * C_EFF * math.log(2 ** bits / STM32_T183_TOL_LSB.get(bits, 10))


rain_cv = 1e3                    # the 1k series resistor (TL074 closed-loop output impedance ~0)
pot_r = 10e3
rain_mux = pot_r / 4 + HC4051_RON_33V
ck.within("B.sampling_time.cv_16bit", ts, ts_needed(rain_cv, 16), None, " s",
          f"tS {SMP_CV} cycles = {ts * 1e6:.3f} us; RAIN {rain_cv:.0f} Ω needs "
          f"{ts_needed(rain_cv, 16) * 1e6:.3f} us for 16 bits (Table 183 model, C {C_EFF * 1e12:.0f} pF, R0 {R0_EFF:.0f} Ω)")
ck.within("B.sampling_time.mux_12bit", ts_mux, ts_needed(rain_mux, 12), None, " s",
          f"pots, tS {SMP_MUX} cycles = {ts_mux * 1e6:.3f} us: RAIN {rain_mux:.0f} Ω (B10k at mid {pot_r / 4:.0f} + rON {HC4051_RON_33V:.0f}, assumed) needs "
          f"{ts_needed(rain_mux, 12) * 1e6:.3f} us for 12 bits (Plaits reads its pots with a 12-bit ADC); "
          f"16 bits would need {ts_needed(rain_mux, 16) * 1e6:.3f} us; the model is Table 183's, with its 47 pF on "
          f"the pin, about the typical MUX_OUT node (TI CCOM 25 pF + copper); with onsemi's 130 pF CCOM max the "
          f"node is 3x that, see analog_ac D.sample_hold.pots")

# ================================================================== C. SPI to the 74HC595s
for role, af_name, table in (("kSpiSck", "SPI1_SCK", LIBDAISY_SPI1_SCLK), ("kSpiMosi", "SPI1_MOSI", LIBDAISY_SPI1_MOSI)):
    gpio = seed_gpio(pin_consts[role])
    ck.check(f"C.af5.{role}", STM32_AF5.get(gpio, "").startswith(af_name) and table.get(gpio) == 5
             and SEED_DS_SPI1.get(pin_of(role), "").replace(" ", "_") == af_name,
             f"seed::{pin_consts[role]} = {gpio}: DS12556 AF5 {STM32_AF5.get(gpio)}, libDaisy SPI1 AF {table.get(gpio)}, "
             f"Seed pinout '{SEED_DS_SPI1.get(pin_of(role))}'")
spi_cfg = dict(re.findall(r"(?<![\w.])config\.(\w+)\s*=\s*([^;]+);", HAL))
ck.check("C.spi1", "SPI_1" in spi_cfg.get("periph", "") and "MASTER" in spi_cfg.get("mode", "")
         and "TWO_LINES_TX_ONLY" in spi_cfg.get("direction", "") and spi_cfg.get("datasize", "").strip() == "8"
         and "SOFT" in spi_cfg.get("nss", ""), f"{spi_cfg}")
spi_pins = dict(re.findall(r"config\.pin_config\.(\w+)\s*=\s*([^;]+);", HAL))
ck.check("C.spi_pins", spi_pins.get("sclk") == "kSpiSck" and spi_pins.get("mosi") == "kSpiMosi", f"{spi_pins}")
ck.check("C.spi_miso_unused", "Pin()" in spi_pins.get("miso", "") and "TX_ONLY" in spi_cfg.get("direction", ""),
         f"miso = {spi_pins.get('miso')}, direction {spi_cfg.get('direction')}: libDaisy initialises MISO only for "
         "TWO_LINES / RX, so PG9 (seed::D27 = MUX_S1, also in libDaisy's SPI1 MISO table) stays the mux's")
ck.check("C.mode0","ClockPolarity::LOW" in spi_cfg.get("clock_polarity", "")
         and "ClockPhase::ONE_EDGE" in spi_cfg.get("clock_phase", ""),
         "CPOL 0 / CPHA 0: SCK idles low, data valid before and sampled on the rising edge, the 595 shifts on "
         "SRCLK rising")
ck.check("C.msb_first", LIBDAISY_SPI_FIRSTBIT == "MSB" and "FirstBit" not in HAL and "LSB" not in HAL,
         "libDaisy fixes FirstBit = MSB; hal_daisy.cc does not change it")
bytes_init = re.search(r"uint8_t\s+bytes\[2\]\s*=\s*{(.*?)};", HAL, re.S)
order = [x.strip() for x in strip_comments(bytes_init.group(1)).split(",") if x.strip()] if bytes_init else []
hi_first = len(order) == 2 and ">> 8" in order[0] and "& 0xff" in order[1]
ck.check("C.byte_order", hi_first and "BlockingTransmit(bytes, 2)" in HAL,
         f"bytes = {order}: high byte first, MSB first -> the first bit out (15) ends in the last stage of the chain "
         "(U10 QH), bit 0 in U9 QA, as hal.h says and the bit checks of section A assume")
ps = int(re.search(r"BaudPrescaler::PS_(\d+)", HAL).group(1))
pll2_vco = HSE / PLL2["M"] * (PLL2["N"] + PLL2["FRACN"] / 8192)
spi_ker = pll2_vco / PLL2["P"]
f_sck = spi_ker / ps
ck.close("C.spi_kernel_clock", spi_ker, 25e6, 1e3, " Hz")
ck.close("C.sck_vs_design_md", f_sck, 1.56e6, 0.01e6, " Hz")
ck.check("C.design_md_states", "1.56 MHz (PLL2P 25 MHz / 16)" in DESIGN, "design.md's figure")
ck.within("C.sck_vs_comment_1.6MHz", f_sck, 1.6e6 * 0.95, 1.6e6 * 1.05, " Hz", "hal_daisy.cc: '1.6 MHz' (5 % rounding)")
t_frame = 16 / f_sck
ck.within("C.frame_vs_comment_10us", t_frame, 9.5e-6, 10.5e-6, " s", "hal_daisy.cc: '10 us for the 16 bits'")
ck.within("C.sck_vs_595_fmax", f_sck, None, HC595_FCLK_MAX[2.0], " Hz", "SN74HC595 fclock max at VCC 2 V (bound for 3.3 V)")
ck.within("C.sck_vs_gpio_speed_low", f_sck, None, STM32_GPIO_FMAX_LOW, " Hz", "GPIO speed 00, C = 50 pF")
half = 0.5 / f_sck
ck.within("C.sck_tw", half - STM32_GPIO_TRF_LOW, HC595_TW_MIN[2.0], None, " s", "SRCLK high / low (50 % duty less an edge)")
ck.within("C.ser_setup", half - STM32_GPIO_TRF_LOW, HC595_TSU_SER[2.0], None, " s",
          "mode 0: MOSI changes on the falling edge, half a period before the rising edge")
ck.within("C.ser_hold", half, HC595_TH_SER[2.0], None, " s", "MOSI holds until the next falling edge")
ck.within("C.chain_hop_setup", 1 / f_sck - HC595_TPD_QH_MAX[2.0], HC595_TSU_SER[2.0], None, " s",
          "U9 QH' moves tpd (max 200 ns at 2 V) after SRCLK rising; U10 samples it a period later")
ck.within("C.chain_hop_hold", HC595_TPD_QH_MIN, HC595_TH_SER[2.0], None, " s",
          "U10 needs th = 0 after the same edge that moves U9 QH'")
# RCLK pulse: DelayTicks(100) counts TIM2 at 2 x PCLK1
ticks = int(re.search(r"DelayTicks\((\d+)\)", HAL).group(1))
boost = re.search(r"hw\.Init\(\s*true\s*\)", MAIN) is not None
sysclk = HSE / PLL1["M"] * PLL1["N"]["480" if boost else "400"] / PLL1["P"]
pclk1 = sysclk / AHB_DIV / APB1_DIV
tim2 = 2 * pclk1
t_rclk = ticks / tim2
ck.within("C.rclk_pulse", t_rclk, HC595_TW_MIN[2.0], None, " s",
          f"DelayTicks({ticks}) at TIM2 {tim2 / 1e6:.0f} MHz (SYSCLK {sysclk / 1e6:.0f} MHz) = {t_rclk * 1e9:.0f} ns; "
          "plus the GPIO writes themselves")
tw33 = interp_vcc(HC595_TW_MIN)
ck.within("C.rclk_comment_50ns", 50e-9, 0.75 * tw33, 1.25 * tw33, " s",
          f"hal_daisy.cc: 'at least ~50 ns wide at 3.3 V'; the -40..85 C table interpolated to 3.3 V: {tw33 * 1e9:.0f} ns "
          f"(25 C: {interp_vcc(HC595_TW_MIN_25C) * 1e9:.0f} ns)")
ck.within("C.srclk_to_rclk_setup", half, HC595_TSU_SRCLK_RCLK[2.0], None, " s",
          "HAL_SPI_Transmit returns after EOT, at least half an SCK period after the last rising edge")
latch_seq = re.search(r"led_latch\.Init\([^)]*\);\s*led_latch\.Write\(false\);", HAL)
svc = re.search(r"led_latch\.Write\(true\);\s*System::DelayTicks\(\d+\);\s*led_latch\.Write\(false\);", HAL)
ck.check("C.rclk_idle_low", latch_seq is not None and svc is not None,
         "RCLK low after InitLeds and between frames; one rising edge per frame, after the 16 bits")
first_frame = re.search(r"InitLeds\(\);\s*plaitsy::hal::Service\(\);", MAIN)
ck.check("C.first_frame_first_thing", first_frame is not None and MAIN.find("InitLeds") < MAIN.find("InitButtons"),
         "main(): InitLeds() + Service() right after hw.Init: the first latched frame")
ck.check("C.first_frame_documented", "random pattern" in README and "no reset" in README,
         f"until then (the bootloader's {BOOT_GRACE_S:.0f} s grace + hw.Init) the 595 outputs are whatever they powered "
         "up with: the README says so")
# What drives SER / SRCLK / RCLK while the Seed is in reset, in the bootloader or waiting in it for an upload:
# STM32 GPIOs reset to analog (high impedance, no pull). Anything on the faceplate holding them?
pulls = {}
for sig in ("SER", "SRCLK", "RCLK"):
    seen, _ = reach_both("face", "U9", HC595_PIN[sig])          # both boards: a pull could sit on the MB side too
    pulls[sig] = sorted(f"{b}:{r_}" for b, r_, p in seen if r_.startswith("R"))
ck.check("C.595_inputs_defined_while_seed_in_reset", all(pulls[s] for s in ("SRCLK", "RCLK")),
         f"resistors on the 595 input nets: {pulls}. None: SRCLK and RCLK float for the ~{BOOT_GRACE_S:.0f} s of "
         "bootloader at every power-up and for as long as the bootloader waits (main.cc: 'the 74HC595s hold it while "
         "the bootloader waits'), so noise can shift / latch garbage and the CMOS inputs sit mid-rail")

# ================================================================== D. buttons, button LEDs, probe drive
ck.check("D.pullup_active_low", re.search(r"GPIO::Pull::PULLUP", HAL) is not None
         and re.search(r"return\s*!buttons\[button\]\.Read\(\);", HAL) is not None,
         "InitButtons: internal pull-ups; ButtonPressed = !Read() (contacts to ground)")
vdd_lo = 3.3 * (1 - RAIL_TOL_D)          # the Seed's GPIOs and the 595s run from 3V3D
tau_max = STM32_RPU[2] * BTN_LINE_C
ck.within("D.pullup_settle_before_read", 1e-3, 12 * tau_max, None, " s",
          f"main.cc System::Delay(1) (>= 1 ms) after InitButtons vs 12 x RPU max {STM32_RPU[2] / 1e3:.0f}k x "
          f"{BTN_LINE_C * 1e12:.0f} pF")
ck.check("D.delay_before_read", re.search(r"InitButtons\(\);\s*System::Delay\((\d+)\);\s*if \(plaitsy::hal::ButtonPressed",
                                          MAIN) is not None, "main.cc waits before reading the left button")
i_press = 3.3 * (1 + RAIL_TOL_D) / STM32_RPU[0]
ck.within("D.pullup_current_pressed", i_press, None, 1e-3, " A", "through the contacts while held (RPU min)")
ck.within("D.released_level", vdd_lo - 1e-6 * STM32_RPU[2], STM32_VIH_MIN * vdd_lo, None, " V",
          "released: VDD less 1 uA leakage x RPU max, against VIH min 0.7 VDD")
for sw, rr in (("SW1", "R60"), ("SW2", "R61")):
    r_ = val("main", rr) or 0
    i_max = (3.3 * (1 + RAIL_TOL_D) - BTN_LED_VF[0]) / (r_ * (1 - RES_TOL)) if r_ else 1
    ck.within(f"D.button_led_gpio_current.{sw}", i_max, None, STM32_IIO_8MA, " A",
              f"{rr} {r_:.0f} Ω, VF {BTN_LED_VF[0]} V (lowest assumed): within the 8 mA at which VOH >= VDD - 0.4 V")
i_probe_hi = 5 * (3.3 * (1 + RAIL_TOL_D) - 0) / (PLAITS_PROBE_R * (1 - RES_TOL) + 100e3 * (1 - RES_TOL))
i_total = 2 * STM32_IIO_8MA + i_probe_hi + 1e-3
ck.within("D.probe_gpio_current", i_probe_hi, None, STM32_IIO_8MA, " A", "five lugs through 10k + 100k to the bias")
ck.within("D.total_gpio_source", i_total, None, STM32_IIO_SUM_ABS, " A",
          "button LEDs at 8 mA each + probe + 1 mA for the logic lines, against the 140 mA sum")
# logic levels: Seed GPIO (3V3D) into the 595s (3V3D_F) and the 4051's address inputs (3V3A_F); VIH / VIL
# interpolated between the 2 V and 4.5 V columns at the receiver's worst rail (they scale with VCC)
vdd_hi = 3.3 * (1 + max(RAIL_TOL_A, RAIL_TOL_D))   # the 595s on 3V3D, the 4051 on 3V3A
voh_min = vdd_lo - STM32_VOH_DROP_8MA            # the 8 mA figure; the real loads are microamps
for what in ("74HC595 SER/SRCLK/RCLK", "74HC4051 S0..S2"):
    ck.within(f"D.logic_high.{what.split()[0]}", voh_min, interp_vcc(HC_VIH_MIN, vdd_hi), None, " V",
              f"GPIO VOH min (VDD {vdd_lo:.2f} V - 0.4) against VIH min at VCC {vdd_hi:.2f} V (interpolated)")
    ck.within(f"D.logic_low.{what.split()[0]}", 0.4, None, interp_vcc(HC_VIL_MAX, vdd_lo), " V",
              f"GPIO VOL max 0.4 V against VIL max at VCC {vdd_lo:.2f} V (interpolated)")
ck.within("D.input_transition", STM32_GPIO_TRF_LOW, None, HC_INPUT_TT_MAX[4.5], " s",
          "GPIO speed 00 edges (50 pF) against the HC input transition limit (4.5 V column, the tighter one)")

# ================================================================== E. CV conversion
names = {"kVdd": cnum(re.search(r"kVdd\s*=\s*([^;]+);", CV).group(1))}
names["kBiasWide"] = cnum(re.search(r"kBiasWide\s*=\s*([^;]+);", CV).group(1), names)
names["kBiasVOct"] = cnum(re.search(r"kBiasVOct\s*=\s*([^;]+);", CV).group(1), names)
FW_STAGE = {}
for nm in ("kPlaitsyWide", "kPlaitsyVOct"):
    g_, v0_ = re.search(rf"{nm}\s*=\s*{{\s*([^,]+),\s*(.+?)\s*}};", CV).groups()
    FW_STAGE[nm] = (cnum(g_, names), cnum(v0_, names))
ck.close("E.kVdd", names["kVdd"], 3.3, 1e-6, " V")
pl_tmpl = re.search(r"return\s*{\s*rf\s*/\s*([\d.]+)f\s*,\s*([\d.]+)f\s*\*\s*rf\s*/\s*rref\s*}", CV)
ck.check("E.plaits_stage_formula", pl_tmpl is not None and float(pl_tmpl.group(1)) * 1e3 == 100e3
         and float(pl_tmpl.group(2)) == PLAITS_REF, "PlaitsStage(): g = rf / 100k, v0 = 10 V x rf / rref "
                                                     f"(Plaits: Rin 100k, |AREF| {PLAITS_REF} V)")
for ci, cname_ in enumerate(CH_NAME):
    if ci >= len(KCH):
        break
    d = KCH[ci]
    st = STAGES.get(d["input"], {})
    try:
        rin, rf = st["Rin"][0][1], st["Rf"][0][1]
        vb = 3.3 * st["Rbot"][1] / (st["Rtop"][1] + st["Rbot"][1])
    except (KeyError, IndexError, TypeError):
        ck.check(f"E.plaitsy_stage.{cname_}", False, f"stage not found: {st}")
        continue
    g_real, v0_real = rf / rin, vb * (1 + rf / rin)
    fw = FW_STAGE["kPlaitsyVOct" if d["voct"] else "kPlaitsyWide"]
    ck.close(f"E.plaitsy_gain.{cname_}", fw[0], g_real, 1e-6,
             f" (fw {'VOct' if d['voct'] else 'Wide'}; routed {st['Rf'][0][0]} {rf:.0f} / {st['Rin'][0][0]} {rin:.0f})")
    ck.close(f"E.plaitsy_v0.{cname_}", fw[1], v0_real, 1e-5,
             f" V (routed bias {st['Rtop'][0]} {st['Rtop'][1]:.0f} / {st['Rbot'][0]} {st['Rbot'][1]:.0f} = {vb:.4f} V)")
    st["g"], st["v0"], st["vb"] = g_real, v0_real, vb
    # Plaits' stage of the same channel
    ps_ = PLAITS_STAGE[cname_]
    ck.check(f"E.plaits_stage_vs_schematic.{cname_}", d["rf"] == ps_[2] and d["rref"] == ps_[3] and ps_[1] == 100e3,
             f"kChannels rf {d['rf']:.0f}, rref {d['rref']:.0f}; plaits_v50 {ps_[0]}: Rf {ps_[2]:.0f}, Rref {ps_[3]:.0f}")
    lug_probe = ps_[5].startswith("probe")
    ck.check(f"E.plaits_normalized_vs_schematic.{cname_}", lug_probe == d["normalized"],
             f"plaits_v50 lug: {ps_[5]}; kChannels normalized {d['normalized']}")
    # Plaits' factory offset says where its 0 V reading is: offset ~ -scale x zero-volt value
    off, scale, thr = PLAITS_DEFAULTS[cname_]
    zero = (PLAITS_REF * ps_[2] / ps_[3]) / PLAITS_VREF * 2 - 1
    tol = {"V_OCT": 0.05, "LEVEL": 0.01}.get(cname_)
    if tol:
        ck.close(f"E.plaits_factory_offset_fits_stage.{cname_}", off, -scale * zero, tol,
                 f" (settings.cc offset vs -scale x float(0 V) of the {ps_[2] / 1e3:.0f}k/{ps_[3] / 1e3:.0f}k stage)")
pv_1v = ((PLAITS_REF * 33e3 / 140e3) - 0.33 * 1.0) / PLAITS_VREF * 2 - 1
ck.close("E.plaits_ui_comment_voct", pv_1v, PLAITS_UI_VOCT_1V, 0.001, "", )
# Plaitsy's settings.cc defaults = Plaits 1.2's (scales and thresholds)
for cname_, (off, scale, thr) in PLAITS_DEFAULTS.items():
    m = re.search(rf"c\[CV_ADC_CHANNEL_{cname_}\]\.scale\s*=\s*([-\d.]+)f?;", SETTINGS)
    t = re.search(rf"c\[CV_ADC_CHANNEL_{cname_}\]\.normalization_detection_threshold\s*=\s*([-\d]+);", SETTINGS)
    ck.check(f"E.defaults_as_plaits.{cname_}", m and float(m.group(1)) == scale and t and int(t.group(1)) == thr,
             f"Plaitsy scale {m.group(1) if m else None}, threshold {t.group(1) if t else None}; Plaits 1.2 {scale}, {thr}")
ck.check("E.offsets_from_nominal", re.search(r"c\[i\]\.offset\s*=\s*-c\[i\]\.scale\s*\*\s*CvAdc::zero_volt_value", SETTINGS)
         is not None, "settings.cc replaces the factory offsets by -scale x zero_volt_value (0 V reads 0)")


# end to end: jack voltage -> Plaitsy (nominal routed parts, ideal 16-bit ADC on 3V3A) -> firmware -> Plaits units
def fw_conv(ci):
    d = KCH[ci]
    s = FW_STAGE["kPlaitsyVOct" if d["voct"] else "kPlaitsyWide"]
    pg, pv0 = d["rf"] / 100e3, PLAITS_REF * d["rf"] / d["rref"]
    gain = pg / s[0]
    offset = (pv0 - pg * s[1] / s[0]) / names["kVdd"] * 65536 - 32768
    return gain, offset


def plaitsy_code(vj, g, v0, vref=3.3):
    v = min(max(v0 - g * vj, 0.0), vref)
    return min(int(v / vref * 65536), 65535)


def fw_value(ci, code):
    gain, offset = fw_conv(ci)
    v = min(max(gain * code + offset, -32768.0), 32767.0)
    return int(v)                     # static_cast<int16_t> truncates towards zero


def plaits_value(cname_, vj):
    _, rin, rf, rref, _, _ = PLAITS_STAGE[cname_]
    v = (PLAITS_REF * rf / rref - rf / rin * vj) / PLAITS_VREF * 65536 - 32768
    return min(max(v, -32768.0), 32767.0)


PRACTICAL = {"MODEL": (-5, 5), "HARMONICS": (-5, 5), "TIMBRE": (-8, 8), "FM": (-8, 8), "MORPH": (-8, 8),
             "TRIGGER": (-0.8, 5), "LEVEL": (-0.8, 9), "V_OCT": (-2.8, 7.1)}
for ci, cname_ in enumerate(CH_NAME):
    st = STAGES.get(KCH[ci]["input"], {})
    if "g" not in st:
        continue
    lo, hi = PRACTICAL[cname_]
    worst = 0.0
    at = None
    for vj in [lo + (hi - lo) * k / 400 for k in range(401)]:
        a = fw_value(ci, plaitsy_code(vj, st["g"], st["v0"]))
        b = plaits_value(cname_, vj)
        if abs(a - b) > worst:
            worst, at = abs(a - b), vj
    gain = fw_conv(ci)[0]
    ck.within(f"E.end_to_end.{cname_}", worst, None, 1.5 + gain, " LSB",
              f"|Plaitsy firmware - Plaits SDADC| over {lo}..{hi} V, worst at {at:.3f} V (gain {gain:.3f} "
              "Plaits LSB per Seed LSB; truncation + ADC rounding)")
    if cname_ != "V_OCT":         # V/OCT's clipping is F.voct_reach_*
        clip = max(abs(fw_value(ci, plaitsy_code(v, st["g"], st["v0"])) - plaits_value(cname_, v)) for v in (-12, 12))
        ck.within(f"E.clips_as_plaits.{cname_}", clip, None, 1.5 + gain, " LSB",
                  "at +-12 V both read Plaits' clipped value (the firmware's CONSTRAIN, not the Seed's ADC, clips)")

# ================================================================== F. thresholds as jack voltages
def jack_v_of_value(ci, value, g, v0, vref=3.3):
    """The jack voltage at which the firmware's value crosses `value` on a Plaitsy with stage (g, v0) and VREF."""
    gain, offset = fw_conv(ci)
    code = (value - offset) / gain
    v_adc = code / 65536 * vref
    return (v0 - v_adc) / g


norm_idx = [CH_NAME.index(c) for c in PLAITS_NORMALIZED]
vj_lo_nom = vj_hi_nom = None
for ci in norm_idx:
    cname_ = CH_NAME[ci]
    st = STAGES[KCH[ci]["input"]]
    off, scale, thr = PLAITS_DEFAULTS[cname_]
    _, rin, rf, rref, _, _ = PLAITS_STAGE[cname_]
    vt_plaits = (PLAITS_REF * rf / rref - (thr + 32768) / 65536 * PLAITS_VREF) / (rf / rin)
    vt_plaitsy = jack_v_of_value(ci, thr, st["g"], st["v0"])
    rp = probed and next(iter(probed.values()))[1] or 10e3
    rin_y = st["Rin"][0][1]
    vlo = st["vb"] * rp / (rp + rin_y)
    vhi = (3.3 * rin_y + st["vb"] * rp) / (rp + rin_y)
    vj_lo_nom, vj_hi_nom = vlo, vhi
    ck.close(f"F.threshold_jack_voltage.{cname_}", vt_plaitsy, vt_plaits, 0.005, " V")
    ck.close(f"F.threshold_vs_design_md.{cname_}", vt_plaitsy, 0.83, 0.01, " V")
    # worst case: 1 % resistors, 3V3A (bias source and ADC reference) +-3.5 % and 3V3D (probe high) +-4.5 %
    rtop, rbot, rf_y = st["Rtop"][1], st["Rbot"][1], st["Rf"][0][1]
    m_lo = m_hi = float("inf")
    for e in itertools.product((-1, 1), repeat=7):
        a3 = 3.3 * (1 + e[0] * RAIL_TOL_A)
        d3 = 3.3 * (1 + e[1] * RAIL_TOL_D)
        rt, rb = rtop * (1 + e[2] * RES_TOL), rbot * (1 + e[3] * RES_TOL)
        ri, rfx, rpx = rin_y * (1 + e[4] * RES_TOL), rf_y * (1 + e[5] * RES_TOL), rp * (1 + e[6] * RES_TOL)
        vb = a3 * rb / (rt + rb)
        g, v0 = rfx / ri, vb * (1 + rfx / ri)
        lo_, hi_ = vb * rpx / (rpx + ri), (d3 * ri + vb * rpx) / (rpx + ri)
        val_lo = fw_value(ci, plaitsy_code(lo_, g, v0, a3))
        val_hi = fw_value(ci, plaitsy_code(hi_, g, v0, a3))
        m_lo = min(m_lo, val_lo - thr)          # probe low must read >= threshold (read_value false)
        m_hi = min(m_hi, thr - val_hi)          # probe high must read < threshold
    ck.within(f"F.probe_low_margin_worst.{cname_}", m_lo, 1000, None, " LSB",
              f"probe low: jack {vlo:.3f} V nominal; worst-case Plaits value above the threshold {thr}")
    ck.within(f"F.probe_high_margin_worst.{cname_}", m_hi, 1000, None, " LSB",
              f"probe high: jack {vhi:.3f} V nominal; worst-case Plaits value below the threshold {thr}")
ck.close("F.probe_swing_low_vs_design_md", vj_lo_nom, 0.13, 0.005, " V")
ck.close("F.probe_swing_high_vs_design_md", vj_hi_nom, 3.13, 0.005, " V")
ck.check("F.design_md_states_swing", "0.13 V / 3.13 V" in DESIGN and "about 0.83 V" in DESIGN, "design.md's figures")
ck.check("F.detect_compare", re.search(r"cv_adc_\.value\(channel\)\s*<\s*\\?\s*settings_->calibration_data\(channel\)"
                                       r"\.normalization_detection_threshold", UI) is not None
         and re.search(r"normalization_detection_mismatches_\[i\]\s*>=\s*2", UI) is not None,
         "ui.cc: read = value < threshold (probe high -> jack high -> value low), patched after >= 2 mismatches "
         "in 32, as Plaits")
# probe_low_offset: sign and size
pl_expr = re.search(r"kProbeLowJackVoltage\s*=\s*([^;]+);", CV).group(1)
kplj = cnum(pl_expr, names)
ck.close("F.kProbeLowJackVoltage", kplj, vj_lo_nom, 1e-4, " V")
po = re.search(r"return\s*-p\.g\s*\*\s*kProbeLowJackVoltage\s*/\s*kVdd\s*\*\s*2\.0f;", CV)
ck.check("F.probe_low_offset_sign", po is not None and re.search(r"cv_adc_\.float_value\(CvAdcChannel\(i\)\)\s*-\s*\\?\s*"
                                                                  r"cv_adc_\.probe_low_offset", UI) is not None,
         "probe_low_offset = -g_plaits x 0.133 V x 2 / 3.3 (a positive jack voltage reads below the 0 V value); "
         "CalibrateC1 subtracts it, so the zero is taken at 0 V")
for ci in norm_idx:
    cname_ = CH_NAME[ci]
    st = STAGES[KCH[ci]["input"]]
    pg = KCH[ci]["rf"] / 100e3
    expect = fw_value(ci, plaitsy_code(vj_lo_nom, st["g"], st["v0"])) / 32768 - \
        fw_value(ci, plaitsy_code(0.0, st["g"], st["v0"])) / 32768
    ck.close(f"F.probe_low_offset_size.{cname_}", -pg * kplj / 3.3 * 2, expect, 1e-4)
# TRIG: Plaits' trigger thresholds (voice.cc) through the boot calibration, as jack voltages
ti = CH_NAME.index("TRIGGER")
st = STAGES[KCH[ti]["input"]]
off, scale, thr = PLAITS_DEFAULTS["TRIGGER"]
pg = KCH[ti]["rf"] / 100e3
per_volt = -scale * pg * 2 / 3.3                    # Transform(float) per jack volt, offset from the nominal zero
v_on, v_off = PLAITS_TRIG_ON / per_volt, PLAITS_TRIG_OFF / per_volt
zero_pl = (PLAITS_REF * pg * 100e3 / KCH[ti]["rref"]) / 3.3 * 2 - 1
v_on_plaits = (PLAITS_TRIG_ON - (off + scale * zero_pl)) / per_volt
ck.within("F.trig_threshold_on", v_on, 1.0, 2.5, " V", f"rises at {v_on:.3f} V, falls at {v_off:.3f} V at the jack "
                                                       f"(Plaits with its factory offset: {v_on_plaits:.3f} V)")
ck.close("F.trig_threshold_vs_plaits", v_on, v_on_plaits, 0.15, " V")
# MODEL: about 0.21 V per model
mi = CH_NAME.index("MODEL")
pg = KCH[mi]["rf"] / 100e3
v_per_model = 1 / ((PLAITS_ENGINES - 1) * abs(PLAITS_DEFAULTS["MODEL"][1]) * pg * 2 / 3.3)
ck.close("F.model_volts_per_model", v_per_model, 0.21, 0.005, " V")
ck.check("F.readme_states_model", "about 0.21 V per model" in README, "README's figure")
# V/OCT reach against Plaits' own range
vi = CH_NAME.index("V_OCT")
st = STAGES[KCH[vi]["input"]]
reach_lo, reach_hi = (st["v0"] - 3.3) / st["g"], st["v0"] / st["g"]
_, rin, rf, rref, _, _ = PLAITS_STAGE["V_OCT"]
pl_lo, pl_hi = (PLAITS_REF * rf / rref - PLAITS_VREF) / (rf / rin), (PLAITS_REF * rf / rref) / (rf / rin)
ck.within("F.voct_reach_low", reach_lo, None, pl_lo, " V", f"Plaitsy reads down to {reach_lo:.3f} V, Plaits {pl_lo:.3f} V")
ck.within("F.voct_reach_high", reach_hi, pl_hi, None, " V",
          f"Plaitsy reads up to {reach_hi:.3f} V before the ADC clips at 0 V, Plaits {pl_hi:.3f} V: the firmware's "
          f"top value is {fw_value(vi, 0)} where Plaits reaches -32768")
# [2026-11-14: design.md's figures are read, not copied here (they were -2.9 / +7.1 V with R43 33k)]
_m_use = re.search(r"usable −([\d.]+) … \+([\d.]+) V", DESIGN)
_doc_lo, _doc_hi = (-float(_m_use.group(1)), float(_m_use.group(2))) if _m_use else (float("nan"), float("nan"))
ck.close("F.voct_reach_nominal_vs_design_md.low", reach_lo, _doc_lo, 0.05, " V")      # design.md "usable ... V"
ck.close("F.voct_reach_nominal_vs_design_md.high", reach_hi, _doc_hi, 0.05, " V")


def voct_reach_corners(rail_tol):
    wl, wh = [], []
    for e in itertools.product((-1, 1), repeat=5):
        a3 = 3.3 * (1 + e[0] * rail_tol)
        rt, rb = st["Rtop"][1] * (1 + e[1] * RES_TOL), st["Rbot"][1] * (1 + e[2] * RES_TOL)
        gg = st["Rf"][0][1] * (1 + e[3] * RES_TOL) / (st["Rin"][0][1] * (1 + e[4] * RES_TOL))
        vb = a3 * rb / (rt + rb)
        v0 = vb * (1 + gg)
        wl.append((v0 - a3) / gg)
        wh.append(v0 / gg)
    return wl, wh


wl, wh = voct_reach_corners(RAIL_TOL_A)
wl1, wh1 = voct_reach_corners(0.01)
# VERIFY 2026-11-13: the requirement was -2 .. +7 V ("nine octaves", not a figure from the docs). README: "every
# input has Plaits' range and response: V/OCT -3...+7 V", Plaits' own reach being pl_lo .. pl_hi = -2.857 .. +7.143 V;
# the worst corner is held to that less 0.1 V at each end, as analog_dc B.voct_*_end_worst holds it to design.md's
# -2.9 .. +7.1 V.
for end, got, lim in (("high", min(wh), pl_hi - 0.1), ("low", max(wl), pl_lo + 0.1)):
    ck.check(f"F.voct_reach_worst.{end}", got >= lim if end == "high" else got <= lim,
             f"worst-case {end} end {got:.3f} V, needs {lim:+.2f} V (Plaits' V/OCT reach {pl_lo:+.3f} .. {pl_hi:+.3f} V, the "
             f"README's 'Plaits' range', less 0.1 V) with 1 % parts and "
             f"3V3A +-{RAIL_TOL_A * 100:.1f} % (LP2985 over temperature): low end {min(wl):.2f}..{max(wl):.2f}, high end {min(wh):.2f}..{max(wh):.2f} V "
             f"(3V3A +-1 %: high end down to {min(wh1):.2f}, low end up to {max(wl1):.2f}); the span is "
             f"3V3A / g = {3.3 / st['g']:.2f} V, Plaits' own {PLAITS_VREF / 0.33:.2f} V: no margin either way")
for ci, cname_ in enumerate(CH_NAME):
    if cname_ == "V_OCT":
        continue
    st = STAGES[KCH[ci]["input"]]
    _, rin, rf, rref, _, _ = PLAITS_STAGE[cname_]
    p_lo, p_hi = (PLAITS_REF * rf / rref - PLAITS_VREF) / (rf / rin), (PLAITS_REF * rf / rref) / (rf / rin)
    y_lo, y_hi = (st["v0"] - 3.3) / st["g"], st["v0"] / st["g"]
    ck.check(f"F.reach_covers_plaits.{cname_}", y_lo <= p_lo and y_hi >= p_hi,
             f"Plaitsy {y_lo:.2f}..{y_hi:.2f} V covers Plaits {p_lo:.2f}..{p_hi:.2f} V")
# design.md / README stated stage figures
st = STAGES[KCH[mi]["input"]]
ck.close("F.design_wide_v0", st["v0"], 1.658, 0.001, " V")
ck.close("F.design_wide_minus12", st["v0"] + 0.13 * 12, 3.22, 0.005, " V")
ck.close("F.design_wide_plus12", st["v0"] - 0.13 * 12, 0.10, 0.005, " V")
stv = STAGES[KCH[vi]["input"]]
_m_v0 = re.search(r"\*\*V/OCT\*\* \(gain −[\d.]+\): V_adc = ([\d.]+) V", DESIGN)        # [2026-11-14: read]
ck.close("F.design_voct_v0", stv["v0"], float(_m_v0.group(1)) if _m_v0 else float("nan"), 0.001, " V")
# loose cable: the tip floats at the virtual ground = the bias; the firmware reads (v0 - Vb) / g = Vb
ck.close("F.readme_loose_cable_wide", (st["v0"] - st["vb"]) / st["g"], 1.5, 0.05, " V")
ck.close("F.readme_loose_cable_voct", (stv["v0"] - stv["vb"]) / stv["g"], 1.8, 0.05, " V")
# calibration window: the second voltage 1..3 V above the first
per_v = -(KCH[vi]["rf"] / 100e3) * 2 / 3.3
win = (PLAITS_CAL_WINDOW[1] / per_v, PLAITS_CAL_WINDOW[0] / per_v)
ck.check("F.readme_calibration_window", abs(win[0] - 1) < 0.05 and abs(win[1] - 3) < 0.05
         and re.search(r"delta\s*>\s*-0\.6f\s*&&\s*delta\s*<\s*-0\.2f", UI) is not None,
         f"accepted step {win[0]:.2f}..{win[1]:.2f} V (README: 'between about 1 and 3 V above the first')")
# uncalibrated: "the pitch can be most of a semitone off and the octaves ten cents or more out"
offs, scl = [], []
for e in itertools.product((-1, 1), repeat=5):
    rt, rb = stv["Rtop"][1] * (1 + e[0] * RES_TOL), stv["Rbot"][1] * (1 + e[1] * RES_TOL)
    ri, rfx = stv["Rin"][0][1] * (1 + e[2] * RES_TOL), stv["Rf"][0][1] * (1 + e[3] * RES_TOL)
    a3 = 3.3 * (1 + e[4] * RAIL_TOL_A_25C)
    vb = a3 * rb / (rt + rb)
    g, v0 = rfx / ri, vb * (1 + rfx / ri)
    # the firmware assumes nominal: Vj_read = (v0_nom - V_adc_read) / g_nom with V_adc_read = V_adc x 3.3 / a3
    def read(vj):
        return (stv["v0"] - (v0 - g * vj) * 3.3 / a3) / stv["g"]
    offs.append(abs(read(0.0)) * 12)
    scl.append(abs((read(1.0) - read(0.0)) - 1) * 1200)
# VERIFY 2026-11-13: the window was 0.5 .. 1.5 semitones, which lets 1.5 semitones count as "most of a semitone";
# "most of a semitone" is more than half of one and less than one. analog_dc D.readme_semitone gets the same
# 1.22 semitones from the resistors alone (the 3V3A tolerance does not move the zero: the bias is ratiometric).
# [2026-11-14: the README now states figures ("up to about 1.3 semitones off and the octaves up to about 25 cents
# out" for 1 % resistors); they are read from it and held as "about" upper bounds: the worst case may exceed a
# figure by 10 % at most and must reach 70 % of it. This model has the resistors and 3V3A, not the op-amp.]
m_unc = re.search(r"With 1 % resistors the pitch can be up to about ([\d.]+) semitones off and the octaves up to "
                  r"about (\d+) cents out", README)
st_off, st_oct = (float(m_unc.group(1)), float(m_unc.group(2))) if m_unc else (float("nan"), float("nan"))
ck.within("F.readme_uncal_pitch_offset", max(offs), 0.7 * st_off, 1.1 * st_off, " semitones",
          f"worst-case 0 V error uncalibrated, 1 % resistors and 3V3A +-2.5 % (25 C) (the bias is ratiometric, so "
          f"3V3A does not move the zero) against the README's 'up to about {st_off:g} semitones off'")
ck.within("F.readme_uncal_octave", max(scl), 0.7 * st_oct, None, " cents",
          f"worst-case octave error, resistors and 3V3A (README: 'up to about {st_oct:g} cents' from the resistors "
          f"alone; 3V3A adds to it, the README's second figure)")
# "an unpatched MODEL input can select the model next to the one the buttons picked": MODEL's 0 V error in models
stm = STAGES[KCH[mi]["input"]]
merr = []
for e in itertools.product((-1, 1), repeat=4):
    rt, rb = stm["Rtop"][1] * (1 + e[0] * RES_TOL), stm["Rbot"][1] * (1 + e[1] * RES_TOL)
    ri, rfx = stm["Rin"][0][1] * (1 + e[2] * RES_TOL), stm["Rf"][0][1] * (1 + e[3] * RES_TOL)
    vb = 3.3 * rb / (rt + rb)
    v0 = vb * (1 + rfx / ri)
    merr.append(abs(stm["v0"] - v0) / stm["g"] / v_per_model)
ck.within("F.readme_uncal_model", max(merr), 0.5 + PLAITS_ENGINE_HYST, None, " models",
          f"worst-case 0 V reading on unpatched MODEL, uncalibrated: {max(merr):.2f} models; the quantizer moves at "
          f"0.5 + {PLAITS_ENGINE_HYST} hysteresis, so the README's warning holds")

# ================================================================== G. flash, bootloader, watchdog
binsize = os.path.getsize(os.path.join(harness.FIRMWARE, "plaitsy.bin"))
ck.within("G.program_size_vs_bootloader", binsize, None, BOOT_SRAM_LIMIT, " B", "plaitsy.bin against the 480 kB SRAM program area")
m = re.search(r"The program is (\d+) kB", README)
ck.close("G.program_size_vs_readme", binsize / 1024, float(m.group(1)) if m else 0, 2.0, " kB")
s_off = cnum(re.search(r"kSettingsFlashOffset\s*=\s*([^;]+);", SETTINGS).group(1))
s_sec = cnum(re.search(r"kSettingsFlashSectors\s*=\s*([^;]+);", SETTINGS).group(1))
u_off = cnum(re.search(r"kUserDataFlashOffset\s*=\s*([^;]+);", USER_DATA).group(1))
u_size = cnum(re.search(r"SIZE\s*=\s*(0x[0-9a-fA-F]+|\d+)", USER_DATA_H).group(1))
sec = cnum(re.search(r"kFlashSectorSize\s*=\s*([^;]+);", HAL_H).group(1))
regions = [("settings", s_off, s_off + s_sec * sec), ("user data", u_off, u_off + u_size)]
ck.check("G.qspi_regions_in_free_area", all(BOOT_QSPI_FREE[0] <= a and b <= BOOT_QSPI_FREE[1] for _, a, b in regions)
         and regions[0][2] <= regions[1][1] and all(a % sec == 0 and (b - a) % sec == 0 for _, a, b in regions),
         f"{[(n, hex(a), hex(b)) for n, a, b in regions]} inside {tuple(hex(x) for x in BOOT_QSPI_FREE)}, sector-aligned, "
         "not overlapping")
ck.check("G.qspi_vs_readme", max(b for _, a, b in regions) <= 128 * 1024 and "first 128 kB" in README
         and s_sec * sec == 64 * 1024 and "first 64 kB" in README and u_off == 0x10000 and "at 64 kB" in README,
         "README: settings in the first 64 kB, custom data at 64 kB, all in the first 128 kB")
ck.check("G.qspi_vs_settings_comment", "0x40000" in SETTINGS and BOOT_QSPI_FREE[1] == 0x40000,
         "settings.cc: 'leaves the first 256 kB free and keeps the program from 0x40000 on'")
pre = re.search(r"IWDG_PRESCALER_(\d+)", HAL)
rel = re.search(r"Init\.Reload\s*=\s*(\d+)", HAL)
pre, rel = int(pre.group(1)), int(rel.group(1))
ck.within("G.iwdg_reload_fits", rel, 1, IWDG_RLR_MAX, "")
t_typ = rel / (STM32_LSI_25C[1] / pre)
t_min, t_max = rel / (STM32_LSI_FULL[1] / pre), rel / (STM32_LSI_FULL[0] / pre)
ck.within("G.watchdog_typ_vs_comment", t_typ, 1.8, 2.2, " s", f"LSI 32 kHz / {pre}, {rel} counts (hal_daisy.cc: 'about 2 s')")
ck.within("G.watchdog_range", t_min, 1.5, None, " s", f"LSI {STM32_LSI_FULL[1] / 1e3:.1f} kHz max -> {t_min:.3f} s; "
                                                      f"LSI {STM32_LSI_FULL[0] / 1e3:.1f} kHz min -> {t_max:.3f} s")
ck.within("G.watchdog_vs_feed", t_min, 100 * 12 / AUDIO_FS, None, " s", "fed every audio block (0.25 ms)")
ck.close("G.plaits_watchdog_comment", PLAITS_WDG_S, 1.6, 0.1, " s")
ck.check("G.bootloader_before_watchdog", 0 < MAIN.find("ResetToBootloader") < MAIN.find("StartWatchdog()")
         and MAIN.find("StartAudio") < MAIN.find("StartWatchdog()"),
         "the IWDG survives a reset: ResetToBootloader must come before it is started (it does), audio first")
ck.check("G.readme_watchdog", "restarts the module if the audio stops for 2 s" in README, "README: 2 s")

ck.done()
