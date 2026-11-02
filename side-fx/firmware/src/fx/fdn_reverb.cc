// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: FDN VERB. See fdn_reverb.h for the signal flow.

#include "fx/fdn_reverb.h"

#include <math.h>

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  { "DECAY", 0.6f, 0, 0, 100 },
  { "SIZE", 0.6f, 0, 0, 100 },
  { "PREDELAY", 0.5f, PARAM_SYNC, 0, 0 },
  { "DAMP", 0.4f, 0, 0, 100 },
  { "WIDTH", 1.0f, 0, 0, 100 },
  { "MOD", 0.4f, 0, 0, 100 },
  { "LOWCUT", 0.3f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "FDN VERB", "FDN", FdnReverb::NUM_PARAMS, kParams, 0.35f, 0,
};

// Primes from 35 to 92 ms at SIZE 1: no two share a factor, so their
// echoes never pile up on one another.
constexpr float kLineLength[FdnReverb::kNumLines] = {
  1693.0f, 2063.0f, 2399.0f, 2789.0f, 3163.0f, 3557.0f, 3967.0f, 4421.0f,
};

// Each line's LFO runs at its own multiple of the base rate.
constexpr float kLfoRatio[FdnReverb::kNumLines] = {
  1.0f, 1.17f, 0.83f, 1.31f, 0.71f, 1.43f, 0.93f, 1.21f,
};

// 3.7 to 12.9 ms, different per side: decorrelated, smeared onsets.
constexpr size_t kDiffuserLength[2][FdnReverb::kNumDiffusers] = {
  { 241, 179, 619, 443 },
  { 251, 167, 593, 461 },
};
constexpr float kDiffusion[FdnReverb::kNumDiffusers] = {
  0.65f, 0.65f, 0.55f, 0.55f,
};

constexpr float kMinSize = 0.5f;
constexpr float kMaxSize = 2.0f;
constexpr float kMaxModDepth = 64.0f;  // samples: +-1.3 ms
constexpr float kMaxPredelay = 0.5f;
constexpr float kFreezeThreshold = 0.98f;

// The longest line's read head moves at most 0.15 samples per sample
// while SIZE glides: a bend of about 2.5 semitones at most.
constexpr float kMaxSizeStep = 0.15f / 4421.0f * float(kBlockSize);

// The loop's highpass never goes under 3 Hz (DC can't build up), and
// sits at a quarter of LOWCUT: lows ring shorter, no boom. Frozen, the
// input is closed and nothing new brings DC: it drops to 0.5 Hz, so the
// sub bass holds too (3 Hz would take 3 dB from 40 Hz in 15 s).
constexpr float kMinLoopLowcut = 3.0f;
constexpr float kFrozenLoopLowcut = 0.5f;

// Four lines per side: about as loud as the dry signal at the default
// DECAY (6.6 s) with sustained input.
constexpr float kOutputGain = 0.21f;

constexpr float kHadamardScale = 0.35355339f;  // 1 / sqrt(8)

// In place, orthogonal: energy in = energy out, so the network's decay is
// set by the line filters alone.
inline void Hadamard8(float* x) {
  for (int h = 1; h < 8; h <<= 1) {
    for (int i = 0; i < 8; i += h << 1) {
      for (int j = i; j < i + h; ++j) {
        const float a = x[j];
        const float b = x[j + h];
        x[j] = a + b;
        x[j + h] = a - b;
      }
    }
  }
  for (int i = 0; i < 8; ++i) {
    x[i] *= kHadamardScale;
  }
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

const BlockInfo& FdnReverb::info() const {
  return kInfo;
}

bool FdnReverb::Frozen(float decay_value) {
  return decay_value > kFreezeThreshold;
}

float FdnReverb::Rt60(float value) {
  value = dsp::Clamp(value * (1.0f / kFreezeThreshold), 0.0f, 1.0f);
  return ExpMap(value, 0.2f, 60.0f);
}

float FdnReverb::SizeRatio(float value) {
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), kMinSize, kMaxSize);
}

float FdnReverb::PredelaySeconds(float value, const ProcessContext& context) {
  return TimeParam(dsp::Clamp(value, 0.0f, 1.0f),
                   context.synced(PARAM_PREDELAY), context.beat_seconds,
                   0.001f, kMaxPredelay);
}

float FdnReverb::LowcutHz(float value) {
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), 20.0f, 500.0f);
}

