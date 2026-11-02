// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: TAPE DELAY (see tape_delay.h).
//
// The loop is a delay line read by three taps. A real varispeed changes
// the tape's speed and so every head's pitch alike; here each head's time
// slews in the log domain with the same time constant, which gives the
// same proportional bend while the change is small. A big jump is rate
// limited per head (never past 0.9 samples per sample, so no head ever
// plays backwards); the far heads then take longer to arrive, as the tape
// recorded at the old speed takes longer to reach them.
//
// Wow and flutter are speed variations, so they modulate each head's time
// by the integral of the speed error over that head's span: up to
// P / (2 pi f) seconds for a pitch deviation P at rate f, less for a head
// whose span is short against the period (x / sqrt(1 + x^2), x = 2 pi f
// span: exact in both limits).

#include "fx/tape_delay.h"

#include <math.h>

namespace sidefx {

namespace {

const float kMinTime = 0.03f;
const float kMaxTime = 2.0f;
// A synced TIME goes on to what the tape holds: head 3 at 10.8 s plus the
// wobble (a few ms). 1 BAR stays on the grid down to 67 BPM.
const float kMaxSyncedTime = 3.6f;

// 2^19 samples: 10.9 s, room for head 3 at 10.8 s plus wobble. 1 MB.
const size_t kBufferSize = 1u << 19;
const float kMinDelay = 2.0f;
const float kMaxDelay = float(kBufferSize) - 8.0f;

const float kSlewSeconds = 0.3f;
const float kMaxSlew = 0.9f;
const float kLandSlew = 0.002f;

const float kMaxFeedback = 1.15f;

// Per-sample one-pole coefficients at kSampleRate (written out: a const
// float is no constant expression, and these must not need a static
// constructor).
// 10 ms: head switching and panning without clicks.
const float kGainCoefficient = 0.0020827f;
// Signal envelope for the modulation noise: 2 ms attack, 1.5 s release,
// so a dying tail keeps its hiss while it lasts.
const float kEnvelopeAttack = 0.0104136f;
const float kEnvelopeRelease = 1.38847e-5f;

const float kWowMinHz = 0.5f;
const float kWowHzRange = 1.0f;
const float kWowDepth = 0.006f;      // pitch deviation at WOBBLE 1
const float kFlutterMinHz = 6.0f;
const float kFlutterHzRange = 5.0f;
const float kFlutterDepth = 0.0015f;
const int kDriftBlocks = 256;        // a new random drift target every 0.17 s
const float kDriftCoefficient = 0.004f;

const char* const kHeadLabels[] = {
  "1", "2", "3", "1+2", "2+3", "1+3", "1+2+3"
};
const uint8_t kHeadMasks[] = { 1, 2, 4, 3, 6, 5, 7 };

const ParamInfo kParams[] = {
  { "TIME", 0.548270f, PARAM_SYNC, 0, 0 },  // 300 ms
  { "FEEDBACK", 0.450000f, 0, 0, 100 },
  { "HEADS", 0.000000f, PARAM_STEPPED, TapeDelay::kNumHeadModes, 0 },
  { "WOBBLE", 0.250000f, 0, 0, 100 },
  { "DRIVE", 0.300000f, 0, 0, 100 },
  { "AGE", 0.400000f, 0, 0, 100 },
  { "WIDTH", 0.500000f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "TAPE DELAY", "TAPE", TapeDelay::NUM_PARAMS, kParams, 0.35f, 0,
};

inline float Clamp01(float x) {
  return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
}

}  // namespace

const BlockInfo& TapeDelay::info() const {
  return kInfo;
}

uint8_t TapeDelay::HeadMask(int mode) {
  return kHeadMasks[mode < 0 ? 0 : (mode >= kNumHeadModes
                                    ? kNumHeadModes - 1 : mode)];
}

float TapeDelay::FeedbackGain(float value) {
  return kMaxFeedback * Clamp01(value);
}

bool TapeDelay::Init(Memory* memory) {
  int16_t* buffer = memory->external->AllocateArray<int16_t>(kBufferSize);
  if (!buffer) {
    return false;
  }
  line_.Init(buffer, kBufferSize);
  random_.Seed(0x7a9e0d1u);
  Reset();
  return true;
}

void TapeDelay::Reset() {
  line_.Clear();
  primed_ = false;
  for (int k = 0; k < kNumHeads; ++k) {
    head_delay_[k] = kMinDelay;
    head_slope_[k] = 0.0f;
    out_l_[k] = out_r_[k] = fb_gain_[k] = 0.0f;
  }
  for (int i = 0; i < NUM_RAMPS; ++i) {
    ramp_[i] = 0.0f;
  }
  wow_phase_ = 0.0f;
  flutter_phase_ = 0.0f;
  wow_drift_ = wow_drift_target_ = 0.0f;
  flutter_drift_ = flutter_drift_target_ = 0.0f;
  drift_counter_ = 0;
  lowpass_[0].Reset();
  lowpass_[1].Reset();
  highpass_.Reset();
  envelope_ = 0.0f;
}

void TapeDelay::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  if (!size) {
    return;
  }
  float p[NUM_PARAMS];
  for (int i = 0; i < NUM_PARAMS; ++i) {
    p[i] = Clamp01(params[i]);
  }
  const float inv_size = 1.0f / float(size);

