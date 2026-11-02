// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: RecordStore (wear levelling, power loss), the
// settings and their coalesced saves, the preset bank and the live state.

#include <string.h>

#include "check.h"
#include "hal_fake.h"
#include "test_support.h"

#include "app/factory_presets.h"
#include "app/preset_bank.h"
#include "app/settings.h"
#include "app/storage.h"
#include "engine/registry.h"

using namespace sidefx;

namespace {

// The name factory preset i gets (the bank's first slots hold them).
const char* FactoryName(int i) {
  static char names[16][16];
  Preset p;
  GetFactoryPreset(i, &p);
  strcpy(names[i & 15], p.name);
  return names[i & 15];
}

struct Record {
  uint32_t serial;
  uint8_t fill[200];
};

void MakeRecord(Record* r, uint32_t serial) {
  r->serial = serial;
  memset(r->fill, int(serial & 0xff), sizeof(r->fill));
}

const uint32_t kRegion = 0x30000;  // in the free part of the map

// The fake blocks, once, for InitPreset's defaults.
void Blocks() {
  static bool done = false;
  static test::TestMemory* memory = NULL;
  if (!done) {
    memory = new test::TestMemory(1u << 20, 200u << 10);
    InitBlocks(memory->memory());
    done = true;
  }
}

}  // namespace

TEST(app_storage, record_store_newest_wins) {
  test::ResetHal();
  RecordStore store;
  store.Init(kRegion, 4, 256, 0x12345678);
  Record r;
  CHECK(!store.Load(&r, sizeof(r)));
  for (uint32_t i = 1; i <= 100; ++i) {
    MakeRecord(&r, i);
    CHECK(store.Save(&r, sizeof(r)));
  }
  RecordStore again;
  again.Init(kRegion, 4, 256, 0x12345678);
  Record loaded;
  CHECK(again.Load(&loaded, sizeof(loaded)));
  CHECK(loaded.serial == 100 && loaded.fill[7] == 100);
  // Another size or tag is not this record.
  CHECK(!again.Load(&loaded, sizeof(loaded) - 4));
  RecordStore other;
  other.Init(kRegion, 4, 256, 0x87654321);
  CHECK(!other.Load(&loaded, sizeof(loaded)));
  // Saving goes on from the newest.
  MakeRecord(&r, 101);
  CHECK(again.Save(&r, sizeof(r)));
  again.Init(kRegion, 4, 256, 0x12345678);
  CHECK(again.Load(&loaded, sizeof(loaded)) && loaded.serial == 101);
}

TEST(app_storage, record_store_wear_levelling) {
  test::ResetHal();
  RecordStore store;
  // The live state's ring: 16 sectors of 1 kB slots, 64 slots.
  store.Init(0x10000, 16, 1024, 0xabcdef01);
  uint8_t payload[512];
  CHECK(!store.Load(payload, sizeof(payload)));
  for (uint32_t i = 0; i < 640; ++i) {
    memset(payload, int(i), sizeof(payload));
    CHECK(store.Save(payload, sizeof(payload)));
  }
  uint32_t lo = 1000000, hi = 0;
  for (uint32_t s = 16; s < 32; ++s) {
    uint32_t n = test::Hal().sector_erases[s];
    lo = n < lo ? n : lo;
    hi = n > hi ? n : hi;
  }
  test::Note("640 saves: %u..%u erases per sector", unsigned(lo), unsigned(hi));
  CHECK(lo == 10 && hi == 10);  // 640 saves / 64 slots, every sector alike
  // Nothing outside the region.
  CHECK(test::Hal().sector_erases[15] == 0 && test::Hal().sector_erases[32] == 0);
  CHECK(store.Load(payload, sizeof(payload)) && payload[0] == uint8_t(639));
}

