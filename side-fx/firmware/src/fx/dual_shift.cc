// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: DUAL SHIFT (see dual_shift.h).

#include "fx/dual_shift.h"

#include "stmlib/dsp/units.h"

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  // +-24 semitones, one per detent; continuous under modulation.
  { "PITCH A", 0.645833f, PARAM_BIPOLAR, 0, 48 },   // +7st
  { "PITCH B", 0.395833f, PARAM_BIPOLAR, 0, 48 },   // -5st
  // +-50 cents, one per detent: +d on A, -d on B.
  { "DETUNE", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "DELAY", 0.300000f, PARAM_SYNC, 0, 0 },         // 180ms
  { "FEEDBACK", 0.200000f, 0, 0, 100 },
  // A timbre, not a musical time: 10..150 ms holds no useful note value.
  { "WINDOW", 0.500000f, 0, 0, 0 },                 // 39ms
  { "WIDTH", 0.800000f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "DUAL SHIFT", "SHIFT", DualShift::NUM_PARAMS, kParams, 0.50f, 0,
};

// 2^17 samples = 2.73 s: 2 s of pre-delay, a 150 ms window and the
// interpolator's neighbours fit.
const size_t kLineSize = 131072;
const size_t kLineMask = kLineSize - 1;

const float kMaxDelaySeconds = 2.0f;
const float kMinWindowSeconds = 0.010f;
const float kMaxWindowSeconds = 0.150f;
const int32_t kMaxPreDelay = int32_t(kMaxDelaySeconds * kSampleRate);

// The closest a tap reads: the Hermite reader needs one newer neighbour.
const float kTapOffset = 2.0f;

// A pre-delay or window change crossfades over 1024 samples (21 ms): short
// enough to follow a turned knob, long enough not to click.
const float kFadeIncrement = 1.0f / 1024.0f;

// A window change smaller than this (0.5 %) is not worth a crossfade.
const float kWindowTolerance = 0.005f;

// The loop's gentle lowpass: each repeat a little darker, as on a
// hardware shifter's converters.
const float kLoopLowpassHz = 6000.0f;

const float kSemitoneRange = 24.0f;
const float kDetuneRange = 50.0f;  // cents

}  // namespace

const BlockInfo& DualShift::info() const {
  return kInfo;
}

float DualShift::PitchSemitones(float value) {
  return Bipolar(value, kSemitoneRange);
}

float DualShift::DetuneCents(float value) {
  return Bipolar(value, kDetuneRange);
}

float DualShift::DelaySeconds(float value, bool synced, float beat_seconds) {
  if (synced) {
    const float t = SyncedSeconds(value, beat_seconds);
    return t > kMaxDelaySeconds ? kMaxDelaySeconds : t;
  }
  // Quadratic from 0: the knob's first half covers 0..500 ms, where the
  // short slap and doubling delays live.
  const float v = dsp::Clamp(value, 0.0f, 1.0f);
  return kMaxDelaySeconds * v * v;
}

float DualShift::WindowSeconds(float value) {
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), kMinWindowSeconds,
                kMaxWindowSeconds);
}

bool DualShift::Init(Memory* memory) {
  for (int v = 0; v < 2; ++v) {
    voice_[v].line = memory->external->AllocateArray<float>(kLineSize);
    if (!voice_[v].line) {
      return false;
    }
  }
  loop_lowpass_ = dsp::OnePoleCoefficient(kLoopLowpassHz, kSampleRate);
  Reset();
  return true;
}

void DualShift::Reset() {
  for (int v = 0; v < 2; ++v) {
    Voice& voice = voice_[v];
    memset(voice.line, 0, sizeof(float) * kLineSize);
    // Tap 1 fully open at the window's centre: at unison the echo comes at
    // exactly DELAY (the pre-delay subtracts half a window).
    voice.phase[0] = voice.phase[1] = 0.0f;
    voice.feedback = 0.0f;
    voice.lowpass.Reset();
    voice.dc_blocker.Reset();
    gain_l_[v] = gain_r_[v] = 0.0f;
  }
  write_ = 0;
  for (int k = 0; k < 2; ++k) {
    pre_delay_[k] = 0;
    window_[k] = kMinWindowSeconds * kSampleRate;
    inverse_window_[k] = 1.0f / window_[k];
  }
  fading_ = false;
  fade_ = 0.0f;
  feedback_ = 0.0f;
  primed_ = false;
}

