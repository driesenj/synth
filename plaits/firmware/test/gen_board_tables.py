"""Writes test/board_tables.h for the port's host tests, from the Plaitsy
netlist (plaits/hardware/tools/circuit.py) and nothing else of the firmware.

What it derives, by following nets rather than trusting labels:
- each CV input stage (Rin, Rf, Cf, bias divider) and the jack behind it,
  with what that jack's switch lug does (ground, probe through R, open);
- the bit of the 16-bit word the HAL shifts out that drives each LED colour,
  from LED_LINES / SR_OUTS / HC595_OUTS and the chain (U9 SER from MOSI,
  U9 QH' into U10 SER), with the HAL sending the high byte first, MSB first;
- the 74HC4051 channel of each pot, from the pot wiper nets and the 4051's
  datasheet pinout (cross-checked with the channel column of POTS);
- which Seed pin each button, button LED and HAL role is wired to, and
  whether src/hal_daisy.cc uses those pins (a text check of its constants).

Run:  python3 -B -E -P gen_board_tables.py <output .h>
(-B and sys.dont_write_bytecode: importing circuit.py must not leave a
__pycache__ in the hardware folder.)
"""
import os
import re
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.dirname(HERE)
TOOLS = os.path.normpath(os.path.join(FIRMWARE, "..", "hardware", "tools"))
sys.path.insert(0, TOOLS)
import circuit  # noqa: E402  (the user's netlist module; importing it has no side effects)

problems = []  # generator-level inconsistencies, reported by the C++ test


def problem(text):
    problems.append(text)


def value_of(text):
    """'13k' -> 13000.0, '470' -> 470.0, '1u' -> 1e-6."""
    m = re.fullmatch(r"([0-9.]+)([kMunp]?)", text.strip())
    if not m:
        raise ValueError(f"cannot parse value {text!r}")
    mult = {"": 1.0, "k": 1e3, "M": 1e6, "u": 1e-6, "n": 1e-9, "p": 1e-12}[m.group(2)]
    return float(m.group(1)) * mult


def index(parts):
    by_ref = {p.ref: p for p in parts}
    nets = {}
    for p in parts:
        for pin, net in p.nets.items():
            nets.setdefault(net, []).append((p.ref, pin))
    return by_ref, nets


mb_parts = circuit.main_board_parts()
fb_parts = circuit.faceplate_parts()
MB, MB_NETS = index(mb_parts)
FB, FB_NETS = index(fb_parts)

# Board-to-board: main-board net <-> faceplate net.
MB_TO_FB, FB_TO_MB = {}, {}
for ref, kind, pairs in circuit.HEADERS:
    for mb, fb in pairs:
        MB_TO_FB[mb] = fb
        FB_TO_MB[fb] = mb


def two_terminal_between(parts_by_ref, kind, net_a, net_b):
    found = []
    for p in parts_by_ref.values():
        if p.kind == kind and set(p.nets.values()) == {net_a, net_b} and len(p.nets) == 2:
            found.append(p)
    return found


def two_terminal_on(parts_by_ref, kind, net):
    return [p for p in parts_by_ref.values() if p.kind == kind and net in p.nets.values() and len(p.nets) == 2]


def other_net(part, net):
    nets = list(part.nets.values())
    return nets[1] if nets[0] == net else nets[0]


# ------------------------------------------------------------ Seed pins
SEED_NET_TO_PIN = {}  # net -> (seed pin number, libDaisy name)
for pin, (name, net) in circuit.SEED.items():
    if net:
        SEED_NET_TO_PIN.setdefault(net, []).append((pin, name))


def seed_names_for_net(net):
    """libDaisy aliases of the Seed pin(s) on a main-board net: 'D15/A0' -> {'D15', 'A0'}."""
    names = set()
    for pin, name in SEED_NET_TO_PIN.get(net, []):
        names.update(name.split("/"))
    return names


def seed_label_for_net(net):
    entries = SEED_NET_TO_PIN.get(net, [])
    return ",".join(f"pin {p} {n}" for p, n in entries) or "none"


