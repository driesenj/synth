// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: BAND DELAY.

#include <math.h>
#include <string.h>

#include "check.h"
#include "test_support.h"
#include "fx/band_delay.h"

namespace {

using sidefx::BandDelay;
using sidefx::Frame;
using sidefx::ProcessContext;

const float kFs = 48014.32f;
const size_t kB = sidefx::kBlockSize;

struct Rig {
  test::TestMemory memory;
  BandDelay* block;
  bool ok;
  float params[BandDelay::NUM_PARAMS];

  Rig() : memory(9u << 20, 32u << 10) {
    block = memory.memory()->internal->Create<BandDelay>();
    ok = block && block->Init(memory.memory());
    Defaults();
  }
  void Defaults() {
    const sidefx::BlockInfo& info = block->info();
    for (int i = 0; i < info.num_params; ++i) {
      params[i] = info.params[i].default_value;
    }
  }
  void Run(const ProcessContext& c, const Frame* in, Frame* out) {
    block->Process(c, params, in, out, kB);
  }
};

float TimeValue(float seconds) {
  return sidefx::ExpUnmap(seconds, 0.01f, 4.0f);
}

// The first sample (from `from`) where either channel's |output| passes
// `threshold`, for an impulse at sample 0. -1 when none.
struct Onsets {
  long left;
  long right;
};

Onsets ImpulseOnsets(Rig* rig, const ProcessContext& c, size_t samples,
                     float threshold) {
  Onsets o = { -1, -1 };
  Frame in[kB];
  Frame out[kB];
  for (size_t n = 0; n < samples; n += kB) {
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = in[i].r = (n + i == 0) ? 1.0f : 0.0f;
    }
    rig->Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      if (o.left < 0 && fabsf(out[i].l) > threshold) {
        o.left = long(n + i);
      }
      if (o.right < 0 && fabsf(out[i].r) > threshold) {
        o.right = long(n + i);
      }
    }
  }
  return o;
}

bool Near(long sample, float seconds, float tolerance_seconds) {
  return sample >= 0 &&
      fabsf(float(sample) / kFs - seconds) <= tolerance_seconds;
}

}  // namespace

TEST(band_delay, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  CHECK(sizeof(BandDelay) < 8192);
  CHECK(rig.memory.external().used() <= (8u << 20) + 256);
  test::Note("object %u bytes, external %u bytes",
             unsigned(sizeof(BandDelay)),
             unsigned(rig.memory.external().used()));
  const sidefx::BlockInfo& info = rig.block->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params <= 7);
  for (int i = 0; i < info.num_params; ++i) {
    CHECK(strlen(info.params[i].name) <= 8);
  }

  ProcessContext c = test::Context(test::Tempo120(), 0);
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  bool silent = true;
  rig.params[BandDelay::PARAM_FEEDBACK] = 1.0f;
  for (int b = 0; b < 3 * 1500; ++b) {
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);

  // Noise in, Reset(), then silence again at once.
  uint32_t seed = 1;
  for (int b = 0; b < 1000; ++b) {
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Run(c, in, out);
  }
  rig.block->Reset();
  memset(in, 0, sizeof(in));
  silent = true;
  for (int b = 0; b < 1500; ++b) {
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);
}

TEST(band_delay, stability) {
  Rig rig;
  CHECK(rig.ok);
  sidefx::TempoState tempo = test::Tempo120();
  Frame in[kB];
  Frame out[kB];
  uint32_t seed = 7;
  sidefx::dsp::Random random;
  float peak = 0.0f;
  bool finite = true;

  // 20 s, every parameter and the sync bits randomised every block.
  const int blocks = int(20.0f * kFs / float(kB));
  for (int b = 0; b < blocks; ++b) {
    for (int p = 0; p < BandDelay::NUM_PARAMS; ++p) {
      rig.params[p] = random.Uniform();
    }
    ProcessContext c = test::Context(tempo, uint16_t(random.Next() & 0x7f));
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      finite = finite && test::Finite(out[i]);
      peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
    }
  }
  CHECK(finite);
  CHECK(peak < 4.0f);
  test::Note("random: peak %.3f", peak);

  // Every parameter at 0, then at 1 (feedback past 100 %), with noise at
  // +-1 and then +-4.
  for (int setting = 0; setting < 2; ++setting) {
    for (int level = 1; level <= 4; level *= 4) {
      rig.block->Reset();
      for (int p = 0; p < BandDelay::NUM_PARAMS; ++p) {
        rig.params[p] = float(setting);
      }
      ProcessContext c = test::Context(tempo, 0);
      float peak_here = 0.0f;
      for (int b = 0; b < int(10.0f * kFs / float(kB)); ++b) {
        for (size_t i = 0; i < kB; ++i) {
          in[i].l = float(level) * test::Noise(&seed);
          in[i].r = float(level) * test::Noise(&seed);
        }
        rig.Run(c, in, out);
        for (size_t i = 0; i < kB; ++i) {
          finite = finite && test::Finite(out[i]);
          peak_here = fmaxf(peak_here,
                            fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
        }
      }
      CHECK(finite);
      CHECK(peak_here < 4.0f);
      test::Note("all %d, input +-%d: peak %.3f", setting, level, peak_here);
    }
  }
}