float DualShift::Read(const float* line, int32_t pre, float offset) const {
  const int32_t k = int32_t(offset);
  const float t = offset - float(k);
  const size_t base = write_ - size_t(pre + k);
  const float xm1 = line[(base + 1) & kLineMask];
  const float x0 = line[base & kLineMask];
  const float x1 = line[(base - 1) & kLineMask];
  const float x2 = line[(base - 2) & kLineMask];
  const float c = (x1 - xm1) * 0.5f;
  const float v = x0 - x1;
  const float w = c + v;
  const float a = w + v + (x2 - x0) * 0.5f;
  const float b_neg = w + a;
  return (((a * t) - b_neg) * t + c) * t + x0;
}

float DualShift::Shift(Voice* voice, int setting, float ratio) {
  const float window = window_[setting];
  float phase = voice->phase[setting] + (1.0f - ratio) *
      inverse_window_[setting];
  if (phase >= 1.0f) {
    phase -= 1.0f;
  } else if (phase < 0.0f) {
    phase += 1.0f;
  }
  voice->phase[setting] = phase;
  float phase_1 = phase + 0.5f;
  if (phase_1 >= 1.0f) {
    phase_1 -= 1.0f;
  }
  // sin(pi p): 0 where a tap wraps, so the jump is never heard.
  const float g0 = dsp::Sine(0.5f * phase);
  const float g1 = dsp::Sine(0.5f * phase_1);
  const int32_t pre = pre_delay_[setting];
  return g0 * Read(voice->line, pre, kTapOffset + phase * window) +
      g1 * Read(voice->line, pre, kTapOffset + phase_1 * window);
}

