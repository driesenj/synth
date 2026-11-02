// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: constants every part of the firmware shares.

#ifndef SIDEFX_ENGINE_CONFIG_H_
#define SIDEFX_ENGINE_CONFIG_H_

#include <stddef.h>
#include <stdint.h>

namespace sidefx {

// The Seed's codec runs at MCLK / 256 with MCLK = PLL3P / 4 = 12.29 MHz:
// 48014.32 Hz, not 48 kHz (see plaits/firmware/README.md). Everything that
// turns seconds or hertz into samples uses this.
constexpr float kSampleRate = 48014.32f;

// Samples per audio callback: 0.67 ms. Modulation, parameters and the
// tempo update once per block; blocks smooth what they need within it.
const size_t kBlockSize = 32;

// The four slots, in the order the signal meets them in the serial
// algorithm and the order of the send buttons on the panel.
enum SlotId {
  SLOT_PITCH,
  SLOT_DELAY,
  SLOT_TEXTURE,
  SLOT_REVERB,
  NUM_SLOTS
};

// A block type has up to kMaxBlockParams parameters of its own. The slot
// adds one more, MIX, which the engine applies; it is stored at kMixValue
// and always shown as the last row of the block's last page.
const int kMaxBlockParams = 11;
const int kNumSlotValues = 12;
const int kMixValue = 11;

// Rows per page: one per encoder, K1 at the top.
const int kRowsPerPage = 4;

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_CONFIG_H_
