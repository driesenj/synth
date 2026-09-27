#pragma once
#include <stdint.h>

// The transport clock (docs/firmware.md 3.3): one tick counter at
// TICKS_PER_BEAT per beat that everything time-based reads - the looper,
// the arp, the AUX shapes, the beat LED. Three sources drive it, in
// priority order: MIDI clock from either socket, the clock jack, and the
// internal clock from tap tempo. An external source takes over on its first
// tick and hands back after CLOCK_EXT_TIMEOUT_MS of silence, at the tempo
// it was last running at, without a jump in the count.
//
// Ticks are polled, not delivered: tick() is monotonic and whoever needs to
// act on time asks where it is now. Between external pulses the count is
// interpolated from the last interval, so a note recorded between two MIDI
// clocks lands where it was played, not on the previous clock.
//
// Beat 1 - the origin bars are counted from - is wherever the loop, a tap
// series or a MIDI start last put it.
namespace clk {

enum Source : uint8_t { SRC_INTERNAL, SRC_MIDI, SRC_JACK };

void begin();
void service();          // every loop: advance, time out external sources, MIDI clock out

uint32_t tick();         // absolute, monotonic
Source   source();
float    bpm();          // the effective tempo, whichever source

// Beat 1 is now: the tick count keeps going, but bars, the beat LED and the
// AUX shapes count from here, and the internal clock's next tick is exactly
// one tick away. The looper's first note calls this.
void resetPhase();
uint32_t origin();
uint32_t ticksSinceOrigin();
uint32_t nextBeatTick();  // the first tick on or after now that is a whole beat from the origin

// The beat LED: milliseconds since the last beat began, and which beat of
// the bar that was (0 = beat 1).
uint32_t beatAgeMs();
uint8_t  beatInBar();

// Tap tempo on the ♪ button. Three taps set the tempo; each further tap
// refines it. The tap that sets it is beat 1. Returns true when the tempo
// changed.
bool tap();
bool tapped();            // a tempo has been tapped since boot

// From midi_in: a MIDI clock byte arrived.
void midiTick();

// Transport out. Start / stop go with the loop; they are sent only when the
// master is not MIDI clock in.
void sendStart();
void sendStop();

}  // namespace clk