void DualShift::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  // --- control rate --------------------------------------------------------
  const float cents = DetuneCents(params[DETUNE]) * 0.01f;
  float ratio[2];
  ratio[0] = stmlib::SemitonesToRatio(PitchSemitones(params[PITCH_A]) + cents);
  ratio[1] = stmlib::SemitonesToRatio(PitchSemitones(params[PITCH_B]) - cents);

  const float window_target = WindowSeconds(params[WINDOW]) * kSampleRate;
  const float delay = DelaySeconds(
      params[DELAY], context.synced(DELAY), context.beat_seconds) *
      kSampleRate;
  // The open tap sits half a window (plus the reader's margin) behind the
  // pre-delay: take that off so the echo comes at DELAY.
  int32_t pre = int32_t(delay - 0.5f * window_target - kTapOffset + 0.5f);
  pre = pre < 0 ? 0 : (pre > kMaxPreDelay ? kMaxPreDelay : pre);

  const float feedback_target = dsp::Clamp(params[FEEDBACK], 0.0f, 1.0f);
  const float width = dsp::Clamp(params[WIDTH], 0.0f, 1.0f);
  float target_l[2];
  float target_r[2];
  dsp::PanGains(-width, &target_l[0], &target_r[0]);
  dsp::PanGains(width, &target_l[1], &target_r[1]);

  if (!primed_) {
    window_[0] = window_target;
    inverse_window_[0] = 1.0f / window_target;
    pre_delay_[0] = pre;
    feedback_ = feedback_target;
    for (int v = 0; v < 2; ++v) {
      gain_l_[v] = target_l[v];
      gain_r_[v] = target_r[v];
    }
    primed_ = true;
  }
  // At unison (or near enough that the sweep would take minutes) the taps
  // stand still wherever the last pitch left them: two open taps half a
  // window apart are a comb filter. Fade to tap 1 alone at the centre.
  bool recentre[2];
  bool any_recentre = false;
  for (int v = 0; v < 2; ++v) {
    recentre[v] = fabsf(1.0f - ratio[v]) * inverse_window_[0] < 1.0e-7f;
    any_recentre = any_recentre || (recentre[v] && voice_[v].phase[0] != 0.0f);
  }
  // A pre-delay that moved by no more than a clock's jitter stays put (see
  // DelayMoved()): crossfading between two taps a few samples apart would
  // comb the echo with every clock pulse.
  if (!fading_ && (any_recentre ||
                   dsp::DelayMoved(float(pre_delay_[0]), float(pre)) ||
                   fabsf(window_target - window_[0]) >
                   kWindowTolerance * window_[0])) {
    pre_delay_[1] = pre;
    window_[1] = window_target;
    inverse_window_[1] = 1.0f / window_target;
    for (int v = 0; v < 2; ++v) {
      voice_[v].phase[1] = recentre[v] ? 0.0f : voice_[v].phase[0];
    }
    fade_ = 0.0f;
    fading_ = true;
  }

  // Linear ramps across the block for what the engine steps once per block.
  const float step = 1.0f / float(size ? size : 1);
  const float feedback_step = (feedback_target - feedback_) * step;
  float step_l[2];
  float step_r[2];
  for (int v = 0; v < 2; ++v) {
    step_l[v] = (target_l[v] - gain_l_[v]) * step;
    step_r[v] = (target_r[v] - gain_r_[v]) * step;
  }

  // --- audio rate ----------------------------------------------------------
  for (size_t i = 0; i < size; ++i) {
    const float x = 0.5f * (in[i].l + in[i].r);
    feedback_ += feedback_step;

    float gain_old = 1.0f;
    float gain_new = 0.0f;
    if (fading_) {
      fade_ += kFadeIncrement;
      if (fade_ > 1.0f) {
        fade_ = 1.0f;
      }
      gain_old = dsp::Sine(0.25f * (1.0f - fade_));
      gain_new = dsp::Sine(0.25f * fade_);
    }

    write_ = (write_ + 1) & kLineMask;
    float y[2];
    for (int v = 0; v < 2; ++v) {
      Voice& voice = voice_[v];
      voice.line[write_] = x + voice.feedback;

      float s = Shift(&voice, 0, ratio[v]);
      if (fading_) {
        s = gain_old * s + gain_new * Shift(&voice, 1, ratio[v]);
      }
      y[v] = s;

      const float loop = voice.lowpass.Lowpass(
          voice.dc_blocker.Process(s), loop_lowpass_);
      voice.feedback = dsp::SoftSaturate(feedback_ * loop);
    }

    if (fading_ && fade_ >= 1.0f) {
      pre_delay_[0] = pre_delay_[1];
      window_[0] = window_[1];
      inverse_window_[0] = inverse_window_[1];
      for (int v = 0; v < 2; ++v) {
        voice_[v].phase[0] = voice_[v].phase[1];
      }
      fading_ = false;
    }

    out[i].l = gain_l_[0] * y[0] + gain_l_[1] * y[1];
    out[i].r = gain_r_[0] * y[0] + gain_r_[1] * y[1];
    for (int v = 0; v < 2; ++v) {
      gain_l_[v] += step_l[v];
      gain_r_[v] += step_r[v];
    }
  }
}

void DualShift::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  switch (param) {
    case PITCH_A:
    case PITCH_B:
      {
        // Whole semitones on the grid; the fraction when modulation or a
        // fast turn leaves it.
        const float st = PitchSemitones(value);
        const float rounded = floorf(st + 0.5f);
        const bool on_grid = fabsf(st - rounded) < 0.01f;
        FormatSemitones(text, size, on_grid ? rounded : st, !on_grid);
      }
      break;
    case DETUNE:
      FormatNumber(text, size, floorf(DetuneCents(value) + 0.5f), 0, true,
                   "ct");
      break;
    case DELAY:
      if (context.synced(param) &&
          SyncedSeconds(value, context.beat_seconds) <= kMaxDelaySeconds) {
        FormatNoteValue(text, size, NoteValueIndex(value));
      } else {
        // Free, or a note value longer than 2 s: the time it plays, so the
        // screen does not claim the grid.
        FormatSeconds(text, size, DelaySeconds(value, context.synced(param),
                                               context.beat_seconds));
      }
      break;
    case WINDOW:
      FormatSeconds(text, size, WindowSeconds(value));
      break;
    case FEEDBACK:
    case WIDTH:
      FormatPercent(text, size, value);
      break;
    default:
      CopyText(text, size, "");
      break;
  }
}

}  // namespace sidefx
