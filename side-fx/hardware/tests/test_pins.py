"""pins: the Seed's pins, from the firmware through libDaisy and the STM32 to the routed copper.

What it checks:
  A. check_pins.py (side-fx/firmware/tools) runs as a subprocess and exits 0; one check per line it prints.
  B. The firmware's pin constants, re-derived independently of check_pins.py: hal_daisy.cc kPin* / kPinCv,
     display_daisy.cc's CS, DC, RST, SCK, MOSI and backlight pins, against
       - the Daisy Seed datasheet's pin names (pin number <-> libDaisy name),
       - circuit.SEED, and the routed main board's U5 pad nets (two sources, both checked),
       - libDaisy v9.0.0's daisy_seed.h ports, and the port names in hal.h's and display_daisy.cc's
         pin tables and hal_daisy.cc's comments,
       - design.md's "Daisy Seed pin map" table and its list of free pins.
  C. Peripherals: SPI1 SCK / MOSI on D8 / D10 with the AF libDaisy's SpiHandle uses (STM32H750 AF table),
     MISO and hardware NSS left off; USART1_RX on D14 = PB7 with the firmware's AF, receive only; TIM4_CH4
     on D12 = PB9 (AF2) and no other TIM4 channel pin; A0..A3 = which ADC and channel each, and that
     libDaisy's ADC1 table has them; no used pin among the Seed's own (SDRAM, QSPI, codec SAI1 / I2C /
     reset, LED, test point, USB FS, version pins, crystals, SWD); D13 (PB6, USART1_TX's pin) a plain
     GPIO while USART1 runs; D29 / D30 (USB HS D- / D+) with no USB HS started; one EXTI user per line;
     timers TIM2..TIM5 one owner each.
  D. The chain's bit order, simulated on gate models of the 74HC165s and the 74HC595 with the edge order
     read from ShiftChain, with the chips found by their nets on the ROUTED boards (TI's pinouts, not
     circuit.HC165_INPUTS): which 165 is read first, the DS chain, every encoder phase and switch to the
     bit hal_daisy.cc expects, every LED to the 595 output and on through its resistor and H3 to the
     right button's LED pad, QF..QH spare and low, the power-up passes clearing random 595 contents,
     an unplugged faceplate reading "nothing pressed".
  E. GPIO setup: SR_CLK / SR_LOAD / SR_DOUT outputs at Speed::LOW, push-pull, no pull; SR_DIN and SHIFT
     inputs with the internal pull-up (RPU min/typ/max: SHIFT settles before main.cc reads it); CLK an
     EXTI input without pull, with its external pull-up on the board; MIDI_RX's AF and pull-up; the
     display's GPIO speeds.
  (The CV stage's output against the ADC pins' TT / FT voltage limits is test_cv.py's: not repeated here.)

Run:  cd side-fx/hardware/tests && python test_pins.py
"""
import os
import random
import re
import subprocess
import sys

import harness
import pins_fw as fw

ck = harness.Checks("pins")
circuit = harness.load("circuit")

# ================================================================== constants (with sources)
# --- Daisy Seed datasheet v1.0.5 (Electrosmith), "Pinout" page: header pin number -> name.
SEED_PIN_NAME = {1: "D0", 2: "D1", 3: "D2", 4: "D3", 5: "D4", 6: "D5", 7: "D6", 8: "D7", 9: "D8", 10: "D9",
                 11: "D10", 12: "D11", 13: "D12", 14: "D13", 15: "D14", 16: "AIN1", 17: "AIN2", 18: "AOUT1",
                 19: "AOUT2", 20: "AGND", 21: "3V3A", 22: "A0/D15", 23: "A1/D16", 24: "A2/D17", 25: "A3/D18",
                 26: "A4/D19", 27: "A5/D20", 28: "A6/D21", 29: "A7/D22", 30: "A8/D23", 31: "A9/D24",
                 32: "A10/D25", 33: "D26", 34: "D27", 35: "A11/D28", 36: "D29", 37: "D30", 38: "3V3D",
                 39: "VIN", 40: "DGND"}
# --- libDaisy v9.0.0 src/daisy_seed.h (namespace seed): libDaisy name -> STM32 port.
LIBDAISY_PORT = {"D0": "PB12", "D1": "PC11", "D2": "PC10", "D3": "PC9", "D4": "PC8", "D5": "PD2", "D6": "PC12",
                 "D7": "PG10", "D8": "PG11", "D9": "PB4", "D10": "PB5", "D11": "PB8", "D12": "PB9", "D13": "PB6",
                 "D14": "PB7", "D15": "PC0", "D16": "PA3", "D17": "PB1", "D18": "PA7", "D19": "PA6", "D20": "PC1",
                 "D21": "PC4", "D22": "PA5", "D23": "PA4", "D24": "PA1", "D25": "PA0", "D26": "PD11", "D27": "PG9",
                 "D28": "PA2", "D29": "PB14", "D30": "PB15"}
LIBDAISY_ALIAS = {"A0": "D15", "A1": "D16", "A2": "D17", "A3": "D18", "A4": "D19", "A5": "D20", "A6": "D21",
                  "A7": "D22", "A8": "D23", "A9": "D24", "A10": "D25", "A11": "D28"}
# --- STM32H750 datasheet DS12556 Rev 7 (March 2023), Tables 9 (port B) and 14 (port G), alternate functions.
STM32_AF = {("PG11", "SPI1_SCK"): 5, ("PB5", "SPI1_MOSI"): 5, ("PB4", "SPI1_MISO"): 5, ("PG10", "SPI1_NSS"): 5,
            ("PB7", "USART1_RX"): 7, ("PB6", "USART1_TX"): 7, ("PB14", "USART1_TX"): 4, ("PB15", "USART1_RX"): 4,
            ("PB6", "TIM4_CH1"): 2, ("PB7", "TIM4_CH2"): 2, ("PB8", "TIM4_CH3"): 2, ("PB9", "TIM4_CH4"): 2,
            ("PB14", "OTG_HS_DM"): 12, ("PB15", "OTG_HS_DP"): 12, ("PB12", "OTG_HS_ID"): 12}
