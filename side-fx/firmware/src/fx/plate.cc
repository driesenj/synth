// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: PLATE. See plate.h for the signal flow.

#include "fx/plate.h"

#include <math.h>

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  { "DECAY", 0.55f, 0, 0, 100 },
  { "SIZE", 0.6f, 0, 0, 100 },
  { "PREDELAY", 0.5f, PARAM_SYNC, 0, 0 },
  { "DAMP", 0.4f, 0, 0, 100 },
  { "DIFFUSE", 0.8f, 0, 0, 100 },
  { "MOD", 0.35f, 0, 0, 100 },
  { "LOWCUT", 0.3f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "PLATE", "PLATE", Plate::NUM_PARAMS, kParams, 0.35f, 0,
};

// Dattorro's lengths are for 29761 Hz; 48014.32 is kSampleRate, spelled
// out so that every table below is a compile-time constant.
constexpr float kLengthScale = 48014.32f / 29761.0f;

constexpr size_t kDiffuserLength[4] = {
  size_t(142 * kLengthScale + 0.5f), size_t(107 * kLengthScale + 0.5f),
  size_t(379 * kLengthScale + 0.5f), size_t(277 * kLengthScale + 0.5f),
};

// Per half (left, right), at SIZE 1, in samples at kSampleRate.
constexpr float kAp1Length[2] = { 672 * kLengthScale, 908 * kLengthScale };
constexpr float kDelay1Length[2] = { 4453 * kLengthScale, 4217 * kLengthScale };
constexpr float kAp2Length[2] = { 1800 * kLengthScale, 2656 * kLengthScale };
constexpr float kDelay2Length[2] = { 3720 * kLengthScale, 3163 * kLengthScale };

constexpr float kMinSize = 0.5f;
constexpr float kMaxSize = 2.0f;
constexpr float kMaxModDepth = 40.0f;  // samples: +-0.8 ms, about 9 cents at 1 Hz
constexpr float kMaxPredelay = 0.5f;

// A SIZE jump glides with the longest line's read head moving at most
// 0.15 samples per sample (about 2.5 semitones of bend).
constexpr float kMaxSizeStep = 0.15f / (4453 * kLengthScale) * float(kBlockSize);

// The time between two decay multiplications: the figure eight has four
// per round trip of 21589 samples at 29761 Hz.
constexpr float kDecaySecondsPerSize = 21589.0f / 29761.0f / 4.0f;

// Dattorro's 0.6, 3 dB down: long tails with sustained input pile up.
constexpr float kOutputGain = 0.42f;

enum TapLine { TAP_DELAY1, TAP_AP2, TAP_DELAY2 };

struct Tap {
  uint8_t half;
  uint8_t line;
  float length;  // samples at SIZE 1
  float gain;
};

// Dattorro's output taps: left from mostly the right half and vice versa.
constexpr Tap kTaps[2][7] = {
  {
    { 1, TAP_DELAY1, 266 * kLengthScale, kOutputGain },
    { 1, TAP_DELAY1, 2974 * kLengthScale, kOutputGain },
    { 1, TAP_AP2, 1913 * kLengthScale, -kOutputGain },
    { 1, TAP_DELAY2, 1996 * kLengthScale, kOutputGain },
    { 0, TAP_DELAY1, 1990 * kLengthScale, -kOutputGain },
    { 0, TAP_AP2, 187 * kLengthScale, -kOutputGain },
    { 0, TAP_DELAY2, 1066 * kLengthScale, -kOutputGain },
  },
  {
    { 0, TAP_DELAY1, 353 * kLengthScale, kOutputGain },
    { 0, TAP_DELAY1, 3627 * kLengthScale, kOutputGain },
    { 0, TAP_AP2, 1228 * kLengthScale, -kOutputGain },
    { 0, TAP_DELAY2, 2673 * kLengthScale, kOutputGain },
    { 1, TAP_DELAY1, 2111 * kLengthScale, -kOutputGain },
    { 1, TAP_AP2, 335 * kLengthScale, -kOutputGain },
    { 1, TAP_DELAY2, 121 * kLengthScale, -kOutputGain },
  },
};

