"""Helpers for the pins and logic groups: the firmware's pins, GPIO setups and the
chain's bit-bang sequence, read from the C++ sources (comments stripped), and
gate-level models of the 74HC165 / 74HC595 chain.

Nothing here decides pass or fail; test_pins.py and test_logic.py do.
"""
import re

import harness


def strip_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"//[^\n]*", "", s)


HAL_RAW = harness.text("firmware", "src", "hal_daisy.cc")
DISPLAY_RAW = harness.text("firmware", "src", "display_daisy.cc")
HAL_H_RAW = harness.text("firmware", "src", "hal.h")
CONTROLS_RAW = harness.text("firmware", "src", "app", "controls.cc")
CONTROLS_H_RAW = harness.text("firmware", "src", "app", "controls.h")
MAIN_RAW = harness.text("firmware", "src", "main.cc")
HAL = strip_comments(HAL_RAW)
DISPLAY = strip_comments(DISPLAY_RAW)
HAL_H = strip_comments(HAL_H_RAW)
CONTROLS = strip_comments(CONTROLS_RAW)
CONTROLS_H = strip_comments(CONTROLS_H_RAW)
MAIN = strip_comments(MAIN_RAW)


def function_body(code, name):
    """The {...} body of the first function definition called `name` (brace matched)."""
    m = re.search(r"\b" + re.escape(name) + r"\s*\([^;{]*\)\s*(?:const\s*)?\{", code)
    if not m:
        return None
    i, depth = m.end(), 1
    while depth and i < len(code):
        depth += {"{": 1, "}": -1}.get(code[i], 0)
        i += 1
    return code[m.end():i - 1]


def int_const(code, name):
    m = re.search(r"\b" + name + r"\s*=\s*([0-9xa-fA-F]+)[uU]?\s*;", code)
    return int(m.group(1), 0) if m else None


def int_array(code, name):
    m = re.search(r"\b" + name + r"\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", code)
    if not m:
        return None
    out = []
    for tok in m.group(1).split(","):
        tok = tok.strip()
        if tok:
            out.append(int(tok, 0) if re.match(r"^[+-]?(0x[0-9a-fA-F]+|\d+)$", tok) else tok)
    return out


def enum_values(code, name):
    m = re.search(r"enum\s+" + name + r"\s*\{(.*?)\}", code, re.S)
    if not m:
        return []
    return [v.strip().split("=")[0].strip() for v in m.group(1).split(",") if v.strip()]


# ------------------------------------------------------------------ the firmware's pins
HAL_PINS = dict(re.findall(r"constexpr\s+Pin\s+(kPin\w+)\s*=\s*daisy::seed::(\w+)\s*;", HAL))
_m = re.search(r"constexpr\s+Pin\s+kPinCv\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", HAL)
CV_PINS = re.findall(r"daisy::seed::(\w+)", _m.group(1)) if _m else []

DISPLAY_PINS = {}
for _obj, _name in re.findall(r"\b(\w+)\.Init\(\s*daisy::seed::(\w+)", DISPLAY):
    DISPLAY_PINS[_obj] = _name
for _field, _name in re.findall(r"pin_config\.(\w+)\s*=\s*daisy::seed::(\w+)", DISPLAY):
    DISPLAY_PINS["spi." + _field] = _name
for _name in re.findall(r"Channel::Config\(\s*daisy::seed::(\w+)", DISPLAY):
    DISPLAY_PINS["backlight"] = _name
EMPTY_SPI_PINS = re.findall(r"pin_config\.(\w+)\s*=\s*daisy::Pin\(\)", DISPLAY)


def gpio_inits(code):
    """{object: (pin expression, mode, pull, speed)} of every libDaisy GPIO::Init call (defaults filled in)."""
    out = {}
    for obj, args in re.findall(r"\b(\w+)\.Init\(([^;]*?)\)\s*;", code):
        if "GPIO::Mode" not in args and "GPIO::" not in args:
            continue
        parts = [a.strip() for a in args.split(",")]
        pin = parts[0]
        mode = next((re.sub(r".*GPIO::Mode::", "", a) for a in parts if "GPIO::Mode::" in a), "INPUT")
        pull = next((re.sub(r".*GPIO::Pull::", "", a) for a in parts if "GPIO::Pull::" in a), "NOPULL")
        speed = next((re.sub(r".*GPIO::Speed::", "", a) for a in parts if "GPIO::Speed::" in a), "LOW")
        out[obj] = (pin, mode, pull, speed)
    return out


def hal_gpio_struct(body):
    """The GPIO_InitTypeDef fields a function body sets (gpio.Mode = ..., ...)."""
    return dict(re.findall(r"\bgpio\.(\w+)\s*=\s*([^;]+);", body or ""))


