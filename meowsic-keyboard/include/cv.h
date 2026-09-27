#pragma once
#include <stdint.h>

// The two CV/gate pairs and the AUX output (docs/firmware.md section 3.5).
// Channel 0 is A (DAC 0x60, PIN_GATE), channel 1 is B (0x61, PIN_GATE2).
//
// Each channel keeps a stack of its held notes in press order, last-note
// priority: the newest sounds; release it and the one under it comes back
// with the gate still high. Pitch is 1 V/oct from CV_ZERO_NOTE, plus the
// pots' offset for notes that want it (the keys' path: keys, arp, loops)
// and none for notes that do not (MIDI in's direct channel), plus pitch
// bend per channel, with glide and the gate mode taken from settings. Wire
// must be up: the DACs share the bus with the expander.
namespace cv {

static constexpr uint8_t N_CH = 2;

void begin();   // gates low, both DACs to 0

void noteOn(uint8_t ch, uint8_t note, bool withOffset = true);
void noteOff(uint8_t ch, uint8_t note);
void allOff(uint8_t ch);              // stack cleared, sustain released, gate low; pitch left where it is

void setOffset(uint8_t ch, float semis);    // base pitch + tune, for the notes that take it
void setBend(uint8_t ch, float semis);
void setSustain(uint8_t ch, bool on);       // holds released notes until off

bool gate(uint8_t ch);
bool sounding(uint8_t ch, uint8_t &note);   // false if nothing is held
int32_t written(uint8_t ch);                // last DAC code sent, -1 if none

// Glide slew, retrigger timing, DAC writes when a code changed. Every loop.
void service();

// After an I2C recovery: write both DACs again whatever they last held.
void resync();

}  // namespace cv
