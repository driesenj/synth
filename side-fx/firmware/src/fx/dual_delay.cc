// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: DUAL DELAY (see dual_delay.h).

#include "fx/dual_delay.h"

#include <math.h>

namespace sidefx {

namespace {

const float kMinTime = 0.001f;
const float kMaxTime = 10.0f;

// 2^19 samples: 10.9 s, room for 10 s plus the modulation and the
// interpolator. 1 MB per line in 16 bits.
const size_t kBufferSize = 1u << 19;
const float kMinDelay = 2.0f;
const float kMaxDelay = float(kBufferSize) - 8.0f;

// Small changes glide with this time constant, at most kMaxSlew samples
// per sample (pitch 0.5x .. 1.5x while the time moves); a change of more
// than kJumpRatio of the current time crossfades in kFadeSeconds instead.
const float kGlideSeconds = 0.1f;
const float kMaxSlew = 0.5f;
const float kLandSlew = 0.002f;
const float kJumpRatio = 0.2f;
const float kFadeSeconds = 0.03f;

// MOD at 1: 6 ms of time modulation (never more than a quarter of the
// time), at 0.63 Hz on L and 1.37 times that on R.
const float kModDepthSeconds = 0.006f;
const float kModMinHz = 0.13f;
const float kModHzRange = 0.5f;
const float kModRatioR = 1.37f;

// The feedback saturates towards +-kFeedbackHeadroom: a self-oscillating
// loop settles there instead of growing.
const float kFeedbackHeadroom = 1.4f;
const float kMaxFeedback = 1.15f;

const float kLowpassMinHz = 700.0f;
const float kLowpassMaxHz = 20000.0f;
const float kHighpassMinHz = 20.0f;
const float kHighpassMaxHz = 1800.0f;

const ParamInfo kParams[] = {
  // 375 ms and 500 ms: a dotted eighth against a quarter at 120 BPM.
  { "TIME L", 0.643510f, PARAM_SYNC, 0, 0 },
  { "TIME R", 0.674743f, PARAM_SYNC, 0, 0 },
  { "FEEDBACK", 0.400000f, 0, 0, 100 },
  { "CROSS", 0.300000f, 0, 0, 100 },
  { "TONE", 0.400000f, PARAM_BIPOLAR, 0, 100 },
  { "MOD", 0.100000f, 0, 0, 100 },
  { "WIDTH", 1.000000f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "DUAL DELAY", "DUAL", DualDelay::NUM_PARAMS, kParams, 0.35f, 0,
};

inline float Clamp01(float x) {
  return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
}

}  // namespace

const BlockInfo& DualDelay::info() const {
  return kInfo;
}

float DualDelay::FeedbackGain(float value) {
  return kMaxFeedback * Clamp01(value);
}

float DualDelay::LowpassHz(float value) {
  const float t = Bipolar(Clamp01(value), 1.0f);
  return t < 0.0f ? ExpMap(1.0f + t, kLowpassMinHz, kLowpassMaxHz)
      : kLowpassMaxHz;
}

float DualDelay::HighpassHz(float value) {
  const float t = Bipolar(Clamp01(value), 1.0f);
  return t > 0.0f ? ExpMap(t, kHighpassMinHz, kHighpassMaxHz)
      : kHighpassMinHz;
}

bool DualDelay::Init(Memory* memory) {
  for (int i = 0; i < 2; ++i) {
    int16_t* buffer = memory->external->AllocateArray<int16_t>(kBufferSize);
    if (!buffer) {
      return false;
    }
    line_[i].buffer.Init(buffer, kBufferSize);
  }
  Reset();
  return true;
}

void DualDelay::Reset() {
  for (int i = 0; i < 2; ++i) {
    Line& l = line_[i];
    l.buffer.Clear();
    l.delay[0] = l.delay[1] = kMinDelay;
    l.slope[0] = l.slope[1] = 0.0f;
    l.active = 0;
    l.fading = false;
    l.fade = 0.0f;
    l.lfo_phase = i ? 0.25f : 0.0f;
    l.lowpass.Reset();
    l.highpass.Reset();
    depth_[i] = 0.0f;
  }
  primed_ = false;
  feedback_ = 0.0f;
  cross_ = 0.0f;
  width_ = 1.0f;
  lowpass_coefficient_ = 1.0f;
  highpass_coefficient_ = 0.0f;
}

void DualDelay::UpdateTime(Line* line, float target, size_t size) {
  const float glide = 1.0f - expf(-float(size) /
                                  (kGlideSeconds * kSampleRate));
  const float max_step = kMaxSlew * float(size);
  const float land_step = kLandSlew * float(size);
  const float inv_size = 1.0f / float(size);
  const int a = line->active;
  const int b = 1 - a;
  if (!line->fading) {
    const float d = line->delay[a];
    if (fabsf(target - d) > kJumpRatio * d) {
      line->delay[b] = target;
      line->slope[a] = line->slope[b] = 0.0f;
      line->fading = true;
      line->fade = 0.0f;
    } else {
      // Within a sample of the target, walk onto it at 0.2 % of pitch:
      // the glide's last steps would fall under the float's resolution at
      // a long time and stall short of it.
      const float step = fabsf(target - d) < 1.0f
          ? dsp::Clamp(target - d, -land_step, land_step)
          : dsp::Clamp((target - d) * glide, -max_step, max_step);
      line->slope[a] = step * inv_size;
      line->slope[b] = 0.0f;
    }
  } else {
    // The incoming tap follows further changes by gliding; the outgoing
    // one holds still.
    const float gap = target - line->delay[b];
    const float step = fabsf(gap) < 1.0f
        ? dsp::Clamp(gap, -land_step, land_step)
        : dsp::Clamp(gap * glide, -max_step, max_step);
    line->slope[b] = step * inv_size;
    line->slope[a] = 0.0f;
  }
}

void DualDelay::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  if (!size) {
    return;
  }
  float p[NUM_PARAMS];
  for (int i = 0; i < NUM_PARAMS; ++i) {
    p[i] = Clamp01(params[i]);
  }
  float target[2];
  for (int i = 0; i < 2; ++i) {
    const float seconds = TimeParam(p[TIME_L + i], context.synced(TIME_L + i),
                                    context.beat_seconds, kMinTime, kMaxTime);
    target[i] = dsp::Clamp(seconds * kSampleRate, kMinDelay, kMaxDelay);
  }

