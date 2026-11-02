// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the factory presets on the real blocks. Every name
// they look up exists; each preset is valid, survives SanitizePreset
// unchanged and covers what the set promises (every block type, every
// algorithm, BEADSY twice, a clean start); and each one runs 5 s of noise
// bursts over a chord through the engine, with the real modulation
// sources, moving CVs, MIDI notes and send throws: no fault, finite, not
// silent, not slammed into the limiter.

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "check.h"
#include "test_support.h"

#include "app/factory_presets.h"
#include "app/mod_sources.h"
#include "engine/engine.h"
#include "engine/preset.h"
#include "engine/registry.h"

namespace sidefx {
// factory_presets.cc: names the presets asked for and did not find.
int FactoryPresetMisses();
}  // namespace sidefx

using namespace sidefx;

namespace {

// The sizes main.cc gives the arenas.
const size_t kInternalArena = 200u << 10;
const size_t kExternalArena = 56u << 20;

// Bursts of noise over a minor chord, now and then a loud hit.
struct Signal {
  uint32_t noise;
  float phase[3];
  int sample;

  Signal() : noise(77), sample(0) {
    phase[0] = phase[1] = phase[2] = 0.0f;
  }

  Frame Next() {
    static const float kHz[3] = { 110.0f, 130.81f, 164.81f };
    float s = 0.0f;
    for (int k = 0; k < 3; ++k) {
      phase[k] += kHz[k] / kSampleRate;
      if (phase[k] >= 1.0f) {
        phase[k] -= 1.0f;
      }
      s += 0.15f * sinf(6.2831853f * phase[k]);
    }
    const bool burst = (sample / 4800) % 5 == 0;
    const bool hit = sample % 96000 < 200;
    ++sample;
    const float n = test::Noise(&noise);
    const float l = s + (burst ? 0.4f * n : 0.0f) + (hit ? 2.0f * n : 0.0f);
    const float r = s * 0.9f + (burst ? 0.4f * test::Noise(&noise) : 0.0f);
    return MakeFrame(l, r);
  }
};

int FindType(int slot, const char* name) {
  for (int t = 0; t < NumBlockTypes(slot); ++t) {
    if (!strcmp(GetBlock(slot, t)->info().name, name)) {
      return t;
    }
  }
  return -1;
}

int CountMods(const Preset& p) {
  int n = p.wet_mod.source != MOD_OFF;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    n += p.slot[s].send_gate != MOD_OFF;
    for (int i = 0; i < kNumSlotValues; ++i) {
      n += p.slot[s].mod[i].source != MOD_OFF;
    }
  }
  return n;
}

struct RunResult {
  bool finite;
  int faults;
  float peak;
  float rms;            // after the first 0.5 s
  float limited;        // share of samples above 0.95
  float slot_peak[NUM_SLOTS];  // each slot's wet meter, after 0.5 s
};

