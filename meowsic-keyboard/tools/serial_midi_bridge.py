#!/usr/bin/env python3
"""Bridge the Meowsic's raw serial MIDI to and from virtual MIDI ports.

The ESP32-WROOM-32 has no native USB, so it cannot enumerate as a class-
compliant MIDI device. With USB_MIDI 1 the firmware speaks raw MIDI on UART0
at USB_BAUD instead, and this forwards it both ways: what the keyboard sends
goes to a MIDI output port a DAW can record from (--midi), and what the DAW
sends to a MIDI input port (--midi-in) goes to the keyboard - notes for the
toy and the CV jacks, CCs for its buttons and settings, later MIDI clock.

    pip install pyserial python-rtmidi

Windows has no API for creating virtual MIDI ports, so they have to exist
already: install loopMIDI and add TWO ports there, one per direction, e.g.
"Meowsic out" and "Meowsic in". One port will not do - every writer on a
loopMIDI port reaches every reader, so the keyboard's own notes would come
straight back to it and the toy would play everything twice. Linux and
macOS can create both on the fly with --create.

    python serial_midi_bridge.py --list
    python serial_midi_bridge.py --midi "Meowsic out"
    python serial_midi_bridge.py --midi "Meowsic out" --midi-in "Meowsic in" --monitor
    python serial_midi_bridge.py --create Meowsic --monitor

In the DAW, "Meowsic out" is an input device (the keyboard) and "Meowsic in"
an output device (a synth). The serial port is exclusive: this holds it open,
so stop the bridge before reflashing the board.
"""

import argparse
import re
import sys

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.exit("pyserial is missing.  pip install pyserial python-rtmidi")

try:
    import rtmidi
except ImportError:
    sys.exit("python-rtmidi is missing.  pip install pyserial python-rtmidi")


# USB-UART bridges found on ESP32 dev boards, by VID:PID.
KNOWN_BRIDGES = {
    (0x10C4, 0xEA60): "CP2102",
    (0x1A86, 0x7523): "CH340",
    (0x1A86, 0x55D4): "CH9102",
    (0x0403, 0x6001): "FT232",
}

# Data bytes that follow each channel-message status, indexed by the high nibble.
CHANNEL_MESSAGE_LENGTH = {
    0x80: 2,  # note off
    0x90: 2,  # note on
    0xA0: 2,  # poly aftertouch
    0xB0: 2,  # control change
    0xC0: 1,  # program change
    0xD0: 1,  # channel aftertouch
    0xE0: 2,  # pitch bend
}

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class MidiParser:
    """Turns a byte stream into complete MIDI messages.

    The ESP32 ROM bootloader logs to UART0 on every reset and CORE_DEBUG_LEVEL
    does not suppress it, so the stream always opens with a burst of text. That
    text is ASCII, which is entirely data bytes - no status byte among them -
    so anything arriving before the first real status is dropped rather than
    being turned into stray notes.

    Running status is handled even though the firmware does not use it, since
    the looper may add it later.
    """

    def __init__(self):
        self.status = None
        self.data = []
        self.dropped = 0

    def feed(self, chunk):
        """Yield complete messages as lists of ints."""
        for byte in chunk:
            # System real-time bytes may appear anywhere, even inside another
            # message, and never disturb running status.
            if byte >= 0xF8:
                yield [byte]
                continue

            if byte >= 0x80:
                if 0xF0 <= byte <= 0xF7:
                    # The firmware sends no sysex or system-common. Treat one
                    # as a resync point rather than trying to parse it.
                    self.status = None
                    self.data = []
                    continue
                self.status = byte
                self.data = []
                continue

            if self.status is None:
                self.dropped += 1  # boot-log text, or a mid-message resync
                continue

            self.data.append(byte)
            wanted = CHANNEL_MESSAGE_LENGTH[self.status & 0xF0]
            if len(self.data) == wanted:
                yield [self.status] + self.data
                self.data = []  # keep self.status for running status


REALTIME_NAMES = {0xF8: "clock", 0xFA: "start", 0xFB: "continue", 0xFC: "stop",
                  0xFE: "active sensing", 0xFF: "reset"}