# DS12556 Rev 7 Table 7 (pin definitions): ADC inputs {port: (ADCs, channel)}.
STM32_ADC = {"PC0": ((1, 2, 3), 10), "PA3": ((1, 2), 15), "PB1": ((1, 2), 5), "PA7": ((1, 2), 7),
             "PC1": ((1, 2, 3), 11)}
# DS12556 Rev 7 Table 58: weak pull-up RPU 30 / 40 / 50 kohm (min / typ / max, VIN = VSS); CIO 5 pF typ;
# input leakage (TT_xx, FT_xx at VIN <= VDD) +-250 nA max.
RPU = (30e3, 40e3, 50e3)
C_IO = 5e-12
I_LKG = 250e-9
# --- libDaisy v9.0.0 src/per/spi.cpp: the pins SpiHandle accepts for SPI1 and their AF.
LIBDAISY_SPI1 = {"sclk": {"PG11": 5, "PA5": 5}, "mosi": {"PB5": 5, "PA7": 5}, "miso": {"PB4": 5, "PA6": 5, "PG9": 5},
                 "nss": {"PG10": 5, "PA4": 5}}
# libDaisy v9.0.0 src/per/pwm.cpp: TIM4 channel pins (GetDefaultPin) and the AF it sets (GPIO_AF2_TIM4).
LIBDAISY_TIM4 = {1: "PB6", 2: "PB7", 3: "PB8", 4: "PB9"}
LIBDAISY_TIM4_AF = 2
# libDaisy v9.0.0 src/per/adc.cpp: ADC1 (hadc1.Instance = ADC1) and its pin -> channel table.
LIBDAISY_ADC1 = {"PA6": 3, "PC4": 4, "PB1": 5, "PA7": 7, "PC5": 8, "PB0": 9, "PC0": 10, "PC1": 11, "PC2": 12,
                 "PC3": 13, "PA2": 14, "PA3": 15, "PA0": 16, "PA1": 17, "PA4": 18, "PA5": 19}
LIBDAISY_ADC_INSTANCE = 1
# --- the Seed's own pins (not on its header): libDaisy v9.0.0 src/dev/sdram.cpp (FMC), daisy_seed.cpp (QSPI,
# SAI1, codec I2C2 / reset, LED PC7, test point PG14, board-version pins), USB FS (PA11/12), HSE/LSE, SWD.
SEED_INTERNAL = (
    {f"PE{n}" for n in (0, 1, 7, 8, 9, 10, 11, 12, 13, 14, 15)} | {f"PG{n}" for n in (0, 1, 2, 4, 5, 8, 15)} |
    {f"PD{n}" for n in (0, 1, 8, 9, 10, 14, 15)} | {f"PI{n}" for n in (0, 1, 2, 3, 4, 5, 6, 7, 9, 10)} |
    {f"PH{n}" for n in (2, 3, 5, 8, 9, 10, 11, 12, 13, 14, 15)} | {f"PF{n}" for n in (0, 1, 2, 3, 4, 5, 11, 12, 13, 14, 15)} |
    {"PF6", "PF7", "PF8", "PF9", "PF10", "PG6"} |                      # QSPI
    {"PE2", "PE3", "PE4", "PE5", "PE6"} | {"PH4", "PB11"} |             # SAI1, codec I2C2 / reset / de-emphasis
    {"PC7", "PG14", "PA11", "PA12", "PD3", "PD4", "PD5", "PH6"} |       # LED, test point, USB FS, version pins
    {"PH0", "PH1", "PC14", "PC15", "PA13", "PA14"})                     # HSE, LSE, SWD
# --- TI pinouts (function names as TI gives them, DIP-16):
# SN74HC165 (SCLS116): 1 SH/LD, 2 CLK, 3..6 E F G H, 7 /QH, 8 GND, 9 QH, 10 SER, 11..14 A B C D, 15 CLK INH, 16 VCC
HC165_D = ["11", "12", "13", "14", "3", "4", "5", "6"]       # A..H = D0..D7 (H shifts out first)
HC165_PIN = {"PL": "1", "CP": "2", "Q7": "9", "DS": "10", "CE": "15", "GND": "8", "VCC": "16"}
# SN74HC595 (SCLS041): 15 QA, 1..7 QB..QH, 8 GND, 9 QH', 10 /SRCLR, 11 SRCLK, 12 RCLK, 13 /OE, 14 SER, 16 VCC
HC595_Q = ["15", "1", "2", "3", "4", "5", "6", "7"]
HC595_PIN = {"SRCLR": "10", "SRCLK": "11", "RCLK": "12", "OE": "13", "SER": "14", "GND": "8", "VCC": "16"}
# --- PCB track capacitance per length for SHIFT's settling: ASSUMED 1 pF/cm (0.3 mm track over a pour on 1.6 mm FR4
#     is ~0.5-0.7 pF/cm; 1 pF/cm is the conservative round figure).
C_PER_M = 100e-12

R = harness.routed()
MB, FB = R.main, R.face


def port_of(name):
    """libDaisy name (D26, A0) -> STM32 port, through libDaisy's own aliases."""
    return LIBDAISY_PORT.get(LIBDAISY_ALIAS.get(name, name))


def seed_pin_of(name):
    """libDaisy name -> Daisy Seed header pin number (from the datasheet's names)."""
    d = LIBDAISY_ALIAS.get(name, name)
    for pin, nm in SEED_PIN_NAME.items():
        if d in nm.split("/"):
            return pin
    return None


U5 = MB.parts["U5"]


def u5_net(pin):
    p = U5["pads"].get(str(pin))
    return p.net if p else "<no pad>"