TEST(app_storage, record_store_power_loss_falls_back) {
  test::ResetHal();
  RecordStore store;
  store.Init(kRegion, 2, 512, 0x55aa55aa);
  Record r;
  CHECK(!store.Load(&r, sizeof(r)));
  for (uint32_t i = 1; i <= 5; ++i) {
    MakeRecord(&r, i);
    CHECK(store.Save(&r, sizeof(r)));
  }
  // Power fails 100 bytes into the next write.
  test::CutFlashPowerAfter(100);
  MakeRecord(&r, 6);
  CHECK(!store.Save(&r, sizeof(r)));
  test::RestoreFlashPower();
  RecordStore after;
  after.Init(kRegion, 2, 512, 0x55aa55aa);
  Record loaded;
  CHECK(after.Load(&loaded, sizeof(loaded)) && loaded.serial == 5);
  // The torn slot is skipped, and the next save lands and wins.
  MakeRecord(&r, 7);
  CHECK(after.Save(&r, sizeof(r)));
  after.Init(kRegion, 2, 512, 0x55aa55aa);
  CHECK(after.Load(&loaded, sizeof(loaded)) && loaded.serial == 7);

  // Go round to the next sector boundary and cut its erase short.
  test::ResetHal();
  store.Init(kRegion, 2, 512, 0x55aa55aa);
  store.Load(&r, sizeof(r));
  for (uint32_t i = 1; i <= 16; ++i) {  // fills both sectors (16 slots)
    MakeRecord(&r, i);
    CHECK(store.Save(&r, sizeof(r)));
  }
  test::Hal().interrupt_next_erase = true;
  MakeRecord(&r, 17);
  CHECK(!store.Save(&r, sizeof(r)));
  after.Init(kRegion, 2, 512, 0x55aa55aa);
  CHECK(after.Load(&loaded, sizeof(loaded)) && loaded.serial == 16);
  MakeRecord(&r, 18);
  CHECK(after.Save(&r, sizeof(r)));
  after.Init(kRegion, 2, 512, 0x55aa55aa);
  CHECK(after.Load(&loaded, sizeof(loaded)) && loaded.serial == 18);
  // And the ring goes on through the half-erased sector.
  for (uint32_t i = 19; i <= 40; ++i) {
    MakeRecord(&r, i);
    CHECK(after.Save(&r, sizeof(r)));
  }
  after.Init(kRegion, 2, 512, 0x55aa55aa);
  CHECK(after.Load(&loaded, sizeof(loaded)) && loaded.serial == 40);
}

TEST(app_storage, settings_defaults_and_sanitize) {
  Settings s;
  InitSettings(&s);
  CHECK(s.magic == kSettingsMagic && s.version == kSettingsVersion);
  CHECK(s.dry == 65535 && s.input_gain == 0 && s.output_gain == 0);
  CHECK(s.midi_channel == 0 && s.cc_a == 1 && s.cc_b == 11);
  CHECK(s.clock_ppqn == 2 && kClockPpqnValues[s.clock_ppqn] == 4);
  CHECK(s.brightness == 8 && s.display_flip == 0 && s.encoder_steps == 4);
  CHECK(s.encoder_reverse == 0 && s.invert_output == 0 && s.last_preset == 0);
  CHECK(s.calibration.offset[2] == 0.5079f && s.calibration.scale[3] == -12.22f);
  CHECK(sizeof(Settings) + 16 <= 128);

  s.midi_channel = 40;
  s.clock_ppqn = 9;
  s.brightness = 0;
  s.encoder_steps = 3;
  s.input_gain = 500;
  s.output_gain = -500;
  s.last_preset = 200;
  s.calibration.scale[1] = 5.0f;
  s.calibration.offset[2] = 0.0f / 0.0f;
  s.calibration.offset[0] = 0.49f;
  SanitizeSettings(&s);
  CHECK(s.midi_channel == 16 && s.clock_ppqn == 5 && s.brightness == 1);
  CHECK(s.encoder_steps == 4 && s.input_gain == 120 && s.output_gain == -120);
  CHECK(s.last_preset == 63);
  CHECK(s.calibration.scale[1] == -12.22f && s.calibration.offset[2] == 0.5079f);
  CHECK(s.calibration.offset[0] == 0.49f);  // a plausible calibration stays
}

