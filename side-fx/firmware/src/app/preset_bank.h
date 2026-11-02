// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the 64 user presets in flash, and the live state.
//
// The bank is 64 fixed 512-byte records from kBankFlashOffset, eight to a
// 4 kB sector: saving one rewrites its sector. So that a power cut or a
// flash error halfway never takes the other seven with it, the new sector
// goes to a journal first (kBankJournalDataOffset, made valid by a record
// naming the sector and the data's CRC once it reads back), and only then
// is the sector erased and rewritten in place. Init() finishes a rewrite
// that was cut short from the journal; while a sector's place does not
// match its journal, its presets load from the journal, and the next save
// puts it in place first. Two sector erases per save: up to ~0.8 s in the
// main loop (the audio keeps running). On the first power-up (no valid
// record anywhere) the factory presets go into slots 1..N and INIT presets
// fill the rest. Names are cached in RAM for browsing.
//
// The live state is the Preset being played, edits included: it goes into
// its own wear-levelled ring 5 s after the last change, so the module
// powers up exactly where it was.

#ifndef SIDEFX_APP_PRESET_BANK_H_
#define SIDEFX_APP_PRESET_BANK_H_

#include <stddef.h>
#include <stdint.h>

#include "app/storage.h"
#include "engine/preset.h"

namespace sidefx {

const int kNumPresets = 64;

class PresetBank {
 public:
  PresetBank() { }
  ~PresetBank() { }

  void Init();

  // False, with *preset = InitPreset, when the slot holds no valid preset.
  bool Load(int index, Preset* preset);
  // Seals a copy and writes it. False on a flash error.
  bool Save(int index, const Preset& preset);
  const char* name(int index) const { return names_[index]; }
  void RestoreFactory();

  bool LoadState(Preset* preset);
  void RequestStateSave(const Preset& live, uint32_t now_ms);
  void Poll(uint32_t now_ms);

 private:
  static const int kPresetsPerSector = 8;
  static const int kNumSectors = kNumPresets / kPresetsPerSector;

  // Writes a bank sector's eight presets through the journal (see above).
  // False, with the bank as it was, when the journal could not be written
  // (or an earlier sector could not be put in place from it).
  bool WriteSector(int sector, const Preset* presets);
  // Puts the journal's sector in place in the bank; true when it is.
  bool RepairFromJournal();
  // Where preset `index` is read from: its place, or the journal.
  uint32_t ReadOffset(int index) const;
  void UpdateName(int index, const Preset& preset);
  void CopyName(int index, const char* name);

  char names_[kNumPresets][16];
  // One sector's presets for a save's read-modify-write (4 kB, kept off
  // the main loop's stack).
  Preset sector_[kPresetsPerSector];
  RecordStore journal_store_;
  int journal_sector_;  // the bank sector the journal holds; -1: none
  bool bank_stale_;     // ... and its place in the bank may not match it
  RecordStore state_store_;
  Preset pending_state_;
  bool state_dirty_;
  uint32_t state_request_ms_;
  uint32_t last_state_crc_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_PRESET_BANK_H_