bool FdnReverb::Init(Memory* memory) {
  Arena* arena = memory->external;
  const size_t predelay_size =
      dsp::NextPowerOfTwo(size_t(kMaxPredelay * kSampleRate) + 4);
  Frame* predelay = arena->AllocateArray<Frame>(predelay_size);
  if (!predelay) {
    return false;
  }
  predelay_.Init(predelay, predelay_size);
  for (int side = 0; side < 2; ++side) {
    for (int i = 0; i < kNumDiffusers; ++i) {
      if (!AllocateLine(arena, &diffuser_[side][i],
                        float(kDiffuserLength[side][i]))) {
        return false;
      }
    }
  }
  for (int i = 0; i < kNumLines; ++i) {
    if (!AllocateLine(arena, &line_[i],
                      kLineLength[i] * kMaxSize + kMaxModDepth)) {
      return false;
    }
  }
  Reset();
  return true;
}

void FdnReverb::Reset() {
  predelay_.Reset();
  for (int side = 0; side < 2; ++side) {
    bandwidth_[side].Reset();
    input_lowcut_[side][0].Reset();
    input_lowcut_[side][1].Reset();
    for (int i = 0; i < kNumDiffusers; ++i) {
      diffuser_[side][i].Clear();
    }
  }
  for (int i = 0; i < kNumLines; ++i) {
    line_[i].Clear();
    reader_[i].Reset();
    loop_lowcut_[i].Reset();
    damp_state_[i] = 0.0f;
    lfo_phase_[i] = float(i) / float(kNumLines);
    modulation_[i] = 0.0f;
  }
  size_ = 1.0f;
  decay_value_ = 0.0f;
  damp_value_ = 0.0f;
  freeze_ = 0.0f;
  input_gain_ = 1.0f;
  lowcut_ = 0.0f;
  loop_lowcut_coefficient_ = 0.0f;
  bandwidth_coefficient_ = 1.0f;
  width_ = 1.0f;
  mod_depth_ = 0.0f;
  first_block_ = true;
}