  const float mod = p[MOD];
  float depth_target[2];
  for (int i = 0; i < 2; ++i) {
    // A quarter of the shorter of the current and the new time keeps the
    // modulated read on the right side of the write head.
    const Line& l = line_[i];
    float shortest = l.delay[l.active] < target[i] ? l.delay[l.active]
        : target[i];
    if (l.fading && l.delay[1 - l.active] < shortest) {
      shortest = l.delay[1 - l.active];
    }
    const float depth = mod * mod * kModDepthSeconds * kSampleRate;
    depth_target[i] = depth < 0.25f * shortest ? depth : 0.25f * shortest;
  }

  const float t = Bipolar(p[TONE], 1.0f);
  const float lowpass_top = dsp::OnePoleCoefficient(kLowpassMaxHz,
                                                    kSampleRate);
  float lowpass_target = dsp::OnePoleCoefficient(LowpassHz(p[TONE]),
                                                 kSampleRate);
  if (t >= 0.0f) {
    lowpass_target = 1.0f;
  } else {
    // Reaches exactly 1 (no filter) at the centre.
    lowpass_target += (1.0f - lowpass_top) * (1.0f + t);
  }
  const float highpass_target = dsp::OnePoleCoefficient(HighpassHz(p[TONE]),
                                                        kSampleRate);

  if (!primed_) {
    for (int i = 0; i < 2; ++i) {
      line_[i].delay[0] = line_[i].delay[1] = target[i];
      line_[i].active = 0;
      line_[i].fading = false;
      depth_[i] = depth_target[i];
    }
    feedback_ = FeedbackGain(p[FEEDBACK]);
    cross_ = p[CROSS];
    width_ = p[WIDTH];
    lowpass_coefficient_ = lowpass_target;
    highpass_coefficient_ = highpass_target;
    primed_ = true;
  }
  for (int i = 0; i < 2; ++i) {
    UpdateTime(&line_[i], target[i], size);
  }

  const float inv_size = 1.0f / float(size);
  float feedback = feedback_;
  float cross = cross_;
  float width = width_;
  float depth_l = depth_[0];
  float depth_r = depth_[1];
  float lowpass = lowpass_coefficient_;
  float highpass = highpass_coefficient_;
  const float d_feedback = (FeedbackGain(p[FEEDBACK]) - feedback) * inv_size;
  const float d_cross = (p[CROSS] - cross) * inv_size;
  const float d_width = (p[WIDTH] - width) * inv_size;
  const float d_depth_l = (depth_target[0] - depth_l) * inv_size;
  const float d_depth_r = (depth_target[1] - depth_r) * inv_size;
  const float d_lowpass = (lowpass_target - lowpass) * inv_size;
  const float d_highpass = (highpass_target - highpass) * inv_size;

