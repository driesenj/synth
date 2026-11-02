// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: TAPE SIM (see tape_sim.h).

#include "fx/tape_sim.h"

#include <math.h>

namespace sidefx {

using namespace dsp;

namespace {

const ParamInfo kParams[] = {
  { "DRIVE", 0.3f, 0, 0, 48 },  // 0.5 dB per detent
  { "WOW", 0.2f, 0, 0, 100 },
  { "FLUTTER", 0.2f, 0, 0, 100 },
  { "AGE", 0.3f, 0, 0, 100 },
  { "HISS", 0.1f, 0, 0, 100 },
  { "DROPOUT", 0.0f, 0, 0, 100 },
  { "BUMP", 0.4f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "TAPE SIM", "TSIM", TapeSim::PARAM_LAST, kParams, 1.0f, 0,
};

const float kMaxDriveDb = 24.0f;
const float kReferenceLevel = 0.5f;  // keeps its peak at any drive

// The saturator's memory: m = S(u + b m). With the input pre-filtered by
// (1 - b z^-1) the small-signal response stays flat, but a loud signal
// lags and rounds off differently going up than coming down: a cheap
// stand-in for the hysteresis loop of tape.
const float kMemory = 0.25f;

// Record pre-emphasis / playback de-emphasis: a first-order high shelf of
// kEmphasisMin..Max (+8..+13 dB) above kEmphasisHz, undone exactly after
// the saturator, so loud highs saturate first.
const float kEmphasisHz = 2500.0f;
const float kEmphasisMin = 1.5f;
const float kEmphasisMax = 3.5f;

// Wow and flutter: peak pitch deviation and rate. More WOW is deeper and
// faster (a tired transport); the rates wander so it never loops.
const float kMaxWow = 0.005f;
const float kWowMinHz = 0.3f;
const float kWowMaxHz = 2.0f;
const float kMaxFlutter = 0.0025f;
const float kFlutterMinHz = 6.0f;
const float kFlutterMaxHz = 15.0f;
const int kWowWanderBlocks = 2250;     // ~1.5 s
const int kFlutterWanderBlocks = 150;  // ~0.1 s
const float kWowRateWander = 0.15f;
const float kWowDepthWander = 0.25f;
const float kFlutterRateWander = 0.12f;
const float kFlutterDepthWander = 0.35f;
// Block-rate smoothing of the modulation depths (~20 ms): a WOW jump
// glides like a capstan changing speed instead of stepping the delay.
const float kDepthSmoothing = 0.03f;

// AGE: the playback loss lowpass, 20 kHz (new) down to 2.5 kHz (worn).
const float kLossMaxHz = 20000.0f;
const float kLossMinHz = 2500.0f;
// DROPOUT: up to kDropoutRate events a second, 4..64 ms each, dipping the
// level by up to 20 dB and the loss filter by up to 3 octaves.
const float kDropoutRate = 8.0f;
const float kDropoutOctaves = 3.0f;
// ~7 ms in and out: a dip, not a crackle, and the loss filter's cutoff
// moves at most a quarter octave per block.
const float kDropoutSmoothing = 0.003f;

// HISS: highpassed white noise up to kMaxHiss peak (about -29 dB RMS),
// fully on while the input is above -40 dB, fading over ~1 s below.
const float kMaxHiss = 0.06f;
const float kHissRms = 0.55f;  // uniform noise' RMS after the low cut
const float kHissLowCutHz = 300.0f;
const float kGateFullScale = 100.0f;
const float kGateAttack = 0.01f;
const float kGateRelease = 0.99996f;  // ~0.5 s

// BUMP: a peak of up to +6 dB moving from 120 Hz (subtle, upper bass) to
// 60 Hz (a sub thump) as it grows, with a gentle low cut below it.
const float kMaxBumpDb = 6.0f;
const float kBumpMaxHz = 120.0f;
const float kBumpQ = 1.2f;
const float kBumpOff = 0.005f;

const float kSmoothing = 0.25f;
// AGE and BUMP move filters: slower (~13 ms), as a coefficient step is a
// step in the output.
const float kFilterSmoothing = 0.05f;
const float kOutputLimit = 3.5f;

inline float Frac(float x) {
  return x - floorf(x);
}

// cos(2 pi phase) for phase in [0, 1).
inline float Cosine(float phase) {
  return Sine(Frac(phase + 0.25f));
}

inline float HissPeak(float value) {
  return kMaxHiss * value * value;
}

}  // namespace

const BlockInfo& TapeSim::info() const {
  return kInfo;
}

float TapeSim::WowDepth(float value) {
  value = Clamp(value, 0.0f, 1.0f);
  return kMaxWow * value * sqrtf(value);
}

float TapeSim::FlutterDepth(float value) {
  value = Clamp(value, 0.0f, 1.0f);
  return kMaxFlutter * value * sqrtf(value);
}

float TapeSim::BumpDecibels(float value) {
  return kMaxBumpDb * Clamp(value, 0.0f, 1.0f);
}

float TapeSim::BumpHz(float value) {
  return kBumpMaxHz * ExpMap(Clamp(value, 0.0f, 1.0f), 1.0f, 0.5f);
}

bool TapeSim::Init(Memory* memory) {
  if (!memory || !memory->internal) {
    return false;
  }
  delay_buffer_ = memory->internal->AllocateArray<Frame>(kDelaySize);
  if (!delay_buffer_) {
    return false;
  }
  delay_.Init(delay_buffer_, kDelaySize);
  Reset();
  return true;
}

void TapeSim::Reset() {
  delay_.Clear();
  for (int c = 0; c < 2; ++c) {
    Channel& ch = channel_[c];
    ch.emphasis = ch.last_pre = ch.magnet = ch.de_emphasis = 0.0f;
    ch.bump.Reset();
    ch.low_cut.Reset();
    ch.hiss_low_cut.Reset();
    ch.loss.Reset();
  }
  random_.Seed(0x7a9e5113u);
  first_block_ = true;
  wow_phase_ = flutter_phase_ = 0.0f;
  Wander* wanders[] = { &wow_rate_, &wow_depth_, &flutter_rate_,
                        &flutter_depth_ };
  for (int i = 0; i < 4; ++i) {
    wanders[i]->value = wanders[i]->target = 0.0f;
    wanders[i]->countdown = 0;
  }
  wow_amplitude_ = flutter_amplitude_ = 0.0f;
  delay_samples_ = 1.0f;
  drive_db_ = age_ = bump_ = hiss_level_ = 0.0f;
  drive_gain_ = out_gain_ = 1.0f;
  hiss_gain_ = 0.0f;
  bump_gain_ = 0.0f;
  envelope_ = 0.0f;
  dropout_remaining_ = 0;
  dropout_target_ = dropout_ = 0.0f;
}

float TapeSim::UpdateWander(Wander* w, int period, float smoothing) {
  if (--w->countdown <= 0) {
    w->target = random_.Bipolar();
    w->countdown = period;
  }
  w->value += smoothing * (w->target - w->value);
  return w->value;
}

void TapeSim::Process(const ProcessContext& context, const float* params,
                      const Frame* in, Frame* out, size_t size) {
  if (size == 0) {
    return;
  }
  const float fs = context.sample_rate;
  const float block_seconds = float(size) / fs;

  // --- control rate -------------------------------------------------------
  const float drive_db = Clamp(params[PARAM_DRIVE], 0.0f, 1.0f) * kMaxDriveDb;
  const float age = Clamp(params[PARAM_AGE], 0.0f, 1.0f);
  const float bump = Clamp(params[PARAM_BUMP], 0.0f, 1.0f);
  const float hiss_level = HissPeak(Clamp(params[PARAM_HISS], 0.0f, 1.0f));
  const float wow = Clamp(params[PARAM_WOW], 0.0f, 1.0f);
  const float flutter = Clamp(params[PARAM_FLUTTER], 0.0f, 1.0f);
  const float dropout = Clamp(params[PARAM_DROPOUT], 0.0f, 1.0f);

  // Transport. A deviation D at f Hz is a delay swing of D / (2 pi f) s.
  const float wow_hz = ExpMap(wow, kWowMinHz, kWowMaxHz) *
      (1.0f + kWowRateWander * UpdateWander(&wow_rate_, kWowWanderBlocks,
                                            0.002f));
  const float flutter_hz = ExpMap(flutter, kFlutterMinHz, kFlutterMaxHz) *
      (1.0f + kFlutterRateWander * UpdateWander(&flutter_rate_,
          kFlutterWanderBlocks, 0.03f));
  const float wow_target = WowDepth(wow) / (kTwoPi * wow_hz) * fs *
      (1.0f + kWowDepthWander * UpdateWander(&wow_depth_, kWowWanderBlocks,
                                             0.002f));
  const float flutter_target = FlutterDepth(flutter) /
      (kTwoPi * flutter_hz) * fs * (1.0f + kFlutterDepthWander *
      UpdateWander(&flutter_depth_, kFlutterWanderBlocks, 0.03f));

  if (first_block_) {
    drive_db_ = drive_db;
    age_ = age;
    bump_ = bump;
    hiss_level_ = hiss_level;
    wow_amplitude_ = wow_target;
    flutter_amplitude_ = flutter_target;
  } else {
    drive_db_ += kSmoothing * (drive_db - drive_db_);
    age_ += kFilterSmoothing * (age - age_);
    bump_ += kFilterSmoothing * (bump - bump_);
    hiss_level_ += kSmoothing * (hiss_level - hiss_level_);
    wow_amplitude_ += kDepthSmoothing * (wow_target - wow_amplitude_);
    flutter_amplitude_ += kDepthSmoothing *
        (flutter_target - flutter_amplitude_);
  }
  wow_phase_ = Frac(wow_phase_ + wow_hz * block_seconds);
  flutter_phase_ = Frac(flutter_phase_ + flutter_hz * block_seconds);
  // 1 - cos keeps the delay at its minimum (1 sample) with no modulation:
  // no latency against the dry signal when WOW and FLUTTER are off.
  float delay_end = 1.0f + wow_amplitude_ * (1.0f - Cosine(wow_phase_)) +
      flutter_amplitude_ * (1.0f - Cosine(flutter_phase_));
  delay_end = Clamp(delay_end, 1.0f, float(kDelaySize - 4));
  if (first_block_) {
    delay_samples_ = delay_end;
  }

  // Dropouts: a Poisson process at block rate.
  if (dropout_remaining_ > 0) {
    dropout_remaining_ -= int(size);
    if (dropout_remaining_ <= 0) {
      dropout_remaining_ = 0;
      dropout_target_ = 0.0f;
    }
  } else if (dropout > 0.0f &&
             random_.Uniform() < kDropoutRate * dropout * dropout *
             block_seconds) {
    const float length = random_.Uniform();
    dropout_remaining_ = int(fs * (0.004f + 0.06f * length * length));
    dropout_target_ = (0.35f + 0.55f * random_.Uniform()) *
        (0.4f + 0.6f * dropout);
  }

  const float drive_gain = DecibelsToGain(drive_db_);
  const float out_gain = SoftSaturate(kReferenceLevel) /
      SoftSaturate(drive_gain * kReferenceLevel);
  const float emphasis = Lerp(kEmphasisMin, kEmphasisMax, age_);
  const float emphasis_c = OnePoleCoefficient(kEmphasisHz, fs);
  const float emphasis_hold = emphasis * (1.0f - emphasis_c);
  const float de_emphasis_scale = 1.0f / (1.0f + emphasis -
                                          emphasis * emphasis_c);

  SvfCoefficients bump_coefficients;
  bump_coefficients.Set(BumpHz(bump_), kBumpQ, fs);
  const float bump_gain = bump_ < kBumpOff ? 0.0f
      : (DecibelsToGain(BumpDecibels(bump_)) - 1.0f) * bump_coefficients.k;
  const float low_cut_c = OnePoleCoefficient(10.0f + 20.0f * bump_, fs);
  const float hiss_low_cut_c = OnePoleCoefficient(kHissLowCutHz, fs);

  SvfCoefficients loss_coefficients;
  loss_coefficients.Set(kLossMaxHz * powf(kLossMinHz / kLossMaxHz,
      age_ * sqrtf(age_)) * powf(2.0f, -kDropoutOctaves * dropout_),
      0.6f, fs);

  // --- audio rate ---------------------------------------------------------
  if (first_block_) {
    drive_gain_ = drive_gain;
    out_gain_ = out_gain;
    hiss_gain_ = hiss_level_;
    bump_gain_ = bump_gain;
  }
  first_block_ = false;
  const float step = 1.0f / float(size);
  const float delay_step = (delay_end - delay_samples_) * step;
  const float drive_step = (drive_gain - drive_gain_) * step;
  const float out_step = (out_gain - out_gain_) * step;
  const float hiss_step = (hiss_level_ - hiss_gain_) * step;
  const float bump_step = (bump_gain - bump_gain_) * step;
  const bool hiss_on = hiss_level_ > 0.0f || hiss_gain_ > 0.0f;

  for (size_t i = 0; i < size; ++i) {
    const float t = float(i + 1);
    const float g = drive_gain_ + drive_step * t;
    const float og = out_gain_ + out_step * t;

    // The hiss gate follows the input, before the transport.
    const float level = fmaxf(fabsf(in[i].l), fabsf(in[i].r));
    if (level > envelope_) {
      envelope_ += kGateAttack * (level - envelope_);
    } else {
      envelope_ *= kGateRelease;
      if (envelope_ < 1.0e-7f) {
        envelope_ = 0.0f;
      }
    }
    float hiss = 0.0f;
    if (hiss_on) {
      const float gate = fminf(envelope_ * kGateFullScale, 1.0f);
      hiss = (hiss_gain_ + hiss_step * t) * gate;
    }

    dropout_ += kDropoutSmoothing * (dropout_target_ - dropout_);
    const float dropout_gain = 1.0f - dropout_;

    delay_.Write(in[i]);
    const Frame played = delay_.ReadHermite(delay_samples_ + delay_step * t);
    float x[2] = { played.l, played.r };

    for (int c = 0; c < 2; ++c) {
      Channel& ch = channel_[c];
      // Record emphasis: x + k (x - lowpass(x)).
      ch.emphasis += emphasis_c * (x[c] - ch.emphasis);
      const float pre = x[c] + emphasis * (x[c] - ch.emphasis);
      // Saturation with memory.
      const float u = g * (pre - kMemory * ch.last_pre);
      ch.last_pre = pre;
      ch.magnet = SoftSaturate(u + kMemory * ch.magnet);
      // De-emphasis: the exact inverse of the emphasis filter.
      const float y0 = (ch.magnet + emphasis_hold * ch.de_emphasis) *
          de_emphasis_scale;
      ch.de_emphasis += emphasis_c * (y0 - ch.de_emphasis);
      float y = y0 * og;
      // Head bump: a peak, and the low cut under it.
      float lp, bp, hp;
      ch.bump.Process(bump_coefficients, y, &lp, &bp, &hp);
      y += (bump_gain_ + bump_step * t) * bp;
      y = ch.low_cut.Highpass(y, low_cut_c);
      if (hiss_on) {
        y += hiss * ch.hiss_low_cut.Highpass(random_.Bipolar(),
                                             hiss_low_cut_c);
      }
      // Playback losses and dropouts.
      y = ch.loss.Lowpass(loss_coefficients, y) * dropout_gain;
      x[c] = Clamp(y, -kOutputLimit, kOutputLimit);
    }
    out[i].l = x[0];
    out[i].r = x[1];
  }

  delay_samples_ = delay_end;
  drive_gain_ = drive_gain;
  out_gain_ = out_gain;
  hiss_gain_ = hiss_level_;
  bump_gain_ = bump_gain;
}

void TapeSim::Format(int param, float value, const ProcessContext& context,
                     char* text, size_t size) const {
  value = Clamp(value, 0.0f, 1.0f);
  switch (param) {
    case PARAM_DRIVE:
      FormatDecibels(text, size, value * kMaxDriveDb);
      break;
    case PARAM_WOW:
    case PARAM_FLUTTER:
      if (value <= 0.0f) {
        CopyText(text, size, "OFF");
      } else {
        const float depth = param == PARAM_WOW ? WowDepth(value)
            : FlutterDepth(value);
        FormatNumber(text, size, depth * 100.0f, depth < 0.001f ? 3 : 2,
                     false, "%");
      }
      break;
    case PARAM_HISS:
      if (value <= 0.0f) {
        CopyText(text, size, "OFF");
      } else {
        FormatDecibels(text, size,
                       20.0f * log10f(HissPeak(value) * kHissRms));
      }
      break;
    case PARAM_DROPOUT:
      if (value <= 0.0f) {
        CopyText(text, size, "OFF");
      } else {
        FormatPercent(text, size, value);
      }
      break;
    case PARAM_BUMP:
      if (value < kBumpOff) {
        CopyText(text, size, "OFF");
      } else {
        // "+6dB 60Hz", "+2dB 95Hz": at most 10 characters.
        size_t n = FormatNumber(text, size, BumpDecibels(value), 0, true,
                                "dB ");
        if (n < size) {
          FormatNumber(text + n, size - n, BumpHz(value), 0, false, "Hz");
        }
      }
      break;
    case PARAM_AGE:
      FormatPercent(text, size, value);
      break;
    default:
      CopyText(text, size, "");
      break;
  }
}

}  // namespace sidefx
