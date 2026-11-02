// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: modulation sources and assignments.
//
// Any parameter (and the preset's WET) can take one source with a depth;
// the engine adds depth * source to the knob's value and clamps to 0..1.
// Each slot's send can also follow one source as a gate (see engine.h).
//
// Source values, computed once per audio block (app/mod_sources.h):
//   CV1..CV4   volts / 4, not clamped: +-5 V gives +-1.25. A pitch
//              parameter spanning 48 semitones (+-24) then tracks 1 V/oct
//              at depth +100 %.
//   LFO1/LFO2  -1..+1
//   RANDOM     -1..+1
//   ENVELOPE   0..1, the input's level (envelope follower)
//   CC A, CC B 0..1, two MIDI controllers (numbers in the settings)
//   NOTE       (last MIDI note - 60) / 48: 1 semitone per note on a +-24 st
//              parameter at +100 %
//   GATE       1 while a MIDI note is held, else 0

#ifndef SIDEFX_ENGINE_MODULATION_H_
#define SIDEFX_ENGINE_MODULATION_H_

#include <stdint.h>

namespace sidefx {

enum ModSource {
  MOD_OFF,
  MOD_CV1,
  MOD_CV2,
  MOD_CV3,
  MOD_CV4,
  MOD_LFO1,
  MOD_LFO2,
  MOD_RANDOM,
  MOD_ENVELOPE,
  MOD_CC_A,
  MOD_CC_B,
  MOD_NOTE,
  MOD_GATE,
  NUM_MOD_SOURCES
};

// Names for the screen, at most 5 characters: "OFF", "CV1", "LFO1", "RND",
// "ENV", "CC A", "CC B", "NOTE", "GATE".
extern const char* const kModSourceNames[NUM_MOD_SOURCES];

struct ModAssign {
  uint8_t source;  // ModSource
  int8_t depth;    // -100..+100 %: depth / 100 * source is added to the value
};

struct ModValues {
  float value[NUM_MOD_SOURCES];  // value[MOD_OFF] is always 0
};

// Send gates: the gate opens above kGateOnThreshold and closes below
// kGateOffThreshold (1.2 V and 0.8 V on a CV input).
const float kGateOnThreshold = 0.3f;
const float kGateOffThreshold = 0.2f;

// LFO waveforms (Preset::lfo[].shape).
enum LfoShape {
  LFO_SINE,
  LFO_TRIANGLE,
  LFO_RAMP_UP,
  LFO_RAMP_DOWN,
  LFO_SQUARE,
  LFO_STEPS,  // a new random value every cycle
  NUM_LFO_SHAPES
};

extern const char* const kLfoShapeNames[NUM_LFO_SHAPES];  // "SINE", "TRI", "RAMP+", "RAMP-", "SQUARE", "S&H"

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_MODULATION_H_
