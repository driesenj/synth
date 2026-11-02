// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: WAVESHAPER (see wave_shaper.h).

#include "fx/wave_shaper.h"

#include <math.h>

#include "fx/dsp_util.h"

namespace sidefx {

using namespace dsp;

namespace {

const ParamInfo kParams[] = {
  { "MODE", 0.0f, PARAM_STEPPED, WaveShaper::MODE_LAST, 0 },
  { "DRIVE", 0.3f, 0, 0, 40 },             // 1 dB per detent
  { "BIAS", 0.5f, PARAM_BIPOLAR, 0, 100 },
  { "TONE", 0.5f, PARAM_BIPOLAR, 0, 100 },
  { "BITS", 1.0f, 0, 0, 28 },              // half a bit per detent
  { "RATE", 1.0f, 0, 0, 100 },
  { "LEVEL", 0.5f, PARAM_BIPOLAR, 0, 48 },  // 0.5 dB per detent
};

const BlockInfo kInfo = {
  "WAVESHAPER", "SHAPE", WaveShaper::PARAM_LAST, kParams, 1.0f, 0,
};

const char* const kModeLabels[] = {
  "SOFT", "HARD", "FOLD", "RECTIFY", "FUZZ", "SINE",
};

const float kMaxDriveDb = 40.0f;
const float kMaxLevelDb = 12.0f;
const float kMinBits = 2.0f;
const float kMaxBits = 16.0f;
const float kMinRateHz = 500.0f;
// The knob's top end is the clean setting of BITS and RATE.
const float kCleanThreshold = 0.999f;
// Block-rate smoothing of the knobs: ~3 ms at 1500 blocks per second.
const float kSmoothing = 0.25f;
// TONE sweeps 6.5 octaves: slower (~10 ms), so a jump is a quick sweep, not
// a filter snapping open.
const float kToneSmoothing = 0.07f;
// The output DC blocker's pole: about 7.6 Hz, under the sub bass (the
// default 0.995, 38 Hz, would take 3 dB from a 40 Hz kick on this 100 %
// wet block). It only has to catch RECTIFY's and FUZZ's DC, which follows
// the signal's envelope; BIAS's static DC is subtracted outright.
const float kDcBlockerPole = 0.999f;
// A MODE change crossfades the two shapers over this many samples.
const float kFadeIncrement = 1.0f / 128.0f;
// Level compensation: a signal peaking at this level keeps its peak level
// whatever the drive.
const float kReferenceLevel = 0.5f;
// What each shaper's output loses (or gains) against SOFT at the same drive,
// measured with a sine at kReferenceLevel: RECTIFY halves the swing once
// its DC is gone, FUZZ's negative side is held low (test drive_adds_harmonics
// prints the levels).
const float kMakeup[WaveShaper::MODE_LAST] = {
  1.0f, 0.9f, 1.0f, 2.0f, 1.15f, 1.0f,
};
// Dark: a lowpass from out of the way down to here. Bright: a high shelf
// above kBrightHz of up to kMaxBrightDb.
const float kDarkMaxHz = 23000.0f;
const float kDarkMinHz = 250.0f;
const float kBrightHz = 1800.0f;
const float kMaxBrightDb = 10.0f;
// The output can only exceed this with BIAS, TONE and LEVEL all at an
// extreme; a hard limit keeps the slot safe there.
const float kOutputLimit = 3.5f;

inline float Frac(float x) {
  return x - floorf(x);
}

// A triangle of period 4 through the origin: x itself up to |x| = 1, then
// folded back, as many times as the drive asks.
inline float Fold(float x) {
  return 1.0f - 4.0f * fabsf(Frac((x + 1.0f) * 0.25f) - 0.5f);
}

// Mid-tread rounding (0 stays 0) without a library call.
inline float RoundToLevels(float x, float levels, float inverse_levels) {
  float v = Clamp(x * levels, -1.0e6f, 1.0e6f);
  v += v >= 0.0f ? 0.5f : -0.5f;
  return float(int32_t(v)) * inverse_levels;
}

}  // namespace

const BlockInfo& WaveShaper::info() const {
  return kInfo;
}

float WaveShaper::Shape(int mode, float x) {
  switch (mode) {
    case MODE_HARD:
      return Clamp(x, -1.0f, 1.0f);
    case MODE_FOLD:
      return Fold(x);
    case MODE_RECTIFY:
      // Full-wave rectified fold: |x|, an octave up, at low drive; more
      // drive folds it into a ripple of ever higher harmonics instead of
      // flattening it into DC (as rectifying a clipper would). With BIAS,
      // a blend towards half-wave.
      return fabsf(Fold(x));
    case MODE_FUZZ:
      // Asymmetric, steep and clipped early on the positive side, softer
      // and lower on the negative: the kink at 0 gives the sputter.
      return x > 0.0f ? SoftSaturate(2.0f * x)
          : 0.6f * SoftSaturate(1.2f * x);
    case MODE_SINE:
      // sin(pi/2 x): the same slope as SOFT at 0, folds smoothly.
      return Sine(Frac(x * 0.25f));
    case MODE_SOFT:
    default:
      return SoftSaturate(x);
  }
}

bool WaveShaper::Init(Memory* memory) {
  // Everything lives in the object (a few hundred bytes of filter state).
  if (!memory) {
    return false;
  }
  Reset();
  return true;
}

void WaveShaper::Reset() {
  for (int c = 0; c < 2; ++c) {
    channel_[c].up.Reset();
    channel_[c].down.Reset();
    channel_[c].dc.Reset();
    channel_[c].bright.Reset();
    channel_[c].dark.Reset();
    channel_[c].held = 0.0f;
  }
  mode_ = previous_mode_ = MODE_SOFT;
  fade_ = 1.0f;
  first_block_ = true;
  hold_phase_ = 0.0f;
  drive_db_ = bias_ = tone_ = level_db_ = 0.0f;
  gain_ = 1.0f;
  offset_ = dc_new_ = dc_old_ = 0.0f;
  out_gain_ = 1.0f;
  dark_mix_ = 0.0f;
}

void WaveShaper::Process(const ProcessContext& context, const float* params,
                         const Frame* in, Frame* out, size_t size) {
  if (size == 0) {
    return;
  }

  // --- control rate -------------------------------------------------------
  const int mode = StepIndex(params[PARAM_MODE], MODE_LAST);
  const float drive_db = Clamp(params[PARAM_DRIVE], 0.0f, 1.0f) * kMaxDriveDb;
  const float bias = Bipolar(Clamp(params[PARAM_BIAS], 0.0f, 1.0f), 1.0f);
  const float tone = Bipolar(Clamp(params[PARAM_TONE], 0.0f, 1.0f), 1.0f);
  const float level_db = Bipolar(Clamp(params[PARAM_LEVEL], 0.0f, 1.0f),
                                 kMaxLevelDb);
  if (first_block_) {
    mode_ = previous_mode_ = mode;
    fade_ = 1.0f;
    drive_db_ = drive_db;
    bias_ = bias;
    tone_ = tone;
    level_db_ = level_db;
  } else {
    if (mode != mode_ && fade_ >= 1.0f) {
      // A change during a fade waits for it to end (under 3 ms), so two
      // shapers at most ever run and their DC terms stay consistent.
      previous_mode_ = mode_;
      mode_ = mode;
      fade_ = 0.0f;
      dc_old_ = dc_new_;
      dc_new_ = Shape(mode_, offset_);
    }
    drive_db_ += kSmoothing * (drive_db - drive_db_);
    bias_ += kSmoothing * (bias - bias_);
    tone_ += kToneSmoothing * (tone - tone_);
    level_db_ += kSmoothing * (level_db - level_db_);
  }

  const float gain = DecibelsToGain(drive_db_);
  // S(r) / S(gain r): 1 at 0 dB, about 0.5 once the reference saturates.
  const float compensation = SoftSaturate(kReferenceLevel) /
      SoftSaturate(gain * kReferenceLevel);
  const float makeup = Lerp(kMakeup[previous_mode_], kMakeup[mode_],
                            fade_ + kFadeIncrement * float(size) > 1.0f
                            ? 1.0f : fade_ + kFadeIncrement * float(size));
  const float out_gain = DecibelsToGain(level_db_) * compensation * makeup;
  const float offset = bias_;
  // The shaper's output at rest: subtracting it right away keeps BIAS from
  // throwing a DC step at the DC blocker.
  const float dc_new = Shape(mode_, offset);
  const float dc_old = Shape(previous_mode_, offset);

  const float bits_value = params[PARAM_BITS];
  const bool crush_bits = bits_value < kCleanThreshold;
  const float bits = kMinBits + (kMaxBits - kMinBits) *
      Clamp(bits_value, 0.0f, 1.0f);
  const float levels = crush_bits ? powf(2.0f, bits - 1.0f) : 1.0f;
  const float inverse_levels = 1.0f / levels;

  const float rate_value = params[PARAM_RATE];
  const float hold_increment = rate_value >= kCleanThreshold ? 1.0f
      : Clamp(ExpMap(Clamp(rate_value, 0.0f, 1.0f), kMinRateHz,
                     context.sample_rate) / context.sample_rate, 0.0f, 1.0f);

  // TONE: a high shelf (fixed frequency, gain 0..+10 dB for 0..+1) into a
  // lowpass (down to 250 Hz at -1). Both always run, so sweeping through
  // the centre never switches a filter's role; the lowpass is blended in
  // over the first eighth of the dark side, while it is still above 13 kHz,
  // so the centre is exactly flat and the crusher's steps stay square.
  const float dark = tone_ < 0.0f ? -tone_ : 0.0f;
  const float bright = tone_ > 0.0f ? tone_ : 0.0f;
  SvfCoefficients dark_coefficients;
  dark_coefficients.Set(kDarkMaxHz * expf(dark * logf(kDarkMinHz /
      kDarkMaxHz)), 0.6f, context.sample_rate);
  SvfCoefficients bright_coefficients;
  bright_coefficients.Set(kBrightHz, 0.707f, context.sample_rate);
  const float bright_weight = DecibelsToGain(kMaxBrightDb * bright) - 1.0f;
  const float dark_mix = dark * 8.0f < 1.0f ? dark * 8.0f : 1.0f;

  // --- audio rate ---------------------------------------------------------
  if (first_block_) {
    gain_ = gain;
    offset_ = offset;
    dc_new_ = dc_new;
    dc_old_ = dc_old;
    out_gain_ = out_gain;
    dark_mix_ = dark_mix;
  }
  first_block_ = false;
  const float step = 1.0f / float(size);
  const float gain_step = (gain - gain_) * step;
  const float offset_step = (offset - offset_) * step;
  const float dc_new_step = (dc_new - dc_new_) * step;
  const float dc_old_step = (dc_old - dc_old_) * step;
  const float out_gain_step = (out_gain - out_gain_) * step;
  const float dark_mix_step = (dark_mix - dark_mix_) * step;
  const bool fading = fade_ < 1.0f;
  const int mode_new = mode_;
  const int mode_old = previous_mode_;

  for (size_t i = 0; i < size; ++i) {
    const float t = float(i + 1);
    const float g = gain_ + gain_step * t;
    const float o = offset_ + offset_step * t;
    const float dn = dc_new_ + dc_new_step * t;
    const float d_o = dc_old_ + dc_old_step * t;
    const float og = out_gain_ + out_gain_step * t;
    float f = 1.0f;
    if (fading) {
      fade_ += kFadeIncrement;
      if (fade_ > 1.0f) {
        fade_ = 1.0f;
      }
      f = fade_;
    }

    hold_phase_ += hold_increment;
    const bool sample = hold_phase_ >= 1.0f;
    if (sample) {
      hold_phase_ -= 1.0f;
    }

    float x[2] = { in[i].l * g, in[i].r * g };
    for (int c = 0; c < 2; ++c) {
      Channel& ch = channel_[c];
      float a, b;
      ch.up.Upsample(x[c], &a, &b);
      a += o;
      b += o;
      float sa = Shape(mode_new, a) - dn;
      float sb = Shape(mode_new, b) - dn;
      if (fading) {
        const float oa = Shape(mode_old, a) - d_o;
        const float ob = Shape(mode_old, b) - d_o;
        sa = oa + (sa - oa) * f;
        sb = ob + (sb - ob) * f;
      }
      float y = ch.down.Downsample(sa, sb);
      y = ch.dc.Process(y, kDcBlockerPole);
      if (crush_bits) {
        y = RoundToLevels(y, levels, inverse_levels);
      }
      if (sample) {
        ch.held = y;
      }
      y = ch.held;
      float lp, bp, hp;
      ch.bright.Process(bright_coefficients, y, &lp, &bp, &hp);
      y += bright_weight * hp;
      y += (dark_mix_ + dark_mix_step * t) * (ch.dark.Lowpass(
          dark_coefficients, y) - y);
      x[c] = Clamp(y * og, -kOutputLimit, kOutputLimit);
    }
    out[i].l = x[0];
    out[i].r = x[1];
  }

  gain_ = gain;
  offset_ = offset;
  dc_new_ = dc_new;
  dc_old_ = dc_old;
  out_gain_ = out_gain;
  dark_mix_ = dark_mix;
  if (!fading) {
    previous_mode_ = mode_;
  }
}

void WaveShaper::Format(int param, float value, const ProcessContext& context,
                        char* text, size_t size) const {
  value = Clamp(value, 0.0f, 1.0f);
  switch (param) {
    case PARAM_MODE:
      FormatLabel(text, size, kModeLabels, StepIndex(value, MODE_LAST));
      break;
    case PARAM_DRIVE:
      FormatDecibels(text, size, value * kMaxDriveDb);
      break;
    case PARAM_BIAS:
    case PARAM_TONE:
      FormatBipolarPercent(text, size, value);
      break;
    case PARAM_BITS:
      if (value >= kCleanThreshold) {
        CopyText(text, size, "CLEAN");
      } else {
        FormatNumber(text, size, kMinBits + (kMaxBits - kMinBits) * value, 1,
                     false, "bit");
      }
      break;
    case PARAM_RATE:
      if (value >= kCleanThreshold) {
        CopyText(text, size, "CLEAN");
      } else {
        FormatHz(text, size, ExpMap(value, kMinRateHz, context.sample_rate));
      }
      break;
    case PARAM_LEVEL:
      FormatDecibels(text, size, Bipolar(value, kMaxLevelDb));
      break;
    default:
      CopyText(text, size, "");
      break;
  }
}

}  // namespace sidefx