# ================================================================== A. check_pins.py
cp = os.path.join(harness.FIRMWARE, "tools", "check_pins.py")
r = subprocess.run([sys.executable, "-B", cp], capture_output=True, text=True, encoding="utf-8", errors="replace",
                   cwd=harness.FIRMWARE)
ck.check("A.check_pins.exit", r.returncode == 0, f"expected exit 0, got {r.returncode}")
lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
ck.check("A.check_pins.output", bool(lines), f"{len(lines)} lines")
cp_notes = []
for k, ln in enumerate(lines):
    if ln.startswith("note:"):
        # a note is a part check_pins.py skipped; B re-derives it (hal.h ports against libDaisy's constants).
        # Verifier fix (2026-11-13): this was check(True), a check that could not fail; the note is now checked
        # after B, against the B.port_* checks that stand in for it (they must exist and pass).
        cp_notes.append((k + 1, ln))
    else:
        ck.check(f"A.check_pins.line{k + 1}", not ln.startswith("MISMATCH") and "OK" in ln, ln)

# ================================================================== B. firmware pins
NET_OF_HAL = {"kPinClock": "CLK", "kPinMidiRx": "MIDI_RX", "kPinShift": "BTN_SHIFT", "kPinSrClk": "SR_CLK",
              "kPinSrLoad": "SR_LOAD", "kPinSrDout": "SR_DOUT", "kPinSrDin": "SR_DIN"}
NET_OF_DISPLAY = {"cs": "LCD_CS", "dc": "LCD_DC", "rst": "LCD_RST", "spi.sclk": "LCD_SCK", "spi.mosi": "LCD_MOSI",
                  "backlight": "LCD_BL"}
fw_pins = {}      # net -> libDaisy name
for c, net in NET_OF_HAL.items():
    ck.check(f"B.found.{c}", c in fw.HAL_PINS, f"hal_daisy.cc constexpr Pin {c}")
    if c in fw.HAL_PINS:
        fw_pins[net] = fw.HAL_PINS[c]
ck.check("B.found.kPinCv", len(fw.CV_PINS) == 4, f"expected 4 pins, got {fw.CV_PINS}")
for i, nm in enumerate(fw.CV_PINS):
    fw_pins[f"ADC_CV{i + 1}"] = nm
for o, net in NET_OF_DISPLAY.items():
    ck.check(f"B.found.display.{o}", o in fw.DISPLAY_PINS, f"display_daisy.cc {o}")
    if o in fw.DISPLAY_PINS:
        fw_pins[net] = fw.DISPLAY_PINS[o]
extra = set(fw.HAL_PINS) - set(NET_OF_HAL) - {"kPinCv"}
ck.check("B.no_unknown_pins.hal", not extra, f"unknown kPin constants {sorted(extra)}")
extra = set(fw.DISPLAY_PINS) - set(NET_OF_DISPLAY)
ck.check("B.no_unknown_pins.display", not extra, f"unknown display pins {sorted(extra)}")
all_seed_uses = re.findall(r"daisy::seed::(\w+)", fw.HAL + fw.DISPLAY + fw.MAIN)
ck.check("B.every_seed_pin_is_a_known_constant", len(all_seed_uses) == len(fw.HAL_PINS) + 4 + len(fw.DISPLAY_PINS),
         f"{len(all_seed_uses)} daisy::seed:: uses, {len(fw.HAL_PINS) + 4 + len(fw.DISPLAY_PINS)} known")

circ_seed = {}
for pin, (nm, net) in circuit.SEED.items():
    if not pin.startswith("J"):
        circ_seed[int(pin)] = (nm, net)
for pin, nm in SEED_PIN_NAME.items():
    cn = circ_seed.get(pin, ("<missing>", None))[0]
    ck.check(f"B.seed_name.pin{pin}", set(cn.split("/")) == set(nm.split("/")),
             f"Seed datasheet {nm}, circuit.SEED {cn}")

for net, nm in sorted(fw_pins.items()):
    pin = seed_pin_of(nm)
    ck.check(f"B.fw_vs_circuit.{net}", pin is not None and circ_seed.get(pin, (0, None))[1] == net,
             f"firmware {nm} = Seed pin {pin}; circuit.SEED has {circ_seed.get(pin, (0, None))[1]} there")
    ck.check(f"B.fw_vs_routed.{net}", pin is not None and u5_net(pin) == net,
             f"firmware {nm} = Seed pin {pin}; routed U5 pad {pin} is on {u5_net(pin) if pin else None}")
# two firmware nets on one Seed pin
pins_used = [seed_pin_of(nm) for nm in fw_pins.values()]
ck.check("B.one_net_per_pin", len(pins_used) == len(set(pins_used)), f"Seed pins {sorted(pins_used)}")
# every signal net on U5 (routed) is one the firmware drives or reads, and vice versa
POWER = {"GND", "3V3A", "3V3D", "+12V", "-12V"}
AUDIO = {"IN1", "IN2", "OUT1", "OUT2"}
u5_signals = {p.net for k, p in U5["pads"].items() if p.net and p.net not in POWER | AUDIO}
ck.check("B.u5_signals_all_used", u5_signals == set(fw_pins),
         f"routed U5 signal nets without firmware: {sorted(u5_signals - set(fw_pins))}; "
         f"firmware nets not on U5: {sorted(set(fw_pins) - u5_signals)}")
# all of U5's pads against circuit.SEED (two independent sources: generator netlist and routed copper)
for pin, (nm, net) in sorted(circuit.SEED.items(), key=lambda kv: (len(kv[0]), kv[0])):
    ck.check(f"B.circuit_vs_routed.U5.{pin}", u5_net(pin) == net, f"circuit.SEED {net}, routed {u5_net(pin)}")

