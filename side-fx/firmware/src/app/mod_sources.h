// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the modulation sources (see engine/modulation.h for what each
// value means).
//
// Process() runs in the audio interrupt, once per block before the engine:
// CV readings to volts through the calibration, the two LFOs, the random
// source and the envelope follower from the preset's settings (synced ones
// lock their phase to the bar), the MIDI values the main loop left.
//
// LFO rates: 0.02..20 Hz, or a note value from 4 BAR to 1/64 when synced.
// RANDOM: a new value at its rate; SMOOTH glides between values (cosine)
// instead of stepping. ENVELOPE: peak follower of the input (both
// channels), ATTACK 1..500 ms, RELEASE 10 ms..5 s, GAIN 0..+24 dB, clamped
// to 0..1.

#ifndef SIDEFX_APP_MOD_SOURCES_H_
#define SIDEFX_APP_MOD_SOURCES_H_

#include <stddef.h>
#include <stdint.h>

#include "engine/frame.h"
#include "engine/modulation.h"
#include "engine/preset.h"
#include "engine/tempo_state.h"

namespace sidefx {

// volts = (raw - offset) * scale. Nominal for the input stage
// (V_adc = 1.676 V - 0.27 * V_in, ADC full scale 3.3 V): offset 0.5079,
// scale -12.22 V per unit.
struct CvCalibration {
  float offset[4];
  float scale[4];
};

void InitCvCalibration(CvCalibration* calibration);

class ModSources {
 public:
  ModSources() { }
  ~ModSources() { }

  void Init();
  void set_calibration(const CvCalibration& calibration) {
    calibration_ = calibration;
  }

  // Audio interrupt. cv_raw: hal::ReadCv() of the four inputs.
  void Process(const Preset& preset, const TempoState& tempo,
               const float* cv_raw, const Frame* in, size_t size);

  const ModValues& values() const { return values_; }
  float cv_raw(int channel) const { return cv_raw_[channel]; }
  float cv_volts(int channel) const { return cv_volts_[channel]; }

  // Main loop, from MIDI.
  void SetCc(int which, float value);  // 0 = CC A, 1 = CC B; 0..1
  void NoteOn(int note);
  void NoteOff(int note);
  void AllNotesOff();

 private:
  CvCalibration calibration_;
  ModValues values_;
  float cv_raw_[4];
  float cv_volts_[4];
  // Synced phases count from a 12-bar window: the shortest span every
  // note value (dotted and triplet ones too, up to 4 bars) divides.
  static const int kSyncBars = 12;

  float NextRandom();
  // The phase of a rate in cycles: synced ones from the bar position,
  // free ones advanced by dt. True when it wrapped (a new cycle).
  bool Advance(uint16_t rate, bool sync, float bar_beats, float dt,
               float* phase);

  int bar_count_;
  float last_bar_phase_;
  float lfo_phase_[2];
  float lfo_steps_value_[2];
  float random_phase_;
  float random_from_;
  float random_to_;
  float envelope_;
  volatile float cc_[2];
  volatile int8_t notes_[16];  // held notes, most recent last; -1 = empty
  volatile uint8_t num_notes_;
  volatile float note_value_;
  uint32_t random_state_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_MOD_SOURCES_H_
