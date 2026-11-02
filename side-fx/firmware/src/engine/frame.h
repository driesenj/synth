// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: a stereo sample. Same layout as beads::FloatFrame ({ l, r }).

#ifndef SIDEFX_ENGINE_FRAME_H_
#define SIDEFX_ENGINE_FRAME_H_

namespace sidefx {

struct Frame {
  float l;
  float r;

  Frame& operator+=(const Frame& rhs) {
    l += rhs.l;
    r += rhs.r;
    return *this;
  }
  Frame& operator-=(const Frame& rhs) {
    l -= rhs.l;
    r -= rhs.r;
    return *this;
  }
  Frame& operator*=(float rhs) {
    l *= rhs;
    r *= rhs;
    return *this;
  }
  friend Frame operator+(Frame lhs, const Frame& rhs) {
    lhs += rhs;
    return lhs;
  }
  friend Frame operator-(Frame lhs, const Frame& rhs) {
    lhs -= rhs;
    return lhs;
  }
  friend Frame operator*(Frame lhs, float rhs) {
    lhs *= rhs;
    return lhs;
  }
  friend Frame operator*(float lhs, Frame rhs) {
    rhs *= lhs;
    return rhs;
  }
};

inline Frame MakeFrame(float l, float r) {
  Frame f;
  f.l = l;
  f.r = r;
  return f;
}

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_FRAME_H_