// reverb::AllpassHermite with the delay read through an allpass
// interpolator: in the tank, which the signal goes round thousands of
// times, Hermite's small loss of highs per pass adds up to a dull tail.
inline float AllpassLossless(dsp::RingBuffer<float>* line,
                             dsp::AllpassReader* reader, float x,
                             float delay, float g) {
  const float d = reader->Read(*line, delay - 1.0f);  // read before write
  const float w = x + g * d;
  line->Write(w);
  return d - g * w;
}

// DAMP's tank lowpass: 20 kHz down to 800 Hz, and over the bottom tenth of
// the knob on to no lowpass at all (a one-pole at 20 kHz still takes
// 0.5 dB per pass at 10 kHz).
inline float DampCoefficient(float damp, float sample_rate) {
  const float c = dsp::OnePoleCoefficient(
      ExpMap(1.0f - damp, 800.0f, 20000.0f), sample_rate);
  const float open = 1.0f - 10.0f * damp;
  return open > 0.0f ? c + (1.0f - c) * open : c;
}

bool AllocateLine(Arena* arena, dsp::RingBuffer<float>* line, float length) {
  const size_t size = dsp::NextPowerOfTwo(size_t(length) + 8);
  float* buffer = arena->AllocateArray<float>(size);
  if (!buffer) {
    return false;
  }
  line->Init(buffer, size);
  return true;
}

}  // namespace

const BlockInfo& Plate::info() const {
  return kInfo;
}

float Plate::Rt60(float value) {
  // 0.2 .. 30 s over 90 % of the knob, then on to 1000 s: a hold that
  // still lets the wash breathe out over minutes.
  value = dsp::Clamp(value, 0.0f, 1.0f);
  return value <= 0.9f
      ? ExpMap(value * (1.0f / 0.9f), 0.2f, 30.0f)
      : ExpMap((value - 0.9f) * 10.0f, 30.0f, 1000.0f);
}

float Plate::SizeRatio(float value) {
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), kMinSize, kMaxSize);
}

float Plate::PredelaySeconds(float value, const ProcessContext& context) {
  return TimeParam(dsp::Clamp(value, 0.0f, 1.0f),
                   context.synced(PARAM_PREDELAY), context.beat_seconds,
                   0.001f, kMaxPredelay);
}

float Plate::LowcutHz(float value) {
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), 20.0f, 500.0f);
}

bool Plate::Init(Memory* memory) {
  Arena* arena = memory->external;
  const size_t predelay_size =
      dsp::NextPowerOfTwo(size_t(kMaxPredelay * kSampleRate) + 4);
  float* predelay = arena->AllocateArray<float>(predelay_size);
  if (!predelay) {
    return false;
  }
  predelay_.Init(predelay, predelay_size);
  for (int i = 0; i < 4; ++i) {
    if (!AllocateLine(arena, &diffuser_[i], float(kDiffuserLength[i]))) {
      return false;
    }
  }
  for (int h = 0; h < 2; ++h) {
    Half& half = half_[h];
    if (!AllocateLine(arena, &half.ap1,
                      kAp1Length[h] * kMaxSize + kMaxModDepth) ||
        !AllocateLine(arena, &half.delay1, kDelay1Length[h] * kMaxSize) ||
        !AllocateLine(arena, &half.ap2, kAp2Length[h] * kMaxSize) ||
        !AllocateLine(arena, &half.delay2, kDelay2Length[h] * kMaxSize)) {
      return false;
    }
  }
  Reset();
  return true;
}

void Plate::Reset() {
  predelay_.Reset();
  for (int i = 0; i < 4; ++i) {
    diffuser_[i].Clear();
  }
  for (int h = 0; h < 2; ++h) {
    Half& half = half_[h];
    half.ap1.Clear();
    half.delay1.Clear();
    half.ap2.Clear();
    half.delay2.Clear();
    half.ap1_reader.Reset();
    half.delay1_reader.Reset();
    half.ap2_reader.Reset();
    half.delay2_reader.Reset();
    half.damp.Reset();
    half.lowcut.Reset();
  }
  bandwidth_.Reset();
  input_lowcut_[0].Reset();
  input_lowcut_[1].Reset();
  state_.size = 1.0f;
  state_.decay = 0.0f;
  state_.damp = 1.0f;
  state_.bandwidth = 1.0f;
  state_.lowcut = 0.0f;
  state_.tank_lowcut = 0.0f;
  state_.input_diffusion[0] = state_.input_diffusion[1] = 0.0f;
  state_.decay_diffusion[0] = state_.decay_diffusion[1] = 0.0f;
  state_.mod_depth = 0.0f;
  lfo_phase_ = 0.0f;
  first_block_ = true;
}

