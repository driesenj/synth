// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: small DSP pieces the blocks share. Header only, float only.
// stmlib (vendor/stmlib/dsp) has the rest: Svf and OnePole filters
// (filter.h), SemitonesToRatio (units.h), SoftClip, Interpolate and
// ParameterInterpolator (dsp.h, parameter_interpolator.h).

#ifndef SIDEFX_FX_DSP_UTIL_H_
#define SIDEFX_FX_DSP_UTIL_H_

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "engine/frame.h"

namespace sidefx {
namespace dsp {

const float kPi = 3.14159265358979f;
const float kTwoPi = 6.28318530717959f;

inline float Clamp(float x, float lo, float hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

inline float Lerp(float a, float b, float t) {
  return a + (b - a) * t;
}

inline float DecibelsToGain(float db) {
  return expf(db * 0.11512925f);
}

// 1 - exp(-2 pi f / fs): the coefficient of a one-pole lowpass at f.
inline float OnePoleCoefficient(float hz, float sample_rate) {
  float c = 1.0f - expf(-kTwoPi * hz / sample_rate);
  return c > 1.0f ? 1.0f : c;
}

// Whether a delay time (samples) has moved far enough from the one playing
// to be worth a crossfade to it. An external clock's pulses are timed on
// the control scan's 250 us grid, so a synced time wanders by a few
// hundredths of a percent from pulse to pulse (more at 24 PPQN), tens of
// samples on a long delay; crossfading between two taps that close sums
// them into a comb that warbles with every pulse. Within 16 samples +
// 0.3 % the tap stays where it is: inside the clock's own jitter, and a
// turned knob is past it after a few samples' worth of turning.
inline bool DelayMoved(float playing, float target) {
  return fabsf(target - playing) > 16.0f + 0.003f * playing;
}

// tanh-like: x (27 + x^2) / (27 + 9 x^2), exact slope 1 at 0, +-1 from
// |x| = 3 on.
inline float SoftSaturate(float x) {
  if (x > 3.0f) {
    return 1.0f;
  } else if (x < -3.0f) {
    return -1.0f;
  }
  const float x2 = x * x;
  return x * (27.0f + x2) / (27.0f + 9.0f * x2);
}

// A triangle with Sine()'s phase, phase in [0, 1): 0 at 0, +1 at 0.25,
// -1 at 0.75.
inline float Triangle(float phase) {
  return phase < 0.25f ? phase * 4.0f
      : (phase < 0.75f ? 2.0f - phase * 4.0f : phase * 4.0f - 4.0f);
}

// sin(2 pi phase) for phase in [0, 1): sin(pi/2 * Triangle(phase)) by its
// Taylor series to the 7th power; error < 2e-4.
inline float Sine(float phase) {
  const float x = Triangle(phase);
  const float x2 = x * x;
  return x * (1.5707963f + x2 * (-0.6459641f + x2 * (0.0796926f -
      x2 * 0.0046818f)));
}

// Equal-power pan, pan in -1 (left) .. +1 (right).
inline void PanGains(float pan, float* left, float* right) {
  const float t = 0.5f * (Clamp(pan, -1.0f, 1.0f) + 1.0f);  // 0..1
  const float t2 = t * t;
  const float u = 1.0f - t;
  const float u2 = u * u;
  // sin(t pi/2) and sin(u pi/2) to 2e-4
  *right = t * (1.5707963f + t2 * (-0.6459641f + t2 * (0.0796926f -
      t2 * 0.0046818f)));
  *left = u * (1.5707963f + u2 * (-0.6459641f + u2 * (0.0796926f -
      u2 * 0.0046818f)));
}

// xorshift32: deterministic, fast, never 0.
class Random {
 public:
  Random() : state_(0x12345678u) { }
  void Seed(uint32_t seed) { state_ = seed ? seed : 0x12345678u; }
  uint32_t Next() {
    uint32_t x = state_;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    state_ = x;
    return x;
  }
  float Uniform() { return float(Next() >> 8) * (1.0f / 16777216.0f); }  // [0, 1)
  float Bipolar() { return Uniform() * 2.0f - 1.0f; }                    // [-1, 1)

 private:
  uint32_t state_;
};

class OnePole {
 public:
  OnePole() : state_(0.0f) { }
  void Reset() { state_ = 0.0f; }
  float Lowpass(float x, float coefficient) {
    state_ += coefficient * (x - state_);
    return state_;
  }
  float Highpass(float x, float coefficient) {
    return x - Lowpass(x, coefficient);
  }
  float state() const { return state_; }

 private:
  float state_;
};

// y = x - x[-1] + r * y[-1], r = 0.995 at 48 kHz: about 38 Hz.
class DcBlocker {
 public:
  DcBlocker() : x_(0.0f), y_(0.0f) { }
  void Reset() { x_ = y_ = 0.0f; }
  float Process(float x, float r = 0.995f) {
    y_ = x - x_ + r * y_;
    x_ = x;
    return y_;
  }

 private:
  float x_;
  float y_;
};

// A ring buffer of T (float or Frame) over memory from an arena, power-of-
// two sized. Write() then Read(d): d = 0 is the sample just written.
template<typename T>
class RingBuffer {
 public:
  RingBuffer() : buffer_(NULL), mask_(0), write_(0) { }

  // size: a power of two.
  void Init(T* buffer, size_t size) {
    buffer_ = buffer;
    mask_ = size - 1;
    write_ = 0;
  }
  void Clear() {
    if (buffer_) {
      memset(buffer_, 0, sizeof(T) * (mask_ + 1));
    }
    write_ = 0;
  }
  size_t size() const { return mask_ + 1; }
  // Clears `count` entries of the memory from index `start` (of the
  // memory, not counted from the write position), to clear a line a piece
  // at a time. Unlike Clear(), the write position stays.
  void ClearPart(size_t start, size_t count) {
    const size_t size = mask_ + 1;
    if (!buffer_ || start >= size) {
      return;
    }
    count = count > size - start ? size - start : count;
    memset(buffer_ + start, 0, sizeof(T) * count);
  }

  void Write(const T& x) {
    write_ = (write_ + 1) & mask_;
    buffer_[write_] = x;
  }
  T Read(size_t delay) const {
    return buffer_[(write_ - delay) & mask_];
  }
  // delay in samples, 0 .. size - 2.
  T ReadLinear(float delay) const {
    const size_t d = size_t(delay);
    const float t = delay - float(d);
    const T a = Read(d);
    const T b = Read(d + 1);
    return a + (b - a) * t;
  }
  // 4-point Hermite, delay 1 .. size - 3: smoother for modulated or
  // pitch-shifted reads.
  T ReadHermite(float delay) const {
    const size_t d = size_t(delay);
    const float t = delay - float(d);
    const T xm1 = Read(d - 1);
    const T x0 = Read(d);
    const T x1 = Read(d + 1);
    const T x2 = Read(d + 2);
    const T c = (x1 - xm1) * 0.5f;
    const T v = x0 - x1;
    const T w = c + v;
    const T a = w + v + (x2 - x0) * 0.5f;
    const T b_neg = w + a;
    return (((a * t) - b_neg) * t + c) * t + x0;
  }

 private:
  T* buffer_;
  size_t mask_;
  size_t write_;
};

// A fractional read from a RingBuffer<float> through a first-order allpass
// (Thiran) interpolator: unity gain at every frequency for any fraction, so
// a feedback loop through it loses nothing however often the signal goes
// round (Hermite loses about 0.5 dB at 10 kHz per pass at a half-sample
// offset, linear far more: a frozen reverb would go dull within seconds).
// The price is a phase that bends at the top, and state: one reader per
// read head, read once per sample, and the delay should move slowly
// (glides, LFOs). The fraction is kept in [0.5, 1.5), so the coefficient
// stays in (-0.2, 1/3], well away from the pole; a whole-sample delay
// reads exactly.
class AllpassReader {
 public:
  AllpassReader() : y_(0.0f) { }
  void Reset() { y_ = 0.0f; }

  // delay as for RingBuffer::Read (0: the sample just written),
  // 0.5 .. size - 2.
  float Read(const RingBuffer<float>& line, float delay) {
    const size_t whole = size_t(delay - 0.5f);
    const float fraction = delay - float(whole);  // 0.5 .. 1.5
    const float eta = (1.0f - fraction) / (1.0f + fraction);
    // H(z) = (eta + z^-1) / (1 + eta z^-1) on the line read at `whole`.
    y_ = eta * (line.Read(whole) - y_) + line.Read(whole + 1);
    return y_;
  }

 private:
  float y_;
};

// The smallest power of two >= n.
inline size_t NextPowerOfTwo(size_t n) {
  size_t p = 1;
  while (p < n) {
    p <<= 1;
  }
  return p;
}

}  // namespace dsp
}  // namespace sidefx

#endif  // SIDEFX_FX_DSP_UTIL_H_
