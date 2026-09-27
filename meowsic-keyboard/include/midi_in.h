#pragma once
#include <stdint.h>

// MIDI in, both sockets (docs/firmware.md section 3.4): the DIN socket on
// UART2 always, and UART0 when USB_MIDI is 1 - the bridge's return path from
// the DAW. One parser per port, each with its own running status, both
// feeding one handler:
//
//   notes on the keys channel      -> router, like a key (no MIDI thru)
//   notes on the other channel     -> the other CV/gate pair, direct
//   CC 20-34 / 35-38, program 0-4  -> the toy's buttons, tapped
//   CC 1, 64, pitch bend           -> AUX (mod wheel), sustain, CV bend
//   CC 102-110                     -> settings, as the buttons would
//   CC 120 / 123                   -> everything off
//   clock, start, stop, continue   -> the clock and the loops' transport
//
// Real-time bytes are handled wherever they land; SysEx, system common and
// active sensing are skipped.
namespace midi_in {

void begin();
void service();   // drain both UARTs; every loop

}  // namespace midi_in