TEST(app_storage, settings_coalesced_saves) {
  test::ResetHal();
  SettingsStore store;
  store.Init();
  Settings s;
  CHECK(!store.Load(&s));
  CHECK(s.cc_b == 11);
  const int writes0 = test::Hal().flash_writes;

  // Five quick edits: one write, 5 s after the last.
  for (int i = 0; i < 5; ++i) {
    s.brightness = uint8_t(2 + i);
    store.RequestSave(s, 1000u * uint32_t(i));
    store.Poll(1000u * uint32_t(i));
  }
  store.Poll(8999);
  CHECK(test::Hal().flash_writes == writes0);
  store.Poll(9000);
  CHECK(test::Hal().flash_writes == writes0 + 1);
  store.Poll(20000);
  CHECK(test::Hal().flash_writes == writes0 + 1);

  // A request that changes nothing writes nothing.
  store.RequestSave(s, 30000);
  store.Poll(40000);
  CHECK(test::Hal().flash_writes == writes0 + 1);

  // The first save of untouched defaults does write (nothing was stored).
  test::ResetHal();
  store.Init();
  store.Load(&s);
  store.RequestSave(s, 0);
  store.Poll(5000);
  CHECK(test::Hal().flash_writes == 1);

  // Back after a power cycle.
  s.midi_channel = 5;
  s.invert_output = 1;
  store.SaveNow(s);
  test::PowerCycleHal();
  SettingsStore again;
  again.Init();
  Settings loaded;
  CHECK(again.Load(&loaded));
  CHECK(loaded.midi_channel == 5 && loaded.invert_output == 1);
  CHECK(loaded.brightness == 8);
}

TEST(app_storage, bank_first_boot_and_names) {
  Blocks();
  test::ResetHal();
  PresetBank bank;
  bank.Init();
  // The whole bank, sector by sector, each through the journal.
  for (int s = 0; s < 8; ++s) {
    CHECK(test::Hal().sector_erases[(kBankFlashOffset >> 12) + s] == 1);
  }
  CHECK(test::Hal().sector_erases[kBankJournalDataOffset >> 12] == 8);
  CHECK(test::Hal().sector_erases[kBankJournalFlashOffset >> 12] == 1);
  CHECK(!strcmp(bank.name(0), FactoryName(0)));
  for (int i = NumFactoryPresets(); i < kNumPresets; ++i) {
    CHECK(!strcmp(bank.name(i), "INIT"));
  }
  Preset p;
  CHECK(bank.Load(0, &p));
  CHECK(p.slot[SLOT_DELAY].send == 1 && p.slot[SLOT_REVERB].send == 1);
  CHECK(p.slot[SLOT_PITCH].send == 0 && p.slot[SLOT_TEXTURE].send == 0);
  CHECK(bank.Load(63, &p) && !strcmp(p.name, "INIT"));

  // The next power-up finds the bank and writes nothing.
  test::PowerCycleHal();
  PresetBank again;
  again.Init();
  CHECK(test::Hal().flash_erases == 0 && test::Hal().flash_writes == 0);
  CHECK(!strcmp(again.name(0), FactoryName(0)));
}