# ------------------------------------------------------------ CV stages
# The HAL's ADC inputs (hal.h, enum AdcInput), named as Plaits names them,
# and the panel label of the jack each one is for.
HAL_ADC_INPUTS = ["MODEL", "TIMBRE", "FM", "MORPH", "HARMONICS", "TRIGGER", "LEVEL", "V_OCT"]
PLAITS_TO_PANEL = {"MODEL": "MODEL", "TIMBRE": "TIMBRE", "FM": "FM", "MORPH": "MORPH",
                   "HARMONICS": "HARMO", "TRIGGER": "TRIG", "LEVEL": "LEVEL", "V_OCT": "V/OCT"}
TL074_SECTIONS = circuit.SECTION  # section -> (out, in-, in+)


def stage_for_adc_net(adc_net):
    """Follows ADC pin net -> series R -> op-amp output -> section -> Rf/Rin/Cf/bias -> jack."""
    series = [p for p in two_terminal_on(MB, "R", adc_net)]
    if len(series) != 1:
        raise RuntimeError(f"{adc_net}: expected one series resistor, found {series}")
    rs = series[0]
    oa = other_net(rs, adc_net)
    # The op-amp pin on that net must be a section output.
    amp_pins = [(r, pin) for r, pin in MB_NETS[oa] if MB[r].kind == "TL074"]
    if len(amp_pins) != 1:
        raise RuntimeError(f"{oa}: expected one op-amp pin, found {amp_pins}")
    amp, out_pin = amp_pins[0]
    section = [s for s, (o, m, p) in TL074_SECTIONS.items() if o == out_pin]
    if not section:
        raise RuntimeError(f"{amp}.{out_pin} is not an op-amp output")
    _, inm_pin, inp_pin = TL074_SECTIONS[section[0]]
    inm = MB[amp].nets[inm_pin]
    bias = MB[amp].nets[inp_pin]
    rf = two_terminal_between(MB, "R", inm, oa)
    cf = two_terminal_between(MB, "C", inm, oa)
    rin = [p for p in two_terminal_on(MB, "R", inm) if p not in rf]
    if len(rf) != 1 or len(cf) != 1 or len(rin) != 1:
        raise RuntimeError(f"{adc_net}: Rf {rf} Cf {cf} Rin {rin}")
    cv = other_net(rin[0], inm)
    # Bias divider: one resistor to 3V3A, one to GND.
    top = [p for p in two_terminal_on(MB, "R", bias) if other_net(p, bias) == "3V3A"]
    bottom = [p for p in two_terminal_on(MB, "R", bias) if other_net(p, bias) == "GND"]
    if len(top) != 1 or len(bottom) != 1:
        raise RuntimeError(f"{bias}: divider {top} {bottom}")
    # The jack whose tip is on this CV net (through the header).
    fb_net = MB_TO_FB.get(cv)
    jacks = [(r, pin) for r, pin in FB_NETS.get(fb_net, []) if FB[r].kind == "JACK" and pin == "3"]
    if len(jacks) != 1:
        raise RuntimeError(f"{cv}/{fb_net}: expected one jack tip, found {jacks}")
    jack = FB[jacks[0][0]]
    lug = jack.nets.get("2")
    lug_kind, probe_r = "open", 0.0
    if lug == "GND_F":
        lug_kind = "ground"
    elif lug is not None:
        rp = [p for p in two_terminal_on(FB, "R", lug) if other_net(p, lug) == "PROBE_F"]
        if len(rp) != 1:
            raise RuntimeError(f"{jack.ref} lug {lug}: no single resistor to PROBE_F ({rp})")
        lug_kind, probe_r = "probe", value_of(rp[0].value)
        # The probe must reach the Seed's probe pin through the header.
        if FB_TO_MB.get("PROBE_F") != "PROBE":
            problem("PROBE_F does not cross to the main board's PROBE net")
    return {
        "adc_net": adc_net, "seed": seed_names_for_net(adc_net), "seed_label": seed_label_for_net(adc_net),
        "rs": value_of(rs.value), "rf": value_of(rf[0].value), "rin": value_of(rin[0].value),
        "cf": value_of(cf[0].value), "bias_net": bias,
        "bias_top": value_of(top[0].value), "bias_bottom": value_of(bottom[0].value),
        "jack": jack.ref, "label": jack.label, "lug": lug_kind, "probe_r": probe_r,
        "refs": f"{rin[0].ref}/{rf[0].ref}/{cf[0].ref}/{rs.ref} on {amp} section {section[0]}",
    }


