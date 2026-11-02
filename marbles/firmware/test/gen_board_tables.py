"""Writes board_tables.h from marbles/hardware/tools/circuit.py.

The host tests compare the firmware's LED, button and DAC tables with these,
and the board model (hal_fake.cc) is built from the resistor values here, so
a change to the netlist that the firmware does not follow fails a test.
Everything is read from the parts' pins, not from circuit.py's summary
tables. It also checks against the netlist the order of hal.h's Pot and
CvInput enums and the Seed pin constants in src/hal_daisy.cc, and exits
non-zero if anything disagrees.
Usage: python3 gen_board_tables.py [output]
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(FIRMWARE, "..", "hardware", "tools"))
import circuit  # noqa: E402

# 74HC595 pins: QA..QH, SER, QH'
HC595_Q = {"15": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}
# 74HC4051 pin -> channel Y0..Y7
HC4051_Y = {"13": 0, "14": 1, "15": 2, "12": 3, "1": 4, "5": 5, "2": 6, "4": 7}
# Marbles' Led enum order -> circuit.py LED refs
LED_ORDER = ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]
# DAC channels in Marbles' order (cv_output index): Y, X1, X2, X3
DAC_ORDER = ["Y", "X1", "X2", "X3"]
OUTPUT_LED = {"Y": "D14", "X1": "D15", "X2": "D16", "X3": "D17"}
# Marbles' Switch enum order -> circuit.py button nets
SWITCH_ORDER = ["T_DEJAVU", "T_MODE", "T_RANGE", "X_DEJAVU", "X_MODE", "X_RANGE", "X_EXT"]
# hal.h enum names -> circuit.py nets
POT_NET = {
    "POT_T_RATE": "POT_T_RATE_F", "POT_T_JITTER": "POT_T_JITTER_F",
    "POT_DEJA_VU": "POT_DEJAVU_F", "POT_T_BIAS": "POT_T_BIAS_F",
    "POT_X_STEPS": "POT_X_STEPS_F", "POT_DEJA_VU_LENGTH": "POT_LENGTH_F",
    "POT_X_BIAS": "POT_X_BIAS_F", "POT_X_SPREAD": "POT_X_SPREAD_F",
}
CV_NET = {
    "CV_T_RATE": "ADC_T_RATE", "CV_T_BIAS": "ADC_T_BIAS", "CV_T_JITTER": "ADC_T_JITTER",
    "CV_DEJA_VU": "ADC_DEJAVU", "CV_X_SPREAD": "ADC_X_SPREAD", "CV_X_BIAS": "ADC_X_BIAS",
    "CV_X_STEPS": "ADC_X_STEPS",
}


def ohms(value):
    """'100k' -> 100000, '2k2' -> 2200, '470' -> 470."""
    m = re.fullmatch(r"(\d+)([kM]?)(\d*)", value)
    whole, unit, frac = m.groups()
    scale = {"": 1, "k": 1e3, "M": 1e6}[unit]
    return float(whole + ("." + frac if frac else "")) * scale


def enum(source, name):
    body = re.search(r"enum " + name + r" \{([^}]*)\}", source).group(1)
    names = [n.strip().split("=")[0].strip() for n in body.split(",")]
    return [n for n in names if n and not n.endswith("_LAST")]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build", "board_tables.h")
    problems = []
    fb = {p.ref: p for p in circuit.faceplate_parts()}
    mb = {p.ref: p for p in circuit.main_board_parts()}

    # The 74HC595 chain: the one fed by MOSI first, then the one its QH' feeds.
    first = [r for r in ("U9", "U10") if fb[r].nets["14"] == "MOSI_F"]
    if len(first) != 1:
        problems.append("no single 74HC595 on MOSI_F")
        first = ["U9"]
    second = [r for r in ("U9", "U10") if r != first[0]][0]
    if fb[second].nets["14"] != fb[first[0]].nets["9"]:
        problems.append(f"{second}.SER is not {first[0]}.QH'")
    chain = {first[0]: 0, second: 8}
    line_bit = {}
    for ref, base in chain.items():
        for pin, q in HC595_Q.items():
            if pin in fb[ref].nets:
                line_bit[fb[ref].nets[pin]] = base + q

    def led_lines(ref):
        # L_<ref>_R / L_<ref>_G: the 595 lines of that LED.
        red = line_bit.get(f"L_{ref}_R", -1)
        green = line_bit.get(f"L_{ref}_G", -1)
        return red, green
    red_bits = [led_lines(r)[0] for r in LED_ORDER]
    green_bits = [led_lines(r)[1] for r in LED_ORDER]
    output_bits = [led_lines(OUTPUT_LED[c])[1] for c in DAC_ORDER]
    if -1 in green_bits or -1 in output_bits:
        problems.append("an LED with no green line")

    hc165 = fb["U11"].nets
    inputs = []
    for sw in SWITCH_ORDER:
        pin = [pid for pid, n in hc165.items() if n == f"BTN_{sw}_F"]
        inputs.append(circuit.HC165_INPUTS.index(pin[0]) if pin else -1)

    # DAC slots from the MCP4922 pins: U on CS1 = slots 0/1, VOUTA = A.
    slot_of_net = {}
    for ref in ("U7", "U8"):
        cs = mb[ref].nets["3"]
        chip = {"DAC_CS1": 0, "DAC_CS2": 1}[cs]
        slot_of_net[mb[ref].nets["14"]] = 2 * chip
        slot_of_net[mb[ref].nets["10"]] = 2 * chip + 1
    dac_slots = [slot_of_net.get(f"DAC_{c}", -1) for c in DAC_ORDER]

    # hal.h's enum orders against the netlist.
    hal_h = open(os.path.join(FIRMWARE, "src", "hal.h"), encoding="utf-8").read()
    channel_of_net = {fb["U1"].nets[pin]: ch for pin, ch in HC4051_Y.items()}
    for i, name in enumerate(enum(hal_h, "Pot")):
        ch = channel_of_net.get(POT_NET.get(name))
        if ch != i:
            problems.append(f"hal::Pot {name} = {i}, but the 74HC4051 has it on Y{ch}")
    cv_names = enum(hal_h, "CvInput")

    # Seed pins: circuit.py's SEED map against hal_daisy.cc's constants.
    seed_names = {net: set(name.split("/")) for name, net in circuit.SEED.values() if net}
    hal_src = open(os.path.join(FIRMWARE, "src", "hal_daisy.cc"), encoding="utf-8").read()
    m = re.search(r"kCvPins\[CV_INPUT_LAST\] = \{([^}]*)\}", hal_src)
    cv_pins = re.findall(r"seed::(\w+)", m.group(1))
    if len(cv_pins) != len(cv_names):
        problems.append(f"kCvPins has {len(cv_pins)} pins for {len(cv_names)} inputs")
    for name, pin in zip(cv_names, cv_pins):
        if pin not in seed_names[CV_NET[name]]:
            problems.append(f"kCvPins[{name}] is {pin}, circuit.py puts {CV_NET[name]} on "
                            f"{seed_names[CV_NET[name]]}")
    for const, net in [("kMuxOut", "MUX_OUT"), ("kMuxS0", "MUX_S0"), ("kMuxS1", "MUX_S1"),
                       ("kMuxS2", "MUX_S2"), ("kClockT", "T_CLK"), ("kClockX", "X_CLK"),
                       ("kGate1", "GATE_T1"), ("kGate2", "GATE_T2"), ("kGate3", "GATE_T3"),
                       ("kProbe", "PROBE"), ("kDacCs1", "DAC_CS1"), ("kSpiSck", "SPI_SCK"),
                       ("kSpiMiso", "SPI_MISO"), ("kSpiMosi", "SPI_MOSI"), ("kDacCs2", "DAC_CS2"),
                       ("kDacLdac", "DAC_LDAC"), ("kLedLatch", "LED_LATCH"),
                       ("kButtonLoad", "BTN_LOAD")]:
        m = re.search(r"constexpr Pin " + const + r" = seed::(\w+);", hal_src)
        if not m or m.group(1) not in seed_names[net]:
            problems.append(f"{const} is {m.group(1) if m else '?'}, circuit.py puts {net} "
                            f"on {seed_names[net]}")
    # The mux address lines: S0 is libDaisy's mux_0 (the LSB).
    for pin, net in (("11", "MUX_S0_F"), ("10", "MUX_S1_F"), ("9", "MUX_S2_F")):
        if fb["U1"].nets[pin] != net:
            problems.append(f"74HC4051 pin {pin} is not {net}")

    # Stage values, from the parts on each net.
    def resistor(a, b):
        found = [p for p in mb.values() if p.kind == "R" and {p.nets["1"], p.nets["2"]} == {a, b}]
        if len(found) != 1:
            problems.append(f"no single resistor between {a} and {b}")
            return 0.0
        return ohms(found[0].value)
    cv_rin = {resistor(f"CV_{n}", f"IN_{n}") for n, _, _, _ in circuit.CV_CHANNELS}
    cv_rf = {resistor(f"IN_{n}", f"OA_{n}") for n, _, _, _ in circuit.CV_CHANNELS}
    dac_rin = {resistor(f"DAC_{c}", f"IN_{c}") for c in DAC_ORDER}
    dac_rref = {resistor("NEG_REF", f"IN_{c}") for c in DAC_ORDER}
    dac_rf = {resistor(f"IN_{c}", f"OA_{c}") for c in DAC_ORDER}
    dac_rout = {resistor(f"OA_{c}", c) for c in DAC_ORDER}
    for label, values in (("CV Rin", cv_rin), ("CV Rf", cv_rf), ("DAC Rin", dac_rin),
                          ("DAC Rref", dac_rref), ("DAC Rf", dac_rf), ("output R", dac_rout)):
        if len(values) != 1:
            problems.append(f"the {label} differs between channels: {sorted(values)}")
    bias_top = resistor("3V3A", "BIAS")
    bias_bottom = resistor("BIAS", "GND")
    inverter_in = resistor("VREF", "IN_NEGREF")
    inverter_fb = resistor("IN_NEGREF", "NEG_REF")
    reference = float(re.search(r"(\d+\.\d+)", mb["D21"].value).group(1))

    def arr(v):
        return "{ " + ", ".join(str(x) for x in v) + " }"

    def f(v):
        return repr(float(v)) + "f"

    text = f"""// Generated by test/gen_board_tables.py from marbles/hardware/tools/circuit.py.
