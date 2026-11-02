// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the engine (sends, mixes, algorithms, fades, faults)
// on the fake blocks of fake_registry.cc.

#include <math.h>
#include <string.h>

#include "check.h"
#include "fake_registry.h"
#include "test_support.h"

#include "engine/engine.h"
#include "engine/preset.h"
#include "engine/registry.h"

using namespace sidefx;

namespace {

struct Rig {
  test::TestMemory memory;
  Engine engine;
  ModValues mods;
  TempoState tempo;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  uint32_t noise;

  Rig() : memory(8u << 20, 256u << 10), noise(1) {
    memset(&mods, 0, sizeof(mods));
    tempo = test::Tempo120();
    CHECK(engine.Init(memory.memory()));
  }

  // One block of noise at `level` (IN 1 and IN 2 differ), processed.
  void Block(float level) {
    for (size_t i = 0; i < kBlockSize; ++i) {
      in[i].l = level * test::Noise(&noise);
      in[i].r = level * test::Noise(&noise);
    }
    engine.Process(mods, tempo, in, out, kBlockSize);
  }

  void Blocks(int n, float level) {
    for (int i = 0; i < n; ++i) {
      Block(level);
    }
  }

  // Worst |out - k * in| over the last block, per channel gains.
  float Error(float k_l, float k_r) const {
    float e = 0.0f;
    for (size_t i = 0; i < kBlockSize; ++i) {
      e = fmaxf(e, fabsf(out[i].l - k_l * in[i].l));
      e = fmaxf(e, fabsf(out[i].r - k_r * in[i].r));
    }
    return e;
  }

  Preset Init() {
    Preset p;
    InitPreset(&p);
    return p;
  }

  void Apply(const Preset& p) { engine.ApplyPresetNow(p); }
};

// GAIN fakes (type 0) give wet = 2 * value[0] * in.
void SetGainSlot(Preset* p, int slot, float gain, float mix, bool send) {
  InitSlot(p, slot, 0);
  p->slot[slot].value[0] = PresetRaw(gain * 0.5f);
  p->slot[slot].value[kMixValue] = PresetRaw(mix);
  p->slot[slot].send = send ? 1 : 0;
}

const float kHalfPower = 0.70710678f;

}  // namespace

TEST(engine, init_passes_dry) {
  Rig rig;
  rig.Blocks(4, 0.5f);
  CHECK(rig.Error(1.0f, 1.0f) < 1e-6f);
  for (int s = 0; s < NUM_SLOTS; ++s) {
    CHECK(!rig.engine.send_active(s));
  }
}

TEST(engine, serial_full_wet) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_DELAY, 0.5f, 1.0f, true);
  rig.Apply(p);
  rig.Blocks(4, 0.5f);
  CHECK(rig.Error(0.5f, 0.5f) < 1e-5f);
}

TEST(engine, mix_zero_is_dry) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_REVERB, 0.5f, 0.0f, true);
  rig.Apply(p);
  rig.Blocks(4, 0.5f);
  CHECK(rig.Error(1.0f, 1.0f) < 1e-5f);
}

TEST(engine, dry_level_removes_unprocessed) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_DELAY, 0.5f, 0.5f, true);
  rig.Apply(p);
  rig.engine.set_dry(0.0f);
  rig.Blocks(4, 0.5f);
  // Only the wet part is left: b * gain.
  CHECK(rig.Error(kHalfPower * 0.5f, kHalfPower * 0.5f) < 1e-4f);
  rig.engine.set_dry(1.0f);
  rig.Blocks(2, 0.5f);
  CHECK(rig.Error(kHalfPower * 1.5f, kHalfPower * 1.5f) < 1e-4f);
}

TEST(engine, sends_off_and_dry_zero_is_silent) {
  Rig rig;
  rig.engine.set_dry(0.0f);
  rig.Blocks(4, 0.5f);
  CHECK(rig.Error(0.0f, 0.0f) < 1e-6f);
}

TEST(engine, wet_zero_leaves_unprocessed) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_PITCH, 0.5f, 0.5f, true);
  p.wet = 0;
  rig.Apply(p);
  rig.Blocks(4, 0.5f);
  CHECK(rig.Error(kHalfPower, kHalfPower) < 1e-4f);
}

