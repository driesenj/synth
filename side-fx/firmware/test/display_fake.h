// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the display half of hal.h on the host. A flush copies
// its rows into a model of the panel's memory at once (so the display is
// never busy) and is recorded, for tests of what the UI sends and when.
// The model maps rows as the ST7789's MADCTL does: SetDisplayFlip changes
// where later writes land, not what the memory already holds.

#ifndef SIDEFX_TEST_DISPLAY_FAKE_H_
#define SIDEFX_TEST_DISPLAY_FAKE_H_

#include <stdint.h>

#include "hal.h"

namespace test {

struct DisplayState {
  int flushes;        // DisplayFlush calls since ResetDisplay()
  int rows_sent;      // their rows, summed
  int last_y0;        // the last flush's rows, inclusive; -1 before any
  int last_y1;
  const uint16_t* last_frame;  // the frame it was given
  float backlight;    // the last SetBacklight, clamped to 0..1
  bool flip;          // the last SetDisplayFlip
  // What the glass shows, row 0 at the top as mounted: with flip off a
  // flushed frame pixel (x, y) lands at (x, y), with flip on at
  // (169 - x, 319 - y).
  uint16_t panel[sidefx::hal::kDisplayWidth * sidefx::hal::kDisplayHeight];
};

const DisplayState& Display();
void ResetDisplay();

}  // namespace test

#endif  // SIDEFX_TEST_DISPLAY_FAKE_H_