  // --- time: a varispeed slew per head ------------------------------------
  const bool synced = context.synced(TIME);
  const float time = TimeParam(p[TIME], synced, context.beat_seconds,
                               kMinTime, synced ? kMaxSyncedTime : kMaxTime);
  const float head1 = time * kSampleRate;
  if (!primed_) {
    for (int k = 0; k < kNumHeads; ++k) {
      head_delay_[k] = head1 * float(k + 1);
    }
  }
  const float slew = 1.0f - expf(-float(size) / (kSlewSeconds * kSampleRate));
  const float max_step = kMaxSlew * float(size);
  const float land_step = kLandSlew * float(size);
  for (int k = 0; k < kNumHeads; ++k) {
    const float d = head_delay_[k];
    const float target = head1 * float(k + 1);
    // Within a sample of the target, walk onto it at 0.2 % of pitch: the
    // exponential glide's last steps would fall under the float's
    // resolution and stall short of it.
    const float step = fabsf(target - d) < 1.0f
        ? dsp::Clamp(target - d, -land_step, land_step)
        : dsp::Clamp(d * powf(target / d, slew) - d, -max_step, max_step);
    head_slope_[k] = step * inv_size;
  }

  // --- wobble -------------------------------------------------------------
  if (--drift_counter_ <= 0) {
    drift_counter_ = kDriftBlocks;
    wow_drift_target_ = random_.Bipolar();
    flutter_drift_target_ = random_.Bipolar();
  }
  wow_drift_ += kDriftCoefficient * (wow_drift_target_ - wow_drift_);
  flutter_drift_ += kDriftCoefficient * (flutter_drift_target_ -
                                         flutter_drift_);
  const float wobble = p[WOBBLE];
  const float wow_hz = (kWowMinHz + kWowHzRange * wobble) *
      (1.0f + 0.25f * wow_drift_);
  const float flutter_hz = (kFlutterMinHz + kFlutterHzRange * wobble) *
      (1.0f + 0.15f * flutter_drift_);
  const float wow_pitch = wobble * kWowDepth * (1.0f + 0.3f * flutter_drift_);
  const float flutter_pitch = wobble * kFlutterDepth *
      (1.0f + 0.3f * wow_drift_);
  const float wow_samples = wow_pitch / (dsp::kTwoPi * wow_hz) * kSampleRate;
  const float flutter_samples = flutter_pitch /
      (dsp::kTwoPi * flutter_hz) * kSampleRate;