TEST(engine, parallel_branches_pass_dry_once) {
  Rig rig;
  Preset p = rig.Init();
  p.algorithm = ALGORITHM_PARALLEL;
  SetGainSlot(&p, SLOT_PITCH, 1.0f, 0.5f, true);
  SetGainSlot(&p, SLOT_DELAY, 0.5f, 0.5f, true);
  rig.Apply(p);
  rig.Blocks(4, 0.3f);
  // wets b*1 + b*0.5, plus the input once at the mean of the branches'
  // unprocessed parts (a, a, 1, 1).
  const float k = kHalfPower * 1.5f + (2.0f * kHalfPower + 2.0f) / 4.0f;
  CHECK(rig.Error(k, k) < 1e-4f);
}

TEST(engine, every_algorithm_passes_dry_with_sends_off) {
  for (int a = 0; a < NUM_ALGORITHMS; ++a) {
    Rig rig;
    Preset p = rig.Init();
    p.algorithm = uint8_t(a);
    rig.Apply(p);
    rig.Blocks(3, 0.5f);
    CHECK(rig.Error(1.0f, 1.0f) < 1e-5f);
  }
}

TEST(engine, dual_mono_keeps_channels_apart) {
  Rig rig;
  Preset p = rig.Init();
  p.algorithm = ALGORITHM_DUAL_MONO;
  SetGainSlot(&p, SLOT_PITCH, 0.5f, 1.0f, true);    // IN 1 > P > D > OUT 1
  SetGainSlot(&p, SLOT_REVERB, 1.5f, 1.0f, true);   // IN 2 > T > R > OUT 2
  rig.Apply(p);
  rig.Blocks(4, 0.4f);
  CHECK(rig.Error(0.5f, 1.5f) < 1e-4f);
}

TEST(engine, send_off_keeps_trails) {
  Rig rig;
  Preset p = rig.Init();
  InitSlot(&p, SLOT_DELAY, 1);  // ECHO: 64 samples, feedback 0.5
  p.slot[SLOT_DELAY].value[kMixValue] = PresetRaw(1.0f);
  p.slot[SLOT_DELAY].send = 1;
  rig.Apply(p);
  memset(rig.in, 0, sizeof(rig.in));
  rig.engine.Process(rig.mods, rig.tempo, rig.in, rig.out, kBlockSize);
  rig.in[0].l = rig.in[0].r = 0.5f;  // an impulse
  rig.engine.Process(rig.mods, rig.tempo, rig.in, rig.out, kBlockSize);
  rig.engine.ToggleSend(SLOT_DELAY);  // off before the echo comes back
  memset(rig.in, 0, sizeof(rig.in));
  float peak = 0.0f;
  for (int b = 0; b < 4; ++b) {
    rig.engine.Process(rig.mods, rig.tempo, rig.in, rig.out, kBlockSize);
    for (size_t i = 0; i < kBlockSize; ++i) {
      peak = fmaxf(peak, fabsf(rig.out[i].l));
    }
  }
  CHECK(!rig.engine.send_active(SLOT_DELAY));
  CHECK(peak > 0.4f);  // the echo rang out
  // New input passes dry and no longer reaches the echo.
  rig.Blocks(8, 0.5f);
  for (int b = 0; b < 8; ++b) {
    rig.Block(0.0f);
  }
  float residue = 0.0f;
  for (size_t i = 0; i < kBlockSize; ++i) {
    residue = fmaxf(residue, fabsf(rig.out[i].l));
  }
  CHECK(residue < 0.01f);
}

TEST(engine, freeze_block_hears_input_with_send_off) {
  Rig rig;
  Preset p = rig.Init();
  InitSlot(&p, SLOT_TEXTURE, 3);  // FREEZE: holds while the send is off
  p.slot[SLOT_TEXTURE].value[kMixValue] = PresetRaw(1.0f);
  p.slot[SLOT_TEXTURE].send = 1;
  rig.Apply(p);
  for (size_t i = 0; i < kBlockSize; ++i) {
    rig.in[i].l = rig.in[i].r = 0.25f;
  }
  for (int b = 0; b < 4; ++b) {
    rig.engine.Process(rig.mods, rig.tempo, rig.in, rig.out, kBlockSize);
  }
  CHECK_NEAR(rig.out[kBlockSize - 1].l, 0.25f, 1e-4);
  rig.engine.SetSend(SLOT_TEXTURE, false);
  for (int b = 0; b < 4; ++b) {
    rig.engine.Process(rig.mods, rig.tempo, rig.in, rig.out, kBlockSize);
  }
  for (size_t i = 0; i < kBlockSize; ++i) {
    rig.in[i].l = rig.in[i].r = 0.1f;
  }
  for (int b = 0; b < 2; ++b) {
    rig.engine.Process(rig.mods, rig.tempo, rig.in, rig.out, kBlockSize);
  }
  // dry 0.1 passes whole, the frozen 0.25 plays on top.
  CHECK_NEAR(rig.out[kBlockSize - 1].l, 0.35f, 1e-3);
}