TEST(band_delay, echo_time) {
  Rig rig;
  CHECK(rig.ok);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[BandDelay::PARAM_TIME] = TimeValue(0.25f);
  rig.params[BandDelay::PARAM_SPREAD] = 0.5f;  // every band at TIME
  rig.params[BandDelay::PARAM_FEEDBACK] = 0.0f;
  rig.params[BandDelay::PARAM_WIDTH] = 0.0f;
  Onsets o = ImpulseOnsets(&rig, c, size_t(0.4f * kFs), 1e-6f);
  test::Note("onsets %ld %ld (expected %.0f)", o.left, o.right, 0.25f * kFs);
  CHECK(Near(o.left, 0.25f, 0.001f));
  CHECK(Near(o.right, 0.25f, 0.001f));

  // Nothing before the echo, and a 2 s time works too.
  rig.block->Reset();
  rig.params[BandDelay::PARAM_TIME] = TimeValue(2.0f);
  o = ImpulseOnsets(&rig, c, size_t(2.2f * kFs), 1e-6f);
  CHECK(Near(o.left, 2.0f, 0.001f));
}

TEST(band_delay, spread_directions) {
  // WIDTH 1: bands 0 and 2 on the left, 1 and 3 on the right. SPREAD +1
  // gives ratios 1/2, 2^-1/3, 2^1/3, 2 low to high; -1 the reverse.
  const float t = 0.4f;
  for (int direction = 0; direction < 2; ++direction) {
    Rig rig;
    CHECK(rig.ok);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    rig.params[BandDelay::PARAM_TIME] = TimeValue(t);
    rig.params[BandDelay::PARAM_SPREAD] = direction ? 0.0f : 1.0f;
    rig.params[BandDelay::PARAM_FEEDBACK] = 0.0f;
    rig.params[BandDelay::PARAM_WIDTH] = 1.0f;
    Onsets o = ImpulseOnsets(&rig, c, size_t(0.5f * kFs), 1e-6f);
    const float early = 0.5f * t;
    const float late = t * exp2f(-1.0f / 3.0f);
    test::Note("spread %s: onsets L %.4fs R %.4fs", direction ? "-1" : "+1",
               float(o.left) / kFs, float(o.right) / kFs);
    CHECK(Near(o.left, direction ? late : early, 0.001f));
    CHECK(Near(o.right, direction ? early : late, 0.001f));
    // The longest band: 2 x TIME.
    const int longest = direction ? 0 : 3;
    CHECK_NEAR(rig.block->band_delay_target(longest), 2.0f * t * kFs, 2.0);
  }
}

TEST(band_delay, bands_split_frequency) {
  // A sine at band 0's centre comes out mostly on the left (WIDTH 1), one
  // at band 1's on the right, with Q high.
  Rig rig;
  CHECK(rig.ok);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[BandDelay::PARAM_TIME] = TimeValue(0.05f);
  rig.params[BandDelay::PARAM_FEEDBACK] = 0.0f;
  rig.params[BandDelay::PARAM_FREQ] = sidefx::ExpUnmap(1000.0f, 100.0f,
                                                       8000.0f);
  rig.params[BandDelay::PARAM_Q] = 0.85f;
  rig.params[BandDelay::PARAM_TILT] = 0.5f;
  rig.params[BandDelay::PARAM_WIDTH] = 1.0f;
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  rig.Run(c, in, out);  // sets the band centres
  for (int band = 0; band < 2; ++band) {
    rig.block->Reset();
    rig.Run(c, in, out);
    const float f = rig.block->band_frequency(band);
    double el = 0.0, er = 0.0;
    double phase = 0.0;
    for (int b = 0; b < int(0.5f * kFs / float(kB)); ++b) {
      for (size_t i = 0; i < kB; ++i) {
        in[i].l = in[i].r = 0.5f * sinf(float(phase));
        phase += 2.0 * 3.14159265358979 * double(f) / double(kFs);
      }
      rig.Run(c, in, out);
      if (b > int(0.2f * kFs / float(kB))) {
        for (size_t i = 0; i < kB; ++i) {
          el += double(out[i].l) * out[i].l;
          er += double(out[i].r) * out[i].r;
        }
      }
    }
    test::Note("band %d at %.0f Hz: L %.4f R %.4f", band, f, el, er);
    if (band == 0) {
      CHECK(el > 10.0 * er);
    } else {
      CHECK(er > 10.0 * el);
    }
  }
}