// 5 s through the engine at DRY `dry`, with the real modulation sources:
// CV1..CV3 slow +-1.5 V sines, CV4 a 0/5 V gate at 1 Hz, MIDI notes held
// now and then, CC A at half. With `throws`, the sends that are off are
// thrown in from 2 s to 3 s.
RunResult Run(Engine* engine, const Preset& preset, float dry, bool throws) {
  ModSources sources;
  sources.Init();
  sources.SetCc(0, 0.5f);
  CvCalibration calibration;
  InitCvCalibration(&calibration);
  engine->set_dry(dry);
  engine->ApplyPresetNow(preset);
  int faults_before = 0;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    faults_before += engine->faults(s);
  }

  TempoState tempo = test::Tempo120();
  tempo.beat_seconds = 600.0f / float(preset.tempo);
  tempo.bar_increment = 1.0f / (4.0f * tempo.beat_seconds * kSampleRate);
  Signal signal;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  RunResult r = { true, 0, 0.0f, 0.0f, 0.0f, { 0.0f, 0.0f, 0.0f, 0.0f } };
  double energy = 0.0;
  int counted = 0;
  int limited = 0;
  const int kBlocks = int(5.0f * kSampleRate / kBlockSize);
  const int kSkip = int(0.5f * kSampleRate / kBlockSize);
  bool thrown[NUM_SLOTS] = { false, false, false, false };
  for (int b = 0; b < kBlocks; ++b) {
    const float t = float(b * kBlockSize) / kSampleRate;
    if (throws && b == int(2.0f * kSampleRate / kBlockSize)) {
      for (int s = 0; s < NUM_SLOTS; ++s) {
        if (!preset.slot[s].send) {
          engine->ToggleSend(s);
          thrown[s] = true;
        }
      }
    }
    if (throws && b == int(3.0f * kSampleRate / kBlockSize)) {
      for (int s = 0; s < NUM_SLOTS; ++s) {
        if (thrown[s]) {
          engine->ToggleSend(s);
        }
      }
    }
    if (b == int(1.0f * kSampleRate / kBlockSize)) {
      sources.NoteOn(48);
    } else if (b == int(2.5f * kSampleRate / kBlockSize)) {
      sources.NoteOff(48);
      sources.NoteOn(55);
    } else if (b == int(3.5f * kSampleRate / kBlockSize)) {
      sources.NoteOff(55);
    }
    float cv_raw[4];
    for (int i = 0; i < 3; ++i) {
      const float volts = 1.5f * sinf(6.2831853f * (0.13f + 0.07f * float(i)) * t);
      cv_raw[i] = calibration.offset[i] + volts / calibration.scale[i];
    }
    const float gate = fmodf(t, 1.0f) < 0.4f ? 5.0f : 0.0f;
    cv_raw[3] = calibration.offset[3] + gate / calibration.scale[3];

    tempo.bar_phase = fmodf(tempo.bar_phase + kBlockSize * tempo.bar_increment, 1.0f);
    for (size_t i = 0; i < kBlockSize; ++i) {
      in[i] = signal.Next();
    }
    sources.Process(engine->preset(), tempo, cv_raw, in, kBlockSize);
    engine->Process(sources.values(), tempo, in, out, kBlockSize);
    for (size_t i = 0; i < kBlockSize; ++i) {
      r.finite = r.finite && test::Finite(out[i]);
      const float m = fmaxf(fabsf(out[i].l), fabsf(out[i].r));
      r.peak = fmaxf(r.peak, m);
      if (b >= kSkip) {
        energy += double(out[i].l) * out[i].l + double(out[i].r) * out[i].r;
        counted += 2;
        limited += m > 0.95f;
      }
    }
    for (int s = 0; s < NUM_SLOTS && b >= kSkip; ++s) {
      r.slot_peak[s] = fmaxf(r.slot_peak[s], engine->slot_level(s));
    }
    if (b % 64 == 0) {
      engine->Poll();
    }
  }
  int faults_after = 0;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    faults_after += engine->faults(s);
  }
  r.faults = faults_after - faults_before;
  r.rms = counted ? float(sqrt(energy / counted)) : 0.0f;
  r.limited = counted ? float(limited) / float(counted / 2) : 0.0f;
  return r;
}

}  // namespace