TEST(engine, nan_block_is_bypassed_and_reset) {
  Rig rig;
  Preset p = rig.Init();
  InitSlot(&p, SLOT_TEXTURE, 2);  // NAN above 0.99
  p.slot[SLOT_TEXTURE].value[0] = 65535;
  p.slot[SLOT_TEXTURE].value[kMixValue] = PresetRaw(1.0f);
  p.slot[SLOT_TEXTURE].send = 1;
  rig.Apply(p);
  FakeBlock* nan_block = GetFakeBlock(SLOT_TEXTURE, 2);
  const int resets = nan_block->resets;
  rig.Blocks(3, 0.5f);
  bool finite = true;
  for (size_t i = 0; i < kBlockSize; ++i) {
    finite = finite && test::Finite(rig.out[i]);
  }
  CHECK(finite);
  CHECK(rig.engine.faults(SLOT_TEXTURE) >= 1);
  CHECK(rig.Error(1.0f, 1.0f) < 1e-5f);  // bypassed: the dry passes
  rig.engine.mutable_preset()->slot[SLOT_TEXTURE].value[0] = PresetRaw(0.5f);
  rig.engine.Poll();
  CHECK(nan_block->resets == resets + 1);
  const int faults = rig.engine.faults(SLOT_TEXTURE);
  rig.Blocks(20, 0.5f);
  CHECK(rig.engine.faults(SLOT_TEXTURE) == faults);
  CHECK(rig.Error(1.0f, 1.0f) < 1e-4f);  // NAN fake at 0.5 passes its input
}

TEST(engine, fault_during_a_type_change_keeps_the_change) {
  // The old block blows up while it fades out for a new type (quite
  // possibly why the user picked another): the new type still comes in.
  Rig rig;
  Preset p = rig.Init();
  InitSlot(&p, SLOT_TEXTURE, 2);  // NAN above 0.99
  p.slot[SLOT_TEXTURE].value[0] = PresetRaw(0.5f);
  p.slot[SLOT_TEXTURE].value[kMixValue] = PresetRaw(1.0f);
  p.slot[SLOT_TEXTURE].send = 1;
  rig.Apply(p);
  rig.Blocks(2, 0.3f);
  FakeBlock* gain = GetFakeBlock(SLOT_TEXTURE, 0);
  const int resets = gain->resets;
  rig.engine.SetBlockType(SLOT_TEXTURE, 0);
  CHECK(rig.engine.block_type(SLOT_TEXTURE) == 0);
  rig.engine.mutable_preset()->slot[SLOT_TEXTURE].value[0] = 65535;
  rig.Block(0.3f);
  CHECK(rig.engine.faults(SLOT_TEXTURE) == 1);
  CHECK(rig.engine.block_type(SLOT_TEXTURE) == 0);  // still on its way
  rig.engine.Poll();
  CHECK(!rig.engine.changing(SLOT_TEXTURE));
  CHECK(rig.engine.block_type(SLOT_TEXTURE) == 0);
  CHECK(rig.engine.preset().slot[SLOT_TEXTURE].type == 0);
  CHECK(gain->resets == resets + 1);
  rig.Blocks(30, 0.3f);
  CHECK(rig.engine.faults(SLOT_TEXTURE) == 1);
  CHECK(rig.engine.block_type(SLOT_TEXTURE) == 0);
}