# hal.h's pin table, display_daisy.cc's wiring table, hal_daisy.cc's "Pxn (Dn)" comments, against libDaisy
header = fw.HAL_H_RAW.split("#ifndef")[0]
rows = re.findall(r"^//\s+(D\d+)\s+(P[A-K]\d+)\s+(\w+)", header, re.M)
n_dpins = sum(1 for nm in fw_pins.values() if nm.startswith("D"))
ck.check("B.hal_h_table.rows", len(rows) == n_dpins, f"{len(rows)} Dn rows for the firmware's {n_dpins} Dn pins")
for nm, port, net in rows:
    ck.check(f"B.port_hal_h.{nm}", LIBDAISY_PORT.get(nm) == port, f"hal.h {port}, libDaisy {LIBDAISY_PORT.get(nm)}")
    ck.check(f"B.net_hal_h.{nm}", u5_net(seed_pin_of(nm)) == net,
             f"hal.h {net}, routed U5 pad {seed_pin_of(nm)} {u5_net(seed_pin_of(nm))}")
m = re.search(r"^//\s+A0\.\.A3\s+((?:P[A-K]\d+\s+){4})", header, re.M)
ck.check("B.hal_h_table.A0..A3", bool(m), "the A0..A3 row")
if m:
    for i, port in enumerate(m.group(1).split()):
        ck.check(f"B.port_hal_h.A{i}", port_of(f"A{i}") == port, f"hal.h {port}, libDaisy {port_of(f'A{i}')}")
drows = re.findall(r"^//\s+(D\d+)\s+(P[A-K]\d+)\s+(\w+)", fw.DISPLAY_RAW, re.M)
ck.check("B.display_table.rows", len(drows) == 6, f"{len(drows)} rows")
for nm, port, what in drows:
    ck.check(f"B.port_display_table.{nm}", LIBDAISY_PORT.get(nm) == port,
             f"display_daisy.cc {port}, libDaisy {LIBDAISY_PORT.get(nm)}")
for port, nm in re.findall(r"\b(P[A-K]\d+)\s*\((D\d+)", fw.HAL_RAW):
    ck.check(f"B.port_hal_comment.{nm}", LIBDAISY_PORT.get(nm) == port,
             f"hal_daisy.cc says {port} ({nm}), libDaisy {LIBDAISY_PORT.get(nm)}")
# check_pins.py's skipped part ("libDaisy not found: hal.h port names not checked") stands only if B re-derived it
_n_port = len(rows) + (4 if m else 0)
_failed_port = [f for f in ck.failed if f.startswith(("B.port_hal_h.", "B.hal_h_table."))]
for ln_no, ln in cp_notes:
    ck.check(f"A.check_pins.line{ln_no}", "hal.h port" in ln and _n_port == n_dpins + 4 and not _failed_port,
             f"{ln}: re-derived by {_n_port} B.port_hal_h checks (for {n_dpins} Dn pins + A0..A3), failed {_failed_port}")

# design.md's pin map table and its free list
design = harness.text("docs", "design.md")
sec = design.split("### Daisy Seed pin map")[1].split("\n## ")[0]


def pin_numbers(cell):
    out = []
    for tok in cell.split(","):
        tok = tok.strip()
        mm = re.match(r"^(\d+)\s*[–-]\s*(\d+)$", tok)
        if mm:
            out += list(range(int(mm.group(1)), int(mm.group(2)) + 1))
        elif tok.isdigit():
            out.append(int(tok))
    return out


doc_free = None
for ln in sec.splitlines():
    cells = [c.strip() for c in ln.strip().strip("|").split("|")]
    if len(cells) < 4 or not re.match(r"^\d", cells[0]):
        continue
    pins = pin_numbers(cells[0])
    if cells[2] in ("—", "-"):
        doc_free = pins
        continue
    nets = []
    for tok in cells[2].split(","):
        tok = tok.strip()
        mm = re.match(r"^(\w+?)(\d+)\.\.(\w+?)(\d+)$", tok)
        nets += [f"{mm.group(1)}{k}" for k in range(int(mm.group(2)), int(mm.group(4)) + 1)] if mm else [tok]
    if len(nets) == 1 and len(pins) > 1:
        nets = nets * len(pins)
    ck.check(f"B.design_md_table.{cells[0]}.count", len(nets) == len(pins), f"{len(pins)} pins, nets {nets}")
    for p, n in zip(pins, nets):
        ck.check(f"B.design_md_table.pin{p}", u5_net(p) == n, f"design.md {n}, routed U5 {u5_net(p)}")
ck.check("B.design_md_free.found", doc_free is not None, "the free-pins row")
routed_free = sorted(int(k) for k, p in U5["pads"].items() if k.isdigit() and not p.net and int(k) not in (16, 17, 18, 19))
ck.check("B.design_md_free.matches_routed", sorted(doc_free or []) == routed_free,
         f"design.md free {sorted(doc_free or [])}, routed U5 pads without a net (audio 16-19 aside) {routed_free}")
fw_names = set(all_seed_uses)
for p in routed_free:
    names = set(SEED_PIN_NAME[p].split("/"))
    ck.check(f"B.free_pin_unused_by_firmware.pin{p}", not (names & fw_names), f"{SEED_PIN_NAME[p]}")

# ================================================================== C. peripherals
sclk, mosi = fw.DISPLAY_PINS.get("spi.sclk"), fw.DISPLAY_PINS.get("spi.mosi")
ck.check("C.spi1.periph", re.search(r"Peripheral::SPI_1\b", fw.DISPLAY) is not None, "SpiHandle on SPI_1")
for role, nm, fn in (("sclk", sclk, "SPI1_SCK"), ("mosi", mosi, "SPI1_MOSI")):
    port = port_of(nm) if nm else None
    lib_af = LIBDAISY_SPI1[role].get(port)
    ck.check(f"C.spi1.{role}.libdaisy_accepts", lib_af is not None, f"{nm} = {port}; libDaisy SPI1 {role} pins "
             f"{sorted(LIBDAISY_SPI1[role])}")
    ck.check(f"C.spi1.{role}.af", lib_af is not None and STM32_AF.get((port, fn)) == lib_af,
             f"libDaisy AF{lib_af}, STM32H750 {fn} on {port} = AF{STM32_AF.get((port, fn))}")