  const float lfo_hz = kModMinHz + kModHzRange * mod;
  const float lfo_increment[2] = {
    lfo_hz / kSampleRate, lfo_hz * kModRatioR / kSampleRate
  };
  const float fade_increment = 1.0f / (kFadeSeconds * kSampleRate);
  const float kInverseHeadroom = 1.0f / kFeedbackHeadroom;

  for (size_t n = 0; n < size; ++n) {
    feedback += d_feedback;
    cross += d_cross;
    width += d_width;
    depth_l += d_depth_l;
    depth_r += d_depth_r;
    lowpass += d_lowpass;
    highpass += d_highpass;

    float y[2];
    for (int i = 0; i < 2; ++i) {
      Line& l = line_[i];
      l.lfo_phase += lfo_increment[i];
      if (l.lfo_phase >= 1.0f) {
        l.lfo_phase -= 1.0f;
      }
      const float m = (i ? depth_r : depth_l) * dsp::Sine(l.lfo_phase);
      // Each tap's time from its value at the block's start: accumulating
      // the slope sample by sample would lose it to rounding at 10 s.
      const float elapsed = float(n + 1);
      const int a = l.active;
      float s = l.buffer.Tap(dsp::Clamp(l.delay[a] + l.slope[a] * elapsed + m,
                                        kMinDelay, kMaxDelay));
      if (l.fading) {
        const int b = 1 - a;
        const float s_b = l.buffer.Tap(dsp::Clamp(
            l.delay[b] + l.slope[b] * elapsed + m, kMinDelay, kMaxDelay));
        // Equal power: the two taps hold different moments of the input.
        const float gain_a = dsp::Sine(0.25f * (1.0f - l.fade));
        const float gain_b = dsp::Sine(0.25f * l.fade);
        s = s * gain_a + s_b * gain_b;
        l.fade += fade_increment;
        if (l.fade >= 1.0f) {
          l.active = b;
          l.fading = false;
          l.fade = 0.0f;
        }
      }
      s = l.lowpass.Lowpass(s, lowpass);
      y[i] = l.highpass.Highpass(s, highpass);
    }

    const float f_l = y[0] + cross * (y[1] - y[0]);
    const float f_r = y[1] + cross * (y[0] - y[1]);
    const float fb_l = kFeedbackHeadroom * dsp::SoftSaturate(
        feedback * f_l * kInverseHeadroom);
    const float fb_r = kFeedbackHeadroom * dsp::SoftSaturate(
        feedback * f_r * kInverseHeadroom);
    // Ping-pong moves the whole input into line L.
    const float half_cross = 0.5f * cross;
    const float in_l = in[n].l + half_cross * (in[n].r - in[n].l);
    const float in_r = in[n].r * (1.0f - cross);
    line_[0].buffer.Write(in_l + fb_l);
    line_[1].buffer.Write(in_r + fb_r);

    const float mid = 0.5f * (y[0] + y[1]);
    const float side = 0.5f * (y[0] - y[1]) * width;
    out[n].l = dsp::SoftLimit(mid + side);
    out[n].r = dsp::SoftLimit(mid - side);
  }

  for (int i = 0; i < 2; ++i) {
    for (int t = 0; t < 2; ++t) {
      line_[i].delay[t] += line_[i].slope[t] * float(size);
    }
  }
  feedback_ = FeedbackGain(p[FEEDBACK]);
  cross_ = p[CROSS];
  width_ = p[WIDTH];
  depth_[0] = depth_target[0];
  depth_[1] = depth_target[1];
  lowpass_coefficient_ = lowpass_target;
  highpass_coefficient_ = highpass_target;
}

void DualDelay::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  value = Clamp01(value);
  switch (param) {
    case TIME_L:
    case TIME_R:
      if (context.synced(param) &&
          SyncedSeconds(value, context.beat_seconds) <= kMaxTime) {
        FormatNoteValue(text, size, NoteValueIndex(value));
      } else {
        // Free, or a note value longer than 10 s: the time it plays, so
        // the screen does not claim the grid.
        FormatSeconds(text, size, TimeParam(value, context.synced(param),
                                            context.beat_seconds, kMinTime,
                                            kMaxTime));
      }
      break;
    case FEEDBACK:
      FormatPercent(text, size, FeedbackGain(value));
      break;
    case TONE: {
      const float t = Bipolar(value, 1.0f);
      if (t > -0.01f && t < 0.01f) {
        CopyText(text, size, "FLAT");
      } else if (size > 3) {
        CopyText(text, size, t < 0.0f ? "LP " : "HP ");
        FormatHz(text + 3, size - 3,
                 t < 0.0f ? LowpassHz(value) : HighpassHz(value));
      } else {
        CopyText(text, size, "");
      }
      break;
    }
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