TEST(factory_presets, names_found_valid_and_sanitized) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  CHECK(InitBlocks(memory.memory()));
  const int misses_before = FactoryPresetMisses();
  CHECK(NumFactoryPresets() == 16);
  for (int i = 0; i < NumFactoryPresets(); ++i) {
    Preset p;
    memset(&p, 0x5a, sizeof(p));
    GetFactoryPreset(i, &p);
    CHECK(PresetValid(p));
    Preset q = p;
    SanitizePreset(&q);
    CHECK(!memcmp(&p, &q, sizeof(p)));
    const size_t length = strlen(p.name);
    CHECK(length > 0 && length <= kPresetNameLength);
    CHECK(strcmp(p.name, "INIT") != 0);
    for (int j = 0; j < i; ++j) {
      Preset other;
      GetFactoryPreset(j, &other);
      CHECK(strcmp(p.name, other.name) != 0);
    }
    // Sync bits only on PARAM_SYNC parameters.
    for (int s = 0; s < NUM_SLOTS; ++s) {
      const BlockInfo& info = GetBlock(s, p.slot[s].type)->info();
      for (int k = 0; k < 16; ++k) {
        if ((p.slot[s].sync_mask >> k) & 1) {
          CHECK(k < info.num_params && (info.params[k].flags & PARAM_SYNC));
        }
      }
    }
    // The same twice (no state carried between calls).
    Preset again;
    GetFactoryPreset(i, &again);
    CHECK(!memcmp(&p, &again, sizeof(p)));
  }
  const int misses = FactoryPresetMisses() - misses_before;
  if (misses) {
    printf("factory presets: %d names not found\n", misses);
  }
  CHECK(misses == 0);

  // Out of range: INIT.
  Preset p;
  GetFactoryPreset(NumFactoryPresets(), &p);
  CHECK(PresetValid(p) && !strcmp(p.name, "INIT"));
}

TEST(factory_presets, coverage) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  CHECK(InitBlocks(memory.memory()));
  bool type_used[NUM_SLOTS][8];
  memset(type_used, 0, sizeof(type_used));
  bool algorithm_used[NUM_ALGORITHMS];
  memset(algorithm_used, 0, sizeof(algorithm_used));
  const int beadsy = FindType(SLOT_TEXTURE, "BEADSY");
  CHECK(beadsy >= 0);
  int beadsy_presets = 0;
  int modulated = 0;
  int with_throw = 0;
  int synced = 0;
  for (int i = 0; i < NumFactoryPresets(); ++i) {
    Preset p;
    GetFactoryPreset(i, &p);
    algorithm_used[p.algorithm] = true;
    bool throw_ready = false;
    bool any_sync = false;
    for (int s = 0; s < NUM_SLOTS; ++s) {
      type_used[s][p.slot[s].type] = true;
      throw_ready = throw_ready || !p.slot[s].send;
      any_sync = any_sync || p.slot[s].sync_mask != 0;
    }
    beadsy_presets += p.slot[SLOT_TEXTURE].type == beadsy;
    modulated += CountMods(p) > 0;
    with_throw += throw_ready;
    synced += any_sync;
  }
  for (int s = 0; s < NUM_SLOTS; ++s) {
    for (int t = 0; t < NumBlockTypes(s); ++t) {
      if (!type_used[s][t]) {
        printf("no factory preset uses %s\n", GetBlock(s, t)->info().name);
      }
      CHECK(type_used[s][t]);
    }
  }
  for (int a = 0; a < NUM_ALGORITHMS; ++a) {
    CHECK(algorithm_used[a]);
  }
  CHECK(beadsy_presets >= 2);
  CHECK(modulated >= 14);
  CHECK(with_throw >= 8);
  CHECK(synced >= 12);
  test::Note("%d presets: %d with BEADSY, %d modulated, %d with a send "
             "ready to throw, %d synced", NumFactoryPresets(), beadsy_presets,
             modulated, with_throw, synced);

  // Preset 0 is the clean start: no modulation, the delay and the reverb
  // on, the rest off (test_app_storage.cc relies on these sends).
  Preset p;
  GetFactoryPreset(0, &p);
  CHECK(CountMods(p) == 0);
  CHECK(p.algorithm == ALGORITHM_SERIAL && p.tempo == 1200);
  CHECK(p.slot[SLOT_DELAY].send == 1 && p.slot[SLOT_REVERB].send == 1);
  CHECK(p.slot[SLOT_PITCH].send == 0 && p.slot[SLOT_TEXTURE].send == 0);
}