void Plate::Targets(const ProcessContext& context, const float* params,
                    Smoothed* target) const {
  const float fs = context.sample_rate;
  const float damp = dsp::Clamp(params[PARAM_DAMP], 0.0f, 1.0f);
  const float diffuse = dsp::Clamp(params[PARAM_DIFFUSE], 0.0f, 1.0f);
  const float mod = dsp::Clamp(params[PARAM_MOD], 0.0f, 1.0f);
  const float lowcut = LowcutHz(params[PARAM_LOWCUT]);
  target->size = SizeRatio(params[PARAM_SIZE]);
  target->decay = 0.0f;  // set by Process() from the smoothed size
  target->damp = DampCoefficient(damp, fs);
  target->bandwidth = dsp::OnePoleCoefficient(
      ExpMap(1.0f - damp, 3000.0f, 18000.0f), fs);
  target->lowcut = dsp::OnePoleCoefficient(lowcut, fs);
  // In the tank at half the cutoff: lows die sooner, so long tails never
  // boom, as on a real plate.
  target->tank_lowcut = dsp::OnePoleCoefficient(0.5f * lowcut, fs);
  // DIFFUSE 1 is about Dattorro's 0.75 / 0.625 and 0.7 / 0.5; at 0 the
  // input diffusers vanish and the tank turns echoey and grainy.
  target->input_diffusion[0] = 0.78f * diffuse;
  target->input_diffusion[1] = 0.65f * diffuse;
  target->decay_diffusion[0] = 0.35f + 0.4f * diffuse;
  target->decay_diffusion[1] = 0.25f + 0.3f * diffuse;
  target->mod_depth = kMaxModDepth * mod;
}

