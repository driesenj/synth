// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the real blocks in the real engine. Every block type
// in its slot under every algorithm, parameters jumping, a loud input: no
// faults, nothing non-finite, the output bounded; and every block fits the
// arenas main.cc gives them. Also a rough host-side cost per block (only
// relative: an x86 core is not a Cortex-M7).

#include <math.h>
#include <string.h>
#include <time.h>

#include "check.h"
#include "test_support.h"

#include "engine/engine.h"
#include "engine/preset.h"
#include "engine/registry.h"

using namespace sidefx;

namespace {

// The sizes main.cc gives the arenas.
const size_t kInternalArena = 200u << 10;
const size_t kExternalArena = 56u << 20;

struct Signal {
  uint32_t noise;
  float phase[3];
  int sample;

  Signal() : noise(99), sample(0) {
    phase[0] = phase[1] = phase[2] = 0.0f;
  }

  // Bursts of noise over a minor chord, now and then a loud hit.
  Frame Next() {
    static const float kHz[3] = { 110.0f, 130.81f, 164.81f };
    float s = 0.0f;
    for (int k = 0; k < 3; ++k) {
      phase[k] += kHz[k] / kSampleRate;
      if (phase[k] >= 1.0f) {
        phase[k] -= 1.0f;
      }
      s += 0.2f * sinf(6.2831853f * phase[k]);
    }
    const bool burst = (sample / 4800) % 5 == 0;
    const bool hit = sample % 96000 < 200;
    ++sample;
    const float n = test::Noise(&noise);
    const float l = s + (burst ? 0.4f * n : 0.0f) + (hit ? 3.5f * n : 0.0f);
    const float r = s * 0.9f + (burst ? 0.4f * test::Noise(&noise) : 0.0f);
    return MakeFrame(l, r);
  }
};

void RandomizeSlot(Preset* p, int slot, uint32_t* state) {
  const Block* block = GetBlock(slot, p->slot[slot].type);
  const int n = block->info().num_params;
  for (int i = 0; i < n; ++i) {
    const float u = 0.5f + 0.5f * test::Noise(state);
    p->slot[slot].value[i] = PresetRaw(u);
  }
  p->slot[slot].value[kMixValue] = PresetRaw(0.3f + 0.7f * (0.5f + 0.5f * test::Noise(state)));
  p->slot[slot].sync_mask = uint16_t(*state >> 16);
}

}  // namespace

TEST(integration, blocks_fit_the_arenas) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  CHECK(InitBlocks(memory.memory()));
  CHECK(!memory.internal().failed());
  CHECK(!memory.external().failed());
  test::Note("internal arena: %zu of %zu bytes, external: %zu of %zu",
             memory.internal().used(), memory.internal().size(),
             memory.external().used(), memory.external().size());
  int types = 0;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    types += NumBlockTypes(s);
    for (int t = 0; t < NumBlockTypes(s); ++t) {
      const BlockInfo& info = GetBlock(s, t)->info();
      CHECK(info.num_params > 0 && info.num_params <= kMaxBlockParams);
      CHECK(strlen(info.name) <= 10);
      CHECK(strlen(info.short_name) <= 5);
      for (int i = 0; i < info.num_params; ++i) {
        CHECK(strlen(info.params[i].name) <= 8);
        CHECK(info.params[i].default_value >= 0.0f &&
              info.params[i].default_value <= 1.0f);
        if (info.params[i].flags & PARAM_STEPPED) {
          CHECK(info.params[i].num_steps >= 2);
        }
      }
    }
  }
  CHECK(types == 17);
}