ck.check("C.spi1.tx_only", "TWO_LINES_TX_ONLY" in fw.DISPLAY, "Direction::TWO_LINES_TX_ONLY (MISO pin not set up)")
ck.check("C.spi1.miso_and_nss_unset", {"miso", "nss"} <= set(fw.EMPTY_SPI_PINS) and "NSS::SOFT" in fw.DISPLAY,
         f"pin_config set to Pin(): {fw.EMPTY_SPI_PINS}; NSS::SOFT {'NSS::SOFT' in fw.DISPLAY}")
# USART1 RX
midi = fw.function_body(fw.HAL, "InitMidi")
g = fw.hal_gpio_struct(midi)
mm = re.search(r"GPIO_AF(\d+)_(\w+)", g.get("Alternate", ""))
rx_port = port_of(fw.HAL_PINS.get("kPinMidiRx", ""))
ck.check("C.usart1.rx_af", bool(mm) and mm.group(2) == "USART1" and int(mm.group(1)) == STM32_AF.get((rx_port, "USART1_RX")),
         f"firmware {g.get('Alternate')}, STM32H750 USART1_RX on {rx_port} = AF{STM32_AF.get((rx_port, 'USART1_RX'))}")
ck.check("C.usart1.rx_pin_only", "kPinMidiRx" in g.get("Pin", "") and midi.count("HAL_GPIO_Init") == 1,
         f"gpio.Pin = {g.get('Pin')}, {midi.count('HAL_GPIO_Init')} HAL_GPIO_Init calls in InitMidi")
cr1 = re.findall(r"USART1->CR1\s*=\s*([^;]+);", midi or "")
ck.check("C.usart1.receive_only", cr1 and "USART_CR1_RE" in cr1[-1] and "USART_CR1_TE" not in " ".join(cr1),
         f"CR1 writes {cr1}")
ck.check("C.usart1.no_libdaisy_uart", re.search(r"UartHandler|MidiUartHandler|UART_1\b|USART_1\b", fw.HAL + fw.MAIN) is None,
         "nothing else opens USART1 through libDaisy")
rst_port = port_of(fw.DISPLAY_PINS.get("rst", ""))
inits = fw.gpio_inits(fw.DISPLAY)
ck.check("C.usart1_tx_pin_is_rst_gpio", rst_port == "PB6" and inits.get("rst", (0, ""))[1] == "OUTPUT",
         f"RST on {rst_port} ({'USART1_TX AF7' if rst_port == 'PB6' else ''}) as GPIO {inits.get('rst')}")
# TIM4 CH4 backlight
bl_port = port_of(fw.DISPLAY_PINS.get("backlight", ""))
ck.check("C.tim4.periph_channel", "Peripheral::TIM_4" in fw.DISPLAY and re.search(r"Channel4\(\)\.Init", fw.DISPLAY) is not None,
         "PWMHandle TIM_4, Channel4().Init")
ck.check("C.tim4.ch4_pin", bl_port == LIBDAISY_TIM4[4] and STM32_AF.get((bl_port, "TIM4_CH4")) == LIBDAISY_TIM4_AF,
         f"backlight {bl_port}; libDaisy TIM4 CH4 {LIBDAISY_TIM4[4]} AF{LIBDAISY_TIM4_AF}, STM32H750 "
         f"AF{STM32_AF.get((bl_port, 'TIM4_CH4'))}")
other_ch = re.findall(r"Channel([123])\(\)\.Init", fw.DISPLAY + fw.HAL)
ck.check("C.tim4.no_other_channel_pins", not other_ch,
         f"TIM4 CH1..3 would take {[LIBDAISY_TIM4[int(c)] for c in other_ch]} (RST, MIDI_RX, DC)")
# ADC
for i, nm in enumerate(fw.CV_PINS):
    port = port_of(nm)
    adcs, ch = STM32_ADC.get(port, ((), None))
    ck.check(f"C.adc.A{i}.stm32", LIBDAISY_ADC_INSTANCE in adcs, f"{nm} = {port}: ADC{''.join(map(str, adcs))}_INP{ch}")
    ck.check(f"C.adc.A{i}.libdaisy_channel", LIBDAISY_ADC1.get(port) == ch,
             f"libDaisy ADC1 table channel {LIBDAISY_ADC1.get(port)}, datasheet INP{ch}")
cv_ports = [port_of(nm) for nm in fw.CV_PINS]
ck.check("C.adc.distinct", len(set(cv_ports)) == 4, f"{cv_ports}")
ck.check("C.adc.init_single", "InitSingle" in fw.HAL and "InitMux" not in fw.HAL, "single-ended channels, no mux")
# collisions with the Seed's own pins
for net, nm in sorted(fw_pins.items()):
    port = port_of(nm)
    ck.check(f"C.not_seed_internal.{net}", port not in SEED_INTERNAL, f"{nm} = {port}")
# USB HS on D29 / D30 (the chain's SR_DOUT / SR_DIN)
ck.check("C.usb_hs_not_started", re.search(r"UsbHandle|FS_EXTERNAL|StartLog|usb_handle", fw.HAL + fw.MAIN + fw.DISPLAY) is None,
         f"D29/D30 = {port_of('D29')}/{port_of('D30')} (OTG_HS_DM/DP AF12) stay GPIO")
# EXTI: one interrupt pin
it_modes = re.findall(r"GPIO_MODE_IT_\w+", fw.HAL + fw.DISPLAY)
clk_port = port_of(fw.HAL_PINS.get("kPinClock", ""))
ck.check("C.exti.one_user", len(it_modes) == 1 and clk_port and 10 <= int(clk_port[2:]) <= 15
         and "EXTI15_10_IRQn" in fw.HAL, f"{it_modes} on {clk_port}: line {clk_port[2:] if clk_port else '?'} -> EXTI15_10")
