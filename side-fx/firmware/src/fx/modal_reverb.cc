// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: MODAL, a resonant body (see modal_reverb.h).

#include "fx/modal_reverb.h"

#include <math.h>
#include <string.h>

namespace sidefx {

namespace {

enum Param {
  PITCH,
  STRUCT,
  DECAY,
  BRIGHT,
  DENSITY,
  WIDTH,
  DRIFT,
  NUM_PARAMS
};

const ParamInfo kParams[] = {
  // 0.5 = C2 (65.41 Hz), +-24 semitones, one per detent.
  { "PITCH", 0.5f, PARAM_BIPOLAR, 0, 48 },
  { "STRUCT", 0.25f, 0, 0, 120 },
  // 0.64 = 3 s. A time: synced, the fundamental rings for a note value.
  { "DECAY", 0.64f, PARAM_SYNC, 0, 100 },
  { "BRIGHT", 0.4f, 0, 0, 100 },
  // 8..32 modes, one per detent.
  { "DENSITY", 0.5f, 0, 0, 24 },
  { "WIDTH", 0.8f, 0, 0, 100 },
  { "DRIFT", 0.2f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "MODAL", "MODAL", NUM_PARAMS, kParams, 0.35f, 0,
};

const float kBaseHz = 65.40639f;    // C2
const float kMinDecay = 0.1f;
const float kMaxDecay = 20.0f;
const float kMinModeDecay = 0.03f;  // high modes at BRIGHT 0 and DECAY min
const float kMinModes = 8.0f;
const float kLn2 = 0.69314718f;
// Input gain constant: noise at +-1 (0.58 RMS) gives about 0.34 RMS out at
// the defaults (measured in the tests).
const float kExcite = 0.3f;
// The largest amplitude a mode's state may reach (its output is this times
// its pan gain and the density normalisation).
const float kModeLimit = 3.0f;
const float kOutputGain = 1.0f;
// The input's DC blocker: about 8 Hz, so a C0 body still gets its sub.
const float kInputDcPole = 0.999f;
// Modes fade out between these, well under Nyquist.
const float kFadeStartHz = 15000.0f;
const float kFadeEndHz = 19000.0f;

// Bell partials (Hemony bell), relative to the hum: hum, prime, tierce,
// quint, nominal, deciem, undeciem, duodeciem, upper octave and above.
const float kBellRatios[] = {
  1.0f, 2.0f, 2.366f, 3.012f, 4.0f, 5.028f, 5.324f, 6.022f, 8.332f,
  10.866f, 13.592f, 16.43f,
};
const int kNumBellRatios = sizeof(kBellRatios) / sizeof(kBellRatios[0]);

// Stiff string inharmonicity: f_n = n f0 sqrt((1 + B n^2) / (1 + B)).
const float kStringStiffness = 0.0012f;
// Plate side ratio (an irrational-ish aspect, so modes do not coincide).
const float kPlateAspect = 1.37f;

// Pan pattern: alternating sides, uneven distances, the fundamental in the
// middle so the low end stays mono.
inline float PanPattern(int n) {
  if (n == 0) {
    return 0.0f;
  }
  const float golden = float(n) * 0.618034f;
  const float spread = 0.35f + 0.65f * (golden - floorf(golden));
  return (n & 1) ? -spread : spread;
}

// Transparent below 2, then bends smoothly towards 3.
inline float Limit(float x) {
  if (x > 2.0f) {
    return 2.0f + dsp::SoftSaturate(x - 2.0f);
  } else if (x < -2.0f) {
    return -2.0f + dsp::SoftSaturate(x + 2.0f);
  }
  return x;
}

inline float DecaySeconds(float value, const ProcessContext& context) {
  return dsp::Clamp(TimeParam(value, context.synced(DECAY),
                              context.beat_seconds, kMinDecay, kMaxDecay),
                    kMinDecay, kMaxDecay);
}

inline float NumModes(float value) {
  return kMinModes + dsp::Clamp(value, 0.0f, 1.0f) *
      (float(ModalReverb::kMaxModes) - kMinModes);
}

const char* const kStructLabels[] = {
  "HARMONIC", "HARM-STR", "STRING", "STR-BELL", "BELL", "BELL-PLT", "PLATE",
};

}  // namespace

const BlockInfo& ModalReverb::info() const {
  return kInfo;
}

bool ModalReverb::Init(Memory* memory) {
  modes_ = memory->internal->AllocateArray<Mode>(kMaxModes);
  ratios_ = memory->internal->AllocateArray<float>(kNumBodies * kMaxModes);
  mix_l_ = memory->internal->AllocateArray<float>(kBlockSize);
  mix_r_ = memory->internal->AllocateArray<float>(kBlockSize);
  excitation_ = memory->internal->AllocateArray<float>(kBlockSize);
  if (!modes_ || !ratios_ || !mix_l_ || !mix_r_ || !excitation_) {
    return false;
  }

  float* harmonic = ratios_;
  float* string = ratios_ + kMaxModes;
  float* bell = ratios_ + 2 * kMaxModes;
  float* plate = ratios_ + 3 * kMaxModes;
  for (int n = 0; n < kMaxModes; ++n) {
    const float k = float(n + 1);
    harmonic[n] = log2f(k);
    string[n] = log2f(k * sqrtf((1.0f + kStringStiffness * k * k) /
                                (1.0f + kStringStiffness)));
  }
  // The bell's measured partials, then a slightly irregular widening
  // series: bell partials crowd less than a string's.
  float ratio = kBellRatios[kNumBellRatios - 1];
  for (int n = 0; n < kMaxModes; ++n) {
    if (n < kNumBellRatios) {
      bell[n] = log2f(kBellRatios[n]);
    } else {
      ratio *= (n & 1) ? 1.083f : 1.117f;
      bell[n] = log2f(ratio);
    }
  }
  // A simply supported plate: f ~ (i / Lx)^2 + (j / Ly)^2. The lowest 32
  // of i, j in 1..10, sorted (selection: Init runs once).
  const int kSide = 10;
  float candidates[kSide * kSide];
  for (int i = 0; i < kSide; ++i) {
    for (int j = 0; j < kSide; ++j) {
      const float a = float(i + 1);
      const float b = float(j + 1) / kPlateAspect;
      candidates[i * kSide + j] = a * a + b * b;
    }
  }
  float lowest = 0.0f;
  for (int n = 0; n < kMaxModes; ++n) {
    int best = 0;
    for (int c = 1; c < kSide * kSide; ++c) {
      if (candidates[c] < candidates[best]) {
        best = c;
      }
    }
    if (n == 0) {
      lowest = candidates[best];
    }
    plate[n] = log2f(candidates[best] / lowest);
    candidates[best] = 1.0e30f;
  }
  Reset();
  return true;
}

void ModalReverb::Reset() {
  memset(modes_, 0, sizeof(Mode) * kMaxModes);
  memset(mix_l_, 0, sizeof(float) * kBlockSize);
  memset(mix_r_, 0, sizeof(float) * kBlockSize);
  memset(excitation_, 0, sizeof(float) * kBlockSize);
  random_.Seed(0x6d6f6461u);  // the same drift after every reset
  for (int n = 0; n < kMaxModes; ++n) {
    modes_[n].drift_target = random_.Bipolar();
    modes_[n].drift = modes_[n].drift_1 = modes_[n].drift_target;
    modes_[n].limiter = 1.0f;
  }
  dc_blocker_.Reset();
  group_ = -1;  // the first Process computes every mode at once
}

void ModalReverb::UpdateMode(int n, const ProcessContext& context,
                             const float* params) {
  Mode& m = modes_[n];
  const float update_seconds = float(kUpdateGroups * kBlockSize) /
      context.sample_rate;

  // DRIFT: a smoothed random walk of each mode's tuning, 0..25 cents,
  // faster as it gets deeper.
  const float drift_amount = dsp::Clamp(params[DRIFT], 0.0f, 1.0f);
  const float drift_hz = 0.06f + 0.5f * drift_amount;
  if (random_.Uniform() < 2.0f * drift_hz * update_seconds) {
    m.drift_target = random_.Bipolar();
  }
  const float drift_coefficient = dsp::Clamp(
      dsp::kTwoPi * drift_hz * update_seconds, 0.0f, 1.0f);
  m.drift_1 += (m.drift_target - m.drift_1) * drift_coefficient;
  m.drift += (m.drift_1 - m.drift) * drift_coefficient;
  const float drift_octaves = m.drift * drift_amount * (25.0f / 1200.0f);

  // STRUCT: the partial ratio, morphed between neighbouring bodies.
  const float body = dsp::Clamp(params[STRUCT], 0.0f, 1.0f) *
      float(kNumBodies - 1);
  int b = int(body);
  if (b > kNumBodies - 2) {
    b = kNumBodies - 2;
  }
  const float fraction = body - float(b);
  const float log2_ratio = dsp::Lerp(ratios_[b * kMaxModes + n],
                                     ratios_[(b + 1) * kMaxModes + n],
                                     fraction);

  // PITCH: 1 V/oct-style, linear in semitones.
  const float semitones = Bipolar(dsp::Clamp(params[PITCH], 0.0f, 1.0f),
                                  24.0f);
  const float hz = kBaseHz * expf(kLn2 * (semitones * (1.0f / 12.0f) +
                                          log2_ratio + drift_octaves));

  // DENSITY: whole modes up to the count, the next one partly, so the
  // knob (or a CV) fades modes in and out smoothly.
  const float num_modes = NumModes(params[DENSITY]);
  float weight = dsp::Clamp(num_modes - float(n), 0.0f, 1.0f);
  weight *= dsp::Clamp((kFadeEndHz - hz) * (1.0f / (kFadeEndHz -
                                                    kFadeStartHz)),
                       0.0f, 1.0f);

  if (weight <= 0.0f) {
    m.pan_l_target = m.pan_r_target = 0.0f;
    // Keep the rotation as it is: the mode fades out over this block and
    // is then switched off (Process clears its state).
    m.c_target = m.c;
    m.s_target = m.s;
    m.gain = 0.0f;
    return;
  }

  // DECAY and BRIGHT: the fundamental's RT60; dark makes high modes die
  // up to proportionally faster (T ~ 1 / ratio) and quieter (-4.5 dB per
  // octave), bright keeps them all ringing and lifts them slightly.
  const float bright = dsp::Clamp(params[BRIGHT], 0.0f, 1.0f);
  const float decay_slope = 1.0f - bright;
  const float level_slope = 0.75f - 0.85f * bright;
  float t60 = DecaySeconds(params[DECAY], context) *
      expf(-kLn2 * decay_slope * log2_ratio);
  if (t60 < kMinModeDecay) {
    t60 = kMinModeDecay;
  }
  const float r = expf(-6.9077553f / (t60 * context.sample_rate));
  float w = dsp::kTwoPi * hz / context.sample_rate;
  if (w > 2.8f) {
    w = 2.8f;
  }
  m.c_target = r * cosf(w);
  m.s_target = r * sinf(w);

  // Input gain ~ (1 - r^2)^(1/4): between a constant gain (a long decay
  // gets louder under sustained input, like a room) and a power-normalised
  // one (every decay equally loud, but long ones then barely react to a
  // hit). Sustained input grows as T^(1/4), a hit's level falls as
  // T^(-1/4): over 0.1..20 s both stay within +-7 dB.
  m.gain = kExcite * sqrtf(sqrtf(1.0f - r * r)) *
      expf(-kLn2 * level_slope * log2_ratio);

  // WIDTH and the density normalisation (modes add up as noise).
  float pan_l, pan_r;
  dsp::PanGains(dsp::Clamp(params[WIDTH], 0.0f, 1.0f) * PanPattern(n),
                &pan_l, &pan_r);
  const float normalisation = weight * kOutputGain / sqrtf(num_modes);
  m.pan_l_target = pan_l * normalisation;
  m.pan_r_target = pan_r * normalisation;
  m.active = true;
}

void ModalReverb::Process(const ProcessContext& context, const float* params,
                          const Frame* in, Frame* out, size_t size) {
  if (size > kBlockSize) {
    // The engine always calls with kBlockSize; anything longer is split.
    while (size) {
      const size_t chunk = size > kBlockSize ? kBlockSize : size;
      Process(context, params, in, out, chunk);
      in += chunk;
      out += chunk;
      size -= chunk;
    }
    return;
  }

  if (group_ < 0) {
    for (int n = 0; n < kMaxModes; ++n) {
      UpdateMode(n, context, params);
      // Start at the target: nothing rings yet, so no ramp is needed.
      modes_[n].c = modes_[n].c_target;
      modes_[n].s = modes_[n].s_target;
    }
    group_ = 0;
  } else {
    // Strided groups, so every part of the spectrum follows a pitch change
    // equally soon.
    for (int n = group_; n < kMaxModes; n += kUpdateGroups) {
      UpdateMode(n, context, params);
    }
    group_ = (group_ + 1) % kUpdateGroups;
  }

  for (size_t i = 0; i < size; ++i) {
    excitation_[i] = dc_blocker_.Process(0.5f * (in[i].l + in[i].r),
                                         kInputDcPole);
    mix_l_[i] = 0.0f;
    mix_r_[i] = 0.0f;
  }

  const float inverse_size = 1.0f / float(size);
  const float limit_squared = kModeLimit * kModeLimit;
  for (int n = 0; n < kMaxModes; ++n) {
    Mode& m = modes_[n];
    if (!m.active) {
      continue;
    }
    float x = m.x;
    float y = m.y;
    // The limiter's extra decay scales the whole rotation (and its ramp).
    const float limiter = m.limiter;
    float c = m.c * limiter;
    float s = m.s * limiter;
    float pan_l = m.pan_l;
    float pan_r = m.pan_r;
    const float dc = (m.c_target - m.c) * limiter * inverse_size;
    const float ds = (m.s_target - m.s) * limiter * inverse_size;
    const float dl = (m.pan_l_target - pan_l) * inverse_size;
    const float dr = (m.pan_r_target - pan_r) * inverse_size;
    const float gain = m.gain;
    for (size_t i = 0; i < size; ++i) {
      c += dc;
      s += ds;
      pan_l += dl;
      pan_r += dr;
      const float x_next = c * x - s * y + gain * excitation_[i];
      y = s * x + c * y;
      x = x_next;
      mix_l_[i] += pan_l * y;
      mix_r_[i] += pan_r * y;
    }
    m.c = m.c_target;
    m.s = m.s_target;
    m.pan_l = m.pan_l_target;
    m.pan_r = m.pan_r_target;

    // A mode pushed past its limit decays faster during the next block,
    // by about limit / amplitude over the block: an amplitude ceiling with
    // no step in the waveform.
    const float energy = x * x + y * y;
    if (energy > limit_squared) {
      const float excess = 1.0f - kModeLimit / sqrtf(energy);
      m.limiter = 1.0f - (excess > 0.5f ? 0.5f : excess) * inverse_size;
    } else {
      m.limiter = 1.0f;
    }
    if (m.pan_l == 0.0f && m.pan_r == 0.0f) {
      // Faded out: switch off and forget the ringing, so it cannot come
      // back stale when the mode is faded in again.
      m.active = false;
      x = y = 0.0f;
    }
    m.x = x;
    m.y = y;
  }

  for (size_t i = 0; i < size; ++i) {
    out[i].l = Limit(mix_l_[i]);
    out[i].r = Limit(mix_r_[i]);
  }
}

void ModalReverb::Format(int param, float value, const ProcessContext& context,
                         char* text, size_t size) const {
  switch (param) {
    case PITCH:
      FormatSemitones(text, size, Bipolar(value, 24.0f), false);
      break;
    case STRUCT:
      {
        // Seven zones: each body, and the blends between neighbours.
        const float body = dsp::Clamp(value, 0.0f, 1.0f) *
            float(kNumBodies - 1);
        const int nearest = int(body + 0.5f);
        const int label = fabsf(body - float(nearest)) < 0.15f
            ? 2 * nearest : 2 * int(body) + 1;
        FormatLabel(text, size, kStructLabels, label > 6 ? 6 : label);
      }
      break;
    case DECAY:
      // A note value outside 0.1 .. 20 s rings for the clamped time: show
      // that instead.
      if (context.synced(DECAY) &&
          SyncedSeconds(value, context.beat_seconds) ==
          DecaySeconds(value, context)) {
        FormatNoteValue(text, size, NoteValueIndex(value));
      } else {
        FormatSeconds(text, size, DecaySeconds(value, context));
      }
      break;
    case DENSITY:
      FormatNumber(text, size, floorf(NumModes(value) + 0.5f), 0, false,
                   " MODES");
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