stages_by_label = {}
for net in SEED_NET_TO_PIN:
    if net.startswith("ADC_"):
        st = stage_for_adc_net(net)
        stages_by_label[st["label"]] = st

stages = []
for name in HAL_ADC_INPUTS:
    label = PLAITS_TO_PANEL[name]
    if label not in stages_by_label:
        raise RuntimeError(f"no CV stage reads the {label} jack")
    stages.append(stages_by_label[label])

# ------------------------------------------------------------ LEDs
HC595_QA_QH = circuit.HC595_OUTS  # pin of QA..QH
HC595_SER, HC595_QH_SERIAL = "14", "9"
LED_PIN_COLOUR = {"1": "R", "3": "G"}  # the bicolour LED's anodes (pin 2 = common cathode)

srs = [p for p in fb_parts if p.kind == "HC595"]
first = [p for p in srs if p.nets.get(HC595_SER) == "MOSI_F"]
if len(first) != 1:
    raise RuntimeError("no single 74HC595 with SER on MOSI_F")
chain = [first[0]]
while True:
    link = chain[-1].nets.get(HC595_QH_SERIAL)
    nxt = [p for p in srs if link and p.nets.get(HC595_SER) == link and p not in chain]
    if not nxt:
        break
    chain.append(nxt[0])
if len(chain) != 2:
    problem(f"74HC595 chain has {len(chain)} parts, expected 2")
if FB_TO_MB.get("MOSI_F") != "SPI_MOSI":
    problem("MOSI_F does not cross to SPI_MOSI")