TEST(engine, gains_and_polarity_glide) {
  // IN GAIN, OUT GAIN and OUT POLARITY never step the signal: a step of
  // a constant input shows as one jump between samples.
  Rig rig;
  rig.Apply(rig.Init());
  Frame in[kBlockSize];
  for (size_t i = 0; i < kBlockSize; ++i) {
    in[i] = MakeFrame(0.25f, -0.25f);
  }
  for (int b = 0; b < 10; ++b) {
    rig.engine.Process(rig.mods, rig.tempo, in, rig.out, kBlockSize);
  }
  CHECK_NEAR(rig.out[kBlockSize - 1].l, 0.25f, 1e-5);
  struct Change {
    float input;
    float output;
    float expect;  // OUT 1 once settled
    float max_jump;
  };
  const Change changes[] = {
    { 1.0f, -1.0f, -0.25f, 0.0025f },  // the polarity flip: 5 ms
    { 1.0f, 1.0f, 0.25f, 0.0025f },
    { 1.0f, 1.12f, 0.28f, 0.0025f },   // +1 dB
    { 2.0f, 1.12f, 0.56f, 0.003f },    // +6 dB in
    { 1.0f, 1.0f, 0.25f, 0.005f },     // both at once
  };
  for (size_t c = 0; c < sizeof(changes) / sizeof(changes[0]); ++c) {
    rig.engine.set_gains(changes[c].input, changes[c].output);
    float previous = rig.out[kBlockSize - 1].l;
    float max_jump = 0.0f;
    for (int b = 0; b < 30; ++b) {
      rig.engine.Process(rig.mods, rig.tempo, in, rig.out, kBlockSize);
      for (size_t i = 0; i < kBlockSize; ++i) {
        max_jump = fmaxf(max_jump, fabsf(rig.out[i].l - previous));
        previous = rig.out[i].l;
      }
    }
    test::Note("change %d: largest step %.5f", int(c), max_jump);
    CHECK(max_jump < changes[c].max_jump);
    CHECK_NEAR(rig.out[kBlockSize - 1].l, changes[c].expect, 1e-3);
    CHECK_NEAR(rig.out[kBlockSize - 1].r, -changes[c].expect, 1e-3);
  }
}

TEST(engine, type_change_fades_detaches_and_resets) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_DELAY, 0.5f, 1.0f, true);
  rig.Apply(p);
  rig.Blocks(3, 0.5f);
  FakeBlock* echo = GetFakeBlock(SLOT_DELAY, 1);
  const int resets = echo->resets;
  rig.engine.SetBlockType(SLOT_DELAY, 1);
  CHECK(rig.engine.block_type(SLOT_DELAY) == 1);
  CHECK(rig.engine.changing(SLOT_DELAY));
  rig.engine.Poll();  // not detached yet: nothing happens
  CHECK(echo->resets == resets);
  rig.Blocks(16, 0.5f);  // 8 ms fade
  CHECK(rig.Error(1.0f, 1.0f) < 1e-5f);  // detached: the input passes
  rig.engine.Poll();
  CHECK(echo->resets == resets + 1);
  CHECK(!rig.engine.changing(SLOT_DELAY));
  CHECK(rig.engine.preset().slot[SLOT_DELAY].type == 1);
  CHECK(rig.engine.preset().slot[SLOT_DELAY].send == 1);  // kept
  const int calls = echo->process_calls;
  rig.Blocks(16, 0.5f);
  CHECK(echo->process_calls == calls + 16);
}

TEST(engine, preset_load_mutes_swaps_unmutes) {
  Rig rig;
  rig.Blocks(2, 0.5f);
  Preset p = rig.Init();
  p.algorithm = ALGORITHM_PD_TR;
  SetGainSlot(&p, SLOT_TEXTURE, 0.5f, 1.0f, true);
  SetPresetName(&p, "LOADED");
  rig.engine.LoadPreset(p);
  CHECK(rig.engine.loading());
  float last = 1.0f;
  for (int b = 0; b < 20; ++b) {
    rig.Block(0.5f);
    last = 0.0f;
    for (size_t i = 0; i < kBlockSize; ++i) {
      last = fmaxf(last, fabsf(rig.out[i].l));
    }
  }
  CHECK(last == 0.0f);  // muted, waiting for Poll()
  rig.engine.Poll();
  CHECK(!rig.engine.loading());
  CHECK(!strcmp(rig.engine.preset().name, "LOADED"));
  CHECK(rig.engine.preset().algorithm == ALGORITHM_PD_TR);
  rig.Blocks(20, 0.4f);
  // (P > D) | (T > R) with only T on: T's branch gives 0.5 x at full wet,
  // P > D passes x; merged: (x - x) + (0.5x - 0) + x * mean(1, 0) = x.
  CHECK(rig.Error(1.0f, 1.0f) < 1e-4f);
}

