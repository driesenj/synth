// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: APF CHAIN, Schroeder allpasses in series with feedback (see
// apf_chain.h).

#include "fx/apf_chain.h"

#include <math.h>
#include <string.h>

namespace sidefx {

namespace {

enum Param {
  LENGTH,
  STAGES,
  DIFFUSE,
  FEEDBACK,
  DAMP,
  MOD,
  WIDTH,
  NUM_PARAMS
};

const int kNumStageSteps = 8;  // 2, 4, .. 16 stages

const ParamInfo kParams[] = {
  { "LENGTH", 0.5f, PARAM_SYNC, 0, 100 },
  // 3 / 7: 8 stages.
  { "STAGES", 0.42857143f, PARAM_STEPPED, kNumStageSteps, 0 },
  { "DIFFUSE", 0.6f, 0, 0, 100 },
  { "FEEDBACK", 0.5f, 0, 0, 100 },
  { "DAMP", 0.4f, 0, 0, 100 },
  { "MOD", 0.3f, 0, 0, 100 },
  { "WIDTH", 0.8f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "APF CHAIN", "APF", NUM_PARAMS, kParams, 0.35f, 0,
};

const float kMinLength = 0.001f;
const float kMaxLength = 0.1f;
const float kMaxDiffusion = 0.92f;
const float kMaxFeedback = 0.98f;
const float kMaxDampHz = 20000.0f;
const float kMinDampHz = 400.0f;
// Modulation: at most 2 ms, and never more than a fifth of the stage.
const float kMaxModSeconds = 0.002f;
const float kMaxModFraction = 0.2f;
// The shortest delay a stage may read (it writes as it reads, sample by
// sample, so 1 would do; 2 leaves room for the interpolation).
const float kMinDelay = 2.0f;
const float kMaxDelay = float(ApfChain::kStageBufferSize) - 4.0f;
// One-pole glide of LENGTH (80 ms), then a slew limit: d(scale)/dn <=
// ln 2 / sum(ratios) keeps the product of all stages' Doppler factors
// within an octave.
const float kGlideSeconds = 0.08f;
// Close enough to the whole-sample target to jump there unheard.
const float kSnapSamples = 0.02f;
// DIFFUSE, WIDTH and MOD smoothing.
const float kSmoothSeconds = 0.015f;
const float kMaxSlew = 0.69314718f / 16.0f;
// The DC blocker in the loop: about 15 Hz, under the sub bass.
const float kDcBlockerPole = 0.998f;
// A STAGES change crossfades the taps over this many samples.
const float kTapFadeSamples = 256.0f;

// Stage delay ratios, prime-ish and interleaved short/long so the first N
// stages of a chain average about 1 for every N. The right chain's are
// different numbers so the two decorrelate.
const float kRatios[ApfChain::kNumChains][ApfChain::kNumStages] = {
  { 1.01f, 0.73f, 1.31f, 0.89f, 1.13f, 0.61f, 1.39f, 0.97f,
    1.09f, 0.79f, 1.27f, 0.67f, 1.51f, 0.83f, 1.03f, 0.71f },
  { 1.07f, 0.79f, 1.37f, 0.94f, 1.18f, 0.57f, 1.46f, 1.03f,
    1.13f, 0.86f, 1.22f, 0.64f, 1.57f, 0.91f, 0.99f, 0.76f },
};

// MOD sways every fourth stage (1, 5, 9, 13: at least one at 2 stages);
// the others keep whole-sample delays and stay exact allpasses.
inline bool IsModulated(int stage) {
  return (stage & 3) == 1;
}

// LFO rates (Hz) of the stages: slow, all different.
inline float LfoHz(int chain, int stage) {
  return 0.11f + 0.053f * float(stage) + 0.031f * float(chain);
}

inline float StageRatioSum(int chain, int stages) {
  float sum = 0.0f;
  for (int k = 0; k < stages; ++k) {
    sum += kRatios[chain][k];
  }
  return sum;
}

// The longest whole-loop period, in samples, the first `stages` stages of
// both chains can make at sample rate fs: each chain's longest tapped stage
// fills its buffer (less the modulation), and the shorter chain sets it for
// both, so the two loops keep one period. Includes the block of feedback
// latency.
inline float MaxLoopSamples(int stages, float fs) {
  const float room = kMaxDelay - kMaxModSeconds * fs;
  float period = 0.0f;
  for (int c = 0; c < ApfChain::kNumChains; ++c) {
    float largest = 0.0f;
    for (int k = 0; k < stages; ++k) {
      largest = fmaxf(largest, kRatios[c][k]);
    }
    const float chain = room / largest * StageRatioSum(c, stages);
    period = c == 0 || chain < period ? chain : period;
  }
  return period + float(kBlockSize);
}

inline int NumStages(float value) {
  return 2 * (StepIndex(value, kNumStageSteps) + 1);
}

inline float FeedbackGain(float value) {
  const float v = dsp::Clamp(value, 0.0f, 1.0f);
  return kMaxFeedback * v * (2.0f - v);
}

inline float DampHz(float value) {
  return ExpMap(1.0f - dsp::Clamp(value, 0.0f, 1.0f), kMinDampHz, kMaxDampHz);
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

}  // namespace

const BlockInfo& ApfChain::info() const {
  return kInfo;
}

bool ApfChain::Init(Memory* memory) {
  buffers_ = memory->external->AllocateArray<float>(
      kNumChains * kNumStages * kStageBufferSize);
  delays_ = memory->internal->AllocateArray<float>(kNumChains * kNumStages);
  reads_ = memory->internal->AllocateArray<float>(kNumChains * kNumStages);
  phases_ = memory->internal->AllocateArray<float>(kNumChains * kNumStages);
  work_ = memory->internal->AllocateArray<float>(kNumChains * kBlockSize);
  tap_ = memory->internal->AllocateArray<float>(kNumChains * kBlockSize);
  previous_tap_ = memory->internal->AllocateArray<float>(
      kNumChains * kBlockSize);
  feedback_ = memory->internal->AllocateArray<float>(kNumChains * kBlockSize);
  if (!buffers_ || !delays_ || !reads_ || !phases_ || !work_ || !tap_ ||
      !previous_tap_ || !feedback_) {
    return false;
  }
  Reset();
  return true;
}

void ApfChain::Reset() {
  memset(buffers_, 0,
         sizeof(float) * kNumChains * kNumStages * kStageBufferSize);
  memset(work_, 0, sizeof(float) * kNumChains * kBlockSize);
  memset(tap_, 0, sizeof(float) * kNumChains * kBlockSize);
  memset(previous_tap_, 0, sizeof(float) * kNumChains * kBlockSize);
  memset(feedback_, 0, sizeof(float) * kNumChains * kBlockSize);
  for (int c = 0; c < kNumChains; ++c) {
    for (int k = 0; k < kNumStages; ++k) {
      const float spread = float(c * kNumStages + k) * 0.618034f;
      phases_[c * kNumStages + k] = spread - floorf(spread);
      delays_[c * kNumStages + k] = kMinDelay;
      reads_[c * kNumStages + k] = kMinDelay;
    }
    damp_[c].Reset();
    dc_blocker_[c].Reset();
  }
  write_ = 0;
  diffusion_ = 0.0f;
  feedback_gain_ = 0.0f;
  mod_depth_ = 0.0f;
  width_ = 0.0f;
  stages_ = previous_stages_ = 2;
  fade_ = 1.0f;
  first_ = true;
}

void ApfChain::Process(const ProcessContext& context, const float* params,
                       const Frame* in, Frame* out, size_t size) {
  // The engine calls with kBlockSize; split anything longer.
  while (size) {
    const size_t chunk = size > kBlockSize ? kBlockSize : size;
    ProcessBlock(context, params, in, out, chunk);
    in += chunk;
    out += chunk;
    size -= chunk;
  }
}

void ApfChain::ProcessBlock(const ProcessContext& context,
                            const float* params, const Frame* in, Frame* out,
                            size_t size) {
  const float fs = context.sample_rate;
  const float inverse_size = 1.0f / float(size);

  // --- control ---------------------------------------------------------
  const int stages = NumStages(params[STAGES]);
  if (first_) {
    stages_ = previous_stages_ = stages;
    fade_ = 1.0f;
  } else if (stages != stages_) {
    if (fade_ >= 1.0f) {
      previous_stages_ = stages_;
      stages_ = stages;
      fade_ = 0.0f;
    } else if (stages == previous_stages_) {
      // Back to the tap that was fading out (a STAGES value jittering at
      // a step boundary): turn the fade round where it is. The equal-power
      // gains are symmetric, so swapping the taps and taking 1 - fade
      // keeps both gains where they were.
      previous_stages_ = stages_;
      stages_ = stages;
      fade_ = 1.0f - fade_;
    }
    // A third value during a fade waits for it to end (256 samples), so
    // a tap never drops out mid-fade.
  }

  float scale_target[kNumChains];
  if (context.synced(LENGTH)) {
    // The loop's period (stages + the block of feedback latency) is the
    // note value, or the longest the tapped stages can make (Format then
    // shows that time).
    const float period = fminf(
        SyncedSeconds(params[LENGTH], context.beat_seconds) * fs,
        MaxLoopSamples(stages_, fs)) - float(kBlockSize);
    for (int c = 0; c < kNumChains; ++c) {
      scale_target[c] = period / StageRatioSum(c, stages_);
    }
  } else {
    const float length = ExpMap(dsp::Clamp(params[LENGTH], 0.0f, 1.0f),
                                kMinLength, kMaxLength) * fs;
    scale_target[0] = scale_target[1] = length;
  }

  const float mod_target = dsp::Clamp(params[MOD], 0.0f, 1.0f);
  const float new_diffusion = kMaxDiffusion *
      dsp::Clamp(params[DIFFUSE], 0.0f, 1.0f);
  const float feedback_target = FeedbackGain(params[FEEDBACK]);
  const float damp = dsp::OnePoleCoefficient(DampHz(params[DAMP]), fs);
  const float width_target = dsp::Clamp(params[WIDTH], 0.0f, 1.0f);

  for (int c = 0; c < kNumChains; ++c) {
    scale_target[c] = fmaxf(scale_target[c], kMinDelay / 0.5f);
  }
  // Every stage stays inside its buffer: the tapped ones already do (see
  // MaxLoopSamples), the ones past the tap clamp on their own.
  const float max_stage = floorf(kMaxDelay - kMaxModSeconds * fs);
  const float glide = 1.0f - expf(-float(size) / (kGlideSeconds * fs));

  // DIFFUSE and WIDTH glide over about 15 ms: a sudden coefficient change
  // leaves the stage buffers out of step with the new allpass, a sudden
  // cross-mix swaps two decorrelated signals; both would click.
  const float smooth = 1.0f - expf(-float(size) / (kSmoothSeconds * fs));
  float diffusion_target = diffusion_;
  float width = width_;
  if (first_) {
    diffusion_target = diffusion_ = new_diffusion;
    width = width_ = width_target;
    feedback_gain_ = feedback_target;
    mod_depth_ = mod_target;
  } else {
    diffusion_target += (new_diffusion - diffusion_) * smooth;
    width += (width_target - width_) * smooth;
    mod_depth_ += (mod_target - mod_depth_) * smooth;
  }

  // --- input, with WIDTH's cross-mix ----------------------------------
  // direct = 0.5 + 0.5 width, cross = 1 - direct, ramped from width_.
  float direct = 0.5f + 0.5f * width_;
  const float direct_step = 0.5f * (width - width_) * inverse_size;
  float* work_l = work_;
  float* work_r = work_ + kBlockSize;
  for (size_t i = 0; i < size; ++i) {
    direct += direct_step;
    const float cross = 1.0f - direct;
    work_l[i] = direct * in[i].l + cross * in[i].r + feedback_[i];
    work_r[i] = direct * in[i].r + cross * in[i].l +
        feedback_[kBlockSize + i];
  }

  // --- the chains --------------------------------------------------------
  const float diffusion_start = diffusion_;
  const float diffusion_step = (diffusion_target - diffusion_) * inverse_size;
  const size_t mask = kStageBufferSize - 1;
  const float mod_samples = kMaxModSeconds * fs;
  for (int c = 0; c < kNumChains; ++c) {
    float* work = work_ + c * kBlockSize;
    for (int k = 0; k < kNumStages; ++k) {
      const int index = c * kNumStages + k;
      float* buffer = buffers_ + size_t(index) * kStageBufferSize;

      // The stage's own delay glides to its share of LENGTH, rounded to
      // whole samples: at rest an unmodulated stage reads without
      // interpolation, so it stays a true (lossless) allpass. The slew
      // limit is proportional to the ratio, so all stages arrive together.
      const float ratio = kRatios[c][k];
      const float target = fminf(floorf(scale_target[c] * ratio + 0.5f),
                                 max_stage);
      float base = delays_[index];
      if (first_) {
        base = target;
      } else {
        const float max_step = kMaxSlew * ratio * float(size);
        base += dsp::Clamp((target - base) * glide, -max_step, max_step);
        if (fabsf(target - base) < kSnapSamples) {
          base = target;
        }
      }
      delays_[index] = base;

      // Alternate the coefficient's sign: neighbouring stages' ringing
      // partly cancels, a less coloured smear.
      float g = (k & 1) ? -diffusion_start : diffusion_start;
      const float g_step = (k & 1) ? -diffusion_step : diffusion_step;
      const uint32_t w0 = write_;

      if (IsModulated(k)) {
        // MOD: an LFO on the read position, ramped across the block and
        // read with 4-point Hermite interpolation (linear would dull the
        // highs on every pass round the allpass).
        float phase = phases_[index] + LfoHz(c, k) * float(size) / fs;
        phase -= floorf(phase);
        phases_[index] = phase;
        float depth = base * kMaxModFraction;
        if (depth > mod_samples) {
          depth = mod_samples;
        }
        const float end = dsp::Clamp(
            base + mod_depth_ * depth * dsp::Sine(phase), kMinDelay,
            kMaxDelay);
        float delay = first_ ? end : reads_[index];
        const float delay_step = (end - delay) * inverse_size;
        reads_[index] = end;
        for (size_t i = 0; i < size; ++i) {
          delay += delay_step;
          g += g_step;
          const uint32_t w = w0 + uint32_t(i);
          const uint32_t whole = uint32_t(delay);
          const float t = delay - float(whole);
          const uint32_t r = w - whole;
          const float xm1 = buffer[(r + 1) & mask];
          const float x0 = buffer[r & mask];
          const float x1 = buffer[(r - 1) & mask];
          const float x2 = buffer[(r - 2) & mask];
          const float cc = (x1 - xm1) * 0.5f;
          const float vv = x0 - x1;
          const float ww = cc + vv;
          const float aa = ww + vv + (x2 - x0) * 0.5f;
          const float bb = ww + aa;
          const float delayed = (((aa * t) - bb) * t + cc) * t + x0;
          const float v = work[i] + g * delayed;
          buffer[w & mask] = v;
          work[i] = delayed - g * v;
        }
      } else {
        // Linear interpolation: exact at rest (whole samples), smooth
        // while LENGTH glides.
        float delay = first_ ? base : reads_[index];
        const float delay_step = (base - delay) * inverse_size;
        reads_[index] = base;
        for (size_t i = 0; i < size; ++i) {
          delay += delay_step;
          g += g_step;
          const uint32_t w = w0 + uint32_t(i);
          const uint32_t whole = uint32_t(delay);
          const float t = delay - float(whole);
          const uint32_t r = w - whole;
          const float a = buffer[r & mask];
          const float b = buffer[(r - 1) & mask];
          const float delayed = a + (b - a) * t;
          const float v = work[i] + g * delayed;
          buffer[w & mask] = v;
          work[i] = delayed - g * v;
        }
      }

      if (k + 1 == stages_) {
        memcpy(tap_ + c * kBlockSize, work, sizeof(float) * size);
      }
      if (k + 1 == previous_stages_) {
        memcpy(previous_tap_ + c * kBlockSize, work, sizeof(float) * size);
      }
    }
  }
  write_ += uint32_t(size);
  diffusion_ = diffusion_target;

  // --- the tap crossfade (equal power) ----------------------------------
  const float fade_end = dsp::Clamp(
      fade_ + float(size) / kTapFadeSamples, 0.0f, 1.0f);
  const float in_start = dsp::Sine(0.25f * fade_);
  const float in_end = dsp::Sine(0.25f * fade_end);
  const float out_start = dsp::Sine(0.25f * (1.0f - fade_));
  const float out_end = dsp::Sine(0.25f * (1.0f - fade_end));
  const bool fading = fade_ < 1.0f;
  fade_ = fade_end;

  // --- output and feedback ------------------------------------------------
  // The feedback rotation: at WIDTH 0 the chains swap half their energy
  // each pass, at 1 they stay apart.
  const float angle_start = 0.125f * (1.0f - width_);  // 0..45 degrees
  const float angle_end = 0.125f * (1.0f - width);
  float rotate_cos = dsp::Sine(angle_start + 0.25f);
  float rotate_sin = dsp::Sine(angle_start);
  const float cos_step = (dsp::Sine(angle_end + 0.25f) - rotate_cos) *
      inverse_size;
  const float sin_step = (dsp::Sine(angle_end) - rotate_sin) * inverse_size;
  direct = 0.5f + 0.5f * width_;
  float feedback_gain = feedback_gain_;
  const float feedback_step = (feedback_target - feedback_gain_) *
      inverse_size;
  const float* tap_l = tap_;
  const float* tap_r = tap_ + kBlockSize;
  const float* old_l = previous_tap_;
  const float* old_r = previous_tap_ + kBlockSize;
  float* feedback_l = feedback_;
  float* feedback_r = feedback_ + kBlockSize;
  for (size_t i = 0; i < size; ++i) {
    float yl = tap_l[i];
    float yr = tap_r[i];
    if (fading) {
      const float t = float(i + 1) * inverse_size;
      const float gain_in = dsp::Lerp(in_start, in_end, t);
      const float gain_out = dsp::Lerp(out_start, out_end, t);
      yl = gain_in * yl + gain_out * old_l[i];
      yr = gain_in * yr + gain_out * old_r[i];
    }
    direct += direct_step;
    const float cross = 1.0f - direct;
    out[i].l = Limit(direct * yl + cross * yr);
    out[i].r = Limit(direct * yr + cross * yl);

    feedback_gain += feedback_step;
    rotate_cos += cos_step;
    rotate_sin += sin_step;
    const float fl = rotate_cos * yl + rotate_sin * yr;
    const float fr = rotate_cos * yr - rotate_sin * yl;
    feedback_l[i] = feedback_gain * dsp::SoftSaturate(damp_[0].Lowpass(
        dc_blocker_[0].Process(fl, kDcBlockerPole), damp));
    feedback_r[i] = feedback_gain * dsp::SoftSaturate(damp_[1].Lowpass(
        dc_blocker_[1].Process(fr, kDcBlockerPole), damp));
  }
  feedback_gain_ = feedback_target;
  width_ = width;
  first_ = false;
}

void ApfChain::Format(int param, float value, const ProcessContext& context,
                      char* text, size_t size) const {
  switch (param) {
    case LENGTH:
      if (context.synced(LENGTH)) {
        // stages_: what the audio runs now (an int, read across threads).
        const float fs = context.sample_rate;
        const float longest = MaxLoopSamples(stages_, fs) / fs;
        if (SyncedSeconds(value, context.beat_seconds) <= longest) {
          FormatNoteValue(text, size, NoteValueIndex(value));
        } else {
          FormatSeconds(text, size, longest);
        }
      } else {
        FormatSeconds(text, size, ExpMap(dsp::Clamp(value, 0.0f, 1.0f),
                                         kMinLength, kMaxLength));
      }
      break;
    case STAGES:
      FormatNumber(text, size, float(NumStages(value)), 0, false, " STAGES");
      break;
    case FEEDBACK:
      FormatPercent(text, size, FeedbackGain(value));
      break;
    case DAMP:
      FormatHz(text, size, DampHz(value));
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
