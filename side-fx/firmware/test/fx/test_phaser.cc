// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the PHASER block.

#include <math.h>
#include <string.h>

#include "check.h"
#include "test_support.h"

#include "engine/params.h"
#include "fx/phaser.h"

using sidefx::Frame;
using sidefx::Phaser;
using sidefx::ProcessContext;

namespace {

const float kFs = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;

struct Rig {
  test::TestMemory memory;
  Phaser* phaser;
  float params[Phaser::NUM_PARAMS];
  ProcessContext context;

  Rig() : memory(1u << 20, 64u << 10) {
    phaser = memory.memory()->internal->Create<Phaser>();
    CHECK(phaser != NULL);
    CHECK(phaser->Init(memory.memory()));
    phaser->Reset();
    const sidefx::BlockInfo& info = phaser->info();
    for (int i = 0; i < Phaser::NUM_PARAMS; ++i) {
      params[i] = info.params[i].default_value;
    }
    context = test::Context(test::Tempo120(), 0);
  }

  void Process(const Frame* in, Frame* out) {
    phaser->Process(context, params, in, out, kBlock);
    context.bar_phase += context.bar_increment * float(kBlock);
    if (context.bar_phase >= 1.0f) {
      context.bar_phase -= 1.0f;
    }
  }

  void SetTempo(float beat_seconds) {
    context.beat_seconds = beat_seconds;
    context.bar_increment = 1.0f / (4.0f * beat_seconds * kFs);
  }
};

float Stage(int stages) {
  return sidefx::StepValue(stages / 2 - 1, Phaser::kNumStageSettings);
}

// Amplitude of (dry + wet) / 2 for a sine at hz: what the engine's 50 % MIX
// would play. Measured over the last half of `seconds`.
float NotchedAmplitude(Rig* rig, float hz, float amplitude, float seconds) {
  const int blocks = int(seconds * kFs / kBlock);
  float peak = 0.0f;
  float phase = 0.0f;
  for (int b = 0; b < blocks; ++b) {
    Frame in[kBlock], out[kBlock];
    for (size_t i = 0; i < kBlock; ++i) {
      const float s = amplitude * sinf(6.2831853f * phase);
      phase += hz / kFs;
      if (phase >= 1.0f) phase -= 1.0f;
      in[i].l = in[i].r = s;
    }
    rig->Process(in, out);
    if (b >= blocks / 2) {
      for (size_t i = 0; i < kBlock; ++i) {
        const float m = fabsf(0.5f * (in[i].l + out[i].l));
        peak = m > peak ? m : peak;
      }
    }
  }
  return peak / amplitude;
}

// Amplitude of the wet signal alone for a sine at hz.
float WetAmplitude(Rig* rig, float hz, float amplitude, float seconds) {
  const int blocks = int(seconds * kFs / kBlock);
  float peak = 0.0f;
  float phase = 0.0f;
  for (int b = 0; b < blocks; ++b) {
    Frame in[kBlock], out[kBlock];
    for (size_t i = 0; i < kBlock; ++i) {
      const float s = amplitude * sinf(6.2831853f * phase);
      phase += hz / kFs;
      if (phase >= 1.0f) phase -= 1.0f;
      in[i].l = in[i].r = s;
    }
    rig->Process(in, out);
    if (b >= blocks / 2) {
      for (size_t i = 0; i < kBlock; ++i) {
        const float m = fabsf(out[i].l);
        peak = m > peak ? m : peak;
      }
    }
  }
  return peak / amplitude;
}

}  // namespace