TEST(band_delay, feedback_repeats) {
  // FEEDBACK 0.6: a second echo at 2 TIME, quieter than the first, and a
  // third quieter still.
  Rig rig;
  CHECK(rig.ok);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  const float t = 0.2f;
  rig.params[BandDelay::PARAM_TIME] = TimeValue(t);
  rig.params[BandDelay::PARAM_SPREAD] = 0.5f;
  rig.params[BandDelay::PARAM_FEEDBACK] = 0.6f;
  rig.params[BandDelay::PARAM_Q] = 0.2f;
  rig.params[BandDelay::PARAM_TILT] = 0.5f;
  Frame in[kB];
  Frame out[kB];
  double energy[4] = { 0.0, 0.0, 0.0, 0.0 };
  for (size_t n = 0; n < size_t(0.9f * kFs); n += kB) {
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = in[i].r = (n + i == 0) ? 1.0f : 0.0f;
    }
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      const int window = int(float(n + i) / (t * kFs) + 0.25f);  // echo k
      if (window < 4) {
        energy[window] += double(out[i].l) * out[i].l;
      }
    }
  }
  test::Note("echo energies %.3g %.3g %.3g %.3g", energy[0], energy[1],
             energy[2], energy[3]);
  CHECK(energy[0] < 1e-12);
  CHECK(energy[1] > 0.0);
  CHECK(energy[2] > 0.02 * energy[1]);
  CHECK(energy[2] < energy[1]);
  CHECK(energy[3] < energy[2]);
}

TEST(band_delay, no_clicks) {
  Rig rig;
  CHECK(rig.ok);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[BandDelay::PARAM_TIME] = TimeValue(0.3f);
  rig.params[BandDelay::PARAM_FEEDBACK] = 0.3f;
  rig.params[BandDelay::PARAM_FREQ] = sidefx::ExpUnmap(667.0f, 100.0f,
                                                       8000.0f);
  rig.params[BandDelay::PARAM_Q] = 0.0f;
  rig.params[BandDelay::PARAM_WIDTH] = 0.0f;
  Frame in[kB];
  Frame out[kB];
  double phase = 0.0;
  float last = 0.0f;
  // Phases: steady, big jump (crossfade), steady, small jump (glide),
  // steady, jump back up.
  const float times[] = { 0.3f, 0.05f, 0.05f, 0.058f, 0.058f, 1.2f };
  float steady_step = 0.0f;
  float jump_step = 0.0f;
  for (int phase_index = 0; phase_index < 6; ++phase_index) {
    rig.params[BandDelay::PARAM_TIME] = TimeValue(times[phase_index]);
    const bool steady = phase_index == 0 || phase_index == 2 ||
        phase_index == 4;
    const int blocks = int(2.5f * kFs / float(kB));
    for (int b = 0; b < blocks; ++b) {
      for (size_t i = 0; i < kB; ++i) {
        in[i].l = in[i].r = 0.5f * sinf(float(phase));
        phase += 2.0 * 3.14159265358979 * 440.0 / double(kFs);
      }
      rig.Run(c, in, out);
      for (size_t i = 0; i < kB; ++i) {
        const float step = fabsf(out[i].l - last);
        last = out[i].l;
        if (steady && b > blocks / 2) {
          steady_step = fmaxf(steady_step, step);
        } else if (!steady) {
          jump_step = fmaxf(jump_step, step);
        }
      }
    }
  }
  test::Note("largest step: steady %.4f, during jumps %.4f", steady_step,
             jump_step);
  CHECK(steady_step > 0.001f);
  CHECK(jump_step < 3.0f * steady_step);
}

