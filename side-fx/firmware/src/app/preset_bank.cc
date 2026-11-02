// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the preset bank and the live state in flash.

#include "app/preset_bank.h"

#include <string.h>

#include "app/factory_presets.h"
#include "app/settings.h"
#include "engine/crc32.h"
#include "hal.h"

namespace sidefx {

namespace {

const uint32_t kStateTag = 0x534c4653;  // "SFLS"
const uint32_t kStateSlotSize = 1024;   // 16-byte header + a 512-byte preset
const uint32_t kStateSaveDelayMs = 5000;
const uint32_t kJournalTag = 0x4a424653;  // "SFBJ"
const uint32_t kJournalSlotSize = 32;     // 16-byte header + the record
// Erase and write attempts for one sector before giving up.
const int kWriteAttempts = 2;

// What makes the journal's data count: the sector it belongs to and the
// data's CRC. Written after the data, so a cut-short journal never counts.
struct JournalRecord {
  uint32_t sector;
  uint32_t crc;
};

uint32_t PresetOffset(int index) {
  return kBankFlashOffset + uint32_t(index) * kPresetSize;
}

uint32_t SectorOffset(int sector) {
  return kBankFlashOffset + uint32_t(sector) * hal::kFlashSectorSize;
}

// The 4 kB at `offset` read back as these eight presets (one at a time
// into a scratch record, to keep the stack small).
bool FlashHolds(uint32_t offset, const Preset* presets, int count) {
  Preset check;
  for (int i = 0; i < count; ++i) {
    hal::FlashRead(offset + uint32_t(i) * kPresetSize, &check, kPresetSize);
    if (memcmp(&check, &presets[i], kPresetSize) != 0) {
      return false;
    }
  }
  return true;
}

// Erases the sector at `offset` and writes `count` presets to it; true once
// they read back.
bool WriteVerified(uint32_t offset, const Preset* presets, int count) {
  for (int attempt = 0; attempt < kWriteAttempts; ++attempt) {
    if (hal::FlashErase(offset, hal::kFlashSectorSize) &&
        hal::FlashWrite(offset, presets, uint32_t(count) * kPresetSize) &&
        FlashHolds(offset, presets, count)) {
      return true;
    }
  }
  return false;
}

}  // namespace

void PresetBank::Init() {
  state_store_.Init(kStateFlashOffset, kStateFlashSectors, kStateSlotSize,
                    kStateTag);
  state_dirty_ = false;
  state_request_ms_ = 0;
  last_state_crc_ = 0;
  InitPreset(&pending_state_);

  // A save cut short between the journal and the bank: finish it.
  journal_store_.Init(kBankJournalFlashOffset, 1, kJournalSlotSize,
                      kJournalTag);
  journal_sector_ = -1;
  bank_stale_ = false;
  JournalRecord record;
  if (journal_store_.Load(&record, sizeof(record)) &&
      record.sector < uint32_t(kNumSectors)) {
    hal::FlashRead(kBankJournalDataOffset, sector_, hal::kFlashSectorSize);
    if (Crc32(0, sector_, hal::kFlashSectorSize) == record.crc) {
      journal_sector_ = int(record.sector);
      const uint32_t place = SectorOffset(journal_sector_);
      if (!FlashHolds(place, sector_, kPresetsPerSector)) {
        bank_stale_ = !WriteVerified(place, sector_, kPresetsPerSector);
      }
    }
  }

  int valid = 0;
  for (int i = 0; i < kNumPresets; ++i) {
    Preset* p = &sector_[0];
    hal::FlashRead(ReadOffset(i), p, kPresetSize);
    if (PresetValid(*p)) {
      ++valid;
      UpdateName(i, *p);
    } else {
      CopyName(i, "INIT");
    }
  }
  if (valid == 0) {
    // The first power-up (or a bank nothing can be read from).
    RestoreFactory();
  }
}

uint32_t PresetBank::ReadOffset(int index) const {
  const int sector = index / kPresetsPerSector;
  if (bank_stale_ && sector == journal_sector_) {
    return kBankJournalDataOffset +
        uint32_t(index - sector * kPresetsPerSector) * kPresetSize;
  }
  return PresetOffset(index);
}

void PresetBank::CopyName(int index, const char* name) {
  size_t i = 0;
  for (; name[i] && i < kPresetNameLength; ++i) {
    names_[index][i] = name[i];
  }
  for (; i < sizeof(names_[index]); ++i) {
    names_[index][i] = '\0';
  }
}

void PresetBank::UpdateName(int index, const Preset& preset) {
  char name[kPresetNameLength + 1];
  memcpy(name, preset.name, kPresetNameLength);
  name[kPresetNameLength] = '\0';
  CopyName(index, name);
}

bool PresetBank::Load(int index, Preset* preset) {
  if (index < 0 || index >= kNumPresets) {
    InitPreset(preset);
    return false;
  }
  hal::FlashRead(ReadOffset(index), preset, kPresetSize);
  if (!PresetValid(*preset)) {
    InitPreset(preset);
    return false;
  }
  SanitizePreset(preset);
  return true;
}

bool PresetBank::RepairFromJournal() {
  if (!bank_stale_ || journal_sector_ < 0) {
    return true;
  }
  // Copied a preset at a time: sector_ may hold a save in progress.
  const uint32_t place = SectorOffset(journal_sector_);
  for (int attempt = 0; attempt < kWriteAttempts && bank_stale_; ++attempt) {
    if (!hal::FlashErase(place, hal::kFlashSectorSize)) {
      continue;
    }
    bool ok = true;
    Preset p;
    for (int i = 0; i < kPresetsPerSector && ok; ++i) {
      const uint32_t at = uint32_t(i) * kPresetSize;
      hal::FlashRead(kBankJournalDataOffset + at, &p, kPresetSize);
      ok = hal::FlashWrite(place + at, &p, kPresetSize) &&
          FlashHolds(place + at, &p, 1);
    }
    bank_stale_ = !ok;
  }
  return !bank_stale_;
}

bool PresetBank::WriteSector(int sector, const Preset* presets) {
  // The journal is about to take another sector: the one it holds must be
  // in its place first.
  if (!RepairFromJournal()) {
    return false;
  }
  // 1. The journal. Erasing its data voids the record that was there.
  journal_sector_ = -1;
  if (!WriteVerified(kBankJournalDataOffset, presets, kPresetsPerSector)) {
    return false;
  }
  JournalRecord record;
  record.sector = uint32_t(sector);
  record.crc = Crc32(0, presets, hal::kFlashSectorSize);
  if (!journal_store_.Save(&record, sizeof(record))) {
    return false;
  }
  journal_sector_ = sector;
  // 2. Its place in the bank. Should that fail, the sector is safe in the
  // journal anyway: it loads from there, and the next save or power-up
  // tries again.
  bank_stale_ = !WriteVerified(SectorOffset(sector), presets,
                               kPresetsPerSector);
  return true;
}

bool PresetBank::Save(int index, const Preset& preset) {
  if (index < 0 || index >= kNumPresets) {
    return false;
  }
  const int sector = index / kPresetsPerSector;
  const int first = sector * kPresetsPerSector;
  hal::FlashRead(ReadOffset(first), sector_, hal::kFlashSectorSize);
  Preset* p = &sector_[index - first];
  *p = preset;
  SealPreset(p);
  bool ok = WriteSector(sector, sector_);
  if (ok) {
    UpdateName(index, *p);
  }
  return ok;
}

void PresetBank::RestoreFactory() {
  const int num_factory = NumFactoryPresets();
  for (int sector = 0; sector < kNumSectors; ++sector) {
    for (int i = 0; i < kPresetsPerSector; ++i) {
      const int index = sector * kPresetsPerSector + i;
      Preset* p = &sector_[i];
      if (index < num_factory) {
        GetFactoryPreset(index, p);
      } else {
        InitPreset(p);
      }
      SealPreset(p);
    }
    if (WriteSector(sector, sector_)) {
      for (int i = 0; i < kPresetsPerSector; ++i) {
        UpdateName(sector * kPresetsPerSector + i, sector_[i]);
      }
    }
  }
}

bool PresetBank::LoadState(Preset* preset) {
  if (!state_store_.Load(preset, kPresetSize) || !PresetValid(*preset)) {
    InitPreset(preset);
    return false;
  }
  last_state_crc_ = preset->crc;
  SanitizePreset(preset);
  return true;
}

void PresetBank::RequestStateSave(const Preset& live, uint32_t now_ms) {
  pending_state_ = live;
  state_dirty_ = true;
  state_request_ms_ = now_ms;
}

void PresetBank::Poll(uint32_t now_ms) {
  if (!state_dirty_ || now_ms - state_request_ms_ < kStateSaveDelayMs) {
    return;
  }
  state_dirty_ = false;
  SealPreset(&pending_state_);
  if (pending_state_.crc == last_state_crc_) {
    return;  // what flash holds already
  }
  if (state_store_.Save(&pending_state_, kPresetSize)) {
    last_state_crc_ = pending_state_.crc;
  }
}

}  // namespace sidefx
