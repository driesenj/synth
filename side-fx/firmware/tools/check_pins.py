# Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
"""Side FXy: checks the firmware's pins and shift-register bit order against
the netlist (side-fx/hardware/tools/circuit.py).

  python -B tools/check_pins.py [--libdaisy DIR]

Reads, from side-fx/firmware:
  src/hal_daisy.cc      the kPin* constants, kEncoderBitA/B, kSwitchBit,
                        kLedOutput
  src/display_daisy.cc  (if present) the seed pins of CS, DC, RST, SCK, MOSI
                        and the backlight PWM channel
  src/hal.h             the Switch and Led enums, and the pin table in its
                        header comment
and compares them with circuit.py's SEED, the 74HC165s' inputs on the
faceplate and the 74HC595's outputs on the main board. With libDaisy's
daisy_seed.h (lib/libDaisy, or --libdaisy) it also checks the port names in
hal.h's pin table. Prints every mismatch; exit status 1 if there is one.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.dirname(HERE)
HARDWARE_TOOLS = os.path.join(os.path.dirname(FIRMWARE), "hardware", "tools")

sys.dont_write_bytecode = True
sys.path.insert(0, HARDWARE_TOOLS)
import circuit  # noqa: E402

errors = []
notes = []


def fail(message):
    errors.append(message)


def read(relative):
    path = os.path.join(FIRMWARE, relative)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


# ------------------------------------------------------------ circuit.py side
# Seed pin name (D26, A0, D15...) -> net, from SEED (names like "D15/A0" give both).
seed_net = {}
for pin, (name, net) in circuit.SEED.items():
    if pin.startswith("J"):
        continue
    for alias in name.split("/"):
        seed_net[alias] = net

# Nets the firmware drives or reads through a Seed GPIO/ADC/peripheral pin.
FIRMWARE_NETS = {"CLK", "MIDI_RX", "BTN_SHIFT", "SR_CLK", "SR_LOAD", "SR_DOUT", "SR_DIN",
                 "ADC_CV1", "ADC_CV2", "ADC_CV3", "ADC_CV4",
                 "LCD_CS", "LCD_SCK", "LCD_MOSI", "LCD_DC", "LCD_BL", "LCD_RST"}
circuit_nets = {n for n in seed_net.values() if n and n not in ("GND", "3V3A", "3V3D")}
for net in sorted(circuit_nets - FIRMWARE_NETS):
    fail(f"circuit.py: Seed net {net} is not one this check knows (update check_pins.py)")


def check_pin(source, what, seed_name, net):
    actual = seed_net.get(seed_name, "<no such Seed pin>")
    if actual != net:
        fail(f"{source}: {what} is seed::{seed_name}, which circuit.py has on {actual}, not {net}")


# --------------------------------------------------------------- hal.h enums
hal_h = read("src/hal.h")
if hal_h is None:
    sys.exit("src/hal.h not found")


def enum_values(text, name):
    m = re.search(r"enum\s+" + name + r"\s*\{(.*?)\}", strip_comments(text), re.S)
    if not m:
        fail(f"hal.h: enum {name} not found")
        return []
    return [v.strip().split("=")[0].strip() for v in m.group(1).split(",") if v.strip()]


switches = [v for v in enum_values(hal_h, "Switch") if v != "NUM_SWITCHES"]
leds = [v for v in enum_values(hal_h, "Led") if v != "NUM_LEDS"]

# ------------------------------------------------------------ hal_daisy.cc pins
hal_cc = read("src/hal_daisy.cc")
if hal_cc is None:
    sys.exit("src/hal_daisy.cc not found")
code = strip_comments(hal_cc)

HAL_PINS = {"kPinClock": "CLK", "kPinMidiRx": "MIDI_RX", "kPinShift": "BTN_SHIFT",
            "kPinSrClk": "SR_CLK", "kPinSrLoad": "SR_LOAD", "kPinSrDout": "SR_DOUT",
            "kPinSrDin": "SR_DIN"}
seen_nets = set()
found = dict(re.findall(r"constexpr\s+Pin\s+(kPin\w+)\s*=\s*daisy::seed::(\w+)\s*;", code))
for name, net in HAL_PINS.items():
    if name not in found:
        fail(f"hal_daisy.cc: {name} not found")
        continue
    check_pin("hal_daisy.cc", name, found[name], net)
    seen_nets.add(net)
for name in sorted(set(found) - set(HAL_PINS)):
    fail(f"hal_daisy.cc: {name} is a pin this check does not know")

m = re.search(r"constexpr\s+Pin\s+kPinCv\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", code)
if not m:
    fail("hal_daisy.cc: kPinCv not found")
else:
    cv = re.findall(r"daisy::seed::(\w+)", m.group(1))
    if len(cv) != 4:
        fail(f"hal_daisy.cc: kPinCv has {len(cv)} pins, not 4")
    for i, name in enumerate(cv):
        check_pin("hal_daisy.cc", f"kPinCv[{i}]", name, f"ADC_CV{i + 1}")
        seen_nets.add(f"ADC_CV{i + 1}")

# Every seed:: pin the file uses must be one of the constants above.
uses = re.findall(r"daisy::seed::(\w+)", code)
if len(uses) != len(HAL_PINS) + 4:
    fail(f"hal_daisy.cc: {len(uses)} daisy::seed:: pins, expected {len(HAL_PINS) + 4} "
         "(use the kPin constants)")

# ----------------------------------------------------- display_daisy.cc pins
display_cc = read("src/display_daisy.cc")
if display_cc is None:
    notes.append("src/display_daisy.cc not present: display pins not checked")
else:
    dcode = strip_comments(display_cc)
    display = {}
    for obj, name in re.findall(r"\b(\w+)\.Init\(\s*daisy::seed::(\w+)", dcode):
        display[obj] = name
    for field, name in re.findall(r"pin_config\.(\w+)\s*=\s*daisy::seed::(\w+)", dcode):
        display["spi." + field] = name
    for name in re.findall(r"Channel::Config\(\s*daisy::seed::(\w+)", dcode):
        display["backlight"] = name
    DISPLAY_PINS = {"cs": "LCD_CS", "dc": "LCD_DC", "rst": "LCD_RST", "spi.sclk": "LCD_SCK",
                    "spi.mosi": "LCD_MOSI", "backlight": "LCD_BL"}
    for what, net in DISPLAY_PINS.items():
        if what not in display:
            fail(f"display_daisy.cc: the {what} pin not found")
            continue
        check_pin("display_daisy.cc", what, display[what], net)
        seen_nets.add(net)
    for what in sorted(set(display) - set(DISPLAY_PINS)):
        fail(f"display_daisy.cc: {what} uses seed::{display[what]}, a pin this check does not know")
    duses = re.findall(r"daisy::seed::(\w+)", dcode)
    if len(duses) != len(display):
        fail(f"display_daisy.cc: {len(duses)} daisy::seed:: uses, {len(display)} recognised")

expected = FIRMWARE_NETS if display_cc is not None else {n for n in FIRMWARE_NETS if not n.startswith("LCD_")}
for net in sorted(expected - seen_nets):
    fail(f"no firmware pin for net {net}")

# Two firmware pins on one Seed pin?
pins_used = {}
for name, seed_name in found.items():
    pins_used.setdefault(seed_net.get(seed_name, seed_name), []).append("hal_daisy.cc " + name)
if display_cc is not None:
    for what, seed_name in display.items():
        pins_used.setdefault(seed_net.get(seed_name, seed_name), []).append("display_daisy.cc " + what)
for net, users in sorted(pins_used.items(), key=lambda kv: str(kv[0])):
    if len(users) > 1:
        fail(f"{', '.join(users)} share the Seed pin of {net}")

# ------------------------------------------------------------ the 165 chain
parts = {p.ref: p for p in circuit.main_board_parts() + circuit.faceplate_parts()}
u1, u2, u3 = parts["U1"], parts["U2"], parts["U3"]
if u1.nets.get("9") != "SR_DIN_F":
    fail(f"circuit.py: U1 Q7 is {u1.nets.get('9')}, not SR_DIN_F: U1 is not read first")
if u2.nets.get("9") != u1.nets.get("10"):
    fail("circuit.py: U2 Q7 does not feed U1 DS")
for u in (u1, u2):
    if u.nets.get("1") != "SR_LOAD_F" or u.nets.get("2") != "SR_CLK_F":
        fail(f"circuit.py: {u.ref} /PL and CP are not SR_LOAD_F and SR_CLK_F")
    if u.nets.get("15") != "GND_D_F":
        fail(f"circuit.py: {u.ref} CE is not grounded")
for pin, net in (("11", "SR_CLK"), ("12", "SR_LOAD"), ("14", "SR_DOUT")):
    if u3.nets.get(pin) != net:
        fail(f"circuit.py: U3 pin {pin} is {u3.nets.get(pin)}, not {net}")

# raw bit (as hal_daisy.cc reads the chain) -> net: U1 Dn at 8 + n, U2 Dn at n
raw_net = {}
for u, base in ((u1, 8), (u2, 0)):
    for n, pin in enumerate(circuit.HC165_INPUTS):
        raw_net[base + n] = u.nets.get(pin)


def int_array(name):
    m = re.search(r"\b" + name + r"\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", code)
    if not m:
        fail(f"hal_daisy.cc: {name} not found")
        return []
    values = []
    for token in m.group(1).split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token, 0) if re.match(r"^(0x)?[0-9a-fA-F]+$", token) else token)
    return values


enc_a = int_array("kEncoderBitA")
enc_b = int_array("kEncoderBitB")
for k in range(4):
    for phase, table in (("A", enc_a), ("B", enc_b)):
        if k >= len(table):
            fail(f"hal_daisy.cc: kEncoderBit{phase} has no entry for encoder {k + 1}")
            continue
        want = f"ENC{k + 1}_{phase}_F"
        got = raw_net.get(table[k])
        if got != want:
            fail(f"hal_daisy.cc: kEncoderBit{phase}[{k}] = {table[k]} reads {got}, not {want}")

switch_bits = int_array("kSwitchBit")
if len(switch_bits) != len(switches):
    fail(f"hal_daisy.cc: kSwitchBit has {len(switch_bits)} entries for {len(switches)} switches")
for s, bit in zip(switches, switch_bits):
    word = s[len("SWITCH_"):]
    if word == "SHIFT":
        if bit != "kNotOnChain":
            fail("hal_daisy.cc: SHIFT has its own Seed pin (BTN_SHIFT), kSwitchBit must be kNotOnChain")
        continue
    want = f"BTN_{word}_F"
    got = raw_net.get(bit) if isinstance(bit, int) else None
    if got != want:
        fail(f"hal_daisy.cc: kSwitchBit[{s}] = {bit} reads {got}, not {want}")
used_bits = [b for b in switch_bits + enc_a + enc_b if isinstance(b, int)]
if sorted(used_bits) != list(range(16)):
    fail(f"hal_daisy.cc: the chain bits used are {sorted(used_bits)}, not 0..15 once each")

# ------------------------------------------------------------- the 595 LEDs
led_out = int_array("kLedOutput")
if len(led_out) != len(leds):
    fail(f"hal_daisy.cc: kLedOutput has {len(led_out)} entries for {len(leds)} LEDs")
for led, q in zip(leds, led_out):
    word = led[len("LED_"):]
    got = u3.nets.get(circuit.HC595_OUT[q]) if isinstance(q, int) and 0 <= q < 8 else None
    if got != f"L_{word}":
        fail(f"hal_daisy.cc: kLedOutput[{led}] = Q{'ABCDEFGH'[q] if isinstance(q, int) and 0 <= q < 8 else '?'} "
             f"drives {got}, not L_{word}")
    # and that L_word really reaches the button labelled word
    button = [ref for ref, label, _ in circuit.BUTTONS if label == word]
    if not button:
        fail(f"circuit.py: no button labelled {word}")

# ------------------------------------------------------- hal.h's pin table
libdaisy = None
args = sys.argv[1:]
if "--libdaisy" in args:
    libdaisy = args[args.index("--libdaisy") + 1]
else:
    candidate = os.path.join(FIRMWARE, "lib", "libDaisy")
    if os.path.isdir(candidate):
        libdaisy = candidate
seed_port = {}
if libdaisy:
    path = os.path.join(libdaisy, "src", "daisy_seed.h")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for name, port, pin in re.findall(r"constexpr\s+Pin\s+(D\d+)\s*=\s*Pin\(PORT([A-K]),\s*(\d+)\)", text):
            seed_port[name] = f"P{port}{pin}"
        for name, alias in re.findall(r"constexpr\s+Pin\s+(A\d+)\s*=\s*(D\d+)\s*;", text):
            if alias in seed_port:
                seed_port[name] = seed_port[alias]
    else:
        notes.append(f"{path} not found: hal.h port names not checked")
else:
    notes.append("libDaisy not found (lib/libDaisy or --libdaisy): hal.h port names not checked")

header = hal_h.split("#ifndef")[0]
for name, port, net in re.findall(r"^//\s+(D\d+)\s+(P[A-K]\d+)\s+(\w+)", header, re.M):
    check_pin("hal.h", name, name, net)
    if seed_port and seed_port.get(name) != port:
        fail(f"hal.h: {name} is {seed_port.get(name)} in libDaisy, not {port}")
m = re.search(r"^//\s+A0\.\.A3\s+((?:P[A-K]\d+\s+){4})", header, re.M)
if m and seed_port:
    for i, port in enumerate(m.group(1).split()):
        if seed_port.get(f"A{i}") != port:
            fail(f"hal.h: A{i} is {seed_port.get(f'A{i}')} in libDaisy, not {port}")

# ------------------------------------------------------------------- report
for n in notes:
    print("note:", n)
if errors:
    for e in errors:
        print("MISMATCH:", e)
    sys.exit(1)
print(f"check_pins: OK ({len(seen_nets)} pins, 16 chain bits, {len(leds)} LEDs"
      f"{', hal.h ports vs libDaisy' if seed_port else ''})")