  float target[NUM_RAMPS];
  for (int k = 0; k < kNumHeads; ++k) {
    const float span = head_delay_[k] * (1.0f / kSampleRate);
    const float x_wow = dsp::kTwoPi * wow_hz * span;
    const float x_flutter = dsp::kTwoPi * flutter_hz * span;
    target[RAMP_WOW_1 + k] = wow_samples * x_wow /
        sqrtf(1.0f + x_wow * x_wow);
    target[RAMP_FLUTTER_1 + k] = flutter_samples * x_flutter /
        sqrtf(1.0f + x_flutter * x_flutter);
  }

  // --- drive, feedback, age -----------------------------------------------
  const float drive = p[DRIVE];
  const float drive_gain = 0.3f * (1.0f + 9.0f * drive * drive);
  target[RAMP_FEEDBACK] = FeedbackGain(p[FEEDBACK]);
  target[RAMP_DRIVE_GAIN] = drive_gain;
  target[RAMP_DRIVE_BIAS] = 0.15f * drive;
  // Up to +8 dB of makeup at small levels: driving hard gets louder and
  // denser, as pushing a tape machine does.
  target[RAMP_DRIVE_MAKEUP] = powf(drive_gain * (1.0f / 0.3f), 0.4f) /
      drive_gain;
  const float loop_gain = 0.6f + 1.4f * drive;
  target[RAMP_LOOP_GAIN] = loop_gain;
  target[RAMP_LOOP_INVERSE] = 1.0f / loop_gain;
  const float age = p[AGE];
  target[RAMP_LOWPASS] = dsp::OnePoleCoefficient(
      ExpMap(age, 15000.0f, 2200.0f), kSampleRate);
  target[RAMP_HIGHPASS] = dsp::OnePoleCoefficient(
      ExpMap(age, 25.0f, 280.0f), kSampleRate);
  target[RAMP_NOISE] = 0.02f * age;

  // --- heads: gains and pans ----------------------------------------------
  const uint8_t mask = HeadMask(StepIndex(p[HEADS], kNumHeadModes));
  int num_active = 0;
  for (int k = 0; k < kNumHeads; ++k) {
    num_active += (mask >> k) & 1;
  }
  const float kOutNorm[] = { 1.0f, 1.0f, 0.70710678f, 0.57735027f };
  float head_l[kNumHeads];
  float head_r[kNumHeads];
  float head_fb[kNumHeads];
  int j = 0;
  for (int k = 0; k < kNumHeads; ++k) {
    if ((mask >> k) & 1) {
      const float position = num_active > 1
          ? -1.0f + 2.0f * float(j) / float(num_active - 1) : 0.0f;
      float l, r;
      dsp::PanGains(position * p[WIDTH], &l, &r);
      // Equal power, 0 dB in the middle.
      const float g = kOutNorm[num_active] * 1.41421356f;
      head_l[k] = l * g;
      head_r[k] = r * g;
      head_fb[k] = 1.0f / float(num_active);
      ++j;
    } else {
      head_l[k] = head_r[k] = head_fb[k] = 0.0f;
    }
  }

  if (!primed_) {
    for (int i = 0; i < NUM_RAMPS; ++i) {
      ramp_[i] = target[i];
    }
    for (int k = 0; k < kNumHeads; ++k) {
      out_l_[k] = head_l[k];
      out_r_[k] = head_r[k];
      fb_gain_[k] = head_fb[k];
    }
    primed_ = true;
  }

  float v[NUM_RAMPS];
  float dv[NUM_RAMPS];
  for (int i = 0; i < NUM_RAMPS; ++i) {
    v[i] = ramp_[i];
    dv[i] = (target[i] - v[i]) * inv_size;
  }

  const float wow_increment = wow_hz / kSampleRate;
  const float flutter_increment = flutter_hz / kSampleRate;

