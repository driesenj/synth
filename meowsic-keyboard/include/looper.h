#pragma once
#include <stdint.h>

// The loopers (docs/firmware.md 3.2): one per CV/gate pair. Each records
// performance events - notes from the keys, MIDI channel 1 and the arp, the
// voice buttons and catface - as the router sees them, positioned in clock
// ticks, and plays them back through the same router onto its own pair, so
// a note from loop A reaches the toy, MIDI out and CV/gate A exactly as a
// key would when A is selected.
//
// The CV select switch names the *active* loop: the keys record into it,
// the transport buttons and the LED belong to it, and the other loop keeps
// running untouched. Flip the switch and the loop just built stays where it
// is; the other pair is free for the next one.
//
//   empty --record--> armed --first note--> recording --record/play--> playing
//   playing --record--> overdub --record--> playing        play: play / stop
//   stop keeps the loop; record long undoes the newest layer; play long
//   (while stopped) clears
//
// Each pass of an overdub is a layer. Every note-on has its note-off in the
// same layer: a note held across the loop point is closed at the end of the
// pass and opened again at the start of the next, so undoing a layer never
// leaves a note hanging. Quantise loop is applied at playback from the raw
// ticks, so it can be flipped while the loop runs.
//
// The first loop to record sets the beat grid; while any loop is running, a
// new recording's first note snaps to that grid instead of moving it.
namespace looper {

enum State : uint8_t { EMPTY, ARMED, RECORDING, PLAYING, OVERDUB, STOPPED };

static constexpr uint8_t N_LOOPS = 2;   // one per CV channel
static constexpr uint8_t ACTIVE  = 0xFF;

void begin();
void service();   // every loop, after clk::service()

// Which loop the keys record into and the transport controls: the switch.
void setActive(uint8_t ch);
uint8_t active();

State    state(uint8_t ch = ACTIVE);
uint16_t lengthTicks(uint8_t ch = ACTIVE);
uint16_t eventCount(uint8_t ch = ACTIVE);
uint8_t  layer(uint8_t ch = ACTIVE);          // the newest layer recorded (0 = the first pass)
uint32_t positionTicks(uint8_t ch = ACTIVE);  // within the pass; 0 when not playing
uint32_t passStart(uint8_t ch = ACTIVE);      // absolute tick the current pass began on
bool     anyRunning();                        // some loop is playing or overdubbing

// The panel's transport, on the active loop.
void record();
void play();
void stop();
void undo();
void clear();

// MIDI's transport and panic: every loop.
void restartAll();   // MIDI start: from the top, playing
void resumeAll();    // MIDI continue: play what is stopped
void stopAll();

// Recording, from the router, into the active loop. Every source but the
// loops themselves.
bool recording();   // the active loop is armed, recording or overdubbing
void noteOn(uint8_t note);
void noteOff(uint8_t note);
void button(uint8_t cc);

}  // namespace looper