TEST(integration, every_type_in_every_algorithm) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  Engine engine;
  CHECK(engine.Init(memory.memory()));
  ModValues mods;
  memset(&mods, 0, sizeof(mods));
  TempoState tempo = test::Tempo120();
  Signal signal;
  uint32_t state = 4242;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  int max_types = 0;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    max_types = NumBlockTypes(s) > max_types ? NumBlockTypes(s) : max_types;
  }
  for (int round = 0; round < max_types; ++round) {
    for (int a = 0; a < NUM_ALGORITHMS; ++a) {
      Preset p;
      InitPreset(&p);
      p.algorithm = uint8_t(a);
      for (int s = 0; s < NUM_SLOTS; ++s) {
        InitSlot(&p, s, round % NumBlockTypes(s));
        p.slot[s].send = 1;
        RandomizeSlot(&p, s, &state);
      }
      engine.ApplyPresetNow(p);
      int faults_before[NUM_SLOTS];
      for (int s = 0; s < NUM_SLOTS; ++s) {
        faults_before[s] = engine.faults(s);
      }
      bool finite = true;
      float peak = 0.0f;
      for (int b = 0; b < 1500; ++b) {  // 1 s
        if (b % 50 == 0) {
          for (int s = 0; s < NUM_SLOTS; ++s) {
            RandomizeSlot(engine.mutable_preset(), s, &state);
          }
        }
        if (b == 700) {
          engine.ToggleSend(SLOT_DELAY);
          engine.ToggleSend(SLOT_TEXTURE);
        }
        tempo.bar_phase = fmodf(tempo.bar_phase + kBlockSize * tempo.bar_increment, 1.0f);
        for (size_t i = 0; i < kBlockSize; ++i) {
          in[i] = signal.Next();
        }
        engine.Process(mods, tempo, in, out, kBlockSize);
        for (size_t i = 0; i < kBlockSize; ++i) {
          finite = finite && test::Finite(out[i]);
          peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
        }
      }
      CHECK(finite);
      CHECK(peak <= 1.0f);
      for (int s = 0; s < NUM_SLOTS; ++s) {
        const int faults = engine.faults(s) - faults_before[s];
        if (faults) {
          printf("round %d algorithm %d: %s faulted %d times\n", round, a,
                 GetBlock(s, p.slot[s].type)->info().name, faults);
        }
        CHECK(faults == 0);
      }
    }
  }
}

TEST(integration, block_cost_on_the_host) {
  test::TestMemory memory(kExternalArena, kInternalArena);
  CHECK(InitBlocks(memory.memory()));
  TempoState tempo = test::Tempo120();
  Signal signal;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  float params[kNumSlotValues];
  const int kBlocks = 3000;  // 2 s
  double reference_ns = 0.0;
  {
    // A reference: 32 one-pole lowpasses per sample, about 100 float ops.
    float state[32] = { 0 };
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    float sink = 0.0f;
    for (int b = 0; b < kBlocks; ++b) {
      for (size_t i = 0; i < kBlockSize; ++i) {
        const float x = signal.Next().l;
        for (int k = 0; k < 32; ++k) {
          state[k] += 0.01f * (x - state[k]);
          sink += state[k];
        }
      }
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    reference_ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
    CHECK(sink == sink);
  }
  for (int s = 0; s < NUM_SLOTS; ++s) {
    for (int t = 0; t < NumBlockTypes(s); ++t) {
      Block* block = GetBlock(s, t);
      const BlockInfo& info = block->info();
      block->Reset();
      ProcessContext context = test::Context(tempo, 0xffff);
      // The expensive end: everything up.
      for (int i = 0; i < info.num_params; ++i) {
        params[i] = (info.params[i].flags & PARAM_STEPPED) ? 1.0f : 0.8f;
      }
      struct timespec t0, t1;
      clock_gettime(CLOCK_MONOTONIC, &t0);
      for (int b = 0; b < kBlocks; ++b) {
        for (size_t i = 0; i < kBlockSize; ++i) {
          in[i] = signal.Next();
        }
        block->Process(context, params, in, out, kBlockSize);
      }
      clock_gettime(CLOCK_MONOTONIC, &t1);
      const double ns = (t1.tv_sec - t0.tv_sec) * 1e9 + (t1.tv_nsec - t0.tv_nsec);
      test::Note("%-10s %6.2fx the reference loop (%.0f ns per sample on this host)",
                 info.name, ns / reference_ns, ns / (kBlocks * kBlockSize));
      CHECK(test::Finite(out[0]));
    }
  }
}
