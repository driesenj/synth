#pragma once
#include <stdint.h>

// The AUX output (docs/firmware.md 3.6): the 8-bit DAC on PIN_AUX, 0-4.5 V
// at the jack, drawing one of eleven shapes phase-locked to the clock. The
// period is the *aux rate* setting: the active loop's pass (a bar when no
// loop is running), the bar, or the beat. Saw, triangle, sine and square
// are LFOs at that period; random is a new level each period; clock and
// reset are 10 ms pulses, one per beat (per 16th at the beat rate) and one
// per period; envelope is a decay from full scale on every note that lands
// on the keys' CV pair; mod wheel is MIDI CC 1 straight through; off is 0 V.
//
// The file is auxout, not aux: "aux" is a reserved DOS device name, reserved
// with any extension, so Windows tools - git among them - cannot open a file
// called aux.h or aux.cpp. The namespace is aux, which is only C++.
namespace aux {

void begin();
void service();                   // every loop: compute and write on change

void trigger();                   // a note-on on the keys' pair: the envelope restarts
void setModWheel(uint8_t value);  // CC 1, 0-127

uint8_t level();                  // what the DAC holds, 0-255

}  // namespace aux
