"""Regression tests for the serial bridge's MIDI parser.

Run from the project root, with no hardware and no dependencies installed:

    python tools/test_bridge.py

The parser is the part of the bridge that can be wrong without anything
looking wrong - a mis-parse shows up as stray notes in the DAW rather than as
an error - so it is worth keeping honest.
"""

import os
import sys, types, importlib.util

# Stub the two optional deps so the module imports without them installed.
for name in ("serial", "rtmidi"):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
tools = types.ModuleType("serial.tools")
tools.list_ports = types.ModuleType("serial.tools.list_ports")
sys.modules["serial.tools"] = tools
sys.modules["serial.tools.list_ports"] = tools.list_ports
sys.modules["serial"].tools = tools

spec = importlib.util.spec_from_file_location("bridge", os.path.join(os.path.dirname(os.path.abspath(__file__)), "serial_midi_bridge.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

fails = []
def check(label, got, want):
    ok = got == want
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        print("          got  %r" % (got,))
        print("          want %r" % (want,))
        fails.append(label)

P = bridge.MidiParser

# 1. The ESP32 ROM bootloader burst is ASCII: all data bytes, no status.
p = P()
boot = b"rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\n"
out = list(p.feed(boot))
check("boot log produces no messages", out, [])
check("boot log counted as dropped", p.dropped, len(boot))

# ...and a real note-on straight after it still parses.
check("note-on after boot log", list(p.feed(bytes([0x90, 45, 100]))),
      [[0x90, 45, 100]])

# 2. The firmware's note-off is note-on with velocity 0.
p = P()
check("note off as vel 0", list(p.feed(bytes([0x90, 45, 0]))), [[0x90, 45, 0]])

# 3. Control change.
p = P()
check("control change", list(p.feed(bytes([0xB0, 64, 127]))), [[0xB0, 64, 127]])

# 4. Several messages split across chunk boundaries mid-message.
p = P()
got = list(p.feed(bytes([0x90, 45]))) + list(p.feed(bytes([100, 0x90, 47])))
got += list(p.feed(bytes([100])))
check("messages split across reads", got, [[0x90, 45, 100], [0x90, 47, 100]])

# 5. Running status: firmware does not send it, the looper might.
p = P()
check("running status", list(p.feed(bytes([0x90, 45, 100, 47, 100, 48, 0]))),
      [[0x90, 45, 100], [0x90, 47, 100], [0x90, 48, 0]])

# 6. A real-time byte may sit inside another message without breaking it.
p = P()
check("realtime inside a message", list(p.feed(bytes([0x90, 45, 0xF8, 100]))),
      [[0xF8], [0x90, 45, 100]])

# 7. A truncated message followed by a fresh status must not merge the two.
p = P()
check("resync after truncation", list(p.feed(bytes([0x90, 45, 0xB0, 64, 127]))),
      [[0xB0, 64, 127]])

# 8. Decoding, including the vel-0 note-off convention.
check("describe note on", bridge.describe([0x90, 45, 100]).strip(),
      "ch1  note on  A2   ( 45) vel 100")
check("describe note off", bridge.describe([0x90, 45, 0]).strip(),
      "ch1  note off A2   ( 45) vel   0")
check("describe middle C", bridge.describe([0x90, 60, 100]).split("(")[0].strip(),
      "ch1  note on  C4")

# 9. A board still in text mode must be called out, not silently dropped.
import io, contextlib
spotter = bridge.TextSpotter()
captured = io.StringIO()
with contextlib.redirect_stdout(captured):
    spotter.feed(b"DOWN pos=13  col=2 row=1  kind=1 data=58\r\n")
    spotter.feed(b"UP   pos=13  col=2 row=1  kind=1 data=58\r\n")
out = captured.getvalue()
check("text log line echoed", "text | DOWN pos=13" in out, True)
check("wrong-mode hint shown once", out.count("set USB_MIDI 1"), 1)

# A line split across two reads is reassembled before it is judged.
spotter = bridge.TextSpotter()
captured = io.StringIO()
with contextlib.redirect_stdout(captured):
    spotter.feed(b"Meowsic MIDI - key")
    spotter.feed(b"bed scan stage\r\n")
check("split text line reassembled",
      "text | Meowsic MIDI - keybed scan stage" in captured.getvalue(), True)

# Non-printable junk - the real boot burst has plenty - stays quiet.
spotter = bridge.TextSpotter()
captured = io.StringIO()
with contextlib.redirect_stdout(captured):
    spotter.feed(bytes([0x00, 0xFF, 0x1B, 0x7F]) + b"\n")
check("binary junk not echoed", captured.getvalue(), "")

print()
print("FAILED: %s" % ", ".join(fails) if fails else "all parser tests passed")
sys.exit(1 if fails else 0)