# The HAL sends the 16-bit word as two bytes, high byte first, each MSB first
# (hal_daisy.cc: bytes {bits >> 8, bits & 0xff}, 8-bit SPI frames, MSB first).
sent_order = [15 - k for k in range(16)]  # word bit sent at clock k
# After 16 shift clocks the bit sent at clock k sits at chain position 15 - k;
# chain position 0..7 = first 595's QA..QH, 8..15 = second's QA..QH.
position_of_word_bit = {sent_order[k]: 15 - k for k in range(16)}
word_bit_of_output = {}  # (595 ref, Q index) -> word bit
for bit, pos in position_of_word_bit.items():
    word_bit_of_output[(chain[pos // 8].ref, pos % 8)] = bit

led_refs_top_down = sorted((ref for ref, *_ in circuit.LEDS), key=lambda r: circuit.PANEL_XY[r][1])
if led_refs_top_down != [f"D{k + 1}" for k in range(8)]:
    problem(f"LED refs top to bottom are {led_refs_top_down}, not D1..D8")
led_bits = {ref: {} for ref in led_refs_top_down}
for sr in chain:
    for q, pin in enumerate(HC595_QA_QH):
        net = sr.nets.get(pin)
        if net is None:
            continue
        res = two_terminal_on(FB, "R", net)
        if len(res) != 1:
            problem(f"{sr.ref} Q{'ABCDEFGH'[q]} ({net}): {len(res)} resistors")
            continue
        led_net = other_net(res[0], net)
        hits = [(r, p) for r, p in FB_NETS[led_net] if FB[r].kind == "LED_RG"]
        if len(hits) != 1:
            problem(f"{led_net}: {hits}")
            continue
        led_ref, led_pin = hits[0]
        colour = LED_PIN_COLOUR[led_pin]
        if not led_net.endswith("_" + colour):
            problem(f"{led_net} reaches {led_ref} pin {led_pin} ({colour}): name and pin disagree")
        if colour in led_bits[led_ref]:
            problem(f"{led_ref} {colour} driven twice")
        led_bits[led_ref][colour] = word_bit_of_output[(sr.ref, q)]
for ref in led_refs_top_down:
    for colour in "RG":
        if colour not in led_bits[ref]:
            problem(f"{ref} {colour} not driven by the 595 chain")
            led_bits[ref][colour] = -1

# ------------------------------------------------------------ pots
MUX_Y_PINS = ["13", "14", "15", "12", "1", "5", "2", "4"]  # 74HC4051 Y0..Y7
MUX_SELECT = {"11": "S0", "10": "S1", "9": "S2"}
mux = [p for p in fb_parts if p.kind == "MUX"]
if len(mux) != 1:
    raise RuntimeError("expected one 74HC4051")
mux = mux[0]
PLAITS_POTS = ["FREQUENCY", "HARMONICS", "TIMBRE", "MORPH", "TIMBRE att.", "FM att.", "MORPH att."]
pot_by_label = {label: (ref, wiper, mpin, ch) for ref, label, wiper, mpin, ch in circuit.POTS}
pot_rows = []
for label in PLAITS_POTS:
    ref, wiper, mpin, ch_table = pot_by_label[label]
    if FB[ref].nets.get("2") != wiper:
        problem(f"{ref}: wiper pin 2 is {FB[ref].nets.get('2')}, POTS says {wiper}")
    chans = [y for y, pin in enumerate(MUX_Y_PINS) if mux.nets.get(pin) == wiper]
    if len(chans) != 1:
        raise RuntimeError(f"{ref} wiper {wiper} on mux channels {chans}")
    if chans[0] != ch_table:
        problem(f"{ref}: wiper on Y{chans[0]} by the 4051 pinout, POTS says {ch_table}")
    ends = (FB[ref].nets.get("1"), FB[ref].nets.get("3"))
    if ends != ("GND_F", "3V3A_F"):
        problem(f"{ref}: ends {ends}, expected CCW GND_F, CW 3V3A_F")
    pot_rows.append((label, ref, chans[0]))
grounded = [y for y, pin in enumerate(MUX_Y_PINS) if mux.nets.get(pin) == "GND_F"]
if mux.nets.get("3") != "MUX_OUT_F" or FB_TO_MB.get("MUX_OUT_F") != "MUX_OUT":
    problem("4051 common pin does not reach MUX_OUT")
mux_select_seed = {}
for pin, s in MUX_SELECT.items():
    fb_net = mux.nets.get(pin)
    mb_net = FB_TO_MB.get(fb_net)
    mux_select_seed[s] = (mb_net, seed_names_for_net(mb_net))

# ------------------------------------------------------------ buttons
buttons = sorted((ref for ref, *_ in circuit.BUTTONS), key=lambda r: circuit.PANEL_XY[r][0])
button_rows = []  # left first
for ref in buttons:
    sw_net = FB[ref].nets.get("3")
    led_net = FB[ref].nets.get("5")
    mb_sw = FB_TO_MB.get(sw_net)
    mb_led = FB_TO_MB.get(led_net)
    # the LED goes through a series resistor on the main board
    led_r = two_terminal_on(MB, "R", mb_led)
    led_io = other_net(led_r[0], mb_led) if len(led_r) == 1 else None
    button_rows.append({
        "ref": ref, "x": circuit.PANEL_XY[ref][0], "switch_net": mb_sw, "switch_seed": seed_names_for_net(mb_sw),
        "led_net": led_io, "led_seed": seed_names_for_net(led_io),
    })

# ------------------------------------------------------------ hal_daisy.cc pins
HAL_DAISY = os.path.join(FIRMWARE, "src", "hal_daisy.cc")
pin_checks = []  # (what, hal pin, netlist pins, ok)


def check_pin(what, hal_pin, expected_names, expected_label):
    ok = hal_pin is not None and hal_pin in expected_names
    pin_checks.append((what, hal_pin or "?", expected_label, ok))


try:
    with open(HAL_DAISY, encoding="utf-8") as f:
        hal_text = f.read()
except OSError as e:
    hal_text = ""
    problem(f"cannot read hal_daisy.cc: {e}")

scalars = dict(re.findall(r"constexpr\s+Pin\s+(\w+)\s*=\s*seed::(\w+)\s*;", hal_text))
arrays = {name: re.findall(r"seed::(\w+)", body)
          for name, body in re.findall(r"constexpr\s+Pin\s+(\w+)\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", hal_text)}
adc_pins = arrays.get("kAdcPins", [])
for i, name in enumerate(HAL_ADC_INPUTS):
    st = stages[i]
    check_pin(f"ADC_{name} (hal input {i})", adc_pins[i] if i < len(adc_pins) else None,
              st["seed"], f"{st['adc_net']} = {st['seed_label']}")
check_pin("pot mux out", scalars.get("kMuxOut"), seed_names_for_net("MUX_OUT"), seed_label_for_net("MUX_OUT"))
for s, key in (("S0", "kMuxS0"), ("S1", "kMuxS1"), ("S2", "kMuxS2")):
    mb_net, names = mux_select_seed[s]
    check_pin(f"mux {s}", scalars.get(key), names, f"{mb_net} = {seed_label_for_net(mb_net)}")
button_pins = arrays.get("kButtonPins", [])
for i, (row, hal_name) in enumerate(zip(button_rows, ("BUTTON_A (left)", "BUTTON_B (right)"))):
    check_pin(f"{hal_name} = {row['ref']}", button_pins[i] if i < len(button_pins) else None,
              row["switch_seed"], f"{row['switch_net']} = {seed_label_for_net(row['switch_net'])}")
for row, key in zip(button_rows, ("kButtonLedA", "kButtonLedB")):
    check_pin(f"{key} = {row['ref']} LED", scalars.get(key), row["led_seed"],
              f"{row['led_net']} = {seed_label_for_net(row['led_net'])}")
for key, net in (("kSpiSck", "SPI_SCK"), ("kSpiMosi", "SPI_MOSI"), ("kLedLatch", "LED_LATCH"), ("kProbe", "PROBE")):
    check_pin(key, scalars.get(key), seed_names_for_net(net), f"{net} = {seed_label_for_net(net)}")
# The 595s' clock and latch reach the chips.
for sr in chain:
    if sr.nets.get("11") != "SCK_F" or FB_TO_MB.get("SCK_F") != "SPI_SCK":
        problem(f"{sr.ref} SRCLK not on SPI_SCK")
    if sr.nets.get("12") != "LED_LATCH_F" or FB_TO_MB.get("LED_LATCH_F") != "LED_LATCH":
        problem(f"{sr.ref} RCLK not on LED_LATCH")
# hal_daisy's transmit order, which the LED bit derivation above assumes.
if not re.search(r"bits\s*>>\s*8\s*\)\s*,\s*\n?\s*static_cast<uint8_t>\(\s*bits\s*&\s*0xff", hal_text):
    problem("hal_daisy.cc Service(): could not confirm the bytes go out as {bits >> 8, bits & 0xff}")
if not re.search(r"datasize\s*=\s*8\s*;", hal_text):
    problem("hal_daisy.cc: SPI datasize is not 8 (the LED derivation assumes 8-bit frames)")


# ------------------------------------------------------------ write
def c_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def c_bool(b):
    return "true" if b else "false"


out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "board_tables.h")
lines = []
w = lines.append
w("// Generated by gen_board_tables.py from plaits/hardware/tools/circuit.py.")
w("// Do not edit; rerun the generator (run_port_test.sh does).")
w("")
w("#ifndef PLAITSY_TEST_BOARD_TABLES_H_")
w("#define PLAITSY_TEST_BOARD_TABLES_H_")
w("")
w("namespace board {")
w("")
w("// CV input stages, in hal::AdcInput order:")
for i, st in enumerate(stages):
    w(f"//   {i} {HAL_ADC_INPUTS[i]:9s} jack {st['jack']} {st['label']:6s} {st['refs']}, bias {st['bias_net']}, "
      f"lug {st['lug']}, Seed {st['seed_label']}")
w("const int kNumAdcInputs = 8;")
w("const char* const kAdcInputName[kNumAdcInputs] = { " + ", ".join(c_str(n) for n in HAL_ADC_INPUTS) + " };")
w("const char* const kAdcJackLabel[kNumAdcInputs] = { " + ", ".join(c_str(s["label"]) for s in stages) + " };")
w("const double kStageRin[kNumAdcInputs] = { " + ", ".join(f"{s['rin']:.1f}" for s in stages) + " };")
w("const double kStageRf[kNumAdcInputs] = { " + ", ".join(f"{s['rf']:.1f}" for s in stages) + " };")
w("const double kStageCf[kNumAdcInputs] = { " + ", ".join(f"{s['cf']:.3e}" for s in stages) + " };")
w("const double kStageRs[kNumAdcInputs] = { " + ", ".join(f"{s['rs']:.1f}" for s in stages) + " };")
w("// Bias divider from 3V3A: top resistor to 3V3A, bottom to GND.")
w("const double kBiasTop[kNumAdcInputs] = { " + ", ".join(f"{s['bias_top']:.1f}" for s in stages) + " };")
w("const double kBiasBottom[kNumAdcInputs] = { " + ", ".join(f"{s['bias_bottom']:.1f}" for s in stages) + " };")
w("const char* const kBiasNet[kNumAdcInputs] = { " + ", ".join(c_str(s["bias_net"]) for s in stages) + " };")
w("// Switch lug: the probe through kProbeR (normalized), ground, or open.")
w("const bool kNormalized[kNumAdcInputs] = { " + ", ".join(c_bool(s["lug"] == "probe") for s in stages) + " };")
w("const bool kLugGrounded[kNumAdcInputs] = { " + ", ".join(c_bool(s["lug"] == "ground") for s in stages) + " };")
w("const double kProbeR[kNumAdcInputs] = { " + ", ".join(f"{s['probe_r']:.1f}" for s in stages) + " };")
w("")
w("// LEDs, UI index 0 = the top one; bit of the HAL's 16-bit 74HC595 word.")
w("// Chain: " + " -> ".join(p.ref for p in chain) + ", high byte first, MSB first.")
w("const char* const kLedRef[8] = { " + ", ".join(c_str(r) for r in led_refs_top_down) + " };")
w("const int kLedRedBit[8] = { " + ", ".join(str(led_bits[r]["R"]) for r in led_refs_top_down) + " };")
w("const int kLedGreenBit[8] = { " + ", ".join(str(led_bits[r]["G"]) for r in led_refs_top_down) + " };")
w("")
w("// Pots in Plaits' PotsAdcChannel order and their 74HC4051 channel.")
w("const char* const kPotLabel[7] = { " + ", ".join(c_str(r[0]) for r in pot_rows) + " };")
w("const char* const kPotRef[7] = { " + ", ".join(c_str(r[1]) for r in pot_rows) + " };")
w("const int kPotMuxChannel[7] = { " + ", ".join(str(r[2]) for r in pot_rows) + " };")
w(f"const int kNumGroundedMuxChannels = {len(grounded)};")
w("const int kGroundedMuxChannels[" + str(max(1, len(grounded))) + "] = { " +
  ", ".join(str(y) for y in grounded or [-1]) + " };")
w("")
w("// Buttons, left first (PANEL_XY x).")
w("const char* const kButtonRef[2] = { " + ", ".join(c_str(r["ref"]) for r in button_rows) + " };")
w("")
w("// src/hal_daisy.cc's pin constants against the netlist.")
w("struct PinCheck { const char* what; const char* hal_pin; const char* netlist; bool ok; };")
w(f"const int kNumPinChecks = {len(pin_checks)};")
w("const PinCheck kPinChecks[kNumPinChecks] = {")
for what, hal_pin, label, ok in pin_checks:
    w(f"  {{ {c_str(what)}, {c_str(hal_pin)}, {c_str(label)}, {c_bool(ok)} }},")
w("};")
w("")
w("// Inconsistencies the generator found in the netlist or its assumptions.")
w(f"const int kNumProblems = {len(problems)};")
w("const char* const kProblems[" + str(max(1, len(problems))) + "] = { " +
  (", ".join(c_str(p) for p in problems) if problems else c_str("")) + " };")
w("")
w("}  // namespace board")
w("")
w("#endif  // PLAITSY_TEST_BOARD_TABLES_H_")
text = "\n".join(lines) + "\n"
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print(f"gen_board_tables: wrote {out}: {len(stages)} CV stages, {len(led_refs_top_down)} LEDs, "
      f"{len(pot_rows)} pots, {len(pin_checks)} pin checks, {len(problems)} problems")