TEST(engine, algorithm_change_dips_and_recovers) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_PITCH, 1.0f, 0.5f, true);
  SetGainSlot(&p, SLOT_DELAY, 0.5f, 0.5f, true);
  rig.Apply(p);
  rig.Blocks(4, 0.3f);
  rig.engine.mutable_preset()->algorithm = ALGORITHM_PARALLEL;
  float minimum = 1.0f;
  for (int b = 0; b < 30; ++b) {
    rig.Block(0.3f);
    float peak = 0.0f;
    for (size_t i = 0; i < kBlockSize; ++i) {
      peak = fmaxf(peak, fabsf(rig.out[i].l));
    }
    minimum = fminf(minimum, peak);
  }
  CHECK(minimum < 0.05f);  // the dip
  const float k = kHalfPower * 1.5f + (2.0f * kHalfPower + 2.0f) / 4.0f;
  CHECK(rig.Error(k, k) < 1e-4f);  // now parallel
}

TEST(engine, modulation_adds_depth) {
  Rig rig;
  Preset p = rig.Init();
  SetGainSlot(&p, SLOT_DELAY, 0.5f, 1.0f, true);  // value 0.25
  p.slot[SLOT_DELAY].mod[0].source = MOD_CV1;
  p.slot[SLOT_DELAY].mod[0].depth = 50;
  rig.Apply(p);
  rig.mods.value[MOD_CV1] = 0.5f;  // +2 V
  rig.Blocks(4, 0.3f);
  CHECK_NEAR(rig.engine.value(SLOT_DELAY, 0), 0.5f, 1e-4);
  CHECK(rig.Error(1.0f, 1.0f) < 1e-4f);
  rig.mods.value[MOD_CV1] = 2.0f;  // clamps at 1
  rig.Blocks(1, 0.3f);
  CHECK_NEAR(rig.engine.value(SLOT_DELAY, 0), 1.0f, 1e-6);
}

TEST(engine, send_gate_inverts_with_hysteresis) {
  Rig rig;
  Preset p = rig.Init();
  p.slot[SLOT_REVERB].send_gate = MOD_CV2;
  rig.Apply(p);
  rig.Blocks(1, 0.1f);
  CHECK(!rig.engine.send_active(SLOT_REVERB));
  rig.mods.value[MOD_CV2] = 0.5f;
  rig.Blocks(1, 0.1f);
  CHECK(rig.engine.send_active(SLOT_REVERB));
  rig.mods.value[MOD_CV2] = 0.25f;  // between the thresholds: stays open
  rig.Blocks(1, 0.1f);
  CHECK(rig.engine.send_active(SLOT_REVERB));
  rig.mods.value[MOD_CV2] = 0.1f;
  rig.Blocks(1, 0.1f);
  CHECK(!rig.engine.send_active(SLOT_REVERB));
  rig.engine.ToggleSend(SLOT_REVERB);  // button on, gate closed: on
  rig.Blocks(1, 0.1f);
  CHECK(rig.engine.send_active(SLOT_REVERB));
  rig.mods.value[MOD_CV2] = 0.5f;      // button on, gate open: off
  rig.Blocks(1, 0.1f);
  CHECK(!rig.engine.send_active(SLOT_REVERB));
}

TEST(engine, odd_sizes_and_loud_input_stay_bounded) {
  Rig rig;
  Preset p = rig.Init();
  p.algorithm = ALGORITHM_PARALLEL;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    SetGainSlot(&p, s, 2.0f, 1.0f, true);
  }
  rig.Apply(p);
  Frame in[77];
  Frame out[77];
  uint32_t noise = 7;
  for (int b = 0; b < 50; ++b) {
    for (int i = 0; i < 77; ++i) {
      in[i].l = 4.0f * test::Noise(&noise);
      in[i].r = 4.0f * test::Noise(&noise);
    }
    rig.engine.Process(rig.mods, rig.tempo, in, out, 77);
    for (int i = 0; i < 77; ++i) {
      CHECK(fabsf(out[i].l) <= 1.0f && fabsf(out[i].r) <= 1.0f);
    }
  }
}

TEST(engine, soft_limit) {
  CHECK(SoftLimit(0.5f) == 0.5f);
  CHECK(SoftLimit(-0.75f) == -0.75f);
  float previous = 0.0f;
  bool monotonic = true;
  bool bounded = true;
  for (float x = 0.0f; x < 40.0f; x += 0.01f) {
    const float y = SoftLimit(x);
    monotonic = monotonic && y >= previous;
    bounded = bounded && y < 1.0f && SoftLimit(-x) == -y;
    previous = y;
  }
  CHECK(monotonic);
  CHECK(bounded);
  CHECK_NEAR(SoftLimit(0.7501f) - SoftLimit(0.75f), 0.0001f, 1e-6);  // slope 1 at the knee
  CHECK(SoftLimit(nanf("")) == 0.0f);
  CHECK(SoftLimit(INFINITY) == 1.0f);
}