void FdnReverb::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  const float fs = context.sample_rate;
  const float decay_value = dsp::Clamp(params[PARAM_DECAY], 0.0f, 1.0f);
  const float damp_value = dsp::Clamp(params[PARAM_DAMP], 0.0f, 1.0f);
  const float mod = dsp::Clamp(params[PARAM_MOD], 0.0f, 1.0f);
  const float width = dsp::Clamp(params[PARAM_WIDTH], 0.0f, 1.0f);
  const float lowcut_hz = LowcutHz(params[PARAM_LOWCUT]);
  const float target_size = SizeRatio(params[PARAM_SIZE]);
  const float target_freeze = Frozen(decay_value) ? 1.0f : 0.0f;
  predelay_.set_delay(PredelaySeconds(params[PARAM_PREDELAY], context) * fs);

  // --- per-block smoothing --------------------------------------------------
  float size_ratio = size_;
  const float k = first_block_ ? 1.0f : 0.1f;
  if (first_block_) {
    size_ratio = size_ = target_size;
    freeze_ = target_freeze;
    predelay_.Snap();
  } else {
    size_ = reverb::SmoothTowards(size_, target_size, 0.05f, kMaxSizeStep);
    freeze_ += 0.05f * (target_freeze - freeze_);
  }
  const float size_increment = (size_ - size_ratio) / float(size);
  decay_value_ += k * (decay_value - decay_value_);
  damp_value_ += k * (damp_value - damp_value_);
  width_ += k * (width - width_);
  mod_depth_ += k * (kMaxModDepth * mod - mod_depth_);
  const float freeze = freeze_;
  const float open = 1.0f - freeze;
  lowcut_ += k * (dsp::OnePoleCoefficient(lowcut_hz, fs) - lowcut_);
  const float loop_lowcut_hz = kFrozenLoopLowcut + open * (
      fmaxf(0.25f * lowcut_hz, kMinLoopLowcut) - kFrozenLoopLowcut);
  loop_lowcut_coefficient_ += k * (
      dsp::OnePoleCoefficient(loop_lowcut_hz, fs) - loop_lowcut_coefficient_);
  bandwidth_coefficient_ += k * (dsp::OnePoleCoefficient(
      ExpMap(1.0f - damp_value_, 3000.0f, 18000.0f), fs) -
      bandwidth_coefficient_);
  first_block_ = false;

  // The input closes as the loop freezes, ramped over the block.
  const float input_gain_start = input_gain_;
  input_gain_ = open;
  const float input_gain_increment =
      (input_gain_ - input_gain_start) / float(size);

  // Jot's absorptive filters: line i of length L loses 60 dB per RT60 at
  // DC (gain g) and per RT60 * hf_ratio at Nyquist; a one-pole lowpass
  // y += a (x - y) with (1 - b) / (1 + b) = g_hf / g, b = 1 - a, gives
  // that ratio between DC and Nyquist.
  const float rt60 = Rt60(decay_value_);
  const float hf_ratio = ExpMap(1.0f - damp_value_, 0.05f, 1.0f);
  float gain[kNumLines];
  float coefficient[kNumLines];
  for (int i = 0; i < kNumLines; ++i) {
    const float log_gain = -6.9077553f * kLineLength[i] * size_ / (fs * rt60);
    const float g = expf(log_gain);
    const float r = expf(log_gain * (1.0f / hf_ratio - 1.0f));
    float b = (1.0f - r) / (1.0f + r);
    b = b > 0.98f ? 0.98f : b;
    gain[i] = g + (1.0f - g) * freeze;
    coefficient[i] = 1.0f - b * open;
  }

  // Block-rate LFOs, interpolated per sample.
  const float lfo_base = (0.1f + 0.5f * mod) / fs * float(size);
  float modulation_increment[kNumLines];
  for (int i = 0; i < kNumLines; ++i) {
    lfo_phase_[i] += lfo_base * kLfoRatio[i];
    if (lfo_phase_[i] >= 1.0f) {
      lfo_phase_[i] -= 1.0f;
    }
    const float target = mod_depth_ * dsp::Sine(lfo_phase_[i]);
    modulation_increment[i] = (target - modulation_[i]) / float(size);
  }

  const float c_lowcut = lowcut_;
  const float c_loop_lowcut = loop_lowcut_coefficient_;
  const float c_bandwidth = bandwidth_coefficient_;
  const float side_gain = width_;
  float input_gain = input_gain_start;

  for (size_t n = 0; n < size; ++n) {
    size_ratio += size_increment;
    input_gain += input_gain_increment;

    const Frame x = predelay_.Process(in[n]);
    float input[2] = { x.l, x.r };
    for (int side = 0; side < 2; ++side) {
      float s = bandwidth_[side].Lowpass(input[side], c_bandwidth);
      s = input_lowcut_[side][0].Highpass(s, c_lowcut);
      s = input_lowcut_[side][1].Highpass(s, c_lowcut);
      for (int i = 0; i < kNumDiffusers; ++i) {
        s = reverb::AllpassFixed(&diffuser_[side][i], s,
                                 kDiffuserLength[side][i], kDiffusion[i]);
      }
      input[side] = s * input_gain;
    }

    float v[kNumLines];
    for (int i = 0; i < kNumLines; ++i) {
      modulation_[i] += modulation_increment[i];
      // The length is fractional (SIZE, MOD): read through the allpass
      // interpolator, or every pass would take a little of the highs and
      // FREEZE would go dull (read before the write: one sample less).
      const float d = reader_[i].Read(
          line_[i], kLineLength[i] * size_ratio + modulation_[i] - 1.0f);
      damp_state_[i] += coefficient[i] * (d - damp_state_[i]);
      v[i] = loop_lowcut_[i].Highpass(gain[i] * damp_state_[i],
                                      c_loop_lowcut);
    }

    // Even lines carry the left input and make the left output (with
    // alternating signs, so the first echoes add up), odd lines the right.
    const float l = (v[0] - v[2] + v[4] - v[6]) * kOutputGain;
    const float r = (v[1] - v[3] + v[5] - v[7]) * kOutputGain;

    Hadamard8(v);
    v[0] += input[0];
    v[1] += input[1];
    v[2] -= input[0];
    v[3] -= input[1];
    v[4] += input[0];
    v[5] += input[1];
    v[6] -= input[0];
    v[7] -= input[1];
    for (int i = 0; i < kNumLines; ++i) {
      line_[i].Write(reverb::SoftLimit(v[i]));
    }

    const float mid = 0.5f * (l + r);
    const float side = 0.5f * (l - r) * side_gain;
    out[n].l = reverb::OutputLimit(mid + side);
    out[n].r = reverb::OutputLimit(mid - side);
  }
}

void FdnReverb::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  value = dsp::Clamp(value, 0.0f, 1.0f);
  switch (param) {
    case PARAM_DECAY:
      if (Frozen(value)) {
        CopyText(text, size, "FREEZE");
      } else {
        FormatSeconds(text, size, Rt60(value));
      }
      break;
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
