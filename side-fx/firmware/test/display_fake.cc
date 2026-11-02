// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the display functions of hal.h (see display_fake.h).

#include "display_fake.h"

#include <string.h>

namespace test {

namespace {

DisplayState state = { 0, 0, -1, -1, 0, 0.0f, false, { 0 } };

}  // namespace

DisplayState& MutableDisplay() { return state; }  // for the hal functions

const DisplayState& Display() { return state; }

void ResetDisplay() {
  state.flushes = 0;
  state.rows_sent = 0;
  state.last_y0 = -1;
  state.last_y1 = -1;
  state.last_frame = 0;
  state.backlight = 0.0f;
  state.flip = false;
  memset(state.panel, 0, sizeof(state.panel));
}

}  // namespace test

namespace sidefx {
namespace hal {

void DisplayFlush(const uint16_t* frame, int y0, int y1) {
  if (y0 < 0) {
    y0 = 0;
  }
  if (y1 > kDisplayHeight - 1) {
    y1 = kDisplayHeight - 1;
  }
  if (!frame || y1 < y0) {
    return;
  }
  test::DisplayState& s = test::MutableDisplay();
  ++s.flushes;
  s.rows_sent += y1 - y0 + 1;
  s.last_y0 = y0;
  s.last_y1 = y1;
  s.last_frame = frame;
  if (!s.flip) {
    memcpy(&s.panel[y0 * kDisplayWidth], &frame[y0 * kDisplayWidth],
           sizeof(uint16_t) * size_t(kDisplayWidth) * size_t(y1 - y0 + 1));
    return;
  }
  // MADCTL MX | MY: the controller mirrors both addresses.
  for (int y = y0; y <= y1; ++y) {
    const uint16_t* source = &frame[y * kDisplayWidth];
    uint16_t* target = &s.panel[(kDisplayHeight - 1 - y) * kDisplayWidth];
    for (int x = 0; x < kDisplayWidth; ++x) {
      target[kDisplayWidth - 1 - x] = source[x];
    }
  }
}

bool DisplayBusy() { return false; }

void SetBacklight(float level) {
  test::MutableDisplay().backlight =
      level < 0.0f ? 0.0f : (level > 1.0f ? 1.0f : level);
}

// As display_daisy.cc: the new mapping, then the last flushed frame again,
// whole.
void SetDisplayFlip(bool flip) {
  test::DisplayState& s = test::MutableDisplay();
  if (flip == s.flip) {
    return;
  }
  s.flip = flip;
  if (s.last_frame) {
    DisplayFlush(s.last_frame, 0, kDisplayHeight - 1);
  }
}

}  // namespace hal
}  // namespace sidefx