TEST(preset, layout_seal_and_sanitize) {
  test::TestMemory memory(8u << 20, 256u << 10);
  CHECK(InitBlocks(memory.memory()));
  Preset p;
  InitPreset(&p);
  CHECK(PresetValid(p));
  CHECK(!strcmp(p.name, "INIT"));
  p.wet = 1234;
  CHECK(!PresetValid(p));
  SealPreset(&p);
  CHECK(PresetValid(p));
  // Sync bits follow PARAM_SYNC.
  const BlockInfo& info = GetBlock(SLOT_DELAY, 0)->info();
  for (int i = 0; i < info.num_params; ++i) {
    const bool sync = info.params[i].flags & PARAM_SYNC;
    CHECK(bool((p.slot[SLOT_DELAY].sync_mask >> i) & 1) == sync);
  }
  // Garbage in, every index in range out.
  memset(&p, 0xff, sizeof(p));
  SanitizePreset(&p);
  CHECK(p.algorithm < NUM_ALGORITHMS);
  CHECK(p.tempo == 3000);
  CHECK(p.name[kPresetNameLength] == '\0');
  for (int s = 0; s < NUM_SLOTS; ++s) {
    CHECK(p.slot[s].type < NumBlockTypes(s));
    CHECK(p.slot[s].send <= 1);
    CHECK(p.slot[s].send_gate < NUM_MOD_SOURCES);
    for (int i = 0; i < kNumSlotValues; ++i) {
      CHECK(p.slot[s].mod[i].source < NUM_MOD_SOURCES);
      CHECK(p.slot[s].mod[i].depth >= -100 && p.slot[s].mod[i].depth <= 100);
    }
  }
  CHECK(p.lfo[0].shape < NUM_LFO_SHAPES && p.lfo[1].shape < NUM_LFO_SHAPES);
}

TEST(params, formatting) {
  char text[16];
  FormatSeconds(text, sizeof(text), 0.0045f);
  CHECK(!strcmp(text, "4.5ms"));
  FormatSeconds(text, sizeof(text), 0.35f);
  CHECK(!strcmp(text, "350ms"));
  FormatSeconds(text, sizeof(text), 1.25f);
  CHECK(!strcmp(text, "1.25s"));
  FormatSeconds(text, sizeof(text), 12.5f);
  CHECK(!strcmp(text, "12.5s"));
  FormatHz(text, sizeof(text), 0.25f);
  CHECK(!strcmp(text, "0.25Hz"));
  FormatHz(text, sizeof(text), 1234.0f);
  CHECK(!strcmp(text, "1.2kHz"));
  FormatSemitones(text, sizeof(text), 7.0f, false);
  CHECK(!strcmp(text, "+7st"));
  FormatSemitones(text, sizeof(text), -12.0f, false);
  CHECK(!strcmp(text, "-12st"));
  FormatSemitones(text, sizeof(text), 0.0f, false);
  CHECK(!strcmp(text, "0st"));
  FormatPercent(text, sizeof(text), 0.625f);
  CHECK(!strcmp(text, "63%"));
  FormatBipolarPercent(text, sizeof(text), 1.0f);
  CHECK(!strcmp(text, "+100%"));
  FormatDecibels(text, sizeof(text), -6.0f);
  CHECK(!strcmp(text, "-6.0dB"));
  FormatNumber(text, 4, 12345.0f, 0, false, "");
  CHECK(!strcmp(text, "123"));  // truncated to the buffer
  FormatNoteValue(text, sizeof(text), NoteValueIndex(1.0f));
  CHECK(!strcmp(text, "4 BAR"));
  CHECK_NEAR(SyncedSeconds(StepValue(8, kNumNoteValues), 0.5f), 0.25f, 1e-6);  // 1/8 at 120
  CHECK_NEAR(SyncedHz(1.0f, 0.5f), 32.0f, 1e-3);  // 1/64 at 120 BPM
  CHECK_NEAR(ExpUnmap(ExpMap(0.3f, 0.01f, 2.0f), 0.01f, 2.0f), 0.3f, 1e-5);
}
