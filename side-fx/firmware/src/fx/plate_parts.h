// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: reverb building blocks shared by PLATE and FDN VERB (header
// only): allpass diffusers over dsp::RingBuffer, a predelay that crossfades
// between read heads instead of gliding, and the tank's soft limiter.

#ifndef SIDEFX_FX_PLATE_PARTS_H_
#define SIDEFX_FX_PLATE_PARTS_H_

#include <math.h>
#include <stddef.h>

#include "fx/dsp_util.h"

namespace sidefx {
namespace reverb {

// A Schroeder allpass with an integer delay (1 .. line size): the fixed
// input diffusers. w = x + g d, y = d - g w, d = w delayed.
inline float AllpassFixed(dsp::RingBuffer<float>* line, float x,
                          size_t delay, float g) {
  const float d = line->Read(delay - 1);  // read before write: delay - 1
  const float w = x + g * d;
  line->Write(w);
  return d - g * w;
}

// The same with a fractional, modulated or size-scaled delay, 2 .. size - 2,
// read with Hermite interpolation: unlike linear interpolation it barely
// loses highs at half-sample offsets, which matters in a loop that runs
// thousands of times through it (long decays, freeze).
inline float AllpassHermite(dsp::RingBuffer<float>* line, float x,
                            float delay, float g) {
  const float d = line->ReadHermite(delay - 1.0f);
  const float w = x + g * d;
  line->Write(w);
  return d - g * w;
}

// A delay line's output `delay` samples (2 .. size - 2) back, read before
// the next Write().
inline float ReadDelay(const dsp::RingBuffer<float>& line, float delay) {
  return line.ReadHermite(delay - 1.0f);
}

// Exactly linear up to `knee`, then a tanh-like bend that never passes
// `limit` (slope continuous at the knee). Linear matters: even 1 % of
// compression per pass would turn a freeze into a decay of a dB a second.
inline float KneeLimit(float x, float knee, float limit) {
  const float magnitude = fabsf(x);
  if (magnitude <= knee) {
    return x;
  }
  const float range = limit - knee;
  const float y = knee + range * dsp::SoftSaturate((magnitude - knee) / range);
  return x < 0.0f ? -y : y;
}

// The tank's safety net: linear to +-1.5, never beyond +-3. Keeps 100 %
// feedback and +-4 V inputs finite.
inline float SoftLimit(float x) {
  return KneeLimit(x, 1.5f, 3.0f);
}

// The output stage: linear to +-1.25, |y| <= 2 whatever the tank does.
inline float OutputLimit(float x) {
  return KneeLimit(x, 1.25f, 2.0f);
}

// A predelay that never glides: a new delay time crossfades from the old
// read head to the new one over kFadeSamples (a glide over hundreds of
// milliseconds would warble the whole reverb input). T: float or Frame.
template<typename T>
class CrossfadeDelay {
 public:
  enum { kFadeSamples = 1024 };  // 21 ms

  CrossfadeDelay()
      : current_(0), next_(0), target_(0), max_delay_(0), fade_(0.0f),
        fading_(false) { }

  void Init(T* buffer, size_t size) {
    line_.Init(buffer, size);
    max_delay_ = size - 1;
    Reset();
  }

  void Reset() {
    line_.Clear();
    current_ = next_ = target_;
    fade_ = 0.0f;
    fading_ = false;
  }

  // Samples, rounded. Takes effect at the next free crossfade.
  void set_delay(float samples) {
    if (samples < 0.0f) {
      samples = 0.0f;
    }
    size_t d = size_t(samples + 0.5f);
    target_ = d > max_delay_ ? max_delay_ : d;
  }

  // Jumps to the target at once (after Reset: nothing to fade from).
  void Snap() {
    current_ = next_ = target_;
    fading_ = false;
  }

  T Process(const T& x) {
    line_.Write(x);
    if (fading_) {
      fade_ += 1.0f / float(kFadeSamples);
      if (fade_ >= 1.0f) {
        current_ = next_;
        fading_ = false;
      }
    } else if (target_ != current_) {
      next_ = target_;
      fade_ = 0.0f;
      fading_ = true;
    }
    const T a = line_.Read(current_);
    if (!fading_) {
      return a;
    }
    const T b = line_.Read(next_);
    return a + (b - a) * fade_;
  }

 private:
  dsp::RingBuffer<T> line_;
  size_t current_;
  size_t next_;
  size_t target_;
  size_t max_delay_;
  float fade_;
  bool fading_;
};

// One step of a per-block parameter smoother: a one-pole with a slew cap,
// so a jump in SIZE becomes a bounded pitch bend.
inline float SmoothTowards(float current, float target, float coefficient,
                           float max_step) {
  const float step = dsp::Clamp((target - current) * coefficient,
                                -max_step, max_step);
  return current + step;
}

}  // namespace reverb
}  // namespace sidefx

#endif  // SIDEFX_FX_PLATE_PARTS_H_