void Plate::Process(const ProcessContext& context, const float* params,
                    const Frame* in, Frame* out, size_t size) {
  Smoothed target;
  Targets(context, params, &target);
  predelay_.set_delay(PredelaySeconds(params[PARAM_PREDELAY], context) *
                      context.sample_rate);
  const float rt60 = Rt60(params[PARAM_DECAY]);

  float size_ratio = state_.size;
  if (first_block_) {
    state_ = target;
    size_ratio = target.size;
    predelay_.Snap();
  } else {
    state_.size = reverb::SmoothTowards(state_.size, target.size, 0.05f,
                                        kMaxSizeStep);
  }
  const float size_increment = (state_.size - size_ratio) / float(size);

  float decay = expf(-6.9077553f * kDecaySecondsPerSize * state_.size /
                     rt60);
  decay = decay > 0.99995f ? 0.99995f : decay;
  const float k = first_block_ ? 1.0f : 0.1f;
  first_block_ = false;
  state_.decay += k * (decay - state_.decay);
  state_.damp += k * (target.damp - state_.damp);
  state_.bandwidth += k * (target.bandwidth - state_.bandwidth);
  state_.lowcut += k * (target.lowcut - state_.lowcut);
  state_.tank_lowcut += k * (target.tank_lowcut - state_.tank_lowcut);
  for (int i = 0; i < 2; ++i) {
    state_.input_diffusion[i] +=
        k * (target.input_diffusion[i] - state_.input_diffusion[i]);
    state_.decay_diffusion[i] +=
        k * (target.decay_diffusion[i] - state_.decay_diffusion[i]);
  }
  state_.mod_depth += k * (target.mod_depth - state_.mod_depth);

  const float mod = dsp::Clamp(params[PARAM_MOD], 0.0f, 1.0f);
  const float lfo_increment = (0.25f + 0.75f * mod) / context.sample_rate;

  const float g_decay = state_.decay;
  const float c_damp = state_.damp;
  const float c_bandwidth = state_.bandwidth;
  const float c_lowcut = state_.lowcut;
  const float c_tank_lowcut = state_.tank_lowcut;
  const float id1 = state_.input_diffusion[0];
  const float id2 = state_.input_diffusion[1];
  const float dd1 = state_.decay_diffusion[0];
  const float dd2 = state_.decay_diffusion[1];
  const float depth = state_.mod_depth;

  for (size_t i = 0; i < size; ++i) {
    size_ratio += size_increment;

    float x = 0.5f * (in[i].l + in[i].r);
    x = predelay_.Process(x);
    x = bandwidth_.Lowpass(x, c_bandwidth);
    x = input_lowcut_[0].Highpass(x, c_lowcut);
    x = input_lowcut_[1].Highpass(x, c_lowcut);
    x = reverb::AllpassFixed(&diffuser_[0], x, kDiffuserLength[0], id1);
    x = reverb::AllpassFixed(&diffuser_[1], x, kDiffuserLength[1], id1);
    x = reverb::AllpassFixed(&diffuser_[2], x, kDiffuserLength[2], id2);
    x = reverb::AllpassFixed(&diffuser_[3], x, kDiffuserLength[3], id2);

    lfo_phase_ += lfo_increment;
    if (lfo_phase_ >= 1.0f) {
      lfo_phase_ -= 1.0f;
    }
    float quadrature = lfo_phase_ + 0.25f;
    if (quadrature >= 1.0f) {
      quadrature -= 1.0f;
    }
    const float modulation[2] = {
      depth * dsp::Sine(lfo_phase_), depth * dsp::Sine(quadrature)
    };

    // Each half's input is the other half's last delay, read before
    // either half writes this sample.
    // Every tank read is fractional (SIZE, MOD) and goes through an
    // allpass interpolator (read before the write: one sample less).
    const float feedback[2] = {
      half_[1].delay2_reader.Read(half_[1].delay2,
                                  kDelay2Length[1] * size_ratio - 1.0f),
      half_[0].delay2_reader.Read(half_[0].delay2,
                                  kDelay2Length[0] * size_ratio - 1.0f),
    };
    for (int h = 0; h < 2; ++h) {
      Half& half = half_[h];
      float a = reverb::SoftLimit(x + g_decay * feedback[h]);
      a = AllpassLossless(&half.ap1, &half.ap1_reader, a,
                          kAp1Length[h] * size_ratio + modulation[h], -dd1);
      float d = half.delay1_reader.Read(
          half.delay1, kDelay1Length[h] * size_ratio - 1.0f);
      half.delay1.Write(a);
      d = half.damp.Lowpass(d, c_damp);
      d = half.lowcut.Highpass(d, c_tank_lowcut);
      d = AllpassLossless(&half.ap2, &half.ap2_reader, g_decay * d,
                          kAp2Length[h] * size_ratio, dd2);
      half.delay2.Write(d);
    }

    float wet[2];
    for (int side = 0; side < 2; ++side) {
      float sum = 0.0f;
      for (int t = 0; t < 7; ++t) {
        const Tap& tap = kTaps[side][t];
        const Half& half = half_[tap.half];
        const dsp::RingBuffer<float>& line = tap.line == TAP_DELAY1
            ? half.delay1 : (tap.line == TAP_AP2 ? half.ap2 : half.delay2);
        sum += tap.gain * line.ReadLinear(tap.length * size_ratio);
      }
      wet[side] = reverb::OutputLimit(sum);
    }
    out[i].l = wet[0];
    out[i].r = wet[1];
  }
}

void Plate::Format(int param, float value, const ProcessContext& context,
                   char* text, size_t size) const {
  value = dsp::Clamp(value, 0.0f, 1.0f);
  switch (param) {
    case PARAM_DECAY: {
      // The top is a long RT60, not a hold: show it ("173s", "1000s").
      const float rt60 = Rt60(value);
      if (rt60 >= 99.95f) {
        FormatNumber(text, size, rt60, 0, false, "s");
      } else {
        FormatSeconds(text, size, rt60);
      }
      break;
    }
    case PARAM_SIZE:
      FormatNumber(text, size, SizeRatio(value), 2, false, "x");
      break;
    case PARAM_PREDELAY:
      if (context.synced(param) &&
          SyncedSeconds(value, context.beat_seconds) <= kMaxPredelay) {
        FormatNoteValue(text, size, NoteValueIndex(value));
      } else {
        FormatSeconds(text, size, PredelaySeconds(value, context));
      }
      break;
    case PARAM_LOWCUT:
      FormatHz(text, size, LowcutHz(value));
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