# timers: TIM2 libDaisy's tick, TIM3 controls, TIM4 backlight, TIM5 microseconds
tims = re.findall(r"Peripheral::TIM_(\d)", fw.HAL + fw.DISPLAY)
ck.check("C.timers.one_owner_each", sorted(tims) == ["3", "4", "5"], f"timers opened: {sorted(tims)} (TIM2 is libDaisy's)")

# ================================================================== D. the chain's bit order (routed boards)
def face_parts_with(pin, net):
    return [ref for ref, p in FB.parts.items() if pin in p["pads"] and p["pads"][pin].net == net]


# header map main net <-> faceplate net, from the routed boards (same pin numbers, same spot)
hdr = {}
for ref in [r_ for r_ in MB.parts if re.match(r"^H\d+$", r_)]:
    fref = circuit.fb_ref(ref)
    if fref not in FB.parts:
        ck.check(f"D.header.{ref}", False, f"no {fref} on the routed faceplate")
        continue
    for k, p in MB.parts[ref]["pads"].items():
        q = FB.parts[fref]["pads"].get(k)
        ok = q is not None and abs(p.x - q.x) < 0.05 and abs(p.y - q.y) < 0.05
        ck.check(f"D.header.{ref}.{k}.aligned", ok, f"main ({p.x:.2f}, {p.y:.2f}), face "
                 f"({q.x:.2f}, {q.y:.2f})" if q else "missing pin")
        if q is not None and p.net:
            hdr[p.net] = q.net
to_face = hdr.get
din_net = u5_net(seed_pin_of(fw.HAL_PINS["kPinSrDin"]))
clk_net = u5_net(seed_pin_of(fw.HAL_PINS["kPinSrClk"]))
load_net = u5_net(seed_pin_of(fw.HAL_PINS["kPinSrLoad"]))
dout_net = u5_net(seed_pin_of(fw.HAL_PINS["kPinSrDout"]))
first = face_parts_with(HC165_PIN["Q7"], to_face(din_net))
ck.check("D.first_165.found", len(first) == 1, f"{din_net} -> {to_face(din_net)} on Q7 (pin 9) of {first}")
A_ = first[0] if first else None
ds_net = FB.parts[A_]["pads"][HC165_PIN["DS"]].net if A_ else None
second = [x for x in face_parts_with(HC165_PIN["Q7"], ds_net) if x != A_] if ds_net else []
ck.check("D.second_165.found", len(second) == 1, f"{A_} DS = {ds_net}, driven by Q7 of {second}")
B_ = second[0] if second else None
if B_:
    ck.check("D.second_165.ds_fixed", FB.parts[B_]["pads"][HC165_PIN["DS"]].net in ("GND_D_F", "3V3D_F"),
             f"{B_} DS on {FB.parts[B_]['pads'][HC165_PIN['DS']].net}")
for u in filter(None, (A_, B_)):
    pads = FB.parts[u]["pads"]
    ck.check(f"D.165_control.{u}", pads[HC165_PIN["PL"]].net == to_face(load_net) and pads[HC165_PIN["CP"]].net == to_face(clk_net)
             and pads[HC165_PIN["CE"]].net == "GND_D_F" and pads[HC165_PIN["GND"]].net == "GND_D_F"
             and pads[HC165_PIN["VCC"]].net == "3V3D_F",
             f"/PL {pads['1'].net}, CP {pads['2'].net}, CE {pads['15'].net}, GND {pads['8'].net}, VCC {pads['16'].net}; "
             f"expected {to_face(load_net)}, {to_face(clk_net)}, GND_D_F, GND_D_F, 3V3D_F")
U3 = [ref for ref, p in MB.parts.items() if p["pads"].get(HC595_PIN["SER"]) is not None
      and p["pads"][HC595_PIN["SER"]].net == dout_net]
ck.check("D.595.found", len(U3) == 1, f"{dout_net} on SER (pin 14) of {U3}")
U3 = U3[0] if U3 else None
if U3:
    pads = MB.parts[U3]["pads"]
    ck.check("D.595.control", pads[HC595_PIN["SRCLK"]].net == clk_net and pads[HC595_PIN["RCLK"]].net == load_net
             and pads[HC595_PIN["SRCLR"]].net == "3V3D" and pads[HC595_PIN["OE"]].net == "GND"
             and pads[HC595_PIN["VCC"]].net == "3V3D" and pads[HC595_PIN["GND"]].net == "GND",
             f"SRCLK {pads['11'].net}, RCLK {pads['12'].net}, /SRCLR {pads['10'].net}, /OE {pads['13'].net}")

# what each 165 input is on the faceplate: (kind, index, phase/label)
def input_meaning(net):
    for ref, p in FB.parts.items():
        for k, pad in p["pads"].items():
            if pad.net != net:
                continue
            if ref.startswith("ENC") and k in ("A", "B"):
                return ("enc", ref, k)
            if ref.startswith("ENC") and k == "S2":
                return ("sw", dict(circuit.ENCODERS)[ref], None)
            if ref.startswith("SW") and k in ("3", "4"):
                return ("sw", circuit.LED_WORD[ref], None)
    return None


