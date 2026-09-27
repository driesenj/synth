#!/usr/bin/env python3
"""Send test MIDI to the keyboard through the bridge's return port.

For the acceptance runs in docs/tests.md, so MIDI in can be checked with
known messages and no DAW. The bridge must be running with --midi-in on the
port this sends to; the default port name is the one the docs use.

    pip install python-rtmidi

    python midi_send.py --list
    python midi_send.py note 57                       # A3 on, 0.5 s, off - channel 1
    python midi_send.py note 57 --ch 2 --hold 2       # on channel 2, held 2 s
    python midi_send.py chord 57 61 64                # three notes on, then off
    python midi_send.py scale 57 84 --hold 0.15       # every note from A3 to C6
    python midi_send.py cc 102 127                    # quantise loop on
    python midi_send.py pc 2                          # program 2: meow
    python midi_send.py bend 8191 --hold 1            # full up, then centre
    python midi_send.py sustain 57 60                 # pedal down, notes on and off, pedal up
    python midi_send.py raw 90 39 64                  # any bytes, hex
    python midi_send.py panic                         # CC 123 on channels 1 and 2
    python midi_send.py clock 100 --hold 10           # start, 10 s of MIDI clock at 100 BPM, stop
    python midi_send.py start / stop / continue       # transport on its own

Channels are 1-16 as a DAW shows them.
"""

import argparse
import sys
import time

try:
    import rtmidi
except ImportError:
    sys.exit("python-rtmidi is missing.  pip install python-rtmidi")

DEFAULT_PORT = "Meowsic in"


def open_port(name_fragment):
    out = rtmidi.MidiOut()
    ports = out.get_ports()
    matches = [i for i, p in enumerate(ports) if name_fragment.lower() in p.lower()]
    if not matches:
        listing = "\n".join("  %d  %s" % (i, p) for i, p in enumerate(ports))
        sys.exit("No MIDI output matching %r. Available:\n%s\n\nThis is the port the "
                 "bridge reads with --midi-in; on Windows add it in loopMIDI."
                 % (name_fragment, listing))
    if len(matches) > 1:
        sys.exit("%r matches several ports:\n%s"
                 % (name_fragment, "\n".join("  %s" % ports[i] for i in matches)))
    out.open_port(matches[0])
    print("port : %s" % ports[matches[0]])
    return out