// Do not edit.

#ifndef MARBLESY_TEST_BOARD_TABLES_H_
#define MARBLESY_TEST_BOARD_TABLES_H_

namespace board {{

// 74HC595 chain bits (0..7 = the first 595's QA..QH, 8..15 = the second's)
// of each LED's red and green lines, in Marbles' Led order; -1 = none.
const int kLedRedBit[7] = {arr(red_bits)};
const int kLedGreenBit[7] = {arr(green_bits)};
// The output LEDs by DAC channel (Y, X1, X2, X3).
const int kOutputLedBit[4] = {arr(output_bits)};
// The 74HC165 input of each button, in Marbles' Switch order.
const int kSwitchInput[7] = {arr(inputs)};
// The MCP4922 of each DAC channel (Y, X1, X2, X3): 0 = U7 A, 1 = U7 B,
// 2 = U8 A, 3 = U8 B.
const int kDacSlotOfChannel[4] = {arr(dac_slots)};

// The CV input stages: Rin, Rf, the + input at 3V3A * kBiasRatio.
const float kCvInputResistor = {f(cv_rin.pop())};
const float kCvFeedbackResistor = {f(cv_rf.pop())};
const float kBiasRatio = {f(bias_bottom / (bias_top + bias_bottom))};
// The output stages, the reference and its inverter.
const float kDacInputResistor = {f(dac_rin.pop())};
const float kDacOffsetResistor = {f(dac_rref.pop())};
const float kDacFeedbackResistor = {f(dac_rf.pop())};
const float kOutputResistor = {f(dac_rout.pop())};
const float kInverterInput = {f(inverter_in)};
const float kInverterFeedback = {f(inverter_fb)};
const float kReference = {f(reference)};

}}  // namespace board

#endif  // MARBLESY_TEST_BOARD_TABLES_H_
"""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    for p in problems:
        print("circuit.py disagrees:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