pre, loop, nbits = fw.chain_ops()
ck.check("D.sequence.parsed", bool(pre) and bool(loop) and nbits == 16, f"pre {pre}, loop {loop}, bits {nbits}")
enc_a = fw.int_array(fw.HAL, "kEncoderBitA")
enc_b = fw.int_array(fw.HAL, "kEncoderBitB")
sw_bit = fw.int_array(fw.HAL, "kSwitchBit")
led_out = fw.int_array(fw.HAL, "kLedOutput")
switches = [v for v in fw.enum_values(fw.HAL_H, "Switch") if v != "NUM_SWITCHES"]
leds = [v for v in fw.enum_values(fw.HAL_H, "Led") if v != "NUM_LEDS"]
enc_refs = [ref for ref, _ in circuit.ENCODERS]
# encoder index k: hal.h "K1 at the top" -> circuit.ENCODERS label K(k+1); check K1..K4 run top to bottom
ys = [circuit.PLACEMENT[ref][1] for ref in enc_refs]
ck.check("D.encoders_top_to_bottom", ys == sorted(ys, reverse=True), f"ENC1..4 y {ys} (front view)")
xs = [circuit.PLACEMENT[ref][0] for ref, lbl, _ in circuit.BUTTONS if lbl in ("PITCH", "DELAY", "TEXTURE", "REVERB")]
ck.check("D.sends_left_to_right", xs == sorted(xs), f"PITCH, DELAY, TEXTURE, REVERB x {xs} (front view)")

if A_ and B_ and pre:
    found_bits = {}
    for chip, base_name in ((A_, "first"), (B_, "second")):
        for n, pin in enumerate(HC165_D):
            net = FB.parts[chip]["pads"][pin].net
            d1, d2 = [1] * 8, [1] * 8
            (d1 if chip == A_ else d2)[n] = 0
            raw, _ = fw.run_chain(pre, loop, nbits, d1, d2, 0)
            zeros = [b for b in range(16) if not (raw >> b) & 1]
            meaning = input_meaning(net)
            ck.check(f"D.input.{chip}.D{n}", len(zeros) == 1 and meaning is not None,
                     f"{net} ({meaning}) reads as raw bit(s) {zeros}")
            if len(zeros) == 1 and meaning:
                found_bits[meaning] = zeros[0]
    for k, ref in enumerate(enc_refs):
        for ph, table in (("A", enc_a), ("B", enc_b)):
            want = found_bits.get(("enc", ref, ph))
            got = table[k] if table and k < len(table) else None
            ck.check(f"D.encoder_bit.{ref}.{ph}", want is not None and got == want,
                     f"firmware kEncoderBit{ph}[{k}] = {got}; the chain reads {ref} {ph} at bit {want}")
    for s, name in enumerate(switches):
        word = name[len("SWITCH_"):]
        got = sw_bit[s] if sw_bit and s < len(sw_bit) else None
        if word == "SHIFT":
            ck.check("D.switch_bit.SHIFT", got == "kNotOnChain", f"kSwitchBit[SHIFT] = {got}")
            continue
        want = found_bits.get(("sw", word, None))
        ck.check(f"D.switch_bit.{word}", want is not None and got == want,
                 f"firmware kSwitchBit[{name}] = {got}; the chain reads {word} at bit {want}")
    used = sorted(found_bits.values())
    ck.check("D.all_16_bits_used_once", used == list(range(16)), f"{used}")
    # unplugged faceplate: SR_DIN floats to its pull-up
    raw, _ = fw.run_chain(pre, loop, nbits, [1] * 8, [1] * 8, 0, faceplate=False)
    pressed = (~raw) & 0xffff
    ck.check("D.unplugged_reads_released", pressed == 0, f"pressed bits 0x{pressed:04x} with SR_DIN at its pull-up")

# SHIFT on its own pin: the button's switch net through H3 to the firmware's pin
shift_sw = [ref for ref, lbl, _ in circuit.BUTTONS if lbl == "SHIFT"]
if shift_sw:
    sn = FB.parts[shift_sw[0]]["pads"]["3"].net
    mbn = [m_ for m_, f_ in hdr.items() if f_ == sn]
    ck.check("D.shift_pin", mbn == [u5_net(seed_pin_of(fw.HAL_PINS["kPinShift"]))],
             f"{shift_sw[0]} switch {sn} <- header {mbn}; kPinShift = {fw.HAL_PINS['kPinShift']} on "
             f"{u5_net(seed_pin_of(fw.HAL_PINS['kPinShift']))}")


# LEDs: each Led enum lit alone -> which 595 output -> resistor -> header -> which button's LED anode (pad 5)
def through_resistor(net):
    out = []
    for ref, p in MB.parts.items():
        if ref.startswith("R") and len(p["pads"]) == 2:
            ns = [pad.net for pad in p["pads"].values()]
            if net in ns:
                out.append((ref, [n for n in ns if n != net][0]))
    return out


if U3 and pre:
    for i, name in enumerate(leds):
        word = name[len("LED_"):]
        u595 = fw.HC595()
        w = fw.led_word(1 << i, led_out, len(leds))
        fw.run_chain(pre, loop, nbits, [1] * 8, [1] * 8, w, u595=u595)     # shifts the byte in
        fw.run_chain(pre, loop, nbits, [1] * 8, [1] * 8, 0, u595=u595)     # the next pass latches it
        high = [q for q in range(8) if u595.out[q]]
        ok = len(high) == 1
        dest = None
        if ok:
            qnet = MB.parts[U3]["pads"][HC595_Q[high[0]]].net
            rs = through_resistor(qnet)
            if len(rs) == 1:
                fnet = to_face(rs[0][1])
                sws = face_parts_with("5", fnet) if fnet else []
                dest = (qnet, rs[0][0], rs[0][1], fnet, sws)
        lbl = circuit.LED_WORD.get(dest[4][0]) if dest and len(dest[4]) == 1 else None
        ck.check(f"D.led.{word}", ok and lbl == word,
                 f"Led {name} lights Q{'ABCDEFGH'[high[0]] if ok else '?'} {high}; path {dest}; button {lbl}")
    # spare outputs: QF..QH have no copper and stay low with every LED on
    u595 = fw.HC595()
    fw.run_chain(pre, loop, nbits, [1] * 8, [1] * 8, fw.led_word(0xff, led_out, len(leds)), u595=u595)
    fw.run_chain(pre, loop, nbits, [1] * 8, [1] * 8, 0, u595=u595)
    lit = [q for q in range(8) if u595.out[q]]
    spare = [q for q in range(8) if not MB.parts[U3]["pads"][HC595_Q[q]].net]
    ck.check("D.595_spare_outputs_unrouted", spare == [5, 6, 7], f"outputs without a net: {['Q' + 'ABCDEFGH'[q] for q in spare]}")
    ck.check("D.595_spare_outputs_low", not (set(lit) & set(spare)) and len(lit) == len(leds),
             f"all LEDs on lights {['Q' + 'ABCDEFGH'[q] for q in lit]}")
    # power-up: InitChain's two passes with no LEDs clear whatever the 595 woke up with
    init = fw.function_body(fw.HAL, "InitChain")
    passes = len(re.findall(r"ShiftChain\(\s*0\s*\)", init or ""))
    rng = random.Random(1)
    ok = True
    for _ in range(50):
        u595 = fw.HC595()
        u595.sr = [rng.randint(0, 1) for _ in range(8)]
        u595.out = [rng.randint(0, 1) for _ in range(8)]
        for _p in range(passes):
            fw.run_chain(pre, loop, nbits, [1] * 8, [1] * 8, 0, u595=u595)
        ok = ok and not any(u595.out)
    ck.check("D.powerup_clears_595", ok and passes >= 2, f"{passes} ShiftChain(0) passes in InitChain; outputs cleared")