TEST(app_storage, bank_save_load_one_sector) {
  Blocks();
  test::ResetHal();
  PresetBank bank;
  bank.Init();
  Preset p;
  InitPreset(&p);
  SetPresetName(&p, "DUB SIREN");
  p.wet = 12345;
  p.tempo = 1240;
  test::PowerCycleHal();
  CHECK(bank.Save(10, p));
  CHECK(test::Hal().flash_erases == 2);  // the journal, then the sector
  CHECK(test::Hal().sector_erases[(kBankFlashOffset >> 12) + 1] == 1);
  CHECK(test::Hal().sector_erases[kBankJournalDataOffset >> 12] == 1);
  CHECK(!strcmp(bank.name(10), "DUB SIREN"));
  Preset q;
  CHECK(bank.Load(10, &q));
  CHECK(q.wet == 12345 && q.tempo == 1240 && !strcmp(q.name, "DUB SIREN"));
  // Its sector neighbours survive the rewrite.
  CHECK(bank.Load(9, &q) && !strcmp(q.name, FactoryName(9)));
  CHECK(bank.Load(15, &q) && !strcmp(q.name, FactoryName(15)));
  CHECK(bank.Load(0, &q) && !strcmp(q.name, FactoryName(0)));

  // A corrupt slot loads as INIT and says so.
  uint8_t* raw = test::Hal().flash + kBankFlashOffset + 20 * kPresetSize + 40;
  *raw = uint8_t(*raw & 0x0f);
  CHECK(!bank.Load(20, &q));
  CHECK(PresetValid(q) || !strcmp(q.name, "INIT"));
  test::PowerCycleHal();
  PresetBank again;
  again.Init();
  CHECK(!strcmp(again.name(20), "INIT"));
  CHECK(!strcmp(again.name(10), "DUB SIREN"));

  // A flash failure is reported.
  test::CutFlashPowerAfter(0);
  CHECK(!again.Save(11, p));
  test::RestoreFlashPower();
  CHECK(!again.Save(64, p) && !again.Save(-1, p));

  // RESTORE FACTORY.
  again.RestoreFactory();
  CHECK(!strcmp(again.name(10), FactoryName(10)));
  CHECK(!strcmp(again.name(0), FactoryName(0)));
}

TEST(app_storage, live_state_coalesced_and_after_power_cycle) {
  Blocks();
  test::ResetHal();
  PresetBank bank;
  bank.Init();
  Preset p;
  CHECK(!bank.LoadState(&p));
  test::PowerCycleHal();
  InitPreset(&p);
  p.wet = 40000;
  for (int i = 0; i < 10; ++i) {
    p.slot[SLOT_DELAY].value[0] = uint16_t(1000 * i);
    bank.RequestStateSave(p, 300u * uint32_t(i));
    bank.Poll(300u * uint32_t(i));
  }
  CHECK(test::Hal().flash_writes == 0);
  bank.Poll(2700 + 4999);
  CHECK(test::Hal().flash_writes == 0);
  bank.Poll(2700 + 5000);
  CHECK(test::Hal().flash_writes == 1);
  // Unchanged: skipped.
  bank.RequestStateSave(p, 10000);
  bank.Poll(16000);
  CHECK(test::Hal().flash_writes == 1);

  test::PowerCycleHal();
  PresetBank again;
  again.Init();
  Preset q;
  CHECK(again.LoadState(&q));
  CHECK(q.wet == 40000 && q.slot[SLOT_DELAY].value[0] == 9000);
  // Unchanged since the load: still skipped.
  again.RequestStateSave(q, 0);
  again.Poll(6000);
  CHECK(test::Hal().flash_writes == 0);
  q.wet = 1;
  again.RequestStateSave(q, 7000);
  again.Poll(12000);
  CHECK(test::Hal().flash_writes == 1);
}

