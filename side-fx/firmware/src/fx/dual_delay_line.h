// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the long delay line DUAL DELAY and TAPE DELAY share. 16-bit
// samples over a power-of-two buffer from the external arena (10 s of
// mono is 1 MB instead of 2), full scale +-4.0 so the +-4.0 input range and
// a saturating feedback loop both fit: one step is 1/8191 of +-1.0,
// -78 dB below a +-1 signal, quieter than the repeats it carries.
//
// Writes truncate towards zero: a fading loop reaches exact zero instead of
// circling on the last few steps of quantisation.

#ifndef SIDEFX_FX_DUAL_DELAY_LINE_H_
#define SIDEFX_FX_DUAL_DELAY_LINE_H_

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace sidefx {
namespace dsp {

// Just under +-4.0, so a full-scale write never wraps the int16.
const float kDelayLineFullScale = 3.9995f;

class DelayLine16 {
 public:
  DelayLine16() : buffer_(NULL), mask_(0), write_(0) { }

  // size: a power of two.
  void Init(int16_t* buffer, size_t size) {
    buffer_ = buffer;
    mask_ = size - 1;
    write_ = 0;
  }
  void Clear() {
    if (buffer_) {
      memset(buffer_, 0, sizeof(int16_t) * (mask_ + 1));
    }
    write_ = 0;
  }
  size_t size() const { return mask_ + 1; }

  void Write(float x) {
    const float k = kDelayLineFullScale;
    x = x > k ? k : (x < -k ? -k : x);
    write_ = (write_ + 1) & mask_;
    buffer_[write_] = static_cast<int16_t>(x * 8191.0f);
  }

  // The signal `delay` samples before the sample the next Write() stores,
  // by 4-point Hermite interpolation. Read before writing: delay 1 is the
  // last sample written. delay in 2 .. size() - 4.
  float Tap(float delay) const {
    const float d = delay - 1.0f;
    const int32_t di = static_cast<int32_t>(d);
    const float t = d - float(di);
    const size_t base = write_ - size_t(di);
    const float xm1 = float(buffer_[(base + 1) & mask_]);
    const float x0 = float(buffer_[base & mask_]);
    const float x1 = float(buffer_[(base - 1) & mask_]);
    const float x2 = float(buffer_[(base - 2) & mask_]);
    const float c = (x1 - xm1) * 0.5f;
    const float v = x0 - x1;
    const float w = c + v;
    const float a = w + v + (x2 - x0) * 0.5f;
    const float b_neg = w + a;
    return ((((a * t) - b_neg) * t + c) * t + x0) * (1.0f / 8191.0f);
  }

 private:
  int16_t* buffer_;
  size_t mask_;
  size_t write_;
};

// A delay output's last line of defence: untouched within +-2, then a
// saturating knee that never passes +-3.9 (a highpassed or crossfaded
// signal can overshoot what the line holds).
inline float SoftLimit(float x) {
  const float kKnee = 2.0f;
  const float kRoom = 1.9f;
  if (x > kKnee) {
    float e = (x - kKnee) * (1.0f / kRoom);
    e = e > 3.0f ? 1.0f : e * (27.0f + e * e) / (27.0f + 9.0f * e * e);
    return kKnee + kRoom * e;
  } else if (x < -kKnee) {
    float e = (-x - kKnee) * (1.0f / kRoom);
    e = e > 3.0f ? 1.0f : e * (27.0f + e * e) / (27.0f + 9.0f * e * e);
    return -kKnee - kRoom * e;
  }
  return x;
}

}  // namespace dsp
}  // namespace sidefx

#endif  // SIDEFX_FX_DUAL_DELAY_LINE_H_