# ================================================================== E. GPIO setup
hal_inits = fw.gpio_inits(fw.HAL)
for obj, const in (("sr_clk", "kPinSrClk"), ("sr_load", "kPinSrLoad"), ("sr_dout", "kPinSrDout")):
    got = hal_inits.get(obj)
    ck.check(f"E.output_low_speed.{obj}", got is not None and got[0] == const and got[1] == "OUTPUT"
             and got[2] == "NOPULL" and got[3] == "LOW", f"{got} (routing audit item 7: Speed::LOW)")
for obj, const in (("sr_din", "kPinSrDin"), ("shift_in", "kPinShift")):
    got = hal_inits.get(obj)
    ck.check(f"E.input_pullup.{obj}", got is not None and got[0] == const and got[1] == "INPUT" and got[2] == "PULLUP",
             f"{got}")
# SHIFT: the pull-up charges the line (two boards' tracks, the header, the pin) well before main.cc reads it
st_m, st_f = MB.net_stats().get("BTN_SHIFT", {}), FB.net_stats().get("BTN_SHIFT_F", {})
c_shift = (st_m.get("length", 0) + st_f.get("length", 0)) * 1e-3 * C_PER_M + 2 * C_IO
tau = RPU[2] * c_shift
dly = re.search(r"System::Delay\((\d+)\)", fw.function_body(fw.HAL, "Init") or "")
ck.within("E.shift_settles_before_read", 7 * tau, 0, int(dly.group(1)) * 1e-3 if dly else 0, " s",
          f"7 tau at RPU max {RPU[2] / 1e3:.0f}k and {c_shift * 1e12:.0f} pF; Init waits {dly.group(1) if dly else '?'} ms")
ck.within("E.shift_leakage_drop", I_LKG * RPU[2], 0, 0.1 * 3.3, " V", "input leakage max x RPU max, against 10 % of VDD")
# CLK: EXTI input, no internal pull, the board's own pull-up from 3V3D
clk = fw.hal_gpio_struct(fw.function_body(fw.HAL, "InitClock"))
ck.check("E.clk_input", clk.get("Mode") == "GPIO_MODE_IT_FALLING" and clk.get("Pull") == "GPIO_NOPULL",
         f"{clk.get('Mode')}, {clk.get('Pull')}")
clk_net_name = u5_net(seed_pin_of(fw.HAL_PINS["kPinClock"]))
pu = [ref for ref, p in MB.parts.items() if ref.startswith("R") and sorted(pd.net for pd in p["pads"].values()) == sorted([clk_net_name, "3V3D"])]
ck.check("E.clk_external_pullup", len(pu) == 1, f"resistors {clk_net_name}-3V3D on the routed main board: {pu}")
# MIDI_RX: AF push-pull (input in AF mode), pull-up, the opto's own pull-up on the board
mid = fw.hal_gpio_struct(midi)
ck.check("E.midi_rx", mid.get("Mode") == "GPIO_MODE_AF_PP" and mid.get("Pull") == "GPIO_PULLUP",
         f"{mid.get('Mode')}, {mid.get('Pull')}")
mrx = u5_net(seed_pin_of(fw.HAL_PINS["kPinMidiRx"]))
pu = [ref for ref, p in MB.parts.items() if ref.startswith("R") and sorted(pd.net for pd in p["pads"].values()) == sorted([mrx, "3V3D"])]
ck.check("E.midi_rx_external_pullup", len(pu) == 1, f"resistors {mrx}-3V3D: {pu}")
# display GPIOs
for obj, mode in (("cs", "OUTPUT"), ("dc", "OUTPUT"), ("rst", "OUTPUT")):
    got = inits.get(obj)
    ck.check(f"E.display_gpio.{obj}", got is not None and got[1] == mode and got[2] == "NOPULL", f"{got}")
# outputs start at their idle levels: SR_LOAD high (no 165 load / 595 latch until a scan), SR_CLK low
ic = fw.function_body(fw.HAL, "InitChain") or ""
ck.check("E.idle_levels", re.search(r"sr_load\.Write\(\s*true", ic) is not None and re.search(r"sr_clk\.Write\(\s*false", ic) is not None,
         "sr_load.Write(true), sr_clk.Write(false) right after their Init")

# F. (pin voltage) is left to test_cv.py, which checks the CV stage's worst output against PB1 / PA7's TT limit
#    (D.tt_overvoltage_*) and the injection rows with the worst-case parts; it is not repeated here.

ck.done()