TEST(app_storage, record_store_checks_what_reached_the_flash) {
  // libDaisy's QSPIHandle::Write says OK whatever its page programs did.
  // A save reads its slot back and moves on when the flash did not take
  // it, instead of reporting a record that is not there.
  test::ResetHal();
  RecordStore store;
  store.Init(kRegion, 2, 1024, 0x0badf1a5);
  Record r;
  MakeRecord(&r, 1);
  CHECK(store.Save(&r, sizeof(r)));
  test::Hal().bad_sector = int32_t(kRegion >> 12);  // slots 1..3 too
  MakeRecord(&r, 2);
  CHECK(store.Save(&r, sizeof(r)));  // in slot 4, the next sector
  test::Hal().bad_sector = -1;
  RecordStore again;
  again.Init(kRegion, 2, 1024, 0x0badf1a5);
  Record loaded;
  CHECK(again.Load(&loaded, sizeof(loaded)) && loaded.serial == 2);
  // Nowhere to put it: the save says so.
  test::Hal().bad_sector = int32_t(kRegion >> 12);
  RecordStore one;
  one.Init(kRegion, 1, 1024, 0x0badf1a5);
  one.Load(&loaded, sizeof(loaded));
  MakeRecord(&r, 3);
  CHECK(!one.Save(&r, sizeof(r)));
  test::Hal().bad_sector = -1;
}

namespace {

// Names of presets 8..15 (bank sector 1) as a fresh bank loads them; "-"
// for one that does not load.
void SectorNames(char names[8][16]) {
  test::PowerCycleHal();
  PresetBank bank;
  bank.Init();
  for (int i = 0; i < 8; ++i) {
    Preset q;
    if (bank.Load(8 + i, &q)) {
      memcpy(names[i], q.name, kPresetNameLength);
      names[i][kPresetNameLength] = '\0';
    } else {
      strcpy(names[i], "-");
    }
    CHECK(!strcmp(bank.name(8 + i), names[i]) ||
          (!strcmp(names[i], "-") && !strcmp(bank.name(8 + i), "INIT")));
  }
}

}  // namespace

TEST(app_storage, bank_save_cut_short_keeps_its_neighbours) {
  // Power lost anywhere in a save (rack switched off, a brown-out) loses
  // at most that save: the other seven presets of the sector survive.
  Blocks();
  test::ResetHal();
  {
    PresetBank bank;
    bank.Init();
    Preset p;
    InitPreset(&p);
    SetPresetName(&p, "WOBBLE BASS");
    CHECK(bank.Save(9, p));
  }
  char before[8][16];
  SectorNames(before);
  CHECK(!strcmp(before[1], "WOBBLE BASS"));
  static uint8_t snapshot[test::kFakeFlashSize];
  memcpy(snapshot, test::Hal().flash, sizeof(snapshot));

  Preset mine;
  InitPreset(&mine);
  SetPresetName(&mine, "NEW ONE");
  int saved = 0;
  int kept = 0;
  int cuts = 0;
  // Every write cut point through the journal (4 kB), its record and the
  // sector's own rewrite (4 kB).
  for (int32_t budget = 0; budget < 8400; budget += 61) {
    memcpy(test::Hal().flash, snapshot, sizeof(snapshot));
    test::PowerCycleHal();
    PresetBank bank;
    bank.Init();
    test::CutFlashPowerAfter(budget);
    test::Hal().erases_before_cut = 4;
    const bool ok = bank.Save(11, mine);
    test::RestoreFlashPower();
    ++cuts;
    char after[8][16];
    SectorNames(after);
    for (int i = 0; i < 8; ++i) {
      if (i == 3) {
        CHECK(!strcmp(after[i], before[i]) || !strcmp(after[i], "NEW ONE"));
        saved += !strcmp(after[i], "NEW ONE");
        kept += !strcmp(after[i], before[i]);
        // A save that says it worked did.
        CHECK(!ok || !strcmp(after[i], "NEW ONE"));
      } else {
        CHECK(!strcmp(after[i], before[i]));
      }
    }
  }
  test::Note("%d cut points: %d kept the old preset, %d the new one", cuts,
             kept, saved);
  CHECK(saved > 0 && kept > 0);

  // An erase of the sector itself cut halfway, the journal complete.
  memcpy(test::Hal().flash, snapshot, sizeof(snapshot));
  test::PowerCycleHal();
  {
    PresetBank bank;
    bank.Init();
    CHECK(bank.Save(11, mine));
  }
  memset(test::Hal().flash + kBankFlashOffset + 4096, 0xff, 2048);
  char after[8][16];
  SectorNames(after);
  for (int i = 0; i < 8; ++i) {
    CHECK(!strcmp(after[i], i == 3 ? "NEW ONE" : before[i]));
  }
  // ... and the power-up put it back in place.
  Preset q;
  memcpy(&q, test::Hal().flash + kBankFlashOffset + 4096 + kPresetSize,
         kPresetSize);
  CHECK(PresetValid(q) && !strcmp(q.name, "WOBBLE BASS"));

  // An erase cut halfway, as the review found it (interrupt_next_erase):
  // the retry gets the save through, and nothing else is touched.
  memcpy(test::Hal().flash, snapshot, sizeof(snapshot));
  test::PowerCycleHal();
  PresetBank bank;
  bank.Init();
  test::Hal().interrupt_next_erase = true;
  CHECK(bank.Save(11, mine));
  for (int i = 0; i < 8; ++i) {
    Preset r;
    CHECK(bank.Load(8 + i, &r));
    CHECK(!strcmp(r.name, i == 3 ? "NEW ONE" : before[i]));
    CHECK(!strcmp(bank.name(8 + i), r.name));
  }
  // A journal that will not take the save: it fails, and nothing is lost
  // (the names still say what loads).
  memcpy(test::Hal().flash, snapshot, sizeof(snapshot));
  test::PowerCycleHal();
  PresetBank failing;
  failing.Init();
  test::Hal().bad_sector = int32_t(kBankJournalDataOffset >> 12);
  CHECK(!failing.Save(11, mine));
  test::Hal().bad_sector = -1;
  for (int i = 0; i < 8; ++i) {
    Preset r;
    CHECK(failing.Load(8 + i, &r) && !strcmp(r.name, before[i]));
    CHECK(!strcmp(failing.name(8 + i), before[i]));
  }
}

