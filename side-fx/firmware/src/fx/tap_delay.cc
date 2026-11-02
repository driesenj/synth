// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: TAP DELAY (see tap_delay.h).

#include "fx/tap_delay.h"

#include <math.h>

namespace sidefx {

using dsp::Clamp;

namespace {

const float kMinSpan = 0.05f;
const float kMaxSpan = 4.0f;
// A synced span goes on to what the line holds: 1 BAR stays on the grid
// down to 45 BPM.
const float kMaxSyncedSpan = 5.4f;

// 2^18 stereo frames: 5.46 s, 2 MB. The longest tap is kMaxSyncedSpan.
const size_t kLineSize = 262144;

// Equal-ish crossfade between old and new tap times, 21 ms. Tap time
// changes within an external clock's jitter (dsp::DelayMoved()) are
// ignored, so that the taps do not crossfade at every clock pulse.
const int32_t kCrossfadeLength = 1024;

// Control-rate smoothing of the knobs and the tap matrix: about 7 ms.
const float kSmoothing = 0.1f;

// Tap positions in sixteenths of the span (16 = the whole span: with a
// one-bar span, sixteenth notes), in order of importance: TAPS = n plays
// the first n. The first is always the span's end, the tap that feeds
// back, so the pattern repeats once per span.
const float kPatterns[TapDelay::kNumPatterns][TapDelay::kNumTaps] = {
  // EVEN: straight eighths.
  { 16.0f, 8.0f, 4.0f, 12.0f, 2.0f, 6.0f, 10.0f, 14.0f },
  // DOTTED: the dotted-eighth grid (3, 6, 9, 12, 15), then straight fills.
  { 16.0f, 6.0f, 12.0f, 3.0f, 9.0f, 15.0f, 8.0f, 4.0f },
  // SWING: eighths with the off-beats at 62 % (an MPC's 62 % swing).
  { 16.0f, 8.0f, 4.0f, 12.0f, 2.48f, 6.48f, 10.48f, 14.48f },
  // TRIPLET: quarter-note triplets across the span, then two beats.
  { 16.0f, 8.0f, 2.6667f, 5.3333f, 10.6667f, 13.3333f, 4.0f, 12.0f },
  // CLAVE: 3-2 son clave (3, 6, 10, 12, 16), then 14, 8, 15.
  { 16.0f, 6.0f, 3.0f, 10.0f, 12.0f, 14.0f, 8.0f, 15.0f },
  // ACCEL: a bouncing ball, gaps shrinking: 16 (1 - (1 - k/8)^2).
  { 16.0f, 3.75f, 7.0f, 9.75f, 12.0f, 13.75f, 15.0f, 15.75f },
  // DECEL: gaps growing: 16 (k/8)^2.
  { 16.0f, 0.25f, 1.0f, 2.25f, 4.0f, 6.25f, 9.0f, 12.25f },
  // SCATTER: off the grid on purpose, a fixed irregular set (the same
  // every time, so presets recall it).
  { 16.0f, 5.3f, 11.1f, 2.2f, 13.9f, 7.7f, 9.4f, 0.9f },
};

const char* const kPatternLabels[TapDelay::kNumPatterns] = {
  "EVEN", "DOTTED", "SWING", "TRIPLET", "CLAVE", "ACCEL", "DECEL", "SCATTER",
};

const ParamInfo kParams[] = {
  // 1 s free; when synced the same value is 1/4 (one bar is 0.89).
  { "TIME", 0.6837f, PARAM_SYNC, 0, 0 },
  { "PATTERN", 1.0f / 7.0f, PARAM_STEPPED, TapDelay::kNumPatterns, 0 },
  { "TAPS", 3.0f / 7.0f, PARAM_STEPPED, TapDelay::kNumTaps, 0 },
  { "DECAY", 0.4f, 0, 0, 100 },
  { "FEEDBACK", 0.3f, 0, 0, 100 },
  { "SPREAD", 0.7f, 0, 0, 100 },
  { "TONE", 0.35f, PARAM_BIPOLAR, 0, 100 },
};

const BlockInfo kInfo = {
  "TAP DELAY", "TAPS", TapDelay::NUM_PARAMS, kParams, 0.35f, 0,
};

// Linear up to 2, then soft to a ceiling of 3: the sum of eight taps of a
// hot signal stays bounded without colouring normal levels.
inline float SoftLimit(float x) {
  if (x > 2.0f) {
    return 2.0f + dsp::SoftSaturate(x - 2.0f);
  } else if (x < -2.0f) {
    return -2.0f - dsp::SoftSaturate(-x - 2.0f);
  }
  return x;
}

// The feedback path saturates at +-1.5: self-oscillation stays bounded.
inline float FeedbackSaturate(float x) {
  return 1.5f * dsp::SoftSaturate(x * (1.0f / 1.5f));
}

}  // namespace

const BlockInfo& TapDelay::info() const {
  return kInfo;
}

float TapDelay::TapDelaySamples(int pattern, int tap, float span_seconds) {
  return kPatterns[pattern][tap] * (1.0f / 16.0f) * span_seconds *
      kSampleRate;
}

bool TapDelay::Init(Memory* memory) {
  Frame* buffer = memory->external->AllocateArray<Frame>(kLineSize);
  if (!buffer) {
    return false;
  }
  line_.Init(buffer, kLineSize);
  Reset();
  return true;
}

void TapDelay::Reset() {
  line_.Clear();
  for (int i = 0; i < kNumTaps; ++i) {
    delay_[i] = next_delay_[i] = 1;
    for (int k = 0; k < 4; ++k) {
      target_[i][k] = smoothed_[i][k] = matrix_[i][k] = 0.0f;
    }
    lp_coefficient_[i] = lp_target_[i] = 1.0f;
    hp_coefficient_[i] = hp_target_[i] = 0.0f;
    lp_[i][0] = lp_[i][1] = 0.0f;
    hp_[i][0] = hp_[i][1] = 0.0f;
  }
  crossfading_ = false;
  crossfade_position_ = 0;
  snap_ = true;
  decay_ = spread_ = tone_ = feedback_ = feedback_gain_ = 0.0f;
  mix_pattern_ = mix_taps_ = -1;
  mix_decay_ = mix_tone_ = mix_spread_ = -2.0f;
}

void TapDelay::UpdateTargets(int pattern, int num_taps, float span_seconds) {
  // The gains and filters cost 16 expf: only when something moved.
  if (snap_ || pattern != mix_pattern_ || num_taps != mix_taps_ ||
      decay_ != mix_decay_ || tone_ != mix_tone_ || spread_ != mix_spread_) {
    mix_pattern_ = pattern;
    mix_taps_ = num_taps;
    mix_decay_ = decay_;
    mix_tone_ = tone_;
    mix_spread_ = spread_;
    UpdateMix(pattern, num_taps);
  }
  UpdateTimes(pattern, span_seconds);
}

void TapDelay::UpdateMix(int pattern, int num_taps) {
  const float* position = kPatterns[pattern];

  // Positions relative to the earliest tap playing: 0 for it, 1 for the
  // span's end. Decay and tone grow along this.
  float earliest = 16.0f;
  for (int i = 0; i < num_taps; ++i) {
    earliest = position[i] < earliest ? position[i] : earliest;
  }
  const float range = 16.0f - earliest;
  const float inverse_range = range > 0.01f ? 1.0f / range : 0.0f;

  float gain[kNumTaps];
  float sum_of_squares = 0.0f;
  for (int i = 0; i < kNumTaps; ++i) {
    const float relative = num_taps > 1
        ? (position[i] - earliest) * inverse_range : 0.0f;
    // DECAY at 1: the last tap 24 dB under the first (10^(-1.2)).
    gain[i] = i < num_taps ? expf(-2.7631f * decay_ * relative) : 0.0f;
    sum_of_squares += gain[i] * gain[i];

    // TONE: the latest tap gets all of it, the earliest a quarter.
    const float amount = (num_taps > 1 ? 0.25f + 0.75f * relative : 1.0f) *
        tone_;
    if (amount < 0.0f) {
      // Lowpass from open (coefficient 1) to about 510 Hz.
      lp_target_[i] = expf(2.7334f * amount);
      hp_target_[i] = dsp::OnePoleCoefficient(20.0f, kSampleRate);
    } else {
      lp_target_[i] = 1.0f;
      // Highpass from 20 Hz (a DC blocker for the feedback) to 3 kHz.
      hp_target_[i] = dsp::OnePoleCoefficient(
          20.0f * expf(5.0106f * amount), kSampleRate);
    }
  }
  // Between no normalisation and equal power: eight equal taps come out
  // 4.5 dB under one, not 9.
  const float normalisation = 1.0f / sqrtf(sqrtf(
      sum_of_squares > 1.0f ? sum_of_squares : 1.0f));

  for (int i = 0; i < kNumTaps; ++i) {
    // Rank in time among the taps playing: they alternate left, right.
    int rank = 0;
    for (int j = 0; j < num_taps; ++j) {
      rank += position[j] < position[i] ? 1 : 0;
    }
    const float pan = num_taps > 1
        ? ((rank & 1) ? spread_ : -spread_) : 0.0f;
    float left, right;
    dsp::PanGains(pan, &left, &right);
    // SPREAD also blends the tap from its stereo self to its mono sum
    // panned, so that a mono input spreads too.
    const float s = spread_;
    const float g = gain[i] * normalisation;
    const float ml = 0.70710678f * s * left;   // 0.5 * sqrt(2) * left
    const float mr = 0.70710678f * s * right;
    target_[i][0] = g * (1.0f - s + ml);  // left from left
    target_[i][1] = g * ml;               // left from right
    target_[i][2] = g * mr;               // right from left
    target_[i][3] = g * (1.0f - s + mr);  // right from right
  }
}

void TapDelay::UpdateTimes(int pattern, float span_seconds) {
  bool moved = false;
  int32_t target[kNumTaps];
  for (int i = 0; i < kNumTaps; ++i) {
    float d = TapDelaySamples(pattern, i, span_seconds) + 0.5f;
    d = Clamp(d, 1.0f, float(kLineSize - 4));
    target[i] = int32_t(d);
    moved = moved || dsp::DelayMoved(float(delay_[i]), float(target[i]));
  }
  if (snap_) {
    for (int i = 0; i < kNumTaps; ++i) {
      delay_[i] = next_delay_[i] = target[i];
    }
  } else if (!crossfading_ && moved) {
    for (int i = 0; i < kNumTaps; ++i) {
      next_delay_[i] = target[i];
    }
    crossfading_ = true;
    crossfade_position_ = 0;
  }
}

void TapDelay::Process(const ProcessContext& context, const float* params,
                       const Frame* in, Frame* out, size_t size) {
  const bool synced = context.synced(PARAM_TIME);
  const float span = TimeParam(params[PARAM_TIME], synced,
                               context.beat_seconds, kMinSpan,
                               synced ? kMaxSyncedSpan : kMaxSpan);
  const int pattern = StepIndex(params[PARAM_PATTERN], kNumPatterns);
  const int num_taps = StepIndex(params[PARAM_TAPS], kNumTaps) + 1;

  const float k = snap_ ? 1.0f : kSmoothing;
  decay_ += k * (Clamp(params[PARAM_DECAY], 0.0f, 1.0f) - decay_);
  spread_ += k * (Clamp(params[PARAM_SPREAD], 0.0f, 1.0f) - spread_);
  tone_ += k * (Bipolar(Clamp(params[PARAM_TONE], 0.0f, 1.0f), 1.0f) - tone_);
  // A little over unity: the repeats can build up into the saturation.
  feedback_ += k * (1.05f * Clamp(params[PARAM_FEEDBACK], 0.0f, 1.0f) -
                    feedback_);

  UpdateTargets(pattern, num_taps, span);

  // The matrix moves towards its target per block (one-pole) and
  // linearly within the block.
  float step[kNumTaps][4];
  float lp_step[kNumTaps];
  float hp_step[kNumTaps];
  bool active[kNumTaps];
  const float inverse_size = size ? 1.0f / float(size) : 0.0f;
  for (int i = 0; i < kNumTaps; ++i) {
    float magnitude = 0.0f;
    for (int j = 0; j < 4; ++j) {
      smoothed_[i][j] += k * (target_[i][j] - smoothed_[i][j]);
      if (snap_) {
        matrix_[i][j] = smoothed_[i][j];
      }
      step[i][j] = (smoothed_[i][j] - matrix_[i][j]) * inverse_size;
      magnitude += fabsf(smoothed_[i][j]) + fabsf(matrix_[i][j]);
    }
    if (snap_) {
      lp_coefficient_[i] = lp_target_[i];
      hp_coefficient_[i] = hp_target_[i];
    }
    lp_step[i] = (lp_target_[i] - lp_coefficient_[i]) * inverse_size;
    hp_step[i] = (hp_target_[i] - hp_coefficient_[i]) * inverse_size;
    // Tap 0 always runs: it feeds back.
    active[i] = i == 0 || magnitude > 1.0e-6f;
    if (!active[i]) {
      lp_[i][0] = lp_[i][1] = 0.0f;
      hp_[i][0] = hp_[i][1] = 0.0f;
    }
  }
  if (snap_) {
    feedback_gain_ = feedback_;
  }
  const float feedback_step = (feedback_ - feedback_gain_) * inverse_size;
  float feedback_gain = feedback_gain_;
  snap_ = false;

  for (size_t n = 0; n < size; ++n) {
    float fade_in = 1.0f;
    float fade_out = 0.0f;
    if (crossfading_) {
      // (1 - t)(1 + 0.4 t) and t (1 + 0.4 (1 - t)): +1.6 dB in the middle
      // for correlated taps (small time changes), -1.4 dB for unrelated
      // ones (big jumps). Neither law alone suits both.
      const float t = float(crossfade_position_) *
          (1.0f / float(kCrossfadeLength));
      fade_in = t * (1.4f - 0.4f * t);
      fade_out = (1.0f - t) * (1.0f + 0.4f * t);
    }

    Frame sum = MakeFrame(0.0f, 0.0f);
    Frame feedback = MakeFrame(0.0f, 0.0f);
    for (int i = 0; i < kNumTaps; ++i) {
      if (!active[i]) {
        continue;
      }
      // Read(d - 1) before the write: the sample from d samples ago.
      Frame tap;
      if (crossfading_) {
        tap = line_.Read(size_t(next_delay_[i] - 1)) * fade_in +
            line_.Read(size_t(delay_[i] - 1)) * fade_out;
      } else {
        tap = line_.Read(size_t(delay_[i] - 1));
      }
      // Tone: lowpass, then highpass.
      const float lc = lp_coefficient_[i] += lp_step[i];
      const float hc = hp_coefficient_[i] += hp_step[i];
      lp_[i][0] += lc * (tap.l - lp_[i][0]);
      lp_[i][1] += lc * (tap.r - lp_[i][1]);
      hp_[i][0] += hc * (lp_[i][0] - hp_[i][0]);
      hp_[i][1] += hc * (lp_[i][1] - hp_[i][1]);
      const float l = lp_[i][0] - hp_[i][0];
      const float r = lp_[i][1] - hp_[i][1];
      if (i == 0) {
        feedback.l = l;
        feedback.r = r;
      }
      float* m = matrix_[i];
      m[0] += step[i][0];
      m[1] += step[i][1];
      m[2] += step[i][2];
      m[3] += step[i][3];
      sum.l += m[0] * l + m[1] * r;
      sum.r += m[2] * l + m[3] * r;
    }

    feedback_gain += feedback_step;
    Frame write = in[n];
    write.l += FeedbackSaturate(feedback.l * feedback_gain);
    write.r += FeedbackSaturate(feedback.r * feedback_gain);
    line_.Write(write);

    out[n].l = SoftLimit(sum.l);
    out[n].r = SoftLimit(sum.r);

    if (crossfading_ && ++crossfade_position_ >= kCrossfadeLength) {
      crossfading_ = false;
      for (int i = 0; i < kNumTaps; ++i) {
        delay_[i] = next_delay_[i];
      }
    }
  }
  // Exact end values: no drift from the summed steps.
  for (int i = 0; i < kNumTaps; ++i) {
    for (int j = 0; j < 4; ++j) {
      matrix_[i][j] = smoothed_[i][j];
    }
    lp_coefficient_[i] = lp_target_[i];
    hp_coefficient_[i] = hp_target_[i];
  }
  feedback_gain_ = feedback_;
}

void TapDelay::Format(int param, float value, const ProcessContext& context,
                      char* text, size_t size) const {
  switch (param) {
    case PARAM_TIME:
      if (!context.synced(param)) {
        FormatSeconds(text, size, TimeParam(value, false, context.beat_seconds,
                                            kMinSpan, kMaxSpan));
      } else if (SyncedSeconds(value, context.beat_seconds) >
                 kMaxSyncedSpan) {
        // A note value longer than the line holds: the span it plays, so
        // the screen does not claim the grid.
        FormatSeconds(text, size, kMaxSyncedSpan);
      } else {
        FormatNoteValue(text, size, NoteValueIndex(value));
      }
      break;
    case PARAM_PATTERN:
      FormatLabel(text, size, kPatternLabels, StepIndex(value, kNumPatterns));
      break;
    case PARAM_TAPS:
      FormatNumber(text, size, float(StepIndex(value, kNumTaps) + 1), 0,
                   false, StepIndex(value, kNumTaps) ? " TAPS" : " TAP");
      break;
    case PARAM_FEEDBACK:
      FormatPercent(text, size, 1.05f * value);
      break;
    case PARAM_TONE:
      FormatBipolarPercent(text, size, value);
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
