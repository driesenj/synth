#pragma once
#include <stdint.h>

// The panel (docs/firmware.md section 2): what the 15 scanned buttons, the
// two pots and the CV select switch do.
//
// Buttons come in two kinds. The voice buttons and catface are performance
// events and go straight to the router on the press. The rest have a short
// and a long function: the long one fires the moment the hold reaches
// LONG_PRESS_MS, the short one on a release before that. Settings are
// changed here directly, with a blink on the LED; the looper's transport
// and panic come out as commands for main.cpp to act on, so this file knows
// nothing about the looper.
namespace controls {

enum Cmd : uint8_t {
    CMD_TAP_TEMPO,   // ♪ short
    CMD_STOP,        // STOP short - the loop stops; the toy's STOP is tapped here
    CMD_PANIC,       // STOP long
    CMD_RECORD,      // record short
    CMD_UNDO,        // record long
    CMD_PLAY,        // play short
    CMD_CLEAR,       // play long
};

void begin();

// Every K_CC edge from the scan.
void onButton(uint8_t cc, bool down);

// Commands for main, in order. False when there are none.
bool nextCommand(Cmd &c);

// Long presses, the pots, the switch. Every loop.
void service();

// The pots as last read: base pitch in semitones, quantised or not per the
// setting; tune in semitones.
float basePitch();
float tune();

// The CV select switch: 0 = A, 1 = B.
uint8_t cvChannel();

// Setting changes, with their LED blink codes: two blue pulses for on, one
// for off, n + 1 for the n-th entry of a cycle. The buttons and MIDI CC
// 102-110 both come through here. An out-of-range value is ignored.
void setQuantLoop(bool on);
void setQuantPitch(bool on);
void setGateMode(uint8_t mode);
void setGlide(uint8_t glide);
void setAuxWave(uint8_t wave);
void setAuxRate(uint8_t rate);
void setArp(bool on);
void setArpOrder(uint8_t order);
void setArpDiv(uint8_t div);
void setToyNotes(bool on);   // catface long: the toy plays notes, or only its buttons

}  // namespace controls