TEST(phaser, silence) {
  Rig rig;
  CHECK(rig.memory.internal().used() < 8192);
  CHECK(rig.memory.external().used() == 0);
  test::Note("internal %u bytes", unsigned(rig.memory.internal().used()));
  Frame in[kBlock], out[kBlock];
  memset(in, 0, sizeof(in));
  bool silent = true;
  for (int b = 0; b < 2000; ++b) {
    rig.Process(in, out);
    for (size_t i = 0; i < kBlock; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);
}

TEST(phaser, stability) {
  Rig rig;
  uint32_t seed = 1;
  float peak = 0.0f;
  bool finite = true;
  const int blocks = int(20.0f * kFs / kBlock);
  for (int b = 0; b < blocks; ++b) {
    for (int p = 0; p < Phaser::NUM_PARAMS; ++p) {
      rig.params[p] = 0.5f + 0.5f * test::Noise(&seed);
    }
    rig.context.sync_mask = uint16_t(test::Noise(&seed) > 0.0f ? 1 : 0);
    Frame in[kBlock], out[kBlock];
    for (size_t i = 0; i < kBlock; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Process(in, out);
    for (size_t i = 0; i < kBlock; ++i) {
      finite = finite && test::Finite(out[i]);
      peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
    }
  }
  // Every parameter at 0, then at 1 (feedback at +max), with +-1 and +-4.
  for (int extreme = 0; extreme < 2; ++extreme) {
    for (int loud = 0; loud < 2; ++loud) {
      for (int p = 0; p < Phaser::NUM_PARAMS; ++p) {
        rig.params[p] = float(extreme);
      }
      for (int b = 0; b < int(5.0f * kFs / kBlock); ++b) {
        Frame in[kBlock], out[kBlock];
        for (size_t i = 0; i < kBlock; ++i) {
          in[i].l = (loud ? 4.0f : 1.0f) * test::Noise(&seed);
          in[i].r = (loud ? 4.0f : 1.0f) * test::Noise(&seed);
        }
        rig.Process(in, out);
        for (size_t i = 0; i < kBlock; ++i) {
          finite = finite && test::Finite(out[i]);
          if (!loud) {
            peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
          } else {
            CHECK(fabsf(out[i].l) < 4.0f && fabsf(out[i].r) < 4.0f);
          }
        }
      }
    }
  }
  test::Note("peak %.3f", peak);
  CHECK(finite);
  CHECK(peak < 4.0f);
}

TEST(phaser, static_notch) {
  // Two stages, no sweep, no feedback: one notch at CENTER.
  Rig rig;
  rig.params[Phaser::PARAM_DEPTH] = 0.0f;
  rig.params[Phaser::PARAM_STAGES] = Stage(2);
  rig.params[Phaser::PARAM_FEEDBACK] = 0.5f;
  rig.params[Phaser::PARAM_CENTER] = sidefx::ExpUnmap(1000.0f, 100.0f,
                                                      4000.0f);
  const float at = NotchedAmplitude(&rig, 1000.0f, 0.5f, 0.5f);
  const float below = NotchedAmplitude(&rig, 120.0f, 0.5f, 0.5f);
  const float above = NotchedAmplitude(&rig, 9000.0f, 0.5f, 0.5f);
  test::Note("1 kHz %.4f, 120 Hz %.3f, 9 kHz %.3f", at, below, above);
  CHECK(at < 0.02f);
  CHECK(below > 0.95f);
  CHECK(above > 0.85f);

  // Four stages: two notches, at fc tan(pi/8) and fc tan(3 pi/8) (where
  // each stage turns 45 and 135 degrees), and none at fc.
  rig.params[Phaser::PARAM_STAGES] = Stage(4);
  const float n1 = NotchedAmplitude(&rig, 1000.0f * 0.41421356f, 0.5f, 0.5f);
  const float n2 = NotchedAmplitude(&rig, 1000.0f * 2.4142136f, 0.5f, 0.5f);
  const float peak = NotchedAmplitude(&rig, 1000.0f, 0.5f, 0.5f);
  test::Note("4 stages: %.4f %.4f, fc %.3f", n1, n2, peak);
  CHECK(n1 < 0.03f);
  CHECK(n2 < 0.03f);
  CHECK(peak > 0.95f);
}

TEST(phaser, moving_notches) {
  // A 4-octave sweep at 1 Hz: a sine at the centre goes in and out of the
  // notch, and the corner covers 16:1.
  Rig rig;
  rig.params[Phaser::PARAM_DEPTH] = 1.0f;
  rig.params[Phaser::PARAM_STAGES] = Stage(2);
  rig.params[Phaser::PARAM_FEEDBACK] = 0.5f;
  rig.params[Phaser::PARAM_RATE] = sidefx::ExpUnmap(1.0f, 0.01f, 10.0f);
  rig.params[Phaser::PARAM_CENTER] = sidefx::ExpUnmap(1000.0f, 100.0f,
                                                      4000.0f);
  float lo = 1e9f, hi = 0.0f;
  float env_lo = 1e9f, env_hi = 0.0f;
  float phase = 0.0f;
  const int window = 8;  // blocks: 5.3 ms
  for (int w = 0; w < int(2.0f * kFs / kBlock) / window; ++w) {
    float peak = 0.0f;
    for (int b = 0; b < window; ++b) {
      Frame in[kBlock], out[kBlock];
      for (size_t i = 0; i < kBlock; ++i) {
        in[i].l = in[i].r = 0.5f * sinf(6.2831853f * phase);
        phase += 1000.0f / kFs;
        if (phase >= 1.0f) phase -= 1.0f;
      }
      rig.Process(in, out);
      for (size_t i = 0; i < kBlock; ++i) {
        peak = fmaxf(peak, fabsf(0.5f * (in[i].l + out[i].l)) / 0.5f);
      }
      lo = fminf(lo, rig.phaser->corner_hz(0));
      hi = fmaxf(hi, rig.phaser->corner_hz(0));
    }
    env_lo = fminf(env_lo, peak);
    env_hi = fmaxf(env_hi, peak);
  }
  test::Note("corner %.1f..%.1f Hz, envelope %.3f..%.3f", lo, hi, env_lo,
             env_hi);
  CHECK(hi / lo > 14.0f && hi / lo < 17.0f);
  CHECK(fabsf(sqrtf(lo * hi) - 1000.0f) < 30.0f);
  CHECK(env_lo < 0.1f);
  CHECK(env_hi > 0.8f);

  // SPREAD 180 degrees: the channels sweep in opposition.
  rig.params[Phaser::PARAM_SPREAD] = 1.0f;
  float worst = 0.0f;
  Frame in[kBlock], out[kBlock];
  memset(in, 0, sizeof(in));
  for (int b = 0; b < 2000; ++b) {
    rig.Process(in, out);
    if (b > 100) {
      const float l = log2f(rig.phaser->corner_hz(0) / 1000.0f);
      const float r = log2f(rig.phaser->corner_hz(1) / 1000.0f);
      worst = fmaxf(worst, fabsf(l + r));
    }
  }
  test::Note("spread: worst log2 asymmetry %.4f", worst);
  CHECK(worst < 0.01f);

  // RANDOM: it still moves, smoothly.
  rig.params[Phaser::PARAM_SHAPE] = 1.0f;
  rig.params[Phaser::PARAM_SPREAD] = 0.0f;
  lo = 1e9f;
  hi = 0.0f;
  float last = 0.0f, largest_step = 0.0f;
  for (int b = 0; b < int(10.0f * kFs / kBlock); ++b) {
    rig.Process(in, out);
    const float o = log2f(rig.phaser->corner_hz(0));
    if (b > 100) {
      largest_step = fmaxf(largest_step, fabsf(o - last));
      lo = fminf(lo, o);
      hi = fmaxf(hi, o);
    }
    last = o;
  }
  test::Note("random: %.2f octaves, largest step %.4f octave per block",
             hi - lo, largest_step);
  CHECK(hi - lo > 1.5f);
  // 1 Hz, +-2 octaves: a smoothstep segment moves at most 1.5 * 4 octaves
  // per cycle, 0.004 octave per block.
  CHECK(largest_step < 0.01f);
}

TEST(phaser, bipolar_feedback) {
  // Four stages turn 360 degrees at the corner: positive feedback rings
  // there, negative feedback cancels.
  Rig rig;
  rig.params[Phaser::PARAM_DEPTH] = 0.0f;
  rig.params[Phaser::PARAM_STAGES] = Stage(4);
  rig.params[Phaser::PARAM_CENTER] = sidefx::ExpUnmap(1000.0f, 100.0f,
                                                      4000.0f);
  rig.params[Phaser::PARAM_FEEDBACK] = 1.0f;
  const float plus = WetAmplitude(&rig, 1000.0f, 0.05f, 0.5f);
  rig.params[Phaser::PARAM_FEEDBACK] = 0.0f;
  const float minus = WetAmplitude(&rig, 1000.0f, 0.05f, 0.5f);
  rig.params[Phaser::PARAM_FEEDBACK] = 0.5f;
  const float neutral = WetAmplitude(&rig, 1000.0f, 0.05f, 0.5f);
  test::Note("wet gain at fc: +max %.2f, -max %.3f, 0 %.3f", plus, minus,
             neutral);
  CHECK(plus > 6.0f);
  CHECK(minus < 0.6f);
  CHECK(fabsf(neutral - 1.0f) < 0.02f);
}

TEST(phaser, no_clicks) {
  // A 220 Hz sine while CENTER, DEPTH, RATE and STAGES jump between their
  // ends every 100 ms: the largest step stays near the steady one.
  Rig rig;
  rig.params[Phaser::PARAM_FEEDBACK] = 0.5f;
  float steady = 0.0f, jumping = 0.0f;
  for (int pass = 0; pass < 3; ++pass) {
    float phase = 0.0f, last = 0.0f;
    for (int b = 0; b < int(3.0f * kFs / kBlock); ++b) {
      const int setting = (b / 150) & 1;  // 100 ms
      const int use = pass == 2 ? setting : pass;
      rig.params[Phaser::PARAM_CENTER] = use ? 1.0f : 0.0f;
      rig.params[Phaser::PARAM_DEPTH] = use ? 1.0f : 0.2f;
      rig.params[Phaser::PARAM_RATE] = use ? 1.0f : 0.3f;
      rig.params[Phaser::PARAM_STAGES] = use ? 1.0f : 0.0f;
      Frame in[kBlock], out[kBlock];
      for (size_t i = 0; i < kBlock; ++i) {
        in[i].l = in[i].r = 0.5f * sinf(6.2831853f * phase);
        phase += 220.0f / kFs;
        if (phase >= 1.0f) phase -= 1.0f;
      }
      rig.Process(in, out);
      for (size_t i = 0; i < kBlock; ++i) {
        const float step = fabsf(out[i].l - last);
        last = out[i].l;
        if (b > 300) {
          if (pass < 2) {
            steady = fmaxf(steady, step);
          } else {
            jumping = fmaxf(jumping, step);
          }
        }
      }
    }
  }
  test::Note("largest step: steady %.4f, jumping %.4f", steady, jumping);
  CHECK(jumping < 3.0f * steady);
}

TEST(phaser, format) {
  Rig rig;
  for (int sync = 0; sync < 2; ++sync) {
    rig.context.sync_mask = sync ? 0xffff : 0;
    for (int p = 0; p < Phaser::NUM_PARAMS; ++p) {
      for (int v = 0; v <= 2; ++v) {
        char text[32];
        memset(text, 'x', sizeof(text));
        rig.phaser->Format(p, 0.5f * float(v), rig.context, text, 11);
        const size_t n = strlen(text);
        test::Note("%d %.1f %s: %s", p, 0.5f * float(v),
                   sync ? "synced" : "free", text);
        CHECK(n > 0 && n <= 10);
      }
    }
  }
  char text[16];
  rig.context.sync_mask = 0;
  rig.phaser->Format(Phaser::PARAM_STAGES, 1.0f, rig.context, text, 16);
  CHECK(strcmp(text, "12") == 0);
  rig.phaser->Format(Phaser::PARAM_SHAPE, 1.0f, rig.context, text, 16);
  CHECK(strcmp(text, "RANDOM") == 0);
  rig.context.sync_mask = 1;
  const float quarter = 1.0f - sidefx::StepValue(11, sidefx::kNumNoteValues);
  rig.phaser->Format(Phaser::PARAM_RATE, quarter, rig.context, text, 16);
  CHECK(strcmp(text, "1/4") == 0);
}

TEST(phaser, synced_rate) {
  // RATE synced to 1/4: 2 cycles a second at 120 BPM, 4 at 240, locked to
  // the bar (four cycles per bar, the first at the downbeat).
  const float quarter = 1.0f - sidefx::StepValue(11, sidefx::kNumNoteValues);
  for (int t = 0; t < 2; ++t) {
    Rig rig;
    const float beat = t ? 0.25f : 0.5f;
    rig.SetTempo(beat);
    rig.context.bar_phase = 0.3f;
    rig.context.sync_mask = 1 << Phaser::PARAM_RATE;
    rig.params[Phaser::PARAM_RATE] = quarter;
    Frame in[kBlock], out[kBlock];
    memset(in, 0, sizeof(in));
    int wraps = 0;
    float last = 0.0f, worst = 0.0f;
    const int blocks = int(4.0f * kFs / kBlock);
    for (int b = 0; b < blocks; ++b) {
      const float bar = rig.context.bar_phase;
      rig.Process(in, out);
      const float ph = rig.phaser->lfo_phase();
      if (b > 0 && ph < last) {
        ++wraps;
      }
      last = ph;
      // The phase at the block's end against the bar's.
      float expected = 4.0f * (bar + rig.context.bar_increment * kBlock);
      expected -= floorf(expected);
      float error = fabsf(ph - expected);
      error = fminf(error, 1.0f - error);
      worst = fmaxf(worst, error);
    }
    test::Note("beat %.2f s: %d cycles in 4 s, worst phase error %.4f",
               beat, wraps, worst);
    CHECK(abs(wraps - int(4.0f / beat)) <= 1);
    CHECK(worst < 0.01f);
  }

  // A tempo change mid-way: still locked a few hundred ms later.
  Rig rig;
  rig.context.sync_mask = 1 << Phaser::PARAM_RATE;
  rig.params[Phaser::PARAM_RATE] = quarter;
  Frame in[kBlock], out[kBlock];
  memset(in, 0, sizeof(in));
  for (int b = 0; b < 3000; ++b) {
    if (b == 1000) {
      rig.SetTempo(0.4f);
    }
    rig.Process(in, out);
  }
  float expected = 4.0f * rig.context.bar_phase;
  expected -= floorf(expected);
  float error = fabsf(rig.phaser->lfo_phase() - expected);
  error = fminf(error, 1.0f - error);
  test::Note("after a tempo change: phase error %.4f", error);
  CHECK(error < 0.01f);
}
