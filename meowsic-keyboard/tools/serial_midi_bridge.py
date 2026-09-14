#!/usr/bin/env python3
"""Bridge the Meowsic's raw serial MIDI onto a virtual MIDI port.

The ESP32-WROOM-32 has no native USB, so it cannot enumerate as a class-
compliant MIDI device. With USB_MIDI 1 the firmware writes raw MIDI bytes to
UART0 at USB_BAUD instead, and this forwards them to a MIDI port that a DAW
can open.

    pip install pyserial python-rtmidi

Windows has no API for creating virtual MIDI ports, so one has to exist
already - install loopMIDI and add a port there first. Linux and macOS can
create one on the fly with --create.

    python serial_midi_bridge.py --list
    python serial_midi_bridge.py --midi loopMIDI
    python serial_midi_bridge.py --port COM5 --midi loopMIDI --monitor

The serial port is exclusive: this holds it open, so stop the bridge before
reflashing the board.
"""

import argparse
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


def describe(message):
    if len(message) == 1:
        return "realtime 0x%02X" % message[0]

    status, channel = message[0] & 0xF0, (message[0] & 0x0F) + 1
    if status in (0x90, 0x80):
        note, velocity = message[1], message[2]
        name = "%s%d" % (NOTE_NAMES[note % 12], note // 12 - 1)
        # Note-on with velocity 0 is the firmware's note-off.
        kind = "note on " if status == 0x90 and velocity else "note off"
        return "ch%-2d %s %-4s (%3d) vel %3d" % (channel, kind, name, note, velocity)
    if status == 0xB0:
        return "ch%-2d cc %3d = %3d" % (channel, message[1], message[2])
    return "ch%-2d status 0x%02X %s" % (channel, status, message[1:])


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


def open_midi_out(name_fragment, create):
    midi_out = rtmidi.MidiOut()
    ports = midi_out.get_ports()

    if create:
        if sys.platform == "win32":
            sys.exit("--create does not work on Windows: it has no virtual "
                     "MIDI API. Install loopMIDI, add a port, then use --midi.")
        midi_out.open_virtual_port(create)
        print("midi   : created virtual port %r" % create)
        return midi_out

    if not ports:
        sys.exit("No MIDI output ports exist.\n"
                 "On Windows, install loopMIDI and add a port first - a DAW "
                 "cannot be fed without one.")

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
        sys.exit("No MIDI output matching %r. Available:\n%s%s"
                 % (name_fragment, listing, hint))
    if len(matches) > 1:
        listing = "\n".join("  %s" % ports[i] for i in matches)
        sys.exit("%r matches several ports:\n%s" % (name_fragment, listing))

    midi_out.open_port(matches[0])
    print("midi   : %s" % ports[matches[0]])
    return midi_out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="serial device, e.g. COM5 (default: autodetect)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="must match USB_BAUD in config.h (default: %(default)s)")
    parser.add_argument("--midi", default="loopMIDI",
                        help="substring of the MIDI output port name (default: %(default)s)")
    parser.add_argument("--create", metavar="NAME",
                        help="create a virtual port instead (not supported on Windows)")
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
        print("\nMIDI outputs:")
        for i, name in enumerate(midi_ports):
            print("  %d  %s" % (i, name))
        if not midi_ports:
            print("  (none - on Windows that means loopMIDI is not running)")
        return

    device = args.port or find_serial_port()
    midi_out = open_midi_out(args.midi, args.create)

    try:
        # A short timeout keeps read() from blocking so Ctrl-C stays responsive;
        # it does not add latency, since read returns as soon as bytes arrive.
        link = serial.Serial(device, args.baud, timeout=0.05)
    except serial.SerialException as exc:
        sys.exit("Could not open %s: %s\n"
                 "If PlatformIO or a serial monitor has it open, close that "
                 "first - the port is exclusive." % (device, exc))

    print("bridging - Ctrl-C to stop (stop it before reflashing)\n")

    midi_parser = MidiParser()
    count = 0
    text = TextSpotter() if args.monitor else None
    try:
        while True:
            chunk = link.read(256)
            if not chunk:
                continue
            before = midi_parser.dropped
            for message in midi_parser.feed(chunk):
                midi_out.send_message(message)
                count += 1
                if args.monitor:
                    print(describe(message))
            if text and midi_parser.dropped > before:
                text.feed(chunk)
    except KeyboardInterrupt:
        print("\n%d messages forwarded, %d stray bytes dropped"
              % (count, midi_parser.dropped))
    finally:
        silence(midi_out)
        link.close()
        del midi_out


if __name__ == "__main__":
    main()
