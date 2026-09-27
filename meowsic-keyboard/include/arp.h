#pragma once
#include <stdint.h>

// The arpeggiator (docs/firmware.md 3.8). It is told about every key and
// MIDI-channel-1 note edge whether it is on or not, so it knows what is
// held the moment it is switched on. When on, the router does not sound
// those notes itself; the arp plays the held ones one at a time on the
// clock's ARP_DIV grid, in the chosen order, as performance events through
// the router - so they reach the toy, MIDI out, the keys' CV pair, and the
// looper when it is recording. Off, held keys go back to sounding directly.
namespace arp {

void begin();

void noteOn(uint8_t note);
void noteOff(uint8_t note);

// Steps on the clock; also notices the setting being switched. Every loop.
void service();

// The note the arp is sounding, if any, gets its note-off. Panic.
void allOff();

}  // namespace arp
