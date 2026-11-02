// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: helpers shared by the test files (header only).

#ifndef SIDEFX_TEST_TEST_SUPPORT_H_
#define SIDEFX_TEST_TEST_SUPPORT_H_

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "engine/block.h"
#include "engine/memory.h"
#include "engine/tempo_state.h"

namespace test {

// Arenas the size of the Seed's (or smaller, for a quick test), from the
// heap. The external one is filled with garbage first, as the SDRAM at
// power-up: a block that forgets to clear a buffer in Reset() shows up.
class TestMemory {
 public:
  explicit TestMemory(size_t external_size = 48u << 20,
                      size_t internal_size = 200u << 10) {
    external_buffer_ = static_cast<uint8_t*>(malloc(external_size));
    internal_buffer_ = static_cast<uint8_t*>(malloc(internal_size));
    uint32_t x = 12345;
    for (size_t i = 0; i < external_size; i += 4096) {
      x = x * 1664525u + 1013904223u;
      memset(external_buffer_ + i, int(x >> 24),
             external_size - i < 4096 ? external_size - i : 4096);
    }
    memset(internal_buffer_, 0xa5, internal_size);
    external_.Init(external_buffer_, external_size);
    internal_.Init(internal_buffer_, internal_size);
    memory_.external = &external_;
    memory_.internal = &internal_;
  }
  ~TestMemory() {
    free(external_buffer_);
    free(internal_buffer_);
  }
  sidefx::Memory* memory() { return &memory_; }
  sidefx::Arena& external() { return external_; }
  sidefx::Arena& internal() { return internal_; }

 private:
  uint8_t* external_buffer_;
  uint8_t* internal_buffer_;
  sidefx::Arena external_;
  sidefx::Arena internal_;
  sidefx::Memory memory_;
};

inline sidefx::TempoState Tempo120() {
  sidefx::TempoState t;
  t.beat_seconds = 0.5f;
  t.bar_phase = 0.0f;
  t.bar_increment = 1.0f / (4.0f * 0.5f * 48014.32f);
  t.external = false;
  return t;
}

inline sidefx::ProcessContext Context(const sidefx::TempoState& tempo,
                                      uint16_t sync_mask) {
  sidefx::ProcessContext c;
  c.sample_rate = 48014.32f;
  c.beat_seconds = tempo.beat_seconds;
  c.bar_phase = tempo.bar_phase;
  c.bar_increment = tempo.bar_increment;
  c.external_clock = tempo.external;
  c.sync_mask = sync_mask;
  c.send = 1.0f;
  return c;
}

inline bool Finite(const sidefx::Frame& f) {
  return isfinite(f.l) && isfinite(f.r);
}

// A deterministic pseudo-random number in [-1, 1).
inline float Noise(uint32_t* state) {
  *state = *state * 1664525u + 1013904223u;
  return float(int32_t(*state)) * (1.0f / 2147483648.0f);
}

}  // namespace test

#endif  // SIDEFX_TEST_TEST_SUPPORT_H_
