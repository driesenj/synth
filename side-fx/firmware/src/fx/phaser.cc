// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: PHASER (see phaser.h).

#include "fx/phaser.h"

#include "stmlib/dsp/units.h"

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  { "RATE", 0.35f, PARAM_SYNC, 0, 0 },
  // 0..4 octaves peak to peak: 0.1 octave per detent.
  { "DEPTH", 0.7f, 0, 0, 40 },
  // 100 Hz..4 kHz is 64 semitones: one per detent.
  { "CENTER", 0.5f, 0, 0, 64 },
  { "FEEDBACK", 0.7f, PARAM_BIPOLAR, 0, 100 },
  { "STAGES", 0.4f, PARAM_STEPPED, Phaser::kNumStageSettings, 0 },
  // 0..180 degrees: 5 degrees per detent.
  { "SPREAD", 0.5f, 0, 0, 36 },
  { "SHAPE", 0.0f, PARAM_STEPPED, Phaser::NUM_SHAPES, 0 },
};

const BlockInfo kInfo = {
  "PHASER", "PHASE", Phaser::NUM_PARAMS, kParams, 0.50f, 0,
};

const char* const kShapeLabels[] = { "SINE", "TRIANGLE", "RANDOM" };

const float kMinRateHz = 0.01f;
const float kMaxRateHz = 10.0f;
const float kMinCenterHz = 100.0f;
const float kMaxCenterHz = 4000.0f;
const float kMaxDepthOctaves = 2.0f;  // each way: 4 octaves peak to peak
const float kMaxFeedback = 0.92f;
// The corner frequency stays where the Pade tan below is accurate (0.4 %
// at 0.4 fs) and the allpass coefficients well inside (-1, 1).
const float kMinCornerHz = 20.0f;
const float kMaxCornerFraction = 0.4f;
// Synced LFOs lock to the bar count modulo this: every note value's cycle
// (4 BAR, the dotted and triplet ones) lines up with it.
const int kBarCycle = 12;
// Per block: how fast the synced LFO pulls onto the bar (about 13 ms) and
// how fast the knobs settle (about 3 ms).
const float kPhaseLock = 0.05f;
const float kSmoothing = 0.2f;
// The stage count crossfades over 10 ms, so changing it never clicks.
const float kCrossfadeStep = 1.0f / 480.0f;

// Linear up to +-2, then a soft knee to at most +-3: only feedback at full
// resonance with a loud input ever reaches the knee.
inline float SoftLimit(float x) {
  if (x > 2.0f) {
    return 2.0f + dsp::SoftSaturate(x - 2.0f);
  } else if (x < -2.0f) {
    return -2.0f + dsp::SoftSaturate(x + 2.0f);
  }
  return x;
}

inline float Wrap(float phase) {
  return phase - float(static_cast<int>(phase + 64.0f) - 64);
}

}  // namespace

const BlockInfo& Phaser::info() const {
  return kInfo;
}

bool Phaser::Init(Memory* memory) {
  // No buffers: the allpass states are a few hundred bytes in the object.
  (void)memory;
  Reset();
  return true;
}

void Phaser::Reset() {
  for (int c = 0; c < 2; ++c) {
    Channel& ch = channel_[c];
    for (int k = 0; k < kMaxStages; ++k) {
      ch.stage[k] = 0.0f;
    }
    ch.feedback = 0.0f;
    ch.dc.Reset();
    ch.coefficient = 0.0f;
    corner_hz_[c] = kMinCenterHz;
  }
  phase_ = 0.0f;
  bar_count_ = 0;
  last_bar_phase_ = 0.0f;
  random_.Seed(0x5eed1234u);
  for (int c = 0; c < 2; ++c) {
    random_from_[c] = 0.0f;
    random_to_[c] = random_.Bipolar();
  }
  center_ = 0.5f;
  depth_ = 0.0f;
  feedback_ = 0.0f;
  spread_ = 0.0f;
  stages_ = stages_from_ = 2;
  crossfade_ = 1.0f;
  primed_ = false;
}

