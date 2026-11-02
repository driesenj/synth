// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: CV, LFOs, random, envelope follower and MIDI as modulation.

#include "app/mod_sources.h"

#include <math.h>
#include <string.h>

#include "engine/config.h"
#include "engine/params.h"

namespace sidefx {

namespace {

const float kPi = 3.14159265358979f;
const float kTwoPi = 2.0f * kPi;
const float kMinLfoHz = 0.02f;
const float kMaxLfoHz = 20.0f;

inline float Wrap(float x) { return x - floorf(x); }

inline float Clamp(float x, float lo, float hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

float Shape(int shape, float phase, float steps_value) {
  switch (shape) {
    case LFO_SINE:
      return sinf(kTwoPi * phase);
    case LFO_TRIANGLE:
      // -1 at 0.75, +1 at 0.25: starts at 0 rising, like the sine.
      return phase < 0.25f ? 4.0f * phase
          : (phase < 0.75f ? 2.0f - 4.0f * phase : 4.0f * phase - 4.0f);
    case LFO_RAMP_UP:
      return 2.0f * phase - 1.0f;
    case LFO_RAMP_DOWN:
      return 1.0f - 2.0f * phase;
    case LFO_SQUARE:
      return phase < 0.5f ? 1.0f : -1.0f;
    case LFO_STEPS:
      return steps_value;
    default:
      return 0.0f;
  }
}

}  // namespace

void InitCvCalibration(CvCalibration* calibration) {
  for (int i = 0; i < 4; ++i) {
    calibration->offset[i] = 0.5079f;
    calibration->scale[i] = -12.22f;
  }
}

void ModSources::Init() {
  InitCvCalibration(&calibration_);
  memset(&values_, 0, sizeof(values_));
  for (int i = 0; i < 4; ++i) {
    cv_raw_[i] = calibration_.offset[i];
    cv_volts_[i] = 0.0f;
  }
  bar_count_ = 0;
  last_bar_phase_ = 0.0f;
  random_state_ = 0x5eed1234u;
  for (int i = 0; i < 2; ++i) {
    lfo_phase_[i] = 0.0f;
    lfo_steps_value_[i] = NextRandom();
    cc_[i] = 0.0f;
  }
  random_phase_ = 0.0f;
  random_from_ = 0.0f;
  random_to_ = NextRandom();
  envelope_ = 0.0f;
  for (int i = 0; i < 16; ++i) {
    notes_[i] = -1;
  }
  num_notes_ = 0;
  note_value_ = 0.0f;
}

float ModSources::NextRandom() {
  random_state_ = random_state_ * 1664525u + 1013904223u;
  return float(int32_t(random_state_)) * (1.0f / 2147483648.0f);
}

bool ModSources::Advance(uint16_t rate, bool sync, float bar_beats,
                         float dt, float* phase) {
  const float value = PresetValue(rate);
  const float previous = *phase;
  if (sync) {
    const float beats = kNoteValues[SyncedRateIndex(value)].beats;
    *phase = Wrap(bar_beats / beats);
  } else {
    *phase = Wrap(previous + ExpMap(value, kMinLfoHz, kMaxLfoHz) * dt);
  }
  return *phase < previous;
}

void ModSources::Process(const Preset& preset, const TempoState& tempo,
                         const float* cv_raw, const Frame* in, size_t size) {
  float* v = values_.value;
  v[MOD_OFF] = 0.0f;

  for (int i = 0; i < 4; ++i) {
    cv_raw_[i] = cv_raw[i];
    cv_volts_[i] = (cv_raw[i] - calibration_.offset[i]) * calibration_.scale[i];
    v[MOD_CV1 + i] = cv_volts_[i] * 0.25f;
  }

  // Bars, counted from the tempo's wraps, for synced cycles longer than a
  // bar (and dotted ones, which only meet the bar again after 3). A
  // downbeat (MIDI START, a clock starting) starts the count over, and
  // its jump back is no wrap.
  if (tempo.downbeat) {
    bar_count_ = 0;
  } else if (tempo.bar_phase < last_bar_phase_ - 0.5f) {
    bar_count_ = (bar_count_ + 1) % kSyncBars;
  }
  last_bar_phase_ = tempo.bar_phase;
  const float bar_beats = (float(bar_count_) + tempo.bar_phase) * 4.0f;
  const float dt = float(size) / kSampleRate;

  for (int i = 0; i < 2; ++i) {
    const LfoPreset& lfo = preset.lfo[i];
    if (Advance(lfo.rate, lfo.sync != 0, bar_beats, dt, &lfo_phase_[i])) {
      lfo_steps_value_[i] = NextRandom();
    }
    v[MOD_LFO1 + i] = Shape(lfo.shape, lfo_phase_[i], lfo_steps_value_[i]);
  }

  // RANDOM: a new target every cycle; SMOOTH sets how much of the cycle
  // the cosine glide to it takes (0: a step).
  const RandomPreset& random = preset.random;
  if (Advance(random.rate, random.sync != 0, bar_beats, dt,
              &random_phase_)) {
    random_from_ = random_to_;
    random_to_ = NextRandom();
  }
  const float smooth = PresetValue(random.smooth);
  float glide = smooth > 0.0f ? random_phase_ / smooth : 1.0f;
  if (glide > 1.0f) {
    glide = 1.0f;
  }
  const float curve = 0.5f - 0.5f * cosf(kPi * glide);
  v[MOD_RANDOM] = random_from_ + (random_to_ - random_from_) * curve;

  // ENVELOPE: peak follower over both inputs.
  const EnvelopePreset& env = preset.envelope;
  const float attack_s = ExpMap(PresetValue(env.attack), 0.001f, 0.5f);
  const float release_s = ExpMap(PresetValue(env.release), 0.01f, 5.0f);
  const float attack = 1.0f - expf(-1.0f / (attack_s * kSampleRate));
  const float release = 1.0f - expf(-1.0f / (release_s * kSampleRate));
  float e = envelope_;
  if (in) {
    for (size_t n = 0; n < size; ++n) {
      const float l = fabsf(in[n].l);
      const float r = fabsf(in[n].r);
      const float peak = l > r ? l : r;
      e += (peak - e) * (peak > e ? attack : release);
    }
  }
  envelope_ = e;
  const float gain = expf(PresetValue(env.gain) * 24.0f * 0.11512925f);
  v[MOD_ENVELOPE] = Clamp(e * gain, 0.0f, 1.0f);

  v[MOD_CC_A] = cc_[0];
  v[MOD_CC_B] = cc_[1];
  v[MOD_NOTE] = note_value_;
  v[MOD_GATE] = num_notes_ ? 1.0f : 0.0f;
}

void ModSources::SetCc(int which, float value) {
  if (which == 0 || which == 1) {
    cc_[which] = Clamp(value, 0.0f, 1.0f);
  }
}

void ModSources::NoteOn(int note) {
  NoteOff(note);  // a repeated note moves to the end
  int n = num_notes_;
  if (n == 16) {
    for (int i = 1; i < 16; ++i) {
      notes_[i - 1] = notes_[i];
    }
    --n;
  }
  notes_[n] = int8_t(note);
  note_value_ = float(note - 60) * (1.0f / 48.0f);
  num_notes_ = uint8_t(n + 1);
}

void ModSources::NoteOff(int note) {
  int n = num_notes_;
  int j = 0;
  for (int i = 0; i < n; ++i) {
    if (notes_[i] != note) {
      notes_[j++] = notes_[i];
    }
  }
  for (int i = j; i < n; ++i) {
    notes_[i] = -1;
  }
  if (j) {
    // Last note wins: back to the newest still held.
    note_value_ = float(notes_[j - 1] - 60) * (1.0f / 48.0f);
  }
  num_notes_ = uint8_t(j);
}

void ModSources::AllNotesOff() {
  for (int i = 0; i < 16; ++i) {
    notes_[i] = -1;
  }
  num_notes_ = 0;
}

}  // namespace sidefx