  for (size_t n = 0; n < size; ++n) {
    for (int i = 0; i < NUM_RAMPS; ++i) {
      v[i] += dv[i];
    }
    wow_phase_ += wow_increment;
    if (wow_phase_ >= 1.0f) {
      wow_phase_ -= 1.0f;
    }
    flutter_phase_ += flutter_increment;
    if (flutter_phase_ >= 1.0f) {
      flutter_phase_ -= 1.0f;
    }
    const float wow = dsp::Sine(wow_phase_);
    const float flutter = dsp::Sine(flutter_phase_);

    float sum_l = 0.0f;
    float sum_r = 0.0f;
    float sum_fb = 0.0f;
    for (int k = 0; k < kNumHeads; ++k) {
      out_l_[k] += kGainCoefficient * (head_l[k] - out_l_[k]);
      out_r_[k] += kGainCoefficient * (head_r[k] - out_r_[k]);
      fb_gain_[k] += kGainCoefficient * (head_fb[k] - fb_gain_[k]);
      if (out_l_[k] + out_r_[k] + fb_gain_[k] < 1e-6f) {
        continue;  // a silent head costs no SDRAM reads
      }
      // From the block's start value: accumulating the per-sample slope
      // would lose it to rounding on a long delay.
      const float d = head_delay_[k] + head_slope_[k] * float(n + 1) +
          v[RAMP_WOW_1 + k] * wow +
          v[RAMP_FLUTTER_1 + k] * flutter;
      const float y = line_.Tap(dsp::Clamp(d, kMinDelay, kMaxDelay));
      sum_l += y * out_l_[k];
      sum_r += y * out_r_[k];
      sum_fb += y * fb_gain_[k];
    }

    // Record head: saturated input plus the saturated loop.
    const float x = 0.5f * (in[n].l + in[n].r);
    const float bias = v[RAMP_DRIVE_BIAS];
    const float rec = (dsp::SoftSaturate(v[RAMP_DRIVE_GAIN] * x + bias) -
                       dsp::SoftSaturate(bias)) * v[RAMP_DRIVE_MAKEUP];
    const float loop = dsp::SoftSaturate(
        v[RAMP_LOOP_GAIN] * v[RAMP_FEEDBACK] * sum_fb) * v[RAMP_LOOP_INVERSE];
    float w = rec + loop;
    w = lowpass_[0].Lowpass(w, v[RAMP_LOWPASS]);
    w = lowpass_[1].Lowpass(w, v[RAMP_LOWPASS]);
    w = highpass_.Highpass(w, v[RAMP_HIGHPASS]);
    const float a = fabsf(w);
    envelope_ += (a > envelope_ ? kEnvelopeAttack : kEnvelopeRelease) *
        (a - envelope_);
    line_.Write(w + envelope_ * v[RAMP_NOISE] * random_.Bipolar());

    out[n].l = dsp::SoftLimit(sum_l);
    out[n].r = dsp::SoftLimit(sum_r);
  }

  for (int i = 0; i < NUM_RAMPS; ++i) {
    ramp_[i] = target[i];
  }
  for (int k = 0; k < kNumHeads; ++k) {
    head_delay_[k] += head_slope_[k] * float(size);
  }
}

void TapeDelay::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  value = Clamp01(value);
  switch (param) {
    case TIME:
      if (!context.synced(param)) {
        FormatSeconds(text, size, ExpMap(value, kMinTime, kMaxTime));
      } else if (SyncedSeconds(value, context.beat_seconds) >
                 kMaxSyncedTime) {
        // A note value longer than the tape holds: the time it plays, so
        // the screen does not claim the grid.
        FormatSeconds(text, size, kMaxSyncedTime);
      } else {
        FormatNoteValue(text, size, NoteValueIndex(value));
      }
      break;
    case FEEDBACK:
      FormatPercent(text, size, FeedbackGain(value));
      break;
    case HEADS:
      FormatLabel(text, size, kHeadLabels, StepIndex(value, kNumHeadModes));
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
