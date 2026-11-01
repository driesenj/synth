// Plaitsy host tests, groups 6 and 7: the QSPI record store (settings) and
// the user data block.

#include "port_test.h"

namespace test {

using namespace plaits;
using plaitsy::RecordStore;

namespace {

// The store as Settings uses it (settings.cc).
const uint32_t kOffset = 0x00000;
const uint32_t kSectors = 16;
const uint32_t kSlotSize = 256;
const uint32_t kTag = 0x31594c50;
const uint32_t kSlots = kSectors * fake::kSectorSize / kSlotSize;
const uint32_t kSlotsPerSector = fake::kSectorSize / kSlotSize;

// Same size as Settings' record (PersistentData + State).
struct TestRecord {
  uint32_t n;
  uint8_t bytes[sizeof(PersistentData) + sizeof(State) - 4];
};

TestRecord MakeRecord(uint32_t n) {
  TestRecord r;
  r.n = n;
  for (size_t i = 0; i < sizeof(r.bytes); ++i) {
    r.bytes[i] = static_cast<uint8_t>((n * 131u + i * 7u) % 251u);  // never 0xff
  }
  return r;
}

bool Same(const TestRecord& a, const TestRecord& b) {
  return memcmp(&a, &b, sizeof(a)) == 0;
}

// A boot: a new store, Init(), Load().
bool Boot(RecordStore* store, TestRecord* r) {
  store->Init(kOffset, kSectors, kSlotSize, kTag);
  return store->Load(r, sizeof(*r));
}

// Loads with a store of its own; -1 when nothing valid.
long Newest() {
  RecordStore store;
  TestRecord r;
  if (!Boot(&store, &r)) {
    return -1;
  }
  return Same(r, MakeRecord(r.n)) ? static_cast<long>(r.n) : -2;
}

// The bytes a complete save of record n with sequence `seq` puts in a slot.
void SlotImage(uint32_t n, uint32_t seq, uint8_t* image) {
  const TestRecord r = MakeRecord(n);
  uint32_t header[4];
  header[0] = kTag;
  header[1] = seq;
  header[2] = sizeof(r);
  uint32_t crc = plaitsy::Crc32(0, &header[1], 4);
  crc = plaitsy::Crc32(crc, &header[2], 4);
  header[3] = plaitsy::Crc32(crc, &r, sizeof(r));
  memcpy(image, header, 16);
  memcpy(image + 16, &r, sizeof(r));
}

uint32_t SlotSequence(uint32_t slot) {
  uint32_t header[4];
  memcpy(header, fake::flash() + kOffset + slot * kSlotSize, 16);
  return header[0] == kTag ? header[1] : 0;
}

std::string ViolationText() {
  const fake::FlashStats& s = fake::flash_stats();
  return s.violations ? s.violation_log[0] : std::string("none");
}

// Power loss during one save: `saves_before` records are written (with a
// reboot every `reboot_every`), then the next save is interrupted after
// `ops` flash operations. Then a reboot must load the newest complete
// record, and saving must carry on.
struct PowerLossOutcome {
  bool save_failed;
  long loaded;
  long expected;
  bool resumed;  // later saves and loads right
  int violations;
};

PowerLossOutcome PowerLossRun(uint32_t saves_before, long ops,
                              fake::EraseInterruption style, uint64_t seed,
                              uint32_t later_saves) {
  PowerLossOutcome o;
  FreshFlash();
  RecordStore store;
  TestRecord r;
  Boot(&store, &r);
  for (uint32_t n = 1; n <= saves_before; ++n) {
    TestRecord rec = MakeRecord(n);
    store.Save(&rec, sizeof(rec));
    if (n % 37 == 0) {
      Boot(&store, &r);
    }
  }
  const uint32_t next = saves_before + 1;
  // Where the save will go, to judge whether it completed anyway.
  const uint32_t slot = store.next_slot_;
  const uint32_t seq = store.sequence_;
  fake::ArmPowerLoss(ops, style, seed);
  TestRecord rec = MakeRecord(next);
  const bool saved = store.Save(&rec, sizeof(rec));
  fake::DisarmPowerLoss();
  o.save_failed = !saved;
  fake::PowerOn();
  uint8_t image[16 + sizeof(TestRecord)];
  SlotImage(next, seq, image);
  const bool complete = memcmp(fake::flash() + kOffset + slot * kSlotSize,
                               image, sizeof(image)) == 0;
  o.expected = saved || complete ? next : static_cast<long>(saves_before);
  if (o.expected == 0) {
    o.expected = -1;
  }
  o.loaded = Newest();
  // Carry on, with a reboot after each few saves.
  o.resumed = true;
  RecordStore after;
  Boot(&after, &r);
  for (uint32_t k = 1; k <= later_saves; ++k) {
    TestRecord more = MakeRecord(next + k);
    if (!after.Save(&more, sizeof(more))) {
      o.resumed = false;
      break;
    }
    if (Newest() != static_cast<long>(next + k)) {
      o.resumed = false;
      break;
    }
    if (k % 5 == 0) {
      Boot(&after, &r);
    }
  }
  o.violations = fake::flash_stats().violations;
  return o;
}

}  // namespace

// ====================================================================== 6
void TestStorage() {
  Section("6. Settings storage: the QSPI record ring");

  // Round trip.
  {
    FreshFlash();
    RecordStore store;
    TestRecord r;
    const bool found_on_blank = Boot(&store, &r);
    TestRecord rec = MakeRecord(42);
    const bool saved = store.Save(&rec, sizeof(rec));
    Check("storage: blank flash loads nothing; a save loads back",
          !found_on_blank && saved && Newest() == 42,
          "blank %d, saved %d, loaded %ld", found_on_blank, saved, Newest());
    TestRecord small;
    RecordStore other;
    other.Init(kOffset, kSectors, kSlotSize, kTag);
    Check("storage: a record of another size is not loaded",
          !other.Load(&small, sizeof(small) - 4), "size %zu",
          sizeof(small) - 4);
    uint8_t big[kSlotSize];
    memset(big, 0, sizeof(big));
    Check("storage: a record too big for a slot is refused",
          !store.Save(big, kSlotSize - 15), "%u bytes into %u-byte slots",
          kSlotSize - 15, kSlotSize);
  }

  // 300+ saves around the ring, with reboots in between.
  {
    FreshFlash();
    RecordStore store;
    TestRecord r;
    Boot(&store, &r);
    const uint32_t kSaves = 700;
    int wrong_erases = 0, wrong_loads = 0, wrong_slots = 0;
    for (uint32_t n = 1; n <= kSaves; ++n) {
      const int erases_before = fake::flash_stats().erase_calls;
      TestRecord rec = MakeRecord(n);
      if (!store.Save(&rec, sizeof(rec))) {
        ++wrong_loads;
      }
      const uint32_t slot = (n - 1) % kSlots;
      const int erased = fake::flash_stats().erase_calls - erases_before;
      if (erased != (slot % kSlotsPerSector == 0 ? 1 : 0)) {
        ++wrong_erases;
      }
      if (SlotSequence(slot) != n) {
        ++wrong_slots;
      }
      if (Newest() != static_cast<long>(n)) {
        ++wrong_loads;
      }
      if (n % 9 == 0) {
        Boot(&store, &r);  // power cycle
      }
    }
    std::string per_sector;
    bool counts_ok = true;
    for (uint32_t s = 0; s < fake::kNumSectors; ++s) {
      // Times the ring entered sector s in kSaves saves.
      int want = 0;
      for (uint32_t n = 1; n <= kSaves; ++n) {
        if ((n - 1) % kSlots == s * kSlotsPerSector && s < kSectors) {
          ++want;
        }
      }
      counts_ok = counts_ok && fake::flash_stats().erases[s] == want;
      if (s < kSectors) {
        per_sector += (s ? " " : "") + std::to_string(fake::flash_stats().erases[s]);
      }
    }
    Check("storage: 700 saves (2.7 laps), reboot every 9: every save loads "
          "back, in the expected slot",
          wrong_loads == 0 && wrong_slots == 0, "%d wrong loads, %d records "
          "not in the next slot", wrong_loads, wrong_slots);
    Check("storage: a sector is erased exactly when the ring enters it",
          wrong_erases == 0 && counts_ok,
          "%d saves with a wrong erase count; erases per sector: %s; "
          "nothing outside the 64 kB region", wrong_erases, per_sector.c_str());
    Check("storage: no programming over unerased cells, nothing outside "
          "the flash region", fake::flash_stats().violations == 0, "%s",
          ViolationText().c_str());
    Observe("storage: 256 saves per lap, one 4 kB erase per 16 saves: each "
            "sector is erased once per 256 saves (700 saves: %s)",
            per_sector.c_str());
  }

  // Power loss in the middle of an erase.
  {
    int bad = 0, cases = 0;
    std::string first_bad;
    const uint32_t entering[] = { 0, 16, 32, 240, 256, 272, 511 + 1 };
    for (uint32_t before : entering) {
      for (int style = 0; style < 2; ++style) {
        for (uint64_t seed = 1; seed <= 6; ++seed) {
          const PowerLossOutcome o = PowerLossRun(
              before, 0, fake::EraseInterruption(style), seed * 7919, 40);
          ++cases;
          if (!o.save_failed || o.loaded != o.expected || !o.resumed ||
              o.violations) {
            if (!bad) {
              char text[200];
              snprintf(text, sizeof(text), "after %u saves (%s, seed %llu): "
                       "save failed %d, loaded %ld, expected %ld, resumed %d, "
                       "violations %d (%s)", before,
                       style ? "garbage" : "partly erased",
                       static_cast<unsigned long long>(seed), o.save_failed,
                       o.loaded, o.expected, o.resumed, o.violations,
                       ViolationText().c_str());
              first_bad = text;
            }
            ++bad;
          }
        }
      }
    }
    Check("storage: power lost during a sector erase -> the previous record "
          "loads, saving carries on",
          bad == 0, "%d of %d cases wrong%s%s", bad, cases,
          bad ? "; first: " : "", first_bad.c_str());
  }

  // Power loss in the middle of a slot write, at every byte.
  {
    int bad = 0, cases = 0;
    std::string first_bad;
    const uint32_t positions[] = { 5, 15, 16, 255, 256 };
    for (uint32_t before : positions) {
      // A save at a sector start erases first: one more operation.
      const bool erases = before % kSlotsPerSector == 0;
      const long total = (erases ? 1 : 0) + 16 + sizeof(TestRecord);
      for (long ops = 0; ops <= total; ++ops) {
        const PowerLossOutcome o = PowerLossRun(
            before, ops, fake::ERASE_PREFIX, 1234 + ops, 20);
        ++cases;
        const bool should_fail = ops < total;
        if (o.save_failed != should_fail || o.loaded != o.expected ||
            !o.resumed || o.violations) {
          if (!bad) {
            char text[200];
            snprintf(text, sizeof(text), "after %u saves, cut after %ld of "
                     "%ld ops: save failed %d, loaded %ld, expected %ld, "
                     "resumed %d, violations %d (%s)", before, ops, total,
                     o.save_failed, o.loaded, o.expected, o.resumed,
                     o.violations, ViolationText().c_str());
            first_bad = text;
          }
          ++bad;
        }
      }
    }
    Check("storage: power lost at every byte of a slot write -> the last "
          "complete record loads, saving carries on",
          bad == 0, "%d of %d cases wrong%s%s", bad, cases,
          bad ? "; first: " : "", first_bad.c_str());
  }

  // Random power cuts.
  {
    uint64_t state = 0x2545f4914f6cdd1dull;
    auto next = [&state]() {
      state ^= state << 13;
      state ^= state >> 7;
      state ^= state << 17;
      return state;
    };
    int bad = 0;
    std::string first_bad;
    const int kRuns = 150;
    for (int i = 0; i < kRuns; ++i) {
      const uint32_t before = next() % 600;
      const long ops = next() % 160;
      const fake::EraseInterruption style = fake::EraseInterruption(next() % 2);
      const PowerLossOutcome o = PowerLossRun(before, ops, style, next(), 12);
      if (o.loaded != o.expected || !o.resumed || o.violations) {
        if (!bad) {
          char text[160];
          snprintf(text, sizeof(text), "after %u saves, %ld ops: loaded %ld, "
                   "expected %ld, resumed %d, violations %d", before, ops,
                   o.loaded, o.expected, o.resumed, o.violations);
          first_bad = text;
        }
        ++bad;
      }
    }
    Check("storage: 150 random power cuts", bad == 0, "%d wrong%s%s", bad,
          bad ? "; first: " : "", first_bad.c_str());
  }

  // Two cuts in a row on the same slot.
  {
    FreshFlash();
    RecordStore store;
    TestRecord r;
    Boot(&store, &r);
    for (uint32_t n = 1; n <= 20; ++n) {
      TestRecord rec = MakeRecord(n);
      store.Save(&rec, sizeof(rec));
    }
    bool ok = true;
    for (int cut = 0; cut < 3; ++cut) {
      fake::ArmPowerLoss(40, fake::ERASE_PREFIX, 99 + cut);
      TestRecord rec = MakeRecord(100 + cut);
      store.Save(&rec, sizeof(rec));
      fake::PowerOn();
      ok = ok && Newest() == 20;
      Boot(&store, &r);
    }
    TestRecord rec = MakeRecord(200);
    ok = ok && store.Save(&rec, sizeof(rec)) && Newest() == 200;
    Check("storage: three interrupted saves in a row, then a good one",
          ok && fake::flash_stats().violations == 0, "newest %ld, %s",
          Newest(), ViolationText().c_str());
  }

  // Garbage in the flash at the first power-up.
  {
    int bad = 0;
    std::string detail;
    for (uint64_t seed = 1; seed <= 5; ++seed) {
      fake::PowerOn();
      fake::FlashFillRandom(seed * 0x9e3779b97f4a7c15ull);
      fake::ResetFlashStats();
      Settings settings;
      const bool loaded = settings.Init();
      const bool defaults = settings.state().engine == 8 &&
          settings.state().enable_alt_navigation == 0 &&
          settings.calibration_data(CV_ADC_CHANNEL_V_OCT).scale == -60.0f;
      settings.mutable_state()->engine = 13;
      settings.SaveState();
      AdvanceTimeMs(5100.0);
      settings.Persist();
      Settings again;
      const bool reloaded = again.Init() && again.state().engine == 13;
      // Then a few hundred more saves on what is left of the garbage.
      RecordStore store;
      TestRecord r;
      Boot(&store, &r);
      int wrong = 0;
      for (uint32_t n = 1; n <= 300; ++n) {
        TestRecord rec = MakeRecord(n);
        if (!store.Save(&rec, sizeof(rec)) || Newest() != static_cast<long>(n)) {
          ++wrong;
        }
      }
      if (loaded || !defaults || !reloaded || wrong ||
          fake::flash_stats().violations) {
        if (!bad) {
          char text[160];
          snprintf(text, sizeof(text), "seed %llu: loaded %d, defaults %d, "
                   "reloaded %d, %d wrong of 300, %s",
                   static_cast<unsigned long long>(seed), loaded, defaults,
                   reloaded, wrong, ViolationText().c_str());
          detail = text;
        }
        ++bad;
      }
    }
    Check("storage: garbage flash at first power-up -> defaults, then saves "
          "work", bad == 0, "%d of 5 garbage patterns wrong%s%s", bad,
          bad ? "; first: " : "", detail.c_str());
  }

  // Records of another firmware version (another size) in the ring.
  {
    FreshFlash();
    RecordStore old_store;
    old_store.Init(kOffset, kSectors, kSlotSize, kTag);
    uint8_t old_record[100];
    old_store.Load(old_record, sizeof(old_record));
    for (int n = 0; n < 50; ++n) {
      memset(old_record, n, sizeof(old_record));
      old_store.Save(old_record, sizeof(old_record));
    }
    Settings settings;
    const bool loaded = settings.Init();
    settings.mutable_state()->engine = 20;
    settings.SaveState();
    AdvanceTimeMs(5100.0);
    settings.Persist();
    Settings again;
    const bool reloaded = again.Init();
    Check("storage: records of another size (an older firmware) are ignored, "
          "new ones win", !loaded && reloaded && again.state().engine == 20 &&
          fake::flash_stats().violations == 0,
          "first load %d, reload %d, engine %d, %s", loaded, reloaded,
          again.state().engine, ViolationText().c_str());
  }

  // Settings: saves requested from the audio callback, written by the main
  // loop under a critical section; an out-of-range engine.
  {
    FreshFlash();
    Settings settings;
    settings.Init();
    const int writes = fake::flash_stats().write_calls;
    fake::SetInInterrupt(true);
    settings.mutable_state()->engine = 21;
    settings.SaveState();
    settings.SavePersistentData();
    fake::SetInInterrupt(false);
    const int writes_in_interrupt = fake::flash_stats().write_calls - writes;
    settings.Persist();
    AdvanceTimeMs(3000.0);
    settings.Persist();
    const int writes_early = fake::flash_stats().write_calls - writes;
    // Another change restarts the hold-off.
    fake::SetInInterrupt(true);
    settings.SaveState();
    fake::SetInInterrupt(false);
    AdvanceTimeMs(3000.0);
    settings.Persist();
    const int writes_restarted = fake::flash_stats().write_calls - writes;
    AdvanceTimeMs(2100.0);
    settings.Persist();
    const int writes_after = fake::flash_stats().write_calls - writes;
    AdvanceTimeMs(6000.0);
    settings.Persist();
    const int writes_again = fake::flash_stats().write_calls - writes;
    Check("storage: Save*() only mark the settings dirty; Persist() writes "
          "once, 5 s after the last change, under a critical section",
          writes_in_interrupt == 0 && writes_early == 0 &&
          writes_restarted == 0 && writes_after == 1 && writes_again == 1 &&
          fake::critical_max_depth() == 1 && fake::critical_depth() == 0 &&
          fake::flash_stats().violations == 0,
          "writes: %d in the callback, %d within 3 s, %d 3 s after a "
          "second change, %d at 5.1 s, %d later; critical depth max %d, "
          "now %d", writes_in_interrupt, writes_early, writes_restarted,
          writes_after, writes_again, fake::critical_max_depth(),
          fake::critical_depth());
    // A save request that changes nothing, and a change undone before the
    // hold-off ends, write nothing.
    fake::SetInInterrupt(true);
    settings.SaveState();
    fake::SetInInterrupt(false);
    AdvanceTimeMs(5100.0);
    settings.Persist();
    const int writes_unchanged = fake::flash_stats().write_calls - writes;
    fake::SetInInterrupt(true);
    settings.mutable_state()->engine = 5;
    settings.SaveState();
    settings.mutable_state()->engine = 21;
    settings.SaveState();
    fake::SetInInterrupt(false);
    AdvanceTimeMs(5100.0);
    settings.Persist();
    const int writes_undone = fake::flash_stats().write_calls - writes;
    Check("storage: a save request that leaves the settings as the flash holds "
          "them writes nothing",
          writes_unchanged == 1 && writes_undone == 1 && !settings.dirty_,
          "writes after an unchanged save %d, after a change undone %d "
          "(1 = only the earlier save)", writes_unchanged, writes_undone);
    // A record with engine 40.
    Settings::Record record;
    record.persistent_data = settings.persistent_data_;
    record.state = settings.state_;
    record.state.engine = 40;
    settings.store_.Save(&record, sizeof(record));
    Settings again;
    again.Init();
    Check("storage: a stored engine beyond 23 loads as 23",
          again.state().engine == 23, "engine %d", again.state().engine);
  }
}

// ====================================================================== 7
void TestUserData() {
  Section("7. User data (wavetables, DX7 banks, wave terrains)");
  FreshFlash();
  UserData::Init();
  UserData user_data;
  bool none = true;
  for (int slot = 0; slot < 24; ++slot) {
    none = none && user_data.ptr(slot) == nullptr;
  }
  Check("userdata: an erased flash has no user data for any model", none,
        "%s", none ? "all NULL" : "some slot has data");

  std::vector<uint8_t> rx(UserData::SIZE);
  for (int i = 0; i < UserData::SIZE; ++i) {
    rx[i] = static_cast<uint8_t>(i * 13 + 5);
  }
  rx[UserData::SIZE - 2] = 2;  // the block is for models 2..4 (six-op FM)
  rx[UserData::SIZE - 1] = 4;
  const std::vector<uint8_t> original = rx;
  const int writes0 = fake::flash_stats().write_calls;
  fake::SetInInterrupt(true);
  const bool below = user_data.Save(rx.data(), 1);
  const bool above = user_data.Save(rx.data(), 5);
  fake::SetInInterrupt(false);
  UserData::Persist();
  Check("userdata: Save() refuses a model outside the block's range",
        !below && !above && rx == original &&
        fake::flash_stats().write_calls == writes0 &&
        user_data.ptr(1) == nullptr && user_data.ptr(5) == nullptr,
        "model 1: %d, model 5: %d, buffer untouched %d, flash writes %d",
        below, above, rx == original,
        fake::flash_stats().write_calls - writes0);

  fake::SetInInterrupt(true);
  const bool saved = user_data.Save(rx.data(), 3);
  fake::SetInInterrupt(false);
  const uint8_t* p = user_data.ptr(3);
  const bool copied = p && memcmp(p, rx.data(), UserData::SIZE) == 0;
  const bool flash_untouched = fake::flash()[0x10000] == 0xff &&
      fake::flash_stats().write_calls == writes0;
  Check("userdata: Save() for model 3 tags the block ('U', ' ' + 3) and "
        "copies it to RAM, from the callback, without flash",
        saved && rx[UserData::SIZE - 2] == 'U' &&
        rx[UserData::SIZE - 1] == ' ' + 3 && copied && flash_untouched &&
        fake::flash_stats().violations == 0,
        "saved %d, tag %c/%d, RAM copy %d, flash untouched %d", saved,
        rx[UserData::SIZE - 2], rx[UserData::SIZE - 1] - ' ', copied,
        flash_untouched);
  Check("userdata: ptr() only for the tagged model",
        user_data.ptr(2) == nullptr && user_data.ptr(4) == nullptr &&
        user_data.ptr(3) != nullptr && user_data.ptr(0) == nullptr,
        "2: %p, 3: %p, 4: %p", static_cast<const void*>(user_data.ptr(2)),
        static_cast<const void*>(user_data.ptr(3)),
        static_cast<const void*>(user_data.ptr(4)));

  const int erases = fake::flash_stats().erase_calls;
  UserData::Persist();
  const bool written = memcmp(fake::flash() + 0x10000, rx.data(),
                              UserData::SIZE) == 0;
  const int writes1 = fake::flash_stats().write_calls;
  UserData::Persist();
  Check("userdata: Persist() erases the sector at 0x10000 and writes the "
        "block once",
        written && fake::flash_stats().erase_calls == erases + 1 &&
        fake::flash_stats().erases[0x10] >= 1 &&
        fake::flash_stats().write_calls == writes1 &&
        fake::flash_stats().violations == 0,
        "written %d, erases %d, second Persist() wrote %d", written,
        fake::flash_stats().erase_calls - erases,
        fake::flash_stats().write_calls - writes1);

  memset(UserData::data_, 0, UserData::SIZE);
  UserData::Init();
  Check("userdata: Init() reloads the block from flash",
        user_data.ptr(3) && memcmp(user_data.ptr(3), rx.data(),
                                   UserData::SIZE) == 0,
        "%s", user_data.ptr(3) ? "tagged for model 3" : "missing");

  // Range limits are inclusive.
  std::vector<uint8_t> rx2 = original;
  rx2[UserData::SIZE - 2] = 5;
  rx2[UserData::SIZE - 1] = 5;
  std::vector<uint8_t> rx3 = rx2;
  const bool one_model = user_data.Save(rx2.data(), 5);
  Check("userdata: a block for exactly one model is accepted for it",
        one_model && user_data.ptr(5) && !user_data.ptr(3), "saved %d",
        one_model);
  UserData::Persist();

  // The settings ring and the user data block do not overlap.
  {
    Settings settings;
    settings.Init();
    for (int i = 0; i < 300; ++i) {
      settings.mutable_state()->engine = i % 24;
      settings.SaveState();
      AdvanceTimeMs(5100.0);
      settings.Persist();
    }
    memset(UserData::data_, 0, UserData::SIZE);
    UserData::Init();
    Settings again;
    const bool loaded = again.Init();
    Check("userdata: 300 settings saves leave the user data intact",
          loaded && again.state().engine == 299 % 24 && user_data.ptr(5) &&
          memcmp(user_data.ptr(5), rx2.data(), UserData::SIZE) == 0 &&
          fake::flash_stats().violations == 0,
          "settings engine %d, user data %s", again.state().engine,
          user_data.ptr(5) ? "intact" : "LOST");
    (void)rx3;
  }
  // Power loss between the erase and the write: no user data, no crash.
  {
    std::vector<uint8_t> rx4 = original;  // range 2..4
    user_data.Save(rx4.data(), 3);
    fake::ArmPowerLoss(1, fake::ERASE_PREFIX, 5);
    UserData::Persist();
    fake::PowerOn();
    UserData::Init();
    Observe("userdata: power lost during Persist() (after the erase) leaves "
            "no user data (models fall back to their built-in data): ptr(3) "
            "%s; Plaits' own flash write has the same window",
            user_data.ptr(3) ? "still set" : "NULL");
  }

  // The models that read their user data while they play (wave terrain 5,
  // wavetable 13), from the RAM copy, as main.cc hands it over: Save() with
  // the voice's active engine, then Voice::ReloadUserData().
  {
    fake::ResetBoard();
    FreshFlash();
    Rig rig(true);
    rig.Boot();
    // MODEL's offset as calibrated, so the voice plays the selected model.
    rig.settings().mutable_calibration_data(CV_ADC_CHANNEL_MODEL)->offset = 0.0f;
    rig.RunMs(300.0);
    uint64_t state = 77;
    const int engines[] = { 5, 13 };
    for (int engine : engines) {
      std::vector<uint8_t> block(UserData::SIZE);
      for (int i = 0; i < UserData::SIZE; ++i) {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        block[i] = static_cast<uint8_t>(state >> 24);
      }
      if (engine == 13) {
        // Bank D's map: 192 built-in waves, then the 15 custom ones (what
        // Mutable's editor sends; 207+ is checked below without playing).
        for (int i = 0; i < 64; ++i) {
          block[i] = static_cast<uint8_t>(block[i] % 207);
        }
      }
      block[UserData::SIZE - 2] = static_cast<uint8_t>(engine);
      block[UserData::SIZE - 1] = static_cast<uint8_t>(engine);
      rig.patch.engine = engine;
      rig.RunMs(50.0);
      const int active = rig.voice->active_engine();
      fake::SetInInterrupt(true);
      const bool saved = user_data.Save(block.data(), active);
      rig.voice->ReloadUserData();
      fake::SetInInterrupt(false);
      rig.peak_out = rig.peak_aux = 0;
      rig.RunMs(300.0);
      const bool in_ram = user_data.ptr(engine) == UserData::data_;
      char name[96];
      snprintf(name, sizeof(name), "userdata: model %d plays from the RAM "
               "copy of a received block", engine);
      Check(name, active == engine && saved && in_ram && rig.peak_out > 0 &&
            fake::flash_stats().violations == 0,
            "active %d, saved %d, ptr() in RAM %d, peak OUT %d AUX %d, %s",
            active, saved, in_ram, rig.peak_out, rig.peak_aux,
            fake::flash_stats().violations ? "FLASH FROM CALLBACK" : "no flash in the callback");
    }

    // Where a map entry can point: WavetableEngine::LoadUserData() clamps
    // the custom wave to min(w - 192, 15), and every wave is 128 + 4
    // samples; Hermite interpolation reads samples 0..130 of it. Checked by
    // loading the map without playing it (playing it is a read past the
    // block, which AddressSanitizer stops on).
    std::vector<uint8_t> block(UserData::SIZE, 0);
    for (int i = 0; i < 64; ++i) {
      block[i] = static_cast<uint8_t>(192 + 15 + i % 49);  // 207..255
    }
    block[UserData::SIZE - 2] = 13;
    block[UserData::SIZE - 1] = 13;
    user_data.Save(block.data(), 13);
    WavetableEngine& wavetable = rig.voice->wavetable_engine_;
    wavetable.LoadUserData(user_data.ptr(13));
    long last_byte = 0;
    for (int i = 0; i < 64; ++i) {
      const uint8_t* wave = reinterpret_cast<const uint8_t*>(
          wavetable.wave_map_[3 * 64 + i]);
      last_byte = std::max(last_byte, static_cast<long>(
          wave - UserData::data_) + 2 * 130 + 1);
    }
    Check("userdata: every wave the wavetable map can select lies inside "
          "the 4 kB block",
          last_byte < static_cast<long>(sizeof(UserData::data_)),
          "map values 207..255 select custom wave 15 of 0..14 (upstream "
          "min(w - 192, kNumCustomWaves)): reads up to byte %ld of the "
          "%d-byte block, %ld bytes past the end of UserData::data_ (%zu bytes)",
          last_byte, UserData::SIZE,
          last_byte + 1 - static_cast<long>(sizeof(UserData::data_)),
          sizeof(UserData::data_));
    // Leave a valid map loaded.
    std::vector<uint8_t> valid(UserData::SIZE, 0);
    valid[UserData::SIZE - 2] = 13;
    valid[UserData::SIZE - 1] = 13;
    user_data.Save(valid.data(), 13);
    wavetable.LoadUserData(user_data.ptr(13));
  }
}

}  // namespace test