float Phaser::LfoValue(float phase, int shape, int channel) const {
  switch (shape) {
    case SHAPE_TRIANGLE:
      return dsp::Triangle(phase);
    case SHAPE_RANDOM:
      {
        const float t = phase * phase * (3.0f - 2.0f * phase);
        return dsp::Lerp(random_from_[channel], random_to_[channel], t);
      }
    default:
      return dsp::Sine(phase);
  }
}

void Phaser::AdvancePhase(float increment) {
  phase_ += increment;
  // A new random segment every cycle. Going backwards (the synced LFO
  // pulling onto the bar) walks the segment back, so the walk stays
  // continuous either way.
  while (phase_ >= 1.0f) {
    phase_ -= 1.0f;
    for (int c = 0; c < 2; ++c) {
      random_from_[c] = random_to_[c];
      random_to_[c] = random_.Bipolar();
    }
  }
  while (phase_ < 0.0f) {
    phase_ += 1.0f;
    for (int c = 0; c < 2; ++c) {
      random_to_[c] = random_from_[c];
      random_from_[c] = random_.Bipolar();
    }
  }
}

float Phaser::Coefficient(float hz) const {
  // a = (t - 1) / (t + 1), t = tan(pi f / fs) by its [3/2] Pade
  // approximant w (15 - w^2) / (15 - 6 w^2): -90 degrees per stage at f.
  const float w = dsp::kPi * hz * (1.0f / kSampleRate);
  const float w2 = w * w;
  const float num = w * (15.0f - w2);
  const float den = 15.0f - 6.0f * w2;
  return (num - den) / (num + den);
}