TEST(band_delay, format) {
  Rig rig;
  CHECK(rig.ok);
  const float values[] = { 0.0f, 0.5f, 1.0f };
  for (int synced = 0; synced < 2; ++synced) {
    ProcessContext c = test::Context(test::Tempo120(), synced ? 0x7f : 0);
    for (int p = 0; p < BandDelay::NUM_PARAMS; ++p) {
      for (int v = 0; v < 3; ++v) {
        char text[32];
        memset(text, 0, sizeof(text));
        rig.block->Format(p, values[v], c, text, sizeof(text));
        CHECK(strlen(text) > 0);
        CHECK(strlen(text) <= 10);
        test::Note("param %d value %.1f synced %d: '%s'", p, values[v],
                   synced, text);
      }
    }
  }
  char text[16];
  ProcessContext c = test::Context(test::Tempo120(), 1);
  rig.block->Format(BandDelay::PARAM_TIME, sidefx::StepValue(11, 20), c,
                    text, sizeof(text));
  CHECK(!strcmp(text, "1/4"));
}

TEST(band_delay, synced_time_follows_tempo) {
  Rig rig;
  CHECK(rig.ok);
  sidefx::TempoState tempo = test::Tempo120();
  rig.params[BandDelay::PARAM_TIME] = sidefx::StepValue(11, 20);  // 1/4
  rig.params[BandDelay::PARAM_SPREAD] = 0.5f;
  rig.params[BandDelay::PARAM_FEEDBACK] = 0.0f;
  const float beats[] = { 0.5f, 0.375f, 0.3f };
  for (int i = 0; i < 3; ++i) {
    rig.block->Reset();
    tempo.beat_seconds = beats[i];
    ProcessContext c = test::Context(tempo, 1);
    Onsets o = ImpulseOnsets(&rig, c, size_t((beats[i] + 0.05f) * kFs),
                             1e-6f);
    test::Note("beat %.3fs: echo at %.4fs", beats[i], float(o.left) / kFs);
    CHECK(Near(o.left, beats[i], 0.001f));
    CHECK_NEAR(rig.block->band_delay_target(1), beats[i] * kFs, 1.0);
  }

  // Synced, SPREAD +1 snaps the ratios to rhythmic ones: band 2 at 4/3.
  tempo.beat_seconds = 0.5f;
  ProcessContext c = test::Context(tempo, 1);
  rig.params[BandDelay::PARAM_SPREAD] = 1.0f;
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  rig.Run(c, in, out);
  CHECK_NEAR(rig.block->band_delay_target(2), 0.5f * 4.0f / 3.0f * kFs, 1.0);
  CHECK_NEAR(rig.block->band_delay_target(0), 0.25f * kFs, 1.0);
}

TEST(band_delay, longest_times_fit) {
  // TIME 4 s with SPREAD +100 %: the bands at 2 s .. 8 s, the ratios kept
  // (the top band not cut short at the line's end). And synced: 1/2. at
  // 60 BPM (3 s) with the 2x ratio is 6 s.
  Rig rig;
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[BandDelay::PARAM_TIME] = 1.0f;
  rig.params[BandDelay::PARAM_SPREAD] = 1.0f;
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  rig.Run(c, in, out);
  for (int k = 0; k < BandDelay::kNumBands; ++k) {
    test::Note("band %d at %.3f s", k, rig.block->band_delay_target(k) / kFs);
  }
  CHECK(fabsf(rig.block->band_delay_target(0) / kFs - 2.0f) < 0.001f);
  CHECK(fabsf(rig.block->band_delay_target(3) / kFs - 8.0f) < 0.001f);
  CHECK(fabsf(rig.block->band_delay_target(2) / rig.block->band_delay_target(1)
              - exp2f(2.0f / 3.0f)) < 0.001f);

  Rig synced;
  sidefx::TempoState t = test::Tempo120();
  t.beat_seconds = 1.0f;
  ProcessContext s = test::Context(t, 1 << BandDelay::PARAM_TIME);
  synced.params[BandDelay::PARAM_TIME] =
      sidefx::StepValue(16, sidefx::kNumNoteValues);  // 1/2.
  synced.params[BandDelay::PARAM_SPREAD] = 1.0f;
  synced.Run(s, in, out);
  test::Note("synced 1/2. at 60 BPM: top band at %.3f s",
             synced.block->band_delay_target(3) / kFs);
  CHECK(fabsf(synced.block->band_delay_target(3) / kFs - 6.0f) < 0.001f);
}