TEST(factory_presets, run_through_the_engine) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  Engine engine;
  CHECK(engine.Init(memory.memory()));
  for (int i = 0; i < NumFactoryPresets(); ++i) {
    Preset p;
    GetFactoryPreset(i, &p);

    // As an insert (DRY 100 %), the sends as stored, the off ones thrown.
    const RunResult insert = Run(&engine, p, 1.0f, true);
    CHECK(insert.finite);
    CHECK(insert.faults == 0);
    CHECK(insert.peak <= 1.0f);
    CHECK(insert.rms > 0.01f && insert.rms < 0.6f);
    CHECK(insert.limited < 0.02f);

    // As a return (DRY 0 %) with every send on: only the processed part.
    Preset all = p;
    for (int s = 0; s < NUM_SLOTS; ++s) {
      all.slot[s].send = 1;
    }
    SealPreset(&all);
    const RunResult wet = Run(&engine, all, 0.0f, false);
    CHECK(wet.finite);
    CHECK(wet.faults == 0);
    CHECK(wet.peak <= 1.0f);
    CHECK(wet.rms > 0.01f);
    CHECK(wet.limited < 0.02f);
    // Every block makes itself heard once its send is on.
    for (int s = 0; s < NUM_SLOTS; ++s) {
      if (wet.slot_peak[s] < 0.02f) {
        printf("%s: %s is silent (wet peak %.4f)\n", p.name,
               GetBlock(s, p.slot[s].type)->info().name, wet.slot_peak[s]);
      }
      CHECK(wet.slot_peak[s] >= 0.02f);
    }
    test::Note("%-15s slot wet peaks %.3f %.3f %.3f %.3f", p.name,
               wet.slot_peak[0], wet.slot_peak[1], wet.slot_peak[2],
               wet.slot_peak[3]);
    test::Note("%-15s insert rms %.3f peak %.2f limited %.4f | "
               "return rms %.3f peak %.2f limited %.4f", p.name, insert.rms,
               insert.peak, insert.limited, wet.rms, wet.peak, wet.limited);
    if (!insert.finite || insert.faults || !wet.finite || wet.faults) {
      printf("%s: finite %d/%d faults %d/%d\n", p.name, insert.finite,
             wet.finite, insert.faults, wet.faults);
    }
  }
}

// Not a check: every preset as the screen would show it (TEST_ARGS=-v), to
// read the values against what the comments in factory_presets.cc promise.
TEST(factory_presets, listing) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  CHECK(InitBlocks(memory.memory()));
  for (int i = 0; i < NumFactoryPresets(); ++i) {
    Preset p;
    GetFactoryPreset(i, &p);
    TempoState tempo = test::Tempo120();
    tempo.beat_seconds = 600.0f / float(p.tempo);
    test::Note("%d %s  %s  %d BPM", i, p.name, kAlgorithmNames[p.algorithm],
               p.tempo / 10);
    for (int s = 0; s < NUM_SLOTS; ++s) {
      const SlotPreset& slot = p.slot[s];
      const Block* block = GetBlock(s, slot.type);
      const BlockInfo& info = block->info();
      const ProcessContext context = test::Context(tempo, slot.sync_mask);
      char line[400];
      size_t n = 0;
      for (int k = 0; k < info.num_params && n + 40 < sizeof(line); ++k) {
        char text[16];
        block->Format(k, PresetValue(slot.value[k]), context, text,
                      sizeof(text));
        n += size_t(snprintf(line + n, sizeof(line) - n, " %s=%s",
                             info.params[k].name, text));
        if (slot.mod[k].source != MOD_OFF) {
          n += size_t(snprintf(line + n, sizeof(line) - n, "(%s%+d)",
                               kModSourceNames[slot.mod[k].source],
                               slot.mod[k].depth));
        }
      }
      test::Note("   %-10s %s mix %.2f%s%s:%s", info.name,
                 slot.send ? "ON " : "off", PresetValue(slot.value[kMixValue]),
                 slot.send_gate != MOD_OFF ? " gate " : "",
                 slot.send_gate != MOD_OFF ? kModSourceNames[slot.send_gate] : "",
                 line);
    }
  }
}