# ------------------------------------------------------------------ the chain sequence
def chain_ops():
    """ShiftChain's edges in order: (pre-loop ops, loop ops, bits). Ops: LOAD_L, LOAD_H, CLK_H, CLK_L,
    DOUT (SR_DOUT set to the next bit), READ (SR_DIN sampled), SETTLE."""
    body = function_body(HAL, "ShiftChain")
    if body is None:
        return None, None, None
    m = loop = None
    for mm in re.finditer(r"for\s*\(\s*int\s+i\s*=\s*0\s*;\s*i\s*<\s*(\w+)\s*;[^)]*\)\s*\{", body):
        i, depth = mm.end(), 1          # the loop body (brace matched)
        while depth:
            depth += {"{": 1, "}": -1}.get(body[i], 0)
            i += 1
        if "sr_clk_port" in body[mm.end():i - 1]:      # the chain's loop, not the LED-word loop
            m, loop = mm, body[mm.end():i - 1]
            break
    if not m:
        return None, None, None
    pre = body[:m.start()]
    bits_name = m.group(1)
    bits = int_const(HAL, bits_name) if not bits_name.isdigit() else int(bits_name)

    def ops(text):
        out = []
        pat = re.compile(r"(if\s*\(\s*out\s*&[^)]*\)\s*\{[^}]*\}\s*else\s*\{[^}]*\})|"
                         r"Set(Low|High)\(\s*sr_(\w+)_port|(Settle)\(\)|(sr_din_port->IDR)")
        for mm in pat.finditer(text):
            if mm.group(1):
                out.append("DOUT")
            elif mm.group(2):
                sig = {"load": "LOAD", "clk": "CLK", "dout": "DOUT_RAW"}.get(mm.group(3), mm.group(3).upper())
                out.append(f"{sig}_{'L' if mm.group(2) == 'Low' else 'H'}")
            elif mm.group(4):
                out.append("SETTLE")
            elif mm.group(5):
                out.append("READ")
        return out

    # the first-pass ops before the loop: only the ones after the LED word is built
    return ops(pre), ops(loop), bits


class HC165:
    """74HC165 (TI SCLS116): /PL low loads D0..D7 asynchronously (Q7 = D7 at once); with /PL high and CE low,
    each CP rising edge shifts Q0 -> Q1 ... -> Q7 and DS into Q0."""

    def __init__(self):
        self.q = [1] * 8      # q[0] = Q0 ... q[7] = Q7

    def load(self, d):        # d[0] = D0 ... d[7] = D7
        self.q = list(d)

    def clock(self, ds):
        self.q = [ds] + self.q[:7]

    @property
    def q7(self):
        return self.q[7]


class HC595:
    """74HC595 (TI SCLS041): each SRCLK rising edge shifts SER into QA's stage, QA -> QB ... -> QH';
    each RCLK rising edge copies the shift register to the outputs QA..QH."""

    def __init__(self):
        self.sr = [0] * 8     # sr[0] = QA stage ... sr[7] = QH stage
        self.out = [0] * 8

    def srclk(self, ser):
        self.sr = [ser] + self.sr[:7]

    def rclk(self):
        self.out = list(self.sr)


def run_chain(pre, loop, bits, inputs_u1, inputs_u2, led_word, din_pullup=1, faceplate=True, u595=None):
    """Run the firmware's op sequence once over the gate models. inputs_*: D0..D7 levels (1 = high).
    Returns (raw word as the firmware assembles it, the 595). led_word: the 16-bit `out` word."""
    u1, u2 = HC165(), HC165()
    u3 = u595 or HC595()
    load = 1
    clk = 0
    dout = 0
    out = led_word
    word = 0
    seq = list(pre) + list(loop) * bits
    for op in seq:
        if op == "LOAD_L":
            load = 0
            u1.load(inputs_u1)
            u2.load(inputs_u2)
        elif op == "LOAD_H":
            if load == 0:
                u3.rclk()           # RCLK rising edge
            load = 1
        elif op == "DOUT":
            dout = 1 if out & 0x8000 else 0
            out = (out << 1) & 0xffff
        elif op == "READ":
            din = u1.q7 if faceplate else din_pullup
            word = ((word << 1) | din) & 0xffff
        elif op == "CLK_H":
            if clk == 0:
                if load == 1:       # /PL high: the 165s shift (CE grounded)
                    q2 = u2.q7
                    u1.clock(q2)
                    u2.clock(0)     # U2 DS grounded
                u3.srclk(dout)
            clk = 1
        elif op == "CLK_L":
            clk = 0
    return word, u3


def led_word(leds, led_output, n_leds):
    """The 16-bit word ShiftChain builds from the LED byte (out |= 1 << kLedOutput[i])."""
    out = 0
    for i in range(n_leds):
        if leds & (1 << i):
            out |= 1 << led_output[i]
    return out
