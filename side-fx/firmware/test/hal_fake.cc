// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the board model behind src/hal.h (see hal_fake.h).

#include "hal_fake.h"

#include <string.h>

namespace test {

namespace {

HalState hal_state;

}  // namespace

HalState& Hal() { return hal_state; }

void PowerCycleHal() {
  HalState& h = hal_state;
  h.time_us = 0;
  for (int i = 0; i < sidefx::hal::kNumCvInputs; ++i) {
    h.cv[i] = CvRawForVolts(0.0f);
  }
  h.shift_now = false;
  h.flash_reads = 0;
  h.flash_erases = 0;
  h.flash_writes = 0;
  h.flash_bytes_written = 0;
  memset(h.sector_erases, 0, sizeof(h.sector_erases));
  h.flash_write_budget = -1;
  h.erases_before_cut = 0;
  h.interrupt_next_erase = false;
  h.bad_sector = -1;
  h.midi_head = 0;
  h.midi_tail = 0;
  h.control_hook = 0;
  h.watchdog_starts = 0;
  h.watchdog_feeds = 0;
  h.critical_enters = 0;
  h.critical_exits = 0;
  h.critical_depth = 0;
  h.bootloader_resets = 0;
}

void ResetHal() {
  memset(hal_state.flash, 0xff, sizeof(hal_state.flash));
  PowerCycleHal();
}

void AdvanceUs(uint64_t us) { hal_state.time_us += us; }
void AdvanceMs(uint32_t ms) { hal_state.time_us += uint64_t(ms) * 1000u; }
uint64_t NowUs() { return hal_state.time_us; }

float CvRawForVolts(float volts) {
  return 0.5022f + volts * (1.0f / -25.38f);
}

void SetCvVolts(int channel, float volts) {
  hal_state.cv[channel] = CvRawForVolts(volts);
}

void PushMidi(uint8_t byte) {
  HalState& h = hal_state;
  int next = (h.midi_head + 1) % kFakeMidiQueueSize;
  if (next == h.midi_tail) {
    return;  // a full UART buffer drops bytes, as the real one would
  }
  h.midi_bytes[h.midi_head] = byte;
  h.midi_times[h.midi_head] = uint32_t(h.time_us);
  h.midi_head = next;
}

void PushMidi(const uint8_t* bytes, int count) {
  for (int i = 0; i < count; ++i) {
    PushMidi(bytes[i]);
  }
}

int MidiPending() {
  const HalState& h = hal_state;
  return (h.midi_head - h.midi_tail + kFakeMidiQueueSize) % kFakeMidiQueueSize;
}

void CutFlashPowerAfter(int32_t bytes) { hal_state.flash_write_budget = bytes; }
void RestoreFlashPower() { hal_state.flash_write_budget = -1; }

}  // namespace test

namespace sidefx {
namespace hal {

using test::hal_state;

uint32_t Milliseconds() { return uint32_t(hal_state.time_us / 1000u); }
uint32_t Microseconds() { return uint32_t(hal_state.time_us); }
uint32_t CycleCount() { return uint32_t(hal_state.time_us * 480u); }

void StartControls(ControlHook hook) { hal_state.control_hook = hook; }
bool ShiftPressedNow() { return hal_state.shift_now; }

float ReadCv(int channel) {
  return channel >= 0 && channel < kNumCvInputs ? hal_state.cv[channel] : 0.502f;
}

bool ReadMidiByte(uint8_t* byte, uint32_t* time_us) {
  test::HalState& h = hal_state;
  if (h.midi_tail == h.midi_head) {
    return false;
  }
  *byte = h.midi_bytes[h.midi_tail];
  *time_us = h.midi_times[h.midi_tail];
  h.midi_tail = (h.midi_tail + 1) % test::kFakeMidiQueueSize;
  return true;
}

void FlashRead(uint32_t offset, void* destination, uint32_t size) {
  ++hal_state.flash_reads;
  uint8_t* d = static_cast<uint8_t*>(destination);
  for (uint32_t i = 0; i < size; ++i) {
    d[i] = offset + i < test::kFakeFlashSize ? hal_state.flash[offset + i] : 0xff;
  }
}

bool FlashErase(uint32_t offset, uint32_t size) {
  test::HalState& h = hal_state;
  ++h.flash_erases;
  if (offset % kFlashSectorSize || size % kFlashSectorSize ||
      offset + size > test::kFakeFlashSize || size == 0) {
    return false;
  }
  if (h.flash_write_budget >= 0) {
    // The power is going: an erase only works while the cut is still to
    // come in the writes.
    if (h.erases_before_cut <= 0 || h.flash_write_budget == 0) {
      return false;
    }
    --h.erases_before_cut;
  }
  if (h.interrupt_next_erase) {
    h.interrupt_next_erase = false;
    memset(h.flash + offset, 0xff, kFlashSectorSize / 2);
    ++h.sector_erases[offset / kFlashSectorSize];
    return false;
  }
  memset(h.flash + offset, 0xff, size);
  for (uint32_t s = offset / kFlashSectorSize;
       s < (offset + size) / kFlashSectorSize; ++s) {
    ++h.sector_erases[s];
  }
  return true;
}

bool FlashWrite(uint32_t offset, const void* data, uint32_t size) {
  test::HalState& h = hal_state;
  ++h.flash_writes;
  if (offset + size > test::kFakeFlashSize) {
    return false;
  }
  if (h.bad_sector >= 0 && size > 0 &&
      int32_t(offset / kFlashSectorSize) <= h.bad_sector &&
      int32_t((offset + size - 1) / kFlashSectorSize) >= h.bad_sector) {
    return true;
  }
  const uint8_t* s = static_cast<const uint8_t*>(data);
  uint32_t n = size;
  bool ok = true;
  if (h.flash_write_budget >= 0) {
    if (uint32_t(h.flash_write_budget) < size) {
      n = uint32_t(h.flash_write_budget);
      ok = false;
    }
    h.flash_write_budget -= int32_t(n);
  }
  for (uint32_t i = 0; i < n; ++i) {
    h.flash[offset + i] &= s[i];  // NOR: programming only clears bits
  }
  h.flash_bytes_written += n;
  return ok;
}

void StartWatchdog() { ++hal_state.watchdog_starts; }
void FeedWatchdog() { ++hal_state.watchdog_feeds; }

uint32_t EnterCritical() {
  ++hal_state.critical_enters;
  return uint32_t(hal_state.critical_depth++);
}

void ExitCritical(uint32_t state) {
  ++hal_state.critical_exits;
  hal_state.critical_depth = int(state);
}

void ResetToBootloader() { ++hal_state.bootloader_resets; }

}  // namespace hal
}  // namespace sidefx