TEST(app_storage, bank_sector_that_will_not_write_loads_from_the_journal) {
  Blocks();
  test::ResetHal();
  PresetBank bank;
  bank.Init();
  char before[8][16];
  for (int i = 0; i < 8; ++i) {
    strcpy(before[i], bank.name(8 + i));
  }
  // Sector 1 of the bank takes no writes (and says nothing).
  test::Hal().bad_sector = int32_t(kBankFlashOffset >> 12) + 1;
  Preset mine;
  InitPreset(&mine);
  SetPresetName(&mine, "KEPT ANYWAY");
  CHECK(bank.Save(12, mine));
  for (int i = 0; i < 8; ++i) {
    Preset q;
    CHECK(bank.Load(8 + i, &q));
    CHECK(!strcmp(q.name, i == 4 ? "KEPT ANYWAY" : before[i]));
  }
  // Another sector's save must not reuse the journal while it is needed.
  Preset other;
  InitPreset(&other);
  SetPresetName(&other, "ELSEWHERE");
  CHECK(!bank.Save(30, other));
  CHECK(strcmp(bank.name(30), "ELSEWHERE"));
  // The flash recovers: that save puts sector 1 in place first.
  test::Hal().bad_sector = -1;
  CHECK(bank.Save(30, other));
  char after[8][16];
  SectorNames(after);
  for (int i = 0; i < 8; ++i) {
    CHECK(!strcmp(after[i], i == 4 ? "KEPT ANYWAY" : before[i]));
  }
  Preset q;
  memcpy(&q, test::Hal().flash + kBankFlashOffset + 4096 + 4 * kPresetSize,
         kPresetSize);
  CHECK(PresetValid(q) && !strcmp(q.name, "KEPT ANYWAY"));
  PresetBank again;
  again.Init();
  CHECK(again.Load(30, &q) && !strcmp(q.name, "ELSEWHERE"));
}