def note_name(n):
    return "%s%d" % (("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[n % 12], n // 12 - 1)


class Sender:
    def __init__(self, out, channel):
        self.out = out
        self.ch = channel - 1

    def send(self, *msg):
        self.out.send_message(list(msg))

    def note_on(self, n, vel=100):
        print("  note on  %-4s (%d)" % (note_name(n), n))
        self.send(0x90 | self.ch, n, vel)

    def note_off(self, n):
        print("  note off %-4s (%d)" % (note_name(n), n))
        self.send(0x80 | self.ch, n, 0)

    def cc(self, num, val):
        print("  cc %d = %d" % (num, val))
        self.send(0xB0 | self.ch, num, val)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--midi", default=DEFAULT_PORT,
                        help="substring of the port name (default: %(default)r)")
    parser.add_argument("--ch", type=int, default=1, help="MIDI channel 1-16 (default: 1)")
    parser.add_argument("--hold", type=float, default=0.5,
                        help="seconds a note, bend or pedal is held (default: 0.5)")
    parser.add_argument("--gap", type=float, default=0.1,
                        help="seconds between the notes of a scale (default: 0.1)")
    parser.add_argument("--list", action="store_true", help="list MIDI output ports and exit")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("note").add_argument("notes", type=int, nargs="+", help="MIDI note numbers, one after another")
    sub.add_parser("chord").add_argument("notes", type=int, nargs="+")
    sc = sub.add_parser("scale")
    sc.add_argument("low", type=int)
    sc.add_argument("high", type=int)
    c = sub.add_parser("cc")
    c.add_argument("num", type=int)
    c.add_argument("val", type=int)
    sub.add_parser("pc").add_argument("program", type=int)
    sub.add_parser("bend").add_argument("amount", type=int, help="-8192 .. 8191")
    sub.add_parser("sustain").add_argument("notes", type=int, nargs="+")
    sub.add_parser("raw").add_argument("bytes", nargs="+", help="hex bytes, e.g. 90 39 64")
    sub.add_parser("panic")
    ck = sub.add_parser("clock")
    ck.add_argument("bpm", type=float)
    ck.add_argument("--no-transport", action="store_true", help="clock only, no start / stop around it")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("continue")
    args = parser.parse_args()

    if args.list:
        for i, p in enumerate(rtmidi.MidiOut().get_ports()):
            print("  %d  %s" % (i, p))
        return
    if not args.cmd:
        parser.print_help()
        return
    if not 1 <= args.ch <= 16:
        sys.exit("--ch must be 1-16")

    out = open_port(args.midi)
    s = Sender(out, args.ch)
    print("ch %d:" % args.ch)

    try:
        if args.cmd == "note":
            for n in args.notes:
                s.note_on(n)
                time.sleep(args.hold)
                s.note_off(n)
                if len(args.notes) > 1:
                    time.sleep(args.gap)

        elif args.cmd == "chord":
            for n in args.notes:
                s.note_on(n)
            time.sleep(args.hold)
            for n in args.notes:
                s.note_off(n)

        elif args.cmd == "scale":
            step = 1 if args.high >= args.low else -1
            for n in range(args.low, args.high + step, step):
                s.note_on(n)
                time.sleep(args.hold)
                s.note_off(n)
                time.sleep(args.gap)

        elif args.cmd == "cc":
            s.cc(args.num, args.val)

        elif args.cmd == "pc":
            print("  program %d" % args.program)
            s.send(0xC0 | s.ch, args.program)

        elif args.cmd == "bend":
            v = max(-8192, min(8191, args.amount)) + 8192
            print("  bend %+d" % (v - 8192))
            s.send(0xE0 | s.ch, v & 0x7F, v >> 7)
            time.sleep(args.hold)
            print("  bend 0")
            s.send(0xE0 | s.ch, 0x00, 0x40)

        elif args.cmd == "sustain":
            s.cc(64, 127)
            for n in args.notes:
                s.note_on(n)
                time.sleep(args.gap)
                s.note_off(n)
            print("  (released notes should still sound) holding %.1f s" % args.hold)
            time.sleep(args.hold)
            s.cc(64, 0)

        elif args.cmd == "raw":
            msg = [int(b, 16) for b in args.bytes]
            print("  raw %s" % " ".join("%02X" % b for b in msg))
            s.send(*msg)

        elif args.cmd == "panic":
            for ch in (0, 1):
                s.send(0xB0 | ch, 123, 0)
            print("  all notes off, channels 1 and 2")

        elif args.cmd == "clock":
            # 24 clocks a beat, paced on a busy-wait: sleep() on Windows is
            # good to ~15 ms and a clock at 120 BPM is every 20.8 ms.
            interval = 60.0 / args.bpm / 24.0
            total = int(args.hold / interval)
            if not args.no_transport:
                print("  start")
                s.send(0xFA)
            print("  clock: %d ticks over %.1f s at %.1f BPM" % (total, args.hold, args.bpm))
            t0 = time.perf_counter()
            for i in range(total):
                target = t0 + i * interval
                while True:
                    left = target - time.perf_counter()
                    if left <= 0:
                        break
                    if left > 0.02:
                        time.sleep(0.001)
                s.send(0xF8)
            if not args.no_transport:
                print("  stop")
                s.send(0xFC)

        elif args.cmd == "start":
            print("  start")
            s.send(0xFA)
        elif args.cmd == "stop":
            print("  stop")
            s.send(0xFC)
        elif args.cmd == "continue":
            print("  continue")
            s.send(0xFB)
    finally:
        time.sleep(0.05)   # let the last message leave before the port closes
        del out


if __name__ == "__main__":
    main()
