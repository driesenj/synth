#pragma once
#include <stdint.h>

// The performance-event router (docs/firmware.md section 1). Whoever plays a
// note - the keys, MIDI in on the keys channel, the arp, a loop - hands it
// here and it does the same things: a tap into the toy at the toy's own
// pitch, a note on MIDI out transposed by the base pitch pot, and CV/gate
// with the pots applied - on the pair the switch selects for the keys, the
// arp and MIDI, on its own pair for a loop. MIDI in's other channel drives
// the other pair straight through cv::, not through here, and without the
// pots.
//
// Two things happen on the way. Notes from the keys and MIDI are offered to
// the arp first, and when it is on they go no further - the arp plays them.
// And everything except the loops' own playback is offered to the active
// looper, which records it while it is recording.
namespace router {

// Who played the note. MIDI-in notes are not echoed to MIDI out - there is
// no thru, the DAW hears its own notes already - so they neither send nor
// end anything there; every other source does. The loop's taps into the
// toy are dropped when the toy is running late (LOOP_TAP_LATE_MS); MIDI
// and CV still get them.
enum Source : uint8_t { SRC_KEYS, SRC_MIDI, SRC_LOOP, SRC_ARP };

void begin();

// Which CV/gate pair the keys drive and which loop they record into: 0 =
// A, 1 = B. The other pair is MIDI in's other channel and the other loop's.
// Flipping it drops every note on both pairs, so nothing can stay held on a
// pair that changed hands; a loop's note comes back at its next event.
void setKeysChannel(uint8_t ch);
uint8_t keysChannel();
uint8_t otherChannel();

// The pots. Base pitch moves MIDI out (rounded) and CV; tune moves CV only.
// They apply on both pairs, to everything but MIDI in's direct notes.
void setPitch(float baseSemis, float tuneSemis);

// Performance events. A note already sounding is retriggered. The keys, MIDI
// and the arp land on the keys' pair; a loop names its own.
static constexpr uint8_t KEYS_PAIR = 0xFF;
void noteOn(uint8_t note, Source src = SRC_KEYS, uint8_t pair = KEYS_PAIR);
void noteOff(uint8_t note, Source src = SRC_KEYS, uint8_t pair = KEYS_PAIR);

// The voice buttons and catface from the panel: a tap on the press, CC
// 127 / 0 out, and recorded by the looper.
void button(uint8_t cc, bool down);

// The same button played back by the loop: a tap and the CC pair, not
// recorded.
void loopButton(uint8_t cc);

// Everything the keys' path is sounding stops - MIDI note-offs, the keys'
// CV pair cleared - and nothing else. The arp switching on.
void releaseKeysPath();

// A toy button tapped without a CC out - the rhythm cycle, STOP into the
// toy, the demo song, everything MIDI in asks for. Not a performance event.
void tapToy(uint8_t cc);
void tapToyPos(uint8_t pos);   // by keybed position: volume and tempo have no CC of their own

// Keybed position of a button, 0xFF if the map has none.
uint8_t posOfCC(uint8_t cc);

// Every MIDI note believed sounding gets its note-off and both CV pairs drop
// their gates. panic() adds CC 120 / 123 on MIDI out; allNotesOff() is the
// same without them, for when the request itself came in over MIDI. The
// toy's queue is the caller's (inject::flush).
void allNotesOff();
void panic();

}  // namespace router