def describe(message):
    if len(message) == 1:
        return "realtime %s" % REALTIME_NAMES.get(message[0], "0x%02X" % message[0])

    status, channel = message[0] & 0xF0, (message[0] & 0x0F) + 1
    if status in (0x90, 0x80):
        note, velocity = message[1], message[2]
        name = "%s%d" % (NOTE_NAMES[note % 12], note // 12 - 1)
        # Note-on with velocity 0 is the firmware's note-off.
        kind = "note on " if status == 0x90 and velocity else "note off"
        return "ch%-2d %s %-4s (%3d) vel %3d" % (channel, kind, name, note, velocity)
    if status == 0xB0:
        return "ch%-2d cc %3d = %3d" % (channel, message[1], message[2])
    if status == 0xC0:
        return "ch%-2d program %d" % (channel, message[1])
    if status == 0xE0:
        return "ch%-2d bend %+d" % (channel, (message[2] << 7 | message[1]) - 8192)
    return "ch%-2d status 0x%02X %s" % (channel, status, message[1:])


def same_port(out_name, in_name):
    """True if the two names are one loopMIDI port seen from both ends.

    loopMIDI lists each port under the same name as an input and an output,
    and everything written to it is read back by everyone, so opening one
    port for both directions echoes the keyboard to itself. On Windows rtmidi
    appends the port's index to its name - "loopMIDI Port 1" as an output,
    "loopMIDI Port 0" as an input - so a trailing number is ignored. Name
    ports with words ("Meowsic out", "Meowsic in"), not with numbers.
    """
    if out_name is None or in_name is None:
        return False
    strip = lambda n: re.sub(r"\s+\d+$", "", n.strip())
    return strip(out_name) == strip(in_name)


def silence(midi_out):
    """All-sound-off and all-notes-off on every channel.

    Sent on the way in and on the way out. On the way in because a byte from
    the ROM boot log can land above 0x80 and be read as a status byte, which
    is the classic way a bridge starts life with a note already hanging. On
    the way out because Ctrl-C while a key is held would otherwise leave that
    note sounding in the DAW with nothing left to release it.
    """
    for channel in range(16):
        midi_out.send_message([0xB0 | channel, 120, 0])
        midi_out.send_message([0xB0 | channel, 123, 0])


class TextSpotter:
    """Shows dropped bytes that look like text, so a firmware in the wrong mode
    is obvious instead of silent.

    Every byte of ASCII is a data byte, so a board still running the self test
    or built with USB_MIDI 0 produces a stream the parser correctly discards -
    and the bridge then sits there saying nothing. Echoing the discarded text
    turns that into "DOWN pos=13 ..." scrolling past with a hint attached.
    """

    def __init__(self):
        self.buffer = b""
        self.warned = False

    def feed(self, chunk):
        self.buffer += chunk
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.strip(b"\r")
            if not line:
                continue
            if not all(0x20 <= b < 0x7F for b in line):
                continue  # genuine junk, not worth showing
            print("  text | %s" % line.decode("ascii"))
            if not self.warned and (line.startswith(b"DOWN") or line.startswith(b"UP")
                                    or b"MCP23017" in line or b"Meowsic" in line):
                self.warned = True
                print("  ---- the board is sending its text log, not MIDI.")
                print("  ---- set USB_MIDI 1 in config.h, then:  "
                      "pio run -e esp32dev -t upload")
                print("  ---- (stop this bridge first - it holds the port)")


def find_serial_port():
    candidates = []
    for port in list_ports.comports():
        chip = KNOWN_BRIDGES.get((port.vid, port.pid))
        if chip:
            candidates.append((port.device, chip))

    if not candidates:
        sys.exit("No USB-UART bridge found. Pass --port explicitly, or check "
                 "the board is plugged in and its driver installed.")
    if len(candidates) > 1:
        listing = ", ".join("%s (%s)" % c for c in candidates)
        sys.exit("Several USB-UART bridges found: %s\nPass --port." % listing)

    device, chip = candidates[0]
    print("serial : %s (%s)" % (device, chip))
    return device


def match_port(ports, name_fragment, direction):
    matches = [i for i, p in enumerate(ports) if name_fragment.lower() in p.lower()]
    if not matches:
        listing = "\n".join("  %d  %s" % (i, p) for i, p in enumerate(ports))
        hint = ""
        # Windows always lists its built-in GS synth, so "no ports" never fires
        # there. Only that synth showing up is the real sign loopMIDI is down.
        if sys.platform == "win32" and all("wavetable" in p.lower() for p in ports):
            hint = ("\n\nOnly the built-in Windows synth is present, so loopMIDI is "
                    "not running or has no port yet.\nOpen loopMIDI, click + to "
                    "add a port, and leave it running in the tray.")
        sys.exit("No MIDI %s matching %r. Available:\n%s%s"
                 % (direction, name_fragment, listing, hint))
    if len(matches) > 1:
        listing = "\n".join("  %s" % ports[i] for i in matches)
        sys.exit("%r matches several %s ports:\n%s" % (name_fragment, direction, listing))
    return matches[0]


def open_midi_out(name_fragment, create):
    """The keyboard -> DAW direction. Returns (MidiOut, port name)."""
    midi_out = rtmidi.MidiOut()
    ports = midi_out.get_ports()

    if create:
        if sys.platform == "win32":
            sys.exit("--create does not work on Windows: it has no virtual "
                     "MIDI API. Install loopMIDI, add two ports, then use "
                     "--midi and --midi-in.")
        midi_out.open_virtual_port(create)
        print("midi out: created virtual port %r  (keyboard -> DAW)" % create)
        return midi_out, create

    if not ports:
        sys.exit("No MIDI output ports exist.\n"
                 "On Windows, install loopMIDI and add a port first - a DAW "
                 "cannot be fed without one.")

    i = match_port(ports, name_fragment, "output")
    midi_out.open_port(i)
    print("midi out: %s  (keyboard -> DAW)" % ports[i])
    return midi_out, ports[i]


def open_midi_in(name_fragment, create):
    """The DAW -> keyboard direction. Returns (MidiIn, port name), or
    (None, None) when no return path was asked for."""
    if not name_fragment and not create:
        return None, None

    midi_in = rtmidi.MidiIn()
    # The default drops timing bytes; the keyboard wants MIDI clock. SysEx
    # and active sensing stay dropped - the firmware ignores both.
    midi_in.ignore_types(sysex=True, timing=False, active_sense=True)

    if create:
        midi_in.open_virtual_port(create)
        print("midi in : created virtual port %r  (DAW -> keyboard)" % create)
        return midi_in, create

    ports = midi_in.get_ports()
    if not ports:
        sys.exit("No MIDI input ports exist for --midi-in.")
    i = match_port(ports, name_fragment, "input")
    midi_in.open_port(i)
    print("midi in : %s  (DAW -> keyboard)" % ports[i])
    return midi_in, ports[i]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial device, e.g. COM5 (default: autodetect)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="must match USB_BAUD in config.h (default: %(default)s)")
    parser.add_argument("--midi", default="loopMIDI",
                        help="substring of the MIDI output port the keyboard is sent to, "
                             "i.e. the DAW's input (default: %(default)s)")
    parser.add_argument("--midi-in", metavar="NAME",
                        help="substring of the MIDI input port read and sent to the keyboard, "
                             "i.e. the DAW's output. Must be a different port from --midi")
    parser.add_argument("--create", metavar="NAME",
                        help="create virtual ports of this name, both directions, instead "
                             "(not supported on Windows)")
    parser.add_argument("--monitor", action="store_true",
                        help="decode every message to stdout")
    parser.add_argument("--list", action="store_true",
                        help="list serial and MIDI ports, then exit")
    args = parser.parse_args()

    if args.list:
        print("Serial ports:")
        for port in list_ports.comports():
            chip = KNOWN_BRIDGES.get((port.vid, port.pid), "")
            print("  %-8s %s %s" % (port.device, port.description,
                                    "<- %s" % chip if chip else ""))
        midi_ports = rtmidi.MidiOut().get_ports()
        print("\nMIDI outputs (for --midi, the keyboard -> DAW port):")
        for i, name in enumerate(midi_ports):
            print("  %d  %s" % (i, name))
        if not midi_ports:
            print("  (none - on Windows that means loopMIDI is not running)")
        in_ports = rtmidi.MidiIn().get_ports()
        print("\nMIDI inputs (for --midi-in, the DAW -> keyboard port):")
        for i, name in enumerate(in_ports):
            print("  %d  %s" % (i, name))
        if not in_ports:
            print("  (none)")
        return

    device = args.port or find_serial_port()
    midi_out, out_name = open_midi_out(args.midi, args.create)
    midi_in, in_name = open_midi_in(args.midi_in, args.create)
    if midi_in is not None and not args.create and same_port(out_name, in_name):
        sys.exit("--midi and --midi-in resolve to the same port, %r. One loopMIDI "
                 "port carries both directions at once, so the keyboard would hear "
                 "its own notes back and the toy would play everything twice.\n"
                 "Add a second port in loopMIDI and name one per direction." % out_name)
    if midi_in is None:
        print("midi in : none - pass --midi-in to send the DAW's output to the keyboard")

    try:
        # A short timeout keeps read() from blocking so Ctrl-C stays responsive
        # and the return path is polled often; it adds no latency to the
        # forward path, since read returns as soon as bytes arrive.
        link = serial.Serial(device, args.baud, timeout=0.005)
    except serial.SerialException as exc:
        sys.exit("Could not open %s: %s\n"
                 "If PlatformIO or a serial monitor has it open, close that "
                 "first - the port is exclusive." % (device, exc))

    print("bridging - Ctrl-C to stop (stop it before reflashing)\n")

    midi_parser = MidiParser()
    count = count_in = 0
    text = TextSpotter() if args.monitor else None
    try:
        while True:
            chunk = link.read(256)
            if chunk:
                before = midi_parser.dropped
                for message in midi_parser.feed(chunk):
                    midi_out.send_message(message)
                    count += 1
                    if args.monitor and message[0] != 0xF8:   # 24 clocks a beat: not shown
                        print(describe(message))
                if text and midi_parser.dropped > before:
                    text.feed(chunk)

            # The return path: whatever the DAW sent since the last pass.
            while midi_in is not None:
                event = midi_in.get_message()
                if event is None:
                    break
                message = event[0]
                link.write(bytes(message))
                count_in += 1
                if args.monitor and message[0] != 0xF8:   # clock would drown the rest
                    print("  <- " + describe(message))
    except KeyboardInterrupt:
        print("\n%d messages forwarded to the DAW, %d to the keyboard, "
              "%d stray bytes dropped" % (count, count_in, midi_parser.dropped))
    finally:
        silence(midi_out)
        if midi_in is not None:
            # Whatever the DAW was holding into the keyboard ends with the bridge.
            link.write(bytes([0xB0, 123, 0, 0xB1, 123, 0]))
            link.flush()
            del midi_in
        link.close()
        del midi_out


if __name__ == "__main__":
    main()