void Phaser::Process(const ProcessContext& context, const float* params,
                     const Frame* in, Frame* out, size_t size) {
  const bool synced = context.synced(PARAM_RATE);
  const float rate_hz = RateParam(params[PARAM_RATE], synced,
                                  context.beat_seconds, kMinRateHz,
                                  kMaxRateHz);
  const int shape = StepIndex(params[PARAM_SHAPE], NUM_SHAPES);
  const int stages = 2 * (StepIndex(params[PARAM_STAGES],
                                    kNumStageSettings) + 1);
  const float center_target = dsp::Clamp(params[PARAM_CENTER], 0.0f, 1.0f);
  const float depth_target = kMaxDepthOctaves *
      dsp::Clamp(params[PARAM_DEPTH], 0.0f, 1.0f);
  const float feedback_target = Bipolar(
      dsp::Clamp(params[PARAM_FEEDBACK], 0.0f, 1.0f), kMaxFeedback);
  const float spread_target = 0.5f *
      dsp::Clamp(params[PARAM_SPREAD], 0.0f, 1.0f);

  if (!size) {
    return;
  }
  // Bars are counted even while free running, so turning sync on lands on
  // the right cycle of a 2 or 4 BAR rate.
  if (context.bar_phase < last_bar_phase_ - 0.5f) {
    bar_count_ = (bar_count_ + 1) % kBarCycle;
  }
  // The LFO: free running, or locked to the bar.
  float increment = rate_hz / kSampleRate;
  if (synced) {
    const float cycles_per_bar = rate_hz * 4.0f * context.beat_seconds;
    increment = cycles_per_bar * context.bar_increment;
    const float target = Wrap(cycles_per_bar *
                              (float(bar_count_) + context.bar_phase));
    float error = target - phase_;
    error -= float(static_cast<int>(error + 64.5f) - 64);  // -0.5..0.5
    AdvancePhase(primed_ ? error * kPhaseLock : error);
  }
  last_bar_phase_ = context.bar_phase;

  float feedback_start;
  if (!primed_) {
    center_ = center_target;
    depth_ = depth_target;
    feedback_ = feedback_target;
    spread_ = spread_target;
    stages_ = stages_from_ = stages;
    crossfade_ = 1.0f;
    feedback_start = feedback_;
  } else {
    feedback_start = feedback_;
    center_ += kSmoothing * (center_target - center_);
    depth_ += kSmoothing * (depth_target - depth_);
    feedback_ += kSmoothing * (feedback_target - feedback_);
    spread_ += kSmoothing * (spread_target - spread_);
  }
  if (stages != stages_ && crossfade_ >= 1.0f) {
    stages_from_ = stages_;
    stages_ = stages;
    crossfade_ = 0.0f;
  }

  const float center_hz = ExpMap(center_, kMinCenterHz, kMaxCenterHz);
  const float max_hz = kMaxCornerFraction * kSampleRate;
  const float feedback_step = (feedback_ - feedback_start) / float(size);
  float feedback = feedback_start;
  const int tap_from = stages_from_ - 1;
  const int tap_to = stages_ - 1;

  size_t done = 0;
  while (done < size) {
    const size_t n = size - done < kUpdatePeriod ? size - done : kUpdatePeriod;
    AdvancePhase(increment * float(n));

    float coefficient_step[2];
    for (int c = 0; c < 2; ++c) {
      float lfo;
      if (shape == SHAPE_RANDOM) {
        // The stereo random walk: the right channel moves away from the
        // left's towards its own as SPREAD goes up.
        lfo = LfoValue(phase_, shape, 0);
        if (c) {
          lfo = dsp::Lerp(lfo, LfoValue(phase_, shape, 1), 2.0f * spread_);
        }
      } else {
        lfo = LfoValue(c ? Wrap(phase_ + spread_) : phase_, shape, c);
      }
      float hz = center_hz * stmlib::SemitonesToRatio(
          12.0f * depth_ * lfo);
      hz = dsp::Clamp(hz, kMinCornerHz, max_hz);
      corner_hz_[c] = hz;
      if (!primed_) {
        channel_[c].coefficient = Coefficient(hz);
        coefficient_step[c] = 0.0f;
      } else {
        coefficient_step[c] = (Coefficient(hz) - channel_[c].coefficient) /
            float(n);
      }
    }
    primed_ = true;

    for (size_t i = 0; i < n; ++i) {
      feedback += feedback_step;
      if (crossfade_ < 1.0f) {
        crossfade_ += kCrossfadeStep;
        if (crossfade_ > 1.0f) {
          crossfade_ = 1.0f;
        }
      }
      const Frame& x_in = in[done + i];
      float result[2];
      for (int c = 0; c < 2; ++c) {
        Channel& ch = channel_[c];
        ch.coefficient += coefficient_step[c];
        const float a = ch.coefficient;
        // Feedback without DC, soft-saturated: resonance stays bounded.
        const float fb = 2.0f * dsp::SoftSaturate(
            0.5f * ch.dc.Process(ch.feedback, 0.999f));
        float x = (c ? x_in.r : x_in.l) + feedback * fb;
        float taps[kMaxStages];
        for (int k = 0; k < kMaxStages; ++k) {
          const float y = a * x + ch.stage[k];
          ch.stage[k] = x - a * y;
          x = y;
          taps[k] = y;
        }
        const float y = taps[tap_from] +
            (taps[tap_to] - taps[tap_from]) * crossfade_;
        ch.feedback = y;
        result[c] = SoftLimit(y);
      }
      out[done + i].l = result[0];
      out[done + i].r = result[1];
    }
    done += n;
  }
}

void Phaser::Format(int param, float value, const ProcessContext& context,
                    char* text, size_t size) const {
  switch (param) {
    case PARAM_RATE:
      if (context.synced(param)) {
        FormatNoteValue(text, size, SyncedRateIndex(value));
      } else {
        FormatHz(text, size, ExpMap(value, kMinRateHz, kMaxRateHz));
      }
      break;
    case PARAM_DEPTH:
      FormatNumber(text, size, 2.0f * kMaxDepthOctaves * value, 1, false,
                   "oct");
      break;
    case PARAM_CENTER:
      FormatHz(text, size, ExpMap(value, kMinCenterHz, kMaxCenterHz));
      break;
    case PARAM_FEEDBACK:
      FormatBipolarPercent(text, size, value);
      break;
    case PARAM_STAGES:
      FormatNumber(text, size,
                   float(2 * (StepIndex(value, kNumStageSettings) + 1)), 0,
                   false, "");
      break;
    case PARAM_SPREAD:
      FormatNumber(text, size, 180.0f * value, 0, false, "deg");
      break;
    case PARAM_SHAPE:
      FormatLabel(text, size, kShapeLabels, StepIndex(value, NUM_SHAPES));
      break;
    default:
      CopyText(text, size, "");
      break;
  }
}

}  // namespace sidefx
