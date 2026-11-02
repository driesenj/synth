// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the filters WAVESHAPER and TAPE SIM share (header only).
//
// - Halfband2x: a polyphase IIR halfband (two allpass chains, the
//   structure of Laurent de Soras' HIIR) for 2x up- and downsampling around
//   a waveshaper. 6 coefficients, transition 0.06 of the oversampled rate:
//   flat to 18.4 kHz, more than 80 dB rejection from 29.8 kHz at 96 kHz.
//   Coefficients designed with HIIR's elliptic method (scratch script).
// - Svf: a topology-preserving (Zavalishin) state variable filter that
//   gives low, band and high pass at once, x = lp + k bp + hp exactly. It
//   tolerates its coefficients changing every block.

#ifndef SIDEFX_FX_WAVE_SHAPER_DSP_H_
#define SIDEFX_FX_WAVE_SHAPER_DSP_H_

#include <math.h>

#include "fx/dsp_util.h"

namespace sidefx {
namespace dsp {

// Namespace-scope const: internal linkage, one copy per user, no static
// constructor.
const int kHalfbandCoefficients = 6;
const float kHalfband[kHalfbandCoefficients] = {
  0.054217526f, 0.196797970f, 0.383087327f,
  0.573136411f, 0.748720944f, 0.914293710f,
};

class Halfband2x {
 public:
  enum { kNumCoefficients = kHalfbandCoefficients };

  Halfband2x() { Reset(); }

  void Reset() {
    for (int i = 0; i < kNumCoefficients; ++i) {
      x_[i] = y_[i] = 0.0f;
    }
  }

  // One input sample in, two output samples at twice the rate.
  inline void Upsample(float in, float* out_0, float* out_1) {
    float even = in;
    float odd = in;
    for (int i = 0; i < kNumCoefficients; i += 2) {
      even = Stage(i, even);
      odd = Stage(i + 1, odd);
    }
    *out_0 = even;
    *out_1 = odd;
  }

  // Two input samples at twice the rate in, one output sample.
  inline float Downsample(float in_0, float in_1) {
    float even = in_1;
    float odd = in_0;
    for (int i = 0; i < kNumCoefficients; i += 2) {
      even = Stage(i, even);
      odd = Stage(i + 1, odd);
    }
    return 0.5f * (even + odd);
  }

 private:
  // A first-order allpass in z^-2 of the high rate: one sample of the low
  // rate per path.
  inline float Stage(int i, float in) {
    const float out = (in - y_[i]) * kHalfband[i] + x_[i];
    x_[i] = in;
    y_[i] = out;
    return out;
  }

  float x_[kNumCoefficients];
  float y_[kNumCoefficients];
};

// The coefficients of an Svf, computed once per block (tanf is a control
// rate operation).
struct SvfCoefficients {
  float g;     // tan(pi f / fs)
  float k;     // 1 / Q
  float h;     // 1 / (1 + g (g + k))

  void Set(float hz, float q, float sample_rate) {
    float f = hz / sample_rate;
    f = f < 1e-5f ? 1e-5f : (f > 0.49f ? 0.49f : f);
    g = tanf(kPi * f);
    k = 1.0f / q;
    h = 1.0f / (1.0f + g * (g + k));
  }
};

class Svf {
 public:
  Svf() : s1_(0.0f), s2_(0.0f) { }
  void Reset() { s1_ = s2_ = 0.0f; }

  inline void Process(const SvfCoefficients& c, float x, float* lp,
                      float* bp, float* hp) {
    const float high = (x - (c.k + c.g) * s1_ - s2_) * c.h;
    const float band = c.g * high + s1_;
    s1_ = c.g * high + band;
    const float low = c.g * band + s2_;
    s2_ = c.g * band + low;
    *lp = low;
    *bp = band;
    *hp = high;
  }

  inline float Lowpass(const SvfCoefficients& c, float x) {
    float lp, bp, hp;
    Process(c, x, &lp, &bp, &hp);
    return lp;
  }

 private:
  float s1_;
  float s2_;
};

}  // namespace dsp
}  // namespace sidefx

#endif  // SIDEFX_FX_WAVE_SHAPER_DSP_H_
