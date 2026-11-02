// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: a model of the board behind src/hal.h, except the
// display (test/display_fake.cc). Time only moves when a test moves it; the
// QSPI flash is a 256 kB NOR array (erase sets 0xFF, a write can only clear
// bits) with counters and power-loss injection; MIDI bytes come from a
// queue the test fills; the system calls are counted.

#ifndef SIDEFX_TEST_HAL_FAKE_H_
#define SIDEFX_TEST_HAL_FAKE_H_

#include <stdint.h>

#include "hal.h"

namespace test {

const uint32_t kFakeFlashSize = 256u << 10;
const uint32_t kFakeFlashSectors = kFakeFlashSize / sidefx::hal::kFlashSectorSize;
const int kFakeMidiQueueSize = 4096;

struct HalState {
  uint64_t time_us;            // Microseconds() is its low 32 bits
  float cv[sidefx::hal::kNumCvInputs];  // ReadCv(), raw 0..1
  bool shift_now;              // ShiftPressedNow()

  uint8_t flash[kFakeFlashSize];
  int flash_reads;             // calls
  int flash_erases;            // calls (each may cover several sectors)
  int flash_writes;            // calls
  uint32_t flash_bytes_written;
  uint32_t sector_erases[kFakeFlashSectors];  // per 4 kB sector
  // Power-loss model: while >= 0, writes stop after this many more bytes
  // (the write that crosses it is cut short and fails) and erases fail
  // untouched; -1 is normal operation.
  int32_t flash_write_budget;
  // ... though this many more erases still work first (0: none), so a cut
  // can land in the writes after them.
  int erases_before_cut;
  bool interrupt_next_erase;   // the next erase clears only half a sector and fails
  // A worn sector (-1: none): writes into it report success but program
  // nothing, as libDaisy's QSPIHandle::Write does when a page program
  // fails (it ignores WritePage's result).
  int32_t bad_sector;

  uint8_t midi_bytes[kFakeMidiQueueSize];
  uint32_t midi_times[kFakeMidiQueueSize];
  int midi_head;
  int midi_tail;

  sidefx::hal::ControlHook control_hook;  // StartControls()
  int watchdog_starts;
  int watchdog_feeds;
  int critical_enters;
  int critical_exits;
  int critical_depth;
  int bootloader_resets;
};

HalState& Hal();

// Everything as at the first power-up: time 0, flash erased, CV inputs at
// 0 V, no MIDI, counters 0.
void ResetHal();
// A power cycle: time back to 0 and counters cleared, the flash kept.
void PowerCycleHal();

void AdvanceUs(uint64_t us);
void AdvanceMs(uint32_t ms);
uint64_t NowUs();

// The raw reading the nominal input stage gives for `volts` at the jack.
float CvRawForVolts(float volts);
void SetCvVolts(int channel, float volts);

// MIDI bytes arriving now (ReadMidiByte returns them in order).
void PushMidi(uint8_t byte);
void PushMidi(const uint8_t* bytes, int count);
int MidiPending();

// Power loss in the middle of flash work (see flash_write_budget).
void CutFlashPowerAfter(int32_t bytes);
void RestoreFlashPower();

}  // namespace test

#endif  // SIDEFX_TEST_HAL_FAKE_H_
