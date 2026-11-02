// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: what belongs to the module rather than to a preset, and the
// QSPI flash layout.
//
// Flash (offsets from the chip's start; the program lives from 0x40000):
//   0x00000-0x0FFFF  settings, a wear-levelled ring of 128-byte records
//   0x10000-0x1FFFF  the live state (the Preset being played), a ring of
//                    1 kB slots (a 512-byte Preset plus its record
//                    header): power up where you left off
//   0x20000-0x27FFF  the preset bank, 64 x 512 bytes
//   0x28000-0x28FFF  the bank's journal records (a ring of 32-byte records)
//   0x29000-0x29FFF  the bank's journal: the bank sector last saved, kept
//                    while its place in the bank is erased and rewritten
//   0x2A000-0x3FFFF  free

#ifndef SIDEFX_APP_SETTINGS_H_
#define SIDEFX_APP_SETTINGS_H_

#include <stddef.h>
#include <stdint.h>

#include "app/mod_sources.h"
#include "app/storage.h"

namespace sidefx {

const uint32_t kSettingsFlashOffset = 0x00000;
const uint32_t kSettingsFlashSectors = 16;
const uint32_t kStateFlashOffset = 0x10000;
const uint32_t kStateFlashSectors = 16;
const uint32_t kBankFlashOffset = 0x20000;
const uint32_t kBankJournalFlashOffset = 0x28000;
const uint32_t kBankJournalDataOffset = 0x29000;

const uint32_t kSettingsMagic = 0x31534653;  // "SFS1"
const uint16_t kSettingsVersion = 1;

const int kNumClockPpqn = 6;
extern const uint8_t kClockPpqnValues[kNumClockPpqn];  // 1, 2, 4, 8, 12, 24

struct Settings {
  uint32_t magic;
  uint16_t version;
  uint16_t reserved0;
  uint8_t last_preset;     // bank slot last loaded or saved
  uint8_t midi_channel;    // 0 = omni, 1..16
  uint8_t cc_a;            // controller numbers for the CC A / CC B sources (1, 11)
  uint8_t cc_b;
  uint8_t clock_ppqn;      // index into kClockPpqnValues (default 4 per quarter: 16ths)
  uint8_t brightness;      // backlight, 1..10
  uint8_t display_flip;    // 1: picture turned 180 degrees
  uint8_t encoder_steps;   // quadrature transitions per detent: 4 or 2
  uint8_t encoder_reverse; // 1: clockwise counts down
  uint8_t invert_output;   // 1: OUT 1 / OUT 2 polarity flipped
  uint8_t reserved1[2];
  uint16_t dry;            // global DRY, 0..65535
  int16_t input_gain;      // dB * 10, -120..+120
  int16_t output_gain;     // dB * 10, -120..+120
  uint16_t reserved2;
  CvCalibration calibration;
  uint32_t reserved3[6];
  uint32_t crc;
};

void InitSettings(Settings* settings);
void SanitizeSettings(Settings* settings);

// The settings ring, with coalesced saves: RequestSave() marks the
// settings dirty; Poll() writes them 5 s after the last request, and only
// if they differ from what flash holds.
class SettingsStore {
 public:
  SettingsStore() { }
  ~SettingsStore() { }

  void Init();
  bool Load(Settings* settings);  // false (and InitSettings) if none is valid
  void RequestSave(const Settings& settings, uint32_t now_ms);
  void Poll(uint32_t now_ms);
  void SaveNow(const Settings& settings);

 private:
  RecordStore store_;
  Settings pending_;
  Settings stored_;
  bool dirty_;
  uint32_t request_ms_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_SETTINGS_H_
